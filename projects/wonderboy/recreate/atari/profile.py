"""WHERE THE CYCLES GO — the reconstruction's frame, function by function, against the shipped
binary's own.

Every other mode in this directory asks whether the port is CORRECT. This one asks what it COSTS,
and it asks both binaries the same way, on the same machine, over a window of the same length: 1000
vblanks of Hatari's CPU profiler, opened when the frame loop is first reached and closed 1000
vblanks later. Frames are then a COUNT rather than an estimate — the arrivals at `game_main_loop` —
so the fps here is read off the emulated clock and not off a stopwatch.

WHAT THE OUTPUT IS FOR. One side's absolute cycle count is an emulator's arithmetic; the RATIO
between the two sides at the same named function is a finding. That table is the bottom of
`compare`, and it means anything only because each side's symbols come from its own map: ours out of
`m68k-elf-nm` over the linked ELF, the original's out of `../names.txt`, whose addresses are runtime
PCs already (`load_base` is `0x3f8` — see ../project.toml, original.py's header, and the refusal in
`names_txt_symbols` that pins that premise rather than trusting it).

TWO HATARI FACTS, both load-bearing:

  * SYMBOLS MUST BE LOADED BEFORE `profile on`, and `symbols autoload off` before THAT. Autoloading
    frees and replaces the table on every debugger entry, so a table loaded with it still on is gone
    by the time the window closes; and the profiler's callsite buffer is SIZED at `profile on`, so
    symbols arriving afterwards get no slots and the callers report comes back empty. `symbols
    <file> $<hex>` wants the offset as a NUMBER — the debugger's `TEXT` variable is not accepted
    there, though `e TEXT` will happily print it, which is what pins the offset below.

  * THE WINDOW CANNOT BE OPENED ON A VBLANK COUNT. `b VBL > N` fires during TOS's own boot, which
    spends >2,000 vblanks probing the floppy drive that is not there before our .PRG is Pexec'd. So
    it is opened at a PC and closed from INSIDE that breakpoint's action file with the
    stop-then-shoot idiom `b VBL > VBL :1000`, where the hit count IS the number of vblanks later
    (original.py's `vbl_breakpoint` documents why that is the only way to say "N vblanks later").

WHAT THE NUMBERS DO AND DO NOT COVER. `window_cycles` is EVERY profiled region summed — our side
spends ~1.2% of its window in ROM TOS, and a figure that quietly dropped it would flatter one side
and not the other. The per-function table is narrower: Hatari attaches cycle totals only to
SUBROUTINE arrivals, so a function entered by `bra`/`jmp` (18 of the shipped side's 91, including
`game_main_loop` itself) carries no totals at all and its cost is folded into the jsr-entered
ancestor that reached it. Those rows show `calls 0` and no cyc/call, and the ratio table skips them.

Use:

    python3 atari/profile.py ours        # builds m2 + play, profiles the reconstruction
    python3 atari/profile.py original    # boots the shipped disks, profiles them
    python3 atari/profile.py compare     # reads both .json files back and diffs them

`ours` REBUILDS BOTH MODES EVERY TIME, on purpose: a stale .PRG measured against a fresh ELF's
symbol map is this directory's documented hazard (atari/README.md, "RUN ONE MODE AT A TIME"), and it
would show up as a plausible report rather than as an error.

`ours` and `original` each leave `out/profile-<side>.log` (the whole run, `profile stats` included)
and `out/profile-<side>.json` (what was parsed out of it), and print their own side's summary.
`compare` needs both to have been run.
"""
import json
import re
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mkprg                                                 # noqa: E402
import original                                              # noqa: E402
import smoke                                                 # noqa: E402

