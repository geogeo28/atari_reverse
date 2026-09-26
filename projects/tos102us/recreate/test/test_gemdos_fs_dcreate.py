r"""`Dcreate` ($39, `$fc73ce`) — `src/gemdos/fs_create.c` — over `test/fs_create.py`'s tree.

    $fc73de  bsr $fc71b6          the entry made with the subdirectory attribute, and opened
    $fc742a  read the entry back  through the holding directory, at the position the file OFD recorded
    $fc7440  bsr $fc65a2          a DND for it (ENSMEM), then $fc5c3c an OFD, stored on it (ENSMEM)
    $fc7478  bsr $fc60f2          ...and a first cluster allocated through that OFD — none: the file OFD
                                  closed and freed, its handle released, `Ddelete` of the path, EACCDN
    $fc74da  bsr $fc70f6          the cluster zeroed, `.` and `..` written into its first sector: the
                                  clock NOT turned round, `..` the holding directory's cluster or 0
    $fc758c  bcopy 50             the directory OFD over the file OFD, which is then closed (flags 6),
                                  freed, and its handle record released

THE CLOSE DROPS THE HOLDING DIRECTORY'S OTHER OPEN FILES. The copied OFD_LINK is the directory OFD's,
0, and the file OFD was the head of the holding directory's list, so the unlink stores 0 there.
"""
import struct

import fs_create as fc
import fs_dir as d
import fs_file as ff
import fs_io as io
import fs_records as records
import gemdos
import gemdos_fs as fs
import gemdos_memory as gm
import gemdos_process as process

EPTHNF, EACCDN = fs.GEMDOS_EPTHNF, fs.GEMDOS_EACCDN
DCREATE = fs.DCREATE
ROOT = fs.ROOT_DND_AT
NEW_SLOT = fc.ROOT_INDEX["GONE"]


def _pokes(path, pokes=None, disk=None):
    return fs.leaf_pokes(DCREATE, (d.TEXT_AT,), fc.staged(path, pokes, disk))


def _dcreate(path, pokes=None, disk=None):
    return io.run(DCREATE.entry, fs.leaf_glue(DCREATE, (d.TEXT_AT,)), _pokes(path, pokes, disk))


def _dot(name, cluster):
    """`.` or `..` as `Dcreate` writes it: the clock words in the 68000's order, stored as they are —
    which the disk reads BYTE-SWAPPED — the cluster in the disk's order, no length."""
    return fs.dirent_bytes(name, "", fs.GEMDOS_ATTR_SUBDIR, cluster, 0,
                           time=fs.as_stored(fc.CLOCK_TIME), date=fs.as_stored(fc.CLOCK_DATE))


def _new_directory(entry_bytes):
    """The cluster the new entry names, read off the entry on the disk."""
    return struct.unpack_from("<H", entry_bytes, fs.DIRENT_STRTCL)[0]


def _assert_released(result, handle=ff.A_HANDLE):
    descriptor = process.descriptor(result.final, handle)
    assert (descriptor.named, descriptor.owner) == (0, 0), "the handle record was not given back"


# ---- a new directory ----------------------------------------------------------------------------------

def test_a_directory_in_the_root():
    """The entry in GONE's slot names a freshly allocated cluster, written back with length 0; the
    cluster opens with `.` (itself) and `..` (0: the root's pseudo-cluster is negative) and is zero
    after them; the new DND is first on the root's list."""
    result = _dcreate("A:\\NEWDIR")
    assert result.info["ret"] == 0
    entry = result.root_entry(NEW_SLOT)
    cluster = _new_directory(entry)
    assert cluster in fc.FREE_CLUSTERS and io.fat_entries_after(result)[cluster] == fs.FAT12_END_OF_CHAIN
    assert entry == fc.new_entry("NEWDIR", attr=fs.GEMDOS_ATTR_SUBDIR, cluster=cluster)
    assert result.cluster_entry(cluster, 0) == _dot(".", cluster)
    assert result.cluster_entry(cluster, 1) == _dot("..", 0)
    assert all(result.cluster_entry(cluster, index) == bytes(fs.DIRENT_BYTES)
               for index in range(d.DOT_ENTRIES, d.ENTRIES_PER_CLUSTER))
    assert d.children(result, ROOT)[0] == "NEWDIR"
    _assert_released(result)


def test_a_directory_two_levels_down_names_its_parent_s_cluster_in_dot_dot():
    result = _dcreate("A:\\SUBDIR\\INNER\\NEWDIR")
    assert result.info["ret"] == 0
    entry = result.cluster_entry(d.INNER_CLUSTER, d.DOT_ENTRIES + 2)
    cluster = _new_directory(entry)
    assert result.cluster_entry(cluster, 1) == _dot("..", d.INNER_CLUSTER)
    _assert_released(result)


