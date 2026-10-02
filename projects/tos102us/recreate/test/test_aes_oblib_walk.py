"""AES ob_sst ($fed19e) and everyobj ($fed27c) — the object library's field read-out and its depth-first walk, in
`src/aes/oblib.c` beside get_par and ob_offset.

    ob_sst(tree, obj, &spec, &state, &type, &flags, &rect, &thick)
        rect.w/h, *flags, *spec, *state, *type = ob_type & $ff; INDIRECT (flags bit 8): *spec = *(long *)ob_spec;
        *thick by type, reading type, spec and flags BACK through the pointers (box: spec byte 1, text: te_thickness,
        button: -1 less EXIT less DEFAULT, title: 1, else 0), then > 128 -> -256; D0.w = *spec's first byte, ext.w
    everyobj(tree, first, last, routine, x, y, max_depth)
        pre-order from `first` until `last` or the root, calling routine(tree, obj, x', y') per object (x', y' its
        position: the sum of ob_x/ob_y down from x, y); into a child unless HIDETREE or the depth passes max_depth

Both Alcyon C (ob_sst returns by the mask $3880, everyobj by $00f8: the mask word is stored and dropped by name).
Seeded with the snapshot's FILE SELECTOR (the AES resource's tree 0, 25 objects four deep: boxes, a box char, boxed
and formatted text, strings and two buttons), copied into the staged band where a case changes it.

everyobj's ROUTINE is an Alcyon routine its caller hands in (just_draw, mkrect); a case stages its own — `LOGGER`,
which appends each call's frame (tree, object, x, y) to a log, and `HIDER`, which logs and then sets the object's
HIDETREE so the walk, reading the object AGAIN after the call, does not go into it. The candidate reaches it through
`staged_call.h`'s `call_alcyon_object` (the register-carrying hook, `isr.REGISTERS_HOOK`), bound to the same effect
in Python by the door's one builder, `aes.alcyon_object_hook`.
"""
import struct
from collections import namedtuple

import pytest

from harness import BASE_IMAGE, emu, make_image
from recreate_kit.os_map import OS_BUS_ADDR_MASK

import aes
import case
import isr
import routines
import vdi
import vdi_helpers
from aes import signed
from case import merge_pokes
from opcodes import (ADDA_L_D0_A0, BSET_IMMEDIATE_D16_A0, LEA_ABSOLUTE_LONG_A0, MOVE_L_STACK_TO_A0_POSTINC,
                     MOVE_W_IMMEDIATE_D16_A0, MOVE_W_STACK_D0, MOVE_W_STACK_TO_A0_POSTINC, MOVEA_L_STACK_A0,
                     MULS_W_IMMEDIATE_D0, RTS)

OB_SST, EVERYOBJ = "AES_ROM_OB_SST", "AES_ROM_EVERYOBJ"
L, W = vdi.LONG_ARG, vdi.WORD_ARG
aes.declare_alcyon(OB_SST, aes.WORD_ANSWER, (vdi.IMAGE_ARG, L, W, L, L, L, L, L, L))
aes.declare_alcyon(EVERYOBJ, None, (vdi.IMAGE_ARG, L, W, W, L, W, W, W))

SELECTOR = aes.resource_tree(0)
SELECTOR_OBJECTS = aes.tree_length(SELECTOR)
COPY = aes.TREE_AT
SELECTOR_COPY = {COPY: bytes(BASE_IMAGE[SELECTOR:SELECTOR + SELECTOR_OBJECTS * aes.OB_BYTES])}
OK, CANCEL = 21, 22
EXIT, DEFAULT = 1 << aes.OB_FLAG_EXIT_BIT, 1 << aes.OB_FLAG_DEFAULT_BIT
INDIRECT = 1 << (8 + aes.OB_FLAG_INDIRECT_BIT)
HIDETREE = 1 << aes.OB_FLAG_HIDETREE_BIT
EVERYOBJ_LEVELS = 8                     # oblib.c's: the frame's two arrays of eight words

