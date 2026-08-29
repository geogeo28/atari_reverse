#!/usr/bin/env python3
"""Drive a headless Hatari from Python: start it, push commands into its FIFO, read back what it did.

This is the shared half of every "boot the real binary and watch it" driver in this workspace
(`projects/*/atari/*.py`, `projects/*/tools/boot_shots.py`). It knows Hatari and the GEMDOS
executable format and nothing about any game: the media matrix, the timeline and the success gate
belong to the caller.

    from hatari_headless import HeadlessSession, locate_by_signature

    session = HeadlessSession(argv, log_path=..., fifo_path=..., work_dir=...)
    session.wait(6.0)
    base = locate_by_signature(session.savebin("ram.bin", 0, ST_RAM_BYTES), prg_path)
    session.screenshot(out / "title.png")
    session.close()

WHAT IT KNOWS THE HARD WAY
--------------------------
*Opening the command FIFO can hang for ever.* Hatari creates the FIFO and opens its READ end; a
plain blocking `open(fifo, "w")` blocks until it does, and if Hatari has already died the writer
waits until the heat death of the universe. So the open is `O_WRONLY | O_NONBLOCK` and retried, with
`process.poll()` checked between tries — a dead emulator is an error, not a hang.

*Emulation runs in REAL TIME* (no `--fast-forward`), so a wall-clock `wait()` here is the same span
of emulated time.

*A capture is not a surface.* Hatari writes a PNG whether or not the machine is doing anything, and
exits 0 after a bus error it printed to its log. `log_faults()`, `distinct_colours()` and the return
code from `close()` are what turn a run into a pass or a fail; see docs/on-target-execution.md.

*Sound recording is a config value plus a shortcut, not an option.* There is no `--wav-record`:
`szYMCaptureFileName` in a `[Sound]` section says where, and `hatari-shortcut recsound` toggles the
recorder. `sound_capture_arguments()` and `HeadlessSession.record_sound()` are those two halves, and
they work under SDL's dummy audio device — headless records what speakers would have played.

*`hatari-event keydown` takes an ST SCANCODE when it is spelled "0x..", and an ASCII character when
it is one character long*, so `key()` always spells hex. A break code is the make code with bit 7
set. A key bound to Hatari's keyboard-as-joystick emulation is SWALLOWED headless (measured in
projects/blackice/atari/play_headless.py): the stick cannot be pressed from outside at all, and the
only way in is to poke the byte the game's own joystick ISR writes.
"""
import os
import struct
import subprocess
import time
from pathlib import Path

HATARI = "hatari"

# --- timings ---------------------------------------------------------------------------------
POLL_SECONDS = 0.1
FIFO_OPEN_SECONDS = 20.0
FILE_WAIT_SECONDS = 30.0
SHUTDOWN_SECONDS = 20.0
# `loadbin` is asynchronous: the debugger returns before the write has landed, and a command sent
# straight after it can be acted on first.
POKE_SETTLE_SECONDS = 0.3

# --- ST keyboard -----------------------------------------------------------------------------
BREAK_BIT = 0x80
KEY_HOLD_SECONDS = 0.4

# --- sound recording ---------------------------------------------------------------------------
# Hatari has NO command-line option for where a sound recording goes: the destination is a config
# value and the recorder is a runtime shortcut. So a caller that wants a WAV has to hand Hatari a
# config file naming the path, and then toggle `recsound` around the span it wants.
SOUND_CONFIG_TEMPLATE = "[Sound]\n%s = %s\n"
SOUND_CAPTURE_KEY = "szYMCaptureFileName"
SOUND_RECORD_SHORTCUT = "hatari-shortcut recsound"
# What Hatari writes: 16-bit STEREO at the --sound frequency, both channels carrying the same mono
# YM signal (the ST has one PSG and no panning). A reader that assumes mono reads it at half speed.
RECORDED_CHANNELS = 2
RECORDED_SAMPLE_BYTES = 2
# Hatari drops samples rather than stalling when its mixer buffer overruns, and says so in the log.
# A recording that carries these has holes in it, so it is a fault marker for an audio run — but
# only for one, which is why it is not in LOG_FAULT_MARKERS.
SOUND_UNDERRUN_MARKER = "some sound samples were not correctly emulated"