# ---- the window --------------------------------------------------------------------------------
# 1000 vblanks = 20 emulated seconds = ~160 M cycles at 8 MHz. Long enough that a 4 fps side still
# lands ~95 frames in it (a 20-frame window is one message box away from measuring nothing), short
# enough that both sides fit in one Hatari run each.
WINDOW_VBLS = 1000
VBL_HZ = 50
# WHAT A FRAME IS, ON BOTH SIDES: one arrival at the frame loop's entry. The name is also the
# original's window anchor — `../names.txt` gives its runtime PC — so the two uses cannot drift.
FRAME_SYMBOL = "game_main_loop"
# OUR side's anchor is the frame CAPTURE rather than the loop entry, because it is the one PC whose
# runtime address the reconstruction reports back (`M2.BIN`'s `capture_pc`) — which is what makes
# the ELF's link-time offsets placeable at all. See `our_text_base`.
OURS_ANCHOR_SYMBOL = "capture_the_frame"
# Generous: the anchor is reached ~1,900 vblanks in and the window's own `q` ends the run at ~2,930.
# This is only the ceiling that stops a run which never reaches its anchor from hanging.
PROFILE_RUN_VBLS = 8000

# THE TWO BUILDS OUR SIDE NEEDS. `m2` stops at 52 anchored frames and reports the runtime PC that
# places every other symbol (see `our_text_base`); `play` is the same frame loop run long, which is
# the one worth profiling. Both are FRAME builds, which `prg_for` asserts, because a build that
# reached the drive without the original's palette staged beside it reports "no M2.BIN" — a missing
# fixture that reads exactly like a crash.
MEASURE_BUILD = "m2"
PROFILE_BUILD = "play"
# Both modes link to this ONE file, which is why `build` returns the map it read: the play build's
# link overwrites the measuring build's ELF, and the measuring build's symbols are needed after it.
ELF_NAME = "wonderboy.elf"

# The `nm` type letters worth giving to Hatari: text, data and bss, local or global. Everything else
# (`U` undefined, `a` absolute, debug entries) would be a name on an address the CPU never executes.
NM_SYMBOL_TYPES = "TtDdBb"

# Report shaping. A function needs real call counts on BOTH sides before a cycles-per-call ratio
# means anything — twenty is enough to be past one-off setup work and still admit per-frame work.
MIN_RATIO_CALLS = 20
TOP_ROWS = 20
# The name column, once: three format strings share it and a table whose header is a different width
# from its rows is a table nobody reads twice.
NAME_COLUMN = 34

# The two sides, spelled once: they are the subcommands, the .json/.log/.sym basenames and the
# report's own headings, and a third spelling would be a file one subcommand writes and the other
# never finds.
OURS, SHIPPED = "ours", "original"

OUT = smoke.OUT
NAMES_TXT = original.REC.parent / "names.txt"
# The `fn` lines of the name map. tools/recreate_kit/harness.py has a reader for the same file, and
# it cannot serve here: it is a MODULE-LEVEL parse that runs on import, behind a ctypes load of the
# built differential library, and it returns address -> name over `var` and `fn` together. This one
# needs name -> address over `fn` alone, without a built .so anywhere in the picture.
NAMES_FN_RE = re.compile(r"^fn\s+0x([0-9a-fA-F]+)\s+(\S+)", re.M)
# WHY names.txt's ADDRESSES ARE RUNTIME PCs, and what has to stay true for that. SWB.PRG relocates
# its own body from `load_base + 8` to the fixed address 0x400 and runs it there (../project.toml
# argues it at length); ../project.toml picks `load_base 0x3f8` precisely so that copy is an
# identity copy and a Ghidra address IS the address the CPU sees. Staged anywhere else, every `fn`
# address here would be off by the difference and the whole shipped side would be attributed to the
# wrong names in silence — so `names_txt_symbols` refuses instead of assuming.
SHIPPED_BODY_IN_IMAGE = 8       # where the relocator's source sits inside the loaded image
SHIPPED_BODY_RUNTIME = 0x400    # ...and the fixed address it copies the body to

