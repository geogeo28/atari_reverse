"""Differential tests for the boss encounter's two callee-free steps (src/mothership.c):
mothership_place_tail @ 0x14f18 and mothership_sprite_build_step @ 0x15128.

Both write only to the game's own fixed addresses, so every case seeds those in place — the address
IS part of what is being verified — and seeds them with noise, so a candidate that writes a byte too
many or a byte too few differs rather than passing.
"""
import ctypes
import random

import pytest

import harness
from harness import differential, report

ENTRY_MOTHERSHIP_PLACE_TAIL = 0x14f18
ENTRY_MOTHERSHIP_SPRITE_BUILD_STEP = 0x15128

# ---- record layout (mirror of include/entity.h) ----
ENTITY_STRIDE = 0x2c

# ---- the globals both routines address themselves (mirrors of include/mothership.h) ----
A_ENTITY_BOSS_PARTS = 0x18142
A_MOTHERSHIP_READY = 0x198b0
A_MOTHERSHIP_PREP_STAGE = 0x19911
A_MOTHERSHIP_X = 0x19dd0
A_MOTHERSHIP_Y = 0x19dd2
A_MOTHERSHIP_PHASE_TIMER = 0x19efe
A_MOTHERSHIP_SPRITE_BANK = 0x310ae
A_MOTHERSHIP_SPRITE_SOURCE = 0x5ed7e

# ---- geometry (mirrors of include/mothership.h and include/sprite.h) ----
MOTHERSHIP_TAIL_SEGMENTS = 5
MOTHERSHIP_SEGMENT_SPRITE_BYTES = 0x190
MOTHERSHIP_FRAME_BYTES = 0xa0
MOTHERSHIP_BANKS = 2
SPRITE_PRESHIFT_SLOTS = 8

BANK_BYTES = SPRITE_PRESHIFT_SLOTS * MOTHERSHIP_FRAME_BYTES

# THE STAGE THE MACHINE CAN ACTUALLY BE IN when the routine is entered. `mothership_place_tail` and
# 0x1504a set it to 1, the routine walks it 1 -> 2 -> 3, and the stage-3 arm clears it — so entry is
# always 1, 2 or 3.
BUILD_STAGES = (1, 2, 3)
# Past the machine's range, and driven separately so the name of the test above stays true. Their
# arithmetic stays inside the image, which is the whole reason they can be driven at all.
BUILD_STAGES_BEYOND = (4, 5)
# 0 is excluded, and the exclusion is load-bearing rather than squeamishness: `sub.b #$2 / ext.w /
# mulu.w` reads 0 as 0xfffe and addresses ~0x5030000, outside the image entirely. The oracle bounds
# that access and drops it while a reconstruction indexing `image + addr` faults, so no differential
# could compare the two sides. The routine's only caller (0x1117e) guards it with `tst.b / beq`.
BUILD_STAGE_UNREACHABLE = 0

_u8p = ctypes.POINTER(ctypes.c_uint8)
for _sym in ("g_mothership_place_tail", "g_mothership_sprite_build_step"):
    getattr(harness._lib, _sym).argtypes = [_u8p]
    getattr(harness._lib, _sym).restype = None


def _noise(seed, span):
    return random.Random(seed).randbytes(span)


# ============================================================== mothership_place_tail @ 0x14f18

# One record past the five the routine writes, so a loop that ran a step too far differs. The
# records are contiguous with the shift-mask table that follows them, which is exactly the memory a
# sixth pass would corrupt.
TAIL_SEEDED_RECORDS = MOTHERSHIP_TAIL_SEGMENTS + 1
# The five segments span 5 x 0x190 = 0x7d0 bytes of sprite bank, which is WIDER than the 0x500 one
# pre-shifted bank occupies — so the last segments point into the second bank by design, and a
# reconstruction that reached for the bank stride here would silently aim all five at the first.
# That confusion is held by the differential (the stored pointers are compared byte for byte), not
# by an assertion here: an assertion comparing this file's own literals to each other could not
# fail on any change to src/.


