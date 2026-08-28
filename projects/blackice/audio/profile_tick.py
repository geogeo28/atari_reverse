#!/usr/bin/env python3
"""profile_tick.py — where the music tick's cycles go, from Hatari's own CPU profiler.

    python3 profile_tick.py              per-symbol cycles for the audio code (AUDIOTEST.PRG)
    python3 profile_tick.py --blackice   the same, for BICETEST.PRG and the BLACK ICE score
    python3 profile_tick.py --addresses  ...and the per-instruction breakdown inside the tick

The .PRG's own 200 Hz measurement (verify.py's "tick within budget") says WHAT the tick costs; this
says WHERE, which is the only way to spend an optimisation usefully. Every number in REPORT.md's
"what the tick costs" table came out of here.

TWO RUNS, because a .PRG's load address is whatever TOS had free and cannot be known host-side. The
first reads `text_probe` out of the ledger — the runtime address of one known symbol — and the ELF's
symbols are then placed at that base for the second. Same ROM, same drive, same memsize, so the two
runs land at the same base; the profile names nothing if they ever do not, which is a loud failure.
"""
import argparse
import os
import pathlib
import re
import struct
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"
BUILD = HERE / "build"
DISK = HERE / "disk"

# The one symbol both runs agree on: audiotest.c publishes its runtime address in the ledger.
ANCHOR_SYMBOL = "audio_vbl_tick"
# Where the profile window closes. It is called exactly once, on the way out, after the frame loop
# and the benchmark — so the window covers the whole run.
WINDOW_END_SYMBOL = "audio_leave_supervisor"
TICK_SYMBOL = "ym_music_tick"

# Fields of audiotest.c's ledger, by their u32 index, for the two numbers this file reads out of it.
LEDGER_TEXT_PROBE_INDEX = 2
LEDGER_FRAMES_RUN_INDEX = 7
LEDGER_BENCH_TICK_ITERATIONS_INDEX = 11
NM_KINDS = set("TtDdBbRr")

CALLER_ROW_RE = re.compile(r"^0x([0-9a-f]+):.*?, (\w+)$")
# One call site: its address, how many arrivals, the entry KIND, and — only for a real subroutine
# call — the inclusive and exclusive calls/instructions/cycles triples.
CALLER_SITE_RE = re.compile(r"0x([0-9a-f]+) = (\d+) (\w)"
                            r"(?: (\d+)/(\d+)/(\d+) (\d+)/(\d+)/(\d+))?")
SUBROUTINE_CALL = "s"
ADDRESS_ROW_RE = re.compile(r"^([0-9a-f]{8})\s+(.*?)\s+[\d.]+% \((\d+), (\d+), \d+, \d+\)$")


