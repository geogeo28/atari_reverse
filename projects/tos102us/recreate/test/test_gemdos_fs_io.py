"""The I/O engine's cursor and transfer — `src/gemdos/fs_io.c`'s advance, seek, next_cluster, xfer,
read and write, over the staged RAM disk.

`test/fs_io.py` stages the disk variants and the open files; `test/gemdos_fs.py` says why a staged
disk is compared image. Each case is one ROM routine entered at its own address, and each asserts,
on top of the byte diff, the claim it is ABOUT: the cursor it left, the `Rwabs` traffic it made, the
bytes the user buffer or the cache ended up holding.

THE FILES. The base disk's `SHORT.TXT` (cluster 3, 100 bytes) and `SPAN.DAT` (4 -> 5 -> 6, 2500
bytes, contiguous), plus two this file adds: `BROKEN` (7 -> 9 -> 10, not contiguous at all) and
`MIXED` (11 -> 12 -> 14: a contiguous pair, then a break). A transfer's `Rwabs` calls are therefore
the chain's shape: one call per contiguous run.
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs, emu

import case
import fs_io as io
import gemdos_fs as fs

for _name in ("gemdos_ofd_seek", "gemdos_next_cluster", "gemdos_ofd_xfer", "gemdos_ofd_read",
              "gemdos_ofd_write"):
    getattr(_lib, _name).restype = ctypes.c_uint32
_lib.gemdos_ofd_advance.restype = None

CLUSTER = fs.CLUSTER_BYTES
SECTOR = fs.SECTOR_BYTES
MINUS_ONE = 0xFFFF_FFFF
EOC = fs.FAT12_END_OF_CHAIN

BROKEN = (7, 9, 10)
MIXED = (11, 12, 14)
BROKEN_SEED, MIXED_SEED = 0x70, 0x90
CHAIN_BYTES = len(BROKEN) * CLUSTER - 72          # ends inside its last cluster's second sector
MIXED_BYTES = len(MIXED) * CLUSTER                # ...and three WHOLE clusters, all in the run loop


def _chain(clusters):
    return {cluster: following for cluster, following in zip(clusters, clusters[1:] + (EOC,))}


def _bodies(clusters, seed):
    body = fs.body(seed, len(clusters) * CLUSTER)
    return {cluster: body[index * CLUSTER:(index + 1) * CLUSTER]
            for index, cluster in enumerate(clusters)}


FILES = io.disk(fat={**_chain(BROKEN), **_chain(MIXED)},
                clusters={**_bodies(BROKEN, BROKEN_SEED), **_bodies(MIXED, MIXED_SEED)})
BROKEN_BODY = fs.body(BROKEN_SEED, CHAIN_BYTES)
MIXED_BODY = fs.body(MIXED_SEED, MIXED_BYTES)


def span_file(**cursor):
    return io.open_file(fs.SPAN_CLUSTER, fs.SPAN_BYTES, **cursor)


def short_file(length=fs.SHORT_BYTES, **cursor):
    return io.open_file(fs.SHORT_CLUSTER, length, **cursor)


class Cursor:
    """An OFD's cursor and length as a run left them."""

    def __init__(self, result, at=io.OFD_AT):
        self.position = result.long(at + fs.OFD_POS)
        self.cluster = result.word(at + fs.OFD_CURCL)
        self.record = result.word(at + fs.OFD_CURREC)
        self.offset = result.word(at + fs.OFD_CLOFF)
        self.length = result.long(at + fs.OFD_FILELN)
        self.flags = result.word(at + fs.OFD_FLAGS)
        self.first = result.word(at + fs.OFD_STRTCL)

    def at(self, position, cluster, offset):
        return (self.position, self.cluster, self.record, self.offset) == (
            position, cluster & fs.D0_LOW_WORD, fs.cluster_record(cluster), offset)


# ---- the fifth tenant: the user buffer -------------------------------------------------------------

def test_the_user_buffer_is_dead_memory_clear_of_the_ram_disk_and_the_stack():
    span = bytes(BASE_IMAGE[fs.USER_AT:fs.USER_AT + fs.USER_BYTES])
    assert span == bytes(len(span)), "the captured machine holds data where the user buffer goes"
    assert fs.RAM_DISK_AT + fs.RAM_DISK_BYTES <= fs.USER_AT
    assert fs.USER_AT + fs.USER_BYTES <= emu.STACK_GUARD_LO


