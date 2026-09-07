#!/usr/bin/env python3
"""Boot the UNMODIFIED Flying Shark payload under Hatari and photograph what a player sees.

    python3 projects/flyingshark/tools/boot_shots.py                    # bin/disk as C:, TOS 1.04
    python3 projects/flyingshark/tools/boot_shots.py --tos 102 --memsize 4
    python3 projects/flyingshark/tools/boot_shots.py --print-command    # the argv, one per line

WHY THIS EXISTS. `unpack_dist.py` claims the game runs out of a plain folder — the payload in
`AUTO\\`, its data in a subdirectory `A` — with the Gamex stub, the GOS and the FRD container all
gone. That claim is only worth something if a 68000 agrees, so this boots the folder as a GEMDOS
drive and photographs what happens. It is the reference run every later reconstruction is compared
against.

THERE IS NO `--auto` ON THIS COMMAND LINE, AND THAT IS THE POINT. `unpack_dist.py` puts the payload
in `disk/AUTO/`, so TOS's own boot runs it BEFORE it loads the desktop — which is the only way it
gets a TPA low enough to survive. The game asks for a fixed screen at $70000/$78000 and builds its
scroll ring downwards from Physbase; the ring only clears the program's own BSS if the program
loaded at or below $d922. Started from the desktop with `--auto` (measured: TEXT at $12596, BSS
ending at $5d474) the ring lands on top of the loaded music driver and the game dies on an illegal
instruction a second after the last file loads. Started from `AUTO\\` it loads at $aa56, ends at
$55934, clears the ring by 11,980 bytes, and plays. notes/loader.md, "Where the screen lives", has
the arithmetic.

WHAT THE RUN PROVES. Hatari's log carries no fault marker, the emulator was alive throughout and
exited cleanly, one capture IS the title picture, and two later captures are DIFFERENT pictures from
it and from each other — the attract cycle (title, hall of fame over a scrolling level, credits)
running of its own accord. That covers loading all eight files through TOS's own GEMDOS, the front
end, the level renderer and the vertical scroll. It does not cover input: a key bound to Hatari's
keyboard-as-joystick emulation is SWALLOWED headless (see tools/hatari_headless.py), so the stick
cannot be pressed from outside at all — and the attract mode does not need it.

A capture is the title when every colour of `FLY_SHK.NEO`'s own palette is on screen at once. That
separates the three states cleanly and with no threshold to tune — measured 15/15 on the title, 5/15
on the TOS desktop, 1/15 on a blank screen, and 4/15 on the attract screens that follow. Captures
are compared in the ST's own 3-bit-per-channel space because Hatari's 8-bit expansion of a colour
word is not this workspace's (73 where `st_pixels` says 72), so a literal RGB comparison matches
only black.

FOUR ANCHORS WERE TRIED FOR THAT CAPTURE AND THREE ARE WRONG, which is most of what this file knows.
They were all found against the desktop recipe, where the title was on screen for one or two
emulated seconds before the crash; the working recipe leaves it up for several, but the reasons hold:

  * A fixed pre-roll photographed one flat colour three times over — once ten seconds before the
    picture existed, once after TOS had taken the screen back.
  * Polling RAM for the payload's TEXT is both late and slow: the program is in memory seconds
    before it has drawn anything, and a 1 MB `savebin` per poll is a debugger stop per poll.
  * Waiting for the picture's own `Fopen` in a `--trace os_base` file looks exact and is not:
    **Hatari's trace file is buffered**, and by the time the line for the SECOND file appears on the
    host, all eight opens are already in it. Read that trace afterwards for the load order — it is
    worth having, and this run keeps it — never as a live signal.
  * What works is recognising the picture, and `--slowdown N` when the window is too narrow to
    photograph: it multiplies Hatari's per-VBL wait, so the timeline stretches by N while the
    machine still executes everything it would have. The working recipe does not need it.

TOS 1.04 IS NOT A PREFERENCE. Hatari refuses GEMDOS directory emulation below it and then simply
does not mount the drive, so nothing on it ever runs. `--tos 102` is kept because it says so out
loud instead of producing a run that did nothing.
"""
import argparse
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(PROJECT / "tools"))

from hatari_headless import (  # noqa: E402  (needs the paths above)
    HATARI, HeadlessSession, distinct_colours, locate_by_signature, log_faults, require_gemdos_tos,
    same_picture, strip_log_noise, tos_label, tos_version)
from extract_assets import title_palette  # noqa: E402
from unpack_dist import (  # noqa: E402
    AUTO_SUBDIR, DEPACKED_GAME, DISK_SUBDIR, GAME_DATA_SUBDIR, NEO_NAME)

