"""Differential tests for the object sprite blitters (blit_obj_* @ 0x10bdc..).

Verifies blitted pixels (whole-image diff) for every variant, plus the returned status
word (D0 low word) for the two that return one (Ln, Lf).
"""
import ctypes
import random

import harness
from harness import differential, report

BUF = 0x8000                      # draw-buffer base in low memory (clear of the program)

# name -> (entry address, verify the returned status word in D0)
# Only Ln leaves a clean status word; the others' D0 is an internal leftover whose meaning
# is settled once draw_object (the caller) is verified, so we check pixels only for those.
VARIANTS = {
    "Ln": (0x10bdc, True),
    "Rn": (0x10c5a, False),
    "Lf": (0x10df4, False),
    "Rf": (0x10e64, False),
}

for name, (_entry, _ret) in VARIANTS.items():
    fn = getattr(harness._lib, "g_blit_obj_" + name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 7
    fn.restype = ctypes.c_uint32


def _run(name, x, width, rows_m1, lo, hi, seed):
    entry, ret = VARIANTS[name]
    rng = random.Random(seed)
    noise = bytes(rng.randrange(256) for _ in range(0x2000))    # 0x6800..0x8800: every touched byte
    pokes = {0x6800: noise}
    args = (BUF, width & 0xffff, 0, x & 0xffff, lo, hi, rows_m1 & 0xffff)
    regs = {"a6": args[0], "d2": args[1], "d3": args[2], "d4": args[3],
            "d5": args[4], "d6": args[5], "d7": args[6], "_pokes": pokes}
    gfn = getattr(harness._lib, "g_blit_obj_" + name)
    diffs, info = differential(entry, regs, lambda lib, buf: gfn(buf, *args))
    label = f"{name} x={x} width={width} rows={rows_m1 + 1}"
    assert not diffs, f"{label}\n{report(diffs[:12])}"
    if ret:
        assert (info["ret"] & 0xffff) == (info["regs"]["d0"] & 0xffff), \
            f"{label}: D0.w cand={info['ret'] & 0xffff:#x} oracle={info['regs']['d0'] & 0xffff:#x}"


def test_edge_cases():
    for name in VARIANTS:
        _run(name, -100, 160, 2, 0xffffffff, 0x0f0f0f0f, 1)     # off-edge regime
        _run(name, 700, 160, 3, 0xaaaaaaaa, 0x55555555, 2)      # fully inside width
        _run(name, 4, 160, 3, 0xffffffff, 0x12345678, 3)        # tiny x
        _run(name, 200, 160, 5, 0xdeadbeef, 0xcafebabe, 4)      # straddling edge


def test_fuzz():
    rng = random.Random(12)
    for i in range(600):
        for name in VARIANTS:
            x = rng.randint(-512, 1400)
            width = rng.randint(8, 320)
            rows_m1 = rng.randint(0, 15)
            _run(name, x, width, rows_m1, rng.getrandbits(32), rng.getrandbits(32), i)