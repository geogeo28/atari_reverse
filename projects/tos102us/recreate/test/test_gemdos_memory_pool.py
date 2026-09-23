"""The GEMDOS record pool — the bump arena $fc7ed0, `pool_get` $fc7f1a and `pool_free` $fc7f9c —
and the SHAPE OF THE POOL the whole memory group's cases start from.

Two halves. The first is ground truth about the captured machine: where the descriptors are, how
many, what tiles what, and how much arena is left. Nothing in it is a differential — it is the
statement of the world every other battery in this group stages on top of, and the reason it is
tests rather than a comment is that a future capture with a different desktop must redden HERE
rather than inside somebody's `Malloc` case.

The second half is the three pool routines themselves, which are where TOS 1.02's "out of memory
descriptors" lives: a descriptor is not an array slot but a size-class record off a 16,000-byte
bump arena, and when the arena is spent `Malloc` reports failure over RAM that is plainly free.
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs

import case
import gemdos_memory as mem

_lib.gemdos_pool_arena_alloc.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16]
_lib.gemdos_pool_arena_alloc.restype = ctypes.c_uint32
_lib.gemdos_pool_get.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16]
_lib.gemdos_pool_get.restype = ctypes.c_uint32
_lib.gemdos_pool_free.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32]
_lib.gemdos_pool_free.restype = None

ARENA_TOP = mem.GEMDOS_POOL_ARENA + mem.GEMDOS_POOL_ARENA_WORDS * 2
CLASS_ONE_CHAIN = mem.GEMDOS_P_ROOT + mem.MD_SIZE_CLASS * mem.POOL_CHAIN_ENTRY_BYTES
BASEPAGE_BYTES = mem.BASEPAGE_SIZE_CLASS * (1 << mem.POOL_CLASS_WORDS_SHIFT) * 2

# The two staged pools the second half of this file works over, hoisted so the registered cases at
# the bottom are the SAME pools the tests run on rather than a second spelling of them. One free
# span and one allocated, which is the least a pool can be; `RECYCLED` adds two spare descriptors on
# the class-1 chain, the state `gemdos_pool_free` leaves.
ONE_USED = mem.fill((mem.USED, 0x1000))
PLAIN = mem.stage(ONE_USED)
RECYCLED = mem.stage(ONE_USED, recycled=2)


# ---- the pool as the snapshot holds it -------------------------------------------------------------

def test_the_free_list_is_one_descriptor_over_the_top_of_the_tpa():
    """Everything the desktop has not taken, in a single block — which is why every stager in this
    group re-cuts THAT block rather than inventing memory."""
    blocks = mem.free_list()
    assert len(blocks) == 1
    assert blocks[0].length == case.long_in(BASE_IMAGE, addrs.SYSVAR_MEMTOP) - blocks[0].start
    assert blocks[0].owner == 0, "a free descriptor is unowned"
    assert blocks[0].link == 0, "...and it is the end of the list"


def test_the_rover_is_on_the_free_list():
    """The rover is where the next search starts (`gemdos_md_alloc`), so it must name a descriptor
    the search can walk from. A null rover is a state the ROM does reach — `Malloc` of the last free
    block exactly — but it is not this machine's."""
    assert mem.rover() == mem.free_list()[0].at


def test_the_two_lists_tile_the_tpa_with_no_gap_and_no_overlap():
    """From `_membot` to `_memtop`, every byte belongs to exactly one descriptor.

    That is the invariant the allocator maintains and the one a staged pool has to keep — a case
    that loses or invents bytes is a case about a machine the ROM could not have produced. It is
    also how the desktop's fourteen allocated blocks are shown to be REAL: they butt up against each
    other and against the free block without a hole anywhere.
    """
    blocks = sorted(mem.free_list() + mem.allocated_list(), key=lambda md: md.start)
    at = case.long_in(BASE_IMAGE, addrs.SYSVAR_MEMBOT)
    for block in blocks:
        assert block.start == at, (
            f"the descriptor at {block.at:#x} starts at {block.start:#x}, not at {at:#x} where the "
            f"one below it ends")
        at += block.length
    assert at == case.long_in(BASE_IMAGE, addrs.SYSVAR_MEMTOP)


