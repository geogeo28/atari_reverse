#!/usr/bin/env python3
"""FAT12 Atari ST floppy-image (.ST / .MSA-decoded raw) lister and extractor.

Stdlib only, game-agnostic: the geometry comes from the boot sector's BPB, so any
FAT12 image works (360K/720K/800K/820K/... single- or double-sided). Atari TOS
writes the standard DOS BPB fields, little-endian, even though the CPU is big-endian.

Priority is *not producing garbage*: an image whose BPB is missing/inconsistent is
rejected with a reason rather than decoded into plausible-looking rubbish, and every
suspicious cluster chain or directory entry is reported instead of being silently
truncated or skipped. A suspicious entry never aborts the run — the rest of the tree
is still listed/extracted, and the exit status reports that the result is not clean.

Usage:
  python3 st_extract.py IMAGE.ST            # list the whole tree
  python3 st_extract.py IMAGE.ST -o OUTDIR  # extract the tree into OUTDIR

Exit status:
  0  clean run
  1  unusable image, or the run completed but emitted warnings (dirty extraction)
  2  bad command line
"""
import os
import struct
import sys

USAGE = "usage: st_extract.py IMAGE.ST [-o OUTDIR]"

# --- boot-sector BPB field offsets (DOS layout; TOS uses the same ones) ---------
BPB_BYTES_PER_SECTOR = 11
BPB_SECTORS_PER_CLUSTER = 13
BPB_RESERVED_SECTORS = 14
BPB_FAT_COUNT = 16
BPB_ROOT_ENTRIES = 17
BPB_TOTAL_SECTORS = 19
BPB_MEDIA_BYTE = 21
BPB_SECTORS_PER_FAT = 22
BPB_SECTORS_PER_TRACK = 24
BPB_HEADS = 26
BOOT_SECTOR_SIZE = 512

# BPB fields that may never be zero, with the reason each one matters.
BPB_NONZERO_FIELDS = (
    ("reserved_sectors", "reserved sectors=0 (the boot sector itself is reserved)"),
    ("sectors_per_fat", "sectors/FAT=0"),
    ("root_entries", "root directory entries=0"),
    ("total_sectors", "total sectors=0"),
)

# --- directory entry layout (32 bytes) -----------------------------------------
DIR_ENTRY_SIZE = 32
DIR_NAME_OFF, DIR_NAME_LEN = 0, 8
DIR_EXT_OFF, DIR_EXT_LEN = 8, 3
DIR_ATTR_OFF = 11
DIR_START_CLUSTER_OFF = 26
DIR_SIZE_OFF = 28

DIR_ENTRY_FREE = 0x00        # this entry and every following one is unused
DIR_ENTRY_DELETED = 0xE5
ATTR_VOLUME_LABEL = 0x08
ATTR_DIRECTORY = 0x10
ATTR_LFN = 0x0F             # VFAT long-name fragment: attr bits 0..3 all set

DOT_ENTRIES = (".", "..")   # the self/parent links every subdirectory carries
# None of these may appear in an 8.3 name; a raw name holding one is corrupt, and
# letting it through would turn one entry into a path that escapes its directory.
NAME_SEPARATORS = ("/", "\\", "\x00")

# --- FAT12 cluster values -------------------------------------------------------
FIRST_DATA_CLUSTER = 2
FAT12_RESERVED_MIN = 0xFF0   # 0xFF0..0xFF6 reserved, 0xFF7 bad, >=0xFF8 end-of-chain
FAT12_BAD_CLUSTER = 0xFF7
FAT12_END_OF_CHAIN = 0xFF8
FAT12_MAX_CLUSTERS = 4085    # a volume is FAT12 only if cluster_count < 4085
FREE_CLUSTER = 0             # also what an empty file stores as its start cluster

MAGIC_BYTES = 4              # bytes of each file shown as its "magic" in the listing
PATH_COLUMN = 28             # width of the path column in the listing/extract output


def le16(data, off):
    return struct.unpack_from("<H", data, off)[0]


def parse_bpb(boot, image_size):
    """Decode + sanity-check the BPB. Raises ValueError with a reason if implausible."""
    if len(boot) < BOOT_SECTOR_SIZE:
        raise ValueError("image is shorter than one boot sector (%d bytes)" % len(boot))
    bpb = dict(
        bytes_per_sector=le16(boot, BPB_BYTES_PER_SECTOR),
        sectors_per_cluster=boot[BPB_SECTORS_PER_CLUSTER],
        reserved_sectors=le16(boot, BPB_RESERVED_SECTORS),
        fat_count=boot[BPB_FAT_COUNT],
        root_entries=le16(boot, BPB_ROOT_ENTRIES),
        total_sectors=le16(boot, BPB_TOTAL_SECTORS),
        media_byte=boot[BPB_MEDIA_BYTE],
        sectors_per_fat=le16(boot, BPB_SECTORS_PER_FAT),
        sectors_per_track=le16(boot, BPB_SECTORS_PER_TRACK),
        heads=le16(boot, BPB_HEADS),
    )
    _check_bpb(bpb, image_size)
    _add_derived_layout(bpb)
    if bpb["cluster_count"] >= FAT12_MAX_CLUSTERS:
        raise ValueError("%d clusters — that is FAT16, not FAT12" % bpb["cluster_count"])
    _check_fat_fits(bpb)
    return bpb


