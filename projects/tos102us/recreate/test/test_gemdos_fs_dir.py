r"""The DIRECTORY layer — `src/gemdos/fs_dir.c`'s `$fc663c` (one directory searched) and `$fc696c` (a
path walked down the DND tree), over `test/fs_dir.py`'s staged tree.

Both run the whole engine underneath: the directory is read an entry at a time through its OFD and
the buffer cache (`$fc5e9c` with no buffer answers a pointer INTO a cached sector), subdirectories get
their DNDs and OFDs out of the record pool, and the root's pseudo-clusters and a subdirectory's FAT
chain are walked by the verified seek. So a case asserts what the SEARCH decided — which entry, where
the position went, which DNDs now exist, the mark and the end flag — and the byte diff holds the rest.

NOTHING HERE POISONS, for `gemdos_fs.run`'s reasons: every search reaches the BIOS through the cache,
and every DND or OFD made reads and writes the pool's chain head. Every staged record is filled and
every buffer starts `SLACK_FILL`, which stands in for the pass.
"""
import struct

import pytest

from harness import BASE_IMAGE, addrs

import fs_dir as d
import fs_io as io
import fs_records as records
import gemdos_fs as fs

SUBDIR = fs.GEMDOS_ATTR_SUBDIR
VOLUME = fs.GEMDOS_ATTR_VOLUME
ANY_ATTR = fs.D0_LOW_WORD               # `move.w #-1`: what a create searches for a free slot with
FREE_SLOT = chr(fs.DIRENT_DELETED)      # ...and the name it searches for ($fc5c9a's `$e5` arm)
# An attribute word whose HIGH byte is not the volume bit's: only the low byte reaches the pattern.
VOLUME_UNDER_A_HIGH_BYTE = 0x1200 | VOLUME
ROOT = fs.ROOT_DND_AT
FROM_SCANNED = fs.GEMDOS_SEARCH_FROM_SCANNED


def _search(dnd_at, name, attr, position, pokes=None):
    return io.run(addrs.GEMDOS_DIR_SEARCH, d.search_glue(dnd_at, attr, position),
                  d.search_pokes(dnd_at, name, attr, position, pokes))


def _found_name(result):
    """The eleven name bytes of the entry a search answered, out of the cache it points into."""
    return result.after(result.info["ret"], fs.DIRENT_NAME_BYTES)


def _position(result):
    return struct.unpack(">i", result.after(d.POSITION_AT, d.LONG_BYTES))[0]


def _root_ofd_flags(result):
    return result.word(fs.ROOT_OFD_AT + fs.OFD_FLAGS)


# ---- dir_search: what it finds ---------------------------------------------------------------------

@pytest.mark.parametrize("name,attr,index,why", (
    ("SHORT.TXT", 0, "SHORT", "an exact name"),
    ("short.txt", 0, "SHORT", "the text is upper-cased into the pattern"),
    ("*.TXT", 0, "SHORT", "a wildcard extension"),
    ("?PAN.DAT", 0, "SPAN", "a `?`"),
    ("S*.*", 0, "SHORT", "a plain-file pattern passes the subdirectory SUBDIR (attributes share no bit)"),
    ("*.*", SUBDIR, "SUBDIR", "...which a subdirectory pattern finds first"),
    ("SHORT.TXT", SUBDIR, "SHORT", "a plain FILE answers a subdirectory pattern: entry attribute 0 matches"),
    ("*.*", VOLUME, "STAGEDDSK", "the volume pattern loses the shortcut: every plain file is passed"),
    ("*.*", VOLUME_UNDER_A_HIGH_BYTE, "STAGEDDSK", "only the attribute's LOW byte is the pattern's twelfth"),
    ("SECRET.HID", fs.GEMDOS_ATTR_HIDDEN, "SECRET", "a hidden file answers the hidden bit"),
    ("KERNEL.SYS", fs.GEMDOS_ATTR_SYSTEM, "KERNEL", "...a system file the system bit"),
    ("EMPTY.BIN", fs.GEMDOS_ATTR_READ_ONLY, "EMPTY", "...a read-only one the read-only bit"),
))
def test_dir_search_answers_the_first_entry_the_pattern_matches(name, attr, index, why):
    result = _search(ROOT, name, attr, 0)
    assert _found_name(result) == d.ROOT[d.ROOT_INDEX[index]][:fs.DIRENT_NAME_BYTES], why
    assert _position(result) == d.position_of(d.ROOT_INDEX[index]), "the position is left after it"
    assert _root_ofd_flags(result) == 0, "a search that finds does not mark the end"


