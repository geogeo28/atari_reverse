"""Differential tests for the number blitter (draw_num / draw_num_thunk @ 0x15a84).

Verifies blitted pixels (whole-image diff). draw_num sources each digit's 15-row sprite
from buf_c + num_glyph_tbl[digit]; the harness pokes buf_c to a scratch arena and fills the
reachable sprite span with noise so the AND/OR blit is exercised against known bytes.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = {"draw_num": 0x15a86, "draw_num_thunk": 0x15a84}

BUF = 0x4000                   # scratch draw buffer (dst = BUF + D0.w)
STR = 0x1000                   # scratch digit string
DST_LO, DST_HI = 0x3000, 0x5200            # every dest byte the blit can touch (pre-seeded noise)
A_FLIP_IDX, A_PHYSBASE, A_BUF_C = 0x18bf2, 0x18bf4, 0x18c08
A_NUM_GLYPH_TBL = 0x17c5e
NUM_GLYPH_BUF_OFF = 0xbb80

BUF_C = 0x30000                # digit-sprite arena base (clear of the program and the dest noise)
SPRITE_SPAN = 0xe000           # covers max num_glyph_tbl offset (~0xcb30) + 15 rows * 0xa0

# Digit indices with a defined num_glyph_tbl entry (0 terminates the string, so it is never a glyph).
DIGITS = list(range(1, 12))

harness._lib.g_draw_num.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 4
harness._lib.g_draw_num_thunk.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 3
harness._lib.g_draw_num.restype = None
harness._lib.g_draw_num_thunk.restype = None


def _pokes(seed, digits, flip=0):
    """Dest noise + digit string + physbase slot + buf_c pointer + noisy sprite arena."""
    rng = random.Random(seed)
    dst_noise = bytes(rng.randrange(256) for _ in range(DST_HI - DST_LO))
    sprite_base = BUF_C + NUM_GLYPH_BUF_OFF
    sprite_noise = bytes(rng.randrange(256) for _ in range(SPRITE_SPAN))
    return {
        DST_LO: dst_noise,
        STR: bytes(digits) + b"\0",
        A_FLIP_IDX: flip.to_bytes(2, "big"),
        A_PHYSBASE + flip: BUF.to_bytes(4, "big"),
        A_BUF_C: BUF_C.to_bytes(4, "big"),
        sprite_base: sprite_noise,
    }


def _check(name, regs, glue, label):
    diffs, _ = differential(ENTRY[name], regs, glue)
    assert not diffs, f"{label}\n{report(diffs[:12])}"


def test_edge_cases():
    lib = harness._lib
    # empty string -> no writes
    _check("draw_num", {"d0": 0, "d1": 3, "d5": 0x13, "a3": STR, "_pokes": _pokes(1, [])},
           lambda l, b: lib.g_draw_num(b, 0, 3, 0x13, STR), "draw_num empty")
    # single digit
    _check("draw_num", {"d0": 0x10, "d1": 1, "d5": 0x13, "a3": STR, "_pokes": _pokes(2, [7])},
           lambda l, b: lib.g_draw_num(b, 0x10, 1, 0x13, STR), "draw_num single")
    # count-limited: D5=2 stops after 3 digits even with a longer string
    _check("draw_num", {"d0": 0, "d1": 2, "d5": 2, "a3": STR, "_pokes": _pokes(3, [1, 2, 3, 4, 5])},
           lambda l, b: lib.g_draw_num(b, 0, 2, 2, STR), "draw_num count-limited")


def test_fuzz_draw_num():
    lib = harness._lib
    rng = random.Random(20)
    for i in range(400):
        flip = rng.choice((0, 4))
        d0 = rng.randint(-0x200, 0x200) & 0xffff
        d1 = rng.randint(0, 15)
        d5 = rng.randint(0, 0x13)
        digits = [rng.choice(DIGITS) for _ in range(rng.randint(0, 20))]
        regs = {"d0": d0, "d1": d1, "d5": d5, "a3": STR, "_pokes": _pokes(i, digits, flip)}
        _check("draw_num", regs,
               lambda l, b, d0=d0, d1=d1, d5=d5: lib.g_draw_num(b, d0, d1, d5, STR),
               f"draw_num d0={d0} d1={d1} d5={d5} flip={flip} n={len(digits)}")


def test_fuzz_draw_num_thunk():
    lib = harness._lib
    rng = random.Random(21)
    for i in range(200):
        flip = rng.choice((0, 4))
        d0 = rng.randint(-0x200, 0x200) & 0xffff
        d1 = rng.randint(0, 15)
        digits = [rng.choice(DIGITS) for _ in range(rng.randint(0, 22))]
        regs = {"d0": d0, "d1": d1, "a3": STR, "_pokes": _pokes(i, digits, flip)}
        _check("draw_num_thunk", regs,
               lambda l, b, d0=d0, d1=d1: lib.g_draw_num_thunk(b, d0, d1, STR),
               f"draw_num_thunk d0={d0} d1={d1} flip={flip} n={len(digits)}")
