#!/usr/bin/env python3
"""Headless verification of JOUST.PRG under Hatari with a real TOS ROM.

    bash atari/build.sh title     && python3 atari/smoke.py title      # M1  the title screen
    bash atari/build.sh smoke     && python3 atari/smoke.py frames     # M2  gameplay
    bash atari/build.sh quit      && python3 atari/smoke.py quit       # M3  Ctrl-C during play
    bash atari/build.sh quittitle && python3 atari/smoke.py quittitle  #     ...on the title screen
    bash atari/build.sh restart   && python3 atari/smoke.py restart    #     R, then Ctrl-C
    bash atari/build.sh title && bash atari/build.sh quit
    python3 atari/smoke.py hiscore                                     # M3  HIGH.SCO round trip
    python3 atari/smoke.py original                                    # M3  vs the shipped binary
    bash atari/build.sh framediff && python3 atari/smoke.py framediff  # M4  ...frame by frame

Each check boots the build made for it (build/JOUST-<mode>.PRG) and refuses one older than the
sources, so a half-done build pair or a mode/build mismatch is named as such instead of surfacing
as a behavioural red.

Every SMOKE build runs the reconstruction, dumps what it drew, hands the machine back and `Pterm`s.
Hatari is then left running for the rest of `--run-vbls` — deliberately, because an incomplete
hand-back does not show up while the program is alive: it shows up a second later as TOS calling a
vector that now points into freed memory. Killing the emulator the moment the dump appears hides
exactly the class of bug this build already had once (see README, "The bugs found on target").

What each mode asserts is in the `check_*` docstrings below. The rule they share: assert on what the
GAME did, not on what a screenshot could plausibly look like. Hence `STATS.BIN` — counters the shim
keeps at the seams the cores call — alongside the framebuffers.
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
import prg_dis                                         # noqa: E402  (tools/, for the reloc table)

DISK = HERE / "disk"
BUILD = HERE / "build"
INPUTS_ONLY = {"JOUST.PRG", "JOUST.IMG", "CMD.INI", "ACT.INI"}   # staged, never written back

# Which build.sh mode each check needs. Every check boots build/JOUST-<mode>.PRG rather than
# whatever build.sh last copied to disk/, because the key script is compiled INTO the binary: run
# `smoke.py restart` against the quit build and the run quits cleanly during play, which reads as
# "the longjmp restart is broken" instead of "you booted the wrong PRG".
MODE_BUILD = {"title": "title", "frames": "smoke", "quit": "quit",
              "quittitle": "quittitle", "restart": "restart", "framediff": "framediff",
              "framediff-fault": "framediff-fault", "framediff-skew": "framediff-skew"}


def prg_for(mode):
    return BUILD / f"JOUST-{MODE_BUILD[mode]}.PRG"
ORIGINAL_PRG = REC.parent / "bin" / "JOUST.PRG"
SHIPPED_HISCORE = REC.parent / "bin" / "HIGH.SCO"

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
# Which of those bands is the HIGH SCORE line (STR_TITLE_HISCORE). It is the TOPMOST one, not the
# second: the bands are in screen order and the three strings are drawn in an order of their own,
# each carrying its own position. Established by the round trip below, which is the only thing that
# can say it — change the record, see which band moves.
HISCORE_BAND = 0

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

# STATS.BIN — twenty big-endian longwords, written by joust_main.c's dump_stats() in this order.
STATS_FIELDS = ("frames", "console_polls", "dosound", "dosound_in_play", "first_sound_frame",
                "psg_writes", "psg_writes_in_play", "ikbd_packets", "restarts",
                "hiscore_bytes_written", "frame_bytes_written", "screen_passed", "screen_physbase",
                "text_probe", "poll_quit_key_pc", "two_player_mode", "players_alive",
                "player_x", "player_y", "rng_ptr")
SMOKE_FRAMES = 240          # build.sh's SMOKE_FRAMES_DEFAULT; the frames run must reach exactly this
MIN_PSG_WRITES = 1000       # snd_tone_sweep alone issues ~14.4k
# joy_handler files one per reply and the chain keeps them coming, so a run of any length sees
# hundreds. The floor only has to exclude "none at all", which is what a broken interrogate or an
# uninstalled joyvec would give — and it is stated PER MODE because the runs differ by two orders of
# magnitude: `quittitle` Pterms at the eighth title-screen console poll, a few tens of ms in, where
# a machine-speed difference of a few ms really can move the count.
MIN_IKBD_PACKETS = 200
MIN_IKBD_PACKETS_SHORT = 10

# What the round trip writes over the record's NAME field. The record's LENGTH must not change:
# os_fwrite only ever grows the staged file's size, so a shorter record would come back out at the
# old length with the tail of the old one still on it.
HISCORE_TEST_NAME = b"JOUSTM3"
HISCORE_RECORD_BYTES = 0x1a      # src/input.c HISCORE_RECORD_BYTES — what save_hiscore writes

TOS_V_BAS_AD = 0x44e        # TOS system variable: the base of the screen it is displaying
MEMSIZE_MB = 4              # what Hatari is given, and therefore how much RAM there is to dump
RAM_BYTES = MEMSIZE_MB << 20

RUN_VBLS = "20000"          # ~11 s wall: TOS boot, the run, and a long tail after the program exits
SHORT_RUN_VBLS = "6000"     # ...for the modes that Pterm in the first few hundred: still ~100 s of
                            # emulated tail after the exit, which is what check_exit needs
RUN_TIMEOUT = 180
# Spare `c` lines fed to the debugger beyond the stops we schedule. Unread ones cost nothing; running
# out stops the emulation dead at a prompt, which is the failure worth over-providing against.
DEBUG_CONTINUE_SLACK = 8
# The frame the DISPLAY check photographs. It is deliberately one from the STATIC band (the screen
# does not change between about frame 2 and frame 110 with the sticks centred): `screenshot` renders
# the emulator's current display surface, which is built scanline by scanline, so a capture taken
# part-way down a frame mixes that frame with the one before. On a static screen that mix is the
# same picture however the raster happens to be placed, and the two sides reach their frame anchors
# at different raster positions. Photographing a MOVING frame is not wrong, it is unstable — it
# differed run to run before this was pinned.
SCREENSHOT_FRAME = 60

ORIGINAL_DUMP_VBL = 2500    # by then the ORIGINAL is sitting on its title screen
ORIGINAL_RUN_VBLS = "4000"
# Enough for the shipped binary to boot, sit through one attract pass and play out the deepest
# sample; it needs no tail, because the frame anchors dump long before it ends.
FRAMEDIFF_RUN_VBLS = "8000"

# ---- the frame differential's anchors in the SHIPPED binary ------------------------------------
# All are Ghidra addresses (../names.txt's base), turned into run-time addresses by adding the load
# base this run discovered. The shipped binary carries no symbol table, so each is derived rather
# than looked up, and each is verified by the run itself: if any is wrong the anchored dumps simply
# do not appear and the mode fails loudly.
GHIDRA_AFTER_INIT_GAME = 0x1000c   # _start's third `jsr` — init_game has returned, title_screen next
GHIDRA_TITLE_BCONSTAT = 0x10b96    # title_screen: `tst.b d0` on Bconstat's answer
GHIDRA_TITLE_BCONIN = 0x10be0      # ...and its `trap #13` for Bconin
GHIDRA_TITLE_BCONIN_SKIP = 0x10be2 # the `adda.w #4,sp` after it, where the injection resumes
GHIDRA_POLL_QUIT_KEY = 0x11c24     # the frame anchor: one entry per frame, and nothing else calls it
GHIDRA_RNG_PTR = 0x10dfe           # ../include/addrs.h A_rng_ptr

# poll_quit_key is a reconstructed core compiled into our binary, so its address there is an ELF
# symbol rather than a Ghidra address — read from the ELF, like our load base.

# A relocation-free window in the shipped .PRG, used to find where GEMDOS loaded it: the bytes there
# are the file's own, so the match is unique and its address gives the base directly. It sits at the
# END of the reloc-free run rather than the start, because the start is the dead floppy loader's
# variable block — six bytes and fifty-eight zeros, distinctive only by luck. [0x55c0,0x5600) is 30
# distinct byte values.
BASE_SIGNATURE_OFF = 0x55c0
BASE_SIGNATURE_LEN = 64
PRG_HEADER = 28             # GEMDOS .PRG header, ahead of the text the signature is taken from

# The ST shifter's sixteen colour registers. `savebin` reads I/O space, so the SHIPPED binary's pens
# can be read straight off the hardware at a frame anchor — which is the only way to compare colour
# at all, the palette being off-image on both sides.
IMAGE_ALIGN = 256           # joust_main.c IMAGE_ALIGN: the video base register's granularity
ST_PALETTE_REGS = 0xffff8240
PALETTE_PENS = 16
PALETTE_BYTES = PALETTE_PENS * 2

# TOS's ROM probes its own hardware at boot and bus-errors doing it; those are expected and are the
# only ones allowed. Anything faulting from RAM is ours.
ROM_PC = re.compile(r"PC=\$(fc|e0)")


def find_rom():
    rom = os.environ.get("JOUST_TOS_ROM") or tos_probe.find_tos_rom()
    if rom:
        return rom
    local = sorted((REC.parents[2] / "tools" / "hatari").glob("TOS*.img"))
    return str(local[-1]) if local else None


def run(prg, files, trace=None, parse=None, run_vbls=RUN_VBLS, debug_continues=0):
    """Boot `prg` headless on a drive holding `files`, let Hatari run to the end of --run-vbls, and
    return everything it left behind: {filename: bytes}, the beacon names, Hatari's own output and
    its exit status.

    A `files` entry may be `str` instead of `bytes`, and `parse` — an optional Hatari DEBUGGER
    script — always is; both get `{drive}` substituted with the temporary drive's HOST path. The
    debugger reads and writes host paths, not GEMDOS ones, which is why it needs the distinction."""
    hatari = tos_probe.find_hatari()
    rom = find_rom()
    if not (hatari and rom):
        raise RuntimeError("Hatari or a TOS ROM is not available (brew install hatari)")
    require_fresh(prg)
    with tempfile.TemporaryDirectory() as tmp:
        drive = Path(tmp)
        (drive / "JOUST.PRG").write_bytes(Path(prg).read_bytes())
        for name, data in files.items():
            (drive / name).write_bytes(data.format(drive=drive).encode()
                                       if isinstance(data, str) else data)
        env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
        args = [hatari, "--sound", "off", "--fast-forward", "on", "--confirm-quit", "off",
                # --statusbar off: it is emulator chrome, it differs with the ROM and the drive LED
                # state, and it is not part of the picture the game draws.
                "--statusbar", "off",
                "--memsize", str(MEMSIZE_MB), "--monitor", "rgb", "--tos-res", "low", "--tos", rom,
                "--run-vbls", run_vbls, "--harddrive", str(drive), "--auto", "C:\\JOUST.PRG"]
        if trace:
            args += ["--trace", trace, "--trace-file", str(drive / "TRACE.TXT")]
        if parse:
            (drive / "CMD.INI").write_text(parse.format(drive=drive))
            args += ["--parse", str(drive / "CMD.INI")]
        # Each breakpoint that runs an action file leaves the debugger at its prompt afterwards, and
        # a prompt with nothing to read stops the emulation dead — so a run with breakpoints is fed
        # a supply of `c`. One per expected stop plus slack; unread lines cost nothing.
        stdin_kw = ({"input": "c\n" * debug_continues} if debug_continues
                    else {"stdin": subprocess.DEVNULL})
        proc = subprocess.run(args, env=env, capture_output=True, text=True,
                              timeout=RUN_TIMEOUT, **stdin_kw)
        # HIGH.SCO is deliberately NOT excluded: it goes in as an input and comes back out as the
        # quit path's output, and reading it back is how the round trip is checked.
        produced = {p.name: p.read_bytes() for p in drive.iterdir() if p.name not in INPUTS_ONLY}
        markers = sorted(name for name in produced if re.fullmatch(r"B.", name))
        log = produced.pop("TRACE.TXT", b"").decode(errors="replace")
        return produced, markers, log, proc


def require_fresh(prg):
    """The PRG must exist AND be newer than everything it is built from.

    build.sh keeps a build/JOUST-<mode>.PRG per mode and `hiscore` boots two of them in sequence, so
    "it exists" is not enough: an interrupted `build.sh title && build.sh quit` leaves one of the
    pair from an older tree, and the run then reports a green (or an unpack error) for a combination
    that never existed."""
    prg = Path(prg)
    if not prg.exists():
        raise RuntimeError(f"{prg} is not built — see the header of this file for the build.sh line")
    if prg.parent != BUILD:
        return          # the shipped 1989 binary (mode `original`); nothing here builds it
    # build.sh is in the list because it is not merely how the PRG is built: the frame differential
    # reads its RNG_PARK and FRAME_SAMPLES and applies them to the SHIPPED binary, so a build.sh
    # edited after the PRG was made would pin the two sides differently.
    sources = [*HERE.glob("*.c"), *HERE.glob("*.s"), *HERE.glob("shim_include/*.h"),
               HERE / "build.sh", *REC.glob("src/*.c"), *REC.glob("include/*.h")]
    newer = [src for src in sources if src.stat().st_mtime > prg.stat().st_mtime]
    if newer:
        raise RuntimeError(f"{prg.name} is older than {newer[0].name} and {len(newer) - 1} other "
                           f"source(s) — rebuild it before trusting this run")


def drive_files(hiscore=None):
    return {"JOUST.IMG": (DISK / "JOUST.IMG").read_bytes(),
            "HIGH.SCO": hiscore if hiscore is not None else SHIPPED_HISCORE.read_bytes()}


def stats_of(produced):
    """Parse STATS.BIN. The length is checked first because the record has GROWN twice and fields
    were inserted mid-way, so a record from an older joust_main.c is not merely short — it is
    differently ordered, and struct's own error says nothing about why."""
    record = produced["STATS.BIN"]
    if len(record) != len(STATS_FIELDS) * 4:
        raise RuntimeError(f"STATS.BIN is {len(record)} bytes, expected {len(STATS_FIELDS) * 4} — "
                           f"it was written by an older joust_main.c; rebuild the PRG")
    return dict(zip(STATS_FIELDS, struct.unpack(f">{len(STATS_FIELDS)}I", record)))


