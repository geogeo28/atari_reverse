"""Load a GEMDOS .PRG into a flat, relocated big-endian memory image.

The image is a plain ``bytearray`` whose indices ARE Ghidra addresses:
byte ``i`` holds what the 68000 sees at address ``i``. Text+data are placed at
``LOAD_BASE``; the relocation table's absolute longwords get ``LOAD_BASE`` added
(they are stored assuming a text base of 0). BSS is left zeroed.

Reuses the header/reloc parsing from ``tools/prg_dis.py`` (single source of truth).
"""
import struct
import sys
from pathlib import Path

# tools/ is two levels up from this file: recreate_kit/oracle/ -> recreate_kit -> tools
_TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_TOOLS))
import prg_dis  # noqa: E402
from recreate_kit import os_map  # noqa: E402  (the I/O page's base, mirrored from os.h)

# Bound per project by recreate_kit.project.load() from that project's project.toml — see
# tools/recreate_kit/project.py. Left None so an unbound import fails loudly instead of
# silently loading at some other game's base.
LOAD_BASE = None             # matches PrgLoader / run.sh default (see CLAUDE.md)
IMAGE_SIZE = None            # flat image length: program + file staging + load buffers + stack
PROGRAM_END = None           # LOAD_BASE + text+data+bss, set by load_image(); the harness vets the
                             # TOS model's fixed regions (heap, file staging) against it
HEADER = 28                  # GEMDOS .PRG header length


def load_rom_image(snapshot_path, rom_path, rom_base):
    """Return a bytearray of length IMAGE_SIZE: the post-boot RAM snapshot at 0, the ROM at rom_base.

    The ROM-mode counterpart of ``load_image``. There is no program and no relocation — a ROM is
    linked at the address it is mapped at, and the snapshot is a photograph of RAM taken at a
    deterministic point of the machine's own boot (see the project's ``tools/boot_snapshot.py``).
    The image is the whole 24-bit address space, so byte ``i`` is still exactly what the 68000 sees
    at address ``i``; the I/O page inside it is decoded by the oracle's memory callbacks rather than
    served from these bytes (``shim.c``, "THE MEMORY MAP").

    ``PROGRAM_END`` is deliberately left at None: it means "where the loaded PROGRAM ends", which is
    what the TOS model's region guards are asked against, and a ROM project has no program for them
    to collide with.
    """
    if IMAGE_SIZE is None:
        raise RuntimeError("the loader is unbound: call recreate_kit.project.load(<recreate dir>) "
                           "first — it sets IMAGE_SIZE from that project's project.toml")
    snapshot = Path(snapshot_path).read_bytes()
    rom = Path(rom_path).read_bytes()
    if rom_base + len(rom) > IMAGE_SIZE:
        raise ValueError(f"the {len(rom)}-byte ROM at {rom_base:#x} does not fit in the "
                         f"{IMAGE_SIZE:#x}-byte image")
    # ...and it may not reach the I/O page. The oracle consults the ROM window AFTER the modeled
    # hardware slots but BEFORE the off-image fallback, so a window that covered $ff0000 would serve
    # every unmodeled I/O read out of whatever ROM byte sits there — silently, with no ledger entry
    # and no refusal. Reachable by a wrong ROM file or a ROM revision of another size.
    if rom_base + len(rom) > os_map.OS_HW_IO_PAGE:
        raise ValueError(f"the {len(rom)}-byte ROM at {rom_base:#x} reaches the I/O page "
                         f"({os_map.OS_HW_IO_PAGE:#x}), whose addresses the oracle decodes rather "
                         f"than serving from the image — reads of them would answer ROM bytes")
    if len(snapshot) > rom_base:
        raise ValueError(f"the {len(snapshot)}-byte RAM snapshot reaches the ROM at {rom_base:#x}")
    img = bytearray(IMAGE_SIZE)
    img[0:len(snapshot)] = snapshot
    img[rom_base:rom_base + len(rom)] = rom
    return img


def load_image(prg_path):
    """Return a bytearray of length IMAGE_SIZE with the relocated program at LOAD_BASE."""
    if LOAD_BASE is None or IMAGE_SIZE is None:
        raise RuntimeError("the loader is unbound: call recreate_kit.project.load(<recreate dir>) "
                           "first — it sets LOAD_BASE/IMAGE_SIZE from that project's project.toml")
    data = Path(prg_path).read_bytes()
    h = prg_dis.parse_header(data)
    fixes = prg_dis.parse_reloc(data, h)

    seg = h["tlen"] + h["dlen"]          # text+data bytes to copy verbatim
    global PROGRAM_END
    PROGRAM_END = LOAD_BASE + seg + h["blen"]
    if PROGRAM_END > IMAGE_SIZE:
        raise ValueError("IMAGE_SIZE too small for this program")

    img = bytearray(IMAGE_SIZE)
    img[LOAD_BASE:LOAD_BASE + seg] = data[HEADER:HEADER + seg]

    # Apply relocations: each fixed longword (image offset, text base 0) += LOAD_BASE.
    for off in fixes:
        a = LOAD_BASE + off
        val = struct.unpack_from(">I", img, a)[0]
        struct.pack_into(">I", img, a, (val + LOAD_BASE) & 0xFFFFFFFF)

    return img