#!/usr/bin/env python3
"""Headless verification of JOUST.PRG under Hatari with a real TOS ROM.

    bash atari/build.sh title  && python3 atari/smoke.py title    # M1
    bash atari/build.sh smoke  && python3 atari/smoke.py frames   # M2

Both SMOKE builds run the reconstruction, dump what they drew, hand the machine back and `Pterm`.
Hatari is then left running for the rest of `--run-vbls` — deliberately, because an incomplete
hand-back does not show up while the program is alive: it shows up a second later as TOS calling a
vector that now points into freed memory. Killing the emulator the moment the dump appears hides
exactly the class of bug this build already had once (see README, "The bugs found on target").

What each mode asserts is in the four `check_*` docstrings below. The rule they share: assert on
what the GAME did, not on what a screenshot could plausibly look like. Hence `STATS.BIN` — counters
the shim keeps at the seams the cores call — alongside the framebuffers.
"""
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC = HERE.parent
sys.path.insert(0, str(REC.parents[2] / "tools"))     # reverse/tools — the shared recreate kit
from recreate_kit import project                       # noqa: E402
project.load(REC)
import tos_probe                                       # noqa: E402

DISK = HERE / "disk"
DRIVE_FILES = ("JOUST.PRG", "JOUST.IMG", "HIGH.SCO")

SCREEN_BASE = 0x8000        # os.h OS_SCREEN_BASE — the modelled Physbase, and screen_base on target
SCREEN_BYTES = 0x7d00       # init.h SCREEN_BYTES: one whole 320x200 4-plane framebuffer
SCREEN_ROW_BYTES = 0xa0     # joust.h
SCREEN_ROWS = SCREEN_BYTES // SCREEN_ROW_BYTES
PICTURE_OFF = 0x23aae       # init.h A_load_buffer — the title picture inside the program's data
IMAGE_LOAD_BASE = 0x10000   # addrs.h

# The scanlines title_screen's three draw_string calls touch, and the ONLY ones that may differ from
# the staged picture. Four disjoint bands from three calls: the credits string (STR_TITLE_CREDITS)
# is two lines, its own text plus the copyright line. Deterministic — identical on EmuTOS and TOS
# 1.04 and across runs — so it is pinned rather than merely counted: 45 scanlines of garbage, or two
# of the three strings drawing nothing at all, both pass a test that only asks "did anything change".
TITLE_TEXT_ROWS = ((121, 127), (138, 144), (155, 161), (165, 172))

# What init_video paints and what the frames build must therefore show: the white score bar, three
# rows of two four-cell blocks at row 171 (init.c HUD_BAR_OFF/HUD_BAR_PLANES01/HUD_BAR_PLANES23).
# Plane 0 is clear and planes 1-3 solid, so the bar's first cell is exactly these eight bytes.
HUD_BAR_OFF = 0x6ae0
HUD_BAR_CELL = bytes.fromhex("0000ffffffffffff")

# Floors for "this is a scene, not a blank screen". Both sit well below what a real frame produces
# (measured at 240 frames: 1651 lit playfield bytes, 181 distinct values) and well above what a
# HUD-only or single-colour frame could reach.
MIN_PLAYFIELD_BYTES = 500
MIN_DISTINCT_BYTES = 32

# STATS.BIN — nine big-endian longwords, written by joust_main.c's dump_stats() in this order.
STATS_FIELDS = ("frames", "console_polls", "dosound", "dosound_in_play", "first_sound_frame",
                "psg_writes", "psg_writes_in_play", "two_player_mode", "players_alive")
SMOKE_FRAMES = 240          # build.sh's SMOKE_FRAMES_DEFAULT; the run must reach exactly this
MIN_PSG_WRITES = 1000       # snd_tone_sweep alone issues ~14.4k

RUN_VBLS = "20000"          # ~11 s wall: TOS boot, the run, and a long tail after the program exits
RUN_TIMEOUT = 180

# TOS's ROM probes its own hardware at boot and bus-errors doing it; those are expected and are the
# only ones allowed. Anything faulting from RAM is ours.
ROM_PC = re.compile(r"PC=\$(fc|e0)")


def find_rom():
    rom = os.environ.get("JOUST_TOS_ROM") or tos_probe.find_tos_rom()
    if rom:
        return rom
    local = sorted((REC.parents[2] / "tools" / "hatari").glob("TOS*.img"))
    return str(local[-1]) if local else None


