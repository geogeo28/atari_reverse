#!/usr/bin/env python3
"""Boot the reconstructed FLYSHARK.PRG on a 68000 and judge it on every surface a run has.

    bash atari/build.sh smoke && python3 atari/smoke.py
    python3 atari/smoke.py --keep-going        # report every failure instead of the first

WHAT IT DOES. Two Hatari runs of the same recipe — `atari/disk` as C: with our .PRG in `AUTO\\`, and
`../bin/disk` as C: with the ORIGINAL's — both TOS 1.04, both `--memsize 1`, both headless. Neither
uses `--auto`: TOS's own `\\AUTO\\` scan runs the program before the desktop, which is the recipe the
release ships and the one `../tools/boot_shots.py` proved the original by.

THE SIX SURFACES (docs/on-target-execution.md, "The observable surfaces"), and what each is here:

  memory                  the framebuffer the game has just published, byte for byte against the
                          ORIGINAL's at the same anchor — the strongest check in this file, and the
                          one a mis-anchor control proves is sensitive
  the trap ledger         `--trace os_base`: our Fopen sequence against the original's, same eight
                          names in the same order
  the hardware-state      the sixteen colour registers, the resolution byte and the video base,
  vector                  read back by the program at its anchor and carried in STATE.BIN — plus
                          `Physbase()` compared with the address that was handed to `Setscreen`,
                          which is the only instrument that catches a base the shifter truncated
  rendered pixels         the title picture, recognised by its own palette being wholly on screen
  timelines               the run's PACING (vertical blanks per drawn frame) and the seam counters:
                          hardware stores, PSG writes, OS calls, files
  exit status and the log Hatari's return code and its bus/address-error and halt lines

WHAT IT CANNOT DO, and this is the honest half. **The joystick is untestable headless.** Hatari's
`--cmd-fifo` has no joystick event at all, and a key bound to its keyboard-as-joystick emulation is
SWALLOWED before it reaches the ST (`tools/hatari_headless.py`), so the stick cannot be pressed from
outside. What this file CAN exercise is the rest of the same path: it presses a real KEY, which
arrives at the same 6850 through the same vector and the same handler, and asserts the byte the
handler filed. Everything from there to a joystick packet — the IKBD's `$14` mode, the `$FE`/`$FF`
headers, the two continuation vectors — stays a runbook step with a person and a stick, and
README.md says so.
"""
import argparse
import re
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]                       # projects/flyingshark
REPO = PROJECT.parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(PROJECT / "tools"))

from hatari_headless import (  # noqa: E402
    HATARI, HeadlessSession, action_file, await_file, distinct_colours, locate_by_signature,
    log_faults, require_gemdos_tos, strip_log_noise, tos_label)
# ../../tools/boot_shots.py's recogniser, imported rather than restated: the same three functions
# decide what the title picture is there and here.
from boot_shots import palette_colours, st_colours, title_palette  # noqa: E402

# --- the media -----------------------------------------------------------------------------------
OURS_DRIVE = HERE / "disk"
ORIGINAL_DRIVE = PROJECT / "bin" / "disk"
OURS_PRG = OURS_DRIVE / "AUTO" / "FLYSHARK.PRG"
ORIGINAL_PRG = ORIGINAL_DRIVE / "AUTO" / "FLYSHARK.PRG"
STAGED_IMAGE = OURS_DRIVE / "FLYSHARK.IMG"
TITLE_NEO = ORIGINAL_DRIVE / "A" / "FLY_SHK.NEO"
RECORD_FILENAME = "STATE.BIN"       # flyshark_main.c's FILE_STATE_RECORD, and the marker that says
                                   # a .PRG was built with the record compiled in (see below)
STATE_RECORD = OURS_DRIVE / RECORD_FILENAME
# ...and its BEACON, which a smoke build writes as early as a file can be written and whose four
# bytes ARE the image base (`flyshark_main.c`, `write_file(FILE_BEACON, &g_record[REC_IMAGE_BASE])`,
# beside the three record fields it fills before anything else). It is a wake-up AND a locate, and
# the second half is what makes the title capture armable: the window between
# `level0_assets_loaded` and the sprite bank landing on the picture is a fraction of a second, and
# the alternative locate — a savebin of the whole megabyte, then a scan — spends a good part of it.
# MEASURED: with the base read out of a RAM dump the capture came back BLACK about one run in three,
# over seven runs of one binary; reading it from the beacon takes the dump off the critical path.
#
# A STALE BEACON CANNOT PUT THIS DRIVER ON THE WRONG ADDRESS, which is what the RAM scan bought and
# has to be paid for another way: the file is deleted before the run starts, so anything read here
# was written by THIS boot, and the base it names is checked against the record's own — read out of
# RAM after the capture, off the critical path — before any surface is judged on it.
BEACON_BYTES = 4
BEACON = OURS_DRIVE / "STARTED.BIN"
# The floppy. `--floppy` boots the volume `mkfloppy.py` wrote, which carries whichever build.sh mode
# ran last — the PLAY build is the one a person puts in a drive.
FLOPPY = OURS_DRIVE / "FLYSHARK.ST"
OUT_DIR = PROJECT / "out" / "smoke"

# --- the machine ---------------------------------------------------------------------------------
TOS_ROM = REPO / "tools" / "hatari" / "TOS104US.img"
MEMSIZE_MB = 1                 # the machine the 1988 release asks for, and the tighter budget
ST_RAM_BYTES = 0x100000
RUN_VBLS = 20000               # Hatari quits by itself at this count so a hung run cannot sit for ever
TRACE_ARGUMENTS = ("--trace", "os_base")

# --- the image model, mirrored from the cores ----------------------------------------------------
# Every value here is a `#define` in a C header or a constant in `../test/abi.py`, and `MIRRORS`
# below names the home of each so that `check_the_mirrors` can read it and compare. That is what
# makes a header that moved fail here BY NAME rather than by a wrong number — the project's own
# `test/test_constants.py` does the same thing for the batteries, and a comment alone would not
# (CLAUDE.md §5: pin the other equal with a test).
LOAD_BASE = 0x10000                 # globals.h FS_LOAD_BASE
PROGRAM_END = 0x5aede               # globals.h FS_PROGRAM_END
SCREEN_BYTES = 0x7d00               # globals.h SCREEN_BYTES — one 320x200 four-plane frame
SCREEN_RING_BYTES = 0x1f900         # globals.h SCREEN_RING_BYTES
SCREEN_RING_ALIGN = 0x100           # globals.h SCREEN_RING_ALIGN — the RING's rounding
IMAGE_ALIGN = 256                   # flyshark_main.c IMAGE_ALIGN — a different fact under a
                                    # different name: what the shim rounds its own array up to, so
                                    # that every screen address inside it can be 256-aligned too
RING_OFFSETS = (0x7800, 0xfa00, 0x17700, 0x1f400)   # globals.h SCREEN_RING_0_OFF .. _3_OFF
TARGET_PHYSBASE = 0x7f800           # shim_include/init.h FS_TARGET_PHYSBASE (= test/abi.py's)
A_SCREEN_DRAW = 0x16416             # globals.h
A_SCREEN_PREV1 = 0x1641a            # globals.h — the frame published one render_frame ago
A_SCROLL_POS = 0x17758              # scroll.h
A_KEY_LAST_SCANCODE = 0x17781       # irq.h
A_KEY_BITS = 0x17780                # irq.h
A_PALETTE_GAME = 0x16294            # init.h A_palette_game — sixteen colour words in the image
A_LEVEL0_ASSETS_LOADED = 0x176ea    # init.h — `st $176ea`, one statement before the picture is
                                    # overwritten by the sprite bank, which is when it is captured
TITLE_READY_FLAG = 0xff             # common.h SCC_TRUE — what a 68000 `Scc` writes
PALETTE_PENS = 16
# The eight file records the boot chain loads, in ../include/globals.h's order. Their LENGTHS are
# not typed here: they are read out of the staged image, which is where the game keeps them.
BOOT_FILE_RECORDS = (0x162ee, 0x16304, 0x1631a, 0x16330, 0x16346, 0x1635a, 0x1636e, 0x16382)
FILE_REC_LEN = 4             # a record is [dest.l][len.l] then the ASCIZ DOS path
FILE_REC_NAME = 8

