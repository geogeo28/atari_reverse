"""v_gtext ($fcd756, opcode 8) — `src/vdi/gtext.c`, entered as the dispatcher's `jsr` leaves the machine.

    $fcd756  count = contrl[3], nothing at <= 0; justified = contrl[0] is the GDP's 11; the effects' parameters
             from the font; the underline's drop; FBASE/FWIDTH; the offset along the text by H_ALIGN (vqt_extent
             into a frame, contrl[2] back to 0 — not for justified text) and across it by V_ALIGN (a font line,
             and italic's lean at it: `mulu.w` low word, `divu.w`); DESTX/DESTY and the underline's start and
             step by the rotation; TEXT_FG, DELY; the fast path ($fcf96a) for a plain monospaced 8-wide string
    $fcdbae  per character: '?' outside FIRST..LAST (unsigned), SOURCEX/DELX from the offset table (the index
             sign-extended), TextBlt; justified text's gaps; a HOR table's byte
    $fcdd00  the underline: UL_SIZE rows of $a003, each through clip_line when CLIP is on, LN_MASK `asr.w`-ed
             with bit 15 set when bit 0 was

Every case draws REAL glyphs (`vdi_gtext`) over a canvas whose every plane differs and is compared whole — the
screen, the Line-A words, the scratch — by the differential; the assertions here say what the case is FOR.

WHAT THE ROM LEAVES UNSET (`src/vdi/gtext.c`) is pinned where the harness makes it deterministic: H_ALIGN over 2
and V_ALIGN over 5 (staged through the workstation RECORD, which the dispatcher copies from — vst_alignment never
stores either) and the UNDERLINE of a rotation that is not a right angle read frame words the ROM never writes,
which lie in the stack band the snapshot leaves zero — 0 on both shores here, whatever the last call at that depth
left on the machine. A font whose TOP or BOTTOM is 0 under an alignment that leans by it is pinned as the host's
named refusal (`divu.w` by zero: vector 5 on the machine), and so is a scratch copy past TextBlt's effects buffer.

WHAT IS NOT PINNED, and why: the same unwritten words reached THROUGH d_justified, whose frame there overlays
vqt_extent's residue (the ROM reads that, the C 0); and the half and three-quarter turns' re-read of BOTTOM after
their DESTY / DESTX store — a header laid with its BOTTOM on either reads its tables out of the I/O page. The TOP
read after the DESTX store is pinned (a header over the Line-A variables).

THE MUTATION SWEEP of `src/vdi/gtext.c` (this battery and `test_vdi_gtext_justified.py`, strict classifier —
README, "Mutation sweeps"): 144 mutants, 143 KILLED, 1 ABNORMAL, 0 SURVIVED. ABNORMAL: WEIGHT taken from the
font's LIGHTEN ($5555) — a bold of 21,845 pixels, whose scratch copy TextBlt's host bound refuses by name (an
abort, not a failed assertion; the ROM would write it over its own RAM). The italic lean's product kept whole
is killed only by a RAM font with offsets of $2000 (no real font's line times offset reaches $10000), and DELY
stored once before the loop by the font CUR_FONT becomes after the first glyph.
"""
import signal

import pytest

from harness import BASE_IMAGE, addrs

import staging
import vdi
import vdi_gtext as g
import vdi_helpers
import vdi_raster
import vdi_text
import vdi_text_c as text
from case import continued, merge_pokes
from vdi_gtext import (ALL_EFFECTS, LIGHTEN, OUTLINE, SKEW, THICKEN, UNDERLINE, font_word, gtext_call, run_gtext,
                       screen_changed)

HELLO = "Hello, world"
ROTATIONS = vdi_text.ROTATIONS
QUARTER_TURN, HALF_TURN, FULL_TURN = vdi_text.QUARTER_TURN, vdi_text.HALF_TURN, vdi_text.FULL_TURN
FORTY = "The quick brown fox jumps over a lazy do"
assert len(FORTY) == 40
# ...and the longest the fast path takes at x = 8 inside the desktop window: its clip test refuses a string
# whose last pixel reaches XMAXCL (319), so 38 cells of 8 — and a ninety-character one only through the loop.
FAST = FORTY[:38]

# The header slot a case stages its own RAM font in (each case its own copy, CUR_FONT pointed at it).
RAM_FONT_AT = text.header_at(8)


def with_font_at(pokes, at):
    """`pokes` with the workstation's font a header staged at `at` (whose own pokes `pokes` already hold)."""
    return merge_pokes(pokes, vdi.dispatched_pokes(onto=pokes, CUR_FONT=at))


def test_the_fonts_band_is_dead_in_the_snapshot():
    g.assert_dead_in_the_snapshot()


# ---- the count ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("count", (0, -1, -32768))
def test_nothing_is_drawn_for_a_count_of_0_or_less(count):
    pokes = merge_pokes(gtext_call(HELLO), {vdi.CONTRL_AT + vdi.CONTRL_N_INTIN: vdi.pack_words(count)})
    result = run_gtext(pokes)
    assert not screen_changed(result)
    assert result.linea("FWIDTH") == vdi.STALE_WORD


