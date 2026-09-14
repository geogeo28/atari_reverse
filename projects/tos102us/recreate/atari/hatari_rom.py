#!/usr/bin/env python3
"""hatari_rom.py — one machine, one way of booting a ROM in it, shared by all three drivers here.

THE POINT OF THIS FILE IS THAT THERE IS EXACTLY ONE MACHINE. Every number the boot surface and the
two ledgers report is a property of a ROM *in a machine*, so two ROMs are comparable only if the
machine either side of them is bit-for-bit the same configuration. Spelling the command line in
three drivers would make that a convention; spelling it once makes it a fact.

THE CONFIGURATION, AND WHY EACH FLAG IS THERE
  --machine st --memsize 1 --monitor rgb   A 1 MB STF on a colour monitor: the machine TOS 1.02 was
        sold for. 1 MB and not 512 KB because the ledger block sits at 0xC0000, and not 4 MB because
        _memtop, phystop and every Malloc answer move with the size and a bigger machine buys none
        of them.
  --sound off                              The PSG is not a surface any driver here reads, and a
        sound thread is one more thing between the emulator and a reproducible run.
  --patch-tos off --fast-boot off --timer-d off
        HATARI MODIFIES TOS IMAGES BY DEFAULT and it is quiet about it: at --log-level debug the
        original ROM reports `Applying TOS patch 'big VDI resolutions mouse driver'` and `Applied 1
        TOS patches`, and the rebuilt ROM reports the same patch FAILING (`expected d2c147f9, found
        0`) because the bytes are not there. A conformance comparison against a patched original is
        a comparison against a ROM nobody shipped, and a comparison in which one side is patched and
        the other is not is not a comparison at all. All three off means both sides run the bytes on
        disk. Measured on Hatari 2.6.1 with this ROM: `--patch-tos on` applies exactly one patch and
        skips one ('boot from DMA bus'); `--patch-tos off` logs `Skipped TOS patches.`
  --fast-forward on                        Headless Hatari otherwise runs in REAL TIME: 500 vblanks
        is ten emulated seconds and ten wall-clock seconds. With it the same 500 vblanks take about
        0.3 s (measured: 1,450-2,000 VBL/s). It changes no emulated behaviour — the emulator still
        executes every cycle of every frame — only how fast the host feeds it.
  --frameskips 0                           ...but under fast-forward Hatari stops RENDERING every
        frame, and `screenshot` grabs the last RENDERED surface. Without this a capture returns
        whichever frame happened to be drawn and no two runs agree.
  --statusbar off --drive-led off          Both draw emulator chrome INSIDE the photographed area.
        The drive LED is the one that matters: a coloured rectangle in the top-right border that
        appears only when a side touches the disk, and whose extra colours push Hatari's PNG writer
        from a palette image to a truecolour one — after which two captures can never match byte for
        byte whatever the pixels do.
  --disk-a <image> --protect-floppy off    A disk in drive A on every run, so the boot's floppy probe
        takes the same path every time. An empty drive is a different boot, not a cleaner one.
  -c hatari-machine.cfg                    ...AND THE COMMAND LINE IS NOT THE WHOLE MACHINE. Hatari
        reads a configuration file before it parses any of the above — $HOME/.config/hatari/hatari.cfg,
        or, WITH NO HOME IN THE ENVIRONMENT, `hatari.cfg` IN THE CURRENT DIRECTORY — and everything in
        it that no flag here overrides is part of the machine. MEASURED: a four-line `hatari.cfg`
        dropped in this directory (`[Screen] bUseExtVdiResolutions = TRUE`) moved the boot metric from
        461/1534 to 479/1340, took the screen from three colours to two and changed the pinned RAM,
        with nothing on the command line to say so. `-c` is spelled FIRST so every flag after it still
        wins, and the committed file names the settings that have no flag here.

WHAT A RUN IS DRIVEN BY. A `--parse` file, whose commands all execute at STARTUP, arming a
breakpoint whose own `:file` defers the real work to the moment it fires. A memory breakpoint cannot
be armed at startup at all — at power-on Hatari has not sized RAM and refuses a condition on a RAM
address — so a ledger watch is armed from inside a VBL breakpoint's action file.

AND `--machine` RESETS THE CPU. MEASURED with TOSBENCH: `--cpuclock 32` BEFORE `--machine st` does
nothing (Bconout = 155 ticks, the 8 MHz reading) and the same flag AFTER it quarters the workload
(38 ticks). So the machine flag is not one setting among many — it re-seeds the CPU type, clock and
blitter from the model's defaults, and anything meant to override them has to come after it.

AND STDIN IS /dev/null, WHICH IS NOT COSMETIC: when `--run-vbls` expires Hatari enters its debugger
and READS A COMMAND. With a terminal on stdin it sits there for ever, which is exactly how three of
this file's own development runs hung. With /dev/null the read is EOF and the emulator quits.
"""
import hashlib
import struct
import subprocess
import sys
from pathlib import Path

