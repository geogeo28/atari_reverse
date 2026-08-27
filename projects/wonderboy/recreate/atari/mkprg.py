#!/usr/bin/env python3
"""Wrap a base-0 linked m68k ELF into a GEMDOS .PRG.

Emits the 28-byte header, the flat text+data image (objcopy -O binary output), and a GEMDOS
relocation table built from the ELF's R_68K_32 fixups (kept via `ld --emit-relocs`). Because the
program is linked at base 0, each fixup's virtual address equals its byte offset in the flat
binary, and the 32-bit value already stored there is the target's base-0 address — exactly what
GEMDOS expects to add the load base to.

Usage: mkprg.py demo.elf demo.bin out.prg

EVERY FIXUP IS CLASSIFIED BY WHERE IT LIVES AND THEN CHECKED AGAINST THE IMAGE, because build.sh
links with `--gc-sections`: an entry left behind for a section the collector discarded names an
offset that is not a pointer, and relocating it adds the load base to a live byte — corruption with
no symptom until some later frame. `abs_fixups` is where that is decided and says what it refuses;
`table_offsets` reads the emitted table back the way TOS will walk it. The measurements and the
mutation checks behind all of it are in ../STATUS.md, "## Performance" (2026-08-26), which is
canonical for them.

COPIED FROM projects/joust/recreate/atari/mkprg.py, which is itself copied from the BuggyBoy build.
The copies were identical BELOW THIS PARAGRAPH and are now TWO ADDITIONS apart: `nm_rows`, the
single parse of `m68k-elf-nm`'s output that `sym_value` and atari/profile.py share, and the fixup
classification above. Both belong in the other copies — `nm_rows` is behaviour-neutral there
(`sym_value` is its only caller), and a link without `--gc-sections` discards nothing, so the
classification refuses nothing new there while holding those builds to the same standard. Every
other change to any of them still belongs in all of them. Copied rather than moved into
`tools/recreate_kit/` because that move is a kit change touching two other projects; it is
registered as a kit candidate in ../STATUS.md's batch 43 phase A queue and in Joust's own README.
"""
import re
import struct
import subprocess
import sys

READELF = "m68k-elf-readelf"
NM = "m68k-elf-nm"

# A GEMDOS fixup relocates a 32-bit longword, so an entry belongs to a section only when all four
# of its bytes do.
FIXUP_BYTES = 4

# The GEMDOS relocation table's byte alphabet, named once because `reloc_table` writes it and
# `table_offsets` reads it back and the two must not drift: RELOC_END_BYTE ends the table,
# RELOC_SKIP_BYTE advances RELOC_SPAN bytes without relocating anything, and any other byte is the
# (even) delta to the next fixup — which is why RELOC_SPAN is also the largest delta one byte can
# carry.
RELOC_END_BYTE = 0
RELOC_SKIP_BYTE = 1
RELOC_SPAN = 254

# `readelf -S`'s Flg column: `A` = allocated, i.e. the section is part of the loaded program.
SECTION_FLAG_ALLOC = "A"


def refuse(reason):
    """Stop the build, loudly and with a non-zero exit.

    NOT an `assert`: this script runs under whatever `python3` build.sh finds, and `-O` or
    PYTHONOPTIMIZE in that environment would strip every assert — writing the corruption each of
    them guards against straight into the .PRG, which is the one failure mode none of the surfaces
    downstream can see until a frame lands on it."""
    raise SystemExit(f"REFUSED: {reason}")


# ELF section header row, `readelf -S -W`: `[Nr] Name Type Addr Off Size ES Flg`. The unnamed
# section 0 shifts every field one to the left, which is why the type is matched by name rather
# than by position — `NULL` is not `PROGBITS`, so that row falls out here.
SECTION_ROW = re.compile(
    r"\s*\[\s*\d+\]\s+(?P<name>\S+)\s+(?P<type>\S+)\s+(?P<addr>[0-9a-fA-F]+)\s+[0-9a-fA-F]+"
    r"\s+(?P<size>[0-9a-fA-F]+)\s+[0-9a-fA-F]+\s+(?P<flags>\S*)")

