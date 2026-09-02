#!/usr/bin/env python3
"""Write disk/ZYNAPS.ST — a bootable Atari floppy carrying OUR .PRG where the game's used to be.

    python3 atari/mkfloppy.py --prg build/ZYNAPS-floppy.PRG --root disk --out disk/ZYNAPS.ST

`build.sh floppy` calls this last, when the staged drive is already complete. THE FILESYSTEM IS NOT
THIS FILE'S — `tools/st_build.py` is the workspace's FAT12 writer and does all of it: two FATs, the
`\\AUTO\\` subdirectory, a deterministic image, a sha256, and the one thing that matters on a real
machine and that `mformat` cannot promise — a boot sector TOS will MOUNT AND NOT EXECUTE. (TOS runs
sector 0 when its 256 big-endian words sum to $1234; `st_build` picks a serial that makes the sum
come out wrong on purpose and then asserts it. An `mformat` image satisfies that by luck, 65,535
times in 65,536.) What is left here is what is about ZYNAPS: which files, under which names.

THE TWO NAMES THE MACHINE INSISTS ON. The loader is the DESKTOP's `\\AUTO\\` scan, so our program has
to be `AUTO\\ZYNAPS17.PRG` — the name the original ships — and the data files have to sit in the
ROOT, because the game opens them by BARE NAME against whatever drive it was booted from
(../../README.md, "The GEMDOS folder works because the game opens its files by bare name").

WHAT IS ON IT THAT THE ORIGINAL DISK HAS NOT. `ZYNAPS.IMG`, the relocated game image the shim stages
into its own array — the original needs no such file because it IS the game — and room for the three
files a run writes back (`SCREEN.BIN`, `STATE.BIN`, `BASE.BIN`). The last of those is asserted
against the finished volume's free space rather than assumed, because a run that cannot write its
record produces no record and every check downstream of it reports the wrong thing.

WHAT IS NOT THE ORIGINAL'S: the geometry. The original disk is 80x1x10x512 = 400 KB, and this is
`st_build`'s 720 KB double-sided — which that file argues for on its own terms (it is what
`gw/README.md` prescribes for an unprotected disk, and the 10- and 11-sector formats hold more but
are the ones a drive that is not the one they were written on can fail to read). 400 KB could not
have held this build in any case: 423 clusters of payload against a single-sided volume's 393.
The cost is that a single-sided drive cannot read this disk; the machine it is for is an STE.

VERIFIED BY A DIFFERENT READER FROM THE ONE THAT WROTE IT. `st_build` writes the volume; the check
below reads it back with `st_extract.py`'s parser and compares every file's bytes against the source
it came from. A writer verified by its own library agrees with itself.
"""
import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]                      # projects/zynaps
REPO = PROJECT.parents[1]
sys.path.insert(0, str(REPO / "tools"))

import st_build                                                        # noqa: E402
import st_extract                                                      # noqa: E402

CORE_INCLUDE = PROJECT / "recreate" / "include"

AUTO_DIR = "AUTO"
# The desktop runs every `\AUTO\*.PRG`, and this is the name the original ships. Keeping it is what
# makes the disk boot into our build with nothing else changed.
AUTO_PRG = "ZYNAPS17.PRG"

# `zynaps_main.c`'s four FILE_* constants, split by who writes them. ZYNAPS.IMG is staged onto the
# drive by build.sh and goes on the volume; the other three are WRITTEN BY THE RUN, so what the
# volume owes them is free space.
STAGED_IMAGE = "ZYNAPS.IMG"
RUN_OUTPUT_FILES = ("SCREEN.BIN", "STATE.BIN", "BASE.BIN")
# ...and how much. ONE of the three has a size worth knowing and it is not typed here: SCREEN.BIN is
# a whole framebuffer, and `../include/video.h` is where that number is defined for the cores, the
# shim and this file alike (CLAUDE.md §5 — one source of truth across a language boundary). The
# other two are a few hundred bytes and a longword, and what they cost a FAT12 volume is one cluster
# each whatever their length, which is what `clusters_the_run_needs` charges them.
SCREEN_BYTES_CONSTANT = "SCREEN_BYTES"

# The staged drive is a GEMDOS drive, not a floppy, and one of its entries does not belong on this
# volume: the ROOT copy of our .PRG. `smoke.py`'s GEMDOS modes start that one with
# `--auto C:\ZYNAPS.PRG`; here the desktop runs AUTO\ZYNAPS17.PRG, and a second 42 KB copy at the
# root would cost 42 clusters for nothing.
ROOT_PRG_COPY = "ZYNAPS.PRG"

# What `st_build` puts in the root besides the files: a volume label, and the AUTO directory whose
# own entry lives there while its contents do not. Both cost a root slot, and the run's three output
# files need three more.
VOLUME_LABEL_SLOTS = 1
AUTO_DIRECTORY_SLOTS = 1


def screen_dump_bytes():
    """`SCREEN_BYTES` out of ../include/video.h — the framebuffer the run writes back."""
    header = (CORE_INCLUDE / "video.h").read_text()
    match = re.search(rf"^#define\s+{SCREEN_BYTES_CONSTANT}\s+(\d+)u?\b", header, re.MULTILINE)
    if not match:
        raise SystemExit(f"ERROR: no {SCREEN_BYTES_CONSTANT} in {CORE_INCLUDE / 'video.h'} — the "
                         f"free-space check has nothing to size the framebuffer dump against")
    return int(match.group(1))


