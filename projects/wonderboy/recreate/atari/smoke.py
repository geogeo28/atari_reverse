#!/usr/bin/env python3
"""M1, M2, M5 and M6 — reconstructed Wonder Boy code on a 68000, asserted.

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

    bash atari/build.sh play  && python3 atari/smoke.py play        # the PLAY build, booted headless
    bash atari/run.sh                                               # ...and played, with a screen

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
# "no STATS.BIN" for a build that was fine. 6000 puts the boot, the run, the two IKBD resets
# (~300 ms each) and a long tail after Pterm inside one run, at ~3 s of wall clock under
# --fast-forward. The tail is not slack: an incomplete hand-back only shows up after the program has
# gone, which is why every mode here runs to the END rather than stopping at the dump.
RUN_VBLS = 6000
# M2 runs 52 frames of the reconstruction on top of the same TOS boot. Measured: 583 vblanks for the
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


def staged(name, width=4):
    """A named image word, read out of the staged image the .PRG actually loaded.

    Not written down here and not taken from the .PRG's own report: these are the very bytes the
    reconstruction ran on. WB_STAGED_AT comes from project.toml for build.sh's reason — that file is
    where the 0x3f8 load base is argued for."""
    base = int(re.search(r"^load_base\s*=\s*(0x[0-9a-fA-F]+)",
                         (REC / "project.toml").read_text(), re.M).group(1), 16)
    at = wb(name) - base
    blob = (DISK / "WB.IMG").read_bytes()
    if not 0 <= at or at + width > len(blob):
        raise SystemExit(f"WB_{name} is outside the staged block — cannot read it back")
    return int.from_bytes(blob[at:at + width], "big")


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
    for stale in (STATS_FILE, M2_FILE, M2_FRAME_FILE, M2_PENS_FILE):
        (DISK / stale).unlink(missing_ok=True)
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


def read_stats():
    path = DISK / STATS_FILE
    if not path.exists():
        return None, "no STATS.BIN — the program never reached its own dump"
    blob = path.read_bytes()
    want = struct.calcsize(STATS_FORMAT)
    if len(blob) != want:
        return None, f"STATS.BIN is {len(blob)} bytes, expected {want}"
    record = dict(zip(STATS_FIELDS, struct.unpack(STATS_FORMAT, blob)))
    if record["magic"] != STATS_MAGIC:
        return None, f"STATS.BIN magic {record['magic']:#x} != {STATS_MAGIC:#x}"
    if record["bytes"] != want:
        return None, f"STATS.BIN says {record['bytes']} bytes, this parser expects {want}"
    return record, None


# ---- M2: the frame differential -----------------------------------------------------------------
#
# A SECOND RECORD RATHER THAN FOUR MORE FIELDS IN STATS.BIN — wonderboy_main.c's reason: this file
# checks STATS.BIN's size against its format string, so a record that grew per build mode would make
# the M1 parser's own version check fire on an M2 run. Two records, two magics, two readers.
M2_FILE = "M2.BIN"
M2_FRAME_FILE = "FRAME.BIN"
M2_PENS_FILE = "PENS.BIN"
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
SCREEN_BYTES = wb("SCREEN_LINE") * wb("SCREEN_SCANLINES")
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


def read_m2():
    path = DISK / M2_FILE
    if not path.exists():
        return None, f"no {M2_FILE} — the frame build never reached its own dump"
    blob = path.read_bytes()
    want = struct.calcsize(M2_FORMAT)
    if len(blob) != want:
        return None, f"{M2_FILE} is {len(blob)} bytes, expected {want}"
    unpacked = struct.unpack(M2_FORMAT, blob)
    record = dict(zip(M2_FIELDS, unpacked))
    if record["magic"] != M2_MAGIC:
        return None, f"{M2_FILE} magic {record['magic']:#x} != {M2_MAGIC:#x}"
    if record["bytes"] != want:
        return None, f"{M2_FILE} says {record['bytes']} bytes, this parser expects {want}"
    # THE ANCHORS THE BINARY RAN, against the anchors this file is about to label its rows with.
    # Both are M2_ANCHOR_FRAMES — one compiled into the .PRG, one scraped from the source NOW — so
    # editing the list and running the smoke without rebuilding would otherwise compare slot 2 (the
    # binary's frame 51) against the shipped frame the new list names, and print the new label on
    # it. The count alone is not enough, because the failure that matters keeps the count.
    ran = list(unpacked[len(M2_FIELDS):][:record["anchor_count"]])
    want_anchors = original.anchor_frames()
    if ran != want_anchors:
        return None, (f"{M2_FILE} was built for anchors {ran} but wonderboy_main.c now says "
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
        ("read-backs ran", record["readback_attempted"] == want_attempted,
         f"attempted {record['readback_attempted']:#06x}, expected exactly {want_attempted:#06x}"),
        ("read-backs passed", record["readback_failed"] & ~unreachable == 0,
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
    add("read-backs ran", record["readback_attempted"] == want_attempted,
        f"attempted {record['readback_attempted']:#06x}, expected exactly {want_attempted:#06x}")
    add("read-backs passed", record["readback_failed"] == 0,
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
MACHINE_DRIVEN = ("read-backs passed", "vbl_handler ran on the machine",
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
    **iff the image base's middle byte carries** — measured on the frame builds, `0x4a600` under
    TOS 1.04 carries and `0x53000` under EmuTOS does not, so the same binary produces 52 transients
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
# Which `build.sh` mode produces each smoke mode's binary, for the message a missing build gets.
BUILD_FOR_MODE = {"mono": "m1", "m2fault": "m2", "m5": "m2", "m5skew": "m2", "m6": "m2",
                  "m6flash": "m5flash"}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "m1"
    prg = dict(PRG_FOR_MODE, **M5_BUILDS, **M6_BUILDS).get(mode)
    if prg is None:
        raise SystemExit(__doc__)
    prg = BUILD / prg
    if not prg.exists():
        raise SystemExit(f"{prg} — run `bash atari/build.sh {BUILD_FOR_MODE.get(mode, mode)}` first")

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