def test_every_allocated_block_is_owned_and_every_free_one_is_not():
    """`m_own` is the basepage `gemdos_md_alloc` read out of `p_run`, and it is what lets `Pterm`
    release a process's memory by walking this list."""
    for block in mem.allocated_list():
        assert block.owner != 0, f"the allocated descriptor at {block.at:#x} is unowned"
    for block in mem.free_list():
        assert block.owner == 0


def test_the_running_process_owns_most_of_what_is_allocated():
    """...and `p_run`'s own basepage is among the blocks, which is what makes the snapshot a
    desktop rather than a bare OS: the process that is running allocated its own workspace."""
    owners = {block.owner for block in mem.allocated_list()}
    running = case.long_in(BASE_IMAGE, addrs.GEMDOS_P_RUN)
    assert running in owners
    assert running in {block.start for block in mem.allocated_list()}, (
        "the running basepage is not itself one of the allocated blocks")


def test_every_descriptor_but_the_os_s_own_is_an_arena_record_of_class_one():
    """A descriptor is a size-class-1 record: sixteen bytes with the class word below them, cut from
    the arena eighteen bytes at a time.

    They are NOT on an eighteen-byte stride from the arena's base, and that is the point of the
    arena rather than a flaw in it: the same bump serves every class, so records of other sizes —
    the root basepage GEMDOS's init cuts, the file system's — sit between them.

    The ONE exception is `$048e`, the descriptor BIOS `Getmpb` builds — it is a fixed longword
    quartet in low RAM rather than a pool record, so the word below it is a system variable and
    reads as a different class. It is on the allocated list here because GEMDOS's own init passed
    its MPB to `Getmpb` and then allocated out of it.
    """
    for block in mem.free_list() + mem.allocated_list():
        if block.at == addrs.OS_MEMORY_DESCRIPTOR:
            continue
        assert mem.GEMDOS_POOL_ARENA < block.at < mem.arena_cursor(), (
            f"the descriptor at {block.at:#x} is not inside the arena the pool cuts from")
        assert mem.size_class_of(BASE_IMAGE, block.at) == mem.MD_SIZE_CLASS


def test_the_os_s_own_descriptor_is_on_the_allocated_list_and_is_not_a_pool_record():
    """Stated as its own case because the exception above would otherwise read as an oversight, and
    because it is the one descriptor `gemdos_pool_free` would file under the WRONG class."""
    at = addrs.OS_MEMORY_DESCRIPTOR
    assert at in {block.at for block in mem.allocated_list()}
    assert mem.size_class_of(BASE_IMAGE, at) != mem.MD_SIZE_CLASS


def test_the_arena_counters_add_up_to_what_the_init_wrote():
    """`move.w #8000,$8780` at $fc936e is the whole of the pool's capacity, and the two counters
    partition it: what has been handed out and what is left."""
    assert mem.arena_used_words() + mem.arena_free_words() == mem.GEMDOS_POOL_ARENA_WORDS


def test_the_arena_ends_just_below_the_word_that_counts_it():
    """WHERE THE GEMDOS BSS IS, the part of it this group pins. The arena's base is the `$2a6e` the
    bump adds and its size is the 8000 words the init writes, so it spans `$2a6e..$68ed` — and the
    cursor word lives at `$68f0`, two bytes above its top. COMPONENTS.md records the GEMDOS BSS
    extent as unestablished; this is the piece of it that is now measured."""
    assert ARENA_TOP == 0x68ee
    assert mem.GEMDOS_POOL_USED_WORDS == ARENA_TOP + 2


def test_the_arena_above_the_cursor_is_untouched_memory():
    """Which is what makes it legitimate for a stager to cut descriptors there — and, separately,
    what makes `gemdos_pool_get`'s CLEAR invisible on a virgin record (see the clear's own case)."""
    assert not any(BASE_IMAGE[mem.arena_cursor():ARENA_TOP]), (
        "the arena above the bump cursor is not all zero, so the desktop has written there and a "
        "staged descriptor would be over live data")


def test_no_descriptor_has_been_recycled_yet():
    """Every class chain at `p_root` is empty on this machine — the desktop has freed nothing — so a
    case that wants `gemdos_pool_get` to POP rather than bump has to stage the chain itself."""
    assert mem.recycled_descriptors() == []


