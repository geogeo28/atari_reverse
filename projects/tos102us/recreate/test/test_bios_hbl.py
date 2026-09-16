"""The HORIZONTAL BLANK handler @ $fc06c8 — vector $68, and the smallest handler in the ROM.

    move.w  d0,-(sp)
    move.w  2(sp),d0            ; the frame's SR: what the interrupted code was running at
    and.w   #$0700,d0
    bne.s   .out
    ori.w   #$0300,2(sp)        ; the mask was 0 -> resume at level 3
.out: move.w (sp)+,d0
    rte

WHY IT IS THE FIRST ONE HERE. Its whole output is a STORE INTO ITS OWN EXCEPTION FRAME, which is the
one thing the default entry shape (`isr.FRAME_IN_STACK_BAND`, the frame under `emu.STACK_TOP`) cannot
show: that band is dropped from the byte diff. So this battery is what drives `isr.STAGED_FRAME` —
the frame in COMPARED image — and with it the claim that the case shape the other three handlers use
is a choice rather than the only thing that works.

Two bytes of the staged frame belong to the machine rather than to the routine: the handler's own
`move.w d0,-(sp)`, at `frame - 2`. A C function has no machine stack to push onto, so those are the
case's to exclude — and they are the ONLY exclusion, so the SR word this routine exists to edit is
compared byte for byte.
"""
import ctypes
import struct

import pytest

import abi
import case
import isr
from harness import _lib, addrs, emu, make_image

_lib.isr_hbl.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32]
_lib.isr_hbl.restype = None

FRAME = isr.STAGED_FRAME
# The handler's own register save, which it pushes under the frame and pops back. Nothing else in
# the routine writes, so this is the whole of what the case gives up.
SAVED_D0 = (FRAME - 2, FRAME)


def _glue(lib, buf):
    lib.isr_hbl(buf, FRAME)


def _glue_at(frame):
    """...and the same over a frame the case chose, which the transcription cases below need: they
    stage theirs in the band the diff drops (`isr.transcribed` says why)."""
    def glue(lib, buf):
        lib.isr_hbl(buf, frame)
    return glue


def run(resume_sr, poison=True):
    """One differential of the HBL handler over a frame taken at `resume_sr`."""
    return isr.run(addrs.ISR_HBL, _glue, frame=FRAME, resume_sr=resume_sr,
                   exclude=(SAVED_D0,), poison=poison)


def test_the_vector_table_still_points_at_this_handler():
    """The reconstruction is of the routine the CAPTURED machine dispatches $68 to, read out of the
    snapshot's own vector table rather than assumed from the disassembly."""
    assert isr.vector_in_snapshot(addrs.VECTOR_HBL) == addrs.ISR_HBL


# Every frame whose interrupt mask is already non-zero, one per level, plus the two the field's own
# boundaries make: a reconstruction testing one bit of the mask instead of all three passes level 4
# and fails levels 1 and 2.
MASKED_LEVELS = (1, 2, 3, 4, 5, 6, 7)


@pytest.mark.parametrize("level", MASKED_LEVELS)
def test_a_frame_already_above_level_zero_is_left_exactly_as_it_is(level):
    """`and.w #$0700,d0 / bne` — the routine FLOORS the mask, it does not set it. Levels 1 and 2 are
    below the horizontal blank's own and are still left alone, which is the ROM's choice and not an
    oversight: the test is "was anything masked at all"."""
    info = run(0x2000 | (level << 8))
    assert not info["writes"].keys() - set(range(*SAVED_D0)), (
        "the handler wrote something other than its own saved D0 over a frame it should not touch")


@pytest.mark.parametrize("resume_sr", (0x0000, 0x2000, 0x001F, 0x201F, 0xF8FF, 0x8000))
def test_a_frame_at_level_zero_resumes_at_level_three(resume_sr):
    """...and the arm that does the work, over frames that differ in every bit BUT the mask.

    `ori.w #$0300` keeps everything else the word held — the condition codes, the supervisor bit, the
    trace bit — so a reconstruction that STORED $0300 rather than or-ing it passes `0x0000` and
    fails every other value here. `0xf8ff` is the whole word with the mask alone cleared, which is
    the value that separates the two most loudly.
    """
    info = run(resume_sr)
    assert case.written(info, FRAME, 2) == (resume_sr | addrs.HBL_IPL_FLOOR)


def test_the_handler_gives_back_the_register_it_borrowed():
    """`move.w d0,-(sp)` ... `move.w (sp)+,d0`, over the dirty file every handler here is entered
    with. The ORACLE's claim (see `isr.assert_registers_survived`), and the premise the whole shape
    rests on: nothing but memory has to be compared."""
    isr.assert_registers_survived(run(0x2000))


# What the two-instruction staged entry (`isr.trampoline_bytes`) plus one `rte` costs on the oracle,
# and the two book figures it is decomposed against: Musashi charges one instruction and 40 cycles
# for the reset before either entry executes anything, and `rte` is 20 cycles on a 68000.
STAGED_ENTRY_PROBE_COST = (4, 84)
RESET_COST = (1, 40)
RTE_COST = (1, 20)


