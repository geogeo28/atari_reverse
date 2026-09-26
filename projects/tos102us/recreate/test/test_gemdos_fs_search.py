"""`Fsnext` ($4f, `$fc6df4`) — the search `Fsfirst` left in the running process's DTA, continued
through `$fc663c` — entered at its own address and then THROUGH THE DISPATCHER, against the ROM's own
leaf.

The DTA carries the whole search: the TEXT pattern (`$fc663c` builds the FCB from it again each call),
the attribute, and at ODD offsets the position to resume from and the directory's DND. A match stores
the position after it and fills the rest of the DTA (`$fc6ebc`); no match is ENMFIL with the DTA
untouched. Unpoisoned, for `test_gemdos_fs_dir.py`'s reasons.
"""
import struct

import fs_dir as d
import fs_io as io
import gemdos_fs as fs

SUBDIR = fs.GEMDOS_ATTR_SUBDIR
ENMFIL = fs.GEMDOS_ENMFIL
FROM_SCANNED = fs.GEMDOS_SEARCH_FROM_SCANNED


def _fsnext(pattern, attr, position, dnd_at, pokes=None):
    return io.run(fs.FSNEXT.entry, fs.leaf_glue(fs.FSNEXT, ()), d.fsnext_pokes(pattern, attr, position, dnd_at, pokes))


def _dta_position(result):
    return struct.unpack(">i", result.after(d.DTA_AT + fs.DTA_DIRPOS, d.LONG_BYTES))[0]


def _dta_name(result):
    return result.after(d.DTA_AT + fs.DTA_NAME, fs.DTA_PATTERN_BYTES + 1).split(b"\0")[0].decode("latin-1")


def test_fsnext_finds_the_next_match_and_fills_the_dta():
    """Where Fsfirst left a `*.*` search after SHORT.TXT: SPAN.DAT, its length byte-swapped into the
    DTA, and the position after it."""
    result = _fsnext("*.*", 0, d.position_of(d.ROOT_INDEX["SHORT"]), fs.ROOT_DND_AT)
    assert result.info["ret"] == 0
    assert _dta_name(result) == "SPAN.DAT"
    assert result.long(d.DTA_AT + fs.DTA_FILELN) == fs.SPAN_BYTES
    assert _dta_position(result) == d.position_of(d.ROOT_INDEX["SPAN"])


def test_fsnext_continues_across_a_cluster_boundary_making_the_dnds_it_passes():
    """From BIG's last entry of cluster 10 into cluster 11, where LATE matches `L*` under the
    subdirectory attribute — and, a subdirectory passed, gets a DND on BIG's list."""
    result = _fsnext("L*", SUBDIR, d.position_of(d.ENTRIES_PER_CLUSTER - 2), d.BIG_DND_AT, d.big_dnd())
    assert result.info["ret"] == 0
    assert _dta_name(result) == "LATE"
    assert result.after(d.DTA_AT + fs.DTA_FOUND_ATTR, 1) == bytes([SUBDIR])
    assert _dta_position(result) == d.position_of(d.ENTRIES_PER_CLUSTER)
    assert d.children(result, d.BIG_DND_AT) == ["LATE"]


def test_fsnext_with_nothing_left_is_enmfil_and_leaves_the_dta():
    position = d.position_of(d.ROOT_INDEX["SHORT"])
    result = _fsnext("*.TXT", 0, position, fs.ROOT_DND_AT)
    assert result.info["ret"] == ENMFIL
    assert _dta_position(result) == position
    assert result.after(d.DTA_AT + fs.DTA_FOUND_ATTR, 1) == bytes([fs.SLACK_FILL])
    assert result.word(fs.ROOT_OFD_AT + fs.OFD_FLAGS) == fs.OFD_SCANNED


def test_a_dta_position_of_minus_1_fills_the_dta_from_a_dnd():
    """The search's own DND_SCANNED arm, reached through a DTA: `$fc663c` answers the DND it made for
    the found directory, and `Fsnext` fills the DTA from that DND as if it were a directory entry —
    the name's eleven bytes are the same, the rest is the DND's fields."""
    result = _fsnext("LATE", SUBDIR, FROM_SCANNED, d.BIG_DND_AT, d.big_dnd())
    late = d.child_named(result, d.BIG_DND_AT, "LATE")
    assert result.info["ret"] == 0 and late != 0
    assert _dta_name(result) == "LATE"
    assert result.after(d.DTA_AT + fs.DTA_FOUND_ATTR, 1) == result.after(late + fs.DIRENT_ATTR, 1)
    assert _dta_position(result) == FROM_SCANNED


# ---- through the dispatcher -------------------------------------------------------------------------

def test_a_dispatched_fsnext_runs_the_leaf():
    """The dispatcher slice with our leaf bound behind the hook by the address the ROM's table
    holds: no argument words, the DTA the whole input."""
    result = io.dispatch_slice(fs.FSNEXT, (), d.fsnext_pokes("*.*", 0, d.position_of(d.ROOT_INDEX["SHORT"]), fs.ROOT_DND_AT))
    assert result.info["ret"] == 0
    assert _dta_name(result) == "SPAN.DAT"


# ---- the registry ------------------------------------------------------------------------------------

io.register("Fsnext, the next match", fs.FSNEXT.entry,
            d.fsnext_pokes("*.*", 0, d.position_of(d.ROOT_INDEX["SHORT"]), fs.ROOT_DND_AT))
io.register("Fsnext, across a cluster", fs.FSNEXT.entry,
            d.fsnext_pokes("L*", SUBDIR, d.position_of(d.ENTRIES_PER_CLUSTER - 2), d.BIG_DND_AT, d.big_dnd()))
io.register("Fsnext, none left", fs.FSNEXT.entry,
            d.fsnext_pokes("*.TXT", 0, d.position_of(d.ROOT_INDEX["SHORT"]), fs.ROOT_DND_AT))