@pytest.mark.parametrize("string", ("A", FORTY, FORTY + FORTY + "0123456789"))
def test_strings_of_one_forty_and_ninety_characters(string):
    """Past more than one glyph, and far enough that the string runs off the window's right edge."""
    assert screen_changed(run_gtext(gtext_call(string, x=5, y=50)))


# ---- the alignments ---------------------------------------------------------------------------------------
FONTS = ("6x6", "8x8", "8x16", "proportional", "first 32")


@pytest.mark.parametrize("v_align", range(6))
@pytest.mark.parametrize("h_align", range(3))
@pytest.mark.parametrize("font", FONTS)
def test_every_alignment_in_every_font_italic(font, h_align, v_align):
    """Italic, so the lean at each font line is not 0: the right offset over top for half and ascent, the
    left over bottom for descent, both for the top line."""
    result = run_gtext(gtext_call(HELLO, x=160, y=100, font=font, h_align=h_align, v_align=v_align, style=SKEW))
    assert screen_changed(result)
    # vqt_extent answered 4 points into v_gtext's own frame; contrl[2] is put back to 0 after it.
    assert result.word(g.POINTS_ANSWERED) == 0


# x on a byte and off it: left-aligned and upright, a plain string on a byte is the fast path's, so the upright
# vertical arms at H_ALIGN 0 are drawn through TextBlt only off it.
UPRIGHT_XS = {"on a byte": 160, "off a byte": 161}


@pytest.mark.parametrize("x", UPRIGHT_XS)
@pytest.mark.parametrize("v_align", range(6))
@pytest.mark.parametrize("h_align", range(3))
def test_every_alignment_upright(h_align, v_align, x):
    assert screen_changed(run_gtext(gtext_call(HELLO, x=UPRIGHT_XS[x], y=100, h_align=h_align, v_align=v_align)))


@pytest.mark.parametrize("h_align", (1, 2))
def test_centring_measures_and_leaves_the_result_flag_set(h_align):
    """vqt_extent sets VDI_RESULT and writes the width into the scratch; v_gtext leaves both."""
    result = run_gtext(gtext_call(HELLO, x=160, y=100, h_align=h_align))
    assert result.word(vdi.VDI_RESULT) == vdi.VDI_RESULT_SET
    assert result.word(vdi.VDI_EXTENT_SCRATCH) == 12 * font_word("8x16", "MAX_CELL_WIDTH")


def test_left_alignment_measures_nothing():
    result = run_gtext(gtext_call(HELLO, x=160, y=100))
    assert result.word(vdi.VDI_RESULT) == 0
    assert result.word(vdi.VDI_EXTENT_SCRATCH) == vdi.STALE_WORD


# ---- the rotations ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("style", (0, UNDERLINE, ALL_EFFECTS, OUTLINE | UNDERLINE))
@pytest.mark.parametrize("rotation", ROTATIONS)
@pytest.mark.parametrize("font", ("8x8", "8x16"))
def test_every_right_angle(font, rotation, style):
    result = run_gtext(gtext_call("Rotate", x=160, y=100, font=font, rotation=rotation, style=style,
                                  h_align=1, v_align=2))
    assert screen_changed(result)


@pytest.mark.parametrize("rotation", ROTATIONS)
@pytest.mark.parametrize("v_align", (0, 3, 4))
def test_every_right_angle_at_the_bottom_lines(rotation, v_align):
    assert screen_changed(run_gtext(gtext_call("Turned", x=150, y=110, rotation=rotation, v_align=v_align,
                                               h_align=2, style=SKEW | UNDERLINE)))