def test_a_disk_variant_with_no_changes_is_the_staged_disk():
    """`fs_io.disk` re-encodes the base FAT; this is what says the re-encoding is exact."""
    assert io.disk()[fs.IMAGE_AT] == fs.DISK


# ---- advance, $fc61d6 -------------------------------------------------------------------------------

def _advance_pokes(count, in_cluster, ofd):
    return {**ofd, **case.args(">IIH", io.OFD_AT, count, in_cluster)}


def _advance(count, in_cluster, ofd):
    """POISONED: the advance touches only the OFD — no BIOS, no pool, no pointer it follows."""
    return io.run(addrs.GEMDOS_OFD_ADVANCE,
                  lambda lib, buf: lib.gemdos_ofd_advance(buf, io.OFD_AT, count, in_cluster),
                  _advance_pokes(count, in_cluster, ofd), width=case.NO_RESULT, poison=True)


@pytest.mark.parametrize("start,count,in_cluster,length,flags,why", (
    (100, 50, 1, fs.SHORT_BYTES, fs.OFD_SCANNED, "past the end: the length follows, DIRTY joins bit 1"),
    (10, 50, 1, fs.SHORT_BYTES, 0, "inside the file: the length and the flags stand"),
    (50, 50, 1, fs.SHORT_BYTES, 0, "EXACTLY to the end: `ble`, not grown, not dirtied"),
    (10, 50, 0, fs.SHORT_BYTES, 0, "no in-cluster offset: a whole-cluster run leaves it at 0"),
))
def test_advance_moves_the_position_and_grows_the_length(start, count, in_cluster, length, flags,
                                                         why):
    result = _advance(count, in_cluster, short_file(length, pos=start, cloff=start, flags=flags))
    cursor = Cursor(result)
    grown = start + count > length
    assert cursor.position == start + count, why
    assert cursor.offset == (start + count if in_cluster else start), why
    assert cursor.length == (start + count if grown else length), why
    assert cursor.flags == (flags | fs.OFD_DIRTY if grown else flags), why


# ---- seek, $fc7d2a ----------------------------------------------------------------------------------

def _seek_pokes(position, ofd, pokes=None):
    return {**ofd, **(pokes or {}), **case.args(">II", io.OFD_AT, position & MINUS_ONE)}


def _seek(position, ofd, pokes=None):
    return io.run(addrs.GEMDOS_OFD_SEEK,
                  lambda lib, buf: lib.gemdos_ofd_seek(buf, io.OFD_AT, position & MINUS_ONE),
                  _seek_pokes(position, ofd, pokes))


@pytest.mark.parametrize("position", (fs.SPAN_BYTES + 1, -1), ids=("past the end", "negative"))
def test_seek_out_of_range_is_erange_and_moves_nothing(position):
    result = _seek(position, span_file(**io.at_cursor(1500, 5, 476)))
    assert result.info["ret"] == fs.GEMDOS_ERANGE
    assert Cursor(result).at(1500, 5, 476)
    assert not fs.DISK_CALLS


@pytest.mark.parametrize("ofd,position,cluster,offset,why", (
    (span_file(**io.at_cursor(1500, 5, 476)), 0, 0, 0,
     "0 is its own arm: cluster 0, the 'before the first cluster' cursor"),
    (span_file(), 1500, 5, 476, "FROM THE START into the middle of the second cluster"),
    (span_file(), CLUSTER, fs.SPAN_CLUSTER, 0,
     "a BOUNDARY is the END of the cluster before it: one step fewer, offset 0"),
    (span_file(), 2 * CLUSTER, 5, 0, "...and the second boundary"),
    (span_file(**io.at_cursor(1100, 5, 76)), 2100, 6, 52,
     "FROM THE CURRENT cluster: the index difference, 2 - 1"),
    (span_file(**io.at_cursor(CLUSTER, 4, 0)), 1500, 5, 476,
     "from a cursor at its cluster's END (offset 0): one step more"),
    (span_file(**io.at_cursor(CLUSTER, 4, CLUSTER)), 2100, 6, 52,
     "...and one whose offset is m_clsizb, which a transfer that filled the cluster leaves"),
    (span_file(**io.at_cursor(2100, 6, 52)), 100, 4, 100,
     "BACKWARDS is from the start: a walk from the current cluster cannot go back"),
    (span_file(**io.at_cursor(1500, 5, 476)), 1500, 5, 476, "to where it already is: no step"),
    (span_file(), fs.SPAN_BYTES, 6, fs.SPAN_BYTES % CLUSTER, "EXACTLY the length: `bge`, allowed"),
))
def test_seek_walks_the_chain_to_the_positions_cluster(ofd, position, cluster, offset, why):
    result = _seek(position, ofd)
    assert result.info["ret"] == position, why
    assert Cursor(result).at(position, cluster, offset), why


