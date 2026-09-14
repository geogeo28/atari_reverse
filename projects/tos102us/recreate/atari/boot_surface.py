#!/usr/bin/env python3
"""boot_surface.py — what a TOS ROM leaves behind when it has finished booting, as text a host can diff.

    python3 boot_surface.py capture [--rom PATH] [--out PREFIX]   one boot -> artefacts under out/
    python3 boot_surface.py golden  [--rom PATH]                  two boots -> golden/, if they agree
    python3 boot_surface.py compare [--rom PATH]                  one boot -> diffed against golden/

THE FOUR SURFACES, and each is a different kind of evidence:
  * THE SCREENSHOT — what a person would see. Compared byte for byte; hatari_rom.py's machine
    configuration is what makes that possible at all (no statusbar, no drive LED, no frameskip).
  * THE 256 VECTORS ($000-$3FF), decoded — where the OS pointed every exception. A composition test:
    Tier 1 can prove each handler equals the original and still leave a vector wired to the wrong one.
  * THE SYSTEM VARIABLES ($400-$5B3), decoded by name from sysvars.py — the OS's published state.
    phystop, _membot, _memtop, the hdv_* driver hooks, _drvbits, _sysbase, end_os, and the four
    xcon* BIOS device tables.
  * THE BOOT METRIC — the vblank count and `_hz_200` at the stop point, i.e. how long the boot took
    on the machine's own two clocks.

## THE STOP RULE IS A VBLANK COUNT, AND THE ANCHOR THE CHARTER ASKED FOR DOES NOT EXIST HERE

The brief for this driver named the desktop's first AES `evnt_multi` — a breakpoint on a `trap #2`
with `d0 = $c8` and the control array's opcode 25 — with a vblank-count fallback. MEASURED, on
TOS 1.02 US: over 900 vblanks of boot, `b (pc).w = $4e42 && d0 = $c8` matches ZERO times. The first
`trap #2` of the boot is at $fecb6a with `d0 = $73`, the VDI. The reason is that TOS's desktop is
not an application that traps into the AES: it is part of the same ROM and calls the AES's dispatcher
($fe65aa, reached from the trap handler at $fe3ea6) directly. The anchor exists for a GEM program
loaded from disk and not for the ROM's own desktop.

Hatari cannot express the opcode test either way: its breakpoint grammar allows ONE level of
indirection (`(d1).w`), and the opcode is `((d1))[0]` — the AES parameter block's first longword
points at the control array. That is a second, independent reason the specified condition is not
writable as one breakpoint.

So the stop rule is STOP_VBL vblanks after power-on, and it is not taken on trust: every capture
also photographs the machine again SETTLE_VBL vblanks later and compares. A capture whose screen or
whose pinned RAM moved between the two is reported as UNSETTLED, which is the failure a fixed count
can have, so THE VERDICT GATES: `capture` exits non-zero on it and `golden` refuses to write, since
a golden of a machine still in motion pins a moment and the next capture differs from it for that
reason alone. A quiescent desktop is a stronger statement than an anchor anyway — the anchor says
the event loop was reached once, the settle proof says nothing is changing any more.

## WHAT IS PINNED, AND WHAT IS ONLY REPORTED

MEASURED over three boots of the ORIGINAL ROM, same configuration: RAM $000-$9FE is byte-identical
across all three, and 645 bytes above it are not (first at $9FF, last at $C7E9, spread over pages
$0000, $1000, $7000, $8000, $9000, $A000 and $C000 — stack scratch and the OS's own working
storage). So the pinned window is $000 to RAM_PINNED_END, which the vectors and the system variables
both fall inside, and the rest of the 64 KB the brief asks for is READ AND HASHED PER PAGE BUT NOT
PINNED. Reporting a per-page hash of a region that is not reproducible would be a red light that
means nothing; saying which pages those are is the useful half.

The three time-varying system variables (`_vbclock`, `_frclock`, `_hz_200`) are masked out of every
comparison and listed by name in the render. They are masked by POLICY — they count time and a
comparison has no business requiring two runs to agree on them — and, measured, all three were
IDENTICAL across the three boots above, which is what makes the boot metric worth reporting.

## WHAT A COMPARISON IS ABOUT

The ROM, and only the ROM. So every capture records its INSTRUMENT — the ROM, the floppy in drive A
and (in the ledger drivers) the program on it — and `compare` REFUSES rather than reporting when the
floppy under the run is not the one the golden was taken with. Without that, rebuilding a disk image
reads as a ROM difference, which is the most expensive kind of wrong answer an instrument can give.

## WHAT A CAPTURE IS NOT

It is not proof that the machine did anything. Hatari writes a PNG whether or not the ROM ran, and
exits 0 after a bus error it printed to its log. hatari_rom.boot() refuses on the log markers, and
`distinct_colours` on the screenshot is what tells a painted screen from a blank one — a ROM that
dies at its first instruction still produces a perfectly good capture of a black rectangle.
"""
import argparse
import difflib
import json
import struct
import sys
from pathlib import Path

