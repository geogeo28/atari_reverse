"""Differential tests for src/weapon.c.

The two type-class tests answer in the 68000's Z flag and write no memory, so they enter at
test/abi.py's `seq` stub exactly as collision.c's pair do. Everything else writes the image, and is
driven at its own entry with a seeded record.
"""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, report

ENTRY_ENTITY_TYPE_IS_LOCKABLE = 0x13d3e
ENTRY_POWERUP_SLOT1_ACTIVATE = 0x13ede
ENTRY_POWERUP_DOWNGRADE_ON_DEATH = 0x13f72
ENTRY_ENTITY_POS_FROM_SHIP = 0x14092
ENTRY_ENTITY_TYPE_IS_MISSILE_TARGET = 0x140f6
ENTRY_PLAYER_SHOT_UPDATE_ALL = 0x152a4
ENTRY_SHOT_SET_SPRITE_A = 0x152ea
ENTRY_SHOT_ANIM_PUFF = 0x15370
ENTRY_SHOT_RETIRE_KIND32 = 0x15582
ENTRY_SHOT_RETIRE_KIND36 = 0x155b4
ENTRY_SHOT_RETIRE_KIND33 = 0x155c2
ENTRY_SHOT_TO_PUFF = 0x155e2
ENTRY_PLAYER_SHOTS_CLEAR = 0x15604

# --- mirrors of include/weapon.h ---
A_ENTITY_GUNSIGHT = 0x17dd2
A_TYPE_MASK_MISSILE_TARGET = 0x1918e
A_TYPE_SEEKER_LOCKABLE_BITS = 0x191ac
A_SHOT_VARIANT_TABLE = 0x18f7c
A_SHOT_SPRITE_PTRS_A = 0x192ac
A_PUFF_FRAME_PTRS = 0x192fc
A_TRAIL_DRONE_ACTIVE = 0x19900
A_ACTIVE_COUNT_TYPE32 = 0x1990b
A_ACTIVE_COUNT_BOMBS = 0x1990c
A_ACTIVE_COUNT_SEEKERS = 0x1990d
A_MISSILE_LOCK_A = 0x19918
A_MISSILE_LOCK_B = 0x19919
A_EXPLOSION_PHASE_ODD = 0x198c5
SHOT_HEADING = 0x1d
SHOT_LOCK_SLOT_B = 0x8000
# --- mirrors of include/collision.h: the other half of the same record field ---
ENTITY_HEIGHT_MASK = 0x7fff
PLAYER_SHOT_SLOTS = 6
SHOT_TYPE_MISSILE, SHOT_TYPE_BOMB, SHOT_TYPE_SEEKER, SHOT_TYPE_PUFF = 0x32, 0x33, 0x36, 0x37
A_PUFF_SPRITE = 0x6791e
PUFF_Y_LIFT = 3
PUFF_ROWS = 0x10
PUFF_FIRST_FRAME = 1
PUFF_DEATH_FRAME = 5
PUFF_FRAME_INDEX_MASK = 0xf
SPRITE_PTR_BYTES = 4
# --- mirrors of include/player.h ---
A_ENTITY_TABLE = 0x17a8e
A_SHIP_RECORD_SHADOW = 0x17da6
A_SHIP_SPEED_LEVEL = 0x19907
A_WEAPON_POWER_LEVEL = 0x19908
A_WEAPON_DECAY_TIMER = 0x19dcc
POWERUP_DECAY_TICKS = 0x3e8
WEAPON_POWER_LEVEL_MIN = 2
# --- mirrors of include/collision.h ---
TYPE_TARGETABLE_MAX = 0x31
# --- mirrors of include/entity.h ---
ENTITY_STRIDE = 0x2c
ENTITY_X, ENTITY_Y, ENTITY_HEIGHT = 0x00, 0x04, 0x08
ENTITY_SPRITE, ENTITY_ALIVE, ENTITY_TYPE, ENTITY_ANIM_FRAME = 0x0a, 0x0e, 0x11, 0x20

RESULT_CANARY = 0x5a
ENTITY_SLOTS = 20               # the whole table, so a stray write past slot 5 is visible

# The types the shipped 0x191ac / 0x1918e tables list — the same set in both, read off the image.
LOCKABLE_TYPES = (0x01, 0x02, 0x03, 0x04, 0x05, 0x0e, 0x0f, 0x10, 0x14, 0x15, 0x16)