# The log's two markers, echoed by the scripts below so every parse can be anchored AFTER the moment
# it belongs to rather than at the first match in a whole boot's worth of output.
PROFILE_ON_ECHO = "PROFILE_ON"
PROFILE_DUMP_ECHO = "PROFILE_DUMP"
# The debugger's own name for the running program's text segment, and how it prints a value:
# `= %1001... (bin), #75158 (dec), $12596 (hex)`.
TEXT_VARIABLE = "TEXT"
HEX_VALUE_RE = re.compile(r"\$([0-9a-fA-F]+)\s*\(hex\)")
# `profile stats`, per memory region: the cycles the window spent there, and the addresses it ran.
USED_CYCLES_RE = re.compile(r"- used cycles:\s*\n\s*(\d+)")
ACTIVE_RANGE_RE = re.compile(r"- active address range:\s*\n\s*0x([0-9a-f]+)-0x([0-9a-f]+)")

# The callers report: one line per callee, `0xADDR: 0xCALLER = N <type> [incl] [excl], ..., name`.
CALLERS_HEADER = "# <callee>"
CALLEE_ROW_RE = re.compile(r"^0x[0-9a-f]+: ")
# One caller's entry. The two optional totals groups are inclusive then exclusive, each printed as
# calls/instructions/cycles (Hatari appends i-miss and d-hit fields when cache emulation is on, so
# the fields are taken by index rather than by a fixed count).
CALLER_RE = re.compile(r"0x[0-9a-f]+ = (\d+) ([a-z])((?: [\d/]+){0,2})")
SUBROUTINE_CALL = "s"          # the only entry type Hatari records inclusive/exclusive totals for
TOTALS_CALLS_FIELD = 0         # CALLS/instructions/cycles
TOTALS_CYCLES_FIELD = 2        # calls/instructions/CYCLES
INCLUSIVE, EXCLUSIVE = "inclusive", "exclusive"


def prg_for(mode):
    """The .PRG `build.sh <mode>` leaves behind, refused unless it is one of the frame builds."""
    name = f"WB-{mode}.PRG"
    if name not in smoke.FRAME_BUILDS:
        raise SystemExit(f"FAIL: {name} is not one of build.sh's FRAME_MODES, so it boots without "
                         f"the original's palette staged and would report `no M2.BIN`")
    return smoke.BUILD / name


def build(mode):
    """`build.sh <mode>`, AND the symbol map it just linked.

    The two are returned together because the ordering between them is an invariant rather than a
    habit: both modes link to one `build/wonderboy.elf`, so the measuring build's map has to be read
    before the play build overwrites it. A comment saying so is a comment somebody reorders past."""
    print(f"building {mode}...", flush=True)
    done = subprocess.run(["bash", str(smoke.HERE / "build.sh"), mode], capture_output=True,
                          text=True)
    if done.returncode != 0:
        raise SystemExit(f"FAIL: `build.sh {mode}` exited {done.returncode}\n"
                         + (done.stdout + done.stderr)[-2000:])
    return elf_symbols(smoke.BUILD / ELF_NAME)


def require_healthy(what, status, log):
    """Refuse a run the machine did not survive — the same scan every other mode here makes.

    A profile of a crashed boot is not a slower frame, it is a different program, and it prints as a
    perfectly plausible table."""
    problems = smoke.check_machine_health(status, log)
    if problems:
        raise SystemExit(f"FAIL: {what}: " + " | ".join(problems))


def symbol_map(entries, source):
    """{name: (address, type letter)} from (name, address, kind) triples, refusing a repeated NAME.

    Two addresses under one name would put another function's cycles on this one's row, and
    silently: the profiler resolves a PC by ADDRESS and this report aggregates by NAME. Both maps
    come through here — the ELF's and names.txt's — because either can grow a duplicate, and the
    consequence is the same wrong table on whichever side it happens."""
    symbols = {}
    for name, address, kind in entries:
        if name in symbols:
            raise SystemExit(f"FAIL: {source} names {name} twice ({symbols[name][0]:#x} and "
                             f"{address:#x}) — this report aggregates by NAME, so one would be "
                             f"charged with the other's cycles")
        symbols[name] = (address, kind)
    return symbols