# ---- ob_sst's answers: the spec, state, type, flags, a GRECT and the thickness, staged STALE ----------------------
SPEC_AT = aes.RECTS_AT
STATE_AT = SPEC_AT + aes.LONG_BYTES
TYPE_AT = STATE_AT + aes.WORD_BYTES
FLAGS_AT = TYPE_AT + aes.WORD_BYTES
RECT_AT = FLAGS_AT + aes.WORD_BYTES
THICK_AT = RECT_AT + aes.GRECT_BYTES
ANSWERS_END = THICK_AT + aes.WORD_BYTES
STALE_ANSWERS = {SPEC_AT: bytes([0xA5] * (ANSWERS_END - SPEC_AT))}
ANSWER_POINTERS = (SPEC_AT, STATE_AT, TYPE_AT, FLAGS_AT, RECT_AT, THICK_AT)
STAGED_TEDINFO = aes.BLOCKS_AT
INDIRECT_SPEC = aes.BLOCKS_AT + aes.TE_BYTES


def sst_model(image, tree, index):
    """(spec, state, type, flags, w, h, thickness, answer) as the ROM leaves them, no answer pointers overlapping."""
    obj = aes.read_object(image, tree, index)
    spec = obj["SPEC"]
    if obj["FLAGS"] & INDIRECT:
        spec = case.long_in(image, spec & OS_BUS_ADDR_MASK)
    kind = obj["TYPE"] & aes.OB_TYPE_MASK
    if kind in (aes.G_BOX, aes.G_IBOX, aes.G_BOXCHAR):
        thickness = signed(spec >> 16 & 0xFF, 8)
    elif kind in (aes.G_TEXT, aes.G_BOXTEXT, aes.G_FTEXT, aes.G_FBOXTEXT):
        thickness = signed(case.word_in(image, (spec + aes.TE_THICKNESS) & OS_BUS_ADDR_MASK))
    elif kind == aes.G_BUTTON:
        thickness = -1 - bool(obj["FLAGS"] & EXIT) - bool(obj["FLAGS"] & DEFAULT)
    else:
        thickness = 1 if kind == aes.G_TITLE else 0
    if thickness > 128:
        thickness -= 256
    return spec, obj["STATE"], kind, obj["FLAGS"], obj["WIDTH"], obj["HEIGHT"], thickness & 0xFFFF, signed(spec >> 24, 8)


def sst(tree, index, pokes=None, pointers=ANSWER_POINTERS, **kwargs):
    return aes.run_function(OB_SST, (tree, index, *pointers), aes.leaf_machine(onto=merge_pokes(STALE_ANSWERS, pokes)),
                            **kwargs)


def sst_answers(result):
    return (result.long(SPEC_AT), result.word(STATE_AT), result.word(TYPE_AT), result.word(FLAGS_AT),
            result.word(RECT_AT + aes.GRECT_W), result.word(RECT_AT + aes.GRECT_H), result.word(THICK_AT), result.answer())


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("index", range(SELECTOR_OBJECTS))
def test_ob_sst_over_every_object_of_the_file_selector(index, through_line_f):
    """Boxes (spec byte 1 the thickness), a box char, boxed and formatted text (te_thickness), strings (0), OK (DEFAULT
    and EXIT: -3) and Cancel (EXIT: -2)."""
    result = sst(SELECTOR, index, through_line_f=through_line_f)
    assert sst_answers(result) == sst_model(BASE_IMAGE, SELECTOR, index)
    assert result.word(RECT_AT + aes.GRECT_X) == 0xA5A5, "x and y are not touched"


# Every arm the selector does not reach: G_TEXT, G_FTEXT, G_TITLE, an image (0), types below and above the switch
# (its `bhi` is unsigned: 19 wraps huge), a type word whose HIGH byte is set, a plain button, and the byte wrap.
def staged_object(kind, spec=0, flags=0, thickness=None):
    pokes = aes.tree_pokes([aes.node(None, TYPE=kind, FLAGS=flags, SPEC=spec, STATE=0x1234, WIDTH=40, HEIGHT=-2)])
    if thickness is not None:
        pokes = merge_pokes(pokes, aes.tedinfo_pokes(STAGED_TEDINFO, THICKNESS=thickness))
    return pokes


