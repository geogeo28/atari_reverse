"""The object library's text and state helpers — `src/aes/objtext.c`: fs_sset $fecf84, inf_sset $fecfb2, fs_sget
$fecfd6, inf_fldset $fecfee, inf_gindex $fed010, inf_what $fed03a.

    fs_sset(tree, obj, text, &ptext, &txtlen)   *ptext = te_ptext; lstcpy(te_ptext, text); *txtlen = te_txtlen
    inf_sset(tree, obj, text)                   fs_sset into the Alcyon frame's own locals
    fs_sget(tree, obj, text)                    lstcpy(text, te_ptext)
    inf_fldset(tree, obj, fld, bits, t, f)      ob_state = (fld & bits) ? t : f
    inf_gindex(tree, first, count)              the index of the first SELECTED of `count` objects, -1 none (`dbf`)
    inf_what(tree, ok, cancel)                  inf_gindex(tree, ok, 2): -1; else that one's state cleared, 1 for OK

Hand 68000 but for inf_sset (Alcyon, returning `unlk; rts`), each reaching its field through OB_ADDR ($fed18e, the
C's `object_address`) and copying through lstcpy ($fecbe6). Seeded with the snapshot's FILE SELECTOR — the AES
resource's tree 0, whose editable path (2) and selection (3) and nine file rows (12-20) are TEDINFO objects and whose
OK (21) and Cancel (22) are the pair fs_input asks inf_what about. A case that changes a state word works on a COPY of
the tree in the staged band (its ob_specs still naming the real TEDINFOs), so nothing outside a claim is poked.
"""
import pytest

from harness import BASE_IMAGE

import aes
import case
import vdi
from case import merge_pokes

FS_SSET, INF_SSET, FS_SGET = "AES_ROM_FS_SSET", "AES_ROM_INF_SSET", "AES_ROM_FS_SGET"
INF_FLDSET, INF_GINDEX, INF_WHAT = "AES_ROM_INF_FLDSET", "AES_ROM_INF_GINDEX", "AES_ROM_INF_WHAT"
L, W, IMAGE = vdi.LONG_ARG, vdi.WORD_ARG, vdi.IMAGE_ARG
aes.declare_alcyon(FS_SSET, None, (IMAGE, L, W, L, L, L))
aes.declare_alcyon(INF_SSET, None, (IMAGE, L, W, L))
aes.declare_alcyon(FS_SGET, None, (IMAGE, L, W, L))
aes.declare_alcyon(INF_FLDSET, None, (IMAGE, L, W, W, W, W, W))
aes.declare_alcyon(INF_GINDEX, aes.WORD_ANSWER, (IMAGE, L, W, W))
aes.declare_alcyon(INF_WHAT, aes.WORD_ANSWER, (IMAGE, L, W, W))

SELECTOR = aes.resource_tree(0)
PATH, SELECTION, FIRST_ROW, ROWS, OK, CANCEL = 2, 3, 12, 9, 21, 22
SELECTED = 1 << aes.OB_STATE_SELECTED_BIT
# The selector COPIED into the staged tree band, byte for byte.
COPY = aes.TREE_AT
SELECTOR_COPY = {COPY: bytes(BASE_IMAGE[SELECTOR:SELECTOR + aes.tree_length(SELECTOR) * aes.OB_BYTES])}
# The strings: a name to set, and a buffer to get into (staged stale).
TEXT_AT = aes.BLOCKS_AT
BUFFER_AT = aes.BLOCKS_AT + 0x40
STAGED_TEDINFO = aes.BLOCKS_AT + 0x80
STAGED_TEXT = aes.BLOCKS_AT + 0xC0
NAME = b"DESKTOP INF\x00"
STALE_BUFFER = {BUFFER_AT: bytes([0xA5] * 0x40)}
# fs_sset's two answers, staged stale.
PTEXT_AT, TXTLEN_AT = aes.RECTS_AT, aes.RECTS_AT + aes.LONG_BYTES
STALE_ANSWERS = {PTEXT_AT: bytes([0xA5] * 6)}


def tedinfo(tree, index, image=BASE_IMAGE):
    return aes.read_field(image, "OB", "SPEC", tree + index * aes.OB_BYTES)


def text_of(image, at):
    return bytes(image[at:image.index(0, at) + 1])


def staged_selection(**states):
    """The selector's copy with object `index`'s state word set, for every `o<index>=state`."""
    return merge_pokes(SELECTOR_COPY, *(aes.object_pokes(COPY, int(key[1:]), STATE=value) for key, value in states.items()))


