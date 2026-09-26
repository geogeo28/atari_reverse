"""The record layer's MAKING half — `src/gemdos/fs_records.c`: DNDs and OFDs out of the record pool,
a handle for an open, and a directory cluster zeroed through the buffer cache.

The pool is the verified `$fc7f1a` (`src/gemdos/memory.c`), run by both shores; each maker is driven
over its three states — a record cut from the arena (the snapshot's own class-4 chain is empty), a
STALE record off the chain (`fs_records.pool_recycled`, so the pool's clear is a visible store), and
nothing left (`fs_records.pool_spent`), which is each routine's failure arm.

NOTHING HERE POISONS. The attribution pass pre-inverts every byte the oracle wrote and runs again,
and every one of these routines both READS and WRITES the pool's chain head — inverted, it names a
record at $ffffffff. `test/gemdos_memory.py` runs the pool's own cases without it for the same reason;
here the staging stands in: a recycled record is STALE (`fs_records.STALE_FILL`) and every staged
record is filled, so a field the reconstruction did not write reads as the fill.
"""
import ctypes

import pytest

from harness import _lib, addrs

import case
import fs_io as io
import fs_records as rec
import gemdos
import gemdos_fs as fs
import gemdos_process as gp

for _name in ("gemdos_ofd_new", "gemdos_dnd_new", "gemdos_ofd_open", "gemdos_handle_alloc",
              "gemdos_dir_zero_cluster"):
    getattr(_lib, _name).restype = ctypes.c_uint32

# A drive pointer no staged DMD needs to be at: these makers only COPY it.
DRIVE_AT = fs.DMD_AT
RECYCLED_AT = rec.record_slot(8)
POOL_STATES = {"arena": {}, "recycled": rec.pool_recycled(RECYCLED_AT)}
POOL_IDS = tuple(POOL_STATES)
# What each staged record is filled with — a different byte per record, so a field copied from the
# wrong one is a wrong byte, and one copied from the right one at the wrong offset is too.
DIRECTORY_FILL, PARENT_FILL, PARENT_OFD_FILL, OPEN_OFD_FILL = 0x33, 0x44, 0x55, 0x66


def _run(entry, pokes, glue):
    """Unpoisoned, for `gemdos_fs.run`'s reason: every one of these reads and writes the pool's
    chain head."""
    info = case.run(entry, {"_pokes": pokes}, glue, poison=False)
    return info, case.final_image(info, pokes)


# ---- ofd_new, $fc5c3c ----------------------------------------------------------------------------

DND_AT = rec.record_slot(0)
PARENT_AT = rec.record_slot(1)
PARENT_OFD_AT = rec.record_slot(2)
DIRECTORY_CLUSTER = 7
# As a DND holds them: still in the entry's little-endian order.
DIRECTORY_TIME = fs.byte_swapped(fs.STAGED_DIRENT_TIME, "H")
DIRECTORY_DATE = fs.byte_swapped(fs.STAGED_DIRENT_DATE, "H")
DIRECTORY_POS = 3 * fs.DIRENT_BYTES


def _directory_dnd():
    return fs.stage_dnd(DND_AT, fill=DIRECTORY_FILL, name=fs.fcb_name("SUB"), strtcl=DIRECTORY_CLUSTER,
                        time=DIRECTORY_TIME, date=DIRECTORY_DATE, parent=PARENT_AT,
                        parent_ofd=PARENT_OFD_AT, dirpos=DIRECTORY_POS, dmd=DRIVE_AT)


def _ofd_new_pokes(pokes):
    return {**pokes, **case.long_args(DND_AT)}


def _ofd_new(pokes):
    return _run(addrs.GEMDOS_OFD_NEW, _ofd_new_pokes(pokes), lambda lib, buf: lib.gemdos_ofd_new(buf, DND_AT))


