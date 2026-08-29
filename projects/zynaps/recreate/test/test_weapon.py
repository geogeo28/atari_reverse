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
ENTRY_FIRE_SEEKER = 0x13f9e
ENTRY_FIRE_HOMING_MISSILE = 0x1401a
ENTRY_SEEKER_UPDATE = 0x140a6
ENTRY_HOMING_MISSILE_UPDATE = 0x14126
ENTRY_ENTITY_STEER_TOWARD_TARGET = 0x141d6
ENTRY_FIRE_BOMB = 0x14324
ENTRY_BOMB_UPDATE = 0x14376

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
A_SEEKER_LOCK_TARGET_INDEX = 0x19917
A_MISSILE_LAUNCH_COUNTER = 0x198b5
A_BOMB_LAUNCH_COUNTER = 0x198b6
A_SEEKER_LAUNCH_COUNTER = 0x198b8
SHOT_TARGET_INDEX = 0x1a
SHOT_BOUNCES_LEFT = 0x1a
SHOT_TURN_COUNTDOWN = 0x1b
SHOT_TURN_PERIOD = 0x1c
SHOT_HEADING = 0x1d
SHOT_SPEED = 0x1e
SHOT_MAX_TURN = 0x1f
SHOT_LOCK_SLOT_B = 0x8000
SHOT_ARM_ROWS = 0x0b
SHOT_ARM_MAX_TURN = 2
MISSILE_SPEED = 5
BOMB_ROWS = 8
BOMB_LAUNCH_DX = 0x200
BOMB_GRAVITY_AY = 0x40
BOMB_BOUNCES = 3
BOMB_FLOOR_Y = 0xac
SFX_BOMB_BOUNCE = 0x11
SFX_BOMB_LAUNCH = 0x18
SFX_SEEKER_LAUNCH = 0x1a
ENTITY_INDEX_SHIP = 0x11
ENTITY_INDEX_TRAIL_DRONE = 0x13
TYPE_TRAIL_DRONE = 0x35
MISSILE_NO_TARGET = 0x14
MISSILE_SCAN_FIRST = 0x08
MISSILE_SCAN_END = 0x11
# --- mirrors of include/sound.h: what `sound_start` reads to pick a voice ---
A_TUNE_INDEX = 0x17058
A_TUNE_DATA = 0x171e8
A_SFX_VOICE_TOGGLE = 0x16e90
SOUND_STREAM_CHANNEL_TAG = 0xfa
# --- mirrors of include/collision.h: the other half of the same record field ---
ENTITY_HEIGHT_MASK = 0x7fff
# ...and the overlap table `bomb_update` resolves its own row in.
A_ENTITY_COLLISION_MASKS = 0x18252
COLLISION_ROW_BYTES = 4
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
ENTITY_PIXEL_HIT, ENTITY_BOUNCE = 0x0f, 0x1b
ENTITY_DX, ENTITY_DY, ENTITY_AX, ENTITY_AY = 0x12, 0x14, 0x16, 0x18

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
        ("g_player_shots_clear", []),
        ("g_entity_steer_toward_target", [ctypes.c_uint32]),
        ("g_fire_seeker", [ctypes.c_uint32] * 3),
        ("g_fire_homing_missile", [ctypes.c_uint32]),
        ("g_fire_bomb", [ctypes.c_uint32] * 2),
        ("g_seeker_update", [ctypes.c_uint32]),
        ("g_homing_missile_update", [ctypes.c_uint32]),
        ("g_bomb_update", [ctypes.c_uint32] * 2)):
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


# ================================================================================================
# Steering, launching and the three per-frame projectile updates.
#
# All seven take their record through a register and write only the image, so they are driven at
# their own entries over the WHOLE poked entity table — which is what makes a wrong record stride,
# a wrong slot or a stray write outside the record visible. The weapon state they share (the launch
# counters, the two lock bytes, the gunsight's lock) is poked as one block per case, with a guard
# byte in the gap so an off-by-one store shows up as a diff rather than as a coincidence.
# ================================================================================================
STEER_SLOT = 0                  # the shot under test, unless a case says otherwise
DEFAULT_TARGET_SLOT = 9         # the first wave-enemy slot — what a missile's scan finds first
GUARD = 0xa5


def _slot_addr(index):
    return A_ENTITY_TABLE + index * ENTITY_STRIDE


def _at_slot(slots, slot):
    """The same slot map with the shot under test moved from STEER_SLOT to `slot`.

    For the per-slot sweeps: these routines take their record as a POINTER, so a case at one slot
    says nothing about the others, and a wrong stride or a wrong table base lands on a neighbour.
    """
    moved = dict(slots)
    moved[slot] = moved.pop(STEER_SLOT)
    return moved


def _weapon_pokes(lock_target=0, lock_a=0, lock_b=0, toggle=None):
    """The weapon-wide bytes a launch or an update reads and writes.

    The two pokes are laid out to catch a neighbour: `A_MISSILE_LAUNCH_COUNTER` covers the bomb and
    seeker counters either side of `free_wave_slot_count` (0x198b7, the enemy subsystem's — a guard
    here, never a target), and the lock poke covers `lives_remaining` (0x1991a) one past the pair.
    """
    pokes = {A_MISSILE_LAUNCH_COUNTER: bytes([0x51, 0x52, GUARD, 0x53]),
             A_SEEKER_LOCK_TARGET_INDEX: bytes([lock_target, lock_a, lock_b, GUARD])}
    if toggle is not None:
        pokes[A_SFX_VOICE_TOGGLE] = bytes([toggle])
    return pokes


