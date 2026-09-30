"""AES ob_find ($fea0a8) and the GRECT helpers it shares with the object library — ob_fs ($fea4b6), ob_actxywh
($fea4e8), ob_relxywh ($fea538), ob_setxywh ($fea55e): `src/aes/objects.c`.

    ob_find(tree, obj, depth, x, y):
        origin = obj == 0 ? r_set(0, 0, 0, 0) : ob_actxywh(tree, get_par(tree, obj))
        loop: t = ob_relxywh(tree, obj) + origin.xy; flags = ob_flags
              hit (inside(x, y, &t) and not HIDETREE):  found = obj; descend to ob_tail if any and depth-- != 0
              miss: after a descent, obj = get_prev(tree, found, obj) until -1; else stop
        return found (-1 when the first object is missed)

Seeded with the snapshot's own file selector (`aes_objects.SELECTOR`, 25 objects four deep); staged trees where a
shape the selector lacks is needed (overlapping siblings, a far edge that wraps). ob_find hands its two frame GRECTs
to its helpers by address — off target a host slot (`host_slot.h`, AES_OB_FIND_RECTS), in the stack band both shores
drop. Each routine entered DIRECT (the row Tier 3 prices) and THROUGH LINE-F by the word most of its callers use.
"""
import pytest

from harness import BASE_IMAGE, make_image

import aes
import aes_objects as objects
from aes_objects import FILE_BOX, FIRST_CHILD, SELECTOR, SLIDER, SLIDER_TRACK
from case import merge_pokes

DEEP = 8                    # more levels than the selector has
UNLIMITED = -1              # a depth counted down through the word: every level
FILE_LINE = objects.FIRST_FILE + 1
HIDETREE = 1 << aes.OB_FLAG_HIDETREE_BIT


def find(tree, start, depth, point, pokes=None, **kwargs):
    return aes.run_function(objects.OB_FIND, (tree, start, depth, *point), aes.leaf_machine(onto=pokes), **kwargs)


def expect(tree, start, depth, point, image=BASE_IMAGE):
    return objects.find_model(image, tree, start, depth, *point)


def with_flags(tree, index, flags):
    return aes.object_pokes(tree, index, FLAGS=flags)


