#!/usr/bin/env python3
"""st_build.py — write a 720 KB double-sided FAT12 Atari `.ST` image, the WRITE half of st_extract.py.

    python3 tools/st_build.py OUT.ST [--label NAME] [--oem SIXCHR] \\
            [--auto path/to/PROG.PRG:PROG.PRG] path/to/file.dat[:NAME.EXT] ...

`st_extract.py` reads an Atari floppy image; this writes one, for the case a project needs a volume a
REAL Atari can boot rather than a host directory an emulator pretends is a disk. Stdlib only, and
game-agnostic: what goes on the disk is the caller's, the filesystem is this file's.

WHY A BUILDER HERE AND NOT `mformat`. Three reasons, and only the first is about dependencies:

  1. `mtools` is not part of this workspace's toolchain (`m68k-elf-gcc`, `hatari`, python), and a
     runbook step a person has to `brew install` before they can write their disk is a step that
     will be skipped.
  2. The Atari boot sector is not the DOS one. TOS EXECUTES sector 0 when its 256 big-endian words
     sum to $1234 and mounts the volume without executing it otherwise; `mformat` knows nothing
     about that sum, so it can only ever produce a mountable disk by accident — 65,535 times in
     65,536, which is exactly the kind of rare failure this workspace refuses. `build` below picks a
     serial that makes the sum come out wrong ON PURPOSE, and then asserts it.
  3. A DETERMINISTIC image. Building the same file list twice produces the same bytes, so the sha256
     `build` returns can be compared against the one a person writes to a physical floppy. That diff
     is the only host-side check there is that the write took.

GEOMETRY: 720 KB double-sided — `gw`'s `atarist.720`, and the format `gw/README.md` prescribes for an
unprotected disk (its "Unprotected disk? Write the `.st`, not the `.scp`" section). Nothing here
writes the 10- or 11-sector extended formats: they hold more, and they are the formats a drive that
is not the one they were written on can fail to read.

WHERE THE BPB FIELDS COME FROM, honestly split between measurement and standard:

  * MEASURED off real Atari volumes — `projects/wonderboy/bin/wb_disk2.st` (the game's own data
    disk) and `gw/dumps/robocop/disk1/robocop_disk1.st` both carry `spc=2 res=1 nfats=2 ndirs=112
    spf=5`, and those are the numbers below.
  * STANDARD for 720 KB double-sided, and NOT evidenced by either of those volumes, because both of
    them are SINGLE-SIDED: `media=0xF9`, 9 sectors a track, 2 heads. (Measured, so the distinction is
    not a guess: wb_disk2.st is `media=0x00 spt=10 heads=1`, robocop_disk1.st is `media=0xF8 spt=9
    heads=1`.) 0xF9 is the DOS/TOS media descriptor for 720K DS and 0xF8 the one for the 360K SS
    disk RoboCop was pressed on.
  * OVER-PROVISIONED BUT LEGAL: `spf=5`. This layout has 711 clusters, and FAT12's byte-and-a-half
    per entry needs only 1,070 bytes — three sectors. Five is what the measured volumes carry and
    what TOS's own formatter writes; the two spare sectors per copy cost 2 KB and buy compatibility
    with anything that assumes the familiar number.
"""
import hashlib
import struct
import sys
from pathlib import Path

# ---- the 720 KB double-sided geometry, and the BPB that describes it ---------------------------
SECTOR_BYTES = 512
SECTORS_PER_TRACK = 9
HEADS = 2
TRACKS = 80
TOTAL_SECTORS = SECTORS_PER_TRACK * HEADS * TRACKS          # 1440
SECTORS_PER_CLUSTER = 2
CLUSTER_BYTES = SECTORS_PER_CLUSTER * SECTOR_BYTES
RESERVED_SECTORS = 1                                        # the boot sector
FAT_COPIES = 2
SECTORS_PER_FAT = 5
ROOT_ENTRIES = 112
DIR_ENTRY_BYTES = 32
DIR_NAME_BYTES = 11                                         # eight of stem and three of extension
DIR_STEM_BYTES, DIR_EXTENSION_BYTES = 8, 3
# Bytes 12..21 of a directory entry: DOS later spent them on creation time and the high half of the
# cluster number, and TOS leaves every one of them zero. `bin/wb_disk2.st`'s own entries read zero.
DIR_RESERVED_SPAN = 10
ROOT_SECTORS = ROOT_ENTRIES * DIR_ENTRY_BYTES // SECTOR_BYTES
MEDIA_BYTE = 0xF9                                           # double-sided, 9 sectors a track
# The BPB's last field. It counts sectors before the volume on a PARTITIONED device; a floppy has
# none, and TOS writes zero.
HIDDEN_SECTORS = 0