def test_the_weapon_state_block_this_battery_pokes():
    """`_weapon_pokes` writes each block as ONE run of bytes, so its layout is a claim about the
    addresses — a claim no compiler can check and that silently weakens every launch case if it
    drifts. The gap byte between the bomb and seeker counters is `free_wave_slot_count` (the enemy
    subsystem's) and the byte past the lock pair is `lives_remaining`; both are guards here.
    """
    assert A_BOMB_LAUNCH_COUNTER == A_MISSILE_LAUNCH_COUNTER + 1
    assert A_SEEKER_LAUNCH_COUNTER == A_MISSILE_LAUNCH_COUNTER + 3
    assert A_MISSILE_LOCK_A == A_SEEKER_LOCK_TARGET_INDEX + 1
    assert A_MISSILE_LOCK_B == A_SEEKER_LOCK_TARGET_INDEX + 2


def _projectile_case(entry, glue_name, register, slots, slot=STEER_SLOT, args=(), regs=None,
                     extra=None, poison=False, note=""):
    """Run one routine that takes an entity record in `register`, over the seeded table."""
    record = _slot_addr(slot)
    pokes = _table_pokes(slots)
    pokes.update(_weapon_pokes())
    pokes.update(extra or {})
    run_regs = {register: record, "_pokes": pokes}
    run_regs.update(regs or {})
    diffs, _ = differential(
        entry, run_regs,
        lambda lib, buf: getattr(lib, glue_name)(buf, record, *args), poison=poison)
    assert not diffs, f"{note}\n{report(diffs)}"


# ------------------------------------------------------------------------------------------------
# entity_steer_toward_target @ 0x141d6
# ------------------------------------------------------------------------------------------------
SHOT_POSITION = {"l00": 0x00800000, "l04": 0x00400000}   # x/y as the 8-bit-fraction fixed point


def _merge_slot(slots, index, fields):
    """Add `fields` under `index` WITHOUT discarding what is already there; existing keys win.

    `slots[index] = fields` was the bug: a case that aimed the shot at its OWN slot replaced the
    whole steering block with three position keys, so the countdown reverted to `_record` noise, the
    turn never came due, and every such case silently became a duplicate of the countdown-only arm.
    Existing keys win because the caller that named a field meant it — a shot aimed at itself keeps
    its own position and its own alive byte, which is exactly what that state is.
    """
    merged = dict(fields)
    merged.update(slots.get(index, {}))
    slots[index] = merged


def _steer_slots(heading, countdown=1, period=3, speed=4, max_turn=2, target=DEFAULT_TARGET_SLOT,
                 target_x=0x00c00000, target_y=0x00400000, target_alive=1, shot=None):
    """The shot under test plus the record it is aimed at, as a `_table_pokes` slot map."""
    fields = dict(SHOT_POSITION, b1a=target, b1b=countdown, b1c=period, b1d=heading, b1e=speed,
                  b1f=max_turn, b0e=1, b11=SHOT_TYPE_SEEKER)
    fields.update(shot or {})
    slots = {STEER_SLOT: fields}
    if target < ENTITY_SLOTS:
        _merge_slot(slots, target, {"l00": target_x, "l04": target_y, "b0e": target_alive})
    return slots


def _steer_case(slots, poison=False, note=""):
    _projectile_case(ENTRY_ENTITY_STEER_TOWARD_TARGET, "g_entity_steer_toward_target", "a2",
                     slots, poison=poison, note=note)


@pytest.mark.parametrize("countdown", (2, 3, 0x80, 0xff, 0x00))
def test_steer_only_moves_while_the_turn_countdown_runs(countdown):
    """A countdown that does not reach zero skips the whole steering block and only integrates.

    Driven with a heading and a target that WOULD turn, so a reconstruction that steered anyway
    diverges — and with 0, which `subi.b` wraps to 0xff rather than treating as expired.
    """
    _steer_case(_steer_slots(heading=0x10, countdown=countdown), note=f"countdown={countdown:#04x}")


@pytest.mark.parametrize("period", (0, 1, 4, 0x80, 0xff))
def test_steer_reloads_the_countdown_from_its_period(period):
    """On the frame it expires the countdown is reloaded from SHOT_TURN_PERIOD, whatever that is —
    including 0, which arms a wrap on the next call rather than a permanent stall."""
    _steer_case(_steer_slots(heading=0, period=period), note=f"period={period:#04x}")


STEER_CHUNKS = 4


@pytest.mark.parametrize("chunk", range(STEER_CHUNKS))
def test_steer_from_every_heading_byte(chunk):
    """All 256 heading bytes against one fixed target, sharded four ways.

    The game only ever holds 0..0x3f there, but every step of the turn is a BYTE operation — the
    difference is a signed byte, its magnitude a `neg.b`, and the two turn arms wrap with `and.b
    #$3f` — so the full range is what pins the signedness. A heading of 0x80 makes the difference
    read negative for targets a masked reading would call positive, and the two spellings part.
    """
    for heading in range(chunk, 0x100, STEER_CHUNKS):
        _steer_case(_steer_slots(heading=heading), note=f"heading={heading:#04x}")


@pytest.mark.parametrize("max_turn", (0, 1, 2, 0x1f, 0x20, 0x7f, 0x80, 0xff))
@pytest.mark.parametrize("heading", (0, 0x08, 0x20, 0x30))
def test_steer_turn_limit_is_a_signed_byte(max_turn, heading):
    """`cmp.b d2,d0` + `bge` is SIGNED, so a max-turn of 0x80 or 0xff is NEGATIVE and every
    difference clears it — the shot then always steps by that byte instead of snapping to the
    target. A max-turn of 0 has the same shape from the other side: nothing is ever within it."""
    _steer_case(_steer_slots(heading=heading, max_turn=max_turn),
                note=f"max_turn={max_turn:#04x} heading={heading:#04x}")


@pytest.mark.parametrize("target_x,target_y", ((0x00800000, 0x00400000),   # exactly on top
                                               (0x00c00000, 0x00400000),   # due east
                                               (0x00400000, 0x00400000),   # due west
                                               (0x00800000, 0x00800000),   # due south
                                               (0x00800000, 0x00100000),   # due north
                                               (0x00c00000, 0x00800000),   # each diagonal
                                               (0x00400000, 0x00800000),
                                               (0x00c00000, 0x00100000),
                                               (0x00400000, 0x00100000)))
