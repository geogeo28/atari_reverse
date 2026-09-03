#!/usr/bin/env python3
"""Boot Zynaps in Hatari, drive it with the keyboard, and photograph what a player sees.

    python3 projects/zynaps/tools/boot_shots.py stx      # the Pasti dump, protection intact
    python3 projects/zynaps/tools/boot_shots.py st       # the patched raw sector image
    python3 projects/zynaps/tools/boot_shots.py gemdos   # bin/disk/ as drive C:, auto-run the PRG
    python3 projects/zynaps/tools/boot_shots.py stx --tos 102          # ...on TOS 1.02 instead of 1.04
    python3 projects/zynaps/tools/boot_shots.py stx --tos-rom /path/to/tos.img
    python3 projects/zynaps/tools/boot_shots.py sheet                  # tile the captures into one picture
    python3 projects/zynaps/tools/boot_shots.py stx --print-command    # the GUI command line, one arg per line

THIS FILE OWNS THE HATARI COMMAND LINE for the whole project — the media matrix, the TOS ROM, the
machine and the memory size. `play.sh` is a thin wrapper that asks for the GUI variant with
`--print-command` and execs it, so the two cannot drift: they did, three ways (the gold master was
mounted writable here and write-protected there, the sound rate differed, and each had its own idea
of how a TOS ROM is selected).

Screenshots land in <out>/<mode>_<tosNNN>_<tag>.png and Hatari's log in <out>/<mode>_<tosNNN>.log.
The TOS tag is in BOTH names because it is derived from the ROM's own version word, and because a
`--tos 102` run must not overwrite the 1.04 evidence.

THE RUN IS ANCHORED ON WHAT THE MACHINE DID, NOT ON A STOPWATCH, and twice.  The first anchor is
the moment the PRG's TEXT appears in RAM, polled for rather than waited out -- a fixed pre-roll
lands wherever the host's speed puts it, and the same poll yields the load address every poke below
needs.  The second is the moment the PREPARE-FOR-COMBAT gate is actually crossed, which the gate's
own breakpoint reports by dumping one byte to a host file.  Both exist because a capture cannot
otherwise be trusted to mean what its tag says: with fixed delays the in-game captures were the
level on one medium and still the PREPARE FOR COMBAT screen on another, ten seconds apart, and
nothing in the picture distinguishes them -- both are the same status panel in 32 colours.

WHY THE KEYBOARD, AND WHY THE STICK IS POKED INSTEAD.  Hatari's `--cmd-fifo` has no joystick event
(`hatari-event` accepts only mouse buttons and keys), and a key bound to the keyboard-as-joystick
emulation is swallowed headless rather than reaching either the ST keyboard or the emulated stick.
Zynaps' front end does not need one: its ACIA handler files every make code in a "last key" byte and
the menu tests '1' and '2' against it (NOT space -- see the TIMELINE comment below).  Its
PREPARE-FOR-COMBAT gate DOES: that loop sends IKBD
$16 (interrogate joystick) and spins until bit 7 of the joystick byte is set, and no key will do.
So the byte the ACIA handler files the $FD reply into is poked directly.  That exercises everything
above the byte and nothing below it: the IKBD-to-$9681 delivery stays unproven either way, and so
does steering, which is never driven here.

The poke is armed AS A BREAKPOINT ON THE GATE'S OWN `tst.b`, not fired on a timer.  A timed poke
races the real IKBD replies, which clear the same byte a few thousand cycles later: it opened the
gate in one run out of three and left the other two sitting on PREPARE FOR COMBAT.  Stopping the CPU
on the instruction that reads the byte and writing it there removes the race entirely.

THE SUCCESS GATE IS NOT "THE PNGs EXIST".  Hatari photographs a blank screen just as happily as a
running game and exits 0 after a bus error it only mentioned in its log.  A run passes only if the
log carries no fault line, the emulator was alive for the whole timeline and exited cleanly, every
capture holds more than one colour, and the level-1 capture is not the same picture as the first
front-end one.  See docs/on-target-execution.md, "The observable surfaces".
"""
import argparse
import struct
import sys
import tempfile
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[1]
sys.path.insert(0, str(REPO / "tools"))

