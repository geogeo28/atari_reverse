"""$a008 TextBlt ($fcee54) and vector 9's CPU body $fd1df6: `src/vdi/text_raster.c`.

    $fcee54  movem.l a5-a6,-(sp) / lea $299a,a6 / jmp (LINEA_VECTOR_TEXTBLT)
    $fd1df6  link a5,#-84: the size (scaled, effects, turned), a trivial clip, the scale pass ($fd2b54),
             the pre-pass into the scratch buffer ($fd1f6e) with its outline ($fd2c9a), the rotation
             ($fd29da), the clip, and the blit ($fd2268) — per plane, the row loop the width needs
             ($fd2506 one word, $fd2534 two, $fd2580 / $fd261c a run shifted left / right) through the
             effect fragments ($fd2784.. thicken, $fd28b2.. lighten, $fd28de skew) to the op

Every case is a glyph of one of the three ROM fonts, staged as v_gtext stages it (`vdi_text`), drawn over
a canvas whose every plane differs (`vdi_raster.CANVAS`) with a STALE scratch buffer, and compared whole:
the screen, the scratch buffer, and the Line-A variables TextBlt moves on (DESTX/DESTY), leaves behind
(SOURCEX/SOURCEY after a pre-pass, XACC_DDA) and restores (DELX/DELY, STYLE, WRT_MODE, SKEWMASK).

THE MUTATION SWEEP of `src/vdi/text_raster.c` (this battery and `test_vdi_text_raster_fast.py`, strict
classifier — README, "Mutation sweeps"): 224 mutants, 203 KILLED, 3 ABNORMAL, 18 SURVIVED. ABNORMAL, caught by
the C's own halts: lighten's middle fragment jumping on to the EDGE's op, the op index's high byte dropped, and
the middle words ending at the masked slot — each reaches an op slot that is not its chain's, which halts.
SURVIVED:
  * THICKEN's one- and two-word fragment ($fd2784): the edge compare's equal case, the spill cleared, the
    glyph cut to the edge, the room shifted, the glyph cut to the room, the spill cut to the room — EQUIVALENT
    by the room arithmetic: the room is the mask widened LEFT by the weight, so the glyph (already cut to its
    mask) never has a bit outside it, a spill bit it would drop smears past the right mask, and the edge
    equals the right mask only at WEIGHT 16, where both branches cut the same (584 probe shapes agree);
  * THICKEN's edge fragment's last cut to the mask: the masked op drops those bits anyway — EQUIVALENT;
  * the right loop's first long taking 0 for the last row's high word, and the multi-word loops' pairs
    taking 0 for the word before: CARRY_MASK keeps only the new word's bits of each — EQUIVALENT;
  * the per-plane thicken spill cleared by the effects: every multi-word row clears it on the way out; the
    first plane's first row reads the C frame's word, which the host stack left 0 — UNKILLABLE on the host;
  * the scale pass's XACC_DDA store (the advance stores it again), the quarter turn's scaled-width swap (a
    turned glyph reads the height), `|=` for `^=` on a bit set once, the clip's `>` as `>=` (subtracts 0),
    the WRT_MODE and SKEWMASK restores (the pre-pass restores the mode itself; nothing writes SKEWMASK), and
    `find_op`'s first guess (it only orders the search) — EQUIVALENT.
"""
import pytest

import vdi
import vdi_raster
import vdi_text
from case import continued, merge_pokes
from vdi_text import LIGHTEN, OUTLINE, SKEW, THICKEN, UNDERLINE, run_textblt, textblt_pokes

FONTS = tuple(vdi_text.FONTS)
# Destination x's putting the glyph's first pixel at column 0, between, and at 15 of its word — so the
# row fits one word, straddles two, and (8x16, a glyph eight wide) runs to a word's last pixel.
XS = (96, 101, 104, 111)
COLOURS = vdi_raster.COLOURS
EFFECTS = {"thicken": THICKEN, "lighten": LIGHTEN, "skew": SKEW, "outline": OUTLINE, "underline": UNDERLINE,
           "bold italic": THICKEN | SKEW, "bold light": THICKEN | LIGHTEN, "light italic": LIGHTEN | SKEW,
           "outlined bold": OUTLINE | THICKEN, "outlined italic": OUTLINE | SKEW, "all": THICKEN | LIGHTEN | SKEW | OUTLINE}


