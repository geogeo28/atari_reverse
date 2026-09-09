#!/usr/bin/env python3
"""profile.py — WHAT AN ATTRACT FRAME COSTS, ours against the shipped FLYSHARK.PRG, function by
function.

`smoke.py` asks whether the reconstruction is CORRECT. This asks what it COSTS, and it asks both
binaries the same question on the same machine with the same instrument.

WHY THE ATTRACT SCREEN IS THE WINDOW. It is the only thing either binary does with no person at the
controls, and it is a real frame: `attract_poll` runs `scroll_advance`, rebuilds the text display
list and calls `render_frame` (`flyshark_main.c`, `title_frame_step`), which is the whole renderer —
the ring seam, both display-list passes, the overlay repaint, the publish, the tile band and the
restore replay. The pace `README.md` quotes comes from exactly this loop.

THE PACE IS THE HEADLINE AND IT IS A COUNT, NOT AN ESTIMATE. `render_frame` waits for the third
vertical blank of the frame it has just published (`../src/sprite.c`, `RENDER_FRAME_VBL_BUDGET`), so
a frame that fits its budget takes 3 vblanks and the game runs at 16.7 fps. A frame that overruns
does not degrade smoothly: it misses the budget, takes the `os_vsync` arm and lands on whatever
vblank it lands on. So `pace` reports the DISTRIBUTION of vblanks per frame, from a repeating
breakpoint on `render_frame` — Hatari prints `CPU=$pc, VBL=n, FrameCycles=m` on every debugger
entry, and a breakpoint whose action file is nothing but `cont` costs the emulated machine nothing.

`ours` and `original` are the Hatari CPU PROFILER over a window of the same length on both sides,
which is what says WHICH routines the cycles are in. Four Hatari facts, each load-bearing and each
learned in `projects/wonderboy/recreate/atari/profile.py` (whose header argues them at length;
`projects/zynaps/` and `projects/bubbleghost/` carry the other two copies):

  * SYMBOLS MUST BE LOADED BEFORE `profile on`, and `symbols autoload off` before THAT. Autoloading
    frees the table on every debugger entry; and the profiler's callsite buffer is SIZED at
    `profile on`, so symbols arriving after it get no slots and the callers report comes back empty.
  * PROFILING STOPS ON EVERY DEBUGGER ENTRY. So the window's own breakpoints are all that may fire
    inside it — no per-frame poke, no host-side `savebin` poll.
  * THE WINDOW CANNOT BE OPENED ON A VBLANK COUNT: `b VBL > N` fires during TOS's own boot. It is
    opened at a PC and closed with `b VBL > VBL :N`, whose hit count IS "N vblanks later".
  * A WRONG TEXT BASE DOES NOT COME BACK EMPTY. Hatari resolves a PC to the nearest symbol BELOW it,
    so every cycle is still attributed — to the wrong name, in silence. `pin_text_base` is what
    stops that, against the machine's own `e TEXT`.

THE PARSE HALF OF THIS FILE IS THE FOURTH COPY (`symbol_map`, `write_symbol_file`, `parse_callers`,
`base_name` and the dozen constants that describe Hatari's output format rather than any game). It
belongs in `tools/` beside `hatari_headless.py` and has not moved there; `../STATUS.md`'s
"Follow-ups the kit should absorb" carries the row.

Use:

    python3 atari/profile.py pace               # OUR cadence: vblanks per frame, and its spread
    python3 atari/profile.py original-pace      # ...the shipped binary's, the same way
    python3 atari/profile.py ours               # OUR per-symbol cycles over a 1000-vblank window
    python3 atari/profile.py original           # ...the shipped binary's, from names.txt symbols
    python3 atari/profile.py compare            # both profiles read back and ratioed

Every mode leaves its raw Hatari log and a `.json` of what was parsed out of it in `atari/out/`.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke                                                            # noqa: E402
sys.path.insert(0, str(smoke.REPO / "tools"))
from hatari_headless import (HeadlessSession, action_file, await_file,  # noqa: E402
                             locate_by_signature)

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
NM = "m68k-elf-nm"

# ---- the clock ---------------------------------------------------------------------------------
# Every debugger entry prints this, and it is the only clock the pace modes have.
DEBUGGER_ENTRY_RE = re.compile(r"CPU=\$([0-9a-f]+), VBL=(\d+), FrameCycles=(\d+)")
# FrameCycles restarts at each vblank, so an absolute cycle is VBL * CYCLES_PER_VBL + FrameCycles.
# The ST's PAL video frame is 512 cycles x 313 lines; the CPU's own fiftieth of a second is a hair
# more, and the one constant is used for every span so the readings agree with each other.
CYCLES_PER_VBL = 512 * 313
# The frame rate and the budget are `smoke.py`'s, which mirrors them from the cores. Spelling either
# again here would be the same value in two files that import each other.
VBL_HZ = smoke.VBL_HZ
FRAME_BUDGET_VBLS = smoke.VBLS_PER_FRAME_FLOOR

# WHY THE BREAKPOINT LINES ARE SPELT HERE and not through `hatari_headless.pc_breakpoint`, whose
# docstring says it is "the only place its spelling lives": that helper models a PLAIN repeating
# breakpoint, and two of this file's three are COUNTED one-shots (`:20 :once`, `:1000 :once`) that it
# has no parameter for. Spelling one of the three through it and two by hand would be worse than
# spelling all three the same way — the point of a single home is that a reader finds every
# occurrence at once. If Hatari's syntax moves, the three are `b pc = $…` and `b VBL > VBL` below.

# ---- the two sides' anchor ----------------------------------------------------------------------
# ONE NAME, BOTH SIDES: ours resolves through the linked ELF's symbols and the original's through
# ../names.txt, so neither address is written down here. `render_frame` is called exactly once per
# attract frame on both sides (`flyshark_main.c`'s `title_frame_step`, and 0x10594 in the original),
# which makes it both the pace clock and the frame counter inside a profile window.
FRAME_SYMBOL = "render_frame"
# ...and the symbol that says the ATTRACT frames have started. `render_frame` alone is not the
# attract screen: `title_attract_prescroll` calls it 108 times to fill the map in before the loop is
# entered, and those calls take a fifth of a vblank each because `prescroll_flag` short-circuits
# everything that draws a sprite or publishes a frame (`../src/sprite.c`). Measured, before this
# anchor existed: 108 of the first 126 arrivals were the prescroll's, and the pace they averaged
# into was 1.9 vblanks a frame against the 12 the attract screen really takes. `set_palette_game` is
# the LAST call `attract_poll` makes before its spin (0x1055e), on both sides, so the next arrival
# after it is the first real attract frame.
ATTRACT_SPIN_SYMBOL = "set_palette_game"
# ...and the one BSS symbol that says where a relocated program landed: `flyshark_main` fills the
# record's magic before it does anything else, so `g_record`'s address in RAM minus its link-time
# offset is the text base. `build.sh` asserts the symbol survives into every build.
RECORD_SYMBOL = "g_record"

# ---- how long each mode runs ---------------------------------------------------------------------
# Hatari's own deadline, well past anything here: both sides spend thousands of vblanks in TOS's
# boot and the game's own eight file loads before a frame is drawn.
PROFILE_RUN_VBLS = 200000
# How many frames a pace run collects before it stops driving. 120 of ours at ~4.6 vblanks each is
# ~11 emulated seconds and the original's are 4 each — but this instrument exists to measure a build
# that has REGRESSED as much as one that has improved, and at the campaign's opening pace of 13.6 the
# same 120 frames were ~33 seconds. The deadline below is sized for that, not for today.
PACE_FRAMES = 120
PACE_DEADLINE_SECONDS = 2400.0
# How often the driver looks at the growing log. Each look is a host-side read of a file Hatari is
# appending to and costs the emulated machine nothing.
POLL_SECONDS = 2.0
# How many polls with no new frame mean the run has stopped drawing rather than being slow.
STALL_POLLS = 15

# 1000 vblanks = 20 emulated seconds: ~63 frames of ours at the pace this campaign opened with, and
# ~333 of the original's — enough of both that no single frame's page change dominates a row.
WINDOW_VBLS = 1000
# Which arrival at `render_frame` opens it: past the prescroll and the first text page, so what is
# measured is a steady-state attract frame.
WINDOW_OPENS_AT_FRAME = 20
# The frame limit the profiled build is given. It must outlast the window on BOTH sides of a
# comparison and on a build that has since got faster — a faster frame is more frames in the same
# 1000 vblanks — so it is far above what any window can hold rather than tuned to one.
PROFILE_BUILD_FRAMES = 2000

# `nm` type letters worth giving Hatari: text, data and bss, local or global.
NM_SYMBOL_TYPES = "TtDdBb"
# ...MINUS the asm twins' span brackets. `../src/asm/*.S` marks each transcribed span with
# `<name>_body` / `<name>_body_end` so `../test/test_asm_sprite.py` can slice the assembled blob and
# compare it against the .PRG. They are MARKERS, never call targets — and `_body_end` sits at the
# first byte AFTER a span, which for bodies laid down back to back is the NEXT body's entry point.
# Since this report resolves a profiled call by ADDRESS and aggregates it by NAME, such a marker
# takes that entry point's row: measured here, `sprite_blit_w32_body`'s calls would come back under
# `sprite_blit_w16_body_end`. Dropping them is the fix, rather than moving a bracket that has to
# cover the span it claims to. (The lesson is `projects/zynaps/recreate/atari/profile.py`'s.)
SPAN_MARKER_RE = re.compile(r"_body(_end)?$")
# GCC's per-constant specialisation makes one function several symbols; a row here is the base name.
CLONE_SUFFIX_RE = re.compile(r"\.(constprop|isra|part|lto_priv)\.\d+$")

# The log's markers, echoed by the scripts so a parse is anchored after the moment it belongs to.
PROFILE_ON_ECHO = "FS_PROFILE_ON"
PROFILE_DUMP_ECHO = "FS_PROFILE_DUMP"
TEXT_VARIABLE = "TEXT"
HEX_VALUE_RE = re.compile(r"\$([0-9a-fA-F]+)\s*\(hex\)")
USED_CYCLES_RE = re.compile(r"- used cycles:\s*\n\s*(\d+)")
# The callers report: `0xADDR: 0xCALLER = N <type> [incl] [excl], ..., name`.
CALLEE_ROW_RE = re.compile(r"^0x[0-9a-f]+: ")
CALLER_RE = re.compile(r"0x[0-9a-f]+ = (\d+) ([a-z])((?: [\d/]+){0,2})")
SUBROUTINE_CALL = "s"          # the only entry type Hatari records inclusive/exclusive totals for
TOTALS_CYCLES_FIELD = 2        # a totals triple is calls/instructions/CYCLES

OURS, SHIPPED = "ours", "original"
TOP_ROWS = 20
NAME_COLUMN = 34
# A cycles-per-call ratio needs real call counts on both sides before it means anything.
MIN_RATIO_CALLS = 20

NAMES_TXT = smoke.PROJECT / "names.txt"
NAMES_FN_RE = re.compile(r"^fn\s+0x([0-9a-fA-F]+)\s+(\S+)", re.M)


# =================================================================================================
# Building, and the symbol maps
# =================================================================================================
def build(frames):
    """`build.sh smoke <frames>`, refused loudly — a stale .PRG profiled against a fresh map reads
    perfectly and names the wrong functions.

    THE SMOKE BUILD AND NOT THE PLAY ONE. The play build writes no files, which is what makes it a
    game and also means nothing says it has started; the smoke build's beacon is how this driver
    knows the moment to dump RAM in, and its record is what says where the program landed. Both are
    written outside any window measured here — the beacon before the first frame, the record at the
    teardown — and `run_should_stop()` is one compare a frame. `--build-frames` is far above what a
    window can hold, so the limit is never reached inside one.
    """
    print(f"building smoke {frames}...", flush=True)
    done = subprocess.run(["bash", str(HERE / "build.sh"), "smoke", str(frames)],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"FAIL: `build.sh smoke {frames}` exited {done.returncode}\n"
                         + (done.stdout + done.stderr)[-2000:])
    # ...AND IT IS LEFT ON THE STAGED DRIVE AND THE FLOPPY, which is what a person would play next.
    # `build.sh` writes disk/AUTO/FLYSHARK.PRG and disk/FLYSHARK.ST whichever mode it ran, so after
    # this the volume holds a program that writes files and stops after `frames` attract frames.
    # `smoke.py` refuses the opposite mistake by name and there is nothing to refuse here, so it is
    # said out loud instead.
    print(f"   disk/ now holds the SMOKE build ({frames}-frame limit) — run `bash "
          f"{HERE / 'build.sh'}` before playing it", flush=True)


def symbol_map(entries, source):
    """{name: (address, type letter)}, refusing a repeated NAME.

    Two addresses under one name would put another function's cycles on this one's row, silently:
    the profiler resolves a PC by ADDRESS and this report aggregates by NAME."""
    symbols = {}
    for name, address, kind in entries:
        if name in symbols:
            raise SystemExit(f"FAIL: {source} names {name} twice ({symbols[name][0]:#x} and "
                             f"{address:#x}) — this report aggregates by NAME, so one row would be "
                             f"charged with the other's cycles")
        symbols[name] = (address, kind)
    return symbols


def elf_symbols():
    """`nm` over the ELF build.sh left beside the .PRG, as {name: (link-time offset, letter)}."""
    elf = HERE / "build" / "flyshark.elf"
    if not elf.is_file():
        raise SystemExit(f"no {elf} — run `bash {HERE / 'build.sh'} smoke` first")
    rows = []
    for line in subprocess.run([NM, str(elf)], check=True, capture_output=True,
                               text=True).stdout.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[1] in NM_SYMBOL_TYPES \
                and not SPAN_MARKER_RE.search(fields[2]):
            rows.append((fields[2], int(fields[0], 16), fields[1].upper()))
    return symbol_map(rows, elf)


def names_txt_symbols():
    """../names.txt's `fn` lines as {name: (Ghidra address, 'T')}.

    These are GHIDRA addresses at the project's load base, not runtime PCs — the shipped .PRG is
    relocated wherever GEMDOS puts it — so the caller relocates them with the base it measured."""
    return symbol_map(((name, int(address, 16), "T")
                       for address, name in NAMES_FN_RE.findall(NAMES_TXT.read_text())), NAMES_TXT)


def write_symbol_file(symbols, path):
    """Hatari's symbol format — `<8 hex address> <letter> <name>`."""
    path.write_text("".join("%08x %s %s\n" % (address, kind, name)
                            for name, (address, kind) in sorted(symbols.items(),
                                                                key=lambda item: item[1][0])))
    return path


