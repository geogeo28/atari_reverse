#!/usr/bin/env python3
"""run_hatari.py — run the remaster HUD .PRG on a headless Hatari and verify the on-target frame.

The demo writes its painted 32000-byte framebuffer to C:\\SCREEN.BIN; we auto-run it on a headless
Hatari GEMDOS drive, read that dump back, and byte-compare it to build/golden.bin (recreate's HUD
frame for the same inputs). A MATCH proves remaster's HUD C, cross-compiled and executed on a real
68000 core, produces the exact same pixels as the verified recreate cores. A PNG is also written.

Usage: python render/atari/run_hatari.py     # build.sh must have run first
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

BUILD = HERE / "build"
SCREEN_BASE = 0x2000                                      # only for _decode_interleaved's indexing
SCREEN_BYTES = W * H * 4 // 8                             # 32000
RUN_VBLS = "4000"


def run(prg, timeout=60):
    hatari, rom = tos_probe.find_hatari(), tos_probe.find_tos_rom()
    if not (hatari and rom):
        raise RuntimeError("Hatari or TOS ROM not available (brew install hatari)")
    with tempfile.TemporaryDirectory() as d:
        drive = Path(d)
        (drive / prg).write_bytes((HERE / "disk" / prg).read_bytes())
        out = drive / "SCREEN.BIN"
        env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
        args = [hatari, "--sound", "off", "--fast-forward", "on", "--confirm-quit", "off",
                "--memsize", "4", "--monitor", "rgb", "--tos-res", "low", "--tos", rom,
                "--run-vbls", RUN_VBLS, "--harddrive", str(drive), "--auto", "C:\\" + prg]
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


def _palette_rgb():
    """build/palette.bin -> 16 (r,g,b) from the ST 0x0RGB words (3-bit channels scaled to 8)."""
    pal_words = (BUILD / "palette.bin").read_bytes()
    pal = []
    for i in range(16):
        w = (pal_words[i * 2] << 8) | pal_words[i * 2 + 1]
        r, g, b = (w >> 8) & 7, (w >> 4) & 7, w & 7
        pal.append((r * 255 // 7, g * 255 // 7, b * 255 // 7))
    return pal


def main():
    fb = run("HUD.PRG")

    outdir = RECREATE.parent / "out" / "render"
    outdir.mkdir(parents=True, exist_ok=True)
    image = bytearray(SCREEN_BASE) + fb                   # pad so SCREEN_BASE indexing works
    rows = _decode_interleaved(image, SCREEN_BASE)
    png = outdir / "remaster_hud_hatari.png"
    write_png(str(png), W, H, rows, _palette_rgb())
    print(f"wrote {png} ({len(fb)} bytes from Hatari)")

    golden = (BUILD / "golden.bin").read_bytes()
    if bytes(fb) == golden:
        print("MATCH: on-target remaster HUD is byte-identical to recreate's g_draw_hud")
    else:
        ndiff = sum(1 for a, b in zip(fb, golden) if a != b)
        print(f"DIFF: {ndiff}/{SCREEN_BYTES} bytes differ from recreate's golden frame")
        sys.exit(1)


if __name__ == "__main__":
    main()
