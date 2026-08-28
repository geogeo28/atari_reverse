"""Differential tests for src/collision.c.

Three of the four routines here WRITE NO MEMORY — their whole answer is the 68000's Z flag, which
every call site reads with a `beq`. Their cases therefore enter at a poked stub that calls the
routine and turns the flag into a byte with `seq` (test/abi.py's `register_call_eq_flag_pokes`),
the same trick test_sound.py uses for a register-only answer.
"""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, report

ENTRY_OBJECT_PAIR_OVERLAP_MARK = 0x11cce
ENTRY_COLLISION_CHAIN_WALK = 0x12d44
ENTRY_OBJECT_TYPE_IS_COLLIDABLE = 0x12dc6
ENTRY_ENTITY_TYPE_IS_LETHAL = 0x13d6e

# --- mirrors of include/collision.h ---
A_ENTITY_COLLISION_MASKS = 0x18252
A_LOWER_INDEX_MASKS = 0x19dda
A_TYPE_HITS_TERRAIN_BITS = 0x19196
A_TYPE_LETHAL_TO_SHIP_BITS = 0x191a4
ENTITY_HEIGHT_MASK = 0x7fff
TYPE_TARGETABLE_MAX = 0x31
TYPE_TERRAIN_SENSITIVE_MAX = 0x37
CHAIN_WALK_D7_OFFSET = 2
# --- mirrors of src/collision.c ---
OBJECT_BOX_WIDTH = 0x10
COLLISION_ROW_BYTES = 4
# --- mirrors of include/player.h ---
A_ENTITY_TABLE = 0x17a8e
# --- mirrors of include/entity.h ---
ENTITY_STRIDE = 0x2c
ENTITY_X, ENTITY_Y, ENTITY_HEIGHT, ENTITY_PIXEL_HIT, ENTITY_TYPE = 0x00, 0x04, 0x08, 0x0f, 0x11

# What the stub's result bytes hold before either side runs — neither `seq` answer, so a candidate
# that stores nothing is caught rather than matching by luck.
RESULT_CANARY = 0x5a

# The two class bitmaps, read off the shipped image rather than restated: these are the types the
# GAME's own tables actually list, and every "in the class" case below drives one of them.
TERRAIN_TYPES = (0x0a, 0x0c, 0x0f, 0x11, 0x14, 0x16, 0x32, 0x33, 0x34, 0x36)
LETHAL_TYPES = (0x01, 0x02, 0x03, 0x04, 0x05, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10,
                0x14, 0x15, 0x16)

# The overlap table is 21 rows (`move.w #$14,d0` + `dbf` in the builder at 0x11c00); the pair loop
# below it only ever reaches indices 0..19, the entity table's own 20 slots.
COLLISION_ROWS = 21
ENTITY_SLOTS = 20

for _name, _args in (
        ("g_object_pair_overlap_mark", [ctypes.c_uint32] * 6),
        ("g_collision_chain_walk", [ctypes.c_uint32] * 2),
        ("g_object_type_is_collidable", [ctypes.c_uint32] * 2),
        ("g_entity_type_is_lethal", [ctypes.c_uint32] * 2)):
    getattr(harness._lib, _name).argtypes = [ctypes.POINTER(ctypes.c_uint8)] + _args
    getattr(harness._lib, _name).restype = None


def _class_bit(table, type_byte):
    """What the shipped bit table says about `type_byte`, read the routine's own way (MSB first)."""
    entry = table + (type_byte >> 4) * 2
    word = int.from_bytes(bytes(harness.BASE_IMAGE[entry:entry + 2]), "big")
    return (word >> (15 - (type_byte & 0xf))) & 1


# ================================================================================================
# The two type-class tests. Identical in shape; they differ only in table and range bound.
# ================================================================================================
def _record(**fields):
    """A whole 44-byte record filled with noise, so a candidate touching the wrong field diverges."""
    record = bytearray(random.Random(sum(fields.values())).randbytes(ENTITY_STRIDE))
    for offset, value in fields.items():
        record[int(offset[1:], 0)] = value
    return bytes(record)


