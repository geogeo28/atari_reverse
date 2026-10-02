"""AES rectangle lists — or_start ($fe5a62), get_orect ($fe5aac), mkpiece ($fe5acc), brkrct ($fe5ba8), mkrect ($fe5c9a):
`src/aes/rlist.c`.

    or_start():            free := 0; for i in 0..79: pool[i].link := free; free := &pool[i]
    get_orect():           o := free; if o: free := o->link; return o                    (0 when empty: no check after)
    mkpiece(side, cut, r): p := get_orect(); p->link := r; p.x, p.w := r.x, r.w
                           p.y := max(r.y, cut.y); p.h := min(r.far_y, cut.far_y) - p.y   (p.y as stored)
                           side 0 above: p.y := r.y, p.h := cut.y - r.y   1 left: p.w := cut.x - r.x
                                2 right: p.x := cut.far_x, p.w := r.far_x - cut.far_x   3 below: likewise in y
    brkrct(cut, r, prev):  no overlap (signed word edges) -> 0; else the four "is there a piece" flags first, then
                           each piece linked after prev in turn, the last takes r's link, r onto the free list
    mkrect(tree, w):       walk window w's list from its head: brkrct(&gl_mkrect, r, prev) -> mark broken and go on
                           after the last piece, or step over r

All Alcyon C. Seeded with the snapshot's own pool (`aes_rlist`'s docstring): window 0's list is ORECT 79 alone, the
free list ORECT 78 down to 0; longer lists are mkrect's own cuts of it, chained (`case.continued`), and the fresh pool
is or_start's own run. THE EXHAUSTED POOL is the ROM's machine too: get_orect answers 0, and mkpiece builds its piece
AT ADDRESS 0 with no check (on the machine the first store is a bus error — $0..$7 is ROM — which no differential
models; here both sides write the 12 bytes and go on, and brkrct's answer then says "no overlap" for a cut it made).
"""
import itertools

import pytest

from harness import BASE_IMAGE, _lib, addrs

import aes
import aes_rlist
import case
import routines
import test_aes_oblib_walk as walkmod
from aes_rlist import (BRKRCT, DESKTOP, DESKTOP_ORECT, GET_ORECT, LAST, MKPIECE, MKRECT, OR_START,
                       SNAPSHOT_FREE_HEAD, cut_pokes, free_list_of, list_head, orect, orect_pokes, rect_of,
                       walk, window_record, window_rects)
from case import merge_pokes

DOOR = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
DESKTOP_AREA = (0, 11, 320, 189)                            # the snapshot's window 0 work area
MIDDLE_CUT = (100, 50, 80, 60)                              # a window over the desktop's middle
EXHAUSTED_AT = 0                                            # where a piece of an exhausted pool is built
TREE = 0                                                    # mkrect's tree argument: never read
SIDES = aes_rlist.ORECT_PIECE_SIDES                         # above, left, right, below
ORECT_PIECE_BELOW = aes_rlist.ORECT_PIECE_BELOW


# THE ATTRIBUTION PASS stays ON for or_start and for every case below that passes `POISONED`: those that store nothing
# they read back — a cut that misses or leaves no piece, an empty or exhausted pool, a window with no list. Every other
# case of the four routines opts out (`aes_rlist.UNPOISONED` says why; measured, forced on: all 60 of them red).
POISONED = {"poison": True}


def run(name, arguments, pokes=None, **kwargs):
    """`name` over the leaf machine and `pokes` — every routine but or_start unpoisoned unless the case keeps the pass
    (`POISONED`), over the stale free pool that stands in for the pass."""
    if name == OR_START:
        return aes.run_function(name, arguments, aes.leaf_machine(onto=pokes), **kwargs)
    pokes = merge_pokes(aes_rlist.stale_free_pool(), pokes)
    return aes.run_function(name, arguments, aes.leaf_machine(onto=pokes), **{**aes_rlist.UNPOISONED, **kwargs})


def free_head(result):
    return result.long(aes.AES_ORECT_FREE)


