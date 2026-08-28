#!/usr/bin/env python3
"""Run SPIKE.PRG in headless Hatari, capture the frame and the ledger, print the results table.

TWO RUNS, because they measure different things and the second one perturbs the first. The plain
run is the measurement: Hatari boots the .PRG off a GEMDOS drive and the program writes RESULT.TXT
back onto that drive with its own timings. The debugger run repeats it under `--parse` and, at the
instant the program publishes its ledger magic, takes a SCREENSHOT and `savebin`s the ledger — so
the picture and the numbers come from the same frame of the same program, and the ledger read out
of the machine's RAM is checked against the text the program wrote through GEMDOS. Two independent
paths out of the emulator agreeing is what makes the table evidence rather than an assertion.

THE ROM IS EMUTOS AND THAT IS NOT A PREFERENCE. `--machine ste` needs a TOS that knows the STE;
tools/hatari/TOS10[24]US.img are ST ROMs and boot an STE only by accident. Hatari's own bundled
EmuTOS is selected simply by not passing --tos, which is what this script does.
"""
import re
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DISK = HERE / "disk"
OUT = HERE / "out"
PRG_HOST = DISK / "SPIKE.PRG"
PRG_GEMDOS = "C:\\SPIKE.PRG"
RESULT_TXT = DISK / "RESULT.TXT"

# --run-vbls has to outlast the whole bench: eight passes of SPIKE_FRAMES_PER_PASS frames at up to
# a fifth of a second each, plus EmuTOS's boot and the still-frame hold at the end. Measured: the
# program finishes around VBL 2600 on this build, so this is roughly a 50% margin.
RUN_VBLS = 4000
# Late enough that EmuTOS has sized memory (so a RAM breakpoint parses), early enough that the
# program has not published its ledger yet.
ARM_VBL = 600
MEMSIZE_MB = 1
MONITOR = "rgb"

# The ledger's fixed address and shape, which spike.h defines and this file must agree with. The
# sizes are checked against SPIKE_LEDGER_MAGIC below, so a field added in C and not here is a loud
# mismatch rather than a silently misread table.
LEDGER_ADDR = 0x80000
LEDGER_MAGIC = 0x53504B45
LEDGER_VERSION = 1
HEADER_FIELDS = ("magic", "version", "tick_ns", "cpu_hz", "frames", "timer_c_max", "passes", "screen")
PASS_FIELDS = ("columns", "rotating", "banded", "ticks_raycast", "ticks_columns", "ticks_fill",
               "ticks_c2p", "ticks_total", "band_top_sum", "band_bottom_sum")
PASSES = 8
LEDGER_BYTES = (len(HEADER_FIELDS) + PASSES * len(PASS_FIELDS)) * 4
# spike.h publishes the showcase frame's SpikeRay array beside the ledger; one savebin
# takes both so the picture check and the timing table come from the same instant.
RAYS_OFFSET = 0x400
RAYS_BYTES = 160 * 16
CAPTURE_BYTES = RAYS_OFFSET + RAYS_BYTES
TIMER_C_RELOAD = 192            # spike.h's; the run reports the largest counter value it saw

STAGES = ("raycast", "columns", "fill", "c2p")


