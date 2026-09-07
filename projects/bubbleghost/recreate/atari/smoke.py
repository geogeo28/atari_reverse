#!/usr/bin/env python3
"""smoke.py — judge BUBBLE.PRG on a real 68000 against the six observable surfaces.

    bash atari/build.sh title      && python3 atari/smoke.py title       # the gate
    bash atari/build.sh titlefault && python3 atari/smoke.py titlefault  # control: one colour pen
    bash atari/build.sh titlepoke  && python3 atari/smoke.py titlepoke   # control: one image word
    bash atari/build.sh titleisr   && python3 atari/smoke.py titleisr    # control: no Timer C
    bash atari/build.sh title floppy && python3 atari/smoke.py floppy    # the bootable volume

WHAT IT COMPARES. Two Hatari runs, at the same memory size on the same TOS: OURS, the reconstructed
program booting from a GEMDOS C: drive with the game's own data files on a floppy in A:; and THE
ORIGINAL, `bin/GHOST.PRG` booting the same way with the protected `.stx` in A: — which is
`../../tools/boot_ghost.py`'s recipe, unchanged, because a comparison between two differently
configured machines is a comparison of the configurations.

THE TWO ANCHORS ARE THE SAME PLACE IN THE SAME PROGRAM. Ours is `bg_anchor`, entered once the menu
is drawn; the original's is `menu_read_key_and_fold` @ 0x116c4 — the slice boundary immediately
after `title_menu_open`, where the original has drawn the same menu and is about to block on a key
it never gets. The original's address is not known until it exists: the shipped program is encrypted
against the protection track and decrypts itself into RAM, so the run polls RAM for the plaintext
(`locate_by_signature`, as `boot_ghost.py` does), and every address is then that load base plus a
Ghidra offset. Both sides therefore stop at a MOMENT, and neither settle is a wall clock.

THE SURFACES ARE docs/on-target-execution.md's, and each check below names the one it belongs to:

  exit status + log        Hatari's return code and its own fault lines, on BOTH sides, plus the
                           program's own record complete to its 'DONE' tail
  memory                   the 32,000-byte displayed framebuffer, ours against a `savebin` of the
                           original's — the strongest surface here, and the one that mirrors the
                           differential — and every field of the record the boot owes a value
  hardware-state vector    the sixteen colour registers, $ff8260 and the video base read off the
                           chip on BOTH sides at their anchors, and `Physbase`/`Logbase` read back
                           against what the shim published
  trap ledger              `--trace gemdos`: our Fopen/Fread/Fclose sequence against the original's,
                           compared by LENGTH as well as content
  timelines                the vertical blanks each side spends reaching its anchor — REPORTED, not
                           asserted, and the report says why
  rendered pixels          a Hatari screenshot of each side, byte for byte

THE THREE NEGATIVE CONTROLS each fault ONE thing and name the surfaces that must go red for it:

  titlefault   one colour register corrupted on its way to the shifter -> the hardware-state vector
               and the rendered pixels. It XORs white to YELLOW and not to black, because a capture
               with one colour is rejected before the two pictures are ever compared — which is how
               the first draft of this control left the picture COMPARISON unexercised.
  titlepoke    one word of the staged program XORed, in the first menu line's text -> the displayed
               framebuffer against the original's, and the rendered pixels. The pens do not move.
  titleisr     the sound engine installed in the image and not on the machine's $114 -> the record:
               no tick fires and the vector at the anchor is still TOS's.

Every other check must stay green under every control: one that only required "something failed"
would pass on a build that crashed.
"""
import re
import shutil
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]                       # projects/bubbleghost
RECREATE = HERE.parent                          # projects/bubbleghost/recreate
REPO = PROJECT.parents[1]
sys.path.insert(0, str(REPO / "tools"))

from hatari_headless import (                                            # noqa: E402
    HeadlessSession, action_file, await_file, distinct_colours, locate_by_signature, log_faults,
    require_gemdos_tos, same_picture, settle_chain,
)

TOS_ROM = REPO / "tools" / "hatari" / "TOS104US.img"
BIN = PROJECT / "bin"
DISK = HERE / "disk"
OUT = HERE / "out"

# ================================================================================================
# ONE DEFINITION ACROSS EVERY LANGUAGE BOUNDARY (CLAUDE.md §5)
#
# Nothing below is retyped. `build.sh` owns the machine's size because its own size gate is their
# first consumer; the cores' headers own every address and every extent of the program, because the
# cores are what the addresses are FOR. A number typed here would be a fourth copy that nothing
# compares, and this file's whole job is to compare.
# ================================================================================================
BUILD_SH = HERE / "build.sh"
GLOBALS_H = RECREATE / "include" / "globals.h"
BLIT_H = RECREATE / "include" / "blit.h"
FRONTEND_H = RECREATE / "include" / "frontend.h"
SHIM_OS_H = HERE / "shim_include" / "os.h"


def scrape_build_constant(name):
    match = re.search(rf"^{name}=(\d+)", BUILD_SH.read_text(), re.MULTILINE)
    if not match:
        raise SystemExit(f"ERROR: no {name} in {BUILD_SH} — this check has no budget to weigh "
                         f"against, and a check with no number passes everything")
    return int(match.group(1))


def scrape_define(header, name):
    """One `#define NAME <number>` out of a C header, as an int. A missing one is fatal."""
    match = re.search(rf"^#define\s+{name}\s+\(?(-?0[xX][0-9a-fA-F]+|-?\d+)u?\)?\b",
                      header.read_text(), re.MULTILINE)
    if not match:
        raise SystemExit(f"ERROR: no `#define {name}` in {header} — this file reads it rather than "
                         f"carrying its own copy, and a copy nothing compares is how the two drift")
    return int(match.group(1), 0)


MEMSIZE_MB = scrape_build_constant("MEMSIZE_MB")
TPA_1MB_BYTES = scrape_build_constant("TPA_1MB_BYTES")
STACK_RESERVE_BYTES = scrape_build_constant("STACK_RESERVE_BYTES")
TPA_MEASURED_AT_MB = 1

LOAD_BASE = scrape_define(GLOBALS_H, "BG_LOAD_BASE")       # a Ghidra address is this plus an offset
A4_BASE = scrape_define(GLOBALS_H, "A4_BASE")              # the crt0's own answer
A_screen_phys = scrape_define(BLIT_H, "A_screen_phys")
A_screen_back = scrape_define(BLIT_H, "A_screen_back")
SCREEN_BYTES = scrape_define(BLIT_H, "SCREEN_BYTES")
A_text_menu_game = scrape_define(FRONTEND_H, "A_text_menu_game")
PICTURE_BYTES = scrape_define(FRONTEND_H, "PICTURE_BYTES")   # ...and the 32-byte palette behind it
PALETTE_BYTES = scrape_define(FRONTEND_H, "PALETTE_BYTES")
IMAGE_BYTES = scrape_define(SHIM_OS_H, "BG_TARGET_IMAGE_BYTES")
SCREEN_BASE = scrape_define(SHIM_OS_H, "BG_TARGET_SCREEN_BASE")
HEAP_BASE = scrape_define(SHIM_OS_H, "BG_HEAP_BASE")
HEAP_LIMIT = scrape_define(SHIM_OS_H, "BG_HEAP_LIMIT")
IMAGE_ALIGN = scrape_define(HERE / "bubble_main.c", "IMAGE_ALIGN")

# THE ORIGINAL'S ANCHOR, and the one address in this file that no header carries. It is the slice
# boundary `[0x116c4, 0x11700)` — `../names.txt`'s plate at 0x116c4 and `../src/frontend.c`'s
# `menu_read_key_and_fold` both name it: "one Cnecin, Setscreen(log=screen_back), and the fold to
# upper case". The instruction before it is the last of `title_menu_open`, which is exactly where
# our own `bg_anchor` stands.
ORIGINAL_ANCHOR_PC = 0x116C4

# ...AND ITS VOICE ANCHOR, the second address in that class: `game_top_loop`'s `jsr play_voice`
# @ 0x10232, the instruction that hands control to GHOST.LOA. `show_presentation` has already loaded
# the presentation's palette three calls earlier, so the chip must be showing GHOST.PRE's colours
# HERE — which is exactly what the XBIOS door was built for and what a reissue made after this call
# returned could not do. Ours is `enter_the_voice_player`, whose address the anchor table carries.
ORIGINAL_VOICE_PC = 0x10232

# ...and the first frame of a room, for the `game` mode: `game_top_loop`'s `jsr game_frame_update`
# @ 0x1078e, the instruction the room loop's first pass reaches. Ours is `game_frame_update` itself.
ORIGINAL_ROOM_FRAME_PC = 0x1078E

# THE MENU'S OWN KEYS, as ST scancodes. `menu_read_key_and_fold` folds to upper case, so a lower-case
# G is the same key (../src/frontend.c); the digit chooses the player count.
KEY_G = 0x22
KEY_ONE = 0x02

RUN_VBLS = 12000                 # ~240 s of emulated time: a hard cap, not a schedule. The original
                                 # is the slower side and reaches its anchor in about 1,600, so the
                                 # cap is ~7x the run — see atari/README.md, "the two anchors".
ANCHOR_SETTLE_VBLS = 4           # stop-then-shoot: the display is built scanline by scanline
BLANK_COLOUR_COUNT = 1           # a capture with one colour is a photograph of nothing

