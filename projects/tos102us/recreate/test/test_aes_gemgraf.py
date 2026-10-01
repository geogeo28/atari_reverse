"""AES gemgraf's gsx_ layer — the clip, attributes, lines, boxes, blits, fills and text the object draw path is built on
— `src/aes/gemgraf.c`, through `test/aes_gsx.py`'s door (the gr_ layer is `test_aes_gemgraf_gr.py`, the box
animations `test_aes_grlib.py`).

    gsx_sclip   the GRECT into the clip words; vs_clip(1, its corners in ptsin) unless h or w is 0; D0 = 1
    gsx_gclip   the clip words out;   gsx_chkclip: 1 when the GRECT touches the clip (or the clip is empty)
    gsx_cline   gsx_moff; v_pline(2, &x1 — its own frame); gsx_mon
    gsx_attr    intin[0] saved; contrl[1,3,6]; vswr_mode if the mode cache differs; vst_color / vsl_color if the
                colour cache differs; intin[0] put back
    gsx_bxpts   five corners into ptsin;   gsx_box: v_pline(5, ptsin)
    gsx_xline   per segment: vsl_udsty($5555 << a parity), v_pline(2, it); then vsl_udsty($ffff)
    gsx_xbox    gsx_bxpts, gsx_xline(4), the fourth side one row short, gsx_xline(2);  gsx_xcbox: four corners
    gsx_blt     gsx_fix(gl_src), gsx_moff, gsx_fix(gl_dst), the corners, vrt_cpyfm or (fg -1) vro_cpyfm, gsx_mon
    bb_screen   gsx_blt screen to screen;   gsx_trans: gsx_fix(dst), gsx_fix(src) standard, vrn_trnfm
    bb_fill     gsx_attr(1, mode, tcolor); vsf_interior / vsf_style through their caches; vr_recfl
    gsx_tcalc   xstrpix into intin; width = min(n * cell, *w); fit = width / cell unless the cell is taller than *h
    gsx_tblt    the font set (vst_height) when its cache differs, y + the font's height; v_gtext of intin

Every case runs in the door's machine (the AES's cursor hidden by the ROM's own gsx_moff) unless it says the
snapshot's (`shown_machine`), and the WHOLE image is compared, the screen included. A routine with a Line-F call word
is also entered through it once; gsx_bxpts and gsx_xline have none (only `bsr`s reach them).
"""
import functools

import pytest

from harness import BASE_IMAGE, addrs

import aes
import aes_gsx as gsx
import case
import vdi
import vdi_helpers
from case import merge_pokes
# THE ATTRIBUTION PASS IS OFF for a case whose call makes vst_height or vsl_width (`test_aes_gsx.py` measured why);
# each such routine's "PTSIN left elsewhere" case stands in for the pass.
from test_aes_gsx import AES_HANDLE, PTSIN_READ_BEFORE_IT_IS_PUT_BACK, contrl_of, screen_changed

IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG
WORD_ANSWER = aes.WORD_ANSWER
SIGNATURES = {
    # the gsx_ layer (this battery)
    "AES_ROM_GSX_SCLIP": (WORD_ANSWER, (IMAGE, LONG)),
    "AES_ROM_GSX_GCLIP": (None, (IMAGE, LONG)),
    "AES_ROM_GSX_CHKCLIP": (WORD_ANSWER, (IMAGE, LONG)),
    "AES_ROM_GSX_CLINE": (None, (IMAGE, WORD, WORD, WORD, WORD)),
    "AES_ROM_GSX_ATTR": (None, (IMAGE, WORD, WORD, WORD)),
    "AES_ROM_GSX_BXPTS": (None, (IMAGE, LONG)),
    "AES_ROM_GSX_BOX": (WORD_ANSWER, (IMAGE, LONG)),
    "AES_ROM_GSX_BLT": (None, (IMAGE, LONG, WORD, WORD, WORD, LONG, WORD, WORD, WORD, WORD, WORD, WORD, WORD, WORD)),
    "AES_ROM_BB_SCREEN": (None, (IMAGE, WORD, WORD, WORD, WORD, WORD, WORD, WORD)),
    "AES_ROM_GSX_TRANS": (WORD_ANSWER, (IMAGE, LONG, WORD, LONG, WORD, WORD)),
    "AES_ROM_BB_FILL": (WORD_ANSWER, (IMAGE, WORD, WORD, WORD, WORD, WORD, WORD, WORD)),
    "AES_ROM_GSX_TCALC": (WORD_ANSWER, (IMAGE, WORD, LONG, LONG, LONG, LONG)),
    "AES_ROM_GSX_TBLT": (WORD_ANSWER, (IMAGE, WORD, WORD, WORD, WORD)),
    "AES_ROM_GSX_XBOX": (WORD_ANSWER, (IMAGE, LONG)),
    "AES_ROM_GSX_XCBOX": (WORD_ANSWER, (IMAGE, LONG)),
    "AES_ROM_GSX_XLINE": (WORD_ANSWER, (IMAGE, WORD, LONG)),
    # the gr_ layer (`test_aes_gemgraf_gr.py`)
    "AES_ROM_GR_INSIDE": (None, (IMAGE, LONG, WORD)),
    "AES_ROM_GR_RECT": (WORD_ANSWER, (IMAGE, WORD, WORD, LONG)),
    "AES_ROM_GR_JUST": (WORD_ANSWER, (IMAGE, WORD, WORD, LONG, WORD, WORD, LONG)),
    "AES_ROM_GR_GTEXT": (None, (IMAGE, WORD, WORD, LONG, LONG)),
    "AES_ROM_GR_CRACK": (None, (IMAGE, WORD, LONG, LONG, LONG, LONG, LONG)),
    "AES_ROM_GR_GICON": (None, (IMAGE, WORD, LONG, LONG, LONG, WORD, WORD, WORD, LONG, LONG)),
    "AES_ROM_GR_BOX": (None, (IMAGE, WORD, WORD, WORD, WORD, WORD)),
    # the box animations (`test_aes_grlib.py`)
    "AES_ROM_GR_SETUP": (None, (IMAGE, WORD)),
    "AES_ROM_GR_SCALE": (WORD_ANSWER, (IMAGE, WORD, WORD, LONG, LONG, LONG)),
    "AES_ROM_GR_STEPCALC": (None, (IMAGE, WORD, WORD, LONG, LONG, LONG, LONG, LONG, LONG)),
    "AES_ROM_GR_XOR": (None, (IMAGE, WORD, WORD, WORD, WORD, WORD, WORD, WORD, WORD, WORD)),
    "AES_ROM_GR_MOVEBOX": (None, (IMAGE, WORD, WORD, WORD, WORD, WORD, WORD)),
    "AES_ROM_GR_GROWBOX": (None, (IMAGE, LONG, LONG)),
    "AES_ROM_GR_SHRINKBOX": (None, (IMAGE, LONG, LONG)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)

GRAF = aes.header_constants("gemgraf.h")
FONT_IBM, FONT_SMALL = GRAF["GSX_FONT_IBM"], GRAF["GSX_FONT_SMALL"]
THROUGH = gsx.THROUGH
WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES
INTIN, PTSIN, PTSOUT = aes.AES_GSX_INTIN, aes.AES_GSX_PTSIN, aes.AES_GSX_PTSOUT
STALE = aes.STALE_WORD

# ---- this battery's band of the AES window: GRECTs, answer words, points, strings and icon forms ----------------------
BAND_OFFSET = 0x700                     # the gap between `test/aes.py`'s bands and aes_gsx's at +$c00
BAND_BYTES = 0x400
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES, "test/test_aes_gemgraf*.py, test_aes_grlib.py")
RECTS_AT = BAND_AT                      # eight GRECTs
RECT_SLOTS = 8
ANSWERS_AT = RECTS_AT + RECT_SLOTS * aes.GRECT_BYTES     # sixteen answer words
ANSWERS_BYTES = 0x20
POINTS_AT = ANSWERS_AT + ANSWERS_BYTES                     # sixteen points
POINTS_BYTES = 0x40
TEXT_AT = POINTS_AT + POINTS_BYTES                         # a NUL-ended string, longer than xstrpix's byte count
TEXT_BYTES = 0x140
ICON_FORM_BYTES = 0x80                                     # a 32 x 32 one-plane form
MASK_AT = TEXT_AT + TEXT_BYTES
DATA_AT = MASK_AT + ICON_FORM_BYTES
FORM_AT = DATA_AT + ICON_FORM_BYTES                        # a destination form
assert FORM_AT + ICON_FORM_BYTES <= BAND_AT + BAND_BYTES


