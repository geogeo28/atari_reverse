"""GEMDOS $48 Malloc ($fc8aae) and the descriptor allocator under it, `md_alloc` ($fc886a).

Two routines and one behaviour: `Malloc` is a rounding and a call, and everything a caller can
observe about which block it gets is `md_alloc`'s. So the cases are split the way the code is — the
SEARCH, the SPLIT and the two lists are driven at `$fc886a`, where the MPB is an argument and the
answer is the descriptor; the ROUNDING and the `-1` exemption are driven at `$fc8aae`, where they
live.

THE SEARCH IS NEXT-FIT, and that is the claim most of this file exists to pin. `md_alloc` starts at
`mp_rover` and examines the block AFTER it, so the same pool answers the same request with a
different block depending on where the last allocation left the rover — and the snapshot's own rover
is on the head of a one-entry free list, which is exactly the state in which next-fit and
first-fit-from-the-head agree. A reconstruction that searched from `mp_mfl` would pass every case
that did not stage a second free block on purpose.

WHY THESE CASES DO NOT POISON, and what they do instead: `gemdos_memory.py`'s module docstring.
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs, make_image

import case
import gemdos_memory as mem

_lib.gemdos_md_alloc.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32, ctypes.c_uint32]
_lib.gemdos_md_alloc.restype = ctypes.c_uint32
_lib.gemdos_malloc.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32]
_lib.gemdos_malloc.restype = ctypes.c_uint32

MPB = mem.GEMDOS_MPB
ROVER_AT = MPB + addrs.MPB_ROVER
ALLOCATED_HEAD = MPB + addrs.MPB_ALLOCATED_LIST
FREE_HEAD = MPB + addrs.MPB_FREE_LIST
RUNNING_PROCESS = case.long_in(BASE_IMAGE, addrs.GEMDOS_P_RUN)

# THE ROVER'S STORE IS OFTEN IDEMPOTENT — the block taken is usually the rover's own successor, so
# the rover is left exactly where it was — and the run check cannot see that either way, because the
# ROM stores `mp_mal` in the four bytes immediately below it and that one always moves. So the
# rover's value is stated where it matters, out of the oracle's ledger:
# `test_the_rover_is_left_at_the_block_s_predecessor` for the ordinary arm and
# `test_a_block_reached_through_the_mpb_leaves_the_rover_on_the_new_free_head` for the other.


def md_alloc(amount, pokes, settled=()):
    def glue(lib, buf):
        return lib.gemdos_md_alloc(buf, amount, MPB)

    return mem.run(addrs.GEMDOS_MD_ALLOC, glue, {**case.long_args(amount, MPB), **pokes},
                   settled=settled)


def malloc(amount, pokes=None, settled=()):
    def glue(lib, buf):
        return lib.gemdos_malloc(buf, amount)

    return mem.run(addrs.GEMDOS_MALLOC, glue, {**case.long_args(amount), **(pokes or {})},
                   settled=settled)


# ---- the search ---------------------------------------------------------------------------------

# Two free blocks either side of a used one, both big enough for the request below, plus whatever is
# left of the snapshot's block as a third. Which of the three a request gets is the whole question,
# and the answer is the one AFTER the rover.
SMALL, LARGE, REQUEST = 0x2000, 0x4000, 0x1000
THREE_FREE = mem.fill((mem.FREE, SMALL), (mem.USED, 0x800), (mem.FREE, LARGE), (mem.USED, 0x800))
# ...staged once, with the rover on the head, because most of the cases below want exactly that and
# the registered rows at the bottom must be the SAME pool the tests run on.
FROM_THE_HEAD = mem.stage(THREE_FREE, rover_span=0)

# ...and a machine with a WRAPPED free length on it, which only `Mshrink`'s own signed growth check
# can produce. Built by running that call under the oracle rather than by writing the descriptor
# down (`mem.after_running`), because `stage` cannot legitimately write one: its descriptors have to
# tile the TPA and a length past 2^31 does not.
#
# A FIXTURE AND NOT A MODULE CONSTANT: it runs the ORACLE, and one case needs it. At import time
# that run happens in every worker that collects this file, before any test has asked for it, and a
# failure in it is a COLLECTION error rather than a red case naming the routine it could not stage.
_SMALL_BLOCK = 0x2000
_WRAP_SPANS = mem.fill((mem.USED, _SMALL_BLOCK), (mem.USED, 0x800))
_WRAP_LENGTH = 0x80000000


@pytest.fixture(scope="module")
def wrapped():
    """`(pokes, image)` for that machine — the pool one `Mshrink` later, and the same bytes staged."""
    pool = mem.stage(_WRAP_SPANS)
    pokes = mem.after_running(addrs.GEMDOS_MSHRINK,
                              {**mem.mshrink_args(pool.used[0].start, _WRAP_LENGTH), **pool.pokes})
    return pokes, make_image(pokes)


@pytest.mark.parametrize("rover_span,taken", ((0, 1), (1, 2), (2, 0)))
def test_the_search_starts_at_the_block_after_the_rover_and_wraps_round_the_list(rover_span, taken):
    """THE NEXT-FIT CLAIM. Three free blocks, all big enough, and the rover moved over each of them
    in turn: the block allocated is always the rover's SUCCESSOR, and from the last one the search
    WRAPS through the MPB to the head of the list rather than giving up.

    A reconstruction that searched from `mp_mfl` answers the head every time and fails two of these
    three; one that searched from the rover but did not wrap fails the third.
    """
    staged = mem.stage(THREE_FREE, rover_span=rover_span)
    info = md_alloc(REQUEST, staged.pokes)
    assert info["ret"] == staged.free[taken].md
    assert case.written_long(info, staged.free[taken].md + addrs.MD_LENGTH) == REQUEST


def test_the_rover_is_left_at_the_block_s_predecessor():
    """...and when the block taken is NOT the rover's successor, the rover moves — to the descriptor
    BEFORE the one that was taken, so the next search starts at whatever took its place.

    Staged by making the rover's successor too small: the request skips it, and the block that is
    taken is one further on. That also makes the rover's store visible, which is why this is the
    case that states it.
    """
    spans = mem.fill((mem.FREE, REQUEST // 2), (mem.USED, 0x800), (mem.FREE, LARGE),
                     (mem.USED, 0x800))
    staged = mem.stage(spans, rover_span=2)          # the rover is on the LAST free block
    info = md_alloc(REQUEST, staged.pokes)
    assert info["ret"] == staged.free[1].md, "the too-small head was taken"
    assert case.written_long(info, ROVER_AT) == staged.free[0].md, (
        "the rover was not left at the taken block's predecessor")


def test_a_block_reached_through_the_mpb_leaves_the_rover_on_the_new_free_head():
    """The one arm where the predecessor is the MPB itself — the search wrapped and took the head of
    the free list. The rover cannot be the MPB (nothing else would read it as a descriptor), so the
    ROM stores `mp_mfl` instead, which by then is whatever took the head's place."""
    staged = mem.stage(THREE_FREE, rover_span=2)
    info = md_alloc(REQUEST, staged.pokes)
    assert info["ret"] == staged.free[0].md
    assert case.written_long(info, FREE_HEAD) == case.written_long(info, ROVER_AT), (
        "the rover and the free-list head must be the same descriptor after this arm")