# ---- fs_sset / inf_sset / fs_sget ---------------------------------------------------------------------------------

def sset(tree, index, pokes=None, *, text=TEXT_AT, ptext=PTEXT_AT, txtlen=TXTLEN_AT, **kwargs):
    pokes = merge_pokes({TEXT_AT: NAME}, STALE_ANSWERS, pokes)
    return aes.run_function(FS_SSET, (tree, index, text, ptext, txtlen), aes.leaf_machine(onto=pokes), **kwargs)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("index", (SELECTION, PATH, FIRST_ROW))
def test_fs_sset_copies_the_text_in_and_answers_its_address_and_length(index, through_line_f):
    te = tedinfo(SELECTOR, index)
    result = sset(SELECTOR, index, through_line_f=through_line_f)
    ptext = case.long_in(BASE_IMAGE, te + aes.TE_PTEXT)
    assert text_of(result.final, ptext) == NAME
    assert result.long(PTEXT_AT) == ptext
    assert result.word(TXTLEN_AT) == case.word_in(BASE_IMAGE, te + aes.TE_TXTLEN)


def staged_tedinfo(ptext, txtlen=12, tag=0):
    """A tree of one object whose ob_spec (with top byte `tag`) names a staged TEDINFO."""
    return merge_pokes(aes.tree_pokes([aes.node(None, SPEC=STAGED_TEDINFO | tag)]),
                       aes.tedinfo_pokes(STAGED_TEDINFO, PTEXT=ptext, TXTLEN=txtlen))


def test_fs_sset_stores_the_text_s_address_before_it_reads_it_again():
    """The address answer laid two bytes into the TEDINFO: it rewrites te_ptext's LOW word with its high one (and
    te_ptmplt's high word), and the copy then goes where the REWRITTEN te_ptext points — $00070007 here."""
    result = sset(aes.TREE_AT, 0, staged_tedinfo(STAGED_TEXT), ptext=STAGED_TEDINFO + aes.WORD_BYTES)
    moved = (STAGED_TEXT >> 16) << 16 | STAGED_TEXT >> 16
    assert text_of(result.final, moved) == NAME
    assert text_of(result.final, STAGED_TEXT) != NAME


def test_fs_sset_reads_the_length_after_the_copy():
    """te_ptext one word below te_txtlen: the copy runs over the length word, and the length answered is what the
    copy left there ("SK")."""
    text = STAGED_TEDINFO + aes.TE_TXTLEN - aes.WORD_BYTES
    result = sset(aes.TREE_AT, 0, merge_pokes(staged_tedinfo(text), {TEXT_AT: b"DESK\x00"}))
    assert result.word(TXTLEN_AT) == int.from_bytes(b"SK", "big")


def test_fs_sset_puts_every_pointer_on_the_24_bit_bus():
    """Tree, text and both answers tagged, and the ob_spec and te_ptext themselves with top bytes: every one is
    addressed through 24 bits, and the address ANSWERED keeps te_ptext's top byte."""
    tagged_text = STAGED_TEXT | aes.BUS_TAG
    result = sset(aes.TREE_AT | aes.BUS_TAG, 0, staged_tedinfo(tagged_text, tag=aes.BUS_TAG),
                  text=TEXT_AT | aes.BUS_TAG, ptext=PTEXT_AT | aes.BUS_TAG, txtlen=TXTLEN_AT | aes.BUS_TAG)
    assert text_of(result.final, STAGED_TEXT) == NAME
    assert result.long(PTEXT_AT) == tagged_text
    assert result.word(TXTLEN_AT) == 12


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
def test_inf_sset_copies_the_text_in(through_line_f):
    """Its answers go into its own frame's locals — the stack band, which no diff compares — so the copy is all."""
    result = aes.run_function(INF_SSET, (SELECTOR, SELECTION, TEXT_AT), aes.leaf_machine(onto={TEXT_AT: NAME}),
                              through_line_f=through_line_f)
    assert text_of(result.final, case.long_in(BASE_IMAGE, tedinfo(SELECTOR, SELECTION))) == NAME


