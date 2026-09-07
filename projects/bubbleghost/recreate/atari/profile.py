#!/usr/bin/env python3
"""profile.py — WHAT A ROOM FRAME COSTS, ours against the shipped GHOST.PRG, function by function.

`smoke.py` asks whether the reconstruction is CORRECT. This asks what it COSTS, and it asks both
binaries the same question over the same window: 1000 vblanks of Hatari's CPU profiler, opened at
the FIRST frame of the first room and closed 1000 vblanks later. Frames are then a COUNT rather
than an estimate — the arrivals at `game_frame_update`, which is one room frame on either side — so
the fps below is read off the emulated clock and not off a stopwatch.

WHY THE FRAME COST IS THE WHOLE STORY HERE. `notes/gameplay.md` §2, "The frame loop": the room loop
has no Vsync and no wait of any kind, so it turns at the renderer's speed. The game's pace AND its
mouse-to-screen latency ARE the frame cost, which is why the campaign's target is parity with the
original's cycles per frame — there is no budget to come in under, only a number to match.

ONE SIDE'S ABSOLUTE CYCLE COUNT IS AN EMULATOR'S ARITHMETIC; the RATIO between the two sides at the
same named function is a finding. That table is the bottom of `compare`, and it means something
only because each side's symbols come from its own map: ours out of `m68k-elf-nm` over the linked
ELF, the original's out of `../names.txt` relocated to the base the run decrypted itself at.

COPIED FROM `projects/wonderboy/recreate/atari/profile.py`, whose header argues the Hatari facts at
length; `projects/zynaps/recreate/atari/profile.py` is a third copy in a second dialect. The parse
half — `symbol_map`, `write_symbol_file`, `base_symbol`, `stats_block`, `parse_callers` and the
dozen constants that describe Hatari's output format rather than any game — is common to all three
and belongs in `tools/` beside `hatari_headless.py`; it has not moved there, so THIS COPY IS AHEAD
OF THE OTHERS in four ways a maintainer carrying a fix should know about: the `OUTSIDE_THE_PROGRAM`
sentinel and its top-of-map pin, `window_cycles`' cross-check against Hatari's own printed seconds
(the two log streams interleave), `symbol_map`'s deterministic fold of two names at one address, and
the `frames` mode's refresh and truncation pins. The four that shape the code below:

  * SYMBOLS MUST BE LOADED BEFORE `profile on`, AND `symbols autoload off` BEFORE THAT. Autoload
    frees and replaces the table on every debugger entry, and the profiler SIZES its callsite buffer
    at `profile on` — either way the callers report comes back empty rather than wrong.
  * THE WINDOW CANNOT BE OPENED ON A VBLANK COUNT (TOS's own boot spends thousands of them before
    the .PRG is Pexec'd), so it is opened at a PC and closed from inside that breakpoint's own
    action file with the stop-then-shoot idiom `b VBL > VBL :1000`.
  * PROFILING STOPS ON EVERY DEBUGGER ENTRY, and that is the constraint this whole driver is shaped
    around. The room is reached by pressing G and 1 from the host, so the host must not issue a
    single `hatari-debug` command between arming the window and the dump landing. "The room is
    open" is therefore the MARKER FILE the window's own script writes — a `savebin` the debugger
    makes from inside that one entry — and never a `savebin` sent from here. Keys go through
    `hatari-event` and are not debugger entries, and `smoke.press_the_game_keys` explains why an
    extra G or 1 after the room opened changes nothing.
  * `:trace` PRINTS NOTHING PER ARRIVAL. What prints `CPU=$..., VBL=N, FrameCycles=M` is a plain
    debugger ENTRY, which `:quiet` is precisely what suppresses — so a breakpoint whose action file
    is nothing but `cont` is a per-frame clock that costs the emulated machine no cycles. That is
    the whole instrument behind the `frames` mode, which is NOT the profiler.

WHAT THE NUMBERS COVER. `window_cycles` is EVERY profiled region summed, ROM TOS included: the
original polls its input through the real VDI and we poll ours through `bubble_backend.c`, so a
figure that quietly dropped ROM would flatter one side and not the other. The per-function table is
narrower — Hatari attaches cycle totals to SUBROUTINE arrivals only, so a routine entered by
`bra`/`jmp` carries none of its own and its cost sits in whichever ancestor `jsr`ed to it. Those
rows show `calls 0`.

THE SOUND TICK IS COSTED OFF A THIRD READING, for the one row that rule makes unmeasurable. The
200 Hz Timer C handler is reached from the MFP's autovector on BOTH sides, and on the shipped side
nothing `jsr`s to it at all — 3,330 ticks arrive and Hatari charges 21. So the same window's
per-ADDRESS data is summed instead (`profile save`, parsed by `address_cycles`): it knows nothing
about how an address was reached, and the rows inside the handler's own code are its cost whatever
entered it. `SOUND_TICK_SYMBOLS` names the ranges on each side and `print_side` reports the cycles
one tick cost, which is the one figure the two sides can be held against each other on.

Use:

    python3 atari/profile.py ours            # builds the play .PRG, profiles one room's window
    python3 atari/profile.py original        # boots the shipped disk, profiles the same window
    python3 atari/profile.py compare         # reads both .json files back and ranks the difference
    python3 atari/profile.py frames ours     # the per-frame cost itself, over the same window
    python3 atari/profile.py frames original

`ours` REBUILDS the play .PRG every time, on purpose: a stale .PRG measured against a fresh ELF's
symbol map reads as a plausible report rather than as an error. `ours` and `original` each leave
`out/profile/profile-<side>.log` (the whole run, `profile stats` included) and
`out/profile-<side>.json` (what was parsed out of it); `compare` needs both to have been run. The
`frames` mode leaves `out/profile/frames-<side>.log` and `out/frames-<side>.txt` beside them — the
log names carry the KIND because otherwise the second mode run overwrites the first one's evidence
(see `run_name`).

WHAT THIS INSTRUMENT DOES NOT MEASURE, and each of these is measured rather than feared:

  * THE TWO WINDOWS ARE EQUAL IN VBLANKS, NOT IN FRAMES, and the room loop advances per FRAME. So
    the faster side sees more of the room: at the first measurement the original ran 286 frames to
    our 168 from the same first frame, ticked its bonus bar 95 times to our 56 and fired 8 ambience
    sounds to our 3. The bias is structural and one-way — whichever side is faster is also the side
    whose window is likelier to contain the expensive events (a bubble that pops takes
    `frame_death_sequence` with it) — so it flatters the SLOWER side. Closing the window on the Nth
    arrival instead (`b pc = $... :N`) is the fix, and it has not been made.
  * THE MOUSE IS IDLE ON BOTH SIDES: Hatari's control protocol has no mouse motion at all
    (atari/README.md, "Unpinned"), so this is a drifting bubble and not a played game.
  * A RUN IS NOT REPRODUCIBLE TO BETTER THAN ABOUT 2%. Two `ours` windows minutes apart gave 165
    and 168 frames. The ambience re-roll draws `Random()` from an unseeded stream (the two sides
    fired 3 and 8 sounds), and `smoke.press_the_game_keys` injects on a HOST wall clock, so whether
    a stray key is drained inside the window is a real-time race. One run of each side is taken, so
    a 2% build regression and the wobble are not distinguishable.
  * THE TWO SYMBOL MAPS ARE NOT EQUALLY FINE — ours is the linked ELF (447 names), the shipped
    side's is `../names.txt` (133), with ~7 KB of shipped .text past the last `fn` line. A shipped
    row can therefore absorb code our map splits out, which tilts a same-name ratio toward the
    original looking more expensive than it is.
"""
import json
import re
import subprocess
import sys
import time
from collections import namedtuple
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# ...AND tools/ IN ITS OWN RIGHT. `smoke` puts it there as a side effect of being imported, so
# `hatari_headless` would resolve anyway — until an import sorter moves the line below above
# `import smoke`, at which point the module dies at import with ModuleNotFoundError before any of
# its own diagnostics can fire. `smoke.REPO` is not available yet, so the path is walked here.
REPO = HERE.parents[3]                 # atari -> recreate -> bubbleghost -> projects -> the repo
sys.path.insert(0, str(REPO / "tools"))
import mkprg                                                             # noqa: E402
import smoke                                                             # noqa: E402
from hatari_headless import HeadlessSession, action_file                 # noqa: E402