# --- media ---------------------------------------------------------------------------------------
GEMDOS_DIR = PROJECT / "bin" / DISK_SUBDIR
GAME_PRG = GEMDOS_DIR / AUTO_SUBDIR / DEPACKED_GAME
TITLE_NEO = GEMDOS_DIR / GAME_DATA_SUBDIR / NEO_NAME
OUT_DIR = PROJECT / "out" / "boot"

# --- the machine ---------------------------------------------------------------------------------
TOS_DIR = REPO / "tools" / "hatari"
TOS_SHORTCUTS = {"104": TOS_DIR / "TOS104US.img", "102": TOS_DIR / "TOS102US.img"}
DEFAULT_TOS = "104"
# The release's own README says 1 MB minimum, but that is the GAMEX runtime's floor: the payload
# alone needs its 0x4AFDE of text+data+bss plus TOS, which fits a 512 KB machine. 1 MB is the
# workspace default and the safe superset.
DEFAULT_MEMSIZE_MB = 1
# Hatari quits by itself at this count so a hung run cannot sit for ever. 50 Hz => 240 s.
RUN_VBLS = 12000

# The GEMDOS trace is kept as evidence — it is where the load order in notes/loader.md comes from —
# but it is buffered, so nothing in this run waits on it.
TRACE_ARGUMENTS = ("--trace", "os_base")
TRACE_NAME = "os_%s.trace"

# --- the timeline --------------------------------------------------------------------------------
# Hatari's per-VBL wait multiplier (1-30): it stretches the whole timeline so the title, which is on
# screen for only a few emulated seconds before the front end moves on, can be photographed. 4 was
# the first value tried and it works; at 1 the same capture loop missed the title twice running.
SLOWDOWN = 4
# Captures are taken back to back — each one stops emulation for as long as it takes, and at this
# slowdown that costs a fraction of the window rather than the whole of it.
TITLE_POLL_SECONDS = 0.0
# TOS's boot plus eight files off an emulated drive, times SLOWDOWN, with slack for a host that is
# also running another emulator (measured: a concurrent Hatari stretched 30 s into 155 s).
TITLE_DEADLINE_SECONDS = 420.0
# The wall-clock gap between the title and each attract capture. Long enough at this slowdown to
# cross into another phase of the cycle, and far more than enough for the level behind it to have
# scrolled — which is what makes three different pictures evidence that the game loop is alive.
ATTRACT_SECONDS = 60.0
TITLE_SHOT = "title.png"
ATTRACT_SHOTS = ("attract_1.png", "attract_2.png")
LOG_NAME = "boot_%s.log"
ST_RAM_BYTES = 0x100000
RAM_DUMP_NAME = "ram.bin"
# Where the payload's TEXT has to land for its own screen ring to clear its BSS. See the banner.
MAX_TEXT_BASE = 0xD922

# --- reading a capture ---------------------------------------------------------------------------
# The ST's colour word is three bits per channel; Hatari expands each to eight its own way and this
# workspace's `st_pixels` expands it another, so a capture is compared to a palette by folding both
# back to the three bits they agree on.
ST_CHANNEL_MAX = 7
EIGHT_BIT_MAX = 255
ST_CHANNEL_SHIFTS = (8, 4, 0)       # where red, green and blue sit in a $0RGB colour word


def resolve_tos(rom_path, shortcut):
    rom = Path(rom_path).resolve() if rom_path else TOS_SHORTCUTS[shortcut]
    if not rom.is_file():
        raise SystemExit(f"missing TOS ROM {rom}")
    return rom


def hatari_arguments(rom, memsize_mb, trace_path=None):
    """The whole Hatari command line except `--cmd-fifo`, which the session appends."""
    trace = list(TRACE_ARGUMENTS) + ["--trace-file", str(trace_path)] if trace_path else []
    return [HATARI, "--tos", str(rom), "--machine", "st", "--memsize", str(memsize_mb),
            "--monitor", "rgb", "--confirm-quit", "off", "--statusbar", "off",
            "--drive-led", "off", "--frameskips", "0", "--sound", "off",
            "--run-vbls", str(RUN_VBLS), "--slowdown", str(SLOWDOWN),
            "--harddrive", str(GEMDOS_DIR)] + trace


def report_capture(path):
    colours = distinct_colours(path)
    print(f"  {path.name}: {colours} distinct colours  ({path})")
    return colours


def st_colours(png_path):
    """A capture's colours, folded back to the ST's three bits per channel."""
    from PIL import Image
    with Image.open(png_path) as image:
        colours = image.convert("RGB").getcolors(maxcolors=1 << 24)
    return {tuple(round(channel * ST_CHANNEL_MAX / EIGHT_BIT_MAX) for channel in colour)
            for _count, colour in colours}