def _class_case(entry, glue, record_register, type_byte, poison=False):
    pokes = abi.register_call_eq_flag_pokes(entry, abi.RESULT)
    pokes[abi.SCRATCH] = _record(_0x11=type_byte)
    pokes[abi.RESULT] = bytes([RESULT_CANARY] * 8)
    regs = {record_register: abi.SCRATCH, "_pokes": pokes}
    diffs, _ = differential(abi.STUB, regs,
                            lambda lib, buf: glue(lib)(buf, abi.RESULT, abi.SCRATCH),
                            poison=poison)
    assert not diffs, f"type={type_byte:#04x}\n{report(diffs)}"


def _collidable_case(type_byte, poison=False):
    _class_case(ENTRY_OBJECT_TYPE_IS_COLLIDABLE, lambda lib: lib.g_object_type_is_collidable,
                "a0", type_byte, poison)


def _lethal_case(type_byte, poison=False):
    _class_case(ENTRY_ENTITY_TYPE_IS_LETHAL, lambda lib: lib.g_entity_type_is_lethal,
                "a4", type_byte, poison)


CLASS_CHUNKS = 4


@pytest.mark.parametrize("chunk", range(CLASS_CHUNKS))
def test_every_type_byte_against_both_class_tables(chunk):
    """All 256 type bytes through both routines, sharded four ways.

    Exhaustive rather than sampled because the interesting inputs are not where a sample looks. The
    bound is a SIGNED byte comparison, so every type from 0x80 up takes the in-range arm and
    resolves through `ext.w` to a word offset of 0x1ff0..0x1ffe — 8 KB past the table, into whatever
    the text segment holds there. Those 128 inputs are the whole reason the probe's `lsr.w`/`not.w`
    arithmetic is driven over the full word rather than over 0..0x37.
    """
    for type_byte in range(chunk, 0x100, CLASS_CHUNKS):
        _collidable_case(type_byte)
        _lethal_case(type_byte)


@pytest.mark.parametrize("type_byte", TERRAIN_TYPES)
def test_the_terrain_types_the_game_ships(type_byte):
    """Every type the shipped 0x19196 table actually lists — including the player's own shots.

    0x32/0x33/0x34/0x36 are ABOVE `TYPE_TARGETABLE_MAX` and still in this table, which is what the
    wider `TYPE_TERRAIN_SENSITIVE_MAX` bound exists for: a player shot does react to the landscape,
    while nothing above 0x37 does. Narrowing this routine's bound to its three siblings' would break
    exactly these four.
    """
    assert _class_bit(A_TYPE_HITS_TERRAIN_BITS, type_byte), "the shipped table lost a member"
    _collidable_case(type_byte)


@pytest.mark.parametrize("type_byte", LETHAL_TYPES)
def test_the_lethal_types_the_game_ships(type_byte):
    assert _class_bit(A_TYPE_LETHAL_TO_SHIP_BITS, type_byte), "the shipped table lost a member"
    _lethal_case(type_byte)


@pytest.mark.parametrize("type_byte", (TYPE_TERRAIN_SENSITIVE_MAX - 1, TYPE_TERRAIN_SENSITIVE_MAX,
                                       TYPE_TERRAIN_SENSITIVE_MAX + 1,
                                       TYPE_TARGETABLE_MAX - 1, TYPE_TARGETABLE_MAX,
                                       TYPE_TARGETABLE_MAX + 1,
                                       0x7f, 0x80, 0xff))
def test_class_range_bounds(type_byte):
    """One step either side of each routine's own bound, and both sides of the signed byte's edge.

    The terrain bound IS pinned here — 0x36 is a member of the shipped table and 0x37 is the last
    type it can describe, so tightening it by one turns this red. The lethal routine's is NOT; see
    the test below.
    """
    _collidable_case(type_byte)
    _lethal_case(type_byte)