# ---- the window ----------------------------------------------------------------------------------
# 1000 vblanks = 16.65 emulated seconds = ~133.6 M cycles (see CYCLES_PER_VBL: this machine is at
# 60 Hz, so it is NOT the 20 s / 160 M a 50 Hz reader would compute). Long enough that a 10 fps side
# still lands ~170 frames in it, short enough that both sides fit in one Hatari run each.
WINDOW_VBLS = 1000
ST_CPU_HZ = 8021247
# THE MACHINE IS AT 60 Hz, NOT 50. `smoke.hatari_arguments` boots TOS104US on an RGB monitor, which
# is a 60 Hz shifter: 508 cycles a scan line and 263 lines a frame. MEASURED, and it is a 20%
# error on every fps if it is assumed the other way — the first window of this file's own first
# measurement came back at 133,545 cycles a vblank against this 133,604 (0.04%), where a 50 Hz
# frame would have been 160,256. `refuse_a_window_of_the_wrong_length` is that measurement kept as
# a check rather than as a memory.
ST_CYCLES_PER_LINE = 508
ST_LINES_PER_FRAME = 263
CYCLES_PER_VBL = ST_CYCLES_PER_LINE * ST_LINES_PER_FRAME
# How far a window's own cycles-per-vblank may sit from that before the run is refused. Generous:
# it is not measuring the shifter, it is telling 60 Hz from 50 Hz (a 20% gap).
REFRESH_TOLERANCE = 0.02

# WHAT A FRAME IS, ON BOTH SIDES: one arrival at `game_frame_update`, which is the whole of one
# room frame's simulation. Ours is `bubble_main.c`'s `__attribute__((noinline)) static
# game_frame_update`, whose RUNTIME address the shim publishes in `BASE.BIN`; the original's is
# `../names.txt`'s `fn 0x12322`. Both are the routine's ENTRY and not its call site:
# `smoke.ORIGINAL_ROOM_FRAME_PC` is the `jsr` @ 0x1078e, which is where the room is first REACHED
# and has no counterpart in our own binary to be counted against.
FRAME_SYMBOL = "game_frame_update"

PROFILE_BUILD = "play"
ELF = smoke.HERE / "build" / "bubble.elf"
# The `nm` type letters worth giving to Hatari: text, data and bss, local or global. Everything else
# (`U` undefined, `a` absolute, debug entries) would be a name on an address the CPU never executes.
NM_SYMBOL_TYPES = "TtDdBb"
# libgcc's `__divsi3` and `__udivsi3` carry their assembler's own branch targets into the link as
# local symbols. Naming them splits one routine's cycles across rows that mean nothing, and there
# are two `L3`s, which `symbol_map`'s duplicate refusal would (rightly) stop the run over.
ASSEMBLER_LOCAL_RE = re.compile(r"^L\d+$")

NAMES_TXT = smoke.PROJECT / "names.txt"
NAMES_FN_RE = re.compile(r"^fn\s+0x([0-9a-fA-F]+)\s+(\S+)", re.M)
# One past the shipped program's last byte, which is where its symbol map has to stop. See
# OUTSIDE_THE_PROGRAM.
PROGRAM_END = smoke.scrape_define(smoke.GLOBALS_H, "BG_PROGRAM_END")

# THE ONE NAME FOR "NOT IN THE PROGRAM AT ALL". Hatari resolves a PC to the nearest symbol BELOW it,
# so without a symbol at the top of the image every name it prints for an address outside the image
# is a game function's. Both maps therefore end in a sentinel there, under ONE name: the shipped
# side needs one because `../names.txt` has no symbol past the code, and ours needs one because the
# linker's `_bss_end` already sits at that address, where a second symbol would only make the lookup
# ambiguous — so it IS that symbol, renamed.
#
# IT PRODUCES NO ROW, and that is not a bug in it. The callers report lists a callee only where
# Hatari saw a CALLSITE, and ROM TOS is entered by a trap — so ROM's cycles sit in the exclusive
# total of whatever made the call (`vdi_call` carries 60% of the shipped window that way). What the
# sentinel fixes is every OTHER place Hatari resolves an address to a name: the "Finalizing costs"
# lines, `profile addresses`, and a debugger opened on the .sym by hand.
OUTSIDE_THE_PROGRAM = "outside_the_program"
OUR_IMAGE_TOP_SYMBOL = "_bss_end"
# Hatari says so itself when it is handed two symbols at one address, and the whole point of
# `symbol_map`'s fold is that WHICH one it keeps is its own load order. A run that still reports
# this has a collision the fold did not see.
SYMBOLS_DROPPED_RE = re.compile(r"Removed (\d+) symbols in same addresses")

# ---- what this driver writes and reads -------------------------------------------------------
OUT = smoke.OUT
WORK = OUT / "profile"                  # logs, action files, symbol files, markers, `savebin` dumps
MARKER_BYTES = 1                        # the smallest `savebin` that proves a script ran
# Any readable byte will do for a marker; the shifter's mode register is the one `smoke.py` already
# uses for the same purpose, so a reader meets one idiom rather than two.
MARKER_ADDRESS = smoke.HW_SHIFTER_MODE

# The two sides, spelled once: they are the subcommands, the .json/.log/.sym basenames and the
# report's own headings, and a third spelling would be a file one subcommand writes and the other
# never finds.
OURS, SHIPPED = "ours", "original"
COMPARE, FRAMES = "compare", "frames"
PROFILE = "profile"                     # ...the other window kind, beside FRAMES

# WHAT TO SAY WHEN `smoke.py`'s OUT-PARAMETER DICT SAYS NOTHING. Its boot helpers report a failure
# by filling `result["problem"]` in a dict the caller supplies; a future key rename would otherwise
# turn a refusal here into a `KeyError` raised from inside the error handler, losing the real reason.
NO_REASON_GIVEN = "the boot did not say why"
# ...and for a .json written before this driver stamped its runs.
UNSTAMPED = "at an unrecorded time"

# How long the host waits for a window to close itself. The window is 20 emulated seconds, and
# emulation is real time; the rest is the profiler's own dump, which is a few hundred lines.
WINDOW_DEADLINE_SECONDS = 300.0

# ---- reading Hatari back -----------------------------------------------------------------------
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
# ...and, unindented under the list of them, the window's own elapsed time. The per-region seconds
# are indented, so this matches the total alone.
WINDOW_SECONDS_RE = re.compile(r"^= ([\d.]+)s$", re.M)
STATS_TOLERANCE = 1e-3          # Hatari prints five decimals, so this is rounding and nothing else
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
# Every debugger ENTRY prints this, and it is the only clock the `frames` mode has.
DEBUGGER_ENTRY_RE = re.compile(r"CPU=\$([0-9a-f]+), VBL=(\d+), FrameCycles=(\d+)")

# GCC's interprocedural passes rename what they specialise: `-fipa-cp-clone` appends `.constprop.N`,
# `-fipa-sra` `.isra.N`, and partial inlining `.part.N`. All of them name the same source function
# — the cores are at -O2 and several such clones survive today's link — so the profile aggregates
# onto the base name. The suffix is a naming artefact of the pass and never a distinction the
# ORIGINAL made, whose map has no clones at all.
CLONE_SUFFIX_RE = re.compile(r"(?:\.(?:constprop|part|isra)\.\d+)+$")
# ...AND ONE SOURCE FUNCTION CAN BE AT TWO ADDRESSES UNDER ONE NAME. A `static inline` in a header
# that GCC could not fully inline is emitted LOCALLY in every translation unit that reached it, and
# every copy carries the same name: `copy_longs_ascending.constprop.0` is in two of this link's
# objects since include/common.h's copy runs were unrolled. `symbol_map`'s one-name-one-address rule
# is what stops one name covering two DIFFERENT functions and must stay, so the copies are given
# their own address as a suffix instead — and `base_symbol` takes it off again, which puts them back
# on the one report row that means anything for one source function.
DUPLICATE_ADDRESS_TAG = "@"
DUPLICATE_ADDRESS_RE = re.compile(rf"{DUPLICATE_ADDRESS_TAG}[0-9a-f]+$")

# Report shaping. The name column, once: three format strings share it, and a table whose header is
# a different width from its rows is a table nobody reads twice.
NAME_COLUMN = 32
TOP_ROWS = 20
# The "what only one side has" list is deliberately shorter than the ranked tables: the LINE is the
# finding (a total), and these are only the few names behind it.
ONE_SIDE_ROWS = 5
# How much of a function's traffic each side must have had CHARGED to it before the two are ranked
# against each other. Generous, because it is not grading anything — it separates a row Hatari
# costed on both sides from one it costed on one: `timer_c_sound_isr` ticks 3,329 times on ours and
# 3,330 on the shipped side, and the shipped side's autovector entry leaves 21 of those charged
# (0.006). Ranked as a ratio that row reads x81 and second in the table.
ATTRIBUTED_SHARE = 0.5
P90 = 0.90
# Two arrivals bound one frame, which is the least this mode can say anything about.
MINIMUM_TIMED_ARRIVALS = 2
# How much of the window the timed arrivals must span before the run is believed. Generous: it is
# telling a window that ran from one that Hatari's vblank cap cut off, not measuring anything.
MINIMUM_WINDOW_SPAN = 0.9