def test_a_chain_that_ends_mid_walk_is_minus_one_with_only_the_offset_moved():
    """`SHORT.TXT` staged with a length its one-cluster chain does not have. The walk's `cmp.w #-1`
    answers -1 — but the split has ALREADY stored the new in-cluster offset, and nothing else."""
    result = _seek(3000, short_file(5000))
    cursor = Cursor(result)
    assert result.info["ret"] == MINUS_ONE
    assert (cursor.position, cursor.cluster, cursor.offset) == (0, 0, 3000 % CLUSTER)


def test_the_last_step_of_a_seek_has_no_end_of_chain_test():
    """...and one cluster further in, the -1 comes from the LAST step, which is not tested
    ($fc7df6): the seek succeeds and leaves the cursor in cluster -1 — a pseudo-cluster."""
    result = _seek(1500, short_file(5000))
    assert result.info["ret"] == 1500
    assert Cursor(result).at(1500, -1, 476)


# ---- next_cluster, $fc60f2 ---------------------------------------------------------------------------

def _next_pokes(ofd, allocate=0, pokes=None, at=io.OFD_AT):
    return {**ofd, **(pokes or {}), **case.args(">IH", at, allocate)}


def _next(ofd, allocate=0, pokes=None, at=io.OFD_AT):
    return io.run(addrs.GEMDOS_NEXT_CLUSTER,
                  lambda lib, buf: lib.gemdos_next_cluster(buf, at, allocate),
                  _next_pokes(ofd, allocate, pokes, at))


@pytest.mark.parametrize("ofd,position,cluster,why", (
    (span_file(**io.at_cursor(CLUSTER, 4, 0)), CLUSTER, 5, "a data cluster: its FAT successor"),
    (span_file(), 0, fs.SPAN_CLUSTER, "a fresh cursor: the file's first cluster"),
    (io.open_file(fs.ROOT_START_CLUSTER, 2 * SECTOR, **io.at_cursor(0, fs.ROOT_START_CLUSTER, 0)),
     0, fs.ROOT_START_CLUSTER + 1, "a NEGATIVE pseudo-cluster: arithmetic, cl + 1, nothing read"),
))
def test_next_cluster_steps_the_cursor(ofd, position, cluster, why):
    """The position does not move — only the cluster, its record and the in-cluster offset (0)."""
    result = _next(ofd)
    assert result.info["ret"] == 0, why
    assert Cursor(result).at(position, cluster, 0), why


@pytest.mark.parametrize("ofd,why", (
    (span_file(**io.at_cursor(2 * CLUSTER, 6, 0)), "the chain's last cluster, not allocating"),
    (io.open_file(0, 0), "an EMPTY file's fresh cursor: first cluster 0 reads as the end"),
))
def test_next_cluster_at_the_end_is_minus_one_and_moves_nothing(ofd, why):
    before = ofd[io.OFD_AT]
    result = _next(ofd)
    assert result.info["ret"] == MINUS_ONE, why
    assert result.after(io.OFD_AT, len(before)) == before, why


def test_the_odd_reserved_entry_sends_the_cursor_into_the_pseudo_clusters():
    """The signed shift at the end of the chain walk: an odd cluster whose entry is $ff8 — end of
    chain to DOS — is followed to cluster -8, and the cursor's record is -16."""
    result = _next(io.open_file(9, CLUSTER, **io.at_cursor(0, 9, 0)),
                   pokes=io.disk(fat={9: 0xFF8}))
    assert result.info["ret"] == 0
    assert Cursor(result).at(0, -8, 0)


