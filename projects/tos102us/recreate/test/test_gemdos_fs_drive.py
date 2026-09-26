"""The file system's DRIVE LOG-IN — `src/gemdos/fs_drive.c`'s three drive routines.

  $fc50fa  gemdos_dmd_alloc   the DMD and its three hangers-on, out of the GEMDOS record pool
  $fc53c0  gemdos_dmd_build   the BPB -> the DMD, the root node and the two pseudo-files
  $fc67de  gemdos_open_drive  `Getbpb`, the builder, and a directory slot for the running process

WHAT THIS FILE ALSO PROVES is the staged RAM disk's own descriptor. Every file-system battery before
it ran over `gemdos_fs.drive()`, a DMD computed by the ROM's own expressions and READ rather than run;
`test_the_staged_drive_is_exactly_what_the_rom_builds` runs the ROM's builder over the staged BPB and
requires the four records it cuts from the pool to be those bytes at the addresses the pool chose —
which is how the staged input became a checked claim, and how it gained the one field it lacked (the
FAT pseudo-file's start at position 3).

THE POOL IS STAGED BY ITS WORD COUNT. The snapshot's size-class chains for classes 3 and 4 are empty,
so every record comes out of the bump arena at `words + 1` apiece — 25 for the DMD, 33 for each of
the other three — and leaving the arena exactly N words short is how a case makes the Nth request
fail. `gemdos_memory`'s own battery proves the pool; this one only spends it.

POISON IS OFF wherever the pool or the BIOS is reached, each for its own battery's reason: the pool's
chain heads and counters are pointers the routine chases, so an inverted one is followed into the I/O
page (`test/gemdos_memory.py`), and the oracle's `trap #13` writes `savptr`, whose inversion sends the
save frame somewhere no case staged (`test_gemdos_fs_disk.py`). What stands in is that the pool hands
every record out CLEARED, so every non-zero field the builder stores is a byte the compare sees; the
zeros it stores over that clear (the root node's first name byte, a FAT12 drive's `m_fat16`) are
invisible to ANY run, and are recorded as such rather than pinned. A log-in of a drive already open
touches neither, and those cases poison.
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs, in_diff

import case
import fs_records
import gemdos
import gemdos_fs as fs
import gemdos_memory as memory
import gemdos_process as process

for _name in ("gemdos_dmd_alloc", "gemdos_dmd_build", "gemdos_open_drive"):
    getattr(_lib, _name).restype = ctypes.c_uint32

# The pool arithmetic of the module docstring, out of the header's own class sizes.
DMD_REQUEST_WORDS = fs.DMD_POOL_CLASS * (1 << memory.POOL_CLASS_WORDS_SHIFT) + 1
NODE_REQUEST_WORDS = fs.NODE_POOL_CLASS * (1 << memory.POOL_CLASS_WORDS_SHIFT) + 1
# ...in the order `$fc50fa` asks: the DMD, the root DND, the root OFD, the FAT OFD.
REQUEST_WORDS = (DMD_REQUEST_WORDS, NODE_REQUEST_WORDS, NODE_REQUEST_WORDS, NODE_REQUEST_WORDS)
DRIVE_RECORD_COUNT = len(REQUEST_WORDS)
DRIVE_REQUEST_WORDS = sum(REQUEST_WORDS)

# The drives: A: is logged in in the snapshot, with p_curdir[0] = 2, and B: is not.
LOGGED_IN = 0
NOT_LOGGED_IN = 1
TOP_DRIVE = 15                  # bit 15 of the mask: a SIGNED word's sign bit
NO_BIT_DRIVE = 16               # `asl.w` by 16 leaves nothing: no bit, so never "logged in"
BELOW_THE_TABLE = -1            # a signed index one entry below each table
DIGIT_DRIVE = -16               # what `$fc68dc` makes of a path starting `1:`
TOP_NODE = 0xFF                 # the node an UNSIGNED p_curdir byte of $ff would be

# The captured machine's own drive state, read rather than spelt.
SNAPSHOT_MASK = case.word_in(BASE_IMAGE, addrs.GEMDOS_DRIVES_OPENED)
# The first node slot with a zero count, which the snapshot's two held nodes put at 3.
SNAPSHOT_FREE_SLOT = next(slot for slot in range(1, addrs.GEMDOS_DIRECTORY_NODE_COUNT)
                          if BASE_IMAGE[addrs.GEMDOS_CURDIR_REFCOUNTS + slot] == 0)

# A value a case stages into a table slot so that the routine's store over it is visible.
STALE_POINTER = 0xDEAD_BEEF
# A node pointer a case stages for a p_curdir byte to find. Any non-zero longword: the routine tests
# it and never follows it.
SOME_NODE = fs.ROOT_DND_AT


def _pool(words_left):
    """The arena left with exactly `words_left` words, and both size-class chains empty."""
    return {memory.GEMDOS_POOL_FREE_WORDS: struct.pack(">H", words_left),
            memory.GEMDOS_P_ROOT + fs.DMD_POOL_CLASS * memory.POOL_CHAIN_ENTRY_BYTES: bytes(4),
            memory.GEMDOS_P_ROOT + fs.NODE_POOL_CLASS * memory.POOL_CHAIN_ENTRY_BYTES: bytes(4)}


def _run(entry, glue, pokes, *, poison):
    """`gemdos_fs.run`, as the run's report and the machine it left."""
    result = fs.run(entry, glue, pokes, poison=poison)
    return result.info, result.final