# Where each of the above lives: (this module's name, the file, the name in that file). The C
# headers are read with a `#define` regex and `abi.py` with an assignment regex; both are read at
# run time by `check_the_mirrors`, which is the first thing this file checks.
CORE_INCLUDE = PROJECT / "recreate" / "include"
SHIM_INCLUDE = HERE / "shim_include"
ABI = PROJECT / "recreate" / "test" / "abi.py"
MIRRORS = (
    ("LOAD_BASE", CORE_INCLUDE / "globals.h", "FS_LOAD_BASE"),
    ("PROGRAM_END", CORE_INCLUDE / "globals.h", "FS_PROGRAM_END"),
    ("SCREEN_BYTES", CORE_INCLUDE / "globals.h", "SCREEN_BYTES"),
    ("SCREEN_RING_BYTES", CORE_INCLUDE / "globals.h", "SCREEN_RING_BYTES"),
    ("SCREEN_RING_ALIGN", CORE_INCLUDE / "globals.h", "SCREEN_RING_ALIGN"),
    ("A_SCREEN_DRAW", CORE_INCLUDE / "globals.h", "A_screen_draw"),
    ("A_SCREEN_PREV1", CORE_INCLUDE / "globals.h", "A_screen_prev1"),
    ("A_SCROLL_POS", CORE_INCLUDE / "scroll.h", "A_scroll_pos"),
    ("A_KEY_BITS", CORE_INCLUDE / "irq.h", "A_key_bits"),
    ("A_KEY_LAST_SCANCODE", CORE_INCLUDE / "irq.h", "A_key_last_scancode"),
    ("A_PALETTE_GAME", CORE_INCLUDE / "init.h", "A_palette_game"),
    ("A_LEVEL0_ASSETS_LOADED", CORE_INCLUDE / "init.h", "A_level0_assets_loaded"),
    ("TARGET_PHYSBASE", SHIM_INCLUDE / "init.h", "FS_TARGET_PHYSBASE"),
    ("IMAGE_ALIGN", HERE / "flyshark_main.c", "IMAGE_ALIGN"),
    # ...and the one that is not a #define at all: the harness's own choice of Physbase, which the
    # shim's FS_TARGET_PHYSBASE exists to equal. If they ever differ, every off-target green is
    # about a screen ring the machine does not build — and nothing else in either tree would say so.
    ("TARGET_PHYSBASE", ABI, "SCREEN_RING_PHYSBASE"),
)
DEFINE_PATTERN = r"^#define\s+%s\s+(0x[0-9a-fA-F]+|\d+)u?\b"
ASSIGNMENT_PATTERN = r"^%s\s*=\s*(0x[0-9a-fA-F]+|\d+)\b"

# --- the anchor ----------------------------------------------------------------------------------
# WHERE THE TWO RUNS ARE COMPARED. `scroll_advance` adds two to `scroll_pos` once per attract frame,
# so this is attract frame 120 — far enough in for the map to have scrolled a screen and a half and
# for two of the three text pages to have been compiled, and well inside the 200 frames the smoke
# build draws before it stops. The breakpoint fires on the store, which is BEFORE the frame is
# drawn, so what both sides are asked for is the frame they last PUBLISHED.
ANCHOR_SCROLL_POS = 0xf0
SCROLL_POS_PER_FRAME = 2
# The smoke build's own limit, which build.sh passes and this file only reports.
SMOKE_ATTRACT_FRAMES = 200
# The two `Setscreen`s the boot makes before the first frame: `boot_init`'s resolution call at
# 0x14c18 and `init_load_assets_title`'s at 0x11258. Every other one is a frame being published.
BOOT_SETSCREEN_CALLS = 2
# ...and the `Setpalette`s. THIS ONE IS A SHAPE, NOT A COUNT, and the difference is the whole point.
#
# The flow installs a palette FOUR times before the attract screen spins — three in
# `init_load_assets_title` and `enter_title`'s own `set_palette_black` — and then TWO more every time
# `title_attract_loop` goes round: `title_attract_prescroll`'s `set_palette_black` at its head and
# `title_attract_start_tune`'s `set_palette_game` before the frame spin. So the invariant is "four, plus two per pass", and the
# smallest run that reaches the attract screen at all makes six.
#
# AN EQUALITY HERE WAS A TRANSCRIPT OF ONE RUN'S PACE. The loop goes round when the module says its
# tune has finished, and the tune advances on the VERTICAL BLANK while this build's limit counts
# FRAMES — so the number of passes inside 200 frames is a function of how fast a frame is. It was 8
# (two passes) when a frame cost 15.8 blanks and became 6 (one pass) at 5.24, for no reason but the
# performance campaign (`../STATUS.md`, "On-target performance"), and it would move again on the next
# lever — reddening with a message that sends the reader hunting a flow regression that is not there.
# The shape below is what the FLOW claims and it holds at any pace; a real regression (a pass that
# stopped installing one of its two, a boot that installed a fifth) still fails it.
SETPALETTE_CALLS_BEFORE_THE_ATTRACT_SPIN = 4
SETPALETTE_CALLS_PER_ATTRACT_PASS = 2
BOOT_SETPALETTE_CALLS = (SETPALETTE_CALLS_BEFORE_THE_ATTRACT_SPIN
                         + SETPALETTE_CALLS_PER_ATTRACT_PASS)   # the fewest a run can make: one pass
# GEMDOS Super(0)'s answer in the kit's token model ('\0SUP'), which `shim_include/os.h` keeps so
# that the core's return value means the same thing on both shores.
OS_SUPER_TOKEN = 0x00535550
# What a 68000 `Scc` writes, and what `st $176ea` leaves in `level0_assets_loaded`.
SCC_TRUE = 0xff
# What the run's stack needs at the top of the TPA: the C call chain plus an interrupt frame on top
# of it, with room to see a change coming. Measured headroom on a 1 MB ST is 413,074 B, so this is a
# floor with two orders of magnitude of slack — it is here to catch a machine or a build that has
# eaten the TPA, not to bound the stack precisely.
STACK_FLOOR_BYTES = 64 * 1024
# The 68000's status register, and the level the ORIGINAL establishes for itself at 0x14cce
# (`move.w #$2300,sr`). This build inherits GEMDOS's instead — ../src/init.c says why the mask pair
# is not in the C — so the equality is measured, not designed.
SR_SUPERVISOR = 0x2000
SR_IPL_SHIFT = 8
SR_IPL_MASK = 7
ORIGINAL_IPL = 3
# TWO KEYS, and the pair is the point. The first is NOT one of the eight `key_watch_scancodes`, so
# it exercises the whole ACIA path without moving a bit the game acts on ('A' makes 0x1e, breaks
# 0x9e). The second IS one — the keypad 4 that `check_cheat_name` arms on, `key_watch_scancodes`
# bit 0 — and it is the POSITIVE control for the ladder: without it, "no bit moved" is equally true
# of a handler whose ladder never runs. It cannot be caught in the record, because the make code
# clears again on release; it is caught by a breakpoint on the byte itself.
PROBE_KEY_MAKE = 0x1e
PROBE_KEY_BREAK = 0x9e
WATCHED_KEY_MAKE = 0x6b            # ../include/hud.h's CHEAT_ARM_KEY_BIT is this key's bit, 0
WATCHED_KEY_BIT = 0x01

# --- timings ------------------------------------------------------------------------------------
#
# EMULATION IS REAL TIME here (there is no --fast-forward), so every deadline below is wall-clock —
# and wall-clock on a machine that may be running something else. Measured on this workspace: a
# concurrent second emulator stretched a 30 s run to 155 s. So the deadlines are generous by a
# factor of about five over a quiet box, nothing waits on a FIXED sleep for something it can poll
# for, and every give-up prints the elapsed time and the tail of Hatari's own log — a deadline that
# fires should tell you whether the machine was slow or the program was wrong.
TITLE_DEADLINE_SECONDS = 480.0
ANCHOR_DEADLINE_SECONDS = 900.0
RECORD_DEADLINE_SECONDS = 900.0
# The one place a fixed wait is right: nothing can be in RAM before TOS has booted, and a dump of a
# megabyte is not free. These are "it cannot possibly be ready before this", and the deadline below
# is "it has had every chance".
ORIGINAL_SETTLE_SECONDS = 30.0
FLOPPY_SETTLE_SECONDS = 20.0
LOCATE_DEADLINE_SECONDS = 360.0
LOCATE_POLL_SECONDS = 5.0
# OUR OWN RUN DOES NOT POLL FOR THE PROGRAM AT ALL — it waits for the beacon the smoke build writes
# as its first act, because the window this driver has to arm its title capture in is the boot's own
# file loading, which off a GEMDOS drive is a fraction of a second. MEASURED, twice, before the
# beacon existed: at a five-second poll the arming lost that race two runs in three and the capture
# came back as the attract screen (4/15 of the title's palette); at half a second it still lost it,
# finding the program 12 s after power-on with `level0_assets_loaded` already set. A poll cannot win
# a sub-second window; a file that appears the instant GEMDOS writes it can.
BEACON_DEADLINE_SECONDS = 300.0
OURS_POLL_SECONDS = 0.5
# How much of Hatari's log a give-up prints. Its last lines are what say whether the machine faulted,
# was still booting, or was simply not asked to do anything yet.
LOG_TAIL_LINES = 12

