#!/usr/bin/env python3
"""Render a reconstructed BuggyBoy screen to a PNG by *running the recreated C*.

This is a listening tool (like sound/sound_player.py), not part of the differential
contract. It exercises the candidate `libbuggyboy.so` end to end on a real input:

  1. load + relocate BUGGYBOY.PRG into the flat image (static data: fonts, label
     strings, fill patterns are all present at their real addresses);
  2. lay the game's own buffer layout (mem_base + offsets, as `main` computes it) and
     stage the real GRAPHICS.GRA bytes where load_graphics would have put them;
  3. call the verified `g_unpack_graphics` to decode the sprite/graphic tables into buf_c;
  4. point the draw buffer (physbase_tbl[0]) at a free screen region and call the screen
     function under test (default `g_draw_leg_results`);
  5. de-interleave that 32000-byte Atari low-res framebuffer and write it as a PNG.

buf_a (the per-leg result/label strings + leg-time digits) is filled by functions not yet
reconstructed (draw_results_screen / update_highscore), so those rows render blank here —
the fills, panels, static labels and dashboard are structurally real; the buf_a text is a
known gap. See STATUS.md.

Usage: python render/render_screen.py [--leg N] [--out DIR]
"""
import ctypes
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                                   # recreate/
sys.path.insert(0, str(ROOT / "oracle"))
sys.path.insert(0, str(ROOT / "test"))
sys.path.insert(0, str(ROOT.parents[2] / "tools"))   # reverse/tools for write_png

import harness                                        # noqa: E402  (loads the candidate .so)
from extract_graphics import write_png                # noqa: E402

# ---- the game's buffer layout, exactly as `main` computes it off the big Malloc block ----
MEM_BASE = 0x20000
BUF_A    = MEM_BASE + 0x1900
BUF_B    = MEM_BASE + 0xf660
BUF_C    = MEM_BASE + 0x1c660
BUF_AUX  = MEM_BASE + 0x57000
GFX_LOAD_OFFSET = 0xc350                              # GRAPHICS.GRA lands at buf_c + this

# ---- named globals we set (mirror addrs.h) ----
A_FLIP_IDX, A_PHYSBASE_TBL = 0x18bf2, 0x18bf4
A_BUF_AUX, A_BUF_A, A_BUF_B, A_BUF_C = 0x18bf8, 0x18c00, 0x18c04, 0x18c08
A_LEG_INDEX = 0x18c38

SCREEN_BASE = 0x2000                                  # free zeroed region below LOAD_BASE (0x10000)
PLANES, PLANE_BITS = 4, 16                            # ST low-res: 4 planes interleaved word-by-word
ROW_STRIDE = 160                                      # bytes per scanline (must match buggyboy.h)
W, H = 320, 200

# Placeholder 16-colour palette: the real one is set at runtime via a Setpalette call we haven't
# reconstructed, so RGB is not authentic — but the pixel *indices* are. Legible, distinct hues so
# the screen's structure (fills / panels / dashboard) reads clearly.
PALETTE = [
    (0, 0, 0), (255, 255, 255), (204, 0, 0), (0, 170, 0),
    (0, 0, 204), (0, 204, 204), (204, 0, 204), (204, 204, 0),
    (128, 128, 128), (255, 128, 0), (255, 128, 128), (128, 255, 128),
    (128, 128, 255), (0, 96, 0), (96, 0, 0), (48, 48, 48),
]


def _decode_interleaved(image, base):
    """De-interleave a 320x200 ST low-res framebuffer into rows of palette indices (0..15).

    Each row is 20 groups of 4 words; within a group the four words are planes 0..3, MSB = leftmost
    pixel. Pixel value = bit from each plane, plane 0 the LSB of the index.
    """
    rows = []
    for y in range(H):
        row = bytearray(W)
        row_base = base + y * ROW_STRIDE
        for group in range(W // PLANE_BITS):
            words = [struct.unpack_from(">H", image, row_base + group * (PLANES * 2) + p * 2)[0]
                     for p in range(PLANES)]
            for bit in range(PLANE_BITS):
                shift = (PLANE_BITS - 1) - bit
                idx = 0
                for p in range(PLANES):
                    idx |= ((words[p] >> shift) & 1) << p
                row[group * PLANE_BITS + bit] = idx
        rows.append(row)
    return rows


def render_leg_results(leg):
    """Build the input image, run unpack + draw_leg_results, return the framebuffer image."""
    graphics = (harness.PRG.parent / "GRAPHICS.GRA").read_bytes()
    pokes = {
        A_BUF_AUX: BUF_AUX.to_bytes(4, "big"),
        A_BUF_A:   BUF_A.to_bytes(4, "big"),
        A_BUF_B:   BUF_B.to_bytes(4, "big"),
        A_BUF_C:   BUF_C.to_bytes(4, "big"),
        BUF_C + GFX_LOAD_OFFSET: graphics,
        A_FLIP_IDX: (0).to_bytes(2, "big"),
        A_PHYSBASE_TBL: SCREEN_BASE.to_bytes(4, "big"),
        A_LEG_INDEX: leg.to_bytes(2, "big"),
    }
    image = harness.make_image(pokes)
    buf = (ctypes.c_uint8 * harness.IMAGE_SIZE).from_buffer(image)

    harness._lib.g_unpack_graphics.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    harness._lib.g_unpack_graphics.restype = None
    harness._lib.g_draw_leg_results.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    harness._lib.g_draw_leg_results.restype = None

    harness._lib.g_unpack_graphics(buf)               # decode GRAPHICS.GRA -> buf_c tables
    harness._lib.g_draw_leg_results(buf)              # paint the leg-results screen
    return image


def main():
    argv = sys.argv[1:]
    leg = int(argv[argv.index("--leg") + 1]) if "--leg" in argv else 0
    outdir = Path(argv[argv.index("--out") + 1]) if "--out" in argv else ROOT.parent / "out" / "render"
    outdir.mkdir(parents=True, exist_ok=True)

    image = render_leg_results(leg)
    rows = _decode_interleaved(image, SCREEN_BASE)
    path = outdir / f"leg_results_{leg}.png"
    write_png(str(path), W, H, rows, PALETTE)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
