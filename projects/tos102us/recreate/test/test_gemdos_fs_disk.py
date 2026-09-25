"""The GEMDOS buffer cache over a STAGED RAM DISK — `src/gemdos/fs_disk.c`, three routines.

`test/gemdos_fs.py` is the method and says why it works; this file is what it proves. Two halves:

  * the STAGED SPAN's own claims — the 44 KB this wave takes out of the captured machine's free
    window is dead RAM, and clear of the three tenants `project.toml` declares. A future capture
    whose desktop grew into it reddens HERE rather than inside somebody's `Fread` case;
  * the three routines, driven over that disk: a buffer flushed, a buffer fetched, and a span of
    data records moved straight through.

WHY NOTHING HERE POISONS. `case.run`'s attribution pass pre-inverts every byte the ORACLE wrote and
re-runs both cores — and the oracle writes `savptr` itself, twice per BIOS call, because it takes a
real `trap #13` where the host build calls its door. An inverted `savptr` sends the next save frame
somewhere no case staged. `test/gemdos.py`'s note is the long version; what stands in for the pass
is STAGING — every buffer starts full of `$a5` and every disk sector holds a ramp keyed on its file,
so a byte the reconstruction did not write reads as something no arm of these routines produces.
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs, emu, project

import case
import gemdos
import gemdos_fs as fs
import staging

_lib.gemdos_buffer_get.restype = ctypes.c_uint32
_lib.gemdos_buffer_flush.restype = None
_lib.gemdos_rwabs_data.restype = None

DRIVE = 0
OTHER_DRIVE = 1

# The three regions' records this file works in, spelt once. Each is the FIRST record of its region
# in the DMD's pseudo-cluster space, which `gemdos_fs.record_of` turns into a BIOS record.
FAT_RECORD = fs.FAT_START_CLUSTER * fs.SECTORS_PER_CLUSTER
DIR_RECORD = fs.ROOT_START_CLUSTER * fs.SECTORS_PER_CLUSTER
DATA_RECORD = fs.FIRST_DATA_CLUSTER * fs.SECTORS_PER_CLUSTER

# What a case writes into a buffer to see it reach the disk: a byte no sector of the staged image
# holds, and not the `$a5` an untouched buffer is filled with.
DIRTY_BYTE = 0x3C


class Result:
    """A run, and what the machine held AFTER it.

    `harness.differential` hands back the oracle's WRITE LEDGER rather than its final image, which
    is the sharper thing for a field the routine stores — a `KeyError` names a field nothing wrote
    — but the disk, the buffers and the list links are mostly bytes a case POKED and the routine
    left alone. So `after()` is a slice of `case.final_image`: the captured snapshot, the case's
    pokes, and then the oracle's writes, composed once per run rather than per read.
    """

    def __init__(self, info, pokes):
        self.info = info
        self._final = case.final_image(info, pokes)

    def after(self, at, length):
        return bytes(self._final[at:at + length])

    def long(self, at):
        return int.from_bytes(self.after(at, 4), "big")

    def word(self, at):
        return int.from_bytes(self.after(at, 2), "big")

    def sector(self, record):
        """...and one sector of the staged disk."""
        return self.after(fs.IMAGE_AT + record * fs.SECTOR_BYTES, fs.SECTOR_BYTES)

    def order(self, which):
        return fs.cache_order(self.long, which)


def _run(entry, glue, pokes, **kwargs):
    """One case over the staged disk: stage the driver, run, and refuse a transfer off the disk.

    `poison=False` for the module docstring's reason.
    """
    staged = fs.machine(pokes)
    with fs.staged_disk():
        info = case.run(entry, {"a5": 0, "_pokes": staged}, fs.recording(glue), poison=False, **kwargs)
    return Result(info, staged)


def _dirty_sector(byte=DIRTY_BYTE):
    return bytes([byte]) * fs.SECTOR_BYTES


# ---- the span this wave takes --------------------------------------------------------------------

def test_the_ram_disk_span_is_dead_memory_in_this_snapshot():
    """Every byte of it, which is what makes staging a disk there staging rather than scribbling on
    the desktop's data. `test_boot_snapshot.py` makes the same claim about the declared band."""
    span = bytes(BASE_IMAGE[fs.RAM_DISK_AT:fs.RAM_DISK_AT + fs.RAM_DISK_BYTES])
    assert span == bytes(len(span)), (
        f"the captured machine holds data in [{fs.RAM_DISK_AT:#x}, "
        f"{fs.RAM_DISK_AT + fs.RAM_DISK_BYTES:#x}) — the RAM disk would be staged over it")