from hatari_headless import (  # noqa: E402  (needs the path above)
    HATARI, POLL_SECONDS, HeadlessSession, action_file, distinct_colours, locate_by_signature,
    log_faults, pc_breakpoint, poke_byte, same_picture)

# --- media ---------------------------------------------------------------------------------------
STX_IMAGE = REPO / "gw" / "dumps" / "zynaps" / "zynaps.stx"
ST_IMAGE = PROJECT / "bin" / "zynaps.st"
GEMDOS_DIR = PROJECT / "bin" / "disk"
GEMDOS_AUTO = r"C:\AUTO\ZYNAPS17.PRG"
GAME_PRG = PROJECT / "bin" / "ZYNAPS17.PRG"

BOOT_MODES = ("stx", "st", "gemdos")
SHEET_MODE = "sheet"

# --- the machine ---------------------------------------------------------------------------------
TOS_DIR = REPO / "tools" / "hatari"
TOS_SHORTCUTS = {"104": TOS_DIR / "TOS104US.img", "102": TOS_DIR / "TOS102US.img"}
DEFAULT_TOS = "104"
# A TOS ROM carries its own version as a BCD word at offset 2 ($0104 = 1.04), so the tag on every
# file this writes comes from the ROM that was actually booted and not from how it was asked for.
TOS_VERSION_OFFSET = 2
# Hatari refuses GEMDOS directory emulation below TOS 1.04 and then simply does not mount the drive,
# so the --auto program never runs. That is an emulator limit, not a Zynaps one — the floppy modes
# cover TOS 1.02 — but the run has to say so instead of failing later with a confusing symptom.
GEMDOS_MIN_TOS_VERSION = 0x0104

# The 1988 ST release is a 512 KB-era game; 1 MB is the safe superset and what every other project
# in this workspace boots with.
MEMSIZE_MB = 1
# Hatari quits by itself at this count, so a hung run cannot sit there for ever. 50 Hz => 240 s,
# comfortably past the whole timeline plus the slowest floppy boot.
RUN_VBLS = 12000
GUI_SOUND_HZ = 44100

# --- the game's own addresses ---------------------------------------------------------------------
# Offsets into the loaded TEXT, read out of out/prg_dis.txt, whose addresses carry the sweep's
# nominal $10000 base. The ACIA handler files the second byte of the IKBD $FD (joystick interrogate)
# reply at $9681, and every joystick test in the game reads it.
JOY1_STATE_OFFSET = 0x9681
JOY1_FIRE = 0x80
# The PREPARE-FOR-COMBAT gate's own `tst.b $9681` ($10f2a in the sweep). Its loop re-sends IKBD $16
# and spins on `bpl` until bit 7 -- fire -- is set. It was FOUND, not read off the sweep: three other
# `tst.b $9681` loops look just like it, and the one that was actually spinning came from the return
# address on the supervisor stack while the game sat on the gate.
GATE_FIRE_DOWN_OFFSET = 0x0F2A
FIRE_ACTION_FILE = "FIRE.INI"
# The same action file also dumps the byte it just wrote to a host file, which is how the driver
# SEES the gate being crossed instead of guessing when. Nothing else can tell "PLAYER 1 / PREPARE
# FOR COMBAT" from the level behind it, and a fixed delay after the '1' key got that wrong by ten
# seconds on one medium and not on another (measured).
GATE_MARKER_FILE = "GATEOPEN.BIN"
GATE_DEADLINE_SECONDS = 60.0

ST_RAM_BYTES = 0x100000
RAM_DUMP_NAME = "ram.bin"

