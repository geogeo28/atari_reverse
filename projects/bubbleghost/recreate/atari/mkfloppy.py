#!/usr/bin/env python3
"""Write the Atari floppies this build needs: the A: data volume, and a bootable one.

    python3 atari/mkfloppy.py --data disk/a --out disk/GHOST.ST
    python3 atari/mkfloppy.py --prg build/BUBBLE-title.PRG --data disk/a \\
                             --image disk/c/GHOST.IMG --out disk/BUBBLE.ST

TWO VOLUMES, AND THE FIRST IS NOT OPTIONAL. Bubble Ghost opens three of its six files as
"A:GHOST.DAT", "A:GHOST.PRE" and "A:GHOST.DEM" — a hard-coded DRIVE LETTER in the program's own
data segment, not a build-time choice — so even the GEMDOS-drive run needs a floppy in A: with
those files on it. `--data` alone writes that volume. The other three names ("GHOST.LOA",
"GHOST.VOI" and the shim's own "GHOST.IMG") carry no drive and open on whatever drive the program
was started from, which is why the bootable volume needs them in its root as well.

THE FILESYSTEM IS NOT THIS FILE'S. `tools/st_build.py` is the workspace's FAT12 writer and does all
of it: two FATs, the `\\AUTO\\` subdirectory, a deterministic image, a sha256, and the one thing
that matters on a real machine and that `mformat` cannot promise — a boot sector TOS will MOUNT AND
NOT EXECUTE. (TOS runs sector 0 when its 256 big-endian words sum to $1234; `st_build` picks a
serial that makes the sum come out wrong on purpose and then asserts it.) What is left here is what
is about BUBBLE GHOST: which files, under which names.

THIS DISK DOES NOT AUTOSTART, AND NEITHER DOES THE ORIGINAL'S. The shipped disk boots to the
desktop and waits for a double-click — its French DESKTOP.INF has no autostart line and there is no
AUTO folder — and this one is written the same way, because BOTH ways of changing that were tried
and MEASURED as failures (the `DESKTOP_INF_TEXT` comment below has the two). In short: TOS runs an
`\\AUTO\\` program before GEM exists and this is a GEM application whose second act is `appl_init`,
and TOS 1.04's desktop reads a `#Z` line without acting on it. So the game is started by a person,
as the original's is; `atari/smoke.py floppy` checks the BOOT, which is the part that has no
double-click in it.

VERIFIED BY A DIFFERENT READER FROM THE ONE THAT WROTE IT: `st_build` writes the volume and
`st_extract`'s parser reads it back, comparing every file against the source it came from. A writer
verified by its own library agrees with itself.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]                      # projects/bubbleghost
REPO = PROJECT.parents[1]
sys.path.insert(0, str(REPO / "tools"))

import st_build                                                        # noqa: E402
import st_extract                                                      # noqa: E402

# The name is ours rather than the original's `GHOST.PRG`, so that a person looking at the directory
# can tell which program they booted — and so that this disk could carry both.
BOOT_PRG = "BUBBLE.PRG"
DESKTOP_INF = "DESKTOP.INF"

# THE DESKTOP PREFERENCES, AND THE AUTOSTART THAT IS NOT THERE. This is the ORIGINAL DISK's own
# DESKTOP.INF, byte for byte bar the drive its `#W` line names — including its French trash can,
# because it is the original's file and not a new one. It is written so the disk boots the way the
# shipped one boots (../../tools/boot_ghost.py: "no autostart in its French DESKTOP.INF, so a real
# machine needs a double-click"), and not to make anything happen.
#
# WHAT THE `#W` LINE DOES NOT DO, measured by `atari/smoke.py floppy` and written here because the
# first draft of this comment claimed the opposite: it does NOT open a directory window on `A:\*.*`
# under TOS 1.04. The desktop reads the file — its `Fopen` is in the GEMDOS trace — and comes up
# with its two drive icons and the trash and no window at all, at three seconds after the read and
# at fifteen. So the game is two double-clicks away (the drive, then the .PRG), not one.
#
# AN AUTOSTART WAS TRIED AND MEASURED, twice, and neither works for THIS program:
#   * `\AUTO\BUBBLE.PRG` — TOS runs an AUTO-folder program BEFORE GEM exists, and this is a GEM
#     application whose second act is `appl_init`. The run reached nothing at all: no record, no
#     first file, and a disk that came back carrying only what was written on it.
#   * a `#Z 01 A:\BUBBLE.PRG@` line in this file — TOS 1.04's desktop READ the .INF (the GEMDOS
#     trace shows its Fopen) and made no `Pexec` of the program. The line is a later desktop's.
# So the disk boots to the desktop and the game is started by a person, as the original's is. What
# that costs is that no headless check runs the FLOPPY path end to end; atari/README.md's "Unpinned"
# says so rather than implying the medium is covered.
DESKTOP_INF_TEXT = """#a000000
#b000000
#c7770007000600070055200505552220770557075055507703111103
#d                                             
#E 1B 01 
#W 01 01 10 07 0A 09 08 A:\\*.*@
#W 00 00 0D 08 15 0B 00 @
#W 00 00 0E 09 15 0B 00 @
#W 00 00 0F 0A 15 0B 00 @
#T 00 03 02 FF   CORBEILLE@ @ 
#F FF 04   @ *.*@ 
#D FF 01   @ *.*@ 
#G 03 FF   *.PRG@ @ 
#G 03 FF   *.APP@ @ 
#F 03 04   *.TOS@ @ 
"""

# What a run writes back, and what the volume therefore owes in FREE SPACE and ROOT SLOTS rather
# than in files. `bubble_main.c`'s four FILE_* constants, minus the one that is staged.
RUN_OUTPUT_FILES = ("SCREEN.BIN", "STATE.BIN", "BASE.BIN")
SCREEN_DUMP_BYTES = 32000        # ../include/blit.h's SCREEN_BYTES; see `screen_dump_bytes`
VOLUME_LABEL_SLOTS = 1

CORE_INCLUDE = PROJECT / "recreate" / "include"
SCREEN_BYTES_CONSTANT = "SCREEN_BYTES"


def screen_dump_bytes():
    """`SCREEN_BYTES` out of ../include/blit.h — the framebuffer a run writes back.

    Scraped rather than typed: it is the cores' own constant and this file must not become a second
    home for it (CLAUDE.md §5). The literal above is only what the docstring quotes.
    """
    import re
    header = (CORE_INCLUDE / "blit.h").read_text()
    match = re.search(rf"^#define\s+{SCREEN_BYTES_CONSTANT}\s+(\d+)u?\b", header, re.MULTILINE)
    if not match:
        raise SystemExit(f"ERROR: no {SCREEN_BYTES_CONSTANT} in {CORE_INCLUDE / 'blit.h'} — the "
                         f"free-space check has nothing to size the framebuffer dump against")
    return int(match.group(1))


def clusters_the_run_needs():
    """What the three files a run writes back cost the volume, in whole clusters.

    Cluster rounding is part of what the volume owes: a 4-byte BASE.BIN starts a cluster exactly as
    a 32,000-byte SCREEN.BIN starts thirty-two of them. A disk that cannot take STATE.BIN produces
    no record at all, and every check downstream of it reads that as a crash.
    """
    per_file = [screen_dump_bytes()] + [1] * (len(RUN_OUTPUT_FILES) - 1)
    return sum(max(1, -(-size // st_build.CLUSTER_BYTES)) for size in per_file)


def verify(image_path, expected):
    """Read the finished image back with st_extract's parser and compare it to what went in."""
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
    # The parser's warnings are inspected LAST: st_extract fills most of them from inside `walk` and
    # `read_file`, so checked before the read they would always be empty.
    for warning in volume.warnings:
        raise SystemExit(f"ERROR: {image_path.name}: {warning}")
    return on_volume


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True,
                        help="the directory of GHOST.* files that becomes the volume's root")
    parser.add_argument("--prg", type=Path,
                        help="the .PRG to put in the volume's root, with a DESKTOP.INF beside it")
    parser.add_argument("--image", type=Path, help="the staged program image the shim reads back")
    parser.add_argument("--out", type=Path, required=True, help="the .ST image to write")
    args = parser.parse_args()

    root = sorted(path for path in args.data.iterdir() if path.is_file())
    if not root:
        raise SystemExit(f"ERROR: {args.data} holds no data files — run build.sh first")
    if args.image:
        root.append(args.image)

    inf = None
    if args.prg:
        inf = args.out.parent / DESKTOP_INF
        inf.write_text(DESKTOP_INF_TEXT)
        root += [args.prg, inf]

    layout = st_build.build(args.out,
                            root_files=[(BOOT_PRG if source is args.prg else source.name, source)
                                        for source in root])

    expected = {(BOOT_PRG if source is args.prg else source.name): source for source in root}
    on_volume = verify(args.out, expected)

    bootable = "bootable" if args.prg else "data only"
    print(f">> {args.out.name}: {len(on_volume)} files verified against {args.data} byte for byte "
          f"({bootable})")
    print(f"   {layout.used_bytes} B used, {layout.free_bytes} B free")
    print(f"   sha256 {layout.digest}")

    if not args.prg:
        return                     # nothing runs from this volume, so it owes the run nothing
    needed = clusters_the_run_needs()
    if layout.free_bytes < needed * st_build.CLUSTER_BYTES:
        raise SystemExit(f"ERROR: the run needs {needed} clusters for its output and the volume has "
                         f"{layout.free_bytes // st_build.CLUSTER_BYTES}")
    # ...AND A ROOT SLOT EACH, which is a different resource and runs out first on a disk with many
    # small files. A FAT12 root is a FIXED number of entries; a volume with 300 KB free and no slot
    # left fails the run's `Fcreate` exactly as a full one does.
    used_slots = len(on_volume) + VOLUME_LABEL_SLOTS
    free_slots = st_build.ROOT_ENTRIES - used_slots
    if free_slots < len(RUN_OUTPUT_FILES):
        raise SystemExit(f"ERROR: the run creates {len(RUN_OUTPUT_FILES)} files and the root has "
                         f"{free_slots} of its {st_build.ROOT_ENTRIES} entries left")
    print(f"   the run writes back {len(RUN_OUTPUT_FILES)} files in {needed} clusters, "
          f"{free_slots} root slots free")


if __name__ == "__main__":
    main()
