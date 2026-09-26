r"""The DIRECTORY layer's staging — what `src/gemdos/fs_dir.c`'s two batteries share.

`test/gemdos_fs.py` stages the disk, the drive and the cache; `test/fs_io.py` the empty buffer cache
every engine case starts from; `test/fs_records.py` says where staged records go. What this adds:

  * A TREE (`directory_tree`, over `gemdos_fs.disk`): the base root's six shapes plus a hidden and a system file,
    a deleted SUBDIRECTORY entry, a directory two clusters long and one that fills its only cluster
    with no end-of-directory entry — and under `SUBDIR` a directory two levels deep:

        \SUBDIR\INNER\LEAF          SUBDIR (2) -> INNER (8) -> LEAF (9)
        \BIG                        clusters 10 -> 11: `.`, `..`, F00..F29.TXT fill cluster 10,
                                    then LATE (12, a directory) and LAST.TXT in cluster 11
        \FULL                       cluster 13: `.`, `..`, G00..G29.TXT and NO 0 entry

  * DNDs for those directories, staged as a search would have left them, at `fs_records` slots.
  * A BAND for what the directory routines are handed: a name or a path, a position, a tail
    pointer and a DTA, each claimed in `gemdos_fs.SPAN`.
  * The glue, which is where a POINTER ARGUMENT comes back: the C takes a host pointer for the
    position and the tail (`include/gemdos/fs_dir.h`), and the glue stores what it holds after the
    call at the address the ROM was handed, so the byte compare sees the store — or its absence —
    exactly as it sees the ROM's.
"""
import ctypes
import struct

from harness import _lib

import case
import fs_io as io
import fs_records as records
import gemdos
import gemdos_fs as fs

_lib.gemdos_dir_search.restype = ctypes.c_uint32
_lib.gemdos_find_dir.restype = ctypes.c_uint32

# ---- the band: at the top of the RAM disk's span, just past the disk image ------------------------
LONG_BYTES = 4
# The longest text a case hands over: a path three directories down, with room to spare.
TEXT_BYTES = 0x80
# A DTA as far as `$fc6ebc` fills it — its name field "NAME.EXT" and a NUL — and slack after it, so a
# store past the record lands on a byte the case staged and reads as a change.
DTA_BYTES = fs.DTA_NAME + fs.FCB_STEM_BYTES + len(".") + fs.FCB_EXTENSION_BYTES + len("\0")
DTA_SLACK_BYTES = 0x10
TEXT_AT = fs.SPAN.claim(fs.IMAGE_AT + fs.DISK_BYTES, TEXT_BYTES, "test/fs_dir.py: a name or a path, NUL-ended")
POSITION_AT = fs.SPAN.claim(TEXT_AT + TEXT_BYTES, LONG_BYTES, "test/fs_dir.py: dir_search's position longword")
TAIL_AT = fs.SPAN.claim(POSITION_AT + LONG_BYTES, LONG_BYTES, "test/fs_dir.py: find_dir's tail pointer")
DTA_AT = fs.SPAN.claim(TAIL_AT + LONG_BYTES, DTA_BYTES + DTA_SLACK_BYTES, "test/fs_dir.py: Fsnext's DTA and its slack")


def text(value):
    """`value` NUL-ended at `TEXT_AT`, the rest of the buffer `SLACK_FILL`."""
    raw = value.encode("latin-1") + b"\0"
    assert len(raw) <= TEXT_BYTES
    return {TEXT_AT: raw + bytes([fs.SLACK_FILL]) * (TEXT_BYTES - len(raw))}


# ---- the tree -------------------------------------------------------------------------------------

