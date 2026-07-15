"""Differential test for init_leg @ 0x104b8 (per-leg state initializer).

init_leg resets all per-leg state: it clears a live-state block, seeds scalar defaults, rebuilds the
checkpoint banner (draw_checkpoint_anim) and the road-scroll offset (set_screen_offset), lays out the
HUD bonus-time and score strings from const image data, clears the road-segment and object-marker
tables, then unpacks this leg's 14 roadside-object marker records and the first object-display record
from buf_a. Both sub-calls are already verified.

The const source strings (0x18136, 0x181fc) and the leg-time/score templates are real image data, so
we leave them in place. We stage the RAM the unpack loops read: buf_a (the marker records + selector
tables + object-display records) and buf_c (checkpoint-anim + set_screen_offset scratch), plus the
leg index. Fuzzed over leg 0-4 with random buf_a/buf_c noise; whole-image diff, poison on.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x104b8

A_LEG_INDEX, A_BUF_A, A_BUF_C = 0x18c38, 0x18c00, 0x18c08
A_FLIP_IDX, A_PHYSBASE = 0x18bf2, 0x18bf4

BUF_A = 0x50000
BUF_A_SPAN = 0x30000            # covers +0x5ce0 markers (+ leg*0x2000, leg<=4 -> +0x8000), +0xf2/+0x50 tables
BUF_C = 0x90000
BUF_C_SPAN = 0x40000            # draw_checkpoint_anim + set_screen_offset read/write within buf_c
BUFFER = 0x8000                 # draw buffer (set_screen_offset / checkpoint anim touch physbase)

harness._lib.g_init_leg.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_init_leg.restype = None


def _pokes(seed, leg):
    rng = random.Random(seed)
    return {
        BUF_A: bytes(rng.randrange(256) for _ in range(BUF_A_SPAN)),
        BUF_C: bytes(rng.randrange(256) for _ in range(BUF_C_SPAN)),
        BUFFER: bytes(rng.randrange(256) for _ in range(0x8000)),
        A_BUF_A: BUF_A.to_bytes(4, "big"),
        A_BUF_C: BUF_C.to_bytes(4, "big"),
        A_FLIP_IDX: (0).to_bytes(2, "big"),
        A_PHYSBASE: BUFFER.to_bytes(4, "big"),
        A_LEG_INDEX: (leg & 0xffff).to_bytes(2, "big"),
    }


def _check(seed, leg):
    regs = {"_pokes": _pokes(seed, leg)}
    diffs, _ = differential(ENTRY, regs, lambda l, b: l.g_init_leg(b), poison=True)
    assert not diffs, f"seed={seed} leg={leg}\n{report(diffs[:20])}"


def test_all_legs():
    for leg in range(5):            # leg 0 uses the long bonus-time string; legs 1-4 the short one
        for seed in range(6):
            _check(seed=leg * 6 + seed, leg=leg)
