"""AES ob_add ($fea1ba), ob_delete ($fea21e), ob_order ($fea2be), get_prev ($fea5dc) and ob_center ($fe92ae, the
form_center arm's) — the tree EDITS of `src/aes/objects.c`.

    ob_add(tree, parent, child):   nothing if either is -1; child.next = parent; then (parent.tail == -1 ? parent.head
                                   : tree[parent.tail].next) = child; parent.tail = child
    ob_delete(tree, obj):          not the root; next = obj.next (read first); parent = get_par; the head: head = next,
                                   or -1 with the tail when obj is the only child; else get_prev's next = next, and the
                                   tail = that previous when obj was the tail
    ob_order(tree, obj, pos):      not the root; parent = get_par; ob_delete; pos 0: obj.next = head, head = obj; else
                                   the one before (the tail for -1, else pos - 1 links from the head): obj.next = its
                                   next, its next = obj; finally the tail = obj when obj.next is the parent
    get_prev(tree, parent, obj):   -1 when obj is the head, else the sibling whose next is obj
    ob_center(tree, rect):         the root centred below the menu bar, x on a character cell, stored into the root;
                                   the GRECT answered, grown by 3 a side for an OUTLINED root

Seeded with the snapshot's own resource trees (the file selector and the alert, both OUTLINED roots, and the menu
tree), edited IN PLACE in GEMBSS as an application's call would; staged trees for the shapes they lack. Every result
held to the tree's links as the batteries' model reads them; every edit's links are the differential's.
"""
import pytest

from harness import BASE_IMAGE

import aes
import aes_objects as objects
import vdi
import vdi_helpers
from aes_objects import FILE_BOX, FIRST_CHILD, FIRST_FILE, LAST_CHILD, LAST_FILE, SELECTOR, SLIDER, SLIDER_TRACK
from case import merge_pokes

MIDDLE_FILE = FIRST_FILE + 3
FILES = list(range(FIRST_FILE, LAST_FILE + 1))
ROOT_CHILDREN = objects.children_of(BASE_IMAGE, SELECTOR, aes.OB_ROOT)     # 1..7 and 21..24: eleven
MENU = aes.resource_tree(2)


# THE ATTRIBUTION PASS IS OFF for the ob_delete and ob_order cases that UNLINK (`LINKS_UNPOISONED`, each case below
# that passes it; measured: every one of them red poisoned, and the three that store nothing or only the link they read
# green): each reads a link it goes on to store — get_par and get_prev walk the very head, tail and next words the
# unlink rewrites — and the pass, inverting a stored word before its first read, sends the walk round a poisoned index
# until the oracle's budget ends. What stands in for it: no case stores a link with the value it already held but
# through a store that changed it first (ob_order's "back to its place" relinks what ob_delete unlinked), so a store the
# C skipped shows as a stale link.
LINKS_UNPOISONED = vdi.READS_A_POINTER_IT_WRITES


def edit(name, arguments, pokes=None, **kwargs):
    return aes.run_function(name, arguments, aes.leaf_machine(onto=pokes), **kwargs)


def children(result, parent, tree=SELECTOR):
    return objects.children_of(result.final, tree, parent)


def link(result, index, name, tree=SELECTOR):
    return objects.object_word(result.final, tree, index, name)


def unchanged(result, tree=SELECTOR):
    """Not a byte of the tree written."""
    span = slice(tree, tree + objects.SELECTOR_OBJECTS * aes.OB_BYTES)
    return result.final[span] == BASE_IMAGE[span] and not any(span.start <= at < span.stop for at in result.info["writes"])


# ---- ob_add ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_ob_add_links_a_child_in_as_the_last(through_line_f):
    result = edit(objects.OB_ADD, (SELECTOR, FILE_BOX, SLIDER), through_line_f=through_line_f)
    assert children(result, FILE_BOX) == FILES + [SLIDER]
    assert (link(result, SLIDER, "NEXT"), link(result, FILE_BOX, "TAIL")) == (FILE_BOX, SLIDER)


def test_ob_add_to_a_leaf_sets_its_head_and_tail():
    result = edit(objects.OB_ADD, (SELECTOR | aes.BUS_TAG, MIDDLE_FILE, SLIDER))
    assert (link(result, MIDDLE_FILE, "HEAD"), link(result, MIDDLE_FILE, "TAIL"), link(result, SLIDER, "NEXT")) == (
        SLIDER, SLIDER, MIDDLE_FILE)


