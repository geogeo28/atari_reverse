#!/usr/bin/env python3
"""Prove the Atari frame is pixel-for-pixel the frame the portable C reference draws.

bench.py says how FAST the target draws; nothing in its numbers says the picture is RIGHT. This
file is the rendered-pixels surface: it re-runs the portable core on the host over the SAME level,
the SAME input script and the SAME frame the target captured, and compares the two pictures. The
host's renderer, c2p and pixel doubling are C the pytest suite already pins; the target's are
hand-written 68000. If the two agree on all 51,200 pixels of the render window, the asm is right.

TWO CHECKS, and splitting them is what makes a failure locatable rather than just red:

  PIXELS      every pixel of the top 320x160, compared by RGB. This is the column drawer, the
              sprite drawer, the shading, the c2p and the doubling all on trial at once, with no
              tolerance whatsoever: the same inputs must produce the same bits.

  SILHOUETTE  for each of the 320 screen columns, the first and last row that is not the void pen.
              This is the GEOMETRY alone — where the walls land — and it is reported separately
              because a break here means the raycast or the projection moved, while a break only
              in the pixel check means the shading, the sprites or the c2p did.

The bottom SCREEN_HUD_LINES lines are the platform's static HUD, which the portable core never
draws and the host binary therefore leaves blank. They are excluded from both checks, and the
output says so, so that "160 of 200 lines" can never be read as an accidental omission.

TWO MORE CHECKS, because a program can draw the right picture and still leave the machine broken:

  TEARDOWN    the machine's state before the program ran, after it terminated, and after the same
              run with NO program at all — read out of Hatari's memory rather than out of the
              source. The third sample is not optional: EmuTOS does not sit still after it boots,
              and on this ROM it installs its own VBL handler and repaints colour 7 whether or not
              our program ever ran. What must hold is that the machine the program leaves behind is
              the machine EmuTOS would have had anyway.

  HEALTH      Hatari's own logs, for bus errors, address errors, illegal instructions and a
              non-zero exit. EmuTOS's boot sizes RAM by probing it and generates bus errors from
              inside its own ROM every single run, so those are counted and reported as expected;
              a fault from anywhere else is a failure.

Comparison is by RGB rather than by palette index because the two pictures arrive in different
palettes-on-paper: the host writes a PLTE from g_palette_rgb, Hatari writes its own palette built
from the STE colour registers main.c programmed. Every channel in g_palette_rgb is a multiple of
0x11, so the 8-bit value round-trips exactly through the STE's 4 bits per gun and the two agree as
RGB — which also means a wrong colour register is caught here rather than hidden by index equality.

The ledger's shape and the screenshot's registration come from bench.py, imported rather than
restated, so a checker cannot drift from the harness that produced the files it checks.

Only a WALK pass is comparable: the WC-A and WC-S passes place the player by hand to hold a
fixture the host binary has no way to reproduce, so a capture from one of those is refused rather
than compared.

Usage: verify.py [--frames N] [--detail 0|1] [--frame K]
       with no arguments the three come from out/ledger.bin's capture_pass / capture_frame.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import bench

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "out"

# Paths as the top-level Makefile knows them: `make -C ROOT <target>` decides for itself whether
# the binary and the compiled level are stale, so this script never second-guesses the build.
HOST_BIN_TARGET = "build/blackice_host"
LEVEL_TARGET = "levels/level1.bil"
SCRIPT_PATH = ROOT / "test" / "scripts" / "walk.txt"

BENCH_LOGS = ("hatari-plain.log", "hatari-debug.log")
TEARDOWN_LOG = "hatari-teardown.log"
TEARDOWN_CONTROL_LOG = "hatari-teardown-control.log"

TARGET_SHOT = OUT / "frame.png"
LEDGER_BIN = OUT / "ledger.bin"
DIFF_PNG = OUT / "diff.png"

# render.h's DETAIL_COLUMNS_*, which is what selects the column count: GameState.detail_level, not
# the throttle. Every bench pass runs at THROTTLE_NOMINAL and varies only the detail level, so the
# host reference is pinned to that throttle and told which detail level to draw.
DETAIL_COLUMNS_160 = 0
DETAIL_COLUMNS_80 = 1
BENCH_THROTTLE = 1                      # game_consts.h's THROTTLE_NOMINAL

# Only a pass that replays the input script from frame 0 can be reproduced on the host; the WC-A
# and WC-S fixtures place the player directly.
COMPARABLE_PASS_PREFIX = "WALK"

# What `make frames` renders, and what the walk script is long enough for. Used only when there is
# no ledger to take the real answer from.
DEFAULT_FRAMES = 100
DEFAULT_DETAIL = DETAIL_COLUMNS_160
DEFAULT_PNG_FRAME = 99

SCREEN_W = bench.SCREEN_W
SCREEN_H = bench.SCREEN_H
WINDOW_LINES = bench.SCREEN_WINDOW_LINES
HUD_LINES = SCREEN_H - WINDOW_LINES

# ---------------------------------------------------------------- teardown --------------------
# The two moments the machine's state is sampled at, as VBL counts.
#
# EARLY is after EmuTOS has booted and sized memory but before the program has taken anything: at
# VBL 300 the whole _vblqueue reads NULL and _v_bas_ad still points at EmuTOS's own screen, which
# is what makes it the "before" picture rather than just an early one.
#
# LATE has to be after the program has terminated, and nothing in the machine announces that, so it
# is placed a wide margin before the end of the run and the ledger is used as the witness: its
# magic must be ABSENT at EARLY and PRESENT at LATE, which proves the two samples bracket the whole
# of the program's work. If a region then differs, "the program had not terminated yet" is the
# first thing the failure message tells you to suspect.
#
# CONTROL is BOTH of those samples taken again from a run with no program at all, and it is what
# makes the check mean anything: a teardown check without a control measures the operating system.
# Measured on this EmuTOS — with nothing whatsoever in the machine — colour 7 goes $555 -> $ddd and
# _vblqueue slot 0 goes NULL -> $e6c606, a handler inside the OS's own ROM, on the way to the
# desktop. A plain before/after diff reports both of those as if the program had done them, so it
# can never pass, and a real regression would hide in the noise.
TEARDOWN_EARLY_VBL = 300
TEARDOWN_LATE_MARGIN_VBLS = 1000
TEARDOWN_LATE_VBL = bench.RUN_VBLS - TEARDOWN_LATE_MARGIN_VBLS

# TOS's low-memory variables. $400..$600 covers the three the program touches AND the queue they
# point at ($4ce on this EmuTOS) — but the block as a whole is NOT comparable, because _frclock and
# _hz_200 live in it and tick all run long. Only the named fields below are compared.
LOW_MEMORY_BASE = 0x400
LOW_MEMORY_BYTES = 0x200
V_BAS_AD_ADDR = 0x44E           # long: the screen the OS's VBL handler programs the shifter from
NVBLS_ADDR = 0x454              # word: how many slots _vblqueue has
VBLQUEUE_ADDR = 0x456           # long: the slot table itself
VBLQUEUE_SLOT_BYTES = 4

# Regions dumped whole and required to come back byte for byte. Deliberately no video ADDRESS
# COUNTER ($ffff8205/07/09): it advances with the raster and would differ between any two samples.
# Wide enough for the longest region description below, so the verdicts line up in a column.
TEARDOWN_LABEL_WIDTH = 52

LOW_MEMORY_REGION = ("lowmem", LOW_MEMORY_BASE, LOW_MEMORY_BYTES, "TOS's low-memory variables")
LEDGER_WITNESS_REGION = ("ledger", bench.LEDGER_ADDR, 4, "the ledger magic")
RESTORED_REGIONS = (
    ("palette", 0xFFFF8240, 32, "the sixteen colour registers"),
    ("videobase", 0xFFFF8200, 4, "video base high/mid"),
    ("videosync", 0xFFFF820A, 2, "sync mode"),
    ("videoste", 0xFFFF820C, 4, "video base low and line offset"),
    ("shiftmode", 0xFFFF8260, 2, "resolution"),
)
TEARDOWN_REGIONS = RESTORED_REGIONS + (LOW_MEMORY_REGION, LEDGER_WITNESS_REGION)

# ---------------------------------------------------------------- machine health --------------
# EmuTOS sizes RAM by reading addresses that may not answer, so it bus-errors from inside its own
# ROM on every single boot. Those are expected and counted; a fault with a PC anywhere else is not.
EMUTOS_ROM_RANGE = (0xE00000, 0xEFFFFF)
FAULT_PATTERN = re.compile(r"(Bus Error|Address Error|Illegal|[Ee]xception)")
FAULT_PC_PATTERN = re.compile(r"PC=\$([0-9a-fA-F]+)")

# How much of a failure to print before it stops being evidence and becomes a wall of pixels.
MISMATCH_EXAMPLES = 10
HISTOGRAM_ROWS = 12

DIFF_DIM_SHIFT = 2                      # matching pixels drawn at a quarter brightness
DIFF_MISMATCH_RGB = (255, 0, 0)


def refuse(message):
    raise SystemExit(f"REFUSED: {message}")


# ---------------------------------------------------------------- the host reference ----------
def build_host_reference():
    """Let make decide whether the host binary and the compiled level are stale."""
    command = ["make", "-C", str(ROOT), HOST_BIN_TARGET, LEVEL_TARGET]
    done = subprocess.run(command, stdin=subprocess.DEVNULL, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if done.returncode:
        print(done.stdout)
        refuse(f"`{' '.join(command)}` failed with status {done.returncode}")
    return ROOT / HOST_BIN_TARGET


def run_host_reference(binary, frames, detail, png_frame):
    """Render the reference frame with the portable core; returns the PNG it wrote."""
    if png_frame >= frames:
        refuse(f"frame {png_frame} was asked for out of a {frames}-frame run — pass --frames")
    if not SCRIPT_PATH.exists():
        refuse(f"{SCRIPT_PATH} does not exist; it is the input script the target replayed")
    OUT.mkdir(exist_ok=True)
    png = OUT / f"frame{png_frame:04d}.png"
    png.unlink(missing_ok=True)
    command = [str(binary), "--level", str(ROOT / LEVEL_TARGET), "--script", str(SCRIPT_PATH),
               "--frames", str(frames), "--throttle", str(BENCH_THROTTLE), "--detail", str(detail),
               "--out", str(OUT), "--png", str(png_frame)]
    done = subprocess.run(command, stdin=subprocess.DEVNULL, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if done.returncode or not png.exists():
        print(done.stdout)
        refuse(f"the host reference wrote no {png} (status {done.returncode})")
    return png


def detail_for_pass(name):
    """Which detail level a bench pass drew at, from the column count its name ends with.

    Tested longest suffix first: "WALK160" ends with "160", and "160" does not end with "80"."""
    if name.endswith(str(bench.RENDER_COLUMNS_HIGH)):
        return DETAIL_COLUMNS_160
    if name.endswith(str(bench.RENDER_COLUMNS_LOW)):
        return DETAIL_COLUMNS_80
    refuse(f"pass {name!r} ends in neither {bench.RENDER_COLUMNS_HIGH} nor "
           f"{bench.RENDER_COLUMNS_LOW}, so its detail level is unknown — pass --detail")


def capture_parameters(args):
    """(frames, detail, png_frame, provenance) — from the ledger unless overridden."""
    frames, detail, png_frame = DEFAULT_FRAMES, DEFAULT_DETAIL, DEFAULT_PNG_FRAME
    provenance = f"defaults (no {LEDGER_BIN})"
    if LEDGER_BIN.exists():
        header, passes = bench.read_ledger(LEDGER_BIN)
        entry = passes[header["capture_pass"]]
        if not entry["name"].startswith(COMPARABLE_PASS_PREFIX):
            refuse(f"the ledger's capture pass is {entry['name']!r}, a fixture that places the "
                   f"player by hand — only a {COMPARABLE_PASS_PREFIX}* pass replays "
                   f"{SCRIPT_PATH.name} from frame 0, so nothing else has a host counterpart")
        frames, png_frame = entry["frames"], header["capture_frame"]
        detail = detail_for_pass(entry["name"])
        provenance = f"{LEDGER_BIN.name}: pass {entry['name']!r}, {entry['columns']} columns"
        if png_frame >= frames and args.frames is None:
            refuse(f"pass {entry['name']!r} measured {frames} frames but the ledger's capture_frame "
                   f"is {png_frame} — pass --frames to say how long the host run should be")
    if args.frames is not None:
        frames, provenance = args.frames, provenance + ", --frames override"
    if args.detail is not None:
        detail, provenance = args.detail, provenance + ", --detail override"
    if args.frame is not None:
        png_frame, provenance = args.frame, provenance + ", --frame override"
    return frames, detail, png_frame, provenance


# ---------------------------------------------------------------- the two pictures ------------
def logical_screen(png):
    """The target's 320x200 ST screen as RGB, undoing the emulator's borders and its zoom.

    The zoom is nearest-neighbour, so one sample per scale x scale block recovers the ST's own
    pixels — and re-expanding those samples and demanding the block region back EXACTLY is a free
    and very strong check on the registration bench.locate_screen() derived: a rectangle even one
    pixel out of place cuts across the blocks and fails here instead of silently mis-comparing."""
    image = Image.open(png)
    left, top, scale = bench.locate_screen(image)
    pixels = np.asarray(image.convert("RGB"))
    block = pixels[top:top + SCREEN_H * scale, left:left + SCREEN_W * scale]
    logical = block[::scale, ::scale]
    expanded = np.repeat(np.repeat(logical, scale, axis=0), scale, axis=1)
    if not np.array_equal(block, expanded):
        refuse(f"{png} is not a clean {scale}x nearest-neighbour zoom of a {SCREEN_W}x{SCREEN_H} "
               f"screen at ({left}, {top}) — the screen was not located correctly")
    return logical


def host_screen_and_void(png):
    """The host's 320x200 screen as RGB, plus the RGB of palette index 0 — the void.

    The void's colour is read from the reference PNG's own PLTE rather than restated here, so the
    silhouette check follows g_palette_rgb automatically if the palette is ever re-authored."""
    image = Image.open(png)
    if image.mode != "P":
        refuse(f"{png} is mode {image.mode}, not the palettised PNG render_png.c writes")
    void_rgb = tuple(image.getpalette()[0:3])
    pixels = np.asarray(image.convert("RGB"))
    if pixels.shape[:2] != (SCREEN_H, SCREEN_W):
        refuse(f"{png} is {pixels.shape[1]}x{pixels.shape[0]}, expected {SCREEN_W}x{SCREEN_H}")
    return pixels, void_rgb


# ---------------------------------------------------------------- the pixel check -------------
def describe_histogram(label, counts):
    """Which rows (or columns) the mismatches fall in, so a systematic shift is visible at once."""
    affected = np.nonzero(counts)[0]
    plural = label if len(affected) == 1 else label + "s"
    span = f", from {label} {affected[0]} to {affected[-1]}" if len(affected) else ""
    print(f"    {len(affected)} {plural} affected{span}")
    order = affected[np.argsort(-counts[affected])][:HISTOGRAM_ROWS]
    for index in sorted(order.tolist()):
        print(f"      {label} {index:>4}: {counts[index]:>5} mismatching")
    if len(affected) > HISTOGRAM_ROWS:
        print(f"      ... {len(affected) - HISTOGRAM_ROWS} more {label}s, worst {HISTOGRAM_ROWS} shown")


def compare_pixels(host_window, target_window):
    """Every pixel of the render window; returns the mismatch mask and prints the diagnosis."""
    mismatch = np.any(host_window != target_window, axis=2)
    count = int(mismatch.sum())
    total = mismatch.size
    print(f"PIXELS     (rendered frame vs host reference, top {WINDOW_LINES} of {SCREEN_H} lines; "
          f"the bottom {HUD_LINES} are the platform's HUD and are not compared)")
    print(f"    {count} of {total} pixels differ")
    if not count:
        print("  PASS")
        return mismatch
    rows, columns = np.nonzero(mismatch)
    for row, column in list(zip(rows.tolist(), columns.tolist()))[:MISMATCH_EXAMPLES]:
        # .tolist() so the RGB reads as (204, 255, 255) and not as three numpy scalar repr()s.
        print(f"      x={column:>3} y={row:>3}  host {tuple(host_window[row, column].tolist())}  "
              f"target {tuple(target_window[row, column].tolist())}")
    if count > MISMATCH_EXAMPLES:
        print(f"      ... {count - MISMATCH_EXAMPLES} more")
    describe_histogram("row", mismatch.sum(axis=1))
    describe_histogram("column", mismatch.sum(axis=0))
    print("  FAIL")
    return mismatch


def write_diff_png(host_window, mismatch, path):
    """The reference frame dimmed, with every disagreeing pixel in red, so the shape is readable."""
    image = (host_window >> DIFF_DIM_SHIFT).astype(np.uint8)
    image[mismatch] = DIFF_MISMATCH_RGB
    Image.fromarray(image).save(path)
    return path


# ---------------------------------------------------------------- the silhouette check --------
def silhouette(window, void_rgb):
    """(first, last) non-void row per screen column; WINDOW_LINES for a column that is all void."""
    solid = np.any(window != np.array(void_rgb, dtype=window.dtype), axis=2)
    has_solid = solid.any(axis=0)
    first = np.where(has_solid, solid.argmax(axis=0), WINDOW_LINES)
    last = np.where(has_solid, WINDOW_LINES - 1 - solid[::-1].argmax(axis=0), WINDOW_LINES)
    return first, last


def compare_silhouettes(host_window, target_window, void_rgb):
    """Geometry alone: where the drawn shape starts and ends in each column. Returns 1 on failure."""
    host_first, host_last = silhouette(host_window, void_rgb)
    target_first, target_last = silhouette(target_window, void_rgb)
    top_delta = np.abs(host_first.astype(int) - target_first.astype(int))
    bottom_delta = np.abs(host_last.astype(int) - target_last.astype(int))
    off = np.nonzero(top_delta | bottom_delta)[0]
    print(f"SILHOUETTE (first and last non-void row of each of the {SCREEN_W} columns; void is "
          f"palette index 0, RGB {void_rgb})")
    print(f"    worst top delta {top_delta.max()}, worst bottom delta {bottom_delta.max()}, "
          f"{len(off)} columns differ")
    for column in off[:MISMATCH_EXAMPLES].tolist():
        print(f"      column {column:>3}: host ({host_first[column]}, {host_last[column]})  "
              f"target ({target_first[column]}, {target_last[column]})")
    if len(off) > MISMATCH_EXAMPLES:
        print(f"      ... {len(off) - MISMATCH_EXAMPLES} more")
    if len(off):
        print("  FAIL: the geometry differs, so look at the raycast and the projection before "
              "the drawers")
        return 1
    print("  PASS")
    return 0


# ---------------------------------------------------------------- the teardown check ----------
def teardown_dump(when, name):
    return OUT / f"teardown_{when}_{name}.bin"


def teardown_sample(when, vbl):
    """A breakpoint line arming one sample: at VBL `vbl`, dump every region and carry on."""
    script = OUT / f"teardown_{when}.txt"
    script.write_text("".join(f"savebin {teardown_dump(when, name)} ${address:x} {size}\n"
                              for name, address, size, _ in TEARDOWN_REGIONS) + "cont\n")
    return f"b VBL > {vbl} :once :file {script}\n"


def teardown_arm(run_name, samples):
    """One --parse file arming every sample of one run.

    All of them can be armed at startup because all are conditions on the VBL counter. A condition
    on a RAM ADDRESS could not be — at power-on Hatari has not sized memory and refuses one — which
    is why bench.py's ledger capture needs three scripts where this needs one per run."""
    arm = OUT / f"teardown_arm_{run_name}.txt"
    arm.write_text("".join(teardown_sample(when, vbl) for when, vbl in samples) + "cont\n")
    return arm