def run_hatari(run, extra, log_name):
    """One headless run of `run` (a verify.py RunProfile), with the same machine, ROM and length
    that verify.py gives it — the options live in that file and are imported, not restated."""
    args = ["hatari", "--machine", "ste", "--tos", str(VERIFY.BUNDLED_EMUTOS),
            "--country", VERIFY.COUNTRY, "--sound", "off", "--fast-forward", "on",
            "--confirm-quit", "off", "--statusbar", "off", "--drive-led", "off",
            "--memsize", "1", "--monitor", "rgb",
            "--run-vbls", str(run.frames + VERIFY.EMUTOS_BOOT_VBLS),
            "--harddrive", str(DISK), "--auto", f"C:\\{run.prg}"] + extra
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    done = subprocess.run(args, env=env, stdin=subprocess.DEVNULL, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    OUT.mkdir(exist_ok=True)
    (OUT / log_name).write_text(done.stdout)
    return done.stdout


def elf_for(run):
    """The linked ELF behind a run's .PRG. The Makefile links build/<stem>.elf into
    disk/<STEM>.PRG, so the .PRG's own name is where the stem comes from."""
    return BUILD / f"{run.prg.split('.')[0].lower()}.elf"


def elf_symbols(elf):
    """{name: (link-time offset, type letter, size)} — `nm -S`, because the --addresses listing
    needs to know how far a function REACHES and not only where it starts. A symbol the assembler
    gave no `.size` (every routine in the two .s/.S files) prints three fields instead of four and
    gets a size of 0; nothing here anchors on one of those."""
    rows = subprocess.run(["m68k-elf-nm", "-S", str(elf)], text=True, capture_output=True).stdout
    symbols = {}
    for line in rows.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[2] in NM_KINDS:
            symbols[parts[3]] = (int(parts[0], 16), parts[2].upper(), int(parts[1], 16))
        elif len(parts) == 3 and parts[1] in NM_KINDS:
            symbols[parts[2]] = (int(parts[0], 16), parts[1].upper(), 0)
    return symbols


def ledger_fields(run):
    """The probe run's ledger as a tuple of u32s — the load address and the tick counts come from
    the machine that ran, not from constants here."""
    run.ledger.unlink(missing_ok=True)
    run_hatari(run, [], f"profile-probe{run.suffix}.log")
    if not run.ledger.exists():
        raise SystemExit("FAIL: the probe run left no ledger to read the load address out of")
    raw = run.ledger.read_bytes()
    return struct.unpack(f">{len(raw) // 4}I", raw[:len(raw) // 4 * 4])


def load_base(symbols, ledger):
    """Where TOS put our text, measured rather than assumed."""
    return ledger[LEDGER_TEXT_PROBE_INDEX] - symbols[ANCHOR_SYMBOL][0]


def tick_calls(ledger):
    """How many times ym_music_tick ran inside the profile window, which is what the per-instruction
    listing divides by. It is BOTH sources: the window closes at the teardown, so it spans the frame
    loop (one tick per vblank) AND the benchmark loop that follows it. Dividing by the frames alone
    would report the demo's tick three times more expensive than it is."""
    return ledger[LEDGER_FRAMES_RUN_INDEX] + ledger[LEDGER_BENCH_TICK_ITERATIONS_INDEX]


def profile(run, symbols, base, dump_commands, log_name):
    symbol_file = OUT / f"symbols{run.suffix}.txt"
    symbol_file.write_text("".join("%08x %s %s\n" % (address, kind, name)
                                   for name, (address, kind, _) in sorted(symbols.items(),
                                                                          key=lambda i: i[1][0])))
    dump = OUT / f"profile-dump{run.suffix}.ini"
    dump.write_text("\n".join(dump_commands + ["q"]) + "\n")
    script = OUT / f"profile-on{run.suffix}.ini"
    script.write_text("\n".join([
        "symbols autoload off",
        f"symbols {symbol_file} ${base:x}",
        "profile on",
        f"b pc = ${base + symbols[WINDOW_END_SYMBOL][0]:x} :once :quiet :file {dump}",
        "c"]) + "\n")
    return run_hatari(run, ["--parse", str(script)], log_name)


def print_callers(log):
    """One row per CALL SITE, not per symbol, and the difference matters.

    Hatari charges a site's cycles to the site, and a tail call (`b`, a branch the compiler turned a
    `jsr` into) arrives with no totals at all — its cycles are already inside its caller's. Summing
    the arrival counts across sites, which is the obvious thing to do, therefore reports a function
    called twice as often as it was and half the cost. The authoritative per-frame number is not
    here in any case: it is verify.py's "tick within budget", measured by the .PRG itself."""
    print(f"  {'symbol':<20} {'call site':>10} {'arrivals':>9} {'incl cycles':>12} {'per call':>9}")
    for line in log.splitlines():
        row = CALLER_ROW_RE.match(line)
        if not row:
            continue
        for site in CALLER_SITE_RE.finditer(line):
            arrivals, kind, cycles = int(site.group(2)), site.group(3), site.group(6)
            if kind != SUBROUTINE_CALL or cycles is None:
                print(f"  {row.group(2):<20} 0x{site.group(1):>8} {arrivals:9d} "
                      f"{'-':>12} {'-':>9}   ({kind})")
                continue
            # Divided by the ARRIVALS and not by the inclusive triple's own call field: that field
            # counts a tail call at both ends and reads exactly half the true cost.
            print(f"  {row.group(2):<20} 0x{site.group(1):>8} {arrivals:9d} {int(cycles):12d} "
                  f"{int(cycles) / max(arrivals, 1):9.1f}")


def print_addresses(log, first, last, ticks):
    """The per-instruction rows inside [first, last) — the profiler lists from a start address to
    the end of the profiled region, so the function's own extent is what bounds it.

    The bound used to be a hard-coded address prefix, which silently listed nothing the day the
    program was linked anywhere else; hence the refusal at the bottom rather than an empty table."""
    rows = []
    for line in log.splitlines():
        row = ADDRESS_ROW_RE.match(line)
        if row and first <= int(row.group(1), 16) < last:
            rows.append((row.group(1), int(row.group(4)), int(row.group(3)), row.group(2)))
    if not rows:
        raise SystemExit(f"FAIL: the profile lists no instruction inside {first:#x}..{last:#x} — "
                         f"either the window never opened or the symbols were placed at the wrong "
                         f"base, and an empty table would read as a function that costs nothing")
    total = sum(row[1] for row in rows)
    print(f"  {len(rows)} instruction addresses, {total} cycles, {total / ticks:.1f} a tick "
          f"over {ticks} calls")
    for address, cycles, count, text in sorted(rows, key=lambda r: -r[1])[:20]:
        print(f"  {address}  {cycles / ticks:7.1f} cyc/tick  n={count:6d}  {text[:70]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--blackice", action="store_true",
                        help="profile BICETEST.PRG and the BLACK ICE score instead of the demo")
    parser.add_argument("--addresses", action="store_true",
                        help="also list the hottest instructions inside the tick")
    parser.add_argument("--ticks", type=int, default=None,
                        help="divide the address listing by this many tick calls "
                             "(default: the ledger's own frames_run + bench_tick_iterations)")
    args = parser.parse_args()

    run = (VERIFY.blackice_profile(VERIFY.read_band_speeds()) if args.blackice
           else VERIFY.demo_profile())
    elf = elf_for(run)
    if not elf.exists():
        raise SystemExit(f"FAIL: no {elf} — run `make` first")
    symbols = elf_symbols(elf)
    ledger = ledger_fields(run)
    base = load_base(symbols, ledger)
    ticks = args.ticks if args.ticks is not None else tick_calls(ledger)
    print(f"{run.prg}: our text is at {base:#x} (anchored on {ANCHOR_SYMBOL})")

    log = profile(run, symbols, base, ["profile stats", "profile callers"],
                  f"profile-callers{run.suffix}.log")
    print_callers(log)
    if args.addresses:
        offset, _, size = symbols[TICK_SYMBOL]
        if size == 0:
            raise SystemExit(f"FAIL: {TICK_SYMBOL} has no size in the ELF, so there is no range to "
                             f"list — it is not a C function any more")
        log = profile(run, symbols, base, [f"profile addresses ${base + offset:x}"],
                      f"profile-addresses{run.suffix}.log")
        print()
        print(f"inside {TICK_SYMBOL} ({base + offset:#x}..{base + offset + size:#x}):")
        print_addresses(log, base + offset, base + offset + size, ticks)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    import verify as VERIFY          # noqa: E402  (the run options live in one place, not two)
    sys.exit(main())
