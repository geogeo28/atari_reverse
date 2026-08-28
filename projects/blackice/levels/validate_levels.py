#!/usr/bin/env python3
"""BLACK ICE level validator - DESIGN.md v2.

Parses any `levels/*.txt` authored in the v2 legend (SS11) and applies the eight compiler rules
plus the two compiler warnings, so a map is proved sound before `tools/mklevel.py` compiles it:

  rule 1  rectangular map, <= 64x64, exactly one `@` (and exactly one `>`)
  rule 2  sealed border: every border cell is a wall or a terminal door
  rule 3  ordinary doors (16, 17, 18, 19, 22) have exactly two OPPOSITE open neighbours
  rule 4  terminal doors (21, 23) lie ON the border with exactly one open neighbour, and no
          other door variant may sit on the border
  rule 5  every Sentry alcove has exactly three wall neighbours and one open neighbour
  rule 6  entity count <= 64, no glyph outside the legend
  rule 7  lock-ordered flood fill proving every token, every pickup and the exit are reachable in
          a legal token order - and reporting that order
  rule 8  WARNING: a floor cell with fewer than two open neighbours that is not a Sentry alcove
  rule 9  WARNING: a `>` gate or `X` plating run first seen from beyond band 2 (SS3 fog)

Header fields are range-checked against the SS11 binary field widths and the SS9/SS14 shipped
values, so a unit slip (a v1 per-tick `trace_base_rate`, say) is caught here and not in play.

Usage:  python3 validate_levels.py [level file or directory ...]
Exit status 0 when every level passes; warnings never fail a level.
"""

import os
import re
import sys
from collections import deque

# ---------------------------------------------------------------------------
# The legend and the numeric contract. DESIGN.md v2 SS9/SS11/SS14 own these.
# ---------------------------------------------------------------------------

MAX_DIM = 64                     # grid is 64x64 cells maximum
MAX_ENTITIES = 64                # the entity list is capped at 64 records
BAND2_CELLS = 9                  # integrity green fogs to slate past band 2 (SS3)
BRAD_TURN = 1024                 # 1024 brads = 360 degrees; 0 = north, clockwise
SHIPPED_TRACE_BASE_RATE = 180    # thousandths of a percent per SECOND (SS9.1: 0.18 %/s)
SHIPPED_TRACE_CARRY_CAP = 25     # percent - SS9 makes this the single authority on start value

WALL_CELLS = {                   # glyph -> wall texture id (1..15)
    '#': 1, '=': 2, '%': 3, '|': 4, '^': 5, '?': 6, 'A': 7, 'X': 8,
}
EXIT_PLATING = 'X'
DOOR_CELLS = {                   # glyph -> door variant (16..31)
    '+': 16, '1': 17, '2': 18, '3': 19, 'S': 21, '~': 22, '>': 23,
}
ORDINARY_DOORS = ('+', '1', '2', '3', '~')          # rule 3
TERMINAL_DOORS = ('S', '>')                         # rule 4: on the border, one open neighbour
ALWAYS_OPEN_DOORS = ('+', '>')                      # bump-to-open plain gate, and the exit gate
NEVER_OPEN_DOORS = ('S', '~')                       # sealed arch, and the door jammed at 3/8

START_GLYPH = '@'
EXIT_GLYPH = '>'
SENTRY_GLYPH = 's'
FLOOR_ENTITIES = {               # every entity is a floor entity in v2; the cell compiles to 0
    'w': ('enemy', 'Watchdog'), 't': ('enemy', 'Tracer'), 'B': ('enemy', 'Black ICE'),
    's': ('enemy', 'Sentry'), '*': ('enemy', 'anchor'),
    'p': ('token', 'ALPHA'), 'q': ('token', 'BETA'), 'r': ('token', 'GAMMA'),
    'c': ('pickup', 'cycles small'), 'C': ('pickup', 'cycles large'),
    'i': ('pickup', 'integrity small'), 'I': ('pickup', 'integrity large'),
    'u': ('pickup', 'scrubber'), 'd': ('pickup', 'data cache'),
}
ENEMY_GLYPHS = ('w', 's', 't', 'B', '*')
TOKEN_GLYPHS = ('p', 'q', 'r')
PICKUP_GLYPHS = ('c', 'C', 'i', 'I', 'u', 'd')
TOKEN_FOR_DOOR = {'1': 'p', '2': 'q', '3': 'r'}     # locked door -> the token that opens it
TOKEN_NAMES = {'p': 'ALPHA', 'q': 'BETA', 'r': 'GAMMA'}