STAGED = {
    "G_TEXT": (aes.G_TEXT, STAGED_TEDINFO, 0, 2),
    "G_FTEXT, a thickness of 129": (aes.G_FTEXT, STAGED_TEDINFO, 0, 129),
    "G_FBOXTEXT, a thickness of 128": (aes.G_FBOXTEXT, STAGED_TEDINFO, 0, 128),
    "G_BOXTEXT, a thickness of $8000": (aes.G_BOXTEXT, STAGED_TEDINFO, 0, 0x8000),
    "G_TEXT, a thickness of -1": (aes.G_TEXT, STAGED_TEDINFO, 0, 0xFFFF),
    "G_TITLE": (aes.G_TITLE, 0x00000000, 0, None),
    "G_IMAGE": (23, 0x12345678, 0, None),
    "type 19": (19, 0x01020304, 0, None),
    "type 33": (33, 0x01020304, 0, None),
    "a high byte over G_BOX": (0x1200 | aes.G_BOX, 0x80FE0000, 0, None),
    "G_BOX, a negative spec": (aes.G_BOX, 0xFFFF1100, 0, None),
    "G_BOX, a border of $80": (aes.G_BOX, 0x00801100, 0, None),
    "G_IBOX": (aes.G_IBOX, 0x00FE1100, 0, None),
    "a plain button": (aes.G_BUTTON, 0, 0, None),
    "an EXIT button": (aes.G_BUTTON, 0, EXIT, None),
    "a DEFAULT button": (aes.G_BUTTON, 0, DEFAULT | 0x80, None),
}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("shape", sorted(STAGED))
def test_ob_sst_over_staged_objects(shape, through_line_f):
    pokes = staged_object(*STAGED[shape])
    result = sst(aes.TREE_AT, 0, pokes, through_line_f=through_line_f)
    assert sst_answers(result) == sst_model(case.final_image(result.info, result.staged), aes.TREE_AT, 0)


def test_ob_sst_follows_an_indirect_spec():
    """INDIRECT (bit 0 of ob_flags' HIGH byte): the spec answered is the longword ob_spec POINTS AT — here a
    TEDINFO's address, whose te_thickness then counts — read again from the object after the flags are stored."""
    pokes = merge_pokes(staged_object(aes.G_FTEXT, INDIRECT_SPEC | aes.BUS_TAG, INDIRECT, thickness=5),
                        {INDIRECT_SPEC: struct.pack(">I", STAGED_TEDINFO)})
    result = sst(aes.TREE_AT, 0, pokes)
    assert result.long(SPEC_AT) == STAGED_TEDINFO and result.word(THICK_AT) == 5


INDIRECT_OTHER = INDIRECT_SPEC + aes.LONG_BYTES      # a second longword an overwritten spec pointer would name


def test_ob_sst_follows_the_object_s_spec_not_the_stored_one():
    """The state's answer laid over the spec's LOW word: stored after the spec, it rewrites the stored pointer to
    INDIRECT_OTHER — and the INDIRECT follow reads ob_spec again FROM THE OBJECT, so INDIRECT_SPEC's longword is what
    is answered."""
    pokes = merge_pokes(staged_object(aes.G_BOX, INDIRECT_SPEC, INDIRECT),
                        aes.object_pokes(aes.TREE_AT, 0, STATE=INDIRECT_OTHER & 0xFFFF),
                        {INDIRECT_SPEC: struct.pack(">II", 0x00041100, 0x00051100)})
    result = sst(aes.TREE_AT, 0, pokes, pointers=(SPEC_AT, SPEC_AT + aes.WORD_BYTES, TYPE_AT, FLAGS_AT, RECT_AT, THICK_AT))
    assert result.long(SPEC_AT) == 0x00041100 and result.word(THICK_AT) == 4


def test_ob_sst_reads_the_type_back_after_the_indirect_spec():
    """The type's answer laid over the spec's HIGH word: the INDIRECT spec, stored after the type, rewrites it — so
    the border switch reads the spec's high word as the type: $0015, G_TEXT, whose te_thickness then counts."""
    pokes = merge_pokes(staged_object(aes.G_BOX, INDIRECT_SPEC, INDIRECT, thickness=6),
                        {INDIRECT_SPEC: struct.pack(">I", aes.G_TEXT << 16 | STAGED_TEDINFO & 0xFFFF)})
    result = sst(aes.TREE_AT, 0, pokes, pointers=(SPEC_AT, STATE_AT, SPEC_AT, FLAGS_AT, RECT_AT, THICK_AT))
    te_thickness = case.word_in(case.final_image(result.info, result.staged),
                                (aes.G_TEXT << 16 | STAGED_TEDINFO & 0xFFFF) + aes.TE_THICKNESS)
    assert result.word(THICK_AT) == te_thickness


