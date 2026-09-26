"""The media-change recovery's two helpers — `$fc93f4` and `$fc9468`, `src/gemdos/dispatch.c` — each a
whole-function differential at its own address.

    $fc93f4  free_dnd_tree(dnd)    the first child's tree, the next sibling's tree, the directory's OFD,
                                   every directory-node slot naming it, then the DND — depth first
    $fc9468  free_drive_ofds(dmd)  every handle record whose OFD is on the drive in the caller's A4:
                                   the OFD back to the pool, the record's three fields cleared

THE RECOVERY ITSELF IS NOT HERE. It runs only after a file-system call longjmps back through the
termination record with E_CHG (`$fc951e`), and that record is the one thing the reconstruction omits
(`src/gemdos/dispatch.c`'s header); `src/gemdos/fs_disk.c` halts where the ROM would throw.

THE POOL IS THE WITNESS. Every record goes back through `gemdos_pool_free`, which pushes it on its size
class's free chain — so the chain a run leaves, head first, is the ORDER the records were freed in, and
that order is the whole traversal.
"""
import ctypes
import struct

from harness import BASE_IMAGE, _lib, addrs

import case
import fs_file as ff
import fs_records as records
import gemdos
import gemdos_console as console
import gemdos_fs as fs
import gemdos_process as process

# Both are `void`: the ROM leaves D0 as whatever its last call did, and neither caller reads it.
FRAME = ">I"                            # each takes one pushed longword: a DND, or the DMD it never reads
FREE_DND_TREE = fs.routine(addrs.GEMDOS_FREE_DND_TREE, "gemdos_free_dnd_tree", FRAME, returns=None)
FREE_DRIVE_OFDS = addrs.GEMDOS_FREE_DRIVE_OFDS
for _core in (_lib.gemdos_free_dnd_tree, _lib.gemdos_free_drive_ofds):
    _core.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32]
_lib.gemdos_free_drive_ofds.restype = None
# Records to be freed sit in ODD slots only: the pool files each by the class word in the two bytes
# BELOW it (`fs_file.pooled`), which must land in an empty slot rather than on a record.
SLOT = [records.record_slot(index) for index in range(1, records.RECORD_SLOTS, 2)]


def _chain(result):
    """The node class's free chain after the run, head first."""
    return list(fs.linked(result.long, records.POOL_CHAIN, 0, records.RECORD_SLOTS))


# ---- $fc93f4 -----------------------------------------------------------------------------------------
# A tree two levels deep and two wide:  ROOT -> A -> B (siblings), A -> D (a child), each with the OFD
# its directory is read through where it has one — the root and D. The directory-node table names A in
# one slot, D in its LAST, and some other DND in a third, which must survive.
ROOT, A, B, D, ROOT_OFD, D_OFD = SLOT
A_NODE, D_NODE, OTHER_NODE = 3, addrs.GEMDOS_DIRECTORY_NODE_COUNT - 1, 7
SOMEONE_ELSE = records.record_slot(0)


def _tree():
    pokes = {**fs.stage_dnd(ROOT, child=A, ofd=ROOT_OFD), **fs.stage_dnd(A, parent=ROOT, child=D, sibling=B),
             **fs.stage_dnd(B, parent=ROOT), **fs.stage_dnd(D, parent=A, ofd=D_OFD),
             **fs.stage_ofd(ROOT_OFD, fill=fs.SLACK_FILL), **fs.stage_ofd(D_OFD, fill=fs.SLACK_FILL),
             fs.node_slot(A_NODE): struct.pack(FRAME, A), fs.node_slot(D_NODE): struct.pack(FRAME, D),
             fs.node_slot(OTHER_NODE): struct.pack(FRAME, SOMEONE_ELSE)}
    for record in SLOT:
        pokes.update(ff.pooled(record))
    return pokes


def _free_tree(dnd, pokes):
    return fs.run(FREE_DND_TREE.entry, fs.leaf_glue(FREE_DND_TREE, (dnd,)), fs.leaf_pokes(FREE_DND_TREE, (dnd,), pokes),
                  width=case.NO_RESULT)


def test_the_whole_tree_goes_back_to_the_pool_children_then_siblings_then_itself():
    result = _free_tree(ROOT, _tree())
    # Freed D's OFD, D, B, A, the root's OFD, the root: the chain is that, last first.
    assert _chain(result) == [ROOT, ROOT_OFD, A, B, D, D_OFD]


def test_every_directory_node_slot_naming_a_freed_dnd_is_cleared_and_no_other():
    result = _free_tree(ROOT, _tree())
    assert result.long(fs.node_slot(A_NODE)) == 0 and result.long(fs.node_slot(D_NODE)) == 0, "the last slot too"
    assert result.long(fs.node_slot(OTHER_NODE)) == SOMEONE_ELSE


