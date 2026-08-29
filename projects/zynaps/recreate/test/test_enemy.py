"""Differential tests for the enemy subsystem (src/enemy.c).

Three shapes of case live here, and the difference matters when reading a failure:

* a LONE RECORD parked at `abi.SCRATCH`, for the routines the dispatchers call with A2 already
  loaded (the movers, the animators, the script-VM opcode handlers);
* the GAME'S OWN ARRAYS at their real addresses, for the routines that load the base themselves
  (`count_free_wave_slots`, `anim_ground_objects`, the asteroid pair) — those are seeded in place
  rather than relocated, because the address IS part of what is being verified;
* a FLAG STUB (`abi.flag_call_pokes`), for the routines whose answer is a condition code the image
  diff cannot otherwise see.

Every record a case builds is noise everywhere the routine must not touch, so a candidate that
writes one byte too many differs instead of passing.
"""
import collections
import ctypes
import functools
import random

import pytest

import abi
import harness
from harness import differential, hi_garbage, report

# ---- entry addresses (pinned by ENTRY_PROLOGUES at the bottom) ----
ENTRY_COUNT_FREE_WAVE_SLOTS = 0x13828
ENTRY_ENEMY_ALLOC_SLOT = 0x14be0
ENTRY_ENTITY_TYPE_IN_MASK = 0x13bc2
ENTRY_ACTOR_CLAMP_Y = 0x14c44
ENTRY_ACTOR_DESPAWN = 0x14a64
ENTRY_ENEMY_MOVE_TYPE16_LEFT = 0x1499e
ENTRY_ENEMY_MOVE_TYPE17_LEFT = 0x14ec4
ENTRY_ENEMY_MOVE_TYPE15_DIVE = 0x149d2
ENTRY_ACTOR_SCRIPT_OP_LOOP_BEGIN = 0x14ce8
ENTRY_ACTOR_SCRIPT_OP_SET_FIRE_RATE = 0x14d00
ENTRY_ACTOR_SCRIPT_OP_DRIFT_LEFT = 0x14dc0
ENTRY_ACTOR_SCRIPT_OP_HALT = 0x14dd8
ENTRY_ACTOR_SCRIPT_OP_LOOP_END = 0x14e00
ENTRY_ACTOR_SCRIPT_OP_STEP_LEFT = 0x14e50
ENTRY_ANIM_ENEMY_TYPE12 = 0x14730
ENTRY_ANIM_ENEMY_TYPE14 = 0x1476e
ENTRY_ANIM_ENEMY_TYPE15_DIVING = 0x147ac
ENTRY_ANIM_ENEMY_TYPE17 = 0x1483e
ENTRY_ENEMY_SET_SPRITE_B = 0x1530e
ENTRY_ENEMY_ANIM_PUFF_B = 0x15332
ENTRY_ANIM_GROUND_OBJECTS = 0x14626
ENTRY_ASTEROIDS_MOVE = 0x159f2
ENTRY_ASTEROIDS_ANIMATE = 0x15a6a
ENTRY_ENTITY_PTR_FROM_INDEX = 0x141c0
ENTRY_ENTITY_PTR_FROM_INDEX_D6 = 0x141c2
ENTRY_ANIM_ENEMY_TYPE20 = 0x1467e
ENTRY_ANIM_ENEMY_TYPE22 = 0x146ba
ENTRY_ANIM_ENEMY_TYPE16 = 0x146f6
ENTRY_ENEMIES_ANIMATE_ALL = 0x147f2
ENTRY_ENEMY_MOVE_TYPE14_SINE = 0x1494a
ENTRY_ACTOR_SCRIPT_OP_BOUNCE_FALL = 0x14d14
ENTRY_ACTOR_SCRIPT_OP_SET_HEADING = 0x14da2
ENTRY_ACTOR_SCRIPT_OP_RANDOM_HEADING = 0x14de2
ENTRY_ACTOR_SCRIPT_OP_THRUST_TO_CENTRE_Y = 0x14e1c
ENTRY_ACTOR_SCRIPT_OP_AIM_AT_PLAYER = 0x14e38
ENTRY_ACTOR_SCRIPT_OP_THRUST_TO_CENTRE = 0x14e5c
ENTRY_ACTOR_SCRIPT_OP_RANDOM_SPEED_NUDGE = 0x14e8c
ENTRY_ACTOR_SCRIPT_CONTINUE = 0x14eb8
ENTRY_ACTOR_SCRIPT_OP_END_FRAME = 0x14ebe
ENTRY_EXPLOSION_ANIMATE_ALL = 0x1544e
ENTRY_EXPLOSION_SPAWN = 0x15510
ENTRY_ASTEROIDS_DRAW = 0x159be

# ---- record layout (mirrors of include/entity.h and include/enemy.h) ----
ENTITY_STRIDE = 0x2c
ENTITY_X, ENTITY_Y, ENTITY_SPRITE = 0x00, 0x04, 0x0a
ENTITY_HEIGHT = 0x08
ENTITY_ALIVE, ENTITY_TYPE = 0x0e, 0x11
ENTITY_DX, ENTITY_DY = 0x12, 0x14
ENTITY_ANIM_FRAME, ENTITY_SQUADRON = 0x20, 0x21
ACTOR_FIRE_COUNTDOWN, ACTOR_FIRE_RELOAD, ACTOR_DIVING = 0x1b, 0x1c, 0x1c
ACTOR_HEADING = 0x1d
ACTOR_SCRIPT_PC, ACTOR_SCRIPT_LOOP_PC, ACTOR_SCRIPT_LOOP_COUNT = 0x22, 0x24, 0x27
ASTEROID_Y_DESCENDING, ASTEROID_SLOW = 0x1e, 0x21
ENTITY_PIXEL_HIT = 0x0f
ENTITY_AX, ENTITY_AY = 0x16, 0x18
ACTOR_SPEED, ACTOR_BOUNCED = 0x1e, 0x29
ACTOR_SINE_BASE_Y, ACTOR_SINE_PHASE = 0x1a, 0x1c

# ---- the globals the routines address themselves ----
A_ENEMY_SLOTS = 0x17c1a
A_ASTEROID_RECORDS = 0x17e2a
A_ENTITY_TABLE = 0x17a8e
A_PLAYER_RECORD = 0x17d7a
A_SCROLL_FROZEN = 0x198b1
A_FREE_WAVE_SLOT_COUNT = 0x198b7
A_SQUADRON_KILL_COUNTERS = 0x198bb
A_ANIM_PHASE_B = 0x198ac
A_EXPLOSION_PHASE_ODD = 0x198c5
A_ASTEROID_ANIM_TOGGLE = 0x198fc
A_ANIM_FRAMES_TYPE12 = 0x1927c
A_ANIM_FRAMES_TYPE14 = 0x1926c
A_ANIM_FRAMES_TYPE15 = 0x1930c
A_ANIM_FRAMES_TYPE17 = 0x1925c
A_ANIM_FRAMES_GROUND_T34 = 0x1928c
A_PUFF_FRAME_PTRS_B = 0x192ec
A_ENEMY_SPRITE_PTRS_B = 0x192cc
A_SHOT_VARIANT_TABLE = 0x18f7c
A_ASTEROID_BANK_PTRS = 0x191e4
A_ENEMY_SHOT_SLOTS = 0x17b96
A_ACTOR_ANIM_TABLE = 0x193dc
A_ANIM_FRAMES_TYPE16 = 0x1929c
A_ANIM_FRAMES_TYPE20 = 0x191b4
A_ANIM_FRAMES_TYPE22 = 0x191cc
A_ANIM_FRAME_LIMIT_TYPE20 = 0x1990f
A_ANIM_FRAME_LIMIT_TYPE22 = 0x19910
A_RNG_LFSR_STATE = 0x195f4
A_ENTITY_COLLISION_MASKS = 0x18252
A_EXPLOSION_GROUP_ACTIVE_BITS = 0x19670
A_EXPLOSION_GROUP_MEMBERS = 0x19664
A_EXPLOSION_PARTICLE_OFFSETS = 0x195a8
A_EXPLOSION_SMALL_FRAME_PTRS = 0x191fc
A_EXPLOSION_FRAME_TOGGLE = 0x198ae
A_SCREEN_BACK = 0x1797e

# ---- geometry and loop counts (mirrors of src/enemy.c) ----
ENEMY_SLOT_COUNT = 8
GROUND_ACTOR_COUNT = 6
GROUND_ACTOR_TYPE = 0x34
GROUND_ANIM_FRAMES = 4
ASTEROID_GROUPS = 6
ASTEROID_COLUMNS = 3
ASTEROID_ANIM_FRAMES = 6
ANIM_CYCLE_END = 5
ANIM_TABLE_INDEX_MASK = 0xf
KEEP_Y_MIN, KEEP_Y_MAX = 0x10, 0xb0
KILL_X = 0x30
STEP_LEFT = 2
SCC_TRUE, SCC_FALSE = 0xff, 0x00
ACTOR_UPDATE_SLOTS = 11
ACTOR_HANDLER_TYPE_MAX = 0x32
ACTOR_CENTRE_X, ACTOR_CENTRE_Y = 0xd8, 0x60
ACTOR_FLOOR_Y = 0xa0
SINE_STEP_LEFT = 4
SINE_PHASE_STEP = 0x14
SIN_DEGREES_FULL = 0x168
COLLISION_ROW_BYTES = 4
NUDGE_MIN_DRAW, NUDGE_UP_DRAW = 0x55, 0xaa
RNG_TAP_MASK, RNG_STEP_BITS = 0x1d872b41, 16
FN_ACTOR_HANDLER_NONE = 0x148c8
SCREEN_BYTES = 32000
PLAYFIELD_TOP_Y = 32
SPRITE_MASKED_ROW_BYTES = 10
ASTEROID_FRAME_ROWS = 32
ASTEROID_FRAME_CELLS = 3

# ---- scratch layout ----
ACTOR = abi.SCRATCH                 # a lone record, for the handlers the dispatchers pre-load A2 for
BITMAP = abi.SCRATCH + 0x100        # the class bitmap entity_type_in_mask walks
FLAG = abi.RESULT                   # where the Scc stub — and each glue — leaves the flag byte
# `andi.w #$ff` admits all 256 types and `(type >> 3) & 0xfffe` turns the largest of them into a
# byte offset of 0x1e, so the bitmap a case seeds has to be this long even though the game's own
# class maps are eight bytes. Reading past them is the routine's behaviour, not the test's licence.
BITMAP_BYTES = 0x20

_u8p = ctypes.POINTER(ctypes.c_uint8)
_u32 = ctypes.c_uint32


def _bind(name, argc, restype=None):
    fn = getattr(harness._lib, name)
    fn.argtypes = [_u8p] + [_u32] * argc
    fn.restype = restype
    return fn


for _sym, _argc in (("g_count_free_wave_slots", 0), ("g_actor_clamp_y", 1),
                    ("g_actor_despawn", 1), ("g_enemy_move_type16_left", 1),
                    ("g_enemy_move_type17_left", 1), ("g_enemy_move_type15_dive", 1),
                    ("g_anim_enemy_type12", 1), ("g_anim_enemy_type14", 1),
                    ("g_anim_enemy_type15_diving", 1), ("g_anim_enemy_type17", 1),
                    ("g_enemy_set_sprite_b", 1), ("g_enemy_anim_puff_b", 1),
                    ("g_anim_ground_objects", 0), ("g_asteroids_move", 0),
                    ("g_asteroids_animate", 0),
                    ("g_entity_type_in_mask", 3),
                    ("g_actor_script_op_drift_left", 2), ("g_actor_script_op_halt", 2),
                    ("g_actor_script_op_loop_end", 2), ("g_actor_script_op_step_left", 2),
                    ("g_actor_script_op_loop_begin", 3),
                    ("g_actor_script_op_set_fire_rate", 3),
                    ("g_entity_ptr_from_index", 2),
                    ("g_anim_enemy_type16", 1), ("g_anim_enemy_type20", 1),
                    ("g_anim_enemy_type22", 1), ("g_enemies_animate_all", 0),
                    ("g_enemy_move_type14_sine", 1),
                    ("g_actor_script_op_bounce_fall", 2),
                    ("g_actor_script_op_set_heading", 3),
                    ("g_actor_script_op_random_heading", 2),
                    ("g_actor_script_op_aim_at_player", 2),
                    ("g_actor_script_op_thrust_to_centre_y", 2),
                    ("g_actor_script_op_thrust_to_centre", 2),
                    ("g_actor_script_op_random_speed_nudge", 2),
                    ("g_actor_script_continue", 1),
                    ("g_actor_script_op_end_frame", 1),
                    ("g_explosion_spawn", 2), ("g_explosion_animate_all", 0),
                    ("g_asteroids_draw", 0)):
    _bind(_sym, _argc)
_bind("g_enemy_alloc_slot", 2, restype=_u32)


class Record:
    """One 0x2c-byte actor record: noise everywhere, then the fields a case cares about.

    The noise is what makes an over-writing candidate fail — a record of zeroes would let a routine
    that clears a field it should not have touched pass unnoticed.
    """

    def __init__(self, seed):
        self.data = bytearray(random.Random(seed).randbytes(ENTITY_STRIDE))

    def byte(self, offset, value):
        self.data[offset] = value & 0xff
        return self

    def word(self, offset, value):
        self.data[offset:offset + 2] = (value & 0xffff).to_bytes(2, "big")
        return self

    def longword(self, offset, value):
        self.data[offset:offset + 4] = (value & 0xffffffff).to_bytes(4, "big")
        return self

    def bytes(self):
        return bytes(self.data)


def _array(records):
    """The concatenated bytes of a whole record array."""
    return b"".join(record.bytes() for record in records)


# Every fuzz test below splits its cases four ways so `-n auto` can spread them: case GENERATION is
# a generator seeded once, and each shard replays the whole stream and runs its own quarter, so the
# coverage is identical to one long loop (README.md, "Adding a function", step 4).
FUZZ_CHUNKS = 4


def _in_chunk(index, chunk):
    return index % FUZZ_CHUNKS == chunk


FLAG_CANARY = 0x5a   # neither SCC_TRUE nor SCC_FALSE, so an unwritten flag byte is a diff


def test_flag_canary_is_neither_answer():
    """The canary under the flag byte must be distinguishable from BOTH answers.

    This is what makes `SCC_TRUE`/`SCC_FALSE` mirrored constants rather than decoration: pick a
    canary equal to either one and every flag case goes silently half-blind — a candidate that never
    wrote the byte would match the oracle on exactly the arm that answers with that value.
    """
    assert FLAG_CANARY not in (SCC_TRUE, SCC_FALSE)
    assert FLAG_CANARY ^ 0xff not in (SCC_TRUE, SCC_FALSE)


# Every script-VM handler whose answer is a flag, and the subset of them that CLOBBER A0 on the way
# to it — the three heading ops walk it over the cosine table inside `entity_set_velocity_from_angle`
# and the bounce walks it over the entity table inside `collision_chain_walk`. A member gets the stub
# that loads A0 itself (test/abi.py, `flag_call_self_addressed_pokes`); everything else keeps the
# default stub, which stores through the RUN's own A0 and so also asserts the routine left it alone.
#
# THE SET IS PINNED IN BOTH DIRECTIONS by `test_a0_clobbering_entries_is_exactly_the_ones_that_do`
# below, against the oracle's own A0. That matters more than it looks: an entry added here that does
# NOT clobber A0 silently drops that routine's preservation assertion and nothing goes red, and an
# entry MISSING here reproduces the measured false bug the second stub was written to prevent — the
# `Scc` byte landing in the TEXT segment, `sine_table` coming back one byte different, and the flag
# byte still holding its canary.
SCRIPT_FLAG_ENTRIES = (ENTRY_ACTOR_SCRIPT_OP_LOOP_BEGIN, ENTRY_ACTOR_SCRIPT_OP_SET_FIRE_RATE,
                       ENTRY_ACTOR_SCRIPT_OP_BOUNCE_FALL, ENTRY_ACTOR_SCRIPT_OP_SET_HEADING,
                       ENTRY_ACTOR_SCRIPT_OP_DRIFT_LEFT, ENTRY_ACTOR_SCRIPT_OP_HALT,
                       ENTRY_ACTOR_SCRIPT_OP_RANDOM_HEADING, ENTRY_ACTOR_SCRIPT_OP_LOOP_END,
                       ENTRY_ACTOR_SCRIPT_OP_THRUST_TO_CENTRE_Y,
                       ENTRY_ACTOR_SCRIPT_OP_AIM_AT_PLAYER, ENTRY_ACTOR_SCRIPT_OP_STEP_LEFT,
                       ENTRY_ACTOR_SCRIPT_OP_THRUST_TO_CENTRE,
                       ENTRY_ACTOR_SCRIPT_OP_RANDOM_SPEED_NUDGE, ENTRY_ACTOR_SCRIPT_CONTINUE,
                       ENTRY_ACTOR_SCRIPT_OP_END_FRAME)

A0_CLOBBERING_ENTRIES = frozenset({ENTRY_ACTOR_SCRIPT_OP_BOUNCE_FALL,
                                   ENTRY_ACTOR_SCRIPT_OP_SET_HEADING,
                                   ENTRY_ACTOR_SCRIPT_OP_RANDOM_HEADING,
                                   ENTRY_ACTOR_SCRIPT_OP_AIM_AT_PLAYER})