# vst_rotation's `(angle + 450) / 900 * 900` answers 3600 for 3150 and -900 for -1400 — rotations v_gtext has no
# arm for: DESTX/DESTY stay where the last text left them, and TextBlt takes any other as a quarter turn.
OTHER_ROTATIONS = (FULL_TURN, -QUARTER_TURN & 0xFFFF, QUARTER_TURN // 2, 1)


@pytest.mark.parametrize("rotation", OTHER_ROTATIONS)
@pytest.mark.parametrize("style", (0, THICKEN | SKEW, OUTLINE))
def test_another_rotation_draws_where_the_last_text_stopped(rotation, style):
    result = run_gtext(gtext_call("Stale", x=10, y=20, rotation=rotation, style=style))
    assert screen_changed(result)


# Where the last text stopped ON A BYTE: a plain 8x16 string is the fast path's shape in every way but its rotation.
LAST_TEXT_END_ON_A_BYTE = 136


@pytest.mark.parametrize("rotation", OTHER_ROTATIONS)
def test_another_rotation_alone_refuses_the_fast_path(rotation):
    """The rotation is OR-ed into the refusal word: TextBlt draws it (as a quarter turn), not the fast path upright."""
    pokes = merge_pokes(gtext_call("Stale", x=10, y=20, rotation=rotation), vdi.linea_pokes(DESTX=LAST_TEXT_END_ON_A_BYTE))
    result = run_gtext(pokes)
    assert not took_the_fast_path(result) and screen_changed(result)


# ---- past the arms the ROM names: frame words it never writes --------------------------------------------------
# H_ALIGN over 2 and V_ALIGN over 5 leave the offset along or across the text an unwritten frame word, and a
# rotation that is not a right angle the underline's start and steps. vst_alignment clamps both alignments and
# the dispatcher re-copies them from the workstation record before every call, so it is a program poking the
# RECORD (WS_H_ALIGN / WS_V_ALIGN) that reaches the first two; vst_rotation(3150) answers 3600, which reaches the
# third through the real API. The value read is the HARNESS'S: opcode 8 is entered at the stack's top, its frame
# lies in the stack band the snapshot leaves zero, and no callee runs over those words before they are read — so
# both shores read 0 (the C's 0). On the machine it is whatever the last call at that depth left.
@pytest.mark.parametrize("h_align", (3, 0x7FFF, 0x8000, 0xFFFF))
@pytest.mark.parametrize("style", (SKEW, UNDERLINE))
def test_a_horizontal_alignment_past_right_offsets_by_an_unwritten_word(h_align, style):
    assert screen_changed(run_gtext(gtext_call("Hello", x=160, y=100, h_align=h_align, style=style)))


@pytest.mark.parametrize("v_align", (6, 0x7FFF, 0xFFFF))
@pytest.mark.parametrize("style", (SKEW, UNDERLINE | SKEW))
def test_a_vertical_alignment_past_top_offsets_by_an_unwritten_word(v_align, style):
    assert screen_changed(run_gtext(gtext_call("Hello", x=160, y=100, v_align=v_align, style=style)))


@pytest.mark.parametrize("rotation", OTHER_ROTATIONS)
@pytest.mark.parametrize("font", ("8x16", "thick underline"))
def test_the_underline_of_another_rotation_starts_at_unwritten_words(rotation, font):
    result = run_gtext(gtext_call("Stale", x=10, y=20, rotation=rotation, style=UNDERLINE, font=font))
    assert screen_changed(result)


def test_a_rotation_of_3600_after_a_string_continues_it():
    """The call before sets DESTX/DESTY; one at 3600 then starts from where that one ended — a real sequence,
    each run starting from the machine the one before left (`case.continued`). The first string is OFF A BYTE,
    so it goes through TextBlt, which moves DESTX past each glyph; on a byte the fast path would take it and
    leave DESTX where it started."""
    first = run_gtext(gtext_call("First", x=41, y=60))
    assert first.linea("DESTX") == 41 + len("First") * font_word("8x16", "MAX_CELL_WIDTH")
    second = vdi.function_pokes("VDI_ROM_V_GTEXT", intin=vdi_text.codes("then"), ptsin=(10, 20),
                                workstation_pokes=vdi.dispatched_pokes(onto=continued(first), CHUP=FULL_TURN))
    assert screen_changed(run_gtext(second), first.final)


# ---- the effects --------------------------------------------------------------------------------------------
EFFECTS = {"thicken": THICKEN, "lighten": LIGHTEN, "skew": SKEW, "outline": OUTLINE, "underline": UNDERLINE,
           "bold italic": THICKEN | SKEW, "light underline": LIGHTEN | UNDERLINE, "all": ALL_EFFECTS,
           "high byte only": 0x0100, "every bit": 0xFFFF}


@pytest.mark.parametrize("effect", EFFECTS)
@pytest.mark.parametrize("font", ("6x6", "8x16", "proportional"))
def test_each_effect(font, effect):
    """The low byte's bits are the effects (`btst` on $29f5); a high-byte bit only refuses the fast path."""
    result = run_gtext(gtext_call(HELLO, x=40, y=70, font=font, style=EFFECTS[effect]))
    assert screen_changed(result)
    if not EFFECTS[effect] & SKEW:
        assert (result.linea("L_OFF"), result.linea("R_OFF")) == (0, 0)


@pytest.mark.parametrize("style", (UNDERLINE, UNDERLINE | LIGHTEN, UNDERLINE | OUTLINE))
@pytest.mark.parametrize("rotation", ROTATIONS)
def test_a_three_row_underline_shifts_the_mask_arithmetically(rotation, style):
    """LN_MASK `asr.w`-ed after each row with bit 15 set when bit 0 was — not a rotation, and not a logical
    shift — on top of the rotation $a003 itself makes of it along the row: the lighten mask 0x5555, or solid."""
    result = run_gtext(gtext_call("Under", x=150, y=100, font="thick underline", rotation=rotation, style=style))
    assert result.linea("LN_MASK") != vdi.STALE_WORD and screen_changed(result)


@pytest.mark.parametrize("window", (None, g.WINDOW, g.TIGHT))
@pytest.mark.parametrize("rotation", ROTATIONS)
def test_the_underline_is_clipped_row_by_row(rotation, window):
    """A string laid across the tight window's corner (on screen whichever way it turns — the host image has no
    off-RAM bus to drop a store past $100000 into): each row cut by clip_line, its end points put back so the
    next row steps from the uncut ones — or no clip at all."""
    result = run_gtext(gtext_call("Clip it", x=150, y=70, font="thick underline", rotation=rotation,
                                  style=UNDERLINE, window=window))
    assert screen_changed(result)


@pytest.mark.parametrize("scale", (None, "double"))
@pytest.mark.parametrize("font", ("6x6", "8x8", "8x16", "proportional", "thick underline"))
def test_the_underline_drop(font, scale):
    """1 below the cell, unless a system-face font's bottom is no thicker than its underline (0) — and then -1
    doubled: 8x8 and 6x6 (bottom 1, underline 1), the three-row underline over 8x16's bottom of 2; not the
    proportional face (id 3)."""
    assert screen_changed(run_gtext(gtext_call("Drop", x=60, y=90, font=font, scale=scale, style=UNDERLINE)))


def test_the_doubling_marker_without_scaling_is_no_doubling():
    """DDA_INC still -1 from an earlier doubled size, SCALED since cleared: the drop is 0, not -1."""
    pokes = gtext_call("Drop", x=60, y=90, font="8x8", style=UNDERLINE)
    pokes = merge_pokes(pokes, vdi.dispatched_pokes(onto=pokes, SCALED=0, DDA_INC=0xFFFF))
    assert screen_changed(run_gtext(pokes))


@pytest.mark.parametrize("style", (OUTLINE, OUTLINE | SKEW, OUTLINE | UNDERLINE))
@pytest.mark.parametrize("h_align", (1, 2))
def test_an_outlined_string_aligned(h_align, style):
    """The outline's border comes off the centre once and off the right end twice."""
    assert screen_changed(run_gtext(gtext_call(HELLO, x=200, y=100, h_align=h_align, style=style)))


@pytest.mark.parametrize("v_align", (3, 4))
@pytest.mark.parametrize("style", (0, SKEW))
def test_the_bottom_and_descent_lines_of_a_deep_face(v_align, style):
    """A face whose bottom is below its descent: the two lines part, and the descent's lean is over the bottom."""
    assert screen_changed(run_gtext(gtext_call(HELLO, x=100, y=100, font="deep", v_align=v_align, style=style)))


@pytest.mark.parametrize("string", ("u", "un", "und", "unde", "under"))
@pytest.mark.parametrize("font,rotation", (("thick underline", 0), ("thick underline", QUARTER_TURN), ("proportional", 0)))
def test_a_light_underline_of_each_length(font, rotation, string):
    """$a003 turns LN_MASK along each row, so the mask each row ends on — and whether bit 0 is set when the next
    row shifts it — depends on the row's length: the proportional face's odd lengths leave it set (0x5555 then
    shifts to 0xaaaa, its top bit SET — 0x2aaa by a plain `asr`)."""
    result = run_gtext(gtext_call(string, x=151, y=100, font=font, rotation=rotation, style=UNDERLINE | LIGHTEN))
    assert screen_changed(result)


# (x, y) of an underline that crosses the tight window's left edge, and of one wholly outside it.
@pytest.mark.parametrize("x,y", ((85, 70), (101, 150), (30, 30)))
@pytest.mark.parametrize("rotation", (0, QUARTER_TURN))
def test_the_underline_crossing_and_outside_the_window(x, y, rotation):
    result = run_gtext(gtext_call("Clip it", x=x, y=y, font="thick underline", rotation=rotation, style=UNDERLINE,
                                  window=g.TIGHT))
    assert result.linea("X1") != vdi.STALE_WORD


def test_clipping_off_the_underline_runs_over_the_menu_bar():
    """No clip: an underline above the desktop window's top is drawn all the same."""
    assert screen_changed(run_gtext(gtext_call("Top line", x=101, y=6, window=None, style=UNDERLINE,
                                               font="thick underline")))


# ---- scaling --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("scale", ("double", 24, 11, 30))
@pytest.mark.parametrize("font", ("8x8", "8x16"))
def test_scaled_text_starts_the_accumulator_half_full(font, scale):
    result = run_gtext(gtext_call(HELLO, x=30, y=80, font=font, scale=scale, style=UNDERLINE))
    assert screen_changed(result)
    assert result.linea("DELX") != vdi.STALE_WORD, "scaled text never takes the fast path"


# ---- the fast path ------------------------------------------------------------------------------------------
def took_the_fast_path(result):
    """The loop stores DELX for every glyph; the fast path never does."""
    return result.linea("DELX") == vdi.STALE_WORD


@pytest.mark.parametrize("mode", vdi_text.MODES)
@pytest.mark.parametrize("font", ("8x8", "8x16", "ram 8x8"))
def test_the_fast_path_draws_a_plain_string_on_a_byte(font, mode):
    result = run_gtext(gtext_call(FAST, x=8, y=60, font=font, mode=mode))
    assert took_the_fast_path(result) and screen_changed(result)


REFUSALS = {"off a byte": dict(x=101), "crossing the clip": dict(x=280), "a high style bit": dict(style=0x0100),
            "centred": dict(h_align=1), "turned": dict(rotation=QUARTER_TURN), "scaled": dict(scale=24),
            "6x6 cells": dict(font="6x6"), "not monospaced": dict(font="proportional")}


@pytest.mark.parametrize("refusal", REFUSALS)
def test_the_fast_path_refused_draws_through_textblt(refusal):
    call = {"x": 96, "y": 60, "font": "8x16", **REFUSALS[refusal]}
    result = run_gtext(gtext_call("Refused", **call))
    assert not took_the_fast_path(result) and screen_changed(result)


def test_justified_text_never_takes_the_fast_path():
    """contrl[0] = 11 (the GDP), the gaps staged 0: the refusal word is all ones whatever the string."""
    gaps = merge_pokes(g.gap_pokes("space", STEP_X=0, STEP_Y=0, EXTRA=0), g.gap_pokes("character", STEP_X=0, STEP_Y=0, EXTRA=0))
    pokes = merge_pokes(gtext_call("Justify", x=96, y=60), gaps,
                        {vdi.CONTRL_AT + vdi.CONTRL_OPCODE: vdi.pack_words(g.JUSTIFIED_OPCODE)})
    result = run_gtext(pokes)
    assert not took_the_fast_path(result) and screen_changed(result)


# ---- characters and tables ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("font,string", (("first 32", (0, 31, 32, 65, 255, 256)), ("8x8", (256, 0x7FFF, 0x8000, 0xFFFF)),
                                         ("proportional", (63, 64, 0x1FF))))
