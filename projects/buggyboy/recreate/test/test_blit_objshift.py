"""Differential test for blit_objshift @ 0x14680 — the sub-pixel (fine-x shifted) 4-plane
masked-transparency sprite blitter (leaf; no Ghidra function entry, disassembly-driven).

Register contract (see names.txt proto): D0 screen x, D1 colour index, D4 rows-1, A0 dst scanline
base, A1 src sprite stream, A3 -> per-row src-stride word. color_pairs @ 0x15afa is real image data
(NOT staged). The test stages a noise dst buffer and a noise src arena, points A3 at a controlled
stride word, and diffs the whole image against the Musashi oracle (poisoned).

Fuzz spans every fine-x (0..15), every dispatch case (left-clip / left-edge / base / right-edge /
right-clip and columns past the bounds), colour 0..15, several row counts, several stride words, and
random sprite content — so every reachable body and both edge-cell kinds are exercised.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x14680

# Staged low-memory layout (clear of the program, which ends 0x1bcf8, and of the stack guard).
DST_BASE = 0x40000        # dst scanline base; a0 = dst + aligned_col, then rewinds DOWN per row
DST_LO = 0x30000          # start of the staged dst noise region (covers rewinds below DST_BASE)
DST_SPAN = 0x14000        # covers DST_LO .. DST_BASE + column reach across all rows
# Staged low-memory layout (clear of the program, which ends 0x1bcf8, and of the stack guard).
DST_BASE = 0x60000        # dst scanline base; a0 = dst + aligned_col, then rewinds DOWN per row
DST_LO = 0x5c000          # start of the staged dst noise region (covers rewinds below DST_BASE)
DST_SPAN = 0x8000         # covers DST_LO .. DST_BASE + column reach across all fuzzed rows
SRC_BASE = 0x88000        # src sprite stream (a1); walks by (8 - stride) per row (either direction)
STRIDE_PTR = 0xf0000      # A3 -> the per-row src-stride word (clear of every staged src band)

FINE_X_ALL = range(16)

# aligned_col = ((int16_t)x >> 1) & 0xfff8. To hit a target aligned column `col` with a chosen
# fine_x nibble, x = (col << 1) | fine_x. The dispatch boundaries live at aligned_col in
# {..-16, -8, 0..0x90, 0x98, 0xa0..}; sweeping x over a wide range covers all of them.


def _x_for(col, fine_x):
    """x that decodes to aligned column `col` (a signed multiple of 8) with nibble `fine_x`.
    aligned_col = ((int16)x >> 1) & 0xfff8 reads x bits >= 4; fine_x = x & 0xf reads bits 0..3.
    They don't overlap when col is a multiple of 8 (col<<1 has zero low nibble)."""
    return ((col << 1) | (fine_x & 0xf)) & 0xffff


def _src_band(rows_m1, stride_word):
    """Byte span [lo, hi) the src pointer a1 sweeps over the run, so the staged noise covers every
    read. Per row a1 nets (cells_advance - stride); each row also reads up to CELL_BYTES ahead. We
    keep a1 inside a big staged region (mirroring a real in-bounds sprite arena) so the test never
    probes the emulator's out-of-bounds-reads-as-zero behaviour, which real code never triggers."""
    stride = stride_word - 0x10000 if stride_word >= 0x8000 else stride_word   # sign-extend the word
    rows = (rows_m1 & 0xffff)
    rows = (rows - 0x10000 if rows >= 0x8000 else rows) + 1
    per_row = 8 - stride                                    # a1 net delta per row (reachable cases)
    a1 = SRC_BASE
    lo = hi = SRC_BASE
    for _ in range(max(rows, 1)):
        lo = min(lo, a1); hi = max(hi, a1 + 0x28)          # up to 5 cells' worth of reads per row
        a1 += per_row
    lo = min(lo, a1); hi = max(hi, a1 + 0x28)
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
        lambda lib, buf: lib.g_blit_objshift(buf, x & 0xffff, color & 0xffff, rows_m1 & 0xffff,
                                             DST_BASE, SRC_BASE, STRIDE_PTR),
        poison=True)
    assert not diffs, (f"x={x:#x} col={color} rows={rows_m1 + 1} stride={stride_word:#x}\n"
                       f"{report(diffs[:16])}")


