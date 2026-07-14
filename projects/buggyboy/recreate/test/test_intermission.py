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


# --- draw_intermission @ 0x129ba: the scrolling between-legs screen (hi-score/times/credits) ---
# Three sections (text rows, digit sprites, credits) all scroll by the signed offset at 0x18ca8.
# The layout tables (0x1858c/0x18622) and credit strings (0x180f4) are real image data; the test
# stages the string arenas (highscore_table, buf_a) + num sprites (buf_c) + screen with noise and
# fuzzes the scroll offset (and flip slot) to exercise the on-screen / clipped / off-top branches.
DI_ENTRY = 0x129ba
DI_NOISE_LO, DI_NOISE_HI = 0x2000, 0xc000      # screen band the sections draw into
A_BUF_A, A_SCROLL = 0x18c00, 0x18ca8
DI_BUF_C, DI_BUF_C_SPAN = 0x30000, 0x1c000     # num sprites (draw_num reads buf_c)
DI_BUF_A = 0x50000
A_HSCORE_LO, A_HSCORE_HI = 0x18266, 0x1858c    # section-1 strings; stop before the layout table

harness._lib.g_draw_intermission.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_draw_intermission.restype = None


def _di_pokes(seed, scroll, flip):
    rng = random.Random(seed)
    return {
        DI_NOISE_LO: bytes(rng.randrange(256) for _ in range(DI_NOISE_HI - DI_NOISE_LO)),
        A_HSCORE_LO: bytes(rng.randrange(256) for _ in range(A_HSCORE_HI - A_HSCORE_LO)),
        A_FLIP_IDX: flip.to_bytes(2, "big"),
        A_PHYSBASE + flip: BUF.to_bytes(4, "big"),
        A_BUF_C: DI_BUF_C.to_bytes(4, "big"),
        DI_BUF_C: bytes(rng.randrange(256) for _ in range(DI_BUF_C_SPAN)),
        A_BUF_A: DI_BUF_A.to_bytes(4, "big"),
        DI_BUF_A + 0x880: bytes(rng.randrange(256) for _ in range(0x60)),   # section-2 number strings
        A_SCROLL: (scroll & 0xffff).to_bytes(2, "big"),
    }


def test_draw_intermission():
    seed = 0
    for scroll in (0, 0x20, -0x20, 0x40, -0x40, 8, -8):    # on-screen / clipped / off-top branches
        for flip in (0, 4):
            regs = {"_pokes": _di_pokes(seed, scroll, flip)}
            diffs, _ = differential(DI_ENTRY, regs, lambda l, b: l.g_draw_intermission(b))
            assert not diffs, f"scroll={scroll} flip={flip}\n{report(diffs[:12])}"
            seed += 1
