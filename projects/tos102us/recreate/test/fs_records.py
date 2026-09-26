"""THE RECORD GAP — where the file system's batteries stage their DNDs, OFDs, directory entries and
buffers, and the record pool's two staged states.

The records themselves are built by `test/gemdos_fs.py` (`dnd_bytes`, `ofd_bytes`, `dirent_bytes`,
...), out of `include/gemdos/fs.h`'s own offsets; this module says WHERE they go.

WHERE THEY GO. `staging.SCRATCH`'s 4 KB is claimed to its last byte by `test/staging.py`'s registry,
so these records live where the 8.3 name battery's buffers already do: in the RAM disk's own span
(`gemdos_fs.RAM_DISK_AT`), in the gap between the staged BCBs' last buffer and the disk image, which
`test_gemdos_fs_disk.py` proves is clear of every declared tenant and zero in the capture. Every band
in it is claimed through `gemdos_fs.SPAN`, the one registry of the file system's window, and the gap's
MAP is below: each battery's band is placed here by name, so no battery places itself by another's
size, and an overlap between two is refused by the registry.
"""
import struct

import gemdos_fs as fs
import gemdos_memory as gm

# ---- the gap, and its map ------------------------------------------------------------------------
GAP_ALIGN = 0x100
GAP_AT = -(-fs.bcb_at(fs.BCB_COUNT) // GAP_ALIGN) * GAP_ALIGN     # above the last staged BCB
GAP_END = fs.IMAGE_AT                                              # ...and below the disk

# Record slots: every DND and OFD is a pool record of one size class, so one stride serves both.
RECORD_STRIDE = fs.DND_BYTES
assert fs.OFD_BYTES == RECORD_STRIDE
RECORD_SLOTS = 12
SLOTS_AT = fs.SPAN.claim(GAP_AT, RECORD_SLOTS * RECORD_STRIDE, "test/fs_records.py, record slots")
DIRENT_SLOTS = 8
DIRENTS_AT = fs.SPAN.claim(SLOTS_AT + RECORD_SLOTS * RECORD_STRIDE, DIRENT_SLOTS * fs.DIRENT_BYTES,
                           "test/fs_records.py, directory-entry slots")
FREE_AT = DIRENTS_AT + DIRENT_SLOTS * fs.DIRENT_BYTES

# ...and the batteries' own bands above the slots, each claimed by the battery that stages there.
COPY_BAND_AT = FREE_AT                          # `test_gemdos_fs_copy.py`: a source and a destination
COPY_BAND_BYTES = 0x300
TEXT_BAND_AT = COPY_BAND_AT + COPY_BAND_BYTES   # `test_gemdos_fs_records.py`: a text and a DTA
TEXT_BAND_BYTES = 0x80
BPB_BAND_AT = TEXT_BAND_AT + TEXT_BAND_BYTES    # `test_gemdos_fs_drive.py`: a BPB of another geometry
PATH_BAND_BYTES = 0x100
PATH_BAND_AT = GAP_END - PATH_BAND_BYTES        # `test_gemdos_fs_path.py`: a pointer, two strings, an FCB


def record_slot(index):
    """The address of staged record `index` (a DND or an OFD)."""
    assert 0 <= index < RECORD_SLOTS
    return SLOTS_AT + index * RECORD_STRIDE


def dirent_slot(index):
    """...and of staged directory entry `index`."""
    assert 0 <= index < DIRENT_SLOTS
    return DIRENTS_AT + index * fs.DIRENT_BYTES


# ---- the record pool, as a record-making routine meets it ----------------------------------------
# Every DND and OFD comes out of `gemdos_pool_get` ($fc7f1a) as size class `NODE_POOL_CLASS`. The
# snapshot's chain for that class is EMPTY, so a case that stages nothing gets a record cut from the
# arena; these two stage the other two states that routine has — a record waiting on the chain, and
# nothing left anywhere.
POOL_CHAIN = gm.GEMDOS_P_ROOT + fs.NODE_POOL_CLASS * gm.POOL_CHAIN_ENTRY_BYTES
POOL_LINK_BYTES = 4                             # a free record's first longword: the next on the chain
# What a RECYCLED record still holds: `gemdos_pool_free` overwrites only its link, so the rest is
# whatever the record last described — which is what makes the pool's CLEAR a visible store.
STALE_FILL = 0x5A


def pool_recycled(*records):
    """The class's free chain holding `records`, in order, each a stale record linked to the next."""
    pokes = {POOL_CHAIN: struct.pack(">I", records[0] if records else 0)}
    for index, at in enumerate(records):
        link = records[index + 1] if index + 1 < len(records) else 0
        pokes[at] = struct.pack(">I", link) + bytes([STALE_FILL]) * (RECORD_STRIDE - POOL_LINK_BYTES)
    return pokes


def pool_spent():
    """...and a pool with nothing to give: an empty chain and an arena with no words left."""
    return {POOL_CHAIN: struct.pack(">I", 0), gm.GEMDOS_POOL_FREE_WORDS: struct.pack(">H", 0)}


# The fields outside the gap these helpers poke, for `test_boot_snapshot.py`'s `CASE_FIELDS` (the
# gap's own bands are `gemdos_fs.SPAN.claims`).
CASE_FIELDS = (
    (POOL_CHAIN, gm.POOL_CHAIN_ENTRY_BYTES, "the record pool's node-class free chain head"),
    (gm.GEMDOS_POOL_FREE_WORDS, 2, "...and the arena's words-left counter"),
)
