"""AES gemgraf's gr_ layer — the GRECT, colour-word, text-in-a-box, icon and thick-box routines the object draw path
calls — `src/aes/gemgraf.c`, through `test/aes_gsx.py`'s door and `test_aes_gemgraf.py`'s band and signatures.

    gr_inside   x += t; y += t; w -= 2t; h -= 2t                        (words, read and stored back one at a time)
    gr_rect     vsf_color(colour); bb_fill(REPLACE, hollow 0 / solid 7 / pattern, pattern, the GRECT read after)
    gr_just     gsx_tcalc(font, text, &r->w, &r->h, &count — its saved D0's low word); r->y += half the height to
                spare; r->x += half the width to spare (centred) or all of it (right); D0 = the count
    gr_gtext    a copy of the GRECT (over its saved D0/D1); gr_just; gsx_tblt of the count when it is > 0
    gr_crack    the colour word out: border, text, pattern (bit 7 of the word: replace, the pattern's low 3 bits),
                mode, interior — in that order
    gr_gicon    the colours swapped when SELECTED; the mask (unless WHITEBAK over white) and a solid gr_rect of the
                text's box in the background; the data in the foreground; the character; the text centred
    gr_box      gsx_moff; per line gr_inside of a copy, gsx_box; gsx_mon — thickness - 1 down to 0, or out from it

Every case runs in the door's machine (the cursor hidden by the ROM's own gsx_moff) unless it says the snapshot's,
and the WHOLE image is compared, the screen included; every routine is also entered through its Line-F word once.
"""
import pytest

import aes
import aes_gsx as gsx
import test_aes_gemgraf as graf
import vdi
from case import merge_pokes
from test_aes_gemgraf import (ANSWERS_AT, DATA_AT, FONT_IBM, FONT_SMALL, GRAF, INTIN, MASK_AT, PTSIN, STALE, TEXT_AT,
                              THROUGH, answer_at, rect_at, rect_pokes, text_pokes)
from test_aes_gsx import PTSIN_READ_BEFORE_IT_IS_PUT_BACK, screen_changed

LEFT, RIGHT, CENTRE = 0, GRAF["GSX_JUST_RIGHT"], GRAF["GSX_JUST_CENTRE"]
TEXT = b"Trash"


def rect_of(result, slot=0):
    return [aes.signed(word) for word in result.words(rect_at(slot), 4)]


# ---- gr_inside ------------------------------------------------------------------------------------------------------------
# (rect, thickness): in, out, none, and the word sums' wrap (2t by `asl.w`).
INSIDE = {
    "in by 1": ((40, 30, 100, 50), 1),
    "in by 3": ((40, 30, 100, 50), 3),
    "out by 2": ((40, 30, 100, 50), -2),
    "none": ((40, 30, 100, 50), 0),
    "twice the thickness wraps": ((0, 0, 0, 0), 0x4000),
    "x wraps": ((0x7FFF, -0x8000, 10, 10), 1),
}


@pytest.mark.parametrize("rect, thickness", INSIDE.values(), ids=INSIDE)
def test_gr_inside(rect, thickness):
    result = gsx.run_gsx("AES_ROM_GR_INSIDE", (rect_at(0), thickness), rect_pokes(*rect))
    x, y, w, h = rect
    assert rect_of(result) == [aes.signed(x + thickness), aes.signed(y + thickness), aes.signed(w - 2 * thickness),
                               aes.signed(h - 2 * thickness)]


@THROUGH
def test_gr_inside_through_its_callers_word(through_line_f):
    result = gsx.run_gsx("AES_ROM_GR_INSIDE", (rect_at(0), 2), rect_pokes(40, 30, 100, 50), through_line_f=through_line_f)
    assert rect_of(result) == [42, 32, 96, 46]


