"""GEMDOS $4a Mshrink ($fc895a) — cut an allocated block down and give the tail back.

The routine is four decisions and a call, and three of the four are observable only in the right
order: find the block (EIMBA if there is none), refuse to GROW it (EGSBF), round an odd length UP,
then split off the remainder and hand it to `gemdos_md_free_insert`. The rounding comes AFTER the
grow check, which is what makes a length one over the block's a refusal and one UNDER it an
acceptance that rounds back to the whole block and frees NOTHING — a zero-length descriptor.

AND THE FOURTH DECISION IS NOT MADE. `gemdos_pool_get`'s answer is not checked, so a spent
descriptor pool makes this routine store through a null pointer — into the 68000's own reset vectors
— and then insert a "descriptor" at address 0 into the free list. That is a defect in TOS 1.02, and
reproducing it is what faithfulness means here; the case at the bottom of this file is its record.

WHY THESE CASES DO NOT POISON, and what they do instead: `gemdos_memory.py`'s module docstring.
"""
import ctypes

import pytest

from harness import _lib, addrs

import case
import gemdos_memory as mem

_lib.gemdos_mshrink.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32, ctypes.c_uint32]
_lib.gemdos_mshrink.restype = ctypes.c_uint32

MPB = mem.GEMDOS_MPB
FREE_HEAD = MPB + addrs.MPB_FREE_LIST
CLASS_ONE_CHAIN = mem.GEMDOS_P_ROOT + mem.MD_SIZE_CLASS * mem.POOL_CHAIN_ENTRY_BYTES

BLOCK, GAP, KEPT = 0x2000, 0x800, 0x800

# A block to shrink with a USED span above it, so the remainder it frees touches no free block and
# the case is about the SPLIT rather than about the coalescing `test_gemdos_memory_mfree.py` pins.
ISOLATED = mem.fill((mem.USED, BLOCK), (mem.USED, GAP))
# ...and the same block with a FREE span immediately above it, where the remainder does merge.
ADJOINING = mem.fill((mem.USED, BLOCK), (mem.FREE, GAP), (mem.USED, GAP))
# ...staged once, for the same reason the other batteries hoist theirs: the registered rows at the
# bottom must be the pool the cases run on.
ISOLATED_POOL = mem.stage(ISOLATED)


def length_unchanged(block):
    """A shrink to the block's OWN length stores that length back over itself.

    It is the one store a case at that boundary cannot make visible, and staging around it is not
    possible: the boundary IS the case. What the case proves instead is the remainder — a
    zero-length descriptor, which nothing else produces.
    """
    return (block.md + addrs.MD_LENGTH, 4,
            "the block is shrunk to the length it already had, so its own field does not move")


def mshrink(block, new_length, pokes=None, settled=()):
    def glue(lib, buf):
        return lib.gemdos_mshrink(buf, block, new_length)

    return mem.run(addrs.GEMDOS_MSHRINK, glue,
                   {**mem.mshrink_args(block, new_length), **(pokes or {})}, settled=settled)


# ---- the two refusals, and the order they are made in ---------------------------------------------

@pytest.mark.parametrize("address", (0x1dde2, 0xca01, 0, 0xffffffff))
def test_an_address_no_allocated_block_starts_at_is_refused(address):
    """EIMBA (-40), the same four wrong addresses `Mfree` is driven at — including the FREE block's
    own start, which is a real `m_start` on the other list."""
    info = mshrink(address, KEPT)
    assert info["ret"] == mem.GEMDOS_EIMBA
    assert mem.stores(info) == {}


@pytest.mark.parametrize("over", (1, 2, 0x1000))
def test_a_length_longer_than_the_block_is_refused_as_a_growth_failure(over):
    """EGSBF (-67) — the error a caller of `Mshrink` to GROW a TPA gets. Nothing is stored, so the
    block is left at its own length rather than at some clamped one."""
    staged = ISOLATED_POOL
    block = staged.used[0]
    info = mshrink(block.start, block.length + over, staged.pokes)
    assert info["ret"] == mem.GEMDOS_EGSBF
    assert mem.stores(info) == {}


def test_a_length_equal_to_the_block_is_not_a_growth_failure():
    """`bge`, not `bgt`: shrinking to exactly what the block already is succeeds, and frees a
    ZERO-LENGTH block — a descriptor with no memory behind it, which then sits on the free list
    like any other."""
    staged = ISOLATED_POOL
    block, remainder = staged.used[0], staged.next_md
    info = mshrink(block.start, block.length, staged.pokes, settled=(length_unchanged(block),))
    assert info["ret"] == 0
    assert case.written_long(info, remainder + addrs.MD_LENGTH) == 0
    assert case.written_long(info, remainder + addrs.MD_START) == block.start + block.length


