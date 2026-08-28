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

# ---- record layout (mirrors of include/entity.h and include/enemy.h) ----
ENTITY_STRIDE = 0x2c
ENTITY_X, ENTITY_Y, ENTITY_SPRITE = 0x00, 0x04, 0x0a
ENTITY_ALIVE, ENTITY_TYPE = 0x0e, 0x11
ENTITY_DX, ENTITY_DY = 0x12, 0x14
ENTITY_ANIM_FRAME, ENTITY_SQUADRON = 0x20, 0x21
ACTOR_FIRE_COUNTDOWN, ACTOR_FIRE_RELOAD, ACTOR_DIVING = 0x1b, 0x1c, 0x1c
ACTOR_HEADING = 0x1d
ACTOR_SCRIPT_PC, ACTOR_SCRIPT_LOOP_PC, ACTOR_SCRIPT_LOOP_COUNT = 0x22, 0x24, 0x27
ASTEROID_Y_DESCENDING, ASTEROID_SLOW = 0x1e, 0x21

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
                    ("g_actor_script_op_set_fire_rate", 3)):
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


def _flag_pokes(entry, condition):
    """The stub for a routine whose answer is a condition code, under a canary the stub overwrites.

    Two bytes, so the byte the stub does NOT write is seeded too — a candidate storing a word where
    the original stores a byte differs.
    """
    pokes = abi.flag_call_pokes(entry, condition)
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


def _script_case(entry, glue, record, opcode=0, poison=False, frozen=0):
    pokes = _flag_pokes(entry, "cs")
    pokes[ACTOR] = record.bytes()
    pokes[A_SCROLL_FROZEN] = bytes([frozen])
    regs = {"a0": FLAG, "a2": ACTOR, "d1": opcode, "_pokes": pokes}
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


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("ENTITY_STRIDE", "include/entity.h", "ENTITY_STRIDE"),
    ("ENTITY_X", "include/entity.h", "ENTITY_X"),
    ("ENTITY_Y", "include/entity.h", "ENTITY_Y"),
    ("ENTITY_SPRITE", "include/entity.h", "ENTITY_SPRITE"),
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
    ("A_ENTITY_TABLE", "include/enemy.h", "A_entity_table"),
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
    ("A_SHOT_VARIANT_TABLE", "include/enemy.h", "A_shot_variant_table"),
    ("A_ASTEROID_BANK_PTRS", "include/enemy.h", "A_asteroid_bank_ptrs"),
    ("KEEP_Y_MIN", "src/enemy.c", "ACTOR_KEEP_Y_MIN"),
    ("KEEP_Y_MAX", "src/enemy.c", "ACTOR_KEEP_Y_MAX"),
    ("KILL_X", "src/enemy.c", "ACTOR_KILL_X"),
    ("SCC_TRUE", "include/enemy.h", "SCC_BYTE_TRUE"),
    ("SCC_FALSE", "include/enemy.h", "SCC_BYTE_FALSE"),
    ("ENEMY_SLOT_COUNT", "src/enemy.c", "ENEMY_SLOT_COUNT"),
    ("GROUND_ACTOR_COUNT", "src/enemy.c", "GROUND_ACTOR_COUNT"),
    ("GROUND_ACTOR_TYPE", "src/enemy.c", "GROUND_ACTOR_TYPE"),
    ("GROUND_ANIM_FRAMES", "src/enemy.c", "GROUND_ANIM_FRAMES"),
    ("ASTEROID_GROUPS", "src/enemy.c", "ASTEROID_GROUPS"),
    ("ASTEROID_COLUMNS", "src/enemy.c", "ASTEROID_COLUMNS"),
    ("ASTEROID_ANIM_FRAMES", "src/enemy.c", "ASTEROID_ANIM_FRAMES"),
    ("ANIM_CYCLE_END", "src/enemy.c", "ANIM_CYCLE_END"),
    ("ANIM_TABLE_INDEX_MASK", "src/enemy.c", "ANIM_TABLE_INDEX_MASK"),
    ("STEP_LEFT", "src/enemy.c", "ENEMY_STEP_LEFT"),
)

# The first ten bytes of each routine, read off the loaded image. Three of them SHARE a prologue —
# anim_enemy_type12, anim_enemy_type14 and enemy_anim_puff_b all open with the same gate and frame
# bump, separating only at the table address 48 bytes in. Those three are told apart by the
# differential itself instead: each writes a pointer out of its own table, so a swapped entry is red
# on the first case rather than on this pin.
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
    "ENTRY_ASTEROIDS_MOVE": "45f900017e2a3e3c0005",
    "ENTRY_ASTEROIDS_ANIMATE": "4639000198fc67000004",
}