def test_the_ram_disk_span_is_clear_of_the_three_declared_tenants():
    """`project.toml` declares three tenants of the free window and `RomBench._vet_tenancy` refuses
    an overlap between THEM; this span is a fourth one it does not know about, so the arithmetic is
    here. Growing `staging_bytes` instead is the orchestrator's call (`test/gemdos_fs.py`).

    WHAT THIS DOES NOT CHECK is Tier 3's blob against its own EXTENT — `bench_base` is an address
    and its length is whatever the cross-compiled cores come to, which only `RomBench._vet_tenancy`
    knows. All that is asserted here is that the blob starts below the case band and this span
    starts above it, so a blob that grew past `staging_base` would be caught by that vet and not by
    this test.
    """
    config = project.current()
    top = fs.RAM_DISK_AT + fs.RAM_DISK_BYTES

    assert staging.SCRATCH + staging.SCRATCH_BYTES <= fs.RAM_DISK_AT, "it overlaps the case band"
    assert config.bench_base < staging.SCRATCH, "Tier 3's blob is expected below the case band"
    assert top <= emu.STACK_GUARD_LO, "it reaches into the run's own stack guard"
    assert fs.IMAGE_AT + fs.DISK_BYTES <= top, "the disk image itself runs past the span"


def test_every_region_of_the_staged_disk_maps_onto_sectors_of_that_region():
    """The geometry's own invariant, and the reason both FAT and root directory are two sectors: a
    pseudo-record inside a region's cluster span must land on a real sector OF that region, or a
    case spelling a record by hand would be reading the region above it."""
    fat_sectors = range(fs.FAT2_RECORD, fs.FAT2_RECORD + fs.FAT_SECTORS)
    dir_sectors = range(fs.ROOT_RECORD, fs.ROOT_RECORD + fs.ROOT_SECTORS)
    for step in range(fs.FAT_SECTORS):
        assert fs.record_of(fs.BCB_TYPE_FAT, FAT_RECORD + step) in fat_sectors
    for step in range(fs.ROOT_SECTORS):
        assert fs.record_of(fs.BCB_TYPE_DIR, DIR_RECORD + step) in dir_sectors
    assert fs.record_of(fs.BCB_TYPE_DATA, DATA_RECORD) == fs.record_of_cluster(fs.SUBDIR_CLUSTER)


def test_the_first_fat_copy_is_where_the_flush_writes_it():
    """`$fc59b2` writes the second copy's record MINUS `m_fsiz`, which is the ROM's whole account of
    keeping two FATs in step. The staged disk has to make that arithmetic land on FAT #1."""
    assert fs.record_of(fs.BCB_TYPE_FAT, FAT_RECORD) - fs.FAT_SECTORS == fs.FAT1_RECORD


def test_the_two_fat_copies_start_out_identical():
    """...so that a flush writing only one of them is a visible difference rather than two sectors
    that happened to agree."""
    for step in range(fs.FAT_SECTORS):
        assert fs.sector_of(fs.DISK, fs.FAT1_RECORD + step) == \
               fs.sector_of(fs.DISK, fs.FAT2_RECORD + step)


# ---- buffer_flush, $fc590a -----------------------------------------------------------------------

def _flush(index, holding):
    """`gemdos_buffer_flush` takes the BCB by pointer and consults no list, so which chain the case
    stages it on makes no difference — the region comes from `b_buftyp`."""
    pokes = {**fs.drive(DRIVE), **fs.cache(data=[(index, holding)]),
             **case.long_args(fs.bcb_at(index))}
    return _run(addrs.GEMDOS_BUFFER_FLUSH,
                lambda lib, buf: lib.gemdos_buffer_flush(buf, fs.bcb_at(index)),
                pokes, width=case.NO_RESULT)


def test_a_clean_buffer_is_invalidated_and_never_reaches_the_disk():
    """The early-out at $fc5924 stores `-1` over `b_bufdrv` either way — so "nothing to write" is
    still a store, and the buffer comes back EMPTY rather than unchanged."""
    result = _flush(0, fs.holding(DRIVE, record=DATA_RECORD, dirty=0))
    assert case.written(result.info, fs.bcb_at(0) + fs.BCB_BUFDRV, 2) == fs.BCB_EMPTY
    assert not fs.DISK_CALLS, "a clean buffer asked the BIOS for something"