@pytest.mark.parametrize("name,attr,why", (
    ("SECRET.HID", 0, "a hidden file under a plain-file pattern"),
    ("KERNEL.SYS", 0, "...a system file"),
    ("GONE.OLD", 0, "a DELETED entry's name is not its name: its first byte is `$e5`"),
    ("?ONE.OLD", 0, "...and a `?` there is the one `?` that is refused"),
    ("NOPE", SUBDIR, "a name nothing has"),
))
def test_dir_search_runs_to_the_end_of_the_directory_and_marks_it(name, attr, why):
    """The root's end-of-directory entry stops it: 0, the position past that entry, and OFD_SCANNED."""
    result = _search(ROOT, name, attr, 0)
    assert result.info["ret"] == 0, why
    assert _position(result) == d.position_of(d.ROOT_END), why
    assert _root_ofd_flags(result) == fs.OFD_SCANNED, why


def test_dir_search_resumes_from_the_position_it_is_handed():
    result = _search(ROOT, "*.*", 0, d.position_of(d.ROOT_INDEX["SHORT"]))
    assert _found_name(result) == fs.fcb_name("SPAN", "DAT")


def test_an_e5_name_finds_a_deleted_entry_to_reuse():
    """`$fc5c9a`'s `$e5` arm, from the search's side: the first DELETED entry, whatever its name."""
    result = _search(ROOT, FREE_SLOT, ANY_ATTR, 0)
    assert result.info["ret"] != 0
    assert result.after(result.info["ret"], 1) == bytes([fs.DIRENT_DELETED])
    assert _position(result) == d.position_of(d.ROOT_INDEX["GONE"])


def test_an_e5_name_takes_the_end_of_directory_entry_when_nothing_is_deleted():
    """No deleted entry in LEAF: the search reaches the 0 entry, and for a TEXT name starting `$e5`
    that entry IS the answer — the free slot at the end — with the end NOT marked."""
    result = _search(d.LEAF_DND_AT, FREE_SLOT, ANY_ATTR, 0, d.leaf_dnd())
    assert result.after(result.info["ret"], fs.DIRENT_BYTES) == bytes(fs.DIRENT_BYTES)
    assert _position(result) == d.position_of(d.DOT_ENTRIES)
    assert result.word(result.long(d.LEAF_DND_AT + fs.DND_OFD) + fs.OFD_FLAGS) == 0


def test_a_directory_filling_its_chain_ends_with_the_chain():
    """FULL has no 0 entry: its one cluster is 32 entries and the FAT ends there, so the read past
    them answers 0 — and 0 is an end with no entry, which even an `$e5` search marks as the end."""
    result = _search(d.FULL_DND_AT, FREE_SLOT, ANY_ATTR, 0, d.full_dnd())
    assert result.info["ret"] == 0
    assert _position(result) == fs.CLUSTER_BYTES, "the read past the chain moved nothing"
    ofd = result.long(d.FULL_DND_AT + fs.DND_OFD)
    assert result.word(ofd + fs.OFD_FLAGS) == fs.OFD_SCANNED


def test_a_search_crosses_a_cluster_boundary():
    """BIG's `.`, `..` and F00..F29 fill cluster 10; LAST.TXT is in cluster 11, and the search reaches
    it from cluster 10's last entry."""
    result = _search(d.BIG_DND_AT, "LAST.TXT", 0, d.position_of(d.ENTRIES_PER_CLUSTER - 2), d.big_dnd())
    assert _found_name(result) == fs.fcb_name("LAST", "TXT")
    assert _position(result) == d.position_of(d.ENTRIES_PER_CLUSTER + 1)
    assert d.children(result, d.BIG_DND_AT) == ["LATE"], "the subdirectory passed on the way"


