"""Differential tests for the boss encounter's two callee-free steps (src/mothership.c):
mothership_place_tail @ 0x14f18 and mothership_sprite_build_step @ 0x15128.

Both write only to the game's own fixed addresses, so every case seeds those in place — the address
IS part of what is being verified — and seeds them with noise, so a candidate that writes a byte too
many or a byte too few differs rather than passing.
"""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, report

ENTRY_MOTHERSHIP_PLACE_TAIL = 0x14f18
ENTRY_MOTHERSHIP_SPRITE_BUILD_STEP = 0x15128
ENTRY_MOTHERSHIP_BEGIN = 0x14eda
ENTRY_MOTHERSHIP_DRAW = 0x158f4

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
for _sym in ("g_mothership_place_tail", "g_mothership_sprite_build_step",
             "g_mothership_begin", "g_mothership_draw"):
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



# Every fuzz battery here splits its cases four ways so `-n auto` can spread them; see
# test_enemy.py's note on the idiom.
FUZZ_CHUNKS = 4


def _in_chunk(index, chunk):
    return index % FUZZ_CHUNKS == chunk


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
        if _in_chunk(i, chunk):
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



# ================================================================= mothership_begin @ 0x14eda

# The eight wave records the arming gate counts, and the byte in each that says "in use".
A_ENEMY_SLOTS = 0x17c1a
ENEMY_SLOT_COUNT = 8
ENTITY_ALIVE = 0x0e
A_FREE_WAVE_SLOT_COUNT = 0x198b7
MOTHERSHIP_START_X = 0x140
MOTHERSHIP_START_Y = 0
# Where the two `move.w #imm,$19dd0/$19dd2` keep their immediates, in the routine's own body.
MOTHERSHIP_BEGIN_START_Y_IMMEDIATE = 0x14f0a
MOTHERSHIP_BEGIN_START_X_IMMEDIATE = 0x14f12
MOTHERSHIP_ENERGY_SECTIONS = 0x10   # what a case seeds; nothing bounds the section byte itself

# `mothership_sprite_expand` copies the disk file's four cells into both banks, so a case has to
# seed the source and the whole destination — the routine is only "callee-free" once those are
# staged. Sizes are include/sprite.h's boss geometry.
BOSS_SPRITE_ROWS = 40
BOSS_SPRITE_SOURCE_CELLS = 4
BOSS_SPRITE_FRAME_CELLS = 5
SPRITE_MASKED_ROW_BYTES = 10
BOSS_SPRITE_CELL_BYTES = BOSS_SPRITE_ROWS * SPRITE_MASKED_ROW_BYTES
BOSS_SPRITE_FRAME_BYTES = BOSS_SPRITE_FRAME_CELLS * BOSS_SPRITE_CELL_BYTES
BOSS_SPRITE_SOURCE_BYTES = BOSS_SPRITE_SOURCE_CELLS * BOSS_SPRITE_CELL_BYTES
BOSS_SPRITE_EXPANDED_BYTES = SPRITE_PRESHIFT_SLOTS * BOSS_SPRITE_FRAME_BYTES

A_BOSS_HITPOINTS = 0x19f44
A_MOTHERSHIP_ENERGY_BY_SECTION = 0x1987d
A_LEVEL_SECTION = 0x19895


def _begin_case(alive_bytes, section=0, seed=0, poison=False):
    pokes = {A_ENEMY_SLOTS: _noise(seed + 11, ENEMY_SLOT_COUNT * ENTITY_STRIDE)}
    slots = bytearray(pokes[A_ENEMY_SLOTS])
    for i, alive in enumerate(alive_bytes):
        slots[i * ENTITY_STRIDE + ENTITY_ALIVE] = alive
    pokes[A_ENEMY_SLOTS] = bytes(slots)
    pokes[A_MOTHERSHIP_SPRITE_SOURCE] = _noise(seed + 22, BOSS_SPRITE_SOURCE_BYTES)
    pokes[A_MOTHERSHIP_SPRITE_BANK] = _noise(seed + 33, BOSS_SPRITE_EXPANDED_BYTES)
    pokes[A_ENTITY_BOSS_PARTS] = _noise(seed + 44, TAIL_SEEDED_RECORDS * ENTITY_STRIDE)
    pokes[A_MOTHERSHIP_ENERGY_BY_SECTION] = _noise(seed + 55, MOTHERSHIP_ENERGY_SECTIONS)
    pokes[A_LEVEL_SECTION] = bytes([section])
    # Canaries on every byte the routine must overwrite, so a store it skipped is a diff.
    pokes[A_BOSS_HITPOINTS] = b"\xa5\x5a"
    pokes[A_MOTHERSHIP_X] = b"\xa5\x5a"
    pokes[A_MOTHERSHIP_Y] = b"\xa5\x5a"
    pokes[A_MOTHERSHIP_PREP_STAGE] = bytes([0xa5])
    pokes[A_FREE_WAVE_SLOT_COUNT] = bytes([0xa5])
    diffs, _ = differential(ENTRY_MOTHERSHIP_BEGIN, {"_pokes": pokes},
                            lambda lib, buf: lib.g_mothership_begin(buf), poison=poison)
    assert not diffs, f"alive={alive_bytes} section={section:#x}\n{report(diffs)}"