def _check_bpb(bpb, image_size):
    sector = bpb["bytes_per_sector"]
    if sector < 128 or sector > 4096 or sector & (sector - 1):
        raise ValueError("bytes/sector=%d is not a power of two in 128..4096" % sector)
    spc = bpb["sectors_per_cluster"]
    if spc == 0 or spc > 64 or spc & (spc - 1):
        raise ValueError("sectors/cluster=%d is not a power of two in 1..64" % spc)
    if not 1 <= bpb["fat_count"] <= 4:
        raise ValueError("FAT count=%d is out of range" % bpb["fat_count"])
    for field, message in BPB_NONZERO_FIELDS:
        if bpb[field] == 0:
            raise ValueError(message)
    if (bpb["root_entries"] * DIR_ENTRY_SIZE) % sector:
        raise ValueError("root directory (%d entries) is not a whole number of sectors"
                         % bpb["root_entries"])
    if bpb["total_sectors"] * sector > image_size:
        raise ValueError("BPB claims %d sectors x %d bytes > image size %d"
                         % (bpb["total_sectors"], sector, image_size))


def _add_derived_layout(bpb):
    """Compute the four region start sectors, the cluster count and the cluster size."""
    root_bytes = bpb["root_entries"] * DIR_ENTRY_SIZE
    bpb["fat_start"] = bpb["reserved_sectors"]
    bpb["root_start"] = bpb["fat_start"] + bpb["fat_count"] * bpb["sectors_per_fat"]
    bpb["root_sectors"] = root_bytes // bpb["bytes_per_sector"]
    bpb["data_start"] = bpb["root_start"] + bpb["root_sectors"]
    bpb["cluster_size"] = bpb["sectors_per_cluster"] * bpb["bytes_per_sector"]
    data_sectors = bpb["total_sectors"] - bpb["data_start"]
    if data_sectors <= 0:
        raise ValueError("no data region: reserved+FATs+root (%d sectors) fills the volume"
                         % bpb["data_start"])
    bpb["cluster_count"] = data_sectors // bpb["sectors_per_cluster"]
    bpb["max_cluster"] = bpb["cluster_count"] + FIRST_DATA_CLUSTER - 1
    # A near-full FAT12 volume can address clusters whose numbers collide with the
    # reserved/bad/end-of-chain values; those numbers are terminators, never data.
    bpb["max_data_cluster"] = min(bpb["max_cluster"], FAT12_RESERVED_MIN - 1)


def _check_fat_fits(bpb):
    """A FAT12 table needs 1.5 bytes per cluster; refuse a FAT too small to address them."""
    fat_bytes = bpb["sectors_per_fat"] * bpb["bytes_per_sector"]
    needed = (bpb["max_cluster"] + 1) * 3 // 2 + 1
    if fat_bytes < needed:
        raise ValueError("FAT is %d bytes, too small for %d clusters (needs %d)"
                         % (fat_bytes, bpb["cluster_count"], needed))