@pytest.mark.parametrize("pool", POOL_IDS)
def test_ofd_new_builds_a_directory_ofd_from_its_dnd(pool):
    """Every field from the DND but the length, which is the largest positive long; the directory
    HOLDING the entry is the DND's PARENT. The rest of the record is the pool's zeros — the DND is
    staged over a fill of $33 so a field copied from the wrong offset is a wrong byte."""
    info, final = _ofd_new({**_directory_dnd(), **POOL_STATES[pool]})
    ofd = info["regs"]["d0"]
    if pool == "recycled":
        assert ofd == RECYCLED_AT
    expected = fs.ofd_bytes(strtcl=DIRECTORY_CLUSTER, fileln=fs.DIRECTORY_LENGTH, dir_ofd=PARENT_OFD_AT,
                             dir_dnd=PARENT_AT, dirpos=DIRECTORY_POS, date=DIRECTORY_DATE,
                             time=DIRECTORY_TIME, dmd=DRIVE_AT)
    assert bytes(final[ofd:ofd + fs.OFD_BYTES]) == expected


def test_ofd_new_answers_zero_when_the_pool_is_spent():
    info, _final_image = _ofd_new({**_directory_dnd(), **rec.pool_spent()})
    assert info["regs"]["d0"] == 0


# ---- dnd_new, $fc65a2 ----------------------------------------------------------------------------

ENTRY_AT = rec.dirent_slot(0)
OLDER_CHILD_AT = rec.record_slot(3)
# A first cluster whose two bytes differ, so a cluster that was not turned round is a wrong word.
TWO_BYTE_CLUSTER = 0x0102
# The ten DOS-reserved bytes, staged non-zero, so a copy reaching into them is a wrong byte.
RESERVED_FILL = 0x77
SUBDIR_ENTRY = fs.dirent_bytes("SUBDIR", "", attr=fs.GEMDOS_ATTR_SUBDIR, cluster=TWO_BYTE_CLUSTER,
                               time=fs.STAGED_DIRENT_TIME, date=fs.STAGED_DIRENT_DATE,
                               reserved=RESERVED_FILL)
PARENT_READ_POS = 5 * fs.DIRENT_BYTES   # the parent directory's OFD, one entry past the one just read


def _parent(child=0):
    return {**fs.stage_dnd(PARENT_AT, fill=PARENT_FILL, child=child, ofd=PARENT_OFD_AT, dmd=DRIVE_AT),
            **fs.stage_ofd(PARENT_OFD_AT, fill=PARENT_OFD_FILL, pos=PARENT_READ_POS)}


def _dnd_new_pokes(pokes):
    return {**pokes, ENTRY_AT: SUBDIR_ENTRY, **case.long_args(PARENT_AT, ENTRY_AT)}


def _dnd_new(pokes):
    return _run(addrs.GEMDOS_DND_NEW, _dnd_new_pokes(pokes),
                lambda lib, buf: lib.gemdos_dnd_new(buf, PARENT_AT, ENTRY_AT))


@pytest.mark.parametrize("pool", POOL_IDS)
@pytest.mark.parametrize("older", (0, OLDER_CHILD_AT), ids=("first child", "a second child"))
def test_dnd_new_pushes_a_child_on_the_front_of_its_parents_list(pool, older):
    """The child becomes the parent's FIRST child with the old first as its sibling; the cluster is
    turned round from the entry's order and the time and date are NOT; the position is the parent
    OFD's, one entry back."""
    info, final = _dnd_new({**_parent(child=older), **POOL_STATES[pool]})
    child = info["regs"]["d0"]
    expected = fs.dnd_bytes(name=fs.fcb_name("SUBDIR"), strtcl=TWO_BYTE_CLUSTER, sibling=older,
                            parent=PARENT_AT, dmd=DRIVE_AT, parent_ofd=PARENT_OFD_AT,
                            dirpos=PARENT_READ_POS - fs.DIRENT_BYTES,
                            time=fs.byte_swapped(fs.STAGED_DIRENT_TIME, "H"),
                            date=fs.byte_swapped(fs.STAGED_DIRENT_DATE, "H"))
    assert bytes(final[child:child + fs.DND_BYTES]) == expected
    assert fs.dnd_field(final, PARENT_AT, "child") == child


