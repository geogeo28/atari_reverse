#!/usr/bin/env python3
"""run_cadence.py — the C1 present-cadence instrument, headless (PERF30 C1 / C4).

Builds a GAME_CADENCE_TRACE + GAME_AUTODRIVE variant and boots it on Hatari for `machine` (st / ste). The
shell records the vblank SPAN of every present (game_main.c's cadence_record) into a log dumped to
C:\\SCREEN.BIN on exit; this parses it and prints the span distribution (vblanks / ms / fps per present).
Pass machine=ste to measure the STE hardware-blitter route (--machine ste --blitter; the unified binary
binds the blitter at boot) — the before/after metric for the C4 blitter engine conversion. Cycle-exactness
is NOT available for the blitter under Hatari; the vblank-span distribution is the perf metric.

--freerun drops the C1 even-vblank flip lock (-DGAME_PRESENT_FREERUN) so a present costs exactly what
the frame took: WITH the lock every present is quantised onto the 2-vblank grid, which hides a render win
smaller than one grid step. The C4 blitter before/after numbers (BLIT_STE_SPEC §6/§11) are free-run.

--idle holds the buggy on the leg-start GATE (no throttle) instead of driving — the objshift-dense
scene the C4 blitter routes were profiled on; without it the script drives the course.

Usage: python render/atari/run_cadence.py [st|ste] [frames] [--legs N] [--idle] [--freerun]
       python render/atari/run_cadence.py            # stock ST, 400 frames, leg 0, driving
       python render/atari/run_cadence.py ste         # STE build on --machine ste --blitter
       python render/atari/run_cadence.py ste 200 --idle --freerun   # the leg-start gate, unquantised
"""
import os
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_hatari                                          # noqa: E402  shared machine-parametrised runner

# Gate frames are ~6-8 vblanks, 10 in the tail-canary-taxed trace build, plus the boot + leg-select
# vblanks before the autodrive script starts. 12 was NOT slack enough: the stock-ST gate cell (200 idle
# frames at ~130 ms) ran out of vblanks mid-trace and died with "did not produce SCREEN.BIN".
VBLS_PER_FRAME_HEADROOM = 16
# Wall-clock budget for one cell, sized WITH the vblank budget above (raising one without the other just
# moves the "did not produce SCREEN.BIN" failure to a different cell).
CELL_TIMEOUT_S = 300
IDLE_CFLAGS = "-DAUTODRIVE_BASE_INPUT=0 -DAUTODRIVE_STEER_AFTER=1000000"   # no throttle, never steer
# game_main.c's cadence tail, in dump order: the sub-vblank render clock, the blitter route counters,
# then the memory-diet pair. Each name appears once; TAIL_COUNTERS is the wire order, the groups are what
# the report prints separately. The route counters read 0 on a machine that bound the CPU engines.
RENDER_COUNTERS = ("render ticks", "render frames")
ROUTE_COUNTERS = ("objshift2 hit", "objshift2 miss",
                  "colour table hit", "colour first-sight", "colour grow", "colour table-full",
                  "scroll routed", "scroll declined",
                  "dash routed", "dash declined")
# The overdraw-tail guard band (game_main.c's SCREEN_OVERDRAW / canary_check) and the free TPA above BSS
# the boot bind measured. A nonzero trip count means an object draw ate the tail margin — a FAILURE.
MEMORY_COUNTERS = ("tail canary trips", "free TPA bytes")
TAIL_COUNTERS = RENDER_COUNTERS + ROUTE_COUNTERS + MEMORY_COUNTERS
CADENCE_MAGIC = 0xCADE00C5                                 # game_main.c's CADENCE_MAGIC; pins the tail
CADENCE_HEADER_LONGS = 2                                   # {magic, counter count} ahead of the counters
HZ200_MS = 1000.0 / 200                                    # one TOS _hz_200 tick


def build(machine, frames, leg, idle=False, freerun=False):
    prg = "CADENCEST.PRG" if machine == "ste" else "CADENCE.PRG"
    extra = f"-DGAME_AUTODRIVE={frames} -DGAME_CADENCE_TRACE={frames}" + (f" {IDLE_CFLAGS}" if idle else "")
    if freerun:
        extra += " -DGAME_PRESENT_FREERUN"
    env = {**os.environ, "GAME_PRG": prg, "GOLDEN_LEG": str(leg), "GAME_EXTRA_CFLAGS": extra,
           "GAME_NO_STAGE": "1"}                # a harness variant stays in build/; disk/ is the play drive
    env.pop("GAME_STE_SELFTEST", None)
    subprocess.run(["bash", str(HERE / "build_game.sh")], env=env, check=True, stdout=subprocess.DEVNULL)
    return prg