# Hatari 2.6.1 prints "Bus Error" and "Address Error" with a capital E, and the shared marker list
# in tools/hatari_headless.py spells them lower-case — so it matches nothing. Measured, not assumed:
# `check_the_fault_scan_can_fail` runs this list over a real fault line every run.
FAULT_MARKERS = ("Bus Error", "Address Error", "CPU halted", "Failed to load", "Not a disk image")
# ...and TOS's own boot-time probes past the end of RAM are dropped BY THEIR ROM PC, never by
# failing to see them.
TOS_ROM_PC = re.compile(r"PC=\$(e0|fc)[0-9a-f]{4}\b")

# ---- what the run writes back, and what the debugger takes ------------------------------------
# BASE.BIN is `bubble_main.c`'s `enum bg_anchor_slot`, one longword per slot: three runtime
# addresses to break on and one to read a counter out of. The two files agree by the COUNT being
# asserted rather than by anyone counting, exactly as the record's fields do.
ANCHOR_TITLE_HOLD = 0
ANCHOR_VOICE_ENTRY = 1
ANCHOR_ROOM_FRAME = 2
ANCHOR_PLAY_TALLY = 3
ANCHOR_IMAGE_BASE = 4
ANCHOR_SLOTS = 5

# ...and `bubble_main.c`'s `enum bg_play_tally_slot`, the two longwords ANCHOR_PLAY_TALLY points at.
TALLY_MENU_OPENS = 0
TALLY_GAME_FRAMES = 1
TALLY_SLOTS = 2

FILE_ANCHOR_BASE = "BASE.BIN"
FILE_SCREEN_DUMP = "SCREEN.BIN"
FILE_STATE_RECORD = "STATE.BIN"

HW_PALETTE_BASE = 0xFFFF8240
HW_SHIFTER_MODE = 0xFFFF8260
HW_SCREEN_BASE_HIGH = 0xFFFF8201     # bits 23-16; $ff8203 holds 15-8 and there is no low byte
PALETTE_PENS = 16
PEN_BYTES = 2
SHIFTER_PEN_MASK = 0x777             # three bits a gun; a CPU read returns the fourth as noise
SHIFTER_REZ_MASK = 0x03
ST_LOW_RESOLUTION = 0

# ---- the record STATE.BIN carries, by field index ----------------------------------------------
# `bubble_main.c`'s `enum bg_record_field`, in order. The two files agree by the LENGTH being
# asserted rather than by anyone counting: a field inserted on one side reds `check_the_record`.
RECORD_FIELDS = """MAGIC IMAGE_BASE IMAGE_BYTES PROGRAM_BYTES A4_BASE LOW_RESOLUTION SCREEN_PHYS
SCREEN_BACK PUBLISHED_PHYSBASE READBACK_PHYSBASE PHASE_REACHED FILE_OPENS FILE_OPEN_FAILURES
FILE_REFUSALS FILE_WRITE_FAILURES SHIM_FILE_OPENS SHIM_FILE_FAILURES MALLOC_CALLS HEAP_POINTER
HW_WRITES VDI_CALLS AES_CALLS VDI_RASTER_COPIES TIMER_C_TICKS TIMER_C_CHAIN TIMER_C_SAVED
TIMER_C_VECTOR TRAP9_VECTOR CONTERM_AT_ANCHOR ENTRY_RESOLUTION READBACK_LOGBASE VOI_BUFFER_OFFSET
VOI_POINTER_MACHINE TPA_LOW TPA_HIGH KEPT_TOP MSHRINK_RESULT IMAGE_HEADROOM GUARD_DIRTY FAULT_PEN
FAULT_IMAGE_WORD FAULT_NO_TIMER_C TAIL""".split()
RECORD_MAGIC = 0x42474D31            # 'BGM1'
RECORD_TAIL = 0x444F4E45             # 'DONE'
PHASE_HANDED_BACK = 10               # the last of `enum bg_phase`
NO_PEN_FAULT = 0xFFFFFFFF            # what a shipped build files in FAULT_PEN

# What the boot is known to do, and what a check therefore predicts EXACTLY rather than bounds.
EXPECTED_FILE_OPENS = 6              # LOA, VOI, PRE, DAT, SCR, DEM — the GAME's own six
EXPECTED_OPEN_FAILURES = 1           # A:GHOST.SCR: the hall of fame does not exist on a fresh disk
# ...and the SHIM's own, counted apart: BASE.BIN (created), GHOST.IMG (opened), SCREEN.BIN
# (created). STATE.BIN's own create is the call AFTER the record is filled, so it is not in it.
EXPECTED_SHIM_OPENS = 3
EXPECTED_MALLOC_CALLS = 11           # MEASURED on the boot path; the bump below is the other half
EXPECTED_HEAP_BYTES = 0x3F310        # ...and where those seven blocks left the arena's pointer
EXPECTED_VDI_CALLS = 68              # v_opnvwk + v_clrwk + 60 raster grabs + 6 menu-text calls
EXPECTED_AES_CALLS = 3               # appl_init, graf_handle, graf_mouse
EXPECTED_RASTER_COPIES = 60          # build_sprite_bank's cell grabs
EXPECTED_HW_WRITES = 2               # the MFP vector register: once by install_sound_vectors, once
                                     # by remove_sound_vectors at the hand-back. build.sh's
                                     # hardware-door gate pins the CALL SITES this counts.

# ---- the original's side ------------------------------------------------------------------------
ORIGINAL_STX = REPO / "gw" / "dumps" / "bubble_ghost" / "bubble_ghost.stx"
ORIGINAL_PRG = "C:\\GHOST.PRG"
ORIGINAL_PLAIN = BIN / "GHOST_PLAIN.PRG"
ORIGINAL_LOAD_POLL_SECONDS = 1.0
ORIGINAL_LOAD_DEADLINE_SECONDS = 90.0

AWAIT_DEADLINE_SECONDS = 240.0
POLL_SECONDS = 0.25

# ---- the bootable floppy -------------------------------------------------------------------------
FLOPPY_IMAGE = DISK / "BUBBLE.ST"
DESKTOP_INF = "DESKTOP.INF"          # what TOS's desktop reads to open its window on A:\
FLOPPY_DEADLINE_SECONDS = 120.0
# MEASURED: the desktop is fully drawn — menu bar, both drive icons, the trash and the pointer — by
# three seconds after it reads the disk's DESKTOP.INF, and a run settled for fifteen photographs
# exactly the same screen. What is NOT on it at either settle is a directory window; see below.
FLOPPY_SETTLE_SECONDS = 3.0


def hatari_arguments(medium, trace_file, extra=()):
    """The machine both sides run on. Everything here is either measured or load-bearing.

    `--frameskips 0` is mandatory for a picture comparison: Hatari emulates every frame but renders
    only some, and `screenshot` grabs the last RENDERED surface. `--drive-led off` keeps the drive
    activity light out of the photographed area — and with it the PNG stays a PALETTE image, whose
    PLTE chunk is literally the shifter's sixteen colour registers, so the rendered picture reads
    pens no pixel uses (docs/on-target-execution.md class 8).
    """
    trace = ["--trace", "gemdos", "--trace-file", str(trace_file)] if trace_file else []
    return ["hatari", "--log-level", "info", "--sound", "off",
            "--tos", str(TOS_ROM), "--machine", "st", "--memsize", str(MEMSIZE_MB),
            "--monitor", "rgb", "--tos-res", "low", "--run-vbls", str(RUN_VBLS),
            "--confirm-quit", "off", "--statusbar", "off", "--drive-led", "off",
            "--frameskips", "0"] + trace + list(medium) + list(extra)


def ours_medium():
    """The media OUR .PRG boots from: the game's data floppy in A:, and the C: drive it runs from."""
    return ["--disk-a", str(DISK / "GHOST.ST"),
            "--harddrive", str(DISK / "c"), "--auto", "C:\\BUBBLE.PRG"]


def original_medium():
    """...and the shipped binary's: the protected `.stx` in A:, `bin/` as C:. Both spellings live
    here alone, because a comparison between two differently configured machines is a comparison of
    the configurations (this file's header) — and three copies of a media list is how they drift."""
    return ["--disk-a", str(ORIGINAL_STX), "--protect-floppy", "on",
            "--harddrive", str(BIN), "--auto", ORIGINAL_PRG]


def await_the_decrypted_original(session, result):
    """Poll RAM for the shipped program's plaintext and answer the load base it was found at.

    ITS ADDRESSES DO NOT EXIST YET when the run starts: the shipped program is encrypted against the
    protection track and decrypts itself into RAM, so there is nothing to break on until it is
    there. This polls exactly as ../../tools/boot_ghost.py does, and the base it finds turns every
    Ghidra address into a real one. Answers None — having filled in `result` and shut the session
    down — when the plaintext never appeared, which is a RESULT a caller reports rather than a
    traceback.
    """
    deadline = time.monotonic() + ORIGINAL_LOAD_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        base = locate_by_signature(session.savebin("ram.bin", 0, MEMSIZE_MB * 0x100000),
                                   ORIGINAL_PLAIN)
        if base:
            result["load_base"] = base
            return base
        session.wait(ORIGINAL_LOAD_POLL_SECONDS)
    result["load_base"] = None
    result["status"] = session.close()
    result["problem"] = "the original never decrypted itself into RAM"
    return None