# --- the record ----------------------------------------------------------------------------------
RECORD_MAGIC = 0x46534b31          # 'FSK1', flyshark_main.c FS_RECORD_MAGIC
RECORD_TAIL = 0x444f4e45           # 'DONE'
# flyshark_main.c's enum, in order. THE LENGTH IS THE PIN: the record's own second field is its
# field count, and a name added there and not here (or the other way round) fails at the parse with
# both numbers printed rather than shifting every value after it by one.
RECORD_FIELDS = """
MAGIC FIELDS IMAGE_BASE IMAGE_BYTES PROGRAM_STAGED_BYTES
TPA_LOW TPA_HIGH PROGRAM_TOP HEADROOM IMAGE_TAIL_DIRTY IMAGE_GUARD_CHANGED
PHYSBASE_WANTED PHYSBASE_AT_BOOT RAW_VIDEO_BASE_AT_BOOT
SCREEN_RING_BASE SCREEN_RING_0 SCREEN_RING_1 SCREEN_RING_2 SCREEN_RING_3
SUPER_TOKEN TOS_JOYVEC_SAVED VBL_CHAIN TICKS_AT_BOOT TICKS_AT_END
VBL_TICKS ACIA_TICKS VBL_ENTRIES ACIA_ENTRIES ACIA_JOY0_ENTRIES ACIA_JOY1_ENTRIES
ATTRACT_FRAMES ATTRACT_FRAME_LIMIT FATAL FATAL_VECTOR FATAL_HANDLER SR_AT_END
FILE_OPENS FILE_OPEN_FAILURES FILE_BYTES_READ FILE_REFUSALS
SETSCREEN_CALLS SETPALETTE_CALLS VSYNC_CALLS IKBD_COMMANDS
HW_WRITES HW_RMW HW_READS PSG_WRITES PSG_REFUSED
PHYSBASE_AT_END RAW_VIDEO_BASE_AT_END REZ_AT_END
SCREEN_DRAW_AT_END SCREEN_PREV1_AT_END SCROLL_POS_AT_END LEVEL0_ASSETS_LOADED
""".split() + [f"PEN{pen}" for pen in range(PALETTE_PENS)] + """
VBL_VECTOR_AFTER ACIA_VECTOR_AFTER JOYVEC_AFTER PHYSBASE_AFTER REZ_AFTER TICKS_AT_TEARDOWN
ACIA_VECTOR_BEFORE REZ_BEFORE TAIL
""".split()

# The GEMDOS token a `--trace os_base` line carries for an open, and the three files that are OURS
# rather than the game's: a comparison of the two runs' ledgers has to leave them out or it is
# comparing the shim's own bookkeeping with nothing.
TRACE_FOPEN = "Fopen("
SHIM_ONLY_FILES = ("FLYSHARK.IMG", "STARTED.BIN", "STATE.BIN")

# The game's own pacing: `render_frame` waits for the third vertical blank of the frame it just
# published (../src/sprite.c, RENDER_FRAME_VBL_BUDGET), so no drawn frame can cost fewer than this.
VBLS_PER_FRAME_FLOOR = 3
VBL_HZ = 50


class Failures:
    """Collected findings, so a run can report every surface rather than the first that reddens."""

    def __init__(self, keep_going):
        self.keep_going = keep_going
        self.found = []

    def check(self, ok, message):
        print(f"  {'ok  ' if ok else 'FAIL'}  {message}")
        if ok:
            return True
        self.found.append(message)
        if not self.keep_going:
            raise SystemExit(f"FAILED: {message}")
        return False


def hatari_arguments(media, trace_path, run_vbls=RUN_VBLS):
    """The whole Hatari command line except `--cmd-fifo`, which the session appends.

    `media` is the only thing that varies between the three runs — a GEMDOS drive for ours and the
    original, a floppy for the .ST — and it is a parameter rather than a second list because the
    machine the runs are compared ON has to be the same one: TOS, memory size, frameskips and the
    trace flags all decide what the comparison means.

    `run_vbls` is the emulator's own deadline and is a parameter for ONE caller: `profile.py` runs
    the same machine for as long as a measurement window needs, which is longer than any check here
    waits for. Every smoke run takes the default, so the machine this file judges is unchanged.
    """
    return [HATARI, "--tos", str(TOS_ROM), "--machine", "st", "--memsize", str(MEMSIZE_MB),
            "--monitor", "rgb", "--confirm-quit", "off", "--statusbar", "off",
            "--drive-led", "off", "--frameskips", "0", "--sound", "off",
            "--run-vbls", str(run_vbls), *media,
            *TRACE_ARGUMENTS, "--trace-file", str(trace_path)]


def gemdos_drive(path):
    return ("--harddrive", str(path))


def arm_title_capture(session, work, shots, image_base):
    """Photograph the title picture at a MOMENT rather than by polling for it.

    ../tools/boot_shots.py photographs the original by polling and stretching the timeline
    (`--slowdown 4`), because it has no way into the program: the picture is on screen only while
    the rest of the assets load, which off a host directory is a second or two, and four anchors
    were tried there before that one worked. This build can do better, because the program itself
    reaches a known state at that moment: `init_load_assets_sprites` sets `level0_assets_loaded`
    ONE STATEMENT before it reads `A\\SPRITES.cru` over the picture's buffer, with the picture
    displayed and its own palette installed. So the capture is a breakpoint on that byte.

    TWO CAPTURES, AND THE BETTER OF THEM IS THE ANSWER, because each is wrong in a different way and
    neither is wrong in both. Class 8's rule is stop-then-shoot: the display surface is built
    scanline by scanline, so a capture taken where a breakpoint fires can mix that frame with the one
    before, and the cure is to photograph at the NEXT vertical blank (`b VBL > VBL :once` — Hatari
    substitutes the expression's current value on the right). But that cure assumes the program is
    still showing the same picture one blank later, and here it need not be: off a GEMDOS drive the
    rest of the boot — 117 KB of sprite bank, the directory fix-up, the per-game reset and
    `enter_title`'s `set_palette_black` — can pass in less than one vertical blank. MEASURED: one run
    in three came back with a single colour, a black screen, from exactly that.

    So the trigger shoots AT ONCE and arms the settled shot, and the caller scores both: a torn
    capture loses to the settled one, and a program that ran ahead loses to the immediate one.

    A THIRD SHOT ONE BLANK FURTHER WAS TRIED AND BOUGHT NOTHING (measured 2026-09-08, during the
    performance campaign; `../STATUS.md`, "On-target performance"). This check comes back black about
    one run in three, and the shots agree on THAT outcome every time — all 15/15 or all 1/15 — so a
    black run is not a frame the shifter had yet to latch but a breakpoint that fired in the wrong
    place, and no number of extra blanks addresses it. The third shot was removed again rather than
    left in as insurance against a mechanism that had been ruled out. The two above stay: on a green
    run they have been measured at 14 and 15, which is the torn frame the second one is for.
    """
    for shot in shots:
        shot.unlink(missing_ok=True)
    settled = action_file(work, "shoot_settled.txt", f"screenshot {shots[1]}")
    immediate = action_file(work, "shoot_title.txt", f"screenshot {shots[0]}",
                            f"b VBL > VBL :once :quiet {settled}")
    session.arm(f"b (${image_base + A_LEVEL0_ASSETS_LOADED:x}).b = ${TITLE_READY_FLAG:x} "
                f":once :quiet {immediate}")


def anchor_clause(session, work, dump, address, value, name):
    """Arm a breakpoint on a WORD in memory reaching a value, whose action dumps the whole of RAM.

    The whole megabyte rather than the framebuffer alone, because WHERE the framebuffer is is a
    longword inside the run's own image that this driver has to read first — and reading it needs a
    dump. One `savebin` answers both.
    """
    dump.unlink(missing_ok=True)
    clause = action_file(work, name, f"savebin {dump} 0 {ST_RAM_BYTES:#x}")
    session.arm(f"b (${address:x}).w = ${value:x} :once :quiet {clause}")


def frame_at(ram, image_base, pointer_address, translate):
    """The 32,000 bytes of the framebuffer a screen pointer names, and the addresses on the way.

    `translate` is what separates the two shores: the reconstruction's pointers are IMAGE addresses
    and the machine address is `image_base + pointer`; the original's are machine addresses already,
    because for it the image IS the machine.
    """
    pointer = struct.unpack_from(">I", ram, image_base + pointer_address)[0]
    machine = image_base + pointer if translate else pointer
    return ram[machine:machine + SCREEN_BYTES], pointer, machine


