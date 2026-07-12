"""Differential tests for the screen-fill family (clear_screen / fill_* @ 0x12e38..)."""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = {
    "clear_screen": 0x12e38,
    "fill_screen":  0x12e56,
    "fill_words":   0x12e5a,
    "fill_span":    0x12e5c,
    "fill_rect":    0x12e80,
}

# Scratch draw buffer in low memory: mapped, zero-initialised, clear of the program (>=0x10000).
BUF = 0x2000

_u8p = ctypes.POINTER(ctypes.c_uint8)
for name, argc in [("clear_screen", 0), ("fill_screen", 1), ("fill_words", 2),
                   ("fill_span", 3), ("fill_rect", 4)]:
    fn = getattr(harness._lib, "g_" + name)
    fn.argtypes = [_u8p] + [ctypes.c_uint32] * argc
    fn.restype = None


def _pokes(flip, buf=BUF):
    """Point the selected physbase_tbl slot at the scratch buffer and set flip_idx."""
    return {
        0x18bf2: flip.to_bytes(2, "big"),          # flip_idx (0 or 4)
        0x18bf4 + flip: buf.to_bytes(4, "big"),     # physbase_tbl[flip] -> buffer
    }


def _run(entry, regs, glue, label):
    diffs, _ = differential(entry, regs, glue)
    assert not diffs, f"{label}\n{report(diffs)}"


def test_clear_screen():
    for flip in (0, 4):
        _run(ENTRY["clear_screen"], {"_pokes": _pokes(flip)},
             lambda lib, buf: lib.g_clear_screen(buf), f"clear_screen flip={flip}")


def test_fill_screen():
    for flip in (0, 4):
        for d1 in (0, 1, 7, 31):
            regs = {"d1": d1, "_pokes": _pokes(flip)}
            _run(ENTRY["fill_screen"], regs,
                 lambda lib, buf, d1=d1: lib.g_fill_screen(buf, d1),
                 f"fill_screen flip={flip} color={d1}")


def test_fuzz_fill_words():
    rng = random.Random(12)
    for _ in range(500):
        d1 = rng.randint(0, 31)
        d2 = rng.randint(0, 3999)                   # up to a full screen of cells
        regs = {"d1": d1, "d2": d2, "_pokes": _pokes(rng.choice((0, 4)))}
        _run(ENTRY["fill_words"], regs,
             lambda lib, buf, d1=d1, d2=d2: lib.g_fill_words(buf, d1, d2),
             f"fill_words color={d1} count={d2}")


def test_fuzz_fill_span():
    rng = random.Random(13)
    for _ in range(500):
        d0 = rng.randint(-0x1000, 0x2000)           # signed byte offset (exercise negative sign-extend)
        d1 = rng.randint(0, 31)
        d2 = rng.randint(0, 1500)                    # cells-1; buf(0x2000) + d0 + (d2+1)*8 stays in image
        regs = {"d0": d0, "d1": d1, "d2": d2, "_pokes": _pokes(0)}
        _run(ENTRY["fill_span"], regs,
             lambda lib, buf, d0=d0, d1=d1, d2=d2: lib.g_fill_span(buf, d0, d1, d2),
             f"fill_span off={d0} color={d1} count={d2}")


def test_fuzz_fill_rect():
    rng = random.Random(14)
    for _ in range(500):
        d0 = rng.randint(-0x800, 0x800)              # signed byte offset
        d1 = rng.randint(0, 31)
        d3 = rng.randint(0, 19)                      # cells per row - 1
        d4 = rng.randint(0, 40)                      # rows - 1
        regs = {"d0": d0, "d1": d1, "d3": d3, "d4": d4, "_pokes": _pokes(0)}
        _run(ENTRY["fill_rect"], regs,
             lambda lib, buf, d0=d0, d1=d1, d3=d3, d4=d4: lib.g_fill_rect(buf, d0, d1, d3, d4),
             f"fill_rect off={d0} color={d1} cells={d3+1} rows={d4+1}")