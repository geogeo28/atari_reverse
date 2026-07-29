"""Differential tests for pos_to_screen @ 0x182a2 and screen_to_pos @ 0x182d6 (src/screen.c)."""
import ctypes
import random
import struct

import pytest

import abi
import emu
import harness
from harness import differential, report

ENTRY_POS_TO_SCREEN = 0x182a2
ENTRY_SCREEN_TO_POS = 0x182d6
A_SCREEN_BASE = 0x10dde   # names.txt: screen_base

CELL_BYTES = 8            # bytes per 4-plane cell (mirror of include/joust.h)

# Argument-block layout, mirroring POS_ARG_* in src/screen.c (offsets from 4(a7)).
ARG_ADDR, ARG_SHIFT, ARG_X, ARG_Y = 0, 4, 6, 8

# Every output slot is pre-filled with this before the call, so a slot the candidate forgets to
# write differs from the oracle's unless the two genuinely agree.
UNWRITTEN_L, UNWRITTEN_W = 0x5a5a5a5a, 0x5a5a

for _glue in ("g_pos_to_screen", "g_screen_to_pos"):
    getattr(harness._lib, _glue).argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
    getattr(harness._lib, _glue).restype = None

# Screen bases the routines are exercised against. Nothing is dereferenced through the address they
# compute, so any value is legal — including odd and "negative" ones, which pin the plain 32-bit
# arithmetic (`sub.l`, `adda.w`) rather than anything screen-shaped.
_SCREEN_BASES = (0x78000, 0x40000, 0, 2, 0xfffffffe)


def _pos_pokes(screen_base, x, y):
    pokes = abi.stack_call_pokes(ENTRY_POS_TO_SCREEN)
    pokes[A_SCREEN_BASE] = screen_base.to_bytes(4, "big")
    pokes[abi.ARG_BLOCK] = struct.pack(">IHHH", UNWRITTEN_L, UNWRITTEN_W, x, y)   # addr/shift out
    return pokes


def _inverse_pokes(screen_base, addr, shift):
    pokes = abi.stack_call_pokes(ENTRY_SCREEN_TO_POS)
    pokes[A_SCREEN_BASE] = screen_base.to_bytes(4, "big")
    pokes[abi.ARG_BLOCK] = struct.pack(">IHHH", addr, shift, UNWRITTEN_W, UNWRITTEN_W)  # x/y out
    return pokes


def _pos_case(screen_base, x, y, poison=False):
    pokes = _pos_pokes(screen_base, x, y)
    diffs, _ = differential(abi.STUB, {"_pokes": pokes},
                            lambda lib, buf: lib.g_pos_to_screen(buf, abi.ARG_BLOCK), poison=poison)
    assert not diffs, f"base={screen_base:#x} x={x} y={y}\n{report(diffs)}"


def _inverse_case(screen_base, offset, shift, poison=False):
    addr = (screen_base + offset) & 0xffffffff
    pokes = _inverse_pokes(screen_base, addr, shift)
    diffs, _ = differential(abi.STUB, {"_pokes": pokes},
                            lambda lib, buf: lib.g_screen_to_pos(buf, abi.ARG_BLOCK), poison=poison)
    assert not diffs, f"base={screen_base:#x} offset={offset:#x} shift={shift:#x}\n{report(diffs)}"


# x around every cell boundary the `divu.w #$10` splits on, plus both ends of the word.
_POS_X = (0, 1, 15, 16, 17, 31, 32, 159, 160, 319, 320, 0x7fff, 0x8000, 0xffff)
# y around the visible screen, and around 205 — where y*0xa0 passes 0x7fff and `adda.w` starts
# sign-extending the row offset NEGATIVE, running the address back up the screen instead of down.
_POS_Y = (0, 1, 99, 199, 200, 203, 204, 205, 206, 409, 410, 0x7fff, 0x8000, 0xffff)


