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


# ================================================= WAVE 3 — the encounter's own five routines
#
# All five work over the WAVE slots at A_enemy_slots rather than over records of their own
# (include/mothership.h, "THE BOSS'S OWN SLOTS"), and four of the five reach the actor script VM or
# the formation spawner in `enemy`. So the staging below is the same shape `test_enemy.py`'s is —
# the twenty entity records, the player's, the generator and the level section — plus the boss's
# own tables.

ENTRY_MOTHERSHIP_SPAWN_HEAD = 0x14f64
ENTRY_MOTHERSHIP_MOVE_AND_PLACE = 0x14fc8
ENTRY_MOTHERSHIP_SEGMENTS_RESPAWN = 0x1504a
ENTRY_MOTHERSHIP_SEGMENTS_UPDATE = 0x151ba
ENTRY_MOTHERSHIP_SEGMENT_HIT = 0x15222

# ---- the globals these five address themselves ----
A_ENTITY_TABLE = 0x17a8e
A_PLAYER_RECORD = 0x17d7a
A_ACTOR_SPAWN_TEMPLATE = 0x17a62
A_ENTITY_COLLISION_MASKS = 0x18252
A_PLAYER_SCORE_BCD = 0x195e0
A_SCORE_VALUE_SEGMENT = 0x195f0
A_RNG_LFSR_STATE = 0x195f4
A_SQUADRON_KILL_COUNTERS = 0x198bb
A_ENEMY_PAIR_HITPOINTS = 0x19884
A_MOTHERSHIP_SEGMENT_ENERGY = 0x1988d
A_MOTHERSHIP_OFFSCREEN = 0x19916
A_EXPLOSION_GROUP_ACTIVE_BITS = 0x19670
A_MOTHERSHIP_FORMATION_BY_SECTION = 0x19cc3
A_MOTHERSHIP_SPAWN_PARAM_BY_SECTION = 0x19cd3
A_FORMATION_TABLE = 0x19504
A_SCORE_AWARD_TABLE_BCD = 0x195e4
A_MOTHERSHIP_HEAD_SPRITE = 0x19e2e
A_MOTHERSHIP_SEGMENT_SPRITE = 0x315ae
A_MOTHERSHIP_EXPLOSION_SPRITE = 0x5cf7e
A_SCROLL_FROZEN = 0x198b1

# ---- record roles (mirrors of include/entity.h and include/enemy.h) ----
ENTITY_TYPE = 0x11
ACTOR_SCRIPT_DELAY, ACTOR_SCRIPT_OPCODE = 0x26, 0x28
ACTOR_SCRIPT_LOOP_PC, ACTOR_SCRIPT_LOOP_COUNT = 0x24, 0x27

# ---- shapes (mirrors of include/mothership.h) ----
MOTHERSHIP_PAIR_BYTES = 0x58
MOTHERSHIP_SEGMENT_PAIRS = 4
MOTHERSHIP_HEAD_RECORDS = 2
MOTHERSHIP_SHADOW_X_LEAD = 0x10
MOTHERSHIP_SEGMENT_TYPE = 2
MOTHERSHIP_HEAD_TYPE = 1
MOTHERSHIP_HEAD_ROWS = 1
MOTHERSHIP_SEGMENT_ROWS = 0x10
MOTHERSHIP_SPAWN_X = 0x180
MOTHERSHIP_ANCHOR_X_LEAD = 0x40
MOTHERSHIP_ANCHOR_Y_LEAD = 0x14
MOTHERSHIP_SEGMENT_KEEP_X_MIN = 0x10
ACTOR_KEEP_X_MAX = 0x1b8
ENTITY_COUNT = 20
COLLISION_ROW_BYTES = 4
PREP_STAGE_COPY = 1
EXPLOSION_PART_TYPE = 0x64
EXPLOSION_X_ALIGN = 0xfffc
ENTITY_ALIVE_EXPLODING = 0x80
FORMATION_COUNT = 2                 # byte 2 of a formation record: how many actors it places
SCORE_BCD_BYTES = 4
MOTHERSHIP_SEGMENT_ENERGY_STRIDE = 2
PAIR_INDEX_ALIGN = 0xfffe
SEGMENT_HIT_COUNTER_BYTES = 0x20   # wider than the eight the fold can reach, so a stray one shows

