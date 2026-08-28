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
import struct
import sys

MAGIC = b"BIL0"
HEADER_BYTES = 38
ENTITY_BYTES = 5
NAME_LEN = 16
MAP_MAX_DIM = 64
MAX_ENTITIES = 64
CELL_RESERVED_BASE = 32
BRADS_PER_TURN = 1024

CELL_EMPTY = 0
CELL_WALL_MAX = 15
CELL_DOOR_BASE = 16

# EntityType, mirroring include/level.h.
ENT = {
    "NONE": 0, "WATCHDOG": 1, "SENTRY": 2, "TRACER": 3, "BLACK_ICE": 4,
    "ANCHOR": 5, "TOKEN_ALPHA": 6, "TOKEN_BETA": 7, "TOKEN_GAMMA": 8,
    "CYCLES_SMALL": 9, "CYCLES_LARGE": 10, "INTEGRITY_SMALL": 11,
    "INTEGRITY_LARGE": 12, "SCRUBBER": 13, "DATA_CACHE": 14,
}

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
    "*": (7, ENT["ANCHOR"], False),
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
    "par": 3000,
    "trace_base_rate": 400,
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
DERIVED_KEYS = ("width", "height", "start_x", "start_y")


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
            key, _, value = line[2:].partition(":")
            key = HEADER_ALIASES.get(key.strip(), key.strip())
            if key in header or key in DERIVED_KEYS:
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
    """The DDA has no bounds test in its inner loop; a sealed wall border is
    what makes that safe, so an unsealed map is a hard error."""
    def is_wall(x, y):
        value = cells[y * width + x]
        return 1 <= value <= CELL_WALL_MAX

    for x in range(width):
        if not is_wall(x, 0) or not is_wall(x, height - 1):
            raise LevelError("border is not sealed at column %d" % x)
    for y in range(height):
        if not is_wall(0, y) or not is_wall(width - 1, y):
            raise LevelError("border is not sealed at row %d" % y)


def validate_reachable(width, height, cells, start):
    """A flood fill from the start, treating every door as passable, proving the
    sector exit can be walked to at all.  DESIGN 11 also asks for a
    lock-ordered fill that respects token order; that is not implemented here
    and the exit check is the weaker claim."""
    def passable(value):
        return value == CELL_EMPTY or value >= CELL_DOOR_BASE

    seen = bytearray(width * height)
    stack = [start]
    seen[start[1] * width + start[0]] = 1
    reached_exit = False
    while stack:
        x, y = stack.pop()
        value = cells[y * width + x]
        if value == LEGEND[">"][0]:
            reached_exit = True
            continue                    # an exit gate is where the walk stops
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            index = ny * width + nx
            if seen[index] or not passable(cells[index]):
                continue
            seen[index] = 1
            stack.append((nx, ny))
    if not reached_exit:
        raise LevelError("no walkable route from '@' to a '>' sector exit")


def header_int(header, key, limit):
    value = int(str(header[key]).strip() or 0)
    if not 0 <= value <= limit:
        raise LevelError("header %s = %d is out of range 0..%d" % (key, value, limit))
    return value


def validate_derived_header(header, width, height, start):
    stated = {"width": width, "height": height, "start_x": start[0], "start_y": start[1]}
    for key, actual in stated.items():
        if key in header and int(str(header[key]).strip()) != actual:
            raise LevelError("header %s = %s but the map says %d" % (key, header[key], actual))


def compile_level(text):
    header, rows = parse_source(text)
    width, height, cells, entities, start = build_grid(rows)
    validate_derived_header(header, width, height, start)
    validate_border(width, height, cells)
    validate_reachable(width, height, cells, start)

    name = str(header["name"]).encode("ascii", "replace")[:NAME_LEN]
    blob = bytearray()
    blob += MAGIC
    blob += name.ljust(NAME_LEN, b"\0")
    blob += struct.pack(
        ">BBBBBBBBHHBBHH",
        width, height,
        header_int(header, "sector", 7),
        header_int(header, "palette", 3),
        header_int(header, "texture_set", 2),
        0,                                          # pad
        start[0], start[1],
        header_int(header, "facing", BRADS_PER_TURN - 1),
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
    try:
        blob = compile_level(text)
    except LevelError as error:
        sys.stderr.write("%s: %s\n" % (args.source, error))
        return 1
    with open(args.output, "wb") as handle:
        handle.write(blob)
    return 0


if __name__ == "__main__":
    sys.exit(main())
