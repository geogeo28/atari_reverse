"""Differential tests for the divider + text panels (draw_divider/panel2/3/5 @ 0x126e6..).

These take no register arguments: draw_divider fills a rect + two vertical lines, and each
panel draws the divider then a fixed set of ASCII labels (strings are real image data). The
harness points a physbase_tbl slot at a scratch buffer seeded with noise; whole-image diff.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = {
    "draw_divider": 0x126e6,
    "draw_panel2":  0x12780,
    "draw_panel3":  0x12758,
    "draw_panel5":  0x1271c,
}

BUF = 0x2000                   # scratch draw buffer; writes land at BUF+0x4118 .. ~BUF+0x7834
NOISE_LO, NOISE_HI = 0x6000, 0xa000
A_FLIP_IDX, A_PHYSBASE = 0x18bf2, 0x18bf4

for name in ENTRY:
    fn = getattr(harness._lib, "g_" + name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    fn.restype = None


def _pokes(seed, flip):
    rng = random.Random(seed)
    noise = bytes(rng.randrange(256) for _ in range(NOISE_HI - NOISE_LO))
    return {
        NOISE_LO: noise,
        A_FLIP_IDX: flip.to_bytes(2, "big"),
        A_PHYSBASE + flip: BUF.to_bytes(4, "big"),
    }


def _check(name, flip, seed):
    gfn = getattr(harness._lib, "g_" + name)
    diffs, _ = differential(ENTRY[name], {"_pokes": _pokes(seed, flip)}, lambda l, b: gfn(b))
    assert not diffs, f"{name} flip={flip}\n{report(diffs[:12])}"


def test_panels():
    for seed, name in enumerate(ENTRY):
        for flip in (0, 4):
            _check(name, flip, seed * 2 + flip)
