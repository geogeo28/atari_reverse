"""Differential tests for the masked buggy / foreground sprites (@ 0x1518a..).

draw_buggy_wheels is the shared blit body (A0 dst, A1 src, D4 rows-1): four transparency
cells per row, walking one scanline up per row. Whole-image diff against the oracle.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY_WHEELS = 0x151f6

DST = 0x9000                   # dst base; the sprite walks up to DST - rows*0xa0
SRC = 0x40000                  # src base (stands in for a buf_c sprite); also walks up
DST_LO, DST_HI = 0x6000, 0x9200
SRC_LO, SRC_HI = 0x3d000, 0x40200
ROW_UP = 0xa0

harness._lib.g_draw_buggy_wheels.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 3
harness._lib.g_draw_buggy_wheels.restype = None


def _pokes(seed):
    rng = random.Random(seed)
    return {
        DST_LO: bytes(rng.randrange(256) for _ in range(DST_HI - DST_LO)),
        SRC_LO: bytes(rng.randrange(256) for _ in range(SRC_HI - SRC_LO)),
    }


def _run(dst, src, rows_m1, seed):
    regs = {"a0": dst, "a1": src, "d4": rows_m1 & 0xffff, "_pokes": _pokes(seed)}
    lib = harness._lib
    diffs, _ = differential(ENTRY_WHEELS, regs,
                            lambda l, b, d=dst, s=src, r=rows_m1 & 0xffff: lib.g_draw_buggy_wheels(b, d, s, r))
    assert not diffs, f"dst={dst:#x} src={src:#x} rows={rows_m1 + 1}\n{report(diffs[:12])}"


def test_edge_cases():
    _run(DST, SRC, 0, 1)                    # single row
    _run(DST, SRC, 40, 2)                   # tall sprite


def test_fuzz_wheels():
    rng = random.Random(50)
    for i in range(400):
        rows_m1 = rng.randint(0, 40)
        # keep the upward walk (dst/src - rows*0xa0) inside the seeded noise regions
        dst = DST - rng.randint(0, 0x100)
        src = SRC - rng.randint(0, 0x100)
        _run(dst, src, rows_m1, i)