def capture_files(work, side):
    """Where one side's anchor capture lands. BOTH SIDES ARE PHOTOGRAPHED THE SAME WAY, so the names
    are per side rather than per purpose: two runs sharing one filename would each read the other's."""
    return {"shot": work / f"{side}_shot.png",
            "pens": work / f"{side}_pens.bin",
            "rez": work / f"{side}_rez.bin",
            "vbase": work / f"{side}_vbase.bin",
            "done": work / f"{side}_done.bin"}


def arm_the_anchor(session, anchor_pc, side):
    """Break at `anchor_pc`, settle, then photograph and dump the chip.

    STOP-THEN-SHOOT: the display surface is built scanline by scanline, so a capture taken where the
    anchor fires mixes that frame with the one before. The last action is a one-byte `savebin` to a
    marker file, so the driver WAITS ON THE CAPTURE rather than guessing a delay.
    """
    work = session.work
    files = capture_files(work, side)
    shoot = action_file(
        work, f"{side}_shoot.txt",
        f"screenshot {files['shot']}",
        f"savebin {files['pens']} ${HW_PALETTE_BASE:x} ${PALETTE_PENS * PEN_BYTES:x}",
        f"savebin {files['rez']} ${HW_SHIFTER_MODE:x} $1",
        f"savebin {files['vbase']} ${HW_SCREEN_BASE_HIGH:x} $3",
        f"savebin {files['done']} ${HW_SHIFTER_MODE:x} $1")
    session.arm(f"b pc = ${anchor_pc:x} :once :quiet "
                f"{settle_chain(work, ANCHOR_SETTLE_VBLS, shoot, f'{side}_wait%d.txt')}")
    return files


VOICE_SETTLE_VBLS = 2            # XBIOS Setpalette is DEFERRED: TOS loads the sixteen registers
                                 # from its own vertical-blank handler, so a dump taken AT the
                                 # breakpoint can read the palette of the frame before


def arm_the_voice_anchor(session, voice_pc, side):
    """Break where the speech starts and read the chip's sixteen colour registers there.

    THE MOMENT IS THE POINT. `show_presentation` loads GHOST.PRE's palette and then hands control to
    GHOST.LOA, a second program that plays the digitised voice for about a second and a half. While
    the XBIOS group had no door, the shim could only reissue that palette at the composition
    boundary AFTER the slice — so a person watched the presentation in the DESKTOP's colours for the
    whole length of the speech, and no check in this file could see it.

    The settle is two vertical blanks because Setpalette is deferred; the `savebin` of one byte at
    the end is the marker the driver waits on, exactly as the anchor capture's is.
    """
    work = session.work
    files = {"pens": work / f"{side}_voice_pens.bin", "done": work / f"{side}_voice_done.bin"}
    for stale in files.values():
        stale.unlink(missing_ok=True)
    dump = action_file(
        work, f"{side}_voice.txt",
        f"savebin {files['pens']} ${HW_PALETTE_BASE:x} ${PALETTE_PENS * PEN_BYTES:x}",
        f"savebin {files['done']} ${HW_SHIFTER_MODE:x} $1")
    session.arm(f"b pc = ${voice_pc:x} :once :quiet "
                f"{settle_chain(work, VOICE_SETTLE_VBLS, dump, f'{side}_voicewait%d.txt')}")
    return files


def collect_voice_capture(result, files):
    result["voice_pens"] = files["pens"].read_bytes() if files["pens"].is_file() else None


def presentation_palette():
    """GHOST.PRE's own sixteen colour words: the 32 bytes that follow the picture in the file.

    Read off the shipped data file rather than named here, because it is the GAME's palette and
    `load_presentation` (../src/frontend.c) reads it from exactly this offset.
    """
    raw = (BIN / "GHOST.PRE").read_bytes()
    tail = raw[PICTURE_BYTES:PICTURE_BYTES + PALETTE_BYTES]
    if len(tail) != PALETTE_BYTES:
        raise SystemExit(f"ERROR: {BIN / 'GHOST.PRE'} is {len(raw)} bytes and the palette is read "
                         f"from {PICTURE_BYTES:#x} — there is nothing there to compare against")
    return struct.unpack(f">{PALETTE_PENS}H", tail)


def collect_capture(result, files):
    """Read back what the anchor's action file dumped, whatever of it landed."""
    result["shot"] = files["shot"]
    for name in ("pens", "rez", "vbase"):
        result[name] = files[name].read_bytes() if files[name].is_file() else None


def await_the_anchor_table(session, result):
    """Wait for BASE.BIN and unpack it, or fill in `result["problem"]` and answer None.

    It is the FIRST thing the run writes, before anything that can crash, so a run that gets this
    far can still be judged when it dies later — and a run that does not get this far has nothing
    below it worth judging.
    """
    base_file = DISK / "c" / FILE_ANCHOR_BASE
    if not await_file(session, base_file, "waiting for the shim to publish its anchor table",
                      AWAIT_DEADLINE_SECONDS, POLL_SECONDS):
        result["status"] = session.close()
        result["problem"] = (f"{FILE_ANCHOR_BASE} never appeared — the shim did not reach the "
                             f"first thing it does, so nothing below has anything to judge")
        return None
    raw = base_file.read_bytes()
    if len(raw) != ANCHOR_SLOTS * 4:
        result["status"] = session.close()
        result["problem"] = (f"{FILE_ANCHOR_BASE} is {len(raw)} bytes and this file expects "
                             f"{ANCHOR_SLOTS} slots ({ANCHOR_SLOTS * 4} bytes): bubble_main.c's "
                             f"`enum bg_anchor_slot` and this file have diverged")
        return None
    anchors = struct.unpack(f">{ANCHOR_SLOTS}I", raw)
    result["anchor_pc"] = anchors[ANCHOR_TITLE_HOLD]
    return anchors


def run_ours(mode, work):
    """Boot the reconstruction, photograph it at its anchor, and collect everything it wrote."""
    work.mkdir(parents=True, exist_ok=True)
    for stale in (FILE_ANCHOR_BASE, FILE_SCREEN_DUMP, FILE_STATE_RECORD):
        (DISK / "c" / stale).unlink(missing_ok=True)
    for stale in capture_files(work, "ours").values():
        stale.unlink(missing_ok=True)

    trace = work / "ours.trace"
    medium = ours_medium()
    session = HeadlessSession(hatari_arguments(medium, trace), work / "ours.log",
                              work / "ours.fifo", work)
    result = {"trace": trace, "log": work / "ours.log", "mode": mode}

    anchors = await_the_anchor_table(session, result)
    if anchors is None:
        return result

    voice = arm_the_voice_anchor(session, anchors[ANCHOR_VOICE_ENTRY], "ours")
    files = arm_the_anchor(session, anchors[ANCHOR_TITLE_HOLD], "ours")
    if not await_file(session, files["done"], "waiting for the anchor capture",
                      AWAIT_DEADLINE_SECONDS, POLL_SECONDS):
        result["problem"] = "the anchor breakpoint never fired"
    result["anchor_seconds"] = time.monotonic() - session.started
    record_file = DISK / "c" / FILE_STATE_RECORD
    await_file(session, record_file, "waiting for the program's record",
               AWAIT_DEADLINE_SECONDS, POLL_SECONDS)
    session.wait(3.0)          # let the emulator run on PAST Pterm: a vector left installed halts
    result["status"] = session.close()                                # the machine about a second on
    collect_capture(result, files)
    collect_voice_capture(result, voice)
    result["record"] = read_record(record_file)
    screen = DISK / "c" / FILE_SCREEN_DUMP
    result["screen"] = screen.read_bytes() if screen.is_file() else None
    return result


def run_original(work):
    """Boot the ORIGINAL the way ../tools/boot_ghost.py does, and photograph it at its own anchor.

    ITS ANCHOR IS A PC THAT DOES NOT EXIST YET. The shipped program is encrypted against the
    protection track and decrypts itself into RAM, so there is no address to break on until it is
    there; this polls RAM for the plaintext exactly as boot_ghost.py does, and the load base it
    finds turns every Ghidra address into a real one. `ORIGINAL_ANCHOR_PC` is then the same place in
    the same program our own anchor stands in, so the settle is a MOMENT on both sides — the first
    draft of this file waited 26 s by the wall clock instead, and the vblank counts it reported were
    a measurement of that wait.
    """
    work.mkdir(parents=True, exist_ok=True)
    for stale in capture_files(work, "orig").values():
        stale.unlink(missing_ok=True)
    trace = work / "orig.trace"
    medium = original_medium()
    session = HeadlessSession(hatari_arguments(medium, trace), work / "orig.log",
                              work / "orig.fifo", work)
    result = {"trace": trace, "log": work / "orig.log"}

    base = await_the_decrypted_original(session, result)
    if base is None:
        return result

    voice = arm_the_voice_anchor(session, base - LOAD_BASE + ORIGINAL_VOICE_PC, "orig")
    files = arm_the_anchor(session, base - LOAD_BASE + ORIGINAL_ANCHOR_PC, "orig")
    reached = await_file(session, files["done"], "waiting for the original to draw its menu",
                         AWAIT_DEADLINE_SECONDS, POLL_SECONDS)
    result["anchor_seconds"] = time.monotonic() - session.started
    collect_voice_capture(result, voice)
    if not reached:
        result["problem"] = (f"the original never reached its menu anchor "
                            f"({ORIGINAL_ANCHOR_PC:#x} at load base {base:#x})")
        result["status"] = session.close()
        collect_capture(result, files)
        return result

    # The program is blocked on `Cnecin` from here on and is drawing nothing, so reading its screen
    # pointer and then its screen races with nothing.
    phys = struct.unpack(">I", session.savebin("phys.bin", base - LOAD_BASE + A_screen_phys, 4))[0]
    result["screen_phys"] = phys
    result["screen"] = session.savebin("origscreen.bin", phys, SCREEN_BYTES)
    result["status"] = session.close()
    collect_capture(result, files)
    return result


