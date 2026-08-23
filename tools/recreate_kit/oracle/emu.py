"""Oracle: execute one function of the program under test under Musashi's 68000 core (via liboracle.so).

Ground truth for the differential test. Same interface the rest of the harness expects:
``run(image, entry, regs) -> (final_image, writes, out_regs)``. The backend is the MAME
68000 core (kstenerud/Musashi), which is faithful to real 68000 behavior — unlike
Unicorn's ColdFire-derived core, which mis-handles byte memory read-modify-write.
"""
import contextlib
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


def _stale_oracle(sym, why):
    """The error for a liboracle.so that predates ``sym``. ``why`` says what is lost without it.

    liboracle.so is SHARED by every project and is rebuilt only by kit.mk's $(ORACLE) rule, which
    several consumers never reach (projects/buggyboy/remaster's Makefile, the standalone
    gen_image/bench/smoke scripts) — so a stale build is a normal state to be in, and a bare ctypes
    dlsym failure names neither the file nor the fix. Say both, the way harness.py does for the
    candidate's required ABI. One spelling, so every site names the same rebuild command.
    """
    return RuntimeError(
        f"the shared oracle is stale: liboracle.so exports no {sym}, {why} Rebuild it with "
        f"`make -C tools/recreate_kit oracle` — or from any project, `make oracle`.")


_u32p = ctypes.POINTER(ctypes.c_uint32)
_LIB.osh_run.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.c_uint32,
                         _u32p, _u32p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                         ctypes.c_uint32, _u32p]
_LIB.osh_run.restype = ctypes.c_int
_LIB.osh_num_writes.restype = ctypes.c_uint32
# shim.c's MAX_WRITES, mirrored — and CROSS-CHECKED against the .so below, the way OSH_OUT_REGS is.
# `logw` SATURATES rather than wrapping (`if (g_wn < MAX_WRITES) g_waddr[g_wn++] = a;`), so
# `osh_num_writes() >= MAX_WRITES` is the ledger sitting at its cap with every further event
# dropped uncounted. run() reports that per run; harness.differential refuses a comparison made
# against such a set. A drift here would be silent in the worst direction — a mirror set too HIGH
# disarms both — which is exactly why it is asked of the .so rather than kept by hand.
MAX_WRITES = 1 << 22
if not hasattr(_LIB, "osh_max_writes"):
    raise _stale_oracle(
        "osh_max_writes",
        "so the write ledger's cap cannot be read back, and a run whose write set was truncated at "
        "it could not be told from one that fit.")
_LIB.osh_max_writes.restype = ctypes.c_uint32
if _LIB.osh_max_writes() != MAX_WRITES:
    raise RuntimeError(
        f"liboracle.so caps its write ledger at {_LIB.osh_max_writes()} events but this emu.py "
        f"mirrors {MAX_WRITES} — the shim and its Python mirror have drifted, and a truncated write "
        f"set would be reported as a complete one. Rebuild with `make -C tools/recreate_kit oracle`.")
_LIB.osh_write_addrs.restype = _u32p
_LIB.osh_unmodeled.restype = ctypes.c_uint32
_LIB.osh_min_a7.restype = ctypes.c_uint32
_LIB.osh_heap.restype = ctypes.c_uint32
_LIB.osh_malloc_count.restype = ctypes.c_uint32
if not hasattr(_LIB, "osh_poked_input_calls"):
    raise _stale_oracle(
        "osh_poked_input_calls",
        "which emu.run() needs to reject a run whose traps read the harness-poked input block over "
        "a project's own program (see _vet_no_poked_input_read).")
_LIB.osh_poked_input_calls.restype = ctypes.c_uint32
# This one's absence is not merely a missing feature: run() sizes the out_regs buffer from
# REPORTED_REGS above, so an .so built from a shim.c that reports a DIFFERENT number of registers
# either leaves slots unwritten (silent zeros where a case expects an output) or writes past the end
# of this process's buffer. Ask the .so rather than assume.
if not hasattr(_LIB, "osh_out_regs"):
    raise _stale_oracle(
        "osh_out_regs",
        "so it predates the oracle reporting the full movem register set (d0-d7/a0-a6) and would "
        "leave every register past d1/a1 unwritten.")
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
# Required, not optional: without it a run whose PSG traffic overflowed the ledger reports a
# truncated stream as a complete one, which is the whole hazard the counter closes (shim.c
# g_psg_dropped). run() names it as a cause, so a missing symbol would silently reopen it.
if not hasattr(_LIB, "osh_psg_dropped"):
    raise _stale_oracle(
        "osh_psg_dropped",
        "so a run whose PSG writes overflowed the ledger cannot be told from one that fit, and "
        "run() would report a truncated register stream as a complete capture.")
_LIB.osh_psg_dropped.restype = ctypes.c_uint32
_LIB.osh_dosound_count.restype = ctypes.c_uint32
_LIB.osh_dosound_args.restype = _u32p
_LIB.osh_psg_mixed_paths.restype = ctypes.c_int
_LIB.osh_psg_unmodeled.restype = ctypes.c_uint32
# The seeded PSG read model (TRAP_MODEL.md, Phase 6). Required, not probed: run() installs the seed
# before EVERY run — an empty one included, so a seed cannot leak from the previous run — and reads
# the unseeded-read refusal mask afterwards. An .so without it does not merely lack a feature; it
# would refuse every direct $ff8800 read the way it did before the model existed, while this file
# reported the case as seeded.
_PSG_MODEL_ABI = ("osh_psg_seed", "osh_psg_file", "osh_psg_known", "osh_psg_unseeded",
                  "osh_psg_no_select", "osh_psg_direct", "osh_psg_giaccess", "osh_psg_kinds",
                  "osh_psg_nregs")
_missing_psg_model = [sym for sym in _PSG_MODEL_ABI if not hasattr(_LIB, sym)]
if _missing_psg_model:
    # All six or none, and named together rather than one at a time: they ship in one shim.c, and a
    # bare ctypes AttributeError on the second of them would name neither the file nor the rebuild.
    raise _stale_oracle(
        "/".join(_missing_psg_model),
        "so it predates the seeded PSG read model: a direct $ff8800 read-back would be refused "
        "however the case seeds it, and no read-modify-write of the chip could be verified.")
