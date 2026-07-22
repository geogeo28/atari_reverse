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

# (label, recon symbol or None, remaster bench symbol). Ordered as the demo's game loop + draw_frame
# run them, so the TOTAL is the demo's frame cost on the staged leg-1 frame. (course_advance and
# ring_views run only on view-wrap frames in the demo — every few frames — so the TOTAL overstates a
# non-wrap frame by their ~1.7 ms.) Recon symbols are only given where an image-arg-only recreate
# entry point has the same scope (g_draw_ground / g_draw_object take a second draw-buffer argument,
# so their per-stage recon column stays blank; the whole tree is compared via the object_tree row
# below instead).
FUNCS = [
    ("player_update",       None,                    "bench_player_update"),
    ("course_advance",      None,                    "bench_course_advance"),
    ("ring_views",          None,                    "bench_ring_views"),
    ("gobj_prefix",         "g_draw_game_objects_prefix", "bench_gobj_prefix"),
    ("build_road_geometry", "g_build_road_geometry", "bench_build_geometry"),
    ("frame_clear",         None,                    "bench_frame_clear"),
    ("render_road",         "g_render_road",         "bench_render_road"),
    ("blit_road_scroll",    "g_blit_road_scroll",    "bench_blit_scroll"),
    ("draw_ground",         None,                    "bench_draw_ground"),
    ("draw_fg_sprite",      "g_draw_fg_sprite",      "bench_draw_fg_sprite"),
    ("objlist_pass1",       None,                    "bench_objlist_pass1"),
    ("draw_object",         None,                    "bench_draw_object"),
    ("objlist_pass2",       None,                    "bench_objlist_pass2"),
    ("objlist_fixed",       None,                    "bench_objlist_fixed"),
    ("draw_buggy",          "g_draw_buggy",          "bench_draw_buggy"),
    ("draw_hud",            "g_draw_hud",            "bench_draw_hud"),
]

# Whole-scope comparison rows (not part of the TOTAL — they re-run stages already counted above).
COMPOSITES = [
    ("object_tree",         "g_draw_game_objects",   "bench_object_tree"),
    ("draw_frame",          None,                    "bench_draw_frame"),
]

# Remaster wrappers that need a built control table (and, for draw_frame, the pre-rotated scroll
# copies) before the measured call — same reason recon preps geometry for its road readers.
RM_PREPS = {
    "player_update":  ["bench_build_geometry"],
    "objlist_pass1":  ["bench_build_geometry"],
    "draw_object":    ["bench_build_geometry"],
    "objlist_pass2":  ["bench_build_geometry"],
    "objlist_fixed":  ["bench_build_geometry"],
    "object_tree":    ["bench_build_geometry"],
    "render_road":    ["bench_build_geometry"],
    "blit_road_scroll": ["bench_scroll_prebuild"],
    "draw_frame":     ["bench_scroll_prebuild"],
}


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


def staged_mem():
    """(syms, mem_template, stack_top, sentinel) with the unpacked asset arena installed — the ONE
    memory image every remaster measurement starts from (this module and tools/profile.py alike).
    The remaster loads its assets from COURSES.DAT / GRAPHICS.GRA, and there is no filesystem under
    Musashi — so drop the already-unpacked arena straight into the .bss block bench_main.c reserved
    for it; bench_stage_assets then binds the pointers into it before every measured call."""
    syms = _syms(BENCH_ELF)
    mem, sp, sentinel = _load_flat(BENCH_BIN, syms)
    arena = assets_load.fresh_arena()
    at = syms["arena_block"]
    # Slice-assigning past the end would silently GROW the bytearray and shift the stack/sentinel
    # layout out from under emu.run_bench, so require it to land inside the image.
    assert at + len(arena) <= len(mem), "arena_block does not fit the Musashi image"
    mem[at:at + len(arena)] = arena
    return syms, mem, sp, sentinel


def preps_for(bench_sym):
    """The prep symbols to run, in order, before measuring `bench_sym`: the staging pass plus the
    stage's RM_PREPS entry, resolved through the FUNCS/COMPOSITES row for that symbol (RM_PREPS is
    keyed by row label, and labels are not uniformly the symbol minus \"bench_\" — deriving the key
    by string surgery is how tools/profile.py once skipped the scroll blit's prebuild silently)."""
    label = next((lbl for lbl, _, rm in FUNCS + COMPOSITES if rm == bench_sym), None)
    return ["bench_stage_assets", *RM_PREPS.get(label, ())]


def remaster_costs():
    syms, mem, sp, sentinel = staged_mem()
    # Some wrappers read state another stage builds (the control table, the pre-rotated scroll
    # copies) — run those preps first (they're per-leg / earlier-in-frame, not part of the measured
    # stage), mirroring the recon's geometry prep, and measure only the per-frame call.
    return {label: _run(mem, syms[rm], 0, sp, sentinel, preps=[syms[p] for p in preps_for(rm)])
            for label, _, rm in FUNCS + COMPOSITES}


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

    GEOM_READERS = ("render_road", "blit_road_scroll", "object_tree")
    out = {label: run(sym, prep_geometry=(label in GEOM_READERS))
           for label, sym, _ in FUNCS + COMPOSITES if sym}
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

    def row(label):
        ri, rc = rm[label]
        line = f"  {label:<20}{ri:>10}{rc:>10}{1000 * rc / CPU_HZ:>8.2f}"
        if rec and label in rec:
            xi, xc = rec[label]
            line += f"{xi:>10}{xc:>10}{1000 * xc / CPU_HZ:>8.2f}{rc / xc:>7.2f}x"
        print(line)
        return rc

    rm_tot = sum(row(label) for label, _, _ in FUNCS)
    print("  " + "-" * (len(hdr) - 2))
    print(f"  {'TOTAL (frame)':<20}{'':>10}{rm_tot:>10}{1000 * rm_tot / CPU_HZ:>8.2f}")

    # Whole-scope comparison rows (re-run stages already counted above; not part of the TOTAL).
    print()
    for label, _, _ in COMPOSITES:
        row(label)

    # render_road vs the byte-exact machine model (recon's tight register/goto transcription).
    if rec and "render_road_machine" in rec:
        mi, mc = rec["render_road_machine"]
        ri, rc = rm["render_road"]
        _, gc = rec["render_road"]
        print(f"\n  render_road vs the machine model (the tight register/goto transcription):")
        print(f"    machine:{mi:>9}{mc:>10}{1000 * mc / CPU_HZ:>8.2f} ms   "
              f"remaster {rc / mc:.2f}x  ·  idiomatic recon {gc / mc:.2f}x")

    print(f"\n  remaster: {rm_tot / FRAME_BUDGET:.2f} frame-budgets/frame "
          f"({CPU_HZ / rm_tot:.1f} fps compute-bound; 30 fps needs <= {CPU_HZ / 30:.0f} cycles)")
    if not rec:
        print("  (recon game.elf not built — run: bash render/atari/game_build.sh)")


if __name__ == "__main__":
    main()
