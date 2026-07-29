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
sys.path.insert(0, str(REC.parents[2] / "tools"))    # reverse/tools — the shared recreate kit
sys.path.insert(0, str(REC / "render"))

from recreate_kit import project                      # noqa: E402
project.load(REC)                                     # binds the kit (tos_probe/loader live there)

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


def host_leg_results():
    """Host g_draw_leg_results(leg=0) framebuffer (32000 bytes) via the candidate .so, using the
    same buffer layout as the on-target legdump — for a byte-exact draw-vs-host comparison."""
    import ctypes
    import struct
    from loader import load_image      # the kit's oracle/ is already on sys.path (project.load)
    lib = ctypes.CDLL(str(REC / "build" / "libbuggyboy.so"))
    img = bytearray(0x100000)
    base = load_image(str(REC.parent / "bin" / "BUGGYBOY.PRG"))
    img[:len(base)] = base
    MEM = 0x20000
    def w32(o, v): img[o:o+4] = struct.pack(">I", v)
    def w16(o, v): img[o:o+2] = struct.pack(">H", v)
    w32(0x18bf8, MEM + 0x57000); w32(0x18bfc, MEM); w32(0x18c00, MEM + 0x1900)
    w32(0x18c04, MEM + 0xf660); w32(0x18c08, MEM + 0x1c660)
    courses = (REC.parent / "bin" / "COURSES.DAT").read_bytes(); img[MEM:MEM+len(courses)] = courses
    gra = (REC.parent / "bin" / "GRAPHICS.GRA").read_bytes(); bc = MEM + 0x1c660
    img[bc+0xc350:bc+0xc350+len(gra)] = gra
    SCR = 0x2100
    w16(0x18bf2, 0); w32(0x18bf4, SCR); w16(0x18c38, 0)
    cb = (ctypes.c_uint8 * len(img)).from_buffer(img)
    lib.g_unpack_graphics(cb); lib.g_init_leg_dash(cb); lib.g_draw_leg_results(cb)
    return bytes(img[SCR:SCR+SCREEN_BYTES])


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    fb = run()

    if mode == "legdump":
        # Byte-exact: the on-target g_draw_leg_results buffer must equal the host render.
        host = host_leg_results()
        if bytes(fb) == host:
            print(f"MATCH: on-target leg-select buffer is byte-identical to the host ({len(fb)} bytes)")
        else:
            ndiff = sum(1 for a, b in zip(fb, host) if a != b)
            print(f"DIFF: {ndiff}/{SCREEN_BYTES} bytes differ from the host render")
            sys.exit(1)
        return

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
