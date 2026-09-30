"""$a00e copy_raster ($fd0346) and the three VDI functions over the raster primitives: `src/vdi/blit.c`.

    $fd0346  a BITBLT block on its own stack (`link a6,#-76`) out of the two MFDBs at contrl[7..10] —
             a NULL base is the screen, PLANES deep and WIDTH bytes a line — and intin[0]: bit 4 the
             fill pattern at PATPTR (16 rows, MULTIFILL's planes); the rest the op (opaque) or, with
             COPY_TRAN, the mode of a one-plane source drawn in intin[1] / intin[2] through MAP_COL.
             Refused: a destination not 1, 2 or 4 planes, an opaque copy between depths or past op 15,
             a transparent source of more than one plane or a mode past 4. Clipped only when CLIP is on
             AND the destination is the screen; otherwise ptsin's two rectangles are taken AS GIVEN, the
             destination's far corner its own. contrl[2] and contrl[4] cleared on every way out.
    $fcb5aa  vro_cpyfm (109): ptsin's two rectangles sorted (arb_corner), COPY_TRAN = 0, $a00e
    $fcb5dc  vrt_cpyfm (121): the same with COPY_TRAN = $ffff
    $fcb614  vr_recfl (114): ptsin sorted, WS_FILL_COLOR's bits into COLBIT0..3, the corners into X1..Y2,
             and $a005 — which clips and fills in the dispatcher's write mode and pattern

$a00e's block lives in the stack band the differential drops: what is compared is every form, contrl and
the Line-A variables. The functions are entered with the workstation DISPATCHED (`vdi.call_pokes`).
"""
import pytest

from harness import addrs

import routines
import test_vdi_raster_rect as rect
import vdi
import vdi_blit
import vdi_raster
from case import merge_pokes
from vdi_blit import MODES, OP_S, PATTERN_MODE, SCREEN

COPY = addrs.VDI_ROM_VRO_CPYFM_OPCODE
TRANSPARENT_COPY = addrs.VDI_ROM_VRT_CPYFM_OPCODE
FILL = addrs.VDI_ROM_VR_RECFL_OPCODE
ON_SCREEN = (10, 150, 72, 170, 131, 60, 193, 80)            # a 63 x 21 source over the screen, shifted
CONTRL_ANSWERS = (vdi.CONTRL_N_PTSOUT, vdi.CONTRL_N_INTOUT)


def copy_raster(pokes, **kwargs):
    result = vdi.run_primitive("LINEA_ROM_COPY_RASTER", {}, pokes, **kwargs)
    assert [result.contrl(offset) for offset in CONTRL_ANSWERS] == [0, 0], "contrl[2] and [4] are cleared"
    return result


def screen_untouched(result):
    return not any(SCREEN.base <= at < SCREEN.base + SCREEN.bytes for at in result.info["writes"])


def call(opcode, corners, **kwargs):
    return vdi_blit.raster_call_pokes(opcode, corners, **kwargs)


# ---- the opaque copy ------------------------------------------------------------------------------------

@pytest.mark.parametrize("op", vdi_blit.OPS)
def test_every_op_screen_to_screen(op):
    copy_raster(call(COPY, ON_SCREEN, mode=op))


@pytest.mark.parametrize("op", (OP_S, 6, 14))
@pytest.mark.parametrize("multifill", (0, 1))
def test_the_pattern_bit(op, multifill):
    """Bit 4: PATPTR ANDed into the source, 16 rows of a word, 32 bytes a plane when MULTIFILL — the
    user pattern's planes, or the same 16 rows for every plane."""
    pattern = vdi_raster.user_pattern_pokes()
    copy_raster(call(COPY, ON_SCREEN, mode=PATTERN_MODE | op,
                     extra=merge_pokes(pattern, vdi.linea_pokes(MULTIFILL=multifill))))


# (source, destination): form to form at every depth, and the screen (a null base) to a form and back —
# which an opaque copy allows only at the screen's own depth.
MFDB_PAIRS = {**{f"form to form, {planes} planes": (vdi_blit.off_screen(0, planes), vdi_blit.off_screen(1, planes))
                 for planes in (1, 2, 4)},
              "screen to form": (None, vdi_blit.off_screen(1, SCREEN.planes)),
              "form to screen": (vdi_blit.off_screen(0, SCREEN.planes), None)}


@pytest.mark.parametrize("forms", MFDB_PAIRS.values(), ids=MFDB_PAIRS.keys())
def test_mfdb_forms(forms):
    """A form's own planes and `wdwidth * 2 * planes` bytes a line; the screen's by a null base."""
    source, destination = forms
    copy_raster(call(COPY, (7, 3, 60, 14, 21, 5, 74, 16), mode=9, source_form=source, destination_form=destination))