PASSABLE_BASE = set(FLOOR_ENTITIES) | {'.', START_GLYPH} | set(ALWAYS_OPEN_DOORS)

HEADER_RE = re.compile(r'^#\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$')
FENCE_RE = re.compile(r'^\s*```')
REPEATABLE_KEYS = ('note',)
# key -> (low, high) inclusive, from the SS11 field widths and the SS9 percentages
HEADER_RANGES = {
    'sector': (0, 7), 'width': (1, MAX_DIM), 'height': (1, MAX_DIM),
    'palette_variant': (0, 3), 'texture_set': (0, 2),
    'start_x': (0, MAX_DIM - 1), 'start_y': (0, MAX_DIM - 1),
    'start_facing': (0, BRAD_TURN - 1), 'rng_seed': (0, 0xFFFFFFFF),
    'trace_base_rate': (0, 0xFFFF), 'trace_start': (0, 100), 'trace_carry_cap': (0, 100),
    'par_ticks': (0, 0xFFFF), 'entity_count': (0, MAX_ENTITIES),
    'watchdogs': (0, MAX_ENTITIES), 'sentries': (0, MAX_ENTITIES), 'tracers': (0, MAX_ENTITIES),
}
REQUIRED_KEYS = ('name', 'sector', 'palette_variant', 'texture_set', 'start_facing', 'rng_seed',
                 'trace_base_rate', 'trace_start', 'trace_carry_cap', 'par_ticks', 'entity_count')
ROSTER_KEYS = (('watchdogs', 'w'), ('sentries', 's'), ('tracers', 't'))
NEIGHBOURS = ((0, -1), (0, 1), (-1, 0), (1, 0))
AXES = (((0, -1), (0, 1)), ((-1, 0), (1, 0)))       # north/south pair, west/east pair