def test_ob_sst_reads_the_spec_back_through_its_pointer():
    """The type's answer laid over the spec's first word: the type (G_BOX, 20) is stored over the spec's high word
    AFTER the spec, and the box arm reads the thickness back as the spec's second byte — the type's low byte."""
    result = sst(aes.TREE_AT, 0, staged_object(aes.G_BOX, 0x00FF1100), pointers=(SPEC_AT, STATE_AT, SPEC_AT, FLAGS_AT,
                                                                                   RECT_AT, THICK_AT))
    assert result.word(THICK_AT) == aes.G_BOX
    assert result.answer() == 0, "the answer, the spec's first byte, read back too: the type's high byte"


def test_ob_sst_reads_the_flags_back_through_their_pointer():
    """The state's answer laid over the flags': the state ($0100) is stored over the flags after them, and the
    INDIRECT test reads the flags word BACK — the state's high byte, so the spec is followed."""
    pokes = merge_pokes(staged_object(aes.G_BOX, INDIRECT_SPEC), aes.object_pokes(aes.TREE_AT, 0, STATE=0x0100),
                        {INDIRECT_SPEC: struct.pack(">I", 0x00031100)})
    result = sst(aes.TREE_AT, 0, pokes, pointers=(SPEC_AT, FLAGS_AT, TYPE_AT, FLAGS_AT, RECT_AT, THICK_AT))
    assert result.long(SPEC_AT) == 0x00031100 and result.word(THICK_AT) == 3


def test_ob_sst_answers_the_thickness_s_high_byte_when_they_overlap():
    """The thickness laid over the spec: stored last, it is what the answer reads back — -3's high byte, $ff."""
    result = sst(COPY, OK, SELECTOR_COPY, pointers=(SPEC_AT, STATE_AT, TYPE_AT, FLAGS_AT, RECT_AT, SPEC_AT))
    assert result.answer() == -1


def test_ob_sst_puts_every_pointer_on_the_24_bit_bus():
    tagged = tuple(at | aes.BUS_TAG for at in ANSWER_POINTERS)
    result = sst(SELECTOR | aes.BUS_TAG, 12, pointers=tagged)
    assert sst_answers(result) == sst_model(BASE_IMAGE, SELECTOR, 12)


# ---- everyobj -----------------------------------------------------------------------------------------------------
BAND_BYTES = 0x200
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + 0x1000, BAND_BYTES, "test/test_aes_oblib_walk.py: everyobj's routines and log")
# THE LOG: one SLOT per object, the call's tree, x and y, stored by index — so the routine reads nothing it writes
# (a log POINTER it read and stored back would be inverted by the attribution pass and steer the poisoned run), and
# a slot left stale is an object never visited. The visiting ORDER is the model's claim, not the log's.
LOG_AT = BAND_AT
LOG_SLOT = struct.Struct(">Ihh")        # tree, x, y
LOG_OBJECTS = aes.TREE_OBJECTS
LOG_BYTES = LOG_OBJECTS * LOG_SLOT.size
STALE_SLOT = bytes([0xA5]) * LOG_SLOT.size
STALE_LOG = {LOG_AT: STALE_SLOT * LOG_OBJECTS}
ROUTINE_AT = LOG_AT + LOG_BYTES
FRAME_TREE, FRAME_OBJECT, FRAME_X, FRAME_Y = 4, 8, 10, 12
# The object's slot := (tree, x, y).
LOG_CODE = struct.pack(">HH HH HI H HH HH HH", MOVE_W_STACK_D0, FRAME_OBJECT, MULS_W_IMMEDIATE_D0, LOG_SLOT.size,
                       LEA_ABSOLUTE_LONG_A0, LOG_AT, ADDA_L_D0_A0,
                       MOVE_L_STACK_TO_A0_POSTINC, FRAME_TREE, MOVE_W_STACK_TO_A0_POSTINC, FRAME_X,
                       MOVE_W_STACK_TO_A0_POSTINC, FRAME_Y)
# ...and then the object's HIDETREE set (bit 7 of ob_flags' low byte).
HIDE_CODE = struct.pack(">HH HH HH H HHH", MOVEA_L_STACK_A0, FRAME_TREE, MOVE_W_STACK_D0, FRAME_OBJECT,
                        MULS_W_IMMEDIATE_D0, aes.OB_BYTES, ADDA_L_D0_A0,
                        BSET_IMMEDIATE_D16_A0, aes.OB_FLAG_HIDETREE_BIT, aes.OB_FLAGS + aes.OB_WORD_LOW_BYTE)
