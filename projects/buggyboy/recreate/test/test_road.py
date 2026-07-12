"""Differential test for build_road_geometry @ 0x11f4c (pure perspective-table math)."""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x11f4c

harness._lib.g_build_road_geometry.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_build_road_geometry.restype = None

VIEW_FLAGS = (0, 2, 4, 6)          # first-loop count = (6 - view_flags) >> 1 stays small/valid


def _w16(v):
    return (v & 0xffff).to_bytes(2, "big")


def _w32(v):
    return (v & 0xffffffff).to_bytes(4, "big")


def _pokes(rng):
    p = {}
    p[0x18d1c] = b"".join(_w16(rng.randint(-0x4000, 0x4000)) for _ in range(13))  # road_seg_data[0..12]
    # wide range so the 16-bit slope accumulator overflows past 0xffff and must wrap
    p[0x18c56] = _w16(rng.choice(VIEW_FLAGS))                                   # view_flags
    p[0x18c6a] = _w16(rng.randint(-3000, 3000))                                 # road_curve
    p[0x1905e] = _w16(rng.randint(-600, 600))                                   # horizon
    for i in range(106):                                                        # road_curve_tbl (RMW)
        p[0x18efc + 4 * i] = _w32(rng.randint(-2000, 2000))
    for i in range(14):                                                         # road_width_src
        p[0x18d5a + 0x20 * i] = _w16(rng.randint(0, 4000))
    return p


def test_fuzz_build_road_geometry():
    rng = random.Random(12)
    for _ in range(300):
        regs = {"_pokes": _pokes(rng)}
        diffs, _ = differential(ENTRY, regs,
                                lambda lib, buf: lib.g_build_road_geometry(buf))
        assert not diffs, report(diffs[:20])