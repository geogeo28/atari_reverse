#!/usr/bin/env python3
"""M1, M2, M3, M5 and M6 — reconstructed Wonder Boy code on a 68000, asserted.

    bash atari/build.sh m1    && python3 atari/smoke.py m1
    bash atari/build.sh novbl && python3 atari/smoke.py novbl     # M1's negative control
    bash atari/build.sh m1    && python3 atari/smoke.py mono      # ...and its HARDWARE control

    python3 atari/original.py dump                                # M2 needs the image FIRST
    python3 atari/original.py frames                              # ...and the shipped side's frames
    bash atari/build.sh m2    && python3 atari/smoke.py m2        # THE FRAME DIFFERENTIAL
    bash atari/build.sh m2    && python3 atari/smoke.py m2fault   # ...its MIS-ANCHOR control

    python3 atari/original.py vecnoise                             # M5 REFUSES TO RUN WITHOUT THIS
    bash atari/build.sh m2      && python3 atari/smoke.py m5       # THE HARDWARE-STATE VECTOR
    bash atari/build.sh m2      && python3 atari/smoke.py m5skew   # ...its mis-anchor control
    bash atari/build.sh m5fault && python3 atari/smoke.py m5fault  # ...and its INJECTED-FAULT one
    python3 atari/original.py flash && python3 atari/original.py flashnoise   # the flash's own boots
    bash atari/build.sh m5flash && python3 atari/smoke.py m5flash  # ...THE FLASH ARMS, both sides

    python3 atari/original.py timeline                              # M6 needs the shipped STREAM
    bash atari/build.sh m2      && python3 atari/smoke.py m6        # THE ORDERED WRITE TIMELINE
    bash atari/build.sh m6rearm && python3 atari/smoke.py m6rearm   # ...its RE-ARM control
    python3 atari/original.py flashtimeline                         # ...and the flash run's stream
    bash atari/build.sh m5flash && python3 atari/smoke.py m6flash   # ...flip_screen's last PAIR

    bash atari/build.sh m2      && python3 atari/smoke.py m3        # M3: THE THREE EXITS, DRIVEN
    bash atari/build.sh m3fault && python3 atari/smoke.py m3fault   # ...its HAND-BACK control

    python3 atari/original.py title                                 # the SHIPPED title screen
    bash atari/build.sh title        && python3 atari/smoke.py title        # THE TITLE, DRAWN HERE
    bash atari/build.sh titlecredits && python3 atari/smoke.py titlecredits # ...its PICTURE control

    bash atari/build.sh play  && python3 atari/smoke.py play        # the PLAY build, booted headless
    python3 atari/original.py credits                               # the SHIPPED credits screen
    python3 atari/original.py dump                                  # ...and its post-boot image
    bash atari/build.sh boot      && python3 atari/smoke.py boot      # THE WHOLE CHAIN, ON TARGET
    bash atari/build.sh bootfault && python3 atari/smoke.py bootfault # ...its MIS-RUN control

    bash atari/build.sh ownplay && python3 atari/smoke.py ownplay   # THE OWN-ENTRY PLAY, 5 passes
    bash atari/build.sh ownrun  && python3 atari/smoke.py ownrun    # ...and the UNCAPPED build,
                                                                    #    booted headless (run.sh's)
    python3 atari/smoke.py runsh                                    # ...and the line run.sh execs
    bash atari/run.sh                                               # ...and played, with a screen

WHAT M3 CLAIMS: `game_key_actions` has three endings that are not returns — they pop the frame loop's
return address and `jmp` into the unported boot chain — and all three are MADE TO HAPPEN on the
machine, one run each, each reporting its own `loop_ending`. Then the program exits, and the machine
is inspected from OUTSIDE it, deep in the tail: both installed vectors have stopped being the shim's
and TOS's own frame clock is still advancing. The negative control is each run's own first pass — the
undriven boot that measures where the image is must report that no ending fired and every frame ran —
and `m3fault` is the build whose `teardown` never gives the two vectors back, which must redden every
hand-back row and no other.

WHAT M6 CLAIMS: over the same fifty-two frames, the ORDER in which writes reached the machine — not
where they left it. The reconstruction's screen-base publications are the shipped binary's, flip for
flip; neither side loads a palette while a stage runs or ever re-loads the one already on the chip;
the shipped binary's PSG writes are an exact prefix of ours, register and value in order — which is
this project's first on-target assertion about SOUND; and `m6flash` puts `flip_screen`'s last two
writes in bus order, which is the only surface that can see the one shifter-sink mutant `../STATUS.md`
measures as surviving everything else.

WHAT M5 CLAIMS, over M2: at the same four anchors the machine ITSELF agrees — TWENTY registers of a
thirty-six-register hardware-state vector, captured on both sides by the same debugger commands and
read back by the same parser — and so does the picture Hatari renders. The twenty are the sixteen
shifter pens, the resolution and sync registers, the refresh rate and the V-overscan. THE SIXTEEN
YM-2149 REGISTERS ARE CAPTURED, PRINTED AND NOT COMPARED, and that is a measurement rather than an
omission: two boots of the SHIPPED BINARY ITSELF write different sound registers at the same anchor,
because the music's position depends on which vblank the boot finished on. `original.py vecnoise` is
that measurement, this file refuses to run without it, and atari/README.md §10 has the argument. The
sound's own surface is the ordered write timeline, which is M6's and is owed.

`m5flash` adds the one thing the anchored window's own data cannot reach: `flip_screen`'s white-flash
arms, armed on BOTH sides by a declared fabrication (see atari/README.md §10 and wonderboy_main.c's
`arm_the_flash`).

WHAT M2 CLAIMS: the reconstruction's own `game_main_loop` runs fifty-two frames on a real 68000 and
draws, at four anchored frames, the SAME 32000 bytes and the SAME sixteen pens as the shipped 1989
binary running the same fifty-two frames on the same emulated machine. Both sides' pictures are read
where the picture really is — ours out of the image at the address `flip_screen` published, theirs
off the shipped binary's own screen by `savebin` at a breakpoint on $4a0.

WHAT M1 CLAIMS is in README.md's milestone table and in wonderboy_main.c's header. In one sentence:
the reconstruction's own vertical-blank handler runs on a real machine at 50 Hz, and the two hardware
reads that steer the music tempo — the pair PORTABILITY.md §5 names as this project's false-green
surface — really answer for themselves.

SIX CONTROLS, because a check that cannot fail proves nothing, and two of them are not code changes
at all:

  novbl   one store suppressed (the level-4 vector install). Every assertion that depends on the
          machine driving the reconstruction must FAIL. The mode inverts its verdict, so a run that
          PASSES the comparison is the failure.
  mono    the SAME BINARY, booted with Hatari's monochrome monitor. `tempo_drop_value`'s first read
          is the MFP GPIP's monitor-detect bit, so the byte it leaves in the image must move from
          WB_SND_TICK_DROP_50HZ to WB_SND_TICK_DROP_MONO. A code control cannot show that the read is
          LIVE rather than a constant the compiler folded; changing the machine can.
  exit    every mode runs Hatari to the END of --run-vbls and asserts both halves of machine health:
          the emulator's exit status, and its log scanned for bus/address errors and halts whose PC
          is not TOS's own memory-sizing probe. THE STREAMS ARE MERGED, because Hatari writes all of
          its logging to stderr and a parser reading stdout scans an empty string for ever — that is
          a measured year-long blindness in the sibling project, and a run whose captured output does
          not contain Hatari's own banner RAISES here rather than being parsed.

Running past the program's own exit is not tidiness: WB.PRG installs two exception vectors and takes
supervisor, and an incomplete hand-back is only visible AFTER Pterm, when TOS is running on with
whatever the shim left hooked.
"""
import bisect
import collections
import fnmatch
import functools
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC = HERE.parent
sys.path.insert(0, str(REC / "test"))
from layout import wb                                        # noqa: E402
sys.path.insert(0, str(HERE))
import original                                              # noqa: E402
# reverse/tools — `depack_rad` is what lets the own-entry mode say WHICH overlay crossed the seam,
# by inflating the shipped file host-side and comparing its first longword against the run's own.
# Same path insert gen_image.py makes, for the same directory and the same reason.
sys.path.insert(0, str(HERE.parents[3] / "tools"))
import depack_rad                                            # noqa: E402

DISK = HERE / "disk"
BUILD = HERE / "build"
OUT = HERE / "out"

# Hatari needs room for the 1 MiB image plus ~100 KB of program; 2 MB is the smallest that fits and
# 4 leaves the choice from mattering.
MEMSIZE_MB = 4
# TOS's OWN BOOT IS THOUSANDS OF VBLANKS, and this is the measurement rather than a guess: at 900
# the program was never Pexec'd at all — the desktop had not appeared yet — and the mode reported
# "no STATS.BIN" for a build that was fine. 6000 puts the boot, the run, the three IKBD resets
# (~300 ms each — `pin_sched_wait8` asks for the acknowledge twice, see wonderboy_main.c) and a long
# tail after Pterm inside one run, at ~3 s of wall clock under --fast-forward. The tail is not slack:
# an incomplete hand-back only shows up after the program has gone, which is why every mode here runs
# to the END rather than stopping at the dump.
RUN_VBLS = 6000
# M2 runs 52 frames of the reconstruction on top of the same TOS boot. Measured: 588 vblanks for the
# frame loop, so this is the M1 run plus that, plus the same tail. The frame loop has its OWN bound
# (wonderboy_main.c's M2_VBL_BUDGET, 2000) which is deliberately well inside this one — a watchdog
# longer than the harness's own limit is not a watchdog, and reporting "no record" says nothing
# about which check broke.
M2_RUN_VBLS = 9000
STATS_FILE = "STATS.BIN"

# ---- the record, named in the same order wonderboy_main.c declares it -------------------------
# THE SIZE IS CHECKED, so a field added in C and not here is a loud parse error rather than a
# silently misread record.
STATS_FORMAT = ">IIIIIIHHHHBBBBBB2x"
STATS_FIELDS = ("magic", "bytes", "image_base", "screen_base_published", "shim_vbl_ticks",
                "ikbd_bytes", "readback_failed", "readback_attempted", "vbl_counter",
                "floppy_idle_timer", "tick_drop_value", "psg_port_a_at_entry",
                "psg_port_a_after_run", "key_last_scancode", "sched_wait_returned",
                "ikbd_last_byte")
STATS_MAGIC = 0x57424131          # 'WBA1' — wonderboy_main.c's STATS_MAGIC


def readback_bits():
    """The RB_* bit numbers, READ OUT OF THE C rather than restated.

    Joust's lesson, taken at the start rather than after: a bit added in C and not classified here
    would never be asserted, and an unasserted check is indistinguishable from a passing one.
    """
    source = (HERE / "wonderboy_main.c").read_text()
    bits = {name: int(value)
            for name, value in re.findall(r"^#define\s+(RB_\w+)\s+(\d+)u", source, re.M)}
    if not bits:
        raise SystemExit("no RB_* bits found in wonderboy_main.c — the scraper has gone blind")
    return bits


RB = readback_bits()


def mask(*names):
    return sum(1 << RB[name] for name in names)


# Every bit, partitioned. A bit in neither list is a hard error below, which is what stops a
# sixteenth check being added in C and silently never asserted.
BOOT_BITS = ("RB_IMAGE_BASE_ALIGNED", "RB_VBL_VECTOR_INSTALLED", "RB_ACIA_VECTOR_INSTALLED",
             "RB_RESOLUTION_SET", "RB_SYNC_SET", "RB_SCREEN_BASE_PUBLISHED", "RB_VBL_TICKING",
             "RB_IKBD_REPLIED", "RB_PSG_PORT_A_DESELECTED")
TEARDOWN_BITS = ("RB_VBL_VECTOR_RESTORED", "RB_ACIA_VECTOR_RESTORED", "RB_RESOLUTION_RESTORED",
                 "RB_SYNC_RESTORED", "RB_SCREEN_BASE_RESTORED", "RB_PSG_PORT_A_RESTORED",
                 "RB_IKBD_DRAINED")

# ---- the image constants, from the C headers through test/layout.py ---------------------------
TICK_DROP_50HZ = wb("SND_TICK_DROP_50HZ")
TICK_DROP_MONO = wb("SND_TICK_DROP_MONO")
PSG_PORT_A_KEEP = wb("PSG_PORT_A_KEEP")
PSG_DRIVES_DESELECTED = wb("PSG_DRIVES_DESELECTED")

# gen_image.py's seeds, read from gen_image.py rather than restated — the same rule as RB above.
def gen_image_constant(name):
    source = (HERE / "gen_image.py").read_text()
    found = re.search(r"^%s = (0x[0-9a-fA-F]+|\d+)" % name, source, re.M)
    if not found:
        raise SystemExit(f"{name} is not a plain constant in gen_image.py")
    return int(found.group(1), 0)


@functools.lru_cache(maxsize=None)
def _staged_image(path, mtime):
    """The staged image's bytes, cached on (path, mtime).

    KEYED ON THE MTIME AND NOT ONLY THE PATH, because `stage_drive` REWRITES this file between the
    passes of a two-boot mode — a cache on the path alone would serve the previous mode's image to
    every `staged()` reader after the first. Every mode reads a handful of named words out of a
    136 KB (M1) or 523 KB (frame) file and the readers are scattered, so the file was being re-read
    once per constant."""
    del mtime                                            # part of the key, not of the read
    return Path(path).read_bytes()


def staged_block(addr, length, what):
    """`length` bytes at Ghidra address `addr`, out of the staged image the .PRG actually loaded.

    Not written down here and not taken from the .PRG's own report: these are the very bytes the
    reconstruction ran on. The load base comes through `original.WB_STAGED_AT`, which scrapes
    project.toml for build.sh's reason — that file is where the 0x3f8 base is argued for, and this
    file already spells it that way everywhere else. `what` names the caller's subject in the
    failure."""
    at = addr - original.WB_STAGED_AT
    image = DISK / "WB.IMG"
    blob = _staged_image(str(image), image.stat().st_mtime_ns)
    if not 0 <= at or at + length > len(blob):
        raise SystemExit(f"{what} is outside the staged block — cannot read it back")
    return blob[at:at + length]


def staged(name, width=4):
    """A named image word, read out of the staged image."""
    return int.from_bytes(staged_block(wb(name), width, f"WB_{name}"), "big")


def staged_screen_front():
    """WB_SCREEN_FRONT's longword. Comparing against it turns M1's check 5 from "the arithmetic
    produced something plausible" into "the arithmetic produced THIS"."""
    return staged("SCREEN_FRONT")


FLOPPY_IDLE_TICKS = gen_image_constant("FLOPPY_IDLE_TICKS")
TICK_DROP_UNWRITTEN = gen_image_constant("TICK_DROP_UNWRITTEN")


# One plain-integer `#define` out of wonderboy_main.c — the same rule as RB above, and defined in
# original.py because BOTH files scrape that header (this one for the record formats, that one for
# the machine registers M5's vector reads). Two scrapers over one file is one scraper that quietly
# stops matching.
c_constant = original.c_constant

SMOKE_VBLS = c_constant("SMOKE_VBLS")


# ---- Hatari -----------------------------------------------------------------------------------

# ONE DEFINITION EACH, IN original.py, and imported here.
#
# Both files boot Hatari and both read its log, so both once carried their own copy of the ROM
# search, the fault pattern and the memory-probe allowlist. THE ALLOWLIST IS THE ONE THAT MATTERS:
# it is the exact PC of TOS's own memory-sizing probe on each ROM, and the whole point of it being
# PC-exact rather than "the PC is in ROM" is that a stale vector sends the CPU into ROM code — so a
# range test would excuse the very class the scan exists for. Two copies of a safety allowlist is
# one copy that quietly stops matching the machine.
find_tos = original.find_tos
MEMORY_PROBE_PCS = original.MEMORY_PROBE_PCS
FAULT_RE = original.FAULT_RE
FAULT_PC_RE = original.FAULT_PC_RE
HATARI_BANNER_RE = original.HATARI_BANNER_RE


# ---- the resources the drive stands in for -------------------------------------------------------
#
# THE TITLE BUILD ASKS THE MACHINE FOR A FILE BY NAME, so the drive has to carry the file. Disk 1
# holds exactly two resources — TITLESCR.RAD and CREDITS.RAD, beside AUTO/SWB.PRG — and both title
# builds get both, because which one a `.PRG` will ask for is compiled into it and only reported
# afterwards. Staging the pair is what makes the mode and its control boot the same drive.
RESOURCE_ROW_BYTES = 1 << wb("RESOURCE_FILE_ROW_SHIFT")
RESOURCE_FILE_COUNT = wb("RESOURCE_FILE_COUNT")
DISK1_RESOURCES = (wb("RESOURCE_TITLESCR"), wb("RESOURCE_CREDITS"))
# What FAT pads a short 8.3 field with, and what a GEMDOS path must not carry. See `resource_name`.
FAT_PAD = b" "
# HOW `stage_drive` SWEEPS THE PREVIOUS MODE'S RESOURCES OFF THE DRIVE. It cannot ask
# `resource_name` — the image the names come out of is not staged yet at that point — so it keys on
# the two extensions the forty rows carry, which `stage_resources` re-derives per file it stages.
RESOURCE_GLOBS = ("*.RAD", "*.CRU")


def resource_name(index):
    """Row `index` of WB_RESOURCE_FILE_TABLE as a GEMDOS path, out of the staged image itself.

    THE PADDING IS DROPPED HERE FOR THE REASON THE BACKEND DROPS IT. The row is a FAT12 directory
    entry's name field — space-padded to eight characters, which two of the forty rows really are
    ("CREDITS .RAD", "SPRITES .CRU") — and GEMDOS `Fopen` takes a path, in which a space is an
    ordinary character. wonderboy_backend.c's `gemdos_name` performs exactly this translation on the
    machine, and the two spellings are PINNED TO EACH OTHER BY THE RUN rather than by inspection: if
    either of them were wrong the file staged here and the file the .PRG asks for would differ, the
    load would return WB_LOAD_DISK_ERROR, and the mode's first row would be red.

    Read out of the image the .PRG loaded rather than written down, so the two sides cannot name
    different files, and so the shipped table stays the single source of what a resource is called.
    """
    # A NUMBER THE BINARY REPORTED IS NOT A ROW UNTIL IT IS CHECKED. `title_checks` prints this
    # name inside the very row that asserts the index, so an out-of-range one has to come back as
    # text rather than as a read past the staged block — a traceback there would throw away the
    # whole report, and the boot that paid for it, exactly as an unguarded capture read once did.
    if index >= RESOURCE_FILE_COUNT:
        return f"<row {index:#x}, past the {RESOURCE_FILE_COUNT}-row table>"
    row = staged_block(wb("RESOURCE_FILE_TABLE") + index * RESOURCE_ROW_BYTES,
                       RESOURCE_ROW_BYTES, f"WB_RESOURCE_FILE_TABLE row {index}")
    return row.split(b"\0")[0].replace(FAT_PAD, b"").decode("ascii")


def stage_drive(prg, withhold=()):
    """Put the .PRG on the drive TOGETHER WITH THE IMAGE IT WAS BUILT AGAINST.

    `withhold` names staged resources to take back OFF the drive again, and it is how a mode drives
    a REFUSAL with real data: the reconstruction asks the machine for a file by the name the
    resource table carries, and a name the volume does not answer is exactly what
    `load_resource_by_index` refuses on. Removed after staging rather than skipped during it, so the
    corpus checks (`refuse_a_hybrid_resource`) still run over the whole set and a withheld name that
    was never staged in the first place is refused below rather than passing silently.

    THE IMAGE IS PART OF THE BUILD, NOT PART OF THE DRIVE. The modes stage different images — M1 the
    program plus seeds, M2 the original's post-boot RAM, 136,408 bytes against 523,272 — and each
    .PRG has its own length compiled in. Copying only the .PRG means `smoke.py m2` after
    `build.sh m1` boots the frame build over the M1 image; measured, and it failed as "no M2.BIN",
    which reads like a crash. build.sh keeps `WB-<mode>.IMG` beside `WB-<mode>.PRG` for this."""
    # THE WHOLE DRIVE IS REMADE ON EVERY CALL, AND THAT IS DELIBERATE. Phase F's first draft cached
    # the fixtures on (build, withhold set) and skipped the copy when they matched; measured, that
    # saved ~1.8 ms per staging — about 5 ms across `mode_ownplay`'s six boots, against ~33 seconds
    # of Hatari each — and bought a module-global that a later DISK/-touching path could leave stale.
    # The failure it would then produce is the one this project exists to refuse: a pass booting over
    # the PREVIOUS pass's drive still satisfies pass 5's and pass 6's own refusal signatures, because
    # "the file is not on the volume" is exactly what a stale withhold leaves behind. Copying is
    # cheap and being certain is not, so nothing here remembers anything.
    prg = Path(prg)

    # EVERY output the program can write is deleted first. A stale FRAME.BIN from the previous build
    # is the shape of failure that PASSES: the run crashes, the comparison reads yesterday's picture,
    # and the mode reports a match.
    for stale in (STATS_FILE, M2_FILE, TITLE_FILE, BOOT_FILE, BOOT_IMAGE_FILE, OWN_FILE,
                  M2_FRAME_FILE, M2_PENS_FILE, OWN_PROMPT_FILE, OWN_PROMPT_PENS_FILE,
                  M3_RESCUED_M2, M3_RESCUED_STATS):
        (DISK / stale).unlink(missing_ok=True)
    # ...AND EVERY RESOURCE, by extension rather than by name. A `.RAD` this mode did not stage is
    # one the PREVIOUS mode did, and a title build asks the machine for its file BY NAME — so a
    # leftover is a picture from another run that the depack would happily inflate. The names come
    # out of the image below, which is not written yet, so the sweep keys on what they all are.
    for pattern in RESOURCE_GLOBS:
        for stale in DISK.glob(pattern):
            stale.unlink()
    (DISK / DRIVE_PRG).write_bytes(prg.read_bytes())
    image = prg.with_suffix(".IMG")
    if not image.exists():
        raise SystemExit(f"{image} is missing — rebuild with `bash atari/build.sh`, which keeps the "
                         f"image beside the .PRG it was compiled for")
    (DISK / "WB.IMG").write_bytes(image.read_bytes())
    # THE PALETTE IS REQUIRED WHEREVER THE BUILD PRODUCED ONE, and "if it exists" was the wrong
    # test: build.sh emits `WB-<mode>.PENS` for the frame build and deletes it for the others, so a
    # frame build whose palette went missing would silently boot with none — and `stage_file` in the
    # shim returns 0, `wonderboy_main` returns 1, and the mode reports "no M2.BIN", which reads like
    # a crash. Keyed on what the build emitted, and absent-when-expected is named.
    pens = prg.with_suffix(".PENS")
    (DISK / "PENS.IMG").unlink(missing_ok=True)
    if prg.name in FRAME_BUILDS:
        if not pens.exists():
            raise SystemExit(f"{pens} is missing — the frame build stages the original's sixteen "
                             f"pens beside its image; rebuild with `bash atari/build.sh m2`")
        (DISK / "PENS.IMG").write_bytes(pens.read_bytes())
    # THE TITLE BUILDS GET DISK 1's RESOURCES, and keyed on the BUILD for the reason the palette is:
    # a build that reached the drive without them would report WB_LOAD_DISK_ERROR, which reads like
    # a defect in the reconstruction rather than a missing fixture.
    if prg.name in TITLE_PRGS:
        stage_resources(DISK1_RESOURCES, DISK1_TREES)
    # ...AND THE BOOT BUILDS GET THE WHOLE CHAIN'S SET, which is disk 1's two and disk 2's three.
    # The original's boot asks a player to swap disks between them; this drive is one volume, which
    # is a declared deviation (atari/README.md §14) and the reason the data-disk prompt is never
    # reached.
    if prg.name in BOOT_PRGS:
        stage_resources(boot_resource_indices(), BOOT_RESOURCE_TREES)
    # ...AND THE OWN-ENTRY BUILDS GET TWO MORE, because two of their resources are reached only by an
    # ENDING: the second sequence row's overlay, which a round end loads, and DATADISK.RAD, which
    # ESC's prompt draws. A ladder that could not find one would stop with the code in its record —
    # which is the honest answer to a missing file and reads nothing like a fixture that was
    # forgotten, so the fixture is staged here where the build is known.
    if prg.name in OWN_PRGS:
        stage_resources(own_resource_indices(), BOOT_RESOURCE_TREES)
    for name in withhold:
        staged = DISK / name
        if not staged.exists():
            raise SystemExit(f"FAIL: {name} was to be withheld from the drive, but this build "
                             f"never staged it — so the run would refuse for a reason nobody chose")
        staged.unlink()


# WHAT BOOTS, AND ON WHAT MACHINE — one spelling each, because `run.sh` needs the same answers and a
# GUI launcher that disagreed with the headless modes about any of them would be playing a different
# build on a different machine from the one every check in this file measured. `DRIVE_PRG` is the
# name on the emulated drive and `AUTO_BOOT` is how TOS is told to run it; they are pinned to each
# other below rather than written twice.
DRIVE_PRG = "WB.PRG"
AUTO_BOOT = "C:\\" + DRIVE_PRG
DEFAULT_MONITOR = "rgb"


def run_hatari(prg, monitor=DEFAULT_MONITOR, run_vbls=RUN_VBLS, parse=None, log_name="hatari.log",
               trace=None, withhold=()):
    """Boot `prg` headless, run to the end of --run-vbls, and return the MERGED output.

    `parse` is an optional Hatari DEBUGGER script, which is how M5 reaches the machine's own
    registers: the shim can read the shifter but not the YM-2149's file, and the debugger can. A run
    that carries one also gets `--frameskips 0`, because `screenshot` grabs the RENDERED surface and
    under --fast-forward Hatari skips rendering frames it still emulates — asking for every frame
    narrows the window in which a capture returns whichever frame was drawn last. It does NOT close
    it; atari/README.md §10 has the measurement of what is left."""
    stage_drive(prg, withhold)

    rom = find_tos()
    # `--statusbar off` AND `--drive-led off`: both are emulator chrome, and the LED is the one that
    # bit. With the statusbar hidden Hatari draws a small activity LED in the top-right BORDER, our
    # side's run touches the GEMDOS drive and the shipped side's does not, so the first rendered
    # compare differed by a green rectangle outside the game's 320x200 — and the extra colours pushed
    # Hatari's PNG writer from a palette image to a truecolour one, so the two encodings could never
    # have matched byte for byte whatever the pixels did. Chrome is not the picture the game draws.
    args = ["hatari", "--sound", "off", "--fast-forward", "on", "--confirm-quit", "off",
            "--statusbar", "off", "--drive-led", "off", "--frameskips", "0",
            "--memsize", str(MEMSIZE_MB), "--monitor", monitor,
            "--run-vbls", str(run_vbls), "--harddrive", str(DISK), "--auto", AUTO_BOOT]
    if rom:
        args[1:1] = ["--tos", rom]
    if parse is not None:
        args += ["--parse", str(parse)]
    # M6's instrument, and it rides along on a run that was happening anyway: the trace is what
    # reached the hardware, in order, which is the one surface a snapshot cannot be.
    if trace is not None:
        args += ["--trace", trace]
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    done = subprocess.run(args, env=env, stdin=subprocess.DEVNULL, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    OUT.mkdir(exist_ok=True)
    # ONE LOG PER RUN, not one per mode: M5 boots our side TWICE (once plain for the record and the
    # framebuffers, once under the debugger for the vector) and a shared name would leave only the
    # second, which is the one whose captures are already parsed.
    (OUT / log_name).write_text(done.stdout)
    return done.returncode, done.stdout, rom


def check_machine_health(status, log, assert_status=True):
    """Both halves: the emulator's return code, and its log scanned for what the code survives."""
    if not HATARI_BANNER_RE.search(log):
        raise SystemExit("FAIL: the captured output carries none of Hatari's own logging — the scan "
                         "below would be reading an empty string (see this file's header)")
    faults = original.machine_faults(log)     # the same scan the shipped-side runs get
    problems = []
    if faults:
        problems.append("unhealthy machine: " + " | ".join(faults[:4]))
    if assert_status and status != 0:
        problems.append(f"Hatari exited {status}")
    return problems


# WHERE A FORMAT WIDER THAN ITS FIELD LIST PUTS THE SURPLUS. Only `M2.BIN` has one — the anchor
# words the binary was compiled with — and it is KEPT rather than dropped, because the reader that
# needs it is the one pinning those anchors against this file's own. Not a C field name, and spelt
# so it cannot be mistaken for one.
RECORD_TRAILING = "_trailing"


def read_record(name, fields, fmt, magic, what):
    """One of the four records off the drive: present, the right size, the right magic, and its own
    `bytes` field agreeing with this parser.

    (record, None) or (None, why). ONE READER FOR FOUR RECORDS, and it was four verbatim copies —
    four places for the version check that stops one build's bytes being read as another build's to
    be corrected in three. `what` names the build in the "never reached its own dump" message, and
    every caller passes `name` because M3 has the debugger rename two of them aside at the exit: a
    run whose machine is deliberately left broken can REBOOT and write a second record over the
    first."""
    path = DISK / name
    if not path.exists():
        return None, f"no {name} — {what} never reached its own dump"
    blob = path.read_bytes()
    want = struct.calcsize(fmt)
    if len(blob) != want:
        return None, f"{name} is {len(blob)} bytes, expected {want}"
    unpacked = struct.unpack(fmt, blob)
    record = dict(zip(fields, unpacked))
    if record["magic"] != magic:
        return None, f"{name} magic {record['magic']:#x} != {magic:#x}"
    if record["bytes"] != want:
        return None, f"{name} says {record['bytes']} bytes, this parser expects {want}"
    record[RECORD_TRAILING] = unpacked[len(fields):]
    return record, None


def read_stats(name=STATS_FILE):
    return read_record(name, STATS_FIELDS, STATS_FORMAT, STATS_MAGIC, "the program")


# ---- M2: the frame differential -----------------------------------------------------------------
#
# A SECOND RECORD RATHER THAN FOUR MORE FIELDS IN STATS.BIN — wonderboy_main.c's reason: this file
# checks STATS.BIN's size against its format string, so a record that grew per build mode would make
# the M1 parser's own version check fire on an M2 run. Two records, two magics, two readers.
M2_FILE = "M2.BIN"
M2_FRAME_FILE = "FRAME.BIN"
M2_PENS_FILE = "PENS.BIN"
# WHERE M3 MOVES THE TWO RECORDS AT THE PROGRAM'S EXIT, and it is not filing. A run whose machine is
# deliberately left broken can fall over in the tail, and TOS's answer to that is a RESET — after
# which `--auto` runs `WB.PRG` AGAIN and the second, undriven run writes its own records over the
# first. The debugger renames both aside at `Pterm`, before anything can reboot, so what M3 reads is
# the run it drove. Renamed WITHIN `disk/` because Hatari's `rename` is `rename(2)` and refuses a
# cross-device move — measured, into a scratch directory on another volume.
M3_RESCUED_M2 = "M2FIRST.BIN"
M3_RESCUED_STATS = "STFIRST.BIN"
# WHICH RECORD GOES WHERE, once. Every M3 run renames both — the driven ones and the undriven pass
# that measures where the image is — so no reading of either can be a rebooted machine's second run.
RECORD_RESCUES = ((M2_FILE, M3_RESCUED_M2), (STATS_FILE, M3_RESCUED_STATS))
# Which built .PRG is a frame build — i.e. stages the original's post-boot RAM and needs its palette
# beside it. Several modes boot the SAME binary (`m2` and `m2fault`; `m5` and `m5skew`), so the mode
# name cannot be the test and the artefact set keys on the BUILD instead. The list is build.sh's own
# `FRAME_MODES`, scraped rather than restated: a frame mode added there and not here would boot with
# no palette and report "no M2.BIN", which reads like a crash (CLAUDE.md §5).
def frame_build_names():
    line = re.search(r'^FRAME_MODES="([^"]+)"', (HERE / "build.sh").read_text(), re.M)
    if not line:
        raise SystemExit("build.sh no longer defines FRAME_MODES — the two files would then "
                         "disagree about which builds need the original's palette staged")
    return {f"WB-{mode}.PRG" for mode in line.group(1).split()}


FRAME_BUILDS = frame_build_names()
# The trailing words are the ANCHOR LIST THE BINARY CARRIES — see wonderboy_main.c's `anchor_frames`.
# Its length is `M2_ANCHOR_MAX`, read out of the C so the two sides cannot disagree about the record's
# shape; `anchor_count` says how much of it is real. The size is checked against `record["bytes"]`,
# so a field added in C and not here is a loud parse error rather than a silently misread record.
M2_ANCHOR_MAX = c_constant("M2_ANCHOR_MAX")
M2_FORMAT = ">17I%dH" % M2_ANCHOR_MAX
M2_FIELDS = ("magic", "bytes", "image_base", "frames_requested", "frames_run", "loop_ending",
             "screen_front", "screen_base_published", "poll16_calls", "shim_vbl_ticks",
             "pens_readback_failed", "shifter_base", "screen_front_out_of_range", "capture_pc",
             "flash_timer_at_entry", "fault_pen", "anchor_count")
M2_MAGIC = c_constant("M2_MAGIC")  # 'WBA2'

# DERIVED FROM THE SAME PLACES THE C DERIVES THEM, rather than written down again. The screen's two
# dimensions and the pen count are `../include/wonderboy.h`'s, which test/layout.py scrapes and
# wonderboy_main.c `#include`s; the pen mask and the loop's normal return are the shim's and
# `../include/game.h`'s. CLAUDE.md §5: one canonical definition, the other pinned to it.
SCREEN_BYTES = original.SCREEN_BYTES
PALETTE_PENS = original.PALETTE_PENS
PALETTE_BYTES = original.PALETTE_BYTES
ST_PEN_MASK = original.ST_PEN_MASK
LOOP_RETURNED = wb("KEY_ACTIONS_RETURNED")
# One 68000 longword. Hoisted above its first user (M3's `savebin` widths) when the boot section
# below needed it too — CLAUDE.md §5's narrowest scope that covers both uses.
LONGWORD_BYTES = 4
# Two waits per frame, each spinning until a level-4 interrupt moves WB_VBL_COUNTER. A count barely
# above 2 per frame would mean the predicate was already true and nothing ever spun — which is what
# `sched_poll16` shipping unpinned looked like. Measured: ~330 per frame.
MIN_POLL16_PER_FRAME = 4
# How far `m2fault` slides our frames along the shipped side's. One anchor: the smallest slip the
# differential could suffer, and therefore the hardest for it to notice.
MIS_ANCHOR_SHIFT = 1
# The two surfaces a frame row can compare. Part of a row's structural key, because the same anchor
# pair carries one row of each and they are not breakable under the same conditions.
BITPLANES, PENS = "bitplanes", "pens"


def read_m2(name=M2_FILE):
    """The frame build's record, plus the one check no other record needs."""
    record, why = read_record(name, M2_FIELDS, M2_FORMAT, M2_MAGIC, "the frame build")
    if record is None:
        return None, why
    # THE ANCHORS THE BINARY RAN, against the anchors this file is about to label its rows with.
    # Both are M2_ANCHOR_FRAMES — one compiled into the .PRG, one scraped from the source NOW — so
    # editing the list and running the smoke without rebuilding would otherwise compare slot 2 (the
    # binary's frame 51) against the shipped frame the new list names, and print the new label on
    # it. The count alone is not enough, because the failure that matters keeps the count.
    ran = list(record[RECORD_TRAILING][:record["anchor_count"]])
    want_anchors = original.anchor_frames()
    if ran != want_anchors:
        return None, (f"{name} was built for anchors {ran} but wonderboy_main.c now says "
                      f"{want_anchors} — rebuild with `bash atari/build.sh m2`, because every frame "
                      f"row below would be labelled with a frame the binary did not photograph")
    return record, None


def shipped_frame(frame, prefix=""):
    """The shipped binary's picture and pens at `frame`, as `original.py frames` left them.

    The picture is cut out of the dumped screen region at the address the SHIPPED binary's own
    WB_SCREEN_FRONT names at that moment — read from the run, not assumed, because the two buffers
    alternate and picking the wrong one is exactly the mistake this comparison would not survive.

    `prefix` SELECTS WHICH BOOT OF THE ORIGINAL, and it is a parameter rather than a constant because
    M5's flash run compares against a DIFFERENT boot of the shipped binary — one with WB_FLASH_TIMER
    poked. Measured on the first `m5flash` run, where this function still read the unflashed boot's
    artefacts: the vector (which does take the prefix) agreed about colour 0 being white while the
    pen row, reading the other boot, called it a divergence. Two boots compared as one."""
    low, _ = original.SCREEN_REGION
    build = original.BUILD
    names = [prefix + f"{stem}{frame}.BIN" for stem in ("OSCR", "OFRONT", "OPEN")]
    missing = [name for name in names if not (build / name).exists()]
    if missing:
        raise SystemExit(f"{', '.join(missing)} is missing — run `python3 atari/original.py "
                         f"{original.FRAME_PRODUCER[prefix]}`")
    screens, front_file, pens_file = names
    front = struct.unpack(">I", (build / front_file).read_bytes())[0]
    screens = (build / screens).read_bytes()
    at = front - low
    if not 0 <= at <= len(screens) - SCREEN_BYTES:
        raise SystemExit(f"the shipped binary's frame {frame} front buffer is {front:#x}, outside "
                         f"the dumped region — original.py's SCREEN_REGION no longer covers it")
    return screens[at:at + SCREEN_BYTES], front, (build / pens_file).read_bytes()


# ONE MASKING RULE, in original.py beside the paragraph that argues it (the ST implements three bits
# per gun and the fourth reads back as bus noise). It was copied here and then a third time inside
# the determinism check, and a rule applied at three sites is a rule two of them can keep after the
# third is corrected — the M2 pen row and the M5 determinism row would then disagree about what "the
# same palette" means, with nothing pinning them together.
pen_words = original.pen_words


def differing_bytes(mine, theirs):
    """Which byte offsets two same-length screen captures disagree at.

    THE COMMON CASE IS EQUAL, AND THE SHORT-CIRCUIT IS THE WHOLE REASON THIS IS A FUNCTION. A
    32000-iteration Python comprehension to establish equality is 32000 interpreter steps per
    comparison for something the interpreter does in one `memcmp`, and this file makes that
    comparison four anchors deep in the frame modes, once per picture differential and once more in
    the prompt control's premise. Written out three times it was short-circuited in two of them."""
    if mine == theirs:
        return []
    return [at for at in range(len(theirs)) if mine[at] != theirs[at]]


# THE ONE M1 READ-BACK M2'S DATA CANNOT REACH, derived from the staged image and PRINTED.
#
# `RB_PSG_PORT_A_DESELECTED` asserts a TRANSITION: `vbl_handler` counts WB_FLOPPY_IDLE_TIMER down,
# and on the tick it reaches zero `floppy_deselect_drives` writes the real YM2149. M1 SEEDS that
# countdown (gen_image.py's FLOPPY_IDLE_TICKS) precisely so a short run witnesses the write. M2 seeds
# nothing — its image is the original's own post-boot RAM — and the original's boot ran its countdown
# out long before the anchor, so the word is already $0000 and the arm cannot fire in fifty-two
# frames. Measured, not assumed: the value is read back out of the staged image below.
#
# It is EXCLUDED rather than asserted-and-failing, and the exclusion is PRINTED — M1's
# `machine_driven` rule, that a check quietly dropped from a run is a check nobody is running. And it
# is masked out of the comparison in BOTH directions, so a ROM that happens to satisfy it at entry
# (EmuTOS leaves port A already deselected) does not turn the exclusion into a false red.
FLOPPY_ARM_DISARMED = 0


def unreachable_readbacks():
    """(mask, why) — the read-back bits this run's own staged data cannot reach."""
    if staged("FLOPPY_IDLE_TIMER", width=2) != FLOPPY_ARM_DISARMED:
        return 0, None
    return mask("RB_PSG_PORT_A_DESELECTED"), (
        "'RB_PSG_PORT_A_DESELECTED' is excluded: WB_FLOPPY_IDLE_TIMER is 0 in the staged image, so "
        "vbl_handler's countdown is already spent and the arm that writes the YM2149 cannot fire in "
        "this run. M1 seeds that countdown to witness the write; M2 stages the original's own RAM "
        "and seeds nothing, which is the point of M2's image and the cost of it.")


# THE TWO READ-BACK ROWS' NAMES, once. They are STRUCTURAL KEYS and not only labels: `MACHINE_DRIVEN`
# selects the second by name for `novbl`, and M3's hand-back control does the same — the teardown bits
# live in `readback_failed`, so suppressing the vector restores must break exactly that row and leave
# "read-backs ran" standing. Two controls matching on a hand-written string is one control that
# quietly stops matching after a reword.
RB_RAN_ROW = "read-backs ran"
RB_PASSED_ROW = "read-backs passed"


def readback_checks(record, also_unreachable=()):
    """The two M1 read-back rows, for every mode that boots a build which writes STATS.BIN.

    THE M1 READ-BACKS APPLY TO EVERY BUILD HERE, and dropping them is a defect this file has had
    twice. The frame builds install the same two vectors, set the same video mode, publish the same
    screen base and hand the machine back the same way; `STATS.BIN` is written on that path exactly
    as on M1's. An earlier draft routed `m2` past the record and left all sixteen checks — including
    every teardown restore — unasserted, so a frame build that never handed the machine back would
    have reported a clean M2; the M6 modes then did the same thing again, reading the record only for
    `image_base`. Extracted here so the next mode that reads `STATS.BIN` gets them by calling one
    function rather than by remembering.

    TWO WORDS AND NOT ONE: `readback_failed` says a write did not take, `readback_attempted` says
    which checks RAN, and the second is compared against an exact mask — a check that quietly stops
    executing is indistinguishable from a passing one in a bare fault word."""
    want_attempted = mask(*BOOT_BITS, *TEARDOWN_BITS)
    unreachable, why = unreachable_readbacks()
    if why:
        print(f"   note {why}")
    # ...AND THE BITS A PARTICULAR PASS CANNOT REACH, on the same terms: EXCLUDED WITH THE REASON
    # PRINTED rather than quietly dropped, because a check nobody is running and a check that passed
    # read the same in a bare fault word. The caller names them because the reason is the caller's —
    # `unreachable_readbacks` above answers from the staged image, and this answers from what the
    # RUN was asked to do. Each entry is (bit name, why this run cannot reach it).
    for name, reason in also_unreachable:
        unreachable |= mask(name)
        print(f"   note '{name}' is excluded: {reason}")
    return [
        (RB_RAN_ROW, record["readback_attempted"] == want_attempted,
         f"attempted {record['readback_attempted']:#06x}, expected exactly {want_attempted:#06x}"),
        (RB_PASSED_ROW, record["readback_failed"] & ~unreachable == 0,
         f"failed {record['readback_failed']:#06x}"
         + (" — " + ", ".join(n for n in RB if record["readback_failed"] >> RB[n] & 1)
            if record["readback_failed"] else "")
         + (f", of which {unreachable:#06x} is excluded" if unreachable else "")),
    ]


def m2_checks(record, stats, anchors, shift=0, prefix=""):
    """The frame differential, one row per anchor, plus the preconditions BOTH records carry.

    Rows are `(name, ok, detail, key)`. `key` is `None` for a precondition and
    `(surface, ours, theirs)` for a frame row — a STRUCTURAL key, so the mis-anchor control can
    select the rows a shift can reach without matching on formatted names. An earlier draft joined
    the two by string equality and by a shift hardcoded in two places.

    THE SURFACE IS PART OF THE KEY AND THE FIRST STRUCTURAL DRAFT LEFT IT OUT, keying on the anchor
    pair alone. The two rows over one pair then shared a key, and a pair whose BITPLANES move while
    its PENS do not — which is every moving pair in this game, the palette being constant across the
    window — marked the pens row breakable too. The control demanded a failure the data cannot
    produce and reddened a working build.

    `shift` is the MIS-ANCHOR control: our frame at anchor i is compared against the shipped
    binary's at anchor i + shift, and the mode inverts its verdict."""
    checks = []

    def add(name, ok, detail, key=None):
        checks.append((name, bool(ok), detail, key))

    for name, ok, detail in readback_checks(stats):
        add(name, ok, detail)

    add("every frame ran", record["frames_run"] == record["frames_requested"]
        and record["loop_ending"] == LOOP_RETURNED,
        f"{record['frames_run']} of {record['frames_requested']} frames, "
        f"game_main_loop returned {record['loop_ending']}")
    # A capture REFUSED because the published address left the image is not a capture of zeros, and
    # FRAME.BIN cannot tell the two apart — wonderboy_main.c gives it its own field for that reason.
    add("every capture was taken", record["screen_front_out_of_range"] == 0,
        f"WB_SCREEN_FRONT named {record['screen_front']:#x}, outside the image, so the frame was "
        f"not copied" if record["screen_front_out_of_range"] else "no capture was refused")
    add("the staged palette took", record["pens_readback_failed"] == 0,
        f"pens that did not read back: {record['pens_readback_failed']:#06x}")
    # SCHED_POLL16'S DISCHARGE, and it is this number rather than the frames alone. `flip_screen`'s
    # two waits are the function's only callers and they are uncapped spins on WB_VBL_COUNTER: a
    # frame count says they returned, but only the iteration count says they SPUN — i.e. that what
    # ended them was a level-4 interrupt raising the counter and not a predicate already true.
    add("flip_screen's two waits really spun",
        record["poll16_calls"] >= MIN_POLL16_PER_FRAME * record["frames_run"],
        f"{record['poll16_calls']} sched_poll16 iterations over {record['frames_run']} frames "
        f"({record['poll16_calls'] / max(record['frames_run'], 1):.0f} per frame; a wait that never "
        f"spun would give 2)")

    # THE ROW THE FRAMEBUFFER COMPARE CANNOT REACH, and the one M2 exists to add over M1.
    # `flip_screen`'s two `shifter_write_byte`s pick which buffer the machine DISPLAYS; they change
    # no image byte, so both of the mutants over them leave every compared pixel correct:
    #   * the wrong buffer published — the shifter ends on WB_SCREEN_BACK's address, not the front's;
    #   * the two base bytes swapped AT flip_screen's own call sites (the swap in the SHARED
    #     translation is already caught at M1) — $078000 goes out as $800700.
    # Both move this number and nothing else, and both are measured dying in atari/README.md.
    want_base = record["image_base"] + record["screen_front"]
    add("the shifter displays the buffer the last flip published",
        record["shifter_base"] == want_base and record["screen_base_published"] == want_base,
        f"$ffff8201/8203 read back {record['shifter_base']:#x}, the backend wrote "
        f"{record['screen_base_published']:#x}, WB_SCREEN_FRONT is {record['screen_front']:#x} "
        f"so the image's own front buffer is at {want_base:#x}")

    # M2.BIN existing does not mean the captures do: they are three separate `Fcreate`/`Fwrite`
    # pairs and `write_file` swallows a failed create, so a full GEMDOS drive writes the record and
    # neither picture. Reading them unguarded raised FileNotFoundError out of the middle of a check
    # — a traceback in place of a verdict, throwing away the boot that had already been paid for.
    missing = [name for name in (M2_FRAME_FILE, M2_PENS_FILE) if not (DISK / name).exists()]
    if missing:
        add("the captures were written", False,
            f"{', '.join(missing)} absent although {M2_FILE} was written — the run reached its own "
            f"dump, so this is the capture write failing rather than the program dying")
        return checks
    ours = (DISK / M2_FRAME_FILE).read_bytes()
    our_pens = (DISK / M2_PENS_FILE).read_bytes()
    if len(ours) != SCREEN_BYTES * len(anchors) or len(our_pens) != PALETTE_BYTES * len(anchors):
        add("the capture is the right size", False,
            f"{len(ours)} frame bytes and {len(our_pens)} pen bytes for {len(anchors)} anchors, "
            f"expected {SCREEN_BYTES * len(anchors)} and {PALETTE_BYTES * len(anchors)}")
        return checks

    for index, frame in enumerate(anchors):
        against = anchors[(index + shift) % len(anchors)]
        theirs, front, their_pens = shipped_frame(against, prefix)
        mine = ours[index * SCREEN_BYTES:(index + 1) * SCREEN_BYTES]
        wrong = differing_bytes(mine, theirs)
        rows = sorted({at // wb("SCREEN_LINE") for at in wrong})
        add(f"frame {frame} bitplanes" + (f" (vs shipped {against})" if shift else ""),
            not wrong,
            f"{len(wrong)} of {SCREEN_BYTES} bytes differ over {len(rows)} scanlines"
            + (f" {rows[:8]}" if rows else "") + f"; shipped front buffer {front:#x}",
            (BITPLANES, frame, against))
        mine_pens = pen_words(our_pens[index * PALETTE_BYTES:(index + 1) * PALETTE_BYTES])
        shipped_pens = pen_words(their_pens)
        wrong_pens = [pen for pen in range(PALETTE_PENS) if mine_pens[pen] != shipped_pens[pen]]
        add(f"frame {frame} pens" + (f" (vs shipped {against})" if shift else ""), not wrong_pens,
            f"pens {wrong_pens} differ" if wrong_pens
            else " ".join("%03x" % pen for pen in mine_pens),
            (PENS, frame, against))
    return checks


def report_neighbour_margins(anchors):
    """BY HOW MUCH a mis-anchor would show, measured on the shipped side and PRINTED.

    An anchor is only evidence if a mis-anchor is detectable. These are the shipped binary's own
    anchor frames differenced against each other; a pair that comes back 0 is a boundary the
    differential above cannot tell apart, and saying so is the point of printing it.

    THE PAIRS ARE THE ONES THE CONTROL ACTUALLY SELECTS — `zip(anchors, anchors[1:])` omitted the
    wrap-around pair (last vs first), which `m2fault` does compare and which this table therefore
    has to account for, or the printed evidence and the control disagree about one row."""
    print("   mis-anchor margins, shipped frame against shipped frame:")
    for index, first in enumerate(anchors):
        second = anchors[(index + 1) % len(anchors)]
        earlier, _, _ = shipped_frame(first)
        later, _, _ = shipped_frame(second)
        differ = sum(1 for a, b in zip(earlier, later) if a != b)
        verdict = "DETECTABLE" if differ else "IDENTICAL PICTURES — a slip here would not show"
        print(f"     {first:>3} vs {second:<3} {differ:>6} of {SCREEN_BYTES} bytes   {verdict}")


# ---- the assertions ----------------------------------------------------------------------------

def m1_checks(record):
    """The M1 claim, as a list of (name, ok, detail). Every one must hold for `m1`; the `novbl`
    control requires that AT LEAST the four machine-driven ones do not."""
    checks = []

    def add(name, ok, detail):
        checks.append((name, bool(ok), detail))

    unclassified = set(RB) - set(BOOT_BITS) - set(TEARDOWN_BITS)
    if unclassified:
        raise SystemExit(f"FAIL: RB bits added in C and never classified here: {sorted(unclassified)}")

    want_attempted = mask(*BOOT_BITS, *TEARDOWN_BITS)
    add(RB_RAN_ROW, record["readback_attempted"] == want_attempted,
        f"attempted {record['readback_attempted']:#06x}, expected exactly {want_attempted:#06x}")
    add(RB_PASSED_ROW, record["readback_failed"] == 0,
        f"failed {record['readback_failed']:#06x}"
        + (" — " + ", ".join(n for n in RB if record["readback_failed"] >> RB[n] & 1)
           if record["readback_failed"] else ""))

    # 1. The reconstruction's own clock tracks the machine's. Both counters are 16-bit in the image
    #    and 32-bit in the shim, so compare the low word; they are equal, not merely close, because
    #    wb_vbl_tick increments its own counter and calls vbl_handler in the same breath.
    add("vbl_handler ran on the machine",
        record["vbl_counter"] == (record["shim_vbl_ticks"] & 0xffff) and record["vbl_counter"] >= SMOKE_VBLS,
        f"image WB_VBL_COUNTER={record['vbl_counter']}, shim ticks={record['shim_vbl_ticks']}, "
        f"asked for {SMOKE_VBLS}")

    # 2. The two REAL hardware reads steered. On a colour machine at 50 Hz the answer is
    #    WB_SND_TICK_DROP_50HZ; the `mono` control asserts the other arm.
    add("tempo_drop_value chose from real hardware",
        record["tick_drop_value"] == TICK_DROP_50HZ,
        f"WB_SND_TICK_DROP_VALUE={record['tick_drop_value']:#04x} "
        f"(50Hz={TICK_DROP_50HZ:#04x}, mono={TICK_DROP_MONO:#04x}, "
        f"never-written sentinel={TICK_DROP_UNWRITTEN:#04x})")

    # 3. The idle countdown expired and the real YM2149 took the write.
    add("floppy idle timer expired", record["floppy_idle_timer"] == 0,
        f"WB_FLOPPY_IDLE_TIMER={record['floppy_idle_timer']}, seeded to {FLOPPY_IDLE_TICKS}")
    add("the real YM2149 deselected the drives",
        record["psg_port_a_after_run"] & ~PSG_PORT_A_KEEP & 0xff == PSG_DRIVES_DESELECTED
        and record["psg_port_a_after_run"] & PSG_PORT_A_KEEP
            == record["psg_port_a_at_entry"] & PSG_PORT_A_KEEP,
        f"port A {record['psg_port_a_at_entry']:#04x} -> {record['psg_port_a_after_run']:#04x} "
        f"(keep mask {PSG_PORT_A_KEEP:#04x}, drives {PSG_DRIVES_DESELECTED})")

    # 4. sched_wait8's uncapped spin ended, on a byte the ACIA interrupt really wrote.
    add("sched_wait8 returned on a real interrupt's byte", record["sched_wait_returned"] == 1,
        f"sched_wait_returned={record['sched_wait_returned']}, "
        f"IKBD bytes filed={record['ikbd_bytes']}, last from the controller="
        f"{record['ikbd_last_byte']:#04x}, image scancode={record['key_last_scancode']:#04x}")

    # 5. The screen base was translated onto the machine, AND THE ADDEND IS PINNED. The first draft
    #    printed `published - image_base` and asserted only that it was positive and aligned, which
    #    a translation that had mangled the address entirely would still satisfy. It is now compared
    #    against WB_SCREEN_FRONT's own longword, read out of the staged image — the same bytes
    #    `publish_screen_base` handed the backend.
    #
    #    THIS IS WHAT KILLS THE BASE-BYTES-SWAPPED MUTANT AT M1, and only in one of its two homes.
    #    `wb_target_shifter_byte` decides which half of the shadow each register updates, and that
    #    code is SHARED with flip_screen; swapping it turns $078000 into $800700 and the compare
    #    fails (measured — see atari/README.md). What M1 still cannot reach is the swap in
    #    flip_screen's own two CALL SITES, because flip_screen does not run: that stays M2.
    want = staged_screen_front()
    got = record["screen_base_published"] - record["image_base"]
    add("the screen base is the translated one",
        got == want
        and record["screen_base_published"] % 256 == 0
        and record["image_base"] % 256 == 0,
        f"image at {record['image_base']:#x}, published {record['screen_base_published']:#x} "
        f"(= image + {got:#x}); WB_SCREEN_FRONT in the staged image is {want:#x}")
    return checks


# The subset of M1 that the `novbl` control must break. Everything here depends on the level-4
# vector reaching the reconstruction; nothing here can be true with that one store suppressed.
MACHINE_DRIVEN = (RB_PASSED_ROW, "vbl_handler ran on the machine",
                  "tempo_drop_value chose from real hardware", "floppy idle timer expired",
                  "the real YM2149 deselected the drives")

# ...EXCEPT ON A MACHINE WHOSE ENTRY STATE ALREADY SATISFIES ONE OF THEM.
#
# EmuTOS leaves YM2149 port A at 0x27 — the drives already deselected — so on that ROM the check
# passes without the reconstruction doing anything, and the control would report "did not break the
# check it exists to break" against a control that was working perfectly. That is a FALSE RED, and it
# is the same class as the vacuous-green above it: the assertion is exact, the machine offers no data
# that reaches the difference.
#
# So membership is decided from the RECORD rather than written down, and the exclusion is PRINTED —
# a check quietly dropped from a control is a check nobody is running.
ENTRY_STATE_VACUOUS = "the real YM2149 deselected the drives"


def machine_driven(record):
    """MACHINE_DRIVEN, minus any check this machine's entry state already satisfies."""
    vacuous = ((record["psg_port_a_at_entry"] & ~PSG_PORT_A_KEEP & 0xff) == PSG_DRIVES_DESELECTED)
    if not vacuous:
        return MACHINE_DRIVEN, None
    return (tuple(n for n in MACHINE_DRIVEN if n != ENTRY_STATE_VACUOUS),
            f"{ENTRY_STATE_VACUOUS!r} is excluded: port A already reads "
            f"{record['psg_port_a_at_entry']:#04x} at entry on this ROM, so the check is satisfied "
            f"by the entry state and cannot be broken by suppressing anything. Run the control on a "
            f"ROM that leaves the drives selected (TOS 1.04 gives 0x25) to exercise it.")


def report(title, checks):
    """Print a row per check. M1's rows are 3-tuples and M2's carry a fourth structural field, so
    this reads the first three and ignores the rest rather than having two printers."""
    print(f"== {title}")
    for row in checks:
        name, ok, detail = row[0], row[1], row[2]
        print(f"   {'ok  ' if ok else 'FAIL'} {name}: {detail}")


def mode_m2(problems, faulted):
    """The frame differential, and its MIS-ANCHOR control.

    `faulted` shifts our frames one anchor along the shipped side's and INVERTS the verdict: a run
    that still reports a match would mean the comparison is not reading the moments it names. It is
    the framediff-fault the sibling project's M4 owes and this one takes at M2."""
    anchors = original.anchor_frames()
    record, why = read_m2()
    stats, stats_why = read_stats()
    for missing in (why, stats_why):
        if missing:
            problems.append(missing)
    if record is None or stats is None:
        report("m2fault" if faulted else "m2", [])
        raise SystemExit("FAIL: " + "; ".join(problems))
    checks = m2_checks(record, stats, anchors, shift=MIS_ANCHOR_SHIFT if faulted else 0)
    report("m2fault (mis-anchor control — the FRAME rows MUST fail)" if faulted else "m2", checks)
    report_neighbour_margins(anchors)
    print(f"   image at {record['image_base']:#x}, last published screen base "
          f"{record['screen_base_published']:#x} (= image + {record['screen_front']:#x}), "
          f"{record['shim_vbl_ticks']} vblanks for {record['frames_run']} frames")

    if not faulted:
        problems += [f"{name}: {detail}" for name, ok, detail, _ in checks if not ok]
        if problems:
            raise SystemExit("FAIL: " + "; ".join(problems))
        print(f"OK: M2 — {record['frames_run']} frames of the reconstruction on a 68000, and at "
              f"{len(anchors)} anchors its screen and its sixteen pens are the shipped binary's")
        return

    # THE CONTROL INVERTS ITS VERDICT OVER THE FRAME ROWS AND ONLY THOSE, and it asserts the rest
    # NORMALLY. An earlier draft ignored every non-frame row, so `m2fault` reported OK for a run in
    # which no frame executed at all: with zero frames the pictures are zeros, every shifted compare
    # "fails", and the control announced success for a build that had done nothing. A control has to
    # know its own run was healthy before its inversion means anything.
    preconditions = [(name, ok, detail) for name, ok, detail, pair in checks if pair is None]
    problems += [f"{name}: {detail}" for name, ok, detail in preconditions if not ok]
    if problems:
        raise SystemExit("FAIL: the control's own run is not sound, so its inverted verdict says "
                         "nothing: " + "; ".join(problems))

    # ...and only over the rows a SHIFT can break. Rows it cannot are EXCLUDED AND PRINTED rather
    # than quietly dropped — M1's `machine_driven` lesson, that a check silently removed from a
    # control is a check nobody is running. This game is motionless between its one-second ticks, so
    # most anchor pairs are the same 32000 bytes and the palette is the same at every one of them; a
    # row over such a pair is not a control that failed, it is a control the data cannot reach.
    reachable = shiftable_pairs(anchors, MIS_ANCHOR_SHIFT)
    breakable = [(name, ok) for name, ok, _, key in checks if key in reachable]
    excluded = [(name, key) for name, ok, _, key in checks
                if key is not None and key not in reachable]
    for name, (surface, ours, theirs) in excluded:
        # NAME THE SURFACE, because for two of these rows the pictures are NOT identical — the
        # bitplanes move across 1->2 and 51->52 while the palette does not, so "the shipped binary
        # draws the two anchors identically" was true of the pairs it was first written for and
        # false of the pens rows over the moving ones.
        print(f"   note {name!r} is excluded: the shipped binary's {surface} are the same at frames "
              f"{ours} and {theirs}, so shifting between them changes nothing this row could see")
    if not breakable:
        raise SystemExit("FAIL: the shift breaks no row at all — every anchor pair is the same "
                         "picture, so this control cannot fail and proves nothing")
    held = [name for name, ok in breakable if ok]
    if held:
        raise SystemExit("FAIL: the mis-anchor control matched anyway at " + ", ".join(held)
                         + " — the differential is not reading the moments it names")
    print(f"OK: all {len(breakable)} rows a one-anchor shift can reach FAIL under it "
          f"({len(excluded)} excluded above)")


def shiftable_pairs(anchors, shift, prefix=""):
    """The (ours, theirs) pairs a `shift`-anchor slip can actually break, from the SHIPPED side.

    Keyed on (surface, ours, theirs) rather than on a formatted row name, and taking the SAME
    `shift` the checks were built with — an earlier draft matched rows by string equality and hardcoded a shift of one
    on this side, so the two could only ever agree by accident.

    Derived from the data rather than written down, for the same reason M1 derives its control's
    membership from the run's recorded entry byte: which rows a control can break is a property of
    the machine's data, and a list would go stale the moment the anchors moved."""
    keys = set()
    for index, frame in enumerate(anchors):
        against = anchors[(index + shift) % len(anchors)]
        mine, _, my_pens = shipped_frame(frame, prefix)
        theirs, _, their_pens = shipped_frame(against, prefix)
        if mine != theirs:
            keys.add((BITPLANES, frame, against))
        if pen_words(my_pens) != pen_words(their_pens):
            keys.add((PENS, frame, against))
    return keys


# ---- the TITLE: the first picture the reconstruction DRAWS ----------------------------------------
#
# WHAT THIS CLAIMS, and it is a different kind of claim from M2's. M2 runs reconstructed code over
# the ORIGINAL's post-boot RAM, because the chain that produces that RAM is unported; every byte the
# frame loop reads was measured off a real machine. The title screen needs none of that: its whole
# chain is five calls, all reconstructed, and this mode starts from the PROGRAM IMAGE — the same
# bytes `smoke.py m1` stages, the shipped file plus gen_image.py's named seeds — asks the machine
# for TITLESCR.RAD across the file-load seam, inflates it and sets the palette. What is compared is
# the 32000 bytes at WB_SCREEN_LOW and the sixteen pens, against the SHIPPED binary's own at $e556.
#
# So this is the first row in this directory where the picture is the reconstruction's product
# rather than its inheritance, and the first time a reconstructed routine asks the machine for a
# file. atari/README.md §13 has the three deviations from the boot that make it possible.
TITLE_FILE = "TITLE.BIN"
TITLE_FORMAT = ">14I"
TITLE_FIELDS = ("magic", "bytes", "image_base", "resource_index", "copylock_arm_flag",
                "load_result", "packed_bytes", "unpacked_bytes", "depack_result", "depack_dest",
                "captured_at", "screen_base_published", "shifter_base", "pens_readback_failed")
TITLE_MAGIC = c_constant("TITLE_MAGIC")  # 'WBA3'

# The boot's own answers, from the headers that define them (test/layout.py), so this file and the
# reconstruction cannot disagree about what "the load worked" or "the depack failed" mean.
LOAD_OK = wb("LOAD_OK")
RAD_BAD_CHECKSUM = wb("RAD_BAD_CHECKSUM")
RESOURCE_LOAD_BUFFER = wb("RESOURCE_LOAD_BUFFER")
SCREEN_LOW = original.WB_SCREEN_LOW
# The Copylock arm flag as this build must leave it. $e51e writes $ffff here before the shipped
# load; the reconstruction does not arm it, so `load_resource_by_index` takes its unarmed arm.
COPYLOCK_UNARMED = 0
NO_PENS_FAILED = 0


def rad_constant(name):
    """One plain-integer `#define RAD_*` out of ../include/rad.h.

    ../test/layout.py scrapes nine headers and every name it takes is `WB_`-prefixed; the depacker's
    FILE FORMAT constants are `RAD_`-prefixed and live in a tenth. Rather than widen that module for
    one caller, this reads the three header offsets the check below needs, by the same rule: a
    missing or non-literal define raises instead of defaulting."""
    found = re.search(r"^#define\s+%s\s+(0[xX][0-9a-fA-F]+|\d+)u?\b" % name,
                      (REC / "include" / "rad.h").read_text(), re.M)
    if not found:
        raise SystemExit(f"{name} is not a plain-integer #define in ../include/rad.h")
    return int(found.group(1), 0)


RAD_HDR_PACKED_OFF = rad_constant("RAD_HDR_PACKED_OFF")
RAD_HDR_UNPACKED_OFF = rad_constant("RAD_HDR_UNPACKED_OFF")
RAD_HDR_LEN = rad_constant("RAD_HDR_LEN")


def read_title(name=TITLE_FILE):
    return read_record(name, TITLE_FIELDS, TITLE_FORMAT, TITLE_MAGIC, "the title build")


def rad_header(index):
    """(packed, unpacked, filesize) of the SHIPPED .RAD file row `index` names, off the host disk.

    The two lengths the .PRG reports are read out of its own load buffer, i.e. out of bytes GEMDOS
    put there; these are the same two fields in the file as it sits in ../bin/disk1. Comparing them
    is what says the seam moved THE FILE and not merely something."""
    shipped = (original.BIN / "disk1" / resource_name(index)).read_bytes()
    return (int.from_bytes(shipped[RAD_HDR_PACKED_OFF:RAD_HDR_PACKED_OFF + 4], "big"),
            int.from_bytes(shipped[RAD_HDR_UNPACKED_OFF:RAD_HDR_UNPACKED_OFF + 4], "big"),
            len(shipped))


def shipped_picture(screen_file, pens_file, mode):
    """(screen, pens) as `original.py <mode>` left them, or a refusal naming the mode to run.

    ONE READER FOR THE TWO ANCHORS. `original.py` collapsed its own two capture modes into
    `capture_boot_picture` because they differ in three values and nothing else; this is the same
    collapse on this shore, so the two sides of one differential cannot come to disagree about how a
    photograph is read back."""
    names = (screen_file, pens_file)
    missing = [name for name in names if not (original.BUILD / name).exists()]
    if missing:
        raise SystemExit(f"{', '.join(missing)} is missing — run "
                         f"`python3 atari/original.py {mode}`")
    return tuple((original.BUILD / name).read_bytes() for name in names)


def picture_rows(theirs, their_pens, what, record_file, captures=None):
    """The two rows a photographed screen comes down to, and the two guards under them.

    `(name, ok, detail, key)` per row, with the SURFACE as the key — `title_checks`' structural key,
    so a control can invert exactly the two rows a different picture can break. `what` names the
    picture in the row labels and `record_file` names the record whose presence makes a missing
    capture a WRITE failure rather than a dead program.

    `captures` is the (screen, pens) pair on OUR drive, defaulting to the pair the title and boot
    builds write. The own-entry build cannot use those two names — it also compiles -DSMOKE_M2 and
    they are already the frame loop's anchor captures — so it names its own, and this stays the one
    reader for every picture in this file."""
    rows = []
    ours_name, our_pens_name = captures or (M2_FRAME_FILE, M2_PENS_FILE)

    def add(name, ok, detail, key=None):
        rows.append((name, bool(ok), detail, key))

    missing = [name for name in (ours_name, our_pens_name) if not (DISK / name).exists()]
    if missing:
        add("the captures were written", False,
            f"{', '.join(missing)} absent although {record_file} was written — the run reached its "
            f"own dump, so this is the capture write failing rather than the program dying")
        return rows
    ours = (DISK / ours_name).read_bytes()
    our_pens = (DISK / our_pens_name).read_bytes()
    if len(ours) != SCREEN_BYTES or len(our_pens) != PALETTE_BYTES:
        add("the capture is the right size", False,
            f"{len(ours)} frame bytes and {len(our_pens)} pen bytes, expected {SCREEN_BYTES} "
            f"and {PALETTE_BYTES}")
        return rows
    wrong = differing_bytes(ours, theirs)
    line_bytes = wb("SCREEN_LINE")
    scanlines = sorted({at // line_bytes for at in wrong})
    add(f"the {what} screen's bitplanes", not wrong,
        f"{len(wrong)} of {SCREEN_BYTES} bytes differ over {len(scanlines)} scanlines"
        + (f" {scanlines[:8]}" if scanlines else ""), BITPLANES)
    mine_pens, shipped_pens = pen_words(our_pens), pen_words(their_pens)
    wrong_pens = [pen for pen in range(PALETTE_PENS) if mine_pens[pen] != shipped_pens[pen]]
    add(f"the {what} screen's pens", not wrong_pens,
        f"pens {wrong_pens} differ" if wrong_pens
        else " ".join("%03x" % pen for pen in mine_pens), PENS)
    return rows


def title_checks(record, stats, want_resource):
    """The title differential, as `(name, ok, detail, key)` rows.

    `key` is `None` for a precondition and the SURFACE for a comparison row, which is what lets the
    control invert exactly the two rows a different picture can break and assert the rest normally —
    `m2_checks`' structural key, with one anchor instead of four so the pair alone is the key."""
    checks = []

    def add(name, ok, detail, key=None):
        checks.append((name, bool(ok), detail, key))

    for name, ok, detail in readback_checks(stats):
        add(name, ok, detail)

    # WHICH BINARY IS RUNNING, asserted before anything it reports is believed. The per-mode `.PRG`s
    # persist across edits to build.sh, so the mode's whole verdict rests on this row: `titlecredits`
    # reporting WB_RESOURCE_TITLESCR would be the control silently running the thing it controls.
    add("this build asked for the resource the mode names",
        record["resource_index"] == want_resource,
        f"resource_index={record['resource_index']:#x} "
        f"({resource_name(record['resource_index'])}), the mode expects "
        f"{want_resource:#x} ({resource_name(want_resource)})")
    # THE HONESTY NOTE, MADE CHECKABLE. $e51e arms the Copylock immediately before the shipped load
    # and this build does not, so the flag must be as the .PRG ships it and the load must have taken
    # its unarmed arm. A run that reported WB_LOAD_COPYLOCK_RAN would be claiming the protection had
    # a part in this picture, which is the one thing this port cannot say.
    add("the Copylock was not armed, and the load says so",
        record["copylock_arm_flag"] == COPYLOCK_UNARMED and record["load_result"] == LOAD_OK,
        f"WB_COPYLOCK_ARM_FLAG={record['copylock_arm_flag']:#06x}, load_resource_by_index returned "
        f"{record['load_result']} (WB_LOAD_OK={LOAD_OK})")

    # THE SHIPPED SIDE IS CHOSEN BY THE MODE, not by the number the binary reported. Which file
    # this run was supposed to load is the mode's own fact and is asserted a row above; taking the
    # reference from the record instead would let a build that loaded the wrong resource compare
    # itself against the wrong resource and agree.
    packed, unpacked, filesize = rad_header(want_resource)
    add("the file the machine served is the file on the disk",
        record["packed_bytes"] == packed and record["unpacked_bytes"] == unpacked
        and packed + RAD_HDR_LEN == filesize,
        f"the buffer at {RESOURCE_LOAD_BUFFER:#x} holds a header saying "
        f"{record['packed_bytes']}/{record['unpacked_bytes']} packed/unpacked; the shipped "
        f"{resource_name(want_resource)} is {filesize} bytes and says {packed}/{unpacked}")
    add("the depack ran to a clean checksum", record["depack_result"] != RAD_BAD_CHECKSUM,
        f"rad_depack returned {record['depack_result']:#x} "
        f"(WB_RAD_BAD_CHECKSUM={RAD_BAD_CHECKSUM:#x})")
    # THE GEOMETRY, PINNED RATHER THAN DESCRIBED. WB_TITLE_DEPACK_DEST is the original's own operand
    # ($e530's `lea $6ff80.l,a1`) and what makes it work is that the depacked file is a prefix plus
    # exactly one screen — so the inflate ENDS on the visible buffer's last byte. Asserted from the
    # file's own header, so a resource of a different shape reds here instead of drawing off-screen.
    add("the picture is inflated onto the visible buffer",
        record["depack_dest"] + record["unpacked_bytes"] == SCREEN_LOW + SCREEN_BYTES
        and record["captured_at"] == SCREEN_LOW,
        f"depacked {record['unpacked_bytes']} bytes to {record['depack_dest']:#x}, i.e. "
        f"[{record['depack_dest']:#x},{record['depack_dest'] + record['unpacked_bytes']:#x}); "
        f"WB_SCREEN_LOW is [{SCREEN_LOW:#x},{SCREEN_LOW + SCREEN_BYTES:#x}) and the capture was "
        f"taken at {record['captured_at']:#x}")
    want_base = record["image_base"] + SCREEN_LOW
    add("the shifter displays the buffer the depack filled",
        record["shifter_base"] == want_base and record["screen_base_published"] == want_base,
        f"$ffff8201/8203 read back {record['shifter_base']:#x}, the backend wrote "
        f"{record['screen_base_published']:#x}, the image is at {record['image_base']:#x} so "
        f"WB_SCREEN_LOW is at {want_base:#x}")
    add("set_palette reached the chip", record["pens_readback_failed"] == NO_PENS_FAILED,
        f"pens that did not read back as the depacked prefix's own words: "
        f"{record['pens_readback_failed']:#06x}")

    theirs, their_pens = shipped_picture(original.TITLE_SCREEN_FILE, original.TITLE_PENS_FILE,
                                        TITLE_MODE)
    return checks + picture_rows(theirs, their_pens, "title", TITLE_FILE)


TITLE_MODE, TITLE_CONTROL_MODE = "title", "titlecredits"
# WHICH RESOURCE EACH MODE'S BINARY MUST HAVE ASKED FOR. The control's whole content is that it is a
# DIFFERENT picture through the same code, so the pair is asserted to be a pair — a control compiled
# with the same index as the mode would pass its inversion only by being broken some other way.
TITLE_RESOURCE_FOR_MODE = {TITLE_MODE: wb("RESOURCE_TITLESCR"),
                           TITLE_CONTROL_MODE: wb("RESOURCE_CREDITS")}
assert TITLE_RESOURCE_FOR_MODE[TITLE_MODE] != TITLE_RESOURCE_FOR_MODE[TITLE_CONTROL_MODE], (
    "the title control depacks the same resource as the mode it controls, so it cannot fail")
# The mode and its control boot DIFFERENT binaries — the control's difference IS a compiled-in
# resource index — unlike `m2`/`m2fault`, whose control is a shift applied on this side.
TITLE_BUILDS = {mode: f"WB-{mode}.PRG" for mode in TITLE_RESOURCE_FOR_MODE}
# ...and which .PRG names `stage_drive` must put disk 1's resources beside, as a set, for the same
# reason FRAME_BUILDS is one: the test there is on the BINARY, not on the mode that booted it.
TITLE_PRGS = frozenset(TITLE_BUILDS.values())


def mode_title(problems, mode):
    """The title differential, and its DIFFERENT-PICTURE control."""
    control = mode == TITLE_CONTROL_MODE
    record, why = read_title()
    stats, stats_why = read_stats()
    for missing in (why, stats_why):
        if missing:
            problems.append(missing)
    if record is None or stats is None:
        report(mode, [])
        raise SystemExit("FAIL: " + "; ".join(problems))

    checks = title_checks(record, stats, TITLE_RESOURCE_FOR_MODE[mode])
    report(f"{mode} (different-picture control — the PICTURE rows MUST fail)" if control else mode,
           checks)
    print(f"   image at {record['image_base']:#x}, {resource_name(record['resource_index'])} "
          f"({record['packed_bytes']} packed) inflated to {record['unpacked_bytes']} bytes at "
          f"{record['depack_dest']:#x}, shifter at {record['shifter_base']:#x}")

    if not control:
        problems += [f"{name}: {detail}" for name, ok, detail, _ in checks if not ok]
        if problems:
            raise SystemExit("FAIL: " + "; ".join(problems))
        print("OK: the title screen — the reconstruction loaded TITLESCR.RAD across the file seam, "
              "depacked it and set the palette on a 68000, and its 32000 bytes and sixteen pens "
              "are the shipped binary's")
        return

    # THE CONTROL ASSERTS ITS PRECONDITIONS NORMALLY and inverts only the picture rows — `m2fault`'s
    # rule, and for its reason: a control whose own run was unsound proves nothing, and "the picture
    # differs" is satisfied by a run that drew no picture at all.
    preconditions = [(name, ok, detail) for name, ok, detail, key in checks if key is None]
    problems += [f"{name}: {detail}" for name, ok, detail in preconditions if not ok]
    if problems:
        raise SystemExit("FAIL: the control's own run is not sound, so its inverted verdict says "
                         "nothing: " + "; ".join(problems))
    broken = [name for name, ok, _, key in checks if key is not None and not ok]
    held = [name for name, ok, _, key in checks if key is not None and ok]
    if not broken:
        raise SystemExit("FAIL: the other picture broke NO row — this control cannot fail and "
                         "proves nothing, so the comparison above is not reading what it names")
    for name in held:
        # NAMED, NOT SWALLOWED. A row the other picture happens not to move is a row this control
        # does not cover, and saying which is the difference between an exclusion and an omission.
        print(f"   note {name!r} held: the two shipped pictures do not differ on this surface, so "
              f"swapping one for the other changes nothing this row could see")
    print(f"OK: {len(broken)} of {len(broken) + len(held)} picture rows FAIL when the same three "
          f"calls are aimed at {resource_name(record['resource_index'])} instead "
          f"({len(held)} named above)")


# ---- THE BOOT: the whole chain on the machine, and the post-boot image RECOMPUTED -----------------
#
# WHAT THIS CLAIMS, and it is the strongest claim in this file. Every picture and every frame above
# it rests, somewhere, on `atari/original.py dump` — the ORIGINAL's own post-boot RAM, measured off a
# real emulated machine at `$f8b4` and staged by `gen_image.py`, because nothing here ran the chain
# that produces it. This mode runs the chain: ../src/boot.c's three composed slices, in the boot's
# own order, with the boot's own fire gates between them, over M1's image — the shipped program plus
# gen_image.py's named seeds and not one byte of measured RAM.
#
# TWO SURFACES COME OFF IT. The CREDITS picture, compared against the shipped binary's own at `$e5aa`
# exactly as the title picture is compared at `$e556`; and the whole game span `[0x3f8,0x80000)`,
# written out at the instant `boot_load_stage` returns and differenced against the dump BAND BY BAND,
# with every band named and every unnamed byte required to be equal.
#
# THE SECOND IS WHAT DISSOLVES gen_image.py's FABRICATION CLAUSE. That file says the M2 image "is the
# boot's result handed over rather than its result recomputed". For every byte outside the bands
# below, this mode measures that the two are the same — so the sentence stops being a promise about
# code that exists and becomes a reading.
BOOT_FILE = "BOOT.BIN"
BOOT_IMAGE_FILE = "BOOT.IMG"
# The record, named in the same order wonderboy_main.c declares it. THE SIZE IS CHECKED, so a field
# added in C and not here is a loud parse error rather than a silently misread record — and it is a
# FOURTH record with a fourth magic for the reason there are three already: one record that grew per
# build mode would make every other mode's version check fire.
BOOT_FIELDS = ("magic", "bytes", "image_base",
               "title_result", "credits_result", "stage_result",
               "fire_press_pc", "fire_release_pc", "fire_gates_crossed", "fire_waits_timed_out",
               "fire_wait_timed_out_pc",
               "title_packed", "title_unpacked", "credits_packed", "credits_unpacked",
               "copylock_arm_flag", "pens_readback_failed", "captured_at",
               "screen_base_published", "shifter_base",
               "stage_map_ptr", "stage_start_ptr", "resource_signature", "stage_number",
               "level_seq_index", "stage_second_load_flag", "stage_side_flag",
               "life_restart_entry_c26",
               "span_bytes", "vbl_ticks_at_span", "vbl_ticks_at_exit")
BOOT_FORMAT = ">%dI" % len(BOOT_FIELDS)


def assert_the_record_matches_the_c(struct, fields):
    """Refuse a field list that is not the C struct's, IN ORDER.

    THE SIZE CHECK CATCHES AN ADDED FIELD AND NOT A MOVED ONE, which is the hole this closes. Every
    field of these records is a `uint32_t`, so swapping two leaves the blob the same length with the
    same magic: `read_*` returns cleanly and every row below compares its expectation against the
    wrong number — some passing spuriously, others reddening for what reads like a reconstruction
    defect. `readback_bits` sets the precedent of reading the C rather than restating it.

    IT COVERS TWO OF THE FIVE RECORDS TODAY — `boot_stats` and, since batch 44 phase E,
    `own_stats`. The other three (`STATS.BIN`, `M2.BIN`, `TITLE.BIN`) have the same hole and are not
    fixed here — an out-of-scope change to three working readers — but the helper is written to take
    any of them. QUEUED in ../STATUS.md.

    AND IT SCRAPES THE WORKING TREE, WHICH IS WHY `refuse_a_stale_build` EXISTS. The declaration read
    here and the bytes graded below come from two different artefacts, so on their own they can be
    from two different edits — see that function."""
    source = (HERE / "wonderboy_main.c").read_text()
    body = re.search(r"^struct %s \{(.*?)^\};" % struct, source, re.S | re.M)
    if not body:
        raise SystemExit(f"struct {struct} is no longer declared in wonderboy_main.c — the record "
                         f"this file parses has no definition to be pinned against")
    declared = tuple(re.findall(r"^\s+uint32_t\s+(\w+);", body.group(1), re.M))
    if declared != tuple(fields):
        raise SystemExit(f"struct {struct} declares {declared} and this file names {tuple(fields)} "
                         f"— the two disagree about which longword is which, so every row below "
                         f"would compare its expectation against another field's value")


assert_the_record_matches_the_c("boot_stats", BOOT_FIELDS)


def refuse_a_stale_build(prg, build_mode, struct="boot_stats"):
    """Refuse a `.PRG` older than the C whose struct declaration the record parser was pinned to.

    THE ASSERTION ABOVE CLOSES A HOLE AND THIS CLOSES THE DOOR IT ARRIVES THROUGH. The scrape reads
    the WORKING TREE and the run grades a BINARY, so without this the two can be from different
    edits: swap two `uint32_t` fields in `struct boot_stats`, run the mode without rebuilding, and
    the scrape compares the new declaration against the new field list, agrees, and every row below
    reads the OLD binary's byte order under the new names — the exact swapped-pair failure the
    assertion exists to catch, wearing a stale build's clothes. It is `capture_pc`'s documented
    hazard ("the per-mode `.PRG`s persist while this file is edited") applied to the record's shape
    rather than to one field's value.

    MTIME AND NOT A DIGEST, because what has to be refused is an ORDERING and the build is what
    establishes it: `build.sh` compiles the C into the `.PRG`, so a `.PRG` at least as new as the C
    cannot predate the declaration that was scraped."""
    if prg.stat().st_mtime_ns >= (HERE / "wonderboy_main.c").stat().st_mtime_ns:
        return
    raise SystemExit(f"FAIL: {prg.name} is older than wonderboy_main.c, whose `struct {struct}` "
                     f"declaration this file scraped to pin the record's field order — so the rows "
                     f"below would grade the old binary's longwords under the new names. Rebuild "
                     f"with `bash atari/build.sh {build_mode}`.")


BOOT_MAGIC = c_constant("BOOT_MAGIC")            # 'WBA4'
BOOT_SLICE_NOT_RUN = c_constant("BOOT_SLICE_NOT_RUN")

BOOT_MODE, BOOT_FAULT_MODE = "boot", "bootfault"
BOOT_BUILDS = {BOOT_MODE: "WB-boot.PRG", BOOT_FAULT_MODE: "WB-bootfault.PRG"}
BOOT_PRGS = frozenset(BOOT_BUILDS.values())
# THE DRIVEN PASS'S BOUND, AND IT IS DERIVED RATHER THAN ROUND. The chain is five disk loads, four
# depacks and two installers on an 8 MHz 68000, on top of TOS's own boot. Measured: the driven run
# reaches its span at ~525 shim vblanks and exits at ~537, so the PROGRAM is a few hundred vblanks
# and `RUN_VBLS`' own budget (TOS's boot, thousands, plus a tail) is the rest.
#
# WHAT THE MARGIN OVER `RUN_VBLS` IS FOR is the case this pass exists to be able to report: all four
# debugger pokes missing. Each unanswered half then spins out `SPINS_LONG` (~6 s, ~300 vblanks)
# before the shim gives up, so a wholly undriven driven-pass costs up to ~1,200 vblanks MORE than a
# working one — and it has to reach its own record anyway, because `fire_wait_timed_out_pc` naming
# the half that was missed is the whole diagnosis. 6,000 + ~540 + ~1,200 is under 8,000 and this is
# half as much again. It is its OWN number and not the play build's, which happens to be the same
# and means something else (how long a person's build is watched flipping buffers).
#
# THE UNDRIVEN PASS DOES NOT USE IT — it runs on `RUN_VBLS`; `measure_the_undriven_boot_chain` says
# why.
BOOT_RUN_VBLS = 12000
# THE ROW GROUPS THIS MODE'S CONTROL CAN INVERT. `CREDITS_SLICE_ROW` is every row that reads
# something the suppressed slice produced OTHER than the picture; the two picture surfaces keep
# `title_checks`' own keys (BITPLANES, PENS) so the two modes' reports read alike; `SPAN_ROW` is the
# recomputed image. Structural keys rather than formatted names, for `m2_checks`' reason.
CREDITS_SLICE_ROW = "credits-slice"
STAGE_PIN_ROW = "stage-pin"
SPAN_ROW = "span"

# WHAT THE BOOT'S SLICES MUST REPORT, from the headers that define them. Two of the five loads are
# ARMED by the chain — $e51e before TITLESCR.RAD and $e6dc before SPRITES.CRU — so the slices holding
# them must report WB_LOAD_COPYLOCK_RAN, which is the port's way of saying the protection blob would
# have executed. Nothing on this machine runs it: it is neither ported nor stubbed.
LOAD_COPYLOCK_RAN = wb("LOAD_COPYLOCK_RAN")
# ...and the code a slice reports when the seam refused its load — the own-entry ladder's stop.
LOAD_DISK_ERROR = wb("LOAD_DISK_ERROR")
CREDITS_PROMPT_PEN = wb("CREDITS_PROMPT_PEN")
CREDITS_PROMPT_COLOUR = wb("CREDITS_PROMPT_COLOUR")
# `load_resource_by_index` clears the flag on the armed arm, so a chain that ran to the end leaves it
# down. Spelt as the same constant the title mode uses, because it is the same word.
COPYLOCK_CLEAR = COPYLOCK_UNARMED
FIRE_DOWN = original.FIRE_DOWN
FIRE_UP = original.FIRE_UP
# How many fire gates the chain has. Each has two halves — a press and a release — so this is also
# what turns the two waits' PCs into the four debugger stops `boot_fire_script` sets, and what the
# record's gate count is compared against. One spelling rather than a 2 and a 4 in four places.
BOOT_FIRE_GATES = 2
# What each fire poke echoes into the log. Not parsed — the record's own `fire_gates_crossed` is what
# asserts the pokes landed — but a debugger script that says which stop fired is the difference
# between reading a Hatari log and guessing at one.
BOOT_FIRE_BEACON = "BOOT_FIRE"
# The `original.py` mode that photographs this mode's shipped side, named once so the refusal message
# a missing artefact produces is the command a reader can paste.
BOOT_CREDITS_ANCHOR_MODE = "credits"
# The first row of WB_LEVEL_SEQ_TABLE — the one `game_restart_reset` leaves WB_LEVEL_SEQ_INDEX on,
# and therefore the one `stage_sequence_advance` consumes. After that one step the index must have
# advanced by exactly one row, which is a pin on BOTH sides (the shipped boot took the same step).
FIRST_SEQ_ROW = 0
SEQ_ROWS_STEPPED = 1


def refuse_unless_the_control_holds(control, what_depends_on_it):
    """Stop the mode unless every row of an UNDRIVEN pass held.

    THREE MODES OPEN THE SAME WAY and this is the shape they share: measure the machine with nothing
    injected, assert that nothing happened, and only then pay for the driven runs whose pokes are
    aimed with the addresses that pass reported. A control that failed makes every number below it
    unreadable — the addresses may be stale, the arm may have fired on its own — so the mode stops
    HERE rather than printing a wall of rows that cannot mean anything.

    `what_depends_on_it` names what is being refused, because "the negative control did not hold" on
    its own does not say which run is now impossible.
    """
    broken = [f"{name}: {detail}" for name, ok, detail in control if not ok]
    if broken:
        raise SystemExit(f"FAIL: the negative control did not hold, so {what_depends_on_it} could "
                         f"not mean anything: " + "; ".join(broken))


def read_boot(name=BOOT_FILE):
    return read_record(name, BOOT_FIELDS, BOOT_FORMAT, BOOT_MAGIC, "the boot build")


def sequence_row(row):
    """WB_LEVEL_SEQ_TABLE's row `row`, out of the staged image the .PRG actually loaded.

    ONE LOOKUP FOR THE TWO SIDES OF ONE CLAIM. The STAGING side reads it to know which overlay file
    to put on the drive, and the CHECKING side reads it to know which bytes the run must have
    published; two copies of the expression would let the harness stage the resource for one row and
    grade the run against another. The own-entry mode reads the SECOND row as well, because an
    ending that reloads is what makes the sequence step."""
    return staged_block(wb("LEVEL_SEQ_TABLE") + row * wb("LEVEL_SEQ_RECORD_BYTES"),
                        wb("LEVEL_SEQ_RECORD_BYTES"), f"WB_LEVEL_SEQ_TABLE row {row}")


def boot_resource_indices():
    """The five rows of WB_RESOURCE_FILE_TABLE this chain asks the machine for, DERIVED.

    Four of them are constants of the chain (TITLESCR, CREDITS, TILEDATA, SPRITES.CRU); the fifth
    is the OVERLAY, which `stage_sequence_resource` computes as the sequence row's own ordinal plus
    WB_RESOURCE_FIRST_OVERLAY. Reading that row out of the staged image rather than writing `2` here
    is what keeps this list and the reconstruction's own arithmetic from drifting — and the run pins
    it either way, because a file staged under the wrong name makes the load return
    WB_LOAD_DISK_ERROR and the mode's first row red.

    THE FIRST TWO ARE DISK1_RESOURCES, not a second listing of them: this chain begins with the
    title build's own slice, so its set is that set PLUS the data disk's three."""
    return DISK1_RESOURCES + (overlay_resource(FIRST_SEQ_ROW),
                              wb("RESOURCE_TILEDATA"), wb("RESOURCE_SPRITES_CRU"))


def overlay_resource(row):
    """WB_RESOURCE_FILE_TABLE's index for the overlay sequence row `row` names — the reconstruction's
    own `stage_sequence_resource` arithmetic (the row's ordinal plus WB_RESOURCE_FIRST_OVERLAY), read
    out of the staged image rather than written down. A BYTE add, as the original's `addq.b #2` is."""
    return (sequence_row(row)[wb("LEVEL_SEQ_OVERLAY")] + wb("RESOURCE_FIRST_OVERLAY")) & 0xff


# WHICH SHIPPED TREE EACH RESOURCE COMES OFF, and the corpus gotcha that goes with it. `bin/disk2/`
# is the AUTHENTIC dump of the pressed data disk and four of its overlays are damaged;
# `bin/disk2_repaired/` is a HYBRID and is evidence about nothing. This mode stages from the
# authentic tree — and PROVES the choice cannot matter by requiring every file it stages to be
# byte-identical in both, which is measured on every run rather than asserted here in prose.
DISK1_TREE = "disk1"
BOOT_RESOURCE_TREE = "disk2"
BOOT_RESOURCE_HYBRID_TREE = "disk2_repaired"
# THE SEARCH IS KEYED BY CALLER AND NOT BY THE FILE, and the asymmetry is the point. The TITLE
# modes' claim is about the 1989 DISK 1 picture (M7), so their two resources may come off disk 1 and
# nowhere else: searching both trees for them would let a same-named file on the data disk stand in
# silently and the mode would still report green. The boot chain really does span both volumes —
# that is its declared one-volume deviation (README.md §14) — so its five search both.
DISK1_TREES = (DISK1_TREE,)
BOOT_RESOURCE_TREES = (DISK1_TREE, BOOT_RESOURCE_TREE)


def shipped_resource(name, trees):
    """The shipped file `name` and which of `trees` it came off, searched in that order."""
    for tree in trees:
        candidate = original.BIN / tree / name
        if candidate.exists():
            return candidate, tree
    raise SystemExit(f"{name} is on none of {', '.join(trees)} — WB_RESOURCE_FILE_TABLE names it "
                     f"and the build being staged asks for it by that name")


# WHICH NOTES HAVE ALREADY BEEN SAID. A mode that boots six times re-stages six times (see
# `stage_drive`) and every staging re-runs the corpus check, which is the point — but printing its
# result six times says nothing the first line did not. This gates the NOTE and never the check, so
# "measured on every run" below stays literally true, and it is deliberately not a cache of anything
# the drive's contents depend on.
_notes_said = set()


def note_once(text):
    if text not in _notes_said:
        _notes_said.add(text)
        print(text)


def refuse_a_hybrid_resource(staged):
    """Refuse to stage a resource whose two shipped trees disagree, and say which agree.

    THE CORPUS GOTCHA, AS A CHECK. `bin/disk2/` is the AUTHENTIC dump of the pressed data disk and
    four of its overlays are damaged; `bin/disk2_repaired/` is a HYBRID and is evidence about
    nothing. This mode stages from the authentic tree, and the choice is PROVEN not to matter by
    requiring every file it stages that also exists in the hybrid tree to be byte-identical there —
    measured on every run rather than asserted in prose.

    IT RUNS BEFORE ANY FILE IS WRITTEN, which is `original.py`'s `mode_dump` rule ("every check
    before every write"): a refusal from inside the copy loop would leave the drive holding some of
    the five resources beside a `.PRG` and an image that had already been staged."""
    compared = []
    for name, shipped, tree in staged:
        hybrid = original.BIN / BOOT_RESOURCE_HYBRID_TREE / name
        if not hybrid.exists():
            continue
        if hybrid.read_bytes() != shipped.read_bytes():
            raise SystemExit(
                f"FAIL: {name} differs between {tree}/ and {BOOT_RESOURCE_HYBRID_TREE}/, so this "
                f"run's evidence depends on which tree it was staged from. The authentic dump is "
                f"{tree}/ and the repaired tree is a hybrid; a boot resource that is damaged on the "
                f"pressed disk cannot be substituted silently.")
        compared.append(name)
    if compared:
        note_once(f"   note the {len(compared)} staged resources that "
                  f"{BOOT_RESOURCE_HYBRID_TREE}/ also carries are byte-identical in it "
                  f"({', '.join(compared)}), so the repaired tree's four damaged overlays are not "
                  f"in this evidence")


def stage_resources(indices, trees):
    """Copy the shipped resources `indices` name onto the emulated drive, under the table's names.

    `trees` is the caller's own search order — see `shipped_resource`, where the asymmetry is
    argued."""
    staged = [(resource_name(index),) + shipped_resource(resource_name(index), trees)
              for index in indices]
    refuse_a_hybrid_resource(staged)
    # ...AND THE NEXT MODE MUST BE ABLE TO SWEEP THEM OFF. `stage_drive` cannot ask `resource_name`
    # which files to delete — the image the names come out of is not staged yet at that point — so it
    # keys on RESOURCE_GLOBS, and a resource staged under an extension that tuple does not cover
    # would be left behind for a later build to load BY NAME. That is the failure the sweep exists to
    # prevent and it would pass rather than red, so it is refused here, where the name is known.
    uncovered = sorted({name for name, _, _ in staged
                        if not any(fnmatch.fnmatch(name, pattern) for pattern in RESOURCE_GLOBS)})
    if uncovered:
        raise SystemExit(f"FAIL: {', '.join(uncovered)} would be staged under an extension "
                         f"RESOURCE_GLOBS {RESOURCE_GLOBS} does not sweep, so the NEXT mode would "
                         f"boot with this run's resource still on the drive")
    for name, shipped, _ in staged:
        (DISK / name).write_bytes(shipped.read_bytes())


# ---- the span diff, band by band ------------------------------------------------------------------
#
# THE BANDS ARE NAMED AND JUSTIFIED, and everything outside them must be BYTE-EQUAL. That is the
# whole discipline of gen_image.py's PROVENANCE table applied one level up: there the dump is checked
# against the shipped FILE, here the recomputed span is checked against the DUMP.
#
# FOUR OF THE TEN BANDS ARE NOT THIS MODE'S AT ALL — they are `original.py variance`'s, the bands that
# differ between two boots of the SHIPPED BINARY ITSELF at the same anchor. A difference the original
# cannot reproduce against itself is not one this reconstruction can be asked to reproduce, so they
# are imported rather than restated (CLAUDE.md §5), and a band added there arrives here.
#
# THE REST ARE THIS MODE'S OWN, and each says what makes it differ:
# THE ONE ADDRESS THIS TABLE NEEDS THAT ../include/wonderboy.h DOES NOT DEFINE. Everything else below
# comes through `wb()`, because the header is the port's source of truth for an address and a second
# spelling is one that can stop naming the same bytes (CLAUDE.md §5).
PROGRAM_BODY_AT = 0x400         # where `startup_relocate_and_run` copies the body to, and therefore
                                # the first byte the two images can be expected to agree on

# A BAND WHOSE WHOLE WIDTH MAY TURN OVER, told apart from one held to a measured reading. The four
# imported bands carry `original.py variance`'s own ceilings, which bite: the sound module's is 256
# of 13,604 bytes and the stack's 512 of 4,096, so growing into the slack is as loud as a byte
# outside every band. THE SIX BELOW CANNOT BE HELD THAT WAY AND SAY SO instead of carrying a
# ceiling equal to their own width, which would read as a check and be a tautology: each is a small
# object owned entirely by something this build does not run — a driver's state block, a parked
# stack pointer, the protection's register save, its decrypt cursor, the boot entry's TOS stack
# word, the loader's prelude — so any byte of it may legitimately differ and the BOUND is the band's
# own extent.
WHOLE_BAND = None

BOOT_SPAN_BANDS = tuple((name, start, end, ceiling,
                         "irreproducible between two boots of the shipped binary itself "
                         "(original.py variance), and held to that mode's own ceiling")
                        for name, start, end, ceiling in original.VARIANCE_BANDS) + (
    # WB_DISK_BAND_HI is where `actor_aim_velocity` begins, i.e. the first byte after the driver's
    # state block; the block starts at WB_FLOPPY_PREAMBLE_FLAG, the first of the `var`s ../names.txt
    # gives it. TWO REASONS, NOT ONE, and the first draft's single reason was measurably false for a
    # word inside the band. Most of the block is never written here: batch 44 phase B cut the chain
    # at `disk_load_file` ($5e7c) and everything below that is a WD1772 state machine this build does
    # not run, where the original's boot programmed a real controller five times. But
    # WB_FLOPPY_IDLE_TIMER ($64f2) lies INSIDE it and IS written on this side — gen_image.py seeds it
    # and `vbl_handler`, the reconstruction's own, counts it down; it is the very word
    # RB_PSG_PORT_A_DESELECTED waits for. So the two sides' readings of that word are two different
    # clocks, which is a difference this band has to hold as much as the unwritten bytes are.
    ("the FDC driver's state block", wb("FLOPPY_PREAMBLE_FLAG"), wb("DISK_BAND_HI"), WHOLE_BAND,
     "the driver below the seam does not run here, so the substitution never writes most of it — and "
     "WB_FLOPPY_IDLE_TIMER inside it is OUR vbl_handler's own countdown off gen_image.py's seed"),
    # ...AND ONE LONGWORD OF THE DEPACKER'S, which is not the driver's at all. ../names.txt cmt
    # 0x5e3a: "rad_depack parks the entry a7 here and restores it on the success path only". A C
    # composition has no such register, which is ../STATUS.md batch 44 phase C's OWN declared
    # deviation (§3.1) — off target the differential hands the candidate the value; here nothing
    # writes it and the shipped side's four bytes are its real stack pointer.
    ("rad_depack's parked a7", wb("RAD_SAVED_SP"), wb("RAD_SAVED_SP") + wb("RAD_SAVED_SP_LEN"),
     WHOLE_BAND,
     "../names.txt cmt 0x5e3a — the depacker parks its caller's a7 there and this port has no such "
     "register (../STATUS.md batch 44 phase C §3.1)"),
    # THE COPYLOCK'S SECOND SCRATCH, and `gen_image.py`'s PROVENANCE table names only the first.
    # The shipped file carries zeros in both of the objects below and this build leaves them zero,
    # because it ARMS the protection (the original does) and never RUNS it — the blob is neither
    # ported nor stubbed. `original.py variance` cannot see either band at all: two boots of the
    # original write the same bytes there, so they are reproducible between them and a real
    # difference against a run that never executed the blob.
    #
    # TWO EXACT BANDS AND NOT ONE HULL OVER BOTH, which was the first draft. `[REG_SAVE, CURSOR+8)`
    # is 114 bytes where ../names.txt names 96 and 8; the ten between them ($ed34..$ed3e) are named
    # by nothing, and a WHOLE_BAND hull swallowed them silently — an unnamed byte absorbed by a band
    # that does not claim it is exactly what BOOT_SPAN_RESIDUE_CEILING exists to refuse. Each object
    # now carries its own header-pinned length, and those ten bytes are RESIDUE: measured equal, and
    # they red if they stop being.
    ("the copylock's register save", wb("COPYLOCK_REG_SAVE"),
     wb("COPYLOCK_REG_SAVE") + wb("COPYLOCK_REG_SAVE_LEN"), WHOLE_BAND,
     "where the blob's `movem.l d0-a7,(a6)` and its vector save land; armed and never run here, so "
     "it stays the shipped file's zeros (../names.txt cmt 0xecd4)"),
    ("the copylock's decrypt cursor", wb("COPYLOCK_DECRYPT_CURSOR"),
     wb("COPYLOCK_DECRYPT_CURSOR") + wb("COPYLOCK_DECRYPT_CURSOR_LEN"), WHOLE_BAND,
     "the trace decryptor's two longwords — the address currently plaintext and its ciphertext; "
     "nothing here primes them (../names.txt cmt 0xed3e)"),
    # ONE LONGWORD OF THE BOOT'S OWN PROLOGUE. ../names.txt cmt 0xf8b8: `sys_save_tos_stack` at
    # $e484 stashes the TOS-supplied a7 there, which is the game's only recorded route back to TOS.
    # $e484 is in the boot's entry, ABOVE the three slices this build calls, so nothing here writes
    # it — and this shim's own route back to TOS is `Pterm`, not that longword.
    ("the boot's parked TOS stack pointer", wb("TOS_STACK_SAVE"),
     wb("TOS_STACK_SAVE") + wb("TOS_STACK_SAVE_LEN"), WHOLE_BAND,
     "../names.txt cmt 0xf8b8 — stashed by $e484, which is in the boot's entry above the three "
     "slices this build calls"),
    # AND THE BYTES BELOW THE PROGRAM BODY, which are a property of the two IMAGES rather than of
    # either boot: `project.toml`'s load base is $3f8 and the body is at $400, so the staged image
    # carries the loaded file's `jmp $217d8.l` prelude there, while the ORIGINAL's RAM at that
    # absolute address never held it — `startup_relocate_and_run` COPIED the body to $400 from
    # wherever GEMDOS put the file. Present before either side executed an instruction.
    ("the staged image's pre-body bytes", original.WB_STAGED_AT, PROGRAM_BODY_AT, WHOLE_BAND,
     "the staged image carries the loaded file's prelude below the body at $400; the original's RAM "
     "at that absolute address never did"),
)

# EVERYTHING THE NAMED BANDS DO NOT CLAIM, as one figure with a ceiling — gen_image.py's own rule
# and its reason: a band is a weak guard on its own (the sound module's is 13 KB wide to certify a
# couple of dozen bytes), so the residue is computed after the bands rather than as a last row of
# them, where reordering the table would silently change what it measures.
#
# THE CEILING IS ZERO, and that is the whole claim. An unnamed byte is this mode's finding, not its
# tolerance: what it exists to say is that outside the bands above, the span the reconstruction
# COMPUTED is the span `original.py dump` MEASURED, byte for byte.
BOOT_SPAN_RESIDUE_CEILING = 0
# How many residue clusters to print. Enough to name a band from, short enough to read.
BOOT_RESIDUE_CLUSTERS_SHOWN = 12

# `fat_dir_buffer` (WB_FAT_DIR_BUFFER) is a POINTER in the driver's state block; ../names.txt cmt
# 0x64f4 says the boot sector, the FAT and the root directory are read through it and the cluster
# extent list is built at +5120. The extent below is therefore derived from the image, not written
# here.
FAT_EXTENT_LIST_OFF = 5120
FAT_EXTENT_LIST_BYTES = 512


def fat_buffer_extent(at, whose):
    """(start, end) of the driver's sector staging buffer, from one side's `fat_dir_buffer`."""
    end = at + FAT_EXTENT_LIST_OFF + FAT_EXTENT_LIST_BYTES
    # THE POINTER IS DERIVED AND SO IS CHECKED. The read is bounded, the region it NAMES is not —
    # and the band above says this build never writes the driver's state block, so a pointer that
    # read 0 is entirely plausible. The note would then print a reassuring "0 bytes differ" over
    # [0,0x1600), indistinguishable from the real reading, and the argument for not making this a
    # band would quietly stop holding.
    if not original.WB_STAGED_AT <= at < end <= original.GAME_SPAN_END:
        raise SystemExit(f"FAIL: {whose} fat_dir_buffer ({wb('FAT_DIR_BUFFER'):#x}) points at "
                         f"{at:#x}, whose extent [{at:#x},{end:#x}) is not inside the game span "
                         f"[{original.WB_STAGED_AT:#x},{original.GAME_SPAN_END:#x}) — the note "
                         f"below would be reading somewhere else entirely")
    return at, end


def fat_buffer_extents(measured, base):
    """The sector staging buffer as EACH SIDE's own `fat_dir_buffer` names it, as (whose, lo, hi).

    NOT A BAND, AND THE MEASUREMENT IS WHY. ../names.txt cmt 0x64f4 says the boot sector, the FAT
    and the root directory are read through this pointer and the cluster extent list is built at
    +FAT_EXTENT_LIST_OFF — all of it the driver's work, none of which happens here. It would be an
    exclusion but for where the pointer lands: inside WB_BG_BUFFER_BASE's span, which
    `stage_load_window` rebuilds at the end of the stage slice on BOTH sides. So the region is
    overwritten before either run reaches the anchor, its reading is 0, and an exclusion that
    claims nothing is one nobody is running. It is reported instead, so a run in which it stopped
    being 0 says so twice — here and as residue.

    BOTH POINTERS ARE READ, because the note argues about BOTH SIDES and the pointer lives INSIDE
    the FDC band this table declares free to differ. Reading it from our image alone and then
    saying "on both sides" was a claim about a region only one side had named."""
    at = wb("FAT_DIR_BUFFER") - base
    ours = int.from_bytes(staged_block(wb("FAT_DIR_BUFFER"), LONGWORD_BYTES, "fat_dir_buffer"),
                          "big")
    theirs = int.from_bytes(measured[at:at + LONGWORD_BYTES], "big")
    if ours == theirs:
        return (("both sides",) + fat_buffer_extent(ours, "the staged image's"),)
    return (("the recomputed span",) + fat_buffer_extent(ours, "the staged image's"),
            ("the measured dump",) + fat_buffer_extent(theirs, "the measured dump's"))


def clusters(addresses):
    """Contiguous runs of `addresses`, as (start, length) — what a residue looks like as bands."""
    runs = []
    for at in addresses:
        if runs and at == runs[-1][0] + runs[-1][1]:
            runs[-1] = (runs[-1][0], runs[-1][1] + 1)
        else:
            runs.append((at, 1))
    return runs


# ONE WALK OF HALF A MEGABYTE, AND EVERY FIGURE BELOW COMES OFF IT — and it is `original.py`'s walk,
# not a second one. The first draft of this section counted the differences three times (once for the
# bands, once for the printed headline, once per cluster listing), and even collapsed to one it was
# still a copy of the comprehension `mode_variance` uses. That mattered here more than anywhere: the
# mis-anchor control below takes its NUMERATOR from this walk and its FLOOR from `original.py
# variance`'s reading, so two implementations would be a control graded with a different instrument
# from the one it controls.
differing_addresses = original.differing_addresses


def span_diff(ours, theirs, base):
    """(rows, differ, residue) for the recomputed span against the measured dump.

    `rows` is one `(name, ok, detail)` per band — the band's reading against its own ceiling —
    `differ` is every differing address, and `residue` is the subset outside every band, which is
    the row this mode exists to assert."""
    if len(ours) != len(theirs):
        return [("the two spans are the same length", False,
                 f"{len(ours)} recomputed against {len(theirs)} measured")], None, None
    differ = differing_addresses(ours, theirs, base)
    rows = []
    claimed = set()
    for name, start, end, ceiling, why in BOOT_SPAN_BANDS:
        inside = [at for at in differ if start <= at < end]
        claimed |= set(inside)
        # A BAND WITH A CEILING IS A BOUNDED EXCLUSION AND ONE WITHOUT IS AN OWNED REGION, and the
        # difference is printed rather than blurred. The four imported bands carry `original.py
        # variance`'s OWN ceilings, which is the strong reading: this recomputation differs from the
        # measured dump by no more, in those bands, than two boots of the original differ from each
        # other. The six WHOLE_BAND ones are small objects owned entirely by something this build
        # does not run, so any byte of them may differ and a ceiling equal to the band's width would
        # be a tautology wearing a check's clothes.
        rows.append((f"band: {name}", ceiling is WHOLE_BAND or len(inside) <= ceiling,
                     f"[{start:#x},{end:#x}): {len(inside)} of {end - start} bytes differ, "
                     + ("no ceiling" if ceiling is WHOLE_BAND else f"ceiling {ceiling}")
                     + f" — {why}"))
    return rows, differ, [at for at in differ if at not in claimed]


def report_span(span_bytes, base, differ, residue, measured):
    """Print what the ROWS DO NOT CARRY, which is what is left for a reader to see.

    THE BAND READINGS ARE NOT PRINTED HERE, and they were: every band's `detail` is already a row in
    `boot_span_rows`' return, which `report` prints a few lines below under the mode banner — so each
    band's line appeared twice, ten duplicated lines above the report they duplicate. What only this
    function has is the headline, the `fat_dir_buffer` note (a measurement rather than a band) and
    the residue's contiguous runs, which is how the last bands in the table were named."""
    for whose, lo, hi in fat_buffer_extents(measured, base):
        # `differ` is sorted, so the count inside an extent is the gap between two insertion points
        # rather than a tenth walk of half a megabyte.
        moved = bisect.bisect_left(differ, hi) - bisect.bisect_left(differ, lo)
        print(f"   note the FDC's sector staging buffer as {whose} name it, [{lo:#x},{hi:#x}): "
              f"{moved} bytes differ — `stage_load_window` rebuilds that region on both sides, so "
              f"it needs no exclusion")
    print(f"   the recomputed span [{base:#x},{base + span_bytes:#x}): "
          f"{span_bytes - len(differ)} of {span_bytes} bytes are the measured dump's own")
    if residue:
        runs = clusters(residue)
        print(f"   OUTSIDE EVERY NAMED BAND: {len(residue)} bytes, in {len(runs)} runs:")
        for start, length in runs[:BOOT_RESIDUE_CLUSTERS_SHOWN]:
            print(f"     {start:#x}..{start + length:#x}  {length} bytes")


def measured_dump():
    """`original.py dump`'s span — the image this mode's own span is differenced against."""
    path = original.BUILD / original.DUMP_FILE
    if not path.exists():
        raise SystemExit(f"{path} is missing — run `python3 atari/original.py dump`, which is the "
                         f"MEASURED half of this comparison")
    ok, message = original.check_manifest(original.BUILD)
    if not ok:
        raise SystemExit(f"FAIL: {message}")
    print(f"   {message}")
    return path.read_bytes()


def boot_checks(record, stats, want_pens, want_screen):
    """The boot differential, as `(name, ok, detail, key)` rows.

    `key` is `None` for a precondition, a SURFACE for the credits comparison rows, and
    SPAN_ROWS for the recomputed image — `title_checks`' structural key with one more group, so the
    mis-run control can invert exactly the rows a suppressed slice can break and assert the rest
    normally (m2fault's rule)."""
    checks = []

    def add(name, ok, detail, key=None):
        checks.append((name, bool(ok), detail, key))

    for name, ok, detail in readback_checks(stats):
        add(name, ok, detail)

    # RB_VBL_TICKING IS ENTRY-STATE-VACUOUS IN THIS MODE, and the note is what stops it reading as
    # coverage — `unreachable_readbacks`' rule, one function over, applied to a bit whose vacuity is
    # a property of the RUN rather than of the staged image. The shim's `run_vblanks(SMOKE_VBLS)`
    # comes AFTER the whole chain, which has already spent hundreds of vblanks, so it returns without
    # waiting for anything. What reads the same fact non-vacuously is the `vbl_ticks_at_span` row
    # below, and it is asserted rather than printed.
    if record["vbl_ticks_at_span"] >= SMOKE_VBLS:
        print(f"   note 'RB_VBL_TICKING' is vacuous in this mode: the chain had already spent "
              f"{record['vbl_ticks_at_span']} shim vblanks by the time it reached the span, so the "
              f"shim's wait for {SMOKE_VBLS} was satisfied before it was made. The non-vacuous "
              f"reading is 'the machine drove the chain, not just the tail' below.")

    # THE CHAIN RAN TO ITS END, and each slice's own report says how. Two of the five loads are armed
    # by the chain itself, so the two slices that hold them must say WB_LOAD_COPYLOCK_RAN and the
    # credits slice — which arms nothing — must say WB_LOAD_OK. One loop rather than three
    # hand-written rows, for the reason the `.RAD` header loop twelve lines below is one: three
    # copies of a row differing in four values is three chances to key one of them wrong, which is
    # this round's own recorded defect one function down.
    for row, slice_fn, field, want, want_name, key in (
            ("the title slice ran the armed load", "boot_title_screen", "title_result",
             LOAD_COPYLOCK_RAN, "WB_LOAD_COPYLOCK_RAN", None),
            ("the credits slice loaded unarmed", "boot_credits_screen", "credits_result",
             LOAD_OK, "WB_LOAD_OK", CREDITS_SLICE_ROW),
            ("the stage slice ran the armed SPRITES.CRU load", "boot_load_stage", "stage_result",
             LOAD_COPYLOCK_RAN, "WB_LOAD_COPYLOCK_RAN", STAGE_PIN_ROW)):
        add(row, record[field] == want,
            f"{slice_fn} returned {record[field]} ({want_name}={want})", key)
    # ...AND ITS TRUTH IS COUPLED TO WHERE A SUPPRESSION STOPS THE CHAIN, which the detail says
    # rather than leaves for a reader to discover. `load_resource_by_index` clears the flag on the
    # armed arm, so "left down" means the LAST armed load ran. Today the mis-run control's cascade
    # stops at the UNARMED overlay load, downstream of the title's arming and upstream of
    # SPRITES.CRU's — so the flag is down in both modes and this stays a precondition. A cascade that
    # moved to stop at the armed SPRITES.CRU load instead would leave the flag standing at $ffff, and
    # the control would abort as "its own run is not sound" for a control that was working. Left
    # UNKEYED deliberately: in the mode this file has, the row really is a precondition, and keying
    # it would invert a row the suppression does not move.
    add("the protection is left disarmed", record["copylock_arm_flag"] == COPYLOCK_CLEAR,
        f"WB_COPYLOCK_ARM_FLAG={record['copylock_arm_flag']:#06x} — load_resource_by_index clears "
        f"it on the armed arm, so a chain that ran to the end leaves it down. Coupled to WHERE a "
        f"stop lands: a chain stopped at the armed SPRITES.CRU load would leave this at $ffff and "
        f"read as an unsound control rather than as the stop it is")

    # BOTH FIRE GATES WERE CROSSED AND NEITHER WAIT TIMED OUT. This is what the driven pass adds over
    # the undriven one, and the undriven one is where it is shown to be the pokes that do it.
    add("both fire gates were crossed", record["fire_gates_crossed"] == BOOT_FIRE_GATES
        and record["fire_waits_timed_out"] == 0,
        f"{record['fire_gates_crossed']} of {BOOT_FIRE_GATES} gates, "
        f"{record['fire_waits_timed_out']} waits timed out"
        + (f" at {record['fire_wait_timed_out_pc']:#x} — the "
           + ("PRESS" if record["fire_wait_timed_out_pc"] == record["fire_press_pc"] else "RELEASE")
           + " half, so it is that poke that did not land"
           if record["fire_wait_timed_out_pc"] else ""))

    # THE TWO PICTURES' FILES ARE THE FILES ON THE DISK, read out of the load buffer after each load.
    for which, index in (("title", wb("RESOURCE_TITLESCR")), ("credits", wb("RESOURCE_CREDITS"))):
        packed, unpacked, filesize = rad_header(index)
        add(f"the {which} file the machine served is the file on the disk",
            record[f"{which}_packed"] == packed and record[f"{which}_unpacked"] == unpacked
            and packed + RAD_HDR_LEN == filesize,
            f"the buffer at {RESOURCE_LOAD_BUFFER:#x} held {record[f'{which}_packed']}/"
            f"{record[f'{which}_unpacked']} packed/unpacked after the load; the shipped "
            f"{resource_name(index)} is {filesize} bytes and says {packed}/{unpacked}",
            CREDITS_SLICE_ROW if which == "credits" else None)

    want_base = record["image_base"] + SCREEN_LOW
    add("the shifter displays the buffer copy_screen filled",
        record["shifter_base"] == want_base and record["screen_base_published"] == want_base
        and record["captured_at"] == SCREEN_LOW,
        f"$ffff8201/8203 read back {record['shifter_base']:#x}, the backend wrote "
        f"{record['screen_base_published']:#x}, the capture was taken at "
        f"{record['captured_at']:#x} and the image is at {record['image_base']:#x}")
    # THE ONE SURFACE THAT CAN SEE `$e5a2`. ../STATUS.md batch 44 phase C measures the credits
    # slice's single colour write as a SURVIVING mutant off target — the oracle drops a write to a
    # register outside the loaded image, so no host differential can tell whether it happened. Here
    # the pen is read back off the chip and required to hold WB_CREDITS_PROMPT_COLOUR while the other
    # fifteen hold the depacked prefix's own words.
    add("set_palette reached the chip, and so did the prompt pen",
        record["pens_readback_failed"] == NO_PENS_FAILED,
        f"pens that did not read back as the credits slice put them (pen {CREDITS_PROMPT_PEN} "
        f"expected {CREDITS_PROMPT_COLOUR:#05x}, the rest the depacked prefix's): "
        f"{record['pens_readback_failed']:#06x}", CREDITS_SLICE_ROW)

    # THE CHAIN RAN ON THE MACHINE, not in the tail. `run_vblanks(SMOKE_VBLS)` after the chain would
    # satisfy RB_VBL_TICKING on its own, so without this row the two readings the record carries
    # would be printed and asserted by nothing — and the C's claim that five loads and four depacks
    # take hundreds of vblanks would be prose. The floor is the same SMOKE_VBLS, taken at the SPAN's
    # instant, so what it says is that the machine was driving the reconstruction all the way to
    # `$f8b4` and not only afterwards.
    add("the machine drove the chain, not just the tail",
        record["vbl_ticks_at_span"] >= SMOKE_VBLS
        and record["vbl_ticks_at_exit"] >= record["vbl_ticks_at_span"],
        f"{record['vbl_ticks_at_span']} shim vblanks to the span and "
        f"{record['vbl_ticks_at_exit']} to the exit, against a floor of {SMOKE_VBLS}",
        STAGE_PIN_ROW)

    # THE PINS FROM THE INSIDE, which are `original.py`'s own seven asked of the RECOMPUTED image.
    # State the shipped `.PRG` does not carry and only a completed chain leaves.
    add("resource_table_relocate stamped the header",
        record["resource_signature"] == original.RESOURCE_SIGNATURE,
        f"{wb('RESOURCE_HEADER'):#x} = {record['resource_signature']:#04x}, want "
        f"{original.RESOURCE_SIGNATURE:#04x} ('E')", STAGE_PIN_ROW)
    add("stage_load_window latched the map and the start record",
        record["stage_map_ptr"] == wb("MAP_ROW_STRIDE")
        and record["stage_start_ptr"] == original.STAGE_START_PTR_VALUE,
        f"WB_STAGE_MAP_PTR={record['stage_map_ptr']:#x} (want {wb('MAP_ROW_STRIDE'):#x}), "
        f"WB_STAGE_START_PTR={record['stage_start_ptr']:#x} "
        f"(want {original.STAGE_START_PTR_VALUE:#x})", STAGE_PIN_ROW)
    add("the first stage is loaded", record["stage_number"] == original.FIRST_STAGE_NUMBER,
        f"WB_STAGE_NUMBER={record['stage_number']}, want {original.FIRST_STAGE_NUMBER}",
        STAGE_PIN_ROW)
    # ONE ROW CONSUMED AND NO MORE. `game_restart_reset` (inside the credits slice) clears the index
    # and `stage_sequence_advance` steps it past the row it took — an INDEX IN ROWS, not in bytes
    # (`at + 1`, with the `lsl.l #3` applied where the row is addressed). Both sides stepped exactly
    # once, so they must agree on the value and not merely on its being nonzero. It is a
    # credits-slice row because it is that slice's `game_restart_reset` that put the index at 0.
    staged_seq_index = staged("LEVEL_SEQ_INDEX", width=2)
    add("the sequence advanced by exactly one row", record["level_seq_index"] == SEQ_ROWS_STEPPED,
        f"WB_LEVEL_SEQ_INDEX={record['level_seq_index']} rows, want {SEQ_ROWS_STEPPED}"
        + (f" — VACUOUS on this image: the staged word is already {staged_seq_index}, so this row "
           f"cannot tell the credits slice's clear and the stage slice's step from neither having "
           f"happened. What DOES tell them apart is the stage slice's own load: an index left "
           f"unreset consumes row {SEQ_ROWS_STEPPED}, whose overlay is not on the drive"
           if staged_seq_index == SEQ_ROWS_STEPPED else
           f", against {staged_seq_index} in the staged image — the step is witnessed"),
        CREDITS_SLICE_ROW)
    # THE ROW'S TWO PUBLISHED BYTES, against the row the image itself carries. `stage_sequence_advance`
    # copies WB_LEVEL_SEQ_SECOND_LOAD out of the row (on a first entry) and `stage_sequence_apply_row`
    # turns WB_LEVEL_SEQ_SIDE into WB_STATE_FLAG_SET or 0, so both are the shipped table's own data
    # arriving in the right words rather than numbers written here.
    row = sequence_row(FIRST_SEQ_ROW)
    want_side = wb("STATE_FLAG_SET") if row[wb("LEVEL_SEQ_SIDE")] else 0
    # ...AND THE SIDE HALF OF IT IS ENTRY-STATE-VACUOUS ON THIS IMAGE, WHICH IT PRINTS. Row 0's own
    # side byte is 0, so `stage_sequence_apply_row` publishes 0 — and the staged image already
    # carries 0 in WB_STAGE_SIDE_FLAG, so that half cannot tell the publish from the byte the .PRG
    # ships. The SECOND_LOAD half is not vacuous whenever the row's byte and the staged word differ,
    # and the two are printed separately rather than blurred into one verdict — the §6 notes' style,
    # applied to the two halves of one row.
    staged_side = staged("STAGE_SIDE_FLAG", width=2)
    side_witnessed = staged_side != want_side
    add("the sequence row's own two bytes were published",
        record["stage_second_load_flag"] == row[wb("LEVEL_SEQ_SECOND_LOAD")]
        and record["stage_side_flag"] == want_side,
        f"WB_STAGE_SECOND_LOAD_FLAG={record['stage_second_load_flag']:#04x} (row "
        f"{FIRST_SEQ_ROW}'s byte is {row[wb('LEVEL_SEQ_SECOND_LOAD')]:#04x}), "
        f"WB_STAGE_SIDE_FLAG={record['stage_side_flag']:#06x} (want {want_side:#06x})"
        + (f", against {staged_side:#06x} in the staged image — the side publish is witnessed"
           if side_witnessed else
           f" — the SIDE half is VACUOUS on this image: row {FIRST_SEQ_ROW}'s side byte is 0 and "
           f"the staged word is already {staged_side:#06x}, so it cannot tell "
           f"`stage_sequence_apply_row`'s publish from the entry state. The SECOND_LOAD half is "
           f"what this row witnesses"),
        STAGE_PIN_ROW)
    # ...AND THE `clr.w` AT $e6ec MADE THE RE-ENTRY ARM ONE-SHOT: the word that would have SUPPRESSED
    # the sprite load is taken down once the stage is built, so the next stage loads its own sprites.
    # ...AND IT IS ENTRY-STATE-VACUOUS ON THIS IMAGE, WHICH THE ROW SAYS RATHER THAN HIDES. The
    # word lies inside `player_pending_event_gate`'s own code and the shipped `.PRG` already carries
    # zero there, so on the M1 image this cannot tell the `clr.w` from the byte it was handed —
    # `machine_driven`'s rule, one mode over: a check whose entry state satisfies it witnesses
    # nothing and the note is what stops it reading as coverage.
    staged_reentry = staged("LIFE_RESTART_ENTRY_C26", width=2)
    add("the re-entry word was taken down", record["life_restart_entry_c26"] == 0,
        f"WB_LIFE_RESTART_ENTRY_C26={record['life_restart_entry_c26']:#06x}"
        + (" — VACUOUS on this image: the staged word is already 0, so this row cannot tell $e6ec's "
           "clr.w from the entry state" if staged_reentry == 0 else
           f", against {staged_reentry:#06x} in the staged image — the clr.w is witnessed"),
        # A STAGE PIN AND NOT A PRECONDITION, although it reads like one: the field is written only
        # inside `take_the_span`, which the mis-run control never reaches, so left unkeyed it would
        # have counted the record's zero-init as a verified green row in the one mode where nothing
        # measured it.
        STAGE_PIN_ROW)

    # ---- the credits picture, against the shipped binary's own at $e5aa, through the SAME rows
    # the title differential uses. `picture_rows` is where they live; a second copy here would let
    # the two halves of one differential drift (`original.py`'s `capture_boot_picture`, this shore).
    return checks + picture_rows(want_screen, want_pens, "credits", BOOT_FILE)


def boot_span_rows(record, theirs, mis_anchor):
    """The recomputed span's own rows: it was written, it is the right length, and it AGREES.

    `theirs` is the measured dump and `mis_anchor` the control's two fixtures, both handed in by
    `require_the_shipped_side` so that nothing here loads a fixture a second time — a dump re-made
    between two reads would otherwise be graded by one and reported by the other. `mis_anchor` is
    `None` in the mode that cannot reach the control; see below."""
    checks = []

    def add(name, ok, detail):
        checks.append((name, bool(ok), detail, SPAN_ROW))

    base = original.WB_STAGED_AT
    path = DISK / BOOT_IMAGE_FILE
    if not path.exists():
        # WHICH OF THE TWO IT IS, from the record rather than from an assumption: `span_bytes` is set
        # inside `take_the_span`, so a non-zero reading with no file means the SPAN was taken and the
        # GEMDOS write failed — a host problem (a full disk, a read-only checkout) wearing the
        # reconstruction's clothes. `write_file` reports nothing, so the record is the only witness.
        add("the span was written", False,
            f"no {BOOT_IMAGE_FILE}, and the record says span_bytes={record['span_bytes']} — "
            + ("boot_load_stage did not return, so there was no $f8b4-equivalent instant to take "
               "it at" if record["span_bytes"] == 0 else
               "the span WAS taken at that instant, so this is the file write failing rather than "
               "the chain"))
        return checks
    ours = path.read_bytes()
    add("the span is the game's whole address space",
        len(ours) == len(theirs) and record["span_bytes"] == len(theirs),
        f"{len(ours)} bytes written, {record['span_bytes']} reported, "
        f"[{base:#x},{base + len(theirs):#x}) is {len(theirs)}")
    if len(ours) != len(theirs):
        return checks
    rows, differ, residue = span_diff(ours, theirs, base)
    report_span(len(ours), base, differ, residue, theirs)
    checks += [(f"span {name}", ok, detail, SPAN_ROW) for name, ok, detail in rows]
    add("every byte outside the named bands is the measured dump's",
        len(residue) <= BOOT_SPAN_RESIDUE_CEILING,
        f"{len(residue)} bytes differ outside every named band, against a ceiling of "
        f"{BOOT_SPAN_RESIDUE_CEILING}"
        + (f"; first at {residue[0]:#x}" if residue else ""))
    # THE CONTROL IS NOT ONE OF THE SPAN'S ROWS, and keying it as one was this round's own defect:
    # `add` stamps SPAN_ROW, the mis-run control inverts every SPAN_ROW, and a mis-anchor that had
    # STOPPED discriminating would then have been counted as evidence the control worked. It is a
    # precondition — a comparison shown to be able to fail — so it carries no key.
    #
    # IT IS REACHED IN ONE MODE, not both, and the fixtures are demanded accordingly. `bootfault`
    # stops the chain before a span is taken (README.md §14: `game_restart_reset` lives in the
    # suppressed slice), so this line is below that mode's early return and its two fixtures are not
    # asked for up front. `mis_anchor or require_the_mis_anchor()` is what keeps that an OPTIMISATION
    # rather than an assumption: if a future cascade did leave the fault mode with a span, the
    # fixtures are still required — here instead of before the boot.
    checks.append(mis_anchored_span_control(ours, base,
                                            mis_anchor or require_the_mis_anchor()) + (None,))
    return checks


# HOW FAR ABOVE THE INSTRUMENT'S OWN NOISE the mis-anchor has to sit, and it is `original.py`'s own
# multiple rather than a second one: the floor is `variance`'s measured reading times this, which is
# exactly what `mode_neighbour` requires of the shipped side's own one-call slip.
MIS_ANCHOR_FLOOR_MULTIPLE = original.MIS_ANCHOR_FLOOR_MULTIPLE


def require_the_mis_anchor():
    """(the noise reading, the mis-anchored span) — or a refusal naming the two modes that make them.

    NOT MANIFEST-PINNED TO THE DUMP'S BOOT, and that is stated rather than left to look tighter than
    it is. `build.sh m2` verifies the dump, its registers and its palette against one manifest
    because a frame staged from mixed artefacts is a silent wrong answer; this pair is a CONTROL, and
    what it has to be is a span taken at a different ANCHOR, which is a property of the run that took
    it and not of which boot it came from. What `mode_neighbour` does guarantee is that a run which
    failed to discriminate leaves no artefact at all: it unlinks the file before the boot."""
    reading = original.BUILD / original.VARIANCE_FILE
    mis_anchored = original.BUILD / original.NEIGHBOUR_DUMP_FILE
    missing = [path for path in (reading, mis_anchored) if not path.exists()]
    if missing:
        raise SystemExit(f"{', '.join(str(path) for path in missing)} is missing — run "
                         f"`python3 atari/original.py variance` and then `neighbour`, which measure "
                         f"the instrument's noise floor and keep the mis-anchored span this mode's "
                         f"own comparison is controlled against")
    return reading, mis_anchored


def mis_anchored_span_control(ours, base, mis_anchor):
    """(name, ok, detail) — THE SPAN COMPARISON, SHOWN TO BE ABLE TO FAIL.

    THE CONTROL IS THE MIS-ANCHOR, and that is M2's precedent taken literally: `smoke.py m2fault`
    reads our frames off the NEIGHBOURING shipped frame and inverts its verdict, and this reads our
    span off the shipped binary's own dump at `$e6fc` — the `bsr.w $f89e` ONE CALL before the frame
    loop, which `original.py neighbour` measures and keeps. Everything else about the run is
    unchanged: no second boot, no second binary, no build. What has to happen is that the SAME band
    table, applied to a span from a moment one call earlier, leaves a residue enormously above the
    instrument's own noise floor.

    WHY THIS RATHER THAN A SUPPRESSED CALL. A mis-run control is a build (`bootfault`, below) and it
    shows the CHAIN can fail; what it cannot show is that this comparison discriminates, because the
    credits slice is upstream of the stage load — suppress it and the chain stops before a span is
    taken at all, so the diff never runs. The mis-anchor exercises the diff itself, which is the
    row it exists to control.

    THE FLOOR IS `original.py variance`'s READING and not a number written here. Two dumps of the
    same moment already differ by hundreds of bytes — the figure MOVES between boots and
    `build/VARIANCE.txt` is the surface that owns it — so "the two differ" is true of every pair this
    instrument can produce; a floor nobody has shown to discriminate is not a floor (§9).

    IT IS THE SAME FLOOR `mode_neighbour` USES AND NOT THE SAME COMPARISON, which an earlier draft
    called symmetrical. That mode counts EVERY differing byte; this one counts only the RESIDUE —
    the bytes outside the named bands — so the numerator here is strictly the smaller of the two and
    clearing the shared floor is strictly the harder claim. Measured, the margin is wide either way
    (a hundred thousand-odd bytes against a floor in the thousands), which is why the asymmetry is
    recorded rather than corrected for."""
    reading, mis_anchored = mis_anchor
    floor = int(reading.read_text().strip()) * MIS_ANCHOR_FLOOR_MULTIPLE
    _, _, residue = span_diff(ours, mis_anchored.read_bytes(), base)
    return ("...and reading it off the ANCHOR ONE CALL EARLIER breaks that",
            residue is not None and len(residue) > floor,
            f"{0 if residue is None else len(residue)} bytes differ outside every named band "
            f"against ${original.STAGE_LOAD_CALL_PC:x}'s span, over a floor of {floor} "
            f"({MIS_ANCHOR_FLOOR_MULTIPLE}x the boot-to-boot noise original.py variance measured)")


def boot_fire_script(directory, record):
    """The debugger script that presses and releases the stick at both of the chain's gates.

    THE SAME MECHANISM THE SHIPPED SIDE USES, which is the whole reason this is honest rather than a
    fixture: `original.py`'s `boot_script` pokes WB_JOY1_STATE at `$e556`/`$e55c` and `$e5ae`/`$e5b4`
    — the addresses of the ORIGINAL's own two waits — and this pokes the same image byte at the
    addresses OUR two waits report about themselves. Both sides' boots are carried past their fire
    gates by a debugger standing in for a person, and neither side is patched.

    Each wait is entered twice, once per gate, so the four stops are two PCs by two arrivals —
    which `refuse_repeated_arrivals` accepts and two breakpoints on one arrival would not."""
    script = Path(directory) / "BOOTCMD.INI"
    script.write_text("\n".join(fire_gate_lines(directory, record, BOOT_FIRE_GATES)) + "\n")
    return script


def fire_gate_lines(directory, record, gates, after_release=None):
    """The debugger lines that press and release the stick at the run's first `gates` fire gates.

    SHARED WITH THE OWN-ENTRY MODE, which crosses more of them than the boot has: ESC's ending walks
    the data-disk prompt's gate and then the boot continuation's two again, so a run that is driven
    through a restart answers five. The arrival number is what separates them — each half is one
    function with one address, entered once per gate — so the list is a `gates` x 2 grid of stops
    and nothing about it is boot-specific.

    `after_release` is {gate index: [extra debugger commands]}, appended to that gate's RELEASE
    action. It exists because one poke has to land at a moment that is already a breakpoint and
    Hatari takes one action per (address, arrival): the ESC pass holds a scancode in the image, and
    without a release the NEXT leg quits on its first frame and restarts again. Folded into the
    existing action rather than set as a second breakpoint on the same arrival, which
    `refuse_repeated_arrivals` would — rightly — reject."""
    directory = Path(directory)
    after_release = after_release or {}
    joy1 = record["image_base"] + wb("JOY1_STATE")
    stops = []
    for gate in range(gates):
        arrival = gate + original.FIRST_HIT
        stops += [(record["fire_press_pc"], arrival, f"PRESS{gate}", FIRE_DOWN, ()),
                  (record["fire_release_pc"], arrival, f"RELEASE{gate}", FIRE_UP,
                   tuple(after_release.get(gate, ())))]
    original.refuse_repeated_arrivals([(pc, hit) for pc, hit, _, _, _ in stops])
    return [original.anchor_breakpoint(pc, hit, original.action_file(
                directory, f"BF{index}.INI", f"echo {BOOT_FIRE_BEACON}_{what}",
                original.poke_byte(joy1, value), *extra))
            for index, (pc, hit, what, value, extra) in enumerate(stops)]


def measure_the_undriven_boot_chain(prg, mode):
    """PASS ONE: boot with no poke at all, and take three things off it.

    Two are the numbers the pokes below are aimed with — where GEMDOS put the image, and where the
    two fire waits are — and the third is THE NEGATIVE CONTROL FOR THE POKES: with nothing injected
    the chain must sit at its FIRST gate until the bound runs out, report the timeout, and never
    reach the credits or the stage. A pass in which the chain got further on its own would mean the
    pokes below are not what carries it.

    IT RUNS ON THE M1 BOUND AND NOT THE BOOT'S, and that is a measurement rather than thrift. What
    this pass has to reach is the FIRST fire gate — one load and one depack — and then spin out
    `SPINS_LONG` (~6 s, ~300 vblanks) and tear down, which `RUN_VBLS` clears many times over.
    `BOOT_RUN_VBLS` is sized for the whole five-load chain, which this pass provably never runs.
    Measured, same binary, same host, undriven: 8.08 s at 12,000 vblanks against 4.52 s at 6,000 —
    3.6 s a mode, and there are two boot modes. The DRIVEN pass below still gets `BOOT_RUN_VBLS`."""
    status, log, rom = run_hatari(prg, run_vbls=RUN_VBLS,
                                  log_name=f"hatari-{mode}-plain.log")
    record, why = read_boot()
    if record is None:
        raise SystemExit(f"FAIL: the undriven pass left no readable record ({why})")
    # THE CREDITS ROW IS VACUOUS IN THE FAULT BUILD, WHICH IT SAYS. `bootfault` compiles the credits
    # call out entirely (-DBOOT_FAULT_SKIP_CREDITS), so `credits_result` stays BOOT_SLICE_NOT_RUN by
    # construction there and the row cannot tell the unanswered gate from the suppression. The stage
    # row is NOT vacuous in either mode: nothing suppresses that call, so its report is real evidence
    # that the chain stopped upstream of it.
    credits_vacuous = (" — VACUOUS in this build: the credits call is compiled out, so this row "
                       "cannot tell the unanswered gate from the suppression"
                       if mode == BOOT_FAULT_MODE else "")
    control = [
        ("the title slice ran on its own", record["title_result"] == LOAD_COPYLOCK_RAN,
         f"boot_title_screen returned {record['title_result']}"),
        # ...AND AT THE PRESS HALF OF THE FIRST GATE, which is the address it must be and no other:
        # a run that stopped at the RELEASE half would mean something had already made the byte
        # negative, and this pass injects nothing.
        ("...and the FIRST fire wait timed out, at its PRESS half",
         record["fire_waits_timed_out"] == 1 and record["fire_gates_crossed"] == 0
         and record["fire_wait_timed_out_pc"] == record["fire_press_pc"],
         f"{record['fire_waits_timed_out']} timed out at {record['fire_wait_timed_out_pc']:#x} "
         f"(wait_fire_pressed is at {record['fire_press_pc']:#x}, wait_fire_released at "
         f"{record['fire_release_pc']:#x}), {record['fire_gates_crossed']} gates crossed"),
        ("...so the credits slice never ran",
         record["credits_result"] == BOOT_SLICE_NOT_RUN,
         f"boot_credits_screen's report is {record['credits_result']:#x} "
         f"(BOOT_SLICE_NOT_RUN={BOOT_SLICE_NOT_RUN:#x})" + credits_vacuous),
        ("...nor the stage slice", record["stage_result"] == BOOT_SLICE_NOT_RUN,
         f"boot_load_stage's report is {record['stage_result']:#x}"),
        ("...and no span was taken", record["span_bytes"] == 0
         and not (DISK / BOOT_IMAGE_FILE).exists(),
         f"span_bytes={record['span_bytes']}, {BOOT_IMAGE_FILE} "
         f"{'present' if (DISK / BOOT_IMAGE_FILE).exists() else 'absent'}"),
    ]
    report(f"{mode} pass 1 — the UNDRIVEN boot, which is the fire pokes' negative control", control)
    print(f"   TOS={rom or 'bundled EmuTOS'} hatari exit={status}; image at "
          f"{record['image_base']:#x}, the two waits at {record['fire_press_pc']:#x} and "
          f"{record['fire_release_pc']:#x}, {record['vbl_ticks_at_exit']} shim vblanks")
    refuse_unless_the_control_holds(control, "the driven run below")
    return record, log, status


def require_the_shipped_side(reaches_the_span_control):
    """Everything `original.py` owes this mode, LOADED before the first boot is paid for.

    Each fixture raises on its own when it is reached, and all of them used to be reached AFTER two
    full 12,000-vblank runs — so a reader who had not run `original.py credits` paid for both boots
    and then got a refusal instead of a report, with every green row already computed thrown away.
    That is the hazard `resource_name`'s own comment names, one function over. The fixtures are all
    knowable before the emulator starts, so they are asked for here.

    AND THEY ARE RETURNED RATHER THAN MERELY TOUCHED. Loading each of them a second time at the point
    of use was two readings of one fixture: the manifest line printed twice, and a dump re-made
    between the two reads would have been VERIFIED by the first read and GRADED by the second.

    `reaches_the_span_control` is False for the mis-run mode, whose chain stops before a span is
    taken — so the mis-anchor control is never reached there and demanding its two fixtures up front
    would refuse a mode that does not need them. `boot_span_rows` still requires them if that mode
    ever does produce a span."""
    screen, pens = shipped_picture(original.CREDITS_SCREEN_FILE, original.CREDITS_PENS_FILE,
                                   BOOT_CREDITS_ANCHOR_MODE)
    return (screen, pens, measured_dump(),
            require_the_mis_anchor() if reaches_the_span_control else None)


def mode_boot(mode):
    """THE BOOT: two passes, the credits picture, and the post-boot image RECOMPUTED."""
    control = mode == BOOT_FAULT_MODE
    prg = BUILD / BOOT_BUILDS[mode]
    refuse_a_stale_build(prg, mode)
    their_screen, their_pens, theirs, mis_anchor = require_the_shipped_side(not control)
    plain, plain_log, plain_status = measure_the_undriven_boot_chain(prg, mode)
    problems = check_machine_health(plain_status, plain_log)

    with tempfile.TemporaryDirectory() as tmp:
        script = boot_fire_script(tmp, plain)
        status, log, rom = run_hatari(prg, run_vbls=BOOT_RUN_VBLS, parse=script,
                                      log_name=f"hatari-{mode}-driven.log")
    problems += check_machine_health(status, log)
    record, why = read_boot()
    stats, stats_why = read_stats()
    for missing in (why, stats_why):
        if missing:
            problems.append(missing)
    if record is None or stats is None:
        report(mode, [])
        raise SystemExit("FAIL: " + "; ".join(problems))
    # THE TWO PASSES MUST AGREE ABOUT WHERE THE PROGRAM IS, which is M5's and M3's rule: a different
    # base means the pokes went into somebody else's memory and the run below is not a drive.
    #
    # THE THREE NUMBERS THE POKES WERE AIMED WITH, NOT ONLY THE BASE. `image_base` is 256-aligned
    # (wonderboy_main.c's IMAGE_ALIGN) and so is strictly COARSER than the two fire-wait PCs pass two
    # reuses out of pass one: a TPA shift of less than 256 bytes leaves this row green while every
    # breakpoint is set on a stale address, and the four pokes then land nowhere. M3 pins `capture_pc`
    # across its own two passes for exactly this reason.
    for field, what in (("image_base", "put the image at"),
                        ("fire_press_pc", "reports wait_fire_pressed at"),
                        ("fire_release_pc", "reports wait_fire_released at")):
        if record[field] != plain[field]:
            problems.append(f"the driven boot {what} {record[field]:#x} where the undriven one "
                            f"reported {plain[field]:#x} — the pokes were aimed with the wrong "
                            f"address")

    checks = boot_checks(record, stats, their_pens, their_screen)
    checks += boot_span_rows(record, theirs, mis_anchor)
    report(f"{mode} (mis-run control — the CREDITS SLICE's rows and the SPAN MUST fail)" if control
           else mode, checks)
    print(f"   TOS={rom or 'bundled EmuTOS'} hatari exit={status}; image at "
          f"{record['image_base']:#x}, {record['vbl_ticks_at_span']} shim vblanks to the span and "
          f"{record['vbl_ticks_at_exit']} to the exit (full log in "
          f"{OUT / f'hatari-{mode}-driven.log'})")

    if not control:
        problems += [f"{name}: {detail}" for name, ok, detail, _ in checks if not ok]
        if problems:
            raise SystemExit("FAIL: " + "; ".join(problems))
        print("OK: THE BOOT — the reconstruction ran all three of the boot chain's composed slices "
              "on a 68000 over the shipped program and its own five files, drew the credits screen "
              "byte-identically to the shipped binary's, and RECOMPUTED the post-boot image that "
              "gen_image.py has been staging as a measurement")
        return

    # THE CONTROL ASSERTS ITS PRECONDITIONS NORMALLY and inverts only the rows the suppressed slice
    # can reach — `m2fault`'s rule, and for its reason: a control whose own run was unsound proves
    # nothing, and "the span differs" is satisfied by a run that computed no span at all.
    # WHAT A SUPPRESSED CREDITS SLICE CAN REACH, and it is more than that slice's own rows —
    # measured rather than assumed. `game_restart_reset` lives inside it and is what puts
    # WB_LEVEL_SEQ_INDEX at 0, so without it `stage_sequence_advance` consumes a DIFFERENT sequence
    # row, asks for an overlay that is not on the drive, and `load_or_stop` stops the chain. Every
    # stage pin and the span itself are therefore downstream of the suppression and are inverted with
    # it. What stays asserted NORMALLY is still a real precondition set (m2fault's rule): the
    # sixteen read-backs, the title slice's armed load and its file, both fire gates, the shifter
    # base and the protection left disarmed.
    breakable = (CREDITS_SLICE_ROW, STAGE_PIN_ROW, BITPLANES, PENS, SPAN_ROW)
    preconditions = [(name, ok, detail) for name, ok, detail, key in checks if key not in breakable]
    problems += [f"{name}: {detail}" for name, ok, detail in preconditions if not ok]
    if problems:
        raise SystemExit("FAIL: the control's own run is not sound, so its inverted verdict says "
                         "nothing: " + "; ".join(problems))
    broken = [name for name, ok, _, key in checks if key in breakable and not ok]
    held = [name for name, ok, _, key in checks if key in breakable and ok]
    if not broken:
        raise SystemExit("FAIL: suppressing the credits slice broke NO row — this control cannot "
                         "fail and proves nothing, so the rows above are not reading what they name")
    for name in held:
        # NAMED, NOT SWALLOWED — `mode_title`'s rule. A row the suppression happens not to move is a
        # row this control does not cover, and saying which is the difference between an exclusion
        # and an omission. `WB_LIFE_RESTART_ENTRY_C26` is the standing one: the shipped image already
        # carries zero there, so neither a chain that ran nor one that stopped can move it.
        print(f"   note {name!r} held: suppressing boot_credits_screen moves nothing this row can "
              f"see, so this control does not cover it")
    print(f"OK: {len(broken)} of {len(broken) + len(held)} breakable rows FAIL with "
          f"boot_credits_screen's call suppressed ({len(held)} named above)")



# ---- M5: the hardware-state vector, and the rendered picture -------------------------------------
#
# WHAT M5 ADDS OVER M2, in one sentence: M2 compares what the reconstruction DREW and reads ONE
# hardware register back; M5 compares THE MACHINE — thirty-six registers captured the same way on both
# sides at every anchor — and the picture the shifter actually put on a display surface.
#
# The capture commands and the parser are atari/original.py's, used by both sides, so the two cannot
# drift into measuring different things. What is here is the DRIVING and the COMPARING.
VECTOR, PICTURE = "vector", "picture"
# The shim's out-of-band "no pen was corrupted" sentinel. `wonderboy_main.c`'s `NO_FAULTED_PEN` is
# `PALETTE_PENS`, which is `WB_PALETTE_COLOURS` — the same constant this derives from, one header
# away. A pen number is 0..15 and this is 16, so a build with no fault in it cannot pass for one
# that faulted pen 0.
NO_FAULT_PEN = PALETTE_PENS

# WHICH ANCHORS THE RENDERED COMPARE ASSERTS ON, and it is MEASURED rather than chosen. `screenshot`
# grabs the rendered display surface; `--frameskips 0` asks Hatari to render every frame and
# stop-then-shoot moves each capture to a vblank boundary, but under `--fast-forward` neither closes
# the window entirely. The recipe that owns this number is in atari/README.md §10: run `smoke.py m5`
# twice and diff atari/out/m5/, and run `original.py frames` twice and diff the shipped side's
# pictures in atari/build/. An anchor whose PNG is not byte-reproducible on BOTH sides is asserting
# on noise and does not belong here.
RENDER_ANCHORS = (1, 2, 51, 52)
# Where each run's own pictures are kept, so that re-running the mode IS the reproducibility
# measurement rather than something a separate harness would have to arrange.
#
# PER MODE, AND EMPTIED FIRST. One shared directory made the stated recipe — "run `smoke.py m5`
# twice and diff `out/m5/`" — read whatever the last mode wrote, so an `m5fault` run in between
# would have left a deliberately colour-corrupted picture for the diff to certify against; and a run
# that raised after two of four anchors would leave the other two stale for the next one to compare.
def picture_dir(mode):
    return OUT / "pictures" / mode


def our_capture_script(directory, capture_pc, anchors):
    """The debugger script that photographs OUR side at every anchor.

    ONE BREAKPOINT PER ANCHOR, on `capture_the_frame`'s own entry: the shim calls it once per anchor
    frame and nowhere else, so the Nth arrival IS the Nth anchor and the vector is taken at the very
    instant FRAME.BIN and PENS.BIN are.

    The breakpoint line, the action file and the same-arrival guard are all `original.py`'s — the
    shipped side has spelled them for three modes, including Hatari's rejection of an explicit `:1`,
    and a second spelling on this side is one that can quietly stop matching the other."""
    stops = [(capture_pc, index) for index in range(1, len(anchors) + 1)]
    original.refuse_repeated_arrivals(stops)
    lines = [original.anchor_breakpoint(
                 pc, hit,
                 original.action_file(Path(directory), f"{original.OUR_TAG}{hit}.INI",
                                      *original.vector_commands(directory, original.OUR_TAG, hit),
                                      original.picture_command(directory, original.OUR_TAG, hit)))
             for pc, hit in stops]
    script = Path(directory) / "CMD.INI"
    script.write_text("\n".join(lines) + "\n")
    return script


def our_captures(prg, mode, anchors, capture_pc):
    """Boot our build a SECOND time, under the debugger, and take every anchor's vector and picture.

    A second boot because the shim cannot take this measurement itself: it can read the shifter, but
    the YM-2149's register file is not readable through $ff8800 without a select write, and the
    rendered surface is the emulator's. The anchor address is the one the FIRST run reported about
    itself, and the assertion that the two runs agree about it — and about every byte of both
    captured surfaces — is this mode's determinism control."""
    with tempfile.TemporaryDirectory() as tmp:
        script = our_capture_script(tmp, capture_pc, anchors)
        status, log, _ = run_hatari(prg, run_vbls=M2_RUN_VBLS, parse=script,
                                    log_name="hatari-m5.log")
        produced = {path.name: path.read_bytes() for path in Path(tmp).iterdir()
                    if path.suffix.lower() in original.CAPTURE_SUFFIXES}
    # THE PLACEMENT CHECK GOES FIRST, before a single vector is parsed. If GEMDOS put the program
    # somewhere else this time, the breakpoint fired at nothing and every message below would be
    # about a missing capture — true, and not the fact that explains it.
    again, why = read_m2()
    if again is None:
        raise SystemExit(f"FAIL: the debugger run left no readable M2.BIN ({why}) — its captures "
                         f"cannot be attributed to a run that reached its own dump")
    if again["capture_pc"] != capture_pc:
        raise SystemExit(f"FAIL: the two boots put capture_the_frame at different addresses "
                         f"({capture_pc:#x} then {again['capture_pc']:#x}) — the vector would have "
                         f"been taken at a breakpoint this run did not have")
    vectors = {frame: original.hardware_vector(log, produced, original.OUR_TAG, index, frame)
               for index, frame in enumerate(anchors, 1)}
    pictures = {frame: original.read_capture(produced, original.OUR_TAG, index,
                                             original.PICTURE_SUFFIX, frame)
                for index, frame in enumerate(anchors, 1)}
    kept = picture_dir(mode)
    if kept.exists():
        shutil.rmtree(kept)
    kept.mkdir(parents=True)
    for frame, picture in pictures.items():
        (kept / (original.PICTURE_FILE % frame)).write_bytes(picture)
    return vectors, pictures, status, log


def their_capture(prefix, frame, name, what):
    path = original.BUILD / (prefix + name % frame)
    if not path.exists():
        raise SystemExit(f"{path} is missing — run `python3 atari/original.py "
                         f"{original.FRAME_PRODUCER[prefix]}` to capture the shipped binary's "
                         f"{what} at the anchors")
    return path


def as_hex(value):
    """Register values in hex, to read against the pens beside them; a parsed string stays itself."""
    return f"{value:#05x}" if isinstance(value, int) else repr(value)


def vector_exclusions(anchors, prefix):
    """(excluded names, how many are compared, why) — what M5 captures but does not compare.

    The set is DECIDED BY KIND (original.py's VECTOR_UNCOMPARED argues each of the two kinds) and
    EVIDENCED BY MEASUREMENT: `original.py vecnoise` boots the shipped binary a second time and
    records which registers moved. That file is REQUIRED rather than defaulted to nothing, and it is
    re-checked here — if it ever names a register M5 does compare, the exclusion's evidence has
    turned into a reason to doubt the comparison, and this mode must not run past it.

    AND THE READING IS CHECKED AGAINST WHAT IT COVERS. A bare list of names licenses any run at all:
    a later anchor set, or a register the vector did not carry when the measurement was taken, is a
    measurement nobody has made. So `vecnoise` stamps the anchors and the register names it saw and
    this refuses anything they do not cover — the same rule `original.py dump`'s manifest applies to
    the staged image's three artefacts."""
    # PER SHIPPED BOOT, because the tripwire has to have looked at the boot it licenses: on the
    # FLASHED one, colour 0 is driven by a countdown the debugger seeds, so `pen00` is a compared
    # register whose reproducibility the unflashed reading says nothing about.
    path = original.BUILD / (prefix + original.VECTOR_NOISE_FILE)
    mode = "flashnoise" if prefix else "vecnoise"
    if not path.exists():
        raise SystemExit(f"{path} is missing — run `python3 atari/original.py {mode}`. It is the "
                         f"evidence that the registers this mode does NOT compare are the ones the "
                         f"shipped binary itself does not reproduce, and the tripwire for the rest.")
    reading = json.loads(path.read_text())
    if reading.get("anchors") != list(anchors):
        raise SystemExit(f"{path} was measured over anchors {reading.get('anchors')} and this run "
                         f"uses {list(anchors)} — the exclusion below would be resting on a "
                         f"measurement of different moments. Re-run `original.py {mode}`.")
    excluded = set(original.VECTOR_REPORT_ONLY) | set(original.VECTOR_UNCOMPARED)
    uncovered = sorted((set(original.VECTOR_UNCOMPARED)) - set(reading.get("registers", ())))
    if uncovered:
        raise SystemExit(f"{path} never saw {uncovered}, which M5 excludes on the strength of it — "
                         f"the vector has grown a register since the measurement was taken. Re-run "
                         f"`original.py {mode}`.")
    noise = reading["moved"]
    intruders = sorted(set(noise) - excluded)
    if intruders:
        raise SystemExit(f"{path} records {intruders} moving between two boots of the shipped "
                         f"binary, and M5 COMPARES those registers — so the compared half of the "
                         f"vector is not reproducible on the shipped side either, and every green "
                         f"below would be luck. Re-run `original.py {mode}` and read its verdict.")
    # VECTOR_REGISTERS already leaves the report-only entries out, so only the other kind comes off.
    compared = original.VECTOR_REGISTERS - len(original.VECTOR_UNCOMPARED)
    return excluded, compared, (
        f"{len(original.VECTOR_REPORT_ONLY)} report-only "
        f"({', '.join(original.VECTOR_REPORT_ONLY)}) and the whole {len(original.VECTOR_UNCOMPARED)}"
        f"-register YM-2149 file — ym00..ym13 because the music's position at an anchor is not "
        f"controlled on either side ({len(noise)} of them, {', '.join(noise)}, measured moving "
        f"between two boots of the SHIPPED binary), ym14/ym15 because they are the parallel ports "
        f"and carry the host's floppy drive select. The sound's own surface is M6's write timeline")


# ANCHORS WHOSE PICTURE IS NOT BYTE-REPRODUCIBLE, with the measurement that says so. Empty today —
# `smoke.py m5` twice and `original.py frames` twice give identical PNGs at all four — and it exists
# so that the day one is not, the fact is written down beside the anchor instead of being expressed
# by quietly shortening RENDER_ANCHORS. The sibling project could assert on one anchor of six.
RENDER_NOT_REPRODUCIBLE = {}


def require_every_anchor_is_rendered(anchors):
    """Every anchor gets a rendered row, or is NAMED as one that cannot.

    The weak version of this guard — "at least one anchor is rendered" — is what the first draft
    had, and it lets a newly added anchor get a vector row and no picture row while the success line
    still prints a list that no longer covers the anchor set. An anchor asserted by nobody must be an
    anchor somebody wrote a reason for."""
    unnamed = [frame for frame in anchors
               if frame not in RENDER_ANCHORS and frame not in RENDER_NOT_REPRODUCIBLE]
    if unnamed:
        raise SystemExit(f"anchors {unnamed} have no rendered row and no measured reason — add them "
                         f"to RENDER_ANCHORS, or to RENDER_NOT_REPRODUCIBLE with the reading that "
                         f"shows their picture is not reproducible on both sides")
    for frame, why in RENDER_NOT_REPRODUCIBLE.items():
        if frame in anchors:
            print(f"   note frame {frame} has no rendered row: {why}")
    stale = sorted(set(RENDER_ANCHORS) - set(anchors))
    if stale:
        raise SystemExit(f"RENDER_ANCHORS names {stale}, which this run does not capture — the "
                         f"rendered claim would list frames nobody photographed")


def m5_checks(our_vectors, our_pictures, anchors, prefix, excluded, compared, shift=0):
    """The two surfaces M5 adds, one row each per anchor, keyed structurally like M2's.

    `excluded`/`compared` come from `vector_exclusions`, computed ONCE by the caller: it is a run
    precondition (it raises on a missing or stale `VECNOISE.json`), and a precondition enforced from
    three places is a precondition nobody can point at."""
    checks = []
    require_every_anchor_is_rendered(anchors)
    for index, frame in enumerate(anchors):
        against = anchors[(index + shift) % len(anchors)]
        mine = our_vectors[frame]
        theirs = json.loads(their_capture(prefix, against, original.VECTOR_FILE,
                                          "hardware-state vector").read_text())
        # A FLOOR ON WHAT WAS PARSED, because this whole surface can go quiet: if Hatari's `info`
        # wording changes, every regex misses, BOTH sides shrink to the savebin-derived entries and
        # the compare prints IDENTICAL over a stump. The floor is on what the parsers YIELDED, before
        # any exclusion, so a degraded capture cannot hide behind an exclusion list.
        #
        # The UNION of both sides' names: iterating the shipped side alone would never notice a
        # register present in ours and missing from theirs.
        parsed = sorted((set(mine) | set(theirs)) - set(original.VECTOR_REPORT_ONLY))
        names = [name for name in parsed if name not in excluded]
        wrong = [name for name in names if mine.get(name) != theirs.get(name)]
        degraded = len(parsed) < original.VECTOR_REGISTERS or len(names) != compared
        if degraded:
            detail = (f"{len(parsed)} registers parsed and {len(names)} compared, expected "
                      f"{original.VECTOR_REGISTERS} and {compared} — a capture or a parser stopped "
                      f"yielding, so this surface is no longer comparing what it claims")
        elif wrong:
            detail = f"{len(wrong)} of {len(names)} registers differ: " + ", ".join(
                f"{name} shipped {as_hex(theirs.get(name))} ours {as_hex(mine.get(name))}"
                for name in wrong[:8])
        else:
            # THE UNCOMPARED REGISTERS ARE PRINTED, both sides, and that is the point of capturing
            # them at all: the YM file is where this game's sound lands, and a reader who cannot see
            # the two columns cannot tell "excluded because it is noise" from "excluded because it
            # was inconvenient". The evidence is in the run's own output either way.
            detail = (f"{len(names)} registers identical; "
                      + " ".join(f"{name}={mine.get(name)}"
                                 for name in original.VECTOR_REPORT_ONLY if name in mine)
                      + "; ym file ours "
                      + " ".join("%02x" % mine.get(name, 0) for name in original.VECTOR_UNCOMPARED)
                      + " shipped "
                      + " ".join("%02x" % theirs.get(name, 0)
                                 for name in original.VECTOR_UNCOMPARED))
        checks.append((f"frame {frame} hardware vector" + (f" (vs shipped {against})" if shift else ""),
                       not wrong and not degraded, detail, (VECTOR, frame, against)))
        # BOTH ENDS OF THE PAIR. Gating on `frame` alone would, the day an anchor moved into
        # RENDER_NOT_REPRODUCIBLE, still compare the skewed row against THAT anchor's picture
        # — a PNG the harness has just declared noise — and `m5_reachable` (which gates on
        # both) would then exclude the row with an explanation about identical pictures that
        # is not the reason.
        if frame not in RENDER_ANCHORS or against not in RENDER_ANCHORS:
            continue
        theirs_png = their_capture(prefix, against, original.PICTURE_FILE,
                                   "rendered picture").read_bytes()
        same = our_pictures[frame] == theirs_png
        checks.append((f"frame {frame} rendered picture"
                       + (f" (vs shipped {against})" if shift else ""), same,
                       f"{len(our_pictures[frame])} bytes of PNG, identical" if same
                       else f"ours {len(our_pictures[frame])} bytes, shipped {len(theirs_png)} — "
                            f"the display path itself, since memory and the vector are compared "
                            f"above", (PICTURE, frame, against)))
    return checks


# WHICH ROWS EACH M5 CONTROL MUST BREAK, AND WHICH IT MUST LEAVE ALONE. Naming both halves is the
# point: a control that fails for the wrong reason proves nothing about the check it exists for, and
# a surface listed in neither is a surface neither control asserts. Membership is TOTAL over the four
# surfaces and checked below, so adding a fifth forces both entries to classify it.
M5_CONTROLS = {
    # ONE PEN CORRUPTED on its way to the shifter (build.sh's `m5fault`, pen 3 = $777, the white the
    # HUD is drawn in and therefore certainly on screen). The machine's COLOUR is wrong by exactly
    # one register and every byte the reconstruction DRAWS is untouched, so all three surfaces that
    # read colour must go red and the one that reads drawn bytes must not.
    "m5fault": {"fail": (PENS, VECTOR, PICTURE), "pass": (BITPLANES,)},
    # OUR ANCHORS READ OFF THE NEIGHBOURING SHIPPED FRAME. This game's picture toggles on a
    # one-second cadence, so only the pairs a shift can actually reach are required to break — the
    # rest are excluded and PRINTED. The vector and the pens must NOT move: the palette is the same
    # at every anchor and a frame shift writes no different YM register, which is why the shift is
    # the wrong instrument for those two and the pen fault above is the right one.
    "m5skew": {"fail": (BITPLANES, PICTURE), "pass": (PENS, VECTOR)},
}
M5_SURFACES = (BITPLANES, PENS, VECTOR, PICTURE)


def report_m5_control(mode, checks, reachable):
    """A control passes only if the RIGHT surfaces failed and the others did not.

    `reachable` is the set of structural keys the fault can actually reach — for the skew that is
    measured from the shipped side's own frames, because a pair whose pictures are identical is a row
    the control cannot break rather than a row that failed."""
    expected = M5_CONTROLS[mode]
    classified = set(expected["fail"]) | set(expected["pass"])
    rows = [(name, ok, key) for name, ok, _, key in checks if key is not None]
    # TOTAL OVER THE SURFACES THE ROWS ACTUALLY CARRY, not over a hand-written tuple. Comparing
    # `classified` against M5_SURFACES alone let a FIFTH surface — a row `m5_checks` starts emitting
    # under a new key — fall through both loops below and be asserted by neither control, while the
    # guard that exists to prevent exactly that went on passing because the two written-down lists
    # still agreed with each other.
    surfaces = {key[0] for _, _, key in rows}
    if classified != set(M5_SURFACES) or not surfaces <= classified:
        raise SystemExit(f"the {mode} control classifies {sorted(classified)}, the surface list says "
                         f"{sorted(M5_SURFACES)} and the run produced {sorted(surfaces)} — every "
                         f"surface must be listed as one this fault trips or one it must leave "
                         f"alone, or it is asserted by neither")
    # EXCLUSIONS ARE PRINTED, and only for the surfaces this control is supposed to BREAK: a row of a
    # `pass` surface is not a row the control could not reach, it is a row the control asserts stays
    # green. Printing those as "excluded" would say the opposite of what is being claimed.
    for name, key in [(name, key) for name, ok, key in rows
                      if key not in reachable and key[0] in expected["fail"]]:
        surface, ours, theirs = key
        print(f"   note {name!r} is excluded: the shipped binary's {surface} are the same at frames "
              f"{ours} and {theirs}, so this fault changes nothing this row could see")
    problems = []
    for surface in expected["fail"]:
        breakable = [(name, ok) for name, ok, key in rows if key in reachable and key[0] == surface]
        if not breakable:
            problems.append(f"the {surface} rows are all excluded — this control cannot fail on the "
                            f"surface it exists to break, so its green proves nothing")
        held = [name for name, ok in breakable if ok]
        if held:
            problems.append(f"the injected fault did NOT trip {', '.join(held)}")
    for surface in expected["pass"]:
        # THE `pass` HALF NEEDS ITS OWN MINIMUM-ROW GUARD, symmetric with the `fail` half above.
        # Without it the whole claim — "a frame shift writes no different register, so these stay
        # green" — is satisfied by a run in which those rows do not exist at all.
        present = [name for name, ok, key in rows if key[0] == surface]
        if not present:
            problems.append(f"there are no {surface} rows at all, so 'the fault leaves {surface} "
                            f"alone' is asserted by nothing")
        broke = [name for name, ok, key in rows if key[0] == surface and not ok]
        if broke:
            problems.append(f"the injected fault also broke {', '.join(broke)} — the control is not "
                            f"isolating what it claims to")
    if problems:
        raise SystemExit("FAIL: " + "; ".join(problems))
    print(f"OK: the {mode} fault is caught by {'+'.join(expected['fail'])} and leaves "
          f"{'+'.join(expected['pass'])} green — which is what this control is for")


def assert_only_the_faulted_pen(our_vectors, anchors, prefix, excluded, record):
    """The fault control's SHARP half: the vector must differ at that pen AND AT NOTHING ELSE.

    Surface-level fail/pass is satisfied by any divergence at all, so on its own it would be green
    for a build that had broken something unrelated and happened to move the palette too. This says
    which register moved.

    WHICH PEN COMES FROM THE BINARY, in `M2.BIN`'s `fault_pen`, for `capture_pc`'s reason: the
    per-mode `.PRG`s persist while build.sh is edited, so scraping `-DM5_FAULT_PEN=` out of the
    script would name a pen the running binary need not have injected. `NO_FAULT_PEN` is the shim's
    out-of-band sentinel, so a build with no fault in it cannot be mistaken for one that faulted
    pen 0."""
    if record["fault_pen"] == NO_FAULT_PEN:
        raise SystemExit(f"FAIL: the binary reports no injected pen (fault_pen = {NO_FAULT_PEN}), so "
                         f"this control is running a build with nothing wrong with it — rebuild with "
                         f"`bash atari/build.sh m5fault`")
    want = "pen%02d" % record["fault_pen"]
    for frame in anchors:
        mine = our_vectors[frame]
        theirs = json.loads(their_capture(prefix, frame, original.VECTOR_FILE,
                                          "hardware-state vector").read_text())
        wrong = sorted(name for name in (set(mine) | set(theirs)) - excluded
                       if mine.get(name) != theirs.get(name))
        if wrong != [want]:
            raise SystemExit(f"FAIL: at frame {frame} the injected fault moved {wrong or 'nothing'}, "
                             f"not exactly [{want!r}] — the control is not measuring the fault it "
                             f"injected")
    print(f"   the divergence is {want} and nothing else, at all {len(anchors)} anchors")


def m5_reachable(mode, anchors, prefix, rows, shift):
    """The structural keys `mode`'s fault can actually reach, derived from the data.

    For the pen fault every row is reachable: it is injected on OUR side and moves whatever looks at
    colour. For the skew it is the shipped side's own frames differenced against their neighbours —
    a pair the shipped binary draws identically is a pair a shift cannot separate, and a list written
    down here would go stale the moment the anchors moved."""
    if mode == "m5fault":
        # FROM THE ROWS THAT EXIST, not from a surface x anchor product. The fault is injected on OUR
        # side and moves whatever looks at colour, so every row it produces IS reachable — but a
        # fabricated key for a row that does not exist makes the "this control cannot fail" guard
        # answer about the product instead of about the run.
        return {key for _, _, _, key in rows if key is not None}
    # THE SHIFT IS THE CALLER'S, not a second reading of the constant. `shiftable_pairs`' own comment
    # records this exact bug being fixed once already — "an earlier draft matched rows by string
    # equality and hardcoded a shift of one on this side, so the two could only ever agree by
    # accident" — and the keys this builds have to pair the anchors the way `m5_checks` paired them
    # or the reachable set silently stops intersecting the rows.
    keys = shiftable_pairs(anchors, shift, prefix)
    for index, frame in enumerate(anchors):
        against = anchors[(index + shift) % len(anchors)]
        if frame in RENDER_ANCHORS and against in RENDER_ANCHORS:
            mine = their_capture(prefix, frame, original.PICTURE_FILE, "rendered picture")
            other = their_capture(prefix, against, original.PICTURE_FILE, "rendered picture")
            if mine.read_bytes() != other.read_bytes():
                keys.add((PICTURE, frame, against))
        # The vector is not in here at all, and that is the measurement M5_CONTROLS states: the
        # shipped binary's pens and YM file are the same at every anchor, so a frame shift has
        # nothing to move. The `pass` half of the skew control is what asserts it.
    return keys


# The image word `m5flash` arms and the other three modes must find unarmed — the same constant
# `build.sh m5flash` compiles in and `original.py flash` pokes, so all three read the ORIGINAL's own
# `move.w #$2,$714.w` operand and there is no fourth spelling to drift.
FLASH_DISARMED = 0


def flash_checks(mode, record, anchors, prefix, excluded):
    """WHETHER THE FABRICATION LANDED — asserted, not printed, and on both sides.

    `m5flash`'s whole distinguishing claim is that `flip_screen`'s two flash arms EXECUTE, and the
    mode is not a control, so it takes the plain agree-with-the-shipped-binary path. Left as a
    printed number, the failure mode is the worst kind of green: the seed comes from ONE constant
    that both sides scrape, so a change that zeroes it disarms BOTH, colour 0 never moves, all four
    surfaces still agree, and the mode reports success while the mutant it exists to kill is alive
    again. A two-sided differential cannot see a fault that hits both sides at once — only an
    assertion about the state can.

    Two rows, and the second is the one that matters:

      * OUR side really armed it — `flash_timer_at_entry` is read back out of the image after
        seeding, so it witnesses the write rather than the build flag.
      * THEIRS did too, and this is measured against the shipped binary's OWN unflashed boot rather
        than against an expectation: the `F`-prefixed and unprefixed `OVEC*.json` are both on disk,
        and the flashed one must differ from the unflashed one somewhere in the compared set. That
        is the reachability half the other three M5 modes get from their controls."""
    armed = mode == "m5flash"
    want = original.lightning_flash_seed() if armed else FLASH_DISARMED
    got = record["flash_timer_at_entry"]
    checks = [(f"WB_FLASH_TIMER at the frame loop's entry is {'the seed' if armed else 'the staged'}"
               f" value", got == want,
               f"{got:#06x}, expected {want:#06x}" + (
                   " — flip_screen's two flash arms run inside the window, seeded identically on "
                   "both sides (atari/README.md §10)" if armed
                   else " — the staged image's own value, so the flash arms are dead all fifty-two "
                        "frames"), None)]
    if not armed:
        return checks

    def compared_half(which, frame):
        vector = json.loads(their_capture(which, frame, original.VECTOR_FILE,
                                          "hardware-state vector").read_text())
        return {name: value for name, value in vector.items() if name not in excluded}

    # OVER THE COMPARED SET ONLY, and the first draft of this row was not — it differenced the whole
    # vector, which carries the music cursors and the emulator's own VBL counter, so it reported the
    # boot moving at every anchor whatever the flash did. That is the vacuity this row exists to
    # remove, reproduced inside the row itself.
    moved = sorted(frame for frame in anchors
                   if compared_half(prefix, frame) != compared_half("", frame))
    checks.append(("the shipped binary's own flashed boot differs from its unflashed one",
                   bool(moved),
                   f"the vector moves at frames {moved}" if moved
                   else "the two boots of the shipped binary are identical at every anchor, so the "
                        "poke reached nothing and this mode is a duplicate of `m5` — the flash arms "
                        "are not being exercised on either side", None))
    return checks


def mode_m5(problems, mode, prefix):
    """M5: the same fifty-two frames, compared on FOUR surfaces instead of two.

    Our side is booted twice — once plain, for the record and the two captured surfaces, and once
    under the debugger for the vector and the picture — and the two runs are required to agree,
    which is the determinism control the shipped side gets from `original.py` being run twice."""
    anchors = original.anchor_frames()
    prg = BUILD / M5_BUILDS[mode]
    status, log, rom = run_hatari(prg, run_vbls=M2_RUN_VBLS)
    print(f"-- {mode}: TOS={rom or 'bundled EmuTOS'} hatari exit={status} "
          f"(plain run's log in {OUT / 'hatari.log'})")
    problems += check_machine_health(status, log)
    record, why = read_m2()
    stats, stats_why = read_stats()
    for missing in (why, stats_why):
        if missing:
            problems.append(missing)
    if record is None or stats is None:
        report(mode, [])
        raise SystemExit("FAIL: " + "; ".join(problems))
    plain = {name: (DISK / name).read_bytes() for name in (M2_FRAME_FILE, M2_PENS_FILE)
             if (DISK / name).exists()}

    excluded, compared, why = vector_exclusions(anchors, prefix)
    print(f"   note the vector compares {compared} of its {original.VECTOR_REGISTERS} registers; "
          f"excluded are {why}")

    our_vectors, our_pictures, debug_status, debug_log = our_captures(
        prg, mode, anchors, record["capture_pc"])
    print(f"   the debugger run: hatari exit={debug_status}, anchored on capture_the_frame at "
          f"{record['capture_pc']:#x} (log in {OUT / 'hatari-m5.log'})")
    problems += check_machine_health(debug_status, debug_log)
    problems += determinism_problems(record, plain)

    # THE FRAME ROWS BELOW READ THE DEBUGGER RUN'S CAPTURES, because the second boot rewrote
    # FRAME.BIN and PENS.BIN on the drive, while `record` and `stats` are the PLAIN run's. That is
    # deliberate and it is exactly what `determinism_problems` above has just pinned: the two boots
    # produced the same picture and the same sixteen colours, so the vector is being read off the
    # same machine state the frames are. Without that pin this would be two moments compared as one.
    shift = MIS_ANCHOR_SHIFT if mode == "m5skew" else 0
    checks = m2_checks(record, stats, anchors, shift=shift, prefix=prefix)
    checks += m5_checks(our_vectors, our_pictures, anchors, prefix, excluded, compared,
                        shift=shift)
    checks += flash_checks(mode, record, anchors, prefix, excluded)
    report(mode, checks)

    if mode in M5_CONTROLS:
        preconditions = [(name, ok, detail) for name, ok, detail, key in checks if key is None]
        problems += [f"{name}: {detail}" for name, ok, detail in preconditions if not ok]
        if problems:
            raise SystemExit("FAIL: the control's own run is not sound, so its verdict says "
                             "nothing: " + "; ".join(problems))
        if mode == "m5fault":
            assert_only_the_faulted_pen(our_vectors, anchors, prefix, excluded, record)
        report_m5_control(mode, checks, m5_reachable(mode, anchors, prefix, checks, shift))
        return
    problems += [f"{name}: {detail}" for name, ok, detail, _ in checks if not ok]
    if problems:
        raise SystemExit("FAIL: " + "; ".join(problems))
    # THE CLAIM IS THE COMPARED SET, not the captured one. `vector_exclusions` returns both numbers
    # for exactly this line: saying "a 36-register vector" of a run that compares 20 of them would be
    # the headline outrunning the measurement.
    print(f"OK: {mode} — at {len(anchors)} anchors the reconstruction's framebuffer, its sixteen "
          f"pens, {compared} of a {original.VECTOR_REGISTERS}-register hardware-state "
          f"vector and the picture rendered at {list(RENDER_ANCHORS)} are all the shipped binary's")


def determinism_problems(record, plain):
    """OUR SIDE RUN TWICE MUST PRODUCE THE SAME TWO SURFACES, and the same anchor address.

    The debugger run is a second boot of the same binary on the same drive, so it re-writes M2.BIN,
    FRAME.BIN and PENS.BIN. Requiring the compared bytes to be identical costs nothing — the run was
    happening anyway — and it is what pins GEMDOS having placed the program at the same address in
    both, which is the premise the vector's breakpoint rests on. Only the reproducible fields are
    compared: `shim_vbl_ticks` and `poll16_calls` are wall-clock counts of a spin and are not."""
    again, why = read_m2()
    if again is None:
        return [f"the debugger run left no readable M2.BIN ({why}) — its captures cannot be "
                f"attributed to a run that got as far as its own dump"]
    problems = []
    # `capture_pc` is NOT compared here: `our_captures` does it the moment the second run's record
    # lands, which is before any vector is parsed. Here it would be unreachable — a moved address
    # means the breakpoint never fired and `hardware_vector` has already raised with a message about
    # the capture rather than about the placement, which is the fact that actually explains it.
    if again["image_base"] != record["image_base"]:
        problems.append(f"the two boots staged the image at different addresses "
                        f"({record['image_base']:#x} then {again['image_base']:#x})")
    # THE PENS ARE COMPARED MASKED and the raw bytes are not, which this check learned the hard way:
    # `capture_the_frame` reads the colour registers with the CPU, and the fourth bit of every gun
    # does not exist — it reads back as whatever was last on the bus, so two boots of one binary
    # legitimately differ there. Unmasked, this row reddened a pair of runs whose sixteen displayable
    # colours were identical. Same lesson as atari/README.md's on-target bug #2, one surface over.
    def masked(blob):
        """Every word of a multi-anchor pen capture, masked. `pen_words` takes one anchor's."""
        return [word & ST_PEN_MASK for word in struct.unpack(">%dH" % (len(blob) // 2), blob)]

    for name, same in ((M2_FRAME_FILE, lambda blob: blob), (M2_PENS_FILE, masked)):
        # BOTH SIDES GUARDED. `write_file` in the shim swallows a failed `Fcreate`, so a boot can
        # reach its own dump and still leave a capture unwritten — the case `m2_checks` already
        # guards on the plain side. Reading the debugger side unguarded raised FileNotFoundError out
        # of the middle of this check: a traceback in place of a verdict, after two full boots.
        if name not in plain:
            problems.append(f"the plain run wrote no {name}")
        elif not (DISK / name).exists():
            problems.append(f"the debugger run wrote no {name} although it reached its own dump — "
                            f"the vector's captures cannot be attributed to a run whose frames are "
                            f"missing")
        elif same((DISK / name).read_bytes()) != same(plain[name]):
            problems.append(f"{name} differs between our two boots of the same binary — the side "
                            f"the vector is taken from is not the side the frames were compared on")
    return problems


# ---- M6: THE ORDERED WRITE TIMELINE ---------------------------------------------------------------
#
# WHAT M6 ADDS OVER M2 AND M5, in one sentence: those compare WHERE the machine ended up at four
# instants, and this compares WHAT REACHED IT, in order, across all fifty-two frames. The instrument
# and its parser are original.py's — one spelling for both sides, §10's rule — and everything below
# is the reduction and the comparison.
TIMELINE_TRACE = original.TIMELINE_TRACE
timeline_events = original.timeline_events
FLASH_TIMER_EVENT = original.FLASH_TIMER_EVENT
PSG_SELECT_PORT, PSG_DATA_PORT = original.PSG_SELECT_PORT, original.PSG_DATA_PORT
BASE_HIGH_REG, BASE_MID_REG = original.BASE_HIGH_REG, original.BASE_MID_REG
PEN_FIRST_REG, PEN_LAST_REG = original.PEN_FIRST_REG, original.PEN_LAST_REG
TIMELINE_FILE = original.TIMELINE_FILE
base_state_after = original.base_state_after
# The image the shim runs the cores on is one flat array, and its LENGTH is what says whether a
# published base is still inside it. The kit owns that number; scraped, not restated.
IMAGE_SIZE = original.kit_constant("OS_IMAGE_SIZE")
# `move.w #$777,$ff8240.l` at $6f8 — colour 0 while the flash countdown still has frames to run.
FLASH_COLOUR_WHITE = wb("FLASH_COLOUR_WHITE")


def palette_loads(events):
    """Whole sixteen-pen loads, as (first position, position AFTER the last, the sixteen words).

    BOTH ENDS, because the caller that opens a window on a load needs the second one and rediscovering
    it costs a second definition of what a load's last write is. `set_palette` is sixteen separate
    calls and the vblank handler's PSG writes interleave with them, so the end is NOT the start plus
    sixteen.

    A load is $ff8240 through $ff825e in order, which is what `set_palette` emits — one call per
    colour, ../src/stage.c's own iteration. A partial burst is not a load and is dropped: it would
    be `flip_screen`'s flash writing colour 0 alone, which is not a palette change."""
    loads, pens, start = [], [], None
    for position, (register, value, _) in enumerate(events):
        if not PEN_FIRST_REG <= register <= PEN_LAST_REG:
            continue
        if register == PEN_FIRST_REG:
            pens, start = [], position
        elif start is None:
            continue          # a burst that did not begin at pen 0 is not a load
        pens.append(value)
        if register == PEN_LAST_REG and len(pens) == PALETTE_PENS:
            loads.append((start, position + 1, tuple(pens)))
            # START CLEARED WITH THE PENS, which is the sibling project's own bug in this function:
            # left set, any later burst reaching pen 15 without starting at pen 0 is filed at the
            # PREVIOUS load's position.
            pens, start = [], None
    return loads


def base_writes(events, buffers, opening_state):
    """`flip_screen`'s screen-base publications, classified.

    `opening_state` IS THE ADDRESS THE SHIFTER ALREADY HELD when the window opened, and it is a
    parameter rather than zero because the first write of a window is usually IDLE — both sides open
    mid-run, with a base already published, and `flip_screen`'s first of two byte writes is the one
    that changes nothing. Started from zero, that write instead looks like the window's first
    publication: measured, it gave our side 53 publications for 52 frames and put the whole sequence
    one flip out of phase with the shipped binary's, while the shipped side's own count came out
    right BY ACCIDENT (its stale first byte, $07, happens to name a real buffer on its own).

    THE SHIFTER'S BASE IS TWO BYTE-WIDE REGISTERS and a publication is therefore a SEQUENCE of
    writes, not one. Replaying them gives the address the shifter actually held after each, and each
    write falls into exactly one of three kinds:

      * a PUBLICATION — the state became one of the game's two screen buffers, and a different one
        from the buffer last published. This is the per-frame heartbeat, and its ordered list is
        what the two sides are compared on.
      * a TRANSIENT — the state became an address that is NEITHER buffer. Real on the machine: the
        shifter is pointed there until the next write. Counted, because the two sides do NOT have
        the same number of them and the difference is this port's (README.md §3).
      * an IDLE write — the byte written was the byte already there, so the state did not move.

    `buffers` is the pair of addresses this side's game draws from; the caller derives them from the
    staged image, which is where both sides' come from.

    Publications carry their POSITION in the stream as well as their address, because the play mode
    needs to know where the last one was and re-deriving that from a second loop is a second answer
    to "what is a publication" — one that counts buffer -> transient -> the SAME buffer as a flip
    while this one does not."""
    state, published, publications, transients, idle = opening_state, opening_state, [], 0, 0
    for position, (register, value, _) in enumerate(events):
        moved = original.apply_base_write(state, register, value)
        if moved is None:
            continue
        if moved == state:
            idle += 1
            continue
        state = moved
        if state not in buffers:
            transients += 1
        elif state != published:
            publications.append((position, state))
            published = state
    return publications, transients, idle


# The YM-2149 writes as (register, value), decoded from the select/data protocol — original.py's, so
# that the two sides' streams are read by one piece of code.
#
# A DATA WRITE WITH NO SELECT BEFORE IT DECODES TO REGISTER `None` RATHER THAN BEING DROPPED, and
# that is the point of decoding rather than comparing raw port writes: README.md §5 records that this
# port reproduces the original's select/data race — an interrupt landing between a select and its
# data writes the interrupted register's value into the interrupting one — and the surface named
# there as the one that would show it is this stream.
psg_stream = original.psg_stream


def psg_noise_reading(mode, prefix):
    """WHICH PSG REGISTERS THE SHIPPED BINARY DOES NOT REPRODUCE AGAINST ITSELF.

    M6 REFUSES TO RUN WITHOUT IT, for M5's reason one surface over: comparing a register the shipped
    binary writes differently on two of its own boots is not evidence in either direction, and a
    comparison that happened to pass on one would have passed by accident. `original.py psgnoise` is
    that measurement and it is STAMPED with the window it covers — a reading of a different number
    of frames is refused rather than allowed to license this one.

    ONE READING PER FABRICATION. The flashed boot is a different machine (README.md §10), so what a
    pair of unflashed boots reproduces licenses nothing about a flashed pair, and `m6flash` reads
    `FPSGNOISE.json`. That is `flashnoise`'s rule, one surface over.

    THE READING IS A FLOOR PLUS WHAT THIS MACHINE HAS SEEN. `PSG_REGISTERS_KNOWN_UNSTABLE` carries
    the registers already measured to move, committed, because the pairing is INTERMITTENT and
    `build/` is gitignored: a clone that drew a quiet pair would otherwise compare a register this
    project has already watched move, and go red for something neither binary did."""
    path = BUILD / (prefix + original.PSG_NOISE_FILE)
    if not path.exists():
        raise SystemExit(f"{path} is missing — `smoke.py {mode}` will not compare a PSG stream "
                         f"without knowing which of its registers are one boot's accident: run "
                         f"`python3 atari/original.py "
                         f"{'flashpsgnoise' if prefix else 'psgnoise'}` first (README.md §11)")
    return json.loads(path.read_text())


def our_timeline_window(events, image_base, staged_palette):
    """Our side's fifty-two frames, cut out of the whole run by two events the run itself gives.

    THE TWO SIDES' WINDOWS ARE CUT DIFFERENTLY AND THAT IS SAID RATHER THAN HIDDEN. The shipped
    binary is under a debugger, so original.py brackets it on `$4a0`'s own hit counter — the same
    anchor M2 and M5 use. Ours is not, so it is bracketed on two things the trace shows:

      * the OPEN is `publish_staged_pens` — the first full sixteen-pen load whose words are the
        staged palette. Everything before it is TOS's boot, including `publish_screen_base`, whose
        base write is not a frame's.
      * the CLOSE is the hand-back: the first base write that points the shifter OUTSIDE the image,
        which is `teardown`/`Setscreen` putting the desktop's screen back. Nothing the frame loop
        does can reach there — `capture_the_frame` bounds the front pointer to the image and the
        smoke reds if it is out of range — so the first such write is the end of the game's run.

    WHAT BINDS THE TWO WINDOWS TOGETHER is not the cutting but the result: both must contain the
    same number of buffer publications and the same publication sequence modulo `image_base`. A
    window cut in the wrong place changes that sequence's length or its phase."""
    loads = palette_loads(events)
    opened = next((end for _, end, pens in loads if pens == staged_palette), None)
    if opened is None:
        return None, None, (f"our run never loaded the staged palette — {len(loads)} full sixteen-pen "
                            f"load(s) in the trace and none of them is PENS.IMG's, so the window this "
                            f"timeline is over cannot be located")
    state, closed = 0, None
    for position, (register, value, _) in enumerate(events):
        moved = original.apply_base_write(state, register, value)
        if moved is None:
            continue
        state = moved
        if position > opened and not image_base <= state < image_base + IMAGE_SIZE:
            closed = position
            break
    if closed is None:
        return None, None, ("our run never pointed the shifter back outside the image — it did not "
                            "reach its own teardown, so the window has no end and the stream below "
                            "would carry whatever the machine did afterwards")
    return events[opened:closed], base_state_after(events[:opened]), None


def timeline_shape(events, buffers, opening_state, back_buffer, frames, label):
    """One side's window, reduced to a shape the other side's can be compared against."""
    tables = [pens for _, _, pens in palette_loads(events)]
    publications, transients, idle = base_writes(events, buffers, opening_state)
    return {
        "label": label,
        "expected": expected_base_shape(BASE_BYTES_PER_PUBLICATION[label], buffers, opening_state,
                                        back_buffer, frames),
        "loads": tables,
        # A load carrying the table already on the hardware. Zero on both sides here, and the number
        # the sibling project's 773-stomps bug drove into the hundreds — which is what `m6rearm`
        # reproduces on purpose so that this counter is shown able to move.
        #
        # IT UNDER-COUNTS BY EXACTLY ONE, STRUCTURALLY, AND THAT IS NOT ROUNDING. Redundancy is a
        # property of a consecutive PAIR, and the window opens immediately after the staged-palette
        # load that `our_timeline_window` anchors on — so the first load INSIDE the window has no
        # in-window predecessor, and its pair with the boot load is invisible here. Measured on
        # `m6rearm`: 52 loads, 51 redundant, where every one of the 52 carries the boot's own table.
        # Harmless for the assertion (the pinned value is ZERO, and one missed pair cannot turn a
        # non-zero count into zero) and stated because the two numbers differ by one for a reason.
        "redundant": sum(1 for before, after in zip(tables, tables[1:]) if before == after),
        "publications": [address for _, address in publications],
        "transients": transients,
        "idle_base_writes": idle,
        "psg": psg_stream(events),
    }


# HOW MANY BYTES EACH SIDE WRITES TO PUBLISH ONE BASE, and this is the only number here that is
# written down rather than derived — because it is the one a regression could change.
#
#   * the shipped binary writes TWO: `move.b $74d.l,$ff8201.l` then `move.b $74e.l,$ff8203.l`.
#   * ours writes FOUR, and §3 is why: the game's two byte writes each enter the translating sink,
#     and the sink must re-emit BOTH hardware bytes every time because the image offset can carry
#     out of the middle byte into the high one, so neither byte can be translated without the other.
BASE_BYTES_PER_PUBLICATION = {"ours": 4, "shipped": 2}
NO_REDUNDANT_LOADS = 0


def expected_base_shape(base_bytes, buffers, opening_state, back_buffer, frames):
    """What this side's base-write counts MUST be — DERIVED FROM ITS OWN TWO BUFFER ADDRESSES.

    Every number below used to be a constant, and every constant was the TOS 1.04 reading. EmuTOS
    put the image somewhere else and all three went wrong at once, which is the tell that they were
    one fact written down three times. The fact is arithmetic on the two addresses:

    TRANSIENTS. A publication writes the high byte and then the middle byte, so between them the
    shifter holds `(new high, old middle)`. That is a real address the machine is pointed at — but
    only if the high byte MOVED. The original's two buffers are `$070000` and `$078000`, which differ
    only in the middle byte, so its high-byte store writes `$07` over `$07` and no transient exists.
    Ours are `image_base + $70000` and `image_base + $78000`, which differ in the high byte too
    **iff the image base's middle byte carries** — measured on the frame builds, `0x4a700` under
    TOS 1.04 carries and `0x53100` under EmuTOS does not, so the same binary produces 52 transients
    on one ROM and none on the other. So: one per frame exactly when the two buffers' high bytes
    differ.

    PUBLICATIONS. One per frame, minus one if frame 1 publishes the address that was ALREADY on the
    shifter. That is not a fudge either: `flip_screen` swaps front and back before publishing, so
    frame 1 always publishes the staged BACK buffer, and whether that is a change depends on what
    the side's own entry left there. The shipped boot leaves `$070000` (the back buffer) at
    `$f90c`/`$f914`; `publish_screen_base` in our shim leaves the FRONT one. Hence the shipped
    binary's list is one shorter, and the entry ours has extra is the FIRST — which is what lets the
    comparison require everything after it to be the shipped binary's, address for address, so
    "dropped one and gained a stray one elsewhere" cannot add up and pass.

    IDLE WRITES are then whatever is left of the byte budget, which is what makes this a closed
    account rather than three independent guesses: every base byte a side writes is a publication, a
    transient, or a write that changed nothing."""
    budget = base_bytes * frames
    transients = frames if len({address >> 16 for address in buffers}) > 1 else 0
    publications = frames - (0 if opening_state != back_buffer else 1)
    return {"publications": publications, "transients": transients,
            "idle_base_writes": budget - publications - transients}
# No palette load at all inside the frame window, on either side: this game loads its palette when a
# stage loads and never again while one runs. It is `m6rearm` that makes the row non-vacuous.
NO_LOADS_IN_FRAMES = 0


def compare_timelines(ours, theirs, image_base, frames, noise):
    """Assert the two shapes against each other and against the per-frame pins.

    Returns the same `(name, ok, detail)` rows the rest of this file reports, so `m6rearm` can
    invert its verdict over named rows rather than over a bare boolean."""
    checks = []
    mine, shipped = ours["publications"], theirs["publications"]
    translated = [address - image_base for address in mine]
    # HOW FAR OUR LIST LEADS THEIRS IS DERIVED, not assumed: it is the difference between the two
    # sides' own expected publication counts, which `expected_base_shape` computes from what each
    # side's entry left on the shifter. Written down, this offset would have been the one number
    # that still silently absorbed a real divergence.
    lead = ours["expected"]["publications"] - theirs["expected"]["publications"]
    checks.append((
        "the frame heartbeat", translated[lead:] == shipped and len(mine) - len(shipped) == lead,
        f"ours {len(mine)} buffer publications over {frames} frames, shipped {len(shipped)}; past "
        f"our leading {lead} the two agree address for address — ours {[hex(a) for a in mine[:3]]} "
        f"= image + {[hex(a) for a in translated[:3]]}, shipped {[hex(a) for a in shipped[:3]]}"))
    for field in ("publications", "transients", "idle_base_writes"):
        got = (len(ours[field]) if field == "publications" else ours[field],
               len(theirs[field]) if field == "publications" else theirs[field])
        want = (ours["expected"][field], theirs["expected"][field])
        checks.append((f"base {field.replace('_', ' ')}", got == want,
                       f"ours {got[0]}, shipped {got[1]}; each side's own two buffer addresses "
                       f"require {want[0]}/{want[1]} (see expected_base_shape)"))
    for shape in (ours, theirs):
        checks.append((f"{shape['label']}: palette loads inside the frames",
                       len(shape["loads"]) == NO_LOADS_IN_FRAMES,
                       f"{len(shape['loads'])} full sixteen-pen load(s); this game loads its palette "
                       f"when a stage loads and never again while one runs"))
        checks.append((f"{shape['label']}: no load repeats the table already on the chip",
                       shape["redundant"] == NO_REDUNDANT_LOADS,
                       f"{shape['redundant']} redundant load(s) — the 773-stomps shape, which no "
                       f"snapshot in this project can see"))
    checks.append(compare_psg_streams(ours["psg"], theirs["psg"], frames, noise))
    return checks


def compare_psg_streams(ours, theirs, frames, noise):
    """The shipped binary's PSG writes must be an exact PREFIX of ours, register and value in order.

    A PREFIX AND NOT AN EQUALITY, AND THE DIRECTION IS MEASURED RATHER THAN CHOSEN. The music driver
    is `snd_music_tick`, called from the vblank handler, so what advances the stream is VBLANKS —
    while what bounds this window is FRAMES. The two sides do not spend the same number of vblanks on
    a frame and are not required to: measured, the shipped binary takes about two and the
    reconstruction about eleven and a half. So over the same fifty-two frames our stream is the
    longer one, and every write the shipped binary made must be the write we made at that point in
    the sequence.

    THIS IS THE PROJECT'S FIRST ON-TARGET ASSERTION ABOUT SOUND. README.md §10 records why a
    snapshot could not supply one — the YM file's music registers move between two boots of the
    SHIPPED BINARY ITSELF, so comparing them proves nothing in either direction — and names this
    stream as the surface that can.

    THE FLOOR IS THE SHIPPED SIDE'S OWN COUNT, not a number written here: a prefix relation is
    satisfied by a stream of length one, and a regression that silenced the chip after its first
    write would otherwise print an identical-looking success.

    AND IT IS COMPARED OVER THE REGISTERS THE SHIPPED BINARY REPRODUCES, which is `psgnoise`'s
    reading rather than a list written here. MEASURED, and this row is why the reading exists: two
    boots of the shipped binary differ in 42 of 1155 writes, all of them channel A's tone period
    (registers 0 and 1) and all inside the first eleven frames. Comparing those would have been
    comparing which vblank a floppy boot finished on. The excluded set is PRINTED — a check quietly
    dropped from a comparison is a check nobody is running, which is M1's `machine_driven` lesson."""
    excluded = set(noise["moved"])
    ours = [(register, value) for register, value in ours if register not in excluded]
    theirs = [(register, value) for register, value in theirs if register not in excluded]
    if len(theirs) < frames:
        return ("timeline sound", False,
                f"the shipped binary issued only {len(theirs)} PSG writes over {frames} frames — "
                f"fewer than one a frame, so its own stream is too short to be evidence of anything "
                f"(measured, it makes 22 a frame)")
    if len(ours) < len(theirs):
        return ("timeline sound", False,
                f"we issued {len(ours)} PSG writes against the shipped binary's {len(theirs)} — a "
                f"prefix cannot be shorter than what it is a prefix of, and our window holds MORE "
                f"vblanks than theirs, so this is the chip going quiet rather than a direction swap")
    diverged = next((i for i in range(len(theirs)) if ours[i] != theirs[i]), None)
    if diverged is None:
        return ("timeline sound", True,
                f"the shipped binary's {len(theirs)} PSG writes are an exact prefix of our "
                f"{len(ours)} — register and value, in order — over registers "
                f"{noise['reproducible']}; registers {noise['moved']} are EXCLUDED because two boots "
                f"of the shipped binary itself write them differently "
                f"({noise['differing_positions']} differing write(s) over {noise['pairs']} measured "
                f"pair(s) of {noise['writes']})")
    reg, value = ours[diverged]
    their_reg, their_value = theirs[diverged]
    return ("timeline sound", False,
            f"PSG write {diverged} of {len(theirs)} differs — ours register {reg} = {value:#04x}, "
            f"shipped register {their_reg} = {their_value:#04x}")


def flash_order_checks(events, seed, label, watch_predates_frames):
    """`flip_screen`'s last pair, in the order the bus saw it.

    THE MUTANT THIS EXISTS FOR changes no value at all. `wr16(image + WB_FLASH_TIMER, flash)` and
    `shifter_palette_write(WB_FLASH_PEN, ...)` are adjacent statements whose argument is the
    already-decremented local, so swapping them writes the same word to RAM and the same colour to
    the chip — only later. `../STATUS.md` measures it surviving the whole differential suite and
    every snapshot this directory takes; this row is the only thing anywhere that can see it, and
    what it sees is which of the two writes reached the bus first.

    THE RAM HALF IS A VALUE-CHANGE BREAKPOINT, folded into the same stream by
    `original.timeline_events` — Hatari has no RAM-write trace, and an instruction-boundary probe is
    one instruction coarser than the bus, which is enough because the two writes are adjacent.

    `seed` frames of countdown produce `seed` pairs: white while the timer still has frames to run,
    black on the frame it reaches zero.

    `watch_predates_frames` IS A PREMISE GUARD ON THE INSTRUMENT, and the two sides need different
    ones because the watch is installed differently. On the shipped side it goes into the same
    action file as the debugger's poke, after it, so its baseline is the seed and it never sees that
    write. On ours it is installed on a vblank count, so it MUST see `arm_the_flash` write the seed —
    and if it did not, it was installed after the frames began and the ordering below would be a
    reading of whichever decrements happened to fall inside it."""
    countdown = [(position, value) for position, (register, value, _) in enumerate(events)
                 if register == FLASH_TIMER_EVENT]
    values = [value for _, value in countdown]
    checks = [(f"{label}: the countdown ran", values[-seed:] == list(range(seed - 1, -1, -1)),
               f"the watched word took {values} — the last {seed} must be the countdown "
               f"{list(range(seed - 1, -1, -1))}")]
    if watch_predates_frames:
        checks.append((f"{label}: the watch was live before the first frame",
                       values[:1] == [seed],
                       f"the watch's first event is {values[:1]}, and it has to be arm_the_flash "
                       f"writing the seed {seed} — otherwise it was installed after the countdown "
                       f"started and the order below is a reading of an unknown window"))
    # AN EMPTY COUNTDOWN MUST NOT REPORT ORDERED. `ordered` starts True and the loop below is what
    # can falsify it, so a watch that produced no events at all — Hatari's line wording moved, or the
    # chained `:file` install silently failed — would report the row this project's last shifter-sink
    # mutant dies to as a PASS on zero data. The neighbouring rows would red, but the row that
    # carries the claim has to red on its own.
    ordered = len(countdown[-seed:]) == seed
    detail = [] if ordered else [f"only {len(countdown)} watch event(s), needed {seed}"]
    for position, value in countdown[-seed:]:
        # The colour write that belongs to this decrement is the NEXT write to colour 0 — and in the
        # correct order there is nothing else between them. What the mutant does is put that write
        # BEFORE the decrement, so the pen 0 write that follows belongs to the NEXT frame and the
        # last decrement has none after it at all.
        after = next((index for index in range(position + 1, len(events))
                      if events[index][0] == PEN_FIRST_REG), None)
        want = FLASH_COLOUR_WHITE if value else 0
        got = events[after][1] if after is not None else None
        ordered &= got == want
        detail.append(f"timer:={value} then colour0:="
                      + ("none" if got is None else f"{got:#05x}") + f" (want {want:#05x})")
    checks.append((f"{label}: the timer store reaches the bus BEFORE the colour",
                   ordered, "; ".join(detail)))
    return checks


def shipped_timeline(prefix, mode):
    """The shipped side's window, read back off disk, with its producer named if it is missing."""
    path = BUILD / (prefix + TIMELINE_FILE)
    if not path.exists():
        raise SystemExit(f"{path} is missing — `smoke.py {mode}` compares an ordered stream against "
                         f"the shipped binary's and cannot compute one: run `python3 atari/"
                         f"original.py {'flashtimeline' if prefix else 'timeline'}` first")
    record = json.loads(path.read_text())
    # The debugger writes them as lists; the rest of this file compares tuples against tuples.
    return ([tuple(event) for event in record["events"]], record["frames"],
            record["base_at_open"])


# WHICH VBLANK THE FLASH WATCH IS INSTALLED ON, and why it is a count rather than an event. Hatari
# refuses `b ($addr).w` for a RAM address at --parse time — measured: "invalid address" for
# $4ad14 at power-on, while $ffff9202 in its own documentation parses — because the machine has not
# sized its memory yet. So the watch is CHAINED: a breakpoint that costs nothing installs it once the
# machine is up. 100 is well after TOS's memory sizing and well before the program is Pexec'd (~700),
# and the run does not have to be trusted about that: `flash_order_checks`' premise guard requires
# the watch to have seen `arm_the_flash` write the seed, which happens before frame one.
M6_WATCH_INSTALL_VBL = 100


def flash_watch_script(directory, image_base):
    """The two-stage debugger script that puts our image's WB_FLASH_TIMER into the timeline."""
    installer = directory / "M6WATCH.INI"
    installer.write_text(original.flash_watch_command(image_base + wb("FLASH_TIMER")) + "\ncont\n")
    chain = directory / "M6CHAIN.INI"
    chain.write_text(f"b VBL > {M6_WATCH_INSTALL_VBL} :once :quiet :file {installer}\n")
    return chain


def mode_m6(mode, prefix, faulted):
    """The ordered write timeline, and — for `m6flash` — `flip_screen`'s last pair in bus order.

    `faulted` is `m6rearm`, whose verdict is INVERTED over the palette rows: it re-publishes the
    staged palette after every frame, which changes no value anywhere, so a run in which those rows
    still pass would mean the timeline is not reading what reaches the chip. Everything else it
    asserts NORMALLY — `mode_m2`'s lesson, that a control has to know its own run was healthy before
    its inversion means anything."""
    theirs_events, frames, their_opening = shipped_timeline(prefix, mode)
    noise = psg_noise_reading(mode, prefix)
    if noise["frames"] != frames:
        raise SystemExit(f"the PSG reproducibility reading covers {noise['frames']} frames and this "
                         f"comparison is over {frames} — a measurement of a different window cannot "
                         f"license this one: re-run `python3 atari/original.py "
                         f"{'flashpsgnoise' if prefix else 'psgnoise'}`")
    flashing = prefix != ""
    prg = BUILD / M6_BUILDS[mode]
    status, log, rom = run_hatari(prg, run_vbls=M2_RUN_VBLS, trace=TIMELINE_TRACE,
                                  log_name=f"hatari-{mode}.log")
    print(f"-- {mode}: TOS={rom or 'bundled EmuTOS'} hatari exit={status} "
          f"(full log in {OUT / ('hatari-%s.log' % mode)})")
    problems = check_machine_health(status, log)
    stats, why = read_stats()
    m2, m2_why = read_m2()
    for missing in (why, m2_why):
        if missing:
            problems.append(missing)
    if stats is None or m2 is None:
        report(mode, [])
        raise SystemExit("FAIL: " + "; ".join(problems))
    image_base = stats["image_base"]

    our_events, why = timeline_events(log.splitlines())
    if why:
        raise SystemExit("FAIL: " + why)
    window, opening_state, why = our_timeline_window(our_events, image_base, staged_palette())
    if why:
        raise SystemExit("FAIL: " + why)

    # THE BUFFERS COME FROM THE STAGED IMAGE — the same two longwords on both sides, because it is
    # the same image; ours are translated by `image_base` and the shipped binary's are not, which is
    # the whole of §3 in one line. `flip_screen` swaps before it publishes, so frame 1's target is
    # the staged BACK buffer on either side.
    buffers = {image_base + staged("SCREEN_FRONT"), image_base + staged("SCREEN_BACK")}
    their_buffers = {staged("SCREEN_FRONT"), staged("SCREEN_BACK")}
    ours = timeline_shape(window, buffers, opening_state,
                          image_base + staged("SCREEN_BACK"), frames, "ours")
    theirs = timeline_shape(theirs_events, their_buffers, their_opening,
                            staged("SCREEN_BACK"), frames, "shipped")
    checks = compare_timelines(ours, theirs, image_base, frames, noise)

    order_checks = []
    if flashing:
        checks += m6_flash_order(prg, image_base, theirs_events, m2["flash_timer_at_entry"])
    # THE RUN'S OWN HEALTH, ASSERTED RATHER THAN JUST READ. `m6` reads STATS.BIN for `image_base` and
    # M2.BIN for the flash seed and, in its first draft, asserted nothing from either — which is the
    # defect `m2_checks` already records having had once: a mode routed past the record leaves every
    # read-back, including all four teardown restores, unchecked. A binary whose teardown stopped
    # restoring a vector would red under `m2` and stay green here, on the same .PRG.
    checks += readback_checks(stats)
    report(f"{mode} (re-arm control — the PALETTE rows MUST fail)" if faulted else mode,
           [(name, ok, detail) for name, ok, detail in checks])
    print(f"   image at {image_base:#x}; our window {len(window)} writes over {frames} frames, "
          f"the shipped binary's {len(theirs_events)}")

    # ONLY OUR OWN PALETTE ROWS ARE INVERTED, and the distinction is the point rather than tidiness:
    # `m6rearm` re-arms the palette on OUR side, so the shipped binary's two palette rows are checks
    # this control does not touch and must therefore still PASS. Exempting them from both halves —
    # not required to fail, not required to pass — would leave two checks nobody was running, which
    # is M1's `machine_driven` lesson. Measured: written that way first.
    inverted_rows = [name for name, _, _ in checks
                     if name.startswith(f"{ours['label']}:")
                     and ("palette loads" in name or "repeats the table" in name)]
    if not faulted:
        problems += [f"{name}: {detail}" for name, ok, detail in checks if not ok]
        if problems:
            raise SystemExit("FAIL: " + "; ".join(problems))
        print(f"OK: {mode} — {frames} frames of writes in the order they reached the machine"
              + (", and flip_screen's last pair in bus order" if flashing else ""))
        return

    problems += [f"{name}: {detail}" for name, ok, detail in checks
                 if not ok and name not in inverted_rows]
    # "INVISIBLE TO EVERY SNAPSHOT" IS MEASURED HERE, NOT CLAIMED BELOW. The whole argument for
    # having a timeline is that this build is one no other surface can tell from `m2`, and a control
    # that only showed the timeline going red would leave that half unexercised — the round's own
    # standing lesson, that a claim made on four surfaces and executed on none is not a result. The
    # run already wrote M2.BIN, FRAME.BIN and PENS.BIN, so the frame differential costs nothing and
    # it must PASS: fifty-two redundant palette loads reached the chip and the pictures and the pens
    # at all four anchors are still the shipped binary's.
    snapshots = m2_checks(m2, stats, original.anchor_frames())
    report("m6rearm: the snapshots the control must NOT move", [row[:3] for row in snapshots])
    problems += [f"snapshot {name}: {detail}" for name, ok, detail, _ in snapshots if not ok]
    if problems:
        raise SystemExit("FAIL: the control's own run is not sound, so its inverted verdict says "
                         "nothing: " + "; ".join(problems))
    if not inverted_rows:
        raise SystemExit("FAIL: the control has no row to invert — its own palette rows are not in "
                         "the check list, so it cannot fail and proves nothing")
    held = [name for name, ok, _ in checks if ok and name in inverted_rows]
    if held:
        raise SystemExit("FAIL: the re-arm control passed " + ", ".join(held) + " — a palette load "
                         "per frame that changes no value reached the chip and the timeline did not "
                         "see it, which is the 773-stomps shape this row exists for")
    print(f"OK: re-publishing the palette every frame reddens the timeline and nothing else — "
          f"{ours['redundant']} redundant loads over {frames} frames, invisible to every snapshot")


def m6_flash_order(prg, image_base, theirs_events, seed):
    """Boot our side a SECOND time with WB_FLASH_TIMER watched, and order both sides' last pair.

    A SECOND BOOT BECAUSE THE WATCH NEEDS AN ADDRESS THE FIRST ONE REPORTS — `image_base` is where
    GEMDOS put the program, and the debugger cannot be told a RAM address before the machine has
    sized its memory (M6_WATCH_INSTALL_VBL). M5 boots our side twice for the same shape of reason,
    and as there the two boots are REQUIRED TO AGREE: a different image base means the breakpoint
    watched somebody else's memory."""
    with tempfile.TemporaryDirectory() as tmp:
        chain = flash_watch_script(Path(tmp), image_base)
        status, log, _ = run_hatari(prg, run_vbls=M2_RUN_VBLS, trace=TIMELINE_TRACE, parse=chain,
                                    log_name="hatari-m6flash-watch.log")
    unhealthy = check_machine_health(status, log)
    checks = [("the watched boot was healthy", not unhealthy, "; ".join(unhealthy) or "clean")]
    again, why = read_stats()
    checks.append(("both boots staged the image at one address",
                   again is not None and again["image_base"] == image_base,
                   f"{image_base:#x} then {'no record (%s)' % why if again is None else '%#x' % again['image_base']}"))
    ours, why = timeline_events(log.splitlines(), image_base + wb("FLASH_TIMER"))
    if why:
        return checks + [("our watched stream parsed", False, why)]
    return (checks + flash_order_checks(ours, seed, "ours", watch_predates_frames=True)
            + flash_order_checks(theirs_events, seed, "shipped", watch_predates_frames=False))


def staged_palette():
    """The sixteen pens the frame build stages — the ORIGINAL's own, off its post-boot machine."""
    blob = (DISK / "PENS.IMG").read_bytes()
    return tuple(struct.unpack(">%dH" % PALETTE_PENS, blob))


PLAY_RUN_VBLS = 12000
# A PAL machine's vertical blank, and the only clock a `--run-vbls` figure can be turned into seconds
# by. `--monitor rgb` is what every mode here boots with, so 50 rather than 60 or 71.
VBLANKS_PER_SECOND = 50
# How far into the run the LAST flip has to be for the play build to count as still running. The
# build has no end — `run_frames`' count and its watchdog are both lifted — so what is asserted is
# not that it finished but that it had not stopped: measured, its last buffer publication is 53 log
# lines from the end of a 258,617-line trace, i.e. it was still flipping when --run-vbls cut it off.
# The floor is loose on purpose. What it has to separate is "flipping at the end" from "stopped
# somewhere in the middle", and the gap between those is the whole run — a tight floor would instead
# be measuring how many PSG writes happen to follow the last flip before the emulator exits, which
# is a quantity nothing controls.
PLAY_STILL_RUNNING_FRACTION = 0.99


def displayed_buffers(events):
    """The two addresses the shifter actually DISPLAYED, found in the run rather than computed.

    `mode_play` cannot ask the program where its image is — the play build never leaves the frame
    loop and so never writes STATS.BIN — so the buffers have to come out of the trace. They are the
    two states the shifter DWELLS in: a transient is superseded by the very next base write and a
    buffer is held for a whole frame, so ranking states by how many events elapse while each is
    current separates them by orders of magnitude rather than by a threshold.

    AND THE PAIR IS THEN PINNED, which is what makes this a measurement instead of a guess: the two
    winners must be exactly `WB_SCREEN_FRONT - WB_SCREEN_BACK` apart, the same distance the staged
    image's own two longwords are. That identifies them as the game's buffers without knowing where
    GEMDOS put the image."""
    dwell, state, since = {}, 0, 0
    for position, (register, value, _) in enumerate(events):
        moved = original.apply_base_write(state, register, value)
        if moved is None:
            continue
        dwell[state] = dwell.get(state, 0) + position - since
        state, since = moved, position
    dwell[state] = dwell.get(state, 0) + len(events) - since
    ranked = sorted(dwell, key=dwell.get, reverse=True)[:2]
    if len(ranked) < 2:
        return None, "the play run pointed the shifter at fewer than two addresses — it never flipped"
    apart = abs(ranked[0] - ranked[1])
    want = abs(staged("SCREEN_FRONT") - staged("SCREEN_BACK"))
    if apart != want:
        return None, (f"the two addresses the shifter dwelt in, {hex(ranked[0])} and "
                      f"{hex(ranked[1])}, are {apart:#x} apart and the staged image's two screen "
                      f"buffers are {want:#x} apart — so they are not the game's two buffers and "
                      f"counting flips between them would be counting something else")
    return set(ranked), None


def mode_play():
    """The build a person plays, booted headless: does it keep running, and for how long?

    WHAT THIS CAN ASSERT AND WHAT IT CANNOT, said plainly because the interesting half is the second.
    It can assert that the frame loop keeps turning without either bound the headless modes give it,
    that the machine stays healthy for four minutes of emulated time, and how many frames that is.
    It CANNOT assert that the stick moves him: a headless run cannot press one, the ACIA handler's
    two joystick arms therefore still have never executed, and `atari/run.sh` is the mechanism that
    discharges them. Joust's play row makes the same split and calls it partial by construction."""
    prg = BUILD / M6_BUILDS["play"]
    status, log, rom = run_hatari(prg, run_vbls=PLAY_RUN_VBLS, trace=TIMELINE_TRACE,
                                  log_name="hatari-play.log")
    print(f"-- play: TOS={rom or 'bundled EmuTOS'} hatari exit={status} --run-vbls {PLAY_RUN_VBLS} "
          f"(full log in {OUT / 'hatari-play.log'})")
    problems = check_machine_health(status, log)
    events, why = timeline_events(log.splitlines())
    if why:
        problems.append(why)
    # WHERE the last flip is, not just how many there were: a build that ran a hundred frames and
    # then hung would pass a bare count. The position is measured in EVENTS rather than in log lines,
    # because the event stream is the only clock a run that writes no record has, and it keeps
    # ticking (the vblank handler's PSG writes) for as long as the machine is alive.
    buffers, why = displayed_buffers(events)
    if why:
        problems.append(why)
        buffers = set()
    # THE SAME `base_writes` THE DIFFERENTIAL USES, so "a buffer publication" has ONE definition in
    # this file. Rolling a second replay here was the first draft's mistake and the two rules did not
    # agree: this one would have counted buffer -> transient -> the SAME buffer as a flip, and our
    # side emits a transient every frame by construction, so the play row's headline number was
    # produced by a rule no other check uses. The opening state is 0 because a play run is read from
    # power-on rather than from a window.
    publications, _, _ = base_writes(events, buffers, 0)
    flips = len(publications)
    last_at = publications[-1][0] if publications else 0
    reach = last_at / max(len(events) - 1, 1)
    headless_frames = max(original.anchor_frames())
    checks = [
        ("the frame loop kept turning", flips > headless_frames,
         f"{flips} buffer publications over {PLAY_RUN_VBLS} vblanks, alternating "
         f"{sorted(hex(address) for address in buffers)} — the headless frame build stops itself at "
         f"{headless_frames}"),
        ("...and was still turning when the run was cut off", reach >= PLAY_STILL_RUNNING_FRACTION,
         f"the last one is {reach:.4f} of the way through the {len(events)}-event stream (floor "
         f"{PLAY_STILL_RUNNING_FRACTION}); a build that hung would leave it early"),
        # NOT "by construction", and the difference is a claim this row had to give up. The frame
        # count and the watchdog are gone in this build, but `run_frames`' THIRD exit is not: a frame
        # in which `game_key_actions` takes one of its three endings returns a `loop_ending` that is
        # not WB_KEY_ACTIONS_RETURNED and the loop breaks, hands the machine back and writes the
        # record. This headless run injects no input, so no ending can be reached and the file is
        # absent — which is what is asserted. A PERSON at `run.sh` can reach one, and that is M3's
        # owed milestone rather than a defect in this row.
        # MEASURED OVER THIS WINDOW, NOT PROVEN. Three of the frame loop's five endings are keys and
        # a headless run presses none; the other two are the PLAYER's — a life spent, a game-over box
        # expiring — and a run that pressed nothing can still reach those if the game kills him. Over
        # PLAY_RUN_VBLS on the staged frame image it does not, and that is what this row says.
        ("this run reached no ending (measured over its window)", not (DISK / STATS_FILE).exists(),
         "no key is pressed and no stick is moved, so game_key_actions' three endings cannot fire; "
         "the player's own two can in principle and do not here — the loop never breaks and the "
         "shim never hands the machine back"),
    ]
    # ...AND IF ONE EVER DOES APPEAR, SAY WHICH EXIT MADE IT. A record here means an ending fired,
    # which under a headless run means the premise above is wrong; under `run.sh` with a person at
    # the keys it is M3's evidence. Either way the answer is a FIELD — `loop_ending` names which of
    # the three endings ran — rather than something inferred from a frame count that cannot tell
    # them apart.
    ended, _ = read_m2()
    if ended is not None:
        print(f"   NOTE a record exists: game_main_loop ended with loop_ending="
              f"{ended['loop_ending']} after {ended['frames_run']} frames — one of "
              f"game_key_actions' three endings fired (../include/game.h names them)")
    report("play", checks)
    print(f"   {flips} frames in {PLAY_RUN_VBLS} vblanks = "
          f"{flips / (PLAY_RUN_VBLS / float(VBLANKS_PER_SECOND)):.2f} frames a second of emulated "
          f"time, on an 8 MHz 68000")
    problems += [f"{name}: {detail}" for name, ok, detail in checks if not ok]
    if problems:
        raise SystemExit("FAIL: " + "; ".join(problems))
    print("OK: play — the reconstruction runs indefinitely; run it with a screen: bash atari/run.sh")


# ---- M3: THE THREE EXITS, DRIVEN, AND THE MACHINE HANDED BACK ------------------------------------
#
# WHAT M3 CLAIMS: `game_key_actions` has three endings that are not returns — they pop
# `game_main_loop`'s return address and `jmp` into the boot chain (../include/game.h) — and all three
# are made to happen ON THE MACHINE, one run each, with the reconstruction reporting WHICH by the
# `loop_ending` field of its own record. Then the program exits, and what the machine does AFTER that
# is asserted too: this is Joust's M3 discipline, where an incomplete hand-back is invisible until
# TOS is running on with whatever the shim left hooked.
#
# HOW AN ENDING IS DRIVEN WITHOUT AN INPUT DEVICE. Each arm's condition is a word or a byte in the
# image, so a debugger poke at the right instant is the whole mechanism. The instant is
# `capture_the_frame`'s Nth arrival — the shim calls it once per anchor frame and nowhere else, which
# is the anchor M5 already photographs on — so the poke lands at the END of a known frame and the
# ending fires at the TOP of the next one, where `game_key_actions` reads.
#
# WHY THE FRAME BUILD AND NOT THE PLAY BUILD, stated because the play build is the one a person
# reaches an ending on. A poke needs the image's run-time address, and the only honest source of it
# is the binary's own report — `M2.BIN`'s `image_base`, which is written when the run ends. The play
# build writes no record until an ending fires, so there is nothing to aim the first poke at; the
# frame build reports `image_base` AND `capture_pc` about itself on an undriven run, and the driven
# run re-reports both and must agree. The exit path is not the play build's difference: `run_frames`'
# third exit, `teardown`, `Pterm` and both records are the same code in both (wonderboy_main.c's
# SMOKE_PLAY block changes the frame count and the watchdog and nothing else).
#
# THE NEGATIVE CONTROL IS THE FIRST PASS, and it is not a separate run bolted on: the undriven boot
# that measures `image_base` must report `loop_ending` = WB_KEY_ACTIONS_RETURNED and every one of its
# fifty-two frames. So each M3 run contains, by construction, one run in which no ending was driven
# and the loop did not end — which is what makes the three driven ones mean something.

# Which arrival at `capture_the_frame` carries the poke. The SECOND, so that a run has already
# completed a whole frame under the debugger before anything is injected, and so that the frame the
# ending fires on is early enough to leave the whole rest of `--run-vbls` as tail.
M3_POKE_ANCHOR = 2
M3_RUN_VBLS = M2_RUN_VBLS
# WHERE THE MACHINE IS INSPECTED FROM OUTSIDE: chained off the program's OWN `Pterm`, not off a
# vblank count. `wonderboy_os.s` exits with `clr.w -(%sp) / trap #1`, i.e. GEMDOS function 0, and a
# breakpoint on that opcode is the exit itself; the two readings then hang off it as "the next
# vblank" and "twenty vblanks later".
#
# AN ABSOLUTE COUNT WAS TRIED FIRST AND THE HAND-BACK CONTROL KILLED IT. With the inspections at
# 8000 and 8500 of 9000 — as deep in the tail as the run allows — `m3fault` failed intermittently on
# TOS 1.04 with a verdict that read like the control not working: the ending row red, `loop_ending`
# = 0 over fifty-two frames, and every hand-back row GREEN. What happens is the control's own point
# taken one step further. The still-hooked level-4 vector runs on memory GEMDOS has taken back; on
# that ROM it took the machine down; TOS RESET, which restores the vectors and restarts the frame
# clock, and `--auto` then re-ran `WB.PRG` with the `:once` poke breakpoint long spent, so the
# undriven second run overwrote the record. **A reset restores exactly what the control asserts must
# stay broken**, and moving the count nearer the exit (3000/3500) did not help, because the crash
# and the reset happen within tens of vblanks of `Pterm`. Anchoring on the exit does: at +1 vblank
# nothing has had time to fall over, and the ordering against the exit stops being a margin to
# measure and becomes structural.
#
# `--run-vbls` is unchanged, so the machine-health scan still covers the whole long tail.
GEMDOS_PTERM0 = 0
# WHICH VBLANK AFTER `Pterm` THE SECOND FRAME-CLOCK READING IS TAKEN ON. One reading cannot show
# motion and two adjacent ones would show it as +1; twenty is a fifth of a second of emulated time
# and still lands before a crashed machine has been reset.
M3_TAIL_STEPS = 20
# ...AND HOW FAR APART THE TWO READINGS THEREFORE ARE, which is one less, because the first is taken
# at `Pterm`+1 and not at `Pterm` itself. Derived rather than written down: an off-by-one here is a
# label that disagrees with the +19 every run prints, and a reader checking the docs against the
# output finds the docs wrong about the instrument.
M3_TAIL_GAP = M3_TAIL_STEPS - 1

# WHERE EACH ENDING'S `jmp` GOES, from ../include/game.h's own comments on the WB_KEY_ACTIONS_* codes.
# Not asserted on target and not reached: the boot chain is unported, so the reconstruction REPORTS
# the transfer in place of making it. Carried here so a row that names an ending names its target.
UNWIND_SEQUENCE = 0xe5ba        # ROUND_END and LEVEL_SKIP
UNWIND_DATA_DISK = 0xe494       # QUIT, via the music fade

VEC_LEVEL4_VBL = c_constant("VEC_LEVEL4_VBL")
VEC_MFP_ACIA = c_constant("VEC_MFP_ACIA")
# TOS's own frame counter, incremented by ITS vertical-blank handler and by nothing else — the
# system variable `_frclock`. It is the liveness half of the hand-back: a program that never gave the
# level-4 vector back leaves this frozen, whatever else the machine appears to be doing. Not scraped
# from anywhere, because it is TOS's number and this project defines none of TOS.
TOS_FRCLOCK = 0x466

M3_POKE_BEACON = "M3_POKE"
M3_EXIT_BEACON = "M3_EXIT"
M3_TAIL_BEACONS = ("M3_TAIL_A", "M3_TAIL_B")
# What each capture is, in one place: the debugger writes these beside the script and the reader
# below names the moment rather than the filename when one is missing.
M3_VBL_VECTOR_RUNNING = "M3VBLIN.BIN"
M3_ACIA_VECTOR_RUNNING = "M3ACIAIN.BIN"
M3_VBL_VECTOR_AFTER = "M3VBLOUT.BIN"
M3_ACIA_VECTOR_AFTER = "M3ACIAOUT.BIN"
M3_CLOCK_EARLY = "M3CLKA.BIN"
M3_CLOCK_LATE = "M3CLKB.BIN"
M3_CAPTURES = ((M3_VBL_VECTOR_RUNNING, "$70 while the reconstruction owned the machine"),
               (M3_ACIA_VECTOR_RUNNING, "$118 while the reconstruction owned the machine"),
               (M3_VBL_VECTOR_AFTER, "$70 in the tail after the program exited"),
               (M3_ACIA_VECTOR_AFTER, "$118 in the tail after the program exited"),
               (M3_CLOCK_EARLY, "TOS's frame clock at the first tail inspection"),
               (M3_CLOCK_LATE, "TOS's frame clock at the second"))

# One ending: which arm, what it returns, where the original's `jmp` goes, and the image words whose
# values ARE its condition. `poke` is `original.poke_byte` or `poke_word` — the width comes FIRST in
# Hatari's memory-write command, which is a documented trap in ../STATUS.md rather than a detail.
M3Poke = collections.namedtuple("M3Poke", "offset poke value what")
M3Ending = collections.namedtuple("M3Ending", "tag arm code unwind pokes why")

M3_ENDINGS = (
    M3Ending("round", "WB_KEY_ACTIONS_ROUND_END", wb("KEY_ACTIONS_ROUND_END"), UNWIND_SEQUENCE,
             (M3Poke(wb("ROUND_END_RELOAD_REQUEST"), original.poke_word,
                     wb("ROUND_END_RELOAD_REQUEST_SET"), "the round-end reload request, raised"),),
             "$53e's first arm, and it outranks every key: the round bonus at $e032 raises the "
             "request word when its countdown finishes, and this consumes it, CLEARS it and unwinds"),
    M3Ending("skip", "WB_KEY_ACTIONS_LEVEL_SKIP", wb("KEY_ACTIONS_LEVEL_SKIP"), UNWIND_SEQUENCE,
             (M3Poke(wb("KEY_SEQUENCE_MATCHED"), original.poke_word,
                     wb("KEY_SEQUENCE_MATCHED_SET"), "the cheat sequence, matched"),
              M3Poke(wb("KEY_LAST_SCANCODE"), original.poke_byte, wb("KEY_SCANCODE_N"),
                     "N, as the IKBD would leave it")),
             "$556: the cheat's level skip. The SAME unwind target as the round end and a different "
             "code, because the two arms are reached on different conditions and clear different "
             "state — one code for the pair would let a port that took the wrong one look right"),
    M3Ending("quit", "WB_KEY_ACTIONS_QUIT", wb("KEY_ACTIONS_QUIT"), UNWIND_DATA_DISK,
             (M3Poke(wb("KEY_LAST_SCANCODE"), original.poke_byte, wb("KEY_SCANCODE_ESC"),
                     "ESC, as the IKBD would leave it"),),
             "$580: ESC starts the music fade ($594, ../src/sound.c) and unwinds into the "
             "data-disk prompt rather than the sequence"),
)
# THE THREE CODES MUST BE DISTINCT, or a run reporting the wrong ending would satisfy another's row.
assert len({ending.code for ending in M3_ENDINGS}) == len(M3_ENDINGS), (
    "two M3 endings share a loop_ending code — ../include/game.h keeps them apart on purpose")
assert LOOP_RETURNED not in {ending.code for ending in M3_ENDINGS}, (
    "an M3 ending reports the code that means the loop RETURNED — no run could tell them apart")

# The mode that runs all three, and the mode that breaks the hand-back. Rows are grouped so the
# control can invert its verdict over the hand-back half and assert the ending half normally, which
# is `m2fault`'s structural-key rule: a control whose own run is unsound proves nothing.
# THE CHEAT WORD IS HALF THE LEVEL-SKIP ARM'S CONDITION, and the three driven endings above show
# only the other half. `$556` is `tst.w $604 / beq` THEN `cmpi.b #$31,$879`, so a port that dropped
# the word test entirely would still pass the LEVEL_SKIP row — the poke sets both, and N alone would
# be enough for the broken port. This control drives N with the word left CLEAR and requires the loop
# NOT to end, which is what makes "the same target on a different condition" a measured claim.
#
# THE POKE SET IS DERIVED FROM THE ARM'S OWN, minus the cheat word, rather than written out again: a
# control whose inputs are a second copy of the thing it controls is one that stops controlling it
# the day the copy drifts.
CHEAT_WORD_OFFSET = wb("KEY_SEQUENCE_MATCHED")
LEVEL_SKIP_ENDING = next(e for e in M3_ENDINGS if e.code == wb("KEY_ACTIONS_LEVEL_SKIP"))
CHEAT_PREMISE_TAG = "nalone"
CHEAT_PREMISE_POKES = tuple(entry for entry in LEVEL_SKIP_ENDING.pokes
                            if entry.offset != CHEAT_WORD_OFFSET)
assert len(CHEAT_PREMISE_POKES) == len(LEVEL_SKIP_ENDING.pokes) - 1, (
    f"the level-skip arm no longer pokes WB_KEY_SEQUENCE_MATCHED ({CHEAT_WORD_OFFSET:#x}), so "
    f"dropping it cannot be the control that shows the word is tested")
assert CHEAT_PREMISE_POKES, "N alone is no poke at all — the control would drive nothing"

M3_MODE, M3_FAULT_MODE = "m3", "m3fault"
ENDING_ROWS, HANDBACK_ROWS = "ending", "handback"


def m3_save(directory, name, address):
    return f"savebin {Path(directory) / name} ${address:x} {LONGWORD_BYTES}"


def m3_exit_breakpoint(directory, tail=()):
    """The breakpoint on the program's OWN exit, and everything that has to happen there.

    Two jobs, and EVERY M3 RUN NEEDS THE FIRST. The records are renamed aside before anything can
    reboot (M3_RESCUED_M2's comment has the reason), and then `tail` — the driven runs' two machine
    inspections — is armed from inside this same action file, which is what makes their ordering
    against the exit structural instead of a margin to measure."""
    directory = Path(directory)
    rescues = [f"rename {DISK / live} {DISK / rescued}" for live, rescued in RECORD_RESCUES]
    return original.gemdos_breakpoint(GEMDOS_PTERM0, original.action_file(
        directory, "M3EXIT.INI", f"echo {M3_EXIT_BEACON}", *rescues, *tail))


def m3_plain_script(directory):
    """PASS ONE'S script, and it exists for one line: the record rescue.

    An undriven boot needs no poke and takes no machine readings — but `m3fault`'s pass one leaves
    the machine hooked into memory GEMDOS has taken back exactly as its driven runs do, so it can
    fall over, be RESET, and have `--auto` re-run `WB.PRG` over its records before `--run-vbls` ends.
    Reading pass one off the live drive would then aim every poke below with a second run's numbers.
    Rescuing them at `Pterm` costs one breakpoint and closes it."""
    script = Path(directory) / "M3PLAIN.INI"
    script.write_text(m3_exit_breakpoint(directory) + "\n")
    return script


def ending_poke_breakpoint(directory, base, capture_pc, pokes, action_name, *before,
                           arrival=M3_POKE_ANCHOR):
    """The breakpoint that injects a `game_key_actions` ending — and the one BOTH driven modes make.

    THE ENDING IS DRIVEN AT ONE OF `capture_the_frame`'s ARRIVALS in both, which is inside the frame
    loop and after any boot, so the mechanism that drives an ending on the FRAME build drives the
    same ending on the OWN-ENTRY one. Two spellings of that is two places the arrival, the beacon or
    the poke's base can drift — and the base is `image_base`, the one number whose mis-aiming is
    INVISIBLE rather than loud: the poke lands somewhere harmless, the ending never fires, and the
    run reads as a build that simply did not take it.

    WHICH ARRIVAL IS THE CALLER'S, AND THE TWO MODES DO NOT AGREE. M3_POKE_ANCHOR is the default and
    is M3's own — the SECOND arrival, so a run has already photographed a frame before the ending
    fires. `mode_ownplay`'s two ESC passes pass OWN_QUIT_POKE_ANCHOR instead, which is a MEASUREMENT:
    the prompt's screen-base rows are about a hardware register the frame loop also writes, and the
    parity of the completed frame count decides whether the publish they pin can be seen at all.
    That constant's own comment has the reading.

    `before` is what a mode does BEFORE the pokes, in the same action file and therefore at the same
    instant: M3 photographs the two vectors as the shim left them, and the own-entry ladder has
    nothing to add."""
    original.refuse_repeated_arrivals([(capture_pc, arrival)])
    return original.anchor_breakpoint(
        capture_pc, arrival,
        original.action_file(directory, action_name, f"echo {M3_POKE_BEACON}", *before,
                             *[entry.poke(base + entry.offset, entry.value) for entry in pokes]))


def m3_script(directory, base, capture_pc, pokes):
    """The debugger script that injects `pokes` and then watches the machine outlive the program.

    Two top-level breakpoints. The first is `capture_the_frame`'s Nth arrival, where the two vectors
    are photographed AS THE SHIM LEFT THEM and the pokes go into the image. The second is the
    program's own `Pterm0`, which rescues the records and arms the two tail readings — the next
    vblank, where the two vectors and TOS's frame clock are read back, and Pterm+M3_TAIL_STEPS,
    where the clock is read again because one reading cannot show motion."""
    directory = Path(directory)
    tail = [
        original.vbl_breakpoint(original.VBL_NEXT, original.action_file(
            directory, "M3TAILA.INI", f"echo {M3_TAIL_BEACONS[0]}",
            m3_save(directory, M3_VBL_VECTOR_AFTER, VEC_LEVEL4_VBL),
            m3_save(directory, M3_ACIA_VECTOR_AFTER, VEC_MFP_ACIA),
            m3_save(directory, M3_CLOCK_EARLY, TOS_FRCLOCK))),
        original.vbl_breakpoint(original.VBL_NEXT, original.action_file(
            directory, "M3TAILB.INI", f"echo {M3_TAIL_BEACONS[1]}",
            m3_save(directory, M3_CLOCK_LATE, TOS_FRCLOCK)), hit=M3_TAIL_STEPS),
    ]
    # THE TWO VECTORS ARE PHOTOGRAPHED IN THE SAME ACTION FILE AS THE POKES, so they are read at the
    # instant the ending is injected rather than at some later breakpoint of their own.
    lines = [
        ending_poke_breakpoint(directory, base, capture_pc, pokes, "M3POKE.INI",
                               m3_save(directory, M3_VBL_VECTOR_RUNNING, VEC_LEVEL4_VBL),
                               m3_save(directory, M3_ACIA_VECTOR_RUNNING, VEC_MFP_ACIA)),
        m3_exit_breakpoint(directory, tail),
    ]
    script = directory / "M3CMD.INI"
    script.write_text("\n".join(lines) + "\n")
    return script


def m3_captures(directory):
    """{filename: longword or None} — what the run's breakpoints left behind.

    A missing capture is None RATHER THAN A RAISE, because the hand-back control is expected to take
    the machine down: a run whose tail breakpoint never fired has failed the rows that read it, and
    that is a verdict this mode knows how to print. It is only a hard error when a file is there and
    the wrong length, which is a reader bug rather than a run."""
    captured = {}
    for name, what in M3_CAPTURES:
        path = Path(directory) / name
        if not path.exists():
            captured[name] = None
            continue
        blob = path.read_bytes()
        if len(blob) != LONGWORD_BYTES:
            raise SystemExit(f"FAIL: {name} ({what}) is {len(blob)} bytes, expected {LONGWORD_BYTES}")
        captured[name] = struct.unpack(">I", blob)[0]
    return captured


def as_capture(value):
    return "not captured" if value is None else f"{value:#x}"


def handed_back(before, after):
    """Did a vector stop being the shim's? Both readings have to exist for the answer to be yes."""
    return before is not None and after is not None and before != after


def base_offset(entry):
    """One poke, as the image offset and value a reader can check against ../include/wonderboy.h."""
    return f"image + {entry.offset:#x} := {entry.value:#x}"


def m3_checks(record, stats, plain, ending, captured, reached_pterm):
    """One driven ending's rows, as (name, ok, detail, group)."""
    poke_frame = original.anchor_frames()[M3_POKE_ANCHOR - 1]
    vbl_in = captured[M3_VBL_VECTOR_RUNNING]
    vbl_out = captured[M3_VBL_VECTOR_AFTER]
    acia_in = captured[M3_ACIA_VECTOR_RUNNING]
    acia_out = captured[M3_ACIA_VECTOR_AFTER]
    early, late = captured[M3_CLOCK_EARLY], captured[M3_CLOCK_LATE]
    checks = [
        ("the loop was LEFT, and by THIS ending", record["loop_ending"] == ending.code,
         f"loop_ending={record['loop_ending']} = {ending.arm} ({ending.code}); the original's arm "
         f"`jmp`s to {ending.unwind:#x}. Poked: "
         + ", ".join(f"{entry.what} at {base_offset(entry)}" for entry in ending.pokes),
         ENDING_ROWS),
        ("...on the frame the poke chose", record["frames_run"] == poke_frame,
         f"{record['frames_run']} frames completed, and the poke landed at the end of frame "
         f"{poke_frame} (capture_the_frame's arrival {M3_POKE_ANCHOR}), so the ending fired at the "
         f"top of the next one", ENDING_ROWS),
        ("the two boots agree where the program is", record["image_base"] == plain["image_base"]
         and record["capture_pc"] == plain["capture_pc"],
         f"image at {record['image_base']:#x} (undriven boot: {plain['image_base']:#x}), "
         f"capture_the_frame at {record['capture_pc']:#x} ({plain['capture_pc']:#x}) — the poke was "
         f"aimed with the undriven boot's numbers", ENDING_ROWS),
        # THE PROGRAM REALLY REACHED ITS OWN EXIT, and the three rows below are anchored on it, so
        # they cannot be reading a machine the reconstruction still owns. A build that hung after
        # the loop — which is what the exit-path defect in §8 did — never trips this.
        ("the program reached Pterm", reached_pterm,
         f"GEMDOS function {GEMDOS_PTERM0} (`clr.w -(%sp) / trap #1`, wonderboy_os.s) was taken, and "
         f"the two inspections below hang off it: +1 vblank and +{M3_TAIL_STEPS}", ENDING_ROWS),
        # THE VECTORS ARE COMPARED ACROSS THE EXIT rather than against a value written down here.
        # What TOS had on $70 before the program ran is TOS's business and differs by ROM; what
        # matters is that the address the shim installed is no longer there once the shim has gone.
        ("$70 stopped being the shim's", handed_back(vbl_in, vbl_out),
         f"level-4 vector {as_capture(vbl_in)} while the reconstruction owned the machine, "
         f"{as_capture(vbl_out)} one vblank after Pterm", HANDBACK_ROWS),
        ("$118 stopped being the shim's", handed_back(acia_in, acia_out),
         f"ACIA vector {as_capture(acia_in)} while the reconstruction owned the machine, "
         f"{as_capture(acia_out)} one vblank after Pterm", HANDBACK_ROWS),
        # ...AND THE MACHINE IS ALIVE, not merely unhooked. Two readings, because one cannot show
        # motion: TOS's own vertical-blank handler is the only writer of this longword, so it moves
        # if and only if the vector really went back to a handler that runs.
        ("TOS's frame clock is still advancing", None not in (early, late) and late > early,
         f"_frclock {as_capture(early)} one vblank after Pterm, {as_capture(late)} at Pterm+"
         f"{M3_TAIL_STEPS} — {M3_TAIL_GAP} vblanks later"
         + ("" if None in (early, late) else f" (+{late - early})"), HANDBACK_ROWS),
    ]
    # The record's OWN teardown verdict, from the inside, beside the debugger's from the outside.
    # `RB_PASSED_ROW` carries every restore bit, so it is the hand-back's row here; `RB_RAN_ROW` says
    # the checks executed at all and must hold whatever the control suppresses.
    for name, ok, detail in readback_checks(stats):
        checks.append((name, ok, detail,
                       HANDBACK_ROWS if name == RB_PASSED_ROW else ENDING_ROWS))
    return [(name, bool(ok), detail, group) for name, ok, detail, group in checks]


def rescued_records(what):
    """The two records the debugger moved aside at `Pterm`, or a failure that names the run.

    READ UNDER THEIR RESCUED NAMES AND NEVER OFF THE LIVE DRIVE — M3_RESCUED_M2's comment has the
    reboot that makes the difference, and it applies to the undriven pass as much as to a driven
    one: `m3fault`'s pass-one machine is left hooked exactly as its driven runs are."""
    record, why = read_m2(M3_RESCUED_M2)
    stats, stats_why = read_stats(M3_RESCUED_STATS)
    if record is None or stats is None:
        raise SystemExit(f"FAIL: {what} left no readable record ({why or stats_why})")
    return record, stats


def measure_the_undriven_boot(prg, mode):
    """PASS ONE: boot the build with no poke at all, and take three things off it.

    Two are the numbers every poke below is aimed with — where GEMDOS put the image, and where
    `capture_the_frame` is — and the third is M3'S NEGATIVE CONTROL: with nothing injected the frame
    loop must run every frame it was asked for and report that it RETURNED. A mode whose control pass
    already showed an ending would be measuring something other than the pokes.

    It carries a debugger script all the same, and `m3_plain_script` says why in one line."""
    with tempfile.TemporaryDirectory() as tmp:
        status, log, rom = run_hatari(prg, run_vbls=M3_RUN_VBLS, parse=m3_plain_script(tmp),
                                      log_name=f"hatari-{mode}-plain.log")
    record, _ = rescued_records("the undriven boot")
    control = [
        ("no ending fires when none is driven", record["loop_ending"] == LOOP_RETURNED,
         f"loop_ending={record['loop_ending']} = WB_KEY_ACTIONS_RETURNED ({LOOP_RETURNED})"),
        ("...and the loop ran every frame", record["frames_run"] == record["frames_requested"],
         f"{record['frames_run']} of {record['frames_requested']}"),
    ]
    report(f"{mode} pass 1 — the UNDRIVEN boot, which is M3's negative control", control)
    print(f"   TOS={rom or 'bundled EmuTOS'} hatari exit={status}; image at "
          f"{record['image_base']:#x}, capture_the_frame at {record['capture_pc']:#x}")
    refuse_unless_the_control_holds(control, "the driven runs below")
    return record, log, status


def boot_with_pokes(prg, mode, plain, tag, pokes, what):
    """Boot the same binary again with `pokes` injected, and bring back everything the run left.

    Shared by the three driven endings and by the cheat word's own control, which is a poke set and
    an expectation like any of them — the only thing that differs is what its record must say."""
    with tempfile.TemporaryDirectory() as tmp:
        script = m3_script(tmp, plain["image_base"], plain["capture_pc"], pokes)
        status, log, rom = run_hatari(prg, run_vbls=M3_RUN_VBLS, parse=script,
                                      log_name=f"hatari-{mode}-{tag}.log")
        captured = m3_captures(tmp)
    if M3_POKE_BEACON not in log:
        raise SystemExit(f"FAIL: {what}'s poke breakpoint never fired — arrival {M3_POKE_ANCHOR} at "
                         f"capture_the_frame ({plain['capture_pc']:#x}) was never reached, so "
                         f"nothing was injected and this run is not a drive")
    record, stats = rescued_records(what)
    return record, stats, captured, log, status, rom


def drive_the_ending(prg, mode, plain, ending):
    """PASS TWO..FOUR: boot the same binary again and MAKE `ending` happen."""
    record, stats, captured, log, status, rom = boot_with_pokes(
        prg, mode, plain, ending.tag, ending.pokes, ending.arm)
    checks = m3_checks(record, stats, plain, ending, captured, M3_EXIT_BEACON in log)
    return checks, record, log, status, rom


def drive_the_cheat_premise_control(prg, mode, plain):
    """N WITH THE CHEAT WORD LEFT CLEAR: the half of `$556`'s condition the endings cannot show.

    The level-skip row proves the arm is reachable; it does not prove that `tst.w $604` is what
    gates it, because the poke that reaches the arm sets the word AND the scancode. Drop the word
    and the loop must NOT end — so a port that tested only the scancode goes red here while staying
    green there. Its poke set is the arm's own minus the word (CHEAT_PREMISE_POKES)."""
    record, _, _, _, status, rom = boot_with_pokes(
        prg, mode, plain, CHEAT_PREMISE_TAG, CHEAT_PREMISE_POKES, "the cheat-word control")
    poked = ", ".join(base_offset(entry) for entry in CHEAT_PREMISE_POKES)
    checks = [
        ("N alone does NOT skip the level", record["loop_ending"] == LOOP_RETURNED,
         f"loop_ending={record['loop_ending']} = WB_KEY_ACTIONS_RETURNED ({LOOP_RETURNED}); poked "
         f"{poked} and left WB_KEY_SEQUENCE_MATCHED ({CHEAT_WORD_OFFSET:#x}) CLEAR, so `tst.w $604` "
         f"at $556 is what refused the arm"),
        ("...and the loop ran to its own end", record["frames_run"] == record["frames_requested"],
         f"{record['frames_run']} of {record['frames_requested']} frames"),
        ("the same placement as the boot the poke was aimed with",
         record["image_base"] == plain["image_base"],
         f"image at {record['image_base']:#x} (undriven boot: {plain['image_base']:#x})"),
    ]
    report(f"{mode}: the CHEAT-WORD control — the level skip's other half", checks)
    print(f"   TOS={rom or 'bundled EmuTOS'} hatari exit={status} (full log in "
          f"{OUT / f'hatari-{mode}-{CHEAT_PREMISE_TAG}.log'})")
    return [f"the cheat-word control {name}: {detail}" for name, ok, detail in checks if not ok]


def mode_m3(mode):
    """M3: `game_key_actions`' three endings, driven one run each, and the hand-back asserted.

    `m3fault` boots the build whose `teardown` never puts the two vectors back and INVERTS its verdict
    over the hand-back rows: a run in which the machine still looks handed back would mean this mode
    is not reading what it names. The ending rows are asserted NORMALLY there, because a control whose
    own run did not do the thing it is controlling proves nothing — and so is the cheat-word control,
    which is about `game_key_actions`' predicate and not about the hand-back at all."""
    faulted = mode == M3_FAULT_MODE
    prg = BUILD / M3_BUILDS[mode]
    plain, plain_log, plain_status = measure_the_undriven_boot(prg, mode)
    # The undriven boot's own health is asserted only where the build is sound. `m3fault` leaves the
    # machine hooked into memory GEMDOS has taken back, so its tail is expected to be unhealthy —
    # that IS the control — and the reading is printed below rather than being a pass/fail here.
    problems = [] if faulted else check_machine_health(plain_status, plain_log)
    problems += drive_the_cheat_premise_control(prg, mode, plain)

    for ending in M3_ENDINGS:
        checks, record, log, status, rom = drive_the_ending(prg, mode, plain, ending)
        report(f"{mode}: {ending.arm} — {ending.why}", checks)
        print(f"   TOS={rom or 'bundled EmuTOS'} hatari exit={status}, {record['shim_vbl_ticks']} "
              f"shim vblanks (full log in {OUT / f'hatari-{mode}-{ending.tag}.log'})")
        faults = check_machine_health(status, log, assert_status=not faulted)
        if faulted:
            # MEASURED AND PRINTED, not asserted in either direction. Whether an unhooked vector
            # takes the machine down depends on what GEMDOS puts in the freed memory, which is TOS's
            # business; the rows below are what this control asserts.
            print(f"   note the machine's tail with the hand-back suppressed: "
                  + ("; ".join(faults) if faults else "no fault in the log, hatari exit "
                                                      f"{status}"))
        else:
            problems += faults
        ending_rows = [row for row in checks if row[3] == ENDING_ROWS]
        handback_rows = [row for row in checks if row[3] == HANDBACK_ROWS]
        problems += [f"{ending.arm} {name}: {detail}" for name, ok, detail, _ in ending_rows if not ok]
        if faulted and record["loop_ending"] == LOOP_RETURNED:
            # THE ONE WAY THIS CONTROL LIED, kept as a tripwire over the two fixes that closed it.
            # A record reporting no ending on a run whose poke fired means the program ran TWICE:
            # the still-hooked vector took the machine down, TOS reset — restoring the vectors and
            # restarting the frame clock, so the hand-back rows go green on a build that never
            # handed anything back — and `--auto` re-ran WB.PRG with the `:once` breakpoint spent,
            # so the undriven second run's records were the ones on the drive. The readings now hang
            # off GEMDOS_PTERM0 and the records are renamed aside there, so reaching this means one
            # of those two did not happen — most likely the rename (M3_RESCUED_M2).
            problems.append(f"{ending.arm}: the control's own run rebooted AND the records were not "
                            f"rescued at Pterm — this record is a SECOND, undriven run's, so no row "
                            f"below reports on the suppressed hand-back")
        if not faulted:
            problems += [f"{ending.arm} {name}: {detail}"
                         for name, ok, detail, _ in handback_rows if not ok]
            continue
        held = [name for name, ok, _, _ in handback_rows if ok]
        if held:
            problems.append(f"{ending.arm}: the hand-back control did not break "
                            + ", ".join(held) + " — these rows are not reading the hand-back")

    if problems:
        raise SystemExit("FAIL: " + "; ".join(problems))
    if faulted:
        print(f"OK: with the two vector restores suppressed, every hand-back row FAILS on all "
              f"{len(M3_ENDINGS)} endings and every ending row still holds — the control is targeted")
        return
    print(f"OK: M3 — all {len(M3_ENDINGS)} of game_key_actions' endings driven on a 68000, each "
          f"reporting its own code, the cheat word shown to be tested rather than assumed, and the "
          f"machine handed back to a TOS still ticking {M3_TAIL_GAP} vblanks later")



# ---- THE OWN-ENTRY BUILD: booted by itself, and every ending walked back into the chain ----------
#
# WHAT THIS MODE CLAIMS, and it is the one claim no other mode here can make: the reconstruction
# BOOTS ITSELF. `mode_boot` runs the chain and stops at `$f8b4`; the frame modes start at `$4a0` over
# the ORIGINAL's measured RAM. This build does both halves in one run — M1's image in, the boot
# chain, the frame loop — and then wires `game_key_actions`' endings to the addresses the original's
# own `jmp`s name, so a round end really does load the next stage and ESC really does show the
# data-disk prompt and start over.
#
# SIX PASSES, AND THE FIRST TWO ARE THE THIRD'S CONTROLS:
#   1. UNDRIVEN — nothing injected. The chain must sit at its first fire gate exactly as `mode_boot`'s
#      pass one does, and it is where the addresses the pokes below are aimed with come from.
#   2. FIRE ONLY — both gates answered and no ending driven. The stage must stay where the boot put
#      it: no reload, no restart, and the overlay in memory is still the first row's. This is the
#      negative control for pass three, and without it "the stage moved" could be something the run
#      does on its own.
#   3. THE ROUND END, DRIVEN — `WB_ROUND_END_RELOAD_REQUEST` poked at `capture_the_frame`'s second
#      arrival, which is M3's own mechanism and its own anchor. The frame loop must leave, the ladder
#      must call `boot_load_stage` AGAIN, the sequence must step, the SECOND overlay must cross the
#      seam, and the frame loop must run again on the other side of it.
#   4. ESC, DRIVEN — the same poke set M3's QUIT ending uses. The prompt slice must draw, its gate
#      and the boot's two must be crossed again, and `game_restart_reset` inside the credits slice
#      must put the sequence back to its first row. This is the pass that exercises
#      `boot_prompt_screen` and `own_restart` on the machine — and, since batch 44 phase F, the pass
#      that PHOTOGRAPHS the prompt and compares it against the shipped binary's own picture, taken
#      at `$e4d6` by `original.py prompt` after driving the SHIPPED side's ESC ending. Its two
#      picture rows have a control that can fail: the same reader, the game's other picture.
#   5. THE ROUND END WITH ITS OVERLAY WITHHELD — the reload arm's stop, with real data.
#   6. ESC WITH DATADISK.RAD WITHHELD — the restart arm's stop, the same way. Five of
#      `run_the_own_entry`'s six exits are executed by these six passes; the sixth (OWN_STOP_LEG_
#      LIMIT) needs a ladder that cycles, which nothing here produces, and is declared in
#      atari/README.md's Known gaps.
#
# WHICH OVERLAY CROSSED, MEASURED. Every stage's overlay inflates to the same address, so the run
# reports the first LONGWORD of what landed there and this file inflates the shipped file host-side
# and compares — after asserting the two rows' heads DIFFER, so the comparison cannot pass by their
# being equal.

OWN_FILE = "OWN.BIN"
OWN_FIELDS = ("magic", "bytes", "image_base",
              "prompt_result", "title_result", "credits_result", "stage_result",
              "prompt_captured_at", "prompt_base_before", "prompt_shifter_base",
              "prompt_pens_readback_failed",
              "fire_press_pc", "fire_release_pc", "fire_gates_crossed", "fire_waits_timed_out",
              "fire_wait_timed_out_pc",
              "entry_unwind", "legs_run", "reloads", "restarts", "last_ending", "stopped_at",
              "frames_total", "frame_loop_vbl_ticks",
              "stage_map_ptr", "stage_start_ptr", "resource_signature", "stage_number",
              "level_seq_index", "stage_second_load_flag", "stage_side_flag",
              "life_restart_entry_c26", "stage_entry_follow", "copylock_arm_flag",
              "vbl_ticks_at_exit")
OWN_FORMAT = ">%dI" % len(OWN_FIELDS)
assert_the_record_matches_the_c("own_stats", OWN_FIELDS)

OWN_MAGIC = c_constant("OWN_MAGIC")              # 'WBA5'
# WHY THE LADDER STOPPED — wonderboy_main.c's OWN_STOP_*, scraped rather than restated, and named
# here so a `stopped_at` that is not the expected one reads as a rung rather than as a number. The
# LEG_LIMIT one is included for completeness: no pass below can reach it, and a run that did would
# print its name instead of a bare 5.
OWN_STOP_NAMES = {c_constant(name): name for name in
                  ("OWN_STOP_BOOT", "OWN_STOP_FRAME_LIMIT", "OWN_STOP_RELOAD", "OWN_STOP_RESTART",
                   "OWN_STOP_LEG_LIMIT")}
OWN_STOP_BOOT = c_constant("OWN_STOP_BOOT")
OWN_STOP_FRAME_LIMIT = c_constant("OWN_STOP_FRAME_LIMIT")
OWN_STOP_RELOAD = c_constant("OWN_STOP_RELOAD")
OWN_STOP_RESTART = c_constant("OWN_STOP_RESTART")

# WHERE THE OWN-ENTRY BUILD PUTS THE PROMPT PICTURE. Not FRAME.BIN/PENS.BIN — this build also
# compiles -DSMOKE_M2 and those two are already the frame loop's anchor captures, which is exactly
# the collision `picture_rows`' `captures` argument exists for.
OWN_PROMPT_FILE = "PROMPT.BIN"
OWN_PROMPT_PENS_FILE = "PROMPTPN.BIN"
OWN_PROMPT_CAPTURES = (OWN_PROMPT_FILE, OWN_PROMPT_PENS_FILE)
# The `original.py` mode that photographs this mode's shipped side, named once for
# BOOT_CREDITS_ANCHOR_MODE's reason: the refusal a missing artefact produces is then the command a
# reader can paste.
PROMPT_ANCHOR_MODE = "prompt"
# WHICH ARRIVAL AT `capture_the_frame` THE ESC PASSES POKE AT, and it is NOT M3's — which is a
# measurement rather than a preference, and the one that turned the prompt's base row from a pin
# that could not fail into one that can.
#
# `flip_screen` publishes the buffer that has just BECOME the front one, so the base at an ending is
# decided by the parity of the leg's frame count. M3's anchor is the SECOND arrival, i.e. two frames
# flipped, and measured that leaves the base already on WB_SCREEN_HIGH — the very buffer
# `boot_prompt_screen` then publishes. The phase-E mutant P3 (the publish deleted outright) was
# applied to the first draft of this row and came back GREEN on both ROMs for exactly that reason.
# One frame earlier the base is on WB_SCREEN_LOW and the publish is the only thing that can move it.
#
# IT COSTS M3'S TWO STATED REASONS NOTHING: `capture_the_frame`'s FIRST arrival is still after a
# whole frame has run under the debugger, and it is if anything earlier in the window, so the tail is
# longer rather than shorter. It is scoped to the ESC passes because they are the only ones whose
# claim is about a hardware register the frame loop also writes.
OWN_QUIT_POKE_ANCHOR = 1
# AND PASS 6 DEPENDS ON THE SAME PARITY, for the same reason on the other arm: its stranded-base row
# is `prompt_base_before != WB_SCREEN_HIGH and the base at the exit == WB_SCREEN_HIGH`, and an anchor
# whose frame count already left the base there would make the conjunct's second half true of a run
# that published nothing. Both ESC passes therefore pass this anchor, and neither takes M3's.
#
# ...AND THE INSTANT BOTH SIDES PHOTOGRAPH, WHICH IS A FRAME AND NOT AN ANCHOR NUMBER. The two
# constants are DIFFERENT KINDS and comparing them directly was the first draft's mistake:
# `original.PROMPT_ESC_ANCHOR` is a 1-based index INTO `anchor_frames()`, while this one is an
# ARRIVAL COUNT at `capture_the_frame`. The shim calls that routine once per anchor frame in the
# FRAME LOOP's order, so its Nth arrival is at the Nth SMALLEST anchor — `sorted(...)[N - 1]` — and
# the two numbers agree only for as long as M2_ANCHOR_FRAMES happens to be written in ascending
# order. What has to hold is that the ESC poke lands after the same number of completed frames on
# both sides, so that is what is asserted: the shipped side's `prompt_esc_stop` breakpoints
# `$4a0`'s hit `frame + 1`, i.e. the start of the frame after `frame`, and ours pokes at the arrival
# that follows the frame below.
_THEIR_ESC_FRAME = original.anchor_frames()[original.PROMPT_ESC_ANCHOR - 1]
_OUR_ESC_FRAME = sorted(original.anchor_frames())[OWN_QUIT_POKE_ANCHOR - 1]
assert _THEIR_ESC_FRAME == _OUR_ESC_FRAME, (
    f"the shipped side pokes ESC once frame {_THEIR_ESC_FRAME} has finished (anchor_frames() index "
    f"{original.PROMPT_ESC_ANCHOR}) and this side once frame {_OUR_ESC_FRAME} has (capture_the_frame "
    f"arrival {OWN_QUIT_POKE_ANCHOR} of {original.anchor_frames()}) — the two prompt pictures would "
    f"be of two different runs' frames, and the base parity the row above depends on is decided by "
    f"exactly that count")


def own_stop(record):
    """`stopped_at`, as the rung it names."""
    return f"{record['stopped_at']} = {OWN_STOP_NAMES.get(record['stopped_at'], 'UNKNOWN')}"

OWN_MODE = "ownplay"
# The build `atari/run.sh` launches: the same ladder with every bound lifted. It is not a smoke mode
# — an uncapped run has no end to assert — but the drive it needs is this file's, so its `.PRG` is
# named here and `stage_drive` keys on both.
OWN_RUN_BUILD = "WB-ownrun.PRG"
OWN_BUILDS = {OWN_MODE: "WB-ownplay.PRG"}
OWN_PRGS = frozenset(OWN_BUILDS.values()) | {OWN_RUN_BUILD}

# HOW MANY GATES EACH PASS CAN CROSS, and it is not the same number for all of them — which is the
# point of naming three. A pass that only walks the chain crosses the chain's own two; ESC's pass
# walks the prompt's and then the chain's two AGAIN, so it crosses five. DERIVED from
# BOOT_FIRE_GATES rather than written as 2 and 5, because what ESC re-walks IS the boot chain and a
# chain that grew a gate must grow both readings.
#
# ARMING MORE THAN A PASS CAN CROSS IS NOT FREE: an unanswered gate stops the ladder, so a pass that
# armed five and crossed two would look identical to one that armed two — and `fire_gates_crossed`
# is then asserted per pass, so a pass whose gates were miscounted reds instead of quietly running
# short.
OWN_PROMPT_GATES = 1
OWN_CHAIN_GATES = BOOT_FIRE_GATES
OWN_RESTART_GATES = OWN_PROMPT_GATES + OWN_CHAIN_GATES
OWN_FIRE_GATES = OWN_CHAIN_GATES + OWN_RESTART_GATES

# The two sequence rows this mode is about: the one the boot loads and the one a reload steps to.
# WB_LEVEL_SEQ_INDEX AFTER A LOAD IS THE SAME ARITHMETIC — `game_restart_reset` (inside the credits
# slice) leaves the index at FIRST_SEQ_ROW and `stage_sequence_advance` steps it once per load — so
# the row a run ended on and the index it reports are ONE expression, not two that can drift.
SECOND_SEQ_ROW = FIRST_SEQ_ROW + SEQ_ROWS_STEPPED
# How many times the ladder enters the frame loop in each driven pass: once, or once more after the
# ending that reloads or restarts.
LEGS_WITHOUT_AN_ENDING = 1
LEGS_WITH_ONE_ENDING = 2
# THE `--run-vbls` THIS MODE NEEDS, BRACKETED RATHER THAN GUESSED — and the bracket is the point,
# because the first draft's 20,000 was a round number nobody had measured against.
#
# MEASURED (TOS 1.04, over the five passes that existed when it was bracketed): 4,000 is green and
# 3,000 is not — at 3,000 the fire-only pass is cut off before it writes `OWN.BIN` and the mode
# reports "never reached its own dump", which reads like a crash. So the floor is between 3,000 and
# 4,000 and this is TWICE it. The sixth pass does not move the floor and is not re-bracketed here:
# it stops at the prompt's refusal, and measured it spends ~562 shim vblanks against the longest
# pass's ~1,690. Every
# vblank above the floor is wall-clock spent five times over (Hatari runs the WHOLE window whatever
# the program does: 20,000 measured 14.3 s per pass), so headroom is not free.
#
# IT IS NOT THE SAME CLOCK AS THE RECORD'S. `vbl_ticks_at_exit` counts the SHIM's vertical blanks —
# only while the reconstruction's own level-4 vector is installed — and the longest pass reports
# ~1,700 of those against a window of thousands. Sizing this from that figure would cut every run
# off inside TOS's own boot; the two numbers are printed side by side per pass so neither is
# mistaken for the other.
OWN_RUN_VBLS = 8000

# The ROUND-END ending, out of M3's own table rather than re-poked here: same word, same value, same
# reason. M3 drives it on the FRAME build to show the loop can be left; this mode drives it on the
# own-entry build to show where it comes back to.
ROUND_END_ENDING = next(e for e in M3_ENDINGS if e.code == wb("KEY_ACTIONS_ROUND_END"))
QUIT_ENDING = next(e for e in M3_ENDINGS if e.code == wb("KEY_ACTIONS_QUIT"))
# Which gate of ESC's ladder the key is let go at: the PROMPT's, which is the first one after the
# ending. Derived from the boot's own gate count, so it names the same gate however the chain grows.
QUIT_RELEASE_GATE = BOOT_FIRE_GATES
# What WB_KEY_LAST_SCANCODE holds when no key has been reported — wonderboy_main.c's own
# IKBD_NOTHING_SAID, and the value `reset_and_hear_back` clears it to before every reset.
IKBD_NOTHING_SAID = c_constant("IKBD_NOTHING_SAID")


def release_the_quit_key(plain):
    """Let go of ESC once the data-disk prompt is up — one poke, at a gate that is already a stop.

    THE POKE IS A PRESS AND A PLAYER IS NOT. `game_key_actions`' ESC arm reads WB_KEY_LAST_SCANCODE,
    and the debugger's poke leaves it there for ever — so without this the SECOND leg quits on its
    own first frame and restarts again, which is what a key physically held down would really do and
    is not what this pass is about. Clearing it at the prompt's own gate is the release the IKBD
    would have delivered while the picture was being loaded, and it is the same byte, poked the same
    way, as the press. Measured before it existed: two restarts, five gates spent, and the ladder
    stopping at OWN_STOP_RESTART because the sixth gate was never armed."""
    return {QUIT_RELEASE_GATE: [original.poke_byte(plain["image_base"] + wb("KEY_LAST_SCANCODE"),
                                                   IKBD_NOTHING_SAID)]}


def read_own(name=OWN_FILE):
    return read_record(name, OWN_FIELDS, OWN_FORMAT, OWN_MAGIC, "the own-entry build")


def own_resource_indices():
    """Every row of WB_RESOURCE_FILE_TABLE this ladder can ask the machine for.

    The boot chain's five, plus the two only an ENDING reaches: the SECOND sequence row's overlay
    (which a round end or a level skip loads) and DATADISK.RAD (which ESC's prompt draws). Derived
    from the table and the sequence exactly as `boot_resource_indices` is — a file staged under a
    name the reconstruction does not ask for would simply sit there, and the load would refuse."""
    return boot_resource_indices() + (overlay_resource(SECOND_SEQ_ROW), wb("RESOURCE_DATADISK"))


@functools.lru_cache(maxsize=None)
def overlay_entry_follow(row):
    """The start record's entry position inside the overlay sequence row `row` names, HOST-SIDE.

    This is the half of "the second overlay crossed the seam" that does not come off the machine.
    The run reports the longword its own `rad_depack` left at WB_OVERLAY_DEPACK_DEST +
    WB_START_FOLLOW_X — the two words `stage_load_window` copies into the followed actor — and this
    is what the shipped file says should be there, inflated by tools/depack_rad.py from the same
    bytes `stage_resources` put on the drive.

    THE FIRST LONGWORD WOULD NOT HAVE DONE, and it was measured rather than assumed: OVALAY01 and
    OVALAY02 both open `00 00 00 06` and first differ at byte 5, so a fingerprint taken at offset 0
    would have been equal for the two stages this mode is about and the reload unobservable."""
    name = resource_name(overlay_resource(row))
    shipped, _ = shipped_resource(name, BOOT_RESOURCE_TREES)
    data = shipped.read_bytes()
    at = wb("START_FOLLOW_X")
    inflated = depack_rad.depack(data, depack_rad.parse_header(data))
    return int.from_bytes(inflated[at:at + LONGWORD_BYTES], "big")


def own_stage_number(row):
    """The stage number sequence row `row` publishes — `stage_sequence_apply_row`'s zero-extended
    byte, read out of the staged image so this file and the reconstruction cannot disagree."""
    return sequence_row(row)[wb("LEVEL_SEQ_STAGE")]


def measure_the_undriven_own_run(prg):
    """PASS ONE: no poke at all — the addresses the pokes below are aimed with, and their control.

    It is `measure_the_undriven_boot_chain`'s job for this build and it asserts the same thing: with
    nothing injected the ladder must stop at the FIRST half of the FIRST gate. What it adds is the
    frame record, because this mode's pokes are aimed at `capture_the_frame` as M3's are — so a run
    that never reached the frame loop still has to report where that function is."""
    status, log, rom = run_hatari(prg, run_vbls=RUN_VBLS, log_name=f"hatari-{OWN_MODE}-plain.log")
    record, why = read_own()
    frames, frames_why = read_m2()
    stats, stats_why = read_stats()
    for missing in (why, frames_why, stats_why):
        if missing:
            raise SystemExit(f"FAIL: the undriven pass left no readable record ({missing})")
    control = readback_checks(stats, also_unreachable=(
        ("RB_VBL_TICKING",
         "this pass deliberately never enters the frame loop — the ladder stops at the FIRST fire "
         "gate — so `frames_run` is 0 and the bit's own floor of one vblank per frame cannot be "
         "met. That the loop was never entered is this pass's own headline row below, asserted "
         "there; the driven passes grade the bit non-vacuously"),)) + [
        ("the title slice ran on its own", record["title_result"] == LOAD_COPYLOCK_RAN,
         f"boot_title_screen returned {record['title_result']}"),
        ("...and the FIRST fire wait timed out, at its PRESS half",
         record["fire_waits_timed_out"] == 1 and record["fire_gates_crossed"] == 0
         and record["fire_wait_timed_out_pc"] == record["fire_press_pc"],
         f"{record['fire_waits_timed_out']} timed out at {record['fire_wait_timed_out_pc']:#x} "
         f"(wait_fire_pressed is at {record['fire_press_pc']:#x})"),
        ("...so the ladder never reached a stage", record["stopped_at"] == OWN_STOP_BOOT,
         f"stopped_at={own_stop(record)}"),
        ("...and the frame loop was never entered", record["legs_run"] == 0,
         f"{record['legs_run']} legs, {record['frames_total']} frames"),
    ]
    report(f"{OWN_MODE} pass 1 — the UNDRIVEN run, which is every poke below's negative control",
           control)
    print(f"   TOS={rom or 'bundled EmuTOS'} hatari exit={status}; image at "
          f"{record['image_base']:#x}, capture_the_frame at {frames['capture_pc']:#x}, the two "
          f"waits at {record['fire_press_pc']:#x} and {record['fire_release_pc']:#x}")
    refuse_unless_the_control_holds(control, "the driven runs below")
    return record, frames, stats, log, status


def the_unwind_agrees_with_the_measured_a5(record):
    """The a5 the frame loop was ENTERED with, against `bg_build_buffer`'s own `lea` operand — and
    against `build/ORIGREGS.txt`'s measured A5 when there is one.

    THE DUMP IS A WITNESS HERE AND NOT THE SOURCE, which is the whole point of the row. The frame
    builds SEED `sprites.blit.unwind` from that measurement; this build PRODUCES the number, from
    `bg_build_buffer`'s `lea $21e90.l,a5` at $fa5e — ../test/test_boot_chain.py runs the oracle over
    `boot_load_stage`'s whole range and requires the 68000's own a5 at the `jmp $4a0.w` to be it. So
    a dump that disagreed would be news; a dump that is absent costs this build nothing, and the row
    says so rather than being silently skipped.

    THE FIELD IS READ BACK OUT OF THE REGISTER FILE AND NOT COPIED FROM THE MACRO, and without that
    this row could not fail. `build.sh` passes -DM2_ENTRY_UNWIND to the FRAME modes only, so the
    own-entry build always compiles the fallback #define — and a record that published that macro
    would be compared here against the same header constant, agreeing by construction however the
    seeding line was edited. `run_frames` reports `sprites.blit.unwind` as the loop was entered with
    it instead, so an edit to that line reddens this row."""
    want = wb("TILE_INDEX_TABLE")
    if record["entry_unwind"] != want:
        return ("the entry unwind is the boot's own producer", False,
                f"the build reports {record['entry_unwind']:#x} and $fa5e's `lea` operand is "
                f"WB_TILE_INDEX_TABLE ({want:#x})")
    regs = BUILD / "ORIGREGS.txt"
    if not regs.exists():
        return ("the entry unwind is the boot's own producer", True,
                f"{want:#x} = WB_TILE_INDEX_TABLE, $fa5e's own operand — NOT CROSS-CHECKED here, "
                f"because {regs.name} is absent and this build needs no dump; the oracle row in "
                f"../test/test_boot_chain.py is what pins it")
    measured = original.register(regs.read_text(), "A5")
    return ("the entry unwind is the boot's own producer, and the dump agrees", measured == want,
            f"{want:#x} = WB_TILE_INDEX_TABLE, produced by $fa5e's `lea`; the original's measured "
            f"A5 at $f8b4 is {measured:#x}")


OWN_RUN_MODE = "ownrun"
OWN_RUN_BUILDS = {OWN_RUN_MODE: OWN_RUN_BUILD}
# THE WINDOW THIS MODE BOOTS FOR, and it is the BOOT mode's own rather than a fourth number: this
# run has to get TOS up, get the program loaded and get the title slice's load and depack across the
# seam, which is exactly what `mode_boot` sized 12,000 vblanks for. Measured at 2,000 the run was cut
# off DURING `clear_palette` — the shim's own vblank counter is not Hatari's, and a shim figure of
# ~500 for a whole chain is not a `--run-vbls` of 500. Everything after the title slice is the
# heartbeat this mode reads, and there is no reason to make the window longer: the build waits at its
# first fire gate for ever, by design.
OWN_RUN_BOOT_VBLS = BOOT_RUN_VBLS
# ...AND HOW MUCH HEARTBEAT COUNTS AS ALIVE. One vertical blank is one music tick and a tick is
# several YM2149 writes, so a machine that survived even a second past the title slice leaves
# hundreds of events. Set an order of magnitude below what a healthy run measures (~200,000), so the
# row fails on a DEAD machine rather than on a slow one.
OWN_RUN_ALIVE_EVENTS = 10000


def mode_ownrun():
    """THE BINARY `atari/run.sh` LAUNCHES, booted headless — the one build a person actually plays.

    IT EXISTS BECAUSE THE SWAP LEFT THE INTERACTIVE BINARY UNBOOTED BY ANYTHING. `run.sh` stopped
    launching `WB-play.PRG` in batch 44 phase E and nothing booted `WB-ownrun.PRG` in its place, so
    the binary a person opens had no headless check at all. That is exactly the gap the `--sound on`
    defect lived in — one line no headless mode executed, found by a person at the first real launch
    — and this is that gap on the BINARY, where `smoke.py runsh` is the same gap on the command line.

    WHAT IT ASSERTS: the build boots, takes the machine, crosses the file seam for TITLESCR.RAD,
    depacks it and puts its palette on the chip — and then keeps running, with the vertical-blank
    handler ticking, for the rest of the window.

    AND WHAT IT CANNOT, WHICH IS MEASURED RATHER THAN ASSUMED. THIS BUILD DOES NOT REACH THE FRAME
    LOOP HEADLESS, and that is correct behaviour rather than a defect: -DSMOKE_PLAY lifts the fire
    gates' spin bound as well as the frame count (wonderboy_main.c's FIRE_SPIN_DECL argues why a
    ninety-minute counter is not "uncapped"), so the title screen waits for a person for ever. The
    headless ladder answers its gates with a debugger poke aimed at the two wait PCs THE RECORD
    REPORTS — and this build writes no record, because with every bound lifted the ladder never ends,
    never hands the machine back and never reaches `write_file`. So there is no `image_base` to aim a
    poke with and no wait PC to aim it at; measured, an undriven run of this binary sits at the first
    gate and publishes no buffer at all. The frame loop, the ladder's five endings and every pin are
    `ownplay`'s, on a binary that differs from this one by one `-D`. The joystick is a person's, which
    is `mode_play`'s standing row and unchanged.

    SO WHAT THIS MODE COVERS IS THE HALF THAT DIFFERS: that the `-DSMOKE_PLAY` build links, boots,
    takes the machine and gets through the seam — none of which the capped build can witness for it,
    because a binary is only checked by being run."""
    prg = BUILD / OWN_RUN_BUILD
    status, log, rom = run_hatari(prg, run_vbls=OWN_RUN_BOOT_VBLS, trace=TIMELINE_TRACE,
                                  log_name=f"hatari-{OWN_RUN_MODE}.log")
    print(f"-- {OWN_RUN_MODE}: TOS={rom or 'bundled EmuTOS'} hatari exit={status} "
          f"--run-vbls {OWN_RUN_BOOT_VBLS} (full log in {OUT / f'hatari-{OWN_RUN_MODE}.log'})")
    problems = check_machine_health(status, log)
    events, why = timeline_events(log.splitlines())
    if why:
        raise SystemExit(f"FAIL: {OWN_RUN_MODE} left no readable write timeline ({why}) — with no "
                         f"record to read, the stream is the only surface this mode has")

    # THE SHIFTER'S BASE MOVED, which is the cheapest evidence that the reconstruction took the
    # video hardware: `install` and `chain_prologue` publish it, and a build that died before
    # either would leave TOS's own base standing for the whole window.
    state, moves = 0, 0
    for register, value, _ in events:
        moved = original.apply_base_write(state, register, value)
        if moved is not None and moved != state:
            moves += 1
        state = state if moved is None else moved
    # ...AND THE PALETTE THE TITLE SLICE PUT THERE. `clear_palette` writes sixteen zeros at $e4ea and
    # `set_palette` writes the depacked picture's own sixteen at $e540, so a chip left holding zeros
    # is a chain that got as far as the clear and no further — a refused load, or a depack that never
    # ran. This is the ONE surface a headless run of this build has for the file seam.
    pens = [(register, value) for register, value, _ in events
            if PEN_FIRST_REG <= register <= PEN_LAST_REG]
    chip = {}
    for register, value in pens:
        chip[register] = value
    lit = sum(1 for value in chip.values() if value)
    # ...AND THE MACHINE WAS STILL RUNNING AFTERWARDS. `vbl_handler` ticks the music every vertical
    # blank and the music writes the YM2149, so the PSG stream is the heartbeat — measured from the
    # LAST pen write onward, which is the instant the title slice finished. A hung or dead machine
    # emits nothing after it; one waiting at a fire gate emits for the rest of the window.
    last_pen = max((position for position, (register, _, _) in enumerate(events)
                    if PEN_FIRST_REG <= register <= PEN_LAST_REG), default=-1)
    after = len(events) - 1 - last_pen if last_pen >= 0 else 0
    checks = [
        ("the build took the video hardware", moves > 0,
         f"{moves} screen-base change(s) in the stream, ending at {state:#x}"),
        ("...and the title slice crossed the seam and put its palette on the chip",
         len(chip) == PALETTE_PENS and lit > 0,
         f"{len(chip)} of {PALETTE_PENS} pen registers written, {lit} of them non-zero — "
         f"clear_palette's sixteen zeros are what a chain that never reached set_palette leaves"),
        ("...and the machine was still ticking when the window closed", after >= OWN_RUN_ALIVE_EVENTS,
         f"{after} write events after the last pen write (floor {OWN_RUN_ALIVE_EVENTS}); the "
         f"vertical-blank handler's music tick is what produces them, so a dead machine leaves 0"),
        # ...AND IT NEVER ENDED, which is this build's whole contract and is asserted from the
        # ABSENCE of the file the ladder writes on its way out. A record here means a bound this
        # build is supposed to have lifted fired anyway.
        ("...and the ladder never ended, so no record was written",
         not (DISK / OWN_FILE).exists() and not (DISK / STATS_FILE).exists(),
         f"{OWN_FILE} and {STATS_FILE} are both absent — with every bound lifted the ladder has no "
         f"exit, which is what `atari/run.sh` documents (Ctrl-Q is how a person leaves)"),
    ]
    report(f"{OWN_RUN_MODE} — the interactive binary, booted headless", checks)
    problems += [f"{name}: {detail}" for name, ok, detail in checks if not ok]
    if problems:
        raise SystemExit("FAIL: " + "; ".join(problems))
    print(f"OK: {OWN_RUN_BUILD} — the binary `atari/run.sh` launches boots, takes the machine, loads "
          f"and depacks TITLESCR.RAD across the seam, puts its palette on the chip and then waits at "
          f"the title's fire gate with the vertical-blank handler still ticking. It waits for ever "
          f"there BY DESIGN (-DSMOKE_PLAY lifts the spin bound), so the frame loop and the ladder's "
          f"endings are `smoke.py ownplay`'s and the joystick is a person's.")


def own_script(directory, plain, frames, pokes, gates, after_release=None,
               arrival=M3_POKE_ANCHOR):
    """The debugger script for one driven pass: the fire gates, and optionally one ending.

    TWO MECHANISMS, BOTH SHARED WITH THE MODE THEY CAME FROM. The gates are `fire_gate_lines`, the
    boot mode's own, aimed at the addresses THIS run reported about itself; the ending is
    `ending_poke_breakpoint`, M3's own, which is where the beacon is stated and the arrival's default
    lives. `arrival` is passed through because the ESC passes drive at OWN_QUIT_POKE_ANCHOR and not
    at M3's — see that constant for the measurement."""
    directory = Path(directory)
    lines = fire_gate_lines(directory, plain, gates, after_release)
    if pokes:
        lines.append(ending_poke_breakpoint(directory, plain["image_base"], frames["capture_pc"],
                                            pokes, "OWNPOKE.INI", arrival=arrival))
    script = directory / "OWNCMD.INI"
    script.write_text("\n".join(lines) + "\n")
    return script


def drive_the_own_run(prg, plain, frames, tag, pokes, gates, what, after_release=None, trace=False,
                      withhold=(), arrival=M3_POKE_ANCHOR):
    """Boot the own-entry build again with `pokes` injected, and bring back its three records.

    `trace` IS OFF BY DEFAULT AND ASKED FOR BY THE PASSES THAT PARSE IT. Hatari's write trace is
    tens of megabytes over this mode's run — the boot chain alone depacks four pictures — and a log
    nothing reads is cost with no evidence in it. The two passes that count buffer publications turn
    it on; the ones that grade fields do not.

    `arrival` IS WHICH OF `capture_the_frame`'s ARRIVALS CARRIES THE POKE, defaulting to M3's. The
    two ESC passes pass OWN_QUIT_POKE_ANCHOR, because their screen-base rows are about the parity of
    the completed frame count; every argument here is passed on BY KEYWORD for that reason — an
    inserted parameter that bound `arrival` positionally would put those passes back on M3's anchor
    silently, and the row they exist for would go green without being able to fail."""
    with tempfile.TemporaryDirectory() as tmp:
        script = own_script(tmp, plain, frames, pokes, gates, after_release=after_release,
                            arrival=arrival)
        status, log, rom = run_hatari(prg, run_vbls=OWN_RUN_VBLS, parse=script,
                                      trace=TIMELINE_TRACE if trace else None,
                                      log_name=f"hatari-{OWN_MODE}-{tag}.log", withhold=withhold)
    record, why = read_own()
    m2, m2_why = read_m2()
    stats, stats_why = read_stats()
    for missing in (why, m2_why, stats_why):
        if missing:
            raise SystemExit(f"FAIL: {what} left no readable record ({missing})")
    if pokes and M3_POKE_BEACON not in log:
        raise SystemExit(f"FAIL: {what}'s poke breakpoint never fired — arrival {arrival} at "
                         f"capture_the_frame ({frames['capture_pc']:#x}) was never reached, so "
                         f"nothing was injected and this run is not a drive")
    if record["image_base"] != plain["image_base"]:
        raise SystemExit(f"FAIL: {what} put the image at {record['image_base']:#x} where the "
                         f"undriven run reported {plain['image_base']:#x} — every poke was aimed "
                         f"with the wrong address")
    return record, m2, stats, log, status, rom


def own_flips(log, image_base, what):
    """How many times `flip_screen` pointed the shifter at one of the game's two screen buffers.

    IT IS THE HEARTBEAT AND IT IS WHY THE TRACE IS ON. The record says the ladder took an ending and
    called `boot_load_stage` again; only the ORDERED write stream says the frame loop was still
    flipping buffers afterwards.

    THE TWO BUFFERS ARE COMPUTED AND NOT INFERRED, which is where this parts company with
    `mode_play`'s `displayed_buffers`. That function RANKS the addresses the shifter dwells in,
    which works for a build that enters the frame loop immediately — and does not work here:
    measured, an own-entry run spends its first ~500 vblanks in the boot chain's five loads and four
    depacks with TOS's own screen still on the bus, so the dwell ranking picked $3f8000 (TOS's) over
    one of the game's and the pair failed its own "WB_SCREEN_FRONT - WB_SCREEN_BACK apart" guard.
    This build reports where GEMDOS put its image, so the two addresses `wb_target_shifter_byte`
    publishes are simply `image_base + WB_SCREEN_LOW` and `+ WB_SCREEN_HIGH` — which is the same
    arithmetic the backend does, from the same two constants."""
    events, why = timeline_events(log.splitlines())
    if why:
        return None, f"{what}: {why}"
    buffers = {image_base + wb("SCREEN_LOW"), image_base + wb("SCREEN_HIGH")}
    publications, _, _ = base_writes(events, buffers, 0)
    return len(publications), None


def own_chain_rows(record, m2, stats, gates):
    """The rows every pass of this mode shares: the MACHINE was taken and given back, the boot chain
    ran, its gates were crossed, and the frame loop was entered.

    THE READ-BACK ROWS ARE FIRST AND THEY ARE THE ONES THIS BUILD MOST NEEDS. `readback_checks` is
    every mode's health scan — the two vectors installed and restored, the resolution and sync set
    and restored, the screen base published, the IKBD answering, the YM2149's port A deselected and
    put back — and this mode ran without them for a phase. It is the build that publishes its own
    palette and its own screen base, from its own boot chain, so a build that took the machine and
    did not set it up would produce a perfectly parseable record with nothing on the screen.

    `gates` is how many fire gates THIS pass can cross, which is not the same for all four (see
    OWN_FIRE_GATES): asserting the count per pass is what stops a pass arming five and silently
    crossing two."""
    return readback_checks(stats) + [
        # THE TWO PICTURE SLICES, AND NOT THE STAGE ONE. `stage_result` is the LAST stage load's,
        # and the ladder loads a stage on every reload and every restart — so it is a per-pass
        # reading and each pass grades it below. That the chain's FIRST stage load succeeded is
        # witnessed by the frame loop having been entered at all, three rows down.
        ("the boot chain's two picture slices ran on its own image",
         record["title_result"] == LOAD_COPYLOCK_RAN and record["credits_result"] == LOAD_OK,
         f"title={record['title_result']} credits={record['credits_result']} "
         f"(WB_LOAD_COPYLOCK_RAN={LOAD_COPYLOCK_RAN}, WB_LOAD_OK={LOAD_OK}); the last stage load "
         f"returned {record['stage_result']}"),
        ("...and the protection was left disarmed", record["copylock_arm_flag"] == COPYLOCK_CLEAR,
         f"copylock_arm_flag={record['copylock_arm_flag']:#x}"),
        ("...and the resource table arrived and was relocated",
         record["resource_signature"] == wb("RESOURCE_RELOCATED"),
         f"WB_RESOURCE_HEADER={record['resource_signature']:#x}, expected "
         f"{wb('RESOURCE_RELOCATED'):#x}"),
        ("the frame loop was entered over what the boot loaded", record["legs_run"] > 0,
         f"{record['legs_run']} leg(s), {record['frames_total']} frames, last shifter base "
         f"{m2['shifter_base']:#x}"),
        # THE FRAME LOOP'S OWN CLOCK, printed beside the whole run's so the difference is visible.
        # RB_VBL_TICKING is graded on the FORMER in this build (wonderboy_main.c says why): the boot
        # chain spends several hundred vblanks on five loads and four depacks, and a floor read off
        # `vbl_ticks_at_exit` would be satisfied by those alone whatever the frame loop did.
        ("...and the frame loop's own vblanks track its frames",
         record["frame_loop_vbl_ticks"] >= record["frames_total"] > 0,
         f"{record['frame_loop_vbl_ticks']} shim vblanks inside the legs over "
         f"{record['frames_total']} frames, out of {record['vbl_ticks_at_exit']} for the whole run "
         f"— the boot chain's are the difference"),
        ("...and every fire gate this pass arms was answered",
         record["fire_gates_crossed"] == gates and record["fire_waits_timed_out"] == 0,
         f"{record['fire_gates_crossed']} of {gates} gates crossed, "
         f"{record['fire_waits_timed_out']} timed out"
         + (f" (last at {record['fire_wait_timed_out_pc']:#x})"
            if record["fire_waits_timed_out"] else "")),
        # THE a5 THE LOOP WAS ENTERED WITH, and it belongs to the passes that ENTER it: the undriven
        # pass stops at the first gate, so its `entry_unwind` is the zero of a field never written
        # and a row asked there would be about nothing.
        the_unwind_agrees_with_the_measured_a5(record),
    ]


def own_stage_rows(record, row, what, index_row=None):
    """WHICH STAGE THE RUN ENDED ON, stated three ways: the sequence index, the stage number, and
    the overlay that is actually in memory — the last of which is only telling because `mode_ownplay`
    asserts, before any boot is paid for, that the two rows this mode is about do not share it.

    `index_row` IS THE ROW THE INDEX WAS STEPPED PAST, and it is normally the same row: a load that
    succeeded consumed the row whose overlay is now in memory. IT IS NOT THE SAME ON A REFUSAL, and
    that asymmetry is the whole of the retry policy's first residue — `stage_sequence_advance` steps
    the index at the TOP of the slice and the load can fail below it, so a refused reload leaves the
    index one row further on than the picture. Pass 5 drives that and names both rows, which is the
    difference between measuring the residue and being surprised by it."""
    seq = (row if index_row is None else index_row) + SEQ_ROWS_STEPPED
    other = SECOND_SEQ_ROW if row == FIRST_SEQ_ROW else FIRST_SEQ_ROW
    return [
        (f"{what}: the sequence index is one past row {seq - SEQ_ROWS_STEPPED}",
         record["level_seq_index"] == seq,
         f"WB_LEVEL_SEQ_INDEX={record['level_seq_index']}, expected {seq} "
         f"(stage_sequence_advance steps the index past the row it consumes)"),
        (f"{what}: the stage number is row {row}'s",
         record["stage_number"] == own_stage_number(row),
         f"WB_STAGE_NUMBER={record['stage_number']}, and WB_LEVEL_SEQ_TABLE row {row} carries "
         f"{own_stage_number(row)}"),
        (f"{what}: row {row}'s overlay is the one in memory",
         record["stage_entry_follow"] == overlay_entry_follow(row),
         f"the start record's entry position at WB_OVERLAY_DEPACK_DEST+{wb('START_FOLLOW_X')} is "
         f"{record['stage_entry_follow']:#010x}; {resource_name(overlay_resource(row))} inflates to "
         f"{overlay_entry_follow(row):#010x} and {resource_name(overlay_resource(other))} to "
         f"{overlay_entry_follow(other):#010x}"),
    ]


def own_prompt_rows(record, theirs, their_pens):
    """THE PROMPT PICTURE, and the screen base under it — the rows pass 4 gained in phase F.

    Through phase E this mode asserted that `boot_prompt_screen` reported WB_LOAD_OK and that the
    ladder went on. It never looked at what was on the screen, which is the one thing a data-disk
    prompt IS — so the picture is compared here against the SHIPPED binary's own, photographed at
    `$e4d6` by `original.py prompt` after driving the shipped side's ESC ending.

    AND THE BASE PUBLISH IS PINNED HERE FOR THE FIRST TIME. `../STATUS.md` batch 44 phase E §4
    measured two mutants SURVIVING every surface this project had — the prompt's screen-base publish
    deleted (P3) and its two bytes sent to each other's registers (P5) — because $ff8201/$ff8203 are
    off the loaded image and the oracle drops the write. `prompt_shifter_base` is those two registers
    READ BACK off the chip at the photograph's own instant, so a build that never published, or
    published the wrong buffer, reds.

    AND THE ROW IS A CHANGE AND NOT A VALUE, WHICH IT HAD TO LEARN THE HARD WAY. The first draft of
    this row asserted only that the base READS as WB_SCREEN_HIGH at the photograph — and P3 was
    applied to it and SURVIVED, green, on both ROMs. `flip_screen` publishes the buffer that has just
    become the front one, so after an EVEN number of frames the base is ALREADY WB_SCREEN_HIGH and
    the ending inherits it; the prompt's own publish then changes nothing an observer can see, which
    is the identical shape to the off-target hole it was written to close. The pass therefore drives
    ESC at an anchor whose frame count leaves the base on the OTHER buffer (OWN_QUIT_POKE_ANCHOR) and
    this row requires the base to have MOVED. A parity that ever changed would red here with that
    sentence rather than passing quietly."""
    want_base = record["image_base"] + original.WB_SCREEN_HIGH
    before = record["prompt_base_before"]
    rows = [
        ("the prompt was photographed at the buffer its own base names",
         record["prompt_captured_at"] == original.WB_SCREEN_HIGH,
         f"prompt_captured_at={record['prompt_captured_at']:#x}, WB_PROMPT_SCREEN_BASE is "
         f"WB_SCREEN_HIGH ({original.WB_SCREEN_HIGH:#x})"),
        # THE ROW THAT KILLS P3 AND P5, and it is the only one in this directory that can — but only
        # because it is a CHANGE. See the docstring: as a bare value it was measured surviving P3.
        ("...and $e498/$e4a0 MOVED the shifter there — both registers read back off the chip",
         before != want_base and record["prompt_shifter_base"] == want_base,
         f"the ending left the base at {before:#x} and the photograph found {record['prompt_shifter_base']:#x}; "
         f"the image is at {record['image_base']:#x} so WB_SCREEN_HIGH translates to {want_base:#x}"
         + ("" if before != want_base else
            " — THE ENDING ALREADY LEFT IT THERE, so this pass cannot see the publish at all: drive "
            "ESC at an anchor whose frame count leaves the base on the other buffer")),
        ("...and every pen read back as DATADISK.RAD's own palette row left it",
         record["prompt_pens_readback_failed"] == NO_PENS_FAILED,
         f"prompt_pens_readback_failed={record['prompt_pens_readback_failed']:#06x}"),
    ]
    # THREE-TUPLES, LIKE `prompt_control_rows` AND LIKE EVERY OTHER ROW LIST `report` IS HANDED.
    # `picture_rows` returns FOUR — the fourth is the SURFACE key, which exists so that the control
    # below can invert exactly the two rows a different picture can break — and pass 4 is not
    # inverting anything, so it dropped the key at the call site. Dropped here instead, where the
    # reason it exists at all is one line away.
    return rows + [(name, ok, detail)
                   for name, ok, detail, _ in picture_rows(theirs, their_pens, "data-disk prompt",
                                                           OWN_FILE, captures=OWN_PROMPT_CAPTURES)]


def require_the_prompt_pictures_differ(theirs, their_pens, control, control_pens, control_name):
    """The control's PREMISE, asked before any boot is paid for: the two shipped pictures differ.

    `mode_boot`'s rule and `own_stage_rows`' — a comparison whose two references are equal cannot
    tell them apart, so the thing that makes the control below a control is checked first, on
    artefacts that are already on disk, rather than after two 8,000-vblank runs.

    BOTH SURFACES, BECAUSE THE CONTROL INVERTS BOTH. `prompt_control_rows` requires the bitplanes
    row AND the pens row to break, and its whole reason for choosing the title picture over the
    credits one is a PEN COUNT — the credits screen ships DATADISK.RAD's own sixteen-word palette row
    and differs by exactly one pen. A premise that asked only about the 32000 bytes would let a
    future picture with an identical palette through, and the pens half of the control would then be
    a row that cannot fail. Returns (bytes differing, pens differing), which is what the mode
    prints."""
    for surface, mine, other, width in (("bitplanes", theirs, control, f"{SCREEN_BYTES} bytes"),
                                        ("palette row", their_pens, control_pens,
                                         f"{PALETTE_PENS} pens")):
        if mine == other:
            raise SystemExit(
                f"FAIL: the shipped data-disk prompt and the shipped {control_name} picture carry "
                f"the same {width} ({surface}), so a reader comparing our capture against either "
                f"could not tell them apart on that surface and the control below would have a row "
                f"that cannot fail")
    their_pen_words, control_pen_words = pen_words(their_pens), pen_words(control_pens)
    return (len(differing_bytes(theirs, control)),
            sum(1 for pen in range(PALETTE_PENS)
                if their_pen_words[pen] != control_pen_words[pen]))


def prompt_control_rows(control, control_pens, control_name):
    """THE CONTROL: our OWN prompt capture read against the game's OTHER picture, inverted.

    §13 controls the title differential by compiling a DIFFERENT resource into the same three calls
    and requiring both picture rows to break. This mode cannot do that: the resource the prompt asks
    for is `boot_prompt_screen`'s own operand inside a verified core, and a second `.PRG` differing
    by a `-D` would be a fifth own-entry build for one row. What it does instead is ask the SAME
    READER the same question about the same captured bytes against a picture the run certainly did
    not draw — one already photographed for another mode — and require the comparison to FAIL on
    both surfaces.

    THE TITLE PICTURE AND NOT THE CREDITS ONE, AND THAT IS A MEASUREMENT RATHER THAN A PREFERENCE.
    The credits screen is the obvious candidate — it is this mode's neighbour, it inflates to the
    same destination, and `mode_boot` already needs it. Measured against our prompt capture it breaks
    the bitplanes row by 12,437 of 32,000 bytes and the pens row by exactly ONE pen, because
    DATADISK.RAD and CREDITS.RAD ship the SAME sixteen-word palette row and the only thing that
    separates them is `$e5a2`'s own override of WB_CREDITS_PROMPT_PEN. A control that breaks a
    surface by one pen is a control that would stop breaking it the day that instruction moved. The
    title picture breaks the same two rows by 19,821 bytes and FIFTEEN of sixteen pens — §13's own
    figure, and for §13's own reason: pen 0 is black in both.

    THE INVERSION IS OVER OUR CAPTURE AND NOT OVER THE TWO SHIPPED FILES, which is the difference
    between a control and an arithmetic identity: `require_the_prompt_pictures_differ` establishes
    that the two references are not the same bytes, and this establishes that the reader which said
    "0 of 32000 differ" about one of them says something else about the other. A reader that always
    agreed, or a capture file left over from another run, fails here while passing above.

    Returns the rows AS INVERTED — a broken row is a PASS — so `report` prints them the way every
    other control in this file prints its own.

    AND IT REFUSES TO INVERT ANYTHING BUT THE TWO PICTURE SURFACES, which is `m2fault`'s structural
    rule and here it is load-bearing: `picture_rows` reports a MISSING capture as a single failed row
    rather than as two, and inverting that would turn "our prompt picture is not on the drive" into a
    green control. The keys are what tell the two apart, so the shapes are checked before the
    inversion."""
    rows = picture_rows(control, control_pens, f"{control_name} CONTROL", OWN_FILE,
                        captures=OWN_PROMPT_CAPTURES)
    if sorted(key for _, _, _, key in rows if key is not None) != sorted((BITPLANES, PENS)):
        raise SystemExit(
            "FAIL: the prompt control read something other than the two picture surfaces — "
            + "; ".join(f"{name}: {detail}" for name, _, detail, _ in rows)
            + ". Inverting that would report a MISSING or malformed capture as a green control")
    return [(f"the control: our prompt is NOT the {control_name} picture — {name}", not ok, detail)
            for name, ok, detail, _ in rows]


def mode_ownplay():
    """THE OWN-ENTRY PLAY: the boot loads the stage, and every ending comes back to it."""
    prg = BUILD / OWN_BUILDS[OWN_MODE]
    refuse_a_stale_build(prg, OWN_MODE, "own_stats")
    # THE TWO ROWS' OVERLAYS MUST DIFFER, asked BEFORE any boot is paid for (`mode_boot`'s rule):
    # every stage inflates its overlay to the same address, so a fingerprint the two rows share would
    # make "row N's overlay is the one in memory" true of both and the reload unobservable.
    if overlay_entry_follow(FIRST_SEQ_ROW) == overlay_entry_follow(SECOND_SEQ_ROW):
        raise SystemExit(
            f"FAIL: {resource_name(overlay_resource(FIRST_SEQ_ROW))} and "
            f"{resource_name(overlay_resource(SECOND_SEQ_ROW))} carry the same start-record entry "
            f"position, so this mode cannot tell a reload from a repeat")
    # THE SHIPPED SIDE'S TWO PICTURES, LOADED BEFORE THE FIRST BOOT IS PAID FOR — `mode_boot`'s
    # `require_the_shipped_side` rule. The prompt is what pass 4 compares against; the TITLE picture
    # is the control it is compared against second (`prompt_control_rows` measures why that one and
    # not the credits screen), and the premise that the two are not the same bytes is checked here
    # rather than after four runs.
    their_prompt, their_prompt_pens = shipped_picture(
        original.PROMPT_SCREEN_FILE, original.PROMPT_PENS_FILE, PROMPT_ANCHOR_MODE)
    control_picture, control_pens = shipped_picture(
        original.TITLE_SCREEN_FILE, original.TITLE_PENS_FILE, TITLE_MODE)
    control_bytes, control_pen_count = require_the_prompt_pictures_differ(
        their_prompt, their_prompt_pens, control_picture, control_pens, TITLE_MODE)
    plain, frames, plain_stats, plain_log, plain_status = measure_the_undriven_own_run(prg)
    problems = check_machine_health(plain_status, plain_log)

    # PASS TWO: the chain's own two gates answered, nothing else. The control for pass three. It
    # arms exactly what it can cross — the ladder never leaves the frame loop here, so the prompt's
    # gate and the chain's second walk are not reached and arming them would say nothing.
    record, m2, stats, log, status, rom = drive_the_own_run(
        prg, plain, frames, "fire", (), OWN_CHAIN_GATES, "the fire-only pass", trace=True)
    problems += check_machine_health(status, log)
    flips, why = own_flips(log, record["image_base"], "the fire-only pass")
    checks = own_chain_rows(record, m2, stats, OWN_CHAIN_GATES) + [
        ("the boot's own stage load ran the armed SPRITES.CRU load",
         record["stage_result"] == LOAD_COPYLOCK_RAN,
         f"boot_load_stage returned {record['stage_result']} "
         f"(WB_LOAD_COPYLOCK_RAN={LOAD_COPYLOCK_RAN})"),
        ("no ending was taken, so the stage did not move",
         record["reloads"] == 0 and record["restarts"] == 0
         and record["legs_run"] == LEGS_WITHOUT_AN_ENDING
         and record["last_ending"] == LOOP_RETURNED
         and record["stopped_at"] == OWN_STOP_FRAME_LIMIT,
         f"{record['reloads']} reloads, {record['restarts']} restarts, {record['legs_run']} leg(s), "
         f"last_ending={record['last_ending']} (WB_KEY_ACTIONS_RETURNED={LOOP_RETURNED}), "
         f"stopped_at={own_stop(record)}"),
        # THE ONE-LEG FLIP COUNT, which is pass three's baseline rather than a claim of its own.
        ("...and the frame loop flipped buffers", flips is not None and flips >= record["frames_total"],
         why or f"{flips} buffer publications over {record['frames_total']} frames — one leg's worth"),
    ] + own_stage_rows(record, FIRST_SEQ_ROW, "undriven")
    report(f"{OWN_MODE} pass 2 — FIRE ONLY: the control that says the stage moves for a reason",
           checks)
    print(f"   TOS={rom or 'bundled EmuTOS'} hatari exit={status}; {record['fire_gates_crossed']} "
          f"gates crossed, {record['frames_total']} frames (full log in "
          f"{OUT / f'hatari-{OWN_MODE}-fire.log'})")
    problems += [f"pass 2 {name}: {detail}" for name, ok, detail in checks if not ok]
    undriven_flips = flips or 0

    # PASS THREE: the round end, driven. It reloads a stage rather than restarting the chain, so it
    # crosses the same two gates the pass above does and no more — the reload enters `$e5ba` below
    # the credits gate.
    record, m2, stats, log, status, rom = drive_the_own_run(
        prg, plain, frames, ROUND_END_ENDING.tag, ROUND_END_ENDING.pokes, OWN_CHAIN_GATES,
        ROUND_END_ENDING.arm, trace=True)
    problems += check_machine_health(status, log)
    flips, why = own_flips(log, record["image_base"], "the round-end pass")
    checks = own_chain_rows(record, m2, stats, OWN_CHAIN_GATES) + [
        (f"{ROUND_END_ENDING.arm} left the frame loop", record["last_ending"] == ROUND_END_ENDING.code,
         f"last_ending={record['last_ending']} = {ROUND_END_ENDING.arm} "
         f"({ROUND_END_ENDING.code}); the original's own `jmp` goes to "
         f"{ROUND_END_ENDING.unwind:#x} and this ladder calls boot_load_stage"),
        ("...and boot_load_stage RAN AGAIN on target",
         record["reloads"] == 1 and record["stage_result"] != LOAD_DISK_ERROR,
         f"{record['reloads']} reload(s), the second stage load returned {record['stage_result']}"),
        ("...and the frame loop ran again after it",
         record["legs_run"] == LEGS_WITH_ONE_ENDING
         and record["stopped_at"] == OWN_STOP_FRAME_LIMIT,
         f"{record['legs_run']} legs, {record['frames_total']} frames, "
         f"stopped_at={own_stop(record)}"),
        # THE HEARTBEAT, AND IT IS A COMPARISON RATHER THAN A FLOOR. `mode_play` asks how far into
        # its event stream the LAST flip is, because that build never ends; this ladder does end —
        # it runs its second leg out and hands the machine back — so "still flipping at the cut-off"
        # is not the question. The question is whether the frame loop turned again AFTER the reload,
        # and the fire-only pass is the baseline that answers it: one leg there, two here, so a run
        # that reloaded and then stopped flipping fails this while satisfying every field above.
        ("...and it was still flipping buffers on the far side of the reload",
         flips is not None and flips > undriven_flips,
         why or f"{flips} buffer publications against the one-leg pass's {undriven_flips}, over "
                f"{record['frames_total']} frames in {record['legs_run']} legs"),
    ] + own_stage_rows(record, SECOND_SEQ_ROW, "after the reload")
    report(f"{OWN_MODE} pass 3 — THE ROUND END, DRIVEN: the ending that reloads the stage", checks)
    print(f"   TOS={rom or 'bundled EmuTOS'} hatari exit={status}; {record['fire_gates_crossed']} "
          f"gates crossed, {record['vbl_ticks_at_exit']} shim vblanks (full log in "
          f"{OUT / f'hatari-{OWN_MODE}-{ROUND_END_ENDING.tag}.log'})")
    problems += [f"pass 3 {name}: {detail}" for name, ok, detail in checks if not ok]

    # PASS FOUR: ESC, driven — the prompt slice and the whole chain again. It is the one pass that
    # crosses all five gates, because it is the one that walks the chain twice.
    record, m2, stats, log, status, rom = drive_the_own_run(
        prg, plain, frames, QUIT_ENDING.tag, QUIT_ENDING.pokes, OWN_FIRE_GATES, QUIT_ENDING.arm,
        after_release=release_the_quit_key(plain), trace=True, arrival=OWN_QUIT_POKE_ANCHOR)
    problems += check_machine_health(status, log)
    flips, why = own_flips(log, record["image_base"], "the ESC pass")
    checks = own_chain_rows(record, m2, stats, OWN_FIRE_GATES) + [
        (f"{QUIT_ENDING.arm} left the frame loop", record["last_ending"] == QUIT_ENDING.code,
         f"last_ending={record['last_ending']} = {QUIT_ENDING.arm} ({QUIT_ENDING.code}); the "
         f"original's own `jmp` goes to {QUIT_ENDING.unwind:#x}, which is show_data_disk_prompt"),
        ("...and the chain after it loaded a stage again",
         record["stage_result"] == LOAD_COPYLOCK_RAN,
         f"the stage load after the restart returned {record['stage_result']} "
         f"(WB_LOAD_COPYLOCK_RAN={LOAD_COPYLOCK_RAN})"),
        ("...and boot_prompt_screen drew the data-disk picture",
         record["prompt_result"] == LOAD_OK and record["restarts"] == 1,
         f"prompt_result={record['prompt_result']} (WB_LOAD_OK={LOAD_OK}, never run is "
         f"{BOOT_SLICE_NOT_RUN:#x}), {record['restarts']} restart(s)"),
        # THE LADDER WENT ROUND AND CAME BACK, which is a claim about LEGS and is what this row is
        # named for. The sequence row it came back to is `own_stage_rows`' four rows below.
        ("...and the ladder ran a SECOND leg after the restart",
         record["legs_run"] == LEGS_WITH_ONE_ENDING and record["stopped_at"] == OWN_STOP_FRAME_LIMIT,
         f"{record['legs_run']} legs, {record['frames_total']} frames, "
         f"stopped_at={own_stop(record)}"),
        # ...AND IT WAS STILL FLIPPING BUFFERS ON THE FAR SIDE OF IT, which is pass 3's own argument
        # applied to the ending that walks the WHOLE chain again rather than one stage load: every
        # field above can be satisfied by a ladder that restarted and then sat still. The baseline
        # is the same one-leg pass, and the comparison is against it rather than against a floor,
        # for the reason pass 3 states.
        ("...and it was still flipping buffers on the far side of the restart",
         flips is not None and flips > undriven_flips,
         why or f"{flips} buffer publications against the one-leg pass's {undriven_flips}, over "
                f"{record['frames_total']} frames in {record['legs_run']} legs"),
    ] + own_stage_rows(record, FIRST_SEQ_ROW, "after the restart — game_restart_reset put it back") \
      + own_prompt_rows(record, their_prompt, their_prompt_pens)
    report(f"{OWN_MODE} pass 4 — ESC, DRIVEN: the prompt, its PICTURE, and the whole chain again",
           checks)
    print(f"   TOS={rom or 'bundled EmuTOS'} hatari exit={status}; "
          f"{record['vbl_ticks_at_exit']} shim vblanks (full log in "
          f"{OUT / f'hatari-{OWN_MODE}-{QUIT_ENDING.tag}.log'})")
    problems += [f"pass 4 {name}: {detail}" for name, ok, detail in checks if not ok]

    # ...AND THE CONTROL FOR THE TWO PICTURE ROWS ABOVE, over the very bytes pass 4 captured.
    control = prompt_control_rows(control_picture, control_pens, TITLE_MODE)
    report(f"{OWN_MODE} pass 4 CONTROL — the same reader, the game's OTHER picture", control)
    print(f"   the two SHIPPED pictures differ in {control_bytes} of {SCREEN_BYTES} bytes and "
          f"{control_pen_count} of {PALETTE_PENS} pens, which is what makes BOTH inverted rows able "
          f"to fail")
    problems += [f"pass 4 control {name}: {detail}" for name, ok, detail in control if not ok]

    # PASS FIVE: THE SAME ROUND END, WITH THE STAGE IT ASKS FOR NOT ON THE DRIVE — the retry
    # policy's own arm, driven rather than argued.
    #
    # `run_the_own_entry`'s three STOP arms (OWN_STOP_RELOAD, OWN_STOP_RESTART, OWN_STOP_LEG_LIMIT)
    # exist because a refused load leaves TWO residues neither recoverable from the other, so the
    # ladder stops rather than retrying by calling the slice again (wonderboy_main.c's banner, and
    # ../STATUS.md §3). Through phase E's first draft NO PASS EXECUTED ANY OF THEM: three arms of the
    # switch, four green passes, and not one of them a witness.
    #
    # THE DATA IS REAL AND NOT FABRICATED, which is the whole shape of this pass. Nothing is poked
    # and no code is faulted: the drive simply does not carry OVALAY02.RAD, exactly as it would not
    # if a player had the wrong disk in — and the reconstruction's own `load_resource_by_index`
    # refuses on the name it asks for. Everything ABOVE the reload is unchanged from pass 3, which is
    # what makes the difference attributable: the chain runs, the frame loop runs a leg, the round
    # end fires, and then the reload has nowhere to come from.
    withheld = resource_name(overlay_resource(SECOND_SEQ_ROW))
    record, m2, stats, log, status, rom = drive_the_own_run(
        prg, plain, frames, "noreload", ROUND_END_ENDING.pokes, OWN_CHAIN_GATES,
        "the withheld-overlay pass", withhold=(withheld,))
    problems += check_machine_health(status, log)
    checks = own_chain_rows(record, m2, stats, OWN_CHAIN_GATES) + [
        (f"{ROUND_END_ENDING.arm} left the frame loop, as it did in pass 3",
         record["last_ending"] == ROUND_END_ENDING.code and record["reloads"] == 1,
         f"last_ending={record['last_ending']}, {record['reloads']} reload(s) attempted"),
        (f"...and the reload was REFUSED, because {withheld} is not on the volume",
         record["stage_result"] == LOAD_DISK_ERROR,
         f"boot_load_stage returned {record['stage_result']} "
         f"(WB_LOAD_DISK_ERROR={LOAD_DISK_ERROR})"),
        ("...and the ladder STOPPED there rather than retrying the slice",
         record["stopped_at"] == OWN_STOP_RELOAD,
         f"stopped_at={own_stop(record)} — the arm that records where it stopped and hands the "
         f"machine back"),
        # AND IT DID NOT GO ROUND AGAIN, which is the half a `stopped_at` alone does not say: a
        # ladder that retried would have entered the frame loop a second time and pass 3's own
        # two-leg reading is the number this is against.
        ("...and no second leg ran", record["legs_run"] == LEGS_WITHOUT_AN_ENDING,
         f"{record['legs_run']} leg(s) against pass 3's {LEGS_WITH_ONE_ENDING} over the same "
         f"ending — a retry would have run another"),
        # ...AND THE RESIDUE THE RETRY POLICY IS BUILT AROUND, MEASURED. `stage_sequence_advance`
        # steps WB_LEVEL_SEQ_INDEX at the TOP of the slice and the load refuses below it, so the
        # index is one past the row that was never loaded while the picture in memory is still the
        # PREVIOUS row's. That is exactly the state a caller which "retried" by calling the slice
        # again would skip a row from, and it is why this ladder stops instead — argued in
        # wonderboy_main.c's banner since phase E and driven on a 68000 here.
    ] + own_stage_rows(record, FIRST_SEQ_ROW, "the refused reload left row 0's picture in memory",
                       index_row=SECOND_SEQ_ROW)
    report(f"{OWN_MODE} pass 5 — THE WITHHELD OVERLAY: the retry policy's own stop arm", checks)
    print(f"   TOS={rom or 'bundled EmuTOS'} hatari exit={status}; {withheld} withheld; "
          f"{record['vbl_ticks_at_exit']} shim vblanks (full log in "
          f"{OUT / f'hatari-{OWN_MODE}-noreload.log'})")
    problems += [f"pass 5 {name}: {detail}" for name, ok, detail in checks if not ok]

    # PASS SIX: ESC AGAIN, WITH THE PROMPT'S OWN PICTURE NOT ON THE DRIVE — the LAST of
    # `run_the_own_entry`'s stop arms that anything here can reach, driven the way pass 5 drives its
    # sibling: real data, no poke past the ending, no injected fault. The volume simply does not
    # carry DATADISK.RAD, which is what a player with the wrong disk in the drive would have, and
    # `boot_prompt_screen` refuses on the name it asks for.
    #
    # IT ARMS TWO GATES AND NOT FIVE, and that is the shape of the claim rather than a setting: the
    # refusal happens BEFORE the prompt's own fire gate, so the chain's two on the way in are all
    # this pass can cross and `own_chain_rows` asserts the count. `release_the_quit_key` is
    # deliberately NOT passed either — it exists to let go of ESC at the prompt's gate so a SECOND
    # leg does not quit on its own first frame, and this pass has neither that gate nor a second leg.
    #
    # AND THE RESIDUE IS DIFFERENT FROM PASS 5'S, WHICH IS WHY BOTH ARMS ARE WORTH DRIVING. A refused
    # RELOAD leaves WB_LEVEL_SEQ_INDEX one row past the picture in memory, because
    # `stage_sequence_advance` steps it at the top of the slice and the load refuses below it. A
    # refused RESTART steps nothing at all — `boot_prompt_screen` touches no sequence state — so the
    # stage rows below are the SAME rows pass 2 asserts about a run that took no ending. What the
    # prompt DOES leave is on the hardware: `clear_palette` and then a screen base pointing at
    # WB_SCREEN_HIGH, the buffer whose picture never arrived, and the ladder stops before
    # `chain_prologue` can take the display back off it.
    withheld_prompt = resource_name(wb("RESOURCE_DATADISK"))
    record, m2, stats, log, status, rom = drive_the_own_run(
        prg, plain, frames, "noprompt", QUIT_ENDING.pokes, OWN_CHAIN_GATES,
        "the withheld-prompt pass", withhold=(withheld_prompt,), arrival=OWN_QUIT_POKE_ANCHOR)
    problems += check_machine_health(status, log)
    stranded_base = record["image_base"] + original.WB_SCREEN_HIGH
    base_before_the_prompt = record["prompt_base_before"]
    checks = own_chain_rows(record, m2, stats, OWN_CHAIN_GATES) + [
        (f"{QUIT_ENDING.arm} left the frame loop, as it did in pass 4",
         record["last_ending"] == QUIT_ENDING.code and record["restarts"] == 1,
         f"last_ending={record['last_ending']}, {record['restarts']} restart(s) attempted"),
        (f"...and the prompt was REFUSED, because {withheld_prompt} is not on the volume",
         record["prompt_result"] == LOAD_DISK_ERROR,
         f"boot_prompt_screen returned {record['prompt_result']} "
         f"(WB_LOAD_DISK_ERROR={LOAD_DISK_ERROR})"),
        ("...and the ladder STOPPED there rather than walking the chain again",
         record["stopped_at"] == OWN_STOP_RESTART,
         f"stopped_at={own_stop(record)} — the arm that records where it stopped and hands the "
         f"machine back"),
        ("...and no second leg ran", record["legs_run"] == LEGS_WITHOUT_AN_ENDING,
         f"{record['legs_run']} leg(s) against pass 4's {LEGS_WITH_ONE_ENDING} over the same "
         f"ending — a ladder that carried on would have run another"),
        # THE RESIDUE, HALF ONE: no picture. The refusal is ABOVE the depack and the palette set, so
        # `capture_the_prompt` is never reached and the drive carries no PROMPT.BIN — which is what
        # tells this stop apart from one that drew a picture and then failed to write it.
        ("...and no prompt picture was taken, because the refusal is above the depack",
         record["prompt_captured_at"] == 0 and not (DISK / OWN_PROMPT_FILE).exists(),
         f"prompt_captured_at={record['prompt_captured_at']:#x} and {OWN_PROMPT_FILE} is "
         f"{'present' if (DISK / OWN_PROMPT_FILE).exists() else 'absent'}"),
        # THE RESIDUE, HALF TWO: the display is left on the buffer the picture never reached. The
        # prompt publishes WB_SCREEN_HIGH before it asks for the file, and the ladder stops before
        # `chain_prologue`'s own publish would have taken it back to WB_SCREEN_LOW. Read by the shim
        # off $ffff8201/8203 in supervisor, BEFORE `teardown` puts TOS's base back.
        #
        # AND IT IS A MOVE AND NOT A VALUE, WHICH IS `own_prompt_rows`' LESSON APPLIED TO THIS ARM.
        # Pass 4's first draft asserted exactly this shape — the base READS as WB_SCREEN_HIGH — and
        # the P3 mutant (the publish deleted outright) came back GREEN on both ROMs, because
        # `flip_screen` publishes the buffer that has just become the front one and an even completed
        # frame count leaves the base already there. This pass drives the same ending at the same
        # anchor for that reason (OWN_QUIT_POKE_ANCHOR), and this row requires the base to have
        # MOVED, so the same mutant reddens here too. `prompt_base_before` is taken by `own_restart`
        # before the slice, which is above the refusal, so it is on the record on this path as well.
        ("...and $e498/$e4a0 MOVED the shifter onto WB_SCREEN_HIGH — the buffer the picture never "
         "arrived in",
         base_before_the_prompt != stranded_base and m2["shifter_base"] == stranded_base,
         f"the ending left the base at {base_before_the_prompt:#x} and the exit found "
         f"{m2['shifter_base']:#x}; the image is at {record['image_base']:#x}, so WB_SCREEN_HIGH is "
         f"{stranded_base:#x}. $e498/$e4a0 published it before the load and nothing after the "
         f"refusal moves it"
         + ("" if base_before_the_prompt != stranded_base else
            " — THE ENDING ALREADY LEFT IT THERE, so this pass cannot see the publish at all: drive "
            "ESC at an anchor whose frame count leaves the base on the other buffer")),
    ] + own_stage_rows(record, FIRST_SEQ_ROW,
                       "the refused prompt stepped NO sequence state — pass 5's residue inverted")
    report(f"{OWN_MODE} pass 6 — THE WITHHELD PROMPT: the restart arm's own stop", checks)
    print(f"   TOS={rom or 'bundled EmuTOS'} hatari exit={status}; {withheld_prompt} withheld; "
          f"{record['vbl_ticks_at_exit']} shim vblanks (full log in "
          f"{OUT / f'hatari-{OWN_MODE}-noprompt.log'})")
    problems += [f"pass 6 {name}: {detail}" for name, ok, detail in checks if not ok]

    if problems:
        raise SystemExit("FAIL: " + "; ".join(problems))
    print("OK: THE OWN-ENTRY PLAY — the reconstruction booted itself from the shipped program and "
          "its own seven files, entered the frame loop over the stage IT loaded, and took two of "
          "the frame loop's five endings back into the boot chain: a round end reloaded the next "
          "stage and ESC drew the data-disk prompt and started over. Two further passes withheld a "
          "file each and the ladder stopped where its retry policy says it stops, once for a "
          "reload and once for a restart. The "
          "level skip shares the round end's unwind and is M3's; the player's own two endings are "
          "driven host-side (test_game.py); the joystick is still a person's job (atari/run.sh).")
    print("    ...and the prompt it drew is the SHIPPED binary's own picture, byte for byte and pen "
          "for pen, against a capture taken at $e4d6 after driving the shipped side's ESC ending — "
          "with the base publish under it read back off the chip, which is the first surface in "
          "this project that can see that write at all. Two withheld-file passes then executed the "
          "ladder's reload and restart stop arms with data a player could really have.")


# ---- the runner's own exec line, parsed ------------------------------------------------------------
#
# THE ONE LINE NO HEADLESS MODE EXECUTES. Every check in this file boots Hatari with `run_hatari`'s
# arguments; `atari/run.sh` builds a DIFFERENT command — a screen, sound, a joystick, no fast-forward
# — and nothing ran it until a person did. Measured the hard way: `--sound on` sat in that line
# through thirteen green modes and is rejected by Hatari's own parser (`--sound` takes a FREQUENCY,
# off or 6000-50066), so the runner died at argument parsing while every headless mode stayed green.
#
# `--help` IS THE PROBE, and the ordering is measured rather than assumed: Hatari parses options left
# to right and `--help` prints the usage and stops WHERE IT IS REACHED, so every option before it has
# already been through its own parser (a bad value after `--help` is never seen; a bad value before it
# reports instead of the usage). A clean parse therefore prints the usage banner and no `Error` line —
# and the exit status says nothing, because `--help` itself exits 1.
RUNSH_MODE = "runsh"
RUNSH_PARSE_CHECK = "parsecheck"
RUNSH_ARGV_BEGIN = "RUNSH-ARGV-BEGIN"
RUNSH_ARGV_END = "RUNSH-ARGV-END"
HATARI_USAGE_RE = re.compile(r"^Usage:", re.M)
HATARI_PARSE_ERROR_RE = re.compile(r"^Error\b.*", re.M)
# The value that shipped, and the value that works. The control substitutes the first for the second
# in the runner's OWN argument list, so what is shown to fail is the real line and not a fixture.
SOUND_REJECTED = "on"


def hatari_parses(args):
    """(ok, why) for `hatari <args> --help` — did every option before the `--help` parse?"""
    done = subprocess.run(["hatari", *args, "--help"], stdin=subprocess.DEVNULL, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    error = HATARI_PARSE_ERROR_RE.search(done.stdout)
    if error:
        return False, error.group(0).strip()
    if not HATARI_USAGE_RE.search(done.stdout):
        return False, "no usage banner — --help was never reached, so nothing was proved parsed"
    return True, "the usage banner printed and no option reported an error"


def runsh_argv(output):
    """The exact argument list `run.sh` would have exec'd, out of what it printed."""
    inside = re.search(rf"^{RUNSH_ARGV_BEGIN}$(.*?)^{RUNSH_ARGV_END}$", output, re.M | re.S)
    if not inside:
        raise SystemExit(f"FAIL: run.sh {RUNSH_PARSE_CHECK} printed no argument list between "
                         f"{RUNSH_ARGV_BEGIN} and {RUNSH_ARGV_END} — this mode cannot know what it "
                         f"checked")
    return [line for line in inside.group(1).split("\n") if line]


def mode_runsh():
    """The interactive invocation, parsed — and shown to be able to fail.

    It restages `atari/disk/` for whichever build `run.sh` launches — the OWN-ENTRY one since batch
    44 phase E, which means the .PRG, its image and the ladder's seven resources — exactly as
    `run.sh` does, so it is not a mode to interleave with another one's run."""
    done = subprocess.run(["bash", str(HERE / "run.sh"), RUNSH_PARSE_CHECK], text=True,
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    OUT.mkdir(exist_ok=True)
    (OUT / "runsh-parse.log").write_text(done.stdout)
    argv = runsh_argv(done.stdout)
    # THE FLAG IS FOUND BY INDEX, and both halves of that matter. The guard is on `--sound` being
    # ABSENT and nothing else — an earlier draft also required the rejected VALUE to be missing, so a
    # future line that legitimately passed a value spelled the same way would have tripped it — and
    # the substitution replaces the word AFTER the flag rather than testing each word's predecessor,
    # which at index 0 asks about `argv[-1]` and reads the LAST element instead.
    if "--sound" not in argv:
        raise SystemExit("FAIL: run.sh's exec line no longer passes --sound at all — the control "
                         "below would be substituting into a flag that is not there")
    value_at = argv.index("--sound") + 1
    if value_at >= len(argv):
        raise SystemExit("FAIL: run.sh's exec line ends with --sound and no value — there is "
                         "nothing for the control to substitute")
    broken = list(argv)
    broken[value_at] = SOUND_REJECTED
    control_ok, control_why = hatari_parses(broken)
    checks = [
        ("run.sh's own exec line parses", done.returncode == 0,
         f"`bash atari/run.sh {RUNSH_PARSE_CHECK}` exited {done.returncode} over "
         f"{len(argv)} arguments: {' '.join(argv)}"),
        ("...and the check can fail", not control_ok,
         f"the same line with `--sound {SOUND_REJECTED}` — the value that shipped — "
         + (f"was accepted, so this probe proves nothing" if control_ok
            else f"is rejected: {control_why}")),
    ]
    report("runsh", checks)
    problems = [f"{name}: {detail}" for name, ok, detail in checks if not ok]
    if problems:
        print(done.stdout[-2000:])
        raise SystemExit("FAIL: " + "; ".join(problems))
    print("OK: runsh — the interactive command Hatari is actually given parses, and a run.sh that "
          "reintroduced the rejected value would be caught here rather than by a person")


# Which .PRG each mode boots, and which shipped-side artefact set it compares against. `m5` and
# `m5skew` share a build, as `m2` and `m2fault` do; `m5flash` is the only one whose shipped side is a
# different boot of the original, which is what the artefact PREFIX names.
M6_BUILDS = {"m6": "WB-m2.PRG", "m6rearm": "WB-m6rearm.PRG", "m6flash": "WB-m5flash.PRG",
             "play": "WB-play.PRG"}
M6_PREFIX = {"m6": "", "m6rearm": "", "m6flash": original.FRAME_PREFIXES[True]}
# `play` is the ONE M6 build that is not a timeline comparison, so it has no shipped-side prefix and
# `main` routes it separately. THE TWO LISTS ARE PINNED TO EACH OTHER rather than left to agree,
# which is `build.sh`'s own FRAME_MODES lesson in Python: a mode added to M6_BUILDS and forgotten
# here does not raise "unknown mode" — it falls through to the bottom of `main` and gets booted at
# M1's --run-vbls and checked by `m1_checks`, which reports read-back failures on a frame build.
PLAY_MODE = "play"
assert set(M6_BUILDS) - set(M6_PREFIX) == {PLAY_MODE}, (
    f"every M6 mode except {PLAY_MODE!r} needs a shipped-side prefix; "
    f"{sorted(set(M6_BUILDS) - set(M6_PREFIX) - {PLAY_MODE})} has none")
assert not set(M6_PREFIX) - set(M6_BUILDS), (
    f"{sorted(set(M6_PREFIX) - set(M6_BUILDS))} has a prefix but no build to boot")
PRG_FOR_MODE = {"m1": "WB-m1.PRG", "mono": "WB-m1.PRG", "novbl": "WB-novbl.PRG",
                "m2": "WB-m2.PRG", "m2fault": "WB-m2.PRG"}
M5_BUILDS = {"m5": "WB-m2.PRG", "m5skew": "WB-m2.PRG", "m5fault": "WB-m5fault.PRG",
             "m5flash": "WB-m5flash.PRG"}
M5_PREFIX = {"m5": "", "m5skew": "", "m5fault": "", "m5flash": original.FRAME_PREFIXES[True]}
# M3 drives the FRAME build — the section above says why the play build cannot be aimed at — and its
# control is the build whose `teardown` never gives the two vectors back.
M3_BUILDS = {M3_MODE: "WB-m2.PRG", M3_FAULT_MODE: "WB-m3fault.PRG"}
# Which `build.sh` mode produces each smoke mode's binary, for the message a missing build gets.
BUILD_FOR_MODE = {"mono": "m1", "m2fault": "m2", "m5": "m2", "m5skew": "m2", "m6": "m2",
                  "m6flash": "m5flash", M3_MODE: "m2"}



def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "m1"
    # `runsh` boots nothing itself — it asks run.sh for the command IT would boot — so it is routed
    # before the .PRG lookup below rather than being given a build it does not use.
    if mode == RUNSH_MODE:
        mode_runsh()
        return
    prg = dict(PRG_FOR_MODE, **M5_BUILDS, **M6_BUILDS, **M3_BUILDS, **TITLE_BUILDS,
               **BOOT_BUILDS, **OWN_BUILDS, **OWN_RUN_BUILDS).get(mode)
    if prg is None:
        raise SystemExit(__doc__)
    prg = BUILD / prg
    if not prg.exists():
        raise SystemExit(f"{prg} — run `bash atari/build.sh {BUILD_FOR_MODE.get(mode, mode)}` first")

    if mode in M3_BUILDS:
        mode_m3(mode)
        return

    if mode in BOOT_BUILDS:
        # TWO PASSES AND ITS OWN --run-vbls, so it routes before the single-boot modes below.
        mode_boot(mode)
        return

    if mode in OWN_RUN_BUILDS:
        # THE UNCAPPED BUILD, and it routes before the ladder's own mode because it shares neither
        # its passes nor its --run-vbls: it writes no record, so there is nothing to drive and
        # nothing to read back.
        mode_ownrun()
        return

    if mode in OWN_BUILDS:
        # SIX PASSES and its own --run-vbls, for `mode_boot`'s reason and one more: three of them
        # drive an ending, so the ladder has a whole second stage to load inside the window.
        mode_ownplay()
        return

    if mode in TITLE_BUILDS:
        # THE SHIPPED SIDE IS ASKED FOR BEFORE THE BOOT IS PAID FOR — `mode_boot`'s rule, and here
        # for a second reason. `title_checks` used to reach `shipped_picture` on its way to
        # `picture_rows`, so a fresh checkout with no `original.py title` behind it raised the
        # SHIPPED-side refusal at the very point `picture_rows`' own guard exists to diagnose the
        # LOCAL capture ("the run reached its own dump, so this is the capture write failing rather
        # than the program dying"). Front-loading it puts each failure back under the row that
        # explains it.
        shipped_picture(original.TITLE_SCREEN_FILE, original.TITLE_PENS_FILE, TITLE_MODE)
        # The title build runs the boot slice ONCE and then M1's vblank count, so it is bounded by
        # the M1 run length rather than the frame builds'.
        status, log, rom = run_hatari(prg)
        print(f"-- {mode}: TOS={rom or 'bundled EmuTOS'} hatari exit={status} "
              f"(full log in {OUT / 'hatari.log'})")
        mode_title(check_machine_health(status, log), mode)
        return

    if mode in M5_BUILDS:
        mode_m5([], mode, M5_PREFIX[mode])
        return

    if mode == PLAY_MODE:
        mode_play()
        return

    if mode in M6_PREFIX:
        mode_m6(mode, M6_PREFIX[mode], faulted=(mode == "m6rearm"))
        return

    frames = mode in ("m2", "m2fault")
    monitor = "mono" if mode == "mono" else "rgb"
    status, log, rom = run_hatari(prg, monitor, M2_RUN_VBLS if frames else RUN_VBLS)
    print(f"-- {mode}: TOS={rom or 'bundled EmuTOS'} monitor={monitor} "
          f"hatari exit={status} (full log in {OUT / 'hatari.log'})")

    problems = check_machine_health(status, log)
    if frames:
        mode_m2(problems, faulted=(mode == "m2fault"))
        return

    record, why = read_stats()
    if record is None:
        problems.append(why)
        report(mode, [])
        raise SystemExit("FAIL: " + "; ".join(problems))

    checks = m1_checks(record)

    if mode == "novbl":
        # The control INVERTS its verdict: a run that passes the comparison is the failure.
        report("novbl (negative control — these MUST fail)", checks)
        must_break, excluded = machine_driven(record)
        if excluded:
            print(f"   note {excluded}")
        held = [name for name, ok, _ in checks if ok and name in must_break]
        if held:
            raise SystemExit("FAIL: the control did not break the checks it exists to break: "
                             + ", ".join(held))
        if problems:
            raise SystemExit("FAIL: " + "; ".join(problems))
        print("OK: every machine-driven M1 check fails with the vector install suppressed")
        return

    if mode == "mono":
        # The HARDWARE control. Only the tempo byte is asserted, and only that it MOVED — the rest
        # of M1 is the `m1` mode's business and a mono boot is not required to reproduce it.
        moved = record["tick_drop_value"] == TICK_DROP_MONO
        report("mono (hardware control)", [
            ("tempo_drop_value read the MONO monitor", moved,
             f"WB_SND_TICK_DROP_VALUE={record['tick_drop_value']:#04x}, expected "
             f"{TICK_DROP_MONO:#04x} (a colour boot gives {TICK_DROP_50HZ:#04x})")])
        if not moved or problems:
            raise SystemExit("FAIL: " + "; ".join(problems + ([] if moved else
                             ["the tempo byte did not move — the GPIP read is not live"])))
        print("OK: the same binary chooses a different tempo arm on a different machine")
        return

    report("m1", checks)
    problems += [f"{name}: {detail}" for name, ok, detail in checks if not ok]
    if problems:
        raise SystemExit("FAIL: " + "; ".join(problems))
    print("OK: M1 — the reconstruction ran on a 68000, driven by the machine")


if __name__ == "__main__":
    main()