def symbol_pc(symbols, name, source):
    """One symbol's address, or a refusal that says which map was missing which name."""
    if name not in symbols:
        raise SystemExit(f"FAIL: {source} carries no symbol named {name} — this profile is anchored "
                         f"on it, so there is nothing to open the window at")
    return symbols[name][0]


def write_symbol_file(symbols, path):
    """Hatari's symbol format — `<8 hex address> <type letter> <name>` — for either side's map."""
    path.write_text("".join("%08x %s %s\n" % (address, kind, name)
                            for name, (address, kind) in sorted(symbols.items(),
                                                                key=lambda item: item[1][0])))
    return path


def elf_symbols(elf):
    """`nm` over the linked ELF as {name: (link-time offset, type letter)}.

    The offsets are link-time (tos.ld links at base 0) and become runtime PCs only once the load
    address is added — which `our_text_base` measures and `pin_load_base` then pins."""
    return symbol_map(((name, address, kind.upper())
                       for address, kind, name in mkprg.nm_rows(elf)
                       if kind in NM_SYMBOL_TYPES), elf)


def names_txt_symbols():
    """`../names.txt`'s `fn` lines as {name: (runtime PC, 'T')}, with their premise checked.

    The addresses need no relocation ONLY because of where ../project.toml stages the image; see
    SHIPPED_BODY_RUNTIME above for the argument and this refusal for the pin."""
    if original.WB_STAGED_AT + SHIPPED_BODY_IN_IMAGE != SHIPPED_BODY_RUNTIME:
        raise SystemExit(f"FAIL: ../project.toml stages the shipped image at "
                         f"{original.WB_STAGED_AT:#x}, so its body no longer runs where it is "
                         f"loaded ({original.WB_STAGED_AT + SHIPPED_BODY_IN_IMAGE:#x} != "
                         f"{SHIPPED_BODY_RUNTIME:#x}) — ../names.txt's addresses are then NOT the "
                         f"PCs Hatari reports and every shipped-side row would name the wrong "
                         f"function")
    return symbol_map(((name, int(address, 16), "T")
                       for address, name in NAMES_FN_RE.findall(NAMES_TXT.read_text())), NAMES_TXT)


def dump_script(side):
    """The window's CLOSING action file: report, then QUIT — the one action file that does not `cont`.

    `profile stats` is kept because it is the one number the callers report does not carry — the
    cycles the whole window spent, which is what a per-frame cost is a share of. The run is over
    once it is printed, and quitting here is also what keeps the log to ONE callers report, which
    `parse_callers`' completeness guard relies on."""
    return original.action_file(OUT, f"profile-{side}-dump.ini",
                                f"echo {PROFILE_DUMP_ECHO}", "profile stats", "profile callers",
                                tail="q")


def profile_on_commands(symbol_file, dump, text_base=None):
    """The window's OPENING commands, in the one order that works (see this file's header)."""
    placed = text_base is not None
    return [f"echo {PROFILE_ON_ECHO}",
            # Asked BEFORE the symbols are placed, so the log carries the machine's own answer for
            # `pin_load_base` to check the offset on the next line against.
            *([f"e {TEXT_VARIABLE}"] if placed else []),
            "symbols autoload off",
            f"symbols {symbol_file}" + (f" ${text_base:x}" if placed else ""),
            "profile on",
            original.vbl_breakpoint(original.VBL_NEXT, dump, hit=WINDOW_VBLS)]


