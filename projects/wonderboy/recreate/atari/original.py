#!/usr/bin/env python3
"""Boot the SHIPPED 1989 disks under Hatari and drive them to a named anchor.

    python3 atari/original.py title       # the TITLE screen at $e556, for the title differential
    python3 atari/original.py credits     # the CREDITS screen at $e5aa, one fire gate later
    python3 atari/original.py prompt      # the DATA-DISK PROMPT at $e4d6, ESC driven in the loop
    python3 atari/original.py dump        # the post-boot RAM, at the anchor, with its pins
    python3 atari/original.py neighbour   # ...and the MIS-ANCHOR measurement (see ANCHOR below)
    python3 atari/original.py variance    # ...and how much of it is NOT reproducible (see below)
    python3 atari/original.py frames [N]  # the shipped binary's first N frames, for the side-by-side
    python3 atari/original.py vecnoise    # ...and which of M5's registers are one boot's accident
    python3 atari/original.py flash  [N]  # ...the same, with WB_FLASH_TIMER armed (M5, see below)
    python3 atari/original.py flashnoise  # ...and the same accident measurement on the FLASHED boot
    python3 atari/original.py nofire      # NEGATIVE CONTROL: no fire injections -> no anchor
    python3 atari/original.py nodisk2     # NEGATIVE CONTROL: no data disk     -> no anchor

WHY THIS EXISTS. `gen_image.py`'s honesty line says a staged image is a declared fabrication of the
boot's result, and lists the six address ranges this project could not compute: the tile bitmaps,
the depacked overlay, the sprite descriptors and cell data, the eight pre-shifted scroll buffers and
both screens. Two of the routines that produce them ($e67e, `sprites_cru_install` $e87c) are not
merely unported but UNRECONSTRUCTED, so no host-side computation can reach them. The one reference
that can is the ORIGINAL's own RAM, and this file takes it.

RUNTIME ADDRESSES ARE GHIDRA ADDRESSES HERE, uniquely among this workspace's projects, and it is why
no load-base discovery step appears below: `startup_relocate_and_run` copies the body to the FIXED
absolute 0x400 and jumps there (../project.toml argues `load_base = 0x3f8` from exactly that), so
every address in ../names.txt is the address the CPU sees. It is PINNED rather than assumed —
`check_pins` compares a relocation-free window of the dump against the shipped file's own bytes.

============================  WHAT IS INJECTED, AND WHY EACH IS THE HUMAN  ====================

The boot chain is not headless: it stops twice for the player and once for the disk swap. Nothing
here patches the game — three debugger actions stand in for a person at the machine, each fired by
a `:once` breakpoint on the wait's own instruction:

  $e556 / $e55c   the TITLE screen's `clr.b $877 / tst.b $877 / bpl.s` then `tst.b $877 / bmi.s`
                  pair: press fire, release fire. The byte is WB_JOY1_STATE, which the original's
                  own `ikbd_acia_handler` files the joystick report into, so writing $80 to it is
                  the report a pushed stick would have produced.
  $e5ae / $e5b4   the CREDITS screen's identical pair.
  $e5ba           `stage_sequence_advance`'s first instruction, the last one before the overlay
                  load at $e5fa. Disk 1 carries only SWB.PRG, TITLESCR.RAD and CREDITS.RAD; every
                  overlay, TILEDATA.RAD and SPRITES.CRU are on disk 2. So the disk is swapped here,
                  which is what `show_data_disk_prompt` ($e494) asks a player to do.

BOTH ARE CONTROLLED. `nofire` and `nodisk2` remove one injection each and the anchor must NOT be
reached; without them "the boot ran" would rest on the injections being necessary rather than on
their being measured to be. (Measured: no fire leaves the machine on the title screen for as long
as it is given; no disk 2 hangs inside `load_resource_by_index`, which retries rather than failing
over to the prompt.)

===============================  THE ANCHOR, AND ITS MIS-ANCHOR  ==============================

Two addresses in the image hold `jmp $4a0.w`, $e708 and $f8b4. **ONLY $f8b4 IS LIVE**, and this file
uses it: $e6fc is `bsr.w $f89e`, $f89e falls off its own end into $f8b4's `jmp`, so the `bsr` never
returns and $e700/$e708 are dead. `../names.txt` cmt 0x4a0 listed both as entries until batch 43
phase B and now records this.

THE CENSUS BEHIND THAT, AT ITS FULL WIDTH — because a recipe narrower than its conclusion is how the
operand-hiding forms of batches 28 and 31 got missed twice. Every even offset of the relocated image
was scanned for: absolute LONG operands; bare words equal to the target; Bcc/BRA/BSR 8- AND 16-bit
displacements; DBcc 16-bit displacements; and EVERY `(d16,PC)` form — `jmp`, `jsr`, `lea`, `pea` and
any other extension-word-bearing opcode — resolved against the extension word's own address.

  $e708   ZERO hits under every form above.
  $e700   two bare words equal $e700, and NEITHER can be a reference. $ebb2 is the instruction
          `asl.b #3,d0`; $fbc6 is the low half of the immediate in `move.l #$4e700,$82b2.l`, a
          scroll-buffer address. And an absolute-SHORT operand sign-extends, so a 16-bit $e700 names
          $ffffe700 and could never reach $00e700 whatever it were part of.

AN ANCHOR IS ONLY EVIDENCE IF A MIS-ANCHOR IS DETECTABLE, so the neighbour is measured rather than
asserted to be different: `neighbour` dumps at $e6fc — the instruction that calls the stage load —
and reports how many bytes of the game-owned span differ from the $f8b4 dump. They are the whole
product of `stage_load_window`, so the two moments are hundreds of kilobytes apart and a one-anchor
slip could not pass for a hit.

The anchor is additionally pinned FROM THE INSIDE by state only a completed boot can leave —
`check_pins` — so a dump taken at the right PC of a run that went wrong still fails.

==========================  THE DUMP IS NOT BIT-REPRODUCIBLE, AND BY HOW MUCH  ================

Two dumps at the same PC of the same disks are NOT the same bytes, and a staged image that pretends
otherwise would be a fixture. `variance` measures it — two independent boots, differenced.

**THIS FILE OWNS THE FIGURE AND THE FIGURE MOVES.** Four boots measured 536, 538, 591 and 605 of
523,272 bytes, so what is true is a RANGE of roughly 500-650 and not any one of them; `variance`
prints the current reading and writes it to `build/VARIANCE.txt`, and every other surface
(atari/README.md, STATUS.md) cites this mode rather than restating a number that would be stale on
the next boot. It decomposes into four bands and nothing else, and each band carries a CEILING as
well as a range — a band is a weak guard on its own, since the sound band spans 13,604 bytes to
certify a couple of dozen:

  $f314..$f514   512 of them, every time, and they are the whole reason this mode exists. The
                 Copylock WRITES that band at run time and writes something DIFFERENT every boot:
                 the bytes are a descending, wrapping sequence, i.e. its own trace/timing samples
                 rather than code it recovered. So the band is not data, and staging it stages one
                 boot's scratch. It is inert here — no reconstructed function lies between
                 `copylock_illegal_handler` ($ee02) and `copylock_restore_state` ($f542), and
                 nothing under `../src/` ever reads there — but a claim that the image is "the
                 original's memory" has to say which of its bytes are one run's accident.
  $17adc..$1b000 12-22 bytes of the sound module's own state: a song is playing at the anchor and
                 its driver's cursors depend on which vblank the boot finished on. The bytes seen
                 moving sit in a much narrower run inside the band (~$17be4..$1aaea).
  $7f000..$80000 8-72 bytes of the game's stack, below its `movea.l #$80000,a7`.
  $74a           0 or 1 — WB_VBL_COUNTER, which vblank the boot happened to finish on. THE GUARD
                 FOUND THIS ONE: the first draft of the band table did not have it, the second boot
                 landed on a different count, and the mode named the address rather than passing.

WHAT THAT COSTS A FRAME DIFFERENTIAL, stated before it is spent: a comparison against a FRESH boot
of the original can only be exact for surfaces none of those bytes reaches. The framebuffer and
the sixteen pens are such surfaces — the Copylock band is never read, the sound state reaches the
YM2149 and not the shifter, and the stack is the boot's. A whole-memory comparison is not.
"""
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC = HERE.parent
sys.path.insert(0, str(REC / "test"))
from layout import wb                                            # noqa: E402

BIN = REC.parents[0] / "bin"
BUILD = HERE / "build"
OUT = HERE / "out"

# ---- the shipped disks ------------------------------------------------------------------------
# Pasti .stx, the uncracked Activision release. The names carry spaces and brackets, and HATARI'S
# DEBUGGER SPLITS `setopt` ON WHITESPACE — measured: it reported `Image '...(1989)(Activision)' not
# found` and carried on — so every run symlinks them into a temporary directory under a plain name.
DISK1 = BIN / "Wonderboy in Monsterland (1989)(Activision)(Disk 1 of 2)[a][!].stx"
DISK2 = BIN / "Wonderboy in Monsterland (1989)(Activision)(Disk 2 of 2)[a][!].stx"

# ---- the boot chain's own addresses, from out/wonderboy_dis.txt ---------------------------------
# Runtime == Ghidra (see the header). Each is the instruction quoted beside it.
TITLE_FIRE_PRESS_PC = 0xe556      # `tst.b $877.w`  / `bpl.s $e556` — wait for the stick's bit 7
TITLE_FIRE_RELEASE_PC = 0xe55c    # `tst.b $877.w`  / `bmi.s $e55c` — ...and for it to go away
CREDITS_WAIT_CLEAR_PC = 0xe5aa    # `clr.b $877.w` — WB_BOOT_CREDITS_END, the credits ANCHOR:
                                  # the instruction after boot_credits_screen's last and before the
                                  # wait below, so it collides with none of the four fire stops
CREDITS_FIRE_PRESS_PC = 0xe5ae    # the same pair after CREDITS.RAD
CREDITS_FIRE_RELEASE_PC = 0xe5b4
DATA_DISK_SWAP_PC = 0xe5ba        # `clr.w $6ef0.w`, stage_sequence_advance's first instruction
STAGE_LOAD_CALL_PC = 0xe6fc       # `bsr.w $f89e` — the NEIGHBOUR anchor, one call before the frame
BOOT_ANCHOR_PC = 0xf8b4           # `jmp $4a0.w` — THE ANCHOR: the boot's last instruction

# THE FOUR PCs `boot_script` PUTS ITS OWN `:once` BREAKPOINTS ON, as a set, so an anchor that lands
# on one can be refused rather than silently sharing an arrival with an injection.
FIRE_INJECTION_PCS = (TITLE_FIRE_PRESS_PC, TITLE_FIRE_RELEASE_PC,
                      CREDITS_FIRE_PRESS_PC, CREDITS_FIRE_RELEASE_PC)

# The fire button in the IKBD's joystick report, DERIVED FROM THE HEADER's bit number rather than
# written as 0x80 — the same constant `wonderboy_main.c`'s FIRE_DOWN_BIT shifts, so the poke this
# file makes into the shipped binary and the mask the shim's own waits test cannot name different
# bits (CLAUDE.md §5). The earlier spelling cited a header LINE, which had since moved onto
# WB_LOAD_OK.
FIRE_DOWN = 1 << wb("JOY1_FIRE_BIT")
FIRE_UP = 0x00
FIRST_HIT = 1                     # Hatari's hit counter is 1-based AND it rejects an explicit `:1`

# ---- the game's own address space ---------------------------------------------------------------
# What a staged image has to carry, and it is bounded by ../project.toml's three agreeing readings:
# `movea.l #$80000,a7` in hw_init_vectors, a screen clear covering exactly $70000..$7fd00, and no
# longword constant in the image at or above $80000. Below WB_STAGED_AT is the 68000 vector page,
# which belongs to whoever owns the machine and not to the image.
GAME_SPAN_END = 0x80000
WB_STAGED_AT = int(re.search(r"^load_base\s*=\s*(0x[0-9a-fA-F]+)",
                             (REC / "project.toml").read_text(), re.M).group(1), 16)

# ---- Hatari ---------------------------------------------------------------------------------
MEMSIZE_MB = 4
RAM_BYTES = MEMSIZE_MB << 20
# The measured boot: fire at VBL ~1200 and ~1370, overlay depacked at 1415, tiles installed at 1750,
# SPRITES.CRU installed at 2819, the anchor at 2854. 12000 is four times the whole chain, which is
# the margin the CONTROLS need — "the anchor was not reached" only means something if the run was
# long enough to reach it. The floppy is emulated at its real speed (no --fastfdc: the Copylock
# reads the disk itself, and speeding the FDC up is documented to break exactly that class).
RUN_VBLS = 12000
RUN_TIMEOUT = 600
DUMP_FILE = "ORIGRAM.BIN"
REGISTERS_FILE = "ORIGREGS.txt"
PENS_FILE = "ORIGPENS.BIN"
# What one anchor's capture leaves on the host, by file suffix. `run_original` collects exactly these
# out of the run's temporary directory — a set rather than "everything", so the debugger scripts and
# the symlinked disks are not swept up as artefacts.
PENS_SUFFIX, RESOLUTION_SUFFIX, SYNC_SUFFIX, PICTURE_SUFFIX = "pens", "rez", "sync", "png"
CAPTURE_SUFFIXES = frozenset((".bin", "." + PENS_SUFFIX, "." + RESOLUTION_SUFFIX,
                              "." + SYNC_SUFFIX, "." + PICTURE_SUFFIX))
# The shifter's sixteen colour registers, in the 32-bit form the debugger reads I/O space at. The
# register NUMBER has one definition — the reconstruction's own 24-bit WB_SHIFTER_PALETTE — and the
# high byte is the I/O page a 68000's address bus ignores. wonderboy_main.c derives its spelling the
# same way, from the same constant.
SHIFTER_IO_PAGE = 0xff000000
SHIFTER_PALETTE = SHIFTER_IO_PAGE | wb("SHIFTER_PALETTE")
PALETTE_PENS = wb("PALETTE_COLOURS")
PALETTE_BYTES = PALETTE_PENS * 2
# One ST low-res screen. THE ONE PYTHON DEFINITION, for ST_PEN_MASK's reason below: smoke.py imports
# it from here, and wonderboy_main.c's SCREEN_BYTES is the C spelling of the same two constants.
SCREEN_BYTES = wb("SCREEN_LINE") * wb("SCREEN_SCANLINES")
# The ST implements THREE bits per gun; the fourth bit of each nibble does not exist and a CPU read
# of a colour register returns it as whatever was last on the bus. So OUR side's pens (read by the
# program) carry that noise and the shipped side's (read by `savebin`, straight out of Hatari's
# register model) do not — masking it is the only way to compare the two reads honestly, and
# everything the machine can display is inside the mask. THE ONE PYTHON DEFINITION: smoke.py imports
# it from here rather than keeping its own, and wonderboy_main.c's ST_PEN_MASK is the C spelling.
ST_PEN_MASK = 0x0777


