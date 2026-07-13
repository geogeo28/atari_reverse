"""Differential tests for the text glyph blitters (shared body @ 0x5a2c).

Verifies blitted pixels (whole-image diff) for the four entry points that converge on the
shared character-pair body: draw_text, draw_text_row, draw_hud_gauge0, draw_hud_bar.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = {
    "draw_text":       0x159fa,
    "draw_text_row":   0x159fc,
    "draw_hud_gauge0": 0x15a08,
    "draw_hud_bar":    0x15a24,
}

BUF = 0x4000                   # scratch draw buffer (headroom below for negative D0 offsets)
STR = 0x1000                   # scratch string area (clear of the buffer and the program)
NOISE_LO, NOISE_HI = 0x3000, 0x4a00       # every byte the blit can touch, pre-seeded with noise
A_FLIP_IDX, A_PHYSBASE = 0x18bf2, 0x18bf4

harness._lib.g_draw_text.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 3
harness._lib.g_draw_text_row.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 4
harness._lib.g_draw_hud_gauge0.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 4
harness._lib.g_draw_hud_bar.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 4
for name in ENTRY:
    getattr(harness._lib, "g_" + name).restype = None


def _pokes(seed, string, flip=0):
    """Noise across the touched buffer region + the string bytes + physbase_tbl slot."""
    rng = random.Random(seed)
    noise = bytes(rng.randrange(256) for _ in range(NOISE_HI - NOISE_LO))
    return {
        NOISE_LO: noise,
        STR: bytes(string),
        A_FLIP_IDX: flip.to_bytes(2, "big"),
        A_PHYSBASE + flip: BUF.to_bytes(4, "big"),
    }


def _string(rng, pairs, terminate=True, allow_char2_zero=True):
    """`pairs` character pairs of random bytes, then a 0 terminator (first byte) if asked.

    char1 is kept non-zero so the pair is drawn; char2 may be 0 to exercise the final-cell
    substitution (which stops the run early)."""
    out = bytearray()
    for _ in range(pairs):
        c1 = rng.randint(1, 255)
        c2 = 0 if (allow_char2_zero and rng.random() < 0.1) else rng.randint(1, 255)
        out += bytes((c1, c2))
        if c2 == 0:
            break
    if terminate:
        out += b"\0\0"
    return out


def _check(name, regs, glue, label):
    diffs, _ = differential(ENTRY[name], regs, glue)
    assert not diffs, f"{label}\n{report(diffs[:12])}"


def test_edge_cases():
    lib = harness._lib
    # empty string -> no writes
    _check("draw_text", {"d0": 0, "d1": 3, "a3": STR, "_pokes": _pokes(1, b"\0\0")},
           lambda l, b: lib.g_draw_text(b, 0, 3, STR), "draw_text empty")
    # single pair with char2 == 0 -> one final half-cell
    _check("draw_text", {"d0": 0x20, "d1": 5, "a3": STR, "_pokes": _pokes(2, bytes((0x41, 0)))},
           lambda l, b: lib.g_draw_text(b, 0x20, 5, STR), "draw_text half-cell")
    # full 20-cell run with no terminator (count-limited)
    full = bytes(v for i in range(20) for v in (0x30 + (i % 10), 0x41 + (i % 20)))
    _check("draw_text", {"d0": 8, "d1": 1, "a3": STR, "_pokes": _pokes(3, full)},
           lambda l, b: lib.g_draw_text(b, 8, 1, STR), "draw_text full")


def test_fuzz_draw_text():
    lib = harness._lib
    rng = random.Random(10)
    for i in range(400):
        flip = rng.choice((0, 4))
        d0 = rng.randint(-0x200, 0x200)
        d1 = rng.randint(0, 63)                     # >15 exercises the colour mask
        s = _string(rng, rng.randint(0, 22))
        regs = {"d0": d0 & 0xffff, "d1": d1, "a3": STR, "_pokes": _pokes(i, s, flip)}
        _check("draw_text", regs,
               lambda l, b, d0=d0 & 0xffff, d1=d1: lib.g_draw_text(b, d0, d1, STR),
               f"draw_text d0={d0} d1={d1} flip={flip}")


def test_fuzz_draw_text_row():
    lib = harness._lib
    rng = random.Random(11)
    for i in range(400):
        flip = rng.choice((0, 4))
        d0 = rng.randint(-0x200, 0x200) & 0xffff
        d1 = rng.randint(0, 63)
        d5 = rng.randint(0, 0x13)                   # caller-supplied cell count-1
        s = _string(rng, rng.randint(0, 22))
        regs = {"d0": d0, "d1": d1, "d5": d5, "a3": STR, "_pokes": _pokes(i, s, flip)}
        _check("draw_text_row", regs,
               lambda l, b, d0=d0, d1=d1, d5=d5: lib.g_draw_text_row(b, d0, d1, d5, STR),
               f"draw_text_row d0={d0} d1={d1} d5={d5} flip={flip}")


def test_fuzz_draw_hud_gauge0():
    lib = harness._lib
    rng = random.Random(12)
    for i in range(400):
        dst = rng.randint(NOISE_LO + 0x100, BUF + 0x200)     # absolute A0 into the noise region
        d1 = rng.randint(0, 63)
        d5 = rng.randint(0, 0x13)
        s = _string(rng, rng.randint(0, 22))
        regs = {"a0": dst, "d1": d1, "d5": d5, "a3": STR, "_pokes": _pokes(i, s)}
        _check("draw_hud_gauge0", regs,
               lambda l, b, dst=dst, d1=d1, d5=d5: lib.g_draw_hud_gauge0(b, dst, d1, d5, STR),
               f"draw_hud_gauge0 dst={dst:#x} d1={d1} d5={d5}")


def test_fuzz_draw_hud_bar():
    lib = harness._lib
    rng = random.Random(13)
    for i in range(400):
        dst = rng.randint(NOISE_LO + 0x100, BUF + 0x200)
        fill_lo = rng.getrandbits(32)
        fill_hi = rng.getrandbits(32)
        s = _string(rng, rng.randint(0, 22))
        regs = {"a0": dst, "d2": fill_lo, "d3": fill_hi, "a3": STR, "_pokes": _pokes(i, s)}
        _check("draw_hud_bar", regs,
               lambda l, b, dst=dst, lo=fill_lo, hi=fill_hi: lib.g_draw_hud_bar(b, dst, lo, hi, STR),
               f"draw_hud_bar dst={dst:#x} lo={fill_lo:#x} hi={fill_hi:#x}")