def _stores(info):
    """The addresses the ORACLE stored to outside its own stack band — the compared machine."""
    return {at for at in info["writes"] if in_diff(at)}


def _records_of(final, drive):
    """`(dmd, root_dnd, root_ofd, fat_ofd)` as the run left them hung off the drive's table slot."""
    dmd = case.long_in(final, fs.dmd_slot(drive))
    root = case.long_in(final, dmd + fs.DMD_ROOT_DND)
    return dmd, root, case.long_in(final, root + fs.DND_OFD), case.long_in(final, dmd + fs.DMD_FAT_OFD)


def _record_bytes(final, dmd, root, root_ofd, fat_ofd):
    return {dmd: bytes(final[dmd:dmd + fs.DMD_BYTES]), root: bytes(final[root:root + fs.DND_BYTES]),
            root_ofd: bytes(final[root_ofd:root_ofd + fs.OFD_BYTES]),
            fat_ofd: bytes(final[fat_ofd:fat_ofd + fs.OFD_BYTES])}


# ---- dmd_alloc, $fc50fa --------------------------------------------------------------------------

def _alloc_pokes(drive, pokes=None):
    return {**(pokes or {}), **case.word_arg(drive)}


def _alloc(drive, pokes):
    return _run(addrs.GEMDOS_DMD_ALLOC, lambda lib, buf: lib.gemdos_dmd_alloc(buf, drive),
                _alloc_pokes(drive, pokes), poison=False)


def test_dmd_alloc_hangs_the_four_records_off_each_other():
    """The DMD in the drive's slot, the root DND at DMD+0x24, the root directory's OFD at DND+0x14
    and the FAT's OFD at DMD+0x1c — four records from the pool, the answer the DMD."""
    info, final = _alloc(NOT_LOGGED_IN, {fs.dmd_slot(NOT_LOGGED_IN): struct.pack(">I", STALE_POINTER)})
    dmd, root, root_ofd, fat_ofd = _records_of(final, NOT_LOGGED_IN)
    assert info["ret"] == dmd != 0
    assert len({dmd, root, root_ofd, fat_ofd}) == DRIVE_RECORD_COUNT and 0 not in (root, root_ofd, fat_ofd)


@pytest.mark.parametrize("failing", range(DRIVE_RECORD_COUNT))
def test_dmd_alloc_gives_back_what_it_got_when_the_pool_runs_out(failing):
    """Request `failing` (0 = the DMD) is the one the arena cannot serve: the answer is 0, the
    records already cut go back onto their chains newest first, and the one that failed leaves its
    0 in the parent it was stored into BEFORE the test — including the DRIVE'S TABLE SLOT, which
    after a later failure keeps naming the DMD that has just been freed."""
    words_left = sum(REQUEST_WORDS[:failing]) + REQUEST_WORDS[failing] - 1
    info, final = _alloc(NOT_LOGGED_IN, {**_pool(words_left),
                                         fs.dmd_slot(NOT_LOGGED_IN): struct.pack(">I", STALE_POINTER)})
    assert info["ret"] == 0
    slot = case.written_long(info, fs.dmd_slot(NOT_LOGGED_IN))
    if failing == 0:
        assert slot == 0, "the failed DMD request's 0 is stored over the table slot"
    else:
        assert slot != 0 and memory.size_class_of(final, slot) == fs.DMD_POOL_CLASS
        dmd_chain = memory.GEMDOS_P_ROOT + fs.DMD_POOL_CLASS * memory.POOL_CHAIN_ENTRY_BYTES
        assert case.long_in(final, dmd_chain) == slot, "...and names a DMD back on the free chain"