def test_a_request_bigger_than_every_free_block_answers_nothing_and_stores_nothing():
    """The sweep ends where it started and the answer is 0 — indistinguishable, to a caller, from a
    spent descriptor pool."""
    staged = FROM_THE_HEAD
    info = md_alloc(mem.SNAPSHOT_FREE_MD.length + 1, staged.pokes)
    assert info["ret"] == 0
    assert mem.stores(info) == {}


def test_an_empty_free_list_answers_nothing_before_it_looks_at_anything():
    """A null rover is the state `Malloc` of the last free block leaves (see `stage`), and it is
    tested FIRST — before the `-1` flag is even computed, which is why the next case matters."""
    staged = mem.stage([(mem.USED, mem.SNAPSHOT_FREE_MD.length)], rover_span=None)
    info = md_alloc(REQUEST, staged.pokes)
    assert info["ret"] == 0
    assert mem.stores(info) == {}


def test_an_empty_free_list_answers_nothing_to_the_largest_block_question_too():
    """...so `Malloc(-1)` on a machine with no free memory answers 0, not "the largest is 0" by some
    other route. Same arm, and a reconstruction that tested the flag first would still answer 0 —
    what separates them is that this one stores nothing either."""
    staged = mem.stage([(mem.USED, mem.SNAPSHOT_FREE_MD.length)], rover_span=None)
    info = md_alloc(mem.MALLOC_LARGEST_FREE_BLOCK, staged.pokes)
    assert info["ret"] == 0
    assert mem.stores(info) == {}