def read_record(path):
    if not path.is_file():
        return None
    raw = path.read_bytes()
    if len(raw) != len(RECORD_FIELDS) * 4:
        return {"_length": len(raw)}
    return dict(zip(RECORD_FIELDS, struct.unpack(f">{len(RECORD_FIELDS)}I", raw)))


# ================================================================================================
# The checks. Each returns a LIST OF COMPLAINTS; empty means it passed, and a check that ran is
# printed even when green.
# ================================================================================================

def faults(log_path):
    """Fault lines Hatari logged, minus TOS's own boot-time probes past the end of RAM."""
    if not log_path.is_file():
        return [f"no log at {log_path}"]
    return [line for line in log_faults(log_path, FAULT_MARKERS) if not TOS_ROM_PC.search(line)]


def check_machine_health(status, log_path):
    """What one run's EXIT STATUS and its own log say went wrong, as a list of plain strings.

    ONE DEFINITION, because three callers grade the same two things: the `title` gate below, the
    `game` gate, and `atari/profile.py`'s measurement window — which is not a gate at all and must
    still refuse a machine that faulted, because a profile of a crashed boot is not a slower frame,
    it is a different program, and it prints as a perfectly plausible table.
    """
    return ([f"Hatari exited {status}"] if status != 0 else []) + faults(log_path)


def check_exit_status_and_log(ours, original):
    problems = []
    for side, run in (("ours", ours), ("the original", original)):
        if run.get("problem"):
            problems.append(f"{side}: {run['problem']}")
        problems += [f"{side}: {problem}"
                     for problem in check_machine_health(run.get("status", 0), run["log"])]
    return problems


def check_the_fault_scan_can_fail(ours, original):
    """The meta-control: prove on every run that the scan above can still go red.

    A scan with nothing to reject demonstrates nothing, and this one drops lines by a ROM PC — so it
    is run over one real fault line and one ROM probe, and must name exactly the real one.
    """
    del ours, original
    probe = OUT / "faultscan.log"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text("WARN : Bus Error writing at $41fffe, PC=$fc0174\n"
                     "WARN : Bus Error reading at $998a00fc, PC=$12908\n")
    named = faults(probe)
    if len(named) != 1 or "$12908" not in named[0]:
        return [f"the fault scan named {named} on one real fault and one ROM probe — it has rotted, "
                f"and a clean report from it would mean nothing"]
    return []


# The fields `exact_record_fields` below cannot express as one expected value, each asserted by name
# in `check_the_record`'s body; and the three the CONTROLS grade rather than the gate. Together with
# that map these must cover the WHOLE record — `check_the_record` says so on every run, because the
# claim this file and atari/README.md make is "every field the boot owes", and a field added to
# `bubble_main.c` with no assertion here would make that claim quietly false.
FIELDS_ASSERTED_BY_HAND = frozenset("""IMAGE_BASE VOI_BUFFER_OFFSET TIMER_C_CHAIN TIMER_C_SAVED
TIMER_C_TICKS TIMER_C_VECTOR TRAP9_VECTOR TPA_LOW TPA_HIGH KEPT_TOP IMAGE_HEADROOM""".split())
FIELDS_THE_CONTROLS_GRADE = frozenset({"FAULT_PEN", "FAULT_IMAGE_WORD", "FAULT_NO_TIMER_C"})


def exact_record_fields(record):
    """Every field whose value the boot owes EXACTLY, as {field: expected}.

    Some are constants of the build and some are derived from other fields of the same record —
    which is the point: a record that agrees with itself is a record whose parts were all written by
    the same run.
    """
    image = record["IMAGE_BASE"]
    return {
        "MAGIC": RECORD_MAGIC,
        "TAIL": RECORD_TAIL,
        "PHASE_REACHED": PHASE_HANDED_BACK,
        "A4_BASE": A4_BASE,
        "LOW_RESOLUTION": 1,
        "ENTRY_RESOLUTION": ST_LOW_RESOLUTION,
        "MSHRINK_RESULT": 0,
        "IMAGE_BYTES": IMAGE_BYTES,
        "PROGRAM_BYTES": (DISK / "c" / "GHOST.IMG").stat().st_size,
        "SCREEN_PHYS": SCREEN_BASE,
        "SCREEN_BACK": SCREEN_BASE - SCREEN_BYTES,
        "PUBLISHED_PHYSBASE": image + record["SCREEN_PHYS"],
        "READBACK_PHYSBASE": record["PUBLISHED_PHYSBASE"],
        "READBACK_LOGBASE": image + record["SCREEN_PHYS"],
        "FILE_OPENS": EXPECTED_FILE_OPENS,
        "FILE_OPEN_FAILURES": EXPECTED_OPEN_FAILURES,
        "FILE_REFUSALS": 0,
        "FILE_WRITE_FAILURES": 0,
        "SHIM_FILE_OPENS": EXPECTED_SHIM_OPENS,
        "SHIM_FILE_FAILURES": 0,
        "MALLOC_CALLS": EXPECTED_MALLOC_CALLS,
        "HEAP_POINTER": HEAP_BASE + EXPECTED_HEAP_BYTES,
        "VDI_CALLS": EXPECTED_VDI_CALLS,
        "AES_CALLS": EXPECTED_AES_CALLS,
        "VDI_RASTER_COPIES": EXPECTED_RASTER_COPIES,
        "HW_WRITES": EXPECTED_HW_WRITES,
        "CONTERM_AT_ANCHOR": 0,
        "GUARD_DIRTY": 0,
        "VOI_POINTER_MACHINE": image + record["VOI_BUFFER_OFFSET"],
    }


def check_the_record(ours, original):
    """The program's own account of its boot: complete, and every field the value the boot owes."""
    del original
    record = ours.get("record")
    if record is None:
        return [f"{FILE_STATE_RECORD} was never written — the run did not reach its own hand-back"]
    if "_length" in record:
        return [f"{FILE_STATE_RECORD} is {record['_length']} bytes and the record has "
                f"{len(RECORD_FIELDS)} fields ({len(RECORD_FIELDS) * 4} bytes): bubble_main.c's "
                f"`enum bg_record_field` and this file's RECORD_FIELDS have diverged"]
    exact = exact_record_fields(record)
    problems = [f"{field} is {record[field]:#x}, not {want:#x}"
                for field, want in exact.items() if record[field] != want]
    unasserted = (set(RECORD_FIELDS) - set(exact) - FIELDS_ASSERTED_BY_HAND
                  - FIELDS_THE_CONTROLS_GRADE)
    if unasserted:
        problems.append(f"the record carries {sorted(unasserted)}, which nothing here asserts — "
                        f"this file and atari/README.md claim EVERY field, so either give them a "
                        f"value to be judged against or say in both places why they have none")

    if record["IMAGE_BASE"] % IMAGE_ALIGN:
        problems.append(f"the image sits at {record['IMAGE_BASE']:#x}, which is not "
                        f"{IMAGE_ALIGN}-aligned — the shifter would truncate the base it is handed")
    if not HEAP_BASE <= record["VOI_BUFFER_OFFSET"] < HEAP_LIMIT:
        problems.append(f"the speech buffer is at image offset {record['VOI_BUFFER_OFFSET']:#x}, "
                        f"outside the Malloc arena [{HEAP_BASE:#x}, {HEAP_LIMIT:#x})")
    if record["TIMER_C_CHAIN"] != record["TIMER_C_SAVED"]:
        problems.append(f"the Timer C chain the stub uses ({record['TIMER_C_CHAIN']:#x}) is not "
                        f"what the verified installer saved ({record['TIMER_C_SAVED']:#x})")
    if record["TIMER_C_TICKS"] == 0:
        problems.append("the 200 Hz Timer C handler never fired — the sound engine is not running")
    # THE TWO VECTORS POINT AT US. Neither address is knowable here — they are link-time addresses
    # of shim routines — so what is asserted is that each one moved off TOS's ROM and INTO the
    # program's own TPA, which is the whole of what "the shim took the vector" means.
    for field in ("TIMER_C_VECTOR", "TRAP9_VECTOR"):
        if not record["TPA_LOW"] <= record[field] < record["TPA_HIGH"]:
            problems.append(f"{field} is {record[field]:#x}, which is outside this program's TPA "
                            f"[{record['TPA_LOW']:#x}, {record['TPA_HIGH']:#x}) — the shim's own "
                            f"handler is not on the vector")
    if not record["TPA_LOW"] < record["KEPT_TOP"] <= record["TPA_HIGH"]:
        problems.append(f"the Mshrink kept up to {record['KEPT_TOP']:#x}, which is not inside the "
                        f"TPA [{record['TPA_LOW']:#x}, {record['TPA_HIGH']:#x})")
    if record["IMAGE_HEADROOM"] < STACK_RESERVE_BYTES // 2:
        problems.append(f"only {record['IMAGE_HEADROOM']} B between the image and the stack")
    if MEMSIZE_MB == TPA_MEASURED_AT_MB:
        tpa = record["TPA_HIGH"] - record["TPA_LOW"]
        if tpa != TPA_1MB_BYTES:
            problems.append(f"the program measured a {tpa} B TPA and build.sh's size gate weighs "
                            f"against {TPA_1MB_BYTES} B — one of the two is stale")
    return problems


