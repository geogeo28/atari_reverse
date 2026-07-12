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


def _run(name, x, width, rows_m1, lo, hi, seed, row_offset=0):
    entry, ret = VARIANTS[name]
    rng = random.Random(seed)
    noise = bytes(rng.randrange(256) for _ in range(0x3000))    # 0x6000..0x9000: every touched byte
    pokes = {0x6000: noise}
    args = (BUF, width & 0xffff, row_offset & 0xffff, x & 0xffff, lo, hi, rows_m1 & 0xffff)
    regs = {"a6": args[0], "d2": args[1], "d3": args[2], "d4": args[3],
            "d5": args[4], "d6": args[5], "d7": args[6], "_pokes": pokes}
    gfn = getattr(harness._lib, "g_blit_obj_" + name)
    diffs, info = differential(entry, regs, lambda lib, buf: gfn(buf, *args))
    label = f"{name} x={x} width={width} rows={rows_m1 + 1} off={row_offset}"
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
            row_offset = rng.randint(-512, 512)     # exercise sign-extended nonzero/negative D3
            _run(name, x, width, rows_m1, rng.getrandbits(32), rng.getrandbits(32), i,
                 row_offset=row_offset)


# ---- road-walk variants (blit_obj_*2): x per scanline from road_width_tbl ----

ROAD_VARIANTS = {"Ln2": 0x10cd8, "Rn2": 0x10d66, "Lf2": 0x10ece, "Rf2": 0x10f60}
ROAD_A6 = 0x4000                  # dst starts A6+0x3480 = 0x7480, steps down by width per row
ROAD_WIDTH_TBL = 0x18f24

for name in ROAD_VARIANTS:
    fn = getattr(harness._lib, "g_blit_obj_" + name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 4
    fn.restype = None


def _road_table(rng, lead, active):
    """85 flag/x-offset pairs: `lead` inactive (flag>=0), `active` active (flag<0), then end."""
    pairs = []
    for _ in range(lead):
        pairs.append((rng.randint(0, 0x7fff), rng.randint(-300, 500)))
    for _ in range(active):
        pairs.append((-1, rng.randint(-300, 500)))
    while len(pairs) < 85:
        pairs.append((rng.randint(0, 0x7fff), rng.randint(-300, 500)))
    out = bytearray()
    for flag, off in pairs:
        out += (flag & 0xffff).to_bytes(2, "big") + (off & 0xffff).to_bytes(2, "big")
    return bytes(out)


def _run_road(name, width, seed):
    rng = random.Random(seed)
    pokes = {
        0x5c00: bytes(rng.randrange(256) for _ in range(0x2000)),   # draw-buffer noise
        ROAD_WIDTH_TBL: _road_table(rng, rng.randint(0, 6), rng.randint(1, 25)),
    }
    args = (ROAD_A6, width & 0xffff, 0xaaaaaaaa, 0x55555555)
    regs = {"a6": args[0], "d2": args[1], "d5": args[2], "d6": args[3], "_pokes": pokes}
    gfn = getattr(harness._lib, "g_blit_obj_" + name)
    diffs, _ = differential(ROAD_VARIANTS[name], regs, lambda lib, buf: gfn(buf, *args))
    assert not diffs, f"{name} width={width}\n{report(diffs[:12])}"


def test_road_walk_fuzz():
    rng = random.Random(21)
    for i in range(300):
        for name in ROAD_VARIANTS:
            _run_road(name, rng.randint(8, 160), i)