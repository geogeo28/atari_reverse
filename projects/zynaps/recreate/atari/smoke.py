#!/usr/bin/env python3
"""Judge ZYNAPS.PRG against the ORIGINAL binary, on named surfaces, headless.

    python3 atari/smoke.py title       # the M1 build: every surface must agree
    python3 atari/smoke.py titlefault  # its negative control: the verdict is INVERTED
    python3 atari/smoke.py floppy      # ...the same build, BOOTED FROM A FLOPPY, both sides
    python3 atari/smoke.py title --keep # leave the captures and traces in atari/out/
    python3 atari/smoke.py floppy --machine ste --tos-rom tools/hatari/TOS102US.img

Each build must exist — `atari/build.sh <mode>` writes `build/ZYNAPS-<mode>.PRG` and this reads it
from there, so the two never race over `disk/ZYNAPS.PRG`.

THE FLOPPY MODE IS THE SAME CHECKS ON THE MEDIUM THE REAL MACHINE USES. `title` and `titlefault`
boot both sides off a Hatari GEMDOS drive — a host directory, no FAT12, no FDC, no TOS floppy
driver. `floppy` boots OURS from `disk/ZYNAPS.ST` (atari/mkfloppy.py builds it) and the ORIGINAL
from its own `bin/zynaps.st`, so the desktop's AUTO scan, the FAT12 volume and TOS's floppy driver
are all in the run. Four things about it differ and `run_ours_from_floppy` says which.

THE SIX SURFACES, and each check below says which one it is. docs/on-target-execution.md's rule is
that every on-target change names the surface that would catch its failure, and the rule's teeth are
that a surface can be PRESENT AND VACUOUS — the sibling project's bus-error detector read stdout
while Hatari logs to stderr, and passed for a year. So this file reports which checks RAN as well as
which failed, and the negative control is what says the sensitive ones can go red.

  exit status + log        Hatari's return code and its own fault lines, plus a complete STATE.BIN
  trap ledger              --trace gemdos: our Fopen/Fread/Fclose sequence against the original's
  hardware-state vector    the sixteen pens, $ff8260 and the video base, read off the chip at the
                           anchor by the debugger AND read back by the program itself
  rendered pixels          a Hatari screenshot of ours against one of the original, byte for byte
  timelines                --trace psg_write, cut into the sound driver's own tick frames
  memory                   the 32000-byte framebuffer, ours against the original's

BOTH SIDES ARE RUN THE SAME WAY, on the same TOS, the same machine and the same memory size. That is
not free: this build needs `--memsize 4` for its 1 MiB image, and the original ships for a 512 KB
machine. Running the original at 4 MB too is what makes every comparison below about the PROGRAMS
rather than about two different machines — the game hard-codes its framebuffers at absolute RAM
(0x70300/0x78000) and TOS's TPA base does not move with the memory size, so the original behaves
identically; that is measured by this file's own `blank capture` and `same picture` guards rather
than assumed.
"""
import argparse
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]                      # projects/zynaps
REPO = PROJECT.parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(PROJECT / "tools"))

import st_extract                                                     # noqa: E402
import st_pixels                                                       # noqa: E402
sys.path.insert(0, str(HERE))
import mkfloppy                                                        # noqa: E402
from hatari_headless import (                                          # noqa: E402
    HATARI, POLL_SECONDS, PRG_HEADER_BYTES, HeadlessSession, action_file, distinct_colours,
    first_fixup_offset, locate_by_signature, log_faults, same_picture)
# The tick-frame cutter, borrowed rather than re-derived: `ref_capture.py` already parses Hatari's
# psg_write trace into the sound driver's own 10..0 flush frames, and re-spelling that here would be
# a second definition of what a frame IS (CLAUDE.md §5). Its TraceReader is incremental, which this
# does not need, but the alternative is a copy that can drift from the recorder's.
import ref_capture                                                     # noqa: E402

# --- the modes -----------------------------------------------------------------------------
FLOPPY_MODE = "floppy"
MODES = ("title", "titlefault", FLOPPY_MODE, "game", "gamefault")

# --- the machine -----------------------------------------------------------------------------
TOS_ROM = REPO / "tools" / "hatari" / "TOS104US.img"
# Plain ST is the default because it is the LOWER machine: an STE runs an ST program and not the
# other way about, so a build that is green here is green on more hardware than one green on `ste`.
# `--machine ste` is the run that asks the target hardware's own question (its shifter has a fourth
# bit a gun and a third video-base byte); the report prints the unmasked pens for it.
DEFAULT_MACHINE = "st"
# A TOS ROM's version is a big-endian word at offset 2 ($0104 for 1.04). Hatari REFUSES to emulate
# an STE on a ROM at or below this — "TOS versions <= 1.4 work only in ST mode and with a 68000
# CPU" — and silently drops back to ST, so a run asked for `ste` on such a ROM would report on a
# machine it was not asked about. `assert_machine_and_rom_agree` turns that into a refusal up front.
TOS_VERSION_OFFSET = 2
TOS_VERSION_BYTES = 2
LAST_ST_ONLY_TOS = 0x0104
# 4 MB, and both sides get it — see the module docstring. The reconstruction's image is a 1 MiB .bss
# array, which leaves a TOS 1.04 TPA on a 1 MB machine no room for the program plus its stack.
MEMSIZE_MB = 4
# Hatari quits by itself at this count, so a hung run cannot sit there for ever — and, as the docs
# put it, letting the emulator run PAST the program's exit is what catches a handler left hooked
# into memory GEMDOS has taken back. 50 Hz => ~240 s.
RUN_VBLS = 12000

ST_RAM_BYTES = 0x400000
RAM_DUMP_NAME = "ram.bin"

# --- what is compared ---------------------------------------------------------------------------
SCREEN_BYTES = 32000                # a 320x200 four-plane ST frame — ../include/video.h's constant
SCREEN_PIXELS_WIDE = 320
SCREEN_ROWS = 200
PALETTE_PENS = 16
PEN_BYTES = 2
PEN_MASK = 0x777                    # three bits a gun; the fourth reads back as bus noise
HW_PALETTE_BASE = 0xFF8240
HW_SHIFTER_RESOLUTION = 0xFF8260
HW_SHIFTER_BASE_HIGH = 0xFF8201
HW_SHIFTER_BASE_MID = 0xFF8203
RESOLUTION_MASK = 0x03
REZ_LOW = 0                         # `andi.b #$fc,$ff8260` clears both bits: ST low resolution

# The game's own hard-coded framebuffers (../src/init.c's BOOT_SCREEN_*). The ORIGINAL displays
# `screen_back` after the boot's one flip, which is 0x70300 at an ABSOLUTE address because the game
# never asks XBIOS for a screen; OURS displays image_base + that offset.
GAME_SCREEN_BACK = 0x70300
GAME_SCREEN_FRONT = 0x78000

# `andi.b #$fc,$ff8260` — ../include/init.h's SHIFTER_MODE_RESOLUTION_MASK, which is what the core's
# own sink records having asked for.
SHIFTER_MODE_MASK = 0xFC
# What TOS booted this machine in, and therefore what the teardown must give back. TOS 1.04 under
# `--monitor rgb` comes up in ST LOW — which is also why `$ff8260` reading 0 at the anchor says
# nothing about our own write, and why the core's write COUNT is what carries that.
TOS_BOOT_REZ = 0

# `movem.l #$00ff,$ff8240.l` — ../include/video.h's SHIFTER_PALETTE_PAIRS: the eight LONGWORDS one
# whole colour row goes up as, which is also the width that tells the core's upload apart from the
# shim's word-wide pen writes (shim_include/hw.h's `zy_note_store` keys `palette_long_writes` on it).
SHIFTER_PALETTE_PAIRS = 8

# EVERY HARDWARE STORE OF THE RUN, PREDICTED EXACTLY rather than merely being non-zero. The three
# terms are three different owners, and keeping them apart is what makes a wrong total readable.
#
# The two IKBD commands `_start` sends at 0x1001c and 0x10024 ($12 mouse off, $15 joystick
# interrogation), one `move.b d0,$fffc02` each. They are `ikbd_send_cmd`'s whole store side, and the
# per-command running totals asserted further down are the same two bytes counted at the same door.
IKBD_BOOT_COMMANDS = 2
# A CALL AT THE VIDEO-BASE DOOR IS TWO STORES, and that is M2's change to this arithmetic. The
# shifter's base is a 24-bit address published as two bytes, `offset >> 8` and `offset >> 16`, and
# the door has to translate the WHOLE offset to a machine address — a byte of a sum is not the sum of
# a byte, because `image base + offset` carries out of bits 8-15 into 16-23. So each of the core's
# two calls updates its half of the remembered offset and stores BOTH translated bytes.
VIDEO_BASE_STORES_PER_CALL = 2
# EVERY OTHER STORE THE CORES MAKE, and all of them are inside `boot_load_title_assets`:
# `andi.b #$fc,$ff8260` (0x10056), the two video-base calls at the tail of `screen_flip_buffers`
# (0x1297a) and the eight palette longwords of `set_palette_title` (0x153ae). They used to be sinks
# the shim replayed; the kit's write ledger made them real stores, and on target shim_include/hw.h is
# what they land through.
CORE_VIDEO_BASE_CALLS = 2
CORE_HW_WRITES = (IKBD_BOOT_COMMANDS + 1
                  + CORE_VIDEO_BASE_CALLS * VIDEO_BASE_STORES_PER_CALL + SHIFTER_PALETTE_PAIRS)
# The SHIM's own, and there is now exactly one of them: `publish_screen_base`'s two calls at the same
# door, which re-publish the FRONT buffer so that `published_screen_base` has something the register
# read-back can be compared against. The teardown's sixteen pens, its four PSG registers and its
# three MFP restores are NOT here — the record is written at the anchor, before the hand-back, so
# nothing the teardown stores is in any of these counts.
# ...and it is its OWN count, not the cores' reused: `publish_screen_base` makes two calls because
# the shifter's base is two bytes, and `screen_flip_buffers` makes two for the same reason — the two
# 2s are the same fact about the register but they are counted at different call sites, and tying
# them together would move both when only one had changed.
SHIM_VIDEO_BASE_CALLS = 2
SHIM_HW_WRITES = SHIM_VIDEO_BASE_CALLS * VIDEO_BASE_STORES_PER_CALL
# ...and the control's injected pen, which is one word-wide store and nothing else.
FAULT_HW_WRITES = 1
# Each PSG register write is two port stores, the select latch then the data port.
PSG_PORTS_PER_WRITE = 2
# NOTHING OF THE SHIM'S GOES THROUGH THAT SEAM. `stage_program_image` and `write_file` call the trap
# wrappers (`Fopen`/`Fcreate`) directly, not the cores' `os_fopen`, so the counter sees the GAME's
# opens and only those — which is what makes it a statement about `boot_load_title_assets` rather
# than about the shim's own bookkeeping.

# The boot palette the original uploads at 0x10084 (`set_palette_title` @ 0x153ae reading
# ../include/video.h's `A_palette_boot`), read out of the STAGED PROGRAM IMAGE rather than typed:
# gen_image.py has already relocated the shipped .PRG, so this is the original binary's own data.
# Its LAST pen is what anchors the original's run — see `original_anchor_condition`.
PALETTE_BOOT_ADDRESS = 0x19618
PROGRAM_IMAGE = "ZYNAPS.IMG"
LOAD_BASE = 0x10000                 # ../project.toml; gen_image.py stages [LOAD_BASE, ...)

ORIGINAL_PRG = PROJECT / "bin" / "ZYNAPS17.PRG"
ORIGINAL_DISK = PROJECT / "bin" / "disk"
ORIGINAL_AUTO = r"C:\AUTO\ZYNAPS17.PRG"

OUR_DISK = HERE / "disk"
OUR_AUTO = r"C:\ZYNAPS.PRG"
OUR_PRG_NAME = "ZYNAPS.PRG"

# --- the floppy mode's two media, and the build that goes on ours -------------------------------
# atari/mkfloppy.py writes this; `build.sh floppy` is what calls it, out of the same shim sources
# and with no `-D` of its own, so AUTO\ZYNAPS17.PRG on the volume is the `title` binary under
# another name. The negative control has a mode of its own and needs no second image.
OUR_FLOPPY = OUR_DISK / "ZYNAPS.ST"
# The original's own floppy: ../../bin/zynaps.st, the dump with the protection tracks absent
# (../../README.md's boot table has it reaching level 1). Booting the original off a floppy too is
# what keeps `floppy` a comparison of two PROGRAMS rather than of two media — and it is also what
# lets the mode run on a ROM below 1.04, where Hatari refuses GEMDOS directory emulation outright.
ORIGINAL_FLOPPY = PROJECT / "bin" / "zynaps.st"

# Two symbols of ours, by TEXT offset, out of the linked ELF. tos.ld links at 0 and build.sh
# refuses a `_start` anywhere but the first byte, so a symbol's value IS its offset from wherever
# GEMDOS loaded us. `run_ours_from_floppy` says what the pair is for.
ANCHOR_SYMBOL = "zy_anchor"
VBL_ENTRY_SYMBOL = "zy_vbl_entry"
NM = "m68k-elf-nm"
# The 68000's vertical-blank vector, at a FIXED address whatever GEMDOS did with the program.
A_VECTOR_VBL = 0x70
VECTOR_BYTES = 4
FIXUP_DUMP = "fixup.bin"
VECTOR_DUMP = "vector.bin"

# The files the SHIM moves, which the original never touches. The trap-ledger check subtracts them
# by name so that what is left on our side is the GAME's own I/O and nothing else. Kept equal to
# zynaps_main.c's four FILE_* constants by `assert_the_shim_owns_these_names`, below.
SHIM_FILES = ("ZYNAPS.IMG", "BASE.BIN", "SCREEN.BIN", "STATE.BIN")
SHIM_MAIN = HERE / "zynaps_main.c"
# ...and the reconstruction itself, which is where every Ghidra address and record geometry the
# frame differential uses is DEFINED. `assert_the_game_constants_are_the_headers` reads them rather
# than this file retyping the numbers (CLAUDE.md §5).
RECREATE = HERE.parent                         # projects/zynaps/recreate
# ...and TOS's own, which is on BOTH drives and lands at a different point in the two boots: ours is
# auto-run after the desktop has read its preferences, the shipped disk runs the game out of C:\AUTO
# before the desktop exists at all. It is the operating system's I/O, not either program's.
TOS_FILES = ("DESKTOP.INF",)
NON_GAME_FILES = SHIM_FILES + TOS_FILES

# How many files `boot_load_title_assets` opens — ../src/init.c: zynpic.pic, power.dat, myship.dat,
# then BOOT_LATE_LOADS' five. It is the floor `check_trap_ledger` refuses to pass without, because a
# ledger comparison between two empty lists is green for ever and that is exactly what shipped here
# once (the parser read the opcode field as the call name).
BOOT_FILE_OPENS = 8

# --- the record ----------------------------------------------------------------------------------
# zynaps_main.c's field order. PINNED BY LENGTH: the binary publishes its own field count as field 1
# and `read_record` refuses a mismatch, so a field added there and not here fails at the parse with
# both numbers printed rather than shifting every value after it by one.
RECORD_MAGIC = 0x5A594D31           # 'ZYM1'
RECORD_TAIL = 0x444F4E45            # 'DONE'

# The five addresses `frame_resolve_hits_and_game_state` leaves through, in ../include/frame.h's own
# order, and the seven handlers the three interrupt entries dispatch to, in zynaps_main.c's. Named
# here so the record reads as prose — `vbl_dispatch_attract` rather than field 96 — and because a
# table that grew a handler on one side of the language boundary and not the other is caught by the
# field count rather than by a wrong number under the right name.
FRAME_EXIT_NAMES = ("title", "reload_section", "restart_section", "advance_section", "next_frame")
# zynaps_main.c's PACING_SLOTS — the pacing histogram's width, pinned against the C by
# `assert_the_phase_names_are_the_shims`.
PACING_SLOTS = 8
VBL_HANDLER_NAMES = ("in_game", "title", "menu", "attract")
TIMER_B_HANDLER_NAMES = ("in_game", "raster", "attract")
RECORD_FIELDS = (
    ["magic", "fields",
     "image_base", "program_staged_bytes", "super_token",
     "acia_bytes_after_mouse_off", "acia_bytes_after_joystick_mode",
     "shifter_mode_writes", "shifter_mode_mask", "palette_long_writes",
     "image_saved_vbl_vector", "tos_vbl_vector", "tos_timer_b_vector",
     "image_screen_back", "image_screen_front", "published_screen_base",
     "physbase_at_anchor", "raw_video_base_at_anchor", "rez_at_anchor",
     "vbl_ticks_at_anchor", "timer_b_ticks_at_anchor",
     # The boot's own clock, in TOS 200 Hz ticks: each of the two asset loaders bracketed
     # by its OWN entry and exit mark, so neither span bills the other's work (the
     # gameplay pair is 0 in a title build, which does not load them). zynaps_main.c says
     # why the program takes this measurement itself, and why the counter is $4ba rather
     # than its own vblanks.
     "ticks_at_title_assets", "ticks_after_title_assets",
     "ticks_at_gameplay_assets", "ticks_after_gameplay_assets", "ticks_at_teardown",
     "psg_writes", "psg_refused", "hw_writes",
     "file_opens", "file_open_failures", "file_refusals",
     "fault_pen", "smoke_vbls", "anchor_hold_vbls", "screen_bytes_written"]
    + [f"pen_at_entry_{pen}" for pen in range(PALETTE_PENS)]
    + [f"pen_at_anchor_{pen}" for pen in range(PALETTE_PENS)]
    + ["vbl_vector_after", "timer_b_vector_after", "physbase_after", "rez_after"]
    + [f"pen_after_{pen}" for pen in range(PALETTE_PENS)]
    # ---- M2's own fields. ZERO IN A TITLE BUILD, and `check_the_game_fork_was_not_taken` asserts
    # exactly that rather than skipping them: a title binary that had somehow run the game path
    # would otherwise pass every M1 surface while being a different program.
    + ["phase_reached", "attract_passes", "section_starts", "frames_run"]
    + [f"frame_exit_{name}" for name in FRAME_EXIT_NAMES]
    + [f"vbl_dispatch_{name}" for name in VBL_HANDLER_NAMES]
    + [f"timer_b_dispatch_{name}" for name in TIMER_B_HANDLER_NAMES]
    + ["acia_ticks", "acia_dispatches",
       "unknown_vector_halts", "unknown_vector", "unknown_vector_handler",
       "mfp_settle_restores", "rmw_stores",
       "tos_acia_vector", "acia_vector_after",
       "player_count", "level_section", "lives", "score_bcd", "frame_dump_bytes", "game_fault",
       "first_life_ended_at",
       "video_base_offset", "video_base_published", "video_base_publishes"]
    # THE PACING SURFACE: one field per vblank count a `frame_loop_once` took, plus the vblanks the
    # frame loop spent in total — which is what gives the exact mean, since the histogram's last
    # slot is "seven or more". zynaps_main.c's PACING_SLOTS argues the shape and `check_the_pacing`
    # is what reads them.
    + [f"frame_vbls_{count}" for count in range(PACING_SLOTS - 1)] + ["frame_vbls_over"]
    + ["playing_vbls",
       "tail"])