def stored(result):
    """The addresses the ROM's run stored to, but for its stack frames and the Line-F mask word."""
    mask_word = range(aes.AES_LINEF_MASK_WORD, aes.AES_LINEF_MASK_WORD + aes.WORD_BYTES)
    return {at for at in result.info["writes"] if at not in case.STACK_BAND and at not in mask_word}


# ---- or_start ------------------------------------------------------------------------------------------------------

@DOOR
def test_or_start_threads_the_whole_pool_the_last_on_top(through_line_f):
    result = run(OR_START, (), through_line_f=through_line_f)
    assert walk(result.final, aes.AES_ORECT_FREE) == [orect(index) for index in reversed(range(aes.AES_ORECT_COUNT))]
    assert result.long(list_head(DESKTOP)) == DESKTOP_ORECT, "a window's list head is not or_start's"


def test_or_start_ends_the_list_on_the_head_it_cleared():
    """A stale head: the `clr.l` is what ORECT 0's link reads, so the list ends there and not on the stale value."""
    result = run(OR_START, (), aes.field_pokes("AES", ORECT_FREE=0x00A5A5A4))
    assert result.long(orect(0) + aes.ORECT_LINK) == 0


# ---- get_orect -----------------------------------------------------------------------------------------------------

@DOOR
def test_get_orect_unlinks_the_head(through_line_f):
    result = run(GET_ORECT, (), through_line_f=through_line_f)
    assert result.long_answer() == SNAPSHOT_FREE_HEAD
    assert free_head(result) == orect(LAST - 2)


def test_get_orect_takes_the_last_one():
    result = run(GET_ORECT, (), free_list_of(1))
    assert result.long_answer() == orect(0) and free_head(result) == 0


def test_get_orect_of_an_empty_list_answers_0_and_stores_nothing():
    result = run(GET_ORECT, (), free_list_of(0), **POISONED)
    assert result.long_answer() == 0
    assert not stored(result)


def test_get_orect_follows_a_tagged_head_on_the_bus_and_answers_it_as_stored():
    """A head with a top byte (brkrct frees whatever pointer it was handed): answered with its top byte, its link read
    through 24 bits."""
    result = run(GET_ORECT, (), aes.field_pokes("AES", ORECT_FREE=orect(5) | aes.BUS_TAG))
    assert result.long_answer() == orect(5) | aes.BUS_TAG
    assert free_head(result) == orect(4)


# ---- mkpiece -------------------------------------------------------------------------------------------------------
CUT_AT = aes.AES_GL_MKRECT
PIECES_OF_THE_MIDDLE_CUT = {                                # side: the piece of the desktop the middle cut leaves
    0: (0, 11, 320, 39),
    1: (0, 50, 100, 60),
    2: (180, 50, 140, 60),
    3: (0, 110, 320, 90),
    4: (0, 50, 320, 60),                                    # past the four: the common piece alone
    -1: (0, 50, 320, 60),
}


def mkpiece(side, cut=MIDDLE_CUT, pokes=None, *, cut_at=CUT_AT, rect_at=DESKTOP_ORECT, **kwargs):
    return run(MKPIECE, (side, cut_at, rect_at), merge_pokes(pokes, cut_pokes(*cut) if cut else None), **kwargs)


@DOOR
@pytest.mark.parametrize("side", sorted(PIECES_OF_THE_MIDDLE_CUT))
def test_mkpiece_makes_each_side_s_piece(side, through_line_f):
    result = mkpiece(side, through_line_f=through_line_f)
    assert result.long_answer() == SNAPSHOT_FREE_HEAD
    assert rect_of(result.final, SNAPSHOT_FREE_HEAD) == PIECES_OF_THE_MIDDLE_CUT[side]
    assert result.long(SNAPSHOT_FREE_HEAD + aes.ORECT_LINK) == DESKTOP_ORECT, "the piece is linked to the rectangle"
    assert rect_of(result.final, DESKTOP_ORECT) == DESKTOP_AREA