def run_teardown_capture():
    """Sample the machine before the program, after it, and after the same run without it."""
    bench.require_inputs()
    OUT.mkdir(exist_ok=True)
    runs = (("program", (("before", TEARDOWN_EARLY_VBL), ("after", TEARDOWN_LATE_VBL)),
             TEARDOWN_LOG, True),
            ("control", (("control_before", TEARDOWN_EARLY_VBL),
                         ("control_after", TEARDOWN_LATE_VBL)), TEARDOWN_CONTROL_LOG, False))
    for _, samples, _, _ in runs:
        for when, _ in samples:
            for name, _, _, _ in TEARDOWN_REGIONS:
                teardown_dump(when, name).unlink(missing_ok=True)
    dumps = {}
    for run_name, samples, log_name, auto in runs:
        bench.hatari(["--parse", str(teardown_arm(run_name, samples))], log_name, auto=auto)
        for when, vbl in samples:
            for name, _, _, _ in TEARDOWN_REGIONS:
                path = teardown_dump(when, name)
                if not path.exists():
                    refuse(f"the {run_name} run produced no {path} — the VBL {vbl} breakpoint "
                           f"never fired; see {OUT / log_name}")
                dumps[when, name] = path.read_bytes()
    return dumps


def check_teardown_brackets(dumps):
    """Prove the samples are what they claim to be, using the ledger magic as the witness."""
    magic = bench.LEDGER_MAGIC.to_bytes(4, "big")
    if dumps["before", "ledger"] == magic:
        refuse(f"the ledger magic was already at ${bench.LEDGER_ADDR:x} at VBL "
               f"{TEARDOWN_EARLY_VBL}, so that sample is not a picture of the machine before the "
               "program ran — lower TEARDOWN_EARLY_VBL")
    if dumps["after", "ledger"] != magic:
        refuse(f"the ledger magic is absent from ${bench.LEDGER_ADDR:x} at VBL "
               f"{TEARDOWN_LATE_VBL}, so the program had not even finished measuring by then — "
               "raise bench.RUN_VBLS or lower TEARDOWN_LATE_MARGIN_VBLS")
    if dumps["control_after", "ledger"] == magic:
        refuse(f"the ledger magic is at ${bench.LEDGER_ADDR:x} in the CONTROL run, which was "
               "supposed to start no program at all — the baseline is not a baseline")


