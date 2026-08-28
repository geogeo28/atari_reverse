"""Differential tests for the shared arithmetic and block-move leaves (src/util.c).

Six of the eight routines write no memory at all — their answers are registers — so those cases run
through `abi.register_dump_pokes`, a `movem.l` stub that lands the registers in diffed memory. The
two that do write memory (the entity motion pair) are diffed on the record itself.
"""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, hi_garbage, report

ENTRY_COPY_BLOCK_WORDS = 0x13858
ENTRY_SIN_QUADRANT_SCALED = 0x15694
ENTRY_SIN_SCALED = 0x15654
ENTRY_COS_SCALED = 0x15644
ENTRY_ANGLE_TO_TARGET = 0x1424c
ENTRY_ENTITY_SET_VELOCITY_FROM_ANGLE = 0x142d4
ENTRY_ENTITY_APPLY_VELOCITY = 0x14306
ENTRY_ENTITY_APPLY_ACCEL = 0x143f8

A_SINE_TABLE_Q1 = 0x18e46    # mirror of include/util.h
A_COS_TABLE_64 = 0x18efc

ENTITY_X = 0x00              # mirror of include/entity.h
ENTITY_Y = 0x04
ENTITY_DX = 0x12
ENTITY_DY = 0x14
ENTITY_AX = 0x16             # mirror of include/util.h — entity.h is frozen and lacks the pair
ENTITY_AY = 0x18
ENTITY_STRIDE = 0x2c

SIN_DEGREES_QUADRANT = 90    # mirror of include/util.h
SIN_DEGREES_FULL = 360
# The first quadrant's table is 91 words, so this is the last angle inside it and the first past it.
SINE_TABLE_ENTRIES = SIN_DEGREES_QUADRANT + 1

# Two records, far enough apart that a routine walking one can never reach the other.
SELF = abi.SCRATCH
TARGET = abi.SCRATCH + ENTITY_STRIDE

for _name, _argtypes in (
        ("g_copy_block_words", [ctypes.c_uint32] * 4),
        ("g_sin_quadrant_scaled", [ctypes.c_uint32] * 3),
        ("g_sin_scaled", [ctypes.c_uint32] * 3),
        ("g_cos_scaled", [ctypes.c_uint32] * 3),
        ("g_angle_to_target", [ctypes.c_uint32] * 4),
        ("g_entity_set_velocity_from_angle", [ctypes.c_uint32] * 3),
        ("g_entity_apply_velocity", [ctypes.c_uint32]),
        ("g_entity_apply_accel", [ctypes.c_uint32] * 2)):
    getattr(harness._lib, _name).argtypes = [ctypes.POINTER(ctypes.c_uint8)] + _argtypes
    getattr(harness._lib, _name).restype = None


def _noise(rng, length):
    return rng.randbytes(length)


# =================================================================================================
# copy_block_words @ 0x13858
# =================================================================================================

# movem order — d0..d7 then a0..a6 ascending, whatever order they are named in (test/abi.py).
_COPY_STORES = ("d2", "a0", "a1")
COPY_RESULT_BYTES = 4 * len(_COPY_STORES)


def _copy_case(byte_count, src, dst, source_bytes, dest_bytes=None, poison=False):
    """Run copy_block_words(A0 = src, A1 = dst, D2 = byte_count) over staged buffers.

    Both buffers are seeded where they are disjoint — the destination too, so a candidate copying
    one word too few leaves a seeded byte standing and differs. An overlapping case seeds only the
    source, since the two spans are the same bytes.
    """
    pokes = abi.register_dump_pokes(ENTRY_COPY_BLOCK_WORDS, _COPY_STORES)
    pokes[src] = source_bytes
    if dest_bytes is not None:
        pokes[dst] = dest_bytes
    pokes[abi.RESULT] = bytes(range(0x41, 0x41 + COPY_RESULT_BYTES))
    regs = {"a0": src, "a1": dst, "d2": byte_count, "_pokes": pokes}
    diffs, _ = differential(abi.STUB, regs,
                            lambda lib, buf: lib.g_copy_block_words(buf, src, dst, byte_count,
                                                                    abi.RESULT),
                            poison=poison)
    assert not diffs, f"count={byte_count:#x} src={src:#x} dst={dst:#x}\n{report(diffs)}"


