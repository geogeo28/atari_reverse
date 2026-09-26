r"""`Fattrib` ($43, `$fc7678`) — a file's attribute byte, read or written in its entry — entered at its
own address and then through the dispatcher, over `test/fs_dir.py`'s tree with two more root entries
(`fs_open.ATTRIBUTE_TREE`: a subdirectory with the archive bit, a file whose byte has bit 7 set).

The name is searched under GEMDOS_ATTR_ANY_FILE, so a PLAIN subdirectory is EFILNF and a directory
reaches `Fattrib` only by also carrying one of the file bits. The byte is then moved one byte at a
time through the directory's OFD, 21 bytes behind where the search stopped, into or out of the
attribute ARGUMENT'S low byte; a write closes the directory (flag 2), flushing every buffer, and
nothing about the byte is checked. The answer is that byte sign-extended to a WORD over whatever the
read or the close left in D0's high half. A missing DIRECTORY is EPTHNF here — the one leaf of this
group that tells the two misses apart.

Unpoisoned, for `test_gemdos_fs_dir.py`'s reasons.
"""
import pytest

import fs_dir as d
import fs_file as ff
import fs_open as fo
import gemdos
import gemdos_fs as fs

FATTRIB = fs.FATTRIB
GET, SET = 0, 1
# Any non-zero flag word is a write (`tst.w 12(a6)`, $fc76da and $fc76f6).
SET_BY_ANOTHER_WORD = 0x0200
READ_ONLY = fs.GEMDOS_ATTR_READ_ONLY
# An attribute ARGUMENT whose high byte is not 0: only its low byte is the one written ($fc76fe
# `15(a6)`).
READ_ONLY_UNDER_A_HIGH_BYTE = fs.ARGUMENT_HIGH_BYTE | READ_ONLY
# A byte with bit 7 set, the subdirectory bit and the read-only one: nothing refuses writing it.
ANY_BYTE_AT_ALL = fs.ATTR_BIT_7 | fs.GEMDOS_ATTR_SUBDIR | READ_ONLY
# `Fattrib` does not look at an attribute argument on a read; this one is what the ROM's frame holds.
UNUSED = 0


def _fattrib(path, set_flag, attribute=UNUSED, extra=None, buffers=None):
    return fo.run(FATTRIB, (fo.NAME_AT, set_flag, attribute), path, extra, fo.ATTRIBUTE_TREE, buffers)


def _word(value):
    """What `ext.w d0` over a 0 high half answers for a byte `value`."""
    return value - 0x100 & fs.D0_LOW_WORD if value & 0x80 else value


def _attribute_on_disk(result, index):
    return result.root_entry(index)[fs.DIRENT_ATTR]


# ---- reading ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path,attribute,why", (
    ("A:\\SHORT.TXT", fs.ATTR_NONE, "a plain file"),
    ("A:\\EMPTY.BIN", READ_ONLY, "a read-only one"),
    ("A:\\HIGHBIT.ATR", fo.HIGH_BIT_ATTR, "a byte with bit 7 set, sign-extended into the word"),
    ("A:\\ARCHIVED", fs.GEMDOS_ATTR_SUBDIR | fs.GEMDOS_ATTR_ARCHIVE, "a directory, reached by its ARCHIVE bit"),
    ("A:\\SECRET.HID", fs.GEMDOS_ATTR_HIDDEN, "a hidden file: the search attribute has its bit"),
))
def test_fattrib_reads_the_attribute_byte(path, attribute, why):
    result = _fattrib(path, GET)
    assert result.info["ret"] == _word(attribute), why


def test_a_read_leaves_the_cache_unflushed():
    """No close on a read: the working cache's two dirty buffers are still dirty, and the disk is as
    staged (`fs_file.assert_nothing_flushed` compares against the base disk, not this tree's)."""
    result = _fattrib("A:\\SHORT.TXT", GET, buffers=ff.WORKING_CACHE)
    for index in (ff.DIRTY_FAT_BCB, ff.DIRTY_DATA_BCB):
        assert result.word(fs.bcb_at(index) + fs.BCB_DIRTY) == fs.BCB_MARKED_DIRTY
    assert result.after(fs.IMAGE_AT, fs.DISK_BYTES) == fo.ATTRIBUTE_TREE[fs.IMAGE_AT]


def test_fattrib_reads_two_levels_down():
    result = _fattrib("A:\\SUBDIR\\INNER\\LEAF", GET)
    assert result.info["ret"] == fo.EFILNF, "LEAF is a plain subdirectory"
    result = _fattrib("A:\\SUBDIR\\INNER\\DEEP.TXT", GET)
    assert result.info["ret"] == fs.ATTR_NONE


