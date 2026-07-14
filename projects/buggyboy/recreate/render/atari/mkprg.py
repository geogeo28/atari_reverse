#!/usr/bin/env python3
"""Wrap a base-0 linked m68k ELF into a GEMDOS .PRG.

Emits the 28-byte header, the flat text+data image (objcopy -O binary output), and a GEMDOS
relocation table built from the ELF's R_68K_32 fixups (kept via `ld --emit-relocs`). Because the
program is linked at base 0, each fixup's virtual address equals its byte offset in the flat
binary, and the 32-bit value already stored there is the target's base-0 address — exactly what
GEMDOS expects to add the load base to.

Usage: mkprg.py demo.elf demo.bin out.prg
"""
import re
import struct
import subprocess
import sys

READELF = "m68k-elf-readelf"


def bss_size(elf):
    out = subprocess.check_output([READELF, "-S", "-W", elf], text=True)
    for line in out.splitlines():
        m = re.search(r"\.bss\s+\w+\s+[0-9a-f]+\s+[0-9a-f]+\s+([0-9a-f]+)", line)
        if m:
            return int(m.group(1), 16)
    return 0


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
    tlen, dlen, blen = len(text), 0, bss_size(elf)
    fixups = abs_fixups(elf)

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