def symbol_at(symbols, name, source):
    if name not in symbols:
        raise SystemExit(f"FAIL: {source} carries no symbol named {name} — this measurement is "
                         f"anchored on it, so there is nothing to open a window at")
    return symbols[name][0]


def require_survived(status, log):
    """Refuse a measurement taken off a machine that did not survive the run.

    A profile of a crashed boot is not a slower frame, it is a different program, and it prints as a
    perfectly plausible table."""
    if status != 0:
        raise SystemExit(f"FAIL: Hatari exited with status {status} — see {log}")


# =================================================================================================
# Booting either side
# =================================================================================================
def session_for(media, name):
    """A headless Hatari on `media`, logging to `atari/out/<name>.log`.

    THE MACHINE IS `smoke.py`'S, argument for argument — same TOS, same 1 MB, same frameskips — so
    what is measured here is comparable with what is judged there. Only the run deadline differs,
    and it is the parameter `hatari_arguments` takes for this caller.
    """
    return HeadlessSession(smoke.hatari_arguments(media, OUT / f"{name}.trace", PROFILE_RUN_VBLS),
                           log_path=OUT / f"{name}.log", fifo_path=OUT / f"{name}.fifo",
                           work_dir=OUT / f"{name}.work")


def boot_our_side(session, log):
    """Wait for our .PRG to start, and answer the text base every symbol is measured from.

    GEMDOS relocates us to wherever the TPA fell, so the base is a run-time fact: the program writes
    its record's magic before anything else, and `g_record`'s link-time offset is in the ELF."""
    smoke.BEACON.unlink(missing_ok=True)
    if await_file(session, smoke.BEACON, "the program's beacon",
                  smoke.BEACON_DEADLINE_SECONDS) is None:
        smoke.give_up(f"{smoke.BEACON.name}, which a smoke build writes as its first act",
                      session.started, smoke.BEACON_DEADLINE_SECONDS, log)
    record_address, image_base = smoke.keep_looking(
        session, smoke.record_in_ram, "the program to reach its first instructions",
        smoke.LOCATE_DEADLINE_SECONDS, started=session.started, log=log,
        poll_seconds=smoke.OURS_POLL_SECONDS)
    symbols = elf_symbols()
    base = record_address - symbol_at(symbols, RECORD_SYMBOL, "the linked ELF")
    print(f"  text base {base:#x}, image base {image_base:#x}")
    return base, symbols


