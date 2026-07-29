"""Oracle: execute one function of the program under test under Musashi's 68000 core (via liboracle.so).

Ground truth for the differential test. Same interface the rest of the harness expects:
``run(image, entry, regs) -> (final_image, writes, out_regs)``. The backend is the MAME
68000 core (kstenerud/Musashi), which is faithful to real 68000 behavior — unlike
Unicorn's ColdFire-derived core, which mis-handles byte memory read-modify-write.
"""
import ctypes
from pathlib import Path

import loader   # bound by recreate_kit.project.load() before this module is first imported
from recreate_kit import project   # already imported: it is what bound `loader` above

if loader.IMAGE_SIZE is None:
    raise RuntimeError("emu was imported before recreate_kit.project.load(<recreate dir>): "
                       "loader.IMAGE_SIZE is unbound, so the stack constants below have no image "
                       "to derive from")

# The stack lives at the top of the image; derived from IMAGE_SIZE so growing the image moves
# it automatically (keep 0x100 headroom for the sentinel return slot, a 0xF00 guard span).
STACK_TOP = loader.IMAGE_SIZE - 0x100   # A7 start; stack grows down into the guard region below
STACK_GUARD_LO = STACK_TOP - 0xF00  # [STACK_GUARD_LO, IMAGE_SIZE): stack scratch, excluded from the diff
STACK_SCRATCH = 0x400     # bytes below STACK_TOP a call frame may legitimately use; a write in
                          # [STACK_GUARD_LO, STACK_TOP - STACK_SCRATCH) is program output, not stack
SENTINEL = 0x00000002     # even, mapped, never real code (code >= 0x10000): rts lands here

# The modeled Malloc heap base, mirroring include/os.h (shim.c bump-allocates from it). It lives
# here rather than with the rest of the os.h mirror in harness.py because the guard below — which
# every emu.run() must pass through, harness or not — needs it; harness.py re-exports it, and
# test/test_os_memory_map.py pins both Python files against os.h.
OS_HEAP_BASE = 0x20000

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
_LIB.osh_heap.restype = ctypes.c_uint32
_LIB.osh_malloc_count.restype = ctypes.c_uint32
_LIB.osh_num_insns.restype = ctypes.c_uint32
_LIB.osh_num_cycles.restype = ctypes.c_uint64
_u8p = ctypes.POINTER(ctypes.c_uint8)
_LIB.osh_psg_count.restype = ctypes.c_uint32
_LIB.osh_psg_regs.restype = _u8p
_LIB.osh_psg_vals.restype = _u8p
_LIB.osh_dosound_count.restype = ctypes.c_uint32
_LIB.osh_dosound_args.restype = _u32p
_LIB.osh_cov_enable.argtypes = [ctypes.c_int]
_LIB.osh_cov_visited.argtypes = [ctypes.c_uint32]
_LIB.osh_cov_visited.restype = ctypes.c_int
_LIB.osh_cov_data.restype = _u8p
_LIB.osh_cov_bytes.restype = ctypes.c_uint32
_LIB.osh_prof_enable.argtypes = [ctypes.c_int]
_LIB.osh_prof_data.restype = _u32p
_LIB.osh_prof_slots.restype = ctypes.c_uint32

_LIB.osh_run_bench.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.c_uint32,
                               ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                               _u32p]
_LIB.osh_run_bench.restype = ctypes.c_int


def run_bench(mem, entry, arg0, sp, sentinel, max_insns=16_000_000):
    """Run a cross-compiled reconstruction function (our C built to m68k, loaded into ``mem`` at its
    link addresses) at ``entry`` with one 32-bit stack argument ``arg0`` (the image pointer). No OS
    traps are installed (see osh_run_bench). ``mem`` is a mutable bytearray already holding the loaded
    recon code + data + the game-image state. Returns {reached, d0, ninsns, cycles}. For measuring the
    reconstruction's own on-target cost, alongside the original's (emu.run)."""
    size = len(mem)
    buf = (ctypes.c_uint8 * size).from_buffer(mem)
    out = (ctypes.c_uint32 * 4)()
    reached = _LIB.osh_run_bench(buf, size, entry & 0xFFFFFFFF, arg0 & 0xFFFFFFFF,
                                 sp & 0xFFFFFFFF, sentinel & 0xFFFFFFFF, max_insns, out)
    if not reached:
        raise RuntimeError(f"recon fn @ {entry:#x} did not return to the sentinel within "
                           f"{max_insns} instructions")
    return {"reached": True, "d0": out[0],
            "ninsns": _LIB.osh_num_insns(), "cycles": _LIB.osh_num_cycles()}


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


def prof_enable(on=True):
    """Turn on the cycle-per-PC profile in run_bench (off by default; adds nothing when off)."""
    _LIB.osh_prof_enable(1 if on else 0)


