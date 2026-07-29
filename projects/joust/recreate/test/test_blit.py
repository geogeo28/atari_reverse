"""Differential tests for blit_copy @ 0x1042a, blit_or @ 0x10456 and blit_andnot @ 0x10482.

The three are the same routine with one opcode changed, so every case runs against all three (see
src/blit.c). The destination is always pre-seeded with noise: without it, `or` and `and-not` would
be indistinguishable from a plain copy.
"""
import ctypes
import random
import struct

import pytest

import abi
import harness
from harness import differential, report

# name -> entry address (names.txt), paired with the glue that reconstructs it.
BLITS = {"blit_copy": 0x1042a, "blit_or": 0x10456, "blit_andnot": 0x10482}

CELL_BYTES = 8            # bytes per 4-plane cell    (mirrors include/joust.h)
SCREEN_ROW_BYTES = 0xa0   # destination stride per row (mirrors include/joust.h)
BLIT_DST = 0x50000        # two scratch buffers, clear of the program and of abi.STUB/ARG_BLOCK
BLIT_SRC = 0x70000

for _name in BLITS:
    getattr(harness._lib, "g_" + _name).argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
    getattr(harness._lib, "g_" + _name).restype = None


def _passes(count):
    """The 68000 `subq.b` loop count: only the low byte counts, and 0 means 256 passes."""
    return ((count - 1) & 0xff) + 1


def _case(name, cols, rows, seed, poison=False):
    col_passes, row_passes = _passes(cols), _passes(rows)
    src_span = col_passes * row_passes * CELL_BYTES              # the source is read straight through
    dst_span = (row_passes - 1) * SCREEN_ROW_BYTES + col_passes * CELL_BYTES

    rng = random.Random(seed)
    pokes = abi.stack_call_pokes(BLITS[name])
    pokes[BLIT_SRC] = bytes(rng.randrange(256) for _ in range(src_span))
    pokes[BLIT_DST] = bytes(rng.randrange(256) for _ in range(dst_span))
    pokes[abi.ARG_BLOCK] = struct.pack(">IIHH", BLIT_DST, BLIT_SRC, cols, rows)

    diffs, _ = differential(abi.STUB, {"_pokes": pokes},
                            lambda lib, buf: getattr(lib, "g_" + name)(buf, abi.ARG_BLOCK),
                            poison=poison)
    assert not diffs, f"{name} cols={cols:#x} rows={rows:#x} seed={seed}\n{report(diffs)}"


# Shapes that pin the loop arithmetic:
#   (20,1)/(21,4) — 20 cells is exactly one scanline, so from 21 the rows OVERLAP and the order the
#                   original writes them in becomes observable;
#   (0,1)/(1,0)   — a zero count means 256 passes, not none;
#   0x100/0x101/0xff00 — only the low byte of the count is read.
_SHAPES = ((1, 1), (2, 1), (1, 2), (3, 5), (20, 1), (20, 4), (21, 4), (64, 3), (255, 1), (1, 255),
           (0, 1), (1, 0), (0x100, 1), (1, 0x100), (0x101, 1), (1, 0x101), (0xff00, 1), (1, 0xff00))


@pytest.mark.parametrize("name", BLITS)
def test_shapes(name):
    for seed, (cols, rows) in enumerate(_SHAPES):
        _case(name, cols, rows, seed=seed)


@pytest.mark.parametrize("name", BLITS)
def test_attribution(name):
    # poison=True: with the destination pre-seeded from the same stream on both sides, a candidate
    # that skipped a cell could still match; poisoning the oracle's outputs makes the omission show.
    for seed, (cols, rows) in enumerate(((1, 1), (3, 5), (21, 4), (0, 1), (1, 0))):
        _case(name, cols, rows, seed=0x900 + seed, poison=True)


# --- fidelity: the original re-reads `cols` from its caller's frame on EVERY row ------------------
# Its row branch targets the `move.w 12(a7),d0` at 0x43a/0x466/0x492, while `rows` is fetched once
# at 0x436. That is observable only when the destination rectangle covers the argument block itself,
# so this case builds exactly that: the rectangle starts one scanline above abi.ARG_BLOCK, so row 1
# lands on the block and rewrites its `cols` field, and rows 2+ must pick the new value up. A
# reconstruction that hoisted `cols` into a local keeps the original count and writes cells the
# oracle never wrote.
REREAD_ROWS = 5
REREAD_COLS = 6            # small enough that row 0 stops short of abi's pre-poked return slot
ARG_COLS_OFF = 8           # BLIT_ARG_COLS; pinned to src/blit.c by test_constants.py
# The source byte row 1 lays over the LOW byte of `cols` (the high byte is left 0; only the low one
# counts). The destination byte it combines with is necessarily REREAD_COLS itself — that is the
# field being overwritten — so 3 is picked to leave a small count differing from 6 under all three
# combines: copy -> src = 3, or -> 6|3 = 7, and-not -> 6 & ~3 = 4.
REREAD_SRC_BYTE = 0x03
REREAD_MAX_COLS = 8        # bounds all three of those; the noise buffers must outlast the widest


@pytest.mark.parametrize("name", BLITS)
def test_cols_is_reread_every_row(name):
    dst = abi.ARG_BLOCK - SCREEN_ROW_BYTES
    # Sized for REREAD_MAX_COLS so the buffers still cover the hoisted path (which keeps writing
    # REREAD_COLS cells per row) as well as the faithful one — otherwise a divergence could fall
    # outside the seeded noise and go unseen.
    span = (REREAD_ROWS - 1) * SCREEN_ROW_BYTES + REREAD_MAX_COLS * CELL_BYTES
    rng = random.Random(0xC0175)
    dst_noise = bytearray(rng.randrange(256) for _ in range(span))
    src_noise = bytearray(rng.randrange(256)
                          for _ in range(REREAD_ROWS * REREAD_MAX_COLS * CELL_BYTES))
    # Within a row, destination offset k takes source offset k, so the block's `cols` word is fed
    # from the source offset one whole row on plus ARG_COLS_OFF.
    row1 = REREAD_COLS * CELL_BYTES
    src_noise[row1 + ARG_COLS_OFF:row1 + ARG_COLS_OFF + 2] = bytes((0, REREAD_SRC_BYTE))

    # Insertion order matters: the destination noise covers both the argument block and the return
    # slot abi pre-pokes below it, so those two are poked AFTER it and win (make_image applies pokes
    # in order). The oracle must still find its real arguments and its rts sentinel.
    pokes = {dst: bytes(dst_noise), BLIT_SRC: bytes(src_noise)}
    pokes.update(abi.stack_call_pokes(BLITS[name]))
    pokes[abi.ARG_BLOCK] = struct.pack(">IIHH", dst, BLIT_SRC, REREAD_COLS, REREAD_ROWS)

    diffs, _ = differential(abi.STUB, {"_pokes": pokes},
                            lambda lib, buf: getattr(lib, "g_" + name)(buf, abi.ARG_BLOCK))
    assert not diffs, f"{name} cols re-read from a self-overwritten frame\n{report(diffs)}"


FUZZ_CHUNKS = 4


def _fuzz_cases():
    rng = random.Random(0x1042A)                 # seeded ONCE — every chunk replays this stream
    for i in range(300):
        yield i, rng.randrange(1, 48), rng.randrange(1, 48)


@pytest.mark.parametrize("name", BLITS)
@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz(chunk, name):
    for i, cols, rows in _fuzz_cases():
        if i % FUZZ_CHUNKS == chunk:
            _case(name, cols, rows, seed=i)