def test_ob_add_of_the_tail_stores_its_next_twice():
    """The ORDER of the two stores into one word: the child IS the parent's tail already, so its ob_next is first the
    parent and then — as the old tail's next — itself."""
    result = edit(objects.OB_ADD, (SELECTOR, aes.OB_ROOT, LAST_CHILD))
    assert (link(result, LAST_CHILD, "NEXT"), link(result, aes.OB_ROOT, "TAIL")) == (LAST_CHILD, LAST_CHILD)


@pytest.mark.parametrize("parent, child", ((aes.OB_NIL, SLIDER), (FILE_BOX, aes.OB_NIL)), ids=("no parent", "no child"))
def test_ob_add_with_either_nil_does_nothing(parent, child):
    assert unchanged(edit(objects.OB_ADD, (SELECTOR, parent, child)))


# ---- ob_delete ---------------------------------------------------------------------------------------------------
DELETE_CASES = {    # object: (its parent, the children left)
    "the head of 11": (FIRST_CHILD, aes.OB_ROOT, ROOT_CHILDREN[1:]),
    "the tail of 11": (LAST_CHILD, aes.OB_ROOT, ROOT_CHILDREN[:-1]),
    "a middle one of nine": (MIDDLE_FILE, FILE_BOX, [f for f in FILES if f != MIDDLE_FILE]),
    "the head of nine": (FIRST_FILE, FILE_BOX, FILES[1:]),
    "the tail of nine": (LAST_FILE, FILE_BOX, FILES[:-1]),
    "an only child": (SLIDER, SLIDER_TRACK, []),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("shape", sorted(DELETE_CASES))
def test_ob_delete_unlinks_an_object_from_its_parent(shape, through_line_f):
    index, parent, left = DELETE_CASES[shape]
    result = edit(objects.OB_DELETE, (SELECTOR, index), through_line_f=through_line_f, **LINKS_UNPOISONED)
    assert children(result, parent) == left
    assert link(result, parent, "TAIL") == (left[-1] if left else aes.OB_NIL)
    assert link(result, index, "NEXT") == objects.object_word(BASE_IMAGE, SELECTOR, index, "NEXT"), "its own link kept"


def test_ob_delete_of_the_root_does_nothing():
    assert unchanged(edit(objects.OB_DELETE, (SELECTOR, aes.OB_ROOT)))


def test_ob_delete_puts_the_tree_on_the_24_bit_bus():
    result = edit(objects.OB_DELETE, (SELECTOR | aes.BUS_TAG, LAST_FILE), **LINKS_UNPOISONED)
    assert children(result, FILE_BOX) == FILES[:-1]


# ---- ob_order ----------------------------------------------------------------------------------------------------
ORDER_CASES = {     # (object, position): the parent's children after
    "a middle one to the head": (MIDDLE_FILE, 0, [MIDDLE_FILE] + [f for f in FILES if f != MIDDLE_FILE]),
    "a middle one to the tail": (MIDDLE_FILE, -1, [f for f in FILES if f != MIDDLE_FILE] + [MIDDLE_FILE]),
    "a middle one after the first": (MIDDLE_FILE, 1, [FIRST_FILE, MIDDLE_FILE] + [f for f in FILES[1:] if f != MIDDLE_FILE]),
    "a middle one back to its place": (MIDDLE_FILE, 3, FILES),
    "a middle one after the last by count": (MIDDLE_FILE, 8, [f for f in FILES if f != MIDDLE_FILE] + [MIDDLE_FILE]),
    "the head to the tail": (FIRST_FILE, -1, FILES[1:] + [FIRST_FILE]),
    "the tail to the head": (LAST_FILE, 0, [LAST_FILE] + FILES[:-1]),
    "the head back to the head, read after the unlink": (FIRST_FILE, 0, FILES),
    "the head after the new head": (FIRST_FILE, 1, [FILES[1], FIRST_FILE] + FILES[2:]),
    "a position below -1, after the head": (MIDDLE_FILE, -2, [FIRST_FILE, MIDDLE_FILE] + [f for f in FILES[1:]
                                                                                          if f != MIDDLE_FILE]),
    "the first of 11 to the tail": (FIRST_CHILD, -1, ROOT_CHILDREN[1:] + [FIRST_CHILD]),
}


def parent_of_case(index):
    return FILE_BOX if index in FILES else aes.OB_ROOT


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("shape", sorted(ORDER_CASES))
def test_ob_order_moves_an_object_among_its_siblings(shape, through_line_f):
    index, position, after = ORDER_CASES[shape]
    parent = parent_of_case(index)
    result = edit(objects.OB_ORDER, (SELECTOR, index, position), through_line_f=through_line_f, **LINKS_UNPOISONED)
    assert children(result, parent) == after
    assert (link(result, parent, "HEAD"), link(result, parent, "TAIL")) == (after[0], after[-1])


def test_ob_order_of_the_root_does_nothing():
    assert unchanged(edit(objects.OB_ORDER, (SELECTOR, aes.OB_ROOT, -1)))


def test_ob_order_puts_the_tree_on_the_24_bit_bus():
    index, position, after = ORDER_CASES["the tail to the head"]
    assert children(edit(objects.OB_ORDER, (SELECTOR | aes.BUS_TAG, index, position), **LINKS_UNPOISONED), FILE_BOX) == after


def test_ob_order_of_an_only_child_to_the_head_leaves_no_tail():
    """A ROM defect: ob_delete empties the parent's head AND tail, ob_order relinks the head, and the tail is set only
    when the object's new ob_next is the parent — here -1, the emptied head. The track keeps a head and no tail."""
    result = edit(objects.OB_ORDER, (SELECTOR, SLIDER, 0), **LINKS_UNPOISONED)
    assert (link(result, SLIDER_TRACK, "HEAD"), link(result, SLIDER_TRACK, "TAIL"), link(result, SLIDER, "NEXT")) == (
        SLIDER, aes.OB_NIL, aes.OB_NIL)


def test_ob_order_of_an_only_child_to_the_tail_writes_below_the_tree():
    """...and to the tail (-1) the one before is the emptied tail, -1: its ob_next is the word 24 bytes BELOW the
    tree — here the AES resource header's TEDINFO count — read into the object's ob_next and then overwritten with
    the object. The track is left with neither head nor tail."""
    below = SELECTOR - aes.OB_BYTES
    result = edit(objects.OB_ORDER, (SELECTOR, SLIDER, -1), **LINKS_UNPOISONED)
    assert result.word(below) == SLIDER
    assert link(result, SLIDER, "NEXT") == objects.signed(BASE_IMAGE[below] << 8 | BASE_IMAGE[below + 1])
    assert (link(result, SLIDER_TRACK, "HEAD"), link(result, SLIDER_TRACK, "TAIL")) == (aes.OB_NIL, aes.OB_NIL)


def test_ob_order_reads_the_one_before_s_next_before_linking_it():
    """The ORDER of the relink, which only a walk that reaches the object itself shows: an only child (1) ordered
    to 2 walks from the emptied head, -1, to the next of the object BELOW the tree — staged as 1. So the one before is
    the object: its ob_next is read (the parent, 0), then rewritten as the object, and the tail left alone because
    that next is no longer the parent. Linked in the other order the next would end as the parent and the tail be 1."""
    tree = aes.TREE_AT + aes.OB_BYTES
    pokes = merge_pokes(aes.tree_pokes([aes.node(None), aes.node(0)], at=tree), aes.object_pokes(aes.TREE_AT, 0, NEXT=1))
    result = edit(objects.OB_ORDER, (tree, 1, 2), pokes)
    assert (objects.object_word(result.final, tree, 1, "NEXT"), objects.object_word(result.final, tree, 0, "TAIL")) == (
        1, aes.OB_NIL)


def test_ob_order_past_the_end_walks_on_through_the_parent():
    """Position 9 among eight siblings: the walk's last step is the last sibling's next, the PARENT, so the object is
    linked in after the file box among the ROOT's children — the parent's own list is left without it."""
    result = edit(objects.OB_ORDER, (SELECTOR, MIDDLE_FILE, 9), **LINKS_UNPOISONED)
    assert children(result, FILE_BOX) == [f for f in FILES if f != MIDDLE_FILE]
    assert (link(result, FILE_BOX, "NEXT"), link(result, MIDDLE_FILE, "NEXT")) == (MIDDLE_FILE, FILE_BOX + 1)


# ---- get_prev ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("index, previous", ((FIRST_CHILD, aes.OB_NIL), (FIRST_CHILD + 1, FIRST_CHILD),
                                             (LAST_CHILD, LAST_CHILD - 1)), ids=("the head", "the second", "the tail"))