_UINT8P = ctypes.POINTER(ctypes.c_uint8)
for _name, _args in (
        ("g_entity_type_is_lockable", [ctypes.c_uint32] * 2),
        ("g_entity_type_is_missile_target", [ctypes.c_uint32] * 2),
        ("g_entity_pos_from_ship", [ctypes.c_uint32]),
        ("g_powerup_slot1_activate", []),
        ("g_powerup_downgrade_on_death", []),
        ("g_shot_to_puff", [ctypes.c_uint32]),
        ("g_shot_retire_kind32", [ctypes.c_uint32]),
        ("g_shot_retire_kind33", [ctypes.c_uint32]),
        ("g_shot_retire_kind36", [ctypes.c_uint32]),
        ("g_shot_set_sprite_a", [ctypes.c_uint32]),
        ("g_shot_anim_puff", [ctypes.c_uint32]),
        ("g_player_shot_update_all", []),
        ("g_player_shots_clear", [])):
    getattr(harness._lib, _name).argtypes = [_UINT8P] + _args
    getattr(harness._lib, _name).restype = None


def test_the_record_field_layouts_this_battery_leans_on():
    """Three relations that live across FILE boundaries, where no compiler can catch a drift.

    * ENTITY_HEIGHT's two halves are named in different subsystem headers — the row-count mask in
      collision.h and the lock-slot flag in weapon.h — and they are complements of one 16-bit field.
      Nothing but this says so.
    * A_entity_gunsight and A_ship_record_shadow are named as bare addresses, but each IS a slot of
      the entity table; the arithmetic is what makes `player_shots_clear` and `entity_pos_from_ship`
      reach the records this battery seeds through A_ENTITY_TABLE.
    """
    assert SHOT_LOCK_SLOT_B == (~ENTITY_HEIGHT_MASK) & 0xffff
    assert A_SHIP_RECORD_SHADOW == A_ENTITY_TABLE + 18 * ENTITY_STRIDE
    assert A_ENTITY_GUNSIGHT == A_ENTITY_TABLE + 19 * ENTITY_STRIDE


def _class_bit(table, type_byte):
    """What the shipped bit table says about `type_byte`, read the routine's own way (MSB first)."""
    entry = table + (type_byte >> 4) * 2
    word = int.from_bytes(bytes(harness.BASE_IMAGE[entry:entry + 2]), "big")
    return (word >> (15 - (type_byte & 0xf))) & 1


def _record(noise_seed, **fields):
    """A whole 44-byte record of noise, with the named byte/word/long fields overwritten.

    Everything the routine must NOT touch is noise, so a candidate writing an extra field diverges.
    Keys are `b<offset>` / `w<offset>` / `l<offset>` in hex.
    """
    raw = bytearray(random.Random(noise_seed).randbytes(ENTITY_STRIDE))
    for key, value in fields.items():
        offset, width = int(key[1:], 16), {"b": 1, "w": 2, "l": 4}[key[0]]
        raw[offset:offset + width] = (value & ((1 << (8 * width)) - 1)).to_bytes(width, "big")
    return bytes(raw)


def _shot_case(entry, glue_name, record, extra_pokes=None, poison=False, note=""):
    """Run one A2-taking routine on a record parked at abi.SCRATCH."""
    pokes = {abi.SCRATCH: record}
    pokes.update(extra_pokes or {})
    regs = {"a2": abi.SCRATCH, "_pokes": pokes}
    diffs, _ = differential(
        entry, regs,
        lambda lib, buf: getattr(lib, glue_name)(buf, abi.SCRATCH), poison=poison)
    assert not diffs, f"{note}\n{report(diffs)}"


# ================================================================================================
# The two type-class tests.
# ================================================================================================
def _class_case(entry, glue_name, record_register, type_byte, poison=False):
    pokes = abi.register_call_eq_flag_pokes(entry, abi.RESULT)
    pokes[abi.SCRATCH] = _record(type_byte, b11=type_byte)
    pokes[abi.RESULT] = bytes([RESULT_CANARY] * 8)
    regs = {record_register: abi.SCRATCH, "_pokes": pokes}
    diffs, _ = differential(
        abi.STUB, regs,
        lambda lib, buf: getattr(lib, glue_name)(buf, abi.RESULT, abi.SCRATCH), poison=poison)
    assert not diffs, f"type={type_byte:#04x}\n{report(diffs)}"


def _lockable_case(type_byte, poison=False):
    _class_case(ENTRY_ENTITY_TYPE_IS_LOCKABLE, "g_entity_type_is_lockable", "a2", type_byte, poison)


def _missile_target_case(type_byte, poison=False):
    _class_case(ENTRY_ENTITY_TYPE_IS_MISSILE_TARGET, "g_entity_type_is_missile_target", "a1",
                type_byte, poison)


CLASS_CHUNKS = 4