_LIB.osh_psg_seed.argtypes = [_u8p, ctypes.c_uint32]
_LIB.osh_psg_file.restype = _u8p
_LIB.osh_psg_known.restype = ctypes.c_uint32
_LIB.osh_psg_unseeded.restype = ctypes.c_uint32
_LIB.osh_psg_no_select.restype = ctypes.c_uint32
_LIB.osh_psg_direct.restype = ctypes.c_uint32
_LIB.osh_psg_giaccess.restype = ctypes.c_uint32
_LIB.osh_psg_kinds.restype = _u8p
_LIB.osh_psg_nregs.restype = ctypes.c_uint32
# Bound ONCE, from the .so rather than from a second copy of the count here, so a shim.c that resized
# the file cannot leave this file reading past it.
PSG_NREGS = _LIB.osh_psg_nregs()
_PsgFileP = ctypes.POINTER(ctypes.c_uint8 * PSG_NREGS)
# The seeded HARDWARE read model (TRAP_MODEL.md, Phase 7). Required, not probed, for the seeded PSG
# model's reason: run() installs the seed before EVERY run — an empty one included, so a seed cannot
# leak from the previous run. An .so without these would answer every modeled hardware read with a
# silent 0 while this file reported the case as having declared them, which is precisely the false
# green the model closes.
_HW_MODEL_ABI = ("osh_hw_seed", "osh_hw_file", "osh_hw_known", "osh_hw_unseeded", "osh_hw_stale",
                 "osh_hw_reread", "osh_hw_volatile", "osh_hw_capture_profile_known",
                 "osh_hw_wide", "osh_hw_count", "osh_hw_log_slots", "osh_hw_log_vals",
                 "osh_hw_dropped", "osh_hw_nslots", "osh_hw_addr_table", "osh_hw_capture_profile")
_missing_hw_model = [sym for sym in _HW_MODEL_ABI if not hasattr(_LIB, sym)]
if _missing_hw_model:
    # Named together rather than one at a time, for _PSG_MODEL_ABI's reason: they ship in one
    # shim.c, and a bare ctypes AttributeError on the second would name neither the file nor the
    # rebuild.
    raise _stale_oracle(
        "/".join(_missing_hw_model),
        "so it predates the seeded hardware read model: $fffa01 and $ff820a would answer a silent "
        "0 on both sides, and a branch steered by one could not be verified at all.")
_LIB.osh_hw_seed.argtypes = [_u8p, ctypes.c_uint32]
_LIB.osh_hw_file.restype = _u8p
_LIB.osh_hw_known.restype = ctypes.c_uint32
_LIB.osh_hw_unseeded.restype = ctypes.c_uint32
_LIB.osh_hw_stale.restype = ctypes.c_uint32
_LIB.osh_hw_wide.restype = ctypes.c_uint32
_LIB.osh_hw_count.restype = ctypes.c_uint32
_LIB.osh_hw_log_slots.restype = _u8p
_LIB.osh_hw_log_vals.restype = _u8p
_LIB.osh_hw_dropped.restype = ctypes.c_uint32
_LIB.osh_hw_nslots.restype = ctypes.c_uint32
_LIB.osh_hw_addr_table.restype = _u32p
_LIB.osh_hw_capture_profile.restype = _u8p
_LIB.osh_hw_capture_profile_known.restype = ctypes.c_uint32
_LIB.osh_hw_reread.restype = ctypes.c_uint32
_LIB.osh_hw_volatile.restype = ctypes.c_uint32
# The modeled set, read from the .so rather than kept as a second copy of os.h's table here — so a
# shim.c that adds an address cannot leave this file naming the old set (PSG_NREGS's argument).
HW_NSLOTS = _LIB.osh_hw_nslots()
HW_ADDRS = tuple(_LIB.osh_hw_addr_table()[slot] for slot in range(HW_NSLOTS))
_HwFileP = ctypes.POINTER(ctypes.c_uint8 * HW_NSLOTS)
# The SCHEDULED WRITE model (TRAP_MODEL.md, Phase 8). Required, not probed, for the seeded models'
# reason: run() installs the schedule before EVERY run — an empty one included, so one case's agent
# cannot fire inside the next — and reads back what fired. An .so without it would run a wait loop
# to the instruction cap and report "did not reach rts", naming neither the schedule nor the fact
# that it was silently dropped.
_SCHED_ABI = ("osh_schedule", "osh_sched_count", "osh_sched_applied", "osh_sched_arrivals",
              "osh_sched_refused", "osh_sched_max", "osh_sched_fields",
              "osh_sched_site_max", "osh_sched_site_count", "osh_sched_site_arrivals")
_missing_sched = [sym for sym in _SCHED_ABI if not hasattr(_LIB, sym)]
if _missing_sched:
    raise _stale_oracle(
        "/".join(_missing_sched),
        "so it predates the scheduled-write model: a routine that busy-waits on a byte an interrupt "
        "supplies would spin to the instruction cap, with the declared store never made.")
_LIB.osh_schedule.argtypes = [_u32p, ctypes.c_uint32, _u32p, ctypes.c_uint32]
_LIB.osh_sched_site_arrivals.argtypes = [ctypes.c_uint32]
for _sym in ("osh_sched_count", "osh_sched_applied", "osh_sched_arrivals", "osh_sched_refused",
             "osh_sched_max", "osh_sched_fields", "osh_sched_site_max", "osh_sched_site_count",
             "osh_sched_site_arrivals"):
    getattr(_LIB, _sym).restype = ctypes.c_uint32
# Read from the .so rather than restated here (PSG_NREGS's argument): a shim that resized the table
# or the entry cannot leave this file encoding the old shape.
SCHED_MAX = _LIB.osh_sched_max()
SCHED_FIELDS = _LIB.osh_sched_fields()
SCHED_SITE_MAX = _LIB.osh_sched_site_max()
# The two trigger kinds. Mirrored from os.h rather than read back from the .so, unlike the two sizes
# above, because they are an ENCODING the CASES are written against rather than a table size — and
# test/test_os_memory_map.py pins the pair equal to os.h, which is what a mirror costs.
OS_SCHED_AT_PC = 0
OS_SCHED_AT_INSN = 1
# ...and the field order of one flattened entry, for the two consumers that read one back rather
# than build one (harness._vet_poison_is_attributable). os.h owns the numbers.
OS_SCHED_F_KIND, OS_SCHED_F_TRIGGER, OS_SCHED_F_NTH = 0, 1, 2
OS_SCHED_F_ADDR, OS_SCHED_F_WIDTH, OS_SCHED_F_VALUE = 3, 4, 5
SCHED_WIDTHS = (1, 2, 4)          # os_sched_store carries a byte, a word and a longword

_LIB.osh_cov_enable.argtypes = [ctypes.c_int]
_LIB.osh_cov_visited.argtypes = [ctypes.c_uint32]
_LIB.osh_cov_visited.restype = ctypes.c_int
_LIB.osh_cov_data.restype = _u8p
_LIB.osh_cov_bytes.restype = ctypes.c_uint32
_LIB.osh_prof_enable.argtypes = [ctypes.c_int]
_LIB.osh_prof_data.restype = _u32p
_LIB.osh_prof_slots.restype = ctypes.c_uint32
# The opt-in audio-capture mode (see audio_capture below). No probe: the mode is a documented
# RELAXATION of the seeded read model, and ships in the same shim.c as the symbols required above —
# so an .so that has those and not these does not exist, and a `if _HAS_AUDIO_CAPTURE:` branch here
# would be a claim about a build that cannot occur, dead in every direction a test could push it.
_LIB.osh_audio_capture.argtypes = [ctypes.c_int]
_LIB.osh_audio_capture_on.restype = ctypes.c_int

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


