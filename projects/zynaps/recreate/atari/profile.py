"""WHERE THE FRAME'S CYCLES GO — the reconstruction's pacing and its cost, against the shipped
binary's own, on the same machine and with the same instrument.

`smoke.py` asks whether the port is CORRECT. This asks whether it is FAST ENOUGH, which for this
program is one number: **how many vertical blanks one `frame_loop_once` takes.** The frame loop is
released by `vbl_menu`, which clears the wait flag on every SECOND vertical blank (../src/irq.c —
the count-up-and-wrap at 0x13c26), so a frame that fits its budget takes exactly 2 and the game runs
at 25 fps on a 50 Hz machine. A frame that overruns does NOT degrade smoothly: it misses the release
and waits for the next one, so the cadence is quantised to 2, 4, 6, ... and the DISTRIBUTION is the
finding rather than the mean.

THE INSTRUMENT IS A BREAKPOINT, NOT A STOPWATCH. Hatari prints `CPU=$pc, VBL=n, FrameCycles=m` on
every debugger ENTRY, and a breakpoint whose action file is nothing but `cont` costs the emulated
machine no cycles at all. So two repeating `:quiet` breakpoints — one at the frame loop's head and
one at `screen_flip_buffers` — turn a run into a timeline of (work, wait) pairs measured on the
emulated clock, with no profiler and no sampling. `frames` and `original-frames` are that, and they
are what the pacing rows of README.md's Performance table come from.

`ours` and `original` are the Hatari CPU PROFILER over a window of the same length on both sides,
which is what says WHICH routines the work is in. Four Hatari facts, each load-bearing and each
learned in projects/wonderboy/recreate/atari/profile.py:

  * SYMBOLS MUST BE LOADED BEFORE `profile on`, and `symbols autoload off` before THAT. Autoloading
    frees the table on every debugger entry; and the profiler's callsite buffer is SIZED at
    `profile on`, so symbols arriving after it get no slots and the callers report comes back empty.
  * PROFILING STOPS ON EVERY DEBUGGER ENTRY. So the window's own breakpoints are all that may fire
    inside it — no per-frame poke, no host-side `savebin` poll, no fire driver.
  * THE WINDOW CANNOT BE OPENED ON A VBLANK COUNT: `b VBL > N` fires during TOS's own boot. It is
    opened at a PC and closed with `b VBL > VBL :N`, whose hit count IS "N vblanks later".
  * `:trace` prints no per-arrival line. A plain quiet breakpoint ENTRY is what prints the clock.

WHY OUR SIDE IS MEASURED IN THE `play` BUILD AND NOT THE ONE `smoke.py` JUDGES. `game` stops at 300
frames where a timeline asks for 600, and it writes 64 KB through GEMDOS at five of them — inside
the span these modes clock and inside the profiler's window. `play` is the same code with both
budgets out of reach and no samples declared, so what is measured is the game rather than the check
watching it. `--build game` is there for a bisection that needs the judged binary.

Use:

    python3 atari/profile.py frames             # OUR cadence: vblanks per frame, work, wait
    python3 atari/profile.py original-frames    # ...the shipped binary's, the same way
    python3 atari/profile.py ours               # OUR per-symbol cycles over a 1000-vblank window
    python3 atari/profile.py original           # ...the shipped binary's, from names.txt symbols
    python3 atari/profile.py compare            # both profiles read back and ratioed

Every mode leaves its raw Hatari log and a `.json` of what was parsed out of it in `atari/out/`.
"""
import argparse
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke                                                       # noqa: E402
sys.path.insert(0, str(smoke.REPO / "tools"))
from hatari_headless import HeadlessSession, action_file, poke_byte   # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

# ---- the clock ---------------------------------------------------------------------------------
# Every debugger entry prints this, and it is the only clock these modes have.
DEBUGGER_ENTRY_RE = re.compile(r"CPU=\$([0-9a-f]+), VBL=(\d+), FrameCycles=(\d+)")
# FrameCycles restarts at each vblank, so an absolute cycle is VBL * CYCLES_PER_VBL + FrameCycles.
# The ST's PAL video frame is 512 cycles x 313 lines; the CPU's own fiftieth of a second is a hair
# more, and the one constant is used for every span so the readings agree with each other.
CYCLES_PER_VBL = 512 * 313
# The frame rate and the release period are `smoke.py`'s, which pins the second against
# ../include/irq.h's RASTER_PHASE_PERIOD. Spelling either again here would be the same value in two
# files that import each other, which is exactly what that pin exists to stop.
VBL_HZ = smoke.VBL_HZ
FRAME_BUDGET_VBLS = smoke.PACING_RELEASE_PERIOD_VBLS

# ---- the two sides' anchors --------------------------------------------------------------------
# ONE NAME, BOTH SIDES. Ours resolves through the linked ELF's symbols and the original's through
# ../../names.txt, so neither address is written down here — the name map is the source of truth for
# the shipped side (CLAUDE.md's own rule) and a re-addressed routine moves both anchors together.
OUR_LOOP_SYMBOL = "frame_loop_once"
FLIP_SYMBOL = "screen_flip_buffers"
# How many times a FRAME flips. `frame_end_and_flip` calls `screen_flip_buffers` once, so a span
# between two loop-head arrivals holding any other number is not a frame — see `timeline`.
FLIPS_PER_FRAME = 1