def our_text_base(measure_offsets):
    """WHERE TOS PUT OUR TEXT, measured on the machine rather than computed.

    A .PRG's load address is TOS's next free block, so it cannot be known host-side. The frame build
    reports the runtime PC of its own capture point in `M2.BIN`; subtracting that function's
    link-time offset gives the base every other ELF offset is placed with. The play build that is
    actually profiled is a DIFFERENT binary — same TOS, same drive, same memsize, so the same base
    is an ARGUMENT and not a measurement, and `pin_load_base` turns it back into one."""
    status, log, _ = smoke.run_hatari(prg_for(MEASURE_BUILD), run_vbls=smoke.M2_RUN_VBLS,
                                      log_name=f"profile-{MEASURE_BUILD}.log")
    require_healthy(f"the {MEASURE_BUILD} run that measures our load address", status, log)
    record, why = smoke.read_m2()
    if record is None:
        raise SystemExit(f"FAIL: the frame build left no usable record, so our text base cannot be "
                         f"measured — {why}")
    return record["capture_pc"] - symbol_pc(measure_offsets, OURS_ANCHOR_SYMBOL, ELF_NAME)


def pin_load_base(log, text_base):
    """PIN the base our symbols were placed at against the base the profiled run actually used.

    A WRONG BASE DOES NOT COME BACK EMPTY. Hatari resolves a PC to the nearest symbol BELOW it, so
    every cycle is still attributed — to the wrong name, in silence, with a report that looks
    exactly like a right one. The `frames` refusal in `summarise` does not catch it either: whatever
    name lands nearest below the frame loop still collects its 500 loop-back arrivals.

    So the run is asked, at the moment the window opens, where ITS text is (`e TEXT`), and the
    answer must be the base the symbol file was loaded with. The active address range from the same
    run's `profile stats` is the cheap second opinion: no RAM below our text is ours to execute."""
    on = log.find(PROFILE_ON_ECHO)
    if on < 0:
        raise SystemExit(f"FAIL: the run's log carries no {PROFILE_ON_ECHO} echo — the window's "
                         f"opening script never ran, so nothing was profiled")
    reported = HEX_VALUE_RE.search(log, on)
    if not reported:
        raise SystemExit(f"FAIL: the debugger printed no value for `e {TEXT_VARIABLE}` after "
                         f"{PROFILE_ON_ECHO} — our load address cannot be pinned, and a wrong one "
                         f"mis-attributes every row without failing anything")
    reported = int(reported.group(1), 16)
    if reported != text_base:
        raise SystemExit(f"FAIL: the profiled run's text is at {reported:#x} but its symbols were "
                         f"placed at {text_base:#x} (measured on the {MEASURE_BUILD} boot) — every "
                         f"row would name the wrong function. The two builds no longer land at the "
                         f"same address")
    lows = [int(low, 16) for low, _ in ACTIVE_RANGE_RE.findall(stats_block(log))]
    if lows and min(lows) < text_base:
        raise SystemExit(f"FAIL: the window executed code at {min(lows):#x}, below our text at "
                         f"{text_base:#x} — those cycles are charged to whatever symbol is nearest "
                         f"below, which is not ours")


def profile_ours():
    """Two boots: one to find out where our text lands, one to profile the frame loop there."""
    measure_offsets = build(MEASURE_BUILD)
    text_base = our_text_base(measure_offsets)
    play_offsets = build(PROFILE_BUILD)
    symbol_file = write_symbol_file(play_offsets, OUT / f"profile-{OURS}.sym")
    commands = profile_on_commands(symbol_file, dump_script(OURS), text_base)
    on = original.action_file(OUT, f"profile-{OURS}-on.ini", *commands)
    start = OUT / f"profile-{OURS}-start.ini"
    anchor_pc = text_base + symbol_pc(play_offsets, OURS_ANCHOR_SYMBOL, ELF_NAME)
    start.write_text(original.anchor_breakpoint(anchor_pc, original.FIRST_HIT, on) + "\n")
    print(f"our text landed at {text_base:#x}; profiling from {OURS_ANCHOR_SYMBOL} at {anchor_pc:#x}")
    status, log, _ = smoke.run_hatari(prg_for(PROFILE_BUILD), run_vbls=PROFILE_RUN_VBLS,
                                      parse=start, log_name=log_path(OURS).name)
    require_healthy("the profiled run of our own build", status, log)
    pin_load_base(log, text_base)
    return log


