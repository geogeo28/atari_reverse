r"""`Ddelete` ($3a, `$fc792a`) — `src/gemdos/fs_create.c` — over `test/fs_create.py`'s tree.

    $fc7942  bsr $fc696c          the path walked INTO its last component: EPTHNF for none, or a file
    $fc795e  bsr $fc5c3c          the directory's OFD — made when the DND has none, and NOT kept
    $fc7978  seek 64, read ...    every entry past `.` and `..` deleted, up to a 0 entry or the chain's
                                  end — anything else is EACCDN
    $fc79be  the child walk       the link naming the DND on its parent's list, followed WITHOUT an end
                                  test; open files or child DNDs are EINTRN
    $fc79fc  unlink, free, free   the DND off the list, its OFD (if it had one) and itself to the pool
    $fc7a58  bsr $fc7824          ...and its entry deleted, through the holding directory's OFD at the
                                  position the (freed) OFD recorded

NOTHING ASKS WHETHER IT IS SOMEBODY'S CURRENT DIRECTORY, and the root never comes back.
"""
import pytest

from harness import addrs, emu, make_image

import fs_create as fc
import fs_dir as d
import fs_file as ff
import fs_io as io
import fs_records as records
import gemdos
import gemdos_fs as fs
import gemdos_process as process

EPTHNF, EACCDN, EINTRN = fs.GEMDOS_EPTHNF, fs.GEMDOS_EACCDN, fs.GEMDOS_EINTRN
DDELETE = fs.DDELETE
ROOT = fs.ROOT_DND_AT
EMPTYD_DND_AT = fc.FIRST_SPARE_RECORD
EMPTYD_OFD_AT = fc.SECOND_SPARE_RECORD


def _pokes(path, pokes=None):
    return fs.leaf_pokes(DDELETE, (d.TEXT_AT,), fc.staged(path, pokes))


def _ddelete(path, pokes=None):
    return io.run(DDELETE.entry, fs.leaf_glue(DDELETE, (d.TEXT_AT,)), _pokes(path, pokes))


def _assert_entry_deleted(result, name):
    before = fc.ROOT[fc.ROOT_INDEX[name]]
    assert result.root_entry(fc.ROOT_INDEX[name]) == bytes([fs.DIRENT_DELETED]) + before[1:]


def _emptyd_dnd(**fields):
    """EMPTYD's DND as a search of the root would have made it, in a slot the pool can take back."""
    return {**ff.pooled(EMPTYD_DND_AT),
            **d.dnd(EMPTYD_DND_AT, "EMPTYD", fc.EMPTYD_CLUSTER, ROOT, fs.ROOT_OFD_AT, fc.ROOT_INDEX["EMPTYD"],
                    **fields)}


def _emptyd_ofd():
    """...and an OFD over it, as `$fc5c3c` builds one."""
    return {**ff.pooled(EMPTYD_OFD_AT),
            **fs.stage_ofd(EMPTYD_OFD_AT, strtcl=fc.EMPTYD_CLUSTER, fileln=fs.DIRECTORY_LENGTH, dmd=fs.DMD_AT,
                           dir_dnd=ROOT, dir_ofd=fs.ROOT_OFD_AT, dirpos=fc.ROOT_INDEX["EMPTYD"] * fs.DIRENT_BYTES)}


def _root_list_with_emptyd_third(**emptyd_fields):
    """The root's child list FULL -> BIG -> EMPTYD, its mark past EMPTYD: the walk reaches the DND along
    the siblings, and so does the unlink."""
    return {**d.root(child=d.FULL_DND_AT, scanned=d.position_of(fc.ROOT_INDEX["EMPTYD"])),
            **d.full_dnd(sibling=d.BIG_DND_AT), **d.big_dnd(sibling=EMPTYD_DND_AT), **_emptyd_dnd(**emptyd_fields)}


def _children(result):
    return d.children(result, ROOT)


# ---- an empty directory ----------------------------------------------------------------------------

