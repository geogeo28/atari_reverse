"""frame_dist.py — per-frame render cost DISTRIBUTION across real drives, on the 68000 (Musashi).

tools/bench.py costs one staged frame — and that frame is the demo's boot frame (a leg start, start
gate in view), near the object tree's worst case. This runs recreate's whole-frame render
(g_draw_frame: geometry + road + scroll + object tree + HUD) over legs x warmup depths of the
oracle's own drive and prints the spread, so planning uses the median frame and not the gate.

Usage: python tools/frame_dist.py          (from remaster/, after recreate `make` built game.elf)
"""
import sys
from pathlib import Path

REMASTER = Path(__file__).resolve().parents[1]
RECREATE = REMASTER.parent / "recreate"
for p in ("oracle", "tools", "test", "render"):
    sys.path.insert(0, str(RECREATE / p))

import emu                                          # noqa: E402  Musashi cycle-accurate runner
import bench_frame                                  # noqa: E402  recon loader + mid-race staging

CPU_HZ = bench_frame.CPU_HZ

LEGS = (0, 1, 4)                  # the legs the equivalence drives use
WARMUPS = range(0, 601, 30)       # sample depth into a 600-frame drive


def main():
    recon = bench_frame._load_recon()
    if recon is None:
        sys.exit("recon game.elf not built — run: bash render/atari/game_build.sh (in recreate/)")
    mem_template, image_addr, stack_top, sentinel, syms = recon

    print(f"{'leg':>4}{'warmup':>8}{'cycles':>10}{'ms':>8}{'fps':>7}")
    cycles = []
    for leg in LEGS:
        for w in WARMUPS:
            state = bench_frame.mid_race_state(leg, w)
            mem = bytearray(mem_template)
            mem[image_addr:image_addr + bench_frame.IMAGE_SIZE] = state
            r = emu.run_bench(mem, syms["g_draw_frame"], arg0=image_addr, sp=stack_top,
                              sentinel=sentinel)
            ms = 1000 * r["cycles"] / CPU_HZ
            cycles.append(r["cycles"])
            print(f"{leg:>4}{w:>8}{r['cycles']:>10}{ms:>8.2f}{1000 / ms:>7.1f}", flush=True)

    cycles.sort()
    n = len(cycles)
    print(f"\nframes: {n}   min {1000 * cycles[0] / CPU_HZ:.1f} ms   "
          f"median {1000 * cycles[n // 2] / CPU_HZ:.1f} ms   "
          f"p90 {1000 * cycles[int(n * 0.9)] / CPU_HZ:.1f} ms   "
          f"max {1000 * cycles[-1] / CPU_HZ:.1f} ms")
    print(f"fps: best {CPU_HZ / cycles[0]:.1f}   median {CPU_HZ / cycles[n // 2]:.1f}   "
          f"worst {CPU_HZ / cycles[-1]:.1f}")


if __name__ == "__main__":
    main()