# The three encounter flags `mothership_sprite_preshift` arms on its way out of
# `mothership_spawn_head`. TWO OF THEM ARE CLEARED, and all of them live in bss — so leaving them at
# their loaded zeroes would make the clears write zeroes over zeroes and differ nowhere.
SPAWN_HEAD_FLAG_SEEDS = ((A_MOTHERSHIP_READY, b"\xa5"), (A_MOTHERSHIP_PREP_STAGE, b"\x3c"),
                         (A_MOTHERSHIP_PHASE_TIMER, b"\xde\xad\xbe\xef"))

# The script every case gives a boss record: a delay of 3 so the VM ticks without fetching, and an
# opcode whose class-7 / operand-15 arm is `actor_script_op_end_frame` — one dispatch and out.
BOSS_SCRIPT_DELAY = 3
BOSS_SCRIPT_END_FRAME = 0x7f

for _sym in ("g_mothership_spawn_head", "g_mothership_move_and_place",
             "g_mothership_segments_update", "g_mothership_segments_respawn"):
    getattr(harness._lib, _sym).argtypes = [_u8p]
    getattr(harness._lib, _sym).restype = None
harness._lib.g_mothership_segment_hit.argtypes = [_u8p, ctypes.c_uint32]
harness._lib.g_mothership_segment_hit.restype = None


class _Record:
    """One 0x2c-byte record: noise everywhere, then the fields a case states."""

    def __init__(self, seed):
        self.data = bytearray(random.Random(seed).randbytes(ENTITY_STRIDE))

    def byte(self, offset, value):
        self.data[offset] = value & 0xff
        return self

    def word(self, offset, value):
        self.data[offset:offset + 2] = (value & 0xffff).to_bytes(2, "big")
        return self

    def bytes(self):
        return bytes(self.data)


def _records(items):
    return b"".join(record.bytes() for record in items)


def _boss_record(seed, alive=1, type_id=MOTHERSHIP_SEGMENT_TYPE, x=0x100, y=0x50):
    """A record the script VM can be run on, whatever else the case is about."""
    return (_Record(seed).byte(ENTITY_ALIVE, alive).byte(ENTITY_TYPE, type_id)
            .word(ENTITY_X, x).word(ENTITY_Y, y)
            .byte(ACTOR_SCRIPT_DELAY, BOSS_SCRIPT_DELAY)
            .byte(ACTOR_SCRIPT_OPCODE, BOSS_SCRIPT_END_FRAME)
            .byte(ACTOR_SCRIPT_LOOP_COUNT, 1).word(ACTOR_SCRIPT_LOOP_PC, 0))


BOSS_RNG_STATE = 0x1234abcd


def _boss_environment(seed):
    """The entity table, the ship's record, the collision rows, the generator and the two flags the
    script handlers read. A_PLAYER_RECORD is inside the table poke and deliberately wins."""
    return {A_ENTITY_TABLE: _records([_Record(seed + i) for i in range(ENTITY_COUNT)]),
            A_ENTITY_COLLISION_MASKS: bytes(ENTITY_COUNT * COLLISION_ROW_BYTES),
            A_PLAYER_RECORD: _Record(seed + 0x40).word(ENTITY_X, 0x90).word(ENTITY_Y, 0x40).bytes(),
            A_SCROLL_FROZEN: bytes([0]),
            A_RNG_LFSR_STATE: BOSS_RNG_STATE.to_bytes(4, "big")}


# ============================================================ mothership_spawn_head @ 0x14f64

def _spawn_head_case(section, seed=0, poison=False):
    pokes = abi.seed_spans(0x14f64 + seed,
                           ((A_MOTHERSHIP_SPRITE_BANK, A_MOTHERSHIP_SPRITE_BANK + BOSS_SPRITE_EXPANDED_BYTES),),
                           guard=abi.GUARD_BYTES)
    pokes.update(_boss_environment(0x20000 + seed))
    pokes[A_ENEMY_SLOTS] = _records([_Record(0x20100 + seed + i).byte(ENTITY_ALIVE, 0)
                                     for i in range(ENEMY_SLOT_COUNT + 1)])
    pokes[A_SQUADRON_KILL_COUNTERS] = bytes(6) + random.Random(seed).randbytes(0x40)
    pokes[A_ACTOR_SPAWN_TEMPLATE] = _noise(0x20200 + seed, ENTITY_STRIDE)
    pokes[A_LEVEL_SECTION] = bytes([section])
    pokes.update(SPAWN_HEAD_FLAG_SEEDS)
    diffs, _ = differential(ENTRY_MOTHERSHIP_SPAWN_HEAD, {"_pokes": pokes},
                            lambda lib, buf: lib.g_mothership_spawn_head(buf), poison=poison)
    assert not diffs, f"section={section}\n{report(diffs)}"


