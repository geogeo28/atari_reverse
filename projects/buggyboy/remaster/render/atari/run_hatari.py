#!/usr/bin/env python3
"""run_hatari.py — the shared headless-Hatari runner. A LIBRARY MODULE, not an entry point.

An on-target program writes its painted 32000-byte framebuffer to C:\\SCREEN.BIN; `run()` auto-runs the
.PRG on a headless Hatari GEMDOS drive and returns that dump, and `verify_frame()` byte-compares it to a
golden .bin rendered by recreate's verified cores (writing a PNG alongside). A MATCH proves remaster's C,
cross-compiled and executed on a real 68000 core, produces the exact same pixels.

Every on-target runner imports this: run_golden.py / run_ste_golden.py (the frame-0 goldens), plus the
measurement runners run_cadence.py and run_ste_{ab,census,selftest,sweep}.py.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REMASTER = HERE.parents[1]
RECREATE = REMASTER.parent / "recreate"
sys.path.insert(0, str(RECREATE / "oracle"))
sys.path.insert(0, str(RECREATE / "render"))
sys.path.insert(0, str(RECREATE.parents[2] / "tools"))   # reverse/tools for write_png

import tos_probe                                          # noqa: E402  Hatari + TOS ROM discovery
from render_screen import _decode_interleaved, W, H       # noqa: E402
from extract_graphics import write_png                    # noqa: E402

BUILD = HERE / "build"                                    # every .PRG variant the build scripts emit
DISK = HERE / "disk"                                      # the interactive-play drive: BUGGYBOY.PRG + its data
SCREEN_BASE = 0x2000                                      # only for _decode_interleaved's indexing
SCREEN_BYTES = W * H * 4 // 8                             # 32000
RUN_VBLS = "4000"
# Emulated RAM in MB. 4 is the harness default; the 1 MB memory-diet gate re-runs every pin at 1, where a
# ~700 KB program leaves EmuTOS ~197 KB of free TPA above its BSS. Overridable per call, or for a whole
# harness run via RM_MEMSIZE so runners that don't take the argument themselves still follow. Runners whose
# .PRG has a REQUIREMENT (the census sets, the sweep's statics + the placed tables) pass memsize
# explicitly and so are immune to RM_MEMSIZE — a measurement must never be silently starved of RAM.
DEFAULT_MEMSIZE = os.environ.get("RM_MEMSIZE", "4")


# The game's data files, staged beside every .PRG: every on-target program built from game_main.c loads
# them itself at boot (src/assets.c) and hangs to a timeout without them. The opt-out this used to carry
# existed only for the retired HUD-only demo, which loaded nothing.
DATA_FILES = ("COURSES.DAT", "GRAPHICS.GRA")


def run(prg, timeout=60, machine="st", blitter=False, run_vbls=None, memsize=None):
    """Boot `prg` headless and return its 32000-byte SCREEN.BIN dump. machine selects the emulated
    hardware (st/ste/...); blitter=True adds --blitter on (STE hardware-blitter build, PERF30 C4). The
    bundled Hatari TOS is EmuTOS 1024k, which boots every machine type, so the STE A/B differential runs
    from the same drive image as the stock ST run.

    COURSES.DAT/GRAPHICS.GRA are staged beside the .PRG (see DATA_FILES) — every on-target program reads
    them at boot; without them it hangs to a timeout.

    The .PRG is read from build/, where every variant lands, so a measurement build never has to be
    copied into disk/ (that stays the interactive-play drive: BUGGYBOY.PRG + the two data files, which
    build_game.sh's shipping build keeps fresh). The run itself happens on a throwaway TemporaryDirectory
    drive, so it can't write back over either directory.

    memsize: emulated RAM in MB (see DEFAULT_MEMSIZE) — the 1 MB memory-diet gate runs the pins at 1."""
    hatari, rom = tos_probe.find_hatari(), tos_probe.find_tos_rom()
    if not (hatari and rom):
        raise RuntimeError("Hatari or TOS ROM not available (brew install hatari)")
    with tempfile.TemporaryDirectory() as d:
        drive = Path(d)
        (drive / prg).write_bytes((BUILD / prg).read_bytes())
        for name in DATA_FILES:
            (drive / name).write_bytes((DISK / name).read_bytes())
        out = drive / "SCREEN.BIN"
        env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
        args = [hatari, "--machine", machine]
        if blitter:
            args += ["--blitter", "on"]
        args += ["--sound", "off", "--fast-forward", "on", "--confirm-quit", "off",
                 "--memsize", str(memsize or DEFAULT_MEMSIZE),
                 "--monitor", "rgb", "--tos-res", "low", "--tos", rom,
                 "--run-vbls", str(run_vbls or RUN_VBLS), "--harddrive", str(drive), "--auto", "C:\\" + prg]
        proc = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            deadline = time.time() + timeout
            while time.time() < deadline:
                if out.exists() and out.stat().st_size >= SCREEN_BYTES:
                    time.sleep(0.3)
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.2)
        finally:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
        if not (out.exists() and out.stat().st_size >= SCREEN_BYTES):
            raise RuntimeError(f"{prg} did not produce SCREEN.BIN (Hatari/boot/build failure)")
        return out.read_bytes()


def _palette_rgb(palette_path):
    """A palette .bin -> 16 (r,g,b) from the ST 0x0RGB words (3-bit channels scaled to 8). run_golden.py
    passes its per-leg build/palette_leg<N>.bin."""
    pal_words = Path(palette_path).read_bytes()
    pal = []
    for i in range(16):
        w = (pal_words[i * 2] << 8) | pal_words[i * 2 + 1]
        r, g, b = (w >> 8) & 7, (w >> 4) & 7, w & 7
        pal.append((r * 255 // 7, g * 255 // 7, b * 255 // 7))
    return pal


def verify_frame(fb, png_basename, match_msg, golden_path, palette_path):
    """Decode the Hatari framebuffer to a PNG, byte-compare it to `golden_path`, and report the result
    (MATCH: <match_msg>, or a DIFF). Returns True on MATCH, False on DIFF — the caller decides the exit
    code (run_golden.py loops legs 0-4 and exits nonzero if ANY diffs)."""
    outdir = RECREATE.parent / "out" / "render"
    outdir.mkdir(parents=True, exist_ok=True)
    image = bytearray(SCREEN_BASE) + fb                   # pad so SCREEN_BASE indexing works
    rows = _decode_interleaved(image, SCREEN_BASE)
    png = outdir / png_basename
    write_png(str(png), W, H, rows, _palette_rgb(palette_path))
    print(f"wrote {png} ({len(fb)} bytes from Hatari)")

    golden = Path(golden_path).read_bytes()
    if bytes(fb) == golden:
        print("MATCH: " + match_msg)
        return True
    ndiff = sum(1 for a, b in zip(fb, golden) if a != b)
    print(f"DIFF: {ndiff}/{SCREEN_BYTES} bytes differ from recreate's golden frame")
    return False


if __name__ == "__main__":
    sys.exit("run_hatari is a library module, not a runner — use "
             "run_golden.py / run_ste_golden.py (the frame-0 goldens) or the run_* measurement runners. "
             "(It used to boot the HUD-only demo, retired once the full game + golden harness superseded it.)")