def low_memory_field(dump, address, size):
    return dump[address - LOW_MEMORY_BASE:address - LOW_MEMORY_BASE + size]


def vblqueue_slots(dump):
    """The queue's slots as raw bytes, or None if the queue lies outside the dumped window."""
    count = int.from_bytes(low_memory_field(dump, NVBLS_ADDR, 2), "big")
    start = int.from_bytes(low_memory_field(dump, VBLQUEUE_ADDR, 4), "big") - LOW_MEMORY_BASE
    end = start + count * VBLQUEUE_SLOT_BYTES
    return dump[start:end] if 0 <= start and end <= len(dump) else None


def teardown_row(label, run, control):
    """One line of the verdict; `run` and `control` are each (before, after). Returns 1 on failure.

    A region that changed is not automatically a fault. The question is whether it changed in a way
    the operating system does not change it all by itself, which is what `control` holds."""
    before, after = run
    if before == after:
        print(f"    {label:<{TEARDOWN_LABEL_WIDTH}} RESTORED")
        return 0
    verdict, failed = ("OS DRIFT", 0) if run == control else ("NOT RESTORED", 1)
    print(f"    {label:<{TEARDOWN_LABEL_WIDTH}} {verdict}")
    for source, (was, now) in (("ours", run), ("control", control)):
        print(f"      {source:<8} before {was.hex()}")
        print(f"      {'':<8} after  {now.hex()}")
    return failed


