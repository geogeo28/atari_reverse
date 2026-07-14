"""Differential test for draw_ground @ 0x10ff2 (ground/horizon band fill; A6 = draw buffer).

Scans up to 13 scanline descriptors (ground_scan_tbl, stride 0x20) for a marker byte at +3: 0x1a
draws a colour gradient (1-3 solid-colour scanlines from a band record), 0x1c a solid fill (1
scanline, 2 for the nearest entry). The band offset comes from the const ground_col_offsets table
(indexed by the entry and ground_view_off) and the colours from color_pairs / band records — all
real image data. The test stages the buffer + the scan table (choosing which entry matches, which
selects the band record / lit-vs-black) + the view offset, and diffs the whole image. Poisoned.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x10ff2

A_GROUND_SCAN_TBL, A_GROUND_VIEW_OFF = 0x18d48, 0x18c58
SCAN_STRIDE, MARKER_OFF = 0x20, 3

BUFFER = 0x8000
BUF_SPAN = 0x7200               # max offset 0x6cc0 + up to 3 bands * 160 + margin

harness._lib.g_draw_ground.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_draw_ground.restype = None


def _pokes(seed, match_idx, marker, view_off):
    rng = random.Random(seed)
    pokes = {
        BUFFER: bytes(rng.randrange(256) for _ in range(BUF_SPAN)),
        A_GROUND_VIEW_OFF: (view_off & 0xffff).to_bytes(2, "big"),
    }
    # 13 descriptors: all markers neutral, except the chosen matching entry.
    for i in range(13):
        m = marker if i == match_idx else 0x00
        pokes[A_GROUND_SCAN_TBL + i * SCAN_STRIDE + MARKER_OFF] = bytes([m])
    return pokes


def _check(seed, match_idx, marker, view_off=0):
    regs = {"a6": BUFFER, "_pokes": _pokes(seed, match_idx, marker, view_off)}
    diffs, _ = differential(ENTRY, regs, lambda l, b: l.g_draw_ground(b, BUFFER), poison=True)
    assert not diffs, f"idx={match_idx} marker={marker:#x} view={view_off:#x}\n{report(diffs[:12])}"


def test_gradient():
    # match index selects the clamped d4 -> band record (0,1,2,3): i=0->rec0, 4->rec1, 8->rec2, 9->rec3.
    for i in (0, 4, 8, 9, 10, 11, 12):
        _check(seed=i, match_idx=i, marker=0x1a)


def test_solid():
    for i in (0, 4, 8, 12):           # i=0..3 lit (d4>=9); i>=4 black; i=12 draws 2 scanlines
        _check(seed=100 + i, match_idx=i, marker=0x1c)


def test_no_match():
    _check(seed=7, match_idx=-1, marker=0x1a)   # no entry matches -> no writes
