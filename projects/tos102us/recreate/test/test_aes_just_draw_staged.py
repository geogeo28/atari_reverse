"""AES just_draw ($fe9a88) — the cells NO snapshot tree reaches, STAGED on real objects (`test/aes_objdraw.py`): a type,
a state bit, a size, a string or a block set on an object of the AES's or the desk's own trees, each case naming what it
staged. Mostly app-only data, honestly so: FTEXT and USERDEF objects, the SHADOWED and CROSSED states, an IBOX's border,
a raw text that is not empty, a text in the small font, HIDETREE and a spec of -1 — none of the snapshot's trees carries
them, and no AES writer of the last three was found. One cell has a ROM writer instead: the desktop band's TEXT, whose
te_ptext sh_draw stores (drawn as sh_draw leaves it). Then the arithmetic the 68000 does in words and packed longwords,
and the ORDER of the reads that follow a callee's stores.
"""
import struct

import pytest

from harness import BASE_IMAGE

import aes
import case
import aes_obuser as obuser
import aes_objdraw as od
import vdi
from aes_objdraw import real
from test_aes_oblib_walk import INDIRECT
from case import merge_pokes
from test_aes_gsx import screen_changed

STATE = od.STATE_BITS


ROOT = real("selector", 0)                  # an OUTLINED box, border 2
BOX = real("selector", 6)                   # a box, border 1
DROP_DOWN = od.DROP_DOWN                    # a box, border -1
BUTTON = od.EXIT_BUTTON                     # a default exit button, border -3
STRING = real("selector", 1)
TITLE = real("menu", 3)
IBOX = real("desk tree 1", 7)
PATH_FIELD = real("selector", 2)            # an FBOXTEXT, left
RIGHT_FIELD = real("desk tree 1", 3)        # an FBOXTEXT, right
BOXTEXT = real("selector", 5)
BOXCHAR = real("selector", 4)
ICON = od.TRASH
TITLE_SPARE = 16                            # an application's title this much wider than its string


def drawn(tree_index, pokes=None, **kwargs):
    tree, index = tree_index
    return od.draw(tree, index, pokes, **kwargs)


def staged_state(tree_index, state):
    return od.state_pokes(*tree_index, state)


def hidden_flags(tree_index):
    """The object's own ob_flags with HIDETREE set."""
    return od.object_word(BASE_IMAGE, *tree_index, "FLAGS") | 1 << aes.OB_FLAG_HIDETREE_BIT


def spec_block_moved(tree_index, size, to, patch=None):
    """The object's ob_spec pointed at `to`, and its block (`size` bytes, the snapshot's) copied there — `patch`,
    `(offset, bytes)`, laid over the copy."""
    tree, index = tree_index
    spec = od.object_long(tree, index, "SPEC")
    block = bytearray(BASE_IMAGE[spec:spec + size])
    if patch is not None:
        offset, data = patch
        block[offset:offset + len(data)] = data
    return merge_pokes(od.spec_pokes(tree, index, to), {to: bytes(block)})


# ---- nothing drawn ------------------------------------------------------------------------------------------------------
def test_a_hidden_object_draws_nothing():
    """HIDETREE in ob_flags: ob_sst's stores and nothing else — not even the clip test."""
    tree, index = ROOT
    result = drawn(ROOT, od.flags_pokes(tree, index, hidden_flags(ROOT)))
    assert not screen_changed(result)


@pytest.mark.parametrize("indirect", (False, True), ids=("its own", "named INDIRECT"))
def test_a_spec_of_minus_one_draws_nothing(indirect):
    tree, index = BUTTON
    if indirect:
        pokes = merge_pokes(od.spec_pokes(tree, index, od.TEXT_AT), {od.TEXT_AT: struct.pack(">i", -1)},
                            od.flags_pokes(tree, index, od.object_word(BASE_IMAGE, tree, index, "FLAGS") | INDIRECT))
    else:
        pokes = od.spec_pokes(tree, index, -1)
    assert not screen_changed(drawn(BUTTON, pokes))


# ---- types no tree has ---------------------------------------------------------------------------------------------------
def test_an_ibox_with_a_border_draws_it_unfilled():
    """An IBOX's spec with a border byte (1): the border drawn in its colour, no fill."""
    tree, index = IBOX
    spec = od.box_spec(tree, index, thickness=1, colour=od.colour_word(border=1, text=1))
    assert screen_changed(drawn(IBOX, od.spec_pokes(tree, index, spec)))