def test_dnd_new_leaves_the_parent_alone_when_the_pool_is_spent():
    info, final = _dnd_new({**_parent(child=OLDER_CHILD_AT), **rec.pool_spent()})
    assert info["regs"]["d0"] == 0
    assert fs.dnd_field(final, PARENT_AT, "child") == OLDER_CHILD_AT


# ---- ofd_open, $fc6fdc ---------------------------------------------------------------------------

DIR_OFD_AT = rec.record_slot(2)
OTHER_OPEN_AT = rec.record_slot(4)
FIRST_OPEN_AT = rec.record_slot(5)
FILE_CLUSTER = 0x0405
FILE_LENGTH = 0x0001_2345
FILE_ENTRY = fs.dirent_bytes("SPAN", "DAT", cluster=FILE_CLUSTER, length=FILE_LENGTH,
                             time=fs.STAGED_DIRENT_TIME, date=fs.STAGED_DIRENT_DATE,
                             reserved=RESERVED_FILL)
DIR_READ_POS = 3 * fs.DIRENT_BYTES
ENTRY_POS = DIR_READ_POS - fs.DIRENT_BYTES
OTHER_ENTRY_POS = 8 * fs.DIRENT_BYTES   # an entry of the same directory that is NOT the one opened
OPEN_MODE = 2
HANDLE = addrs.GEMDOS_FIRST_FILE_HANDLE + 3
LAST_HANDLE = addrs.GEMDOS_FIRST_FILE_HANDLE + gp.GEMDOS_HANDLE_COUNT - 1
# The first open's state, which a second open copies twelve bytes of — and its DMD, whose high word
# is one of those twelve.
FIRST_OPEN_STATE = dict(time=0x1111, date=0x2222, strtcl=0x0033, fileln=0x0004_4444,
                        dmd=0x0007_0100)


def _directory(files=0):
    return {**fs.stage_dnd(DND_AT, fill=PARENT_FILL, ofd=DIR_OFD_AT, dmd=DRIVE_AT, files=files),
            **fs.stage_ofd(DIR_OFD_AT, fill=PARENT_OFD_FILL, pos=DIR_READ_POS)}


def _open_list(*dirposes):
    """OFDs already open in the directory, head first: `(slot, dirpos)`, linked in that order."""
    pokes = {}
    for index, (at, dirpos) in enumerate(dirposes):
        link = dirposes[index + 1][0] if index + 1 < len(dirposes) else 0
        state = FIRST_OPEN_STATE if at == FIRST_OPEN_AT else {}
        pokes.update(fs.stage_ofd(at, fill=OPEN_OFD_FILL, link=link, dirpos=dirpos, **state))
    return pokes


def _ofd_open_pokes(pokes, handle=HANDLE):
    return {**pokes, ENTRY_AT: FILE_ENTRY, **case.args(">IIHH", ENTRY_AT, DND_AT, handle, OPEN_MODE)}


def _ofd_open(pokes, handle=HANDLE):
    return _run(addrs.GEMDOS_OFD_OPEN, _ofd_open_pokes(pokes, handle),
                lambda lib, buf: lib.gemdos_ofd_open(buf, ENTRY_AT, DND_AT, handle, OPEN_MODE))


def _opened(final, info, handle):
    ofd = case.long_in(final, gp.descriptor_at(handle) + gp.HANDLE_VALUE)
    assert info["regs"]["d0"] == handle
    assert fs.dnd_field(final, DND_AT, "files") == ofd, "the new OFD heads the directory's list"
    return ofd


