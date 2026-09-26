r"""`$fc71b6` gemdos_create(name, attr) and `Fcreate` ($3c, `$fc719a`) — `src/gemdos/fs_create.c` — over
`test/fs_create.py`'s tree.

    $fc71d2  bsr $fc696c          the directory the path's last component is in (EPTHNF: none)
    $fc71ea  bsr $fc7e52          ...and that component not "", "." or ".." (EPTHNF)
    $fc722c  bsr $fc663c          an entry of the name, any attribute: read-only or a directory is
    $fc725e  bsr $fc7824          EACCDN, anything else DELETED — its chain freed, its slot `$e5`
    $fc7280  bsr $fc663c          a free slot ("\xe5"), from that slot or from 0; none: EACCDN for a
    $fc72a2  bsr $fc60f2          negative cluster (the root) or a full disk, else a cluster added,
    $fc72b4  bsr $fc70f6          zeroed, and the search run again from 0
    $fc72d2  bsr $fc5d28 ...      the entry written in the cache, its name through the OFD, flushed
    $fc7394  bsr $fc6f5c          ...and opened: the handle, its OFD marked dirty

NOTHING HERE POISONS, for `gemdos_fs.run`'s reasons: every run reaches the BIOS through the cache.
"""
import pytest

import fs_create as fc
import fs_dir as d
import fs_file as ff
import fs_io as io
import fs_records as records
import gemdos
import gemdos_fs as fs
import gemdos_process as process

EPTHNF, EACCDN = fs.GEMDOS_EPTHNF, fs.GEMDOS_EACCDN
FILE_ATTR = fs.ATTR_NONE
CREATE, FCREATE = fs.CREATE, fs.FCREATE


def _create_pokes(path, attr, pokes=None, disk=None):
    return fs.leaf_pokes(CREATE, (d.TEXT_AT, attr), fc.staged(path, pokes, disk))


def _create(path, attr=FILE_ATTR, pokes=None, disk=None):
    return io.run(CREATE.entry, fs.leaf_glue(CREATE, (d.TEXT_AT, attr)), _create_pokes(path, attr, pokes, disk))


def _opened_ofd(result, handle):
    return process.descriptor(result.final, handle).named


def _assert_opened(result, index, entry, dnd=fs.ROOT_DND_AT):
    """A handle to a fresh OFD over the new entry at `index` of `dnd`'s directory — dirty, first on
    the directory's list of open files — and the entry itself on the disk."""
    handle = result.info["ret"]
    assert handle == ff.A_HANDLE, "the first free handle record"
    ofd = _opened_ofd(result, handle)
    assert result.long(dnd + fs.DND_FILES) == ofd
    assert fs.ofd_field(result.final, ofd, "dirpos") == index * fs.DIRENT_BYTES
    assert fs.ofd_field(result.final, ofd, "flags") & fs.OFD_DIRTY
    assert process.descriptor(result.final, handle).owner == gemdos.BASEPAGE
    if dnd == fs.ROOT_DND_AT:
        assert result.root_entry(index) == entry


# ---- a new entry ---------------------------------------------------------------------------------------

def test_a_new_file_in_the_root_reuses_the_deleted_slot():
    """GONE.OLD's slot is the first free one; the new entry is the clock in the DISK's order."""
    result = _create("A:\\NEW.TXT")
    _assert_opened(result, fc.ROOT_INDEX["GONE"], fc.new_entry("NEW", "TXT"))


def test_a_root_with_nothing_deleted_takes_the_end_of_directory_entry():
    result = _create("A:\\NEW.TXT", disk=fc.tree(fc.LIVE_ROOT))
    _assert_opened(result, len(fc.LIVE_ROOT), fc.new_entry("NEW", "TXT"))


def test_a_new_file_two_levels_down():
    """INNER's `.`, `..`, DEEP.TXT and LEAF, then the end entry: the new one lands there."""
    result = _create("A:\\SUBDIR\\INNER\\NEW.TXT")
    handle = result.info["ret"]
    assert handle == ff.A_HANDLE
    inner = fs.ofd_field(result.final, _opened_ofd(result, handle), "dir_dnd")
    assert result.after(inner + fs.DND_NAME, fs.DIRENT_NAME_BYTES) == fs.fcb_name("INNER")
    assert result.cluster_entry(d.INNER_CLUSTER, d.DOT_ENTRIES + 2) == fc.new_entry("NEW", "TXT")


@pytest.mark.parametrize("attr,why", (
    (fs.GEMDOS_ATTR_READ_ONLY, "read-only: the open is read-only too"),
    (fs.GEMDOS_ATTR_HIDDEN | fs.GEMDOS_ATTR_SUBDIR, "create itself does not mask the subdirectory bit"),
    (fs.ARGUMENT_HIGH_BYTE | fs.GEMDOS_ATTR_SYSTEM, "only the attribute's LOW byte is written"),
))
def test_the_attribute_s_low_byte_is_the_entry_s(attr, why):
    result = _create("A:\\NEW.TXT", attr)
    entry = result.root_entry(fc.ROOT_INDEX["GONE"])
    assert entry[fs.DIRENT_ATTR] == attr & 0xFF, why
    mode = fs.ofd_field(result.final, _opened_ofd(result, result.info["ret"]), "mode")
    assert mode == (fs.OPEN_MODE_READ if attr & fs.GEMDOS_ATTR_READ_ONLY else fs.OPEN_MODE_READ_WRITE), why


