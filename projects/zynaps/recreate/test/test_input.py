"""Differential tests for onscreen_keyboard_hit_test @ 0x1326e (src/input.c).

The routine writes no memory — its whole answer is D0 — so the case enters at test/abi.py's
`jsr`+store stub, which parks D0 where the image diff can see it.
"""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, hi_garbage, report

ENTRY_ONSCREEN_KEYBOARD_HIT_TEST = 0x1326e

# --- mirrors of include/input.h ---
A_OSK_CURSOR_X = 0x19d44
A_OSK_CURSOR_Y = 0x19d46
A_OSK_ROW_TOP = 0x132e2
A_OSK_ROW_MIDDLE = 0x132fe
A_OSK_ROW_BOTTOM = 0x1331a
OSK_X_ORIGIN = 0x38
OSK_Y_ORIGIN = 0x20
OSK_ROW_BAND_TOP = 0x60
OSK_ROW_TOP_MAX = 0x70
OSK_ROW_MIDDLE_MAX = 0x80
OSK_ROW_BOTTOM_MAX = 0x90
OSK_COLUMN_FIRST = 0x30
OSK_COLUMN_LAST = 0x110
OSK_COLUMN_SHIFT = 3

# The routine's answers are register-only, so the stub stores D0 where the diff can see it.
_STORES = ("d0",)
# What a key occupies on screen: ten keys per row, three columns apart. Both numbers are read back
# off the shipped tables by test_the_shipped_rows_spell_the_alphabet below rather than assumed.
OSK_KEYS_PER_ROW = 10
OSK_KEY_COLUMN_STRIDE = 3
# A row's table stops at its LAST key rather than after it, so ten keys three columns apart occupy
# 28 bytes and not 30 — which is exactly why OSK_COLUMN_LAST's byte 28 falls into the next row.
OSK_ROW_BYTES = (OSK_KEYS_PER_ROW - 1) * OSK_KEY_COLUMN_STRIDE + 1