# How many frames a timeline collects before it stops driving the run. 600 at the original's two
# vblanks each is 24 emulated seconds; ours takes longer, and the deadline is what stops a side that
# never reaches the loop at all.
TIMELINE_FRAMES = 600
TIMELINE_DEADLINE_SECONDS = 2400.0
# How often the driver looks at the growing log. Each look is a host-side read of a file Hatari is
# appending to and costs the emulated machine nothing.
TIMELINE_POLL_SECONDS = 2.0
# How many polls with no new frame mean the run has stopped playing rather than being slow. Twenty
# seconds: at the slowest cadence measured here a frame takes about a third of a second of emulated
# time and rather less of host time, so a minute's worth of margin over that is generous and a run
# parked in a screen no fire button leaves is caught in under half a minute.
TIMELINE_STALL_POLLS = 10
# NO MODE HERE READS A TRACE — the clock is the debugger's own entry lines and the profiler's
# report — and asking for one is not free even when nothing reads it: `smoke.py`'s flags left a
# 128 MB `frames-original.trace` behind on this script's first run, and `psg_write` alone makes
# Hatari format thousands of lines an emulated second. `trace_flags=None` leaves `--trace` off; the
# file argument still has to be passed and is never opened.
NO_TRACE = None
# ...but `hatari_arguments` still takes the path positionally, and it is never opened.
TRACE_UNUSED = Path(os.devnull)

# ---- the profiler's window ---------------------------------------------------------------------
# 1000 vblanks = 20 emulated seconds. At the original's 25 fps that is ~500 frames; at ours, ~87 —
# enough of both that no single frame's setup work dominates a row.
WINDOW_VBLS = 1000
# Which arrival at the frame loop opens it: far enough in that the section's first-frame work (the
# prefill, the panel repaint) is behind us and what is measured is a steady-state frame.
WINDOW_OPENS_AT_FRAME = 20
# The ceiling that stops a run which never reaches its anchor. Both sides spend thousands of
# vblanks in TOS's boot, the attract loop and the PREPARE FOR COMBAT wait before the window opens.
PROFILE_RUN_VBLS = 200000

# `nm` type letters worth giving Hatari: text, data and bss, local or global.
NM_SYMBOL_TYPES = "TtDdBb"
# GCC's per-constant specialisation makes one function several symbols; a row here is the base name.
CLONE_SUFFIX_RE = re.compile(r"\.(constprop|isra|part|lto_priv)\.\d+$")

# The log's markers, echoed by the scripts so a parse is anchored after the moment it belongs to.
PROFILE_ON_ECHO = "ZY_PROFILE_ON"
PROFILE_DUMP_ECHO = "ZY_PROFILE_DUMP"
TEXT_VARIABLE = "TEXT"
HEX_VALUE_RE = re.compile(r"\$([0-9a-fA-F]+)\s*\(hex\)")
USED_CYCLES_RE = re.compile(r"- used cycles:\s*\n\s*(\d+)")
# The callers report: `0xADDR: 0xCALLER = N <type> [incl] [excl], ..., name`.
CALLEE_ROW_RE = re.compile(r"^0x[0-9a-f]+: ")
CALLER_RE = re.compile(r"0x[0-9a-f]+ = (\d+) ([a-z])((?: [\d/]+){0,2})")
SUBROUTINE_CALL = "s"          # the only entry type Hatari records inclusive/exclusive totals for
TOTALS_CYCLES_FIELD = 2        # a totals triple is calls/instructions/CYCLES

OURS, SHIPPED = "ours", "original"
# WHICH BUILD OUR SIDE IS MEASURED IN, and it is `play` for both modes because `game` would put the
# HARNESS inside the measurement. `game` stops at ZY_GAME_FRAMES (300) where a timeline asks for
# 600, and it writes 64 KB through GEMDOS at frames 1, 30, 60, 120 and 240 — inside the loop-head to
# loop-head span `timeline` measures and inside the profiler's window, which opens at frame 20 and
# holds about 175. `play` declares no samples and has both budgets out of reach, so what either mode
# measures is the game rather than the check watching it.
PROFILE_BUILD = "play"
TOP_ROWS = 20
NAME_COLUMN = 38
# A cycles-per-call ratio needs real call counts on both sides before it means anything.
MIN_RATIO_CALLS = 20
# HOW MANY FRAMES A PROFILE WINDOW HELD, and the one counter that works on BOTH sides. The window
# cannot count its own frames — a per-frame breakpoint inside it is a debugger entry, and a debugger
# entry stops the profiler — so the count has to come out of the report itself. `frame_loop_once` is
# ours alone (the original's loop head is entered by `bra` and has no arrivals to count), but
# `frame_panel_scroll_and_ship_stage` calls exactly ONE of the twenty `scroll_page_to_screen_p*`
# entries per pass through the jump table at 0x179aa, on both sides. Measured: our report gives 155
# scroll calls against `frame_loop_once`'s own 155.
#
# IT IS ALSO HOW A CUT-SHORT WINDOW IS SEEN. The original's window holds 72 frames of the ~500 its
# vblanks would buy, because the fire-poll breakpoints that press its start button are debugger
# entries too and one of them lands inside the window. A cycles-per-frame taken over the window's
# VBLANKS instead would have divided the same cycles by seven times the frames and reported the
# shipped binary at a seventh of its real cost.
FRAME_COUNTER_PREFIX = "scroll_page_to_screen_p"

