#!/usr/bin/env python3
"""tosbench.py — run TOSBENCH.PRG under a ROM and read back the timing ledger it leaves in RAM.

    python3 tosbench.py capture [--rom PATH]             one run -> out/tosbench-*
    python3 tosbench.py golden  [--rom PATH] [--runs N]  N runs -> golden/, with the measured spread
    python3 tosbench.py compare [--rom PATH]             one run -> a ratio against the golden

WHAT A COMPARISON MEANS HERE, AND IT IS NOT WHAT TOSTEST'S MEANS. A conformance ledger is diffed;
a timing ledger cannot be, because a number that has a spread has no identity to diff against. So
`golden` runs the program SEVERAL times, records every run, and stores the MEDIAN as the reference
alongside the spread — and the spread is the whole point: it is the noise floor, and a ratio inside
it is not a finding whatever the charter's bar says. The bar is <= 1.05 per workload; a spread wider
than 5% would mean the instrument cannot see the bar at all, which is a fact worth knowing before
anyone tunes anything.

TWO CLOCKS PER WORKLOAD, AND BOTH ARE COMPARED: `_hz_200` (timer C, 200 a second) and `_frclock`
(vertical blanks, 50 or 60 a second depending on `palmode`). They come from different interrupts, so
a workload that moved in one and not the other says something about the TIMER rather than about the
workload — see tosbench/tosbench.c's header — and a driver that ratio'd only one would report a
rebuilt timer C as a uniform slowdown. The noise floor is per clock too, and they are not alike:
measured over five runs of the original, the widest tick spread is 1.57 % (Fread) and the widest
vblank spread is 2.13 % (Bconout).

A RATIO IS ONLY A READING IF THE RUN WORKED. The program publishes a status word and a FAILED flag
per row, and a failed workload still leaves a number behind — the loop it did not finish took some
time to not finish. So `compare` gates on the status, on every row's flag and on the iteration
counts matching the golden's BEFORE it prints a ratio, and it diffs the screen the workloads drew:
a run that failed is a red verdict that names why, never "within the bar".

WHAT THIS IS NOT. It is not Tier 3's per-function half: that one runs the compiled C under the
Musashi oracle and reports a cycle ratio per function. This is the whole-ROM half — what a program
running on the machine actually waits for — and the two answer different questions. A per-function
ratio inside the bar and a workload ratio outside it means the cost is in the composition.
"""
import argparse
import concurrent.futures
import json
import statistics
import sys
import time
from pathlib import Path

import hatari_rom
import ledger_run
from hatari_rom import GOLDEN, OUT, capture_prefix, refuse, require_files

DISK = hatari_rom.HERE / "build" / "TOSBENCH.ST"
PROGRAM = hatari_rom.HERE / "build" / "TOSBENCH.PRG"
GOLDEN_STEM = "tosbench"
COLUMNS = ("hz200 ticks", "iterations", "vblanks")
TITLE = "TOSBENCH performance ledger: three workloads on the machine's own two clocks"

# How many runs `golden` takes. FIVE, AND THREE WAS MEASURABLY TOO FEW: a three-run golden reported
# the Fread workload's spread as 0.07% and the very next run came back at 1.002 — outside it. A
# spread over N runs is a LOWER BOUND on the noise, and the bound has to be wide enough that a
# reading just outside it is not read as a regression. The runs overlap — each in its own work
# directory — which costs about 9 s of wall clock against 22 s in a row.
GOLDEN_RUNS = 5
# ...BUT THEY MUST NOT START TOGETHER, AND THIS IS THE INSTRUMENT'S OWN CHARACTER. MEASURED: five
# runs launched in the same instant read Fread as 1360 ticks FIVE TIMES (spread 0.00 %), and the
# same five started a second apart read 1380 / 1299 / 1369 / 1327 / 1283 (spread 7.28 %) — the
# emulated floppy's rotational phase comes from the host clock at launch, so simultaneous runs are
# ONE reading taken five times. A golden taken that way would publish a noise floor of zero and the
# very next comparison would read ordinary floppy noise as a regression.
RUN_STAGGER_SECONDS = 1.0
# The charter's Tier 3 on-target bar: recreate / original, per workload.
TIER3_BAR = 1.05

TICKS_PER_SECOND = 200          # _hz_200, by definition

# The two clocks a workload is timed on, and the key each takes in a reading. Both, always: they
# come from different interrupts (timer C and the vertical blank), so a workload that moved on one
# and not the other is a finding about the TIMER and not about the workload.
CLOCKS = ("ticks", "vblanks")


def capture(rom, prefix, log_name):
    return ledger_run.capture(rom, DISK, ledger_run.LEDGER_KIND_BENCH, prefix, COLUMNS, TITLE,
                              log_name, program=PROGRAM)


