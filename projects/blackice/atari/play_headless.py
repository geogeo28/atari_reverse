#!/usr/bin/env python3
"""Play BLACKICE.PRG in a headless Hatari and capture what a player would see.

`bench.py` arms a `--parse` script at startup, which is enough to time fixed passes but cannot
answer "what happens when someone walks into that door".  This starts the same emulator with
`--cmd-fifo` instead, so commands can be pushed into it WHILE it runs:

    hatari-event keydown/keyup <ST scancode>   a held key, straight into the emulated IKBD
    hatari-debug screenshot <png>              the frame, to a named file
    hatari-debug savebin <file> <addr> <len>   memory, for the state a picture cannot show
    hatari-debug loadbin <file> <addr>         memory, for the input Hatari cannot deliver

Emulation runs in REAL TIME (no --fast-forward), so a wall-clock sleep here is the same span of
emulated time and "walk forward for two seconds" means what it says.

TWO THINGS THIS FILE KNOWS THE HARD WAY.

*Keys, not the stick.*  `hatari-event` takes an ST scancode or a single ASCII character.  The
scancode goes to the emulated keyboard.  The character goes through Hatari's host keymap, which
offers it to the keyboard-as-joystick emulation first -- and headless, that emulation SWALLOWS the
key and then reports nothing: binding joystick port 1 to W/S/A/D/F stops those letters reaching the
ST keyboard, but `bi_joy_port1` never moves and no $FF packet is sent.  So the joystick cannot be
pressed from outside at all, and `stick()` pokes the byte the joystick ISR writes instead.  That
exercises everything above `bi_joy_entry` and nothing below it; the IKBD-to-`joyvec` delivery stays
unproven either way.

*Where GameState is, is found and not computed.*  `savebin` takes a plain number, never an
expression, so the debugger's virtual TEXT variable cannot be added to inside the command; and the
program's own `.bss` offset moves whenever the tree is rebuilt.  `locate_state` scans RAM once for
the state's boot signature, which is right for whatever binary is actually running.
"""
import argparse
import math
import os
import re
import struct
import subprocess
import time
from pathlib import Path

# ST keyboard make codes, the ones DESIGN 6 binds.  A break code is the make with bit 7 set;
# `hatari-event keyup` sends it.  They are always spelled to Hatari as "0x.." -- a ONE-character
# argument is taken as an ASCII character and never as a scancode, so a bare "1" is the '1' key and
# not Escape, and that silently made an Escape test pass nothing at all.
KEY = {"esc": 0x01, "7": 0x08, "8": 0x09, "9": 0x0a, "p": 0x19, "z": 0x2c, "x": 0x2d,
       "space": 0x39, "up": 0x48, "left": 0x4b, "right": 0x4d, "down": 0x50,
       "alt": 0x38, "shift": 0x2a}

# The IKBD joystick report bitmap, as main.c reads it.
JOY = {"up": 0x01, "down": 0x02, "left": 0x04, "right": 0x08, "fire": 0x80}

# GameState field offsets, from offsetof() compiled BY THE TARGET COMPILER -- the 68000 aligns
# 32-bit fields to 2 bytes and the host does not, so a host-computed offset would be quietly wrong.
STATE_BYTES = 0x4224
STATE_FIELDS = {
    "x": (0x0004, ">h"), "y": (0x0006, ">h"), "angle": (0x0008, ">H"),
    "tick": (0x1410, ">L"), "trace_milli": (0x1458, ">l"),
    "integrity": (0x420a, ">h"), "cycles": (0x420c, ">h"),
    "tokens": (0x4214, ">B"), "phase": (0x4215, ">B"),
    "next_sector": (0x4216, ">B"), "trace_band": (0x4217, ">B"),
    "muzzle_flash": (0x421b, ">B"), "deaths": (0x421c, ">B"), "kills": (0x421e, ">B"),
}
# bi_joy_port1 relative to g_state: both are in .bss, so their DISTANCE survives a rebuild even
# though neither address does.  From `m68k-elf-nm build/blackice.elf`.
JOY_PORT1_FROM_STATE = 0x538c

# The state at the first frame of level 1, which is what locate_state recognises.
BOOT_INTEGRITY, BOOT_CYCLES = 100, 60
ST_RAM_BYTES = 0x100000
SEARCH_LOW, SEARCH_HIGH = 0x10000, 0xf0000

CELL_UNITS = 256                # fixed.h: map units per grid cell
ANGLE_UNITS_PER_TURN = 65536
# Angle 0 is +x (east) and y grows south, so north is 270 degrees.  Measured on the running game,
# not taken from the constants: a held key arrives once per RENDERED frame and the frame is 100-160
# ms, so what the player gets is well under PLAYER_TURN_SPEED x SIM_HZ.
DEGREES_PER_SECOND = 115.0
CELLS_PER_SECOND = 3.7
# TOS's type-ahead holds a few repeats past the key release; let them drain before measuring.
SETTLE_SECONDS = 0.5