def directory_tree(root, directories=(), fat=None):
    """The staged disk with its ROOT DIRECTORY replaced and SUBDIRECTORIES written, as the poke at
    `IMAGE_AT` that replaces the base disk.

    `root` is the root's entries in order (32-byte entries, at most `ROOT_ENTRIES`), and `directories`
    is `((chain, entries), ...)`: each directory's clusters in order — linked in BOTH FAT copies, the
    last one the end of the chain — and its entries laid across them. Every byte after a directory's
    last entry is 0, which is the end-of-directory entry; a directory whose entries fill its whole
    chain has none. `fat` is FAT12 entries laid over all of that (`{cluster: value}`). Everything else
    is the base disk's, its files and their chains included.
    """
    assert len(root) <= fs.ROOT_ENTRIES, "more entries than the root directory has room for"
    chains, clusters = {}, {}
    for chain, entries in directories:
        contents = b"".join(entries).ljust(len(chain) * fs.CLUSTER_BYTES, b"\0")
        assert len(contents) == len(chain) * fs.CLUSTER_BYTES, "more entries than the directory's clusters hold"
        for index, cluster in enumerate(chain):
            chains[cluster] = chain[index + 1] if index + 1 < len(chain) else fs.FAT12_END_OF_CHAIN
            clusters[cluster] = contents[index * fs.CLUSTER_BYTES:(index + 1) * fs.CLUSTER_BYTES]
    image = bytearray(fs.disk({**chains, **(fat or {})}, clusters)[fs.IMAGE_AT])
    root_at, root_bytes = fs.ROOT_RECORD * fs.SECTOR_BYTES, fs.ROOT_SECTORS * fs.SECTOR_BYTES
    image[root_at:root_at + root_bytes] = b"".join(root).ljust(root_bytes, b"\0")
    return {fs.IMAGE_AT: bytes(image)}


INNER_CLUSTER, LEAF_CLUSTER = 8, 9
BIG_CHAIN = (10, 11)
LATE_CLUSTER = 12
FULL_CLUSTER = 13
ENTRIES_PER_CLUSTER = fs.CLUSTER_BYTES // fs.DIRENT_BYTES
DOT_ENTRIES = len(fs.dots(0, 0))        # `.` and `..` open every subdirectory
entry = fs.staged_dirent


def directory(name, cluster):
    return entry(name, "", fs.GEMDOS_ATTR_SUBDIR, cluster)


def _numbered(prefix, count):
    return [entry(f"{prefix}{index:02d}", "TXT") for index in range(count)]


# The root: the base disk's six, then what a search has to tell apart that they do not show.
ROOT_ROWS = fs.ROOT_FILES + (
    ("SECRET", "HID", fs.GEMDOS_ATTR_HIDDEN, 0, 0, False),
    ("KERNEL", "SYS", fs.GEMDOS_ATTR_SYSTEM, 0, 0, False),
    ("BIG", "", fs.GEMDOS_ATTR_SUBDIR, BIG_CHAIN[0], 0, False),
    ("XDIR", "", fs.GEMDOS_ATTR_SUBDIR, 0, 0, True),              # a deleted subdirectory: no DND
    ("FULL", "", fs.GEMDOS_ATTR_SUBDIR, FULL_CLUSTER, 0, False),
)
ROOT = [entry(*row) for row in ROOT_ROWS]
ROOT_INDEX = fs.index_by_name(ROOT_ROWS)
ROOT_END = len(ROOT)                    # the index of the root's end-of-directory entry
BIG_FILLER = ENTRIES_PER_CLUSTER - DOT_ENTRIES
FULL_FILLER = ENTRIES_PER_CLUSTER - DOT_ENTRIES
# The tree's subdirectories, in `directory_tree`'s shape — for a battery that grows the tree by its own.
DIRECTORIES = (
    ((fs.SUBDIR_CLUSTER,), fs.dots(fs.SUBDIR_CLUSTER, 0) + [directory("INNER", INNER_CLUSTER),
                                                             entry("NOTE", "TXT")]),
    ((INNER_CLUSTER,), fs.dots(INNER_CLUSTER, fs.SUBDIR_CLUSTER) + [entry("DEEP", "TXT"),
                                                                   directory("LEAF", LEAF_CLUSTER)]),
    ((LEAF_CLUSTER,), fs.dots(LEAF_CLUSTER, INNER_CLUSTER)),
    (BIG_CHAIN, fs.dots(BIG_CHAIN[0], 0) + _numbered("F", BIG_FILLER)
     + [directory("LATE", LATE_CLUSTER), entry("LAST", "TXT")]),
    ((LATE_CLUSTER,), fs.dots(LATE_CLUSTER, BIG_CHAIN[0])),
    ((FULL_CLUSTER,), fs.dots(FULL_CLUSTER, 0) + _numbered("G", FULL_FILLER)),
)
TREE = directory_tree(ROOT, DIRECTORIES)