@pytest.mark.parametrize("x", XS)
@pytest.mark.parametrize("font", FONTS)
@pytest.mark.parametrize("mode", vdi_text.MODES)
def test_a_glyph_in_every_vdi_mode_and_font(x, font, mode):
    run_textblt(textblt_pokes(font, ord("g"), x=x, mode=mode))


@pytest.mark.parametrize("mode", vdi_text.BITBLT_MODES)
@pytest.mark.parametrize("colour,background", ((0b0101, 0b1010), (0b0011, 0b0110)))
def test_the_bitblt_write_modes(mode, colour, background):
    """WRT_MODE 4..19: the op by the plane's (colour, background) bits — every pair reached across the planes."""
    run_textblt(textblt_pokes("8x16", ord("W"), x=101, mode=mode, colour=colour, background=background))


@pytest.mark.parametrize("colour", COLOURS)
@pytest.mark.parametrize("mode", vdi_text.MODES)
def test_the_vdi_modes_ignore_the_background(colour, mode):
    """The claim in pixels, besides the differential: modes 0..3 index the op table's pairs that differ only
    in the background bit to the SAME op ($fd23b2), so REPLACE draws the glyph's clear pixels in colour 0
    whatever TEXT_BG holds."""
    screens = set()
    for background in COLOURS:
        result = run_textblt(textblt_pokes("8x8", ord("M"), x=103, mode=mode, colour=colour, background=background))
        screens.add(result.after(vdi.SCREEN.base, vdi.SCREEN.bytes))
    assert len(screens) == 1


@pytest.mark.parametrize("effect", EFFECTS.values(), ids=EFFECTS.keys())
@pytest.mark.parametrize("x", XS)
@pytest.mark.parametrize("font", FONTS)
def test_every_effect_alone_and_combined(effect, x, font):
    run_textblt(textblt_pokes(font, ord("R"), x=x, style=effect, mode="transparent"))


@pytest.mark.parametrize("effect", EFFECTS.values(), ids=EFFECTS.keys())
@pytest.mark.parametrize("mode", vdi_text.MODES)
def test_effects_in_every_mode(effect, mode):
    run_textblt(textblt_pokes("8x16", ord("&"), x=109, style=effect, mode=mode))


@pytest.mark.parametrize("effect", (SKEW, OUTLINE, LIGHTEN), ids=("skew", "outline", "lighten"))
@pytest.mark.parametrize("chup", (0, 900))
def test_a_stale_weight_without_the_bold_bit(effect, chup):
    """v_gtext stores WEIGHT only for bold text, so a plain glyph after a bold one finds the old weight
    there. Nothing but the bold bit makes TextBlt read it — the pre-pass's `btst #0` ($fd1fa8) included."""
    run_textblt(textblt_pokes("8x16", ord("S"), x=100, y=90, style=effect, chup=chup, window=vdi_text.TIGHT,
                              extra=vdi.linea_pokes(WEIGHT=3)))


@pytest.mark.parametrize("mono", (0, vdi.FONT_FLAG_MONOSPACE_MASK))
@pytest.mark.parametrize("weight", (0, 1, 3))
@pytest.mark.parametrize("chup", (0, 900))
def test_the_weight_widens_a_proportional_font_only(mono, weight, chup):
    """Thicken: a WEIGHT of 0 clears the bit for the call ($fd1e8a) — and STYLE comes back set — and the
    advance counts the weight only when MONO_STATUS is 0. Turned, the cleared bit is what spares the
    glyph the pre-pass."""
    run_textblt(textblt_pokes("8x16", ord("B"), x=100, y=90, style=THICKEN, chup=chup,
                              extra=vdi.linea_pokes(WEIGHT=weight, MONO_STATUS=mono)))


# ---- the row loops: a DELX spanning several of the form's characters -------------------------------------------
# (x, SOURCEX offset into the glyph, width): every loop — one word, two, a run shifted right, a run shifted
# left — and the two-word row whose source needs a third word ($fd22f8).
RUNS = {"one word": (96, 0, 8), "two words": (106, 0, 8), "two words, source past 32": (101, 5, 23),
        "right, wide": (99, 2, 40), "left, wide": (97, 6, 40), "right, long": (100, 0, 70),
        "left, long": (96, 7, 70), "exactly two words": (96, 0, 32), "ends on a word": (100, 4, 28),
        "right, from a word's last pixel": (111, 2, 40), "left, from a word's last pixel": (111, 15, 40),
        "two words, source exactly 32": (101, 1, 23)}


