"""Read/write census of every a4-relative global Bubble Ghost's code touches.

`GHOST.PRG` is Alcyon/DRI C in the small model, so every global is reached as a
displacement off `a4` (= 0x24f1a, the BSS/DATA boundary — `notes/anchors.md`).  This
script sweeps the linear disassembly for those operands, classifies each as a read, a
write, a read-modify-write or an address-taken (`lea`/`pea`), attributes it to the
enclosing function, and proposes an owning subsystem so the recreate knows who holds
each variable.

WHICH ADDRESSING MODES THIS SWEEPS, and therefore what it cannot see:
  * `d16(a4)` and the indexed `d16(a4,Xn)` form.  The image uses only the first: `(a4,`
    occurs zero times in `out/prg_dis.txt` (the code always does `lea -N(a4),a0` and then
    indexes off `a0`), so the indexed branch is pinned by `--self-test`, not by real data.
  * BLIND SPOT 1 — `init_globals`' initialiser stream.  It points a1 at a table with
    `lea -N(a4),a1` and then stores through `(a1)+` (7,797 such stores in its body); only
    the globals it happens to write with a plain `d16(a4)` move show an `init_globals` write,
    30 of the 497 rows.
  * BLIND SPOT 2 — a write through a pointer the caller passed.  `mouse_x` (`0x2311a`) shows
    reads and six `pea` sites and zero writes, because `vq_mouse` stores into it through
    `14(a6)`, not through `a4`.
  * BLIND SPOT 3 — the elements of a table.  An `A` (address-taken) row is a TABLE BASE, and
    the elements above it are reached through the scratch register, not through `a4`.  A row
    with `lea` sites and no reads/writes is normal, not a dead global.

The `reads` and `writes` columns count a read-modify-write site in BOTH (`rmw` counts it once).

Run from the repository root:  python3 projects/bubbleghost/tools/globals_census.py
                              python3 projects/bubbleghost/tools/globals_census.py --self-test
"""
import bisect
import collections
import re
import sys

DIS = 'projects/bubbleghost/out/prg_dis.txt'
DECOMP = 'projects/bubbleghost/decomp.c'
NAMES = 'projects/bubbleghost/names.txt'
TSV = 'projects/bubbleghost/out/globals.tsv'
SUMMARY = 'projects/bubbleghost/out/globals_summary.md'

A4 = 0x24f1a                        # small-model data pointer = BSS/DATA boundary
INIT_GLOBALS = 0x16d8e              # the one function whose writes the ownership vote discounts
BSS_LO, BSS_HI = 0x1e8ca, 0x24f1a   # zeroed by the crt0, written by init_globals
DATA_LO, DATA_HI = 0x24f1a, 0x2520e  # the strings, moved above BSS by the crt0

# Subsystem per function: names.txt's own `# ==== <section> ====` headings are the source of
# truth (a `fn` line belongs to the section it sits under), so the census and the name map can
# never disagree.  The address bands below are only a fallback for the handful of functions
# names.txt has no `fn` line for.
SECTION_OWNERS = (('entry', 'init'), ('front end', 'frontend'), ('file i/o', 'frontend'),
                  ('gameplay', 'gameplay'), ('blitters', 'blitters'), ('hud', 'gameplay'),
                  ('sound', 'sound'), ('c library', 'clib'))
RANGE_OWNERS = ((0x10000, 0x101e6, 'init'),      # _start, crt0, main, video+heap init
                (0x101e6, 0x10dea, 'gameplay'),  # game_top_loop: the level/play driver
                (0x10dea, 0x129b4, 'frontend'),  # loaders, presentation, attract, scores, keys
                (0x129b4, 0x142bc, 'gameplay'),  # collision, object update, drawing
                (0x142bc, 0x149b6, 'sound'),     # the PSG engine (notes/sound_engine.md)
                (0x149b6, 0x16d8e, 'clib'),      # AES stub + the Alcyon/DRI C runtime
                (0x16d8e, BSS_LO, 'init'))       # init_globals, up to the end of TEXT