# ---- dir_search: the directory's OFD ---------------------------------------------------------------

def test_a_directory_with_no_ofd_gets_one_and_keeps_it():
    """SUBDIR's DND as `$fc65a2` made it — no OFD. The search makes one (`$fc5c3c`) and stores it on
    the DND; `.` and `..` get no DND, INNER does."""
    result = _search(d.SUBDIR_DND_AT, "INNER", SUBDIR, 0, d.subdir_dnd())
    ofd = result.long(d.SUBDIR_DND_AT + fs.DND_OFD)
    assert ofd != 0 and result.long(ofd + fs.OFD_DIR_DND) == ROOT
    assert _found_name(result) == fs.fcb_name("INNER")
    assert d.children(result, d.SUBDIR_DND_AT) == ["INNER"]


def test_a_spent_pool_with_no_ofd_answers_0_having_stored_the_0():
    result = _search(d.SUBDIR_DND_AT, "INNER", SUBDIR, 0, {**d.subdir_dnd(), **records.pool_spent()})
    assert result.info["ret"] == 0
    assert result.long(d.SUBDIR_DND_AT + fs.DND_OFD) == 0
    assert _position(result) == 0, "nothing read, nothing stored"


# ---- dir_search: the DNDs it makes on the way -------------------------------------------------------

def test_every_subdirectory_passed_gets_a_dnd_the_matching_one_included():
    """SUBDIR, BIG and FULL itself — pushed on the FRONT of the list, so newest first — and not the
    DELETED subdirectory XDIR between them. A real position: the mark is not moved."""
    result = _search(ROOT, "FULL", SUBDIR, 0)
    assert _found_name(result) == fs.fcb_name("FULL")
    assert d.children(result, ROOT) == ["FULL", "BIG", "SUBDIR"]
    assert result.long(ROOT + fs.DND_SCANNED) == 0


def test_the_mark_is_where_making_dnds_resumes_and_an_entry_at_it_gets_none():
    """DND_SCANNED at BIG's own position (the position AFTER BIG): SUBDIR and BIG are at or below it
    — `ble`, so exactly at the mark is not past it — and only FULL gets a DND."""
    result = _search(ROOT, "FULL", SUBDIR, 0, d.root(scanned=d.position_of(d.ROOT_INDEX["BIG"])))
    assert d.children(result, ROOT) == ["FULL"]


def test_the_mark_is_compared_signed():
    """A mark of -32: every position is past it SIGNED, and none would be unsigned."""
    result = _search(ROOT, "BIG", SUBDIR, 0, d.root(scanned=-fs.DIRENT_BYTES))
    assert d.children(result, ROOT) == ["BIG", "SUBDIR"]


def test_an_ofd_marked_scanned_makes_no_dnd():
    result = _search(ROOT, "FULL", SUBDIR, 0, d.root_ofd(flags=fs.OFD_SCANNED))
    assert _found_name(result) == fs.fcb_name("FULL")
    assert d.children(result, ROOT) == []


def test_a_name_the_child_list_already_has_gets_no_second_dnd():
    """A DND named FULL already on the list — made some other way, as `Dcreate` does. The search
    passes FULL's entry and makes it no DND; it still makes SUBDIR's and BIG's."""
    other = d.dnd(d.OTHER_DND_AT, "FULL", d.FULL_CLUSTER, ROOT, fs.ROOT_OFD_AT, d.ROOT_INDEX["FULL"])
    result = _search(ROOT, "FULL", SUBDIR, 0, {**other, **d.root(child=d.OTHER_DND_AT)})
    assert d.children(result, ROOT) == ["BIG", "SUBDIR", "FULL"]
    assert _found_name(result) == fs.fcb_name("FULL")