@pytest.mark.parametrize("chunk", range(CLASS_CHUNKS))
def test_every_type_byte_against_both_class_tables(chunk):
    """All 256 type bytes through both routines, sharded four ways.

    Exhaustive for the reason collision.py's twin is: the bound is a SIGNED byte comparison, so
    every type from 0x80 up takes the in-range arm and resolves 8 KB past its table. Nothing about
    a sample of the 0..0x37 range would exercise that.
    """
    for type_byte in range(chunk, 0x100, CLASS_CHUNKS):
        _lockable_case(type_byte)
        _missile_target_case(type_byte)


@pytest.mark.parametrize("type_byte", LOCKABLE_TYPES)
def test_the_lockable_types_the_game_ships(type_byte):
    """The members of both shipped tables — which hold the same eleven types, byte for byte."""
    for table in (A_TYPE_SEEKER_LOCKABLE_BITS, A_TYPE_MASK_MISSILE_TARGET):
        assert _class_bit(table, type_byte), "the shipped table lost a member"
    _lockable_case(type_byte)
    _missile_target_case(type_byte)


@pytest.mark.parametrize("type_byte", (TYPE_TARGETABLE_MAX - 1, TYPE_TARGETABLE_MAX,
                                       TYPE_TARGETABLE_MAX + 1, 0x7f, 0x80, 0xff))
def test_class_range_bounds(type_byte):
    """One step either side of the bound, and both sides of the signed byte's edge."""
    _lockable_case(type_byte)
    _missile_target_case(type_byte)


def test_the_class_bound_is_unobservable_at_its_own_value():
    """Whether TYPE_TARGETABLE_MAX itself is IN range cannot be shown from here.

    The bound is `type > last_type`; tightening it to `>=` changes the answer for exactly one input,
    `last_type` itself — and both shipped tables have that type's bit clear, so the two spellings
    answer alike. Measured: the tightened comparison survives the whole suite (STATUS.md's survivor
    ledger). Asserted rather than implied, so the claim is re-checked against the image every run
    instead of ageing in a comment.
    """
    for table in (A_TYPE_SEEKER_LOCKABLE_BITS, A_TYPE_MASK_MISSILE_TARGET):
        assert not _class_bit(table, TYPE_TARGETABLE_MAX)


def test_class_attribution():
    """Poison the flag byte on both answers of both routines."""
    for type_byte in (0x01, TYPE_TARGETABLE_MAX):
        _lockable_case(type_byte, poison=True)
        _missile_target_case(type_byte, poison=True)


# ================================================================================================
# entity_pos_from_ship, and the two power-up level routines.
# ================================================================================================
@pytest.mark.parametrize("x,y", ((0, 0), (0x40, 0x64), (0xffff, 0xffff), (0x8000, 0x7fff),
                                 (0x1234, 0x5678)))
def test_entity_pos_from_ship(x, y):
    """Both words copied from the SHADOW record, and nothing else in the destination touched.

    The destination is seeded with noise and the shadow with a known pair, so a copy of the wrong
    field — or of a long where the original copies two words — shows up immediately.
    """
    shadow = _record(x ^ y, w00=x, w04=y)
    _shot_case(ENTRY_ENTITY_POS_FROM_SHIP, "g_entity_pos_from_ship", _record(0xf00),
               {A_SHIP_RECORD_SHADOW: shadow}, note=f"x={x:#x} y={y:#x}")


def test_entity_pos_from_ship_attribution():
    _shot_case(ENTRY_ENTITY_POS_FROM_SHIP, "g_entity_pos_from_ship", _record(0xf00),
               {A_SHIP_RECORD_SHADOW: _record(1, w00=0x40, w04=0x64)}, poison=True)


def _timer_case(glue_name, entry, pokes, poison=False, note=""):
    diffs, _ = differential(entry, {"_pokes": pokes},
                            lambda lib, buf: getattr(lib, glue_name)(buf), poison=poison)
    assert not diffs, f"{note}\n{report(diffs)}"


@pytest.mark.parametrize("seed", (0x0000, POWERUP_DECAY_TICKS, 0xffff))
def test_powerup_slot1_activate(seed):
    """One word store, driven over a timer that already holds the value it is about to be given —
    which is what the poison pass below turns into a real check."""
    _timer_case("g_powerup_slot1_activate", ENTRY_POWERUP_SLOT1_ACTIVATE,
                {A_WEAPON_DECAY_TIMER: seed.to_bytes(2, "big") + b"\xa5\xa5"}, note=f"seed={seed:#x}")