def test_an_already_empty_buffer_is_stored_empty_again():
    """`b_bufdrv == -1` takes the same arm, and the ROM writes the `-1` back over itself."""
    result = _flush(0, fs.EMPTY)
    assert case.written(result.info, fs.bcb_at(0) + fs.BCB_BUFDRV, 2) == fs.BCB_EMPTY
    assert not fs.DISK_CALLS


def test_a_dirty_data_buffer_is_written_to_its_own_record_and_comes_back_clean():
    """One `Rwabs` write at `m_recoff[2] + b_bufrec`, and then the drive restored and the dirty flag
    cleared — in that order, which is what leaves a buffer EMPTY if the write had failed."""
    contents = _dirty_sector()
    result = _flush(0, fs.holding(DRIVE, record=DATA_RECORD, dirty=1, contents=contents))
    record = fs.record_of(fs.BCB_TYPE_DATA, DATA_RECORD)

    assert fs.DISK_CALLS == [(addrs.BIOS_RWABS_FN, fs.RWABS_WRITE, fs.buffer_at(0), 1, record,
                              DRIVE)]
    assert result.sector(record) == contents
    assert case.written(result.info, fs.bcb_at(0) + fs.BCB_BUFDRV, 2) == DRIVE
    assert case.written(result.info, fs.bcb_at(0) + fs.BCB_DIRTY, 2) == 0
    assert case.written_long(result.info, addrs.GEMDOS_DISK_ERROR) == 0


def test_a_dirty_directory_buffer_uses_the_directory_bias():
    """The same routine, one region over: the record it writes is `m_recoff[1] + b_bufrec`, which is
    what makes one buffer list hold directory and data sectors without confusing them."""
    contents = _dirty_sector(0x2B)
    result = _flush(0, fs.holding(DRIVE, region=fs.BCB_TYPE_DIR, record=DIR_RECORD, dirty=1,
                                  contents=contents))
    record = fs.record_of(fs.BCB_TYPE_DIR, DIR_RECORD)

    assert [call[4] for call in fs.DISK_CALLS] == [record]
    assert result.sector(record) == contents


def test_a_dirty_fat_buffer_is_written_TWICE_once_to_each_copy():
    """THE ONE THING THAT MAKES BUFFER TYPE 0 SPECIAL. `m_recoff[0]` is derived from the BPB's
    `fatrec`, which names the SECOND FAT; the first copy is `m_fsiz` records below it, and the ROM's
    second `Rwabs` at $fc59b2 is what keeps the two in step. Both copies must end up holding the
    buffer, and no third sector may be touched."""
    contents = _dirty_sector(0x7E)
    result = _flush(0, fs.holding(DRIVE, region=fs.BCB_TYPE_FAT, record=FAT_RECORD, dirty=1,
                                  contents=contents))
    second = fs.record_of(fs.BCB_TYPE_FAT, FAT_RECORD)
    first = second - fs.FAT_SECTORS

    assert [call[4] for call in fs.DISK_CALLS] == [second, first]
    assert result.sector(second) == contents
    assert result.sector(first) == contents
    assert result.sector(second + 1) == fs.sector_of(fs.DISK, second + 1), \
        "the FAT's other sector was written too"


# ---- buffer_get, $fc5a98 -------------------------------------------------------------------------

def _get(record, chains, dirty=0, dmd_drive=DRIVE, mediach=None):
    pokes = {**fs.drive(dmd_drive), **fs.cache(**chains), **fs.mediach_answer(mediach),
             **case.args(">HIH", record & 0xFFFF, fs.DMD_AT, dirty)}
    return _run(addrs.GEMDOS_BUFFER_GET,
                lambda lib, buf: lib.gemdos_buffer_get(buf, record & 0xFFFF, fs.DMD_AT, dirty),
                pokes)


