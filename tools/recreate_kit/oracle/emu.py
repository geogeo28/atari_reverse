"""Oracle: execute one function of the program under test under Musashi's 68000 core (via liboracle.so).

Ground truth for the differential test. Same interface the rest of the harness expects:
``run(image, entry, regs) -> (final_image, writes, out_regs)``. The backend is the MAME
68000 core (kstenerud/Musashi), which is faithful to real 68000 behavior — unlike
Unicorn's ColdFire-derived core, which mis-handles byte memory read-modify-write.
"""
import ctypes
from pathlib import Path

import loader   # bound by recreate_kit.project.load() before this module is first imported
from recreate_kit import os_map    # the poked-input block + the pure overlap arithmetic below
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

# What a run REPORTS BACK, in shim.c's OSH_OUT_REGS order: every data register, then A0..A6. A7 is
# excluded because it is the HARNESS's stack pointer, not the function's — run() forces it to
# STACK_TOP on entry and the rts pops the sentinel frame back off it, so its final value states the
# harness's own convention rather than anything the function computed; ``min_a7`` below is the one
# fact about it a case can use. Pinned against shim.c by test/test_reported_regs.py.
REPORTED_REGS = _DREG_NAMES + _AREG_NAMES[:-1]

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
# The newest oracle export. liboracle.so is SHARED by every project and is rebuilt only by kit.mk's
# $(ORACLE) rule, which several consumers never reach (projects/buggyboy/remaster's Makefile, the
# standalone gen_image/bench/smoke scripts) — so a stale build is a normal state to be in, and a bare
# ctypes dlsym failure names neither the file nor the fix. Say both, the way harness.py does for the
# candidate's required ABI.
if not hasattr(_LIB, "osh_poked_input_calls"):
    raise RuntimeError(
        "the shared oracle is stale: liboracle.so exports no osh_poked_input_calls, which "
        "emu.run() needs to reject a run whose traps read the harness-poked input block over a "
        "project's own program (see _vet_no_poked_input_read). Rebuild it with "
        "`make -C tools/recreate_kit oracle` — or from any project, `make oracle`.")
_LIB.osh_poked_input_calls.restype = ctypes.c_uint32
# The newest export, and the one whose absence is not merely a missing feature: run() sizes the
# out_regs buffer from REPORTED_REGS above, so an .so built from a shim.c that reports a DIFFERENT
# number of registers either leaves slots unwritten (silent zeros where a case expects an output) or
# writes past the end of this process's buffer. Ask the .so rather than assume, for the same reason
# the guard above does — a stale liboracle.so is a normal state to be in.
if not hasattr(_LIB, "osh_out_regs"):
    raise RuntimeError(
        "the shared oracle is stale: liboracle.so exports no osh_out_regs, so it predates the "
        "oracle reporting the full movem register set (d0-d7/a0-a6) and would leave every register "
        "past d1/a1 unwritten. Rebuild it with `make -C tools/recreate_kit oracle` — or from any "
        "project, `make oracle`.")
_LIB.osh_out_regs.restype = ctypes.c_uint32
if _LIB.osh_out_regs() != len(REPORTED_REGS):
    raise RuntimeError(
        f"liboracle.so reports {_LIB.osh_out_regs()} registers per run but this emu.py names "
        f"{len(REPORTED_REGS)} ({', '.join(REPORTED_REGS)}) and sizes its buffer to match — the "
        f"shim and its Python mirror have drifted, and the run would read unwritten slots or "
        f"overrun the buffer. Rebuild with `make -C tools/recreate_kit oracle`.")
_LIB.osh_num_insns.restype = ctypes.c_uint32
_LIB.osh_num_cycles.restype = ctypes.c_uint64
_u8p = ctypes.POINTER(ctypes.c_uint8)
_LIB.osh_psg_count.restype = ctypes.c_uint32
_LIB.osh_psg_regs.restype = _u8p
_LIB.osh_psg_vals.restype = _u8p
_LIB.osh_dosound_count.restype = ctypes.c_uint32
_LIB.osh_dosound_args.restype = _u32p
_LIB.osh_psg_mixed_paths.restype = ctypes.c_int
_LIB.osh_psg_unmodeled.restype = ctypes.c_uint32
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


def poked_input_overlaps_program():
    """Does the harness-poked input block sit inside the loaded program? (os_map's predicate.)"""
    return os_map.poked_input_overlaps_program(loader.LOAD_BASE, loader.PROGRAM_END)