# --- the log ---------------------------------------------------------------------------------
# Hatari polls its command FIFO non-blockingly and logs a line every time the read finds nothing,
# which is tens of thousands of identical lines per run and buries everything worth reading.
FIFO_POLL_NOISE = "command FIFO read error"
# Hatari's own wording, read out of the 2.6.1 binary. It refuses GEMDOS directory emulation below
# TOS 1.04 and then simply does not mount the drive, so an --auto program never runs.
GEMDOS_NEEDS_TOS104 = "Please use at least TOS v1.04 for the HD directory emulation"
# Substrings that mean the run is worthless. Deliberately NOT a generic /error/i: Hatari prints
# "ERROR: symbol table missing from the program!" for every stripped .PRG and that is harmless.
LOG_FAULT_MARKERS = (
    "Bus error",            # the 68000 faulted on an address nothing answers
    "Address error",        # ...or on an odd word address
    "CPU halted",           # double fault
    "Failed to load",       # a TOS image, disk image or program Hatari could not open
    "Not a disk image",
    GEMDOS_NEEDS_TOS104,
)

# --- GEMDOS executable header ------------------------------------------------------------------
PRG_MAGIC = 0x601A
# magic, text, data, bss, symbol-table lengths, reserved, program flags, absflag.
PRG_HEADER_FORMAT = ">HIIIIIIH"
PRG_HEADER_BYTES = struct.calcsize(PRG_HEADER_FORMAT)   # 28
RELOC_OFFSET_BYTES = 4          # the relocation table opens with the first fixup's TEXT offset...
NO_FIXUPS = 0                   # ...or with a single zero longword when there are none at all
# A signature shorter than this is not worth searching a megabyte of RAM for: the odds of a chance
# match stop being negligible, and the uniqueness check below would start failing on noise.
MIN_SIGNATURE_BYTES = 12


def headless_environment():
    """The environment that keeps SDL from wanting a window or a sound card."""
    return dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")


def sound_capture_arguments(config_path, wav_path):
    """The Hatari arguments that point WAV recording at `wav_path`, via a config file it writes.

    SDL's dummy audio device is still a device: Hatari mixes into it and the recorder taps the same
    buffer, so a headless run records exactly what a run with speakers would play.
    """
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(SOUND_CONFIG_TEMPLATE % (SOUND_CAPTURE_KEY, Path(wav_path).resolve()))
    return ["-c", str(config_path)]


# --- finding a loaded program in RAM -----------------------------------------------------------

def first_fixup_offset(image):
    """The TEXT offset of a GEMDOS executable's first relocated longword, or None if it has none.

    Three shapes have no fixups: a header whose `absflag` is set (no relocation table is present at
    all), a table that is a single zero longword (present but empty), and a file that simply stops
    where the table would begin. All three used to fall through the arithmetic below — the first
    into a `struct.error` on a slice past EOF, the others into "the first relocation is at 0".
    """
    magic, text, data, _bss, symbols, _reserved, _flags, absflag = struct.unpack_from(PRG_HEADER_FORMAT, image)
    if magic != PRG_MAGIC:
        raise SystemExit(f"not a GEMDOS executable (magic {magic:#06x}, expected {PRG_MAGIC:#06x})")
    table = PRG_HEADER_BYTES + text + data + symbols
    if absflag or len(image) < table + RELOC_OFFSET_BYTES:
        return None
    first = struct.unpack_from(">I", image, table)[0]
    return None if first == NO_FIXUPS else first


def prg_text_signature(image):
    """The leading TEXT bytes of a GEMDOS executable that survive loading unchanged.

    GEMDOS rewrites every relocated longword in place as it loads, so past the FIRST fixup the
    file's bytes and RAM's disagree by construction. Everything before it is verbatim, and that is
    what can be searched for. With no fixups at all, the whole TEXT is signature-safe.
    """
    text_length = struct.unpack_from(PRG_HEADER_FORMAT, image)[1]
    whole_text = image[PRG_HEADER_BYTES:PRG_HEADER_BYTES + text_length]
    first_fixup = first_fixup_offset(image)
    if first_fixup is None:
        return whole_text
    if first_fixup < MIN_SIGNATURE_BYTES:
        raise SystemExit(f"the first relocation is at text offset {first_fixup:#x} — too early to cut a "
                         f"signature of at least {MIN_SIGNATURE_BYTES} bytes that the loaded image would match")
    return whole_text[:first_fixup]


