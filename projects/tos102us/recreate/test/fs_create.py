r"""The CREATE layer's staging — what `src/gemdos/fs_create.c`'s three batteries share.

`test/fs_dir.py` stages the directory tree (`\SUBDIR\INNER\LEAF`, `\BIG`, `\FULL`, ...) and the text a
path is handed in; `test/fs_io.py` the drive and an all-empty cache. What this adds:

  * THE TREE GROWN BY TWO EMPTY DIRECTORIES in the root, past `FULL` — which is what `Ddelete` needs,
    since every directory `fs_dir` stages has something in it:

        \EMPTYD     cluster 14: `.`, `..`, one DELETED entry, then the end-of-directory entry
        \DELDIR     cluster 15: `.`, `..` and deleted entries to the end of its only cluster — no end
                    entry, so a scan for contents runs off the chain

  * VARIANTS of that tree's disk: a root with no free slot at all, a root with no deleted entry, and a
    disk with no free cluster.
  * A CLOCK: `GEMDOS_TIME` and `GEMDOS_DATE` poked to values no staged entry holds, so a new entry's
    time and date are told from the staged ones — and their byte order read.
  * Two RECORD SLOTS for what these batteries free or recycle.

Every routine here takes the text at `fs_dir.TEXT_AT`, and is entered through `gemdos_fs`'s one door
(`fs.CREATE`, `fs.FCREATE`, `fs.DDELETE`, `fs.DCREATE`).
"""
import fs_dir as d
import fs_records as records
import gemdos
import gemdos_fs as fs

# ---- the tree -------------------------------------------------------------------------------------
EMPTYD_CLUSTER, DELDIR_CLUSTER = 14, 15
DELETED_FILLER = d.ENTRIES_PER_CLUSTER - d.DOT_ENTRIES


def _deleted(index):
    return d.entry(f"D{index:02d}", "TXT", deleted=True)


ROOT_ROWS = d.ROOT_ROWS + (
    ("EMPTYD", "", fs.GEMDOS_ATTR_SUBDIR, EMPTYD_CLUSTER, 0, False),
    ("DELDIR", "", fs.GEMDOS_ATTR_SUBDIR, DELDIR_CLUSTER, 0, False),
)
ROOT = [d.entry(*row) for row in ROOT_ROWS]
ROOT_INDEX = fs.index_by_name(ROOT_ROWS)
ROOT_END = len(ROOT)
EMPTYD = ((EMPTYD_CLUSTER,), fs.dots(EMPTYD_CLUSTER, 0) + [_deleted(0)])
DELDIR = ((DELDIR_CLUSTER,), fs.dots(DELDIR_CLUSTER, 0) + [_deleted(index) for index in range(DELETED_FILLER)])


def tree(root=None, fat=None, emptyd=EMPTYD, extra=()):
    """`fs_dir`'s tree with the root replaced by `root` (this module's `ROOT` unless the case says) and
    EMPTYD (`emptyd`, a directory as `fs_dir.directory_tree` takes one) and DELDIR written — each one
    cluster long — with the `extra` directories, then `fat` over the whole table: the poke at `IMAGE_AT`
    that replaces the disk."""
    return d.directory_tree(ROOT if root is None else root, d.DIRECTORIES + (emptyd, DELDIR) + extra, fat)


TREE = tree()
TREE_FAT = {cluster: fs.fat12_entry(fs.fat_sectors(TREE[fs.IMAGE_AT], fs.FAT1_RECORD), cluster)
            for cluster in range(fs.FAT_ENTRIES)}
# Every data cluster the tree leaves free, in order — the allocator's candidates.
FREE_CLUSTERS = [cluster for cluster in range(fs.FIRST_DATA_CLUSTER, fs.FAT_ENTRIES) if TREE_FAT[cluster] == 0]


def full_disk():
    """...and the same tree with every free cluster marked end-of-chain: nothing left to allocate."""
    return {cluster: fs.FAT12_END_OF_CHAIN for cluster in FREE_CLUSTERS}


# A root with room but nothing DELETED — GONE.OLD and XDIR left out — so a new entry takes the end entry.
LIVE_ROOT = [entry for row, entry in zip(ROOT_ROWS, ROOT) if not row[-1]]
# ...and one with no free slot at all: those entries, then files to the root's last entry — no deleted
# entry and no end-of-directory entry.
FULL_ROOT = LIVE_ROOT + [d.entry(f"R{index:02d}", "TXT") for index in range(fs.ROOT_ENTRIES - len(LIVE_ROOT))]

# ---- the clock --------------------------------------------------------------------------------------
# Two words no staged entry holds, with DIFFERENT high and low bytes, so an entry holding one in the
# wrong byte order reads as a different word.
CLOCK_TIME = 0x4321
CLOCK_DATE = 0x8765
CLOCK = {**gemdos.time_poke(CLOCK_TIME), **gemdos.date_poke(CLOCK_DATE)}

# ---- two record slots --------------------------------------------------------------------------------
# For the records these batteries free or recycle: past every slot `fs_io` (0, 1) and `fs_dir` (2..7)
# stage in, and one apart, because the pool's class word lands in the two bytes BELOW a record it takes
# back (`fs_file.pooled`), which must not be the slot before's.
FIRST_SPARE_RECORD = records.record_slot(8)
SECOND_SPARE_RECORD = records.record_slot(10)


def staged(path, pokes=None, disk=None):
    """The disk (`TREE` unless the case says), the staged DMD in drive A:'s slot, the clock and the text
    `path` at `fs_dir.TEXT_AT`, then the case's own pokes."""
    return {**d.staged({}), **(disk or TREE), **CLOCK, **d.text(path), **(pokes or {})}


# ---- reading a run back ---------------------------------------------------------------------------

def new_entry(name, extension="", attr=0, cluster=0):
    """A new entry as `create` writes it: the clock in the disk's order, no length."""
    return fs.dirent_bytes(name, extension, attr, cluster, 0, time=CLOCK_TIME, date=CLOCK_DATE)

