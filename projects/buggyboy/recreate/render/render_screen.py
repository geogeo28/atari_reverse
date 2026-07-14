#!/usr/bin/env python3
"""Render a reconstructed BuggyBoy screen to a PNG by *running the recreated C*.

This is a listening tool (like sound/sound_player.py), not part of the differential
contract. It exercises the candidate `libbuggyboy.so` end to end on a real input:

  1. load + relocate BUGGYBOY.PRG into the flat image (static data: fonts, label
     strings, fill patterns are all present at their real addresses);
  2. lay the game's own buffer layout (mem_base + offsets, as `main` computes it) and
     stage the real COURSES.DAT (buf_a strings) + GRAPHICS.GRA where load_graphics puts them;
  3. call the verified `g_unpack_graphics` to decode the sprite/graphic tables into buf_c;
  4. point the draw buffer (physbase_tbl[0]) at a free screen region and call the screen
     function under test (`g_draw_leg_results`, or `g_draw_results_screen` for --screen results);
  5. de-interleave that 32000-byte Atari low-res framebuffer and write it as a PNG.

Everything drawn from static data or the two data files is real. `--screen highscore` additionally
builds the game's default high-score table with the verified `g_init_scoretable`, ranks a demo
player record into it with `g_update_highscore`, then draws — so the SCORE/NAME columns fill in
with authentic data (only the single 12-byte player record is demo data).

Usage: python render/render_screen.py [--screen leg|results|highscore] [--leg N] [--out DIR]
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
A_HISCORE_POS, A_RESULTS_MODE = 0x18c9c, 0x18c9e

# Demo state for the race-end results screen (must match render/atari/main.c). mode gates the row
# count + extra block; pos gates the score line; leg selects the per-leg row-2 labels.
RESULTS_LEG, RESULTS_MODE, RESULTS_POS = 0, 0, 5

import hiscore_demo   # noqa: E402  demo high-score data (shared with gen_hiscore.py for HISCORE.BIN)

SCREEN_BASE = 0x2000                                  # free zeroed region below LOAD_BASE (0x10000)
PLANES, PLANE_BITS = 4, 16                            # ST low-res: 4 planes interleaved word-by-word
ROW_STRIDE = 160                                      # bytes per scanline (must match buggyboy.h)
W, H = 320, 200

# The game's real results-screen palette: 16 ST words (0x0RGB, 3 bits/channel) at this address,
# passed to xbios_setpalette (A0) by update_highscore. It sits inside the STATIC.BIN region, so
# the Atari shim points Setpalette straight at it. read_palette() converts it to RGB for the PNG.
PALETTE_ADDR = 0x17fc2


def read_palette(image, addr=PALETTE_ADDR):
    """16 ST palette words at `addr` -> list of (r,g,b) 0..255 (3-bit channels scaled to 8)."""
    pal = []
    for i in range(16):
        w = struct.unpack_from(">H", image, addr + i * 2)[0]
        r, g, b = (w >> 8) & 7, (w >> 4) & 7, w & 7
        pal.append((r * 255 // 7, g * 255 // 7, b * 255 // 7))
    return pal


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


def _prepared_image(state):
    """Fresh image with the buffer layout + graphics staged, unpack_graphics run, and `state`
    (extra {addr: bytes} — leg_index / mode / pos) applied. Returns (image, ctypes buf)."""
    graphics = (harness.PRG.parent / "GRAPHICS.GRA").read_bytes()
    courses = (harness.PRG.parent / "COURSES.DAT").read_bytes()   # buf_a strings live at mem_base+0x1900
    pokes = {
        A_BUF_AUX: BUF_AUX.to_bytes(4, "big"),
        A_BUF_A:   BUF_A.to_bytes(4, "big"),
        A_BUF_B:   BUF_B.to_bytes(4, "big"),
        A_BUF_C:   BUF_C.to_bytes(4, "big"),
        MEM_BASE:  courses,
        BUF_C + GFX_LOAD_OFFSET: graphics,
        A_FLIP_IDX: (0).to_bytes(2, "big"),
        A_PHYSBASE_TBL: SCREEN_BASE.to_bytes(4, "big"),
        **state,
    }
    image = harness.make_image(pokes)
    buf = (ctypes.c_uint8 * harness.IMAGE_SIZE).from_buffer(image)
    harness._lib.g_unpack_graphics.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    harness._lib.g_unpack_graphics.restype = None
    harness._lib.g_unpack_graphics(buf)               # decode GRAPHICS.GRA -> buf_c tables
    return image, buf


def render_leg_results(leg=0):
    """Build the input image, run unpack + draw_leg_results, return the framebuffer image."""
    image, buf = _prepared_image({A_LEG_INDEX: leg.to_bytes(2, "big")})
    harness._lib.g_draw_leg_results.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    harness._lib.g_draw_leg_results.restype = None
    harness._lib.g_draw_leg_results(buf)
    return image


def render_results_screen(leg=RESULTS_LEG, mode=RESULTS_MODE, pos=RESULTS_POS):
    """Build the input image, run unpack + draw_results_screen, return the framebuffer image."""
    image, buf = _prepared_image({
        A_LEG_INDEX: leg.to_bytes(2, "big"),
        A_HISCORE_POS: pos.to_bytes(2, "big"),
        A_RESULTS_MODE: mode.to_bytes(2, "big"),
    })
    harness._lib.g_draw_results_screen.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    harness._lib.g_draw_results_screen.restype = None
    harness._lib.g_draw_results_screen(buf)
    return image


def render_highscore_screen(leg=0):
    """Build the authentic high-score screen: the verified g_init_scoretable writes the game's
    default table, g_update_highscore ranks a demo player record into it, then g_draw_results_screen
    draws it — so the SCORE/NAME columns fill in with real data. Returns the framebuffer image."""
    image, buf = _prepared_image({
        A_LEG_INDEX: leg.to_bytes(2, "big"),
        hiscore_demo.A_SCORE_BCD: hiscore_demo.PLAYER,
    })
    for name in ("g_init_scoretable", "g_update_highscore", "g_draw_results_screen"):
        getattr(harness._lib, name).argtypes = [ctypes.POINTER(ctypes.c_uint8)]
        getattr(harness._lib, name).restype = None
    harness._lib.g_init_scoretable(buf)       # game's default table (scores 40000..10000)
    harness._lib.g_update_highscore(buf)      # rank + insert the player into it
    harness._lib.g_draw_results_screen(buf)
    return image


def main():
    argv = sys.argv[1:]
    screen = argv[argv.index("--screen") + 1] if "--screen" in argv else "leg"
    leg = int(argv[argv.index("--leg") + 1]) if "--leg" in argv else 0
    outdir = Path(argv[argv.index("--out") + 1]) if "--out" in argv else ROOT.parent / "out" / "render"
    outdir.mkdir(parents=True, exist_ok=True)

    if screen == "highscore":
        image = render_highscore_screen(leg)
        name = f"highscore_screen_{leg}.png"
    elif screen == "results":
        image = render_results_screen(leg)
        name = f"results_screen_{leg}.png"
    else:
        image = render_leg_results(leg)
        name = f"leg_results_{leg}.png"
    rows = _decode_interleaved(image, SCREEN_BASE)
    path = outdir / name
    write_png(str(path), W, H, rows, read_palette(image))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
