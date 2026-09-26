r"""`Dsetpath` ($3b, `$fc6a7e`) — a path made a drive's current directory — entered at its own address
and then through the dispatcher, over `test/fs_dir.py`'s tree.

The drive (`X:`, or the current one) is logged in; the node the process's p_curdir byte names then
LOSES A REFERENCE; the first node slot from 1 nobody holds is found; and the whole path is walked
(`$fc696c` with its tail taken). Only when all of that succeeds does the slot get the directory, a
reference, and the byte. So a failure after the drop leaves the byte naming a node it no longer
counts — and, the slot search coming after the drop, a node only this process held is free again and
is handed straight back when no slot below it is free first.

THE CAPTURED MACHINE is where every case starts: drive A: logged in, the running process's byte for
A: naming node 2 with ONE reference (its own), node 1 held by another basepage, node 3 and up free.
Unpoisoned, for `test_gemdos_fs_dir.py`'s reasons.
"""
import struct

from harness import BASE_IMAGE, addrs

import case
import fs_dir as d
import fs_io as io
import fs_open as fo
import gemdos
import gemdos_fs as fs

DSETPATH = fs.DSETPATH
ROOT = fs.ROOT_DND_AT
DRIVE_A, DRIVE_B = io.DRIVE, io.DRIVE + 1
A_NODE = BASE_IMAGE[fs.curdir_at(DRIVE_A)]
FIRST_FREE_NODE = next(node for node in range(1, addrs.GEMDOS_DIRECTORY_NODE_COUNT)
                       if BASE_IMAGE[addrs.GEMDOS_CURDIR_REFCOUNTS + node] == 0)
assert BASE_IMAGE[addrs.GEMDOS_CURDIR_REFCOUNTS + A_NODE] == 1, "the process is no longer A:'s node's only holder"
assert FIRST_FREE_NODE > A_NODE


def _dsetpath(path, extra=None):
    return fo.run(DSETPATH, (fo.NAME_AT,), path, extra)


def _references(result, node):
    return result.after(addrs.GEMDOS_CURDIR_REFCOUNTS + node, 1)[0]


def _node(result, drive):
    """The drive's p_curdir byte after the run, and the DND its slot names."""
    node = result.after(fs.curdir_at(drive), 1)[0]
    return node, result.long(fs.node_slot(node))


def _shared(node, holders):
    return {addrs.GEMDOS_CURDIR_REFCOUNTS + node: bytes([holders])}


def _inner(result):
    subdir = d.child_named(result, ROOT, "SUBDIR")
    return d.child_named(result, subdir, "INNER")


# ---- success --------------------------------------------------------------------------------------------

def test_the_node_only_this_process_held_is_handed_straight_back():
    """Two levels down: the drop takes node 2 to 0, the slot search from 1 finds it first, and it ends
    with the new directory and its one reference back."""
    result = _dsetpath("A:\\SUBDIR\\INNER")
    assert result.info["ret"] == 0
    assert _node(result, DRIVE_A) == (A_NODE, _inner(result))
    assert _inner(result) != 0
    assert _references(result, A_NODE) == 1


def test_a_node_another_process_holds_keeps_its_count_and_a_new_one_is_taken():
    result = _dsetpath("a:\\subdir", _shared(A_NODE, 2))
    assert result.info["ret"] == 0
    assert _node(result, DRIVE_A) == (FIRST_FREE_NODE, d.child_named(result, ROOT, "SUBDIR"))
    assert _references(result, A_NODE) == 1
    assert _references(result, FIRST_FREE_NODE) == 1


def test_a_path_with_no_drive_is_walked_from_the_current_directory():
    """No `X:`, no `\\`: A: (the current drive), from the directory its node names — SUBDIR's DND here."""
    extra = {**d.subdir_dnd(), fs.node_slot(A_NODE): struct.pack(">I", d.SUBDIR_DND_AT)}
    result = _dsetpath("INNER", extra)
    assert _node(result, DRIVE_A) == (A_NODE, d.child_named(result, d.SUBDIR_DND_AT, "INNER"))


def test_the_walk_crosses_a_child_list_three_long_and_reads_no_directory():
    result = _dsetpath("A:\\SUBDIR", fo.walked_root())
    assert _node(result, DRIVE_A) == (A_NODE, d.SUBDIR_DND_AT)
    assert not fs.DISK_CALLS


def test_the_drive_prefix_picks_the_drive_but_the_walk_runs_on_the_current_one():
    """"B:\\SUBDIR" with A: current: B: is logged in (a DMD of its own, out of the pool) and its byte
    is the one set — to A:'s SUBDIR, because the `X:` was stepped over in the argument and `$fc696c`
    starts a `\\` path on the CURRENT drive."""
    result = _dsetpath("B:\\SUBDIR")
    node, directory = _node(result, DRIVE_B)
    assert result.info["ret"] == 0
    assert directory == d.child_named(result, ROOT, "SUBDIR") != 0
    assert result.long(directory + fs.DND_DMD) == fs.DMD_AT, "not A:'s DMD"
    assert result.long(fs.dmd_slot(DRIVE_B)) not in (0, fs.DMD_AT), "B: was not logged in on a DMD of its own"
    assert _references(result, node) == 1


def test_slot_0_is_never_handed_out_even_when_nobody_holds_it():
    """Node 0's count cleared (the capture has it non-zero) and A:'s node shared: the new slot is the
    first free one FROM 1 — a p_curdir byte of 0 means "no directory"."""
    result = _dsetpath("A:\\SUBDIR", {**_shared(A_NODE, 2), **_shared(0, 0)})
    assert _node(result, DRIVE_A)[0] == FIRST_FREE_NODE
    assert _references(result, 0) == 0