# ...or its ob_head set to -1 (the object pointer as HIDE_CODE forms it, then `move.w #-1,2(a0)`).
PRUNE_CODE = HIDE_CODE[:-6] + struct.pack(">HhH", MOVE_W_IMMEDIATE_D16_A0, aes.OB_NIL, aes.OB_HEAD)
LOGGER = LOG_CODE + RTS
HIDER = LOG_CODE + HIDE_CODE + RTS
PRUNER = LOG_CODE + PRUNE_CODE + RTS
assert ROUTINE_AT + max(len(HIDER), len(PRUNER)) <= BAND_AT + BAND_BYTES


def frame_of(registers):
    """`call_alcyon_object`'s three slots back into the frame's (tree, object, x, y)."""
    packed = registers[isr.REGISTER["d1"]]
    return (registers[isr.REGISTER["a0"]], signed(registers[isr.REGISTER["d0"]] & 0xFFFF), signed(packed >> 16),
            signed(packed & 0xFFFF))


def _log(buf, registers):
    """The logger's effect over the candidate's image."""
    tree, index, x, y = frame_of(registers)
    isr.poke(buf, (LOG_AT + index * LOG_SLOT.size) & OS_BUS_ADDR_MASK, LOG_SLOT.pack(tree, x, y))


def _hide(buf, registers):
    """The hider's: the log, then the object's HIDETREE set."""
    _log(buf, registers)
    tree, index, _x, _y = frame_of(registers)
    buf[(tree + index * aes.OB_BYTES + aes.OB_FLAGS + aes.OB_WORD_LOW_BYTE) & OS_BUS_ADDR_MASK] |= HIDETREE


def _prune(buf, registers):
    """The pruner's: the log, then the object's ob_head -1."""
    _log(buf, registers)
    tree, index, _x, _y = frame_of(registers)
    isr.poke(buf, (tree + index * aes.OB_BYTES + aes.OB_HEAD) & OS_BUS_ADDR_MASK, (aes.OB_NIL & 0xFFFF).to_bytes(2, "big"))


ROUTINES = {"logger": (LOGGER, _log), "hider": (HIDER, _hide), "pruner": (PRUNER, _prune)}


def routine_pokes(routine):
    return merge_pokes({ROUTINE_AT: ROUTINES[routine][0]}, STALE_LOG)


def routine_hook(routine):
    """The candidate's side of `routine`: its effect bound at ROUTINE_AT, as `aes.run_function`'s `hook`."""
    return aes.alcyon_object_hook({ROUTINE_AT: ROUTINES[routine]})


def walk(tree, first, last, pokes=None, *, routine="logger", x=0, y=0, max_depth=8, **kwargs):
    """everyobj over `pokes` with `routine` staged, the candidate's calls served by the same effect."""
    return aes.run_function(EVERYOBJ, (tree, first, last, ROUTINE_AT, x, y, max_depth),
                            aes.leaf_machine(onto=merge_pokes(routine_pokes(routine), pokes)), hook=routine_hook(routine),
                            **kwargs)


def logged(result):
    """The calls the routine logged, as (tree, object, x, y) in object order."""
    slots = (result.after(LOG_AT + index * LOG_SLOT.size, LOG_SLOT.size) for index in range(LOG_OBJECTS))
    return [(tree, index, x, y) for index, slot in enumerate(slots) if slot != STALE_SLOT
            for tree, x, y in (LOG_SLOT.unpack(slot),)]


def by_object(call):
    return call[1]


