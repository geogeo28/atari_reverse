"""AES rectangle helpers round rc_intersect — `src/aes/rect.c`: r_get $fecca6, r_set $feccbe, rc_copy $feccca, inside
$feccd6, rc_equal $fecd0c, rc_union $fecd8c, rc_constrain $fecde4.

    r_get(rect, &x, &y, &w, &h)     each word read and stored in turn (`move.w (a0)+,(a1)`)
    r_set(rect, x, y, w, h)         two longword stores (`movem.l a1-a2,(a0)`)
    rc_copy(from, to)               two longwords, each read and stored in turn
    inside(x, y, rect)              D0.w = rect.x <= x < rect.x + rect.w and the same down (word sums, signed)
    rc_equal(one, other)            D0.w = the two GRECTs' longwords equal (`cmpm.l`, the second only if the first is)
    rc_union(from, into)            per axis: min origin, max far edge, into's words stored, x before y is read
    rc_constrain(container, rect)   per axis: the origin pulled up to the container's, then back so the far edge fits

Hand 68000 returning by `rts` (so no mask word is ever stored), seeded with the snapshot's own rectangles: the
desktop window's current and full GRECTs, and an object's ob_x..ob_height — the GRECT inside every OBJECT, which
the object library copies and tests (the AES resource's file selector, `aes.resource_tree(0)`).
"""
import pytest

from harness import BASE_IMAGE

import aes
import vdi
from case import merge_pokes
from test_aes_rect import rect_of, signed_rect

R_GET, R_SET, RC_COPY = "AES_ROM_R_GET", "AES_ROM_R_SET", "AES_ROM_RC_COPY"
INSIDE, RC_EQUAL = "AES_ROM_INSIDE", "AES_ROM_RC_EQUAL"
RC_UNION, RC_CONSTRAIN = "AES_ROM_RC_UNION", "AES_ROM_RC_CONSTRAIN"
L, W = vdi.LONG_ARG, vdi.WORD_ARG
aes.declare_alcyon(R_GET, None, (vdi.IMAGE_ARG, L, L, L, L, L))
aes.declare_alcyon(R_SET, None, (vdi.IMAGE_ARG, L, W, W, W, W))
aes.declare_alcyon(RC_COPY, None, (vdi.IMAGE_ARG, L, L))
aes.declare_alcyon(INSIDE, aes.WORD_ANSWER, (vdi.IMAGE_ARG, W, W, L))
aes.declare_alcyon(RC_EQUAL, aes.WORD_ANSWER, (vdi.IMAGE_ARG, L, L))
aes.declare_alcyon(RC_UNION, None, (vdi.IMAGE_ARG, L, L))
aes.declare_alcyon(RC_CONSTRAIN, None, (vdi.IMAGE_ARG, L, L))

DESKTOP_CURR = aes.AES_WINDOWS + aes.WIN_CURR
DESKTOP_FULL = aes.AES_WINDOWS + aes.WIN_FULL
SELECTOR = aes.resource_tree(0)
# The file selector's object 12, the first of its nine file rows: its ob_x..ob_height, a GRECT inside the OBJECT.
FILE_ROW = SELECTOR + 12 * aes.OB_BYTES + aes.OB_X
FIRST_AT = aes.RECTS_AT
SECOND_AT = aes.RECTS_AT + aes.GRECT_BYTES
# r_get's four answer words, after the two GRECTs, staged STALE so a skipped store shows.
ANSWERS_AT = aes.RECTS_AT + 2 * aes.GRECT_BYTES
ANSWER_WORDS = tuple(ANSWERS_AT + index * aes.WORD_BYTES for index in range(4))
STALE_ANSWERS = merge_pokes(*(aes.field_pokes("GRECT", at, X=aes.STALE_WORD) for at in ANSWER_WORDS))


def run(name, arguments, pokes=None, **kwargs):
    return aes.run_function(name, arguments, aes.leaf_machine(onto=pokes), **kwargs)


def two_rects(first, second):
    return merge_pokes(aes.grect_pokes(FIRST_AT, *first), aes.grect_pokes(SECOND_AT, *second))


# ---- r_get / r_set / rc_copy ------------------------------------------------------------------------------------

