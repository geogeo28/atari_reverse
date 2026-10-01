"""AES window rectangles — w_getxptr ($feb4be), w_getsize ($feb53e), newrect ($fe5cee): `src/aes/wrect.c`.

    w_getxptr(which, w):  switch (unsigned) which: 0 &win[w].full  1, 4 &wtree[w].ob_x  2 &win[w].prev  3 &win[w].work
                          (table $fefcca); past 4: D0 as the switch left it — `which` in its low word
    w_getsize(which, w, r): rc_copy(w_getxptr(which, w), r); if which == 4 && r.w && r.h: r.w += 2, r.h += 2
    newrect(tree, w):     the window's list onto the free list (its last link := the free head, the head := the list);
                          its list := 0, WIN_BROKEN cleared; w_getsize(4, w, &gl_mkrect.x); if gl_mkrect.w && .h:
                          gl_mkrect.link := 0; everyobj(tree, 0, w, mkrect, 0, 0, 8); o := get_orect(); o.link := 0;
                          w_getsize(4, w, &o.x); its list := o

All Alcyon C. Seeded with the snapshot's own windows (`aes_rlist`'s docstring): window 0, the desktop, in use, its list
ORECT 79 alone, its tree object the screen (0, 0, 320, 200) — so its WS_TRUE rectangle is (0, 0, 322, 202); windows
1..7 closed, their records and tree objects zero. A second window is window 1 staged OPEN by value (its record in use,
its tree object a child of the root after the desktop — the order the tree walk visits them in) over the snapshot's
desktop; a desktop whose list is several rectangles is mkrect's own cut of the snapshot's (`aes_rlist.after`).

newrect has NO Line-F call word: the window-change redraw hands everyobj its ADDRESS ($fec146 pushes $fe5cee), as
newrect hands everyobj mkrect's ($fe5d68) — so a direct case runs the ROM's newrect, whose everyobj calls the ROM's
mkrect, against the C newrect, whose everyobj calls the C mkrect through the hook; and the door case is the ROM's own
everyobj calling the ROM's newrect over the whole window tree, against the C pair through the hook, both routines.
"""
import pytest

from harness import BASE_IMAGE, _lib, addrs

import aes
import aes_rlist
import routines
import test_aes_oblib_walk as walkmod
import test_aes_rlist as rlist_battery
import vdi
from aes_rlist import (DESKTOP, DESKTOP_ORECT, LAST, MKRECT, free_list_of, list_head, orect, rect_of, walk,
                       window_record, window_rects)
from case import merge_pokes

# `aes/wrect.h`'s constants — the WS_* rectangles and newrect's walk depth.
WRECT = aes.header_constants("wrect.h")
WS_FULL, WS_CURR, WS_PREV, WS_WORK, WS_TRUE = (WRECT[name] for name in ("WS_FULL", "WS_CURR", "WS_PREV", "WS_WORK",
                                                                          "WS_TRUE"))
WS_TRUE_BORDER = WRECT["WS_TRUE_BORDER"]

W_GETXPTR, W_GETSIZE, NEWRECT = "AES_ROM_W_GETXPTR", "AES_ROM_W_GETSIZE", "AES_ROM_NEWRECT"
L, W = vdi.LONG_ARG, vdi.WORD_ARG
aes.declare_alcyon(W_GETXPTR, aes.LONG_ANSWER, (W, W))     # a core over words alone: no image
aes.declare_alcyon(W_GETSIZE, None, (vdi.IMAGE_ARG, W, W, L))
aes.declare_alcyon(NEWRECT, None, (vdi.IMAGE_ARG, L, W))

WINDOW_TREE = aes.AES_WINDOW_TREE                       # gl_wtree's value in the snapshot: the tree newrect is handed
TREE_BYTES = aes.AES_WINDOW_COUNT * aes.OB_BYTES
# Window -1's tree object, the one OB_BYTES below the tree (`muls.w #24`, a signed product), is in the span too.
aes.declare_case_field(WINDOW_TREE - aes.OB_BYTES, aes.OB_BYTES + TREE_BYTES, "the window tree, and object -1 below it")
# w_getsize's answer GRECT, and the words a case lays round it to show what the copy and the border touch.
RECT_AT = aes.RECTS_AT + aes.GRECT_BYTES
DOOR = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))