def boot_the_original(session, log):
    """...and the shipped binary's, found the way `smoke.py` finds it: its own TEXT in RAM."""
    session.wait(smoke.ORIGINAL_SETTLE_SECONDS)
    base = smoke.keep_looking(session,
                              lambda ram: locate_by_signature(ram, smoke.ORIGINAL_PRG),
                              "the original's TEXT to appear in RAM",
                              smoke.LOCATE_DEADLINE_SECONDS, started=session.started, log=log)
    print(f"  text base {base:#x}")
    return base


def our_media():
    return smoke.gemdos_drive(smoke.OURS_DRIVE)


def original_media():
    return smoke.gemdos_drive(smoke.ORIGINAL_DRIVE)


# =================================================================================================
# THE PACE — one repeating breakpoint, and what its arrivals mean
# =================================================================================================
def absolute_cycle(vbl, frame_cycles):
    return vbl * CYCLES_PER_VBL + frame_cycles


def debugger_entries(log_path):
    """Every `CPU=$pc, VBL=n, FrameCycles=m` the run printed, as (pc, vbl, cycle) triples."""
    return [(int(pc, 16), int(vbl), absolute_cycle(int(vbl), int(cycles)))
            for pc, vbl, cycles in DEBUGGER_ENTRY_RE.findall(Path(log_path).read_text())]


