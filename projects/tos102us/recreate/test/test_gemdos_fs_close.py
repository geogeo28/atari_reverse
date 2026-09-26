"""`$fc57ee` gemdos_ofd_close, and `Fclose`'s ($3e) open-FILE arm over it — over the staged disk.

    $fc5800  btst #0,5(a5)        OFD_DIRTY: the entry is rewritten through the directory's OFD
    $fc5826  jsr $fc4f10          ...the cluster and the length turned round IN THE OFD, and back
    $fc583a  btst #1,13(a6)       flag 2 (a DIRECTORY): the entry written with length 0
    $fc5898  tst.w 12(a6)         flag 0 — or flag bit 2 — unlinks the OFD from its DND's list
    $fc58c8  moveq #-65,d0        ...EINTRN if it is not on it, answered BEFORE the flush
    $fc58cc  clr.w d6             EVERY buffer of BOTH lists flushed, whatever drive or state

THE CLOSE IS WHERE THE CACHE IS WRITTEN, lopsidedly: `$fc590a` writes a dirty buffer and KEEPS it,
clean, and EMPTIES one that was clean already — so after every close but the EINTRN one the cache
holds only what was waiting to be written. That is why the cases run over a cache with work in it
(`test/fs_file.py`) and read the dirty sectors back off the disk.

`Fclose` of a handle naming an open file closes the OFD FIRST, with flags 0 — whoever else holds the
descriptor — and only then drops the count; the last holder gives the OFD back to the pool.
"""
import ctypes

import pytest

from harness import _lib, addrs

import case
import fs_file as ff
import fs_io as io
import fs_records as records
import gemdos
import gemdos_fs as fs
import gemdos_process as process

for _name in ("gemdos_ofd_close", "gemdos_fdup", "gemdos_pool_get"):
    getattr(_lib, _name).restype = ctypes.c_uint32

EINTRN = fs.GEMDOS_EINTRN
FILE = "SPAN"                               # three clusters: its entry has a cluster AND a length
# In slot 1 and not slot 0: the OFD `Fclose` frees has the pool's class word BELOW it, in slot 0.
FILE_OFD = records.record_slot(1)
OTHER_OFD = records.record_slot(2)
THIRD_OFD = records.record_slot(3)
DIRTY = fs.OFD_DIRTY
# What a dirty close writes back: a grown length and a new first cluster (and `fs_file`'s new time
# and date) — values no staged entry holds, so the rewritten entry is told from the one that was there.
NEW_CLUSTER = 0x0123
NEW_LENGTH = 0x0004_5678


def _close_pokes(ofd, flags, pokes):
    return {**pokes, **case.args(">IH", ofd, flags)}


def _close(ofd, flags, pokes):
    return io.run(addrs.GEMDOS_OFD_CLOSE, lambda lib, buf: lib.gemdos_ofd_close(buf, ofd, flags),
                  _close_pokes(ofd, flags, pokes), buffers=ff.WORKING_CACHE)


def _on_the_list(**fields):
    """The file open at `FILE_OFD`, alone on the root's list, a record of the pool's node class."""
    return {**ff.pooled(FILE_OFD), **ff.open_entry(FILE, FILE_OFD, **fields), **ff.root_files(FILE_OFD)}


def _dirty_file(**fields):
    return _on_the_list(**{"flags": DIRTY, "strtcl": NEW_CLUSTER, "fileln": NEW_LENGTH,
                           "time": fs.as_stored(ff.NEW_TIME), "date": fs.as_stored(ff.NEW_DATE), **fields})


# ---- the write-back ------------------------------------------------------------------------------

def test_a_clean_file_is_unlinked_and_every_buffer_flushed_with_its_entry_untouched():
    result = _close(FILE_OFD, 0, _on_the_list())
    assert result.info["ret"] == 0
    assert ff.files_after(result) == []
    assert ff.root_entry_after(result, FILE) == fs.sector_of(fs.DISK, fs.ROOT_RECORD)[
        ff.entry_position(FILE):ff.entry_position(FILE) + fs.DIRENT_BYTES]
    ff.assert_every_buffer_flushed(result)


