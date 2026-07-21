"""bench.py — per-function cycle cost of the remaster render cores vs recreate's recon, on a 68000.

Both sides are C cross-compiled to m68k and run under the cycle-accurate Musashi core (emu.run_bench):
  - recreate recon: render/atari/build/game.elf — the faithful flat-image cores g_<fn>(image).
  - remaster:       render/atari/build/bench.elf — the native-struct cores, called through the
                    zero-work bench_<fn> wrappers in bench_main.c (structs staged from the demo
                    fixture). Build it first: bash render/atari/bench_build.sh

For each render function we report instructions, cycles, and the remaster/recon cycle ratio, plus how
much of the 50 Hz frame budget each side spends. Both sides render the SAME staged leg-1 frame
(gen_demo_fixture.staged_image), so per-function ratios reflect the code, not frame content. This is
the perf-track measurement: recreate is the correctness oracle, and this shows where remaster pays
(or wins) for its native-struct rewrite.

Usage: python tools/bench.py            (from remaster/, after bench_build.sh + recreate `make`)
"""
import ctypes
import subprocess
import sys
from pathlib import Path

REMASTER = Path(__file__).resolve().parents[1]
RECREATE = REMASTER.parent / "recreate"
for p in ("oracle", "tools", "test", "render"):
    sys.path.insert(0, str(RECREATE / p))

import emu                                          # noqa: E402  Musashi cycle-accurate runner
import bench_frame                                  # noqa: E402  recon loader + mid-race staging
sys.path.insert(0, str(REMASTER / "test"))
sys.path.insert(0, str(REMASTER / "render" / "atari"))
import assets_load                                  # noqa: E402  the arena the remaster cores read
import gen_demo_fixture                             # noqa: E402  shared leg-1 staging (same frame both sides)

CPU_HZ = bench_frame.CPU_HZ                          # 8 MHz ST 68000
FRAME_BUDGET = bench_frame.FRAME_BUDGET_CYCLES       # cycles per 50 Hz frame
BENCH_ELF = REMASTER / "render" / "atari" / "build" / "bench.elf"
BENCH_BIN = REMASTER / "render" / "atari" / "build" / "bench.bin"
A_view_flags = 0x18c56
A_scroll_speed = 0x18cb4
BENCH_SCROLL_SPEED = 0x20                            # must match bench_main.c BENCH_SCROLL_SPEED

# (label, recon symbol, remaster bench symbol). Ordered by the in-frame draw sequence.
FUNCS = [
    ("build_road_geometry", "g_build_road_geometry", "bench_build_geometry"),
    ("render_road",         "g_render_road",         "bench_render_road"),
    ("blit_road_scroll",    "g_blit_road_scroll",    "bench_blit_scroll"),
    ("draw_hud",            "g_draw_hud",            "bench_draw_hud"),
]


