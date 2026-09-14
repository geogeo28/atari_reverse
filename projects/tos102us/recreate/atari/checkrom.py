#!/usr/bin/env python3
"""checkrom.py — refuse a rebuilt ROM image whose OS header does not say what romdefs.h says.

    python3 checkrom.py build/TOS102RC.IMG build/tos_rom.elf original.img

THE HEADER IS THE ONE PART OF A ROM THAT EVERY OTHER PROGRAM READS BEFORE IT RUNS A SINGLE
INSTRUCTION — the machine takes its reset PC from it, Hatari identifies the image by its version
word, a loader finds GEM through os_magic — so a header that is wrong produces a machine that does
something arbitrary rather than a build that complains. This is the complaint.

IT EXISTS BECAUSE TWO CONSTANTS CAN DISAGREE AND A MUTATION PROVED IT. The MUPB's address is spelled
in romdefs.h (as the header field `os_magic`) and again in tos_rom.ld (as the address the `.mupb`
section is placed at), because a linker script cannot include a C header. Moving the romdefs.h one by
0x100 and rebuilding produced a perfectly well-formed 196,608-byte ROM whose os_magic pointed at
twelve bytes of zero — and both of the build's assertions passed, because the size was right and the
reset entry had not moved. So the check here is not "the two constants are equal" (which would be a
third copy of the same number): it FOLLOWS the pointer in the built image and requires the magic to
be there. A pointer proved by dereferencing it cannot be pinned to the wrong address.

WHAT IT CHECKS, all against the IMAGE rather than against the sources that produced it:
  * the length is exactly ROM_BYTES;
  * every OS header field equals its romdefs.h value;
  * the header opens with a `bra.s` to the reset entry, and os_start points at the same place;
  * `_reset` is linked where os_start says (this one needs the ELF, so it is the only check that
    reads anything but the image);
  * os_magic points at a MUPB whose magic longword is there;
  * and that the rebuilt header is byte-identical to the ORIGINAL ROM's first OS_HEADER_BYTES. That
    is the only check here that is a CONFORMANCE claim rather than an internal consistency one —
    everything above it would still pass if romdefs.h and the image agreed on the wrong number,
    which a mutation demonstrated: moving OS_ENTRY_OFFSET to 0x34 moves the reset PC, os_start and
    the opening bra.s together, and nothing internal notices.

THE ORIGINAL IS REQUIRED, not optional. It is gitignored (Atari copyright) and it is read in place,
but a recreate of a ROM cannot be checked against anything else: without it every field VALUE above
is unverified, and a build that printed "NOT cross-checked" and returned 0 would be a green build
that proved nothing. A machine that does not have the ROM cannot run this project's Tier 2 either.
"""
import struct
import subprocess
import sys
from pathlib import Path

import cdefines

HERE = Path(__file__).resolve().parent
ROMDEFS = HERE / "romdefs.h"
NM = "m68k-elf-nm"
RESET_SYMBOL = "_reset"

# The 68000's `bra.s` is 0x60 followed by the signed byte displacement from the address of the word
# AFTER the opcode, i.e. from ROM_BASE + 2.
BRA_S_OPCODE = 0x60
BRA_S_ORIGIN = 2

# Where each header field lives and how wide it is. The names are romdefs.h's, minus the OS_ prefix
# where the field has an Atari name of its own; the third column is the romdefs.h macro that has to
# equal it, or None for a field derived from others.
HEADER_FIELDS = (
    (0x02, "H", "os_version", "OS_VERSION"),
    (0x04, "I", "os_start", "OS_START"),
    (0x08, "I", "os_base", "ROM_BASE"),
    (0x0C, "I", "os_membot", "OS_MEMBOT"),
    (0x10, "I", "os_rsv1", "OS_RSV1"),
    (0x14, "I", "os_magic", "OS_MUPB"),
    (0x18, "I", "os_date", "OS_DATE_BCD"),
    (0x1C, "H", "os_conf", "OS_CONF"),
    (0x1E, "H", "os_dosdate", "OS_DOSDATE"),
    (0x20, "I", "p_root", "OS_P_ROOT"),
    (0x24, "I", "pkbshift", "OS_P_KBSHIFT"),
    (0x28, "I", "p_run", "OS_P_RUN"),
    (0x2C, "I", "p_rsv2", "OS_RSV2"),
)
FIELD_FORMAT = {"H": ">H", "I": ">I"}
FIELD_DIGITS = {"H": 4, "I": 8}