def image_base_from_ram(ram):
    """The shim's image base, found in RAM by the record's own magic rather than by a file.

    THE SAME WAY FOR EVERY RUN, and an earlier draft had the GEMDOS run read a file the program
    wrote instead. That was wrong twice over: a FLOPPY run cannot use it (Hatari 2.6.1 does not
    write a modified `.ST` back to the host on a `--run-vbls` exit — docs/on-target-execution.md,
    "The observable surfaces"), and a PLAY build writes no files at all, so a driver pointed at one
    waits out its whole deadline on a program that is running perfectly. What is readable in every
    case is the machine: `flyshark_main` fills the record's first fields — magic, field count, image
    base — before it does anything else, in every build.

    NOT `locate_by_signature`, which is how the ORIGINAL is found: that searches for a run of TEXT
    no relocation touches, and this .PRG's is 44 bytes of the ZERO PADDING mkprg.py adds to reach
    `_bss_start` (measured: it matches at 0x200 and everywhere else zeroes run). A magic that the
    program itself wrote is exact, and its uniqueness is asserted rather than assumed.
    """
    found = record_in_ram(ram)
    return found[1] if found else None


def record_in_ram(ram):
    """WHERE THE RECORD IS and what image base it names, as (machine address, image base).

    `image_base_from_ram` above wants only the second; `profile.py` wants the FIRST as well, because
    the record's address is how a relocated program is placed: `g_record`'s link-time offset is in
    the ELF, so `address - offset` is the text base every symbol and every breakpoint is measured
    from. One scan answers both, and neither caller writes a second one.
    """
    magic = struct.pack(">I", RECORD_MAGIC)
    found = []
    at = ram.find(magic)
    while at >= 0:
        # THE MAGIC IS IN THE PROGRAM'S TEXT AS WELL AS IN ITS RECORD — it is an immediate in the
        # instruction that stores it (measured: two matches, one of them the `move.l #$46534b31`).
        # The record is the one whose next two fields are the field COUNT and a 256-ALIGNED base,
        # which is a test the instruction stream does not pass by accident.
        fields, base = struct.unpack_from(">II", ram, at + 4)
        if fields == len(RECORD_FIELDS) and base and base % IMAGE_ALIGN == 0:
            found.append((at, base))
        at = ram.find(magic, at + 1)
    if len(found) > 1:
        raise SystemExit(f"the record is at {len(found)} addresses in RAM "
                         f"({[hex(where) for where, _ in found]}) — something else in memory "
                         f"carries its magic AND its shape")
    return found[0] if found else None


def give_up(doing, started, deadline_seconds, log):
    """Stop, and say WHY — not just which file did not appear.

    A bare "the program never wrote X" is the wrong sentence three times over: it names a MECHANISM
    rather than the thing being waited for, it does not say whether the wait was 20 seconds or 900,
    and it leaves the reader to go and open a log that usually answers the question in its last
    line. This prints all three.
    """
    tail = "\n    ".join(Path(log).read_text(errors="replace").splitlines()[-LOG_TAIL_LINES:])
    raise SystemExit(
        f"GAVE UP waiting for {doing}\n"
        f"  after {time.monotonic() - started:.0f} s of a {deadline_seconds:.0f} s deadline\n"
        f"  the emulator was alive throughout; its log ends:\n    {tail}\n"
        f"  full log: {log}")


def keep_looking(session, look, doing, deadline_seconds, started=None, log=None,
                 poll_seconds=LOCATE_POLL_SECONDS):
    """Dump RAM and run `look` over it until it answers, or the deadline passes.

    NOT A FIXED PRE-ROLL. How long a program takes to reach its first instruction is the medium's
    business: a GEMDOS drive is a host directory and a floppy is an emulated 720 KB disc whose boot,
    AUTO scan and program load are seconds of emulated time that vary from run to run. A settle long
    enough for the slowest case wastes it on every other; a settle tuned to the fast case fails
    intermittently, which is worse than either (measured: the floppy arm found nothing at 30 s on one
    run in four).
    """
    began = time.monotonic()
    while True:
        answer = look(session.savebin("early.bin", 0, ST_RAM_BYTES))
        if answer is not None:
            print(f"  found {doing.split(' to ')[0]} after "
                  f"{time.monotonic() - (started or began):.0f} s")
            return answer
        if time.monotonic() - began >= deadline_seconds:
            if log is None:
                return None
            give_up(doing, started or began, deadline_seconds, log)
        session.require_alive(doing)
        session.wait(poll_seconds)


def read_record(path):
    """STATE.BIN as a name -> value mapping, refusing a record whose length is not this file's."""
    blob = path.read_bytes()
    values = struct.unpack(f">{len(blob) // 4}I", blob)
    if len(values) != len(RECORD_FIELDS):
        raise SystemExit(f"{path}: {len(values)} fields, smoke.py names {len(RECORD_FIELDS)} — "
                         f"flyshark_main.c's enum and RECORD_FIELDS have diverged")
    if values[1] != len(values):
        raise SystemExit(f"{path}: the record says it has {values[1]} fields and is {len(values)}")
    return dict(zip(RECORD_FIELDS, values))


def expected_boot_bytes(staged, drive):
    """What the boot's eight `Fread`s can actually deliver, file by file.

    NOT the sum of the record lengths, and the difference is a finding rather than a rounding: the
    game asks for a FIXED length per record — `A\\LEVEL1.MAP`'s record asks for 5,000 bytes — and
    the shipped file is 3,664, so GEMDOS answers with what the file holds. `load_file` has no error
    handling at all (../src/init.c), so a short read is simply a short read on both shores, and the
    number this build must produce is the sum of the MINIMA.
    """
    total = 0
    for record in BOOT_FILE_RECORDS:
        wanted = image_long(staged, record + FILE_REC_LEN)
        name = image_asciz(staged, record + FILE_REC_NAME)
        path = resolve_like_gemdos(drive, name)
        if path is None:
            raise SystemExit(f"{drive} has no {name} — it does not carry what the boot loads")
        total += min(wanted, path.stat().st_size)
    return total


def resolve_like_gemdos(drive, dos_path):
    """The host file a `A\\NAME.EXT` record names, matched the way GEMDOS matches it: without case.

    The records spell `A\\SPRITES.cru` and the file on the drive is `A/SPRITES.CRU`. GEMDOS does not
    care and neither does the emulated run; a host filesystem that does would fail this check over a
    disc that boots perfectly, which is a driver bug rather than a finding.
    """
    here = drive
    for part in dos_path.split("\\"):
        match = [entry for entry in here.iterdir() if entry.name.lower() == part.lower()]
        if not match:
            return None
        here = match[0]
    return here if here.is_file() else None


def image_asciz(blob, address):
    end = blob.index(b"\0", address - LOAD_BASE)
    return blob[address - LOAD_BASE:end].decode("ascii")


def image_word(blob, address):
    return struct.unpack_from(">H", blob, address - LOAD_BASE)[0]


def image_long(blob, address):
    return struct.unpack_from(">I", blob, address - LOAD_BASE)[0]


def ring_pointers():
    """`boot_init`'s own arithmetic at the Physbase this build chooses — test/abi.py's numbers."""
    base = (TARGET_PHYSBASE - SCREEN_RING_BYTES + SCREEN_RING_ALIGN) & ~(SCREEN_RING_ALIGN - 1)
    return base, [base + offset for offset in RING_OFFSETS]


def fopen_names(trace_path):
    """The files a run opened, in order, with the shim's own three left out."""
    names = []
    for line in trace_path.read_text(errors="replace").splitlines():
        if TRACE_FOPEN not in line:
            continue
        name = line.split(TRACE_FOPEN, 1)[1].split('"')[1]
        if name.split("\\")[-1] in SHIM_ONLY_FILES:
            continue
        names.append(name)
    return names