def test_an_empty_directory_found_by_the_walk_is_deleted():
    """EMPTYD's DND is made by the walk's search (first on the list, no OFD), its scan passes the
    deleted entry to the end entry, and it goes: off the list, its cluster freed, its entry `$e5`."""
    result = _ddelete("A:\\EMPTYD")
    assert result.info["ret"] == 0
    assert _children(result) == ["FULL", "BIG", "SUBDIR"]
    assert io.fat_entries_after(result)[fc.EMPTYD_CLUSTER] == 0
    _assert_entry_deleted(result, "EMPTYD")


def test_a_directory_of_deleted_entries_to_the_end_of_its_chain_is_empty():
    """DELDIR has no end entry: the scan runs off its only cluster, and a read of nothing is empty too."""
    result = _ddelete("A:\\DELDIR")
    assert result.info["ret"] == 0
    assert io.fat_entries_after(result)[fc.DELDIR_CLUSTER] == 0
    _assert_entry_deleted(result, "DELDIR")


def test_the_dnd_is_unlinked_from_the_middle_of_its_parent_s_list():
    """THE LIST LONGER THAN ONE: EMPTYD third on the root's list, reached along the siblings — and the
    unlink stores BIG's sibling link, leaving FULL -> BIG."""
    result = _ddelete("A:\\EMPTYD", _root_list_with_emptyd_third())
    assert result.info["ret"] == 0
    assert _children(result) == ["FULL", "BIG"]
    _assert_entry_deleted(result, "EMPTYD")


def test_a_dnd_with_an_ofd_frees_both_and_reads_the_freed_ofd():
    """The OFD goes back to the pool FIRST, and the entry's position and holding directory are read out
    of it afterwards — the pool rewrote only its link. Both records end on the pool's chain."""
    pokes = {**_root_list_with_emptyd_third(ofd=EMPTYD_OFD_AT), **_emptyd_ofd()}
    result = _ddelete("A:\\EMPTYD", pokes)
    assert result.info["ret"] == 0
    assert result.long(records.POOL_CHAIN) == EMPTYD_DND_AT
    assert result.long(EMPTYD_DND_AT) == EMPTYD_OFD_AT
    _assert_entry_deleted(result, "EMPTYD")


# The node the process's current directory is staged in: any slot, its count never read — nothing in
# `Ddelete` looks at the node table. The last slot, clear of the ones the capture's processes hold.
CURRENT_NODE = addrs.GEMDOS_DIRECTORY_NODE_COUNT - 1


def test_the_current_directory_is_deleted_all_the_same():
    """`.` with the current directory EMPTYD: deleted, and the node table still names the freed DND."""
    pokes = {**_root_list_with_emptyd_third(), **gemdos.current_drive_poke(io.DRIVE),
             **fs.current_directory_poke(io.DRIVE, CURRENT_NODE, EMPTYD_DND_AT)}
    result = _ddelete(".", pokes)
    assert result.info["ret"] == 0
    assert result.long(fs.node_slot(CURRENT_NODE)) == EMPTYD_DND_AT
    assert result.long(records.POOL_CHAIN) == EMPTYD_DND_AT
    _assert_entry_deleted(result, "EMPTYD")


# ---- refusals --------------------------------------------------------------------------------------

@pytest.mark.parametrize("path,why", (
    ("A:\\SUBDIR", "INNER and NOTE.TXT"),
    ("A:\\SUBDIR\\INNER", "two levels down: DEEP.TXT and LEAF"),
))
def test_a_directory_with_anything_in_it_is_eaccdn(path, why):
    result = _ddelete(path)
    assert result.info["ret"] == EACCDN, why
    assert result.after(fs.IMAGE_AT, fs.DISK_BYTES) == fc.TREE[fs.IMAGE_AT], why


@pytest.mark.parametrize("path,why", (
    ("A:\\SHORT.TXT", "a FILE: the walk into it finds no DND"),
    ("A:\\NOPE", "nothing of the name"),
    ("A:\\NOPE\\DEEPER", "...nor above it"),
))
def test_a_path_that_names_no_directory_is_epthnf(path, why):
    result = _ddelete(path)
    assert result.info["ret"] == EPTHNF, why


