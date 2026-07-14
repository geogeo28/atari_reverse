"""Differential tests for the masked buggy / foreground sprites (@ 0x1518a..).

draw_buggy_wheels is the shared blit body (A0 dst, A1 src, D4 rows-1): four transparency
cells per row, walking one scanline up per row. Whole-image diff against the oracle.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY_WHEELS = 0x151f6

DST = 0x9000                   # dst base; the sprite walks up to DST - rows*0xa0
SRC = 0x40000                  # src base (stands in for a buf_c sprite); also walks up
DST_LO, DST_HI = 0x6000, 0x9200
SRC_LO, SRC_HI = 0x3d000, 0x40200
ROW_UP = 0xa0

harness._lib.g_draw_buggy_wheels.argtypes = [ctypes.POINTER(ctypes.c_uint8)] + [ctypes.c_uint32] * 3
harness._lib.g_draw_buggy_wheels.restype = None


def _pokes(seed):
    rng = random.Random(seed)
    return {
        DST_LO: bytes(rng.randrange(256) for _ in range(DST_HI - DST_LO)),
        SRC_LO: bytes(rng.randrange(256) for _ in range(SRC_HI - SRC_LO)),
    }


def _run(dst, src, rows_m1, seed):
    regs = {"a0": dst, "a1": src, "d4": rows_m1 & 0xffff, "_pokes": _pokes(seed)}
    lib = harness._lib
    diffs, _ = differential(ENTRY_WHEELS, regs,
                            lambda l, b, d=dst, s=src, r=rows_m1 & 0xffff: lib.g_draw_buggy_wheels(b, d, s, r))
    assert not diffs, f"dst={dst:#x} src={src:#x} rows={rows_m1 + 1}\n{report(diffs[:12])}"


def test_edge_cases():
    _run(DST, SRC, 0, 1)                    # single row
    _run(DST, SRC, 40, 2)                   # tall sprite


def test_fuzz_wheels():
    rng = random.Random(50)
    for i in range(400):
        rows_m1 = rng.randint(0, 40)
        # keep the upward walk (dst/src - rows*0xa0) inside the seeded noise regions
        dst = DST - rng.randint(0, 0x100)
        src = SRC - rng.randint(0, 0x100)
        _run(dst, src, rows_m1, i)


# ---- draw_fg_sprite @ 0x1518a: spin/curve gate + anim-table lookup, falls into the blit ----

ENTRY_FG = 0x1518a
FG_BUF = 0x8000                # dst base (physbase slot); frame dst offset lands the sprite here
FG_BUF_C = 0x30000             # buf_c base; frame src offset indexes a sprite here
A_FLIP_IDX, A_PHYSBASE, A_BUF_C = 0x18bf2, 0x18bf4, 0x18c08
A_SPIN_STATE, A_ROAD_CURVE, A_ANIM_FRAME = 0x18caa, 0x18c6a, 0x18d0c
A_SPRITE_SUPPRESS, A_FG_GATE, A_FG_ANIM_TBL = 0x18cd0, 0x18ebb, 0x177a0
FRAME_ROWS_M1, FRAME_DST_OFF, FRAME_SRC_OFF = 8, 0x400, 0x2000

harness._lib.g_draw_fg_sprite.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_draw_fg_sprite.restype = None


def _fg_pokes(seed, spin_state, curve, suppress, gate):
    rng = random.Random(seed)
    entry = (FRAME_ROWS_M1.to_bytes(2, "big") + FRAME_DST_OFF.to_bytes(2, "big")
             + FRAME_SRC_OFF.to_bytes(4, "big"))
    return {
        0x7000: bytes(rng.randrange(256) for _ in range(0x1600)),        # dst noise [0x7000,0x8600)
        FG_BUF_C: bytes(rng.randrange(256) for _ in range(0x3000)),      # src noise
        A_FLIP_IDX: (0).to_bytes(2, "big"),
        A_PHYSBASE: FG_BUF.to_bytes(4, "big"),
        A_BUF_C: FG_BUF_C.to_bytes(4, "big"),
        A_FG_ANIM_TBL: entry,
        A_ANIM_FRAME: (0).to_bytes(2, "big"),
        A_SPIN_STATE: bytes([spin_state & 0xff]),
        A_ROAD_CURVE: (curve & 0xffff).to_bytes(2, "big"),
        A_SPRITE_SUPPRESS: (suppress & 0xffff).to_bytes(2, "big"),
        A_FG_GATE: bytes([gate & 0xff]),
    }


def _fg_run(label, seed, spin_state=0, curve=0, suppress=0, gate=0):
    regs = {"_pokes": _fg_pokes(seed, spin_state, curve, suppress, gate)}
    diffs, _ = differential(ENTRY_FG, regs, lambda l, b: l.g_draw_fg_sprite(b))
    assert not diffs, f"{label}\n{report(diffs[:12])}"


def test_fg_sprite():
    _fg_run("blit (not spinning)", 1, spin_state=0)
    _fg_run("blit (spinning, gentle curve)", 2, spin_state=0xff, curve=0x50)
    _fg_run("spin abort right", 3, spin_state=0xff, curve=0x200)      # sets spin_counter 0x1e
    _fg_run("spin abort left", 4, spin_state=0x80, curve=-0x200)      # sets spin_counter 0x3c
    _fg_run("suppressed (word)", 5, spin_state=0, suppress=1)
    _fg_run("suppressed (gate)", 6, spin_state=0, gate=0x80)