def capture_runs(rom, runs):
    """`runs` captures of the same ROM, overlapping but STARTED APART. Each has its own prefix, work
    directory and log, which is what makes them independent files; the stagger is what makes them
    independent readings."""
    def staggered(index):
        time.sleep(index * RUN_STAGGER_SECONDS)
        return capture(rom, OUT / f"tosbench-golden{index}", f"tosbench-golden{index}.log")

    with concurrent.futures.ThreadPoolExecutor(max_workers=runs) as pool:
        return list(pool.map(staggered, range(runs)))


def workloads(metrics):
    """{name: {'ticks', 'iterations', 'vblanks'}} — one entry per record, keyed by the name the
    program itself wrote, so a workload added on target needs no change here."""
    return {record["name"]: {"ticks": record["v0"],
                             "iterations": record["v1"],
                             "vblanks": record["v2"],
                             "failed": bool(record["flags"] & ledger_run.FLAG_FAILED)}
            for record in metrics["records"]}


def describe(metrics):
    rom = metrics["instrument"]["rom"]
    lines = [f"  ROM {rom['version']}  sha256 {rom['sha256'][:16]}...",
             f"  {'workload':<10} {'ticks':>8} {'seconds':>9} {'vblanks':>8} {'iterations':>11}"]
    for name, work in workloads(metrics).items():
        lines.append(f"  {name:<10} {work['ticks']:>8} {work['ticks'] / TICKS_PER_SECOND:>9.3f} "
                     f"{work['vblanks']:>8} {work['iterations']:>11}"
                     f"{'  FAILED' if work['failed'] else ''}")
    return "\n".join(lines)


def spread(values):
    """The median and the relative spread of one workload's measurements across runs.

    `relative_spread` is (max - min) / median: the width of the noise, in the same units as the
    ratio the bar is expressed in, so the two can be read against each other directly.
    """
    median = statistics.median(values)
    return {
        "runs": values,
        "median": median,
        "min": min(values),
        "max": max(values),
        "relative_spread": (max(values) - min(values)) / median if median else 0.0,
    }


def do_capture(rom, prefix):
    metrics = capture(rom, prefix, "tosbench-capture.log")
    print(f"TOSBENCH under {rom} -> {prefix}-*")
    print(describe(metrics))
    print()
    print(Path(f"{prefix}-ledger.txt").read_text(), end="")
    return 0


def workload_reference(captures, name):
    """One workload's reference: what the runs agreed on (the iteration count, which is the
    workload's identity) and what they spread over (each clock)."""
    reference = {"iterations": workloads(captures[0])[name]["iterations"]}
    for clock in CLOCKS:
        reference[clock] = spread([workloads(metrics)[name][clock] for metrics in captures])
    return reference


def do_golden(rom, runs):
    captures = capture_runs(rom, runs)
    names = [tuple(workloads(metrics)) for metrics in captures]
    if len(set(names)) != 1:
        refuse(f"the {runs} runs reported different workloads: {names}")
    for index, metrics in enumerate(captures):
        broken = ledger_run.failures(metrics["header"], metrics["records"])
        if broken:
            refuse(f"run {index} did not pass and a golden must not be taken from it:\n    "
                   + "\n    ".join(broken))

    reference = {
        "instrument": captures[0]["instrument"],
        "runs": runs,
        "screen": captures[0]["screen"],
        "workloads": {name: workload_reference(captures, name) for name in names[0]},
    }
    GOLDEN.mkdir(parents=True, exist_ok=True)
    (GOLDEN / f"{GOLDEN_STEM}-metrics.json").write_text(json.dumps(reference, indent=2) + "\n")
    ledger_run.write_golden(OUT / "tosbench-golden0", GOLDEN_STEM, names=("screen.png",))
    # The ledger TEXT of one run is not a golden: `compare` cannot diff a table of numbers that move
    # by design, so a copy of it in golden/ would be a claim nothing ever checks. A stale one from
    # before this was true is removed rather than left to be read as evidence.
    (GOLDEN / f"{GOLDEN_STEM}-ledger.txt").unlink(missing_ok=True)

    print(f"TOSBENCH golden from {rom}, {runs} runs")
    print(f"  {'workload':<10} {'clock':>8} {'median':>8} {'min':>8} {'max':>8} {'spread':>8}")
    for name, work in reference["workloads"].items():
        for clock in CLOCKS:
            measured = work[clock]
            print(f"  {name:<10} {clock:>8} {measured['median']:>8.0f} {measured['min']:>8} "
                  f"{measured['max']:>8} {measured['relative_spread']:>7.2%}")
    bar = TIER3_BAR - 1
    print("\n  NOISE FLOOR, PER CLOCK — a ratio inside it is not a finding whatever the bar says:")
    for clock in CLOCKS:
        widest_name, widest = max(((name, work[clock]["relative_spread"])
                                   for name, work in reference["workloads"].items()),
                                  key=lambda entry: entry[1])
        verdict = "the instrument can see the bar" if widest < bar else \
                  "WIDER THAN THE BAR: the instrument CANNOT see the bar on this clock"
        print(f"    {clock:<8} widest {widest:.2%} ({widest_name}) against a {bar:.0%} bar — {verdict}")
    print(f"\n  -> golden/{GOLDEN_STEM}-metrics.json")
    return 0