def test_dmd_alloc_indexes_the_table_by_a_SIGNED_drive():
    """`movea.w` then two `adda.l`: drive -1 is the longword BELOW the table."""
    info, _final = _alloc(BELOW_THE_TABLE, {})
    assert case.written_long(info, fs.dmd_slot(BELOW_THE_TABLE)) == info["ret"] != 0


# ---- dmd_build, $fc53c0 --------------------------------------------------------------------------

def _bpb(recsiz, clsiz, clsizb, rdlen, fsiz, fatrec, datrec, numcl, bflags):
    return struct.pack(">9H", *(value & 0xFFFF for value in (recsiz, clsiz, clsizb, rdlen, fsiz,
                                                             fatrec, datrec, numcl, bflags)))


# Where a case stages a BPB other than the RAM disk's own: its own band in the record gap.
OTHER_BPB_AT = fs.SPAN.claim(fs_records.BPB_BAND_AT, fs.BPB_BYTES, "test/test_gemdos_fs_drive.py, a BPB")

GEOMETRIES = {
    "the staged ram disk": None,
    # A double-sided 720 KB floppy: an ODD root-directory length, so its cluster count rounds up.
    "a 720K floppy": _bpb(512, 2, 1024, 7, 5, 6, 18, 711, 0),
    # A hard-disk partition: FAT16, and every other BFLAGS bit set, which `and.w #1` drops.
    "a FAT16 partition": _bpb(512, 4, 2048, 16, 41, 42, 99, 10000, 0x8003),
    "one sector per cluster": _bpb(1024, 1, 1024, 3, 2, 3, 6, 100, 0),
    # Not powers of two: log2 is the top set bit and the mask follows it.
    "a 1000-byte sector": _bpb(1000, 3, 3000, 5, 4, 5, 10, 50, 0),
    # recsiz 0: log2 answers -1 and the mask is read from the word BELOW the table.
    "a zero sector size": _bpb(0, 2, 0, 2, 2, 3, 5, 10, 0),
    # rdlen -1: `muls.w` makes the root's length NEGATIVE, where an unsigned multiply would not.
    "a negative root length": _bpb(512, 2, 1024, 0xFFFF, 2, 3, 5, 10, 0),
    # rdlen -16: `divs.w` TRUNCATES (-15 / 2 = -7, not -8), so the root starts at cluster +6.
    "a negative quotient": _bpb(512, 2, 1024, 0xFFF0, 2, 3, 5, 10, 0),
}


def _build_pokes(bpb_at, drive, pokes=None):
    return {**(pokes or {}), **case.args(">IH", bpb_at, drive & fs.D0_LOW_WORD)}


def _build(bpb_bytes, drive=NOT_LOGGED_IN, pokes=None, bpb_at=None):
    """The builder over `bpb_bytes` staged at `bpb_at` (this file's own band by default), or over the
    RAM disk's own BPB when `bpb_bytes` is None."""
    if bpb_at is None:
        bpb_at = fs.BPB_AT if bpb_bytes is None else OTHER_BPB_AT
    staged = {**({} if bpb_bytes is None else {bpb_at: bpb_bytes}), **(pokes or {})}
    return _run(addrs.GEMDOS_DMD_BUILD, lambda lib, buf: lib.gemdos_dmd_build(buf, bpb_at, drive),
                _build_pokes(bpb_at, drive, staged), poison=False)


@pytest.mark.parametrize("geometry", GEOMETRIES)
def test_dmd_build_turns_a_bpb_into_the_drive(geometry):
    """Every field `$fc53c0` stores, over eight geometries — the differential is the claim; what is
    asserted here is only that the build SUCCEEDED and set the drive number, so a geometry whose case
    silently took the ENSMEM arm cannot pass for one that exercised the arithmetic."""
    info, final = _build(GEOMETRIES[geometry])
    dmd, *_ = _records_of(final, NOT_LOGGED_IN)
    assert info["ret"] == 0
    assert case.word_in(final, dmd + fs.DMD_DRVNUM) == NOT_LOGGED_IN