def test_the_holding_directory_s_other_open_files_drop_off_its_list():
    """SHORT.TXT and SPAN.DAT open in the root (a list of TWO): after the Dcreate the root's list of
    open files is EMPTY — the new directory's close unlinked the head and stored the copied link, 0."""
    pokes = {**ff.open_entry("SHORT", io.OFD_AT, link=io.OTHER_OFD_AT), **ff.open_entry("SPAN", io.OTHER_OFD_AT),
             **ff.root_files(io.OFD_AT), **ff.handle_naming(io.OFD_AT),
             **ff.handle_naming(io.OTHER_OFD_AT, ff.ANOTHER_HANDLE)}
    result = _dcreate("A:\\NEWDIR", pokes)
    assert result.info["ret"] == 0
    assert ff.files_after(result) == []


# ---- create's refusals --------------------------------------------------------------------------------

def test_create_s_refusals_come_back_unchanged():
    for path, answer in (("A:\\NOPE\\NEWDIR", EPTHNF), ("A:\\SUBDIR", EACCDN), ("A:\\", EPTHNF)):
        result = _dcreate(path)
        assert result.info["ret"] == answer, path


def test_a_full_root_is_eaccdn():
    result = _dcreate("A:\\NEWDIR", disk=fc.tree(fc.FULL_ROOT))
    assert result.info["ret"] == EACCDN


def test_no_free_handle_is_enhndl_with_the_entry_left_made():
    result = _dcreate("A:\\NEWDIR", process.full_table_poke(ff.SOMEBODY_ELSE))
    assert result.info["ret"] == process.GEMDOS_ENHNDL
    assert result.root_entry(NEW_SLOT) == fc.new_entry("NEWDIR", attr=fs.GEMDOS_ATTR_SUBDIR)


# ---- the pool runs out after the entry is made ---------------------------------------------------------
# One record left (the file OFD's), or two (and the DND's): the arena spent, the chain holding them —
# and the root's end already seen, so `create`'s searches of it make no DNDs of their own out of them
# (a search that cannot make one reads as a miss: `test_gemdos_fs_create.py`).
ONE_RECORD, TWO_RECORDS = fc.FIRST_SPARE_RECORD, fc.SECOND_SPARE_RECORD


def _pool_holding(*slots):
    return {**records.pool_recycled(*slots), gm.GEMDOS_POOL_FREE_WORDS: struct.pack(">H", 0),
            **d.root_ofd(flags=fs.OFD_SCANNED)}


def test_no_record_for_the_dnd_is_ensmem_with_the_file_left_open():
    result = _dcreate("A:\\NEWDIR", _pool_holding(ONE_RECORD))
    assert result.info["ret"] == process.GEMDOS_ENSMEM
    assert process.descriptor(result.final, ff.A_HANDLE).named == ONE_RECORD


def test_no_record_for_the_directory_s_ofd_is_ensmem_with_the_dnd_on_the_list():
    result = _dcreate("A:\\NEWDIR", _pool_holding(ONE_RECORD, TWO_RECORDS))
    assert result.info["ret"] == process.GEMDOS_ENSMEM
    assert d.children(result, ROOT)[0] == "NEWDIR"
    assert result.long(TWO_RECORDS + fs.DND_OFD) == 0


# ---- no cluster: the rollback ------------------------------------------------------------------------------

def test_a_full_disk_undoes_the_entry_through_ddelete():
    """The entry is made (a free slot needs no cluster) but the directory gets none: the file OFD is
    closed and freed, the handle released, and `Ddelete` of the same path finds the new DND — empty,
    its OFD reading a chain that never started — and deletes it. EACCDN, whatever `Ddelete` said."""
    result = _dcreate("A:\\NEWDIR", disk=fc.tree(fat=fc.full_disk()))
    assert result.info["ret"] == EACCDN
    assert result.root_entry(NEW_SLOT)[0] == fs.DIRENT_DELETED
    assert "NEWDIR" not in d.children(result, ROOT)
    _assert_released(result)


# ---- through the dispatcher -------------------------------------------------------------------------

def test_a_dispatched_dcreate_runs_the_leaf():
    result = io.dispatch_slice(DCREATE, gemdos.long_words(d.TEXT_AT), fc.staged("A:\\NEWDIR"))
    assert result.info["ret"] == 0


# ---- the registry ------------------------------------------------------------------------------------

def _register_all():
    io.register("Dcreate, in the root", DCREATE.entry, _pokes("A:\\NEWDIR"))
    io.register("Dcreate, two levels down", DCREATE.entry, _pokes("A:\\SUBDIR\\INNER\\NEWDIR"))
    io.register("Dcreate, a full disk rolled back", DCREATE.entry, _pokes("A:\\NEWDIR", disk=fc.tree(fat=fc.full_disk())))


_register_all()
