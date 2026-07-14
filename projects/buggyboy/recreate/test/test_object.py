"""Differential test for draw_object @ 0x1087e (roadside-object scaler/dispatcher; A6 = buffer).

Scans road_width_tbl for the first visible row (a negative long), walks the object's consecutive
rows to compute left/right edges + scanline offsets, then dispatches to the blit_obj_* variants
(all already verified). The descriptor's high word carries flags (bit15 visible, bit14 left, bit13
right, bit12 far, bit11 scale2) and its low word the width. The test crafts road_width_tbl with a
controlled object (position, span, flags, width) + obj_shade, stages a large draw buffer, and diffs
the whole image (which includes the A_obj_* state block). Poisoned.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x1087e

A_ROAD_WIDTH_TBL = 0x18f24
A_OBJ_SHADE = 0x18c5e
ROWS = 96

BUFFER = 0x8000
BUF_SPAN = 0x8800

# descriptor high-word flag bits
VISIBLE, F_LEFT, F_RIGHT, F_FAR, F_SCALE2 = 0x8000, 0x4000, 0x2000, 0x1000, 0x0800

harness._lib.g_draw_object.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_draw_object.restype = None


def _table(row_i, n_rows, flags_hi, width):
    tbl = bytearray(ROWS * 4)                     # all 0 -> non-visible
    desc = ((VISIBLE | flags_hi) << 16) | (width & 0xffff)
    for r in range(row_i, min(row_i + n_rows, ROWS)):
        tbl[r * 4:r * 4 + 4] = desc.to_bytes(4, "big")
    return bytes(tbl)


def _pokes(seed, row_i, n_rows, flags_hi, width, shade):
    rng = random.Random(seed)
    return {
        BUFFER: bytes(rng.randrange(256) for _ in range(BUF_SPAN)),
        A_ROAD_WIDTH_TBL: _table(row_i, n_rows, flags_hi, width),
        A_OBJ_SHADE: (shade & 0xffff).to_bytes(2, "big"),
    }


def _check(seed, row_i, n_rows, flags_hi, width, shade=0):
    regs = {"a6": BUFFER, "_pokes": _pokes(seed, row_i, n_rows, flags_hi, width, shade)}
    diffs, _ = differential(ENTRY, regs, lambda l, b: l.g_draw_object(b, BUFFER), poison=True)
    assert not diffs, (f"row={row_i} n={n_rows} flags={flags_hi:#06x} width={width} shade={shade}\n"
                       f"{report(diffs[:16])}")


def test_no_object():
    _check(seed=1, row_i=0, n_rows=0, flags_hi=0, width=0)     # nothing visible -> early return


def test_near():
    for flags in (F_LEFT, F_RIGHT, F_LEFT | F_RIGHT):
        for row in (20, 40, 60):
            for w in (0x20, 0x80, -0x40):
                _check(seed=row + w, row_i=row, n_rows=1, flags_hi=flags, width=w)


def test_far():
    for flags in (F_LEFT | F_FAR, F_RIGHT | F_FAR, F_LEFT | F_RIGHT | F_FAR):
        for row in (25, 50):
            for w in (0x30, -0x20):
                _check(seed=row + w + 1, row_i=row, n_rows=2, flags_hi=flags, width=w)


def test_scale2():
    for flags in (F_LEFT | F_SCALE2, F_LEFT | F_RIGHT | F_SCALE2, F_LEFT | F_RIGHT | F_FAR | F_SCALE2):
        for shade in (0, 5, -5):
            _check(seed=shade + 3, row_i=30, n_rows=2, flags_hi=flags, width=0x40, shade=shade)


def test_multirow():
    for n in (1, 2, 3, 5):
        _check(seed=n, row_i=35, n_rows=n, flags_hi=F_LEFT | F_RIGHT, width=0x50)


def test_extreme_widths():
    # Widths near the int16 limits exercise the edge-select cmp.w/bpl (16-bit N flag) path, where a
    # naive C `<` compare would diverge from the 68000 on the wrapped subtraction.
    for w in (0x7f00, -0x7f00, 0x7fff, -0x8000, 0x4000, -0x4000):
        for flags in (F_LEFT | F_RIGHT, F_LEFT | F_RIGHT | F_FAR):
            _check(seed=w & 0xffff, row_i=30, n_rows=3, flags_hi=flags, width=w)

