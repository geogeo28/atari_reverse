"""Differential test for draw_results_screen @ 0x1225a (race-end results screen).

An orchestrator driving the fill/text/num/dashboard leaves with heavy A3 chaining and, in
row 2, A0/fill leftover threading from each label into a bar gauge. Two runtime state words
(results_mode, hiscore_pos) shape the row counts / palettes / conditional blocks; the test
sweeps both branches. Whole-image diff; only physbase, buf_a/buf_c and the state words are
staged (label strings + palettes are real image data).
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x1225a

BUF = 0x2000                   # draw buffer; fill_screen + dashboard span ~[BUF, BUF+0xa600)
NOISE_LO, NOISE_HI = 0x2000, 0xb000
A_FLIP_IDX, A_PHYSBASE = 0x18bf2, 0x18bf4
A_BUF_A, A_BUF_C = 0x18c00, 0x18c08
A_LEG_INDEX, A_HISCORE_POS, A_RESULTS_MODE = 0x18c38, 0x18c9c, 0x18c9e

BUF_C = 0x30000
BUF_C_SPAN = 0x1c000           # covers num sprites (buf_c+0xbb80) and the dashboard (buf_c+0x11c20)
BUF_A = 0x50000

harness._lib.g_draw_results_screen.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_draw_results_screen.restype = None


def _pokes(seed, leg, mode, pos, flip):
    rng = random.Random(seed)
    fin = 0x910 + leg * 0x10       # final label: [dst word][string...]
    return {
        NOISE_LO: bytes(rng.randrange(256) for _ in range(NOISE_HI - NOISE_LO)),
        A_FLIP_IDX: flip.to_bytes(2, "big"),
        A_PHYSBASE + flip: BUF.to_bytes(4, "big"),
        A_BUF_C: BUF_C.to_bytes(4, "big"),
        BUF_C: bytes(rng.randrange(256) for _ in range(BUF_C_SPAN)),
        A_BUF_A: BUF_A.to_bytes(4, "big"),
        BUF_A + 0x800: bytes(rng.randrange(256) for _ in range(0x160)),
        BUF_A + fin: bytes([0x10, 0x00, 0x41, 0x42, 0x00, 0x00]),   # dst=0x1000, "AB", terminator
        A_LEG_INDEX: leg.to_bytes(2, "big"),
        A_HISCORE_POS: pos.to_bytes(2, "big"),
        A_RESULTS_MODE: mode.to_bytes(2, "big"),
    }


def _check(seed, leg, mode, pos, flip):
    regs = {"_pokes": _pokes(seed, leg, mode, pos, flip)}
    diffs, _ = differential(ENTRY, regs, lambda l, b: l.g_draw_results_screen(b))
    assert not diffs, f"leg={leg} mode={mode} pos={pos} flip={flip}\n{report(diffs[:12])}"


def test_results_screen():
    seed = 0
    for mode in (0, 2):                    # gates row count and the extra block
        for pos in (0, 5):                 # gates the score line + palette offset
            for leg in (0, 2, 4):
                for flip in (0, 4):
                    _check(seed, leg, mode, pos, flip)
                    seed += 1