# --- ST keyboard make codes, as the game's ACIA handler files them into its "last key" byte --------
KEY_SPACE, KEY_ONE_PLAYER = 0x39, 0x02

# --- when things happen ----------------------------------------------------------------------------
# Nothing can be loaded before TOS has booted and read the AUTO folder, so the poll does not start
# until then; each poll costs one 1 MB RAM dump through the debugger, which is why it is a poll and
# not a busy loop. Measured on this host: the PRG is in RAM at ~7 s off a floppy, ~11 s off drive C:.
LOAD_POLL_START_SECONDS = 6.0
LOAD_POLL_INTERVAL_SECONDS = 1.0
LOAD_DEADLINE_SECONDS = 90.0

# Seconds after the PRG's TEXT appears in RAM, with the tag to capture and the key to press.
# MEASURED ON THE FLOPPY, which is the slow case: the program is in RAM at power-on + ~7 s but then
# spends ~20 s reading its 62 data files off the disk behind a STATIC loading picture, and the
# interactive front end (credits + menu) only comes up around load + 27 s. Sampling every 2 s over a
# whole boot is how these came out; a capture placed inside the load window photographs the same
# loading picture three times and calls it three different things. The GEMDOS drive gets there in a
# fraction of the time and simply idles in the front end until the timeline catches up.
# The front end then CYCLES its pages by itself (ROLE OF HONOUR, credits + menu, loading picture), so
# which page a capture catches is not fixed; '1' starts a one-player game from any of them.
AWAIT_GATE = "await-gate"   # re-anchors the clock on the moment the fire gate is crossed

TIMELINE = (
    (30.0, "front1", None),
    # SPACE IS A NO-OP HERE -- the front end's pages turn on a timer of their own and it tests only
    # '1', '2' and fire. The row is kept because removing it would move every later step's timing for
    # no gain, and it is harmless: the release code falls inside the ACIA handler's clear window, so
    # nothing leaks into the '1' press below. NOTHING HERE OBSERVES THE KEY ARRIVING -- the run that
    # does is `tools/secrets_demo.py pause`. See README.md, "Secrets and dead code".
    (34.0, None, KEY_SPACE),
    (38.0, "front2", None),
    (42.0, None, KEY_ONE_PLAYER),   # '1' starts a one-player game
    (48.0, "getready", None),       # PLAYER 1 / PREPARE FOR COMBAT over the status panel
    (None, None, AWAIT_GATE),       # ...and from here the seconds count from the gate, not the load
    (3.0, "level1", None),          # the scrolling level itself
    (11.0, "level1_later", None),
)
TAIL_SECONDS = 1.0                  # let the last screenshot land before the emulator is told to quit

# A timeline step that starts late has already missed the moment its tag names. Below the warning
# threshold that is host jitter; past the failure one the captures no longer mean what they say.
OVERRUN_WARN_SECONDS = 0.25
OVERRUN_FAIL_SECONDS = 2.0

# --- the success gate --------------------------------------------------------------------------
# The first front-end capture and the in-game one. If they are the same picture the run never left
# the front end, however many PNGs it wrote.
TAG_FRONT1, TAG_LEVEL1 = "front1", "level1"
BLANK_COLOUR_COUNT = 1              # a capture with one colour is a photograph of nothing
# The game blanks the screen for about two seconds between front-end pages, and that gap moves with
# the TOS version: a capture placed near it caught a black frame on 1.02 and a page on 1.04. Retaking
# is right where failing is not — the run is fine, the shutter was early — and a screen that is STILL
# blank after every retry falls through to the gate below, which is what a real fault looks like.
CAPTURE_RETRIES = 5
CAPTURE_RETRY_SECONDS = 2.0

# --- the contact sheet ---------------------------------------------------------------------------
CONTACT_SHEET_SHRINK = 3