# Byte counts the game itself passes, read off the `move.l #<n>,d2` beside each call site
# (0x1037c and its nine neighbours build the pre-shifted sprite banks; 0x153cc builds one bank).
# They are all even and all small; the odd and the huge counts below are this battery's own.
SHIPPED_COPY_COUNTS = (0x20, 0x50, 0xa0, 0x140, 0x2c0)


@pytest.mark.parametrize("byte_count", SHIPPED_COPY_COUNTS + (2, 4, 6, 0x400))
def test_copy_disjoint(byte_count):
    """A plain disjoint copy, destination seeded so a short run shows up."""
    rng = random.Random(byte_count)
    dst = abi.SCRATCH + 0x1000
    _copy_case(byte_count, abi.SCRATCH, dst, _noise(rng, byte_count + 4), _noise(rng, byte_count + 4))


@pytest.mark.parametrize("byte_count", (3, 5, 0x2b))
def test_copy_odd_byte_count_rounds_down(byte_count):
    """`lsr.l #1` DISCARDS the odd byte, so 3 copies one word and 5 copies two.

    A count of 1 belongs to this family too, but it halves to 0 and takes the wrap arm — 128 KB of
    traffic rather than a handful of words — so it has a case of its own below.
    """
    rng = random.Random(byte_count)
    dst = abi.SCRATCH + 0x100
    _copy_case(byte_count, abi.SCRATCH, dst, _noise(rng, 0x40), _noise(rng, 0x40))


def test_copy_count_zero_wraps_the_word_counter():
    """`dbf` exits at -1, so a halved count of 0 copies 0x10000 words, not none.

    Run IN PLACE (A0 == A1) so the 128 KB of traffic stays inside the scratch band the map reserves;
    the copied bytes are then unobservable, and what the case actually pins is the two cursors and
    the counter the stub dumps — 0x20000 apart from where they started, which no other count gives.
    """
    rng = random.Random(0)
    _copy_case(0, abi.SCRATCH, abi.SCRATCH, _noise(rng, 0x40))


def test_copy_count_is_a_longword():
    """`lsr.l`/`sub.l` are 32-bit, and only the counter the stub dumps can tell.

    0x20004 halves to 0x10002, whose low word is 2 — so two words are copied either way, and a
    word-sized reading of the same instructions differs ONLY in the high half D2 comes back with.
    """
    rng = random.Random(0x20004)
    dst = abi.SCRATCH + 0x100
    _copy_case(0x20004, abi.SCRATCH, dst, _noise(rng, 0x40), _noise(rng, 0x40))


@pytest.mark.parametrize("offset", (2, 4, -2, 0x10, -0x10))
def test_copy_overlapping(offset):
    """Source and destination overlapping, which is what holds the copy's DIRECTION.

    The routine copies forward through both cursors; at these offsets a backward run would write a
    word it has yet to read. The game's own call sites are disjoint, so this dimension is the
    battery's — but the inputs are a bare pointer pair, not invented game data.
    """
    rng = random.Random(offset)
    src = abi.SCRATCH + 0x200
    _copy_case(0x40, src, src + offset, _noise(rng, 0x100))


def test_copy_attribution():
    """Poison the copied bytes and the dumped registers: a candidate that writes neither stays
    canary."""
    rng = random.Random(1)
    dst = abi.SCRATCH + 0x1000
    _copy_case(0x40, abi.SCRATCH, dst, _noise(rng, 0x40), _noise(rng, 0x40), poison=True)


# =================================================================================================
# The scaled sine — 0x15694 / 0x15654 / 0x15644
# =================================================================================================

_SINE_STORES = ("d0",)