def test_steer_towards_a_target_in_every_octant(target_x, target_y):
    """One target per compass point, each from four headings — which is what pins WHICH WAY the
    turn goes. `(-difference) & 0x3f >= 0x20` is the only thing choosing between +max and -max, and
    a target on the far side of the circle is exactly where the two answers separate."""
    for heading in (0, 0x0f, 0x20, 0x3a):
        _steer_case(_steer_slots(heading=heading, target_x=target_x, target_y=target_y),
                    note=f"heading={heading:#04x} target=({target_x:#x},{target_y:#x})")


def test_steer_leaves_the_velocity_alone_when_already_on_heading():
    """A difference of zero branches straight to the position step — the velocity pair keeps
    whatever the last turn left in it rather than being re-derived from the same angle.

    The shot's velocity words are noise, so a reconstruction that recomputed them would overwrite
    that noise with the table's own answer and diverge.

    HEADING 0 IS THE ONE THAT REACHES THIS ARM, in both shapes below: `angle_to_target` answers 0
    for a target on the same cell as the asker (every octant flag clear, the slope search exhausted)
    and 0 for one due east of it, so a shot already holding heading 0 has a difference of zero.
    Before this was written explicitly the arm was reached only incidentally, by the one heading in
    256 that happened to match in `test_steer_from_every_heading_byte`.
    """
    shot_x, shot_y = SHOT_POSITION["l00"], SHOT_POSITION["l04"]

    _steer_case(_steer_slots(heading=0, target=STEER_SLOT), note="aimed at its own slot")
    _steer_case(_steer_slots(heading=0, target_x=shot_x + 0x00400000, target_y=shot_y),
                note="aimed due east")


@pytest.mark.parametrize("heading", (0x01, 0x10, 0x20, 0x30, 0x3f))
def test_steer_at_its_own_slot_from_a_heading_that_must_turn(heading):
    """The same self-target with a heading that is NOT the answer, so the turn runs on a degenerate
    angle — the case the clobbered slot map used to swallow (see `_merge_slot`)."""
    _steer_case(_steer_slots(heading=heading, target=STEER_SLOT),
                note=f"aimed at its own slot, heading={heading:#04x}")


@pytest.mark.parametrize("target", (0, 1, 9, 0x13, ENTITY_SLOTS - 1, ENTITY_SLOTS, 0x50, 0x7f,
                                    0x80, 0xff))
def test_steer_resolves_the_target_index_as_a_byte(target):
    """The target record is `entity_table + (index & 0xff) * 0x2c`, so every one of the 256 indices
    resolves — the ones past the table onto ordinary bss, which reads as a record of zeroes.

    Indices 0x14..0xff are what pin the stride: a wrong multiplier lands on a different record for
    every one of them, and the angle it computes from that record's position differs.
    """
    _steer_case(_steer_slots(heading=5, target=target), note=f"target={target:#04x}")


@pytest.mark.parametrize("speed", (0, 1, 4, 0x7f, 0x80, 0xff))
def test_steer_speed_is_sign_extended(speed):
    """SHOT_SPEED reaches `entity_set_velocity_from_angle` through `ext.w d1`, so 0x80..0xff are
    NEGATIVE speeds and the shot flies backwards along its heading."""
    _steer_case(_steer_slots(heading=0x11, speed=speed), note=f"speed={speed:#04x}")


def test_steer_attribution():
    """Poison the turning arm, the already-on-heading arm and the countdown-only arm."""
    shot_x, shot_y = SHOT_POSITION["l00"], SHOT_POSITION["l04"]

    _steer_case(_steer_slots(heading=0x30), poison=True)
    _steer_case(_steer_slots(heading=0, target_x=shot_x + 0x00400000, target_y=shot_y),
                poison=True)
    _steer_case(_steer_slots(heading=0x30, countdown=4), poison=True)


# ------------------------------------------------------------------------------------------------
# The three launchers.
# ------------------------------------------------------------------------------------------------
def test_every_launch_sound_names_its_own_channel():
    """D0 reaches `sound_start` as the channel a stream without a header would be armed on — and
    all three shipped streams DO carry one, so D0 cannot pick the voice.

    Asserted off the image rather than assumed, because it is the whole reason the batteries below
    can drive one D0 and call the launch verified: `sound_start` overwrites the channel from the
    stream's 0xfa header before it selects a voice record (src/sound.c).
    """
    for number in (SFX_SEEKER_LAUNCH, SFX_BOMB_LAUNCH, SFX_BOMB_BOUNCE):
        offset = int.from_bytes(bytes(harness.BASE_IMAGE[A_TUNE_INDEX + number * 2:][:2]), "little")
        stream = (A_TUNE_DATA + (offset - 0x10000 if offset & 0x8000 else offset)) & 0xffffffff
        assert harness.BASE_IMAGE[stream] == SOUND_STREAM_CHANNEL_TAG, (
            f"sfx {number:#x} no longer opens with the 0xfa channel header — D0 now reaches the "
            f"voice selection and every launch case has to drive it")


LAUNCH_SLOT_NOISE = {"b0e": 0, "b11": 0x77, "w08": 0x1234, "l0a": 0xdeadbeef, "b1a": 0x99,
                     "b1b": 0x88, "b1c": 0x66, "b1d": 0x55, "b1e": 0x44, "b1f": 0x33, "b20": 0x22}
SHIP_SHADOW_POSITION = {"w00": 0x0140, "w04": 0x0060}


def _launch_slots(shot_fields=None):
    """A free slot pre-loaded with values every launch store must overwrite, plus the ship shadow
    the spawn position is copied from (slot 18 — see the record-layout test at the top)."""
    fields = dict(LAUNCH_SLOT_NOISE)
    fields.update(shot_fields or {})
    return {STEER_SLOT: fields, 18: dict(SHIP_SHADOW_POSITION)}