# How many `audio_capturing()` blocks are open. The mode is an oracle-global toggle, so "is it
# armed?" cannot say whether THIS caller meant to arm it — and a run made under someone else's
# capture reads answers shim.c invented (see run()'s one-sided-capture guard). The context manager
# is the one thing that can say "yes, deliberately", so it is what run() asks. A depth rather than a
# bool so the bookkeeping stays exact however the blocks nest.
_capture_scopes = 0


def audio_capture(on):
    """Arm or disarm the oracle's opt-in AUDIO-CAPTURE mode. **Off is the default and the
    differential's contract; this is never valid for a differential run** — ``harness.differential``
    refuses one outright while it is armed.

    The argument is required: at a call site "audio_capture()" would read as *query* rather than as
    *arm*, and arming this by accident is the failure mode the whole design is shaped around.

    With it on, the seeded PSG read model is RELAXED and two machine-profile bytes are served, so an
    extraction tool can drive a game's music replayer tick by tick and read the YM2149 register
    stream out of ``psg_writes()``:

      * a BYTE read of ``$ff8800`` returns the modeled register file's currently latched register
        even when nothing declared or wrote it, answering **0** where the default model refuses (see
        ``run``'s ``psg_seed``). A capture cannot declare a seed per tick and a refusal would end it
        at the replayer's first mixer read-back — but that 0 is this mode's own invention, and is
        the reason a differential may not run under it. The register file also SPANS runs here,
        where the default model re-seeds it per run.
      * a BYTE read of ``$fffa01`` (MFP GPIP) or ``$ff820a`` (shifter sync) reports the 50 Hz
        colour-ST tempo profile a replayer keys on: GPIP bit 7 set, sync bit 1 set. Both read 0
        when no case declares them, and 0/0 is the *monochrome* profile — a replayer taking it would
        render every song at the wrong rate, silently. Only those two bits are modeled (plus the two
        idle, active-low interrupt lines that share the GPIP byte); the rest of each byte is a
        fabricated zero, which is why nothing wider is served — see below. Since Phase 7 the mode
        serves them by INSTALLING A SEED over the same model a case seeds (``hw_capture_profile()``
        is that seed), so this is one code path rather than a second answer beside it — and passing
        a ``hw_seed`` under the mode is refused, since the profile would silently win.

    WHAT IS STILL REFUSED, in this mode exactly as out of it — every one of these counts unmodeled
    and sinks the run in ``run()``:

      * any read of the PSG data port ``$ff8802`` (on real hardware it is not the read-back port),
        of an odd alias such as ``$ff8801``, or of any other address in the chip's ``$ff88xx`` block;
      * any word- or long-wide access to the PSG block, in either direction;
      * a word- or long-wide read taking in ``$fffa01`` or ``$ff820a``, which would fabricate the
        neighbouring MFP/shifter registers as 0 (this one is refused only WHILE the mode is armed;
        off it, it is an ordinary off-image read answered 0, as it has always been).

    Why opt-in: each served answer is the MODEL's invention rather than the game's data, so a
    reconstruction verified against one would be verified against ``shim.c``. Refusing them is the
    differential's whole point (see ``TRAP_MODEL.md``), which is why the mode changes nothing at all
    while it is off.

    CONTRACT. The register file and the select latch both **persist across ``run()`` calls** while
    the mode is on — an extractor calls ``run()`` once per VBL tick, feeding each run's image back
    in, and tick N's read-back must see tick N-1's writes, exactly as the chip's own latch and
    registers survive a VBL. Both are cleared by ``audio_reset()``, and mid-capture by nothing else,
    so arming is IDEMPOTENT: re-arming an already-armed capture keeps it. Arming from OFF *does*
    clear them — the register file is shared with the differential's seeded model, so a capture armed
    bare would otherwise inherit whatever the last ordinary ``run()`` left in it.
    ``psg_writes()`` keeps its per-run scope unchanged: it is still exactly this tick's register
    traffic, which is the extractor's data feed. ``audio_capturing()`` is the two together, and is
    also what ``run()`` requires before it will run under the mode at all.
    """
    _LIB.osh_audio_capture(1 if on else 0)


def audio_reset():
    """Clear the modeled YM2149 register file **and the select latch** — where a new capture begins.

    Split from ``audio_capture(True)`` for the reason ``cov_reset`` is split from ``cov_enable``: an
    arming that also cleared could not be issued defensively mid-capture without destroying it.

    The latch goes with the file because it is the other half of the same chip state a capture
    carries across runs: clearing one and keeping the other would start the next capture selecting
    the register the previous one last named, and a bare data write would land there.
    """
    _LIB.osh_audio_reset()


def audio_capture_on():
    """Is the audio-capture mode armed?"""
    return bool(_LIB.osh_audio_capture_on())


@contextlib.contextmanager
def audio_capturing():
    """Arm audio capture over a block, on a freshly cleared register file, and disarm on the way out.

    The mode is PROCESS-global state in the shared oracle, so a caller that left it armed would
    change every later user of the same process — and under ``pytest -n auto`` which those are is not
    stable between runs. This is the shape that cannot leak it, and the one every case should use.

    It is also the only way to declare that a ``run()`` under the mode is DELIBERATE: the toggle
    alone cannot say whose capture it is, so ``run()`` refuses a run made while the mode is armed
    from outside a block like this one.
    """
    global _capture_scopes
    audio_capture(True)
    audio_reset()
    _capture_scopes += 1
    try:
        yield
    finally:
        _capture_scopes -= 1
        audio_capture(False)


def psg_file():
    """The modeled YM2149 register file a ``$ff8800`` read-back answers from, as ``bytes``.

    Off the audio-capture mode this is per-run state: ``run()`` starts it from the case's
    ``psg_seed`` and the run's own ``$ff8802`` writes update it, so this is the chip's contents at
    the end of the last run (also reported as ``out_regs["psg_file"]``, which is what
    ``harness.differential`` compares against the candidate's). Under the mode it is the extractor's
    view of the chip and spans runs until ``audio_reset()``.
    """
    return bytes(ctypes.cast(_LIB.osh_psg_file(), _PsgFileP).contents)


def psg_known():
    """Bitmask of the registers whose contents are known (seeded, or written by the last run).

    A register outside it cannot be read: the model refuses rather than invent what the chip held.
    """
    return _LIB.osh_psg_known()