def compare_teardown(dumps):
    """Everything the program borrowed, checked back in. Returns 1 on any unexplained change."""
    print(f"TEARDOWN   (the machine at VBL {TEARDOWN_EARLY_VBL} before the program took it against "
          f"VBL {TEARDOWN_LATE_VBL} after it\n            terminated, and the same two instants of "
          "a run with no program at all — from Hatari's memory)")
    check_teardown_brackets(dumps)

    def pairs(extract):
        """(ours, control) as ((before, after), (before, after)) for one region or field."""
        return (tuple(extract(when) for when in ("before", "after")),
                tuple(extract(when) for when in ("control_before", "control_after")))

    changed = 0
    for name, address, size, description in RESTORED_REGIONS:
        changed += teardown_row(f"{description} ${address:x}..${address + size - 1:x}",
                                *pairs(lambda when, name=name: dumps[when, name]))
    for label, address, size in (("_v_bas_ad", V_BAS_AD_ADDR, 4), ("nvbls", NVBLS_ADDR, 2),
                                 ("_vblqueue", VBLQUEUE_ADDR, 4)):
        changed += teardown_row(f"{label} ${address:x}", *pairs(
            lambda when, address=address, size=size:
            low_memory_field(dumps[when, "lowmem"], address, size)))
    if any(vblqueue_slots(dumps[when, "lowmem"]) is None
           for when in ("before", "after", "control_before", "control_after")):
        refuse(f"_vblqueue points outside the ${LOW_MEMORY_BASE:x}.."
               f"${LOW_MEMORY_BASE + LOW_MEMORY_BYTES:x} window this check dumps — widen "
               "LOW_MEMORY_BYTES")
    low = dumps["before", "lowmem"]
    count = int.from_bytes(low_memory_field(low, NVBLS_ADDR, 2), "big")
    queue = int.from_bytes(low_memory_field(low, VBLQUEUE_ADDR, 4), "big")
    changed += teardown_row(f"the {count} _vblqueue slots at ${queue:x}",
                            *pairs(lambda when: vblqueue_slots(dumps[when, "lowmem"])))
    # Said plainly rather than quietly skipped: KBDVECS is reached through XBIOS Kbdvbase, and a
    # --parse script cannot call an XBIOS function, so there is no address for savebin to read.
    print("    note: KBDVECS.joyvec is restored BY CONSTRUCTION — os.S saves it and puts it back —")
    print("          but it is NOT measured here. The KBDVECS pointer comes from XBIOS Kbdvbase,")
    print("          which a debugger script cannot call, so this check has no address to dump.")
    if changed:
        print(f"  FAIL: {changed} region(s) NOT RESTORED — changed in a way EmuTOS does not change "
              f"them on its own. If everything looks like the program is still running, suspect "
              f"that VBL {TEARDOWN_LATE_VBL} came before it terminated.")
        return 1
    print("  PASS  (every difference is EmuTOS's own drift, reproduced with no program present)")
    return 0