def _sine_case(entry, glue_name, angle, amplitude, poison=False):
    """Call one of the three sine entries with D0 = angle, D2 = amplitude; the answer is D0."""
    pokes = abi.register_dump_pokes(entry, _SINE_STORES)
    pokes[abi.RESULT] = bytes(range(0x51, 0x55))
    regs = {"d0": angle, "d2": amplitude, "_pokes": pokes}
    diffs, _ = differential(
        abi.STUB, regs,
        lambda lib, buf: getattr(lib, glue_name)(buf, angle, amplitude, abi.RESULT),
        poison=poison)
    assert not diffs, f"{glue_name} angle={angle:#x} amp={amplitude:#x}\n{report(diffs)}"


# The amplitudes every case sweeps: both ends of the word, the +/-0x100 the entity tables use, and
# one value with bits in both halves so a swapped/shifted answer cannot coincide.
SINE_AMPLITUDES = (0, 1, 0x100, 0x5a5a, 0x8000, 0xffff)

FUZZ_CHUNKS = 4


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_sin_quadrant_every_table_entry(chunk):
    """Every angle the folded entry is ever handed — 0..90, the whole first-quadrant table."""
    for angle in range(chunk, SINE_TABLE_ENTRIES, FUZZ_CHUNKS):
        for amplitude in SINE_AMPLITUDES:
            _sine_case(ENTRY_SIN_QUADRANT_SCALED, "g_sin_quadrant_scaled", angle, amplitude)


def test_sin_quadrant_indexes_below_the_table_when_the_angle_is_negative():
    """`lsl.w #1` then a `d0.w` index register SIGN-EXTENDS, so a negative angle reads BELOW
    0x18e46 rather than wrapping. Every such address is still inside the image (the table sits
    0x8e46 above the load base and the whole reachable span is +/-0x8000), so this is faithful
    behaviour with a real answer, not an out-of-bounds read."""
    for angle in (0xffff, 0xfff8, 0x8000, 0x4000, 0x7fff):
        _sine_case(ENTRY_SIN_QUADRANT_SCALED, "g_sin_quadrant_scaled", angle, 0x100)


def test_sin_quadrant_high_halves_are_ignored():
    """Every step is a word or byte operation until `and.l #$ffff,d0` clears D0's high half, so
    junk above either argument's low word must not reach the answer."""
    rng = random.Random(ENTRY_SIN_QUADRANT_SCALED)
    for angle in (0, 45, SIN_DEGREES_QUADRANT):
        _sine_case(ENTRY_SIN_QUADRANT_SCALED, "g_sin_quadrant_scaled",
                   hi_garbage(rng, angle), hi_garbage(rng, 0x100))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_sin_every_degree(chunk):
    """All 360 degrees through the four-quadrant fold, at both ends of the amplitude range.

    Sharded four ways; every chunk walks the same range and takes its own quarter, so coverage is
    identical to one 360-case loop. The three boundaries the fold turns on (90/180/270) are hit by
    construction, and one past each.
    """
    for angle in range(chunk, SIN_DEGREES_FULL, FUZZ_CHUNKS):
        _sine_case(ENTRY_SIN_SCALED, "g_sin_scaled", angle, 0x100)
        _sine_case(ENTRY_SIN_SCALED, "g_sin_scaled", angle, 0xffff)


@pytest.mark.parametrize("angle", (0, 1, 89, 90, 91, 179, 180, 181, 269, 270, 271, 359,
                                   360, 0x7fff, 0x8000, 0xffff, 0xfff6))
def test_sin_boundaries_and_out_of_range(angle):
    """The three fold boundaries either side, and the angles OUTSIDE 0..359.

    All four comparisons are signed, so 0x8000 and 0xffff take the FIRST arm (they read as negative
    and so as `<= 90`) rather than the fourth — which an unsigned reading would get backwards.
    """
    for amplitude in SINE_AMPLITUDES:
        _sine_case(ENTRY_SIN_SCALED, "g_sin_scaled", angle, amplitude)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_cos_every_degree(chunk):
    """All 360 degrees through the +90 shift, whose wrap arm 270..359 alone reaches."""
    for angle in range(chunk, SIN_DEGREES_FULL, FUZZ_CHUNKS):
        _sine_case(ENTRY_COS_SCALED, "g_cos_scaled", angle, 0x100)


