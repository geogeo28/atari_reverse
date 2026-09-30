"""The GDP (`src/vdi/gdp.c`): vdi_gdp ($fcbbcc, opcode 11), entered as the dispatcher's `jsr` leaves the machine —
its workstation DISPATCHED — and run through every arm of its switch ($fd3954) to the worker it calls.

    $fcbbcc  contrl[5] into a frame word; A5 = PTSIN, A4 = CUR_WORK; out of 1..10 nothing
    $fcbc0a  1  vr_recfl; WS_FILL_PER == 1: LN_MASK = -1, A5 = PTSIN again, (L,T) (R,T) (R,B) (L,B) (L,T) built over
                the sorted corners in the order ptsin[7], [5] = [3]; [9], [3] = [1]; [4] = [2]; [8], [6] = [0];
                contrl[1] = 5; polyline
    $fcbc68  2, 3  gdp_arc
    $fcbc70  4  XC, YC, XRAD = ptsin[0], [1], [4]; YRAD = smul_div(XRAD, DEV_TAB[3], DEV_TAB[4]); DEL_ANG 3600,
                BEG_ANG 0, END_ANG 3600; clc_nsteps; clc_arc
    $fcbcc8  5  XC, YC, XRAD, YRAD = ptsin[0..3]; WS_XFM_MODE < 2 (A4's): YRAD = DEV_TAB[1] - YRAD; DEL_ANG 3600,
                BEG_ANG 0, END_ANG 0; clc_nsteps; clc_arc
    $fcbd1e  6, 7  gdp_ell
    $fcbd24  8  WS_LINE_BEG, WS_LINE_END saved and cleared (A4's), gdp_rbox, put back (CUR_WORK read again)
    $fcbd50  9  gdp_rbox
    $fcbd56  10 d_justified

Each arm's run is held to its worker's own run from the machine `test/vdi_arcs.py` / `test/vdi_gtext.py` staged as
the arm's output (`vdi_gdp.assert_same_machine`): the worker's staging is the arm's real set-up, byte for byte.

THE ATTRIBUTION PASS IS OFF (`vdi.READS_A_POINTER_IT_WRITES`) where the workers' batteries have it off — a wide
outline (wline moves LINEA_PTSIN), justified text (TextBlt, and INTIN moved past the flags) — and where a case lays
ptsin over Line-A's own pointers. Every other case runs poisoned.

UNPINNED: the `cmp.w #9 / bhi` at $fcbd60 and the `bra` at $fcbd5e (dead: the range test in front of the switch
passes only 1..10, and arm 10 branches past the `bra`); a workstation record laid over LINEA_PTSIN, where arm 8's
clears would move the pointer gdp_rbox reads while the ROM's A5 kept the old one (the core reads LINEA_PTSIN,
`vdi/arcs.h`) — no workstation is allocated there; and arm 8's re-read of CUR_WORK for the put-back ($fcbd3c): it
tells only for a record whose LINE_BEG or LINE_END word IS CUR_WORK's low word ($27cc), where the arm's own clear
moves CUR_WORK to 0 — the vector page as the record gdp_rbox draws from, whose words are no workstation's (its
LINE_WIDTH is 2896; staged, wline was measured reading through a LINEA_PTSIN of $05970597 off the bus). The
wrapped rounded-box outlines that cycle in clip_line are gdp_rbox's (`test_vdi_arcs_rbox.py`).
"""
import subprocess

import pytest

import routines
import vdi
import vdi_arcs
import vdi_gdp
import vdi_gtext
import vdi_helpers
import vdi_raster
from case import merge_pokes
from vdi_arcs import (VDI_GDP_ARC, VDI_GDP_CIRCLE, VDI_GDP_ELLIPSE, VDI_GDP_ELLIPTICAL_ARC, VDI_GDP_ELLIPTICAL_PIE,
                      VDI_GDP_FILLED_ROUNDED_BOX, VDI_GDP_PIE, VDI_GDP_ROUNDED_BOX, circle_call, ellipse_call, workstation)
from vdi_gdp import (VDI_BAR_OUTLINE_POINTS, VDI_GDP_BAR, VDI_GDP_JUSTIFIED, assert_same_machine, bar_pokes, run_gdp,
                     run_worker)
from vdi_fill import DESKTOP_CLIP

UNPOISONED = vdi.READS_A_POINTER_IT_WRITES
HOST_RETURN_SECONDS = 10


