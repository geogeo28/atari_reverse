"""Oracle: execute one BUGGYBOY function under Musashi's 68000 core (via liboracle.so).

Ground truth for the differential test. Same interface the rest of the harness expects:
``run(image, entry, regs) -> (final_image, writes, out_regs)``. The backend is the MAME
68000 core (kstenerud/Musashi), which is faithful to real 68000 behavior — unlike
Unicorn's ColdFire-derived core, which mis-handles byte memory read-modify-write.
"""
import ctypes
from pathlib import Path

from loader import IMAGE_SIZE

# The stack lives at the top of the image; derived from IMAGE_SIZE so growing the image moves
# it automatically (keep 0x100 headroom for the sentinel return slot, a 0xF00 guard span).
STACK_TOP = IMAGE_SIZE - 0x100   # A7 start; stack grows down into the guard region below
STACK_GUARD_LO = STACK_TOP - 0xF00  # [STACK_GUARD_LO, IMAGE_SIZE): stack scratch, excluded from the diff
STACK_SCRATCH = 0x400     # bytes below STACK_TOP a call frame may legitimately use; a write in
                          # [STACK_GUARD_LO, STACK_TOP - STACK_SCRATCH) is program output, not stack
SENTINEL = 0x00000002     # even, mapped, never real code (code >= 0x10000): rts lands here

_DREG_NAMES = ("d0", "d1", "d2", "d3", "d4", "d5", "d6", "d7")
_AREG_NAMES = ("a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7")

_LIB = ctypes.CDLL(str(Path(__file__).resolve().parent / "build" / "liboracle.so"))
_u32p = ctypes.POINTER(ctypes.c_uint32)
_LIB.osh_run.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.c_uint32,
                         _u32p, _u32p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                         ctypes.c_uint32, _u32p]
_LIB.osh_run.restype = ctypes.c_int
_LIB.osh_num_writes.restype = ctypes.c_uint32
_LIB.osh_write_addrs.restype = _u32p
_LIB.osh_unmodeled.restype = ctypes.c_uint32
_LIB.osh_min_a7.restype = ctypes.c_uint32
_LIB.osh_num_insns.restype = ctypes.c_uint32
_u8p = ctypes.POINTER(ctypes.c_uint8)
_LIB.osh_psg_count.restype = ctypes.c_uint32
_LIB.osh_psg_regs.restype = _u8p
_LIB.osh_psg_vals.restype = _u8p
_LIB.osh_cov_enable.argtypes = [ctypes.c_int]
_LIB.osh_cov_visited.argtypes = [ctypes.c_uint32]
_LIB.osh_cov_visited.restype = ctypes.c_int
_LIB.osh_cov_data.restype = _u8p
_LIB.osh_cov_bytes.restype = ctypes.c_uint32


def cov_enable(on=True):
    """Turn on executed-PC coverage tracking in the oracle (off by default; adds nothing when off)."""
    _LIB.osh_cov_enable(1 if on else 0)


def cov_reset():
    """Clear the accumulated coverage bitset (call once before running the corpus to measure)."""
    _LIB.osh_cov_reset()


def cov_visited(addr):
    """Was the instruction at Ghidra address ``addr`` executed by any ``run()`` since cov_reset()?"""
    return bool(_LIB.osh_cov_visited(addr & 0xFFFFFFFF))


def cov_data():
    """The raw visited-PC bitset (bit i = address i executed). For dumping/merging across workers."""
    n = _LIB.osh_cov_bytes()
    return bytes(ctypes.cast(_LIB.osh_cov_data(), ctypes.POINTER(ctypes.c_uint8 * n)).contents)


def psg_writes():
    """(reg, val) YM2149 writes captured during the most recent ``run()``, in order.

    ``run()`` resets the capture each call, so this is exactly that call's PSG traffic —
    one VBL frame's worth when ``run()`` drove the sound driver's ``REFRESH``.
    """
    n = _LIB.osh_psg_count()
    regs, vals = _LIB.osh_psg_regs(), _LIB.osh_psg_vals()
    return [(regs[i], vals[i]) for i in range(n)]


def run(image, entry, regs=None, max_insns=200_000, stop_pc=0):
    """Run ``entry`` on a copy of ``image``. Return (final_image, writes, out_regs).

    ``regs`` maps register name -> value (e.g. {"a1": 0x1e000}); A7 is forced to STACK_TOP.
    ``stop_pc`` is an optional checkpoint PC: with it set, the run stops when it reaches that
    address instead of only at rts — the way to diff a function that never returns (its final
    memory is trustworthy at the checkpoint). ``writes`` is {addr: byte} for every byte the
    code stored (stack writes included). ``out_regs`` holds D0/D1/A0/A1 at return.
    """
    regs = regs or {}
    mem = bytearray(image)
    Buf = ctypes.c_uint8 * IMAGE_SIZE
    buf = Buf.from_buffer(mem)

    dregs = (ctypes.c_uint32 * 8)(*[regs.get(n, 0) & 0xFFFFFFFF for n in _DREG_NAMES])
    aregs = (ctypes.c_uint32 * 8)(*[regs.get(n, 0) & 0xFFFFFFFF for n in _AREG_NAMES])
    out = (ctypes.c_uint32 * 4)()

    reached = _LIB.osh_run(buf, IMAGE_SIZE, entry & 0xFFFFFFFF, dregs, aregs,
                           STACK_TOP, SENTINEL, stop_pc & 0xFFFFFFFF, max_insns, out)
    if not reached:
        where = f"checkpoint {stop_pc:#x}" if stop_pc else "rts"
        raise RuntimeError(f"function @ {entry:#x} did not reach {where} within {max_insns} "
                           f"instructions; final memory is mid-execution, not trustworthy")
    if _LIB.osh_unmodeled():
        raise RuntimeError(f"function @ {entry:#x} used an unmodeled OS call "
                           f"(e.g. Fread/Supexec/GEM); its result is fabricated, not trustworthy")

    n = _LIB.osh_num_writes()
    waddr = _LIB.osh_write_addrs()
    writes = {waddr[i]: mem[waddr[i]] for i in range(n)}
    out_regs = {"d0": out[0], "d1": out[1], "a0": out[2], "a1": out[3]}
    out_regs["min_a7"] = _LIB.osh_min_a7()   # deepest stack pointer; used to vet diff exclude bands
    out_regs["ninsns"] = _LIB.osh_num_insns()  # instructions executed (perf profiling)
    return mem, writes, out_regs