@pytest.mark.parametrize("angle", (0, 269, 270, 271, 359, 0x8000, 0xffff))
def test_cos_wrap_boundary(angle):
    """270 is the first angle whose +90 reaches 360 and takes the subtraction; the two either side
    hold the boundary, and the negative pair holds the SIGNED compare that decides it."""
    for amplitude in SINE_AMPLITUDES:
        _sine_case(ENTRY_COS_SCALED, "g_cos_scaled", angle, amplitude)


@pytest.mark.parametrize("angle", (0, 45, 90, 200, 300))
def test_sine_attribution(angle):
    """Poison the dumped answer: a candidate that stores nothing stays canary."""
    _sine_case(ENTRY_SIN_SCALED, "g_sin_scaled", angle, 0x100, poison=True)


# =================================================================================================
# angle_to_target @ 0x1424c
# =================================================================================================

_ANGLE_STORES = ("d0",)
_ANGLE_D0_GARBAGE = 0xdead0000   # D0's high word is the caller's; `move.w d4,d0` must leave it


def _entity_record(rng, fields):
    """One 0x2c-byte record: noise everywhere, with `fields` (offset -> value) laid over it.

    Noise rather than zeroes, so a routine reading a field this case did not mean to set — or
    writing one it should not — shows up in the diff.
    """
    record = bytearray(_noise(rng, ENTITY_STRIDE))
    for offset, value in fields.items():
        record[offset:offset + 2] = value.to_bytes(2, "big")
    return bytes(record)


def _angle_case(self_x, self_y, target_x, target_y, poison=False):
    rng = random.Random(hash((self_x, self_y, target_x, target_y)))
    pokes = abi.register_dump_pokes(ENTRY_ANGLE_TO_TARGET, _ANGLE_STORES)
    pokes[SELF] = _entity_record(rng, {ENTITY_X: self_x, ENTITY_Y: self_y})
    pokes[TARGET] = _entity_record(rng, {ENTITY_X: target_x, ENTITY_Y: target_y})
    pokes[abi.RESULT] = bytes(range(0x61, 0x65))
    regs = {"a2": SELF, "a1": TARGET, "d0": _ANGLE_D0_GARBAGE, "_pokes": pokes}
    diffs, _ = differential(
        abi.STUB, regs,
        lambda lib, buf: lib.g_angle_to_target(buf, SELF, TARGET, _ANGLE_D0_GARBAGE, abi.RESULT),
        poison=poison)
    assert not diffs, (f"self=({self_x:#x},{self_y:#x}) target=({target_x:#x},{target_y:#x})\n"
                       f"{report(diffs)}")


# A ring of targets around one fixed source, at cell distances that put the vector in every octant
# and on both diagonals — the three flag arms (negative y, negative x, x/y swap) and the sub-step
# search all key on which of these the case is.
ANGLE_RING_ORIGIN = 0x400
ANGLE_RING_OFFSETS = (0, 8, 0x20, 0x40, 0x80, -8, -0x20, -0x40, -0x80)


@pytest.mark.parametrize("dx", ANGLE_RING_OFFSETS)
def test_angle_ring(dx):
    """Every (dx, dy) pair from the ring above — all eight octants, both axes and both diagonals."""
    for dy in ANGLE_RING_OFFSETS:
        _angle_case(ANGLE_RING_ORIGIN, ANGLE_RING_ORIGIN,
                    ANGLE_RING_ORIGIN + dx, ANGLE_RING_ORIGIN + dy)


@pytest.mark.parametrize("bit", (0, 1, 2, 3, 4))
def test_angle_half_cell_rounding(bit):
    """Only bit 2 of the TARGET's coordinate rounds its cell up, and only the target's.

    Sweeping one bit at a time over both coordinates of both records is what separates `btst #2`
    from its neighbours: setting bit 1 or bit 3 must change nothing that bit 2 changes.
    """
    value = 1 << bit
    for base in (0x100, 0x101):
        _angle_case(base, base, base + value, base)
        _angle_case(base, base, base, base + value)
        _angle_case(base + value, base, base, base)