def run_pokes(run, **kwargs):
    x, into, width = run
    source_x, _width = vdi_text.glyph("8x16", ord("a"))
    return textblt_pokes("8x16", ord("a"), x=x, width=width,
                         extra=merge_pokes(vdi.linea_pokes(SOURCEX=source_x + into), kwargs.pop("extra", None)),
                         **kwargs)


@pytest.mark.parametrize("run", RUNS.values(), ids=RUNS.keys())
@pytest.mark.parametrize("mode", [*vdi_text.MODES, 7, 12])
def test_every_row_loop(run, mode):
    run_textblt(run_pokes(run, mode=mode, colour=0b1001))


@pytest.mark.parametrize("run", RUNS.values(), ids=RUNS.keys())
@pytest.mark.parametrize("effect", EFFECTS.values(), ids=EFFECTS.keys())
def test_every_row_loop_with_every_effect(run, effect):
    """The multi-word loops' own fragments — thicken's edge and middle, lighten's — and the SKEW STEP
    between rows ($fd2944) that turns one multi-word loop into the other."""
    run_textblt(run_pokes(run, style=effect, mode="replace", colour=0b0110))


@pytest.mark.parametrize("weight", (1, 3))
def test_a_thickened_first_word_is_cut_to_its_mask_before_the_smear(weight):
    """$fd2784 `and.w d2,d1`: a glyph taken from INSIDE a character — the form's pixels just left of SOURCEX
    set — would smear them right into the row; the one-word fragment drops them first."""
    source_x, _width = vdi_text.glyph("8x16", ord("W"))
    run_textblt(textblt_pokes("8x16", ord("W"), x=97, width=6, style=THICKEN,
                              extra=vdi.linea_pokes(SOURCEX=source_x + 2, WEIGHT=weight, MONO_STATUS=0)))


@pytest.mark.parametrize("weight", (1, 15, 16, 17))
@pytest.mark.parametrize("run", ("right, wide", "left, wide", "two words", "one word"))
@pytest.mark.parametrize("style", (THICKEN, THICKEN | SKEW), ids=("bold", "bold italic"))
def test_a_line_a_caller_s_weight(weight, run, style):
    """WEIGHT is the caller's: a whole word of it (16) makes the thickening's edge mask the right mask
    itself ($fd232e `cmp.w d2,d4` / `bcs` — the count's equal case, and the recount's at $fd2872)."""
    run_textblt(run_pokes(RUNS[run], style=style, extra=vdi.linea_pokes(WEIGHT=weight, MONO_STATUS=0)))


@pytest.mark.parametrize("skew_mask", (0x5555, 0xAAAA, 0x8421, 0xFFFF, 0x0001))
@pytest.mark.parametrize("run", RUNS.values(), ids=RUNS.keys())
def test_the_skew_steps_by_skewmask(skew_mask, run):
    run_textblt(run_pokes(run, style=SKEW | THICKEN, extra=vdi.linea_pokes(SKEWMASK=skew_mask, L_OFF=2, R_OFF=5)))


@pytest.mark.parametrize("stray", vdi_text.stray_modes(), ids=str)
@pytest.mark.parametrize("run", ("one word", "two words", "right, wide"))
def test_a_write_mode_past_19_that_lands_on_an_op(stray, run):
    """WRT_MODE past 19 index the op tables' neighbours — the byte table runs on into the ROM's easter egg,
    "Dave StaUgas loves Bea Hablig" — and past 63 the index's high byte carries it further still
    (`vdi_text.stray_modes`). Where the index is even and names ops in both fragment tables, a one-plane
    glyph in the colour and background bits that select it is drawn with that op."""
    mode, colour, background = stray
    run_textblt(run_pokes(RUNS[run], mode=mode, colour=colour, background=background,
                          extra=vdi_raster.geometry_pokes(vdi_raster.HIGH)))


@pytest.mark.parametrize("stray", vdi_text.masked_only_modes(), ids=str)
def test_a_write_mode_past_19_whose_masked_slot_alone_is_an_op(stray):
    """A one- or two-word row runs only the MASKED slot, so where that alone names an op the row draws —
    the whole slot, garbage, is never reached (a wider row would, and halts: below)."""
    mode, colour, background = stray
    run_textblt(run_pokes(RUNS["two words"], mode=mode, colour=colour, background=background,
                          extra=vdi_raster.geometry_pokes(vdi_raster.HIGH)))


