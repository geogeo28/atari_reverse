#!/usr/bin/env python3
"""ledger_run.py — booting a ROM with one of the conformance programs on the floppy, and reading the
block of RAM it leaves behind. Shared by tostest.py and tosbench.py, which differ only in what the
three longwords of a record MEAN and in what a comparison of them is allowed to demand.

THE LEDGER'S SHAPE IS NOT SPELLED TWICE. Every constant below is read out of `prg/ledger.h` at
import time (`cdefines.py` is the parser, shared with the other headers this directory reads), so
the C the program is compiled from and the Python that parses its output cannot disagree about an
offset. A field added to the header is a field this file sees; a field renamed here and not there
fails loudly at import rather than quietly at offset 12.

HOW A RUN IS SYNCHRONISED. The program writes its records and then its magic, and the host breaks on
the magic: when the longword at LEDGER_ADDR reads 'TOSL', everything behind it has landed. The
breakpoint's condition is NOT QUOTED — a quoted expression is evaluated when the script is parsed,
which would read the still-zero longword and arm a breakpoint on the constant 0 — and it cannot be
armed at startup either, because Hatari has not sized RAM at power-on and refuses a condition on a
RAM address. So a vblank breakpoint arms the memory breakpoint, which fires the capture. Three
scripts, one per hop, each because the hop before it is the only thing that can arm it.

THE PROGRAM NEVER TERMINATES. Both programs spin after publishing, so the machine the host reads is
standing exactly where the last record was written: no desktop has redrawn the screen the ledger
measured, and no later allocation has reused the block. The run ends on `--run-vbls`.
"""
import json
import struct
import sys
from pathlib import Path

import cdefines
import hatari_rom
from hatari_rom import (BLANK_SCREEN_COLOURS, GOLDEN, OUT, breakpoint_script, file_clause,
                        instrument_identity, refuse, require_files, sha256_bytes)

sys.path.insert(0, str(hatari_rom.REPO / "tools"))
from hatari_headless import distinct_colours      # noqa: E402

LEDGER_HEADER = hatari_rom.HERE / "prg" / "ledger.h"

# Late enough that Hatari has sized RAM (a memory breakpoint armed at power-on is refused), early
# enough that neither program has published anything — the AUTO folder does not run until the boot
# has read the disk, which is hundreds of vblanks in.
ARM_VBL = 60
# Outlasts the slowest workload by a wide margin. TOSBENCH's 64 KB floppy read is the long one, and
# an emulated floppy is emulated at a real floppy's speed; under --fast-forward the margin is nearly
# free, and a run cut off mid-workload publishes no magic and fails loudly rather than quietly.
RUN_VBLS = 6000

_DEFINES = cdefines.defines(LEDGER_HEADER)
LEDGER_ADDR = _DEFINES["LEDGER_ADDR"]
LEDGER_MAGIC = _DEFINES["LEDGER_MAGIC"]
LEDGER_VERSION = _DEFINES["LEDGER_VERSION"]
LEDGER_KIND_TEST = _DEFINES["LEDGER_KIND_TEST"]
LEDGER_KIND_BENCH = _DEFINES["LEDGER_KIND_BENCH"]
LEDGER_MAX_RECORDS = _DEFINES["LEDGER_MAX_RECORDS"]
LEDGER_NAME_BYTES = _DEFINES["LEDGER_NAME_BYTES"]
LEDGER_BLOB_BYTES = _DEFINES["LEDGER_BLOB_BYTES"]
LEDGER_HEADER_BYTES = _DEFINES["LEDGER_HEADER_BYTES"]
LEDGER_RECORD_BYTES = _DEFINES["LEDGER_RECORD_BYTES"]
FLAG_MASKED = _DEFINES["LEDGER_FLAG_MASKED"]
FLAG_FAILED = _DEFINES["LEDGER_FLAG_FAILED"]
FLAG_BLOB = _DEFINES["LEDGER_FLAG_BLOB"]