def test_a_dirty_file_s_entry_is_rewritten_from_the_ofd():
    """Time and date go back AS STORED (the OFD holds them in the disk's order already); the cluster
    and length are turned into it. The OFD itself ends as it began — both turned back — and its
    DIRTY bit is NOT cleared."""
    result = _close(FILE_OFD, 0, _dirty_file())
    entry = ff.root_entry_after(result, FILE)
    expected = fs.dirent_bytes(FILE, ff.ROOT_ENTRY[FILE][0], ff.ROOT_ENTRY[FILE][1], NEW_CLUSTER,
                               NEW_LENGTH, time=ff.NEW_TIME, date=ff.NEW_DATE)
    assert entry == expected
    assert fs.ofd_field(result.final, FILE_OFD, "strtcl") == NEW_CLUSTER
    assert fs.ofd_field(result.final, FILE_OFD, "fileln") == NEW_LENGTH
    assert fs.ofd_field(result.final, FILE_OFD, "flags") == DIRTY
    assert ff.files_after(result) == []
    ff.assert_every_buffer_flushed(result)


@pytest.mark.parametrize("flags,unlinked", (
    (fs.OFD_CLOSE_DIRECTORY, False),
    (fs.OFD_CLOSE_DIRECTORY | fs.OFD_CLOSE_UNLINK, True),       # `Dcreate`'s 6
))
def test_a_directory_s_entry_is_written_with_length_0(flags, unlinked):
    """Flag 2: the OFD's own length ($7fffffff, a directory's) set aside for the write and put back.
    Flag 2 alone does not unlink — the OFD stays on the list; with bit 2 as well it goes."""
    result = _close(FILE_OFD, flags, _dirty_file(fileln=fs.DIRECTORY_LENGTH))
    entry = ff.root_entry_after(result, FILE)
    assert entry[fs.DIRENT_FILELN:] == bytes(4)
    assert entry[fs.DIRENT_STRTCL:fs.DIRENT_FILELN] == NEW_CLUSTER.to_bytes(2, "little")
    assert fs.ofd_field(result.final, FILE_OFD, "fileln") == fs.DIRECTORY_LENGTH
    assert ff.files_after(result) == ([] if unlinked else [FILE_OFD])
    assert result.info["ret"] == 0


def test_flag_2_alone_on_an_ofd_on_no_list_is_not_EINTRN():
    """...which is the arm `Fdatime` and the directory writers take on a directory's OFD: nothing
    is looked up, so an OFD on no list closes cleanly."""
    result = _close(FILE_OFD, fs.OFD_CLOSE_DIRECTORY, ff.open_entry(FILE, FILE_OFD))
    assert result.info["ret"] == 0
    ff.assert_every_buffer_flushed(result)


# ---- the unlink ----------------------------------------------------------------------------------

def _three_open():
    """Three OFDs on the root's list: FILE_OFD -> OTHER_OFD -> THIRD_OFD."""
    return {**ff.open_entry(FILE, FILE_OFD, link=OTHER_OFD),
            **ff.open_entry("SHORT", OTHER_OFD, link=THIRD_OFD),
            **ff.open_entry("EMPTY", THIRD_OFD),
            **ff.root_files(FILE_OFD)}


@pytest.mark.parametrize("closing,left", (
    (FILE_OFD, [OTHER_OFD, THIRD_OFD]),         # the head: the DND's own link rewritten
    (OTHER_OFD, [FILE_OFD, THIRD_OFD]),         # the middle: the previous OFD's link
    (THIRD_OFD, [FILE_OFD, OTHER_OFD]),         # the tail
))
def test_the_unlink_rewrites_whichever_link_named_it(closing, left):
    result = _close(closing, 0, _three_open())
    assert result.info["ret"] == 0
    assert ff.files_after(result) == left


@pytest.mark.parametrize("flags", (0, fs.OFD_CLOSE_UNLINK))
def test_an_ofd_not_on_its_list_is_EINTRN_and_nothing_is_flushed(flags):
    """The walk reaches the list's end: `moveq #-65` and straight out — no flush, the cache as it
    was, and a dirty entry ALREADY rewritten into it (the write-back came first)."""
    pokes = {**_dirty_file(), **ff.open_entry("SHORT", OTHER_OFD), **ff.root_files(OTHER_OFD)}
    result = _close(FILE_OFD, flags, pokes)
    assert result.info["ret"] == EINTRN
    assert ff.files_after(result) == [OTHER_OFD]
    ff.assert_nothing_flushed(result)