def test_a_miss_on_an_empty_list_entry_fills_it_from_the_disk():
    """The plainest arm: nothing holds the record, one buffer is EMPTY, so that one is filled by a
    single `Rwabs` read and stamped with the record, the region, the drive and the DMD.

    This is also what pins the STAGED DRIVER itself — if the stub read its `recno` or its buffer
    pointer from the wrong stack slot, the sector that arrived would be the wrong one, and the
    candidate's hook (which is handed the arguments by C) would have the right one.
    """
    result = _get(DATA_RECORD, {"data": [(0, fs.EMPTY)]})
    record = fs.record_of(fs.BCB_TYPE_DATA, DATA_RECORD)

    assert fs.DISK_CALLS == [(addrs.BIOS_RWABS_FN, fs.RWABS_READ, fs.buffer_at(0), 1, record,
                              DRIVE)]
    assert result.info["ret"] == fs.buffer_at(0)
    assert result.after(fs.buffer_at(0), fs.SECTOR_BYTES) == fs.sector_of(fs.DISK, record)
    assert case.written(result.info, fs.bcb_at(0) + fs.BCB_BUFREC, 2) == DATA_RECORD & 0xFFFF
    assert case.written(result.info, fs.bcb_at(0) + fs.BCB_BUFTYP, 2) == fs.BCB_TYPE_DATA
    assert case.written(result.info, fs.bcb_at(0) + fs.BCB_BUFDRV, 2) == DRIVE
    assert case.written_long(result.info, fs.bcb_at(0) + fs.BCB_DM) == fs.DMD_AT
    assert case.written(result.info, fs.bcb_at(0) + fs.BCB_DIRTY, 2) == 0


def test_a_hit_asks_mediach_and_reads_nothing():
    """A buffer already holding the record answers it — but only after `Mediach` has been asked
    whether the medium those bytes came off is still in the drive. That interrogation is the whole
    of what a hit costs.

    WHICH DRIVE IT IS ASKED WITH CANNOT BE TESTED. The ROM passes `b_bufdrv` ($fc5bc8) and the hit
    test has just proved that equal to the DMD's `m_drvnum`, so a reconstruction passing either one
    behaves identically — a mutation swapping them survives, and it is recorded as an equivalent
    mutant rather than as a coverage hole."""
    held = _dirty_sector(0x66)
    result = _get(DATA_RECORD,
                  {"data": [(0, fs.holding(DRIVE, record=DATA_RECORD, contents=held))]})

    assert fs.DISK_CALLS == [(addrs.BIOS_MEDIACH_FN, 0, 0, 0, 0, DRIVE)]
    assert result.info["ret"] == fs.buffer_at(0)
    assert result.after(fs.buffer_at(0), fs.SECTOR_BYTES) == held, \
        "a hit re-read the sector it already had"


def test_a_MAYBE_media_change_re_reads_the_hit_in_place():
    """THE SUBTLEST ARM OF THE ROUTINE. `Mediach` answering 1 sends the ROM back into the victim
    walk at $fc5b2c with the HIT still in A4 — so the walk re-finds that buffer's predecessor rather
    than choosing a new victim, and the buffer the caller asked for is flushed and re-read in place.

    The staged buffer holds bytes the disk does not, so "re-read" is visible: what comes back is the
    sector, not what the buffer was holding. And it is still the same buffer — a reconstruction
    that evicted the tail instead would answer a different address.
    """
    stale = _dirty_sector(0x5B)
    chain = [(0, fs.holding(DRIVE, record=DATA_RECORD)),
             (1, fs.holding(DRIVE, record=DATA_RECORD + 1, contents=stale))]
    result = _get(DATA_RECORD + 1, {"data": chain}, mediach=addrs.MEDIACH_MAYBE)
    record = fs.record_of(fs.BCB_TYPE_DATA, DATA_RECORD + 1)

    assert [(call[0], call[1], call[4]) for call in fs.DISK_CALLS] == [
        (addrs.BIOS_MEDIACH_FN, 0, 0), (addrs.BIOS_RWABS_FN, fs.RWABS_READ, record)]
    assert result.info["ret"] == fs.buffer_at(1), "the re-read went to a different buffer"
    assert result.after(fs.buffer_at(1), fs.SECTOR_BYTES) == fs.sector_of(fs.DISK, record)
    assert result.order(1) == [1, 0], "...and it is the head of the list afterwards"


def test_a_MAYBE_media_change_flushes_the_hit_before_re_reading_it():
    """...and the re-read goes through the flush, so a buffer that had been WRITTEN reaches the disk
    before the disk overwrites it — three BIOS calls, in one order."""
    contents = _dirty_sector()
    chain = [(0, fs.holding(DRIVE, record=DATA_RECORD, dirty=1, contents=contents))]
    result = _get(DATA_RECORD, {"data": chain}, mediach=addrs.MEDIACH_MAYBE)
    record = fs.record_of(fs.BCB_TYPE_DATA, DATA_RECORD)

    assert [(call[0], call[1]) for call in fs.DISK_CALLS] == [
        (addrs.BIOS_MEDIACH_FN, 0), (addrs.BIOS_RWABS_FN, fs.RWABS_WRITE),
        (addrs.BIOS_RWABS_FN, fs.RWABS_READ)]
    assert result.sector(record) == contents, "the dirty buffer was lost rather than written"