def test_dmd_build_answers_ENSMEM_when_the_pool_cannot_serve_it():
    """`moveq #-39`, with nothing of the DMD built — the allocator has already given back what it
    got."""
    info, _final = _build(None, pokes=_pool(DRIVE_REQUEST_WORDS - 1))
    assert info["ret"] == process.GEMDOS_ENSMEM


# Where the pool cuts its NEXT record out of the snapshot's arena — the DMD, `$fc50fa`'s first request.
NEXT_RECORD_AT = memory.arena_cursor() + memory.POOL_CLASS_HEADER_BYTES
# A floppy-shaped BPB whose `fatrec` is NOT the `m_clsiz` it will lie under, so the order is visible.
UNDER_THE_DMD = dict(recsiz=512, clsiz=2, clsizb=1024, rdlen=2, fsiz=2, fatrec=3, datrec=7, numcl=32,
                     bflags=0)


def test_a_bpb_lying_under_the_dmd_is_read_in_the_roms_order():
    """THE BPB IS READ WHERE THE ROM READS IT, not all at entry. `$fc53c0` takes `recsiz`, `clsiz`,
    `rdlen` and `fsiz` into its frame first, and every other field only where it uses it — `fatrec`
    twice, at $fc5568 and $fc5584, after the stores above them. A BPB staged exactly where the pool is
    about to cut the DMD makes that order an answer: the pool clears the record, the builder writes
    `m_clsiz` at DMD+10, and DMD+10 is BPB+10, so the FAT's record bias is built from `clsiz` rather
    than from the `fatrec` that was staged there."""
    info, final = _build(_bpb(**UNDER_THE_DMD), bpb_at=NEXT_RECORD_AT)
    dmd, *_ = _records_of(final, NOT_LOGGED_IN)
    clsiz = UNDER_THE_DMD["clsiz"]
    fat_start = ctypes.c_int16(case.word_in(final, case.long_in(final, dmd + fs.DMD_FAT_OFD)
                                            + fs.OFD_STRTCL)).value
    assert info["ret"] == 0 and dmd == NEXT_RECORD_AT
    assert case.word_in(final, dmd + fs.DMD_RECOFF) == (clsiz - fat_start * clsiz) & fs.D0_LOW_WORD


def test_the_staged_drive_is_exactly_what_the_rom_builds():
    """THE CLAIM `gemdos_fs.drive()` RESTS ON. The ROM's builder over the staged BPB, and the four
    records it cut from the pool compared byte for byte with `drive_records` at those addresses — so
    every other battery's staged DMD, root node and pseudo-files are the ROM's own, not a transcription
    of its expressions."""
    drive = NOT_LOGGED_IN
    _info, final = _build(None, drive)
    records = _records_of(final, drive)
    assert _record_bytes(final, *records) == fs.drive_records(drive, *records)


# ---- open_drive, $fc67de -------------------------------------------------------------------------

def _open(drive, pokes=None, poison=False):
    return _run(addrs.GEMDOS_OPEN_DRIVE, lambda lib, buf: lib.gemdos_open_drive(buf, drive),
                _alloc_pokes(drive, pokes), poison=poison)


def _getbpb_calls():
    return [call for call in fs.DISK_CALLS if call[0] == addrs.BIOS_GETBPB_FN]


def test_a_logged_in_drive_with_a_live_directory_asks_nobody():
    """A: is in the mask and p_curdir[0] names a live node: the drive back, no BIOS call, nothing
    stored — which is why this case can poison."""
    info, _final = _open(LOGGED_IN, poison=True)
    assert info["ret"] == LOGGED_IN
    assert not fs.DISK_CALLS
    assert not _stores(info), "a drive with nothing to do stored something"


def test_logging_a_drive_in_builds_it_and_gives_the_process_the_first_free_slot():
    """B: is not in the mask: one `Getbpb(1)`, the builder, the mask's bit 1 — and then, p_curdir[1]
    being 0, the first node slot with a zero count, given B:'s root node and a count of 1."""
    info, final = _open(NOT_LOGGED_IN)
    gemdos.bios_call_site(info)
    assert info["ret"] == NOT_LOGGED_IN
    assert _getbpb_calls() == [(addrs.BIOS_GETBPB_FN, 0, 0, 0, 0, NOT_LOGGED_IN)]
    assert case.word_in(final, addrs.GEMDOS_DRIVES_OPENED) == SNAPSHOT_MASK | 1 << NOT_LOGGED_IN
    dmd, root, *_ = _records_of(final, NOT_LOGGED_IN)
    assert final[fs.curdir_at(NOT_LOGGED_IN)] == SNAPSHOT_FREE_SLOT
    assert final[addrs.GEMDOS_CURDIR_REFCOUNTS + SNAPSHOT_FREE_SLOT] == 1
    assert case.long_in(final, fs.node_slot(SNAPSHOT_FREE_SLOT)) == root


