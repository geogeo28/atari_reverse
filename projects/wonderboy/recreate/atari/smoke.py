#!/usr/bin/env python3
"""M1 and M2 — reconstructed Wonder Boy code on a 68000, asserted.

    bash atari/build.sh m1    && python3 atari/smoke.py m1
    bash atari/build.sh novbl && python3 atari/smoke.py novbl     # M1's negative control
    bash atari/build.sh m1    && python3 atari/smoke.py mono      # ...and its HARDWARE control

    python3 atari/original.py dump                                # M2 needs the image FIRST
    python3 atari/original.py frames                              # ...and the shipped side's frames
    bash atari/build.sh m2    && python3 atari/smoke.py m2        # THE FRAME DIFFERENTIAL
    bash atari/build.sh m2    && python3 atari/smoke.py m2fault   # ...its MIS-ANCHOR control

WHAT M2 CLAIMS: the reconstruction's own `game_main_loop` runs fifty-two frames on a real 68000 and
draws, at four anchored frames, the SAME 32000 bytes and the SAME sixteen pens as the shipped 1989
binary running the same fifty-two frames on the same emulated machine. Both sides' pictures are read
where the picture really is — ours out of the image at the address `flip_screen` published, theirs
off the shipped binary's own screen by `savebin` at a breakpoint on $4a0.

WHAT M1 CLAIMS is in README.md's milestone table and in wonderboy_main.c's header. In one sentence:
the reconstruction's own vertical-blank handler runs on a real machine at 50 Hz, and the two hardware
reads that steer the music tempo — the pair PORTABILITY.md §5 names as this project's false-green
surface — really answer for themselves.

THREE CONTROLS, because a check that cannot fail proves nothing, and one of them is not a code change
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
import os
import re
import struct
import subprocess
import sys
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


def c_constant(name):
    """One plain-integer `#define` out of wonderboy_main.c — the same rule as RB above.

    The shim's own constants have no header for test/layout.py to scrape, so this is how a number
    that lives in the C reaches the Python that checks it. A missing or non-literal define RAISES
    rather than defaulting: a check that silently substitutes its own idea of a constant is exactly
    the across-a-language-boundary drift CLAUDE.md §5 forbids."""
    found = re.search(r"^#define\s+%s\s+(0[xX][0-9a-fA-F]+|\d+)u?\b" % name,
                      (HERE / "wonderboy_main.c").read_text(), re.M)
    if not found:
        raise SystemExit(f"{name} is not a plain-integer #define in wonderboy_main.c")
    return int(found.group(1), 0)


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
    (DISK / "WB.PRG").write_bytes(Path(prg).read_bytes())
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
    if M2_BUILD_PREFIX in prg.name:
        if not pens.exists():
            raise SystemExit(f"{pens} is missing — the frame build stages the original's sixteen "
                             f"pens beside its image; rebuild with `bash atari/build.sh m2`")
        (DISK / "PENS.IMG").write_bytes(pens.read_bytes())


def run_hatari(prg, monitor="rgb", run_vbls=RUN_VBLS):
    """Boot `prg` headless, run to the end of --run-vbls, and return the MERGED output."""
    stage_drive(prg)

    rom = find_tos()
    args = ["hatari", "--sound", "off", "--fast-forward", "on", "--confirm-quit", "off",
            "--statusbar", "off", "--memsize", str(MEMSIZE_MB), "--monitor", monitor,
            "--run-vbls", str(run_vbls), "--harddrive", str(DISK), "--auto", "C:\\WB.PRG"]
    if rom:
        args[1:1] = ["--tos", rom]
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    done = subprocess.run(args, env=env, stdin=subprocess.DEVNULL, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    OUT.mkdir(exist_ok=True)
    (OUT / "hatari.log").write_text(done.stdout)
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
# Which built .PRG is a frame build, from its name. `m2` and `m2fault` boot the SAME binary, so the
# mode name cannot be the test and the artefact set has to key on the build instead.
M2_BUILD_PREFIX = "WB-m2"
# The trailing words are the ANCHOR LIST THE BINARY CARRIES — see wonderboy_main.c's `anchor_frames`.
# Its length is `M2_ANCHOR_MAX`, read out of the C so the two sides cannot disagree about the record's
# shape; `anchor_count` says how much of it is real. The size is checked against `record["bytes"]`,
# so a field added in C and not here is a loud parse error rather than a silently misread record.
M2_ANCHOR_MAX = c_constant("M2_ANCHOR_MAX")
M2_FORMAT = ">14I%dH" % M2_ANCHOR_MAX
M2_FIELDS = ("magic", "bytes", "image_base", "frames_requested", "frames_run", "loop_ending",
             "screen_front", "screen_base_published", "poll16_calls", "shim_vbl_ticks",
             "pens_readback_failed", "shifter_base", "screen_front_out_of_range", "anchor_count")
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


def shipped_frame(frame):
    """The shipped binary's picture and pens at `frame`, as `original.py frames` left them.

    The picture is cut out of the dumped screen region at the address the SHIPPED binary's own
    WB_SCREEN_FRONT names at that moment — read from the run, not assumed, because the two buffers
    alternate and picking the wrong one is exactly the mistake this comparison would not survive."""
    low, _ = original.SCREEN_REGION
    build = original.BUILD
    missing = [name for name in (f"OSCR{frame}.BIN", f"OFRONT{frame}.BIN", f"OPEN{frame}.BIN")
               if not (build / name).exists()]
    if missing:
        raise SystemExit(f"{', '.join(missing)} is missing — run `python3 atari/original.py frames`")
    front = struct.unpack(">I", (build / f"OFRONT{frame}.BIN").read_bytes())[0]
    screens = (build / f"OSCR{frame}.BIN").read_bytes()
    at = front - low
    if not 0 <= at <= len(screens) - SCREEN_BYTES:
        raise SystemExit(f"the shipped binary's frame {frame} front buffer is {front:#x}, outside "
                         f"the dumped region — original.py's SCREEN_REGION no longer covers it")
    return screens[at:at + SCREEN_BYTES], front, (build / f"OPEN{frame}.BIN").read_bytes()


def pen_words(blob):
    return [word & ST_PEN_MASK for word in struct.unpack(">%dH" % PALETTE_PENS, blob)]


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


def m2_checks(record, stats, anchors, shift=0):
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

    # THE M1 READ-BACKS APPLY TO THIS BUILD TOO, and an earlier draft of the M2 modes dropped them.
    # The frame build installs the same two vectors, sets the same video mode, publishes the same
    # screen base and hands the machine back the same way; STATS.BIN is written on this path exactly
    # as on M1's. Routing m2 past `read_stats` left all sixteen checks — including every teardown
    # restore — unasserted, so a frame build that never handed the machine back would have reported
    # a clean M2. The frame rows are what M2 ADDS, not what it replaces.
    want_attempted = mask(*BOOT_BITS, *TEARDOWN_BITS)
    add("read-backs ran", stats["readback_attempted"] == want_attempted,
        f"attempted {stats['readback_attempted']:#06x}, expected exactly {want_attempted:#06x}")
    unreachable, why = unreachable_readbacks()
    if why:
        print(f"   note {why}")
    add("read-backs passed", stats["readback_failed"] & ~unreachable == 0,
        f"failed {stats['readback_failed']:#06x}"
        + (" — " + ", ".join(n for n in RB if stats["readback_failed"] >> RB[n] & 1)
           if stats["readback_failed"] else "")
        + (f", of which {unreachable:#06x} is excluded" if unreachable else ""))

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
        theirs, front, their_pens = shipped_frame(against)
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


def shiftable_pairs(anchors, shift):
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
        mine, _, my_pens = shipped_frame(frame)
        theirs, _, their_pens = shipped_frame(against)
        if mine != theirs:
            keys.add((BITPLANES, frame, against))
        if pen_words(my_pens) != pen_words(their_pens):
            keys.add((PENS, frame, against))
    return keys


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "m1"
    prg = {"m1": "WB-m1.PRG", "mono": "WB-m1.PRG", "novbl": "WB-novbl.PRG",
           "m2": "WB-m2.PRG", "m2fault": "WB-m2.PRG"}.get(mode)
    if prg is None:
        raise SystemExit(__doc__)
    prg = BUILD / prg
    if not prg.exists():
        build_mode = {"mono": "m1", "m2fault": "m2"}.get(mode, mode)
        raise SystemExit(f"{prg} — run `bash atari/build.sh {build_mode}` first")

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
