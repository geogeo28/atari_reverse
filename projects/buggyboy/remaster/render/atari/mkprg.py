#!/usr/bin/env python3
"""Wrap a base-0 linked m68k ELF into a GEMDOS .PRG. Copied from recreate/render/atari/mkprg.py.

Emits the 28-byte header, the flat text+data image (objcopy -O binary output), and a GEMDOS
relocation table built from the ELF's R_68K_32 fixups (kept via `ld --emit-relocs`).

Usage: mkprg.py game.elf game.bin out.prg
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


def sym_value(elf, name):
    out = subprocess.check_output(["m68k-elf-nm", elf], text=True)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == name:
            return int(parts[0], 16)
    return None


def abs_fixups(elf):
    out = subprocess.check_output([READELF, "-r", "-W", elf], text=True)
    # Only relocs in the LOADED sections (.text/.data) belong in the .PRG reloc table. For this base-0
    # `ld --emit-relocs` executable a reloc's Offset column is a VIRTUAL ADDRESS: an allocated section's
    # vaddr equals its offset in the flat text+data image, so .rela.text/.rela.data offsets are already
    # the correct .PRG fixup positions (no +text_size adjustment — .data's vaddr already includes it).
    # Non-allocated debug sections sit at vaddr 0, so their relocs collide with low .text offsets (and land
    # odd, tripping reloc_table) — hence the filter. The section whitelist is correct under the current
    # tos.ld (only .rela.text/.rela.data are allocated; .rodata folds into .text); a future split-out
    # allocated reloc section (e.g. -ffunction-sections .rela.text.hot) would need adding here. Stock
    # builds carry no debug relocs, so this is a no-op there; only a build that emits debug line-info needs it.
    offs = set()
    in_loaded = False
    for line in out.splitlines():
        m = re.search(r"Relocation section '(\S+)'", line)
        if m:
            in_loaded = m.group(1) in (".rela.text", ".rela.data")
            continue
        m = re.match(r"\s*([0-9a-fA-F]{8})\s+[0-9a-fA-F]{8}\s+(\S+)", line)
        if in_loaded and m and m.group(2) == "R_68K_32":
            offs.add(int(m.group(1), 16))
    return sorted(offs)


def reloc_table(fixups):
    if not fixups:
        return struct.pack(">I", 0)
    out = bytearray(struct.pack(">I", fixups[0]))
    prev = fixups[0]
    for f in fixups[1:]:
        d = f - prev
        while d > 254:
            out.append(1)
            d -= 254
        assert d % 2 == 0 and 0 < d <= 254, f"bad reloc delta {d}"
        out.append(d)
        prev = f
    out.append(0)
    return bytes(out)


def main():
    elf, binf, out = sys.argv[1], sys.argv[2], sys.argv[3]
    text = open(binf, "rb").read()
    fixups = abs_fixups(elf)

    bss_start = sym_value(elf, "_bss_start")
    if bss_start is not None and bss_start > len(text):
        text += b"\x00" * (bss_start - len(text))

    tlen, dlen, blen = len(text), 0, bss_size(elf)
    header = struct.pack(">H 6I", 0x601a, tlen, dlen, blen, 0, 0, 0)
    header += struct.pack(">H", 0)     # absflag = 0 -> reloc table present
    open(out, "wb").write(header + text + reloc_table(fixups))
    print(f"{out}: text={tlen} data={dlen} bss={blen} relocs={len(fixups)}")


if __name__ == "__main__":
    main()