def test_the_top_drive_s_bit_is_the_mask_s_sign_bit():
    """Drive 15: `1 << 15` in a WORD, OR-ed into the mask."""
    _info, final = _open(TOP_DRIVE)
    assert case.word_in(final, addrs.GEMDOS_DRIVES_OPENED) == SNAPSHOT_MASK | 0x8000


def test_a_negative_drive_indexes_below_every_table():
    """Drive -16 — what `$fc68dc` makes of a path starting `1:` — under a driver that answers every
    drive with a BPB. `asl.w` by -16 is a shift of 48 (no bit, so the BIOS is asked), the DMD lands
    sixteen longwords BELOW the table, the directory byte four below `p_curdir` (inside `p_uft`), and
    the drive comes back SIGN-EXTENDED: every index here is a signed word."""
    drive = DIGIT_DRIVE
    info, final = _open(drive)
    assert info["ret"] == drive & 0xFFFF_FFFF
    assert _getbpb_calls() == [(addrs.BIOS_GETBPB_FN, 0, 0, 0, 0, drive & 0xFFFF)]
    assert case.long_in(final, fs.dmd_slot(drive)) != 0
    assert final[fs.curdir_at(drive)] == SNAPSHOT_FREE_SLOT


def test_a_drive_with_no_bpb_is_ERROR_and_nothing_else():
    """`Getbpb` answering 0 is `moveq #-1` straight away: no DMD, no bit, no slot."""
    info, final = _open(NOT_LOGGED_IN, fs.getbpb_answer(0))
    assert info["ret"] == fs.GEMDOS_ERROR
    assert case.word_in(final, addrs.GEMDOS_DRIVES_OPENED) == SNAPSHOT_MASK
    assert fs.dmd_slot(NOT_LOGGED_IN) not in info["writes"]


def test_drive_16_has_no_bit_so_it_is_asked_for_every_time():
    """`asl.w` by 16 shifts the 1 out of the word: whatever the mask holds, drive 16 is "not logged
    in" and goes to the BIOS (whose answer here is 0, so the case stops there)."""
    info, _final = _open(NO_BIT_DRIVE, {addrs.GEMDOS_DRIVES_OPENED: struct.pack(">H", 0xFFFF),
                                         **fs.getbpb_answer(0)})
    assert info["ret"] == fs.GEMDOS_ERROR
    assert _getbpb_calls() == [(addrs.BIOS_GETBPB_FN, 0, 0, 0, 0, NO_BIT_DRIVE)]


def test_a_build_that_runs_out_of_pool_is_ENSMEM_and_the_bit_stays_clear():
    info, final = _open(NOT_LOGGED_IN, _pool(DRIVE_REQUEST_WORDS - 1))
    assert info["ret"] == process.GEMDOS_ENSMEM
    assert case.word_in(final, addrs.GEMDOS_DRIVES_OPENED) == SNAPSHOT_MASK
    assert not any(addrs.GEMDOS_CURDIR_REFCOUNTS <= at < addrs.GEMDOS_CURDIR_REFCOUNTS
                   + addrs.GEMDOS_DIRECTORY_NODE_COUNT for at in info["writes"])


@pytest.mark.parametrize("curdir,node_pointer,why", (
    (0, None, "no directory at all: p_curdir[0] = 0"),
    (5, 0, "a directory byte whose node table entry is 0"),
))
def test_a_logged_in_drive_without_a_live_directory_gets_a_new_slot(curdir, node_pointer, why):
    """The drive is not asked about again; only the directory is replaced — and the OLD byte's count
    is not dropped."""
    pokes = {fs.curdir_at(LOGGED_IN): bytes([curdir])}
    if node_pointer is not None:
        pokes[fs.node_slot(curdir)] = struct.pack(">I", node_pointer)
    info, final = _open(LOGGED_IN, pokes, poison=True)
    assert info["ret"] == LOGGED_IN, why
    assert not fs.DISK_CALLS
    assert final[fs.curdir_at(LOGGED_IN)] == SNAPSHOT_FREE_SLOT