NAMES_TXT = smoke.PROJECT / "names.txt"
NAMES_FN_RE = re.compile(r"^fn\s+0x([0-9a-fA-F]+)\s+(\S+)", re.M)


# =================================================================================================
# Building, and the symbol maps
# =================================================================================================
def build(mode):
    """`build.sh <mode>`, refused loudly — a stale .PRG profiled against a fresh map reads fine."""
    print(f"building {mode}...", flush=True)
    done = subprocess.run(["bash", str(HERE / "build.sh"), mode], capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"FAIL: `build.sh {mode}` exited {done.returncode}\n"
                         + (done.stdout + done.stderr)[-2000:])


def require_survived(status, log):
    """Refuse a measurement taken off a machine that did not survive the run.

    THE ONLY CALLER OF THIS HARNESS THAT QUITS ITSELF IS THIS FILE — the profiler's closing script
    ends in `q` — so `close()` returns Hatari's own exit status here rather than the driver's.
    `smoke.py`'s five sessions all check theirs; a profile of a crashed boot is not a slower frame,
    it is a different program, and it prints as a perfectly plausible table.
    """
    if status != 0:
        raise SystemExit(f"FAIL: Hatari exited with status {status} — see {log}")


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


def elf_symbols(mode):
    """`nm` over the ELF build.sh left beside the .PRG, as {name: (link-time offset, letter)}."""
    elf = HERE / "build" / f"zynaps-{mode}.elf"
    if not elf.is_file():
        raise SystemExit(f"no {elf} — run `bash {HERE / 'build.sh'} {mode}` first")
    rows = []
    for line in subprocess.run([smoke.NM, str(elf)], check=True, capture_output=True,
                               text=True).stdout.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[1] in NM_SYMBOL_TYPES:
            rows.append((fields[2], int(fields[0], 16), fields[1].upper()))
    return symbol_map(rows, elf)


def names_txt_symbols():
    """../../names.txt's `fn` lines as {name: (Ghidra address, 'T')}.

    These are GHIDRA addresses at ../project.toml's load base, not runtime PCs — the shipped .PRG is
    relocated wherever GEMDOS puts it — so the caller places them with the base it measured, which
    is what Hatari's `symbols <file> $<offset>` takes."""
    return symbol_map(((name, int(address, 16), "T")
                       for address, name in NAMES_FN_RE.findall(NAMES_TXT.read_text())), NAMES_TXT)


def write_symbol_file(symbols, path):
    """Hatari's symbol format — `<8 hex address> <letter> <name>`."""
    path.write_text("".join("%08x %s %s\n" % (address, kind, name)
                            for name, (address, kind) in sorted(symbols.items(),
                                                                key=lambda item: item[1][0])))
    return path


def symbol_pc(symbols, name, source):
    if name not in symbols:
        raise SystemExit(f"FAIL: {source} carries no symbol named {name} — this measurement is "
                         f"anchored on it, so there is nothing to open a window at")
    return symbols[name][0]


# =================================================================================================
# THE TIMELINE — two repeating breakpoints, and what their arrivals mean
# =================================================================================================
def absolute_cycle(vbl, frame_cycles):
    return vbl * CYCLES_PER_VBL + frame_cycles


def debugger_entries(log_path):
    """Every `CPU=$pc, VBL=n, FrameCycles=m` the run printed, as (pc, vbl, cycle) triples."""
    return [(int(pc, 16), int(vbl), absolute_cycle(int(vbl), int(cycles)))
            for pc, vbl, cycles in DEBUGGER_ENTRY_RE.findall(Path(log_path).read_text())]


def timeline(log_path, loop_pc, flip_pc):
    """The run's frames as {vbls, work, wait} rows, from the two breakpoints' arrivals.

    A FRAME IS LOOP-HEAD TO LOOP-HEAD, and the flip inside it splits that span in two. The first
    half is the frame's computing PLUS `frame_end_and_flip`'s wait on `A_raster_phase`, which stands
    before `screen_flip_buffers`; the second is its wait on `A_vbl_wait_flag`, which stands after.
    So `work` is an upper bound on the frame's real cost and `wait` is a lower bound on its real
    idle — the split a breakpoint on one symbol can make, and enough to compare the two sides, which
    are cut at the same place.

    A span WITHOUT EXACTLY ONE FLIP IN IT IS NOT A FRAME AND IS DROPPED — measured, not assumed. A
    first draft kept the last flip of every span, which quietly admitted the section-restart chain:
    `section_advance` through `section_start_tail` flips buffers of its own, so the span from the
    last frame of a life to the first of the next holds several, and keeping the last one charged
    that row's `work` with the whole restart. Those are the 247- and 489-vblank rows in the README's
    table, and their cycles were inflating `work_mean` on both sides. Zero flips is the other shape:
    a frame that left through an exit before flipping, or a run whose breakpoints were armed
    mid-frame."""
    rows = []
    pending = None
    flips = []
    for pc, vbl, cycle in debugger_entries(log_path):
        if pc == flip_pc:
            flips.append(cycle)
            continue
        if pc != loop_pc:
            continue
        if pending is not None and len(flips) == FLIPS_PER_FRAME:
            rows.append({"vbls": vbl - pending[0],
                         "work": flips[0] - pending[1],
                         "wait": cycle - flips[0]})
        pending = (vbl, cycle)
        flips = []
    return rows


