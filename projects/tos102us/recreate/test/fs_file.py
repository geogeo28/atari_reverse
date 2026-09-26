"""The FILE layer's staging — what `src/gemdos/fs_file.c`'s batteries (and `Fclose`'s file arm,
`Dfree`, `Dgetpath` beside them) share.

`test/gemdos_fs.py` stages the disk and builds every record, `test/fs_records.py` says where records
go and `test/fs_io.py` stages the drive, an all-empty cache and the user buffer. What this adds is
the one shape every routine here starts from: a file of the staged disk's ROOT DIRECTORY held OPEN —
an OFD mirroring its entry exactly as `$fc6fdc` would have built it, on the root DND's list of open
files, named by a handle record — and a cache with work in it, so that "every buffer flushed" is a
set of sector writes a case can read back rather than a walk over buffers holding nothing.
"""
import struct

from harness import addrs

import fs_io as io
import fs_records as records
import gemdos
import gemdos_fs as fs
import gemdos_memory as gm
import gemdos_process as process

# ---- the root directory's entries --------------------------------------------------------------
# `gemdos_fs.ROOT_FILES`, by name.
ROOT_ENTRY = {name: entry for name, *entry in fs.ROOT_FILES}


def entry_position(name):
    """The byte offset of a root entry in the root directory — the `pos` every routine here takes."""
    return fs.ROOT_INDEX[name] * fs.DIRENT_BYTES


def root_entry_after(result, name):
    """The 32 bytes of a root entry ON THE DISK after a run — what a flush left there."""
    return result.root_entry(fs.ROOT_INDEX[name])


def open_entry(name, at=io.OFD_AT, **fields):
    """An OFD over root entry `name` as `$fc6fdc` builds one: the entry's time and date as stored,
    its cluster and length turned round, the root's DND and OFD as the holding directory, and the
    entry's position — every other field the case names, every byte nobody names `SLACK_FILL`."""
    _extension, _attr, cluster, length, _deleted = ROOT_ENTRY[name]
    cluster, length = fields.pop("strtcl", cluster), fields.pop("fileln", length)
    return io.open_file(cluster, length, at, **{
        "time": fs.as_stored(fs.STAGED_DIRENT_TIME), "date": fs.as_stored(fs.STAGED_DIRENT_DATE),
        "dir_dnd": fs.ROOT_DND_AT, "dir_ofd": fs.ROOT_OFD_AT, "dirpos": entry_position(name),
        "link": 0, **fields})


def pooled(at):
    """The pool's class word below a record at `at` — what `gemdos_pool_free` files it by, and what
    `$fc6fdc`'s `pool_get(4)` would have left there. It lands in the two bytes BELOW the record, so a
    record that is to be freed goes in a slot whose predecessor holds nothing else."""
    return {at - gm.POOL_CLASS_HEADER_BYTES: struct.pack(">H", fs.NODE_POOL_CLASS)}


def root_files(head):
    """The root DND's list of open files, by its HEAD: each OFD's own `link` field (`open_entry`)
    chains the rest — a separate poke of the link would land on the same address as the OFD's own
    and replace it."""
    return {fs.ROOT_DND_AT + fs.DND_FILES: struct.pack(">I", head)}


def files_after(result):
    """...and the list a run left, head first."""
    return list(fs.linked(result.long, fs.ROOT_DND_AT + fs.DND_FILES, fs.OFD_LINK, records.RECORD_SLOTS))


# ---- a time and a date -------------------------------------------------------------------------
# What a close writes back or `Fdatime` sets: values no staged entry holds, so the rewritten entry is
# told from the one that was there.
NEW_TIME = 0x9ABC
NEW_DATE = 0xDEF0
# The two words `Fdatime` moves — `include/gemdos/fs.h`'s DIRENT_TIME_DATE_BYTES, the same expression.
TIME_DATE_BYTES = fs.DIRENT_STRTCL - fs.DIRENT_TIME


def stamp(time, date):
    """A time and a date as a caller's buffer holds them: two words in the 68000's order."""
    return struct.pack(">HH", time, date)


def stamp_on_disk(time, date):
    """...and as an entry stores them, little-endian."""
    return struct.pack("<HH", time, date)


# ---- handles -----------------------------------------------------------------------------------
A_HANDLE = addrs.GEMDOS_FIRST_FILE_HANDLE
ANOTHER_HANDLE = A_HANDLE + 1
P_RUN = gemdos.BASEPAGE
# Another process, as an OWNER longword: any basepage address that is not `p_run`'s — here the one a
# TOS basepage's own length above it.
BASEPAGE_BYTES = 0x100
SOMEBODY_ELSE = gemdos.BASEPAGE + BASEPAGE_BYTES