@pytest.mark.parametrize("raw", (b"@", b"FILE", b"1234567"), ids=("empty", "short", "nearly full"))
@pytest.mark.parametrize("field", (PATH_FIELD, RIGHT_FIELD), ids=("left", "right"))
@pytest.mark.parametrize("kind", ("G_FBOXTEXT", "G_FTEXT"), ids=("boxed", "unboxed"))
def test_an_editable_text(field, raw, kind):
    """An FBOXTEXT (real) or an FTEXT (its type staged) whose raw text the desk seeded: copied out, merged with its
    template by ob_format into AES_FMTSTR — which becomes the TEDINFO's text — and drawn."""
    tree, index = field
    result = drawn(field, merge_pokes(od.seeded_text(tree, index, raw), od.type_pokes(tree, index, kind)))
    assert screen_changed(result)
    assert result.long(aes.AES_EDBLK + aes.TE_PTEXT) == aes.AES_FMTSTR


def test_an_editable_text_centred():
    """TE_CENTER on an editable text (no tree has one): ob_format's left-to-right merge, gr_gtext centring it."""
    tree, index = PATH_FIELD
    pokes = merge_pokes(od.seeded_text(tree, index, b"CENTRE"), od.tedinfo_pokes(tree, index, JUST=od.GRAF["GSX_JUST_CENTRE"]))
    assert screen_changed(drawn(PATH_FIELD, pokes))


FONT_SMALL = od.GRAF["GSX_FONT_SMALL"]


@pytest.mark.parametrize("font", (FONT_SMALL, 1), ids=("small", "neither"))
def test_a_text_in_another_font(font):
    """The BOXTEXT's TEDINFO in the small font (te_font 5, no tree uses it) — gsx_tblt sets it, poison off — and in a
    font neither of the AES's: gr_just measures nothing, nothing written."""
    tree, index = BOXTEXT
    result = drawn(BOXTEXT, od.tedinfo_pokes(tree, index, FONT=font), **(od.PTSIN_READ_FIRST if font == FONT_SMALL else {}))
    assert screen_changed(result)


def test_the_desktop_band_s_text_is_sh_draw_s():
    """The AES's tree 2's TEXT has a writer: ad_pfile names its TEDINFO, whose te_ptext sh_draw ($feada0) stores."""
    tree, index = real("desktop band", od.BAND_TEXT)
    assert case.long_in(BASE_IMAGE, aes.AES_AD_PFILE) == od.object_long(tree, index, "SPEC")


def test_the_desktop_band_s_text_as_sh_draw_leaves_it():
    """...drawn as sh_draw's one-object pass draws it ($feaddc: object 2, depth 0): te_ptext the shell's buffer, a
    command in it, the clip the whole screen — two commands, two screens (`aes_objdraw.band_screens`)."""
    band_text = real("desktop band", od.BAND_TEXT)
    screens = od.band_screens(lambda pokes, **kwargs: drawn(band_text, pokes, onto=od.sh_draw_machine(), **kwargs))
    assert screens[0] != screens[1]


@pytest.mark.parametrize("character", (0x41, 0), ids=("a letter", "none"))
def test_a_boxchar_s_character(character):
    """The BOXCHAR's character is the spec's first byte, through ob_sst's D0 into the byte at AES_FMTSTR: none, an
    empty string, draws nothing in its box."""
    tree, index = BOXCHAR
    spec = od.box_spec(tree, index, character=character)
    result = drawn(BOXCHAR, od.spec_pokes(tree, index, spec))
    assert result.after(aes.AES_FMTSTR, 2) == bytes((character, 0))


@pytest.mark.parametrize("kind", (19, 33, 0x7F), ids=("below G_BOX", "above G_TITLE", "far above"))
def test_a_type_outside_the_tables(kind):
    """A type below G_BOX or above G_TITLE falls through both tables: the text colour set, its state drawn."""
    tree, index = BOX
    pokes = merge_pokes(od.type_pokes(tree, index, kind), staged_state(BOX, STATE["SELECTED"]))
    assert screen_changed(drawn(BOX, pokes))


def test_an_extended_type_s_high_byte_is_ignored():
    """ob_sst keeps the type's LOW byte: a high byte of $12 (an application's extended type) draws as the box."""
    tree, index = BOX
    pokes = aes.object_pokes(tree, index, TYPE=0x1200 | aes.G_BOX)
    assert screen_changed(drawn(BOX, pokes))