def test_fattrib_through_a_child_list_three_long():
    result = _fattrib("A:\\SUBDIR\\NOTE.TXT", GET, extra=fo.walked_root())
    assert result.info["ret"] == fs.ATTR_NONE
    assert result.word(fs.ROOT_OFD_AT + fs.OFD_FLAGS) == 0, "the root was searched"


# ---- writing ------------------------------------------------------------------------------------------

SHORT_AT, EMPTY_AT, ARCHIVED_AT = d.ROOT_INDEX["SHORT"], d.ROOT_INDEX["EMPTY"], fo.EXTRA_INDEX[fo.ARCHIVED_DIR]


@pytest.mark.parametrize("path,index,set_flag,attribute,written,why", (
    ("A:\\SHORT.TXT", SHORT_AT, SET, READ_ONLY, READ_ONLY, "a plain file made read-only"),
    ("A:\\EMPTY.BIN", EMPTY_AT, SET, fs.ATTR_NONE, fs.ATTR_NONE, "a read-only file made writable: nothing refuses it"),
    ("A:\\SHORT.TXT", SHORT_AT, SET_BY_ANOTHER_WORD, READ_ONLY, READ_ONLY, "any non-zero flag word writes"),
    ("A:\\SHORT.TXT", SHORT_AT, SET, READ_ONLY_UNDER_A_HIGH_BYTE, READ_ONLY, "only the argument's LOW byte is written"),
    ("A:\\SHORT.TXT", SHORT_AT, SET, ANY_BYTE_AT_ALL, ANY_BYTE_AT_ALL, "any byte at all, the subdirectory bit included"),
    ("A:\\ARCHIVED", ARCHIVED_AT, SET, fs.GEMDOS_ATTR_ARCHIVE, fs.GEMDOS_ATTR_ARCHIVE,
     "a directory's subdirectory bit cleared"),
))
def test_fattrib_writes_the_byte_and_the_close_puts_it_on_the_disk(path, index, set_flag, attribute, written, why):
    result = _fattrib(path, set_flag, attribute, buffers=ff.WORKING_CACHE)
    assert result.info["ret"] == _word(written), why
    assert _attribute_on_disk(result, index) == written, why
    ff.assert_every_buffer_flushed(result)


def test_fattrib_writes_two_levels_down():
    result = _fattrib("A:\\SUBDIR\\INNER\\DEEP.TXT", SET, READ_ONLY)
    assert result.info["ret"] == READ_ONLY
    assert result.cluster_entry(d.INNER_CLUSTER, d.DOT_ENTRIES)[fs.DIRENT_ATTR] == READ_ONLY


# ---- the two misses -------------------------------------------------------------------------------------

@pytest.mark.parametrize("path,error,why", (
    ("A:\\NOPE\\SHORT.TXT", fo.EPTHNF, "a directory the path has not got"),
    ("A:\\NOPE.TXT", fo.EFILNF, "a name the directory has not got"),
    ("A:\\SUBDIR", fo.EFILNF, "a PLAIN subdirectory: the search attribute has not got its bit"),
))
def test_a_miss(path, error, why):
    result = _fattrib(path, SET, READ_ONLY)
    assert result.info["ret"] == error, why
    assert result.after(fs.IMAGE_AT, fs.DISK_BYTES) == fo.ATTRIBUTE_TREE[fs.IMAGE_AT], why


# ---- through the dispatcher -------------------------------------------------------------------------

def test_a_dispatched_fattrib_runs_the_leaf():
    result = fo.dispatch(FATTRIB, (*gemdos.long_words(fo.NAME_AT), SET, READ_ONLY), "A:\\SHORT.TXT",
                         tree=fo.ATTRIBUTE_TREE)
    assert result.info["ret"] == READ_ONLY
    assert _attribute_on_disk(result, d.ROOT_INDEX["SHORT"]) == READ_ONLY


# ---- the registry ------------------------------------------------------------------------------------

def _register_all():
    fo.register("Fattrib, read", FATTRIB, (fo.NAME_AT, GET, UNUSED), "A:\\HIGHBIT.ATR", tree=fo.ATTRIBUTE_TREE)
    fo.register("Fattrib, write", FATTRIB, (fo.NAME_AT, SET, READ_ONLY), "A:\\SHORT.TXT", tree=fo.ATTRIBUTE_TREE,
                buffers=ff.WORKING_CACHE)


_register_all()