def test_the_directory_byte_is_SIGNED():
    """`ext.w`: a p_curdir byte of $ff is node -1, the longword below the table. Staged non-zero
    there and ZERO at node 255, so an unsigned index would find no node and hand out a slot."""
    pokes = {fs.curdir_at(LOGGED_IN): bytes([TOP_NODE]),
             fs.node_slot(BELOW_THE_TABLE): struct.pack(">I", SOME_NODE),
             fs.node_slot(TOP_NODE): bytes(4)}
    info, _final = _open(LOGGED_IN, pokes, poison=True)
    assert info["ret"] == LOGGED_IN
    assert not _stores(info), "node -1 is live, so nothing is replaced"


def _held(slots):
    """Reference counts: every slot in `slots` held once, every other slot 1..39 free."""
    return {addrs.GEMDOS_CURDIR_REFCOUNTS + slot: bytes([1 if slot in slots else 0])
            for slot in range(1, addrs.GEMDOS_DIRECTORY_NODE_COUNT)}


@pytest.mark.parametrize("free_slot", (1, 17, addrs.GEMDOS_DIRECTORY_NODE_COUNT - 1))
def test_the_slot_search_takes_the_first_zero_count_from_1(free_slot):
    """Slot 0 is never searched (a p_curdir byte of 0 means "none"), and the last slot, 39, is
    reachable — which a bound of `<= 38` fails."""
    held = set(range(1, free_slot))
    info, final = _open(LOGGED_IN, {fs.curdir_at(LOGGED_IN): b"\0", **_held(held)}, poison=True)
    assert info["ret"] == LOGGED_IN
    assert final[fs.curdir_at(LOGGED_IN)] == free_slot


def test_slot_0_is_never_handed_out_even_with_a_zero_count():
    """The snapshot's slot 0 carries a count, so the search starting at 1 is only a claim once slot 0
    is staged FREE: the ROM still skips it."""
    info, final = _open(LOGGED_IN, {fs.curdir_at(LOGGED_IN): b"\0",
                                    addrs.GEMDOS_CURDIR_REFCOUNTS: b"\0", **_held(set())}, poison=True)
    assert info["ret"] == LOGGED_IN
    assert final[fs.curdir_at(LOGGED_IN)] == 1


def test_forty_held_slots_are_ERROR_with_nothing_stored():
    info, _final = _open(LOGGED_IN, {fs.curdir_at(LOGGED_IN): b"\0",
                                     **_held(set(range(1, addrs.GEMDOS_DIRECTORY_NODE_COUNT)))},
                         poison=True)
    assert info["ret"] == fs.GEMDOS_ERROR
    assert not _stores(info)


# ---- the registry --------------------------------------------------------------------------------
# One row per routine, in the shape `test_boot_snapshot.VERIFIED_CASES` takes.

gemdos.register("dmd_alloc, all four records", addrs.GEMDOS_DMD_ALLOC, {"a5": 0},
                fs.machine(_alloc_pokes(NOT_LOGGED_IN)))
gemdos.register("dmd_build, the staged BPB", addrs.GEMDOS_DMD_BUILD, {"a5": 0},
                fs.machine(_build_pokes(fs.BPB_AT, NOT_LOGGED_IN)))
gemdos.register("open_drive, logging drive B in", addrs.GEMDOS_OPEN_DRIVE, {"a5": 0},
                fs.machine(_alloc_pokes(NOT_LOGGED_IN)))
gemdos.register("open_drive, a logged-in drive", addrs.GEMDOS_OPEN_DRIVE, {"a5": 0},
                fs.machine(_alloc_pokes(LOGGED_IN)))

# The table entries these cases reach OUTSIDE the tables `gemdos_fs.CASE_FIELDS` declares — each a
# signed index the ROM does not bound — for `test_boot_snapshot.py`'s claim about which bytes a case
# rests on.
CASE_FIELDS = (
    *((fs.dmd_slot(drive), fs.DRIVE_TABLE_ENTRY_BYTES, f"drive {drive}'s DMD slot, below the table")
      for drive in (BELOW_THE_TABLE, DIGIT_DRIVE)),
    (fs.curdir_at(DIGIT_DRIVE), 1, f"drive {DIGIT_DRIVE}'s p_curdir byte, below the basepage's"),
    *((fs.node_slot(node), fs.DRIVE_TABLE_ENTRY_BYTES, f"directory node {node}, outside the table")
      for node in (BELOW_THE_TABLE, TOP_NODE)),
)
