"""Differential test for flip_screen @ 0x121f8 (double-buffer page flip).

Run-to-rts, no register args. Points the ST video-base registers ($ffff8200) at the current
physbase_tbl[flip_idx] with interrupts masked, toggles flip_idx = (flip_idx + 4) & 4, and Vsyncs
(XBIOS 0x25). The video-base write is above the image (dropped) and Vsync is hardware, so the only
observable image effect is the flip_idx toggle. The test stages flip_idx + physbase_tbl and diffs
the whole image; flip_idx is fuzzed past the real {0, 4} to exercise the (x + 4) & 4 word math.
"""
import ctypes

import harness
from harness import differential, report

ENTRY = 0x121f8

A_FLIP_IDX = 0x18bf2
A_PHYSBASE = 0x18bf4          # physbase_tbl: screen-buffer pointers indexed by flip_idx

harness._lib.g_flip_screen.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_flip_screen.restype = None


def _pokes(flip_idx):
    return {
        A_FLIP_IDX: (flip_idx & 0xffff).to_bytes(2, "big"),
        A_PHYSBASE: (0x00090000).to_bytes(4, "big") + (0x00098000).to_bytes(4, "big"),
    }


def test_flip_screen():
    for flip_idx in (0, 4, 2, 6, 0x1234, 0xfffc, 0x8000):
        regs = {"_pokes": _pokes(flip_idx)}
        diffs, _ = differential(ENTRY, regs, lambda l, b: l.g_flip_screen(b), poison=True,
                                hw_waiver=harness.HW_STUBBED_BY_OS_C)
        assert not diffs, f"flip_idx={flip_idx:#x}\n{report(diffs[:12])}"