def run(trace=None):
    """Boot disk/JOUST.PRG headless, let Hatari run to the end of --run-vbls, and return everything
    it left behind: {filename: bytes}, the beacon names, Hatari's own output and its exit status."""
    hatari = tos_probe.find_hatari()
    rom = find_rom()
    if not (hatari and rom):
        raise RuntimeError("Hatari or a TOS ROM is not available (brew install hatari)")
    with tempfile.TemporaryDirectory() as tmp:
        drive = Path(tmp)
        for name in DRIVE_FILES:
            (drive / name).write_bytes((DISK / name).read_bytes())
        env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
        args = [hatari, "--sound", "off", "--fast-forward", "on", "--confirm-quit", "off",
                "--memsize", "4", "--monitor", "rgb", "--tos-res", "low", "--tos", rom,
                "--run-vbls", RUN_VBLS, "--harddrive", str(drive), "--auto", "C:\\JOUST.PRG"]
        if trace:
            args += ["--trace", trace, "--trace-file", str(drive / "TRACE.TXT")]
        proc = subprocess.run(args, env=env, capture_output=True, text=True, timeout=RUN_TIMEOUT)
        produced = {p.name: p.read_bytes() for p in drive.iterdir() if p.name not in DRIVE_FILES}
        markers = sorted(name for name in produced if re.fullmatch(r"B\d", name))
        log = produced.pop("TRACE.TXT", b"").decode(errors="replace")
        return produced, markers, log, proc


def check_exit(proc):
    """Hatari must have reached the end of --run-vbls by itself and reported a healthy machine.

    This is the assertion that witnesses the SHUTDOWN, not the run: the program Pterms well before
    --run-vbls expires, so everything after that is TOS on its own with whatever we left hooked. An
    unrestored KBDVBASE joystick vector shows up here and nowhere else — measured, as
    `Address Error reading at address $e69, PC=$12800` followed by
    `Detected double bus/address error => CPU halted!`, exit status 1."""
    faults = [line for line in proc.stdout.splitlines()
              if ("Bus Error" in line or "Address Error" in line) and not ROM_PC.search(line)]
    halted = [line for line in proc.stdout.splitlines() if "halted" in line.lower()]
    if proc.returncode == 0 and not faults and not halted:
        print("clean exit: Hatari ran to the end of --run-vbls, no fault outside the TOS ROM")
        return True
    print(f"FAIL: unhealthy machine after the program exited (hatari status {proc.returncode})")
    for line in faults + halted:
        print("  " + line.strip())
    return False


def check_title(fb):
    """The framebuffer must BE the staged picture, with the title text drawn over TITLE_TEXT_ROWS
    and nowhere else — the exact set, so a wrong picture, a missing draw_string or a scribble
    outside the text bands all fail."""
    picture = (DISK / "JOUST.IMG").read_bytes()[PICTURE_OFF - IMAGE_LOAD_BASE:][:SCREEN_BYTES]
    if len(picture) != SCREEN_BYTES:
        raise RuntimeError("JOUST.IMG is too short to hold the title picture")

    dirty = [row for row in range(SCREEN_ROWS)
             if fb[row * SCREEN_ROW_BYTES:(row + 1) * SCREEN_ROW_BYTES]
             != picture[row * SCREEN_ROW_BYTES:(row + 1) * SCREEN_ROW_BYTES]]
    expected = [row for lo, hi in TITLE_TEXT_ROWS for row in range(lo, hi + 1)]
    same = sum(1 for a, b in zip(fb, picture) if a == b)
    print(f"title framebuffer vs staged picture: {same}/{SCREEN_BYTES} bytes identical, "
          f"{len(dirty)}/{SCREEN_ROWS} scanlines differ")
    if dirty == expected:
        print(f"MATCH: the differing scanlines are exactly the {len(TITLE_TEXT_ROWS)} text bands "
              f"{TITLE_TEXT_ROWS}; every other scanline is byte-identical to the picture")
        return True
    print(f"FAIL: differing scanlines are {dirty}, expected {expected}")
    return False