def psg_seed_bytes(psg_seed):
    """``{register: value}`` -> ``(bytes(PSG_NREGS), known-mask)``: the encoding BOTH sides take.

    One implementation because the two must start from identical contents — ``run()`` installs the
    pair in the oracle, ``harness.differential`` hands the same pair to the candidate's
    ``g_psg_reset``. A register outside the chip's file or a value outside a byte is refused rather
    than masked: either means the case meant something the model would silently change.
    """
    values = bytearray(PSG_NREGS)
    known = 0
    for reg, value in (psg_seed or {}).items():
        if not 0 <= reg < PSG_NREGS:
            raise ValueError(f"YM2149 register {reg} is outside 0..{PSG_NREGS - 1}")
        if not 0 <= value <= 0xFF:
            raise ValueError(f"psg_seed[{reg}] = {value!r} is not a byte")
        values[reg] = value
        known |= 1 << reg
    return bytes(values), known


def hw_seed_bytes(hw_seed):
    """``{address: value}`` -> ``(bytes(HW_NSLOTS), known-mask)``: the encoding BOTH sides take.

    One implementation, for ``psg_seed_bytes``'s reason — ``run()`` installs the pair in the oracle
    and ``harness.differential`` hands the same pair to the candidate's ``g_hw_reset``, so the two
    cannot disagree about what ``{address: byte}`` means. An address outside the modeled set
    (``HW_ADDRS``) or a value outside a byte is refused rather than dropped: a case that declares
    ``$ff8609`` is describing hardware this model does not serve, and silently ignoring it would
    leave the run reading a fabricated 0 while the case says otherwise.
    """
    values = bytearray(HW_NSLOTS)
    known = 0
    for addr, value in (hw_seed or {}).items():
        if addr not in HW_ADDRS:
            raise ValueError(
                f"hw_seed[{addr:#x}] declares an address the seeded hardware model does not serve. "
                f"It models exactly {', '.join(f'{a:#x}' for a in HW_ADDRS)} — every other off-image "
                f"read still answers 0, invisibly. Adding one is a change to os.h's OS_HW_* table on "
                f"both sides, and it belongs with the evidence for what the address really answers "
                f"(TRAP_MODEL.md, Phase 7)")
        if not 0 <= value <= 0xFF:
            raise ValueError(f"hw_seed[{addr:#x}] = {value!r} is not a byte")
        slot = HW_ADDRS.index(addr)
        values[slot] = value
        known |= 1 << slot
    return bytes(values), known


def schedule_entries(schedule):
    """``[{...}]`` -> the flattened uint32 array BOTH sides take (os.h, "SCHEDULED WRITES").

    One implementation, for ``psg_seed_bytes``'s reason: ``run()`` installs it in the oracle and
    ``harness.differential`` hands the SAME array to the candidate's ``g_sched_reset``, so the two
    cannot describe different stores at different moments.

    Each entry is a dict naming its trigger and its store::

        {"pc": 0x64e, "nth": 3, "addr": 0x879, "width": 1, "value": 0x99}
        {"insn": 40,              "addr": 0x879, "width": 1, "value": 0x99}

    ``pc`` fires the store just before the ``nth`` execution of the instruction at that address
    (``nth`` defaults to 1); ``insn`` fires it before the run's Nth instruction (1 = the first) and
    has no candidate equivalent, so a differential refuses one (``harness.differential``). Every field is checked
    rather than masked: a width the model does not carry, a value that does not fit it or a store
    that leaves the image would otherwise be dropped by ``os_sched_store`` at run time, and a
    schedule that silently did nothing reads as a wait loop that simply never ended.
    """
    entries = list(schedule or ())
    if len(entries) > SCHED_MAX:
        raise ValueError(f"a run may schedule at most {SCHED_MAX} write(s) (os.h's OS_SCHED_MAX); "
                         f"this one declares {len(entries)}")
    flat = []
    for i, entry in enumerate(entries):
        unknown = set(entry) - {"pc", "insn", "nth", "addr", "width", "value"}
        if unknown:
            raise ValueError(f"schedule[{i}] carries unknown key(s) {sorted(unknown)}")
        if ("pc" in entry) == ("insn" in entry):
            raise ValueError(f"schedule[{i}] must name exactly one trigger: `pc` (with an optional "
                             f"`nth`) or `insn`")
        nth = entry.get("nth", 1)
        if "insn" in entry and "nth" in entry:
            raise ValueError(f"schedule[{i}] is an `insn` trigger, which fires once at a fixed "
                             f"instruction index — `nth` names an arrival count and applies only to "
                             f"a `pc` trigger")
        if not (isinstance(nth, int) and nth >= 1):
            raise ValueError(f"schedule[{i}]['nth'] = {nth!r} is not an arrival count (1 = the first)")
        if "insn" in entry and not (isinstance(entry["insn"], int) and entry["insn"] >= 1):
            raise ValueError(f"schedule[{i}]['insn'] = {entry['insn']!r} is not an instruction index "
                             f"(1 = the first instruction the run executes)")
        kind = OS_SCHED_AT_PC if "pc" in entry else OS_SCHED_AT_INSN
        trigger = entry.get("pc", entry.get("insn"))
        if kind == OS_SCHED_AT_PC and not (isinstance(trigger, int) and 0 <= trigger < loader.IMAGE_SIZE
                                           and trigger % 2 == 0):
            # A 68000 fetches instructions at EVEN addresses inside the image, so a `pc` that is
            # odd, negative or out of range can never be arrived at. Left unchecked it reaches the
            # oracle as a `ctypes.c_uint32` (a negative silently becomes 0xffff_fffe), the wait runs
            # to the instruction cap, and the diagnostic sends the reader after "the trigger PC is
            # not the instruction the wait re-executes" — which is true and unhelpful.
            raise ValueError(f"schedule[{i}]['pc'] = {trigger!r} is not an even address inside the "
                             f"{loader.IMAGE_SIZE:#x}-byte image, so no run can ever arrive at it")
        for name in ("addr", "width", "value"):
            if name not in entry:
                raise ValueError(f"schedule[{i}] names no `{name}` — an entry is a whole store")
        addr, width, value = entry["addr"], entry["width"], entry["value"]
        if width not in SCHED_WIDTHS:
            raise ValueError(f"schedule[{i}]['width'] = {width!r} is not one of {SCHED_WIDTHS}")
        if not 0 <= value < (1 << (8 * width)):
            raise ValueError(f"schedule[{i}]['value'] = {value:#x} does not fit {width} byte(s)")
        if not (0 <= addr and addr + width <= loader.IMAGE_SIZE):
            raise ValueError(f"schedule[{i}] stores {width} byte(s) at {addr:#x}, outside the "
                             f"{loader.IMAGE_SIZE:#x}-byte image")
        flat += [kind, trigger, nth, addr, width, value]
    return flat


