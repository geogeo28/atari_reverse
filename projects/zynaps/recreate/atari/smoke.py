#!/usr/bin/env python3
"""Judge ZYNAPS.PRG against the ORIGINAL binary, on named surfaces, headless.

    python3 atari/smoke.py title       # the M1 build: every surface must agree
    python3 atari/smoke.py titlefault  # its negative control: the verdict is INVERTED
    python3 atari/smoke.py title --keep # leave the captures and traces in atari/out/

Each build must exist — `atari/build.sh <mode>` writes `build/ZYNAPS-<mode>.PRG` and this reads it
from there, so the two never race over `disk/ZYNAPS.PRG`.

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
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]                      # projects/zynaps
REPO = PROJECT.parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(PROJECT / "tools"))

import st_pixels                                                       # noqa: E402
from hatari_headless import (                                          # noqa: E402
    HATARI, POLL_SECONDS, HeadlessSession, action_file, distinct_colours, locate_by_signature,
    log_faults, same_picture)
# The tick-frame cutter, borrowed rather than re-derived: `ref_capture.py` already parses Hatari's
# psg_write trace into the sound driver's own 10..0 flush frames, and re-spelling that here would be
# a second definition of what a frame IS (CLAUDE.md §5). Its TraceReader is incremental, which this
# does not need, but the alternative is a copy that can drift from the recorder's.
import ref_capture                                                     # noqa: E402

# --- the machine -----------------------------------------------------------------------------
TOS_ROM = REPO / "tools" / "hatari" / "TOS104US.img"
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

# Hardware stores the SHIM makes on its own account, so `hw_writes` can be predicted exactly rather
# than merely being non-zero: the resolution read-modify-write, the two video-base bytes, and the
# sixteen pens of the title palette; then, in the teardown, four PSG registers' worth (counted in
# psg_writes instead) and the sixteen pens TOS gets back.
SHIM_HW_WRITES = 1 + 2 + PALETTE_PENS
# ...and each PSG register write is two port stores, the select latch then the data port.
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

# The files the SHIM moves, which the original never touches. The trap-ledger check subtracts them
# by name so that what is left on our side is the GAME's own I/O and nothing else. Kept equal to
# zynaps_main.c's four FILE_* constants by `assert_the_shim_owns_these_names`, below.
SHIM_FILES = ("ZYNAPS.IMG", "BASE.BIN", "SCREEN.BIN", "STATE.BIN")
SHIM_MAIN = HERE / "zynaps_main.c"
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
RECORD_FIELDS = (
    ["magic", "fields",
     "image_base", "program_staged_bytes", "super_token",
     "ikbd_mouse_off", "ikbd_joystick_mode",
     "shifter_mode_writes", "shifter_mode_mask", "palette_uploads",
     "image_saved_vbl_vector", "tos_vbl_vector", "tos_timer_b_vector",
     "image_screen_back", "image_screen_front", "published_screen_base",
     "physbase_at_anchor", "raw_video_base_at_anchor", "rez_at_anchor",
     "vbl_ticks_at_anchor", "timer_b_ticks_at_anchor",
     "psg_writes", "psg_refused", "hw_writes",
     "file_opens", "file_open_failures", "file_refusals",
     "fault_pen", "smoke_vbls", "anchor_hold_vbls", "screen_bytes_written"]
    + [f"pen_at_entry_{pen}" for pen in range(PALETTE_PENS)]
    + [f"pen_at_anchor_{pen}" for pen in range(PALETTE_PENS)]
    + ["vbl_vector_after", "timer_b_vector_after", "physbase_after", "rez_after"]
    + [f"pen_after_{pen}" for pen in range(PALETTE_PENS)]
    + ["tail"])

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
def hatari_arguments(drive, auto, trace_file):
    """The whole Hatari command line for one side. Both sides get exactly this, bar the drive.

    --frameskips 0, --statusbar off and --drive-led off are the three settings that decide whether a
    screenshot comparison can succeed at all: without the first, Hatari emulates every frame but
    renders only some and `screenshot` grabs whichever was last drawn; without the third it paints
    an activity LED IN THE TOP-RIGHT BORDER, i.e. inside the photographed area, and the extra
    colours push its PNG writer from a palette image to a truecolour one so the two files can never
    match whatever the pixels do. All three are docs/on-target-execution.md class 8's measurements.
    """
    return [HATARI, "--tos", str(TOS_ROM), "--machine", "st", "--memsize", str(MEMSIZE_MB),
            "--monitor", "rgb", "--confirm-quit", "off", "--statusbar", "off",
            "--drive-led", "off", "--frameskips", "0", "--sound", "off",
            "--run-vbls", str(RUN_VBLS), "--trace", TRACE_FLAGS, "--trace-file", str(trace_file),
            "--harddrive", str(drive), "--auto", auto]


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


def run_ours(mode, out_dir, work):
    """Boot our .PRG, photograph it at its own anchor, and collect everything it wrote."""
    trace = out_dir / f"{mode}.trace"
    log = out_dir / f"{mode}.log"
    session = HeadlessSession(hatari_arguments(OUR_DISK, OUR_AUTO, trace),
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


def run_original(out_dir, work):
    """Boot the shipped binary the same way, and photograph it at the same point in its own boot."""
    trace = out_dir / "original.trace"
    log = out_dir / "original.log"
    session = HeadlessSession(hatari_arguments(ORIGINAL_DISK, ORIGINAL_AUTO, trace),
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
        base = poll_for_original(session)
        # The anchor is the FIRST frame of the tune, so the trace has almost none of it yet. Ours
        # has run for five seconds by its anchor and needs no such wait.
        wait_for_tick_frames(session, trace, TICK_FRAMES_COMPARED, "the original's")
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


def poll_for_original(session):
    """Where GEMDOS put the shipped .PRG, found by a relocation-verified signature search.

    A poll rather than one dump because it is also used where the program may not be loaded yet;
    called after the anchor has fired, the first attempt answers.
    """
    deadline = time.monotonic() + ANCHOR_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        found = locate_by_signature(session.savebin(RAM_DUMP_NAME, 0, ST_RAM_BYTES), ORIGINAL_PRG)
        if found is not None:
            return found
        session.require_alive("waiting for the original to be loaded")
        session.wait(1.0)
    raise SystemExit(f"{ORIGINAL_PRG.name} was never in RAM — the AUTO folder did not run it")


# =================================================================================================
# Reading what came back
# =================================================================================================
def read_record(path):
    """STATE.BIN as a dict, refusing anything that is not the record this file knows."""
    blob = Path(path).read_bytes()
    values = list(struct.unpack(f">{len(blob) // 4}I", blob[:len(blob) // 4 * 4]))
    if not values or values[0] != RECORD_MAGIC:
        raise SystemExit(f"{path}: not a Zynaps record (magic {values[:1]})")
    if values[1] != len(RECORD_FIELDS):
        raise SystemExit(f"{path}: the binary published {values[1]} fields and this file names "
                         f"{len(RECORD_FIELDS)} — zynaps_main.c's record moved and smoke.py did not")
    record = dict(zip(RECORD_FIELDS, values))
    if record["tail"] != RECORD_TAIL:
        raise SystemExit(f"{path}: no 'DONE' tail — the program did not finish writing it")
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
    for command in ("ikbd_mouse_off", "ikbd_joystick_mode"):
        if record[command] != 1:
            problems.append(f"{command}: the IKBD transmitter never went ready — the byte was "
                            f"NOT sent (zynaps_os.s's bounded wait spun out)")
    if record["psg_refused"]:
        problems.append(f"{record['psg_refused']} PSG writes named a register outside 0..15")
    if not record["psg_writes"]:
        problems.append("the sound driver never wrote the chip — no music")
    if record["timer_b_ticks_at_anchor"]:
        problems.append(f"Timer B fired {record['timer_b_ticks_at_anchor']} times, and nothing in "
                        f"M1 starts it")
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

    # ../src/init.c's own off-image ledger. `palette_uploads` exists because deleting the
    # `set_palette_title` call once left the whole differential green; asserting it here is what
    # stops that being true again on target.
    if record["palette_uploads"] != 1:
        problems.append(f"the slice made {record['palette_uploads']} title-palette uploads, not 1")
    if record["shifter_mode_writes"] != 1 or record["shifter_mode_mask"] != SHIFTER_MODE_MASK:
        problems.append(f"the resolution sink recorded {record['shifter_mode_writes']} write(s) "
                        f"with mask {record['shifter_mode_mask']:#x}, not 1 with "
                        f"{SHIFTER_MODE_MASK:#x} — and $ff8260 alone cannot say so, because TOS "
                        f"boots this machine in low resolution anyway")

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
    expected_hw = PSG_PORTS_PER_WRITE * record["psg_writes"] + SHIM_HW_WRITES
    if record["hw_writes"] != expected_hw:
        problems.append(f"{record['hw_writes']} hardware stores, expected {expected_hw} "
                        f"({PSG_PORTS_PER_WRITE} ports x {record['psg_writes']} PSG writes + "
                        f"{SHIM_HW_WRITES} the shim makes itself)")
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


def stage_our_build(mode):
    """Put the mode's .PRG where Hatari will auto-run it, and refuse a stale or missing one."""
    built = HERE / "build" / f"ZYNAPS-{mode}.PRG"
    if not built.is_file():
        raise SystemExit(f"no {built} — run `bash {HERE / 'build.sh'} {mode}` first")
    shutil.copy(built, OUR_DISK / OUR_PRG_NAME)
    # The shim's own outputs from a previous run would otherwise be read as this run's.
    for name in (BASE_FILE, STATE_FILE, SCREEN_FILE):
        (OUR_DISK / name).unlink(missing_ok=True)