@pytest.mark.parametrize("section", range(0x10))
def test_spawn_head_every_section(section):
    """Each section names its own formation and its own fire-flags byte, and the formation then
    names the base y — so a candidate that read either table with the wrong index, or that skipped
    the doubling on the base-y one, spawns the boss somewhere else."""
    _spawn_head_case(section, seed=section)


def test_spawn_head_overwrites_the_formations_own_sprite():
    """The spawner leaves the formation's graphics on both head records and this routine then
    replaces them — so the two records end with the head's sprite and a row count of one, not with
    whatever the formation's attributes said. Poison is what makes both stores attributable."""
    _spawn_head_case(0, seed=0x20, poison=True)


def test_spawn_head_fixes_up_exactly_two_records():
    """The third record must come back as the noise it went in as.

    THE PREMISE IS READ OFF THE IMAGE, not assumed: every section's formation places exactly
    MOTHERSHIP_HEAD_RECORDS actors, so the spawner never writes a third slot either and the only
    thing that could touch it is a head fixup loop one pass too long. The assertion below is what
    keeps that true — the day a section's formation asks for three, this case stops meaning what it
    says and fails here rather than silently.
    """
    for section in range(MOTHERSHIP_ENERGY_SECTIONS):
        formation = harness.BASE_IMAGE[A_MOTHERSHIP_FORMATION_BY_SECTION + section]
        record = int.from_bytes(
            bytes(harness.BASE_IMAGE[A_FORMATION_TABLE + 4 * formation:][:4]), "big")
        assert harness.BASE_IMAGE[record + FORMATION_COUNT] == MOTHERSHIP_HEAD_RECORDS, (
            f"section {section} spawns {harness.BASE_IMAGE[record + FORMATION_COUNT]} head actors")
    _spawn_head_case(3, seed=0x21)


# ======================================================= mothership_move_and_place @ 0x14fc8

def _move_and_place_case(head_x, explosion_bits=0, offscreen=0xa5, seed=0, poison=False):
    pokes = _boss_environment(0x21000 + seed)
    pokes[A_ENEMY_SLOTS] = _records(
        [_boss_record(0x21100 + seed + i, x=head_x[i] if i < len(head_x) else 0x100)
         for i in range(MOTHERSHIP_HEAD_RECORDS + 1)])
    pokes[A_ENTITY_BOSS_PARTS] = random.Random(0x21200 + seed).randbytes(
        (MOTHERSHIP_TAIL_SEGMENTS + 1) * ENTITY_STRIDE)
    pokes[A_EXPLOSION_GROUP_ACTIVE_BITS] = bytes([explosion_bits])
    pokes[A_MOTHERSHIP_OFFSCREEN] = bytes([offscreen])
    pokes[A_MOTHERSHIP_PREP_STAGE] = bytes([0x3c])
    pokes[A_MOTHERSHIP_X] = bytes([0x5a, 0x5a])
    pokes[A_MOTHERSHIP_Y] = bytes([0xa5, 0xa5])
    diffs, _ = differential(ENTRY_MOTHERSHIP_MOVE_AND_PLACE, {"_pokes": pokes},
                            lambda lib, buf: lib.g_mothership_move_and_place(buf), poison=poison)
    assert not diffs, f"head_x={[hex(x) for x in head_x]} bits={explosion_bits:#x}\n{report(diffs)}"


@pytest.mark.parametrize("bits", (0, 1, 2, 3, 0xff))
def test_move_and_place_stands_down_while_the_section_blast_runs(bits):
    """`btst #0,$19670` — only bit 0 stops it, so bit 1 (the ship's own explosion) must not."""
    _move_and_place_case((0x100, 0x100), explosion_bits=bits, seed=bits)