# Write modes whose op index the ROM cannot draw with — (mode, colour bit, background bit, STYLE, row loop):
# an ODD index, which `movea.w (pc,d0.w)` takes an address error on; and slots naming an EFFECT fragment,
# which the ROM runs over a frame it never set — mode 44 with its own LIGHTEN spins for ever, the effect's
# `_next` being the slot itself. The C halts on each, and must not hang.
UNDRAWABLE = {
    "odd index, mode 79": ((79, 0, 1), 0, "one word", "odd op index"),
    "odd index, mode 20": ((20, 1, 1), 0, "one word", "odd op index"),
    "masked slot lighten's edge, mode 44": ((44, 0, 1), 0, "one word", "slot naming no op"),
    "...under LIGHTEN, which spins the ROM": ((44, 0, 1), LIGHTEN, "one word", "slot naming no op"),
    "masked slot lighten's first, mode 50": ((50, 0, 1), 0, "two words", "slot naming no op"),
    "masked slot thicken's middle, mode 65": ((65, 0, 0), THICKEN, "one word", "slot naming no op"),
    "masked slot thicken's edge, mode 65": ((65, 1, 0), 0, "right, wide", "slot naming no op"),
    "whole slot, a masked-only mode on a wide row": ((20, 0, 0), 0, "right, wide", "slot naming no op"),
}
UNDRAWABLE_SLOTS = {"mode 44": ((44, 0, 1), "TEXT_FRAGMENT_LIGHTEN_EDGE"), "mode 50": ((50, 0, 1), "TEXT_FRAGMENT_LIGHTEN_FIRST"),
                    "mode 65": ((65, 0, 0), "TEXT_FRAGMENT_THICKEN_MIDDLE"), "mode 65, colour": ((65, 1, 0), "TEXT_FRAGMENT_THICKEN_EDGE")}


@pytest.mark.parametrize("slot", UNDRAWABLE_SLOTS.values(), ids=UNDRAWABLE_SLOTS.keys())
def test_the_undrawable_modes_name_the_effects_they_are_said_to(slot):
    stray, fragment = slot
    assert vdi_text.op_slots(*stray)[2] == vdi_text.HEADER[fragment]


@pytest.mark.parametrize("undrawable", UNDRAWABLE.values(), ids=UNDRAWABLE.keys())
def test_a_write_mode_the_rom_cannot_draw_with_halts(undrawable):
    (mode, colour, background), style, run, message = undrawable
    returncode, stderr = vdi_text.refusal(run_pokes(RUNS[run], mode=mode, colour=colour, background=background, style=style,
                                                    extra=vdi_raster.geometry_pokes(vdi_raster.HIGH)))
    assert returncode != 0 and message in stderr, stderr[-400:]


# ---- rotation and scaling -------------------------------------------------------------------------------------

@pytest.mark.parametrize("chup", (*vdi_text.ROTATIONS[1:], 450))
@pytest.mark.parametrize("effect", (0, *EFFECTS.values()))
@pytest.mark.parametrize("font,character", (*((font, ord("F")) for font in FONTS), ("6x6", ord("E"))),
                         ids=(*FONTS, "6x6 across a word"))
def test_rotation(chup, effect, font, character):
    """A quarter or half turn through the scratch buffer (and the pre-pass for any effect); 450 is taken as
    a quarter turn that moves nothing ($fd1ed2). The 6x6 'E' starts at bit 14 of its form word: unstyled,
    its half turn's rows are a word longer for it ($fd2af0)."""
    run_textblt(textblt_pokes(font, character, x=150, y=120, chup=chup, style=effect))


@pytest.mark.parametrize("chup", vdi_text.ROTATIONS[1:])
@pytest.mark.parametrize("source_y", (3, 9))
def test_a_turned_line_a_rectangle_below_the_form_s_first_row(chup, source_y):
    """A Line-A caller's SOURCEY: the quarter turn at 270 degrees starts at it, and the one at 90 and the
    half turn do not read it at all ($fd2a1e, $fd2aec) — they start at the form's first row."""
    run_textblt(textblt_pokes("8x16", ord("P"), x=150, y=120, chup=chup,
                              extra=vdi.linea_pokes(SOURCEY=source_y, DELY=16 - source_y)))


@pytest.mark.parametrize("requested", (4, 7, 12, 20, 24, 31, 32, 40))
@pytest.mark.parametrize("chup", vdi_text.ROTATIONS)
def test_scaling(requested, chup):
    """8x16 scaled down (4..12), up by a fraction (20..31) and doubled (32, 40): the rows through act_siz,
    the width through the DDA, and the scale pass into the scratch buffer."""
    run_textblt(textblt_pokes("8x16", ord("Q"), x=140, y=110, chup=chup, scale=requested))