# ---- USERDEF -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("answer", (0, STATE["SELECTED"], STATE["CROSSED"] | STATE["OUTLINED"], 0x12340000),
                         ids=("0: nothing more", "SELECTED: inverted", "CROSSED and OUTLINED", "a high word only"))
def test_a_userdef_s_answer_is_the_state_drawn(answer):
    """The routine (`aes_obuser`'s) handed the PARMBLK — the object's state as both its states, its GRECT, the clip and
    ub_parm — and its answer's LOW word drawn as the object's state."""
    tree, index = BUTTON
    pokes = merge_pokes(od.userdef_pokes(tree, index, answer), staged_state(BUTTON, STATE["CHECKED"]))
    result = drawn(BUTTON, pokes, userdef=answer)
    logged = obuser.logged_parmblk(result.final)
    x, y = od.screen_origin(BASE_IMAGE, tree, index)
    assert (logged["tree"], logged["object"], logged["parm"]) == (tree, index, od.USERDEF_PARM)
    assert logged["prevstate"] == logged["currstate"] == STATE["CHECKED"]
    assert logged["rect"] == (x, y, *(od.object_word(BASE_IMAGE, tree, index, name) for name in ("WIDTH", "HEIGHT")))


# ---- states no tree has ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("tree_index", (BOX, DROP_DOWN, ROOT, BUTTON, IBOX), ids=("border 1", "border -1",
                                                                                     "border 2, outlined",
                                                                                     "a button: border -3",
                                                                                     "border 0: no shadow"))
def test_a_shadowed_object(tree_index):
    """SHADOWED: the shadow drawn in the border's colour, `2 x |border|` deep, below and right — none with no border."""
    tree, index = tree_index
    state = od.object_word(BASE_IMAGE, tree, index, "STATE") | STATE["SHADOWED"]
    result = drawn(tree_index, staged_state(tree_index, state))
    assert screen_changed(result) == (tree_index != IBOX)


# Colours the frame's STALE word does not draw like (black does: a pin staged black stays green with its ROM word moved).
@pytest.mark.parametrize("colour", (2, 0), ids=("colour 2", "white"))
def test_a_shadowed_title_reads_its_border_colour_unset(colour):
    """A TITLE's border is 1 (ob_sst) but nothing sets its border COLOUR — no crack, no BUTTON — so a SHADOWED title's
    shadow takes the colour of whatever word the frame holds there: the ROM's frame word below its saved A6 (its run
    entered direct), the C's its own frame's last word (`aes_objdraw.ROM_BORDER_AT` / `HOST_BORDER_AT`).
    Both staged to one colour, the draw is the same; left alone, they are whatever the stack held."""
    tree, index = TITLE
    pokes = merge_pokes(staged_state(TITLE, STATE["SHADOWED"]), {od.ROM_BORDER_AT: vdi.pack_words(colour),
                                                                  od.HOST_BORDER_AT: vdi.pack_words(colour)})
    result = drawn(TITLE, pokes, at=(16, 40), **od.PTSIN_READ_FIRST)
    assert screen_changed(result)


@pytest.mark.parametrize("tree_index", (BOX, BUTTON, STRING), ids=("a box", "a button", "a string"))
@pytest.mark.parametrize("state", ("CROSSED", "CHECKED", "DISABLED"))
def test_a_mark_on_another_type(tree_index, state):
    """CROSSED (no tree has it), and CHECKED and DISABLED on types other than the menu's strings."""
    label_first = tree_index == STRING and state != "CHECKED"     # a mark after the label that points PTSIN back
    result = drawn(tree_index, staged_state(tree_index, STATE[state]), **(od.PTSIN_READ_FIRST if label_first else {}))
    assert screen_changed(result)


@pytest.mark.parametrize("state", ("", "SHADOWED"), ids=("its border", "its shadow"))
def test_a_box_whose_border_colour_is_not_its_text_colour(state):
    """An application's colour word: border 2, text 1 (every tree's own has the two alike) — the border, and a SHADOWED
    box's shadow, drawn in the border's colour as gr_crack split it."""
    tree, index = BOX
    spec = od.box_spec(tree, index, colour=od.colour_word(border=2, text=1))
    pokes = merge_pokes(od.spec_pokes(tree, index, spec), staged_state(BOX, STATE[state]) if state else None)
    assert screen_changed(drawn(BOX, pokes))