# ---- ob_find over the snapshot's file selector -------------------------------------------------------------------
# (start, depth, point, the object found): every arm of the walk — a hit that descends, a hit at the depth limit, a
# hit on a leaf, misses that step back across many siblings, a miss of the first object.
ROOT_ORIGIN = objects.point_in(BASE_IMAGE, SELECTOR, aes.OB_ROOT)
SELECTOR_CASES = {
    "a file line, two levels": (aes.OB_ROOT, DEEP, objects.point_in(BASE_IMAGE, SELECTOR, FILE_LINE, 5, 3), FILE_LINE),
    "the slider, three levels": (aes.OB_ROOT, DEEP, objects.point_in(BASE_IMAGE, SELECTOR, SLIDER, 2, 2), SLIDER),
    "the first child, past ten siblings": (aes.OB_ROOT, DEEP, objects.point_in(BASE_IMAGE, SELECTOR, FIRST_CHILD, 1, 1),
                                          FIRST_CHILD),
    "the root, every child missed": (aes.OB_ROOT, DEEP, (ROOT_ORIGIN[0] + 2, ROOT_ORIGIN[1] + 2), aes.OB_ROOT),
    "outside the root": (aes.OB_ROOT, DEEP, (5, 5), aes.OB_NIL),
    "the root's origin corner": (aes.OB_ROOT, DEEP, ROOT_ORIGIN, aes.OB_ROOT),
    "one short of the root's far corner": (aes.OB_ROOT, DEEP, (319, ROOT_ORIGIN[1] + 151), aes.OB_ROOT),
    "the root's far x edge": (aes.OB_ROOT, DEEP, (320, ROOT_ORIGIN[1] + 20), aes.OB_NIL),
    "the root's far y edge": (aes.OB_ROOT, DEEP, (100, ROOT_ORIGIN[1] + 152), aes.OB_NIL),
    "one left of the root": (aes.OB_ROOT, DEEP, (-1, ROOT_ORIGIN[1] + 20), aes.OB_NIL),
    "one above the root": (aes.OB_ROOT, DEEP, (100, ROOT_ORIGIN[1] - 1), aes.OB_NIL),
    "depth 0, the root only": (aes.OB_ROOT, 0, objects.point_in(BASE_IMAGE, SELECTOR, FILE_LINE, 5, 3), aes.OB_ROOT),
    "depth 1, the file box": (aes.OB_ROOT, 1, objects.point_in(BASE_IMAGE, SELECTOR, FILE_LINE, 5, 3), FILE_BOX),
    "depth 2 stops at the slider's track": (aes.OB_ROOT, 2, objects.point_in(BASE_IMAGE, SELECTOR, SLIDER, 2, 2),
                                            SLIDER_TRACK),
    "a negative depth, every level": (aes.OB_ROOT, UNLIMITED, objects.point_in(BASE_IMAGE, SELECTOR, SLIDER, 2, 2), SLIDER),
    "from the file box": (FILE_BOX, DEEP, objects.point_in(BASE_IMAGE, SELECTOR, FILE_LINE, 5, 3), FILE_LINE),
    "from the slider's track, its parents summed": (SLIDER_TRACK, DEEP, objects.point_in(BASE_IMAGE, SELECTOR, SLIDER, 2, 2),
                                                    SLIDER),
    "from the file box, a point outside it": (FILE_BOX, DEEP, objects.point_in(BASE_IMAGE, SELECTOR, SLIDER, 2, 2),
                                              aes.OB_NIL),
    "the file box's last line, past eight": (aes.OB_ROOT, DEEP,
                                             objects.point_in(BASE_IMAGE, SELECTOR, objects.LAST_FILE, 1, 7),
                                             objects.LAST_FILE),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("shape", sorted(SELECTOR_CASES))
def test_the_object_under_a_point_over_the_snapshot_s_file_selector(shape, through_line_f):
    start, depth, point, found = SELECTOR_CASES[shape]
    assert expect(SELECTOR, start, depth, point) == found, "the model agrees with the case's reading of the tree"
    assert find(SELECTOR, start, depth, point, through_line_f=through_line_f).answer() == found


def test_the_tree_pointer_is_put_on_the_24_bit_bus():
    _start, depth, point, found = SELECTOR_CASES["from the slider's track, its parents summed"]
    assert find(SELECTOR | aes.BUS_TAG, SLIDER_TRACK, depth, point).answer() == found


@pytest.mark.parametrize("hidden, found", ((FILE_BOX, aes.OB_ROOT), (FILE_LINE, FILE_BOX), (aes.OB_ROOT, aes.OB_NIL)),
                         ids=("the file box: the root, past it", "the line: its box", "the root: nothing"))
def test_a_hidden_object_and_everything_under_it_is_passed_over(hidden, found):
    """HIDETREE (bit 7 of the flags' low byte) makes an object a miss, whatever the point: the walk steps back past it."""
    flags = objects.object_word(BASE_IMAGE, SELECTOR, hidden, "FLAGS") | HIDETREE
    point = objects.point_in(BASE_IMAGE, SELECTOR, FILE_LINE, 5, 3)
    pokes = with_flags(SELECTOR, hidden, flags)
    assert find(SELECTOR, aes.OB_ROOT, DEEP, point, pokes).answer() == found


def test_the_other_flag_bits_do_not_hide():
    """Every flag but HIDETREE set: still a hit."""
    point = objects.point_in(BASE_IMAGE, SELECTOR, FILE_LINE, 5, 3)
    pokes = with_flags(SELECTOR, FILE_LINE, 0xFFFF & ~HIDETREE)
    assert find(SELECTOR, aes.OB_ROOT, DEEP, point, pokes).answer() == FILE_LINE


# ---- staged shapes the selector lacks ---------------------------------------------------------------------------
OVERLAPPING = [aes.node(None, WIDTH=100, HEIGHT=100), aes.node(0, X=10, Y=10, WIDTH=50, HEIGHT=50),
               aes.node(0, X=30, Y=30, WIDTH=50, HEIGHT=50), aes.node(2, X=5, Y=5, WIDTH=4, HEIGHT=4)]


@pytest.mark.parametrize("point, found", (((40, 40), 2), ((15, 15), 1), ((36, 36), 3), ((90, 5), aes.OB_ROOT)),
                         ids=("both: the last, drawn on top", "the first alone: stepped back to", "a grandchild",
                              "neither"))
def test_overlapping_siblings_are_tried_last_first(point, found):
    pokes = aes.tree_pokes(OVERLAPPING)
    assert objects.find_model(make_image(pokes), aes.TREE_AT, aes.OB_ROOT, DEEP, *point) == found
    assert find(aes.TREE_AT, aes.OB_ROOT, DEEP, point, pokes).answer() == found


def test_a_far_edge_that_wraps_is_empty():
    """An object at x $7ff0, $20 wide: its far edge is the WORD $8010, negative, so no x is short of it — the signed
    compare the ROM's `bge` makes; a 32-bit sum would find the point."""
    objects_ = [aes.node(None, X=0x7FF0, WIDTH=0x20, HEIGHT=10)]
    assert find(aes.TREE_AT, aes.OB_ROOT, DEEP, (0x7FF5, 5), aes.tree_pokes(objects_)).answer() == aes.OB_NIL


def test_negative_coordinates_are_signed():
    objects_ = [aes.node(None, X=-50, Y=-40, WIDTH=100, HEIGHT=80), aes.node(0, X=10, Y=10, WIDTH=20, HEIGHT=20)]
    pokes = aes.tree_pokes(objects_)
    assert find(aes.TREE_AT, aes.OB_ROOT, DEEP, (-35, -25), pokes).answer() == 1
    assert find(aes.TREE_AT, aes.OB_ROOT, DEEP, (-45, 30), pokes).answer() == aes.OB_ROOT


def test_the_origin_sum_wraps_as_a_word():
    """Entered at a child of a root at x $7000 (whose own far edge wraps, so the root is never hit): the child's
    screen x is $7000 + $7000, the WORD $e000 — a point at -8190 is inside it."""
    objects_ = [aes.node(None, X=0x7000, WIDTH=0x2000, HEIGHT=100), aes.node(0, X=0x7000, WIDTH=100, HEIGHT=10)]
    assert find(aes.TREE_AT, 1, DEEP, (-8190, 5), aes.tree_pokes(objects_)).answer() == 1


def test_a_miss_of_the_starting_object_ends_the_search():
    """Entered at a child the point misses, with nothing found yet: the ROM stops (-1) without stepping back — a
    step back would ask get_prev for the siblings of object -1, the object BELOW the tree. Staged so that step would
    land: object -1's head is 2, whose next is the starting 1, and 2 holds the point."""
    tree = aes.TREE_AT + aes.OB_BYTES
    pokes = merge_pokes(aes.tree_pokes([aes.node(None, WIDTH=100, HEIGHT=100), aes.node(0, X=50, WIDTH=10, HEIGHT=10),
                                        aes.node(0, WIDTH=10, HEIGHT=10)], at=tree),
                        aes.object_pokes(tree, 0, HEAD=2, TAIL=1), aes.object_pokes(tree, 2, NEXT=1),
                        aes.object_pokes(tree, 1, NEXT=0), aes.object_pokes(aes.TREE_AT, 0, HEAD=2))
    assert find(tree, 1, DEEP, (5, 5), pokes).answer() == aes.OB_NIL


def test_a_start_at_object_minus_one_that_hits_then_misses_ends_the_search():
    """The OTHER half of the step back's test ($fea182 `cmpi.w #-1`): entered at object -1 (objc_find's `startob` is
    the caller's word), -1 is hit and descends to its tail, 1; the point misses 1, and with -1 the object found the
    ROM ends the search (-1) rather than asking get_prev for -1's children — here 2, which holds the point."""
    tree = aes.TREE_AT + aes.OB_BYTES
    pokes = merge_pokes(
        aes.tree_pokes([aes.node(None, WIDTH=100, HEIGHT=100), aes.node(0, X=50, WIDTH=10, HEIGHT=10),
                        aes.node(0, WIDTH=10, HEIGHT=10)], at=tree),
        aes.object_pokes(tree, 0, HEAD=-1, TAIL=-1),          # get_par(-1): [-1].next = 0, whose tail is -1
        aes.object_pokes(tree, 2, NEXT=1),
        aes.object_pokes(aes.TREE_AT, 0, NEXT=0, HEAD=2, TAIL=1, WIDTH=100, HEIGHT=100))
    assert objects.find_model(make_image(pokes), tree, aes.OB_NIL, DEEP, 5, 5) == aes.OB_NIL
    assert find(tree, aes.OB_NIL, DEEP, (5, 5), pokes).answer() == aes.OB_NIL


def test_a_child_s_offset_is_its_parent_s_hit_rectangle_not_the_root_s():
    """The origin a descent places children from is the HIT object's screen position, re-set at every level: a
    grandchild at (5, 5) under a child at (30, 30) is at (35, 35), not (5, 5) or (30, 30)."""
    pokes = aes.tree_pokes(OVERLAPPING)
    assert find(aes.TREE_AT, aes.OB_ROOT, DEEP, (6, 6), pokes).answer() == aes.OB_ROOT
    assert find(aes.TREE_AT, aes.OB_ROOT, DEEP, (35, 35), pokes).answer() == 3


# ---- the helpers -------------------------------------------------------------------------------------------------
RECT_AT = aes.RECTS_AT
FLAGS_AT = aes.RECTS_AT + aes.GRECT_BYTES
STALE_RECT = aes.grect_pokes(RECT_AT, *(aes.STALE_WORD,) * 4)
STALE_FLAGS = aes.field_pokes("GRECT", FLAGS_AT, X=aes.STALE_WORD)
DEFAULT_BUTTON = 21         # the selector's OK button: flags SELECTABLE | DEFAULT | EXIT


def rect_at(image, at):
    return tuple(objects.signed(aes.read_field(image, "GRECT", name, at)) for name in ("X", "Y", "W", "H"))


def object_rect(image, tree, index):
    return tuple(objects.object_word(image, tree, index, name) for name in ("X", "Y", "WIDTH", "HEIGHT"))


def field_address(tree, index, name):
    return tree + index * aes.OB_BYTES + aes.field("OB", name)[0]


def helper(name, tree, index, pointer, pokes=None, **kwargs):
    return aes.run_function(name, (tree, index, pointer), aes.leaf_machine(onto=pokes), **kwargs)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_ob_fs_stores_the_flags_and_answers_the_state(through_line_f):
    result = helper(objects.OB_FS, SELECTOR, DEFAULT_BUTTON, FLAGS_AT, STALE_FLAGS, through_line_f=through_line_f)
    assert result.word(FLAGS_AT) == objects.object_word(BASE_IMAGE, SELECTOR, DEFAULT_BUTTON, "FLAGS")
    assert result.answer() == objects.object_word(BASE_IMAGE, SELECTOR, DEFAULT_BUTTON, "STATE")


def test_ob_fs_reads_the_state_after_storing_the_flags():
    """The ORDER: the flags word laid over the object's own state — the answer is the flags just stored."""
    state_at = field_address(SELECTOR, DEFAULT_BUTTON, "STATE")
    result = helper(objects.OB_FS, SELECTOR | aes.BUS_TAG, DEFAULT_BUTTON, state_at | aes.BUS_TAG)
    assert result.answer() == objects.object_word(BASE_IMAGE, SELECTOR, DEFAULT_BUTTON, "FLAGS")


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_ob_actxywh_is_the_object_s_rectangle_on_the_screen(through_line_f):
    result = helper(objects.OB_ACTXYWH, SELECTOR, SLIDER, RECT_AT, STALE_RECT, through_line_f=through_line_f)
    width, height = object_rect(BASE_IMAGE, SELECTOR, SLIDER)[2:]
    assert rect_at(result.final, RECT_AT) == (*objects.screen_origin(BASE_IMAGE, SELECTOR, SLIDER), width, height)


def test_ob_actxywh_puts_the_tree_and_the_rectangle_on_the_24_bit_bus():
    result = helper(objects.OB_ACTXYWH, SELECTOR | aes.BUS_TAG, SLIDER, RECT_AT | aes.BUS_TAG, STALE_RECT)
    width, height = object_rect(BASE_IMAGE, SELECTOR, SLIDER)[2:]
    assert rect_at(result.final, RECT_AT) == (*objects.screen_origin(BASE_IMAGE, SELECTOR, SLIDER), width, height)


def test_ob_actxywh_reads_each_size_word_after_the_stores_before_it():
    """The ORDER: the GRECT laid over the object from its ob_y, so its x is the object's ob_y, its y the width, its w
    the height and its h the NEXT object's ob_next. ob_offset clears both, then x += ob_x lands 40 in ob_y before
    y += ob_y reads it, and the root's 3 and 5 follow; the width — now y's sum — is read and stored into the height,
    and the height, just stored, into the next object's ob_next."""
    objects_ = [aes.node(None, X=3, Y=5, WIDTH=200, HEIGHT=100), aes.node(0, X=40, Y=60, WIDTH=70, HEIGHT=80),
                aes.node(0)]
    at = field_address(aes.TREE_AT, 1, "Y")
    result = helper(objects.OB_ACTXYWH, aes.TREE_AT, 1, at, aes.tree_pokes(objects_))
    y_sum = 40 + 5
    assert rect_at(result.final, at) == (40 + 3, y_sum, y_sum, y_sum)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_ob_relxywh_copies_the_object_s_rectangle_out(through_line_f):
    result = helper(objects.OB_RELXYWH, SELECTOR, FILE_LINE, RECT_AT, STALE_RECT, through_line_f=through_line_f)
    assert rect_at(result.final, RECT_AT) == object_rect(BASE_IMAGE, SELECTOR, FILE_LINE)


def test_ob_relxywh_copies_forward_a_word_at_a_time():
    """wcopy's ORDER: the GRECT one word above the object's ob_x — each word read after the one before it was
    stored, so ob_x runs through all four."""
    at = field_address(SELECTOR, FILE_LINE, "Y")
    result = helper(objects.OB_RELXYWH, SELECTOR | aes.BUS_TAG, FILE_LINE, at | aes.BUS_TAG)
    x = objects.object_word(BASE_IMAGE, SELECTOR, FILE_LINE, "X")
    assert rect_at(result.final, at) == (x, x, x, x)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_ob_setxywh_copies_a_rectangle_in(through_line_f):
    pokes = aes.grect_pokes(RECT_AT, 11, -22, 333, 0x8004)
    result = helper(objects.OB_SETXYWH, SELECTOR, FILE_LINE, RECT_AT, pokes, through_line_f=through_line_f)
    assert object_rect(result.final, SELECTOR, FILE_LINE) == (11, -22, 333, objects.signed(0x8004))


def test_ob_setxywh_copies_forward_a_word_at_a_time():
    """The GRECT one word BELOW the object's ob_x (the spec's low word): that word runs through all four."""
    at = field_address(SELECTOR, FILE_LINE, "X") - aes.WORD_BYTES
    result = helper(objects.OB_SETXYWH, SELECTOR | aes.BUS_TAG, FILE_LINE, at | aes.BUS_TAG)
    spec_low = objects.signed(aes.read_field(BASE_IMAGE, "OB", "SPEC", SELECTOR + FILE_LINE * aes.OB_BYTES))
    assert object_rect(result.final, SELECTOR, FILE_LINE) == (spec_low,) * 4


# ---- the registry ------------------------------------------------------------------------------------------------
# ob_find: the cheapest (a miss of the root), a descent, and the dearest — the first child and every child missed,
# each walk stepping back across all eleven of the root's children by get_prev, which itself walks from the head (quadratic).
for _shape in ("outside the root", "a file line, two levels", "the first child, past ten siblings",
               "the root, every child missed", "the slider, three levels", "depth 0, the root only",
               "from the slider's track, its parents summed"):
    _start, _depth, _point, _found = SELECTOR_CASES[_shape]
    aes.register(_shape, objects.OB_FIND, (SELECTOR, _start, _depth, *_point), aes.leaf_machine())
_start, _depth, _point, _found = SELECTOR_CASES["the first child, past ten siblings"]
aes.register("the first child, past ten siblings", objects.OB_FIND, (SELECTOR, _start, _depth, *_point), aes.leaf_machine(),
             through_line_f=True)
for _through in (False, True):
    aes.register("the OK button", objects.OB_FS, (SELECTOR, DEFAULT_BUTTON, FLAGS_AT), aes.leaf_machine(onto=STALE_FLAGS),
                 through_line_f=_through)
    aes.register("the slider, four levels", objects.OB_ACTXYWH, (SELECTOR, SLIDER, RECT_AT),
                 aes.leaf_machine(onto=STALE_RECT), through_line_f=_through)
    aes.register("a file line", objects.OB_RELXYWH, (SELECTOR, FILE_LINE, RECT_AT), aes.leaf_machine(onto=STALE_RECT),
                 through_line_f=_through)
    aes.register("a file line", objects.OB_SETXYWH, (SELECTOR, FILE_LINE, RECT_AT),
                 aes.leaf_machine(onto=aes.grect_pokes(RECT_AT, 11, -22, 333, 0x8004)), through_line_f=_through)
aes.register("the first of eleven siblings", objects.OB_ACTXYWH, (SELECTOR, FIRST_CHILD, RECT_AT),
             aes.leaf_machine(onto=STALE_RECT))