import hatari_rom
import sysvars
from hatari_rom import (BLANK_SCREEN_COLOURS, GOLDEN, OUT, breakpoint_script, capture_prefix,
                        file_clause, instrument_identity, refuse, require_files, sha256_bytes)

sys.path.insert(0, str(hatari_rom.REPO / "tools"))
from hatari_headless import distinct_colours      # noqa: E402

# ---- the stop rule --------------------------------------------------------------------------------
# The desktop is fully drawn by vblank ~400 on this machine (measured); 500 leaves a margin that
# costs 0.07 s of wall clock under --fast-forward.
STOP_VBL = 500
# Far enough after the stop that anything still running would have moved the screen — one emulated
# second — and cheap for the same reason.
SETTLE_VBL = 550
# Outlasts the settle shot with room to spare; the useful part of the run has ended by then.
RUN_VBLS = 620

# ---- the window that is read back -----------------------------------------------------------------
RAM_WINDOW_BYTES = 0x10000
RAM_PAGE_BYTES = 0x1000
# The measurement in the docstring: the lowest address that differed between three boots was $9FF.
RAM_PINNED_END = 0x9FF

VECTOR_COUNT = 256
VECTOR_BYTES = 4
VECTOR_TABLE_END = VECTOR_COUNT * VECTOR_BYTES

# ---- the masked fields ----------------------------------------------------------------------------
# (address, bytes, why) for the three time-varying system variables — sysvars.py owns which they are,
# because the same three are the boot metric. Everything here is excluded from every byte comparison
# and rendered as `<masked>`.
MASKED_FIELDS = sysvars.MASKED_FIELDS

# ---- the 68000 and ST exception vectors ------------------------------------------------------------
# Index -> name. Anything not named renders as `-`, which is most of $50-$FF: the ST leaves them for
# programs. The MFP's sixteen are at $40-$4F because the ST programs the 68901's vector base to $40.
VECTOR_NAMES = {
    0: "reset SSP", 1: "reset PC", 2: "bus error", 3: "address error", 4: "illegal instruction",
    5: "divide by zero", 6: "CHK", 7: "TRAPV", 8: "privilege violation", 9: "trace",
    10: "line-A emulator", 11: "line-F emulator", 15: "uninitialised interrupt",
    24: "spurious interrupt",
    25: "autovector 1", 26: "autovector 2 (HBL)", 27: "autovector 3", 28: "autovector 4 (VBL)",
    29: "autovector 5", 30: "autovector 6 (MFP)", 31: "autovector 7",
    32: "trap #0", 33: "trap #1 (GEMDOS)", 34: "trap #2 (GEM)", 35: "trap #3", 36: "trap #4",
    37: "trap #5", 38: "trap #6", 39: "trap #7", 40: "trap #8", 41: "trap #9", 42: "trap #10",
    43: "trap #11", 44: "trap #12", 45: "trap #13 (BIOS)", 46: "trap #14 (XBIOS)", 47: "trap #15",
    64: "MFP centronics busy", 65: "MFP RS232 DCD", 66: "MFP RS232 CTS", 67: "MFP blitter",
    68: "MFP timer D", 69: "MFP timer C", 70: "MFP keyboard/MIDI ACIA", 71: "MFP FDC/HDC",
    72: "MFP timer B", 73: "MFP send error", 74: "MFP send buffer empty", 75: "MFP receive error",
    76: "MFP receive buffer full", 77: "MFP timer A", 78: "MFP RS232 ring",
    79: "MFP mono monitor detect",
}