@pytest.mark.parametrize("side", range(SIDES))
def test_mkpiece_s_edges_are_words_that_wrap_compared_signed(side):
    """A rectangle whose far edges pass $7fff: its far y is NEGATIVE, so the common height's min takes it, and the
    right piece's width wraps round — 68000 words, signed (an unsigned min would take the cut's $7200: height $100)."""
    pokes = orect_pokes(orect(3), X=0x7000, Y=0x7000, W=0x2000, H=0x2000)
    result = mkpiece(side, (0x7100, 0x7100, 0x100, 0x100), pokes, rect_at=orect(3))
    expected = {0: (0x7000, 0x7000, 0x2000, 0x100), 1: (0x7000, 0x7100, 0x100, 0x1F00),
                2: (0x7200, 0x7100, 0x1E00, 0x1F00), 3: (0x7000, 0x7200, 0x2000, 0x1E00)}[side]
    assert rect_of(result.final, SNAPSHOT_FREE_HEAD) == expected


TALL_CUT = (100, 50, 80, 300)                               # ...reaching below the desktop


@pytest.mark.parametrize("cut", (MIDDLE_CUT, TALL_CUT), ids=("inside", "reaching below"))
@pytest.mark.parametrize("side", range(SIDES))
def test_mkpiece_over_the_rectangle_itself_reads_its_own_stores(side, cut):
    """The ORDER, which only an overlap shows: the free list's head IS the rectangle (a corrupt pool), so the piece
    overwrites it field by field and every later read sees the stores — the common height's far edge from the y just
    stored (which the tall cut's min then takes), the above piece's height from it, the right piece's width from the x
    it just stored."""
    result = mkpiece(side, cut, aes.field_pokes("AES", ORECT_FREE=DESKTOP_ORECT))
    assert result.long_answer() == DESKTOP_ORECT
    assert result.long(DESKTOP_ORECT + aes.ORECT_LINK) == DESKTOP_ORECT


@pytest.mark.parametrize("side", range(SIDES))
def test_mkpiece_over_the_cut_reads_its_own_stores(side):
    """...and the head IS the cut: the piece's x and w land on the cut's before its y and far edges are read."""
    cut_at = orect(LAST - 1)
    result = mkpiece(side, None, orect_pokes(cut_at, X=100, Y=50, W=80, H=60), cut_at=cut_at)
    assert result.long_answer() == cut_at


@pytest.mark.parametrize("side", range(SIDES))
def test_mkpiece_of_an_exhausted_pool_builds_its_piece_at_0(side):
    result = mkpiece(side, pokes=free_list_of(0), **POISONED)
    assert result.long_answer() == EXHAUSTED_AT
    assert rect_of(result.final, EXHAUSTED_AT) == PIECES_OF_THE_MIDDLE_CUT[side]
    assert result.long(EXHAUSTED_AT + aes.ORECT_LINK) == DESKTOP_ORECT


def test_mkpiece_puts_both_pointers_on_the_bus_and_links_the_rectangle_as_handed_in():
    result = mkpiece(2, cut_at=CUT_AT | aes.BUS_TAG, rect_at=DESKTOP_ORECT | aes.BUS_TAG)
    assert rect_of(result.final, SNAPSHOT_FREE_HEAD) == PIECES_OF_THE_MIDDLE_CUT[2]
    assert result.long(SNAPSHOT_FREE_HEAD + aes.ORECT_LINK) == DESKTOP_ORECT | aes.BUS_TAG


BUS_TOP_ORECT = 0xFFFFFFFC                                  # an ORECT whose words lie past the top of the bus


