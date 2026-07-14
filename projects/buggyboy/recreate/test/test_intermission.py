"""Differential test for intermission_poll @ 0x12914 (an intermission-screen block blitter).

Despite the "poll" name it reads no input — it's a 9-entry, table-driven plain block copy from a
pre-rendered graphic in buf_c to the draw buffer (physbase_tbl[flip_idx] + 0x990). The 9-entry
control table is real image data (inline after the function); the test stages a buf_c source arena
+ dest region with noise and diffs the whole image. Fuzzed over both flip slots, poison-checked.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x12914

BUF = 0x2000                   # draw buffer; dst = BUF + 0x990 + (signed) dst_off
A_FLIP_IDX, A_PHYSBASE, A_BUF_C = 0x18bf2, 0x18bf4, 0x18c08

BUF_C = 0x40000                # buf_c base (clear of the program, dest region and stack staging)
# Source: buf_c + 0x32c80 + src_off (max 0x6ea0) + a rows*stride + width margin (recomputed per entry).
SRC_LO = BUF_C + 0x32c80
SRC_HI = BUF_C + 0x3b000
DST_LO, DST_HI = 0x1000, 0x6000            # covers BUF+0x990 +/- every (signed) dst_off + rows

harness._lib.g_intermission_poll.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_intermission_poll.restype = None


def _pokes(seed, flip):
    rng = random.Random(seed)
    return {
        DST_LO: bytes(rng.randrange(256) for _ in range(DST_HI - DST_LO)),
        SRC_LO: bytes(rng.randrange(256) for _ in range(SRC_HI - SRC_LO)),
        A_FLIP_IDX: flip.to_bytes(2, "big"),
        A_PHYSBASE + flip: BUF.to_bytes(4, "big"),
        A_BUF_C: BUF_C.to_bytes(4, "big"),
    }


def test_intermission_poll():
    for seed in range(25):
        for flip in (0, 4):
            regs = {"_pokes": _pokes(seed, flip)}
            diffs, _ = differential(ENTRY, regs,
                                    lambda l, b: l.g_intermission_poll(b), poison=True)
            assert not diffs, f"seed={seed} flip={flip}\n{report(diffs[:12])}"