def require(produced, *names):
    missing = [name for name in names if name not in produced]
    if missing:
        raise RuntimeError(f"JOUST.PRG did not produce {missing} — it hung or crashed before the dump")


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


def title_bands(framebuffer):
    """The staged picture, the rows the framebuffer differs from it on, and the four text bands."""
    picture = (DISK / "JOUST.IMG").read_bytes()[PICTURE_OFF - IMAGE_LOAD_BASE:][:SCREEN_BYTES]
    if len(picture) != SCREEN_BYTES:
        raise RuntimeError("JOUST.IMG is too short to hold the title picture")
    dirty = [row for row in range(SCREEN_ROWS)
             if framebuffer[row * SCREEN_ROW_BYTES:(row + 1) * SCREEN_ROW_BYTES]
             != picture[row * SCREEN_ROW_BYTES:(row + 1) * SCREEN_ROW_BYTES]]
    bands = [framebuffer[lo * SCREEN_ROW_BYTES:(hi + 1) * SCREEN_ROW_BYTES]
             for lo, hi in TITLE_TEXT_ROWS]
    return picture, dirty, bands


def check_title(framebuffer):
    """The framebuffer must BE the staged picture, with the title text drawn over TITLE_TEXT_ROWS
    and nowhere else — the exact set, so a wrong picture, a missing draw_string or a scribble
    outside the text bands all fail."""
    picture, dirty, _ = title_bands(framebuffer)
    expected = [row for lo, hi in TITLE_TEXT_ROWS for row in range(lo, hi + 1)]
    same = sum(1 for a, b in zip(framebuffer, picture) if a == b)
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