def test_mkpiece_s_words_are_each_summed_then_put_on_the_bus():
    """A cut pointer 4 below the top of the address space: each word's `d16(An)` sum wraps past it to the bottom of
    the bus, so its x, y, w and h are the bytes at 0..7 (the ROM's first eight, mirrored there). Put on the bus
    BEFORE the offset is added, they would be read above the top of the 24-bit bus."""
    wrapped = aes_rlist.make_image({})
    result = mkpiece(ORECT_PIECE_BELOW, None, cut_at=BUS_TOP_ORECT)
    cut_y, cut_h = (case.word_in(wrapped, aes.ORECT_Y - aes.ORECT_X), case.word_in(wrapped, aes.ORECT_H - aes.ORECT_X))
    assert rect_of(result.final, SNAPSHOT_FREE_HEAD)[1] == aes.signed(cut_y + cut_h)


# ---- brkrct --------------------------------------------------------------------------------------------------------
SIDE_OFFSET = 10


def cut_leaving(sides):
    """A cut of the desktop leaving a piece on exactly `sides` (a set of 0..3): each edge inside the desktop's, or
    past it."""
    x, y, w, h = DESKTOP_AREA
    left = x + SIDE_OFFSET if 1 in sides else x - SIDE_OFFSET
    top = y + SIDE_OFFSET if 0 in sides else y - SIDE_OFFSET
    right = x + w - SIDE_OFFSET if 2 in sides else x + w + SIDE_OFFSET
    bottom = y + h - SIDE_OFFSET if 3 in sides else y + h + SIDE_OFFSET
    return left, top, right - left, bottom - top


ALL_SIDE_SETS = [frozenset(combo) for count in range(5) for combo in itertools.combinations(range(4), count)]


def brkrct(cut, pokes=None, *, cut_at=CUT_AT, rect_at=DESKTOP_ORECT, prior=list_head(DESKTOP), **kwargs):
    return run(BRKRCT, (cut_at, rect_at, prior), merge_pokes(pokes, cut_pokes(*cut) if cut else None), **kwargs)


@pytest.mark.parametrize("sides", ALL_SIDE_SETS, ids=lambda sides: "".join("ALRB"[side] for side in sorted(sides))
                         or "none")
def test_brkrct_replaces_the_rectangle_by_the_pieces_round_the_cut(sides):
    cut = cut_leaving(sides)
    result = brkrct(cut, **(POISONED if not sides else {}))
    pieces = [orect(LAST - 1 - taken) for taken in range(len(sides))]
    assert walk(result.final, list_head(DESKTOP)) == pieces
    assert aes_rlist.pieces_tile(window_rects(result.final, DESKTOP), DESKTOP_AREA, cut)
    assert result.long_answer() == (pieces[-1] if pieces else list_head(DESKTOP))
    assert free_head(result) == DESKTOP_ORECT
    assert result.long(DESKTOP_ORECT + aes.ORECT_LINK) == orect(LAST - 1 - len(sides)), "freed onto the rest"


@DOOR
def test_brkrct_cuts_the_desktop_in_four(through_line_f):
    result = brkrct(MIDDLE_CUT, through_line_f=through_line_f)
    assert window_rects(result.final, DESKTOP) == [PIECES_OF_THE_MIDDLE_CUT[side] for side in range(4)]


def test_brkrct_of_a_cut_exactly_the_rectangle_leaves_no_piece():
    """Every edge equal: none of the four flags is set (each a strict compare), and the rectangle is freed."""
    result = brkrct(DESKTOP_AREA, **POISONED)
    assert walk(result.final, list_head(DESKTOP)) == []
    assert result.long_answer() == list_head(DESKTOP)


DISJOINT = {
    "right of it": (320, 11, 50, 50),                       # the rectangle's far x on the cut's x: `ble`, no overlap
    "left of it": (-50, 11, 50, 50),
    "below it": (0, 200, 50, 50),
    "above it": (0, -39, 50, 50),
    "far past it": (1000, 1000, 5, 5),
}


@pytest.mark.parametrize("where", sorted(DISJOINT))
def test_brkrct_of_a_cut_that_misses_answers_0_and_touches_nothing(where):
    result = brkrct(DISJOINT[where], **POISONED)
    assert result.long_answer() == 0
    assert not stored(result)