def test_the_lethal_bound_is_unobservable_at_its_own_value():
    """Whether TYPE_TARGETABLE_MAX itself is IN range cannot be shown from here.

    The bound is `type > last_type`; tightening it to `>=` changes the answer for exactly one input,
    `last_type` itself — and the shipped table has that type's bit clear, so both spellings answer
    "not lethal". Measured: the tightened comparison survives the whole suite (STATUS.md's survivor
    ledger). Asserted rather than left implied, so the day the table gains that bit this says why
    the mutation has suddenly become killable.
    """
    assert not _class_bit(A_TYPE_LETHAL_TO_SHIP_BITS, TYPE_TARGETABLE_MAX)


def test_class_attribution():
    """Poison the stub's result bytes: a candidate that never stores an answer cannot stay green.

    Driven on a type in the class and one out of it for each routine, because the flag byte is the
    only thing either run writes and 0x00/0xff are what it can be — a pass that came from the
    canary already holding the answer is what this rules out.
    """
    for type_byte in (0x0a, 0x38):
        _collidable_case(type_byte, poison=True)
    for type_byte in (0x01, 0x38):
        _lethal_case(type_byte, poison=True)


# ================================================================================================
# object_pair_overlap_mark — the all-pairs box test.
# ================================================================================================
def _pair_pokes(left_box, right_box, rows):
    def record(box):
        raw = bytearray(b"\xa5" * ENTITY_STRIDE)
        raw[ENTITY_X:ENTITY_X + 2] = (box[0] & 0xffff).to_bytes(2, "big")
        raw[ENTITY_Y:ENTITY_Y + 2] = (box[1] & 0xffff).to_bytes(2, "big")
        raw[ENTITY_HEIGHT:ENTITY_HEIGHT + 2] = (box[2] & 0xffff).to_bytes(2, "big")
        return bytes(raw)

    return {abi.SCRATCH: record(left_box),
            abi.SCRATCH + ENTITY_STRIDE: record(right_box),
            A_ENTITY_COLLISION_MASKS: rows}


def _pair_case(left_box, right_box, left_index=5, right_index=2, shared_row=None, poison=False):
    """One ordered pair, with both mask rows seeded non-zero so an extra `bset` shows up.

    `shared_row` points BOTH row pointers at that one index — see test_both_rows_are_read_before.
    """
    rows = bytes(bytearray(range(COLLISION_ROWS * COLLISION_ROW_BYTES)))
    left, right = abi.SCRATCH, abi.SCRATCH + ENTITY_STRIDE
    left_row_index = left_index if shared_row is None else shared_row
    right_row_index = right_index if shared_row is None else shared_row
    left_row = A_ENTITY_COLLISION_MASKS + left_row_index * COLLISION_ROW_BYTES
    right_row = A_ENTITY_COLLISION_MASKS + right_row_index * COLLISION_ROW_BYTES
    regs = {"a2": left, "a1": right, "a3": left_row, "a4": right_row,
            "a5": left_index, "a6": right_index,
            "_pokes": _pair_pokes(left_box, right_box, rows)}
    diffs, _ = differential(
        ENTRY_OBJECT_PAIR_OVERLAP_MARK, regs,
        lambda lib, buf: lib.g_object_pair_overlap_mark(buf, left, right, left_row, right_row,
                                                        left_index, right_index),
        poison=poison)
    assert not diffs, f"left={left_box} right={right_box}\n{report(diffs)}"


LEFT_BOX = (0x40, 0x40, 0x10)   # x, y, rows — the fixed box the edge cases move a partner around


@pytest.mark.parametrize("dx", (-OBJECT_BOX_WIDTH - 1, -OBJECT_BOX_WIDTH, -OBJECT_BOX_WIDTH + 1,
                                0, OBJECT_BOX_WIDTH - 1, OBJECT_BOX_WIDTH, OBJECT_BOX_WIDTH + 1))