def palette_colours(words):
    """The same three-bit form, for a list of $0RGB colour words."""
    return {tuple((word >> shift) & ST_CHANNEL_MAX for shift in ST_CHANNEL_SHIFTS) for word in words}


def wait_for_title(session, path, wanted):
    """Photograph until the whole title palette is on screen at once; answer the capture and its score.

    Answers the LAST capture either way, so a run that never drew the title still leaves the picture
    it did have for a reader to look at.
    """
    deadline = time.monotonic() + TITLE_DEADLINE_SECONDS
    matched = 0
    while time.monotonic() < deadline:
        session.require_alive("waiting for the title screen")
        matched = len(wanted & st_colours(session.screenshot(path)))
        if matched == len(wanted):
            break
        session.wait(TITLE_POLL_SECONDS)
    return path, matched


def run(rom, memsize_mb, out_dir):
    tag = tos_label(require_gemdos_tos(rom)).replace(".", "")
    out_dir.mkdir(parents=True, exist_ok=True)
    log = out_dir / (LOG_NAME % tag)
    trace = out_dir / (TRACE_NAME % tag)
    trace.unlink(missing_ok=True)
    session = HeadlessSession(hatari_arguments(rom, memsize_mb, trace), log_path=log,
                              fifo_path=out_dir / "hatari.fifo", work_dir=out_dir / "work")
    wanted = palette_colours(title_palette(TITLE_NEO.read_bytes()))
    try:
        title, matched = wait_for_title(session, out_dir / TITLE_SHOT, wanted)
        drawn_at = time.monotonic() - session.started
        base = locate_by_signature(session.savebin(RAM_DUMP_NAME, 0, ST_RAM_BYTES), GAME_PRG)
        attract = []
        for name in ATTRACT_SHOTS:
            session.wait(ATTRACT_SECONDS)
            attract.append(session.screenshot(out_dir / name))
    finally:
        status = session.close()
    strip_log_noise(log)

    print(f"TOS {tag}, {memsize_mb} MB, {GEMDOS_DIR} as C: — no --auto: TOS runs "
          f"{AUTO_SUBDIR}\\{DEPACKED_GAME} itself, before the desktop")
    print(f"  GEMDOS trace (load order, buffered — read after the run): {trace}")
    print(f"  {title.name}: {matched}/{len(wanted)} of the {NEO_NAME} palette on screen, "
          f"{distinct_colours(title)} distinct colours, {drawn_at:.0f} s after power-on  ({title})")
    print(f"  payload TEXT in RAM at {base:#x}, ceiling {MAX_TEXT_BASE:#x}"
          if base else "  payload TEXT was NOT in RAM by then")
    for shot in attract:
        report_capture(shot)
    moved = [not same_picture(first, second)
             for first, second in ((title, attract[0]), (title, attract[1]), (attract[0], attract[1]))]
    print(f"  title/attract_1, title/attract_2, attract_1/attract_2 differ: {moved}")
    faults = log_faults(log)
    print(f"  Hatari exit status {status}; log {log}")
    print("  fault lines: " + (", ".join(faults) if faults else "none"))

    if faults:
        raise SystemExit(f"the run faulted: {faults}")
    if status != 0:
        raise SystemExit(f"Hatari exited {status} — the run did not finish cleanly")
    if matched != len(wanted):
        raise SystemExit(f"the title screen never appeared: {matched}/{len(wanted)} of its palette was ever "
                         f"on screen at once, in a capture holding {distinct_colours(title)} colours")
    if base is None or base > MAX_TEXT_BASE:
        raise SystemExit(f"the payload loaded at {base if base is None else hex(base)}, above the {MAX_TEXT_BASE:#x} "
                         f"its own screen ring leaves it — it would be overwritten mid-run")
    if not all(moved):
        raise SystemExit(f"the attract cycle did not run: title/attract_1, title/attract_2, "
                         f"attract_1/attract_2 differ = {moved} — the front end is frozen or never appeared")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tos", choices=tuple(TOS_SHORTCUTS), default=DEFAULT_TOS)
    parser.add_argument("--tos-rom", help="boot this TOS image instead of a shortcut")
    parser.add_argument("--memsize", type=int, default=DEFAULT_MEMSIZE_MB, help="emulated RAM in MB")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--print-command", action="store_true", help="print the argv and exit")
    options = parser.parse_args()

    rom = resolve_tos(options.tos_rom, options.tos)
    if options.print_command:
        tag = tos_label(tos_version(rom)).replace(".", "")
        print("\n".join(hatari_arguments(rom, options.memsize, options.out / (TRACE_NAME % tag))))
        return
    if not GAME_PRG.is_file():
        raise SystemExit(f"{GEMDOS_DIR} is not laid out — run tools/unpack_dist.py first")
    run(rom, options.memsize, options.out)


if __name__ == "__main__":
    main()
