#!/usr/bin/env python3
"""Dump the relocated PRG static-data region (fonts, label strings, fill patterns, glyph tables)
that the demo loads into the image at 0x10000. Derived from BUGGYBOY.PRG via the same loader the
differential harness uses, so it stays in sync. Written where build.sh stages the drive.

Usage: gen_static.py BUGGYBOY.PRG out/STATIC.BIN
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "oracle"))     # recreate/oracle
from loader import load_image                            # noqa: E402

LO, HI = 0x10000, 0x1c000        # relocated PRG static region (must match main.c STATIC_LO/LEN)


def main():
    prg, out = sys.argv[1], sys.argv[2]
    blob = bytes(load_image(prg)[LO:HI])
    Path(out).write_bytes(blob)
    print(f"{out}: {len(blob)} bytes  [{LO:#x},{HI:#x})")


if __name__ == "__main__":
    main()