def test_powerup_slot1_activate_attribution():
    _timer_case("g_powerup_slot1_activate", ENTRY_POWERUP_SLOT1_ACTIVATE,
                {A_WEAPON_DECAY_TIMER: b"\x00\x00\xa5\xa5"}, poison=True)


def _downgrade_case(speed, power, poison=False):
    """The two levels sit in adjacent bytes; both are poked with a trailing guard byte."""
    _timer_case("g_powerup_downgrade_on_death", ENTRY_POWERUP_DOWNGRADE_ON_DEATH,
                {A_SHIP_SPEED_LEVEL: bytes([speed, power, 0xa5])}, poison=poison,
                note=f"speed={speed:#04x} power={power:#04x}")


DOWNGRADE_CHUNKS = 4


@pytest.mark.parametrize("chunk", range(DOWNGRADE_CHUNKS))
def test_every_speed_level(chunk):
    """All 256 speed bytes. The floor is a SIGNED test on the decremented byte (`subq.b` + `bpl`),
    so 0x00 -> 0xff -> clamped to 0 while 0x80 -> 0x7f survives, and only a full sweep separates
    that from an unsigned or a compare-with-zero reading."""
    for speed in range(chunk, 0x100, DOWNGRADE_CHUNKS):
        _downgrade_case(speed, WEAPON_POWER_LEVEL_MIN + 1)


@pytest.mark.parametrize("chunk", range(DOWNGRADE_CHUNKS))
def test_every_weapon_power_level(chunk):
    """All 256 power bytes, against a signed `cmpi.b #$2` + `bge` floor."""
    for power in range(chunk, 0x100, DOWNGRADE_CHUNKS):
        _downgrade_case(1, power)


@pytest.mark.parametrize("speed", (0, 1, 2, 0x7f, 0x80, 0x81, 0xff))
@pytest.mark.parametrize("power", (0, 1, WEAPON_POWER_LEVEL_MIN, WEAPON_POWER_LEVEL_MIN + 1,
                                   0x80, 0xff))
def test_downgrade_corners(speed, power):
    """Both floors driven together, so a routine that clamped one level from the other's value —
    the two are adjacent bytes — cannot pass."""
    _downgrade_case(speed, power)


def test_downgrade_attribution():
    """Poison both level bytes, on a case that clamps and one that does not."""
    _downgrade_case(0, 0, poison=True)
    _downgrade_case(4, 8, poison=True)


# ================================================================================================
# Retiring a shot.
# ================================================================================================
LIVE_COUNTS = bytes([0x40, 0x41, 0x42])   # type32 / bombs / seekers, at three distinct values
COUNT_POKE = {A_ACTIVE_COUNT_TYPE32: LIVE_COUNTS}


@pytest.mark.parametrize("y", (0, 1, 2, PUFF_Y_LIFT, 0x8000, 0x8002, 0x7fff, 0xffff))
def test_shot_to_puff(y):
    """Every field the rewrite touches, over a y that borrows across the word's ends.

    `subi.w #$3` wraps at 16 bits: y=0 becomes 0xfffd and y=0x8002 becomes 0x7fff. The rest of the
    record is noise, so a candidate writing ENTITY_HEIGHT as a byte, or the sprite pointer as a
    word, diverges.
    """
    _shot_case(ENTRY_SHOT_TO_PUFF, "g_shot_to_puff", _record(y, w04=y), note=f"y={y:#x}")


def test_shot_to_puff_attribution():
    _shot_case(ENTRY_SHOT_TO_PUFF, "g_shot_to_puff", _record(7, w04=0x64), poison=True)


@pytest.mark.parametrize("alive", (0x00, 0x01, 0x80, 0xff))
@pytest.mark.parametrize("type_byte", (SHOT_TYPE_MISSILE, SHOT_TYPE_BOMB, SHOT_TYPE_SEEKER,
                                       SHOT_TYPE_PUFF, 0x00))
@pytest.mark.parametrize("height", (PUFF_ROWS, SHOT_LOCK_SLOT_B | PUFF_ROWS, 0x7fff, 0xffff))
def test_shot_retire_kind32(alive, type_byte, height):
    """The guard (alive AND type 0x32), and WHICH lock slot the sign of field 8 releases.

    Both lock bytes are poked to a marker, so a release of the wrong one is a diff rather than a
    coincidence; the height values step across bit 15 in both directions.
    """
    _shot_case(ENTRY_SHOT_RETIRE_KIND32, "g_shot_retire_kind32",
               _record(alive ^ type_byte ^ height, b0e=alive, b11=type_byte, w08=height),
               {A_ACTIVE_COUNT_TYPE32: LIVE_COUNTS, A_MISSILE_LOCK_A: b"\x77\x88\x99"},
               note=f"alive={alive:#04x} type={type_byte:#04x} height={height:#06x}")