# STATE.BIN's length, which is the record's own — one big-endian longword a field. The floppy
# mode's "the machine finished" test compares the trace's Fwrite byte count against it, so the
# number is derived from the field list rather than typed beside it.
RECORD_BYTES = len(RECORD_FIELDS) * 4

OS_SUPER_TOKEN = 0x00535550         # the kit's os.h — what the model's Super(0) answers
NO_FAULT_PEN = 0xFFFFFFFF           # zynaps_main.c publishes -1 as an unsigned longword

# --- the anchors ---------------------------------------------------------------------------------
# The run is anchored on what the MACHINE did, never on a stopwatch — and the two sides need
# different kinds of anchor, for a reason that cost this file a rewrite.
#
# OURS is a PC: the shim writes BASE.BIN with the runtime address of `zy_anchor` before it loads
# anything, and then spends five seconds on the title screen, so there is all the time in the world
# to arm a breakpoint on an address the program has not reached yet.
#
# THE ORIGINAL'S CANNOT BE A PC, and the first draft's was. A PC breakpoint has to be armed BEFORE
# the program arrives there, the address is only known once the program is in RAM, and the original
# runs `_start` from 0x10000 to 0x101ba in a few milliseconds of emulated time — so by the time a
# RAM poll has seen the program and computed its load base, the anchor is already behind it and the
# breakpoint never fires (measured: it never did). So the original is anchored on a STATE instead:
# the last of the sixteen colour registers holding the boot palette's last pen. That condition
# becomes true when `set_palette_title` runs at 0x10084 and STAYS true until the front end changes
# the palette about twenty seconds later, so it fires whether it was armed before or after — which
# is what makes it immune to the race a PC has. It needs no load address at all, and the value it
# names is read off the shipped binary's own data.
#
# WHAT THAT COSTS, and it is nothing this file compares: the original is photographed at 0x10084
# rather than at 0x101ba, i.e. before the last seven of the boot's eight file loads. Those seven
# read into 0x41eae..0x6115e, all below the framebuffer at 0x70300, and none of them touches the
# palette — so the screen, the pens, the resolution and the video base are identical at both points.
# The trap ledger and the PSG timeline are read out of the whole run's trace file and do not depend
# on where the shot was taken at all.
#
# Both sides are then photographed STOP-THEN-SHOOT: break at the anchor, arm a breakpoint some
# vertical blanks later, and capture from THAT one's action file — because the display surface is
# built scanline by scanline and a capture taken where the anchor happens to fire mixes that frame
# with the one before.
# (the anchor breakpoint runs the settle chain directly — it needs no action file of its own)
SHOOT_ACTION = "SHOOT.INI"
# Vertical blanks between the anchor and the shot. More than one, because the ORIGINAL's anchor is
# the palette upload — four instructions after it published its framebuffer — and the shifter only
# latches a new base at the start of a frame, so a shot one vblank later could still be a picture of
# TOS's screen. Our own build holds `zy_anchor` for longer than this and PUBLISHES that hold, which
# `check_the_program_finished` compares: the two numbers are in different languages and the check is
# the pin.
ANCHOR_SETTLE_VBLS = 4
WAIT_ACTION = "WAIT%d.INI"
ANCHOR_DEADLINE_SECONDS = 180.0
# Between RAM dumps while waiting for a program to be loaded. Each dump is 4 MB through the
# debugger, so this is slower than POLL_SECONDS on purpose.
PROGRAM_POLL_SECONDS = 1.0
BASE_FILE = "BASE.BIN"
BASE_POLL_START_SECONDS = 3.0
# How long our side is left running AFTER the program has Ptermed, before the log is judged. The
# machine survives a badly handed-back vector for about a second and then dies, so a check that
# stopped at the record would see nothing (docs/on-target-execution.md class 7).
POST_EXIT_SECONDS = 3.0
STATE_FILE = "STATE.BIN"
SCREEN_FILE = "SCREEN.BIN"

# What the shoot breakpoint dumps, and what each is called on disk.
DUMP_PENS = "PENS.BIN"
DUMP_REZ = "REZ.BIN"
DUMP_BASE_HIGH = "VBHI.BIN"
DUMP_BASE_MID = "VBMID.BIN"
DUMP_SCREEN = "FB.BIN"
SHOT = "shot.png"
DUMP_DONE = "SHOTDONE.BIN"          # written last, so the driver can tell the shoot finished

# --- the timeline ----------------------------------------------------------------------------
TRACE_FLAGS = "gemdos,psg_write"
# How many of the driver's tick frames are compared. The tune is 50 Hz and deterministic on both
# sides, so any number works; 64 is over a second of it and keeps a failure's printout readable.
TICK_FRAMES_COMPARED = 64

# --- the success gate ----------------------------------------------------------------------------
BLANK_COLOUR_COUNT = 1              # a capture with one colour is a photograph of nothing

# WHAT A FAULT LINE LOOKS LIKE, IN HATARI'S OWN CASING. The shared `tools/hatari_headless.py` list
# spells "Bus error"; Hatari 2.6.1 prints "WARN : Bus Error writing at address $41fffe" — measured,
# in this directory's own logs — so the shared markers match nothing and `log_faults` returns [] over
# a log that names a bus error. That is the sibling project's half-blind exit detector exactly, and
# it is why these are passed explicitly rather than defaulted. (The shared list is worth fixing where
# it lives; doing it here would redden every other project's harmless TOS probe, so this file names
# the bug and leaves the tools change to its own commit — README.md, "Out of scope".)
FAULT_MARKERS = ("Bus Error", "Address Error", "CPU halted", "Failed to load", "Not a disk image")

# ...AND THE ONE FAULT THAT IS NOT THE PROGRAM'S. TOS sizes memory by writing past the top of RAM and
# catching the bus error, so every 4 MB boot logs one at a ROM address. docs/on-target-execution.md:
# "TOS boot-time bus errors at PC=$e000xx are the ROM probing hardware — harmless, ignore them; a
# panic from *your* text segment is real." Matched on the PC rather than on the address, so a fault
# our own code takes at the same address is still reported.
TOS_ROM_PC = re.compile(r"PC=\$(e0|fc)[0-9a-f]{4}\b")


# =================================================================================================
# Running one side
# =================================================================================================
def gemdos_medium(drive, auto):
    """A Hatari GEMDOS drive: a host directory as C:, with the program auto-run off it."""
    return ["--harddrive", str(drive), "--auto", auto]


def booted_copy(image, work):
    """A scratch copy of a floppy image, because Hatari mounts one READ-WRITE and writes it back.

    Neither side may be booted from the file it lives in. Ours is a build artifact that would end up
    holding the previous run's `SCREEN.BIN`; the original's is `../../bin/zynaps.st`, a GreaseWeazle
    preservation dump that is gitignored and that nothing recovers if a boot writes to it
    (CLAUDE.md §8 — "what version control won't recover"). A `--protect-floppy on` would stop the
    writes but would also stop OUR side's record ever being written, so the copy is what both get.
    """
    copy = work / image.name
    shutil.copy(image, copy)
    return copy


def floppy_medium(image):
    r"""A real FAT12 volume in drive A:, booted the way the machine on the desk boots — no --auto:
    TOS's desktop finds AUTO\*.PRG by itself, which is the loader the original ships for."""
    return ["--disk-a", str(image)]


def hatari_arguments(medium, trace_file, machine, tos_rom, run_vbls=RUN_VBLS,
                     trace_flags=TRACE_FLAGS):
    """The whole Hatari command line for one side. Both sides get exactly this, bar the medium.

    --frameskips 0, --statusbar off and --drive-led off are the three settings that decide whether a
    screenshot comparison can succeed at all: without the first, Hatari emulates every frame but
    renders only some and `screenshot` grabs whichever was last drawn; without the third it paints
    an activity LED IN THE TOP-RIGHT BORDER, i.e. inside the photographed area, and the extra
    colours push its PNG writer from a palette image to a truecolour one so the two files can never
    match whatever the pixels do. All three are docs/on-target-execution.md class 8's measurements.

    `trace_flags=None` LEAVES `--trace` OFF ENTIRELY, for a caller that reads no trace. It is not
    the same as pointing `--trace-file` at the null device: `psg_write` fires on every write to the
    sound chip, thousands an emulated second with music playing, and Hatari FORMATS every one of
    those lines before the kernel throws them away. `atari/profile.py` is the caller — its runs are
    raced against a host-time deadline, so that formatting is work taken off a measurement.
    """
    trace = ["--trace", trace_flags, "--trace-file", str(trace_file)] if trace_flags else []
    return [HATARI, "--tos", str(tos_rom), "--machine", machine, "--memsize", str(MEMSIZE_MB),
            "--monitor", "rgb", "--confirm-quit", "off", "--statusbar", "off",
            "--drive-led", "off", "--frameskips", "0", "--sound", "off",
            "--run-vbls", str(run_vbls)] + trace + list(medium)


def shoot_commands(work):
    """What the NEXT-VBLANK breakpoint does: photograph, then dump the shifter.

    The pens, the resolution byte and the two video-base bytes are read out of the emulated
    MACHINE, not out of the program — which is the whole point of the hardware-state vector. The
    program reads them back too, into STATE.BIN, and the two are compared: an agreement between an
    independent reader and the program's own is worth more than either alone.
    """
    return [f"screenshot {work / SHOT}",
            f"savebin {work / DUMP_PENS} ${HW_PALETTE_BASE:x} ${PALETTE_PENS * PEN_BYTES:x}",
            f"savebin {work / DUMP_REZ} ${HW_SHIFTER_RESOLUTION:x} $1",
            f"savebin {work / DUMP_BASE_HIGH} ${HW_SHIFTER_BASE_HIGH:x} $1",
            f"savebin {work / DUMP_BASE_MID} ${HW_SHIFTER_BASE_MID:x} $1"]


def settle_chain(work, vblanks, clause):
    """A `:file` clause that runs `clause` exactly `vblanks` vertical blanks from when it is armed.

    HATARI'S BREAKPOINT EXPRESSIONS HAVE NO ARITHMETIC. `b VBL > VBL + 4` is refused at the `+`
    ("ERROR in parsed string", measured on 2.6.1), so "N vblanks from now" cannot be one
    breakpoint. What DOES work is `b VBL > VBL`, because Hatari substitutes the expression's current
    value on the right when the breakpoint is set — that is "the next vblank" — so N of them nested,
    each arming the next, is N vblanks. `:once` on every one: a repeat would re-arm the chain.
    """
    for step in range(vblanks):
        clause = action_file(work, WAIT_ACTION % step, f"b VBL > VBL :once :quiet {clause}")
    return clause


def arm_anchor(session, condition, extra_shoot_commands=()):
    """Break when `condition` holds, and from there photograph ANCHOR_SETTLE_VBLS vblanks later.

    The last thing the shot does is dump one byte to DUMP_DONE, which is how the driver SEES the
    capture finish instead of waiting a guessed number of seconds for it.
    """
    shoot = action_file(session.work, SHOOT_ACTION,
                        *shoot_commands(session.work), *extra_shoot_commands,
                        f"savebin {session.work / DUMP_DONE} ${HW_SHIFTER_RESOLUTION:x} $1")
    session.arm(f"b {condition} :once :quiet "
                f"{settle_chain(session.work, ANCHOR_SETTLE_VBLS, shoot)}")
    return session.work / DUMP_DONE


def boot_palette():
    """The sixteen colours `set_palette_title` uploads, read off the staged program image.

    The shipped binary's own bytes, relocated by the same loader the differential uses, so nothing
    here names a colour of its own — and nothing here is taken from a run of ours, which is what
    would make the comparisons below circular.
    """
    image = (OUR_DISK / PROGRAM_IMAGE).read_bytes()
    offset = PALETTE_BOOT_ADDRESS - LOAD_BASE
    return list(struct.unpack(f">{PALETTE_PENS}H", image[offset:offset + PALETTE_PENS * PEN_BYTES]))


def original_anchor_condition():
    """The state that says the original has uploaded its title palette.

    The last colour register holding the boot palette's last pen. See the "the anchors" note above
    for why the original's anchor is a state and ours is a program counter.
    """
    last_pen_register = HW_PALETTE_BASE + (PALETTE_PENS - 1) * PEN_BYTES
    return f"($ff{last_pen_register:x}).w = ${boot_palette()[-1]:x}"


def await_file(session, path, doing, deadline_seconds=ANCHOR_DEADLINE_SECONDS):
    """Block until a file the MACHINE writes appears, or say what did not happen."""
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        if path.is_file() and path.stat().st_size:
            return path
        session.require_alive(doing)
        session.wait(POLL_SECONDS)
    raise SystemExit(f"{path.name} never appeared in {deadline_seconds:.0f} s — {doing}")


def run_ours(mode, out_dir, work, machine, tos_rom):
    """Boot our .PRG off a GEMDOS drive, photograph it at its anchor, collect what it wrote."""
    trace = out_dir / f"{mode}.trace"
    log = out_dir / f"{mode}.log"
    session = HeadlessSession(hatari_arguments(gemdos_medium(OUR_DISK, OUR_AUTO), trace,
                                              machine, tos_rom),
                              log_path=log, fifo_path=out_dir / f"{mode}.fifo", work_dir=work)
    try:
        # The shim writes BASE.BIN — the runtime address of `zy_anchor` — onto the GEMDOS drive
        # before it loads anything, and a GEMDOS drive IS a host directory, so it simply appears.
        # That is the load address discovered rather than assumed: GEMDOS put us wherever the TPA
        # fell, and a breakpoint on a guessed address is a breakpoint on nothing.
        session.wait(BASE_POLL_START_SECONDS)
        base_file = await_file(session, OUR_DISK / BASE_FILE, "waiting for the program to start")
        anchor_pc = struct.unpack(">I", base_file.read_bytes()[:4])[0]
        done = arm_anchor(session, f"pc = ${anchor_pc:x}")
        await_file(session, done, "waiting for our anchor's next-vblank capture")
        # ...and then the program finishes on its own: the record is written after the hand-back.
        await_file(session, OUR_DISK / STATE_FILE, "waiting for the program's own record")
        # Let the emulator run ON past the exit, and judge the log afterwards. A vector left
        # pointing into memory GEMDOS has taken back kills the machine about a second after Pterm,
        # and the whole class is invisible to every check that stops at the dump.
        session.wait(POST_EXIT_SECONDS)
    finally:
        status = session.close()
    return {"status": status, "log": log, "trace": trace, "work": work,
            "record": read_record(OUR_DISK / STATE_FILE),
            "screen": (OUR_DISK / SCREEN_FILE).read_bytes(),
            "shot": work / SHOT}


def symbol_offsets(mode, *wanted):
    """The named symbols' TEXT offsets, out of the linked ELF build.sh kept beside the .PRG."""
    elf = HERE / "build" / f"zynaps-{mode}.elf"
    if not elf.is_file():
        raise SystemExit(f"no {elf} — run `bash {HERE / 'build.sh'} {mode}` first")
    found = {}
    for line in subprocess.run([NM, str(elf)], check=True, capture_output=True,
                               text=True).stdout.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] in wanted:
            found[fields[2]] = int(fields[0], 16)
    missing = [name for name in wanted if name not in found]
    if missing:
        raise SystemExit(f"{elf} has no {missing} — nothing here can name an address in that build")
    return [found[name] for name in wanted]


def log_hint(session):
    """Where to look, in a message about a machine that did something other than what was wanted."""
    return f"See {session.log_path}."


def poll_for_our_load_base(session, vbl_entry, prg):
    """Where GEMDOS put OUR program, taken from the vector the program itself publishes.

    NOT A SIGNATURE SEARCH, and it cannot be one: `locate_by_signature` cuts its needle from the
    bytes BEFORE a program's first relocation, and this build's first fixup is at TEXT offset 0xa —
    ten bytes, which is shorter than any needle worth searching 4 MB for. (The original's first
    fixup is far enough in that the search works, which is why that side still uses it.)

    What this uses instead is a fact the program PUBLISHES at a fixed address: `_start` installs
    `zy_vbl_entry` at the 68000's vertical-blank vector, $70, and $70 does not move with the TPA. So
    the vector's contents minus that symbol's TEXT offset IS the load address — one 4-byte dump per
    poll instead of a 4 MB one, and no disk-buffer twin to disambiguate.

    IT IS THEN CONFIRMED BY RELOCATION, which is the same exact test the signature search ends with:
    GEMDOS adds the load address to the first fixup's longword in place, so at the right base that
    longword reads `the file's own value + base` and at a wrong one it does not. A vector that
    happened to hold something else — TOS's own, or a value read before TOS had set it — fails that
    and the poll keeps going.
    """
    image = prg.read_bytes()
    fixup = first_fixup_offset(image)
    if fixup is None:
        raise SystemExit(f"{prg.name} has no relocations — the load address could not be confirmed")
    unrelocated = struct.unpack_from(">I", image, PRG_HEADER_BYTES + fixup)[0]

    # WHAT MAY BE HANDED TO `savebin`, and it is not "anything even". The debugger refuses a range
    # outside the machine's memory by writing no file at all, which `HeadlessSession.savebin` turns
    # into a hard SystemExit after its own timeout — so a candidate this poll means to SHRUG OFF
    # would abort the run and report a debugger fault. $70 holds TOS's own handler until our program
    # replaces it, and holds uninitialised RAM before TOS gets there, so the candidate is filtered
    # to a range that can be dumped before it is dumped.
    def is_a_dumpable_base(candidate):
        return (candidate > 0 and not candidate % 2
                and candidate + fixup + VECTOR_BYTES <= ST_RAM_BYTES)

    deadline = time.monotonic() + ANCHOR_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        vector, = struct.unpack(">I", session.savebin(VECTOR_DUMP, A_VECTOR_VBL, VECTOR_BYTES))
        base = vector - vbl_entry
        if is_a_dumpable_base(base):
            live, = struct.unpack(">I", session.savebin(FIXUP_DUMP, base + fixup, VECTOR_BYTES))
            if live == unrelocated + base:
                return base
        session.require_alive("waiting for the desktop to run our program")
        session.wait(PROGRAM_POLL_SECONDS)
    # TWO THINGS LOOK IDENTICAL FROM HERE and the message names both, because the likelier one is
    # not the one a reader guesses. `_start` installs this vector AFTER the boot slice, so anything
    # that hangs before it — most concretely `ikbd_send_cmd`, whose spin is unbounded on target by
    # design — leaves $70 holding TOS's own handler for ever, exactly as a program that never loaded
    # would. An earlier draft named only the loader and would have blamed TOS for a dead 6850.
    raise SystemExit(f"${A_VECTOR_VBL:x} never held a relocated {VBL_ENTRY_SYMBOL}: either the "
                     f"desktop did not run {mkfloppy.AUTO_DIR}\\{mkfloppy.AUTO_PRG}, or the "
                     f"program is hung before it installs its vectors (ikbd_send_cmd's spin on the "
                     f"ACIA is the one place in the boot slice that can). {log_hint(session)}")


