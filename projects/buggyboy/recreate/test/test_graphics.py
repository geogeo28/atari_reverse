"""Differential test for the GRAPHICS.GRA decompressor (unpack_graphics @ 0x10620).

Verified at the checkpoint 0x10720 (before the sprite-shift builders, which are separate
functions). The buffer pointers use the game's own layout (mem_base + offsets) because
unpack_graphics relies on the relative positions — e.g. buf_b == buf_c - 0xd000.
"""
import ctypes

import harness
import emu
from harness import differential, report

harness._lib.g_unpack_graphics.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
harness._lib.g_unpack_graphics.restype = None

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