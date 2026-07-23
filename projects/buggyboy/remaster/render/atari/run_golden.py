#!/usr/bin/env python3
"""run_golden.py — the frame-0 GOLDEN HARNESS for the on-target BuggyBoy game.

The shipping BUGGYBOY.PRG boots into the leg select, so it has no deterministic "first painted frame"
to pin. This harness therefore builds a SEPARATE variant — GOLDEN.PRG, compiled with -DGOLDEN_BOOT_LEG=0
(the boot fast path) — that skips the leg select and starts leg 0 directly, drawing + dumping that
leg-start frame to C:\\SCREEN.BIN *before* any physics. We run it headless, read the dump back, and
byte-compare it to build/golden.bin (recreate's g_build_road_geometry + g_render_road +
g_blit_road_scroll + g_draw_game_objects + g_draw_hud for the same pose). A MATCH proves remaster's
whole render pipeline — the geometry builder, the road rasterizer, the fine-scroll, the object tree
(ground, foreground sprite, roadside object list, scaled object, player buggy) and the HUD —
cross-compiled and executed on a real 68000 core, produces the exact same pixels as the verified
recreate cores. A PNG is also written.

Play the shipping game (leg select, then arrow keys) with a manual run:
    bash render/atari/build_game.sh
    hatari --harddrive render/atari/disk --auto 'C:\\BUGGYBOY.PRG'
See README.
Usage: python render/atari/run_golden.py     # builds GOLDEN.PRG itself, then verifies
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REMASTER = HERE.parents[1]
RECREATE = REMASTER.parent / "recreate"
sys.path.insert(0, str(RECREATE / "oracle"))
sys.path.insert(0, str(RECREATE / "render"))
sys.path.insert(0, str(RECREATE.parents[2] / "tools"))

import run_hatari                                          # noqa: E402  shared Hatari runner + verify_frame
from gen_game_fixture import GAME_LEG                        # noqa: E402  single source of the boot/golden leg

GOLDEN_PRG = "GOLDEN.PRG"
GOLDEN_BOOT_LEG = GAME_LEG                                 # the golden variant boots the fixture's leg


def build_golden_prg():
    """Build the GOLDEN.PRG variant (the boot fast path enabled) via build_game.sh, with GEN_GOLDEN=1
    so the fixture generator also writes build/golden.bin + palette.bin (the reference frame)."""
    env = {**os.environ,
           "GAME_PRG": GOLDEN_PRG,
           "GEN_GOLDEN": "1",
           "GAME_EXTRA_CFLAGS": f"-DGOLDEN_BOOT_LEG={GOLDEN_BOOT_LEG}"}
    subprocess.run(["bash", str(HERE / "build_game.sh")], env=env, check=True)


def main():
    build_golden_prg()
    fb = run_hatari.run(GOLDEN_PRG)
    run_hatari.verify_frame(
        fb, "remaster_road_hud_hatari.png",
        "on-target road + objects + HUD is byte-identical to recreate's ported pipeline")


if __name__ == "__main__":
    main()