LINE_RE = re.compile(r'^([0-9a-f]{6}): [0-9a-f ]+?\s\s+(\S+)\s*(.*?)\s*$')
FN_RE = re.compile(r'^//\s+([0-9a-f]{8})\s+(\S+)\s+(\d+) bytes$')
SECTION_RE = re.compile(r'^#\s*=+\s*(.*?)\s*=+\s*$')
FN_LINE_RE = re.compile(r'^fn 0x([0-9a-fA-F]+)\s')
A4_RE = re.compile(r'(-?\d+)\(a4(?:\)|,[ad]\d)')  # d16(a4) and the indexed d16(a4,Xn)
OPERAND_RE = re.compile(r',(?![^()]*\))')         # top-level commas: keeps d16(a4,Xn) in one part
WIDTHS = {'b': 1, 'w': 2, 'l': 4}


def read_functions():
    """(start, end, name) for every function, from decomp.c's header listing."""
    out = []
    for raw in open(DECOMP):
        m = FN_RE.match(raw.rstrip('\n'))
        if m:
            start, size = int(m.group(1), 16), int(m.group(3))
            out.append((start, start + size, m.group(2)))
    return sorted(out)


def read_var_names():
    return {int(m.group(1), 16): m.group(2)
            for m in (re.match(r'^var 0x([0-9a-fA-F]+)\s+(\S+)', raw) for raw in open(NAMES))
            if m}


def section_owner(heading):
    """Owner key for a names.txt section heading, or None for the non-code sections."""
    lowered = heading.lower()
    for key, owner in SECTION_OWNERS:
        if key in lowered:
            return owner
    return None


def read_fn_owners():
    """function start address -> owner, from the names.txt section each `fn` line sits under."""
    owners, owner = {}, None
    for raw in open(NAMES):
        heading = SECTION_RE.match(raw.rstrip('\n'))
        if heading:
            owner = section_owner(heading.group(1))
            continue
        m = FN_LINE_RE.match(raw)
        if m and owner:
            owners[int(m.group(1), 16)] = owner
    return owners


def owner_of(start, fn_owners):
    if start in fn_owners:
        return fn_owners[start]
    for lo, hi, owner in RANGE_OWNERS:
        if lo <= start < hi:
            return owner
    return 'unattributed'


def classify(mnemonic, part_index, part_count):
    """Read / Write / read-modify-write / Address-taken, from the opcode and operand slot."""
    base = mnemonic.split('.')[0]
    if base in ('lea', 'pea'):
        return 'A'
    if part_count == 1:
        if base in ('clr', 'st', 'sf'):
            return 'W'
        if base in ('jmp', 'jsr'):
            return 'A'                   # the EA is a destination; nothing at it is read
        if base == 'tst':
            return 'R'
        return 'RW'                      # neg, not, ext, asl/lsr on memory, ...
    if base in ('cmp', 'cmpi', 'cmpa', 'cmpm', 'btst'):
        return 'R'
    if base in ('bset', 'bclr', 'bchg'):
        return 'RW'
    if base in ('addi', 'subi', 'andi', 'ori', 'eori', 'addq', 'subq'):
        return 'RW' if part_index else 'R'
    if base in ('move', 'movea', 'movem'):
        return 'R' if part_index == 0 else 'W'
    return 'R' if part_index == 0 else 'RW'   # add/sub/and/or/eor into memory


def a4_sites(mnemonic, operands):
    """[(a4 displacement, kind)] for every a4-relative effective address in one instruction."""
    parts = [p.strip() for p in OPERAND_RE.split(operands)]
    return [(int(am.group(1)), classify(mnemonic, index, len(parts)))
            for index, part in enumerate(parts) for am in A4_RE.finditer(part)]


