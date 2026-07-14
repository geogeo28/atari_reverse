"""Differential test for draw_leg_results @ 0x125f2 (the per-leg results screen).

An orchestrator: it drives the already-verified fill/blit/text/num leaves. This test checks
the orchestration (arg values, call order, A3 chaining, loop counts, leg_index indexing) by
staging buf_a/buf_c source arenas + leg_index and diffing the whole image. No register args.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x125f2

BUF = 0x2000                   # draw buffer; the screen clear + fills span ~[BUF, BUF+0x7d00)
NOISE_LO, NOISE_HI = 0x2000, 0xa000
A_FLIP_IDX, A_PHYSBASE = 0x18bf2, 0x18bf4
A_BUF_A, A_BUF_C, A_LEG_INDEX = 0x18c00, 0x18c08, 0x18c38

BUF_C = 0x30000                # result/dashboard/num sprite arena (sources at buf_c + 0x11a30..)
BUF_C_SPAN = 0x1a000
BUF_A = 0x50000                # label/digit strings live here
LEG_DIGITS_OFF = 0x884

harness._lib.g_draw_leg_results.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_draw_leg_results.restype = None


def _pokes(seed, leg, flip):
    rng = random.Random(seed)
    pokes = {
        NOISE_LO: bytes(rng.randrange(256) for _ in range(NOISE_HI - NOISE_LO)),
        A_FLIP_IDX: flip.to_bytes(2, "big"),
        A_PHYSBASE + flip: BUF.to_bytes(4, "big"),
        A_BUF_C: BUF_C.to_bytes(4, "big"),
        BUF_C: bytes(rng.randrange(256) for _ in range(BUF_C_SPAN)),
        A_BUF_A: BUF_A.to_bytes(4, "big"),
        BUF_A + 0x800: bytes(rng.randrange(256) for _ in range(0x100)),
        A_LEG_INDEX: leg.to_bytes(2, "big"),
        # A bounded digit string for draw_num_thunk (digits index a bounded glyph-offset table).
        BUF_A + LEG_DIGITS_OFF + leg * 0xc: bytes([1, 2, 3, 0]),
    }
    return pokes


def test_leg_results():
    for i, leg in enumerate((0, 1, 2, 4)):
        for flip in (0, 4):
            regs = {"_pokes": _pokes(i * 2 + flip, leg, flip)}
            diffs, _ = differential(ENTRY, regs, lambda l, b: l.g_draw_leg_results(b))
            assert not diffs, f"leg={leg} flip={flip}\n{report(diffs[:12])}"
