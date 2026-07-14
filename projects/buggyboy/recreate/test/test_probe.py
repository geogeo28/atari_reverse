"""Differential test for probe_collision @ 0x110a4 (advances the dashboard progress-marker).

Run-to-rts, no register args: it reads the marker record (dash_marker: y byte, bit nibble, x word),
erases the marker's current dot in the dashboard bitmap at buf_c + 0x11c22, then probes the eight
neighbour cells (the real A_probe_deltas table in the image) and moves the marker to the first cell
whose bit is set. The test stages buf_c to a noise arena + fuzzes the marker record; a random bitmap
exercises the found-and-commit path, an all-zero bitmap the no-hit path. Whole-image diff, poisoned.
"""
import ctypes
import random

import harness
from harness import differential, report

ENTRY = 0x110a4

A_BUF_C = 0x18c08
A_DASH_MARKER = 0x18c3a

BUF_C = 0x30000                # dashboard bitmap arena; marker coords are relative to buf_c + 0x11c22
GFX_LO = BUF_C + 0x11a00       # staged noise window around the origin (covers y + x +/- 160 probes)
GFX_HI = BUF_C + 0x12800

harness._lib.g_probe_collision.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_probe_collision.restype = None


def _pokes(bitmap, y, bit, x):
    return {
        A_BUF_C: BUF_C.to_bytes(4, "big"),
        GFX_LO: bitmap,
        A_DASH_MARKER: bytes([y, bit]) + (x & 0xffff).to_bytes(2, "big"),
    }


def _check(bitmap, y, bit, x, label):
    regs = {"_pokes": _pokes(bitmap, y, bit, x)}
    diffs, _ = differential(ENTRY, regs, lambda l, b: l.g_probe_collision(b), poison=True)
    assert not diffs, f"{label} y={y} bit={bit} x={x:#x}\n{report(diffs[:12])}"


def test_no_hit():
    # All-zero bitmap: no neighbour on the track, so only the current dot is (already) clear.
    zeros = bytes(GFX_HI - GFX_LO)
    for y in (0x40, 0x80):
        for bit in range(16):
            _check(zeros, y, bit, 0x400, "no_hit")


def test_fuzz():
    rng = random.Random(7)
    for _ in range(400):
        bitmap = bytes(rng.randrange(256) for _ in range(GFX_HI - GFX_LO))
        y = rng.randint(0, 0xf0)
        bit = rng.randint(0, 15)
        x = rng.randint(0, 0x400)
        _check(bitmap, y, bit, x, "fuzz")