SCREEN = (0, 0, 320, 200)                               # the desktop's tree object, its WS_CURR
DESKTOP_AREA = (0, 11, 320, 189)                        # ...its full and work areas (below the menu bar)
WINDOW = 1
WINDOW_AT = (100, 50, 80, 60)                           # where window 1 is staged open: over the desktop's middle
WINDOW_TRUE = (100, 50, 80 + WS_TRUE_BORDER, 60 + WS_TRUE_BORDER)


def grown(rect):
    x, y, w, h = rect
    return (x, y, w + WS_TRUE_BORDER, h + WS_TRUE_BORDER) if w and h else rect


def window_object(window):
    return WINDOW_TREE + window * aes.OB_BYTES


def object_rect_pokes(window, rect):
    x, y, w, h = rect
    return aes.object_pokes(WINDOW_TREE, window, X=x, Y=y, WIDTH=w, HEIGHT=h)


def open_window_pokes(window=WINDOW, at=WINDOW_AT, rlist=0):
    """Window `window` OPEN over the snapshot's desktop: its record in use with list `rlist`, and its tree object at
    `at`, the root's last child (the desktop's root has none in the snapshot) — as ob_add links a window wm_open adds."""
    return merge_pokes(aes.field_pokes("WIN", window_record(window), FLAGS=aes.WIN_IN_USE, RLIST=rlist),
                       aes.object_pokes(WINDOW_TREE, aes.OB_ROOT, HEAD=window, TAIL=window),
                       aes.object_pokes(WINDOW_TREE, window, NEXT=aes.OB_ROOT, HEAD=aes.OB_NIL, TAIL=aes.OB_NIL),
                       object_rect_pokes(window, at))


# A WINDOW'S OWN LIST: ORECTs 78, 77, ... — the snapshot's free head on — taken as newrect takes one, the free head
# moved past them (`free_list_of`) and each a list of its own (its link cleared, its rectangle the window's), so a
# staged window owns a list that is not the desktop's.
TAKEN_ORECT = orect(LAST - 1)


def taken_orects_pokes(*rects):
    """ORECTs 78, 77, ... taken, one per rectangle of `rects` (None: its words left as they are)."""
    taken = [aes_rlist.orect_pokes(orect(LAST - 1 - index), link=0, **({} if rect is None else dict(zip("XYWH", rect))))
             for index, rect in enumerate(rects)]
    return merge_pokes(free_list_of(LAST - len(rects)), *taken)


def taken_orect_pokes():
    return taken_orects_pokes(None)


def run(name, arguments, pokes=None, **kwargs):
    """`name` over the leaf machine and `pokes`, over the stale free pool that stands in for the attribution pass on
    the rectangle lists' links (`aes_rlist.UNPOISONED`), mkrect bound for the C everyobj newrect calls."""
    pokes = merge_pokes(aes_rlist.stale_free_pool(), pokes)
    return aes.run_function(name, arguments, aes.leaf_machine(onto=pokes), hook=rlist_battery.MKRECT_HOOK,
                            **{**aes_rlist.UNPOISONED, **kwargs})


# ---- w_getxptr -----------------------------------------------------------------------------------------------------
RECTANGLE_AT = {                                        # which: where w_getxptr answers for window w
    WS_FULL: lambda window: window_record(window) + aes.WIN_FULL,
    WS_CURR: lambda window: window_object(window) + aes.OB_X,
    WS_PREV: lambda window: window_record(window) + aes.WIN_PREV,
    WS_WORK: lambda window: window_record(window) + aes.WIN_WORK,
    WS_TRUE: lambda window: window_object(window) + aes.OB_X,
}


@DOOR
@pytest.mark.parametrize("window", (DESKTOP, 7, -1), ids=("the desktop", "the last window", "window -1, signed"))
@pytest.mark.parametrize("which", sorted(RECTANGLE_AT))
def test_w_getxptr_answers_each_rectangle_s_address(which, window, through_line_f):
    result = aes.run_function(W_GETXPTR, (which, window), aes.leaf_machine(), through_line_f=through_line_f)
    assert result.long_answer() == RECTANGLE_AT[which](window) & 0xFFFFFFFF


@pytest.mark.parametrize("which", (WS_TRUE + 1, -1, 0x7FFF), ids=("5", "-1, unsigned", "$7fff"))
def test_w_getxptr_past_the_table_answers_which_in_the_low_word(which):
    """No arm: D0 as the switch left it. Its low word is `which`; its HIGH word is the caller's D0, which the oracle
    enters as 0 — the C's clear high word — so this pins the low word and leaves the high one honestly unpinned."""
    result = aes.run_function(W_GETXPTR, (which, DESKTOP), aes.leaf_machine())
    assert result.long_answer() & 0xFFFF == which & 0xFFFF