def test_a_missing_character_is_drawn_as_a_question_mark(font, string):
    """UNSIGNED bounds: $8000 and $ffff are past the last, not below the first."""
    assert screen_changed(run_gtext(gtext_call(string, x=41, y=60, font=font)))   # off a byte: not the fast path


def test_the_proportional_face_moves_each_glyph_by_its_hor_byte():
    """ONE BYTE A GLYPH of the HOR table — (left, right) pairs to vqt_width, so glyph n takes byte n."""
    assert screen_changed(run_gtext(gtext_call(HELLO, x=40, y=60, font="proportional", h_align=1)))


# The 8x8 over every character 0..$ffff with a HOR table: glyph $8000 indexes the offset table 64 KB BELOW itself
# (ROM words there: a glyph 22,330 wide, cut by the clip) and the HOR table 32 KB below (the staged 0x85 = -123);
# $ffff one entry below both (a glyph 0 wide, the byte staged below the HOR table).
HOR_BELOW = {text.WRAPPED_HOR_TABLE - 1: bytes([0x07]), text.WRAPPED_HOR_TABLE: bytes([0xFD])}


@pytest.mark.parametrize("string", ((0x8000,), (0xFFFF, 65), (0, 0x8000, 66)))
def test_both_tables_are_indexed_sign_extended(string):
    result = run_gtext(gtext_call(string, x=201, y=60, font="wrapping", onto=HOR_BELOW))
    assert result.linea("DELX") != vdi.STALE_WORD, "drawn glyph by glyph, not by the fast path"