def summarise_timeline(side, rows):
    """The pacing table's row for one side: the distribution, not just the mean."""
    if not rows:
        raise SystemExit(f"FAIL: {side}'s run produced no complete frames — the breakpoints never "
                         f"bracketed one, so there is nothing to report")
    vbls = [row["vbls"] for row in rows]
    work = [row["work"] for row in rows]
    distribution = sorted(Counter(vbls).items())
    return {"side": side, "frames": len(rows),
            "vbls_mean": sum(vbls) / len(vbls),
            "vbls_min": min(vbls), "vbls_max": max(vbls),
            "vbls_distribution": {str(count): times for count, times in distribution},
            "on_budget": sum(1 for count in vbls if count <= FRAME_BUDGET_VBLS),
            "work_mean": sum(work) / len(work),
            "work_min": min(work), "work_max": max(work),
            "fps": VBL_HZ / (sum(vbls) / len(vbls))}


def print_timeline(summary):
    """One side's pacing, in the shape README.md's Performance table wants."""
    print(f"-- {summary['side']}: {summary['frames']} frames")
    print(f"   vblanks per frame  mean {summary['vbls_mean']:.3f}  "
          f"min {summary['vbls_min']}  max {summary['vbls_max']}  "
          f"=> {summary['fps']:.2f} fps")
    print("   distribution       " + "  ".join(f"{count}x{times}"
          for count, times in sorted(summary["vbls_distribution"].items(), key=lambda kv: int(kv[0]))))
    print(f"   on budget (<= {FRAME_BUDGET_VBLS})   "
          f"{summary['on_budget']} of {summary['frames']} "
          f"({100.0 * summary['on_budget'] / summary['frames']:.1f}%)")
    print(f"   work cycles/frame  mean {summary['work_mean']:.0f}  "
          f"min {summary['work_min']}  max {summary['work_max']}  "
          f"(one vblank is {CYCLES_PER_VBL})")


def timeline_breakpoints(session, work, loop_pc, flip_pc):
    """The two clocks. `cont` and nothing else, so neither costs the machine a cycle."""
    session.arm(f"b pc = ${loop_pc:x} :quiet " + action_file(work, "ZYLOOP.INI"))
    session.arm(f"b pc = ${flip_pc:x} :quiet " + action_file(work, "ZYFLIP.INI"))


def loop_arrivals(log_path, loop_pc):
    """How many loop-head arrivals the growing log holds, counted without parsing it.

    A SUBSTRING COUNT RATHER THAN `debugger_entries`' REGEX, because this runs every couple of
    seconds over the whole growing log: the poll is O(run length) either way and so O(n^2) over a
    run, but the regex is about fifty times the constant. Measured, the logs it reads are 2.4 MB and
    205 KB, so at today's `--frames 600` the whole quadratic costs well under a second — the note is
    here because a slower future build, which is what this instrument exists for, walks back into
    it, and the fix then is to keep the last read offset and count only the appended tail."""
    return Path(log_path).read_text(errors="replace").count(f"CPU=${loop_pc:x},")


def drive_until_frames(session, log_path, loop_pc, frames, doing, press=None):
    """Let the run go until `frames` loop-head arrivals are in the log, pressing fire in the waits.

    IT STOPS EARLY WHEN THE RUN STOPS PLAYING, and that is not a compromise: a timeline asks for 600
    frames and both binaries lose their third life somewhere before that and sit in a screen no fire
    button leaves (the shipped one enters its name-entry screen, ours waits on the same byte). The
    frames already collected are the measurement; what would be wrong is reporting the REQUEST as if
    it had been met, so the count that came back is returned and the caller prints it.
    """
    deadline = time.monotonic() + TIMELINE_DEADLINE_SECONDS
    arrivals, stalled_polls = 0, 0
    while time.monotonic() < deadline:
        session.require_alive(doing)
        now = loop_arrivals(log_path, loop_pc)
        if now >= frames:
            return now
        # THE STALL COUNTER ONLY RUNS ONCE A FRAME HAS ARRIVED. Counting from the first poll would
        # make a slow BOOT look like a stalled game: our side does not reach the frame loop's head
        # until vertical blank ~2,230, and TIMELINE_STALL_POLLS is twenty seconds of HOST time —
        # so on a machine where headless Hatari is not comfortably faster than real time, the run
        # would be given up on before it had started and reported as "stopped playing after 0".
        stalled_polls = stalled_polls + 1 if now == arrivals and now else 0
        arrivals = now
        if stalled_polls >= TIMELINE_STALL_POLLS:
            print(f"   the run stopped playing after {arrivals} of the {frames} frames asked for; "
                  f"measuring those", flush=True)
            return arrivals
        if press is not None:
            press()
        session.wait(TIMELINE_POLL_SECONDS)
    raise SystemExit(f"FAIL: only {arrivals} of {frames} frames in "
                     f"{TIMELINE_DEADLINE_SECONDS:.0f}s — {doing}")