harness._lib.g_blit_objshift.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 6
harness._lib.g_blit_objshift.restype = None


def test_base_every_fine_x():
    # BASE: 0 <= aligned_col < 0x98, one straddle cell per row, every fine-x + colour.
    for fine_x in FINE_X_ALL:
        for color in (0, 3, 15):
            _check(seed=fine_x * 16 + color, x=_x_for(0x40, fine_x), color=color,
                   rows_m1=3, stride_word=8)


def test_left_edge_every_fine_x():
    # LEFT case1: aligned_col == -8, a2-only lead edge cell.
    for fine_x in FINE_X_ALL:
        for color in (1, 7, 14):
            _check(seed=0x100 + fine_x * 16 + color, x=_x_for(-8, fine_x),
                   color=color, rows_m1=2, stride_word=8)


def test_right_edge_every_fine_x():
    # RIGHT case1: aligned_col == 0x98, a0-only trail edge cell.
    for fine_x in FINE_X_ALL:
        for color in (2, 9, 15):
            _check(seed=0x200 + fine_x * 16 + color, x=_x_for(0x98, fine_x),
                   color=color, rows_m1=2, stride_word=8)


def test_clipped_columns_no_draw():
    # aligned_col <= -16 and >= 0xa0 both rts without drawing (must match: no writes).
    for fine_x in (0, 5, 15):
        for col in (-16, -24, 0xa0, 0xa8, 0x100):
            _check(seed=0x300 + fine_x + (col & 0xffff), x=_x_for(col, fine_x),
                   color=6, rows_m1=1, stride_word=8)


def test_base_column_sweep():
    # Every BASE aligned column 0..0x90 (multiples of 8), one fine-x.
    for col in range(0, 0x98, 8):
        _check(seed=0x400 + col, x=_x_for(col, 7), color=5, rows_m1=2, stride_word=0x10)


def test_stride_words():
    # The per-row a1 rewind is suba.w (a3): a sign-extended WORD. Exercise zero / positive /
    # negative / larger magnitudes (kept small enough that a1 stays inside the staged src arena,
    # as it does in real use). 2 rows so even a big stride keeps a1 in-bounds.
    for stride in (0, 8, 0x10, 0x40, 0x100, -8 & 0xffff, -0x20 & 0xffff, -0x100 & 0xffff, 0x600,
                   -0x600 & 0xffff):
        _check(seed=0x500 + stride, x=_x_for(0x30, 4), color=8, rows_m1=1, stride_word=stride)


def test_row_counts():
    for rows_m1 in (0, 1, 5, 15, 0x2f):
        _check(seed=0x600 + rows_m1, x=_x_for(0x50, 9), color=11, rows_m1=rows_m1, stride_word=0x18)


def test_fuzz():
    rng = random.Random(0xB117)
    for i in range(4000):
        fine_x = rng.randrange(16)
        # Bias the aligned column across the whole dispatch: clipped-left, left-edge, base,
        # right-edge, clipped-right. `col` is a signed multiple of 8 (column granularity).
        col = rng.choice([
            rng.randrange(-40, -8) & ~7,       # clipped left
            -8,                                # left edge (the one reachable LEFT case)
            rng.randrange(0, 0x98) & ~7,       # base
            0x98,                              # right edge
            rng.randrange(0xa0, 0x140) & ~7,   # clipped right
        ])
        x = _x_for(col, fine_x)
        color = rng.randrange(16)
        rows_m1 = rng.randrange(0, 20)
        # Signed stride bounded so a1 (net (8 - stride)/row) stays inside the staged src arena
        # across all rows — real sprites keep a1 in bounds; this is not the emu's OOB path.
        stride = rng.randint(-0x400, 0x400) & 0xffff
        _check(seed=i, x=x, color=color, rows_m1=rows_m1, stride_word=stride)