def test_allocating_links_the_first_free_cluster_after_the_last():
    """SPAN ends at 6; 7 is free. The new cluster is marked end-of-chain and 6 is pointed at it,
    both in the cached FAT (dirty, not yet on the disk)."""
    result = _next(span_file(**io.at_cursor(3 * CLUSTER, 6, 0)), allocate=1)
    table = io.fat_after(result)
    assert result.info["ret"] == 0
    assert Cursor(result).cluster == 7
    assert (fs.fat12_entry(table, 6), fs.fat12_entry(table, 7)) == (7, fs.FAT12_END_OF_CHAIN)


def test_allocating_for_an_empty_file_sets_its_first_cluster_and_dirties_it():
    """No cluster to link FROM: the OFD's own first cluster is set instead, and the entry marked
    dirty so the close writes it back. The search starts at 0, lifted to cluster 2."""
    result = _next(io.open_file(0, 0), allocate=1)
    cursor = Cursor(result)
    assert (cursor.first, cursor.cluster, cursor.flags) == (7, 7, fs.OFD_DIRTY)
    assert fs.fat12_entry(io.fat_after(result), 7) == fs.FAT12_END_OF_CHAIN


def test_the_search_wraps_modulo_m_numcl():
    """From cluster 30 with 31 in use, `(31 + 1) % 32` is 0, lifted to 2 — the first free cluster
    after the wrap is 7."""
    pokes = io.disk(fat={30: EOC, 31: EOC})
    result = _next(io.open_file(30, CLUSTER, **io.at_cursor(CLUSTER, 30, 0)), allocate=1,
                   pokes=pokes)
    assert Cursor(result).cluster == 7


def _all_used(except_for=()):
    return {cluster: EOC for cluster in range(fs.FIRST_DATA_CLUSTER, io.FAT_ENTRIES)
            if cluster not in except_for and cluster not in io.BASE_FAT_USED}


@pytest.mark.parametrize("last,free,why", (
    (6, (), "every cluster in use"),
    (6, (32, 33), "only the last two free: `% m_numcl` never reaches them"),
    (33, (31,), "from cluster 33, m_numcl - 2 probes run out one short of cluster 31"),
))
def test_a_full_disk_is_minus_one_and_writes_no_fat(last, free, why):
    pokes = io.disk(fat=_all_used(except_for=free))
    result = _next(io.open_file(last, CLUSTER, **io.at_cursor(CLUSTER, last, 0)), allocate=1,
                   pokes=pokes)
    assert result.info["ret"] == MINUS_ONE, why
    assert Cursor(result).cluster == last, why
    assert all(result.word(fs.bcb_at(index) + fs.BCB_DIRTY) == 0 for index in result.order(0)), why


# ---- xfer, $fc6218 ------------------------------------------------------------------------------------

def _xfer_pokes(rwflag, ofd, count, buffer=fs.USER_AT, copy=addrs.GEMDOS_COPY_OUT, pokes=None,
                at=io.OFD_AT):
    return {**FILES, **ofd, **(pokes or {}), **case.args(">HIIII", rwflag, at, count, buffer, copy)}


def _xfer(rwflag, ofd, count, buffer=fs.USER_AT, copy=addrs.GEMDOS_COPY_OUT, pokes=None,
          at=io.OFD_AT):
    return io.run(addrs.GEMDOS_OFD_XFER,
                  lambda lib, buf: lib.gemdos_ofd_xfer(buf, rwflag, at, count, buffer, copy),
                  _xfer_pokes(rwflag, ofd, count, buffer, copy, pokes, at))


def _user(result, count):
    return result.after(fs.USER_AT, count)


