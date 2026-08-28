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

An EMPTY RESULT is a warning, never a silent success. A BPB whose fields point the root
directory at the wrong sector decodes into "0 files" and used to exit 0 — which reads as
"this disk is empty" rather than "this disk was not understood". A root holding no live
entries therefore warns, and the warning carries a diagnosis: the early sectors are
scanned for one shaped like a directory (32-byte 8.3 records), and each candidate is
reported together with the BPB value that would place the root there, e.g.
"sector 7 => nfats=2". `--nfats N` then applies that value without editing the image, so
a disk whose BPB under-counts its FATs (real dumps do) is readable and reproducibly so.

Usage:
  python3 st_extract.py IMAGE.ST              # list the whole tree
  python3 st_extract.py IMAGE.ST -o OUTDIR    # extract the tree into OUTDIR
  python3 st_extract.py IMAGE.ST --nfats 2    # read it with the BPB's FAT count overridden

Exit status:
  0  clean run
  1  unusable image, or the run completed but emitted warnings — a dirty extraction, or a
     root directory with no live entries (nothing was listed/extracted)
  2  bad command line
"""
import os
import struct
import sys

USAGE = "usage: st_extract.py IMAGE.ST [-o OUTDIR] [--nfats N]"
OUTDIR_FLAG = "-o"
NFATS_FLAG = "--nfats"

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
BPB_FAT_COUNT_MAX = 4        # real volumes carry 1 or 2 FATs; 4 is the generous upper bound

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

DIR_NAME_BYTES = DIR_NAME_LEN + DIR_EXT_LEN   # the 11 raw 8.3 name bytes, stem and ext unseparated
ATTR_UNUSED_BITS = 0xC0     # bits 6-7 carry no meaning in a FAT attribute byte; set = not a directory
NAME_BYTE_MIN, NAME_BYTE_MAX = 0x20, 0x7E     # a live 8.3 name is printable ASCII, space-padded

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
DIAGNOSTIC_MAX_CANDIDATES = 3   # candidate root sectors the empty-root diagnosis reports


def le16(data, off):
    return struct.unpack_from("<H", data, off)[0]


def parse_bpb(boot, image_size, fat_count=None):
    """Decode + sanity-check the BPB. Raises ValueError with a reason if implausible.

    `fat_count` overrides the BPB's own FAT count, which is the one field a real dump is
    routinely wrong about and the one that silently moves the root directory.
    """
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
    if fat_count is not None:
        bpb["fat_count"] = fat_count
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
    if not 1 <= bpb["fat_count"] <= BPB_FAT_COUNT_MAX:
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

    def __init__(self, data, fat_count=None):
        self.data = data
        self.bpb = parse_bpb(data[:BOOT_SECTOR_SIZE], len(data), fat_count)
        self.warnings = []
        fat_off = self.bpb["fat_start"] * self.bpb["bytes_per_sector"]
        fat_len = self.bpb["sectors_per_fat"] * self.bpb["bytes_per_sector"]
        self.fat = data[fat_off:fat_off + fat_len]
        # Parsed once, here, so the empty-root diagnosis is emitted once however often the
        # tree is walked — `read_file` walks it per call.
        root = self.sectors(self.bpb["root_start"], self.bpb["root_sectors"])
        self.root_dir = _parse_dir_entries(root, "", self.warnings)
        if not self.root_dir:
            self.warnings += _diagnose_empty_root(self)

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


def _live_entry_count(block):
    """How many live 8.3 entries a sector holds — 0 unless the whole sector is shaped like one.

    Shape, not meaning: 32-byte records whose names are printable and whose attribute byte has
    no unused bit set, ending (if at all) in an all-zero tail. That is enough to tell a
    directory sector from a FAT sector, boot code or file data without knowing the volume.
    """
    live = 0
    for off in range(0, len(block), DIR_ENTRY_SIZE):
        raw = block[off:off + DIR_ENTRY_SIZE]
        if raw[DIR_NAME_OFF] == DIR_ENTRY_FREE:
            return live if not any(block[off:]) else 0   # past end-of-directory all is zero
        if raw[DIR_NAME_OFF] == DIR_ENTRY_DELETED:
            continue
        if raw[DIR_ATTR_OFF] & ATTR_UNUSED_BITS:
            return 0
        name = raw[DIR_NAME_OFF:DIR_NAME_OFF + DIR_NAME_BYTES]
        if any(not NAME_BYTE_MIN <= byte <= NAME_BYTE_MAX for byte in name):
            return 0
        live += 1
    return live


def _directory_like_sectors(image):
    """(sector, live entry count) for each RUN of directory-shaped sectors in the early volume.

    Only a run's first sector is offered: a directory occupies consecutive sectors, so the
    sectors after the first are its continuation, not another candidate root.
    """
    bpb = image.bpb
    # The root cannot begin later than the reserved area plus the most FATs a BPB may claim,
    # and one root's worth of slack covers a sectors/FAT that is itself understated.
    limit = min(bpb["total_sectors"],
                bpb["reserved_sectors"] + BPB_FAT_COUNT_MAX * bpb["sectors_per_fat"]
                + bpb["root_sectors"])
    previous_was_directory = False
    for sector in range(bpb["reserved_sectors"], limit):
        live = _live_entry_count(image.sectors(sector, 1))
        if live and not previous_was_directory:
            yield sector, live
        previous_was_directory = bool(live)


def _implied_bpb(bpb, root_sector):
    """The BPB value that would put the root directory at `root_sector`, as ' => field=value'.

    root_start = reserved_sectors + fat_count * sectors_per_fat, so a candidate sector pins one
    of those two fields once the others are taken as read. Empty if neither solves to a legal value.
    """
    fat_span = root_sector - bpb["reserved_sectors"]
    if fat_span > 0 and fat_span % bpb["sectors_per_fat"] == 0:
        fat_count = fat_span // bpb["sectors_per_fat"]
        if 1 <= fat_count <= BPB_FAT_COUNT_MAX:
            return " => nfats=%d (%d reserved + %d FATs x %d sectors)" % (
                fat_count, bpb["reserved_sectors"], fat_count, bpb["sectors_per_fat"])
    reserved = root_sector - bpb["fat_count"] * bpb["sectors_per_fat"]
    if reserved > 0:
        return " => reserved sectors=%d (keeping the BPB's %d FATs x %d sectors)" % (
            reserved, bpb["fat_count"], bpb["sectors_per_fat"])
    return ""


def _diagnose_empty_root(image):
    """Warnings for a root directory with no live entries: say so, and say where it might be."""
    found = ["<root>: no live directory entries at sector %d — nothing to list or extract;"
             " the BPB may be placing the root on the wrong sector"
             % image.bpb["root_start"]]
    for sector, live in _directory_like_sectors(image):
        if len(found) > DIAGNOSTIC_MAX_CANDIDATES:
            break
        found.append("<root>: DIAGNOSTIC sector %d looks like a directory (%d live entries)%s"
                     % (sector, live, _implied_bpb(image.bpb, sector)))
    if len(found) == 1:
        found.append("<root>: DIAGNOSTIC no early sector looks like a directory either —"
                     " the volume may genuinely be empty")
    return found


def walk(image):
    """Every file and directory in the volume, depth-first, parents before children."""
    return _walk_entries(image, image.root_dir, set())


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


def read_file(image, path):
    """The bytes of one file ("OWN.BIN", "AUTO/WB.PRG") out of `image`, or None if it is not there.

    The programmatic half of `extract`, for a caller that wants one named file rather than a tree —
    the case that brought this here is lifting a record off a floppy a real Atari wrote. It goes
    through the SAME `walk` and the same `file_bytes`, so a chain that loops, runs into a bad cluster
    or disagrees with the directory entry's size lands in `image.warnings` for this caller exactly as
    it does for an extraction.

    Case-insensitive and separator-insensitive: names are upper-case on the volume, and a caller may
    spell the path with either slash.
    """
    want = path.replace("\\", "/").strip("/").upper()
    for entry in walk(image):
        if not entry["is_dir"] and entry["path"].upper() == want:
            return image.file_bytes(entry)
    return None


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
    """(image path, outdir or None, FAT count or None) — path None after printing what is wrong.

    Flags may come before or after the image path; a value-taking flag consumes the token after it.
    """
    unusable = (None, None, None)
    values = {OUTDIR_FLAG: None, NFATS_FLAG: None}
    paths = []
    pending = list(args)
    while pending:
        token = pending.pop(0)
        if token in values:
            if not pending:
                sys.stderr.write("%s needs a value\n%s\n" % (token, USAGE))
                return unusable
            values[token] = pending.pop(0)
        elif token.startswith("-"):
            sys.stderr.write("unexpected argument %r\n%s\n" % (token, USAGE))
            return unusable
        else:
            paths.append(token)
    if len(paths) != 1:
        sys.stderr.write("expected exactly one image path\n%s\n" % USAGE)
        return unusable
    nfats = values[NFATS_FLAG]
    if nfats is not None and not (nfats.isdigit() and 1 <= int(nfats) <= BPB_FAT_COUNT_MAX):
        sys.stderr.write("%s needs a FAT count in 1..%d\n%s\n"
                         % (NFATS_FLAG, BPB_FAT_COUNT_MAX, USAGE))
        return unusable
    return paths[0], values[OUTDIR_FLAG], None if nfats is None else int(nfats)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    path, outdir, fat_count = _parse_args(args)
    if path is None:
        return 2
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as err:
        sys.stderr.write("cannot read %s: %s\n" % (path, err))
        return 1
    try:
        image = Fat12Image(data, fat_count)
    except ValueError as err:
        sys.stderr.write("%s: not a usable FAT12 image: %s\n" % (path, err))
        return 1
    print("IMAGE %s (%d bytes)" % (path, len(data)))
    if fat_count is not None:
        print("      %s %d overriding the BPB's own FAT count" % (NFATS_FLAG, fat_count))
    if outdir:
        extract(image, outdir)
    else:
        print_listing(image)
    for warning in image.warnings:
        sys.stderr.write("WARNING %s\n" % warning)
    return 1 if image.warnings else 0


if __name__ == "__main__":
    sys.exit(main())
