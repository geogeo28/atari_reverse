"""GEMDOS $49 Mfree ($fc8afc) and the free-list insert under it, `md_free_insert` ($fc89dc).

`Mfree` is a search of the allocated list and an unlink; everything else a caller can see is the
insert's, so the COALESCING cases are driven through `Mfree` (where the staged pool is a state the
machine really reaches) and the insert's own two arms — the sorted position and the null-rover
fix-up — are driven at `$fc89dc`.

THE FOUR COALESCING ARMS, which is what this file is for: neither neighbour, the successor only, the
predecessor only, and BOTH — three blocks becoming one, two descriptors going back to the pool, and
the rover walking from the successor to the freed block to the predecessor as each merge fixes it in
turn. That last one is the only path on which the insert's second rover fix-up fires at all, which
is why it is stated as its own case rather than folded into the three-way merge's assertions.

WHY THESE CASES DO NOT POISON, and what they do instead: `gemdos_memory.py`'s module docstring.
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs, make_image

import case
import gemdos_memory as mem

_lib.gemdos_mfree.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32]
_lib.gemdos_mfree.restype = ctypes.c_uint32
_lib.gemdos_md_free_insert.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32,
                                       ctypes.c_uint32]
_lib.gemdos_md_free_insert.restype = None

MPB = mem.GEMDOS_MPB
FREE_HEAD = MPB + addrs.MPB_FREE_LIST
ALLOCATED_HEAD = MPB + addrs.MPB_ALLOCATED_LIST
ROVER_AT = MPB + addrs.MPB_ROVER
CLASS_ONE_CHAIN = mem.GEMDOS_P_ROOT + mem.MD_SIZE_CLASS * mem.POOL_CHAIN_ENTRY_BYTES

BLOCK, GAP = 0x1000, 0x800

# The pool the three-way merge runs over, staged once so the registered rows at the bottom are the
# same pool the case is: a free block, the block to free, a free block, and a used separator.
BETWEEN_TWO_FREE = mem.stage(mem.fill((mem.FREE, BLOCK), (mem.USED, BLOCK), (mem.FREE, BLOCK),
                                      (mem.USED, GAP)))


def after(info, staged):
    """The image as the ORACLE left it — the staged pool with the run's own stores applied, which is
    what a case asserting about the LIST rather than about one field has to walk."""
    image = make_image(staged.pokes)
    for address, value in info["writes"].items():
        image[address] = value
    return image


def mfree(address, pokes=None, settled=()):
    def glue(lib, buf):
        return lib.gemdos_mfree(buf, address)

    return mem.run(addrs.GEMDOS_MFREE, glue, {**case.long_args(address), **(pokes or {})},
                   settled=settled)


def md_free_insert(md, pokes, settled=()):
    def glue(lib, buf):
        lib.gemdos_md_free_insert(buf, md, MPB)

    return mem.run(addrs.GEMDOS_MD_FREE_INSERT, glue, {**case.long_args(md, MPB), **pokes},
                   width=case.NO_RESULT, settled=settled)


def recycled_onto_an_empty_chain(md):
    """`gemdos_pool_free` of a descriptor whose `m_link` was ALREADY zero writes zero over zero.

    It happens whenever the descriptor that goes back to the pool was the last one on the free list,
    which is the commonest shape there is — so it is a named `settled` span rather than a case to
    stage around, and the store itself is asserted out of the oracle's ledger where it matters.
    """
    return (md + addrs.MD_LINK, 4,
            "the descriptor returned to the pool was the end of the free list, so the chain link "
            "that replaces its own is the zero already there")


# ---- the search, and the two refusals ------------------------------------------------------------

def test_the_block_is_found_by_its_start_address_anywhere_on_the_allocated_list():
    """Head, middle and tail of the snapshot's own fourteen — the walk has no bound but the list."""
    blocks = mem.allocated_list()
    for block in (blocks[0], blocks[len(blocks) // 2], blocks[-1]):
        info = mfree(block.start, settled=_settled_for(block))
        assert info["ret"] == 0, f"the block at {block.start:#x} was not found"


def _settled_for(block):
    """...and the one store those three cases cannot attribute, where it arises.

    Only the HEAD of the snapshot's allocated list touches the free block — it ends exactly where
    the free block begins — so only that one coalesces, and only that one returns a descriptor to
    the pool.
    """
    free = mem.free_list()[0]
    return (recycled_onto_an_empty_chain(free.at),) if block.start + block.length == free.start \
        else ()


@pytest.mark.parametrize("address", (0x1dde2, 0xca01, 0, 0xffffffff))
def test_an_address_no_allocated_block_starts_at_is_refused(address):
    """EIMBA (-40) and not a single store. The four are chosen to be wrong in four ways: the FREE
    block's own start (a real `m_start`, on the other list — a reconstruction that searched both
    would return 0 here), one byte inside a live block, address zero, and -1.
    """
    info = mfree(address)
    assert info["ret"] == mem.GEMDOS_EIMBA
    assert mem.stores(info) == {}


def test_a_block_is_unlinked_from_the_allocated_list_wherever_it_sits_on_it():
    """The head goes through `mp_mal` itself — the MPB read as the descriptor before the first —
    and everything else through its predecessor's `m_link`."""
    blocks = mem.allocated_list()
    head, second = blocks[0], blocks[1]
    info = mfree(head.start, settled=_settled_for(head))
    assert case.written_long(info, ALLOCATED_HEAD) == second.at

    info = mfree(second.start, settled=_settled_for(second))
    assert case.written_long(info, head.at + addrs.MD_LINK) == blocks[2].at
    assert ALLOCATED_HEAD not in mem.stores(info), "a middle block moved the list head"


# ---- the four coalescing arms ----------------------------------------------------------------------

def test_a_block_with_neither_neighbour_free_is_inserted_and_nothing_merges():
    """Three used blocks in a row: freeing the middle one leaves three free descriptors where there
    were two, and no descriptor goes back to the pool."""
    staged = mem.stage(mem.fill((mem.USED, BLOCK), (mem.USED, BLOCK), (mem.USED, BLOCK)))
    middle = staged.used[1]
    info = mfree(middle.start, staged.pokes)
    assert info["ret"] == 0
    assert case.written_long(info, FREE_HEAD) == middle.md, (
        "the freed block sorts below the only free block, so it becomes the head")
    assert case.written_long(info, middle.md + addrs.MD_LINK) == staged.free[0].md
    assert CLASS_ONE_CHAIN not in mem.stores(info), "nothing merged, so nothing was recycled"
    assert len(mem.free_list(after(info, staged))) == 2


def test_a_block_whose_successor_is_free_swallows_it():
    """The FORWARD merge: the freed block ends exactly where the next free block begins, so the
    freed descriptor takes both lengths and the successor's descriptor goes back to the pool."""
    staged = mem.stage(mem.fill((mem.USED, BLOCK), (mem.FREE, BLOCK), (mem.USED, GAP)))
    freed, swallowed = staged.used[0], staged.free[0]
    info = mfree(freed.start, staged.pokes)
    assert case.written_long(info, freed.md + addrs.MD_LENGTH) == freed.length + swallowed.length
    assert case.written_long(info, freed.md + addrs.MD_LINK) == staged.free[1].md, (
        "the freed block did not take the swallowed one's place in the list")
    assert case.written_long(info, CLASS_ONE_CHAIN) == swallowed.md


def test_a_block_whose_predecessor_is_free_is_swallowed_by_it():
    """The BACKWARD merge, and the asymmetry worth stating: it is the PREDECESSOR that survives, so
    the descriptor that goes back to the pool is the freed block's own."""
    staged = mem.stage(mem.fill((mem.FREE, BLOCK), (mem.USED, BLOCK), (mem.USED, GAP)))
    below, freed = staged.free[0], staged.used[0]
    # THE PREDECESSOR'S LINK IS WRITTEN TWICE and ends where it began — the insert points it at the
    # descriptor going in, and the merge then points it past it at the same successor as before. It
    # is named rather than staged around because there is no pool shape in which a backward merge
    # leaves that field anywhere else.
    info = mfree(freed.start, staged.pokes,
                 settled=((below.md + addrs.MD_LINK, 4,
                           "the insert set the predecessor's link to the freed descriptor and the "
                           "merge set it back past it, to the successor it already named"),))
    assert case.written_long(info, below.md + addrs.MD_LENGTH) == below.length + freed.length
    assert case.written_long(info, below.md + addrs.MD_LINK) == staged.free[1].md
    assert case.written_long(info, CLASS_ONE_CHAIN) == freed.md


def test_a_block_between_two_free_ones_merges_all_three_and_recycles_two_descriptors():
    """BOTH ARMS ON ONE CALL. The predecessor ends up spanning all three blocks, and the two spare
    descriptors go back to the class chain in the ROM's own order — the SUCCESSOR first, then the
    freed block, so the freed block is the one the next split will get."""
    staged = BETWEEN_TWO_FREE
    below, freed, above = staged.free[0], staged.used[0], staged.free[1]
    info = mfree(freed.start, staged.pokes)
    assert case.written_long(info, below.md + addrs.MD_LENGTH) == \
        below.length + freed.length + above.length
    assert case.written_long(info, below.md + addrs.MD_LINK) == staged.free[2].md
    assert case.written_long(info, CLASS_ONE_CHAIN) == freed.md, "the freed descriptor is on top"
    assert case.written_long(info, freed.md + addrs.MD_LINK) == above.md, (
        "the successor's descriptor is below it on the chain, which is the order they were freed in")


def test_the_rover_walks_from_the_successor_to_the_freed_block_to_the_predecessor():
    """THE ONLY PATH ON WHICH THE INSERT'S SECOND ROVER FIX-UP FIRES. The rover starts on the
    successor; the forward merge moves it onto the freed block because the successor is about to be
    recycled; and the backward merge then finds it on the freed block and moves it again, onto the
    predecessor. A reconstruction with only the first fix-up leaves the rover pointing at a
    descriptor that is back on the pool's free chain.
    """
    staged = mem.stage(mem.fill((mem.FREE, BLOCK), (mem.USED, BLOCK), (mem.FREE, BLOCK),
                                (mem.USED, GAP)), rover_span=1)
    assert staged.rover == staged.free[1].md, "the case only means something with the rover there"
    info = mfree(staged.used[0].start, staged.pokes)
    assert case.written_long(info, ROVER_AT) == staged.free[0].md


def test_the_snapshot_s_own_head_block_merges_into_the_free_block_above_it():
    """No staging at all: the desktop's most recent allocation ends exactly where the free block
    begins, so freeing it is a forward merge on the machine as it was captured — and the free list
    comes back to one descriptor, which is the state `Malloc` split it out of."""
    freed = mem.allocated_list()[0]
    above = mem.free_list()[0]
    assert freed.start + freed.length == above.start
    info = mfree(freed.start, settled=(recycled_onto_an_empty_chain(above.at),))
    assert case.written_long(info, FREE_HEAD) == freed.at
    assert case.written_long(info, freed.at + addrs.MD_LENGTH) == freed.length + above.length
    assert case.written_long(info, CLASS_ONE_CHAIN) == above.at
    assert case.written_long(info, ROVER_AT) == freed.at, (
        "the rover was on the swallowed descriptor and had to move")


# ---- the insert's own two arms, driven at $fc89dc ---------------------------------------------------

def unlinked(staged, index):
    """`staged`, with the `index`-th USED span taken off the allocated list — the state `Mfree`
    hands the insert.

    Without it the descriptor would be on both lists at once, which is a shape nothing produces and
    which the insert would nonetheless accept. The USED spans are chained in address order with the
    first at the head, so removing one is either a new head or one predecessor's link.
    """
    span = staged.used[index]
    successor = staged.used[index + 1].md if index + 1 < len(staged.used) \
        else case.long_in(BASE_IMAGE, ALLOCATED_HEAD)
    at = ALLOCATED_HEAD if index == 0 else staged.used[index - 1].md + addrs.MD_LINK
    return {**staged.pokes, at: successor.to_bytes(4, "big")}, span


# The three heights the descriptor going in can sit at, each with a USED span between it and every
# free block so that NOTHING merges and the case is about the position alone. `fill` cannot build
# the last of them — it always ends the list with a free span — so the remainder is spelt here.
def _sorted_spans(target_index):
    spans = [(mem.USED, BLOCK), (mem.USED, GAP), (mem.FREE, BLOCK), (mem.USED, GAP),
             (mem.FREE, BLOCK)]
    if target_index == 1:
        spans = [(mem.FREE, BLOCK), (mem.USED, GAP), (mem.USED, BLOCK), (mem.USED, GAP),
                 (mem.FREE, BLOCK)]
    elif target_index == 2:
        spans = [(mem.FREE, BLOCK), (mem.USED, GAP), (mem.FREE, BLOCK), (mem.USED, GAP),
                 (mem.USED, BLOCK)]
    return spans + [(mem.USED, mem.SNAPSHOT_FREE_MD.length - sum(n for _k, n in spans))]


# ...and which of the pool's USED spans that target is, once the separators are counted.
_TARGET_OF = {0: 0, 1: 1, 2: 2}


@pytest.mark.parametrize("target_index", (0, 1, 2))
def test_the_free_list_is_kept_sorted_by_start_address(target_index):
    """The insert walks until it meets a block that starts at or above the one going in, so a
    descriptor lands in address order wherever it belongs — below both free blocks, between them,
    or above both. That sorted order is what lets the coalescing arms above compare with two
    NEIGHBOURS instead of searching the whole list.
    """
    staged = mem.stage(_sorted_spans(target_index))
    pokes, target = unlinked(staged, _TARGET_OF[target_index])
    info = md_free_insert(target.md, pokes)

    above = [span for span in staged.free if span.start > target.start]
    below = [span for span in staged.free if span.start < target.start]
    assert case.written_long(info, target.md + addrs.MD_LINK) == (above[0].md if above else 0)
    if below:
        assert case.written_long(info, below[-1].md + addrs.MD_LINK) == target.md
        assert FREE_HEAD not in mem.stores(info), "a descriptor that is not the lowest moved the head"
    else:
        assert case.written_long(info, FREE_HEAD) == target.md
    assert CLASS_ONE_CHAIN not in mem.stores(info), "nothing was adjacent, so nothing may merge"


def test_a_null_rover_is_put_back_on_the_descriptor_that_is_going_in():
    """The free list emptied by a `Malloc` that took the last block exactly leaves the rover null,
    and this is what makes the pool usable again: the first descriptor freed becomes the rover. A
    reconstruction without the fix-up leaves a null rover, and `gemdos_md_alloc` then refuses every
    request on a machine with free memory."""
    staged = mem.stage([(mem.USED, mem.SNAPSHOT_FREE_MD.length)], rover_span=None)
    pokes, target = unlinked(staged, 0)
    info = md_free_insert(target.md, pokes)
    assert case.written_long(info, ROVER_AT) == target.md
    assert case.written_long(info, FREE_HEAD) == target.md
    assert case.written_long(info, target.md + addrs.MD_LINK) == 0


# ---- the cases this battery has VERIFIED ------------------------------------------------------------
# See `test_gemdos_memory_pool.py`'s own list for what these rows are for. The first is the one that
# needs no staging at all — the desktop's own most recent allocation, freed back into the free block
# it was split out of.
_SORTED = mem.stage(_sorted_spans(1))
_SORTED_POKES, _SORTED_TARGET = unlinked(_SORTED, _TARGET_OF[1])

VERIFIED_CASES = (
    ("gemdos_mfree, the snapshot's own head block", addrs.GEMDOS_MFREE, dict(mem.ENTRY_REGS),
     case.long_args(mem.allocated_list()[0].start), None, None, ()),
    ("gemdos_mfree, an address no block starts at", addrs.GEMDOS_MFREE, dict(mem.ENTRY_REGS),
     case.long_args(mem.free_list()[0].start), None, None, ()),
    ("gemdos_mfree, both neighbours free", addrs.GEMDOS_MFREE, dict(mem.ENTRY_REGS),
     {**case.long_args(BETWEEN_TWO_FREE.used[0].start), **BETWEEN_TWO_FREE.pokes}, None, None, ()),
    ("gemdos_md_free_insert, into the middle of the list", addrs.GEMDOS_MD_FREE_INSERT,
     dict(mem.ENTRY_REGS), {**case.long_args(_SORTED_TARGET.md, MPB), **_SORTED_POKES},
     None, None, ()),
)