def position_of(index):
    """A directory's read position once it has read entry `index` — what DND_SCANNED and a search's
    position count in."""
    return (index + 1) * fs.DIRENT_BYTES


# ---- the DNDs a search would have made ------------------------------------------------------------
SUBDIR_DND_AT = records.record_slot(2)
INNER_DND_AT = records.record_slot(3)
BIG_DND_AT = records.record_slot(4)
FULL_DND_AT = records.record_slot(5)
OTHER_DND_AT = records.record_slot(6)   # a child made some other way (Dcreate's), for the known-name arm
LEAF_DND_AT = records.record_slot(7)


def dnd(at, name, cluster, parent, parent_ofd, index, **fields):
    """The DND `$fc65a2` makes for the subdirectory entry `index` of its parent — no OFD yet, no
    children, nothing scanned — with `fields` over it."""
    return fs.stage_dnd(at, **{"name": fs.fcb_name(name), "strtcl": cluster,
                               "time": fs.as_stored(fs.STAGED_DIRENT_TIME), "date": fs.as_stored(fs.STAGED_DIRENT_DATE),
                               "parent": parent, "dmd": fs.DMD_AT,
                               "parent_ofd": parent_ofd, "dirpos": index * fs.DIRENT_BYTES, **fields})


def root(**fields):
    """The staged drive's root DND with `fields` over it — a child list, a mark."""
    return {fs.ROOT_DND_AT: fs.root_dnd_bytes(fs.ROOT_OFD_AT, fs.DMD_AT, **fields)}


def root_ofd(**fields):
    """...and its OFD, as `drive()` stages it, with `fields` over it (OFD_SCANNED)."""
    return {fs.ROOT_OFD_AT: fs.root_ofd_bytes(fs.DMD_AT, **fields)}


def subdir_dnd(**fields):
    return dnd(SUBDIR_DND_AT, "SUBDIR", fs.SUBDIR_CLUSTER, fs.ROOT_DND_AT, fs.ROOT_OFD_AT,
               ROOT_INDEX["SUBDIR"], **fields)


def inner_dnd(**fields):
    return dnd(INNER_DND_AT, "INNER", INNER_CLUSTER, SUBDIR_DND_AT, 0, DOT_ENTRIES, **fields)


def leaf_dnd(**fields):
    return dnd(LEAF_DND_AT, "LEAF", LEAF_CLUSTER, INNER_DND_AT, 0, DOT_ENTRIES + 1, **fields)


def big_dnd(**fields):
    return dnd(BIG_DND_AT, "BIG", BIG_CHAIN[0], fs.ROOT_DND_AT, fs.ROOT_OFD_AT, ROOT_INDEX["BIG"],
               **fields)


def full_dnd(**fields):
    return dnd(FULL_DND_AT, "FULL", FULL_CLUSTER, fs.ROOT_DND_AT, fs.ROOT_OFD_AT, ROOT_INDEX["FULL"],
               **fields)


def staged(pokes):
    """The tree and the staged DMD in drive A:'s slot, then the case's own pokes — what `fs_io.run`
    stages the machine from."""
    return {**TREE, **fs.dmd_pointer_poke(io.DRIVE), **pokes}


# ---- reading a run back --------------------------------------------------------------------------
# The most DNDs a child list can hold: one per entry of the longest directory staged.
MOST_CHILDREN = ENTRIES_PER_CLUSTER * len(BIG_CHAIN)