def tos_version(rom):
    """The BCD version word a TOS ROM carries at offset 2 ($0104 = TOS 1.04)."""
    with open(rom, "rb") as image:
        image.seek(TOS_VERSION_OFFSET)
        return struct.unpack(">H", image.read(2))[0]


def tos_tag(version):
    """$0104 -> "tos104" — the stem every file of a run is tagged with."""
    return "tos%x%02x" % (version >> 8, version & 0xFF)


def tos_label(version):
    """$0104 -> "1.04", for messages."""
    return "%x.%02x" % (version >> 8, version & 0xFF)


def resolve_tos(rom_path, shortcut):
    """(ROM path, version word) from an explicit path or one of the shortcut keys."""
    rom = Path(rom_path).resolve() if rom_path else TOS_SHORTCUTS[shortcut]
    if not rom.is_file():
        raise SystemExit(f"missing TOS ROM {rom}")
    return rom, tos_version(rom)


def media_arguments(mode):
    """The Hatari media options for one boot mode, and the ONLY place they are spelled.

    The gold master is never written to, so the .stx is mounted WRITE-PROTECTED; the .st gets the
    same treatment because the game saves nothing to disk anyway (its only file calls are
    Fopen/Fread/Fclose).
    """
    if mode == "stx":
        return ["--disk-a", str(STX_IMAGE), "--protect-floppy", "on"]
    if mode == "st":
        return ["--disk-a", str(ST_IMAGE), "--protect-floppy", "on"]
    if mode == "gemdos":
        return ["--harddrive", str(GEMDOS_DIR), "--auto", GEMDOS_AUTO]
    raise SystemExit(f"unknown mode {mode!r}")


def hatari_arguments(mode, rom, gui, sound_hz=None):
    """The whole Hatari command line for a mode, GUI or headless. `--cmd-fifo` is the session's.

    A headless run is silent unless `sound_hz` asks for a rate: nothing in a screenshot timeline
    needs the mixer, and turning it off is the fastest setting. `tools/ref_capture.py` passes one,
    because a recording of the real game is the only surface that can judge the dumps' renderer.
    """
    display = ["--sound", str(GUI_SOUND_HZ), "--joy1", "keys", "--zoom", "2"] if gui else \
              ["--sound", str(sound_hz) if sound_hz else "off", "--run-vbls", str(RUN_VBLS)]
    return ([HATARI, "--tos", str(rom), "--machine", "st", "--memsize", str(MEMSIZE_MB),
             "--monitor", "rgb", "--confirm-quit", "off", "--statusbar", "off",
             "--drive-led", "off", "--frameskips", "0"]
            + display + media_arguments(mode))


def refuse_unsupported(mode, version):
    if mode == "gemdos" and version < GEMDOS_MIN_TOS_VERSION:
        raise SystemExit(f"Hatari will not emulate a GEMDOS drive on TOS {tos_label(version)} — it needs "
                         f"{tos_label(GEMDOS_MIN_TOS_VERSION)} or later. Use a floppy mode instead.")


def shot_path(out_dir, mode, tag, capture):
    return out_dir / f"{mode}_{tag}_{capture}.png"


def log_path(out_dir, mode, tag):
    return out_dir / f"{mode}_{tag}.log"


def wait_for_load(session):
    """Poll RAM until the PRG's TEXT is in it, and return where. This is the run's real start."""
    session.wait(LOAD_POLL_START_SECONDS)
    deadline = time.monotonic() + LOAD_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        base = locate_by_signature(session.savebin(RAM_DUMP_NAME, 0, ST_RAM_BYTES), GAME_PRG)
        if base is not None:
            return base
        session.wait(LOAD_POLL_INTERVAL_SECONDS)
    raise SystemExit(f"{GAME_PRG.name} was still not in RAM {LOAD_DEADLINE_SECONDS:.0f} s after power-on — "
                     f"the medium did not boot, or the AUTO folder did not run it")