def check_screen_base(stats):
    """What we asked the shifter to display from, against what it says it IS displaying from.

    THIS IS THE ONE CHECK THAT SEES PAST MEMORY. On an STF the video base register has no low byte
    ($ffff8201/8203 only), so an address that is not 256-byte aligned is TRUNCATED and the picture is
    displaced — while the framebuffer bytes, the palette and every dump in this file stay identical.
    A displacement that is a multiple of 8 slides the image by whole 4-plane cells; one that is not
    PERMUTES the bitplanes, because ST low-res interleaves plane0..plane3 word by word: shapes
    intact, colours systematically remapped. That is a whole class of "it looks wrong" this project
    was blind to, and the read-back is two instructions."""
    passed, actual = stats["screen_passed"], stats["screen_physbase"]
    # ALIGNMENT is the invariant; hardware agreement is only how an STF SHOWS a breach of it. An STE
    # has $ffff820d and honours the low byte, so a misaligned base there displays exactly as asked
    # and the read-back agrees — the check has to assert the property, not just the symptom.
    aligned = passed % IMAGE_ALIGN == 0
    if aligned and passed == actual:
        print(f"video base {passed:#010x} ({IMAGE_ALIGN}-aligned; the hardware confirms it)")
        return True
    if not aligned:
        print(f"FAIL: the video base {passed:#010x} is not {IMAGE_ALIGN}-aligned (low byte "
              f"{passed % IMAGE_ALIGN:#04x}) — an STF cannot display from it")
    if passed != actual:
        lost = passed - actual
        how = "TRUNCATED" if actual == passed & ~(IMAGE_ALIGN - 1) else "IGNORED"
        print(f"FAIL: asked the shifter for {passed:#010x}, it displays from {actual:#010x} "
              f"({how}) — {lost} bytes, i.e. {lost // 8} whole cells and {lost % 8} bytes of "
              f"PLANE PERMUTATION")
    return False


def check_stats(stats, want, at_least=None):
    """What the game DID, read off the shim's own seams — the half no framebuffer can show.

    `two_player_mode`/`players_alive` are read out of the image at the dump and are what proves the
    scripted '1' drove title_screen's ONE-player arm specifically. `dosound_in_play` counts
    play_sound's command lists reaching the real XBIOS trap AFTER the frame loop started — not the
    title screen's silence list and not init_video's snd_tone_sweep, both of which fire before any
    frame and would let a completely broken play_sound pass. `ikbd_packets` is joy_handler's own
    tally: the IKBD really is answering the interrogates the shim chains, which is what every wait
    loop in the game blocks on. `restarts` is the R key's longjmp landing back in joust_main."""
    print("stats: " + ", ".join(f"{name}={stats[name]}" for name in STATS_FIELDS))
    ok = True
    for name, expected in want.items():
        if stats[name] != expected:
            print(f"FAIL: {name} is {stats[name]}, expected {expected}")
            ok = False
    # Counts that witness "this happened at all" are FLOORS, never equalities: the number of sounds
    # a 240-frame game asks for is not a property of the build, and `build.sh smoke <N>` is a
    # documented knob that changes it.
    for name, floor in (at_least or {}).items():
        if stats[name] < floor:
            print(f"FAIL: {name} is {stats[name]}, expected at least {floor}")
            ok = False
    return ok & check_screen_base(stats)


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


def modified_hiscore():
    """The shipped record with a distinctive name written into it — so the round trip below proves
    CHANGED bytes travelled, rather than that a file was copied over itself."""
    record = bytearray(SHIPPED_HISCORE.read_bytes())
    record[:len(HISCORE_TEST_NAME)] = HISCORE_TEST_NAME
    return bytes(record)


# ---- the modes ---------------------------------------------------------------------------------

def mode_title():
    produced, markers, _, proc = run(prg_for("title"), drive_files(), run_vbls=SHORT_RUN_VBLS)
    print(f"beacons reached: {' '.join(markers) or 'none'}")
    ok = check_exit(proc)
    require(produced, "SCREEN.BIN", "STATS.BIN")
    # The title mode's whole job is "the picture is right", so it is the last place that should be
    # taking the video base on trust.
    ok &= check_screen_base(stats_of(produced))
    return ok & check_title(produced["SCREEN.BIN"]), produced["SCREEN.BIN"]