# ---- the sound tick ------------------------------------------------------------------------------
# WHICH CODE IS THE TICK, on each side, as symbol names read against that side's own map. A range is
# [symbol, the next symbol in the WHOLE map), so these do not have to be contiguous and every name in
# them must resolve — one that stopped existing (GCC inlined it, `../names.txt` was re-cut) would
# otherwise drop that routine's cycles in silence, and `symbol_ranges` refuses instead.
#
# OURS IS ONE CORE RANGE PLUS THE SHIM'S, BECAUSE THE LINK SPELT IT THAT WAY. Every helper the ISR
# runs — `sound_voice_tick`, the two step routines, the three `write_*`, `key_off` — is `static` and
# GCC inlines all of them into `timer_c_sound_isr`, so none carries an address range of its own;
# what survives beside it is the shim's own entry, tick and $484 store.
#
# THE LISTS ARE HAND-MAINTAINED AGAINST WHAT THE MAPS SAY TODAY, and that is a live hazard in ONE
# direction: a name that VANISHES is refused below, but a name that APPEARS is not noticed. A core
# edit or an `-O` change that stopped inlining one of those helpers would take its cycles out of the
# sum AND cut `timer_c_sound_isr`'s own range short at the new symbol, so the tick would read low
# twice over with nothing red. The shipped side has the same shape for the other reason:
# its one range runs to the next `fn` line in a HAND-EDITED map, so a naming sweep inside
# [0x1459a, 0x148ea) would truncate it. `sound_tick_cost` reports the BYTES each side's ranges
# cover, which is the cheap thing a reader can hold against the last run.
#
# THE TRAP #9 GATE IS STILL NAMED THOUGH THE TICK NO LONGER TAKES IT. What is left in
# `bg_super_gate` and `trap9_psg_handler` is USER-mode traffic: about two cycles a tick, measured.
# They stay in the list so that a build which put the ISR's writes back through the gate would show
# the whole cost here rather than appear to have got faster.
#
# THREE NAMES THAT USED TO BE HERE ARE GONE BECAUSE THE CODE IS (wave 3a, ../STATUS.md): the two
# step routines are now inlined into `timer_c_sound_isr`, whose range therefore covers them, and the
# ISR's chip write is a `move.b` pair the compiler puts inline where `bg_psg_write_super` used to be
# `jsr`ed. `bg_write_byte` STAYS: the ISR's $484 mirror still calls it, and dropping a name whose
# cycles the tick still spends would make the tick read cheaper than it is.
SOUND_TICK_SYMBOLS = {
    OURS: ("bg_timer_c_entry",                                     # the autovector entry, bubble_os.s
           "bg_timer_c_tick",                                      # ...and bubble_main.c's counter
           "timer_c_sound_isr",                                    # src/sound.c, steps inlined
           "psg_gate", "trap9_psg_handler",                        # the gate those writes used to take
           "bg_super_gate", "bg_super_gate_entry",                 # the `trap #9` under it
           "bg_write_byte"),                                       # the conterm byte the ISR clears
    SHIPPED: ("timer_c_sound_isr",                                 # 0x1459a, the whole handler
              "psg_gate", "trap9_psg_handler"),                    # 0x14940 and 0x14950
}
# ...and the FIRST name in each list is the routine every tick reaches exactly once, which is what
# the cycles are divided by. Spelt as a position rather than as a second dict because two dicts that
# have to agree about one name are two dicts that can disagree: a stale one still resolves every
# range and then divides real cycles by a tick count from somewhere else.
SOUND_TICK_ARRIVES_AT = 0
# Where each side's symbol names come from, for a refusal that says which map was missing which name.
SIDE_MAP_SOURCE = {OURS: ELF, SHIPPED: NAMES_TXT}

# `profile save <file>` is what dumps one row per executed address, and BOTH halves of that sentence
# are measured on Hatari 2.6.1 rather than assumed:
#
#   * THE ROWS COME BACK IN THE LOG, NOT IN THE FILE. The disassembler prints to stdout whatever
#     stream the profiler hands it, so the saved file keeps the section's header, its symbol labels
#     and a `[...]` for every row — and the rows themselves land in the debugger's own output.
#   * `profile addresses` IS NOT THE COMMAND FOR THIS. It PAGES, like the debugger's `d`: one call
#     printed 17 rows of 3,613 active addresses and left the rest for the next call, which is a
#     report that looks exactly like a complete one until its row count is checked.
#
#   `00012712 48e7 2020   movem.l d2/a2,-(a7) == $00003780   0.00% (168, 4032, 0, 0)`
#
# The TRAILING group is what is read, not the disassembly — which carries parentheses of its own
# (`(a7)`, `($000c,a7)`) — and its fields are taken by INDEX because Hatari appends i-cache and
# d-cache columns when cache emulation is on.
PROFILE_ADDRESSES_ECHO = "PROFILE_ADDRESSES"
ADDRESS_ROW_RE = re.compile(r"^([0-9a-f]{6,8}) .*[\d.]+%\s*\(([^()]*)\)\s*$", re.M)
ADDRESS_CYCLES_FIELD = 1        # instructions, CYCLES, [i-misses, d-hits]
# ...and Hatari's own count of what it printed, which is what makes reading them back a MEASUREMENT:
# a regex that stopped matching would otherwise sum a subset and report a tick that costs nothing.
DISASSEMBLED_RE = re.compile(r"Disassembled (\d+) \(of active (\d+)\) CPU addresses")
# The second, looser pin: the rows are every address the window executed, so their cycles are the
# window's. Generous, because it is only telling a parse that read the dump from one that read a
# tenth of it — the row count above is the exact check.
MINIMUM_ADDRESS_COVERAGE = 0.9

# One run of one side: its whole log, the PC the window was opened at (which the `frames` mode
# needs to tell its own breakpoint's entries apart from anything else that stops the machine), and
# the symbol map that run was measured with — `relocate` is what turns one of its addresses into a
# runtime PC, which is 0 for a map that is already absolute.
Run = namedtuple("Run", "log frame_pc symbols relocate")


# ---- symbol maps ---------------------------------------------------------------------------------
def symbol_map(entries, source):
    """{name: (address, type letter)} from (name, address, kind) triples, one name per address.

    TWO ADDRESSES UNDER ONE NAME is refused. It would put another function's cycles on this one's
    row, and silently: the profiler resolves a PC by ADDRESS and this report aggregates by NAME.

    TWO NAMES AT ONE ADDRESS is folded, not refused, because the link has four of them today and
    they are all real: libgcc publishes `__divsi3` beside `__divsi3_internal` (likewise `__udivsi3`
    and `__mulsi3`), and tos.ld's `_bss_start` lands on the first object in .bss. Handing Hatari
    both names lets it resolve a PC to whichever its own load order reaches first, so the divide
    helpers' cycles would sit under one name on one link and the other name on the next — the same
    report, not reproducible, with nothing failing. The surviving name is the alphabetically first,
    which is a rule and not a coincidence: it is stable across links, and it happens to prefer the
    plain name over its `_internal` alias."""
    by_address = {}
    for name, address, kind in entries:
        chosen = by_address.get(address)
        if chosen is None or name < chosen[0]:
            by_address[address] = (name, kind)
    symbols = {}
    for address, (name, kind) in by_address.items():
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
                         f"on it, so there is nothing to open a window at")
    return symbols[name][0]


def write_symbol_file(symbols, path):
    """Hatari's symbol format — `<8 hex address> <type letter> <name>` — for either side's map."""
    path.write_text("".join("%08x %s %s\n" % (address, kind, name)
                            for name, (address, kind) in sorted(symbols.items(),
                                                                key=lambda item: item[1][0])))
    return path


def refuse_a_sentinel_that_is_not_the_top(symbols, source):
    """The sentinel only works while it IS the highest address in its map.

    Hatari charges a PC to the nearest symbol BELOW it, so a symbol above `outside_the_program`
    takes back every cycle the window spent outside the image — quietly, and onto a name the ratio
    table then blames. Neither map guarantees the ordering on its own: ours is the linker's
    `_bss_end`, which stays on top only while nothing else lands above it, and the shipped side's is
    a constant scraped from a header while `../names.txt` is hand-edited."""
    top = max(address for address, _ in symbols.values())
    placed = symbols[OUTSIDE_THE_PROGRAM][0]
    if placed != top:
        raise SystemExit(f"FAIL: {source} carries a symbol at {top:#x}, above the "
                         f"{OUTSIDE_THE_PROGRAM} sentinel at {placed:#x} — every cycle spent "
                         f"outside the image would be charged to it instead")
    return symbols


def tag_duplicate_names(entries):
    """One name at two addresses, made two names — see DUPLICATE_ADDRESS_TAG for why they exist."""
    entries = list(entries)
    placements = {}
    for name, address, _ in entries:
        placements.setdefault(name, set()).add(address)
    return [(name if len(placements[name]) == 1 else f"{name}{DUPLICATE_ADDRESS_TAG}{address:x}",
             address, kind)
            for name, address, kind in entries]


