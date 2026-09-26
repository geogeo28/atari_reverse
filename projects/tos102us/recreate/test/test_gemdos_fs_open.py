r"""`open` (`$fc7606`) and its leaf `Fopen` ($3d, `$fc75f2`) — a path's file into a handle — over
`test/fs_dir.py`'s tree.

The name is searched under GEMDOS_ATTR_ANY_FILE, which no plain subdirectory and no volume label
answers; a read-only entry is EACCDN for any mode but 0; and the rest is `$fc6f5c` (the first unowned
handle record, then `$fc6fdc` building the OFD — or copying the one already open on the same entry).
Either miss, the directory's or the name's, is EFILNF. The mode is a WORD throughout: the read-only
test is a `tst.w` and `$fc6f5c` stores all sixteen bits at OFD_MODE, so a mode whose low byte is read's
is still a write.

`Fopen` IS ALSO DISPATCHED. The dispatcher compares an `Fopen`'s file name against the device names
before it calls the leaf (`$fc9aca`); a name that is not one goes on to the leaf, which is the slice below.
The device names themselves are `test_gemdos_dispatch_device.py`'s.

Unpoisoned, for `test_gemdos_fs_dir.py`'s reasons.
"""
import pytest

import fs_dir as d
import fs_file as ff
import fs_io as io
import fs_open as fo
import fs_records as records
import gemdos
import gemdos_fs as fs
import gemdos_process as process

FOPEN, OPEN = fs.FOPEN, fs.OPEN
READ, WRITE, READ_WRITE = fs.OPEN_MODE_READ, fs.OPEN_MODE_WRITE, fs.OPEN_MODE_READ_WRITE
# A mode WORD whose low byte is read's.
READ_UNDER_A_HIGH_BYTE = fs.ARGUMENT_HIGH_BYTE | READ
ROOT = fs.ROOT_DND_AT


def _fopen(path, mode, extra=None):
    return fo.run(FOPEN, (fo.NAME_AT, mode), path, extra)


def _record(result, handle):
    """The handle record `handle` names after the run: (OFD, owner, references)."""
    _at, *fields = process.descriptor(result.final, handle)
    return tuple(fields)


def _assert_opened(result, handle, dnd, index):
    """`handle` answered, its record claimed by `p_run` naming an OFD at the head of `dnd`'s open files,
    over entry `index` of that directory."""
    assert result.info["ret"] == handle
    ofd, owner, references = _record(result, handle)
    assert (owner, references) == (ff.P_RUN, 1)
    assert result.long(dnd + fs.DND_FILES) == ofd != 0
    assert result.long(ofd + fs.OFD_DIRPOS) == index * fs.DIRENT_BYTES


# ---- what it opens -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("mode", (READ, WRITE, READ_WRITE))
def test_fopen_opens_a_plain_file_in_every_mode(mode):
    result = _fopen("A:\\SHORT.TXT", mode)
    _assert_opened(result, ff.A_HANDLE, ROOT, d.ROOT_INDEX["SHORT"])


def test_a_read_only_file_opens_for_reading():
    result = _fopen("A:\\EMPTY.BIN", READ)
    _assert_opened(result, ff.A_HANDLE, ROOT, d.ROOT_INDEX["EMPTY"])


@pytest.mark.parametrize("mode", (WRITE, READ_WRITE))
def test_a_read_only_file_opened_to_write_is_eaccdn_with_no_record_claimed(mode):
    result = _fopen("A:\\EMPTY.BIN", mode)
    assert result.info["ret"] == fo.EACCDN
    assert _record(result, ff.A_HANDLE) == (0, 0, 0)


def test_a_read_only_file_opened_with_only_a_high_byte_is_eaccdn():
    """`tst.w` ($fc7656): a mode whose low byte is 0 is a write all the same."""
    result = _fopen("A:\\EMPTY.BIN", READ_UNDER_A_HIGH_BYTE)
    assert result.info["ret"] == fo.EACCDN
    assert _record(result, ff.A_HANDLE) == (0, 0, 0)


def test_the_whole_mode_word_is_stored_in_the_ofd():
    mode = fs.ARGUMENT_HIGH_BYTE | READ_WRITE
    result = _fopen("A:\\SHORT.TXT", mode)
    _assert_opened(result, ff.A_HANDLE, ROOT, d.ROOT_INDEX["SHORT"])
    assert result.word(_record(result, ff.A_HANDLE)[0] + fs.OFD_MODE) == mode