def check_the_framebuffer(ours, original):
    """MEMORY: the displayed 32,000 bytes, ours against the original's own.

    This is the surface that mirrors the differential, and the only one here that compares the two
    programs' MEANING rather than their configuration.
    """
    if ours.get("screen") is None:
        return [f"{FILE_SCREEN_DUMP} was never written"]
    if original.get("screen") is None:
        return ["the original's framebuffer was never dumped"]
    if len(ours["screen"]) != len(original["screen"]):
        return [f"{len(ours['screen'])} bytes against the original's {len(original['screen'])}"]
    differing = sum(1 for a, b in zip(ours["screen"], original["screen"]) if a != b)
    if differing:
        first = next(i for i, (a, b) in enumerate(zip(ours["screen"], original["screen"])) if a != b)
        return [f"{differing} of {len(ours['screen'])} framebuffer bytes differ, first at {first}"]
    if not any(ours["screen"]):
        return ["both framebuffers are entirely zero, so their equality means nothing — the menu "
                "drew nothing on either side"]
    return []


def check_the_hardware_state(ours, original):
    """The chip itself, read by the DEBUGGER at both anchors: the pens, the resolution, the base."""
    problems = []
    if ours.get("pens") is None or ours.get("rez") is None or ours.get("vbase") is None:
        return ["the anchor's register dumps are missing — the capture never happened"]
    pens = struct.unpack(">16H", ours["pens"])
    record = ours.get("record") or {}
    if all(pen & SHIFTER_PEN_MASK == 0 for pen in pens):
        problems.append("every colour register is black, so nothing the picture shows is a colour "
                        "the game chose")
    # MASKED, because an STF implements three bits a gun and returns the fourth as bus noise: a
    # comparison of raw reads would differ on hardware for a reason that is not about the game
    # (docs/on-target-execution.md class 8). The REPORT prints them unmasked, which is the only
    # place an STE's fourth bit could show.
    if original.get("pens"):
        theirs = struct.unpack(">16H", original["pens"])
        wrong = [(pen, mine & SHIFTER_PEN_MASK, their & SHIFTER_PEN_MASK)
                 for pen, (mine, their) in enumerate(zip(pens, theirs))
                 if (mine ^ their) & SHIFTER_PEN_MASK]
        for pen, mine, their in wrong:
            problems.append(f"pen {pen} is {mine:03x} on the chip and the original's is {their:03x}")
    rez = ours["rez"][0] & SHIFTER_REZ_MASK
    if rez != ST_LOW_RESOLUTION:
        problems.append(f"$ff8260 reads {rez}, not {ST_LOW_RESOLUTION} (ST low resolution)")
    if original.get("rez") is not None:
        theirs = original["rez"][0] & SHIFTER_REZ_MASK
        if theirs != rez:
            problems.append(f"$ff8260 reads {rez} on ours and {theirs} on the original's")
    # $ff8201 holds bits 23-16 and $ff8203 holds 15-8, with an UNDECODED byte between them: the
    # three-byte dump is high, nothing, mid — reading the middle byte as the mid half reports a base
    # that is always a whole 64 KiB, which is what the first draft of this check did.
    high, _undecoded, mid = ours["vbase"]
    base = (high << 16) | (mid << 8)
    if record.get("PUBLISHED_PHYSBASE") not in (None, base):
        problems.append(f"the shifter is displaying from {base:#x} and the shim published "
                        f"{record['PUBLISHED_PHYSBASE']:#x}")
    return problems


GEMDOS_LINE = re.compile(r"^GEMDOS 0x[0-9A-Fa-f]+ (\w+)\((.*)\) at PC")
GEMDOS_QUOTED = re.compile(r'"([^"]*)"')
# The shim's own four files are not the game's, and neither is TOS's DESKTOP.INF: the ledger
# compares the GAME's traps, so those names are dropped from our side before the comparison.
SHIM_FILES = ("GHOST.IMG", "BASE.BIN", "SCREEN.BIN", "STATE.BIN", DESKTOP_INF)


GEMDOS_HANDLE_LINE = re.compile(r"^-> FD (\d+)")


def gemdos_file_calls(trace_path, drop_names=()):
    """(name, subject) per GEMDOS file call the GAME made, in order.

    THE BUFFER ADDRESS IS DELIBERATELY DROPPED: ours is inside the image array and the original's is
    absolute RAM, so comparing them would compare the two builds' memory maps — which is exactly the
    thing that is allowed to differ.

    SO IS THE HANDLE, for the same kind of reason: our GHOST.LOA opens on the GEMDOS drive and gets
    Hatari's FD 64 while the original's opens on the floppy and gets a number TOS chose. What is
    compared is the ORDER, the call, the name and the byte count.

    A DROPPED OPEN DROPS ITS WHOLE FILE. The shim's four files are not the game's, so they leave the
    ledger — and so must the Fread/Fwrite/Fclose that follow them, which is what the handle tracking
    below is for. Hatari prints the handle it assigned on the next line (`-> FD 64`) for a file on
    the GEMDOS drive; a floppy file is handed `-> to TOS` and has no visible handle, which is
    harmless because every file this drops is on the GEMDOS drive by construction.
    """
    if not trace_path.is_file():
        return None
    calls, dropped_handles, awaiting_handle = [], set(), False
    for line in trace_path.read_text(errors="replace").splitlines():
        handle_match = GEMDOS_HANDLE_LINE.match(line.strip())
        if handle_match and awaiting_handle:
            dropped_handles.add(handle_match.group(1))
            awaiting_handle = False
            continue
        match = GEMDOS_LINE.match(line)
        if not match:
            continue
        awaiting_handle = False
        name, arguments = match.group(1), match.group(2)
        fields = [field.strip() for field in arguments.split(",")]
        if name in ("Fopen", "Fcreate"):
            quoted = GEMDOS_QUOTED.search(arguments)
            filename = quoted.group(1) if quoted else arguments
            if any(drop.lower() in filename.lower() for drop in drop_names):
                awaiting_handle = True
                continue
            calls.append((name, filename.upper()))
        elif name in ("Fread", "Fwrite", "Fclose"):
            if fields[0] in dropped_handles:
                if name == "Fclose":
                    dropped_handles.discard(fields[0])
                continue
            calls.append((name, fields[1] if name != "Fclose" and len(fields) > 1 else ""))
    return calls


def check_the_voice_palette(ours, original):
    """HARDWARE-STATE VECTOR, at the moment the speech starts rather than at the menu.

    The defect this exists for was reported by a person, not by a check: the presentation picture
    was in the DESKTOP's colours for the whole length of "Welcome to Bubble Ghost". The cause was
    that the XBIOS group had no door, so `show_presentation`'s Setpalette was swallowed inside a
    verified core and `bubble_main.c` could only reissue it at the composition boundary AFTER the
    slice that runs the voice. Nothing in this file could see it: the menu anchor is seconds later,
    by which time the reissue has happened.

    Three claims, and the third is what makes the first two mean something: the pens on the chip are
    GHOST.PRE's own sixteen colour words, they are the same on both sides, and the ORIGINAL's are
    that palette too — so a green here is a comparison against the shipped game and not against a
    number this file believes.
    """
    problems = []
    expected = presentation_palette()
    for side, run in (("ours", ours), ("the original", original)):
        raw = run.get("voice_pens")
        if raw is None:
            problems.append(f"{side}: the chip was never read at the voice anchor — the breakpoint "
                            f"did not fire, so this check has nothing to judge")
            continue
        pens = struct.unpack(f">{PALETTE_PENS}H", raw)
        wrong = [(pen, mine & SHIFTER_PEN_MASK, want & SHIFTER_PEN_MASK)
                 for pen, (mine, want) in enumerate(zip(pens, expected))
                 if (mine ^ want) & SHIFTER_PEN_MASK]
        for pen, mine, want in wrong:
            problems.append(f"{side}: pen {pen} is {mine:03x} when the speech starts and "
                            f"GHOST.PRE's is {want:03x}")
    return problems


def check_the_trap_ledger(ours, original):
    """The GEMDOS calls the game makes, ours against the original's, in order AND in number.

    THE LENGTHS ARE COMPARED AND NOT ONLY THE COMMON PREFIX: a run that stopped early, or one that
    made a call the original never makes after the last one they share, agrees on every index that
    exists in both — so a prefix comparison reports green on a ledger that is missing its tail.
    """
    mine = gemdos_file_calls(ours["trace"], SHIM_FILES)
    theirs = gemdos_file_calls(original["trace"], (DESKTOP_INF,))
    if mine is None or theirs is None:
        return ["a GEMDOS trace is missing"]
    if not mine or not theirs:
        return [f"the trace parser found {len(mine)} of our calls and {len(theirs)} of the "
                f"original's — one is EMPTY, so the comparison below would be silent"]
    for index in range(min(len(mine), len(theirs))):
        if mine[index] != theirs[index]:
            return [f"GEMDOS call {index} is {mine[index]} and the original's is {theirs[index]}"]
    if len(mine) != len(theirs):
        longer, side = (mine, "ours") if len(mine) > len(theirs) else (theirs, "the original's")
        return [f"we made {len(mine)} GEMDOS calls and the original {len(theirs)}: the first one "
                f"the shorter ledger does not have is {side} call {min(len(mine), len(theirs))}, "
                f"{longer[min(len(mine), len(theirs))]}"]
    return []