def test_get_prev_is_the_sibling_before(index, previous, through_line_f):
    result = edit(objects.GET_PREV, (SELECTOR, aes.OB_ROOT, index), through_line_f=through_line_f)
    assert result.answer() == previous


def test_get_prev_puts_the_tree_on_the_24_bit_bus():
    assert edit(objects.GET_PREV, (SELECTOR | aes.BUS_TAG, FILE_BOX, LAST_FILE)).answer() == LAST_FILE - 1


# ---- ob_center ---------------------------------------------------------------------------------------------------
RECT_AT = aes.RECTS_AT
STALE_RECT = aes.grect_pokes(RECT_AT, *(aes.STALE_WORD,) * 4)
SCREEN_FIELDS = ("GL_WIDTH", "GL_HEIGHT", "GL_WCHAR", "GL_HBOX")
for _name in SCREEN_FIELDS:
    aes.declare_case_field(aes.field("AES", _name)[0], aes.WORD_BYTES, "the screen metrics ob_center's cases stage")
OUTLINE = 3


def screen(width=None, height=None, cell=None, bar=None):
    """The four screen metrics, each the snapshot's unless named."""
    values = {name: value for name, value in zip(SCREEN_FIELDS, (width, height, cell, bar)) if value is not None}
    return aes.field_pokes("AES", **values)