FIRST_DATA_SECTOR = RESERVED_SECTORS + FAT_COPIES * SECTORS_PER_FAT + ROOT_SECTORS
DATA_SECTORS = TOTAL_SECTORS - FIRST_DATA_SECTOR
# FAT12 numbers clusters from 2, so cluster N lives at data sector (N - 2) * SECTORS_PER_CLUSTER.
FIRST_CLUSTER = 2
CLUSTER_COUNT = DATA_SECTORS // SECTORS_PER_CLUSTER
LAST_CLUSTER = FIRST_CLUSTER + CLUSTER_COUNT - 1
# THE VOLUME'S CAPACITY, which is not the image's size: the boot sector, the two FATs and the root
# directory are the difference (728,064 of the file's 737,280 bytes).
DATA_BYTES = CLUSTER_COUNT * CLUSTER_BYTES

FAT_END_OF_CHAIN = 0xFFF
# FAT12 reserves $ff0..$fff for end-of-chain and bad-cluster marks, so a chain walk stops at the
# first entry that is not a cluster number.
FAT_FIRST_RESERVED = 0xFF0
FAT_ENTRY_BITS = 12
# The FAT's own entry 0 is the media descriptor with every nibble above it set — the identifier a
# reader can cross-check the BPB against.
FAT_ID_HIGH_NIBBLES = 0xF00

# Directory-entry field values. `ATTR_NONE` and not DOS's archive bit because that is what a pressed
# Atari disk carries — every root entry of `projects/wonderboy/bin/wb_disk2.st` reads `attr=0`.
ATTR_NONE = 0x00
ATTR_VOLUME_LABEL = 0x08
ATTR_DIRECTORY = 0x10
DELETED_ENTRY = 0xE5                                        # what a name may not begin with

# ONE FIXED STAMP, so that building the same file list twice produces the same bytes — see the
# determinism argument in the banner. The day is arbitrary and says so by being the first of a year.
STAMP_YEAR, STAMP_MONTH, STAMP_DAY = 1989, 1, 1
FAT_EPOCH_YEAR = 1980
# A FAT date is one little-endian word: year-since-1980 in bits 15..9, month in 8..5, day in 4..0.
FAT_DATE_YEAR_SHIFT, FAT_DATE_MONTH_SHIFT = 9, 5
FAT_TIME_MIDNIGHT = 0                                       # the time is not information here

# ---- the Atari boot sector ---------------------------------------------------------------------
#
# TOS reads sector 0 of the boot drive, sums its 256 words as BIG-ENDIAN unsigned, and EXECUTES it
# from offset 0 when the sum is $1234. Anything else and the volume is simply mounted — which is
# what an AUTO-folder disk wants: TOS's own loader runs the program, and the boot sector has no job
# beyond carrying the BPB.
ATARI_BOOT_EXECUTABLE_SUM = 0x1234
BOOT_SERIAL_AT = 8
BOOT_SERIAL_BYTES = 3
BPB_AT = 11
OEM_AT = 2
OEM_BYTES = 6
DEFAULT_OEM_NAME = b"STBULD"                                # 6 bytes; overridable per volume
DEFAULT_LABEL = "ATARI"
# How many times a serial may be re-derived before the boot sector is not the magic sum. Each rehash
# is an independent draw with a 1-in-65,536 chance of colliding again, so this bound is never
# approached; it exists so a broken derivation cannot spin.
SERIAL_ATTEMPT_LIMIT = 16


def _fat12_set(fat, index, value):
    """One FAT12 entry, which is a byte and a half and therefore shares a byte with a neighbour."""
    at = index * FAT_ENTRY_BITS // 8
    pair = fat[at] | (fat[at + 1] << 8)
    pair = ((pair & 0x000F) | (value << 4)) if (index & 1) else ((pair & 0xF000) | value)
    fat[at] = pair & 0xFF
    fat[at + 1] = pair >> 8