def pace_rows(log_path, frame_pc):
    """The run's frames as {vbls, cycles} rows — one per span between two `render_frame` arrivals.

    A SPAN IS THE WHOLE FRAME, work and wait together, because the wait is INSIDE `render_frame`
    (`publish_and_wait`) and a breakpoint on one symbol cannot cut it out. That is the right span for
    the pace: what the player sees is arrivals per second, and both sides are cut at the same place.
    """
    rows = []
    previous = None
    for pc, vbl, cycle in debugger_entries(log_path):
        if pc != frame_pc:
            continue
        if previous is not None:
            rows.append({"vbls": vbl - previous[0], "cycles": cycle - previous[1]})
        previous = (vbl, cycle)
    return rows


def frame_arrivals(log_path, frame_pc):
    """How many frames the growing log holds, counted without parsing it.

    A SUBSTRING COUNT RATHER THAN `debugger_entries`' REGEX, because this runs every couple of
    seconds over the whole growing log: the poll is O(run length) either way and so O(n^2) over a
    run, but the regex is about fifty times the constant. MEASURED, the logs it reads are 14-17 KB
    at today's pace, so the whole quadratic costs nothing — the note is here because this instrument
    exists to measure SLOWER builds, where the log grows with the run, and a regressed build walks
    back into it. The fix then is to keep the last read offset and count only the appended tail.
    (`projects/zynaps/recreate/atari/profile.py`'s `loop_arrivals` carries the same note against
    2.4 MB logs.)"""
    return Path(log_path).read_text(errors="replace").count(f"CPU=${frame_pc:x},")