def mode_frames():
    produced, markers, log, proc = run(prg_for("frames"), drive_files(), trace="xbios,psg_write")
    print(f"beacons reached: {' '.join(markers) or 'none'}")
    ok = check_exit(proc)
    require(produced, "SCREEN.BIN", "SCREEN0.BIN", "STATS.BIN")
    ok &= check_frames(produced["SCREEN0.BIN"], produced["SCREEN.BIN"])
    ok &= check_stats(stats_of(produced),
                      {"frames": SMOKE_FRAMES, "two_player_mode": 0, "players_alive": 1},
                      at_least={"dosound_in_play": 1, "ikbd_packets": MIN_IKBD_PACKETS})
    ok &= check_sound(log)
    return ok, produced["SCREEN.BIN"]


def mode_exit(mode, want, at_least=None, run_vbls=RUN_VBLS):
    """The quit / quittitle / restart builds: the reconstruction's own never-returning exits, driven
    for real. What is asserted is the machine AFTERWARDS (check_exit — the whole point of the
    hand-back), the counters, and that HIGH.SCO came back out through real GEMDOS unchanged."""
    hiscore = SHIPPED_HISCORE.read_bytes()
    produced, markers, _, proc = run(prg_for(mode), drive_files(hiscore), run_vbls=run_vbls)
    print(f"beacons reached: {' '.join(markers) or 'none'}")
    # check_exit FIRST: if the scripted key never landed, the program is still hooked into TOS when
    # --run-vbls expires, and that is exactly the run whose hand-back most needs diagnosing — but
    # require() raises, so anything after it would never print.
    ok = check_exit(proc)
    require(produced, "STATS.BIN")
    stats = stats_of(produced)
    return ok & check_stats(stats, want, at_least) & check_hiscore(produced, stats, hiscore), \
        produced.get("SCREEN.BIN")


def check_hiscore(produced, stats, staged):
    """The quit path really put the record back, and put back the right bytes.

    BOTH halves are needed, and the counter is the load-bearing one: HIGH.SCO goes onto the drive as
    an INPUT, so a file with the expected contents is there whether or not the program ever wrote
    one — measured, the title build (which never reaches write_hiscore_file) passed a check that
    only compared contents. `hiscore_bytes_written` is the byte count real GEMDOS Fwrite returned
    inside the shim, so it is zero unless the write happened.

    What makes the write happen at all is init_system, not a beaten score: a successfully loaded
    HIGH.SCO is marked with HISCORE_LOADED_MARK, and save_hiscore gates on that byte — so every
    Ctrl-C rewrites the file. ../src/init.c records that as the original's behaviour, reproduced."""
    written = produced.get("HIGH.SCO")
    print(f"HIGH.SCO on the drive: {len(written or b'')} bytes, {written!r}; "
          f"bytes the quit path wrote through GEMDOS: {stats['hiscore_bytes_written']}")
    if stats["hiscore_bytes_written"] != HISCORE_RECORD_BYTES:
        print(f"FAIL: the game wrote {stats['hiscore_bytes_written']} bytes, "
              f"expected {HISCORE_RECORD_BYTES}")
        return False
    if written != staged:
        print(f"FAIL: the record changed across the round trip (staged {staged!r})")
        return False
    return True


def mode_hiscore():
    """HIGH.SCO round trip, end to end and in the game's own terms.

    Phase 1 boots the title build on the SHIPPED record and keeps the four text bands as a baseline.
    Phase 2 boots the quit build on a MODIFIED one — the game reads it into the image at
    init_system, quit_to_desktop writes it back into the staged file, and the shim copies that out
    through real GEMDOS. Phase 3 boots the title build on what phase 2 wrote: the HIGH SCORE band
    must have changed and the other three must be byte-identical, which is what says the new bytes
    reached the screen through the record and that nothing else moved with them."""
    title_prg, quit_prg = prg_for("title"), prg_for("quit")
    print("--- phase 1: the title screen on the shipped record (baseline)")
    produced, _, _, proc = run(title_prg, drive_files())
    require(produced, "SCREEN.BIN", "STATS.BIN")
    ok = check_exit(proc) & check_screen_base(stats_of(produced))
    _, _, baseline = title_bands(produced["SCREEN.BIN"])

    print("--- phase 2: play, then Ctrl-C, with a modified record staged")
    staged = modified_hiscore()
    produced, _, _, proc = run(quit_prg, drive_files(staged))
    require(produced, "STATS.BIN")
    ok &= check_exit(proc)
    if not check_hiscore(produced, stats_of(produced), staged):
        return False, None
    written = produced["HIGH.SCO"]
    print(f"HIGH.SCO round-tripped through the game and real GEMDOS: {written!r}")

    print("--- phase 3: the title screen on what the quit path wrote")
    produced, _, _, proc = run(title_prg, drive_files(written))
    require(produced, "SCREEN.BIN", "STATS.BIN")
    ok &= check_exit(proc) & check_screen_base(stats_of(produced)) & check_title(produced["SCREEN.BIN"])
    _, _, bands = title_bands(produced["SCREEN.BIN"])
    changed = [i for i, (a, b) in enumerate(zip(baseline, bands)) if a != b]
    print(f"title text bands that changed with the record: {changed}")
    if changed != [HISCORE_BAND]:
        print(f"FAIL: expected only band {HISCORE_BAND} (the HIGH SCORE line) to change")
        ok = False
    else:
        print("MATCH: the new record shows on the HIGH SCORE line, and only there")
    return ok, produced["SCREEN.BIN"]


def mode_original():
    """Side-by-side with the shipped binary: run the ORIGINAL JOUST.PRG to its title screen, dump
    the machine's whole RAM through Hatari's debugger, and look for OUR on-target title framebuffer
    inside it. A hit is the strongest form this comparison can take — the two bitmaps are equal byte
    for byte, drawn by different code on the same 68000 out of the same data.

    It compares BITPLANES, which is the right thing to compare: the palette is off-image on both
    sides (the reconstruction's Setpalette has no image effect at all — README §5), so colour is not
    part of this claim and stays a GUI check."""
    ours = REC.parent / "out" / "screen_title.bin"
    if not ours.exists():
        raise RuntimeError(f"run `smoke.py title` first — {ours} is what this compares against")
    dump = "ORIGRAM.BIN"
    produced, _, _, proc = run(ORIGINAL_PRG,
                               {"HIGH.SCO": SHIPPED_HISCORE.read_bytes(),
                                "ACT.INI": "savebin {drive}/%s 0 %#x\ncont\n" % (dump, RAM_BYTES)},
                               parse=("b VBL > %d :once :file {drive}/ACT.INI\n"
                                      % ORIGINAL_DUMP_VBL),
                               run_vbls=ORIGINAL_RUN_VBLS)
    ram = produced.get(dump)
    if ram is None:
        raise RuntimeError("the debugger did not dump the original's RAM")
    ours_bytes = ours.read_bytes()
    at = ram.find(ours_bytes)
    v_bas_ad = int.from_bytes(ram[TOS_V_BAS_AD:TOS_V_BAS_AD + 4], "big")
    print(f"original RAM dumped at VBL {ORIGINAL_DUMP_VBL}: {len(ram)} bytes, "
          f"its _v_bas_ad = {v_bas_ad:#x}")
    if at >= 0:
        # WHERE the match is, not just that there is one: 32000 bytes could in principle turn up in
        # a scratch buffer or a stale copy, and only a hit at the machine's own screen base says the
        # ORIGINAL is displaying it.
        if at != v_bas_ad:
            print(f"FAIL: the match is at {at:#x}, which is not the original's screen ({v_bas_ad:#x})")
            return False, None
        print(f"MATCH: our on-target title framebuffer appears byte-identical in the ORIGINAL's "
              f"RAM at {at:#x} — its own _v_bas_ad, i.e. the screen it is displaying")
        return check_exit(proc), None
    theirs = ram[v_bas_ad:v_bas_ad + SCREEN_BYTES]
    rows = [r for r in range(SCREEN_ROWS)
            if ours_bytes[r * SCREEN_ROW_BYTES:(r + 1) * SCREEN_ROW_BYTES]
            != theirs[r * SCREEN_ROW_BYTES:(r + 1) * SCREEN_ROW_BYTES]]
    print(f"FAIL: no match. Their screen is at {v_bas_ad:#x}; {len(rows)} scanlines differ: {rows[:16]}")
    return False, None