# ---- EINTRN: empty, but still in use ----------------------------------------------------------------
# Each arm is reached by REAL CALLS in sequence, every one a differential of its own, each starting from
# the machine the one before it ended in (`gemdos_fs.continued`): EMPTYD staged holding one more entry,
# which the calls delete again — leaving behind what `Ddelete` refuses.

def _then(leaf, values, path, previous):
    """`leaf` over the text `path` (its first argument), from the machine `previous` ended in."""
    pokes = fs.leaf_pokes(leaf, values, {**fs.continued(previous), **d.text(path)})
    return io.run(leaf.entry, fs.leaf_glue(leaf, values), pokes)


def _first(leaf, values, path, disk):
    return io.run(leaf.entry, fs.leaf_glue(leaf, values), fs.leaf_pokes(leaf, values, fc.staged(path, disk=disk)))


# THE CHILD ARM. KID, a subdirectory that ALSO has the archive bit — which is what lets `Fdelete`'s
# file-only search name it (`test_gemdos_fs_attrib.py`'s ARCHIVED) — in a cluster of its own.
KID_CLUSTER = fc.FREE_CLUSTERS[0]
KID = d.entry("KID", "", fs.GEMDOS_ATTR_SUBDIR | fs.GEMDOS_ATTR_ARCHIVE, KID_CLUSTER)
EMPTYD_HOLDING_KID = fc.tree(emptyd=((fc.EMPTYD_CLUSTER,), fc.EMPTYD[1] + [KID]),
                             extra=(((KID_CLUSTER,), fs.dots(KID_CLUSTER, fc.EMPTYD_CLUSTER)),))


def test_a_child_dnd_left_by_a_deleted_subdirectory_is_eintrn():
    """`Fdelete` of KID: the search that finds it makes KID's DND on EMPTYD's child list, and the delete
    marks the entry `$e5` and frees its cluster — and leaves the DND. EMPTYD then scans empty, and
    `Ddelete` of it answers EINTRN through DND_CHILD, with nothing unlinked or deleted."""
    deleted = _first(fs.FDELETE, (d.TEXT_AT,), "A:\\EMPTYD\\KID", EMPTYD_HOLDING_KID)
    emptyd = d.child_named(deleted, ROOT, "EMPTYD")
    assert deleted.info["ret"] == 0 and d.children(deleted, emptyd) == ["KID"]
    assert deleted.cluster_entry(fc.EMPTYD_CLUSTER, d.DOT_ENTRIES + 1)[0] == fs.DIRENT_DELETED

    refused = _then(DDELETE, (d.TEXT_AT,), "A:\\EMPTYD", deleted)
    assert refused.info["ret"] == EINTRN
    assert "EMPTYD" in _children(refused)
    assert refused.root_entry(fc.ROOT_INDEX["EMPTYD"]) == fc.ROOT[fc.ROOT_INDEX["EMPTYD"]]


# THE FILES ARM. F.TXT, an empty file, in EMPTYD. A DND for a subdirectory is made by ANY search that
# passes its entry beyond its parent's DND_SCANNED mark, and only the path walk moves the mark
# (`src/gemdos/fs_dir.c`): so two searches of the root from position 0 make EMPTYD TWO DNDs, and the
# walk, which takes the newest one of a name, reaches them in turn.
EMPTYD_HOLDING_A_FILE = fc.tree(emptyd=((fc.EMPTYD_CLUSTER,), fc.EMPTYD[1] + [d.entry("F", "TXT")]))
_PAST_EMPTYD = ("A:\\DELDIR", fs.GEMDOS_ATTR_SUBDIR)       # the root's entry just past EMPTYD
_NO_DTA = 0


