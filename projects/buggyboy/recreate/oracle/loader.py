"""Load BUGGYBOY.PRG into a flat, relocated big-endian memory image.

The image is a plain ``bytearray`` whose indices ARE Ghidra addresses:
byte ``i`` holds what the 68000 sees at address ``i``. Text+data are placed at
``LOAD_BASE``; the relocation table's absolute longwords get ``LOAD_BASE`` added
(they are stored assuming a text base of 0). BSS is left zeroed.

Reuses the header/reloc parsing from ``tools/prg_dis.py`` (single source of truth).
"""
import struct
import sys
from pathlib import Path

# tools/ lives three levels up from this file: recreate/oracle/ -> buggyboy -> projects -> reverse
_TOOLS = Path(__file__).resolve().parents[4] / "tools"
sys.path.insert(0, str(_TOOLS))
import prg_dis  # noqa: E402

LOAD_BASE = 0x10000          # matches PrgLoader / run.sh default (see CLAUDE.md)
IMAGE_SIZE = 0x20000         # covers code + data + bss for BUGGYBOY.PRG (text ends 0x1bcf8)
HEADER = 28                  # GEMDOS .PRG header length


def load_image(prg_path):
    """Return a bytearray of length IMAGE_SIZE with the relocated program at LOAD_BASE."""
    data = Path(prg_path).read_bytes()
    h = prg_dis.parse_header(data)
    fixes = prg_dis.parse_reloc(data, h)

    seg = h["tlen"] + h["dlen"]          # text+data bytes to copy verbatim
    if LOAD_BASE + seg + h["blen"] > IMAGE_SIZE:
        raise ValueError("IMAGE_SIZE too small for this program")

    img = bytearray(IMAGE_SIZE)
    img[LOAD_BASE:LOAD_BASE + seg] = data[HEADER:HEADER + seg]

    # Apply relocations: each fixed longword (image offset, text base 0) += LOAD_BASE.
    for off in fixes:
        a = LOAD_BASE + off
        val = struct.unpack_from(">I", img, a)[0]
        struct.pack_into(">I", img, a, (val + LOAD_BASE) & 0xFFFFFFFF)

    return img