def _launch_case(entry, glue_name, slots, args=(), regs=None, lock=None, toggle=None,
                 poison=False, note=""):
    """One launcher, at the shot slot, with the weapon-state block a case names.

    A thin wrapper over `_projectile_case` rather than a second copy of it: `extra` replaces the
    default `_weapon_pokes()` under the same two keys, so any hardening added to the shared runner
    reaches the launch cases too.
    """
    _projectile_case(entry, glue_name, "a3", slots, args=args, regs=regs,
                     extra=_weapon_pokes(**(lock or {}), toggle=toggle),
                     poison=poison, note=note)


@pytest.mark.parametrize("lock_target", (0, 1, 9, 0x13, 0x7f, 0x80, 0xff))
@pytest.mark.parametrize("fallback", (0, 0x0d, 0xff))
def test_fire_seeker_target_and_sound_follow_the_gunsight_lock(lock_target, fallback):
    """The lock decides BOTH the seeker's target and whether the launch makes a sound.

    With `A_seeker_lock_target_index` clear the routine keeps D6 — its caller's own byte — and never
    reaches `sound_start`, so nothing in the voice records moves. With it set, the lock byte becomes
    the target and sfx 0x1a is armed. Both bytes are driven independently, which is what separates
    "copies the lock" from "copies D6" on the case where they happen to agree.
    """
    _launch_case(ENTRY_FIRE_SEEKER, "g_fire_seeker", _launch_slots(),
                 args=(fallback, 0), regs={"d6": fallback, "d0": 0},
                 lock={"lock_target": lock_target},
                 note=f"lock={lock_target:#04x} d6={fallback:#04x}")


@pytest.mark.parametrize("fallback_reg", (0x00000000, 0xffffff00, 0x000000ff, 0x123456ff,
                                          0x12345678))
def test_fire_seeker_keeps_only_d6s_low_byte(fallback_reg):
    """`move.b d6,26(a2)` stores a byte: the register's high three are never read.

    Two PAIRS share a low byte (0x00 and 0xff) with different upper halves, which is what makes
    "only the low byte survives" observable rather than assumed. The WHOLE register goes to the glue
    as well as to the oracle, so `g_fire_seeker`'s own `(uint8_t)` narrowing is exercised — handing
    it a pre-masked byte would have left that cast untested on both sides.
    """
    _launch_case(ENTRY_FIRE_SEEKER, "g_fire_seeker", _launch_slots(),
                 args=(fallback_reg, 0), regs={"d6": fallback_reg, "d0": 0},
                 note=f"d6={fallback_reg:#010x}")


@pytest.mark.parametrize("channel", (1, 0xff))
@pytest.mark.parametrize("toggle", (0, 1, 2, 3))
def test_fire_seeker_sound_ignores_d0_and_alternates_on_the_toggle(channel, toggle):
    """Which voice sfx 0x1a lands on comes from the stream's own header (code 4 = "alternate") and
    the toggle byte it flips — never from D0.

    The toggle axis is swept and the channel axis is not, deliberately: the header claim above
    (`test_every_launch_sound_names_its_own_channel`) is what says D0 cannot reach the selection, so
    a wider channel grid would repeat the toggle axis rather than add a case. Two values, one a
    voice code the driver names and one it does not, are what a reader needs to see it driven.
    """
    _launch_case(ENTRY_FIRE_SEEKER, "g_fire_seeker", _launch_slots(),
                 args=(7, channel), regs={"d6": 7, "d0": channel},
                 lock={"lock_target": 9}, toggle=toggle,
                 note=f"d0={channel:#04x} toggle={toggle}")


@pytest.mark.parametrize("alive", (0, 1, 0x80, 0xff))
def test_fire_seeker_has_no_alive_guard(alive):
    """Unlike the missile and the bomb, the seeker overwrites a slot whoever it belongs to — the
    caller has already chosen a free one. Stated by driving the same grid its neighbours refuse."""
    _launch_case(ENTRY_FIRE_SEEKER, "g_fire_seeker", _launch_slots({"b0e": alive}),
                 args=(9, 0), regs={"d6": 9, "d0": 0}, lock={"lock_target": 9},
                 note=f"alive={alive:#04x}")


@pytest.mark.parametrize("alive", (0, 1, 0x80, 0xff))
@pytest.mark.parametrize("lock_a", (0, 1, 0xff))
def test_fire_homing_missile(alive, lock_a):
    """The alive guard, and which of the two lock slots the new missile claims.

    A non-zero `A_missile_lock_a` means the other missile already owns slot A, so this one sets
    ENTITY_HEIGHT's bit 15 — over a row count the same instruction has just stored, which is why
    the height is checked as a whole word rather than as a flag.
    """
    _launch_case(ENTRY_FIRE_HOMING_MISSILE, "g_fire_homing_missile",
                 _launch_slots({"b0e": alive}), lock={"lock_a": lock_a},
                 note=f"alive={alive:#04x} lock_a={lock_a:#04x}")


@pytest.mark.parametrize("alive", (0, 1, 0x80, 0xff))
@pytest.mark.parametrize("channel", (0, 3))
def test_fire_bomb(alive, channel):
    """The alive guard, and the eight fields a launch writes over the slot's previous contents."""
    _launch_case(ENTRY_FIRE_BOMB, "g_fire_bomb", _launch_slots({"b0e": alive}),
                 args=(channel,), regs={"d0": channel},
                 note=f"alive={alive:#04x} d0={channel}")