# =================================================================================================
# BOOTING EITHER SIDE — the four drivers below open the same two machines, so they open them here
# =================================================================================================
def session_for(medium, name, work):
    """A headless Hatari on `medium`, logging to `atari/out/<name>.log` and asking for no trace."""
    return HeadlessSession(
        smoke.hatari_arguments(medium, TRACE_UNUSED, smoke.DEFAULT_MACHINE, smoke.TOS_ROM,
                               PROFILE_RUN_VBLS, trace_flags=NO_TRACE),
        log_path=OUT / f"{name}.log", fifo_path=OUT / f"{name}.fifo", work_dir=work)


def our_offsets(build_mode):
    """The four link-time offsets both of our drivers place their breakpoints and reads from."""
    return smoke.symbol_offsets(build_mode, OUR_LOOP_SYMBOL, smoke.ANCHOR_SYMBOL, "zy_image_base",
                                "g_phase")


def boot_our_side(session, offsets):
    """Wait for our .PRG to publish its anchor, and answer where it and its image landed.

    GEMDOS relocates us to wherever the TPA fell, so both are run-time facts: the program writes
    `zy_anchor`'s address into BASE.BIN before its file loads, and the image is a `.bss` array whose
    pointer the shim publishes for this to read."""
    _, anchor_offset, image_pointer, _ = offsets
    session.wait(smoke.BASE_POLL_START_SECONDS)
    base_file = smoke.await_file(session, smoke.OUR_DISK / smoke.BASE_FILE,
                                 "waiting for the program to start")
    base = struct.unpack(">I", base_file.read_bytes()[:smoke.VECTOR_BYTES])[0] - anchor_offset
    image = struct.unpack(">I", session.savebin("image.bin", base + image_pointer,
                                                smoke.VECTOR_BYTES))[0]
    return base, image


def phase_gated_press(session, base, image, phase_field):
    """OUR side's fire button, pressed only while the program is NOT in its frame loop.

    The same guard `smoke.run_ours_game` uses and for the same reason: `g_phase` is PLAYING for the
    whole of the frame loop and nothing else, so a poke made under it cannot land inside a frame and
    change what is being measured."""
    def press():
        phase = struct.unpack(">I", session.savebin("phase.bin", base + phase_field,
                                                    smoke.VECTOR_BYTES))[0]
        if phase != smoke.PHASE_PLAYING:
            session.poke(image + smoke.GHIDRA_JOYSTICK_STATE, smoke.JOYSTICK_FIRE)
    return press


def arm_original_fire_polls(session, work, base, prefix):
    """...and the ORIGINAL's, which is a repeating breakpoint on each of its two own fire polls.

    The PC reaches neither during a frame — both are inside a wait — so the press cannot perturb
    what is being measured. `smoke.py` arms the same pair for the frame differential."""
    joystick = smoke.runtime(base, smoke.GHIDRA_JOYSTICK_STATE)
    for index, site in enumerate((smoke.GHIDRA_SECTION_TAIL_FIRE_POLL,
                                  smoke.GHIDRA_ATTRACT_FIRE_POLL)):
        session.arm(f"b pc = ${smoke.runtime(base, site):x} :{smoke.FIRE_POLLS_PER_PRESS} :quiet "
                    + action_file(work, f"{prefix}FIRE{index}.INI",
                                  poke_byte(joystick, smoke.JOYSTICK_FIRE)))


def our_timeline(build_mode, frames):
    """OUR cadence: boot the build, start a game, and clock every frame of it."""
    build(build_mode)
    smoke.stage_our_build(build_mode)
    offsets = our_offsets(build_mode)
    loop_offset, phase_field = offsets[0], offsets[3]
    flip_offset = symbol_pc(elf_symbols(build_mode), FLIP_SYMBOL, f"the {build_mode} ELF")
    name = f"frames-{OURS}"
    log = OUT / f"{name}.log"
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        session = session_for(smoke.gemdos_medium(smoke.OUR_DISK, smoke.OUR_AUTO), name, work)
        try:
            base, image = boot_our_side(session, offsets)
            timeline_breakpoints(session, work, base + loop_offset, base + flip_offset)
            drive_until_frames(session, log, base + loop_offset, frames,
                               "waiting for our side to play out the timeline",
                               phase_gated_press(session, base, image, phase_field))
        finally:
            require_survived(session.close(), log)
    return timeline(log, base + loop_offset, base + flip_offset)