# ---------------------------------------------------------------- the health check ------------
def scan_log(path):
    """(expected boot probes, unexpected fault lines, exit status or None) for one Hatari log."""
    if not path.exists():
        refuse(f"{path} does not exist — run bench.py first; it is what writes the logs")
    expected, faults, status = 0, [], None
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith(bench.HATARI_STATUS_PREFIX):
            status = int(line[len(bench.HATARI_STATUS_PREFIX):])
        elif FAULT_PATTERN.search(line):
            program_counter = FAULT_PC_PATTERN.search(line)
            in_rom = (program_counter
                      and EMUTOS_ROM_RANGE[0] <= int(program_counter.group(1), 16) <= EMUTOS_ROM_RANGE[1])
            expected, faults = (expected + 1, faults) if in_rom else (expected, faults + [line])
    return expected, faults, status


def check_health(logs):
    """Hatari's own account of the runs. Returns 1 if any log shows a fault or a bad exit."""
    print("HEALTH     (Hatari's logs: bus and address errors, illegal instructions, exit status)")
    failures = 0
    for path in logs:
        expected, faults, status = scan_log(path)
        print(f"    {path.name:<28} {expected} bus error(s) from EmuTOS's boot RAM probe, "
              f"{len(faults)} other fault(s), exit status "
              f"{'NOT RECORDED' if status is None else status}")
        for line in faults[:MISMATCH_EXAMPLES]:
            print(f"      {line.strip()}")
        if len(faults) > MISMATCH_EXAMPLES:
            print(f"      ... {len(faults) - MISMATCH_EXAMPLES} more")
        failures += bool(faults) + bool(status)
    print(f"    (a fault whose PC is inside EmuTOS's ROM ${EMUTOS_ROM_RANGE[0]:x}.."
          f"${EMUTOS_ROM_RANGE[1]:x} is the OS sizing memory, and is expected every boot)")
    if failures:
        print(f"  FAIL: {failures} log(s) show a fault outside EmuTOS's ROM or a non-zero exit")
        return 1
    print("  PASS")
    return 0