def host_returns(pokes):
    """The host vdi_gdp over `pokes` alone in a child: a core that follows a pointer the case moved off the image
    FAILS here, where the differential would kill its worker."""
    try:
        returncode, stderr, _image = vdi_helpers.refusal_over(routines.core_symbol("VDI_ROM_GDP"), pokes,
                                                              seconds=HOST_RETURN_SECONDS, read_back=False)
    except subprocess.TimeoutExpired:
        pytest.fail(f"the host vdi_gdp did not return within {HOST_RETURN_SECONDS} s")
    assert returncode == 0, stderr


def stored_outside_the_stack(result):
    return [at for at in result.info["writes"] if at not in vdi_gdp.STACK_BAND]


# ================================================================================================
# The switch
# ================================================================================================
@pytest.mark.parametrize("gdp", (0, -1, 11, 12, 0x7FFF, -0x8000))
def test_out_of_range_does_nothing(gdp):
    """`tst.w / ble` and `cmpi.w #11 / bge`, both signed: nothing stored but the frame."""
    result = run_gdp(vdi_arcs.gdp_pokes(gdp, workstation(perimeter=1), intin=(0, 900),
                                        ptsin=(160, 100, 200, 150, 40, 0, 50, 0)))
    assert stored_outside_the_stack(result) == []


# ================================================================================================
# GDP 1, the bar
# ================================================================================================
BARS = {"upper left, lower right": (40, 30, 200, 150), "lower right, upper left": (200, 150, 40, 30),
        "lower left, upper right": (40, 150, 200, 30), "upper right, lower left": (200, 30, 40, 150),
        "a line": (60, 100, 260, 100), "a point": (150, 120, 150, 120)}
# The outline's last word, ptsin[9]: the closing point's y, which is the top again.
CLOSING_Y_SLOT = 2 * VDI_BAR_OUTLINE_POINTS - 1


@pytest.mark.parametrize("name", BARS)
def test_bar_with_its_perimeter(name):
    result = run_gdp(bar_pokes(BARS[name]))
    left, right = sorted(BARS[name][0::2])
    top, bottom = sorted(BARS[name][1::2])
    outline = (left, top, right, top, right, bottom, left, bottom, left, top)
    assert result.words(vdi.VDI_PTSIN_COPY, len(outline)) == [value & 0xFFFF for value in outline]
    assert result.contrl(vdi.CONTRL_N_PTSIN) == VDI_BAR_OUTLINE_POINTS
    assert result.linea("LN_MASK") == vdi.VDI_PERIMETER_LINE_MASK


@pytest.mark.parametrize("perimeter", (0, 2, -1, 0x101))
def test_bar_outlined_only_for_exactly_one(perimeter):
    """`cmpi.w #1`: 2, -1, and a word whose low byte is 1 fill the bar and draw no outline."""
    result = run_gdp(bar_pokes(BARS["upper left, lower right"], perimeter=perimeter))
    assert result.contrl(vdi.CONTRL_N_PTSIN) == 2


@pytest.mark.parametrize("pattern", vdi_raster.PATTERNS)
@pytest.mark.parametrize("mode", vdi_raster.MODES)
def test_bar_every_pattern_and_mode(pattern, mode):
    run_gdp(bar_pokes((33, 41, 170, 88), pattern=pattern, mode=mode))


@pytest.mark.parametrize("colour", vdi_raster.COLOURS)
def test_bar_every_colour(colour):
    """The outline in the FILL colour vr_recfl leaves in COLBIT — the line colour is staged apart from it."""
    run_gdp(bar_pokes((200, 90, 37, 60), colour=colour, mode="transparent"))


@pytest.mark.parametrize("clip", ((10, 20, 100, 199), (50, 40, 150, 120), None))
def test_bar_clipped_and_unclipped(clip):
    run_gdp(bar_pokes((-40, -20, 120, 90), clip=clip))


def test_bar_contrl_1_is_stored_after_the_outline():
    """CONTRL laid inside ptsin so contrl[1] is ptsin[9], the closing point's y: stored as the top by the outline,
    then 5 by `move.w #5` — and polyline draws the five points with that y."""
    contrl_at = vdi.VDI_PTSIN_COPY + CLOSING_Y_SLOT * vdi.WORD_BYTES - vdi.CONTRL_N_PTSIN
    pokes = merge_pokes(bar_pokes((40, 30, 200, 150)), vdi.linea_pokes(CONTRL=contrl_at),
                        {contrl_at: vdi.contrl(vdi_arcs.addrs.VDI_ROM_GDP_OPCODE, 2, subfunction=VDI_GDP_BAR)})
    result = run_gdp(pokes)
    assert result.word(contrl_at + vdi.CONTRL_N_PTSIN) == VDI_BAR_OUTLINE_POINTS