@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_r_get_answers_the_desktop_window_s_four_words(through_line_f):
    result = run(R_GET, (DESKTOP_CURR, *ANSWER_WORDS), STALE_ANSWERS, through_line_f=through_line_f)
    assert tuple(aes.signed(result.word(at)) for at in ANSWER_WORDS) == rect_of(BASE_IMAGE, DESKTOP_CURR)


def test_r_get_stores_each_word_before_it_reads_the_next():
    """The x answer laid over the rectangle's OWN y: x is stored there first, so y reads x back — read up front, the
    y answer would be the old y."""
    pokes = merge_pokes(STALE_ANSWERS, aes.grect_pokes(FIRST_AT, 3, 4, 5, 6))
    y_of_rect = FIRST_AT + aes.GRECT_Y
    result = run(R_GET, (FIRST_AT, y_of_rect, *ANSWER_WORDS[1:]), pokes)
    assert tuple(result.word(at) for at in ANSWER_WORDS[1:]) == (3, 5, 6)


def test_r_get_puts_every_pointer_on_the_24_bit_bus():
    result = run(R_GET, (DESKTOP_CURR | aes.BUS_TAG, *(at | aes.BUS_TAG for at in ANSWER_WORDS)), STALE_ANSWERS)
    assert tuple(aes.signed(result.word(at)) for at in ANSWER_WORDS) == rect_of(BASE_IMAGE, DESKTOP_CURR)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("values", ((0, 11, 320, 189), (-1, -32768, 32767, 0x8001), (5, -2, 7, -3)),
                         ids=("desktop", "extremes", "negative words beside positive ones"))
def test_r_set_stores_the_four_words(values, through_line_f):
    result = run(R_SET, (FIRST_AT, *values), aes.grect_pokes(FIRST_AT, *(aes.STALE_WORD,) * 4),
                 through_line_f=through_line_f)
    assert rect_of(result.final, FIRST_AT) == signed_rect(values)


def test_r_set_puts_its_rectangle_on_the_24_bit_bus():
    result = run(R_SET, (FIRST_AT | aes.BUS_TAG, 7, 8, 9, 10))
    assert rect_of(result.final, FIRST_AT) == (7, 8, 9, 10)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_rc_copy_copies_an_object_s_rectangle(through_line_f):
    result = run(RC_COPY, (FILE_ROW, FIRST_AT), aes.grect_pokes(FIRST_AT, *(aes.STALE_WORD,) * 4),
                 through_line_f=through_line_f)
    assert rect_of(result.final, FIRST_AT) == rect_of(BASE_IMAGE, FILE_ROW)


def test_rc_copy_reads_its_second_longword_after_storing_the_first():
    """`to` one longword above `from`: the first longword lands on from's w and h, and is then read back as the
    second — the copy is the first longword twice."""
    to = FIRST_AT + aes.GRECT_W
    result = run(RC_COPY, (FIRST_AT, to), aes.grect_pokes(FIRST_AT, 1, 2, 3, 4))
    assert rect_of(result.final, to) == (1, 2, 1, 2)


def test_rc_copy_downwards_over_itself():
    """`to` one longword BELOW `from`: the first longword stored over nothing the copy reads again."""
    to = SECOND_AT - aes.GRECT_W
    result = run(RC_COPY, (SECOND_AT, to), aes.grect_pokes(SECOND_AT, 1, 2, 3, 4))
    assert rect_of(result.final, to) == (1, 2, 3, 4)


def test_rc_copy_puts_both_pointers_on_the_24_bit_bus():
    result = run(RC_COPY, (FILE_ROW | aes.BUS_TAG, FIRST_AT | aes.BUS_TAG))
    assert rect_of(result.final, FIRST_AT) == rect_of(BASE_IMAGE, FILE_ROW)


# ---- inside / rc_equal ------------------------------------------------------------------------------------------

def inside_model(x, y, rect):
    rx, ry, rw, rh = rect
    return int(rx <= x < aes.signed(rx + rw) and ry <= y < aes.signed(ry + rh))


