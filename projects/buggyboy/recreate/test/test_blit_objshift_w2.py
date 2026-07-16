"""Differential test for the "0x90" width family of the blit_objshift engine, entered at 0x144c8.

Same engine and register contract as blit_objshift (0x14680) — a sub-pixel (fine-x shifted) 4-plane
masked-transparency sprite blitter — but the wider entry (base ceiling 0x90) draws a TWO-straddle-cell
base and reaches the LEFT-2 / RIGHT-2 ladder rungs that are dead from the 0x14680 entry. These bodies
are dispatched by draw_object_list's jump table (object types 13-15, via 0x144ac/0x144b2).

Entry 0x144c8 is the color_pairs load — the exact analogue of blit_objshift's 0x14680 entry (after the
handler-specific a0/src/mode preamble). Register contract: D0 screen x, D1 colour index, D4 rows-1,
A0 dst scanline base, A1 src sprite stream, A3 -> per-row src-stride word. color_pairs @ 0x15afa is
real image data (NOT staged). Whole-image diff vs the Musashi oracle (poisoned).

The 0x90 dispatch (aligned_col A, a signed multiple of 8):
  A <= -24 -> off left, no draw;  A == -16 -> LEFT-1 (edge only);  A == -8 -> LEFT-2 (edge + 1 straddle);
  0 <= A < 0x90 -> BASE (2 straddle cells);  A == 0x90 -> RIGHT-2 (1 straddle + trail edge);
  A == 0x98 -> RIGHT-1 (trail edge only);  A >= 0xa0 -> off right, no draw.
"""
import ctypes
import random

import pytest

import harness
from harness import differential, report

ENTRY = 0x144c8

# Number of xdist shards the fuzz loop is split into (round-robin by iteration index).
FUZZ_CHUNKS = 8

DST_BASE = 0x60000        # dst scanline base; a0 = dst + aligned_col, then rewinds DOWN per row
DST_LO = 0x5c000          # start of the staged dst noise region (covers rewinds below DST_BASE)
DST_SPAN = 0x8000         # covers DST_LO .. DST_BASE + column reach across all fuzzed rows
SRC_BASE = 0x88000        # src sprite stream (a1); walks by (8 - stride) per row
STRIDE_PTR = 0xf0000      # A3 -> the per-row src-stride word

FINE_X_ALL = range(16)


def _x_for(col, fine_x):
    """x that decodes to aligned column `col` (a signed multiple of 8) with nibble `fine_x`.
    aligned_col = ((int16)x >> 1) & 0xfff8; fine_x = x & 0xf. They don't overlap for col % 8 == 0."""
    return ((col << 1) | (fine_x & 0xf)) & 0xffff


def _src_band(rows_m1, stride_word):
    """Byte span [lo, hi) a1 sweeps over the run. Per row a1 nets (8 - stride); each row reads up to a
    few cells ahead (2-straddle base + the LEFT skip pre-advance). Headroom 0x30 covers it."""
    stride = stride_word - 0x10000 if stride_word >= 0x8000 else stride_word
    rows = (rows_m1 & 0xffff)
    rows = (rows - 0x10000 if rows >= 0x8000 else rows) + 1
    per_row = 8 - stride
    a1 = SRC_BASE
    lo = hi = SRC_BASE
    for _ in range(max(rows, 1)):
        lo = min(lo, a1); hi = max(hi, a1 + 0x30)
        a1 += per_row
    lo = min(lo, a1); hi = max(hi, a1 + 0x30)
    return lo, hi


def _pokes(seed, rows_m1, stride_word):
    rng = random.Random(seed)
    lo, hi = _src_band(rows_m1, stride_word)
    return {
        DST_LO: bytes(rng.randrange(256) for _ in range(DST_SPAN)),
        lo: bytes(rng.randrange(256) for _ in range(hi - lo)),
        STRIDE_PTR: (stride_word & 0xffff).to_bytes(2, "big"),
    }


def _check(seed, x, color, rows_m1, stride_word):
    regs = {
        "d0": x & 0xffff, "d1": color & 0xffff, "d4": rows_m1 & 0xffff,
        "a0": DST_BASE, "a1": SRC_BASE, "a3": STRIDE_PTR,
        "_pokes": _pokes(seed, rows_m1, stride_word),
    }
    diffs, _ = differential(
        ENTRY, regs,
        lambda lib, buf: lib.g_blit_objshift_w2(buf, x & 0xffff, color & 0xffff, rows_m1 & 0xffff,
                                                DST_BASE, SRC_BASE, STRIDE_PTR),
        poison=True)
    assert not diffs, (f"x={x:#x} col={color} rows={rows_m1 + 1} stride={stride_word:#x}\n"
                       f"{report(diffs[:16])}")