def clock_verdict(ratio, noise):
    """(is it over the bar, what to print) for one ratio, against the bar and against the measured
    noise on the SAME clock — a ratio inside the noise is not a finding whatever the bar says."""
    if ratio <= TIER3_BAR:
        return False, "within the bar"
    if ratio - 1 <= noise:
        return False, "over the bar but inside the noise floor"
    return True, f"OVER THE BAR ({TIER3_BAR:.2f})"


def do_compare(rom):
    reference = ledger_run.golden_metrics(GOLDEN_STEM)
    metrics = capture(rom, OUT / "tosbench-compare", "tosbench-compare.log")
    moved = hatari_rom.instrument_differences(reference.get("instrument"), metrics["instrument"])
    if moved:
        refuse("this run was not taken with the golden's instrument, so any ratio below would be "
               "the instrument's and not the ROM's:\n    " + "\n    ".join(moved))
    print(f"TOSBENCH: {rom} against golden/ ({reference['runs']} reference runs)")
    print(describe(metrics))

    # EVERY WAY THE RUN CAN FAIL TO BE A READING, BEFORE ANY RATIO IS PRINTED. A workload that
    # failed or that ran a different number of iterations still leaves a number behind, and a
    # comparison that takes it at face value reports a broken run as a performance result.
    measured = workloads(metrics)
    broken = ledger_run.failures(metrics["header"], metrics["records"])
    missing = sorted(set(reference["workloads"]) - set(measured))
    if missing:
        broken.append(f"this run reported no {missing} workload; the ledgers are not comparable")
    broken += [f"{name} ran {measured[name]['iterations']} iterations and the golden's ran "
               f"{work['iterations']} — the two are not the same workload"
               for name, work in reference["workloads"].items()
               if name in measured and measured[name]["iterations"] != work["iterations"]]
    if broken:
        print("\nTHIS RUN IS NOT A READING:\n  " + "\n  ".join(broken))
        return 1

    print(f"\n  {'workload':<10} {'clock':>8} {'golden':>8} {'this':>8} {'ratio':>7}  "
          f"{'spread':>7}  verdict")
    over_bar = []
    for name, work in reference["workloads"].items():
        for clock in CLOCKS:
            median, noise = work[clock]["median"], work[clock]["relative_spread"]
            ratio = measured[name][clock] / median if median else 0.0
            over, verdict = clock_verdict(ratio, noise)
            if over:
                over_bar.append(f"{name} ({clock})")
            print(f"  {name:<10} {clock:>8} {median:>8.0f} {measured[name][clock]:>8} "
                  f"{ratio:>7.3f}  {noise:>6.2%}  {verdict}")

    # The screen the workloads drew on, for tostest.py's reason: the ledger says what the program
    # believed and the picture says what the machine did. It is a pinned surface, not a ratio.
    if reference["screen"]["sha256"] != metrics["screen"]["sha256"]:
        print(f"\nTHE SCREEN DIFFERS: golden sha256 {reference['screen']['sha256'][:16]}, this run "
              f"{metrics['screen']['sha256'][:16]} — the workloads did not draw what they drew "
              f"under the golden's ROM, whatever their timings say")
        return 1
    if over_bar:
        print(f"\n{len(over_bar)} reading(s) over the bar: {', '.join(over_bar)}")
        return 1
    print("\nEVERY WORKLOAD IS WITHIN THE BAR ON BOTH CLOCKS, AND THE SCREEN IS IDENTICAL.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("capture", "golden", "compare"))
    parser.add_argument("--rom", default=str(hatari_rom.ORIGINAL_ROM))
    parser.add_argument("--out", help="capture mode only: the path prefix the artefacts take")
    parser.add_argument("--runs", type=int, default=GOLDEN_RUNS,
                        help="golden mode: how many runs the median and spread come from")
    arguments = parser.parse_args()
    require_files((arguments.rom, "the ROM"), (DISK, "the floppy (make disks)"),
                  (PROGRAM, "the program the floppy carries (make prgs)"))
    OUT.mkdir(parents=True, exist_ok=True)
    prefix = capture_prefix(arguments.mode, arguments.out, OUT / "tosbench")
    if arguments.mode == "capture":
        return do_capture(arguments.rom, prefix)
    if arguments.mode == "golden":
        return do_golden(arguments.rom, arguments.runs)
    return do_compare(arguments.rom)


if __name__ == "__main__":
    sys.exit(main())
