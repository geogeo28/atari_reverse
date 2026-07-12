"""Differential tests for the OS-wrapper functions — validates the trap-dispatch layer.

These wrappers enter TOS via `trap`; the oracle services the trap deterministically (os.h)
and must reach the wrapper's rts without crashing or writing the image. A green case proves
the trap layer works end to end (previously any trap jumped to the zeroed vector page).
"""
import ctypes

import harness            # inserts oracle/ onto sys.path
import emu
from harness import differential, report

harness._lib.g_xbios_setscreen.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_xbios_setscreen.restype = None
harness._lib.g_xbios_setpalette.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_xbios_setpalette.restype = None
harness._lib.g_set_rez.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_set_rez.restype = None

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


def test_set_rez():
    # Stores D0.b to a config global then calls XBIOS Ikbdws (0x19), a hardware serial write.
    # Byte-exact over varied D0 confirms the reconstruction matches the modeled call.
    for mode in (0x00, 0x12, 0x15, 0x1a, 0xff, 0x142):   # high byte must be ignored (move.b)
        diffs, _ = differential(0x120f8, {"d0": mode},
                                lambda lib, buf, m=mode: lib.g_set_rez(buf, m))
        assert not diffs, f"mode={mode:#x}\n{report(diffs[:12])}"


def test_supexec_nested():
    """Supexec must run the passed routine in place and return its D0 to the caller."""
    stub = bytes.fromhex("487900010020"  # pea 0x10020 (routine)
                         "3f3c0026"       # move.w #0x26,-(sp)  (Supexec)
                         "4e4e"           # trap #14
                         "5c8f"           # addq.l #6,a7
                         "4e75")          # rts
    routine = bytes.fromhex("23fcdeadbeef0000c000"  # move.l #0xdeadbeef,(0xc000).l
                            "303c1234"              # move.w #0x1234,d0
                            "4e75")                 # rts
    img = harness.make_image({0x10000: stub, 0x10020: routine})
    mem, _, out = emu.run(img, 0x10000)
    assert mem[0xc000:0xc004] == bytes.fromhex("deadbeef"), "Supexec routine did not execute"
    assert out["d0"] & 0xffff == 0x1234, "Supexec did not return the routine's result"