def profile_original():
    """One boot of the shipped disks, with the window opened at the frame loop's own entry.

    The boot script is `original.py`'s, unchanged: the same two fire injections and the same disk
    swap every other shipped-side measurement in this directory is made through. The window is one
    more `extra_stop` on it, so it goes through `anchor_breakpoint` and `refuse_repeated_arrivals`
    like every other anchor rather than being spelled a second time here.

    There is no load base to pin on this side: the shipped image runs where ../names.txt says it
    does, which `names_txt_symbols` refuses to assume."""
    symbols = names_txt_symbols()
    symbol_file = write_symbol_file(symbols, OUT / f"profile-{SHIPPED}.sym")
    commands = profile_on_commands(symbol_file, dump_script(SHIPPED))
    anchor_pc = symbol_pc(symbols, FRAME_SYMBOL, NAMES_TXT)
    print(f"profiling the shipped binary from {FRAME_SYMBOL} at {anchor_pc:#x}")

    def script(directory, disk2):
        stops = [(anchor_pc, original.FIRST_HIT, "PROFON.INI", commands)]
        return original.boot_script(directory, disk2, extra_stops=stops)

    _, log, status = original.run_original(script, "profile", run_vbls=PROFILE_RUN_VBLS)
    require_healthy("the profiled run of the shipped disks", status, log)
    log_path(SHIPPED).write_text(log)
    return log


def stats_block(log):
    """The `profile stats` output of THIS window, from its own dump echo to the callers report.

    Anchored on the echo because the log carries a whole boot before it, and `- used cycles:` is
    printed once per memory REGION — a search from the top of the file finds the first region of
    whatever was dumped first, which is how a window's ROM TOS cycles went missing."""
    dump = log.find(PROFILE_DUMP_ECHO)
    if dump < 0:
        raise SystemExit(f"FAIL: the run's log carries no {PROFILE_DUMP_ECHO} echo, so it carries "
                         f"no `profile stats` block — the window never closed (see this file's "
                         f"header on why `b VBL > N` cannot open it)")
    block = log[dump:]
    end = block.find(CALLERS_HEADER)
    return block if end < 0 else block[:end]


def window_cycles(log):
    """EVERY profiled region's cycles in the window, summed.

    One region is the ST's RAM and another is ROM TOS, and our side spends ~1.2% of its frame in the
    latter (`Cconis`, the floppy, `Supexec`) where the shipped binary spends none. Counting only the
    first region would quietly hand our side that difference."""
    block = stats_block(log)
    regions = [int(cycles) for cycles in USED_CYCLES_RE.findall(block)]
    if not regions:
        raise SystemExit("FAIL: the `profile stats` block reports no `used cycles` for any region "
                         "— the window closed on a profiler that was never enabled")
    return sum(regions)