def test_the_growth_check_is_a_signed_compare_so_bit_thirty_one_gets_through():
    """`cmp.l 14(a6),d0 / bge` compares SIGNED longwords, so a length with bit 31 set reads as
    negative and passes a check meant to refuse it. The block's length then becomes that value and
    the remainder's is a subtraction that wraps.

    A caller's argument, so it is reachable by anything that asks — and a reconstruction that
    compared unsigned would answer EGSBF where the ROM answers 0 and rewrites both descriptors.
    """
    staged = ISOLATED_POOL
    block, remainder = staged.used[0], staged.next_md
    asked = 0x80000000
    info = mshrink(block.start, asked, staged.pokes)
    assert info["ret"] == 0
    assert case.written_long(info, block.md + addrs.MD_LENGTH) == asked
    assert case.written_long(info, remainder + addrs.MD_START) == (block.start + asked) & 0xFFFFFFFF
    assert case.written_long(info, remainder + addrs.MD_LENGTH) == \
        (block.length - asked) & 0xFFFFFFFF


@pytest.mark.parametrize("asked,kept", ((KEPT - 1, KEPT), (1, 2), (BLOCK - 3, BLOCK - 2)))
def test_an_odd_length_is_rounded_up_to_an_even_one(asked, kept):
    """...so the lengths on GEMDOS's lists stay even however odd the request. The rounding is in the
    block's own `m_length` and in where the remainder starts."""
    staged = ISOLATED_POOL
    block, remainder = staged.used[0], staged.next_md
    info = mshrink(block.start, asked, staged.pokes)
    assert case.written_long(info, block.md + addrs.MD_LENGTH) == kept
    assert case.written_long(info, remainder + addrs.MD_START) == block.start + kept
    assert case.written_long(info, remainder + addrs.MD_LENGTH) == block.length - kept


def test_the_rounding_is_made_after_the_growth_check_and_not_before():
    """THE ORDER, stated as the pair that separates it. One byte OVER an even block's length is
    refused although rounding would have made it two over and refused it anyway; one byte UNDER is
    accepted and rounds back UP to the whole block, so the call succeeds and frees nothing.

    A reconstruction that rounded first refuses the second of these — `block.length - 1` becomes
    `block.length`, still not a growth, so it would still pass... but it would ALSO round
    `block.length + 1` to `block.length + 2` before the compare, which changes no answer either.
    What the pair really pins is that the rounding does not RESCUE the over-length request: the
    block's length is never written at all on that side.
    """
    staged = ISOLATED_POOL
    block = staged.used[0]
    refused = mshrink(block.start, block.length + 1, staged.pokes)
    assert refused["ret"] == mem.GEMDOS_EGSBF
    assert mem.stores(refused) == {}

    accepted = mshrink(block.start, block.length - 1, staged.pokes,
                       settled=(length_unchanged(block),))
    assert accepted["ret"] == 0
    assert case.written_long(accepted, block.md + addrs.MD_LENGTH) == block.length
    assert case.written_long(accepted, staged.next_md + addrs.MD_LENGTH) == 0


# ---- the split -------------------------------------------------------------------------------------

def test_the_block_keeps_its_start_and_the_remainder_is_freed_from_where_it_ends():
    """The shape of the split, and the three stores that are the whole of it."""
    staged = ISOLATED_POOL
    block, remainder = staged.used[0], staged.next_md
    info = mshrink(block.start, KEPT, staged.pokes)
    assert info["ret"] == 0
    assert addrs.MD_START + block.md not in mem.stores(info), "the block's start moved"
    assert case.written_long(info, block.md + addrs.MD_LENGTH) == KEPT
    assert case.written_long(info, remainder + addrs.MD_START) == block.start + KEPT
    assert case.written_long(info, remainder + addrs.MD_LENGTH) == block.length - KEPT
    assert case.written_long(info, FREE_HEAD) == remainder, (
        "the remainder sorts below every other free block here, so it becomes the head")


def test_the_block_stays_on_the_allocated_list_and_keeps_its_owner():
    """Shrinking does not release the block: it stays where it is, owned by whoever owned it, and
    only the tail changes hands."""
    staged = ISOLATED_POOL
    block = staged.used[0]
    info = mshrink(block.start, KEPT, staged.pokes)
    assert MPB + addrs.MPB_ALLOCATED_LIST not in mem.stores(info)
    assert block.md + addrs.MD_OWNER not in mem.stores(info)


def test_shrinking_to_nothing_frees_the_whole_block_but_keeps_the_descriptor():
    """Zero is even, so nothing rounds: the block's length becomes 0 and the remainder is the whole
    of it, starting where the block does. The block is still allocated, and still owned — which is
    how a TPA of no bytes comes about."""
    staged = ISOLATED_POOL
    block, remainder = staged.used[0], staged.next_md
    info = mshrink(block.start, 0, staged.pokes)
    assert case.written_long(info, block.md + addrs.MD_LENGTH) == 0
    assert case.written_long(info, remainder + addrs.MD_START) == block.start
    assert case.written_long(info, remainder + addrs.MD_LENGTH) == block.length