@pytest.mark.parametrize("screen_base", _SCREEN_BASES)
def test_pos_to_screen_edges(screen_base):
    for x in _POS_X:
        for y in _POS_Y:
            _pos_case(screen_base, x, y)


def test_pos_to_screen_attribution():
    # poison=True costs a second run plus a full-image walk, so it covers a handful of shapes
    # rather than the grid above: it proves the candidate really writes both output slots.
    for x, y in ((0, 0), (17, 100), (319, 199), (0xffff, 0xffff), (16, 205)):
        _pos_case(0x78000, x, y, poison=True)


# Offsets from screen_base, in bytes. The middle three straddle `divu.w #$a0`'s overflow: a quotient
# above 0xffff (dividend >= 0xa0 * 0x10000) leaves the 68000's destination register UNTOUCHED, so
# the routine silently carries the raw offset into the rest of its arithmetic.
_DIVU_ROW_OVERFLOW = 0xa0 * 0x10000
_INVERSE_OFFSETS = (0, 1, 7, 8, 9, 0x9f, 0xa0, 0xa1, 0x140, 0x7cff, 0x7d00, 0xffff, 0x10000,
                    _DIVU_ROW_OVERFLOW - 1, _DIVU_ROW_OVERFLOW, _DIVU_ROW_OVERFLOW + 0xa0,
                    0x7fffffff, 0xffffffff)
# Shifts, including values past a cell (the routine simply adds them) and the word extremes.
_INVERSE_SHIFTS = (0, 1, 7, 8, 15, 16, 0x7fff, 0x8000, 0xffff)


@pytest.mark.parametrize("screen_base", _SCREEN_BASES)
def test_screen_to_pos_edges(screen_base):
    for offset in _INVERSE_OFFSETS:
        for shift in _INVERSE_SHIFTS:
            _inverse_case(screen_base, offset, shift)


def test_screen_to_pos_attribution():
    for offset, shift in ((0, 0), (0xa1, 3), (_DIVU_ROW_OVERFLOW, 0), (0xffffffff, 0xffff)):
        _inverse_case(0x78000, offset, shift, poison=True)


ORIGINAL_X_SCALE = 0x16   # `mulu.w #$16` = 22, where inverting pos_to_screen needs 16


def test_screen_to_pos_keeps_the_original_wrong_x_scale():
    """Pin the shipped bug: one cell into a row reads back as x = 22, not x = 16.

    The differential cases above already refuse any "corrected" reconstruction; this states the
    value outright so the reason is on the record. screen_to_pos is unreferenced in the whole
    image, which is why the game never trips over it.
    """
    screen_base = 0x78000
    pokes = _inverse_pokes(screen_base, screen_base + CELL_BYTES, shift=0)
    final, _, _ = emu.run(harness.make_image(pokes), abi.STUB)
    x, y = struct.unpack_from(">HH", bytes(final), abi.ARG_BLOCK + ARG_X)
    assert (x, y) == (ORIGINAL_X_SCALE, 0), f"original reported x={x} y={y}"


FUZZ_CHUNKS = 4


def _fuzz_cases():
    rng = random.Random(0x182A2)                 # seeded ONCE — every chunk replays this stream
    for i in range(800):
        # Split the offsets: the overflow threshold is only 0.24% of the 32-bit range, so drawing
        # them uniformly would put ~798 of 800 cases on the "destination unchanged" path and leave
        # the ordinary in-range arithmetic to the handful of hand-picked offsets above.
        in_range = rng.random() < 0.5
        offset = rng.randrange(_DIVU_ROW_OVERFLOW) if in_range else rng.randrange(1 << 32)
        yield (i, rng.choice(_SCREEN_BASES), rng.randrange(0x10000), rng.randrange(0x10000),
               offset, rng.randrange(0x10000))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz(chunk):
    for i, screen_base, x, y, offset, shift in _fuzz_cases():
        if i % FUZZ_CHUNKS != chunk:
            continue
        _pos_case(screen_base, x, y)
        _inverse_case(screen_base, offset, shift)