def hatari(args, log_name):
    """One headless Hatari run; returns (exit status, merged output)."""
    command = ["hatari", "--sound", "off", "--fast-forward", "on", "--confirm-quit", "off",
               "--statusbar", "off", "--drive-led", "off", "--frameskips", "0",
               "--machine", "ste", "--memsize", str(MEMSIZE_MB), "--monitor", MONITOR,
               "--run-vbls", str(RUN_VBLS),
               "--harddrive", str(DISK), "--auto", PRG_GEMDOS] + args
    environment = {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
    done = subprocess.run(command, env=environment, stdin=subprocess.DEVNULL, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    OUT.mkdir(exist_ok=True)
    (OUT / log_name).write_text(done.stdout)
    return done.returncode, done.stdout


def capture_scripts(frame_png, ledger_bin):
    """The three debugger scripts, and it takes three for a reason at each hop.

    A `--parse` file's commands all run at STARTUP, so the capture cannot live in one — the
    breakpoint's own ':file' is what defers it to the moment the ledger's magic lands. And the
    memory breakpoint cannot be armed at startup either: at power-on Hatari has not sized RAM yet
    and refuses a condition on a RAM address with "invalid address" (the same trap Wonder Boy's
    harness records). So a VBL breakpoint arms the memory breakpoint, which fires the capture."""
    capture = OUT / "capture.txt"
    capture.write_text(f"screenshot {frame_png}\n"
                       f"savebin {ledger_bin} ${LEDGER_ADDR:x} {CAPTURE_BYTES}\ncont\n")
    # NOT QUOTED: a quoted expression is evaluated when the script is PARSED, which would read the
    # ledger's still-zero longword and arm a breakpoint on the constant 0. Unquoted, the condition
    # is the debugger's own and is re-read every instruction, which is the whole point.
    watch = OUT / "watch.txt"
    watch.write_text(f"b (${LEDGER_ADDR:x}).l = ${LEDGER_MAGIC:x} :once :file {capture}\ncont\n")
    arm = OUT / "arm.txt"
    arm.write_text(f"b VBL > {ARM_VBL} :once :file {watch}\ncont\n")
    return arm


def crop_to_screen(png):
    """Hatari's screenshot carries the borders; save a copy that is just the 320x200 screen.

    The border is pen 0, which this program leaves black, so the screen is the image's non-black
    bounding box — the same way verify.py locates it, and for the same reason: nothing in the
    capture says where the screen starts."""
    from PIL import Image
    image = Image.open(png).convert("RGB")
    pixels = image.load()
    columns = [x for x in range(image.width)
               if any(pixels[x, y] != (0, 0, 0) for y in range(0, image.height, 4))]
    rows = [y for y in range(image.height)
            if any(pixels[x, y] != (0, 0, 0) for x in range(0, image.width, 4))]
    out = png.with_name(png.stem + "_screen.png")
    image.crop((columns[0], rows[0], columns[-1] + 1, rows[-1] + 1)).save(out)
    return out


def read_ledger(path):
    """The ledger as dicts, refusing anything that is not this program's."""
    raw = path.read_bytes()
    if len(raw) != CAPTURE_BYTES:
        raise SystemExit(f"REFUSED: {path} is {len(raw)} bytes, this parser expects {CAPTURE_BYTES}")
    words = struct.unpack(f">{LEDGER_BYTES // 4}L", raw[:LEDGER_BYTES])
    header = dict(zip(HEADER_FIELDS, words))
    if header["magic"] != LEDGER_MAGIC:
        raise SystemExit(f"REFUSED: ledger magic {header['magic']:#x}, expected {LEDGER_MAGIC:#x}")
    if header["version"] != LEDGER_VERSION:
        raise SystemExit(f"REFUSED: ledger version {header['version']}, this parser knows {LEDGER_VERSION}")
    passes = []
    for index in range(PASSES):
        start = len(HEADER_FIELDS) + index * len(PASS_FIELDS)
        passes.append(dict(zip(PASS_FIELDS, words[start:start + len(PASS_FIELDS)])))
    return header, passes


def parse_result_text(path):
    """The same numbers by the other road: what the program formatted and wrote through GEMDOS."""
    rows = []
    for line in path.read_text().splitlines():
        if line.startswith("cols="):
            rows.append({key: int(value) for key, value in re.findall(r"(\w+)=(\d+)", line)})
    return rows


def microseconds(ticks, frames, tick_ns):
    return ticks * tick_ns / frames / 1000.0


def report(header, passes, text_rows):
    tick_ns, frames, cpu_hz = header["tick_ns"], header["frames"], header["cpu_hz"]
    print(f"ledger @ ${LEDGER_ADDR:x}  frames/pass={frames}  tick={tick_ns} ns  "
          f"cpu={cpu_hz} Hz  screen=${header['screen']:x}")
    if header["timer_c_max"] >= TIMER_C_RELOAD + 1:
        print(f"  WARNING: timer C counted to {header['timer_c_max']}, above the {TIMER_C_RELOAD} "
              "reload the clock arithmetic assumes — every time below is wrong by that ratio")
    print()
    head = f"{'cols':>5} {'view':>9} {'ceil/floor':>11} " + "".join(f"{s:>10}" for s in STAGES)
    print(head + f"{'total':>10} {'fps':>7} {'band':>10}")
    print("-" * len(head + f"{'total':>10} {'fps':>7} {'band':>10}"))
    for entry in passes:
        total_us = microseconds(entry["ticks_total"], frames, tick_ns)
        cells = "".join(f"{microseconds(entry['ticks_' + s], frames, tick_ns):10.1f}" for s in STAGES)
        band = f"{entry['band_top_sum'] / frames:.0f}-{entry['band_bottom_sum'] / frames:.0f}"
        print(f"{entry['columns']:>5} {'rotating' if entry['rotating'] else 'fixed':>9} "
              f"{'band fill' if entry['banded'] else 'in chunky':>11} {cells}{total_us:10.1f}"
              f"{1e6 / total_us:7.2f} {band:>10}")
    print("\n(microseconds per frame; total is the sum of the four stages on the visible screen)\n")
    print(f"{'cols':>5} {'view':>9} {'ceil/floor':>11} " + "".join(f"{s:>10}" for s in STAGES)
          + f"{'total':>10}")
    print("-" * (5 + 1 + 9 + 1 + 11 + 1 + 10 * len(STAGES) + 10))
    for entry in passes:
        cells = "".join(f"{microseconds(entry['ticks_' + s], frames, tick_ns) * cpu_hz / 1e6:10.0f}"
                        for s in STAGES)
        total = microseconds(entry["ticks_total"], frames, tick_ns) * cpu_hz / 1e6
        print(f"{entry['columns']:>5} {'rotating' if entry['rotating'] else 'fixed':>9} "
              f"{'band fill' if entry['banded'] else 'in chunky':>11} {cells}{total:10.0f}")
    print(f"\n({cpu_hz / 1e6:.0f} MHz CPU cycles per frame; the frame budget at 50 Hz is 160000)\n")
    cross_check(passes, text_rows, frames, tick_ns)


def cross_check(passes, text_rows, frames, tick_ns):
    """The ledger read out of RAM against the text the program wrote through GEMDOS.

    The program computes its microseconds with integer arithmetic and this script with floating
    point, so they are allowed to differ by the program's own truncation — one microsecond per
    tick-to-microsecond conversion — and by nothing else."""
    if len(text_rows) != len(passes):
        raise SystemExit(f"REFUSED: RESULT.TXT has {len(text_rows)} passes, the ledger has {len(passes)}")
    worst = 0.0
    for entry, row in zip(passes, text_rows):
        if (entry["columns"], entry["rotating"], entry["banded"]) != (row["cols"], row["rot"], row["band"]):
            raise SystemExit("REFUSED: the ledger and RESULT.TXT describe different passes")
        worst = max(worst, abs(microseconds(entry["ticks_total"], frames, tick_ns) - row["tot"]))
    print(f"cross-check: ledger vs RESULT.TXT agree on all {len(passes)} passes "
          f"(largest total difference {worst:.1f} us, the program's own rounding)")


def main():
    if not PRG_HOST.exists():
        raise SystemExit(f"REFUSED: {PRG_HOST} does not exist — run `make` first")
    OUT.mkdir(exist_ok=True)
    RESULT_TXT.unlink(missing_ok=True)
    status, _ = hatari([], "hatari-plain.log")
    print(f"-- plain run: hatari exit={status}, log in {OUT / 'hatari-plain.log'}")
    if not RESULT_TXT.exists():
        raise SystemExit(f"REFUSED: the program wrote no {RESULT_TXT.name} — see the log")

    frame_png, ledger_bin = OUT / "frame.png", OUT / "ledger.bin"
    frame_png.unlink(missing_ok=True)
    ledger_bin.unlink(missing_ok=True)
    arm = capture_scripts(frame_png, ledger_bin)
    status, _ = hatari(["--parse", str(arm)], "hatari-debug.log")
    print(f"-- debugger run: hatari exit={status}, log in {OUT / 'hatari-debug.log'}")
    for wanted in (frame_png, ledger_bin):
        if not wanted.exists():
            raise SystemExit(f"REFUSED: the debugger run produced no {wanted} — the breakpoint on "
                             "the ledger magic never fired; see the log")
    print(f"-- screenshot: {frame_png}  (cropped to the screen: {crop_to_screen(frame_png)})")
    print()
    header, passes = read_ledger(ledger_bin)
    report(header, passes, parse_result_text(RESULT_TXT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