@pytest.mark.parametrize("skew", vdi_raster.WIDTH_SKEWS)
def test_a_null_base_is_width_bytes_a_line_not_bytes_lin(skew):
    copy_raster(call(COPY, ON_SCREEN, mode=OP_S, extra=vdi_raster.width_skew_pokes(skew)))


# ---- clipping ------------------------------------------------------------------------------------------------
CLIP = (50, 20, 200, 90)
# The destination rectangle cut on each side, all four, missed each way — and a clip that does NOT apply.
CLIP_CASES = {"left": (0, 100, 60, 110, 20, 30, 80, 40), "right": (0, 100, 60, 110, 170, 30, 230, 40),
              "top": (0, 100, 60, 130, 60, 5, 120, 35), "bottom": (0, 100, 60, 130, 60, 80, 120, 110),
              "all four": (0, 0, 319, 199, 0, 0, 319, 199),
              "wholly left": (0, 100, 30, 110, 5, 30, 35, 40), "wholly above": (0, 100, 30, 110, 60, 1, 90, 12),
              "wholly right": (0, 100, 30, 110, 201, 30, 231, 40), "wholly below": (0, 100, 30, 110, 60, 95, 90, 99),
              # ...and cut to a single column and a single row: a width or height of exactly 1 still draws
              "one column": (0, 100, 30, 110, 200, 30, 230, 40), "one row": (0, 100, 30, 110, 60, 90, 90, 99)}


@pytest.mark.parametrize("corners", CLIP_CASES.values(), ids=CLIP_CASES.keys())
@pytest.mark.parametrize("op", (OP_S, 6))
def test_the_clip_moves_the_source_with_the_destination(corners, op):
    """A near edge before the clip moves the source's by as much; the far edges are the near ones plus
    the SOURCE's size, cut at the clip; an empty result draws nothing."""
    result = copy_raster(call(COPY, corners, mode=op, clip=CLIP))
    if corners[4] + (corners[2] - corners[0]) < CLIP[0] or corners[4] > CLIP[2] \
            or corners[5] + (corners[3] - corners[1]) < CLIP[1] or corners[5] > CLIP[3]:
        assert screen_untouched(result)


def test_the_clip_is_ignored_for_an_off_screen_destination():
    copy_raster(call(COPY, (0, 0, 40, 10, 5, 3, 45, 13), mode=OP_S, destination_form=vdi_blit.off_screen(1, 4),
                     clip=CLIP))


# ---- the transparent copy --------------------------------------------------------------------------------------
ONE_PLANE = vdi_blit.off_screen(0, 1)
FROM_FORM = (5, 2, 70, 19, 41, 70, 106, 87)
# (foreground, background): colours whose four planes each take a different op pair; a colour past the
# device's 16 (served as 1); and a negative one, which passes the SIGN test and indexes MAP_COL backwards.
# $8005 is the one kind where the SIGN of colour - 16 and a signed compare disagree: the subtraction overflows.
COLOURS = {"differing planes": (6, 9), "both past 15": (16, 99), "negative": (-1, 3), "$8005": (0x8005, 2)}


@pytest.mark.parametrize("colours", COLOURS.values(), ids=COLOURS.keys())
@pytest.mark.parametrize("mode", MODES.values(), ids=MODES.keys())
def test_every_mode_and_colour(mode, colours):
    copy_raster(call(TRANSPARENT_COPY, FROM_FORM, mode=mode, colours=colours, source_form=ONE_PLANE, transparent=1))


@pytest.mark.parametrize("mode", MODES.values(), ids=MODES.keys())
def test_a_transparent_copy_through_the_pattern(mode):
    copy_raster(call(TRANSPARENT_COPY, FROM_FORM, mode=PATTERN_MODE | mode, colours=(5, 10), source_form=ONE_PLANE,
                     transparent=1, extra=merge_pokes(vdi_raster.user_pattern_pokes(), vdi.linea_pokes(MULTIFILL=1))))


# ---- the refusals ----------------------------------------------------------------------------------------------
REFUSALS = {
    "a 3-plane destination": dict(mode=OP_S, source_form=vdi_blit.off_screen(0, 3), destination_form=vdi_blit.off_screen(1, 3)),
    "opaque between depths": dict(mode=OP_S, source_form=vdi_blit.off_screen(0, 2)),
    "opaque op 16": dict(mode=0x20 | OP_S),
    "transparent from two planes": dict(mode=1, source_form=vdi_blit.off_screen(0, 2), transparent=1, colours=(1, 2)),
    "transparent mode 0": dict(mode=0, source_form=ONE_PLANE, transparent=1, colours=(1, 2)),
    "transparent mode 5": dict(mode=5, source_form=ONE_PLANE, transparent=1, colours=(1, 2)),
}