def _flag_pokes(entry, condition):
    """The stub for a routine whose answer is a condition code, under a canary the stub overwrites.

    Two bytes, so the byte the stub does NOT write is seeded too — a candidate storing a word where
    the original stores a byte differs.
    """
    pokes = (abi.flag_call_self_addressed_pokes(entry, condition, FLAG)
             if entry in A0_CLOBBERING_ENTRIES else abi.flag_call_pokes(entry, condition))
    pokes[FLAG] = bytes([FLAG_CANARY, FLAG_CANARY ^ 0xff])
    return pokes


# ============================================================== count_free_wave_slots @ 0x13828

def _slot_pokes(alive_bytes, seed):
    """The eight wave records at their real address, with the alive byte of each one given."""
    records = [Record(seed + i).byte(ENTITY_ALIVE, alive) for i, alive in enumerate(alive_bytes)]
    return {A_ENEMY_SLOTS: _array(records),
            A_FREE_WAVE_SLOT_COUNT: bytes([0xa5])}     # a canary the routine must overwrite


def _count_case(alive_bytes, seed=1, poison=False):
    diffs, _ = differential(ENTRY_COUNT_FREE_WAVE_SLOTS,
                            {"_pokes": _slot_pokes(alive_bytes, seed)},
                            lambda lib, buf: lib.g_count_free_wave_slots(buf),
                            poison=poison)
    assert not diffs, f"alive={alive_bytes}\n{report(diffs)}"


def test_count_free_extremes():
    """None free, all free, and the two single-slot shapes that pin which end the walk starts at."""
    _count_case((1,) * ENEMY_SLOT_COUNT)
    _count_case((0,) * ENEMY_SLOT_COUNT, poison=True)
    _count_case((0,) + (1,) * (ENEMY_SLOT_COUNT - 1))
    _count_case((1,) * (ENEMY_SLOT_COUNT - 1) + (0,))


@pytest.mark.parametrize("alive", (0x01, 0x7f, 0x80, 0xff))
def test_count_free_tests_the_whole_byte(alive):
    """`tst.b` is a test against zero, not against 1 — every non-zero alive byte is "in use"."""
    _count_case((alive, 0, alive, 0, alive, 0, alive, 0))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_count_free_fuzz(chunk):
    rng = random.Random(ENTRY_COUNT_FREE_WAVE_SLOTS)
    for seed in range(60):
        alive = tuple(rng.randrange(256) for _ in range(ENEMY_SLOT_COUNT))
        if _in_chunk(seed, chunk):
            _count_case(alive, seed=seed)


# =================================================================== enemy_alloc_slot @ 0x14be0

def _alloc_case(alive_bytes, slot_in, seed=1, poison=False):
    """Call through the stub that stores the carry, and compare A2 against the oracle's own."""
    pokes = _flag_pokes(ENTRY_ENEMY_ALLOC_SLOT, "cs")
    pokes.update(_slot_pokes(alive_bytes, seed))
    regs = {"a0": FLAG, "a2": slot_in, "_pokes": pokes}
    diffs, info = differential(abi.STUB, regs,
                               lambda lib, buf: lib.g_enemy_alloc_slot(buf, slot_in, FLAG),
                               poison=poison)
    assert not diffs, f"alive={alive_bytes} a2={slot_in:#x}\n{report(diffs)}"
    assert info["ret"] == info["regs"]["a2"], (
        f"alive={alive_bytes}: slot cand={info['ret']:#x} oracle={info['regs']['a2']:#x}")


@pytest.mark.parametrize("free_index", range(ENEMY_SLOT_COUNT))
def test_alloc_finds_the_first_free_slot(free_index):
    """One free record at each position: the answer must be that record, not merely a free one."""
    alive = [1] * ENEMY_SLOT_COUNT
    alive[free_index] = 0
    _alloc_case(tuple(alive), slot_in=ACTOR)


def test_alloc_takes_the_lowest_of_several():
    _alloc_case((1, 1, 0, 1, 0, 0, 1, 0), slot_in=ACTOR, poison=True)


def test_alloc_fails_with_no_free_slot():
    """The failure arm never loads A2 at all, so the caller's own pointer must come back untouched —
    which is why `slot_in` is a recognisable address rather than zero."""
    _alloc_case((1,) * ENEMY_SLOT_COUNT, slot_in=ACTOR)
    _alloc_case((0xff,) * ENEMY_SLOT_COUNT, slot_in=A_PLAYER_RECORD)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_alloc_fuzz(chunk):
    rng = random.Random(ENTRY_ENEMY_ALLOC_SLOT)
    for seed in range(60):
        alive = tuple(rng.randrange(256) for _ in range(ENEMY_SLOT_COUNT))
        if _in_chunk(seed, chunk):
            _alloc_case(alive, slot_in=ACTOR, seed=seed)


# ================================================================ entity_type_in_mask @ 0x13bc2

def _mask_case(bitmap_bytes, type_reg, poison=False):
    pokes = _flag_pokes(ENTRY_ENTITY_TYPE_IN_MASK, "eq")
    pokes[BITMAP] = bitmap_bytes
    regs = {"a0": FLAG, "a6": BITMAP, "d0": type_reg, "_pokes": pokes}
    diffs, _ = differential(abi.STUB, regs,
                            lambda lib, buf: lib.g_entity_type_in_mask(buf, BITMAP, type_reg, FLAG),
                            poison=poison)
    assert not diffs, f"type={type_reg:#x}\n{report(diffs)}"


MASK_FUZZ_CHUNKS = 4


@pytest.mark.parametrize("chunk", range(MASK_FUZZ_CHUNKS))
def test_mask_every_type(chunk):
    """All 256 types the mask admits, against a bitmap whose every bit is distinguishable.

    A striped map would let a wrong bit number pass; this one is pseudorandom over the whole
    BITMAP_BYTES the largest type can reach, so a wrong word index and a wrong bit both diverge.
    """
    bitmap = random.Random(ENTRY_ENTITY_TYPE_IN_MASK).randbytes(BITMAP_BYTES)
    for type_reg in range(chunk, 0x100, MASK_FUZZ_CHUNKS):
        _mask_case(bitmap, type_reg)


@pytest.mark.parametrize("bit", range(16))
def test_mask_bit_order_is_msb_first(bit):
    """One bit set in the first word, and the one type that must see it.

    `not.w` + `andi.w #$f` means type N reads bit `15 - (N & 15)`, i.e. the map reads left to right
    across the big-endian word. A candidate numbering the bits the other way passes a symmetric
    pattern and fails here.
    """
    bitmap = (1 << bit).to_bytes(2, "big") + bytes(BITMAP_BYTES - 2)
    _mask_case(bitmap, 15 - bit)
    _mask_case(bitmap, (15 - bit) ^ 1)     # a neighbouring type must NOT see it


def test_mask_ignores_the_high_bits_of_d0():
    """`andi.w #$ff,d0` masks to a byte and nothing reads the rest of D0."""
    rng = random.Random(ENTRY_ENTITY_TYPE_IN_MASK + 1)
    bitmap = rng.randbytes(BITMAP_BYTES)
    for low in (0, 1, 0x0f, 0x10, 0x3f, 0xff):
        _mask_case(bitmap, hi_garbage(rng, low))
        _mask_case(bitmap, low | 0xff00)


def test_mask_attribution():
    bitmap = random.Random(ENTRY_ENTITY_TYPE_IN_MASK + 2).randbytes(BITMAP_BYTES)
    for type_reg in (0, 0x0f, 0x33, 0xff):
        _mask_case(bitmap, type_reg, poison=True)


# ====================================================================== actor_clamp_y @ 0x14c44

def _actor_case(entry, glue, record, poison=False, pokes=None, regs=None):
    """The shared shape: one record at ACTOR, A2 pointing at it, plus whatever else a case needs."""
    all_pokes = {ACTOR: record.bytes()}
    all_pokes.update(pokes or {})
    all_regs = {"a2": ACTOR, "_pokes": all_pokes}
    all_regs.update(regs or {})
    diffs, _ = differential(entry, all_regs, glue, poison=poison)
    assert not diffs, report(diffs)


CLAMP_Y_EDGES = (KEEP_Y_MIN - 1, KEEP_Y_MIN, KEEP_Y_MIN + 1,
                 KEEP_Y_MAX - 1, KEEP_Y_MAX, KEEP_Y_MAX + 1)


@pytest.mark.parametrize("y", CLAMP_Y_EDGES + (0, 0xffff, 0x7fff, 0x8000))
def test_clamp_y(y):
    """Both bounds one step either side, plus the far ends of the word.

    THE FLOOR'S SIGNEDNESS IS PINNED AND THE CEILING'S IS NOT, which is a property of the order the
    two run in rather than of this battery. 0x8000 read signed is below the floor and read unsigned
    is not, and the two readings write different values back — so `bge` is held. But whatever
    reaches the ceiling has already been through the floor, so it is 0x0010..0x7fff, where the two
    readings agree on every value. Measured: `blt` -> unsigned survives the whole suite, and
    STATUS.md's ledger records it as unreachable rather than untested.
    """
    _actor_case(ENTRY_ACTOR_CLAMP_Y, lambda lib, buf: lib.g_actor_clamp_y(buf, ACTOR),
                Record(y).word(ENTITY_Y, y), poison=(y == 0))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_clamp_y_fuzz(chunk):
    rng = random.Random(ENTRY_ACTOR_CLAMP_Y)
    for i in range(200):
        y = rng.randrange(KEEP_Y_MIN - 4, KEEP_Y_MAX + 4) if i % 3 else rng.randrange(1 << 16)
        if _in_chunk(i, chunk):
            _actor_case(ENTRY_ACTOR_CLAMP_Y, lambda lib, buf: lib.g_actor_clamp_y(buf, ACTOR),
                        Record(i).word(ENTITY_Y, y))


# ====================================================================== actor_despawn @ 0x14a64

COUNTER_BAND = 0x100   # every byte a sign-extended squadron id can reach, centred on the array