def test_a_reused_slot_s_reserved_bytes_are_cleared():
    """A deleted entry keeps whatever DOS left in its ten reserved bytes: `create` clears each one."""
    gone = fs.dirent_bytes("GONE", "OLD", deleted=True, reserved=fs.SLACK_FILL)
    root = [gone if row[0] == "GONE" else entry for row, entry in zip(fc.ROOT_ROWS, fc.ROOT)]
    result = _create("A:\\NEW.TXT", disk=fc.tree(root))
    _assert_opened(result, fc.ROOT_INDEX["GONE"], fc.new_entry("NEW", "TXT"))


# ---- an entry of the name already there ---------------------------------------------------------------

def test_an_existing_file_is_deleted_and_its_slot_reused():
    """SPAN.DAT's three clusters go back to the FAT and the new, empty SPAN.DAT is in its slot."""
    result = _create("A:\\SPAN.DAT")
    _assert_opened(result, fc.ROOT_INDEX["SPAN"], fc.new_entry("SPAN", "DAT"))
    fat = io.fat_entries_after(result)
    assert [fat[cluster] for cluster in range(fs.SPAN_CLUSTER, fs.SPAN_CLUSTER + fs.SPAN_CLUSTERS)] == [0, 0, 0]


def test_a_volume_label_of_the_name_is_deleted_like_a_file():
    """The search is for ANY attribute and only read-only and subdirectory refuse: `STAGEDDS` names
    the volume label (its FCB name is the stem's first eight), which is deleted and replaced by a plain
    file."""
    result = _create("A:\\STAGEDDS")
    _assert_opened(result, fc.ROOT_INDEX["STAGEDDSK"], fc.new_entry("STAGEDDS"))


@pytest.mark.parametrize("path,why", (
    ("A:\\EMPTY.BIN", "a read-only file"),
    ("A:\\SUBDIR", "a subdirectory"),
))
def test_a_read_only_or_directory_entry_is_eaccdn_and_nothing_is_written(path, why):
    result = _create(path)
    assert result.info["ret"] == EACCDN, why
    assert result.after(fs.IMAGE_AT, fs.DISK_BYTES) == fc.TREE[fs.IMAGE_AT], why


def test_a_file_another_process_has_open_gets_a_second_entry_of_the_same_name():
    """`$fc7824` refuses the delete (EACCDN) and `create` DOES NOT LOOK: the free-slot search starts at
    the still-live entry, passes it, and the new SPAN.DAT goes in the next free slot — GONE.OLD's."""
    pokes = {**ff.open_entry("SPAN", io.OFD_AT), **ff.root_files(io.OFD_AT),
             **ff.handle_naming(io.OFD_AT, ff.A_HANDLE, ff.SOMEBODY_ELSE)}
    result = _create("A:\\SPAN.DAT", pokes=pokes)
    assert result.info["ret"] == ff.ANOTHER_HANDLE
    assert result.root_entry(fc.ROOT_INDEX["SPAN"]) == d.ROOT[d.ROOT_INDEX["SPAN"]]
    assert result.root_entry(fc.ROOT_INDEX["GONE"]) == fc.new_entry("SPAN", "DAT")


# ---- names and paths refused ------------------------------------------------------------------------

@pytest.mark.parametrize("path,why", (
    ("A:\\", "an empty last component"),
    ("A:\\.", "`.`"),
    ("A:\\SUBDIR\\..", "`..`"),
    ("A:\\NOPE\\NEW.TXT", "a directory that is not there"),
))
def test_a_path_with_no_name_or_no_directory_is_epthnf(path, why):
    result = _create(path)
    assert result.info["ret"] == EPTHNF, why


# ---- a directory with no free slot ----------------------------------------------------------------------

def test_a_full_root_cannot_grow_and_is_eaccdn():
    """Thirty-two entries, none deleted and no end entry: the search runs off the root's length, and a
    root's cluster is a NEGATIVE pseudo-cluster, which `create` will not extend."""
    result = _create("A:\\NEW.TXT", disk=fc.tree(fc.FULL_ROOT))
    assert result.info["ret"] == EACCDN
    assert io.fat_entries_after(result) == fc.TREE_FAT


