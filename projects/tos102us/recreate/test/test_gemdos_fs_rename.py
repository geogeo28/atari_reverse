r"""`Frename` ($56, `$fc7af0`) — `src/gemdos/fs_rename.c` — over `test/fs_create.py`'s tree, entered at its
own address and through the dispatcher.

    $fc7b00  bsr $fc6d14          the NEW name searched for (attribute 0, widened to 0x21, no DTA):
                                  found is EACCDN — a hidden, system or directory entry is not seen
    $fc7b1a  bsr $fc696c  x2      both paths' directories (EPTHNF), then their DMDs' drive words
                                  compared (ENSAME)
    $fc7b72  bsr $fc75f2          `Fopen(old, 2)`: its error is the answer
    $fc7b8c  ...                  the entry through the open file's directory OFD:
               same DND           the new FCB name written over the entry's eleven name bytes
               another DND        `$e5` over the entry (its chain NOT freed), its ten tail bytes kept,
    $fc7c22  bsr $fc719a          `Fcreate(new, attr)` — its answer not looked at — the tail written
    $fc7c6c  bsr $fc56c6          over the new entry, the new OFD made clean, closed, its directory closed
    $fc7cac  bsr $fc56c6          `Fclose(old)` (a negative answer is the answer), the directory closed

NOTHING HERE POISONS, for `gemdos_fs.run`'s reasons: every run reaches the BIOS through the cache.
"""
import pytest

from harness import BASE_IMAGE, addrs

import fs_create as fc
import fs_dir as d
import fs_file as ff
import fs_io as io
import fs_open as fo
import gemdos
import gemdos_fs as fs
import gemdos_process as process

FRENAME = fs.FRENAME
EACCDN, EPTHNF, ENSAME = fs.GEMDOS_EACCDN, fs.GEMDOS_EPTHNF, fs.GEMDOS_ENSAME
EFILNF, ENHNDL = process.GEMDOS_EFILNF, process.GEMDOS_ENHNDL
DRIVE_B = io.DRIVE + 1
# The ABI's unused first word: a value nothing else stages, so a core that read it would show.
RESERVED = 0x5A5A

# The NEW path's text, in a band of its own just below the user buffer — the OLD one is `fs_dir`'s.
NEW_AT = fs.SPAN.claim(fs.USER_AT - d.TEXT_BYTES, d.TEXT_BYTES, "test/test_gemdos_fs_rename.py: the new path")
VALUES = (RESERVED, d.TEXT_AT, NEW_AT)


def _new_text(value):
    raw = value.encode("latin-1") + b"\0"
    return {NEW_AT: raw + bytes([fs.SLACK_FILL]) * (d.TEXT_BYTES - len(raw))}


def _pokes(old, new, extra=None, disk=None):
    return fs.leaf_pokes(FRENAME, VALUES, fc.staged(old, {**_new_text(new), **(extra or {})}, disk))


def _frename(old, new, extra=None, disk=None):
    return io.run(FRENAME.entry, fs.leaf_glue(FRENAME, VALUES), _pokes(old, new, extra, disk))


def _root_entry(name):
    return fc.ROOT[fc.ROOT_INDEX[name]]


def _renamed(entry, name, extension=""):
    return fs.fcb_name(name, extension) + entry[fs.DIRENT_NAME_BYTES:]


def _deleted(entry):
    return bytes([fs.DIRENT_DELETED]) + entry[1:]


def _assert_nothing_changed(result):
    assert result.after(fs.IMAGE_AT, fs.DISK_BYTES) == fc.TREE[fs.IMAGE_AT], "the disk changed"
    assert process.descriptor(result.final, ff.A_HANDLE).owner == 0, "a handle was left open"


def _assert_handles_released(result, *handles):
    for handle in handles:
        assert process.descriptor(result.final, handle) == process.Descriptor(
            process.descriptor_at(handle), 0, 0, 0), f"handle {handle} not given back"


# ---- in place --------------------------------------------------------------------------------------