@pytest.mark.parametrize("x", (0, 1, 0x100, 0x1b7, 0x1b8, 0x1b9, 0x7fff, 0x8000, 0xffff))
def test_move_and_place_marks_the_boss_offscreen(x):
    """`tst.w` + `bmi` on the left and `cmpi.w #$1b8` + `bge` on the right, BOTH signed — so
    0x8000 and 0xffff are off the left edge and 0 is not. Driven on the first record and then on
    the second, since either one can raise the flag."""
    _move_and_place_case((x, 0x100), seed=0x10 + (x & 0xff))
    _move_and_place_case((0x100, x), seed=0x30 + (x & 0xff))


def test_move_and_place_clears_the_flag_first():
    """The flag is cleared at the top and set only by a record that is outside, so a call with both
    records inside must leave it clear whatever it held going in."""
    for offscreen in (0, 1, 0xff):
        _move_and_place_case((0x100, 0x100), offscreen=offscreen, seed=0x50 + offscreen)


def test_move_and_place_anchors_the_tail_on_the_first_record():
    """The anchor is the FIRST record's position less the two leads, whatever the second record is
    doing — driven with the two records far apart so a candidate reading the wrong one differs."""
    for first, second in ((0x100, 0x40), (0x40, 0x100), (0x1b7, 0x1b7)):
        _move_and_place_case((first, second), seed=0x60 + (first & 0xff))


def test_move_and_place_attribution():
    _move_and_place_case((0x100, 0x100), seed=0x70, poison=True)


# ====================================================== mothership_segments_update @ 0x151ba

def _segments_update_case(pairs, seed=0, poison=False):
    """`pairs` is one (alive, type, x) per segment pair; each pair is two records, stride 0x58."""
    records = []
    for pair, (alive, type_id, x) in enumerate(pairs):
        records.append(_boss_record(0x22000 + seed + pair, alive=alive, type_id=type_id, x=x))
        records.append(_Record(0x22100 + seed + pair))
    records.append(_Record(0x22200 + seed))          # the ninth record, which is the ship's own
    pokes = _boss_environment(0x22300 + seed)
    pokes[A_ENEMY_SLOTS] = _records(records)
    diffs, _ = differential(ENTRY_MOTHERSHIP_SEGMENTS_UPDATE, {"_pokes": pokes},
                            lambda lib, buf: lib.g_mothership_segments_update(buf), poison=poison)
    assert not diffs, f"pairs={pairs}\n{report(diffs)}"


ALL_SEGMENTS = ((1, MOTHERSHIP_SEGMENT_TYPE, 0x100),) * MOTHERSHIP_SEGMENT_PAIRS


@pytest.mark.parametrize("pair", range(MOTHERSHIP_SEGMENT_PAIRS))
def test_segments_update_runs_every_pair(pair):
    """One live segment at each of the four pair positions, which pins the 0x58 stride against the
    0x2c one — a candidate striding by a record would run the SHADOWS as segments."""
    pairs = tuple((1 if i == pair else 0, MOTHERSHIP_SEGMENT_TYPE, 0x100)
                  for i in range(MOTHERSHIP_SEGMENT_PAIRS))
    _segments_update_case(pairs, seed=pair)


@pytest.mark.parametrize("type_id", (0, 1, MOTHERSHIP_SEGMENT_TYPE, 3, 0x80, 0xff))
def test_segments_update_only_type_two(type_id):
    """The type guard is an EQUALITY on 2, which is what keeps this pass off the head records the
    same array holds — driven over the whole byte."""
    _segments_update_case(((1, type_id, 0x100),) * MOTHERSHIP_SEGMENT_PAIRS, seed=0x10 + type_id)


@pytest.mark.parametrize("alive", (0, 1, 0x80, 0xff))
def test_segments_update_skips_dead_pairs(alive):
    _segments_update_case(((alive, MOTHERSHIP_SEGMENT_TYPE, 0x100),) * MOTHERSHIP_SEGMENT_PAIRS,
                          seed=0x20 + alive)