@pytest.mark.parametrize("alive", (0x00, 0x01, 0xff))
@pytest.mark.parametrize("type_byte", (SHOT_TYPE_BOMB, SHOT_TYPE_MISSILE, SHOT_TYPE_SEEKER, 0x00))
def test_shot_retire_kind33(alive, type_byte):
    _shot_case(ENTRY_SHOT_RETIRE_KIND33, "g_shot_retire_kind33",
               _record(alive ^ type_byte, b0e=alive, b11=type_byte), COUNT_POKE,
               note=f"alive={alive:#04x} type={type_byte:#04x}")


@pytest.mark.parametrize("alive", (0x00, 0x01, 0xff))
@pytest.mark.parametrize("type_byte", (SHOT_TYPE_SEEKER, SHOT_TYPE_MISSILE, 0x00))
def test_shot_retire_kind36_has_no_guard(alive, type_byte):
    """Unlike its two neighbours this one tests nothing: even a dead, wrongly-typed slot is turned
    into a puff and the seeker count is decremented. Driven over the same grid to say so."""
    _shot_case(ENTRY_SHOT_RETIRE_KIND36, "g_shot_retire_kind36",
               _record(alive ^ type_byte, b0e=alive, b11=type_byte), COUNT_POKE,
               note=f"alive={alive:#04x} type={type_byte:#04x}")


@pytest.mark.parametrize("count", (0x00, 0x01, 0x80, 0xff))
def test_retire_counts_wrap_as_bytes(count):
    """`subi.b #$1` on a count of 0 wraps to 0xff — it does not borrow into its neighbour, which is
    what the three adjacent counters make observable."""
    counts = bytes([count] * 3)
    for entry, glue, type_byte in ((ENTRY_SHOT_RETIRE_KIND32, "g_shot_retire_kind32",
                                    SHOT_TYPE_MISSILE),
                                   (ENTRY_SHOT_RETIRE_KIND33, "g_shot_retire_kind33",
                                    SHOT_TYPE_BOMB),
                                   (ENTRY_SHOT_RETIRE_KIND36, "g_shot_retire_kind36",
                                    SHOT_TYPE_SEEKER)):
        _shot_case(entry, glue, _record(count, b0e=1, b11=type_byte, w08=PUFF_ROWS),
                   {A_ACTIVE_COUNT_TYPE32: counts, A_MISSILE_LOCK_A: b"\x77\x88\x99"},
                   note=f"count={count:#04x} entry={entry:#x}")


def test_retire_attribution():
    """Poison each retire's whole write set — record, count and, for kind 32, the lock byte."""
    _shot_case(ENTRY_SHOT_RETIRE_KIND32, "g_shot_retire_kind32",
               _record(1, b0e=1, b11=SHOT_TYPE_MISSILE, w08=PUFF_ROWS),
               {A_ACTIVE_COUNT_TYPE32: LIVE_COUNTS, A_MISSILE_LOCK_A: b"\x77\x88\x99"}, poison=True)
    _shot_case(ENTRY_SHOT_RETIRE_KIND33, "g_shot_retire_kind33",
               _record(2, b0e=1, b11=SHOT_TYPE_BOMB), COUNT_POKE, poison=True)
    _shot_case(ENTRY_SHOT_RETIRE_KIND36, "g_shot_retire_kind36",
               _record(3, b0e=1, b11=SHOT_TYPE_SEEKER), COUNT_POKE, poison=True)


# ================================================================================================
# The per-frame shot pass.
# ================================================================================================
SPRITE_CHUNKS = 4


def _sprite_case(heading, poison=False):
    _shot_case(ENTRY_SHOT_SET_SPRITE_A, "g_shot_set_sprite_a",
               _record(heading, b1d=heading), poison=poison, note=f"heading={heading:#04x}")


@pytest.mark.parametrize("chunk", range(SPRITE_CHUNKS))
def test_every_heading_picks_a_sprite(chunk):
    """All 256 heading bytes, sharded four ways.

    The game's own headings are 0..0x3f, exactly the length of A_SHOT_VARIANT_TABLE, but BOTH
    lookups sign-extend their index: a heading of 0x80 reads 128 bytes BELOW the variant table, and
    a variant byte it finds there is itself signed and can reach 512 bytes below the sprite table.
    Every one of those 256 resolutions stays inside the text segment, so all 256 are drivable — and
    they are what pins the two `ext.w`s. Dropping either turns this red above 0x7f.
    """
    for heading in range(chunk, 0x100, SPRITE_CHUNKS):
        _sprite_case(heading)