@pytest.mark.parametrize("pool", POOL_IDS)
@pytest.mark.parametrize("others", ((), ((OTHER_OPEN_AT, OTHER_ENTRY_POS),)), ids=("none open", "another open"))
@pytest.mark.parametrize("handle", (addrs.GEMDOS_FIRST_FILE_HANDLE, HANDLE, LAST_HANDLE))
def test_a_first_open_takes_the_entry_and_heads_the_list(pool, others, handle):
    head = others[0][0] if others else 0
    info, final = _ofd_open({**_directory(files=head), **_open_list(*others), **POOL_STATES[pool]},
                            handle)
    ofd = _opened(final, info, handle)
    expected = fs.ofd_bytes(link=head, mode=OPEN_MODE, dmd=DRIVE_AT, dir_dnd=DND_AT, dir_ofd=DIR_OFD_AT,
                            dirpos=ENTRY_POS, strtcl=FILE_CLUSTER, fileln=FILE_LENGTH,
                            time=fs.byte_swapped(fs.STAGED_DIRENT_TIME, "H"),
                            date=fs.byte_swapped(fs.STAGED_DIRENT_DATE, "H"))
    assert bytes(final[ofd:ofd + fs.OFD_BYTES]) == expected


def test_a_second_open_copies_twelve_bytes_of_the_first_and_points_the_first_at_itself():
    """The entry is not re-read: time, date, cluster and length come from the OFD already open on
    it — found on the directory's list by POSITION, past one that is not it — and the twelve bytes
    run two into `OFD_DMD`, so the new OFD's DMD takes the first's HIGH word over its own low one.
    The first then points at the new one through `OFD_NEXT_SAME_FILE`."""
    others = ((OTHER_OPEN_AT, OTHER_ENTRY_POS), (FIRST_OPEN_AT, ENTRY_POS))
    info, final = _ofd_open({**_directory(files=OTHER_OPEN_AT), **_open_list(*others)})
    ofd = _opened(final, info, HANDLE)
    state = FIRST_OPEN_STATE
    expected = fs.ofd_bytes(link=OTHER_OPEN_AT, mode=OPEN_MODE,
                            dmd=fs.callers_high_half(state["dmd"]) | (DRIVE_AT & fs.D0_LOW_WORD),
                            dir_dnd=DND_AT, dir_ofd=DIR_OFD_AT, dirpos=ENTRY_POS, strtcl=state["strtcl"],
                            fileln=state["fileln"], time=state["time"], date=state["date"])
    assert bytes(final[ofd:ofd + fs.OFD_BYTES]) == expected
    assert fs.ofd_field(final, FIRST_OPEN_AT, "next_same_file") == ofd
    assert fs.ofd_field(final, OTHER_OPEN_AT, "next_same_file") == int.from_bytes(bytes([OPEN_OFD_FILL]) * 4, "big")


def test_ofd_open_answers_ensmem_and_stores_nothing_when_the_pool_is_spent():
    pokes = {**_directory(), **_table(0), **rec.pool_spent()}
    info, final = _ofd_open(pokes)
    assert info["regs"]["d0"] == gp.GEMDOS_ENSMEM
    record = gp.descriptor_at(HANDLE)
    assert bytes(final[record:record + addrs.GEMDOS_HANDLE_STRIDE]) == bytes(
        case.make_image(pokes)[record:record + addrs.GEMDOS_HANDLE_STRIDE])
    assert fs.dnd_field(final, DND_AT, "files") == 0


# ---- handle_alloc, $fc6f5c -----------------------------------------------------------------------

AN_OWNER = 0x0000_CB0E
A_STALE_VALUE = 0x1234_5678


def _table(owned):
    """The whole handle table: the first `owned` records owned, the rest free but for a stale value
    in their first longword — which is NOT what makes a record free."""
    pokes = {}
    for index in range(gp.GEMDOS_HANDLE_COUNT):
        pokes.update(gp.descriptor_poke(addrs.GEMDOS_FIRST_FILE_HANDLE + index, A_STALE_VALUE,
                                        AN_OWNER if index < owned else 0, references=0))
    return pokes


def _handle_alloc_pokes(pokes):
    return {**pokes, ENTRY_AT: FILE_ENTRY, **case.args(">IIH", ENTRY_AT, DND_AT, OPEN_MODE)}