@pytest.mark.parametrize("x", (0, 0x0f, 0x10, 0x11, 0x100, 0x1b7, 0x1b8, 0x1b9, 0x8000, 0xffff))
def test_segments_update_keep_band(x):
    """`cmpi.w #$10` + `ble` and `cmpi.w #$1b8` + `bge`, both SIGNED and one step either side.

    A segment outside the band takes BOTH records' alive bytes with it, and the shadow's position
    has already been written by then — so the case also says the mirror happens before the kill.
    """
    _segments_update_case(((1, MOTHERSHIP_SEGMENT_TYPE, x),) * MOTHERSHIP_SEGMENT_PAIRS,
                          seed=0x30 + (x & 0xff))


def test_segments_update_attribution():
    _segments_update_case(ALL_SEGMENTS, seed=0x40, poison=True)


# ===================================================== mothership_segments_respawn @ 0x1504a

def _segments_respawn_case(section, free=ENEMY_SLOT_COUNT, energy=0x20, seed=0, poison=False):
    pokes = _boss_environment(0x23000 + seed)
    pokes[A_ENEMY_SLOTS] = _records(
        [_Record(0x23100 + seed + i).byte(ENTITY_ALIVE, 0 if i < free else 1)
         for i in range(ENEMY_SLOT_COUNT + 1)])
    pokes[A_SQUADRON_KILL_COUNTERS] = bytes(6) + random.Random(seed).randbytes(0x40)
    pokes[A_ACTOR_SPAWN_TEMPLATE] = _noise(0x23300 + seed, ENTITY_STRIDE)
    # ORDER IS LOAD-BEARING: the counter band overlaps both the energy table and the section byte,
    # and `make_image` applies pokes in insertion order — so the wide noise goes down FIRST and the
    # two stated values are written over it. Seeded the other way round the section byte is noise,
    # the formation index it names is out of range, and the case tests nothing it claims to.
    pokes[A_ENEMY_PAIR_HITPOINTS] = random.Random(0x23200 + seed).randbytes(SEGMENT_HIT_COUNTER_BYTES)
    # NOISE over the whole energy table and the stated byte only at the section being driven. A
    # table filled with one value would make the INDEX untestable — every in-range section would
    # read the same byte, and a candidate that hard-coded section 0 would be green on all sixteen.
    pokes[A_MOTHERSHIP_ENERGY_BY_SECTION] = _noise(0x23400 + seed, MOTHERSHIP_ENERGY_SECTIONS)
    pokes[A_MOTHERSHIP_ENERGY_BY_SECTION + section] = bytes([energy])
    pokes[A_LEVEL_SECTION] = bytes([section])
    pokes[A_MOTHERSHIP_PREP_STAGE] = bytes([0x3c])
    diffs, _ = differential(ENTRY_MOTHERSHIP_SEGMENTS_RESPAWN, {"_pokes": pokes},
                            lambda lib, buf: lib.g_mothership_segments_respawn(buf), poison=poison)
    assert not diffs, f"section={section} free={free}\n{report(diffs)}"


@pytest.mark.parametrize("free", range(ENEMY_SLOT_COUNT + 1))
def test_segments_respawn_needs_every_slot_free(free):
    """`cmp.b #$8,d0` + `beq` — an EQUALITY on the count, so seven free slots is not enough and a
    candidate testing `>= 8` or `!= 0` agrees on some of these and not others."""
    _segments_respawn_case(0, free=free, seed=free)


@pytest.mark.parametrize("section", range(0x10))
def test_segments_respawn_every_section(section):
    """Each section's formation, fire-flags byte and energy byte, all read with the same
    sign-extended index — and the energy reaches four bytes of A_mothership_segment_energy, which
    is A_enemy_pair_hitpoints entered nine bytes in."""
    _segments_respawn_case(section, seed=0x10 + section)