def test_an_open_file_left_on_a_second_dnd_s_list_is_eintrn():
    """`sfirst` past EMPTYD makes its first DND; `Fopen` of F.TXT puts an OFD on THAT DND's list; a second
    `sfirst` makes a second DND, newer; `Fdelete` of F.TXT walks to the newer one, whose list is empty,
    and deletes the entry; `Ddelete` of EMPTYD walks to the newer one too and deletes it, entry and all.
    The FIRST DND is still on the root's list, and a second `Ddelete` of EMPTYD walks to it: its directory
    scans empty, and its list of open files still holds F.TXT's OFD — EINTRN."""
    path, attr = _PAST_EMPTYD
    first = _first(fs.SFIRST, (d.TEXT_AT, attr, _NO_DTA), path, EMPTYD_HOLDING_A_FILE)
    older = d.child_named(first, ROOT, "EMPTYD")
    opened = _then(fs.FOPEN, (d.TEXT_AT, fs.OPEN_MODE_READ), "A:\\EMPTYD\\F.TXT", first)
    assert opened.info["ret"] == ff.A_HANDLE and opened.long(older + fs.DND_FILES) != 0
    second = _then(fs.SFIRST, (d.TEXT_AT, attr, _NO_DTA), path, opened)
    newer = d.child_named(second, ROOT, "EMPTYD")
    assert newer not in (0, older)
    deleted = _then(fs.FDELETE, (d.TEXT_AT,), "A:\\EMPTYD\\F.TXT", second)
    assert deleted.info["ret"] == 0
    assert deleted.cluster_entry(fc.EMPTYD_CLUSTER, d.DOT_ENTRIES + 1)[0] == fs.DIRENT_DELETED
    removed = _then(DDELETE, (d.TEXT_AT,), "A:\\EMPTYD", deleted)
    assert removed.info["ret"] == 0 and d.child_named(removed, ROOT, "EMPTYD") == older

    refused = _then(DDELETE, (d.TEXT_AT,), "A:\\EMPTYD", removed)
    assert refused.info["ret"] == EINTRN
    assert refused.long(older + fs.DND_FILES) == opened.long(older + fs.DND_FILES)


def test_a_dnd_with_no_ofd_and_a_spent_pool_is_ensmem():
    result = _ddelete("A:\\EMPTYD", {**_root_list_with_emptyd_third(), **records.pool_spent()})
    assert result.info["ret"] == process.GEMDOS_ENSMEM


def test_the_root_is_scanned_like_any_directory():
    """`\\` walks to the root's own DND. Its scan skips the first TWO entries as though they were `.`
    and `..` — the root has neither — and finds SHORT.TXT: EACCDN."""
    result = _ddelete("A:\\")
    assert result.info["ret"] == EACCDN


# A root whose first two entries are the only ones: past them, the scan finds the end at once.
_TWO_ENTRY_ROOT = fc.tree(fc.ROOT[:d.DOT_ENTRIES])


def test_the_rom_s_ddelete_of_an_empty_root_never_returns():
    """...and a root that passes the scan has no parent, so the child walk starts at address 28 — the
    exception vectors — and follows longwords there for ever. The reconstruction HALTS there; this is an
    ORACLE claim."""
    pokes = fs.machine(io.engine(fs.leaf_pokes(DDELETE, (d.TEXT_AT,), fc.staged("A:\\", disk=_TWO_ENTRY_ROOT))))
    with pytest.raises(RuntimeError, match="did not reach rts"):
        emu.run(make_image(pokes), DDELETE.entry, {"a5": 0}, max_insns=200_000)


# ---- through the dispatcher -------------------------------------------------------------------------

def test_a_dispatched_ddelete_runs_the_leaf():
    result = io.dispatch_slice(DDELETE, gemdos.long_words(d.TEXT_AT), fc.staged("A:\\EMPTYD"))
    assert result.info["ret"] == 0


# ---- the registry ------------------------------------------------------------------------------------

def _register_all():
    io.register("Ddelete, an empty directory", DDELETE.entry, _pokes("A:\\EMPTYD"))
    io.register("Ddelete, third on its parent's list", DDELETE.entry, _pokes("A:\\EMPTYD", _root_list_with_emptyd_third()))
    io.register("Ddelete, not empty", DDELETE.entry, _pokes("A:\\SUBDIR"))


_register_all()