# ---- Fclose's FILE arm ---------------------------------------------------------------------------

def _fclose(handle, pokes):
    return io.run(fs.FCLOSE.entry, fs.leaf_glue(fs.FCLOSE, (handle,)), fs.leaf_pokes(fs.FCLOSE, (handle,), pokes),
                  buffers=ff.WORKING_CACHE)


def _descriptor(result, handle):
    at = process.descriptor_at(handle)
    return (result.long(at + process.HANDLE_VALUE), result.long(at + process.HANDLE_OWNER),
            result.word(at + process.HANDLE_REFCOUNT))


def test_fclose_of_the_last_holder_closes_frees_and_releases():
    """The whole arm: the OFD closed (unlinked, its dirty entry written, everything flushed), the
    count to 0, the OFD onto the pool's chain, and the descriptor's value and owner zeroed."""
    result = _fclose(ff.A_HANDLE, {**_dirty_file(), **ff.handle_naming(FILE_OFD)})
    assert result.info["ret"] == 0
    assert ff.files_after(result) == []
    assert ff.root_entry_after(result, FILE)[fs.DIRENT_STRTCL:] == \
        NEW_CLUSTER.to_bytes(2, "little") + NEW_LENGTH.to_bytes(4, "little")
    assert _descriptor(result, ff.A_HANDLE) == (0, 0, 0)
    assert result.long(records.POOL_CHAIN) == FILE_OFD, "the OFD did not go back to the pool"
    ff.assert_every_buffer_flushed(result)


def test_fclose_of_a_shared_file_still_closes_the_ofd():
    """TWO holders: the file system's close runs ANYWAY — unlinked and flushed — and only the count
    goes down; the OFD stays allocated and the descriptor still names it."""
    result = _fclose(ff.A_HANDLE, {**_on_the_list(), **ff.handle_naming(FILE_OFD, references=2)})
    assert result.info["ret"] == 0
    assert ff.files_after(result) == []
    assert _descriptor(result, ff.A_HANDLE) == (FILE_OFD, ff.P_RUN, 1)
    assert result.long(records.POOL_CHAIN) == 0
    ff.assert_every_buffer_flushed(result)


def test_the_second_fclose_of_a_shared_file_is_EINTRN_and_still_frees():
    """...so the OTHER holder's close finds the OFD already off the list: EINTRN, no flush — and the
    count reaching 0 still frees the OFD and releases the descriptor. The shape an `Fforce`d
    descriptor (one descriptor, count 2) ends in; `Fdup`'s is the double free below."""
    result = _fclose(ff.A_HANDLE, {**_on_the_list(), **ff.root_files(0), **ff.handle_naming(FILE_OFD)})
    assert result.info["ret"] == EINTRN
    assert _descriptor(result, ff.A_HANDLE) == (0, 0, 0)
    assert result.long(records.POOL_CHAIN) == FILE_OFD
    ff.assert_nothing_flushed(result)


def test_fclose_of_a_standard_handle_naming_a_file_closes_through_its_record():
    """`p_uft[1]` naming the record: the slot is cleared, and the record's file closed and freed."""
    pokes = {**_on_the_list(), **ff.handle_naming(FILE_OFD),
             **gemdos.standard_handles_poke([0, ff.A_HANDLE])}
    result = _fclose(1, pokes)
    assert result.info["ret"] == 0
    assert result.after(ff.P_RUN + addrs.BASEPAGE_HANDLES + 1, 1) == b"\x00"
    assert _descriptor(result, ff.A_HANDLE) == (0, 0, 0)
    assert ff.files_after(result) == []


# ---- Fdup, Fclose, Fclose: the double free -------------------------------------------------------
# THREE CHAINED DIFFERENTIALS, then the two pool_gets that show what they left: each step starts from
# the machine the previous one ENDED in (`gemdos_fs.continued`), so the sequence is proved one routine
# at a time.


def _step(entry, glue, pokes, frame):
    return fs.run(entry, glue, {**pokes, **frame})