def dos_name(name):
    """`name` as a directory entry's eleven bytes: eight of stem, three of extension, space-padded.

    THE SPACE PADDING IS THE FILESYSTEM'S AND NOT THE PROGRAM'S. A game that stores the FAT form in
    its own resource table ("CREDITS .RAD") strips it before `Fopen` sees it; this is the inverse, so
    a name the program asks for by its table row lands on the volume as the bytes TOS compares."""
    stem, _, extension = name.upper().partition(".")
    if not stem or len(stem) > DIR_STEM_BYTES or len(extension) > DIR_EXTENSION_BYTES:
        raise ValueError(f"{name!r} is not an 8.3 name")
    if stem[0] == chr(DELETED_ENTRY):
        raise ValueError(f"{name!r} begins with the byte that marks a deleted entry")
    return (stem.ljust(DIR_STEM_BYTES).encode("ascii")
            + extension.ljust(DIR_EXTENSION_BYTES).encode("ascii"))


def _fat_stamp():
    date = (((STAMP_YEAR - FAT_EPOCH_YEAR) << FAT_DATE_YEAR_SHIFT)
            | (STAMP_MONTH << FAT_DATE_MONTH_SHIFT) | STAMP_DAY)
    return FAT_TIME_MIDNIGHT, date


def _entry_bytes(eleven, attr, cluster, size):
    time, date = _fat_stamp()
    return (eleven + bytes([attr]) + bytes(DIR_RESERVED_SPAN)
            + struct.pack("<HHHI", time, date, cluster, size))


def _dir_entry(name, attr, cluster, size):
    return _entry_bytes(dos_name(name), attr, cluster, size)


def _volume_label(label):
    """The eleven bytes are ONE field for a label, not a stem and an extension — so it is built here
    rather than through `dos_name`, which would refuse a name with no dot and truncate one with."""
    if len(label) > DIR_NAME_BYTES:
        raise ValueError(f"volume label {label!r} is longer than {DIR_NAME_BYTES} characters")
    return _entry_bytes(label.upper().ljust(DIR_NAME_BYTES).encode("ascii"), ATTR_VOLUME_LABEL, 0, 0)


def _boot_sector(serial, oem):
    boot = bytearray(SECTOR_BYTES)
    # Bytes 0-1 are the branch a BOOTABLE sector puts its entry in. Left at zero, which is what a
    # pressed non-executable Atari data disk carries.
    boot[OEM_AT:OEM_AT + OEM_BYTES] = oem
    boot[BOOT_SERIAL_AT:BOOT_SERIAL_AT + BOOT_SERIAL_BYTES] = serial
    struct.pack_into("<HBHBHHBHHHH", boot, BPB_AT,
                     SECTOR_BYTES, SECTORS_PER_CLUSTER, RESERVED_SECTORS, FAT_COPIES, ROOT_ENTRIES,
                     TOTAL_SECTORS, MEDIA_BYTE, SECTORS_PER_FAT, SECTORS_PER_TRACK, HEADS,
                     HIDDEN_SECTORS)
    return boot