def handle_naming(ofd, handle=A_HANDLE, owner=P_RUN, references=1):
    """A handle record naming `ofd`, owned by `owner`."""
    return process.descriptor_poke(handle, ofd, owner, references)


# ---- a cache with work in it -------------------------------------------------------------------
# A FAT sector and a data sector DIRTY, one data sector CLEAN, the other three buffers empty. What
# each dirty one holds is a byte pattern no disk sector has, so the write a flush makes is a byte the
# case can find on the disk afterwards.
DIRTY_FAT_SEED = 0xC0
DIRTY_FAT_BYTES = fs.body(DIRTY_FAT_SEED, fs.SECTOR_BYTES)
# A ramp of stride 3 from its own seed: no staged file's body (stride 1) holds it at any offset.
DIRTY_DATA_SEED, DIRTY_DATA_STRIDE = 0x70, 3
DIRTY_DATA_BYTES = bytes((DIRTY_DATA_SEED + DIRTY_DATA_STRIDE * index) & 0xFF for index in range(fs.SECTOR_BYTES))
DIRTY_DATA_CLUSTER = fs.SHORT_CLUSTER
CLEAN_DATA_CLUSTER = fs.SPAN_CLUSTER

# The six staged BCBs by role: each list's head holds work, the rest are EMPTY.
DIRTY_FAT_BCB, SPARE_FAT_BCB = 0, 1
DIRTY_DATA_BCB, CLEAN_DATA_BCB, *SPARE_DATA_BCBS = range(SPARE_FAT_BCB + 1, fs.BCB_COUNT)

# The staged cache with the three buffers above: the FAT list's head dirty, the data list's head
# dirty and its second clean — the `buffers` a file-layer case runs over (`fs_io.run`).
WORKING_CACHE = fs.cache(
    fat=[(DIRTY_FAT_BCB, fs.holding(region=fs.BCB_TYPE_FAT, record=fs.FAT_PSEUDO_RECORD, dirty=fs.BCB_MARKED_DIRTY,
                                    contents=DIRTY_FAT_BYTES)),
         (SPARE_FAT_BCB, fs.EMPTY)],
    data=[(DIRTY_DATA_BCB, fs.holding(record=fs.pseudo_record(DIRTY_DATA_CLUSTER),
                                      dirty=fs.BCB_MARKED_DIRTY, contents=DIRTY_DATA_BYTES)),
          (CLEAN_DATA_BCB, fs.holding(record=fs.pseudo_record(CLEAN_DATA_CLUSTER))),
          *((index, fs.EMPTY) for index in SPARE_DATA_BCBS)])


def assert_every_buffer_flushed(result):
    """What `$fc58cc` leaves: both dirty sectors on the disk — the FAT one in BOTH copies — and no
    buffer of either list dirty. `$fc590a` keeps a buffer it has just WRITTEN (clean, still holding
    its sector) and EMPTIES every one that was clean already, so the staged clean buffer is gone and
    the two staged dirty ones are still there."""
    assert result.sector(fs.FAT2_RECORD) == DIRTY_FAT_BYTES, "the FAT buffer was not written"
    assert result.sector(fs.FAT1_RECORD) == DIRTY_FAT_BYTES, "...nor its first copy"
    assert result.sector(fs.record_of_cluster(DIRTY_DATA_CLUSTER)) == DIRTY_DATA_BYTES
    for index in range(fs.BCB_COUNT):
        assert result.word(fs.bcb_at(index) + fs.BCB_DIRTY) == 0, f"buffer {index} left dirty"
    for index in (DIRTY_FAT_BCB, DIRTY_DATA_BCB):
        assert result.word(fs.bcb_at(index) + fs.BCB_BUFDRV) == io.DRIVE, f"written buffer {index} dropped"
    assert result.word(fs.bcb_at(CLEAN_DATA_BCB) + fs.BCB_BUFDRV) == fs.BCB_EMPTY, "the clean buffer kept"


def assert_nothing_flushed(result):
    """...and the arm that answers before the flush: the dirty buffers still dirty and holding."""
    assert result.word(fs.bcb_at(DIRTY_FAT_BCB) + fs.BCB_DIRTY) == fs.BCB_MARKED_DIRTY
    assert result.word(fs.bcb_at(DIRTY_DATA_BCB) + fs.BCB_DIRTY) == fs.BCB_MARKED_DIRTY
    assert result.word(fs.bcb_at(CLEAN_DATA_BCB) + fs.BCB_BUFDRV) == io.DRIVE
    assert result.sector(fs.FAT2_RECORD) == fs.sector_of(fs.DISK, fs.FAT2_RECORD)