def elf_symbols(elf):
    """`nm` over the linked ELF as {name: (link-time offset, type letter)}.

    tos.ld links at base 0, so these are offsets into the flat image; they become runtime PCs once
    the base TOS chose is added, which `measure_ours` takes off the shim's own anchor table and
    `pin_load_base` then pins against the machine. Clone suffixes are NOT folded here — that happens
    in `parse_callers`, because a base name and its clone are two distinct addresses and folding
    them into one map entry would lose one of them."""
    symbols = symbol_map(tag_duplicate_names(
        (name, address, kind.upper())
        for address, kind, name in mkprg.nm_rows(elf)
        if kind in NM_SYMBOL_TYPES and not ASSEMBLER_LOCAL_RE.match(name)), elf)
    if OUR_IMAGE_TOP_SYMBOL not in symbols:
        raise SystemExit(f"FAIL: {elf} carries no {OUR_IMAGE_TOP_SYMBOL} — tos.ld's own marker for "
                         f"the top of our image is gone, so every cycle spent above it (ROM TOS, "
                         f"reached through the shim) would be charged to the last real function")
    symbols[OUTSIDE_THE_PROGRAM] = symbols.pop(OUR_IMAGE_TOP_SYMBOL)
    return refuse_a_sentinel_that_is_not_the_top(symbols, elf)


def names_txt_symbols(runtime_base):
    """`../names.txt`'s `fn` lines as {name: (runtime PC, 'T')}, relocated to where the run put them.

    Those addresses are GHIDRA addresses — an image offset plus `BG_LOAD_BASE` — and the shipped
    program decrypts itself into RAM wherever TOS happened to load it, so a runtime PC is
    `runtime_base - BG_LOAD_BASE + address`. `runtime_base` is MEASURED, by matching the program's
    own bytes in RAM (`smoke.await_the_decrypted_original`), which is what makes this arithmetic a
    measurement rather than an assumption."""
    relocate = runtime_base - smoke.LOAD_BASE
    entries = [(name, relocate + int(address, 16), "T")
               for address, name in NAMES_FN_RE.findall(NAMES_TXT.read_text())]
    entries.append((OUTSIDE_THE_PROGRAM, relocate + PROGRAM_END, "T"))
    return refuse_a_sentinel_that_is_not_the_top(symbol_map(entries, NAMES_TXT), NAMES_TXT)


# ---- the window's own scripts --------------------------------------------------------------------
def run_name(kind, side):
    """The basename every artefact of one run shares — its log, its action files, its marker.

    SCOPED BY KIND AND NOT BY SIDE ALONE. The two window kinds are two separate boots of the same
    binary, and a `frames` run that reused the profile run's log name overwrote the `profile stats`
    dump this directory's README points at — measured, the first time both were run in one sitting.
    """
    return f"{kind}-{side}"


def run_log(run):
    return WORK / f"{run}.log"


def window_marker(run):
    return WORK / f"{run}-window.bin"


def marker_command(path):
    """A one-byte `savebin` the DEBUGGER makes from inside a breakpoint's own action file, so the
    HOST can see that the breakpoint fired.

    It reads the shifter's mode register because that is a byte always readable that costs the
    machine nothing — the same choice `smoke.arm_the_anchor` makes, and for the same reason: a
    driver that waits on a FILE never has to guess a delay. Being written from INSIDE the entry is
    what makes it legal here, where a `savebin` sent from the host would stop the profiler."""
    return f"savebin {path} ${MARKER_ADDRESS:x} ${MARKER_BYTES:x}"


def close_after_the_window(action):
    """`WINDOW_VBLS` vertical blanks from now, run `action`.

    Hatari substitutes a breakpoint expression's CURRENT value on the right when the breakpoint is
    set, so `b VBL > VBL` is "the next vblank" and its Nth hit is N vblanks later.

    A DIFFERENT IDIOM FROM `settle_chain`'s, deliberately. tools/hatari_headless.py nests one action
    file per vblank, which is right for the four-blank settle it was written for and would write a
    thousand files here; the hit count does the same job in one breakpoint. Both rest on the same
    substitution, which `settle_chain`'s docstring argues in full."""
    return f"b VBL > VBL :{WINDOW_VBLS} :once :quiet {action}"


def frames_window_commands(run, frame_pc):
    """The `frames` window's script: a per-arrival clock, and a `q` a thousand vblanks later.

    The tick breakpoint is NOT `:quiet` and NOT `:once` — the debugger's own entry line IS the
    reading, and the clock has to stay armed for the whole window. Its action file is `cont` alone,
    so an arrival costs the emulated machine nothing."""
    return [marker_command(window_marker(run)),
            f"b pc = ${frame_pc:x} {action_file(WORK, f'{run}-tick.ini')}",
            close_after_the_window(action_file(WORK, f"{run}-quit.ini", tail="q"))]


def addresses_dump(run):
    """The file `profile save` writes. Kept for its header and its symbol labels — the rows this
    driver reads are in the LOG, for the reason ADDRESS_ROW_RE gives."""
    return WORK / f"{run}-addresses.txt"


def profile_window_commands(run, symbol_file, text_base=None):
    """...and the profiler's, in the one order that works (this file's header).

    `text_base` places our side's LINK-TIME offsets at the address TOS gave them; the shipped side's
    map is already absolute and passes none. `profile stats` is kept beside the callers report
    because it is the one number that report does not carry — the cycles the whole window spent,
    which is what a per-frame cost is a share of. Quitting straight after is also what keeps the log
    to ONE callers report, which `parse_callers`' completeness guard relies on.

    `profile save` goes LAST, after the callers report, for that same guard: its thousands of rows
    are printed to the log, and between the header and the report they would be read as callee rows
    this parser does not recognise. Its own echo is what `address_cycles` anchors on."""
    dump = action_file(WORK, f"{run}-dump.ini", f"echo {PROFILE_DUMP_ECHO}",
                       "profile stats", "profile callers", f"echo {PROFILE_ADDRESSES_ECHO}",
                       f"profile save {addresses_dump(run)}", tail="q")
    placed = text_base is not None
    return [marker_command(window_marker(run)), f"echo {PROFILE_ON_ECHO}",
            # Asked BEFORE the symbols are placed, so the log carries the machine's own answer for
            # `pin_load_base` to check the offset on the next line against.
            *([f"e {TEXT_VARIABLE}"] if placed else []),
            "symbols autoload off",
            f"symbols {symbol_file}" + (f" ${text_base:x}" if placed else ""),
            "profile on",
            close_after_the_window(dump)]


def arm_the_window(session, run, frame_pc, commands):
    """Arm the one-shot breakpoint that opens the window at the room's first frame.

    THE LAST `hatari-debug` COMMAND THE HOST MAY SEND on this run — see this file's header."""
    window_marker(run).unlink(missing_ok=True)
    script = action_file(WORK, f"{run}-open.ini", *commands)
    session.arm(f"b pc = ${frame_pc:x} :once :quiet {script}")


def open_the_room(session, run):
    """Press G and 1 until the window's marker appears, and refuse a run where it never did."""
    if not smoke.press_the_game_keys(session, window_marker(run).is_file,
                                     smoke.ROOM_DEADLINE_SECONDS):
        raise SystemExit(f"FAIL: {run}: the two keys never opened a room, so no window opened "
                         f"and nothing was measured — see {run_log(run)}")


def collect(session, run):
    """Wait for the window's own `q`, then hand back the log the run left behind."""
    deadline = time.monotonic() + WINDOW_DEADLINE_SECONDS
    while session.alive() and time.monotonic() < deadline:
        session.wait(smoke.POLL_SECONDS)
    closed_itself = not session.alive()
    status = session.close()
    if not closed_itself:
        raise SystemExit(f"FAIL: {run}: the {WINDOW_VBLS}-vblank window never closed the run "
                         f"within {WINDOW_DEADLINE_SECONDS:.0f}s — see {run_log(run)}")
    problems = smoke.check_machine_health(status, run_log(run))
    if problems:
        raise SystemExit(f"FAIL: {run}: " + " | ".join(problems))
    return run_log(run).read_text(errors="replace")


# ---- the two sides ---------------------------------------------------------------------------
@contextmanager
def emulator(medium, run):
    """A headless Hatari that is SHUT DOWN on every path out, refusals included.

    A `SystemExit` raised with the emulator still up leaves it holding the media, and the next run's
    Hatari is then the second one on the same image — `tools/hatari_headless.py` kills its own
    process on a failed handshake for exactly that reason. `HeadlessSession.close` is idempotent, so
    the normal path's own close inside `collect` is not disturbed by this one."""
    session = HeadlessSession(smoke.hatari_arguments(medium, None), run_log(run),
                              WORK / f"{run}.fifo", WORK)
    try:
        yield session
    finally:
        session.close()


def build_the_play_prg():
    """`build.sh play` — the binary both window kinds measure.

    The build stages its own .PRG on the C: drive it boots from, so what is measured below is the
    binary just linked and cannot be a leftover from another mode."""
    print(f"building {PROFILE_BUILD}...", flush=True)
    done = subprocess.run(["bash", str(smoke.BUILD_SH), PROFILE_BUILD],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"FAIL: `build.sh {PROFILE_BUILD}` exited {done.returncode}\n"
                         + (done.stdout + done.stderr)[-2000:])


