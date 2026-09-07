#!/usr/bin/env python3
"""Write disk/FLYSHARK.ST — a bootable Atari floppy carrying OUR .PRG where the game's used to be.

    python3 atari/mkfloppy.py --prg build/FLYSHARK.PRG --root disk --out disk/FLYSHARK.ST

`build.sh` calls this last, when the staged drive is already complete.

WHAT IS THIS FILE'S AND WHAT IS NOT. `tools/st_build.py` is the workspace's FAT12 writer and knows
everything that is about the FILESYSTEM: the geometry, the two FATs, a deterministic image, a
sha256, and the one thing that matters on a real machine and that `mformat` cannot promise — a boot
sector TOS will MOUNT AND NOT EXECUTE (TOS runs sector 0 when its 256 big-endian words sum to
$1234; `st_build` picks a serial that makes the sum come out wrong on purpose and then asserts it).
Every primitive below is IMPORTED from it: the geometry constants, `_fat12_set`, `_dir_entry`,
`_entry_bytes`, `_volume_label`, `_mountable_boot_sector`, `refuse_an_executable_boot_sector` and
`Layout`.

WHAT IS COPIED, AND IT IS SAID PLAINLY BECAUSE A READER WILL SEE IT: `place_directories` below has
the SHAPE of `st_build.build()` — the same allocate-and-chain loop, the same root assembly, the same
write-back — because it is that function generalised from one hard-coded `AUTO\\` to a mapping of
directory to file list. This volume needs TWO subdirectories, `AUTO\\` for the program and `A\\` for
the game's twenty-one data files, and `build()` writes one. The generalisation belongs in
`st_build.build()` itself, where its own tests reach it, and ../STATUS.md's "Follow-ups the kit
should absorb" carries that row; until it lands, a fix to `build()`'s layout logic has to be applied
here too, and this paragraph is the only thing that says so.

WHY TWO DIRECTORIES, AND NEITHER NAME IS OURS. The loader is the DESKTOP's `\\AUTO\\` scan, which is
the only way this game gets a low enough load address on the machine it was written for
(README.md, "The load-address budget"); and the data files are opened as `A\\NAME` — a relative path
the game's own file records spell — so they have to sit in a subdirectory called `A` off the root of
whatever drive it booted from.

WHAT IS ON IT THAT THE ORIGINAL DISK HAS NOT: `FLYSHARK.IMG`, the relocated program image the shim
stages into its own array. The original needs no such file because it IS the game.

NOT EVERY LEVEL'S ASSETS FIT, and the volume says which do. The twenty files in `A\\` are 600,440
bytes and a 720 KB volume holds 728,064 — so with our .PRG and the image beside them the later
levels' tile banks are what has to give. The choice is made by LEVEL and reported: level 0's eight
files are required (the boot loads them and the title screen needs them), and each later level's own
five are added while they fit. Which files a level asks for is not typed here — it is read out of
the staged image, by the game's own rule (`load_level_assets` @ 0x10332 patches one digit of each of
five names), so a disc built from a different release still names the right files.

VERIFIED BY A DIFFERENT READER FROM THE ONE THAT WROTE IT: `st_build` writes the volume and
`st_extract.py`'s parser reads it back, comparing every file against the source it came from. A
writer verified by its own library agrees with itself.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]                      # projects/flyingshark
REPO = PROJECT.parents[1]
sys.path.insert(0, str(REPO / "tools"))

import st_build                                                        # noqa: E402
import st_extract                                                      # noqa: E402

# The desktop runs every `\AUTO\*.PRG`, and this is the name the release ships. Keeping it is what
# makes the disk boot into our build with nothing else changed.
AUTO_DIR = "AUTO"
AUTO_PRG = "FLYSHARK.PRG"
# The game's own data subdirectory, named by the `A\...` paths inside its file records.
DATA_DIR = "A"
# The one file on the volume that the original disc has not; `flyshark_main.c`'s FILE_PROGRAM_IMAGE.
STAGED_IMAGE = "FLYSHARK.IMG"
# What a smoke run writes back into the root — one file. It is not put on the volume, because a
# floppy run has to have room to CREATE it, and it costs a cluster and a root slot whatever its
# length. (A play build writes nothing at all; `flyshark_main.c` says how a driver finds it anyway.)
RUN_OUTPUT_FILES = ("STARTED.BIN", "STATE.BIN")

# The five file records `load_level_assets` patches, and the byte of each name it patches. Both are
# ../include/globals.h's and ../src/frontend.c's, read out of the staged image below rather than
# retyped: A_file_rec_hsc_0 .. A_file_rec_hsc_3 are 20 bytes apart, the map's record is its own
# address, and the digit table is five bytes per level.
LOAD_BASE = 0x10000
A_FILE_REC_HSC_0 = 0x16346
A_FILE_REC_LEVEL_MAP = 0x16330
A_LEVEL_BANK_DIGITS = 0x162d4
FILE_REC_NAME = 8            # a record is [dest.l][len.l] then the ASCIZ DOS path
FILE_REC_STRIDE = 20         # HSC_0 .. HSC_3 are consecutive records of this length
TILE_BANKS = 4
LEVEL_BANK_DIGITS = 5        # four tile-bank digits and then the map's, per level
LEVELS = 5
HSC_NAME_DIGIT = 6           # `move.b (a0)+,6(a2)` — the digit inside "A\HSC_0.DAT"
MAP_NAME_DIGIT = 7           # `move.b (a0),7(a2)`  — ...and inside "A\LEVEL1.MAP"
# The two files every level needs and that are not in the table: the title picture and the driver.
BOOT_FILES = ("FLY_SHK.NEO", "MODULE.BAK", "SPRITES.CRU")

# What `st_build` puts in the root besides the files: a volume label, and one entry per
# subdirectory. Each costs a root slot, as does each file a run writes back.
VOLUME_LABEL_SLOTS = 1


def asciz(blob, at):
    """The NUL-terminated DOS path at `at` in the staged image."""
    end = blob.index(b"\0", at)
    return blob[at:end].decode("ascii")


def level_file_names(image_blob):
    """For each level, the five names its `load_level_assets` call opens — by the game's own rule.

    The digit table is the image's (`level_bank_digits` @ 0x162d4, the string
    "012314567289AB3013B48C375"); the five names are the file records'. Patching one byte of each is
    exactly what ../src/frontend.c's `load_level_assets_patch_filenames` does, so a release whose
    table or names differ still produces the right list.
    """
    def at(address):
        return address - LOAD_BASE

    names = []
    for level in range(LEVELS):
        digits = image_blob[at(A_LEVEL_BANK_DIGITS) + level * LEVEL_BANK_DIGITS:][:LEVEL_BANK_DIGITS]
        wanted = []
        for bank in range(TILE_BANKS):
            name = asciz(image_blob, at(A_FILE_REC_HSC_0 + bank * FILE_REC_STRIDE) + FILE_REC_NAME)
            wanted.append(name[:HSC_NAME_DIGIT] + chr(digits[bank]) + name[HSC_NAME_DIGIT + 1:])
        name = asciz(image_blob, at(A_FILE_REC_LEVEL_MAP) + FILE_REC_NAME)
        wanted.append(name[:MAP_NAME_DIGIT] + chr(digits[TILE_BANKS]) + name[MAP_NAME_DIGIT + 1:])
        names.append([entry.split("\\")[-1] for entry in wanted])
    return names


def clusters_for(sizes):
    return sum(max(1, -(-size // st_build.CLUSTER_BYTES)) for size in sizes)


def choose_data_files(data_dir, image_blob, already_used_bytes):
    """The `A\\` files that fit, level by level, and the levels that did not.

    Level 0's assets are REQUIRED: the boot loads them before the title picture is drawn, and a
    volume without them boots to a black screen. Each later level's five are added only if the whole
    set fits, because half a level's tile banks is worse than none — the missing bank would draw as
    whatever the previous level left in memory.
    """
    per_level = level_file_names(image_blob)
    chosen, dropped = [], []
    budget = st_build.CLUSTER_COUNT - clusters_for([already_used_bytes])

    def add(names):
        nonlocal budget
        fresh = [name for name in names if name not in chosen]
        paths = [data_dir / name for name in fresh]
        missing = [path for path in paths if not path.is_file()]
        if missing:
            raise SystemExit(f"ERROR: {missing[0]} is not in {data_dir} — run tools/unpack_dist.py")
        cost = clusters_for([path.stat().st_size for path in paths])
        if cost > budget:
            return False
        budget -= cost
        chosen.extend(fresh)
        return True

    if not add(list(BOOT_FILES) + per_level[0]):
        raise SystemExit("ERROR: level 0's own assets do not fit on the volume — the .PRG is too big")
    for level in range(1, LEVELS):
        if not add(per_level[level]):
            dropped.append(level)
    return chosen, dropped


def place_directories(image_path, root_files, directories, label=st_build.DEFAULT_LABEL,
                      oem=st_build.DEFAULT_OEM_NAME):
    """`st_build.build()` with a MAPPING of subdirectory name to file list instead of one `AUTO\\`.

    Every primitive is st_build's; what is here is the loop over directories and the root entry each
    one costs. Each file entry is `(dos_name, host_path)`, as st_build spells them.
    """
    if len(oem) != st_build.OEM_BYTES:
        raise ValueError(f"the OEM name is {st_build.OEM_BYTES} bytes; {oem!r} is {len(oem)}")
    contents = [(name, Path(host).read_bytes()) for name, host in root_files]
    subdirs = {name: [(entry, Path(host).read_bytes()) for entry, host in files]
               for name, files in directories.items()}

    image = bytearray(st_build.TOTAL_SECTORS * st_build.SECTOR_BYTES)
    fat = bytearray(st_build.SECTORS_PER_FAT * st_build.SECTOR_BYTES)
    st_build._fat12_set(fat, 0, st_build.FAT_ID_HIGH_NIBBLES | st_build.MEDIA_BYTE)
    st_build._fat12_set(fat, 1, st_build.FAT_END_OF_CHAIN)

    state = {"next": st_build.FIRST_CLUSTER}
    placed = []

    def cluster_offset(cluster):
        return (st_build.FIRST_DATA_SECTOR
                + (cluster - st_build.FIRST_CLUSTER) * st_build.SECTORS_PER_CLUSTER) \
               * st_build.SECTOR_BYTES

    def allocate(what, data):
        """Lay `data` out in consecutive clusters and chain them — st_build's own `allocate`."""
        count = max(1, -(-len(data) // st_build.CLUSTER_BYTES))
        first = state["next"]
        if first + count - 1 > st_build.LAST_CLUSTER:
            raise SystemExit(f"FAIL: {what} does not fit — {len(data)} bytes needs {count} clusters "
                             f"and only {st_build.LAST_CLUSTER - first + 1} are left")
        for step in range(count):
            cluster = first + step
            st_build._fat12_set(fat, cluster,
                                st_build.FAT_END_OF_CHAIN if step == count - 1 else cluster + 1)
            at = cluster_offset(cluster)
            image[at:at + st_build.CLUSTER_BYTES] = \
                data[step * st_build.CLUSTER_BYTES:(step + 1) * st_build.CLUSTER_BYTES] \
                .ljust(st_build.CLUSTER_BYTES, b"\0")
        state["next"] = first + count
        placed.append((what, len(data), first, count))
        return first

    root = bytearray()
    if label:
        root += st_build._volume_label(label)
    for directory, files in subdirs.items():
        # THE SUBDIRECTORY IS ALLOCATED BEFORE ITS CONTENTS so that its own `.` entry can name the
        # cluster it is itself stored in.
        entry_bytes = st_build.DIR_ENTRY_BYTES * (2 + len(files))
        span = bytes(max(st_build.CLUSTER_BYTES, -(-entry_bytes // st_build.CLUSTER_BYTES)
                         * st_build.CLUSTER_BYTES))
        cluster = allocate(directory + "\\", span)
        # `.` and `..` are not 8.3 names — the dot IS the name — so their eleven bytes are spelled
        # here rather than through `dos_name`. `..` names cluster 0, which is FAT12's "the root".
        entries = st_build._entry_bytes(b".".ljust(st_build.DIR_NAME_BYTES),
                                        st_build.ATTR_DIRECTORY, cluster, 0)
        entries += st_build._entry_bytes(b"..".ljust(st_build.DIR_NAME_BYTES),
                                         st_build.ATTR_DIRECTORY, 0, 0)
        for name, data in files:
            entries += st_build._dir_entry(name, st_build.ATTR_NONE,
                                           allocate(f"{directory}\\{name}", data), len(data))
        at = cluster_offset(cluster)
        image[at:at + len(entries)] = entries
        root += st_build._dir_entry(directory, st_build.ATTR_DIRECTORY, cluster, 0)

    for name, data in contents:
        root += st_build._dir_entry(name, st_build.ATTR_NONE, allocate(name, data), len(data))
    if len(root) > st_build.ROOT_ENTRIES * st_build.DIR_ENTRY_BYTES:
        raise SystemExit(f"FAIL: the root holds {len(root) // st_build.DIR_ENTRY_BYTES} entries and "
                         f"a {st_build.ROOT_ENTRIES}-entry FAT12 root has room for "
                         f"{st_build.ROOT_ENTRIES}")

    every_file = contents + [entry for files in subdirs.values() for entry in files]
    boot = st_build._mountable_boot_sector(every_file, oem)
    st_build.refuse_an_executable_boot_sector(boot)
    image[0:st_build.SECTOR_BYTES] = boot
    for copy in range(st_build.FAT_COPIES):
        at = (st_build.RESERVED_SECTORS + copy * st_build.SECTORS_PER_FAT) * st_build.SECTOR_BYTES
        image[at:at + len(fat)] = fat
    at = (st_build.RESERVED_SECTORS + st_build.FAT_COPIES * st_build.SECTORS_PER_FAT) \
        * st_build.SECTOR_BYTES
    image[at:at + len(root)] = root

    Path(image_path).parent.mkdir(parents=True, exist_ok=True)
    Path(image_path).write_bytes(bytes(image))
    return st_build.Layout(Path(image_path), bytes(image), placed,
                           state["next"] - st_build.FIRST_CLUSTER)


def verify(image_path, expected):
    """Read the finished image back with st_extract's parser and compare it to what went in.

    `expected` maps the path ON THE VOLUME to the host file it was written from. Both halves are
    checked: no file on the volume that was not asked for, and every one byte-for-byte. The parser's
    `warnings` are inspected LAST, because st_extract fills most of them from inside `walk` and
    `read_file`; checked before the read they would always be empty.
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
    parser.add_argument("--root", type=Path, required=True, help="the staged drive to build from")
    parser.add_argument("--out", type=Path, required=True, help="the .ST image to write")
    args = parser.parse_args()

    staged_image = args.root / STAGED_IMAGE
    if not staged_image.is_file():
        raise SystemExit(f"ERROR: {staged_image} is missing — run build.sh, which stages it first")
    image_blob = staged_image.read_bytes()
    data_dir = args.root / DATA_DIR
    used = args.prg.stat().st_size + staged_image.stat().st_size
    data_files, dropped = choose_data_files(data_dir, image_blob, used)

    layout = place_directories(
        args.out,
        root_files=[(STAGED_IMAGE, staged_image)],
        directories={AUTO_DIR: [(AUTO_PRG, args.prg)],
                     DATA_DIR: [(name, data_dir / name) for name in data_files]})

    expected = {f"{AUTO_DIR}/{AUTO_PRG}": args.prg, STAGED_IMAGE: staged_image}
    expected.update({f"{DATA_DIR}/{name}": data_dir / name for name in data_files})
    on_volume = verify(args.out, expected)

    print(f">> {args.out}: {len(on_volume)} files verified against {args.root} byte for byte")
    print(f"   {AUTO_DIR}\\{AUTO_PRG} = {args.prg.name} ({args.prg.stat().st_size} B), "
          f"{STAGED_IMAGE} in the root, {len(data_files)} files in {DATA_DIR}\\")
    print(f"   {layout.used_bytes} B used, {layout.free_bytes} B free; sha256 {layout.digest}")
    if dropped:
        print(f"   LEVELS {dropped} HAVE NO ASSETS ON THIS VOLUME — 720 KB does not hold all "
              f"{len(list(data_dir.iterdir()))} of them beside the program. README.md says what a "
              f"level whose banks are missing draws.")

    # A run writes its record back, and it needs a cluster AND a root slot. A FAT12
    # root is a FIXED number of entries, so a volume with room and no slot left fails a `Fcreate`
    # exactly as a full one does, and a free-space check alone would not see it.
    needed = clusters_for([1] * len(RUN_OUTPUT_FILES))
    if layout.free_bytes < needed * st_build.CLUSTER_BYTES:
        raise SystemExit(f"ERROR: a smoke run writes {len(RUN_OUTPUT_FILES)} files and the volume "
                         f"has {layout.free_bytes // st_build.CLUSTER_BYTES} clusters free")
    used_slots = 1 + len(directories_in(on_volume)) + VOLUME_LABEL_SLOTS
    free_slots = st_build.ROOT_ENTRIES - used_slots
    if free_slots < len(RUN_OUTPUT_FILES):
        raise SystemExit(f"ERROR: a smoke run creates {len(RUN_OUTPUT_FILES)} files and the root "
                         f"has {free_slots} of its {st_build.ROOT_ENTRIES} entries left")


def directories_in(on_volume):
    """The subdirectory names the volume's file paths name — one root slot each."""
    return {path.split("/")[0] for path in on_volume if "/" in path}


if __name__ == "__main__":
    main()