def _place_tail_case(anchor_x, anchor_y, seed=0, poison=False):
    pokes = {A_ENTITY_BOSS_PARTS: _noise(seed, TAIL_SEEDED_RECORDS * ENTITY_STRIDE),
             A_MOTHERSHIP_X: (anchor_x & 0xffff).to_bytes(2, "big"),
             A_MOTHERSHIP_Y: (anchor_y & 0xffff).to_bytes(2, "big"),
             A_MOTHERSHIP_PREP_STAGE: bytes([0xa5])}      # a canary the routine must overwrite
    diffs, _ = differential(ENTRY_MOTHERSHIP_PLACE_TAIL, {"_pokes": pokes},
                            lambda lib, buf: lib.g_mothership_place_tail(buf), poison=poison)
    assert not diffs, f"anchor=({anchor_x:#x},{anchor_y:#x})\n{report(diffs)}"


@pytest.mark.parametrize("anchor_x", (0, 1, 0x100, 0x140, 0x7fff, 0x8000, 0xfff8, 0xffff))
def test_place_tail_steps_x_across_the_segments(anchor_x):
    """The x step accumulates in a WORD register, so an anchor near the top of the range wraps
    rather than growing — which is what the 0xfff8 and 0xffff cases drive."""
    _place_tail_case(anchor_x, anchor_y=0x40, seed=anchor_x & 0xff)


@pytest.mark.parametrize("anchor_y", (0, 0x40, 0xb0, 0x7fff, 0x8000, 0xffff))
def test_place_tail_copies_y_unchanged(anchor_y):
    """Every segment gets the SAME y, unlike x, which is stepped.

    Only "not stepped" is pinned. The original re-reads A_mothership_y inside the loop and this
    reconstruction does too, but nothing in the loop can change that byte pair — the five records
    end well below it — so hoisting the read out is byte-identical and no case here separates the
    two. Transcribed faithfully, held only as far as the difference is observable.
    """
    _place_tail_case(anchor_x=0x140, anchor_y=anchor_y, seed=anchor_y & 0xff)



FUZZ_CHUNKS = 4


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_place_tail_fuzz(chunk):
    """Random anchors over the whole word, sharded so `-n auto` can spread them.

    Only mothership_place_tail is fuzzed: mothership_sprite_build_step's ONLY input is the stage
    byte, and `test_build_step_every_reachable_stage` already drives every value of it the machine
    can be entered in — a random stage would be fabricating a state, not sampling one.
    """
    rng = random.Random(ENTRY_MOTHERSHIP_PLACE_TAIL)
    for i in range(80):
        anchor_x, anchor_y = rng.randrange(1 << 16), rng.randrange(1 << 16)
        if i % FUZZ_CHUNKS == chunk:
            _place_tail_case(anchor_x, anchor_y, seed=0x200 + i)


def test_place_tail_attribution():
    """Poison every byte the oracle wrote: a candidate that skipped a field cannot pass by luck."""
    _place_tail_case(anchor_x=0x140, anchor_y=0, seed=99, poison=True)


# ====================================================== mothership_sprite_build_step @ 0x15128

# What a case seeds around the banks: every byte any driven stage reads or writes. The furthest
# stage pre-shifts the bank at index `stage - PREP_STAGE_PRESHIFT` and walks all of it.
PREP_STAGE_PRESHIFT = 2   # mirror of src/mothership.c
BANK_SEEDED_BYTES = (max(BUILD_STAGES + BUILD_STAGES_BEYOND) - PREP_STAGE_PRESHIFT + 1) * BANK_BYTES
SOURCE_SEEDED_BYTES = MOTHERSHIP_BANKS * MOTHERSHIP_FRAME_BYTES


# NO `poison=True` ANYWHERE BELOW, and the reason is a property of the routine rather than a
# shortcut. The attribution pass re-runs both sides over an image whose oracle-written bytes are
# INVERTED (`harness.py`, `o_final[a] ^ 0xff`), and A_mothership_prep_stage is written AND read
# here — so a stage-1 case, whose oracle leaves 2 in that byte, re-runs with 0xfd, and `sub.b #$2 /
# ext.w / mulu.w` then addresses 0x310ae + 0xfffb * 0x500, about 0x5030000: outside the image, the
# same place a stage of 0 lands. `make guarded` caught it as a worker crash while `make test` alone
# stayed green. Attribution is instead carried by what every case seeds — noise across both banks
# and both raw frames, and a distinguishable canary under each of the three "finished" flags — so a
# candidate that skips any store still differs.
def _build_step_case(stage, seed=0):
    pokes = {A_MOTHERSHIP_SPRITE_BANK: _noise(seed, BANK_SEEDED_BYTES),
             A_MOTHERSHIP_SPRITE_SOURCE: _noise(seed + 1000, SOURCE_SEEDED_BYTES),
             A_MOTHERSHIP_PREP_STAGE: bytes([stage]),
             A_MOTHERSHIP_READY: bytes([0xa5]),
             A_MOTHERSHIP_PHASE_TIMER: bytes([0xde, 0xad, 0xbe, 0xef])}
    diffs, _ = differential(ENTRY_MOTHERSHIP_SPRITE_BUILD_STEP, {"_pokes": pokes},
                            lambda lib, buf: lib.g_mothership_sprite_build_step(buf))
    assert not diffs, f"stage={stage}\n{report(diffs)}"