def pin_load_base(log, text_base):
    """PIN the base our symbols were placed at against the base the profiled run actually used.

    A WRONG BASE DOES NOT COME BACK EMPTY. Hatari resolves a PC to the nearest symbol BELOW it, so
    every cycle is still attributed — to the wrong name, in silence, with a report that looks
    exactly like a right one. So the run is asked, at the moment the window opens, where ITS text is
    (`e TEXT`), and the answer must be the base the symbol file was loaded with. The active address
    range from the same run's `profile stats` is the cheap second opinion: no RAM below our text is
    ours to execute."""
    profile_on_at = log.find(PROFILE_ON_ECHO)
    if profile_on_at < 0:
        raise SystemExit(f"FAIL: the run's log carries no {PROFILE_ON_ECHO} echo — the window's "
                         f"opening script never ran, so nothing was profiled")
    printed = HEX_VALUE_RE.search(log, profile_on_at)
    if not printed:
        raise SystemExit(f"FAIL: the debugger printed no value for `e {TEXT_VARIABLE}` after "
                         f"{PROFILE_ON_ECHO} — our load address cannot be pinned, and a wrong one "
                         f"mis-attributes every row without failing anything")
    reported = int(printed.group(1), 16)
    if reported != text_base:
        raise SystemExit(f"FAIL: the profiled run's text is at {reported:#x} but its symbols were "
                         f"placed at {text_base:#x} (taken from the shim's own anchor table) — "
                         f"every row would name the wrong function")
    lows = [int(low, 16) for low, _ in ACTIVE_RANGE_RE.findall(stats_block(log))]
    if lows and min(lows) < text_base:
        raise SystemExit(f"FAIL: the window executed code at {min(lows):#x}, below our text at "
                         f"{text_base:#x} — those cycles are charged to whatever symbol is nearest "
                         f"below, which is not ours")


def measure_ours(kind):
    """Build the play .PRG, boot it, drive it into a room, and measure the window that opens there.

    THE ORDER IS THE INSTRUMENT. The tally is polled — a `savebin`, so a debugger entry — only
    while the menu is still being drawn, which is BEFORE the window is armed; once it is armed the
    host does nothing but press keys and watch for a file.

    THE SYMBOL MAP IS BUILT ONLY FOR THE PROFILER. `frames` breaks on an address the shim published
    and reads the debugger's own entry lines, so it needs no symbols at all — and building them
    anyway would let `nm` refuse the run (a duplicate local, a missing `_bss_end`) over a table that
    mode never opens."""
    run = run_name(kind, OURS)
    build_the_play_prg()
    # `build.sh` clears the drive's *.BIN, but the anchor table below is what places every symbol,
    # and a stale one would place them all at the wrong base.
    (smoke.DISK / "c" / smoke.FILE_ANCHOR_BASE).unlink(missing_ok=True)
    with emulator(smoke.ours_medium(), run) as session:
        booted = {}
        anchors = smoke.await_the_anchor_table(session, booted)
        if anchors is None:
            raise SystemExit(f"FAIL: ours: {booted.get('problem', NO_REASON_GIVEN)}")
        frame_pc = anchors[smoke.ANCHOR_ROOM_FRAME]
        if not frame_pc:
            raise SystemExit("FAIL: the .PRG under test composes no room loop — it is a `title` "
                             "build, and there is no frame to measure")
        offsets, text_base = None, None
        commands = frames_window_commands(run, frame_pc)
        if kind == PROFILE:
            offsets = elf_symbols(ELF)
            text_base = frame_pc - symbol_pc(offsets, FRAME_SYMBOL, ELF)
            commands = profile_window_commands(run, write_symbol_file(offsets, WORK / f"{run}.sym"),
                                               text_base)
            print(f"our text landed at {text_base:#x}")
        print(f"the window opens at {FRAME_SYMBOL} @ {frame_pc:#x}")
        if not smoke.await_play_tally(session, anchors[smoke.ANCHOR_PLAY_TALLY],
                                      smoke.TALLY_MENU_OPENS, 1, "waiting for the menu to be drawn",
                                      smoke.MENU_DEADLINE_SECONDS):
            raise SystemExit("FAIL: ours: the menu was never opened, so no key could be sent")
        arm_the_window(session, run, frame_pc, commands)
        open_the_room(session, run)
        log = collect(session, run)
    if kind == PROFILE:
        pin_load_base(log, text_base)
    return Run(log, frame_pc, offsets, 0 if text_base is None else text_base)


def measure_original(kind):
    """The same window on the shipped binary, opened at its own `game_frame_update`.

    There is no load base to pin here beyond the one that was measured: the symbol map and the
    breakpoint are both built from the base `locate_by_signature` matched the program's own bytes
    at, so they cannot disagree with each other. What WOULD show a wrong base is `summarise`'s
    refusal — a window with no arrivals at `game_frame_update` in it."""
    run = run_name(kind, SHIPPED)
    with emulator(smoke.original_medium(), run) as session:
        booted = {}
        base = smoke.await_the_decrypted_original(session, booted)
        if base is None:
            raise SystemExit(f"FAIL: the original: {booted.get('problem', NO_REASON_GIVEN)}")
        # Parsed on BOTH paths: the frame PC this window opens at is one of its entries.
        symbols = names_txt_symbols(base)
        frame_pc = symbol_pc(symbols, FRAME_SYMBOL, NAMES_TXT)
        commands = (profile_window_commands(run, write_symbol_file(symbols, WORK / f"{run}.sym"))
                    if kind == PROFILE else frames_window_commands(run, frame_pc))
        print(f"the original decrypted itself at {base:#x}; the window opens at {FRAME_SYMBOL} "
              f"@ {frame_pc:#x}")
        # The menu has to be DRAWN before a key means anything, and the shipped side has no tally to
        # poll — so its own menu PC drops a marker, the same way the window below does.
        menu = WORK / f"{run}-menu.bin"
        menu.unlink(missing_ok=True)
        menu_script = action_file(WORK, f"{run}-menu.ini", marker_command(menu))
        session.arm(f"b pc = ${base - smoke.LOAD_BASE + smoke.ORIGINAL_ANCHOR_PC:x} :once :quiet "
                    f"{menu_script}")
        if not smoke.await_file(session, menu, "waiting for the original to draw its menu",
                                smoke.MENU_DEADLINE_SECONDS, smoke.POLL_SECONDS):
            raise SystemExit("FAIL: the original: the menu was never drawn, so no key could be sent")
        arm_the_window(session, run, frame_pc, commands)
        open_the_room(session, run)
        # The shipped map is built at the base the run decrypted itself to, so it is already
        # absolute and nothing further has to be added to reach a runtime PC.
        return Run(collect(session, run), frame_pc, symbols, 0)


def measure(side, kind):
    return measure_ours(kind) if side == OURS else measure_original(kind)


# ---- parsing the profiler's dump -----------------------------------------------------------------
def stats_block(log):
    """The `profile stats` output of THIS window, from its own dump echo to the callers report.

    Anchored on the echo because the log carries a whole boot before it, and `- used cycles:` is
    printed once per memory REGION — a search from the top of the file finds the first region of
    whatever was dumped first."""
    dump_echo_at = log.find(PROFILE_DUMP_ECHO)
    if dump_echo_at < 0:
        raise SystemExit(f"FAIL: the run's log carries no {PROFILE_DUMP_ECHO} echo, so it carries "
                         f"no `profile stats` block — the window never closed")
    block = log[dump_echo_at:]
    end = block.find(CALLERS_HEADER)
    return block if end < 0 else block[:end]


def window_cycles(log):
    """EVERY profiled region's cycles in the window, summed — and cross-checked against Hatari's own
    total for the same window.

    One region is the ST's RAM, another is ROM TOS and a third the cartridge port, and the two sides
    do not spend the same share in the second: the original polls its input through the real VDI,
    where 59% of its window goes. Counting only the first region would hand one side that whole
    difference.

    THE CROSS-CHECK IS NOT CEREMONY. Hatari writes this log on two differently buffered streams that
    interleave — a fragment of the region list appears in every log BEFORE the dump echo, flushed
    out of order — so a flush landing inside the block would double or drop a region in silence.
    Hatari prints the window's elapsed seconds under the list, unindented, and that is what the sum
    is held against."""
    block = stats_block(log)
    regions = [int(cycles) for cycles in USED_CYCLES_RE.findall(block)]
    if not regions:
        raise SystemExit("FAIL: the `profile stats` block reports no `used cycles` for any region "
                         "— the window closed on a profiler that was never enabled")
    stated = WINDOW_SECONDS_RE.findall(block)
    if not stated:
        raise SystemExit("FAIL: the `profile stats` block carries no total for the window, so the "
                         "regions summed here cannot be checked against anything")
    total, seconds = sum(regions), float(stated[-1])
    if abs(total / ST_CPU_HZ - seconds) > seconds * STATS_TOLERANCE:
        raise SystemExit(f"FAIL: the window's regions sum to {total:,} cycles "
                         f"({total / ST_CPU_HZ:.5f}s) but Hatari reports {seconds}s for the same "
                         f"window — the log's two streams interleaved inside the block and a "
                         f"region was double-counted or lost")
    return total


