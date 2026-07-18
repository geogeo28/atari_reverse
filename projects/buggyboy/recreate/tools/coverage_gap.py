#!/usr/bin/env python3
"""coverage_gap.py — flag side-effecting call sites that no differential test executes.

The differential harness compares the memory image, which leaves two kinds of trigger unverified:

  * off-image effects — XBIOS Dosound writes the YM2149, not RAM; play_event_tune / handle_marker
    only touch the image when their mzflag/game_over guard is open. The effect is invisible to the
    image diff even when the code runs.
  * fuzz-unreached branches — the call never executes, so nothing is compared at all.

Either way the sound/OS trigger is unverified. This tool runs the differential suite once with the
oracle's executed-PC coverage on (oracle/shim.c osh_cov_*, dumped per xdist worker by test/conftest.py),
merges the per-worker coverage, then reports every call site to a "sink" (below) that no test executed.
Those are the triggers to directed-test or knowingly read-verify — see docs/on-target-execution.md §5.
Written after three leg-start/checkpoint/collision jingles shipped wrong because their play_event_tune
id sat in such a gap.

    mlenv python tools/coverage_gap.py            # run the suite, report gaps (exit 1 on a new gap)
    mlenv python tools/coverage_gap.py --list     # also list the covered sites

Knowingly-read-verified gaps live in tools/coverage_gap_allow.txt (`0x<addr> reason` per line); the
tool exits 0 when every gap is allowlisted, non-zero on a new one.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC = HERE.parent                                   # recreate/
PRG = REC.parent / "bin" / "BUGGYBOY.PRG"           # projects/buggyboy/bin/
PRG_DIS = REC.parents[2] / "tools" / "prg_dis.py"   # reverse/tools/
ALLOW = HERE / "coverage_gap_allow.txt"
LOAD_BASE = 0x10000                                 # oracle PC = LOAD_BASE + disasm offset

# Sound / OS "sinks": a call site reaching one of these fires an effect the image diff can miss.
# Ghidra addresses (== oracle PC); the disassembly prints them as (addr - LOAD_BASE).
SINKS = {
    0x11c7a: "play_event_tune",
    0x11cb2: "handle_marker",
    0x12ec4: "stop_music",
    0x12ebc: "stop_music_chk",
    0x1b59c: "INITTUNE",
    0x1b560: "INITFX",
}

CALL_RE = re.compile(r"^([0-9a-f]+):.*\b(?:bsr|jsr)\b\S*\s+\$([0-9a-f]+)")


def call_sites():
    """Every bsr/jsr call site (Ghidra addr -> sink name) that targets a sink, from prg_dis."""
    dis = subprocess.run([sys.executable, str(PRG_DIS), str(PRG)],
                         capture_output=True, text=True).stdout
    sites = {}
    for line in dis.splitlines():
        m = CALL_RE.match(line)
        if m and LOAD_BASE + int(m.group(2), 16) in SINKS:
            sites[LOAD_BASE + int(m.group(1), 16)] = SINKS[LOAD_BASE + int(m.group(2), 16)]
    return sites


def load_allow():
    allow = {}
    if ALLOW.exists():
        for line in ALLOW.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                addr, _, reason = line.partition(" ")
                allow[int(addr, 16)] = reason.strip() or "(no reason given)"
    return allow


def run_suite_with_coverage():
    """Run the differential suite (parallel) with per-worker coverage dumping; return merged bitset."""
    covdir = tempfile.mkdtemp(prefix="covgap_")
    env = {**os.environ, "COVGAP_DIR": covdir}
    code = subprocess.run([sys.executable, "-m", "pytest", "-q", "-n", "auto", str(REC / "test")],
                          env=env).returncode
    merged = bytearray()
    for dump in Path(covdir).glob("*.bin"):
        data = dump.read_bytes()
        if len(data) > len(merged):
            merged.extend(b"\0" * (len(data) - len(merged)))
        for i, b in enumerate(data):
            merged[i] |= b
    return code, merged


def visited(merged, addr):
    byte = addr >> 3
    return byte < len(merged) and bool((merged[byte] >> (addr & 7)) & 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="also print the covered sink call sites")
    args = ap.parse_args()

    sites = call_sites()
    if not sites:
        print("no sink call sites found (is prg_dis.py / the PRG present?)", file=sys.stderr)
        return 2
    print(f"tracking {len(sites)} sink call sites across {len(set(sites.values()))} sinks; "
          f"running the differential suite …\n")
    suite_code, merged = run_suite_with_coverage()

    allow = load_allow()
    covered = [s for s in sorted(sites) if visited(merged, s)]
    gaps = [s for s in sorted(sites) if not visited(merged, s)]

    if args.list:
        print("\ncovered sink call sites:")
        for s in covered:
            print(f"  0x{s:05x}  {sites[s]}")

    new_gaps = [g for g in gaps if g not in allow]
    print(f"\n=== coverage gaps: {len(gaps)} unexecuted sink call site(s) "
          f"({len(gaps) - len(new_gaps)} allowlisted) ===")
    for g in gaps:
        tag = f"  [allowed: {allow[g]}]" if g in allow else "  <-- NEW: unverified sound/OS trigger"
        print(f"  0x{g:05x}  {sites[g]}{tag}")
    if not gaps:
        print("  (none — every sink call site is exercised by a test)")

    if suite_code != 0:
        print("\nWARNING: the differential suite did not pass; coverage may be incomplete.",
              file=sys.stderr)
    return 1 if (new_gaps or suite_code != 0) else 0


if __name__ == "__main__":
    sys.exit(main())
