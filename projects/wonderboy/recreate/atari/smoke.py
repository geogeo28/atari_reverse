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
import collections
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


def staged_block(addr, length, what):
    """`length` bytes at Ghidra address `addr`, out of the staged image the .PRG actually loaded.

    Not written down here and not taken from the .PRG's own report: these are the very bytes the
    reconstruction ran on. WB_STAGED_AT comes from project.toml for build.sh's reason — that file is
    where the 0x3f8 load base is argued for. `what` names the caller's subject in the failure."""
    base = int(re.search(r"^load_base\s*=\s*(0x[0-9a-fA-F]+)",
                         (REC / "project.toml").read_text(), re.M).group(1), 16)
    at = addr - base
    blob = (DISK / "WB.IMG").read_bytes()
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


def stage_resources():
    """Copy disk 1's two .RAD resources onto the emulated drive, under the names the table gives."""
    for index in DISK1_RESOURCES:
        name = resource_name(index)
        shipped = original.BIN / "disk1" / name
        if not shipped.exists():
            raise SystemExit(f"{shipped} is missing — WB_RESOURCE_FILE_TABLE row {index} names it "
                             f"and the title build asks the machine for it by that name")
        (DISK / name).write_bytes(shipped.read_bytes())


def stage_drive(prg):
    """Put the .PRG on the drive TOGETHER WITH THE IMAGE IT WAS BUILT AGAINST.

    THE IMAGE IS PART OF THE BUILD, NOT PART OF THE DRIVE. The modes stage different images — M1 the
    program plus seeds, M2 the original's post-boot RAM, 136,408 bytes against 523,272 — and each
    .PRG has its own length compiled in. Copying only the .PRG means `smoke.py m2` after
    `build.sh m1` boots the frame build over the M1 image; measured, and it failed as "no M2.BIN",
    which reads like a crash. build.sh keeps `WB-<mode>.IMG` beside `WB-<mode>.PRG` for this."""
    # EVERY output the program can write is deleted first. A stale FRAME.BIN from the previous build
    # is the shape of failure that PASSES: the run crashes, the comparison reads yesterday's picture,
    # and the mode reports a match.
    for stale in (STATS_FILE, M2_FILE, TITLE_FILE, M2_FRAME_FILE, M2_PENS_FILE,
                  M3_RESCUED_M2, M3_RESCUED_STATS):
        (DISK / stale).unlink(missing_ok=True)
    # ...AND EVERY RESOURCE, by extension rather than by name. A `.RAD` this mode did not stage is
    # one the PREVIOUS mode did, and a title build asks the machine for its file BY NAME — so a
    # leftover is a picture from another run that the depack would happily inflate. The names come
    # out of the image below, which is not written yet, so the sweep keys on what they all are.
    for stale in DISK.glob("*.RAD"):
        stale.unlink()
    (DISK / DRIVE_PRG).write_bytes(Path(prg).read_bytes())
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
        stage_resources()


# WHAT BOOTS, AND ON WHAT MACHINE — one spelling each, because `run.sh` needs the same answers and a
# GUI launcher that disagreed with the headless modes about any of them would be playing a different
# build on a different machine from the one every check in this file measured. `DRIVE_PRG` is the
# name on the emulated drive and `AUTO_BOOT` is how TOS is told to run it; they are pinned to each
# other below rather than written twice.
DRIVE_PRG = "WB.PRG"
AUTO_BOOT = "C:\\" + DRIVE_PRG
DEFAULT_MONITOR = "rgb"


def run_hatari(prg, monitor=DEFAULT_MONITOR, run_vbls=RUN_VBLS, parse=None, log_name="hatari.log",
               trace=None):
    """Boot `prg` headless, run to the end of --run-vbls, and return the MERGED output.

    `parse` is an optional Hatari DEBUGGER script, which is how M5 reaches the machine's own
    registers: the shim can read the shifter but not the YM-2149's file, and the debugger can. A run
    that carries one also gets `--frameskips 0`, because `screenshot` grabs the RENDERED surface and
    under --fast-forward Hatari skips rendering frames it still emulates — asking for every frame
    narrows the window in which a capture returns whichever frame was drawn last. It does NOT close
    it; atari/README.md §10 has the measurement of what is left."""
    stage_drive(prg)

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