def sweep(functions):
    """address -> {'sites': [(pc, kind, function)], 'widths': set of access widths}."""
    starts = [f[0] for f in functions]
    refs = collections.defaultdict(lambda: {'sites': [], 'widths': set()})
    for raw in open(DIS):
        m = LINE_RE.match(raw.rstrip('\n'))
        if not m:
            continue
        pc, mnemonic = int(m.group(1), 16), m.group(2)
        i = bisect.bisect_right(starts, pc) - 1
        fn = functions[i][2] if i >= 0 and pc < functions[i][1] else 'unattributed'
        for displacement, kind in a4_sites(mnemonic, m.group(3).split('<RELOC')[0]):
            entry = refs[A4 + displacement]
            entry['sites'].append((pc, kind, fn))
            entry['widths'].add(WIDTHS.get(mnemonic.rpartition('.')[2], 0))
    return refs


def region(addr):
    if BSS_LO <= addr < BSS_HI:
        return 'bss'
    return 'data' if DATA_LO <= addr < DATA_HI else 'outside'


def main():
    functions = read_functions()
    fn_owners = read_fn_owners()
    owners = {name: owner_of(start, fn_owners) for start, _, name in functions}
    owners['unattributed'] = 'unattributed'
    names = read_var_names()
    refs = sweep(functions)
    initialiser = next(name for start, _, name in functions if start == INIT_GLOBALS)

    rows = []
    for addr in sorted(refs):
        sites = refs[addr]['sites']
        kinds = [k for _, k, _ in sites]
        # The `init_globals` FUNCTION never counts as a co-owner: it initialises globals right
        # across the map, so counting it would make almost every row SHARED.  The discount is
        # safe in the other direction too — most of what it writes goes through `(a1)+` and is
        # invisible here anyway (BLIND SPOT 1 in the module docstring).  It is scoped to that
        # one function, not to the `init` subsystem: `game_top_loop` is filed under entry/crt0
        # in names.txt, and the play driver's writes are real writes.
        writers = sorted({owners[fn] for _, k, fn in sites if 'W' in k and fn != initialiser})
        touchers = sorted({owners[fn] for _, _, fn in sites if fn != initialiser}) or \
            sorted({owners[fn] for _, _, fn in sites})
        # Owner: whoever WRITES it; a global nobody writes is owned by its readers.  Two writing
        # subsystems is not an owner but a finding, so the column says SHARED and `writers` lists
        # them.  Both columns discount `init` exactly as the per-owner buckets do.
        owner_list = writers or touchers
        shared = len(writers) > 1
        rows.append({
            'addr': addr, 'name': names.get(addr, ''), 'region': region(addr),
            'size': max(refs[addr]['widths']) or '-',
            'reads': sum(1 for k in kinds if 'R' in k),
            'writes': sum(1 for k in kinds if 'W' in k),
            'rmw': kinds.count('RW'), 'lea': kinds.count('A'),
            'fns': sorted({fn for _, _, fn in sites}),
            'owner': 'SHARED' if shared else '+'.join(owner_list),
            'writers': '+'.join(writers) or '-', 'shared': shared,
            'bucket': '+'.join(owner_list),
        })

    with open(TSV, 'w') as f:
        # reads/writes count an RMW site in both; rmw counts it once.  owner is the single
        # owning subsystem, SHARED (2+ writing subsystems), or — for a global NOBODY writes —
        # its readers joined with '+'.  writers lists the writing subsystems (init discounted).
        f.write('addr\tregion\tname\tsize\treads\twrites\trmw\tlea\towner\twriters\tfunctions\n')
        for r in rows:
            f.write('0x%05x\t%s\t%s\t%s\t%d\t%d\t%d\t%d\t%s\t%s\t%s\n' % (
                r['addr'], r['region'], r['name'] or '-', r['size'], r['reads'], r['writes'],
                r['rmw'], r['lea'], r['owner'], r['writers'], ' '.join(r['fns'])))

    per_owner = collections.Counter(r['bucket'] for r in rows if not r['shared'])
    shared = sorted((r for r in rows if r['shared']),
                    key=lambda r: (-r['writes'], -r['reads'], r['addr']))
    total_sites = sum(len(refs[r['addr']]['sites']) for r in rows)
    with open(SUMMARY, 'w') as f:
        f.write('# Bubble Ghost — globals census\n\n')
        f.write('Generated by `tools/globals_census.py`, from `d16(a4)` operands. Three blind '
                'spots, all documented in the script\'s docstring: (a) `init_globals` writes '
                'most of its initialisers through `lea -N(a4),a1` + `move.w #imm,(a1)+`, a '
                'stream this sweep cannot see; (b) a write through a pointer the caller passed '
                'is invisible (`mouse_x` has reads and `pea` sites and zero writes — `vq_mouse` '
                'stores into it through `14(a6)`); (c) a table reached through `lea -N(a4),a0` '
                'shows up as its base, and its elements not at all.\n\n')
        f.write('%d distinct `n(a4)` globals, over %d operand sites.\n' % (len(rows), total_sites))
        f.write('BSS %d, DATA %d, outside the segments %d.\n\n' % (
            sum(r['region'] == 'bss' for r in rows), sum(r['region'] == 'data' for r in rows),
            sum(r['region'] == 'outside' for r in rows)))
        f.write('Each function\'s subsystem is the `# ==== section ====` its `fn` line sits '
                'under in `names.txt`. Owner = the subsystem that WRITES the global (a global '
                'nobody writes is attributed to its readers); the `init_globals` FUNCTION is '
                'discounted, because it initialises globals right across the map and would '
                'otherwise make almost every row SHARED — the discount is scoped to that one '
                'function, not to the `init` subsystem, so `game_top_loop` (filed under '
                'entry/crt0 in `names.txt`) still owns what it writes. Two writing subsystems '
                'is not an owner but a finding: '
                'the `owner` column says SHARED and `writers` names them. A compound owner like '
                '`frontend+gameplay` is the other case — a global nobody writes, read by both. '
                '`reads`/`writes` count a read-modify-write site in both columns.\n\n')
        f.write('| owner | globals |\n|---|---:|\n')
        for owner, count in sorted(per_owner.items(), key=lambda kv: (-kv[1], kv[0])):
            f.write('| %s | %d |\n' % (owner, count))
        f.write('| **SHARED (written by 2+ subsystems, `init_globals` excluded)** | **%d** |\n\n'
                % len(shared))
        f.write('## Top shared globals\n\n')
        f.write('| addr | name | size | R | W | writing subsystems | functions |\n')
        f.write('|---|---|---:|---:|---:|---|---|\n')
        for r in shared[:30]:
            f.write('| `0x%05x` | %s | %s | %d | %d | %s | %s |\n' % (
                r['addr'], r['name'] or '-', r['size'], r['reads'], r['writes'], r['writers'],
                ' '.join(r['fns'][:6])))
    print('globals: %d  sites: %d  shared: %d' % (len(rows), total_sites, len(shared)))
    print('wrote %s and %s' % (TSV, SUMMARY))


SELF_TEST = (('clr.w 4(a4,d0.w)', [(4, 'W')]),
             ('move.w d1,4(a4,d0.w)', [(4, 'W')]),
             ('move.w 4(a4,d0.w),d1', [(4, 'R')]),
             ('clr.w -8028(a4)', [(-8028, 'W')]),
             ('jsr 100(a4)', [(100, 'A')]))


def self_test():
    """Pin the operand split and the classifier on forms this image happens not to contain."""
    for text, expected in SELF_TEST:
        mnemonic, _, operands = text.partition(' ')
        got = a4_sites(mnemonic, operands)
        assert got == expected, '%s -> %s, expected %s' % (text, got, expected)
    print('self-test: %d operand forms OK' % len(SELF_TEST))


if __name__ == '__main__':
    if '--self-test' in sys.argv:
        self_test()
    else:
        main()
