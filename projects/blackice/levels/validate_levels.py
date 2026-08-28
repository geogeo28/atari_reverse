#!/usr/bin/env python3
"""BLACK ICE level validator.

Parses any `levels/*.txt` authored in the DESIGN.md legend (SS11) and checks the invariants the
compiler (`tools/mklevel.py`) will also enforce, so a map is proved sound before it is compiled:

  * rectangular map, dimensions within the engine limit and matching the header
  * sealed outer border
  * exactly one player start and exactly one sector exit
  * every door jambed by walls on one axis and open on the other; terminal gates (the sector
    exit and the sealed arch) are exempt on the side that abuts the outer border
  * every Sentry standing on floor in a 1-cell niche - three wall neighbours, one open side
  * no entity stranded inside solid geometry
  * start -> exit reachable under the lock-ordered rule: a token door only opens once its token
    has itself been reached, so the route is provably walkable in a legal order
  * entity totals agree with the header

Usage:  python3 validate_levels.py [level file or directory ...]
Exit status 0 when every level passes, 1 otherwise.
"""

import os
import re
import sys
from collections import deque

# ---------------------------------------------------------------------------
# The legend. DESIGN.md SS11 owns this table; it is transcribed, not invented.
# ---------------------------------------------------------------------------

MAX_DIM = 64                     # grid is 64x64 cells maximum
MAX_ENTITIES = 64                # entity_count is a u16 but the format caps the list at 64
CELL_EMPTY = 0
WALL_CELLS = {                   # glyph -> wall texture id (1..15)
    '#': 1, '=': 2, '%': 3, '|': 4, '^': 5, '?': 6, 'A': 7, 'X': 8,
}
DOOR_CELLS = {                   # glyph -> door variant (16..31)
    '+': 16, '1': 17, '2': 18, '3': 19, 'S': 21, '~': 22, '>': 23,
}
ANCHOR_WALL_CELL = 7             # '*' lowers to wall 7 plus an anchor entity
SENTRY_OPEN_FACES = 1            # a Sentry is a billboard recessed into a 1-cell niche

START_GLYPH = '@'
EXIT_GLYPH = '>'
FLOOR_ENTITIES = {               # glyph -> (kind, human name); these sit on an empty cell
    'w': ('enemy', 'Watchdog'), 't': ('enemy', 'Tracer'), 'B': ('enemy', 'Black ICE'),
    'p': ('token', 'ALPHA'), 'q': ('token', 'BETA'), 'r': ('token', 'GAMMA'),
    'c': ('pickup', 'cycles small'), 'C': ('pickup', 'cycles large'),
    'i': ('pickup', 'integrity small'), 'I': ('pickup', 'integrity large'),
    'u': ('pickup', 'scrubber'), 'd': ('pickup', 'data cache'),
    's': ('enemy', 'Sentry'),    # a billboard on floor, recessed into a niche - not a wall cell
}
WALL_ENTITIES = {                # glyph -> (kind, human name); these ARE a wall cell
    '*': ('enemy', 'anchor'),
}
ENEMY_GLYPHS = ('w', 's', 't', 'B', '*')
TOKEN_GLYPHS = ('p', 'q', 'r')
PICKUP_GLYPHS = ('c', 'C', 'i', 'I', 'u', 'd')

TOKEN_FOR_DOOR = {'1': 'p', '2': 'q', '3': 'r'}     # locked door -> the token that opens it
ALWAYS_OPEN_DOORS = ('+', '>')                      # bump-to-open plain gate, and the exit gate
NEVER_OPEN_DOORS = ('S', '~')                       # sealed arch, and the door frozen at 3/8
TERMINAL_DOORS = ('>', 'S')                         # gates that end (or never begin) a run

PASSABLE_BASE = set(FLOOR_ENTITIES) | {'.', START_GLYPH} | set(ALWAYS_OPEN_DOORS)

HEADER_RE = re.compile(r'^#\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$')
FENCE_RE = re.compile(r'^\s*```')
REPEATABLE_KEYS = ('note',)
INT_KEYS = ('sector', 'width', 'height', 'palette_variant', 'texture_set', 'start_x', 'start_y',
            'start_facing', 'trace_base_rate', 'trace_start', 'trace_carry_cap', 'par_ticks',
            'entity_count', 'watchdogs', 'sentries', 'tracers')
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

    def is_solid(self, x, y):
        """Solid for line-of-sight and for the door-jamb rule: walls and every door variant."""
        ch = self.glyph(x, y)
        return ch in WALL_CELLS or ch in WALL_ENTITIES or ch in DOOR_CELLS