@pytest.mark.parametrize("dy", (-0x11, -0x10, -0xf, 0, 0xf, 0x10, 0x11))
def test_box_edges(dx, dy):
    """The partner box stepped across all four `blt` bounds, one pixel either side of each.

    Both spans are exclusive at both ends — boxes that share an edge do NOT overlap — and each of
    the four comparisons has its own asymmetric pair of operands (the widths come from a literal,
    the heights from the two records), so a swapped operand shows up on one side of the grid only.
    """
    _pair_case(LEFT_BOX, (LEFT_BOX[0] + dx, LEFT_BOX[1] + dy, 0x10))


@pytest.mark.parametrize("height", (0, 1, 0x10, ENTITY_HEIGHT_MASK, ENTITY_HEIGHT_MASK + 1,
                                    0x8010, 0xffff))
def test_height_is_masked_and_wraps(height):
    """Field 8's bit 15 is a flag, not part of the row count, and the bottom edge is a 16-bit ADD.

    0x8010 and 0x10 must behave identically (the mask), and 0xffff must behave as 0x7fff. The pair
    at ENTITY_HEIGHT_MASK/+1 is what separates the mask from a plain read: unmasked, 0x8000 rows
    would put the bottom edge a whole word below the top.
    """
    _pair_case((0x40, 0x40, height), (0x44, 0x44, height))
    _pair_case((0x40, 0x40, height), (0x44, 0x60, height))


@pytest.mark.parametrize("y", (0x7ff0, 0x7ff8, 0x8000, 0xfff8))
def test_bottom_edge_wraps_at_sixteen_bits(y):
    """`add.w` on a y near the word's sign boundary, compared with a SIGNED `blt`.

    A bottom edge computed at 32 bits would stay above the partner and report an overlap where the
    original's wrapped, negative edge reports none.
    """
    _pair_case((0x40, y, 0x10), (0x44, y, 0x10))
    _pair_case((0x40, y, 0x10), (0x44, 0x40, 0x10))


@pytest.mark.parametrize("left_index,right_index", ((1, 0), (19, 18), (19, 0), (2, 1)))
def test_the_mark_is_reciprocal(left_index, right_index):
    """Row i gets bit j and row j gets bit i — never the same bit in both rows.

    The index pairs are the loop's own shape (0x11c78: i from 1 to 19, j from 0 to i-1), so a
    reconstruction that marked row i twice, or used one index for both `bset`s, diverges here.
    """
    _pair_case((0x40, 0x40, 0x10), (0x44, 0x44, 0x10), left_index, right_index)


@pytest.mark.parametrize("left_index,right_index", ((5, 2), (2, 5), (0, 31), (31, 0), (7, 7)))
def test_both_rows_are_read_before_either_is_stored(left_index, right_index):
    """Aim BOTH row pointers at one longword: only ONE of the two bits survives.

    The original reads (a3) and (a4), sets a bit in each register, and stores both back — so when
    the two rows are the same address the second store overwrites the first, and the bit for
    `right_index` is lost. Two sequential read-modify-writes would keep both, and that is the only
    thing separating the two spellings: with distinct rows they are identical, which is why the rest
    of this battery cannot see the ordering.

    The rows are POINTER ARGUMENTS (A3/A4), so driving them at one address explores the routine's
    own input the way test_sprite.py's aliased pointer pairs do; the game's builder passes distinct
    rows, and this says what happens at the input it does not use.
    """
    _pair_case((0x40, 0x40, 0x10), (0x44, 0x44, 0x10), left_index, right_index, shared_row=3)


def test_pair_attribution():
    """Poison the two mask rows: a candidate that never sets a bit cannot pass on the seeded value.

    The overlapping shape only — on a miss the oracle writes nothing at all, so there is nothing to
    poison and the pass would merely repeat the plain one.
    """
    _pair_case((0x40, 0x40, 0x10), (0x44, 0x44, 0x10), poison=True)