def metric(name):
    return objects.signed(aes.read_field(BASE_IMAGE, "AES", name))


def center_model(tree, image=BASE_IMAGE):
    """form_center as the ROM computes it: `divs` truncates toward zero, and a word's arithmetic wraps."""
    def toward_zero(value, divisor):
        quotient = abs(value) // abs(divisor)
        return quotient if (value < 0) == (divisor < 0) else -quotient
    field = {name: objects.signed(aes.read_field(image, "AES", name)) for name in SCREEN_FIELDS}
    width, height = objects.object_word(image, tree, 0, "WIDTH"), objects.object_word(image, tree, 0, "HEIGHT")
    x = toward_zero(toward_zero(objects.signed(field["GL_WIDTH"] - width), 2), field["GL_WCHAR"]) * field["GL_WCHAR"]
    x = objects.signed(x)
    y = objects.signed(toward_zero(objects.signed(field["GL_HEIGHT"] - field["GL_HBOX"] - height), 2) + field["GL_HBOX"])
    placed = (x, y)
    if objects.object_word(image, tree, 0, "STATE") & 1 << aes.OB_STATE_OUTLINED_BIT:
        x, y, width, height = x - min(x, OUTLINE), y - min(y, OUTLINE), width + 2 * OUTLINE, height + 2 * OUTLINE
    return placed, (x, y, width, height)


def rect_at(image, at):
    return tuple(objects.signed(aes.read_field(image, "GRECT", name, at)) for name in ("X", "Y", "W", "H"))


def center(tree, pokes=None, rect=RECT_AT, **kwargs):
    return edit(objects.OB_CENTER, (tree, rect), merge_pokes(STALE_RECT, pokes), **kwargs)