def check_neither_capture_is_blank(ours, original):
    """RENDERED PIXELS, the half that must be green in EVERY mode including the controls.

    It is a check of its own and not the first lines of the comparison below, and that is what the
    first negative control cost: it XORed the menu's only ink colour to black, `distinct_colours`
    rejected the capture, and the picture COMPARISON — the thing the control existed to exercise —
    never ran at all while the control reported a satisfying red.
    """
    problems = []
    for side, run in (("ours", ours), ("the original", original)):
        shot = run.get("shot")
        if shot is None or not shot.is_file():
            problems.append(f"{side}: no screenshot was taken")
        elif distinct_colours(shot) <= BLANK_COLOUR_COUNT:
            problems.append(f"{side}: the capture has one colour — it is a photograph of nothing")
    return problems


def check_the_rendered_pixels(ours, original):
    """The picture Hatari's own video path drew, on both sides, byte for byte."""
    if check_neither_capture_is_blank(ours, original):
        return ["there is no pair of captures to compare — see the check above"]
    if not same_picture(ours["shot"], original["shot"]):
        return ["the two captures differ"]
    return []


def screen_pens_used(screen):
    """Which hardware pens the displayed picture actually draws, as a set.

    ST low resolution interleaves four bit-planes word by word, so a pixel's pen is one bit from
    each of four consecutive words.
    """
    used = set()
    for word in range(0, len(screen) - 7, 8):
        planes = struct.unpack(">4H", screen[word:word + 8])
        for bit in range(16):
            used.add(sum(((planes[plane] >> (15 - bit)) & 1) << plane for plane in range(4)))
    return used


def check_the_pen_fault_is_the_one_claimed(ours, original):
    """CONTROL MODE ONLY: the injected fault is the pen the build says, and the picture uses it.

    Without the second half the control is vacuous in the way that is hardest to see — a fault on a
    register no pixel reads moves the chip's state and leaves the rendered picture byte-identical,
    so `rendered pixels` reports green under a fault that was really there. Measured on this build:
    the menu draws in hardware pens 0 and 15 only, and the first draft faulted pen 1.
    """
    del original
    record = ours.get("record") or {}
    pen = record.get("FAULT_PEN")
    if pen is None:
        return ["the record carries no fault pen"]
    if pen == NO_PEN_FAULT:
        return ["the .PRG under test reports no injected pen fault — it is a shipped build, and "
                "this control has nothing to prove"]
    if ours.get("screen") is None:
        return ["no framebuffer to check the fault's coverage against"]
    if pen not in screen_pens_used(ours["screen"]):
        return [f"pen {pen} is faulted and NO PIXEL on the screen uses it, so the rendered picture "
                f"cannot move and this control proves nothing. The picture draws in pens "
                f"{sorted(screen_pens_used(ours['screen']))}"]
    return []


def check_the_image_fault_is_the_one_claimed(ours, original):
    """CONTROL MODE ONLY: one word of the staged program was XORed, and it is the one named."""
    del original
    record = ours.get("record") or {}
    word = record.get("FAULT_IMAGE_WORD")
    if not word:
        return ["the .PRG under test reports no injected image fault — it is a shipped build, and "
                "this control has nothing to prove"]
    if word != A_text_menu_game:
        return [f"the build faulted image word {word:#x} and ../include/frontend.h puts the first "
                f"menu line at {A_text_menu_game:#x} — the control is no longer aimed at text the "
                f"menu draws, and a picture that did not move would prove nothing"]
    return []


def check_the_isr_fault_is_the_one_claimed(ours, original):
    """CONTROL MODE ONLY: the Timer C vector really was left uninstalled."""
    del original
    record = ours.get("record") or {}
    if not record.get("FAULT_NO_TIMER_C"):
        return ["the .PRG under test reports no injected Timer C fault — it is a shipped build, "
                "and this control has nothing to prove"]
    if record["TIMER_C_VECTOR"] != record["TIMER_C_CHAIN"]:
        return [f"$114 holds {record['TIMER_C_VECTOR']:#x} at the anchor and TOS's own handler is "
                f"{record['TIMER_C_CHAIN']:#x} — something installed a vector this control says it "
                f"did not, so what the record reds on is not this fault"]
    return []


# ================================================================================================
# The modes: which checks run, and which of them a control expects to be RED
# ================================================================================================
CHECK_EXIT = "exit status + log"
CHECK_SCAN = "exit status + log (the fault scan can fail)"
CHECK_RECORD = "memory (the program's own record)"
CHECK_FRAMEBUFFER = "memory (the displayed framebuffer, against the original's)"
CHECK_LEDGER = "trap ledger"
CHECK_HARDWARE = "hardware-state vector (the pens, $ff8260, the video base)"
CHECK_VOICE_PALETTE = "hardware-state vector (the pens when the speech starts)"
CHECK_NOT_BLANK = "rendered pixels (neither capture is a photograph of nothing)"
CHECK_PIXELS = "rendered pixels (the two captures, byte for byte)"

CHECKS = {
    CHECK_EXIT: check_exit_status_and_log,
    CHECK_SCAN: check_the_fault_scan_can_fail,
    CHECK_RECORD: check_the_record,
    CHECK_FRAMEBUFFER: check_the_framebuffer,
    CHECK_LEDGER: check_the_trap_ledger,
    CHECK_HARDWARE: check_the_hardware_state,
    CHECK_VOICE_PALETTE: check_the_voice_palette,
    CHECK_NOT_BLANK: check_neither_capture_is_blank,
    CHECK_PIXELS: check_the_rendered_pixels,
}

# mode -> (the checks that MUST go red, the extra check that proves the fault is really there)
CONTROLS = {
    "titlefault": ({CHECK_HARDWARE, CHECK_PIXELS}, check_the_pen_fault_is_the_one_claimed),
    "titlepoke": ({CHECK_FRAMEBUFFER, CHECK_PIXELS}, check_the_image_fault_is_the_one_claimed),
    "titleisr": ({CHECK_RECORD}, check_the_isr_fault_is_the_one_claimed),
}
CLAIM_CHECK = "the fault is the one claimed"


def report(ours, original, mode):
    must_be_red, claim = CONTROLS.get(mode, (set(), None))
    checks = dict(CHECKS)
    if claim:
        checks[CLAIM_CHECK] = claim
    record = ours.get("record") or {}

    print(f"-- {mode} on st / {TOS_ROM.name} at {MEMSIZE_MB} MB: "
          f"image base {record.get('IMAGE_BASE', 0):#x}, the original at "
          f"{original.get('load_base') or 0:#x}")
    if record:
        print(f"   memory: TPA [{record.get('TPA_LOW', 0):#x}, {record.get('TPA_HIGH', 0):#x}), "
              f"kept to {record.get('KEPT_TOP', 0):#x}, image "
              f"{record.get('IMAGE_BYTES', 0) // 1024} KiB at {record.get('IMAGE_BASE', 0):#x}, "
              f"{record.get('IMAGE_HEADROOM', 0)} B headroom, "
              f"{record.get('GUARD_DIRTY', 0)} guard byte(s) dirty")
        print(f"   the boot: {record.get('FILE_OPENS')} file opens "
              f"({record.get('FILE_OPEN_FAILURES')} refused by the disk) + "
              f"{record.get('SHIM_FILE_OPENS')} the shim's, "
              f"{record.get('MALLOC_CALLS')} Mallocs to {record.get('HEAP_POINTER', 0):#x}, "
              f"{record.get('VDI_CALLS')} VDI and {record.get('AES_CALLS')} AES traps, "
              f"{record.get('TIMER_C_TICKS')} Timer C ticks")
        print(f"   the speech: GHOST.VOI at image offset "
              f"{record.get('VOI_BUFFER_OFFSET', 0):#x}, poked into the LOA as "
              f"{record.get('VOI_POINTER_MACHINE', 0):#x}")
    if ours.get("pens"):
        print("   pens read off the chip, unmasked: "
              + " ".join(f"{pen:04x}" for pen in struct.unpack(">16H", ours["pens"])))
    # THE TIMELINE IS REPORTED AND NOT ASSERTED. Both anchors are moments now, but the two runs do
    # not START together — the original spends about eight emulated seconds decrypting itself before
    # its first instruction of plaintext exists, and this driver's own RAM polling for it is in the
    # same span — so the two numbers are not comparable quantities. Emulation is real time, so host
    # seconds from power-on ARE emulated seconds from power-on.
    print(f"   timelines: power-on to the anchor, ours {ours.get('anchor_seconds', 0):.0f} s and "
          f"the original's {original.get('anchor_seconds', 0):.0f} s — REPORTED, not asserted: the "
          f"original's decrypt and this driver's poll for it are in front of its number only")

    failures = []
    for name, check in sorted(checks.items()):
        problems = check(ours, original)
        inverted = name in must_be_red
        group = "must FAIL" if inverted else "must PASS"
        print(f"   [{'red ' if problems else 'green'}] {name}   ({group})")
        for problem in problems:
            print(f"           {problem}")
        if inverted and not problems:
            failures.append(name)
            print(f"           CONTROL FAILED: {name} stayed green under the injected fault")
        elif problems and not inverted:
            failures.append(name)
    print("-- OK" if not failures else f"-- FAILED: {len(failures)} check(s)")
    return 0 if not failures else 1