# ---- the system variables --------------------------------------------------------------------------
# sysvars.py is the table: one definition, pinned by test_atari_pins.py against names.txt and against
# prg/tosapi.h's SYSVAR_* addresses.

MASKED_TEXT = "<masked>"

# The hexdump of the pinned window: sixteen bytes a line, masked bytes as `--`, so the file a golden
# carries is the exact bytes rather than a hash nobody can localise a difference in.
HEXDUMP_COLUMNS = 16
MASKED_BYTE_TEXT = "--"

# The artefacts a capture writes, keyed by the suffix they take after the prefix.
ARTEFACTS = ("screen.png", "screen-settle.png", "vectors.txt", "sysvars.txt", "ram.txt", "metrics.json")
# Everything but the settle shot is golden. THE SETTLE SHOT IS NOT MISSING FROM THE GOLDEN, IT IS
# NOT A GOLDEN KIND OF THING: it is evidence about one run's quiescence, it is compared inside that
# run — against the run's own stop shot, and the verdict gates the capture — and a golden copy would
# be compared against nothing. What a later ROM has to reproduce is the stop shot and the VERDICT,
# and both of those are golden (`screen.png`, and `settle` in `metrics.json`).
GOLDEN_ARTEFACTS = tuple(name for name in ARTEFACTS if name != "screen-settle.png")


# ---- reading the machine ---------------------------------------------------------------------------

def capture_scripts(work, screen_png, ram_bin, settle_png, settle_ram):
    """The three debugger scripts, and it takes three because each hop can only be armed by the one
    before it. A `--parse` file's commands all run at STARTUP, so the capture cannot live in one;
    and the settle shot has to be armed from inside the stop, because Hatari's breakpoint
    expressions have no arithmetic — `b VBL > VBL + 50` is refused at the `+`."""
    # The settle shot reads the PINNED WINDOW ONLY, because that is the only part of it anything
    # looks at: above it two moments of one boot disagree as freely as two boots do.
    settle = breakpoint_script(work / "settle.txt",
                               f"screenshot {settle_png}",
                               f"savebin {settle_ram} $0 ${RAM_PINNED_END:x}")
    stop = breakpoint_script(work / "stop.txt",
                             f"screenshot {screen_png}",
                             f"savebin {ram_bin} $0 ${RAM_WINDOW_BYTES:x}",
                             f"b VBL > {SETTLE_VBL} :once :quiet {file_clause(settle)}")
    return breakpoint_script(work / "arm.txt", f"b VBL > {STOP_VBL} :once :quiet {file_clause(stop)}")


def boot_and_read(rom, disk, work, log_path):
    """Boot `rom`, stop twice, and return (screen bytes, RAM, settle screen bytes, settle RAM)."""
    work.mkdir(parents=True, exist_ok=True)
    files = [work / name for name in ("screen.png", "ram.bin", "settle.png", "settle-ram.bin")]
    for path in files:
        path.unlink(missing_ok=True)
    arm = capture_scripts(work, *files)
    hatari_rom.boot(rom, disk, RUN_VBLS, arm, log_path)
    for path in files:
        if not path.is_file():
            refuse(f"the debugger never wrote {path} — the stop at vblank {STOP_VBL} did not fire; "
                   f"see {log_path}")
    return tuple(path.read_bytes() for path in files)