def test_a_title_wider_than_its_label():
    """An application's TITLE wider than its string (the menu's are exactly as wide): its label is centred DOWN only,
    left at the title's x — only a BUTTON's is centred across — so, redrawn in its place, it is the bar's own."""
    tree, index = TITLE
    pokes = od.size_pokes(tree, index, od.object_word(BASE_IMAGE, tree, index, "WIDTH") + TITLE_SPARE,
                          od.object_word(BASE_IMAGE, tree, index, "HEIGHT"))
    assert od.redrawn_as_it_stands(drawn(TITLE, pokes, onto=od.screen_clip_machine()))


def test_a_check_mark_with_ad_intin_elsewhere():
    """CHECKED's mark is stored in intin[0] itself ($fe9f7e move.w #8,$95ba), not through ad_intin — staged away from
    intin here (the snapshot's ad_intin IS intin)."""
    tree, index = od.MENU_ITEM
    pokes = aes.field_pokes("AES", AD_INTIN=od.TEMPLATE_AT)
    assert screen_changed(od.draw(tree, index, pokes))


def test_every_mark_at_once():
    """All six state bits on a box with a border: each mark in the ROM's order over the GRECT the border shrank."""
    result = drawn(BOX, staged_state(BOX, sum(STATE.values())))
    assert screen_changed(result)


def test_a_state_with_only_its_high_byte_set():
    """The state test is the whole WORD (`tst.w`): a high byte alone enters the marks, which find no bit."""
    result = drawn(BOX, staged_state(BOX, 0x0100))
    assert screen_changed(result)


# ---- the packed longwords: a carry or a borrow out of the low word ----------------------------------------------------
@pytest.mark.parametrize("y", (0, 1, 2, 3), ids=("y 0", "y 1", "y 2", "y 3: no borrow"))
def test_an_outline_near_the_top_borrows_from_x(y):
    """OUTLINED's corner is (x, y) - $30003 as ONE longword: at y < 3 the borrow moves the outline a pixel left (and the
    inner one at y < 2). Drawn under the whole screen's clip, as the menu bar is: the outline shows."""
    tree, index = real("desk tree 5", 0)
    assert screen_changed(drawn((tree, index), at=(8, y), onto=od.screen_clip_machine()))


def test_an_outline_of_a_negative_height_carries_into_its_width():
    """...and its size (w, h) + $60006: a height of -2 carries into the width."""
    tree, index = real("desk tree 5", 0)
    pokes = od.size_pokes(tree, index, od.object_word(BASE_IMAGE, tree, index, "WIDTH"), -2)
    drawn((tree, index), pokes, at=(8, 40))


@pytest.mark.parametrize("at, height", (((40, 0), 0), ((40, -5), 20), ((40, 40), 20)),
                         ids=("a height of 0 at y 0 borrows", "y negative: y + h - 1 carries", "neither"))
def test_a_cross_s_far_corner_is_packed(at, height):
    """CROSSED's far corner is (x, y) + ((w, h) - $10001), longwords: a height of 0 borrows from the width — a borrow
    that stays only at y 0, any other y's add carrying it back — and a y + h - 1 past $ffff carries into x. On the
    drop-down box, whose outward border leaves the GRECT as staged."""
    tree, index = DROP_DOWN
    pokes = merge_pokes(staged_state(DROP_DOWN, STATE["CROSSED"]), od.size_pokes(tree, index, 40, height))
    assert screen_changed(drawn(DROP_DOWN, pokes, at=at, onto=od.screen_clip_machine()))


@pytest.mark.parametrize("y", (-2, -40), ids=("y -2: the icon's y carries", "y -40: no carry"))
def test_an_icon_s_grects_move_as_packed_longwords(y):
    """The ICONBLK copy's two GRECTs moved by `add.l` of the object's corner: a y that carries out of the low word
    moves x one more. The icon drawn under the whole screen's clip."""
    tree, index = ICON
    x = od.ICON_PLACE[0]
    result = drawn(ICON, at=(x, y), onto=od.screen_clip_machine(font=od.SNAPSHOT_FONT))
    staged = case.long_in(BASE_IMAGE, od.object_long(tree, index, "SPEC") + aes.IB_XICON)
    assert result.long(aes.AES_IB + aes.IB_XICON) == (staged + struct.unpack(">I", struct.pack(">hh", x, y))[0]) & 0xFFFFFFFF