def test_brkrct_s_overlap_is_a_signed_compare_of_wrapped_edges():
    """A rectangle from $7000 wide $2000: its far x is $9000, NEGATIVE as a word, so a cut at $7100 is past it by the
    ROM's `ble` — no overlap, though the two share $7100..$7200 unsigned."""
    pokes = orect_pokes(orect(3), link=0, X=0x7000, Y=0, W=0x2000, H=100)
    result = brkrct((0x7100, 0, 0x100, 50), pokes, rect_at=orect(3), **POISONED)
    assert result.long_answer() == 0


def test_brkrct_over_the_pool_or_start_leaves_takes_the_rectangle_itself_for_its_first_piece():
    """REAL DATA reaching the overlap: after or_start (the ROM's own run) the desktop's ORECT is the free list's head
    AND window 0's list — so the first piece brkrct makes IS the rectangle it is cutting, and every read after it
    sees the piece's stores."""
    result = brkrct(MIDDLE_CUT, aes_rlist.after_or_start(), **POISONED)
    assert result.long_answer() == orect(LAST - 3)


def test_brkrct_of_an_exhausted_pool_links_its_pieces_at_0():
    """Two ORECTs left and four pieces to make: the third and fourth are built at 0 (the same 12 bytes twice), the
    rectangle's link stored there, and the answer is 0 — the "no overlap" answer, for a cut it made."""
    result = brkrct(MIDDLE_CUT, free_list_of(2))
    assert result.long_answer() == EXHAUSTED_AT
    assert walk(result.final, list_head(DESKTOP)) == [orect(1), orect(0)]
    assert free_head(result) == DESKTOP_ORECT


def test_brkrct_carries_every_pointer_as_handed_in():
    """All three pointers with a top byte: followed through 24 bits, and stored as they came — the answer is the
    tagged prior when the cut covers the rectangle, and the tagged rectangle is the free list's new head."""
    result = brkrct(cut_leaving(frozenset()), cut_at=CUT_AT | aes.BUS_TAG, rect_at=DESKTOP_ORECT | aes.BUS_TAG,
                    prior=list_head(DESKTOP) | aes.BUS_TAG, **POISONED)
    assert result.long_answer() == list_head(DESKTOP) | aes.BUS_TAG
    assert free_head(result) == DESKTOP_ORECT | aes.BUS_TAG


def test_brkrct_s_pieces_link_through_a_tagged_prior():
    result = brkrct(MIDDLE_CUT, prior=list_head(DESKTOP) | aes.BUS_TAG)
    assert window_rects(result.final, DESKTOP) == [PIECES_OF_THE_MIDDLE_CUT[side] for side in range(4)]


# ---- mkrect --------------------------------------------------------------------------------------------------------
SECOND_CUT = (150, 30, 100, 100)                            # crosses the above, right and below pieces, misses the left


def mkrect(window, cut, pokes=None, *, tree=TREE, **kwargs):
    return run(MKRECT, (tree, window), merge_pokes(pokes, cut_pokes(*cut)), **kwargs)


def window_flags(result, window):
    return result.word(window_record(window) + aes.WIN_FLAGS)


def test_mkrect_cuts_the_desktop_s_list_and_marks_it_broken():
    result = mkrect(DESKTOP, MIDDLE_CUT)
    assert window_rects(result.final, DESKTOP) == [PIECES_OF_THE_MIDDLE_CUT[side] for side in range(4)]
    assert window_flags(result, DESKTOP) == aes.WIN_IN_USE | aes.WIN_BROKEN


def test_mkrect_of_a_cut_that_misses_leaves_the_list_and_the_flags():
    result = mkrect(DESKTOP, DISJOINT["far past it"], **POISONED)
    assert window_rects(result.final, DESKTOP) == [DESKTOP_AREA]
    assert window_flags(result, DESKTOP) == aes.WIN_IN_USE


