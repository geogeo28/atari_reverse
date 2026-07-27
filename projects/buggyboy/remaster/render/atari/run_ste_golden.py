#!/usr/bin/env python3
"""run_ste_golden.py — PERF30 C4, slice 1: prove the STE build target is pixel-faithful and additive.

Thin wrapper over run_golden.py's ONE golden harness in its ste=True mode: it builds each leg's GOLDEN.PRG
(-DGOLDEN_BOOT_LEG=N) and boots it on `hatari --machine ste --blitter`, byte-comparing the boot frame
against recreate's pipeline golden. A MATCH on all legs proves the STE run's whole render pipeline draws
the SAME pixels as the stock ST run (the object blits still run the
C/asm CPU reference in this slice; the blitter driver is proven separately by run_ste_selftest.py). This
is the "STE goldens MATCH x5 on --machine ste" pin. The leg-bounds check + summary live in run_golden.main.

Usage: python render/atari/run_ste_golden.py                 # all legs
       python render/atari/run_ste_golden.py 3               # a single leg
       python render/atari/run_ste_golden.py --memsize 1     # all legs on a 1 MB machine (the memory-diet gate)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_golden                                          # noqa: E402  the single golden harness

if __name__ == "__main__":
    run_golden.main(ste=True)