def prof_reset():
    """Clear the accumulated cycle-per-PC tallies (call before the run(s) to profile)."""
    _LIB.osh_prof_reset()


def prof_data():
    """The accumulated profile as a list of cycle tallies, one per even PC (index i = PC 2*i)."""
    n = _LIB.osh_prof_slots()
    return list(ctypes.cast(_LIB.osh_prof_data(), ctypes.POINTER(ctypes.c_uint32 * n)).contents)


def psg_writes():
    """(reg, val) YM2149 writes captured during the most recent ``run()``, in order.

    ``run()`` resets the capture each call, so this is exactly that call's PSG traffic —
    one VBL frame's worth when ``run()`` drove the sound driver's ``REFRESH``.
    """
    n = _LIB.osh_psg_count()
    regs, vals = _LIB.osh_psg_regs(), _LIB.osh_psg_vals()
    return [(regs[i], vals[i]) for i in range(n)]


def heap_overlaps_program():
    """Does the modeled Malloc heap sit inside the loaded program?

    If so, any block the model hands out lands ON TOP of the program's own code/data.
    ``loader.PROGRAM_END`` is None until ``load_image()`` has run — no program is loaded then, so
    there is nothing a block could overwrite.
    """
    return loader.PROGRAM_END is not None and OS_HEAP_BASE < loader.PROGRAM_END


def _vet_no_malloc_over_program(malloc_calls):
    """Reject a run that served a Malloc from a modeled heap overlapping the program — a FALSE GREEN.

    Reachable only under the ``tos_malloc_unused`` waiver (see harness._vet_os_memory_map), which
    claims the game issues no GEMDOS Malloc. If that claim is wrong the diff does not merely become
    unreliable, it becomes actively misleading, so the claim is re-tested after every run rather
    than trusted once. It lives here, not in harness.differential(), so that a bare ``emu.run()``
    (an oracle-only test, the poison re-run inside harness._attribution_check) is covered too.

    ``malloc_calls`` counts SERVICED Malloc traps rather than looking at the bump pointer: a
    Malloc whose rounded size is 0 — canonically ``Malloc(-1)``, GEMDOS's "how big is the largest
    free block?" query — is fully serviced and returns a block at OS_HEAP_BASE without moving the
    pointer, so a pointer test would let exactly that case through.
    """
    if not (malloc_calls and heap_overlaps_program()):
        return
    cfg = project.current()
    raise AssertionError(
        f"the oracle served {malloc_calls} GEMDOS Malloc call(s) while OS_HEAP_BASE "
        f"({OS_HEAP_BASE:#x}) lies inside {cfg.name}'s program, which ends at "
        f"{loader.PROGRAM_END:#x}. The block was handed out ON TOP of the program's own code/data "
        f"— and the candidate mirrors the same OS_HEAP_BASE by convention, so BOTH sides scribble "
        f"the same bytes over the same program bytes and the diff comes back clean while proving "
        f"nothing. A green result on this run is not evidence of anything. {cfg.name}'s "
        f"`tos_malloc_unused = true` in {cfg.dir / project.CONFIG_NAME} is therefore false: drop it "
        f"and move OS_HEAP_BASE above the program (include/os.h + its mirror in emu.py), or lower "
        f"load_base.")


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
    Buf = ctypes.c_uint8 * loader.IMAGE_SIZE
    buf = Buf.from_buffer(mem)

    dregs = (ctypes.c_uint32 * 8)(*[regs.get(n, 0) & 0xFFFFFFFF for n in _DREG_NAMES])
    aregs = (ctypes.c_uint32 * 8)(*[regs.get(n, 0) & 0xFFFFFFFF for n in _AREG_NAMES])
    out = (ctypes.c_uint32 * 4)()

    reached = _LIB.osh_run(buf, loader.IMAGE_SIZE, entry & 0xFFFFFFFF, dregs, aregs,
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
    out_regs["heap"] = _LIB.osh_heap()       # Malloc bump pointer at the end of the run (diagnostics)
    out_regs["malloc_calls"] = _LIB.osh_malloc_count()   # serviced GEMDOS Malloc traps this run
    out_regs["ninsns"] = _LIB.osh_num_insns()  # instructions executed (perf profiling)
    out_regs["cycles"] = _LIB.osh_num_cycles()  # 68000 clock cycles executed (perf profiling)
    dn, dargs = _LIB.osh_dosound_count(), _LIB.osh_dosound_args()
    out_regs["dosound"] = [dargs[i] for i in range(dn)]  # ordered XBIOS Dosound(A0) list pointers

    _vet_no_malloc_over_program(out_regs["malloc_calls"])
    return mem, writes, out_regs