def test_bar_ln_mask_is_stored_before_the_outline():
    """ptsin laid at INTOUT, so ptsin[9] (the closing point's y) is LN_MASK: vr_recfl sorts and fills the rectangle
    INTOUT and PTSOUT's pointer words make (clipped away) and spreads the colour over ptsin[4..7], then the arm
    stores LN_MASK = -1 and the outline's top OVER it — polyline draws the outline in that mask."""
    ptsin_at = vdi.field("LINEA", "LN_MASK").at - CLOSING_Y_SLOT * vdi.WORD_BYTES
    assert ptsin_at == vdi.field("LINEA", "INTOUT").at
    result = run_gdp(merge_pokes(bar_pokes((0, 0, 0, 0)), vdi.pointer_pokes(ptsin=ptsin_at)))
    assert result.linea("LN_MASK") == vdi.INTOUT_AT & 0xFFFF


def test_bar_reads_ptsin_again_after_vr_recfl():
    """ptsin laid at $29a2, over Line-A's INTIN and PTSIN: vr_recfl's sort swaps x (INTIN's high word, 7, past
    PTSIN's 0) and y (INTIN's low word past PTSIN's) — MOVING the pointer onto `moved_to`, where the bar is staged.
    vr_recfl re-reads it and so does the arm ($fcbc26 `movea.l $29a6,a5`): the outline is built there. A core that
    kept the entry's A5 would build it over Line-A's pointers and follow them off the image (`host_returns`)."""
    ptsin_at = vdi.field("LINEA", "PTSIN").at - 2 * vdi.WORD_BYTES
    moved_to = vdi.PTSIN_AT
    assert (moved_to >> 16) > 0 and (moved_to & 0xFFFF) > (ptsin_at & 0xFFFF)
    pokes = merge_pokes(bar_pokes(BARS["upper left, lower right"]), {moved_to: vdi.pack_words(*BARS["a line"])},
                        vdi.linea_pokes(PTSIN=ptsin_at, INTIN=moved_to))
    host_returns(pokes)
    result = run_gdp(pokes, **UNPOISONED)
    assert result.linea("PTSIN") == moved_to
    assert result.word(moved_to + CLOSING_Y_SLOT * vdi.WORD_BYTES) == min(BARS["a line"][1::2]), "the outline's top"


# ================================================================================================
# GDP 4 and 5, the circle and the ellipse: the arm's scratch, held to clc_arc's run from vdi_arcs' staging
# ================================================================================================
CIRCLES = {"small": (160, 100, 20), "medium": (120, 90, 60), "large, 128 steps": (160, 105, 520),
           "off the left": (5, 100, 40), "trivially clipped away": (-100, 100, 40)}


@pytest.mark.parametrize("name", CIRCLES)
@pytest.mark.parametrize("perimeter", (0, 1))
def test_circle_is_what_clc_arc_was_verified_over(name, perimeter):
    work = workstation(perimeter=perimeter)
    result = run_gdp(circle_call(*CIRCLES[name], work))
    assert_same_machine(result, run_worker("VDI_ROM_CLC_ARC", vdi_arcs.circle_arm_pokes(*CIRCLES[name], work)))


@pytest.mark.parametrize("radius", (0, 1, -30, 32767, -32768))
def test_circle_radii_no_caller_is_refused(radius):
    """A radius the model smul_div refuses — negative, or one whose aspect overflows the word — the arm takes."""
    run_gdp(circle_call(160, 100, radius, workstation(perimeter=1)))


@pytest.mark.parametrize("aspect", ("medium", "high"))
def test_circle_other_aspects(aspect):
    run_gdp(merge_pokes(circle_call(160, 100, 50, workstation(perimeter=1)), vdi_arcs.vdi_lines.aspect_pokes(aspect)))


# A centre far enough left that clc_arc rejects the curve before building it in a ptsin laid over its own scratch.
OFF_THE_LEFT = -200