def test_fopen_two_levels_down():
    result = _fopen("A:\\SUBDIR\\INNER\\DEEP.TXT", READ)
    inner = d.child_named(result, d.child_named(result, ROOT, "SUBDIR"), "INNER")
    _assert_opened(result, ff.A_HANDLE, inner, d.DOT_ENTRIES)


def test_fopen_through_a_child_list_three_long():
    result = _fopen("A:\\SUBDIR\\NOTE.TXT", READ, fo.walked_root())
    _assert_opened(result, ff.A_HANDLE, d.SUBDIR_DND_AT, d.DOT_ENTRIES + 1)
    assert result.word(fs.ROOT_OFD_AT + fs.OFD_FLAGS) == 0, "the root was searched"


def test_a_second_open_shares_the_ofd_already_open_on_the_entry():
    """SHORT.TXT already open — the SECOND OFD on the root's list, behind SPAN.DAT's — through the
    first handle record: the new open takes the second record, copies the open OFD's state, and points
    the old OFD at itself (`$fc6fdc`'s already-open arm)."""
    already = {**ff.open_entry("SPAN", io.OTHER_OFD_AT, link=io.OFD_AT), **ff.open_entry("SHORT", io.OFD_AT),
               **ff.root_files(io.OTHER_OFD_AT), **ff.handle_naming(io.OFD_AT)}
    result = _fopen("A:\\SHORT.TXT", READ, already)
    _assert_opened(result, ff.A_HANDLE + 1, ROOT, d.ROOT_INDEX["SHORT"])
    new = _record(result, ff.A_HANDLE + 1)[0]
    assert result.long(io.OFD_AT + fs.OFD_NEXT_SAME_FILE) == new
    assert ff.files_after(result) == [new, io.OTHER_OFD_AT, io.OFD_AT]


@pytest.mark.parametrize("path,why", (
    ("A:\\NOPE.TXT", "a name the directory has not got"),
    ("A:\\NOPE\\SHORT.TXT", "a DIRECTORY the path has not got — EFILNF too"),
    ("A:\\SUBDIR", "a subdirectory: the search attribute has not got its bit"),
    ("A:\\STAGEDDS.K", "...nor the volume label's"),
))
def test_a_miss_is_efilnf(path, why):
    result = _fopen(path, READ)
    assert result.info["ret"] == fo.EFILNF, why
    assert _record(result, ff.A_HANDLE) == (0, 0, 0), why


def test_a_full_handle_table_is_enhndl():
    result = _fopen("A:\\SHORT.TXT", READ, process.full_table_poke(ff.SOMEBODY_ELSE))
    assert result.info["ret"] == fo.ENHNDL


def test_a_spent_pool_is_ensmem_with_the_record_already_claimed():
    """The root's DNDs already made (so the search passing SUBDIR asks the pool for nothing), the one
    record the pool is asked for is the file's OFD — which it cannot give."""
    result = _fopen("A:\\SHORT.TXT", READ, {**fo.walked_root(), **records.pool_spent()})
    assert result.info["ret"] == process.GEMDOS_ENSMEM
    assert _record(result, ff.A_HANDLE)[1] == ff.P_RUN


def test_a_dispatched_fopen_of_a_file_runs_the_leaf():
    """Past the device-name arm, which "SHORT.TXT" does not match, our dispatcher calls our leaf."""
    result = fo.dispatch(FOPEN, (*gemdos.long_words(fo.NAME_AT), READ), "A:\\SHORT.TXT")
    _assert_opened(result, ff.A_HANDLE, ROOT, d.ROOT_INDEX["SHORT"])


def test_open_at_its_own_address():
    result = fo.run(OPEN, (fo.NAME_AT, READ_WRITE), "A:\\SPAN.DAT")
    _assert_opened(result, ff.A_HANDLE, ROOT, d.ROOT_INDEX["SPAN"])


# ---- the registry ------------------------------------------------------------------------------------

def _register_all():
    fo.register("open, a plain file", OPEN, (fo.NAME_AT, READ), "A:\\SHORT.TXT")
    fo.register("Fopen, two levels down", FOPEN, (fo.NAME_AT, READ), "A:\\SUBDIR\\INNER\\DEEP.TXT")
    fo.register("Fopen, a read-only file to write", FOPEN, (fo.NAME_AT, WRITE), "A:\\EMPTY.BIN")


_register_all()