def test_an_icon_whose_image_sits_below_its_top_carries():
    """An application's ICONBLK (the trash's, its image moved 4 down — staged): at y -2 its ib_yicon's sum carries into
    ib_xicon. The desk's own icons have ib_yicon 0, which no y carries."""
    tree, index = ICON
    pokes = spec_block_moved(ICON, aes.IB_BYTES, aes.BLOCKS_AT, patch=(aes.IB_YICON, vdi.pack_words(4)))
    x = od.ICON_PLACE[0]
    result = drawn(ICON, pokes, at=(x, -2), onto=od.screen_clip_machine(font=od.SNAPSHOT_FONT))
    xicon = case.word_in(BASE_IMAGE, od.object_long(tree, index, "SPEC") + aes.IB_XICON)
    assert result.words(aes.AES_IB + aes.IB_XICON, 2) == [xicon + x + 1, 2]


def test_a_check_mark_s_indent():
    """CHECKED's mark at (x + 2, y): `addi.l #$20000`, nothing carried."""
    drawn(STRING, staged_state(STRING, STATE["CHECKED"]), at=(-1, 40))


# ---- the contents' own geometry ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("field", (PATH_FIELD, RIGHT_FIELD), ids=("left", "right"))
def test_a_text_inside_its_border(field):
    """An editable text with a border of 2 (its TEDINFO's te_thickness, staged) and SELECTED: the text drawn in the
    GRECT shrunk by the border, the GRECT grown back for the border's own shrink before the inversion."""
    tree, index = field
    pokes = merge_pokes(od.seeded_text(tree, index, b"1234"), od.tedinfo_pokes(tree, index, THICKNESS=2),
                        staged_state(field, STATE["SELECTED"]))
    assert screen_changed(drawn(field, pokes))


def test_an_image_s_own_corner_and_colour():
    """An application's BITBLK (the desk's logo's, staged): blitted from (8, 4) inside its form, in colour 2."""
    logo = real("desk tree 4", 1)
    pokes = spec_block_moved(logo, aes.BI_BYTES, aes.BLOCKS_AT, patch=(aes.BI_X, vdi.pack_words(8, 4, 2)))
    assert screen_changed(drawn(logo, pokes))


# ---- words: the label's centring --------------------------------------------------------------------------------------
@pytest.mark.parametrize("label", (b"A LABEL FAR WIDER THAN ITS BUTTON", b"OK!", b""),
                         ids=("too wide: a negative spare halved toward 0", "an odd spare", "empty: nothing drawn"))
def test_a_button_s_label_is_centred_in_words(label):
    tree, index = BUTTON
    pokes = merge_pokes(od.spec_pokes(tree, index, od.TEXT_AT), od.string_pokes(label))
    result = drawn(BUTTON, pokes)
    assert screen_changed(result)


@pytest.mark.parametrize("height", (7, 9, -1), ids=("shorter than a cell: -1 halved to 0", "odd", "negative"))
def test_a_label_is_centred_down_in_words(height):
    tree, index = STRING
    pokes = od.size_pokes(tree, index, od.object_word(BASE_IMAGE, tree, index, "WIDTH"), height)
    assert screen_changed(drawn(STRING, pokes))


def test_a_label_is_centred_down_by_the_cell_s_height():
    """The centring reads gl_hchar, the cell's HEIGHT — 8 here, as its width is: staged at 16, a high resolution's,
    the label moves up by 4 (the VDI's font stays the 8 x 8 one)."""
    result = drawn(STRING, aes.field_pokes("AES", GL_HCHAR=16))
    assert screen_changed(result)


def test_an_empty_string_skips_its_label():
    """No characters (xstrpix answers 0): no writing mode, no text."""
    tree, index = STRING
    pokes = merge_pokes(od.spec_pokes(tree, index, od.TEXT_AT), od.string_pokes(b""), aes.field_pokes("AES", GL_MODE=0))
    result = drawn(STRING, pokes)
    assert not screen_changed(result) and result.field("AES", "GL_MODE") == 0