def walk_model(tree, first, last, x, y, max_depth, image=BASE_IMAGE):
    """The walk as a pre-order recursion: an object, then its children (unless it is hidden, childless, or its
    depth passes max_depth), then its next sibling — until `last` or the root's end."""
    calls = []

    def word(index, name):
        return signed(aes.read_field(image, "OB", name, tree + index * aes.OB_BYTES))

    def visit(index, depth, parent_x, parent_y):
        at_x, at_y = signed((parent_x + word(index, "X")) & 0xFFFF), signed((parent_y + word(index, "Y")) & 0xFFFF)
        calls.append((tree, index, at_x, at_y))
        child = word(index, "HEAD")
        if child != aes.OB_NIL and not word(index, "FLAGS") & HIDETREE and depth <= max_depth:
            while child != index and child != last:
                visit(child, depth + 1, at_x, at_y)
                child = word(child, "NEXT")

    index = first
    while index != last:
        visit(index, 1, x, y)
        following = word(index, "NEXT")
        if following == last or index == aes.OB_ROOT or word(following, "TAIL") == index:
            break
        index = following
    return calls


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("max_depth", (8, 2, 1, 0))
def test_everyobj_walks_the_file_selector_from_its_root(max_depth, through_line_f):
    """All 25 objects four deep, from a start position; the depth limit cutting it to two, one and no levels below
    the root."""
    result = walk(SELECTOR, aes.OB_ROOT, aes.OB_NIL, x=10, y=-20, max_depth=max_depth, through_line_f=through_line_f)
    assert logged(result) == sorted(walk_model(SELECTOR, aes.OB_ROOT, aes.OB_NIL, 10, -20, max_depth), key=by_object)


@pytest.mark.parametrize("first", (7, 6, 10, 1))
def test_everyobj_walks_a_subtree_as_ob_draw_asks(first):
    """ob_draw's shape: from an object to its own ob_next — its subtree alone (7: two levels, 6: nine children, 10: a
    LAST child, whose ob_next is its parent, so the climb back from its child stops on `last` and not on a tail,
    1: a leaf)."""
    last = signed(aes.read_field(BASE_IMAGE, "OB", "NEXT", SELECTOR + first * aes.OB_BYTES))
    result = walk(SELECTOR, first, last, x=3, y=4)
    assert logged(result) == sorted(walk_model(SELECTOR, first, last, 3, 4, 8), key=by_object)


def test_everyobj_does_not_enter_a_hidden_subtree():
    pokes = merge_pokes(SELECTOR_COPY, aes.object_pokes(COPY, 6, FLAGS=HIDETREE))
    result = walk(COPY, aes.OB_ROOT, aes.OB_NIL, pokes)
    image = case.final_image(result.info, result.staged)
    assert logged(result) == sorted(walk_model(COPY, aes.OB_ROOT, aes.OB_NIL, 0, 0, 8, image), key=by_object)
    assert all(index not in range(12, 21) for _tree, index, _x, _y in logged(result))


def test_everyobj_reads_the_object_again_after_the_call():
    """The HIDER sets each object's HIDETREE inside the call: the walk, reading ob_flags after it, enters nothing —
    the root alone is visited. Read before the call, it would walk all 25."""
    result = walk(COPY, aes.OB_ROOT, aes.OB_NIL, SELECTOR_COPY, routine="hider")
    assert [index for _tree, index, _x, _y in logged(result)] == [aes.OB_ROOT]


def test_everyobj_reads_the_head_again_after_the_call():
    """The PRUNER sets each object's ob_head to -1 inside the call: read after it, the root has no children."""
    result = walk(COPY, aes.OB_ROOT, aes.OB_NIL, SELECTOR_COPY, routine="pruner")
    assert [index for _tree, index, _x, _y in logged(result)] == [aes.OB_ROOT]


def test_everyobj_s_hider_across_siblings():
    """From the root's first child to -1: each child is hidden in its call, so the walk goes across every one of the
    root's children and up to the root, where it stops — no grandchild visited."""
    result = walk(COPY, 1, aes.OB_NIL, SELECTOR_COPY, routine="hider")
    children = [index for index in range(1, SELECTOR_OBJECTS) if aes.parent_of(SELECTOR, index) == aes.OB_ROOT]
    assert [index for _tree, index, _x, _y in logged(result)] == children


def test_everyobj_positions_are_words_that_wrap():
    objects = [aes.node(None, X=0x7000, Y=-0x8000), aes.node(0, X=0x7000, Y=-1)]
    result = walk(aes.TREE_AT, aes.OB_ROOT, aes.OB_NIL, aes.tree_pokes(objects), x=0x1000)
    assert logged(result) == [(aes.TREE_AT, 0, signed(0x8000), -0x8000), (aes.TREE_AT, 1, signed(0xF000), 0x7FFF)]


def chain(levels):
    """A tree `levels` deep, each object the only child of the one before."""
    return aes.tree_pokes([aes.node(None)] + [aes.node(index) for index in range(levels - 1)])


