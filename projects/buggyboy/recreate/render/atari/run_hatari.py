#!/usr/bin/env python3
"""Run DEMO.PRG on a headless Hatari and verify the on-target framebuffer.

The demo writes its painted 32000-byte framebuffer to C:\\SCREEN.BIN; we auto-run it on a
headless Hatari GEMDOS drive (reusing tos_probe's Hatari/ROM discovery), read that dump back,
de-interleave it to a PNG, and diff it against the host render (render_screen.py) — so a green
run proves the *reconstructed C, cross-compiled and executed on a real 68000 core*, produces the
exact same picture as the host `.so`.

Usage: python render/atari/run_hatari.py           # build must have run first (build.sh)
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

import tos_probe                                      # noqa: E402  (Hatari + TOS ROM discovery)
from render_screen import _decode_interleaved, SCREEN_BASE, W, H, PALETTE  # noqa: E402
from extract_graphics import write_png                # noqa: E402

DISK = HERE / "disk"
SCREEN_BYTES = W * H * 4 // 8                          # 32000
RUN_VBLS = "4000"                                      # ~80s of emulated time at 50Hz, fast-forwarded


def run(timeout=60):
    hatari, rom = tos_probe.find_hatari(), tos_probe.find_tos_rom()
    if not (hatari and rom):
        raise RuntimeError("Hatari or TOS ROM not available (brew install hatari)")

    with tempfile.TemporaryDirectory() as d:
        drive = Path(d)
        for name in ("DEMO.PRG", "STATIC.BIN", "GRAPHICS.GRA"):
            (drive / name).write_bytes((DISK / name).read_bytes())
        out = drive / "SCREEN.BIN"
        env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
        args = [hatari, "--sound", "off", "--fast-forward", "on", "--confirm-quit", "off",
                "--memsize", "4", "--monitor", "rgb", "--tos-res", "low", "--tos", rom,
                "--run-vbls", RUN_VBLS, "--harddrive", str(drive), "--auto", "C:\\DEMO.PRG"]
        proc = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            deadline = time.time() + timeout
            while time.time() < deadline:
                if out.exists() and out.stat().st_size >= SCREEN_BYTES:
                    time.sleep(0.3)                    # let the write flush
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
            raise RuntimeError("DEMO.PRG did not produce SCREEN.BIN (Hatari/boot/build failure)")
        return out.read_bytes()


def main():
    fb = run()
    # The dump is the framebuffer itself; de-interleave from offset 0 (not SCREEN_BASE).
    image = bytearray(SCREEN_BASE) + fb                # pad so SCREEN_BASE indexing works
    rows = _decode_interleaved(image, SCREEN_BASE)
    outdir = REC.parent / "out" / "render"
    outdir.mkdir(parents=True, exist_ok=True)
    png = outdir / "leg_results_0_hatari.png"
    write_png(str(png), W, H, rows, PALETTE)
    print(f"wrote {png} ({len(fb)} bytes from Hatari)")

    # Compare against the host render's framebuffer for an exact-match check.
    from render_screen import render_leg_results
    host = render_leg_results(0)
    host_fb = bytes(host[SCREEN_BASE:SCREEN_BASE + SCREEN_BYTES])
    if host_fb == bytes(fb):
        print("MATCH: on-target framebuffer is byte-identical to the host render")
    else:
        ndiff = sum(1 for a, b in zip(host_fb, fb) if a != b)
        print(f"DIFF: {ndiff}/{SCREEN_BYTES} bytes differ from the host render")


if __name__ == "__main__":
    main()