# A RAM 8x16 whose TOP (or BOTTOM) is 0, italic, aligned on a line that leans by it: `divu.w` by zero — vector 5 on
# the machine, the idiom's named refusal here.
@pytest.mark.parametrize("line,v_align", (("TOP", 1), ("TOP", 2), ("BOTTOM", 4)))
def test_a_lean_over_a_line_of_0_is_a_zero_divide(line, v_align):
    font = text.rom_header_pokes(RAM_FONT_AT, "8x16", **{line: 0})
    pokes = with_font_at(gtext_call("Lean", x=100, y=100, font="8x16", style=SKEW, v_align=v_align, onto=font), RAM_FONT_AT)
    returncode, stderr, _ = vdi_helpers.refusal_over("vdi_v_gtext", pokes, read_back=False)
    assert returncode == -signal.SIGABRT and "divu.w by zero" in stderr, (returncode, stderr)


# ---- the host's bound on TextBlt's scratch copies ------------------------------------------------------------------
# A bold of thousands of pixels, or a glyph 22,330 wide turned, makes a scratch copy far past the effects buffer: the
# ROM writes it over the VDI's own RAM and runs on in garbage, where the host would run off its image (SIGSEGV /
# SIGBUS before the bound). TextBlt's HOST-ONLY bound names it and stops instead (`text_raster.c`,
# `require_scratch_room`): the pre-pass's copy, a quarter turn's, a half turn's and the scale's, each BEFORE it writes
# past the buffer — so the PTSIN copy after it is still as staged when the host stops. The legitimate copies peak at
# 228 bytes — more than one of the buffer's 204-byte halves, still inside the 532 before the PTSIN copy.
SCRATCH_REFUSED = "TextBlt: a scratch copy past the effects buffer"
PTSIN_COPY = range(vdi.VDI_PTSIN_COPY, vdi.VDI_PTSIN_COPY + vdi.VDI_PTSIN_COPY_BYTES)