class Level:
    """A parsed level: header dict, map rows, and the derived glyph index."""

    def __init__(self, path, header, rows):
        self.path = path
        self.name = header.get('name', os.path.basename(path))
        self.header = header
        self.rows = rows
        self.height = len(rows)
        self.width = len(rows[0]) if rows else 0
        self.at = {}                                # glyph -> list of (x, y)
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                self.at.setdefault(ch, []).append((x, y))

    def glyph(self, x, y):
        return self.rows[y][x]

    def count(self, glyphs):
        return sum(len(self.at.get(g, ())) for g in glyphs)

    def in_bounds(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def on_border(self, x, y):
        return x in (0, self.width - 1) or y in (0, self.height - 1)

    def is_wall(self, x, y):
        return self.glyph(x, y) in WALL_CELLS

    def is_solid(self, x, y):
        """Solid for the jamb and alcove rules: a wall, or a door (a closed door is not a gap)."""
        ch = self.glyph(x, y)
        return ch in WALL_CELLS or ch in DOOR_CELLS

    def neighbours(self, x, y):
        for dx, dy in NEIGHBOURS:
            nx, ny = x + dx, y + dy
            if self.in_bounds(nx, ny):
                yield nx, ny


def parse_level(path):
    """Return (Level, [errors]). Header lines are `# key: value`; a map row never matches that."""
    header, rows, errors = {}, [], []
    for lineno, raw in enumerate(open(path, encoding='ascii').read().splitlines(), 1):
        line = raw.rstrip()
        if not line or FENCE_RE.match(line):
            continue
        match = HEADER_RE.match(line)
        if match and rows:
            errors.append('line %d: header key %r appears after the map block' % (lineno, match.group(1)))
            continue
        if match:
            key, value = match.group(1), match.group(2)
            if key in REPEATABLE_KEYS:
                header.setdefault(key, []).append(value)
            elif key in header:
                errors.append('line %d: duplicate header key %r' % (lineno, key))
            else:
                header[key] = value
            continue
        rows.append(line)
    for key in HEADER_RANGES:
        if key in header:
            try:
                header[key] = int(header[key])
            except ValueError:
                errors.append('header %r is not an integer: %r' % (key, header[key]))
    return Level(path, header, rows), errors


def check_header(lvl, errors, warnings):
    """Range-check every SS11 field, then flag the SS9/SS14 shipped values that drifted."""
    for key in REQUIRED_KEYS:
        if key not in lvl.header:
            errors.append('header is missing required key %r' % key)
    for key, (low, high) in HEADER_RANGES.items():
        value = lvl.header.get(key)
        if isinstance(value, int) and not low <= value <= high:
            errors.append('header %s=%d is outside its field range %d..%d' % (key, value, low, high))
    rate = lvl.header.get('trace_base_rate')
    if isinstance(rate, int) and rate != SHIPPED_TRACE_BASE_RATE:
        warnings.append('trace_base_rate=%d; SS14 ships %d (thousandths of a percent per SECOND)'
                        % (rate, SHIPPED_TRACE_BASE_RATE))
    cap = lvl.header.get('trace_carry_cap')
    if isinstance(cap, int) and cap != SHIPPED_TRACE_CARRY_CAP:
        warnings.append('trace_carry_cap=%d; SS9 ships %d on every level' % (cap, SHIPPED_TRACE_CARRY_CAP))


def check_shape(lvl, errors):
    """Rule 1: rectangular, within the grid limit, and agreeing with the header."""
    if not lvl.rows:
        errors.append('map block is empty')
        return
    widths = {len(r) for r in lvl.rows}
    if len(widths) != 1:
        errors.append('map is not rectangular: row widths %s' % sorted(widths))
    if lvl.width > MAX_DIM or lvl.height > MAX_DIM:
        errors.append('map %dx%d exceeds the %dx%d limit' % (lvl.width, lvl.height, MAX_DIM, MAX_DIM))
    for key, actual in (('width', lvl.width), ('height', lvl.height)):
        if key in lvl.header and lvl.header[key] != actual:
            errors.append('header %s=%s but the map block is %d' % (key, lvl.header[key], actual))


def check_glyphs(lvl, errors):
    """Rule 6: no glyph outside the legend, i.e. no reserved cell value."""
    known = set(WALL_CELLS) | set(DOOR_CELLS) | set(FLOOR_ENTITIES) | {'.', START_GLYPH}
    for y, row in enumerate(lvl.rows):
        for x, ch in enumerate(row):
            if ch not in known:
                errors.append('(%d,%d): glyph %r is not in the legend' % (x, y, ch))


def check_border(lvl, errors):
    """Rule 2: every border cell is a wall or a terminal door."""
    for x in range(lvl.width):
        for y in range(lvl.height):
            if not lvl.on_border(x, y):
                continue
            ch = lvl.glyph(x, y)
            if ch not in WALL_CELLS and ch not in TERMINAL_DOORS:
                errors.append('(%d,%d): border cell %r is neither wall nor terminal door' % (x, y, ch))


def check_singletons(lvl, errors):
    """Rule 1: exactly one start; the format also carries exactly one sector exit."""
    for glyph, label in ((START_GLYPH, 'player start'), (EXIT_GLYPH, 'sector exit')):
        found = lvl.at.get(glyph, [])
        if len(found) != 1:
            errors.append('expected exactly one %s %r, found %d' % (label, glyph, len(found)))
    start = lvl.at.get(START_GLYPH, [])
    if len(start) == 1:
        x, y = start[0]
        for key, value in (('start_x', x), ('start_y', y)):
            if key in lvl.header and lvl.header[key] != value:
                errors.append('header %s=%s but %r sits at %d' % (key, lvl.header[key], START_GLYPH, value))


def open_neighbours(lvl, x, y):
    """Cells a body could stand in: not wall, not a door. Used by rules 3, 4 and 5."""
    return [(nx, ny) for nx, ny in lvl.neighbours(x, y) if not lvl.is_solid(nx, ny)]


def walkable_neighbours(lvl, x, y):
    """Cells a body could move through, doors included. Used by warning 8."""
    return [(nx, ny) for nx, ny in lvl.neighbours(x, y) if not lvl.is_wall(nx, ny)]


def check_ordinary_doors(lvl, errors):
    """Rule 3: exactly two opposite open neighbours - that pair is the door's axis."""
    for glyph in ORDINARY_DOORS:
        for x, y in lvl.at.get(glyph, ()):
            if lvl.on_border(x, y):
                errors.append('(%d,%d): ordinary door %r sits on the border (rule 4)' % (x, y, glyph))
                continue
            opened = open_neighbours(lvl, x, y)
            axes = [1 for (adx, ady), (bdx, bdy) in AXES
                    if (x + adx, y + ady) in opened and (x + bdx, y + bdy) in opened]
            if len(opened) != 2 or len(axes) != 1:
                errors.append('(%d,%d): door %r has %d open neighbours on %d axis/axes, expected 2 opposite'
                              % (x, y, glyph, len(opened), len(axes)))


def check_terminal_doors(lvl, errors):
    """Rule 4: variants 21 and 23 lie on the border with exactly one open neighbour."""
    for glyph in TERMINAL_DOORS:
        for x, y in lvl.at.get(glyph, ()):
            if not lvl.on_border(x, y):
                errors.append('(%d,%d): terminal door %r is not on the map border' % (x, y, glyph))
            opened = open_neighbours(lvl, x, y)
            if len(opened) != 1:
                errors.append('(%d,%d): terminal door %r has %d open neighbours, expected exactly 1'
                              % (x, y, glyph, len(opened)))


def check_sentries(lvl, errors):
    """Rule 5: a Sentry alcove has exactly three wall neighbours and one open neighbour."""
    for x, y in lvl.at.get(SENTRY_GLYPH, ()):
        walls = [n for n in lvl.neighbours(x, y) if lvl.is_wall(*n)]
        opened = open_neighbours(lvl, x, y)
        if len(walls) != 3 or len(opened) != 1:
            errors.append('(%d,%d): Sentry alcove has %d wall and %d open neighbours, expected 3 and 1'
                          % (x, y, len(walls), len(opened)))


def lock_ordered_reach(lvl):
    """Rule 7: BFS from the start, unlocking a token door only once its token has been reached.

    Returns (distance map, [token glyphs in the order they became reachable]). Re-running the flood
    each time a token is picked up is what proves the route is walkable in a legal order rather
    than merely connected once every door is assumed open.
    """
    start = lvl.at.get(START_GLYPH, [])
    if not start:
        return {}, []
    held, order, dist = set(), [], {}
    while True:
        passable = set(PASSABLE_BASE) | {d for d, tok in TOKEN_FOR_DOOR.items() if tok in held}
        dist = {start[0]: 0}
        queue = deque(start)
        while queue:
            x, y = queue.popleft()
            if lvl.glyph(x, y) == EXIT_GLYPH:
                continue                            # entering the exit ends the level: walk no further
            for nx, ny in lvl.neighbours(x, y):
                if (nx, ny) in dist or lvl.glyph(nx, ny) not in passable:
                    continue
                dist[(nx, ny)] = dist[(x, y)] + 1
                queue.append((nx, ny))
        gained = sorted({lvl.glyph(x, y) for (x, y) in dist if lvl.glyph(x, y) in TOKEN_GLYPHS} - held)
        if not gained:
            return dist, order
        held |= set(gained)
        order.append(gained)


def check_reachability(lvl, dist, errors):
    """Rule 7: the exit, every token and every pickup must fall inside the lock-ordered flood."""
    exits = lvl.at.get(EXIT_GLYPH, [])
    if exits and exits[0] not in dist:
        errors.append('the sector exit at (%d,%d) is not reachable in a legal token order' % exits[0])
    for glyph in TOKEN_GLYPHS + PICKUP_GLYPHS:
        for x, y in lvl.at.get(glyph, ()):
            if (x, y) not in dist:
                errors.append('(%d,%d): %s %r is not reachable in a legal token order'
                              % (x, y, FLOOR_ENTITIES[glyph][1], glyph))


def check_entities_placed(lvl, dist, errors):
    """Every entity stands on floor, and on floor the player can actually get to."""
    for glyph in FLOOR_ENTITIES:
        for x, y in lvl.at.get(glyph, ()):
            if (x, y) not in dist:
                errors.append('(%d,%d): %s %r is walled off from the player'
                              % (x, y, FLOOR_ENTITIES[glyph][1], glyph))


def check_counts(lvl, errors):
    """Rule 6, plus the SS14 roster the header restates."""
    total = lvl.count(FLOOR_ENTITIES)
    if total > MAX_ENTITIES:
        errors.append('%d entities exceeds the %d-entity level cap' % (total, MAX_ENTITIES))
    if 'entity_count' in lvl.header and lvl.header['entity_count'] != total:
        errors.append('header entity_count=%s but the map holds %d entities'
                      % (lvl.header['entity_count'], total))
    for key, glyph in ROSTER_KEYS:
        if key in lvl.header and lvl.header[key] != lvl.count(glyph):
            errors.append('header %s=%s but the map holds %d' % (key, lvl.header[key], lvl.count(glyph)))


def check_dead_ends(lvl, dist, warnings):
    """Warning 8: a floor cell with fewer than two open neighbours that is not a Sentry alcove."""
    pockets = []
    for y, row in enumerate(lvl.rows):
        for x, ch in enumerate(row):
            if ch in WALL_CELLS or ch in DOOR_CELLS or ch == SENTRY_GLYPH:
                continue
            if len(walkable_neighbours(lvl, x, y)) < 2:
                pockets.append((x, y))
    for x, y in pockets:
        warnings.append('(%d,%d): 1-cell pocket - floor with fewer than two open neighbours' % (x, y))
    return len(pockets)


def approach_run(lvl, x, y):
    """How many floor cells you can see in a straight line out of a border gate."""
    opened = open_neighbours(lvl, x, y)
    if len(opened) != 1:
        return 0
    dx, dy = opened[0][0] - x, opened[0][1] - y
    run, cx, cy = 0, x + dx, y + dy
    while lvl.in_bounds(cx, cy) and not lvl.is_solid(cx, cy):
        run += 1
        cx, cy = cx + dx, cy + dy
    return run


def check_gate_band(lvl, warnings):
    """Warning 9: the exit gate and its plating must first be seen inside band 2 (SS3 fog)."""
    for x, y in lvl.at.get(EXIT_GLYPH, ()):
        run = approach_run(lvl, x, y)
        if run > BAND2_CELLS:
            warnings.append('(%d,%d): exit gate is seen down a %d-cell straight approach, past band %d'
                            % (x, y, run, BAND2_CELLS))
    floors = [(x, y) for y, row in enumerate(lvl.rows) for x, ch in enumerate(row)
              if ch not in WALL_CELLS and ch not in NEVER_OPEN_DOORS]
    for x, y in lvl.at.get(EXIT_PLATING, ()):
        if not any(max(abs(fx - x), abs(fy - y)) <= BAND2_CELLS for fx, fy in floors):
            warnings.append('(%d,%d): exit plating has no floor cell inside band %d' % (x, y, BAND2_CELLS))


def summarise(lvl, dist, order, warn_count):
    walls = lvl.count(WALL_CELLS)
    doors = lvl.count(DOOR_CELLS)
    exits = lvl.at.get(EXIT_GLYPH, [])
    path = dist.get(exits[0]) if exits else None
    return {
        'name': lvl.name,
        'size': '%dx%d' % (lvl.width, lvl.height),
        'floor': lvl.width * lvl.height - walls - doors,
        'walls': walls,
        'watchdogs': lvl.count('w'),
        'sentries': lvl.count('s'),
        'tracers': lvl.count('t'),
        'enemies': lvl.count(ENEMY_GLYPHS),
        'pickups': lvl.count(PICKUP_GLYPHS),
        'tokens': lvl.count(TOKEN_GLYPHS),
        'doors': doors,
        'path': '-' if path is None else str(path),
        'warn': warn_count,
        'order': ' '.join('[%s]' % ','.join(TOKEN_NAMES[g] for g in step) for step in order) or '-',
    }


def validate(path):
    lvl, errors = parse_level(path)
    warnings = []
    check_shape(lvl, errors)
    if errors:
        return lvl, errors, warnings, None
    check_header(lvl, errors, warnings)
    check_glyphs(lvl, errors)
    check_border(lvl, errors)
    check_singletons(lvl, errors)
    check_ordinary_doors(lvl, errors)
    check_terminal_doors(lvl, errors)
    check_sentries(lvl, errors)
    dist, order = lock_ordered_reach(lvl)
    check_reachability(lvl, dist, errors)
    check_entities_placed(lvl, dist, errors)
    check_counts(lvl, errors)
    warn_count = check_dead_ends(lvl, dist, warnings)
    check_gate_band(lvl, warnings)
    return lvl, errors, warnings, summarise(lvl, dist, order, warn_count)


COLUMNS = (
    ('file', 'file', 12), ('name', 'name', 12), ('size', 'size', 7),
    ('floor', 'floor', 6), ('walls', 'walls', 6), ('watchdogs', 'W', 3),
    ('sentries', 'S', 3), ('tracers', 'T', 3), ('enemies', 'enemy', 6),
    ('pickups', 'pick', 5), ('tokens', 'tok', 4), ('doors', 'door', 5),
    ('path', 'path', 5), ('warn', 'warn', 5), ('order', 'lock order', 22),
)
TABLE_CAPTION = (
    'floor/walls = cells; W/S/T = Watchdog/Sentry/Tracer; enemy includes anchors and Black ICE;\n'
    'path = shortest start->exit walk once the gates you earn are open (token detours not counted);\n'
    'warn = rule 8 one-cell pockets; lock order = the token order the flood fill proved.')


def format_table(summaries):
    head = '  '.join(title.ljust(w) for _key, title, w in COLUMNS)
    lines = [head, '-' * len(head)]
    for row in summaries:
        lines.append('  '.join(str(row[key]).ljust(w) for key, _title, w in COLUMNS).rstrip())
    lines.append('')
    lines.append(TABLE_CAPTION)
    return lines


def collect(targets):
    files = []
    for target in targets:
        if os.path.isdir(target):
            files += [os.path.join(target, n) for n in sorted(os.listdir(target)) if n.endswith('.txt')]
        else:
            files.append(target)
    return files


def main(argv):
    targets = argv[1:] or [os.path.dirname(os.path.abspath(__file__))]
    files = collect(targets)
    if not files:
        print('no level files found in %s' % ', '.join(targets))
        return 1
    summaries, failed = [], 0
    for path in files:
        lvl, errors, warnings, summary = validate(path)
        label = os.path.basename(path)
        if errors:
            failed += 1
            print('FAIL %s (%s)' % (label, lvl.name))
            for message in errors:
                print('       %s' % message)
        if warnings:
            print('WARN %s (%s)' % (label, lvl.name))
            for message in warnings:
                print('       %s' % message)
        if summary:
            summary['file'] = label
            summaries.append(summary)
    if summaries:
        print()
        for line in format_table(summaries):
            print(line)
    print()
    print('%d level(s) checked, %d passed, %d failed' % (len(files), len(files) - failed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
