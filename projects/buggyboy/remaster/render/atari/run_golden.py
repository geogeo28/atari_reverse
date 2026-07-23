#!/usr/bin/env python3
"""run_golden.py — the frame-0 GOLDEN HARNESS for the on-target BuggyBoy game, legs 0-4.

The shipping BUGGYBOY.PRG boots into the leg select, so it has no deterministic "first painted frame"
to pin. This harness therefore builds a SEPARATE variant — GOLDEN.PRG, compiled with -DGOLDEN_BOOT_LEG=N
(the boot fast path) — that skips the leg select and starts leg N directly, drawing + dumping that
leg-start frame to C:\\SCREEN.BIN *before* any physics. For each leg 0-4 we run it headless, read the
dump back, and byte-compare it to build/golden_leg<N>.bin (recreate's g_build_road_geometry +
g_render_road + g_blit_road_scroll + g_draw_game_objects + g_draw_hud for that leg's start pose). A
MATCH proves remaster's whole render pipeline — the geometry builder, the road rasterizer, the
fine-scroll, the object tree (ground, foreground sprite, roadside object list, scaled object, player
buggy) and the HUD — cross-compiled and executed on a real 68000 core, produces the exact same pixels
as the verified recreate cores, for every leg. A per-leg PNG is also written.

The leg is a PARAMETER of both sides from ONE source: the loop variable is passed to gen_game_fixture
(GOLDEN_LEG=N -> golden_leg<N>.bin + palette_leg<N>.bin) AND to the PRG build (-DGOLDEN_BOOT_LEG=N ->
GOLDEN.PRG boots leg N via start_leg/bind_leg). The shipping BUGGYBOY.PRG still boots every leg from
ONE binary; this only adds the boot fast path. The cores don't vary with the leg, but each leg needs a
fresh gen_game_fixture (its golden render) + cross-compile + Hatari run — sequential, ~3 s/leg.

Play the shipping game (leg select, then arrow keys) with a manual run:
    bash render/atari/build_game.sh
    hatari --harddrive render/atari/disk --auto 'C:\\BUGGYBOY.PRG'
See README.
Usage: python render/atari/run_golden.py        # all legs 0-4
       python render/atari/run_golden.py 3      # a single leg, for quick iteration
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
from gen_game_fixture import NUM_LEGS                        # noqa: E402  single source of the leg count

GOLDEN_PRG = "GOLDEN.PRG"
BUILD = HERE / "build"
LEGS = range(NUM_LEGS)                                     # the legs to pin — the ONE source of the boot legs


def build_golden_prg(leg):
    """Build the GOLDEN.PRG variant booting `leg` (the boot fast path) via build_game.sh, with GEN_GOLDEN=1
    so the fixture generator also writes build/golden_leg<N>.bin + palette_leg<N>.bin (that leg's reference).
    GOLDEN_LEG and -DGOLDEN_BOOT_LEG both derive from the SAME `leg` — the reference and the PRG can't drift."""
    env = {**os.environ,
           "GAME_PRG": GOLDEN_PRG,
           "GEN_GOLDEN": "1",
           "GOLDEN_LEG": str(leg),
           "GAME_EXTRA_CFLAGS": f"-DGOLDEN_BOOT_LEG={leg}"}
    subprocess.run(["bash", str(HERE / "build_game.sh")], env=env, check=True)


def verify_leg(leg):
    """Build + run leg `leg`'s GOLDEN.PRG and byte-compare its boot frame vs recreate's pipeline.
    Returns True on MATCH, False on DIFF."""
    build_golden_prg(leg)
    fb = run_hatari.run(GOLDEN_PRG)
    return run_hatari.verify_frame(
        fb, f"remaster_road_hud_leg{leg}.png",
        f"leg {leg} on-target road + objects + HUD is byte-identical to recreate's ported pipeline",
        golden_path=BUILD / f"golden_leg{leg}.bin",
        palette_path=BUILD / f"palette_leg{leg}.bin")


def main():
    if len(sys.argv) > 1:
        leg = int(sys.argv[1])
        if leg not in LEGS:
            sys.exit(f"leg {leg} outside legs 0-{NUM_LEGS - 1}")
        legs = [leg]
    else:
        legs = list(LEGS)

    results = {leg: verify_leg(leg) for leg in legs}

    print("\n==== golden summary ====")
    for leg in legs:
        print(f"  leg {leg}: {'MATCH' if results[leg] else 'DIFF'}")
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
