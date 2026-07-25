#!/usr/bin/env python3
"""run_ste_ab.py — PERF30 C4: the whole-frame A/B differential between the stock ST build (68000 CPU
blits, on --machine st) and the STE hardware-blitter build (on --machine ste --blitter). Both run the
SAME GAME_AUTODRIVE script and dump the framebuffer after N frames; a byte-compare of the two dumps at
matched frame indices is the load-bearing pin for the blitter engine conversion.

Musashi cannot emulate the blitter, so this Hatari A/B compare (plus run_ste_golden.py's 5-leg goldens
ON --machine ste and run_ste_selftest.py's engine-vs-blitter XOR) is the pin for the STE build — weaker
instruction-level pinning than the host Musashi differentials, compensated by whole-frame byte equality
over a real headless drive.

In slice 1 the STE build still runs the C/asm objshift2 on the CPU, so the two builds render identically
and the A/B diff is 0 by construction — this run wires + proves the harness. When slice 2 routes
objshift2 through the blitter, this same compare becomes the byte-exactness gate.

Usage: python render/atari/run_ste_ab.py [frame_indices...]   # default: 50 150 300
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_hatari                                          # noqa: E402

STOCK_PRG, STE_PRG = "ABST.PRG", "ABSTE.PRG"
SCREEN_BYTES = run_hatari.SCREEN_BYTES
DEFAULT_FRAMES = (50, 150, 300)


def build(prg, frame_n, ste):
    """Build a GAME_AUTODRIVE=frame_n dump build (stock ST or STE). The env is scrubbed so each arm is
    exactly the build it names: the stock arm must NOT inherit a leaked GAME_STE, and neither arm is a
    self-test build."""
    env = {**os.environ, "GAME_PRG": prg, "GAME_EXTRA_CFLAGS": f"-DGAME_AUTODRIVE={frame_n}"}
    env.pop("GAME_STE_SELFTEST", None)
    if ste:
        env["GAME_STE"] = "1"
    else:
        env.pop("GAME_STE", None)
    subprocess.run(["bash", str(HERE / "build_game.sh")], env=env, check=True, stdout=subprocess.DEVNULL)


def main():
    frames = [int(a) for a in sys.argv[1:]] or list(DEFAULT_FRAMES)
    ok = True
    for n in frames:
        # needs_data=True: the A/B .PRGs load COURSES.DAT/GRAPHICS.GRA at boot (own names, so pass the flag
        # rather than mutating run_hatari's NEEDS_DATA_FILES global).
        build(STOCK_PRG, n, ste=False)
        fb_st = run_hatari.run(STOCK_PRG, machine="st", blitter=False, needs_data=True)[:SCREEN_BYTES]
        build(STE_PRG, n, ste=True)
        fb_ste = run_hatari.run(STE_PRG, machine="ste", blitter=True, needs_data=True)[:SCREEN_BYTES]
        ndiff = sum(1 for a, b in zip(fb_st, fb_ste) if a != b)
        tag = "MATCH" if ndiff == 0 else f"DIFF {ndiff}/{SCREEN_BYTES}"
        print(f"frame {n:4d}: stock-ST vs STE-blitter  {tag}")
        ok = ok and ndiff == 0
    print("\nA/B differential:", "0-mismatch over the drive — PASS" if ok else "MISMATCH — FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
