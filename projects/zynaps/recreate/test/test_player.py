"""Differential tests for the ship's vertical movers in src/player.c."""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, report

ENTRY_SHIP_MOVE_UP = 0x11318
ENTRY_SHIP_MOVE_DOWN = 0x1135a

# --- mirrors of include/player.h ---
A_SHIP_TILT_COUNTDOWN = 0x198b2
A_SHIP_TILT = 0x198b3
A_SHIP_SPEED_TABLE = 0x19370
SHIP_SPEED_DY_UP = 4
SHIP_SPEED_DY_DOWN = 6
SHIP_MIRROR_Y = 0x30
SHIP_Y_MIN = 0x20
SHIP_Y_MAX = 0x9c
SHIP_TILT_PERIOD = 4
SHIP_TILT_MAX = 6
# --- mirrors of include/entity.h ---
ENTITY_STRIDE = 0x2c
ENTITY_Y = 0x04

# The ship occupies two adjacent records, so the case seeds a pair of them.
SHIP_RECORD_BYTES = 2 * ENTITY_STRIDE
# Where a case parks a speed entry of its own, clear of the record pair below abi.SCRATCH.
CUSTOM_SPEED_ENTRY = abi.SCRATCH + 0x100
# The speed table's entries are eight bytes and the game reaches exactly two of them: ship_speed_level
# is stepped up by 0x13d9e and clamped to 1, and down by powerup_downgrade_on_death and floored at 0.
SHIP_SPEED_ENTRY_BYTES = 8
SHIP_SPEED_LEVELS = 2

for _name in ("g_ship_move_up", "g_ship_move_down"):
    getattr(harness._lib, _name).argtypes = [ctypes.POINTER(ctypes.c_uint8),
                                             ctypes.c_uint32, ctypes.c_uint32]
    getattr(harness._lib, _name).restype = None


def _ship_records(y, mirror_y, seed):
    """The ship's record pair, noise everywhere but the two y words the movers touch."""
    raw = bytearray(random.Random(seed).randbytes(SHIP_RECORD_BYTES))
    raw[ENTITY_Y:ENTITY_Y + 2] = (y & 0xffff).to_bytes(2, "big")
    raw[SHIP_MIRROR_Y:SHIP_MIRROR_Y + 2] = (mirror_y & 0xffff).to_bytes(2, "big")
    return bytes(raw)


def _move_case(entry, glue_name, y, mirror_y=None, countdown=SHIP_TILT_PERIOD, tilt=3,
               speed_level=0, speed_entry_bytes=None, poison=False):
    """One call, with the tilt bytes and the speed entry seeded and the record pair at SCRATCH.

    `speed_entry_bytes` parks a caller-supplied entry at CUSTOM_SPEED_ENTRY instead of pointing A6
    into the game's own table — see test_the_two_movers_read_different_words_of_the_speed_entry.
    """
    mirror = y if mirror_y is None else mirror_y
    pokes = {abi.SCRATCH: _ship_records(y, mirror, y ^ tilt),
             # The two tilt bytes are adjacent, plus a guard so a wide write shows up.
             A_SHIP_TILT_COUNTDOWN: bytes([countdown, tilt, 0xa5])}
    if speed_entry_bytes is None:
        speed_entry = A_SHIP_SPEED_TABLE + speed_level * SHIP_SPEED_ENTRY_BYTES
    else:
        speed_entry = CUSTOM_SPEED_ENTRY
        pokes[CUSTOM_SPEED_ENTRY] = speed_entry_bytes
    regs = {"a2": abi.SCRATCH, "a6": speed_entry, "_pokes": pokes}
    diffs, _ = differential(
        entry, regs,
        lambda lib, buf: getattr(lib, glue_name)(buf, abi.SCRATCH, speed_entry), poison=poison)
    assert not diffs, (f"y={y:#x} mirror={mirror:#x} countdown={countdown} tilt={tilt} "
                       f"level={speed_level}\n{report(diffs)}")


def _up(**kwargs):
    _move_case(ENTRY_SHIP_MOVE_UP, "g_ship_move_up", **kwargs)


def _down(**kwargs):
    _move_case(ENTRY_SHIP_MOVE_DOWN, "g_ship_move_down", **kwargs)


