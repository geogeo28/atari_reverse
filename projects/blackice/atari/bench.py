#!/usr/bin/env python3
"""Run BLACKICE.PRG in headless Hatari, capture the frame and the ledger, print the results table.

TWO RUNS, because they measure different things and the second one perturbs the first. The plain
run is the measurement: Hatari boots the .PRG off a GEMDOS drive and the program writes BENCH.TXT
back onto that drive with its own timings. The debugger run repeats it under `--parse` and, at the
instant the program publishes its ledger magic, takes a SCREENSHOT and `savebin`s the ledger — so
the picture and the numbers come from the same frame of the same program, and the ledger read out
of the machine's RAM is checked against the text the program wrote through GEMDOS. Two independent
paths out of the emulator agreeing is what makes the table evidence rather than an assertion.

THE MAGIC IS WRITTEN LAST, which is the whole reason a breakpoint on it is safe: when the longword
at BI_LEDGER_ADDR reads 'BLK1' every field behind it has already landed, so the savebin cannot
catch a half-written table. Nothing else in this script would notice if it did.

THE ROM IS EMUTOS AND THAT IS NOT A PREFERENCE. `--machine ste` needs a TOS that knows the STE;
tools/hatari/TOS10[24]US.img are ST ROMs and boot an STE only by accident. Hatari's own bundled
EmuTOS is selected simply by not passing --tos, which is what this script does.

This file also owns the two things verify.py must agree with byte for byte — the ledger's shape and
where the ST's screen sits inside Hatari's bordered screenshot — so that there is exactly one
definition of each and a checker cannot drift from the harness that produced its inputs.
"""
import re
import math
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DISK = HERE / "disk"
OUT = HERE / "out"
# BENCH.PRG, not BLACKICE.PRG: atari/Makefile builds two programs from one main.c, and only the
# -DBLACKICE_BENCH twin runs the fixture passes and publishes the ledger. BLACKICE.PRG is the
# playable game — it takes joystick input and never terminates on its own, so it would hang here.
PRG_HOST = DISK / "BENCH.PRG"
PAK_HOST = DISK / "BLACKICE.PAK"          # both programs open it as "\BLACKICE.PAK"
PRG_GEMDOS = "C:\\BENCH.PRG"
BENCH_TXT = DISK / "BENCH.TXT"

# --run-vbls has to outlast the whole bench: every pass at up to three VBLs a frame, plus EmuTOS's
# boot and the still-frame hold at the end. Fast-forward makes an unused margin nearly free, and
# the useful part of the run ends at the ledger breakpoint anyway, so this is deliberately generous
# rather than tuned — a bench that is cut off mid-pass writes no BENCH.TXT and fails loudly.
RUN_VBLS = 14000
# Late enough that EmuTOS has sized memory (so a RAM breakpoint parses), early enough that the
# program has not published its ledger yet.
ARM_VBL = 600
MEMSIZE_MB = 1
MONITOR = "rgb"

# ---------------------------------------------------------------- the ledger -----------------
# plat.h's BI_LEDGER_*: a FIXED absolute address, so the debugger script can savebin it without
# knowing where GEMDOS loaded the program. Every field is a 32-bit big-endian unsigned.
LEDGER_ADDR = 0xC0000
LEDGER_MAGIC = 0x424C4B31       # 'BLK1'
LEDGER_VERSION = 1

# Header, in order, at LEDGER_ADDR + 0.
HEADER_FIELDS = ("magic", "version", "tick_ns", "cpu_hz", "pass_count", "timer_c_max",
                 "stage_count", "capture_pass", "capture_frame", "cast_mismatches")
HEADER_BYTES = len(HEADER_FIELDS) * 4                       # 40

# One measured pass: an 8-byte NUL-padded ASCII name, then longwords, then the per-stage triples.
PASS_NAME_BYTES = 8
PASS_FIELDS = ("columns", "frames", "band_top_sum", "band_bottom_sum", "sprite_px_sum",
               "sprite_count_sum", "total_min", "total_sum", "total_max",
               "wall_rows_sum", "clipped_columns_sum")
PASS_FIELDS_OFFSET = PASS_NAME_BYTES                        # 8
PASS_HEADER_BYTES = 64                                      # name + fields + reserved[3]
STAGE_TRIPLE = ("min", "sum", "max")
STAGE_TRIPLE_BYTES = len(STAGE_TRIPLE) * 4                  # 12