def run_reconstruction(out_dir):
    """Boot ours, watch the title, press a key, anchor the framebuffer, collect the record."""
    out = out_dir / "ours"
    out.mkdir(parents=True, exist_ok=True)
    for stale in (BEACON, STATE_RECORD):
        stale.unlink(missing_ok=True)
    log, trace = out / "hatari.log", out / "os.trace"
    trace.unlink(missing_ok=True)
    session = HeadlessSession(hatari_arguments(gemdos_drive(OURS_DRIVE), trace), log_path=log,
                              fifo_path=out / "hatari.fifo", work_dir=out / "work")
    result = {"log": log, "trace": trace, "out": out}
    try:
        # THE BEACON FIRST, and only then one RAM dump. Waiting on the file is what makes the dump
        # land inside the title's window; the dump is what says where the image is.
        if await_file(session, BEACON, "the program's beacon", BEACON_DEADLINE_SECONDS) is None:
            give_up(f"{BEACON.name}, which a smoke build writes as its first act",
                    session.started, BEACON_DEADLINE_SECONDS, log)
        # THE BASE COMES OUT OF THE BEACON AND THE BREAKPOINT IS ARMED AT ONCE. Nothing between the
        # file appearing and the `arm` below costs the emulated machine anything it could spend on
        # the title's window.
        result["image_base"] = struct.unpack(">I", BEACON.read_bytes()[:BEACON_BYTES])[0]
        shots = (out / "title.png", out / "title_settled.png")
        arm_title_capture(session, out / "work", shots, result["image_base"])

        # ...and only THEN the checks that need a dump. Whether the arming was in time is still
        # asked — a capture taken after the picture is a wrong answer, not a slow one — but it is
        # asked of a ONE-BYTE read rather than of a megabyte, and after the breakpoint is standing.
        if session.savebin("late.bin", result["image_base"] + A_LEVEL0_ASSETS_LOADED,
                           1)[0] == TITLE_READY_FLAG:
            give_up(f"the program, EARLY ENOUGH: `level0_assets_loaded` was already set "
                    f"{time.monotonic() - session.started:.0f} s after power-on, which means the "
                    f"title picture had already been drawn when the breakpoint was armed. It would "
                    f"fire on whatever is on screen, so the capture is refused rather than taken",
                    session.started, LOCATE_DEADLINE_SECONDS, log)
        for shot in shots:
            if await_file(session, shot, f"the title picture ({shot.name})",
                          TITLE_DEADLINE_SECONDS) is None:
                give_up(f"{shot.name} — the title picture's own moment (`level0_assets_loaded`, "
                        f"one statement before the sprite bank overwrites the picture)",
                        session.started, TITLE_DEADLINE_SECONDS, log)
        wanted = palette_colours(title_palette(TITLE_NEO.read_bytes()))
        scored = sorted(((len(wanted & st_colours(shot)), shot.name, shot) for shot in shots),
                        reverse=True)
        result.update(title=scored[0][2], title_matched=scored[0][0], title_wanted=len(wanted),
                      title_scores=[(name, score) for score, name, _ in scored])

        # THE ACIA PATH, which nothing else here can reach: two real keys, in this order for a
        # reason. The WATCHED one goes first, with a breakpoint armed on the byte its bit lives in,
        # so that "a key moved a bit" is observed WHILE IT IS HELD — the make sets the bit and the
        # break clears it again, so a record read afterwards would show nothing either way. The
        # UNWATCHED one goes last, so that the byte the handler filed last is a scancode this file
        # knows exactly, and `key_bits` is back to zero with both keys released.
        result["key_bit_marker"] = out / "key_bit.bin"
        result["key_bit_marker"].unlink(missing_ok=True)
        moved = action_file(out / "work", "key_bit.txt",
                            f"savebin {result['key_bit_marker']} "
                            f"${result['image_base'] + A_KEY_BITS:x} 1")
        session.arm(f"b (${result['image_base'] + A_KEY_BITS:x}).b = ${WATCHED_KEY_BIT:x} "
                    f":once :quiet {moved}")
        session.key(WATCHED_KEY_MAKE)
        session.key(PROBE_KEY_MAKE)

        result["ram"] = out / "anchor.bin"
        anchor_clause(session, out / "work", result["ram"],
                      result["image_base"] + A_SCROLL_POS, ANCHOR_SCROLL_POS, "anchor.txt")
        result["anchored"] = await_file(session, result["ram"], "the framebuffer anchor",
                                        ANCHOR_DEADLINE_SECONDS) is not None
        # The attract screen as it is at the anchor, for a reader: taken WHILE the program still
        # owns the machine, because after the teardown the desktop owns it and the capture is TOS's.
        result["attract"] = session.screenshot(out / "attract.png")
        result["record_written"] = await_file(session, STATE_RECORD, "the run's record",
                                              RECORD_DEADLINE_SECONDS) is not None
        if not result["record_written"]:
            give_up(f"{STATE_RECORD.name}, which this build writes at its teardown",
                    session.started, RECORD_DEADLINE_SECONDS, log)
    finally:
        result["status"] = session.close()
    strip_log_noise(log)
    result["faults"] = log_faults(log)
    return result


def run_original(out_dir):
    """Boot the 1988 binary through the same recipe and anchor it at the same scroll position."""
    out = out_dir / "original"
    out.mkdir(parents=True, exist_ok=True)
    log, trace = out / "hatari.log", out / "os.trace"
    trace.unlink(missing_ok=True)
    session = HeadlessSession(hatari_arguments(gemdos_drive(ORIGINAL_DRIVE), trace), log_path=log,
                              fifo_path=out / "hatari.fifo", work_dir=out / "work")
    result = {"log": log, "trace": trace, "out": out}
    try:
        # WHERE IT LOADED is not knowable in advance and is not assumed: the program's own first
        # bytes are looked for in RAM (`locate_by_signature`), which is ../tools/boot_shots.py's
        # method and the same one that measured the 0xaa56 README.md's budget section quotes.
        session.wait(ORIGINAL_SETTLE_SECONDS)
        text = keep_looking(session, lambda ram: locate_by_signature(ram, ORIGINAL_PRG),
                            "the original's TEXT to appear in RAM", LOCATE_DEADLINE_SECONDS,
                            started=session.started, log=log)
        result["text_base"] = text
        result["image_base"] = text - LOAD_BASE

        result["ram"] = out / "anchor.bin"
        anchor_clause(session, out / "work", result["ram"],
                      result["image_base"] + A_SCROLL_POS, ANCHOR_SCROLL_POS, "anchor.txt")
        result["anchored"] = await_file(session, result["ram"], "the framebuffer anchor",
                                        ANCHOR_DEADLINE_SECONDS) is not None
    finally:
        result["status"] = session.close()
    strip_log_noise(log)
    result["faults"] = log_faults(log)
    return result


def run_floppy(out_dir):
    """Boot the .ST the way a person will: drive A:, no hard disk, TOS's own AUTO scan.

    THE GATE IS THE ANCHOR FIRING. Reaching `scroll_pos == ANCHOR_SCROLL_POS` from a floppy means
    the volume mounted, TOS found `AUTO\\FLYSHARK.PRG`, the program staged its image off the disc,
    the boot loaded all eight files through the same GEMDOS calls, and the attract screen drew 120
    frames. The frame it dumps there is then compared with the ORIGINAL's, exactly as the GEMDOS
    run's is — so the floppy is not merely alive, it is drawing the same pixels.
    """
    out = out_dir / "floppy"
    out.mkdir(parents=True, exist_ok=True)
    log, trace = out / "hatari.log", out / "os.trace"
    trace.unlink(missing_ok=True)
    session = HeadlessSession(hatari_arguments(("--disk-a", str(FLOPPY)), trace), log_path=log,
                              fifo_path=out / "hatari.fifo", work_dir=out / "work")
    result = {"log": log, "trace": trace, "out": out}
    try:
        session.wait(FLOPPY_SETTLE_SECONDS)
        result["image_base"] = keep_looking(session, image_base_from_ram,
                                            "the floppy to mount and TOS to run its AUTO program",
                                            LOCATE_DEADLINE_SECONDS, started=session.started,
                                            log=log)

        result["ram"] = out / "anchor.bin"
        anchor_clause(session, out / "work", result["ram"],
                      result["image_base"] + A_SCROLL_POS, ANCHOR_SCROLL_POS, "anchor.txt")
        result["anchored"] = await_file(session, result["ram"], "the framebuffer anchor",
                                        ANCHOR_DEADLINE_SECONDS) is not None
        result["attract"] = session.screenshot(out / "attract.png")
    finally:
        result["status"] = session.close()
    strip_log_noise(log)
    result["faults"] = log_faults(log)
    return result


def check_the_floppy(fail, floppy, original):
    print("\n-- the floppy: the volume a person puts in a drive -------------------------------")
    print(f"  {FLOPPY} ({FLOPPY.stat().st_size} B), booted as A: with no hard disk")
    print(f"  image base {floppy['image_base']:#x}, out of the record's own magic in RAM")
    print(f"  {floppy['attract'].name}: {distinct_colours(floppy['attract'])} distinct colours "
          f"({floppy['attract']})")
    # The emulator's own verdict on this run is `check_the_runs_finished`'s, which lists every run
    # the invocation made — including the anchor firing, which for a floppy IS the boot: reaching
    # attract frame 120 means the volume mounted, TOS ran the AUTO program, the image was staged off
    # the disc and all eight files loaded through it.
    if not floppy["anchored"]:
        return
    compare_the_frame(fail, "floppy", floppy, original)