def original_timeline(frames):
    """...and the shipped binary's, clocked at the same two places by the same instrument."""
    name = f"frames-{SHIPPED}"
    log = OUT / f"{name}.log"
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        session = session_for(smoke.gemdos_medium(smoke.ORIGINAL_DISK, smoke.ORIGINAL_AUTO),
                              name, work)
        try:
            base = smoke.poll_for_program(session, smoke.ORIGINAL_PRG,
                                          "waiting for the original to be loaded")
            loop_pc = smoke.runtime(base, smoke.GHIDRA_FRAME_LOOP_HEAD)
            flip_pc = smoke.runtime(base, symbol_pc(names_txt_symbols(), FLIP_SYMBOL, NAMES_TXT))
            arm_original_fire_polls(session, work, base, "ZYT")
            timeline_breakpoints(session, work, loop_pc, flip_pc)
            drive_until_frames(session, log, loop_pc, frames,
                               "waiting for the original to play out the timeline")
        finally:
            require_survived(session.close(), log)
    return timeline(log, loop_pc, flip_pc)


# =================================================================================================
# THE PROFILER — a window of the same length on both sides
# =================================================================================================
def profile_on_commands(symbol_file, dump_clause, symbol_offset=None):
    """The window's OPENING commands, in the one order that works (see this file's header).

    `symbol_offset` is what Hatari adds to every address in the symbol file. OUR side's are link-time
    offsets into an ELF linked at 0, so it is the text base; the ORIGINAL's are ../../names.txt's
    Ghidra addresses, which this file relocates HOST-SIDE — Hatari's offset cannot be negative and
    the shipped .PRG lands well below ../project.toml's 0x10000 load base."""
    return [f"echo {PROFILE_ON_ECHO}",
            # Asked BEFORE the symbols are placed, so the log carries the machine's own answer for
            # `pin_text_base` to check the placement on the next line against.
            f"e {TEXT_VARIABLE}",
            "symbols autoload off",
            f"symbols {symbol_file}" + (f" ${symbol_offset:x}" if symbol_offset else ""),
            "profile on",
            f"b VBL > VBL :{WINDOW_VBLS} :once :quiet {dump_clause}"]


def dump_script(work, side):
    """The window's CLOSING action file: report, then QUIT — the one that does not `cont`.

    `profile stats` is kept because it carries the one number the callers report does not: the
    cycles the whole window spent, which is what a per-frame cost is a share of. Quitting here is
    also what keeps the log to ONE callers report, which the parse below relies on."""
    return action_file(work, f"ZYDUMP-{side}.INI", f"echo {PROFILE_DUMP_ECHO}",
                       "profile stats", "profile callers", tail="q")


def after_the_dump(log_text):
    """Everything the log printed from the window's CLOSING script onwards.

    Anchored on the echo rather than on the first match in the file, because the debugger prints a
    `profile stats` of its own when the buffers are allocated and a parse that took the first one
    would read an empty window as a full one. A log with no echo is a run whose window never closed,
    which is a refusal here and not an empty report — `str.find`'s -1 would otherwise slice off the
    last character and every count below would come back 0 with no reason given."""
    at = log_text.find(PROFILE_DUMP_ECHO)
    if at < 0:
        raise SystemExit(f"FAIL: the log carries no {PROFILE_DUMP_ECHO} echo — the window's closing "
                         f"script never ran, so nothing was reported")
    return log_text[at:]


def window_cycles(log_text):
    """Every profiled region's used cycles, summed.

    OUR side spends a percent or so of its window inside TOS's ROM, and a figure that quietly
    dropped that would flatter one side and not the other."""
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

    A WRONG BASE DOES NOT COME BACK EMPTY: Hatari resolves a PC to the nearest symbol BELOW it, so
    every cycle is still attributed — to the wrong name, in silence, with a report that looks
    exactly like a right one."""
    on = log_text.find(PROFILE_ON_ECHO)
    if on < 0:
        raise SystemExit(f"FAIL: the log carries no {PROFILE_ON_ECHO} echo — the window's opening "
                         f"script never ran, so nothing was profiled")
    reported = HEX_VALUE_RE.search(log_text, on)
    if not reported:
        raise SystemExit(f"FAIL: the debugger printed no value for `e {TEXT_VARIABLE}` — the load "
                         f"address cannot be pinned, and a wrong one mis-attributes every row "
                         f"without failing anything")
    reported = int(reported.group(1), 16)
    if reported != expected:
        raise SystemExit(f"FAIL: the profiled run's text is at {reported:#x} but its symbols were "
                         f"placed for a text base of {expected:#x} — every row would name the wrong "
                         f"function")


def profile_result(side, log, text_base):
    """One side's parsed window, saved beside its log so `compare` can read it back."""
    text = Path(log).read_text(errors="replace")
    pin_text_base(text, text_base)
    functions = parse_callers(text)
    result = {"side": side, "window_vbls": WINDOW_VBLS, "window_cycles": window_cycles(text),
              "frames": frames_in_window(functions), "functions": functions}
    if not result["functions"]:
        raise SystemExit(f"FAIL: {side}'s callers report is empty — the symbols reached the "
                         f"profiler after `profile on` sized its callsite buffer")
    (OUT / f"profile-{side}.json").write_text(json.dumps(result, indent=1, sort_keys=True))
    return result


