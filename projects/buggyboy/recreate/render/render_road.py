#!/usr/bin/env python3
"""Render render_road to a PNG from BOTH reconstruction layers and compare them.

render_road (the pseudo-3D road rasterizer @0x19144) has two independently-verified forms:
  - g_render_road          — the idiomatic proper-C default (src/road.c);
  - g_render_road_machine  — the byte-exact 1:1 machine-model anchor (src/machine/road.c).

This tool feeds BOTH the *identical* input image — the same staging the differential test uses
(the real static per-scanline param/edge tables that ship in BUGGYBOY.PRG, a textured buf_b source
arena, and a table of control longwords that drive the per-row road geometry) — runs each layer,
de-interleaves the resulting Atari low-res framebuffer to a PNG, and diffs the two pixel-for-pixel.
Because the two layers are byte-for-byte equivalent, the PNGs are identical; the diff PNG is blank.

This is a listening tool (like render_screen.py / sound_player.py), not part of the differential
contract. Its job is the two-layer EQUIVALENCE check: identical input in, pixel-for-pixel diff out.

Note on the picture: the per-scanline road geometry (road_width_src / road_seg_data) is *dynamic
game state* that game_update computes while the car drives — it is zero in a cold image. Until the
frame pipeline (game_update ...) is reconstructed, or a live frame is captured (Hatari memory dump),
there is no authentic road geometry to feed, so this tool stages a SYNTHETIC input (a ramp texture
in buf_b + a smooth width sweep). The result exercises the rasterizer and proves the two layers
agree, but it renders as flat perspective bands, not a real gameplay road. Swap in real road_width_*
state here once it is available and the same code path will draw the actual road.
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
from render_screen import read_palette                # noqa: E402  (real 16-colour game palette)

# render_road's staging (mirrors test/test_render_road.py). a2 = physbase[flip_idx] + 0x4100.
A_FLIP_IDX, A_PHYSBASE, A_BUF_B = 0x18bf2, 0x18bf4, 0x18c04
A_EDGE_SEL = 0x18c5a
A_ROAD_WIDTH_TBL = 0x18f24

SCREEN = 0x40000                 # draw buffer; the visible 320x200 frame is [SCREEN, SCREEN+32000)
BUF_B = 0x60000                  # texture source arena (a1 = buf_b + fine_x + flag deltas)
BUF_B_SPAN = 0x20000
N_ROWS = 0x60                    # control longs staged into road_width_tbl (band A's row count)

W, H, ROW_STRIDE = 320, 200, 160
ROAD_BAND_OFF = 0x4100           # a2 offset into the draw buffer (top of the on-screen road band)

# Control-longword flag bits (see include/road_bands.h). A representative set per band group so the
# render exercises the edge-split + texture-copy paths (not just flat fills), the same branches the
# differential test drives.
RR_F_SPLIT_A = 1 << 18
RR_F_SPLIT_B = 1 << 17
RR_F_SPLIT_C = 1 << 19
RR_F_SPLIT_D = 1 << 20
RR_F_SKIP_ABC = 1 << 29
RR_F_SKIP_D = 1 << 30


def _control_longs():
    """A SYNTHETIC table of N_ROWS control longwords (real road_width_tbl state is dynamic game
    state, absent from a cold image — see the module docstring). The low word is a half-width that
    sweeps wide->narrow down the band and the high word carries edge-split flags, enough to drive the
    rasterizer's texture-copy paths for the equivalence check — not an authentic road profile.
    """
    longs = []
    for row in range(N_ROWS):
        # width sweeps 0x160 (near, wide) down to 0x20 (far, narrow) across the 96-row band.
        width = 0x160 - (row * 0x140 // N_ROWS)
        flags = (RR_F_SPLIT_A | RR_F_SPLIT_B | RR_F_SPLIT_C | RR_F_SPLIT_D
                 | RR_F_SKIP_ABC | RR_F_SKIP_D)
        longs.append(((flags << 16) | (width & 0xffff)) & 0xffffffff)
    return b"".join(v.to_bytes(4, "big") for v in longs)


def _texture_ramp(n):
    """A smooth diagonal ramp so copied texture columns show visible structure (not noise)."""
    return bytes((i * 7) & 0xff for i in range(n))


def _pokes():
    return {
        SCREEN: bytes(32000),                         # black background; only render_road's output shows
        BUF_B: _texture_ramp(BUF_B_SPAN),
        A_FLIP_IDX: (0).to_bytes(2, "big"),
        A_PHYSBASE: SCREEN.to_bytes(4, "big"),
        A_BUF_B: BUF_B.to_bytes(4, "big"),
        A_EDGE_SEL: (0).to_bytes(2, "big"),
        A_ROAD_WIDTH_TBL: _control_longs(),
    }


def _render(entry_name):
    """Run one render_road layer on a fresh copy of the staged image; return the raw bytes."""
    image = harness.make_image(_pokes())
    buf = (ctypes.c_uint8 * harness.IMAGE_SIZE).from_buffer(image)
    fn = getattr(harness._lib, entry_name)
    fn.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    fn.restype = None
    fn(buf)
    return bytes(image)


def _decode(image, base):
    """De-interleave a 320x200 ST low-res framebuffer at `base` into rows of palette indices."""
    rows = []
    for y in range(H):
        row = bytearray(W)
        row_base = base + y * ROW_STRIDE
        for group in range(W // 16):
            words = [struct.unpack_from(">H", image, row_base + group * 8 + p * 2)[0] for p in range(4)]
            for bit in range(16):
                shift = 15 - bit
                idx = 0
                for p in range(4):
                    idx |= ((words[p] >> shift) & 1) << p
                row[group * 16 + bit] = idx
        rows.append(row)
    return rows


def main():
    argv = sys.argv[1:]
    outdir = Path(argv[argv.index("--out") + 1]) if "--out" in argv else ROOT.parent / "out" / "render"
    outdir.mkdir(parents=True, exist_ok=True)

    l2 = _render("g_render_road")            # idiomatic default
    l1 = _render("g_render_road_machine")    # byte-exact anchor

    pal = read_palette(l2)
    frame = SCREEN
    rows_l2 = _decode(l2, frame)
    rows_l1 = _decode(l1, frame)
    write_png(str(outdir / "road_layer2_idiomatic.png"), W, H, rows_l2, pal)
    write_png(str(outdir / "road_layer1_machine.png"), W, H, rows_l1, pal)

    # Pixel diff over the whole visible frame: red where the two layers disagree (expect none).
    ndiff = sum(1 for y in range(H) for x in range(W) if rows_l2[y][x] != rows_l1[y][x])
    diff_rows = [bytearray(rows_l2[y][x] if rows_l2[y][x] == rows_l1[y][x] else 1 for x in range(W))
                 for y in range(H)]
    diff_pal = list(pal)
    diff_pal[1] = (255, 0, 0)
    write_png(str(outdir / "road_layer_diff.png"), W, H, diff_rows, diff_pal)

    # Ground truth is the raw framebuffer bytes, not the (lossy) palette decode.
    band = slice(frame, frame + 32000)
    byte_diff = sum(1 for a, b in zip(l2[band], l1[band]) if a != b)
    print(f"wrote {outdir}/road_layer2_idiomatic.png, road_layer1_machine.png, road_layer_diff.png")
    print(f"framebuffer bytes differing between layers: {byte_diff}  (pixels: {ndiff})")
    print("LAYERS IDENTICAL" if byte_diff == 0 else "LAYERS DIFFER")


if __name__ == "__main__":
    main()
