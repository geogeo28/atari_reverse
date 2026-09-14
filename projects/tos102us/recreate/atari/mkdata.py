#!/usr/bin/env python3
"""mkdata.py — the fixture files the two conformance floppies carry, written deterministically.

    python3 mkdata.py <out-dir>

TOSTEST walks the floppy root with Fsfirst/Fsnext and TOSBENCH reads DATA64K.BIN through GEMDOS, so
both need a root whose contents are the same on every build and on both disks: identical names,
identical sizes, identical bytes. A directory listing that differed between two runs would be
indistinguishable from a GEMDOS that behaved differently.

THE SPEC IS prg/fixtures.h AND THIS SCRIPT PARSES IT rather than restating it, because the other
reader of it is TOSBENCH.PRG, which runs on a different machine and cannot import anything. A name
or a size spelled in both places would not fail a build when they drifted: it would fail as an
`Fopen` returning -33 inside a timed workload, or as a read shorter than the bench believed it
asked for. That header's comments are where the choices — the eight-character-distinct names, the
counter pattern and its period — are explained.
"""
import re
import sys
from pathlib import Path

from cdefines import defines

HERE = Path(__file__).resolve().parent
FIXTURES_HEADER = HERE / "prg" / "fixtures.h"

# `defines` reads integers; a fixture's name is a string, so the one line shape it does not cover is
# read here. The two halves are paired by the `<KEY>` between the prefix and the suffix.
FIXTURE_NAME = re.compile(r'^#define\s+FIXTURE_(\w+)_NAME\s+"([^"]+)"')
SIZE_MACRO = "FIXTURE_{key}_BYTES"
PERIOD_MACRO = "FIXTURE_PATTERN_PERIOD"


def fixture_spec():
    """(name -> size in bytes, pattern period), read out of prg/fixtures.h in the header's order."""
    values = defines(FIXTURES_HEADER)
    sizes = {}
    for line in FIXTURES_HEADER.read_text().splitlines():
        found = FIXTURE_NAME.match(line.strip())
        if found:
            key, name = found.group(1), found.group(2)
            # A KeyError here names the macro that is missing, which is the point of not defaulting.
            sizes[name] = values[SIZE_MACRO.format(key=key)]
    if not sizes:
        raise SystemExit(f"REFUSED: {FIXTURES_HEADER} names no fixtures — has its format changed?")
    return sizes, values[PERIOD_MACRO]


def pattern(size, period):
    """The byte at offset N is N modulo `period`; see prg/fixtures.h for why it is not zeroes."""
    return bytes((offset % period) for offset in range(size))


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    sizes, period = fixture_spec()
    for name, size in sizes.items():
        (out / name).write_bytes(pattern(size, period))
        print(f"{name:<12} {size:>6} bytes")


if __name__ == "__main__":
    main()