def test_segments_respawn_energy_bytes_are_the_pairs_own():
    """The four bytes the respawn refills are exactly the ones `mothership_segment_hit` decrements,
    which is what makes the two routines one encounter rather than two.

    Derived TWICE and required to agree, which is the whole content: the left side runs the hit
    routine's own fold — `((entity index - 1) & ~1) + 1` off A_enemy_pair_hitpoints — over all eight
    boss slots, and the right side walks the respawn's base and stride. Neither restates the other,
    so moving either address, changing the stride, or changing the fold breaks it. That is the test
    `include/mothership.h` names as what holds its two derived addresses (CLAUDE.md §5).
    """
    first_wave_slot = (A_ENEMY_SLOTS - A_ENTITY_TABLE) // ENTITY_STRIDE
    hit_reaches = {A_ENEMY_PAIR_HITPOINTS + (((index - 1) & PAIR_INDEX_ALIGN) + 1)
                   for index in range(first_wave_slot,
                                      first_wave_slot + 2 * MOTHERSHIP_SEGMENT_PAIRS)}
    respawn_writes = {A_MOTHERSHIP_SEGMENT_ENERGY + MOTHERSHIP_SEGMENT_ENERGY_STRIDE * pair
                      for pair in range(MOTHERSHIP_SEGMENT_PAIRS)}
    assert hit_reaches == respawn_writes


def test_the_two_derived_addresses_this_subsystem_spells_as_literals():
    """`include/mothership.h` says both are derivations the original writes out as immediates, and
    this is where that claim is held rather than left in prose.

    The segment sprite is bank 1 of the boss preshift store — one whole bank past the base — and the
    score award is one past the third entry of `include/score.h`'s award table, which is the shape
    `score_add_bcd` takes its argument in. Move either base and this fails instead of the boss
    quietly pointing at an unbuilt bank or awarding another entry's digits.
    """
    assert A_MOTHERSHIP_SEGMENT_SPRITE == A_MOTHERSHIP_SPRITE_BANK + BANK_BYTES
    assert A_SCORE_VALUE_SEGMENT == A_SCORE_AWARD_TABLE_BCD + 3 * SCORE_BCD_BYTES


@pytest.mark.parametrize("energy", (0, 1, 0x20, 0x80, 0xff))
def test_segments_respawn_carries_the_sections_energy(energy):
    _segments_respawn_case(4, energy=energy, seed=0x30 + energy)


def test_segments_respawn_attribution():
    _segments_respawn_case(0, seed=0x40, poison=True)


# ========================================================== mothership_segment_hit @ 0x15222

SEGMENT_HIT_INDEXES = tuple(range(9, 17))       # both halves of all four boss pairs


SEGMENT_HIT_SCORE_SEEDS = (0x12345678, 0x99999999)   # ...and one that makes the BCD add CARRY


def _segment_hit_case(index, energy, score=SEGMENT_HIT_SCORE_SEEDS[0], seed=0, poison=False):
    pokes = _boss_environment(0x24000 + seed)
    pokes[A_ENEMY_SLOTS] = _records([_Record(0x24100 + seed + i)
                                     for i in range(ENEMY_SLOT_COUNT + 1)])
    pokes[A_PLAYER_SCORE_BCD] = score.to_bytes(4, "big")
    pokes[A_ENEMY_PAIR_HITPOINTS] = bytes([energy]) * SEGMENT_HIT_COUNTER_BYTES
    record = A_ENTITY_TABLE + index * ENTITY_STRIDE
    diffs, _ = differential(ENTRY_MOTHERSHIP_SEGMENT_HIT, {"a1": record, "_pokes": pokes},
                            lambda lib, buf: lib.g_mothership_segment_hit(buf, record),
                            poison=poison)
    assert not diffs, f"index={index} energy={energy:#x}\n{report(diffs)}"


@pytest.mark.parametrize("index", SEGMENT_HIT_INDEXES)
@pytest.mark.parametrize("energy", (1, 2, 0x80))
def test_segment_hit_folds_either_half_onto_the_pair(index, energy):
    """`((i - 1) & ~1) + 1` over the entity index, so 9 and 10 both cost pair 9 its energy.

    Driven at every one of the eight boss slots against an energy of 1 (which explodes), 2 (which
    only counts down) and 0x80 (the other side of the byte's sign) — the whole 0x20-byte counter
    array is seeded with the same value, so what tells the pairs apart is which byte MOVED.
    """
    _segment_hit_case(index, energy, seed=index * 4 + energy)


@pytest.mark.parametrize("energy", (1, 2, 0))
def test_segment_hit_explodes_at_zero_only(energy):
    """`subi.b #$1` + `bne`: only the transition to zero explodes, and an energy of 0 WRAPS to 0xff
    and survives — which is what separates the test from a `<= 0` bound."""
    _segment_hit_case(9, energy, seed=0x60 + energy)