# ---- masking ----------------------------------------------------------------------------------------

def masked(data):
    """A copy of the RAM window with every masked field zeroed, for hashing and comparison."""
    blanked = bytearray(data)
    for address, length, _why in MASKED_FIELDS:
        blanked[address:address + length] = bytes(length)
    return bytes(blanked)


def is_masked(address):
    return any(start <= address < start + length for start, length, _why in MASKED_FIELDS)


# ---- rendering --------------------------------------------------------------------------------------

def read_field(data, address, width):
    return struct.unpack_from(sysvars.WIDTH_FORMAT[width], data, address)[0]


def render_vectors(data):
    lines = [f"# the 68000/ST exception vectors, $000-${VECTOR_TABLE_END - 1:03X}",
             "# address  vector  name                          value"]
    for index in range(VECTOR_COUNT):
        address = index * VECTOR_BYTES
        name = VECTOR_NAMES.get(index, "-")
        value = MASKED_TEXT if is_masked(address) else f"${read_field(data, address, 'L'):08x}"
        lines.append(f"  ${address:03X}     {index:3d}     {name:<28}  {value}")
    return "\n".join(lines) + "\n"


def render_sysvars(data):
    lines = [f"# the TOS system variables, ${sysvars.BLOCK_START:03X}-${sysvars.BLOCK_END - 1:03X}",
             "# masked (time-varying, excluded from every comparison):"]
    lines += [f"#   ${address:03X}  {length} bytes  {why}" for address, length, why in MASKED_FIELDS]
    lines.append("# address  name            value")
    for address, width, count, name in sysvars.SYSVARS:
        step = sysvars.WIDTH_BYTES[width]
        values = []
        for index in range(count):
            at = address + index * step
            values.append(MASKED_TEXT if is_masked(at)
                          else f"${read_field(data, at, width):0{step * 2}x}")
        lines.append(f"  ${address:03X}     {name:<14}  {' '.join(values)}")
    return "\n".join(lines) + "\n"


def render_ram(data):
    """The pinned window as a hexdump. The masked bytes print as `--`, so this file IS the
    comparison rather than a hash standing in for one."""
    lines = [f"# RAM $000-${RAM_PINNED_END - 1:04X}, the window measured reproducible across three "
             f"boots of the original ROM",
             f"# bytes at or above ${RAM_PINNED_END:04X} are read and hashed per page in "
             f"metrics.json, and are NOT pinned"]
    for base in range(0, RAM_PINNED_END, HEXDUMP_COLUMNS):
        columns = []
        for offset in range(HEXDUMP_COLUMNS):
            at = base + offset
            if at >= RAM_PINNED_END:
                break
            columns.append(MASKED_BYTE_TEXT if is_masked(at) else f"{data[at]:02x}")
        lines.append(f"  ${base:04X}  " + " ".join(columns))
    return "\n".join(lines) + "\n"


def page_hashes(data):
    """A sha256 per 4 KB page of the whole window, so a difference above the pinned end is at least
    localised even though it is not pinned."""
    blanked = masked(data)
    return [sha256_bytes(blanked[base:base + RAM_PAGE_BYTES])
            for base in range(0, RAM_WINDOW_BYTES, RAM_PAGE_BYTES)]


def boot_metric(data):
    """The clocks at the stop point — how long the boot took, in the machine's own units.

    They are exactly the masked variables: the same bytes a comparison must not require two runs to
    agree on are the ones worth reading, which is why sysvars.py owns the list and neither half
    spells an address.
    """
    metric = {"stop_vbl": STOP_VBL}
    for name, _why in sysvars.TIME_VARYING:
        address, width, _count = sysvars.entry(name)
        metric[name] = read_field(data, address, width)
    return metric