# ================================================================================================
# The bootable floppy — a run of its own, because it shares no anchor with anything
# ================================================================================================
def run_the_floppy():
    r"""Boot atari/disk/BUBBLE.ST in A: with no --auto and photograph the desktop it comes up on.

    WHAT THIS CAN AND CANNOT SETTLE. The disk deliberately does NOT autostart — both ways of making
    it were tried and measured as failures, and `mkfloppy.py` records them — so the game itself is
    started by a double-click and Hatari's control protocol has no mouse motion of any kind. What is
    therefore checkable is the BOOT: TOS mounts the volume without executing its boot sector, the
    desktop reads the `DESKTOP.INF` on it, the machine faults nowhere, the emulator exits 0, and the
    capture is a picture and not a blank screen. That is the claim atari/README.md makes about this
    disk, and until this ran it was a claim with no surface under it.

    IT ALSO CORRECTED THAT CLAIM ON ITS FIRST RUN. Both this file and `mkfloppy.py` said the disk
    came up with a directory window open on `A:\*.*`, from the `#W` line in the original's own
    DESKTOP.INF. The capture shows the desktop, its two drive icons and the trash — and NO window,
    at three seconds and at fifteen. TOS 1.04's desktop reads the file (its `Fopen` is in the trace)
    and does not act on that line, exactly as it does not act on a `#Z` autostart line.
    """
    if not FLOPPY_IMAGE.is_file():
        raise SystemExit(f"ERROR: no {FLOPPY_IMAGE} — run `bash atari/build.sh title floppy` first")
    work = OUT / "floppy"
    work.mkdir(parents=True, exist_ok=True)
    shot = work / "floppy_shot.png"
    shot.unlink(missing_ok=True)
    trace = work / "floppy.trace"
    session = HeadlessSession(hatari_arguments(["--disk-a", str(FLOPPY_IMAGE)], trace),
                              work / "floppy.log", work / "floppy.fifo", work)

    reached_desktop = False
    deadline = time.monotonic() + FLOPPY_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        if trace.is_file() and DESKTOP_INF in trace.read_text(errors="replace"):
            reached_desktop = True
            break
        session.require_alive("waiting for the desktop to read the disk's DESKTOP.INF")
        session.wait(POLL_SECONDS)
    session.wait(FLOPPY_SETTLE_SECONDS)      # let the desktop finish drawing its window
    session.screenshot(shot)
    status = session.close()

    problems = []
    if not reached_desktop:
        problems.append(f"the desktop never opened {DESKTOP_INF} from the volume, so nothing says "
                        f"TOS mounted it as a filesystem")
    if status != 0:
        problems.append(f"Hatari exited {status}")
    problems += faults(work / "floppy.log")
    if not shot.is_file():
        problems.append("no screenshot was taken")
    elif distinct_colours(shot) <= BLANK_COLOUR_COUNT:
        problems.append("the capture has one colour — it is a photograph of nothing, so 'it boots "
                        "to the desktop' has no evidence behind it")

    print(f"-- floppy on st / {TOS_ROM.name} at {MEMSIZE_MB} MB: {FLOPPY_IMAGE.name}, "
          f"{FLOPPY_IMAGE.stat().st_size} B, booted with no --auto")
    print(f"   [{'red ' if problems else 'green'}] the volume boots TOS to a desktop   (must PASS)")
    for problem in problems:
        print(f"           {problem}")
    print("   the game itself is started by a double-click and no headless run can make one — "
          "atari/README.md's 'Unpinned' carries that")
    print("-- OK" if not problems else f"-- FAILED: {len(problems)} problem(s)")
    return 0 if not problems else 1


# ================================================================================================
# The `game` mode — the G key, and the room behind it
#
# It is a run of its own for the floppy's reason: it shares no anchor with the title gate. It judges
# the `play` .PRG, which has no hold and no photograph of its own — it composes the whole program
# and runs until the window is closed — so what it does instead is DRIVE it: wait for the menu, send
# the two keys a person sends, and watch the room loop turn.
#
# WHY IT EXISTS. A person reported that pressing G on the menu returned them to the desktop. Nothing
# headless had ever pressed a key on this build: `smoke.py title` stops at the menu deliberately,
# one instruction before the blocking read. This mode is that missing surface, and it is the whole
# of what a machine with no mouse can say about the game — Bubble Ghost is PLAYED with the mouse,
# and Hatari's control protocol has no mouse motion of any kind (atari/README.md's "Unpinned").
# ================================================================================================
MENU_DEADLINE_SECONDS = 120.0    # the boot is a real floppy-and-GEMDOS timeline on both sides
ROOM_DEADLINE_SECONDS = 90.0
GAME_KEY_RETRY_SECONDS = 2.5     # how long each resent key is given to land and be acted on
GAME_FRAMES_REQUIRED = 10        # a room loop that TURNS, not one that was entered and stopped


def read_play_tally(session, tally_address):
    """The two longwords `bg_play_tally` holds, read out of the running machine."""
    raw = session.savebin("tally.bin", tally_address, TALLY_SLOTS * 4)
    return struct.unpack(f">{TALLY_SLOTS}I", raw)


def await_play_tally(session, tally_address, slot, want, doing, deadline_seconds):
    """Poll one tally until it reaches `want`. Answers the value it last read.

    POLLING THE PROGRAM'S OWN COUNTER rather than waiting a fixed time is what tells a boot that is
    still loading from a floppy apart from one that has finished: `TALLY_MENU_OPENS` moves when
    `title_menu_open` returns, which is after its own console flush, so a key sent from here has a
    program waiting for it.
    """
    deadline = time.monotonic() + deadline_seconds
    value = 0
    while time.monotonic() < deadline:
        value = read_play_tally(session, tally_address)[slot]
        if value >= want:
            return value
        session.require_alive(doing)
        session.wait(POLL_SECONDS)
    return value


def arm_the_room_anchor(session, room_pc, side, screen_address):
    """Break on a room's FIRST frame, dump the framebuffer THERE, and photograph four blanks later.

    It is a deterministic moment on both sides and the strongest one this mode has: the room has
    been composed and drawn, `game_room_frame_tail` has not run once, and the mouse — which is what
    would otherwise make two runs diverge immediately — has not moved on either side, because
    nothing headless can move it.

    THE FRAMEBUFFER IS DUMPED AT THE BREAKPOINT AND THE PICTURE FOUR BLANKS LATER, and the split is
    the whole reason this check means anything. Memory is exact at the instruction, so it needs no
    settle; the DISPLAY surface is built scanline by scanline and does (docs/on-target-execution.md
    class 8). Four blanks is four more frames of the room loop, and the ghost and the bubble are
    ERASED AND REDRAWN every one of them — so a capture taken then catches whichever side of that
    cycle the run happened to be on, and the two sides differed by exactly the ghost and the bubble
    when the comparison was made off the late dump (measured, 556 of 32,000 bytes).
    """
    work = session.work
    files = {"shot": work / f"{side}_room.png", "pens": work / f"{side}_room_pens.bin",
             "screen": work / f"{side}_room_screen.bin", "done": work / f"{side}_room_done.bin"}
    for stale in files.values():
        stale.unlink(missing_ok=True)
    shoot = action_file(
        work, f"{side}_room.txt",
        f"screenshot {files['shot']}",
        f"savebin {files['pens']} ${HW_PALETTE_BASE:x} ${PALETTE_PENS * PEN_BYTES:x}",
        f"savebin {files['done']} ${HW_SHIFTER_MODE:x} $1")
    settle = settle_chain(work, ANCHOR_SETTLE_VBLS - 1, shoot, f"{side}_roomwait%d.txt")
    entry = action_file(work, f"{side}_roomentry.txt",
                        f"savebin {files['screen']} ${screen_address:x} ${SCREEN_BYTES:x}",
                        f"b VBL > VBL :once :quiet {settle}")
    session.arm(f"b pc = ${room_pc:x} :once :quiet {entry}")
    return files


def press_the_game_keys(session, room_is_open, deadline_seconds):
    """Send `G` and then `1` over and over until the room opens. Answers whether it did.

    BOTH KEYS ARE RESENT, and a single pass with a fixed gap is exactly what does not work —
    measured, three failures to one success before the loop was written. Two things can eat a press
    and neither is observable from here: `menu_ask_player_count` ENDS with a console flush
    (`drain_console_queue`), so a `1` that arrives while the two prompt lines are still being drawn
    is emptied by the program's own drain; and a `G` that arrives in the window between the anchor's
    capture and the program reaching its `Cnecin` is simply not there when the read happens. Either
    one leaves the run blocked for ever on a screen a check cannot tell from the other.

    The PAIR is what makes the loop safe to repeat. On the menu, `G` opens the prompt and `1`
    answers it; on the prompt, a stray `G` is a digit that is neither 1 nor 2 and the program asks
    again; in the room, both are keys `frame_poll_input` does not act on. So every pass either makes
    progress or changes nothing, whichever screen the program is on.
    """
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        session.key(KEY_G)
        session.wait(GAME_KEY_RETRY_SECONDS)      # ...for the prompt to draw AND run its flush
        session.key(KEY_ONE)
        session.wait(GAME_KEY_RETRY_SECONDS)
        if not session.alive():
            return False
        if room_is_open():
            return True
    return False