# Where the ST's 320x200 screen sits inside Hatari's bordered screenshot at this window size,
# measured with bench.py's locate_screen.
SCREEN_LEFT, SCREEN_TOP, SCREEN_SCALE = 96, 58, 2
SCREEN_W, SCREEN_H = 320, 200

MEMSIZE_MB = 1
BOOT_SECONDS = 16               # EmuTOS, GEMDOS, the PAK load, and a few frames of settling
DEFAULT_DISK = Path(__file__).resolve().parent / "disk"   # the drive bench.py boots from


def crop_to_screen(png):
    """Rewrite a Hatari screenshot as just the ST screen; the borders are not the game."""
    from PIL import Image
    box = (SCREEN_LEFT, SCREEN_TOP,
           SCREEN_LEFT + SCREEN_W * SCREEN_SCALE, SCREEN_TOP + SCREEN_H * SCREEN_SCALE)
    Image.open(png).crop(box).save(png)
    return png


class Session:
    """A running headless Hatari with the game in it."""

    def __init__(self, disk, out, prg="BLACKICE.PRG", run_vbls=400000, extra=()):
        self.out = Path(out)
        (self.out / "shots").mkdir(parents=True, exist_ok=True)
        self.fifo = self.out / "cmd.fifo"
        if self.fifo.exists():
            self.fifo.unlink()
        self.log_path = self.out / "hatari.log"
        self.log = open(self.log_path, "w")
        self.state_base = None
        self.command = ["hatari",
                        "--machine", "ste", "--memsize", str(MEMSIZE_MB), "--monitor", "rgb",
                        "--sound", "off", "--confirm-quit", "off", "--statusbar", "off",
                        "--drive-led", "off", "--frameskips", "0", "--run-vbls", str(run_vbls),
                        "--harddrive", str(disk), "--auto", f"C:\\{prg}",
                        "--cmd-fifo", str(self.fifo)] + list(extra)
        environment = dict(os.environ)
        environment.update({"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"})
        self.process = subprocess.Popen(self.command, env=environment, stdin=subprocess.DEVNULL,
                                        stdout=self.log, stderr=subprocess.STDOUT)
        self.pipe = self._open_fifo()

    def _open_fifo(self):
        """Hatari creates the fifo and opens it for reading; a writer has to wait for that."""
        deadline = time.time() + 20
        while time.time() < deadline:
            if self.fifo.exists():
                try:
                    return open(os.open(str(self.fifo), os.O_WRONLY | os.O_NONBLOCK), "w")
                except OSError:
                    pass
            if self.process.poll() is not None:
                raise SystemExit(f"Hatari exited before opening {self.fifo}")
            time.sleep(0.1)
        raise SystemExit(f"Hatari never opened {self.fifo}")

    def send(self, line):
        self.pipe.write(line + "\n")
        self.pipe.flush()

    def wait(self, seconds):
        time.sleep(seconds)

    # ---- input ---------------------------------------------------------------------------------
    def down(self, *names):
        for name in names:
            self.send(f"hatari-event keydown 0x{KEY[name]:02x}")

    def up(self, *names):
        for name in names:
            self.send(f"hatari-event keyup 0x{KEY[name]:02x}")

    def hold(self, name, seconds, modifier=None):
        """Hold one key (optionally under Alt or Shift) for `seconds` of emulated time."""
        if modifier:
            self.down(modifier)
        self.down(name)
        self.wait(seconds)
        self.up(name)
        if modifier:
            self.up(modifier)

    def tap(self, name, seconds=0.3):
        self.hold(name, seconds)

    def stick(self, bits, seconds):
        """Hold the joystick bitmap for `seconds`, by poking the byte the joystick ISR writes."""
        self.poke(self.state_address() + JOY_PORT1_FROM_STATE, bits)
        self.wait(seconds)
        self.poke(self.state_address() + JOY_PORT1_FROM_STATE, 0)

    # ---- navigation ----------------------------------------------------------------------------
    # A key held for less than this delivers one make and no repeats, and one make is one frame's
    # worth of turn -- about 8 degrees.  Every nudge is at least this long, so a turn always moves.
    MIN_HOLD_SECONDS = 0.7

    def turn_to(self, degrees, tolerance=15.0, tries=6):
        """Turn until facing within `tolerance` of `degrees`, measuring after every nudge."""
        for _ in range(tries):
            error = (degrees - self.state()["degrees"] + 180.0) % 360.0 - 180.0
            if abs(error) <= tolerance:
                return True
            seconds = min(max(abs(error) / DEGREES_PER_SECOND, self.MIN_HOLD_SECONDS), 1.4)
            self.hold("left" if error > 0 else "right", seconds)
            self.wait(SETTLE_SECONDS)
        return abs((degrees - self.state()["degrees"] + 180.0) % 360.0 - 180.0) <= tolerance

    def goto(self, cell_x, cell_y, tolerance=0.45, tries=10):
        """Walk to a map cell, re-aiming each leg.  Returns the state it stopped in."""
        for _ in range(tries):
            state = self.state()
            dx, dy = cell_x - state["cell_x"], cell_y - state["cell_y"]
            distance = math.hypot(dx, dy)
            if distance <= tolerance:
                return state
            self.turn_to(math.degrees(math.atan2(dy, dx)) % 360.0)
            self.hold("up", min(distance / CELLS_PER_SECOND, 1.5))
            self.wait(SETTLE_SECONDS)
        return self.state()

    # ---- the machine ---------------------------------------------------------------------------
    def _await_file(self, path, size, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if path.exists() and path.stat().st_size >= size:
                return path
            time.sleep(0.05)
        raise SystemExit(f"the debugger never wrote {path}")

    def savebin(self, name, address, length):
        raw = self.out / name
        if raw.exists():
            raw.unlink()
        self.send(f"hatari-debug savebin {raw} ${address:x} ${length:x}")
        return self._await_file(raw, length).read_bytes()

    def poke(self, address, *values):
        blob = self.out / "poke.bin"
        blob.write_bytes(bytes(values))
        self.send(f"hatari-debug loadbin {blob} ${address:x}")
        time.sleep(0.3)

    def place(self, cell_x, cell_y, degrees):
        """Put the player somewhere with the debugger.

        This is INSTRUMENTATION, not play: it is the only way to aim the camera at a specific
        entity from a script, because a turn is delivered by TOS key repeat and lands within tens
        of degrees rather than one.  Every finding taken this way says so."""
        angle = int(round(degrees * ANGLE_UNITS_PER_TURN / 360.0)) % ANGLE_UNITS_PER_TURN
        self.poke(self.state_address() + STATE_FIELDS["x"][0],
                  *struct.pack(">hhH", int(cell_x * CELL_UNITS), int(cell_y * CELL_UNITS), angle))

    def state_address(self):
        """Where GameState is in RAM, found by its boot signature rather than computed."""
        if self.state_base is None:
            ram = self.savebin("ram.bin", 0, ST_RAM_BYTES)
            wanted = struct.pack(">hh", BOOT_INTEGRITY, BOOT_CYCLES)
            found = [base for base in range(SEARCH_LOW, SEARCH_HIGH, 2)
                     if ram[base + 0x420a:base + 0x420e] == wanted]
            if len(found) != 1:
                raise SystemExit(f"{len(found)} candidates for GameState in RAM ({found[:8]}) -- "
                                 "the game did not reach its first frame, or the struct moved")
            self.state_base = found[0]
        return self.state_base

    def state(self):
        blob = self.savebin("state.bin", self.state_address(), STATE_BYTES)
        out = {name: struct.unpack_from(fmt, blob, offset)[0]
               for name, (offset, fmt) in STATE_FIELDS.items()}
        out["cell_x"] = out["x"] / CELL_UNITS
        out["cell_y"] = out["y"] / CELL_UNITS
        out["degrees"] = out["angle"] * 360.0 / ANGLE_UNITS_PER_TURN
        return out

    def report(self, label):
        s = self.state()
        print(f"  {label}: cell=({s['cell_x']:.2f},{s['cell_y']:.2f}) {s['degrees']:.0f}deg "
              f"integrity={s['integrity']} cycles={s['cycles']} trace={s['trace_milli']} "
              f"band={s['trace_band']} tokens={s['tokens']:#04x} phase={s['phase']} "
              f"kills={s['kills']} deaths={s['deaths']} tick={s['tick']}")
        return s

    def shot(self, name):
        png = self.out / "shots" / name
        if png.exists():
            png.unlink()
        self.send(f"hatari-debug screenshot {png}")
        self._await_file(png, 1)
        time.sleep(0.3)
        crop_to_screen(png)
        print(f"  shot: {png}")
        return png

    def close(self):
        try:
            self.send("hatari-shortcut quit")
        except (BrokenPipeError, ValueError):
            pass
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.log.close()
        return self.process.returncode


def main():
    parser = argparse.ArgumentParser(description="Boot the game, screenshot it, print its state.")
    parser.add_argument("--disk", default=str(DEFAULT_DISK),
                        help="the GEMDOS drive holding BLACKICE.PRG")
    parser.add_argument("--out", default="qa-out", help="where the log, shots and dumps go")
    parser.add_argument("--boot", type=float, default=BOOT_SECONDS, help="seconds to let boot settle")
    args = parser.parse_args()
    session = Session(args.disk, args.out)
    session.wait(args.boot)
    session.report("boot")
    session.shot("boot.png")
    print(f"hatari exit: {session.close()}")


if __name__ == "__main__":
    main()