def test_the_shipped_variant_table_is_eight_ways():
    """The game's 64 headings map onto the 8 sprite pointers, read off the image — so the cases
    above really do walk the whole shipped fan-out and not one repeated entry."""
    variants = {harness.BASE_IMAGE[A_SHOT_VARIANT_TABLE + heading] for heading in range(0x40)}
    assert variants == set(range(8))


def test_sprite_attribution():
    for heading in (0, 0x1f, 0x80, 0xff):
        _sprite_case(heading, poison=True)


PUFF_CHUNKS = 4


def _puff_case(frame, phase, poison=False):
    _shot_case(ENTRY_SHOT_ANIM_PUFF, "g_shot_anim_puff",
               _record(frame ^ phase, b20=frame, b0e=1),
               {A_EXPLOSION_PHASE_ODD: bytes([phase, 0xa5])}, poison=poison,
               note=f"frame={frame:#04x} phase={phase:#04x}")


@pytest.mark.parametrize("chunk", range(PUFF_CHUNKS))
def test_every_puff_frame(chunk):
    """All 256 incoming frame bytes on the live phase.

    Three arms meet here and only a sweep separates them: the frame that kills the record is
    compared for EQUALITY (`cmpi.b #$5` + `bne`), not for "at least", so a frame of 6 or 0xff keeps
    animating; the pointer index is `(frame - 1) & 0xf`, so frame 0x11 draws the same picture as
    frame 1; and the increment is a byte, so 0xff wraps to 0 rather than growing.
    """
    for frame in range(chunk, 0x100, PUFF_CHUNKS):
        _puff_case(frame, phase=0)


@pytest.mark.parametrize("frame", (0, PUFF_FIRST_FRAME, PUFF_DEATH_FRAME - 1, PUFF_DEATH_FRAME,
                                   0xff))
@pytest.mark.parametrize("phase", (0x01, 0x80, 0xff))
def test_the_half_rate_gate_blocks_everything(frame, phase):
    """A non-zero phase byte returns before any field is touched — including the frame counter."""
    _puff_case(frame, phase)


def test_puff_attribution():
    for frame in (PUFF_FIRST_FRAME, PUFF_DEATH_FRAME - 1):
        _puff_case(frame, phase=0, poison=True)


def _table_pokes(slots, phase=0):
    """Seed the whole 20-record entity table; `slots` is {index: {field: value}}."""
    table = bytearray()
    for index in range(ENTITY_SLOTS):
        table += _record(0x2000 + index, **slots.get(index, {}))
    return {A_ENTITY_TABLE: bytes(table), A_EXPLOSION_PHASE_ODD: bytes([phase, 0xa5]),
            A_ACTIVE_COUNT_TYPE32: LIVE_COUNTS, A_TRAIL_DRONE_ACTIVE: b"\x33\xa5"}


def _table_case(entry, glue_name, slots, phase=0, poison=False, note=""):
    regs = {"_pokes": _table_pokes(slots, phase)}
    diffs, _ = differential(entry, regs, lambda lib, buf: getattr(lib, glue_name)(buf),
                            poison=poison)
    assert not diffs, f"{note}\n{report(diffs)}"


LIVE_SHOT = {"b0e": 1}


@pytest.mark.parametrize("phase", (0, 1))
def test_player_shot_update_all_dispatches_by_kind(phase):
    """One slot of each kind, plus a dead slot and an unknown kind, in one pass.

    Slots 6..19 are seeded too and must come back untouched — the loop runs over six slots, and a
    stride or a count that overran would rewrite a sprite pointer outside them.
    """
    slots = {0: dict(LIVE_SHOT, b11=SHOT_TYPE_MISSILE, b1d=0x05),
             1: dict(LIVE_SHOT, b11=SHOT_TYPE_SEEKER, b1d=0x2a),
             2: dict(LIVE_SHOT, b11=SHOT_TYPE_PUFF, b20=2),
             3: {"b0e": 0, "b11": SHOT_TYPE_MISSILE},
             4: dict(LIVE_SHOT, b11=SHOT_TYPE_BOMB),
             5: dict(LIVE_SHOT, b11=SHOT_TYPE_PUFF, b20=PUFF_DEATH_FRAME - 1)}
    _table_case(ENTRY_PLAYER_SHOT_UPDATE_ALL, "g_player_shot_update_all", slots, phase,
                note=f"phase={phase}")