CENTER_CASES = {    # the tree, and the screen staged over the snapshot's 320 x 200, 8-pixel cells, an 11-pixel bar
    "the file selector, outlined": (SELECTOR, None),
    "the alert, outlined, as its builder left it": (objects.ALERT, None),
    "the menu tree, taller than the screen below the bar": (MENU, None),
    "a negative half, truncated toward zero": (SELECTOR, screen(width=320 - 81 - 80, cell=6)),
    "an odd negative half, toward zero not down": (SELECTOR, screen(width=320 - 161, cell=1)),   # -80, not -81
    "a negative cell width": (MENU, screen(width=100, cell=-8)),
    "an outline at the screen's corner": (SELECTOR, screen(width=324, height=41, cell=1)),   # x 2 and y -50: both to 0
    "a wide screen": (objects.ALERT, screen(width=640, height=400, cell=8, bar=19)),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("shape", sorted(CENTER_CASES))
def test_ob_center_centres_the_root_below_the_menu_bar(shape, through_line_f):
    tree, pokes = CENTER_CASES[shape]
    result = center(tree, pokes, through_line_f=through_line_f)
    image = bytearray(BASE_IMAGE)
    for at, data in (pokes or {}).items():
        image[at:at + len(data)] = data
    placed, answered = center_model(tree, image)
    assert (link(result, 0, "X", tree), link(result, 0, "Y", tree)) == placed
    assert rect_at(result.final, RECT_AT) == answered


def test_ob_center_puts_the_tree_and_the_rectangle_on_the_24_bit_bus():
    result = center(SELECTOR | aes.BUS_TAG, rect=RECT_AT | aes.BUS_TAG)
    assert rect_at(result.final, RECT_AT) == center_model(SELECTOR)[1]


def test_ob_center_answers_over_the_root_s_own_rectangle():
    """The GRECT laid over the root's ob_x..ob_height: the size is read before anything is stored, the position
    stored, then the answer over all four."""
    at = SELECTOR + aes.field("OB", "X")[0]
    result = center(SELECTOR, rect=at)
    assert rect_at(result.final, at) == center_model(SELECTOR)[1]


def test_ob_center_a_zero_cell_width_is_refused_on_the_host():
    """The ROM's `divs` by a zero cell width takes the 68000's zero-divide trap; the host refuses the case by name."""
    zero_cell = "; ".join(f"buf[{aes.AES_GL_WCHAR + offset}] = 0" for offset in range(aes.WORD_BYTES))
    returncode, stderr = vdi_helpers.refusal("aes_ob_center", ["ctypes.c_void_p", "ctypes.c_uint32", "ctypes.c_uint32"],
                                             f"buf, {SELECTOR}, {RECT_AT}",
                                             prelude=f"{vdi_helpers.FRESH_IMAGE}; {zero_cell}")
    assert returncode != 0 and "zero divide" in stderr, stderr


# ---- the registry ------------------------------------------------------------------------------------------------
# The dearest realistic rows: an edit of the root's first or last of 11 children (get_par and get_prev walk them all),
# and the cheap ones: a leaf's add, the nil and root arms.
for _through in (False, True):
    aes.register("a file line added to a leaf", objects.OB_ADD, (SELECTOR, MIDDLE_FILE, SLIDER), aes.leaf_machine(),
                 through_line_f=_through)
    aes.register("the tail of 11", objects.OB_DELETE, (SELECTOR, LAST_CHILD), aes.leaf_machine(), through_line_f=_through)
    aes.register("the first of 11 to the tail", objects.OB_ORDER, (SELECTOR, FIRST_CHILD, -1), aes.leaf_machine(),
                 through_line_f=_through)
    aes.register("the tail of 11", objects.GET_PREV, (SELECTOR, aes.OB_ROOT, LAST_CHILD), aes.leaf_machine(),
                 through_line_f=_through)
    aes.register("the file selector", objects.OB_CENTER, (SELECTOR, RECT_AT), aes.leaf_machine(onto=STALE_RECT),
                 through_line_f=_through)
aes.register("to the box of nine", objects.OB_ADD, (SELECTOR, FILE_BOX, SLIDER), aes.leaf_machine())
aes.register("no parent", objects.OB_ADD, (SELECTOR, aes.OB_NIL, SLIDER), aes.leaf_machine())
aes.register("the head of 11", objects.OB_DELETE, (SELECTOR, FIRST_CHILD), aes.leaf_machine())
aes.register("an only child", objects.OB_DELETE, (SELECTOR, SLIDER), aes.leaf_machine())
aes.register("the root", objects.OB_DELETE, (SELECTOR, aes.OB_ROOT), aes.leaf_machine())
aes.register("a middle one after the last by count", objects.OB_ORDER, (SELECTOR, MIDDLE_FILE, 8), aes.leaf_machine())
aes.register("the tail to the head", objects.OB_ORDER, (SELECTOR, LAST_FILE, 0), aes.leaf_machine())
aes.register("the root", objects.OB_ORDER, (SELECTOR, aes.OB_ROOT, 0), aes.leaf_machine())
aes.register("the head", objects.GET_PREV, (SELECTOR, aes.OB_ROOT, FIRST_CHILD), aes.leaf_machine())
aes.register("the menu tree, not outlined", objects.OB_CENTER, (MENU, RECT_AT), aes.leaf_machine(onto=STALE_RECT))
aes.register("a negative half, truncated toward zero", objects.OB_CENTER, (SELECTOR, RECT_AT),
             aes.leaf_machine(onto=merge_pokes(STALE_RECT, CENTER_CASES["a negative half, truncated toward zero"][1])))
