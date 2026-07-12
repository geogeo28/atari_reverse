"""Differential test for the GRAPHICS.GRA decompressor (unpack_graphics @ 0x10620).

Verified at the checkpoint 0x10720 (before the sprite-shift builders, which are separate
functions). The buffer pointers use the game's own layout (mem_base + offsets) because
unpack_graphics relies on the relative positions — e.g. buf_b == buf_c - 0xd000.
"""
import ctypes
import random

import harness
import emu
from harness import differential, report

harness._lib.g_unpack_graphics.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_unpack_graphics.restype = None
harness._lib.g_build_sprite_shifts.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32]
harness._lib.g_build_sprite_shifts.restype = None
harness._lib.g_build_sprite_shifts_msk.argtypes = [ctypes.POINTER(ctypes.c_uint8),
                                                    ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_build_sprite_shifts_msk.restype = None

MEM_BASE = 0x20000               # scratch big-block base (fits program + buffers under 1 MiB)
BUF_AUX = MEM_BASE + 0x57000     # as main computes them; the offsets are load-bearing here
BUF_B = MEM_BASE + 0xf660
BUF_C = MEM_BASE + 0x1c660
GFX_LOAD_OFFSET = 0xc350         # GRAPHICS.GRA sits at buf_c + this (where load_graphics put it)
A_BUF_AUX, A_BUF_B, A_BUF_C = 0x18bf8, 0x18c04, 0x18c08
UNPACK_CKPT = 0x10720            # `move.w #0xcf,d5` — right before bsr build_sprite_shifts
UNPACK_INSNS = 3_000_000         # data-heavy (RLE fills + a 256 KB shift + 8x de-interleave)


def test_unpack_graphics():
    graphics = (harness.PRG.parent / "GRAPHICS.GRA").read_bytes()
    pokes = {A_BUF_AUX: BUF_AUX.to_bytes(4, "big"),
             A_BUF_B: BUF_B.to_bytes(4, "big"),
             A_BUF_C: BUF_C.to_bytes(4, "big"),
             BUF_C + GFX_LOAD_OFFSET: graphics}
    diffs, _ = differential(0x10620, {"_pokes": pokes},
                            lambda lib, buf: lib.g_unpack_graphics(buf),
                            stop_pc=UNPACK_CKPT, max_insns=UNPACK_INSNS)
    assert not diffs, report(diffs[:12])
    # Sanity: the decode produced pixel data at buf_c (guards against a no-op that would also
    # match if both sides did nothing).
    mem, _, _ = emu.run(harness.make_image(pokes), 0x10620, stop_pc=UNPACK_CKPT, max_insns=UNPACK_INSNS)
    assert any(mem[BUF_C:BUF_C + 32000]), "decoded screen 0 should not be all-zero"


# --- sprite pre-shift builders (build_sprite_shifts @0x1078c, _msk @0x107f2) ---
SPR_BUF_AUX = 0x60000            # scratch; sprite source lives at +28000
SPR_BUF_B = 0x40000              # scratch; shift tables written here (well clear of buf_aux)
SPRITE_SRC_OFF = 28000           # buf_aux + this = the sprite source (== the header stash)


def _sprite_pokes(src_bytes):
    """Point buf_aux/buf_b at scratch and lay fuzzed sprite source at buf_aux+28000."""
    return {A_BUF_AUX: SPR_BUF_AUX.to_bytes(4, "big"),
            A_BUF_B: SPR_BUF_B.to_bytes(4, "big"),
            SPR_BUF_AUX + SPRITE_SRC_OFF: src_bytes}


def test_build_sprite_shifts():
    # count+1 sprites, 16 bytes of source each -> 256 bytes of shift table each (asr.l steps).
    for count in (0, 3, 0xcf):
        src = random.Random(count).randbytes((count + 1) * 16)
        diffs, _ = differential(0x1078c, {"d5": count, "_pokes": _sprite_pokes(src)},
                                lambda lib, buf, c=count: lib.g_build_sprite_shifts(buf, c))
        assert not diffs, f"count={count:#x}\n{report(diffs[:12])}"


def test_build_sprite_shifts_msk():
    # The exact (D0 buf_b offset, D1 source offset, D5 count-1) tuples unpack_graphics uses.
    configs = [(0x14f0, 0x140, 0x13), (0x3cf0, 0x3c0, 0x13), (0x6cf0, 0x6c0, 0x13),
               (0x94f0, 0x940, 0x13), (0x52f0, 0x520, 0x01), (0x56f0, 0x560, 0x01),
               (0xbcf0, 0xbc0, 0x13)]
    for dst_off, src_off, count in configs:
        src = random.Random(dst_off).randbytes(src_off + (count + 1) * 16)
        diffs, _ = differential(0x107f2,
                                {"d0": dst_off, "d1": src_off, "d5": count,
                                 "_pokes": _sprite_pokes(src)},
                                lambda lib, buf, a=dst_off, b=src_off, c=count:
                                    lib.g_build_sprite_shifts_msk(buf, a, b, c))
        assert not diffs, f"cfg=({dst_off:#x},{src_off:#x},{count:#x})\n{report(diffs[:12])}"