@pytest.mark.parametrize("kind", (SHOT_TYPE_MISSILE, SHOT_TYPE_SEEKER, SHOT_TYPE_PUFF))
def test_player_shot_update_all_at_every_slot(kind):
    """The same kind in all six slots at once: a wrong stride lands on the wrong record."""
    slots = {slot: dict(LIVE_SHOT, b11=kind, b1d=slot * 7, b20=slot + 1)
             for slot in range(PLAYER_SHOT_SLOTS)}
    _table_case(ENTRY_PLAYER_SHOT_UPDATE_ALL, "g_player_shot_update_all", slots,
                note=f"kind={kind:#04x}")


def test_player_shot_update_all_attribution():
    slots = {slot: dict(LIVE_SHOT, b11=SHOT_TYPE_MISSILE, b1d=slot) for slot in range(3)}
    slots[3] = dict(LIVE_SHOT, b11=SHOT_TYPE_PUFF, b20=1)
    _table_case(ENTRY_PLAYER_SHOT_UPDATE_ALL, "g_player_shot_update_all", slots, poison=True)


@pytest.mark.parametrize("kind", (SHOT_TYPE_SEEKER, SHOT_TYPE_MISSILE, SHOT_TYPE_PUFF, 0x00))
@pytest.mark.parametrize("alive", (0, 1))
def test_player_shots_clear(kind, alive):
    """The gunsight is killed unconditionally; only LIVE seekers among slots 0..5 are retired.

    Slot 19 is the gunsight itself (A_ENTITY_GUNSIGHT is A_ENTITY_TABLE + 19 * ENTITY_STRIDE), so
    the same poked table carries both ends of the routine.
    """
    slots = {slot: {"b0e": alive, "b11": kind} for slot in range(PLAYER_SHOT_SLOTS)}
    slots[19] = {"b0e": 1}
    _table_case(ENTRY_PLAYER_SHOTS_CLEAR, "g_player_shots_clear", slots,
                note=f"kind={kind:#04x} alive={alive}")


def test_player_shots_clear_mixed_slots():
    """A mixture, so the count ends up decremented exactly as many times as there were seekers."""
    slots = {0: dict(LIVE_SHOT, b11=SHOT_TYPE_SEEKER),
             1: dict(LIVE_SHOT, b11=SHOT_TYPE_MISSILE),
             2: {"b0e": 0, "b11": SHOT_TYPE_SEEKER},
             3: dict(LIVE_SHOT, b11=SHOT_TYPE_SEEKER),
             4: dict(LIVE_SHOT, b11=SHOT_TYPE_PUFF),
             5: dict(LIVE_SHOT, b11=SHOT_TYPE_SEEKER),
             19: {"b0e": 0x80}}
    _table_case(ENTRY_PLAYER_SHOTS_CLEAR, "g_player_shots_clear", slots)


