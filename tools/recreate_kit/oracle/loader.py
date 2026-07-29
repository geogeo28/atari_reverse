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

# Bound per project by recreate_kit.project.load() from that project's project.toml — see
# tools/recreate_kit/project.py. Left None so an unbound import fails loudly instead of
# silently loading at some other game's base.
LOAD_BASE = None             # matches PrgLoader / run.sh default (see CLAUDE.md)
IMAGE_SIZE = None            # flat image length: program + file staging + load buffers + stack
PROGRAM_END = None           # LOAD_BASE + text+data+bss, set by load_image(); the harness vets the
                             # TOS model's fixed regions (heap, file staging) against it
HEADER = 28                  # GEMDOS .PRG header length


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