class Fat12Image:
    """Read-only view of a FAT12 volume: sectors, cluster chains, directories."""

    def __init__(self, data):
        self.data = data
        self.bpb = parse_bpb(data[:BOOT_SECTOR_SIZE], len(data))
        self.warnings = []
        fat_off = self.bpb["fat_start"] * self.bpb["bytes_per_sector"]
        fat_len = self.bpb["sectors_per_fat"] * self.bpb["bytes_per_sector"]
        self.fat = data[fat_off:fat_off + fat_len]

    def sectors(self, start, count):
        sector = self.bpb["bytes_per_sector"]
        return self.data[start * sector:(start + count) * sector]

    def is_data_cluster(self, cluster):
        """True if this cluster number really addresses data (not a reserved value)."""
        return FIRST_DATA_CLUSTER <= cluster <= self.bpb["max_data_cluster"]

    def cluster_start_sector(self, cluster):
        """The volume sector a cluster begins at (data clusters are numbered from 2)."""
        return (self.bpb["data_start"]
                + (cluster - FIRST_DATA_CLUSTER) * self.bpb["sectors_per_cluster"])

    def cluster_bytes(self, cluster):
        return self.sectors(self.cluster_start_sector(cluster),
                            self.bpb["sectors_per_cluster"])

    def fat_entry(self, cluster):
        """FAT12 packs two entries into three bytes; odd clusters take the high nibbles."""
        off = cluster + cluster // 2
        pair = le16(self.fat, off)
        return pair >> 4 if cluster & 1 else pair & 0xFFF

    def chain(self, first_cluster, what, empty_ok=False):
        """Cluster numbers of a file/dir, stopping (with a warning) on anything odd.

        `empty_ok` marks the one legitimately empty case: a zero-length file, which
        stores no start cluster at all.
        """
        clusters = []
        seen = set()
        cluster = first_cluster
        while self.is_data_cluster(cluster):
            if cluster in seen:
                self.warnings.append("%s: cluster chain loops at %d" % (what, cluster))
                break
            seen.add(cluster)
            clusters.append(cluster)
            cluster = self.fat_entry(cluster)
        if not clusters:
            if first_cluster != FREE_CLUSTER or not empty_ok:
                self.warnings.append("%s: start cluster %d is not a valid data cluster"
                                     % (what, first_cluster))
            return clusters
        if cluster >= FAT12_END_OF_CHAIN:
            return clusters                         # the normal end-of-chain terminator
        if cluster == FAT12_BAD_CLUSTER:
            self.warnings.append("%s: chain runs into a bad cluster marker" % what)
        elif cluster >= FAT12_RESERVED_MIN:
            self.warnings.append("%s: chain ends on reserved value 0x%03x" % (what, cluster))
        elif cluster not in seen:
            self.warnings.append("%s: chain continues into free/out-of-range cluster %d"
                                 % (what, cluster))
        return clusters

    def _read_clusters(self, clusters):
        """Concatenate the contents of a cluster list, in order."""
        return b"".join(self.cluster_bytes(c) for c in clusters)

    def chain_bytes(self, first_cluster, what):
        """Every byte of a cluster chain, in order."""
        return self._read_clusters(self.chain(first_cluster, what))

    def file_clusters(self, entry):
        """A file's chain, checked against the length its directory entry claims."""
        clusters = self.chain(entry["cluster"], entry["path"], empty_ok=entry["size"] == 0)
        held = len(clusters) * self.bpb["cluster_size"]
        if held < entry["size"]:
            self.warnings.append("%s: chain holds %d bytes but the entry says %d"
                                 % (entry["path"], held, entry["size"]))
        elif held - entry["size"] >= self.bpb["cluster_size"]:
            # Slack inside the last cluster is normal; a whole spare cluster is not —
            # it is the signature of a cross-linked chain or a clobbered size field.
            self.warnings.append("%s: chain holds %d bytes, a whole cluster more than"
                                 " the entry's %d" % (entry["path"], held, entry["size"]))
        return clusters

    def file_bytes(self, entry):
        """Chain contents truncated to the directory-entry size."""
        return self._read_clusters(self.file_clusters(entry))[:entry["size"]]


def _entry_name(raw):
    stem = raw[DIR_NAME_OFF:DIR_NAME_OFF + DIR_NAME_LEN].decode("latin1").rstrip(" ")
    ext = raw[DIR_EXT_OFF:DIR_EXT_OFF + DIR_EXT_LEN].decode("latin1").rstrip(" ")
    return stem + "." + ext if ext else stem


def _unusable_name(name):
    """Why this 8.3 name cannot be used as a path component, or None if it is fine."""
    if not name:
        return "empty name"
    if name in DOT_ENTRIES:
        return "dot entry"
    for separator in NAME_SEPARATORS:
        if separator in name:
            return "path separator in the name"
    return None


def _parse_dir_entries(block, parent_path, warnings):
    """Live entries of one directory block, as dicts. Stops at the end-of-directory mark."""
    entries = []
    for off in range(0, len(block), DIR_ENTRY_SIZE):
        raw = block[off:off + DIR_ENTRY_SIZE]
        if raw[0] == DIR_ENTRY_FREE:
            break
        attr = raw[DIR_ATTR_OFF]
        if raw[0] == DIR_ENTRY_DELETED or attr == ATTR_LFN or attr & ATTR_VOLUME_LABEL:
            continue
        name = _entry_name(raw)
        if name in DOT_ENTRIES:
            continue
        reason = _unusable_name(name)
        if reason:
            warnings.append("%s: skipping entry — %s (%r)"
                            % (parent_path or "<root>", reason, name))
            continue
        entries.append(dict(
            name=name,
            path=parent_path + "/" + name if parent_path else name,
            attr=attr,
            is_dir=bool(attr & ATTR_DIRECTORY),
            cluster=le16(raw, DIR_START_CLUSTER_OFF),
            size=struct.unpack_from("<I", raw, DIR_SIZE_OFF)[0],
        ))
    return entries


def walk(image):
    """Every file and directory in the volume, depth-first, parents before children."""
    root = image.sectors(image.bpb["root_start"], image.bpb["root_sectors"])
    return _walk_entries(image, _parse_dir_entries(root, "", image.warnings), set())