def test_begin_parks_the_anchor_where_its_own_immediates_say():
    """The two `move.w #imm,<ea>` the routine ends with, read back out of the image."""
    for immediate_at, expected in ((MOTHERSHIP_BEGIN_START_Y_IMMEDIATE, MOTHERSHIP_START_Y),
                                   (MOTHERSHIP_BEGIN_START_X_IMMEDIATE, MOTHERSHIP_START_X)):
        loaded = int.from_bytes(bytes(harness.BASE_IMAGE[immediate_at:immediate_at + 2]), "big")
        assert loaded == expected, f"{immediate_at:#x} holds {loaded:#x}"


@pytest.mark.parametrize("in_use", range(ENEMY_SLOT_COUNT + 1))
def test_begin_arms_only_with_every_wave_slot_free(in_use):
    """The gate is `count_free_wave_slots() == 8`, i.e. nothing else alive.

    Driven at every count from 0 to 8 rather than at 7 and 8 alone, because the count comes back in
    a register the gate compares for EQUALITY — so a candidate testing `>= 8`, `!= 0` or a bit of
    the byte agrees with it on some of these and not on others. The count is published to
    A_free_wave_slot_count on every call, armed or not, and its canary holds that.
    """
    _begin_case([1] * in_use + [0] * (ENEMY_SLOT_COUNT - in_use))


@pytest.mark.parametrize("alive", (0x01, 0x7f, 0x80, 0xff))
def test_begin_gate_counts_any_non_zero_byte(alive):
    """...and "in use" is `tst.b`, not a comparison against 1."""
    _begin_case([alive] + [0] * (ENEMY_SLOT_COUNT - 1))


@pytest.mark.parametrize("section", (0, 1, 2, 0x0f, 0x7f, 0x80, 0xff))
def test_begin_energy_comes_from_the_section_table(section):
    """The section byte is SIGN-extended into the index and the energy byte it reaches is read
    UNSIGNED into a word (`and.w #$ff`) — so 0x80..0xff read a byte BELOW the table, and a value of
    0x80 or more is stored as 0x0080..0x00ff rather than sign-extended. The band around the table is
    seeded so both halves of that are a difference."""
    _begin_case([0] * ENEMY_SLOT_COUNT, section=section)


def test_begin_falls_through_into_place_tail():
    """0x14eda has no `rts`: it runs into mothership_place_tail, which lays the five segments out
    from the anchor this routine has just written and sets the prep stage to 1. The canaries on the
    anchor words and on the stage byte are what say both halves ran."""
    _begin_case([0] * ENEMY_SLOT_COUNT, section=1, poison=True)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_begin_fuzz(chunk):
    rng = random.Random(ENTRY_MOTHERSHIP_BEGIN)
    for i in range(40):
        alive = [rng.randrange(256) if rng.randrange(3) == 0 else 0
                 for _ in range(ENEMY_SLOT_COUNT)]
        case = dict(alive_bytes=alive, section=rng.randrange(256), seed=i)
        if _in_chunk(i, chunk):
            _begin_case(**case)


# ================================================================== mothership_draw @ 0x158f4

# D2 is half a preshift frame, derived rather than transcribed — test_sprite.py makes the same claim
# about the same immediate from the other side.
MOTHERSHIP_DRAW_PHASE_STEP = BOSS_SPRITE_FRAME_BYTES // 2
# Where `move.w #$3e8,d2` keeps its immediate, inside mothership_draw's own body.
MOTHERSHIP_DRAW_D2_IMMEDIATE = 0x1590c

A_SCREEN_BACK = 0x1797e
SCREEN_BYTES = 32000
PLAYFIELD_TOP_Y = 32
DRAW_SPRITE = abi.SCRATCH + 0x10000
DRAW_SPRITE_BYTES = 0x8000
ENTITY_X, ENTITY_Y, ENTITY_HEIGHT, ENTITY_SPRITE = 0x00, 0x04, 0x08, 0x0a


def _drawable_segment(seed, alive, x, y):
    record = bytearray(_noise(seed, ENTITY_STRIDE))
    record[ENTITY_ALIVE] = alive
    record[ENTITY_X:ENTITY_X + 2] = (x & 0xffff).to_bytes(2, "big")
    record[ENTITY_Y:ENTITY_Y + 2] = (y & 0xffff).to_bytes(2, "big")
    record[ENTITY_HEIGHT:ENTITY_HEIGHT + 2] = BOSS_SPRITE_ROWS.to_bytes(2, "big")
    record[ENTITY_SPRITE:ENTITY_SPRITE + 4] = DRAW_SPRITE.to_bytes(4, "big")
    return bytes(record)