def test_the_snapshot_s_desktop_rectangles_are_what_the_window_get_arms_say():
    """The real data the names rest on: the desktop's full and work areas are below the menu bar, its previous and its
    tree object the whole screen — what wm_start sets them to (`aes/aes.h`, the WIN_* GRECTs)."""
    assert rect_of(BASE_IMAGE, window_record(DESKTOP) + aes.WIN_FULL - aes.ORECT_X) == DESKTOP_AREA
    assert rect_of(BASE_IMAGE, window_record(DESKTOP) + aes.WIN_WORK - aes.ORECT_X) == DESKTOP_AREA
    assert rect_of(BASE_IMAGE, window_record(DESKTOP) + aes.WIN_PREV - aes.ORECT_X) == SCREEN
    assert rect_of(BASE_IMAGE, window_object(DESKTOP) + aes.OB_X - aes.ORECT_X) == SCREEN


# ---- w_getsize -----------------------------------------------------------------------------------------------------
def getsize(which, window, pokes=None, *, rect_at=RECT_AT, **kwargs):
    return aes.run_function(W_GETSIZE, (which, window, rect_at), aes.leaf_machine(onto=pokes), **kwargs)


def grect(image, at):
    return rect_of(image, at - aes.ORECT_X)


@DOOR
@pytest.mark.parametrize("which", sorted(RECTANGLE_AT))
def test_w_getsize_copies_each_of_the_desktop_s_rectangles(which, through_line_f):
    result = getsize(which, DESKTOP, through_line_f=through_line_f)
    source = grect(BASE_IMAGE, RECTANGLE_AT[which](DESKTOP))
    assert grect(result.final, RECT_AT) == (grown(source) if which == WS_TRUE else source)


@pytest.mark.parametrize("w,h", ((0, 60), (80, 0), (0, 0), (1, 1)), ids=("no width", "no height", "empty", "1 x 1"))
def test_w_getsize_grows_ws_true_only_when_both_extents_are_non_zero(w, h):
    result = getsize(WS_TRUE, WINDOW, object_rect_pokes(WINDOW, (5, 6, w, h)))
    assert grect(result.final, RECT_AT) == grown((5, 6, w, h))


def test_w_getsize_grows_by_a_word_add_that_wraps():
    """$ffff + 2 is 1 (`addq.w`), and $7fff + 2 goes negative: no carry into the next word, no saturation."""
    result = getsize(WS_TRUE, WINDOW, object_rect_pokes(WINDOW, (5, 6, 0xFFFF, 0x7FFF)))
    assert result.after(RECT_AT + aes.GRECT_W, 2 * aes.WORD_BYTES) == bytes.fromhex("00018001")


STAGED_RECTS = {WS_FULL: (1, 2, 3, 4), WS_PREV: (5, 6, 7, 8), WS_WORK: (9, 10, 11, 12), WS_CURR: WINDOW_AT}


@pytest.mark.parametrize("which", sorted(STAGED_RECTS))
def test_w_getsize_does_not_grow_any_other_rectangle(which):
    """Window 1 open, its four rectangles all different and non-empty: each copied as it is."""
    record = aes.field_pokes("WIN", window_record(WINDOW), FULL=STAGED_RECTS[WS_FULL], PREV=STAGED_RECTS[WS_PREV],
                             WORK=STAGED_RECTS[WS_WORK])
    result = getsize(which, WINDOW, merge_pokes(open_window_pokes(), record))
    assert grect(result.final, RECT_AT) == STAGED_RECTS[which]


def test_w_getsize_reads_the_extents_back_from_the_copy():
    """The answer laid one WORD over the source (the tree object's y onward): rc_copy's first longword (x, y) lands on
    the source's y and w, its second is read from there — (y, h) — so the copy is (x, y, y, h). Its h is 0, so it is
    NOT grown, while the source's own w and h, read after the copy, are y and y: a C that tested the source would."""
    source = window_object(WINDOW) + aes.OB_X
    rect_at = source + aes.WORD_BYTES
    result = getsize(WS_TRUE, WINDOW, object_rect_pokes(WINDOW, (5, 6, 7, 0)), rect_at=rect_at)
    assert grect(result.final, rect_at) == (5, 6, 6, 0)


