#!/usr/bin/env python3
"""Boot Bubble Ghost in headless Hatari and check that the disk protection is satisfied.

    python3 projects/bubbleghost/tools/boot_ghost.py            # the Pasti dump in A:, TOS 1.04
    python3 projects/bubbleghost/tools/boot_ghost.py --settle 20
    python3 projects/bubbleghost/tools/boot_ghost.py --tos 102   # refused, and says why

The disk has no AUTO folder and no autostart line in its French DESKTOP.INF, so the real machine
needs a double-click. Headless, GHOST.PRG is started from a GEMDOS drive C: instead — which costs
nothing, because the protection reads drive A: by device number (XBIOS Floprd, dev 0) no matter
where the program itself came from. The Pasti image therefore stays mounted in A: with its fuzzy
bits intact. That is also why `--tos 102` is refused before Hatari starts: Hatari will not emulate a
GEMDOS drive below TOS 1.04, so on that ROM the program would simply never be run.

THE SUCCESS GATE IS THE DECRYPTED IMAGE, NOT THE PICTURE.  GHOST.PRG's wrapper turns the CRC of
track 79 into the key of a stream cipher over the whole program (notes/loader.md), so a failed
check does not branch anywhere interesting — it produces rubbish, or the Pterm0 that drops straight
back to the desktop. This run passes only if the WHOLE TEXT that tools/depack_bubbleghost.py
produces statically is in the emulated machine's RAM, byte for byte apart from the nine longwords
GEMDOS relocates. That simultaneously answers "does the protection pass under Hatari" and "is the
static decrypter right" — and it is the whole TEXT rather than a window because the prefetch bug in
notes/loader.md is exactly a "first 0x236 bytes right, the rest wrong" failure, which any window
short of the program passes.

The other surfaces are judged too: Hatari's log, its exit status, and the capture's colour count.
Every one of them used to be printed and ignored (docs/on-target-execution.md, "The observable
surfaces").
"""
import argparse
import struct
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[1]
sys.path.insert(0, str(REPO / "tools"))

from hatari_headless import (  # noqa: E402  (needs the path above)
    FIXUP_BYTES, HATARI, PRG_HEADER_BYTES, PRG_HEADER_FORMAT, HeadlessSession, distinct_colours,
    fixup_offsets, locate_by_signature, log_faults, require_gemdos_tos)

STX_IMAGE = REPO / "gw" / "dumps" / "bubble_ghost" / "bubble_ghost.stx"
GEMDOS_DIR = PROJECT / "bin"
GEMDOS_AUTO = r"C:\GHOST.PRG"
PLAIN_PRG = PROJECT / "bin" / "GHOST_PLAIN.PRG"
OUT_DIR = PROJECT / "out"

TOS_DIR = REPO / "tools" / "hatari"
TOS_SHORTCUTS = {"104": TOS_DIR / "TOS104US.img", "102": TOS_DIR / "TOS102US.img"}
DEFAULT_TOS = "104"

MEMSIZE_MB = 1
RUN_VBLS = 12000                      # 50 Hz => 240 s; Hatari quits by itself if the run hangs
ST_RAM_BYTES = 0x100000
RAM_DUMP_NAME = "ram.bin"

# The decrypt is POLLED FOR, not waited out: it lands 7.9 s after power-on on this host (measured),
# and a fixed pre-roll long enough to be safe everywhere is a fixed pre-roll wasted everywhere.
LOAD_POLL_SECONDS = 1.0
LOAD_DEADLINE_SECONDS = 90.0
# ...and then the capture has its own schedule, because the decrypt is not what the picture is for.
# The game shows its presentation screen and speaks over it first: at decrypt + 16 s the shutter
# still caught the title (measured), and the menu is up by decrypt + 24 s.
DEFAULT_SETTLE_SECONDS = 24.0

BLANK_COLOUR_COUNT = 1                # a capture with one colour is a photograph of nothing
MISMATCHES_SHOWN = 8                  # enough to see WHERE a bad decrypt goes wrong, in one line


def hatari_command(tos_rom):
    """The whole Hatari command line except `--cmd-fifo`, which the session appends.

    `--confirm-quit off` is not cosmetic: with the confirmation on, `hatari-shortcut quit` raises a
    modal nobody can answer headless, and every run ended in a kill (status -9) 40 s after the work
    was done. The status bar and the drive LED are off because they are composited INTO the
    screenshot, where they add colours to the picture the gate counts.
    """
    return [HATARI, "--log-level", "info", "--sound", "off",
            "--tos", str(tos_rom), "--machine", "st", "--memsize", str(MEMSIZE_MB),
            "--monitor", "rgb", "--tos-res", "low", "--run-vbls", str(RUN_VBLS),
            "--confirm-quit", "off", "--statusbar", "off", "--drive-led", "off",
            "--disk-a", str(STX_IMAGE), "--protect-floppy", "on",
            "--harddrive", str(GEMDOS_DIR), "--auto", GEMDOS_AUTO]