def _vet_no_poked_input_read(poked_input_calls):
    """Reject a run in which a trap reached poked input that lies inside the program — a FALSE GREEN.

    Reachable only under the ``tos_poked_input_unused`` waiver (see harness._vet_os_memory_map),
    which claims the game reads NONE of that state — no Bconstat/Bconin/Crawio, no Random, no
    Giaccess, no Kbdvbase. That claim is what lets the program cover the block, so it is re-tested
    after every run rather than trusted once, exactly as the Malloc waiver's is above.

    Without it the claim would only ever be checked at the point a TEST stages a poke, which is a
    different claim: the game's own reads would go unwatched. They are the dangerous half. A
    ``Bconin`` in code that exists only after a depack reads the block — i.e. the program's own
    instruction bytes, which are nonzero — so the model reports a keystroke pending, hands back four
    bytes of the game's code as the key, and CLEARS four bytes of code at OS_CON_PENDING. Both sides
    do it identically from the same os.h, so the diff is clean and the case proves nothing.

    ``poked_input_calls`` counts SERVICED traps rather than looking at the block's bytes: Bconstat
    and a Giaccess read leave it untouched, and a poked-input read is no less fabricated for being
    read-only. It counts the WRITING traps too — a Giaccess write stores into the register file,
    Bconin clears the pending flag — because under the overlap those land on the game's code, which
    is the worse half of the same hazard.
    """
    if not (poked_input_calls and poked_input_overlaps_program()):
        return
    cfg = project.current()
    raise AssertionError(
        f"the oracle served {poked_input_calls} trap(s) reaching the harness-poked input block "
        f"({os_map.OS_CON_PENDING:#x}..{os_map.OS_POKE_BLOCK_END - 1:#x}) while that block lies "
        f"inside {cfg.name}'s program, which loads at {loader.LOAD_BASE:#x} and ends at "
        f"{loader.PROGRAM_END:#x}. The trap read — and Bconin/Crawio then cleared — the game's own "
        f"code, and the candidate mirrors the same addresses through os.h, so BOTH sides mangle the "
        f"same bytes and the diff comes back clean while proving nothing. {cfg.name}'s "
        f"`tos_poked_input_unused = true` in {cfg.dir / project.CONFIG_NAME} is therefore false: "
        f"drop it and move the block (include/os.h + its mirror in recreate_kit/os_map.py) above "
        f"the program, or raise load_base.")


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
    code stored (stack writes included). ``out_regs`` holds every register the run leaves —
    ``REPORTED_REGS``, i.e. d0..d7 and a0..a6 at return (A7 is the harness's own; ``min_a7`` reports
    the only thing about it a case can use) — plus the ledger entries appended below.
    """
    regs = regs or {}
    mem = bytearray(image)
    Buf = ctypes.c_uint8 * loader.IMAGE_SIZE
    buf = Buf.from_buffer(mem)

    dregs = (ctypes.c_uint32 * 8)(*[regs.get(n, 0) & 0xFFFFFFFF for n in _DREG_NAMES])
    aregs = (ctypes.c_uint32 * 8)(*[regs.get(n, 0) & 0xFFFFFFFF for n in _AREG_NAMES])
    out = (ctypes.c_uint32 * len(REPORTED_REGS))()

    reached = _LIB.osh_run(buf, loader.IMAGE_SIZE, entry & 0xFFFFFFFF, dregs, aregs,
                           STACK_TOP, SENTINEL, stop_pc & 0xFFFFFFFF, max_insns, out)
    if not reached:
        where = f"checkpoint {stop_pc:#x}" if stop_pc else "rts"
        raise RuntimeError(f"function @ {entry:#x} did not reach {where} within {max_insns} "
                           f"instructions; final memory is mid-execution, not trustworthy")
    # Three independent reasons a run's result may be fabricated. They are reported TOGETHER rather
    # than as a first-match: a run can hit more than one, and naming only the first sends the reader
    # off to fix that one and hit the identical message again. The two PSG causes are named
    # specifically because otherwise they read as a puzzling "unmodeled OS call" on a run whose
    # every trap WAS modeled. See tools/recreate_kit/TRAP_MODEL.md, Phase 3.
    causes = []
    if _LIB.osh_unmodeled():
        causes.append("an OS call (e.g. Bconin with no key staged, an unstaged file, GEM) "
                      "has no model")
    if _LIB.osh_psg_mixed_paths():
        causes.append("it used XBIOS Giaccess AND the PSG ports ($ff8800/$ff8802) directly in one "
                      "run — the modeled register file only sees Giaccess, so a read from it may "
                      "be stale")
    if _LIB.osh_psg_unmodeled():
        causes.append("it accessed the PSG ports ($ff8800/$ff8802) in a way the model cannot serve "
                      "— a READ (the ledger records writes only, so the selected register cannot "
                      "be read back), or an access outside the byte select/data protocol")
    if causes:
        raise RuntimeError(f"function @ {entry:#x} hit unmodeled OS behaviour: "
                           + "; also, ".join(causes)
                           + "; its result is fabricated, not trustworthy")

    n = _LIB.osh_num_writes()
    waddr = _LIB.osh_write_addrs()
    writes = {waddr[i]: mem[waddr[i]] for i in range(n)}
    out_regs = dict(zip(REPORTED_REGS, out))
    out_regs["min_a7"] = _LIB.osh_min_a7()   # deepest stack pointer; used to vet diff exclude bands
    out_regs["heap"] = _LIB.osh_heap()       # Malloc bump pointer at the end of the run (diagnostics)
    out_regs["malloc_calls"] = _LIB.osh_malloc_count()   # serviced GEMDOS Malloc traps this run
    out_regs["poked_input_calls"] = _LIB.osh_poked_input_calls()  # ...and traps reading poked input
    out_regs["ninsns"] = _LIB.osh_num_insns()  # instructions executed (perf profiling)
    out_regs["cycles"] = _LIB.osh_num_cycles()  # 68000 clock cycles executed (perf profiling)
    dn, dargs = _LIB.osh_dosound_count(), _LIB.osh_dosound_args()
    out_regs["dosound"] = [dargs[i] for i in range(dn)]  # ordered XBIOS Dosound(A0) list pointers

    _vet_no_malloc_over_program(out_regs["malloc_calls"])
    _vet_no_poked_input_read(out_regs["poked_input_calls"])
    return mem, writes, out_regs