def require_a_build_that_can_answer(prg, floppy_only):
    """Refuse a .PRG that cannot produce what this invocation is about to wait for.

    `build.sh` with no argument builds the PLAY program, which writes no files anywhere — that is
    the whole point of it — and the full smoke needs the record. An earlier draft checked only that
    a .PRG existed and then waited out its deadline on a program that was running perfectly, with a
    Hatari log that held nothing but its own banner (because a driver waiting on a file sends the
    debugger no commands, so there is nothing for the emulator to log). This is one `read_bytes` and
    it turns three minutes and a misleading sentence into a line naming the command to run.

    THE TEST IS THE RECORD'S OWN FILENAME, which the linker keeps only when `write_file` is
    compiled in. Not a version stamp, not a size: the string is there exactly when the behaviour is.
    """
    if floppy_only:
        return                      # judges the FRAME; needs no file from the program at all
    if RECORD_FILENAME.encode() in Path(prg).read_bytes():
        return
    raise SystemExit(
        f"{prg} is a PLAY build: it writes no files, so the record this run needs can never appear.\n"
        f"  build the smoke program first:   bash atari/build.sh smoke\n"
        f"  ...or judge the play build's frame instead:   python3 atari/smoke.py --floppy-only")


def check_the_mirrors(fail):
    """Every constant this file mirrors, read out of the file that owns it and compared.

    Run FIRST and before any emulator starts, because a mirror that has drifted makes every later
    check a statement about the wrong address — a breakpoint that never fires, a palette compared
    against the wrong table — and none of them would say why.
    """
    print("-- the mirrored constants -------------------------------------------------------")
    for name, path, spelling in MIRRORS:
        pattern = ASSIGNMENT_PATTERN if path.suffix == ".py" else DEFINE_PATTERN
        found = re.search(pattern % re.escape(spelling), path.read_text(), re.MULTILINE)
        if not found:
            fail.check(False, f"{spelling} is not in {path.name} — this file mirrors a constant "
                              f"that no longer exists there")
            continue
        theirs = int(found.group(1), 0)
        fail.check(globals()[name] == theirs,
                   f"{name} = {globals()[name]:#x} is {path.name}'s {spelling} ({theirs:#x})")


def check_the_runs_finished(fail, runs):
    """The emulator's own verdict on each run: its return code and the lines it printed.

    A surface that can be present and VACUOUS (docs/on-target-execution.md: a log parser that read
    the wrong stream reported nothing for a year), so the numbers are printed whether they pass or
    not, and every run this invocation made is listed rather than a fixed pair.
    """
    print("\n-- exit status and the log ------------------------------------------------------")
    for side, run in runs:
        print(f"  {side}: Hatari exit {run['status']}, log {run['log']}")
        fail.check(not run["faults"], f"{side}: no fault lines in the log ({run['faults']})")
        fail.check(run["status"] == 0, f"{side}: Hatari exited cleanly ({run['status']})")
        fail.check(run["anchored"], f"{side}: the framebuffer anchor fired")
        if "record_written" in run:
            fail.check(run["record_written"], f"{side}: the run wrote its record and tore down")


def check_the_picture(fail, ours):
    print("\n-- rendered pixels --------------------------------------------------------------")
    print(f"  {ours['title'].name}: {ours['title_matched']}/{ours['title_wanted']} of "
          f"{TITLE_NEO.name}'s palette on screen, {distinct_colours(ours['title'])} distinct "
          f"colours  ({ours['title']})")
    print(f"  both captures scored {ours['title_scores']} — the better one is the picture, and the "
          f"other is a torn frame or a program that ran on (`arm_title_capture` says why there are "
          f"two, and why a third was tried and removed)")
    print(f"  {ours['attract'].name}: {distinct_colours(ours['attract'])} distinct colours "
          f"({ours['attract']})")
    fail.check(ours["title_matched"] == ours["title_wanted"],
               "the title picture was drawn: every colour of its own palette on screen at once")