def test_circle_stores_each_word_before_reading_the_next():
    """ptsin laid one word below XC: ptsin[1] IS XC — the centre's y is read after ptsin[0] was stored there — and
    ptsin[4] IS YC, so the radius is the y just stored."""
    ptsin_at = vdi.LINEA_GDP_XC - vdi.WORD_BYTES
    pokes = merge_pokes(circle_call(0, 0, 0, workstation(perimeter=1)),
                        {ptsin_at: vdi.pack_words(OFF_THE_LEFT, 7, 7, 7, 7, 7)}, vdi.pointer_pokes(ptsin=ptsin_at))
    result = run_gdp(pokes)
    assert [vdi.signed_word(result.linea(name)) for name in ("GDP_XC", "GDP_YC", "GDP_XRAD")] == [OFF_THE_LEFT] * 3


ELLIPSES = {"flat": (160, 100, 140, 20), "tall": (80, 110, 15, 85), "zero radii": (100, 100, 0, 0),
            "clipped away": (160, 300, 40, 20)}


@pytest.mark.parametrize("name", ELLIPSES)
@pytest.mark.parametrize("perimeter", (0, 1))
def test_ellipse_is_what_clc_arc_was_verified_over(name, perimeter):
    work = workstation(perimeter=perimeter)
    result = run_gdp(ellipse_call(*ELLIPSES[name], work))
    assert_same_machine(result, run_worker("VDI_ROM_CLC_ARC", vdi_arcs.ellipse_pokes(*ELLIPSES[name], work)))


@pytest.mark.parametrize("mode", (-1, 0, 1, 2, 3))
def test_ellipse_normalised_coordinates_measure_the_y_radius_from_the_last_row(mode):
    result = run_gdp(ellipse_call(160, 100, 60, 150, workstation(perimeter=1, XFM_MODE=mode)))
    assert result.linea("GDP_YRAD") == (199 - 150 if mode < vdi.VDI_XFM_MODE_RC else 150)


def test_ellipse_stores_each_word_before_reading_the_next():
    ptsin_at = vdi.LINEA_GDP_XC - vdi.WORD_BYTES
    pokes = merge_pokes(ellipse_call(0, 0, 0, 0, workstation(perimeter=1)),
                        {ptsin_at: vdi.pack_words(OFF_THE_LEFT, 5, 60, 9)}, vdi.pointer_pokes(ptsin=ptsin_at))
    result = run_gdp(pokes)
    assert [vdi.signed_word(result.linea(name)) for name in ("GDP_XC", "GDP_YC")] == [OFF_THE_LEFT] * 2


# ================================================================================================
# The arms that only call: 2, 3, 6, 7, 9, 10 — each run held to its worker's
# ================================================================================================
ARC_PTSIN = (160, 105, 0, 0, 0, 0, 60, 0)
ELL_PTSIN = (160, 105, 90, 50)
PASSED_ON = {(VDI_GDP_ARC, "VDI_ROM_GDP_ARC", ARC_PTSIN), (VDI_GDP_PIE, "VDI_ROM_GDP_ARC", ARC_PTSIN),
             (VDI_GDP_ELLIPTICAL_ARC, "VDI_ROM_GDP_ELL", ELL_PTSIN), (VDI_GDP_ELLIPTICAL_PIE, "VDI_ROM_GDP_ELL", ELL_PTSIN)}


@pytest.mark.parametrize("gdp,worker,ptsin", sorted(PASSED_ON))
@pytest.mark.parametrize("sweep", ((450, 3150), (3000, 600), (900, 900)))
def test_arcs_and_pies_are_their_workers(gdp, worker, ptsin, sweep):
    pokes = vdi_arcs.gdp_pokes(gdp, workstation(perimeter=1, index=3), intin=sweep, ptsin=ptsin)
    assert_same_machine(run_gdp(pokes), run_worker(worker, pokes))


@pytest.mark.parametrize("width", (3, 9))
def test_wide_arc(width):
    run_gdp(vdi_arcs.gdp_pokes(VDI_GDP_ARC, workstation(width=width), intin=(1000, 3000), ptsin=ARC_PTSIN), **UNPOISONED)


RBOXES = {"upper left, lower right": (40, 30, 200, 150), "upper right, lower left": (200, 30, 40, 150),
          "odd half-sizes": (33, 41, 70, 88), "a point": (150, 120, 150, 120)}


@pytest.mark.parametrize("name", RBOXES)
def test_filled_rounded_box_is_gdp_rbox(name):
    pokes = vdi_arcs.rbox_pokes(RBOXES[name], outlined=False, perimeter=1)
    assert_same_machine(run_gdp(pokes), run_worker("VDI_ROM_GDP_RBOX", pokes, regs=vdi_arcs.RBOX_REGISTERS))