def drive_until_frames(session, log_path, frame_pc, frames, doing):
    """Let the run go until `frames` arrivals are in the log, or it stops drawing."""
    deadline = time.monotonic() + PACE_DEADLINE_SECONDS
    arrivals, stalled = 0, 0
    while time.monotonic() < deadline:
        session.require_alive(doing)
        now = frame_arrivals(log_path, frame_pc)
        if now >= frames:
            return now
        # THE STALL COUNTER ONLY RUNS ONCE A FRAME HAS ARRIVED: counting from the first poll would
        # make a slow BOOT — eight files, off a host directory, before the first frame — look like a
        # stalled attract screen.
        stalled = stalled + 1 if now == arrivals and now else 0
        arrivals = now
        if stalled >= STALL_POLLS:
            print(f"   the run stopped drawing after {arrivals} of the {frames} frames asked for; "
                  f"measuring those", flush=True)
            return arrivals
        session.wait(POLL_SECONDS)
    raise SystemExit(f"FAIL: only {arrivals} of {frames} frames in "
                     f"{PACE_DEADLINE_SECONDS:.0f}s — {doing}")


def summarise_pace(side, rows):
    """One side's pacing row: the distribution, not just the mean."""
    if not rows:
        raise SystemExit(f"FAIL: {side}'s run produced no frames — the breakpoint never fired "
                         f"twice, so there is nothing to report")
    vbls = [row["vbls"] for row in rows]
    cycles = [row["cycles"] for row in rows]
    mean = sum(vbls) / len(vbls)
    return {"side": side, "frames": len(rows), "vbls_mean": mean,
            "vbls_min": min(vbls), "vbls_max": max(vbls),
            "vbls_distribution": {str(count): times
                                  for count, times in sorted(Counter(vbls).items())},
            "on_budget": sum(1 for count in vbls if count <= FRAME_BUDGET_VBLS),
            "cycles_mean": sum(cycles) / len(cycles),
            "cycles_min": min(cycles), "cycles_max": max(cycles),
            "fps": VBL_HZ / mean}


def print_pace(summary):
    print(f"-- {summary['side']}: {summary['frames']} frames")
    print(f"   vblanks per frame  mean {summary['vbls_mean']:.3f}  "
          f"min {summary['vbls_min']}  max {summary['vbls_max']}  "
          f"=> {summary['fps']:.2f} fps")
    print("   distribution       " + "  ".join(
        f"{count}x{times}" for count, times in sorted(summary["vbls_distribution"].items(),
                                                      key=lambda kv: int(kv[0]))))
    print(f"   on budget (<= {FRAME_BUDGET_VBLS})   {summary['on_budget']} of {summary['frames']}")
    print(f"   cycles per frame   mean {summary['cycles_mean']:.0f}  "
          f"min {summary['cycles_min']}  max {summary['cycles_max']}  "
          f"(one vblank is {CYCLES_PER_VBL})")


def arm_after_the_prescroll(session, work, spin_pc, breakpoint_line, name):
    """Arm `breakpoint_line` on the first arrival at the attract spin, and not before.

    ONE BREAKPOINT ARMING ANOTHER, because what this measurement is about does not start when the
    program does: everything before `set_palette_game` is the prescroll (see ATTRACT_SPIN_SYMBOL),
    and a window opened there measures the one thing on this screen that is NOT a frame.
    """
    session.arm(f"b pc = ${spin_pc:x} :once :quiet " + action_file(work, name, breakpoint_line))


def frame_and_spin_pcs(session, log, side):
    """(text base, the `render_frame` PC, the attract-spin PC, the symbol map) for one side.

    The MAP comes back with the PCs because the profile modes need it again to write Hatari's symbol
    file, and building it a second time means a second `nm` (or a second parse of `../names.txt`)
    over a program that cannot have changed since the first."""
    if side == OURS:
        base, symbols = boot_our_side(session, log)
        return (base, base + symbol_at(symbols, FRAME_SYMBOL, "the linked ELF"),
                base + symbol_at(symbols, ATTRACT_SPIN_SYMBOL, "the linked ELF"), symbols)
    base = boot_the_original(session, log)
    image_base = base - smoke.LOAD_BASE
    symbols = names_txt_symbols()
    return (base, image_base + symbol_at(symbols, FRAME_SYMBOL, NAMES_TXT),
            image_base + symbol_at(symbols, ATTRACT_SPIN_SYMBOL, NAMES_TXT), symbols)


