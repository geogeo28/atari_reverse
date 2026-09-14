#!/usr/bin/env python3
"""Emit Ghidra function seeds for every TOS 1.02 dispatch-table target.

A TOS ROM reaches nearly all of its code through tables, not through calls: six trap /
exception dispatchers index a table of handler addresses, and GEM additionally calls its
own routines with one-word Line-F opcodes indexed into a 658-entry table.  Ghidra's flow
follower never sees any of it, so without seeding, `decomp.c` holds the boot chain and
little else.

The output is a name map in the `tools/ghidra_scripts/ApplyNames` format whose every line
carries Ghidra's OWN default name (`FUN_00xxxxxx`), because an `fn` line creates the
function by itself (docs/ghidra-pipeline.md, "Gotchas") and a seed must not put a name in
the DB that `names.txt` does not have.  Run it ahead of auto-analysis; `names.txt` is
applied after it and renames the entries it has evidence for.

Every table address below was read out of the dispatcher that indexes it -- the citation
is on the constant -- and they are specific to TOS 1.02 US, so the image is checked
before anything is emitted.

Usage: gen_seeds.py <rom.img> [-o out.txt]
"""
import argparse
import struct
import sys

ROM_BASE = 0xFC0000
ROM_SIZE = 0x30000                  # 192 KB; 0xFC0000..0xFEFFFF
OS_VERSION = 0x0102                 # OS header +0x02
OS_VERSION_OFFSET = 0x02

# --- dispatch tables -----------------------------------------------------------------
# Each entry: (label, table address, entry count, stride, offset of the first entry).
# BIOS/XBIOS share one dispatcher at 0xfc07fc, which reads the entry COUNT from the first
# word of the table and then indexes longwords, hence the offset of 2.  A negative entry
# there is a pointer to a system-variable vector, not a routine -- see INDIRECT_BIT.
TABLES = [
    # 0xfc07f8 `lea 0xfc0846,a0` (BIOS)  /  0xfc07f2 `lea 0xfc0878,a0` (XBIOS)
    ("BIOS   trap #13", 0xFC0846, 12, 4, 2),
    ("XBIOS  trap #14", 0xFC0878, 65, 4, 2),
    # 0xfc9742 `muls #6,d0 / add.l #0xfd307a,d0` -- 6-byte records: handler + arg flags
    ("GEMDOS trap #1", 0xFD307A, 88, 6, 0),
    # 0xfcab2e / 0xfcab52 in the VDI dispatcher: opcodes 1..39 and 100..131
    ("VDI    1..39", 0xFD372C, 39, 4, 0),
    ("VDI    100..131", 0xFD37C8, 32, 4, 0),
    # 0xfe64c8 `add.l #0xfef834,a0` after `sub #10,d0 / cmp #115,d0` -- opcodes 10..125
    ("AES    10..125", 0xFEF834, 116, 4, 0),
    # 0xfc9f24 `movea.l 0xfc9f4a(pc,d2.w),a1` after `cmp #15,d2`
    ("Line-A $a000..$a00f", 0xFC9F4A, 16, 4, 0),
    # 0xfee8d6 `movea.l #0xfee900,a0 / movea.l (a0,d1.w),a0` in the Line-F handler
    ("Line-F $f000..$fa44", 0xFEE900, 658, 4, 0),
]

INDIRECT_BIT = 0x80000000           # BIOS table: entry is a pointer to a RAM vector

# Word-offset jump tables: `jmp <table>(pc,d0.w)` over SIGNED 16-bit displacements from the
# table base.  Entry count = the bound of the `cmp.w #n,d0` just above the jump.
WORD_TABLES = [
    # 0xfc428c `cmp #19,d0` / 0xfc4294 `jmp 0xfc4298(pc,d0.w)` -- VDI escape (opcode 5) sub-functions
    ("VDI escape sub-opcodes", 0xFC4298, 20),
    # 0xfc46a2 `cmp #7,d0` / 0xfc46ae `jmp 0xfc46b2(pc,d0.w)` -- XBIOS 21 Cursconf sub-functions
    ("Cursconf sub-opcodes", 0xFC46B2, 8),
]

# The boot chain returns through a6 rather than by `bsr`: `lea ret(pc),a6 / bra.w sub`, with the
# subroutine ending `jmp (a6)`.  Ghidra follows the branch and never comes back, so `ret` is
# code no flow follower reaches.  Found by signature rather than listed: the `lea d(pc),a6`
# word, a small positive displacement, and a `bra.w`/`jmp` immediately after it.
LEA_PC_A6 = 0x4DFA                  # lea d16(pc),a6
BRANCH_AFTER = (0x6000, 0x4EF9, 0x4EFA)     # bra.w / jmp abs.l / jmp d16(pc)
MAX_RETURN_DISP = 0x40              # the return address is always a few bytes ahead

