"""Differential test for blit_obj_Ln @ 0x10bdc (clipped masked sprite column).

Verifies both the blitted pixels (whole-image diff) and the returned status register (D0).
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x10bdc
BUF = 0x8000                      # draw-buffer base in low memory (clear of the program)
A6 = BUF

harness._lib.g_blit_obj_Ln.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 7
harness._lib.g_blit_obj_Ln.restype = ctypes.c_uint32


def _run(x, width, rows_m1, fill_lo, fill_hi, buf_seed):
    """One blit case. Pokes the draw buffer with noise so masking is exercised."""
    rng = random.Random(buf_seed)
    noise = bytes(rng.randrange(256) for _ in range(0x1400))
    pokes = {0x7000: noise}                      # covers every address the blit can touch
    regs = {"d2": width & 0xffff, "d3": 0, "d4": x & 0xffff,
            "d5": fill_lo, "d6": fill_hi, "d7": rows_m1 & 0xffff,
            "a6": A6, "_pokes": pokes}
    diffs, info = differential(
        ENTRY, regs,
        lambda lib, buf: lib.g_blit_obj_Ln(buf, A6, width & 0xffff, 0, x & 0xffff,
                                           fill_lo, fill_hi, rows_m1 & 0xffff))
    label = f"x={x} width={width} rows={rows_m1 + 1}"
    assert not diffs, f"{label}\n{report(diffs[:12])}"
    # The function returns a word in D0; the high word is uncleared leftover (caller uses
    # only the low word). Full-register fidelity is settled when draw_object is ported.
    assert (info["ret"] & 0xffff) == (info["regs"]["d0"] & 0xffff), \
        f"{label}: D0.w cand={info['ret'] & 0xffff:#x} oracle={info['regs']['d0'] & 0xffff:#x}"


def test_edge_cases():
    _run(-100, 160, 0, 0xffffffff, 0x0f0f0f0f, 1)     # off the left edge (no-op)
    _run(700, 160, 3, 0xaaaaaaaa, 0x55555555, 2)      # full-width fill (edge_col >= width)
    _run(4, 160, 3, 0xffffffff, 0x12345678, 3)        # tiny x: masked edge, no interior
    _run(200, 160, 5, 0xdeadbeef, 0xcafebabe, 4)      # masked edge + interior fill


def test_fuzz():
    rng = random.Random(12)
    for i in range(1500):
        x = rng.randint(-512, 1400)
        width = rng.randint(8, 320)
        rows_m1 = rng.randint(0, 15)
        _run(x, width, rows_m1, rng.getrandbits(32), rng.getrandbits(32), i)