def boot_checksum(boot):
    """TOS's own sum: 256 BIG-endian words, truncated to sixteen bits."""
    return sum(struct.unpack(">%dH" % (SECTOR_BYTES // 2), bytes(boot))) & 0xFFFF


def refuse_an_executable_boot_sector(boot):
    """TOS executes sector 0 when its words sum to $1234. These volumes must be MOUNTED, not booted.

    `_mountable_boot_sector` chooses a serial that avoids the sum, so this can only fire if that
    search is broken. It stays because the failure it guards is the kind that would be found on a
    person's hardware rather than here: the machine would jump into a BPB and bomb, and every
    emulated check behind it would still be green."""
    total = boot_checksum(boot)
    if total == ATARI_BOOT_EXECUTABLE_SUM:
        raise SystemExit(f"FAIL: the boot sector's checksum is {total:#06x} — TOS would EXECUTE it, "
                         f"and the serial search was supposed to have made that impossible.")


def _mountable_boot_sector(entries, oem):
    """A boot sector whose serial DIFFERS PER FILE LIST and whose checksum is not TOS's magic.

    Two requirements in one search, because the serial serves both. TOS detects a disk change partly
    from the boot sector's serial, so two disks a person swaps in and out of one drive must not carry
    the same three bytes or the second may be read through the first's cached directory — hence a
    digest of the contents. And roughly one file list in 65,536 would land on the executable sum, so
    when that happens the digest is simply rehashed: still deterministic, still content-derived, and
    an accident that used to be an unactionable refusal becomes a second draw."""
    digest = hashlib.sha256(b"".join(name.encode() + data for name, data in entries)).digest()
    for _attempt in range(SERIAL_ATTEMPT_LIMIT):
        boot = _boot_sector(digest[:BOOT_SERIAL_BYTES], oem)
        if boot_checksum(boot) != ATARI_BOOT_EXECUTABLE_SUM:
            return boot
        digest = hashlib.sha256(digest).digest()
    raise SystemExit(f"FAIL: {SERIAL_ATTEMPT_LIMIT} serials in a row summed to "
                     f"{ATARI_BOOT_EXECUTABLE_SUM:#06x}, which cannot happen by chance — the "
                     f"checksum or the serial derivation is broken.")


class Layout:
    """What the builder put where, and the digest of what it wrote."""

    def __init__(self, path, image, placed, used_clusters):
        self.path = path
        self.placed = placed                                # [(name, size, first_cluster, clusters)]
        self.used_clusters = used_clusters
        # THE BINDING BETWEEN A PROVED IMAGE AND A WRITTEN DISK. Nothing else connects the file a
        # check booted to the bytes a person puts on a floppy: printed at build, re-read before the
        # write, and compared after a boot that was supposed to leave the volume alone.
        self.digest = hashlib.sha256(image).hexdigest()

    @property
    def used_bytes(self):
        return self.used_clusters * CLUSTER_BYTES

    @property
    def free_bytes(self):
        return DATA_BYTES - self.used_bytes

    def __str__(self):
        rows = "\n".join(f"   {name:<20} {size:>7} B  clusters {first}..{first + count - 1}"
                         for name, size, first, count in self.placed)
        return (f"{rows}\n   {'TOTAL':<20} {self.used_bytes:>7} B in {self.used_clusters} clusters, "
                f"{self.free_bytes} B free of {DATA_BYTES}\n"
                f"   {'sha256':<20} {self.digest}")


def build(image_path, root_files, auto_files=(), label=DEFAULT_LABEL, oem=DEFAULT_OEM_NAME):
    """Write a 720 KB FAT12 image holding `root_files` in `\\` and `auto_files` in `\\AUTO\\`.

    Each entry is `(dos_name, host_path)`. TOS runs every `\\AUTO\\*.PRG` on the boot drive before it
    puts up the desktop, which is why a program that must start by itself goes there and not in the
    root: a disk that has to be double-clicked needs a desktop, a mouse and a person, and this one is
    meant to be inserted into a machine that is then switched on."""
    if len(oem) != OEM_BYTES:
        raise ValueError(f"the OEM name is {OEM_BYTES} bytes; {oem!r} is {len(oem)}")
    contents = [(name, Path(host).read_bytes()) for name, host in root_files]
    auto_contents = [(name, Path(host).read_bytes()) for name, host in auto_files]

    image = bytearray(TOTAL_SECTORS * SECTOR_BYTES)
    fat = bytearray(SECTORS_PER_FAT * SECTOR_BYTES)
    _fat12_set(fat, 0, FAT_ID_HIGH_NIBBLES | MEDIA_BYTE)
    _fat12_set(fat, 1, FAT_END_OF_CHAIN)

    next_cluster = FIRST_CLUSTER
    placed = []

    def allocate(what, data):
        """Lay `data` out in consecutive clusters and chain them. Consecutive because nothing here
        ever deletes a file, so there is no free-list to reuse and no reason to fragment a load."""
        nonlocal next_cluster
        count = max(1, -(-len(data) // CLUSTER_BYTES))
        first = next_cluster
        if first + count - 1 > LAST_CLUSTER:
            raise SystemExit(f"FAIL: {what} does not fit — {len(data)} bytes needs {count} clusters "
                             f"and only {LAST_CLUSTER - first + 1} are left of the {DATA_BYTES} "
                             f"bytes this volume holds. Take a file off this image, or split it "
                             f"across two.")
        for step in range(count):
            cluster = first + step
            _fat12_set(fat, cluster, FAT_END_OF_CHAIN if step == count - 1 else cluster + 1)
            at = (FIRST_DATA_SECTOR + (cluster - FIRST_CLUSTER) * SECTORS_PER_CLUSTER) * SECTOR_BYTES
            image[at:at + CLUSTER_BYTES] = data[step * CLUSTER_BYTES:(step + 1) * CLUSTER_BYTES] \
                .ljust(CLUSTER_BYTES, b"\0")
        next_cluster = first + count
        placed.append((what, len(data), first, count))
        return first

    root = bytearray()
    if label:
        root += _volume_label(label)
    if auto_contents:
        # THE SUBDIRECTORY IS ALLOCATED BEFORE ITS CONTENTS so that its own entries can name their
        # clusters; its `.` entry has to name the cluster it is itself stored in.
        auto_cluster = allocate("AUTO\\", bytes(CLUSTER_BYTES))
        # `.` and `..` are not 8.3 names — the dot IS the name — so their eleven bytes are spelled
        # here rather than through `dos_name`, which would read the dot as a separator. `..` names
        # cluster 0, which is how FAT12 spells "the root".
        entries = _entry_bytes(b".".ljust(DIR_NAME_BYTES), ATTR_DIRECTORY, auto_cluster, 0)
        entries += _entry_bytes(b"..".ljust(DIR_NAME_BYTES), ATTR_DIRECTORY, 0, 0)
        for name, data in auto_contents:
            entries += _dir_entry(name, ATTR_NONE, allocate("AUTO\\" + name, data), len(data))
        if len(entries) > CLUSTER_BYTES:
            raise SystemExit("FAIL: \\AUTO\\ holds more entries than one cluster")
        at = (FIRST_DATA_SECTOR + (auto_cluster - FIRST_CLUSTER) * SECTORS_PER_CLUSTER) * SECTOR_BYTES
        image[at:at + len(entries)] = entries
        root += _dir_entry("AUTO", ATTR_DIRECTORY, auto_cluster, 0)

    for name, data in contents:
        root += _dir_entry(name, ATTR_NONE, allocate(name, data), len(data))
    if len(root) > ROOT_ENTRIES * DIR_ENTRY_BYTES:
        raise SystemExit(f"FAIL: the root directory holds {len(root) // DIR_ENTRY_BYTES} entries "
                         f"and a {ROOT_ENTRIES}-entry FAT12 root has room for {ROOT_ENTRIES}")

    boot = _mountable_boot_sector(contents + auto_contents, oem)
    refuse_an_executable_boot_sector(boot)
    image[0:SECTOR_BYTES] = boot
    for copy in range(FAT_COPIES):
        at = (RESERVED_SECTORS + copy * SECTORS_PER_FAT) * SECTOR_BYTES
        image[at:at + len(fat)] = fat
    at = (RESERVED_SECTORS + FAT_COPIES * SECTORS_PER_FAT) * SECTOR_BYTES
    image[at:at + len(root)] = root

    Path(image_path).parent.mkdir(parents=True, exist_ok=True)
    Path(image_path).write_bytes(bytes(image))
    return Layout(Path(image_path), bytes(image), placed, next_cluster - FIRST_CLUSTER)


def _split(argument):
    """`host/path.EXT` or `host/path:NAME.EXT` — the second form is how a build product gets its
    volume name, since a file called `WB-ownrun.PRG` is not what a program's `Fopen` asks for."""
    host, _, name = argument.partition(":")
    return (name or Path(host).name, host)


def main():
    arguments = iter(sys.argv[2:] if len(sys.argv) > 2 else [])
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    image, auto, root = sys.argv[1], [], []
    label, oem = DEFAULT_LABEL, DEFAULT_OEM_NAME
    for argument in arguments:
        if argument == "--auto":
            auto.append(_split(next(arguments)))
        elif argument == "--label":
            label = next(arguments)
        elif argument == "--oem":
            oem = next(arguments).encode("ascii")
        else:
            root.append(_split(argument))
    print(build(image, root, auto, label, oem))


if __name__ == "__main__":
    main()