def clusters_the_run_needs():
    """What the three files a run writes back cost the volume, in whole clusters.

    Cluster rounding is part of what the volume owes: a 4-byte BASE.BIN starts a cluster exactly as
    a 32000-byte SCREEN.BIN starts thirty-two of them. A disk that cannot take STATE.BIN produces no
    record at all, and every check downstream of it reads that as a crash.
    """
    per_file = [screen_dump_bytes()] + [1] * (len(RUN_OUTPUT_FILES) - 1)
    return sum(max(1, -(-size // st_build.CLUSTER_BYTES)) for size in per_file)


def root_files(staged_drive, prg, image_path):
    """The staged drive's files that belong in the volume's root, and nothing else."""
    not_on_the_volume = set(RUN_OUTPUT_FILES) | {ROOT_PRG_COPY, prg.name}
    out_path = image_path.resolve()
    chosen = sorted(candidate for candidate in staged_drive.iterdir()
                    if candidate.is_file() and candidate.name not in not_on_the_volume
                    and candidate.resolve() != out_path)
    if not any(candidate.name == STAGED_IMAGE for candidate in chosen):
        raise SystemExit(f"ERROR: {STAGED_IMAGE} is not in {staged_drive} — run build.sh first")
    return chosen


def verify(image_path, expected):
    """Read the finished image back with st_extract's parser and compare it to what went in.

    `expected` maps the path ON THE VOLUME to the host file it was written from. Both halves are
    checked: no file on the volume that was not asked for, and every one byte-for-byte.

    The parser's `warnings` are inspected LAST, because st_extract fills most of them from inside
    `walk` and `read_file` — a chain that loops, one that runs into a bad-cluster marker, one whose
    length disagrees with its directory entry. Checked before the read they would always be empty.
    """
    volume = st_extract.Fat12Image(image_path.read_bytes())
    on_volume = {entry["path"]: entry for entry in st_extract.walk(volume) if not entry["is_dir"]}
    missing = sorted(set(expected) - set(on_volume))
    extra = sorted(set(on_volume) - set(expected))
    if missing or extra:
        raise SystemExit(f"ERROR: {image_path.name}: missing {missing}, unexpected {extra}")

    for path, source in sorted(expected.items()):
        want = source.read_bytes()
        got = st_extract.read_file(volume, path)
        if got == want:
            continue
        if got is None or len(got) != len(want):
            length = "absent" if got is None else f"{len(got)} bytes"
            raise SystemExit(f"ERROR: {image_path.name}: {path} is {length}, "
                             f"{source} is {len(want)} bytes")
        first = next(index for index, (a, b) in enumerate(zip(got, want)) if a != b)
        raise SystemExit(f"ERROR: {image_path.name}: {path} differs from {source} at byte {first}")

    for warning in volume.warnings:
        raise SystemExit(f"ERROR: {image_path.name}: {warning}")
    return on_volume


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prg", type=Path, required=True, help="the .PRG to put in AUTO\\")
    parser.add_argument("--root", type=Path, required=True,
                        help="the staged drive whose files become the volume's root")
    parser.add_argument("--out", type=Path, required=True, help="the .ST image to write")
    args = parser.parse_args()

    files = root_files(args.root, args.prg, args.out)
    layout = st_build.build(args.out,
                            root_files=[(source.name, source) for source in files],
                            auto_files=[(AUTO_PRG, args.prg)])

    expected = {f"{AUTO_DIR}/{AUTO_PRG}": args.prg}
    expected.update({source.name: source for source in files})
    on_volume = verify(args.out, expected)

    needed = clusters_the_run_needs()
    print(f">> {args.out}: {len(on_volume)} files verified against {args.root} byte for byte")
    print(f"   {AUTO_DIR}\\{AUTO_PRG} = {args.prg.name} ({args.prg.stat().st_size} B), "
          f"{len(on_volume) - 1} files in the root")
    print(f"   {layout.used_bytes} B used, {layout.free_bytes} B free; the run writes back "
          f"{len(RUN_OUTPUT_FILES)} files in {needed} clusters")
    print(f"   sha256 {layout.digest}")
    if layout.free_bytes < needed * st_build.CLUSTER_BYTES:
        raise SystemExit(f"ERROR: the run needs {needed} clusters for its output and the volume has "
                         f"{layout.free_bytes // st_build.CLUSTER_BYTES}")
    # ...AND A ROOT SLOT EACH, which is a different resource and runs out first on a disk with many
    # small files. A FAT12 root is a FIXED number of entries; a volume with 300 KB free and no slot
    # left fails the run's `Fcreate` exactly as a full one does, and the check above would not see
    # it. `on_volume` counts the files; the volume label and the AUTO directory take a slot each.
    root_entries = len(on_volume) - 1        # AUTO\ZYNAPS17.PRG's slot is in the subdirectory
    used_slots = root_entries + VOLUME_LABEL_SLOTS + AUTO_DIRECTORY_SLOTS
    free_slots = st_build.ROOT_ENTRIES - used_slots
    if free_slots < len(RUN_OUTPUT_FILES):
        raise SystemExit(f"ERROR: the run creates {len(RUN_OUTPUT_FILES)} files and the root has "
                         f"{free_slots} of its {st_build.ROOT_ENTRIES} entries left")


if __name__ == "__main__":
    main()
