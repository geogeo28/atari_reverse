#!/usr/bin/env python3
"""run_cadence.py — the C1 present-cadence instrument, headless (PERF30 C1 / C4).

Builds a GAME_CADENCE_TRACE + GAME_AUTODRIVE variant and boots it on Hatari for `machine` (st / ste). The
shell records the vblank SPAN of every present (game_main.c's cadence_record) into a log dumped to
C:\\SCREEN.BIN on exit; this parses it and prints the span distribution (vblanks / ms / fps per present).
Pass machine=ste to measure on the STE hardware-blitter build (GAME_STE=1, --machine ste --blitter) — the
before/after metric for the C4 blitter engine conversion. Cycle-exactness is NOT available for the blitter
under Hatari; the vblank-span distribution is the perf metric.

Usage: python render/atari/run_cadence.py [st|ste] [frames] [--legs N]
       python render/atari/run_cadence.py            # stock ST, 400 frames, leg 0
       python render/atari/run_cadence.py ste         # STE build on --machine ste --blitter
"""
import os
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_hatari                                          # noqa: E402  shared machine-parametrised runner

VBLS_PER_FRAME_HEADROOM = 12                               # gate frames are ~6-8 vblanks; 12 is safe slack


def build(machine, frames, leg):
    prg = "CADENCEST.PRG" if machine == "ste" else "CADENCE.PRG"
    env = {**os.environ, "GAME_PRG": prg, "GOLDEN_LEG": str(leg),
           "GAME_EXTRA_CFLAGS": f"-DGAME_AUTODRIVE={frames} -DGAME_CADENCE_TRACE={frames}"}
    env.pop("GAME_STE_SELFTEST", None)
    if machine == "ste":
        env["GAME_STE"] = "1"
    else:
        env.pop("GAME_STE", None)
    subprocess.run(["bash", str(HERE / "build_game.sh")], env=env, check=True, stdout=subprocess.DEVNULL)
    return prg


def parse(fb):
    n = (fb[0] << 8) | fb[1]
    return [(fb[2 + i * 2] << 8) | fb[2 + i * 2 + 1] for i in range(n)]


def report(label, spans):
    s = spans[1:]                                          # drop present 0 (boot-to-first-flip, not a cadence)
    print(f"\n=== {label}: {len(s)} presents (frame 0 dropped) ===")
    print(f"  median {statistics.median(s)}  mean {statistics.mean(s):.2f}  min {min(s)}  max {max(s)}  vblanks/present")
    hist = {}
    for v in s:
        hist[v] = hist.get(v, 0) + 1
    for v in sorted(hist):
        print(f"    {v:2d} vbl ({v * 20:4d} ms, {50.0 / v:4.1f} fps): {hist[v]:3d}  {'#' * min(hist[v], 60)}")


def measure(machine="st", frames=400, leg=0):
    prg = build(machine, frames, leg)
    fb = run_hatari.run(prg, machine=machine, blitter=(machine == "ste"), needs_data=True,
                        run_vbls=frames * VBLS_PER_FRAME_HEADROOM, timeout=180)
    spans = parse(fb)
    report(f"{machine} (leg {leg}, {frames} frames)", spans)
    return spans


def main():
    args = [a for a in sys.argv[1:]]
    leg = 0
    if "--legs" in args:
        i = args.index("--legs")
        leg = int(args[i + 1])
        del args[i:i + 2]
    machine = args[0] if args and args[0] in ("st", "ste") else "st"
    frames = next((int(a) for a in args if a.isdigit()), 400)
    measure(machine, frames, leg)


if __name__ == "__main__":
    main()
