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

FOUR HATARI FACTS, all load-bearing:

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

  * PROFILING STOPS ON EVERY DEBUGGER ENTRY. So machine state a whole window needs held has to be
    poked ONCE, from the window's own opening script, and never from a per-frame breakpoint —
    measured: `--walk`'s first draft re-poked the joystick byte at each arrival at the frame loop
    and the window came back with ONE frame in it. One poke is enough here because with no real
    joystick events the IKBD handler never writes WB_JOY1_STATE again.

  * `:trace` PRINTS NO PER-ARRIVAL LINE — only a match count when the run ends. What prints
    `CPU=$..., VBL=N, FrameCycles=M` is a plain debugger ENTRY, and `:quiet` is what suppresses it.
    So a breakpoint whose action file is nothing but `cont` is a per-arrival clock that costs the
    emulated machine no cycles, and that is the whole instrument behind the `frames` mode.

WHY OUR SIDE'S SYMBOLS ARE FOLDED AND THE ORIGINAL'S ARE NOT. The build REQUIRES `-fipa-cp-clone`
(atari/build.sh's `UNITS_THAT_MUST_STAY_AT_O3` and its clone check after the link): specialising a
routine per constant argument is what gives the sprite blit's column loop a trip count to unroll and
the HUD's glyph plotter a width, and it is worth ~79 K cycles a frame. What it costs the PROFILE is
that one function arrives in the map as several symbols (`hud_plot_digit` beside
`hud_plot_digit.constprop.0`), so its cycles are split across rows that each look small — and a
routine whose every call site was specialised has no row under its own name at all
(`blit_sprite_rows_clipped`, which reaches the map only as its four `.constprop.N` clones). The
clone suffix is a naming artefact of the pass and never a distinction the ORIGINAL made, so a row
here is the base symbol and `CLONE_SUFFIX_RE` is what strips it. The shipped side comes out of
`../names.txt`, which has no clones, so nothing about it changes.

A HAND-WRITTEN SPLIT IS NOT FOLDED, and that is deliberate: `blit_sprite_rows_plain` and
`blit_sprite_rows_clipped` are two functions in the source, not one GCC specialised, so they get
their own rows and no rule here joins them. A split half can also have NO row at all — the plain one
is inlined bodily into its four entry points — in which case its cycles are inside the callers, and
`blit_sprite_w2`..`blit_sprite_w5` are the rows to read for it.

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
    python3 atari/profile.py frames      # OUR per-frame timeline: work, wait, vblanks per frame

    ... --walk    # on any of the four: hold the joystick RIGHT for the whole window, so what is
                  # measured is a walking player rather than a standing one. The scrolling frame is
                  # the expensive one and neither side reaches 25 fps in it. Walking runs write
                  # `-walk` files, so the idle and walking baselines coexist rather than overwrite.

`ours` REBUILDS BOTH MODES EVERY TIME, on purpose: a stale .PRG measured against a fresh ELF's
symbol map is this directory's documented hazard (atari/README.md, "RUN ONE MODE AT A TIME"), and it
would show up as a plausible report rather than as an error.

`ours` and `original` each leave `out/profile-<side>.log` (the whole run, `profile stats` included)
and `out/profile-<side>.json` (what was parsed out of it), and print their own side's summary.
`compare` needs both to have been run.

WHAT `frames` IS FOR, AND WHY IT IS NOT THE PROFILER. Every figure above is a WINDOW AVERAGE, and
`cycles/frame` is the window's cycles divided by the frames in it — so it moves only when the frame
COUNT does, and a change worth thousands of cycles can leave it to the digit (../STATUS.md, "##
Performance"). `frames` measures the frames THEMSELVES: two per-arrival breakpoints, one at the
frame loop's entry and one at the flip, so a frame is WORK (loop -> flip) plus WAIT (flip -> next
loop) and its length is a whole number of vblanks, which is what fps here actually is. It leaves
`out/frames-<scenario>.txt`, one `index work wait` row a frame.
"""
import json
import re
import subprocess
import sys
from collections import Counter, namedtuple
from pathlib import Path
from statistics import median

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
# The other end of a frame's WORK: `flip_screen` waits for a vblank and swaps the buffers, so its
# entry is the moment the frame's computing is done and its waiting begins. Only the `frames` mode
# needs it, and that mode measures OUR side alone — the same timeline of the shipped binary would be
# one more boot of the disks and no question here has needed it yet.
FLIP_SYMBOL = "flip_screen"
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
# The two modes that read rather than measure, spelled once for the same reason.
COMPARE, FRAMES = "compare", "frames"
WALK_FLAG = "--walk"
# WHAT `--walk` ADDS TO A NAME. The idle and the walking window measure different programs-in-flight
# and neither is the other's baseline, so they get different files rather than the second
# overwriting the first — and `compare` refuses to read one against the other (see `load`).
WALK_SUFFIX = "-walk"
IDLE, WALKING = "idle", "walk"          # the `frames` scenarios, and its output file's name

# HOLDING THE STICK. The byte the game polls is WB_JOY1_STATE, written by nothing but the IKBD
# interrupt's handler; `include/wonderboy.h` names it and the bit, and `original.py`'s own fire
# injections poke the same byte — so the two cannot drift into different bits of different
# addresses.
WB_JOY1_STATE = original.wb("JOY1_STATE")
JOY_RIGHT = 1 << original.wb("JOY1_RIGHT_BIT")

# ---- the per-frame timeline's clock ---------------------------------------------------------
# Every debugger ENTRY prints this, and it is the only clock the `frames` mode has.
DEBUGGER_ENTRY_RE = re.compile(r"CPU=\$([0-9a-f]+), VBL=(\d+), FrameCycles=(\d+)")
# FrameCycles restarts at each vblank, so an absolute cycle is VBL * CYCLES_PER_VBL + FrameCycles.
# The ST's PAL video frame is 512 cycles x 313 lines = 160,256, a hair under the CPU clock's own
# fiftieth below, so this conversion runs ~0.1% long on the WHOLE-VBLANK part of a span — ~170
# cycles, against readings taken to a whole vblank and a work figure that is almost all
# within-frame cycles. The one constant is used for both directions, so the two agree with each
# other whatever it is.
ST_CPU_HZ = 8021247
CYCLES_PER_VBL = ST_CPU_HZ / VBL_HZ
# A frame that costs more than this is over its budget: `flip_screen` then waits for the vblank
# AFTER the one it was aiming at, and the frame takes three rather than two.
FRAME_BUDGET_VBLS = 2
# The shim's frames are numbered from 1 (wonderboy_main.c's M2_ANCHOR_FRAMES) and this timeline
# indexes from 0, so an anchor frame is at index `frame - FIRST_FRAME_NUMBER`.
FIRST_FRAME_NUMBER = 1
HEAVY_FRAMES_LISTED = 12

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
    record = m2_record("our text base cannot be measured")
    return record["capture_pc"] - symbol_pc(measure_offsets, OURS_ANCHOR_SYMBOL, ELF_NAME)


def m2_record(needed_for):
    """The frame build's record, or a refusal naming what could not be measured without it."""
    record, why = smoke.read_m2()
    if record is None:
        raise SystemExit(f"FAIL: the frame build left no usable record, so {needed_for} — {why}")
    return record


def our_joy1_state():
    """WHERE THE JOYSTICK BYTE IS IN OUR IMAGE — image-relative, because TOS chose the address.

    The shipped binary runs at the addresses ../names.txt names, so WB_JOY1_STATE is that byte's
    runtime address there and nothing has to be measured. Ours is the same offset into an image
    staged wherever the .PRG landed, which only the frame build's own record can place."""
    placed = m2_record("the joystick byte cannot be placed in our image")
    return placed["image_base"] + WB_JOY1_STATE


def joystick_hold(walk, joy1_state):
    """THE ONE POKE that holds the stick RIGHT for a whole window — or nothing, on an idle run.

    It belongs in the window's OPENING action file, before `profile on`, and it must be the ONLY
    one: Hatari stops profiling on every debugger entry, so a breakpoint that re-pokes the byte
    each frame closes the window with one frame in it (measured — this file's header). One is
    enough because with no real joystick events the IKBD handler never writes the byte again."""
    return [original.poke_byte(joy1_state, JOY_RIGHT)] if walk else []


def side_name(side, walk):
    """The side's name in every file it writes and every heading it prints."""
    return side + WALK_SUFFIX if walk else side


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


def profile_ours(walk=False):
    """Two boots: one to find out where our text lands, one to profile the frame loop there."""
    side = side_name(OURS, walk)
    measure_offsets = build(MEASURE_BUILD)
    text_base = our_text_base(measure_offsets)
    # Off the SAME boot's record the base above came from, so both answers describe one image.
    hold = joystick_hold(walk, our_joy1_state())
    play_offsets = build(PROFILE_BUILD)
    symbol_file = write_symbol_file(play_offsets, OUT / f"profile-{side}.sym")
    commands = hold + profile_on_commands(symbol_file, dump_script(side), text_base)
    on = original.action_file(OUT, f"profile-{side}-on.ini", *commands)
    start = OUT / f"profile-{side}-start.ini"
    anchor_pc = text_base + symbol_pc(play_offsets, OURS_ANCHOR_SYMBOL, ELF_NAME)
    start.write_text(original.anchor_breakpoint(anchor_pc, original.FIRST_HIT, on) + "\n")
    print(f"our text landed at {text_base:#x}; profiling from {OURS_ANCHOR_SYMBOL} at {anchor_pc:#x}")
    status, log, _ = smoke.run_hatari(prg_for(PROFILE_BUILD), run_vbls=PROFILE_RUN_VBLS,
                                      parse=start, log_name=log_path(side).name)
    require_healthy("the profiled run of our own build", status, log)
    pin_load_base(log, text_base)
    return log


def profile_original(walk=False):
    """One boot of the shipped disks, with the window opened at the frame loop's own entry.

    The boot script is `original.py`'s, unchanged: the same two fire injections and the same disk
    swap every other shipped-side measurement in this directory is made through. The window is one
    more `extra_stop` on it, so it goes through `anchor_breakpoint` and `refuse_repeated_arrivals`
    like every other anchor rather than being spelled a second time here.

    There is no load base to pin on this side: the shipped image runs where ../names.txt says it
    does, which `names_txt_symbols` refuses to assume."""
    side = side_name(SHIPPED, walk)
    symbols = names_txt_symbols()
    symbol_file = write_symbol_file(symbols, OUT / f"profile-{side}.sym")
    # The stick is poked AFTER the boot script's own fire injections, whose last act is to release
    # the same byte — this anchor is past both of them.
    commands = joystick_hold(walk, WB_JOY1_STATE) + profile_on_commands(symbol_file,
                                                                        dump_script(side))
    anchor_pc = symbol_pc(symbols, FRAME_SYMBOL, NAMES_TXT)
    print(f"profiling the shipped binary from {FRAME_SYMBOL} at {anchor_pc:#x}")

    def script(directory, disk2):
        stops = [(anchor_pc, original.FIRST_HIT, "PROFON.INI", commands)]
        return original.boot_script(directory, disk2, extra_stops=stops)

    _, log, status = original.run_original(script, side_name("profile", walk),
                                           run_vbls=PROFILE_RUN_VBLS)
    require_healthy("the profiled run of the shipped disks", status, log)
    log_path(side).write_text(log)
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


# GCC's interprocedural passes rename what they specialise: `-fipa-cp-clone` appends
# `.constprop.N`, `-fipa-sra` `.isra.N`, and partial inlining `.part.N`, and a routine can carry
# more than one. All of them name the same source function, so the profile aggregates onto the base.
# ONLY THOSE SUFFIXES. Two functions the SOURCE wrote apart — `blit_sprite_rows_plain` against
# `blit_sprite_rows_clipped` — stay two rows, because they are two bodies a reader can change one of;
# and a body with no row at all was inlined rather than folded (see the docstring above).
CLONE_SUFFIX_RE = re.compile(r"(?:\.(?:constprop|part|isra)\.\d+)+$")


def base_symbol(name):
    """The source function a linker symbol belongs to, whatever GCC specialised it into."""
    return CLONE_SUFFIX_RE.sub("", name)


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
        totals = rows.setdefault(base_symbol(name),
                                 dict(calls=0, arrivals=0, inclusive=0, exclusive=0))
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


def summarise(side, walk, log):
    """Turn one run's log into the side's .json. The log itself is written by the run that made it."""
    OUT.mkdir(exist_ok=True)
    name = side_name(side, walk)
    data = {"side": name, "walk": walk, "window_vbls": WINDOW_VBLS,
            "window_cycles": window_cycles(log), "functions": parse_callers(log)}
    if not frame_count(data):
        raise SystemExit(f"FAIL: nothing arrived at {FRAME_SYMBOL} in the window — either the "
                         f"symbols were not loaded (they must precede `profile on`) or the window "
                         f"opened somewhere other than the frame loop")
    (OUT / f"profile-{name}.json").write_text(json.dumps(data, indent=1, sort_keys=True))
    return data


def load(side, walk):
    """One side's .json, refused unless it was measured under the scenario being asked about.

    The scenario is READ OUT OF THE FILE rather than inferred from its name, so a json copied over
    another, or one written before `--walk` existed, cannot be compared against the other scenario:
    an idle window against a walking one would print a ratio table of two different games."""
    name = side_name(side, walk)
    path = OUT / f"profile-{name}.json"
    if not path.exists():
        raise SystemExit(f"FAIL: {path} is missing — run `python3 atari/profile.py {side}"
                         f"{' ' + WALK_FLAG if walk else ''}` first")
    data = json.loads(path.read_text())
    if bool(data.get("walk", False)) != walk:
        raise SystemExit(f"FAIL: {path} was measured with the joystick "
                         f"{'idle' if walk else 'held right'} but is being read as the "
                         f"{'walking' if walk else 'idle'} baseline — re-run that side")
    return data


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
    # PER FRAME, over the same `frames` the line above divides by — the two numbers sit next to each
    # other and are read as a pair ("of the whole window's N, M is inside the frame loop"), so they
    # cannot be per-arrival and per-charged-call respectively. `calls` still gates the line, because
    # a frame loop Hatari charged nothing to has no inclusive total to print.
    if loop.get("calls"):
        print(f"   {loop[INCLUSIVE] / frames / 1e3:9.1f}K cycles/frame inside "
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


def compare(walk=False):
    """Both sides' summaries and the ratio table, refusing two windows of different lengths.

    Per-frame and per-call figures survive a window change; `frames`, `fps` and `window_cycles` do
    not, and the table prints them side by side as though they were comparable."""
    ours, theirs = load(OURS, walk), load(SHIPPED, walk)
    if ours["window_vbls"] != theirs["window_vbls"]:
        raise SystemExit(f"FAIL: the two sides were measured over different windows "
                         f"({ours['window_vbls']} vblanks vs {theirs['window_vbls']}) — re-run both "
                         f"sides before comparing them")
    print_side(ours)
    print_side(theirs)
    print_ratios(ours, theirs)


# ---- the per-frame timeline -----------------------------------------------------------------
# One frame, split where the computing stops: WORK is the frame loop's entry to the flip's, WAIT is
# the flip's to the next frame loop's — almost all of it `flip_screen`'s spin on the vblank counter.
Frame = namedtuple("Frame", "work wait")


def trace_breakpoint(pc, action):
    """A breakpoint that stays armed and PRINTS on every arrival — the timeline's whole clock.

    Deliberately NOT `anchor_breakpoint`'s spelling, whose `:once :quiet` is wrong in both halves
    here: this one has to fire every frame, and the reading IS the debugger's own entry line
    (`CPU=$..., VBL=N, FrameCycles=M`), which `:quiet` is precisely what suppresses. `:trace` is not
    it either — it prints no line at all, only a match count when the run ends."""
    return f"b pc = ${pc:x} {action}"


def frame_events(log, loop_pc, flip_pc):
    """The run's arrivals at the two PCs as (pc, absolute cycle), in the order they were made."""
    events = []
    for pc, vbl, frame_cycles in DEBUGGER_ENTRY_RE.findall(log):
        pc = int(pc, 16)
        if pc in (loop_pc, flip_pc):
            events.append((pc, int(vbl) * CYCLES_PER_VBL + int(frame_cycles)))
    return events


def frame_timings(events, loop_pc, flip_pc):
    """Every COMPLETE loop -> flip -> loop triple in the stream, as its (work, wait) pair.

    Complete triples only, and that is not fastidiousness: `--run-vbls` stops the machine wherever
    it happens to be, so the stream ends mid-frame, and a run whose breakpoints were armed before
    the .PRG was loaded can begin anywhere too. Either half-frame would otherwise be reported as a
    frame that did no work or no waiting."""
    wanted = [loop_pc, flip_pc, loop_pc]
    timings = []
    at = 0
    while at + len(wanted) <= len(events):
        triple = events[at:at + len(wanted)]
        if [pc for pc, _ in triple] != wanted:
            at += 1
            continue
        (_, loop_at), (_, flip_at), (_, next_loop_at) = triple
        timings.append(Frame(flip_at - loop_at, next_loop_at - flip_at))
        # The third event is the NEXT frame's first, so the walk steps by two and not by three.
        at += 2
    return timings


def frame_vblanks(frame):
    """How many vblanks a frame took, which is the only length the machine can give it."""
    return round((frame.work + frame.wait) / CYCLES_PER_VBL)


def print_frames(timings, scenario):
    """The readings a timeline has that a window average does not, and the rows behind them."""
    if not timings:
        raise SystemExit(f"FAIL: the {scenario} run produced no complete "
                         f"{FRAME_SYMBOL} -> {FLIP_SYMBOL} -> {FRAME_SYMBOL} triple — the two "
                         f"breakpoints never fired in that order, so nothing here is a frame")
    work = [frame.work for frame in timings]
    budget = FRAME_BUDGET_VBLS * CYCLES_PER_VBL
    lengths = Counter(frame_vblanks(frame) for frame in timings)
    # The frame build PHOTOGRAPHS its anchor frames, and a 32 KB copy is not the game's own work.
    # It lands in the WAIT rather than the work — the capture is taken after the flip — so a frame
    # that is eight vblanks long with a two-vblank work is this and not a slow frame.
    anchors = {frame - FIRST_FRAME_NUMBER for frame in original.anchor_frames()}
    print(f"\n== OURS, {scenario}: {len(timings)} frames ==")
    print(f"   work cycles a frame: min {min(work):>9,.0f}   median {median(work):>9,.0f}"
          f"   max {max(work):>9,.0f}")
    print("   frame length in vblanks: "
          + "   ".join(f"{vbls} x {count}" for vbls, count in sorted(lengths.items())))
    late = sum(1 for frame in timings if frame.work > budget)
    print(f"   frames whose WORK is over the {FRAME_BUDGET_VBLS}-vblank budget ({budget:,.0f} "
          f"cycles) — the game itself late: {late}")
    over = [(index, frame) for index, frame in enumerate(timings)
            if frame_vblanks(frame) > FRAME_BUDGET_VBLS]
    print(f"   frames LONGER than {FRAME_BUDGET_VBLS} vblanks: {len(over)}")
    for index, frame in over[:HEAVY_FRAMES_LISTED]:
        anchor = "   <- M2 capture anchor: instrumentation, not the game" if index in anchors \
            else ""
        print(f"      frame {index:<6} {frame_vblanks(frame):>2} vbls   work {frame.work:>9,.0f}"
              f"   wait {frame.wait:>9,.0f}{anchor}")
    if len(over) > HEAVY_FRAMES_LISTED:
        print(f"      ... and {len(over) - HEAVY_FRAMES_LISTED} more, in the file below")
    path = OUT / f"frames-{scenario}.txt"
    path.write_text("".join(f"{index} {frame.work:.0f} {frame.wait:.0f}\n"
                            for index, frame in enumerate(timings)))
    print(f"   {path} — one `index work wait` row a frame")


def frames_timeline(walk=False):
    """OUR frames, one by one: boot the play build with a clock on the two PCs and read them off it.

    The same two builds `ours` needs and for the same reason — the frame build reports where TOS put
    our text, and the play build is the one worth timing."""
    scenario = WALKING if walk else IDLE
    measure_offsets = build(MEASURE_BUILD)
    text_base = our_text_base(measure_offsets)
    joy1_state = our_joy1_state()
    play_offsets = build(PROFILE_BUILD)
    loop_pc = text_base + symbol_pc(play_offsets, FRAME_SYMBOL, ELF_NAME)
    flip_pc = text_base + symbol_pc(play_offsets, FLIP_SYMBOL, ELF_NAME)
    # NOTHING IS PROFILED HERE, so the rule the windows live under does not apply: the per-frame
    # debugger entry is already being made, and re-poking the stick from it costs no emulated cycle
    # and holds it however the game's own code treats the byte.
    loop_action = original.action_file(OUT, "FRLOOP.INI", *joystick_hold(walk, joy1_state))
    flip_action = original.action_file(OUT, "FRFLIP.INI")
    start = OUT / f"frames-{scenario}-start.ini"
    start.write_text(trace_breakpoint(loop_pc, loop_action) + "\n"
                     + trace_breakpoint(flip_pc, flip_action) + "\n")
    print(f"our text landed at {text_base:#x}; timing {FRAME_SYMBOL} at {loop_pc:#x} against "
          f"{FLIP_SYMBOL} at {flip_pc:#x}")
    status, log, _ = smoke.run_hatari(prg_for(PROFILE_BUILD), run_vbls=PROFILE_RUN_VBLS,
                                      parse=start, log_name=f"frames-{scenario}.log")
    require_healthy(f"the {scenario} per-frame timeline run", status, log)
    print_frames(frame_timings(frame_events(log, loop_pc, flip_pc), loop_pc, flip_pc), scenario)


def main():
    args = [argument for argument in sys.argv[1:] if argument != WALK_FLAG]
    walk = WALK_FLAG in sys.argv[1:]
    mode = args[0] if len(args) == 1 else ""
    OUT.mkdir(exist_ok=True)
    if mode == OURS:
        print_side(summarise(OURS, walk, profile_ours(walk)))
    elif mode == SHIPPED:
        print_side(summarise(SHIPPED, walk, profile_original(walk)))
    elif mode == COMPARE:
        compare(walk)
    elif mode == FRAMES:
        frames_timeline(walk)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
