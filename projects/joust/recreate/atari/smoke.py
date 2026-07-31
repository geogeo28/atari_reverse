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

DISK = HERE / "disk"
BUILD = HERE / "build"
INPUTS_ONLY = {"JOUST.PRG", "JOUST.IMG", "CMD.INI", "ACT.INI"}   # staged, never written back

# Which build.sh mode each check needs. Every check boots build/JOUST-<mode>.PRG rather than
# whatever build.sh last copied to disk/, because the key script is compiled INTO the binary: run
# `smoke.py restart` against the quit build and the run quits cleanly during play, which reads as
# "the longjmp restart is broken" instead of "you booted the wrong PRG".
MODE_BUILD = {"title": "title", "frames": "smoke", "quit": "quit",
              "quittitle": "quittitle", "restart": "restart"}


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

# STATS.BIN — fourteen big-endian longwords, written by joust_main.c's dump_stats() in this order.
STATS_FIELDS = ("frames", "console_polls", "dosound", "dosound_in_play", "first_sound_frame",
                "psg_writes", "psg_writes_in_play", "ikbd_packets", "restarts",
                "hiscore_bytes_written", "two_player_mode", "players_alive",
                "player_x", "player_y")
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
ORIGINAL_DUMP_VBL = 2500    # by then the ORIGINAL is sitting on its title screen
ORIGINAL_RUN_VBLS = "4000"

# TOS's ROM probes its own hardware at boot and bus-errors doing it; those are expected and are the
# only ones allowed. Anything faulting from RAM is ours.
ROM_PC = re.compile(r"PC=\$(fc|e0)")


def find_rom():
    rom = os.environ.get("JOUST_TOS_ROM") or tos_probe.find_tos_rom()
    if rom:
        return rom
    local = sorted((REC.parents[2] / "tools" / "hatari").glob("TOS*.img"))
    return str(local[-1]) if local else None


def run(prg, files, trace=None, parse=None, run_vbls=RUN_VBLS):
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
                "--memsize", str(MEMSIZE_MB), "--monitor", "rgb", "--tos-res", "low", "--tos", rom,
                "--run-vbls", run_vbls, "--harddrive", str(drive), "--auto", "C:\\JOUST.PRG"]
        if trace:
            args += ["--trace", trace, "--trace-file", str(drive / "TRACE.TXT")]
        if parse:
            (drive / "CMD.INI").write_text(parse.format(drive=drive))
            args += ["--parse", str(drive / "CMD.INI")]
        proc = subprocess.run(args, env=env, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=RUN_TIMEOUT)
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
    sources = [*HERE.glob("*.c"), *HERE.glob("*.s"), *HERE.glob("shim_include/*.h"),
               *REC.glob("src/*.c"), *REC.glob("include/*.h")]
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
    require(produced, "SCREEN.BIN")
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
    require(produced, "SCREEN.BIN")
    ok = check_exit(proc)
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
    require(produced, "SCREEN.BIN")
    ok &= check_exit(proc) & check_title(produced["SCREEN.BIN"])
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
