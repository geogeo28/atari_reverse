"""Wide lines and arrowheads (`src/vdi/lines.c`): wline ($fccba0), arrow ($fcd0fa) and do_arrow ($fcd196) —
Alcyon calls entered by `jsr` over a DISPATCHED workstation, as v_pline reaches them.

    $fccba0  contrl[1] < 2: nothing. cir_dda when WS_LINE_WIDTH != LINE_CW; arrow when BEG|END bit 0; s_fa_attr;
             do_circ at the start when BEG was nonzero; per segment of any length: the offset (Q[0], 0) upright,
             (0, NUM_QC_LINES - 1) flat, else perp_off(smul_div(-dy, ph, pw), smul_div(dx, pw, ph)); contrl[1] = 4,
             PTSIN at the four corners, plygn (outlined: contrl[1] left 5), PTSIN back; do_circ at the far end
             unless it is the last point and END was 0; r_fa_attr
    $fcd0fa  s_fa_attr; BEG bit 0: do_arrow(ptsin, +2); END bit 0: the first point put back as it was, then
             do_arrow(ptsin + 4 * contrl[1] - 4, -2), then the first point as the start arrow left it; r_fa_attr
    $fcd196  length 8 (width 1) or 3w - 1; walk to the first point at least that far (y in x's aspect); the
             triangle through plygn with contrl[1] = 3; the end pulled back to the head's base and every point
             walked past moved onto it

Every case runs over `vdi_raster.CANVAS`, the fill fields staged apart from the line fields (so a field s_fa_attr
or r_fa_attr missed shows), and a quarter circle for ANOTHER width left in LINE_CW so wline rebuilds it — except
the cases that stage the right one, where it must not.

WHAT IS NOT STAGED: do_arrow with fewer than two points compares a length it never computed (stack garbage in the
ROM) — only v_pline's one-pixel path can arrive so; widths whose arrowhead is not longer than 0 (a width of 0 or
below) divide by a zero distance.
"""
import pytest

import vdi
import vdi_lines
import vdi_raster
from case import merge_pokes
from vdi_lines import WIDEST, circle_pokes, line_workstation

FORWARD = vdi_lines.VDI_ARROW_STEP_FORWARD
BACKWARD = vdi_lines.VDI_ARROW_STEP_BACKWARD

PATHS = {
    "one segment": [(40, 60), (200, 150)],
    "zigzag": [(20, 20), (120, 80), (60, 150), (300, 180), (250, 30)],
    "upright and flat": [(50, 30), (50, 170), (250, 170), (250, 40)],
    "steep and shallow": [(100, 20), (110, 180), (300, 190), (10, 175)],
    "a repeated point": [(40, 40), (140, 90), (140, 90), (60, 170)],
    # Off both sides and the top — not below the screen, whose last row is 768 bytes short of the end of RAM,
    # where an unclipped quadrilateral's rows would land off the image.
    "clipped": [(-30, 100), (160, 5), (350, 120), (160, 195)],
}
# Another width's quarter circle left behind: wline must rebuild it (LINE_CW differs).
STALE_WIDTH = 5


def wline_pokes(path, *, width=9, stale=True, aspect="low", count=None, **fields):
    circle = circle_pokes(STALE_WIDTH if stale else width, aspect)
    work = line_workstation(width=width, onto=circle, **fields)
    return vdi_lines.path_pokes("VDI_ROM_V_PLINE", path, work, count=count)


def run_wline(pokes):
    return vdi_lines.run_call("VDI_ROM_WLINE", (), pokes)


@pytest.mark.parametrize("name", PATHS)
@pytest.mark.parametrize("width", (3, 9, WIDEST))
def test_wline(name, width):
    path = PATHS[name]
    result = run_wline(wline_pokes(path, width=width))
    assert result.linea("LINE_CW") == width


@pytest.mark.parametrize("begin", vdi_lines.ENDS)
@pytest.mark.parametrize("end", vdi_lines.ENDS)
def test_wline_every_pair_of_ends(begin, end):
    run_wline(wline_pokes(PATHS["zigzag"], width=7, begin=begin, end=end))


@pytest.mark.parametrize("mode", vdi_raster.MODES)
@pytest.mark.parametrize("colour", vdi_raster.COLOURS)
def test_wline_every_mode_and_colour(mode, colour):
    run_wline(wline_pokes(PATHS["steep and shallow"], width=5, mode=mode, colour=colour, end="round"))


@pytest.mark.parametrize("aspect", ("medium", "high"))
@pytest.mark.parametrize("name", ("zigzag", "upright and flat"))
def test_wline_other_aspects(aspect, name):
    """Medium resolution's tall pixels average two octant rows into one, so an upright segment's offset
    (Q[0]) is not Q[1]."""
    run_wline(wline_pokes(PATHS[name], width=11, aspect=aspect, begin="round", end="arrow"))