@pytest.mark.parametrize("rover_span", (0, 1, 2))
def test_the_largest_block_is_measured_over_the_whole_list_wherever_the_rover_is(rover_span):
    """`-1` allocates nothing: it walks every block and answers the biggest `m_length` it saw. The
    biggest is staged in the MIDDLE of the list so that neither the head nor the tail is the answer
    by accident, and the rover is moved over all three so the wrap is exercised in each.
    """
    biggest = mem.SNAPSHOT_FREE_MD.length - 0x9000
    spans = [(mem.FREE, 0x4000), (mem.USED, 0x1000), (mem.FREE, biggest), (mem.USED, 0x1000),
             (mem.FREE, 0x3000)]
    staged = mem.stage(spans, rover_span=rover_span)
    info = md_alloc(mem.MALLOC_LARGEST_FREE_BLOCK, staged.pokes)
    assert info["ret"] == biggest
    assert mem.stores(info) == {}, "the report-only request allocated something"


def test_the_largest_block_is_compared_signed_so_a_wrapped_length_never_wins(wrapped):
    """`cmp.l a5@(8),d6 / bge` is a SIGNED compare, so a free block whose length has bit 31 set is
    never reported as the largest however big it looks.

    SUCH A BLOCK EXISTS, and the case starts from a machine that really has one: `Mshrink`'s growth
    check is signed too, so asking it for $80000000 bytes of a small block is accepted and the
    remainder's length is a subtraction that wraps (`test_gemdos_memory_mshrink.py` drives that arm
    directly). `mem.after_running` runs THAT call under the oracle and hands this one what it left,
    rather than staging a descriptor no routine could have written.

    A reconstruction comparing unsigned answers the wrapped length here — the largest free block on
    a machine that has none that big.
    """
    pokes, image = wrapped
    free = mem.free_list(image)
    signed_largest = max((length - (1 << 32) if length >> 31 else length)
                         for length in (block.length for block in free))
    assert any(block.length >> 31 for block in free), (
        "the fixture no longer holds a wrapped length, so this case has stopped being about one")
    info = md_alloc(mem.MALLOC_LARGEST_FREE_BLOCK, pokes)
    assert info["ret"] == signed_largest


# ---- the split, and the exact fit -----------------------------------------------------------------

def test_an_exact_fit_is_unlinked_whole_and_costs_the_pool_nothing():
    """A request that matches a block's length takes the descriptor as it stands: it is unlinked
    from the free list, its start and length are untouched, and no new descriptor is cut — which is
    visible as the arena's cursor not moving."""
    staged = FROM_THE_HEAD
    block = staged.free[1]
    info = md_alloc(block.length, staged.pokes)
    assert info["ret"] == block.md
    assert case.written_long(info, staged.free[0].md + addrs.MD_LINK) == staged.free[2].md, (
        "the block was not unlinked from the free list")
    assert mem.GEMDOS_POOL_USED_WORDS not in mem.stores(info), "an exact fit cut a descriptor"
    assert addrs.MD_LENGTH + block.md not in mem.stores(info), "an exact fit rewrote the length"


def test_a_split_keeps_the_low_half_and_gives_the_remainder_the_new_descriptor():
    """THE SPLIT'S WHOLE SHAPE, and the one a reconstruction gets backwards. The block that was on
    the free list keeps its `m_start`, has its length cut to the request and moves to the ALLOCATED
    list; the REMAINDER gets the freshly cut descriptor, starts where the request ends, and takes
    the block's place in the free list."""
    staged = FROM_THE_HEAD
    block = staged.free[1]
    remainder = staged.next_md
    info = md_alloc(REQUEST, staged.pokes)

    assert info["ret"] == block.md
    assert case.written_long(info, block.md + addrs.MD_LENGTH) == REQUEST
    assert addrs.MD_START + block.md not in mem.stores(info), "the block's start moved"
    assert case.written_long(info, remainder + addrs.MD_START) == block.start + REQUEST
    assert case.written_long(info, remainder + addrs.MD_LENGTH) == block.length - REQUEST
    assert case.written_long(info, remainder + addrs.MD_LINK) == staged.free[2].md
    assert case.written_long(info, staged.free[0].md + addrs.MD_LINK) == remainder, (
        "the remainder did not take the block's place on the free list")


