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


def differential(entry, regs, glue, stop_pc=0, exclude=None):
    """Run oracle + candidate on the same image. Return (diffs, info).

    ``diffs`` is the list of (addr, oracle, cand) byte differences (stack-guard excluded).
    ``info`` carries {"writes", "regs", "ret"}: the oracle write-set, the oracle's D0/D1/A0/A1
    at return, and whatever the candidate glue returned (its D0, or None for void glues).
    ``regs`` are the oracle's input registers; ``glue(lib, buf)`` runs the candidate on a
    mutable ctypes copy of the same image with the matching arguments.

    ``stop_pc`` diffs at a checkpoint PC instead of at rts (for a function that never returns;
    see emu.run). ``exclude`` is an optional list of (lo, hi) byte bands to drop from the diff
    in addition to the default stack guard — used when the function relocates its own stack
    outside [STACK_GUARD_LO, IMAGE_SIZE) (e.g. _start moves A7 to 0x1b044). The candidate is
    pure C and never writes a machine stack, so excluding the oracle's stack band is sound.
    """
    img = make_image(regs.pop("_pokes", None))
    o_final, o_writes, o_regs = emu.run(img, entry, regs, stop_pc=stop_pc)

    Buf = ctypes.c_uint8 * IMAGE_SIZE
    buf = Buf.from_buffer(bytearray(img))
    cand_ret = glue(_lib, buf)
    c_final = bytes(buf)

    def excluded(a):
        return any(lo <= a < hi for lo, hi in (exclude or ()))

    # Diff only [0, STACK_GUARD_LO): the oracle uses the guard region above as a real machine
    # stack (return address, saved registers) that the C reconstruction has no analogue for.
    # Fast path — compare that prefix at C speed; only walk it byte-by-byte when it actually
    # differs (a failure, or an excluded band like _start's relocated stack). This keeps the
    # scan cheap as IMAGE_SIZE grows (the prefix is ~1 MiB now).
    guard_lo = emu.STACK_GUARD_LO
    if bytes(o_final[:guard_lo]) == bytes(c_final[:guard_lo]):
        diffs = []
    else:
        diffs = [(a, o_final[a], c_final[a])
                 for a in range(guard_lo)
                 if o_final[a] != c_final[a] and not excluded(a)]

    # Write-set completeness: the guard cutoff above is only sound if the oracle used that
    # region purely as stack. A write in [STACK_GUARD_LO, STACK_TOP - STACK_SCRATCH) is program
    # output the diff would silently hide — fail loudly so it can't pass as verified.
    stray = sorted(a for a in o_writes
                   if emu.STACK_GUARD_LO <= a < emu.STACK_TOP - emu.STACK_SCRATCH)
    if stray:
        raise AssertionError(
            f"oracle wrote {len(stray)} byte(s) in the reserved stack-guard band "
            f"(e.g. {label(stray[0])} @ 0x{stray[0]:x}) — real output masked by the guard cutoff")

    return diffs, {"writes": o_writes, "regs": o_regs, "ret": cand_ret}


def report(diffs):
    return "\n".join(f"  {label(a)} (0x{a:x}): oracle={o:#04x} cand={c:#04x}" for a, o, c in diffs)