# The stage names are HERE and not in the target: the ledger carries only a count, so a stage added
# to main.c and not to this tuple is a stage_count mismatch and a loud refusal, never a table whose
# columns have quietly slid one to the left.
STAGES = ("sim", "cast", "columns", "sprites", "fill", "c2p", "hud")
PASS_BYTES = PASS_HEADER_BYTES + len(STAGES) * STAGE_TRIPLE_BYTES   # 64 + 84 == 148

# A fixed, generous window: reading a constant number of bytes keeps the debugger script free of
# anything it would have to compute from the ledger it has not read yet. read_ledger() then refuses
# if the pass table the header describes does not fit inside what was actually captured.
CAPTURE_BYTES = 4096

# plat.h's TIMER_C_RELOAD. The counter is LOADED with the reload value, so reading exactly it is
# normal and is what ../spike/REPORT.md observed ("read the counter to a maximum of 192, confirming
# the 192 reload the arithmetic assumes"); only a value ABOVE it means this
# TOS programmed timer C differently and every microsecond in the ledger is wrong by that ratio.
TIMER_C_RELOAD = 192

# ---------------------------------------------------------------- the budgets ----------------
# game_consts.h's RENDER_COLUMNS_HIGH / _LOW, and DESIGN 17's cycle budget for each: three 50 Hz
# VBLs for a 160-column frame, two for an 80-column one.
RENDER_COLUMNS_HIGH = 160
RENDER_COLUMNS_LOW = 80
PAL_VBL_HZ = 50                 # the PAL vertical blank, and so the flip lock's granularity
VBL_PERIOD_US = 1e6 / PAL_VBL_HZ
VBL_CYCLES = 160000                                         # 8 MHz / 50 Hz
BUDGET_CYCLES = {RENDER_COLUMNS_HIGH: 3 * VBL_CYCLES, RENDER_COLUMNS_LOW: 2 * VBL_CYCLES}

# ---------------------------------------------------------------- the screen -----------------
# game_consts.h's SCREEN_*: the ST screen the emulator draws inside its borders, and the top part
# of it that the engine renders (the bottom SCREEN_HUD_LINES are the platform's static HUD).
SCREEN_W = 320
SCREEN_H = 200
SCREEN_WINDOW_LINES = 160
BORDER_RGB = (0, 0, 0)                  # pen 0, which this program leaves black

# Where the screen's vertical registration is anchored: the two full-width solid rules in the
# shipped HUD strip (art/out/native/hud_strip.png rows 0 and 8 == screen lines 160 and 168).
# This is a property of the ART, not of the platform, so a redraw of the strip that removes
# either rule makes locate_screen REFUSE rather than mis-register — the failure we want.
# Their colours are deliberately not named: the test is that each row is uniform, neither is the
# border's black, and the two differ from each other. That survives a re-authored palette (which
# this project does re-author) while still pinning the registration, because no other pair of
# screen lines eight apart in a rendered frame is two different full-width solids.
HUD_RULE_LINES = (SCREEN_WINDOW_LINES, SCREEN_WINDOW_LINES + 8)

# The program's own microsecond figures are integer-truncated from its tick counts, so the text it
# writes may sit up to one microsecond below this script's floating-point value, and nowhere else.
# The target converts timer units to microseconds in two halves — whole ticks per frame and the
# remainder — so its answer can be up to one microsecond low in EACH, and rounding can put it half a
# microsecond high. See ticks_to_us in atari/main.c for why the conversion is split at all.
TRUNCATION_US = 2.0


def refuse(message):
    raise SystemExit(f"REFUSED: {message}")


# Appended to every Hatari log so a later reader — verify.py's health check — can see how the
# emulator exited without having been the one to launch it.
HATARI_STATUS_PREFIX = "-- hatari exit status: "