def test_w_getsize_grows_the_copy_laid_one_longword_over_its_source():
    """...and one LONGWORD over it: the first longword copied twice, (5, 6, 5, 6) — grown, though the source's w was 0."""
    source = window_object(WINDOW) + aes.OB_X
    result = getsize(WS_TRUE, WINDOW, object_rect_pokes(WINDOW, (5, 6, 0, 8)), rect_at=source + aes.LONG_BYTES)
    assert grect(result.final, source + aes.LONG_BYTES) == grown((5, 6, 5, 6))


def test_w_getsize_into_a_rectangle_below_its_source():
    source = window_object(WINDOW) + aes.OB_X
    result = getsize(WS_TRUE, WINDOW, object_rect_pokes(WINDOW, (5, 6, 7, 8)), rect_at=source - aes.LONG_BYTES)
    assert grect(result.final, source - aes.LONG_BYTES) == grown((5, 6, 7, 8))


def test_w_getsize_into_a_tagged_rectangle_stores_through_the_bus():
    result = getsize(WS_TRUE, DESKTOP, rect_at=RECT_AT | aes.BUS_TAG)
    assert grect(result.final, RECT_AT) == grown(SCREEN)


def test_w_getsize_of_window_minus_one_reads_below_the_tree():
    result = getsize(WS_TRUE, -1, object_rect_pokes(-1, (1, 2, 3, 4)))
    assert grect(result.final, RECT_AT) == grown((1, 2, 3, 4))


# ---- newrect -------------------------------------------------------------------------------------------------------
def newrect(window, pokes=None, *, tree=WINDOW_TREE, **kwargs):
    return run(NEWRECT, (tree, window), pokes, **kwargs)


def flags(result, window):
    return result.word(window_record(window) + aes.WIN_FLAGS)


STALE_LINK = 0x00A5A5A4                                 # an even longword no list holds


def mkrect_cut(result):
    return rect_of(result.final, aes.AES_GL_MKRECT)


def test_newrect_of_the_desktop_rebuilds_its_list_as_its_true_rectangle():
    """Real data alone: ORECT 79 back on the free list's top, then taken again — the desktop's list is ONE ORECT,
    now (0, 0, 322, 202), WIN_BROKEN clear; the walk stops on the desktop itself, so nothing is cut."""
    result = newrect(DESKTOP, aes.field_pokes("WIN", window_record(DESKTOP), FLAGS=aes.WIN_IN_USE | aes.WIN_BROKEN))
    assert walk(result.final, list_head(DESKTOP)) == [DESKTOP_ORECT]
    assert window_rects(result.final, DESKTOP) == [grown(SCREEN)]
    assert mkrect_cut(result) == grown(SCREEN)
    assert flags(result, DESKTOP) == aes.WIN_IN_USE
    assert walk(result.final, aes.AES_ORECT_FREE) == walk(BASE_IMAGE, aes.AES_ORECT_FREE)


def test_newrect_of_a_window_over_the_desktop_cuts_the_desktop_round_it():
    """gl_mkrect's link, staged stale, is cleared before the walk (mkrect never reads it)."""
    stale_link = aes_rlist.orect_pokes(aes.AES_GL_MKRECT, link=STALE_LINK)
    result = newrect(WINDOW, merge_pokes(open_window_pokes(), stale_link))
    assert result.long(aes.AES_GL_MKRECT + aes.ORECT_LINK) == 0
    assert window_rects(result.final, WINDOW) == [WINDOW_TRUE]
    assert flags(result, DESKTOP) == aes.WIN_IN_USE | aes.WIN_BROKEN
    assert aes_rlist.pieces_tile(window_rects(result.final, DESKTOP), DESKTOP_AREA, WINDOW_TRUE)


def desktop_in_four():
    """The desktop's list as mkrect's own run leaves it, cut round window 1's rectangle: four ORECTs."""
    return aes_rlist.after(MKRECT, (WINDOW_TREE, DESKTOP), aes.leaf_machine(onto=aes_rlist.cut_pokes(*WINDOW_TRUE)))