# What the debugger reads back: the header plus every record the block can hold, so the window never
# has to move when a program grows.
CAPTURE_BYTES = LEDGER_HEADER_BYTES + LEDGER_MAX_RECORDS * LEDGER_RECORD_BYTES

HEADER_FORMAT = ">8I"
RECORD_FORMAT = f">HH3I{LEDGER_NAME_BYTES}s{LEDGER_BLOB_BYTES}s"
HEADER_FIELDS = ("magic", "version", "kind", "record_count", "record_bytes", "status",
                 "rom_version", "reserved")

KIND_NAMES = {LEDGER_KIND_TEST: "TEST", LEDGER_KIND_BENCH: "BNCH"}


# ---- running --------------------------------------------------------------------------------------

def capture_scripts(work, screen_png, ledger_bin):
    capture = breakpoint_script(work / "capture.txt",
                                f"screenshot {screen_png}",
                                f"savebin {ledger_bin} ${LEDGER_ADDR:x} {CAPTURE_BYTES}")
    watch = breakpoint_script(
        work / "watch.txt",
        f"b (${LEDGER_ADDR:x}).l = ${LEDGER_MAGIC:x} :once :quiet {file_clause(capture)}")
    return breakpoint_script(work / "arm.txt", f"b VBL > {ARM_VBL} :once :quiet {file_clause(watch)}")


def run(rom, disk, work, log_path):
    """Boot `rom` with `disk` in drive A and return (ledger bytes, screenshot bytes, png path)."""
    work.mkdir(parents=True, exist_ok=True)
    screen_png, ledger_bin = work / "screen.png", work / "ledger.bin"
    for path in (screen_png, ledger_bin):
        path.unlink(missing_ok=True)
    arm = capture_scripts(work, screen_png, ledger_bin)
    hatari_rom.boot(rom, disk, RUN_VBLS, arm, log_path)
    if not ledger_bin.is_file():
        refuse(f"the program under {rom} never published its ledger magic within {RUN_VBLS} "
               f"vblanks — see {log_path}")
    return ledger_bin.read_bytes(), screen_png.read_bytes(), screen_png


# ---- parsing ---------------------------------------------------------------------------------------

def parse(data, expected_kind):
    """The ledger as (header dict, list of record dicts), refusing anything that is not this
    program's. Every check here is a way a capture can be silently wrong rather than absent."""
    if len(data) < LEDGER_HEADER_BYTES:
        refuse(f"the ledger capture is {len(data)} bytes, shorter than its {LEDGER_HEADER_BYTES}-byte header")
    header = dict(zip(HEADER_FIELDS, struct.unpack_from(HEADER_FORMAT, data, 0)))
    if header["magic"] != LEDGER_MAGIC:
        refuse(f"ledger magic {header['magic']:#x}, expected {LEDGER_MAGIC:#x}")
    if header["version"] != LEDGER_VERSION:
        refuse(f"ledger version {header['version']}, this parser knows {LEDGER_VERSION}")
    if header["kind"] != expected_kind:
        refuse(f"this ledger was written by {KIND_NAMES.get(header['kind'], hex(header['kind']))}, "
               f"not {KIND_NAMES[expected_kind]} — the wrong floppy is in the drive")
    if header["record_bytes"] != LEDGER_RECORD_BYTES:
        refuse(f"the program writes {header['record_bytes']}-byte records and this parser reads "
               f"{LEDGER_RECORD_BYTES}-byte ones")
    if not 0 < header["record_count"] <= LEDGER_MAX_RECORDS:
        refuse(f"the ledger reports {header['record_count']} records")

    records = []
    for index in range(header["record_count"]):
        at = LEDGER_HEADER_BYTES + index * LEDGER_RECORD_BYTES
        identifier, flags, v0, v1, v2, name, blob = struct.unpack_from(RECORD_FORMAT, data, at)
        records.append({
            "index": index, "id": identifier, "flags": flags,
            "v0": v0, "v1": v1, "v2": v2,
            "name": name.rstrip(b"\0").decode("ascii", "replace"),
            "blob": blob.hex(),
        })
    return header, records