def base_symbol(name):
    """The source function a linker symbol belongs to, whatever GCC specialised or copied it into."""
    return CLONE_SUFFIX_RE.sub("", DUPLICATE_ADDRESS_RE.sub("", name))


def parse_callers(log):
    """The callers report as {name: {calls, arrivals, inclusive, exclusive}}.

    `calls` is the ATTRIBUTED call count — the first field of an entry's exclusive totals, i.e. the
    arrivals whose cycles Hatari actually charged to this function. `arrivals` counts every entry of
    every type, which is what a frame count needs. THE TWO ARE NOT THE SAME NUMBER: an `s` entry can
    be printed with no totals at all (`0xffffffff = 1 s`, the unknown caller at the moment the
    profiler was switched on), so dividing charged cycles by an arrival count reads low."""
    rows = {}
    lines = log.splitlines()
    start = next((index for index, line in enumerate(lines) if line.startswith(CALLERS_HEADER)),
                 None)
    if start is None:
        raise SystemExit("FAIL: the run's log carries no `profile callers` report — the window "
                         "never closed, or the symbols were loaded after `profile on`")
    consumed = 0
    for line in lines[start:]:
        if line.startswith("#"):
            continue
        # The report is one contiguous block; the first line that is not a callee row ends it, and
        # what follows in the log must not be read as one.
        if not CALLEE_ROW_RE.match(line):
            break
        consumed += 1
        callers, _, name = line.rpartition(", ")
        # A callee Hatari has no symbol for prints no trailing name at all, so the last thing on its
        # line is one more caller entry. Telling the two apart on SPACES rather than on a name
        # pattern is what makes the compiler's own symbols land (`write_file.isra.0` is a real name
        # in this build's map).
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
    # Every callee row IN THIS REPORT belongs to it, so a loop that stopped early stopped on a line
    # shape this parser does not know — and the functions past that point would be missing from the
    # whole report in silence. The report used to run to the end of the log; `profile save` now puts
    # thousands of address rows after it, so the count is bounded at that dump's own echo rather
    # than resting on those rows happening not to look like callee rows.
    end = next((index for index, line in enumerate(lines[start:], start)
                if PROFILE_ADDRESSES_ECHO in line), len(lines))
    rows_in_block = sum(1 for line in lines[start:end] if CALLEE_ROW_RE.match(line))
    if consumed != rows_in_block:
        raise SystemExit(f"FAIL: the callers report has {rows_in_block} callee rows but this parser "
                         f"read {consumed} of them — it stopped at a line it does not recognise")
    return rows


def address_cycles(side, log):
    """{runtime address: cycles} for every address the window EXECUTED, off `profile addresses`.

    ANCHORED ON ITS OWN ECHO, because the log carries a whole boot's disassembly before it — every
    debugger entry prints the instruction it stopped on, and those lines are the same shape without
    the profile fields. Pinned on Hatari's own count of the rows it printed, so a regex that stopped
    matching reds rather than summing a subset."""
    echoed_at = log.find(PROFILE_ADDRESSES_ECHO)
    if echoed_at < 0:
        raise SystemExit(f"FAIL: {side}: the run's log carries no {PROFILE_ADDRESSES_ECHO} echo — "
                         f"`profile save` never ran, and the sound tick is the one cost the "
                         f"callers report cannot carry")
    # THE ECHO IS NOT NEWLINE-TERMINATED where the profiler's own stream follows it, so the first
    # row arrives glued to it and a `^`-anchored match would silently drop exactly one address.
    block = "\n" + log[echoed_at + len(PROFILE_ADDRESSES_ECHO):]
    rows = {}
    for address, totals in ADDRESS_ROW_RE.findall(block):
        rows[int(address, 16)] = int(totals.split(",")[ADDRESS_CYCLES_FIELD])
    printed = DISASSEMBLED_RE.search(block)
    if not printed:
        raise SystemExit(f"FAIL: {side}: `profile save` printed no count of the rows it wrote, so "
                         f"the {len(rows)} read back here are held against nothing")
    shown, active = int(printed.group(1)), int(printed.group(2))
    if len(rows) != shown or shown != active:
        raise SystemExit(f"FAIL: {side}: Hatari printed {shown} of {active} active addresses and "
                         f"this parser read {len(rows)} of them — a row shape it does not know, and "
                         f"every range summed out of them would read low with nothing failing")
    return rows


def symbol_ranges(symbols, names, relocate, source):
    """[start, end) runtime addresses for every symbol each name owns, the ends taken from the map.

    A range ends at the next symbol ABOVE its own, which is why it matters that both maps carry a
    sentinel at the top of the image (OUTSIDE_THE_PROGRAM): a named function with nothing above it
    would have no end at all.

    ONE NAME CAN OWN SEVERAL RANGES. `base_symbol` is what decides: a GCC clone (`.constprop.N`) and
    a per-translation-unit copy both belong to the source function they were named after, and each
    sits at its own address. Taking only the base symbol's own range would leave a clone's cycles
    out of the sum with nothing red — and, where the clone happens to be laid down next to it, would
    cut the base's range short as well."""
    placed = sorted(address for address, _ in symbols.values())
    owned = {}
    for name, (address, _) in symbols.items():
        owned.setdefault(base_symbol(name), []).append(address)
    ranges = []
    for name in names:
        if name not in owned:
            raise SystemExit(f"FAIL: {source} carries no symbol named {name} — the sound tick is "
                             f"summed over its address range, so there is nothing to sum")
        for start in sorted(owned[name]):
            above = next((address for address in placed if address > start), None)
            if above is None:
                raise SystemExit(f"FAIL: {source} carries no symbol above {name} at {start:#x}, so "
                                 f"its range has no end — the map's top-of-image sentinel is gone")
            ranges.append((relocate + start, relocate + above))
    return ranges


def sound_tick_cost(side, run, functions, window):
    """What one 200 Hz Timer C tick cost, summed off the window's per-ADDRESS data.

    THE CALLERS REPORT CANNOT ANSWER THIS on the shipped side and that is the whole point (this
    file's header): the handler is entered from the MFP's autovector, which is not a subroutine
    call, so its cycles sit in whatever the interrupt landed in. Per-address data has no such
    notion — an address's cycles are its own however the PC got there — so the ranges in
    SOUND_TICK_SYMBOLS are summed instead, and the two sides become comparable at last.

    WHAT IS NOT IN IT, on either side: the Timer C work TOS still wants done. Both handlers chain to
    the saved $114 vector by pushing it and `rts`ing, and ROM is outside every range below."""
    executed = address_cycles(side, run.log)
    accounted = sum(executed.values())
    if accounted < window * MINIMUM_ADDRESS_COVERAGE:
        raise SystemExit(f"FAIL: {side}: the address rows account for {accounted:,} of the window's "
                         f"{window:,} cycles — they are supposed to BE the window, so one of the "
                         f"two is not the measurement it is read as")
    ranges = symbol_ranges(run.symbols, SOUND_TICK_SYMBOLS[side], run.relocate,
                           SIDE_MAP_SOURCE[side])
    cycles = sum(count for address, count in executed.items()
                 if any(start <= address < end for start, end in ranges))
    covered = sum(end - start for start, end in ranges)
    arrives_at = SOUND_TICK_SYMBOLS[side][SOUND_TICK_ARRIVES_AT]
    ticks = functions.get(arrives_at, {}).get("arrivals", 0)
    if not ticks:
        raise SystemExit(f"FAIL: {side}: nothing arrived at {arrives_at} in the window, so the "
                         f"tick's cycles are over an unknown number of ticks")
    return {"cycles": cycles, "ticks": ticks, "per_tick": cycles / ticks, "accounted": accounted,
            "bytes": covered}


def refuse_a_window_of_the_wrong_length(side, cycles):
    """Refuse a window whose vblanks are not the ones every figure here is divided by.

    The whole report is per FRAME and per SECOND, and both come off the emulated clock — so a run
    on a machine at a refresh this file does not expect reports every number 20% wrong and fails
    nothing. See CYCLES_PER_VBL."""
    measured = cycles / WINDOW_VBLS
    if abs(measured - CYCLES_PER_VBL) > CYCLES_PER_VBL * REFRESH_TOLERANCE:
        raise SystemExit(f"FAIL: {side}: the window spent {measured:,.0f} cycles a vblank and this "
                         f"file is built on {CYCLES_PER_VBL:,} (a 60 Hz shifter) — the machine is "
                         f"not the one `smoke.hatari_arguments` describes")


