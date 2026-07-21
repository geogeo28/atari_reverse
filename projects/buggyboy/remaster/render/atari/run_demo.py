#!/usr/bin/env python3
"""run_demo.py — run the interactive road + objects + HUD .PRG on headless Hatari, verify frame 1.

The demo writes its first painted frame (before any key) to C:\\SCREEN.BIN; we auto-run it headless,
read that dump back, and byte-compare it to build/golden.bin (recreate's g_build_road_geometry +
g_render_road + g_blit_road_scroll + g_draw_game_objects + g_draw_hud for the same pose). A MATCH
proves remaster's whole render pipeline — the geometry builder, the road rasterizer, the fine-scroll,
the object tree (ground, foreground sprite, roadside object list, scaled object, player buggy) and the
HUD — cross-compiled and executed on a real 68000 core, produces the exact same pixels as the verified
recreate cores. A PNG is also written.

Interactive play (arrow keys) is a manual run: `hatari --harddrive disk C:\\DEMO.PRG`. See README.
Usage: python render/atari/run_demo.py     # build_demo.sh must have run first
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REMASTER = HERE.parents[1]
RECREATE = REMASTER.parent / "recreate"
sys.path.insert(0, str(RECREATE / "oracle"))
sys.path.insert(0, str(RECREATE / "render"))
sys.path.insert(0, str(RECREATE.parents[2] / "tools"))

import run_hatari                                          # noqa: E402  shared Hatari runner + palette
from render_screen import _decode_interleaved, W, H         # noqa: E402
from extract_graphics import write_png                      # noqa: E402

BUILD = HERE / "build"
SCREEN_BASE = 0x2000
SCREEN_BYTES = W * H * 4 // 8                              # 32000


def main():
    fb = run_hatari.run("DEMO.PRG")

    outdir = RECREATE.parent / "out" / "render"
    outdir.mkdir(parents=True, exist_ok=True)
    image = bytearray(SCREEN_BASE) + fb
    rows = _decode_interleaved(image, SCREEN_BASE)
    png = outdir / "remaster_road_hud_hatari.png"
    write_png(str(png), W, H, rows, run_hatari._palette_rgb())
    print(f"wrote {png} ({len(fb)} bytes from Hatari)")

    golden = (BUILD / "golden.bin").read_bytes()
    if bytes(fb) == golden:
        print("MATCH: on-target road + objects + HUD is byte-identical to recreate's ported pipeline")
    else:
        ndiff = sum(1 for a, b in zip(fb, golden) if a != b)
        print(f"DIFF: {ndiff}/{SCREEN_BYTES} bytes differ from recreate's golden frame")
        sys.exit(1)


if __name__ == "__main__":
    main()
