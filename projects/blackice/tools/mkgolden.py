#!/usr/bin/env python3
"""Render the scripted walk and write the golden files under test/golden/.

Two goldens are kept, for two different jobs:

  walk_hashes.txt      one line per tick: the GameState hash and the planar
                       screen hash.  A sim regression shows up in the first
                       column, a renderer regression in the second, so a
                       failure says which half broke before you open anything.
  walk_png_sha256.txt  the sha256 of every frame's PNG.  This is the pixel
                       contract the 68000 c2p and column drawer must reproduce.

Only KEEP_FRAMES of the PNGs themselves are committed - enough to look at, not
6 MB of them.

    python3 tools/mkgolden.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "test" / "golden"
LEVEL = ROOT / "levels" / "level1.txt"
SCRIPT = ROOT / "test" / "scripts" / "walk.txt"
FRAMES = 100
KEEP_FRAMES = (0, 20, 40, 60, 99)


def render(out_dir, hashes_path):
    subprocess.run([
        str(ROOT / "build" / "blackice_host"),
        "--level", str(LEVEL),
        "--script", str(SCRIPT),
        "--frames", str(FRAMES),
        "--out", str(out_dir),
        "--png", "all",
        "--hashes", str(hashes_path),
    ], check=True)


def png_digests(out_dir):
    lines = []
    for frame in range(FRAMES):
        data = (out_dir / ("frame%04d.png" % frame)).read_bytes()
        lines.append("%d %s" % (frame, hashlib.sha256(data).hexdigest()))
    return "\n".join(lines) + "\n"


def main():
    GOLDEN.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = pathlib.Path(tmp)
        hashes_path = GOLDEN / "walk_hashes.txt"
        render(out_dir, hashes_path)
        (GOLDEN / "walk_png_sha256.txt").write_text(png_digests(out_dir))
        for frame in KEEP_FRAMES:
            name = "frame%04d.png" % frame
            shutil.copy(out_dir / name, GOLDEN / name)
    print("goldens written to %s" % GOLDEN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
