#!/usr/bin/env python3
"""Compile an ASCII level (levels/*.txt) into a .bil blob.

The blob layout is DESIGN 11 and is documented in include/level.h; the C loader
in src/level.c reads exactly this.  The legend below is the same table as the
one in src/level.c, and test/test_level.py parses both and asserts they agree -
a silent divergence between the compiler and the loader shows up as a wrong
wall, which is the worst kind of bug to chase.

    python3 tools/mklevel.py levels/level1.txt -o levels/level1.bil
"""
import argparse
import collections
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from consts import CONST                                        # noqa: E402

# Read out of include/, never restated: the compiler and the loader disagreeing
# about a limit or a cell value is exactly the defect this file exists to avoid.
MAGIC = bytes((CONST["LEVEL_BLOB_MAGIC_0"], CONST["LEVEL_BLOB_MAGIC_1"],
               CONST["LEVEL_BLOB_MAGIC_2"], CONST["LEVEL_BLOB_MAGIC_3"]))
HEADER_BYTES = CONST["LEVEL_BLOB_HEADER_BYTES"]
ENTITY_BYTES = CONST["LEVEL_BLOB_ENTITY_BYTES"]
NAME_LEN = CONST["LEVEL_NAME_LEN"]
MAP_MAX_DIM = CONST["MAP_MAX_DIM"]
MAX_ENTITIES = CONST["LEVEL_MAX_ENTITIES"]
MAX_DOORS = CONST["DOOR_MAX_COUNT"]
CELL_RESERVED_BASE = CONST["CELL_RESERVED_BASE"]
BRADS_PER_TURN = CONST["BRADS_PER_TURN"]

CELL_EMPTY = CONST["CELL_EMPTY"]
CELL_WALL_MAX = CONST["CELL_WALL_MAX"]
CELL_DOOR_BASE = CONST["CELL_DOOR_BASE"]
CELL_DOOR_MAX = CONST["CELL_DOOR_MAX"]
# DESIGN 11 rule 4: a terminal door seals the border because it is touched,
# never passed through.  These two are the only cell values legal on a border.
DOOR_SEALED = CONST["DOOR_SEALED"]
DOOR_SECTOR_EXIT = CONST["DOOR_SECTOR_EXIT"]
TERMINAL_DOORS = (DOOR_SEALED, DOOR_SECTOR_EXIT)

# DESIGN 11 rule 3: the variants that stand in a jamb between two rooms, and so
# must have exactly two OPPOSITE open neighbours.
DOOR_PLAIN = CONST["DOOR_PLAIN"]
DOOR_LOCK_ALPHA = CONST["DOOR_LOCK_ALPHA"]
DOOR_LOCK_BETA = CONST["DOOR_LOCK_BETA"]
DOOR_LOCK_GAMMA = CONST["DOOR_LOCK_GAMMA"]
DOOR_CORRUPTED = CONST["DOOR_CORRUPTED"]
ORDINARY_DOORS = (DOOR_PLAIN, DOOR_LOCK_ALPHA, DOOR_LOCK_BETA, DOOR_LOCK_GAMMA,
                  DOOR_CORRUPTED)

NEIGHBOURS = ((0, -1), (1, 0), (0, 1), (-1, 0))
#: The two ways a pair of neighbours can be opposite: north/south, west/east.
AXES = (((0, -1), (0, 1)), ((-1, 0), (1, 0)))
#: The minimum open neighbours a floor cell needs before it stops reading as a
#: dead-end pocket (DESIGN 11 rule 8).
DEAD_END_OPEN_NEIGHBOURS = 2
#: DESIGN 11 rule 5's alcove: three wall neighbours and one open side.
ALCOVE_WALLS = 3