def test_player_shots_clear_attribution():
    slots = {slot: dict(LIVE_SHOT, b11=SHOT_TYPE_SEEKER) for slot in range(PLAYER_SHOT_SLOTS)}
    slots[19] = {"b0e": 1}
    _table_case(ENTRY_PLAYER_SHOTS_CLEAR, "g_player_shots_clear", slots, poison=True)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_ENTITY_GUNSIGHT", "include/weapon.h", "A_entity_gunsight"),
    ("A_TYPE_MASK_MISSILE_TARGET", "include/weapon.h", "A_type_mask_missile_target"),
    ("A_TYPE_SEEKER_LOCKABLE_BITS", "include/weapon.h", "A_type_seeker_lockable_bits"),
    ("A_SHOT_VARIANT_TABLE", "include/weapon.h", "A_shot_variant_table"),
    ("A_SHOT_SPRITE_PTRS_A", "include/weapon.h", "A_shot_sprite_ptrs_a"),
    ("A_PUFF_FRAME_PTRS", "include/weapon.h", "A_puff_frame_ptrs"),
    ("A_TRAIL_DRONE_ACTIVE", "include/weapon.h", "A_trail_drone_active"),
    ("A_ACTIVE_COUNT_TYPE32", "include/weapon.h", "A_active_count_type32"),
    ("A_ACTIVE_COUNT_BOMBS", "include/weapon.h", "A_active_count_bombs"),
    ("A_ACTIVE_COUNT_SEEKERS", "include/weapon.h", "A_active_count_seekers"),
    ("A_MISSILE_LOCK_A", "include/weapon.h", "A_missile_lock_a"),
    ("A_MISSILE_LOCK_B", "include/weapon.h", "A_missile_lock_b"),
    ("A_EXPLOSION_PHASE_ODD", "include/enemy.h", "A_explosion_phase_odd"),
    ("SHOT_HEADING", "include/weapon.h", "SHOT_HEADING"),
    ("SHOT_LOCK_SLOT_B", "include/weapon.h", "SHOT_LOCK_SLOT_B"),
    ("PLAYER_SHOT_SLOTS", "include/weapon.h", "PLAYER_SHOT_SLOTS"),
    ("SHOT_TYPE_MISSILE", "include/weapon.h", "SHOT_TYPE_MISSILE"),
    ("SHOT_TYPE_BOMB", "include/weapon.h", "SHOT_TYPE_BOMB"),
    ("SHOT_TYPE_SEEKER", "include/weapon.h", "SHOT_TYPE_SEEKER"),
    ("SHOT_TYPE_PUFF", "include/weapon.h", "SHOT_TYPE_PUFF"),
    ("A_PUFF_SPRITE", "include/weapon.h", "A_puff_sprite"),
    ("PUFF_Y_LIFT", "include/weapon.h", "PUFF_Y_LIFT"),
    ("PUFF_ROWS", "include/weapon.h", "PUFF_ROWS"),
    ("PUFF_FIRST_FRAME", "include/weapon.h", "PUFF_FIRST_FRAME"),
    ("PUFF_DEATH_FRAME", "include/weapon.h", "PUFF_DEATH_FRAME"),
    ("PUFF_FRAME_INDEX_MASK", "include/weapon.h", "PUFF_FRAME_INDEX_MASK"),
    ("SPRITE_PTR_BYTES", "include/weapon.h", "SPRITE_PTR_BYTES"),
    ("A_ENTITY_TABLE", "include/player.h", "A_entity_table"),
    ("A_SHIP_RECORD_SHADOW", "include/player.h", "A_ship_record_shadow"),
    ("A_SHIP_SPEED_LEVEL", "include/player.h", "A_ship_speed_level"),
    ("A_WEAPON_POWER_LEVEL", "include/player.h", "A_weapon_power_level"),
    ("A_WEAPON_DECAY_TIMER", "include/player.h", "A_weapon_decay_timer"),
    ("ENTITY_HEIGHT_MASK", "include/collision.h", "ENTITY_HEIGHT_MASK"),
    ("POWERUP_DECAY_TICKS", "include/player.h", "POWERUP_DECAY_TICKS"),
    ("WEAPON_POWER_LEVEL_MIN", "include/player.h", "WEAPON_POWER_LEVEL_MIN"),
    ("TYPE_TARGETABLE_MAX", "include/collision.h", "TYPE_TARGETABLE_MAX"),
    ("ENTITY_STRIDE", "include/entity.h", "ENTITY_STRIDE"),
    ("ENTITY_X", "include/entity.h", "ENTITY_X"),
    ("ENTITY_Y", "include/entity.h", "ENTITY_Y"),
    ("ENTITY_HEIGHT", "include/entity.h", "ENTITY_HEIGHT"),
    ("ENTITY_SPRITE", "include/entity.h", "ENTITY_SPRITE"),
    ("ENTITY_ALIVE", "include/entity.h", "ENTITY_ALIVE"),
    ("ENTITY_TYPE", "include/entity.h", "ENTITY_TYPE"),
    ("ENTITY_ANIM_FRAME", "include/entity.h", "ENTITY_ANIM_FRAME"),
)
ENTRY_PROLOGUES = {
    "ENTRY_ENTITY_TYPE_IS_LOCKABLE": "102a0011b03c00326d00",
    "ENTRY_POWERUP_SLOT1_ACTIVATE": "33fc03e800019dcc4e75",
    "ENTRY_POWERUP_DOWNGRADE_ON_DEATH": "5339000199076a000008",
    "ENTRY_ENTITY_POS_FROM_SHIP": "41f900017da635680000",
    "ENTRY_ENTITY_TYPE_IS_MISSILE_TARGET": "41f90001918e10290011",
    "ENTRY_PLAYER_SHOT_UPDATE_ALL": "45f900017a8e3e3c0005",
    "ENTRY_SHOT_SET_SPRITE_A": "102a001d488041f90001",
    "ENTRY_SHOT_ANIM_PUFF": "4a39000198c566000034",
    "ENTRY_SHOT_RETIRE_KIND32": "4a2a000e6700002a0c2a",
    "ENTRY_SHOT_RETIRE_KIND36": "6100002c043900010001",
    "ENTRY_SHOT_RETIRE_KIND33": "4a2a000e670000180c2a",
    "ENTRY_SHOT_TO_PUFF": "046a00030004157c0037",
    "ENTRY_PLAYER_SHOTS_CLEAR": "45f900017dd2422a000e",
}