def test_everyobj_s_deepest_walk_that_fits_its_frame():
    """Seven levels: the last uses x[7], y[7], the arrays' last words."""
    result = walk(aes.TREE_AT, aes.OB_ROOT, aes.OB_NIL, chain(EVERYOBJ_LEVELS - 1))
    assert [index for _tree, index, _x, _y in logged(result)] == list(range(EVERYOBJ_LEVELS - 1))


def test_a_descent_onto_last_at_the_eighth_level_ends_the_walk_without_a_halt():
    """Eight deep, but the eighth object is `last`: the walk ends before storing x[8] — in the ROM and here alike, so
    the halt below is taken only when a store at the level follows."""
    last = EVERYOBJ_LEVELS - 1
    result = walk(aes.TREE_AT, aes.OB_ROOT, last, chain(EVERYOBJ_LEVELS))
    assert [index for _tree, index, _x, _y in logged(result)] == list(range(last))


def test_a_climb_to_the_root_s_level_that_ends_the_walk_takes_no_halt():
    """From a child of the root to the root's end: the last sibling's climb reaches level 0 — below `first`'s — and
    the walk ends there without a store, so neither side reads x[-1]."""
    result = walk(SELECTOR, 1, aes.OB_NIL)
    assert logged(result) == sorted(walk_model(SELECTOR, 1, aes.OB_NIL, 0, 0, EVERYOBJ_LEVELS), key=by_object)


# ---- a level outside everyobj's frame arrays: the same named halt on BOTH builds (oblib.c says why) ----------------
# Eight deep, the eighth level would be x[8] — the ROM's saved frame pointer. And a climb above `first`'s level: object
# 2 names its own sibling 1 as its ob_tail (a caller's tree, as objc_draw hands one in), so the climb from 1 lands at
# level 0 and visits 3 there, where the ROM reads x[-1] and y[-1] — its own frame's y[7] and saved D7. Each is
# (the tree, its objects, `first`, the objects visited before the halt).
OutOfFrame = namedtuple("OutOfFrame", "pokes objects first visited")
CLIMB_FIRST = 1
OUT_OF_FRAME = {
    "eight levels deep": OutOfFrame(chain(EVERYOBJ_LEVELS), EVERYOBJ_LEVELS, aes.OB_ROOT, list(range(EVERYOBJ_LEVELS - 1))),
    "a climb above the first level": OutOfFrame(
        merge_pokes(aes.tree_pokes([aes.node(None), aes.node(0, X=1), aes.node(0, X=2), aes.node(0, X=3, Y=4)]),
                    aes.object_pokes(aes.TREE_AT, 2, TAIL=1)), 4, CLIMB_FIRST, [CLIMB_FIRST]),
}
EVERYOBJ_HALT = "not reconstructed: AES everyobj: a level outside its 8-word frame arrays"
NO_OP_HOOK = ("cb = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p)(lambda *a: None); "
              "ctypes.c_void_p.in_dll(lib, 'recreate_call_vector_registers').value = "
              "ctypes.cast(cb, ctypes.c_void_p).value")
EVERYOBJ_ARGTYPES = ["ctypes.c_void_p", "ctypes.c_uint32", "ctypes.c_int16", "ctypes.c_int16", "ctypes.c_uint32",
                     "ctypes.c_int16", "ctypes.c_int16", "ctypes.c_int16"]


def out_of_frame_arguments(case_):
    """everyobj's arguments for one `OUT_OF_FRAME` walk: from `first` to the root's end, at the depth GEM programs pass."""
    return (aes.TREE_AT, case_.first, aes.OB_NIL, ROUTINE_AT, 0, 0, EVERYOBJ_LEVELS)


@pytest.mark.parametrize("case_", OUT_OF_FRAME.values(), ids=OUT_OF_FRAME.keys())
def test_a_walk_outside_the_frame_halts_by_name_on_the_host(case_):
    tree_bytes = bytes(make_image(case_.pokes)[aes.TREE_AT:aes.TREE_AT + case_.objects * aes.OB_BYTES])
    prelude = (f"{vdi_helpers.FRESH_IMAGE}; {NO_OP_HOOK}; "
               f"ctypes.memmove(ctypes.addressof(buf) + {aes.TREE_AT}, {tree_bytes!r}, {len(tree_bytes)})")
    returncode, stderr = vdi_helpers.refusal(routines.core_symbol(EVERYOBJ), EVERYOBJ_ARGTYPES,
                                             ", ".join(map(str, ("buf", *out_of_frame_arguments(case_)))), prelude=prelude)
    assert returncode != 0 and EVERYOBJ_HALT in stderr, stderr