def floppy_file(image_path, name):
    """One file's bytes out of a .ST volume, through tools/st_extract.py's own FAT12 reader.

    THE WARNINGS ARE READ AFTER THE READ, not before it. st_extract appends its chain diagnostics —
    a cluster chain that loops, one that runs into a bad-cluster marker, one holding fewer bytes than
    the directory entry claims — from inside `read_file`, so a check made before it inspects an empty
    list. A short STATE.BIN handed on unremarked is then reported by `read_record_bytes` as "no
    'DONE' tail", which blames the program for a defect in the volume.
    """
    volume = st_extract.Fat12Image(image_path.read_bytes())
    data = st_extract.read_file(volume, name)
    if volume.warnings:
        raise SystemExit(f"{image_path.name}: {volume.warnings[0]}")
    if data is None:
        raise SystemExit(f"{image_path.name} has no {name} — the run did not get that far")
    return data


def state_record_is_written(trace):
    """True once the GEMDOS ledger shows STATE.BIN created, written WHOLE, and closed.

    THE RUN'S END IS A FACT ABOUT THE MACHINE, not a stopwatch. On a GEMDOS drive the record simply
    appears as a host file and `await_file` waits for it; on a floppy it goes into the image, which
    Hatari keeps in memory until it is quit — so the evidence has to come from somewhere the driver
    can see WHILE the machine runs, and the trace it is already collecting is it. The close matters
    as much as the write: GEMDOS flushes the file's last sectors and its directory entry there, and
    a quit before it would flush an image whose STATE.BIN is not all on the volume.

    AND THE WRITE'S LENGTH MATTERS AS MUCH AS THE CLOSE. `write_file` in zynaps_main.c ignores what
    Fwrite returns, so a volume with no cluster left produces Fcreate -> Fwrite of ZERO bytes ->
    Fclose, which a create-and-close test reads as success. The driver would then quit, flush an
    empty STATE.BIN, and the finding would surface as a record that could not be parsed rather than
    as a disk that was full. The trace carries the byte count, so this asks for it.
    """
    calls = gemdos_calls(trace)
    for index, call in enumerate(calls):
        if call != ("Fcreate", STATE_FILE):
            continue
        rest = calls[index + 1:]
        wrote = any(later[0] == "Fwrite" and later[2] == RECORD_BYTES for later in rest)
        return wrote and any(later[0] == "Fclose" for later in rest)
    return False


def await_condition(session, predicate, doing, deadline_seconds=ANCHOR_DEADLINE_SECONDS):
    """Block until the machine has done something, or say what it did not do.

    `doing` is CALLED, not passed as a string, so a message that reports how far the machine got is
    built when it is printed rather than before the first poll. An f-string argument would freeze
    that count at zero and point a reader at the wrong side of the comparison.
    """
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        session.require_alive(doing())
        session.wait(POLL_SECONDS)
    raise SystemExit(f"{doing()} — nothing in {deadline_seconds:.0f} s")


def run_ours_from_floppy(mode, build, out_dir, work, machine, tos_rom):
    r"""Boot our .PRG the way the machine on the desk does: TOS's desktop, off AUTO\ on a FAT12 disk.

    FOUR THINGS DIFFER FROM `run_ours`, and all four are consequences of the medium.

      * NOTHING AUTO-RUNS IT. The desktop's own AUTO scan finds AUTO\ZYNAPS17.PRG — which is why
        mkfloppy.py keeps the original's file name — so there is no `--auto` on the command line and
        the loader under test is TOS's, not Hatari's.
      * THE ANCHOR CANNOT COME FROM BASE.BIN. That file is written onto the FLOPPY, and Hatari holds
        the image in memory until it is quit, so the driver cannot read it during the run. The load
        address comes out of the vertical-blank vector the program installs instead
        (`poll_for_our_load_base`), and `zy_anchor`'s offset out of the ELF.
      * THE RECORD AND THE FRAMEBUFFER ARE READ OUT OF THE IMAGE, after the session is closed. The
        quit is what makes Hatari write the volume back; `--run-vbls` expiring does NOT (measured —
        README.md's floppy section carries it), which is why this waits for the record and closes
        rather than letting the vblank budget run out.
      * THE FLOPPY IS A COPY, and so is the original's — `booted_copy` is what both sides go
        through. Hatari mounts a `.ST` read-write and writes it back when it is quit, so a run
        against `disk/ZYNAPS.ST` itself would leave the build's own artifact holding the last run's
        output, and the next run would boot a disk with 34 clusters already spent. The original's
        matters more and for a different reason: `../../bin/zynaps.st` is a GreaseWeazle
        preservation dump, gitignored, and nothing recovers it if TOS or the game writes to it.
    """
    trace = out_dir / f"{mode}.trace"
    log = out_dir / f"{mode}.log"
    image = booted_copy(OUR_FLOPPY, work)

    session = HeadlessSession(hatari_arguments(floppy_medium(image), trace, machine, tos_rom),
                              log_path=log, fifo_path=out_dir / f"{mode}.fifo", work_dir=work)
    try:
        # THE MODE NAMES THE ARTIFACTS AND THE BUILD NAMES THE BINARY. `floppy` is a mode of this
        # file and not of build.sh any more (the medium is a flag there), so the ELF whose symbols
        # this reads is the one that was written onto the volume — `--floppy-build`'s.
        vbl_entry, anchor = symbol_offsets(build, VBL_ENTRY_SYMBOL, ANCHOR_SYMBOL)
        base = poll_for_our_load_base(session, vbl_entry, built_prg(build))
        done = arm_anchor(session, f"pc = ${base + anchor:x}")
        await_file(session, done, "waiting for our anchor's next-vblank capture")
        await_condition(session, lambda: state_record_is_written(trace),
                        lambda: "waiting for the program to write its record to the floppy")
        session.wait(POST_EXIT_SECONDS)
    finally:
        status = session.close()

    return {"status": status, "log": log, "trace": trace, "work": work,
            "record": read_record_bytes(floppy_file(image, STATE_FILE)),
            "screen": floppy_file(image, SCREEN_FILE),
            "shot": work / SHOT}


def run_original(out_dir, work, medium, machine, tos_rom, ledger_calls):
    """Boot the shipped binary the same way, and photograph it at the same point in its own boot.

    `ledger_calls` is how many GAME calls OUR side made, and this run is held open until the
    original's trace holds at least that many. The ledger check compares our whole call list against
    the original's first slice of it, so an original closed too early makes that comparison one
    between a list and a shorter list — which is what a floppy boot produces, the medium being some
    forty times slower than the host directory the GEMDOS modes use.
    """
    trace = out_dir / "original.trace"
    log = out_dir / "original.log"
    session = HeadlessSession(hatari_arguments(medium, trace, machine, tos_rom),
                              log_path=log, fifo_path=out_dir / "original.fifo", work_dir=work)
    try:
        # ARMED BEFORE THE PROGRAM IS EVEN LOADED, and that is the whole point of a state condition.
        # The shipped disk runs the game out of C:\AUTO, so it is in RAM within the first seconds of
        # TOS's boot and reaches its palette upload a few milliseconds later; anything that waits to
        # SEE it loaded has already missed. (Measured: a first draft polled RAM for the program and
        # then armed, and anchored the original in its FRONT END twenty seconds later — 22,948 of
        # 32,000 framebuffer bytes apart, with pen 0 blanked by a title-screen handler our boot
        # never installs.) The cost is that Hatari evaluates the condition after every instruction
        # for the length of TOS's boot, which is seconds, not minutes.
        done = arm_anchor(session, original_anchor_condition(),
                          # The original displays `screen_back` after its one flip, at the ABSOLUTE
                          # address it hard-codes — no `+ base`, because it never asks XBIOS.
                          [f"savebin {work / DUMP_SCREEN} ${GAME_SCREEN_BACK:x} ${SCREEN_BYTES:x}"])
        await_file(session, done, "waiting for the original's capture at its title palette")
        # ...and only NOW is the base worth measuring: the program is certainly in RAM, so one dump
        # answers instead of a poll. It is not what the anchor is made of — it is how the run
        # reports WHERE the original was loaded, and what the screen dump above is checked against.
        base = poll_for_program(session, ORIGINAL_PRG,
                                "waiting for the original to be loaded")
        # The anchor is the FIRST frame of the tune, so the trace has almost none of it yet. Ours
        # has run for five seconds by its anchor and needs no such wait.
        wait_for_tick_frames(session, trace, TICK_FRAMES_COMPARED, "the original's")
        # ONE parse per poll, shared by the test and the message: `gemdos_calls` re-reads and
        # re-matches the whole trace, and the message needs the same number the test just computed.
        made = [0]

        def counted():
            made[0] = len(gemdos_calls(trace, drop_names=NON_GAME_FILES))
            return made[0] >= ledger_calls

        await_condition(session, counted,
                        lambda: f"waiting for {ledger_calls} of the original's GEMDOS calls "
                                f"(it has made {made[0]})")
        # The original never terminates — it runs on into its front end — so this side is closed by
        # the driver rather than by the program.
    finally:
        status = session.close()
    return {"status": status, "log": log, "trace": trace, "work": work,
            "base": base, "screen": (work / DUMP_SCREEN).read_bytes(), "shot": work / SHOT}


def wait_for_tick_frames(session, trace, count, whose):
    """Let the machine run until `count` of the sound driver's tick frames are in its trace."""
    deadline = time.monotonic() + ANCHOR_DEADLINE_SECONDS
    reader = ref_capture.TraceReader(trace)
    while time.monotonic() < deadline:
        if reader.update() >= count:
            return
        session.require_alive(f"collecting {whose} tick frames")
        session.wait(POLL_SECONDS)
    raise SystemExit(f"only {len(reader.frames)} of {whose} tick frames appeared in "
                     f"{ANCHOR_DEADLINE_SECONDS:.0f} s — the sound driver is not running")


def poll_for_program(session, prg, doing):
    """Where GEMDOS put a .PRG, found by a relocation-verified signature search.

    A poll rather than one dump because the caller may not know the program is loaded yet: the
    floppy mode uses it as its ANCHOR's first half, before the program has reached anything, while
    the original side calls it after its own anchor has already fired and gets an answer first try.
    """
    deadline = time.monotonic() + ANCHOR_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        found = locate_by_signature(session.savebin(RAM_DUMP_NAME, 0, ST_RAM_BYTES), prg)
        if found is not None:
            return found
        session.require_alive(doing)
        session.wait(PROGRAM_POLL_SECONDS)
    raise SystemExit(f"{prg.name} was never in RAM — {doing}")


# =================================================================================================
# Reading what came back
# =================================================================================================
def read_record(path):
    """STATE.BIN as a dict, read from a host file (the GEMDOS-drive modes' record)."""
    return read_record_bytes(Path(path).read_bytes(), str(path))