def test_newrect_frees_a_list_of_several_whole_onto_the_free_list():
    """The desktop cut in four first (mkrect's own run), then its newrect: the walk to the list's end crosses three
    links, the last takes the free head, and the four ORECTs head the free list in list order."""
    cut = desktop_in_four()
    four = walk(aes_rlist.make_image(cut), list_head(DESKTOP))
    free_before = walk(aes_rlist.make_image(cut), aes.AES_ORECT_FREE)
    assert len(four) == 4
    result = newrect(DESKTOP, cut)
    assert walk(result.final, list_head(DESKTOP)) == four[:1]
    assert walk(result.final, aes.AES_ORECT_FREE) == four[1:] + free_before


def test_newrect_follows_tagged_links_and_frees_the_head_as_stored():
    tagged = DESKTOP_ORECT | aes.BUS_TAG
    result = newrect(DESKTOP, aes.field_pokes("WIN", window_record(DESKTOP), RLIST=tagged))
    assert window_rects(result.final, DESKTOP) == [grown(SCREEN)]
    assert result.long(DESKTOP_ORECT + aes.ORECT_LINK) == 0, "the list rebuilt from the same ORECT, its link cleared"


@pytest.mark.parametrize("window", (2, 7), ids=("window 2", "the last window"))
def test_newrect_of_a_closed_window_of_the_snapshot_empties_it_and_cuts_nothing(window):
    """The snapshot's windows 1..7: no list, a zero tree object — gl_mkrect zero, and nothing past it (no cut, no
    ORECT taken, gl_mkrect's link left as it was)."""
    stale_link = aes_rlist.orect_pokes(aes.AES_GL_MKRECT, link=STALE_LINK)
    result = newrect(window, stale_link)
    assert mkrect_cut(result) == (0, 0, 0, 0)
    assert result.long(aes.AES_GL_MKRECT + aes.ORECT_LINK) == STALE_LINK
    assert walk(result.final, aes.AES_ORECT_FREE) == walk(BASE_IMAGE, aes.AES_ORECT_FREE)
    assert window_rects(result.final, DESKTOP) == [DESKTOP_AREA]


@pytest.mark.parametrize("rect", ((100, 50, 0, 60), (100, 50, 80, 0)), ids=("no width", "no height"))
def test_newrect_of_a_window_with_no_area_frees_its_list_and_stops(rect):
    """A window whose list is a rectangle of the pool but whose tree object has no width (or height): its list freed,
    nothing cut, no list rebuilt. The border is NOT added, so gl_mkrect keeps the zero."""
    result = newrect(WINDOW, merge_pokes(taken_orect_pokes(), open_window_pokes(at=rect, rlist=TAKEN_ORECT)))
    assert result.long(list_head(WINDOW)) == 0
    assert mkrect_cut(result) == rect
    assert walk(result.final, aes.AES_ORECT_FREE) == walk(BASE_IMAGE, aes.AES_ORECT_FREE)
    assert window_rects(result.final, DESKTOP) == [DESKTOP_AREA]


WRAPPING_EXTENT = 0xFFFE                                # grows by WS_TRUE_BORDER to 0 in a word


@pytest.mark.parametrize("rect", ((100, 50, WRAPPING_EXTENT, 60), (100, 50, 80, WRAPPING_EXTENT)),
                         ids=("width $fffe", "height $fffe"))
def test_newrect_s_area_is_the_grown_rectangle_s(rect):
    """The area test reads gl_mkrect AFTER w_getsize's border ($fe5d4c/$fe5d54), which a word add wraps: an extent of
    $fffe grows to 0, so newrect stops as for no area — its list freed, nothing cut, no list rebuilt — where the tree
    object's extent is not 0."""
    result = newrect(WINDOW, merge_pokes(taken_orect_pokes(), open_window_pokes(at=rect, rlist=TAKEN_ORECT)))
    x, y, w, h = rect
    assert result.long(list_head(WINDOW)) == 0
    assert mkrect_cut(result) == (x, y, (w + WS_TRUE_BORDER) & 0xFFFF, (h + WS_TRUE_BORDER) & 0xFFFF)
    assert walk(result.final, aes.AES_ORECT_FREE) == walk(BASE_IMAGE, aes.AES_ORECT_FREE)
    assert window_rects(result.final, DESKTOP) == [DESKTOP_AREA]


def test_newrect_of_an_exhausted_pool_builds_the_list_at_address_0():
    """No list to free and no ORECT left: get_orect answers 0 and the ROM clears and fills an ORECT AT 0 (on a machine,
    a bus error on the first store — $0..$7 is ROM — which no differential models) and makes it the list."""
    pokes = merge_pokes(free_list_of(0), aes.field_pokes("WIN", window_record(DESKTOP), RLIST=0))
    result = newrect(DESKTOP, pokes)
    assert result.long(list_head(DESKTOP)) == 0
    assert rect_of(result.final, 0) == grown(SCREEN)