def huge_weight_call(weight, **attributes):
    font = text.rom_header_pokes(RAM_FONT_AT, "8x16", THICKEN=weight)
    return with_font_at(gtext_call("Hi", x=101, y=60, font="8x16", onto=font, **attributes), RAM_FONT_AT)


SCRATCH_OVERRUNS = {
    "bold of 21,845 outlined: the pre-pass": lambda: huge_weight_call(0x5555, style=THICKEN | OUTLINE),
    "bold of 1,024 italic, turned": lambda: huge_weight_call(0x400, style=THICKEN | SKEW, rotation=QUARTER_TURN),
    "a glyph 22,330 wide, a quarter turn": lambda: gtext_call((0x8000,), x=201, y=100, font="wrapping", rotation=QUARTER_TURN),
    "a glyph 22,330 wide, a half turn": lambda: gtext_call((0x8000,), x=201, y=100, font="wrapping", rotation=HALF_TURN),
    "a glyph 22,330 wide, doubled: the scale": lambda: gtext_call((0x8000,), x=201, y=100, font="wrapping",
                                                                  scale="double"),
    # ...and enlarged half again: the first source row does not carry, so the first row laid is an ENLARGED one.
    "a glyph 22,330 wide, 8 to 12: the scale": lambda: gtext_call((0x8000,), x=201, y=100, font="wrapping", scale=12),
}


@pytest.mark.parametrize("overrun", SCRATCH_OVERRUNS)
def test_a_scratch_copy_past_the_effects_buffer_is_refused_on_the_host(overrun):
    pokes = SCRATCH_OVERRUNS[overrun]()
    staged = vdi.make_image(pokes)
    returncode, stderr, left = vdi_helpers.refusal_over("vdi_v_gtext", pokes)
    assert returncode == -signal.SIGABRT and SCRATCH_REFUSED in stderr, (returncode, stderr)
    overwritten = [at for at in PTSIN_COPY if left[at] != staged[at]]
    assert not overwritten, f"the copy ran over the PTSIN copy from ${overwritten[0]:x} before the host stopped"


# ---- the clip, the modes, the colours ---------------------------------------------------------------------------
# (rotation, x, y) laying the string across the tight window's left, right, top and bottom edges, and a corner.
EDGE_CROSSINGS = ((0, 90, 60), (0, 150, 60), (0, 120, 58), (0, 120, 90), (0, 60, 58),
                  (QUARTER_TURN, 104, 70), (QUARTER_TURN, 175, 70), (QUARTER_TURN, 130, 60), (QUARTER_TURN, 130, 120),
                  (QUARTER_TURN, 175, 120))


@pytest.mark.parametrize("rotation,x,y", EDGE_CROSSINGS)
def test_a_string_crossing_each_edge_of_the_clip(rotation, x, y):
    assert screen_changed(run_gtext(gtext_call("Across the edge", x=x, y=y, window=g.TIGHT, rotation=rotation,
                                               style=THICKEN)))


def test_clipping_off_draws_past_the_window():
    assert screen_changed(run_gtext(gtext_call("Anywhere", x=250, y=5, window=None, style=OUTLINE)))


@pytest.mark.parametrize("colour", vdi_raster.COLOURS + (0xFFF6,))
@pytest.mark.parametrize("mode", vdi_text.MODES)
def test_every_write_mode_and_colour(mode, colour):
    result = run_gtext(gtext_call("Mode", x=101, y=60, mode=mode, colour=colour, style=UNDERLINE))
    assert result.linea("TEXT_FG") == colour


@pytest.mark.parametrize("x", (40, 41))
def test_on_a_virtual_workstation_its_own_text_colour(x):
    """On a byte through the fast path, off it through TextBlt: the colour reaches the screen both ways."""
    result = run_gtext(gtext_call(HELLO, x=x, y=60, colour=0b0110, virtual=7))
    assert result.linea("TEXT_FG") == 0b0110 and screen_changed(result)


# ---- the order of reads and stores -------------------------------------------------------------------------------
def test_the_characters_are_read_after_the_string_is_measured():
    """intin laid over the dispatcher's alignment copies and the extent words: vqt_extent sums the four words
    (the width building up under its own reads), and v_gtext then draws them AS THEY ARE AFTER — H_ALIGN,
    V_ALIGN, the width and the height."""
    pokes = merge_pokes(gtext_call("abcd", x=160, y=100, font="wrapping", h_align=1),
                        vdi.linea_pokes(INTIN=vdi.VDI_TEXT_H_ALIGN))
    result = run_gtext(pokes)
    assert screen_changed(result)
    assert vdi.STALE_WORD not in result.words(vdi.VDI_EXTENT_SCRATCH, 2), "the glyphs drawn must not be the stale words"


def test_ptsin_y_is_read_after_destx_is_stored():
    """ptsin laid one word below DESTX: ptsin[0] is SOURCEY, and ptsin[1] IS DESTX — read after the store, so
    the string's y is its own x."""
    pokes = merge_pokes(gtext_call("Order", font="first 32"), vdi.linea_pokes(PTSIN=vdi.LINEA_DESTX - vdi.WORD_BYTES,
                                                                            SOURCEY=90))
    result = run_gtext(pokes)
    assert screen_changed(result)


