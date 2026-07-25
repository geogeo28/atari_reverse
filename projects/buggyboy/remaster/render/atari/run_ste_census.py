#!/usr/bin/env python3
"""run_ste_census.py — PERF30 C4 slice 5: census the DISTINCT materialise-key tuples each fine-x engine
issues over real drives, to decide whether boot pre-shift tables are FINITE.

Boot tables pre-materialise the interleaved (mask,data) bitmaps for every reachable (sprite region ×
fine_x × width × rows) combination, so a driving blit is 2 passes over static data — no per-frame
materialise. That is only viable if the reachable set is bounded. This drives each leg headless (long
GAME_AUTODRIVE) with the dispatch instrumented (src/blitter_census.c counts distinct base-family tuples
via a 65536-slot set) and reports the distinct count + base/total call counts per engine per leg. If the
distinct set is small and bounded → tables are finite (state the size). If it saturates or grows with the
drive length → measured NO-GO for full tables; the honest fallback is a hybrid (a big non-evicting cache
for the recurring set + CPU for the rest).

Usage: python render/atari/run_ste_census.py [frames]   # default 800 frames/leg, legs 0-4
"""
import os
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REMASTER = HERE.parents[1]
RECREATE = REMASTER.parent / "recreate"
sys.path.insert(0, str(RECREATE / "oracle"))
sys.path.insert(0, str(HERE))
import run_hatari                                          # noqa: E402
from gen_game_fixture import NUM_LEGS                        # noqa: E402

CENSUS_PRG = "CENSUS.PRG"


def build(leg, frames):
    env = {**os.environ, "GAME_STE": "1", "GAME_STE_CENSUS": "1", "GAME_PRG": CENSUS_PRG,
           "GOLDEN_LEG": str(leg), "GAME_EXTRA_CFLAGS": f"-DGAME_AUTODRIVE={frames} -DGOLDEN_BOOT_LEG={leg}"}
    subprocess.run(["bash", str(HERE / "build_game.sh")], env=env, check=True, stdout=subprocess.DEVNULL)


def census_leg(leg, frames):
    build(leg, frames)
    fb = run_hatari.run(CENSUS_PRG, machine="ste", blitter=True, needs_data=True,
                        run_vbls=frames * 20, timeout=300)
    w = struct.unpack(">14H", fb[:28])
    # A valid census caps `distinct` at 0xFFFF (the set holds 65536 slots), so its hi word is ALWAYS 0.
    # A nonzero hi word means the run CRASHED (autodrive off-course) before census_dump wrote the report,
    # leaving a rendered/garbage frame in SCREEN.BIN — discard it rather than treat it as data.
    crashed = w[0] != 0 or w[7] != 0
    out = {"_crashed": crashed}
    for i, name in enumerate(("objshift2", "objshift")):
        distinct = (w[i * 7 + 0] << 16) | w[i * 7 + 1]
        base = (w[i * 7 + 2] << 16) | w[i * 7 + 3]
        total = (w[i * 7 + 4] << 16) | w[i * 7 + 5]
        sat = w[i * 7 + 6]
        out[name] = (distinct, base, total, sat)
    return out


def main():
    # The headless autodrive crashes off-course past ~60 clean frames (§10), so census at a clean frame
    # count; the bounded/unbounded verdict is read off the trend, not a full-leg total.
    frames = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    print(f"=== census: {NUM_LEGS} legs x {frames} frames (RAM/entry: objshift2 ~2.75 KB, objshift ~2.05 KB) ===")
    print(f"{'leg':>3} {'engine':>10} {'distinct':>9} {'base_calls':>11} {'total_calls':>12} {'saturated':>10}")
    for leg in range(NUM_LEGS):
        res = census_leg(leg, frames)
        if res["_crashed"]:
            print(f"{leg:>3}  (run crashed past the clean-frame window — discard; lower `frames`)")
            continue
        for eng in ("objshift2", "objshift"):
            distinct, base, total, sat = res[eng]
            print(f"{leg:>3} {eng:>10} {distinct:>9} {base:>11} {total:>12} {sat:>10}")


if __name__ == "__main__":
    main()