def profile_ours(build_mode):
    """Profile OUR build over WINDOW_VBLS vblanks opened at the 20th frame."""
    build(build_mode)
    smoke.stage_our_build(build_mode)
    offsets = our_offsets(build_mode)
    loop_offset, phase_field = offsets[0], offsets[3]
    symbols = elf_symbols(build_mode)
    name = f"profile-{OURS}"
    log = OUT / f"{name}.log"
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        session = session_for(smoke.gemdos_medium(smoke.OUR_DISK, smoke.OUR_AUTO), name, work)
        try:
            base, image = boot_our_side(session, offsets)
            symbol_file = write_symbol_file(symbols, OUT / f"{name}.sym")
            session.arm(f"b pc = ${base + loop_offset:x} :{WINDOW_OPENS_AT_FRAME} :once :quiet "
                        + action_file(work, f"ZYON-{OURS}.INI",
                                      *profile_on_commands(symbol_file, dump_script(work, OURS),
                                                           base)))
            # THE FIRE DRIVER STOPS WHEN THE WINDOW OPENS, and it has to: every `savebin` it makes
            # is a debugger entry, and a debugger entry inside the window stops the profiler.
            await_window(session, log, phase_gated_press(session, base, image, phase_field))
        finally:
            require_survived(session.close(), log)
    return profile_result(OURS, log, base)


def profile_original():
    """...and the shipped binary's window, opened at the same frame with names.txt's symbols."""
    name = f"profile-{SHIPPED}"
    log = OUT / f"{name}.log"
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        session = session_for(smoke.gemdos_medium(smoke.ORIGINAL_DISK, smoke.ORIGINAL_AUTO),
                              name, work)
        try:
            base = smoke.poll_for_program(session, smoke.ORIGINAL_PRG,
                                          "waiting for the original to be loaded")
            loop_pc = smoke.runtime(base, smoke.GHIDRA_FRAME_LOOP_HEAD)
            # ../../names.txt's addresses are GHIDRA addresses at ../project.toml's 0x10000 load
            # base, and the shipped .PRG lands BELOW that — so the offset is negative and cannot go
            # to Hatari. Each is relocated here instead, and the file is loaded with no offset.
            relocated = {symbol: (smoke.runtime(base, address), kind)
                         for symbol, (address, kind) in names_txt_symbols().items()}
            symbol_file = write_symbol_file(relocated, OUT / f"{name}.sym")
            arm_original_fire_polls(session, work, base, "ZYP")
            session.arm(f"b pc = ${loop_pc:x} :{WINDOW_OPENS_AT_FRAME} :once :quiet "
                        + action_file(work, f"ZYON-{SHIPPED}.INI",
                                      *profile_on_commands(symbol_file,
                                                           dump_script(work, SHIPPED))))
            await_window(session, log, None)
        finally:
            require_survived(session.close(), log)
    return profile_result(SHIPPED, log, base)


def await_window(session, log_path, press):
    """Drive the run until the window has opened AND closed — the log's two echoes say so.

    THE ONLY WAY OUT WITHOUT AN ECHO IS THE EMULATOR HAVING QUIT, and that is not a success. The
    closing script ends in `q`, so a run that reaches the dump has already gone; a run that died
    before it has not, and returning quietly from here would hand `profile_result` a log with no
    echo, which would then be diagnosed as "the symbols reached the profiler after `profile on`" —
    a codegen story for a machine that crashed. `require_survived` on the caller's `close()` is what
    tells the two apart, so this returns and lets it look."""
    deadline = time.monotonic() + TIMELINE_DEADLINE_SECONDS
    opened = False
    while time.monotonic() < deadline:
        text = Path(log_path).read_text(errors="replace") if Path(log_path).exists() else ""
        if PROFILE_DUMP_ECHO in text:
            session.wait(TIMELINE_POLL_SECONDS)
            return
        if PROFILE_ON_ECHO in text:
            opened = True
        if not session.alive():
            return
        if press is not None and not opened:
            press()
        session.wait(TIMELINE_POLL_SECONDS)
    raise SystemExit(f"FAIL: the profile window never closed — see {log_path}")


# =================================================================================================
# The reports
# =================================================================================================
def frames_in_window(functions):
    """The window's frame count, from the one per-frame call both sides make (see the constant)."""
    return sum(row["calls"] for name, row in functions.items()
               if name.startswith(FRAME_COUNTER_PREFIX))