def test_a_split_takes_a_recycled_descriptor_before_it_touches_the_arena():
    """...and where the remainder's descriptor comes from is `gemdos_pool_get`'s business: with one
    on the class-1 chain the arena is not touched at all."""
    staged = mem.stage(THREE_FREE, rover_span=0, recycled=1)
    info = md_alloc(REQUEST, staged.pokes)
    remainder = staged.recycled[0]
    assert case.written_long(info, remainder + addrs.MD_START) == staged.free[1].start + REQUEST
    assert mem.GEMDOS_POOL_USED_WORDS not in mem.stores(info)


def test_a_spent_descriptor_pool_refuses_a_split_over_memory_that_is_plainly_free():
    """TOS 1.02's OWN FAILURE MODE. The block fits, the free list is long, and the request is
    refused anyway — because a split needs a descriptor and the arena has none left. Nothing is
    stored: the block stays on the free list at its full length."""
    staged = mem.stage(THREE_FREE, rover_span=0, arena_words_left=mem.MD_ARENA_WORDS - 1)
    info = md_alloc(REQUEST, staged.pokes)
    assert info["ret"] == 0
    assert mem.stores(info) == {}


def test_an_exact_fit_still_succeeds_when_the_descriptor_pool_is_spent():
    """...and the other side of it, which is what makes the failure above about the SPLIT and not
    about the request: the same spent pool serves a request that needs no new descriptor."""
    staged = mem.stage(THREE_FREE, rover_span=0, arena_words_left=0)
    info = md_alloc(staged.free[1].length, staged.pokes)
    assert info["ret"] == staged.free[1].md


# ---- the allocated list ---------------------------------------------------------------------------

def test_the_block_goes_to_the_head_of_the_allocated_list_owned_by_the_running_process():
    """`m_own` is `p_run`'s basepage read at the moment of the call — not the caller's, and not
    anything on the descriptor — which is what lets `Pterm` release a process's blocks by owner."""
    staged = FROM_THE_HEAD
    block = staged.free[1]
    info = md_alloc(REQUEST, staged.pokes)
    assert case.written_long(info, block.md + addrs.MD_LINK) == staged.used[0].md, (
        "the block's link is not the allocated list it was pushed onto")
    assert case.written_long(info, ALLOCATED_HEAD) == block.md
    assert case.written_long(info, block.md + addrs.MD_OWNER) == RUNNING_PROCESS


def test_the_owner_is_read_from_p_run_and_is_not_a_constant():
    """Driven at a second value, staged into `p_run` itself: a reconstruction that had baked the
    snapshot's basepage in would pass the case above and fail this one."""
    another = RUNNING_PROCESS + 0x100
    staged = FROM_THE_HEAD
    pokes = {**staged.pokes, addrs.GEMDOS_P_RUN: another.to_bytes(4, "big")}
    info = md_alloc(REQUEST, pokes)
    assert case.written_long(info, staged.free[1].md + addrs.MD_OWNER) == another


def test_taking_the_last_free_block_empties_the_list_and_nulls_the_rover():
    """The state `stage(rover_span=None)` above describes, produced rather than staged: the
    snapshot's one free block asked for exactly its own length. The search wraps to the MPB, the
    exact fit unlinks through it, and the rover — stored from `mp_mfl` because the predecessor was
    the MPB — comes out null."""
    info = md_alloc(mem.SNAPSHOT_FREE_MD.length, {})
    assert info["ret"] == mem.SNAPSHOT_FREE_MD.at
    assert case.written_long(info, FREE_HEAD) == 0
    assert case.written_long(info, ROVER_AT) == 0


# ---- Malloc's own two lines -----------------------------------------------------------------------

def test_malloc_answers_the_block_s_address_and_not_its_descriptor():
    """The one thing `Malloc` does with `md_alloc`'s answer: read `m_start` out of it."""
    staged = FROM_THE_HEAD
    info = malloc(REQUEST, staged.pokes)
    assert info["ret"] == staged.free[1].start


def test_malloc_reports_a_failure_as_zero():
    """...and a null descriptor is answered as 0 rather than dereferenced."""
    staged = FROM_THE_HEAD
    info = malloc(mem.SNAPSHOT_FREE_MD.length + 2, staged.pokes)
    assert info["ret"] == 0
    assert mem.stores(info) == {}


