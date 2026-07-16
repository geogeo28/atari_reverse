"""Differential test for blit_objshift2 @ 0x13ed6 — the SECOND sub-pixel (fine-x shifted) 4-plane
masked sprite blitter (leaf; no Ghidra function entry, disassembly-driven).

Distinct from blit_objshift @ 0x14680: the transparency mask is built from only TWO source words
(~(w0|w1)), it never touches color_pairs, and the copy is a plain shifted OR. PURE LEAF.

Register contract (see names.txt proto): D0 screen x, D4 rows-1, A0 dst scanline base, A1 src sprite
stream. There is NO A3/stride word and NO colour: a1 rewinds by a fixed per-row constant (net -0x50).

The test stages a noise dst buffer and a noise src arena, presets the registers, and diffs the whole
image against the Musashi oracle (poisoned). Fuzz spans every fine-x (0..15), every reachable dispatch
case (left-clip / L0C / L1C / L2C / base / W2 / W1 / W0 / right-clip), several row counts, and random
sprite content — so every reachable body and both edge-cell kinds are exercised.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x13ed6

# Staged low-memory layout (clear of the program, which ends 0x1bcf8, and of the stack guard).
DST_BASE = 0x60000        # dst scanline base; a0 = dst + aligned_col, then rewinds DOWN per row
DST_LO = 0x5c000          # start of the staged dst noise region (covers rewinds below DST_BASE)
DST_SPAN = 0x8000         # covers DST_LO .. DST_BASE + column reach across all fuzzed rows
SRC_BASE = 0x88000        # src sprite stream (a1); marches DOWN by 0x50 per row (fixed rewind)

SRC_STEP_PER_ROW = 0x50   # net a1 delta per row (negative direction): 4*cells - rewind_src
CELL_READ_AHEAD = 0x10    # max bytes a1 reads forward within one row (3 cells * 4 + a mask +2)

FINE_X_ALL = range(16)


def _x_for(col, fine_x):
    """x that decodes to aligned column `col` (a signed multiple of 8) with nibble `fine_x`.
    aligned_col = ((int16)x >> 1) & 0xfff8 reads x bits >= 4; fine_x = x & 0xf reads bits 0..3.
    They don't overlap when col is a multiple of 8 (col<<1 has zero low nibble)."""
    return ((col << 1) | (fine_x & 0xf)) & 0xffff


def _src_band(rows_m1):
    """Byte span [lo, hi) the src pointer a1 sweeps over the run. a1 starts at SRC_BASE and marches
    DOWN by SRC_STEP_PER_ROW per row, reading up to CELL_READ_AHEAD ahead within each row."""
    rows = (rows_m1 & 0xffff)
    rows = (rows - 0x10000 if rows >= 0x8000 else rows) + 1
    lo = SRC_BASE - SRC_STEP_PER_ROW * max(rows - 1, 0)
    hi = SRC_BASE + CELL_READ_AHEAD
    return lo, hi


def _pokes(seed, rows_m1):
    rng = random.Random(seed)
    lo, hi = _src_band(rows_m1)
    return {
        DST_LO: bytes(rng.randrange(256) for _ in range(DST_SPAN)),
        lo: bytes(rng.randrange(256) for _ in range(hi - lo)),
    }


def _check(seed, x, rows_m1):
    regs = {
        "d0": x & 0xffff, "d4": rows_m1 & 0xffff,
        "a0": DST_BASE, "a1": SRC_BASE,
        "_pokes": _pokes(seed, rows_m1),
    }
    diffs, _ = differential(
        ENTRY, regs,
        lambda lib, buf: lib.g_blit_objshift2(buf, x & 0xffff, rows_m1 & 0xffff, DST_BASE, SRC_BASE),
        poison=True)
    assert not diffs, (f"x={x:#x} rows={rows_m1 + 1}\n{report(diffs[:16])}")


harness._lib.g_blit_objshift2.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 4
harness._lib.g_blit_objshift2.restype = None


def test_base_every_fine_x():
    # BASE: 0 <= aligned_col <= 0x80, three straddle cells per row, every fine-x.
    for fine_x in FINE_X_ALL:
        _check(seed=fine_x, x=_x_for(0x40, fine_x), rows_m1=3)


def test_base_column_sweep():
    # Every BASE aligned column 0..0x80 (multiples of 8), one fine-x.
    for col in range(0, 0x88, 8):
        _check(seed=0x100 + col, x=_x_for(col, 7), rows_m1=2)


def test_left_cases_every_fine_x():
    # LEFT family: aligned_col in {-8 (L2C), -16 (L1C), -24 (L0C)} -> LE-cell + {2,1,0} straddles.
    for fine_x in FINE_X_ALL:
        for col in (-8, -16, -24):
            _check(seed=0x200 + fine_x * 4 + ((-col) >> 3), x=_x_for(col, fine_x), rows_m1=2)


def test_wide_cases_every_fine_x():
    # WIDE family: aligned_col in {0x88 (W2), 0x90 (W1), 0x98 (W0)} -> {2,1,0} straddles + RE-cell.
    for fine_x in FINE_X_ALL:
        for col in (0x88, 0x90, 0x98):
            _check(seed=0x300 + fine_x * 4 + ((col - 0x88) >> 3), x=_x_for(col, fine_x), rows_m1=2)


def test_clipped_columns_no_draw():
    # aligned_col <= -32 and >= 0xa0 both rts without drawing (must match: no writes).
    for fine_x in (0, 5, 15):
        for col in (-32, -40, -0x80, 0xa0, 0xa8, 0x100):
            _check(seed=0x400 + fine_x + (col & 0xffff), x=_x_for(col, fine_x), rows_m1=1)


def test_row_counts():
    # dbf d4 counts d4+1 rows; a1 marches down 0x50/row, so keep rows bounded to the staged arena.
    for rows_m1 in (0, 1, 5, 15, 0x2f):
        _check(seed=0x500 + rows_m1, x=_x_for(0x50, 9), rows_m1=rows_m1)


def test_fuzz():
    rng = random.Random(0xB0B2)
    for i in range(4000):
        fine_x = rng.randrange(16)
        # Bias the aligned column across the whole dispatch: clipped-left, the three LEFT cases,
        # base, the three WIDE cases, clipped-right. `col` is a signed multiple of 8.
        col = rng.choice([
            rng.randrange(-0x80, -24) & ~7,    # clipped left (<= -32)
            -24, -16, -8,                      # L0C / L1C / L2C
            rng.randrange(0, 0x88) & ~7,       # base (0..0x80)
            0x88, 0x90, 0x98,                  # W2 / W1 / W0
            rng.randrange(0xa0, 0x140) & ~7,   # clipped right (>= 0xa0)
        ])
        x = _x_for(col, fine_x)
        rows_m1 = rng.randrange(0, 20)         # bounded so a1 stays inside the staged src arena
        _check(seed=i, x=x, rows_m1=rows_m1)