def locate_by_signature(ram, prg_path):
    """Where GEMDOS put a program's TEXT in `ram`, or None if it is not loaded (yet).

    FOUND, NOT COMPUTED: the load address depends on the TOS version and on what the OS put below
    the TPA, and it differs between a floppy boot and a GEMDOS drive. Returning None rather than
    raising is what lets a caller POLL for the load instead of guessing a fixed pre-roll.

    THE SIGNATURE ALONE IS NOT ENOUGH DURING A FLOPPY BOOT: while the program is being read in, the
    same bytes are sitting in a disk buffer as well as in the program, and a bare search finds two.
    They are told apart by RELOCATION. The first fixup's longword holds an offset from the start of
    TEXT in the file, and GEMDOS adds the load address to it in place, so the loaded copy — and only
    it — satisfies `longword == file's longword + base`. That is an exact test, not a heuristic, and
    it doubles as proof that the candidate really is a loaded program.
    """
    image = Path(prg_path).read_bytes()
    signature = prg_text_signature(image)
    fixup = first_fixup_offset(image)
    unrelocated = struct.unpack_from(">I", image, PRG_HEADER_BYTES + fixup)[0] if fixup is not None else None

    bases = []
    at = ram.find(signature)
    while at >= 0:
        if fixup is None or struct.unpack_from(">I", ram, at + fixup)[0] == unrelocated + at:
            bases.append(at)
        at = ram.find(signature, at + 1)
    if not bases:
        return None
    if len(bases) > 1:
        raise SystemExit(f"the TEXT of {prg_path} appears relocated at {len(bases)} addresses in RAM "
                         f"({[hex(base) for base in bases]}) — every address derived from it would be a guess")
    return bases[0]


# --- debugger scripts --------------------------------------------------------------------------

def action_file(directory, name, *commands, tail="cont"):
    """Write one breakpoint's action file and return the `:file` clause that runs it.

    These are HOST paths the debugger reads; they are deliberately not on any emulated drive, where
    the program itself could see them. `tail` is the last line — `cont` for an anchor that hands the
    machine back, `q` for one that closes the run.
    """
    path = Path(directory) / name
    path.write_text("".join(command + "\n" for command in commands) + tail + "\n")
    return f":file {path}"


def poke_byte(address, value):
    """A debugger write of one byte, as an action-file line."""
    return f"w b ${address:x} ${value:x}"


def pc_breakpoint(pc, action):
    """A breakpoint on an address, and the only place its spelling lives.

    Deliberately NOT `:once`, which would retire it on its first hit: a one-shot answer to a gate
    that guards every respawn opens the gate exactly once and leaves the run sitting on it
    thereafter. Add the flag here, with the reason, if a caller ever genuinely wants one arrival.
    """
    return f"b pc = ${pc:x} :quiet " + action


# --- reading back what happened ------------------------------------------------------------------

def strip_log_noise(path):
    """Drop Hatari's per-poll FIFO chatter from a log, in place, so the rest can be read."""
    path = Path(path)
    kept = [line for line in path.read_text(errors="replace").splitlines(True) if FIFO_POLL_NOISE not in line]
    path.write_text("".join(kept))


def log_faults(path, markers=LOG_FAULT_MARKERS):
    """The lines of a Hatari log that say the run is worthless. Empty means nothing was found."""
    text = Path(path).read_text(errors="replace")
    return [line.strip() for line in text.splitlines() if any(marker in line for marker in markers)]


def distinct_colours(png_path):
    """How many colours a capture actually holds — one means Hatari photographed a blank screen."""
    from PIL import Image
    with Image.open(png_path) as image:
        colours = image.convert("RGB").getcolors(maxcolors=1 << 24)
    # getcolors() returns None only past maxcolors, which 2**24 cannot be for an RGB image.
    return len(colours)


def same_picture(first_png, second_png):
    """True if two captures are the same image — i.e. nothing moved between them."""
    from PIL import Image
    with Image.open(first_png) as first, Image.open(second_png) as second:
        if first.size != second.size:
            return False
        return first.convert("RGB").tobytes() == second.convert("RGB").tobytes()