def test_the_speed_table_the_game_actually_reaches():
    """Two eight-byte entries, read off the image — the level is clamped to 0..1 by its two writers.

    The full WORDS, not their low bytes: a table whose steps became 0x0102/0x0104 would keep every
    low byte this used to look at and move the ship 258 pixels a frame.

    It also states the fact the test below exists for — both entries hold the SAME word at +4 and
    at +6 — so the two readings the game can reach cannot tell the two offsets apart.
    """
    def step(level, offset):
        entry = A_SHIP_SPEED_TABLE + level * SHIP_SPEED_ENTRY_BYTES + offset
        return int.from_bytes(bytes(harness.BASE_IMAGE[entry:entry + 2]), "big")

    steps = {level: (step(level, SHIP_SPEED_DY_UP), step(level, SHIP_SPEED_DY_DOWN))
             for level in range(SHIP_SPEED_LEVELS)}
    assert steps == {0: (2, 2), 1: (4, 4)}, "the shipped speed table is not what these cases drive"


@pytest.mark.parametrize("y", (SHIP_Y_MIN - 1, SHIP_Y_MIN, SHIP_Y_MIN + 1, SHIP_Y_MIN + 2,
                               0x40, SHIP_Y_MAX, 0x7fff, 0x8000, 0xffff))
@pytest.mark.parametrize("speed_level", range(SHIP_SPEED_LEVELS))
def test_up_clamp(y, speed_level):
    """`cmpi.w #$20` + `ble` is SIGNED and INCLUSIVE: at exactly SHIP_Y_MIN the ship is re-set to it
    rather than stepped, and a y in the negative half of the word clamps rather than wrapping up."""
    _up(y=y, speed_level=speed_level)


@pytest.mark.parametrize("y", (SHIP_Y_MAX - 2, SHIP_Y_MAX - 1, SHIP_Y_MAX, SHIP_Y_MAX + 1,
                               0x40, 0x7fff, 0x8000, 0xffff))
@pytest.mark.parametrize("speed_level", range(SHIP_SPEED_LEVELS))
def test_down_clamp(y, speed_level):
    """`cmpi.w #$9c` + `bge`, the mirror image of the test above."""
    _down(y=y, speed_level=speed_level)


@pytest.mark.parametrize("dy_up,dy_down", ((1, 0x20), (0x20, 1), (0, 0x1234), (0x8000, 3),
                                           (0xffff, 0x7fff)))
def test_the_two_movers_read_different_words_of_the_speed_entry(dy_up, dy_down):
    """`ship_move_up` reads +4 of the entry and `ship_move_down` reads +6 — a real difference.

    THE GAME'S OWN TABLE CANNOT SHOW THIS. Both entries the speed level can select hold the SAME
    word at +4 and +6 (2/2 and 4/4, asserted above), so swapping the two offsets is invisible on
    every speed the game can be in — measured: that mutation survives every other case in this file.

    So the entry here is one the case supplies. That is legitimate rather than fabricated data: A6
    is a POINTER ARGUMENT, exactly like the pointer pairs test_sprite.py drives at offsets the game
    never uses, and what is being explored is the routine's own input, not an invented game record.
    """
    entry = b"\x11\x11\x22\x22" + (dy_up & 0xffff).to_bytes(2, "big") \
        + (dy_down & 0xffff).to_bytes(2, "big")
    _up(y=0x40, speed_entry_bytes=entry)
    _down(y=0x40, speed_entry_bytes=entry)


@pytest.mark.parametrize("mirror_y", (0, 0x20, 0x40, 0x9c, 0xffff))
def test_the_two_records_step_independently(mirror_y):
    """Only the FIRST record's y is compared against the clamp, but BOTH are written.

    So a mirror that has drifted away from the live record steps by the same amount when the clamp
    does not fire, and is snapped to the same literal when it does. Seeding the two differently is
    what makes those two behaviours distinguishable; equal values would hide either.
    """
    _up(y=0x40, mirror_y=mirror_y)
    _up(y=SHIP_Y_MIN, mirror_y=mirror_y)
    _down(y=0x40, mirror_y=mirror_y)
    _down(y=SHIP_Y_MAX, mirror_y=mirror_y)