# ---- the frame differential -------------------------------------------------------------------

def build_setting(name):
    """Read one shell assignment out of build.sh, so the pins have ONE definition.

    RNG_PARK and FRAME_SAMPLES are compiled into this build with -D and must be applied identically
    to the shipped binary from the debugger side; re-typing either here is exactly the across-a-
    language-boundary duplication that would make a green mean nothing."""
    text = (HERE / "build.sh").read_text()
    match = re.search(rf"^{name}=(\S+)", text, re.M)
    if not match:
        raise RuntimeError(f"build.sh no longer defines {name} — the frame differential's pins moved")
    return match.group(1)


def c_define(name):
    """One #define's value out of joust_main.c — the key byte the shipped side must be handed is the
    same one this build's shim watches for, and build.sh already passes it by NAME for that reason."""
    match = re.search(rf"^#define\s+{name}\s+(0x[0-9a-fA-F]+)", (HERE / "joust_main.c").read_text(),
                      re.M)
    if not match:
        raise RuntimeError(f"joust_main.c no longer defines {name}")
    return int(match.group(1), 16)


def original_ram_dump():
    """Boot the SHIPPED binary to its title screen and dump all of RAM through Hatari's debugger.

    Both the side-by-side and the frame differential start here — one needs the whole image to
    search, the other needs the load base and the screen address out of it."""
    produced, _, _, proc = run(ORIGINAL_PRG,
                               {"HIGH.SCO": SHIPPED_HISCORE.read_bytes(),
                                "ACT.INI": "savebin {drive}/ORIGRAM.BIN 0 %#x\ncont\n" % RAM_BYTES},
                               parse="b VBL > %d :once :file {drive}/ACT.INI\n" % ORIGINAL_DUMP_VBL,
                               run_vbls=ORIGINAL_RUN_VBLS)
    ram = produced.get("ORIGRAM.BIN")
    if ram is None:
        raise RuntimeError("the debugger did not dump the original's RAM")
    return ram, proc


def original_load_base(ram):
    """Where GEMDOS put the shipped binary in this run, from a relocation-free signature.

    It is NOT a constant: it depends on the ROM and on what TOS put below the TPA, so every anchor
    below is derived from it per run rather than written down (measured: 0x12596 under TOS 1.04)."""
    prg = ORIGINAL_PRG.read_bytes()
    signature = prg[PRG_HEADER + BASE_SIGNATURE_OFF:][:BASE_SIGNATURE_LEN]
    hits = ram.count(signature)
    if hits != 1:
        raise RuntimeError(f"the load-base signature appears {hits} times in RAM, expected exactly 1")
    return ram.find(signature) - BASE_SIGNATURE_OFF


def original_frame_script(script_dir, base, screen, samples, rng_park):
    """The debugger script that makes the shipped binary comparable, and the files it calls.

    Three pins and one anchor, all at run-time addresses derived from `base`:
      * the RNG cursor is parked where this build parks its own, so both walk identical bytes;
      * Bconstat is made to answer "a key is waiting" once;
      * the Bconin trap is SKIPPED and '1' put in D0 — skipped because Bconin BLOCKS: forcing
        Bconstat alone makes the game call it, and with no key in TOS's buffer it never returns
        (measured: the run stops there for ever);
      * poll_quit_key's entry is the frame counter. Hatari's `:<count>` breaks on every count-th hit
        and `:once` retires it, so one breakpoint per sample frame reads off that sample exactly. A
        count of 1 is rejected by Hatari, so frame 1 is a plain `:once`.
    """
    def runtime(ghidra):
        return base + ghidra - IMAGE_LOAD_BASE

    def action(name, *commands):
        """Write one breakpoint's action file. These are HOST paths the debugger reads, and they
        deliberately do not live on the emulated drive, where the game would see them."""
        (script_dir / name).write_text("".join(command + "\n" for command in commands))
        return f":file {script_dir / name}"

    lines = [
        f"b pc = ${runtime(GHIDRA_AFTER_INIT_GAME):x} :once :quiet "
        + action("RNG.INI", f"w l ${runtime(GHIDRA_RNG_PTR):x} ${runtime(rng_park):x}"),
        f"b pc = ${runtime(GHIDRA_TITLE_BCONSTAT):x} :once :quiet "
        + action("STAT.INI", "r d0=$ff"),
        f"b pc = ${runtime(GHIDRA_TITLE_BCONIN):x} :once :quiet "
        + action("KEY.INI", f"r d0=${c_define('KEY_ONE_PLAYER'):x}",
                 f"r pc=${runtime(GHIDRA_TITLE_BCONIN_SKIP):x}"),
    ]
    for index, frame in enumerate(samples, 1):
        count = "" if frame == 1 else f":{frame} "
        lines.append(f"b pc = ${runtime(GHIDRA_POLL_QUIT_KEY):x} {count}:once :quiet "
                     + action(f"F{index}.INI",
                              f"savebin {script_dir / ('OPAL%d.BIN' % index)} "
                              f"${ST_PALETTE_REGS:x} {PALETTE_BYTES}",
                              f"savebin {script_dir / ('OFRAME%d.BIN' % index)} "
                              f"${screen:x} {SCREEN_BYTES}"))
    return "\n".join(lines) + "\n"


# The widest read any caller makes THROUGH the cursor: dissolve_platforms takes the WORD at
# rng_ptr + 8, so the last byte it touches is rng_ptr + 9. The safe travel is the reloc-free run
# minus that reach, not the whole run.
RNG_WIDEST_CALLER_OFFSET = 8
RNG_CALLER_READ_BYTES = 2
RNG_WIDEST_CALLER_READ = RNG_WIDEST_CALLER_OFFSET + RNG_CALLER_READ_BYTES