def test_a_rename_in_the_root_rewrites_only_the_name():
    result = _frename("A:\\SHORT.TXT", "A:\\RENAMED.TXT")
    assert result.info["ret"] == 0
    assert result.root_entry(fc.ROOT_INDEX["SHORT"]) == _renamed(_root_entry("SHORT"), "RENAMED", "TXT")
    assert io.fat_entries_after(result) == fc.TREE_FAT
    _assert_handles_released(result, ff.A_HANDLE)
    assert ff.files_after(result) == [], "the file's OFD is still on the root's list"


def test_a_rename_two_levels_down_through_a_child_list_three_long():
    """INNER's DEEP.TXT: both walks cross the root's list to SUBDIR, and the name is rewritten in
    INNER's cluster."""
    result = _frename("A:\\SUBDIR\\INNER\\DEEP.TXT", "A:\\SUBDIR\\INNER\\SHALLOW.X", fo.walked_root())
    assert result.info["ret"] == 0
    deep = d.DIRECTORIES[1][1][d.DOT_ENTRIES]
    assert result.cluster_entry(d.INNER_CLUSTER, d.DOT_ENTRIES) == _renamed(deep, "SHALLOW", "X")


# ---- a move --------------------------------------------------------------------------------------

def test_a_move_hands_the_chain_to_the_new_entry():
    """SPAN.DAT into SUBDIR: the root's entry is `$e5` with everything else kept, and SUBDIR's end entry
    becomes MOVED.DAT with SPAN's attribute, time, date, first cluster and length — the clock `Fcreate`
    stamped is overwritten, and not one FAT entry moves."""
    result = _frename("A:\\SPAN.DAT", "A:\\SUBDIR\\MOVED.DAT")
    assert result.info["ret"] == 0
    assert result.root_entry(fc.ROOT_INDEX["SPAN"]) == _deleted(_root_entry("SPAN"))
    assert result.cluster_entry(fs.SUBDIR_CLUSTER, d.DOT_ENTRIES + 2) == _renamed(_root_entry("SPAN"), "MOVED", "DAT")
    assert io.fat_entries_after(result) == fc.TREE_FAT
    _assert_handles_released(result, ff.A_HANDLE, ff.ANOTHER_HANDLE)


def test_a_move_into_the_root_takes_its_first_free_slot():
    """NOTE.TXT out of SUBDIR: `Fcreate` puts it in GONE.OLD's deleted slot."""
    result = _frename("A:\\SUBDIR\\NOTE.TXT", "A:\\NOTE.TXT")
    assert result.info["ret"] == 0
    note = d.DIRECTORIES[0][1][d.DOT_ENTRIES + 1]
    assert result.cluster_entry(fs.SUBDIR_CLUSTER, d.DOT_ENTRIES + 1) == _deleted(note)
    assert result.root_entry(fc.ROOT_INDEX["GONE"]) == note


def test_a_move_carries_the_attribute_byte():
    """SECRET.HID is hidden: `Fcreate` is handed the byte, and the moved entry is hidden too."""
    result = _frename("A:\\SECRET.HID", "A:\\SUBDIR\\SECRET.HID")
    assert result.info["ret"] == 0
    moved = result.cluster_entry(fs.SUBDIR_CLUSTER, d.DOT_ENTRIES + 2)
    assert moved == _root_entry("SECRET")
    assert moved[fs.DIRENT_ATTR] == fs.GEMDOS_ATTR_HIDDEN


# ---- the new name already there --------------------------------------------------------------------

@pytest.mark.parametrize("old,new,why", (
    ("A:\\SHORT.TXT", "A:\\SPAN.DAT", "a file of the new name"),
    ("A:\\SHORT.TXT", "A:\\SHORT.TXT", "the same name"),
    ("A:\\SHORT.TXT", "A:\\EMPTY.BIN", "a READ-ONLY file of the new name: the widened attribute sees it"),
    ("A:\\NOPE.TXT", "A:\\SHORT.TXT", "the new name is looked for FIRST: a missing old name never asked about"),
))
def test_a_new_name_that_is_there_is_eaccdn_and_nothing_moves(old, new, why):
    result = _frename(old, new)
    assert result.info["ret"] == EACCDN, why
    _assert_nothing_changed(result)