def test_the_known_name_is_looked_for_along_the_whole_child_list():
    """The list walk goes past its head: FULL is the SECOND child (BIG -> FULL), so the search that
    passes FULL's entry — the only one past the mark — must still find the name on the list and make
    no second DND for it."""
    other = d.dnd(d.OTHER_DND_AT, "FULL", d.FULL_CLUSTER, ROOT, fs.ROOT_OFD_AT, d.ROOT_INDEX["FULL"])
    pokes = {**d.big_dnd(sibling=d.OTHER_DND_AT), **other,
             **d.root(child=d.BIG_DND_AT, scanned=d.position_of(d.ROOT_INDEX["BIG"]))}
    result = _search(ROOT, "FULL", SUBDIR, 0, pokes)
    assert _found_name(result) == fs.fcb_name("FULL")
    assert d.children(result, ROOT) == ["BIG", "FULL"]


def test_a_spent_pool_ends_the_search_at_the_first_dnd_it_cannot_make():
    """0 at once, from inside the loop: no position stored, the end not marked."""
    result = _search(ROOT, "FULL", SUBDIR, 0, records.pool_spent())
    assert result.info["ret"] == 0
    assert _position(result) == 0
    assert _root_ofd_flags(result) == 0


# ---- dir_search from the mark (the walk's search) ---------------------------------------------------

def test_from_the_mark_a_found_directory_answers_its_dnd_and_is_unread():
    """Position -1: the search starts at DND_SCANNED (past SPAN here), answers the DND it made for
    the entry it found, raises the mark past it and seeks back one entry so the next search reads it
    again. The position longword is never stored."""
    result = _search(ROOT, "BIG", SUBDIR, FROM_SCANNED,
                     d.root(scanned=d.position_of(d.ROOT_INDEX["SPAN"])))
    big = d.child_named(result, ROOT, "BIG")
    assert result.info["ret"] == big != 0
    assert result.long(ROOT + fs.DND_SCANNED) == d.position_of(d.ROOT_INDEX["BIG"])
    assert result.long(fs.ROOT_OFD_AT + fs.OFD_POS) == d.position_of(d.ROOT_INDEX["BIG"] - 1)
    assert _position(result) == FROM_SCANNED


def test_from_the_mark_a_miss_raises_it_to_the_end():
    result = _search(ROOT, "NOPE", SUBDIR, FROM_SCANNED)
    assert result.info["ret"] == 0
    assert result.long(ROOT + fs.DND_SCANNED) == d.position_of(d.ROOT_END)
    assert _root_ofd_flags(result) == fs.OFD_SCANNED
    assert _position(result) == FROM_SCANNED


def test_from_the_mark_at_the_end_nothing_is_read_and_the_mark_stands():
    """A mark at the root's length: the first read is clamped to nothing."""
    result = _search(ROOT, "NOPE", SUBDIR, FROM_SCANNED,
                     d.root(scanned=fs.ROOT_SECTORS * fs.SECTOR_BYTES))
    assert result.info["ret"] == 0
    assert result.long(ROOT + fs.DND_SCANNED) == fs.ROOT_SECTORS * fs.SECTOR_BYTES
    assert _root_ofd_flags(result) == fs.OFD_SCANNED


def test_from_a_negative_mark_the_raise_is_compared_signed():
    """A mark of -32 from the mark: the seek refuses the negative position (ERANGE) and the search
    reads the root from where its OFD stood, 0, to the end — and then RAISES the mark to the end,
    because the end is past -32 SIGNED (`ble` at $fc677a); unsigned, -32 would be past everything.
    Every subdirectory read is past the mark too, so each gets a DND."""
    mark = -fs.DIRENT_BYTES
    result = _search(ROOT, "NOPE", SUBDIR, FROM_SCANNED, d.root(scanned=mark))
    assert result.long(ROOT + fs.DND_SCANNED) == d.position_of(d.ROOT_END)
    assert d.children(result, ROOT) == ["FULL", "BIG", "SUBDIR"]