@pytest.mark.parametrize("requested", (3, 4, 7, 9, 11, 12, 20))
@pytest.mark.parametrize("font,character", (("6x6", ord("E")), ("8x8", ord("y"))), ids=("6x6", "8x8"))
@pytest.mark.parametrize("chup", vdi_text.ROTATIONS)
def test_scaling_the_smaller_fonts(requested, font, character, chup):
    """The 6x6 system font's 'E' runs from bit 14 of its form word into the next ($fd2c2e `ror.w d3` / `bcc`
    past the load): the scale pass reads a second source word — and the half turn's row is a word longer
    for the bit it starts at ($fd2af0)."""
    run_textblt(textblt_pokes(font, character, x=140, y=110, chup=chup, scale=requested))


@pytest.mark.parametrize("requested", (10, 20, 24))
def test_a_scaled_string_carries_xacc_dda(requested):
    """v_gtext starts XACC_DDA half full for the string; each glyph leaves it where its width's DDA ended,
    and the next glyph's rows are scaled across from there ($fd2c28 `move.w 64(a6),d7`)."""
    result = run_textblt(textblt_pokes("8x16", ord("W"), x=40, y=110, scale=requested))
    for character in b"ide":
        source_x, width = vdi_text.glyph("8x16", character)
        result = run_textblt(merge_pokes(continued(result), vdi.linea_pokes(SOURCEX=source_x, DELX=width)))


@pytest.mark.parametrize("accumulator", (0, 0x4000, 0xC000, 0xFFFF))
@pytest.mark.parametrize("source_y", (0, 5))
@pytest.mark.parametrize("requested", (10, 24))
def test_a_line_a_caller_s_accumulator_and_rectangle(accumulator, source_y, requested):
    """XACC_DDA and SOURCEY are the caller's: the scale pass starts each row's DDA at the one and its rows
    at the other ($fd2b6a `mulu.w -12(a5),d0`)."""
    run_textblt(textblt_pokes("8x16", ord("M"), x=140, y=110, scale=requested,
                              extra=vdi.linea_pokes(XACC_DDA=accumulator, SOURCEY=source_y, DELY=16 - source_y)))


@pytest.mark.parametrize("effect", EFFECTS.values(), ids=EFFECTS.keys())
@pytest.mark.parametrize("requested", (10, 24, 32))
@pytest.mark.parametrize("chup", (0, 900))
def test_scaling_with_effects(effect, requested, chup):
    """Scaled, pre-passed and turned, the glyph goes through the scratch buffer three times: the first
    half, the second, and the first again ($fd2c7c's toggle)."""
    run_textblt(textblt_pokes("8x16", ord("Z"), x=141, y=110, style=effect, scale=requested, chup=chup))


# ---- clipping ------------------------------------------------------------------------------------------------
# The tight window (97, 51)..(170, 80), and a glyph cut by each edge, touching each from inside and missing
# it outside — the trivial test ($fd1ed4) and the clip of the final blit ($fd20b8).
PLACES = {"inside": (120, 60), "cut left": (93, 60), "cut right": (166, 60), "cut top": (120, 45),
          "cut bottom": (120, 72), "cut corner": (94, 47), "touch left": (97, 60), "touch right": (163, 60),
          "touch top": (120, 51), "touch bottom": (120, 65), "left of it": (80, 60), "right of it": (171, 60),
          "above it": (120, 30), "below it": (120, 81), "ending on ymin": (120, 35), "ending above ymin": (120, 34),
          "ending on xmin": (89, 60), "ending left of xmin": (88, 60)}


@pytest.mark.parametrize("place", PLACES.values(), ids=PLACES.keys())
@pytest.mark.parametrize("effect", (0, SKEW, OUTLINE | THICKEN, LIGHTEN))
def test_clipping_each_edge(place, effect):
    x, y = place
    run_textblt(textblt_pokes("8x16", ord("H"), x=x, y=y, style=effect, window=vdi_text.TIGHT))


@pytest.mark.parametrize("place", PLACES.values(), ids=PLACES.keys())
@pytest.mark.parametrize("chup", vdi_text.ROTATIONS[1:])
def test_clipping_a_turned_glyph(place, chup):
    x, y = place
    run_textblt(textblt_pokes("8x16", ord("L"), x=x, y=y, chup=chup, window=vdi_text.TIGHT))


