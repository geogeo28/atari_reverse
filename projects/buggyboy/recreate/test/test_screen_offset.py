"""Differential tests for set_screen_offset @ 0x10300 and wait_vbl_set_offset @ 0x102ee.

set_screen_offset picks this frame's road-scroll offset into buf_c: the scroll frame (0-15)
indexes the leg's 16-byte scroll table at buf_a + leg_index*0x10, and the selected byte times
0x1900 (one 40-scanline band, low word) is written to screen_offset (read by blit_road_scroll).
wait_vbl_set_offset waits 51 vblanks (XBIOS Vsync, hardware only) then falls into it. Both are
run-to-rts with no register args; the test stages buf_a + the indices and diffs the whole image.
"""
import ctypes
import random

import harness
from harness import differential, report

SET_SCREEN_OFFSET = 0x10300
WAIT_VBL_SET_OFFSET = 0x102ee

A_BUF_A, A_LEG_INDEX, A_SCROLL_FRAME, A_SCREEN_OFFSET = 0x18c00, 0x18c38, 0x18cb2, 0x18d18
BUF_A = 0x50000                # scroll table lives at buf_a + leg*0x10 (+ frame)

for name in ("g_set_screen_offset", "g_wait_vbl_set_offset"):
    fn = getattr(harness._lib, name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    fn.restype = None


def _pokes(leg, frame, seed):
    rng = random.Random(seed)
    return {
        A_BUF_A: BUF_A.to_bytes(4, "big"),
        A_LEG_INDEX: leg.to_bytes(2, "big"),
        A_SCROLL_FRAME: frame.to_bytes(2, "big"),
        A_SCREEN_OFFSET: (0x1234).to_bytes(2, "big"),   # nonzero so a step=0 clear is observable
        BUF_A: bytes(rng.randrange(256) for _ in range(0x80)),
    }


def _check(entry, glue, leg, frame, seed):
    regs = {"_pokes": _pokes(leg, frame, seed)}
    diffs, _ = differential(entry, regs, glue, poison=True)
    assert not diffs, f"entry={entry:#x} leg={leg} frame={frame} seed={seed}\n{report(diffs[:12])}"


def test_set_screen_offset():
    glue = lambda l, b: l.g_set_screen_offset(b)
    for leg in range(5):
        for frame in range(16):
            _check(SET_SCREEN_OFFSET, glue, leg, frame, seed=leg * 16 + frame)


def test_wait_vbl_set_offset():
    glue = lambda l, b: l.g_wait_vbl_set_offset(b)
    for leg in range(5):
        for frame in (0, 7, 15):
            _check(WAIT_VBL_SET_OFFSET, glue, leg, frame, seed=200 + leg * 3 + frame)