def read_stats(name=STATS_FILE):
    """`name` is a parameter for M3's sake: a run whose machine is deliberately left broken can
    REBOOT and write a second record over the first, so M3 has the debugger move both records aside
    at the exit and reads them under those names."""
    path = DISK / name
    if not path.exists():
        return None, f"no {name} — the program never reached its own dump"
    blob = path.read_bytes()
    want = struct.calcsize(STATS_FORMAT)
    if len(blob) != want:
        return None, f"{name} is {len(blob)} bytes, expected {want}"
    record = dict(zip(STATS_FIELDS, struct.unpack(STATS_FORMAT, blob)))
    if record["magic"] != STATS_MAGIC:
        return None, f"{name} magic {record['magic']:#x} != {STATS_MAGIC:#x}"
    if record["bytes"] != want:
        return None, f"{name} says {record['bytes']} bytes, this parser expects {want}"
    return record, None


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
    """`name` is a parameter for the reason `read_stats` gives one."""
    path = DISK / name
    if not path.exists():
        return None, f"no {name} — the frame build never reached its own dump"
    blob = path.read_bytes()
    want = struct.calcsize(M2_FORMAT)
    if len(blob) != want:
        return None, f"{name} is {len(blob)} bytes, expected {want}"
    unpacked = struct.unpack(M2_FORMAT, blob)
    record = dict(zip(M2_FIELDS, unpacked))
    if record["magic"] != M2_MAGIC:
        return None, f"{name} magic {record['magic']:#x} != {M2_MAGIC:#x}"
    if record["bytes"] != want:
        return None, f"{name} says {record['bytes']} bytes, this parser expects {want}"
    # THE ANCHORS THE BINARY RAN, against the anchors this file is about to label its rows with.
    # Both are M2_ANCHOR_FRAMES — one compiled into the .PRG, one scraped from the source NOW — so
    # editing the list and running the smoke without rebuilding would otherwise compare slot 2 (the
    # binary's frame 51) against the shipped frame the new list names, and print the new label on
    # it. The count alone is not enough, because the failure that matters keeps the count.
    ran = list(unpacked[len(M2_FIELDS):][:record["anchor_count"]])
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


def readback_checks(record):
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
        # The common case is EQUAL, and a 32000-iteration Python comprehension to establish that is
        # ~4 anchors x 32000 interpreter steps per run for a `bytes` comparison the interpreter does
        # in one memcmp. Locate the differing bytes only once there are some.
        wrong = ([] if mine == theirs
                 else [at for at in range(SCREEN_BYTES) if mine[at] != theirs[at]])
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
    """The title build's record, or a failure that says which half of the run did not happen."""
    path = DISK / name
    if not path.exists():
        return None, f"no {name} — the title build never reached its own dump"
    blob = path.read_bytes()
    want = struct.calcsize(TITLE_FORMAT)
    if len(blob) != want:
        return None, f"{name} is {len(blob)} bytes, expected {want}"
    record = dict(zip(TITLE_FIELDS, struct.unpack(TITLE_FORMAT, blob)))
    if record["magic"] != TITLE_MAGIC:
        return None, f"{name} magic {record['magic']:#x} != {TITLE_MAGIC:#x}"
    if record["bytes"] != want:
        return None, f"{name} says {record['bytes']} bytes, this parser expects {want}"
    return record, None


def rad_header(index):
    """(packed, unpacked, filesize) of the SHIPPED .RAD file row `index` names, off the host disk.

    The two lengths the .PRG reports are read out of its own load buffer, i.e. out of bytes GEMDOS
    put there; these are the same two fields in the file as it sits in ../bin/disk1. Comparing them
    is what says the seam moved THE FILE and not merely something."""
    shipped = (original.BIN / "disk1" / resource_name(index)).read_bytes()
    return (int.from_bytes(shipped[RAD_HDR_PACKED_OFF:RAD_HDR_PACKED_OFF + 4], "big"),
            int.from_bytes(shipped[RAD_HDR_UNPACKED_OFF:RAD_HDR_UNPACKED_OFF + 4], "big"),
            len(shipped))