# ...and ON TARGET, where the C would otherwise store past `across[]`/`down[]` (undefined behaviour: before the halt,
# the eight-level walk returned and a nine-level one never did). `recreate_not_reconstructed` is `trap #7` there
# (recreate_kit's recreate.h), so its vector is pointed at the sentinel: the run STOPS at the halt, and the log shows
# where — every object before the out-of-range level visited, the one at it never. The blob is run ALONE
# (`RomBench._call`), there being no ROM run to compare with a halt; safe here, as everyobj touches no chip.
TRAP_VECTORS_AT = 0x80                  # the 68000's trap #0..#15 vectors
TRAP_7_VECTOR = TRAP_VECTORS_AT + 7 * vdi.LONG_BYTES


@pytest.fixture(scope="module")
def bench():
    """The cross-compiled blob — a missing one FAILS rather than skips (`test_tier3.py`'s fixture)."""
    from recreate_kit.rom_bench import RomBench
    return RomBench()


@pytest.mark.parametrize("case_", OUT_OF_FRAME.values(), ids=OUT_OF_FRAME.keys())
def test_the_target_build_halts_where_the_host_does(bench, case_):
    image = make_image(merge_pokes(aes.leaf_machine(onto=merge_pokes(routine_pokes("logger"), case_.pokes)),
                                   {TRAP_7_VECTOR: emu.SENTINEL.to_bytes(vdi.LONG_BYTES, "big")}))
    words = tuple(value & 0xFFFF_FFFF for value in out_of_frame_arguments(case_))
    bench._call(image, routines.core_symbol(EVERYOBJ), (0, *words))       # the image argument: 0 in ROM mode
    slot_at = (LOG_AT + index * LOG_SLOT.size for index in range(LOG_OBJECTS))
    assert [index for index, at in enumerate(slot_at) if image[at:at + LOG_SLOT.size] != STALE_SLOT] == case_.visited


def test_everyobj_puts_its_tree_on_the_24_bit_bus():
    """The tree with a top byte: every object read through 24 bits, and the routine handed the TAGGED tree."""
    result = walk(SELECTOR | aes.BUS_TAG, 7, 12)
    assert logged(result) == sorted(((SELECTOR | aes.BUS_TAG, *call[1:]) for call in walk_model(SELECTOR, 7, 12, 0, 0, 8)),
                                   key=by_object)


# ---- the registry. Both cores take more C arguments than the harness's argument area holds (ob_sst nine, everyobj
# eight): Tier 3 enters their C lower by the bytes that do not fit (`rom_bench._stack_args_overflow`), so the direct
# rows are priced — everyobj's through its routine's Alcyon frame on target (`staged_call.h`). The rows: OK's button
# arm, a text row's TEDINFO, the root's box and a string's default; the whole selector walked, and a leaf alone; one
# of each through Line-F.
_OB_SST = aes.leaf_machine(onto=STALE_ANSWERS)
aes.register("OK, a button", OB_SST, (SELECTOR, OK, *ANSWER_POINTERS), _OB_SST)
aes.register("a formatted text row", OB_SST, (SELECTOR, 12, *ANSWER_POINTERS), _OB_SST)
aes.register("the root, a box", OB_SST, (SELECTOR, aes.OB_ROOT, *ANSWER_POINTERS), _OB_SST)
aes.register("a string", OB_SST, (SELECTOR, 1, *ANSWER_POINTERS), _OB_SST)
aes.register("OK, a button", OB_SST, (SELECTOR, OK, *ANSWER_POINTERS), _OB_SST, through_line_f=True)
_WALK, _LOGGED = aes.leaf_machine(onto=routine_pokes("logger")), routine_hook("logger")
aes.register("the file selector from its root", EVERYOBJ, (SELECTOR, aes.OB_ROOT, aes.OB_NIL, ROUTINE_AT, 0, 0, 8), _WALK,
             hook=_LOGGED)
aes.register("a leaf alone", EVERYOBJ, (SELECTOR, 1, 2, ROUTINE_AT, 0, 0, 8), _WALK, hook=_LOGGED)
aes.register("the file selector from its root", EVERYOBJ, (SELECTOR, aes.OB_ROOT, aes.OB_NIL, ROUTINE_AT, 0, 0, 8), _WALK,
             through_line_f=True)
