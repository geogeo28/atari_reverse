"""Read/write census of every absolute-long address the Zynaps linear sweep touches.

Classifies each `$xxxxx.l` operand as a read, a write, a read-modify-write or an
address-taken (`lea`), so a global with readers and no writer -- or a writer and no
reader -- falls out. Run from the repository root.
"""
import re, collections

DIS = 'projects/zynaps/out/prg_dis.txt'
NAMES = 'projects/zynaps/names.txt'
OUT = 'projects/zynaps/out/secrets/globals_rw_census.tsv'

# The image's bss/data window: below this is the vector page and code, above is the
# unpacked-asset arena the loader fills.
BSS_LO, BSS_HI = 0x17000, 0x70000

line_re = re.compile(r'^([0-9a-f]{6}):\s+([0-9a-f]+)\s+(\S+)\s*(.*?)\s*$')

refs = collections.defaultdict(list)

for raw in open(DIS):
    m = line_re.match(raw.rstrip('\n'))
    if not m:
        continue
    pc, mnem, ops = m.group(1), m.group(3), m.group(4)
    ops = ops.split('<RELOC')[0].strip()
    for am in re.finditer(r'\$([0-9a-f]{4,6})\.l', ops):
        addr = int(am.group(1), 16)
        parts = [p.strip() for p in ops.split(',')]
        idx = next((i for i, p in enumerate(parts) if am.group(0) in p), None)
        base = mnem.split('.')[0]
        if len(parts) == 1:
            if base in ('tst', 'jmp', 'jsr', 'pea', 'lea'):
                kind = 'R'
            elif base in ('clr', 'st', 'sf'):
                kind = 'W'
            else:
                kind = 'RW'
        elif len(parts) == 2:
            if base == 'lea':
                kind = 'A'
            elif base == 'movem':
                kind = 'R' if idx == 0 else 'W'
            elif base in ('cmp', 'cmpi', 'cmpa', 'btst'):
                kind = 'R'
            elif base in ('bset', 'bclr', 'bchg'):
                kind = 'RW'
            elif base in ('addi', 'subi', 'andi', 'ori', 'eori', 'addq', 'subq'):
                kind = 'RW' if idx == 1 else 'R'
            elif base in ('move', 'movea'):
                kind = 'R' if idx == 0 else 'W'
            else:
                kind = 'R' if idx == 0 else 'RW'
        else:
            kind = '?'
        refs[addr].append((pc, kind))

names = {}
for raw in open(NAMES):
    m = re.match(r'^var 0x([0-9a-fA-F]+)\s+(\S+)', raw)
    if m:
        names[int(m.group(1), 16)] = m.group(2)

rows = []
for addr in sorted(refs):
    kinds = [k for _, k in refs[addr]]
    rows.append((addr, names.get(addr, ''),
                 len(kinds),
                 sum(1 for k in kinds if 'R' in k),
                 sum(1 for k in kinds if 'W' in k),
                 sum(1 for k in kinds if k == 'A')))

with open(OUT, 'w') as f:
    f.write('addr\tname\ttotal\treads\twrites\tlea\tsites\n')
    for addr, nm, total, nr, nw, na in rows:
        sites = ' '.join('%s:%s' % (pc, k) for pc, k in refs[addr])
        f.write('0x%05x\t%s\t%d\t%d\t%d\t%d\t%s\n' % (addr, nm, total, nr, nw, na, sites))

print('distinct absolute-long addresses referenced:', len(refs))
print('\n=== READ, never written, never lea\'d (bss window) ===')
for addr, nm, _, nr, nw, na in rows:
    if nr and not nw and not na and BSS_LO <= addr < BSS_HI:
        print('0x%05x %-38s reads=%-3d %s' % (addr, nm or '-', nr,
                                              ' '.join(pc for pc, _ in refs[addr])))
print('\n=== WRITTEN, never read, never lea\'d (bss window) ===')
for addr, nm, _, nr, nw, na in rows:
    if nw and not nr and not na and BSS_LO <= addr < BSS_HI:
        print('0x%05x %-38s writes=%-3d %s' % (addr, nm or '-', nw,
                                               ' '.join(pc for pc, _ in refs[addr])))