def _handle_alloc(pokes):
    return _run(addrs.GEMDOS_HANDLE_ALLOC, _handle_alloc_pokes(pokes),
                lambda lib, buf: lib.gemdos_handle_alloc(buf, ENTRY_AT, DND_AT, OPEN_MODE))


@pytest.mark.parametrize("owned", (0, 3, gp.GEMDOS_HANDLE_COUNT - 1))
def test_handle_alloc_claims_the_first_unowned_record_for_p_run(owned):
    info, final = _handle_alloc({**_table(owned), **_directory()})
    handle = owned + addrs.GEMDOS_FIRST_FILE_HANDLE
    record = gp.descriptor_at(handle)
    assert info["regs"]["d0"] == handle
    assert case.long_in(final, record + gp.HANDLE_OWNER) == case.long_in(final, addrs.GEMDOS_P_RUN)
    assert case.word_in(final, record + gp.HANDLE_REFCOUNT) == 1
    _opened(final, info, handle)


def test_handle_alloc_answers_enhndl_when_every_record_is_owned():
    pokes = {**_table(gp.GEMDOS_HANDLE_COUNT), **_directory()}
    info, final = _handle_alloc(pokes)
    assert info["regs"]["d0"] == gp.GEMDOS_ENHNDL
    table = slice(addrs.GEMDOS_HANDLE_TABLE,
                  addrs.GEMDOS_HANDLE_TABLE + gp.GEMDOS_HANDLE_COUNT * addrs.GEMDOS_HANDLE_STRIDE)
    assert bytes(final[table]) == bytes(case.make_image(pokes)[table])


def test_handle_alloc_passes_ofd_opens_ensmem_through_with_the_record_already_claimed():
    """The claim happens BEFORE the open, and nothing undoes it: a spent pool leaves the record owned
    with a count of 1 and a value the open never wrote."""
    info, final = _handle_alloc({**_table(0), **_directory(), **rec.pool_spent()})
    assert info["regs"]["d0"] == gp.GEMDOS_ENSMEM
    record = gp.descriptor_at(addrs.GEMDOS_FIRST_FILE_HANDLE)
    assert case.word_in(final, record + gp.HANDLE_REFCOUNT) == 1
    assert case.long_in(final, record + gp.HANDLE_VALUE) == A_STALE_VALUE


# ---- dir_zero_cluster, $fc70f6 -------------------------------------------------------------------

GEOMETRY_AT = rec.record_slot(6)        # a second DMD, for the case whose OFD and DND disagree
HALF_SECTOR = fs.SECTOR_BYTES // 2
SUBDIR_RECORD = fs.pseudo_record(fs.SUBDIR_CLUSTER)
# A pattern no zeroing produces, for the sectors whose every byte a case wants to see: a byte the
# routine zeroed that it should not have is then a changed byte, and not a zero over a zero.
SUBDIR_PATTERN_SEED = 0x21
# What a sector already in the cache holds: neither a disk byte nor the fill an EMPTY buffer has.
CACHED_BYTE = 0x3C


def _cluster_directory(record, geometry=fs.DMD_AT):
    return {**fs.stage_dnd(DND_AT, fill=PARENT_FILL, ofd=DIR_OFD_AT, dmd=fs.DMD_AT),
            **fs.stage_ofd(DIR_OFD_AT, fill=PARENT_OFD_FILL, dmd=geometry, currec=record)}


def _zero_cluster_pokes(pokes, chains):
    return {**fs.drive(), **fs.cache(**chains), **pokes, **case.long_args(DND_AT)}


def _zero_cluster(pokes, chains):
    result = fs.run(addrs.GEMDOS_DIR_ZERO_CLUSTER, lambda lib, buf: lib.gemdos_dir_zero_cluster(buf, DND_AT),
                    _zero_cluster_pokes(pokes, chains))
    return result.info, result.final