def test_the_remainder_merges_with_a_free_block_it_touches():
    """The remainder goes through the same insert `Mfree` uses, so it coalesces: with a free block
    immediately above, the freshly cut descriptor swallows it and the swallowed one goes straight
    back to the pool it was just taken from."""
    staged = mem.stage(ADJOINING)
    block, remainder, above = staged.used[0], staged.next_md, staged.free[0]
    info = mshrink(block.start, KEPT, staged.pokes)
    assert case.written_long(info, remainder + addrs.MD_LENGTH) == \
        block.length - KEPT + above.length
    assert case.written_long(info, CLASS_ONE_CHAIN) == above.md


def test_the_remainder_takes_a_recycled_descriptor_before_it_touches_the_arena():
    """...and where that descriptor comes from is the pool's business, as it is for a split."""
    staged = mem.stage(ISOLATED, recycled=1)
    block = staged.used[0]
    info = mshrink(block.start, KEPT, staged.pokes)
    assert case.written_long(info, staged.recycled[0] + addrs.MD_START) == block.start + KEPT
    assert mem.GEMDOS_POOL_USED_WORDS not in mem.stores(info), "the arena was cut into"


def test_a_zero_length_remainder_sorts_BELOW_a_free_block_that_starts_where_it_does():
    """THE SORT WALK'S `<=`, and the only pool shape that can see it.

    Shrinking a block to its own length frees a ZERO-LENGTH descriptor at the block's end — and
    where the block is followed by a free one, that is an address some other descriptor already
    starts at. The walk stops at "starts at OR ABOVE", so the zero-length descriptor goes in BELOW
    its twin and then swallows it; a walk that stopped only at "above" would put it after, where
    neither merge fires and two descriptors are left describing one block.
    """
    staged = mem.stage(ADJOINING)
    block, remainder, above = staged.used[0], staged.next_md, staged.free[0]
    assert block.start + block.length == above.start, "the two must really share an address"
    info = mshrink(block.start, block.length, staged.pokes, settled=(length_unchanged(block),))
    assert case.written_long(info, FREE_HEAD) == remainder, (
        "the zero-length descriptor did not become the head of the free list")
    assert case.written_long(info, remainder + addrs.MD_LENGTH) == above.length, (
        "...and did not swallow the block it starts at the start of")
    assert case.written_long(info, CLASS_ONE_CHAIN) == above.md


# ---- the descriptor that is never checked -----------------------------------------------------------

def test_a_spent_descriptor_pool_makes_mshrink_write_through_null():
    """TOS 1.02's OWN BUG, reproduced rather than corrected.

    `Malloc` checks `gemdos_pool_get`'s answer and reports a failure; `Mshrink` does not, and stores
    through it. With the arena spent and no recycled descriptor, the "remainder" is at address 0, so
    `m_start` and `m_length` land on the 68000's reset vectors at $4 and $8 — and the insert that
    follows then puts that address-0 descriptor on the FREE LIST, writing its link over the initial
    supervisor stack pointer at $0 and emptying the list in the process. The call reports SUCCESS.

    Staged, not fabricated: the arena really does run out (16,000 bytes, and one descriptor per
    split), and `arena_words_left` is a word GEMDOS's own init writes.
    """
    staged = mem.stage(ISOLATED, arena_words_left=mem.MD_ARENA_WORDS - 1)
    block = staged.used[0]
    free_head_before = staged.free[0].md
    info = mshrink(block.start, KEPT, staged.pokes)

    assert info["ret"] == 0, "the ROM reports this as a success, which is the half that bites"
    assert case.written_long(info, addrs.MD_START) == block.start + KEPT
    assert case.written_long(info, addrs.MD_LENGTH) == block.length - KEPT
    assert case.written_long(info, addrs.MD_LINK) == free_head_before, (
        "the insert wrote the old free-list head over the initial supervisor stack pointer")
    assert case.written_long(info, FREE_HEAD) == 0, (
        "...and made the null descriptor the head, which empties the list for every later Malloc")


# ---- the cases this battery has VERIFIED ------------------------------------------------------------
# See `test_gemdos_memory_pool.py`'s own list for what these rows are for.
VERIFIED_CASES = (
    ("gemdos_mshrink, a split", addrs.GEMDOS_MSHRINK, dict(mem.ENTRY_REGS),
     {**mem.mshrink_args(ISOLATED_POOL.used[0].start, KEPT), **ISOLATED_POOL.pokes},
     None, None, ()),
    ("gemdos_mshrink, asked to grow", addrs.GEMDOS_MSHRINK, dict(mem.ENTRY_REGS),
     {**mem.mshrink_args(ISOLATED_POOL.used[0].start, ISOLATED_POOL.used[0].length + 1),
      **ISOLATED_POOL.pokes}, None, None, ()),
    ("gemdos_mshrink, an address no block starts at", addrs.GEMDOS_MSHRINK, dict(mem.ENTRY_REGS),
     mem.mshrink_args(mem.free_list()[0].start, KEPT), None, None, ()),
)