def test_a_full_subdirectory_grows_by_a_zeroed_cluster():
    """FULL fills cluster 13 with no end entry. A free cluster is linked on, zeroed, and the search
    runs again FROM THE START — to the new cluster's first entry, 32."""
    result = _create("A:\\FULL\\NEW.TXT")
    assert result.info["ret"] == ff.A_HANDLE
    fat = io.fat_entries_after(result)
    grown = fat[d.FULL_CLUSTER]
    assert grown in fc.FREE_CLUSTERS and fat[grown] == fs.FAT12_END_OF_CHAIN
    assert result.cluster_entry(grown, 0) == fc.new_entry("NEW", "TXT")
    assert all(result.cluster_entry(grown, index) == bytes(fs.DIRENT_BYTES)
               for index in range(1, d.ENTRIES_PER_CLUSTER))


def test_a_full_subdirectory_on_a_full_disk_is_eaccdn():
    result = _create("A:\\FULL\\NEW.TXT", disk=fc.tree(fat=fc.full_disk()))
    assert result.info["ret"] == EACCDN


# ---- the open ---------------------------------------------------------------------------------------

def test_no_free_handle_is_enhndl_after_the_entry_is_made():
    """`$fc6f5c` answers ENHNDL — and the entry is already on the disk, with nothing open on it."""
    result = _create("A:\\NEW.TXT", pokes=process.full_table_poke(ff.SOMEBODY_ELSE))
    assert result.info["ret"] == process.GEMDOS_ENHNDL
    assert result.root_entry(fc.ROOT_INDEX["GONE"]) == fc.new_entry("NEW", "TXT")


def test_a_directory_with_no_ofd_and_a_spent_pool_is_ensmem():
    """SUBDIR's DND already on the root's list, with no OFD: `create` makes one, and the pool has none."""
    pokes = {**d.root(child=d.SUBDIR_DND_AT, scanned=d.position_of(0)), **d.subdir_dnd(), **records.pool_spent()}
    result = _create("A:\\SUBDIR\\NEW.TXT", pokes=pokes)
    assert result.info["ret"] == process.GEMDOS_ENSMEM


def test_a_spent_pool_reads_as_a_full_root():
    """The root's searches make a DND for every subdirectory they pass, and one that cannot is a MISS
    (`$fc663c` answers 0): the name is not found, no free slot is found, and the root cannot grow —
    EACCDN, with a deleted slot standing free."""
    result = _create("A:\\NEW.TXT", pokes=records.pool_spent())
    assert result.info["ret"] == EACCDN
    assert result.root_entry(fc.ROOT_INDEX["GONE"]) == fc.ROOT[fc.ROOT_INDEX["GONE"]]


# ---- Fcreate --------------------------------------------------------------------------------------------

def _fcreate(path, attr):
    return io.run(FCREATE.entry, fs.leaf_glue(FCREATE, (d.TEXT_AT, attr)),
                  fs.leaf_pokes(FCREATE, (d.TEXT_AT, attr), fc.staged(path)))


@pytest.mark.parametrize("attr,written", (
    (FILE_ATTR, FILE_ATTR),
    (fs.GEMDOS_ATTR_SUBDIR | fs.GEMDOS_ATTR_READ_ONLY, fs.GEMDOS_ATTR_READ_ONLY),
    (fs.ARGUMENT_HIGH_BYTE | fs.GEMDOS_ATTR_SUBDIR | fs.GEMDOS_ATTR_ARCHIVE, fs.GEMDOS_ATTR_ARCHIVE),
    (fs.ATTR_BIT_7 | fs.GEMDOS_ATTR_SUBDIR, fs.ATTR_BIT_7),
))
def test_fcreate_masks_the_subdirectory_bit_off(attr, written):
    result = _fcreate("A:\\NEW.TXT", attr)
    assert result.info["ret"] == ff.A_HANDLE
    assert result.root_entry(fc.ROOT_INDEX["GONE"])[fs.DIRENT_ATTR] == written


def test_a_dispatched_fcreate_of_a_file_runs_the_leaf():
    """Past the dispatcher's device-name arm, which "NEW.TXT" does not match, our dispatcher calls our leaf."""
    result = io.dispatch_slice(FCREATE, (*gemdos.long_words(d.TEXT_AT), FILE_ATTR), fc.staged("A:\\NEW.TXT"))
    _assert_opened(result, fc.ROOT_INDEX["GONE"], fc.new_entry("NEW", "TXT"))


# ---- the registry ------------------------------------------------------------------------------------

def _register_all():
    io.register("create, the root's deleted slot", CREATE.entry, _create_pokes("A:\\NEW.TXT", FILE_ATTR))
    io.register("create, over a three-cluster file", CREATE.entry, _create_pokes("A:\\SPAN.DAT", FILE_ATTR))
    io.register("create, a full subdirectory grown", CREATE.entry, _create_pokes("A:\\FULL\\NEW.TXT", FILE_ATTR))
    io.register("Fcreate, a new file", FCREATE.entry,
                fs.leaf_pokes(FCREATE, (d.TEXT_AT, FILE_ATTR), fc.staged("A:\\NEW.TXT")))


_register_all()
