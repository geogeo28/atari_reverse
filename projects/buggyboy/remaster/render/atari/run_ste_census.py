#!/usr/bin/env python3
"""run_ste_census.py — PERF30 C4 slice 5: census the DISTINCT materialise-key tuples each fine-x engine
issues over real drives, to decide whether boot pre-shift tables are FINITE.

Boot tables pre-materialise the interleaved (mask,data) bitmaps for every reachable (sprite region ×
fine_x × width × rows) combination, so a driving blit is 2 passes over static data — no per-frame
materialise. That is only viable if the reachable set is bounded. This drives each leg headless (long
GAME_AUTODRIVE) with the dispatch instrumented (src/blitter_census.c counts distinct base-family tuples
via open-addressed sets) and reports the distinct count + base/total call counts per key per leg. If the
distinct set is small and bounded → tables are finite (state the size). If it saturates or grows with the
drive length → measured NO-GO for full tables; the honest fallback is a hybrid (a big non-evicting cache
for the recurring set + CPU for the rest).

The colour engine is counted under four keys (see SETS) because what a table must enumerate depends on
the blit scheme: the full pre-shift key is unbounded, the hardware-skew `sprite` key is not.

Usage: python render/atari/run_ste_census.py [frames]   # default 60 frames/leg, legs 0-4
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

# One 7-word block per set, in blitter_census_report's order: the fixed-pass engine, then the colour
# engine under four progressively coarser materialise keys. The reduced keys measure the HARDWARE-SKEW
# scheme (BLIT_STE_SPEC §10's remaining lever): skewing at blit time from unshifted bitmaps drops fine_x
# from the materialised content, the binary per-plane colour fill drops `color`, and materialising at max
# rows (blitting fewer via y_count) drops rows_m1 — leaving `sprite` as the static-table key.
BLOCK_WORDS = 7
HEADER_WORDS = 2                                         # {CENSUS_MAGIC, set count}, before the blocks
CENSUS_MAGIC = 0xC5C5                                    # pins this wire format; see src/blitter_census.c
SETS = ("objshift2", "objshift/full", "objshift/noshift", "objshift/noshift-nocolor", "objshift/sprite")
VBLS_PER_FRAME = 20                                      # generous headroom: a census frame runs on the CPU
VBLS_BOOT = 900                                          # EmuTOS boot + asset load, before frame 0
HATARI_TIMEOUT_MIN = 300                                 # seconds; scaled with the vbl budget below
HATARI_SECS_PER_VBL = 0.1                                # host wall-clock allowance per emulated vbl


def build(leg, frames):
    # NO -DGOLDEN_BOOT_LEG: that variant dumps the frame-0 golden to SCREEN.BIN at BOOT, and run_hatari
    # returns the FIRST dump it observes — so the boot frame raced the census report and won at some frame
    # counts (the pre-existing "crashed" rows). GAME_AUTODRIVE alone boots the same leg via GAME_LEG_INDEX
    # (game_main.c's BOOT_FAST_LEG), which GOLDEN_LEG already sets, and dumps only the census.
    env = {**os.environ, "GAME_STE": "1", "GAME_STE_CENSUS": "1", "GAME_PRG": CENSUS_PRG,
           "GOLDEN_LEG": str(leg), "GAME_EXTRA_CFLAGS": f"-DGAME_AUTODRIVE={frames}"}
    subprocess.run(["bash", str(HERE / "build_game.sh")], env=env, check=True, stdout=subprocess.DEVNULL)


def census_leg(leg, frames):
    build(leg, frames)
    run_vbls = VBLS_BOOT + frames * VBLS_PER_FRAME
    fb = run_hatari.run(CENSUS_PRG, machine="ste", blitter=True, needs_data=True, run_vbls=run_vbls,
                        timeout=max(HATARI_TIMEOUT_MIN, int(run_vbls * HATARI_SECS_PER_VBL)))
    nwords = HEADER_WORDS + BLOCK_WORDS * len(SETS)
    w = struct.unpack(f">{nwords}H", fb[:nwords * 2])
    # blitter_census_report stamps {CENSUS_MAGIC, set count} ahead of the blocks. SCREEN.BIN is a shared
    # channel (other build variants dump frames through it), so the header is what proves this file is the
    # census report and not somebody else's output — no header, no data.
    out = {"_valid": w[0] == CENSUS_MAGIC and w[1] == len(SETS)}
    for i, name in enumerate(SETS):
        b = w[HEADER_WORDS + i * BLOCK_WORDS:HEADER_WORDS + (i + 1) * BLOCK_WORDS]
        out[name] = ((b[0] << 16) | b[1], (b[2] << 16) | b[3], (b[4] << 16) | b[5], b[6])
    return out


def main():
    # §10's "~60 clean frames" ceiling was the boot-dump race, not a crash: with the golden dump gone the
    # autodrive censuses cleanly to at least 300 frames. Grow `frames` until the counts stop moving.
    frames = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    print(f"=== census: {NUM_LEGS} legs x {frames} frames ===")
    print(f"{'leg':>3} {'key':>25} {'distinct':>9} {'base_calls':>11} {'total_calls':>12} {'saturated':>10}")
    for leg in range(NUM_LEGS):
        try:
            res = census_leg(leg, frames)
        except RuntimeError as e:                        # build/emulation failure: crash, hang, or vbl budget
            print(f"{leg:>3}  (leg failed, skipped — crash, hang, or too small a vbl budget: {e})")
            continue
        if not res["_valid"]:
            print(f"{leg:>3}  (report header did not validate — SCREEN.BIN holds something other than the "
                  f"census: a second writer or a corrupted run. Investigate; do NOT lower `frames`.)")
            continue
        for name in SETS:
            distinct, base, total, sat = res[name]
            print(f"{leg:>3} {name:>25} {distinct:>9} {base:>11} {total:>12} {sat:>10}")


if __name__ == "__main__":
    main()
