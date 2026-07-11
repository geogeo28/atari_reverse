"""Differential test harness: real 68000 code (oracle) vs the reconstruction (candidate).

Both run on the same flat memory image; a green case means byte-for-byte identical
final memory. The candidate is the compiled ``libbuggyboy.so``, driven through ctypes.
"""
import ctypes
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                       # recreate/
sys.path.insert(0, str(ROOT / "oracle"))

from loader import load_image, IMAGE_SIZE, LOAD_BASE  # noqa: E402
import emu  # noqa: E402

PRG = ROOT.parent / "bin" / "BUGGYBOY.PRG"            # projects/buggyboy/bin/BUGGYBOY.PRG
NAMES = ROOT.parent / "names.txt"
LIB = ROOT / "build" / "libbuggyboy.so"

BASE_IMAGE = load_image(PRG)             # loaded + relocated once; tests copy & poke it
_lib = ctypes.CDLL(str(LIB))


def _load_name_map():
    """addr -> name, from names.txt `var`/`fn` lines, for readable diff reports."""
    m = {}
    for line in NAMES.read_text().splitlines():
        mm = re.match(r"\s*(?:var|fn)\s+0x([0-9a-fA-F]+)\s+(\S+)", line)
        if mm:
            m[int(mm.group(1), 16)] = mm.group(2)
    return m


NAME_MAP = _load_name_map()


def label(addr):
    """Nearest named global at or below addr, as 'name+off' (or bare hex)."""
    best = max((a for a in NAME_MAP if a <= addr), default=None)
    if best is None or addr - best > 0x40:
        return f"0x{addr:x}"
    off = addr - best
    return NAME_MAP[best] + (f"+{off}" if off else "")


def make_image(pokes=None):
    """Fresh copy of the loaded image with {addr: bytes} written in."""
    img = bytearray(BASE_IMAGE)
    for addr, data in (pokes or {}).items():
        img[addr:addr + len(data)] = data
    return img


def differential(entry, regs, glue):
    """Run oracle + candidate on the same image. Return list of (addr, oracle, cand) diffs.

    ``regs`` are the oracle's input registers; ``glue`` is called as glue(lib, buf) to run
    the candidate on a mutable ctypes copy of the same image with the matching arguments.
    """
    img = make_image(regs.pop("_pokes", None))
    o_final, o_writes, _ = emu.run(img, entry, regs)

    Buf = ctypes.c_uint8 * IMAGE_SIZE
    buf = Buf.from_buffer(bytearray(img))
    glue(_lib, buf)
    c_final = bytes(buf)

    # Ignore the stack-guard region: the oracle uses a real machine stack there
    # (return address, saved registers), which the C reconstruction has no analogue for.
    diffs = [(a, o_final[a], c_final[a])
             for a in range(IMAGE_SIZE)
             if a < emu.STACK_GUARD_LO and o_final[a] != c_final[a]]
    return diffs, o_writes


def report(diffs):
    return "\n".join(f"  {label(a)} (0x{a:x}): oracle={o:#04x} cand={c:#04x}" for a, o, c in diffs)