"""`$fc7824` gemdos_delete_entry(dnd, dirent, pos) — `Fdelete`'s, `Fcreate`'s and `Ddelete`'s common
end of a directory entry — over the staged disk.

    $fc7830  movea.l 52(a0),a4     every OFD open on the directory...
    $fc783a  cmp.l 16(a6),d0       ...at the entry's position: every handle record naming it —
    $fc786e  cmp.l $87ce,d0        the caller's are CLOSED ($fc57ee, flags 0), anybody else's is EACCDN
    $fc78a6  move.w 26(a0),-2(a6)  the entry's first cluster, turned round in the frame
    $fc78be  bsr $fc6038 / $fc5f44 the chain walked and every entry zeroed, until 0 or the word -1
    $fc78fa  move.b #$e5,-4(a6)    the DELETED mark written over the entry's first byte
    $fc7918  bsr $fc57ee           ...and the directory closed with flag 2 — which flushes it all

THE HANDLES ARE CLOSED, NOT RELEASED. The caller's handle records go on naming the OFD after its
delete, and two of them on one OFD close it twice (the second close is `$fc57ee`'s EINTRN arm, not
read — and UNPINNED: nothing it does survives the delete, see the case). And a refusal comes AFTER any
of the caller's own handles met first in the table were closed.
"""
import ctypes

import pytest

from harness import _lib, addrs

import case
import fs_file as ff
import fs_io as io
import fs_records as records
import gemdos_fs as fs
import gemdos_process as process

_lib.gemdos_delete_entry.restype = ctypes.c_uint32

EACCDN = fs.GEMDOS_EACCDN
DIRENT_AT = records.dirent_slot(0)
FILE_OFD = io.OFD_AT
OTHER_OFD = io.OTHER_OFD_AT


def _root_entry_before(name):
    """A root entry's 32 bytes as the staged disk holds them."""
    at = fs.ROOT_RECORD * fs.SECTOR_BYTES + ff.entry_position(name)
    return fs.DISK[at:at + fs.DIRENT_BYTES]


def _delete_pokes(name, pokes=None):
    """The entry as the caller hands it — a copy of the root's own (it is the cache's in the ROM, and
    `delete_entry` only reads its first cluster) — and the frame."""
    return {DIRENT_AT: _root_entry_before(name), **(pokes or {}),
            **case.args(">III", fs.ROOT_DND_AT, DIRENT_AT, ff.entry_position(name))}


def _delete(name, pokes=None):
    return io.run(addrs.GEMDOS_DELETE_ENTRY,
                  lambda lib, buf: lib.gemdos_delete_entry(buf, fs.ROOT_DND_AT, DIRENT_AT, ff.entry_position(name)),
                  _delete_pokes(name, pokes))


def _assert_deleted(result, name):
    """The mark on the disk over the entry's first byte, and nothing else of the entry changed."""
    before = _root_entry_before(name)
    assert ff.root_entry_after(result, name) == bytes([fs.DIRENT_DELETED]) + before[1:]


def _fat(result):
    return {cluster: fs.fat12_entry(io.fat_after(result), cluster) for cluster in range(fs.FAT_ENTRIES)}


def _freed(result, clusters):
    """The FAT a run left is the base one with `clusters` (and only they) zero."""
    return _fat(result) == {**fs.BASE_FAT, **{cluster: 0 for cluster in clusters}}


# ---- the chain and the mark ----------------------------------------------------------------------

@pytest.mark.parametrize("name,chain", (
    ("SPAN", range(fs.SPAN_CLUSTER, fs.SPAN_CLUSTER + fs.SPAN_CLUSTERS)),   # 4 -> 5 -> 6, even $fff
    ("SHORT", (fs.SHORT_CLUSTER,)),                                         # one ODD cluster's $fff
    ("EMPTY", ()),                                                          # cluster 0: no walk at all
))
def test_the_chain_is_freed_and_the_entry_marked(name, chain):
    result = _delete(name)
    assert result.info["ret"] == 0
    assert _freed(result, chain)
    _assert_deleted(result, name)


def test_the_directory_close_writes_everything_to_the_disk():
    """Flag 2 on the directory's OFD: no unlink, and the flush puts the FAT (both copies) and the
    root's sector on the disk — the cache keeps them, clean."""
    result = _delete("SPAN")
    table = fs.sector_of(result.final, fs.FAT1_RECORD, fs.IMAGE_AT)
    assert fs.fat12_entry(table, fs.SPAN_CLUSTER) == 0
    assert fs.sector_of(result.final, fs.FAT2_RECORD, fs.IMAGE_AT) == table
    for index in range(fs.BCB_COUNT):
        assert result.word(fs.bcb_at(index) + fs.BCB_DIRTY) == 0