PAIR_FUZZ_CHUNKS = 4
PAIR_FUZZ_CASES = 240


def _pair_fuzz_cases():
    rng = random.Random(ENTRY_OBJECT_PAIR_OVERLAP_MARK)   # seeded ONCE; every chunk replays it
    for case in range(PAIR_FUZZ_CASES):
        # Cluster the partner near the fixed box so most cases land on or just off an edge.
        near = case % 3
        yield (case,
               (LEFT_BOX[0] + rng.randrange(-0x14, 0x15) if near else rng.randrange(1 << 16),
                LEFT_BOX[1] + rng.randrange(-0x14, 0x15) if near else rng.randrange(1 << 16),
                rng.randrange(1 << 16)),
               rng.randrange(ENTITY_SLOTS), rng.randrange(ENTITY_SLOTS))


@pytest.mark.parametrize("chunk", range(PAIR_FUZZ_CHUNKS))
def test_pair_fuzz(chunk):
    for case, right_box, left_index, right_index in _pair_fuzz_cases():
        if case % PAIR_FUZZ_CHUNKS == chunk:
            _pair_case(LEFT_BOX, right_box, left_index, right_index)


# ================================================================================================
# collision_chain_walk — did the pixel hit come from the landscape?
# ================================================================================================
def _chain_pokes(records, mask_rows):
    """`records` is {index: (pixel_hit, type)}; `mask_rows` is {index: overlap longword}.

    The record table is ENTITY_SLOTS long and the mask table COLLISION_ROWS — they are different
    lengths (20 records against 21 mask rows) and sizing the first with the second would pre-zero a
    record's worth of bss past slot 19, which is exactly where a wrong stride would land.
    """
    table = bytearray(b"\x00" * (ENTITY_SLOTS * ENTITY_STRIDE))
    for index, (pixel_hit, type_byte) in records.items():
        table[index * ENTITY_STRIDE + ENTITY_PIXEL_HIT] = pixel_hit
        table[index * ENTITY_STRIDE + ENTITY_TYPE] = type_byte
    rows = bytearray(b"\x00" * (COLLISION_ROWS * COLLISION_ROW_BYTES))
    for index, mask in mask_rows.items():
        start = index * COLLISION_ROW_BYTES
        rows[start:start + COLLISION_ROW_BYTES] = mask.to_bytes(COLLISION_ROW_BYTES, "big")
    return {A_ENTITY_TABLE: bytes(table), A_ENTITY_COLLISION_MASKS: bytes(rows)}


def _chain_case(index, records, mask_rows, poison=False):
    pokes = abi.register_call_eq_flag_pokes(ENTRY_COLLISION_CHAIN_WALK, abi.RESULT, ("d7",))
    pokes.update(_chain_pokes(records, mask_rows))
    pokes[abi.RESULT] = bytes([RESULT_CANARY] * 8)
    regs = {"d0": index, "d7": 0x5eed5eed, "_pokes": pokes}
    diffs, _ = differential(abi.STUB, regs,
                            lambda lib, buf: lib.g_collision_chain_walk(buf, abi.RESULT, index),
                            poison=poison)
    assert not diffs, f"index={index}\n{report(diffs)}"


TERRAIN_TYPE = TERRAIN_TYPES[0]        # 0x0a — a type the shipped 0x19196 table lists
INERT_TYPE = 0x00                      # ...and one it does not
PIXEL_HIT = 0x01


def test_lower_index_masks_are_what_the_walk_assumes():
    """entry i = (1 << i) - 1, read off the image. The walk's TERMINATION rests on it: masking with
    it leaves only strictly lower indices, so each hop descends and the chain cannot cycle."""
    for index in range(COLLISION_ROWS):
        entry = A_LOWER_INDEX_MASKS + index * COLLISION_ROW_BYTES
        assert int.from_bytes(bytes(harness.BASE_IMAGE[entry:entry + 4]), "big") == (1 << index) - 1