def _syms(elf):
    out = {}
    for line in subprocess.check_output(["m68k-elf-nm", str(elf)], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            out[parts[2]] = int(parts[0], 16)
    return out


def _load_flat(binpath, syms):
    """Load a flat base-0 recon binary into a Musashi memory image with a stack above its end.
    Returns (mem_template, stack_top, sentinel)."""
    flat = binpath.read_bytes()
    end = max(syms.values()) + 0x8000               # past the highest symbol (BSS lives here)
    stack_top = (end + 0x40000) & ~0xf              # 256 KiB stack above BSS
    sentinel = stack_top + 0x1000
    mem = bytearray(sentinel + 0x1000)
    mem[0:len(flat)] = flat
    return mem, stack_top, sentinel


def _run(mem_template, entry, arg0, stack_top, sentinel, preps=()):
    """Run `entry`, after each `preps` entry on the SAME memory (e.g. bind the asset pointers, build
    the geometry table so render_road reads a valid road). Only the final run is counted."""
    mem = bytearray(mem_template)
    for prep in preps:
        emu.run_bench(mem, prep, arg0=arg0, sp=stack_top, sentinel=sentinel)
    r = emu.run_bench(mem, entry, arg0=arg0, sp=stack_top, sentinel=sentinel)
    return r["ninsns"], r["cycles"]


def remaster_costs():
    syms = _syms(BENCH_ELF)
    mem, sp, sentinel = _load_flat(BENCH_BIN, syms)
    # The remaster loads its assets from COURSES.DAT / GRAPHICS.GRA, and there is no filesystem under
    # Musashi — so drop the already-unpacked arena straight into the .bss block bench_main.c reserved
    # for it, and let bench_stage_assets bind the pointers into it before every measured call.
    arena = assets_load.fresh_arena()
    at = syms["arena_block"]
    # Slice-assigning past the end would silently GROW the bytearray and shift the stack/sentinel
    # layout out from under emu.run_bench, so require it to land inside the image.
    assert at + len(arena) <= len(mem), "arena_block does not fit the Musashi image"
    mem[at:at + len(arena)] = arena

    # render_road reads the control table geometry writes; blit_road_scroll reads the pre-rotated
    # copies rm_scroll_prebuild builds — so run those preps first (they're per-leg, not per-frame),
    # mirroring the recon's geometry prep, and measure only the per-frame call.
    prep = {"render_road": syms["bench_build_geometry"], "blit_road_scroll": syms["bench_scroll_prebuild"]}
    return {label: _run(mem, syms[rm], 0, sp, sentinel,
                        preps=[syms["bench_stage_assets"], *([prep[label]] if label in prep else [])])
            for label, _, rm in FUNCS}


def recon_costs():
    """Run each recon g_<fn> on the SAME leg-1 frame the remaster bench uses (gen_demo_fixture's
    shared staging), so the per-function ratio reflects code, not frame content. scroll_speed is set
    to match bench_main; geometry is rebuilt so render_road/blit read valid tables."""
    state = gen_demo_fixture.staged_image()
    state[A_scroll_speed], state[A_scroll_speed + 1] = (BENCH_SCROLL_SPEED >> 8) & 0xff, BENCH_SCROLL_SPEED & 0xff
    recon = bench_frame._load_recon()
    if recon is None:
        return None
    mem_template, image_addr, stack_top, sentinel, syms = recon

    def run(sym, prep_geometry=False):
        mem = bytearray(mem_template)
        mem[image_addr:image_addr + bench_frame.IMAGE_SIZE] = state
        if prep_geometry:                            # refresh road_curve_tbl for the readers
            emu.run_bench(mem, syms["g_build_road_geometry"], arg0=image_addr, sp=stack_top,
                          sentinel=sentinel, max_insns=16_000_000)
        r = emu.run_bench(mem, syms[sym], arg0=image_addr, sp=stack_top, sentinel=sentinel)
        return r["ninsns"], r["cycles"]

    out = {label: run(sym, prep_geometry=(label in ("render_road", "blit_road_scroll")))
           for label, sym, _ in FUNCS}
    # also the byte-exact machine-model render_road (the tight register/goto transcription — the
    # fastest reference), to show how much the idiomatic recon (and remaster) give up for readability.
    if "g_render_road_machine" in syms:
        out["render_road_machine"] = run("g_render_road_machine", prep_geometry=True)
    return out


def main():
    if not (BENCH_ELF.exists() and BENCH_BIN.exists()):
        sys.exit("bench.elf not built — run: bash render/atari/bench_build.sh")
    rm = remaster_costs()
    rec = recon_costs()

    print(f"Per-function render cost under Musashi (cycle-accurate), 8 MHz ST, 50 Hz frame "
          f"budget = {FRAME_BUDGET} cycles\n")
    hdr = f"  {'function':<20}{'rm.insn':>10}{'rm.cyc':>10}{'rm.ms':>8}"
    if rec:
        hdr += f"{'rec.insn':>10}{'rec.cyc':>10}{'rec.ms':>8}{'rm/rec':>8}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    rm_tot = rec_tot = 0
    for label, _, _ in FUNCS:
        ri, rc = rm[label]
        rm_tot += rc
        line = f"  {label:<20}{ri:>10}{rc:>10}{1000 * rc / CPU_HZ:>8.2f}"
        if rec:
            xi, xc = rec[label]
            rec_tot += xc
            line += f"{xi:>10}{xc:>10}{1000 * xc / CPU_HZ:>8.2f}{rc / xc:>7.2f}x"
        print(line)
    print("  " + "-" * (len(hdr) - 2))
    tline = f"  {'TOTAL':<20}{'':>10}{rm_tot:>10}{1000 * rm_tot / CPU_HZ:>8.2f}"
    if rec:
        tline += f"{'':>10}{rec_tot:>10}{1000 * rec_tot / CPU_HZ:>8.2f}{rm_tot / rec_tot:>7.2f}x"
    print(tline)

    # render_road vs the byte-exact machine model (recon's tight register/goto transcription).
    if rec and "render_road_machine" in rec:
        mi, mc = rec["render_road_machine"]
        ri, rc = rm["render_road"]
        _, gc = rec["render_road"]
        print(f"\n  render_road vs the machine model (the tight register/goto transcription):")
        print(f"    machine:{mi:>9}{mc:>10}{1000 * mc / CPU_HZ:>8.2f} ms   "
              f"remaster {rc / mc:.2f}x  ·  idiomatic recon {gc / mc:.2f}x")

    print(f"\n  remaster: {rm_tot / FRAME_BUDGET:.2f} frame-budgets/frame", end="")
    if rec:
        print(f"    recon: {rec_tot / FRAME_BUDGET:.2f}  (remaster is {rm_tot / rec_tot:.2f}x the recon)")
    else:
        print("\n  (recon game.elf not built — run: bash render/atari/game_build.sh)")


if __name__ == "__main__":
    main()