def refuse_symbols_hatari_dropped(log):
    """Refuse a run where Hatari discarded symbols the map handed it.

    It prints the count itself, and `symbol_map`'s fold exists precisely so the count is zero: a
    dropped symbol is one of a pair at the same address, and WHICH of the pair survives is Hatari's
    own load order — so a report that changes between two runs of one binary, with nothing failing.
    """
    dropped = [int(count) for count in SYMBOLS_DROPPED_RE.findall(log) if int(count)]
    if dropped:
        raise SystemExit(f"FAIL: Hatari dropped {sum(dropped)} symbol(s) sharing an address with "
                         f"another — `symbol_map`'s fold missed a collision, and which name keeps "
                         f"those cycles is then Hatari's load order rather than a rule")


def measured_now():
    """When this measurement was taken, to the second, so `compare` can show its two ages."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def summarise(side, run):
    """Turn one run into the side's .json, refusing a window with no frames in it."""
    functions = parse_callers(run.log)
    data = {"side": side, "window_vbls": WINDOW_VBLS, "window_cycles": window_cycles(run.log),
            "measured_at": measured_now(),
            "frames": functions.get(FRAME_SYMBOL, {}).get("arrivals", 0), "functions": functions}
    refuse_a_window_of_the_wrong_length(side, data["window_cycles"])
    refuse_symbols_hatari_dropped(run.log)
    if not data["frames"]:
        raise SystemExit(f"FAIL: nothing arrived at {FRAME_SYMBOL} in the window — either the "
                         f"symbols were not loaded (they must precede `profile on`, and autoload "
                         f"must be off before that) or the window opened somewhere else")
    data["sound_tick"] = sound_tick_cost(side, run, functions, data["window_cycles"])
    (OUT / f"profile-{side}.json").write_text(json.dumps(data, indent=1, sort_keys=True))
    return data


def load(side):
    """One side's .json, or a refusal naming the run that has not been made.

    THE WINDOW IS CHECKED BY `compare`, not here, because it is a check between two files."""
    path = OUT / f"profile-{side}.json"
    if not path.exists():
        raise SystemExit(f"FAIL: {path} is missing — run `python3 atari/profile.py {side}` first")
    return json.loads(path.read_text())


# ---- the report ----------------------------------------------------------------------------------
def per_frame(totals, field, data):
    return totals.get(field, 0) / data["frames"]


def print_side(data):
    """One side's headline plus its most expensive functions, per frame.

    Both counts are in the table because they answer different questions: `calls` is what the cycles
    beside it were charged over, `arrivals` is how often the function was reached. A branch-entered
    function has arrivals and no calls, and carries no cycles of its own at all."""
    frames, window = data["frames"], data["window_cycles"]
    # OFF THE EMULATED CLOCK, not off an assumed refresh: the window's own cycles are what elapsed
    # in it, so the fps below holds whatever the shifter was doing.
    seconds = window / ST_CPU_HZ
    loop = data["functions"].get(FRAME_SYMBOL, {})
    print(f"\n== {data['side'].upper()}: {frames} frames in {data['window_vbls']} vblanks "
          f"({seconds:.2f}s) = {frames / seconds:.2f} fps ==")
    print(f"   {window / frames / 1e3:9.1f}K cycles/frame over the whole window "
          f"({window / 1e6:.1f}M cycles, every profiled region)")
    if loop.get("calls"):
        print(f"   {loop[INCLUSIVE] / frames / 1e3:9.1f}K cycles/frame inside {FRAME_SYMBOL} itself "
              f"({loop[INCLUSIVE] / window * 100:.1f}% of the window)")
    tick = data.get("sound_tick")
    if tick:
        print(f"   {tick['cycles'] / frames / 1e3:9.1f}K cycles/frame in the 200 Hz sound tick "
              f"= {tick['per_tick']:,.0f} a tick over {tick['ticks']:,} of them "
              f"({tick['cycles'] / window * 100:.1f}% of the window, "
              f"{tick.get('bytes', 0):,} bytes of code)")
    print(f"   {'function':<{NAME_COLUMN}} {'calls':>7} {'arrivals':>9} {'incl/frame':>12} "
          f"{'excl/frame':>12} {'cyc/call':>10}")
    ranked = sorted(data["functions"].items(), key=lambda item: -item[1][INCLUSIVE])
    for name, totals in ranked[:TOP_ROWS]:
        calls = totals["calls"]
        per_call = f"{totals[INCLUSIVE] / calls:.0f}" if calls else "-"
        print(f"   {name:<{NAME_COLUMN}} {calls:>7} {totals['arrivals']:>9} "
              f"{totals[INCLUSIVE] / frames / 1e3:>11.1f}K "
              f"{totals[EXCLUSIVE] / frames / 1e3:>11.1f}K {per_call:>10}")


# One comparable function, both sides, per frame. `over` — what ours costs over the original's — is
# first because that is what the table is sorted on, and it is the campaign's whole worklist.
Ratio = namedtuple("Ratio", "over name ours_incl theirs_incl ours_excl theirs_excl "
                            "ours_calls theirs_calls ours_share theirs_share")


def attributed_share(totals):
    """How much of a function's traffic Hatari actually CHARGED it: calls over arrivals.

    One is a routine every entry of which was a subroutine call. Near zero is one the binary mostly
    reaches some other way — an interrupt vector, a `bra` — whose cycles are then not in this row
    at all, and whose total is a fraction of what the function really cost."""
    return totals["calls"] / totals["arrivals"] if totals["arrivals"] else 0.0


def ratio_rows(ours, theirs):
    """Every name both sides carry, as a Ratio, with the ones nobody charged dropped."""
    rows = []
    for name, mine in ours["functions"].items():
        shipped = theirs["functions"].get(name)
        if shipped is None:
            continue
        row = Ratio(per_frame(mine, INCLUSIVE, ours) - per_frame(shipped, INCLUSIVE, theirs), name,
                    per_frame(mine, INCLUSIVE, ours), per_frame(shipped, INCLUSIVE, theirs),
                    per_frame(mine, EXCLUSIVE, ours), per_frame(shipped, EXCLUSIVE, theirs),
                    mine["calls"] / ours["frames"], shipped["calls"] / theirs["frames"],
                    attributed_share(mine), attributed_share(shipped))
        if row.ours_incl or row.theirs_incl:
            rows.append(row)
    return rows


def print_ratios(ours, theirs):
    """The output this file exists for: the same function on both sides, per frame, ranked by what
    ours costs over the original's.

    A ROW IS ONLY A RATIO WHERE BOTH SIDES WERE CHARGED. Hatari attaches cycle totals to SUBROUTINE
    arrivals alone, so a routine the two binaries ENTER DIFFERENTLY carries a full total on one side
    and none on the other, and the subtraction between them is arithmetic on an attribution rather
    than on a cost. `timer_c_sound_isr` is the measured example and it is not a small one: both
    sides tick 3,329 times in the window, but ours is reached by a `jsr` out of `bg_timer_c_tick`
    and the shipped one straight off its autovector — whose cycles Hatari leaves in whatever the
    interrupt landed in. Ranked as a ratio it reads x47.8 and second in the table. So those rows are
    listed BELOW the ranking, under what they actually are."""
    ranked, incomparable = [], []
    for row in ratio_rows(ours, theirs):
        comparable = min(row.ours_share, row.theirs_share) >= ATTRIBUTED_SHARE
        (ranked if comparable else incomparable).append(row)
    print("\n== THE SAME FUNCTION, BOTH SIDES, CYCLES PER FRAME — ranked by ours over theirs ==")
    print(f"   {'function':<{NAME_COLUMN}} {'ours incl':>10} {'orig incl':>10} {'over':>10} "
          f"{'x':>6} {'ours excl':>10} {'orig excl':>10} {'calls o/t':>13}")
    for row in sorted(ranked, key=lambda item: -item.over)[:TOP_ROWS]:
        print(f"   {row.name:<{NAME_COLUMN}} {row.ours_incl:>10,.0f} {row.theirs_incl:>10,.0f} "
              f"{row.over:>+10,.0f} {row.ours_incl / row.theirs_incl:>6.2f} "
              f"{row.ours_excl:>10,.0f} {row.theirs_excl:>10,.0f} "
              f"{row.ours_calls:>6.1f}/{row.theirs_calls:<6.1f}")
    if not incomparable:
        return
    print("\n   NOT A RATIO — one side's cycles are mostly NOT in its row, because the two binaries")
    print("   enter these differently (an interrupt vector against a `jsr`, a `bra` against a call).")
    print(f"   The last column is the share of arrivals Hatari charged, ours/theirs:")
    for row in sorted(incomparable, key=lambda item: -abs(item.over))[:ONE_SIDE_ROWS]:
        print(f"   {row.name:<{NAME_COLUMN}} {row.ours_incl:>10,.0f} {row.theirs_incl:>10,.0f} "
              f"{'':>10} {'':>6} {row.ours_excl:>10,.0f} {row.theirs_excl:>10,.0f} "
              f"{row.ours_share:>6.2f}/{row.theirs_share:<6.2f}")