def pen_words(blob):
    """A palette dump's words, masked to the bits the hardware has.

    LENGTH FROM THE BLOB, not from PALETTE_PENS, so the one masking rule serves a single anchor's
    thirty-two bytes and a whole run's four anchors alike. Three copies of `& ST_PEN_MASK` is three
    places for the reason above it — the ST implements three bits per gun — to be edited in two."""
    return [word & ST_PEN_MASK for word in struct.unpack(">%dH" % (len(blob) // 2), blob)]


def c_constant(name):
    """One plain-integer `#define` out of wonderboy_main.c.

    THE SHIM'S CONSTANTS HAVE NO HEADER for ../test/layout.py to scrape, so this is how a number that
    lives in the C reaches the Python that checks it. A missing or non-literal define RAISES rather
    than defaulting: a check that silently substitutes its own idea of a constant is exactly the
    across-a-language-boundary drift CLAUDE.md §5 forbids.

    It lives HERE rather than in smoke.py because both files need it — smoke.py for the record
    formats, this file for the machine registers M5's vector reads — and two scrapers over one header
    is one scraper that quietly stops matching."""
    found = re.search(r"^#define\s+%s\s+(0[xX][0-9a-fA-F]+|\d+)u?\b" % name,
                      (HERE / "wonderboy_main.c").read_text(), re.M)
    if not found:
        raise SystemExit(f"{name} is not a plain-integer #define in wonderboy_main.c")
    return int(found.group(1), 0)


ANCHOR_BEACON = "ANCHOR_REACHED"
REGISTERS_BEACON = "REGISTERS_DUMPED"

HATARI_BANNER_RE = re.compile(r"Hatari v\d|WARN :|INFO :|Reading TOS")
FAULT_RE = re.compile(r"(Bus [Ee]rror|Address [Ee]rror|CPU halted|double bus)")
FAULT_PC_RE = re.compile(r"PC=(\$[0-9a-fA-F]+)")
# TOS sizes memory by faulting on purpose. Excused by the EXACT PC of the probe, never by "the PC is
# in ROM": a stale vector sends the CPU into ROM code, so a range test would excuse the very class
# this scan is for. smoke.py carries the same two and for the same reason.
MEMORY_PROBE_PCS = ("$e00d98", "$fc0174")


def find_tos():
    named = os.environ.get("WB_TOS_ROM")
    if named:
        return named
    for candidate in sorted((HERE.parents[3] / "tools" / "hatari").glob("TOS*.img"), reverse=True):
        return str(candidate)
    return None


def action_file(directory, name, *commands, tail="cont"):
    """Write one breakpoint's action file and return the `:file` clause that runs it.

    These are HOST paths the debugger reads and writes; they are deliberately not on any emulated
    drive, where the game could see them.

    `tail` is the last line, and it is `cont` for every anchor that hands the machine back — which
    is all of them but one: profile.py's window CLOSES on its breakpoint, so its action file ends in
    `q` instead. The parameter exists so that file still writes its script through here, rather than
    spelling `:file <path>` a second time to get a different last line."""
    path = directory / name
    path.write_text("".join(command + "\n" for command in commands) + tail + "\n")
    return f":file {path}"


def anchor_breakpoint(pc, hit, action):
    """One anchor's breakpoint line, and THE ONLY PLACE IT IS SPELLED.

    Hatari counts hits from 1 and REJECTS an explicit `:1`, so the first arrival is a bare `:once` —
    a parser quirk of the debugger, not a choice, and one that has to be got right identically on
    both sides of a differential. `boot_script` below and `smoke.py`'s own capture script both come
    through here, so the two cannot drift.

    `action` is an `action_file` clause."""
    count = "" if hit == FIRST_HIT else f":{hit} "
    return f"b pc = ${pc:x} {count}:once :quiet " + action


VBL_NEXT = "VBL"   # Hatari substitutes the counter's CURRENT value, i.e. "the next vblank"


def vbl_breakpoint(when, action, hit=FIRST_HIT):
    """A breakpoint on the emulator's own vblank counter, and THE ONLY PLACE IT IS SPELLED.

    `when` is either a vblank NUMBER — an absolute moment in the run — or `VBL_NEXT`, the
    stop-then-shoot idiom the rendered capture below needs. With `VBL_NEXT`, `hit` counts vblanks:
    the condition is true at every vblank from now on, so the Nth arrival IS N vblanks later.

    HATARI'S CONDITION PARSER TAKES A BARE VARIABLE OR A BARE NUMBER AND NOTHING ELSE, measured: it
    rejects `VBL+300` at the `+`, and `VBL > VBL + 300` at the first space. So "N vblanks after some
    other moment" cannot be written as a condition at all — the `hit` count above is the only way to
    express it, and it is why smoke.py's M3 arms BOTH of its tail readings from inside the action
    file of the breakpoint on the program's exit (`gemdos_breakpoint` below) rather than timing them
    off the run's own clock. An absolute count was M3's first design and its own control retired it.

    `action` is an `action_file` clause."""
    count = "" if hit == FIRST_HIT else f":{hit} "
    return f"b VBL > {when} {count}:once :quiet " + action


def gemdos_breakpoint(opcode, action):
    """A breakpoint on a GEMDOS trap, by function number — the third and last breakpoint spelling.

    Hatari's `GemdosOpcode` variable reads `$ffff` except on a `trap #1`, so this stops the machine
    inside the OS call rather than at an address the program has to be searched for. smoke.py's M3
    uses it on `Pterm0` to anchor its tail inspections on the program's OWN exit: an absolute vblank
    count cannot do that job, because a machine that has fallen over between the exit and the count
    is reset by TOS — and a reset restores the very vectors the hand-back control needs to stay
    broken. `action` is an `action_file` clause."""
    return f"b GemdosOpcode = {opcode} :once :quiet " + action


def refuse_repeated_arrivals(stops):
    """Refuse a script that sets two breakpoints on the same PC AND the same arrival.

    The invariant is per ARRIVAL, not per PC: the frame differential deliberately sets N breakpoints
    on $4a0 told apart by their counts. What must not recur is two selecting the SAME hit — their
    counters interfere, and the measured consequence in the sibling project was captures and dumps
    arriving from different moments and being compared as if from one. `stops` is (pc, hit) pairs."""
    stops = list(stops)
    if len(set(stops)) != len(stops):
        raise SystemExit("two breakpoints select the same arrival at the same PC: their counters "
                         "interfere, and the anchors would fire at moments other than the ones "
                         "asked for. Give each anchor ONE breakpoint whose action file does all of "
                         "that anchor's work.")


def poke_byte(addr, value):
    return f"w b ${addr:x} ${value:x}"


def poke_word(addr, value):
    return f"w w ${addr:x} ${value:x}"


def boot_script(directory, disk2, extra_stops=()):
    """The debugger script that carries the shipped binary from power-on to the frame loop.

    `extra_stops` is a list of (pc, hit, action-file name, [command, ...]) the caller anchors its own
    work at — one breakpoint per anchor, whose action file does all of that anchor's work. Shared by
    the dump below and by smoke.py's frame differential, so the injections that make the shipped
    side comparable have ONE spelling and cannot drift between the two runs that are compared.

    `hit` is which arrival at `pc` to stop on, 1-based as Hatari counts them; `anchor_breakpoint`
    owns the spelling and `refuse_repeated_arrivals` owns the guard, so smoke.py's own capture script
    goes through the same two rather than round them — which its first draft did."""
    joy1 = wb("JOY1_STATE")
    lines = [
        f"b pc = ${TITLE_FIRE_PRESS_PC:x} :once :quiet "
        + action_file(directory, "FIRE1D.INI", "echo TITLE_FIRE_DOWN", poke_byte(joy1, FIRE_DOWN)),
        f"b pc = ${TITLE_FIRE_RELEASE_PC:x} :once :quiet "
        + action_file(directory, "FIRE1U.INI", "echo TITLE_FIRE_UP", poke_byte(joy1, FIRE_UP)),
        f"b pc = ${CREDITS_FIRE_PRESS_PC:x} :once :quiet "
        + action_file(directory, "FIRE2D.INI", "echo CREDITS_FIRE_DOWN", poke_byte(joy1, FIRE_DOWN)),
        f"b pc = ${CREDITS_FIRE_RELEASE_PC:x} :once :quiet "
        + action_file(directory, "FIRE2U.INI", "echo CREDITS_FIRE_UP", poke_byte(joy1, FIRE_UP)),
    ]
    if disk2 is not None:
        lines.append(f"b pc = ${DATA_DISK_SWAP_PC:x} :once :quiet "
                     + action_file(directory, "SWAP.INI", "echo DATA_DISK_INSERTED",
                                   f"setopt --disk-a {disk2}"))
    refuse_repeated_arrivals((pc, hit) for pc, hit, _, _ in extra_stops)
    for pc, hit, name, commands in extra_stops:
        lines.append(anchor_breakpoint(pc, hit, action_file(directory, name, *commands)))
    return "\n".join(lines) + "\n"


def run_original(build_script, tag, run_vbls=RUN_VBLS, fires=True, trace=None):
    """Boot disk 1 and run `build_script(directory, disk2_path)` against it.

    Returns (produced files, merged Hatari output, exit status). THE STREAMS ARE MERGED because
    Hatari writes its logging AND all debugger output to stderr; a parser reading stdout scans an
    empty string for ever, which is a measured year-long blindness in the sibling project.

    `trace` is a Hatari `--trace` flag list, which is M6's instrument: the ordered stream of writes
    that reached the hardware, rather than a snapshot of where they left it."""
    rom = find_tos()
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for name, image in (("d1.stx", DISK1), ("d2.stx", DISK2)):
            if not image.exists():
                raise SystemExit(f"{image} is missing — this mode needs the shipped .stx disks")
            (directory / name).symlink_to(image)
        script = build_script(directory, directory / "d2.stx")
        if not fires:
            script = "\n".join(line for line in script.splitlines() if "FIRE" not in line) + "\n"
        (directory / "CMD.INI").write_text(script)
        # `--drive-led off` alongside `--statusbar off`: with the statusbar hidden Hatari draws an
        # activity LED in the top-right BORDER, which is emulator chrome inside the photographed
        # area. It is passed on EVERY mode rather than only the photographing ones because it is a
        # display-layer overlay that changes no emulated cycle — smoke.py's `run_hatari` has the
        # measurement that made it necessary.
        args = ["hatari", "--sound", "off", "--fast-forward", "on", "--confirm-quit", "off",
                "--statusbar", "off", "--drive-led", "off",
                "--memsize", str(MEMSIZE_MB), "--monitor", "rgb",
                "--run-vbls", str(run_vbls), "--disk-a", str(directory / "d1.stx"),
                "--parse", str(directory / "CMD.INI")]
        if rom:
            args[1:1] = ["--tos", rom]
        # `--frameskips 0` ON EVERY MODE, not only the photographing ones. Under --fast-forward Hatari
        # SKIPS RENDERING frames it still emulates, so `screenshot` grabs whichever frame was last
        # drawn — the shipped side's first pictures came back with the default 5-frame skip and no two
        # runs agreed. Asking for every frame narrows the window; it does not close it, which is why
        # atari/README.md §10's rendered claim is bounded by a measurement.
        #
        # AN EARLIER DRAFT PASSED IT ONLY FOR `frames`/`flash`/`vecnoise`, and that was the mistake:
        # it split this file's runs into two emulator configurations, with `variance`'s per-band
        # ceilings measured under one and the `frames` artefacts M2 and M5 compare against produced by
        # the other. Frameskip is a HOST-side draw decision and changes no emulated cycle, so one
        # configuration for every mode costs nothing and removes a difference nobody was measuring.
        args += ["--frameskips", "0"]
        if trace is not None:
            args += ["--trace", trace]
        env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
        done = subprocess.run(args, env=env, stdin=subprocess.DEVNULL, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=RUN_TIMEOUT)
        # ONE LOG PER MODE, kept whether the mode passed or not. A single shared filename would let
        # the control's run overwrite the dump's, and the two are read together when a mode is
        # argued about.
        OUT.mkdir(exist_ok=True)
        (OUT / f"original-{tag}.log").write_text(done.stdout)
        if not HATARI_BANNER_RE.search(done.stdout):
            raise SystemExit(f"FAIL: Hatari's output carries none of its own logging (status "
                             f"{done.returncode}) — every check below would read an empty string")
        produced = {path.name: path.read_bytes()
                    for path in directory.iterdir()
                    if path.suffix.lower() in CAPTURE_SUFFIXES}
        return produced, done.stdout, done.returncode


def machine_faults(log):
    """The log's faults, minus TOS's own memory-sizing probe, by EXACT PC."""
    faults = []
    for line in log.splitlines():
        if not FAULT_RE.search(line):
            continue
        where = FAULT_PC_RE.search(line)
        if where and where.group(1) in MEMORY_PROBE_PCS:
            continue
        faults.append(line.strip())
    return faults


# ---- M5: the HARDWARE-STATE VECTOR, and the rendered picture -------------------------------------
#
# THE ONE SPELLING, FOR BOTH SIDES. The commands that TAKE a capture and the parser that READS it
# back live here together, and smoke.py drives both sides through them — so the reconstruction's run
# and the shipped binary's cannot drift into measuring different things. Joust's writer and reader
# each grew their own idea of the marker terminator and every one of its frame modes died at the
# first anchor; one definition is the fix.
#
# WHAT IS HONESTLY CAPTURABLE, and what each entry really is:
#   * the sixteen PENS, the RESOLUTION register and the SYNC register are read out of I/O space by
#     `savebin` — genuine reads of the emulated hardware, at the same addresses and the same widths
#     wonderboy_main.c's own read-backs use;
#   * the VIDEO BASE, the REFRESH RATE and the V-OVERSCAN come from the debugger's `info video`;
#   * the sixteen YM-2149 registers come from `info ym`, and THIS ONE IS NOT A HARDWARE READ. The
#     PSG's register file cannot be read through $ff8800 without first writing a select, which is
#     itself a write with side effects, so there is no honest read to take. `info ym` reports
#     HATARI'S MODEL of the chip — the values it has been written. That is the right capture for a
#     differential, because both sides are measured the same way and a register one program sets and
#     the other does not still shows up; what it cannot witness is anything the real chip would do
#     that the model does not.
VECTOR_MARKER_PREFIX, VECTOR_MARKER_END = "VECTOR-", "."
# The terminator is what keeps `VECTOR-OUR-1` from also matching `VECTOR-OUR-10`.
VECTOR_MARKER_RE = re.compile(VECTOR_MARKER_PREFIX + r"[A-Z]+-\d+" + re.escape(VECTOR_MARKER_END))
# Which side a capture came from. Load-bearing twice — it names the files on disk AND the `echo`
# marker the log is split on — so it has one definition rather than a literal at each site.
OUR_TAG, THEIR_TAG = "OUR", "THEIR"

# The two single-register reads, in the 32-bit form the debugger addresses I/O space at. Scraped from
# wonderboy_main.c rather than restated: that file's `snapshot`/`install` write and read back these
# very registers, and a second spelling here would be a differential against an address the shim
# never touched. Read as ONE BYTE each, which is the width the shim's own `io8` reads use.
SHIFTER_RESOLUTION = c_constant("SHIFTER_RES")
SHIFTER_SYNC = c_constant("SHIFTER_SYNC")
REGISTER_BYTE = 1
# THE RESOLUTION REGISTER IS TWO BITS WIDE and the other six read back as whatever was last on the
# bus — atari/README.md's on-target bug #2, found by an unmasked read-back failing against a machine
# that had done exactly what it was told. Same constant the shim masks with.
ST_RESOLUTION_MASK = c_constant("SHIFTER_RES_MASK")
# $ff820a implements TWO bits — 0 external sync, 1 the 50/60 Hz select `video_set_lowres_50hz` writes
# — and the rest float, so the same reasoning applies one register over. The mask is wider than the
# shim's own read-back (which checks only the 50 Hz bit) because this is a DIFFERENTIAL: bit 0 is a
# real bit both sides have and neither writes, so comparing it is free evidence rather than noise.
ST_SYNC_MASK = 0x03
YM_REGISTERS = 16
# How many entries the vector must COMPARE, so that a capture or a parser going quiet is a RED rather
# than an `IDENTICAL` printed over a stump: the pens, the YM file, and the four singletons
# (resolution, sync, refresh rate, V-overscan). VECTOR_REPORT_ONLY's names are not compared and are
# not counted here.
VECTOR_SINGLETONS = ("resolution", "sync", "refresh_hz", "v_overscan")
VECTOR_REGISTERS = PALETTE_PENS + YM_REGISTERS + len(VECTOR_SINGLETONS)
# CAPTURED AND PRINTED, BUT NOT COMPARED. The two sides legitimately draw from different addresses —
# ours inside a GEMDOS-placed image, the shipped binary in the 512 KB map it owns outright — and the
# other three are the emulator's own position in its run, not the machine's state. Named explicitly
# rather than inferred from a spelling convention, so what is exempt is a list one can read.
VECTOR_REPORT_ONLY = ("video_base", "vbl_counter", "hbl_line", "frame_skips")
# `info video`'s lines, as (name, pattern). Everything here is parsed; VECTOR_REPORT_ONLY above is
# what decides which of them the differential then looks at.
VIDEO_INFO_FIELDS = (("video_base", r"Video base\s*:\s*(0x[0-9a-fA-F]+)"),
                     ("vbl_counter", r"VBL counter\s*:\s*(\d+)"),
                     ("hbl_line", r"HBL line\s*:\s*(\d+)"),
                     ("v_overscan", r"V-overscan\s*:\s*(\S+)"),
                     ("refresh_hz", r"Refresh rate\s*:\s*(\d+)"),
                     ("frame_skips", r"Frame skips\s*:\s*(\d+)"))
YM_INFO_RE = re.compile(r"Reg \$([0-9A-F]{2}) : \$([0-9A-F]{2})")


def vector_marker(tag, index):
    return f"{VECTOR_MARKER_PREFIX}{tag}-{index}{VECTOR_MARKER_END}"


def capture_name(tag, index, suffix):
    """What one anchor's capture of `suffix` is CALLED. Same reason as the marker: the debugger
    script that WRITES these and the compare that READS them are far apart, so they share one
    spelling instead of each carrying their own."""
    return f"{tag}{index}.{suffix}"


def capture_path(directory, tag, index, suffix):
    return Path(directory) / capture_name(tag, index, suffix)


def vector_commands(directory, tag, index):
    """The debugger commands that take one anchor's hardware-state vector, WHERE THE ANCHOR FIRES.

    Not at the following vblank, which is where the picture below is taken: this is the same instant
    the two sides' framebuffers and pens are compared at, so the vector's own pens cross-check that
    comparison through an entirely different path — `savebin` off the register file against a CPU
    read by the running program."""
    return [f"echo {vector_marker(tag, index)}", "info video", "info ym",
            f"savebin {capture_path(directory, tag, index, PENS_SUFFIX)} "
            f"${SHIFTER_PALETTE:x} {PALETTE_BYTES}",
            f"savebin {capture_path(directory, tag, index, RESOLUTION_SUFFIX)} "
            f"${SHIFTER_RESOLUTION:x} {REGISTER_BYTE}",
            f"savebin {capture_path(directory, tag, index, SYNC_SUFFIX)} "
            f"${SHIFTER_SYNC:x} {REGISTER_BYTE}"]


def picture_command(directory, tag, index):
    """STOP-THEN-SHOOT: arm a breakpoint at the NEXT vblank, and photograph there.

    `screenshot` renders the emulator's display surface, which is built scanline by scanline, so a
    capture taken where the anchor happens to fire mixes that frame with the one before —
    deterministic only if the picture is static. `VBL_NEXT` holds the machine until a frame boundary,
    where the surface holds one completed frame.

    A SECOND STOP RATHER THAN A SECOND TOP-LEVEL BREAKPOINT: two breakpoints selecting the same
    arrival interfere with each other's counters, which is what `boot_script`'s duplicate guard is
    for. This one is armed from inside the anchor's own action file and disarms itself."""
    shot = Path(directory) / f"{tag}SHOT{index}.INI"
    shot.write_text(f"screenshot {capture_path(directory, tag, index, PICTURE_SUFFIX)}\ncont\n")
    return vbl_breakpoint(VBL_NEXT, f":file {shot}")


def read_capture(captures, tag, index, suffix, frame):
    """One capture artefact out of {filename: bytes}, or a failure that names the ANCHOR.

    The likeliest failure of the whole capture path is an anchor that never fires, and its symptom is
    a missing file. A bare KeyError points at a filename; this points at the moment."""
    name = capture_name(tag, index, suffix)
    if name not in captures:
        raise SystemExit(f"no {suffix} capture from the {tag} side at frame {frame} (anchor "
                         f"{index}) — the anchor never fired, or its capture chain did not run")
    return captures[name]


def hardware_vector(log, captures, tag, index, frame):
    """One anchor's hardware-state vector, as a dict of named registers.

    `captures` is {filename: bytes} — what the run left behind — so the shipped side and ours reach
    this through the same reader whether their files came off a temporary drive or a script dir."""
    # THE BODY IS CUT AT THE NEXT MARKER. Without the cut it runs to the end of the whole log, a
    # findall over it collects every LATER anchor's `info ym` block too, and every anchor ends up
    # holding the LAST one's registers — sixteen of the compared entries would be one measurement
    # repeated four times, exactly the vacuity this surface exists to remove.
    block = log.split(vector_marker(tag, index), 1)
    if len(block) < 2:
        raise SystemExit(f"no hardware-state vector for anchor {index} ({tag}, frame {frame}) — the "
                         f"capture breakpoint never fired")
    body = VECTOR_MARKER_RE.split(block[1], maxsplit=1)[0]
    vector = {}
    for name, pattern in VIDEO_INFO_FIELDS:
        found = re.search(pattern, body)
        if found:
            vector[name] = found.group(1)
    for register, value in YM_INFO_RE.findall(body):
        vector[f"ym{int(register, 16):02d}"] = int(value, 16)
    for pen, word in enumerate(pen_words(read_capture(captures, tag, index, PENS_SUFFIX, frame))):
        vector[f"pen{pen:02d}"] = word
    vector["resolution"] = (read_capture(captures, tag, index, RESOLUTION_SUFFIX, frame)[0]
                            & ST_RESOLUTION_MASK)
    vector["sync"] = read_capture(captures, tag, index, SYNC_SUFFIX, frame)[0] & ST_SYNC_MASK
    return vector


# ---- the pins ------------------------------------------------------------------------------
# WHAT MAKES THIS DUMP THE RIGHT MOMENT, from the inside. Each is state the shipped .PRG does NOT
# carry and only a completed boot leaves, so a dump of a run that went wrong fails here even though
# its PC was right. The addresses come from ../include/wonderboy.h through layout.py; the values are
# the boot's own operands, quoted from out/wonderboy_dis.txt.
VEC_LEVEL4_VBL = 0x70
VEC_MFP_ACIA = 0x118
VBL_HANDLER_PC = 0x716            # `move.l #$716,$70.w` — hw_init_vectors ($f8bc), and again $e506
ACIA_HANDLER_PC = 0x754           # `move.l #$754,$118.w` — the same routine
RESOURCE_SIGNATURE = 0x45         # 'E', stamped by resource_table_relocate ($fe1e). NOT idempotent,
                                  # which is what the signature exists for, and zero in the .PRG.
STAGE_START_PTR_VALUE = 0x217d8   # `lea $217d8.l,a1` at $f8aa, latched by stage_load_window
FIRST_STAGE_NUMBER = 1            # level_seq_table[0][3] -> $bd88; the first playable stage

# A window of the program body with no relocation site in it and no runtime writer: what makes the
# dump's addresses comparable with ../names.txt's at all. Chosen inside game_main_loop's own code,
# which is executed and never written.
CODE_WINDOW = (0x4a0, 0x50a)


def check_pins(ram, prg_image):
    """(problems, notes) for a dump that claims to be the original's post-boot RAM."""
    def long_at(addr):
        return struct.unpack(">I", ram[addr:addr + 4])[0]

    def word_at(addr):
        return struct.unpack(">H", ram[addr:addr + 2])[0]

    lo, hi = CODE_WINDOW
    pins = [
        ("the program is at its Ghidra addresses", bytes(prg_image[lo:hi]) == ram[lo:hi],
         f"{hi - lo} bytes of game_main_loop's own code at {lo:#x}"),
        ("the VBL vector holds vbl_handler", long_at(VEC_LEVEL4_VBL) == VBL_HANDLER_PC,
         f"${VEC_LEVEL4_VBL:x} = {long_at(VEC_LEVEL4_VBL):#x}, want {VBL_HANDLER_PC:#x}"),
        ("the ACIA vector holds ikbd_acia_handler", long_at(VEC_MFP_ACIA) == ACIA_HANDLER_PC,
         f"${VEC_MFP_ACIA:x} = {long_at(VEC_MFP_ACIA):#x}, want {ACIA_HANDLER_PC:#x}"),
        ("the resource table is relocated", ram[wb("RESOURCE_HEADER")] == RESOURCE_SIGNATURE,
         f"{wb('RESOURCE_HEADER'):#x} = {ram[wb('RESOURCE_HEADER')]:#04x}, want "
         f"{RESOURCE_SIGNATURE:#04x} ('E')"),
        ("stage_load_window latched the map", long_at(wb("STAGE_MAP_PTR")) == wb("MAP_ROW_STRIDE"),
         f"{wb('STAGE_MAP_PTR'):#x} = {long_at(wb('STAGE_MAP_PTR')):#x}, want "
         f"{wb('MAP_ROW_STRIDE'):#x}"),
        ("...and the start record", long_at(wb("STAGE_START_PTR")) == STAGE_START_PTR_VALUE,
         f"{wb('STAGE_START_PTR'):#x} = {long_at(wb('STAGE_START_PTR')):#x}, want "
         f"{STAGE_START_PTR_VALUE:#x}"),
        ("the first stage is loaded", word_at(0xbd88) == FIRST_STAGE_NUMBER,
         f"stage number = {word_at(0xbd88)}, want {FIRST_STAGE_NUMBER}"),
    ]
    problems = [f"{name} ({detail})" for name, ok, detail in pins if not ok]
    return problems, [f"{'ok  ' if ok else 'FAIL'} {name}: {detail}" for name, ok, detail in pins]


# ---- the modes -------------------------------------------------------------------------------

def dump_at(pc, tag):
    """Run the shipped disks to `pc` and return the whole of RAM there, or None."""
    def script(directory, disk2):
        return boot_script(directory, disk2, extra_stops=[
            (pc, FIRST_HIT, "ANCHOR.INI", [f"echo {ANCHOR_BEACON}",
                                f"savebin {directory / DUMP_FILE} 0 {RAM_BYTES:#x}",
                                # THE ENTRY REGISTERS ARE PART OF THE MOMENT. `game_main_loop` is
                                # `jmp`ed into, not called, so the frame it runs inherits whatever
                                # the boot left — and its one C argument, `sprite_pass_regs`, is
                                # exactly that inheritance (blit.h: a5 is a real input).
                                # ...AND THE SIXTEEN PENS, which are the boot's product too and do
                                # NOT live in RAM. `set_palette` runs inside the unported boot
                                # chain, so a build that stages only memory paints its frame
                                # through whatever the DESKTOP left in the shifter — measured on
                                # the first M2 run, which came back with TOS 1.04's own palette.
                                f"savebin {directory / PENS_FILE} ${SHIFTER_PALETTE:x} "
                                f"{PALETTE_BYTES}",
                                "cpureg", f"echo {REGISTERS_BEACON}"])])

    produced, log, status = run_original(script, tag)
    print(f"-- {tag}: anchor ${pc:x}, hatari exit={status} "
          f"(full log in {OUT / ('original-%s.log' % tag)})")
    faults = machine_faults(log)
    if faults:
        raise SystemExit("FAIL: unhealthy machine: " + " | ".join(faults[:4]))
    if ANCHOR_BEACON not in log:
        return None, None, None
    return produced.get(DUMP_FILE), registers_at_anchor(log), produced.get(PENS_FILE)


# `cpureg`'s block, between the two beacons the action file brackets it with. Kept VERBATIM as the
# evidence and parsed for the one register the port needs, rather than parsed into a dict nobody
# reads: which registers matter is `../include/blit.h`'s question, not this file's.
REGISTER_RE = re.compile(r"\b([DA][0-7])\s*[:=]?\s*\$?([0-9a-fA-F]{8})\b")


def registers_at_anchor(log):
    """The `cpureg` text the anchor printed, or None."""
    start = log.find(ANCHOR_BEACON)
    end = log.find(REGISTERS_BEACON, start + 1)
    if start < 0 or end < 0:
        return None
    return log[start + len(ANCHOR_BEACON):end]


def register(text, name):
    for found, value in REGISTER_RE.findall(text or ""):
        if found == name:
            return int(value, 16)
    return None


def shipped_image():
    sys.path.insert(0, str(HERE.parents[3] / "tools"))
    from recreate_kit import project
    project.load(REC)
    import loader
    return loader.load_image(str(BIN / "disk1" / "AUTO" / "SWB.PRG")), loader.PROGRAM_END


def mode_dump():
    ram, registers, pens = dump_at(BOOT_ANCHOR_PC, "dump")
    if ram is None:
        raise SystemExit(f"FAIL: the boot never reached ${BOOT_ANCHOR_PC:x}")
    image, program_end = shipped_image()
    problems, notes = check_pins(ram, image)
    for note in notes:
        print(f"   {note}")
    if problems:
        raise SystemExit("FAIL: " + "; ".join(problems))

    # EVERY CHECK BEFORE EVERY WRITE, and that ordering is the whole point.
    #
    # The three artefacts are ONE MEASUREMENT of ONE BOOT, and `build.sh m2`'s precondition can only
    # see whether each file exists. An earlier draft wrote the RAM, then validated the registers,
    # then wrote them, then validated the palette — so a boot whose `cpureg` block did not parse
    # left THIS boot's RAM beside the PREVIOUS boot's registers and palette. All three exist, the
    # build proceeds, and the image and A5 come from one boot while the sixteen pens come from
    # another; the resulting frame mismatch reads as a rendering bug. Validate all three, then
    # write all three.
    unwind = register(registers, "A5") if registers else None
    if registers is None or unwind is None:
        raise SystemExit("FAIL: the anchor dumped memory but no readable register file — "
                         "`game_main_loop`'s entry state would then be chosen here, not measured")
    if pens is None or len(pens) != PALETTE_BYTES:
        raise SystemExit(f"FAIL: the anchor did not dump {PALETTE_BYTES} bytes of palette — a frame "
                         f"staged without it is painted through whoever owned the shifter last")

    span = ram[WB_STAGED_AT:GAME_SPAN_END]
    BUILD.mkdir(exist_ok=True)
    # Identifies THIS boot's set of three. A digest of the three payloads rather than a clock: two
    # boots a second apart must get different ids, and two boots that somehow produced identical
    # bytes are the same measurement and may share one.
    boot_id = hashlib.sha256(span + registers.encode() + pens).hexdigest()[:16]
    # The manifest is stamped AFTER all three land, so an interrupted set has no manifest to match.
    (BUILD / MANIFEST_FILE).unlink(missing_ok=True)
    (BUILD / DUMP_FILE).write_bytes(span)
    (BUILD / REGISTERS_FILE).write_text(registers)
    (BUILD / PENS_FILE).write_bytes(pens)
    print(f"{write_manifest(boot_id)}: stamps this boot over "
          f"{', '.join(MANIFEST_ARTEFACTS)}")
    print(f"{BUILD / REGISTERS_FILE}: the entry register file, A5 (the sprite pass's `unwind`) = "
          f"{unwind:#010x}")
    print(f"{BUILD / PENS_FILE}: the sixteen pens the boot left — " + " ".join(
        "%03x" % pen for pen in pen_words(pens)))
    print(f"{BUILD / DUMP_FILE}: {len(span)} bytes "
          f"[{WB_STAGED_AT:#x},{GAME_SPAN_END:#x}) — the game's whole address space at the anchor")
    same = sum(1 for i in range(WB_STAGED_AT, program_end) if image[i] == ram[i])
    print(f"program span [{WB_STAGED_AT:#x},{program_end:#x}): {same} of "
          f"{program_end - WB_STAGED_AT} bytes are the shipped file's own "
          f"({program_end - WB_STAGED_AT - same} differ — see gen_image.py's provenance table)")
    return True


# How far above the measured boot-to-boot noise a mis-anchor has to sit before it counts as
# DETECTABLE. Ten times: the noise is ~600 bytes and the real margin is ~134,000, so the factor is
# not tuned to squeeze a pass — it is loose enough to be obviously satisfied and tight enough that a
# same-moment pair (which sits AT the noise) cannot clear it.
MIS_ANCHOR_FLOOR_MULTIPLE = 10


def differing_addresses(first, second, base=WB_STAGED_AT):
    """Every Ghidra address at which two staged spans differ.

    ONE WALK, AND EVERY FIGURE ON EITHER SHORE COMES OFF IT. `mode_variance`'s band table, this
    file's own mis-anchor margin and `smoke.py`'s band diff all count the same thing over the same
    two spans, and each of the three once had its own comprehension. That matters most in
    `smoke.py`'s mis-anchor control, which compares a NUMERATOR it computes against a FLOOR this
    module measured: two implementations of one measurement there is a control grading itself with a
    different instrument from the one it is controlling."""
    return [base + at for at, (mine, theirs) in enumerate(zip(first, second)) if mine != theirs]


def span_difference(first, second):
    """How many bytes of two staged spans differ."""
    return len(differing_addresses(first, second))


def mode_neighbour():
    """THE MIS-ANCHOR MEASUREMENT, against the noise floor the instrument actually measures.

    AN EARLIER DRAFT ASSERTED `differ == 0` AND COULD NEVER FIRE. Two dumps of the SAME moment
    already differ by ~600 bytes (the copylock's scratch alone is 512), so "not byte-identical" is
    true of every pair this tool can produce, including two boots stopped at the same instruction.
    The assertion passed for the right reason and would have passed for the wrong one.

    So the floor is derived from `mode_variance`'s reading and CHECKED IN BOTH DIRECTIONS in one
    run: the real mis-anchor must clear it, and a pair the instrument knows is the SAME moment —
    the two same-anchor boots variance already differenced — must not. Without the second half the
    floor is a number nobody has shown is discriminating."""
    anchor = BUILD / DUMP_FILE
    same_moment = BUILD / SECOND_DUMP_FILE
    reading = BUILD / VARIANCE_FILE
    for needed in (anchor, same_moment, reading):
        if not needed.exists():
            raise SystemExit(f"run `original.py dump` and then `original.py variance` first — "
                             f"{needed} is what this measures against")
    noise = int(reading.read_text().strip())
    floor = noise * MIS_ANCHOR_FLOOR_MULTIPLE
    at_anchor = anchor.read_bytes()
    # THE KEPT SPAN GOES BEFORE THE BOOT, not only after the checks. `smoke.py boot` reads it as its
    # own control, and a run of this mode that ends in a refusal must leave no artefact for that
    # control to be taken against — otherwise a failed re-measurement leaves the PREVIOUS one
    # standing and the control reports on evidence this session did not produce.
    (BUILD / NEIGHBOUR_DUMP_FILE).unlink(missing_ok=True)

    ram, _, _ = dump_at(STAGE_LOAD_CALL_PC, "neighbour")
    if ram is None:
        raise SystemExit(f"FAIL: the boot never reached ${STAGE_LOAD_CALL_PC:x}")
    before = ram[WB_STAGED_AT:GAME_SPAN_END]

    differ = span_difference(at_anchor, before)
    control = span_difference(at_anchor, same_moment.read_bytes())
    print(f"   boot-to-boot noise at the SAME anchor: {noise} bytes, so the floor is "
          f"{MIS_ANCHOR_FLOOR_MULTIPLE}x that = {floor}")
    print(f"   ${STAGE_LOAD_CALL_PC:x} (the `bsr.w $f89e` one call before the frame loop) against "
          f"${BOOT_ANCHOR_PC:x}: {differ} of {len(at_anchor)} bytes differ "
          f"({100.0 * differ / len(at_anchor):.1f}%)")
    print(f"   ...and the SAME-MOMENT control, two boots both stopped at ${BOOT_ANCHOR_PC:x}: "
          f"{control} bytes differ ({100.0 * control / len(at_anchor):.2f}%)")

    problems = []
    if differ <= floor:
        problems.append(f"the mis-anchor moved only {differ} bytes, at or under the {floor}-byte "
                        f"floor — a one-anchor slip is indistinguishable from boot-to-boot noise "
                        f"and the anchor is not evidence of anything")
    if control > floor:
        problems.append(f"two dumps of the SAME moment differ by {control} bytes, ABOVE the "
                        f"{floor}-byte floor — the floor does not separate a different moment from "
                        f"the same one, so clearing it means nothing")
    if problems:
        raise SystemExit("FAIL: " + "; ".join(problems))
    # KEPT, for `smoke.py boot`'s span control, and written only once both margins have held —
    # `mode_dump`'s rule, every check before every write. The file was unlinked before the boot, so
    # a run that reached neither check leaves none either.
    (BUILD / NEIGHBOUR_DUMP_FILE).write_bytes(before)
    print(f"OK: a one-call mis-anchor clears the floor by {differ / max(floor, 1):.0f}x and the "
          f"same moment does not reach it — the margin discriminates in both directions "
          f"({BUILD / NEIGHBOUR_DUMP_FILE} keeps the mis-anchored span)")
    return True


# THE BANDS THE IRREPRODUCIBLE BYTES MUST FALL IN, each with A CEILING ON HOW MANY.
#
# A band alone is a weak guard: the sound band spans 13,604 bytes to certify ~20, and the stack band
# 4,096 to certify ~69, so "it landed inside a named band" would stay true while the count grew a
# hundredfold. The header's claim is that the variance DECOMPOSES into these four and nothing else,
# and a claim that cannot be falsified is not one — so each band carries a ceiling set from the
# measured readings with headroom, and `mode_variance` reds on a band that grows into its slack as
# loudly as on a byte outside every band.
#
# (name, start, end, ceiling). Readings across four boots: copylock exactly 512 every time (it is a
# fixed-size scratch and the whole band turns over), sound 20-22, stack 56-72, counter 0-1.
VARIANCE_BANDS = (
    ("the copylock's scratch", 0xf314, 0xf514, 512),
    # The sound module's own span, `../project.toml`'s `0x17adc..0x1ab04` rounded up to the next
    # page. The bytes actually seen moving are a much narrower run inside it (~$17be4..$1aaea), and
    # the ceiling rather than the band is what pins the size.
    ("the sound module's state", 0x17adc, 0x1b000, 256),
    # The game sets its own A7 to $80000 and grows down; the deepest byte seen moving is ~$7ff0d.
    ("the game's stack", 0x7f000, GAME_SPAN_END, 512),
    # WHICH VBLANK THE BOOT FINISHED ON. The most obvious irreproducible word in the image and the
    # one this table was written without — the guard below found it and named the address. It is a
    # PHASE and not content: `flip_screen`'s two waits compare against it, so a frame differential
    # inherits an offset in the counter and not a difference in what is drawn.
    ("vbl_handler's counter", wb("VBL_COUNTER"), wb("VBL_COUNTER") + 2, 2),
)

# The second same-anchor boot and the reading it produced, kept for `mode_neighbour`'s floor: the
# mis-anchor margin is only meaningful against the noise this instrument actually measures.
SECOND_DUMP_FILE = "ORIGRAM2.BIN"
VARIANCE_FILE = "VARIANCE.txt"
# ...AND THE MIS-ANCHORED SPAN ITSELF, kept rather than measured and thrown away. `smoke.py boot`
# differences the RECOMPUTED post-boot image against `DUMP_FILE`; this is the same instrument's
# reading of a moment ONE CALL EARLIER, and it is what shows that comparison can fail. The floor it
# has to clear is `VARIANCE_FILE`'s — the same floor `mode_neighbour` uses, but NOT the same
# comparison: this mode counts every differing byte, where `smoke.py`'s control counts only the ones
# OUTSIDE its named bands. Band-excluding the numerator can only make it smaller, so that control
# clears the shared floor on strictly less evidence than this one does.
NEIGHBOUR_DUMP_FILE = "ORIGNEIG.BIN"

# ---- the boot manifest -------------------------------------------------------------------------
#
# THE THREE ARTEFACTS ARE ONE MEASUREMENT OF ONE BOOT, AND FILE-EXISTENCE CANNOT SAY SO. Validating
# all three before writing any of them narrows the window; it does not close it — three `write_bytes`
# calls are three moments, and an interrupt (or a full disk, or a Ctrl-C) between the first and the
# third leaves THIS boot's RAM beside the PREVIOUS boot's registers and palette. All three exist,
# `build.sh m2`'s `-f` test is satisfied, and the image and A5 come from one boot while the sixteen
# pens come from another — a frame mismatch that reads as a rendering bug.
#
# So the boot stamps a manifest: an id for the boot plus the size and digest of each artefact,
# WRITTEN LAST. `build.sh m2` verifies the three against it and refuses on any mismatch, so a
# half-written set is a loud refusal rather than a plausible build. The manifest being last is what
# makes it work — an interrupted run leaves no manifest, or an older one whose digests do not match.
MANIFEST_FILE = "ORIGBOOT.txt"
MANIFEST_ARTEFACTS = (DUMP_FILE, REGISTERS_FILE, PENS_FILE)


def artefact_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_manifest(boot_id):
    lines = [f"boot {boot_id}"]
    for name in MANIFEST_ARTEFACTS:
        path = BUILD / name
        lines.append(f"{name} {path.stat().st_size} {artefact_digest(path)}")
    (BUILD / MANIFEST_FILE).write_text("\n".join(lines) + "\n")
    return BUILD / MANIFEST_FILE


def check_manifest(build_dir):
    """(ok, message) for the artefact set in `build_dir`. Used by build.sh before an m2 build."""
    manifest = Path(build_dir) / MANIFEST_FILE
    if not manifest.exists():
        return False, (f"{manifest} is missing — the dump did not finish, or predates the manifest. "
                       f"Run `python3 atari/original.py dump`.")
    rows = [line.split() for line in manifest.read_text().split("\n") if line.strip()]
    boot = next((row[1] for row in rows if row[0] == "boot"), None)
    seen = {row[0]: (int(row[1]), row[2]) for row in rows if row[0] != "boot"}
    if set(seen) != set(MANIFEST_ARTEFACTS):
        return False, f"{manifest} lists {sorted(seen)}, expected {sorted(MANIFEST_ARTEFACTS)}"
    for name, (size, digest) in seen.items():
        path = Path(build_dir) / name
        if not path.exists():
            return False, f"{path} is missing although boot {boot} recorded it"
        if path.stat().st_size != size or artefact_digest(path) != digest:
            return False, (f"{path} does not match boot {boot}'s manifest — the three artefacts are "
                           f"ONE measurement of ONE boot and this set is mixed or half-written. "
                           f"Re-run `python3 atari/original.py dump`.")
    return True, f"boot {boot}: all {len(seen)} artefacts match the manifest"


def mode_variance():
    """HOW MUCH OF THE DUMP IS ONE BOOT'S ACCIDENT: two independent boots, differenced.

    THE INSTRUMENT THAT OWNS THE NUMBER. Every other surface — this file's header, atari/README.md,
    STATUS.md — cites the range this mode measures rather than restating a figure of its own, because
    the figure MOVES between boots and three copies of a moving number are three chances to quote a
    stale one."""
    first = BUILD / DUMP_FILE
    if not first.exists():
        raise SystemExit(f"run `original.py dump` first — {first} is one of the two boots")
    ram, _, _ = dump_at(BOOT_ANCHOR_PC, "variance")
    if ram is None:
        raise SystemExit(f"FAIL: the second boot never reached ${BOOT_ANCHOR_PC:x}")
    a, b = first.read_bytes(), ram[WB_STAGED_AT:GAME_SPAN_END]
    differ = differing_addresses(a, b)
    print(f"   two independent boots differ in {len(differ)} of {len(a)} bytes")

    problems = []
    unexplained = list(differ)
    for name, start, end, ceiling in VARIANCE_BANDS:
        inside = [i for i in differ if start <= i < end]
        unexplained = [i for i in unexplained if not (start <= i < end)]
        print(f"     {name} [{start:#x},{end:#x}): {len(inside)} of at most {ceiling}")
        if len(inside) > ceiling:
            problems.append(f"{name} moved {len(inside)} bytes, past its {ceiling}-byte ceiling — "
                            f"the band still contains them but the decomposition no longer "
                            f"describes them")
    if unexplained:
        problems.append(f"{len(unexplained)} bytes differ outside every band this file knows about, "
                        f"first at {unexplained[0]:#x} — the decomposition in the header is "
                        f"incomplete and the staged image carries an unnamed accident")
    if problems:
        raise SystemExit("FAIL: " + "; ".join(problems))

    # KEPT FOR `mode_neighbour`, which needs both: the reading, to set a floor the mis-anchor has to
    # clear, and the second boot itself, to check that floor in the other direction.
    (BUILD / SECOND_DUMP_FILE).write_bytes(b)
    (BUILD / VARIANCE_FILE).write_text(f"{len(differ)}\n")
    print(f"OK: every irreproducible byte is inside a named band and under its ceiling; none of "
          f"them reaches a frame ({BUILD / VARIANCE_FILE} records the reading)")
    return True


# WHICH frames to photograph, READ OUT OF THE SHIM rather than restated: the two sides have to be
# anchored at the same frames, and a list written down twice is a comparison of two different
# moments waiting to happen (CLAUDE.md §5). wonderboy_main.c argues the choice.
def anchor_frames():
    line = re.search(r"^#define M2_ANCHOR_FRAMES (.+)$",
                     (HERE / "wonderboy_main.c").read_text(), re.M)
    if not line:
        raise SystemExit("wonderboy_main.c no longer defines M2_ANCHOR_FRAMES — the two sides' "
                         "anchors have no shared definition, so nothing below compares one moment")
    return [int(frame) for frame in line.group(1).split(",")]


FRAME_LOOP_PC = 0x4a0             # `game_main_loop` — one entry per frame, and nothing else reaches
                                  # it (../names.txt cmt 0x4a0: `jmp $4a0.w` from $f8b4, `bra.s`
                                  # from $508). So the Nth hit IS the Nth frame's start.
SCREEN_REGION = (0x70000, 0x80000)  # both 32000-byte screens and the game's stack, in one savebin


def frames_script(directory, disk2, frames, flash_seed=None):
    """Anchor the SHIPPED binary at each frame in `frames` and photograph it there.

    Hit 1 of $4a0 is the boot's own `jmp` arriving, i.e. BEFORE any frame has run, so frame N's
    RESULT is on screen at hit N+1. Hatari counts hits from 1 and rejects an explicit `:1`, which is
    why no anchor here is ever hit 1 — and hit 1 is not a frame anyway.

    Everything one anchor does is in ONE action file rather than several breakpoints: two breakpoints
    on the same PC and hit count disturb each other's counters, and the measured consequence in the
    sibling project was captures and dumps arriving from different moments. Anchors are told apart
    by the HIT COUNT and share a PC, which is why boot_script's duplicate guard keys on the pair.

    `flash_seed` uses hit 1 — the arrival no frame owns — to poke WB_FLASH_TIMER before the first
    frame runs. That is M5's declared fabrication, and the instant is chosen so that it matches, on
    this side, exactly where wonderboy_main.c's `arm_the_flash` writes the same word on ours: after
    the boot, before frame 1."""
    low, high = SCREEN_REGION
    stops = [(FRAME_LOOP_PC, frame + 1, f"F{frame}.INI", [
        f"savebin {directory / ('OSCR%d.BIN' % frame)} ${low:x} {high - low:#x}",
        f"savebin {directory / ('OFRONT%d.BIN' % frame)} ${wb('SCREEN_FRONT'):x} 4",
        f"savebin {directory / ('OPEN%d.BIN' % frame)} ${SHIFTER_PALETTE:x} {PALETTE_BYTES}"]
        + vector_commands(directory, THEIR_TAG, index)
        + [picture_command(directory, THEIR_TAG, index), f"echo FRAME_{frame}_CAPTURED"])
        for index, frame in enumerate(frames, 1)]
    if flash_seed is not None:
        stops.append((FRAME_LOOP_PC, FIRST_HIT, "FLASH.INI",
                      [f"echo {FLASH_ARMED_BEACON}",
                       poke_word(wb("FLASH_TIMER"), flash_seed)]))
    return boot_script(directory, disk2, extra_stops=stops)


# WHERE THE SHIPPED SIDE'S CAPTURES LAND, and why a flash run gets its own names: the two runs
# photograph DIFFERENT machines (one with `flip_screen`'s flash arms live, one without), and a shared
# filename would let `smoke.py m5` compare our unflashed frames against the flashed side's pens the
# moment the two modes were run in the wrong order. One prefix per fabrication.
FRAME_PREFIXES = {False: "", True: "F"}
# Which mode PRODUCED a prefix's artefact set. One definition, because two `'flash' if prefix else
# 'frames'` ternaries — in this file and in smoke.py — are two places that would print the wrong
# recovery command the day a third artefact set exists.
FRAME_PRODUCER = {"": "frames", "F": "flash"}
FLASH_ARMED_BEACON = "FLASH_ARMED"
VECTOR_FILE, PICTURE_FILE = "OVEC%d.json", "OPNG%d.png"


def mode_frames(frames, flash_seed=None):
    """Photograph the shipped binary at `frames`, for smoke.py's side-by-side.

    Each anchor leaves five artefacts: the screen region, the front-buffer pointer, the sixteen pens,
    the HARDWARE-STATE VECTOR and the rendered picture. The vector is parsed HERE — by the one reader
    both sides use — and stored as JSON, because the shipped side runs minutes before ours and the
    two have to meet on disk without either re-implementing the other's parse."""
    tag = "flash" if flash_seed is not None else "frames"
    prefix = FRAME_PREFIXES[flash_seed is not None]
    produced, log, status = run_original(
        lambda d, disk2: frames_script(d, disk2, frames, flash_seed), tag)
    print(f"-- {tag}: anchors {frames} at ${FRAME_LOOP_PC:x}, hatari exit={status} "
          f"(full log in {OUT / ('original-%s.log' % tag)})")
    faults = machine_faults(log)
    if faults:
        raise SystemExit("FAIL: unhealthy machine: " + " | ".join(faults[:4]))
    if flash_seed is not None and FLASH_ARMED_BEACON not in log:
        raise SystemExit(f"FAIL: the flash poke never ran — ${FRAME_LOOP_PC:x} was never reached a "
                         f"first time, so this side's WB_FLASH_TIMER is the staged $0000 and the "
                         f"comparison would be against a machine that is not flashing")
    BUILD.mkdir(exist_ok=True)
    for index, frame in enumerate(frames, 1):
        for stem in ("OSCR", "OFRONT", "OPEN"):
            name = f"{stem}{frame}.BIN"
            if name not in produced:
                raise SystemExit(f"FAIL: the shipped binary produced no {name} — it did not reach "
                                 f"frame {frame}, so there is nothing to compare against")
            (BUILD / (prefix + name)).write_bytes(produced[name])
        vector = hardware_vector(log, produced, THEIR_TAG, index, frame)
        (BUILD / (prefix + VECTOR_FILE % frame)).write_text(json.dumps(vector, sort_keys=True))
        (BUILD / (prefix + PICTURE_FILE % frame)).write_bytes(
            read_capture(produced, THEIR_TAG, index, PICTURE_SUFFIX, frame))
    print(f"   {len(frames)} frames captured into {BUILD} as {prefix or '(no prefix)'}*: "
          f"screens, pens, {VECTOR_REGISTERS}-register vectors and rendered pictures")
    return True


# ---- the TWO BOOT PICTURES, on the shipped side ---------------------------------------------------
#
# THE TITLE is the earliest moment in this file, and the cheapest: the picture is on screen before
# the boot has asked for anything but disk 1, so it needs no data disk, no fire and no anchor past
# the one instruction. `$e556` is `tst.b $877.w` — the first of the pair the boot spins on waiting
# for the stick — and its FIRST arrival is the instant after `set_palette` has run and before a
# player could have answered. That is exactly what `smoke.py title` photographs on our side.
#
# THE TITLE'S FIRE INJECTIONS ARE TURNED OFF, and not only because they are unnecessary.
# `boot_script` puts its own `:once` breakpoint on this very PC to press the stick, and two
# breakpoints selecting the same arrival at the same PC interfere with each other's counters —
# `refuse_repeated_arrivals` is the guard for exactly that, and it cannot see boot_script's own four
# lines. `fires=False` removes them, which leaves that mode's anchor the only thing stopping at
# $e556.
#
# THE CREDITS is one fire gate later and so is the FIRST anchor in this file that needs the
# injections. Its anchor is `$e5aa` — `clr.b $877.w`, the instruction immediately before the credits
# fire wait — which is chosen because it collides with NONE of `boot_script`'s four `:once`
# breakpoints ($e556/$e55c press and release the title's stick, $e5ae/$e5b4 the credits' own), so it
# needs neither `fires=False` nor a hook into their action files. At that instruction the whole of
# `boot_credits_screen` has run: `rad_depack` inflated CREDITS.RAD onto WB_SCREEN_HIGH,
# `set_palette` put its sixteen words on the chip, `copy_screen` brought the picture down onto
# WB_SCREEN_LOW — the buffer $f906 pointed the shifter at — `game_restart_reset` drew the three
# lives over it, and `move.w #$77,$ff8254.l` raised pen WB_CREDITS_PROMPT_PEN.
#
# BOTH READ WB_SCREEN_LOW, and for one reason: `video_set_lowres_50hz` ($f906) publishes that buffer
# as two immediates and nothing between the boot's start and either anchor flips it. The title
# depacks straight into it; the credits depacks into the OTHER buffer and copies down. So the
# address the shifter is showing is the address both captures are taken at, on both sides.
#
# THE DATA-DISK PROMPT is the third picture and the only one the BOOT never draws: `$e494` is
# reached by three `jmp`s and not one of them is on the boot path (`$e490` is `bra.w $e4e6`, which
# steps over the whole prompt). So this one is reached by DRIVING THE SHIPPED BINARY'S OWN ESC
# ENDING — the boot carried past both fire gates and through the data-disk swap into the frame loop,
# then WB_KEY_LAST_SCANCODE poked with ESC at a named frame, exactly as `smoke.py m3` drives the same
# arm on our side. `game_key_actions` reads that byte at `$580`, the second call of every frame.
#
# ITS ANCHOR IS `$e4d6` — `clr.b $877.w`, the instruction the slice falls into — and it is the same
# choice `$e5aa` and `$e556` are: the first instruction after the reconstructed slice's last and
# before anything waits for a player. It is NOT `$e4d4`: `jsr $f944.l` at `$e4d0` is six bytes, so
# $e4d4 is inside its operand and no instruction begins there. It collides with none of
# `boot_script`'s four `:once` fire breakpoints, so it needs neither `fires=False` nor a hook into
# their action files.
#
# AND IT READS WB_SCREEN_HIGH, where the other two read WB_SCREEN_LOW. `$e498`/`$e4a0` publish
# `WB_PROMPT_SCREEN_BASE` before the load and the depack at `$e4c6` inflates into that very buffer,
# so — as for the other two — the address the shifter is showing is the address the capture is taken
# at, on both sides.
TITLE_SCREEN_FILE = "OTITLE.BIN"
TITLE_PENS_FILE = "OTITLEPEN.BIN"
CREDITS_SCREEN_FILE = "OCREDITS.BIN"
CREDITS_PENS_FILE = "OCREDPEN.BIN"
PROMPT_SCREEN_FILE = "OPROMPT.BIN"
PROMPT_PENS_FILE = "OPROMPTP.BIN"
WB_SCREEN_LOW = wb("SCREEN_LOW")
WB_SCREEN_HIGH = wb("SCREEN_HIGH")
# `clr.b $877.w`, the prompt's own anchor — TAKEN FROM THE HEADER and not written down again. Both
# sides of this differential have to photograph one instruction: ours is `capture_the_prompt`, called
# where WB_BOOT_PROMPT_END names, and a second spelling of the address here is the two sides
# photographing two instants while both stay green (CLAUDE.md §5). The older literal PCs above
# (TITLE_FIRE_PRESS_PC, CREDITS_WAIT_CLEAR_PC and their siblings) are the same hole and are queued in
# ../STATUS.md §7 rather than changed under this batch.
PROMPT_ANCHOR_PC = wb("BOOT_PROMPT_END")
PROMPT_ESC_BEACON = "PROMPT_ESC_POKED"
# WHICH ANCHOR FRAME THE KEY IS POKED AT — a 1-based index INTO `anchor_frames()`, and the FIRST of
# them. `smoke.py`'s `OWN_QUIT_POKE_ANCHOR` is the same instant expressed in ITS units (which arrival
# at `capture_the_frame` carries the poke), and the two are cross-pinned there — as the FRAME each
# side's ESC lands after, because the two numbers are different kinds and only look alike.
#
# THE PICTURE DOES NOT DEPEND ON IT and OUR SIDE'S SCREEN-BASE ROW DOES, which is why the number is
# the first arrival and not M3's second. The prompt inflates a file over the whole of WB_SCREEN_HIGH,
# so no frame the loop had drawn survives into the photograph whichever frame ESC fires on; but
# `flip_screen` publishes the buffer that has just become the front one, so an EVEN frame count
# leaves the shifter already on the buffer the prompt is about to publish and smoke.py's row for
# that publish could not then fail. Matched here so the two sides are anchored at one instant.
PROMPT_ESC_ANCHOR = 1


def echoed_beacons(stops):
    """Every beacon a `boot_script` stop echoes, in order — the stop's own spelling of its name."""
    return [command.split(None, 1)[1] for _, _, _, commands in stops
            for command in commands if command.startswith("echo ")]


def capture_boot_picture(tag, anchor_pc, screen_file, pens_file, fires,
                         at=None, swap_the_data_disk=False, drive=()):
    """Photograph one screen buffer and the sixteen pens at `anchor_pc`, and write both to build/.

    ONE ROUTINE FOR ALL THREE PICTURES, because they differ in a handful of values and in nothing
    else — which mode, which instruction, which buffer, and how far the boot has to be carried to
    reach the moment. Three copies of this would be three chances for one side of a differential to
    photograph a different thing from the other (CLAUDE.md §6).

    `at` is the buffer, defaulting to WB_SCREEN_LOW, which is where the title and credits pictures
    are; the data-disk prompt publishes WB_SCREEN_HIGH and inflates into it, so that mode names its
    own. `swap_the_data_disk` puts disk 2 in the drive at `$e5ba` — the boot's own swap point — which
    the two pictures BEFORE the stage load do not need and the one AFTER it cannot do without.
    `drive` is extra `boot_script` stops the mode injects on its way to the anchor, which is how the
    prompt mode reaches an instruction only an ENDING leads to.

    `fires` WAS A HARDCODED FALSE AND IS NOW AN ARGUMENT, so the invariant that forced it is checked
    here rather than left in prose. `boot_script` puts its own `:once` breakpoint on each of the four
    fire PCs and, when a disk 2 is passed, a fifth on the swap; two breakpoints selecting the same
    arrival at the same PC interfere with each other's counters — which is exactly what
    `refuse_repeated_arrivals` refuses, and which it cannot see, because it is handed `extra_stops`
    alone. So no stop this routine adds may sit on a PC `boot_script` has already claimed.

    THE GUARD COVERS THE `drive` STOPS AND NOT ONLY THE ANCHOR, which the first draft got wrong: a
    mode that reaches its anchor by injecting stops of its own has as many chances to collide as it
    has stops, and `drive` is the argument that made that possible."""
    claimed = {}
    if fires:
        claimed.update({pc: "one of boot_script's own fire breakpoints" for pc in FIRE_INJECTION_PCS})
    if swap_the_data_disk:
        claimed[DATA_DISK_SWAP_PC] = "boot_script's own data-disk swap breakpoint"
    for pc, whose in ([(anchor_pc, "this capture's anchor")]
                      + [(stop[0], "one of this capture's drive stops") for stop in drive]):
        if pc in claimed:
            raise SystemExit(f"FAIL: ${pc:x} is {whose} AND {claimed[pc]}, which this capture asked "
                             f"for too — the two would select the same arrival at the same PC and "
                             f"the photograph would be taken at a moment other than the one named. "
                             f"Pass fires=False, as `title` does, or move the stop.")
    beacon = f"{tag.upper()}_CAPTURED"
    at = WB_SCREEN_LOW if at is None else at

    # ...AND THE RUN ENDS AT THE ANCHOR. `quit` is the LAST command of the anchor's own action file,
    # after both `savebin`s, so Hatari stops the moment the photograph is taken instead of emulating
    # the rest of a 12,000-vblank window nothing in this mode reads. MEASURED, all three modes, with
    # all six artefacts BYTE-IDENTICAL either way (md5): title 9.5 s -> 1.8 s, credits 9.8 -> 2.3,
    # prompt 10.4 -> 4.0.
    #
    # THE EXIT STATUS IS STILL 0 AND THE HEALTH SCAN STILL BITES, which is what had to be checked
    # before this was worth anything: a scripted quit is an ordinary Hatari exit, and
    # `machine_faults` reads the log up to it — i.e. exactly the window the photograph is OF. A fault
    # after the capture was never evidence about the capture. And a run whose anchor never fires
    # never reaches this `quit` at all: it plays the whole window out and the beacon check below is
    # what reports it, unchanged.
    def script(directory, disk2):
        return boot_script(directory, disk2 if swap_the_data_disk else None,
                           extra_stops=list(drive) + [
            (anchor_pc, FIRST_HIT, "PICTURE.INI", [
                f"echo {beacon}",
                f"savebin {directory / screen_file} ${at:x} {SCREEN_BYTES:#x}",
                f"savebin {directory / pens_file} ${SHIFTER_PALETTE:x} {PALETTE_BYTES}",
                "quit"])])

    produced, log, status = run_original(script, tag, fires=fires)
    print(f"-- {tag}: anchor ${anchor_pc:x}, hatari exit={status} "
          f"(full log in {OUT / ('original-%s.log' % tag)})")
    faults = machine_faults(log)
    if faults:
        raise SystemExit("FAIL: unhealthy machine: " + " | ".join(faults[:4]))
    # EVERY DRIVE STOP FIRED, ASKED BEFORE THE ANCHOR IS. A mode that injects stops to REACH its
    # anchor has one failure the anchor's own beacon reports as the wrong thing: if the ESC poke
    # never happened, the boot never took the ending, the anchor is never reached, and "no prompt
    # picture was drawn" is true but says nothing about the cause. So each stop is named by the
    # `echo` it makes — derived from the stop itself rather than restated, so a beacon renamed in one
    # place cannot be checked for under its old name here.
    for stop_beacon in echoed_beacons(drive):
        if stop_beacon not in log:
            raise SystemExit(f"FAIL: {tag}'s {stop_beacon} stop never fired — the run never reached "
                             f"the moment that leads to ${anchor_pc:x}, so whatever the anchor did "
                             f"or did not do afterwards is not evidence about this mode")
    if beacon not in log:
        raise SystemExit(f"FAIL: the boot never reached ${anchor_pc:x} — no {tag} picture was "
                         f"drawn, so there is nothing for the reconstruction to be compared to")
    missing = [name for name in (screen_file, pens_file) if name not in produced]
    if missing:
        raise SystemExit(f"FAIL: the anchor fired but produced no {', '.join(missing)}")
    BUILD.mkdir(exist_ok=True)
    for name in (screen_file, pens_file):
        (BUILD / name).write_bytes(produced[name])
    # A PICTURE OF NOTHING WOULD PASS EVERY CHECK ABOVE, and an all-zero screen is precisely what a
    # boot that stopped one call too early leaves — `clear_both_screens` ($e4ee) runs before the
    # title load. So the artefact is required to be a picture, here, where it is written.
    drawn = sum(1 for byte in produced[screen_file] if byte)
    if not drawn:
        raise SystemExit(f"FAIL: {screen_file} is {SCREEN_BYTES} zero bytes — the anchor fired "
                         f"over the CLEARED screen, not over a depacked one")
    print(f"   {BUILD / screen_file}: {SCREEN_BYTES} bytes at {at:#x}, "
          f"{drawn} of them non-zero")
    print(f"   {BUILD / pens_file}: " + " ".join(
        "%03x" % pen for pen in pen_words(produced[pens_file])))
    return True


def mode_title():
    """Photograph the shipped binary's title screen at $e556, for smoke.py's side-by-side."""
    return capture_boot_picture("title", TITLE_FIRE_PRESS_PC, TITLE_SCREEN_FILE, TITLE_PENS_FILE,
                                fires=False)


def mode_credits():
    """Photograph the shipped binary's credits screen at $e5aa, one fire gate later."""
    return capture_boot_picture("credits", CREDITS_WAIT_CLEAR_PC, CREDITS_SCREEN_FILE,
                                CREDITS_PENS_FILE, fires=True)


def prompt_esc_stop():
    """The one poke that turns a running game into the data-disk prompt: ESC, at a named frame.

    `$4a0`'s hit N+1 is the START of frame N+1, i.e. the instant frame N finished — `frames_script`'s
    own convention, and the shipped-side twin of `capture_the_frame`'s Nth arrival, which is where
    smoke.py's M3 pokes the identical byte with the identical value. `game_key_actions` is the frame's
    SECOND call ($4a4) and reads WB_KEY_LAST_SCANCODE at $580, so the arm fires inside that frame.

    THE KEY IS NEVER RELEASED AND THAT IS CORRECT HERE, where it would not be on a run that carried
    on: the debugger's poke stays in the byte for ever, which is what a key physically held down
    would do, and this run stops at the prompt's own anchor before anything reads it again."""
    frame = anchor_frames()[PROMPT_ESC_ANCHOR - 1]
    return (FRAME_LOOP_PC, frame + 1, "ESCPOKE.INI",
            [f"echo {PROMPT_ESC_BEACON}",
             poke_byte(wb("KEY_LAST_SCANCODE"), wb("KEY_SCANCODE_ESC"))])


def mode_prompt():
    """Photograph the shipped binary's DATA-DISK PROMPT at $e4d6, after driving its own ESC ending.

    THE ONLY ONE OF THE THREE PICTURES THE BOOT DOES NOT DRAW. It needs the whole boot (both fire
    gates AND the data-disk swap, because `$e494`'s load asks disk 2 for DATADISK.RAD), then a frame
    loop, then the ending — so it is the deepest anchor in this file that is not the dump's."""
    return capture_boot_picture("prompt", PROMPT_ANCHOR_PC, PROMPT_SCREEN_FILE, PROMPT_PENS_FILE,
                                fires=True, at=WB_SCREEN_HIGH, swap_the_data_disk=True,
                                drive=(prompt_esc_stop(),))


def frames_argument():
    """`frames` with no argument takes the shim's anchors; `frames N` takes 1..N, which is the form
    that MEASURED those anchors in the first place (see wonderboy_main.c's M2_ANCHOR_FRAMES)."""
    if len(sys.argv) > 2:
        return list(range(1, int(sys.argv[2]) + 1))
    return anchor_frames()


# ---- M6: THE ORDERED WRITE TIMELINE ---------------------------------------------------------------
#
# THE SURFACE EVERY OTHER CHECK IN THIS PROJECT IS BLIND TO. M2's framebuffer, M5's pens, the
# hardware-state vector and the rendered picture are all SNAPSHOTS: they say what the machine looked
# like at four instants, and a program that arrives at the right state by a wrong route passes every
# one of them. `../STATUS.md`'s surviving shifter-sink mutant is exactly that shape — the sink write
# moved above the timer store changes no value at all, only the ORDER of two writes — and so is the
# sibling project's 773-stomps bug, where a VBL handler re-armed the palette every vblank and each of
# the 773 redundant loads wrote the same correct sixteen words.
#
# THE INSTRUMENT IS `io_write` AND NOT Joust's `video_color,psg_write`, for two measured reasons:
#   * this game's timeline needs the SCREEN-BASE publication, which is `flip_screen`'s own per-frame
#     heartbeat, and `--trace video_addr` emits nothing at all for a write to $ff8201/$ff8203
#     (measured on Hatari 2.6.1: zero lines over a whole 52-frame run);
#   * one stream removes the question of how two trace channels interleave, and interleaving is the
#     only thing this check measures.
#
# ...AND IT IS PARSED HERE, ONCE, FOR BOTH SIDES. smoke.py runs `timeline_events` over its own log
# and over the JSON this file leaves behind, so the shipped binary's stream and the reconstruction's
# cannot be read by two parsers that have drifted apart. That is M5's lesson taken rather than
# relearned (§10: one `vector_commands`, one `hardware_vector`).
TIMELINE_TRACE = "io_write"
# `IO write.b $ffff8800 = $07 pc=fc0086`. The WIDTH matters to nobody here — a pen is written as a
# word and a base byte as a byte — but the ADDRESS is normalised, because the same register is named
# two ways in one log: code that sign-extends a short absolute reaches $ffff8800 and code that does
# not reaches $00ff8800. Measured, and it splits along the two sides — TOS and our C write $ffff88xx,
# the shipped 1989 binary writes $00ff88xx — so a parser that keyed on the printed spelling would
# have read one side's stream as empty and passed.
IO_WRITE_RE = re.compile(r"^IO write\.[bwl] \$([0-9a-f]+) = \$([0-9a-f]+) pc=([0-9a-f]+)$")
IO_ADDRESS_MASK = 0xffffff
# Hatari COLLAPSES a run of identical consecutive trace lines into `N repeats of: <line>`, on a
# doubling schedule. Measured over both sides' whole runs, the only line it ever collapses is the
# MFP's `$fffffa11 = $00` — none of the five registers this timeline reads — but "measured today"
# is not "cannot happen", and a collapsed run would silently shorten a stream this check compares
# element for element. So it is DETECTED AND REFUSED rather than expanded on a guess about whether
# the printed count is cumulative or incremental, which is a semantics this project has not pinned.
TRACE_REPEAT_RE = re.compile(r"^(\d+) repeats of: (.*)$")


def kit_constant(name):
    """One plain-integer `#define` out of the recreate kit's `os.h`.

    The two YM-2149 ports are the KIT's constants, not this game's — `../include/bus.h` names them
    in prose and `../src/sound.c` reaches them through the kit — so they are scraped from where they
    are defined rather than written down a third time (CLAUDE.md §5)."""
    header = REC.parents[2] / "tools" / "recreate_kit" / "include" / "os.h"
    found = re.search(r"^#define\s+%s\s+(0[xX][0-9a-fA-F]+|\d+)u?\b" % name, header.read_text(), re.M)
    if not found:
        raise SystemExit(f"{name} is not a plain-integer #define in {header}")
    return int(found.group(1), 0)


PSG_SELECT_PORT = kit_constant("OS_PSG_PORT_SELECT")
PSG_DATA_PORT = kit_constant("OS_PSG_PORT_DATA")
BASE_HIGH_REG = wb("SHIFTER_SCREEN_BASE_HIGH")
BASE_MID_REG = wb("SHIFTER_SCREEN_BASE_MID")
# Which byte of the screen address each of those two registers carries. An STF's video base has NO
# low byte — bits 7..0 are always zero (docs/on-target-execution.md, taxonomy 8) — so these two are
# the whole register, and `apply_base_write` below is the only place they are applied.
BASE_HIGH_SHIFT, BASE_MID_SHIFT = 16, 8
BASE_HIGH_MASK, BASE_MID_MASK = 0xff << BASE_HIGH_SHIFT, 0xff << BASE_MID_SHIFT
PEN_FIRST_REG = wb("SHIFTER_PALETTE")
PEN_LAST_REG = PEN_FIRST_REG + (PALETTE_PENS - 1) * 2
# The five registers a Wonder Boy timeline is about. Everything else `io_write` carries — the MFP,
# the FDC, the RS-232 — belongs to TOS and to the floppy, differs between a GEMDOS drive and a real
# one by construction, and is dropped.
TIMELINE_REGISTERS = frozenset(
    [PSG_SELECT_PORT, PSG_DATA_PORT, BASE_HIGH_REG, BASE_MID_REG]
    + [PEN_FIRST_REG + pen * 2 for pen in range(PALETTE_PENS)])


# The flash countdown is a RAM word, not a register, so it needs a slot in the same ordered stream
# that cannot collide with one. Negative is out of band by construction — every real register here is
# a positive $ff8xxx — which is the encoding rule this project learned the hard way when an in-band
# refusal sentinel collided with a zero table entry (../STATUS.md, batch 32).
FLASH_TIMER_EVENT = -1


def timeline_events(lines, flash_address=None):
    """Hatari's trace, reduced to (register, value, pc) over TIMELINE_REGISTERS, in order.

    With `flash_address`, the value-change breakpoint's own lines are folded into the SAME stream as
    `FLASH_TIMER_EVENT` entries — which is the whole point of it: what `m6flash` compares is the
    ORDER of a RAM store against a hardware write, and two separately-parsed lists could not say
    which came first.

    RETURNS `(events, problem)` and never raises: every caller is inside a checker whose contract is
    a verdict, and a parse failure surfacing as a traceback would abort a negative control before it
    could report which of its checks it had broken."""
    watch = re.compile(FLASH_WATCH_RE_TEMPLATE % flash_address) if flash_address else None
    events = []
    for line in lines:
        if watch:
            watched = watch.match(line)
            if watched:
                events.append((FLASH_TIMER_EVENT, int(watched.group(1), 16), "watch"))
                continue
        line = line.strip()
        collapsed = TRACE_REPEAT_RE.match(line)
        if collapsed:
            inner = IO_WRITE_RE.match(collapsed.group(2).strip())
            if inner and (int(inner.group(1), 16) & IO_ADDRESS_MASK) in TIMELINE_REGISTERS:
                return [], (f"Hatari collapsed {collapsed.group(1)} consecutive writes to "
                            f"${int(inner.group(1), 16) & IO_ADDRESS_MASK:x} into one `repeats of` "
                            f"line, so the ordered stream this compares is missing entries; see "
                            f"TRACE_REPEAT_RE for why this is refused rather than expanded")
            continue
        write = IO_WRITE_RE.match(line)
        if not write:
            continue
        register = int(write.group(1), 16) & IO_ADDRESS_MASK
        if register in TIMELINE_REGISTERS:
            events.append((register, int(write.group(2), 16), write.group(3)))
    return events, None


TIMELINE_FILE = "OTIMELINE.json"
WINDOW_OPEN_BEACON, WINDOW_CLOSE_BEACON = "TIMELINE_WINDOW_OPEN", "TIMELINE_WINDOW_CLOSE"
# The flash countdown's own word, watched as a VALUE-CHANGE breakpoint so that the RAM half of
# `flip_screen`'s last pair is in the same ordered stream as the hardware half. Hatari has no
# RAM-write trace; `($addr).w ! ($addr).w :trace` is its documented idiom for tracking a memory
# value, and it is checked at instruction boundaries — one instruction coarser than the bus, and
# enough here because the two writes this brackets are adjacent statements.
#
# THE LINE IT PRINTS is `  $714 = $1`, which is what `flash_watch_events` below matches.
FLASH_WATCH_RE_TEMPLATE = r"^\s+\$0*%x = \$([0-9a-f]+)\s*$"


def flash_watch_command(address):
    """The debugger command that puts WB_FLASH_TIMER's word into the timeline."""
    return f"b (${address:x}).w ! (${address:x}).w :trace"




def apply_base_write(state, register, value):
    """The shifter's base address after one write to it, or None if `register` is not one of its two.

    THE ONE PLACE THE BASE REGISTER'S SEMANTICS LIVE. Which two registers it is and which byte of the
    address each carries was written out three times before this existed — twice as the same masking
    pair and once as a fold — and one of the copies was inside the function that produces the
    publication list M6 compares. A fix to the rule (an STE's low byte at $ff820d would be one) that
    reached the fold and not that copy would leave the comparison on the old rule with every count
    still adding up."""
    if register == BASE_HIGH_REG:
        return (state & ~BASE_HIGH_MASK) | (value << BASE_HIGH_SHIFT)
    if register == BASE_MID_REG:
        return (state & ~BASE_MID_MASK) | (value << BASE_MID_SHIFT)
    return None


def base_state_after(events, state=0):
    """Replay the base register over `events` and return the address they leave.

    In THIS file because the two registers are, and both files replay them: smoke.py to classify a
    window's writes and this one to record the address a window OPENS on."""
    for register, value, _ in events:
        moved = apply_base_write(state, register, value)
        if moved is not None:
            state = moved
    return state


def timeline_window(log, label):
    """The lines before, and the lines between, the two beacons — the run's own window statement."""
    lines = log.splitlines()
    opened = next((i for i, line in enumerate(lines) if WINDOW_OPEN_BEACON in line), None)
    closed = next((i for i, line in enumerate(lines) if WINDOW_CLOSE_BEACON in line), None)
    if opened is None or closed is None:
        return None, None, (f"the {label} run reached {WINDOW_OPEN_BEACON if opened is None else ''}"
                            f"{' and ' if opened is None and closed is None else ''}"
                            f"{WINDOW_CLOSE_BEACON if closed is None else ''} never — it did not run "
                            f"the frames this timeline is over")
    return lines[:opened], lines[opened:closed], None


def timeline_script(directory, disk2, frames, flash_seed=None):
    """Bracket the shipped binary's `frames` frames at the frame loop's own entry.

    THE WINDOW IS THE SAME ANCHOR M2 AND M5 USE — `$4a0`, one arrival per frame — so the stream this
    captures is over exactly the frames whose pictures and pens those modes compare. Hit 1 is the
    boot's own `jmp` arriving before any frame has run, and hit `frames + 1` is the arrival after the
    last one, so the two beacons bracket `frames` complete frames and nothing else.

    `flash_seed` does at hit 1 exactly what `frames_script` does at hit 1 — the same declared
    fabrication at the same instant — AND installs the countdown's watch there, in the same action
    file, so the watch is live from before the first frame rather than from wherever a separate
    breakpoint happened to land."""
    opener = [f"echo {WINDOW_OPEN_BEACON}"]
    if flash_seed is not None:
        opener += [f"echo {FLASH_ARMED_BEACON}", poke_word(wb("FLASH_TIMER"), flash_seed),
                   flash_watch_command(wb("FLASH_TIMER"))]
    return boot_script(directory, disk2, extra_stops=[
        (FRAME_LOOP_PC, FIRST_HIT, "TLOPEN.INI", opener),
        (FRAME_LOOP_PC, frames + 1, "TLCLOSE.INI", [f"echo {WINDOW_CLOSE_BEACON}"])])


def capture_shipped_window(frames, flash_seed, tag):
    """Boot the shipped binary once and return its window as `(events before, events in)`.

    ONE RECIPE FOR BOTH MODES. `timeline` records the window and `psgnoise` differences a second boot
    against it, and they have to boot the SAME machine or the difference is between two experiments.
    Written twice, they were not: the flash premise guard below existed only in `timeline`, so
    `flashpsgnoise` could record a reading from a boot in which the poke never landed — and that
    reading is what licenses M6's PSG exclusions."""
    _, log, status = run_original(
        lambda d, disk2: timeline_script(d, disk2, frames, flash_seed), tag, trace=TIMELINE_TRACE)
    print(f"-- {tag}: ${FRAME_LOOP_PC:x} hits 1..{frames + 1}, hatari exit={status} "
          f"(full log in {OUT / ('original-%s.log' % tag)})")
    faults = machine_faults(log)
    if faults:
        raise SystemExit("FAIL: unhealthy machine: " + " | ".join(faults[:4]))
    if flash_seed is not None and FLASH_ARMED_BEACON not in log:
        raise SystemExit(f"FAIL: the flash poke never ran — ${FRAME_LOOP_PC:x} was never reached a "
                         f"first time, so this side's WB_FLASH_TIMER is $0000 and its last four "
                         f"instructions are dead")
    before_lines, window, why = timeline_window(log, "shipped")
    if why:
        raise SystemExit("FAIL: " + why)
    events, why = timeline_events(window, wb("FLASH_TIMER") if flash_seed is not None else None)
    if why:
        raise SystemExit("FAIL: " + why)
    if not events:
        raise SystemExit(f"FAIL: the shipped binary's {frames}-frame window carries no write to any "
                         f"of the five registers this timeline reads — `{TIMELINE_TRACE}` produced "
                         f"nothing, so Hatari's wording or its flag has moved")
    # THE ADDRESS THE SHIFTER ALREADY HELD when the window opened, replayed out of everything before
    # it. Without it the first write of the window — `flip_screen`'s high byte, which changes nothing
    # because both of this binary's buffers are $07xxxx — reads as the window's first PUBLICATION,
    # and the whole sequence comes out one flip out of phase. smoke.py's `base_writes` says what that
    # measured.
    before, why = timeline_events(before_lines)
    if why:
        raise SystemExit("FAIL: " + why)
    return before, events


def mode_timeline(frames, flash_seed=None):
    """Capture the SHIPPED binary's ordered write stream over its first `frames` frames.

    The flash run gets its own `F`-prefixed artefact for `mode_frames`' reason: it photographs a
    DIFFERENT machine — `flip_screen`'s flash arms are live in it and dead in the other — and one
    filename would let a plain comparison read the flashed stream the moment the two modes were run
    in the wrong order."""
    prefix = FRAME_PREFIXES[flash_seed is not None]
    before, events = capture_shipped_window(
        frames, flash_seed, "flashtimeline" if flash_seed is not None else "timeline")
    BUILD.mkdir(exist_ok=True)
    (BUILD / (prefix + TIMELINE_FILE)).write_text(json.dumps(
        {"frames": frames, "events": events, "base_at_open": base_state_after(before)}))
    print(f"   {len(events)} writes over {frames} frames -> {BUILD / (prefix + TIMELINE_FILE)}")
    return True


PSG_NOISE_FILE = "PSGNOISE.json"
# REGISTERS ALREADY MEASURED TO MOVE BETWEEN TWO BOOTS OF THE SHIPPED BINARY, per fabrication, as a
# COMMITTED floor under the reading rather than as something each machine must be lucky enough to
# rediscover. `build/` is gitignored, so a reading kept only there starts empty on every clone.
#
# THE READINGS, batch 43 phase E, four pairs on TOS 1.04:
#   * UNFLASHED: two pairs, 0 of 1,155 writes differing in each. Nothing to exclude, and `m6`
#     therefore compares all eleven registers the window touches.
#   * FLASHED: two pairs, one clean and one differing in 42 of 1,155 — every one of them channel A's
#     tone period (registers 0 and 1), all inside the first eleven frames. THE PAIRING IS
#     INTERMITTENT, so a run that happens to draw the quiet pair would license comparing a register
#     already watched to move, and `m6flash` would go red for something neither binary did.
#
# Coherent with §10's `flashnoise` finding rather than an exception to it: the flashed boot is a
# different machine — `../src/behavior.c` gates on the same countdown word — so it drives different
# actors, and a sound effect whose pitch sweeps per vblank cannot land on the same value twice when
# what varies is which vblank the floppy boot finished on.
#
# ONE-DIRECTIONAL, as the whole instrument is: this names registers demonstrably unstable, and says
# nothing about the ones not in it. `mode_psg_noise` unions its own pairs on top and never subtracts.
PSG_REGISTERS_KNOWN_UNSTABLE = {"": (), "F": (0, 1)}


def psg_stream(events):
    """The YM-2149 writes as (register, value), decoded from the select/data protocol.

    In this file rather than smoke.py because BOTH sides' streams go through it — smoke.py's own
    window and the JSON this file leaves behind — and §10's rule is that the two sides are measured
    by one piece of code."""
    pairs, selected = [], None
    for register, value, _ in events:
        if register == PSG_SELECT_PORT:
            selected = value
        elif register == PSG_DATA_PORT:
            pairs.append((selected, value))
    return pairs


def sorted_registers(registers):
    """Sort PSG register numbers, tolerating the `None` `psg_stream` files for an orphan data write.

    A BARE `sorted()` RAISES ON THAT, and the orphan is deliberate rather than a parse failure:
    smoke.py's comment on `psg_stream` records that a data write with no select before it is exactly
    what README §5's select/data race would look like on the bus, so it is kept rather than dropped.
    Keeping it and then crashing on it — after two Hatari boots — is the worst of both."""
    return sorted(registers, key=lambda register: (register is not None, register))


def mode_psg_noise(frames, flash_seed=None):
    """WHICH OF THE SHIPPED BINARY'S OWN PSG WRITES ARE ONE BOOT'S ACCIDENT.

    M6's sound assertion is that the shipped binary's ordered PSG stream is a prefix of ours, and
    that claim is worth nothing over registers the shipped binary does not reproduce against ITSELF.
    §10 already establishes the mechanism for the snapshot version of this — where the music is at
    frame N depends on which vblank the boot finished on, and `vecnoise` measures it — and this is
    the same measurement over the STREAM instead of over the register file.

    ONE-DIRECTIONAL, AND THE MODE SAYS SO: a register that moves is demonstrably one boot's
    accident; one that does not is not thereby shown to be stable. Two boots is not a sample that
    could bound anything. So the exclusion this licenses is BY REGISTER, with this reading as its
    evidence, and the reading doubles as a tripwire — a register moving that M6 does compare turns
    up here first.

    Diffed against `OTIMELINE.json`, which is a DIFFERENT BOOT of the same disks under the same
    injections, exactly as `vecnoise` diffs against `frames`' vectors.

    AND THE FLASH RUN GETS ITS OWN READING, for the reason §10 gives for `flashnoise`: the flashed
    boot is a DIFFERENT MACHINE — `flip_screen`'s arms are live in it and `../src/behavior.c` gates
    on the same word — so what a pair of unflashed boots reproduces says nothing about what a pair
    of flashed ones does. One reading per fabrication, and `m6flash` reads the `F` one."""
    tag = "flashpsgnoise" if flash_seed is not None else "psgnoise"
    prefix = FRAME_PREFIXES[flash_seed is not None]
    first = BUILD / (prefix + TIMELINE_FILE)
    if not first.exists():
        raise SystemExit(f"{first} is missing — this mode differences a second boot against the "
                         f"first: run `python3 atari/original.py "
                         f"{'flashtimeline' if prefix else 'timeline'}` before it")
    reference = json.loads(first.read_text())
    if reference["frames"] != frames:
        raise SystemExit(f"{first} covers {reference['frames']} frames and this run covers {frames} "
                         f"— two different windows cannot be differenced")
    print(f"   (a SECOND boot, to be differenced against {first})")
    _, events = capture_shipped_window(frames, flash_seed, tag)
    once = psg_stream([tuple(event) for event in reference["events"]])
    twice = psg_stream(events)
    if len(once) != len(twice):
        raise SystemExit(f"FAIL: the two boots wrote the PSG a different number of times "
                         f"({len(once)} and {len(twice)}) — this reading differences them position "
                         f"by position and cannot align two streams of different lengths. That is "
                         f"itself a finding: record it rather than tolerating it")
    moved = sorted_registers({once[i][0] for i in range(len(once)) if once[i] != twice[i]})
    where = [i for i in range(len(once)) if once[i] != twice[i]]
    frames_touched = sorted({position * frames // max(len(once), 1) for position in where})
    # THE EVIDENCE ACCUMULATES RATHER THAN BEING REPLACED, and that is not bookkeeping — it is what
    # a one-directional measurement means. MEASURED: this pairing is INTERMITTENT. Two plain boots
    # came back with zero differences and a later pair came back with 42, the same 42 both times
    # (registers 0 and 1, inside the first eleven frames). A reading that overwrote would therefore
    # license comparing a register on Monday that it had already watched move on Sunday, and the
    # mode would go red for something neither binary did. A register once seen to move stays
    # excluded; the pair count says how much looking is behind that.
    BUILD.mkdir(exist_ok=True)
    path = BUILD / (prefix + PSG_NOISE_FILE)
    # `.get` ON EVERY FIELD, because a reading written by an earlier shape of this record must not
    # crash the mode two Hatari boots in. Measured: the first version of this guard checked `frames`
    # with a default and then indexed `pairs` directly, so an existing file passed the guard and
    # raised KeyError after the boots, losing the reading it had just taken.
    before = json.loads(path.read_text()) if path.exists() else {}
    if before.get("frames") != frames:
        before = {}                                 # a reading of another window licenses nothing
    pairs = before.get("pairs", 0) + 1
    # BOTH NUMBERS ACCUMULATE, and that is an honesty fix rather than bookkeeping: `moved` was
    # accumulated while `differing_positions` was overwritten by the latest pair, so a quiet third
    # pair would have printed "registers [0, 1] are EXCLUDED because two boots write them
    # differently (0 of 1155 writes)" — an evidence line refuting the exclusion it exists to justify.
    differing = before.get("differing_positions", 0) + len(where)
    moved = sorted_registers(set(moved) | set(before.get("moved", []))
                             | set(PSG_REGISTERS_KNOWN_UNSTABLE[prefix]))
    path.write_text(json.dumps(
        {"frames": frames, "writes": len(once), "moved": moved,
         "differing_positions": differing, "pairs": pairs,
         "reproducible": sorted_registers({register for register, _ in once} - set(moved))}))
    print(f"   {len(where)} of {len(once)} writes differ IN THIS PAIR; registers that moved in it: "
          f"{sorted_registers({once[i][0] for i in where})}; frames touched: "
          f"{frames_touched[:1] + ['..'] + frames_touched[-1:] if len(frames_touched) > 2 else frames_touched}")
    print(f"   -> {path}: over {pairs} pair(s), {differing} differing write(s) and the excluded set "
          f"is {moved}; M6 compares the rest and PRINTS the exclusion")
    return True


def mode_control(name, fires, disk2):
    """A negative control: remove one injection and require that the anchor is NOT reached."""
    def script(directory, disk2_path):
        return boot_script(directory, disk2_path if disk2 else None, extra_stops=[
            (BOOT_ANCHOR_PC, FIRST_HIT, "ANCHOR.INI", [f"echo {ANCHOR_BEACON}"])])

    _, log, status = run_original(script, name, fires=fires)
    print(f"-- {name} (negative control — the anchor MUST NOT be reached): hatari exit={status} "
          f"(full log in {OUT / ('original-%s.log' % name)})")
    if ANCHOR_BEACON in log:
        raise SystemExit(f"FAIL: the boot reached ${BOOT_ANCHOR_PC:x} with the injection removed, "
                         f"so the injection was not what carried it there and the `dump` mode's "
                         f"claim to be driving the boot is unfounded")
    print(f"OK: without it the boot never reaches ${BOOT_ANCHOR_PC:x} in {RUN_VBLS} vblanks")
    return True


# ---- WHAT THE VECTOR CAPTURES BUT DOES NOT COMPARE, and the two reasons ---------------------------
#
# THE WHOLE YM-2149 FILE IS CAPTURED, PRINTED AND NOT COMPARED. That is a bigger exclusion than the
# sibling project's — its M5 compares all sixteen — and the difference is a property of this game
# rather than of this harness: Joust's anchors sit on a silent title screen, and Wonder Boy's sit
# inside a stage with its music playing.
#
#   * ym00..ym13, THE SOUND CHIP. Where the music is at frame N depends on which vblank the boot
#     finished on and on how many vblanks each side's frame loop spends per frame — and NEITHER is
#     controlled. `variance` already names the mechanism on the memory side ("a song is playing at
#     the anchor and its driver's cursors depend on which vblank the boot finished on"), and
#     `vecnoise` below measures it arriving at the chip: two boots of the SHIPPED BINARY ITSELF write
#     different values at the same anchor. A snapshot of these registers is therefore not evidence in
#     either direction, and a comparison that happened to pass on them would have passed by accident.
#     THE SURFACE THAT CAN COMPARE SOUND IS THE WRITE TIMELINE, which is M6's and is owed.
#   * ym14, ym15, THE TWO PARALLEL PORTS — not the sound chip at all. Port A carries the floppy
#     drive-select lines, so whoever owns the machine's disks writes it, and the two sides own
#     different disks: measured, the shipped binary (booted from its own floppy) leaves $27, drives
#     deselected, while our side — loaded off a GEMDOS hard drive by a TOS still polling for a floppy
#     — reads $25. Neither is the game's frame loop, and M1's RB_PSG_PORT_A_DESELECTED is where that
#     write IS asserted.
YM_SOUND_REGISTERS = tuple("ym%02d" % register for register in range(14))
YM_PARALLEL_PORTS = ("ym14", "ym15")
VECTOR_UNCOMPARED = YM_SOUND_REGISTERS + YM_PARALLEL_PORTS

# `vecnoise`'s reading: WHICH registers two boots of the shipped binary actually disagreed about.
# It is the EVIDENCE for the first exclusion above and a TRIPWIRE for everything else — a pen, the
# resolution or the sync bit turning out to be boot-dependent would be a far larger fact than a music
# cursor, and absorbing it into an exclusion list is exactly how a surface goes quiet. So anything
# outside VECTOR_UNCOMPARED raises, here and again in smoke.py where the file is read.
VECTOR_NOISE_FILE = "VECNOISE.json"


def mode_vector_noise(flash_seed=None):
    """A SECOND boot at the same anchors, differenced against `frames`' vectors register by register.

    `flash_seed` measures the FLASHED boot instead, and it is not a luxury: `m5flash` compares colour
    0, which on that boot is driven by a countdown seeded at a breakpoint and decremented by
    `flip_screen`. If its phase at an anchor were boot-dependent — the class this mode exists to
    detect — `pen00` would be a boot-dependent COMPARED register and every disagreement would read as
    a reconstruction defect. The reading taken over the unflashed boot cannot see that, because
    nothing is driving colour 0 there.

    Two boots is not a sample that could BOUND anything, and this mode does not pretend otherwise:
    what it establishes is one-directional. A register that moves is demonstrably one boot's
    accident; a register that does not move is not thereby shown to be stable. That is why the
    compared set is decided by kind, above, and this measurement is its evidence and its tripwire."""
    frames = frames_argument()
    prefix = FRAME_PREFIXES[flash_seed is not None]
    tag = "flashnoise" if flash_seed is not None else "vecnoise"
    first = {frame: BUILD / (prefix + VECTOR_FILE % frame) for frame in frames}
    missing = [str(path) for path in first.values() if not path.exists()]
    if missing:
        raise SystemExit(f"run `original.py {'flash' if flash_seed is not None else 'frames'}` first "
                         f"— {', '.join(missing)} is the boot this one is differenced against")
    produced, log, status = run_original(
        lambda d, disk2: frames_script(d, disk2, frames, flash_seed), tag)
    print(f"-- {tag}: a second boot at anchors {frames}, hatari exit={status}")
    faults = machine_faults(log)
    if faults:
        raise SystemExit("FAIL: unhealthy machine: " + " | ".join(faults[:4]))
    moved, seen = set(), set()
    for index, frame in enumerate(frames, 1):
        earlier = json.loads(first[frame].read_text())
        later = hardware_vector(log, produced, THEIR_TAG, index, frame)
        names = sorted(set(earlier) | set(later))
        seen |= set(names)
        differ = [name for name in names
                  if name not in VECTOR_REPORT_ONLY and earlier.get(name) != later.get(name)]
        print(f"     frame {frame:>3}: {len(differ)} of {len(names)} registers moved between two "
              f"boots" + (": " + ", ".join(f"{name} {earlier.get(name)}->{later.get(name)}"
                                           for name in differ) if differ else ""))
        moved |= set(differ)
    outside = sorted(moved - set(VECTOR_UNCOMPARED))
    if outside:
        raise SystemExit(f"FAIL: {outside} moved between two boots of the same binary, and they are "
                         f"registers M5 COMPARES. A boot-dependent pen, resolution or sync bit is a "
                         f"much larger fact than a music cursor: it would mean the vector's compared "
                         f"half is not reproducible either, and it must not be absorbed into an "
                         f"exclusion list.")
    if not moved:
        raise SystemExit("FAIL: two independent boots produced an identical vector at every anchor. "
                         "That is not the machine this game runs on — its music driver's cursors are "
                         "boot-dependent and `variance` measures them moving in memory — so either "
                         "the second boot is not independent (a cached artefact?) or the capture is "
                         "not reading the chip. Either way the exclusion above rests on nothing.")
    # STAMPED WITH WHAT IT COVERS, because a bare list of names licenses any run at all. The anchors
    # and the register names this boot actually saw are what make the reading answerable to the run
    # that reads it: a later anchor set, or a 37th register, is a measurement nobody has taken, and
    # smoke.py refuses rather than inheriting this one's authority. (Same reason `original.py dump`
    # stamps a manifest over its three artefacts.)
    (BUILD / (prefix + VECTOR_NOISE_FILE)).write_text(json.dumps(
        {"moved": sorted(moved), "anchors": frames, "registers": sorted(seen)}, sort_keys=True))
    print(f"OK: {len(moved)} registers are one boot's accident ({', '.join(sorted(moved))}), and "
          f"every one of them is inside the {len(VECTOR_UNCOMPARED)} that M5 captures without "
          f"comparing. {BUILD / (prefix + VECTOR_NOISE_FILE)} records the reading, stamped with the "
          f"anchors {frames} and the register names it covers; smoke.py refuses a run those do not "
          f"cover.")
    return True


def lightning_flash_seed():
    """M5's seed, from the header that quotes the instruction that writes it.

    `move.w #$2,$714.w` at $1328 — `player_weapon_fire`'s LIGHTNING arm, the image's ONLY writer that
    raises WB_FLASH_TIMER. Scraped rather than written down, so this side and atari/build.sh's
    `m5flash` cannot poke and compile different words (CLAUDE.md §5).

    NOT `flash_seed`, which is the name `frames_script` and `mode_frames` give their PARAMETER: the
    two would shadow each other inside those bodies, and the obvious later edit — defaulting the
    parameter from the scraper — would raise UnboundLocalError in a mode that costs a two-minute
    boot to reach."""
    return wb("PLAYER_LIGHTNING_FLASH")


MODES = {
    "title": mode_title,
    "credits": mode_credits,
    "prompt": mode_prompt,
    "dump": mode_dump,
    "neighbour": mode_neighbour,
    "variance": mode_variance,
    "frames": lambda: mode_frames(frames_argument()),
    "vecnoise": mode_vector_noise,
    "flashnoise": lambda: mode_vector_noise(lightning_flash_seed()),
    "flash": lambda: mode_frames(frames_argument(), lightning_flash_seed()),
    # M6's shipped side. The frame count is the SHIM'S last anchor rather than a number written here,
    # for `anchor_frames`' reason: the two sides have to time the same window.
    "timeline": lambda: mode_timeline(max(anchor_frames())),
    "flashtimeline": lambda: mode_timeline(max(anchor_frames()), lightning_flash_seed()),
    "psgnoise": lambda: mode_psg_noise(max(anchor_frames())),
    "flashpsgnoise": lambda: mode_psg_noise(max(anchor_frames()), lightning_flash_seed()),
    "nofire": lambda: mode_control("nofire", fires=False, disk2=True),
    "nodisk2": lambda: mode_control("nodisk2", fires=True, disk2=False),
}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "dump"
    if mode not in MODES:
        raise SystemExit(__doc__)
    MODES[mode]()


if __name__ == "__main__":
    main()