def hatari(args, log_name, auto=True):
    """One headless Hatari run; returns (exit status, merged output).

    `auto=False` boots the same machine off the same drive but starts no program, which is how
    verify.py gets a baseline for what EmuTOS does to the machine all by itself."""
    command = ["hatari", "--sound", "off", "--fast-forward", "on", "--confirm-quit", "off",
               "--statusbar", "off", "--drive-led", "off", "--frameskips", "0",
               "--machine", "ste", "--memsize", str(MEMSIZE_MB), "--monitor", MONITOR,
               "--run-vbls", str(RUN_VBLS), "--harddrive", str(DISK)]
    command += (["--auto", PRG_GEMDOS] if auto else []) + args
    environment = {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy",
                   "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
    done = subprocess.run(command, env=environment, stdin=subprocess.DEVNULL, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    OUT.mkdir(exist_ok=True)
    (OUT / log_name).write_text(f"{done.stdout}\n{HATARI_STATUS_PREFIX}{done.returncode}\n")
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


def uniform_row_colour(image, left, right, row):
    """The single RGB of a screen-wide row of the screenshot, or None if it is not one colour."""
    colours = image.crop((left, row, right, row + 1)).getcolors(maxcolors=2)
    return colours[0][1] if colours and len(colours) == 1 else None


def hud_rules_found(image, left, right, top, scale):
    """Do the HUD's two solid rules sit where a screen at `top` would put them?"""
    colours = [uniform_row_colour(image, left, right, top + line * scale) for line in HUD_RULE_LINES]
    if any(colour is None or colour == BORDER_RGB for colour in colours):
        return False
    return len(set(colours)) == len(colours)


def locate_screen(image):
    """Where the ST's 320x200 screen sits inside Hatari's screenshot; returns (left, top, scale).

    Nothing in the capture says where the screen starts, and the answer moves with the emulator's
    border and zoom settings, so it is measured rather than assumed.

    HORIZONTALLY that is easy: the border is pen 0, which this program leaves black, and the HUD's
    top rule spans all 320 columns, so the non-black bounding box is exactly as wide as the screen.

    VERTICALLY neither edge of that box can be trusted. The top of the render window is the void,
    which is pen 0 as well, and the HUD strip's LAST line (screen line 199) is entirely index 0 in
    the shipped art — so both edges float with what happens to be drawn. Instead every vertical
    placement that would contain the drawn area is enumerated, and the one that puts the HUD's two
    solid rules where they belong wins. Exactly one must; anything else is refused, because a
    silently mis-registered screen turns verify.py's pixel check into noise."""
    rgb = image.convert("RGB")
    box = rgb.getbbox()
    if box is None:
        refuse("the screenshot is entirely black — the program drew nothing")
    left, drawn_top, right, drawn_bottom = box
    width = right - left
    if width == 0 or width % SCREEN_W:
        refuse(f"the drawn area is {width} px wide, not a whole multiple of the {SCREEN_W}-pixel "
               "screen — the borders are not black, or this is not a low-resolution frame")
    scale = width // SCREEN_W
    height = SCREEN_H * scale
    # The screen must fit the image and contain every drawn pixel, and — because a zoomed
    # screenshot repeats each ST line `scale` times — the first drawn row must sit a whole number
    # of ST lines below the screen's top edge. Without that last constraint the HUD rules alone
    # cannot separate a placement from the one a sub-pixel below it, which lands on the same block.
    span = range(max(0, drawn_bottom - height), min(drawn_top, image.height - height) + 1)
    placements = [top for top in span if (drawn_top - top) % scale == 0]
    found = [top for top in placements if hud_rules_found(rgb, left, right, top, scale)]
    if len(found) != 1:
        refuse(f"{len(found)} of the {len(placements)} possible screen placements put the HUD's "
               f"rules at screen lines {HUD_RULE_LINES[0]} and {HUD_RULE_LINES[1]} "
               f"(found {found}) — the HUD was not drawn, or the strip art no longer has them")
    return left, found[0], scale


def crop_to_screen(png):
    """Save a copy of the screenshot that is just the ST screen, borders removed."""
    from PIL import Image
    image = Image.open(png)
    left, top, scale = locate_screen(image)
    out = png.with_name(png.stem + "_screen.png")
    image.crop((left, top, left + SCREEN_W * scale, top + SCREEN_H * scale)).save(out)
    return out


def read_pass(raw, offset, stage_count):
    """One pass record, as a dict; `raw` is the whole captured window."""
    name = raw[offset:offset + PASS_NAME_BYTES].split(b"\0")[0].decode("ascii", "replace")
    values = struct.unpack_from(f">{len(PASS_FIELDS)}L", raw, offset + PASS_FIELDS_OFFSET)
    entry = dict(zip(PASS_FIELDS, values), name=name)
    entry["stages"] = {}
    for index, stage in enumerate(STAGES[:stage_count]):
        triple = struct.unpack_from(f">{len(STAGE_TRIPLE)}L", raw,
                                    offset + PASS_HEADER_BYTES + index * STAGE_TRIPLE_BYTES)
        entry["stages"][stage] = dict(zip(STAGE_TRIPLE, triple))
    return entry


def read_ledger(path):
    """The ledger as (header, passes), refusing anything that is not this program's.

    Every refusal here is a shape disagreement between main.c and this file. None of them are
    recoverable by guessing, because a mis-sized record does not fail — it silently reports another
    field's bytes as a timing."""
    raw = path.read_bytes()
    if len(raw) != CAPTURE_BYTES:
        refuse(f"{path} is {len(raw)} bytes, this parser captured and expects {CAPTURE_BYTES}")
    header = dict(zip(HEADER_FIELDS, struct.unpack_from(f">{len(HEADER_FIELDS)}L", raw, 0)))
    if header["magic"] != LEDGER_MAGIC:
        refuse(f"ledger magic {header['magic']:#x}, expected {LEDGER_MAGIC:#x}")
    if header["version"] != LEDGER_VERSION:
        refuse(f"ledger version {header['version']}, this parser knows {LEDGER_VERSION}")
    if header["stage_count"] != len(STAGES):
        refuse(f"the ledger has {header['stage_count']} stages, this parser names {len(STAGES)} "
               f"({', '.join(STAGES)}) — main.c and bench.py disagree about the stage list")
    if header["pass_count"] == 0:
        refuse("the ledger reports zero passes")
    needed = HEADER_BYTES + header["pass_count"] * PASS_BYTES
    if needed > CAPTURE_BYTES:
        refuse(f"{header['pass_count']} passes of {PASS_BYTES} bytes need {needed} bytes, past the "
               f"{CAPTURE_BYTES}-byte window this script captures — raise CAPTURE_BYTES")
    passes = [read_pass(raw, HEADER_BYTES + index * PASS_BYTES, header["stage_count"])
              for index in range(header["pass_count"])]
    for entry in passes:
        if entry["frames"] == 0:
            refuse(f"pass {entry['name']!r} reports zero frames, so nothing can be averaged")
    if header["capture_pass"] >= header["pass_count"]:
        refuse(f"capture_pass {header['capture_pass']} is past the {header['pass_count']} passes")
    return header, passes


def parse_bench_text(path):
    """The same numbers by the other road: what the program formatted and wrote through GEMDOS.

    Read as latin-1 because a stray byte in a target-written file should show up in a comparison,
    not raise out of the decoder."""
    rows = []
    for line in path.read_text(encoding="latin-1").splitlines():
        if line.startswith("pass="):
            rows.append(dict(re.findall(r"(\w+)=([\w.+-]+)", line)))
    return rows


def text_name(row):
    """The pass name out of a BENCH.TXT row, whether it is `pass=WALK160` or `pass=0 name=WALK160`."""
    if "name" in row:
        return row["name"]
    return row["pass"] if not row["pass"].isdigit() else None


def microseconds(ticks, frames, tick_ns):
    return ticks * tick_ns / frames / 1000.0


def cycles(us, cpu_hz):
    return us * cpu_hz / 1e6


def stage_us(entry, header, stage, field="sum"):
    """Microseconds per frame for one stage. `sum` is the mean; `min`/`max` are single frames."""
    ticks = entry["stages"][stage][field]
    divisor = entry["frames"] if field == "sum" else 1
    return microseconds(ticks, divisor, header["tick_ns"])


def print_header(header):
    print(f"ledger @ ${LEDGER_ADDR:x}  passes={header['pass_count']}  tick={header['tick_ns']} ns  "
          f"cpu={header['cpu_hz']} Hz  capture=pass {header['capture_pass']} frame "
          f"{header['capture_frame']}")
    # cast.S is compared against src/raycast.c's render_cast on every frame of every pass; the
    # ledger carries how many RenderColumns disagreed. Anything but zero voids the run, whatever
    # the pixels say — a wrong column can hide behind a band the drawer never reaches.
    if header["cast_mismatches"]:
        refuse(f"the asm raycast disagreed with src/raycast.c on {header['cast_mismatches']} "
               "columns — the numbers below describe a renderer that is not the engine")
    print(f"  cast self-check: {header['cast_mismatches']} column(s) differ from src/raycast.c")
    if header["timer_c_max"] > TIMER_C_RELOAD:
        print(f"  WARNING: timer C counted to {header['timer_c_max']}, ABOVE the "
              f"{TIMER_C_RELOAD} reload the clock arithmetic assumes — this TOS programmed the "
              "timer differently and every microsecond below is wrong by that ratio")


def print_pass(header, entry, index):
    """One pass: the per-stage means in microseconds and in CPU cycles, then the whole frame."""
    tick_ns, cpu_hz, frames = header["tick_ns"], header["cpu_hz"], entry["frames"]
    mark = "  <- screenshot" if index == header["capture_pass"] else ""
    print(f"\n{entry['name']:<8} cols={entry['columns']:<4} frames={frames}{mark}")
    label_width = 12
    print(" " * label_width + "".join(f"{stage:>10}" for stage in STAGES) + f"{'sum':>10}")
    # THREE ROWS OF MICROSECONDS AND NOT ONE: the mean of a stage hides its spikes, and one of them
    # is not noise — the simulation rebuilds DESIGN 8.1's BFS distance field every eighth tick, so
    # its mean is a number no individual frame ever costs. min and max say so.
    means = [stage_us(entry, header, stage) for stage in STAGES]
    for row_label, field in (("us mean", "sum"), ("us min", "min"), ("us max", "max")):
        values = [stage_us(entry, header, stage, field) for stage in STAGES]
        cells = "".join(f"{value:10.1f}" for value in values)
        print(f"  {row_label:<{label_width - 2}}" + cells + f"{sum(values):10.1f}")
    cells = "".join(f"{cycles(value, cpu_hz):10.0f}" for value in means)
    print(f"  {'cycles':<{label_width - 2}}" + cells + f"{cycles(sum(means), cpu_hz):10.0f}")

    mean_us = microseconds(entry["total_sum"], frames, tick_ns)
    min_us = microseconds(entry["total_min"], 1, tick_ns)
    max_us = microseconds(entry["total_max"], 1, tick_ns)
    stage_sum_us = sum(stage_us(entry, header, stage) for stage in STAGES)
    # A raycaster's worst frame is what a flip lock sees, so the mean alone would flatter it.
    print(f"  whole frame  min {min_us:9.1f} us / {cycles(min_us, cpu_hz):8.0f} cyc"
          f"   mean {mean_us:9.1f} / {cycles(mean_us, cpu_hz):8.0f}"
          f"   max {max_us:9.1f} / {cycles(max_us, cpu_hz):8.0f}")
    if mean_us:
        print(f"  stages sum to {stage_sum_us:.1f} us of that mean "
              f"({stage_sum_us / mean_us * 100:.1f}% — the rest is unmeasured frame overhead)")
        mean_cycles = cycles(mean_us, cpu_hz)
        budget = BUDGET_CYCLES.get(entry["columns"])
        budget_text = (f"{mean_cycles / budget * 100:.1f}% of its own {budget}-cycle DESIGN 17 budget"
                       if budget else f"no DESIGN 17 budget is defined for {entry['columns']} columns")
        # TWO FRAME RATES, and the second is the one a player sees. The loop waits for the vertical
        # blank after every frame (DESIGN 17.3's flip lock), so the only rates on a 50 Hz machine are
        # 50 divided by a whole number of blanks. Quoting the work rate alone overstates every pass:
        # a 121,000 us frame does not deliver 8.3 fps, it delivers 50/7 = 7.1.
        blanks = max(1, math.ceil(mean_us / VBL_PERIOD_US))
        print(f"  budget       {budget_text},  {mean_cycles / VBL_CYCLES:.2f} x the "
              f"{VBL_CYCLES}-cycle 50 Hz frame,  {1e6 / mean_us:.2f} fps of work")
        print(f"  delivered    {PAL_VBL_HZ / blanks:.2f} fps at the flip lock "
              f"({blanks} blanks a frame), from a mean frame of {mean_us / 1000:.1f} ms")
    else:
        print("  WARNING: this pass measured a zero whole-frame total — the timer never advanced")
    print(f"  per frame    wall rows {entry['wall_rows_sum'] / frames:.0f}, "
          f"{entry['clipped_columns_sum'] / frames:.1f} columns clipped to the window,  "
          f"band {entry['band_top_sum'] / frames:.0f}-"
          f"{entry['band_bottom_sum'] / frames:.0f} rows,  "
          f"{entry['sprite_count_sum'] / frames:.1f} sprites,  "
          f"{entry['sprite_px_sum'] / frames:.0f} sprite pixels asked for")


def cross_check(header, passes, text_rows):
    """The ledger read out of RAM against the text the program wrote through GEMDOS.

    The program computes its microseconds with integer arithmetic and this script with floating
    point, so they are allowed to differ by the program's own truncation — under one microsecond
    per tick-to-microsecond conversion — and by nothing else. fps10 is reported rather than
    enforced: it is a second-order figure and how main.c derives it (from the truncated total or
    from the raw ticks) changes its last digit without meaning anything is wrong."""
    if len(text_rows) != len(passes):
        refuse(f"{BENCH_TXT.name} has {len(text_rows)} passes, the ledger has {len(passes)}")
    worst_key, worst_delta = None, 0.0
    for entry, row in zip(passes, text_rows):
        name = text_name(row)
        if name is not None and name != entry["name"]:
            refuse(f"the ledger's pass {entry['name']!r} is {name!r} in {BENCH_TXT.name}")
        for key, value in (("cols", entry["columns"]), ("frames", entry["frames"])):
            if int(row[key]) != value:
                refuse(f"pass {entry['name']!r}: {key}={row[key]} in {BENCH_TXT.name}, "
                       f"{value} in the ledger")
        wanted = {stage: stage_us(entry, header, stage) for stage in STAGES}
        wanted["tot"] = microseconds(entry["total_sum"], entry["frames"], header["tick_ns"])
        for key, exact in wanted.items():
            if key not in row:
                refuse(f"pass {entry['name']!r}: {BENCH_TXT.name} has no {key}= for this stage")
            delta = exact - int(row[key])
            if not -TRUNCATION_US < delta < TRUNCATION_US:
                refuse(f"pass {entry['name']!r}: {key}={row[key]} us in {BENCH_TXT.name} but "
                       f"{exact:.3f} us in the ledger — more than the program's own truncation")
            if delta > worst_delta:
                worst_key, worst_delta = f"{entry['name']}.{key}", delta
        if "fps10" in row and wanted["tot"]:
            implied = 1e6 / wanted["tot"] * 10
            if abs(implied - int(row["fps10"])) > 1.0:
                print(f"  note: pass {entry['name']!r} reports fps10={row['fps10']}, the ledger's "
                      f"total implies {implied:.1f}")
    print(f"\ncross-check: the ledger and {BENCH_TXT.name} agree on all {len(passes)} passes "
          f"(largest difference {worst_delta:.3f} us at {worst_key}, the program's own truncation)")


def report(header, passes, text_rows):
    print_header(header)
    for index, entry in enumerate(passes):
        print_pass(header, entry, index)
    print(f"\n(microseconds and {header['cpu_hz'] / 1e6:.0f} MHz cycles PER FRAME; stage rows are "
          "means, the whole-frame line carries the single best and worst frames)")
    cross_check(header, passes, text_rows)


def require_inputs():
    for wanted, why in ((PRG_HOST, "the program"), (PAK_HOST, "its asset pack")):
        if not wanted.exists():
            refuse(f"{wanted} does not exist — {why} is built by `make` in {HERE}")


def main():
    require_inputs()
    OUT.mkdir(exist_ok=True)
    # Deleted first so a stale file from an earlier build cannot be mistaken for this run's output.
    BENCH_TXT.unlink(missing_ok=True)
    status, _ = hatari([], "hatari-plain.log")
    print(f"-- plain run: hatari exit={status}, log in {OUT / 'hatari-plain.log'}")
    if not BENCH_TXT.exists():
        refuse(f"the program wrote no {BENCH_TXT.name} — see {OUT / 'hatari-plain.log'}")

    frame_png, ledger_bin = OUT / "frame.png", OUT / "ledger.bin"
    frame_png.unlink(missing_ok=True)
    ledger_bin.unlink(missing_ok=True)
    arm = capture_scripts(frame_png, ledger_bin)
    status, _ = hatari(["--parse", str(arm)], "hatari-debug.log")
    print(f"-- debugger run: hatari exit={status}, log in {OUT / 'hatari-debug.log'}")
    for wanted in (frame_png, ledger_bin):
        if not wanted.exists():
            refuse(f"the debugger run produced no {wanted} — the breakpoint on the ledger magic "
                   f"never fired; see {OUT / 'hatari-debug.log'}")
    print(f"-- screenshot: {frame_png}  (cropped to the screen: {crop_to_screen(frame_png)})")
    report(*read_ledger(ledger_bin), parse_bench_text(BENCH_TXT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