def _walk_entries(image, entries, visited_dirs):
    out = []
    for entry in entries:
        out.append(entry)
        if not entry["is_dir"]:
            continue
        if entry["cluster"] in visited_dirs:
            image.warnings.append("%s: directory revisits cluster %d — not descending"
                                  % (entry["path"], entry["cluster"]))
            continue
        visited_dirs.add(entry["cluster"])
        block = image.chain_bytes(entry["cluster"], entry["path"])
        children = _parse_dir_entries(block, entry["path"], image.warnings)
        out += _walk_entries(image, children, visited_dirs)
    return out


def _magic(head):
    printable = "".join(chr(b) if 32 <= b < 127 else "." for b in head)
    return "%-*s %s" % (MAGIC_BYTES * 2, head.hex(), printable)


def _magic_head(image, entry):
    """The file's first bytes — the whole chain is checked, only its head is read."""
    clusters = image.file_clusters(entry)
    if not clusters:
        return b""
    return image.cluster_bytes(clusters[0])[:MAGIC_BYTES]


def print_listing(image):
    bpb = image.bpb
    print("BPB   %d bytes/sector, %d sectors/cluster, %d reserved, %d FATs x %d sectors,"
          " %d root entries" % (bpb["bytes_per_sector"], bpb["sectors_per_cluster"],
                                bpb["reserved_sectors"], bpb["fat_count"],
                                bpb["sectors_per_fat"], bpb["root_entries"]))
    print("      %d total sectors, media 0x%02x, %d sectors/track, %d heads"
          % (bpb["total_sectors"], bpb["media_byte"], bpb["sectors_per_track"], bpb["heads"]))
    print("      FAT@%d root@%d(%d sectors) data@%d, %d clusters of %d bytes"
          % (bpb["fat_start"], bpb["root_start"], bpb["root_sectors"], bpb["data_start"],
             bpb["cluster_count"], bpb["cluster_size"]))
    print()
    print("%-*s %9s %8s  %s" % (PATH_COLUMN, "PATH", "SIZE", "CLUSTER", "MAGIC"))
    files = 0
    total = 0
    for entry in walk(image):
        if entry["is_dir"]:
            print("%-*s %9s %8d  <DIR>" % (PATH_COLUMN, entry["path"], "", entry["cluster"]))
            continue
        files += 1
        total += entry["size"]
        print("%-*s %9d %8d  %s"
              % (PATH_COLUMN, entry["path"], entry["size"], entry["cluster"],
                 _magic(_magic_head(image, entry))))
    print("\n%d files, %d bytes" % (files, total))


def _safe_path(outdir, path, warnings):
    """Join a FAT path under outdir. Returns None (with a warning) if it could escape."""
    target = outdir
    for part in path.split("/"):
        reason = _unusable_name(part)
        if reason:
            warnings.append("%s: refusing to extract — %s (%r)" % (path, reason, part))
            return None
        target = os.path.join(target, part)
    return target


def extract(image, outdir):
    count = 0
    written = 0
    os.makedirs(outdir, exist_ok=True)
    for entry in walk(image):
        target = _safe_path(outdir, entry["path"], image.warnings)
        if target is None:
            continue
        if entry["is_dir"]:
            os.makedirs(target, exist_ok=True)
            continue
        blob = image.file_bytes(entry)
        with open(target, "wb") as fh:
            fh.write(blob)
        count += 1
        written += len(blob)
        print("%-*s %9d bytes" % (PATH_COLUMN, entry["path"], len(blob)))
    print("\nextracted %d files, %d bytes -> %s" % (count, written, outdir))


def _parse_args(args):
    """(image path, outdir or None) — or (None, None) after printing why it is unusable."""
    if args[0].startswith("-"):
        sys.stderr.write("%s\n" % USAGE)
        return None, None
    outdir = None
    if "-o" in args:
        flag = args.index("-o")
        if flag + 1 >= len(args):
            sys.stderr.write("-o needs an output directory\n%s\n" % USAGE)
            return None, None
        outdir = args[flag + 1]
    return args[0], outdir


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    path, outdir = _parse_args(args)
    if path is None:
        return 2
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as err:
        sys.stderr.write("cannot read %s: %s\n" % (path, err))
        return 1
    try:
        image = Fat12Image(data)
    except ValueError as err:
        sys.stderr.write("%s: not a usable FAT12 image: %s\n" % (path, err))
        return 1
    print("IMAGE %s (%d bytes)" % (path, len(data)))
    if outdir:
        extract(image, outdir)
    else:
        print_listing(image)
    for warning in image.warnings:
        sys.stderr.write("WARNING %s\n" % warning)
    return 1 if image.warnings else 0


if __name__ == "__main__":
    sys.exit(main())