def test_a_mark_past_the_end_is_never_lowered():
    """A mark beyond the root's length: the seek refuses it (ERANGE) and leaves the OFD where it
    stood, at 0, so the search reads the whole root below the mark — making no DND, and leaving the
    mark where it was rather than lowering it to where the reading stopped."""
    mark = 2 * fs.ROOT_SECTORS * fs.SECTOR_BYTES
    result = _search(ROOT, "NOPE", SUBDIR, FROM_SCANNED, d.root(scanned=mark))
    assert result.long(fs.ROOT_OFD_AT + fs.OFD_POS) == d.position_of(d.ROOT_END)
    assert result.long(ROOT + fs.DND_SCANNED) == mark
    assert d.children(result, ROOT) == []


def test_from_the_mark_a_matching_FILE_answers_the_last_dnd_made():
    """THE ANSWER IS WHATEVER DND WAS MADE LAST: SHORT.TXT matches a subdirectory pattern (attribute
    0), but a file gets no DND — so the search answers SUBDIR's, made one entry earlier."""
    result = _search(ROOT, "SHORT.TXT", SUBDIR, FROM_SCANNED)
    assert result.info["ret"] == d.child_named(result, ROOT, "SUBDIR") != 0


def test_from_the_mark_a_name_the_list_has_answers_the_last_dnd_made_not_that_one():
    """The known-name arm from the mark: FULL is on the list already, so its entry makes nothing and
    the answer is BIG's DND, made two entries before it."""
    other = d.dnd(d.OTHER_DND_AT, "FULL", d.FULL_CLUSTER, ROOT, fs.ROOT_OFD_AT, d.ROOT_INDEX["FULL"])
    result = _search(ROOT, "FULL", SUBDIR, FROM_SCANNED, {**other, **d.root(child=d.OTHER_DND_AT)})
    assert result.info["ret"] == d.child_named(result, ROOT, "BIG") != 0


def test_from_the_mark_a_name_the_list_has_answers_that_dnd_when_nothing_else_is_made():
    """...and with the mark past BIG, nothing is made on the way to FULL: the answer is the list
    walk's own result, the DND already there."""
    other = d.dnd(d.OTHER_DND_AT, "FULL", d.FULL_CLUSTER, ROOT, fs.ROOT_OFD_AT, d.ROOT_INDEX["FULL"])
    result = _search(ROOT, "FULL", SUBDIR, FROM_SCANNED,
                     {**other, **d.root(child=d.OTHER_DND_AT, scanned=d.position_of(d.ROOT_INDEX["BIG"]))})
    assert result.info["ret"] == d.OTHER_DND_AT
    assert d.children(result, ROOT) == ["FULL"]


def test_from_the_mark_with_the_end_already_seen_a_found_directory_answers_0():
    """OFD_SCANNED and an empty list: the entry is found, no DND is made, and the list walk's 0 is
    the answer — a directory the walk can then never enter."""
    result = _search(ROOT, "BIG", SUBDIR, FROM_SCANNED, d.root_ofd(flags=fs.OFD_SCANNED))
    assert result.info["ret"] == 0
    assert d.children(result, ROOT) == []


# ---- find_dir, $fc696c -----------------------------------------------------------------------------

def _find(path, take_tail=0, pokes=None):
    return io.run(addrs.GEMDOS_FIND_DIR, d.find_glue(take_tail), d.find_pokes(path, take_tail, pokes))


def _tail(result, path):
    """How far into `path` the walk left the tail, or None for a tail never stored."""
    tail = result.long(d.TAIL_AT)
    return None if tail == d.TAIL_BEFORE else path[tail - d.TEXT_AT:]


def _dnd_name(result, dnd_at):
    return result.after(dnd_at + fs.DND_NAME, fs.DIRENT_NAME_BYTES)


def test_find_dir_walks_two_levels_down_and_stops_short_of_the_file():
    """Neither SUBDIR nor INNER has a DND yet: each directory is searched from its mark as it is
    reached, SUBDIR's own OFD made on the way. The answer is INNER's DND, the tail the file name."""
    path = "A:\\SUBDIR\\INNER\\DEEP.TXT"
    result = _find(path)
    assert _dnd_name(result, result.info["ret"]) == fs.fcb_name("INNER")
    assert _tail(result, path) == "DEEP.TXT"
    subdir = d.child_named(result, ROOT, "SUBDIR")
    assert d.children(result, subdir) == ["INNER"]
    assert result.long(result.info["ret"] + fs.DND_PARENT) == subdir


