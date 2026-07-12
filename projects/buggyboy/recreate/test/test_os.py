"""Differential tests for the OS-wrapper functions — validates the trap-dispatch layer.

These wrappers enter TOS via `trap`; the oracle services the trap deterministically (os.h)
and must reach the wrapper's rts without crashing or writing the image. A green case proves
the trap layer works end to end (previously any trap jumped to the zeroed vector page).
"""
import ctypes

import harness
from harness import differential, report

harness._lib.g_xbios_setscreen.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_xbios_setscreen.restype = None
harness._lib.g_xbios_setpalette.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_xbios_setpalette.restype = None

PALETTE_PTR = 0x1e000             # scratch (below the stack guard) for the 16-word palette


def test_xbios_setpalette():
    # A0 -> palette words; the XBIOS call copies them to hardware, so no image effect.
    pokes = {PALETTE_PTR: bytes(range(32))}
    regs = {"a0": PALETTE_PTR, "_pokes": pokes}
    diffs, _ = differential(0x12eb0, regs,
                            lambda lib, buf: lib.g_xbios_setpalette(buf, PALETTE_PTR))
    assert not diffs, report(diffs[:12])


def test_xbios_setscreen():
    # Reads physbase_tbl[0] and calls Setscreen(base, base, -1) — shifter/TOS state only.
    # The value is arbitrary here: the modeled Setscreen ignores it (no image effect).
    pokes = {0x18bf4: (0x9240).to_bytes(4, "big")}   # physbase_tbl[0]
    regs = {"_pokes": pokes}
    diffs, _ = differential(0x12226, regs, lambda lib, buf: lib.g_xbios_setscreen(buf))
    assert not diffs, report(diffs[:12])