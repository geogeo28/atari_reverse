#!/usr/bin/env python3
"""run_ste_selftest.py — PERF30 C4, slice 1: prove the STE hardware-blitter driver reproduces the
68000 masked-blit engine BYTE-FOR-BYTE, on emulated STE hardware.

Builds the GAME_STE_SELFTEST variant (BUGGYBST.PRG) and boots it on `hatari --machine ste --blitter on`.
The PRG (src/blitter_selftest.c) draws a synthetic sprite twice — once with the real rm_blit_objshift2
(src/blit.c, the shipping reference) at fine_x==0, once by firing the hardware blitter (8 passes: 4
planes x {AND mask, OR data}) — over the same background, then dumps the XOR of the two framebuffers to
C:\\SCREEN.BIN. A byte-exact blitter makes that diff all-zero. This is the driver/recipe pin: register
poking, HOP=SRC + LOP AND/OR, the interleaved 4-plane walk, endmasks and Hatari's blitter model all
agree with the C engine. (The fine_x!=0 SKEW mapping is specified in BLIT_STE_SPEC.md, slice 2.)

Usage: python render/atari/run_ste_selftest.py
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_hatari                                          # noqa: E402  shared machine-parametrised runner

SELFTEST_PRG = "BUGGYBST.PRG"
SCREEN_BYTES = run_hatari.SCREEN_BYTES


def build():
    # GAME_PRG makes this runner's SELFTEST_PRG constant authoritative — the build writes exactly the
    # .PRG we then boot, so a stale earlier build can't cause a false pass.
    env = {**os.environ, "GAME_STE": "1", "GAME_STE_SELFTEST": "1", "GAME_PRG": SELFTEST_PRG}
    subprocess.run(["bash", str(HERE / "build_game.sh")], env=env, check=True,
                   stdout=subprocess.DEVNULL)


def main():
    build()
    diff = run_hatari.run(SELFTEST_PRG, machine="ste", blitter=True, needs_data=True)[:SCREEN_BYTES]
    nz = sum(1 for b in diff if b)
    if nz == 0:
        print("MATCH: STE blitter reproduces rm_blit_objshift2 byte-for-byte (0/%d)" % SCREEN_BYTES)
        sys.exit(0)
    first = next(i for i, b in enumerate(diff) if b)
    print(f"DIFF: {nz}/{SCREEN_BYTES} bytes differ (first at byte {first}) — blitter recipe is NOT byte-exact")
    sys.exit(1)


if __name__ == "__main__":
    main()
