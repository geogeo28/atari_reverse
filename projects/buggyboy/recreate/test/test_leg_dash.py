"""Differential test for init_leg_dash @ 0x12d38 (builds the per-leg dashboard graphic).

Two keyed-by-leg_index effects, both pure image transforms (no draw buffer, no input):
  1. seed the dash_marker long @ 0x18c3a from the per-leg table at buf_a + 0x7f8;
  2. expand the raw per-leg block (mem_base + leg*0x500) into buf_c + 0x11c20, doubling each
     source word pair W0,W1 into four dest words W0,W1,W1,W1.
The test stages mem_base/buf_a/buf_c source arenas + leg_index with noise and diffs the whole
image; fuzzed over the real leg range (0-4) and poison-checked.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x12d38

A_LEG_INDEX, A_DASH_MARKER = 0x18c38, 0x18c3a
A_MEM_BASE, A_BUF_A, A_BUF_C = 0x18bfc, 0x18c00, 0x18c08

MEM_BASE = 0x50000             # raw source arena; block at MEM_BASE + leg*0x500 (0x500 bytes)
MEM_SPAN = 0x2000              # covers leg<=4: 0x1400 + 0x500
BUF_A = 0x60000                # marker-seed longs at buf_a + 0x7f8
MARKER_TBL = 0x7f8
BUF_C = 0x30000                # dashboard graphic dest at buf_c + 0x11c20 (40 rows * 0xa0)
BUF_C_SPAN = 0x14000

harness._lib.g_init_leg_dash.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_init_leg_dash.restype = None


def _pokes(seed, leg):
    rng = random.Random(seed)
    return {
        MEM_BASE: bytes(rng.randrange(256) for _ in range(MEM_SPAN)),
        BUF_C: bytes(rng.randrange(256) for _ in range(BUF_C_SPAN)),
        BUF_A + MARKER_TBL: bytes(rng.randrange(256) for _ in range(0x40)),
        A_MEM_BASE: MEM_BASE.to_bytes(4, "big"),
        A_BUF_A: BUF_A.to_bytes(4, "big"),
        A_BUF_C: BUF_C.to_bytes(4, "big"),
        A_LEG_INDEX: leg.to_bytes(2, "big"),
    }


def test_init_leg_dash():
    for leg in range(5):
        for seed in range(6):
            regs = {"_pokes": _pokes(seed * 5 + leg, leg)}
            diffs, _ = differential(ENTRY, regs,
                                    lambda l, b: l.g_init_leg_dash(b), poison=True)
            assert not diffs, f"leg={leg} seed={seed}\n{report(diffs[:12])}"
