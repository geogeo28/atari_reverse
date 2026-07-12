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
harness._lib.g_gem_aes.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_gem_aes.restype = None
harness._lib.g_gem_vdi.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_gem_vdi.restype = None

PALETTE_PTR = 0x1e000             # scratch (below the stack guard) for the 16-word palette

CONTRL = 0x19a58                  # contrl[0]: the AES/VDI opcode (shared block; = aesvdi_contrl)
INTOUT = 0x19c8c                  # intout[0]: where AES/VDI results land (shared block)


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


def _poke_contrl(opcode):
    """Set contrl[0] (the AES/VDI opcode) — the game normally does this before the trap."""
    return {CONTRL: opcode.to_bytes(2, "big")}


def test_gem_aes_appl_init():
    # appl_init (opcode 10) writes ap_id (=0) to intout[0]; a clean trap #2 with no other effect.
    diffs, _ = differential(0x100dc, {"_pokes": _poke_contrl(10)},
                            lambda lib, buf: lib.g_gem_aes(buf))
    assert not diffs, report(diffs[:12])


def test_gem_aes_graf_handle():
    # graf_handle (opcode 77) returns the physical VDI handle + font cell sizes in intout[0..4].
    pokes = _poke_contrl(77)
    diffs, _ = differential(0x100dc, {"_pokes": pokes}, lambda lib, buf: lib.g_gem_aes(buf))
    assert not diffs, report(diffs[:12])
    # os_gem_trap writes the image directly (not via the logged m68k path), so read the modeled
    # values back from the oracle's final image to pin them against an os.h regression.
    mem, _, _ = emu.run(harness.make_image(pokes), 0x100dc)
    assert int.from_bytes(mem[INTOUT:INTOUT + 2], "big") == 1, "intout[0] should be VDI handle 1"
    assert int.from_bytes(mem[INTOUT + 2:INTOUT + 4], "big") == 8, "intout[1] should be 8px cell width"


def test_gem_vdi_v_opnvwk():
    # v_opnvwk (opcode 100) fills work_out; we model the two determinate low-res fields:
    # intout[0] = max x = 319, intout[1] = max y = 199.
    pokes = _poke_contrl(100)
    diffs, _ = differential(0x100ea, {"_pokes": pokes}, lambda lib, buf: lib.g_gem_vdi(buf))
    assert not diffs, report(diffs[:12])
    mem, _, _ = emu.run(harness.make_image(pokes), 0x100ea)
    assert int.from_bytes(mem[INTOUT:INTOUT + 2], "big") == 319, "work_out[0] should be max x 319"
    assert int.from_bytes(mem[INTOUT + 2:INTOUT + 4], "big") == 199, "work_out[1] should be max y 199"


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