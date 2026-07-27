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
Usage: python render/atari/run_golden.py                  # all legs 0-4
       python render/atari/run_golden.py 3                # a single leg, for quick iteration
       python render/atari/run_golden.py --memsize 1      # all legs on a 1 MB machine (the memory-diet gate)
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
    GOLDEN_LEG and -DGOLDEN_BOOT_LEG both derive from the SAME `leg` — the reference and the PRG can't drift.
    ONE binary covers both machines (PERF30 C4), so the ST and STE arms build the same .PRG and differ only
    in how Hatari runs it. The env is scrubbed of a leaked GAME_STE_SELFTEST so the build is what it names."""
    env = {**os.environ,
           "GAME_PRG": GOLDEN_PRG,
           "GEN_GOLDEN": "1",
           "GOLDEN_LEG": str(leg),
           "GAME_NO_STAGE": "1",                # a harness variant stays in build/; disk/ is the play drive
           "GAME_EXTRA_CFLAGS": f"-DGOLDEN_BOOT_LEG={leg}"}
    env.pop("GAME_STE_SELFTEST", None)          # a golden is never a self-test build
    subprocess.run(["bash", str(HERE / "build_game.sh")], env=env, check=True)


def verify_leg(leg, ste=False, memsize=None):
    """Build + run leg `leg`'s GOLDEN.PRG and byte-compare its boot frame vs recreate's pipeline. ste=True
    boots the SAME binary on --machine ste --blitter. memsize selects the emulated RAM in MB (None =
    run_hatari's default). Returns True on MATCH, False on DIFF."""
    build_golden_prg(leg)
    fb = run_hatari.run(GOLDEN_PRG, machine="ste" if ste else "st", blitter=ste, memsize=memsize)
    where = "on STE (--machine ste --blitter)" if ste else "on-target road + objects + HUD"
    return run_hatari.verify_frame(
        fb, f"remaster_{'ste' if ste else 'road_hud'}_leg{leg}.png",
        f"leg {leg} {where} is byte-identical to recreate's ported pipeline",
        golden_path=BUILD / f"golden_leg{leg}.bin",
        palette_path=BUILD / f"palette_leg{leg}.bin")


def main(ste=False):
    args = sys.argv[1:]
    memsize = None
    if "--memsize" in args:
        # The 1 MB memory-diet gate. Passed through to run_hatari.run, where an explicit value WINS over
        # the RM_MEMSIZE env default — so `--memsize 1` means 1 MB whatever the environment says.
        i = args.index("--memsize")
        if i + 1 >= len(args):
            sys.exit("--memsize needs a value in MB (e.g. --memsize 1)")
        memsize = args[i + 1]
        if not memsize.isdigit():
            sys.exit(f"--memsize takes an integer number of MB, got {memsize!r}")
        del args[i:i + 2]
    if args:
        leg = int(args[0])
        if leg not in LEGS:
            sys.exit(f"leg {leg} outside legs 0-{NUM_LEGS - 1}")
        legs = [leg]
    else:
        legs = list(LEGS)

    results = {leg: verify_leg(leg, ste=ste, memsize=memsize) for leg in legs}

    ram = f", {memsize} MB" if memsize else ""
    print(f"\n==== {'STE ' if ste else ''}golden summary{ram} ====")
    for leg in legs:
        print(f"  leg {leg}: {'MATCH' if results[leg] else 'DIFF'}")
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
