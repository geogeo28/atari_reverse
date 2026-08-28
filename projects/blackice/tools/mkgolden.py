#!/usr/bin/env python3
"""Render the scripted walk and compare it against the goldens in test/golden/.

BY DEFAULT THIS WRITES NOTHING.  It renders to a temp directory, diffs the
result against what is committed, and prints what moved; only `--bless` copies
the new files over the old ones.  A golden that a tool can silently rewrite is
not a golden, and "the pixels changed and I did not notice" is exactly the
failure the golden exists to catch.

Two goldens are kept, for two different jobs:

  walk_hashes.txt      one line per tick: the GameState hash and the planar
                       screen hash.  A sim regression shows up in the first
                       column, a renderer regression in the second, so a
                       failure says which half broke before you open anything.
  walk_png_sha256.txt  the sha256 of every frame's PNG.  This is the pixel
                       contract the 68000 c2p and column drawer must reproduce.

Only KEEP_FRAMES of the PNGs themselves are committed - enough to look at, not
6 MB of them.

    python3 tools/mkgolden.py            # diff only, exit 1 if anything moved
    python3 tools/mkgolden.py --bless    # accept the new frames
"""
import argparse
import hashlib
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from consts import CONST                                        # noqa: E402

GOLDEN = ROOT / "test" / "golden"
LEVEL = ROOT / "levels" / "level1.txt"
SCRIPT = ROOT / "test" / "scripts" / "walk.txt"
FRAMES = 100
KEEP_FRAMES = (0, 20, 40, 60, 99)
# Rendered at the SHIPPING width, and passed explicitly rather than left to the
# default: the pixel contract has to say which of the two modes it is.
DETAIL = CONST["DETAIL_DEFAULT"]
DETAIL_COLUMNS = (CONST["RENDER_COLUMNS_HIGH"] if DETAIL == CONST["DETAIL_COLUMNS_160"]
                  else CONST["RENDER_COLUMNS_LOW"])


def render(out_dir, hashes_path):
    subprocess.run([
        str(ROOT / "build" / "blackice_host"),
        "--level", str(LEVEL),
        "--script", str(SCRIPT),
        "--frames", str(FRAMES),
        "--detail", str(DETAIL),
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


def first_difference(produced, committed):
    """The first line that differs, as a human-readable string, or None."""
    produced_lines = produced.splitlines()
    committed_lines = committed.splitlines()
    if len(produced_lines) != len(committed_lines):
        return "line count %d -> %d" % (len(committed_lines), len(produced_lines))
    for was, now in zip(committed_lines, produced_lines):
        if was != now:
            return "%r -> %r" % (was, now)
    return None


def report(name, produced, path):
    """Print what moved in one golden file.  Returns True if anything did."""
    committed = path.read_text() if path.exists() else ""
    difference = first_difference(produced, committed)
    if difference is None:
        print("  %-20s unchanged" % name)
        return False
    print("  %-20s MOVED: %s" % (name, difference))
    return True


def main():
    parser = argparse.ArgumentParser(description="diff or bless the golden walk")
    parser.add_argument("--bless", action="store_true",
                        help="overwrite the committed goldens with what was just rendered")
    args = parser.parse_args()

    GOLDEN.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = pathlib.Path(tmp)
        # Rendered to the temp directory too, so a plain run cannot touch
        # anything under test/golden/.
        hashes_path = out_dir / "walk_hashes.txt"
        render(out_dir, hashes_path)
        produced = {
            "walk_hashes.txt": hashes_path.read_text(),
            "walk_png_sha256.txt": png_digests(out_dir),
        }

        print("golden walk: %d frames of %s at %d columns"
              % (FRAMES, LEVEL.name, DETAIL_COLUMNS))
        moved = [report(name, text, GOLDEN / name) for name, text in produced.items()]

        if not args.bless:
            if any(moved):
                print("\nnothing written.  Look at the frames, then re-run with --bless.")
                return 1
            return 0

        for name, text in produced.items():
            (GOLDEN / name).write_text(text)
        for frame in KEEP_FRAMES:
            name = "frame%04d.png" % frame
            shutil.copy(out_dir / name, GOLDEN / name)
    print("\nblessed: goldens written to %s" % GOLDEN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