def rng_window_bytes(park):
    """How far the cursor may travel from `park` before the two sides stop reading the same bytes.

    COMPUTED FROM THE SHIPPED .PRG, not written down: it is the distance to the next relocation
    site, and a relocated longword is precisely where the two loads differ (it holds file value +
    load base). Deriving it means the number cannot drift from the file it describes, and moving
    RNG_PARK in build.sh re-derives it for free."""
    fixups = sorted(prg_dis.parse_reloc(*_shipped_prg_header()))
    offset = park - IMAGE_LOAD_BASE
    after = [fix for fix in fixups if fix >= offset]
    if not after:
        raise RuntimeError(f"RNG_PARK {park:#x} is past every relocation site")
    return after[0] - offset - RNG_WIDEST_CALLER_READ


def _shipped_prg_header():
    data = ORIGINAL_PRG.read_bytes()
    return data, prg_dis.parse_header(data)


def check_rng_window(stats, rng_park):
    """The parked cursor must have stayed inside the relocation-free stretch.

    Outside it the two loads' bytes differ, so the two sides would stop reading the same random
    stream. Measured at 121 frames: 2904 bytes travelled. This reads OUR side's cursor only — the
    shipped side's is not sampled — which is sound because both are parked at the same offset and
    driven by the same code, but it is a premise rather than an observation of both."""
    travelled = stats["rng_ptr"] - rng_park
    window = rng_window_bytes(rng_park)
    print(f"RNG cursor travelled {travelled} bytes of the {window}-byte relocation-free window "
          f"(our side; the shipped side is parked identically)")
    if 0 <= travelled < window:
        return True
    print("FAIL: the cursor left the window — from here the two sides read different bytes, so "
          "nothing downstream of the RNG is pinned any more")
    return False


# The ST implements three bits per gun; the fourth bit of each nibble does not exist. A CPU read of
# a shifter register returns those bits as whatever was last on the bus, so OUR dump (read by the
# program) carries noise there while the shipped side's (read by the debugger, straight out of
# Hatari's register model) does not. That is a measurement asymmetry, not a palette difference, and
# masking it is the only way to compare the two reads honestly. Everything the ST can display is
# inside the mask.
ST_PEN_MASK = 0x0777


def pen_words(dump):
    return [int.from_bytes(dump[i:i + 2], "big") & ST_PEN_MASK for i in range(0, PALETTE_BYTES, 2)]


def compare_palettes(ours, theirs, samples):
    """The sixteen HARDWARE pens, at the same frames as the bitplanes.

    This is the half the frame differential was blind to by construction: a framebuffer compare sees
    bitplane indices, and the colour those indices resolve to lives in registers neither side's image
    contains. Both sides are read off the shifter itself — ours by the shim in a Super pair, the
    shipped binary's by `savebin` at the frame anchor — so what is compared is what the screen shows,
    not what either program intended."""
    ok = True
    for frame in samples:
        mine, shipped = ours.get(frame), theirs.get(frame)
        if not mine or not shipped or len(mine) != PALETTE_BYTES or len(shipped) != PALETTE_BYTES:
            print(f"  palette {frame:<4} UNUSABLE: ours {len(mine or b'')} bytes, "
                  f"shipped {len(shipped or b'')}, expected {PALETTE_BYTES} each")
            ok = False
            continue
        a, b = pen_words(mine), pen_words(shipped)
        wrong = [pen for pen in range(PALETTE_PENS) if a[pen] != b[pen]]
        if not wrong:
            print(f"  palette {frame:<4} IDENTICAL  {' '.join('%03x' % v for v in b)}")
            continue
        ok = False
        print(f"  palette {frame:<4} DIVERGES on pens {wrong}")
        print(f"      shipped: {' '.join('%03x' % v for v in b)}")
        print(f"      ours   : {' '.join('%03x' % v for v in a)}")
    return ok