# The empty install, built ONCE. run() re-installs the schedule before every run — an empty one
# included, so a list cannot leak into the next case — and the overwhelming majority of runs have
# nothing to declare, so the common path should allocate nothing. (Measured at ~1.3 us per run
# otherwise, against a ~115 us oracle run, and it repeats up to four times per poisoned case.)
_NO_SCHEDULE = (ctypes.c_uint32 * 1)()


def schedule_array(flat):
    """``flat`` as the uint32 array both sides are handed; the empty one is shared, not rebuilt."""
    return _NO_SCHEDULE if not flat else (ctypes.c_uint32 * len(flat))(*flat)


def wait_site_pcs(schedule, wait_sites):
    """The run's declared WAIT SITES as a tuple of PCs (os.h, "WAIT SITES").

    A site is the address of the instruction at which the ORIGINAL's wait RE-READS the byte it
    spins on — the store lands just before that instruction on both shores — and both shores count
    per site: the oracle its arrivals there, the candidate its ``sched_poll8`` calls naming it. What
    that buys over a run TOTAL is in os.h — with two waits in one run the totals can balance by
    cancellation while the two sides ran different loops.

    ``wait_sites`` defaults to the trigger PCs the schedule names, which is every case with ONE wait
    in it and needs no thought. A case whose run polls at a site NO entry stores on — the shape
    ``flip_screen`` has, where the first wait falls through on a byte the seed already holds — must
    name it, because the candidate's poll there would otherwise be uncounted, and an uncounted poll
    is the hole the sites close (``sched_poll8`` refuses one).
    """
    triggers = [entry["pc"] for entry in (schedule or ()) if "pc" in entry]
    sites = list(dict.fromkeys(triggers if wait_sites is None else wait_sites))
    if wait_sites is not None and len(sites) != len(list(wait_sites)):
        raise ValueError(f"wait_sites names the same PC twice ({[hex(s) for s in wait_sites]}) — a "
                         f"site is one wait, and two counters keyed the same way cannot be compared")
    if len(sites) > SCHED_SITE_MAX:
        raise ValueError(f"a run may declare at most {SCHED_SITE_MAX} wait site(s) (os.h's "
                         f"OS_SCHED_SITE_MAX); this one declares {len(sites)}")
    for site in sites:
        if not (isinstance(site, int) and 0 <= site < loader.IMAGE_SIZE and site % 2 == 0):
            raise ValueError(f"wait site {site!r} is not an even address inside the "
                             f"{loader.IMAGE_SIZE:#x}-byte image, so no run can ever arrive at it")
    missing = [pc for pc in triggers if pc not in sites]
    if missing:
        # Without this the entry reaches the oracle, its site is never counted, and it never comes
        # due — which surfaces as "the wait loop never ended" and points at the routine.
        raise ValueError(f"schedule trigger PC(s) {[hex(pc) for pc in missing]} are not among the "
                         f"declared wait sites {[hex(s) for s in sites]} — an entry fires on ITS "
                         f"SITE's count, so a trigger that is not a site can never come due")
    return tuple(sites)


def _install_schedule(schedule, wait_sites):
    """Install ``schedule`` in the oracle; return ``(flattened entries, the declared sites)``.

    Both go to the candidate too (``harness._seed_candidate_sched``), so the two sides cannot
    describe different stores OR key their counts differently.
    """
    flat = schedule_entries(schedule)
    sites = wait_site_pcs(schedule, wait_sites)
    n = len(flat) // SCHED_FIELDS
    _LIB.osh_schedule(schedule_array(flat), n, schedule_array(list(sites)), len(sites))
    # The shim CLAMPS to OS_SCHED_MAX/OS_SCHED_SITE_MAX and reports what it kept. The encoders above
    # refuse an over-long list, so these can only fire when the two sides disagree about a cap — and
    # a run silently carrying fewer stores or sites than the case declared reads as a wait that
    # never ended.
    if _LIB.osh_sched_count() != n:
        raise RuntimeError(f"the oracle kept {_LIB.osh_sched_count()} of this run's {n} scheduled "
                           f"store(s) — its OS_SCHED_MAX and this file's disagree")
    if _LIB.osh_sched_site_count() != len(sites):
        raise RuntimeError(f"the oracle kept {_LIB.osh_sched_site_count()} of this run's "
                           f"{len(sites)} wait site(s) — its OS_SCHED_SITE_MAX and this file's "
                           f"disagree")
    return flat, sites


def hw_capture_profile():
    """``{address: byte}``: the machine the AUDIO-CAPTURE mode declares (50 Hz colour ST).

    Read from the shim rather than restated here, so a test can pin "the mode serves this" against
    "a case that declares this serves the same" without either side holding a copy of the constants.
    """
    profile = _LIB.osh_hw_capture_profile()
    # FILTERED BY THE MODE'S OWN MASK. The profile array is a designated initializer with a slot
    # per modeled address, so every slot the mask WITHHOLDS holds a fabricated 0 — returning those
    # as if the mode declared them hands a caller a byte the C side never serves, and a case that
    # fed the dict straight back in as a hw_seed would declare a fabrication (shim.c's
    # HW_CAPTURE_PROFILE_KNOWN says why the mask withholds them).
    known = _LIB.osh_hw_capture_profile_known()
    return {addr: profile[slot] for slot, addr in enumerate(HW_ADDRS) if known & (1 << slot)}


def hw_events():
    """The modeled hardware bytes' whole ordered READ stream from the most recent ``run()``.

    A list of ``(address, value)`` in the order the run read them, an UNDECLARED read included (it
    is served 0 and recorded in ``hw_unseeded``). This is the entire observable effect of such a
    read: it touches no image byte, and the branch it steers may leave no trace either, so
    ``harness.differential`` compares this stream against the candidate's (``src/hw.c``).
    """
    n = _LIB.osh_hw_count()
    slots, vals = _LIB.osh_hw_log_slots(), _LIB.osh_hw_log_vals()
    return [(HW_ADDRS[slots[i]], vals[i]) for i in range(n)]


def _hw_addrs_of(mask):
    """The modeled addresses a slot mask names — the shape every hardware refusal reports in."""
    return [addr for slot, addr in enumerate(HW_ADDRS) if mask & (1 << slot)]


def hw_unseeded_addrs():
    """The modeled addresses the last ``run()`` read while nothing had declared them.

    Deliberately NOT a raise: see ``run()``. A bare ``run()`` drives a game's relocator, its Copylock
    and its bootstrap, whose hardware reads are nobody's enumerated list — so the refusal lives in
    ``harness.differential``, where a fabricated byte could produce a false green, and this is what
    it reads.
    """
    return _hw_addrs_of(_LIB.osh_hw_unseeded())