def _bcb_holding(final, index):
    return (case.word_in(final, fs.bcb_at(index) + fs.BCB_BUFTYP),
            ctypes.c_int16(case.word_in(final, fs.bcb_at(index) + fs.BCB_BUFREC)).value,
            case.word_in(final, fs.bcb_at(index) + fs.BCB_DIRTY))


@pytest.mark.parametrize("record,region", ((SUBDIR_RECORD, fs.BCB_TYPE_DATA),
                                           (fs.ROOT_PSEUDO_RECORD, fs.BCB_TYPE_DIR)),
                         ids=("a data cluster", "a root-directory cluster"))
def test_every_sector_of_the_cluster_is_zeroed_dirty_and_the_first_is_answered(record, region):
    """Two misses into two empty buffers: sector 1 first, then sector 0, which is what is answered
    and what is left at the head of the list. Both are read from the disk before they are zeroed —
    `$fc5a98` fills a miss — and both are marked dirty; neither reaches the disk here."""
    info, final = _zero_cluster(_cluster_directory(record), {"data": [(0, fs.EMPTY), (1, fs.EMPTY)]})
    first = info["regs"]["d0"]
    assert first in (fs.buffer_at(0), fs.buffer_at(1))
    held = {_bcb_holding(final, index) for index in (0, 1)}
    assert held == {(region, record, fs.BCB_MARKED_DIRTY), (region, record + 1, fs.BCB_MARKED_DIRTY)}
    for index in (0, 1):
        assert bytes(final[fs.buffer_at(index):fs.buffer_at(index) + fs.SECTOR_BYTES]) == bytes(
            fs.SECTOR_BYTES)
    assert fs.cache_order(lambda at: case.long_in(final, at), 1)[0] == (first - fs.BUFFERS_AT) // fs.BCB_STRIDE
    assert [call[0] for call in fs.DISK_CALLS] == [addrs.BIOS_RWABS_FN, addrs.BIOS_RWABS_FN]


def test_a_sector_already_cached_is_zeroed_where_it_is():
    """A hit asks `Mediach` and reads nothing; the buffer it answers is zeroed in place."""
    held = fs.holding(record=SUBDIR_RECORD + 1, contents=bytes([CACHED_BYTE]) * fs.SECTOR_BYTES)
    info, final = _zero_cluster(_cluster_directory(SUBDIR_RECORD),
                                {"data": [(0, held), (1, fs.EMPTY)]})
    assert info["regs"]["d0"] == fs.buffer_at(1)
    assert bytes(final[fs.buffer_at(0):fs.buffer_at(0) + fs.SECTOR_BYTES]) == bytes(fs.SECTOR_BYTES)
    assert [call[0] for call in fs.DISK_CALLS] == [addrs.BIOS_MEDIACH_FN, addrs.BIOS_RWABS_FN]


@pytest.mark.parametrize("sectors", (1, fs.SECTORS_PER_CLUSTER))
def test_the_geometry_is_the_ofds_drive_and_the_cache_is_asked_with_the_dnds(sectors):
    """The two DMD pointers are read for different things: sectors-per-cluster and bytes-per-sector
    from the OFD's, the drive handed to the cache from the DND's. A geometry DMD of half a sector's
    bytes zeroes HALF of each sector, `sectors` of them — while every buffer is stamped with the
    DND's drive, the loop's as well as the first sector's.

    The cluster's sectors hold a PATTERN, so the half a zeroing should leave is a half of non-zero
    bytes (a routine sizing it from the DND's drive zeroes them), and the Rwabs traffic is exactly
    `sectors` reads (a routine counting sectors from the DND's drive reads — and later writes — one
    more). The pattern is the staged disk's `SUBDIR` cluster replaced, which nothing here reads as
    a directory."""
    geometry = fs.drive(clsiz=sectors, recsiz=HALF_SECTOR)[fs.DMD_AT]
    pattern = fs.body(SUBDIR_PATTERN_SEED, fs.CLUSTER_BYTES)
    info, final = _zero_cluster({**_cluster_directory(SUBDIR_RECORD, GEOMETRY_AT), GEOMETRY_AT: geometry,
                                 **io.disk(clusters={fs.SUBDIR_CLUSTER: pattern})},
                                {"data": [(index, fs.EMPTY) for index in range(sectors)]})
    first = fs.record_of_cluster(fs.SUBDIR_CLUSTER)
    for index in range(sectors):
        buffer = fs.buffer_at(index)
        record = ctypes.c_int16(case.word_in(final, fs.bcb_at(index) + fs.BCB_BUFREC)).value
        sector = pattern[(fs.record_of(fs.BCB_TYPE_DATA, record) - first) * fs.SECTOR_BYTES:][:fs.SECTOR_BYTES]
        assert bytes(final[buffer:buffer + fs.SECTOR_BYTES]) == bytes(HALF_SECTOR) + sector[HALF_SECTOR:]
        assert case.long_in(final, fs.bcb_at(index) + fs.BCB_DM) == fs.DMD_AT
    assert [(call[0], call[1]) for call in fs.DISK_CALLS] == [(addrs.BIOS_RWABS_FN, fs.RWABS_READ)] * sectors