import cdefines

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "tools"))

from hatari_headless import headless_environment, log_faults      # noqa: E402  (sys.path, above)

HATARI = "hatari"
ORIGINAL_ROM = REPO / "tools" / "hatari" / "TOS102US.img"
REBUILT_ROM = HERE / "build" / "TOS102RC.IMG"
BLANK_DISK = HERE / "build" / "BLANK.ST"
OUT = HERE / "out"
GOLDEN = HERE / "golden"
# Tracked, not generated: it is part of the machine's definition, so it is read by every run and
# reviewed like the flags above it.
MACHINE_CONFIG = HERE / "hatari-machine.cfg"

MACHINE = "st"
MEMSIZE_MB = 1
MONITOR = "rgb"

# A TOS ROM carries its version as a BCD word at offset 2; how long a TOS 1.0x image is, is the
# rebuilt ROM's own ROM_BYTES — the same number, read from the header the ROM is built from.
TOS_VERSION_OFFSET = 2
TOS_ROM_BYTES = cdefines.defines(HERE / "romdefs.h")["ROM_BYTES"]

# A capture of a screen nothing painted is one colour; anything above this is a picture. Every
# driver here asks the same question of its screenshot, so the threshold is asked once.
BLANK_SCREEN_COLOURS = 1

# Appended to every log this module writes, so a later reader can see how the emulator exited
# without having been the one to launch it.
EXIT_STATUS_PREFIX = "-- hatari exit status: "


def refuse(message):
    raise SystemExit(f"REFUSED: {message}")


def require_files(*wanted):
    """Refuse, naming all of them, unless every (path, what it is) pair exists.

    ALL of them: a driver that stops at the first missing file makes a reader run it three times to
    learn that three things are not built.
    """
    missing = [f"{path} does not exist — {why}" for path, why in wanted if not Path(path).is_file()]
    if missing:
        refuse("\n    ".join(missing))


def capture_prefix(mode, requested, default):
    """The path prefix a capture writes under, refusing `--out` in a mode that does not write one.

    `golden` and `compare` write to fixed places — the golden is the golden, and a comparison is
    against it — so `--out` handed to either is a request the driver cannot honour, and taking it
    in silence leaves a reader looking for files somewhere nothing was ever written.
    """
    if requested is None:
        return default
    if mode != "capture":
        refuse(f"--out names where a capture is written and `{mode}` writes no capture")
    return requested


def file_identity(path):
    """What a capture records about a file that was part of the instrument: name, size and sha256.

    The NAME and not the path: a golden is a tracked file, and an absolute path in one is a
    statement about one person's disk that every later reader has to diff around.
    """
    data = Path(path).read_bytes()
    return {"name": Path(path).name, "bytes": len(data), "sha256": sha256_bytes(data)}


def rom_identity(rom):
    """`file_identity` plus the version word, and a refusal for an image of the wrong length."""
    image = Path(rom).read_bytes()
    if len(image) != TOS_ROM_BYTES:
        refuse(f"{rom} is {len(image)} bytes; a TOS 1.0x ROM is {TOS_ROM_BYTES}")
    version = struct.unpack_from(">H", image, TOS_VERSION_OFFSET)[0]
    return dict(file_identity(rom), version=f"{version >> 8:x}.{version & 0xFF:02x}")