def test_wline_keeps_the_quarter_circle_built_for_its_width():
    """LINE_CW equal to the width: cir_dda is not run, so the staged circle is the one drawn with."""
    run_wline(wline_pokes(PATHS["zigzag"], width=9, stale=False, end="round"))


def test_wline_keeps_a_quarter_circle_built_for_another_aspect():
    """The circle is keyed by width alone: one built for this width on a medium-resolution workstation (tall
    pixels, fewer rows) is kept when the aspect is low resolution's — cir_dda is not run."""
    pokes = merge_pokes(wline_pokes(PATHS["zigzag"], width=9, stale=False, begin="round", end="round"),
                        circle_pokes(9, "medium"), vdi_lines.aspect_pokes("low"))
    run_wline(pokes)


@pytest.mark.parametrize("width", (2, 4, 40), ids=("2", "4", "40"))
def test_wline_even_staged_widths(width):
    run_wline(wline_pokes(PATHS["one segment"], width=width, begin="round", end="round"))


@pytest.mark.parametrize("count", (0, 1), ids=("no points", "one point"))
def test_wline_fewer_than_two_points_draws_nothing(count):
    """Not even the fill attributes are borrowed: the saved words keep their stale values."""
    pokes = merge_pokes(wline_pokes(PATHS["one segment"], count=count),
                        vdi.linea_pokes(GDP_SAVED_FILL_COLOR=0x5A5A))
    assert run_wline(pokes).linea("GDP_SAVED_FILL_COLOR") == 0x5A5A


def test_wline_clip_off_still_clips_its_discs():
    """plygn clips only when CLIP; do_circ asks clip_line whatever it says — so with CLIP 0 and the discs past
    the clip rectangle, the quadrilaterals run on and the discs stop at it."""
    run_wline(wline_pokes(PATHS["clipped"], width=15, clip=None, begin="round", end="round"))


def test_wline_leaves_the_caller_s_count_at_the_outline_s():
    """contrl[1] = 4 for each quadrilateral, and plygn's outline makes it 5 — which is where the CALLER's
    contrl[1] is left."""
    result = run_wline(wline_pokes(PATHS["zigzag"], width=9))
    assert result.contrl(vdi.CONTRL_N_PTSIN) == vdi_lines.VDI_WIDE_CORNER_COUNT + 1


# contrl laid over the caller's points so that contrl[1] IS the last point's x: the first quadrilateral's store
# of 4 (then 5) lands on it BEFORE the cursor reads that point — the other order draws to x = 3.
CONTRL_OVER_THE_LAST_POINT = vdi.VDI_PTSIN_COPY + 2 * vdi.VDI_POINT_BYTES - vdi.CONTRL_N_PTSIN


def test_wline_reads_each_point_after_the_segment_before_it_is_drawn():
    path = [(60, 40), (160, 120), (3, 170)]
    pokes = merge_pokes(wline_pokes(path, width=7), vdi.linea_pokes(CONTRL=CONTRL_OVER_THE_LAST_POINT))
    run_wline(pokes)


# ---- arrow and do_arrow ------------------------------------------------------------------------------------
ARROW_PATHS = {
    "long segment": [(30, 40), (250, 160)],
    "short first segments": [(100, 100), (102, 101), (104, 103), (200, 180), (280, 60)],
    "all too short": [(100, 100), (102, 101), (103, 103)],
    "backwards and up": [(280, 170), (20, 30)],
    "upright": [(160, 20), (160, 190)],
    # A one-pixel line's arrowhead is 8 long: a point EXACTLY that far stops the walk ($fcd24c `bge`) ...
    "exactly the length away": [(100, 100), (108, 100), (200, 150)],
    # ...and, as the last point, is still far enough to draw ($fcd260 `blt`).
    "only point exactly the length away": [(100, 100), (108, 100)],
}


def arrow_pokes(path, *, width=1, begin="arrow", end="arrow", **fields):
    work = line_workstation(width=width, begin=begin, end=end, **fields)
    return vdi_lines.path_pokes("VDI_ROM_V_PLINE", path, work)


def run_arrow(pokes):
    return vdi_lines.run_call("VDI_ROM_ARROW", (), pokes, **vdi.READS_A_POINTER_IT_WRITES)


@pytest.mark.parametrize("name", ARROW_PATHS)
@pytest.mark.parametrize("width", (1, 3, 9))
@pytest.mark.parametrize("ends", (("arrow", "square"), ("square", "arrow"), ("arrow", "arrow")), ids=str)
def test_arrow(name, width, ends):
    begin, end = ends
    run_arrow(arrow_pokes(ARROW_PATHS[name], width=width, begin=begin, end=end))


@pytest.mark.parametrize("aspect", ("medium", "high"))
def test_arrow_other_aspects(aspect):
    pokes = merge_pokes(arrow_pokes(ARROW_PATHS["short first segments"], width=5), vdi_lines.aspect_pokes(aspect))
    run_arrow(pokes)


