"""Per-frame cost benchmark for the in-race pipeline: the ORIGINAL 68000 code vs. our RECONSTRUCTION
cross-compiled to 68000 — both measured under Musashi (cycle-accurate), no Hatari needed.

Two things are measured on the same realistic mid-race image:
  - original:  the real BUGGYBOY machine code, run by the oracle (emu.run) — the baseline/ceiling.
  - recon:     our C cores cross-compiled to m68k (render/atari/build/game.elf, the exact code in
               BUGGY.PRG), loaded into a Musashi memory buffer at their link addresses and driven
               through emu.run_bench. This is what actually runs (slower) in Hatari.

The ratio recon/original is the compiler-efficiency gap per function — where GCC's output costs more
than the hand-written asm. render_road / blit_road_scroll / draw_game_objects / draw_hud are pure
image draws (no OS traps), so their comparison is exact. game_update is approximate: on the recon
side it runs the game build's input glue (a no-op with hw_ready=0) rather than the oracle's trap
model, so treat its ratio as indicative only.

Realistic state: mirror test_game_update_real_course — stage the real leg course, run the oracle
init_leg, then advance the recon game_update over the real COURSES.DAT (forcing a section-12 advance
each frame) to a representative in-race frame.

Usage:  python tools/bench_frame.py [leg] [warmup_frames]   (defaults: leg 0, 60 frames)
Build the recon first:  bash render/atari/game_build.sh   (else only the original is reported)
"""
import ctypes
import subprocess
import sys
from pathlib import Path

REC = Path(__file__).resolve().parents[1]                  # recreate/
sys.path.insert(0, str(REC.parents[2] / "tools"))          # reverse/tools — the shared recreate kit
sys.path.insert(0, str(REC / "test"))
sys.path.insert(0, str(REC / "render"))

from recreate_kit import project                           # noqa: E402
project.load(REC)                                          # binds the kit's loader/emu to this game

import emu                                                 # noqa: E402
import harness                                             # noqa: E402
import render_screen as R                                  # noqa: E402

CPU_HZ = 8_000_000                     # stock Atari ST 68000 clock
FRAME_HZ = 50                          # PAL vertical-blank rate the game targets
FRAME_BUDGET_CYCLES = CPU_HZ // FRAME_HZ   # 160000 cycles available per displayed frame

INIT_LEG = 0x104b8                     # oracle init_leg (brings state to leg start)
MAX_INSNS = 4_000_000
IMAGE_SIZE = harness.IMAGE_SIZE        # 0x100000; the recon's `image[]` BSS array is this size

# per-frame state that forces a section-12 course advance each frame (from test_game_update_real_course)
A_LEG_INDEX = 0x18c38
A_VIEW_FLAGS, A_ENGINE_RPM, A_SCROLL_PHASE, A_INPUT_STATE = 0x18c56, 0x18c4c, 0x18c4e, 0x18c44

# The in-race per-frame pipeline (game_main.c race loop). draw_game_objects takes the draw buffer in
# A6 (original convention); the rest read it from physbase_tbl[flip_idx]. The recon g_* wrappers all
# take only the image pointer, so the recon side needs no per-function registers.
DRAW_BUF = R.SCREEN_BASE               # physbase_tbl[0] set by _prepared_image
PIPELINE = [
    # name,              original entry, oracle input regs,   recon symbol
    ("game_update",       0x1110e, {},                  "g_game_update"),
    ("render_road",       0x19144, {},                  "g_render_road"),
    ("blit_road_scroll",  0x10326, {},                  "g_blit_road_scroll"),
    ("draw_game_objects", 0x12ef6, {"a6": DRAW_BUF},    "g_draw_game_objects"),
    ("draw_hud",          0x1555e, {},                  "g_draw_hud"),
]

RECON_ELF = REC / "render" / "atari" / "build" / "game.elf"
RECON_BIN = REC / "render" / "atari" / "build" / "game.bin"


def _w16(m, a, v):
    m[a], m[a + 1] = (v >> 8) & 0xff, v & 0xff


def _force_advance(m):
    _w16(m, A_VIEW_FLAGS, 0x10)
    _w16(m, A_ENGINE_RPM, 0xf)
    _w16(m, A_SCROLL_PHASE, 0xe)
    _w16(m, A_INPUT_STATE, 0)


def mid_race_state(leg, warmup):
    """Authentic in-race image: real course staged, oracle init_leg, then `warmup` recon game_update
    frames (each forcing a section-12 advance) so the road/objects/HUD hold real racing values."""
    img, _ = R._prepared_image({A_LEG_INDEX: leg.to_bytes(2, "big")})
    post_init, _, _ = emu.run(bytearray(img), INIT_LEG, {}, max_insns=MAX_INSNS)
    state = bytearray(post_init)
    buf = (ctypes.c_uint8 * IMAGE_SIZE).from_buffer(state)
    harness._lib.g_game_update.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    harness._lib.g_game_update.restype = None
    for _ in range(warmup):
        _force_advance(state)
        harness._lib.g_game_update(buf)
    return state