def flag_text(flags):
    marks = []
    if flags & FLAG_MASKED:
        marks.append("masked")
    if flags & FLAG_FAILED:
        marks.append("FAILED")
    if flags & FLAG_BLOB:
        marks.append("blob")
    return ",".join(marks) if marks else "-"


def render(header, records, columns, title):
    """The ledger as text: one line per record, with `columns` naming what v0/v1/v2 mean here."""
    lines = [
        f"# {title}",
        f"# kind={KIND_NAMES.get(header['kind'], hex(header['kind']))} version={header['version']} "
        f"records={header['record_count']} status={header['status']} "
        f"ROM version={header['rom_version']:#06x}",
        f"# index  id      name      flags          {columns[0]:>12}  {columns[1]:>12}  "
        f"{columns[2]:>12}  blob",
    ]
    for record in records:
        lines.append(f"  {record['index']:>5}  {record['id']:#06x}  {record['name']:<8}  "
                     f"{flag_text(record['flags']):<13}  {record['v0']:>12}  {record['v1']:>12}  "
                     f"{record['v2']:>12}  {record['blob']}")
    return "\n".join(lines) + "\n"


def comparable(records):
    """The part of a ledger two ROMs must agree on: every field of every unmasked record.

    A masked record keeps its id, name and flags — a timing whose row VANISHED or was renamed is a
    difference even though its number is not.
    """
    return [(record["id"], record["name"], record["flags"] & ~FLAG_FAILED)
            if record["flags"] & FLAG_MASKED
            else (record["id"], record["name"], record["flags"], record["v0"], record["v1"],
                  record["v2"], record["blob"])
            for record in records]


# ---- a capture ------------------------------------------------------------------------------------

def capture(rom, disk, kind, prefix, columns, title, log_name, program=None):
    """One boot; writes <prefix>-ledger.txt, <prefix>-screen.png and <prefix>-metrics.json.

    The work directory is named after the OUTPUT PREFIX and not after the program, because
    tosbench.py runs several captures AT ONCE: two runs sharing one `arm.txt` and one `screen.png`
    is the collision boot_surface.py's own comment warns about, made concurrent.
    """
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    work = OUT / f"work-{prefix.name}"
    data, screen, screen_path = run(rom, disk, work, OUT / log_name)
    header, records = parse(data, kind)

    (prefix.parent / f"{prefix.name}-ledger.txt").write_text(render(header, records, columns, title))
    (prefix.parent / f"{prefix.name}-screen.png").write_bytes(screen)
    metrics = {
        "instrument": instrument_identity(rom, disk, program),
        "header": header,
        "records": records,
        "screen": {"sha256": sha256_bytes(screen),
                   "distinct_colours": distinct_colours(screen_path)},
    }
    (prefix.parent / f"{prefix.name}-metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    if metrics["screen"]["distinct_colours"] <= BLANK_SCREEN_COLOURS:
        refuse("the screenshot holds one colour — the machine drew nothing, whatever the ledger says")
    return metrics


def write_golden(prefix, stem, names=("ledger.txt", "screen.png", "metrics.json")):
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for name in names:
        (GOLDEN / f"{stem}-{name}").write_bytes(Path(f"{prefix}-{name}").read_bytes())
    return [f"{stem}-{name}" for name in names]


def golden_metrics(stem):
    path = GOLDEN / f"{stem}-metrics.json"
    require_files((path, "the golden to compare against — run the driver's `golden` mode first"))
    return json.loads(path.read_text())


def failures(header, records):
    """Why a run is not a reading: the program's own status word, and every row it marked FAILED.

    A workload that failed still WRITES A NUMBER — the loop it did not finish took some time to not
    finish — so a comparison that ignores the flag compares a broken run against a good one and
    calls the difference performance.
    """
    reasons = []
    if header["status"] != 0:
        reasons.append(f"the program reported status {header['status']}: a call did not do what it "
                       f"asked")
    failed = [record["name"] for record in records if record["flags"] & FLAG_FAILED]
    if failed:
        reasons.append(f"{len(failed)} row(s) are marked FAILED: {', '.join(failed)}")
    return reasons