@pytest.mark.parametrize("shadow_x,shadow_y", ((0, 0), (0xffff, 0xffff), (0x8000, 0x7fff)))
def test_every_launch_spawns_at_the_ship_shadow(shadow_x, shadow_y):
    """All three launches copy the shadow record's x/y in — and the bomb does it LAST, as a tail
    call, after it has already written its velocity pair."""
    slots = _launch_slots()
    slots[18] = {"w00": shadow_x, "w04": shadow_y}
    note = f"shadow=({shadow_x:#06x},{shadow_y:#06x})"
    _launch_case(ENTRY_FIRE_SEEKER, "g_fire_seeker", slots, args=(9, 0),
                 regs={"d6": 9, "d0": 0}, note=note)
    _launch_case(ENTRY_FIRE_HOMING_MISSILE, "g_fire_homing_missile", slots, note=note)
    _launch_case(ENTRY_FIRE_BOMB, "g_fire_bomb", slots, args=(0,), note=note)


def test_launch_attribution():
    """Poison each launcher's whole write set, on an arm that actually launches."""
    _launch_case(ENTRY_FIRE_SEEKER, "g_fire_seeker", _launch_slots(), args=(9, 0),
                 regs={"d6": 9, "d0": 0}, lock={"lock_target": 9}, poison=True)
    _launch_case(ENTRY_FIRE_HOMING_MISSILE, "g_fire_homing_missile", _launch_slots(),
                 lock={"lock_a": 1}, poison=True)
    _launch_case(ENTRY_FIRE_BOMB, "g_fire_bomb", _launch_slots(), args=(0,), poison=True)


# ------------------------------------------------------------------------------------------------
# seeker_update @ 0x140a6
# ------------------------------------------------------------------------------------------------
def _seeker_slots(target=DEFAULT_TARGET_SLOT, target_alive=1, time_to_live=0x20,
                  gunsight_alive=1, gunsight_type=TYPE_TRAIL_DRONE):
    slots = _steer_slots(heading=0x08, target=target, target_alive=target_alive,
                         shot={"b20": time_to_live})
    # Merged, not assigned: when a case aims the seeker AT the drone's own slot, `_steer_slots` has
    # already written that slot's alive byte from `target_alive`, and that is the value the case
    # asked for — the gunsight arguments describe the slot only when it is not also the target.
    _merge_slot(slots, ENTITY_INDEX_TRAIL_DRONE,
                {"b0e": gunsight_alive, "b11": gunsight_type,
                 "l00": 0x00300000, "l04": 0x00700000})
    return slots


@pytest.mark.parametrize("gunsight_alive", (0, 1, 0xff))
@pytest.mark.parametrize("gunsight_type", (TYPE_TRAIL_DRONE, SHOT_TYPE_SEEKER, 0x00))
def test_seeker_retargets_at_the_drone_or_the_ship(gunsight_alive, gunsight_type):
    """A dead target sends the seeker at the drone when slot 19 holds a LIVE one of type 0x35, and
    at the ship otherwise — the two conditions driven independently, so "alive" and "is a drone"
    cannot stand in for each other."""
    _projectile_case(ENTRY_SEEKER_UPDATE, "g_seeker_update", "a3",
                     _seeker_slots(target_alive=0, gunsight_alive=gunsight_alive,
                                   gunsight_type=gunsight_type),
                     note=f"gunsight alive={gunsight_alive:#04x} type={gunsight_type:#04x}")


@pytest.mark.parametrize("target", (0, 9, 0x13, ENTITY_SLOTS, 0xff))
def test_seeker_keeps_a_live_target(target):
    """A target that is still alive is left alone — including the drone's own slot and an index
    past the table, whose zeroed record always reads as dead and so always retargets."""
    _projectile_case(ENTRY_SEEKER_UPDATE, "g_seeker_update", "a3",
                     _seeker_slots(target=target), note=f"target={target:#04x}")


@pytest.mark.parametrize("time_to_live", (0, 1, 2, 6, 0x80, 0xff))
def test_seeker_time_to_live(time_to_live):
    """`subi.b #$1,32(a2)` + `beq`: only the frame it reaches EXACTLY zero retires the seeker, so a
    TTL of 0 wraps to 0xff and flies on. Retiring goes through the already-verified
    `shot_retire_kind36`, which turns the record into a puff and steps the seeker count down."""
    _projectile_case(ENTRY_SEEKER_UPDATE, "g_seeker_update", "a3",
                     _seeker_slots(time_to_live=time_to_live),
                     note=f"ttl={time_to_live:#04x}")


@pytest.mark.parametrize("slot", range(PLAYER_SHOT_SLOTS))
def test_seeker_update_at_every_shot_slot(slot):
    """The routine takes its record as a pointer, so a case at one slot says nothing about the
    others; every slot is driven, and the rest of the table must come back untouched."""
    _projectile_case(ENTRY_SEEKER_UPDATE, "g_seeker_update", "a3", _at_slot(_seeker_slots(), slot),
                     slot=slot, note=f"slot={slot}")


def test_seeker_update_attribution():
    _projectile_case(ENTRY_SEEKER_UPDATE, "g_seeker_update", "a3",
                     _seeker_slots(target_alive=0), poison=True)
    _projectile_case(ENTRY_SEEKER_UPDATE, "g_seeker_update", "a3",
                     _seeker_slots(time_to_live=1), poison=True)


# ------------------------------------------------------------------------------------------------
# homing_missile_update @ 0x14126
# ------------------------------------------------------------------------------------------------
# The two types the shipped 0x1918e table lists that a wave-enemy slot can plausibly hold, and one
# it does not — read back through `_class_bit` so the case ages with the data.
MISSILE_TARGET_TYPE = 0x01
MISSILE_INERT_TYPE = 0x20