def test_gr_inside_s_pointer_is_put_on_the_bus():
    result = gsx.run_gsx("AES_ROM_GR_INSIDE", (rect_at(0) | aes.BUS_TAG, 2), rect_pokes(40, 30, 100, 50))
    assert rect_of(result) == [42, 32, 96, 46]


# ---- gr_rect --------------------------------------------------------------------------------------------------------------
# (colour, pattern, the interior bb_fill is handed): each of gr_rect's three choices.
HOLLOW, SOLID = GRAF["GSX_PATTERN_HOLLOW"], GRAF["GSX_PATTERN_SOLID"]
RECT = {
    "hollow": (1, HOLLOW, GRAF["GSX_FIS_HOLLOW"]),
    "solid": (2, SOLID, GRAF["GSX_FIS_SOLID"]),
    "a pattern": (3, 4, GRAF["GSX_FIS_PATTERN"]),
}


@pytest.mark.parametrize("colour, pattern, interior", RECT.values(), ids=RECT)
def test_gr_rect(colour, pattern, interior):
    result = gsx.run_gsx("AES_ROM_GR_RECT", (colour, pattern, rect_at(0)), rect_pokes(40, 30, 100, 50))
    assert (result.field("AES", "GL_FIS"), result.field("AES", "GL_PATT")) == (interior, pattern)
    assert result.field("AES", "GL_MODE") == GRAF["GSX_MODE_REPLACE"]
    assert screen_changed(result)


@THROUGH
def test_gr_rect_through_its_callers_word(through_line_f):
    result = gsx.run_gsx("AES_ROM_GR_RECT", (2, SOLID, rect_at(0)), rect_pokes(40, 30, 100, 50),
                         through_line_f=through_line_f)
    assert screen_changed(result)


def test_gr_rect_reads_the_grect_after_the_colour_call():
    """The ORDER: a GRECT laid over intout, whose first word vsf_color answers — the colour it set — before gr_rect
    reads the GRECT: the fill's x is that colour, not the x staged."""
    result = gsx.run_gsx("AES_ROM_GR_RECT", (6, SOLID, aes.AES_GSX_INTOUT),
                         {aes.AES_GSX_INTOUT: vdi.pack_words(90, 30, 40, 20)})
    assert result.words(aes.AES_GSX_PTSIN, 4) == [6, 30, 45, 49]


def test_gr_rect_s_pointer_is_put_on_the_bus():
    assert screen_changed(gsx.run_gsx("AES_ROM_GR_RECT", (2, SOLID, rect_at(0) | aes.BUS_TAG), rect_pokes(40, 30, 100, 50)))


# ---- gr_just ---------------------------------------------------------------------------------------------------------------
# (just, font, the GRECT staged, width, height): each justification, each font, and each spare's sign — the GRECT's
# width and height are gsx_tcalc's answers, its x and y moved.
JUST = {
    "centred in the IBM font": (CENTRE, FONT_IBM, (40, 30, 300, 300), 80, 20),
    "right": (RIGHT, FONT_IBM, (40, 30, 300, 300), 80, 20),
    "left: x stays": (LEFT, FONT_IBM, (40, 30, 300, 300), 80, 20),
    "small font, an odd spare": (CENTRE, FONT_SMALL, (40, 30, 300, 300), 41, 9),
    "a spare of one: half of it rounds up": (CENTRE, FONT_IBM, (40, 30, 300, 300), 41, 9),
    "no room to spare": (CENTRE, FONT_IBM, (40, 30, 300, 300), 20, 4),
    "any other font: nothing measured": (CENTRE, 1, (40, 30, 300, 300), 80, 20),
    "a box narrower than the text": (CENTRE, FONT_IBM, (40, 30, 16, 300), 80, 20),
    "a spare that wraps a word": (CENTRE, FONT_IBM, (40, 30, 300, -1), 80, 0x7FFF),
    "half a spare of $7fff wraps": (CENTRE, FONT_IBM, (40, 30, 300, 0), 80, 0x7FFF),
}


