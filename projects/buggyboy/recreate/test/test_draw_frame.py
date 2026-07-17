"""Differential test for draw_frame @ 0x12e22 — the whole-frame render wrapper.

draw_frame is a pure sequential wrapper (no logic, no args): build_road_geometry, render_road,
blit_road_scroll, draw_game_objects, draw_hud — each derives its own draw buffer from physbase_tbl.
Verified by a full-rts whole-image diff vs the Musashi oracle: with one shared draw buffer and
distinct buf_a/buf_b/buf_c arenas, the frame renders identically iff draw_frame invokes the five
(already byte-for-byte verified) sub-functions in order. Most per-frame tables sit in BSS (0) so the
sub-draws do little, but every one executes end-to-end.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x12e22

A_FLIP_IDX, A_PHYSBASE = 0x18bf2, 0x18bf4
A_BUF_A, A_BUF_B, A_BUF_C = 0x18c00, 0x18c04, 0x18c08

BUFFER = 0x40000              # shared draw buffer (physbase); render_road needs room below+above 0x4100
BUF_LO = 0x38000
BUF_SPAN = 0x1c000            # 0x38000..0x54000 — clear of code (0x10000..) and the buf arenas
BUF_B = 0x60000
BUF_C = 0x80000
BUF_A = 0xa0000
ARENA_SPAN = 0x20000


def _w(v): return (v & 0xffff).to_bytes(2, "big")
def _l(v): return (v & 0xffffffff).to_bytes(4, "big")


def _pokes(seed):
    rng = random.Random(seed)
    return {
        BUF_LO: bytes(rng.randrange(256) for _ in range(BUF_SPAN)),
        BUF_B: bytes(rng.randrange(256) for _ in range(ARENA_SPAN)),
        BUF_C: bytes(rng.randrange(256) for _ in range(ARENA_SPAN)),
        BUF_A: bytes(rng.randrange(256) for _ in range(ARENA_SPAN)),
        A_FLIP_IDX: _w(0),
        A_PHYSBASE: _l(BUFFER),
        A_BUF_A: _l(BUF_A),
        A_BUF_B: _l(BUF_B),
        A_BUF_C: _l(BUF_C),
    }


def _check(seed):
    regs = {"_pokes": _pokes(seed)}
    diffs, _ = differential(ENTRY, regs, lambda lib, buf: lib.g_draw_frame(buf),
                            poison=True, max_insns=8_000_000)
    assert not diffs, f"seed={seed}\n{report(diffs[:24])}"


harness._lib.g_draw_frame.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_draw_frame.restype = None


def test_frame():
    for seed in range(8):
        _check(seed=seed)