@pytest.mark.parametrize("asked,taken", ((REQUEST - 1, REQUEST), (REQUEST + 1, REQUEST + 2),
                                         (1, 2), (LARGE - 3, LARGE - 2)))
def test_an_odd_request_is_rounded_up_to_an_even_one(asked, taken):
    """Which is why every length on either of GEMDOS's lists is even. The rounding is visible in the
    block's `m_length`, not in the answer — the address is the same either way."""
    staged = FROM_THE_HEAD
    info = malloc(asked, staged.pokes)
    assert case.written_long(info, staged.free[1].md + addrs.MD_LENGTH) == taken


def test_the_rounding_turns_a_near_miss_into_an_exact_fit():
    """The sharpest form of it: one byte under a block's length rounds back UP to it, so the block
    is taken whole and no descriptor is cut at all. A reconstruction that skipped the rounding
    splits instead and leaves a one-byte free block behind."""
    staged = FROM_THE_HEAD
    block = staged.free[1]
    info = malloc(block.length - 1, staged.pokes)
    assert info["ret"] == block.start
    assert mem.GEMDOS_POOL_USED_WORDS not in mem.stores(info), "the rounded request still split"


def test_the_rounding_can_push_a_request_past_a_block_it_would_have_fitted():
    """...and the other direction: one byte over an even block's length rounds to two over, so the
    block is skipped and the request lands on the next one that fits."""
    staged = FROM_THE_HEAD
    info = malloc(staged.free[1].length + 1, staged.pokes)
    assert info["ret"] == staged.free[2].start


def test_the_largest_block_request_escapes_the_rounding():
    """-1 IS ODD, and rounding it would make it 0 — a request for no memory, which the first free
    block satisfies. So the exemption is what stops `Malloc(-1)` from allocating: it is checked on
    the whole longword before the low bit is looked at, and the answer here is a LENGTH where a
    rounded reconstruction would answer an address and leave the pool changed."""
    staged = FROM_THE_HEAD
    info = malloc(mem.MALLOC_LARGEST_FREE_BLOCK, staged.pokes)
    assert info["ret"] == max(span.length for span in staged.free)
    assert mem.stores(info) == {}


def test_a_request_for_no_memory_splits_a_block_into_nothing_and_the_whole_of_it():
    """Zero is even, so nothing rounds and nothing refuses it: the block is split at 0, which leaves
    a zero-length block on the ALLOCATED list and a remainder that is the whole of the original.
    The answer is a real address — the block's own start."""
    staged = FROM_THE_HEAD
    block = staged.free[1]
    remainder = staged.next_md
    info = malloc(0, staged.pokes)
    assert info["ret"] == block.start
    assert case.written_long(info, block.md + addrs.MD_LENGTH) == 0
    assert case.written_long(info, remainder + addrs.MD_START) == block.start
    assert case.written_long(info, remainder + addrs.MD_LENGTH) == block.length


# ---- the cases this battery has VERIFIED ------------------------------------------------------------
# See `test_gemdos_memory_pool.py`'s own list for what these rows are for.
VERIFIED_CASES = (
    ("gemdos_md_alloc, a split", addrs.GEMDOS_MD_ALLOC, dict(mem.ENTRY_REGS),
     {**case.long_args(REQUEST, MPB), **FROM_THE_HEAD.pokes}, None, None, ()),
    ("gemdos_md_alloc, an exact fit", addrs.GEMDOS_MD_ALLOC, dict(mem.ENTRY_REGS),
     {**case.long_args(FROM_THE_HEAD.free[1].length, MPB), **FROM_THE_HEAD.pokes}, None, None, ()),
    ("gemdos_md_alloc, the largest free block", addrs.GEMDOS_MD_ALLOC, dict(mem.ENTRY_REGS),
     {**case.long_args(mem.MALLOC_LARGEST_FREE_BLOCK, MPB), **FROM_THE_HEAD.pokes}, None, None, ()),
    ("gemdos_malloc, an odd request", addrs.GEMDOS_MALLOC, dict(mem.ENTRY_REGS),
     {**case.long_args(REQUEST - 1), **FROM_THE_HEAD.pokes}, None, None, ()),
    ("gemdos_malloc, the largest free block", addrs.GEMDOS_MALLOC, dict(mem.ENTRY_REGS),
     {**case.long_args(mem.MALLOC_LARGEST_FREE_BLOCK), **FROM_THE_HEAD.pokes}, None, None, ()),
)