def require_inputs(tos_rom):
    """Fail before Hatari starts if anything this run reads is missing, or cannot do the job.

    A missing GHOST_PLAIN.PRG used to cost the whole boot and then die in a bare traceback while
    reading it, with the emulator's evidence already thrown away; a TOS the emulator will not mount
    a GEMDOS drive on used to cost one too, and then report "the program did nothing".
    """
    for what, path in (("TOS ROM", tos_rom), ("Pasti image", STX_IMAGE),
                       ("GEMDOS drive directory", GEMDOS_DIR),
                       ("statically decrypted image", PLAIN_PRG)):
        if not path.exists():
            raise SystemExit(f"missing {what} {path}")
    require_gemdos_tos(tos_rom)


def wait_for_plaintext(session):
    """Poll RAM until the decrypted TEXT is in it. (base, that dump) — (None, the last dump) on time-out.

    The dump the search HIT is the one the gate reads, so the comparison sees the program as the
    wrapper left it rather than after the game has had a while to write over its own TEXT.
    """
    deadline = time.monotonic() + LOAD_DEADLINE_SECONDS
    while True:
        ram = session.savebin(RAM_DUMP_NAME, 0, ST_RAM_BYTES)
        base = locate_by_signature(ram, PLAIN_PRG)
        if base is not None or time.monotonic() >= deadline:
            return base, ram
        session.wait(LOAD_POLL_SECONDS)


def text_mismatches(ram, base):
    """The TEXT offsets where the machine's copy differs from the static decrypt.

    The nine longwords GEMDOS relocates are skipped: it rewrote them in place as it loaded, so they
    are SUPPOSED to differ, and they are the only bytes that may.
    """
    image = PLAIN_PRG.read_bytes()
    text_length = struct.unpack_from(PRG_HEADER_FORMAT, image)[1]
    relocated = {offset + byte for offset in fixup_offsets(image) for byte in range(FIXUP_BYTES)}
    loaded = ram[base:base + text_length]
    return [at for at in range(text_length)
            if at not in relocated and loaded[at] != image[PRG_HEADER_BYTES + at]]


def judge(status, log_path, shot, base, ram):
    """Why this run is not evidence that the protection passed, or an empty list if it is."""
    problems = [f"Hatari logged: {line}" for line in log_faults(log_path)]
    if status != 0:
        problems.append(f"Hatari exited with status {status}")
    colours = distinct_colours(shot)
    if colours <= BLANK_COLOUR_COUNT:
        problems.append(f"{shot.name} holds {colours} colour — the screen was blank")
    if base is None:
        problems.append(f"the TEXT of {PLAIN_PRG.name} was never in RAM — the protection failed, the wrapper "
                        f"never ran, or the static decrypt is wrong")
        return problems
    differing = text_mismatches(ram, base)
    if differing:
        shown = ", ".join(f"{at:#x}" for at in differing[:MISMATCHES_SHOWN])
        problems.append(f"{len(differing)} TEXT bytes differ from {PLAIN_PRG.name} (at {shown}...) — the "
                        f"machine's program is not the one the static decrypter produces")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tos", choices=sorted(TOS_SHORTCUTS), default=DEFAULT_TOS)
    parser.add_argument("--settle", type=float, default=DEFAULT_SETTLE_SECONDS,
                        help="seconds to let the game run after the decrypt, before capturing")
    args = parser.parse_args()

    tos_rom = TOS_SHORTCUTS[args.tos]
    require_inputs(tos_rom)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUT_DIR / f"boot_tos{args.tos}.log"
    session = HeadlessSession(hatari_command(tos_rom), log_path=log_path,
                              fifo_path=OUT_DIR / "hatari.fifo", work_dir=OUT_DIR / "work")
    try:
        base, ram = wait_for_plaintext(session)
        decrypted_at = time.monotonic() - session.started
        session.wait(args.settle)
        session.require_alive("running GHOST.PRG")
        shot = session.screenshot(OUT_DIR / "boot_title.png")
    finally:
        status = session.close()

    problems = judge(status, log_path, shot, base, ram)
    where = "not in RAM" if base is None else f"at ${base:x}"
    print(f"decrypted TEXT {where} {decrypted_at:.1f}s after power-on; capture {shot} "
          f"({distinct_colours(shot)} distinct colours); hatari exit status {status}")
    for problem in problems:
        print(f"   FAIL: {problem}")
    if problems:
        return 1
    print(f"PROTECTION PASSED: the whole TEXT of {PLAIN_PRG.name} is in the machine's RAM")
    return 0


if __name__ == "__main__":
    sys.exit(main())