@pytest.mark.parametrize("place", ("left of it", "cut left", "inside"))
def test_a_scaled_glyph_the_clip_refuses_still_moves_xacc_dda(place):
    """Refused before the scale pass, the glyph still leaves XACC_DDA where its width's DDA ended — the
    exit's store ($fd2204) is then the only one. (21 rows from 16: eight columns of an increment of $5000
    do not come back round to where they started, as a multiple of $2000 would.)"""
    x, y = PLACES[place]
    run_textblt(textblt_pokes("8x16", ord("V"), x=x, y=y, scale=21, window=vdi_text.TIGHT))


def test_clip_off_draws_past_the_window():
    run_textblt(textblt_pokes("8x16", ord("H"), x=80, y=30, window=None))


# ---- other screens, and the ROM's group table ------------------------------------------------------------------

@pytest.mark.parametrize("shape", (vdi_raster.MEDIUM, vdi_raster.HIGH), ids=("medium", "high"))
@pytest.mark.parametrize("effect", (0, THICKEN | SKEW))
@pytest.mark.parametrize("mode", vdi_text.MODES)
def test_fewer_planes(shape, effect, mode):
    run_textblt(textblt_pokes("8x8", ord("e"), x=105, style=effect, mode=mode, colour=0b01,
                              extra=vdi_raster.geometry_pokes(shape)))


def test_three_planes_step_zero_bytes_a_group():
    """TEXT_GROUP_BYTES_TABLE holds 0 for three planes ($fd215c): each plane's second word is its first."""
    run_textblt(textblt_pokes("8x16", ord("K"), x=109, extra=vdi.linea_pokes(PLANES=3)))


@pytest.mark.parametrize("skew", vdi_raster.WIDTH_SKEWS)
def test_rows_are_placed_by_bytes_lin_and_stepped_by_width(skew):
    run_textblt(textblt_pokes("8x16", ord("N"), x=101, extra=vdi_raster.width_skew_pokes(skew)))


# ---- a string: each glyph where the last one's advance put it ----------------------------------------------------

@pytest.mark.parametrize("chup", vdi_text.ROTATIONS)
@pytest.mark.parametrize("style", (0, THICKEN | SKEW, OUTLINE))
def test_a_string_advances_glyph_by_glyph(chup, style):
    """DESTX (or DESTY) moved past each glyph, and the next glyph drawn there — `case.continued`."""
    result = run_textblt(textblt_pokes("8x16", ord("T"), x=150, y=100, chup=chup, style=style))
    for character in b"ext":
        source_x, width = vdi_text.glyph("8x16", character)
        result = run_textblt(merge_pokes(continued(result), vdi.linea_pokes(SOURCEX=source_x, DELX=width)))


def test_through_the_line_a_exception():
    vdi.run_through_exception("LINEA_ROM_TEXTBLT", 8, {}, textblt_pokes("8x16", ord("A"), x=101, style=THICKEN))


# ---- Tier 3's rows: the glyphs a desktop draws, and the worst of what v_gtext asks for -------------------------
TIER3_ROWS = {
    "8x16 across two words, replace": textblt_pokes("8x16", ord("A"), x=101),
    "6x6 in one word, transparent": textblt_pokes("6x6", ord("e"), x=96, mode="transparent"),
    "8x16 bold italic, transparent": textblt_pokes("8x16", ord("B"), x=101, style=THICKEN | SKEW, mode="transparent"),
    "8x16 light, reverse": textblt_pokes("8x16", ord("C"), x=107, style=LIGHTEN, mode="reverse"),
    "8x16 outlined, turned 90": textblt_pokes("8x16", ord("D"), x=150, y=120, style=OUTLINE, chup=900),
    "8x16 scaled to 32": textblt_pokes("8x16", ord("E"), x=140, y=110, scale=32),
    "8x16 clipped away": textblt_pokes("8x16", ord("H"), x=80, y=60, window=vdi_text.TIGHT),
}
# Each a C row and two `.S` rows (`text_raster.S`): the front end, which reaches the ROM's body through vector 9
# on both sides, and the body itself.
for _label, _pokes in TIER3_ROWS.items():
    vdi.register(f"linea_textblt, {_label}", vdi.addrs.LINEA_ROM_TEXTBLT, _pokes)
    vdi_text.register_transcription("LINEA_ROM_TEXTBLT", _label, _pokes)
    vdi_text.register_transcription("LINEA_ROM_CPU_TEXTBLT", _label, _pokes)