# A p_curdir byte with bit 7 set is node -1 — a SIGNED index (`movea.w` at $fc6ade): its slot is the
# longword BELOW the node table and its count the byte below the counts. `$fc67de` keeps it only when
# that "slot" is non-zero, so the case makes it so.
NODE_MINUS_ONE = -1


def test_a_negative_node_s_count_is_the_byte_below_the_table():
    extra = {fs.curdir_at(DRIVE_A): bytes([NODE_MINUS_ONE & 0xFF]),
             fs.node_slot(NODE_MINUS_ONE): struct.pack(">I", ROOT)}
    result = _dsetpath("A:\\SUBDIR", extra)
    below = addrs.GEMDOS_CURDIR_REFCOUNTS + NODE_MINUS_ONE
    assert result.after(below, 1)[0] == (BASE_IMAGE[below] - 1) & 0xFF
    assert _node(result, DRIVE_A)[0] == FIRST_FREE_NODE


# A drive letter with bit 7 set: the byte is SIGN-extended before `$fc50ca` sees it ($fc6a98 `ext.w`), so
# `\xC1` is the word $ffc1, which no case folding touches, and less 'A' it is drive -128.
NEGATIVE_LETTER = "\xC1"
NEGATIVE_DRIVE = -128


def test_a_drive_letter_with_bit_7_set_is_a_negative_drive_taken_for_an_error():
    """`$fc67de` logs drive -128 in — its bit is A:'s (`asl.w` by -128 is by 0), so there is no BIOS call
    — and answers the drive, sign-extended: NEGATIVE, which `Dsetpath`'s `bge` reads as an error. It
    answers -128 with nothing dropped and no walk made."""
    result = _dsetpath(NEGATIVE_LETTER + ":\\SUBDIR")
    assert result.info["ret"] == NEGATIVE_DRIVE & fs.LONG_MASK
    assert _references(result, A_NODE) == 1
    assert not fs.DISK_CALLS


def test_another_drive_s_log_in_and_the_walk_s_share_one_node():
    """"B:\\SUBDIR" with A:'s byte 0. B:'s log-in takes the first free node, and the drop gives it back;
    the slot search then picks it again — and the WALK, on A:, logs A: a directory into the same free
    node before Dsetpath takes it. A: and B: end naming ONE node, counted twice, holding SUBDIR."""
    result = _dsetpath("B:\\SUBDIR", {fs.curdir_at(DRIVE_A): bytes([0])})
    assert result.info["ret"] == 0
    shared = result.after(fs.curdir_at(DRIVE_B), 1)[0]
    assert shared == FIRST_FREE_NODE == result.after(fs.curdir_at(DRIVE_A), 1)[0]
    assert _references(result, shared) == 2
    assert result.long(fs.node_slot(shared)) == d.child_named(result, ROOT, "SUBDIR") != 0


# ---- failure ------------------------------------------------------------------------------------------------

def test_a_missing_directory_is_epthnf_and_the_dropped_reference_is_not_restored():
    result = _dsetpath("A:\\NOPE")
    assert result.info["ret"] == fo.EPTHNF
    assert _references(result, A_NODE) == 0, "the drop was undone"
    assert result.after(fs.curdir_at(DRIVE_A), 1)[0] == A_NODE, "...and the byte still names the node"
    assert result.long(fs.node_slot(A_NODE)) == case.long_in(BASE_IMAGE, fs.node_slot(A_NODE))


def test_a_shared_node_is_left_one_reference_short():
    result = _dsetpath("A:\\SUBDIR\\NOPE", _shared(A_NODE, 2))
    assert result.info["ret"] == fo.EPTHNF
    assert _references(result, A_NODE) == 1


def test_forty_held_nodes_is_epthnf_before_the_walk():
    """Every slot from 1 held (A:'s node by two): the drop leaves it at 1, the search finds nothing,
    and no directory is read."""
    held = {addrs.GEMDOS_CURDIR_REFCOUNTS + 1: bytes([1]) * (addrs.GEMDOS_DIRECTORY_NODE_COUNT - 1),
            **_shared(A_NODE, 2)}
    result = _dsetpath("A:\\SUBDIR", held)
    assert result.info["ret"] == fo.EPTHNF
    assert _references(result, A_NODE) == 1
    assert not fs.DISK_CALLS


def test_a_drive_that_will_not_open_answers_its_log_in_error_and_drops_nothing():
    result = _dsetpath("Q:\\SUBDIR", fs.getbpb_answer(0))
    assert result.info["ret"] == fs.GEMDOS_ERROR
    assert _references(result, A_NODE) == 1


# ---- through the dispatcher -------------------------------------------------------------------------

def test_a_dispatched_dsetpath_runs_the_leaf():
    result = fo.dispatch(DSETPATH, gemdos.long_words(fo.NAME_AT), "A:\\SUBDIR\\INNER")
    assert result.info["ret"] == 0
    assert _node(result, DRIVE_A) == (A_NODE, _inner(result))


# ---- the registry ------------------------------------------------------------------------------------

def _register_all():
    fo.register("Dsetpath, two levels", DSETPATH, (fo.NAME_AT,), "A:\\SUBDIR\\INNER")
    fo.register("Dsetpath, a missing directory", DSETPATH, (fo.NAME_AT,), "A:\\NOPE")


_register_all()
