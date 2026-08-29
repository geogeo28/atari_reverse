#!/usr/bin/env python3
"""Wrap a base-0 linked m68k ELF into a GEMDOS .PRG.

Emits the 28-byte header, the flat text+data image (objcopy -O binary output), and a GEMDOS
relocation table built from the ELF's R_68K_32 fixups (kept via `ld --emit-relocs`). Because the
program is linked at base 0, each fixup's virtual address equals its byte offset in the flat
binary, and the 32-bit value already stored there is the target's base-0 address — exactly what
GEMDOS expects to add the load base to.

Usage: mkprg.py demo.elf demo.bin out.prg

COPIED FROM projects/joust/recreate/atari/mkprg.py, and identical to it BELOW THIS PARAGRAPH
(verified at copy time by diffing the two past their headers; each copy names the other, so the
markers differ and nothing else does). A change to either belongs in both.

THE THIRD COPY HAS DIVERGED AND MUST NOT BE ASSUMED TO MATCH. projects/wonderboy/recreate/atari/
mkprg.py is 250 lines to this one's 105: that project links with `--gc-sections`, and its copy adds
a fixup CLASSIFICATION that refuses a relocation `ld` left behind for a section it discarded — a
corruption its own header says has "no symptom until some later frame". Read its header before
carrying anything either way. Nothing here needs that machinery, because this build does not pass
the flag (tos.ld's header says what adopting it would cost).

None of the three is canonical: `tools/recreate_kit/` is where this ought to live, and it is
registered as a kit candidate in projects/joust/recreate/atari/README.md ("Reviewed and deferred"),
in projects/wonderboy/recreate/STATUS.md's batch 43 phase A queue, and in this directory's
README.md. Until that move happens, this marker is the only thing linking the copies.
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
    """Value of a symbol (e.g. _bss_start) from nm, or None."""
    out = subprocess.check_output(["m68k-elf-nm", elf], text=True)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == name:
            return int(parts[0], 16)
    return None


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