def test_only_the_LOW_WORD_of_what_mediach_answers_is_read():
    """`move.w d0,d5` at $fc5bd8 truncates before the three compares, so a driver whose high half is
    not zero is still read by its low word alone — and `hdv_mediach` is a RAM vector, i.e. somebody
    else's hard-disk driver, so "no driver does that" would be an assumption about code this ROM
    does not contain. A reconstruction comparing the whole longword treats this as "unchanged".
    """
    stale = _dirty_sector(0x5B)
    chain = [(0, fs.holding(DRIVE, record=DATA_RECORD, contents=stale))]
    result = _get(DATA_RECORD, {"data": chain},
                  mediach=(1 << 16) | addrs.MEDIACH_MAYBE)
    record = fs.record_of(fs.BCB_TYPE_DATA, DATA_RECORD)

    assert [call[0] for call in fs.DISK_CALLS] == [addrs.BIOS_MEDIACH_FN, addrs.BIOS_RWABS_FN]
    assert result.after(fs.buffer_at(0), fs.SECTOR_BYTES) == fs.sector_of(fs.DISK, record)


def test_a_hit_is_moved_to_the_head_of_its_list():
    """MRU to the front, which is the other half of the LRU policy: the buffer the caller just used
    is the last one that will be evicted."""
    chain = [(index, fs.holding(DRIVE, record=DATA_RECORD + index)) for index in range(3)]
    result = _get(DATA_RECORD + 2, {"data": chain})

    assert result.order(1) == [2, 0, 1]


def test_a_hit_already_at_the_head_leaves_the_list_as_it_was():
    """...and the degenerate case, which the ROM does NOT special-case: it writes the head's own
    link to itself and then back, so the three stores happen either way."""
    chain = [(index, fs.holding(DRIVE, record=DATA_RECORD + index)) for index in range(3)]
    result = _get(DATA_RECORD, {"data": chain})

    assert result.order(1) == [0, 1, 2]


def test_a_miss_with_no_empty_buffer_evicts_the_LAST_one():
    """The tail of the list is the least recently used, by construction — every hit and every fill
    moves a buffer to the head — so eviction needs no timestamp and no counter."""
    chain = [(index, fs.holding(DRIVE, record=DATA_RECORD + index)) for index in range(3)]
    result = _get(DATA_RECORD + 9, {"data": chain})

    assert [call[0] for call in fs.DISK_CALLS] == [addrs.BIOS_RWABS_FN]
    assert fs.DISK_CALLS[0][2] == fs.buffer_at(2), "the buffer filled was not the list's tail"
    assert result.order(1) == [2, 0, 1]


def test_a_miss_prefers_an_EMPTY_buffer_wherever_it_is_in_the_list():
    """An empty buffer is taken in preference to the tail, even from the middle — and because the
    ROM's scan stores the candidate unconditionally, it is the LAST empty one that is taken."""
    chain = [(0, fs.holding(DRIVE, record=DATA_RECORD)),
             (1, fs.EMPTY),
             (2, fs.EMPTY),
             (3, fs.holding(DRIVE, record=DATA_RECORD + 1))]
    result = _get(DATA_RECORD + 9, {"data": chain})

    assert fs.DISK_CALLS[0][2] == fs.buffer_at(2)
    assert result.order(1) == [2, 0, 1, 3]


def test_evicting_a_DIRTY_buffer_writes_it_out_before_the_read():
    """The eviction goes through `GEMDOS_BUFFER_FLUSH`, so a modified sector reaches the disk before
    its buffer is reused — two `Rwabs` calls, a write then a read, in that order."""
    contents = _dirty_sector()
    chain = [(0, fs.holding(DRIVE, record=DATA_RECORD)),
             (1, fs.holding(DRIVE, record=DATA_RECORD + 1, dirty=1, contents=contents))]
    result = _get(DATA_RECORD + 9, {"data": chain})
    evicted = fs.record_of(fs.BCB_TYPE_DATA, DATA_RECORD + 1)
    fetched = fs.record_of(fs.BCB_TYPE_DATA, DATA_RECORD + 9)

    assert [(call[1], call[4]) for call in fs.DISK_CALLS] == [(fs.RWABS_WRITE, evicted),
                                                              (fs.RWABS_READ, fetched)]
    assert result.sector(evicted) == contents
    assert result.after(fs.buffer_at(1), fs.SECTOR_BYTES) == fs.sector_of(fs.DISK, fetched)