def test_find_dir_with_take_tail_descends_into_the_last_component_too():
    path = "A:\\SUBDIR\\INNER\\LEAF"
    result = _find(path, take_tail=1)
    assert _dnd_name(result, result.info["ret"]) == fs.fcb_name("LEAF")
    assert _tail(result, path) == ""


def test_find_dir_with_take_tail_on_a_file_answers_0_at_the_file():
    """DEEP.TXT answers INNER's search (a file matches the subdirectory pattern) with the last DND
    made — none, INNER's list being empty — so the walk ends AT the component."""
    path = "A:\\SUBDIR\\INNER\\DEEP.TXT"
    result = _find(path, take_tail=1)
    assert result.info["ret"] == 0
    assert _tail(result, path) == "DEEP.TXT"


def test_dot_stays_and_dot_dot_climbs_and_the_second_visit_reuses_the_dnd():
    """`.` is a step of one and `..` of two up DND_PARENT; INNER's second lookup is on SUBDIR's child
    list, so SUBDIR ends with ONE child DND and INNER is not searched for twice."""
    path = "A:\\SUBDIR\\.\\INNER\\..\\INNER\\X"
    result = _find(path)
    subdir = d.child_named(result, ROOT, "SUBDIR")
    assert d.children(result, subdir) == ["INNER"]
    assert result.info["ret"] == d.child_named(result, subdir, "INNER")
    assert _tail(result, path) == "X"


def test_a_staged_dnd_is_reused_and_its_directory_never_read():
    """SUBDIR already on the root's list with INNER under it: the walk reads no directory at all."""
    pokes = {**d.root(child=d.SUBDIR_DND_AT, scanned=d.position_of(0)), **d.subdir_dnd(child=d.INNER_DND_AT),
             **d.inner_dnd()}
    result = _find("A:\\SUBDIR\\INNER\\X", pokes=pokes)
    assert result.info["ret"] == d.INNER_DND_AT
    assert not fs.DISK_CALLS


def test_dot_dot_above_the_root_answers_0():
    path = "A:\\..\\X"
    result = _find(path)
    assert result.info["ret"] == 0
    assert _tail(result, path) == "X"


def test_a_missing_component_of_a_directory_with_no_list_ends_at_the_component():
    path = "A:\\NOPE\\X"
    result = _find(path)
    assert result.info["ret"] == 0
    assert _tail(result, path) == "NOPE\\X"
    assert d.children(result, ROOT) == ["FULL", "BIG", "SUBDIR"], "the search made every DND it passed"


def test_a_missing_component_of_a_directory_whose_list_runs_out_ends_past_it():
    """SUBDIR on the list and the mark past it: the list runs out, the directory is searched from
    the mark and the name is not there — and the tail is left PAST the component and its separator,
    as though it had been found."""
    path = "A:\\NOPE\\X"
    pokes = {**d.root(child=d.SUBDIR_DND_AT, scanned=d.position_of(0)), **d.subdir_dnd()}
    result = _find(path, pokes=pokes)
    assert result.info["ret"] == 0
    assert _tail(result, path) == "X"
    assert _root_ofd_flags(result) == fs.OFD_SCANNED


def test_find_dir_walks_the_child_list_past_its_head():
    """THE COMMON WALK: the root's list as a whole search would have left it — newest first, FULL ->
    BIG -> SUBDIR — its mark at the end and its end NOT yet flagged. SUBDIR is the list's THIRD
    child, reached along the siblings ($fc69f6 -> $fc6a2e); a walk that searched the disk instead
    would start at the mark, find nothing, and flag the end."""
    path = "A:\\SUBDIR\\X"
    pokes = {**d.root(child=d.FULL_DND_AT, scanned=d.position_of(d.ROOT_END - 1)),
             **d.full_dnd(sibling=d.BIG_DND_AT), **d.big_dnd(sibling=d.SUBDIR_DND_AT), **d.subdir_dnd()}
    result = _find(path, pokes=pokes)
    assert result.info["ret"] == d.SUBDIR_DND_AT
    assert _tail(result, path) == "X"
    assert _root_ofd_flags(result) == 0, "the root was searched"
    assert not fs.DISK_CALLS