def defines():
    """romdefs.h's `#define`s, through the parser this directory's other drivers read headers with."""
    return cdefines.defines(ROMDEFS)


def reset_symbol_address(elf):
    """Where the linker put `_reset`, straight out of the ELF."""
    for line in subprocess.run([NM, str(elf)], text=True, capture_output=True,
                               check=True).stdout.splitlines():
        columns = line.split()
        if len(columns) == 3 and columns[2] == RESET_SYMBOL:
            return int(columns[0], 16)
    raise SystemExit(f"FAIL: {elf} has no {RESET_SYMBOL} symbol")


def header_against_original(image, original_path, header_bytes):
    """The conformance half: the rebuilt header versus the original ROM's, field by field."""
    original = Path(original_path).read_bytes()
    if image[:header_bytes] == original[:header_bytes]:
        return []
    faults = []
    for offset, width, name, _macro in HEADER_FIELDS:
        mine = struct.unpack_from(FIELD_FORMAT[width], image, offset)[0]
        theirs = struct.unpack_from(FIELD_FORMAT[width], original, offset)[0]
        if mine != theirs:
            faults.append(f"header field {name} at +{offset:#04x} reads "
                          f"{mine:#0{FIELD_DIGITS[width] + 2}x}; the original ROM has "
                          f"{theirs:#0{FIELD_DIGITS[width] + 2}x}")
    if not faults:
        faults.append("the header differs from the original's somewhere HEADER_FIELDS does not name "
                      "— compare the first bytes of the two images by hand")
    return faults


def check(image_path, elf_path, original_path):
    values = defines()
    image = Path(image_path).read_bytes()
    faults = []

    if len(image) != values["ROM_BYTES"]:
        faults.append(f"the image is {len(image)} bytes, romdefs.h says {values['ROM_BYTES']}")
        return faults                       # every offset below would be meaningless

    for offset, width, name, macro in HEADER_FIELDS:
        actual = struct.unpack_from(FIELD_FORMAT[width], image, offset)[0]
        expected = values[macro]
        if actual != expected:
            faults.append(f"header field {name} at +{offset:#04x} reads "
                          f"{actual:#0{FIELD_DIGITS[width] + 2}x}, {macro} is {expected:#x}")

    if image[0] != BRA_S_OPCODE:
        faults.append(f"the header does not open with a bra.s ({image[0]:#04x})")
    else:
        branches_to = values["ROM_BASE"] + BRA_S_ORIGIN + image[1]
        if branches_to != values["OS_START"]:
            faults.append(f"the opening bra.s goes to {branches_to:#x}, os_start is "
                          f"{values['OS_START']:#x}")

    linked = reset_symbol_address(elf_path)
    if linked != values["OS_START"]:
        faults.append(f"{RESET_SYMBOL} is linked at {linked:#x}, os_start is {values['OS_START']:#x}")

    # The dereference this file exists for: follow os_magic and require the MUPB to be there.
    magic_at = struct.unpack_from(">I", image, 0x14)[0] - values["ROM_BASE"]
    if not 0 <= magic_at <= len(image) - 4:
        faults.append(f"os_magic points outside the ROM ({magic_at + values['ROM_BASE']:#x})")
    else:
        magic = struct.unpack_from(">I", image, magic_at)[0]
        if magic != values["MUPB_MAGIC"]:
            faults.append(f"os_magic points at {magic_at + values['ROM_BASE']:#x}, which holds "
                          f"{magic:#010x} and not the MUPB magic {values['MUPB_MAGIC']:#010x}")

    faults += header_against_original(image, original_path, values["OS_HEADER_BYTES"])
    return faults


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    original = sys.argv[3]
    if not Path(original).is_file():
        print(f"FAIL: the original ROM {original} is not here, so no field VALUE in the rebuilt "
              f"header can be checked against anything. Put the user's own TOS102US.img at "
              f"tools/hatari/TOS102US.img (it is gitignored and read in place).")
        return 1
    faults = check(sys.argv[1], sys.argv[2], original)
    if faults:
        for fault in faults:
            print(f"FAIL: {fault}")
        return 1
    values = defines()
    print(f"ROM header: {len(HEADER_FIELDS)} fields match romdefs.h, {values['ROM_BYTES']} bytes, "
          f"reset PC ${values['OS_START']:06x}, MUPB found at ${values['OS_MUPB']:06x}")
    print(f"            header byte-identical to {Path(original).name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