def run_the_game_ours(work):
    """Boot the `play` build, wait for its menu, press G and 1, and watch the room loop turn."""
    work.mkdir(parents=True, exist_ok=True)
    for stale in (FILE_ANCHOR_BASE, FILE_SCREEN_DUMP, FILE_STATE_RECORD):
        (DISK / "c" / stale).unlink(missing_ok=True)
    trace = work / "ours.trace"
    medium = ours_medium()
    session = HeadlessSession(hatari_arguments(medium, trace), work / "ours.log",
                              work / "ours.fifo", work)
    result = {"trace": trace, "log": work / "ours.log", "mode": "game"}

    anchors = await_the_anchor_table(session, result)
    if anchors is None:
        return result
    if anchors[ANCHOR_ROOM_FRAME] == 0:
        result["status"] = session.close()
        result["problem"] = ("the .PRG under test composes no room loop — it is a `title` build, "
                             "and this mode has nothing to drive. Run `bash atari/build.sh play`")
        return result

    tally = anchors[ANCHOR_PLAY_TALLY]
    room = arm_the_room_anchor(session, anchors[ANCHOR_ROOM_FRAME], "ours",
                               anchors[ANCHOR_IMAGE_BASE] + SCREEN_BASE)
    if not await_play_tally(session, tally, TALLY_MENU_OPENS, 1,
                            "waiting for the menu to be drawn", MENU_DEADLINE_SECONDS):
        result["status"] = session.close()
        result["problem"] = "the menu was never opened, so no key could be sent"
        return result
    press_the_game_keys(
        session,
        lambda: read_play_tally(session, tally)[TALLY_GAME_FRAMES] >= GAME_FRAMES_REQUIRED,
        ROOM_DEADLINE_SECONDS)
    result["alive"] = session.alive()
    result["frames"] = read_play_tally(session, tally)[TALLY_GAME_FRAMES] if result["alive"] else 0
    if room["done"].is_file():
        result["room_pens"] = room["pens"].read_bytes()
        result["screen"] = room["screen"].read_bytes()
    result["shot"] = room["shot"]
    result["status"] = session.close()
    return result


def run_the_game_original(work):
    """The same two keys, on the shipped binary, judged at the same first-room-frame anchor."""
    work.mkdir(parents=True, exist_ok=True)
    trace = work / "orig.trace"
    medium = original_medium()
    session = HeadlessSession(hatari_arguments(medium, trace), work / "orig.log",
                              work / "orig.fifo", work)
    result = {"trace": trace, "log": work / "orig.log"}

    base = await_the_decrypted_original(session, result)
    if base is None:
        return result

    menu = arm_the_anchor(session, base - LOAD_BASE + ORIGINAL_ANCHOR_PC, "orig")
    if not await_file(session, menu["done"], "waiting for the original to draw its menu",
                      MENU_DEADLINE_SECONDS, POLL_SECONDS):
        result["status"] = session.close()
        result["problem"] = "the original never drew its menu, so no key could be sent"
        return result
    # ...AND ONLY NOW is there a screen base to dump from. `init_gem_and_screens` takes it off XBIOS
    # long before the menu, but the plaintext this run breaks on exists from the moment the program
    # decrypts itself — which is earlier still, so a read taken when the base was FOUND would be a
    # read of whatever that longword held before the boot wrote it.
    phys = struct.unpack(">I", session.savebin("phys.bin", base - LOAD_BASE + A_screen_phys, 4))[0]
    result["screen_phys"] = phys
    room = arm_the_room_anchor(session, base - LOAD_BASE + ORIGINAL_ROOM_FRAME_PC, "orig", phys)
    if press_the_game_keys(session, room["done"].is_file, ROOM_DEADLINE_SECONDS):
        result["room_pens"] = room["pens"].read_bytes()
        result["screen"] = room["screen"].read_bytes()
    result["alive"] = session.alive()
    result["shot"] = room["shot"]
    result["status"] = session.close()
    return result


def check_the_game_path(ours, original):
    """The G key reached a running room loop, on a machine that faulted nowhere."""
    problems = []
    if ours.get("problem"):
        problems.append(f"ours: {ours['problem']}")
    if original.get("problem"):
        problems.append(f"the original: {original['problem']}")
    for side, run in (("ours", ours), ("the original", original)):
        # ...only where the side got far enough for "gone" to MEAN something: a run that never
        # reached its menu has already said so above, and this would repeat it as a second cause.
        if not run.get("problem") and not run.get("alive", False):
            problems.append(f"{side}: the program was gone before the run was stopped — it "
                            f"terminated or the machine died, which is what a return to the "
                            f"desktop looks like from here")
        problems += [f"{side}: {problem}"
                     for problem in check_machine_health(run.get("status", 0), run["log"])]
    frames = ours.get("frames", 0)
    if frames < GAME_FRAMES_REQUIRED:
        problems.append(f"the room loop ran {frames} frame(s) and this check needs "
                        f"{GAME_FRAMES_REQUIRED}: pressing G did not reach a turning room loop")
    return problems


def check_the_room_state(ours, original):
    """The chip and the framebuffer at the first frame of the room, ours against the original's."""
    problems = []
    for side, run in (("ours", ours), ("the original", original)):
        if run.get("room_pens") is None:
            problems.append(f"{side}: the first room frame was never reached, so there is nothing "
                            f"to compare at it")
    if problems:
        return problems
    mine = struct.unpack(f">{PALETTE_PENS}H", ours["room_pens"])
    theirs = struct.unpack(f">{PALETTE_PENS}H", original["room_pens"])
    for pen, (a, b) in enumerate(zip(mine, theirs)):
        if (a ^ b) & SHIFTER_PEN_MASK:
            problems.append(f"pen {pen} is {a & SHIFTER_PEN_MASK:03x} in our room and the "
                            f"original's is {b & SHIFTER_PEN_MASK:03x}")
    if ours.get("screen") and original.get("screen"):
        differing = sum(1 for a, b in zip(ours["screen"], original["screen"]) if a != b)
        if differing:
            problems.append(f"{differing} of {SCREEN_BYTES} framebuffer bytes differ at the first "
                            f"room frame")
        elif not any(ours["screen"]):
            problems.append("both room framebuffers are entirely zero, so their equality means "
                            "nothing")
    return problems


CHECK_GAME_PATH = "exit status + log (the G key reaches a turning room loop)"
CHECK_ROOM_STATE = "memory + hardware-state vector (the first room frame, against the original's)"


def run_the_game():
    # The `play` build by NAME, copied over the drive's BUBBLE.PRG exactly as run.sh does — so this
    # mode judges the play .PRG whichever build ran last, rather than whatever the drive happens to
    # be carrying.
    play_prg = HERE / "build" / "BUBBLE-play.PRG"
    if not play_prg.is_file():
        raise SystemExit(f"ERROR: no {play_prg} — run `bash atari/build.sh play` first")
    shutil.copy(play_prg, DISK / "c" / "BUBBLE.PRG")
    if not (DISK / "GHOST.ST").is_file():
        raise SystemExit(f"ERROR: no {DISK / 'GHOST.ST'} — run `bash atari/build.sh play` first")
    if not ORIGINAL_STX.is_file():
        raise SystemExit(f"ERROR: no {ORIGINAL_STX} — the original is half of this comparison")
    work = OUT / "game"
    ours = run_the_game_ours(work)
    original = run_the_game_original(work)

    checks = {CHECK_GAME_PATH: check_the_game_path,
              CHECK_ROOM_STATE: check_the_room_state,
              CHECK_NOT_BLANK: check_neither_capture_is_blank}
    print(f"-- game on st / {TOS_ROM.name} at {MEMSIZE_MB} MB: G then 1, one player, "
          f"the original at {original.get('load_base') or 0:#x}")
    print(f"   ours ran {ours.get('frames', 0)} room frame(s) after the two keys")
    failures = []
    for name, check in sorted(checks.items()):
        problems = check(ours, original)
        print(f"   [{'red ' if problems else 'green'}] {name}   (must PASS)")
        for problem in problems:
            print(f"           {problem}")
        if problems:
            failures.append(name)
    print("   the mouse is untouched on both sides: Hatari has no mouse-motion event, so this mode "
          "judges the two keys and the room they open, not playing the game")
    print("-- OK" if not failures else f"-- FAILED: {len(failures)} check(s)")
    return 0 if not failures else 1


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "title"
    if mode not in ("title", "floppy", "game", *CONTROLS):
        raise SystemExit(f"usage: smoke.py [title | {' | '.join(CONTROLS)} | floppy | game]")
    require_gemdos_tos(TOS_ROM)
    if mode == "floppy":
        return run_the_floppy()
    if mode == "game":
        return run_the_game()
    for needed in (DISK / "c" / "BUBBLE.PRG", DISK / "GHOST.ST"):
        if not needed.is_file():
            raise SystemExit(f"ERROR: no {needed} — run `bash atari/build.sh {mode}` first")
    if not ORIGINAL_STX.is_file():
        raise SystemExit(f"ERROR: no {ORIGINAL_STX} — the original is half of every comparison "
                         f"here, and a run without it would compare this build to nothing")
    work = OUT / mode
    ours = run_ours(mode, work)
    original = run_original(work)
    return report(ours, original, mode)


if __name__ == "__main__":
    sys.exit(main())