@pytest.mark.parametrize("stage", BUILD_STAGES)
def test_build_step_every_reachable_stage(stage):
    """Stage 1 copies both raw frames in; 2 and 3 pre-shift one bank each.

    The banks are seeded across their whole extent, so the stage-1 case pins BOTH strides — the
    source's MOTHERSHIP_FRAME_BYTES and the destination's BANK_BYTES, which differ by a factor of
    eight and would otherwise be easy to conflate.
    """
    _build_step_case(stage, seed=stage)


@pytest.mark.parametrize("stage", BUILD_STAGES_BEYOND)
def test_build_step_past_the_machines_range(stage):
    """The multiply keeps working past stage 3, and these say so without pretending to be reachable.

    They are here because the bank index is the one piece of arithmetic in the routine, and two more
    values of it cost nothing while the addresses stay inside the image. They are NOT evidence about
    the game: no caller can produce them.
    """
    _build_step_case(stage, seed=stage)


def test_build_step_finish_arm_is_the_last_call_and_only_the_last():
    """The three finish stores fire on the stage-3 call and on no other.

    One test rather than two, over a fresh noise seed, because the seeding is shared: every case
    above already carries the canaries, so what this adds is the CONTRAST — the same three
    addresses, driven through the stage that writes them and the two that must not, in one place a
    reader can check the claim against.
    """
    for stage in BUILD_STAGES:
        _build_step_case(stage, seed=77 + stage)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("ENTITY_STRIDE", "include/entity.h", "ENTITY_STRIDE"),
    ("A_ENTITY_BOSS_PARTS", "include/mothership.h", "A_entity_boss_parts"),
    ("A_MOTHERSHIP_READY", "include/mothership.h", "A_mothership_ready"),
    ("A_MOTHERSHIP_PREP_STAGE", "include/mothership.h", "A_mothership_prep_stage"),
    ("A_MOTHERSHIP_X", "include/mothership.h", "A_mothership_x"),
    ("A_MOTHERSHIP_Y", "include/mothership.h", "A_mothership_y"),
    ("A_MOTHERSHIP_PHASE_TIMER", "include/mothership.h", "A_mothership_phase_timer"),
    ("A_MOTHERSHIP_SPRITE_BANK", "include/mothership.h", "A_mothership_sprite_bank"),
    ("A_MOTHERSHIP_SPRITE_SOURCE", "include/mothership.h", "A_mothership_sprite_source"),
    ("MOTHERSHIP_TAIL_SEGMENTS", "include/mothership.h", "MOTHERSHIP_TAIL_SEGMENTS"),
    ("MOTHERSHIP_SEGMENT_SPRITE_BYTES", "include/mothership.h",
     "MOTHERSHIP_SEGMENT_SPRITE_BYTES"),
    ("MOTHERSHIP_FRAME_BYTES", "include/mothership.h", "MOTHERSHIP_FRAME_BYTES"),
    ("MOTHERSHIP_BANKS", "include/mothership.h", "MOTHERSHIP_BANKS"),
    ("PREP_STAGE_PRESHIFT", "src/mothership.c", "PREP_STAGE_PRESHIFT"),
    ("SPRITE_PRESHIFT_SLOTS", "include/sprite.h", "SPRITE_PRESHIFT_SLOTS"),
)
ENTRY_PROLOGUES = {
    "ENTRY_MOTHERSHIP_PLACE_TAIL": "45f90001814249f90003",
    "ENTRY_MOTHERSHIP_SPRITE_BUILD_STEP": "0c390001000199116600",
}