def measure_original(state):
    """Cycle/instruction cost of each original pipeline function on `state` (oracle). Returns
    {name: (insns, cycles)}."""
    out = {}
    for name, entry, regs, _ in PIPELINE:
        _, _, r = emu.run(bytearray(state), entry, dict(regs), max_insns=MAX_INSNS)
        out[name] = (r["ninsns"], r["cycles"])
    return out


def _load_recon():
    """Load the cross-compiled recon (game.elf/.bin) into a Musashi memory buffer at its link
    addresses. Returns (mem_template, image_addr, stack_top, sentinel, symbols) or None if unbuilt.

    The ELF links at base 0: flat code+data is game.bin; `image` is a 1 MiB BSS array whose address
    the linker chose. We size the buffer to cover [0, image_end) + a stack above it; the sentinel
    (an even return PC outside the loaded code) sits above the stack."""
    if not (RECON_ELF.exists() and RECON_BIN.exists()):
        return None
    syms = {}
    for line in subprocess.check_output(["m68k-elf-nm", str(RECON_ELF)], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            syms[parts[2]] = int(parts[0], 16)
    image_addr = syms["image"]
    stack_top = (image_addr + IMAGE_SIZE + 0x40000) & ~0xf     # 256 KiB of stack above the image
    sentinel = stack_top + 0x1000                              # even, above the stack, never executed
    mem_size = sentinel + 0x1000
    mem = bytearray(mem_size)
    flat = RECON_BIN.read_bytes()
    mem[0:len(flat)] = flat                                    # text + data at their link addresses
    return mem, image_addr, stack_top, sentinel, syms


def measure_recon(state, recon):
    """Cycle/instruction cost of each recon pipeline function on `state` (emu.run_bench). Returns
    {name: (insns, cycles)}. Each run starts from a fresh copy of the loaded image + the state."""
    mem_template, image_addr, stack_top, sentinel, syms = recon
    out = {}
    for name, _, _, sym in PIPELINE:
        mem = bytearray(mem_template)
        mem[image_addr:image_addr + IMAGE_SIZE] = state        # game globals at the recon's image[]
        r = emu.run_bench(mem, syms[sym], arg0=image_addr, sp=stack_top, sentinel=sentinel)
        out[name] = (r["ninsns"], r["cycles"])
    return out


def _fmt_row(name, orig, recon):
    o_ins, o_cyc = orig
    line = f"  {name:<18}{o_ins:>9}{o_cyc:>10}{1000 * o_cyc / CPU_HZ:>9.2f}"
    if recon is not None:
        r_ins, r_cyc = recon
        line += f"{r_ins:>10}{r_cyc:>10}{1000 * r_cyc / CPU_HZ:>9.2f}{r_cyc / o_cyc:>8.2f}x"
    return line


def benchmark(leg=0, warmup=60):
    state = mid_race_state(leg, warmup)
    orig = measure_original(state)
    recon_ctx = _load_recon()
    recon = measure_recon(state, recon_ctx) if recon_ctx else None

    print(f"BuggyBoy per-frame cost under Musashi (cycle-accurate), leg {leg}, after {warmup} frames")
    print(f"frame budget @ {FRAME_HZ} Hz on {CPU_HZ // 1_000_000} MHz ST = {FRAME_BUDGET_CYCLES} "
          f"cycles ({1000 / FRAME_HZ:.0f} ms)")
    if recon is None:
        print("(recon not built — showing original only; run: bash render/atari/game_build.sh)")
    print()
    header = f"  {'function':<18}{'o.insn':>9}{'o.cyc':>10}{'o.ms':>9}"
    if recon is not None:
        header += f"{'r.insn':>10}{'r.cyc':>10}{'r.ms':>9}{'ratio':>9}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for name, *_ in sorted(PIPELINE, key=lambda p: -orig[p[0]][1]):
        print(_fmt_row(name, orig[name], recon[name] if recon else None))
    print("  " + "-" * (len(header) - 2))
    o_tot = sum(c for _, c in orig.values())
    r_tot = sum(c for _, c in recon.values()) if recon else None
    print(_fmt_row("TOTAL", (sum(i for i, _ in orig.values()), o_tot),
                   (sum(i for i, _ in recon.values()), r_tot) if recon else None))
    print(f"\n  original: {o_tot / FRAME_BUDGET_CYCLES:.2f} vblanks/frame", end="")
    if recon:
        print(f"    recon: {r_tot / FRAME_BUDGET_CYCLES:.2f} vblanks/frame "
              f"({r_tot / o_tot:.2f}x the original)")
    else:
        print()


if __name__ == "__main__":
    leg = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    warmup = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    benchmark(leg, warmup)