def parse_callers(log):
    """The callers report as {name: {calls, arrivals, inclusive, exclusive}}.

    `calls` is the ATTRIBUTED call count — the first field of an entry's exclusive totals, i.e. the
    arrivals whose cycles Hatari actually charged to this function. `arrivals` counts every entry of
    every type, which is what a frame count needs (the shipped binary re-enters its frame loop with
    a `bra`, not a `jsr`, and would otherwise be measured at zero frames). THE TWO ARE NOT THE SAME
    NUMBER and neither substitutes for the other: an `s` entry can be printed with no totals at all
    (`0xffffffff = 1 s`, the unknown caller at the moment the profiler was switched on), and
    dividing this function's charged cycles by a call count that includes such an entry reads 25%
    low — measured, on `capture_the_frame`."""
    rows = {}
    lines = log.splitlines()
    start = next((index for index, line in enumerate(lines) if line.startswith(CALLERS_HEADER)),
                 None)
    if start is None:
        raise SystemExit("FAIL: the run's log carries no `profile callers` report — the window "
                         "never closed (see this file's header on why `b VBL > N` cannot open it)")
    consumed = 0
    for line in lines[start:]:
        if line.startswith("#"):
            continue
        # The report is one contiguous block; the first line that is not a callee row ends it, and
        # what follows in the log (the next debugger entry, another dump) must not be read as one.
        if not CALLEE_ROW_RE.match(line):
            break
        consumed += 1
        callers, _, name = line.rpartition(", ")
        # A callee Hatari has no symbol for prints no trailing name at all, so the last thing on its
        # line is one more caller entry. Telling the two apart on SPACES rather than on a name
        # pattern is what makes the compiler's own symbols land: `game_key_actions.part.0` is a
        # real name in the play build's map, and a `\w+` name pattern silently truncated the whole
        # report at it — 41 functions parsed out of 86, and no error anywhere.
        if not callers or " " in name:
            continue
        totals = rows.setdefault(name, dict(calls=0, arrivals=0, inclusive=0, exclusive=0))
        for entry in CALLER_RE.finditer(callers):
            count, kind, groups = int(entry.group(1)), entry.group(2), entry.group(3).split()
            totals["arrivals"] += count
            if kind != SUBROUTINE_CALL:
                continue
            for group, into in zip(groups, (INCLUSIVE, EXCLUSIVE)):
                fields = group.split("/")
                totals[into] += int(fields[TOTALS_CYCLES_FIELD])
                if into == EXCLUSIVE:
                    totals["calls"] += int(fields[TOTALS_CALLS_FIELD])
    # The truncation guard the `.part.0` bug earned: every callee row after the header belongs to
    # this one report (the dump script quits straight after printing it), so a loop that stopped
    # early stopped on a line shape this parser does not know.
    rows_in_block = sum(1 for line in lines[start:] if CALLEE_ROW_RE.match(line))
    if consumed != rows_in_block:
        raise SystemExit(f"FAIL: the callers report has {rows_in_block} callee rows but this parser "
                         f"read {consumed} of them — it stopped at a line it does not recognise, "
                         f"and the functions past that point are missing from the whole report")
    return rows


def log_path(side):
    return OUT / f"profile-{side}.log"


def frame_count(data):
    """Frames in the window: arrivals at the frame loop's entry, however it was entered."""
    return data["functions"].get(FRAME_SYMBOL, {}).get("arrivals", 0)


def summarise(side, log):
    """Turn one run's log into the side's .json. The log itself is written by the run that made it."""
    OUT.mkdir(exist_ok=True)
    data = {"side": side, "window_vbls": WINDOW_VBLS, "window_cycles": window_cycles(log),
            "functions": parse_callers(log)}
    if not frame_count(data):
        raise SystemExit(f"FAIL: nothing arrived at {FRAME_SYMBOL} in the window — either the "
                         f"symbols were not loaded (they must precede `profile on`) or the window "
                         f"opened somewhere other than the frame loop")
    (OUT / f"profile-{side}.json").write_text(json.dumps(data, indent=1, sort_keys=True))
    return data


def load(side):
    path = OUT / f"profile-{side}.json"
    if not path.exists():
        raise SystemExit(f"FAIL: {path} is missing — run `python3 atari/profile.py {side}` first")
    return json.loads(path.read_text())