class HeadlessSession:
    """A running headless Hatari, driven through its command FIFO.

    `argv` is the whole Hatari command line EXCEPT `--cmd-fifo`, which this class appends: the FIFO
    is its own, and a caller that spelled it too would be able to disagree with it.
    """

    def __init__(self, argv, log_path, fifo_path, work_dir):
        self.log_path = Path(log_path)
        self.fifo = Path(fifo_path)
        self.work = Path(work_dir)
        self.fifo.parent.mkdir(parents=True, exist_ok=True)
        self.work.mkdir(parents=True, exist_ok=True)
        # A stale FIFO from a killed run is opened successfully and read by nobody, which loses every
        # command silently.
        self.fifo.unlink(missing_ok=True)
        self.command = list(argv) + ["--cmd-fifo", str(self.fifo)]
        self.started = time.monotonic()     # power-on, for a caller timing anything against the boot
        self.log = open(self.log_path, "w")
        self.process = subprocess.Popen(self.command, env=headless_environment(), stdin=subprocess.DEVNULL,
                                        stdout=self.log, stderr=subprocess.STDOUT)
        try:
            self.pipe = self._open_fifo()
        except BaseException:
            # A failed handshake must not leave an emulator running: it holds the media, and the
            # next run's Hatari would be the second one on the same image.
            self.process.kill()
            self.process.wait()
            self.log.close()
            raise

    def _open_fifo(self):
        """Wait for Hatari to open the FIFO's read end, without being able to wait for ever."""
        deadline = time.monotonic() + FIFO_OPEN_SECONDS
        while time.monotonic() < deadline:
            if self.fifo.exists():
                try:
                    return open(os.open(str(self.fifo), os.O_WRONLY | os.O_NONBLOCK), "w")
                except OSError:
                    pass                        # created but not yet opened for reading
            if self.process.poll() is not None:
                raise SystemExit(f"Hatari exited (status {self.process.returncode}) before opening {self.fifo} — "
                                 f"see {self.log_path}")
            time.sleep(POLL_SECONDS)
        raise SystemExit(f"Hatari never opened the command FIFO {self.fifo} — see {self.log_path}")

    # ---- the machine ----------------------------------------------------------------------------
    def send(self, line):
        self.pipe.write(line + "\n")
        self.pipe.flush()

    def wait(self, seconds):
        time.sleep(seconds)

    def alive(self):
        return self.process.poll() is None

    def require_alive(self, doing):
        if not self.alive():
            raise SystemExit(f"Hatari died (status {self.process.returncode}) while {doing} — see {self.log_path}")

    def _await_file(self, path, minimum_bytes, timeout=FILE_WAIT_SECONDS):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists() and path.stat().st_size >= minimum_bytes:
                return path
            self.require_alive(f"writing {path.name}")
            time.sleep(POLL_SECONDS)
        raise SystemExit(f"the debugger never wrote {path} — see {self.log_path}")

    def savebin(self, name, address, length):
        """`length` bytes of emulated memory from `address`, through a host file in the work dir."""
        dump = self.work / name
        dump.unlink(missing_ok=True)
        self.send(f"hatari-debug savebin {dump} ${address:x} ${length:x}")
        return self._await_file(dump, length).read_bytes()

    def poke(self, address, *values):
        """Write bytes into emulated memory now — the only way in for input Hatari cannot deliver."""
        blob = self.work / "poke.bin"
        blob.write_bytes(bytes(values))
        self.send(f"hatari-debug loadbin {blob} ${address:x}")
        self.wait(POKE_SETTLE_SECONDS)

    def arm(self, breakpoint_line):
        self.send("hatari-debug " + breakpoint_line)

    # ---- input ----------------------------------------------------------------------------------
    def key(self, scancode, hold_seconds=KEY_HOLD_SECONDS):
        """Press and release one ST key, held long enough for a per-frame poll to see it."""
        self.send(f"hatari-event keydown {scancode:#04x}")
        self.wait(hold_seconds)
        self.send(f"hatari-event keyup {scancode | BREAK_BIT:#04x}")

    def record_sound(self, seconds, during=None):
        """Record `seconds` of emulated audio to the WAV `sound_capture_arguments` named.

        `recsound` is a TOGGLE, so the span is bundled here rather than exposed as two sends: an
        unpaired one leaves the recorder running into whatever the caller does next, and Hatari
        reports that only as a longer file. A second span in the same run REPLACES the first, since
        the config names one path — copy the finished WAV aside before starting another.

        `during(seconds)` fills the span in place of a plain wait, for a caller that has to keep
        driving the machine while it records.
        """
        self.send(SOUND_RECORD_SHORTCUT)
        (during or self.wait)(seconds)
        self.send(SOUND_RECORD_SHORTCUT)

    # ---- output ---------------------------------------------------------------------------------
    def screenshot(self, path):
        """Photograph the frame and WAIT for the file, so a caller never reads a half-written PNG."""
        path = Path(path)
        path.unlink(missing_ok=True)
        self.send(f"hatari-debug screenshot {path}")
        return self._await_file(path, 1)

    def close(self):
        """Shut the emulator down and return its exit status (negative = it had to be killed)."""
        try:
            self.send("hatari-shortcut quit")
        except (BrokenPipeError, ValueError, OSError):
            pass
        try:
            self.process.wait(timeout=SHUTDOWN_SECONDS)
        except subprocess.TimeoutExpired:
            # A Hatari stopped INSIDE the debugger does not act on the quit shortcut until it
            # resumes, and would otherwise outlive this process.
            self.process.terminate()
            try:
                self.process.wait(timeout=SHUTDOWN_SECONDS)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.pipe.close()
        self.log.close()
        self.fifo.unlink(missing_ok=True)
        strip_log_noise(self.log_path)
        return self.process.returncode