def test_a_buffer_held_for_another_drive_is_not_a_hit():
    """`b_bufdrv` is compared before `b_bufrec`, so the same record on another drive is a miss —
    and the buffer holding it is evicted like any other."""
    chain = [(0, fs.holding(OTHER_DRIVE, record=DATA_RECORD))]
    _get(DATA_RECORD, {"data": chain})
    assert [call[0] for call in fs.DISK_CALLS] == [addrs.BIOS_RWABS_FN]


@pytest.mark.parametrize("record,region,which", (
    (FAT_RECORD, fs.BCB_TYPE_FAT, 0),
    (DIR_RECORD, fs.BCB_TYPE_DIR, 1),
    (DATA_RECORD, fs.BCB_TYPE_DATA, 1),
))
def test_the_region_is_arithmetic_on_the_record_and_it_chooses_the_LIST(record, region, which):
    """The record is shifted down to its cluster and compared with the root directory's own first
    cluster: below it is the FAT, at or above it a NEGATIVE record is the directory and a
    non-negative one is data. The FAT then gets a list of its own and the other two share one."""
    chains = {"fat": [(0, fs.EMPTY)], "data": [(1, fs.EMPTY)]}
    result = _get(record, chains)
    index = 0 if which == 0 else 1

    assert fs.DISK_CALLS[0][4] == fs.record_of(region, record)
    assert fs.DISK_CALLS[0][2] == fs.buffer_at(index), "the wrong buffer list was used"
    assert case.written(result.info, fs.bcb_at(index) + fs.BCB_BUFTYP, 2) == region
    assert result.info["ret"] == fs.buffer_at(index)


def test_the_dirty_argument_marks_the_buffer():
    """A caller about to modify a sector says so in the same call, which is why nothing in the ROM
    ever sets `b_dirty` by hand.

    The ROM stores it AFTER the relink, over the 0 a fill has just left — and that ORDER is not
    what this asserts: nothing between the two touches `b_dirty`, so a reconstruction storing it
    first leaves the same byte. Only the value is a compared fact."""
    result = _get(DATA_RECORD, {"data": [(0, fs.EMPTY)]}, dirty=1)
    assert case.written(result.info, fs.bcb_at(0) + fs.BCB_DIRTY, 2) == 1


# ---- rwabs_data, $fc59f2 -------------------------------------------------------------------------

def _rwabs_data(rwflag, count, record, buffer_at, chains=None, contents=None):
    pokes = {**fs.drive(DRIVE), **fs.cache(**(chains or {})),
             **case.args(">HHHII", rwflag, count, record & 0xFFFF, buffer_at, fs.DMD_AT)}
    if contents is not None:
        pokes[buffer_at] = contents
    return _run(addrs.GEMDOS_RWABS_DATA,
                lambda lib, buf: lib.gemdos_rwabs_data(buf, rwflag, count, record & 0xFFFF,
                                                       buffer_at, fs.DMD_AT),
                pokes, width=case.NO_RESULT)


# A buffer for a whole cluster, clear of the BCBs and their sector buffers, inside the RAM disk's
# own span and below the image.
TRANSFER_AT = fs.BUFFERS_AT + fs.BCB_COUNT * fs.BCB_STRIDE
assert TRANSFER_AT + fs.CLUSTER_BYTES <= fs.IMAGE_AT


def test_a_multi_record_read_goes_straight_to_rwabs():
    """One call, `count` records, biased by `m_recoff[2]` — which is how a whole cluster of a file
    moves without passing through a 512-byte buffer at all."""
    result = _rwabs_data(fs.RWABS_READ, fs.SECTORS_PER_CLUSTER, DATA_RECORD, TRANSFER_AT,
                         contents=bytes([fs.SLACK_FILL]) * fs.CLUSTER_BYTES)
    first = fs.record_of(fs.BCB_TYPE_DATA, DATA_RECORD)

    assert fs.DISK_CALLS == [(addrs.BIOS_RWABS_FN, fs.RWABS_READ, TRANSFER_AT,
                              fs.SECTORS_PER_CLUSTER, first, DRIVE)]
    assert result.after(TRANSFER_AT, fs.CLUSTER_BYTES) == \
        fs.DISK[first * fs.SECTOR_BYTES:(first + fs.SECTORS_PER_CLUSTER) * fs.SECTOR_BYTES]