def test_segment_hit_x_is_aligned_and_both_halves_explode():
    """The explosion rewrite covers BOTH records of the pair and aligns each x to four pixels, so a
    candidate that rewrote only the record it was given — or that aligned only one — differs.
    Poison is what makes each of the eight stores attributable."""
    for index in (9, 10, 15, 16):
        _segment_hit_case(index, energy=1, seed=0x70 + index, poison=True)


@pytest.mark.parametrize("score", SEGMENT_HIT_SCORE_SEEDS)
def test_segment_hit_awards_the_segment_score(score):
    """The kill runs `score_add_bcd` over the segment's own award, so the player's packed-BCD score
    moves — driven over a score that makes every digit of the add carry as well as one that does
    not, since `abcd` is the instruction and a binary add would agree on neither."""
    _segment_hit_case(9, energy=1, score=score, seed=0x80 + (score & 0xff))


def test_segment_hit_the_fold_this_battery_leans_on():
    """The parent index each of the eight slots folds onto, computed the way the routine does."""
    folds = {index: (((index - 1) & PAIR_INDEX_ALIGN) + 1) for index in SEGMENT_HIT_INDEXES}
    assert folds == {9: 9, 10: 9, 11: 11, 12: 11, 13: 13, 14: 13, 15: 15, 16: 15}


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
    ("A_LEVEL_SECTION", "include/init.h", "A_level_section"),
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
    # ---- wave 3: the encounter's own five routines ----
    ("A_ENTITY_TABLE", "include/player.h", "A_entity_table"),
    ("A_PLAYER_RECORD", "include/enemy.h", "A_player_record"),
    ("A_ACTOR_SPAWN_TEMPLATE", "include/enemy.h", "A_actor_spawn_template"),
    ("A_ENTITY_COLLISION_MASKS", "include/collision.h", "A_entity_collision_masks"),
    ("A_PLAYER_SCORE_BCD", "include/score.h", "A_player_score_bcd"),
    ("A_SCORE_VALUE_SEGMENT", "include/mothership.h", "A_score_value_segment"),
    ("A_RNG_LFSR_STATE", "include/rng.h", "A_rng_lfsr_state"),
    ("A_SQUADRON_KILL_COUNTERS", "include/enemy.h", "A_squadron_kill_counters"),
    ("A_ENEMY_PAIR_HITPOINTS", "include/enemy.h", "A_enemy_pair_hitpoints"),
    ("A_MOTHERSHIP_SEGMENT_ENERGY", "include/mothership.h", "A_mothership_segment_energy"),
    ("A_MOTHERSHIP_OFFSCREEN", "include/mothership.h", "A_mothership_offscreen"),
    ("A_EXPLOSION_GROUP_ACTIVE_BITS", "include/enemy.h", "A_explosion_group_active_bits"),
    ("A_MOTHERSHIP_FORMATION_BY_SECTION", "include/mothership.h",
     "A_mothership_formation_by_section"),
    ("A_MOTHERSHIP_SPAWN_PARAM_BY_SECTION", "include/mothership.h",
     "A_mothership_spawn_param_by_section"),
    ("A_MOTHERSHIP_HEAD_SPRITE", "include/mothership.h", "A_mothership_head_sprite"),
    ("A_MOTHERSHIP_SEGMENT_SPRITE", "include/mothership.h", "A_mothership_segment_sprite"),
    ("A_MOTHERSHIP_EXPLOSION_SPRITE", "include/mothership.h", "A_mothership_explosion_sprite"),
    ("A_SCROLL_FROZEN", "include/enemy.h", "A_scroll_frozen"),
    ("ENTITY_TYPE", "include/entity.h", "ENTITY_TYPE"),
    ("ACTOR_SCRIPT_DELAY", "include/enemy.h", "ACTOR_SCRIPT_DELAY"),
    ("ACTOR_SCRIPT_OPCODE", "include/enemy.h", "ACTOR_SCRIPT_OPCODE"),
    ("ACTOR_SCRIPT_LOOP_PC", "include/enemy.h", "ACTOR_SCRIPT_LOOP_PC"),
    ("ACTOR_SCRIPT_LOOP_COUNT", "include/enemy.h", "ACTOR_SCRIPT_LOOP_COUNT"),
    ("ACTOR_KEEP_X_MAX", "include/enemy.h", "ACTOR_KEEP_X_MAX"),
    ("COLLISION_ROW_BYTES", "include/collision.h", "COLLISION_ROW_BYTES"),
    ("MOTHERSHIP_PAIR_BYTES", "include/mothership.h", "MOTHERSHIP_PAIR_BYTES"),
    ("MOTHERSHIP_SEGMENT_PAIRS", "include/mothership.h", "MOTHERSHIP_SEGMENT_PAIRS"),
    ("MOTHERSHIP_HEAD_RECORDS", "include/mothership.h", "MOTHERSHIP_HEAD_RECORDS"),
    ("MOTHERSHIP_SHADOW_X_LEAD", "include/mothership.h", "MOTHERSHIP_SHADOW_X_LEAD"),
    ("MOTHERSHIP_SEGMENT_TYPE", "include/mothership.h", "MOTHERSHIP_SEGMENT_TYPE"),
    ("MOTHERSHIP_HEAD_TYPE", "include/mothership.h", "MOTHERSHIP_HEAD_TYPE"),
    ("MOTHERSHIP_HEAD_ROWS", "include/mothership.h", "MOTHERSHIP_HEAD_ROWS"),
    ("MOTHERSHIP_SEGMENT_ROWS", "include/mothership.h", "MOTHERSHIP_SEGMENT_ROWS"),
    ("MOTHERSHIP_SPAWN_X", "include/mothership.h", "MOTHERSHIP_SPAWN_X"),
    ("MOTHERSHIP_ANCHOR_X_LEAD", "include/mothership.h", "MOTHERSHIP_ANCHOR_X_LEAD"),
    ("MOTHERSHIP_ANCHOR_Y_LEAD", "include/mothership.h", "MOTHERSHIP_ANCHOR_Y_LEAD"),
    ("MOTHERSHIP_SEGMENT_KEEP_X_MIN", "include/mothership.h", "MOTHERSHIP_SEGMENT_KEEP_X_MIN"),
    ("PREP_STAGE_COPY", "src/mothership.c", "PREP_STAGE_COPY"),
    ("EXPLOSION_PART_TYPE", "include/enemy.h", "EXPLOSION_PART_TYPE"),
    ("EXPLOSION_X_ALIGN", "include/enemy.h", "EXPLOSION_X_ALIGN"),
    ("A_FORMATION_TABLE", "include/enemy.h", "A_formation_table"),
    ("A_SCORE_AWARD_TABLE_BCD", "include/score.h", "A_score_award_table_bcd"),
    ("SCORE_BCD_BYTES", "include/score.h", "SCORE_BCD_BYTES"),
    ("FORMATION_COUNT", "src/enemy.c", "FORMATION_COUNT"),
    ("MOTHERSHIP_SEGMENT_ENERGY_STRIDE", "src/mothership.c",
     "MOTHERSHIP_SEGMENT_ENERGY_STRIDE"),
    ("ENTITY_ALIVE_EXPLODING", "src/mothership.c", "ENTITY_ALIVE_EXPLODING"),
    ("PAIR_INDEX_ALIGN", "src/mothership.c", "PAIR_INDEX_ALIGN"),
)
ENTRY_PROLOGUES = {
    "ENTRY_MOTHERSHIP_PLACE_TAIL": "45f90001814249f90003",
    "ENTRY_MOTHERSHIP_SPRITE_BUILD_STEP": "0c390001000199116600",
    "ENTRY_MOTHERSHIP_BEGIN": "6100e94cb03c00086700",
    "ENTRY_MOTHERSHIP_DRAW": "45f9000181423c3c0004",
    "ENTRY_MOTHERSHIP_SPAWN_HEAD": "610008d2123c00011039",
    "ENTRY_MOTHERSHIP_MOVE_AND_PLACE": "08390000000196706700",
    "ENTRY_MOTHERSHIP_SEGMENTS_RESPAWN": "6100e7dcb03c00086700",
    "ENTRY_MOTHERSHIP_SEGMENTS_UPDATE": "45f900017c1a3e3c0003",
    "ENTRY_MOTHERSHIP_SEGMENT_HIT": "2a099abc00017a8e8afc",
}