def _missile_slots(target=MISSILE_NO_TARGET, time_to_live=0x20, lock_slot_b=False,
                   enemies=None):
    """The missile plus whichever wave-enemy slots (9..16) a case wants populated."""
    height = SHOT_ARM_ROWS | (SHOT_LOCK_SLOT_B if lock_slot_b else 0)
    slots = {STEER_SLOT: dict(SHOT_POSITION, b0e=1, b11=SHOT_TYPE_MISSILE, w08=height,
                              b1a=target, b1b=1, b1c=3, b1d=0x08, b1e=MISSILE_SPEED,
                              b1f=SHOT_ARM_MAX_TURN, b20=time_to_live)}
    for index, (alive, type_byte) in (enemies or {}).items():
        slots[index] = {"b0e": alive, "b11": type_byte, "l00": 0x00a00000 + index * 0x10000,
                        "l04": 0x00300000}
    return slots


def _missile_case(slots, lock=None, poison=False, note=""):
    _projectile_case(ENTRY_HOMING_MISSILE_UPDATE, "g_homing_missile_update", "a3", slots,
                     extra=_weapon_pokes(**(lock or {})), poison=poison, note=note)


def test_the_missile_target_types_this_battery_uses():
    """One type the shipped 0x1918e table lists and one it does not — asserted, because every
    acquire case below turns on the answer and the table is the game's, not the case's."""
    assert _class_bit(A_TYPE_MASK_MISSILE_TARGET, MISSILE_TARGET_TYPE)
    assert not _class_bit(A_TYPE_MASK_MISSILE_TARGET, MISSILE_INERT_TYPE)


@pytest.mark.parametrize("lock_slot_b", (False, True))
def test_missile_acquires_the_first_lockable_enemy(lock_slot_b):
    """The scan runs slots 9..16 and takes the first live, listed one — writing its index into the
    lock slot ENTITY_HEIGHT's bit 15 names, which is the only difference the two arms have."""
    slots = _missile_slots(lock_slot_b=lock_slot_b,
                           enemies={9: (0, MISSILE_TARGET_TYPE),
                                    10: (1, MISSILE_INERT_TYPE),
                                    11: (1, MISSILE_TARGET_TYPE),
                                    12: (1, MISSILE_TARGET_TYPE)})
    _missile_case(slots, note=f"lock_slot_b={lock_slot_b}")


@pytest.mark.parametrize("held", (9, 10, 11, 0x10))
def test_missile_refuses_a_target_the_other_missile_holds(held):
    """The claim test compares the two lock BYTES, so a candidate whose index is already in the
    other slot leaves the pair equal and the scan walks past it — after storing it, which is what
    makes the arm observable at all: the lock byte moves even on the candidate that is refused."""
    slots = _missile_slots(enemies={index: (1, MISSILE_TARGET_TYPE) for index in range(9, 0x11)})
    _missile_case(slots, lock={"lock_b": held}, note=f"other missile holds {held:#04x}")


def test_missile_gives_up_when_nothing_is_lockable():
    """A scan that reaches the ship's own slot parks MISSILE_NO_TARGET in the record AND the lock."""
    for enemies in ({}, {index: (1, MISSILE_INERT_TYPE) for index in range(9, 0x11)},
                    {index: (0, MISSILE_TARGET_TYPE) for index in range(9, 0x11)}):
        _missile_case(_missile_slots(enemies=enemies), lock={"lock_a": 0x0c},
                      note=f"{len(enemies)} enemy slots seeded")


@pytest.mark.parametrize("target", (0, 8, 9, 0x10, MISSILE_NO_TARGET, 0x15, 0x7f, 0x80, 0xff))
def test_missile_scan_resumes_from_its_current_target(target):
    """The scan starts at the CURRENT target index, not at the first slot — except from
    MISSILE_NO_TARGET, which restarts it at MISSILE_SCAN_FIRST.

    The counter is a byte, so an index above the enemy slots walks up through 0xff, wraps, and only
    then reaches MISSILE_SCAN_END — a long walk with the same answer, and the case that says the
    loop terminates rather than spinning.
    """
    slots = _missile_slots(target=target,
                           enemies={index: (1, MISSILE_TARGET_TYPE) for index in range(9, 0x11)})
    slots[STEER_SLOT]["b0e"] = 1
    _missile_case(slots, note=f"target={target:#04x}")


@pytest.mark.parametrize("alive", (0, 1))
@pytest.mark.parametrize("type_byte", (MISSILE_TARGET_TYPE, MISSILE_INERT_TYPE))
def test_missile_keeps_a_valid_target_and_re_acquires_otherwise(alive, type_byte):
    """A target is kept only while it is BOTH alive and listed; either failing runs the scan."""
    slots = _missile_slots(target=11, enemies={11: (alive, type_byte),
                                               12: (1, MISSILE_TARGET_TYPE)})
    _missile_case(slots, note=f"target 11 alive={alive} type={type_byte:#04x}")


@pytest.mark.parametrize("time_to_live", (0, 1, 2, 0x80, 0xff))
@pytest.mark.parametrize("lock_slot_b", (False, True))
def test_missile_time_to_live_releases_its_own_lock(time_to_live, lock_slot_b):
    """Retiring goes through `shot_retire_kind32`, which frees the lock slot the height's bit 15
    names — so both lock bytes are poked to distinct markers and the wrong one shows."""
    slots = _missile_slots(target=11, time_to_live=time_to_live, lock_slot_b=lock_slot_b,
                           enemies={11: (1, MISSILE_TARGET_TYPE)})
    _missile_case(slots, lock={"lock_a": 0x77, "lock_b": 0x88},
                  note=f"ttl={time_to_live:#04x} lock_slot_b={lock_slot_b}")


def test_missile_update_attribution():
    _missile_case(_missile_slots(enemies={11: (1, MISSILE_TARGET_TYPE)}), poison=True)
    _missile_case(_missile_slots(target=11, time_to_live=1,
                                 enemies={11: (1, MISSILE_TARGET_TYPE)}), poison=True)


# ------------------------------------------------------------------------------------------------
# bomb_update @ 0x14376
# ------------------------------------------------------------------------------------------------
COLLISION_ROWS = 21             # the table's full height, so a wrong row index lands in it