def arm_fire_gate(session, base):
    """Answer the PREPARE-FOR-COMBAT gate the next time it asks, and return the marker it leaves.

    NOT `:once`: the same gate guards every respawn, and a one-shot breakpoint leaves the run sitting
    on PREPARE FOR COMBAT again the moment the unattended ship is shot down. Which also means the
    marker is rewritten on every respawn; only its FIRST appearance is read.
    """
    joystick_byte = base + JOY1_STATE_OFFSET
    marker = session.work / GATE_MARKER_FILE
    marker.unlink(missing_ok=True)
    action = action_file(session.work, FIRE_ACTION_FILE,
                         poke_byte(joystick_byte, JOY1_FIRE),
                         f"savebin {marker} ${joystick_byte:x} $1")
    session.arm(pc_breakpoint(base + GATE_FIRE_DOWN_OFFSET, action))
    return marker


def await_gate(session, marker):
    """Block until the fire gate is actually crossed, and return that moment.

    This is the run's second anchor and it exists because a capture cannot be trusted to mean what
    its tag says otherwise: "PLAYER 1 / PREPARE FOR COMBAT" and the level behind it are both a
    32-colour picture of the status panel, and the delay between the '1' key and the level differed
    by more than ten seconds between two media on the same host.
    """
    deadline = time.monotonic() + GATE_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        if marker.is_file():
            return time.monotonic()
        session.require_alive("waiting for the PREPARE-FOR-COMBAT gate")
        session.wait(POLL_SECONDS)
    raise SystemExit(f"the PREPARE-FOR-COMBAT gate was never reached in {GATE_DEADLINE_SECONDS:.0f} s "
                     f"— the '1' key did not start a game, or the breakpoint never fired")


def step_name(capture, action):
    """What a timeline step is called in a message."""
    if capture:
        return capture
    return AWAIT_GATE if action == AWAIT_GATE else f"key {action:#04x}"


def capture_frame(session, path):
    """Photograph the frame, retaking while the screen is blank. See CAPTURE_RETRIES."""
    for _ in range(CAPTURE_RETRIES):
        shot = session.screenshot(path)
        if distinct_colours(shot) > BLANK_COLOUR_COUNT:
            return shot
        session.wait(CAPTURE_RETRY_SECONDS)
    return shot


def play_timeline(session, out_dir, mode, tag, loaded_at, marker):
    """Replay TIMELINE from the load, then from the gate. Returns (captures, overrun complaints)."""
    captures = {}
    complaints = []
    anchor = loaded_at
    for at, capture, action in TIMELINE:
        if action == AWAIT_GATE:
            # The re-anchoring step waits on the machine, not on the clock, so it has no schedule of
            # its own to be late for; `at` is not read here and the rows after it restart from 0.
            anchor = await_gate(session, marker)
            continue
        slack = anchor + at - time.monotonic()
        if slack < -OVERRUN_WARN_SECONDS:
            complaints.append((step_name(capture, action), -slack))
        session.wait(max(0.0, slack))
        session.require_alive(f"running the timeline at +{at:.0f}s")
        if capture:
            captures[capture] = capture_frame(session, shot_path(out_dir, mode, tag, capture))
        if action is not None:
            session.key(action)
    session.wait(TAIL_SECONDS)
    return captures, complaints


def check_captures(captures):
    """Why this set of captures is not evidence, or an empty list if it is."""
    problems = []
    for capture, path in sorted(captures.items()):
        colours = distinct_colours(path)
        if colours <= BLANK_COLOUR_COUNT:
            problems.append(f"{path.name} holds {colours} colour — the screen was blank")
    if TAG_FRONT1 in captures and TAG_LEVEL1 in captures \
            and same_picture(captures[TAG_FRONT1], captures[TAG_LEVEL1]):
        problems.append(f"{captures[TAG_LEVEL1].name} is the same picture as {captures[TAG_FRONT1].name} — "
                        f"the game never left the front end")
    return problems