def parse_level(path):
    """Return (Level, [errors]). Header lines are `# key: value`; a map row never matches that."""
    header, rows, errors = {}, [], []
    for lineno, raw in enumerate(open(path, encoding='ascii').read().splitlines(), 1):
        line = raw.rstrip()
        if not line or FENCE_RE.match(line):
            continue
        match = HEADER_RE.match(line)
        if match and not rows:
            key, value = match.group(1), match.group(2)
            if key in REPEATABLE_KEYS:
                header.setdefault(key, []).append(value)
            elif key in header:
                errors.append('line %d: duplicate header key %r' % (lineno, key))
            else:
                header[key] = value
            continue
        if match and rows:
            errors.append('line %d: header key %r appears after the map block' % (lineno, key))
            continue
        rows.append(line)
    for key in INT_KEYS:
        if key in header:
            try:
                header[key] = int(header[key])
            except ValueError:
                errors.append('header %r is not an integer: %r' % (key, header[key]))
    return Level(path, header, rows), errors


def check_shape(lvl, errors):
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
    known = set(WALL_CELLS) | set(DOOR_CELLS) | set(FLOOR_ENTITIES) | set(WALL_ENTITIES) | {'.', START_GLYPH}
    for y, row in enumerate(lvl.rows):
        for x, ch in enumerate(row):
            if ch not in known:
                errors.append('(%d,%d): glyph %r is not in the legend' % (x, y, ch))


def check_border(lvl, errors):
    holes = []
    for x in range(lvl.width):
        for y in (0, lvl.height - 1):
            if lvl.glyph(x, y) not in WALL_CELLS and lvl.glyph(x, y) not in WALL_ENTITIES:
                holes.append((x, y))
    for y in range(lvl.height):
        for x in (0, lvl.width - 1):
            if lvl.glyph(x, y) not in WALL_CELLS and lvl.glyph(x, y) not in WALL_ENTITIES:
                holes.append((x, y))
    for x, y in sorted(set(holes)):
        errors.append('(%d,%d): outer border is not sealed (glyph %r)' % (x, y, lvl.glyph(x, y)))


def check_singletons(lvl, errors):
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


def touches_border(lvl, x, y):
    return any(nx in (0, lvl.width - 1) or ny in (0, lvl.height - 1)
               for nx, ny in ((x + dx, y + dy) for dx, dy in NEIGHBOURS))


def check_doors(lvl, errors):
    """A door is jambed by wall on one axis and slides open across the other.

    Terminal gates - the sector exit and the sealed arch - are exempt from needing an open cell
    on both sides of the sliding axis when they back onto the outer border.
    """
    for glyph in DOOR_CELLS:
        for x, y in lvl.at.get(glyph, ()):
            jambed, sliding = 0, 0
            for (adx, ady), (bdx, bdy) in AXES:
                ax, ay, bx, by = x + adx, y + ady, x + bdx, y + bdy
                if not (lvl.in_bounds(ax, ay) and lvl.in_bounds(bx, by)):
                    continue
                if lvl.is_solid(ax, ay) and lvl.is_solid(bx, by):
                    jambed += 1
                elif not lvl.is_solid(ax, ay) and not lvl.is_solid(bx, by):
                    sliding += 1
            if jambed != 1:
                errors.append('(%d,%d): door %r has %d jambed axes, expected exactly 1' % (x, y, glyph, jambed))
            if sliding != 1 and not (glyph in TERMINAL_DOORS and touches_border(lvl, x, y)):
                errors.append('(%d,%d): door %r has %d open axes, expected two opposite open cells'
                              % (x, y, glyph, sliding))


def open_faces(lvl, x, y):
    faces = []
    for dx, dy in NEIGHBOURS:
        nx, ny = x + dx, y + dy
        if lvl.in_bounds(nx, ny) and not lvl.is_solid(nx, ny):
            faces.append((nx, ny))
    return faces


def check_sentries(lvl, errors):
    """A Sentry is a floor billboard in a 1-cell niche: three wall neighbours, one open side."""
    for x, y in lvl.at.get('s', ()):
        faces = [f for f in open_faces(lvl, x, y) if f != (x, y)]
        if len(faces) != SENTRY_OPEN_FACES:
            errors.append('(%d,%d): Sentry niche has %d open sides, expected exactly %d'
                          % (x, y, len(faces), SENTRY_OPEN_FACES))


def lock_ordered_reach(lvl):
    """BFS from the start, unlocking a token door only once its token has been reached.

    Returns (distance map, set of tokens held). Re-runs the flood each time a new token is
    picked up, which is what proves the route is walkable in a legal order rather than merely
    connected once every door is assumed open.
    """
    start = lvl.at.get(START_GLYPH, [])
    if not start:
        return {}, set()
    held = set()
    dist = {}
    while True:
        passable = set(PASSABLE_BASE) | {d for d, tok in TOKEN_FOR_DOOR.items() if tok in held}
        dist = {start[0]: 0}
        queue = deque(start)
        while queue:
            x, y = queue.popleft()
            if lvl.glyph(x, y) == EXIT_GLYPH:
                continue                            # entering the exit ends the level: walk no further
            for dx, dy in NEIGHBOURS:
                nx, ny = x + dx, y + dy
                if not lvl.in_bounds(nx, ny) or (nx, ny) in dist:
                    continue
                if lvl.glyph(nx, ny) not in passable:
                    continue
                dist[(nx, ny)] = dist[(x, y)] + 1
                queue.append((nx, ny))
        gained = {lvl.glyph(x, y) for (x, y) in dist if lvl.glyph(x, y) in TOKEN_GLYPHS}
        if gained <= held:
            return dist, held
        held |= gained