def check_frames(early, final):
    """A rendered scene that is also a MOVING one. The two framebuffers are different frames of the
    same game (build.sh's SMOKE_EARLY_FRAME and SMOKE_FRAMES), so a build that painted frame 1 and
    then stopped — which passes every static check, measured — fails here."""
    ok = True
    bar = final[HUD_BAR_OFF:HUD_BAR_OFF + len(HUD_BAR_CELL)]
    print(f"score bar @ {HUD_BAR_OFF:#x}: {bar.hex()}")
    if bar != HUD_BAR_CELL:
        print("FAIL: init_video's score bar is not on the framebuffer")
        ok = False

    playfield = final[:HUD_BAR_OFF]
    lit = sum(1 for b in playfield if b)
    distinct = len(set(final))
    moved = sum(1 for a, b in zip(early, final) if a != b)
    print(f"final frame: {lit}/{len(playfield)} lit bytes above the bar, {distinct} distinct values; "
          f"{moved} bytes moved between the early frame and it")
    # The platforms, the ground and the riders all live above the bar; a run that drew only the HUD
    # would pass a whole-screen count but not this one.
    if lit < MIN_PLAYFIELD_BYTES or distinct < MIN_DISTINCT_BYTES:
        print("FAIL: framebuffer looks blank or degenerate")
        ok = False
    if not moved:
        print("FAIL: the two frames are identical — the game rendered once and stopped")
        ok = False
    return ok


def check_stats(stats):
    """What the game DID, read off the shim's own seams — the half of M2 no framebuffer can show.

    `two_player_mode`/`players_alive` are read out of the image at the dump and are what proves the
    scripted '1' drove title_screen's ONE-player arm specifically: nothing about one-vs-two players
    is legible in a framebuffer, so without these the '1' path is assumed rather than checked.

    `dosound_in_play` is the GAMEPLAY sound witness. It counts play_sound's command lists reaching
    the real XBIOS trap after the frame loop started — not the title screen's silence list, and not
    init_video's snd_tone_sweep, both of which fire before any frame and would let a completely
    broken play_sound pass. (`psg_writes_in_play` is 0 by construction and is reported, not asserted:
    during play the only Giaccess call is snd_poll_done's READ of register 7.)"""
    print("stats: " + ", ".join(f"{name}={stats[name]}" for name in STATS_FIELDS))
    ok = True
    for name, want in (("frames", SMOKE_FRAMES), ("two_player_mode", 0), ("players_alive", 1)):
        if stats[name] != want:
            print(f"FAIL: {name} is {stats[name]}, expected {want}")
            ok = False
    if stats["dosound_in_play"] < 1:
        print("FAIL: no play_sound reached XBIOS Dosound during the frame loop")
        ok = False
    return ok


def check_sound(log):
    """...and where those requests LANDED. Hatari's `xbios` trace names Dosound but not Giaccess, so
    snd_tone_sweep is counted through the `ym write data` lines instead — TOS writing the YM2149 on
    the game's behalf. This corroborates check_stats; the gameplay claim is made there."""
    calls = Counter(re.findall(r"XBIOS 0x[0-9a-f]+ (\w+)", log))
    writes = sum(1 for line in log.splitlines() if line.startswith("ym write data"))
    print("XBIOS traps: " + ", ".join(f"{name} x{n}" for name, n in sorted(calls.items())))
    print(f"YM2149 register writes: {writes}")
    if writes < MIN_PSG_WRITES:
        print("FAIL: the game's sound did not reach the chip")
        return False
    return True


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "title"
    trace = "xbios,psg_write" if mode == "frames" else None
    produced, markers, log, proc = run(trace=trace)
    print(f"beacons reached: {' '.join(markers) or 'none'}")

    missing = [name for name in (("SCREEN.BIN",) if mode == "title"
                                 else ("SCREEN.BIN", "SCREEN0.BIN", "STATS.BIN"))
               if name not in produced]
    if missing:
        raise RuntimeError(f"JOUST.PRG did not produce {missing} — it hung or crashed before the dump")

    ok = check_exit(proc)
    if mode == "title":
        ok &= check_title(produced["SCREEN.BIN"])
    else:
        stats = dict(zip(STATS_FIELDS, struct.unpack(f">{len(STATS_FIELDS)}I", produced["STATS.BIN"])))
        ok &= check_frames(produced["SCREEN0.BIN"], produced["SCREEN.BIN"])
        ok &= check_stats(stats)
        ok &= check_sound(log)

    outdir = REC.parent / "out"
    outdir.mkdir(parents=True, exist_ok=True)
    dump = outdir / f"screen_{mode}.bin"
    dump.write_bytes(produced["SCREEN.BIN"])
    print(f"wrote {dump}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