def print_one_side_only(data, other, label):
    """Everything one side has a row for that the other has no NAME for at all, summed EXCLUSIVE.

    EXCLUSIVE because inclusive totals nest: summing them over a set of functions counts a callee's
    cycles once per caller in the set.

    THIS IS NOT "WHAT THE SHIM COSTS", and reading it that way over-counts. The set is every name
    the OTHER side's map does not happen to carry, and the two maps are not equally fine: ours is
    the linked ELF (447 symbols), the shipped side's is `../names.txt` (133). So our side's list
    holds real shim — `bubble_os.s`'s trap doors, `bubble_backend.c`'s stand-ins, the Timer C ISR —
    beside PORTED GAME CODE our source simply named more finely than the name map did
    (`game_room_frame_tail` is an un-named slice of the original's branch-entered `game_top_loop`;
    the sound engine's envelope and LFO steps are inside its ISR). The shipped side's list is
    dominated by `vdi_call`, which is the ROM VDI. Subtracting the two totals is therefore not a
    shim budget; the rows under each are what to read."""
    only = {name: totals for name, totals in data["functions"].items()
            if name not in other["functions"]}
    spent = sum(totals[EXCLUSIVE] for totals in only.values()) / data["frames"]
    print(f"   {label}: {len(only)} symbol(s), {spent:,.0f} cycles/frame exclusive")
    for name, totals in sorted(only.items(), key=lambda item: -item[1][EXCLUSIVE])[:ONE_SIDE_ROWS]:
        print(f"      {name:<{NAME_COLUMN}} {totals[EXCLUSIVE] / data['frames']:>10,.0f}")


def compare():
    """Both sides' summaries and the ranked difference, refusing two windows of different lengths."""
    ours, theirs = load(OURS), load(SHIPPED)
    if ours["window_vbls"] != theirs["window_vbls"]:
        raise SystemExit(f"FAIL: the two sides were measured over different windows "
                         f"({ours['window_vbls']} vblanks vs {theirs['window_vbls']}) — re-run both")
    print_side(ours)
    print_side(theirs)
    # NOTHING HERE CAN KNOW WHICH BINARY EACH SIDE SAW. `ours` rebuilds before it measures, so its
    # .json describes whatever was linked then; the two files can be weeks apart and the ratio table
    # would rank a worklist off two incomparable windows and look exactly like a right one. Printing
    # both stamps is what a reader needs to notice.
    print(f"\n   ours measured {ours.get('measured_at', UNSTAMPED)}, "
          f"the original {theirs.get('measured_at', UNSTAMPED)}")
    mine = ours["window_cycles"] / ours["frames"]
    shipped = theirs["window_cycles"] / theirs["frames"]
    print(f"\n== HEADLINE: ours {mine / 1e3:.1f}K cycles/frame against the original's "
          f"{shipped / 1e3:.1f}K = x{mine / shipped:.2f} ==")
    mine_tick, shipped_tick = ours.get("sound_tick"), theirs.get("sound_tick")
    if mine_tick and shipped_tick:
        print(f"   the 200 Hz sound tick, off the per-address data: ours "
              f"{mine_tick['per_tick']:,.0f} cycles a tick against the original's "
              f"{shipped_tick['per_tick']:,.0f} = "
              f"x{mine_tick['per_tick'] / shipped_tick['per_tick']:.2f}")
    print_ratios(ours, theirs)
    print("\n== WHAT ONLY ONE SIDE HAS ==")
    print_one_side_only(ours, theirs, "named only in OUR map (shim AND finer-named game code)")
    print_one_side_only(theirs, ours, "named only in ../names.txt (mostly the ROM VDI)")


# ---- the per-frame timeline ----------------------------------------------------------------------
# One arrival's reading, before it is turned into a cycle count: the vertical blank it fell in, and
# how far into that blank it was.
Arrival = namedtuple("Arrival", "vbl frame_cycles")


def frame_arrivals(log, frame_pc):
    """Every arrival at the frame PC the debugger printed, in order."""
    return [Arrival(int(vbl), int(cycles))
            for pc, vbl, cycles in DEBUGGER_ENTRY_RE.findall(log) if int(pc, 16) == frame_pc]


def refuse_a_vblank_of_the_wrong_length(side, arrivals):
    """THE 60 Hz PIN FOR THE MODE THE PROFILER DOES NOT COVER.

    `FrameCycles` counts from the start of the current video frame, so no reading can reach the
    frame's own length — and on a 50 Hz shifter (160,256 cycles) readings would run half again past
    the 133,604 this file is built on. That is not merely a 20% error in the fps: `frame_costs`
    linearises an arrival as `vbl * CYCLES_PER_VBL + frame_cycles`, so with too small a multiplier
    the stream stops being monotonic and a frame's cost comes out NEGATIVE, with nothing failing.

    One-sided on purpose. A reading close to the frame length is normal — the maximum over a few
    hundred arrivals lands within a percent of it (measured: 133,580 of 133,604) — so only the
    overshoot is evidence, and that is exactly the wrong-refresh case."""
    past = max((arrival.frame_cycles for arrival in arrivals), default=0)
    if past >= CYCLES_PER_VBL:
        raise SystemExit(f"FAIL: {side}: an arrival was {past:,} cycles into a vblank this file "
                         f"sizes at {CYCLES_PER_VBL:,} — the machine is not the 60 Hz one "
                         f"`smoke.hatari_arguments` describes, and every figure below would be "
                         f"wrong by the difference")


def refuse_a_truncated_window(side, arrivals):
    """Refuse a window Hatari's own `--run-vbls` cap ended instead of the closing breakpoint.

    `collect` cannot tell the two apart: a capped run also exits 0, also leaves no fault line, and
    also stops being alive. What it leaves behind is a SHORT window, and the arrivals carry the
    vblank numbers that say so. The profiler's side of the house is caught by `stats_block` finding
    no dump echo; this is the frames side's equivalent, and without it a run cut in half prints
    half the frames over the whole window's length as a plausible fps."""
    spanned = arrivals[-1].vbl - arrivals[0].vbl
    if spanned < WINDOW_VBLS * MINIMUM_WINDOW_SPAN:
        raise SystemExit(f"FAIL: {side}: the timed arrivals span {spanned} vblanks of the "
                         f"{WINDOW_VBLS}-vblank window — the run ended early, most likely on "
                         f"`smoke.hatari_arguments`' own `--run-vbls` cap")


def frame_costs(arrivals):
    """The cycles between consecutive arrivals — one whole room frame each."""
    absolute = [arrival.vbl * CYCLES_PER_VBL + arrival.frame_cycles for arrival in arrivals]
    return [later - earlier for earlier, later in zip(absolute, absolute[1:])]


def print_frames(arrivals, side):
    """The readings a timeline has that a window average does not, and the rows behind them.

    WHAT IS COUNTED IS A TIMED FRAME, and there is one fewer of them than the window holds twice
    over: the window's opening breakpoint is `:once :quiet`, so the first arrival prints no line and
    arms the clock instead, and N printed arrivals bound N-1 complete frames. So the fps here is
    taken from the frames THEMSELVES — their own cycles over their own elapsed time — rather than
    from a count divided by the window, which would carry that shortfall into the headline. It is
    the same number the profiler's window average reports, arrived at from the other end."""
    refuse_a_vblank_of_the_wrong_length(side, arrivals)
    if len(arrivals) < MINIMUM_TIMED_ARRIVALS:
        raise SystemExit(f"FAIL: the {side} run printed {len(arrivals)} arrival(s) at "
                         f"{FRAME_SYMBOL} — either the clock never fired or `:quiet` swallowed its "
                         f"entry lines, and there is no frame here to time")
    refuse_a_truncated_window(side, arrivals)
    costs = frame_costs(arrivals)
    ordered = sorted(costs)
    p90 = ordered[int(P90 * (len(ordered) - 1))]
    seconds = sum(costs) / ST_CPU_HZ
    print(f"\n== {side.upper()}, per frame: {len(costs)} timed frames over {seconds:.2f}s "
          f"(the window is {WINDOW_VBLS} vblanks) ==")
    print(f"   cycles a frame: min {min(costs):>9,.0f}   median {median(costs):>9,.0f}"
          f"   mean {mean(costs):>9,.0f}   p90 {p90:>9,.0f}   max {max(costs):>9,.0f}")
    print(f"   vblanks a frame: median {median(costs) / CYCLES_PER_VBL:.2f}"
          f"   mean {mean(costs) / CYCLES_PER_VBL:.2f}")
    print(f"   {len(costs) / seconds:.2f} fps, off the frames' own cycles")
    path = OUT / f"frames-{side}.txt"
    path.write_text("".join(f"{index} {cost:.0f}\n" for index, cost in enumerate(costs)))
    print(f"   {path} — one `index cycles` row a frame")


def main():
    args = sys.argv[1:]
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    if args in ([OURS], [SHIPPED]):
        print_side(summarise(args[0], measure(args[0], PROFILE)))
    elif args == [COMPARE]:
        compare()
    elif len(args) == 2 and args[0] == FRAMES and args[1] in (OURS, SHIPPED):
        run = measure(args[1], FRAMES)
        print_frames(frame_arrivals(run.log, run.frame_pc), args[1])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