# What a metrics file carries that a comparison must NOT hold two ROMs to. `None` drops the whole
# key, a tuple drops those fields of it:
#   * the instrument has a check of its own, and it is the one place a difference is allowed — the
#     ROM under test is expected to differ and everything else in it is not;
#   * the clocks are dropped by the policy that masks their bytes, and reported as the boot metric;
#   * the page hashes above the pinned window are MEASURED not to reproduce — two boots of the
#     original ROM disagree on pages $0, $1, $7, $8, $9, $A and $C every time — so requiring them
#     would make every golden impossible and every comparison red.
REPORTED_NOT_PINNED = (("instrument", None),
                       ("boot_metric", tuple(name for name, _why in sysvars.TIME_VARYING)),
                       ("ram", ("page_sha256",)))


def pinned_metrics(metrics):
    """A metrics dictionary with everything that only reports taken out — what two captures of one
    ROM have to agree on, and what a compare holds a rebuilt ROM to."""
    pinned = {key: dict(value) if isinstance(value, dict) else value
              for key, value in metrics.items()}
    for key, dropped in REPORTED_NOT_PINNED:
        if dropped is None:
            pinned.pop(key, None)
            continue
        for field in dropped:
            pinned.get(key, {}).pop(field, None)
    return pinned


def metrics_differences(reference, candidate):
    """Which top-level parts of two metrics files disagree, once the reported halves are dropped."""
    left, right = pinned_metrics(reference), pinned_metrics(candidate)
    return [(f"metrics.json: {key}", f"golden {left.get(key)}\n  this  {right.get(key)}")
            for key in sorted(set(left) | set(right)) if left.get(key) != right.get(key)]


def page_differences(reference, candidate):
    """Which 4 KB pages above the pinned window differ — reported, never a verdict (see above)."""
    return [f"page ${index * RAM_PAGE_BYTES:05x}"
            for index, (left, right) in enumerate(zip(reference["ram"]["page_sha256"],
                                                      candidate["ram"]["page_sha256"]))
            if left != right]


# ---- a capture ---------------------------------------------------------------------------------------

def settle_report(screen, settle_screen, ram, settle_ram):
    """Did anything move between the stop and the settle shot? The pinned window only: above it the
    machine is not reproducible even between two boots, let alone between two moments of one."""
    pinned, settled = masked(ram)[:RAM_PINNED_END], masked(settle_ram)[:RAM_PINNED_END]
    moved = [f"${index:04x}" for index in range(RAM_PINNED_END) if pinned[index] != settled[index]]
    return {
        "screen_still": screen == settle_screen,
        "ram_still": not moved,
        "ram_moved_at": moved[:16],
        "settle_vbl": SETTLE_VBL,
    }