def test_in_place_onto_a_hidden_name_makes_two_entries_of_it():
    """The search for the new name does not see a HIDDEN file: SHORT.TXT becomes a second SECRET.HID."""
    result = _frename("A:\\SHORT.TXT", "A:\\SECRET.HID")
    assert result.info["ret"] == 0
    assert result.root_entry(fc.ROOT_INDEX["SHORT"]) == _renamed(_root_entry("SHORT"), "SECRET", "HID")
    assert result.root_entry(fc.ROOT_INDEX["SECRET"]) == _root_entry("SECRET")


def test_in_place_onto_a_directory_name_makes_a_file_of_the_same_name():
    result = _frename("A:\\SHORT.TXT", "A:\\BIG")
    assert result.info["ret"] == 0
    assert result.root_entry(fc.ROOT_INDEX["SHORT"]) == _renamed(_root_entry("SHORT"), "BIG")
    assert result.root_entry(fc.ROOT_INDEX["BIG"]) == _root_entry("BIG")


def test_a_move_onto_a_system_file_replaces_it():
    """KERNEL.SYS is a system file the search does not see; `Fcreate` DELETES it and the moved entry
    lands in its slot."""
    result = _frename("A:\\SUBDIR\\NOTE.TXT", "A:\\KERNEL.SYS")
    assert result.info["ret"] == 0
    note = d.DIRECTORIES[0][1][d.DOT_ENTRIES + 1]
    assert result.root_entry(fc.ROOT_INDEX["KERNEL"]) == _renamed(note, "KERNEL", "SYS")


# ---- refusals ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("old,new,answer,why", (
    ("A:\\NOPE\\X.TXT", "A:\\NEW.TXT", EPTHNF, "the old path's directory is not there"),
    ("A:\\SHORT.TXT", "A:\\NOPE\\X.TXT", EPTHNF, "...nor the new one's"),
    ("A:\\NOPE.TXT", "A:\\NEW.TXT", EFILNF, "`Fopen`'s: no such file"),
    ("A:\\SUBDIR", "A:\\NEW", EFILNF, "`Fopen`'s: a directory is not a file"),
    ("A:\\EMPTY.BIN", "A:\\NEW.BIN", EACCDN, "`Fopen`'s: a read-only file, opened read-write"),
))
def test_a_refusal_changes_nothing(old, new, answer, why):
    result = _frename(old, new)
    assert result.info["ret"] == answer, why
    _assert_nothing_changed(result)


def test_two_drives_are_ensame():
    """B: is logged in on the way (its DMD out of the pool, drive word 1) and A:'s is 0."""
    result = _frename("A:\\SHORT.TXT", "B:\\NEW.TXT")
    assert result.info["ret"] == ENSAME
    assert result.after(fs.IMAGE_AT, fs.DISK_BYTES) == fc.TREE[fs.IMAGE_AT]
    assert result.long(fs.dmd_slot(DRIVE_B)) not in (0, fs.DMD_AT), "B: was not logged in on a DMD of its own"


def test_no_handle_for_the_old_file_is_enhndl():
    result = _frename("A:\\SHORT.TXT", "A:\\NEW.TXT", process.full_table_poke(ff.SOMEBODY_ELSE))
    assert result.info["ret"] == ENHNDL
    assert result.after(fs.IMAGE_AT, fs.DISK_BYTES) == fc.TREE[fs.IMAGE_AT]


# ---- `Fcreate` refusing, mid-move ----------------------------------------------------------------------
# `Fcreate`'s negative answer is taken for a handle. `$fc51c0` reads a standard handle below 6 as the
# `p_uft` byte it indexes — and a NEGATIVE one indexes BELOW `p_uft`, into `p_tlen`: EACCDN (-36) its
# high byte, ENHNDL (-35) the next. The running program's text is under 64 KB, so both bytes are 0, and a
# 0 names handle RECORD 0 — which is the OLD file's, `Fopen` having just taken the first free record. So
# the saved tail is written back over the OLD entry it came from, the old OFD is made clean, `Fclose` of the
# negative handle does nothing, and the rename answers 0: the file has LOST ITS NAME, and its chain is
# held by nothing.
SPAN_CHAIN = tuple(range(fs.SPAN_CLUSTER, fs.SPAN_CLUSTER + fs.SPAN_CLUSTERS))