def test_no_pixel_hit_returns_immediately():
    """`tst.b 15(a0)` / `beq`: an entity the blitter did not flag is never walked at all."""
    _chain_case(5, {5: (0, TERRAIN_TYPE)}, {5: 0xffffffff})


@pytest.mark.parametrize("type_byte", (INERT_TYPE, TYPE_TERRAIN_SENSITIVE_MAX + 1, 0x35))
def test_type_that_ignores_terrain_returns_zero(type_byte):
    """The type test guards the ENTRY only. A flagged entity whose type is not terrain-sensitive
    answers 0 however its overlap row reads."""
    _chain_case(5, {5: (PIXEL_HIT, type_byte)}, {5: 0})


@pytest.mark.parametrize("index", range(ENTITY_SLOTS))
def test_unexplained_hit_at_every_index(index):
    """A flagged, terrain-sensitive entity overlapping nothing below it: the hit was the landscape.

    Driven at every index the builder reaches, because the record address and both row addresses
    are computed from that index with different arithmetic — `mulu.w #$2c` for one and `lsl.w #2`
    for the other two — so a wrong stride shows up at some indices and not at others.
    """
    _chain_case(index, {index: (PIXEL_HIT, TERRAIN_TYPE)}, {index: 0})


def test_row_bits_at_or_above_the_index_are_masked_away():
    """Only overlaps with LOWER indices explain a hit; the entity's own bit and every higher one is
    filtered by A_LOWER_INDEX_MASKS, so a row of all-ones still answers 1 at index 0."""
    _chain_case(0, {0: (PIXEL_HIT, TERRAIN_TYPE)}, {0: 0xffffffff})
    _chain_case(3, {3: (PIXEL_HIT, TERRAIN_TYPE)}, {3: 0xfffffff8})


def test_one_hop_to_a_flagged_partner():
    """Index 5 overlaps 2, which is itself flagged and overlaps nothing below: still the landscape.

    The partner's TYPE is deliberately inert — the walk does not re-test it, only the pixel-hit
    flag, which is the difference between the 0x12d44 entry and the 0x12d78 loop head.
    """
    _chain_case(5, {5: (PIXEL_HIT, TERRAIN_TYPE), 2: (PIXEL_HIT, INERT_TYPE)},
                {5: 1 << 2, 2: 0})


def test_one_hop_to_an_unflagged_partner():
    """...and the same chain with the partner unflagged: another sprite explains the hit, answer 0."""
    _chain_case(5, {5: (PIXEL_HIT, TERRAIN_TYPE), 2: (0, INERT_TYPE)}, {5: 1 << 2, 2: 0})


def test_the_walk_takes_the_lowest_bit_not_the_highest():
    """Row 8 overlaps 2, 5 and 7; only 2 is unflagged. The answer separates the two orders: taking
    the lowest bit reaches 2 and returns 0, taking the highest reaches 7 and returns 1."""
    records = {8: (PIXEL_HIT, TERRAIN_TYPE), 7: (PIXEL_HIT, INERT_TYPE),
               5: (PIXEL_HIT, INERT_TYPE), 2: (0, INERT_TYPE)}
    _chain_case(8, records, {8: (1 << 2) | (1 << 5) | (1 << 7), 7: 0, 5: 0, 2: 0})


def test_a_long_chain():
    """19 -> 12 -> 6 -> 1 -> 0, every link flagged: four hops and still the landscape."""
    chain = (19, 12, 6, 1, 0)
    records = {index: (PIXEL_HIT, TERRAIN_TYPE) for index in chain}
    rows = {index: (1 << chain[step + 1]) if step + 1 < len(chain) else 0
            for step, index in enumerate(chain)}
    _chain_case(19, records, rows)


