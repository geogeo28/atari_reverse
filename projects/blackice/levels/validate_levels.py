#!/usr/bin/env python3
"""BLACK ICE level validator - DESIGN.md v2.

Parses any `levels/*.txt` authored in the v2 legend (SS11) and applies the eight compiler rules
plus the one compiler warning, so a map is proved sound before `tools/mklevel.py` compiles it:

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

SS11's rule 9 - warning on an exit gate first seen beyond band 2 - is WITHDRAWN: it rested on
integrity green fogging out at band 3, and `palette.py`'s BAND_ACCENT_MAP holds index 14 unfogged
in all five bands (SS3), so a gate is green from any distance.  The compiler carries eight rules.

Header fields are range-checked against the SS11 binary field widths and the SS9/SS14 shipped
values, so a unit slip (a v1 per-tick `trace_base_rate`, say) is caught here and not in play.

Usage:  python3 validate_levels.py [level file or directory ...]
Exit status 0 when every level passes; warnings never fail a level.
"""

import os
import pathlib
import re
import sys
from collections import deque

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import mklevel                                                  # noqa: E402

# ---------------------------------------------------------------------------
# The legend and the numeric contract. DESIGN.md v2 SS9/SS11/SS14 own these.
#
# The glyph tables below are DERIVED from tools/mklevel.py's one legend, not
# copied from it: a validator that passes a map the compiler then rejects - or
# worse, passes one the compiler compiles differently - is not a validator.
#
# The RULES are mklevel's too.  Rules 3, 4, 5, 7 and 8 used to be implemented
# twice, once here over glyphs and once (or not at all) there over cell values;
# they now live in the compiler and this file calls them, so the compiler is the
# single authority on what a legal map is.  What stays local is the REPORT:
# names, roles, the header ranges and the summary table.
# ---------------------------------------------------------------------------

MAX_DIM = mklevel.MAP_MAX_DIM    # grid is 64x64 cells maximum
MAX_ENTITIES = mklevel.MAX_ENTITIES     # the entity list is capped at 64 records
BRAD_TURN = mklevel.BRADS_PER_TURN      # 1024 brads = 360 degrees; 0 = north, clockwise
SHIPPED_TRACE_BASE_RATE = 180    # thousandths of a percent per SECOND (SS9.1: 0.18 %/s)
SHIPPED_TRACE_CARRY_CAP = 25     # percent - SS9 makes this the single authority on start value


def _cells_between(low, high):
    """Legend glyphs whose compiled cell value falls in [low, high]."""
    return {glyph: cell for glyph, (cell, _entity, _start) in mklevel.LEGEND.items()
            if low <= cell <= high}


WALL_CELLS = _cells_between(1, mklevel.CELL_WALL_MAX)           # glyph -> wall texture id
DOOR_CELLS = _cells_between(mklevel.CELL_DOOR_BASE, mklevel.CELL_DOOR_MAX)
TERMINAL_DOORS = ('S', '>')                         # rule 4: on the border, one open neighbour

START_GLYPH = '@'
EXIT_GLYPH = '>'
FLOOR_ENTITIES = {               # every entity is a floor entity in v2; the cell compiles to 0
    'w': ('enemy', 'Watchdog'), 't': ('enemy', 'Tracer'), 'B': ('enemy', 'Black ICE'),
    's': ('enemy', 'Sentry'), '*': ('enemy', 'anchor'),
    'p': ('token', 'ALPHA'), 'q': ('token', 'BETA'), 'r': ('token', 'GAMMA'),
    'c': ('pickup', 'cycles small'), 'C': ('pickup', 'cycles large'),
    'i': ('pickup', 'integrity small'), 'I': ('pickup', 'integrity large'),
    'u': ('pickup', 'scrubber'), 'd': ('pickup', 'data cache'),
}
# FLOOR_ENTITIES carries names and roles mklevel has no opinion about, so it
# stays spelled out - but WHICH glyphs place an entity is mklevel's to say, and
# a glyph in one table and not the other is a defect in this file.
assert set(FLOOR_ENTITIES) == {glyph for glyph, (_cell, entity, _start) in mklevel.LEGEND.items()
                               if entity != mklevel.ENT["NONE"]}, \
    "the validator's entity glyphs have drifted from tools/mklevel.py's legend"
assert set(WALL_CELLS) | set(DOOR_CELLS) | set(FLOOR_ENTITIES) | {'.', '@'} \
    == set(mklevel.LEGEND), "the validator does not cover the whole legend"

ENEMY_GLYPHS = ('w', 's', 't', 'B', '*')
TOKEN_GLYPHS = ('p', 'q', 'r')
PICKUP_GLYPHS = ('c', 'C', 'i', 'I', 'u', 'd')
# The lock order mklevel reports is a list of ENTITY TYPES, because that is what
# the compiler sees; these are the names the table prints them under.
TOKEN_NAMES = {mklevel.ENT['TOKEN_ALPHA']: 'ALPHA',
               mklevel.ENT['TOKEN_BETA']: 'BETA',
               mklevel.ENT['TOKEN_GAMMA']: 'GAMMA'}

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

    def on_border(self, x, y):
        return x in (0, self.width - 1) or y in (0, self.height - 1)



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


def compiled(lvl, errors):
    """Compile the map block the way tools/mklevel.py does, so the rules below
    are asked of exactly the cells the compiler would produce."""
    try:
        width, height, cells, entities, start = mklevel.build_grid(lvl.rows)
    except mklevel.LevelError as error:
        errors.append(str(error))
        return None, None, None
    return mklevel.Grid(width, height, cells), entities, start


def check_compiler_rules(grid, entities, start, errors, warnings):
    """DESIGN 11 rules 3, 4, 5 and 7, and warning 8 - all delegated.

    mklevel raises on the FIRST failure rather than collecting them, so this
    reports one rule failure at a time.  That is the trade for having one
    implementation: the message is the compiler's own, and a map this file
    passes is a map the compiler will compile.
    """
    try:
        mklevel.validate_door_jambs(grid)
        mklevel.validate_terminal_doors(grid)
        mklevel.validate_sentry_alcoves(grid, entities)
        mklevel.validate_reachable(grid, entities, start)
    except mklevel.LevelError as error:
        errors.append(str(error))
    pockets = mklevel.warn_dead_ends(grid, entities)
    warnings.extend(pockets)
    return len(pockets)


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
    check_counts(lvl, errors)
    grid, entities, start = compiled(lvl, errors)
    if grid is None:
        return lvl, errors, warnings, None
    warn_count = check_compiler_rules(grid, entities, start, errors, warnings)
    dist, order = mklevel.lock_ordered_reach(grid, entities, start)
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