def check_the_record(fail, record, staged):
    print("\n-- the record, the memory budget and the hardware-state vector -------------------")
    base, ring = ring_pointers()
    tail_bytes = base - PROGRAM_END
    print(f"  image base {record['IMAGE_BASE']:#x}, {record['IMAGE_BYTES']} bytes, "
          f"program staged {record['PROGRAM_STAGED_BYTES']} B")
    print(f"  TPA [{record['TPA_LOW']:#x}, {record['TPA_HIGH']:#x}), program ends "
          f"{record['PROGRAM_TOP']:#x}, headroom {record['HEADROOM']} B")
    print(f"  Physbase wanted {record['PHYSBASE_WANTED']:#x}, read back "
          f"{record['PHYSBASE_AT_BOOT']:#x}, shifter {record['RAW_VIDEO_BASE_AT_BOOT']:#x}")
    print(f"  ring {record['SCREEN_RING_BASE']:#x} -> "
          + " ".join(f"{record[f'SCREEN_RING_{slot}']:#x}" for slot in range(len(ring))))
    print(f"  files {record['FILE_OPENS']} opened, {record['FILE_BYTES_READ']} B read, "
          f"{record['FILE_OPEN_FAILURES']} failures, {record['FILE_REFUSALS']} refusals")
    print(f"  OS calls: Setscreen {record['SETSCREEN_CALLS']}, Setpalette "
          f"{record['SETPALETTE_CALLS']}, Vsync {record['VSYNC_CALLS']}, IKBD "
          f"{record['IKBD_COMMANDS']}")
    print(f"  hardware: {record['HW_WRITES']} stores, {record['HW_RMW']} read-modify-writes, "
          f"{record['HW_READS']} reads; PSG {record['PSG_WRITES']} writes, "
          f"{record['PSG_REFUSED']} refused")
    print(f"  interrupts: {record['VBL_ENTRIES']} vertical blanks, {record['ACIA_ENTRIES']} ACIA "
          f"(+{record['ACIA_JOY0_ENTRIES']}/{record['ACIA_JOY1_ENTRIES']} joystick continuations)")

    fail.check(record["MAGIC"] == RECORD_MAGIC and record["TAIL"] == RECORD_TAIL,
               "the record is whole: its magic and its 'DONE' tail are both there")
    fail.check(record["IMAGE_BASE"] % IMAGE_ALIGN == 0,
               f"the image base is {IMAGE_ALIGN}-byte aligned, so every screen address in it can be "
               f"(is {record['IMAGE_BASE']:#x})")
    # THE CLASS-8 CHECK (docs/on-target-execution.md): an address the shifter's two-byte register
    # truncated reads back different from what was handed to Setscreen.
    fail.check(record["PHYSBASE_AT_BOOT"] == record["PHYSBASE_WANTED"]
               == record["RAW_VIDEO_BASE_AT_BOOT"],
               "the shifter took the screen address it was given, untruncated")
    fail.check(record["PHYSBASE_WANTED"] == record["IMAGE_BASE"] + TARGET_PHYSBASE,
               "the screen is at the image Physbase shim_include/init.h answers with")
    fail.check(record["SCREEN_RING_BASE"] == base
               and [record[f"SCREEN_RING_{slot}"] for slot in range(len(ring))] == ring,
               f"boot_init derived the verified ring pointers ({base:#x} + "
               f"{'/'.join(hex(offset) for offset in RING_OFFSETS)})")
    # NOT `> 0`: the headroom IS the run's stack, and a program whose bss reaches the stack pointer
    # has already been overwritten by the time a zero could be reported. The floor is what this run
    # actually needs — interrupt frames on top of the C stack — with room to see a change coming.
    fail.check(record["HEADROOM"] >= STACK_FLOOR_BYTES,
               f"the program leaves the stack {record['HEADROOM']} B, at least the "
               f"{STACK_FLOOR_BYTES} B floor")
    fail.check(record["IMAGE_TAIL_DIRTY"] == 0,
               f"nothing wrote into the {tail_bytes} B between the program and the screen ring")
    fail.check(record["IMAGE_GUARD_CHANGED"] == 0,
               "nothing wrote past the top of the image into the guard band")

    wanted_bytes = expected_boot_bytes(staged, OURS_DRIVE)
    fail.check(record["FILE_OPENS"] == len(BOOT_FILE_RECORDS)
               and record["FILE_BYTES_READ"] == wanted_bytes,
               f"the boot loaded its {len(BOOT_FILE_RECORDS)} files whole "
               f"({wanted_bytes} B — what the records ask for, or the file, whichever is less)")
    fail.check(record["FILE_OPEN_FAILURES"] == 0 and record["FILE_REFUSALS"] == 0,
               "no open failed and the image bound refused nothing")
    fail.check(record["FATAL"] == 0,
               f"no interrupt named a handler the dispatch table does not know "
               f"(vector {record['FATAL_VECTOR']:#x}, handler {record['FATAL_HANDLER']:#x})")
    fail.check(record["IKBD_COMMANDS"] == 1,
               "the one IKBD command the boot sends ($14, report joystick events) went out")
    # EVERY PSG WRITE IS A PAIR OF STORES — the register-select latch and the data port
    # (shim_include/psg.h) — so this equality says the chip was driven through the seam and not
    # through some other path, and that no store went missing on the way.
    fail.check(record["HW_WRITES"] == 2 * record["PSG_WRITES"] and record["PSG_REFUSED"] == 0,
               f"every hardware store was one half of a PSG register write "
               f"({record['HW_WRITES']} = 2 x {record['PSG_WRITES']})")
    fail.check(record["VBL_ENTRIES"] == record["VBL_TICKS"] > 0,
               "the vertical blank ran and every entry reached the verified handler")
    fail.check(record["SUPER_TOKEN"] == OS_SUPER_TOKEN,
               f"`boot_init` took supervisor mode and stored the answer it was given "
               f"({record['SUPER_TOKEN']:#x})")
    fail.check(record["LEVEL0_ASSETS_LOADED"] == SCC_TRUE,
               "the boot chain recorded that level 0's assets are in memory")
    # `Vsync` is AT MOST one a frame, and it is the arm `render_frame`'s pacer takes when the frame
    # was already over its three-blank budget. A bound rather than an equality because the port is no
    # longer always late: at 4.56 blanks a frame one frame in the 200 comes in UNDER budget and takes
    # the spin arm instead, so the run measures 199 (`../STATUS.md`, "On-target performance").
    attract_passes, spare = divmod(record["SETPALETTE_CALLS"]
                                   - SETPALETTE_CALLS_BEFORE_THE_ATTRACT_SPIN,
                                   SETPALETTE_CALLS_PER_ATTRACT_PASS)
    fail.check(spare == 0 and attract_passes >= 1
               and record["VSYNC_CALLS"] <= record["ATTRACT_FRAMES"],
               f"the palette was installed {record['SETPALETTE_CALLS']} times = "
               f"{SETPALETTE_CALLS_BEFORE_THE_ATTRACT_SPIN} + "
               f"{SETPALETTE_CALLS_PER_ATTRACT_PASS} x {attract_passes} attract passes, as the flow "
               f"says, and the pacer waited at most once a frame ({record['VSYNC_CALLS']})")

    print(f"  teardown: $70 {record['VBL_VECTOR_AFTER']:#x}, $118 "
          f"{record['ACIA_VECTOR_AFTER']:#x}, joyvec {record['JOYVEC_AFTER']:#x}, Physbase "
          f"{record['PHYSBASE_AFTER']:#x}, rez {record['REZ_AFTER']}")
    fail.check(record["VBL_VECTOR_AFTER"] == record["VBL_CHAIN"],
               "the $70 vector was handed back to the TOS handler the boot chained to")
    # NOT A TAUTOLOGY: the shim restores the joyvec from ITS OWN reading of TOS's struct, taken
    # before any core ran, and `TOS_JOYVEC_SAVED` is the copy `boot_init` made through
    # `image + fs_kbdvbase() + 0x18`. They are equal only if that seam really landed on TOS's struct.
    fail.check(record["JOYVEC_AFTER"] == record["TOS_JOYVEC_SAVED"] != 0,
               "TOS's joystick callback was handed back, and the core saved the same pointer the "
               "shim read — which is `fs_kbdvbase()` landing where it says")
    fail.check(record["PHYSBASE_AFTER"] not in (0, record["PHYSBASE_WANTED"]),
               f"the screen was handed back to TOS's own ({record['PHYSBASE_AFTER']:#x})")
    # $118 IS TAKEN OUTRIGHT — no chain — so its before-value is the shim's own reading, and a
    # vector left pointing into the freed TPA is the class-7 halt a second after Pterm.
    fail.check(record["ACIA_VECTOR_AFTER"] == record["ACIA_VECTOR_BEFORE"] != 0
               and record["REZ_AFTER"] == record["REZ_BEFORE"],
               f"the $118 vector and the resolution were handed back as they were found "
               f"({record['ACIA_VECTOR_BEFORE']:#x}, rez {record['REZ_BEFORE']})")

    # THE PER-FRAME PUBLISH, which is the one class-8 read-back at an address that MOVES. The game
    # changes the physical screen base every frame and the harness's Setscreen event drops that
    # argument, so off target nothing at all watches it; here the shifter's own two bytes, the trap's
    # answer and the buffer the CORE named must be one address.
    # ...AND THE BUFFER IT NAMES IS `screen_prev1`, NOT `screen_draw`: `render_frame` publishes the
    # frame it has drawn and THEN rotates the ring, so between two frames the chip is fetching the
    # base that has just become the previous one. Comparing against `screen_draw` is off by exactly
    # one ring step (measured: 0x7d00, one frame).
    fail.check(record["RAW_VIDEO_BASE_AT_END"] == record["PHYSBASE_AT_END"]
               == record["IMAGE_BASE"] + record["SCREEN_PREV1_AT_END"],
               f"the frame the cores published is the frame the shifter is fetching "
               f"({record['PHYSBASE_AT_END']:#x} = image + screen_prev1 "
               f"{record['SCREEN_PREV1_AT_END']:#x})")
    fail.check(record["SETSCREEN_CALLS"] == record["ATTRACT_FRAMES"] + BOOT_SETSCREEN_CALLS,
               f"one Setscreen per drawn frame, plus the boot's {BOOT_SETSCREEN_CALLS} "
               f"({record['SETSCREEN_CALLS']})")
    fail.check(record["PSG_WRITES"] > 0 and record["ACIA_TICKS"] == record["ACIA_ENTRIES"],
               f"the chip was driven at all ({record['PSG_WRITES']} register writes) and every ACIA "
               f"interrupt reached a handler")
    fail.check(record["PROGRAM_STAGED_BYTES"] == STAGED_IMAGE.stat().st_size,
               f"the whole of {STAGED_IMAGE.name} was staged into the image "
               f"({record['PROGRAM_STAGED_BYTES']} B)")
    # THE INTERRUPT LEVEL THE RUN WAS AT, which nothing in this build sets: the original establishes
    # `move.w #$2300,sr` (supervisor, IPL 3) and the shim keeps whatever GEMDOS entered it with. That
    # the two agree is a measurement rather than a design, and it is worth a red on a TOS where they
    # do not: a lower IPL means the machine is taking interrupts the 1988 binary masked.
    fail.check((record["SR_AT_END"] & SR_SUPERVISOR) != 0
               and (record["SR_AT_END"] >> SR_IPL_SHIFT) & SR_IPL_MASK == ORIGINAL_IPL,
               f"the run is in supervisor mode at the interrupt level the original chooses "
               f"(SR {record['SR_AT_END']:#06x}, IPL {(record['SR_AT_END'] >> SR_IPL_SHIFT) & SR_IPL_MASK})")
    fail.check(record["ATTRACT_FRAMES"] == record["ATTRACT_FRAME_LIMIT"]
               > ANCHOR_SCROLL_POS // SCROLL_POS_PER_FRAME,
               f"the loop stopped at the frame limit the build was given "
               f"({record['ATTRACT_FRAME_LIMIT']}), which is past the framebuffer anchor")

    pens = [record[f"PEN{pen}"] for pen in range(PALETTE_PENS)]
    wanted_pens = [image_word(staged, A_PALETTE_GAME + pen * 2) for pen in range(PALETTE_PENS)]
    print(f"  pens at the end of the run {' '.join(f'{pen:03x}' for pen in pens)}")
    fail.check(pens == wanted_pens,
               "the sixteen colour registers hold the game palette out of the program's own table")
    fail.check(record["REZ_AT_END"] == 0, "the shifter is in low resolution")


def check_the_pacing(fail, record):
    print("\n-- timelines: what the run cost -------------------------------------------------")
    frames = record["ATTRACT_FRAMES"]
    vbls = record["VBL_TICKS"]
    per_frame = vbls / frames if frames else 0
    ticks = record["TICKS_AT_END"] - record["TICKS_AT_BOOT"]
    print(f"  {frames} attract frames in {vbls} vertical blanks = {per_frame:.2f} VBL/frame "
          f"= {VBL_HZ / per_frame:.2f} fps (the original's own pacer asks for "
          f"{VBLS_PER_FRAME_FLOOR}, i.e. {VBL_HZ / VBLS_PER_FRAME_FLOOR:.1f} fps)")
    print(f"  TOS's 200 Hz clock advanced {ticks} ticks = {ticks * 5 / 1000:.1f} s of machine time")
    fail.check(frames == SMOKE_ATTRACT_FRAMES,
               f"the build drew the {SMOKE_ATTRACT_FRAMES} attract frames it was asked for")
    fail.check(per_frame >= VBLS_PER_FRAME_FLOOR,
               "no frame was faster than the game's own three-vertical-blank pacer allows")
    fail.check(record["SCROLL_POS_AT_END"] == frames * SCROLL_POS_PER_FRAME,
               f"the scroll advanced exactly twice a frame ({record['SCROLL_POS_AT_END']})")