# Handlers the boot code installs into the 68000 vector table, and the two entries the
# GEM trap dispatcher reaches directly.  Address = the instruction that installs it.
VECTOR_HANDLERS = [
    ("os_reset", 0xFC0030),         # OS header +0x04
    ("bus/address/illegal... trap", 0xFC0B50),   # 0xfc0334 fills $08..$fc with it
    ("divide by zero / unused", 0xFC07CE),       # 0xfc0340, 0xfc034c
    ("HBL level 2", 0xFC06C8),      # 0xfc035e `move.l #0xfc06c8,$68`
    ("VBL level 4", 0xFC06DE),      # 0xfc0356 `move.l #0xfc06de,$70`
    ("Line-A $28", 0xFC9F0C),       # 0xfc037a `move.l #0xfc9f0c,$28`
    ("trap #1 GEMDOS $84", 0xFC4F6E),            # 0xfc4e5e
    ("trap #2 GEM $88 (boot)", 0xFC4EBC),        # 0xfc4e72
    ("trap #2 GEM $88 (AES)", 0xFE3EA6),         # 0xfe3c78
    ("trap #13 BIOS $b4", 0xFC07F8),             # 0xfc036a
    ("trap #14 XBIOS $b8", 0xFC07F2),            # 0xfc0372
    ("etv_timer $400 / etv_term $408", 0xFC0670),   # 0xfc0382, 0xfc038e
    ("etv_critic $404", 0xFC07EE),  # 0xfc0386
    ("VDI entry", 0xFC9F9E),        # 0xfc4ec6 `jsr 0xfc9f9e` on d0 == 0x73
    ("VDI dispatcher", 0xFCA9F6),   # 0xfc9fe0
    ("AES entry", 0xFE65AA),        # 0xfe3f00
    ("AES dispatcher", 0xFE5D9C),   # Line-F $f2b0
    ("GEMDOS dispatcher", 0xFC94E4),             # 0xfc4fe0
    ("Line-F handler (ROM copy)", 0xFEE8C2),     # 0xfd9f4a, copied to RAM at AES init
    ("GEM entry (MUPB +8)", 0xFD9ECA),           # os_magic block at 0xfefff4
]


def read_rom(path):
    with open(path, "rb") as handle:
        rom = handle.read()
    if len(rom) != ROM_SIZE:
        sys.exit(f"{path}: {len(rom)} bytes, expected {ROM_SIZE} (a 192 KB ST TOS image)")
    version = struct.unpack_from(">H", rom, OS_VERSION_OFFSET)[0]
    if version != OS_VERSION:
        sys.exit(f"{path}: OS version 0x{version:04x}, expected 0x{OS_VERSION:04x} "
                 "(the table addresses in this script are TOS 1.02-specific)")
    return rom


def longword(rom, addr):
    return struct.unpack_from(">I", rom, addr - ROM_BASE)[0]


def word(rom, addr):
    return struct.unpack_from(">H", rom, addr - ROM_BASE)[0]


def signed_word(rom, addr):
    return struct.unpack_from(">h", rom, addr - ROM_BASE)[0]


def pc_return_addresses(rom):
    """Return addresses of the boot chain's `lea ret(pc),a6 / bra.w sub` calls."""
    found = []
    for addr in range(ROM_BASE, ROM_BASE + ROM_SIZE - 8, 2):
        if word(rom, addr) != LEA_PC_A6 or word(rom, addr + 4) not in BRANCH_AFTER:
            continue
        disp = signed_word(rom, addr + 2)
        if 0 < disp < MAX_RETURN_DISP and disp % 2 == 0:
            found.append(addr + 2 + disp)
    return found


def targets(rom):
    """Every distinct routine address any dispatch table points at, in address order."""
    found = set()
    for label, addr, count, stride, offset in TABLES:
        for i in range(count):
            value = longword(rom, addr + offset + stride * i)
            if value & INDIRECT_BIT:            # a RAM vector, not a ROM routine
                continue
            if ROM_BASE <= value < ROM_BASE + ROM_SIZE:
                found.add(value)
            else:
                print(f"warning: {label} entry {i} = 0x{value:08x} is outside the ROM",
                      file=sys.stderr)
    for label, base, count in WORD_TABLES:
        for i in range(count):
            value = base + signed_word(rom, base + 2 * i)
            if ROM_BASE <= value < ROM_BASE + ROM_SIZE and value % 2 == 0:
                found.add(value)
            else:
                print(f"warning: {label} entry {i} resolves to 0x{value:08x}", file=sys.stderr)
    for _name, addr in VECTOR_HANDLERS:
        found.add(addr)
    found.update(pc_return_addresses(rom))
    return sorted(found)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rom")
    parser.add_argument("-o", "--out", default="-")
    args = parser.parse_args()

    rom = read_rom(args.rom)
    entries = targets(rom)
    out = sys.stdout if args.out == "-" else open(args.out, "w")
    with out:
        out.write("# Generated by gen_seeds.py -- do not edit; regenerate from the ROM.\n")
        out.write("# One function seed per distinct dispatch-table target, under Ghidra's\n")
        out.write("# own default name, so the DB carries no name names.txt does not.\n")
        for addr in entries:
            out.write(f"fn 0x{addr:06x} FUN_{addr:08x}\n")
    print(f"{len(entries)} seeds", file=sys.stderr)


if __name__ == "__main__":
    main()