def _child_list(result, dnd_at):
    return fs.linked(result.long, dnd_at + fs.DND_CHILD, fs.DND_SIBLING, MOST_CHILDREN)


def _name_of(result, dnd_at):
    return result.after(dnd_at + fs.DND_NAME, fs.DIRENT_NAME_BYTES)


def children(result, dnd_at):
    """The names on `dnd_at`'s child list after a run, first first, as text."""
    return [_name_of(result, child).decode("latin-1").rstrip() for child in _child_list(result, dnd_at)]


def child_named(result, dnd_at, name):
    """The DND on `dnd_at`'s list named `name` after a run, or 0."""
    return next((child for child in _child_list(result, dnd_at) if _name_of(result, child) == fs.fcb_name(name)), 0)


def _store_long(buf, at, value):
    """A longword into the candidate's image — the store a C pointer argument made, put where the ROM
    was handed the address."""
    buf[at:at + LONG_BYTES] = struct.pack(">I", value & fs.LONG_MASK)


# ---- dir_search, $fc663c --------------------------------------------------------------------------

def search_pokes(dnd_at, name, attr, position, pokes=None):
    """A search of `dnd_at`'s directory for the text `name` under `attr`, from `position`."""
    return staged({**text(name), POSITION_AT: struct.pack(">i", position), **(pokes or {}),
                   **case.args(">IIHI", dnd_at, TEXT_AT, attr, POSITION_AT)})


def search_glue(dnd_at, attr, position):
    """...and our C over the same, the position handed as a host cell and stored back where the ROM
    was handed it."""
    def glue(lib, buf):
        cell = ctypes.c_int32(position)
        found = lib.gemdos_dir_search(buf, dnd_at, TEXT_AT, attr, ctypes.byref(cell))
        _store_long(buf, POSITION_AT, cell.value)
        return found
    return glue


# ---- find_dir, $fc696c ----------------------------------------------------------------------------
# What the tail pointer holds before a run: an address no arm stores, so an arm that stores nothing
# leaves it and one that does is a change.
TAIL_BEFORE = 0xDEAD_BEEF


def find_pokes(path, take_tail, pokes=None):
    """A walk of the text `path`, `take_tail` or not."""
    return staged({**text(path), TAIL_AT: struct.pack(">I", TAIL_BEFORE), **(pokes or {}),
                   **case.args(">IIH", TEXT_AT, TAIL_AT, take_tail)})


def find_glue(take_tail):
    """...and our C, the tail handed as a host cell and stored back where the ROM was handed it."""
    def glue(lib, buf):
        cell = ctypes.c_uint32(TAIL_BEFORE)
        found = lib.gemdos_find_dir(buf, TEXT_AT, ctypes.byref(cell), take_tail)
        _store_long(buf, TAIL_AT, cell.value)
        return found
    return glue


# ---- Fsnext, $fc6df4 ------------------------------------------------------------------------------

def dta(pattern, attr, position, dnd_at):
    """The DTA as `Fsfirst` leaves it: the TEXT pattern (NUL-padded to its twelve bytes), the
    attribute, and the two UNALIGNED longwords — then `SLACK_FILL` over what a find fills."""
    raw = pattern.encode("latin-1")
    assert len(raw) < fs.DTA_PATTERN_BYTES
    record = bytearray([fs.SLACK_FILL]) * (DTA_BYTES + DTA_SLACK_BYTES)
    record[fs.DTA_PATTERN:fs.DTA_PATTERN + fs.DTA_PATTERN_BYTES] = raw.ljust(fs.DTA_PATTERN_BYTES, b"\0")
    record[fs.DTA_ATTR] = attr
    struct.pack_into(">iI", record, fs.DTA_DIRPOS, position, dnd_at)
    return {DTA_AT: bytes(record), **gemdos.dta_poke(DTA_AT)}


def fsnext_pokes(pattern, attr, position, dnd_at, pokes=None):
    return staged({**dta(pattern, attr, position, dnd_at), **(pokes or {})})