def run_pace(side, frames):
    """Boot one side and clock every attract frame it draws."""
    name = f"pace-{side}"
    log = OUT / f"{name}.log"
    session = session_for(our_media() if side == OURS else original_media(), name)
    try:
        _, frame_pc, spin_pc, _ = frame_and_spin_pcs(session, log, side)
        keep_going = action_file(session.work, "FSCONT.INI")
        arm_after_the_prescroll(session, session.work, spin_pc,
                                f"b pc = ${frame_pc:x} :quiet {keep_going}", "FSPACE.INI")
        drive_until_frames(session, log, frame_pc, frames, f"waiting for {side} to draw frames")
    finally:
        require_survived(session.close(), log)
    return pace_rows(log, frame_pc)


# =================================================================================================
# THE PROFILER — a window of the same length on both sides
# =================================================================================================
def profile_on_commands(symbol_file, dump_clause, symbol_offset=None):
    """The window's OPENING commands, in the one order that works (see this file's header).

    `symbol_offset` is what Hatari adds to every address in the symbol file. OUR side's are
    link-time offsets into an ELF linked at 0, so it is the text base; the ORIGINAL's are relocated
    host-side, because Hatari's offset cannot be negative and the shipped .PRG lands well below the
    project's 0x10000 load base."""
    return [f"echo {PROFILE_ON_ECHO}",
            # Asked BEFORE the symbols are placed, so the log carries the machine's own answer for
            # `pin_text_base` to check the placement against.
            f"e {TEXT_VARIABLE}",
            "symbols autoload off",
            f"symbols {symbol_file}" + (f" ${symbol_offset:x}" if symbol_offset else ""),
            "profile on",
            f"b VBL > VBL :{WINDOW_VBLS} :once :quiet {dump_clause}"]


def dump_script(work, side):
    """The window's CLOSING action file: report, then QUIT — the one that does not `cont`.

    `profile stats` carries the one number the callers report does not: the cycles the whole window
    spent, which is what a per-frame cost is a share of. Quitting here is also what keeps the log to
    ONE callers report, which the parse below relies on."""
    return action_file(work, f"FSDUMP-{side}.INI", f"echo {PROFILE_DUMP_ECHO}",
                       "profile stats", "profile callers", tail="q")


def after_the_dump(log_text):
    """Everything the log printed from the window's CLOSING script onwards.

    Anchored on the echo rather than on the first match in the file, because the debugger prints a
    `profile stats` of its own when the buffers are allocated and a parse that took the first one
    would read an empty window as a full one."""
    at = log_text.find(PROFILE_DUMP_ECHO)
    if at < 0:
        raise SystemExit(f"FAIL: the log carries no {PROFILE_DUMP_ECHO} echo — the window's closing "
                         f"script never ran, so nothing was reported")
    return log_text[at:]


def window_cycles(log_text):
    """Every profiled region's used cycles, summed — TOS's ROM included, on both sides alike."""
    return sum(int(value) for value in USED_CYCLES_RE.findall(after_the_dump(log_text)))


def base_name(symbol):
    """A GCC clone's base name — the suffix is a naming artefact of the pass, never a distinction
    the original made."""
    return CLONE_SUFFIX_RE.sub("", symbol)


def parse_callers(log_text):
    """{name: {calls, cycles}} out of `profile callers`.

    Hatari attaches cycle totals only to SUBROUTINE arrivals, so a function entered by `bra`/`jmp`
    carries none and its cost is folded into the `jsr`-entered ancestor that reached it. Those rows
    come back with 0 calls and 0 cycles rather than being invented."""
    rows = {}
    for line in after_the_dump(log_text).splitlines():
        if not CALLEE_ROW_RE.match(line):
            continue
        name = base_name(line.rsplit(",", 1)[-1].strip())
        row = rows.setdefault(name, {"calls": 0, "cycles": 0})
        for calls, kind, totals in CALLER_RE.findall(line):
            if kind != SUBROUTINE_CALL:
                continue
            fields = totals.split()
            row["calls"] += int(calls)
            if fields:
                inclusive = fields[0].split("/")
                if len(inclusive) > TOTALS_CYCLES_FIELD:
                    row["cycles"] += int(inclusive[TOTALS_CYCLES_FIELD])
    return rows


def pin_text_base(log_text, expected):
    """PIN the text base the symbols were placed for against the one the profiled run actually used.

    A WRONG BASE DOES NOT COME BACK EMPTY (see this file's header): every row would name the wrong
    function and the table would look exactly like a right one."""
    on = log_text.find(PROFILE_ON_ECHO)
    if on < 0:
        raise SystemExit(f"FAIL: the log carries no {PROFILE_ON_ECHO} echo — the window's opening "
                         f"script never ran, so nothing was profiled")
    reported = HEX_VALUE_RE.search(log_text, on)
    if not reported:
        raise SystemExit(f"FAIL: the debugger printed no value for `e {TEXT_VARIABLE}` — the load "
                         f"address cannot be pinned, and a wrong one mis-attributes every row "
                         f"without failing anything")
    if int(reported.group(1), 16) != expected:
        raise SystemExit(f"FAIL: the profiled run's text is at {int(reported.group(1), 16):#x} but "
                         f"its symbols were placed for {expected:#x} — every row would name the "
                         f"wrong function")


