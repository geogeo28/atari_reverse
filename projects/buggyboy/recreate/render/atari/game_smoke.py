#!/usr/bin/env python3
"""Headless smoke test for the playable BuggyBoy PRG.

Build with `game_build.sh smoke` first: that PRG skips the leg-select wait, runs a fixed number of
in-race frames on a real 68000, dumps the drawn framebuffer to C:\\SCREEN.BIN, and terminates. This
runs it on a headless Hatari (real TOS ROM), reads the dump back, de-interleaves it to a PNG under
out/render/, and sanity-checks that the frame is actually a rendered scene (non-blank, plausible
plane content) — proving the whole init + render pipeline works cross-compiled and on-target.

Usage: python render/atari/game_smoke.py
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC = HERE.parents[1]                                # recreate/
sys.path.insert(0, str(REC / "oracle"))
sys.path.insert(0, str(REC / "render"))

import tos_probe                                      # noqa: E402
from render_screen import _decode_interleaved, SCREEN_BASE, W, H  # noqa: E402
from extract_graphics import write_png                # noqa: E402

DISK = HERE / "disk"
SCREEN_BYTES = W * H * 4 // 8                          # 32000
RUN_VBLS = "8000"                                     # init + unpack + 120 render frames, fast-forwarded


def run(timeout=90):
    hatari = tos_probe.find_hatari()
    rom = os.environ.get("BB_TOS_ROM") or tos_probe.find_tos_rom()
    if not (hatari and rom):
        raise RuntimeError("Hatari or TOS ROM not available (brew install hatari)")
    with tempfile.TemporaryDirectory() as d:
        drive = Path(d)
        for name in ["BUGGY.PRG", "STATIC.BIN", "GRAPHICS.GRA", "COURSES.DAT"]:
            (drive / name).write_bytes((DISK / name).read_bytes())
        out = drive / "SCREEN.BIN"
        env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
        args = [hatari, "--sound", "off", "--fast-forward", "on", "--confirm-quit", "off",
                "--memsize", "4", "--monitor", "rgb", "--tos-res", "low", "--tos", rom,
                "--run-vbls", RUN_VBLS, "--harddrive", str(drive), "--auto", "C:\\BUGGY.PRG"]
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
            raise RuntimeError("BUGGY.PRG did not produce SCREEN.BIN (boot/build/render failure)")
        return out.read_bytes()


def main():
    fb = run()
    image = bytearray(SCREEN_BASE) + fb
    rows = _decode_interleaved(image, SCREEN_BASE)
    outdir = REC.parent / "out" / "render"
    outdir.mkdir(parents=True, exist_ok=True)
    png = outdir / "game_smoke.png"
    # neutral 16-grey ramp palette (the dump has no palette; we only check structure)
    pal = [(i * 17, i * 17, i * 17) for i in range(16)]
    write_png(str(png), W, H, rows, pal)

    nonzero = sum(1 for b in fb if b)
    distinct = len(set(fb))
    print(f"wrote {png} ({len(fb)} bytes)")
    print(f"non-zero bytes: {nonzero}/{SCREEN_BYTES}   distinct byte values: {distinct}")
    if nonzero < SCREEN_BYTES // 20 or distinct < 8:
        print("SUSPECT: framebuffer looks blank/degenerate — init or render likely failed")
        sys.exit(1)
    print("OK: on-target framebuffer is a non-blank rendered frame")


if __name__ == "__main__":
    main()