# THE THREE TRAP ROUTINES ARE PINNED TO THEIR TABLE ENTRIES ELSEWHERE, and this battery no longer
# does it itself: now that their addresses are in `addrs.h` beside their function numbers,
# `test_boot_snapshot.py::test_a_reconstruction_is_the_dispatch_table_entry_it_claims_to_be` reads
# the same records out of the mapped ROM for every `<NAME>`/`<NAME>_FN` pair a verified case enters
# — which is the project's one such check rather than a fourth copy of it.


# ---- the bump arena, $fc7ed0 -------------------------------------------------------------------

def arena_alloc(words, pokes=None, settled=()):
    def glue(lib, buf):
        return lib.gemdos_pool_arena_alloc(buf, words)

    return mem.run(addrs.GEMDOS_POOL_ARENA_ALLOC, glue,
                   {**case.word_arg(words), **(pokes or {})}, settled=settled)


def counter_pokes(used=None, left=None):
    """The arena's two counters, staged directly — they are plain words of GEMDOS's BSS."""
    pokes = {}
    if used is not None:
        pokes[mem.GEMDOS_POOL_USED_WORDS] = struct.pack(">H", used)
    if left is not None:
        pokes[mem.GEMDOS_POOL_FREE_WORDS] = struct.pack(">H", left)
    return pokes


@pytest.mark.parametrize("words", (1, mem.MD_ARENA_WORDS, 129, 1000))
def test_the_arena_hands_out_words_from_the_cursor_and_moves_both_counters(words):
    """The record is `$2a6e + used * 2` and the two counters move by the request — one down, one
    up. Four sizes, including a descriptor's nine words and a basepage's 129."""
    info = arena_alloc(words)
    assert info["ret"] == mem.arena_cursor()
    assert case.written(info, mem.GEMDOS_POOL_USED_WORDS, 2) == mem.arena_used_words() + words
    assert case.written(info, mem.GEMDOS_POOL_FREE_WORDS, 2) == mem.arena_free_words() - words


def test_the_arena_refuses_one_word_more_than_it_has_left_and_stores_nothing():
    """The refusal is BEFORE the subtraction, so a spent request leaves the counters exactly as it
    found them — which is what lets `gemdos_pool_get`'s caller retry later."""
    info = arena_alloc(mem.arena_free_words() + 1)
    assert info["ret"] == 0
    assert mem.stores(info) == {}, "the refused request moved a counter"


def test_the_arena_hands_out_the_last_word_it_has():
    """`ble`, not `blt`: a request for exactly what is left succeeds and leaves nothing."""
    left = mem.arena_free_words()
    info = arena_alloc(left)
    assert info["ret"] == mem.arena_cursor()
    assert case.written(info, mem.GEMDOS_POOL_FREE_WORDS, 2) == 0


def test_a_request_for_no_words_still_stores_both_counters():
    """A zero request is not a special case in the ROM: it passes the compare, subtracts nothing,
    answers the cursor and stores both counters back unchanged. The two stores are named as settled
    below because nothing else in this battery can make them move — which is the honest statement
    that this case proves the ANSWER and not the stores."""
    info = arena_alloc(0, settled=(
        (mem.GEMDOS_POOL_USED_WORDS, 2, "a zero request stores the cursor back unchanged"),
        (mem.GEMDOS_POOL_FREE_WORDS, 2, "...and the remaining-words counter likewise")))
    assert info["ret"] == mem.arena_cursor()


@pytest.mark.parametrize("words", (0x8000, 0xffff))
def test_the_words_compare_is_a_signed_word_so_bit_fifteen_reads_as_a_shortfall(words):
    """`cmp.w $8780,d0 / ble` compares SIGNED words, so a request with bit 15 set looks NEGATIVE and
    is granted however little is left — and the subtraction then wraps the counter.

    Not reachable from `gemdos_pool_get`, whose largest request is `class * 8 + 1`: it is the
    arithmetic the ROM wrote, and a reconstruction that compared unsigned would refuse exactly
    these. The same distinction the project already drives on `Setexc`'s word index.
    """
    info = arena_alloc(words)
    assert info["ret"] == mem.arena_cursor(), "a negative-looking request was refused"
    assert case.written(info, mem.GEMDOS_POOL_FREE_WORDS, 2) == \
        (mem.arena_free_words() - words) & 0xFFFF


