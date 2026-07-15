"""Differential test for render_road @ 0x19144 — the pseudo-3D road rasterizer (a PURE LEAF).

render_road draws the road surface one scanline at a time in seven `dbf` bands. Each scanline
reads a 32-bit *control* longword from road_width_tbl (a5) whose flag bits (btst #16..#30) pick a
16-pixel-column 4-plane blit variant: it copies road-texture columns from buf_b (a3, plus a
flag-chosen sub-region) into the on-screen road band (a2 = draw_buffer + 0x4100) and fills the road
interior / shoulders with solid plane patterns. The other tables (the a4 param stream @0x1623a and
the a6 edge table @0x15c3a) are REAL image data (small signed offsets), so we leave them in place;
they read identically on both sides. We stage only RAM state: the screen buffer, a large buf_b
noise arena (all the +offset source reads land in it), physbase/flip_idx, and the edge selector.

We steer the blits by fuzzing the control longwords: the HIGH 16 bits (the flag word) are fuzzed
freely to exercise every branch variant, while the LOW 16 bits (the per-row road half-width, which
drives a0/a2 write offsets) are kept small so all writes stay inside the staged screen buffer. The
whole image is diffed vs the Musashi oracle, with the attribution/poison pass on.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x19144

A_FLIP_IDX, A_PHYSBASE, A_BUF_B = 0x18bf2, 0x18bf4, 0x18c04
A_EDGE_SEL = 0x18c5a
A_ROAD_WIDTH_TBL = 0x18f24

# The screen: a2 = physbase[flip_idx] + 0x4100. Give margin below 0x4100 (shoulder blits write
# backward) and above (7 bands walk ~0x3c00 down, rewinding between groups). BUFFER spans the lot.
# Placed well above the game globals (~0x10000-0x1b000) so it never overlaps road_width_tbl etc.
BUFFER = 0x40000
BUFFER_SPAN = 0x14000           # covers a2's full range plus fill/shoulder reach on either side

# buf_b source arena: a1 = buf_b + fine_x (0..0xf0) + flag deltas (up to ~0xa800+0xa00) + 0x2808
# mask + a6 offset. A 0x20000 arena holds every reachable source read.
BUF_B = 0x60000
BUF_B_SPAN = 0x20000

# a5 (road_width_tbl @0x18f24) reads at most 0x60 control longs (band A's row count; the later band
# groups reset a5 and read fewer). Stage exactly that many — road_width_tbl has only 0x88 longs of
# room before the render_road code at 0x19144, so a wider poke would overwrite the code under test.
N_ROWS = 0x60

harness._lib.g_render_road.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_render_road.restype = None


def _control_long(rng, flag_mask):
    """A fuzzed control longword: random flag bits (masked to flag_mask) in the high word, a small
    road half-width in the low word (bounded so blit dst offsets stay inside the screen buffer)."""
    flags = rng.getrandbits(16) & flag_mask
    low = rng.randint(0, 0x180)          # half-width; keeps a0/a2 offsets small
    return ((flags << 16) | low) & 0xffffffff


def _pokes(seed, flag_mask):
    rng = random.Random(seed)
    p = {
        BUFFER: bytes(rng.randrange(256) for _ in range(BUFFER_SPAN)),
        BUF_B: bytes(rng.randrange(256) for _ in range(BUF_B_SPAN)),
        A_FLIP_IDX: (0).to_bytes(2, "big"),
        A_PHYSBASE: BUFFER.to_bytes(4, "big"),
        A_BUF_B: BUF_B.to_bytes(4, "big"),
        A_EDGE_SEL: (0).to_bytes(2, "big"),
    }
    p[A_ROAD_WIDTH_TBL] = b"".join(
        _control_long(rng, flag_mask).to_bytes(4, "big") for _ in range(N_ROWS))
    return p


def _check(seed, flag_mask=0xffff):
    regs = {"_pokes": _pokes(seed, flag_mask)}
    diffs, _ = differential(ENTRY, regs, lambda l, b: l.g_render_road(b),
                            poison=True, max_insns=4_000_000)
    assert not diffs, f"seed={seed} flag_mask={flag_mask:#x}\n{report(diffs[:24])}"


def test_fuzz_all_flags():
    """Broad fuzz over every flag bit combination across all seven bands."""
    for seed in range(60):
        _check(seed)


# Per-flag coverage: force one flag family at a time so each branch variant is driven, rather than
# relying on the broad fuzz to hit every rare combination.
FLAG_SPLIT = (1 << (17 - 16)) | (1 << (18 - 16)) | (1 << (19 - 16)) | (1 << (20 - 16))
FLAG_MASK_READ = (1 << (16 - 16)) | (1 << (24 - 16))
FLAG_WIDE = 1 << (23 - 16)
FLAG_SRC = (1 << (21 - 16)) | (1 << (22 - 16)) | (1 << (27 - 16)) | (1 << (28 - 16))
FLAG_SKIP = (1 << (29 - 16)) | (1 << (30 - 16))


def test_split_paths():
    for seed in range(20):
        _check(1000 + seed, flag_mask=FLAG_SPLIT | FLAG_SKIP | FLAG_SRC)


def test_wide_paths():
    for seed in range(20):
        _check(2000 + seed, flag_mask=FLAG_SPLIT | FLAG_WIDE | FLAG_SRC)


def test_mask_and_const_paths():
    for seed in range(20):
        _check(3000 + seed, flag_mask=FLAG_SPLIT | FLAG_MASK_READ | FLAG_SRC | (1 << (27 - 16)))


def test_center_run_paths():
    # split flags mostly clear -> the center-run / a6-add path in each band.
    for seed in range(20):
        _check(4000 + seed, flag_mask=FLAG_SRC | (1 << (27 - 16)) | (1 << (28 - 16)))


def test_thunk_alias():
    """0x15af6 is a 4-byte `bra.w 0x19144` thunk: entering there must match entering render_road."""
    regs = {"_pokes": _pokes(seed=0, flag_mask=0xffff)}
    diffs, _ = differential(0x15af6, regs, lambda l, b: l.g_render_road(b),
                            poison=True, max_insns=4_000_000)
    assert not diffs, f"thunk\n{report(diffs[:24])}"