def hw_file():
    """The declared hardware bytes a modeled read is served from, as ``bytes`` indexed by slot."""
    return bytes(ctypes.cast(_LIB.osh_hw_file(), _HwFileP).contents)


def psg_events():
    """The direct path's whole ordered access stream from the most recent ``run()``.

    A list of ``(kind, reg, value)``, ``kind`` being ``os_map.OS_PSG_EVENT_WRITE`` or
    ``OS_PSG_EVENT_READ``; ``value`` is what a write stored, or what a read was served. This — not
    ``psg_writes()`` below — is what ``harness.differential`` compares against the candidate's,
    because a reconstruction that reads the WRONG register still writes the right one: its write
    stream and the register file it leaves are identical to a correct one's, and only the read
    entries separate them.
    """
    n = _LIB.osh_psg_count()
    kinds, regs, vals = _LIB.osh_psg_kinds(), _LIB.osh_psg_regs(), _LIB.osh_psg_vals()
    return [(kinds[i], regs[i], vals[i]) for i in range(n)]


def _psg_write_projection(events):
    """The ``(reg, value)`` writes of an access stream, in order — see ``psg_writes``."""
    return [(reg, value) for kind, reg, value in events
            if kind == os_map.OS_PSG_EVENT_WRITE]


def psg_writes():
    """(reg, val) YM2149 **writes** captured during the most recent ``run()``, in order.

    The write-only projection of ``psg_events()``, and an unchanged contract: it is the audio
    extractor's data feed and every project's ``psg_writes()`` consumer rests on it holding writes
    and nothing else.

    ``run()`` resets the capture each call, so this is exactly that call's PSG traffic —
    one VBL frame's worth when ``run()`` drove the sound driver's ``REFRESH``. It is always the
    WHOLE of that traffic: a run whose accesses overflowed the shim's ledger is rejected by ``run()``
    rather than reported truncated (see ``osh_psg_dropped``).
    """
    return _psg_write_projection(psg_events())


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