def test_newrect_s_window_index_is_signed():
    """Window -1: the record 56 bytes BELOW the table and the tree object 24 below the tree — each `muls.w`. Its list
    (one ORECT) freed, rebuilt from its object, and the walk — stopping on no object — visits the desktop and cuts it."""
    pokes = merge_pokes(taken_orect_pokes(),
                        aes.field_pokes("WIN", window_record(-1), FLAGS=aes.WIN_BROKEN, RLIST=TAKEN_ORECT),
                        object_rect_pokes(-1, WINDOW_AT))
    result = newrect(-1, pokes)
    assert flags(result, -1) == 0
    assert window_rects(result.final, -1) == [WINDOW_TRUE]
    assert flags(result, DESKTOP) == aes.WIN_IN_USE | aes.WIN_BROKEN


# ---- three windows: the desktop, window 1 over it, window 2 over both (the root's children in that order) ----------
LOWER_AT = (40, 30, 100, 80)                            # window 1
UPPER_AT = (100, 50, 80, 60)                            # window 2, over window 1's corner and the desktop
LOWER_TRUE, UPPER_TRUE = grown(LOWER_AT), grown(UPPER_AT)


def three_windows():
    """The desktop with its snapshot list, and windows 1 and 2 open, each its own list of one rectangle — its WS_TRUE
    one, as its own newrect left it (ORECTs 78 and 77)."""
    tree = aes.tree_pokes([aes.node(None, X=0, Y=0, WIDTH=320, HEIGHT=200),
                           aes.node(aes.OB_ROOT, **dict(zip(("X", "Y", "WIDTH", "HEIGHT"), LOWER_AT))),
                           aes.node(aes.OB_ROOT, **dict(zip(("X", "Y", "WIDTH", "HEIGHT"), UPPER_AT)))], at=WINDOW_TREE)
    records = [aes.field_pokes("WIN", window_record(window), FLAGS=aes.WIN_IN_USE, RLIST=orect(LAST - window))
               for window in (1, 2)]
    return merge_pokes(tree, *records, taken_orects_pokes(LOWER_TRUE, UPPER_TRUE))


def test_newrect_of_the_top_window_cuts_every_window_below_it():
    """Window 2: the walk visits the desktop and window 1 — the ROOT'S CHILD, one level down — and stops on window 2,
    so both lists are cut round it and marked broken."""
    result = newrect(2, three_windows())
    assert window_rects(result.final, 2) == [UPPER_TRUE]
    assert flags(result, DESKTOP) == flags(result, 1) == aes.WIN_IN_USE | aes.WIN_BROKEN
    assert aes_rlist.pieces_tile(window_rects(result.final, 1), LOWER_TRUE, UPPER_TRUE)
    assert aes_rlist.pieces_tile(window_rects(result.final, DESKTOP), DESKTOP_AREA, UPPER_TRUE)


def test_newrect_of_a_lower_window_leaves_the_windows_above_it():
    """Window 1: the walk stops on it — the desktop is cut round it, window 2 (above it) is not visited at all."""
    result = newrect(1, three_windows())
    assert window_rects(result.final, 1) == [LOWER_TRUE]
    assert window_rects(result.final, 2) == [UPPER_TRUE]
    assert flags(result, 2) == aes.WIN_IN_USE
    assert aes_rlist.pieces_tile(window_rects(result.final, DESKTOP), DESKTOP_AREA, LOWER_TRUE)


def test_newrect_reads_its_tree_for_the_walk():
    """The tree argument is everyobj's alone (w_getsize reads the window tree by its own address): a copy of the window
    tree with window 1 a child of the root, handed in, is walked; the real tree, where the root has no child, is not
    — so the desktop is cut only through the copy."""
    copy = aes.TREE_AT
    pokes = merge_pokes(open_window_pokes(),
                        aes.tree_pokes([aes.node(None), aes.node(aes.OB_ROOT)], at=copy),
                        aes.object_pokes(WINDOW_TREE, aes.OB_ROOT, HEAD=aes.OB_NIL, TAIL=aes.OB_NIL))
    result = newrect(WINDOW, pokes, tree=copy)
    assert flags(result, DESKTOP) == aes.WIN_IN_USE | aes.WIN_BROKEN
    assert window_rects(result.final, WINDOW) == [WINDOW_TRUE]


