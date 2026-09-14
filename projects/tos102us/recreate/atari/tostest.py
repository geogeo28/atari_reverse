#!/usr/bin/env python3
"""tostest.py — run TOSTEST.PRG under a ROM and read back the conformance ledger it leaves in RAM.

    python3 tostest.py capture [--rom PATH]     one run -> out/tostest-*
    python3 tostest.py golden  [--rom PATH]     two runs -> golden/, if they agree on every field
    python3 tostest.py compare [--rom PATH]     one run -> diffed against golden/

WHAT THIS PROVES AND WHAT IT DOES NOT. The ledger is a list of answers TOS gave to fixed questions:
return values, pointers into the OS's own memory, a directory walk, a CRC of the screen after the
console driver drew on it. Two ROMs whose ledgers are identical answered every one of those
questions the same way. That is Tier 2 of the charter — the COMPOSITION being equal — and it is a
different claim from Tier 1, where each function is proved equal to the original in isolation.

EVERY FIELD OF EVERY RECORD IS REQUIRED TO MATCH, except in rows the PROGRAM marked masked (today:
Tgetdate, because Hatari seeds the emulated clock from the host). A masked row still has to be
present, with its id and name — a timing that vanished is a difference even though its number is not.

`golden` RUNS TWICE AND WRITES NOTHING IF THE TWO DISAGREE, so the reproducibility the golden depends
on is proved by the same invocation rather than asserted in a comment.
"""
import argparse
import difflib
import sys
from pathlib import Path

import hatari_rom
import ledger_run
from hatari_rom import OUT, capture_prefix, refuse, require_files

DISK = hatari_rom.HERE / "build" / "TOSTEST.ST"
PROGRAM = hatari_rom.HERE / "build" / "TOSTEST.PRG"
GOLDEN_STEM = "tostest"
# What v0/v1/v2 mean for this program — tostest/tostest.c's header is canonical for the per-call
# detail; these are the column titles.
COLUMNS = ("return", "second", "third")
TITLE = "TOSTEST conformance ledger: the answers TOS gave to a fixed set of calls"


def capture(rom, prefix, log_name):
    return ledger_run.capture(rom, DISK, ledger_run.LEDGER_KIND_TEST, prefix, COLUMNS, TITLE,
                              log_name, program=PROGRAM)


def describe(metrics):
    header, rom = metrics["header"], metrics["instrument"]["rom"]
    failed = [record for record in metrics["records"] if record["flags"] & ledger_run.FLAG_FAILED]
    return (f"  ROM {rom['version']}  sha256 {rom['sha256'][:16]}...\n"
            f"  {header['record_count']} records, status={header['status']}"
            f"{'' if header['status'] == 0 else ' (a call did not do what the program asked)'}\n"
            f"  failed rows: {', '.join(r['name'] for r in failed) if failed else 'none'}\n"
            f"  screen: {metrics['screen']['distinct_colours']} distinct colours")


def ledger_diff(golden_path, candidate_path):
    left, right = Path(golden_path).read_text(), Path(candidate_path).read_text()
    if left == right:
        return None
    return "\n".join(list(difflib.unified_diff(left.splitlines(), right.splitlines(),
                                               str(golden_path), str(candidate_path),
                                               lineterm="", n=1))[:80])


def do_capture(rom, prefix):
    metrics = capture(rom, prefix, "tostest-capture.log")
    print(f"TOSTEST under {rom} -> {prefix}-*")
    print(describe(metrics))
    print()
    print(Path(f"{prefix}-ledger.txt").read_text(), end="")
    return 0


def do_golden(rom):
    first = capture(rom, OUT / "tostest-golden1", "tostest-golden1.log")
    second = capture(rom, OUT / "tostest-golden2", "tostest-golden2.log")
    print(f"TOSTEST golden candidate from {rom}")
    print(describe(first))
    # A golden is what every later ROM is held to, so it is taken from a run that WORKED: a failed
    # call answers something, and pinning that answer makes the failure the standard.
    for index, metrics in enumerate((first, second), start=1):
        broken = ledger_run.failures(metrics["header"], metrics["records"])
        if broken:
            print(f"\nRUN {index} DID NOT PASS — no golden written:\n  " + "\n  ".join(broken))
            return 1
    if ledger_run.comparable(first["records"]) != ledger_run.comparable(second["records"]):
        print("\nTWO RUNS OF THE SAME ROM DISAGREE — no golden written:")
        print(ledger_diff(OUT / "tostest-golden1-ledger.txt", OUT / "tostest-golden2-ledger.txt"))
        return 1
    if first["screen"]["sha256"] != second["screen"]["sha256"]:
        print("\nTWO RUNS OF THE SAME ROM DREW DIFFERENT SCREENS — no golden written")
        return 1
    written = ledger_run.write_golden(OUT / "tostest-golden1", GOLDEN_STEM)
    print(f"\ntwo runs agree on every unmasked field -> golden/{GOLDEN_STEM}-* written "
          f"({len(written)} files)")
    return 0


def do_compare(rom):
    reference = ledger_run.golden_metrics(GOLDEN_STEM)
    metrics = capture(rom, OUT / "tostest-compare", "tostest-compare.log")
    moved = hatari_rom.instrument_differences(reference.get("instrument"), metrics["instrument"])
    if moved:
        refuse("this run was not taken with the golden's instrument, so any difference below would "
               "be the instrument's and not the ROM's:\n    " + "\n    ".join(moved))
    print(f"TOSTEST: {rom} against golden/")
    print(describe(metrics))
    differences = []
    if ledger_run.comparable(reference["records"]) != ledger_run.comparable(metrics["records"]):
        differences.append(("ledger", ledger_diff(hatari_rom.GOLDEN / f"{GOLDEN_STEM}-ledger.txt",
                                                  OUT / "tostest-compare-ledger.txt")))
    if reference["screen"]["sha256"] != metrics["screen"]["sha256"]:
        differences.append(("screen.png", f"sha256 {reference['screen']['sha256'][:16]} vs "
                                          f"{metrics['screen']['sha256'][:16]}"))
    if not differences:
        print("\nEVERY UNMASKED FIELD AND THE SCREEN ARE IDENTICAL.")
        return 0
    print(f"\n{len(differences)} surface(s) differ:")
    for name, text in differences:
        print(f"\n-- {name}\n{text}")
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("capture", "golden", "compare"))
    parser.add_argument("--rom", default=str(hatari_rom.ORIGINAL_ROM))
    parser.add_argument("--out", help="capture mode only: the path prefix the artefacts take")
    arguments = parser.parse_args()
    require_files((arguments.rom, "the ROM"), (DISK, "the floppy (make disks)"),
                  (PROGRAM, "the program the floppy carries (make prgs)"))
    OUT.mkdir(parents=True, exist_ok=True)
    prefix = capture_prefix(arguments.mode, arguments.out, OUT / "tostest")
    if arguments.mode == "capture":
        return do_capture(arguments.rom, prefix)
    if arguments.mode == "golden":
        return do_golden(arguments.rom)
    return do_compare(arguments.rom)


if __name__ == "__main__":
    sys.exit(main())