def test_mkrect_walks_a_list_of_several_cutting_some_and_stepping_over_the_rest():
    first = case.continued(mkrect(DESKTOP, MIDDLE_CUT))
    before = window_rects(aes_rlist.make_image(first), DESKTOP)
    assert len(before) == 4
    result = mkrect(DESKTOP, SECOND_CUT, first)
    after = window_rects(result.final, DESKTOP)
    assert before[1] in after, "the left piece, which the cut misses, is stepped over"
    covered = set().union(*(aes_rlist.area(rect) for rect in after))
    assert covered == aes_rlist.uncovered(DESKTOP_AREA, MIDDLE_CUT) - aes_rlist.area(SECOND_CUT)


def test_mkrect_of_a_window_with_no_list_does_nothing():
    result = mkrect(1, MIDDLE_CUT, **POISONED)
    assert not stored(result)


def test_mkrect_s_window_index_is_signed():
    """Window -1: the record 56 bytes BELOW the table (`muls.w`), its list head staged to name a rectangle the cut
    overlaps — broken, and its flags word (at the table less 56) marked. Unsigned, the index reads 3.5 MB up."""
    below = window_record(-1)
    rect_at = aes.RECTS_AT
    pokes = merge_pokes(aes.field_pokes("WIN", below, RLIST=rect_at), orect_pokes(rect_at, link=0, X=0, Y=0, W=50, H=50))
    result = mkrect(-1, (10, 10, 10, 10), pokes)
    assert result.word(below + aes.WIN_FLAGS) == aes.WIN_BROKEN
    assert len(walk(result.final, list_head(-1))) == 4


def test_mkrect_of_an_exhausted_pool_loses_the_last_pieces_and_is_not_marked_broken():
    """Two ORECTs left: brkrct builds the third and fourth pieces at 0 and answers 0 — which mkrect reads as "the
    cut missed", so the window is NOT marked broken, its list ends after the two real pieces, and the walk goes on
    from the rectangle brkrct already freed."""
    result = mkrect(DESKTOP, MIDDLE_CUT, free_list_of(2))
    assert window_flags(result, DESKTOP) == aes.WIN_IN_USE
    assert walk(result.final, list_head(DESKTOP)) == [orect(1), orect(0)]


def test_mkrect_never_reads_its_tree():
    result = mkrect(DESKTOP, MIDDLE_CUT, tree=0xFFFFFFFF)
    assert window_flags(result, DESKTOP) == aes.WIN_IN_USE | aes.WIN_BROKEN


# ---- mkrect entered as the ROM enters it: everyobj's `jsr (a0)` ----------------------------------------------------
# mkrect has no Line-F call word: newrect hands everyobj its ADDRESS ($fe5d68 pushes $fe5c9a) and everyobj calls it for
# each window of the window tree over the 10-byte Alcyon frame (`staged_call.h`, call_alcyon_object). So the door case
# is the ROM's own everyobj calling the ROM's own mkrect, against the C everyobj calling the C mkrect through the hook
# — which also pins everyobj's VISITING ORDER: each window's cut takes its pieces off the one free list in turn, so the
# desktop visited first takes the free list's head.
WINDOW_TREE = aes.TREE_AT                                   # the desktop (0) and window 1, its child


def mkrect_called(buf, registers):
    """The C mkrect on the object (the window) everyobj's call hands it."""
    tree, window, _x, _y = walkmod.frame_of(registers)
    MKRECT_CORE(buf, tree, window)


MKRECT_CORE = getattr(_lib, routines.core_symbol(MKRECT))
MKRECT_HOOK = aes.alcyon_object_hook({addrs.AES_ROM_MKRECT: (b"", mkrect_called)})