def test_a_write_puts_the_callers_bytes_on_the_disk():
    contents = bytes([DIRTY_BYTE]) * fs.CLUSTER_BYTES
    result = _rwabs_data(fs.RWABS_WRITE, fs.SECTORS_PER_CLUSTER, DATA_RECORD, TRANSFER_AT,
                         contents=contents)
    first = fs.record_of(fs.BCB_TYPE_DATA, DATA_RECORD)

    assert result.sector(first) == contents[:fs.SECTOR_BYTES]
    assert result.sector(first + 1) == contents[fs.SECTOR_BYTES:]


def test_a_cached_buffer_inside_the_span_is_flushed_first():
    """THE REASON THIS ROUTINE IS NOT JUST AN `Rwabs`. A dirty buffer holding a record the caller is
    about to read would otherwise be lost, and a stale one would survive a write — so the DATA list
    is walked and every buffer inside `[recno, recno + count)` is flushed.

    A FLUSH IS NOT AN EVICTION: `$fc59e0` puts `b_bufdrv` back and clears `b_dirty`, so the buffer
    goes on holding the record, now clean — and what the caller reads is the bytes the flush has
    just put on the disk."""
    contents = _dirty_sector()
    chains = {"data": [(0, fs.holding(DRIVE, record=DATA_RECORD + 1, dirty=1, contents=contents))]}
    result = _rwabs_data(fs.RWABS_READ, fs.SECTORS_PER_CLUSTER, DATA_RECORD, TRANSFER_AT,
                         chains=chains, contents=bytes([fs.SLACK_FILL]) * fs.CLUSTER_BYTES)
    first = fs.record_of(fs.BCB_TYPE_DATA, DATA_RECORD)

    assert [(call[1], call[4]) for call in fs.DISK_CALLS] == [(fs.RWABS_WRITE, first + 1),
                                                              (fs.RWABS_READ, first)]
    assert case.written(result.info, fs.bcb_at(0) + fs.BCB_BUFDRV, 2) == DRIVE
    assert case.written(result.info, fs.bcb_at(0) + fs.BCB_DIRTY, 2) == 0
    assert result.after(TRANSFER_AT + fs.SECTOR_BYTES, fs.SECTOR_BYTES) == contents


@pytest.mark.parametrize("held,flushed,why", (
    (DATA_RECORD - 1, False, "one record BELOW the span"),
    (DATA_RECORD, True, "the span's first record: `b_bufrec >= recno` is a `blt` to skip"),
    (DATA_RECORD + 1, True, "...and its last"),
    (DATA_RECORD + 2, False, "one record ABOVE it: `recno + count > b_bufrec` is a `ble` to skip"),
))
def test_the_overlap_bound_is_closed_below_and_open_above(held, flushed, why):
    chains = {"data": [(0, fs.holding(DRIVE, record=held, dirty=1, contents=_dirty_sector()))]}
    _rwabs_data(fs.RWABS_READ, fs.SECTORS_PER_CLUSTER, DATA_RECORD, TRANSFER_AT, chains=chains,
                contents=bytes([fs.SLACK_FILL]) * fs.CLUSTER_BYTES)
    writes = [call for call in fs.DISK_CALLS if call[1] == fs.RWABS_WRITE]
    assert bool(writes) is flushed, why


def test_a_buffer_on_another_drive_inside_the_span_is_left_alone():
    """The overlap test is `b_bufdrv == m_drvnum` first: the same record numbers on another drive
    are not this drive's records."""
    chains = {"data": [(0, fs.holding(OTHER_DRIVE, record=DATA_RECORD, dirty=1,
                                      contents=_dirty_sector()))]}
    _rwabs_data(fs.RWABS_READ, fs.SECTORS_PER_CLUSTER, DATA_RECORD, TRANSFER_AT, chains=chains,
                contents=bytes([fs.SLACK_FILL]) * fs.CLUSTER_BYTES)
    assert [call[1] for call in fs.DISK_CALLS] == [fs.RWABS_READ]