def test_chain_attribution():
    """Poison the stub's flag and D7 store on both answers."""
    _chain_case(5, {5: (PIXEL_HIT, TERRAIN_TYPE)}, {5: 0}, poison=True)
    _chain_case(5, {5: (0, TERRAIN_TYPE)}, {5: 0}, poison=True)


CHAIN_FUZZ_CHUNKS = 4
CHAIN_FUZZ_CASES = 200


def _chain_fuzz_cases():
    rng = random.Random(ENTRY_COLLISION_CHAIN_WALK)   # seeded ONCE; every chunk replays it
    for case in range(CHAIN_FUZZ_CASES):
        records = {index: (rng.randrange(2), rng.choice(TERRAIN_TYPES + (INERT_TYPE, 0x38, 0xc9)))
                   for index in range(ENTITY_SLOTS)}
        rows = {index: rng.getrandbits(32) for index in range(ENTITY_SLOTS)}
        yield case, rng.randrange(ENTITY_SLOTS), records, rows


@pytest.mark.parametrize("chunk", range(CHAIN_FUZZ_CHUNKS))
def test_chain_fuzz(chunk):
    """Random flags, types and rows over the whole index range.

    Every row is random rather than a hand-built chain, so the walk really does hop — and it still
    terminates, because the shipped A_LOWER_INDEX_MASKS makes every hop strictly downwards (pinned
    by test_lower_index_masks_are_what_the_walk_assumes above).
    """
    for case, index, records, rows in _chain_fuzz_cases():
        if case % CHAIN_FUZZ_CHUNKS == chunk:
            _chain_case(index, records, rows)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_ENTITY_COLLISION_MASKS", "include/collision.h", "A_entity_collision_masks"),
    ("A_LOWER_INDEX_MASKS", "include/collision.h", "A_lower_index_masks"),
    ("A_TYPE_HITS_TERRAIN_BITS", "include/collision.h", "A_type_hits_terrain_bits"),
    ("A_TYPE_LETHAL_TO_SHIP_BITS", "include/collision.h", "A_type_lethal_to_ship_bits"),
    ("ENTITY_HEIGHT_MASK", "include/collision.h", "ENTITY_HEIGHT_MASK"),
    ("TYPE_TARGETABLE_MAX", "include/collision.h", "TYPE_TARGETABLE_MAX"),
    ("TYPE_TERRAIN_SENSITIVE_MAX", "include/collision.h", "TYPE_TERRAIN_SENSITIVE_MAX"),
    ("CHAIN_WALK_D7_OFFSET", "include/collision.h", "CHAIN_WALK_D7_OFFSET"),
    ("OBJECT_BOX_WIDTH", "src/collision.c", "OBJECT_BOX_WIDTH"),
    ("COLLISION_ROW_BYTES", "src/collision.c", "COLLISION_ROW_BYTES"),
    ("A_ENTITY_TABLE", "include/player.h", "A_entity_table"),
    ("ENTITY_STRIDE", "include/entity.h", "ENTITY_STRIDE"),
    ("ENTITY_X", "include/entity.h", "ENTITY_X"),
    ("ENTITY_Y", "include/entity.h", "ENTITY_Y"),
    ("ENTITY_HEIGHT", "include/entity.h", "ENTITY_HEIGHT"),
    ("ENTITY_PIXEL_HIT", "include/entity.h", "ENTITY_PIXEL_HIT"),
    ("ENTITY_TYPE", "include/entity.h", "ENTITY_TYPE"),
)
ENTRY_PROLOGUES = {
    "ENTRY_OBJECT_PAIR_OVERLAP_MARK": "302a0000322a0004342a",
    "ENTRY_COLLISION_CHAIN_WALK": "320041f900017a8ec0fc",
    "ENTRY_OBJECT_TYPE_IS_COLLIDABLE": "14280011b43c00376f00",
    "ENTRY_ENTITY_TYPE_IS_LETHAL": "1c2c0011bc3c00326d00",
}