def run(mode, out_dir, rom, version):
    """Boot one medium, photograph it, and judge the run. True if it is evidence."""
    refuse_unsupported(mode, version)
    # ABSOLUTE paths throughout: Hatari resolves a screenshot name against its own working directory,
    # and a relative one writes somewhere nobody is looking while the run still exits 0.
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = tos_tag(version)
    log = log_path(out_dir, mode, tag)
    with tempfile.TemporaryDirectory() as work:
        session = HeadlessSession(hatari_arguments(mode, rom, gui=False), log_path=log,
                                  fifo_path=out_dir / f"{mode}.fifo", work_dir=work)
        try:
            base = wait_for_load(session)
            marker = arm_fire_gate(session, base)
            loaded_at = time.monotonic()
            captures, complaints = play_timeline(session, out_dir, mode, tag, loaded_at, marker)
        finally:
            status = session.close()

    problems = [f"Hatari logged: {line}" for line in log_faults(log)]
    problems += [f"{what} started {late:.1f}s late" for what, late in complaints if late >= OVERRUN_FAIL_SECONDS]
    if status != 0:
        problems.append(f"Hatari exited with status {status}")
    problems += check_captures(captures)

    print(f"-- {mode} (TOS {tos_label(version)}): loaded at {loaded_at - session.started:.1f}s, "
          f"{len(captures)} captures in {out_dir}")
    for what, late in complaints:
        print(f"   warning: {what} started {late:.1f}s late")
    for problem in problems:
        print(f"   FAIL: {problem}")
    return not problems


def build_contact_sheet(out_dir, tag):
    """One picture of every capture of one TOS version, so three boots can be read in a single look."""
    from PIL import Image
    captures = [capture for _, capture, _ in TIMELINE if capture]
    complete = [[shot_path(out_dir, mode, tag, capture) for capture in captures] for mode in BOOT_MODES]
    complete = [shots for shots in complete if all(shot.is_file() for shot in shots)]
    if not complete:
        raise SystemExit(f"no complete set of {tag} captures in {out_dir} — run a boot mode first")
    tiles = [[Image.open(shot).convert("RGB") for shot in shots] for shots in complete]
    width, height = tiles[0][0].size
    cell = (width // CONTACT_SHEET_SHRINK, height // CONTACT_SHEET_SHRINK)
    sheet = Image.new("RGB", (cell[0] * len(tiles[0]), cell[1] * len(tiles)))
    for row, pictures in enumerate(tiles):
        for column, picture in enumerate(pictures):
            sheet.paste(picture.resize(cell), (column * cell[0], row * cell[1]))
    target = out_dir / f"contact_sheet_{tag}.png"
    sheet.save(target)
    print(f"-- contact sheet: {len(tiles)} boot(s) x {len(tiles[0])} captures -> {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=BOOT_MODES + (SHEET_MODE,))
    parser.add_argument("--out", type=Path, default=PROJECT / "out" / "boot")
    parser.add_argument("--tos", choices=tuple(TOS_SHORTCUTS), default=DEFAULT_TOS,
                        help="shortcut for one of the ROMs in tools/hatari (default 104)")
    parser.add_argument("--tos-rom", help="boot this TOS image instead; its version word names the output files")
    parser.add_argument("--print-command", action="store_true",
                        help="print the GUI Hatari command line, one argument per line, and exit")
    options = parser.parse_args()

    rom, version = resolve_tos(options.tos_rom, options.tos)
    if options.print_command:
        if options.mode == SHEET_MODE:
            parser.error("--print-command needs a boot mode, not the contact sheet")
        refuse_unsupported(options.mode, version)
        print("\n".join(hatari_arguments(options.mode, rom, gui=True)))
        return 0
    if options.mode == SHEET_MODE:
        build_contact_sheet(options.out.resolve(), tos_tag(version))
        return 0
    return 0 if run(options.mode, options.out, rom, version) else 1


if __name__ == "__main__":
    sys.exit(main())