# ---- the ORDER: reads after a callee's stores ---------------------------------------------------------------------------
def test_a_raw_text_too_long_runs_into_the_template():
    """An editable text whose raw text is longer than its buffer (81 bytes): the first lstcpy runs past AES_RAWSTR into
    AES_TMPLT, and the second — the template — is copied over it AFTER; ob_format then merges what the two left."""
    tree, index = PATH_FIELD
    raw = bytes(range(0x41, 0x5B)) * 4
    pokes = merge_pokes(od.tedinfo_pokes(tree, index, PTEXT=aes.BLOCKS_AT), {aes.BLOCKS_AT: raw + b"\0"})
    result = drawn(PATH_FIELD, pokes)
    assert screen_changed(result)


def test_a_template_that_is_the_raw_buffer():
    """te_ptmplt naming AES_RAWSTR itself: the template copy reads the raw text the first copy just stored."""
    tree, index = PATH_FIELD
    pokes = merge_pokes(od.seeded_text(tree, index, b"RAW___"), od.tedinfo_pokes(tree, index, PTMPLT=aes.AES_RAWSTR))
    assert screen_changed(drawn(PATH_FIELD, pokes))


def test_a_text_whose_string_is_the_merge_buffer():
    """A TEXT whose te_ptext is AES_FMTSTR (an earlier editable text's merge left there): gr_gtext reads it."""
    tree, index = BOXTEXT
    pokes = merge_pokes(od.tedinfo_pokes(tree, index, PTEXT=aes.AES_FMTSTR), {aes.AES_FMTSTR: b"LEFT OVER\0"})
    assert screen_changed(drawn(BOXTEXT, pokes))


def test_a_label_laid_over_intin():
    """A STRING whose text IS the AES's intin: xstrpix widens it in place, a byte read after each word stored."""
    tree, index = STRING
    pokes = merge_pokes(od.spec_pokes(tree, index, aes.AES_GSX_INTIN), {aes.AES_GSX_INTIN: b"OVERLAP\0"})
    assert screen_changed(drawn(STRING, pokes))


def test_a_tedinfo_laid_over_its_copy():
    """A text object's TEDINFO at AES_EDBLK + 2: lbcopy moves it down over itself (memmove), and the colour, font and
    text are read from the copy after."""
    pokes = spec_block_moved(BOXTEXT, aes.TE_BYTES, aes.AES_EDBLK + 2)
    assert screen_changed(drawn(BOXTEXT, pokes))


def test_a_bitblk_laid_over_its_copy():
    """An image whose BITBLK sits at AES_BI + 2: lbcopy moves it down over itself, and the blit's fields are read from
    the copy after."""
    logo = real("desk tree 4", 1)
    pokes = spec_block_moved(logo, aes.BI_BYTES, aes.AES_BI + 2)
    assert screen_changed(drawn(logo, pokes))


def test_a_label_s_intin_laid_over_the_cell_height():
    """ad_intin (the address xstrpix widens the label into) staged at gl_hchar: the label's first character lands on
    the cell height the centring reads AFTER it."""
    pokes = aes.field_pokes("AES", AD_INTIN=aes.AES_GL_HCHAR)
    drawn(STRING, pokes)


def test_an_iconblk_laid_over_its_copy():
    """An icon whose ICONBLK IS AES_IB: the copy a no-op, the GRECTs moved in place — the block itself changed."""
    pokes = spec_block_moved(ICON, aes.IB_BYTES, aes.AES_IB)
    assert screen_changed(drawn(ICON, pokes, at=od.ICON_PLACE, onto=od.snapshot_font_machine()))


# ---- the registry --------------------------------------------------------------------------------------------------------
_PATH_TREE, _PATH_INDEX = PATH_FIELD
od.register("an FTEXT, seeded", *PATH_FIELD, merge_pokes(od.seeded_text(_PATH_TREE, _PATH_INDEX, b"A_LONGER_ONE"),
                                                         od.type_pokes(_PATH_TREE, _PATH_INDEX, "G_FTEXT")))
od.register("a USERDEF answering SELECTED", *BUTTON, od.userdef_pokes(*BUTTON, STATE["SELECTED"]),
            userdef=STATE["SELECTED"])
od.register("a hidden object", *BOX, od.flags_pokes(*BOX, hidden_flags(BOX)))
od.register("a shadowed box", *BOX, staged_state(BOX, STATE["SHADOWED"]))
od.register("a crossed box", *BOX, staged_state(BOX, STATE["CROSSED"]))