def test_the_FAT_list_is_never_walked():
    """Only `_bufl[1]` is: a FAT sector can never be inside a span of data records, so a dirty FAT
    buffer survives a data transfer untouched."""
    chains = {"fat": [(0, fs.holding(DRIVE, region=fs.BCB_TYPE_FAT, record=FAT_RECORD, dirty=1,
                                     contents=_dirty_sector()))],
              "data": [(1, fs.EMPTY)]}
    result = _rwabs_data(fs.RWABS_READ, fs.SECTORS_PER_CLUSTER, DATA_RECORD, TRANSFER_AT,
                         chains=chains, contents=bytes([fs.SLACK_FILL]) * fs.CLUSTER_BYTES)

    assert [call[1] for call in fs.DISK_CALLS] == [fs.RWABS_READ]
    assert result.word(fs.bcb_at(0) + fs.BCB_BUFDRV) == DRIVE
    assert result.word(fs.bcb_at(0) + fs.BCB_DIRTY) == 1


# ---- what every one of these owes the harness ----------------------------------------------------

def test_every_bios_call_returned_to_a_site_the_rom_really_has_a_jsr_at():
    """`GEMDOS_BIOS_TRAMPOLINE` parks its return address at `$eb0` before taking the trap, so the
    longword left there names the instruction after a `jsr` to it — which `gemdos.bios_call_site`
    re-checks against the ROM's own instruction stream. The reconstruction stores the same longword
    from a named constant, and this is what says that constant is a real call site."""
    result = _get(DATA_RECORD, {"data": [(0, fs.EMPTY)]})
    assert gemdos.bios_call_site(result.info) == addrs.BIOS_RETURN_BUFFER_READ


@pytest.mark.parametrize("entry,expected", (
    (addrs.BIOS_RETURN_BUFFER_FLUSH, addrs.BIOS_RETURN_BUFFER_FLUSH),
    (addrs.BIOS_RETURN_BUFFER_FLUSH_FAT1, addrs.BIOS_RETURN_BUFFER_FLUSH_FAT1),
))
def test_each_call_site_constant_names_an_instruction_after_such_a_jsr(entry, expected):
    """...and the other four, checked as ADDRESSES rather than by running each arm: the six bytes
    before each must be `jsr GEMDOS_BIOS_TRAMPOLINE`."""
    assert bytes(BASE_IMAGE[entry - gemdos.JSR_BYTES:entry]) == gemdos.JSR_TRAMPOLINE
    assert entry == expected


@pytest.mark.parametrize("site", (addrs.BIOS_RETURN_RWABS_DATA, addrs.BIOS_RETURN_BUFFER_READ,
                                  addrs.BIOS_RETURN_BUFFER_MEDIACH))
def test_the_remaining_call_sites_are_jsr_sites_too(site):
    assert bytes(BASE_IMAGE[site - gemdos.JSR_BYTES:site]) == gemdos.JSR_TRAMPOLINE


# ---- the registry --------------------------------------------------------------------------------
# One row per routine, in the shape `test_boot_snapshot.VERIFIED_CASES` takes.

_FLUSH_INDEX = 0
_FLUSH_HOLDING = fs.holding(DRIVE, record=DATA_RECORD, dirty=1, contents=_dirty_sector())
gemdos.register("buffer_flush, a dirty data buffer", addrs.GEMDOS_BUFFER_FLUSH, {"a5": 0},
            fs.machine({**fs.drive(DRIVE), **fs.cache(data=[(_FLUSH_INDEX, _FLUSH_HOLDING)]),
                        **case.long_args(fs.bcb_at(_FLUSH_INDEX))}))
gemdos.register("buffer_get, a miss into an empty buffer", addrs.GEMDOS_BUFFER_GET, {"a5": 0},
            fs.machine({**fs.drive(DRIVE), **fs.cache(data=[(0, fs.EMPTY)]),
                        **case.args(">HIH", DATA_RECORD & 0xFFFF, fs.DMD_AT, 0)}))
gemdos.register("rwabs_data, a cluster read", addrs.GEMDOS_RWABS_DATA, {"a5": 0},
            fs.machine({**fs.drive(DRIVE), **fs.cache(),
                        TRANSFER_AT: bytes([fs.SLACK_FILL]) * fs.CLUSTER_BYTES,
                        **case.args(">HHHII", fs.RWABS_READ, fs.SECTORS_PER_CLUSTER,
                                    DATA_RECORD & 0xFFFF, TRANSFER_AT, fs.DMD_AT)}))