def test_inf_sset_puts_its_pointers_on_the_24_bit_bus():
    result = aes.run_function(INF_SSET, (aes.TREE_AT | aes.BUS_TAG, 0, TEXT_AT | aes.BUS_TAG),
                              aes.leaf_machine(onto=merge_pokes({TEXT_AT: NAME}, staged_tedinfo(STAGED_TEXT,
                                                                                                 tag=aes.BUS_TAG))))
    assert text_of(result.final, STAGED_TEXT) == NAME


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("index", (PATH, SELECTION, FIRST_ROW))
def test_fs_sget_copies_the_text_out(index, through_line_f):
    result = aes.run_function(FS_SGET, (SELECTOR, index, BUFFER_AT), aes.leaf_machine(onto=STALE_BUFFER),
                              through_line_f=through_line_f)
    assert text_of(result.final, BUFFER_AT) == text_of(BASE_IMAGE, case.long_in(BASE_IMAGE, tedinfo(SELECTOR, index)))


def test_fs_sget_puts_its_pointers_on_the_24_bit_bus():
    pokes = merge_pokes(STALE_BUFFER, {STAGED_TEXT: NAME}, staged_tedinfo(STAGED_TEXT | aes.BUS_TAG, tag=aes.BUS_TAG))
    result = aes.run_function(FS_SGET, (aes.TREE_AT | aes.BUS_TAG, 0, BUFFER_AT | aes.BUS_TAG), aes.leaf_machine(onto=pokes))
    assert text_of(result.final, BUFFER_AT) == NAME


# ---- inf_fldset ---------------------------------------------------------------------------------------------------
FLDSETS = {"set": (0x0104, 0x0004), "clear": (0x0104, 0x0010), "the high byte's bit": (0x8000, 0x8000)}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("shape", sorted(FLDSETS))
def test_inf_fldset(shape, through_line_f):
    field, bits = FLDSETS[shape]
    result = aes.run_function(INF_FLDSET, (COPY, OK, field, bits, 0x0001, 0x8008),
                              aes.leaf_machine(onto=staged_selection(o21=0x5A5A)), through_line_f=through_line_f)
    assert result.object(COPY, OK)["STATE"] == (0x0001 if field & bits else 0x8008)


def test_inf_fldset_puts_its_tree_on_the_24_bit_bus():
    result = aes.run_function(INF_FLDSET, (COPY | aes.BUS_TAG, CANCEL, 1, 1, 0x0001, 0),
                              aes.leaf_machine(onto=SELECTOR_COPY))
    assert result.object(COPY, CANCEL)["STATE"] == 0x0001


# ---- inf_gindex / inf_what ----------------------------------------------------------------------------------------

def gindex(first, count, pokes, tree=COPY, **kwargs):
    return aes.run_function(INF_GINDEX, (tree, first, count), aes.leaf_machine(onto=pokes), **kwargs)


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("selected", (None, FIRST_ROW, FIRST_ROW + 4, FIRST_ROW + ROWS - 1))
def test_inf_gindex_over_the_selector_s_nine_rows(selected, through_line_f):
    """None selected (the walk crosses all nine and answers -1), the first, one in the middle, the last."""
    pokes = SELECTOR_COPY if selected is None else staged_selection(**{f"o{selected}": SELECTED})
    result = gindex(FIRST_ROW, ROWS, pokes, through_line_f=through_line_f)
    assert result.answer() == (aes.OB_NIL if selected is None else selected - FIRST_ROW)


def test_inf_gindex_reads_only_the_state_s_low_byte_bit_0():
    """A state of $0100 (bit 0 of the HIGH byte) or $0002 is not SELECTED; $ff01 is."""
    pokes = staged_selection(o12=0x0100, o13=0x0002, o14=0xFF01)
    assert gindex(FIRST_ROW, ROWS, pokes).answer() == 2


def test_inf_gindex_of_one_object():
    assert gindex(OK, 1, staged_selection(o22=SELECTED)).answer() == aes.OB_NIL


def test_inf_gindex_counts_zero_as_65536():
    """A `dbf` counter: a count of 0 does not stop at the first object — the second, selected, is found."""
    assert gindex(FIRST_ROW, 0, staged_selection(o13=SELECTED)).answer() == 1


def test_inf_gindex_s_index_is_signed():
    """A first object of -1 is the 24 bytes BELOW the tree: its state word staged SELECTED there."""
    tree = COPY + aes.OB_BYTES
    pokes = merge_pokes(SELECTOR_COPY, aes.object_pokes(COPY, 0, STATE=SELECTED))
    assert gindex(aes.OB_NIL, 2, pokes, tree=tree).answer() == 0


def test_inf_gindex_puts_its_tree_on_the_24_bit_bus():
    assert gindex(FIRST_ROW, ROWS, staged_selection(o15=SELECTED), tree=COPY | aes.BUS_TAG).answer() == 3


WHATS = {"neither": {}, "OK": {"o21": SELECTED}, "Cancel": {"o22": SELECTED | 0x0100},
         "both": {"o21": SELECTED | 0x0020, "o22": SELECTED}}


@pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
@pytest.mark.parametrize("shape", sorted(WHATS))
def test_inf_what_over_the_selector_s_ok_and_cancel(shape, through_line_f):
    states = WHATS[shape]
    result = aes.run_function(INF_WHAT, (COPY, OK, CANCEL), aes.leaf_machine(onto=staged_selection(**states)),
                              through_line_f=through_line_f)
    first = next((index for index in (OK, CANCEL) if f"o{index}" in states), None)
    assert result.answer() == (aes.OB_NIL if first is None else int(first == OK))
    for index in (OK, CANCEL):
        staged = states.get(f"o{index}", aes.read_field(BASE_IMAGE, "OB", "STATE", SELECTOR + index * aes.OB_BYTES))
        assert result.object(COPY, index)["STATE"] == (0 if index == first else staged)


@pytest.mark.parametrize("cancel", (0, OK), ids=("zero", "ok itself"))
def test_inf_what_never_reads_cancel(cancel):
    """The pair is `ok` and `ok + 1` whatever `cancel` says: a cancel of 0, or of `ok` itself, changes nothing —
    the one after OK, selected, is still found."""
    result = aes.run_function(INF_WHAT, (COPY, OK, cancel), aes.leaf_machine(onto=staged_selection(o22=SELECTED)))
    assert result.answer() == 0 and result.object(COPY, CANCEL)["STATE"] == 0


def test_inf_what_puts_its_tree_on_the_24_bit_bus():
    result = aes.run_function(INF_WHAT, (COPY | aes.BUS_TAG, OK, CANCEL), aes.leaf_machine(onto=staged_selection(o21=SELECTED)))
    assert result.answer() == 1 and result.object(COPY, OK)["STATE"] == 0


# ---- the registry: the dearest realistic rows priced, one of each routine through Line-F. ---------------------------
_SSET = merge_pokes({TEXT_AT: NAME}, STALE_ANSWERS)
aes.register("the selector's path", FS_SSET, (SELECTOR, PATH, TEXT_AT, PTEXT_AT, TXTLEN_AT), aes.leaf_machine(onto=_SSET))
aes.register("the selector's path", FS_SSET, (SELECTOR, PATH, TEXT_AT, PTEXT_AT, TXTLEN_AT), aes.leaf_machine(onto=_SSET),
             through_line_f=True)
aes.register("the selector's selection", INF_SSET, (SELECTOR, SELECTION, TEXT_AT), aes.leaf_machine(onto={TEXT_AT: NAME}))
aes.register("the selector's selection", INF_SSET, (SELECTOR, SELECTION, TEXT_AT), aes.leaf_machine(onto={TEXT_AT: NAME}),
             through_line_f=True)
aes.register("the selector's path", FS_SGET, (SELECTOR, PATH, BUFFER_AT), aes.leaf_machine(onto=STALE_BUFFER))
aes.register("the selector's path", FS_SGET, (SELECTOR, PATH, BUFFER_AT), aes.leaf_machine(onto=STALE_BUFFER),
             through_line_f=True)
aes.register("set", INF_FLDSET, (COPY, OK, 0x0104, 0x0004, 1, 0), aes.leaf_machine(onto=SELECTOR_COPY))
aes.register("clear", INF_FLDSET, (COPY, OK, 0x0104, 0x0010, 1, 0), aes.leaf_machine(onto=SELECTOR_COPY))
aes.register("set", INF_FLDSET, (COPY, OK, 0x0104, 0x0004, 1, 0), aes.leaf_machine(onto=SELECTOR_COPY), through_line_f=True)
aes.register("none of nine rows", INF_GINDEX, (COPY, FIRST_ROW, ROWS), aes.leaf_machine(onto=SELECTOR_COPY))
aes.register("the first row", INF_GINDEX, (COPY, FIRST_ROW, ROWS), aes.leaf_machine(onto=staged_selection(o12=SELECTED)))
aes.register("none of nine rows", INF_GINDEX, (COPY, FIRST_ROW, ROWS), aes.leaf_machine(onto=SELECTOR_COPY),
             through_line_f=True)
for _shape in sorted(WHATS):
    aes.register(_shape, INF_WHAT, (COPY, OK, CANCEL), aes.leaf_machine(onto=staged_selection(**WHATS[_shape])))
aes.register("Cancel", INF_WHAT, (COPY, OK, CANCEL), aes.leaf_machine(onto=staged_selection(**WHATS["Cancel"])),
             through_line_f=True)