@pytest.mark.parametrize("last", (aes.OB_NIL, 1), ids=("the whole tree", "the desktop alone"))
def test_mkrect_through_the_rom_s_everyobj_cuts_each_window_in_visiting_order(last):
    window1 = window_record(1)
    pokes = merge_pokes(aes_rlist.stale_free_pool(), aes.tree_pokes([aes.node(None), aes.node(0)], at=WINDOW_TREE),
                        cut_pokes(*MIDDLE_CUT), aes.field_pokes("WIN", window1, RLIST=aes.RECTS_AT),
                        orect_pokes(aes.RECTS_AT, link=0, X=0, Y=0, W=200, H=150))
    arguments = (WINDOW_TREE, aes.OB_ROOT, last, addrs.AES_ROM_MKRECT, 0, 0, walkmod.EVERYOBJ_LEVELS)
    result = aes.run_function(walkmod.EVERYOBJ, arguments, aes.leaf_machine(onto=pokes), hook=MKRECT_HOOK,
                              **aes_rlist.UNPOISONED)
    free = walk(BASE_IMAGE, aes.AES_ORECT_FREE)
    assert walk(result.final, list_head(DESKTOP)) == free[:SIDES]
    assert window_flags(result, DESKTOP) == aes.WIN_IN_USE | aes.WIN_BROKEN
    window1_broken = result.word(window1 + aes.WIN_FLAGS) & aes.WIN_BROKEN
    assert bool(window1_broken) == (last == aes.OB_NIL), "window 1 is visited only when the walk reaches it"


# ---- the registry --------------------------------------------------------------------------------------------------
# DIRECT rows priced, each routine with a Line-F-free entry has its THROUGH-LINE-F row (mkrect has no call word: only
# everyobj's `jsr (a0)` reaches it, on the address newrect pushes, $fe5d68 — its door case is the one above).
aes.register("the snapshot's pool", OR_START, (), aes.leaf_machine())
aes.register("the snapshot's pool", OR_START, (), aes.leaf_machine(), through_line_f=True)
aes.register("the snapshot's head", GET_ORECT, (), aes.leaf_machine())
aes.register("an empty list", GET_ORECT, (), aes.leaf_machine(onto=free_list_of(0)))
aes.register("the snapshot's head", GET_ORECT, (), aes.leaf_machine(), through_line_f=True)
for _side in range(5):
    aes.register(f"side {_side} of the desktop", MKPIECE, (_side, CUT_AT, DESKTOP_ORECT),
                 aes.leaf_machine(onto=cut_pokes(*MIDDLE_CUT)))
aes.register("side 2 of the desktop", MKPIECE, (2, CUT_AT, DESKTOP_ORECT), aes.leaf_machine(onto=cut_pokes(*MIDDLE_CUT)),
             through_line_f=True)
for _where in ("right of it", "above it"):
    aes.register(f"a cut {_where}", BRKRCT, (CUT_AT, DESKTOP_ORECT, list_head(DESKTOP)),
                 aes.leaf_machine(onto=cut_pokes(*DISJOINT[_where])))
for _sides in (frozenset(), frozenset({1}), frozenset(range(4))):
    aes.register(f"{len(_sides)} pieces of the desktop", BRKRCT, (CUT_AT, DESKTOP_ORECT, list_head(DESKTOP)),
                 aes.leaf_machine(onto=cut_pokes(*cut_leaving(_sides))))
aes.register("4 pieces of the desktop", BRKRCT, (CUT_AT, DESKTOP_ORECT, list_head(DESKTOP)),
             aes.leaf_machine(onto=cut_pokes(*MIDDLE_CUT)), through_line_f=True)
aes.register("the desktop in four", MKRECT, (TREE, DESKTOP), aes.leaf_machine(onto=cut_pokes(*MIDDLE_CUT)))
aes.register("a cut that misses", MKRECT, (TREE, DESKTOP), aes.leaf_machine(onto=cut_pokes(*DISJOINT["far past it"])))
aes.register("a window with no list", MKRECT, (TREE, 1), aes.leaf_machine(onto=cut_pokes(*MIDDLE_CUT)))
aes.register("a list of four, cut again", MKRECT, (TREE, DESKTOP),
             aes.leaf_machine(onto=merge_pokes(aes_rlist.after(MKRECT, (TREE, DESKTOP),
                                                               aes.leaf_machine(onto=cut_pokes(*MIDDLE_CUT))),
                                               cut_pokes(*SECOND_CUT))))