def test_fdup_and_two_fcloses_free_the_ofd_twice():
    """`$fc5216` gives the duplicate its OWN count of 1 over the same OFD. The first `Fclose` closes
    the OFD (unlinked, its dirty entry written, everything flushed) and frees it; the second closes
    the FREED record — its entry rewritten into the cache again, OFD_DIRTY never having been cleared,
    then EINTRN before any flush — and frees it AGAIN. The pool's chain then names the record and the
    record names itself, so the next two `pool_get(4)`s both answer it. TOS 1.02's own bug, kept."""
    standard = 1
    start = io.engine({**_dirty_file(), **ff.handle_naming(FILE_OFD),
                       **gemdos.standard_handles_poke([0, ff.A_HANDLE])}, ff.WORKING_CACHE)

    duplicated = _step(addrs.GEMDOS_FDUP, lambda lib, buf: lib.gemdos_fdup(buf, standard), start,
                       case.word_arg(standard))
    duplicate = duplicated.info["ret"]
    assert duplicate == ff.ANOTHER_HANDLE and _descriptor(duplicated, duplicate) == (FILE_OFD, ff.P_RUN, 1)

    first = _step(fs.FCLOSE.entry, fs.leaf_glue(fs.FCLOSE, (ff.A_HANDLE,)), fs.continued(duplicated),
                  case.word_arg(ff.A_HANDLE))
    assert first.info["ret"] == 0 and ff.files_after(first) == []
    assert first.long(records.POOL_CHAIN) == FILE_OFD and first.long(FILE_OFD) == 0, "freed onto an empty chain"
    ff.assert_every_buffer_flushed(first)

    second = _step(fs.FCLOSE.entry, fs.leaf_glue(fs.FCLOSE, (duplicate,)), fs.continued(first), case.word_arg(duplicate))
    assert second.info["ret"] == EINTRN
    assert _descriptor(second, duplicate) == (0, 0, 0)
    assert second.long(records.POOL_CHAIN) == FILE_OFD and second.long(FILE_OFD) == FILE_OFD, "the self-loop"
    root_buffer = next(index for index in second.order(1)
                       if second.word(fs.bcb_at(index) + fs.BCB_BUFDRV) != fs.BCB_EMPTY
                       and second.word(fs.bcb_at(index) + fs.BCB_BUFREC) == fs.cluster_record(fs.ROOT_START_CLUSTER))
    assert second.word(fs.bcb_at(root_buffer) + fs.BCB_DIRTY) == fs.BCB_MARKED_DIRTY, "the freed OFD rewrote its entry"

    handed_out = []
    pokes = fs.continued(second)
    for _get in range(2):
        got = _step(addrs.GEMDOS_POOL_GET, lambda lib, buf: lib.gemdos_pool_get(buf, fs.NODE_POOL_CLASS), pokes,
                    case.word_arg(fs.NODE_POOL_CLASS))
        handed_out.append(got.info["ret"])
        pokes = fs.continued(got)
    assert handed_out == [FILE_OFD, FILE_OFD], "the same record handed out twice"


# ---- Fclose through the dispatcher ---------------------------------------------------------------

def test_a_dispatched_fclose_of_a_file_runs_the_leaf():
    """The slice: our dispatcher calling our `Fclose` through the hook, against the ROM's own leaf."""
    result = io.dispatch_slice(fs.FCLOSE, (ff.A_HANDLE,), {**_dirty_file(), **ff.handle_naming(FILE_OFD)},
                               buffers=ff.WORKING_CACHE)
    assert result.info["ret"] == 0
    assert _descriptor(result, ff.A_HANDLE) == (0, 0, 0)
    ff.assert_every_buffer_flushed(result)


# ---- the registry --------------------------------------------------------------------------------

def _register_all():
    io.register("ofd_close, a dirty file", addrs.GEMDOS_OFD_CLOSE, _close_pokes(FILE_OFD, 0, _dirty_file()),
                buffers=ff.WORKING_CACHE)
    io.register("ofd_close, not on its list", addrs.GEMDOS_OFD_CLOSE,
                _close_pokes(FILE_OFD, 0, {**_dirty_file(), **ff.root_files(0)}), buffers=ff.WORKING_CACHE)
    io.register("gemdos_fclose, the last holder of a file", fs.FCLOSE.entry,
                fs.leaf_pokes(fs.FCLOSE, (ff.A_HANDLE,), {**_dirty_file(), **ff.handle_naming(FILE_OFD)}),
                buffers=ff.WORKING_CACHE)


_register_all()