# =================================================================================================
def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("title", "titlefault"))
    parser.add_argument("--out", type=Path, default=HERE / "out")
    parser.add_argument("--keep", action="store_true", help="leave the captures and dumps in --out")
    options = parser.parse_args()

    assert_the_shim_owns_these_names()
    out_dir = options.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stage_our_build(options.mode)

    with tempfile.TemporaryDirectory() as our_work, tempfile.TemporaryDirectory() as their_work:
        ours = run_ours(options.mode, out_dir, Path(our_work))
        original = run_original(out_dir, Path(their_work))

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
            "trap ledger": check_trap_ledger(ours, original),
            "memory (the framebuffer)": check_memory(ours, original),
            "timelines (the PSG tick frames)": check_timeline(ours, original),
        }

        if options.keep:
            for side, tag in ((ours, options.mode), (original, "original")):
                for name in (SHOT, DUMP_PENS, DUMP_REZ, DUMP_BASE_HIGH, DUMP_BASE_MID):
                    if (side["work"] / name).is_file():
                        shutil.copy(side["work"] / name, out_dir / f"{tag}_{name}")

        return report(options.mode, colour_sensitive, colour_blind, ours, original)


def report(mode, colour_sensitive, colour_blind, ours, original):
    """Print every check that RAN, with its verdict, and return the process's exit status."""
    control = mode == "titlefault"
    if control:
        colour_blind["the control's own soundness"] = check_the_fault_is_the_one_claimed(ours)
        colour_blind["the control moved exactly one pen"] = \
            check_only_the_faulted_pen_moved(ours, original)

    print(f"-- {mode}: image base {ours['record']['image_base']:#x}, the original at "
          f"{original['base']:#x}, {ours['record']['vbl_ticks_at_anchor']} vblanks and "
          f"{ours['record']['psg_writes']} PSG writes at the anchor")
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
