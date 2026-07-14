"""Differential test for draw_checkpoint_anim @ 0x1442c (checkpoint-banner scroll within buf_c).

Copies columns from an X-shifted source (buf_c + 0x9c40 + k*ckpt_scroll) to a fixed dest
(buf_c + 0x9c40) in three table-driven blocks: 7 groups of 1-longword columns (shift 1x), 4 of 2
(shift 2x), and one of 3 (shift 3x); each group's row count + src/dst offsets come from the real
control table at 0x17324, every row stepping 80 bytes. The test stages a buf_c arena with noise +
ckpt_scroll and diffs the whole image; scroll is swept over its per-frame (+=4) range. Poisoned.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x1442c

A_BUF_C, A_CKPT_SCROLL = 0x18c08, 0x18c72

BUF_C = 0x30000
# banner region is buf_c + 0x9c40; the control-table offsets reach [-7240, +7292] around it, plus
# up to 22 rows * 80 + 3*scroll. Stage a generous window covering both directions.
ARENA_LO = BUF_C + 0x7000
ARENA_HI = BUF_C + 0xc800

harness._lib.g_draw_checkpoint_anim.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_draw_checkpoint_anim.restype = None


def _pokes(seed, scroll):
    rng = random.Random(seed)
    return {
        ARENA_LO: bytes(rng.randrange(256) for _ in range(ARENA_HI - ARENA_LO)),
        A_BUF_C: BUF_C.to_bytes(4, "big"),
        A_CKPT_SCROLL: (scroll & 0xffff).to_bytes(2, "big"),
    }


def test_checkpoint_anim():
    for scroll in (0, 4, 8, 0x10, 0x20, 0x3c, 0x50):
        for seed in range(3):
            regs = {"_pokes": _pokes(seed * 8 + scroll, scroll)}
            diffs, _ = differential(ENTRY, regs,
                                    lambda l, b: l.g_draw_checkpoint_anim(b), poison=True)
            assert not diffs, f"scroll={scroll:#x} seed={seed}\n{report(diffs[:12])}"