# Relocation row, `readelf -r -W`: `Offset Info Type Sym.Value Symbol's Name +/- Addend`. TWO parts
# of that line are not what a first reading assumes, and both are real output rather than cases
# that cannot arise: the addend CARRIES A SIGN — readelf prints `sym - 4` for a reference to the
# bytes ahead of a symbol — and the NAME COLUMN IS EMPTY for a relocation against a section symbol
# the ELF does not name. A row this pattern cannot read is refused below, so a format it silently
# skipped would be a fixup silently not emitted.
RELOC_ROW = re.compile(
    r"\s*([0-9a-fA-F]+)\s+[0-9a-fA-F]+\s+(\S+)\s+([0-9a-fA-F]+)\s+(?:\S+\s+)?([-+])\s*([0-9a-fA-F]+)\s*$")


def section_rows(elf):
    """Every section header as a match — THE ONE PARSE of `readelf -S`.

    `bss_size` and `loaded_sections` read different columns of the same rows, so they share one
    regex rather than each carrying its own reading of the same output."""
    out = subprocess.check_output([READELF, "-S", "-W", elf], text=True)
    return [row for row in (SECTION_ROW.match(line) for line in out.splitlines()) if row]


def bss_size(elf):
    """Size of .bss, which GEMDOS zeroes after the image (0 if the program has none)."""
    return next((int(row["size"], 16) for row in section_rows(elf) if row["name"] == ".bss"), 0)


def loaded_sections(elf):
    """(start, end) of every allocated PROGBITS section — the bytes that reach the flat binary.

    A section the `--gc-sections` collector discarded is not among them, and neither is `.bss`
    (NOBITS, no bytes in the file). Base-0 link, packed tight, so a section's virtual address IS
    its offset in the flat binary."""
    spans = []
    for row in section_rows(elf):
        if row["type"] == "PROGBITS" and SECTION_FLAG_ALLOC in row["flags"]:
            addr = int(row["addr"], 16)
            spans.append((addr, addr + int(row["size"], 16)))
    return spans


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


def abs_fixups(elf, image):
    """Sorted byte offsets of every R_68K_32 fixup that is really in the image; refuses the rest.

    WHERE A FIXUP LIVES decides whether it may be relocated at all, and there are three answers.
    Inside a loaded section is the normal one. PAST THE END of the flat binary is an entry left
    behind for a section `--gc-sections` discarded: it names nothing this .PRG contains, so it is
    dropped and counted — today's binutils emits none, and the count is how the build would say
    that had changed. INSIDE the binary but in no loaded section is the dangerous one — the
    alignment padding between two sections, or a discarded section still overlapping live bytes —
    because relocating it adds the load base to a live byte that is not a pointer. Refused, not
    dropped: dropping it would silently keep building a .PRG whose layout this file cannot explain.

    WHAT A FIXUP HOLDS is then checked against the ELF itself: the longword already in the image
    must equal the address the ELF resolves the entry to (`Sym. Value + Addend`), and that address
    must be inside the program. A stale entry that happened to alias live text, an offset let
    through, a mis-parsed row — each shows up here as a longword that is not its own target."""
    spans = loaded_sections(elf)
    image_end = max(end for _, end in spans)
    if image_end > len(image):
        refuse(f"the flat binary is {len(image)} bytes, shorter than the {image_end} its sections"
               " describe — objcopy and the ELF disagree about what is in this program")
    # A fixup may TARGET anything the program owns, `.bss` included, and `_bss_end` is one past the
    # top of it — which a pointer to the end of the last array legally holds. Hence `<=` below: a
    # `<` refuses `&arr[64]` for a 64-byte array that happens to end .bss, which is legal C.
    limit = sym_value(elf, "_bss_end") or image_end
    offsets, dropped = set(), 0
    for line in subprocess.check_output([READELF, "-r", "-W", elf], text=True).splitlines():
        if "R_68K_32" not in line:
            continue
        row = RELOC_ROW.match(line)
        # A row this file cannot read is a fixup it would SILENTLY NOT EMIT, and an unrelocated
        # pointer is the same corruption as a wrongly relocated one.
        if not row or row.group(2) != "R_68K_32":
            refuse(f"unreadable relocation row: {line!r}")
        off, addend = int(row.group(1), 16), int(row.group(5), 16)
        target = int(row.group(3), 16) + (-addend if row.group(4) == "-" else addend)
        if not any(start <= off and off + FIXUP_BYTES <= end for start, end in spans):
            if off >= len(image):
                dropped += 1
                continue
            refuse(f"fixup at {off:#x} lies inside the {len(image)}-byte image but in no loaded"
                   " section — section padding, or a discarded section overlapping live bytes."
                   " Relocating it would add the load base to a byte that is not a pointer")
        stored = struct.unpack_from(">I", image, off)[0]
        if stored != target:
            refuse(f"fixup at {off:#x} holds {stored:#x}, but the ELF resolves it to {target:#x} —"
                   " the relocation table would relocate a byte that is not this reference")
        if not 0 <= target <= limit:
            refuse(f"fixup at {off:#x} targets {target:#x}, outside the loaded image (0..{limit:#x})")
        offsets.add(off)
    return sorted(offsets), dropped