def _collision_rows(marked=()):
    """The whole overlap table, all rows clear except the ones a case names.

    Built by `abi.indexed_table`, which is shared with `test_collision.py` because the slice
    assignment this needs has been written wrong twice in this project — see its docstring.
    """
    return {A_ENTITY_COLLISION_MASKS: abi.indexed_table(COLLISION_ROWS, COLLISION_ROW_BYTES,
                                                        dict(marked))}


# ENTITY_AX IS SEEDED NON-ZERO, and it is the one field here a launched bomb never holds — fire_bomb
# clears it. Without it the accel mask is half untested: `entity_apply_accel` on the X axis with a
# zero ENTITY_AX stores ENTITY_DX back unchanged, so widening the mask from bit 5 alone to bits 3+5
# or 4+5 (claiming the bomb also accelerates horizontally, which `move.b #$20,d1` does not) writes a
# byte-identical image and the differential cannot see it. `bomb_update` takes the record as given,
# so a record with a live AX is a legitimate input to its contract even though the launcher's is 0.
BOMB_SEEDED_AX = 0x0180


def _bomb_slots(alive=1, pixel_hit=1, bounces=BOMB_BOUNCES, latched=0, dy=0x0100, y=0x00300000):
    return {STEER_SLOT: {"l00": 0x00800000, "l04": y, "b0e": alive, "b11": SHOT_TYPE_BOMB,
                         "b0f": pixel_hit, "b1a": bounces, "b1b": latched,
                         "w12": BOMB_LAUNCH_DX, "w14": dy, "w16": BOMB_SEEDED_AX,
                         "w18": BOMB_GRAVITY_AY, "w08": BOMB_ROWS}}


def _bomb_case(slots, marked=(), slot=STEER_SLOT, channel=0, poison=False, note=""):
    _projectile_case(ENTRY_BOMB_UPDATE, "g_bomb_update", "a3", slots, slot=slot,
                     args=(channel,), regs={"d0": channel}, extra=_collision_rows(marked),
                     poison=poison, note=note)


@pytest.mark.parametrize("alive", (0, 1, 0x80, 0xff))
def test_bomb_alive_guard(alive):
    """A dead slot returns before anything — including before the row pointer it has already
    computed is used, which is what makes the guard observable rather than harmless."""
    _bomb_case(_bomb_slots(alive=alive), note=f"alive={alive:#04x}")


@pytest.mark.parametrize("pixel_hit", (0, 1, 0x80, 0xff))
@pytest.mark.parametrize("row_bits", (0, 1, 0x80000000, 0xffffffff))
def test_bomb_bounces_only_off_the_landscape(pixel_hit, row_bits):
    """A pixel hit is the landscape only when the bomb's own overlap row is EMPTY: any other entity
    under it explains the hit instead, and the bomb falls through untouched with its latch cleared.

    Both halves are driven together, so neither can stand in for the other.
    """
    _bomb_case(_bomb_slots(pixel_hit=pixel_hit), marked=((STEER_SLOT, row_bits),),
               note=f"pixel_hit={pixel_hit:#04x} row={row_bits:#010x}")


@pytest.mark.parametrize("slot", range(PLAYER_SHOT_SLOTS))
def test_bomb_resolves_its_own_collision_row(slot):
    """The bomb divides its record ADDRESS back into an index to find its row, so every slot is
    driven with ONLY that slot's row marked — a wrong stride or a wrong shift then reads a clear
    row where the case set one, and the bomb bounces when it should not."""
    slots = _at_slot(_bomb_slots(), slot)
    for marked_row in (slot, (slot + 1) % PLAYER_SHOT_SLOTS):
        _bomb_case(slots, marked=((marked_row, 0xffffffff),), slot=slot,
                   note=f"slot={slot} marked row={marked_row}")


@pytest.mark.parametrize("dy", (0, 1, 2, 3, 0x0100, 0x7fff, 0x8000, 0x8001, 0xfffe, 0xffff))
def test_bomb_bounce_halves_and_reverses_the_fall(dy):
    """`neg.w` then `asr.w #1`. The shift is ARITHMETIC, so an upward (negative) result halves
    towards zero and not towards 0xffff; 0x8000 is the value where `neg.w` overflows back onto
    itself and the two readings of the shift part."""
    _bomb_case(_bomb_slots(dy=dy), note=f"dy={dy:#06x}")


@pytest.mark.parametrize("latched", (0, 1, 0x80, 0xff))
@pytest.mark.parametrize("bounces", (0, 1, 2, BOMB_BOUNCES, 0x80, 0xff))
def test_bomb_latch_and_bounce_count(latched, bounces):
    """ENTITY_BOUNCE is a one-frame latch: a bomb ALREADY on the terrain last frame is retired
    instead of bouncing. The count is stepped first either way, so a retiring bomb still spends
    one — and a count of 0 wraps to 0xff rather than retiring on the wrap."""
    _bomb_case(_bomb_slots(latched=latched, bounces=bounces),
               note=f"latched={latched:#04x} bounces={bounces:#04x}")


@pytest.mark.parametrize("y", (0x00000000, (BOMB_FLOOR_Y - 1) << 16, BOMB_FLOOR_Y << 16,
                               (BOMB_FLOOR_Y + 1) << 16, 0x7fff0000, 0x80000000, 0xffff0000))
def test_bomb_floor_is_a_signed_word_compare(y):
    """`cmpi.w #$ac,4(a2)` + `bge` reads the position's HIGH word — after gravity has moved it, so
    the case that retires is decided on the post-step y — and reads it SIGNED, which is why a y past
    the word's sign edge is BELOW the floor rather than far under it."""
    _bomb_case(_bomb_slots(pixel_hit=0, y=y), note=f"y={y:#010x}")