def test_the_sectors_after_the_first_are_zeroed_in_ascending_order():
    """THE LOOP'S ORDER, which only a cluster of three or more sectors can show: sectors 1, 2 and 3
    are fetched and zeroed in that order, and then sector 0 — so the MRU list ends 0, 3, 2, 1, and
    the Rwabs reads go 1, 2, 3, 0. Four-sector clusters (`test/fs_io.py`'s second geometry) on both
    of the directory's drives."""
    record = fs.SUBDIR_CLUSTER * io.BIG_CLUSTER_SECTORS
    buffers = range(io.BIG_CLUSTER_SECTORS)
    info, final = _zero_cluster({**io.big_cluster_drive(), **_cluster_directory(record)},
                                {"data": [(index, fs.EMPTY) for index in buffers]})
    first = io.big_cluster_record(fs.SUBDIR_CLUSTER)
    reads = [first + sector for sector in (*range(1, io.BIG_CLUSTER_SECTORS), 0)]
    assert [call[4] for call in fs.DISK_CALLS] == reads
    held = [ctypes.c_int16(case.word_in(final, fs.bcb_at(index) + fs.BCB_BUFREC)).value
            for index in fs.cache_order(lambda at: case.long_in(final, at), 1)]
    assert held == [record + sector for sector in (0, *range(io.BIG_CLUSTER_SECTORS - 1, 0, -1))]
    assert info["regs"]["d0"] == fs.buffer_at(fs.cache_order(lambda at: case.long_in(final, at), 1)[0])


# ---- the registry --------------------------------------------------------------------------------

gemdos.register("ofd_new, a directory's OFD off the arena", addrs.GEMDOS_OFD_NEW, {},
                _ofd_new_pokes(_directory_dnd()))
gemdos.register("dnd_new, a second child", addrs.GEMDOS_DND_NEW, {},
                _dnd_new_pokes(_parent(child=OLDER_CHILD_AT)))
gemdos.register("ofd_open, a second open of an entry", addrs.GEMDOS_OFD_OPEN, {},
                _ofd_open_pokes({**_directory(files=OTHER_OPEN_AT),
                                 **_open_list((OTHER_OPEN_AT, OTHER_ENTRY_POS), (FIRST_OPEN_AT, ENTRY_POS))}))
gemdos.register("handle_alloc, three records owned", addrs.GEMDOS_HANDLE_ALLOC, {},
                _handle_alloc_pokes({**_table(3), **_directory()}))
gemdos.register("dir_zero_cluster, a data cluster into two empty buffers", addrs.GEMDOS_DIR_ZERO_CLUSTER,
                {"a5": 0},
                fs.machine(_zero_cluster_pokes(_cluster_directory(SUBDIR_RECORD),
                                               {"data": [(0, fs.EMPTY), (1, fs.EMPTY)]})))