def shipped_title():
    """The shipped binary's title screen and pens, as `original.py title` left them."""
    names = (original.TITLE_SCREEN_FILE, original.TITLE_PENS_FILE)
    missing = [name for name in names if not (original.BUILD / name).exists()]
    if missing:
        raise SystemExit(f"{', '.join(missing)} is missing — run `python3 atari/original.py title`")
    return tuple((original.BUILD / name).read_bytes() for name in names)


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
    # THE GEOMETRY, PINNED RATHER THAN DESCRIBED. TITLE_DEPACK_DEST is the original's own operand
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

    missing = [name for name in (M2_FRAME_FILE, M2_PENS_FILE) if not (DISK / name).exists()]
    if missing:
        add("the captures were written", False,
            f"{', '.join(missing)} absent although {TITLE_FILE} was written — the run reached its "
            f"own dump, so this is the capture write failing rather than the program dying")
        return checks
    ours = (DISK / M2_FRAME_FILE).read_bytes()
    our_pens = (DISK / M2_PENS_FILE).read_bytes()
    if len(ours) != SCREEN_BYTES or len(our_pens) != PALETTE_BYTES:
        add("the capture is the right size", False,
            f"{len(ours)} frame bytes and {len(our_pens)} pen bytes, expected {SCREEN_BYTES} "
            f"and {PALETTE_BYTES}")
        return checks

    theirs, their_pens = shipped_title()
    wrong = [] if ours == theirs else [at for at in range(SCREEN_BYTES) if ours[at] != theirs[at]]
    rows = sorted({at // wb("SCREEN_LINE") for at in wrong})
    add("the title screen's bitplanes", not wrong,
        f"{len(wrong)} of {SCREEN_BYTES} bytes differ over {len(rows)} scanlines"
        + (f" {rows[:8]}" if rows else ""), BITPLANES)
    mine_pens, shipped_pens = pen_words(our_pens), pen_words(their_pens)
    wrong_pens = [pen for pen in range(PALETTE_PENS) if mine_pens[pen] != shipped_pens[pen]]
    add("the title screen's pens", not wrong_pens,
        f"pens {wrong_pens} differ" if wrong_pens
        else " ".join("%03x" % pen for pen in mine_pens), PENS)
    return checks


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
    `shifter_write_word(WB_SHIFTER_PALETTE, ...)` are adjacent statements whose argument is the
    already-decremented local, so swapping them writes the same word to RAM and the same colour to
    the chip — only later. `../STATUS.md` measures it surviving the whole differential suite and
    every snapshot this directory takes, and it is the last of the four shifter-sink mutants alive.
    The only thing that can see it is which of the two writes reached the bus first.

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
        ("this run reached no dump (it injects no input)", not (DISK / STATS_FILE).exists(),
         "with no joystick or key input, game_key_actions' three endings are unreachable, so the "
         "loop never breaks and the shim never hands the machine back"),
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
LONGWORD_BYTES = 4

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


def m3_script(directory, base, capture_pc, pokes):
    """The debugger script that injects `pokes` and then watches the machine outlive the program.

    Two top-level breakpoints. The first is `capture_the_frame`'s Nth arrival, where the two vectors
    are photographed AS THE SHIM LEFT THEM and the pokes go into the image. The second is the
    program's own `Pterm0`, which rescues the records and arms the two tail readings — the next
    vblank, where the two vectors and TOS's frame clock are read back, and Pterm+M3_TAIL_STEPS,
    where the clock is read again because one reading cannot show motion."""
    directory = Path(directory)
    poke_commands = [f"echo {M3_POKE_BEACON}",
                     m3_save(directory, M3_VBL_VECTOR_RUNNING, VEC_LEVEL4_VBL),
                     m3_save(directory, M3_ACIA_VECTOR_RUNNING, VEC_MFP_ACIA)]
    poke_commands += [entry.poke(base + entry.offset, entry.value) for entry in pokes]
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
    # The same-arrival guard and the breakpoint's own spelling are original.py's, for the reason
    # `our_capture_script` gives: a second spelling on this side is one that can quietly stop
    # matching the shipped side's.
    original.refuse_repeated_arrivals([(capture_pc, M3_POKE_ANCHOR)])
    lines = [
        original.anchor_breakpoint(capture_pc, M3_POKE_ANCHOR,
                                   original.action_file(directory, "M3POKE.INI", *poke_commands)),
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
    broken = [f"{name}: {detail}" for name, ok, detail in control if not ok]
    if broken:
        raise SystemExit("FAIL: the negative control did not hold, so no driven run below could "
                         "mean anything: " + "; ".join(broken))
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

    It restages `atari/disk/` for the play build, exactly as `run.sh` does, so it is not a mode to
    interleave with another one's run."""
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
    prg = dict(PRG_FOR_MODE, **M5_BUILDS, **M6_BUILDS, **M3_BUILDS, **TITLE_BUILDS).get(mode)
    if prg is None:
        raise SystemExit(__doc__)
    prg = BUILD / prg
    if not prg.exists():
        raise SystemExit(f"{prg} — run `bash atari/build.sh {BUILD_FOR_MODE.get(mode, mode)}` first")

    if mode in M3_BUILDS:
        mode_m3(mode)
        return

    if mode in TITLE_BUILDS:
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