def check_reachability(lvl, dist, errors):
    exits = lvl.at.get(EXIT_GLYPH, [])
    if exits and exits[0] not in dist:
        errors.append('the sector exit at (%d,%d) is not reachable in a legal token order' % exits[0])
    for glyph in TOKEN_GLYPHS:
        for x, y in lvl.at.get(glyph, ()):
            if (x, y) not in dist:
                errors.append('(%d,%d): token %r is not reachable' % (x, y, glyph))


def check_entities_placed(lvl, dist, errors):
    """Floor entities must stand on reachable open floor; wall entities need a reachable face."""
    for glyph in FLOOR_ENTITIES:
        for x, y in lvl.at.get(glyph, ()):
            if (x, y) not in dist:
                errors.append('(%d,%d): %s %r is walled off from the player' %
                              (x, y, FLOOR_ENTITIES[glyph][1], glyph))
    for glyph in WALL_ENTITIES:
        for x, y in lvl.at.get(glyph, ()):
            faces = open_faces(lvl, x, y)
            if not faces:
                errors.append('(%d,%d): %s %r is entombed - no open face' %
                              (x, y, WALL_ENTITIES[glyph][1], glyph))
            elif not any(face in dist for face in faces):
                errors.append('(%d,%d): %s %r has no reachable face' %
                              (x, y, WALL_ENTITIES[glyph][1], glyph))


def check_counts(lvl, errors):
    total = sum(lvl.count(g) for g in list(FLOOR_ENTITIES) + list(WALL_ENTITIES))
    if total > MAX_ENTITIES:
        errors.append('%d entities exceeds the %d-entity level cap' % (total, MAX_ENTITIES))
    if 'entity_count' in lvl.header and lvl.header['entity_count'] != total:
        errors.append('header entity_count=%s but the map holds %d entities' %
                      (lvl.header['entity_count'], total))
    for key, glyph in ROSTER_KEYS:
        if key in lvl.header and lvl.header[key] != lvl.count(glyph):
            errors.append('header %s=%s but the map holds %d' % (key, lvl.header[key], lvl.count(glyph)))


def exit_path_length(lvl, dist):
    exits = lvl.at.get(EXIT_GLYPH, [])
    return dist.get(exits[0]) if exits else None


def summarise(lvl, dist):
    walls = sum(lvl.count(g) for g in WALL_CELLS) + sum(lvl.count(g) for g in WALL_ENTITIES)
    floor = lvl.width * lvl.height - walls - sum(lvl.count(g) for g in DOOR_CELLS)
    path = exit_path_length(lvl, dist)
    return {
        'name': lvl.name,
        'size': '%dx%d' % (lvl.width, lvl.height),
        'floor': floor,
        'walls': walls,
        'watchdogs': lvl.count('w'),
        'sentries': lvl.count('s'),
        'tracers': lvl.count('t'),
        'enemies': sum(lvl.count(g) for g in ENEMY_GLYPHS),
        'pickups': sum(lvl.count(g) for g in PICKUP_GLYPHS),
        'tokens': sum(lvl.count(g) for g in TOKEN_GLYPHS),
        'doors': sum(lvl.count(g) for g in DOOR_CELLS),
        'path': '-' if path is None else str(path),
    }


def validate(path):
    lvl, errors = parse_level(path)
    check_shape(lvl, errors)
    if errors:
        return lvl, errors, None
    check_glyphs(lvl, errors)
    check_border(lvl, errors)
    check_singletons(lvl, errors)
    check_doors(lvl, errors)
    check_sentries(lvl, errors)
    dist, _held = lock_ordered_reach(lvl)
    check_reachability(lvl, dist, errors)
    check_entities_placed(lvl, dist, errors)
    check_counts(lvl, errors)
    return lvl, errors, summarise(lvl, dist)


COLUMNS = (
    ('file', 'file', 12), ('name', 'name', 13), ('size', 'size', 7),
    ('floor', 'floor', 6), ('walls', 'walls', 6), ('watchdogs', 'W', 3),
    ('sentries', 'S', 3), ('tracers', 'T', 3), ('enemies', 'enemy', 6),
    ('pickups', 'pick', 5), ('tokens', 'tok', 4), ('doors', 'door', 5), ('path', 'path', 5),
)
TABLE_CAPTION = ('floor/walls = cells; W/S/T = Watchdog/Sentry/Tracer; enemy includes anchors and '
                 'Black ICE;\npath = shortest start->exit walk once the gates you earn are open '
                 '(token detours not counted).')


def format_table(summaries):
    head = '  '.join(title.ljust(w) for _key, title, w in COLUMNS)
    lines = [head, '-' * len(head)]
    for row in summaries:
        lines.append('  '.join(str(row[key]).ljust(w) for key, _title, w in COLUMNS))
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
        lvl, errors, summary = validate(path)
        label = os.path.basename(path)
        if errors:
            failed += 1
            print('FAIL %s (%s)' % (label, lvl.name))
            for message in errors:
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
