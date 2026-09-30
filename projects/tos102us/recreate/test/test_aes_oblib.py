"""AES get_par ($fed382) and ob_offset ($fea584) — the object layer's worked example: `src/aes/oblib.c`.

    get_par(tree, obj):   obj == 0 -> -1; else walk ob_next until the object whose ob_tail is the one just left
    ob_offset(tree, obj, &x, &y):   *y = *x = 0; do { *x += ob_x; *y += ob_y; obj = get_par(tree, obj) } while (obj != -1)

Both Alcyon C, and between them every surface the object layer has: a tree walked by SIGNED index, a caller's words
stored through at every step, one Alcyon routine Line-F-calling another, and the handler's mask word (ob_offset's
return mask is $30c0, get_par's $00f0). Seeded with the snapshot's own trees — the AES's ROM resource, relocated into
GEMBSS at start-up (`aes.resource_tree`): its first is the file selector, 25 objects four deep. Each routine is entered
DIRECTLY (the row Tier 3 prices) and THROUGH LINE-F, by the call word the ROM's own callers use.
"""
import ctypes

import pytest

from harness import BASE_IMAGE

import aes
import vdi
from case import merge_pokes

GET_PAR = "AES_ROM_GET_PAR"
OB_OFFSET = "AES_ROM_OB_OFFSET"
aes.declare_alcyon(GET_PAR, ctypes.c_uint16, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.WORD_ARG))
aes.declare_alcyon(OB_OFFSET, ctypes.c_uint16, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.WORD_ARG, vdi.LONG_ARG, vdi.LONG_ARG))

# THE SNAPSHOT's FILE SELECTOR (the resource's tree 0), whose shape the cases name: object 1 is the FIRST of the
# root's 24 children (get_par walks all 24 siblings), 24 the LAST (one step), 11 the deepest (root -> 7 -> 10 -> 11),
# 20 the last of 6's nine children.
SELECTOR = aes.resource_tree(0)
FIRST_CHILD, LAST_CHILD, DEEPEST, LAST_OF_NINE = 1, 24, 11, 20
# The two answer words, staged STALE so a skipped clear or store shows.
X_AT = aes.RECTS_AT
Y_AT = aes.RECTS_AT + aes.WORD_BYTES
ANSWERS = merge_pokes(aes.field_pokes("GRECT", X_AT, X=aes.STALE_WORD), aes.field_pokes("GRECT", Y_AT, X=aes.STALE_WORD))


def screen_position(tree, index, image=BASE_IMAGE):
    """The model's sum of ob_x/ob_y up the parents, as words."""
    x = y = 0
    while index != aes.OB_NIL:
        x += aes.read_field(image, "OB", "X", tree + index * aes.OB_BYTES)
        y += aes.read_field(image, "OB", "Y", tree + index * aes.OB_BYTES)
        index = aes.parent_of(tree, index, image) if index != aes.OB_ROOT else aes.OB_NIL
    return x & 0xFFFF, y & 0xFFFF


def get_par(tree, index, pokes=None, **kwargs):
    return aes.run_function(GET_PAR, (tree, index), aes.leaf_machine(onto=pokes), **kwargs)


def ob_offset(tree, index, pokes=None, *, x_at=X_AT, y_at=Y_AT, **kwargs):
    return aes.run_function(OB_OFFSET, (tree, index, x_at, y_at), aes.leaf_machine(onto=merge_pokes(ANSWERS, pokes)),
                            **kwargs)


# ---- get_par -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("index", (FIRST_CHILD, LAST_CHILD, DEEPEST, 8, LAST_OF_NINE, 12))
def test_the_parent_is_found_over_the_snapshot_s_file_selector(index, through_line_f):
    """Every shape of walk: 24 siblings, none, one level down, three siblings to a parent that is not the root."""
    result = get_par(SELECTOR, index, through_line_f=through_line_f)
    assert result.answer() == aes.parent_of(SELECTOR, index)


def test_the_tree_pointer_is_put_on_the_24_bit_bus():
    """An application's tree pointer with a top byte (it reaches the AES through addrin unmasked): the ROM's
    `adda.l` addresses through 24 bits, so the walk is the untagged tree's."""
    assert get_par(SELECTOR | aes.BUS_TAG, FIRST_CHILD).answer() == aes.parent_of(SELECTOR, FIRST_CHILD)


def test_the_root_has_no_parent_and_nothing_is_read():
    """-1 by `moveq`, before any read of the tree: a tree pointer into the I/O page is never followed."""
    result = get_par(aes.OB_NIL & 0xFFFFFF, aes.OB_ROOT)
    assert result.answer() == aes.OB_NIL
    assert not result.info["regs"]["io_events"]


def test_the_index_is_signed_and_reads_the_object_below_the_tree():
    """An object whose ob_next is -1 (a root-level object a caller detached) leads the walk to object -1 — the 24
    bytes BELOW the tree, `muls.w` then `adda.l`. Staged there: a tail that is not 1 (so the walk goes on) and a next
    of 2, whose tail — a leaf's -1 — is the object just left: the answer is 2, reached only through the object below.
    An unsigned index reads 1.5 MB ABOVE the tree instead, where the zeros lead the walk back to the root and -1."""
    tree = aes.TREE_AT + aes.OB_BYTES
    below = aes.object_pokes(aes.TREE_AT, 0, NEXT=2, TAIL=5)
    pokes = merge_pokes(below, aes.tree_pokes([aes.node(None), aes.node(0), aes.node(0)], at=tree),
                        aes.object_pokes(tree, 1, NEXT=aes.OB_NIL))
    assert get_par(tree, 1, pokes).answer() == 2