def print_side(data):
    """One side's headline plus its most expensive functions, per frame.

    Both counts are in the table because they answer different questions: `calls` is what the
    cycles beside it were charged over, `arrivals` is how often the function was reached. A
    branch-entered function has arrivals and no calls, and prints no cycles-per-call at all rather
    than a number divided by the wrong thing."""
    frames, window = frame_count(data), data["window_cycles"]
    seconds = data["window_vbls"] / VBL_HZ
    loop = data["functions"].get(FRAME_SYMBOL, {})
    print(f"\n== {data['side'].upper()}: {frames} frames in {data['window_vbls']} vblanks "
          f"= {frames / seconds:.2f} fps ==")
    print(f"   {window / max(1, frames) / 1e3:9.1f}K cycles/frame over the whole window "
          f"({window / 1e6:.1f}M cycles, every profiled region)")
    if loop.get("calls"):
        print(f"   {loop[INCLUSIVE] / loop['calls'] / 1e3:9.1f}K cycles/frame inside "
              f"{FRAME_SYMBOL} itself")
    print(f"   {'function':<{NAME_COLUMN}} {'calls':>7} {'arrivals':>9} {'incl/frame':>12} "
          f"{'excl/frame':>12} {'cyc/call':>10}")
    ranked = sorted(data["functions"].items(), key=lambda item: -item[1][INCLUSIVE])
    for name, totals in ranked[:TOP_ROWS]:
        calls = totals["calls"]
        per_call = f"{totals[INCLUSIVE] / calls:.0f}" if calls else "-"
        print(f"   {name:<{NAME_COLUMN}} {calls:>7} {totals['arrivals']:>9} "
              f"{totals[INCLUSIVE] / frames / 1e3:>11.1f}K "
              f"{totals[EXCLUSIVE] / frames / 1e3:>11.1f}K {per_call:>10}")


# One comparable function, both sides. Positional fields in a six-tuple are a bug waiting for the
# next column; `ratio` stays first because that is what the table is sorted on.
Ratio = namedtuple("Ratio", "ratio name ours_per_call ours_calls theirs_per_call theirs_calls")


def print_ratios(ours, theirs):
    """The output this file exists for: the same function, both sides, cycles per call.

    Only functions with real ATTRIBUTED calls on both sides appear, which also excludes every
    branch-entered function — those carry no cycles of their own on either side."""
    print(f"\n== SAME-NAME functions, inclusive cycles per call "
          f"(>= {MIN_RATIO_CALLS} calls on both sides) ==")
    rows = []
    for name, mine in ours["functions"].items():
        shipped = theirs["functions"].get(name)
        if not shipped or min(mine["calls"], shipped["calls"]) < MIN_RATIO_CALLS:
            continue
        mine_per_call = mine[INCLUSIVE] / mine["calls"]
        their_per_call = shipped[INCLUSIVE] / shipped["calls"]
        rows.append(Ratio(mine_per_call / max(1, their_per_call), name, mine_per_call,
                          mine["calls"], their_per_call, shipped["calls"]))
    for row in sorted(rows, reverse=True):
        print(f"   {row.name:<{NAME_COLUMN}} ours {row.ours_per_call:>9.0f} "
              f"({row.ours_calls:>6} calls)   orig {row.theirs_per_call:>8.0f} "
              f"({row.theirs_calls:>6} calls)   x{row.ratio:.1f}")


def compare():
    """Both sides' summaries and the ratio table, refusing two windows of different lengths.

    Per-frame and per-call figures survive a window change; `frames`, `fps` and `window_cycles` do
    not, and the table prints them side by side as though they were comparable."""
    ours, theirs = load(OURS), load(SHIPPED)
    if ours["window_vbls"] != theirs["window_vbls"]:
        raise SystemExit(f"FAIL: the two sides were measured over different windows "
                         f"({ours['window_vbls']} vblanks vs {theirs['window_vbls']}) — re-run both "
                         f"sides before comparing them")
    print_side(ours)
    print_side(theirs)
    print_ratios(ours, theirs)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    OUT.mkdir(exist_ok=True)
    if mode == OURS:
        print_side(summarise(OURS, profile_ours()))
    elif mode == SHIPPED:
        print_side(summarise(SHIPPED, profile_original()))
    elif mode == "compare":
        compare()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