@pytest.mark.parametrize("used", (0x3fff, 0x4000, 0x8000))
def test_the_cursor_is_doubled_inside_a_word_and_then_sign_extended(used):
    """`asl.w #1 / ext.l` — so a cursor at or above $4000 forms a NEGATIVE byte offset and the
    record lands BELOW the arena, wrapping the 68000's address space rather than running past it.

    Unreachable from the 8000 words the init writes (the largest offset it can form is $3e80), and
    driven for the same reason as the case above: the reconstruction must be of the ROM's arithmetic
    and not of the one a reader would assume. The routine writes no memory but the two counters, so
    an address outside RAM costs this case nothing.
    """
    info = arena_alloc(1, pokes=counter_pokes(used=used, left=0x7fff))
    offset = (used * 2) & 0xFFFF
    expected = (mem.GEMDOS_POOL_ARENA + (offset - 0x10000 if offset & 0x8000 else offset)) & 0xFFFFFFFF
    assert info["ret"] == expected


# ---- pool_get, $fc7f1a ---------------------------------------------------------------------------

def pool_get(size_class, pokes=None, settled=()):
    def glue(lib, buf):
        return lib.gemdos_pool_get(buf, size_class)

    return mem.run(addrs.GEMDOS_POOL_GET, glue,
                   {**case.word_arg(size_class), **(pokes or {})}, settled=settled)


@pytest.mark.parametrize("size_class,record_bytes", ((mem.MD_SIZE_CLASS, mem.MD_BYTES),
                                                     (mem.BASEPAGE_SIZE_CLASS, BASEPAGE_BYTES)))
def test_a_class_is_eight_words_and_the_record_is_cut_below_its_own_class_word(size_class,
                                                                               record_bytes):
    """`asl.w #3` turns the class into the record's size in WORDS, so class 1 is a 16-byte memory
    descriptor and class 16 the 256-byte basepage GEMDOS's init allocates for the root process. The
    arena request is one word MORE — the class word the record is cut below — and the answer points
    past it.

    THE CLEAR IS NAMED AS SETTLED here: the arena above the cursor is virgin BSS and already zero
    (its own case above), so writing zeroes over it moves no byte. What attributes the clear is the
    RECYCLED case below, where the record comes back holding the fields of the block it last
    described.
    """
    info = pool_get(size_class)
    assert info["ret"] == mem.arena_cursor() + mem.POOL_CLASS_HEADER_BYTES
    assert case.written(info, mem.arena_cursor(), 2) == size_class
    assert case.written(info, mem.GEMDOS_POOL_USED_WORDS, 2) == \
        mem.arena_used_words() + record_bytes // 2 + 1


def test_a_recycled_record_is_popped_from_its_class_chain_and_cleared():
    """The other arm, and the one that attributes the clear. The chain's head becomes the answer,
    the chain advances to the record's own first longword, and the sixteen bytes the record was
    holding — the fields of the block it last described — are zeroed, INCLUDING the longword the
    chain link was just read out of. The arena is not touched at all.
    """
    staged = RECYCLED
    first, second = staged.recycled
    info = pool_get(mem.MD_SIZE_CLASS, pokes=staged.pokes)
    assert info["ret"] == first
    assert case.written_long(info, CLASS_ONE_CHAIN) == second
    for field in (addrs.MD_LINK, addrs.MD_START, addrs.MD_LENGTH, addrs.MD_OWNER):
        assert case.written_long(info, first + field) == 0
    assert mem.GEMDOS_POOL_USED_WORDS not in mem.stores(info), "the recycled arm bumped the arena"


def test_a_spent_arena_answers_nothing_and_stores_nothing():
    """THE DESCRIPTOR POOL RUNNING OUT, which is the failure TOS 1.02 is known for: the answer is 0
    and no byte moves, so the caller cannot tell it from any other refusal."""
    staged = mem.stage(ONE_USED, arena_words_left=mem.MD_ARENA_WORDS - 1)
    info = pool_get(mem.MD_SIZE_CLASS, pokes=staged.pokes)
    assert info["ret"] == 0
    assert mem.stores(info) == {}


def test_a_spent_arena_is_no_obstacle_while_the_class_chain_has_a_record():
    """...and the two arms are independent: a chain with a record on it is popped however little
    arena is left, which is what makes a freed descriptor worth having."""
    staged = mem.stage(ONE_USED, recycled=1, arena_words_left=0)
    info = pool_get(mem.MD_SIZE_CLASS, pokes=staged.pokes)
    assert info["ret"] == staged.recycled[0]