def test_bomb_update_attribution():
    _bomb_case(_bomb_slots(pixel_hit=0), poison=True)
    _bomb_case(_bomb_slots(), poison=True)
    _bomb_case(_bomb_slots(latched=1), poison=True)


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
    ("A_SEEKER_LOCK_TARGET_INDEX", "include/weapon.h", "A_seeker_lock_target_index"),
    ("A_MISSILE_LAUNCH_COUNTER", "include/weapon.h", "A_missile_launch_counter"),
    ("A_BOMB_LAUNCH_COUNTER", "include/weapon.h", "A_bomb_launch_counter"),
    ("A_SEEKER_LAUNCH_COUNTER", "include/weapon.h", "A_seeker_launch_counter"),
    ("SHOT_TARGET_INDEX", "include/weapon.h", "SHOT_TARGET_INDEX"),
    # ...and the SAME python name against entity.h's name for that byte. Two triples on one name is
    # how this file pins two C constants EQUAL — nothing else does: `test_no_constant_is_defined_in_
    # two_files` keys on names, and `test_no_address_has_two_spellings` deliberately exempts record
    # offsets, so without these pairs entity.h's frozen block and weapon.h's union names could drift
    # apart silently and each header's provenance tag would keep claiming the other's coverage.
    ("SHOT_TARGET_INDEX", "include/entity.h", "ENTITY_HP"),
    ("SHOT_BOUNCES_LEFT", "include/weapon.h", "SHOT_BOUNCES_LEFT"),
    ("SHOT_TURN_COUNTDOWN", "include/weapon.h", "SHOT_TURN_COUNTDOWN"),
    ("SHOT_TURN_COUNTDOWN", "include/entity.h", "ENTITY_BOUNCE"),
    ("SHOT_TURN_PERIOD", "include/weapon.h", "SHOT_TURN_PERIOD"),
    ("SHOT_SPEED", "include/weapon.h", "SHOT_SPEED"),
    ("SHOT_MAX_TURN", "include/weapon.h", "SHOT_MAX_TURN"),
    ("SHOT_ARM_ROWS", "include/weapon.h", "SHOT_ARM_ROWS"),
    ("SHOT_ARM_MAX_TURN", "include/weapon.h", "SHOT_ARM_MAX_TURN"),
    ("MISSILE_SPEED", "include/weapon.h", "MISSILE_SPEED"),
    ("BOMB_ROWS", "include/weapon.h", "BOMB_ROWS"),
    ("BOMB_LAUNCH_DX", "include/weapon.h", "BOMB_LAUNCH_DX"),
    ("BOMB_GRAVITY_AY", "include/weapon.h", "BOMB_GRAVITY_AY"),
    ("BOMB_BOUNCES", "include/weapon.h", "BOMB_BOUNCES"),
    ("BOMB_FLOOR_Y", "include/weapon.h", "BOMB_FLOOR_Y"),
    ("SFX_BOMB_BOUNCE", "include/weapon.h", "SFX_BOMB_BOUNCE"),
    ("SFX_BOMB_LAUNCH", "include/weapon.h", "SFX_BOMB_LAUNCH"),
    ("SFX_SEEKER_LAUNCH", "include/weapon.h", "SFX_SEEKER_LAUNCH"),
    ("ENTITY_INDEX_SHIP", "include/weapon.h", "ENTITY_INDEX_SHIP"),
    ("ENTITY_INDEX_TRAIL_DRONE", "include/weapon.h", "ENTITY_INDEX_TRAIL_DRONE"),
    ("TYPE_TRAIL_DRONE", "include/weapon.h", "TYPE_TRAIL_DRONE"),
    ("MISSILE_NO_TARGET", "include/weapon.h", "MISSILE_NO_TARGET"),
    ("MISSILE_SCAN_FIRST", "include/weapon.h", "MISSILE_SCAN_FIRST"),
    ("MISSILE_SCAN_END", "include/weapon.h", "MISSILE_SCAN_END"),
    ("A_ENTITY_COLLISION_MASKS", "include/collision.h", "A_entity_collision_masks"),
    ("COLLISION_ROW_BYTES", "include/collision.h", "COLLISION_ROW_BYTES"),
    ("A_TUNE_INDEX", "include/sound.h", "A_tune_index"),
    ("A_TUNE_DATA", "include/sound.h", "A_tune_data"),
    ("A_SFX_VOICE_TOGGLE", "include/sound.h", "A_sfx_voice_toggle"),
    ("SOUND_STREAM_CHANNEL_TAG", "include/sound.h", "SOUND_STREAM_CHANNEL_TAG"),
    ("ENTITY_PIXEL_HIT", "include/entity.h", "ENTITY_PIXEL_HIT"),
    ("ENTITY_BOUNCE", "include/entity.h", "ENTITY_BOUNCE"),
    ("ENTITY_DX", "include/entity.h", "ENTITY_DX"),
    ("ENTITY_DY", "include/entity.h", "ENTITY_DY"),
    ("ENTITY_AX", "include/entity.h", "ENTITY_AX"),
    ("ENTITY_AY", "include/entity.h", "ENTITY_AY"),
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
    "ENTRY_ENTITY_STEER_TOWARD_TARGET": "042a0001001b66000064",
    "ENTRY_FIRE_SEEKER": "4a390001991767000014",
    "ENTRY_SEEKER_UPDATE": "244b102a001a61000112",
    "ENTRY_HOMING_MISSILE_UPDATE": "244b49f9000199184a6a",
    "ENTRY_BOMB_UPDATE": "244b220b92bc00017a8e",
    # `fire_homing_missile` and `fire_bomb` open with the SAME ten bytes (`movea.l a3,a2` + the
    # alive guard), so these two are pinned sixteen deep — far enough to reach the first store
    # either routine makes, which is where they part.
    "ENTRY_FIRE_HOMING_MISSILE": "244b4a2a000e670000044e756100006a",
    "ENTRY_FIRE_BOMB": "244b4a2a000e670000044e75426a0016",
}