def run(image, entry, regs=None, max_insns=200_000, stop_pc=0, psg_seed=None, hw_seed=None,
        schedule=None, wait_sites=None):
    """Run ``entry`` on a copy of ``image``. Return (final_image, writes, out_regs).

    ``regs`` maps register name -> value (e.g. {"a1": 0x1e000}); A7 is forced to STACK_TOP.
    ``stop_pc`` is an optional checkpoint PC: with it set, the run stops when it reaches that
    address instead of only at rts — the way to diff a function that never returns (its final
    memory is trustworthy at the checkpoint). ``writes`` is {addr: byte} for every byte the
    code stored (stack writes included) — and it is INCOMPLETE, silently, on a run that made more
    than ``MAX_WRITES`` write events, which ``out_regs["writes_truncated"]`` is how to find out.
    ``out_regs`` holds every register the run leaves —
    ``REPORTED_REGS``, i.e. d0..d7 and a0..a6 at return (A7 is the harness's own; ``min_a7`` reports
    the only thing about it a case can use) — plus the ledger entries appended below.

    ``psg_seed`` is ``{register: value}``, the contents the case declares the YM2149 held on entry —
    an ordinary test input, exactly like a poked keystroke, and the ONLY way a direct ``$ff8800``
    read-back of a register this run has not written can be served. A read of any other register
    refuses the run and names the registers to declare, because a read-modify-write preserves
    precisely the bits nothing wrote and inventing them is a false green (TRAP_MODEL.md, Phase 6).
    Registers are re-seeded before every run, so a seed never leaks into the next case.

    ``hw_seed`` is ``{address: value}`` over the modeled hardware set (``HW_ADDRS``, built from the
    ``.so``'s own table: the MFP GPIP byte, the shifter's sync byte and its two video-counter
    bytes), the same kind of declared input for a byte that steers a branch — or, for the counter
    pair, one a routine hashes into an arithmetic result (TRAP_MODEL.md, Phase 7). It too is
    re-installed before every run. **An UNDECLARED modeled read does not raise here**, unlike an
    undeclared PSG register: it is served the 0 it has always been served, and reported in
    ``out_regs["hw_unseeded"]`` for ``harness.differential`` to refuse the case on. A bare ``run()``
    drives relocators, Copylock and bootstrap code whose hardware reads are nobody's enumerated
    list, and a false green needs something being verified — which a bare run is not. A SECOND read
    of a VOLATILE address in one run is reported the same way, in ``out_regs["hw_reread"]``: one
    declaration is one byte, and the counter cannot have held it twice.

    ``schedule`` is the list of stores an EXTERNAL AGENT makes while the run is in flight — the ACIA
    interrupt storing a release scancode a busy-wait is spinning on, the VBL bumping a frame counter
    (``schedule_entries`` gives the shape; TRAP_MODEL.md, Phase 8). It too is re-installed before
    every run. An entry that never came due sinks the run: a wait loop whose agent never fired ran
    to the instruction cap, and reporting only "did not reach rts" would name the symptom.

    ``wait_sites`` is the list of PCs at which this run BUSY-WAITS, and it defaults to the trigger
    PCs the schedule names — which is right for every run with one wait in it. Arrivals are counted
    per site, not per run, so that ``harness.differential`` can compare them against the candidate's
    polls wait by wait; a run with a second wait the schedule does not store on must name it here or
    that wait goes uncounted (os.h, "WAIT SITES", has what a run TOTAL loses).
    """
    regs = regs or {}
    if audio_capture_on():
        # ONE-SIDED CAPTURE. The mode is oracle-global, so a run can be made under someone else's
        # capture — an extractor in the same process, a block that raised on its way out — and every
        # read it answers is then shim.c's invention rather than the game's data. `audio_capturing()`
        # is the only thing that can say the run MEANT to be there, so a run outside one is refused
        # rather than served fabricated bytes it never asked for. (harness.differential's
        # _vet_audio_capture_off is the same refusal one level up; this one also covers the direct
        # emu.run callers, which is most of a project's PSG cases.)
        if not _capture_scopes:
            raise RuntimeError(
                f"function @ {entry:#x} was run while the AUDIO-CAPTURE mode is armed, but this run "
                f"did not opt into it. Under the mode a $ff8800 read of a register nothing declared "
                f"is answered 0 and the register file spans runs, so the result is the shim's "
                f"invention — valid for an extractor reading the ORIGINAL's register stream, never "
                f"for anything being verified. Scope the capture with `with emu.audio_capturing():` "
                f"if this run is part of one, or disarm it (emu.audio_capture(False)) — most likely "
                f"an earlier block left it armed.")
        if psg_seed is not None:
            raise RuntimeError(
                "a psg_seed was passed while the audio-capture mode is armed. The two make opposite "
                "claims about an unknown register — the seeded model refuses to read one, the "
                "capture mode serves it as 0 — and the capture's register file spans runs, so the "
                "seed would be ignored. Disarm the mode (emu.audio_capture(False), or scope it with "
                "`with emu.audio_capturing():`) or drop the seed.")
        if hw_seed is not None:
            raise RuntimeError(
                "a hw_seed was passed while the audio-capture mode is armed. The mode DECLARES the "
                "modeled hardware bytes itself — the 50 Hz colour-ST profile a replayer picks its "
                "tempo from — and installs that profile over this seed, so the case's declaration "
                "would be silently ignored (emu.hw_capture_profile() is what the run would really "
                "read). Disarm the mode (emu.audio_capture(False), or scope it with "
                "`with emu.audio_capturing():`) or drop the seed.")
    # Deliberately unconditional, seed or none: leaving the previous run's seed installed would make
    # a case that declares nothing readable through another case's declaration, under -n auto
    # unpredictably. (Under audio capture the shim ignores it — the file spans runs there by contract
    # — which is why passing one under the mode is refused outright, just above.)
    seed_values, seed_known = psg_seed_bytes(psg_seed)
    _LIB.osh_psg_seed((ctypes.c_uint8 * PSG_NREGS)(*seed_values), seed_known)
    # ...and the modeled hardware bytes, unconditionally for the same reason (under audio capture the
    # shim installs its own profile over this, which is why passing one under the mode is refused).
    hw_values, hw_known = hw_seed_bytes(hw_seed)
    _LIB.osh_hw_seed((ctypes.c_uint8 * HW_NSLOTS)(*hw_values), hw_known)
    # ...and the external agent's stores, unconditionally for the same reason: a schedule left
    # installed would fire inside the next case, which under -n auto is not even a stable one.
    scheduled, sites = _install_schedule(schedule, wait_sites)

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
        # A schedule that never fired is the likeliest cause of an overrun on a routine that has a
        # wait loop, and the cap's own message would send the reader to max_insns instead. Say which
        # entries came due, so "the trigger PC is wrong" and "the loop never got there" are separable.
        stalled = ""
        if scheduled:
            n_entries = len(scheduled) // SCHED_FIELDS
            stalled = (f"; its schedule of {n_entries} store(s) made "
                       f"{_LIB.osh_sched_applied()} of them, after {_LIB.osh_sched_arrivals()} "
                       f"arrival(s) at a trigger PC — an entry that never came due leaves the wait "
                       f"loop spinning")
        raise RuntimeError(f"function @ {entry:#x} did not reach {where} within {max_insns} "
                           f"instructions; final memory is mid-execution, not trustworthy{stalled}")
    # The independent reasons a run's result may be fabricated. They are reported TOGETHER rather
    # than as a first-match: a run can hit more than one, and naming only the first sends the reader
    # off to fix that one and hit the identical message again. The PSG causes are named
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
                      "— a READ of the write-only data port $ff8802 (the chip reads back through "
                      "$ff8800), a SELECT of a register number above 15 (the chip requires the "
                      "select byte's upper nibble to be zero), or an access outside the byte "
                      "select/data protocol")
    if _LIB.osh_psg_no_select():
        causes.append(
            f"it accessed the PSG ports ($ff8800/$ff8802) to READ back a register before anything "
            f"SELECTED one, which the model cannot serve: a $ff8800 read answers the LATCHED "
            f"register, and with no `move.b #<reg>,$ff8800` before it there is no latched register "
            f"to answer from — the 0 the model would otherwise start at is this file's convention, "
            f"not the chip's state. Enter the routine at (or past) its own select, or run the "
            f"caller that performs it. Unlike an undeclared register this is NOT seedable: the "
            f"select is an instruction the run either executes or does not")
    unseeded = _LIB.osh_psg_unseeded()
    if unseeded:
        undeclared = [reg for reg in range(PSG_NREGS) if unseeded & (1 << reg)]
        # The wording keeps BOTH phrases the older cause had — "accessed the PSG ports" and "cannot
        # serve" — because a refused PSG read is matched by substring outside this file
        # (projects/wonderboy/notes/portability_predictions.py, projects/joust's trap battery), and a
        # rename would silently stop those matching rather than fail loudly.
        causes.append(
            f"it accessed the PSG ports ($ff8800/$ff8802) to READ register(s) "
            f"{', '.join(str(reg) for reg in undeclared)}, which the model cannot serve as this "
            f"case is written: nothing declared their contents — no psg_seed set them and no write "
            f"in this run did — and it will not invent what the chip held on entry, because a "
            f"read-modify-write preserves exactly the bits nothing wrote. Declare them as the input "
            f"they are, with the byte the chip really held: "
            f"psg_seed={{{', '.join(f'{reg}: <byte>' for reg in undeclared)}}}")
    dropped_psg_writes = _LIB.osh_psg_dropped()
    if dropped_psg_writes:
        causes.append(f"its PSG accesses overflowed the ledger — {dropped_psg_writes} access(es) "
                      f"past os.h's OS_PSG_LOG_MAX cap were DROPPED, so psg_writes() is a truncated "
                      f"register stream, not this run's whole one")
    # A wide read of a modeled hardware byte is recorded on every run, but it is only a CAUSE here
    # under audio capture — where the extractor has no second chance and no diff to catch it. Off
    # the mode it stays what it has always been for a bare run (an off-image 0), and
    # harness._vet_hw_reads_are_declared is what refuses it in a differential, which is where a
    # fabricated neighbour could produce a false green. Same split as the undeclared read above.
    # The hardware read ledger's OWN truncation, however, is a cause for EVERY caller — the split
    # above is about a fabricated byte, and this is about hw_events() reporting a truncated stream as
    # a complete one. A bare emu.run reader has no diff to notice it, which is precisely why the PSG
    # ledger's sibling counter is a cause too. Reachable: a poll loop on $fffa01 does 4,096 reads.
    dropped_hw_reads = _LIB.osh_hw_dropped()
    if dropped_hw_reads:
        causes.append(f"its modeled hardware reads overflowed the ledger — {dropped_hw_reads} "
                      f"read(s) past os.h's OS_HW_LOG_MAX cap were DROPPED, so hw_events() is a "
                      f"truncated read stream, not this run's whole one")
    # The addresses come from the mask, never from a restated pair: the modeled set grows (os.h owns
    # it), and a message naming two of four would send the reader looking at the wrong register.
    if audio_capture_on() and _LIB.osh_hw_wide():
        wide_reads = _hw_addrs_of(_LIB.osh_hw_wide())
        causes.append(f"under audio capture it read the modeled hardware byte(s) "
                      f"{', '.join(f'{addr:#x}' for addr in wide_reads)} at 16 or 32 bits, and only "
                      f"a BYTE read of one is modeled — a wider one takes in neighbouring registers "
                      f"the model would have to fabricate as 0. Under the mode only the two "
                      f"machine-profile bytes are declared at all (hw_capture_profile()); the rest "
                      f"of the set reads an undeclared 0 there, by design")
    # The external agent's own two failures. An entry that never came due means the run is not the
    # one the case describes — the trigger PC was never reached, or was reached fewer times than
    # `nth` — and a refused store means os_sched_store would not make it (a straddle of the image's
    # top; the width and value are already checked in schedule_entries). Both leave the byte the case
    # declared unwritten, which on a wait loop is the difference between a modeled run and a hang.
    n_scheduled = len(scheduled) // SCHED_FIELDS
    if n_scheduled and _LIB.osh_sched_applied() != n_scheduled:
        causes.append(f"{n_scheduled - _LIB.osh_sched_applied()} of its {n_scheduled} scheduled "
                      f"store(s) never came due — the run made {_LIB.osh_sched_arrivals()} "
                      f"arrival(s) at a trigger PC, so either the PC is not the instruction the "
                      f"wait re-executes or `nth` names an arrival the loop never reached")
    if _LIB.osh_sched_refused():
        causes.append(f"{_LIB.osh_sched_refused()} of its scheduled store(s) could not be made — "
                      f"the store leaves the {loader.IMAGE_SIZE:#x}-byte image")
    if causes:
        raise RuntimeError(f"function @ {entry:#x} hit unmodeled OS behaviour: "
                           + "; also, ".join(causes)
                           + "; its result is fabricated, not trustworthy")

    n = _LIB.osh_num_writes()
    waddr = _LIB.osh_write_addrs()
    writes = {waddr[i]: mem[waddr[i]] for i in range(n)}
    out_regs = dict(zip(REPORTED_REGS, out))
    # THE WRITE LEDGER'S OWN TRUNCATION, REPORTED RATHER THAN REFUSED — and it is the quietest of
    # the three ledgers: the PSG's and the hardware's each COUNT what they dropped, while shim.c's
    # `logw` simply stops recording at MAX_WRITES. `writes` above is keyed by ADDRESS, so a caller
    # counting it sees distinct BYTES and cannot tell a capped run from a complete one.
    #
    # NOT A CAUSE, and the split is the one this file already makes for a wide hardware read: a
    # truncated write ledger does not FABRICATE anything — the final memory is exact and every
    # register is the run's own — it only makes one ancillary product incomplete. Bare `emu.run`
    # callers who never look at `writes` are served (a Copylock run into the blob legitimately
    # fills the ledger and is compared on its MEMORY), and `harness.differential`, which is where a
    # write set becomes a claim, refuses it — `_vet_write_ledger_below_cap`. Same shape as
    # `_vet_hw_reads_are_declared` above: recorded for every run, refused where it could go green
    # for the wrong reason.
    out_regs["writes_truncated"] = _LIB.osh_num_writes() >= MAX_WRITES
    out_regs["min_a7"] = _LIB.osh_min_a7()   # deepest stack pointer; used to vet diff exclude bands
    out_regs["heap"] = _LIB.osh_heap()       # Malloc bump pointer at the end of the run (diagnostics)
    out_regs["malloc_calls"] = _LIB.osh_malloc_count()   # serviced GEMDOS Malloc traps this run
    out_regs["poked_input_calls"] = _LIB.osh_poked_input_calls()  # ...and traps reading poked input
    out_regs["ninsns"] = _LIB.osh_num_insns()  # instructions executed (perf profiling)
    out_regs["cycles"] = _LIB.osh_num_cycles()  # 68000 clock cycles executed (perf profiling)
    dn, dargs = _LIB.osh_dosound_count(), _LIB.osh_dosound_args()
    out_regs["dosound"] = [dargs[i] for i in range(dn)]  # ordered XBIOS Dosound(A0) list pointers
    # The direct PSG path's off-image surfaces: the ordered access stream (reads included), its
    # write-only projection for the consumers that want just that, and the register file the writes
    # left behind. harness.differential compares the stream and the file against the candidate's
    # (src/psg.c) — nothing here is in the image, so nothing else could catch a divergence.
    events = psg_events()                # read the ledger ONCE; the write list is its projection
    out_regs["psg_events"] = events
    out_regs["psg"] = _psg_write_projection(events)
    out_regs["psg_file"] = psg_file()
    out_regs["psg_known"] = psg_known()
    # Direct-path accesses, READS INCLUDED — "did this run use the chip?" — and Giaccess traps, the
    # OTHER door to it. harness.differential's seed-door guard tests a case's psg_seed against both.
    out_regs["psg_direct"] = _LIB.osh_psg_direct()
    out_regs["psg_giaccess"] = _LIB.osh_psg_giaccess()
    # The seeded hardware model's off-image surfaces (TRAP_MODEL.md, Phase 7). Every one of them is
    # reported rather than raised on, because the refusal lives in harness.differential — see the
    # docstring. harness._vet_hw_reads_are_declared reads the first three, _vet_hw_state the rest.
    out_regs["hw_unseeded"] = hw_unseeded_addrs()   # modeled addresses read while undeclared
    out_regs["hw_stale"] = _hw_addrs_of(_LIB.osh_hw_stale())     # ...written, then read back
    out_regs["hw_wide"] = _hw_addrs_of(_LIB.osh_hw_wide())       # ...taken in by a 16/32-bit read
    out_regs["hw_reread"] = _hw_addrs_of(_LIB.osh_hw_reread())   # ...VOLATILE and read twice
    out_regs["hw_events"] = hw_events()             # the ordered (address, value) read stream
    out_regs["hw_file"] = hw_file()
    out_regs["hw_known"] = _LIB.osh_hw_known()
    # The external agent's surfaces. `sched_site_arrivals` is the comparable one: entry i counts the
    # run's executions of the instruction at declared site i, which is the ORIGINAL's iteration count
    # for THAT wait, and harness.differential compares it against the candidate's polls at the same
    # site. `sched_arrivals` is their sum, kept because a one-wait case reads more clearly for it.
    out_regs["sched"] = scheduled                     # the flattened list, for the candidate's copy
    out_regs["sched_sites"] = sites                   # ...and the same site list
    out_regs["sched_applied"] = _LIB.osh_sched_applied()
    out_regs["sched_arrivals"] = _LIB.osh_sched_arrivals()
    out_regs["sched_site_arrivals"] = tuple(_LIB.osh_sched_site_arrivals(i)
                                            for i in range(len(sites)))

    _vet_no_malloc_over_program(out_regs["malloc_calls"])
    _vet_no_poked_input_read(out_regs["poked_input_calls"])
    return mem, writes, out_regs