"""Differential test for draw_buggy @ 0x152ac (player car body + overlay + lower body).

Positions the car from the lean/crash/skid/pitch state, picks the body sprite for the current lean
from the real buggy_body_tbl, blits the body (draw_buggy_wheels for flag==0 leans, else an inline
5-cell transparency blit), then draw_buggy_hi (A2 = body dst) and draw_buggy_lo (A6 = buffer). The
three sub-draws are already verified; here the whole-image diff checks draw_buggy's positioning,
path selection, the inline blit, and the call args. hi/lo are parked in a clean bail state for most
cases (so the body/orchestration is isolated), with one case where both draw to verify A2/A6.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x152ac

A_FLIP_IDX, A_PHYSBASE, A_BUF_C = 0x18bf2, 0x18bf4, 0x18c08
A_CRASH_DISP, A_PITCH, A_SKID, A_LEAN_STATE = 0x18c68, 0x18cbe, 0x18cbc, 0x18cc2
A_SPEED_RAW, A_LEAN_ACCUM, A_LEAN_FRAME, A_HI_TBL = 0x18cf8, 0x18d10, 0x18d12, 0x17554
A_BUGGY_DRAW_FLAG, A_BUGGY_GATE, A_FG_GATE = 0x18d0e, 0x18eba, 0x18ebb
A_SPRITE_SUPPRESS, A_COLLISION_LOCK, A_WHEEL_POS = 0x18cd0, 0x18c84, 0x18cc0
A_SPIN_COUNTER, A_SPIN_RESET = 0x18d0a, 0x18cc8
LO_PIECE_TBL, LO_PIECE_IDX_TBL = 0x17746, 0x1773c

BUFFER = 0x8000                # draw buffer; dst reaches ~buffer + 0x7ca0
BUF_C = 0x20000                # body/overlay/lo sprite sources live at buf_c + 0x23000..0x37100
BUF_C_ARENA = 0x20000          # staged window offset into buf_c
BUF_C_SPAN = 0x18000

harness._lib.g_draw_buggy.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_draw_buggy.restype = None


def _pokes(seed, lean, crash, pitch, skid, overlays):
    rng = random.Random(seed)
    p = {
        BUFFER: bytes(rng.randrange(256) for _ in range(0x8000)),
        BUF_C + BUF_C_ARENA: bytes(rng.randrange(256) for _ in range(BUF_C_SPAN)),
        A_FLIP_IDX: (0).to_bytes(2, "big"),
        A_PHYSBASE: BUFFER.to_bytes(4, "big"),
        A_BUF_C: BUF_C.to_bytes(4, "big"),
        A_CRASH_DISP: (crash & 0xffff).to_bytes(2, "big"),
        A_PITCH: (pitch & 0xffff).to_bytes(2, "big"),
        A_SKID: (skid & 0xffff).to_bytes(2, "big"),
        A_LEAN_STATE: (lean & 0xffff).to_bytes(2, "big"),
        A_SPEED_RAW: (0).to_bytes(2, "big"),
        A_LEAN_ACCUM: (0).to_bytes(2, "big"),
    }
    if overlays:
        # hi draws: frame stays 8 (rate 0 -> no advance), a bounded piece list at HI_TBL+8.
        tbl = bytearray(0x20)
        tbl[8:16] = bytes([0x00, 0x00, 0x04, 0x06, 0x00, 0x10, 0x06, 0x06])
        p[A_HI_TBL] = bytes(tbl)
        p[A_LEAN_FRAME] = (8).to_bytes(2, "big")
        # lo draws: bounded piece entry, all gates open.
        p[LO_PIECE_TBL] = bytes([8, 8]) + b"".join(o.to_bytes(2, "big") for o in (0x00, 0x400, 0x10, 0x420))
        p[LO_PIECE_IDX_TBL] = (0).to_bytes(2, "big")
        p[A_WHEEL_POS] = (0).to_bytes(2, "big")
        p[A_BUGGY_DRAW_FLAG] = (1).to_bytes(2, "big")
        for a in (A_BUGGY_GATE, A_FG_GATE):
            p[a] = bytes([0])
        for a in (A_SPRITE_SUPPRESS, A_COLLISION_LOCK, A_SPIN_COUNTER):
            p[a] = (0).to_bytes(2, "big")
        p[A_SPIN_RESET] = (0).to_bytes(4, "big")
    else:
        # hi bails (rate 0 keeps frame 0 -> no draw); lo bails (draw flag 0).
        p[A_HI_TBL] = bytes([0]) + bytes(random.Random(seed + 1).randrange(256) for _ in range(0x1f))
        p[A_LEAN_FRAME] = (0).to_bytes(2, "big")
        p[A_BUGGY_DRAW_FLAG] = (0).to_bytes(2, "big")
    return p


def _check(seed, lean, crash=0, pitch=0, skid=0, overlays=False):
    regs = {"_pokes": _pokes(seed, lean, crash, pitch, skid, overlays)}
    diffs, _ = differential(ENTRY, regs, lambda l, b: l.g_draw_buggy(b), poison=True)
    assert not diffs, (f"lean={lean} crash={crash} pitch={pitch} skid={skid} overlays={overlays}\n"
                       f"{report(diffs[:16])}")


def test_simple_body():                         # flag==0 leans -> draw_buggy_wheels
    for lean in (0, 3, 5, 9, 10):
        for crash, pitch, skid in ((0, 0, 0), (0xa0, 0, 8), (0, 0x10, -8), (0x140, 0x20, 8)):
            _check(seed=lean * 4 + skid, lean=lean, crash=crash, pitch=pitch, skid=skid)


def test_complex_body():                        # flag!=0 leans -> inline 5-cell transparency blit
    for lean in (36, 40, 41):
        for crash, skid in ((0, 0), (0xa0, 8), (0x140, -8)):
            _check(seed=lean + skid, lean=lean, crash=crash, skid=skid)


def test_overlays():                            # hi + lo also draw -> verifies A2/A6 propagation
    for seed in range(4):
        _check(seed=seed, lean=0, crash=seed * 0x40, overlays=True)