# EntityType, mirroring include/level.h.
ENT = {
    "NONE": 0, "WATCHDOG": 1, "SENTRY": 2, "TRACER": 3, "BLACK_ICE": 4,
    "ANCHOR": 5, "TOKEN_ALPHA": 6, "TOKEN_BETA": 7, "TOKEN_GAMMA": 8,
    "CYCLES_SMALL": 9, "CYCLES_LARGE": 10, "INTEGRITY_SMALL": 11,
    "INTEGRITY_LARGE": 12, "SCRUBBER": 13, "DATA_CACHE": 14,
}

# DESIGN 10: the token each locked variant demands, as the entity that carries
# it.  Rule 7's flood consults this and nothing else, so "which key opens which
# gate" is written down once.
TOKEN_FOR_DOOR = {
    DOOR_LOCK_ALPHA: ENT["TOKEN_ALPHA"],
    DOOR_LOCK_BETA: ENT["TOKEN_BETA"],
    DOOR_LOCK_GAMMA: ENT["TOKEN_GAMMA"],
}
TOKEN_TYPES = tuple(TOKEN_FOR_DOOR.values())
PICKUP_TYPES = (ENT["CYCLES_SMALL"], ENT["CYCLES_LARGE"], ENT["INTEGRITY_SMALL"],
                ENT["INTEGRITY_LARGE"], ENT["SCRUBBER"], ENT["DATA_CACHE"])
# Doors a body walks through by touching them, with nothing in its pockets: the
# plain gate, and the exit arch (which ends the sector rather than opening).
# The sealed gate and the jammed leaf never open for anybody.
ALWAYS_PASSABLE_DOORS = (DOOR_PLAIN, DOOR_SECTOR_EXIT)

# glyph -> (cell value, entity type, is player start)
LEGEND = {
    ".": (0, ENT["NONE"], False),
    "#": (1, ENT["NONE"], False),
    "=": (2, ENT["NONE"], False),
    "%": (3, ENT["NONE"], False),
    "|": (4, ENT["NONE"], False),
    "^": (5, ENT["NONE"], False),
    "?": (6, ENT["NONE"], False),
    "A": (7, ENT["NONE"], False),
    "X": (8, ENT["NONE"], False),
    "+": (16, ENT["NONE"], False),
    "1": (17, ENT["NONE"], False),
    "2": (18, ENT["NONE"], False),
    "3": (19, ENT["NONE"], False),
    "S": (21, ENT["NONE"], False),
    "~": (22, ENT["NONE"], False),
    ">": (23, ENT["NONE"], False),
    "@": (0, ENT["NONE"], True),
    "w": (0, ENT["WATCHDOG"], False),
    "t": (0, ENT["TRACER"], False),
    "B": (0, ENT["BLACK_ICE"], False),
    "s": (0, ENT["SENTRY"], False),
    "*": (0, ENT["ANCHOR"], False),
    "p": (0, ENT["TOKEN_ALPHA"], False),
    "q": (0, ENT["TOKEN_BETA"], False),
    "r": (0, ENT["TOKEN_GAMMA"], False),
    "c": (0, ENT["CYCLES_SMALL"], False),
    "C": (0, ENT["CYCLES_LARGE"], False),
    "i": (0, ENT["INTEGRITY_SMALL"], False),
    "I": (0, ENT["INTEGRITY_LARGE"], False),
    "u": (0, ENT["SCRUBBER"], False),
    "d": (0, ENT["DATA_CACHE"], False),
}

HEADER_DEFAULTS = {
    "name": "",
    "sector": 0,
    "palette": 0,
    "texture_set": 0,
    "facing": 0,
    "rng_seed": 0,
    "par": 3000,
    # DESIGN 9.1: thousandths of a percent per SECOND, 180 on every shipped level.
    "trace_base_rate": 180,
    "trace_start": 0,
    "trace_carry_cap": 25,
}

# Authored files spell some keys the long way; src/level.c accepts both too.
HEADER_ALIASES = {
    "palette_variant": "palette",
    "start_facing": "facing",
    "par_ticks": "par",
    "sector_index": "sector",
}

# Keys that restate something the map already says.  They are not stored; they
# are cross-checked against the map, so a header that has drifted from the grid
# it describes is a compile error instead of a silently ignored line.
DERIVED_KEYS = ("width", "height", "start_x", "start_y", "entity_count",
                "watchdogs", "tracers", "sentries")