def read_record_bytes(blob, where=STATE_FILE):
    """...and the same parse over bytes, for a record lifted out of a floppy image.

    Refuses anything that is not the record this file knows: the magic, the FIELD COUNT the binary
    publishes as field 1 (so a field added in one language and not the other fails at the parse with
    both numbers printed, rather than shifting every value after it by one), and the 'DONE' tail
    zynaps_main.c writes last.
    """
    # THE LENGTH IS CHECKED BEFORE ANYTHING IS INDEXED, because on the floppy path this blob is
    # whatever a cluster chain actually held. A record cut short by a write that ran out of disk
    # has a valid magic and a valid field count and no `tail` key at all, and every check below
    # would raise a KeyError instead of the sentence this function exists to print.
    values = list(struct.unpack(f">{len(blob) // 4}I", blob[:len(blob) // 4 * 4]))
    if len(values) != len(RECORD_FIELDS):
        raise SystemExit(f"{where}: {len(blob)} bytes is {len(values)} longwords, and the record is "
                         f"{len(RECORD_FIELDS)} — it was truncated, most likely by a write that ran "
                         f"out of room on the volume")
    if not values or values[0] != RECORD_MAGIC:
        raise SystemExit(f"{where}: not a Zynaps record (magic {values[:1]})")
    if values[1] != len(RECORD_FIELDS):
        raise SystemExit(f"{where}: the binary published {values[1]} fields and this file names "
                         f"{len(RECORD_FIELDS)} — zynaps_main.c's record moved and smoke.py did not")
    record = dict(zip(RECORD_FIELDS, values))
    if record["tail"] != RECORD_TAIL:
        raise SystemExit(f"{where}: no 'DONE' tail — the program did not finish writing it")
    return record


def pens_from_dump(blob):
    """The sixteen colour registers a `savebin` of $ff8240 holds, masked to the bits the ST has."""
    return [word & PEN_MASK for word in struct.unpack(f">{PALETTE_PENS}H", blob[:PALETTE_PENS * PEN_BYTES])]


def pens_from_record(record, prefix):
    return [record[f"{prefix}_{pen}"] for pen in range(PALETTE_PENS)]


# HATARI'S GEMDOS TRACE LINE, and the parser is written against a MEASURED sample rather than a
# guess, because the first one was not and the surface it fed was empty on both sides for every run:
#
#     GEMDOS 0x3D Fopen("zynpic.pic", read-only) at PC=0xEF4C
#     GEMDOS 0x3F Fread(64, 32000, 0x70300) at PC 0xEF68
#     GEMDOS 0x3E Fclose(64) at PC 0xEF7A
#
# The OPCODE sits between "GEMDOS" and the name, so the name is the THIRD field; a parser that took
# the second matched nothing and `check_trap_ledger` compared [] against [] and reported green. Note
# also that `Fopen` ends "PC=0x…" and `Fread`/`Fclose` end "PC 0x…" — a scan for "the first number
# after the name" therefore returns a call-site ADDRESS for some calls and an argument for others,
# which is why this takes the arguments from INSIDE the parentheses and nothing else.
GEMDOS_LINE = re.compile(r'^GEMDOS 0x[0-9A-Fa-f]+ (\w+)\((.*)\) at PC')
GEMDOS_QUOTED_NAME = re.compile(r'"([^"]*)"')

# The calls whose FIRST argument is a filename, and the ones whose first argument is a handle.
GEMDOS_BY_NAME = ("Fopen", "Fcreate")
GEMDOS_BY_HANDLE = ("Fread", "Fwrite", "Fclose")


def gemdos_calls(trace_path, drop_names=()):
    """The file-I/O sequence in a `--trace gemdos` log, as tuples two runs can be compared on.

    WHAT IS COMPARED AND WHAT IS DELIBERATELY NOT. An open is compared by FILENAME, a read or write
    by (handle, byte count), a close by handle. The BUFFER ADDRESS is dropped on purpose: ours is
    inside a 1 MiB array GEMDOS placed and the original's is absolute RAM, so it is the one argument
    the two programs cannot agree on by construction. The handle is kept because a `Fread` on handle
    0 is exactly the GEMDOS-HD defect `zynaps_os.s`'s wrapper order exists to avoid.

    `drop_names` removes the calls that are not the GAME's — see NON_GAME_FILES. A dropped open's
    reads and closes go with it, tracked by the fact that both programs hold ONE file open at a
    time (`load_file` opens, reads and closes in one go), which `check_trap_ledger` asserts rather
    than assumes.
    """
    calls = []
    skipping = False
    for line in Path(trace_path).read_text(errors="replace").splitlines():
        match = GEMDOS_LINE.match(line)
        if not match:
            continue
        name, arguments = match.group(1), match.group(2)
        if name in GEMDOS_BY_NAME:
            quoted = GEMDOS_QUOTED_NAME.search(arguments)
            opened = Path(quoted.group(1)).name.upper() if quoted else "?"
            skipping = opened in drop_names
            if not skipping:
                calls.append((name, opened))
        elif name in GEMDOS_BY_HANDLE:
            if skipping:
                continue
            calls.append((name, *_arguments(arguments)[:2]))
    return calls


def _arguments(arguments):
    """The comma-separated arguments of a traced call, as numbers where they are numbers."""
    parsed = []
    for field in arguments.split(","):
        field = field.strip()
        try:
            parsed.append(int(field, 0))
        except ValueError:
            parsed.append(field)
    return parsed


def tick_frames(trace_path):
    """The sound driver's own tick frames in a psg_write trace — see ref_capture.TraceReader."""
    reader = ref_capture.TraceReader(trace_path)
    reader.update()
    return reader.frames


def title_picture_pens():
    """Which pens the title picture actually uses, decoded off ZYNPIC.PIC.

    The negative control corrupts ONE pen and requires the rendered picture to change; a pen that
    happened not to appear on screen would make that arm fail for a reason about coverage rather
    than about the fault. So the pen the binary reports is checked against this set.
    """
    picture = (ORIGINAL_DISK / "ZYNPIC.PIC").read_bytes()[:SCREEN_BYTES]
    rows = st_pixels.decode_planar(picture, SCREEN_PIXELS_WIDE, SCREEN_ROWS)
    return {pen for row in rows for pen in row if pen >= 0}


# =================================================================================================
# The checks. Each returns a list of complaints; empty means it passed.
# =================================================================================================
def check_exit_and_log(name, side):
    """SURFACE: exit status and the log. See FAULT_MARKERS for why the markers are passed in."""
    problems = [f"{name}: Hatari logged: {line}"
                for line in log_faults(side["log"], markers=FAULT_MARKERS)
                if not TOS_ROM_PC.search(line)]
    if side["status"] != 0:
        problems.append(f"{name}: Hatari exited with status {side['status']}")
    return problems


def check_the_fault_scan_can_fail():
    """...and that the scan above is not the vacuous thing it replaced.

    A marker list that matches nothing looks exactly like a clean log — which is how the wrong
    casing survived into a green run of this very file. So the scan is run over a line Hatari really
    printed (from this directory's own log) and must name it, and over the ROM's harmless probe and
    must not. It costs a tempfile and it is the only reason a green log line means anything.
    """
    real = "WARN : Bus Error writing at address $12345, PC=$00012a\n"
    rom = "WARN : Bus Error writing at address $41fffe, PC=$fc0174\n"
    with tempfile.TemporaryDirectory() as work:
        probe = Path(work) / "faults.log"
        probe.write_text(real + rom)
        named = [line for line in log_faults(probe, markers=FAULT_MARKERS)
                 if not TOS_ROM_PC.search(line)]
    if len(named) != 1 or "PC=$00012a" not in named[0]:
        return [f"the fault scan named {named} over one real bus error and one ROM probe — it "
                f"cannot tell them apart, and a clean log from it would mean nothing"]
    return []


def check_the_program_finished(ours):
    """SURFACE: exit status and the log — the program's own half of it.

    A complete record with its 'DONE' tail says the whole of `zynaps_main` ran, teardown included;
    `read_record` has already refused anything less. What is left is that each step it reports
    actually happened, which is what these read-backs are.
    """
    record = ours["record"]
    problems = []
    if record["program_staged_bytes"] != len(gen_image_bytes()):
        problems.append(f"staged {record['program_staged_bytes']} bytes of the program, "
                        f"{len(gen_image_bytes())} were on the drive")
    if record["super_token"] != OS_SUPER_TOKEN:
        problems.append(f"boot_enter_supervisor answered {record['super_token']:#x}, "
                        f"not the model's {OS_SUPER_TOKEN:#x}")
    # RUNNING TOTALS, one per command: the shim reads `zy_acia_bytes_sent` after each of the boot's
    # two `ikbd_send_cmd` calls, so the pair is 1 then 2. It is a count and not a verdict because the
    # core's spin is unbounded on target exactly as the original's is (shim_include/tos.h) — a
    # transmitter that never empties never returns, and the finding is then a run that produced no
    # STATE.BIN at all rather than a 0 in this field.
    #
    # SO BE HONEST ABOUT WHAT IT PINS. `ikbd_send_cmd` has ONE return path on target, taken straight
    # after the store, so "returned without storing" is not a state these two can be in. What they
    # do hold is that the boot made exactly TWO of them, in order, and that `note_store`'s ACIA key
    # (shim_include/hw.h) names the register the core actually wrote — the same cross-check the
    # shifter-mode and palette tallies get from their own asserted counts.
    boot_commands = ("acia_bytes_after_mouse_off", "acia_bytes_after_joystick_mode")
    assert len(boot_commands) == IKBD_BOOT_COMMANDS
    for sent, command in enumerate(boot_commands, start=1):
        if record[command] != sent:
            problems.append(f"{command}: {record[command]} command byte(s) had reached $fffc02, "
                            f"expected {sent} — a call returned without sending")
    if record["psg_refused"]:
        problems.append(f"{record['psg_refused']} PSG writes named a register outside 0..15")
    if not record["psg_writes"]:
        problems.append("the sound driver never wrote the chip — no music")
    if record["screen_bytes_written"] != SCREEN_BYTES:
        problems.append(f"the framebuffer dump was {record['screen_bytes_written']} bytes")
    # The cross-language pin: `zy_anchor` must still be standing when the shot is taken, or the
    # picture would be of the teardown. Neither language can import the other's number.
    if record["anchor_hold_vbls"] <= ANCHOR_SETTLE_VBLS:
        problems.append(f"the shim holds its anchor for {record['anchor_hold_vbls']} vblanks and "
                        f"this file photographs {ANCHOR_SETTLE_VBLS} later — the capture races the "
                        f"teardown")
    if record["smoke_vbls"] > record["vbl_ticks_at_anchor"]:
        problems.append(f"the anchor was reached at {record['vbl_ticks_at_anchor']} vblanks, before "
                        f"the {record['smoke_vbls']} it was compiled to wait for")
    return problems


def check_the_boot_slice_did_its_work(ours):
    """SURFACE: memory, plus the two off-image ledgers the CORES keep.

    EVERY FIELD HERE WAS PUBLISHED AND JUDGED BY NOTHING until this check existed, which is the
    "present and vacuous" shape smoke.py's own docstring is written against. Each row below is a
    claim some comment in zynaps_main.c already made; this is where the claim is measured.
    """
    record = ours["record"]
    problems = []

    # `boot_save_vbl_vector` (0x10012) copies image[0x70] to image[0x195d0]. The shim seeded the
    # first from the REAL vector, so this is the only evidence on any surface that the slice ran —
    # and the seed is a value nothing else in the image holds.
    if record["image_saved_vbl_vector"] != record["tos_vbl_vector"]:
        problems.append(f"boot_save_vbl_vector left {record['image_saved_vbl_vector']:#x} at "
                        f"image[0x195d0], not the {record['tos_vbl_vector']:#x} it was given")

    # `screen_flip_buffers` SWAPS the two hard-coded pointers, so after the boot's one flip the back
    # buffer is what started as the front and vice versa. ../src/init.c's BOOT_SCREEN_* are the two
    # constants; the swap is what this compares.
    if (record["image_screen_back"], record["image_screen_front"]) != (GAME_SCREEN_FRONT,
                                                                      GAME_SCREEN_BACK):
        problems.append(f"the framebuffer pointers are back={record['image_screen_back']:#x} "
                        f"front={record['image_screen_front']:#x}; after the boot's one flip they "
                        f"should be {GAME_SCREEN_FRONT:#x} / {GAME_SCREEN_BACK:#x}")

    # THE TWO STORES THE CORES MAKE THAT THE MACHINE CANNOT BE ASKED ABOUT AFTERWARDS, counted at
    # the hardware door (shim_include/hw.h). Off target the kit's ordered write ledger holds both;
    # here they are counts, and each is keyed on something the shim's own traffic cannot forge — the
    # resolution byte's address, and the LONGWORD width of `set_palette_title`'s `movem` upload.
    #
    # `palette_long_writes` is the arm that stops a deleted `set_palette_title` call being green:
    # the upload writes no image byte, so before there was a ledger, deleting it left the whole
    # differential passing. A short upload (seven longs) is a red here for the same reason.
    if record["palette_long_writes"] != SHIFTER_PALETTE_PAIRS:
        problems.append(f"the slice put {record['palette_long_writes']} longwords into the colour "
                        f"block, and `set_palette_title`'s movem is {SHIFTER_PALETTE_PAIRS}")
    if record["shifter_mode_writes"] != 1 or record["shifter_mode_mask"] != SHIFTER_MODE_MASK:
        problems.append(f"the boot made {record['shifter_mode_writes']} store(s) to $ff8260 with "
                        f"mask {record['shifter_mode_mask']:#x}, not 1 with "
                        f"{SHIFTER_MODE_MASK:#x} — and reading $ff8260 back cannot say so, because "
                        f"TOS boots this machine in low resolution anyway")

    # The file seam's own counters (shim_include/os.h). `load_file` has NO error handling, so a
    # missing data file would leave a zeroed buffer and every other surface green — M1 draws none of
    # the four files whose absence would show.
    if record["file_opens"] != BOOT_FILE_OPENS:
        problems.append(f"the cores made {record['file_opens']} opens through the seam, and "
                        f"boot_load_title_assets makes {BOOT_FILE_OPENS}")
    if record["file_open_failures"]:
        problems.append(f"{record['file_open_failures']} of those opens FAILED — a data file is "
                        f"missing from the drive and the buffer it feeds is zeroed")
    if record["file_refusals"]:
        problems.append(f"the seam refused {record['file_refusals']} transfer(s) for leaving the "
                        f"1 MiB image — a destination address or a length is wrong")

    # Two more that only say the run did what it says: the machine was actually written to, and
    # every chip write the driver made went through the counted path.
    injected = 0 if record["fault_pen"] == NO_FAULT_PEN else FAULT_HW_WRITES
    expected_hw = (PSG_PORTS_PER_WRITE * record["psg_writes"]
                   + CORE_HW_WRITES + SHIM_HW_WRITES + injected)
    if record["hw_writes"] != expected_hw:
        problems.append(f"{record['hw_writes']} hardware stores, expected {expected_hw} "
                        f"({PSG_PORTS_PER_WRITE} ports x {record['psg_writes']} PSG writes + "
                        f"{CORE_HW_WRITES} the cores make + {SHIM_HW_WRITES} the shim makes"
                        + (f" + {injected} injected)" if injected else ")"))
    if record["raw_video_base_at_anchor"] != record["published_screen_base"]:
        problems.append(f"the shifter's own two bytes read back "
                        f"{record['raw_video_base_at_anchor']:#x} against the "
                        f"{record['published_screen_base']:#x} published")
    return problems


def check_the_machine_was_handed_back(ours):
    """SURFACE: exit status and the log — the teardown's read-backs.

    Anything installed into TOS outlives the process. Each of these is a write this shim made,
    read back after it was undone; the emulator running on past the exit is the other half.
    """
    record = ours["record"]
    problems = []
    for what, before, after in (("the vertical-blank vector", "tos_vbl_vector", "vbl_vector_after"),
                                ("the Timer B vector", "tos_timer_b_vector", "timer_b_vector_after")):
        if record[before] != record[after]:
            problems.append(f"{what} came back as {record[after]:#x}, TOS had {record[before]:#x}")
    # Physbase has no "before" to equal — TOS's own screen moves when Setscreen resets the mode — so
    # what it can say is that it is no longer OURS.
    if record["physbase_after"] == record["physbase_at_anchor"]:
        problems.append("Physbase after the teardown still names OUR framebuffer — Setscreen did "
                        "not put TOS's screen back")
    if pens_from_record(record, "pen_after") != pens_from_record(record, "pen_at_entry"):
        problems.append("the sixteen pens did not come back to what TOS had")
    # THE RESOLUTION, and it is the one hand-back step with a wholly unverified wrapper under it:
    # `Setscreen`'s third argument is a `short` in a 4-byte slot, and reading the wrong half of that
    # slot is the exact ABI defect docs/on-target-execution.md class 3 is written from. Without this
    # row, TOS comes back in the wrong screen mode and every check stays green.
    if record["rez_after"] != TOS_BOOT_REZ:
        problems.append(f"$ff8260 reads {record['rez_after']} after the teardown; TOS booted this "
                        f"machine in {TOS_BOOT_REZ} and Setscreen was given that back")
    return problems


def check_the_original_was_anchored_on_its_boot(original):
    """The ORIGINAL side's own soundness, and it is not optional.

    The original is anchored on a STATE — its last colour register holding the boot palette's last
    pen — which is true from `set_palette_title` at 0x10084 until its front end changes the palette
    about twenty seconds later. That is deliberately a WINDOW rather than an instant, so the run has
    to say it landed at the near end of it: all sixteen registers holding the shipped boot palette
    is what only the boot produces. In the front end they do not — the title handlers blank pen 0
    every frame and cycle pens 6..12 — which is exactly how a first draft's mis-anchor announced
    itself, and this is that diagnosis turned into a check.
    """
    theirs = pens_from_dump((original["work"] / DUMP_PENS).read_bytes())
    expected = boot_palette()
    if theirs == expected:
        return []
    differing = [pen for pen in range(PALETTE_PENS) if theirs[pen] != expected[pen]]
    return [f"the original's pens at its anchor are not the shipped boot palette (differ at "
            f"{differing}: {[hex(theirs[pen]) for pen in differing]} against "
            f"{[hex(expected[pen]) for pen in differing]}) — it was photographed somewhere other "
            f"than its title screen, and every comparison against it is meaningless"]


def check_trap_ledger(ours, original):
    """SURFACE: the trap ledger."""
    ours_calls = gemdos_calls(ours["trace"], drop_names=NON_GAME_FILES)
    original_calls = gemdos_calls(original["trace"], drop_names=NON_GAME_FILES)

    # THE FLOOR, and it is not decoration. A prefix comparison of two lists is trivially true when
    # ours is empty, so a parser that stops matching — a Hatari upgrade, a renamed trace flag, a
    # truncated file — turns the only check on the eight file loads into a permanent green. That is
    # not hypothetical: it is what this file did until the parser was measured against a real trace.
    opens = sum(1 for call in ours_calls if call[0] == "Fopen")
    if opens != BOOT_FILE_OPENS:
        return [f"our GEMDOS ledger holds {opens} game opens and `boot_load_title_assets` makes "
                f"{BOOT_FILE_OPENS} ({len(ours_calls)} calls parsed, {len(original_calls)} on the "
                f"original's side) — the parser or the boot slice moved"]
    # The original's ledger runs on past the anchor into the rest of its boot; ours stops there. So
    # the comparison is a PREFIX one, and its length is our own call count — which is the whole of
    # our slice, so nothing of ours goes unexamined.
    head = original_calls[:len(ours_calls)]
    if ours_calls == head:
        return []
    for index, (mine, theirs) in enumerate(zip(ours_calls, head)):
        if mine != theirs:
            return [f"the GEMDOS ledger diverges at call {index}: ours {mine}, the original's "
                    f"{theirs} (of {len(ours_calls)} ours / {len(original_calls)} theirs)"]
    return [f"the GEMDOS ledgers are different lengths: ours {len(ours_calls)}, the original's "
            f"first slice {len(head)}"]


def check_hardware_state(ours, original):
    """SURFACE: the hardware-state vector."""
    record = ours["record"]
    problems = []
    our_pens = pens_from_dump((ours["work"] / DUMP_PENS).read_bytes())
    their_pens = pens_from_dump((original["work"] / DUMP_PENS).read_bytes())

    if our_pens != their_pens:
        differing = [pen for pen in range(PALETTE_PENS) if our_pens[pen] != their_pens[pen]]
        problems.append(f"the pens differ at {differing}: ours "
                        f"{[hex(our_pens[pen]) for pen in differing]}, the original's "
                        f"{[hex(their_pens[pen]) for pen in differing]}")
    # ...and the program's own read-back must agree with the debugger's. Two independent readers of
    # the same sixteen registers; either alone could be reading something else.
    if pens_from_record(record, "pen_at_anchor") != our_pens:
        problems.append("the program read the pens back differently from the debugger — one of the "
                        "two is not reading the shifter")

    our_rez = (ours["work"] / DUMP_REZ).read_bytes()[0] & RESOLUTION_MASK
    their_rez = (original["work"] / DUMP_REZ).read_bytes()[0] & RESOLUTION_MASK
    if our_rez != their_rez or our_rez != REZ_LOW:
        problems.append(f"$ff8260: ours {our_rez}, the original's {their_rez}, low res is {REZ_LOW}")
    if record["rez_at_anchor"] != our_rez:
        problems.append("the program and the debugger disagree about $ff8260")

    # THE VIDEO BASE IS THE ONE THING THAT CANNOT BE EQUAL, and the check is a RELATION rather than
    # an equality: the original displays its framebuffer at the absolute address it hard-codes, and
    # ours displays the same offset inside a 1 MiB array GEMDOS placed. What must hold is that each
    # side displays its own `screen_back`, and — the part class 8 is about — that no low byte was
    # lost on the way to a register that has none.
    our_base = video_base(ours["work"])
    their_base = video_base(original["work"])
    if their_base != GAME_SCREEN_BACK:
        problems.append(f"the original's shifter reads {their_base:#x}, not its own "
                        f"screen_back {GAME_SCREEN_BACK:#x}")
    if our_base != record["image_base"] + GAME_SCREEN_BACK:
        problems.append(f"our shifter reads {our_base:#x}, not image base {record['image_base']:#x} "
                        f"+ screen_back {GAME_SCREEN_BACK:#x}")
    if record["physbase_at_anchor"] != record["published_screen_base"]:
        problems.append(f"Physbase reads back {record['physbase_at_anchor']:#x} against the "
                        f"{record['published_screen_base']:#x} that was published — the address was "
                        f"TRUNCATED (docs/on-target-execution.md class 8)")
    return problems


def video_base(work):
    """The address the shifter is displaying from, out of its two bytes. It has no third."""
    high = (work / DUMP_BASE_HIGH).read_bytes()[0]
    mid = (work / DUMP_BASE_MID).read_bytes()[0]
    return (high << 16) | (mid << 8)


def check_rendered_pixels(ours, original):
    """SURFACE: rendered pixels."""
    problems = []
    for name, side in (("ours", ours), ("the original's", original)):
        colours = distinct_colours(side["shot"])
        if colours <= BLANK_COLOUR_COUNT:
            problems.append(f"{name} capture holds {colours} colour — the screen was blank")
    if problems:
        return problems
    if not same_picture(ours["shot"], original["shot"]):
        from PIL import Image
        with Image.open(ours["shot"]) as mine, Image.open(original["shot"]) as theirs:
            mine, theirs = mine.convert("RGB").tobytes(), theirs.convert("RGB").tobytes()
        differing = sum(1 for a, b in zip(mine, theirs) if a != b)
        problems.append(f"the rendered pictures differ in {differing} of {len(mine)} colour bytes")
    return problems


def check_memory(ours, original):
    """SURFACE: memory."""
    if ours["screen"] == original["screen"]:
        return []
    differing = sum(1 for a, b in zip(ours["screen"], original["screen"]) if a != b)
    return [f"the framebuffers differ in {differing} of {len(ours['screen'])} bytes "
            f"(ours {len(ours['screen'])}, the original's {len(original['screen'])})"]


def check_timeline(ours, original):
    """SURFACE: timelines.

    THE ALIGNMENT RULE, and it is why this compares a SHAPE. Both runs write the chip only from the
    sound driver's per-frame flush, which pushes registers 10..0 in that order and is the only thing
    that does — so a trace is cut into frames on that descending run, and frame 0 is each side's
    FIRST one whatever the boot did before it. The two boots do not agree on when frame 0 falls:
    the original installs its vertical-blank vector in the middle of the boot slice and ticks
    through all eight file loads, while this build installs it after the slice returns
    (zynaps_main.c says why, at length). What must be identical is the frames themselves.
    """
    ours_frames = tick_frames(ours["trace"])
    original_frames = tick_frames(original["trace"])
    if len(ours_frames) < TICK_FRAMES_COMPARED:
        return [f"only {len(ours_frames)} of our tick frames reached the trace, needed "
                f"{TICK_FRAMES_COMPARED} — the driver is not running at 50 Hz"]
    if len(original_frames) < TICK_FRAMES_COMPARED:
        return [f"only {len(original_frames)} of the original's tick frames reached the trace"]
    for index in range(TICK_FRAMES_COMPARED):
        if ours_frames[index] != original_frames[index]:
            return [f"the register streams diverge at tick frame {index}: ours "
                    f"{sorted(ours_frames[index].items())}, the original's "
                    f"{sorted(original_frames[index].items())}"]
    return []


# =================================================================================================
# The negative control
# =================================================================================================
def check_the_fault_is_the_one_claimed(ours):
    """The control's own soundness: the binary must say it injected a fault, at a visible pen.

    The pen comes from the RECORD and never from a scrape of build.sh — the per-mode .PRGs outlive
    an edit to that script, so a scraped number could name a pen the running binary never touched.
    """
    pen = ours["record"]["fault_pen"]
    if pen == NO_FAULT_PEN:
        return ["the control build reports no injected fault — it was built without ZY_FAULT_PEN"]
    if pen >= PALETTE_PENS:
        return [f"the injected fault names pen {pen}, and there are {PALETTE_PENS}"]
    on_screen = title_picture_pens()
    if pen not in on_screen:
        return [f"pen {pen} is not used by ZYNPIC.PIC (it uses {sorted(on_screen)}), so the "
                f"rendered-picture arm of this control would fail for lack of coverage rather "
                f"than because of the fault"]
    return []


def check_only_the_faulted_pen_moved(ours, original):
    """...and the fault must be exactly one pen, so the control is about colour and nothing else."""
    pen = ours["record"]["fault_pen"]
    our_pens = pens_from_dump((ours["work"] / DUMP_PENS).read_bytes())
    their_pens = pens_from_dump((original["work"] / DUMP_PENS).read_bytes())
    differing = [index for index in range(PALETTE_PENS) if our_pens[index] != their_pens[index]]
    if differing != [pen]:
        return [f"the control moved pens {differing} and it claims to have faulted only {pen}"]
    return []


# =================================================================================================
# Housekeeping the checks depend on
# =================================================================================================
def gen_image_bytes():
    """The staged program image, so `program_staged_bytes` is compared against a measurement."""
    return (OUR_DISK / "ZYNAPS.IMG").read_bytes()


def assert_machine_and_rom_agree(machine, rom):
    """Refuse a machine the ROM cannot drive, before three minutes of emulation say so obliquely.

    boot_shots.py refuses the GEMDOS-drive-under-TOS-1.02 combination the same way and for the same
    reason (../../README.md): a combination the emulator quietly rewrites produces a run that looks
    like a timeout, and the diagnosis is a line in a log nobody was told to read.
    """
    version, = struct.unpack(">H", rom.read_bytes()[TOS_VERSION_OFFSET:
                                                    TOS_VERSION_OFFSET + TOS_VERSION_BYTES])
    if machine != DEFAULT_MACHINE and version <= LAST_ST_ONLY_TOS:
        raise SystemExit(f"{rom.name} is TOS {version >> 8}.{version & 0xff:02x} and Hatari runs "
                         f"TOS <= {LAST_ST_ONLY_TOS >> 8}.{LAST_ST_ONLY_TOS & 0xff:02x} in ST mode "
                         f"only — it would switch back to `st` and report on a machine you did not "
                         f"ask for. `--machine {machine}` needs TOS 1.06 or later, or EmuTOS.")
    return version


def assert_the_shim_owns_these_names():
    """SHIM_FILES must be exactly zynaps_main.c's four FILE_* constants.

    The trap ledger's whole meaning rests on this list: a name here that the shim does not use would
    silently delete one of the GAME's opens from our side of the comparison, and the check would
    pass over a missing file load. So it is read out of the C rather than agreed with it.
    """
    source = SHIM_MAIN.read_text()
    declared = sorted(part.split('"')[1] for part in source.split("#define FILE_")[1:])
    if declared != sorted(SHIM_FILES):
        raise SystemExit(f"smoke.py's SHIM_FILES {sorted(SHIM_FILES)} is not zynaps_main.c's "
                         f"{declared} — the trap-ledger exclusion would edit the wrong calls")


def built_prg(mode):
    """The .PRG `build.sh <mode>` left behind, refusing a missing one by name."""
    built = HERE / "build" / f"ZYNAPS-{mode}.PRG"
    if not built.is_file():
        raise SystemExit(f"no {built} — run `bash {HERE / 'build.sh'} {mode}` first")
    return built


def stage_our_build(mode):
    """Put the mode's .PRG where Hatari will auto-run it, and refuse a stale or missing one."""
    shutil.copy(built_prg(mode), OUR_DISK / OUR_PRG_NAME)
    # The shim's own outputs from a previous run would otherwise be read as this run's.
    for name in (BASE_FILE, STATE_FILE, SCREEN_FILE):
        (OUR_DISK / name).unlink(missing_ok=True)


def stage_our_floppy(build):
    r"""Refuse a floppy image that is not the build sitting next to it.

    mkfloppy.py verifies the volume against the files it wrote; this verifies it against the files
    that exist NOW. The two are different questions, and the one that bites is this one: an image
    left over from an earlier floppy build boots and passes every surface, having tested a binary
    that is no longer on disk.

    `build` IS A PARAMETER because build.sh's medium is a flag rather than a mode (README.md's
    Unpinned 14): any mode can be written onto a floppy, so the volume's `AUTO\ZYNAPS17.PRG` has to
    be checked against the one that was, not against a name this file assumes.
    """
    if not OUR_FLOPPY.is_file():
        raise SystemExit(f"no {OUR_FLOPPY} — run `bash {HERE / 'build.sh'} {build} floppy` first")
    on_volume = floppy_file(OUR_FLOPPY, f"{mkfloppy.AUTO_DIR}/{mkfloppy.AUTO_PRG}")
    if on_volume != built_prg(build).read_bytes():
        raise SystemExit(f"{OUR_FLOPPY.name}'s {mkfloppy.AUTO_PRG} is not "
                         f"build/ZYNAPS-{build}.PRG — the image is stale, rebuild it")


# =================================================================================================
# =================================================================================================
# M2 — THE WHOLE GAME, AND THE FRAME DIFFERENTIAL THAT JUDGES IT
#
# `title` compares two programs that have only booted. This compares two programs that are PLAYING:
# the shipped 1988 binary and the reconstruction, both driven from the same anchor with the same
# input and the same random seed, at the same numbered frames of the same section.
#
# WHAT MAKES THE TWO COMPARABLE, and every one of these is a pin rather than a hope:
#
#  * THE FRAME NUMBER IS THE LOOP HEAD'S OWN PASS COUNT. One `frame_loop_once` here is one arrival
#    at 0x10f4e there, so "frame 60" means the same thing to the program's own counter and to a
#    Hatari breakpoint's hit count. Sample N is the state AFTER N passes, i.e. the original's
#    (N + 1)th arrival.
#  * THE INPUT IS THE SAME. Both sides are given the fire button — poked into the byte the ACIA
#    handler writes, because Hatari swallows a key bound to its own joystick emulation and the stick
#    cannot be pressed from outside at all (tools/hatari_headless.py's docstring records that
#    measurement; `atari/run.sh` is the discharge). Both are then RELEASED at the first arrival at
#    the loop head, before the frame's own read of the byte, so frame 1 sees a neutral stick on both.
#  * THE RANDOM STREAM IS THE SAME. `rand16` is called in the attract loop and in the fire wait, so
#    the two sides arrive at the game with different LFSR states — a different enemy on frame 1. The
#    same breakpoint parks both at the seed the .PRG ships with.
#
# WHAT IS COMPARED at each sample: the 32000-byte framebuffer the shifter is displaying, the
# sixteen colour registers read off the chip, and the twenty entity records. The entity table's
# SPRITE POINTERS are rebased before the compare — they are absolute on both sides and the two
# programs load at different addresses — and `entity_problems` says exactly which bytes it excused.
# =================================================================================================
GAME_MODE = "game"
GAME_FAULT_MODE = "gamefault"

# ../include/frame.h's loop head: `bra.w $10f4e` at 0x1296a comes back here once a frame.
GHIDRA_FRAME_LOOP_HEAD = 0x10F4E
# ../include/irq.h's `A_joystick_state` — joystick 1, fire in bit 7, written by `ikbd_acia_isr`.
GHIDRA_JOYSTICK_STATE = 0x19681
JOYSTICK_FIRE = 0x80
JOYSTICK_NEUTRAL = 0
# The two polls the ORIGINAL reads the joystick byte at, and nowhere else: `tst.b $19681` in
# `section_start_tail`'s PREPARE FOR COMBAT wait and in `title_attract_loop`'s menu
# (../src/init.c's SECTION_TAIL_FIRE_WAIT_SITE and ATTRACT_FIRE_WAIT_SITE, which the reconstruction
# already names because the off-target model counts polls per site).
GHIDRA_SECTION_TAIL_FIRE_POLL = 0x10F2A
GHIDRA_ATTRACT_FIRE_POLL = 0x12C5E
# How many arrivals at one of those polls between presses. Each pass of the wait sends an IKBD
# command, so the loop is thousands of cycles and this is a press every few milliseconds — often
# enough that the wait leaves promptly, rare enough that the debugger is not entered in a spin.
FIRE_POLLS_PER_PRESS = 20
# ../include/rng.h: the 32-bit LFSR and the seed the shipped .PRG carries.
GHIDRA_RNG_STATE = 0x195F4
RNG_SHIPPED_SEED = 0x83E4F2B3
# ../include/player.h / ../include/entity.h / ../include/frame.h — the twenty records the loop drives.
GHIDRA_ENTITY_TABLE = 0x17A8E
ENTITY_SLOTS = 20
ENTITY_STRIDE = 0x2C
ENTITY_SPRITE_OFFSET = 0x0A
ENTITY_SPRITE_BYTES = 4
ENTITY_TABLE_BYTES = ENTITY_SLOTS * ENTITY_STRIDE
# How many differing bytes the message spells before it starts counting instead. Enough
# for a whole record's worth of fields; past that the list is noise and the number is the
# finding.
ENTITY_DIFF_REPORTED = 12
# ../include/video.h's screen pointer pair, as one range: which buffer the original was displaying.
GHIDRA_SCREEN_POINTERS = 0x1797E
SCREEN_POINTER_BYTES = 8
# `zynaps_main.c`'s own phases, in its enum's order. The record carries the number.
PHASE_PLAYING = 6
PHASE_BUDGET_SPENT = 7
PHASE_NAMES = ("staging", "title assets", "gameplay assets", "attract", "front-end screens",
               "section start", "playing", "budget spent", "halted")
# How long to hold the fire button before giving up on the game ever starting.
FIRE_DEADLINE_SECONDS = 300.0
FIRE_POKE_SECONDS = 0.2
# A WHOLE GAME NEEDS A BIGGER BUDGET THAN A TITLE SCREEN, and the number is a measurement rather
# than a guess: at 12000 the run reached frame 120 of 240 and Hatari quit under it, having spent
# most of its vertical blanks in the attract loop and the PREPARE FOR COMBAT wait while the driver
# poked the fire button. This is that with room for the original's slower start.
GAME_RUN_VBLS = 80000


def c_define(source, name):
    """One `#define <name> <value>` from a C source, as an int.

    CLAUDE.md §5: "when the same value must agree in two places that can't import each other, pick
    one canonical definition and pin the other equal with a test". The canonical definition of every
    address below is the reconstruction's own header; this is the import, so a header that moves one
    breaks the run at the parse with both spellings named instead of comparing the wrong bytes.
    """
    marker = f"#define {name} "
    if marker not in source:
        raise SystemExit(f"no `{marker.strip()}` to read — smoke.py names a constant its header "
                         f"no longer defines")
    value = source[source.index(marker) + len(marker):].split()[0]
    return int(value.rstrip("uU").rstrip(","), 0)


def assert_the_game_constants_are_the_headers(headers=None):
    """Every Ghidra address and record geometry this mode uses, checked against its owning header.

    The frame differential reads the ORIGINAL's RAM at addresses computed from these, so one that
    had drifted would compare two unrelated ranges and could still come out green on a quiet slot.
    """
    read = headers or (lambda name: (RECREATE / name).read_text())
    # THE TWO POLL SITES ARE IN THE .c AND NOT THE .h, and that is the reconstruction's own choice:
    # they are `sched_poll8`'s site identifiers, which only the routine that polls has a use for.
    for constant, owner, define in (
            (GHIDRA_JOYSTICK_STATE, "include/irq.h", "A_joystick_state"),
            (GHIDRA_RNG_STATE, "include/rng.h", "A_rng_lfsr_state"),
            (GHIDRA_ENTITY_TABLE, "include/player.h", "A_entity_table"),
            (ENTITY_STRIDE, "include/entity.h", "ENTITY_STRIDE"),
            (ENTITY_SPRITE_OFFSET, "include/entity.h", "ENTITY_SPRITE"),
            (ENTITY_SLOTS, "include/frame.h", "ENTITY_SLOTS"),
            (GHIDRA_SCREEN_POINTERS, "include/video.h", "A_screen_back"),
            (GHIDRA_SECTION_TAIL_FIRE_POLL, "src/init.c", "SECTION_TAIL_FIRE_WAIT_SITE"),
            (GHIDRA_ATTRACT_FIRE_POLL, "src/init.c", "ATTRACT_FIRE_WAIT_SITE"),
            (ATTRACT_TIMER_B_PERIOD, "include/init.h", "MFP_TIMER_B_PERIOD_ATTRACT_BARS"),
            (PACING_RELEASE_PERIOD_VBLS, "include/irq.h", "RASTER_PHASE_PERIOD")):
        theirs = c_define(read(owner), define)
        if constant != theirs:
            raise SystemExit(f"smoke.py has {define} = {constant:#x}, ../{owner} has {theirs:#x} — "
                             f"the checks built on it would read the wrong range or divide by the "
                             f"wrong denominator")


def assert_the_phase_names_are_the_shims():
    """...and the same for `zynaps_main.c`'s phase enum, which the record carries as a NUMBER.

    `phase_reached` is an ordinal, so a phase inserted in the middle of that enum renames every one
    after it and this file would report the run stopping somewhere it did not.
    """
    source = SHIM_MAIN.read_text()
    marker = "enum zy_phase_reached {"
    body = source[source.index(marker) + len(marker):source.index("};", source.index(marker))]
    declared = [line.split("/*")[0].split("=")[0].strip().rstrip(",")
                for line in body.splitlines()
                if line.strip().startswith("PHASE_")]
    ours = [f"PHASE_{name.upper().replace(' ', '_').replace('-', '_')}" for name in PHASE_NAMES]
    if declared != ours:
        raise SystemExit(f"zynaps_main.c's phases are {declared} and smoke.py's are {ours} — "
                         f"`phase_reached` is an ordinal and would name the wrong one")
    if PHASE_NAMES[PHASE_PLAYING] != "playing" or PHASE_NAMES[PHASE_BUDGET_SPENT] != "budget spent":
        raise SystemExit("smoke.py's PHASE_PLAYING / PHASE_BUDGET_SPENT do not index their own "
                         "names — the two constants and the list have drifted apart")
    # ...and the pacing histogram's width, for the same reason one field further on: the record is
    # positional, so a slot added there and not here shifts every field after it. The length guard
    # in `read_record` would catch that, but it would report "the field count moved" rather than
    # naming the constant that moved it.
    theirs = c_define(source, "PACING_SLOTS")
    if PACING_SLOTS != theirs:
        raise SystemExit(f"smoke.py has PACING_SLOTS = {PACING_SLOTS} and zynaps_main.c has "
                         f"{theirs} — the pacing histogram's fields would be misread")


def frame_samples():
    """The sample frames, read out of zynaps_main.c's own `ZY_FRAME_SAMPLES`.

    PINNED ACROSS THE LANGUAGE BOUNDARY rather than agreed with it (CLAUDE.md §5): the binary dumps
    FRAME<i>.BIN for the i-th entry of that list and this side arms the original's breakpoints from
    the same list, so a frame added there and not here would compare two different frames under the
    same name.
    """
    source = SHIM_MAIN.read_text()
    marker = "#define ZY_FRAME_SAMPLES "
    line = source[source.index(marker) + len(marker):].splitlines()[0]
    samples = [int(part.strip().rstrip("uU"), 0) for part in line.split(",")]
    if not samples or sorted(samples) != samples:
        raise SystemExit(f"zynaps_main.c's ZY_FRAME_SAMPLES is {samples} — the smoke needs an "
                         f"ascending, non-empty list to arm one breakpoint per sample")
    return samples


def runtime(base, ghidra):
    """A Ghidra address at the address the ORIGINAL was relocated to."""
    return base + ghidra - LOAD_BASE


def press_fire_only_in_a_wait(session, finished, doing, press=None):
    """Let the run proceed, pressing fire ONLY while the program is waiting for it.

    The byte is poked rather than pressed because Hatari swallows a key bound to its keyboard-as-
    joystick emulation — measured, and recorded in tools/hatari_headless.py. So this is
    docs/on-target-execution.md class 12 by construction on BOTH sides: the gate is crossed by a
    poke, and the input path behind it (a 6301 report parsed by `ikbd_acia_isr`) is exercised by the
    run but is not what opens the gate.

    THE PRESS MUST NEVER REACH A FRAME, and a first draft that poked on a wall-clock timer did:
    the frame loop interrogates the controller once a frame, so a poke landing between the loop
    head's release and the stage's own read gave one side a shot the other did not fire — measured
    as a framebuffer that differed by 12 bytes at frame 30 in one run and 24 in the next, which is a
    NON-DETERMINISTIC comparison and worth nothing. So each side presses from somewhere that only
    exists inside a wait: the original from a repeating breakpoint on the poll at 0x10f2a, ours from
    a driver that reads the program's own phase and presses only when it is not PLAYING.

    IT KEEPS PRESSING AFTER THE GAME HAS STARTED, which is not laziness: the ship dies (measured at
    frame 176 of a neutral-stick life with the front end's leftovers in the entity table), the
    frame loop takes its RESTART exit, and
    `section_start_tail` asks for the fire button again. A driver that let go after the first start
    parked the run in that wait for ever with four of its five samples taken.
    """
    deadline = time.monotonic() + FIRE_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        if finished():
            return
        session.require_alive(doing)
        if press is not None:
            press()
        session.wait(FIRE_POKE_SECONDS)
    raise SystemExit(f"the run did not finish in {FIRE_DEADLINE_SECONDS:.0f} s — {doing}")


def start_of_play_action(work, name, rng_address, entity_address, marker):
    """The action file both sides run at their FIRST arrival at the frame loop's head.

    TWO PINS, and both exist because the two sides reach the loop head through DIFFERENT front ends.

    * The RANDOM STREAM. `rand16` is called once a pass in the attract loop and once a pass in the
      fire wait, and the two sides make different numbers of both, so they would arrive with
      different LFSR states — a different enemy on frame 1.
    * The ENTITY TABLE, which is the front end's scratch as well as the frame loop's. MEASURED: with
      the RNG pinned and this not, entity record 0 differed at five bytes from frame 30 onwards and
      then never moved again — `A_entity_table`'s first record is what the front end draws its
      GUNSIGHT through (`../include/highscore.h`), and our attract loop leaves it in a different
      state because it exits after one pass where the original's runs until the driver presses fire
      (README.md's M2 unpinned 19). The frame loop's own `section_restart_prologue` clears each
      record's ALIVE byte and nothing else, so the rest of that scratch survives into the game.
    * Neither pin is applied PER FRAME. The state has to EVOLVE identically from the loop head, and
      re-applying either every frame would hide exactly the divergence this comparison is for.

    ZEROING IS NOT FABRICATION HERE, and the distinction matters: it makes the two sides' STARTING
    state equal without inventing a value either program could not have — an all-zero table is what
    a machine that had just booted holds, and it is a superset of the clearing the game's own
    section start does. What it does NOT do is fix unpinned 19; it stops the front end's difference
    being reported as a frame-loop one.

    The marker is how the driver sees the game start.
    """
    return action_file(work, name,
                       f"w l ${rng_address:x} ${RNG_SHIPPED_SEED:x}",
                       f"loadbin {zero_blob(work, ENTITY_TABLE_BYTES)} ${entity_address:x}",
                       f"savebin {marker} ${A_VECTOR_VBL:x} ${VECTOR_BYTES:x}")


def zero_blob(work, length):
    """A file of `length` zero bytes for the debugger's `loadbin` — one per length, reused."""
    path = Path(work) / f"zero{length}.bin"
    if not path.is_file():
        path.write_bytes(bytes(length))
    return path


def release_action(work, name, joystick_address):
    """...and the one that runs at EVERY arrival, on a breakpoint with no `:once`.

    The frame loop reads `A_joystick_state` inside its first stage, after the loop head, so clearing
    the byte here means every frame of both runs sees a neutral stick whatever the driver is doing
    with the fire button. That is what makes the input identical rather than merely similar.
    """
    return action_file(work, name, f"w b ${joystick_address:x} ${JOYSTICK_NEUTRAL:x}")


def run_ours_game(mode, out_dir, work, machine, tos_rom):
    """Boot our .PRG, start a game, and let it run its declared budget of frames."""
    trace = out_dir / f"{mode}.trace"
    log = out_dir / f"{mode}.log"
    loop_once, anchor, image_pointer, phase_field = symbol_offsets(
        mode, "frame_loop_once", ANCHOR_SYMBOL, "zy_image_base", "g_phase")
    session = HeadlessSession(hatari_arguments(gemdos_medium(OUR_DISK, OUR_AUTO), trace,
                                               machine, tos_rom, GAME_RUN_VBLS),
                              log_path=log, fifo_path=out_dir / f"{mode}.fifo", work_dir=work)
    try:
        session.wait(BASE_POLL_START_SECONDS)
        base_file = await_file(session, OUR_DISK / BASE_FILE, "waiting for the program to start",
                               deadline_seconds=ANCHOR_DEADLINE_SECONDS)
        base = struct.unpack(">I", base_file.read_bytes()[:VECTOR_BYTES])[0] - anchor
        # The image is a .bss array whose base is a run-time fact; the shim publishes the pointer and
        # this reads it, so nothing here has to predict where GEMDOS put us.
        image = struct.unpack(">I", session.savebin("image.bin", base + image_pointer,
                                                    VECTOR_BYTES))[0]
        started = work / "OURSTART.bin"
        session.arm(f"b pc = ${base + loop_once:x} :once :quiet "
                    + start_of_play_action(work, "OURSTART.INI", image + GHIDRA_RNG_STATE,
                                           image + GHIDRA_ENTITY_TABLE, started))
        session.arm(f"b pc = ${base + loop_once:x} :quiet "
                    + release_action(work, "OURFRAME.INI", image + GHIDRA_JOYSTICK_STATE))
        record_file = OUR_DISK / STATE_FILE

        def press_if_waiting():
            """Our side's press: gated on the program's OWN phase, which is exact — `g_phase` is
            PLAYING for the whole of the frame loop and nothing else, so a poke made under this
            guard cannot land in a frame."""
            phase = struct.unpack(">I", session.savebin("phase.bin", base + phase_field,
                                                        VECTOR_BYTES))[0]
            if phase != PHASE_PLAYING:
                session.poke(image + GHIDRA_JOYSTICK_STATE, JOYSTICK_FIRE)

        press_fire_only_in_a_wait(session,
                                  lambda: record_file.is_file() and record_file.stat().st_size,
                                  "waiting for our side to play out its frame budget",
                                  press_if_waiting)
        session.wait(POST_EXIT_SECONDS)
    finally:
        status = session.close()
    samples = frame_samples()
    return {"status": status, "log": log, "trace": trace, "work": work, "base": base,
            "image": image,
            "record": read_record(OUR_DISK / STATE_FILE),
            "screen": (OUR_DISK / SCREEN_FILE).read_bytes(),
            "frames": sample_dumps(OUR_DISK, "FRAME", samples),
            "pens": sample_dumps(OUR_DISK, "PAL", samples),
            "entities": sample_dumps(OUR_DISK, "ENT", samples)}


def sample_dumps(directory, stem, samples):
    """One side's per-sample dumps, with a MISSING one read as empty rather than as a traceback.

    A run that spends its budget in a wait reaches only some of its samples, and the check written
    for exactly that — `check_the_game_ran`'s "only N frames ran" — cannot run if collecting the
    files raises first. An empty blob fails the length guards next door and names the frame.
    """
    return {frame: (directory / f"{stem}{index}.BIN").read_bytes()
                   if (directory / f"{stem}{index}.BIN").is_file() else b""
            for index, frame in enumerate(samples, 1)}


def run_original_game(out_dir, work, machine, tos_rom, samples):
    """Boot the shipped binary, start the same game, and dump the same three things per frame.

    ONE BREAKPOINT PER SAMPLE, on the loop head, with Hatari's own hit count doing the arithmetic:
    `:N` breaks on the Nth hit and `:once` retires it. Sample N is the state after N passes, so the
    breakpoint is armed for hit N + 1 — and a count of 1 is refused by Hatari, which is why the
    first arrival is a plain `:once` and carries the two pins instead.
    """
    trace = out_dir / "original.trace"
    log = out_dir / "original.log"
    session = HeadlessSession(hatari_arguments(gemdos_medium(ORIGINAL_DISK, ORIGINAL_AUTO), trace,
                                               machine, tos_rom, GAME_RUN_VBLS),
                              log_path=log, fifo_path=out_dir / "original.fifo", work_dir=work)
    try:
        base = poll_for_program(session, ORIGINAL_PRG, "waiting for the original to be loaded")
        joystick, rng = runtime(base, GHIDRA_JOYSTICK_STATE), runtime(base, GHIDRA_RNG_STATE)
        head = runtime(base, GHIDRA_FRAME_LOOP_HEAD)
        started = work / "THEIRSTART.bin"
        session.arm(f"b pc = ${head:x} :once :quiet "
                    + start_of_play_action(work, "THEIRSTART.INI", rng,
                                           runtime(base, GHIDRA_ENTITY_TABLE), started))
        session.arm(f"b pc = ${head:x} :quiet "
                    + release_action(work, "THEIRFRAME.INI", joystick))
        for index, frame in enumerate(samples, 1):
            session.arm(f"b pc = ${head:x} :{frame + 1} :once :quiet "
                        + action_file(work, f"THEIR{index}.INI",
                                      *original_sample_dumps(work, base, index)))
        # THE ORIGINAL PRESSES FIRE FROM INSIDE ITS OWN WAITS, on repeating breakpoints at the two
        # polls that read the byte: `tst.b $19681` at 0x10f2a (PREPARE FOR COMBAT, re-entered after
        # every death) and at 0x12c5e (the attract menu). The PC reaches neither during a frame, so
        # the press cannot perturb one. `:N` fires on every Nth arrival, which is often enough for a
        # loop that sends an IKBD command on each pass and cheap enough not to crawl.
        for site, name in ((GHIDRA_SECTION_TAIL_FIRE_POLL, "THEIRFIRE1.INI"),
                           (GHIDRA_ATTRACT_FIRE_POLL, "THEIRFIRE2.INI")):
            session.arm(f"b pc = ${runtime(base, site):x} :{FIRE_POLLS_PER_PRESS} :quiet "
                        + action_file(work, name,
                                      f"w b ${joystick:x} ${JOYSTICK_FIRE:x}"))
        last = work / f"OENT{len(samples)}.bin"
        press_fire_only_in_a_wait(session, lambda: last.is_file() and last.stat().st_size,
                                  "waiting for the original's last sampled frame")
        # The original never terminates — it runs on into its next life — so this side is closed by
        # the driver rather than by the program.
    finally:
        status = session.close()
    return {"status": status, "log": log, "trace": trace, "work": work, "base": base,
            "frames": {frame: original_front_buffer(work, index)
                       for index, frame in enumerate(samples, 1)},
            "pens": {frame: read_or_empty(work / f"OPAL{index}.bin")
                     for index, frame in enumerate(samples, 1)},
            "entities": {frame: read_or_empty(work / f"OENT{index}.bin")
                         for index, frame in enumerate(samples, 1)}}


def read_or_empty(path):
    """...and the original's side of the same rule — a breakpoint that never fired is an empty
    dump the length guards name, not an exception before the report is printed."""
    return path.read_bytes() if path.is_file() else b""


def original_sample_dumps(work, base, index):
    """What the original's breakpoint dumps at one sample: both buffers, which one is showing,
    the colour registers and the entity table.

    BOTH FRAMEBUFFERS, because the debugger cannot dereference: the game's two buffers are at the
    absolute addresses it hard-codes and the pointer pair says which of them is front, so the choice
    is made on the host afterwards (`original_front_buffer`).
    """
    return [f"savebin {work / ('OPTR%d.bin' % index)} "
            f"${runtime(base, GHIDRA_SCREEN_POINTERS):x} ${SCREEN_POINTER_BYTES:x}",
            f"savebin {work / ('OFBA%d.bin' % index)} ${GAME_SCREEN_BACK:x} ${SCREEN_BYTES:x}",
            f"savebin {work / ('OFBB%d.bin' % index)} ${GAME_SCREEN_FRONT:x} ${SCREEN_BYTES:x}",
            f"savebin {work / ('OPAL%d.bin' % index)} ${HW_PALETTE_BASE:x} "
            f"${PALETTE_PENS * PEN_BYTES:x}",
            f"savebin {work / ('OENT%d.bin' % index)} ${runtime(base, GHIDRA_ENTITY_TABLE):x} "
            f"${ENTITY_TABLE_BYTES:x}"]


def original_front_buffer(work, index):
    """Whichever of the two dumps the original's own `screen_front` pointer named."""
    pointers = work / f"OPTR{index}.bin"
    if not pointers.is_file() or pointers.stat().st_size < SCREEN_POINTER_BYTES:
        return b""                     # the breakpoint never fired; the length guard names it
    _, front = struct.unpack(">II", pointers.read_bytes()[:SCREEN_POINTER_BYTES])
    if front == GAME_SCREEN_BACK:
        return read_or_empty(work / f"OFBA{index}.bin")
    if front == GAME_SCREEN_FRONT:
        return read_or_empty(work / f"OFBB{index}.bin")
    raise SystemExit(f"the original's screen_front held {front:#x} at sample {index}, which is "
                     f"neither of the two buffers it hard-codes")


def entity_rebase_spans():
    """The byte ranges of the entity table that hold a POINTER and cannot be compared raw.

    Each record's ENTITY_SPRITE is an absolute address of the loaded program, so the two sides
    differ there by exactly the difference of their load bases. The comparison excludes those twenty
    longwords from the byte diff and checks them REBASED instead, which is stricter than skipping
    them: a sprite pointing at the wrong bank is still caught.
    """
    return [(slot * ENTITY_STRIDE + ENTITY_SPRITE_OFFSET, ENTITY_SPRITE_BYTES)
            for slot in range(ENTITY_SLOTS)]


def in_the_loaded_program(address, base, size):
    """Is this longword an address of the program that was loaded at `base`?

    A sprite field that holds neither side's program address is not a pointer at all — it is what a
    slot the game has never armed happens to contain, and on the two machines that is a different
    piece of leftover (measured: `$fc0000` here against `$fc55aa` there, both inside TOS's ROM). Such
    a field is reported as UNSET rather than as a difference, because the record it belongs to is
    dead on both sides and the byte diff over the rest of the record is what says so.
    """
    return base <= address < base + size


def entity_problems(frame, ours, theirs, their_base, our_base, program_bytes):
    """One sample's entity table, compared with the sprite pointers rebased."""
    if len(ours) != ENTITY_TABLE_BYTES or len(theirs) != ENTITY_TABLE_BYTES:
        return [f"frame {frame}: entity dumps are {len(ours)} and {len(theirs)} bytes, "
                f"not {ENTITY_TABLE_BYTES}"]
    excused = set()
    problems = []
    for start, width in entity_rebase_spans():
        excused.update(range(start, start + width))
        mine = int.from_bytes(ours[start:start + width], "big")
        yours = int.from_bytes(theirs[start:start + width], "big")
        # OURS is an image offset (a Ghidra address, because the image is staged at LOAD_BASE) and
        # THEIRS is an absolute address of the program TOS relocated, so the two are compared in
        # Ghidra addresses. A field that is a pointer on neither side is a dead slot's leftover.
        mine_pointer = in_the_loaded_program(mine, our_base, program_bytes)
        their_pointer = in_the_loaded_program(yours, their_base, program_bytes)
        if not mine_pointer and not their_pointer:
            continue
        rebased = yours - their_base + LOAD_BASE if their_pointer else yours
        if mine != rebased:
            problems.append(f"frame {frame}: entity {start // ENTITY_STRIDE}'s sprite is "
                            f"{mine:#x}, the original's rebases to {rebased:#x}")
    differing = [index for index in range(ENTITY_TABLE_BYTES)
                 if index not in excused and ours[index] != theirs[index]]
    if differing:
        # NAMED AS (record, field offset) PAIRS, because "record 0 differs" is not a finding anybody
        # can act on and "record 0 at +0x14" is: the offsets are include/entity.h's field map, so
        # the message says WHICH field of which actor and the header says what that field is.
        where = ", ".join(f"{index // ENTITY_STRIDE}+{index % ENTITY_STRIDE:#04x} "
                          f"({ours[index]:#04x} vs {theirs[index]:#04x})"
                          for index in differing[:ENTITY_DIFF_REPORTED])
        unlisted = len(differing) - ENTITY_DIFF_REPORTED
        more = f", +{unlisted} more" if unlisted > 0 else ""
        problems.append(f"frame {frame}: {len(differing)} entity bytes differ at {where}{more}")
    return problems


def check_frame_differential(ours, original, program_bytes):
    """SURFACE: memory — the framebuffer and the entity table, frame for frame.

    BOTH LENGTHS ARE CHECKED, and the second one is the important one: `zip` stops at the shorter
    sequence, so a short or empty `savebin` on the ORIGINAL's side would make `differing` come out 0
    and report the milestone's headline surface green for a frame that was never captured. The
    entity compare next door has always checked both; this one did not.
    """
    problems = []
    for frame, mine in sorted(ours["frames"].items()):
        yours = original["frames"][frame]
        if len(mine) != SCREEN_BYTES or len(yours) != SCREEN_BYTES:
            problems.append(f"frame {frame}: the framebuffer dumps are {len(mine)} and "
                            f"{len(yours)} bytes, not {SCREEN_BYTES} — one side was not captured")
            continue
        differing = sum(1 for left, right in zip(mine, yours) if left != right)
        if differing:
            problems.append(f"frame {frame}: {differing} of {SCREEN_BYTES} framebuffer bytes differ")
        problems += entity_problems(frame, ours["entities"][frame], original["entities"][frame],
                                    original["base"], LOAD_BASE, program_bytes)
    return problems


def check_frame_pens(ours, original):
    """SURFACE: the hardware-state vector — the sixteen colour registers at each sampled frame."""
    problems = []
    for frame, mine in sorted(ours["pens"].items()):
        yours = original["pens"][frame]
        mine_masked = [pen & PEN_MASK for pen in struct.unpack(f">{PALETTE_PENS}H", mine)]
        yours_masked = [pen & PEN_MASK for pen in struct.unpack(f">{PALETTE_PENS}H", yours)]
        if mine_masked != yours_masked:
            differing = [index for index, pair in enumerate(zip(mine_masked, yours_masked))
                         if pair[0] != pair[1]]
            problems.append(f"frame {frame}: pens differ at {differing}: "
                            f"ours {[hex(mine_masked[i]) for i in differing]}, "
                            f"the original's {[hex(yours_masked[i]) for i in differing]}")
    return problems


def check_timer_b_never_fired(ours):
    """SURFACE: the hardware-state vector — an M1 build must not have started an MFP timer.

    IT MOVED OUT OF `check_the_program_finished` AND THE GAME MODE IS WHY. That check is shared by
    every mode, and this assertion is M1's alone: nothing in the title composition programs a timer
    and TOS leaves Timer B stopped on an ST, so a non-zero count there means something started one.
    M2 starts it deliberately, twice, at two periods — the raster split and the attract bars both
    run off it — so leaving the arm in the shared check made the game modes red for doing their job.
    """
    record = ours["record"]
    if record["timer_b_ticks_at_anchor"]:
        return [f"Timer B fired {record['timer_b_ticks_at_anchor']} times, and nothing in the title "
                f"composition starts it"]
    return []


def check_the_game_fork_was_not_taken(ours):
    """SURFACE: memory — an M1 build must not have run M2's composition.

    zynaps_main.c forks on ONE `#if`, and the fields below are written only on the game side of it.
    A title binary that had somehow taken that fork would pass every M1 surface — the boot is the
    same code and the anchor is the same picture — while being a different program running for a
    different length of time. These are the ones that say it did not, the pacing histogram among
    them: it is written by `note_frame_pacing`, which only the frame loop reaches.
    """
    record = ours["record"]
    game_only = ("phase_reached", "attract_passes", "section_starts", "frames_run", "playing_vbls",
                 *(f"frame_vbls_{count}" for count in range(PACING_SLOTS - 1)), "frame_vbls_over")
    return [f"{name} is {record[name]}, not 0 — this build ran the game composition"
            for name in game_only if record[name]]


def check_the_game_ran(ours, samples=None):
    """SURFACE: exit status and the log — the program's own account of the whole run."""
    record = ours["record"]
    samples = samples or frame_samples()
    problems = []
    if record["phase_reached"] != PHASE_BUDGET_SPENT:
        reached = (PHASE_NAMES[record["phase_reached"]]
                   if record["phase_reached"] < len(PHASE_NAMES) else record["phase_reached"])
        problems.append(f"the run stopped at phase '{reached}', not at its frame budget")
    if record["unknown_vector_halts"]:
        problems.append(f"an interrupt named handler {record['unknown_vector_handler']:#x} on "
                        f"vector {record['unknown_vector']:#x}, which the dispatch table does not "
                        f"know — see zynaps_main.c's isr_binding tables")
    if record["frames_run"] < max(samples):
        problems.append(f"only {record['frames_run']} frames ran, fewer than the last sample "
                        f"({max(samples)})")
    if record["attract_passes"] < 1:
        problems.append("the attract loop never ran")
    if record["section_starts"] < 1:
        problems.append("no section was ever started")
    # Every interrupt entry must have dispatched to at least one handler, or the vector it is on was
    # never taken and the phase behind it never ran.
    for name in ("vbl_dispatch_in_game", "vbl_dispatch_attract", "timer_b_dispatch_attract",
                 "acia_dispatches"):
        if not record[name]:
            problems.append(f"{name} is 0 — that handler was never entered")
    # `vbl_isr_title` @ 0x106a2 is in the table and NO STORE IN THE PROGRAM NAMES IT (measured over
    # every `move.l #$x,$70/$118/$120` in the shipped disassembly). A non-zero count would mean the
    # image's vector page held an address this reconstruction does not expect.
    if record["vbl_dispatch_title"]:
        problems.append(f"vbl_isr_title was entered {record['vbl_dispatch_title']} times, and no "
                        f"store in the shipped program installs it")
    if record["rmw_stores"] < 1:
        problems.append("no read-modify-write reached the machine — the cores' hw_bclr8/hw_bset8/"
                        "hw_and8 went somewhere other than shim_include/hw.h, and the MFP enables "
                        "and acknowledges would be plain stores that clear bits TOS owns")
    # ONE PUBLISH PER FRAME AT LEAST: `screen_flip_buffers` runs once a frame, and the door
    # republishes on each of its two byte stores, so a run that flipped every frame cannot be under
    # the frame count. A shim that had stopped translating would sit far below it.
    if record["video_base_publishes"] < record["frames_run"]:
        problems.append(f"the video base was published {record['video_base_publishes']} times over "
                        f"{record['frames_run']} frames — the frame loop flips every frame")
    # ...AND THE ADDRESS IT PUBLISHED IS THE ONE THE TRANSLATION OWES. The core names an image
    # OFFSET and the door adds the image base; if that addition ever stopped happening the shifter
    # would fetch from $0703xx and the picture would be garbage, which no other field here can see.
    translated = record["image_base"] + record["video_base_offset"]
    if record["video_base_published"] != translated:
        problems.append(f"the video base published {record['video_base_published']:#x}, but image "
                        f"base {record['image_base']:#x} + offset "
                        f"{record['video_base_offset']:#x} is {translated:#x} — the door's "
                        f"image-to-machine translation is not what reached the shifter")
    # EVERY SAMPLE MUST BE INSIDE THE FIRST LIFE. Past the first non-NEXT_FRAME exit the ship has
    # died, `section_start_tail` has asked for the fire button again, and that wait calls `rand16`
    # a driver-dependent number of times — so the two sides' random streams part company and
    # nothing after it is comparable. The program reports the frame it happened on; this is the
    # relation, checked rather than the sample list being trusted to stay inside it.
    ended = record["first_life_ended_at"]
    if ended and ended <= max(samples):
        problems.append(f"the first life ended at frame {ended}, at or before the last sample "
                        f"({max(samples)}) — every frame after it is compared over two random "
                        f"streams that have parted, see README.md's M2 unpinned 17")
    return problems


# =================================================================================================
# THE PACING SURFACE — the frame cadence, the interrupt service rates, and what each is measured
# against.
#
# EVERY OTHER CHECK IN THIS FILE ASKS WHETHER THE PORT COMPUTES THE RIGHT BYTES. This one asks
# whether it computes them IN TIME, which for this program is one number: how many vertical blanks
# one `frame_loop_once` takes. `frame_end_and_flip` (../src/frame.c) waits on `A_vbl_wait_flag`, and
# the handler that clears it is `vbl_menu`, whose raster phase counts up and wraps at 2 — so the
# cadence is QUANTISED. A frame that fits its budget is released on the second vertical blank; one
# that overruns waits for the next release, not for a few more scanlines.
#
# THE BAR IS THE SHIPPED BINARY'S OWN, MEASURED: `atari/profile.py original-frames` clocks the
# original's loop head over 542 frames of section 1 on this machine and gets 496 frames at 2
# vblanks, 2 at 3, 42 at 4 and 2 at 45 (a death and its respawn). So 2 is the bar, the 4-vblank tail
# is the original's own and not a threshold this file chose, and 25 fps is what "on par" means.
#
# THIS RECONSTRUCTION DOES NOT MEET THAT BAR AND THE CHECK SAYS SO IN NUMBERS RATHER THAN PASSING
# QUIETLY. A frame costs 815,488 cycles against the original's 271,565 — 3.0x, and a fact about C
# against hand-written 68000 assembly rather than about any one routine (atari/README.md's
# PERFORMANCE section carries the per-routine table). So the ceiling below is a REGRESSION GUARD set
# from what this tree measures, and the gap to the original is carried as an unpinned residual. A
# check that demanded the original's 2 would be red on every run and would therefore be read by
# nobody; one that demanded nothing would let a slowdown through.
# =================================================================================================
# The vertical blanks a frame takes when its work fits, on both sides — `vbl_menu`'s
# RASTER_PHASE_PERIOD, pinned against ../include/irq.h by
# `assert_the_game_constants_are_the_headers`. It is the release PERIOD and therefore the step the
# cadence moves in; it is NOT a floor a frame can never be under, because `A_raster_phase` is
# free-running and a frame can arrive with it already at READY (see `check_the_pacing`).
PACING_RELEASE_PERIOD_VBLS = 2
# The PAL machine both sides are measured on, so a vblank count can be printed as a frame rate.
VBL_HZ = 50
# THE RUN THE TOLERANCES BELOW WERE MEASURED ON, and the reason this is a constant rather than a
# sentence: they are absolute numbers, not shares, so they mean nothing over a different number of
# frames. `check_the_pacing` refuses a run whose frame count is not this one instead of applying
# them anyway — a longer run reaches a second life, whose 4-vblank frames are a different mixture.
PACING_BASELINE_FRAMES = 300
# What this tree measures, and the ceiling a run must stay under. MEASURED at 3.75 mean vblanks a
# frame over those 300 frames — 38 at 2, 262 at 4, NONE over — and measured TWICE to the second
# decimal, because the tolerance rests on that: the 300 frames are pinned (the same random state,
# the same entity table, a neutral stick every frame), so the cadence is REPRODUCIBLE and this is
# not a noise band.
#
# THE SCROLL PATH'S ASM TWINS ARE WHAT MOVED IT, from 5.73 (41 at 4, 258 at 6, one over) to 3.75:
# ../src/asm/ transcribes the original binary's own instructions for the twenty page blits, the two
# column emitters and the tile emitter, and the frame's biggest item stopped costing three times
# what the original paid for it. 8.7 fps to 13.3, and the MODE moved a whole release slot, 6 to 4.
#
# THE CEILING IS 3.87, AND THE ARITHMETIC IS THE SAME ONE THAT SET 5.85 — the slack is EIGHTEEN
# frames slipping one release slot, and a slot is 2 vertical blanks, so 36 vblanks over 300 frames
# is 0.12 on the mean: 3.7467 measured (1,124 vblanks) + 0.12 = 3.8667 (1,160).
#
# 3.87 IS THAT ROUNDED UP TO TWO DECIMALS, AND THE ROUNDING BUYS ONE VBLANK MORE THAN THE DERIVATION
# ASKS FOR. `check_the_pacing` fails on `mean > ceiling`, so a run still passes at 1,161 vblanks
# (1,161 / 300 = 3.87 exactly) where eighteen slipped frames account for 1,160: the real slack is 37,
# not 36. The pre-twin ceiling's was exactly 36 (5.85 x 300 = 1,755 against 5.73's 1,719), so this
# one is a vblank looser than that rather than identical to it. Kept at 3.87 rather than carried to
# more decimals — one vblank is a thirtieth of the tolerance it sits in, and two decimals is what
# every cadence figure in this file and in README.md is quoted to — but named here rather than
# papered over, because "the same slack as before" would otherwise be off by one.
#
# The 0.12 is deliberately NOT re-derived as a share of the new mean, which would have shrunk the
# slack to 24 vblanks and made the check tighter than the evidence for it.
#
# It is a tight number and it is meant to be. The run is deterministic — 3.75 to the second decimal
# on the `game` build twice and on `gamefault` once, with the same histogram to the frame — so the
# margin is for a real change, not for noise. It is also why the frame count is pinned above: the
# `play` build's longer run reaches a second life, whose mixture is a different one.
#
# THE `gamefault` CONTROL WAS MEASURED AGAINST THE SAME CEILING rather than exempted from it,
# because this check sits in `mode_game`'s FAULT-BLIND set and a tolerance that had only ever seen
# one mode would be one the control could redden by accident. Measured: `gamefault` gives 3.75 and
# [2x38 4x262], the same histogram to the frame — the dropped section-chain step is a one-off panel
# repaint, not per-frame work, so it moves what is DRAWN and not what a frame costs.
PACING_MEAN_CEILING_VBLS = 3.87
# ...and how many frames may reach the histogram's last slot (PACING_SLOTS - 1 = seven vblanks
# or more) — an ABSOLUTE COUNT (the share form was measured 40x looser than its comment claimed,
# see the git history). IT IS ZERO, AND THAT IS WHAT WAS MEASURED: 0 of 300 since the asm twins landed,
# on all three runs the mean above rests on — two `game` builds and one `gamefault`, the same
# histogram to the frame. The section's first pass, which draws the whole playfield and was the one
# frame that used to overflow, now fits. A 2% allowance is six frames over 300, and a run this
# deterministic never spends them: an allowance nothing occupies is slack, not headroom, so zero is
# the honest number and the first overflowing frame is the report.
#
# THE LIMITATION ZERO DOES NOT FIX, stated rather than left implicit: the last slot is fixed in C at
# seven vblanks (zynaps_main.c's PACING_SLOTS, pinned by `assert_the_phase_names_are_the_shims`)
# while the cadence's mode is now four, so this arm only fires at nearly DOUBLE the mode. It was one
# release slot above the mode when the mode was six; it no longer is. A regression that puts frames
# at five or six vblanks — a whole release slot lost — never reaches the slot at all, and
# PACING_MEAN_CEILING_VBLS above is the only arm that catches it.
PACING_OVERFLOW_FRAMES = 0

# ATTRACT MODE'S TIMER B IS THE INTERRUPT THIS PORT IS MOST EXPOSED TO, and its expected rate is
# arithmetic rather than a measurement: `attract_program_rasterbar_timer` puts Timer B in
# event-count mode with a period of 2 (MFP_TIMER_B_PERIOD_ATTRACT_BARS), and the event it counts is
# the shifter's display-enable pulse — one per DISPLAYED scanline, of which ST low resolution has
# 200. So the chip offers 100 interrupts per vertical blank, and every one the handler does not
# reach is a colour bar the attract screen does not draw.
#
# THE DENOMINATOR IS `vbl_dispatch_attract` AND NOT A SPAN THE SHIM TIMES, because the two are not
# the same window and the shim's was the wrong one: `title_attract_loop` returns while attract
# mode's VBL and Timer B are both STILL INSTALLED — `boot_program_timer_b` is what swaps them, four
# calls later — so a span measured around the loop was 34 vertical blanks where the handler ran for
# 64, and the ratio came out at 184% of a rate nothing can exceed. The handler's own entry count
# over the entry count of the VBL handler installed beside it is the same window by construction.
ATTRACT_DISPLAYED_LINES = 200
# ../include/init.h's MFP_TIMER_B_PERIOD_ATTRACT_BARS, pinned against it by
# `assert_the_game_constants_are_the_headers` — a period that moved there and not here would make
# this check compare the served count against the wrong denominator and pass on half service.
ATTRACT_TIMER_B_PERIOD = 2
ATTRACT_TIMER_B_PER_VBL = ATTRACT_DISPLAYED_LINES // ATTRACT_TIMER_B_PERIOD
# The share of them the handler must serve. MEASURED at 0.98 of the arithmetic rate; the floor is
# 0.95, which is the point below which the bars are visibly thinned — a handler over its own 1024-
# cycle period drops every other interrupt and lands near 0.5, so the two states are far apart and
# the floor does not have to be precise to separate them.
ATTRACT_TIMER_B_SERVED_FLOOR = 0.95
# The keyboard controller's own traffic, as interrupts per vertical blank of the whole run. The
# frame loop asks for a joystick packet once a frame (`ikbd_send_cmd(IKBD_CMD_INTERROGATE_JOYSTICK)`
# in `frame_end_and_flip`) and the 6301 answers with a three-byte report, so a served run cannot be
# far below one interrupt per frame. MEASURED at 0.45 per vblank over the whole run; the floor is
# 0.25, which a run whose ACIA was being starved by a longer-running handler would fall under.
ACIA_SERVED_PER_VBL_FLOOR = 0.25


def pacing_figures(record):
    """The two ratios the report and the verdict both need — derived ONCE so they cannot disagree.

    A run that reached no frame gives a mean of 0 rather than dividing by its own zero: the report
    is printed BEFORE the verdicts, so it has to survive the run `check_the_game_ran` reddens.
    """
    mean = record["playing_vbls"] / record["frames_run"] if record["frames_run"] else 0
    attract_offered = record["vbl_dispatch_attract"] * ATTRACT_TIMER_B_PER_VBL
    return mean, attract_offered


def pacing_line(record):
    """The pacing numbers as one line of the report, whatever the check made of them.

    THE WHOLE DISTRIBUTION AND NOT JUST THE MEAN, because the release mechanism quantises the
    cadence: "5.7 vblanks a frame" is not a rate anything runs at, it is a mixture of 4s and 6s, and
    which mixture is what moves when a lever lands.
    """
    buckets = [f"{count}x{record[f'frame_vbls_{count}']}"
               for count in range(PACING_SLOTS - 1) if record[f"frame_vbls_{count}"]]
    if record["frame_vbls_over"]:
        buckets.append(f"{PACING_SLOTS - 1}+x{record['frame_vbls_over']}")
    mean, attract_offered = pacing_figures(record)
    cadence = (f"{mean:.2f} vblanks/frame [{' '.join(buckets)}] = {VBL_HZ / mean:.1f} fps" if mean
               else "no frame ran")
    return (f"pacing: {cadence} (the original's {PACING_RELEASE_PERIOD_VBLS} = "
            f"{VBL_HZ // PACING_RELEASE_PERIOD_VBLS}); attract Timer B "
            f"{record['timer_b_dispatch_attract']}/{attract_offered} served over "
            f"{record['vbl_dispatch_attract']} vblanks")


def check_the_pacing(ours):
    """SURFACE: timelines — the frame cadence and the two interrupt service rates.

    Every figure is the PROGRAM's own, out of STATE.BIN: the shim latches `zy_vbl_ticks` either side
    of each `frame_loop_once` (zynaps_main.c's `note_frame_pacing`), and the two service rates come
    out of the per-handler dispatch counts the record already carried. So what is judged is what the
    machine did rather than what a host stopwatch saw.
    """
    record = ours["record"]
    frames = record["frames_run"]
    problems = []
    if not frames:
        return ["no frame ran, so there is no cadence to judge"]
    # THE TOLERANCES BELOW ARE ABSOLUTE NUMBERS, NOT SHARES, so they mean nothing over a different
    # run. Refusing here is not pedantry: a longer run reaches a second life, whose mixture of 4-
    # and 6-vblank frames is a different one, and applying this ceiling to it would report a
    # different GAME as a regression (measured: the `play` build's 534 frames average 7.38).
    if frames != PACING_BASELINE_FRAMES:
        problems.append(f"this run played {frames} frames and the tolerances below were measured "
                        f"over {PACING_BASELINE_FRAMES} — they do not describe it, so the cadence "
                        f"is reported rather than judged")
        return problems

    # NO FRAME MAY COST ZERO VERTICAL BLANKS, and the tolerance is 0 because that one IS an
    # invariant: `frame_end_and_flip` arms `A_vbl_wait_flag` and then spins until a VBL handler
    # clears it, and `shim_include/sched.h`'s `sched_wait8` has no cap, so at least one vertical
    # blank always elapses inside the wait. A frame recorded at 0 did not go through it at all.
    #
    # ONE VBLANK IS NOT AN ERROR AND THIS ARM MUST NOT SAY IT IS. `A_raster_phase` is FREE-RUNNING —
    # `vbl_menu` ticks it every vertical blank and nothing resets it at a frame boundary — so a
    # frame whose head arrives with the phase already at FRAME_RASTER_PHASE_READY returns from
    # `frame_end_and_flip`'s first wait immediately and is released by the very next wrap, one
    # vblank later. Measured in this tree: the shipped binary's own timeline carries two 3-vblank
    # frames in 542 and ours two 7-vblank frames in 534, which is the same parity effect one slot
    # up. The mean and the overflow share below are what judge those, not a floor.
    if record["frame_vbls_0"]:
        problems.append(f"{record['frame_vbls_0']} frame(s) cost no vertical blank at all — the "
                        f"frame loop's wait on A_vbl_wait_flag was not the thing that released "
                        f"them")
    mean, attract_offered = pacing_figures(record)
    if mean > PACING_MEAN_CEILING_VBLS:
        problems.append(f"the frame loop averaged {mean:.2f} vblanks a frame over {frames} frames, "
                        f"past the {PACING_MEAN_CEILING_VBLS} ceiling — the game got slower (the "
                        f"original's own is {PACING_RELEASE_PERIOD_VBLS}; see README.md's "
                        f"PERFORMANCE section)")
    overflowed = record["frame_vbls_over"]
    if overflowed > PACING_OVERFLOW_FRAMES:
        problems.append(f"{overflowed} of {frames} frames took {PACING_SLOTS - 1} vblanks or more, "
                        f"past the {PACING_OVERFLOW_FRAMES}-frame allowance")

    # THE ATTRACT SCREEN'S TIMER B, as a share of what the chip offered over the same vblanks.
    attract_vbls = record["vbl_dispatch_attract"]
    if not attract_vbls:
        problems.append("attract mode's VBL handler was never entered — its Timer B rate has no "
                        "denominator, and `check_the_game_ran` should already have failed")
    else:
        served = record["timer_b_dispatch_attract"] / attract_offered
        if served < ATTRACT_TIMER_B_SERVED_FLOOR:
            problems.append(f"attract mode served {record['timer_b_dispatch_attract']} of the "
                            f"{attract_offered} Timer B interrupts the chip offered over "
                            f"{attract_vbls} vblanks "
                            f"({served:.0%}, floor {ATTRACT_TIMER_B_SERVED_FLOOR:.0%}) — "
                            f"the handler is running past its own two-scanline period and the "
                            f"colour bars are drawn at reduced density")

    # ...AND THE KEYBOARD'S, over the whole run. A handler that overruns blocks the ACIA (MFP
    # channel 6 is below Timer B's channel 8), which loses a byte of the 6301's three-byte report
    # and desynchronises the packet parser — README.md's M2 unpinned 19.
    # SUMMED OVER THE HANDLER LIST rather than over three names typed here: `VBL_HANDLER_NAMES` has
    # four entries, and a denominator that named three would come out SHORT — a served rate too
    # high, and a genuinely starved keyboard passing the floor — the day `vbl_isr_title` is
    # installed. The dispatch table exists so that installing it is a dispatch and not a halt.
    total_vbls = sum(record[f"vbl_dispatch_{name}"] for name in VBL_HANDLER_NAMES)
    if total_vbls:
        served = record["acia_dispatches"] / total_vbls
        if served < ACIA_SERVED_PER_VBL_FLOOR:
            problems.append(f"the keyboard ACIA was served {record['acia_dispatches']} times over "
                            f"{total_vbls} vertical blanks ({served:.2f} per vblank, floor "
                            f"{ACIA_SERVED_PER_VBL_FLOOR}) — a handler that runs past its own "
                            f"period blocks MFP channel 6 and the joystick packet is lost")
    return problems


def check_the_acia_vector_went_back(ours):
    """SURFACE: exit status and the log — the third vector M2 displaces, put back."""
    record = ours["record"]
    if record["acia_vector_after"] != record["tos_acia_vector"]:
        return [f"$118 was left at {record['acia_vector_after']:#x}, TOS had "
                f"{record['tos_acia_vector']:#x} — a keyboard handler in freed memory"]
    return []


def mode_game(mode, out_dir, machine, tos_rom, keep):
    """The whole game, judged against the shipped binary at five numbered frames."""
    assert_the_game_constants_are_the_headers()
    assert_the_phase_names_are_the_shims()
    stage_our_build(mode)
    for stale in OUR_DISK.glob("FRAME*.BIN"):
        stale.unlink()
    for stale in list(OUR_DISK.glob("PAL*.BIN")) + list(OUR_DISK.glob("ENT*.BIN")):
        stale.unlink()
    samples = frame_samples()
    with tempfile.TemporaryDirectory() as our_work, tempfile.TemporaryDirectory() as their_work:
        ours = run_ours_game(mode, out_dir, Path(our_work), machine, tos_rom)
        original = run_original_game(out_dir, Path(their_work), machine, tos_rom, samples)

        # THE SENSITIVE CHECKS AND THE INSENSITIVE ONES ARE SEPARATED HERE, because that separation
        # IS the control: `gamefault` drops ONE STEP of the section chain and nothing else, so what
        # the game DRAWS must move while its colours, its exit path and its own record must not.
        fault_sensitive = {
            "memory (the framebuffer and the entity table, frame by frame)":
                check_frame_differential(ours, original, len(gen_image_bytes())),
        }
        fault_blind = {
            "exit status + log (ours)": check_exit_and_log("ours", ours),
            "exit status + log (the original)": check_exit_and_log("the original", original),
            "exit status + log (the fault scan can fail)": check_the_fault_scan_can_fail(),
            # THE BOOT'S OWN READ-BACKS TOO, and not only M2's counters: `check_the_program_finished`
            # asserts the staged byte count, the supervisor token, the two IKBD command totals and
            # the teardown's own numbers, every one of which the game build makes exactly as the
            # title build does. Dropping them here would have left the M2 modes asserting less
            # about the boot than the M1 modes do over the same code.
            "exit status + log (the program's own record)":
                check_the_program_finished(ours) + check_the_game_ran(ours),
            "exit status + log (the machine was handed back)":
                check_the_machine_was_handed_back(ours) + check_the_acia_vector_went_back(ours),
            "hardware-state vector (the pens, frame by frame)": check_frame_pens(ours, original),
            # THE PACING SURFACE IS FAULT-BLIND BY CONSTRUCTION and that is worth a line: the
            # control drops a section-chain step, which changes what is DRAWN and not how long a
            # frame takes, so a pacing check that moved under it would be measuring the wrong
            # thing. Its own control is the busy-wait one README.md's Performance section describes.
            "timelines (the frame cadence and the interrupt service rates)": check_the_pacing(ours),
            "hardware-state vector (TOS's 200 Hz clock survived the boot)":
                check_the_boot_clock(ours["record"]),
        }
        # THERE IS NO TIMELINE ARM HERE, AND IT WAS TRIED. M1's `check_timeline` cuts the PSG trace
        # into the sound driver's own descending 10..0 tick frames and compares the first 64 as a
        # SHAPE, which works there because both runs are still on the title screen for all of them.
        # In a game run those 64 frames reach past the boot: the section-start effect and the
        # in-game tune fall inside the window, and they fall at different absolute times on the two
        # sides because the two boots take different lengths of time. Measured: green on `game`, but
        # RED at tick frame 51 on `gamefault`, whose fault touches no sound at all — a check that
        # moves for a reason it cannot name is not one to ship. README.md's M2 unpinned 20 carries
        # what would replace it: a cut anchored on the first IN-GAME tune start rather than on the
        # trace's beginning.
        if keep:
            for frame, pixels in sorted(ours["frames"].items()):
                (out_dir / f"{mode}_frame{frame}.bin").write_bytes(pixels)
                (out_dir / f"original_frame{frame}.bin").write_bytes(original["frames"][frame])

        return report_game(mode, fault_sensitive, fault_blind, ours, original,
                           f"{machine} / {tos_rom.name}", samples)


def report_game(mode, fault_sensitive, fault_blind, ours, original, machine, samples):
    """Print every check that RAN, with its verdict, and return the process's exit status."""
    control = mode == GAME_FAULT_MODE
    record = ours["record"]
    print(f"-- {mode} on {machine}: image base {record['image_base']:#x}, the original at "
          f"{original['base']:#x}")
    print(f"   {record['frames_run']} frames over {record['section_starts']} section start(s), "
          f"{record['attract_passes']} attract pass(es), player(s) {record['player_count']}, "
          f"section {record['level_section']}, {record['lives']} lives, "
          f"score {record['score_bcd']:08x}")
    print(f"   dispatched: {record['vbl_dispatch_in_game']} in-game / "
          f"{record['vbl_dispatch_menu']} menu / {record['vbl_dispatch_attract']} attract VBLs, "
          f"{record['timer_b_dispatch_raster']} raster + "
          f"{record['timer_b_dispatch_attract']} bar Timer Bs, "
          f"{record['acia_dispatches']} IKBD; "
          f"{record['unknown_vector_halts']} unknown-vector halt(s)")
    print(f"   samples {samples}; {record['rmw_stores']} read-modify-writes made, "
          f"{record['mfp_settle_restores']} Timer B data restore(s) in the four read-back spins")
    print_the_boot_clock(record)
    print("   " + pacing_line(record))
    for group, checks in (("must PASS", fault_blind),
                          ("must FAIL" if control else "must PASS", fault_sensitive)):
        for name, problems in sorted(checks.items()):
            print(f"   [{'red ' if problems else 'green'}] {name}   ({group})")
            for problem in problems:
                print(f"           {problem}")

    failures = [name for name, problems in fault_blind.items() if problems]
    if control:
        if record["game_fault"] != 1:
            print("   CONTROL FAILED: the binary reports no injected fault")
            failures.append("the control's own soundness")
        for name in [name for name, problems in fault_sensitive.items() if not problems]:
            print(f"   CONTROL FAILED: {name} stayed green with a step of the section chain "
                  f"dropped")
            failures.append(name)
    else:
        if record["game_fault"]:
            print("   FAILED: the shipped build reports an injected fault")
            failures.append("the build is the control's")
        failures += [name for name, problems in fault_sensitive.items() if problems]

    print("-- OK" if not failures else f"-- FAILED: {len(failures)} check(s)")
    return 0 if not failures else 1


# TOS's `_hz_200` ticks 200 times a second, so a span in ticks is that many times five milliseconds.
HZ_200_TICK_MS = 5


def boot_clock_marks(record):
    """The program's five `$4ba` marks in the order it took them, as (what it bracketed, tick).

    The gameplay pair is 0 in a title build, which does not load them; it is dropped rather than
    reported as a span running backwards from the title loader's end."""
    marks = [("entering the title loader", record["ticks_at_title_assets"]),
             ("leaving it", record["ticks_after_title_assets"])]
    if record["ticks_at_gameplay_assets"]:
        marks += [("entering the gameplay loader", record["ticks_at_gameplay_assets"]),
                  ("leaving it", record["ticks_after_gameplay_assets"])]
    return marks + [("the hand-back", record["ticks_at_teardown"])]


def check_the_boot_clock(record):
    """TOS's 200 Hz clock was live when the boot started and STILL LIVE at the hand-back.

    THE SPANS THEMSELVES ARE REPORTED AND NOT JUDGED, and that half is deliberate: a boot time is a
    COST, no value of it makes the program wrong, and a threshold picked off one machine's Hatari
    would redden on a faster host for a reason that is not about this build. `atari/profile.py` is
    where cost is judged.

    WHAT IS JUDGED IS THAT THE CLOCK RAN, and that is a behaviour rather than a cost — it is the
    surface for the defect the read-modify-write doors exist to prevent. Timer C drives `$4ba` and
    sits in MFP interrupt-enable B beside the channel `boot_enable_interrupts` turns on; a plain
    `move.b #$40,$fffa09` there would enable that channel and DISABLE Timer C with it, taking TOS's
    200 Hz clock and the floppy driver's motor timeout. The kit's own `hw.h` says the write ledger
    holds that the store happened and CANNOT hold which bits it preserved, so until this arm the
    project had nothing that could see the difference: the game runs, the frames are byte-identical,
    and the clock is simply dead. A run that clobbered Timer C leaves every mark below equal.

    The other two arms are about the instrument rather than the program: a first mark of 0 means
    `$4ba` was read at the wrong address or the wrong width (TOS has been up for seconds by then,
    so a live counter is in the thousands), and marks out of order mean the program took them in a
    different order from the one this file prints."""
    problems = []
    marks = boot_clock_marks(record)
    if not marks[0][1]:
        problems.append(f"the boot's first $4ba mark is {marks[0][1]} — TOS's 200 Hz counter reads "
                        f"zero seconds after a boot that takes tens of them, so the address or the "
                        f"width of the read is wrong, not the timing")
    for (earlier_name, earlier), (later_name, later) in zip(marks, marks[1:]):
        if later < earlier:
            problems.append(f"$4ba went backwards between {earlier_name} ({earlier}) and "
                            f"{later_name} ({later})")
    if marks[-1][1] == marks[0][1]:
        problems.append(f"$4ba read {marks[0][1]} entering the title loader and the same at the "
                        f"hand-back — TOS's 200 Hz clock stopped during the run, which is what a "
                        f"`bset` on $fffa09 spelt as a plain store does to Timer C (and to the "
                        f"floppy's motor timeout with it)")
    return problems


def print_the_boot_clock(record):
    """Where the boot's milliseconds went, out of the program's own marks at $4ba.

    It answers README.md's Unpinned 25 — whether the boot is GEMDOS reading files or this build's C
    building preshift banks — on every run, rather than by a measurement somebody has to go and
    take. Each loader is bracketed by its own pair, so neither span bills the other's work."""
    marks = boot_clock_marks(record)
    spans = [(f"{'title' if index == 0 else 'gameplay'} assets",
              marks[index * 2 + 1][1] - marks[index * 2][1])
             for index in range(len(marks) // 2)]
    said = ", ".join(f"{name} {ticks * HZ_200_TICK_MS} ms" for name, ticks in spans)
    print(f"   boot: {said} (TOS was {marks[0][1] * HZ_200_TICK_MS} ms in when the first loader "
          f"ran, {marks[-1][1] * HZ_200_TICK_MS} ms at the hand-back)")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--out", type=Path, default=HERE / "out")
    parser.add_argument("--keep", action="store_true", help="leave the captures and dumps in --out")
    # BOTH SIDES GET WHATEVER THESE SAY, which is the module docstring's rule: a comparison between
    # two different machines is about the machines. `ste` is what the target hardware is; a second
    # ROM is what says the build does not depend on the one it was developed against.
    parser.add_argument("--machine", default=DEFAULT_MACHINE, help="Hatari --machine (st, ste, ...)")
    parser.add_argument("--tos-rom", type=Path, default=TOS_ROM, help="the ROM both sides boot")
    # WHICH BUILD IS ON THE VOLUME, because build.sh's medium is a flag and not a mode: `build.sh
    # title floppy` and `build.sh game floppy` both write disk/ZYNAPS.ST, and only the caller knows
    # which. The floppy mode's own checks are M1's, so its default is the M1 build.
    parser.add_argument("--floppy-build", default="title",
                        help="the build.sh mode whose .PRG is in AUTO\\ on disk/ZYNAPS.ST")
    options = parser.parse_args()

    assert_the_shim_owns_these_names()
    out_dir = options.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not options.tos_rom.is_file():
        raise SystemExit(f"no ROM at {options.tos_rom}")
    assert_machine_and_rom_agree(options.machine, options.tos_rom)
    # M2'S MODES HAVE THEIR OWN RUNNER AND THEIR OWN REPORT, exactly as Joust's framediff does:
    # they compare two programs that are PLAYING, so nothing below them applies — the anchor is a
    # frame count rather than a palette state, and both sides are driven with the same input.
    if options.mode in (GAME_MODE, GAME_FAULT_MODE):
        return mode_game(options.mode, out_dir, options.machine, options.tos_rom, options.keep)

    floppy = options.mode == FLOPPY_MODE
    if floppy:
        stage_our_floppy(options.floppy_build)
    else:
        stage_our_build(options.mode)

    with tempfile.TemporaryDirectory() as our_work, tempfile.TemporaryDirectory() as their_work:
        original_medium = (floppy_medium(booted_copy(ORIGINAL_FLOPPY, Path(their_work)))
                           if floppy else gemdos_medium(ORIGINAL_DISK, ORIGINAL_AUTO))
        # THE ARTIFACT NAMES ARE THE MODE'S AND THE ELF IS THE BUILD'S, which are two different
        # things now that the medium is a flag: `smoke.py floppy --floppy-build title` must not
        # write `out/title.log` over the log `smoke.py title` just produced, or a failure in either
        # run is diagnosed against the other's evidence.
        ours = (run_ours_from_floppy(options.mode, options.floppy_build, out_dir, Path(our_work),
                                     options.machine, options.tos_rom)
                if floppy else
                run_ours(options.mode, out_dir, Path(our_work), options.machine, options.tos_rom))
        original = run_original(out_dir, Path(their_work), original_medium,
                                options.machine, options.tos_rom,
                                len(gemdos_calls(ours["trace"], drop_names=NON_GAME_FILES)))

        # THE SENSITIVE CHECKS AND THE INSENSITIVE ONES ARE SEPARATED HERE, because that separation
        # IS the control: `titlefault` corrupts one pen on its way to the shifter and nothing else,
        # so the first group must go red and the second must stay green. A control that only
        # required "something failed" would pass on a build that crashed.
        colour_sensitive = {
            "hardware-state vector (the pens, $ff8260, the video base)":
                check_hardware_state(ours, original),
            "rendered pixels": check_rendered_pixels(ours, original),
        }
        colour_blind = {
            "exit status + log (ours)": check_exit_and_log("ours", ours),
            "exit status + log (the original)": check_exit_and_log("the original", original),
            "exit status + log (the program's own record)": check_the_program_finished(ours),
            "exit status + log (the machine was handed back)":
                check_the_machine_was_handed_back(ours),
            "exit status + log (the fault scan can fail)": check_the_fault_scan_can_fail(),
            "the original was anchored on its own boot":
                check_the_original_was_anchored_on_its_boot(original),
            "memory (the boot slice's own output and ledgers)":
                check_the_boot_slice_did_its_work(ours),
            "memory (the game fork was not taken)": check_the_game_fork_was_not_taken(ours),
            "hardware-state vector (Timer B never fired)": check_timer_b_never_fired(ours),
            "trap ledger": check_trap_ledger(ours, original),
            "memory (the framebuffer)": check_memory(ours, original),
            "timelines (the PSG tick frames)": check_timeline(ours, original),
            "hardware-state vector (TOS's 200 Hz clock survived the boot)":
                check_the_boot_clock(ours["record"]),
        }

        if options.keep:
            for side, tag in ((ours, options.mode), (original, "original")):
                for name in (SHOT, DUMP_PENS, DUMP_REZ, DUMP_BASE_HIGH, DUMP_BASE_MID):
                    if (side["work"] / name).is_file():
                        shutil.copy(side["work"] / name, out_dir / f"{tag}_{name}")

        return report(options.mode, colour_sensitive, colour_blind, ours, original,
                      f"{options.machine} / {options.tos_rom.name}")


def report(mode, colour_sensitive, colour_blind, ours, original, machine):
    """Print every check that RAN, with its verdict, and return the process's exit status."""
    control = mode == "titlefault"
    if control:
        colour_blind["the control's own soundness"] = check_the_fault_is_the_one_claimed(ours)
        colour_blind["the control moved exactly one pen"] = \
            check_only_the_faulted_pen_moved(ours, original)

    print(f"-- {mode} on {machine}: image base {ours['record']['image_base']:#x}, the original at "
          f"{original['base']:#x}, {ours['record']['vbl_ticks_at_anchor']} vblanks and "
          f"{ours['record']['psg_writes']} PSG writes at the anchor")
    print_the_boot_clock(ours["record"])
    # THE RAW PENS, unmasked, because PEN_MASK is three bits a gun and an STE implements FOUR
    # (docs/on-target-execution.md class 8). Every comparison in this file masks — it has to, or an
    # STF's bus noise would fail it — so the extra bit is invisible to all of them, and printing the
    # words is how an STE run says what the fourth bit actually read back.
    raw = struct.unpack(f">{PALETTE_PENS}H",
                        (ours["work"] / DUMP_PENS).read_bytes()[:PALETTE_PENS * PEN_BYTES])
    print(f"   pens read off the chip, unmasked: {' '.join(f'{pen:04x}' for pen in raw)}")
    for group, checks in (("must PASS", colour_blind),
                          ("must FAIL" if control else "must PASS", colour_sensitive)):
        for name, problems in sorted(checks.items()):
            verdict = "red " if problems else "green"
            print(f"   [{verdict}] {name}   ({group})")
            for problem in problems:
                print(f"           {problem}")

    failures = [name for name, problems in colour_blind.items() if problems]
    if control:
        unmoved = [name for name, problems in colour_sensitive.items() if not problems]
        for name in unmoved:
            print(f"   CONTROL FAILED: {name} stayed green under an injected palette fault")
        failures += unmoved
    else:
        failures += [name for name, problems in colour_sensitive.items() if problems]

    print("-- OK" if not failures else f"-- FAILED: {len(failures)} check(s)")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
