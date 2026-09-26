"""The I/O ENGINE's staging — what `src/gemdos/fs_io.c`'s three batteries share.

`test/gemdos_fs.py` stages the disk, the drive, the cache and the user buffer, and builds every
record; `test/fs_records.py` says where records go. What this adds is the two things only the engine
needs:

  * VARIANTS OF THE DISK. A FAT16 table (a FAT12 one with the entries a case needs is
    `gemdos_fs.disk`), and the drive descriptor re-staged with fields changed (the FAT16 flag, a
    four-sector geometry). Built over `gemdos_fs.DISK` rather than beside it, so the six root files
    every other battery reads are still there.
  * OPEN FILES: an OFD over one of the disk's files, its cursor where the case says.
"""
import struct

from harness import addrs

import fs_records as records
import gemdos
import gemdos_fs as fs

DRIVE = 0

# ---- the disk ------------------------------------------------------------------------------------

def fat16_disk(entries):
    """...and the same disk with a FAT16 table: little-endian words, entry `n` at byte `2n`."""
    table = bytearray(fs.FAT_SECTORS * fs.SECTOR_BYTES)
    for cluster, value in entries.items():
        struct.pack_into("<H", table, cluster * fs.FAT16_ENTRY_BYTES, value)
    return {fs.IMAGE_AT: bytes(fs.with_fat(fs.DISK, bytes(table)))}


def fat_after(result):
    """The FAT a run left: the disk's second copy, with every FAT sector the cache holds laid over
    it (a cached sector is the newer one — it is what a flush would write)."""
    table = bytearray(fs.fat_sectors(result.after(fs.IMAGE_AT, fs.DISK_BYTES), fs.FAT2_RECORD))
    for index in result.order(0):
        if result.word(fs.bcb_at(index) + fs.BCB_BUFDRV) == fs.BCB_EMPTY:
            continue
        sector = (result.word(fs.bcb_at(index) + fs.BCB_BUFREC)
                  - fs.cluster_record(fs.FAT_START_CLUSTER)) & fs.D0_LOW_WORD
        table[sector * fs.SECTOR_BYTES:(sector + 1) * fs.SECTOR_BYTES] = result.after(
            fs.buffer_at(index), fs.SECTOR_BYTES)
    return bytes(table)


def drive(**dmd_fields):
    """`gemdos_fs.drive()` with DMD fields replaced by `gemdos_fs.DMD_FIELDS` key — `drive(fat16=1)`."""
    return fs.drive(DRIVE, **dmd_fields)


# A SECOND GEOMETRY over the same sectors: FOUR-sector clusters, the DMD `$fc53c0` would build for a
# BPB saying so. The FAT and the root directory still take one (pseudo-)cluster each, so their start
# clusters and the three records they map to are unchanged; the data area is 16 clusters of 2 KB.
# It exists for the arms whose arithmetic only a cluster of more than two sectors can tell apart
# (`src/gemdos/fs_io.c`, the head's cluster finished with the SECTOR INDEX as the count; `$fc70f6`'s
# loop over a cluster's sectors after the first).
BIG_CLUSTER_SECTORS = 4
BIG_CLUSTER_BYTES = BIG_CLUSTER_SECTORS * fs.SECTOR_BYTES


def big_cluster_drive():
    return drive(recoff=(fs.FAT2_RECORD - fs.FAT_START_CLUSTER * BIG_CLUSTER_SECTORS,
                         fs.ROOT_RECORD - fs.ROOT_START_CLUSTER * BIG_CLUSTER_SECTORS,
                         fs.DATA_RECORD - fs.FIRST_DATA_CLUSTER * BIG_CLUSTER_SECTORS),
                 clsiz=BIG_CLUSTER_SECTORS, clsiz_log2=fs.log2(BIG_CLUSTER_SECTORS),
                 clsiz_mask=BIG_CLUSTER_SECTORS - 1, clsizb=BIG_CLUSTER_BYTES,
                 clsizb_log2=fs.log2(BIG_CLUSTER_BYTES),
                 numcl=fs.DATA_CLUSTERS * fs.SECTORS_PER_CLUSTER // BIG_CLUSTER_SECTORS)


def big_cluster_record(cluster, sector=0):
    """...and the BIOS record of a sector of one of ITS clusters."""
    return fs.DATA_RECORD + (cluster - fs.FIRST_DATA_CLUSTER) * BIG_CLUSTER_SECTORS + sector


# Every case's cache unless its layer stages another: two FAT buffers and four data buffers, all
# EMPTY, so each run's sectors arrive through the ROM's own misses. A case that wants a hit stages its
# own chain.
def cache():
    return fs.cache(fat=[(0, fs.EMPTY), (1, fs.EMPTY)],
                    data=[(index, fs.EMPTY) for index in range(2, fs.BCB_COUNT)])


# ---- open files ----------------------------------------------------------------------------------
OFD_AT = records.record_slot(0)
OTHER_OFD_AT = records.record_slot(1)


def open_file(first_cluster, length, at=OFD_AT, **cursor):
    """An OFD over a file on the staged drive — `first_cluster`, `length`, and the cursor fields
    (`pos`, `curcl`, `currec`, `cloff`, `flags`) the case names; every other byte is the fill, so a
    field the engine should not touch and did reads as a change."""
    return fs.stage_ofd(at, fill=fs.SLACK_FILL, strtcl=first_cluster, fileln=length, dmd=fs.DMD_AT,
                        **{"pos": 0, "curcl": 0, "currec": 0, "cloff": 0, "flags": 0, **cursor})


def at_cursor(position, cluster, cloff):
    """The cursor fields of an OFD sitting at `position` in `cluster`."""
    return {"pos": position, "curcl": cluster, "currec": fs.cluster_record(cluster), "cloff": cloff}


# ---- running a case ------------------------------------------------------------------------------

def engine(pokes, buffers=None):
    """The staged drive, the cache — `buffers` if the case's layer stages its own (`fs.cache`'s pokes,
    every BCB and both list heads), `cache()` otherwise — and the user buffer, then the case's own
    pokes over them."""
    return {**drive(), **(cache() if buffers is None else buffers), **fs.user_buffer(), **pokes}


def run(entry, glue, pokes, buffers=None, **kwargs):
    """`gemdos_fs.run` over `engine(pokes, buffers)`."""
    return fs.run(entry, glue, engine(pokes, buffers), **kwargs)


def register(name, entry, pokes, regs=None, buffers=None):
    """...and the same staging as a `VERIFIED_CASES` row."""
    return gemdos.register(name, entry, {"a5": 0, **(regs or {})}, fs.machine(engine(pokes, buffers)))


def dispatch_slice(leaf, words, pokes, buffers=None):
    """`gemdos_fs.dispatch_slice` over the same staging."""
    return fs.dispatch_slice(leaf, words, engine(pokes, buffers))


def rwabs_calls():
    """The run's `Rwabs` traffic as `(rwflag, count, bios record)` — what a transfer case asserts."""
    return [(call[1], call[3], call[4]) for call in fs.DISK_CALLS if call[0] == addrs.BIOS_RWABS_FN]


def data_transfers():
    """...and only its transfers of DATA records, which is a transfer case's claim: the FAT sectors
    a chain walk reads on the way are the cache's business, and `test_gemdos_fs_fat.py`'s."""
    return [call for call in rwabs_calls() if call[2] >= fs.DATA_RECORD]


def data_record(cluster, sector=0):
    """The BIOS record of `sector` of data cluster `cluster`."""
    return fs.record_of_cluster(cluster) + sector