@pytest.mark.parametrize("error", (EACCDN, ENHNDL))
def test_a_refused_handle_reads_a_zero_byte_of_p_tlen(error):
    """The claim the two cases below stand on, about the captured machine."""
    at = gemdos.BASEPAGE + addrs.BASEPAGE_HANDLES + (error - (fs.LONG_MASK + 1))
    assert gemdos.BASEPAGE + addrs.BASEPAGE_TLEN <= at < gemdos.BASEPAGE + addrs.BASEPAGE_DBASE
    assert BASE_IMAGE[at] == 0


def _assert_the_file_lost_its_name(result, handle=ff.A_HANDLE):
    """...where `handle` is the record `Fopen` took for the moved file."""
    assert result.info["ret"] == 0
    assert result.root_entry(fc.ROOT_INDEX["SPAN"]) == _deleted(_root_entry("SPAN"))
    fat = io.fat_entries_after(result)
    assert [fat[cluster] for cluster in SPAN_CHAIN] == [fc.TREE_FAT[cluster] for cluster in SPAN_CHAIN], \
        "the chain was freed"
    _assert_handles_released(result, handle)


def test_a_move_onto_a_directory_s_name_loses_the_file():
    """INNER is a directory of SUBDIR's that the search for the new name does not see, and `Fcreate`
    refuses it (EACCDN) — nothing is made in SUBDIR."""
    result = _frename("A:\\SPAN.DAT", "A:\\SUBDIR\\INNER")
    _assert_the_file_lost_its_name(result)
    assert result.cluster_entry(fs.SUBDIR_CLUSTER, d.DOT_ENTRIES + 2) == bytes(fs.DIRENT_BYTES)


def test_no_handle_for_the_new_file_leaves_an_empty_entry_and_loses_the_old():
    """Every record owned but record 0: `Fopen` takes it, and `Fcreate` makes MOVED.DAT on the disk
    before its open fails (ENHNDL) — an empty file with the clock's stamp, which nothing then fills."""
    (table_at, owned), = process.full_table_poke(ff.SOMEBODY_ELSE).items()
    table = {table_at: bytes(addrs.GEMDOS_HANDLE_STRIDE) + owned[addrs.GEMDOS_HANDLE_STRIDE:]}
    result = _frename("A:\\SPAN.DAT", "A:\\SUBDIR\\MOVED.DAT", table)
    _assert_the_file_lost_its_name(result)
    assert result.cluster_entry(fs.SUBDIR_CLUSTER, d.DOT_ENTRIES + 2) == fc.new_entry("MOVED", "DAT")


# ...and the same refusal with RECORD 0 HELD BY ANOTHER OPEN FILE, which is where the handle lands whoever
# owns it. Proved as the sequence a program makes, each run from where the one before ended: SHORT.TXT
# opened (record 0) and written through (its OFD dirty), then SPAN.DAT moved onto INNER's name — `Fopen`
# takes record 1 for it, and the refused `Fcreate`'s handle names record 0. So SPAN's tail is written over
# SHORT.TXT's entry: SHORT.TXT keeps its name and takes SPAN's time, date, chain and length, its OFD is
# made CLEAN under the program's open handle, and its directory is closed. SPAN.DAT loses its name as
# before. (With `p_tlen` of 64 KB or more the byte is not 0 and the handle names whatever record it picks —
# the captured program's is under that, so that arm is not reached here.)
SHORT_WRITTEN = fs.SHORT_BYTES * 2