@pytest.mark.parametrize("refusal", REFUSALS.values(), ids=REFUSALS.keys())
def test_what_it_refuses_draws_nothing_but_still_clears_the_counts(refusal):
    assert screen_untouched(copy_raster(call(COPY, ON_SCREEN, **refusal)))


def test_a_plane_count_of_33_passes_the_register_btst():
    """`btst d1,d3` on a register takes the bit number modulo 32: 33 planes is bit 1, and served."""
    source, destination = vdi_blit.Form(vdi_blit.FORMS_AT, 33, 66), vdi_blit.Form(vdi_blit.FORMS_AT + vdi_blit.FORM_BYTES, 33, 66)
    copy_raster(call(COPY, (0, 0, 20, 4, 3, 1, 23, 5), mode=6, source_form=source, destination_form=destination))


# ---- the rectangles as given ------------------------------------------------------------------------------------
# Unclipped, the destination's far corner is ptsin's own and the width and height the source's: a
# destination narrower or wider than the source, either way round in memory.
MISMATCHED = {"narrower, forwards": (100, 120, 160, 130, 40, 20, 70, 30),
              "wider, forwards": (100, 120, 130, 130, 40, 20, 110, 30),
              "narrower, backwards": (100, 20, 160, 30, 43, 120, 70, 130),
              "wider, backwards": (100, 20, 130, 30, 41, 120, 110, 130),
              "one word from three": (3, 20, 40, 25, 130, 120, 135, 125),
              # bit-aligned: op 3 takes the FAST copy, and walks the SOURCE's words into the destination
              "aligned, source wider": (32, 120, 120, 130, 64, 20, 90, 30),
              "a shift of exactly 8, backwards": (104, 20, 150, 30, 64, 120, 140, 130),
              # no shift, the spans an odd number of words apart: aligner 8 (one source word too many
              # for the row's first), never 9 — a shift of 0 is not a right shift
              "no shift, odd spans": (0, 20, 40, 25, 128, 120, 150, 125),
              "no shift, odd spans, wider": (0, 20, 40, 25, 128, 120, 190, 125)}


@pytest.mark.parametrize("corners", MISMATCHED.values(), ids=MISMATCHED.keys())
@pytest.mark.parametrize("op", (OP_S, 6, 12))
def test_rectangles_of_different_sizes(corners, op):
    """The engine's spans come from each rectangle's own edges — and backwards, the first word of a row
    is built from one source word and the stale half of the latch, which the mask does not then cover."""
    copy_raster(call(COPY, corners, mode=op))


# BACKWARDS, the row's first word is its RIGHTMOST, and the four aligners that build it from ONE source
# word (bits 2 and 3 of the index: 4, 6, 13, 15) fill the rest of it from the latch's stale high half —
# discarded by the right mask while the two rectangles agree. Here the destination ends on its word's
# last pixel, so the right mask keeps every bit, and the source is sized to give each aligner its parity.
# From the second row on, the stale half is the previous row's last word — so six rows.
# (source x1, source x2, destination x1): the destination always ends at x 95, the last pixel of a word.
STALE_LATCH = {"shift 3, even spans": (168, 180, 69), "shift 8, even spans": (173, 180, 69),
               "shift 9, even spans": (174, 180, 69),
               "shift -3, odd spans": (165, 175, 72), "shift -9, odd spans": (163, 200, 76)}


@pytest.mark.parametrize("edges", STALE_LATCH.values(), ids=STALE_LATCH.keys())
@pytest.mark.parametrize("op", (OP_S, 6))
def test_the_stale_latch_half_reaches_the_screen(edges, op):
    source_x1, source_x2, destination_x1 = edges
    copy_raster(call(COPY, (source_x1, 20, source_x2, 25, destination_x1, 120, 95, 125), mode=op))


def test_through_the_line_a_exception():
    vdi.run_through_exception("LINEA_ROM_COPY_RASTER", 0xE, {}, call(COPY, ON_SCREEN, mode=7))


# ---- the VDI functions -----------------------------------------------------------------------------------------

def run_function(name, pokes):
    return vdi.run_function(name, pokes)


def test_vro_cpyfm_sorts_both_rectangles_then_copies():
    """Each corner pair given the wrong way round: sorted in ptsin, IN PLACE (x ascending, y ascending)."""
    corners = (72, 170, 10, 150, 193, 80, 131, 60)
    result = run_function("VDI_ROM_VRO_CPYFM", call(COPY, corners, mode=6))
    assert result.words(vdi.VDI_PTSIN_COPY, 8) == list(ON_SCREEN)
    assert result.linea("COPY_TRAN") == 0