BOX = (10, 20, 30, 40)
WRAPPING = (0x7000, 0x7000, 0x2000, 0x2000)      # far edges $9000: negative words, so nothing is inside
# Every edge's both sides, on each axis, and the wrap.
POINTS = {
    "the origin": (10, 20, BOX), "left of it": (9, 20, BOX), "above it": (10, 19, BOX),
    "the last column": (39, 20, BOX), "the far edge across": (40, 20, BOX),
    "the last row": (10, 59, BOX), "the far edge down": (10, 60, BOX),
    "negative, inside": (-5, -5, (-10, -10, 20, 20)),
    "a far edge that wraps": (0x7100, 0x7100, WRAPPING),
    "a far edge across that wraps": (0x7100, 5, (0x7000, 0, 0x2000, 10)),
    "a far edge down that wraps": (5, 0x7100, (0, 0x7000, 10, 0x2000)),
    "the desktop's middle": (160, 100, None), "the menu bar, above the desktop": (160, 5, None),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("shape", sorted(POINTS))
def test_inside(shape, through_line_f):
    x, y, rect = POINTS[shape]
    if rect is None:
        at, pokes, model_rect = DESKTOP_CURR, None, rect_of(BASE_IMAGE, DESKTOP_CURR)
    else:
        at, pokes, model_rect = FIRST_AT, aes.grect_pokes(FIRST_AT, *rect), signed_rect(rect)
    result = run(INSIDE, (x, y, at), pokes, through_line_f=through_line_f)
    assert result.answer() == inside_model(aes.signed(x), aes.signed(y), model_rect)


def test_inside_puts_its_rectangle_on_the_24_bit_bus():
    assert run(INSIDE, (160, 100, DESKTOP_CURR | aes.BUS_TAG)).answer() == 1


PAIRS = {
    "equal": ((1, 2, 3, 4), (1, 2, 3, 4)),
    "x differs": ((9, 2, 3, 4), (1, 2, 3, 4)),
    "y differs": ((1, 9, 3, 4), (1, 2, 3, 4)),
    "w differs": ((1, 2, 9, 4), (1, 2, 3, 4)),
    "h differs": ((1, 2, 3, 9), (1, 2, 3, 4)),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("shape", sorted(PAIRS))
def test_rc_equal(shape, through_line_f):
    first, second = PAIRS[shape]
    result = run(RC_EQUAL, (FIRST_AT, SECOND_AT), two_rects(first, second), through_line_f=through_line_f)
    assert result.answer() == int(first == second)


def test_rc_equal_over_the_snapshot_and_the_24_bit_bus():
    """The desktop's current area against itself (1) and against its full area (0), every pointer tagged."""
    assert run(RC_EQUAL, (DESKTOP_CURR | aes.BUS_TAG, DESKTOP_CURR | aes.BUS_TAG)).answer() == 1
    assert run(RC_EQUAL, (DESKTOP_FULL | aes.BUS_TAG, DESKTOP_CURR | aes.BUS_TAG)).answer() == 0


# ---- rc_union ---------------------------------------------------------------------------------------------------

def union_model(source, into):
    def axis(origin, extent, into_origin, into_extent):
        near = min(into_origin, origin)
        far = max(aes.signed(into_origin + into_extent), aes.signed(origin + extent))
        return near, aes.signed(far - near)
    x, w = axis(source[0], source[2], into[0], into[2])
    y, h = axis(source[1], source[3], into[1], into[3])
    return x, y, w, h


UNIONS = {
    "into inside from": ((0, 0, 320, 200), (10, 20, 30, 40)),
    "from inside into": ((10, 20, 30, 40), (0, 0, 320, 200)),
    "from to the lower right": ((50, 60, 100, 100), (0, 0, 100, 100)),
    "from to the upper left": ((0, 0, 100, 100), (50, 60, 100, 100)),
    "disjoint": ((200, 150, 10, 10), (0, 0, 10, 10)),
    "equal": ((5, 6, 7, 8), (5, 6, 7, 8)),
    "negative origins": ((-50, -40, 10, 10), (-80, 30, 60, 30)),
    "a far edge that wraps": ((0x7000, 0x7000, 0x2000, 0x2000), (0, 0, 10, 10)),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("shape", sorted(UNIONS))
def test_rc_union(shape, through_line_f):
    source, into = UNIONS[shape]
    result = run(RC_UNION, (FIRST_AT, SECOND_AT), two_rects(source, into), through_line_f=through_line_f)
    assert rect_of(result.final, SECOND_AT) == union_model(signed_rect(source), signed_rect(into))
    assert rect_of(result.final, FIRST_AT) == signed_rect(source), "from is only read"


def test_rc_union_s_y_pass_reads_the_x_pass_s_stores():
    """`from` one word below `into`, so from.y is into.x and from.h is into.w — both stored by the x pass (and from.w
    is into.y). into (10, 30, 50, 20) with from.x 5: the x pass joins 10..60 with 5..35 — x 5, w 55; the y pass then
    joins 30..50 with the STORED 5..60 — y 5, h 55. Read before the x stores it would join 10..60: y 10, h 50."""
    from_at = SECOND_AT - aes.WORD_BYTES
    pokes = merge_pokes(aes.grect_pokes(SECOND_AT, 10, 30, 50, 20), aes.field_pokes("GRECT", from_at, X=5))
    result = run(RC_UNION, (from_at, SECOND_AT), pokes)
    assert rect_of(result.final, SECOND_AT) == (5, 5, 55, 55)


def test_rc_union_puts_both_pointers_on_the_24_bit_bus():
    source, into = UNIONS["disjoint"]
    result = run(RC_UNION, (FIRST_AT | aes.BUS_TAG, SECOND_AT | aes.BUS_TAG), two_rects(source, into))
    assert rect_of(result.final, SECOND_AT) == union_model(source, into)


def test_rc_union_of_the_desktop_window_s_rectangles():
    """Real data: the full area joined into the current one, in place."""
    result = run(RC_UNION, (DESKTOP_FULL, DESKTOP_CURR))
    assert rect_of(result.final, DESKTOP_CURR) == union_model(rect_of(BASE_IMAGE, DESKTOP_FULL),
                                                              rect_of(BASE_IMAGE, DESKTOP_CURR))


# ---- rc_constrain -----------------------------------------------------------------------------------------------

def constrain_model(container, rect):
    rect = list(rect)
    for origin, extent in ((0, 2), (1, 3)):
        if container[origin] >= rect[origin]:
            rect[origin] = container[origin]
        far = aes.signed(container[origin] + container[extent])
        if far < aes.signed(rect[origin] + rect[extent]):
            rect[origin] = aes.signed(far - rect[extent])
    return tuple(rect)


CONSTRAINTS = {
    "already inside": ((0, 0, 320, 200), (10, 20, 30, 40)),
    "off to the upper left": ((0, 11, 320, 189), (-20, -5, 30, 40)),
    "off to the lower right": ((0, 11, 320, 189), (300, 190, 30, 40)),
    "wider and taller than its container": ((10, 20, 30, 40), (0, 0, 100, 100)),
    "touching the far edges": ((0, 0, 100, 100), (70, 60, 30, 40)),
    "touching the near edges": ((10, 20, 100, 100), (10, 20, 30, 40)),
    "a far edge that wraps": ((0, 0, 100, 100), (0x7000, 0x7000, 0x2000, 0x2000)),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("shape", sorted(CONSTRAINTS))
def test_rc_constrain(shape, through_line_f):
    container, rect = CONSTRAINTS[shape]
    result = run(RC_CONSTRAIN, (FIRST_AT, SECOND_AT), two_rects(container, rect), through_line_f=through_line_f)
    assert rect_of(result.final, SECOND_AT) == constrain_model(signed_rect(container), signed_rect(rect))
    assert rect_of(result.final, FIRST_AT) == signed_rect(container), "the container is only read"


def test_rc_constrain_reads_the_container_s_extent_after_storing_the_origin():
    """The rectangle laid one GRECT_W above the container's origin, so rect.x IS container.w: pulling rect.x up to
    the container's x (50) rewrites container.w to 50 before it is read — the container's far edge is then
    50 + 50 = 100, not 50 + the staged 400, and the rectangle (80 wide) is pulled back to 20."""
    rect_at = FIRST_AT + aes.GRECT_W
    pokes = aes.grect_pokes(FIRST_AT, 50, 0, 400, 0)
    pokes = merge_pokes(pokes, aes.grect_pokes(rect_at, 10, 0, 80, 0))
    result = run(RC_CONSTRAIN, (FIRST_AT, rect_at), pokes)
    assert aes.signed(result.word(rect_at + aes.GRECT_X)) == 100 - 80


def test_rc_constrain_puts_both_pointers_on_the_24_bit_bus():
    container, rect = CONSTRAINTS["off to the lower right"]
    result = run(RC_CONSTRAIN, (FIRST_AT | aes.BUS_TAG, SECOND_AT | aes.BUS_TAG), two_rects(container, rect))
    assert rect_of(result.final, SECOND_AT) == constrain_model(container, rect)


def test_rc_constrain_of_an_object_to_the_desktop():
    """Real data: the selector's first file row, taken as a screen rectangle, kept inside the desktop's area."""
    result = run(RC_CONSTRAIN, (DESKTOP_CURR, FILE_ROW))
    assert rect_of(result.final, FILE_ROW) == constrain_model(rect_of(BASE_IMAGE, DESKTOP_CURR),
                                                              rect_of(BASE_IMAGE, FILE_ROW))


def test_no_helper_stores_the_mask_word():
    """Hand 68000 returning by `rts`: the call's handler path runs, the return's does not."""
    result = run(RC_UNION, (FIRST_AT, SECOND_AT), two_rects(*UNIONS["disjoint"]), through_line_f=True)
    assert aes.AES_LINEF_MASK_WORD not in result.info["writes"]


# ---- the registry: each routine's dearest realistic shapes priced, and one through Line-F -------------------------
aes.register("the desktop window", R_GET, (DESKTOP_CURR, *ANSWER_WORDS), aes.leaf_machine(onto=STALE_ANSWERS))
aes.register("the desktop window", R_GET, (DESKTOP_CURR, *ANSWER_WORDS), aes.leaf_machine(onto=STALE_ANSWERS),
             through_line_f=True)
aes.register("the desktop's words", R_SET, (FIRST_AT, 0, 11, 320, 189), aes.leaf_machine())
aes.register("the desktop's words", R_SET, (FIRST_AT, 0, 11, 320, 189), aes.leaf_machine(), through_line_f=True)
aes.register("an object's rectangle", RC_COPY, (FILE_ROW, FIRST_AT), aes.leaf_machine())
aes.register("an object's rectangle", RC_COPY, (FILE_ROW, FIRST_AT), aes.leaf_machine(), through_line_f=True)
for _shape in ("the origin", "left of it", "the last row", "the far edge down", "the desktop's middle",
               "the menu bar, above the desktop"):
    _x, _y, _rect = POINTS[_shape]
    _at, _pokes = (DESKTOP_CURR, None) if _rect is None else (FIRST_AT, aes.grect_pokes(FIRST_AT, *_rect))
    aes.register(_shape, INSIDE, (_x, _y, _at), aes.leaf_machine(onto=_pokes))
aes.register("the desktop's middle", INSIDE, (160, 100, DESKTOP_CURR), aes.leaf_machine(), through_line_f=True)
for _shape in ("equal", "x differs", "h differs"):
    aes.register(_shape, RC_EQUAL, (FIRST_AT, SECOND_AT), aes.leaf_machine(onto=two_rects(*PAIRS[_shape])))
aes.register("equal", RC_EQUAL, (FIRST_AT, SECOND_AT), aes.leaf_machine(onto=two_rects(*PAIRS["equal"])),
             through_line_f=True)
for _shape in sorted(UNIONS):
    aes.register(_shape, RC_UNION, (FIRST_AT, SECOND_AT), aes.leaf_machine(onto=two_rects(*UNIONS[_shape])))
aes.register("the desktop window", RC_UNION, (DESKTOP_FULL, DESKTOP_CURR), aes.leaf_machine())
aes.register("disjoint", RC_UNION, (FIRST_AT, SECOND_AT), aes.leaf_machine(onto=two_rects(*UNIONS["disjoint"])),
             through_line_f=True)
for _shape in sorted(CONSTRAINTS):
    aes.register(_shape, RC_CONSTRAIN, (FIRST_AT, SECOND_AT), aes.leaf_machine(onto=two_rects(*CONSTRAINTS[_shape])))
aes.register("an object to the desktop", RC_CONSTRAIN, (DESKTOP_CURR, FILE_ROW), aes.leaf_machine())
aes.register("off to the lower right", RC_CONSTRAIN, (FIRST_AT, SECOND_AT),
             aes.leaf_machine(onto=two_rects(*CONSTRAINTS["off to the lower right"])), through_line_f=True)