def rect_at(slot):
    assert 0 <= slot < RECT_SLOTS
    return RECTS_AT + slot * aes.GRECT_BYTES


def answer_at(index):
    assert 0 <= index < ANSWERS_BYTES // WORD_BYTES
    return ANSWERS_AT + index * WORD_BYTES


def rect_pokes(x, y, w, h, slot=0, at=None):
    return aes.grect_pokes(rect_at(slot) if at is None else at, x, y, w, h)


def text_pokes(text, at=TEXT_AT):
    assert len(text) < TEXT_BYTES
    return {at: text + b"\0"}


STALE_ANSWERS = {ANSWERS_AT: vdi.pack_words(*[STALE] * (ANSWERS_BYTES // WORD_BYTES))}
# The VDI's clip as the AES's (its words read back by the case): the snapshot's — the desktop below the menu bar.
SNAPSHOT_CLIP = tuple(case.word_in(BASE_IMAGE, at) for at in (aes.AES_GL_XCLIP, aes.AES_GL_YCLIP, aes.AES_GL_WCLIP,
                                                              aes.AES_GL_HCLIP))


def clip_of(result):
    return tuple(result.field("AES", name) for name in ("GL_XCLIP", "GL_YCLIP", "GL_WCLIP", "GL_HCLIP"))


def clip_pokes(x, y, w, h):
    return aes.field_pokes("AES", GL_XCLIP=x, GL_YCLIP=y, GL_WCLIP=w, GL_HCLIP=h)


# ---- gsx_sclip --------------------------------------------------------------------------------------------------------
@THROUGH
def test_gsx_sclip_sets_the_clip_and_turns_it_on(through_line_f):
    pokes = merge_pokes(rect_pokes(16, 24, 120, 60), {PTSIN: vdi.pack_words(*[STALE] * 4)})
    result = gsx.run_gsx("AES_ROM_GSX_SCLIP", (rect_at(0),), pokes, through_line_f=through_line_f)
    assert clip_of(result) == (16, 24, 120, 60)
    assert result.words(PTSIN, 4) == [16, 24, 135, 83]
    assert result.word(INTIN) == 1 and result.answer() == 1
    assert contrl_of(result) == (addrs.VDI_ROM_VS_CLIP_OPCODE, 2, 1, AES_HANDLE)


@pytest.mark.parametrize("w, h", ((120, 0), (0, 60), (0, 0)), ids=("no height", "no width", "neither"))
def test_gsx_sclip_turns_an_empty_clip_off(w, h):
    """The height tested as it is MOVED, the width read back out of its clip word: either 0 turns clipping off —
    the corners never stored (ptsin staged stale stays so)."""
    pokes = merge_pokes(rect_pokes(16, 24, w, h), {PTSIN: vdi.pack_words(*[STALE] * 4)})
    result = gsx.run_gsx("AES_ROM_GSX_SCLIP", (rect_at(0),), pokes)
    assert clip_of(result) == (16, 24, w, h)
    assert result.word(INTIN) == 0 and result.answer() == 1
    assert result.words(PTSIN, 4) == [STALE] * 4


def test_gsx_sclip_of_the_whole_screen():
    """gr_setup's call: gl_rscreen, the snapshot's own GRECT."""
    result = gsx.run_gsx("AES_ROM_GSX_SCLIP", (aes.AES_GL_RSCREEN,))
    assert clip_of(result) == (0, 0, 320, 200)


def test_gsx_sclip_reads_the_corner_again_after_its_stores():
    """The ORDER, over ptsin itself: the corner stored into ptsin[0..1] and [2..3], then the width read back — it is
    ptsin[2], the x just stored — so the right edge is x + x - 1, the bottom y + y - 1."""
    result = gsx.run_gsx("AES_ROM_GSX_SCLIP", (PTSIN,), {PTSIN: vdi.pack_words(30, 40, 100, 50)})
    assert result.words(PTSIN, 4) == [30, 40, 59, 79]


def test_gsx_sclip_over_the_clip_words_reads_its_own_stores():
    """A GRECT laid at gl_xclip: its y IS gl_wclip ($95b8) and its w intin[0] — each clip word stored before the
    next is read, and the corner read again after all four: the stores chain."""
    pokes = {INTIN: vdi.pack_words(48, 30)}
    result = gsx.run_gsx("AES_ROM_GSX_SCLIP", (aes.AES_GL_XCLIP,), pokes)
    xclip = SNAPSHOT_CLIP[0]
    assert clip_of(result) == (xclip, SNAPSHOT_CLIP[2], 48, 30)
    assert result.words(PTSIN, 4) == [xclip, 48, xclip + 47, 48 + 29]


def test_gsx_sclip_s_pointer_is_put_on_the_bus():
    result = gsx.run_gsx("AES_ROM_GSX_SCLIP", (rect_at(0) | aes.BUS_TAG,), rect_pokes(8, 16, 64, 32))
    assert clip_of(result) == (8, 16, 64, 32)


# ---- gsx_gclip ---------------------------------------------------------------------------------------------------------
@THROUGH
def test_gsx_gclip_copies_the_clip_out(through_line_f):
    pokes = merge_pokes(rect_pokes(STALE, STALE, STALE, STALE), clip_pokes(5, 6, 70, 80))
    result = gsx.run_gsx("AES_ROM_GSX_GCLIP", (rect_at(0),), pokes, through_line_f=through_line_f)
    assert result.words(rect_at(0), 4) == [5, 6, 70, 80]


# Every link of the copy's ORDER, each by a GRECT laid so one store lands on the clip word the next read takes: its x
# on gl_yclip, its y on gl_wclip, its w on gl_hclip — each read then takes the word just stored (the clip 5, 6, 70, 80).
GCLIP_CHAINS = {
    "x onto gl_yclip": (aes.AES_GL_YCLIP, [5, 5, 70, 80]),
    "y onto gl_wclip": (aes.AES_GL_XCLIP, [5, 6, 6, 80]),
    "w onto gl_hclip": (aes.AES_GL_HCLIP - 2 * WORD_BYTES, [5, 6, 70, 70]),
}


@pytest.mark.parametrize("at, stored", GCLIP_CHAINS.values(), ids=GCLIP_CHAINS)
def test_gsx_gclip_reads_each_clip_word_after_the_store_before_it(at, stored):
    result = gsx.run_gsx("AES_ROM_GSX_GCLIP", (at,), clip_pokes(5, 6, 70, 80))
    assert result.words(at, 4) == stored


def test_gsx_gclip_s_pointer_is_put_on_the_bus():
    result = gsx.run_gsx("AES_ROM_GSX_GCLIP", (rect_at(0) | aes.BUS_TAG,), rect_pokes(STALE, STALE, STALE, STALE))
    assert result.words(rect_at(0), 4) == list(SNAPSHOT_CLIP)


# ---- gsx_chkclip -------------------------------------------------------------------------------------------------------
# (clip, rect, answer): every arm, both sides of each compare, and the sums' word wrap.
CHKCLIP = {
    "inside": ((10, 20, 100, 50), (30, 30, 10, 10), 1),
    "no clip width: everything": ((10, 20, 0, 50), (500, 500, 1, 1), 1),
    "no clip height: everything": ((10, 20, 100, 0), (500, 500, 1, 1), 1),
    "x at the clip's right edge": ((10, 20, 100, 50), (110, 30, 10, 10), 0),
    "x one inside it": ((10, 20, 100, 50), (109, 30, 10, 10), 1),
    "y at the clip's bottom edge": ((10, 20, 100, 50), (30, 70, 10, 10), 0),
    "y one inside it": ((10, 20, 100, 50), (30, 69, 10, 10), 1),
    "x + w short of the clip": ((10, 20, 100, 50), (0, 30, 9, 10), 0),
    "x + w ON the clip's x: still touches": ((10, 20, 100, 50), (0, 30, 10, 10), 1),
    "y + h short of the clip": ((10, 20, 100, 50), (30, 0, 10, 19), 0),
    "y + h ON the clip's y: still touches": ((10, 20, 100, 50), (30, 0, 10, 20), 1),
    "a clip whose right edge wraps negative": ((0x7F00, 0, 0x200, 50), (0x7F80, 10, 4, 4), 0),
    "a GRECT whose right edge wraps negative": ((10, 20, 100, 50), (0x7FF0, 30, 0x20, 10), 0),
    "x + w wraps below the clip's x": ((0x7F00, 0, 0x80, 50), (0x7F70, 10, 0x100, 4), 0),
    "y + h wraps below the clip's y": ((0, 0x7F00, 50, 0x80), (10, 0x7F70, 4, 0x100), 0),
    "negative coordinates": ((-50, -40, 100, 100), (-60, -60, 20, 30), 1),
}


@pytest.mark.parametrize("clip, rect, answer", CHKCLIP.values(), ids=CHKCLIP)
def test_gsx_chkclip(clip, rect, answer):
    result = gsx.run_gsx("AES_ROM_GSX_CHKCLIP", (rect_at(0),), merge_pokes(clip_pokes(*clip), rect_pokes(*rect)))
    assert result.answer() == answer


def test_gsx_chkclip_through_its_callers_word():
    pokes = merge_pokes(clip_pokes(10, 20, 100, 50), rect_pokes(30, 30, 10, 10))
    assert gsx.run_gsx("AES_ROM_GSX_CHKCLIP", (rect_at(0),), pokes, through_line_f=True).answer() == 1


def test_gsx_chkclip_s_pointer_is_put_on_the_bus():
    pokes = merge_pokes(clip_pokes(10, 20, 100, 50), rect_pokes(0, 30, 9, 10))
    assert gsx.run_gsx("AES_ROM_GSX_CHKCLIP", (rect_at(0) | aes.BUS_TAG,), pokes).answer() == 0


# ---- gsx_cline ----------------------------------------------------------------------------------------------------------
@THROUGH
def test_gsx_cline_draws_one_line(through_line_f):
    result = gsx.run_gsx("AES_ROM_GSX_CLINE", (10, 20, 200, 120), aes.field_pokes("AES", GSX_PB_PTSIN=vdi.STALE_LONG),
                         through_line_f=through_line_f)
    assert screen_changed(result)
    assert result.field("AES", "GSX_PB_PTSIN") == PTSIN
    assert contrl_of(result)[:2] == (addrs.VDI_ROM_V_PLINE_OPCODE, 2)


def test_gsx_cline_hides_the_snapshot_s_cursor_round_the_line():
    """The snapshot's drawn arrow: gsx_moff's v_hide_c, the line, gsx_mon's v_show_c redrawing the arrow over it."""
    result = gsx.run_gsx("AES_ROM_GSX_CLINE", (0, 0, 319, 199), onto=gsx.shown_machine())
    assert result.field("AES", "GL_MOFF") == gsx.NEST_SHOWN and screen_changed(result)


# ---- gsx_attr ------------------------------------------------------------------------------------------------------------
SNAPSHOT_MODE = case.word_in(BASE_IMAGE, aes.AES_GL_MODE)
SNAPSHOT_TCOLOR = case.word_in(BASE_IMAGE, aes.AES_GL_TCOLOR)
SNAPSHOT_LCOLOR = case.word_in(BASE_IMAGE, aes.AES_GL_LCOLOR)
FIRST_CHARACTER = ord("G")              # a caller's string in intin, which gsx_attr must leave as it found it
NEW_MODE = GRAF["GSX_MODE_XOR"]
assert NEW_MODE != SNAPSHOT_MODE
# (text, mode, colour, the calls made — by their contrl[0] — and the caches after): every arm of both caches.
ATTR = {
    "text: mode and colour both new": (1, NEW_MODE, 2, (addrs.VDI_ROM_VST_COLOR_OPCODE,), (NEW_MODE, 2, SNAPSHOT_LCOLOR)),
    "text: both cached": (1, SNAPSHOT_MODE, SNAPSHOT_TCOLOR, (), (SNAPSHOT_MODE, SNAPSHOT_TCOLOR, SNAPSHOT_LCOLOR)),
    "line: the colour new": (0, SNAPSHOT_MODE, 3, (addrs.VDI_ROM_VSL_COLOR_OPCODE,), (SNAPSHOT_MODE, SNAPSHOT_TCOLOR, 3)),
    "line: the mode new, the colour cached": (0, NEW_MODE, aes.signed(SNAPSHOT_LCOLOR), (addrs.VDI_ROM_VSWR_MODE_OPCODE,),
                                              (NEW_MODE, SNAPSHOT_TCOLOR, SNAPSHOT_LCOLOR)),
    "text: a colour the LINE cache holds is still new": (1, SNAPSHOT_MODE, aes.signed(SNAPSHOT_LCOLOR),
                                                         (addrs.VDI_ROM_VST_COLOR_OPCODE,),
                                                         (SNAPSHOT_MODE, SNAPSHOT_LCOLOR, SNAPSHOT_LCOLOR)),
}
ATTR_STAGED = merge_pokes({INTIN: vdi.pack_words(FIRST_CHARACTER)},
                          aes.stale_fields("GSX_HANDLE", "GSX_OPCODE"))


def caches_of(result):
    return tuple(result.field("AES", name) for name in ("GL_MODE", "GL_TCOLOR", "GL_LCOLOR"))


@pytest.mark.parametrize("text, mode, colour, calls, caches", ATTR.values(), ids=ATTR)
def test_gsx_attr(text, mode, colour, calls, caches):
    """The caches as each arm leaves them, contrl[1, 3, 6] filled even when nothing is called, the last call's
    contrl[0] — and intin[0], a caller's first character, back as it was after any call."""
    result = gsx.run_gsx("AES_ROM_GSX_ATTR", (text, mode, colour), ATTR_STAGED)
    assert caches_of(result) == caches
    assert result.word(INTIN) == FIRST_CHARACTER
    opcode, points, words, handle = contrl_of(result)
    assert (points, words, handle) == (0, 1, AES_HANDLE)
    assert opcode == (calls[-1] if calls else STALE)


def test_gsx_attr_through_its_callers_word():
    result = gsx.run_gsx("AES_ROM_GSX_ATTR", (1, NEW_MODE, 2), ATTR_STAGED, through_line_f=True)
    assert caches_of(result)[:2] == (NEW_MODE, 2)


# ---- gsx_bxpts, gsx_box -------------------------------------------------------------------------------------------------
def corners(x, y, w, h):
    right, bottom = (x + w - 1) & 0xFFFF, (y + h - 1) & 0xFFFF
    return [x & 0xFFFF, y & 0xFFFF, right, y & 0xFFFF, right, bottom, x & 0xFFFF, bottom, x & 0xFFFF, y & 0xFFFF]


BXPTS = {
    "a box": (40, 30, 100, 50),
    "one pixel": (7, 9, 1, 1),
    "the right edge wraps": (0x7FF0, 10, 0x20, 0x8000),
}


@pytest.mark.parametrize("rect", BXPTS.values(), ids=BXPTS)
def test_gsx_bxpts(rect):
    result = gsx.run_gsx("AES_ROM_GSX_BXPTS", (rect_at(0),), merge_pokes(rect_pokes(*rect), {PTSIN: bytes(20)}))
    assert result.words(PTSIN, 10) == corners(*rect)


def test_gsx_bxpts_reads_the_whole_grect_before_its_first_store():
    """A GRECT laid over ptsin[2..5]: read whole first, so the corners are its own, not the ones just stored."""
    at = PTSIN + 2 * WORD_BYTES
    result = gsx.run_gsx("AES_ROM_GSX_BXPTS", (at,), {PTSIN: vdi.pack_words(STALE, STALE, 40, 30, 100, 50)})
    assert result.words(PTSIN, 10) == corners(40, 30, 100, 50)


def test_gsx_bxpts_reads_the_size_before_the_first_corner_is_stored():
    """...and one laid BELOW ptsin, its width and height on ptsin[0..1]: the first store lands on them, so a size read
    after it would be the corner's x and y."""
    at = PTSIN - 2 * WORD_BYTES
    result = gsx.run_gsx("AES_ROM_GSX_BXPTS", (at,), {at: vdi.pack_words(40, 30, 100, 50)})
    assert result.words(PTSIN, 10) == corners(40, 30, 100, 50)


def test_gsx_bxpts_s_pointer_is_put_on_the_bus():
    result = gsx.run_gsx("AES_ROM_GSX_BXPTS", (rect_at(0) | aes.BUS_TAG,), rect_pokes(40, 30, 100, 50))
    assert result.words(PTSIN, 10) == corners(40, 30, 100, 50)


@THROUGH
def test_gsx_box_draws_the_outline(through_line_f):
    result = gsx.run_gsx("AES_ROM_GSX_BOX", (rect_at(0),), rect_pokes(40, 30, 100, 50), through_line_f=through_line_f)
    assert screen_changed(result) and contrl_of(result)[:2] == (addrs.VDI_ROM_V_PLINE_OPCODE, 5)


def test_gsx_box_s_pointer_is_put_on_the_bus():
    assert screen_changed(gsx.run_gsx("AES_ROM_GSX_BOX", (rect_at(0) | aes.BUS_TAG,), rect_pokes(40, 30, 10, 5)))


# ---- gsx_xline, gsx_xbox, gsx_xcbox -------------------------------------------------------------------------------------
points_pokes = functools.partial(gsx.points_pokes, at=POINTS_AT)


# (points): the parity each kind of segment takes its dots from, both values of it, and the counts that draw none.
XLINE = {
    "rightwards, an even y": (10, 20, 100, 20),
    "rightwards, an odd y": (10, 21, 100, 21),
    "leftwards: the last point's y": (100, 20, 10, 21),
    "from a negative x: rightwards, signed": (-10, 20, 100, 21),
    "vertical: x ^ y, even": (40, 10, 40, 90),
    "vertical: x ^ y, odd": (41, 10, 41, 90),
    "three segments": (10, 10, 90, 10, 90, 60, 10, 60),
}


@pytest.mark.parametrize("points", XLINE.values(), ids=XLINE)
def test_gsx_xline_draws_dotted_segments(points):
    count = len(points) // 2
    result = gsx.run_gsx("AES_ROM_GSX_XLINE", (count, POINTS_AT), points_pokes(*points))
    assert screen_changed(result)
    assert result.word(INTIN) == aes.GSX_STYLE_SOLID


@pytest.mark.parametrize("count", (1, 0, -3), ids=("one point", "none", "negative"))
def test_gsx_xline_with_no_segment_only_puts_the_solid_style_back(count):
    result = gsx.run_gsx("AES_ROM_GSX_XLINE", (count, POINTS_AT), points_pokes(10, 20, 100, 20))
    assert not screen_changed(result)
    assert contrl_of(result)[0] == addrs.VDI_ROM_VSL_UDSTY_OPCODE and result.word(INTIN) == aes.GSX_STYLE_SOLID


def test_gsx_xline_reads_each_segment_after_the_call_before_it():
    """Points laid over intin: each style call stores intin[0] — the first point's x — before v_pline reads it, and
    the next segment's points are read after. A port reading the points ahead draws elsewhere."""
    result = gsx.run_gsx("AES_ROM_GSX_XLINE", (3, INTIN), {INTIN: vdi.pack_words(10, 20, 100, 21, 30, 90)})
    assert screen_changed(result)


def test_gsx_xline_s_pointer_is_put_on_the_bus():
    result = gsx.run_gsx("AES_ROM_GSX_XLINE", (2, POINTS_AT | aes.BUS_TAG), points_pokes(10, 20, 100, 20))
    assert screen_changed(result)


@THROUGH
def test_gsx_xbox_draws_a_dotted_box(through_line_f):
    result = gsx.run_gsx("AES_ROM_GSX_XBOX", (rect_at(0),), rect_pokes(40, 30, 100, 50), through_line_f=through_line_f)
    assert screen_changed(result)
    # the fourth side's points as it left them: (x, y) and the bottom-left corner a row up
    assert result.words(PTSIN, 4) == [40, 30, 40, 78]


def test_gsx_xbox_s_pointer_is_put_on_the_bus():
    assert screen_changed(gsx.run_gsx("AES_ROM_GSX_XBOX", (rect_at(0) | aes.BUS_TAG,), rect_pokes(40, 30, 10, 5)))


@THROUGH
def test_gsx_xcbox_draws_four_corners(through_line_f):
    result = gsx.run_gsx("AES_ROM_GSX_XCBOX", (rect_at(0),), rect_pokes(40, 30, 100, 80), through_line_f=through_line_f)
    assert screen_changed(result)


def test_gsx_xcbox_reads_the_grect_between_its_stores():
    """A GRECT laid over ptsin: its corner read three times between the stores that build the first corner (and its
    size after them) — each read sees the stores before it."""
    result = gsx.run_gsx("AES_ROM_GSX_XCBOX", (PTSIN,), {PTSIN: vdi.pack_words(40, 30, 100, 80)})
    assert screen_changed(result)


def test_gsx_xcbox_s_pointer_is_put_on_the_bus():
    assert screen_changed(gsx.run_gsx("AES_ROM_GSX_XCBOX", (rect_at(0) | aes.BUS_TAG,), rect_pokes(40, 30, 60, 40)))


# ---- gsx_blt, bb_screen, gsx_trans ---------------------------------------------------------------------------------------
ICON_WORDS = tuple((0xF00F, 0x0FF0)[row % 2] if row % 3 else 0xAAAA for row in range(ICON_FORM_BYTES // WORD_BYTES))
ICON_FORM = {MASK_AT: vdi.pack_words(*ICON_WORDS),
             DATA_AT: vdi.pack_words(*reversed(ICON_WORDS)),
             FORM_AT: bytes(ICON_FORM_BYTES)}
ICON_BYTES_ACROSS = 4                   # 32 pixels
SCREEN_BYTES_ACROSS = 40                # the low-resolution screen's 320 pixels, as gr_gicon hands it


# (arguments): an icon's form onto the screen in two colours (gr_gicon's, vrt_cpyfm) and the screen onto the screen
# with no colours (bb_screen's, vro_cpyfm). A one-plane form with no colours is no realistic call: vro_cpyfm refuses
# a form whose planes are not the screen's, and draws nothing.
BLT = {
    "a form onto the screen in two colours": (MASK_AT, 0, 0, ICON_BYTES_ACROSS, 0, 64, 40, SCREEN_BYTES_ACROSS, 32, 32,
                                              GRAF["GSX_MODE_TRANSPARENT"], 2, 5),
    "the screen onto the screen, no colours": (0, 0, 40, 0, 0, 100, 100, 0, 48, 32, GRAF["GSX_MODE_REPLACE"], -1, 3),
}


@pytest.mark.parametrize("arguments", BLT.values(), ids=BLT)
def test_gsx_blt(arguments):
    result = gsx.run_gsx("AES_ROM_GSX_BLT", arguments, merge_pokes(ICON_FORM, gsx.GL_MFDBS_STALE))
    source, sx, sy, _sw, destination, dx, dy, _dw, w, h, _rule, foreground, _background = arguments
    assert result.words(PTSIN, 8) == [sx, sy, sx + w - 1, sy + h - 1, dx, dy, dx + w - 1, dy + h - 1]
    assert gsx.mfdb_of(result, aes.AES_GL_SRC)[0] == source and gsx.mfdb_of(result, aes.AES_GL_DST)[0] == destination
    called = addrs.VDI_ROM_VRT_CPYFM_OPCODE if foreground != -1 else addrs.VDI_ROM_VRO_CPYFM_OPCODE
    assert contrl_of(result)[0] == called
    assert screen_changed(result)


def test_gsx_blt_of_a_form_into_a_form():
    """Neither MFDB the screen: gl_dst a one-plane form as wide as its own bytes and as tall as the blit — each
    MFDB's width its own (4 and 6 bytes across), the height the blit's, not its width. (No AES caller blits into a
    form — every one hands the screen — and the VDI copies nothing here; the MFDBs are what this case is about.)"""
    arguments = (MASK_AT, 0, 0, ICON_BYTES_ACROSS, FORM_AT, 8, 0, 6, 32, 16, GRAF["GSX_MODE_REPLACE"], -1, -1)
    result = gsx.run_gsx("AES_ROM_GSX_BLT", arguments, merge_pokes(ICON_FORM, gsx.GL_MFDBS_STALE))
    assert gsx.mfdb_of(result, aes.AES_GL_DST) == (FORM_AT, 48, 16, 3, 0, 1)


def test_gsx_blt_through_its_callers_word():
    result = gsx.run_gsx("AES_ROM_GSX_BLT", BLT["a form onto the screen in two colours"], ICON_FORM, through_line_f=True)
    assert screen_changed(result)


def test_gsx_blt_hides_the_snapshot_s_cursor_between_its_two_mfdbs():
    """The snapshot's drawn arrow: v_hide_c after gl_src is set up and before gl_dst, v_show_c last."""
    result = gsx.run_gsx("AES_ROM_GSX_BLT", BLT["a form onto the screen in two colours"], ICON_FORM,
                         onto=gsx.shown_machine())
    assert result.field("AES", "GL_MOFF") == gsx.NEST_SHOWN and screen_changed(result)


def test_gsx_blt_s_form_pointer_is_put_on_the_bus():
    """The form's address with a top byte: stored into gl_src AS IT IS, read through the bus by the VDI."""
    arguments = (MASK_AT | aes.BUS_TAG, *BLT["a form onto the screen in two colours"][1:])
    result = gsx.run_gsx("AES_ROM_GSX_BLT", arguments, ICON_FORM)
    assert gsx.mfdb_of(result, aes.AES_GL_SRC)[0] == MASK_AT | aes.BUS_TAG and screen_changed(result)


@THROUGH
def test_bb_screen_copies_the_screen(through_line_f):
    result = gsx.run_gsx("AES_ROM_BB_SCREEN", (GRAF["GSX_MODE_REPLACE"], 0, 40, 100, 100, 48, 32), gsx.GL_MFDBS_STALE,
                         through_line_f=through_line_f)
    assert screen_changed(result)
    assert gsx.mfdb_of(result, aes.AES_GL_SRC)[0] == 0 and contrl_of(result)[0] == addrs.VDI_ROM_VRO_CPYFM_OPCODE


@THROUGH
def test_gsx_trans_a_standard_form_to_the_device_s(through_line_f):
    """gl_dst set up first, then gl_src — made standard, one plane, by one longword store."""
    pokes = merge_pokes(ICON_FORM, gsx.GL_MFDBS_STALE)
    result = gsx.run_gsx("AES_ROM_GSX_TRANS", (MASK_AT, ICON_BYTES_ACROSS, FORM_AT, ICON_BYTES_ACROSS, 32), pokes,
                         through_line_f=through_line_f)
    assert gsx.mfdb_of(result, aes.AES_GL_SRC) == (MASK_AT, 32, 32, 2, 1, 1)
    assert gsx.mfdb_of(result, aes.AES_GL_DST) == (FORM_AT, 32, 32, 2, 0, 1)
    assert result.after(FORM_AT, ICON_FORM_BYTES) != bytes(ICON_FORM_BYTES)


def test_gsx_trans_sets_each_mfdb_from_its_own_width():
    """The two forms' widths differ: gl_dst is the destination's (6 bytes, 48 pixels), gl_src the source's."""
    pokes = merge_pokes(ICON_FORM, gsx.GL_MFDBS_STALE)
    result = gsx.run_gsx("AES_ROM_GSX_TRANS", (MASK_AT, ICON_BYTES_ACROSS, FORM_AT, 6, 16), pokes)
    assert gsx.mfdb_of(result, aes.AES_GL_DST) == (FORM_AT, 48, 16, 3, 0, 1)
    assert gsx.mfdb_of(result, aes.AES_GL_SRC) == (MASK_AT, 32, 16, 2, 1, 1)


# NO TOP-BYTE CASE for gsx_trans: it hands its two addresses on as they are (gsx_fix stores them into gl_src / gl_dst,
# which `test_gsx_blt_s_form_pointer_is_put_on_the_bus` holds), and the VDI's C vr_trnfm ($fd2d32, `src/vdi/helpers.c`)
# reads a form through the image UNMASKED — a tagged one, which the 68000's bus reaches, faults the host build. A VDI
# finding, reported, not this battery's to work round.


# ---- bb_fill -------------------------------------------------------------------------------------------------------------
SNAPSHOT_FIS = case.word_in(BASE_IMAGE, aes.AES_GL_FIS)
SNAPSHOT_PATT = case.word_in(BASE_IMAGE, aes.AES_GL_PATT)
# (mode, interior, style): each cache missed and hit.
BB_FILL = {
    "every cache new": (GRAF["GSX_MODE_REPLACE"], GRAF["GSX_FIS_PATTERN"], 4),
    "every cache hit": (SNAPSHOT_MODE, SNAPSHOT_FIS, SNAPSHOT_PATT),
    "the interior new, the style cached": (GRAF["GSX_MODE_REPLACE"], GRAF["GSX_FIS_HOLLOW"], SNAPSHOT_PATT),
    "the style new, the interior cached": (SNAPSHOT_MODE, SNAPSHOT_FIS, 2),
}


@pytest.mark.parametrize("mode, interior, style", BB_FILL.values(), ids=BB_FILL)
def test_bb_fill(mode, interior, style):
    result = gsx.run_gsx("AES_ROM_BB_FILL", (mode, interior, style, 40, 30, 100, 50), gsx.GL_MFDBS_STALE)
    assert (result.field("AES", "GL_MODE"), result.field("AES", "GL_FIS"), result.field("AES", "GL_PATT")) == \
        (mode, interior, style)
    assert result.words(PTSIN, 4) == [40, 30, 139, 79]
    assert gsx.mfdb_of(result, aes.AES_GL_DST)[0] == 0
    assert contrl_of(result)[0] == addrs.VDI_ROM_VR_RECFL_OPCODE


def test_bb_fill_through_its_callers_word():
    result = gsx.run_gsx("AES_ROM_BB_FILL", (GRAF["GSX_MODE_REPLACE"], GRAF["GSX_FIS_SOLID"], 7, 4, 3, 30, 20),
                         through_line_f=True)
    assert screen_changed(result)


# ---- gsx_tcalc -----------------------------------------------------------------------------------------------------------
WIDTH_AT, HEIGHT_AT, COUNT_AT = answer_at(0), answer_at(1), answer_at(2)
TEXT = b"Desktop"
LONG_TEXT = bytes(ord("A") + index % 26 for index in range(300))     # past xstrpix's byte count: it counts 300 & 255


def answers_pokes(width, height, count=STALE):
    return {WIDTH_AT: vdi.pack_words(width, height, count)}


# (font, text, the width and height answer words staged): each font, each arm of the width clamp and height test.
TCALC = {
    "IBM: the text fits": (FONT_IBM, TEXT, 200, 16),
    "IBM: wider than the box": (FONT_IBM, TEXT, 20, 16),
    "IBM: the cell taller than the box": (FONT_IBM, TEXT, 200, 7),
    "IBM: the cell as tall as the box": (FONT_IBM, TEXT, 200, 8),
    "small: the text fits": (FONT_SMALL, TEXT, 200, 6),
    "small: a box narrower than one cell": (FONT_SMALL, TEXT, 4, 6),
    "any other font: all three 0": (1, TEXT, 200, 16),
    "an empty string": (FONT_IBM, b"", 200, 16),
    "a string longer than 255": (FONT_SMALL, LONG_TEXT, 0x7FFF, 16),
    "a negative width": (FONT_IBM, TEXT, -8, 16),
}


@pytest.mark.parametrize("font, text, width, height", TCALC.values(), ids=TCALC)
def test_gsx_tcalc(font, text, width, height):
    pokes = merge_pokes(text_pokes(text), answers_pokes(width, height))
    result = gsx.run_gsx("AES_ROM_GSX_TCALC", (font, TEXT_AT, WIDTH_AT, HEIGHT_AT, COUNT_AT), pokes)
    assert result.answer() == aes.signed(result.word(COUNT_AT))
    if font in (FONT_IBM, FONT_SMALL):
        assert result.words(INTIN, min(len(text), 4)) == list(text[:4])


@THROUGH
def test_gsx_tcalc_through_its_callers_word(through_line_f):
    pokes = merge_pokes(text_pokes(TEXT), answers_pokes(200, 16))
    result = gsx.run_gsx("AES_ROM_GSX_TCALC", (FONT_IBM, TEXT_AT, WIDTH_AT, HEIGHT_AT, COUNT_AT), pokes,
                         through_line_f=through_line_f)
    assert result.words(WIDTH_AT, 3) == [len(TEXT) * 8, 8, len(TEXT)]


def test_gsx_tcalc_reads_each_answer_after_the_store_before_it():
    """The ORDER, through answer pointers laid over each other: the height pointer IS the width's, so the height
    compared is the width just stored (56, not the 16 staged) — and the count lands on the same word last."""
    pokes = merge_pokes(text_pokes(TEXT), answers_pokes(200, 16))
    result = gsx.run_gsx("AES_ROM_GSX_TCALC", (FONT_IBM, TEXT_AT, WIDTH_AT, WIDTH_AT, WIDTH_AT), pokes)
    assert result.word(WIDTH_AT) == len(TEXT)


def test_gsx_tcalc_reads_the_width_after_the_string_is_stored():
    """...and the width pointer laid over intin[1]: xstrpix stores the string's second character there (33, '!')
    before the width is compared — 5 characters of 8 pixels, 40, are cut to 33, not to the 200 staged."""
    pokes = merge_pokes(text_pokes(b"G!XYZ"), {INTIN + WORD_BYTES: vdi.pack_words(200)}, answers_pokes(STALE, 16))
    result = gsx.run_gsx("AES_ROM_GSX_TCALC", (FONT_IBM, TEXT_AT, INTIN + WORD_BYTES, HEIGHT_AT, COUNT_AT), pokes)
    assert result.word(INTIN + WORD_BYTES) == ord("!")


def test_gsx_tcalc_s_divide_overflows_and_leaves_its_dividend():
    """A cell width of -1 (staged: no font has one) and a width of -32768: -32768 / -1 overflows `divs.w`, which sets V
    and leaves the register as it was — the count stored is the dividend's low word, $8000."""
    pokes = merge_pokes(text_pokes(TEXT), answers_pokes(-0x8000, 16), aes.field_pokes("AES", GL_WCHAR=0xFFFF))
    result = gsx.run_gsx("AES_ROM_GSX_TCALC", (FONT_IBM, TEXT_AT, WIDTH_AT, HEIGHT_AT, COUNT_AT), pokes)
    assert result.word(COUNT_AT) == 0x8000


def test_gsx_tcalc_s_divide_by_a_zero_cell_is_refused_on_the_host():
    """A cell width of 0: the 68000 takes the zero-divide exception (vector 5), which the host refuses by name rather
    than dividing (`m68k_idioms.h`) — the arm no differential can run, pinned here."""
    pokes = gsx.machine(merge_pokes(text_pokes(TEXT), answers_pokes(200, 16), aes.field_pokes("AES", GL_WCHAR=0)))
    arguments = (("ctypes.c_int16", str(FONT_IBM)), *(gsx.pointer(at) for at in (TEXT_AT, WIDTH_AT, HEIGHT_AT, COUNT_AT)))
    returncode, stderr, _image = vdi_helpers.refusal_over("aes_gsx_tcalc", pokes, arguments=arguments, read_back=False)
    assert returncode != 0 and "divs.w by zero" in stderr, stderr


def test_gsx_tcalc_s_pointers_are_put_on_the_bus():
    pokes = merge_pokes(text_pokes(TEXT), answers_pokes(200, 16))
    tagged = tuple(at | aes.BUS_TAG for at in (TEXT_AT, WIDTH_AT, HEIGHT_AT, COUNT_AT))
    result = gsx.run_gsx("AES_ROM_GSX_TCALC", (FONT_SMALL, *tagged), pokes)
    assert result.words(WIDTH_AT, 3) == [len(TEXT) * 6, 6, len(TEXT)]


# ---- gsx_tblt ------------------------------------------------------------------------------------------------------------
SNAPSHOT_FONT = case.word_in(BASE_IMAGE, aes.AES_GL_FONT)
assert SNAPSHOT_FONT == GRAF["GSX_FONT_SMALL"]
TEXT_IN_INTIN = {INTIN: vdi.pack_words(*b"GEM")}


@THROUGH
def test_gsx_tblt_in_the_cached_font(through_line_f):
    """The small font, the snapshot's own: no vst_height, y moved down by its character height (4)."""
    result = gsx.run_gsx("AES_ROM_GSX_TBLT", (FONT_SMALL, 40, 60, 3), TEXT_IN_INTIN, through_line_f=through_line_f)
    assert result.words(PTSIN, 2) == [40, 64]
    assert contrl_of(result) == (addrs.VDI_ROM_V_GTEXT_OPCODE, 1, 3, AES_HANDLE)
    assert screen_changed(result)


# The font change runs WITHOUT the attribution pass (vst_height reads PTSIN before it puts it back), so what stands in
# for it is staging: every word the arm stores — the four answers, contrl's handle, the point — stale beforehand, so a
# store skipped differs from the one the ROM made (contrl[0..3] are stale in every machine).
FONT_CHANGE_STALE = merge_pokes(TEXT_IN_INTIN, {PTSIN: vdi.pack_words(STALE, STALE)},
                                aes.stale_fields("GL_HPTSCHAR", "GL_WPTSCHAR", "GL_WCHAR", "GL_HCHAR", "GSX_HANDLE"))


@THROUGH
def test_gsx_tblt_changes_the_font(through_line_f):
    """The IBM font over the small one cached: vst_height to work_out's largest character height, its four answers
    into the IBM font's words, the cache stored after the call, and y moved by the height vst_height just answered."""
    result = gsx.run_gsx("AES_ROM_GSX_TBLT", (FONT_IBM, 40, 60, 3), FONT_CHANGE_STALE, through_line_f=through_line_f,
                         **PTSIN_READ_BEFORE_IT_IS_PUT_BACK)
    assert result.field("AES", "GL_FONT") == FONT_IBM
    assert result.words(PTSIN, 2) == [40, 60 + result.field("AES", "GL_HPTSCHAR")]
    assert screen_changed(result)


def test_gsx_tblt_changes_back_to_the_small_font():
    """...and the small font over the IBM one cached: vst_height to work_out's SMALLEST character height, its answers
    into the small font's words."""
    pokes = merge_pokes(FONT_CHANGE_STALE, aes.field_pokes("AES", GL_FONT=FONT_IBM, GL_HSPTSCHAR=STALE, GL_WSPTSCHAR=STALE,
                                                           GL_WSCHAR=STALE, GL_HSCHAR=STALE))
    result = gsx.run_gsx("AES_ROM_GSX_TBLT", (FONT_SMALL, 40, 60, 3), pokes, **PTSIN_READ_BEFORE_IT_IS_PUT_BACK)
    assert result.field("AES", "GL_FONT") == FONT_SMALL
    assert result.words(PTSIN, 2) == [40, 60 + result.field("AES", "GL_HSPTSCHAR")]


def test_gsx_tblt_s_font_change_puts_a_ptsin_left_elsewhere_back():
    """The stand-in for the attribution pass on the font change: PTSIN left at the caller's points, which vst_height
    reads and then stores back — so v_gtext's point is ptsin's."""
    pokes = merge_pokes(TEXT_IN_INTIN, aes.field_pokes("AES", GSX_PB_PTSIN=POINTS_AT), points_pokes(0, 13))
    result = gsx.run_gsx("AES_ROM_GSX_TBLT", (FONT_IBM, 40, 60, 3), pokes, **PTSIN_READ_BEFORE_IT_IS_PUT_BACK)
    assert result.field("AES", "GSX_PB_PTSIN") == PTSIN


@pytest.mark.parametrize("font", (1, 4), ids=("font 1", "font 4"))
def test_gsx_tblt_in_any_other_font_draws_as_the_vdi_stands(font):
    """Neither the IBM nor the small font: no vst_height, no baseline, the cache untouched."""
    result = gsx.run_gsx("AES_ROM_GSX_TBLT", (font, 40, 60, 3), TEXT_IN_INTIN)
    assert result.words(PTSIN, 2) == [40, 60] and result.field("AES", "GL_FONT") == SNAPSHOT_FONT


def test_gsx_tblt_reads_the_block_s_ptsin_as_it_was_left():
    """No vst_height to put PTSIN back: v_gtext reads its point where the block's PTSIN was left — here the case's
    points, not the ptsin gsx_tblt stores."""
    pokes = merge_pokes(TEXT_IN_INTIN, aes.field_pokes("AES", GSX_PB_PTSIN=POINTS_AT), points_pokes(100, 100))
    result = gsx.run_gsx("AES_ROM_GSX_TBLT", (FONT_SMALL, 40, 60, 3), pokes)
    assert result.field("AES", "GSX_PB_PTSIN") == POINTS_AT and screen_changed(result)


# ---- the registry ----------------------------------------------------------------------------------------------------
# Each routine's realistic shapes priced (`bench/tier3.py`, mechanism (V) for every one that reaches the VDI), and
# each with a Line-F call word entered through it once (verified, unpriced).
_ROWS = {
    "a GRECT: clipping on": ("AES_ROM_GSX_SCLIP", (rect_at(0),), rect_pokes(16, 24, 120, 60)),
    "no height: clipping off": ("AES_ROM_GSX_SCLIP", (rect_at(0),), rect_pokes(16, 24, 120, 0)),
    "the clip out": ("AES_ROM_GSX_GCLIP", (rect_at(0),), None),
    "inside": ("AES_ROM_GSX_CHKCLIP", (rect_at(0),), rect_pokes(30, 30, 10, 10)),
    "past the clip's bottom": ("AES_ROM_GSX_CHKCLIP", (rect_at(0),), rect_pokes(30, 199, 10, 10)),
    "touching its top-left": ("AES_ROM_GSX_CHKCLIP", (rect_at(0),), rect_pokes(-10, 0, 11, 12)),
    "a diagonal": ("AES_ROM_GSX_CLINE", (10, 20, 200, 120), None),
    "text: mode and colour both new": ("AES_ROM_GSX_ATTR", ATTR["text: mode and colour both new"][:3], ATTR_STAGED),
    "text: both cached": ("AES_ROM_GSX_ATTR", ATTR["text: both cached"][:3], ATTR_STAGED),
    "a box's corners": ("AES_ROM_GSX_BXPTS", (rect_at(0),), rect_pokes(40, 30, 100, 50)),
    "a box": ("AES_ROM_GSX_BOX", (rect_at(0),), rect_pokes(40, 30, 100, 50)),
    "three dotted segments": ("AES_ROM_GSX_XLINE", (4, POINTS_AT), points_pokes(*XLINE["three segments"])),
    "a dotted box": ("AES_ROM_GSX_XBOX", (rect_at(0),), rect_pokes(40, 30, 100, 50)),
    "a box's dotted corners": ("AES_ROM_GSX_XCBOX", (rect_at(0),), rect_pokes(40, 30, 100, 80)),
    "an icon's form in two colours": ("AES_ROM_GSX_BLT", BLT["a form onto the screen in two colours"], ICON_FORM),
    "the screen onto the screen": ("AES_ROM_GSX_BLT", BLT["the screen onto the screen, no colours"], None),
    "a screen rectangle": ("AES_ROM_BB_SCREEN", (GRAF["GSX_MODE_REPLACE"], 0, 40, 100, 100, 48, 32), None),
    "a standard form": ("AES_ROM_GSX_TRANS", (MASK_AT, ICON_BYTES_ACROSS, FORM_AT, ICON_BYTES_ACROSS, 32), ICON_FORM),
    "every cache new": ("AES_ROM_BB_FILL", (*BB_FILL["every cache new"], 40, 30, 100, 50), None),
    "every cache hit": ("AES_ROM_BB_FILL", (*BB_FILL["every cache hit"], 40, 30, 100, 50), None),
    "IBM: the text fits": ("AES_ROM_GSX_TCALC", (FONT_IBM, TEXT_AT, WIDTH_AT, HEIGHT_AT, COUNT_AT),
                           merge_pokes(text_pokes(TEXT), answers_pokes(200, 16))),
    "small: the cell too tall": ("AES_ROM_GSX_TCALC", (FONT_SMALL, TEXT_AT, WIDTH_AT, HEIGHT_AT, COUNT_AT),
                                 merge_pokes(text_pokes(TEXT), answers_pokes(200, 4))),
    # the worst realistic shape (an empty G_TEXT): the C's fixed cost over the fewest xstrpix passes
    "small: an empty string, the cell too tall": ("AES_ROM_GSX_TCALC", (FONT_SMALL, TEXT_AT, WIDTH_AT, HEIGHT_AT, COUNT_AT),
                                                  merge_pokes(text_pokes(b""), answers_pokes(200, 4))),
    "the cached font": ("AES_ROM_GSX_TBLT", (FONT_SMALL, 40, 60, 3), TEXT_IN_INTIN),
    "the font changed": ("AES_ROM_GSX_TBLT", (FONT_IBM, 40, 60, 3), TEXT_IN_INTIN),
    "one point: no segment": ("AES_ROM_GSX_XLINE", (1, POINTS_AT), points_pokes(10, 20, 100, 20)),
}
gsx.register_rows(_ROWS, line_f=("a GRECT: clipping on", "the clip out", "inside", "a diagonal",
                                 "text: mode and colour both new", "a box", "a dotted box", "a box's dotted corners",
                                 "an icon's form in two colours", "a screen rectangle", "a standard form",
                                 "every cache new", "IBM: the text fits", "the cached font"))
gsx.register("the snapshot's cursor hidden round it", "AES_ROM_GSX_CLINE", (0, 0, 319, 199), None,
             onto=gsx.shown_machine())