def test_a_refused_move_writes_its_tail_into_another_open_file_s_entry():
    opened = io.run(fs.FOPEN.entry, fs.leaf_glue(fs.FOPEN, (d.TEXT_AT, fs.OPEN_MODE_READ_WRITE)),
                    fs.leaf_pokes(fs.FOPEN, (d.TEXT_AT, fs.OPEN_MODE_READ_WRITE),
                                  fc.staged("A:\\SHORT.TXT", _new_text("A:\\SUBDIR\\INNER"))))
    assert opened.info["ret"] == ff.A_HANDLE, "SHORT.TXT did not take record 0"
    written = _then(fs.FWRITE, (ff.A_HANDLE, SHORT_WRITTEN, fs.USER_AT), opened)
    short_ofd = process.descriptor(written.final, ff.A_HANDLE).named
    assert fs.ofd_field(written.final, short_ofd, "flags") & fs.OFD_DIRTY
    moved = io.run(FRENAME.entry, fs.leaf_glue(FRENAME, VALUES),
                   fs.leaf_pokes(FRENAME, VALUES, {**fs.continued(written), **d.text("A:\\SPAN.DAT")}))
    _assert_the_file_lost_its_name(moved, ff.ANOTHER_HANDLE)
    short, span = _root_entry("SHORT"), _root_entry("SPAN")
    assert moved.root_entry(fc.ROOT_INDEX["SHORT"]) == short[:fs.DIRENT_TIME] + span[fs.DIRENT_TIME:]
    assert not fs.ofd_field(moved.final, short_ofd, "flags") & fs.OFD_DIRTY, "SHORT.TXT's OFD left dirty"
    assert process.descriptor(moved.final, ff.A_HANDLE).named == short_ofd, "the program's handle was closed"


# ---- a file the caller already has open --------------------------------------------------------------
# `Frename` opens the file AGAIN, and a second open copies the first OFD's time..length but not its
# flags: the move's handle is clean whatever the first one holds. So a file written through a handle
# the caller still has open moves with the length ON THE DISK, and the first handle's close writes its
# own length back into the DELETED entry it still points at.

def _then(leaf, values, previous):
    """`leaf` run from where `previous` ended — `gemdos_fs.continued`."""
    return io.run(leaf.entry, fs.leaf_glue(leaf, values), fs.leaf_pokes(leaf, values, fs.continued(previous)))


def test_a_write_through_a_handle_still_open_is_lost_by_the_move():
    grown = fs.SHORT_BYTES * 2
    opened = io.run(fs.FOPEN.entry, fs.leaf_glue(fs.FOPEN, (d.TEXT_AT, fs.OPEN_MODE_READ_WRITE)),
                    fs.leaf_pokes(fs.FOPEN, (d.TEXT_AT, fs.OPEN_MODE_READ_WRITE),
                                  fc.staged("A:\\SHORT.TXT", _new_text("A:\\SUBDIR\\MOVED.TXT"))))
    assert opened.info["ret"] == ff.A_HANDLE
    written = _then(fs.FWRITE, (ff.A_HANDLE, grown, fs.USER_AT), opened)
    assert written.info["ret"] == grown
    moved = _then(FRENAME, VALUES, written)
    assert moved.info["ret"] == 0
    entry = moved.cluster_entry(fs.SUBDIR_CLUSTER, d.DOT_ENTRIES + 2)
    assert entry == _renamed(_root_entry("SHORT"), "MOVED", "TXT"), "the move took the length on the disk"
    closed = _then(fs.FCLOSE, (ff.A_HANDLE,), moved)
    assert closed.info["ret"] == 0
    stale = closed.root_entry(fc.ROOT_INDEX["SHORT"])
    assert stale[0] == fs.DIRENT_DELETED
    assert int.from_bytes(stale[fs.DIRENT_FILELN:], "little") == grown, "the close wrote into the deleted entry"
    assert closed.cluster_entry(fs.SUBDIR_CLUSTER, d.DOT_ENTRIES + 2) == entry


# ---- through the dispatcher ------------------------------------------------------------------------

def test_a_dispatched_frename_runs_the_leaf():
    words = (RESERVED, *gemdos.long_words(d.TEXT_AT), *gemdos.long_words(NEW_AT))
    result = io.dispatch_slice(FRENAME, words, fc.staged("A:\\SHORT.TXT", _new_text("A:\\RENAMED.TXT")))
    assert result.info["ret"] == 0
    assert result.root_entry(fc.ROOT_INDEX["SHORT"]) == _renamed(_root_entry("SHORT"), "RENAMED", "TXT")


# ---- the registry ------------------------------------------------------------------------------------

def _register_all():
    io.register("Frename, in place", FRENAME.entry, _pokes("A:\\SHORT.TXT", "A:\\RENAMED.TXT"))
    io.register("Frename, a move", FRENAME.entry, _pokes("A:\\SPAN.DAT", "A:\\SUBDIR\\MOVED.DAT"))


_register_all()