# contrl laid over a staged 8x8 so that contrl[2] IS its TOP: the call's own count is its ASCENT (contrl[3]), and
# centring stores contrl[2] = 4 (vqt_extent) and then 0 — so every read of TOP after the measure sees 0.
TOP_UNDER_CONTRL = text.header_at(8)
TOP_OVERLAP_CONTRL = TOP_UNDER_CONTRL + vdi.FONT_TOP - vdi.CONTRL_N_PTSOUT


def test_the_font_is_read_after_contrl_2_is_put_back():
    font = text.rom_header_pokes(TOP_UNDER_CONTRL, "8x8")
    work = vdi.dispatched_pokes(onto=g.machine(onto=font), CUR_FONT=TOP_UNDER_CONTRL, H_ALIGN=1,
                                V_ALIGN=0, STYLE=UNDERLINE)
    pokes = merge_pokes(vdi.function_pokes("VDI_ROM_V_GTEXT", intin=vdi_text.codes("Topless"), ptsin=(160, 100),
                                           workstation_pokes=work),
                        vdi.linea_pokes(CONTRL=TOP_OVERLAP_CONTRL))
    result = run_gtext(pokes)
    assert result.word(TOP_UNDER_CONTRL + vdi.FONT_TOP) == 0
    assert screen_changed(result)


# A "font" laid over the Line-A variables so that its TOP IS DESTX ($29be: WRT_MODE is its id, SOURCEX/SOURCEY its
# first and last characters — staged 0 and $ffff, so every character is in range — and SCRTCHP its offset table).
# The string is laid below the tight window, so each TextBlt returns at its trivial clip; the underline is not
# clipped away from memory — X1/Y1 end where its rows stepped from.
TOP_ON_DESTX = vdi.LINEA_DESTX - vdi.FONT_TOP


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_the_font_lines_are_read_after_destx_is_stored(rotation):
    """Upright, and turned a quarter or a half, the ROM reads the font's TOP for the underline (and the half turn
    for its height) AFTER it stores DESTX ($fcda34, $fcda62, $fcdab4) — here, the x it has just stored. At 270 it
    reads TOP before the store, to place DESTX by it."""
    base = gtext_call("A", x=150, y=20, style=UNDERLINE, window=g.TIGHT, rotation=rotation)
    pokes = merge_pokes(with_font_at(base, TOP_ON_DESTX), vdi.linea_pokes(SOURCEX=0, SOURCEY=0xFFFF))
    result = run_gtext(pokes)
    assert result.linea("X1") != vdi.STALE_WORD


# A RAM 8x8 whose ADDRESS's low word is its string's length: contrl laid two words below CUR_FONT, so contrl[2..3]
# ARE CUR_FONT and contrl[3] the count. Centring's measure stores contrl[2] = 4 and then 0 — CUR_FONT becomes
# $00000010 between v_gtext's entry and its first glyph.
COUNT_FONT_AT = staging.HIGH_BANDS.claim(0xB0010, vdi.FONT_HEADER_BYTES, "test_vdi_gtext.py: a font whose address is a count")
COUNT_FONT_STRING = "ABCDEFGHIJKLMNOP"
assert len(COUNT_FONT_STRING) == COUNT_FONT_AT & 0xFFFF


def test_the_count_font_is_dead_in_the_snapshot():
    assert BASE_IMAGE[COUNT_FONT_AT:COUNT_FONT_AT + vdi.FONT_HEADER_BYTES] == bytes(vdi.FONT_HEADER_BYTES)




def test_the_first_glyph_is_drawn_in_the_font_loaded_at_entry():
    """The ROM loads CUR_FONT into A5 at entry ($fcd76e) and draws the FIRST glyph with it; it reads CUR_FONT again
    only after each TextBlt ($fcdc38). Here that re-read finds the $10 the measure left, and every later glyph is
    drawn out of the "font" at $10 — the first one alone out of the real one."""
    font = text.rom_header_pokes(COUNT_FONT_AT, "8x8")
    pokes = with_font_at(gtext_call(COUNT_FONT_STRING, x=161, y=100, font="8x8", h_align=1, onto=font), COUNT_FONT_AT)
    result = run_gtext(merge_pokes(pokes, vdi.linea_pokes(CONTRL=vdi.LINEA_CUR_FONT - 2 * vdi.WORD_BYTES)))
    assert result.linea("CUR_FONT") == COUNT_FONT_AT & 0xFFFF
    assert screen_changed(result)


# A RAM 8x16 with italic offsets of $2000: a font line times an offset passes $ffff, so the lean's `mulu.w` keeps
# only the product's LOW word — no real font's offsets reach it. The string is laid wholly above the tight window,
# so every TextBlt returns at its trivial clip before it makes a copy of a glyph leaning 8,192 pixels.
WIDE_LEAN_OFFSET = 0x2000