@pytest.mark.parametrize("ofd,count,body,start,calls,why", (
    (short_file(**io.at_cursor(10, 3, 10)), 20, fs.SHORT_BODY, 10,
     [(fs.RWABS_READ, 1, io.data_record(3))], "a HEAD only: inside one sector, one cache fill"),
    (span_file(**io.at_cursor(500, 4, 500)), 100, fs.SPAN_BODY, 500,
     [(fs.RWABS_READ, 1, io.data_record(4)), (fs.RWABS_READ, 1, io.data_record(4, 1))],
     "head and TAIL across a sector boundary: two cached sectors"),
    (span_file(**io.at_cursor(1000, 4, 1000)), 100, fs.SPAN_BODY, 1000,
     [(fs.RWABS_READ, 1, io.data_record(4, 1)), (fs.RWABS_READ, 1, io.data_record(5))],
     "...across a CLUSTER boundary: the tail steps the cursor first"),
    (span_file(**io.at_cursor(SECTOR, 4, SECTOR)), SECTOR, fs.SPAN_BODY, SECTOR,
     [(fs.RWABS_READ, 1, io.data_record(4, 1))],
     "the rest of the head's cluster as WHOLE sectors, straight through Rwabs"),
    (span_file(**io.at_cursor(100, 4, 100)), 2 * SECTOR - 100, fs.SPAN_BODY, 100,
     [(fs.RWABS_READ, 1, io.data_record(4)), (fs.RWABS_READ, 1, io.data_record(4, 1))],
     "a head, then the sector AFTER it whole: the record moved past the head's"),
    (span_file(), fs.SPAN_BYTES, fs.SPAN_BODY, 0,
     [(fs.RWABS_READ, 4, io.data_record(4)), (fs.RWABS_READ, 1, io.data_record(6))],
     "two CONTIGUOUS clusters in ONE Rwabs, then the tail through the cache"),
    (span_file(), CLUSTER + SECTOR, fs.SPAN_BODY, 0,
     [(fs.RWABS_READ, 2, io.data_record(4)), (fs.RWABS_READ, 1, io.data_record(5))],
     "a whole cluster and a LEFTOVER sector of the next"),
    (io.open_file(BROKEN[0], CHAIN_BYTES), CHAIN_BYTES, BROKEN_BODY, 0,
     [(fs.RWABS_READ, 2, io.data_record(7)), (fs.RWABS_READ, 2, io.data_record(9)),
      (fs.RWABS_READ, 1, io.data_record(10)), (fs.RWABS_READ, 1, io.data_record(10, 1))],
     "a BROKEN chain: one Rwabs per cluster — the last one by the second flush pass"),
    (io.open_file(MIXED[0], MIXED_BYTES), MIXED_BYTES, MIXED_BODY, 0,
     [(fs.RWABS_READ, 4, io.data_record(11)), (fs.RWABS_READ, 2, io.data_record(14))],
     "a contiguous pair, then a break on the LAST cluster: the run, then the second pass"),
), ids=("head", "sector", "cluster", "sectors", "head+sectors", "contiguous", "leftover", "broken",
        "mixed"))
def test_a_read_moves_the_files_bytes_by_the_cheapest_route(ofd, count, body, start, calls, why):
    result = _xfer(fs.RWABS_READ, ofd, count)
    assert result.info["ret"] == count, why
    assert _user(result, count) == body[start:start + count], why
    assert io.data_transfers() == calls, why
    assert Cursor(result).position == start + count, why


def test_a_head_cluster_of_more_than_two_sectors_is_finished_with_the_wrong_count():
    """THE ROM'S OWN BUG, pinned rather than fixed. The rest of the head's cluster is moved as
    `clsiz_mask & record` whole sectors ($fc6330) — the sector's INDEX in its cluster, not the number
    left in it. The two agree for every head of a two-sector cluster (every floppy) and for the middle
    sector of a four-sector one; here, with FOUR, a read of three whole sectors from sector 1 moves
    sector 1, then steps to the NEXT cluster for the other two — sectors 2 and 3 are never read, and
    the bytes in the buffer are the next cluster's."""
    ofd = io.open_file(fs.SPAN_CLUSTER, 4 * io.BIG_CLUSTER_BYTES, pos=SECTOR,
                       curcl=fs.SPAN_CLUSTER, currec=fs.SPAN_CLUSTER * io.BIG_CLUSTER_SECTORS,
                       cloff=SECTOR)
    result = _xfer(fs.RWABS_READ, ofd, 3 * SECTOR, pokes=io.big_cluster_drive())
    assert result.info["ret"] == 3 * SECTOR
    assert io.data_transfers() == [
        (fs.RWABS_READ, 1, io.big_cluster_record(fs.SPAN_CLUSTER, 1)),
        (fs.RWABS_READ, 2, io.big_cluster_record(fs.SPAN_CLUSTER + 1))]


