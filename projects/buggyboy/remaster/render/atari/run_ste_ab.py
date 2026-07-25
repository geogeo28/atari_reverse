#!/usr/bin/env python3
"""run_ste_ab.py — PERF30 C4: the whole-frame A/B differential of the UNIFIED BUGGYBOY.PRG on the two
machines. The SAME binary runs its GAME_AUTODRIVE script on --machine st (which binds the 68000 CPU asm
path — no blitter) and on --machine ste --blitter (which binds the hardware-blitter path), dumps the
framebuffer after N frames, and byte-compares the two dumps. Because it is ONE .PRG, this is the
load-bearing pin that the boot-bound blitter route draws the same pixels as the CPU route.

Musashi cannot emulate the blitter, so this Hatari A/B compare (plus run_ste_golden.py's 5-leg goldens
on BOTH machines) is the pin — weaker instruction-level pinning than the host Musashi differentials,
compensated by whole-frame byte equality over a real headless drive.

Note: the default headless autodrive steers off-course and crashes past ~90 frames, so pick frame indices
inside the valid render window (≤ ~80).

Usage: python render/atari/run_ste_ab.py [frame_indices...]   # default: 20 40 60 80
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_hatari                                          # noqa: E402

AB_PRG = "AB.PRG"
SCREEN_BYTES = run_hatari.SCREEN_BYTES
DEFAULT_FRAMES = (20, 40, 60, 80)


def build(frame_n):
    """Build ONE unified GAME_AUTODRIVE=frame_n dump build (the shipping code path — no GAME_STE split)."""
    env = {**os.environ, "GAME_PRG": AB_PRG, "GAME_EXTRA_CFLAGS": f"-DGAME_AUTODRIVE={frame_n}"}
    subprocess.run(["bash", str(HERE / "build_game.sh")], env=env, check=True, stdout=subprocess.DEVNULL)


def main():
    frames = [int(a) for a in sys.argv[1:]] or list(DEFAULT_FRAMES)
    ok = True
    for n in frames:
        build(n)                                            # ONE binary, run on both machines
        fb_st = run_hatari.run(AB_PRG, machine="st", blitter=False, needs_data=True)[:SCREEN_BYTES]
        fb_ste = run_hatari.run(AB_PRG, machine="ste", blitter=True, needs_data=True)[:SCREEN_BYTES]
        ndiff = sum(1 for a, b in zip(fb_st, fb_ste) if a != b)
        tag = "MATCH" if ndiff == 0 else f"DIFF {ndiff}/{SCREEN_BYTES}"
        print(f"frame {n:4d}: same PRG  st(CPU) vs ste(blitter)  {tag}")
        ok = ok and ndiff == 0
    print("\nsame-PRG A/B differential:", "0-mismatch over the drive — PASS" if ok else "MISMATCH — FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