def test_a_parent_is_the_first_object_whose_tail_is_the_one_left():
    """A staged tree whose first child's next names a SIBLING whose tail happens to be that child: the walk stops
    there, at the sibling, though the links say otherwise — the ROM's test is ob_tail alone."""
    objects = [aes.node(None), aes.node(0), aes.node(0), aes.node(0)]
    pokes = merge_pokes(aes.tree_pokes(objects), aes.object_pokes(aes.TREE_AT, 2, TAIL=1))
    assert get_par(aes.TREE_AT, 1, pokes).answer() == 2


# ---- ob_offset ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("index", (aes.OB_ROOT, FIRST_CHILD, DEEPEST, LAST_OF_NINE))
def test_the_offset_sums_every_ancestor_over_the_snapshot_s_file_selector(index, through_line_f):
    result = ob_offset(SELECTOR, index, through_line_f=through_line_f)
    assert (result.word(X_AT), result.word(Y_AT)) == screen_position(SELECTOR, index)
    assert result.answer() == aes.OB_NIL, "the walk's last get_par, which the desk's binding hands on"


def test_the_tree_and_the_answer_words_are_put_on_the_24_bit_bus():
    """The tree and both answer pointers with a top byte: every one of them addressed through 24 bits."""
    result = ob_offset(SELECTOR | aes.BUS_TAG, DEEPEST, x_at=X_AT | aes.BUS_TAG, y_at=Y_AT | aes.BUS_TAG)
    assert (result.word(X_AT), result.word(Y_AT)) == screen_position(SELECTOR, DEEPEST)


def test_the_sums_are_words_that_wrap():
    """ob_x $7000 in the object and in its parent: $e000, a word, not $1e000 carried."""
    objects = [aes.node(None, X=0x7000, Y=0x8000), aes.node(0, X=0x7000, Y=0x8001)]
    result = ob_offset(aes.TREE_AT, 1, aes.tree_pokes(objects))
    assert (result.word(X_AT), result.word(Y_AT)) == (0xE000, 0x0001)


def test_x_is_stored_before_y_is_read():
    """The ORDER, which only an overlap shows: the x word laid over the object's own ob_y. x is cleared, then
    x += ob_x makes ob_y that sum, and only then is ob_y read into y — the other order would add the cleared 0."""
    objects = [aes.node(None, X=3, Y=5), aes.node(0, X=40, Y=60)]
    y_of_object_1 = aes.TREE_AT + aes.OB_BYTES + aes.OB_Y
    result = ob_offset(aes.TREE_AT, 1, aes.tree_pokes(objects), x_at=y_of_object_1)
    assert result.word(Y_AT) == 40 + 5


def test_an_answer_word_over_an_ancestor_doubles_it():
    """x laid over the PARENT's ob_x: the clear zeroes it, the child's step adds 40 to it, and the parent's step adds
    the word to itself — stored through at every step, never summed in a register."""
    objects = [aes.node(None), aes.node(0, X=7), aes.node(1, X=40)]
    x_of_object_1 = aes.TREE_AT + aes.OB_BYTES + aes.OB_X
    result = ob_offset(aes.TREE_AT, 2, aes.tree_pokes(objects), x_at=x_of_object_1)
    assert result.word(x_of_object_1) == 2 * 40


def test_one_word_for_both_answers_accumulates_both():
    objects = [aes.node(None, X=1, Y=2), aes.node(0, X=30, Y=400)]
    assert ob_offset(aes.TREE_AT, 1, aes.tree_pokes(objects), y_at=X_AT).word(X_AT) == 1 + 2 + 30 + 400


# ---- the registry ------------------------------------------------------------------------------------------------
# DIRECT rows priced (the mask word staged at what the run leaves, and dropped at Tier 3 with its companion); each
# routine's THROUGH-LINE-F row verified and unpriced. The worst realistic rows: get_par across all 24 siblings, and
# ob_offset of that first child, whose one get_par is that walk; the cheapest: the root.
aes.register("the root", GET_PAR, (SELECTOR, aes.OB_ROOT), aes.leaf_machine())
aes.register("the last child, one step", GET_PAR, (SELECTOR, LAST_CHILD), aes.leaf_machine())
aes.register("the first of 24 siblings", GET_PAR, (SELECTOR, FIRST_CHILD), aes.leaf_machine())
aes.register("the first of 24 siblings", GET_PAR, (SELECTOR, FIRST_CHILD), aes.leaf_machine(), through_line_f=True)
aes.register("the root", OB_OFFSET, (SELECTOR, aes.OB_ROOT, X_AT, Y_AT), aes.leaf_machine(onto=ANSWERS))
aes.register("the deepest, four levels", OB_OFFSET, (SELECTOR, DEEPEST, X_AT, Y_AT), aes.leaf_machine(onto=ANSWERS))
aes.register("the first of 24 siblings", OB_OFFSET, (SELECTOR, FIRST_CHILD, X_AT, Y_AT), aes.leaf_machine(onto=ANSWERS))
aes.register("the deepest, four levels", OB_OFFSET, (SELECTOR, DEEPEST, X_AT, Y_AT), aes.leaf_machine(onto=ANSWERS),
             through_line_f=True)