def test_angle_negative_coordinates():
    """`lsr.w #3` is a LOGICAL shift, so a coordinate with bit 15 set becomes a large positive cell
    rather than a negative one — and the delta that comes out of it is what the sign tests see."""
    for coord in (0x8000, 0xffff, 0xfff8):
        _angle_case(coord, coord, 0x100, 0x100)
        _angle_case(0x100, 0x100, coord, coord)


def test_angle_equal_positions():
    """A zero vector: both legs 0, so the search runs its counter to 0 and the answer is the flags
    alone. It is the one input for which the loop takes every one of its eight passes."""
    _angle_case(0x200, 0x200, 0x200, 0x200)


ANGLE_FUZZ_CASES = 400
ANGLE_FUZZ_COORD_MAX = 0x600     # a playfield-sized span, well clear of the word's sign bit


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_angle_fuzz(chunk):
    """Random source/target pairs across the playfield, sharded four ways.

    Each chunk seeds from its own index and draws its own quarter of the cases, so the run is
    reproducible and the shards do not overlap.
    """
    rng = random.Random(ENTRY_ANGLE_TO_TARGET + chunk)
    for _ in range(ANGLE_FUZZ_CASES // FUZZ_CHUNKS):
        coords = [rng.randrange(ANGLE_FUZZ_COORD_MAX) for _ in range(4)]
        _angle_case(*coords)


def test_angle_attribution():
    """Poison the dumped answer over four vectors, one per quadrant."""
    for dx, dy in ((0x40, 0x20), (-0x40, 0x20), (0x40, -0x20), (-0x40, -0x20)):
        _angle_case(ANGLE_RING_ORIGIN, ANGLE_RING_ORIGIN,
                    ANGLE_RING_ORIGIN + dx, ANGLE_RING_ORIGIN + dy, poison=True)


# =================================================================================================
# The entity motion — 0x142d4 / 0x14306 / 0x143f8
# =================================================================================================

def _motion_case(entry, glue, fields, regs, poison=False):
    """Run one motion routine over a single seeded record at SELF and diff the record.

    The record is noise outside the fields the case sets, so a routine writing a field it should
    not — or leaving one it should write — differs.
    """
    rng = random.Random(entry + sum(fields.values()))
    pokes = {SELF: _entity_record(rng, fields)}
    diffs, _ = differential(entry, {**regs, "a2": SELF, "_pokes": pokes}, glue, poison=poison)
    shown = {f"{offset:#x}": f"{value:#x}" for offset, value in fields.items()}
    assert not diffs, f"{entry:#x} regs={regs} fields={shown}\n{report(diffs)}"


VELOCITY_ANGLES = tuple(range(0x40))          # the 6-bit circle names.txt says the game passes
VELOCITY_SPEEDS = (0, 1, 2, 0x7f, 0x80, 0xff)  # D1.b is SIGNED: 0x80 is -128 and 0xff is -1


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_set_velocity_every_angle(chunk):
    """Every 6-bit angle against every speed byte, sharded four ways.

    The speeds straddle the byte's sign bit because `ext.w d1` sign-extends it before `muls.w` —
    reading the speed unsigned would agree on 0..0x7f and differ on every value above.
    """
    for angle in VELOCITY_ANGLES[chunk::FUZZ_CHUNKS]:
        for speed in VELOCITY_SPEEDS:
            _motion_case(ENTRY_ENTITY_SET_VELOCITY_FROM_ANGLE,
                         lambda lib, buf, a=angle, s=speed:
                             lib.g_entity_set_velocity_from_angle(buf, SELF, a, s),
                         {}, {"d0": angle, "d1": speed})


@pytest.mark.parametrize("angle", (0x40, 0x50, 0x7f, 0xff))
def test_set_velocity_past_the_table(angle):
    """The x index is masked to a BYTE, not to the 6-bit circle, so an angle above 0x3f reads past
    the 64-word table into the data behind it. Faithful, and the y index — masked to 0x3f — stays
    inside it for the same input, which is what makes the pair of masks visible at all."""
    for speed in (1, 0xff):
        _motion_case(ENTRY_ENTITY_SET_VELOCITY_FROM_ANGLE,
                     lambda lib, buf, a=angle, s=speed:
                         lib.g_entity_set_velocity_from_angle(buf, SELF, a, s),
                     {}, {"d0": angle, "d1": speed})


def test_set_velocity_ignores_the_high_bits_of_its_arguments():
    """`and.l #$ff,d0` and `ext.w d1` take a byte each, so junk above either must not reach the
    record — and D3's own high half, which the y index is built on top of, must not either."""
    rng = random.Random(ENTRY_ENTITY_SET_VELOCITY_FROM_ANGLE)
    for angle, speed in ((0x11, 3), (0x2f, 0xfe)):
        dirty_angle = hi_garbage(rng, angle | 0xff00)
        dirty_speed = hi_garbage(rng, speed | 0xff00)
        _motion_case(ENTRY_ENTITY_SET_VELOCITY_FROM_ANGLE,
                     lambda lib, buf, a=dirty_angle, s=dirty_speed:
                         lib.g_entity_set_velocity_from_angle(buf, SELF, a, s),
                     {}, {"d0": dirty_angle, "d1": dirty_speed,
                          "d3": rng.randrange(1 << 32)})


# Velocity words the position step is driven with: zero, both signs, and the two extremes whose
# <<8 fills the whole longword.
APPLY_VELOCITIES = (0, 1, 0xffff, 0x7fff, 0x8000, 0x0100, 0xff00)


@pytest.mark.parametrize("dx", APPLY_VELOCITIES)
def test_apply_velocity(dx):
    """`ext.l` then `lsl.l #8` — a SIGNED velocity scaled into the position's 8 fractional bits.

    Reading the velocity unsigned agrees for 0..0x7fff and moves the entity a whole screen the wrong
    way above it, which the position longword shows.
    """
    for dy in APPLY_VELOCITIES:
        for position in (0, 0x00010000, 0xffffff00, 0x7fffff00):
            _motion_case(ENTRY_ENTITY_APPLY_VELOCITY,
                         lambda lib, buf: lib.g_entity_apply_velocity(buf, SELF),
                         {ENTITY_DX: dx, ENTITY_DY: dy,
                          ENTITY_X: position >> 16, ENTITY_X + 2: position & 0xffff,
                          ENTITY_Y: position >> 16, ENTITY_Y + 2: position & 0xffff}, {})


def test_apply_velocity_attribution():
    """Poison both position longwords: a candidate that writes only one stays canary."""
    _motion_case(ENTRY_ENTITY_APPLY_VELOCITY,
                 lambda lib, buf: lib.g_entity_apply_velocity(buf, SELF),
                 {ENTITY_DX: 0x0123, ENTITY_DY: 0xfe80, ENTITY_X: 0x0002, ENTITY_Y: 0xfffe},
                 {}, poison=True)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_apply_accel_every_direction_byte(chunk):
    """All 256 direction bytes, sharded four ways.

    Exhaustive because the four bits are read as two EXCLUSIVE pairs tested in order — bit 3 wins
    over bit 4, bit 5 over bit 6 — and because with neither bit of a pair set the original branches
    past its own store, so that axis's velocity word must come back UNTOUCHED. Only a case with
    both bits clear and a velocity the routine did not compute can see that.
    """
    for bits in range(chunk, 0x100, FUZZ_CHUNKS):
        _motion_case(ENTRY_ENTITY_APPLY_ACCEL,
                     lambda lib, buf, b=bits: lib.g_entity_apply_accel(buf, SELF, b),
                     {ENTITY_DX: 0x0010, ENTITY_DY: 0xfff0, ENTITY_AX: 0x0003, ENTITY_AY: 0x0005,
                      ENTITY_X: 0x0100, ENTITY_Y: 0x0080},
                     {"d1": bits})


@pytest.mark.parametrize("bits", (0x08, 0x10, 0x20, 0x40, 0x18, 0x60, 0x78))
def test_apply_accel_wraps_the_velocity_word(bits):
    """The adjustment is a WORD add/subtract, so it wraps rather than saturating."""
    for velocity, accel in ((0x7fff, 0x0001), (0x8000, 0x0001), (0xffff, 0x0002), (0, 0xffff)):
        _motion_case(ENTRY_ENTITY_APPLY_ACCEL,
                     lambda lib, buf, b=bits: lib.g_entity_apply_accel(buf, SELF, b),
                     {ENTITY_DX: velocity, ENTITY_DY: velocity,
                      ENTITY_AX: accel, ENTITY_AY: accel,
                      ENTITY_X: 0x0100, ENTITY_Y: 0x0080},
                     {"d1": bits})


def test_apply_accel_ignores_the_high_bits_of_its_argument():
    """`btst` on a data register addresses bits modulo 32, but only bits 3..6 are ever tested, so
    junk elsewhere in D1 must not change the record."""
    rng = random.Random(ENTRY_ENTITY_APPLY_ACCEL)
    for bits in (0x08, 0x28, 0x00):
        dirty = hi_garbage(rng, bits | 0xff00)
        _motion_case(ENTRY_ENTITY_APPLY_ACCEL,
                     lambda lib, buf, b=dirty: lib.g_entity_apply_accel(buf, SELF, b),
                     {ENTITY_DX: 0x0010, ENTITY_DY: 0xfff0, ENTITY_AX: 0x0003, ENTITY_AY: 0x0005,
                      ENTITY_X: 0x0100, ENTITY_Y: 0x0080},
                     {"d1": dirty})


def test_apply_accel_attribution():
    """Poison the record over the four single-bit arms plus the no-op one."""
    for bits in (0x08, 0x10, 0x20, 0x40):
        _motion_case(ENTRY_ENTITY_APPLY_ACCEL,
                     lambda lib, buf, b=bits: lib.g_entity_apply_accel(buf, SELF, b),
                     {ENTITY_DX: 0x0010, ENTITY_DY: 0xfff0, ENTITY_AX: 0x0003, ENTITY_AY: 0x0005,
                      ENTITY_X: 0x0100, ENTITY_Y: 0x0080},
                     {"d1": bits}, poison=True)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_SINE_TABLE_Q1", "include/util.h", "A_sine_table_q1"),
    ("A_COS_TABLE_64", "include/util.h", "A_cos_table_64"),
    ("SIN_DEGREES_QUADRANT", "include/util.h", "SIN_DEGREES_QUADRANT"),
    ("SIN_DEGREES_FULL", "include/util.h", "SIN_DEGREES_FULL"),
    ("ENTITY_AX", "include/util.h", "ENTITY_AX"),
    ("ENTITY_AY", "include/util.h", "ENTITY_AY"),
    ("ENTITY_X", "include/entity.h", "ENTITY_X"),
    ("ENTITY_Y", "include/entity.h", "ENTITY_Y"),
    ("ENTITY_DX", "include/entity.h", "ENTITY_DX"),
    ("ENTITY_DY", "include/entity.h", "ENTITY_DY"),
    ("ENTITY_STRIDE", "include/entity.h", "ENTITY_STRIDE"),
)
ENTRY_PROLOGUES = {
    "ENTRY_COPY_BLOCK_WORDS": "e28a94bc0000000132d8",
    "ENTRY_SIN_QUADRANT_SCALED": "e34841f900018e463030",
    "ENTRY_SIN_SCALED": "b07c005a6f00003ab07c",
    "ENTRY_COS_SCALED": "d07c005ab07c01686d00",
    "ENTRY_ANGLE_TO_TARGET": "362a0000e64b32290000",
    "ENTRY_ENTITY_SET_VELOCITY_FROM_ANGLE": "4881c0bc000000ff1600",
    "ENTRY_ENTITY_APPLY_VELOCITY": "302a001248c0e188d1aa",
    "ENTRY_ENTITY_APPLY_ACCEL": "342a0012362a00160801",
}