# The GRECT and the text every other gr_just case and row stages.
JUST_POKES = merge_pokes(rect_pokes(40, 30, 300, 300), text_pokes(TEXT))


@pytest.mark.parametrize("just, font, rect, width, height", JUST.values(), ids=JUST)
def test_gr_just(just, font, rect, width, height):
    pokes = merge_pokes(rect_pokes(*rect), text_pokes(TEXT))
    result = gsx.run_gsx("AES_ROM_GR_JUST", (just, font, TEXT_AT, width, height, rect_at(0)), pokes)
    assert result.answer() >= 0


@THROUGH
def test_gr_just_answers_the_count_its_frame_holds(through_line_f):
    """The count gsx_tcalc stored into the word of D0 the `movem` saved — the answer, after the `movem` back."""
    result = gsx.run_gsx("AES_ROM_GR_JUST", (CENTRE, FONT_IBM, TEXT_AT, 80, 20, rect_at(0)), JUST_POKES,
                         through_line_f=through_line_f)
    assert result.answer() == len(TEXT)
    assert rect_of(result) == [40 + (80 - 40 + 1) // 2, 30 + (20 - 8 + 1) // 2, len(TEXT) * 8, 8]


def test_gr_just_s_pointers_are_put_on_the_bus():
    result = gsx.run_gsx("AES_ROM_GR_JUST", (RIGHT, FONT_SMALL, TEXT_AT | aes.BUS_TAG, 80, 20, rect_at(0) | aes.BUS_TAG),
                         JUST_POKES)
    assert result.answer() == len(TEXT)


def test_gr_just_reads_the_corner_after_gsx_tcalc():
    """The ORDER: the GRECT laid over intin, where xstrpix copies the string as words BEFORE the corner is read and
    moved — the x and y moved are the characters, not the corner staged."""
    pokes = merge_pokes(rect_pokes(40, 30, 300, 300, at=INTIN), text_pokes(b"\x05\x06\x07\x08"))
    gsx.run_gsx("AES_ROM_GR_JUST", (CENTRE, FONT_SMALL, TEXT_AT, 200, 100, INTIN), pokes)


# ---- gr_gtext ---------------------------------------------------------------------------------------------------------------
GTEXT = {
    "centred, small font": (CENTRE, FONT_SMALL, (40, 30, 120, 20)),
    "right, small font": (RIGHT, FONT_SMALL, (40, 30, 120, 20)),
    "left, small font": (LEFT, FONT_SMALL, (40, 30, 120, 20)),
    "a box too short: nothing drawn": (CENTRE, FONT_SMALL, (40, 30, 120, 3)),
    "any other font: nothing drawn": (CENTRE, 1, (40, 30, 120, 20)),
}


@pytest.mark.parametrize("just, font, rect", GTEXT.values(), ids=GTEXT)
def test_gr_gtext(just, font, rect):
    """The GRECT handed in is not touched: gr_just moves the COPY in the routine's own frame."""
    result = gsx.run_gsx("AES_ROM_GR_GTEXT", (just, font, TEXT_AT, rect_at(0)), merge_pokes(rect_pokes(*rect),
                                                                                           text_pokes(TEXT)))
    assert rect_of(result) == list(rect)
    assert screen_changed(result) == (font == FONT_SMALL and rect[3] >= 6)


# The GRECT and the text every other gr_gtext case and row stages.
GTEXT_POKES = merge_pokes(rect_pokes(40, 30, 120, 20), text_pokes(TEXT))


def test_gr_gtext_in_the_ibm_font():
    """The IBM font over the small one cached: gsx_tblt's font change (vst_height), run without the attribution
    pass — `test_aes_gemgraf.py`'s "PTSIN left elsewhere" case stands in for it."""
    result = gsx.run_gsx("AES_ROM_GR_GTEXT", (CENTRE, FONT_IBM, TEXT_AT, rect_at(0)),
                         GTEXT_POKES, **PTSIN_READ_BEFORE_IT_IS_PUT_BACK)
    assert screen_changed(result) and result.field("AES", "GL_FONT") == FONT_IBM


@THROUGH
def test_gr_gtext_through_its_callers_word(through_line_f):
    result = gsx.run_gsx("AES_ROM_GR_GTEXT", (CENTRE, FONT_SMALL, TEXT_AT, rect_at(0)),
                         GTEXT_POKES, through_line_f=through_line_f)
    assert screen_changed(result)


def test_gr_gtext_s_pointers_are_put_on_the_bus():
    result = gsx.run_gsx("AES_ROM_GR_GTEXT", (CENTRE, FONT_SMALL, TEXT_AT | aes.BUS_TAG, rect_at(0) | aes.BUS_TAG),
                         GTEXT_POKES)
    assert screen_changed(result)


# ---- gr_crack ---------------------------------------------------------------------------------------------------------------
BORDER, TEXT_COLOUR, PATTERN, INTERIOR, MODE = (answer_at(index) for index in range(5))
CRACK_POINTERS = (BORDER, TEXT_COLOUR, PATTERN, INTERIOR, MODE)


def crack(colour, pointers=CRACK_POINTERS, **kwargs):
    return gsx.run_gsx("AES_ROM_GR_CRACK", (colour, *pointers), graf.STALE_ANSWERS, **kwargs)


@pytest.mark.parametrize("colour", (0x1234, 0x11F3, 0xFFFF, 0x0000, 0x8070), ids=("transparent", "replace",
                                                                                   "every bit", "none", "the high bit"))
def test_gr_crack(colour):
    result = crack(colour)
    replace = colour & 0x80
    assert result.words(ANSWERS_AT, 5) == [colour >> 12, colour >> 8 & 15, colour >> 4 & (7 if replace else 15),
                                           colour & 15, 1 if replace else 2]


@THROUGH
def test_gr_crack_through_its_callers_word(through_line_f):
    assert crack(0x11F3, through_line_f=through_line_f).word(MODE) == 1


def test_gr_crack_s_stores_in_order_the_last_wins():
    """Every pointer the same word: the five stores land in order, so the interior colour — the last — is left."""
    assert crack(0x12B4, pointers=(BORDER,) * 5).word(BORDER) == 4


def test_gr_crack_reads_the_pattern_back_before_the_mode():
    """The pattern and the mode on one word: the pattern stored, its top bit read back, the mode stored over it."""
    result = crack(0x12B4, pointers=(BORDER, TEXT_COLOUR, PATTERN, INTERIOR, PATTERN))
    assert result.word(PATTERN) == 1


def test_gr_crack_s_pointers_are_put_on_the_bus():
    result = crack(0x11F3, pointers=tuple(at | aes.BUS_TAG for at in CRACK_POINTERS))
    assert result.words(ANSWERS_AT, 5) == [1, 1, 7, 3, 1]


# ---- gr_gicon ----------------------------------------------------------------------------------------------------------------
ICON_RECT, TEXT_RECT = rect_at(1), rect_at(2)
ICON_PLACE = rect_pokes(64, 40, 32, 32, slot=1)
TEXT_PLACE = rect_pokes(52, 72, 56, 8, slot=2)
ICON_POKES = merge_pokes(graf.ICON_FORM, ICON_PLACE, TEXT_PLACE, text_pokes(TEXT))
SELECTED, WHITEBAK = 0x01, 0x40
# (state, the character word): both colour orders, the mask skipped and kept, a character and none.
GICON = {
    "plain, a character": (0, 0x1041),
    "selected: the colours swapped": (SELECTED, 0x1041),
    "no character": (0, 0x1000),
    "whitebak over white: no mask": (WHITEBAK, 0x1000),
    "whitebak over a colour: the mask": (WHITEBAK, 0x1300),
    "whitebak and selected over white": (WHITEBAK | SELECTED, 0x0100),
}


CHARACTER_X, CHARACTER_Y = 12, 4          # the character's place in the icon


def gicon_arguments(state, character, icon=ICON_RECT, text=TEXT_RECT, tag=0):
    """gr_gicon's nine: the mask, data and label staged in this battery's band, `tag` on every pointer."""
    return (state, MASK_AT | tag, DATA_AT | tag, TEXT_AT | tag, character, CHARACTER_X, CHARACTER_Y, icon | tag,
            text | tag)


def gicon(state, character, **kwargs):
    return gsx.run_gsx("AES_ROM_GR_GICON", gicon_arguments(state, character), kwargs.pop("pokes", ICON_POKES), **kwargs)


@pytest.mark.parametrize("state, character", GICON.values(), ids=GICON)
def test_gr_gicon(state, character):
    assert screen_changed(gicon(state, character))


def test_gr_gicon_with_no_character_leaves_intin_alone():
    """No character and no text: the character test skips its store, and an empty string puts nothing in intin — so
    intin[0] is what the data's vrt_cpyfm left there, its writing mode, not a character."""
    pokes = merge_pokes(ICON_POKES, text_pokes(b""), {INTIN: vdi.pack_words(STALE)})
    result = gicon(0, 0x1000, pokes=pokes)
    assert result.word(INTIN) == GRAF["GSX_MODE_TRANSPARENT"]


@THROUGH
def test_gr_gicon_through_its_callers_word(through_line_f):
    assert screen_changed(gicon(0, 0x1041, through_line_f=through_line_f))


def test_gr_gicon_hides_the_snapshot_s_cursor_round_each_blit():
    result = gicon(SELECTED, 0x1041, onto=gsx.shown_machine())
    assert result.field("AES", "GL_MOFF") == gsx.NEST_SHOWN and screen_changed(result)


def test_gr_gicon_s_pointers_are_put_on_the_bus():
    arguments = gicon_arguments(0, 0x1041, tag=aes.BUS_TAG)
    assert screen_changed(gsx.run_gsx("AES_ROM_GR_GICON", arguments, ICON_POKES))


def test_gr_gicon_reads_the_icon_again_after_each_blit():
    """The ORDER: the icon's GRECT laid over ptsin, where each blit stores its corners — the data blit and the
    character read the GRECT as the mask blit and gr_rect left it, not as it was staged."""
    pokes = merge_pokes(graf.ICON_FORM, rect_pokes(64, 40, 32, 32, at=PTSIN), TEXT_PLACE, text_pokes(TEXT))
    arguments = gicon_arguments(0, 0x1041, icon=PTSIN)
    assert screen_changed(gsx.run_gsx("AES_ROM_GR_GICON", arguments, pokes))


def test_gr_gicon_s_text_box_over_ptsin():
    """The text's GRECT laid over ptsin: gr_rect and gr_gtext read it after the mask blit stored its corners there."""
    pokes = merge_pokes(graf.ICON_FORM, ICON_PLACE, rect_pokes(52, 72, 56, 8, at=PTSIN), text_pokes(TEXT))
    arguments = gicon_arguments(0, 0x1041, text=PTSIN)
    assert screen_changed(gsx.run_gsx("AES_ROM_GR_GICON", arguments, pokes))


# ---- gr_box ------------------------------------------------------------------------------------------------------------------
# Thickness -32768 is REACHABLE (ob_sst reads a TEDINFO's te_thickness as a word, $fed22a) and UNPINNED: its 32767
# lines overflow the oracle's write ledger (shim.c MAX_WRITES) before the ROM's run ends. The C's `subq.w` wrap is
# `(int16_t)(thickness - 1)`, checked by reading.
@pytest.mark.parametrize("thickness", (1, 2, 3, -1, -2), ids=("1", "2", "3", "-1", "-2"))
def test_gr_box(thickness):
    assert screen_changed(gsx.run_gsx("AES_ROM_GR_BOX", (40, 30, 100, 50, thickness)))


def test_gr_box_of_no_thickness_draws_nothing():
    """Not even the cursor nest is touched: the zero test is the first thing done."""
    pokes = aes.field_pokes("AES", GL_MOFF=0x1234)
    result = gsx.run_gsx("AES_ROM_GR_BOX", (40, 30, 100, 50, 0), pokes)
    assert not screen_changed(result) and result.field("AES", "GL_MOFF") == 0x1234


@THROUGH
def test_gr_box_through_its_callers_word(through_line_f):
    assert screen_changed(gsx.run_gsx("AES_ROM_GR_BOX", (40, 30, 100, 50, 2), through_line_f=through_line_f))


def test_gr_box_hides_the_snapshot_s_cursor_round_its_lines():
    result = gsx.run_gsx("AES_ROM_GR_BOX", (0, 0, 320, 200, 2), onto=gsx.shown_machine())
    assert result.field("AES", "GL_MOFF") == gsx.NEST_SHOWN and screen_changed(result)


# ---- the registry ----------------------------------------------------------------------------------------------------------
_ROWS = {
    "in by 2": ("AES_ROM_GR_INSIDE", (rect_at(0), 2), rect_pokes(40, 30, 100, 50)),
    "solid": ("AES_ROM_GR_RECT", (2, SOLID, rect_at(0)), rect_pokes(40, 30, 100, 50)),
    "a pattern": ("AES_ROM_GR_RECT", (3, 4, rect_at(0)), rect_pokes(40, 30, 100, 50)),
    "centred in the small font": ("AES_ROM_GR_JUST", (CENTRE, FONT_SMALL, TEXT_AT, 80, 20, rect_at(0)), JUST_POKES),
    "right in the IBM font": ("AES_ROM_GR_JUST", (RIGHT, FONT_IBM, TEXT_AT, 80, 20, rect_at(0)), JUST_POKES),
    "centred, small font": ("AES_ROM_GR_GTEXT", (CENTRE, FONT_SMALL, TEXT_AT, rect_at(0)), GTEXT_POKES),
    "centred, IBM font": ("AES_ROM_GR_GTEXT", (CENTRE, FONT_IBM, TEXT_AT, rect_at(0)), GTEXT_POKES),
    "replace": ("AES_ROM_GR_CRACK", (0x11F3, *CRACK_POINTERS), graf.STALE_ANSWERS),
    "transparent": ("AES_ROM_GR_CRACK", (0x1234, *CRACK_POINTERS), graf.STALE_ANSWERS),
    "plain, a character": ("AES_ROM_GR_GICON", gicon_arguments(0, 0x1041), ICON_POKES),
    "selected, a character": ("AES_ROM_GR_GICON", gicon_arguments(SELECTED, 0x1041), ICON_POKES),
    "whitebak over white: no mask": ("AES_ROM_GR_GICON", gicon_arguments(WHITEBAK, 0x1000), ICON_POKES),
    # the worst realistic shape: an icon with an EMPTY label (legal resource data) — no text to amortise the C's cost
    "whitebak over white: an empty label": ("AES_ROM_GR_GICON", gicon_arguments(WHITEBAK, 0x1000),
                                            merge_pokes(ICON_POKES, text_pokes(b""))),
    "two lines thick": ("AES_ROM_GR_BOX", (40, 30, 100, 50, 2), None),
    "one line out": ("AES_ROM_GR_BOX", (40, 30, 100, 50, -1), None),
}
gsx.register_rows(_ROWS, line_f=("in by 2", "solid", "centred in the small font", "centred, small font", "replace",
                                 "plain, a character", "two lines thick"))
gsx.register("the snapshot's cursor hidden round it", "AES_ROM_GR_BOX", (0, 0, 320, 200, 2), None, onto=gsx.shown_machine())
