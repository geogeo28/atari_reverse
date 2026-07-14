"""Differential test for draw_leg_labels @ 0x12d88 (per-leg dashboard labels + probe_collision).

Run-to-rts, no register args. Reads two per-leg records from buf_a:
  - a label descriptor (buf_a + 0x8c0 + leg*16): word dst offset then glyph byte-pairs (c1,c2)
    ending on a 0 byte; each pair AND/OR-blits an 8-row cell into the dashboard graphic in buf_c;
  - a clear record (buf_a + 0x7d0 + leg*8): word dst offset + two AND masks over 4 rows.
Then it tail-calls probe_collision (which walks dash_marker via the real probe table). The test
stages buf_a records + a buf_c noise arena + dash_marker and diffs the whole image; the glyph and
probe tables are the real image data. Fuzzed over leg 0-4, plus an empty-label edge case.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x12d88

A_LEG_INDEX, A_DASH_MARKER = 0x18c38, 0x18c3a
A_BUF_A, A_BUF_C = 0x18c00, 0x18c08

BUF_A = 0x50000
BUF_C = 0x30000
LABEL_DESC_TBL, LABEL_CLEAR_TBL = 0x8c0, 0x7d0
GFX_LO, GFX_HI = BUF_C + 0x10000, BUF_C + 0x14000   # dashboard arena around buf_c + 0x11c20

harness._lib.g_draw_leg_labels.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_draw_leg_labels.restype = None


def _record(rng, npairs):
    desc = rng.randint(0, 0x400).to_bytes(2, "big")            # word dst offset
    for _ in range(npairs):
        desc += bytes([rng.randint(1, 255), rng.randint(0, 255)])   # (c1 != 0, c2)
    desc += b"\x00"                                            # terminator
    clear = (rng.randint(0, 0x400).to_bytes(2, "big")
             + rng.randint(0, 0xffff).to_bytes(2, "big")
             + rng.randint(0, 0xffff).to_bytes(2, "big"))
    return desc, clear


def _pokes(seed, leg, npairs):
    rng = random.Random(seed)
    desc, clear = _record(rng, npairs)
    return {
        A_BUF_A: BUF_A.to_bytes(4, "big"),
        A_BUF_C: BUF_C.to_bytes(4, "big"),
        A_LEG_INDEX: leg.to_bytes(2, "big"),
        GFX_LO: bytes(rng.randrange(256) for _ in range(GFX_HI - GFX_LO)),
        BUF_A + LABEL_DESC_TBL + leg * 0x10: desc,
        BUF_A + LABEL_CLEAR_TBL + leg * 8: clear,
        A_DASH_MARKER: bytes([rng.randint(0, 0xf0), rng.randint(0, 15)])
                       + rng.randint(0, 0x400).to_bytes(2, "big"),
    }


def _check(seed, leg, npairs):
    regs = {"_pokes": _pokes(seed, leg, npairs)}
    diffs, _ = differential(ENTRY, regs, lambda l, b: l.g_draw_leg_labels(b), poison=True)
    assert not diffs, f"leg={leg} npairs={npairs} seed={seed}\n{report(diffs[:12])}"


def test_empty_labels():
    for leg in range(5):
        _check(seed=leg, leg=leg, npairs=0)      # descriptor is just [dst_off][00]


def test_fuzz():
    for leg in range(5):
        for seed in range(8):
            _check(seed=100 + leg * 8 + seed, leg=leg, npairs=random.Random(seed).randint(1, 5))