def _counter_pokes(seed=7):
    """Noise over the whole span a signed squadron id can reach, so a wrong index shows up.

    The id is sign-extended, so it addresses A_squadron_kill_counters - 0x80 .. + 0x7f. That band
    covers other globals of the game's own — names.txt's comment on the counters says as much —
    and seeding it here is what turns a mis-indexed decrement into a diff.

    IT SWALLOWS A_scroll_frozen AND THE OTHER GATE BYTES, which live inside that same band, so a
    case that wants a particular gate value must poke it AFTER this dict is built.
    `harness.make_image` applies pokes in insertion order, and every caller below relies on it.
    """
    return {A_SQUADRON_KILL_COUNTERS - COUNTER_BAND // 2: random.Random(seed).randbytes(COUNTER_BAND)}


@pytest.mark.parametrize("squadron", (0, 1, 5, 0x0f, 0x7f, 0x80, 0xff))
def test_despawn_credits_the_squadron(squadron):
    """The counter index is SIGN-EXTENDED, so 0x80..0xff reach below the array — transcribed."""
    _actor_case(ENTRY_ACTOR_DESPAWN, lambda lib, buf: lib.g_actor_despawn(buf, ACTOR),
                Record(squadron).byte(ENTITY_SQUADRON, squadron).byte(ENTITY_ALIVE, 1),
                pokes=_counter_pokes(), poison=True)


def test_despawn_counter_wraps():
    """`subi.b #1` on a counter of 0 wraps to 0xff — it does not saturate."""
    pokes = _counter_pokes()
    pokes[A_SQUADRON_KILL_COUNTERS] = bytes([0x00])
    _actor_case(ENTRY_ACTOR_DESPAWN, lambda lib, buf: lib.g_actor_despawn(buf, ACTOR),
                Record(11).byte(ENTITY_SQUADRON, 0).byte(ENTITY_ALIVE, 0xff), pokes=pokes)


@pytest.mark.parametrize("flag_word", (0xffff, 0xff01, 0x01ff, 0x0101))
def test_despawn_clears_only_the_alive_byte(flag_word):
    """`clr.b 14(a2)`, not `clr.w`: the pixel-hit byte at +0x0f must come back untouched.

    BOTH BYTES MUST BE NON-ZERO GOING IN, and an earlier revision of this case got that wrong — it
    seeded the pair as 0x00ff, so the alive byte was already 0 and the routine's only store wrote 0
    over 0. Deleting that store from the reconstruction then left this test green (measured). The
    parameter set now drives every combination of "set" for the two bytes, and poison attributes the
    store, so neither mistake can come back quietly.
    """
    _actor_case(ENTRY_ACTOR_DESPAWN, lambda lib, buf: lib.g_actor_despawn(buf, ACTOR),
                Record(12 + flag_word).byte(ENTITY_SQUADRON, 3).word(ENTITY_ALIVE, flag_word),
                pokes=_counter_pokes(), poison=True)


# ================================================================ the left-marching movers

def _mover_case(entry, glue_name, record, frozen=0, seed=0, poison=False):
    pokes = _counter_pokes(seed)
    pokes[A_SCROLL_FROZEN] = bytes([frozen])
    _actor_case(entry, lambda lib, buf: getattr(lib, glue_name)(buf, ACTOR), record,
                pokes=pokes, poison=poison)


# Every value is distinct AS A WORD: `Record.word` masks to 16 bits, so -1 and 0xffff would be one
# case run twice rather than a signed/unsigned pair.
MOVER_X_EDGES = (0, 1, 2, 3, 4, 0xfffe, 0xffff, KILL_X - 1, KILL_X, KILL_X + 1, KILL_X + 2,
                 0x7fff, 0x8000)


@pytest.mark.parametrize("x", MOVER_X_EDGES)
@pytest.mark.parametrize("frozen", (0, 1, 0xff))
def test_type16_left(x, frozen):
    """2 px/frame while the map moves; below zero it despawns and credits its squadron."""
    _mover_case(ENTRY_ENEMY_MOVE_TYPE16_LEFT, "g_enemy_move_type16_left",
                Record(x & 0xffff).word(ENTITY_X, x).byte(ENTITY_ALIVE, 1).byte(ENTITY_SQUADRON, 2),
                frozen=frozen)


@pytest.mark.parametrize("x", MOVER_X_EDGES)
def test_type17_left(x):
    """Retires at ACTOR_KILL_X rather than at zero, and never touches the squadron counters —
    which the seeded counter band is what proves."""
    _mover_case(ENTRY_ENEMY_MOVE_TYPE17_LEFT, "g_enemy_move_type17_left",
                Record(x & 0xffff).word(ENTITY_X, x).byte(ENTITY_ALIVE, 1).byte(ENTITY_SQUADRON, 2))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_movers_fuzz(chunk):
    rng = random.Random(ENTRY_ENEMY_MOVE_TYPE16_LEFT)
    for i in range(150):
        x = rng.randrange(-8, KILL_X + 8) if i % 2 else rng.randrange(1 << 16)
        record = (Record(i).word(ENTITY_X, x).byte(ENTITY_ALIVE, rng.randrange(1, 256))
                  .byte(ENTITY_SQUADRON, rng.randrange(256)))
        if _in_chunk(i, chunk):
            _mover_case(ENTRY_ENEMY_MOVE_TYPE16_LEFT, "g_enemy_move_type16_left", record,
                        frozen=i % 3 == 0, seed=i)
            _mover_case(ENTRY_ENEMY_MOVE_TYPE17_LEFT, "g_enemy_move_type17_left", record, seed=i)


def test_mover_attribution():
    _mover_case(ENTRY_ENEMY_MOVE_TYPE16_LEFT, "g_enemy_move_type16_left",
                Record(1).word(ENTITY_X, 1).byte(ENTITY_ALIVE, 1).byte(ENTITY_SQUADRON, 4),
                poison=True)
    _mover_case(ENTRY_ENEMY_MOVE_TYPE17_LEFT, "g_enemy_move_type17_left",
                Record(2).word(ENTITY_X, KILL_X).byte(ENTITY_ALIVE, 1), poison=True)


# ================================================================ enemy_move_type15_dive @ 0x149d2

def _dive_case(x, y, diving, player_x, player_y, frozen=0, seed=0, poison=False):
    pokes = _counter_pokes(seed)
    pokes[A_SCROLL_FROZEN] = bytes([frozen])
    pokes[A_PLAYER_RECORD] = (Record(0x1000 + seed).word(ENTITY_X, player_x)
                              .word(ENTITY_Y, player_y).bytes())
    record = (Record(seed).word(ENTITY_X, x).word(ENTITY_Y, y)
              .byte(ACTOR_DIVING, diving).byte(ENTITY_ALIVE, 1).byte(ENTITY_SQUADRON, 3))
    _actor_case(ENTRY_ENEMY_MOVE_TYPE15_DIVE,
                lambda lib, buf: lib.g_enemy_move_type15_dive(buf, ACTOR), record,
                pokes=pokes, poison=poison)


@pytest.mark.parametrize("gap", (-2, -1, 0, 1, 2))
def test_dive_arms_on_the_cone_edge(gap):
    """The dive arms exactly when `x - player.x <= |player.y - y|`, so a case sits either side of
    that boundary with the vertical gap held fixed."""
    player_y, y = 0x60, 0x40
    dy = abs(player_y - y)
    # x is read AFTER its own 2-pixel step, so the case offsets for that to land on the edge.
    _dive_case(x=0x100, y=y, diving=0, player_x=0x100 - STEP_LEFT - dy - gap, player_y=player_y)


@pytest.mark.parametrize("y", (KEEP_Y_MIN - 1, KEEP_Y_MIN, KEEP_Y_MIN + 1, KEEP_Y_MIN + 2, 0x50))
def test_dive_climbs_and_retires(y):
    """Armed, the diver rises 2 px/frame and is freed once it is above the playfield."""
    _dive_case(x=0x100, y=y, diving=1, player_x=0x40, player_y=0x50, poison=True)


@pytest.mark.parametrize("x", (-2, -1, 0, 1, 2, 3))
def test_dive_left_edge(x):
    """The 2-pixel step lands the despawn exactly at x < 2, and the cases straddle that.

    NOT ALL OF THEM DESPAWN, and the split is the point: -2..1 step below zero and free the record,
    while 2 and 3 write the stepped x back and carry on. An earlier revision named this test for the
    despawn alone while two of its parameters never reached that arm.
    """
    _dive_case(x=x, y=0x50, diving=0, player_x=0x40, player_y=0x50)


@pytest.mark.parametrize("frozen", (1, 0xff))
def test_dive_frozen_skips_the_march(frozen):
    """A frozen map suppresses the x step AND the arming test, but not the climb of an armed dive."""
    _dive_case(x=0x100, y=0x50, diving=0, player_x=0x100, player_y=0x50, frozen=frozen)
    _dive_case(x=0x100, y=0x50, diving=1, player_x=0x100, player_y=0x50, frozen=frozen)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_dive_fuzz(chunk):
    rng = random.Random(ENTRY_ENEMY_MOVE_TYPE15_DIVE)
    for i in range(200):
        case = dict(x=rng.randrange(-4, 0x1c0), y=rng.randrange(-4, 0xc0),
                    diving=rng.randrange(2) and rng.randrange(1, 256),
                    player_x=rng.randrange(1 << 16), player_y=rng.randrange(1 << 16),
                    frozen=(i % 5 == 0), seed=i)
        if _in_chunk(i, chunk):
            _dive_case(**case)


# ============================================================== the script VM's opcode handlers

SCRIPT_OPCODES = tuple(range(0x100))
SCRIPT_CHUNKS = 4


def _script_case(entry, glue, record, opcode=0, poison=False, frozen=0, pokes=None):
    all_pokes = _flag_pokes(entry, "cs")
    all_pokes[ACTOR] = record.bytes()
    all_pokes[A_SCROLL_FROZEN] = bytes([frozen])
    all_pokes.update(pokes or {})
    regs = {"a0": FLAG, "a2": ACTOR, "d1": opcode, "_pokes": all_pokes}
    diffs, _ = differential(abi.STUB, regs, glue, poison=poison)
    assert not diffs, f"opcode={opcode:#x}\n{report(diffs)}"


@pytest.mark.parametrize("chunk", range(SCRIPT_CHUNKS))
def test_op_loop_begin_every_opcode(chunk):
    """All 256 opcode bytes: `(d1 & 0x78) >> 3` must ignore bits 0..2 and bit 7 alike.

    The pc word is noise in each record, and it is copied to the loop-start word — so a candidate
    that copied the wrong way round, or copied a byte, differs.
    """
    for opcode in SCRIPT_OPCODES[chunk::SCRIPT_CHUNKS]:
        _script_case(ENTRY_ACTOR_SCRIPT_OP_LOOP_BEGIN,
                     lambda lib, buf, op=opcode: lib.g_actor_script_op_loop_begin(
                         buf, ACTOR, op, FLAG),
                     Record(opcode), opcode=opcode)


@pytest.mark.parametrize("chunk", range(SCRIPT_CHUNKS))
def test_op_set_fire_rate_every_opcode(chunk):
    for opcode in SCRIPT_OPCODES[chunk::SCRIPT_CHUNKS]:
        _script_case(ENTRY_ACTOR_SCRIPT_OP_SET_FIRE_RATE,
                     lambda lib, buf, op=opcode: lib.g_actor_script_op_set_fire_rate(
                         buf, ACTOR, op, FLAG),
                     Record(0x200 + opcode), opcode=opcode)


def test_operand_classes_ignore_the_high_bits_of_d1():
    """Only D1's low BYTE is read (`andi.b`), so junk anywhere above it must not move the answer.

    BOTH SIDES ARE HANDED THE SAME DIRTY REGISTER, which is the whole point: passing the oracle
    `hi_garbage` and the candidate a clean byte would test that the candidate ignores bits it was
    never given. `hi_garbage` fills bits 16..31 only, so bits 8..15 are driven separately — a
    reconstruction reading D1 as a WORD instead of a byte diverges on those and on nothing else.
    """
    rng = random.Random(ENTRY_ACTOR_SCRIPT_OP_SET_FIRE_RATE)
    for low in (0, 0x08, 0x78, 0x7f, 0xff):
        for dirty in (hi_garbage(rng, low), low | 0xab00, hi_garbage(rng, low | 0x5c00)):
            _script_case(ENTRY_ACTOR_SCRIPT_OP_SET_FIRE_RATE,
                         lambda lib, buf, op=dirty: lib.g_actor_script_op_set_fire_rate(
                             buf, ACTOR, op, FLAG),
                         Record(low), opcode=dirty)


@pytest.mark.parametrize("x", MOVER_X_EDGES)
@pytest.mark.parametrize("frozen", (0, 1))
def test_op_drift_left(x, frozen):
    """The freeze arm returns on `tst.b`, which clears the carry just as the moving arm does."""
    _script_case(ENTRY_ACTOR_SCRIPT_OP_DRIFT_LEFT,
                 lambda lib, buf: lib.g_actor_script_op_drift_left(buf, ACTOR, FLAG),
                 Record(x & 0xffff).word(ENTITY_X, x), frozen=frozen)


@pytest.mark.parametrize("x", MOVER_X_EDGES)
def test_op_step_left(x):
    """No freeze test at all: the step is unconditional, unlike the drift above."""
    _script_case(ENTRY_ACTOR_SCRIPT_OP_STEP_LEFT,
                 lambda lib, buf: lib.g_actor_script_op_step_left(buf, ACTOR, FLAG),
                 Record(x & 0xffff).word(ENTITY_X, x), frozen=1)


def test_op_halt_zeroes_both_velocity_words():
    """Both words are noise going in, so a candidate clearing one — or clearing a longword across
    the pair — differs."""
    for seed in range(8):
        _script_case(ENTRY_ACTOR_SCRIPT_OP_HALT,
                     lambda lib, buf: lib.g_actor_script_op_halt(buf, ACTOR, FLAG),
                     Record(seed), poison=True)


@pytest.mark.parametrize("count", (0, 1, 2, 0x7f, 0x80, 0xff))
def test_op_loop_end(count):
    """The rewind happens while the count is still non-zero AFTER the decrement, so a count of 1
    falls out of the loop and a count of 0 wraps to 0xff and stays in it."""
    _script_case(ENTRY_ACTOR_SCRIPT_OP_LOOP_END,
                 lambda lib, buf: lib.g_actor_script_op_loop_end(buf, ACTOR, FLAG),
                 Record(count).byte(ACTOR_SCRIPT_LOOP_COUNT, count), poison=True)


def test_op_loop_end_rewinds_the_pc_word():
    """pc and loop-start are distinct noise words, so copying the wrong direction fails."""
    for seed in range(8):
        _script_case(ENTRY_ACTOR_SCRIPT_OP_LOOP_END,
                     lambda lib, buf: lib.g_actor_script_op_loop_end(buf, ACTOR, FLAG),
                     Record(0x300 + seed).byte(ACTOR_SCRIPT_LOOP_COUNT, 4))


# =============================================================== the four-frame animation handlers

# The four handlers that share one C body, and the three things that differ between them: which
# half-frame byte gates each one, WHICH POLARITY of that byte lets it run, and its frame table.
# Named rather than positional because a case reads the polarity out of it and reading the table by
# mistake would silently make every "blocked" case a running one.
AnimHandler = collections.namedtuple("AnimHandler", "name entry glue gate_addr runs_when table")

ANIM_HANDLERS = (
    AnimHandler("type12", ENTRY_ANIM_ENEMY_TYPE12, "g_anim_enemy_type12",
                A_EXPLOSION_PHASE_ODD, 0, A_ANIM_FRAMES_TYPE12),
    AnimHandler("type14", ENTRY_ANIM_ENEMY_TYPE14, "g_anim_enemy_type14",
                A_EXPLOSION_PHASE_ODD, 0, A_ANIM_FRAMES_TYPE14),
    AnimHandler("type15", ENTRY_ANIM_ENEMY_TYPE15_DIVING, "g_anim_enemy_type15_diving",
                A_EXPLOSION_PHASE_ODD, 0, A_ANIM_FRAMES_TYPE15),
    AnimHandler("type17", ENTRY_ANIM_ENEMY_TYPE17, "g_anim_enemy_type17",
                A_ANIM_PHASE_B, 1, A_ANIM_FRAMES_TYPE17),
)


def _anim_case(handler, frame, gate, diving=1, poison=False):
    record = Record(frame ^ (gate << 8)).byte(ENTITY_ANIM_FRAME, frame).byte(ACTOR_DIVING, diving)
    _actor_case(handler.entry, lambda lib, buf: getattr(lib, handler.glue)(buf, ACTOR), record,
                pokes={handler.gate_addr: bytes([gate])}, poison=poison)


@pytest.mark.parametrize("handler", ANIM_HANDLERS, ids=lambda h: h.name)
@pytest.mark.parametrize("frame", (0, 1, 2, 3, 4, ANIM_CYCLE_END, 6, 0x0f, 0x10, 0x7f, 0x80, 0xff))
def test_anim_cycle_frames(handler, frame):
    """Every frame the cycle can hold plus the ones it cannot, against a live gate.

    The out-of-range frames are what pin `andi.l #$f`: 0x10 and 0x80 both resolve to a slot inside
    the sixteen the mask allows, where an unmasked index would run off the table.
    """
    _anim_case(handler, frame, gate=handler.runs_when)


# A gate byte is read with `tst.b`, so one of the two sides of every handler's test is a SINGLE
# value and the other is 255 of them. Which side is which flips with the handler's polarity, so both
# lists are derived from `runs_when` rather than written out twice.
GATE_SAMPLES = (0x00, 0x01, 0x02, 0x7f, 0x80, 0xff)


@pytest.mark.parametrize("handler", ANIM_HANDLERS, ids=lambda h: h.name)
@pytest.mark.parametrize("gate", GATE_SAMPLES)
def test_anim_gate_polarity(handler, gate):
    """Every sampled gate byte against every handler, running side and blocked side alike.

    THE MANY-VALUED SIDE IS WHAT MATTERS. Three of these run only while their byte is 0 and block on
    any other; type17 is the mirror, and blocks only on 0. Driving 0x01, 0x02, 0x7f, 0x80 and 0xff
    is what separates `tst.b` from an equality test — a candidate written as `gate == 1` passes a
    battery that only ever drives 0 and 1, which is what an earlier revision of this test did.
    """
    for frame in (1, 3, ANIM_CYCLE_END - 1):
        _anim_case(handler, frame, gate=gate)


def test_anim_frame_tables_are_distinguishable():
    """The four handlers share one C body, so their TABLE is the only thing separating them — and
    nothing pokes those tables, so the separation rests on the shipped image's own bytes.

    Asserting it here rather than assuming it: if two of the four held equal pointer arrays, a
    reconstruction that read the wrong table would pass every case above and this file's header
    comment about the shared prologues would be wrong.
    """
    slots = ANIM_TABLE_INDEX_MASK + 1
    banks = {handler.name: bytes(harness.BASE_IMAGE[handler.table:handler.table + slots * 4])
             for handler in ANIM_HANDLERS}
    assert len(set(banks.values())) == len(banks), f"two handlers read identical tables: {banks}"


def test_anim_type15_needs_its_dive_armed():
    """The diver's second gate, and the one that separates it from its three siblings."""
    handler = ANIM_HANDLERS[2]
    for frame in (1, 3, ANIM_CYCLE_END - 1):
        _anim_case(handler, frame, gate=0, diving=0)
    _anim_case(handler, 2, gate=0, diving=0x80)


@pytest.mark.parametrize("handler", ANIM_HANDLERS, ids=lambda h: h.name)
def test_anim_attribution(handler):
    _anim_case(handler, ANIM_CYCLE_END - 1, gate=handler.runs_when, poison=True)
    _anim_case(handler, 1, gate=handler.runs_when, poison=True)


# ================================================================== enemy_anim_puff_b @ 0x15332

@pytest.mark.parametrize("frame", (0, 1, 2, 3, 4, ANIM_CYCLE_END, 6, 0x7f, 0x80, 0xff))
def test_puff_kills_at_the_end_of_its_cycle(frame):
    """The one handler whose fifth frame clears the record instead of wrapping to the first."""
    record = Record(0x400 + frame).byte(ENTITY_ANIM_FRAME, frame).byte(ENTITY_ALIVE, 1)
    _actor_case(ENTRY_ENEMY_ANIM_PUFF_B, lambda lib, buf: lib.g_enemy_anim_puff_b(buf, ACTOR),
                record, pokes={A_EXPLOSION_PHASE_ODD: bytes([0])},
                poison=frame in (3, ANIM_CYCLE_END - 1))


@pytest.mark.parametrize("gate", (1, 0x80, 0xff))
def test_puff_gate_blocks(gate):
    record = Record(0x420 + gate).byte(ENTITY_ANIM_FRAME, 2).byte(ENTITY_ALIVE, 1)
    _actor_case(ENTRY_ENEMY_ANIM_PUFF_B, lambda lib, buf: lib.g_enemy_anim_puff_b(buf, ACTOR),
                record, pokes={A_EXPLOSION_PHASE_ODD: bytes([gate])})


# ================================================================== enemy_set_sprite_b @ 0x1530e

SET_SPRITE_CHUNKS = 4
# The heading and the variant byte are both sign-extended, so the two tables are read across
# [base - 0x80, base + 0x7f] and [base - 0x200, base + 0x1fc]. Seeding those spans is what turns a
# dropped `ext.w` into a diff instead of a coincidence.
VARIANT_SPAN = 0x100
SPRITE_PTR_SPAN = 0x400


def _set_sprite_pokes(seed):
    rng = random.Random(seed)
    return {A_SHOT_VARIANT_TABLE - VARIANT_SPAN // 2: rng.randbytes(VARIANT_SPAN),
            A_ENEMY_SPRITE_PTRS_B - SPRITE_PTR_SPAN // 2: rng.randbytes(SPRITE_PTR_SPAN)}


@pytest.mark.parametrize("chunk", range(SET_SPRITE_CHUNKS))
def test_set_sprite_every_heading(chunk):
    """All 256 headings, over seeded tables — which drives both sign extensions on real data."""
    pokes = _set_sprite_pokes(ENTRY_ENEMY_SET_SPRITE_B)
    for heading in range(chunk, 0x100, SET_SPRITE_CHUNKS):
        _actor_case(ENTRY_ENEMY_SET_SPRITE_B,
                    lambda lib, buf: lib.g_enemy_set_sprite_b(buf, ACTOR),
                    Record(heading).byte(ACTOR_HEADING, heading), pokes=pokes)


def test_set_sprite_attribution():
    pokes = _set_sprite_pokes(ENTRY_ENEMY_SET_SPRITE_B + 1)
    for heading in (0, 0x0f, 0x80, 0xff):
        _actor_case(ENTRY_ENEMY_SET_SPRITE_B,
                    lambda lib, buf: lib.g_enemy_set_sprite_b(buf, ACTOR),
                    Record(heading).byte(ACTOR_HEADING, heading), pokes=pokes, poison=True)


# ================================================================= anim_ground_objects @ 0x14626

GROUND_FRAME_SPAN = 0x400   # `ext.w` again: a frame byte of 0x80 reaches 0x200 below the table


def _ground_case(records, gate=0, seed=0, poison=False):
    pokes = {A_ENTITY_TABLE: _array(records),
             A_EXPLOSION_PHASE_ODD: bytes([gate]),
             A_ANIM_FRAMES_GROUND_T34 - GROUND_FRAME_SPAN // 2:
                 random.Random(seed).randbytes(GROUND_FRAME_SPAN)}
    diffs, _ = differential(ENTRY_ANIM_GROUND_OBJECTS, {"_pokes": pokes},
                            lambda lib, buf: lib.g_anim_ground_objects(buf), poison=poison)
    assert not diffs, report(diffs)


def _ground_record(seed, alive, type_id, frame):
    return (Record(seed).byte(ENTITY_ALIVE, alive).byte(ENTITY_TYPE, type_id)
            .byte(ENTITY_ANIM_FRAME, frame))


@pytest.mark.parametrize("frame", (0, 1, 2, 3, GROUND_ANIM_FRAMES, 5, 0x7e, 0x7f, 0x80, 0xff))
def test_ground_cycles_every_live_type34(frame):
    """Six live scenery actors on the same frame: the cycle counts 0..3, wrapping with a SIGNED
    comparison, so 0x7f steps to 0x80 and is kept as a negative table index."""
    _ground_case([_ground_record(frame * 8 + i, 1, GROUND_ACTOR_TYPE, frame)
                  for i in range(GROUND_ACTOR_COUNT)], poison=frame == 1)


def test_ground_skips_dead_and_wrong_type():
    """Both guards, and their interaction: only a live type-0x34 record animates."""
    records = [_ground_record(50, 0, GROUND_ACTOR_TYPE, 1),      # dead
               _ground_record(51, 1, GROUND_ACTOR_TYPE - 1, 1),  # wrong type
               _ground_record(52, 1, GROUND_ACTOR_TYPE + 1, 1),
               _ground_record(53, 1, GROUND_ACTOR_TYPE, 2),      # animates
               _ground_record(54, 0, 0, 3),
               _ground_record(55, 0xff, GROUND_ACTOR_TYPE, 0)]   # animates
    _ground_case(records, poison=True)


@pytest.mark.parametrize("gate", (1, 0x80, 0xff))
def test_ground_gate_blocks(gate):
    _ground_case([_ground_record(60 + i, 1, GROUND_ACTOR_TYPE, i) for i in range(6)], gate=gate)


def test_ground_walks_exactly_six_records():
    """A seventh live type-0x34 record beyond the six must be left alone — which is what pins the
    loop count, since the records past it are the enemy-shot slots."""
    records = [_ground_record(70 + i, 1, GROUND_ACTOR_TYPE, 1)
               for i in range(GROUND_ACTOR_COUNT + 2)]
    _ground_case(records)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_ground_fuzz(chunk):
    rng = random.Random(ENTRY_ANIM_GROUND_OBJECTS)
    for seed in range(50):
        records = [_ground_record(seed * 8 + i, rng.randrange(256),
                                  GROUND_ACTOR_TYPE if rng.randrange(2) else rng.randrange(256),
                                  rng.randrange(256))
                   for i in range(GROUND_ACTOR_COUNT)]
        if _in_chunk(seed, chunk):
            _ground_case(records, gate=0, seed=seed)


# ======================================================================= the asteroid columns

ASTEROID_RECORD_COUNT = ASTEROID_GROUPS * ASTEROID_COLUMNS
ASTEROID_BANK_SPAN = 0x400   # the same sign-extended reach as the other frame tables


def _asteroid_pokes(records, seed):
    return {A_ASTEROID_RECORDS: _array(records),
            A_ASTEROID_BANK_PTRS - ASTEROID_BANK_SPAN // 2:
                random.Random(seed).randbytes(ASTEROID_BANK_SPAN)}


def _asteroid_record(seed, alive, x, y, descending, slow, frame=0):
    return (Record(seed).byte(ENTITY_ALIVE, alive).word(ENTITY_X, x).word(ENTITY_Y, y)
            .byte(ASTEROID_Y_DESCENDING, descending).byte(ASTEROID_SLOW, slow)
            .byte(ENTITY_ANIM_FRAME, frame))


def _asteroid_move_case(records, seed=0, poison=False):
    diffs, _ = differential(ENTRY_ASTEROIDS_MOVE, {"_pokes": _asteroid_pokes(records, seed)},
                            lambda lib, buf: lib.g_asteroids_move(buf), poison=poison)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("y", (0, 1, KEEP_Y_MAX - 2, KEEP_Y_MAX - 1, KEEP_Y_MAX, KEEP_Y_MAX + 1,
                               -1, 0x7fff, 0x8000))
@pytest.mark.parametrize("descending", (0, 1))
def test_asteroid_y_wrap(y, descending):
    """The wrap is asymmetric: past the bottom the column restarts at 0, past the top at 0xb0.

    Both directions are driven at every edge, so a candidate that used one range check for both
    diverges at 0 going up.
    """
    _asteroid_move_case([_asteroid_record(y * 4 + descending + i, 1, 0x100, y, descending, 0)
                         for i in range(ASTEROID_RECORD_COUNT)])


@pytest.mark.parametrize("x", (0, 1, 2, 3, 4, 5, -1, 0x7fff, 0x8000))
@pytest.mark.parametrize("slow", (0, 1))
def test_asteroid_x_step_and_kill(x, slow):
    """Two or four pixels a frame, and the kill below zero — which is why both step widths are
    driven against the same x values."""
    _asteroid_move_case([_asteroid_record(x * 4 + slow + i, 1, x, 0x50, 0, slow)
                         for i in range(ASTEROID_RECORD_COUNT)])


def test_asteroid_move_skips_dead_records():
    records = [_asteroid_record(90 + i, i % 2, 0x100, 0x50, i % 3 == 0, i % 2)
               for i in range(ASTEROID_RECORD_COUNT)]
    _asteroid_move_case(records, poison=True)


def test_asteroid_move_walks_exactly_eighteen():
    """A nineteenth record — the first boss part — must be untouched, which pins 6 x 3."""
    records = [_asteroid_record(100 + i, 1, 0x100, 0x50, 0, 0)
               for i in range(ASTEROID_RECORD_COUNT + 2)]
    _asteroid_move_case(records)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_asteroid_move_fuzz(chunk):
    rng = random.Random(ENTRY_ASTEROIDS_MOVE)
    for seed in range(40):
        records = [_asteroid_record(seed * 32 + i, rng.randrange(256),
                                    rng.randrange(-8, 0x1c0), rng.randrange(-8, 0xc0),
                                    rng.randrange(256), rng.randrange(256))
                   for i in range(ASTEROID_RECORD_COUNT)]
        if _in_chunk(seed, chunk):
            _asteroid_move_case(records, seed=seed)


def _asteroid_anim_case(records, toggle, seed=0, poison=False):
    pokes = _asteroid_pokes(records, seed)
    pokes[A_ASTEROID_ANIM_TOGGLE] = bytes([toggle])
    diffs, _ = differential(ENTRY_ASTEROIDS_ANIMATE, {"_pokes": pokes},
                            lambda lib, buf: lib.g_asteroids_animate(buf), poison=poison)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("toggle", (0x00, 0xff, 0x01, 0x80))
def test_asteroid_animate_half_rate_gate(toggle):
    """`not.b` flips the toggle AND tests it, so the frames advance only on the call that leaves it
    zero — and the flip itself happens on every call, gate or no gate."""
    _asteroid_anim_case([_asteroid_record(110 + i, 1, 0x100, 0x50, 0, 0, frame=i % 6)
                         for i in range(ASTEROID_RECORD_COUNT)], toggle=toggle)


@pytest.mark.parametrize("frame", (0, 1, 4, ASTEROID_ANIM_FRAMES - 1, ASTEROID_ANIM_FRAMES,
                                   0x7f, 0x80, 0xff))
def test_asteroid_animate_cycles_six_frames(frame):
    """Six frames, counted 0..5, with the same signed wrap the ground objects use."""
    _asteroid_anim_case([_asteroid_record(120 + frame * 32 + i, 1, 0x100, 0x50, 0, 0, frame=frame)
                         for i in range(ASTEROID_RECORD_COUNT)], toggle=0xff,
                        poison=frame == ASTEROID_ANIM_FRAMES - 1)


def test_asteroid_animate_column_offset_is_positional():
    """The three records of a group read the SAME bank pointer and add 0, 0x140, 0x280 — and the
    offset advances over a DEAD record too, so killing the middle column must not shift the third.
    """
    records = [_asteroid_record(200 + i, 0 if i % 3 == 1 else 1, 0x100, 0x50, 0, 0, frame=1)
               for i in range(ASTEROID_RECORD_COUNT)]
    _asteroid_anim_case(records, toggle=0xff, poison=True)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_asteroid_animate_fuzz(chunk):
    rng = random.Random(ENTRY_ASTEROIDS_ANIMATE)
    for seed in range(40):
        records = [_asteroid_record(seed * 32 + i, rng.randrange(256), 0x100, 0x50, 0, 0,
                                    frame=rng.randrange(256))
                   for i in range(ASTEROID_RECORD_COUNT)]
        if _in_chunk(seed, chunk):
            _asteroid_anim_case(records, toggle=0xff if seed % 2 else 0x00, seed=seed)



# ================================================================ entity_ptr_from_index @ 0x141c0

# The stub stores D6 then A1 as longwords; the third longword is a canary neither side writes, so a
# candidate storing more than the two registers the routine leaves behind differs.
PTR_RESULT_BYTES = 12


def _ptr_case(entry, index_reg, other_reg=0, poison=False):
    """Call one entry of the index->record helper and compare BOTH registers it leaves behind.

    `index_reg` is the register that entry reads — D0 at 0x141c0, D6 at 0x141c2 — and `other_reg`
    is whatever the case wants in the one it does not, which must not reach the answer.
    """
    from_d6 = entry == ENTRY_ENTITY_PTR_FROM_INDEX_D6
    pokes = abi.register_call_pokes(entry, ("d6", "a1"))
    pokes[abi.RESULT] = random.Random(entry ^ index_reg).randbytes(PTR_RESULT_BYTES)
    regs = {"a0": abi.RESULT,
            "d0": other_reg if from_d6 else index_reg,
            "d6": index_reg if from_d6 else other_reg,
            "_pokes": pokes}
    diffs, _ = differential(abi.STUB, regs,
                            lambda lib, buf: lib.g_entity_ptr_from_index(buf, index_reg,
                                                                         abi.RESULT),
                            poison=poison)
    assert not diffs, f"entry={entry:#x} index={index_reg:#x}\n{report(diffs)}"


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_entity_ptr_every_index(chunk):
    """All 256 indices `and.l #$ff` admits, sharded.

    Exhaustive rather than sampled because the routine's whole content is that mask and the
    multiply: only the far end of the byte separates `mulu.w #$2c` from a 16-bit product, and only
    the mask stops index 20..0xff from being refused — the game's table holds 20 records and nothing
    here bounds the index to them, so the answer walks up to 0x1c68 bytes past it.
    """
    for index in range(chunk, 0x100, FUZZ_CHUNKS):
        _ptr_case(ENTRY_ENTITY_PTR_FROM_INDEX, index)


def test_entity_ptr_ignores_the_bits_above_the_byte():
    """`move.b d0,d6` copies a byte and `and.l #$ff,d6` clears what the caller left above it, so
    neither D0's high bits nor D6's incoming value can reach the answer."""
    rng = random.Random(ENTRY_ENTITY_PTR_FROM_INDEX + 1)
    for index in (0, 1, 9, 19, 0xff):
        _ptr_case(ENTRY_ENTITY_PTR_FROM_INDEX, hi_garbage(rng, index),
                  other_reg=rng.randrange(1 << 32))
        _ptr_case(ENTRY_ENTITY_PTR_FROM_INDEX, index | 0xff00, other_reg=0xffffffff)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_entity_ptr_d6_entry(chunk):
    """0x141c2 is the SAME body entered one instruction later, with the index already in D6 — so
    every case here hands D6 a full longword and D0 something else entirely."""
    rng = random.Random(ENTRY_ENTITY_PTR_FROM_INDEX_D6)
    for i in range(64):
        index, junk = rng.randrange(1 << 32), rng.randrange(1 << 32)
        if _in_chunk(i, chunk):
            _ptr_case(ENTRY_ENTITY_PTR_FROM_INDEX_D6, index, other_reg=junk)


def test_entity_ptr_attribution():
    for index in (0, 9, 0x80, 0xff):
        _ptr_case(ENTRY_ENTITY_PTR_FROM_INDEX, index, poison=True)


# ======================================== the OTHER animation cycle — types 16, 20 and 22

# The three handlers whose index into their frame table is NOT masked, and whose gate is the other
# phase byte. `limit_addr` is None for the one whose frame count is a literal.
LimitAnimHandler = collections.namedtuple("LimitAnimHandler",
                                          "name entry glue table limit_addr limit")

LIMIT_ANIM_HANDLERS = (
    LimitAnimHandler("type16", ENTRY_ANIM_ENEMY_TYPE16, "g_anim_enemy_type16",
                     A_ANIM_FRAMES_TYPE16, None, ANIM_CYCLE_END),
    LimitAnimHandler("type20", ENTRY_ANIM_ENEMY_TYPE20, "g_anim_enemy_type20",
                     A_ANIM_FRAMES_TYPE20, A_ANIM_FRAME_LIMIT_TYPE20, 5),
    LimitAnimHandler("type22", ENTRY_ANIM_ENEMY_TYPE22, "g_anim_enemy_type22",
                     A_ANIM_FRAMES_TYPE22, A_ANIM_FRAME_LIMIT_TYPE22, 5),
)

# How far past its own base an unmasked frame byte reaches: 0xff frames of four bytes each. The span
# is seeded so that a candidate masking the index the way the four-frame handlers do lands on
# different noise and differs, instead of quietly reading a plausible pointer.
UNMASKED_TABLE_SPAN = 0x100 * 4


def _limit_anim_case(handler, frame, gate=0, limit=None, seed=0, poison=False):
    pokes = abi.seed_spans(handler.entry + seed,
                           [(handler.table, handler.table + UNMASKED_TABLE_SPAN)])
    pokes[A_ANIM_PHASE_B] = bytes([gate])
    if handler.limit_addr is not None:
        pokes[handler.limit_addr] = bytes([handler.limit if limit is None else limit])
    _actor_case(handler.entry, lambda lib, buf: getattr(lib, handler.glue)(buf, ACTOR),
                Record(frame ^ (seed << 8)).byte(ENTITY_ANIM_FRAME, frame),
                pokes=pokes, poison=poison)


@pytest.mark.parametrize("handler", LIMIT_ANIM_HANDLERS, ids=lambda h: h.name)
@pytest.mark.parametrize("frame", (0, 1, 2, 3, 4, 5, 6, 7, 0x0f, 0x10, 0x11, 0x7f, 0x80, 0xfe,
                                   0xff))
def test_limit_anim_cycles_and_indexes_unmasked(handler, frame):
    """Every frame the cycle reaches and the ones it cannot, against a live gate.

    TWO THINGS SEPARATE THESE THREE FROM THE FOUR ABOVE, and both are driven here. The wrap is an
    EQUALITY test, so frame 6 against a limit of 5 counts on to 7 where a `>=` bound would restart;
    and the table index is UNMASKED, so 0x10 reads 0x3c bytes into the table rather than the 0 an
    `andi.l #$f` would give, and 0xff reaches 0x3f8 past its base. The seeded span is what makes
    both of those a difference rather than a coincidence.
    """
    _limit_anim_case(handler, frame)


@pytest.mark.parametrize("handler", LIMIT_ANIM_HANDLERS, ids=lambda h: h.name)
@pytest.mark.parametrize("gate", (1, 2, 0x7f, 0x80, 0xff))
def test_limit_anim_gate_blocks(handler, gate):
    """All three run only while A_anim_phase_b is ZERO — the opposite half-frame to type17's, and a
    different byte from the one the four-frame handlers read. Five blocking values, not one, so
    `tst.b` is held against an equality test."""
    _limit_anim_case(handler, frame=2, gate=gate)


@pytest.mark.parametrize("handler", LIMIT_ANIM_HANDLERS[1:], ids=lambda h: h.name)
@pytest.mark.parametrize("limit", (0, 1, 2, 3, 5, 6, 0x7f, 0x80, 0xff))
def test_limit_anim_reads_its_limit_byte(handler, limit):
    """The two per-section handlers take their cycle length from a GLOBAL, and the frame here steps
    onto each limit exactly — so a candidate that hard-coded 5 differs everywhere but at 5, and one
    that read the other section's byte differs everywhere."""
    _limit_anim_case(handler, frame=(limit - 1) & 0xff, limit=limit)


def test_limit_anim_frame_tables_are_distinguishable():
    """The three share one C body, so their tables are the only thing telling them apart — assert
    the shipped image really does hold three different ones rather than leaving that to luck."""
    rows = {h.name: bytes(harness.BASE_IMAGE[h.table:h.table + 4 * 8])
            for h in LIMIT_ANIM_HANDLERS}
    assert len(set(rows.values())) == len(rows), rows


@pytest.mark.parametrize("handler", LIMIT_ANIM_HANDLERS, ids=lambda h: h.name)
def test_limit_anim_attribution(handler):
    _limit_anim_case(handler, frame=1, poison=True)
    _limit_anim_case(handler, frame=0x80, seed=3, poison=True)

# ================================================================ enemies_animate_all @ 0x147f2

# The types the shipped table gives a handler to, and two inert ones. Read off the image rather than
# remembered: `test_anim_table_is_fully_reconstructed` below asserts the table agrees.
ANIMATED_TYPES = (0x06, 0x0b, 0x0c, 0x0e, 0x0f, 0x10, 0x11, 0x14, 0x16)
INERT_TYPES = (0x00, 0x0d)

# The ten addresses src/enemy.c's ACTOR_ANIM_HANDLERS maps, in its order.
ANIM_HANDLER_ADDRESSES = (FN_ACTOR_HANDLER_NONE, ENTRY_ANIM_ENEMY_TYPE20,
                          ENTRY_ANIM_ENEMY_TYPE22, ENTRY_ANIM_ENEMY_TYPE16,
                          ENTRY_ANIM_ENEMY_TYPE12, ENTRY_ANIM_ENEMY_TYPE14,
                          ENTRY_ANIM_ENEMY_TYPE15_DIVING, ENTRY_ANIM_ENEMY_TYPE17,
                          ENTRY_ENEMY_SET_SPRITE_B, ENTRY_ENEMY_ANIM_PUFF_B)
# (A_actor_anim_table's own extent: it runs to the script class table that follows it.)
ACTOR_ANIM_TABLE_ENTRIES = 23

# Every frame-pointer table the ten handlers read, as two spans. Seeded with noise so that a
# candidate dispatching to the WRONG handler writes a pointer out of the wrong table and differs,
# rather than happening to agree because two shipped tables share an entry.
ANIM_TABLE_SPANS = ((A_ANIM_FRAMES_TYPE20, A_ASTEROID_BANK_PTRS),
                    (A_ANIM_FRAMES_TYPE17, A_ANIM_FRAMES_TYPE15 + 4 * 8))

# Frames stay inside those seeded tables: this battery is about the DISPATCH, and the unmasked index
# each handler applies to its own table is driven by the battery above.
ANIM_IN_RANGE_FRAME = 2


def _table_entry(address):
    return int.from_bytes(bytes(harness.BASE_IMAGE[address:address + 4]), "big")


def _animate_record(seed, alive, type_id, frame=ANIM_IN_RANGE_FRAME):
    return (Record(seed).byte(ENTITY_ALIVE, alive).byte(ENTITY_TYPE, type_id)
            .byte(ENTITY_ANIM_FRAME, frame).byte(ACTOR_DIVING, 1))


def _animate_case(records, phase=0, explosion_phase=0, limits=(5, 5), extra=None, seed=0,
                  poison=False):
    """Run the pass over a whole poked slot array, with every frame table seeded."""
    pokes = abi.seed_spans(ENTRY_ENEMIES_ANIMATE_ALL + seed, ANIM_TABLE_SPANS)
    pokes[A_ENEMY_SHOT_SLOTS] = _array(records)
    pokes[A_ANIM_PHASE_B] = bytes([phase])
    pokes[A_EXPLOSION_PHASE_ODD] = bytes([explosion_phase])
    pokes[A_ANIM_FRAME_LIMIT_TYPE20] = bytes([limits[0]])
    pokes[A_ANIM_FRAME_LIMIT_TYPE22] = bytes([limits[1]])
    pokes.update(extra or {})
    diffs, _ = differential(ENTRY_ENEMIES_ANIMATE_ALL, {"_pokes": pokes},
                            lambda lib, buf: lib.g_enemies_animate_all(buf), poison=poison)
    assert not diffs, report(diffs)


def test_anim_table_is_fully_reconstructed():
    """Every longword of the shipped table must be a routine src/enemy.c can run.

    THE DISPATCHER READS ITS TARGET OUT OF THE IMAGE, so the reconstruction maps that address back
    to a C function — and an entry the map does not hold would be left uncalled while the original
    jumped to it. This is the assertion that says the map is complete for the table the game ships,
    and `test_animate_all_dispatches_every_type` is what says the mapping itself is right.
    """
    entries = {_table_entry(A_ACTOR_ANIM_TABLE + 4 * t) for t in range(ACTOR_ANIM_TABLE_ENTRIES)}
    unmapped = sorted(hex(e) for e in entries - set(ANIM_HANDLER_ADDRESSES))
    assert not unmapped, f"table entries with no C handler: {unmapped}"


def test_the_types_past_the_table_are_this_batchs_boundary():
    """The SIGNED type guard admits more types than the 23-entry table defines, and this is where
    the reconstruction stops.

    The slots between the table's end and the guard's bound are not junk: they are the two script-VM
    jump tables, holding real entry points (index 23 is `entity_apply_accel`, 26 is
    `actor_script_op_bounce_fall`, and so on). The original would call a SCRIPT handler from the
    ANIMATION pass; `run_actor_anim_handler` finds none of those addresses in its map and returns.
    STATUS.md, "`enemies_animate_all`'s unreconstructed edge", is the one home for why that is
    stated rather than modelled — and this assertion is what keeps the boundary where it says: it
    fails the day a slot past the table becomes one the map holds, i.e. the day the gap narrows and
    the prose stops being true.
    """
    assert ACTOR_ANIM_TABLE_ENTRIES < ACTOR_HANDLER_TYPE_MAX
    beyond = {_table_entry(A_ACTOR_ANIM_TABLE + 4 * t)
              for t in range(ACTOR_ANIM_TABLE_ENTRIES, ACTOR_HANDLER_TYPE_MAX)}
    mapped = beyond & set(ANIM_HANDLER_ADDRESSES)
    assert not mapped, (
        f"slots past the table now reach handler(s) the map holds: "
        f"{sorted(hex(a) for a in mapped)} — the reconstruction's boundary moved")


def test_animated_types_are_the_ones_the_table_serves():
    """...and the mirror of it: the types this battery drives are exactly the table's non-default
    entries, so a handler added to the table by a later revision cannot go untested silently."""
    served = tuple(t for t in range(ACTOR_ANIM_TABLE_ENTRIES)
                   if _table_entry(A_ACTOR_ANIM_TABLE + 4 * t) != FN_ACTOR_HANDLER_NONE)
    assert served == ANIMATED_TYPES
    for type_id in INERT_TYPES:
        assert _table_entry(A_ACTOR_ANIM_TABLE + 4 * type_id) == FN_ACTOR_HANDLER_NONE


def test_animate_all_dispatches_every_type():
    """One record of each animatable type in a single pass, and the same set rotated one slot on.

    The rotation is what separates "dispatched by type" from "dispatched by position": a candidate
    keyed on the slot index agrees with the first arrangement and differs on the second.
    """
    types = ANIMATED_TYPES + INERT_TYPES
    for rotation in (0, 1):
        records = [_animate_record(i, 1, types[(i + rotation) % len(types)])
                   for i in range(ACTOR_UPDATE_SLOTS)]
        _animate_case(records, seed=rotation)


@pytest.mark.parametrize("type_id", ANIMATED_TYPES + INERT_TYPES)
def test_animate_all_same_type_in_every_slot(type_id):
    """Eleven records of one type: a walk that stopped early, or stepped by the wrong stride,
    leaves some of them un-animated."""
    _animate_case([_animate_record(0x100 + i, 1, type_id) for i in range(ACTOR_UPDATE_SLOTS)])


def test_animate_all_skips_dead_records():
    """`tst.b 14(a2)` gates each record; the dead ones must come back byte-identical."""
    records = [_animate_record(0x200 + i, i % 2, ANIMATED_TYPES[i % len(ANIMATED_TYPES)])
               for i in range(ACTOR_UPDATE_SLOTS)]
    _animate_case(records)


@pytest.mark.parametrize("phase", (0, 1, 0x7f, 0x80, 0xff))
def test_animate_all_flips_the_phase_byte(phase):
    """`not.b $198ac` runs before the walk and unconditionally — with every record dead there is
    nothing else the pass can write, so this case is the flip alone."""
    _animate_case([_animate_record(0x300 + i, 0, 0x0c) for i in range(ACTOR_UPDATE_SLOTS)],
                  phase=phase)


def test_animate_all_walks_exactly_eleven_records():
    """A twelfth live record, of the type the eleventh carries, must come back untouched — which
    pins the loop count against the ship records that follow the wave slots."""
    records = [_animate_record(0x400 + i, 1, 0x0c) for i in range(ACTOR_UPDATE_SLOTS + 1)]
    _animate_case(records)


@pytest.mark.parametrize("type_id", (0x31, 0x80, 0xff))
def test_animate_all_reads_its_handler_out_of_the_table(type_id):
    """A type past the 23-entry table indexes past it, and the routine calls whatever it finds.

    Both facts are driven here by POKING a real handler's address into the slot the type reaches: if
    the target came from a `switch` on the type rather than from the image, none of these three
    would animate anything. 0x80 and 0xff also pin the guard's SIGNEDNESS — an unsigned `cmpi.b`
    would refuse both, and 0x31 is the last type below the bound.
    """
    slot = A_ACTOR_ANIM_TABLE + 4 * type_id
    records = [_animate_record(0x500 + i, 1, type_id) for i in range(ACTOR_UPDATE_SLOTS)]
    _animate_case(records, extra={slot: ENTRY_ANIM_ENEMY_TYPE12.to_bytes(4, "big")})


@pytest.mark.parametrize("type_id", (ACTOR_HANDLER_TYPE_MAX, ACTOR_HANDLER_TYPE_MAX + 1, 0x7f))
def test_animate_all_type_guard_refuses_its_bound_and_above(type_id):
    """...and the other side of the same bound: with a live handler poked into the slot each type
    reaches, a record at 0x32 or above must still come back untouched. `bge` is `>=`, so the bound
    itself is refused where 0x31 above runs."""
    slot = A_ACTOR_ANIM_TABLE + 4 * type_id
    records = [_animate_record(0x600 + i, 1, type_id) for i in range(ACTOR_UPDATE_SLOTS)]
    _animate_case(records, extra={slot: ENTRY_ANIM_ENEMY_TYPE12.to_bytes(4, "big")})


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_animate_all_fuzz(chunk):
    rng = random.Random(ENTRY_ENEMIES_ANIMATE_ALL)
    types = ANIMATED_TYPES + INERT_TYPES
    for i in range(60):
        records = [_animate_record(i * 32 + slot, rng.randrange(256) if rng.randrange(4) else 0,
                                   rng.choice(types), frame=rng.randrange(1, 5))
                   for slot in range(ACTOR_UPDATE_SLOTS)]
        case = dict(phase=rng.randrange(2) * rng.randrange(1, 256),
                    explosion_phase=rng.randrange(2) * rng.randrange(1, 256),
                    limits=(rng.randrange(1, 8), rng.randrange(1, 8)), seed=i)
        if _in_chunk(i, chunk):
            _animate_case(records, **case)


def test_animate_all_attribution():
    _animate_case([_animate_record(0x700 + i, 1, ANIMATED_TYPES[i % len(ANIMATED_TYPES)])
                   for i in range(ACTOR_UPDATE_SLOTS)], poison=True)


# =========================================================== enemy_move_type14_sine @ 0x1494a

# The step is 4, so the despawn edge sits at x < 4 rather than at the 2-pixel movers' x < 2.
SINE_X_EDGES = (0, 1, SINE_STEP_LEFT - 1, SINE_STEP_LEFT, SINE_STEP_LEFT + 1, 6,
                0xfffe, 0xffff, 0x7fff, 0x8000, 0x8000 + SINE_STEP_LEFT - 1,
                0x8000 + SINE_STEP_LEFT)
# Every fold boundary sin_scaled has, the phase step's own wrap point, and both ends of the word.
SINE_PHASE_WRAP = SIN_DEGREES_FULL - SINE_PHASE_STEP
SINE_PHASE_EDGES = (0, 1, 0x59, 0x5a, 0x5b, 0xb3, 0xb4, 0xb5, 0x10d, 0x10e, 0x10f,
                    SINE_PHASE_WRAP - 1, SINE_PHASE_WRAP, SINE_PHASE_WRAP + 1,
                    SIN_DEGREES_FULL - 1, SIN_DEGREES_FULL, 0x7fff, 0x8000, 0xffff)


def _sine_case(x, phase, base_y=0x50, seed=0, poison=False):
    record = (Record(seed ^ phase).word(ENTITY_X, x).word(ACTOR_SINE_PHASE, phase)
              .word(ACTOR_SINE_BASE_Y, base_y).byte(ENTITY_ALIVE, 1).byte(ENTITY_SQUADRON, 3))
    _actor_case(ENTRY_ENEMY_MOVE_TYPE14_SINE,
                lambda lib, buf: lib.g_enemy_move_type14_sine(buf, ACTOR), record,
                pokes=_counter_pokes(seed), poison=poison)


@pytest.mark.parametrize("x", SINE_X_EDGES)
def test_sine_marches_and_despawns(x):
    """4 px a frame, and the record is freed once the step takes x below zero — a different edge
    from the two 2-pixel movers above. The seeded counter band is what proves this one credits its
    squadron on the way out, as the original's open-coded despawn does."""
    _sine_case(x, phase=0x30)


@pytest.mark.parametrize("phase", SINE_PHASE_EDGES)
def test_sine_phase_folds_and_wraps(phase):
    """Every quadrant boundary of the sine fold, and the 360-degree wrap of the phase step.

    The wrap test is a SIGNED `cmp.w #$168` + `blt`, so a phase whose step carries it past 0x7fff
    reads as negative and is NOT wrapped — 0x7fff and 0x8000 are here for that.
    """
    _sine_case(x=0x100, phase=phase)


@pytest.mark.parametrize("base_y", (0, 1, 0x50, 0x7fff, 0x8000, 0xffff))
def test_sine_height_is_added_to_the_base(base_y):
    """The y is recomputed from scratch every frame as base + sin(phase) rather than integrated, so
    the record's velocity words are never read; the add is a word one and wraps."""
    _sine_case(x=0x100, phase=0x2d, base_y=base_y)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_sine_fuzz(chunk):
    rng = random.Random(ENTRY_ENEMY_MOVE_TYPE14_SINE)
    for i in range(200):
        case = dict(x=rng.randrange(-4, 0x1c0) & 0xffff if i % 2 else rng.randrange(1 << 16),
                    phase=rng.randrange(SIN_DEGREES_FULL) if i % 3 else rng.randrange(1 << 16),
                    base_y=rng.randrange(1 << 16), seed=i)
        if _in_chunk(i, chunk):
            _sine_case(**case)


def test_sine_attribution():
    _sine_case(x=0x100, phase=0x2d, poison=True)
    _sine_case(x=1, phase=0x2d, seed=5, poison=True)

# ================================================== the script VM's util-calling opcode handlers

SPEED_SAMPLES = (0, 1, 2, 3, 7, 0x7f, 0x80, 0xff)   # ACTOR_SPEED is read SIGNED by 0x142d4


def _signed_byte(value):
    return value - 0x100 if value >= 0x80 else value


def _op_case(entry, glue_name, record, opcode=0, pokes=None, poison=False, pass_opcode=False):
    """One opcode handler, entered at the flag stub with A2 on the record and D1 on the opcode.

    `pass_opcode` says whether the glue takes the opcode byte too — only the operand classes read
    D1, and handing it to a glue that does not take it would be a signature mismatch rather than a
    stronger case.
    """
    def glue(lib, buf):
        fn = getattr(lib, glue_name)
        return fn(buf, ACTOR, opcode, FLAG) if pass_opcode else fn(buf, ACTOR, FLAG)

    _script_case(entry, glue, record, opcode=opcode, pokes=pokes, poison=poison)


# ---- actor_script_op_set_heading @ 0x14da2 ----

@pytest.mark.parametrize("chunk", range(SCRIPT_CHUNKS))
def test_op_set_heading_every_opcode(chunk):
    """All 256 opcode bytes, sharded.

    The shift is `lsr.b #1` and not the `lsr.b #3` its five sibling operand classes use, so the
    heading this writes is `(opcode & 0x78) >> 1` — sixteen of the sixty-four directions, four
    apart. An exhaustive sweep is what separates that shift from every other one: a `>> 3` agrees
    with it only at operand 0.
    """
    for opcode in range(chunk, 0x100, SCRIPT_CHUNKS):
        _op_case(ENTRY_ACTOR_SCRIPT_OP_SET_HEADING, "g_actor_script_op_set_heading",
                 Record(opcode).byte(ACTOR_SPEED, 3), opcode=opcode, pass_opcode=True)


@pytest.mark.parametrize("speed", SPEED_SAMPLES)
def test_op_set_heading_speed_is_signed(speed):
    """The speed byte feeds a `muls.w` through `ext.w d1`, so 0x80..0xff drive the velocity the
    other way — an unsigned reading writes a different pair of words."""
    _op_case(ENTRY_ACTOR_SCRIPT_OP_SET_HEADING, "g_actor_script_op_set_heading",
             Record(0x900 + speed).byte(ACTOR_SPEED, speed), opcode=0x38, pass_opcode=True)


@pytest.mark.parametrize("opcode", (0x00, 0x08, 0x40, 0x78, 0xff))
def test_op_set_heading_integrates_the_new_velocity(opcode):
    """It ends by calling 0x142d4 and then 0x14306, so the position longwords move in the same
    call — with both position fields noise, a candidate that stopped after setting the velocity
    leaves eight bytes behind."""
    _op_case(ENTRY_ACTOR_SCRIPT_OP_SET_HEADING, "g_actor_script_op_set_heading",
             Record(0xa00 + opcode).byte(ACTOR_SPEED, 5), opcode=opcode, pass_opcode=True,
             poison=True)


# ---- actor_script_op_random_heading @ 0x14de2 ----

# The shipped state, the LFSR's 0 fixed point, both all-ones/one-bit extremes and the tap mask — the
# set test_rng.py drives, for the same reason.
RNG_SEEDS = (0x83e4f2b3, 0x00000000, 0xffffffff, 0x00000001, 0x1d872b41, 0x12345678)


@pytest.mark.parametrize("state", RNG_SEEDS)
def test_op_random_heading_draws_and_steers(state):
    """The heading is `rand16() & 0x3f`, so the generator's state is this opcode's whole input —
    and it is ALSO an output, since rand16 writes the advanced state back where the diff sees it."""
    _op_case(ENTRY_ACTOR_SCRIPT_OP_RANDOM_HEADING, "g_actor_script_op_random_heading",
             Record(state & 0xffff).byte(ACTOR_SPEED, 4),
             pokes={A_RNG_LFSR_STATE: state.to_bytes(4, "big")})


@pytest.mark.parametrize("speed", SPEED_SAMPLES)
def test_op_random_heading_speed_is_signed(speed):
    """The same signed-speed battery as its sibling, and it too integrates the velocity it set."""
    _op_case(ENTRY_ACTOR_SCRIPT_OP_RANDOM_HEADING, "g_actor_script_op_random_heading",
             Record(0xb00 + speed).byte(ACTOR_SPEED, speed), poison=(speed == 1))


# ---- actor_script_op_aim_at_player @ 0x14e38 ----

# The four axes, the four diagonals, two off-diagonal slopes and the one-pixel neighbourhood of the
# origin: angle_to_target folds its vector into an octant, and this is the ring round that fold.
AIM_OFFSETS = ((0, 0), (0x40, 0), (-0x40, 0), (0, 0x40), (0, -0x40), (0x40, 0x40), (-0x40, 0x40),
               (0x40, -0x40), (-0x40, -0x40), (0x40, 0x20), (0x20, 0x40), (1, 0), (0, 1), (1, 1))


@pytest.mark.parametrize("dx,dy", AIM_OFFSETS)
def test_op_aim_at_player_every_octant(dx, dy):
    """The heading comes from angle_to_target against the ship's own record, and — unlike its two
    neighbours — this op neither stores that heading nor integrates the velocity it sets. Both
    absences are what the seeded record catches: writing ACTOR_HEADING, or stepping the position,
    would each be a diff."""
    actor_x, actor_y = 0x80, 0x60
    player = (Record(0x1200 + (dx & 0xff)).word(ENTITY_X, actor_x + dx)
              .word(ENTITY_Y, actor_y + dy).bytes())
    _op_case(ENTRY_ACTOR_SCRIPT_OP_AIM_AT_PLAYER, "g_actor_script_op_aim_at_player",
             Record(0xc00 + (dy & 0xff)).word(ENTITY_X, actor_x).word(ENTITY_Y, actor_y)
             .byte(ACTOR_SPEED, 4),
             pokes={A_PLAYER_RECORD: player})


@pytest.mark.parametrize("speed", SPEED_SAMPLES)
def test_op_aim_at_player_speed_is_signed(speed):
    player = Record(0x1300 + speed).word(ENTITY_X, 0x120).word(ENTITY_Y, 0x30).bytes()
    _op_case(ENTRY_ACTOR_SCRIPT_OP_AIM_AT_PLAYER, "g_actor_script_op_aim_at_player",
             Record(0xd00 + speed).word(ENTITY_X, 0x80).word(ENTITY_Y, 0x60)
             .byte(ACTOR_SPEED, speed),
             pokes={A_PLAYER_RECORD: player}, poison=(speed == 2))


# ---- the two thrust-to-centre ops, 0x14e1c and 0x14e5c ----

# One step either side of each centre line, plus the values whose SIGNED reading differs from their
# unsigned one — which is what holds `blt` against `blo`.
THRUST_Y_EDGES = (0, ACTOR_CENTRE_Y - 1, ACTOR_CENTRE_Y, ACTOR_CENTRE_Y + 1, 0x7fff, 0x8000, 0xffff)
THRUST_X_EDGES = (0, ACTOR_CENTRE_X - 1, ACTOR_CENTRE_X, ACTOR_CENTRE_X + 1, 0x7fff, 0x8000, 0xffff)
# The acceleration words entity_apply_accel folds in, including the ones that wrap the velocity.
THRUST_ACCELS = (0, 1, 0x1234, 0x7fff, 0x8000, 0xffff)


def _thrust_record(seed, x, y, ax, ay):
    return (Record(seed).word(ENTITY_X, x).word(ENTITY_Y, y).word(ENTITY_AX, ax)
            .word(ENTITY_AY, ay))


@pytest.mark.parametrize("y", THRUST_Y_EDGES)
def test_op_thrust_to_centre_y(y):
    """`cmpi.w #$60` + `blt` picks bit 5 (add ay) below the centre line and bit 6 (subtract it) at
    or above; the compare is SIGNED, which 0x8000 and 0xffff are here to hold."""
    _op_case(ENTRY_ACTOR_SCRIPT_OP_THRUST_TO_CENTRE_Y, "g_actor_script_op_thrust_to_centre_y",
             _thrust_record(0xe00 + (y & 0xff), 0x100, y, 0x11, 0x22))


@pytest.mark.parametrize("ay", THRUST_ACCELS)
def test_op_thrust_to_centre_y_folds_the_accel(ay):
    """...and it is ENTITY_AY that is folded in, not a literal: the velocity word moves by exactly
    this much, wrapping where the sum leaves the word."""
    for y in (ACTOR_CENTRE_Y - 1, ACTOR_CENTRE_Y + 1):
        _op_case(ENTRY_ACTOR_SCRIPT_OP_THRUST_TO_CENTRE_Y, "g_actor_script_op_thrust_to_centre_y",
                 _thrust_record(0xf00 + (ay & 0xff), 0x100, y, 0x33, ay))


@pytest.mark.parametrize("x", THRUST_X_EDGES)
@pytest.mark.parametrize("y", (ACTOR_CENTRE_Y - 1, ACTOR_CENTRE_Y + 1))
def test_op_thrust_to_centre_both_axes(x, y):
    """Ext 9 ORs the two masks together, so every case here drives one x arm against one y arm — a
    candidate that dropped the `or.w` accelerates on one axis only."""
    _op_case(ENTRY_ACTOR_SCRIPT_OP_THRUST_TO_CENTRE, "g_actor_script_op_thrust_to_centre",
             _thrust_record(0x1000 + (x & 0xff), x, y, 0x44, 0x55))


@pytest.mark.parametrize("ax", THRUST_ACCELS)
def test_op_thrust_to_centre_folds_both_accels(ax):
    for x in (ACTOR_CENTRE_X - 1, ACTOR_CENTRE_X + 1):
        _op_case(ENTRY_ACTOR_SCRIPT_OP_THRUST_TO_CENTRE, "g_actor_script_op_thrust_to_centre",
                 _thrust_record(0x1100 + (ax & 0xff), x, ACTOR_CENTRE_Y - 1, ax, 0x66),
                 poison=(ax == 1))


# ---- actor_script_continue @ 0x14eb8 and actor_script_op_end_frame @ 0x14ebe ----

@pytest.mark.parametrize("entry,glue_name", ((ENTRY_ACTOR_SCRIPT_CONTINUE,
                                              "g_actor_script_continue"),
                                             (ENTRY_ACTOR_SCRIPT_OP_END_FRAME,
                                              "g_actor_script_op_end_frame")))
def test_op_end_frame_and_continue_answer_opposite_carries(entry, glue_name):
    """Six bytes each, one `ori.b #$1,ccr` and one `andi.b #$fe,ccr`, and the flag byte is their
    whole observable effect — which is exactly why FLAG_CANARY is neither of the two answers, and
    why the record they are handed is noise the pair must not touch."""
    pokes = _flag_pokes(entry, "cs")
    pokes[ACTOR] = Record(entry).bytes()
    regs = {"a0": FLAG, "a2": ACTOR, "_pokes": pokes}
    diffs, _ = differential(abi.STUB, regs,
                            lambda lib, buf: getattr(lib, glue_name)(buf, FLAG))
    assert not diffs, f"{glue_name}\n{report(diffs)}"


# ---- actor_script_op_random_speed_nudge @ 0x14e8c ----

def _draw_from(state):
    """A local mirror of rand16 @ 0x13bf8, used ONLY to CHOOSE the generator state a case starts
    from — never to assert an answer, which is the oracle's job. Without it the draw would be
    whatever the shipped state happens to produce, and neither the carry split below nor the
    unreachable arm could be addressed at all."""
    result = 0
    for _ in range(RNG_STEP_BITS):
        bit = state >> 31
        state = (state << 1) & 0xffffffff
        if bit:
            state ^= RNG_TAP_MASK
        result = ((result << 1) | bit) & 0xffff
    return result & 0xff


# The generator hands back the sixteen bits that leave the TOP of the state, so the draw's low byte
# comes out of bits 16..24 of the state it starts from — a search that walked 1, 2, 3, ... would
# only ever see draw 0. This walks the whole 32-bit space in one stride instead (the odd golden-ratio
# multiplier), which reaches all 256 bytes in about the 1420 draws coupon-collecting predicts.
RNG_SEARCH_STRIDE = 0x9e3779b1


@functools.lru_cache(maxsize=1)
def _states_by_draw(tries=1 << 14):
    """One generator state per draw byte: {draw: state}, all 256 of them.

    Cached and built on FIRST USE rather than at import: the search is ~1000 states of sixteen
    LFSR steps each, and this module is imported by every one of `-n auto`'s workers — including
    the ones whose share of the suite contains no nudge case, and every `--collect-only` run.
    """
    found = {}
    for i in range(1, tries):
        state = (i * RNG_SEARCH_STRIDE) & 0xffffffff
        found.setdefault(_draw_from(state), state)
        if len(found) == 0x100:
            return found
    raise AssertionError(f"only {len(found)} of 256 draw bytes found in {tries} states")


# The draw decides three things at once, and these are their boundaries: the SIGNED `bge #$55` that
# gates the whole body, the SIGNED `blt #$aa` inside it, and the UNSIGNED carry the early return
# hands back.
NUDGE_DRAWS = (0, 1, 0x54, 0x55, 0x56, 0x7e, 0x7f, 0x80, 0x81, 0xa9, 0xaa, 0xab, 0xfe, 0xff)
NUDGE_SPEEDS = (0, 1, 2, 6, 7, 8, 0x7f, 0xff)


@pytest.mark.parametrize("draw", NUDGE_DRAWS)
def test_op_random_speed_nudge(draw):
    """Every boundary of the two signed compares, against every speed the `and.b #$7` can produce.

    THE EARLY RETURN'S CARRY IS THE FIRST COMPARE'S OWN, and `cmp.b` sets it unsigned — so a draw
    below 0x55 leaves it SET and one of 0x80 or more leaves it CLEAR, though both take the same
    branch. The flag byte is what pins that: a candidate answering one carry for the whole early
    arm fails on half of these.
    """
    for speed in NUDGE_SPEEDS:
        _op_case(ENTRY_ACTOR_SCRIPT_OP_RANDOM_SPEED_NUDGE,
                 "g_actor_script_op_random_speed_nudge",
                 Record((draw << 8) ^ speed).byte(ACTOR_SPEED, speed),
                 pokes={A_RNG_LFSR_STATE: _states_by_draw()[draw].to_bytes(4, "big")})


def test_op_random_speed_nudge_never_draws_the_increment():
    """The "+1" arm is unreachable, and this is the assertion that says so rather than a comment.

    `bge #$55` admits only 0x55..0x7f read as SIGNED bytes, and every one of those is above 0xaa
    read the same way — so `blt #$aa` never branches and the nudge is always -1. If a later reading
    of the disassembly overturns either compare's signedness, this fails and the C beside it is
    wrong in the same place. STATUS.md carries the matching mutation survivor.
    """
    admitted = [d for d in range(0x100) if _signed_byte(d) >= _signed_byte(NUDGE_MIN_DRAW)]
    assert admitted == list(range(NUDGE_MIN_DRAW, 0x80))
    assert not [d for d in admitted if _signed_byte(d) < _signed_byte(NUDGE_UP_DRAW)]


@pytest.mark.parametrize("draw", (0x20, 0x60, 0x90))
def test_op_random_speed_nudge_attribution(draw):
    _op_case(ENTRY_ACTOR_SCRIPT_OP_RANDOM_SPEED_NUDGE, "g_actor_script_op_random_speed_nudge",
             Record(draw).byte(ACTOR_SPEED, 3),
             pokes={A_RNG_LFSR_STATE: _states_by_draw()[draw].to_bytes(4, "big")}, poison=True)


# ============================================== actor_script_op_bounce_fall @ 0x14d14

ENTITY_COUNT = 20                 # `entity_table` holds 20 of the 0x2c-byte records
BOUNCE_TERRAIN_TYPE = 0x33        # a bomb — a member of A_type_hits_terrain_bits
BOUNCE_INERT_TYPE = 0x0b          # ...and one that is not, so the chain walk answers "no hit"
BOUNCE_INDEXES = (0, 1, 6, 9, 19)


def _bounce_records(seed, index, y, dy, ay, bounced, pixel_hit, type_id):
    """Twenty seeded records, the one under test at `index`.

    Every OTHER record has its pixel-hit flag clear, so an index computed one slot out reads a
    record that answers "no terrain" and the bounce quietly disappears — which is what makes the
    `(a2 - table) / 0x2c` division observable rather than assumed.
    """
    records = [Record(seed * 64 + i).byte(ENTITY_ALIVE, 1).byte(ENTITY_PIXEL_HIT, 0)
               .byte(ENTITY_TYPE, BOUNCE_INERT_TYPE) for i in range(ENTITY_COUNT)]
    records[index] = (Record(seed * 64 + index).word(ENTITY_Y, y).word(ENTITY_DY, dy)
                      .word(ENTITY_AY, ay).byte(ENTITY_ALIVE, 1)
                      .byte(ENTITY_PIXEL_HIT, pixel_hit).byte(ENTITY_TYPE, type_id)
                      .byte(ACTOR_BOUNCED, bounced))
    return records


def _bounce_case(index=9, y=0x40, dy=2, ay=1, bounced=0, pixel_hit=1,
                 type_id=BOUNCE_TERRAIN_TYPE, rows=None, seed=0, poison=False):
    actor = A_ENTITY_TABLE + index * ENTITY_STRIDE
    pokes = _flag_pokes(ENTRY_ACTOR_SCRIPT_OP_BOUNCE_FALL, "cs")
    pokes[A_ENTITY_TABLE] = _array(_bounce_records(seed, index, y, dy, ay, bounced, pixel_hit,
                                                   type_id))
    pokes[A_ENTITY_COLLISION_MASKS] = b"".join(
        (rows or {}).get(i, 0).to_bytes(COLLISION_ROW_BYTES, "big") for i in range(ENTITY_COUNT))
    regs = {"a0": FLAG, "a2": actor, "_pokes": pokes}
    diffs, _ = differential(abi.STUB, regs,
                            lambda lib, buf: lib.g_actor_script_op_bounce_fall(buf, actor, FLAG),
                            poison=poison)
    assert not diffs, f"index={index} y={y:#x} dy={dy:#x} bounced={bounced}\n{report(diffs)}"


@pytest.mark.parametrize("index", BOUNCE_INDEXES)
def test_bounce_index_comes_from_the_record_pointer(index):
    """`(a2 - 0x17a8e) / 0x2c` is how the terrain test learns which entity it is testing, and only
    the record at `index` carries a pixel hit — so a wrong quotient answers "no hit"."""
    _bounce_case(index=index)


@pytest.mark.parametrize("pixel_hit", (0, 1, 0x80, 0xff))
def test_bounce_terrain_gate(pixel_hit):
    """No pixel hit means no bounce, and the whole call is then the gravity tail."""
    _bounce_case(pixel_hit=pixel_hit)


@pytest.mark.parametrize("type_id", (BOUNCE_INERT_TYPE, BOUNCE_TERRAIN_TYPE))
def test_bounce_type_must_be_terrain_sensitive(type_id):
    """The chain walk refuses a type the terrain table does not list, so an inert record falls
    without ever bouncing however set its pixel-hit flag is."""
    _bounce_case(type_id=type_id)


def test_bounce_chain_walk_can_deny_the_hit():
    """An overlap with a LOWER-indexed entity whose own flag is clear explains the pixel hit away,
    so the walk answers "no terrain" even though this record's flag is set — which is what makes
    the callee the collision chain rather than a bare flag test."""
    _bounce_case(index=9, rows={9: 1 << 4})


@pytest.mark.parametrize("bounced", (0, 1, 0x80, 0xff))
def test_bounce_flag_picks_the_arm(bounced):
    """A record that has already bounced takes the x-only arm and returns; one that has not
    reverses its dy, sets the flag and falls through into the gravity tail. Both arms answer carry
    clear, and the flag byte is compared on every case."""
    _bounce_case(bounced=bounced)


@pytest.mark.parametrize("y", (0, 0x40, ACTOR_FLOOR_Y - 2, ACTOR_FLOOR_Y - 1, ACTOR_FLOOR_Y,
                               ACTOR_FLOOR_Y + 1, 0x7fff, 0x8000, 0xffff))
@pytest.mark.parametrize("dy", (0, 1, 2, 0xfffe, 0x7fff, 0x8000))
def test_bounce_floor_clamp(y, dy):
    """The floor sits at y = 0xa0, the compare is SIGNED, and the clamp runs AFTER the accel has
    already stepped the position — so the y a case sets is not the y the clamp sees, and these
    pairs straddle the edge from both directions."""
    _bounce_case(y=y, dy=dy, pixel_hit=0)


@pytest.mark.parametrize("ay", (0, 1, 0x100, 0x7fff, 0x8000, 0xffff))
def test_bounce_gravity_is_the_records_own_accel(ay):
    """`move.w #$20,d1` selects bit 5, which adds ENTITY_AY to ENTITY_DY — so the fall's rate is
    the record's own field and not a literal, and the vertical step lands TWICE per call."""
    _bounce_case(y=0x40, dy=1, ay=ay, pixel_hit=0)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_bounce_fuzz(chunk):
    rng = random.Random(ENTRY_ACTOR_SCRIPT_OP_BOUNCE_FALL)
    for i in range(120):
        case = dict(index=rng.randrange(ENTITY_COUNT),
                    y=(rng.randrange(ACTOR_FLOOR_Y - 8, ACTOR_FLOOR_Y + 8) if i % 2
                       else rng.randrange(1 << 16)),
                    dy=rng.randrange(1 << 16), ay=rng.randrange(1 << 16),
                    bounced=rng.randrange(2) * rng.randrange(1, 256),
                    pixel_hit=rng.randrange(2), seed=i)
        if _in_chunk(i, chunk):
            _bounce_case(**case)


def test_bounce_attribution():
    _bounce_case(y=0x40, bounced=0, poison=True)
    _bounce_case(y=ACTOR_FLOOR_Y, bounced=1, seed=3, poison=True)


# ================================================ the explosion groups — 0x15510 and 0x1544e

EXPLOSION_GROUPS = 2
EXPLOSION_PARTS = 6
EXPLOSION_END_FRAME = 0x0d
EXPLOSION_OFFSET_WORDS = 3
EXPLOSION_PART_FRAME = 0x10

# The member lists index the 20-record entity table, and the index is `ext.w` then `mulu.w` — a
# member of 0x80 or more becomes a huge POSITIVE offset that leaves the image, so no case drives
# one. `test_explosion_members_are_inside_the_table` pins that the shipped lists do not either.
ENTITY_TABLE_RECORDS = 20
# The offsets table's own extent: two groups' worth of the SAME six triples, read once per spawn.
EXPLOSION_OFFSET_BYTES = EXPLOSION_PARTS * EXPLOSION_OFFSET_WORDS * 2
# ...and the frame-pointer table's, as far as an in-range particle frame reaches.
EXPLOSION_FRAME_PTR_BYTES = (EXPLOSION_END_FRAME - 1) * 4


def _explosion_pokes(seed, members, offsets=None, active=0, toggle=0, records=None):
    """The group member lists, the offset table, the frame pointers and the twenty records.

    The member lists and the offsets are POKED rather than left as the image's own, because the two
    groups otherwise share every particle field this battery reads and a candidate that walked the
    wrong list would still land on plausible records.
    """
    pokes = abi.seed_spans(0x15510 + seed,
                           [(A_EXPLOSION_SMALL_FRAME_PTRS,
                             A_EXPLOSION_SMALL_FRAME_PTRS + EXPLOSION_FRAME_PTR_BYTES)])
    pokes[A_EXPLOSION_GROUP_MEMBERS] = bytes(members)
    if offsets is not None:
        pokes[A_EXPLOSION_PARTICLE_OFFSETS] = offsets
    pokes[A_EXPLOSION_GROUP_ACTIVE_BITS] = bytes([active])
    pokes[A_EXPLOSION_FRAME_TOGGLE] = bytes([toggle])
    pokes[A_ENTITY_TABLE] = _array(records or [Record(seed * 64 + i)
                                               for i in range(ENTITY_TABLE_RECORDS)])
    return pokes


def _shipped_members():
    """The two six-byte lists the binary ships, as one twelve-byte block."""
    return bytes(harness.BASE_IMAGE[A_EXPLOSION_GROUP_MEMBERS:
                                    A_EXPLOSION_GROUP_MEMBERS + EXPLOSION_GROUPS * EXPLOSION_PARTS])


def test_explosion_members_are_inside_the_table():
    """Every shipped member indexes one of the twenty records.

    The index is sign-extended to a word and then multiplied UNSIGNED, so a member of 0x80 or more
    would address about 0x2bedc0 bytes past the table — outside the image, where there is nothing to
    diff and nothing to fault on. This is the assertion that says the game's own data cannot get
    there, which is also why no case below drives such a member.
    """
    assert all(m < ENTITY_TABLE_RECORDS for m in _shipped_members()), _shipped_members().hex()


# ---- explosion_spawn @ 0x15510 ----

def _spawn_case(group, x=0x80, y=0x50, members=None, offsets=None, active=0, seed=0, poison=False):
    source = A_ENTITY_TABLE + ENTITY_TABLE_RECORDS * ENTITY_STRIDE   # clear of the six it writes
    records = [Record(seed * 64 + i) for i in range(ENTITY_TABLE_RECORDS + 1)]
    records[ENTITY_TABLE_RECORDS] = Record(0x2000 + seed).word(ENTITY_X, x).word(ENTITY_Y, y)
    pokes = _explosion_pokes(seed, members or _shipped_members(), offsets=offsets, active=active,
                             records=records)
    regs = {"a2": source, "d2": group, "_pokes": pokes}
    diffs, _ = differential(ENTRY_EXPLOSION_SPAWN, regs,
                            lambda lib, buf: lib.g_explosion_spawn(buf, source, group),
                            poison=poison)
    assert not diffs, f"group={group} x={x:#x} y={y:#x}\n{report(diffs)}"


@pytest.mark.parametrize("group", range(EXPLOSION_GROUPS))
@pytest.mark.parametrize("x", (0, 1, 2, 3, 0x80, 0x81, 0xfffe, 0xffff, 0x7fff, 0x8000))
def test_explosion_spawn_positions(group, x):
    """The x offsets ACCUMULATE and each sum is re-aligned to four pixels, so the six particles land
    in a chain rather than a rosette — a candidate applying each offset to the source's own x agrees
    only on the first particle. The odd x values are what hold `and.w #$fffc` against a shift."""
    _spawn_case(group, x=x)


@pytest.mark.parametrize("group", range(EXPLOSION_GROUPS))
@pytest.mark.parametrize("y", (0, 1, 0x50, 0x7fff, 0x8000, 0xffff))
def test_explosion_spawn_y_is_not_aligned(group, y):
    """...and only x is aligned: the y sum is stored as it comes out, wrapping at the word."""
    _spawn_case(group, y=y)


@pytest.mark.parametrize("group", range(EXPLOSION_GROUPS))
@pytest.mark.parametrize("active", (0, 1, 2, 3, 0x5a, 0xff))
def test_explosion_spawn_sets_its_group_bit(group, active):
    """`bset d2,$19670` is a read-modify-write on the byte, so the OTHER group's bit has to survive
    — which is what the six starting values are for.

    ONLY GROUPS 0 AND 1 ARE DRIVEN, here and everywhere below, and that is a limit of what can be
    staged rather than a gap: `group * 6` walks the member list, so a group of 2 or more reads
    entity INDICES out of whatever follows the two six-byte lists the game ships, and an index of
    0x80 or more addresses about 0x2bedc0 bytes past the table — outside the image. names.txt's
    comment on 0x15510 reads D2 as "0 boss, 1 player" and both call sites pass a literal.
    """
    _spawn_case(group, active=active)


def test_explosion_spawn_reads_its_offsets_in_triples():
    """dx, dy and the starting frame, in that order, three words per particle — a candidate reading
    them in any other order lands every particle somewhere else."""
    offsets = b"".join((dx & 0xffff).to_bytes(2, "big") + (dy & 0xffff).to_bytes(2, "big")
                       + frame.to_bytes(2, "big")
                       for dx, dy, frame in ((4, -1, 1), (-8, 2, 2), (0x10, 0, 3),
                                             (-0x11, 0x7fff, 4), (3, -0x8000, 0x0c), (1, 1, 0xffff)))
    _spawn_case(0, offsets=offsets)
    _spawn_case(1, offsets=offsets, poison=True)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_explosion_spawn_fuzz(chunk):
    rng = random.Random(ENTRY_EXPLOSION_SPAWN)
    for i in range(40):
        offsets = rng.randbytes(EXPLOSION_OFFSET_BYTES)
        case = dict(group=i % EXPLOSION_GROUPS, x=rng.randrange(1 << 16), y=rng.randrange(1 << 16),
                    offsets=offsets, active=rng.randrange(256), seed=i)
        if _in_chunk(i, chunk):
            _spawn_case(**case)


# ---- explosion_animate_all @ 0x1544e ----

def _animate_explosion_case(frames, active, toggle=0, members=None, seed=0, poison=False):
    """`frames` is the EXPLOSION_PART_FRAME byte of each of the twenty records."""
    records = [Record(seed * 64 + i).byte(EXPLOSION_PART_FRAME, frames[i])
               .byte(ENTITY_ALIVE, 0x5a) for i in range(ENTITY_TABLE_RECORDS)]
    pokes = _explosion_pokes(seed, members or _shipped_members(), active=active, toggle=toggle,
                             records=records)
    diffs, _ = differential(ENTRY_EXPLOSION_ANIMATE_ALL, {"_pokes": pokes},
                            lambda lib, buf: lib.g_explosion_animate_all(buf), poison=poison)
    assert not diffs, f"active={active:#x} toggle={toggle:#x}\n{report(diffs)}"


# Every frame the step can be handed: the ones inside the cycle, the retiring edge, and the three
# that make `add.b #1` wrap into an arm of its own — 0xff steps to 0 (`beq`), 0x7f to 0x80 (`bmi`).
EXPLOSION_FRAMES = (0, 1, 2, EXPLOSION_END_FRAME - 2, EXPLOSION_END_FRAME - 1, EXPLOSION_END_FRAME,
                    EXPLOSION_END_FRAME + 1, 0x7e, 0x7f, 0x80, 0xfe, 0xff)


@pytest.mark.parametrize("frame", EXPLOSION_FRAMES)
@pytest.mark.parametrize("active", (1, 2, 3))
def test_explosion_animate_every_frame(frame, active):
    """One frame value in every record, so both groups' six particles take the same arm at once.

    The toggle is seeded so the flip leaves it non-zero, which is the arm that RUNS — the opposite
    way round from `asteroids_animate`, whose `beq` continues.
    """
    _animate_explosion_case([frame] * ENTITY_TABLE_RECORDS, active=active, toggle=0)


@pytest.mark.parametrize("toggle", (0, 1, 0x7f, 0x80, 0xfe, 0xff))
def test_explosion_animate_half_rate_gate(toggle):
    """`not.b` flips AND tests, so the flip has to happen on the blocked call too — a candidate
    that returned before flipping leaves the byte behind."""
    _animate_explosion_case([2] * ENTITY_TABLE_RECORDS, active=3, toggle=toggle)


@pytest.mark.parametrize("active", (0, 1, 2, 3, 4, 0x80, 0xff))
def test_explosion_animate_group_bits(active):
    """`tst.b` on the whole byte gates the routine and `btst d4` gates each group, so bit 2 and
    above arm the routine without animating anything — and the two CLEARS on group 1's pass still
    run, because they sit before its own `btst`."""
    frames = [(i % (EXPLOSION_END_FRAME + 2)) for i in range(ENTITY_TABLE_RECORDS)]
    _animate_explosion_case(frames, active=active, toggle=0)


def test_explosion_animate_walks_each_groups_own_list():
    """Two disjoint member lists, so a candidate that walked group 0's list twice — or stepped the
    cursor by anything but six — animates the wrong records."""
    members = bytes([0, 2, 4, 6, 8, 10, 1, 3, 5, 7, 9, 11])
    frames = [(i % (EXPLOSION_END_FRAME + 1)) for i in range(ENTITY_TABLE_RECORDS)]
    for active in (1, 2, 3):
        _animate_explosion_case(frames, active=active, members=members)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_explosion_animate_fuzz(chunk):
    rng = random.Random(ENTRY_EXPLOSION_ANIMATE_ALL)
    for i in range(40):
        frames = [rng.randrange(256) for _ in range(ENTITY_TABLE_RECORDS)]
        members = bytes(rng.randrange(ENTITY_TABLE_RECORDS)
                        for _ in range(EXPLOSION_GROUPS * EXPLOSION_PARTS))
        case = dict(frames=frames, active=rng.randrange(256), toggle=rng.randrange(256),
                    members=members, seed=i)
        if _in_chunk(i, chunk):
            _animate_explosion_case(**case)


def test_explosion_animate_attribution():
    _animate_explosion_case([3] * ENTITY_TABLE_RECORDS, active=3, poison=True)
    _animate_explosion_case([EXPLOSION_END_FRAME - 1] * ENTITY_TABLE_RECORDS, active=1, seed=2,
                            poison=True)


# ===================================================================== asteroids_draw @ 0x159be

# D2 is half a preshift frame, DERIVED rather than transcribed — see test_sprite.py, which makes the
# same claim about the same two immediates from the other side.
ASTEROID_FRAME_BYTES = ASTEROID_FRAME_CELLS * ASTEROID_FRAME_ROWS * SPRITE_MASKED_ROW_BYTES
ASTEROID_DRAW_PHASE_STEP = ASTEROID_FRAME_BYTES // 2

# The arena a case points every record's sprite at: the largest slot a phase can reach is
# 14 * ASTEROID_DRAW_PHASE_STEP, plus one frame.
DRAW_SPRITE = abi.SCRATCH + 0x10000
DRAW_SPRITE_BYTES = 0x8000
DRAW_HEIGHT = ASTEROID_FRAME_ROWS


def _draw_pokes(seed):
    pokes = abi.seed_spans(seed, ((DRAW_SPRITE, DRAW_SPRITE + DRAW_SPRITE_BYTES),
                                  (abi.SCREEN_BACK, abi.SCREEN_BACK + SCREEN_BYTES)),
                           guard=abi.GUARD_BYTES)
    pokes[A_SCREEN_BACK] = abi.SCREEN_BACK.to_bytes(4, "big")
    return pokes


def _drawable_record(seed, alive, x, y):
    return (Record(seed).byte(ENTITY_ALIVE, alive).word(ENTITY_X, x).word(ENTITY_Y, y)
            .word(ENTITY_HEIGHT, DRAW_HEIGHT).longword(ENTITY_SPRITE, DRAW_SPRITE))


# Where `move.w #$1e0,d2` keeps its immediate, inside asteroids_draw's own body.
ASTEROID_DRAW_D2_IMMEDIATE = 0x159da


def _asteroid_draw_case(records, seed=0, poison=False):
    pokes = _draw_pokes(ENTRY_ASTEROIDS_DRAW + seed)
    pokes[A_ASTEROID_RECORDS] = _array(records)
    diffs, _ = differential(ENTRY_ASTEROIDS_DRAW, {"_pokes": pokes},
                            lambda lib, buf: lib.g_asteroids_draw(buf), poison=poison)
    assert not diffs, report(diffs)


def _draw_grid(count, alive_of=lambda i: 1, seed=0):
    """`count` records marching diagonally across the playfield, so no two blits coincide."""
    return [_drawable_record(seed * 64 + i, alive_of(i),
                             0x10 + i * 0x10 + (i % 8) * 2,      # ...through all eight x phases
                             PLAYFIELD_TOP_Y + 4 + (i % 8) * 0x10)
            for i in range(count)]


def test_asteroid_draw_every_record():
    """All eighteen live at once, each at its own place — so a walk that stopped early, or stepped
    by the wrong stride, leaves part of the screen unwritten."""
    _asteroid_draw_case(_draw_grid(ASTEROID_GROUPS * ASTEROID_COLUMNS))


def test_asteroid_draw_skips_dead_records():
    _asteroid_draw_case(_draw_grid(ASTEROID_GROUPS * ASTEROID_COLUMNS,
                                   alive_of=lambda i: i % 3 != 1))


def test_asteroid_draw_walks_exactly_eighteen():
    """A nineteenth live record must be left undrawn — which pins 6 x 3 against the boss records
    that follow the columns."""
    _asteroid_draw_case(_draw_grid(ASTEROID_GROUPS * ASTEROID_COLUMNS + 1))


def test_asteroid_draw_phase_step_is_half_a_frame():
    """The immediate the routine loads into D2, from the image's own bytes: `move.w #$1e0,d2` at
    0x159d8. Derived on this side, so a frame geometry that no longer halves to it fails here."""
    assert ASTEROID_DRAW_PHASE_STEP == 0x1e0
    loaded = int.from_bytes(
        bytes(harness.BASE_IMAGE[ASTEROID_DRAW_D2_IMMEDIATE:ASTEROID_DRAW_D2_IMMEDIATE + 2]), "big")
    assert loaded == ASTEROID_DRAW_PHASE_STEP, f"{loaded:#x}"


def test_asteroid_draw_attribution():
    _asteroid_draw_case(_draw_grid(ASTEROID_GROUPS * ASTEROID_COLUMNS), poison=True)

# ================================== the A0-clobber roster, pinned against the oracle's own A0

# A recognisable address no handler has any reason to leave in A0. abi.RESULT is one: nothing in the
# script VM computes it, and the routines that DO load A0 load a table's base instead.
A0_SENTINEL = abi.RESULT
# One record inside the entity table, so `actor_script_op_bounce_fall`'s `(a2 - table) / 0x2c`
# quotient is a real index rather than a wrapped one.
A0_PROBE_INDEX = 9


@pytest.mark.parametrize("entry", SCRIPT_FLAG_ENTRIES)
def test_a0_clobbering_entries_is_exactly_the_ones_that_do(entry):
    """Run each flag handler at ITS OWN entry with a sentinel in A0, and ask the oracle.

    THE DIFF IS DELIBERATELY IGNORED here — the candidate glue does nothing, because the claim under
    test is about the ORIGINAL alone: which of these routines brings A0 back. `differential` reports
    the oracle's registers at the `rts` in `info["regs"]`, and that is the whole answer.

    Everything the fifteen routines between them read is staged: the twenty entity records (so the
    bounce's index and the chain walk's rows are real), a cleared collision-mask table, the player
    record the aim op reads, and the generator state the two random ops advance.
    """
    actor = A_ENTITY_TABLE + A0_PROBE_INDEX * ENTITY_STRIDE
    pokes = {A_ENTITY_TABLE: _array([Record(0x3000 + i) for i in range(ENTITY_COUNT)]),
             A_ENTITY_COLLISION_MASKS: bytes(ENTITY_COUNT * COLLISION_ROW_BYTES),
             A_PLAYER_RECORD: Record(0x3100).word(ENTITY_X, 0x90).word(ENTITY_Y, 0x40).bytes(),
             A_SCROLL_FROZEN: bytes([0])}
    regs = {"a0": A0_SENTINEL, "a2": actor, "d1": 0x38, "_pokes": pokes}

    _diffs, info = differential(entry, regs, lambda lib, buf: None)
    clobbered = info["regs"]["a0"] != A0_SENTINEL
    assert clobbered == (entry in A0_CLOBBERING_ENTRIES), (
        f"{entry:#x} left a0={info['regs']['a0']:#x}: it "
        f"{'clobbers' if clobbered else 'preserves'} A0 but is "
        f"{'not ' if clobbered else ''}in A0_CLOBBERING_ENTRIES")


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("ENTITY_STRIDE", "include/entity.h", "ENTITY_STRIDE"),
    ("ENTITY_X", "include/entity.h", "ENTITY_X"),
    ("ENTITY_Y", "include/entity.h", "ENTITY_Y"),
    ("ENTITY_SPRITE", "include/entity.h", "ENTITY_SPRITE"),
    ("ENTITY_HEIGHT", "include/entity.h", "ENTITY_HEIGHT"),
    ("ENTITY_ALIVE", "include/entity.h", "ENTITY_ALIVE"),
    ("ENTITY_TYPE", "include/entity.h", "ENTITY_TYPE"),
    ("ENTITY_DX", "include/entity.h", "ENTITY_DX"),
    ("ENTITY_DY", "include/entity.h", "ENTITY_DY"),
    ("ENTITY_ANIM_FRAME", "include/entity.h", "ENTITY_ANIM_FRAME"),
    ("ENTITY_SQUADRON", "include/entity.h", "ENTITY_SQUADRON"),
    ("ACTOR_FIRE_COUNTDOWN", "include/enemy.h", "ACTOR_FIRE_COUNTDOWN"),
    ("ACTOR_FIRE_RELOAD", "include/enemy.h", "ACTOR_FIRE_RELOAD"),
    ("ACTOR_DIVING", "include/enemy.h", "ACTOR_DIVING"),
    ("ACTOR_HEADING", "include/enemy.h", "ACTOR_HEADING"),
    ("ACTOR_SCRIPT_PC", "include/enemy.h", "ACTOR_SCRIPT_PC"),
    ("ACTOR_SCRIPT_LOOP_PC", "include/enemy.h", "ACTOR_SCRIPT_LOOP_PC"),
    ("ACTOR_SCRIPT_LOOP_COUNT", "include/enemy.h", "ACTOR_SCRIPT_LOOP_COUNT"),
    ("ASTEROID_Y_DESCENDING", "include/enemy.h", "ASTEROID_Y_DESCENDING"),
    ("ASTEROID_SLOW", "include/enemy.h", "ASTEROID_SLOW"),
    ("A_ENEMY_SLOTS", "include/enemy.h", "A_enemy_slots"),
    ("A_ASTEROID_RECORDS", "include/enemy.h", "A_asteroid_records"),
    ("A_ENTITY_TABLE", "include/player.h", "A_entity_table"),
    ("A_PLAYER_RECORD", "include/enemy.h", "A_player_record"),
    ("A_SCROLL_FROZEN", "include/enemy.h", "A_scroll_frozen"),
    ("A_FREE_WAVE_SLOT_COUNT", "include/enemy.h", "A_free_wave_slot_count"),
    ("A_SQUADRON_KILL_COUNTERS", "include/enemy.h", "A_squadron_kill_counters"),
    ("A_ANIM_PHASE_B", "include/enemy.h", "A_anim_phase_b"),
    ("A_EXPLOSION_PHASE_ODD", "include/enemy.h", "A_explosion_phase_odd"),
    ("A_ASTEROID_ANIM_TOGGLE", "include/enemy.h", "A_asteroid_anim_toggle"),
    ("A_ANIM_FRAMES_TYPE12", "include/enemy.h", "A_anim_frames_type12"),
    ("A_ANIM_FRAMES_TYPE14", "include/enemy.h", "A_anim_frames_type14"),
    ("A_ANIM_FRAMES_TYPE15", "include/enemy.h", "A_anim_frames_type15"),
    ("A_ANIM_FRAMES_TYPE17", "include/enemy.h", "A_anim_frames_type17"),
    ("A_ANIM_FRAMES_GROUND_T34", "include/enemy.h", "A_anim_frames_ground_t34"),
    ("A_PUFF_FRAME_PTRS_B", "include/enemy.h", "A_puff_frame_ptrs_b"),
    ("A_ENEMY_SPRITE_PTRS_B", "include/enemy.h", "A_enemy_sprite_ptrs_b"),
    ("A_SHOT_VARIANT_TABLE", "include/weapon.h", "A_shot_variant_table"),
    ("A_ASTEROID_BANK_PTRS", "include/enemy.h", "A_asteroid_bank_ptrs"),
    ("KEEP_Y_MIN", "src/enemy.c", "ACTOR_KEEP_Y_MIN"),
    ("KEEP_Y_MAX", "src/enemy.c", "ACTOR_KEEP_Y_MAX"),
    ("KILL_X", "src/enemy.c", "ACTOR_KILL_X"),
    ("SCC_TRUE", "include/enemy.h", "SCC_BYTE_TRUE"),
    ("SCC_FALSE", "include/enemy.h", "SCC_BYTE_FALSE"),
    ("ENEMY_SLOT_COUNT", "include/enemy.h", "ENEMY_SLOT_COUNT"),
    ("GROUND_ACTOR_COUNT", "src/enemy.c", "GROUND_ACTOR_COUNT"),
    ("GROUND_ACTOR_TYPE", "src/enemy.c", "GROUND_ACTOR_TYPE"),
    ("GROUND_ANIM_FRAMES", "src/enemy.c", "GROUND_ANIM_FRAMES"),
    ("ASTEROID_GROUPS", "src/enemy.c", "ASTEROID_GROUPS"),
    ("ASTEROID_COLUMNS", "src/enemy.c", "ASTEROID_COLUMNS"),
    ("ASTEROID_ANIM_FRAMES", "src/enemy.c", "ASTEROID_ANIM_FRAMES"),
    ("ANIM_CYCLE_END", "src/enemy.c", "ANIM_CYCLE_END"),
    ("ANIM_TABLE_INDEX_MASK", "src/enemy.c", "ANIM_TABLE_INDEX_MASK"),
    ("STEP_LEFT", "src/enemy.c", "ENEMY_STEP_LEFT"),
    ("ENTITY_PIXEL_HIT", "include/entity.h", "ENTITY_PIXEL_HIT"),
    ("ENTITY_AX", "include/entity.h", "ENTITY_AX"),
    ("ENTITY_AY", "include/entity.h", "ENTITY_AY"),
    ("ACTOR_SPEED", "include/enemy.h", "ACTOR_SPEED"),
    ("ACTOR_BOUNCED", "include/enemy.h", "ACTOR_BOUNCED"),
    ("ACTOR_SINE_BASE_Y", "include/enemy.h", "ACTOR_SINE_BASE_Y"),
    ("ACTOR_SINE_PHASE", "include/enemy.h", "ACTOR_SINE_PHASE"),
    ("A_ENEMY_SHOT_SLOTS", "include/enemy.h", "A_enemy_shot_slots"),
    ("A_ACTOR_ANIM_TABLE", "include/enemy.h", "A_actor_anim_table"),
    ("A_ANIM_FRAMES_TYPE16", "include/enemy.h", "A_anim_frames_type16"),
    ("A_ANIM_FRAMES_TYPE20", "include/enemy.h", "A_anim_frames_type20"),
    ("A_ANIM_FRAMES_TYPE22", "include/enemy.h", "A_anim_frames_type22"),
    ("A_ANIM_FRAME_LIMIT_TYPE20", "include/enemy.h", "A_anim_frame_limit_type20"),
    ("A_ANIM_FRAME_LIMIT_TYPE22", "include/enemy.h", "A_anim_frame_limit_type22"),
    ("A_RNG_LFSR_STATE", "include/rng.h", "A_rng_lfsr_state"),
    ("A_ENTITY_COLLISION_MASKS", "include/collision.h", "A_entity_collision_masks"),
    ("COLLISION_ROW_BYTES", "include/collision.h", "COLLISION_ROW_BYTES"),
    ("SIN_DEGREES_FULL", "include/util.h", "SIN_DEGREES_FULL"),
    ("RNG_TAP_MASK", "src/rng.c", "RNG_TAP_MASK"),
    ("RNG_STEP_BITS", "src/rng.c", "RNG_STEP_BITS"),
    ("ACTOR_UPDATE_SLOTS", "src/enemy.c", "ACTOR_UPDATE_SLOTS"),
    ("ACTOR_HANDLER_TYPE_MAX", "src/enemy.c", "ACTOR_HANDLER_TYPE_MAX"),
    ("ACTOR_CENTRE_X", "src/enemy.c", "ACTOR_CENTRE_X"),
    ("ACTOR_CENTRE_Y", "src/enemy.c", "ACTOR_CENTRE_Y"),
    ("ACTOR_FLOOR_Y", "src/enemy.c", "ACTOR_FLOOR_Y"),
    ("SINE_STEP_LEFT", "src/enemy.c", "SINE_ENEMY_STEP_LEFT"),
    ("SINE_PHASE_STEP", "src/enemy.c", "SINE_ENEMY_PHASE_STEP"),
    ("NUDGE_MIN_DRAW", "src/enemy.c", "SPEED_NUDGE_MIN_DRAW"),
    ("NUDGE_UP_DRAW", "src/enemy.c", "SPEED_NUDGE_UP_DRAW"),
    # The ten entries of src/enemy.c's ACTOR_ANIM_HANDLERS, pinned against the same addresses the
    # ENTRY_PROLOGUES below hold to their routines' first bytes.
    ("FN_ACTOR_HANDLER_NONE", "src/enemy.c", "FN_actor_handler_none"),
    ("ENTRY_ANIM_ENEMY_TYPE20", "src/enemy.c", "FN_anim_enemy_type20"),
    ("ENTRY_ANIM_ENEMY_TYPE22", "src/enemy.c", "FN_anim_enemy_type22"),
    ("ENTRY_ANIM_ENEMY_TYPE16", "src/enemy.c", "FN_anim_enemy_type16"),
    ("ENTRY_ANIM_ENEMY_TYPE12", "src/enemy.c", "FN_anim_enemy_type12"),
    ("ENTRY_ANIM_ENEMY_TYPE14", "src/enemy.c", "FN_anim_enemy_type14"),
    ("ENTRY_ANIM_ENEMY_TYPE15_DIVING", "src/enemy.c", "FN_anim_enemy_type15"),
    ("ENTRY_ANIM_ENEMY_TYPE17", "src/enemy.c", "FN_anim_enemy_type17"),
    ("ENTRY_ENEMY_SET_SPRITE_B", "src/enemy.c", "FN_enemy_set_sprite_b"),
    ("ENTRY_ENEMY_ANIM_PUFF_B", "src/enemy.c", "FN_enemy_anim_puff_b"),
    ("A_EXPLOSION_GROUP_ACTIVE_BITS", "include/enemy.h", "A_explosion_group_active_bits"),
    ("A_EXPLOSION_GROUP_MEMBERS", "include/enemy.h", "A_explosion_group_members"),
    ("A_EXPLOSION_PARTICLE_OFFSETS", "include/enemy.h", "A_explosion_particle_offsets"),
    ("A_EXPLOSION_SMALL_FRAME_PTRS", "include/enemy.h", "A_explosion_small_frame_ptrs"),
    ("A_EXPLOSION_FRAME_TOGGLE", "include/enemy.h", "A_explosion_frame_toggle"),
    ("A_SCREEN_BACK", "include/video.h", "A_screen_back"),
    ("SCREEN_BYTES", "include/video.h", "SCREEN_BYTES"),
    ("PLAYFIELD_TOP_Y", "include/video.h", "PLAYFIELD_TOP_Y"),
    ("SPRITE_MASKED_ROW_BYTES", "include/sprite.h", "SPRITE_MASKED_ROW_BYTES"),
    ("ASTEROID_FRAME_ROWS", "include/sprite.h", "ASTEROID_FRAME_ROWS"),
    ("ASTEROID_FRAME_CELLS", "include/sprite.h", "ASTEROID_FRAME_CELLS"),
    ("EXPLOSION_PART_FRAME", "include/enemy.h", "EXPLOSION_PART_FRAME"),
    ("EXPLOSION_GROUPS", "src/enemy.c", "EXPLOSION_GROUPS"),
    ("EXPLOSION_PARTS", "src/enemy.c", "EXPLOSION_PARTS"),
    ("EXPLOSION_END_FRAME", "src/enemy.c", "EXPLOSION_END_FRAME"),
    ("EXPLOSION_OFFSET_WORDS", "src/enemy.c", "EXPLOSION_OFFSET_WORDS"),
)

# The first bytes of each routine, read off the loaded image — ten of them where ten is enough, and
# as many as it takes where it is not. `test_entry_addresses_still_point_at_their_routines` compares
# whatever length each value carries, so a pair that shares its opening is pinned by lengthening ITS
# entry rather than by weakening every other one:
#   * anim_enemy_type20 / anim_enemy_type22 open with the same gate, branch and frame bump and
#     separate only at the per-section limit byte they compare against, 25 bytes in — so both carry
#     26 bytes here;
#   * asteroids_move / asteroids_draw both open `lea $17e2a,a2 / move.w #$5,d7 / move.w #$2,d6 /
#     tst.b 14(a2)` and separate at the branch that follows it, 21 bytes in — so both carry 22.
# THREE ROUTINES ARE STILL TOLD APART BY THE DIFFERENTIAL INSTEAD: anim_enemy_type12,
# anim_enemy_type14 and enemy_anim_puff_b share their gate and frame bump and separate only at the
# table address 48 bytes in, which is past the point where a "prologue" is a prologue. Each writes a
# pointer out of its own table, so a swapped entry is red on that battery's first case.
ENTRY_PROLOGUES = {
    "ENTRY_COUNT_FREE_WAVE_SLOTS": "2f072f08420041f90001",
    "ENTRY_ENEMY_ALLOC_SLOT": "2f076100ec444a006700",
    "ENTRY_ENTITY_TYPE_IN_MASK": "c07c00ff3c00e648c07c",
    "ENTRY_ACTOR_CLAMP_Y": "0c6a001000046c000008",
    "ENTRY_ACTOR_DESPAWN": "102a002148804df90001",
    "ENTRY_ENEMY_MOVE_TYPE16_LEFT": "4a39000198b16600002a",
    "ENTRY_ENEMY_MOVE_TYPE17_LEFT": "046a000200000c6a0030",
    "ENTRY_ENEMY_MOVE_TYPE15_DIVE": "4a39000198b16600005a",
    "ENTRY_ACTOR_SCRIPT_OP_LOOP_BEGIN": "1001c03c0078e6081540",
    "ENTRY_ACTOR_SCRIPT_OP_SET_FIRE_RATE": "c23c0078e6091541001b",
    "ENTRY_ACTOR_SCRIPT_OP_DRIFT_LEFT": "4a39000198b167000004",
    "ENTRY_ACTOR_SCRIPT_OP_HALT": "426a0012426a00144e75",
    "ENTRY_ACTOR_SCRIPT_OP_LOOP_END": "042a0001002766000008",
    "ENTRY_ACTOR_SCRIPT_OP_STEP_LEFT": "046a00020000023c00fe",
    "ENTRY_ANIM_ENEMY_TYPE12": "4a39000198c566000034",
    "ENTRY_ANIM_ENEMY_TYPE14": "4a39000198c566000034",
    "ENTRY_ANIM_ENEMY_TYPE15_DIVING": "4a39000198c56600003c",
    "ENTRY_ANIM_ENEMY_TYPE17": "4a39000198ac67000034",
    "ENTRY_ENEMY_SET_SPRITE_B": "102a001d488041f90001",
    "ENTRY_ENEMY_ANIM_PUFF_B": "4a39000198c566000034",
    "ENTRY_ANIM_GROUND_OBJECTS": "4a39000198c56600004e",
    "ENTRY_ASTEROIDS_MOVE": "45f900017e2a3e3c00053c3c00024a2a000e67000056",
    "ENTRY_ASTEROIDS_ANIMATE": "4639000198fc67000004",
    "ENTRY_ENTITY_PTR_FROM_INDEX": "1c00ccbc000000ffccfc",
    "ENTRY_ENTITY_PTR_FROM_INDEX_D6": "ccbc000000ffccfc002c",
    "ENTRY_ANIM_ENEMY_TYPE20": "4a39000198ac660000324281122a0020d23c0001b2390001990f",
    "ENTRY_ANIM_ENEMY_TYPE22": "4a39000198ac660000324281122a0020d23c0001b23900019910",
    "ENTRY_ANIM_ENEMY_TYPE16": "4a39000198ac66000030",
    "ENTRY_ENEMIES_ANIMATE_ALL": "4639000198ac45f90001",
    "ENTRY_ENEMY_MOVE_TYPE14_SINE": "302a0000907c00046a00",
    "ENTRY_ACTOR_SCRIPT_OP_BOUNCE_FALL": "48e70020200a90bc0001",
    "ENTRY_ACTOR_SCRIPT_OP_SET_HEADING": "c23c0078e2091541001d",
    "ENTRY_ACTOR_SCRIPT_OP_RANDOM_HEADING": "6100ee14c03c003f1540",
    "ENTRY_ACTOR_SCRIPT_OP_THRUST_TO_CENTRE_Y": "323c00200c6a00600004",
    "ENTRY_ACTOR_SCRIPT_OP_AIM_AT_PLAYER": "43f900017d7a6100f40c",
    "ENTRY_ACTOR_SCRIPT_OP_THRUST_TO_CENTRE": "323c00080c6a00d80000",
    "ENTRY_ACTOR_SCRIPT_OP_RANDOM_SPEED_NUDGE": "6100ed6ab03c00556c00",
    "ENTRY_ACTOR_SCRIPT_CONTINUE": "003c00014e75023c00fe",
    "ENTRY_ACTOR_SCRIPT_OP_END_FRAME": "023c00fe4e75046a0002",
    "ENTRY_EXPLOSION_ANIMATE_ALL": "4a3900019670670000b8",
    "ENTRY_EXPLOSION_SPAWN": "302a0000322a000405f9",
    "ENTRY_ASTEROIDS_DRAW": "45f900017e2a3e3c00053c3c00024a2a000e67000012",
}
