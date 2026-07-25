#!/usr/bin/env python3
"""run_ste_sweep.py — PERF30 C4, slice 2: prove the STE objshift2 blitter path is byte-exact vs the CPU
engine across the whole objshift2 case space (fine_x x width_idx x column/clip family x rows).

Builds the GAME_STE_SWEEP variant and boots it on --machine ste --blitter. The PRG (src/blitter_sweep.c)
runs rm_blit_objshift2_blitter against rm_blit_objshift2 for every case and dumps a per-case mismatch
grid to SCREEN.BIN: word0 = case count, word1 = total mismatch, then one word per case (0 == byte-exact;
clip cases the blitter declines are logged 0 as the pinned CPU hybrid). ALL words zero == PASS.

Usage: python render/atari/run_ste_sweep.py
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_hatari                                          # noqa: E402

SWEEP_PRG = "BUGGYBST.PRG"
SCREEN_BYTES = run_hatari.SCREEN_BYTES


def build():
    env = {**os.environ, "GAME_STE": "1", "GAME_STE_SWEEP": "1", "GAME_PRG": SWEEP_PRG}
    env.pop("GAME_STE_SELFTEST", None)
    subprocess.run(["bash", str(HERE / "build_game.sh")], env=env, check=True, stdout=subprocess.DEVNULL)


def main():
    build()
    # 1728 cases x full-framebuffer memset/compare is a lot of emulated cycles — give it a generous
    # vblank budget + wall-clock so the sweep finishes and dumps (default 4000 vbls is too short).
    fb = run_hatari.run(SWEEP_PRG, machine="ste", blitter=True, needs_data=True,
                        run_vbls=40000, timeout=240)[:SCREEN_BYTES]
    ncases = (fb[0] << 8) | fb[1]
    total = (fb[2] << 8) | fb[3]
    handled = (fb[SCREEN_BYTES - 2] << 8) | fb[SCREEN_BYTES - 1]
    bad = [i for i in range(ncases) if ((fb[(2 + i) * 2] << 8) | fb[(2 + i) * 2 + 1]) != 0]
    print(f"cases: {ncases}   blitter-handled (BASE): {handled}   CPU-hybrid (CLIP): {ncases - handled}"
          f"   total mismatch: {total}   failing cases: {len(bad)}")
    if not bad:
        print(f"MATCH: objshift2 blitter path is byte-exact over all {ncases} swept cases")
        sys.exit(0)
    print(f"DIFF: {len(bad)} case(s) mismatch (indices {bad[:20]}{'...' if len(bad) > 20 else ''})")
    sys.exit(1)


if __name__ == "__main__":
    main()