@pytest.mark.parametrize("countdown", (0, 1, 2, SHIP_TILT_PERIOD, 0x80, 0xff))
@pytest.mark.parametrize("tilt", (0, 1, SHIP_TILT_MAX - 1, SHIP_TILT_MAX, SHIP_TILT_MAX + 1, 0xff))
def test_the_tilt_bank_rolls_one_frame_in_four(countdown, tilt):
    """The countdown is decremented on EVERY call and reloaded only on the call it reaches zero, so
    a countdown of 1 rolls the bank and a countdown of 0 wraps to 0xff and does not.

    The two arms stop differently, and the pair of `tilt` values at SHIP_TILT_MAX and above is what
    says so: `ship_move_up` guards with `tst.b` (stop at 0), while `ship_move_down` guards with
    `cmpi.b #$6` + `beq` — so a bank already PAST 6 keeps climbing instead of being held there.
    """
    _up(y=0x40, countdown=countdown, tilt=tilt)
    _down(y=0x40, countdown=countdown, tilt=tilt)


def test_attribution():
    """Poison every byte either mover writes — both y words and the two tilt bytes."""
    for kwargs in ({"y": 0x40, "countdown": 1, "tilt": 3},
                   {"y": SHIP_Y_MIN, "countdown": 1, "tilt": 0},
                   {"y": 0x40, "countdown": 2, "tilt": 3}):
        _up(poison=True, **kwargs)
    for kwargs in ({"y": 0x40, "countdown": 1, "tilt": 3},
                   {"y": SHIP_Y_MAX, "countdown": 1, "tilt": SHIP_TILT_MAX},
                   {"y": 0x40, "countdown": 2, "tilt": 3}):
        _down(poison=True, **kwargs)


FUZZ_CHUNKS = 4
FUZZ_CASES = 320


def _fuzz_cases():
    rng = random.Random(ENTRY_SHIP_MOVE_UP)          # seeded ONCE; every chunk replays the stream
    for case in range(FUZZ_CASES):
        # Cluster y on the two clamps, where every interesting branch is.
        near = case % 3
        yield (case,
               rng.choice((SHIP_Y_MIN, SHIP_Y_MAX)) + rng.randrange(-4, 5) if near
               else rng.randrange(1 << 16),
               rng.randrange(1 << 16), rng.randrange(0x100), rng.randrange(0x100),
               rng.randrange(SHIP_SPEED_LEVELS))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz(chunk):
    for case, y, mirror_y, countdown, tilt, speed_level in _fuzz_cases():
        if case % FUZZ_CHUNKS == chunk:
            mover = _up if case % 2 else _down
            mover(y=y, mirror_y=mirror_y, countdown=countdown, tilt=tilt, speed_level=speed_level)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_SHIP_TILT_COUNTDOWN", "include/player.h", "A_ship_tilt_countdown"),
    ("A_SHIP_TILT", "include/player.h", "A_ship_tilt"),
    ("A_SHIP_SPEED_TABLE", "include/player.h", "A_ship_speed_table"),
    ("SHIP_SPEED_DY_UP", "include/player.h", "SHIP_SPEED_DY_UP"),
    ("SHIP_SPEED_DY_DOWN", "include/player.h", "SHIP_SPEED_DY_DOWN"),
    ("SHIP_MIRROR_Y", "include/player.h", "SHIP_MIRROR_Y"),
    ("SHIP_Y_MIN", "include/player.h", "SHIP_Y_MIN"),
    ("SHIP_Y_MAX", "include/player.h", "SHIP_Y_MAX"),
    ("SHIP_TILT_PERIOD", "include/player.h", "SHIP_TILT_PERIOD"),
    ("SHIP_TILT_MAX", "include/player.h", "SHIP_TILT_MAX"),
    ("ENTITY_STRIDE", "include/entity.h", "ENTITY_STRIDE"),
    ("ENTITY_Y", "include/entity.h", "ENTITY_Y"),
)
ENTRY_PROLOGUES = {
    "ENTRY_SHIP_MOVE_UP": "5339000198b2661613fc",
    "ENTRY_SHIP_MOVE_DOWN": "5339000198b2661813fc",
}