# ---- pool_free, $fc7f9c ---------------------------------------------------------------------------

def pool_free(record, pokes=None, settled=()):
    def glue(lib, buf):
        lib.gemdos_pool_free(buf, record)

    return mem.run(addrs.GEMDOS_POOL_FREE, glue, {**case.long_args(record), **(pokes or {})},
                   width=case.NO_RESULT, settled=settled)


def test_a_record_is_pushed_onto_the_chain_its_own_class_word_names():
    """The class is read from BELOW the record, which is the whole reason `gemdos_pool_get` wrote it
    there: `gemdos_pool_free` knows nothing about its argument but the address."""
    staged = PLAIN
    freed = staged.spans[0].md
    info = pool_free(freed, pokes=staged.pokes)
    assert case.written_long(info, CLASS_ONE_CHAIN) == freed
    assert case.written_long(info, freed + addrs.MD_LINK) == 0, (
        "the record's first longword becomes the chain link, and the chain was empty")


def test_the_chain_is_a_stack_so_the_newest_record_is_the_one_the_pool_hands_back():
    """Push onto a chain that already has records: the old head becomes this record's link."""
    staged = mem.stage(ONE_USED, recycled=1)
    freed = staged.spans[0].md
    info = pool_free(freed, pokes=staged.pokes)
    assert case.written_long(info, freed + addrs.MD_LINK) == staged.recycled[0]
    assert case.written_long(info, CLASS_ONE_CHAIN) == freed


def test_a_record_of_another_class_lands_on_that_class_s_own_chain():
    """Sharp against a reconstruction that hard-coded class 1: the class word below the record picks
    the chain, and the two chains are four bytes apart. Staged by cutting a BASEPAGE-sized record
    the way `gemdos_pool_get` cuts one, which is what GEMDOS's init did for the root process."""
    record = mem.arena_cursor() + mem.POOL_CLASS_HEADER_BYTES
    pokes = {mem.arena_cursor(): struct.pack(">HI", mem.BASEPAGE_SIZE_CLASS, 0xdeadbeef),
             **counter_pokes(used=mem.arena_used_words() + BASEPAGE_BYTES // 2 + 1,
                             left=mem.arena_free_words() - BASEPAGE_BYTES // 2 - 1)}
    info = pool_free(record, pokes=pokes)
    chain = mem.GEMDOS_P_ROOT + mem.BASEPAGE_SIZE_CLASS * mem.POOL_CHAIN_ENTRY_BYTES
    assert case.written_long(info, chain) == record
    assert CLASS_ONE_CHAIN not in mem.stores(info), "the record was filed under the wrong class"


# ---- the cases this battery has VERIFIED ------------------------------------------------------------
# For `test_boot_snapshot.py`'s register (the mask sweep and the unmodelled-I/O sweep) and, through
# it, for Tier 3. Each row is one of the cases above, built from the same constructors — the rows
# are not a second list of what this file proves.
VERIFIED_CASES = (
    ("gemdos_pool_arena_alloc, a descriptor's words", addrs.GEMDOS_POOL_ARENA_ALLOC,
     dict(mem.ENTRY_REGS), case.word_arg(mem.MD_ARENA_WORDS), None, None, ()),
    ("gemdos_pool_arena_alloc, more than is left", addrs.GEMDOS_POOL_ARENA_ALLOC,
     dict(mem.ENTRY_REGS), case.word_arg(mem.arena_free_words() + 1), None, None, ()),
    ("gemdos_pool_get, cut from the arena", addrs.GEMDOS_POOL_GET, dict(mem.ENTRY_REGS),
     case.word_arg(mem.MD_SIZE_CLASS), None, None, ()),
    ("gemdos_pool_get, popped from the class chain", addrs.GEMDOS_POOL_GET, dict(mem.ENTRY_REGS),
     {**case.word_arg(mem.MD_SIZE_CLASS), **RECYCLED.pokes}, None, None, ()),
    ("gemdos_pool_free, onto an empty chain", addrs.GEMDOS_POOL_FREE, dict(mem.ENTRY_REGS),
     {**case.long_args(PLAIN.spans[0].md), **PLAIN.pokes}, None, None, ()),
)