def test_a_read_stops_where_the_chain_does():
    """A length the chain does not have: the second cluster step answers -1, the run already
    gathered is flushed, and the answer is what really moved."""
    result = _xfer(fs.RWABS_READ, short_file(3000), 3000)
    assert result.info["ret"] == CLUSTER
    assert io.data_transfers() == [(fs.RWABS_READ, 2, io.data_record(3))]


@pytest.mark.parametrize("position,why", ((32, "the HEAD's sector"), (0, "the TAIL's sector")))
def test_a_null_buffer_answers_a_pointer_into_the_cache(position, why):
    """How the directory layer reads an entry: nothing is copied, and the answer is the entry's own
    address inside the cached sector. The root directory's OFD, whose clusters are negative."""
    root = io.open_file(fs.ROOT_START_CLUSTER, 2 * SECTOR, at=fs.ROOT_OFD_AT,
                        **(io.at_cursor(position, fs.ROOT_START_CLUSTER, position)
                           if position else {}))
    result = _xfer(fs.RWABS_READ, root, fs.DIRENT_BYTES, buffer=0, at=fs.ROOT_OFD_AT)
    buffer = fs.buffer_at(result.order(1)[0])
    assert result.info["ret"] == buffer + position, why
    assert result.after(buffer + position, fs.DIRENT_BYTES) == \
        fs.DISK[fs.ROOT_RECORD * SECTOR + position:][:fs.DIRENT_BYTES], why


def test_a_write_copies_in_and_leaves_the_sector_dirty_in_the_cache():
    new = bytes(range(0x40, 0x40 + 50))
    result = _xfer(fs.RWABS_WRITE, span_file(**io.at_cursor(100, 4, 100)), len(new),
                   copy=addrs.GEMDOS_COPY_IN, pokes=fs.user_buffer(new))
    head = result.order(1)[0]
    assert result.info["ret"] == len(new)
    assert result.after(fs.buffer_at(head) + 100, len(new)) == new
    assert result.word(fs.bcb_at(head) + fs.BCB_DIRTY) == 1


# ---- read and write, $fc5e9c / $fc5f1c --------------------------------------------------------------

def _read_pokes(ofd, count):
    return {**FILES, **ofd, **case.args(">III", io.OFD_AT, count & MINUS_ONE, fs.USER_AT)}


def _read(ofd, count):
    return io.run(addrs.GEMDOS_OFD_READ,
                  lambda lib, buf: lib.gemdos_ofd_read(buf, io.OFD_AT, count & MINUS_ONE, fs.USER_AT),
                  _read_pokes(ofd, count))


def _write_pokes(ofd, data, count=None, pokes=None):
    count = len(data) if count is None else count
    return {**FILES, **ofd, **fs.user_buffer(data), **(pokes or {}),
            **case.args(">III", io.OFD_AT, count, fs.USER_AT)}


def _write(ofd, data, count=None, pokes=None):
    count = len(data) if count is None else count
    return io.run(addrs.GEMDOS_OFD_WRITE,
                  lambda lib, buf: lib.gemdos_ofd_write(buf, io.OFD_AT, count, fs.USER_AT),
                  _write_pokes(ofd, data, count, pokes))


def test_a_read_past_the_end_is_clamped_to_it():
    result = _read(short_file(**io.at_cursor(90, 3, 90)), 50)
    assert result.info["ret"] == 10
    assert _user(result, 11) == fs.SHORT_BODY[90:] + bytes([fs.SLACK_FILL])


@pytest.mark.parametrize("ofd,count,why", (
    (short_file(**io.at_cursor(fs.SHORT_BYTES, 3, fs.SHORT_BYTES)), 50, "at the end"),
    (short_file(), -5, "a NEGATIVE count: the signed `ble`"),
    (short_file(), 0, "nothing asked for"),
))
def test_a_read_with_nothing_to_move_is_zero_and_touches_nothing(ofd, count, why):
    result = _read(ofd, count)
    assert result.info["ret"] == 0, why
    assert not fs.DISK_CALLS, why


def test_a_write_past_the_end_grows_the_file_and_dirties_it():
    new = b"appended!"
    result = _write(short_file(**io.at_cursor(fs.SHORT_BYTES, 3, fs.SHORT_BYTES)), new)
    cursor = Cursor(result)
    assert (cursor.length, cursor.flags) == (fs.SHORT_BYTES + len(new), fs.OFD_DIRTY)