def check_the_input_path(fail, record, ram, image_base, marker):
    print("\n-- the ACIA seam: a real key through the reconstruction's own handler ------------")
    scancode = ram[image_base + A_KEY_LAST_SCANCODE]
    key_bits = ram[image_base + A_KEY_BITS]
    print(f"  {record['ACIA_ENTRIES']} ACIA interrupts, key_last_scancode {scancode:#04x}, "
          f"key_bits {key_bits:#04x}, {record['HW_RMW']} read-modify-writes (the handler's EOI)")
    fail.check(record["ACIA_ENTRIES"] >= 2,
               "the keyboard's make and break both reached `acia_ikbd_isr` through the real $118")
    fail.check(scancode == PROBE_KEY_BREAK,
               f"the handler filed the last byte the keyboard sent ({scancode:#04x} is "
               f"{PROBE_KEY_MAKE:#04x}'s break code)")
    fail.check(key_bits == 0,
               "the unwatched scancode moved none of the eight watched bits, and the watched one's "
               "own bit was cleared again by its break code")
    fail.check(record["HW_RMW"] >= record["ACIA_ENTRIES"],
               "every ACIA entry cleared its own MFP in-service bit with a real `bclr`")
    # THE POSITIVE CONTROL for the two checks above: a WATCHED scancode must move the bit the ladder
    # owns, caught by a breakpoint while the key is down. Without it, "no bit moved" would be just as
    # true of a handler whose eight comparisons never ran at all.
    fail.check(marker is not None and marker.read_bytes() == bytes([WATCHED_KEY_BIT]),
               f"a watched scancode ({WATCHED_KEY_MAKE:#04x}) set its own bit in `key_bits` while "
               f"it was held")


def check_the_trap_ledger(fail, ours, original):
    print("\n-- the trap ledger --------------------------------------------------------------")
    ours_names = fopen_names(ours["trace"])
    original_names = fopen_names(original["trace"])
    print(f"  ours:     {ours_names}")
    print(f"  original: {original_names}")
    fail.check(len(original_names) == len(BOOT_FILE_RECORDS),
               f"the trace was read at all: the original opened its {len(BOOT_FILE_RECORDS)} boot "
               f"files ({len(original_names)} Fopen lines parsed)")
    fail.check(ours_names == original_names,
               f"both runs opened the same {len(original_names)} files in the same order")


def compare_the_frame(fail, side, run, original):
    """One side's published frame against the original's at the same anchor, with its control.

    ONE FUNCTION FOR BOTH ARMS. The GEMDOS run and the floppy run ask exactly the same question, and
    an earlier draft asked it twice — the copy in the floppy arm had lost the length guard, which is
    what stops a slice that ran off the end of RAM reporting "0 differ" over nothing.
    """
    mine, mine_pointer, mine_machine = frame_at(run["ram"].read_bytes(), run["image_base"],
                                                A_SCREEN_DRAW, True)
    original_ram = original["ram"].read_bytes()
    theirs, their_pointer, their_machine = frame_at(original_ram, original["image_base"],
                                                    A_SCREEN_DRAW, False)
    print(f"  {side} screen_draw {mine_pointer:#x} (image) -> {mine_machine:#x} (machine); "
          f"original {their_pointer:#x} -> {their_machine:#x}")
    differing = sum(1 for a, b in zip(mine, theirs) if a != b)
    print(f"  {SCREEN_BYTES} bytes compared, {differing} differ")
    if not fail.check(len(mine) == len(theirs) == SCREEN_BYTES,
                      f"{side}: both framebuffers are a whole {SCREEN_BYTES}-byte frame"):
        return
    fail.check(differing == 0,
               f"{side}: the published frame is the ORIGINAL's, byte for byte")

    # THE CONTROL, and it costs no extra boot: the same comparison against the frame the original
    # published one `render_frame` EARLIER must fail. Without it a comparison that had silently
    # started reading zeroes on both sides would report the same green.
    before, _, before_machine = frame_at(original_ram, original["image_base"], A_SCREEN_PREV1, False)
    mis = sum(1 for a, b in zip(mine, before) if a != b)
    print(f"  control: against the original's PREVIOUS frame ({before_machine:#x}), {mis} differ")
    fail.check(mis > 0,
               f"{side}: the mis-anchored comparison diverges, so the green above is about this frame")


def check_the_framebuffer(fail, ours, original):
    print("\n-- memory: the published framebuffer, against the original's --------------------")
    print(f"  anchor: scroll_pos = {ANCHOR_SCROLL_POS:#x} = attract frame "
          f"{ANCHOR_SCROLL_POS // SCROLL_POS_PER_FRAME}; the original loaded at "
          f"{original['text_base']:#x}")
    compare_the_frame(fail, "ours", ours, original)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--keep-going", action="store_true",
                        help="report every failing surface instead of stopping at the first")
    parser.add_argument("--floppy", action="store_true",
                        help="also boot disk/FLYSHARK.ST as A: and compare ITS frame (one more "
                             "emulated boot; the volume carries whichever build.sh mode ran last)")
    parser.add_argument("--floppy-only", action="store_true",
                        help="the floppy and the original alone, skipping the GEMDOS-drive run and "
                             "its record — which is how a PLAY build is checked, since that build "
                             "deliberately writes no files")
    options = parser.parse_args()

    for needed in (OURS_PRG, STAGED_IMAGE):
        if not needed.is_file():
            raise SystemExit(f"{needed} is missing — run `bash atari/build.sh smoke` first")
    if not ORIGINAL_PRG.is_file():
        raise SystemExit(f"{ORIGINAL_PRG} is missing — run ../tools/unpack_dist.py first")
    require_gemdos_tos(TOS_ROM)
    require_a_build_that_can_answer(OURS_PRG, options.floppy_only)

    print(f"TOS {tos_label(require_gemdos_tos(TOS_ROM))}, {MEMSIZE_MB} MB, no --auto: TOS runs "
          f"AUTO\\{OURS_PRG.name} itself, before the desktop")
    print(f"  ours     {OURS_PRG} ({OURS_PRG.stat().st_size} B) on {OURS_DRIVE}")
    print(f"  original {ORIGINAL_PRG} ({ORIGINAL_PRG.stat().st_size} B) on {ORIGINAL_DRIVE}")

    fail = Failures(options.keep_going)
    check_the_mirrors(fail)
    ours = None if options.floppy_only else run_reconstruction(options.out)
    original = run_original(options.out)
    floppy = run_floppy(options.out) if options.floppy or options.floppy_only else None

    check_the_runs_finished(fail, [(side, run) for side, run in (("ours", ours),
                                                                 ("original", original),
                                                                 ("floppy", floppy))
                                   if run is not None])
    if ours is not None:
        check_the_picture(fail, ours)
        record = read_record(STATE_RECORD)
        # THE BEACON'S BASE AGAINST THE PROGRAM'S OWN. The GEMDOS run arms its title breakpoint on
        # the four bytes the beacon carried, before anything has read RAM (see BEACON above); this
        # is where that address is confirmed against the record the SAME run wrote at its teardown.
        # A beacon left over from another build would have put every capture on the wrong address,
        # and this is the check that would say so rather than the pictures being quietly wrong.
        fail.check(record["IMAGE_BASE"] == ours["image_base"],
                   f"the beacon named the image base the program's own record does "
                   f"({ours['image_base']:#x})")
        staged = STAGED_IMAGE.read_bytes()
        check_the_record(fail, record, staged)
        check_the_pacing(fail, record)
        check_the_input_path(fail, record, ours["ram"].read_bytes(), ours["image_base"],
                             ours["key_bit_marker"] if ours["key_bit_marker"].is_file() else None)
        check_the_trap_ledger(fail, ours, original)
        check_the_framebuffer(fail, ours, original)
    if floppy is not None:
        check_the_floppy(fail, floppy, original)

    print()
    if fail.found:
        raise SystemExit(f"FAILED on {len(fail.found)} surface(s):\n  "
                         + "\n  ".join(fail.found))
    print("smoke: every surface green")


if __name__ == "__main__":
    main()