@pytest.mark.parametrize("v_align", (1, 2, 4))
def test_the_lean_keeps_the_low_word_of_its_product(v_align):
    font = text.rom_header_pokes(RAM_FONT_AT, "8x16", LEFT_OFFSET=WIDE_LEAN_OFFSET, RIGHT_OFFSET=WIDE_LEAN_OFFSET)
    pokes = with_font_at(gtext_call("Lean", x=100, y=5, font="8x16", style=SKEW, v_align=v_align, window=g.TIGHT,
                                    onto=font), RAM_FONT_AT)
    result = run_gtext(pokes)
    assert result.linea("DESTX") != 100


# ---- justified text's gaps, staged directly -------------------------------------------------------------------------
def justified_call(string, space, character, **attributes):
    """v_gtext as d_justified calls it: contrl[0] the GDP's, the two gap records staged."""
    return merge_pokes(gtext_call(string, **attributes), g.gap_pokes("space", **space), g.gap_pokes("character", **character),
                       {vdi.CONTRL_AT + vdi.CONTRL_OPCODE: vdi.pack_words(g.JUSTIFIED_OPCODE)})


@pytest.mark.parametrize("rotation", (0, QUARTER_TURN))
def test_justified_gaps_are_taken_and_their_extra_pixels_counted_down(rotation):
    """Three extra pixels for the character gaps (spent on the first three), five for the word gaps — more than
    the string has spaces, so some are left."""
    result = run_gtext(justified_call("a b c d e", dict(STEP_X=4, STEP_Y=-1, EXTRA=5, EXTRA_X=1, EXTRA_Y=2),
                                      dict(STEP_X=1, STEP_Y=1, EXTRA=3, EXTRA_X=-1, EXTRA_Y=0), x=20, y=60,
                                      rotation=rotation))
    assert g.gap(result, "character")["EXTRA"] == 0
    assert g.gap(result, "space")["EXTRA"] == 1


def test_justified_centring_takes_the_width_it_was_given():
    """Justified text is not measured: the width is whatever d_justified left in the scratch word."""
    pokes = merge_pokes(justified_call("Given", dict(STEP_X=0, STEP_Y=0, EXTRA=0), dict(STEP_X=0, STEP_Y=0, EXTRA=0),
                                       x=160, y=60, h_align=1),
                        {vdi.VDI_EXTENT_SCRATCH: vdi.pack_words(90)})
    result = run_gtext(pokes)
    assert result.word(vdi.VDI_RESULT) == 0 and result.word(vdi.VDI_EXTENT_SCRATCH) == 90


def test_the_space_test_reads_the_character_again_after_the_gap():
    """intin laid on the character gap's count: glyph 33 ('!') drawn, the count taken down to 32 by that gap —
    and read again as the character, now a SPACE, so the word gap is taken too."""
    pokes = merge_pokes(justified_call("x", dict(STEP_X=7, STEP_Y=3, EXTRA=0), dict(STEP_X=2, STEP_Y=0, EXTRA=33,
                                                                                  EXTRA_X=1, EXTRA_Y=1), x=40, y=60),
                        vdi.linea_pokes(INTIN=g.GAPS["character"] + 2 * vdi.WORD_BYTES))
    result = run_gtext(pokes)
    assert g.gap(result, "character")["EXTRA"] == g.SPACE
    assert screen_changed(result)


# ==== Tier 3: the worst realistic rows ======================================================================
vdi.register("vdi_v_gtext, twelve characters through TextBlt", addrs.VDI_ROM_V_GTEXT, gtext_call(HELLO, x=101, y=60))
vdi.register("vdi_v_gtext, thirty-eight characters, the fast path", addrs.VDI_ROM_V_GTEXT, gtext_call(FAST, x=8, y=60))
vdi.register("vdi_v_gtext, one character, centred, underlined, clipped", addrs.VDI_ROM_V_GTEXT,
             gtext_call("A", x=160, y=100, h_align=1, v_align=1, style=UNDERLINE | SKEW))
vdi.register("vdi_v_gtext, turned, every effect, three-row underline", addrs.VDI_ROM_V_GTEXT,
             gtext_call("Turned", x=150, y=100, font="thick underline", rotation=QUARTER_TURN, style=ALL_EFFECTS, h_align=2))
vdi.register("vdi_v_gtext, no characters", addrs.VDI_ROM_V_GTEXT, gtext_call(""))
# ...and where v_gtext's own loop is the cost: every glyph outside the window, so TextBlt returns at its trivial
# clip — a string scrolled out of view, in a proportional face with a HOR table.
vdi.register("vdi_v_gtext, forty characters clipped away, proportional", addrs.VDI_ROM_V_GTEXT,
             gtext_call(FORTY, x=10, y=150, font="proportional", window=g.TIGHT, h_align=1))
# ...and ninety characters the font does not have, each drawn as '?' — the bounds test's longest path — clipped away.
MISSING_NINETY = tuple(range(1, 31)) * 3
vdi.register("vdi_v_gtext, ninety missing characters clipped away", addrs.VDI_ROM_V_GTEXT,
             gtext_call(MISSING_NINETY, x=11, y=150, font="first 32", window=g.TIGHT))