def test_a_write_past_the_last_cluster_allocates_one():
    """SHORT's one cluster is full: the tail's step extends the chain (3 -> 7) and the bytes land in
    the new cluster's first sector, in the cache."""
    new = bytes(range(0x20, 0x20 + 100))
    result = _write(short_file(CLUSTER, **io.at_cursor(CLUSTER, 3, CLUSTER)), new,
                    pokes=io.disk())
    cursor = Cursor(result)
    table = io.fat_after(result)
    assert result.info["ret"] == len(new)
    assert (cursor.cluster, cursor.length) == (7, CLUSTER + len(new))
    assert (fs.fat12_entry(table, 3), fs.fat12_entry(table, 7)) == (7, fs.FAT12_END_OF_CHAIN)


def test_a_whole_cluster_write_allocates_and_goes_straight_to_the_disk():
    """Two clusters at the end of an empty file: two allocations (7, then 8 — contiguous), and ONE
    Rwabs write of four sectors, the cache bypassed."""
    new = fs.body(0x33, 2 * CLUSTER)
    result = _write(io.open_file(0, 0), new, pokes=io.disk())
    assert result.info["ret"] == len(new)
    assert [call for call in io.data_transfers() if call[0] == fs.RWABS_WRITE] == [
        (fs.RWABS_WRITE, 4, io.data_record(7))]
    assert result.after(fs.IMAGE_AT + io.data_record(7) * SECTOR, len(new)) == new


def test_a_write_to_a_full_disk_moves_nothing():
    pokes = io.disk(fat={**_all_used(), **_chain(BROKEN), **_chain(MIXED)})
    result = _write(short_file(CLUSTER, **io.at_cursor(CLUSTER, 3, CLUSTER)), b"x" * 100,
                    pokes=pokes)
    assert result.info["ret"] == 0
    assert Cursor(result).length == CLUSTER


def test_a_write_of_nothing_inside_a_sector_still_dirties_it():
    """No clamp and no zero test: the head is `min(0, room)` = 0 bytes, but the sector is fetched
    through the cache with the WRITE's dirty flag — so a flush will write it back unchanged."""
    result = _write(short_file(**io.at_cursor(10, 3, 10)), b"", count=0)
    assert result.info["ret"] == 0
    assert result.word(fs.bcb_at(result.order(1)[0]) + fs.BCB_DIRTY) == 1


# ---- the registry -------------------------------------------------------------------------------------

def _register_all():
    io.register("ofd_advance, past the end", addrs.GEMDOS_OFD_ADVANCE,
                _advance_pokes(50, 1, short_file(pos=100, cloff=100)))
    io.register("ofd_seek, from the current cluster", addrs.GEMDOS_OFD_SEEK,
                _seek_pokes(2100, span_file(**io.at_cursor(1100, 5, 76))))
    io.register("ofd_seek, from the start", addrs.GEMDOS_OFD_SEEK, _seek_pokes(1500, span_file()))
    io.register("next_cluster, a FAT step", addrs.GEMDOS_NEXT_CLUSTER,
                _next_pokes(span_file(**io.at_cursor(CLUSTER, 4, 0))))
    io.register("next_cluster, an allocation", addrs.GEMDOS_NEXT_CLUSTER,
                _next_pokes(span_file(**io.at_cursor(3 * CLUSTER, 6, 0)), allocate=1))
    io.register("ofd_xfer, a head-only read", addrs.GEMDOS_OFD_XFER,
                _xfer_pokes(fs.RWABS_READ, short_file(**io.at_cursor(10, 3, 10)), 20))
    io.register("ofd_xfer, a broken chain", addrs.GEMDOS_OFD_XFER,
                _xfer_pokes(fs.RWABS_READ, io.open_file(BROKEN[0], CHAIN_BYTES), CHAIN_BYTES))
    io.register("ofd_read, clamped at the end", addrs.GEMDOS_OFD_READ,
                _read_pokes(short_file(**io.at_cursor(90, 3, 90)), 50))
    io.register("ofd_write, allocating a cluster", addrs.GEMDOS_OFD_WRITE,
                _write_pokes(short_file(CLUSTER, **io.at_cursor(CLUSTER, 3, CLUSTER)), b"x" * 100,
                             pokes=io.disk()))


_register_all()