def capture(rom, disk, prefix, log_name):
    """One boot, every artefact written under `prefix`. Returns the metrics dictionary."""
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    # Its OWN work directory: every driver here writes `arm.txt` and `screen.png`, and one
    # shared directory is a collision waiting for the day two of them overlap.
    work = OUT / "work-boot"
    screen, ram, settle_screen, settle_ram = boot_and_read(rom, disk, work, OUT / log_name)

    (prefix.parent / f"{prefix.name}-screen.png").write_bytes(screen)
    (prefix.parent / f"{prefix.name}-screen-settle.png").write_bytes(settle_screen)
    (prefix.parent / f"{prefix.name}-vectors.txt").write_text(render_vectors(ram))
    (prefix.parent / f"{prefix.name}-sysvars.txt").write_text(render_sysvars(ram))
    (prefix.parent / f"{prefix.name}-ram.txt").write_text(render_ram(ram))

    metrics = {
        "instrument": instrument_identity(rom, disk),
        "stop_rule": {"stop_vbl": STOP_VBL, "settle_vbl": SETTLE_VBL, "run_vbls": RUN_VBLS},
        "boot_metric": boot_metric(ram),
        "settle": settle_report(screen, settle_screen, ram, settle_ram),
        "screen": {
            "sha256": sha256_bytes(screen),
            "distinct_colours": distinct_colours(prefix.parent / f"{prefix.name}-screen.png"),
        },
        "ram": {
            "pinned_end": RAM_PINNED_END,
            "pinned_sha256": sha256_bytes(masked(ram)[:RAM_PINNED_END]),
            "page_sha256": page_hashes(ram),
        },
    }
    (prefix.parent / f"{prefix.name}-metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    # HERE AND NOT IN A MODE: a black screen is a run that did not happen, and a golden or a
    # comparison that reached the mode's own check would already have pinned or diffed it.
    if metrics["screen"]["distinct_colours"] <= BLANK_SCREEN_COLOURS:
        refuse(f"the screenshot under {rom} holds one colour — nothing painted, whatever else the "
               f"run reported; see {prefix}-screen.png")
    return metrics


# ---- the modes -----------------------------------------------------------------------------------------

def settled(metrics):
    """Did the machine stand still between the stop and the settle shot? The stop rule is a fixed
    vblank count, and this is the failure a fixed count can have — so it is a VERDICT, not a note."""
    settle = metrics["settle"]
    return settle["screen_still"] and settle["ram_still"]


def describe(metrics):
    metric, settle, rom = metrics["boot_metric"], metrics["settle"], metrics["instrument"]["rom"]
    clocks = " ".join(f"{name}={metric[name]}" for name, _why in sysvars.TIME_VARYING)
    return (f"  ROM {rom['version']}  sha256 {rom['sha256'][:16]}...\n"
            f"  boot metric at vblank {metric['stop_vbl']}: {clocks}\n"
            f"  screen: {metrics['screen']['distinct_colours']} distinct colours\n"
            f"  settled by vblank {settle['settle_vbl']}: screen "
            f"{'still' if settle['screen_still'] else 'MOVING'}, pinned RAM "
            f"{'still' if settle['ram_still'] else 'MOVING at ' + ', '.join(settle['ram_moved_at'])}")


def do_capture(rom, disk, prefix):
    metrics = capture(rom, disk, prefix, "boot-capture.log")
    print(f"capture of {rom} -> {prefix}-*")
    print(describe(metrics))
    if not settled(metrics):
        print(f"\nUNSETTLED: the machine was still moving at vblank {SETTLE_VBL}, so this capture "
              f"is of a moment and not of a booted machine.")
        return 1
    return 0


def artefact_differences(first, second):
    """Which of a capture's artefacts differ between two prefixes, and the text diff of each.

    A missing file REFUSES rather than counting as a difference: a golden artefact that is not there
    is a broken golden, and reporting it as "this ROM differs" would be a lie about the ROM.
    """
    require_files(*[(Path(f"{prefix}-{name}"), "a capture artefact the comparison needs "
                                               "(cut the golden again: `make golden`)")
                    for prefix in (first, second) for name in GOLDEN_ARTEFACTS])
    report = []
    for name in GOLDEN_ARTEFACTS:
        left = Path(f"{first}-{name}")
        right = Path(f"{second}-{name}")
        if left.read_bytes() == right.read_bytes():
            continue
        if name.endswith(".txt"):
            diff = list(difflib.unified_diff(left.read_text().splitlines(),
                                             right.read_text().splitlines(),
                                             str(left), str(right), lineterm="", n=1))
            report.append((name, "\n".join(diff[:60])))
        else:
            report.append((name, f"{len(left.read_bytes())} vs {len(right.read_bytes())} bytes, "
                                 f"sha256 {sha256_bytes(left.read_bytes())[:16]} vs "
                                 f"{sha256_bytes(right.read_bytes())[:16]}"))
    return report


def do_golden(rom, disk):
    """Two boots, and the golden is only written if they agree — the reproducibility claim is made
    by the same invocation that would depend on it, rather than by a comment."""
    first = capture(rom, disk, OUT / "golden-run1", "boot-golden1.log")
    second = capture(rom, disk, OUT / "golden-run2", "boot-golden2.log")
    print(f"golden candidate from {rom}")
    print(describe(first))
    pages = page_differences(first, second)
    print(f"  RAM pages the two boots differ on above the pinned window (reported, not pinned): "
          f"{', '.join(pages) if pages else 'none'}")

    material = [(name, text) for name, text in artefact_differences(OUT / "golden-run1",
                                                                   OUT / "golden-run2")
                if name != "metrics.json"]
    # ...and metrics.json compared by what it MEASURES rather than byte for byte: its reported half
    # (the clocks, the unpinned page hashes) is expected to move between two boots.
    material += metrics_differences(first, second)
    if material:
        print("\nTWO BOOTS OF THE SAME ROM DISAGREE — no golden written:")
        for name, text in material:
            print(f"\n-- {name}\n{text}")
        return 1
    if not settled(first) or not settled(second):
        print(f"\nUNSETTLED at vblank {SETTLE_VBL} — no golden written: a golden of a machine that "
              f"was still moving pins a moment, and the next capture would differ from it for that "
              f"reason alone.")
        return 1
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for name in GOLDEN_ARTEFACTS:
        (GOLDEN / f"boot-{name}").write_bytes((OUT / f"golden-run1-{name}").read_bytes())
    print(f"\ntwo boots agree on every pinned, unmasked byte and both settled -> golden/boot-* "
          f"written ({len(GOLDEN_ARTEFACTS)} files)")
    return 0


def do_compare(rom, disk):
    metrics = capture(rom, disk, OUT / "compare", "boot-compare.log")
    golden_metrics = GOLDEN / "boot-metrics.json"
    require_files((golden_metrics, "the golden to compare against — run `boot_surface.py golden`"))
    reference = json.loads(golden_metrics.read_text())
    moved = hatari_rom.instrument_differences(reference.get("instrument"), metrics["instrument"])
    if moved:
        refuse("this run was not taken with the golden's instrument, so any difference below would "
               "be the instrument's and not the ROM's:\n    " + "\n    ".join(moved))

    print(f"compare {rom} against golden/")
    print(describe(metrics))
    print(f"\n  golden boot metric: {reference['boot_metric']}")
    print(f"  this ROM's        : {metrics['boot_metric']}")
    pages = page_differences(reference, metrics)
    print(f"  RAM pages differing above the pinned window (not pinned, reported only): "
          f"{', '.join(pages) if pages else 'none'}")

    differences = [(name, text) for name, text in artefact_differences(GOLDEN / "boot",
                                                                       OUT / "compare")
                   if name != "metrics.json"]
    differences += metrics_differences(reference, metrics)
    if not differences:
        print("\nEVERY PINNED SURFACE IS IDENTICAL.")
        return 0
    print(f"\n{len(differences)} surface(s) differ:")
    for name, text in differences:
        print(f"\n-- {name}\n{text}")
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("capture", "golden", "compare"))
    parser.add_argument("--rom", default=str(hatari_rom.ORIGINAL_ROM),
                        help="the ROM image to boot (default: the original TOS102US.img)")
    parser.add_argument("--disk", default=str(hatari_rom.BLANK_DISK),
                        help="the floppy image in drive A (default: build/BLANK.ST)")
    parser.add_argument("--out",
                        help="capture mode only: the path prefix every artefact is written under")
    arguments = parser.parse_args()
    require_files((arguments.rom, "the ROM"), (arguments.disk, "the floppy (make disks)"))
    OUT.mkdir(parents=True, exist_ok=True)
    prefix = capture_prefix(arguments.mode, arguments.out, OUT / "boot")
    if arguments.mode == "capture":
        return do_capture(arguments.rom, arguments.disk, prefix)
    if arguments.mode == "golden":
        return do_golden(arguments.rom, arguments.disk)
    return do_compare(arguments.rom, arguments.disk)


if __name__ == "__main__":
    sys.exit(main())