# ---- newrect entered as the ROM enters it: everyobj's `jsr (a0)`, over the whole window tree ----------------------
NEWRECT_CORE = getattr(_lib, routines.core_symbol(NEWRECT))


def newrect_called(buf, registers):
    """The C newrect on the window everyobj's call hands it."""
    tree, window, _x, _y = walkmod.frame_of(registers)
    NEWRECT_CORE(buf, tree, window)


BOTH_HOOK = aes.alcyon_object_hook({addrs.AES_ROM_NEWRECT: (b"", newrect_called),
                                    addrs.AES_ROM_MKRECT: (b"", rlist_battery.mkrect_called)})


def test_newrect_through_the_rom_s_everyobj_rebuilds_every_window_bottom_up():
    """The window-change redraw's own call ($fec146): everyobj(gl_wtree, 0, -1, newrect, 0, 0, 8) — each window's list
    rebuilt in visiting order, the desktop first, so the window above it is the one that cuts it."""
    pokes = merge_pokes(aes_rlist.stale_free_pool(), open_window_pokes(rlist=0))
    arguments = (WINDOW_TREE, aes.OB_ROOT, aes.OB_NIL, addrs.AES_ROM_NEWRECT, 0, 0, walkmod.EVERYOBJ_LEVELS)
    result = aes.run_function(walkmod.EVERYOBJ, arguments, aes.leaf_machine(onto=pokes), hook=BOTH_HOOK,
                              **aes_rlist.UNPOISONED)
    assert window_rects(result.final, WINDOW) == [WINDOW_TRUE]
    assert aes_rlist.pieces_tile(window_rects(result.final, DESKTOP), grown(SCREEN), WINDOW_TRUE)


# ---- the registry --------------------------------------------------------------------------------------------------
OVER_THE_FOUR_AT = (60, 40, 150, 100)                   # window 1 moved over every piece the desktop was cut into
# DIRECT rows priced; w_getxptr and w_getsize have Line-F call words and a THROUGH-LINE-F row each; newrect has none
# (only everyobj's `jsr (a0)` reaches it, on the address $fec146 pushes — its door case is the one above).
for _which in sorted(RECTANGLE_AT):
    aes.register(f"WS {_which} of the desktop", W_GETXPTR, (_which, DESKTOP), aes.leaf_machine())
aes.register("WS 1 of the desktop", W_GETXPTR, (WS_CURR, DESKTOP), aes.leaf_machine(), through_line_f=True)
for _which in sorted(RECTANGLE_AT):
    aes.register(f"WS {_which} of the desktop", W_GETSIZE, (_which, DESKTOP, RECT_AT), aes.leaf_machine())
aes.register("WS 4 of the desktop", W_GETSIZE, (WS_TRUE, DESKTOP, RECT_AT), aes.leaf_machine(), through_line_f=True)
_NEWRECT_MACHINE = aes.leaf_machine(onto=merge_pokes(aes_rlist.stale_free_pool(), open_window_pokes()))
aes.register("a window over the desktop", NEWRECT, (WINDOW_TREE, WINDOW), _NEWRECT_MACHINE,
             hook=rlist_battery.MKRECT_HOOK)
aes.register("the desktop alone", NEWRECT, (WINDOW_TREE, DESKTOP), aes.leaf_machine(), hook=rlist_battery.MKRECT_HOOK)
aes.register("a closed window", NEWRECT, (WINDOW_TREE, 2), aes.leaf_machine(), hook=rlist_battery.MKRECT_HOOK)
aes.register("the desktop, its list of four", NEWRECT, (WINDOW_TREE, DESKTOP), aes.leaf_machine(onto=desktop_in_four()),
             hook=rlist_battery.MKRECT_HOOK)
# The WORST realistic row: a window over a desktop already cut in four. Both sides run the ROM's own mkrect (shared
# bytes), so the more pieces lie below the window the nearer 1.0 the ratio — the C's own body is about half the ROM's.
aes.register("a window over the desktop already cut in four", NEWRECT, (WINDOW_TREE, WINDOW),
             aes.leaf_machine(onto=merge_pokes(desktop_in_four(), open_window_pokes(at=OVER_THE_FOUR_AT))),
             hook=rlist_battery.MKRECT_HOOK)