def test_the_staged_entry_costs_what_tier_3_takes_off_the_original():
    """`bench/tier3.py` subtracts `isr.STAGED_ENTRY_COST` from an ISR row's ORIGINAL column, so that
    the ratio is about the handler and not about the trampoline that reached it. MEASURED here
    rather than asserted there: the trampoline is jumped at a routine that is nothing but `rte`, so
    the run is the entry, the jump and the return and there is nowhere else for a cycle to be."""
    entry = isr.TRAMPOLINE_AT[addrs.ISR_HBL]
    stub = isr.STUB_BAND
    image = make_image({entry: isr.trampoline_bytes(FRAME, stub),
                        FRAME: isr.frame_bytes(isr.RESUME_SR),
                        stub: isr.RTE})
    _final, _writes, regs = emu.run(image, entry, {})
    assert (regs["ninsns"], regs["cycles"]) == STAGED_ENTRY_PROBE_COST
    assert isr.STAGED_ENTRY_COST == (STAGED_ENTRY_PROBE_COST[0] - RESET_COST[0] - RTE_COST[0],
                                     STAGED_ENTRY_PROBE_COST[1] - RESET_COST[1] - RTE_COST[1])


# ...and the same for the SHARED trampoline, which is the entry a TRANSCRIPTION row is measured
# through: both sides run it, so `bench/tier3.py` takes it off BOTH columns (`shared_entry`) and a
# wrong number there makes the ratio lenient in one direction and harsh in the other.
SHARED_ENTRY_PROBE_COST = (5, 116)


def test_the_shared_entry_costs_what_tier_3_takes_off_both_columns():
    """MEASURED as the probe above is, over the same `rte`-only routine: the run is the three
    instructions of the shared trampoline, the return through them, and nothing else."""
    entry = isr.SHARED_TRAMPOLINE_AT[addrs.ISR_HBL]
    stub = isr.STUB_BAND
    image = make_image({entry: isr.shared_trampoline_bytes(FRAME),
                        abi.FIRST_ARG: struct.pack(">I", stub),
                        FRAME: isr.frame_bytes(isr.RESUME_SR),
                        stub: isr.RTE})
    _final, _writes, regs = emu.run(image, entry, {})
    assert (regs["ninsns"], regs["cycles"]) == SHARED_ENTRY_PROBE_COST
    assert isr.SHARED_ENTRY_COST == (SHARED_ENTRY_PROBE_COST[0] - RESET_COST[0] - RTE_COST[0],
                                     SHARED_ENTRY_PROBE_COST[1] - RESET_COST[1] - RTE_COST[1])


def test_the_stub_at_the_vector_is_the_rom_s_own_bytes():
    """`src/bios/isr.S`'s HBL stub is the ROM's seven instructions and nothing else — the one
    handler here whose whole body is transcribed rather than called."""
    isr.assert_the_stub_is_the_rom_s_bytes("ISR_HBL")


# ---- the cases this battery REGISTERS ---------------------------------------------------------------
# `test_boot_snapshot.VERIFIED_CASES` reads them (so the snapshot's non-deterministic MASK is checked
# against every byte they touch) and `bench/tier3.py` prices them. Both arms of the routine, because
# they cost different numbers of cycles and only one of them writes.
#
# THE FRAME IS THE STAGED ONE, unlike the other three handlers', and it is what makes the Tier 3 row
# a real second differential here: the byte this routine exists to change is then in COMPARED image
# rather than in the band the comparison drops. It costs nothing, because the handler's own
# `move.w d0,-(sp)` stores the LOW WORD of `isr.DIRTY_REGISTERS["d0"]` — which is zero, over a
# staging band the snapshot leaves zero — so the one write our C has no analogue for writes nothing.
assert isr.DIRTY_REGISTERS["d0"] & 0xFFFF == 0, (
    "the registered cases below rest on the handler's saved D0 being a zero word: with any other "
    "value the ROM's push would show up in the Tier 3 row's image comparison, which has no "
    "per-case exclusion")

REGISTERED = (
    {"name": "isr_hbl, a frame at level zero", "entry": addrs.ISR_HBL,
     "frame": FRAME, "resume_sr": 0x0000},
    {"name": "isr_hbl, a frame already masked", "entry": addrs.ISR_HBL,
     "frame": FRAME, "resume_sr": 0x2300},
)
VERIFIED_CASES = tuple(isr.registered(spec) for spec in REGISTERED)

# ...and the same two frames as WHOLE-HANDLER cases, which is the other relation: `src/bios/isr.S`
# against the ROM's own seven instructions, held to the image, the WHOLE register file and the chip
# (`isr.transcribed`). THE FRAME IS THE DROPPED-BAND ONE and not `FRAME` above, because the shared
# trampoline both sides run pushes its own target below it — so what these rows prove is the
# register file and the cost, and the store into the frame stays the C row's and the byte
# relation's.
TRANSCRIBED = tuple({**spec, "frame": isr.FRAME_IN_STACK_BAND} for spec in REGISTERED)
TRANSCRIPTION_CASES = tuple(isr.transcribed(spec) for spec in TRANSCRIBED)


@pytest.mark.parametrize("spec", REGISTERED, ids=lambda spec: spec["name"])
def test_every_registered_case_is_one_this_battery_proves(spec):
    """The row and the differential are the SAME spec (`isr.registered` / `isr.run_spec`), so this
    is what says the registry describes a run that was verified rather than one that was written
    down."""
    isr.run_spec(spec, _glue, exclude=(SAVED_D0,))


@pytest.mark.parametrize("spec", TRANSCRIBED, ids=lambda spec: spec["name"])
def test_every_transcription_case_is_one_this_battery_proves(spec):
    """...and the same for the whole-handler rows: the spec Tier 3 measures the `.S` over is one
    this battery has already run the C core through."""
    isr.run_spec(spec, _glue_at(spec["frame"]))