def test_a_directory_whose_end_has_been_seen_is_not_searched_again():
    path = "A:\\NOPE\\X"
    pokes = {**d.root(child=d.SUBDIR_DND_AT, scanned=d.position_of(0)), **d.subdir_dnd(),
             **d.root_ofd(flags=fs.OFD_SCANNED)}
    result = _find(path, pokes=pokes)
    assert result.info["ret"] == 0
    assert not fs.DISK_CALLS


def test_a_component_naming_a_file_is_searched_for_twice():
    """SHORT.TXT answers the root's search with SUBDIR's DND (the last made); its name is not
    SHORT.TXT, the list runs out, and a second search from the raised mark finds nothing."""
    path = "A:\\SHORT.TXT\\X"
    result = _find(path)
    assert result.info["ret"] == 0
    assert _tail(result, path) == "X"
    assert d.children(result, ROOT) == ["FULL", "BIG", "SUBDIR"]
    assert _root_ofd_flags(result) == fs.OFD_SCANNED


def test_a_directory_found_across_a_cluster_boundary():
    path = "A:\\BIG\\LATE\\X"
    result = _find(path)
    assert _dnd_name(result, result.info["ret"]) == fs.fcb_name("LATE")
    assert _tail(result, path) == "X"


def test_the_end_flag_stops_the_walk_at_a_directory_it_has_no_dnd_for():
    """The root's end seen and no list: SUBDIR's entry is found but gets no DND — EPTHNF, for a
    directory that is on the disk."""
    path = "A:\\SUBDIR\\X"
    result = _find(path, pokes=d.root_ofd(flags=fs.OFD_SCANNED))
    assert result.info["ret"] == 0
    assert _tail(result, path) == "SUBDIR\\X"


def test_a_path_with_no_drive_starts_in_the_current_directory():
    """No `X:` and no `\\`: the current drive's p_curdir slot, pointed here at SUBDIR's DND."""
    slot = BASE_IMAGE[fs.curdir_at(0)]
    path = "INNER\\X"
    result = _find(path, pokes={**d.subdir_dnd(), fs.node_slot(slot): struct.pack(">I", d.SUBDIR_DND_AT)})
    assert result.info["ret"] == d.child_named(result, d.SUBDIR_DND_AT, "INNER") != 0
    assert _tail(result, path) == "X"


def test_a_drive_that_will_not_open_answers_0_and_stores_no_tail():
    result = _find("Q:\\SUBDIR\\X", pokes=fs.getbpb_answer(0))
    assert result.info["ret"] == 0
    assert result.long(d.TAIL_AT) == d.TAIL_BEFORE


# ---- the registry ------------------------------------------------------------------------------------

io.register("dir_search, a subdirectory's first search", addrs.GEMDOS_DIR_SEARCH,
            d.search_pokes(d.SUBDIR_DND_AT, "INNER", SUBDIR, 0, d.subdir_dnd()))
io.register("dir_search, the root to its end", addrs.GEMDOS_DIR_SEARCH, d.search_pokes(ROOT, "NOPE", SUBDIR, 0))
io.register("dir_search, from the mark", addrs.GEMDOS_DIR_SEARCH,
            d.search_pokes(ROOT, "BIG", SUBDIR, FROM_SCANNED, d.root(scanned=d.position_of(d.ROOT_INDEX["SPAN"]))))
io.register("find_dir, two levels down", addrs.GEMDOS_FIND_DIR, d.find_pokes("A:\\SUBDIR\\INNER\\DEEP.TXT", 0))
io.register("find_dir, DNDs already made", addrs.GEMDOS_FIND_DIR,
            d.find_pokes("A:\\SUBDIR\\INNER\\X", 0, {**d.root(child=d.SUBDIR_DND_AT, scanned=d.position_of(0)),
                                                      **d.subdir_dnd(child=d.INNER_DND_AT), **d.inner_dnd()}))