harness._lib.g_blit_objshift_w2.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 6
harness._lib.g_blit_objshift_w2.restype = None


def test_base_every_fine_x():
    # BASE: 0 <= aligned_col < 0x90, TWO straddle cells per row, every fine-x + colour.
    for fine_x in FINE_X_ALL:
        for color in (0, 3, 15):
            _check(seed=fine_x * 16 + color, x=_x_for(0x40, fine_x), color=color,
                   rows_m1=3, stride_word=8)


def test_left_cases_every_fine_x():
    # LEFT-2 (A=-8, edge + 1 straddle) and LEFT-1 (A=-16, edge only, one skipped column).
    for col in (-8, -16):
        for fine_x in FINE_X_ALL:
            for color in (1, 7, 14):
                _check(seed=0x100 + (col & 0xff) * 16 + fine_x * 4 + color,
                       x=_x_for(col, fine_x), color=color, rows_m1=2, stride_word=8)


def test_right_cases_every_fine_x():
    # RIGHT-2 (A=0x90, 1 straddle + trail edge) and RIGHT-1 (A=0x98, trail edge only).
    for col in (0x90, 0x98):
        for fine_x in FINE_X_ALL:
            for color in (2, 9, 15):
                _check(seed=0x300 + col * 16 + fine_x * 4 + color,
                       x=_x_for(col, fine_x), color=color, rows_m1=2, stride_word=8)


def test_clipped_columns_no_draw():
    # A <= -24 and A >= 0xa0 both rts without drawing (must match: no writes).
    for fine_x in (0, 5, 15):
        for col in (-24, -32, 0xa0, 0xa8, 0x100):
            _check(seed=0x500 + fine_x + (col & 0xffff), x=_x_for(col, fine_x),
                   color=6, rows_m1=1, stride_word=8)


def test_base_column_sweep():
    # Every BASE aligned column 0..0x88 (multiples of 8), one fine-x.
    for col in range(0, 0x90, 8):
        _check(seed=0x600 + col, x=_x_for(col, 7), color=5, rows_m1=2, stride_word=0x10)


def test_stride_words():
    for stride in (0, 8, 0x10, 0x40, 0x100, -8 & 0xffff, -0x20 & 0xffff, 0x600, -0x600 & 0xffff):
        _check(seed=0x700 + stride, x=_x_for(0x30, 4), color=8, rows_m1=1, stride_word=stride)


def test_row_counts():
    for rows_m1 in (0, 1, 5, 15, 0x2f):
        _check(seed=0x800 + rows_m1, x=_x_for(0x50, 9), color=11, rows_m1=rows_m1, stride_word=0x18)


def _fuzz_cases():
    """Yield (i, x, color, rows_m1, stride) from a single seeded RNG stream.

    Split from the check so the fuzz can be sharded across xdist workers without
    perturbing the stream: every worker replays the full sequence (cheap) and only
    runs the expensive differential on its assigned iterations. Coverage is identical.
    """
    rng = random.Random(0x90FA)
    for i in range(4000):
        fine_x = rng.randrange(16)
        col = rng.choice([
            rng.randrange(-48, -16) & ~7,      # clipped left
            -16,                               # LEFT-1
            -8,                                # LEFT-2
            rng.randrange(0, 0x90) & ~7,       # base
            0x90,                              # RIGHT-2
            0x98,                              # RIGHT-1
            rng.randrange(0xa0, 0x140) & ~7,   # clipped right
        ])
        x = _x_for(col, fine_x)
        color = rng.randrange(16)
        rows_m1 = rng.randrange(0, 20)
        stride = rng.randint(-0x400, 0x400) & 0xffff
        yield i, x, color, rows_m1, stride


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_fuzz(chunk):
    for i, x, color, rows_m1, stride in _fuzz_cases():
        if i % FUZZ_CHUNKS != chunk:
            continue
        _check(seed=i, x=x, color=color, rows_m1=rows_m1, stride_word=stride)