def print_profile(result):
    """One side's window: the total, the frames in it, and the top functions by cycles."""
    total = result["window_cycles"]
    frames = result["frames"]
    if not frames:
        raise SystemExit(f"FAIL: {result['side']}'s window holds no call to "
                         f"{FRAME_COUNTER_PREFIX}* — its frames cannot be counted, so a "
                         f"cycles-per-frame figure would be an invention")
    print(f"-- {result['side']}: {frames} frames inside a {WINDOW_VBLS}-vblank window, "
          f"{total} cycles profiled => {total / frames:.0f} cycles/frame")
    rows = sorted(result["functions"].items(), key=lambda kv: -kv[1]["cycles"])[:TOP_ROWS]
    print(f"   {'function':<{NAME_COLUMN}} {'cycles':>12} {'%':>6} {'calls':>8} {'cyc/call':>10} "
          f"{'cyc/frame':>10}")
    for name, row in rows:
        share = 100.0 * row["cycles"] / total if total else 0.0
        per_call = row["cycles"] / row["calls"] if row["calls"] else 0
        print(f"   {name:<{NAME_COLUMN}} {row['cycles']:>12} {share:>6.2f} "
              f"{row['calls']:>8} {per_call:>10.0f} {row['cycles'] / frames:>10.0f}")


def load_json(name):
    path = OUT / name
    if not path.is_file():
        raise SystemExit(f"FAIL: no {path} — run the mode that writes it first")
    return json.loads(path.read_text())


def with_scroll_blit_folded(functions):
    """The twenty scroll phases as ONE row, so the biggest item in the frame gets a ratio.

    The jump table at 0x179aa has twenty entries because the wrap point moves with the scroll
    position, and each is a separate body on BOTH sides — so they are not clones and `base_name`
    does not join them. But one call a frame goes to one of them, which means each entry alone is
    under `MIN_RATIO_CALLS` on the shipped side's shorter window and the routine that costs 30% of
    the frame would have no row in the ratio table at all.
    """
    folded = {name: row for name, row in functions.items()
              if not name.startswith(FRAME_COUNTER_PREFIX)}
    phases = [row for name, row in functions.items() if name.startswith(FRAME_COUNTER_PREFIX)]
    if phases:
        folded[FRAME_COUNTER_PREFIX + "*"] = {"calls": sum(row["calls"] for row in phases),
                                              "cycles": sum(row["cycles"] for row in phases)}
    return folded


def compare():
    """Both windows read back, and the ratio at each function both sides name."""
    ours, theirs = load_json(f"profile-{OURS}.json"), load_json(f"profile-{SHIPPED}.json")
    # A WINDOW WITH NO FRAMES IN IT REACHES DISK: `profile_result` saves the .json before
    # `print_profile` gets to refuse it, so a run whose window held no scroll-blit call leaves a
    # `"frames": 0` behind for this mode to read. Refuse it by name rather than dividing by it.
    for side in (ours, theirs):
        if not side["frames"]:
            raise SystemExit(f"FAIL: out/profile-{side['side']}.json holds no frames — re-run "
                             f"`profile.py {side['side']}`, whose window measured nothing")
    ours_per_frame = ours["window_cycles"] / ours["frames"]
    theirs_per_frame = theirs["window_cycles"] / theirs["frames"]
    print(f"-- cycles a frame: ours {ours_per_frame:.0f} over {ours['frames']} frames, the original "
          f"{theirs_per_frame:.0f} over {theirs['frames']} — "
          f"{ours_per_frame / theirs_per_frame:.2f}x")
    theirs_folded = with_scroll_blit_folded(theirs["functions"])
    shared = []
    for name, row in with_scroll_blit_folded(ours["functions"]).items():
        other = theirs_folded.get(name)
        if other is None or row["calls"] < MIN_RATIO_CALLS or other["calls"] < MIN_RATIO_CALLS:
            continue
        mine, yours = row["cycles"] / row["calls"], other["cycles"] / other["calls"]
        shared.append((mine / yours, name, mine, yours, row["calls"], other["calls"]))
    shared.sort(reverse=True)
    print(f"   {'function':<{NAME_COLUMN}} {'ours/call':>10} {'orig/call':>10} {'ratio':>7} "
          f"{'calls':>8}")
    for ratio, name, mine, yours, calls, _ in shared[:TOP_ROWS]:
        print(f"   {name:<{NAME_COLUMN}} {mine:>10.0f} {yours:>10.0f} {ratio:>7.2f} {calls:>8}")
    if not shared:
        print("   (no function is called at least "
              f"{MIN_RATIO_CALLS} times on both sides — nothing to ratio)")


FRAMES, ORIGINAL_FRAMES, COMPARE = "frames", "original-frames", "compare"
MODES = (FRAMES, ORIGINAL_FRAMES, OURS, SHIPPED, COMPARE)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--build", default=PROFILE_BUILD,
                        help="which build.sh mode our side is measured in")
    parser.add_argument("--frames", type=int, default=TIMELINE_FRAMES,
                        help="how many frames a timeline collects")
    options = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    if options.mode in (FRAMES, ORIGINAL_FRAMES):
        side = OURS if options.mode == FRAMES else SHIPPED
        rows = (our_timeline(options.build, options.frames) if side == OURS
                else original_timeline(options.frames))
        summary = summarise_timeline(side, rows)
        (OUT / f"frames-{side}.json").write_text(json.dumps({"summary": summary, "rows": rows},
                                                            indent=1))
        print_timeline(summary)
        return 0
    if options.mode == COMPARE:
        compare()
        return 0

    print_profile(profile_ours(options.build) if options.mode == OURS else profile_original())
    return 0


if __name__ == "__main__":
    sys.exit(main())