# Free prose for whoever authors the map next.  Stored nowhere and checked
# against nothing - but named here, so that a MISSPELLED real key is still an
# error rather than something the compiler decides must be a note.
ANNOTATION_KEYS = ("note",)


class LevelError(Exception):
    pass


def parse_source(text):
    """Split the source into its header dictionary and its map rows.

    A header line is '#' followed by a space; a map row starts with a legend
    glyph and never contains a space, so '#' is unambiguously both the comment
    marker and the wall glyph.
    """
    header = dict(HEADER_DEFAULTS)
    rows = []
    for line in text.splitlines():
        line = line.rstrip("\r")
        if not line:
            continue
        if line.startswith("# "):
            key, separator, value = line[2:].partition(":")
            if not separator:
                continue                    # a prose comment, not a header line
            key = HEADER_ALIASES.get(key.strip(), key.strip())
            # An unknown key is a compile error, not a dropped line: a typo in
            # `trace_base_rate` used to compile a level with the default rate
            # and no complaint, which plays wrong and looks fine.
            if key in ANNOTATION_KEYS:
                continue
            if key not in header and key not in DERIVED_KEYS:
                raise LevelError("unknown header key %r" % key)
            header[key] = value.strip()
            continue
        rows.append(line)
    return header, rows


def build_grid(rows):
    if not rows:
        raise LevelError("no map rows")
    width = len(rows[0])
    height = len(rows)
    if width > MAP_MAX_DIM or height > MAP_MAX_DIM:
        raise LevelError("map is %dx%d, over the %d limit" % (width, height, MAP_MAX_DIM))
    cells = bytearray(width * height)
    entities = []
    start = None
    for y, row in enumerate(rows):
        if len(row) != width:
            raise LevelError("row %d is %d wide, expected %d" % (y, len(row), width))
        for x, glyph in enumerate(row):
            if glyph not in LEGEND:
                raise LevelError("row %d column %d: glyph %r is not in the legend"
                                 % (y, x, glyph))
            cell, entity, is_start = LEGEND[glyph]
            if cell >= CELL_RESERVED_BASE:
                raise LevelError("row %d column %d: reserved cell value %d" % (y, x, cell))
            cells[y * width + x] = cell
            if is_start:
                if start is not None:
                    raise LevelError("more than one '@' player start")
                start = (x, y)
            if entity != ENT["NONE"]:
                entities.append((entity, x, y, 0, 0))
    if start is None:
        raise LevelError("no '@' player start")
    if len(entities) > MAX_ENTITIES:
        raise LevelError("%d entities, over the %d limit" % (len(entities), MAX_ENTITIES))
    return width, height, cells, entities, start


def validate_border(width, height, cells):
    """DESIGN 11 rule 2: every border cell is a wall or a terminal door.

    The DDA has no bounds test in its inner loop, and a terminal door is safe
    there because it never opens under the caster - a `S` or a `>` is an arch
    in the outer wall that is touched, not walked through.  Rule 4's other half
    is enforced here too: no ordinary door may sit on the border.
    """
    def seals(x, y):
        value = cells[y * width + x]
        return 1 <= value <= CELL_WALL_MAX or value in TERMINAL_DOORS

    for x in range(width):
        for y in (0, height - 1):
            if not seals(x, y):
                raise LevelError("border is not sealed at (%d, %d)" % (x, y))
    for y in range(height):
        for x in (0, width - 1):
            if not seals(x, y):
                raise LevelError("border is not sealed at (%d, %d)" % (x, y))
    for y in range(height):
        for x in range(width):
            on_border = x in (0, width - 1) or y in (0, height - 1)
            value = cells[y * width + x]
            if value in TERMINAL_DOORS and not on_border:
                raise LevelError("terminal door %d at (%d, %d) is not on the border"
                                 % (value, x, y))


