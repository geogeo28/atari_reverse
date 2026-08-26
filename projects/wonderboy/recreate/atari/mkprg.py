#!/usr/bin/env python3
"""Wrap a base-0 linked m68k ELF into a GEMDOS .PRG.

Emits the 28-byte header, the flat text+data image (objcopy -O binary output), and a GEMDOS
relocation table built from the ELF's R_68K_32 fixups (kept via `ld --emit-relocs`). Because the
program is linked at base 0, each fixup's virtual address equals its byte offset in the flat
binary, and the 32-bit value already stored there is the target's base-0 address — exactly what
GEMDOS expects to add the load base to.

Usage: mkprg.py demo.elf demo.bin out.prg

COPIED FROM projects/joust/recreate/atari/mkprg.py, which is itself copied from the BuggyBoy build.
The copies were identical BELOW THIS PARAGRAPH and are now ONE ADDITION apart: `nm_rows`, the single
parse of `m68k-elf-nm`'s output that `sym_value` and atari/profile.py share. It belongs in the other
copies too — it is behaviour-neutral there, `sym_value` being the only caller — and every other
change to any of them still belongs in all of them. Copied
rather than moved into `tools/recreate_kit/` because that move is a kit change touching two other
projects; it is registered as a kit candidate in ../STATUS.md's batch 43 phase A queue and in
Joust's own README.
"""
import re
import struct
import subprocess
import sys

READELF = "m68k-elf-readelf"
NM = "m68k-elf-nm"


def bss_size(elf):
    out = subprocess.check_output([READELF, "-S", "-W", elf], text=True)
    for line in out.splitlines():
        m = re.search(r"\.bss\s+\w+\s+[0-9a-f]+\s+[0-9a-f]+\s+([0-9a-f]+)", line)
        if m:
            return int(m.group(1), 16)
    return 0


def nm_rows(elf):
    """Every `nm` row as (value, type letter, name) — THE ONE PARSE of that output.

    A row with no value (`U some_undefined_symbol`) has two fields and names nothing that can be
    placed at an address, so it is dropped here rather than at each caller. `sym_value` below takes
    one row out of this; atari/profile.py builds a whole Hatari symbol table out of it."""
    listing = subprocess.check_output([NM, str(elf)], text=True)
    rows = (line.split() for line in listing.splitlines())
    return [(int(fields[0], 16), fields[1], fields[2]) for fields in rows if len(fields) == 3]


def sym_value(elf, name):
    """Value of a symbol (e.g. _bss_start) from nm, or None."""
    return next((value for value, _, symbol in nm_rows(elf) if symbol == name), None)


def abs_fixups(elf):
    """Sorted byte offsets of every R_68K_32 fixup (absolute 32-bit address to relocate)."""
    out = subprocess.check_output([READELF, "-r", "-W", elf], text=True)
    offs = set()
    for line in out.splitlines():
        m = re.match(r"\s*([0-9a-fA-F]{8})\s+[0-9a-fA-F]{8}\s+(\S+)", line)
        if m and m.group(2) == "R_68K_32":
            offs.add(int(m.group(1), 16))
    return sorted(offs)


def reloc_table(fixups):
    """GEMDOS relocation table: first fixup as a longword, then byte deltas (0x01 = +254 span,
    0x00 = end). All offsets are even. Empty table is a single zero longword."""
    if not fixups:
        return struct.pack(">I", 0)
    out = bytearray(struct.pack(">I", fixups[0]))
    prev = fixups[0]
    for f in fixups[1:]:
        d = f - prev
        while d > 254:
            out.append(1)          # advance 254 without a fixup
            d -= 254
        assert d % 2 == 0 and 0 < d <= 254, f"bad reloc delta {d}"
        out.append(d)
        prev = f
    out.append(0)                  # terminator
    return bytes(out)


def main():
    elf, binf, out = sys.argv[1], sys.argv[2], sys.argv[3]
    text = open(binf, "rb").read()
    fixups = abs_fixups(elf)

    # GEMDOS places BSS at tlen+dlen, so the emitted text+data MUST reach _bss_start. The linker
    # aligns .bss (e.g. for a 256-aligned image) to a boundary past the end of .data; objcopy does
    # not emit that trailing gap, so pad it here — otherwise on-target BSS lands at the wrong address.
    bss_start = sym_value(elf, "_bss_start")
    if bss_start is not None and bss_start > len(text):
        text += b"\x00" * (bss_start - len(text))

    tlen, dlen, blen = len(text), 0, bss_size(elf)

    header = struct.pack(">H 6I",
                         0x601a,       # magic
                         tlen, dlen, blen,
                         0,            # symbol table length
                         0,            # reserved
                         0)            # prgflags
    header += struct.pack(">H", 0)     # absflag = 0 -> reloc table present
    open(out, "wb").write(header + text + reloc_table(fixups))
    print(f"{out}: text={tlen} data={dlen} bss={blen} relocs={len(fixups)}")


if __name__ == "__main__":
    main()