def test_arrow_the_round_bit_alone_draws_no_arrowhead():
    run_arrow(arrow_pokes(ARROW_PATHS["long segment"], begin="round", end="round"))


# contrl laid over the FIRST point, so contrl[1] is its x: the start arrowhead moves it (and so the count),
# and the end arrowhead's address is computed from contrl[1] AFTER the first point is put back — the original
# x again. Read before the store, it would be the moved one.
CONTRL_OVER_THE_FIRST_POINT = vdi.VDI_PTSIN_COPY - vdi.CONTRL_N_PTSIN


def test_arrow_puts_the_first_point_back_before_it_counts_the_points():
    path = [(3, 60), (150, 120), (260, 30)]
    pokes = merge_pokes(arrow_pokes(path, width=3), vdi.linea_pokes(CONTRL=CONTRL_OVER_THE_FIRST_POINT))
    run_arrow(pokes)


def do_arrow_pokes(path, *, width=1, **fields):
    return arrow_pokes(path, width=width, **fields)


def run_do_arrow(pokes, point, step):
    return vdi_lines.run_call("VDI_ROM_DO_ARROW", (point, step), pokes)


def last_point(path):
    return vdi.VDI_PTSIN_COPY + (len(path) - 1) * vdi.VDI_POINT_BYTES


@pytest.mark.parametrize("name", ARROW_PATHS)
@pytest.mark.parametrize("mode", vdi_raster.MODES)
def test_do_arrow_forward_from_the_first_point(name, mode):
    run_do_arrow(do_arrow_pokes(ARROW_PATHS[name], mode=mode, width=3), vdi.VDI_PTSIN_COPY, FORWARD)


@pytest.mark.parametrize("name", ARROW_PATHS)
def test_do_arrow_back_from_the_last_point(name):
    path = ARROW_PATHS[name]
    run_do_arrow(do_arrow_pokes(path, width=5), last_point(path), BACKWARD)


def test_do_arrow_moves_every_point_walked_past_onto_the_base():
    path = ARROW_PATHS["short first segments"]
    result = run_do_arrow(do_arrow_pokes(path, width=9), vdi.VDI_PTSIN_COPY, FORWARD)
    points = result.words(vdi.VDI_PTSIN_COPY, 2 * len(path))
    assert points[2:4] == points[0:2] and points[4:6] == points[0:2]


def test_do_arrow_restores_the_caller_s_count():
    result = run_do_arrow(do_arrow_pokes(ARROW_PATHS["long segment"]), vdi.VDI_PTSIN_COPY, FORWARD)
    assert result.contrl(vdi.CONTRL_N_PTSIN) == len(ARROW_PATHS["long segment"])


# contrl laid over the END point, so contrl[1] is its x: contrl[1] = 3 is stored BEFORE the triangle reads the
# point, and the count is put back after it.
def test_do_arrow_reads_the_point_after_storing_the_count():
    path = [(200, 150), (2, 40)]
    pokes = merge_pokes(do_arrow_pokes(path), vdi.linea_pokes(CONTRL=last_point(path) - vdi.CONTRL_N_PTSIN))
    run_do_arrow(pokes, last_point(path), BACKWARD)


# ---- Tier 3 ------------------------------------------------------------------------------------------------
vdi_lines.register_call("zigzag, width 9, rebuilt, round ends", "VDI_ROM_WLINE", (),
                        wline_pokes(PATHS["zigzag"], width=9, begin="round", end="round"))
vdi_lines.register_call("one segment, width 3, square ends", "VDI_ROM_WLINE", (),
                        wline_pokes(PATHS["one segment"], width=3, stale=False))
# arrow's and do_arrow's worst realistic rows are ONE PIXEL wide — the width v_pline's one-pixel path calls arrow
# at ($fcba46) — over a long segment, the longest walk.
vdi_lines.register_call("long segment, width 1, both ends", "VDI_ROM_ARROW", (), arrow_pokes(ARROW_PATHS["long segment"]))
vdi_lines.register_call("both ends, width 3", "VDI_ROM_ARROW", (), arrow_pokes(ARROW_PATHS["long segment"], width=3))
vdi_lines.register_call("long segment, width 1", "VDI_ROM_DO_ARROW", (vdi.VDI_PTSIN_COPY, FORWARD),
                        do_arrow_pokes(ARROW_PATHS["long segment"]))
vdi_lines.register_call("one-pixel line, walked past short segments", "VDI_ROM_DO_ARROW", (vdi.VDI_PTSIN_COPY, FORWARD),
                        do_arrow_pokes(ARROW_PATHS["short first segments"]))
vdi_lines.register_call("all too short", "VDI_ROM_DO_ARROW", (vdi.VDI_PTSIN_COPY, FORWARD),
                        do_arrow_pokes(ARROW_PATHS["all too short"]))