harness._lib.g_onscreen_keyboard_hit_test.argtypes = [ctypes.POINTER(ctypes.c_uint8),
                                                      ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_onscreen_keyboard_hit_test.restype = None

SCRATCH_D0 = 0xbeef0000   # the caller's D0, whose HIGH word a hit must hand back untouched


def _case(cursor_x, cursor_y, scratch=SCRATCH_D0, poison=False):
    pokes = abi.register_call_pokes(ENTRY_ONSCREEN_KEYBOARD_HIT_TEST, _STORES)
    # Both cursor words are adjacent; a trailing guard word catches a wide read or write.
    pokes[A_OSK_CURSOR_X] = ((cursor_x & 0xffff) << 16 | (cursor_y & 0xffff)).to_bytes(4, "big")
    pokes[abi.RESULT] = bytes(range(0x61, 0x69))
    regs = {"d0": scratch, "a0": abi.RESULT, "_pokes": pokes}
    diffs, _ = differential(
        abi.STUB, regs,
        lambda lib, buf: lib.g_onscreen_keyboard_hit_test(buf, abi.RESULT, scratch), poison=poison)
    assert not diffs, f"cursor=({cursor_x:#x},{cursor_y:#x}) d0={scratch:#x}\n{report(diffs)}"


def _key_position(row_index, key):
    """Screen coordinates of one key: the inverse of the routine's own arithmetic."""
    band_y = (OSK_ROW_BAND_TOP, OSK_ROW_TOP_MAX + 1, OSK_ROW_MIDDLE_MAX + 1)[row_index]
    column = OSK_COLUMN_FIRST + (key * OSK_KEY_COLUMN_STRIDE << OSK_COLUMN_SHIFT)
    return OSK_X_ORIGIN + column, OSK_Y_ORIGIN + band_y


def test_the_shipped_rows_spell_the_alphabet():
    """The three tables hold A..J, K..T and U..Z + space/Delete/Esc/Return, three columns apart.

    Transcribed off the image rather than described, because the description would be wrong: the
    bottom row's last four keys are TWO columns wide (0x39 0x39, 0x53 0x53, 0x01 0x01, 0x1c 0x1c)
    while every other key is one column with two dead ones after it. The whole 28-byte row is what
    a hit test walks, so the whole 28-byte row is what is pinned.

    Load-bearing for the cases below: it says the grid coordinates `_key_position` computes really
    do land on distinct keys, and that a near-miss really is a miss.
    """
    rows = [bytes(harness.BASE_IMAGE[table:table + OSK_ROW_BYTES])
            for table in (A_OSK_ROW_TOP, A_OSK_ROW_MIDDLE, A_OSK_ROW_BOTTOM)]
    assert rows == [
        bytes([0x1e, 0, 0, 0x30, 0, 0, 0x2e, 0, 0, 0x20, 0, 0, 0x12, 0, 0, 0x21, 0, 0,
               0x22, 0, 0, 0x23, 0, 0, 0x17, 0, 0, 0x24]),                              # A..J
        bytes([0x25, 0, 0, 0x26, 0, 0, 0x32, 0, 0, 0x31, 0, 0, 0x18, 0, 0, 0x19, 0, 0,
               0x10, 0, 0, 0x13, 0, 0, 0x1f, 0, 0, 0x14]),                              # K..T
        bytes([0x16, 0, 0, 0x2f, 0, 0, 0x11, 0, 0, 0x2d, 0, 0, 0x15, 0, 0, 0x2c, 0, 0,
               0x39, 0x39, 0, 0x53, 0x53, 0, 0x01, 0x01, 0, 0x1c])]                     # U..Z, ...
    # The rows are packed with no gap, which is what OSK_COLUMN_LAST's byte-28 overrun lands in.
    assert A_OSK_ROW_MIDDLE - A_OSK_ROW_TOP == OSK_ROW_BYTES
    assert A_OSK_ROW_BOTTOM - A_OSK_ROW_MIDDLE == OSK_ROW_BYTES


@pytest.mark.parametrize("row_index", range(3))
@pytest.mark.parametrize("key", range(OSK_KEYS_PER_ROW))
def test_every_key_of_every_row(key, row_index):
    """All thirty keys, addressed by their own screen position — the whole grid the game draws."""
    _case(*_key_position(row_index, key))


@pytest.mark.parametrize("y", (0, OSK_Y_ORIGIN, OSK_Y_ORIGIN + OSK_ROW_BAND_TOP - 1,
                               OSK_Y_ORIGIN + OSK_ROW_BAND_TOP,
                               OSK_Y_ORIGIN + OSK_ROW_TOP_MAX, OSK_Y_ORIGIN + OSK_ROW_TOP_MAX + 1,
                               OSK_Y_ORIGIN + OSK_ROW_MIDDLE_MAX,
                               OSK_Y_ORIGIN + OSK_ROW_MIDDLE_MAX + 1,
                               OSK_Y_ORIGIN + OSK_ROW_BOTTOM_MAX,
                               OSK_Y_ORIGIN + OSK_ROW_BOTTOM_MAX + 1, 0x8000, 0xffff))
def test_row_band_edges(y):
    """One step either side of all four row boundaries, on a column that is on a key.

    The bands SHARE their edges — a biased y of exactly 0x70 belongs to the TOP row, because that
    row's `ble` runs first — so a reconstruction that made them half-open picks the wrong table on
    exactly these values, and the two neighbouring rows hold different scancodes there.
    """
    _case(_key_position(0, 4)[0], y)


@pytest.mark.parametrize("x", (0, OSK_X_ORIGIN, OSK_X_ORIGIN + OSK_COLUMN_FIRST - 1,
                               OSK_X_ORIGIN + OSK_COLUMN_FIRST, OSK_X_ORIGIN + OSK_COLUMN_FIRST + 1,
                               OSK_X_ORIGIN + OSK_COLUMN_LAST - 1, OSK_X_ORIGIN + OSK_COLUMN_LAST,
                               OSK_X_ORIGIN + OSK_COLUMN_LAST + 1, 0x8000, 0xffff))
def test_column_band_edges(x):
    """`blt` at the first column and `bgt` at the last, so the band is CLOSED at both ends.

    OSK_COLUMN_LAST is the one that matters: it is 0x110, which after the shift indexes byte 28 of a
    28-byte row — the first byte of the NEXT row's table. The routine admits it, and this pins that.
    """
    _case(x, _key_position(0, 0)[1])


@pytest.mark.parametrize("offset", range(OSK_KEY_COLUMN_STRIDE << OSK_COLUMN_SHIFT))
def test_the_pixels_between_two_keys(offset):
    """One key's whole 24-pixel span: the first eight pixels are the key, the rest are dead columns.

    `lsr.w #3` is what turns pixels into columns, and a wrong shift moves this boundary.
    """
    x, y = _key_position(1, 3)
    _case(x + offset, y)


@pytest.mark.parametrize("scratch", (0, 0xffffffff, 0x0000ffff, 0xdead0000, 0x00ff00ff))
def test_d0_is_an_input_as_well_as_the_answer(scratch):
    """A hit overwrites only D0's low BYTE, so the caller's high word comes back untouched — while a
    MISS clears the whole register with `moveq`. Both arms are driven for each incoming value."""
    _case(*_key_position(2, 5), scratch=scratch)      # a hit
    _case(0, 0, scratch=scratch)                      # ...and a miss


def test_attribution():
    """Poison the stub's D0 store, on a hit and on a miss."""
    _case(*_key_position(0, 0), poison=True)
    _case(0, 0, poison=True)


FUZZ_CHUNKS = 4
FUZZ_CASES = 400


def _fuzz_cases():
    rng = random.Random(ENTRY_ONSCREEN_KEYBOARD_HIT_TEST)   # seeded ONCE; each chunk replays it
    grid_x, grid_y = _key_position(0, 0)
    for case in range(FUZZ_CASES):
        # Two thirds of the cases sit on or near the grid; the rest are anywhere in the word.
        near = case % 3
        yield (case,
               grid_x + rng.randrange(-0x20, 0x120) if near else rng.randrange(1 << 16),
               grid_y + rng.randrange(-0x20, 0x50) if near else rng.randrange(1 << 16),
               hi_garbage(rng, rng.randrange(1 << 16)))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz(chunk):
    """Random cursors with junk in D0's high half, which every case must hand back on a hit."""
    for case, x, y, scratch in _fuzz_cases():
        if case % FUZZ_CHUNKS == chunk:
            _case(x, y, scratch)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_OSK_CURSOR_X", "include/input.h", "A_osk_cursor_x"),
    ("A_OSK_CURSOR_Y", "include/input.h", "A_osk_cursor_y"),
    ("A_OSK_ROW_TOP", "include/input.h", "A_osk_row_top"),
    ("A_OSK_ROW_MIDDLE", "include/input.h", "A_osk_row_middle"),
    ("A_OSK_ROW_BOTTOM", "include/input.h", "A_osk_row_bottom"),
    ("OSK_X_ORIGIN", "include/input.h", "OSK_X_ORIGIN"),
    ("OSK_Y_ORIGIN", "include/input.h", "OSK_Y_ORIGIN"),
    ("OSK_ROW_BAND_TOP", "include/input.h", "OSK_ROW_BAND_TOP"),
    ("OSK_ROW_TOP_MAX", "include/input.h", "OSK_ROW_TOP_MAX"),
    ("OSK_ROW_MIDDLE_MAX", "include/input.h", "OSK_ROW_MIDDLE_MAX"),
    ("OSK_ROW_BOTTOM_MAX", "include/input.h", "OSK_ROW_BOTTOM_MAX"),
    ("OSK_COLUMN_FIRST", "include/input.h", "OSK_COLUMN_FIRST"),
    ("OSK_COLUMN_LAST", "include/input.h", "OSK_COLUMN_LAST"),
    ("OSK_COLUMN_SHIFT", "include/input.h", "OSK_COLUMN_SHIFT"),
)
ENTRY_PROLOGUES = {"ENTRY_ONSCREEN_KEYBOARD_HIT_TEST": "48e77ffe323900019d44"}