def instrument_identity(rom, disk, program=None):
    """Everything a reading was taken WITH: the ROM under test, the floppy in drive A, and the
    program on it when the driver runs one.

    A comparison against a golden is a statement about the ROM, and it is only that if everything
    else is the same object it was. Rebuilding a .PRG changes what the machine executes as surely as
    rebuilding the ROM does, and without this the driver would report the difference as the ROM's.
    """
    identity = {"rom": rom_identity(rom), "disk": file_identity(disk)}
    if program is not None:
        identity["program"] = file_identity(program)
    return identity


def _identity_text(identity):
    if identity is None:
        return "absent"
    return f"{identity['name']} ({identity['bytes']} bytes, sha256 {identity['sha256'][:16]})"


def instrument_differences(reference, current):
    """How the instrument moved since the golden — everything in it BUT the ROM, which is the thing
    under test and is expected to differ."""
    if reference is None:
        return ["the golden carries no instrument identity: it was cut before this check existed, "
                "so nothing can say it was taken with these floppies — re-cut it (`make golden`)"]
    return [f"the {part} is {_identity_text(current.get(part))} and the golden was taken with "
            f"{_identity_text(reference.get(part))}"
            for part in ("disk", "program") if reference.get(part) != current.get(part)]


def machine_arguments(rom, disk, run_vbls):
    """The whole Hatari command line except the `--parse` file — see the module docstring."""
    return [
        HATARI,
        # First, so that every flag below still overrides it — and so that whatever a hatari.cfg in
        # $HOME or in the current directory says about these settings is overwritten rather than run.
        "-c", str(MACHINE_CONFIG),
        "--tos", str(rom),
        "--machine", MACHINE, "--memsize", str(MEMSIZE_MB), "--monitor", MONITOR,
        "--sound", "off",
        "--patch-tos", "off", "--fast-boot", "off", "--timer-d", "off",
        "--fast-forward", "on", "--frameskips", "0",
        "--statusbar", "off", "--drive-led", "off", "--confirm-quit", "off",
        "--disk-a", str(disk), "--protect-floppy", "off",
        "--run-vbls", str(run_vbls),
    ]


def boot(rom, disk, run_vbls, parse_file, log_path):
    """One headless boot. Returns Hatari's exit status; the log is written to `log_path`.

    A run whose log carries a fault marker (a bus error, an address error, a halted CPU, a file
    Hatari could not open) is refused here rather than reported by its caller: every driver in this
    directory would otherwise have to remember to ask, and a capture taken after a bus error looks
    exactly like a capture taken after a boot.
    """
    require_files((MACHINE_CONFIG, "the machine configuration this directory commits"))
    command = machine_arguments(rom, disk, run_vbls) + ["--parse", str(parse_file)]
    done = subprocess.run(command, env=headless_environment(), stdin=subprocess.DEVNULL,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    Path(log_path).write_text(f"{done.stdout}\n{EXIT_STATUS_PREFIX}{done.returncode}\n")
    faults = log_faults(log_path)
    if faults:
        refuse(f"the run under {rom} faulted:\n    " + "\n    ".join(faults) + f"\n  see {log_path}")
    return done.returncode


def breakpoint_script(path, *commands, tail="cont"):
    """Write one breakpoint's action file and return its PATH.

    NOT named `action_file`: tools/hatari_headless.py has a function of that name which takes a
    directory and a name and returns the `:file` CLAUSE, and two functions with one name that differ
    in both their arguments and their answer is a mistake waiting for the reader who imports the
    other one.

    These are HOST paths the debugger reads; they are deliberately not on any emulated drive, where
    the program under test could see them. The path is returned rather than the `:file` clause
    because the outermost file is handed to `--parse`, which wants the path alone — and a helper
    that returned the clause made exactly that mistake once, with Hatari reporting
    `debugger input file ':file /...' missing`.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(command + "\n" for command in commands) + tail + "\n")
    return path


def file_clause(path):
    """The breakpoint option that runs an action file when the breakpoint fires."""
    return f":file {path}"


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()
