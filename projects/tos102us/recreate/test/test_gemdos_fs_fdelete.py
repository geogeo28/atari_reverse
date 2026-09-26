r"""`Fdelete` ($41, `$fc77b2`) — a path's file deleted — entered at its own address and then through the
dispatcher, over `test/fs_dir.py`'s tree.

The name is searched under GEMDOS_ATTR_ANY_FILE (no plain subdirectory or volume label answers it), a
read-only entry is EACCDN before anything is touched, and the rest is `$fc7824` at the entry's own
position: the caller's opens of it closed, another process's open refusing it (EACCDN), the chain
freed, `$e5` over its first byte, and the directory closed — which flushes every buffer, so what
the delete did is ON THE DISK when the run ends. Either miss is EFILNF.

Unpoisoned, for `test_gemdos_fs_dir.py`'s reasons.
"""
import pytest

import fs_dir as d
import fs_file as ff
import fs_io as io
import fs_open as fo
import gemdos
import gemdos_fs as fs

FDELETE = fs.FDELETE


def _fdelete(path, extra=None):
    return fo.run(FDELETE, (fo.NAME_AT,), path, extra)


def _root_entry(result, name):
    return result.root_entry(d.ROOT_INDEX[name])


def _assert_nothing_deleted(result):
    assert result.after(fs.IMAGE_AT, fs.DISK_BYTES) == d.TREE[fs.IMAGE_AT], "the disk changed"


# ---- what it deletes -----------------------------------------------------------------------------------

@pytest.mark.parametrize("name,path,chain", (
    ("SHORT", "A:\\SHORT.TXT", (fs.SHORT_CLUSTER,)),
    ("SPAN", "a:\\span.dat", tuple(range(fs.SPAN_CLUSTER, fs.SPAN_CLUSTER + fs.SPAN_CLUSTERS))),
))
def test_fdelete_marks_the_entry_and_frees_its_chain_on_the_disk(name, path, chain):
    result = _fdelete(path)
    assert result.info["ret"] == 0
    assert _root_entry(result, name)[0] == fs.DIRENT_DELETED
    assert _root_entry(result, name)[1:] == d.ROOT[d.ROOT_INDEX[name]][1:]
    fat = io.fat_entries_after(result)
    assert [fat[cluster] for cluster in chain] == [0] * len(chain)


def test_fdelete_two_levels_down():
    """DEEP.TXT, in INNER's cluster: the mark lands there, not in the root."""
    result = _fdelete("A:\\SUBDIR\\INNER\\DEEP.TXT")
    assert result.info["ret"] == 0
    assert result.cluster_entry(d.INNER_CLUSTER, d.DOT_ENTRIES)[0] == fs.DIRENT_DELETED


def test_fdelete_through_a_child_list_three_long():
    result = _fdelete("A:\\SUBDIR\\NOTE.TXT", fo.walked_root())
    assert result.cluster_entry(fs.SUBDIR_CLUSTER, d.DOT_ENTRIES + 1)[0] == fs.DIRENT_DELETED
    assert result.word(fs.ROOT_OFD_AT + fs.OFD_FLAGS) == 0, "the root was searched"


# ---- an open file --------------------------------------------------------------------------------------
# SHORT.TXT open — the SECOND OFD on the root's list, behind SPAN.DAT's — through a handle record.
OPEN_BEHIND_SPAN = {**ff.open_entry("SPAN", io.OTHER_OFD_AT, link=io.OFD_AT), **ff.open_entry("SHORT", io.OFD_AT),
                    **ff.root_files(io.OTHER_OFD_AT)}


def test_a_file_another_process_has_open_is_eaccdn_and_left_on_the_disk():
    result = _fdelete("A:\\SHORT.TXT", {**OPEN_BEHIND_SPAN, **ff.handle_naming(io.OFD_AT, owner=ff.SOMEBODY_ELSE)})
    assert result.info["ret"] == fo.EACCDN
    _assert_nothing_deleted(result)
    assert ff.files_after(result) == [io.OTHER_OFD_AT, io.OFD_AT]


def test_a_file_the_caller_has_open_is_closed_and_deleted():
    result = _fdelete("A:\\SHORT.TXT", {**OPEN_BEHIND_SPAN, **ff.handle_naming(io.OFD_AT)})
    assert result.info["ret"] == 0
    assert _root_entry(result, "SHORT")[0] == fs.DIRENT_DELETED
    assert ff.files_after(result) == [io.OTHER_OFD_AT], "the caller's OFD was not closed"


# ---- what it refuses -------------------------------------------------------------------------------------

def test_a_read_only_file_is_eaccdn_before_anything_is_touched():
    result = _fdelete("A:\\EMPTY.BIN")
    assert result.info["ret"] == fo.EACCDN
    _assert_nothing_deleted(result)


@pytest.mark.parametrize("path,why", (
    ("A:\\NOPE.TXT", "a name the directory has not got"),
    ("A:\\NOPE\\SHORT.TXT", "a DIRECTORY the path has not got — EFILNF too"),
    ("A:\\SUBDIR", "a subdirectory: the search attribute has not got its bit"),
))
def test_a_miss_is_efilnf(path, why):
    result = _fdelete(path)
    assert result.info["ret"] == fo.EFILNF, why
    _assert_nothing_deleted(result)


# ---- through the dispatcher -------------------------------------------------------------------------

def test_a_dispatched_fdelete_runs_the_leaf():
    result = fo.dispatch(FDELETE, gemdos.long_words(fo.NAME_AT), "A:\\SHORT.TXT")
    assert result.info["ret"] == 0
    assert _root_entry(result, "SHORT")[0] == fs.DIRENT_DELETED


# ---- the registry ------------------------------------------------------------------------------------

def _register_all():
    fo.register("Fdelete, a three-cluster file", FDELETE, (fo.NAME_AT,), "A:\\SPAN.DAT")
    fo.register("Fdelete, open by another process", FDELETE, (fo.NAME_AT,), "A:\\SHORT.TXT",
                {**OPEN_BEHIND_SPAN, **ff.handle_naming(io.OFD_AT, owner=ff.SOMEBODY_ELSE)})


_register_all()