# ---- files still open ------------------------------------------------------------------------------

def _open_span(*handles):
    """`SPAN` open at `FILE_OFD`, on the root's list, named by `handles` — `(handle, owner)` pairs."""
    pokes = {**ff.open_entry("SPAN", FILE_OFD), **ff.root_files(FILE_OFD)}
    for handle, owner in handles:
        pokes.update(ff.handle_naming(FILE_OFD, handle, owner))
    return pokes


# The table's LAST record, so the walk is proved to reach the end of all seventy-five.
LAST_HANDLE = addrs.GEMDOS_FIRST_FILE_HANDLE + process.GEMDOS_HANDLE_COUNT - 1


def test_a_file_another_process_has_open_is_EACCDN_and_nothing_is_touched():
    result = _delete("SPAN", _open_span((LAST_HANDLE, ff.SOMEBODY_ELSE)))
    assert result.info["ret"] == EACCDN
    assert not fs.DISK_CALLS, "the refusal reached the disk"
    assert ff.files_after(result) == [FILE_OFD]


def test_the_caller_s_own_open_is_closed_and_the_file_deleted():
    """Closed through `$fc57ee` with flags 0 — off the list — and then deleted; the handle record
    still names the OFD afterwards."""
    result = _delete("SPAN", _open_span((ff.A_HANDLE, ff.P_RUN)))
    assert result.info["ret"] == 0
    assert ff.files_after(result) == []
    assert _freed(result, range(fs.SPAN_CLUSTER, fs.SPAN_CLUSTER + fs.SPAN_CLUSTERS))
    _assert_deleted(result, "SPAN")
    assert result.long(process.descriptor_at(ff.A_HANDLE)) == FILE_OFD


def test_two_of_the_caller_s_handles_close_the_ofd_twice():
    """The second close finds the OFD already unlinked — `$fc57ee`'s EINTRN, which nobody reads.

    THE SECOND CLOSE IS UNOBSERVABLE, so this case pins the delete going through, NOT that the ROM
    closes twice: a reconstruction that closed only once passes it (the fix pass's mutant). A clean
    OFD's second close only walks the list and answers EINTRN; a dirty one's rewrites the entry into
    the cached directory sector — the same ten bytes the first close wrote — before the EINTRN, and
    the delete's own mark and flag-2 close then write and flush that sector either way. Faithful to
    the ROM (`$fc787a` closes once per matching record), and honestly unpinned."""
    result = _delete("SPAN", _open_span((ff.A_HANDLE, ff.P_RUN), (ff.ANOTHER_HANDLE, ff.P_RUN)))
    assert result.info["ret"] == 0
    _assert_deleted(result, "SPAN")


def test_a_refusal_comes_after_the_caller_s_earlier_handles_were_closed():
    """The table is walked in order: the caller's handle 6 closes the OFD (unlinking it), and only
    then does handle 7, somebody else's, refuse the delete — with the chain and the entry intact."""
    result = _delete("SPAN", _open_span((ff.A_HANDLE, ff.P_RUN), (ff.ANOTHER_HANDLE, ff.SOMEBODY_ELSE)))
    assert result.info["ret"] == EACCDN
    assert ff.files_after(result) == []
    assert _freed(result, ())
    assert ff.root_entry_after(result, "SPAN") == _root_entry_before("SPAN")


def test_an_open_file_at_another_position_is_not_looked_at():
    """Only an OFD whose `OFD_DIRPOS` is the entry's own: `SHORT` open by somebody else does not stop
    `SPAN`'s delete, and stays on the list."""
    pokes = {**ff.open_entry("SHORT", OTHER_OFD), **ff.root_files(OTHER_OFD),
             **ff.handle_naming(OTHER_OFD, ff.A_HANDLE, ff.SOMEBODY_ELSE)}
    result = _delete("SPAN", pokes)
    assert result.info["ret"] == 0
    assert ff.files_after(result) == [OTHER_OFD]
    _assert_deleted(result, "SPAN")


# ---- the registry --------------------------------------------------------------------------------

def _register_all():
    io.register("delete_entry, a three-cluster file", addrs.GEMDOS_DELETE_ENTRY, _delete_pokes("SPAN"))
    io.register("delete_entry, open by another process", addrs.GEMDOS_DELETE_ENTRY,
                _delete_pokes("SPAN", _open_span((ff.A_HANDLE, ff.SOMEBODY_ELSE))))


_register_all()