def reloc_table(fixups):
    """GEMDOS relocation table: first fixup as a longword, then byte deltas (RELOC_SKIP_BYTE =
    advance RELOC_SPAN with no fixup, RELOC_END_BYTE = end). All offsets are even. Empty table is a
    single zero longword."""
    if not fixups:
        return struct.pack(">I", 0)
    out = bytearray(struct.pack(">I", fixups[0]))
    prev = fixups[0]
    for f in fixups[1:]:
        d = f - prev
        while d > RELOC_SPAN:
            out.append(RELOC_SKIP_BYTE)
            d -= RELOC_SPAN
        if d % 2 != 0 or not 0 < d <= RELOC_SPAN:
            refuse(f"bad reloc delta {d} between fixups {prev:#x} and {f:#x}")
        out.append(d)
        prev = f
    out.append(RELOC_END_BYTE)
    return bytes(out)


def table_offsets(table):
    """Decode a GEMDOS relocation table back to the offsets it names — TOS's own walk.

    The encoder above is where a dropped or duplicated fixup would turn into a table that relocates
    the WRONG longwords, and it is deltas all the way down, so a single wrong byte slides every
    fixup after it. This reads the emitted bytes back the way the loader will, so main() can hold
    the table to the list it was built from rather than to the arithmetic that built it."""
    first = struct.unpack_from(">I", table)[0]
    if first == 0:
        return []
    offsets, cursor = [first], first
    for byte in table[FIXUP_BYTES:]:            # past the leading longword
        if byte == RELOC_END_BYTE:
            break
        cursor += RELOC_SPAN if byte == RELOC_SKIP_BYTE else byte
        if byte != RELOC_SKIP_BYTE:
            offsets.append(cursor)
    return offsets


def main():
    elf, binf, out = sys.argv[1], sys.argv[2], sys.argv[3]
    text = open(binf, "rb").read()
    fixups, dropped = abs_fixups(elf, text)

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
    table = reloc_table(fixups)
    if table_offsets(table) != fixups:
        refuse("the relocation table does not name the fixups it was built from")
    open(out, "wb").write(header + text + table)
    print(f"{out}: text={tlen} data={dlen} bss={blen} relocs={len(fixups)}"
          f" (+{dropped} past the end of the image, dropped)")


if __name__ == "__main__":
    main()