@pytest.mark.parametrize("corners", (ON_SCREEN, CLIP_CASES["left"], CLIP_CASES["wholly right"]),
                         ids=("on screen", "clipped", "clipped out"))
def test_vro_cpyfm(corners):
    run_function("VDI_ROM_VRO_CPYFM", call(COPY, corners, mode=OP_S, clip=CLIP))


@pytest.mark.parametrize("mode", MODES.values(), ids=MODES.keys())
def test_vrt_cpyfm(mode):
    result = run_function("VDI_ROM_VRT_CPYFM", call(TRANSPARENT_COPY, FROM_FORM, mode=mode, colours=(11, 4),
                                                    source_form=ONE_PLANE))
    assert result.linea("COPY_TRAN") == 0xFFFF


# vr_recfl: the dispatched workstation's fill — colour, write mode, pattern — over the canvas.
def recfl_pokes(corners, *, colour, mode, style="solid", clip=None):
    patterned = vdi_raster.user_pattern_pokes() if style == "user" else vdi_raster.pattern_pokes(style)
    xmin, ymin, xmax, ymax = clip or (0, 0, SCREEN.width - 1, SCREEN.height - 1)
    work = vdi.dispatched_pokes(onto=merge_pokes(vdi_blit.canvas(), patterned), FILL_COLOR=colour,
                                WRT_MODE=vdi_raster.MODES[mode], CLIP=int(clip is not None),
                                XMN_CLIP=xmin, YMN_CLIP=ymin, XMX_CLIP=xmax, YMX_CLIP=ymax)
    return merge_pokes(vdi.call_pokes(FILL, (), corners, workstation_pokes=work), patterned)


@pytest.mark.parametrize("colour", (0b0101, 0b1010, 0, 15))
@pytest.mark.parametrize("mode", vdi_raster.MODES)
def test_vr_recfl_every_mode_and_colour(mode, colour):
    result = run_function("VDI_ROM_VR_RECFL", recfl_pokes((200, 90, 37, 60), colour=colour, mode=mode, style="8 rows"))
    assert [result.linea(name) for name in vdi_raster.COLBITS] == [colour & 1 << plane for plane in range(4)]


@pytest.mark.parametrize("corners", rect.CUTS.values(), ids=rect.CUTS.keys())
def test_vr_recfl_clipped(corners):
    run_function("VDI_ROM_VR_RECFL", recfl_pokes(corners, colour=9, mode="replace", style="user", clip=rect.TIGHT_CLIP))


# ---- the rows Tier 3 prices ------------------------------------------------------------------------------------
COPY_RASTER_ROWS = {"op 3, 63 x 21 screen to screen, shifted": call(COPY, ON_SCREEN, mode=OP_S),
                    "transparent replace from a one-plane form": call(TRANSPARENT_COPY, FROM_FORM, mode=1, colours=(6, 9),
                                                                      source_form=ONE_PLANE, transparent=1),
                    "clipped out": call(COPY, CLIP_CASES["wholly right"], mode=OP_S, clip=CLIP)}
FUNCTION_ROWS = {("VDI_ROM_VRO_CPYFM", "op 6, corners reversed"): call(COPY, (72, 170, 10, 150, 193, 80, 131, 60), mode=6),
                 ("VDI_ROM_VRT_CPYFM", "reverse transparent"): call(TRANSPARENT_COPY, FROM_FORM, mode=4, colours=(11, 4),
                                                                    source_form=ONE_PLANE),
                 ("VDI_ROM_VR_RECFL", "8-row pattern, transparent, 164 x 31"): recfl_pokes((200, 90, 37, 60), colour=0b0110,
                                                                                            mode="transparent", style="8 rows"),
                 ("VDI_ROM_VR_RECFL", "clipped user pattern"): recfl_pokes(rect.CUTS["left"], colour=9, mode="replace",
                                                                           style="user", clip=rect.TIGHT_CLIP)}
for _label, _pokes in COPY_RASTER_ROWS.items():
    vdi_blit.register(_label, "LINEA_ROM_COPY_RASTER", _pokes)
for (_name, _label), _pokes in FUNCTION_ROWS.items():
    vdi.register(f"{routines.core_symbol(_name)}, {_label}", getattr(addrs, _name), _pokes)


@pytest.mark.parametrize("row", COPY_RASTER_ROWS, ids=list(COPY_RASTER_ROWS))
def test_the_copy_raster_rows(row):
    copy_raster(COPY_RASTER_ROWS[row])


@pytest.mark.parametrize("row", FUNCTION_ROWS, ids=[f"{name} {label}" for name, label in FUNCTION_ROWS])
def test_the_function_rows(row):
    run_function(row[0], FUNCTION_ROWS[row])
