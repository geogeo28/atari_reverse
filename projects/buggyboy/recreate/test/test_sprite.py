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


# ---- draw_buggy_lo @ 0x153fa: gated 2-sub-sprite lower body; A6 = draw buffer ----

ENTRY_LO = 0x153fa
LO_BUFFER = 0x8000             # A6 draw buffer base
LO_BUF_C = 0x30000
LO_SRC_OFF = 0x27100
A_BUGGY_DRAW_FLAG, A_BUGGY_GATE = 0x18d0e, 0x18eba
A_COLLISION_LOCK, A_WHEEL_POS = 0x18c84, 0x18cc0
A_SPIN_COUNTER, A_SPIN_RESET = 0x18d0a, 0x18cc8
LO_PIECE_TBL, LO_PIECE_IDX_TBL = 0x17746, 0x1773c

harness._lib.g_draw_buggy_lo.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_draw_buggy_lo.restype = None


def _lo_pokes(seed, draw_flag=1, gate=0, fg_gate=0, suppress=0, lock=0, spin_reset=0, spin_counter=0):
    rng = random.Random(seed)
    # piece entry: rows0, rows1, then (src,dst) word pair per sub-sprite
    entry = bytes([8, 8]) + b"".join(
        off.to_bytes(2, "big") for off in (0x00, 0x400, 0x10, 0x420))
    return {
        0x7000: bytes(rng.randrange(256) for _ in range(0x1600)),          # dst noise
        LO_BUF_C: bytes(rng.randrange(256) for _ in range(0x28000)),       # buf_c incl. +0x27100 src
        A_BUF_C: LO_BUF_C.to_bytes(4, "big"),
        A_WHEEL_POS: (0).to_bytes(2, "big"),
        LO_PIECE_IDX_TBL: (0).to_bytes(2, "big"),                          # idx_tbl[0] = 0
        LO_PIECE_TBL: entry,
        A_BUGGY_DRAW_FLAG: (draw_flag & 0xffff).to_bytes(2, "big"),
        A_BUGGY_GATE: bytes([gate & 0xff]),
        A_FG_GATE: bytes([fg_gate & 0xff]),
        A_SPRITE_SUPPRESS: (suppress & 0xffff).to_bytes(2, "big"),
        A_COLLISION_LOCK: (lock & 0xffff).to_bytes(2, "big"),
        A_SPIN_RESET: (spin_reset & 0xffffffff).to_bytes(4, "big"),
        A_SPIN_COUNTER: (spin_counter & 0xffff).to_bytes(2, "big"),
    }


def _lo_run(label, seed, **kw):
    regs = {"a6": LO_BUFFER, "_pokes": _lo_pokes(seed, **kw)}
    diffs, _ = differential(ENTRY_LO, regs, lambda l, b: l.g_draw_buggy_lo(b, LO_BUFFER))
    assert not diffs, f"{label}\n{report(diffs[:12])}"


def test_buggy_lo():
    _lo_run("draw", 1)
    _lo_run("gated: draw_flag=0", 2, draw_flag=0)
    _lo_run("gated: buggy_gate bit7", 3, gate=0x80)
    _lo_run("gated: fg_gate bit7", 4, fg_gate=0x80)
    _lo_run("gated: suppress", 5, suppress=1)
    _lo_run("gated: collision_lock", 6, lock=1)
    _lo_run("gated: spin_reset", 7, spin_reset=1)


# ---- draw_buggy_hi @ 0x154c6: lean overlay (OR-blit) with a speed-driven anim counter; A2 dst ----

ENTRY_HI = 0x154c6
HI_A2 = 0x9000                 # A2 dst base
HI_BUF_C = 0x30000
A_LEAN_STATE, A_SPEED_RAW, A_BUGGY_VARIANT = 0x18cc2, 0x18cf8, 0x18cc6
A_LEAN_ACCUM, A_LEAN_FRAME, A_HI_TBL = 0x18d10, 0x18d12, 0x17554

harness._lib.g_draw_buggy_hi.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_draw_buggy_hi.restype = None


def _hi_pokes(seed, lean_state=0, speed_raw=0, accum=0, frame=8, variant=0):
    rng = random.Random(seed)
    tbl = bytearray(rng.randrange(256) for _ in range(0x20))
    tbl[0] = 0                                    # rate for speed_raw>>5 == 0
    tbl[1] = 8                                    # rate for speed_raw>>5 == 1 (accum-step case)
    tbl[8:16] = bytes([0x00, 0x00, 0x04, 0x06,    # sub0: src=0, dst_byte=4, rows-1=6
                       0x00, 0x10, 0x06, 0x06])   # sub1: src=0x10, dst_byte=6, rows-1=6
    return {
        0x8000: bytes(rng.randrange(256) for _ in range(0x1100)),        # dst noise
        HI_BUF_C: bytes(rng.randrange(256) for _ in range(0x24000)),     # buf_c incl. +0x23280
        A_BUF_C: HI_BUF_C.to_bytes(4, "big"),
        A_HI_TBL: bytes(tbl),
        A_LEAN_STATE: (lean_state & 0xffff).to_bytes(2, "big"),
        A_SPEED_RAW: (speed_raw & 0xffff).to_bytes(2, "big"),
        A_LEAN_ACCUM: (accum & 0xffff).to_bytes(2, "big"),
        A_LEAN_FRAME: (frame & 0xffff).to_bytes(2, "big"),
        A_BUGGY_VARIANT: (variant & 0xffff).to_bytes(2, "big"),
    }


def _hi_run(label, seed, **kw):
    regs = {"a2": HI_A2, "_pokes": _hi_pokes(seed, **kw)}
    diffs, _ = differential(ENTRY_HI, regs, lambda l, b: l.g_draw_buggy_hi(b, HI_A2))
    assert not diffs, f"{label}\n{report(diffs[:12])}"


def test_buggy_hi():
    _hi_run("blit (frame preset)", 1)
    _hi_run("gated: leaning hard", 2, lean_state=0x1e)
    _hi_run("frame stays 0 -> return", 3, frame=0)
    _hi_run("accum steps frame 0->8", 4, frame=0, accum=4, speed_raw=0x20)