# ---------------------------------------------------------------- the run ---------------------
def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--frames", type=int, help="frames the host run should render")
    parser.add_argument("--detail", type=int, choices=(DETAIL_COLUMNS_160, DETAIL_COLUMNS_80),
                        help="detail level the host run should draw at (0 = 160 columns)")
    parser.add_argument("--frame", type=int, help="which frame to compare")
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    if not TARGET_SHOT.exists():
        refuse(f"{TARGET_SHOT} does not exist — run bench.py first; it is the screenshot Hatari "
               "took at the instant the target published its ledger")
    frames, detail, png_frame, provenance = capture_parameters(arguments)
    print(f"-- comparing frame {png_frame} of a {frames}-frame walk at detail {detail}, throttle "
          f"{BENCH_THROTTLE}   [{provenance}]")

    host_png = run_host_reference(build_host_reference(), frames, detail, png_frame)
    host_screen, void_rgb = host_screen_and_void(host_png)
    target_screen = logical_screen(TARGET_SHOT)
    print(f"-- host reference: {host_png}     target: {TARGET_SHOT}\n")

    host_window, target_window = host_screen[:WINDOW_LINES], target_screen[:WINDOW_LINES]
    mismatch = compare_pixels(host_window, target_window)
    failures = int(mismatch.any())
    if failures:
        print(f"    difference image: {write_diff_png(host_window, mismatch, DIFF_PNG)} "
              "(reference dimmed, disagreeing pixels red)")
    print()
    failures += compare_silhouettes(host_window, target_window, void_rgb)

    print(f"\n-- teardown runs: sampling at VBL {TEARDOWN_EARLY_VBL} and VBL "
          f"{TEARDOWN_LATE_VBL} of a fresh {bench.RUN_VBLS}-VBL run, and at VBL "
          f"{TEARDOWN_LATE_VBL}\n   of the same run with no program at all, as the baseline\n")
    failures += compare_teardown(run_teardown_capture())
    print()
    failures += check_health([OUT / name for name in
                              BENCH_LOGS + (TEARDOWN_LOG, TEARDOWN_CONTROL_LOG)])
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