def profile_result(side, log, text_base):
    """One side's parsed window, saved beside its log so `compare` can read it back."""
    text = Path(log).read_text(errors="replace")
    pin_text_base(text, text_base)
    functions = parse_callers(text)
    if not functions:
        raise SystemExit(f"FAIL: {side}'s callers report is empty — the symbols reached the "
                         f"profiler after `profile on` sized its callsite buffer")
    frames = functions.get(FRAME_SYMBOL, {}).get("calls", 0)
    result = {"side": side, "window_vbls": WINDOW_VBLS, "window_cycles": window_cycles(text),
              "frames": frames, "functions": functions}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"profile-{side}.json").write_text(json.dumps(result, indent=1, sort_keys=True))
    return result


def await_window(session, log_path):
    """Drive the run until the window has opened AND closed — the log's two echoes say so.

    THE ONLY WAY OUT WITHOUT AN ECHO IS THE EMULATOR HAVING QUIT, and that is not a success: the
    closing script ends in `q`, so a run that reached the dump has already gone and a run that died
    before it has not. `require_survived` on the caller's `close()` is what tells the two apart."""
    deadline = time.monotonic() + PACE_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        text = Path(log_path).read_text(errors="replace") if Path(log_path).exists() else ""
        if PROFILE_DUMP_ECHO in text:
            session.wait(POLL_SECONDS)
            return
        if not session.alive():
            return
        session.wait(POLL_SECONDS)
    raise SystemExit(f"FAIL: the profile window never closed — see {log_path}")


def run_profile(side):
    """Open a WINDOW_VBLS window at the same frame on either side and report what it held."""
    name = f"profile-{side}"
    log = OUT / f"{name}.log"
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        session = session_for(our_media() if side == OURS else original_media(), name)
        try:
            base, frame_pc, spin_pc, symbols = frame_and_spin_pcs(session, log, side)
            if side == OURS:
                symbol_file = write_symbol_file(symbols, OUT / f"{name}.sym")
                opening = profile_on_commands(symbol_file, dump_script(work, side), base)
            else:
                # ../names.txt's addresses are GHIDRA addresses at the project's 0x10000 load base,
                # and the shipped .PRG lands BELOW that — so Hatari's own offset would have to be
                # negative, which it cannot be. Each is relocated here instead.
                relocated = {symbol: (base - smoke.LOAD_BASE + address, kind)
                             for symbol, (address, kind) in symbols.items()}
                symbol_file = write_symbol_file(relocated, OUT / f"{name}.sym")
                opening = profile_on_commands(symbol_file, dump_script(work, side))
            arm_after_the_prescroll(
                session, work, spin_pc,
                f"b pc = ${frame_pc:x} :{WINDOW_OPENS_AT_FRAME} :once :quiet "
                + action_file(work, f"FSON-{side}.INI", *opening), f"FSARM-{side}.INI")
            await_window(session, log)
        finally:
            require_survived(session.close(), log)
    return profile_result(side, log, base)


def print_profile(result):
    """One side's window: the total, the frames in it, and the top functions by cycles."""
    total, frames = result["window_cycles"], result["frames"]
    if not frames:
        raise SystemExit(f"FAIL: {result['side']}'s window holds no call to {FRAME_SYMBOL} — its "
                         f"frames cannot be counted, so a cycles-per-frame figure would be an "
                         f"invention")
    print(f"-- {result['side']}: {frames} frames inside a {WINDOW_VBLS}-vblank window, "
          f"{total} cycles profiled => {total / frames:.0f} cycles/frame")
    print(f"   {'function':<{NAME_COLUMN}} {'cycles':>12} {'%':>6} {'calls':>8} {'cyc/call':>9} "
          f"{'cyc/frame':>10}")
    for name, row in sorted(result["functions"].items(), key=lambda kv: -kv[1]["cycles"])[:TOP_ROWS]:
        share = 100.0 * row["cycles"] / total if total else 0.0
        per_call = row["cycles"] / row["calls"] if row["calls"] else 0
        print(f"   {name:<{NAME_COLUMN}} {row['cycles']:>12} {share:>6.2f} {row['calls']:>8} "
              f"{per_call:>9.0f} {row['cycles'] / frames:>10.0f}")


def load_json(name):
    path = OUT / name
    if not path.is_file():
        raise SystemExit(f"FAIL: no {path} — run the mode that writes it first")
    return json.loads(path.read_text())