def compare_frames(ours, theirs, samples, label="frame"):
    """Byte-equality at every sampled frame, reporting the FIRST divergence rather than a count.

    THE LENGTHS ARE CHECKED FIRST. `zip` stops at the shorter side, so a truncated — or empty —
    dump compares equal as far as it goes and reports IDENTICAL (demonstrated: a zero-byte shipped
    dump passed). `savebin` failing, or a breakpoint firing before the screen is drawn, would look
    exactly like a green."""
    ok = True
    for frame in samples:
        mine, shipped = ours[frame], theirs[frame]
        if len(mine) != SCREEN_BYTES or len(shipped) != SCREEN_BYTES:
            print(f"  {label} {frame:<4} UNUSABLE: ours {len(mine)} bytes, shipped {len(shipped)}, "
                  f"expected {SCREEN_BYTES} each")
            ok = False
            continue
        differing = [i for i, (a, b) in enumerate(zip(mine, shipped)) if a != b]
        if not differing:
            print(f"  {label} {frame:<4} IDENTICAL")
            continue
        ok = False
        rows = sorted({i // SCREEN_ROW_BYTES for i in differing})
        print(f"  {label} {frame:<4} DIVERGES: {len(differing)} bytes on {len(rows)} scanlines "
              f"{rows[:8]}; first at {differing[0]:#x} (row {differing[0] // SCREEN_ROW_BYTES}) "
              f"ours {mine[differing[0]]:#04x} vs shipped {shipped[differing[0]]:#04x}")
    return ok


def compare_displayed(stats, base, screen, frame, rng_park, build="framediff"):
    """The picture the SHIFTER RENDERS, ours against the shipped binary's, at one matched frame.

    Everything else in this file compares MEMORY, and memory-equal is not display-equal: the video
    base register's missing low byte can displace the whole picture while every byte we dump stays
    identical (check_screen_base). This is the only check that looks at what the user looks at. It
    is one frame rather than six because it costs two extra boots and the failure it catches is a
    CONSTANT displacement — visible at any frame or none. That frame is a STATIC one (see
    SCREENSHOT_FRAME) so the capture does not depend on where the raster happens to be.

    Both sides are photographed by the same emulator through the same video path, so the PNGs are
    byte-comparable. THE FRAME ANCHOR IS DELIBERATELY NOT LOAD-BEARING HERE: SCREENSHOT_FRAME is one
    where the picture is CONSTANT, so an anchor landing anywhere in roughly [3, 109] gives the same
    photograph (measured: frames 30, 60 and 100 produce the identical PNG). That is a property this
    check wants — it is looking for a constant displacement, and it must not be able to fail because
    two runs sat at different raster positions."""
    print("--- the displayed picture, both sides photographed at frame", frame)
    mine, our_proc = our_screenshot(stats, frame, build)
    ok = check_exit(our_proc)
    with tempfile.TemporaryDirectory() as tmp:
        script_dir = Path(tmp)
        entry = base + GHIDRA_POLL_QUIT_KEY - IMAGE_LOAD_BASE
        _, _, _, their_proc = run(
            ORIGINAL_PRG, {"HIGH.SCO": SHIPPED_HISCORE.read_bytes()},
            parse=(original_frame_script(script_dir, base, screen, [], rng_park)
                   + screenshot_script(script_dir, entry, frame, "THEIRSHOT")),
            run_vbls=FRAMEDIFF_RUN_VBLS, debug_continues=DEBUG_CONTINUE_SLACK + 4)
        ok &= check_exit(their_proc)
        shot = script_dir / "THEIRSHOT.png"
        if not shot.exists():
            raise RuntimeError("no screenshot from the shipped binary")
        theirs = shot.read_bytes()
    if mine == theirs:
        print(f"  rendered frame {frame}: IDENTICAL ({len(mine)} bytes of PNG, same renderer both sides)")
        return ok
    del ok
    print(f"  rendered frame {frame}: DIFFERS — ours {len(mine)} bytes, shipped {len(theirs)}. "
          f"The memory compares above passed, so this is a DISPLAY fault: video base, resolution "
          f"or palette latch, not the drawing.")
    return False


def framediff_controls(base, screen, samples, rng_park, ours, theirs, their_pens):
    """Two in-mode controls, because a compare that cannot fail proves nothing — and a third that
    has to be its own build (see the end of this docstring).

    DETERMINISM — the shipped side is run a second time with the identical script and must produce
    identical dumps. It is the side with all the machinery (a discovered load base, four kinds of
    debugger breakpoint, a skipped trap), so it is the side whose repeatability is worth asserting.

    AND WHAT THESE TWO CANNOT DO IS EXERCISE THE PALETTE. The game's pens are one constant across
    all six anchors, so a mis-anchor moves the bitplanes and leaves the colours exactly where they
    were: the palette half of the comparison is six repetitions of one measurement. Its control is a
    separate build — `framediff-fault`, which corrupts a pen on the way to the hardware — and its
    limit is stated in the README: this compares the palette AT the anchors, so a shim that had the
    pens right at every sampled frame and wrong in between would pass. That is precisely the shape
    of a flashing pen.

    SENSITIVITY — the shipped side is re-run ANCHORED ONE FRAME LATE and the comparison must FAIL.
    This is a real injected fault, not a rearrangement of the numbers already in hand: an earlier
    version compared ours[early] against theirs[late] and called that sensitivity, which is a
    theorem once the main compare has passed (theirs[late] == ours[late]) — measured, it stayed
    green while the main compare correctly failed. It is also deliberately not the RNG pin, which
    perturbs nothing at these depths (see the README): that is a fact about the samples, not about
    the compare."""
    print("--- control 1: determinism, the shipped side run twice")
    again, again_pens, _ = run_original_frames(base, screen, samples, rng_park)
    ok = compare_frames(again, theirs, samples, label="rerun frame")
    ok &= compare_palettes(again_pens, their_pens, samples)
    if not ok:
        print("FAIL: the shipped side is not reproducible — the pins do not fully determine the run")

    print("--- control 2: sensitivity, the shipped side deliberately MIS-ANCHORED by one frame")
    shifted = [frame + 1 for frame in samples]
    late, _, _ = run_original_frames(base, screen, shifted, rng_park)
    # Deliberately no palette comparison here: see the docstring. A mis-anchor cannot move a
    # palette that does not change between the frames being confused.
    print("    (the comparison below MUST fail; every sample depth was chosen to have a moving "
          "neighbour, so all of them should)")
    mis = compare_frames(ours, {frame: late[frame + 1] for frame in samples}, samples,
                         label="mis-anchored")
    if mis:
        print("FAIL: the mode still passes with the shipped side a frame out — the anchor is not "
              "anchoring and the equality above means nothing")
        return False
    print("  control 2 passed: a one-frame mis-anchor is detected at every sample")
    return ok


def screenshot_script(script_dir, entry_pc, frame, name):
    """A debugger script that photographs the SCREEN at a frame anchor.

    `screenshot` renders through the emulator's own video path, so what it captures is what the
    shifter is displaying — the only artefact in this whole project that is not a memory dump."""
    action = script_dir / f"{name}.INI"
    action.write_text(f"screenshot {script_dir / name}.png\n")
    count = "" if frame == 1 else f":{frame} "
    return f"b pc = ${entry_pc:x} {count}:once :quiet :file {action}\n"


def our_screenshot(stats, frame, build="framediff"):
    """Boot our build again, anchored on OUR poll_quit_key, and photograph frame `frame`.

    The anchor address is the one the PREVIOUS run of this same binary reported about itself
    (`poll_quit_key_pc` in STATS.BIN), not one read out of build/joust.elf. That ELF is overwritten
    by every build while the per-mode .PRGs persist, so it is not necessarily the running program's:
    a stale one once supplied an anchor four bytes out and the mode went green on the wrong
    breakpoint. A binary reporting its own addresses cannot be the wrong binary."""
    with tempfile.TemporaryDirectory() as tmp:
        script_dir = Path(tmp)
        entry = stats["poll_quit_key_pc"]
        _, _, _, proc = run(prg_for(build), drive_files(),
                            parse=screenshot_script(script_dir, entry, frame, "OURSHOT"),
                            debug_continues=DEBUG_CONTINUE_SLACK)
        shot = script_dir / "OURSHOT.png"
        if not shot.exists():
            raise RuntimeError(f"no screenshot from our side at frame {frame} — "
                               f"the anchor {entry:#x} (load base {base:#x}) is wrong")
        return shot.read_bytes(), proc


def run_original_frames(base, screen, samples, rng_park):
    """Boot the SHIPPED binary pinned and anchored, and return its framebuffer per sample frame."""
    with tempfile.TemporaryDirectory() as tmp:
        script_dir = Path(tmp)
        script = original_frame_script(script_dir, base, screen, samples, rng_park)
        produced, _, _, proc = run(ORIGINAL_PRG, {"HIGH.SCO": SHIPPED_HISCORE.read_bytes()},
                                   parse=script, run_vbls=FRAMEDIFF_RUN_VBLS,
                                   # one `c` per expected stop: three pins plus one per sample,
                                   # and slack for a debugger entry we did not schedule
                                   debug_continues=len(samples) + DEBUG_CONTINUE_SLACK)
        # savebin writes to HOST paths, so the dumps land beside the script, not on the drive.
        frames, palettes = {}, {}
        for index in range(1, len(samples) + 1):
            dump = script_dir / f"OFRAME{index}.BIN"
            if not dump.exists():
                raise RuntimeError(f"the shipped binary produced no dump for frame {samples[index-1]}"
                                   f" — an anchor address is wrong or the game never started")
            frames[samples[index - 1]] = dump.read_bytes()
            pens = script_dir / f"OPAL{index}.BIN"
            if not pens.exists():
                raise RuntimeError(f"the shipped binary produced no palette dump for frame "
                                   f"{samples[index-1]} — savebin of the shifter failed")
            palettes[samples[index - 1]] = pens.read_bytes()
        return frames, palettes, proc


# Which checks each negative-control build MUST fail, and which it must still pass. Naming both is
# the point: a control that fails for the wrong reason proves nothing about the check it is for.
INJECTED_FAULTS = {
    "palette": {"fail": ("palette",), "pass": ("boot", "bitplanes")},
    "display": {"fail": ("boot", "display"), "pass": ("bitplanes", "palette")},
}


def report_injected_fault(kind, checks):
    """A negative control passes only if the RIGHT checks failed and the others did not."""
    expected = INJECTED_FAULTS[kind]
    ok = True
    for name in expected["fail"]:
        if checks.get(name, True):
            print(f"FAIL: the injected {kind} fault did NOT trip the {name} check")
            ok = False
    for name in expected["pass"]:
        if not checks.get(name, True):
            print(f"FAIL: the injected {kind} fault also broke the {name} check — the control is "
                  f"not isolating what it claims to")
            ok = False
    if ok:
        print(f"the injected {kind} fault was caught by {'+'.join(expected['fail'])}, and "
              f"{'+'.join(expected['pass'])} still pass — which is what this build is for")
    return ok


def mode_framediff(build="framediff", expect_fail=None):
    """Byte-compare the SHIPPED binary's framebuffer against this build's, frame for frame.

    The title screen already matches (mode `original`); this carries it through the start of a game
    and 120 frames of play. Both sides run on the same Hatari, ROM and HIGH.SCO, and the shipped side
    is pinned and anchored from the debugger — see original_frame_script for the three pins and why
    the Bconin trap has to be skipped rather than answered.

    THE PINS ARE NOT ALL LOAD-BEARING, and the controls below say which: parking the RNG cursor turns
    out not to change any sampled frame (the stream is consulted but nothing it feeds reaches the
    screen this early), so it is precaution rather than the reason the frames match. What IS
    load-bearing is the frame anchor, and the cross-check proves the comparison can see a
    difference at all."""
    samples = [int(frame) for frame in build_setting("FRAME_SAMPLES").split(",")]
    rng_park = int(build_setting("RNG_PARK"), 16)
    print(f"sample frames {samples}; RNG cursor parked at {rng_park:#x} on both sides")

    print("--- ours: one run, every sample")
    produced, _, _, proc = run(prg_for(build), drive_files())
    ok = check_exit(proc)
    require(produced, "STATS.BIN",
            *[f"FRAME{i}.BIN" for i in range(1, len(samples) + 1)],
            *[f"PAL{i}.BIN" for i in range(1, len(samples) + 1)])
    stats = stats_of(produced)
    ours = {frame: produced[f"FRAME{i}.BIN"] for i, frame in enumerate(samples, 1)}
    our_pens = {frame: produced[f"PAL{i}.BIN"] for i, frame in enumerate(samples, 1)}
    ok &= check_stats(stats, {"frame_bytes_written":
                              (SCREEN_BYTES + PALETTE_BYTES) * len(samples)})
    ok &= check_rng_window(stats, rng_park)

    print("--- the shipped binary: load base, then the pinned and anchored run")
    ram, _ = original_ram_dump()
    base = original_load_base(ram)
    screen = int.from_bytes(ram[TOS_V_BAS_AD:TOS_V_BAS_AD + 4], "big")
    print(f"shipped binary loaded at {base:#x}, drawing at {screen:#x}")

    theirs, their_pens, proc = run_original_frames(base, screen, samples, rng_park)
    ok &= check_exit(proc)
    # Each check's verdict is kept SEPARATELY, because a negative control has to be caught by the
    # RIGHT one: ORing them together and inverting would let `framediff-skew` pass on its boot-time
    # alignment failure while the display compare it exists to exercise was blind.
    checks = {"boot": ok,
              "bitplanes": compare_frames(ours, theirs, samples),
              "palette": compare_palettes(our_pens, their_pens, samples)}
    if expect_fail != "palette":     # the pen fault is invisible in a screenshot of frame 60
        checks["display"] = compare_displayed(stats, base, screen, SCREENSHOT_FRAME, rng_park, build)

    if expect_fail:
        return report_injected_fault(expect_fail, checks), ours[samples[-1]]

    ok = all(checks.values())
    ok &= framediff_controls(base, screen, samples, rng_park, ours, theirs, their_pens)
    return ok, ours[samples[-1]]


MODES = {
    "title": mode_title,
    "frames": mode_frames,
    # The quit builds end through the game's own exit, so `frames` is where the script left it and
    # is not pinned; what is pinned is the state the exit was taken from and that it was taken once.
    "quit": lambda: mode_exit("quit", {"two_player_mode": 0, "players_alive": 1, "restarts": 0},
                              at_least={"ikbd_packets": MIN_IKBD_PACKETS}),
    "quittitle": lambda: mode_exit("quittitle", {"frames": 0, "restarts": 0},
                                   at_least={"ikbd_packets": MIN_IKBD_PACKETS_SHORT},
                                   run_vbls=SHORT_RUN_VBLS),
    "restart": lambda: mode_exit("restart", {"restarts": 1, "two_player_mode": 0},
                                 at_least={"ikbd_packets": MIN_IKBD_PACKETS}),
    "hiscore": mode_hiscore,
    "framediff": mode_framediff,
    # The palette compare's negative control: the same build with one pen corrupted on its way to
    # the shifter. It must FAIL, and fail on the palette rather than on the bitplanes.
    "framediff-fault": lambda: mode_framediff(build="framediff-fault", expect_fail="palette"),
    # ...and the DISPLAY check's control: the same run with the screen two bytes off its 256-byte
    # boundary. Every memory comparison must still pass and the rendered picture must not.
    "framediff-skew": lambda: mode_framediff(build="framediff-skew", expect_fail="display"),
    "original": mode_original,
}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "title"
    if mode not in MODES:
        raise SystemExit(f"usage: smoke.py [{' | '.join(MODES)}]")
    started = time.time()
    ok, framebuffer = MODES[mode]()
    # Only on success: mode_original loads out/screen_title.bin as ground truth, so a framebuffer
    # from a run that FAILED check_title would turn a title regression into a confusing side-by-side
    # "no match" days later.
    if ok and framebuffer:
        outdir = REC.parent / "out"
        outdir.mkdir(parents=True, exist_ok=True)
        dump = outdir / f"screen_{mode}.bin"
        dump.write_bytes(framebuffer)
        print(f"wrote {dump}")
    print(f"{mode}: {'OK' if ok else 'FAILED'} in {time.time() - started:.0f}s")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