def _draw_case(alive_of, count=None, seed=0, poison=False):
    count = MOTHERSHIP_TAIL_SEGMENTS if count is None else count
    pokes = abi.seed_spans(ENTRY_MOTHERSHIP_DRAW + seed,
                           ((DRAW_SPRITE, DRAW_SPRITE + DRAW_SPRITE_BYTES),
                            (abi.SCREEN_BACK, abi.SCREEN_BACK + SCREEN_BYTES)),
                           guard=abi.GUARD_BYTES)
    pokes[A_SCREEN_BACK] = abi.SCREEN_BACK.to_bytes(4, "big")
    pokes[A_ENTITY_BOSS_PARTS] = b"".join(
        _drawable_segment(seed * 16 + i, alive_of(i),
                          0x20 + i * 0x20 + (i % 8) * 2,        # ...through eight x phases
                          PLAYFIELD_TOP_Y + 8 + (i % 4) * 0x18)
        for i in range(count))
    diffs, _ = differential(ENTRY_MOTHERSHIP_DRAW, {"_pokes": pokes},
                            lambda lib, buf: lib.g_mothership_draw(buf), poison=poison)
    assert not diffs, report(diffs)


def test_draw_every_segment():
    """All five live, each at its own place and its own sub-cell phase."""
    _draw_case(lambda i: 1)


@pytest.mark.parametrize("dead", range(MOTHERSHIP_TAIL_SEGMENTS))
def test_draw_skips_a_dead_segment(dead):
    """`tst.b 14(a2)` gates each one, and the dead segment must leave the screen alone under it."""
    _draw_case(lambda i: 0 if i == dead else 1)


def test_draw_walks_exactly_five_segments():
    """A sixth live record must be left undrawn — the records are contiguous with the shift-mask
    table, so a pass too far reads a record made of table bytes."""
    _draw_case(lambda i: 1, count=MOTHERSHIP_TAIL_SEGMENTS + 1)


def test_draw_phase_step_is_half_a_frame():
    """The immediate the routine loads into D2, read off the image's own bytes."""
    assert MOTHERSHIP_DRAW_PHASE_STEP == 0x3e8
    loaded = int.from_bytes(bytes(harness.BASE_IMAGE[MOTHERSHIP_DRAW_D2_IMMEDIATE:
                                                     MOTHERSHIP_DRAW_D2_IMMEDIATE + 2]), "big")
    assert loaded == MOTHERSHIP_DRAW_PHASE_STEP, f"{loaded:#x}"


def test_draw_attribution():
    _draw_case(lambda i: 1, seed=5, poison=True)

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
    ("A_ENEMY_SLOTS", "include/enemy.h", "A_enemy_slots"),
    ("A_FREE_WAVE_SLOT_COUNT", "include/enemy.h", "A_free_wave_slot_count"),
    ("A_BOSS_HITPOINTS", "include/mothership.h", "A_boss_hitpoints"),
    ("A_MOTHERSHIP_ENERGY_BY_SECTION", "include/mothership.h",
     "A_mothership_energy_by_section"),
    ("A_LEVEL_SECTION", "include/mothership.h", "A_level_section"),
    ("A_SCREEN_BACK", "include/video.h", "A_screen_back"),
    ("SCREEN_BYTES", "include/video.h", "SCREEN_BYTES"),
    ("PLAYFIELD_TOP_Y", "include/video.h", "PLAYFIELD_TOP_Y"),
    ("ENTITY_ALIVE", "include/entity.h", "ENTITY_ALIVE"),
    ("ENTITY_X", "include/entity.h", "ENTITY_X"),
    ("ENTITY_Y", "include/entity.h", "ENTITY_Y"),
    ("ENTITY_HEIGHT", "include/entity.h", "ENTITY_HEIGHT"),
    ("ENTITY_SPRITE", "include/entity.h", "ENTITY_SPRITE"),
    ("ENEMY_SLOT_COUNT", "include/enemy.h", "ENEMY_SLOT_COUNT"),
    ("MOTHERSHIP_START_X", "include/mothership.h", "MOTHERSHIP_START_X"),
    ("MOTHERSHIP_START_Y", "include/mothership.h", "MOTHERSHIP_START_Y"),
    ("BOSS_SPRITE_ROWS", "include/sprite.h", "BOSS_SPRITE_ROWS"),
    ("BOSS_SPRITE_SOURCE_CELLS", "include/sprite.h", "BOSS_SPRITE_SOURCE_CELLS"),
    ("BOSS_SPRITE_FRAME_CELLS", "include/sprite.h", "BOSS_SPRITE_FRAME_CELLS"),
    ("SPRITE_MASKED_ROW_BYTES", "include/sprite.h", "SPRITE_MASKED_ROW_BYTES"),
)
ENTRY_PROLOGUES = {
    "ENTRY_MOTHERSHIP_PLACE_TAIL": "45f90001814249f90003",
    "ENTRY_MOTHERSHIP_SPRITE_BUILD_STEP": "0c390001000199116600",
    "ENTRY_MOTHERSHIP_BEGIN": "6100e94cb03c00086700",
    "ENTRY_MOTHERSHIP_DRAW": "45f9000181423c3c0004",
}