ENDS = (("arrow", "square"), ("square", "arrow"), ("arrow", "round"), ("arrow and round bits", 0x7FFF),
        ("square", "square"))


@pytest.mark.parametrize("ends", ENDS)
@pytest.mark.parametrize("name", RBOXES)
def test_outlined_rounded_box_clears_the_line_ends_round_gdp_rbox(name, ends):
    """The outline drawn with no arrowheads — gdp_rbox's run over `vdi_arcs.rbox_pokes`, whose record has them
    cleared — and the caller's ends put back after it: the two fields are the only bytes the runs differ in."""
    begin, end = ends
    result = run_gdp(vdi_gdp.outlined_rbox_pokes(RBOXES[name], begin=begin, end=end))
    reference = run_worker("VDI_ROM_GDP_RBOX", vdi_arcs.rbox_pokes(RBOXES[name]), regs=vdi_arcs.RBOX_REGISTERS)
    assert_same_machine(result, reference, allowed=(vdi_gdp.work_field_span("LINE_BEG"),
                                                    vdi_gdp.work_field_span("LINE_END")))
    assert (result.workstation("LINE_BEG"), result.workstation("LINE_END")) == \
        tuple(vdi_arcs.vdi_lines.ENDS.get(value, value) for value in ends)


@pytest.mark.parametrize("width", (3, 9))
def test_wide_outlined_rounded_box(width):
    run_gdp(vdi_gdp.outlined_rbox_pokes(RBOXES["upper right, lower left"], width=width, begin="arrow", end="arrow"),
            **UNPOISONED)


def test_outlined_rounded_box_on_a_virtual_workstation():
    """The ends saved and put back through CUR_WORK, which names a virtual workstation's record here."""
    work = vdi.virtual_workstation(7, onto=vdi_raster.CANVAS, LINE_BEG=1, LINE_END=1, LINE_COLOR=0b0110)
    result = run_gdp(vdi_arcs.gdp_pokes(VDI_GDP_ROUNDED_BOX, work, ptsin=RBOXES["odd half-sizes"]))
    assert result.workstation("LINE_BEG", vdi.VIRTUAL_WORK_AT) == 1


QUICK = "The quick brown fox"


@pytest.mark.parametrize("string,length,words,characters", ((QUICK, 211, 1, 1), ("a b c", 0, 1, 0), ("", 100, 1, 1)))
def test_justified_text_is_d_justified(string, length, words, characters):
    pokes = vdi_gtext.justified_call(string, length, words=words, characters=characters)
    assert_same_machine(run_gdp(pokes, **UNPOISONED), vdi_gtext.run_justified(pokes))


# ==== Tier 3: the worst realistic row of each arm ===========================================================
# Measured over the candidates each arm's cases above span (the densest pattern, every mode, a point to the whole
# screen, drawn and clipped away): the dearest ratio of each, and the worker-bound ones at their workers' worst.
A_POINT = (150, 120, 150, 120)
SPACES = " " * 80
TIER3_ROWS = {
    "out of range": vdi_arcs.gdp_pokes(0, workstation(perimeter=1)),
    "bar, a point, xor": bar_pokes(A_POINT, perimeter=0, mode="xor"),
    "bar, a point, xor, outlined": bar_pokes(A_POINT, mode="xor"),
    "pie, three quadrants": vdi_arcs.gdp_pokes(VDI_GDP_PIE, workstation(perimeter=1), intin=(450, 3150), ptsin=ARC_PTSIN),
    "circle, radius 60, filled and outlined": circle_call(120, 90, 60, workstation(perimeter=1)),
    "ellipse, tall, filled and outlined": ellipse_call(*ELLIPSES["tall"], workstation(perimeter=1)),
    "elliptical pie, tall, wraps past 0": vdi_arcs.gdp_pokes(VDI_GDP_ELLIPTICAL_PIE, workstation(perimeter=1), intin=(3000, 600),
                                                             ptsin=ELLIPSES["tall"]),
    "rounded box, outlined, width 3": vdi_gdp.outlined_rbox_pokes(RBOXES["upper left, lower right"], width=3),
    "filled rounded box, outlined": vdi_arcs.rbox_pokes(RBOXES["odd half-sizes"], outlined=False, perimeter=1),
    "justified, eighty spaces, both spread, clipped away": vdi_gtext.justified_call(SPACES, 700, words=1, characters=1, y=150,
                                                                                   window=vdi_gtext.TIGHT),
}
for _label, _pokes in TIER3_ROWS.items():
    vdi_gdp.register(_label, _pokes)