# The suffix an asm twin's symbol carries (`../src/asm/*.S`). A twin IS the routine — the same work,
# transcribed from the original's own instructions — so it has to be ratioed against the original's
# row for the routine it stands in for, or the very functions a wave rewrote drop out of the table.
#
# TODAY'S ONE TWIN STILL DOES NOT RATIO, and that is a property of the twin rather than a gap here:
# `blit_sprite_rows_unclipped_asm` stands in for FOUR of the original's routines
# (`sprite_blit_w16`..`w64`, which the original's caller picks between with a jump table), so there
# is no single shipped row to divide by and a per-call ratio would not mean anything. Its cycles are
# compared in `../STATUS.md`'s "On-target performance" table instead, per FRAME, where the four are
# summed on both sides. The rename below is kept because it is what the next twin will need.
ASM_TWIN_SUFFIX = "_asm"


def with_asm_twins_renamed(functions):
    """Our side's rows under the ORIGINAL's names, so a twin ratios against what it replaced.

    A name is SUMMED rather than overwritten because both spellings can be present: the C core is
    still compiled and linked (it is what the differential pins the twin against), so it has a
    symbol — with, in a correct build, no samples against it at all."""
    renamed = {}
    for name, row in functions.items():
        key = name[:-len(ASM_TWIN_SUFFIX)] if name.endswith(ASM_TWIN_SUFFIX) else name
        into = renamed.setdefault(key, {"calls": 0, "cycles": 0})
        into["calls"] += row["calls"]
        into["cycles"] += row["cycles"]
    return renamed


def compare():
    """Both windows read back, and the ratio at each function both sides name."""
    ours, theirs = load_json(f"profile-{OURS}.json"), load_json(f"profile-{SHIPPED}.json")
    for side in (ours, theirs):
        if not side["frames"]:
            raise SystemExit(f"FAIL: out/profile-{side['side']}.json holds no frames — re-run "
                             f"`profile.py {side['side']}`, whose window measured nothing")
    ours_per_frame = ours["window_cycles"] / ours["frames"]
    theirs_per_frame = theirs["window_cycles"] / theirs["frames"]
    print(f"-- cycles a frame: ours {ours_per_frame:.0f} over {ours['frames']} frames, the original "
          f"{theirs_per_frame:.0f} over {theirs['frames']} — "
          f"{ours_per_frame / theirs_per_frame:.2f}x")
    shared = []
    for name, row in with_asm_twins_renamed(ours["functions"]).items():
        other = theirs["functions"].get(name)
        if other is None or row["calls"] < MIN_RATIO_CALLS or other["calls"] < MIN_RATIO_CALLS:
            continue
        mine, yours = row["cycles"] / row["calls"], other["cycles"] / other["calls"]
        shared.append((mine / yours, name, mine, yours, row["calls"]))
    shared.sort(reverse=True)
    print(f"   {'function':<{NAME_COLUMN}} {'ours/call':>10} {'orig/call':>10} {'ratio':>7} "
          f"{'calls':>8}")
    for ratio, name, mine, yours, calls in shared[:TOP_ROWS]:
        print(f"   {name:<{NAME_COLUMN}} {mine:>10.0f} {yours:>10.0f} {ratio:>7.2f} {calls:>8}")
    # ...AND SAY WHICH TWINS COULD NOT BE RATIOED. A twin that stands in for several of the
    # original's routines has no single shipped row to divide by, so it drops out of the table
    # above — and a reader running this after landing one can reasonably read its absence as the
    # twin not being linked at all. Name them instead.
    unratioed = sorted(name for name in ours["functions"]
                       if name.endswith(ASM_TWIN_SUFFIX)
                       and name[:-len(ASM_TWIN_SUFFIX)] not in theirs["functions"])
    for name in unratioed:
        row = ours["functions"][name]
        print(f"   ({name}: {row['cycles'] / ours['frames']:.0f} cycles a frame over "
              f"{row['calls']} calls, and NO ratio — it stands in for more than one of the "
              f"original's routines, so there is no single row to divide by)")
    if not shared:
        print(f"   (no function is called at least {MIN_RATIO_CALLS} times on both sides — nothing "
              f"to ratio)")


PACE, ORIGINAL_PACE, COMPARE = "pace", "original-pace", "compare"
MODES = (PACE, ORIGINAL_PACE, OURS, SHIPPED, COMPARE)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--frames", type=int, default=PACE_FRAMES,
                        help="how many frames a pace run collects")
    parser.add_argument("--build-frames", type=int, default=PROFILE_BUILD_FRAMES,
                        help="the frame limit the profiled smoke build is given")
    parser.add_argument("--no-build", action="store_true",
                        help="measure the .PRG that is already staged (a bisection wants this)")
    options = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    if options.mode == COMPARE:
        compare()
        return 0
    side = OURS if options.mode in (PACE, OURS) else SHIPPED
    if side == OURS and not options.no_build:
        build(options.build_frames)

    if options.mode in (PACE, ORIGINAL_PACE):
        summary = summarise_pace(side, run_pace(side, options.frames))
        (OUT / f"pace-{side}.json").write_text(json.dumps(summary, indent=1))
        print_pace(summary)
        return 0
    print_profile(run_profile(side))
    return 0


if __name__ == "__main__":
    sys.exit(main())