def test_a_subtree_takes_its_later_siblings_with_it():
    """Entered at A — not the root — the walk follows A's SIBLING as well as its child: B goes too, and the
    root and its OFD stay."""
    result = _free_tree(A, _tree())
    assert _chain(result) == [A, B, D, D_OFD]


# ---- $fc9468 -----------------------------------------------------------------------------------------
# A second DMD is only ever COMPARED here, never read, so any address other than the first's will do: the
# one just past it.
THIS_DRIVE, OTHER_DRIVE, NO_DRIVE = fs.DMD_AT, fs.DMD_AT + fs.DMD_BYTES, 0x0BAD_0000
ON_THIS, ON_OTHER, ALSO_ON_THIS = SLOT[:3]
FILE_ON_THIS = ff.A_HANDLE
DEVICE_RECORD = ff.ANOTHER_HANDLE
FILE_ON_OTHER = ff.ANOTHER_HANDLE + 1
LAST_RECORD = addrs.GEMDOS_FIRST_FILE_HANDLE + process.GEMDOS_HANDLE_COUNT - 1
TWO_REFERENCES = 2
OWNER = ff.P_RUN


def _open_files():
    """Handle records 6 (a file on this drive), 7 (a device), 8 (a file on the other drive) and the
    table's LAST (a file on this drive again), every other record free."""
    pokes = {**process.descriptor_poke(FILE_ON_THIS, ON_THIS, OWNER, TWO_REFERENCES),
             **process.descriptor_poke(DEVICE_RECORD, console.HANDLE_CON, OWNER),
             **process.descriptor_poke(FILE_ON_OTHER, ON_OTHER, OWNER),
             **process.descriptor_poke(LAST_RECORD, ALSO_ON_THIS, OWNER),
             **fs.stage_ofd(ON_THIS, fill=fs.SLACK_FILL, dmd=THIS_DRIVE),
             **fs.stage_ofd(ON_OTHER, fill=fs.SLACK_FILL, dmd=OTHER_DRIVE),
             **fs.stage_ofd(ALSO_ON_THIS, fill=fs.SLACK_FILL, dmd=THIS_DRIVE)}
    for record in (ON_THIS, ON_OTHER, ALSO_ON_THIS):
        pokes.update(ff.pooled(record))
    return pokes


def _free_ofds_pokes(pushed):
    return {**_open_files(), **case.args(FRAME, pushed)}


def _free_ofds(caller_a4, pushed):
    """Glued by hand, not through `gemdos_fs.routine`: the core takes the A4 its caller left, which the
    frame does not carry (the ROM pushes `pushed` and never reads it)."""
    return fs.run(FREE_DRIVE_OFDS, lambda lib, buf: lib.gemdos_free_drive_ofds(buf, caller_a4),
                  _free_ofds_pokes(pushed), regs={"a4": caller_a4}, width=case.NO_RESULT)


def test_the_open_files_on_the_drive_in_a4_are_freed_and_their_records_cleared():
    result = _free_ofds(THIS_DRIVE, THIS_DRIVE)
    assert _chain(result) == [ALSO_ON_THIS, ON_THIS]
    assert tuple(process.descriptor(result.final, FILE_ON_THIS))[1:] == (0, 0, 0), "value, owner AND references"
    assert tuple(process.descriptor(result.final, LAST_RECORD))[1:] == (0, 0, 0)
    assert process.descriptor(result.final, DEVICE_RECORD).named == console.HANDLE_CON & fs.LONG_MASK, \
        "a device is passed over"
    assert process.descriptor(result.final, FILE_ON_OTHER).named == ON_OTHER


def test_the_pushed_drive_is_never_read_only_a4_is():
    """ROM BUG: the argument is pushed and ignored. The other drive in A4 and this one pushed frees the
    other drive's file."""
    result = _free_ofds(OTHER_DRIVE, THIS_DRIVE)
    assert _chain(result) == [ON_OTHER]


def test_an_a4_naming_no_drive_frees_nothing():
    """...which is what the recovery really gets: A4 is whatever the innermost file-system routine left in
    it when the longjmp was thrown, not a DMD — so in practice the open files survive their drive."""
    result = _free_ofds(NO_DRIVE, THIS_DRIVE)
    assert _chain(result) == []
    assert case.long_in(BASE_IMAGE, records.POOL_CHAIN) == 0, "the snapshot's chain is empty to start with"


# ---- the registry -------------------------------------------------------------------------------------

def _register_all():
    gemdos.register("gemdos_free_dnd_tree, a tree two deep and two wide", FREE_DND_TREE.entry, {"a5": 0},
                    fs.machine(fs.leaf_pokes(FREE_DND_TREE, (ROOT,), _tree())))
    gemdos.register("gemdos_free_drive_ofds, two files on the drive in A4", FREE_DRIVE_OFDS,
                    {"a5": 0, "a4": THIS_DRIVE}, fs.machine(_free_ofds_pokes(THIS_DRIVE)))


_register_all()