def parse(fb):
    n = (fb[0] << 8) | fb[1]
    return [(fb[2 + i * 2] << 8) | fb[2 + i * 2 + 1] for i in range(n)]


def parse_counters(fb):
    """The counter longs game_main.c writes at the end of the dump, behind a {magic, count} header.

    SCREEN.BIN is a shared channel — every build variant dumps a frame through it — so a tail read from
    the wrong dump, or from a build whose counter list has moved, would still yield plausible-looking
    numbers. Refuse to report any of them unless the header matches."""
    def long_at(i):
        return int.from_bytes(fb[i * 4:i * 4 + 4], "big")

    base = len(fb) // 4 - (CADENCE_HEADER_LONGS + len(TAIL_COUNTERS))
    magic, count = long_at(base), long_at(base + 1)
    if magic != CADENCE_MAGIC or count != len(TAIL_COUNTERS):
        die(f"cadence tail header is {magic:#010x}/{count}, expected {CADENCE_MAGIC:#010x}/"
            f"{len(TAIL_COUNTERS)} — this SCREEN.BIN is not a cadence dump, or game_main.c's tail layout "
            f"moved and run_cadence.py did not follow")
    return {name: long_at(base + CADENCE_HEADER_LONGS + i) for i, name in enumerate(TAIL_COUNTERS)}


def die(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def pop_flag(args, flag):
    """Remove `flag` from `args` (in place) and report whether it was there."""
    if flag not in args:
        return False
    args.remove(flag)
    return True


def report(label, spans):
    s = spans[1:]                                          # drop present 0 (boot-to-first-flip, not a cadence)
    print(f"\n=== {label}: {len(s)} presents (frame 0 dropped) ===")
    print(f"  median {statistics.median(s)}  mean {statistics.mean(s):.2f}  min {min(s)}  max {max(s)}  vblanks/present")
    hist = {}
    for v in s:
        hist[v] = hist.get(v, 0) + 1
    for v in sorted(hist):
        print(f"    {v:2d} vbl ({v * 20:4d} ms, {50.0 / v:4.1f} fps): {hist[v]:3d}  {'#' * min(hist[v], 60)}")


def measure(machine="st", frames=400, leg=0, idle=False, freerun=False):
    prg = build(machine, frames, leg, idle, freerun)
    fb = run_hatari.run(prg, machine=machine, blitter=(machine == "ste"), needs_data=True,
                        run_vbls=frames * VBLS_PER_FRAME_HEADROOM, timeout=CELL_TIMEOUT_S)
    spans = parse(fb)
    report(f"{machine} (leg {leg}, {frames} frames, {'gate/idle' if idle else 'driving'}"
           f"{', free-run' if freerun else ''})", spans)
    counters = parse_counters(fb)
    ticks, rendered = counters["render ticks"], counters["render frames"]
    if rendered:
        print(f"  render time (sub-vblank, {rendered} frames): "
              f"{ticks * HZ200_MS / rendered:.2f} ms/frame  ({ticks} ticks total)")
    print("  blitter routes: " + "  ".join(f"{k}={counters[k]}" for k in ROUTE_COUNTERS))
    trips = counters["tail canary trips"]
    print(f"  memory: free TPA above BSS = {counters['free TPA bytes']} bytes;  "
          + (f"*** TAIL CANARY TRIPPED on {trips} presents ***" if trips else "tail canary clean (0 trips)"))
    return spans, counters


def main():
    args = [a for a in sys.argv[1:]]
    idle = pop_flag(args, "--idle")
    freerun = pop_flag(args, "--freerun")
    leg = 0
    if "--legs" in args:
        i = args.index("--legs")
        leg = int(args[i + 1])
        del args[i:i + 2]
    machine = args[0] if args and args[0] in ("st", "ste") else "st"
    frames = next((int(a) for a in args if a.isdigit()), 400)
    measure(machine, frames, leg, idle, freerun)


if __name__ == "__main__":
    main()
