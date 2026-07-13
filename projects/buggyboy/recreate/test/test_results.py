"""Differential tests for the results-screen block blitters (draw_result_row/col @ 0x15016..).

Both copy a block from buf_c (A1 offset) to buffer[flip_idx] + D0. The harness pokes buf_c
to a scratch arena seeded with noise (the blit source) and noise across the dest region so
the copy / transparency blit is exercised against known bytes; whole-image diff.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = {"draw_result_row": 0x15016, "draw_result_col": 0x1506c}

BUF = 0x2000                   # scratch draw buffer (dst = BUF + D0.w)
DST_LO, DST_HI = 0x1000, 0x6800            # every dest byte the blit can touch (row spans ~0x3c00)
A_FLIP_IDX, A_PHYSBASE, A_BUF_C = 0x18bf2, 0x18bf4, 0x18c08

BUF_C = 0x30000                # buf_c source arena base (clear of the program and the dest noise)
SRC_SPAN = 0x15000             # covers the result blitters (A1<=0x5000 + 0x1400) and the dashboard
                               # graphic (buf_c + 0x11c20 + 40 rows * 0xa0)

for name in ENTRY:
    fn = getattr(harness._lib, "g_" + name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.c_uint32]
    fn.restype = None
harness._lib.g_draw_dashboard.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_draw_dashboard.restype = None


def _pokes(seed, flip=0):
    rng = random.Random(seed)
    dst_noise = bytes(rng.randrange(256) for _ in range(DST_HI - DST_LO))
    src_noise = bytes(rng.randrange(256) for _ in range(SRC_SPAN))
    return {
        DST_LO: dst_noise,
        A_FLIP_IDX: flip.to_bytes(2, "big"),
        A_PHYSBASE + flip: BUF.to_bytes(4, "big"),
        A_BUF_C: BUF_C.to_bytes(4, "big"),
        BUF_C: src_noise,
    }


def _check(name, d0, a1, flip, seed):
    regs = {"d0": d0 & 0xffff, "a1": a1, "_pokes": _pokes(seed, flip)}
    gfn = getattr(harness._lib, "g_" + name)
    diffs, _ = differential(ENTRY[name], regs, lambda l, b, d0=d0 & 0xffff, a1=a1: gfn(b, d0, a1))
    assert not diffs, f"{name} d0={d0} a1={a1:#x} flip={flip}\n{report(diffs[:12])}"


def test_edge_cases():
    for name in ENTRY:
        _check(name, 0, 0x1000, 0, 1)          # aligned dst, small source offset
        _check(name, -0x400, 0x2000, 4, 2)     # negative D0 sign-extend, flip slot 4


def test_fuzz_result_col():
    rng = random.Random(30)
    for i in range(300):
        _check("draw_result_col", rng.randint(-0x400, 0x400), rng.randint(0x1000, 0x5000),
               rng.choice((0, 4)), i)


def test_fuzz_result_row():
    rng = random.Random(31)
    for i in range(300):
        _check("draw_result_row", rng.randint(-0x400, 0x400), rng.randint(0x1000, 0x5000),
               rng.choice((0, 4)), i)


def test_fuzz_dashboard():
    rng = random.Random(32)
    for i in range(200):
        d0, flip = rng.randint(-0x400, 0x400) & 0xffff, rng.choice((0, 4))
        regs = {"d0": d0, "_pokes": _pokes(i, flip)}
        diffs, _ = differential(0x150a4, regs, lambda l, b, d0=d0: l.g_draw_dashboard(b, d0))
        assert not diffs, f"draw_dashboard d0={d0} flip={flip}\n{report(diffs[:12])}"