class Grid:
    """A compiled map, with the neighbourhood questions DESIGN 11's rules ask.

    The rules below are the compiler's, and `levels/validate_levels.py` calls
    the same functions rather than keeping a second glyph-level copy of them: a
    validator that passes a map the compiler then rejects is not a validator.
    """

    def __init__(self, width, height, cells):
        self.width = width
        self.height = height
        self.cells = cells

    def at(self, x, y):
        """The cell value at (x, y), or None off the grid."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.cells[y * self.width + x]
        return None

    def on_border(self, x, y):
        return x in (0, self.width - 1) or y in (0, self.height - 1)

    def is_wall(self, x, y):
        value = self.at(x, y)
        return value is not None and 1 <= value <= CELL_WALL_MAX

    def is_floor(self, x, y):
        """A cell a body can STAND in: empty, never a wall and never a door.
        A closed leaf is not a gap, and an open one is not somewhere to stand."""
        return self.at(x, y) == CELL_EMPTY

    def open_neighbours(self, x, y):
        return [(x + dx, y + dy) for dx, dy in NEIGHBOURS if self.is_floor(x + dx, y + dy)]

    def walkable_neighbours(self, x, y):
        """Cells a body could move THROUGH, doors included.  Rule 8's question,
        which is about geometry a chase AI might enter and not about standing
        room."""
        return [(x + dx, y + dy) for dx, dy in NEIGHBOURS
                if self.at(x + dx, y + dy) is not None and not self.is_wall(x + dx, y + dy)]

    def cells_of(self, values):
        return [(x, y) for y in range(self.height) for x in range(self.width)
                if self.cells[y * self.width + x] in values]


def validate_door_jambs(grid):
    """DESIGN 11 rule 3: an ordinary door has exactly two OPPOSITE open
    neighbours.

    That pair is the door's AXIS, and DESIGN 10.1 puts the door plane on the
    cell midline perpendicular to it - so a door with three open neighbours, or
    with two on a corner, has no axis and the renderer and the collider would be
    free to disagree about which way the leaf slides.  Because the rule holds,
    the axis is DERIVABLE from the two open neighbours at load time and needs no
    byte in the .bil: nothing in the engine stores it, so nothing can store it
    wrong.
    """
    for x, y in grid.cells_of(ORDINARY_DOORS):
        if grid.on_border(x, y):
            raise LevelError("door %d at (%d, %d) sits on the border (rule 4)"
                             % (grid.at(x, y), x, y))
        opened = grid.open_neighbours(x, y)
        axes = [pair for pair in AXES
                if (x + pair[0][0], y + pair[0][1]) in opened
                and (x + pair[1][0], y + pair[1][1]) in opened]
        if len(opened) != 2 or len(axes) != 1:
            raise LevelError(
                "door %d at (%d, %d) has %d open neighbours on %d axis/axes, "
                "expected 2 opposite" % (grid.at(x, y), x, y, len(opened), len(axes)))


def validate_terminal_doors(grid):
    """DESIGN 11 rule 4: a terminal door lies on the border with exactly one
    open neighbour - it is an arch in the outer wall, touched and never passed
    through.  validate_border enforces the other half, that it is ON the border
    and that no ordinary door is."""
    for x, y in grid.cells_of(TERMINAL_DOORS):
        opened = grid.open_neighbours(x, y)
        if len(opened) != 1:
            raise LevelError("terminal door %d at (%d, %d) has %d open neighbours, "
                             "expected exactly 1" % (grid.at(x, y), x, y, len(opened)))


def validate_sentry_alcoves(grid, entities):
    """DESIGN 11 rule 5: a Sentry stands in a 1-cell alcove with exactly three
    wall neighbours and one open side.  DESIGN 8 then makes the alcove's shape
    the authority on which way the turret looks, so a Sentry the shape does not
    describe has a facing decided by whichever neighbour was scanned first."""
    for entity, x, y, _facing, _extra in entities:
        if entity != ENT["SENTRY"]:
            continue
        walls = sum(1 for dx, dy in NEIGHBOURS if grid.is_wall(x + dx, y + dy))
        opened = grid.open_neighbours(x, y)
        if walls != ALCOVE_WALLS or len(opened) != 1:
            raise LevelError("Sentry alcove at (%d, %d) has %d wall and %d open "
                             "neighbours, expected %d and 1"
                             % (x, y, walls, len(opened), ALCOVE_WALLS))


def lock_ordered_reach(grid, entities, start):
    """DESIGN 11 rule 7's flood: which cells the player can walk to, and the
    order in which the tokens become reachable.

    Re-running the flood each time a token comes into reach is what proves the
    route is walkable in a LEGAL order, rather than merely connected once every
    gate is assumed open.  Returns ({cell: steps from the start}, [[token types]
    per step]); the distances are what the validator's report prints.
    """
    token_at = {(x, y): entity for entity, x, y, _f, _e in entities
                if entity in TOKEN_TYPES}
    held = set()
    order = []
    while True:
        passable = set(ALWAYS_PASSABLE_DOORS)
        passable |= {door for door, token in TOKEN_FOR_DOOR.items() if token in held}
        distance = {start: 0}
        frontier = collections.deque([start])
        while frontier:
            x, y = frontier.popleft()
            if grid.at(x, y) == DOOR_SECTOR_EXIT:
                continue                # entering the exit ends the level
            for dx, dy in NEIGHBOURS:
                step = (x + dx, y + dy)
                value = grid.at(*step)
                if step in distance or value is None:
                    continue
                if value != CELL_EMPTY and value not in passable:
                    continue
                distance[step] = distance[(x, y)] + 1
                frontier.append(step)
        gained = sorted({token_at[cell] for cell in distance if cell in token_at} - held)
        if not gained:
            return distance, order
        held |= set(gained)
        order.append(gained)


def validate_reachable(grid, entities, start):
    """DESIGN 11 rule 7: the sector exit, every token and every pickup must fall
    inside the lock-ordered flood - and so must every body, because an enemy the
    player can never meet is a body the level pays for and never uses."""
    reached, _order = lock_ordered_reach(grid, entities, start)

    exits = grid.cells_of((DOOR_SECTOR_EXIT,))
    if not exits:
        raise LevelError("no '>' sector exit")
    for cell in exits:
        if cell not in reached:
            raise LevelError("the sector exit at (%d, %d) is not reachable in a "
                             "legal token order" % cell)
    for entity, x, y, _facing, _extra in entities:
        if (x, y) in reached:
            continue
        if entity in TOKEN_TYPES or entity in PICKUP_TYPES:
            raise LevelError("the pickup at (%d, %d) is not reachable in a legal "
                             "token order" % (x, y))
        raise LevelError("the entity at (%d, %d) is walled off from the player" % (x, y))


def warn_dead_ends(grid, entities):
    """DESIGN 11 rule 8, a WARNING and not a refusal: a floor cell with fewer
    than two open neighbours that is not a Sentry alcove - the 1-cell pocket
    that reads as dead geometry and that a chase AI has no reason to enter."""
    alcoves = {(x, y) for entity, x, y, _f, _e in entities if entity == ENT["SENTRY"]}
    pockets = [(x, y) for x, y in grid.cells_of((CELL_EMPTY,))
               if (x, y) not in alcoves
               and len(grid.walkable_neighbours(x, y)) < DEAD_END_OPEN_NEIGHBOURS]
    return ["(%d, %d): 1-cell pocket - floor with fewer than two open neighbours" % cell
            for cell in pockets]


def header_number(header, key):
    """A header value as an int.  A non-numeric one is a LevelError like every
    other authoring mistake, not a ValueError escaping from the compiler."""
    text = str(header[key]).strip()
    if not text:
        return 0
    try:
        return int(text)
    except ValueError:
        raise LevelError("header %s = %r is not a number" % (key, text)) from None


def header_int(header, key, limit):
    value = header_number(header, key)
    if not 0 <= value <= limit:
        raise LevelError("header %s = %d is out of range 0..%d" % (key, value, limit))
    return value


def validate_derived_header(header, width, height, start, entities):
    """Cross-check every header key that restates something the map already
    says.  These are not stored - the map is the truth - so an unchecked one is
    a comment that quietly goes stale."""
    def population(entity_type):
        return sum(1 for entity in entities if entity[0] == ENT[entity_type])

    stated = {
        "width": width, "height": height,
        "start_x": start[0], "start_y": start[1],
        "entity_count": len(entities),
        "watchdogs": population("WATCHDOG"),
        "tracers": population("TRACER"),
        "sentries": population("SENTRY"),
    }
    for key, actual in stated.items():
        if key in header and header_number(header, key) != actual:
            raise LevelError("header %s = %s but the map says %d" % (key, header[key], actual))


def validate_door_count(cells):
    """The engine's door table is DOOR_MAX_COUNT long.  The loader refuses a
    grid with more, and so does the compiler: silently dropping the 65th door
    would leave a level whose last gates never open."""
    doors = sum(1 for value in cells if CELL_DOOR_BASE <= value <= CELL_DOOR_MAX)
    if doors > MAX_DOORS:
        raise LevelError("%d doors, over the %d the door table holds" % (doors, MAX_DOORS))


def compile_level(text, warnings=None):
    """Compile one ASCII level to its .bil blob.

    DESIGN 11's rule 8 is a WARNING and not a refusal, so it is appended to
    `warnings` when the caller passes a list and dropped otherwise - the
    compiler's answer is still the blob, and a level with a dead-end pocket
    still ships.
    """
    header, rows = parse_source(text)
    width, height, cells, entities, start = build_grid(rows)
    grid = Grid(width, height, cells)
    validate_derived_header(header, width, height, start, entities)
    validate_border(width, height, cells)
    validate_door_jambs(grid)
    validate_terminal_doors(grid)
    validate_sentry_alcoves(grid, entities)
    validate_door_count(cells)
    validate_reachable(grid, entities, start)
    if warnings is not None:
        warnings.extend(warn_dead_ends(grid, entities))

    name = str(header["name"]).encode("ascii", "replace")[:NAME_LEN]
    blob = bytearray()
    blob += MAGIC
    blob += name.ljust(NAME_LEN, b"\0")
    blob += struct.pack(
        ">BBBBBBBBHIHBBHH",
        width, height,
        header_int(header, "sector", 7),
        header_int(header, "palette", 3),
        header_int(header, "texture_set", 2),
        0,                                          # pad
        start[0], start[1],
        header_int(header, "facing", BRADS_PER_TURN - 1),
        header_int(header, "rng_seed", 0xffffffff),
        header_int(header, "trace_base_rate", 0xffff),
        header_int(header, "trace_start", 100),
        header_int(header, "trace_carry_cap", 100),
        header_int(header, "par", 0xffff),
        len(entities),
    )
    assert len(blob) == HEADER_BYTES, "header is %d bytes, expected %d" % (len(blob), HEADER_BYTES)
    blob += cells
    for entity, x, y, facing, extra in entities:
        blob += struct.pack(">BBBBB", entity, x, y, facing, extra)
    assert len(blob) == HEADER_BYTES + width * height + len(entities) * ENTITY_BYTES
    return bytes(blob)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="the levels/*.txt source file")
    parser.add_argument("-o", "--output", required=True, help="the .bil file to write")
    args = parser.parse_args()

    with open(args.source, "r", encoding="ascii") as handle:
        text = handle.read()
    warnings = []
    try:
        blob = compile_level(text, warnings)
    except LevelError as error:
        sys.stderr.write("%s: %s\n" % (args.source, error))
        return 1
    for warning in warnings:
        sys.stderr.write("%s: warning: %s\n" % (args.source, warning))
    with open(args.output, "wb") as handle:
        handle.write(blob)
    return 0


if __name__ == "__main__":
    sys.exit(main())
