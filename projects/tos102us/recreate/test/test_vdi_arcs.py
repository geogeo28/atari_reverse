"""Arcs and ellipses (`src/vdi/arcs.c`): clc_pts ($fcc914), clc_arc ($fcc79e), gdp_arc ($fcc62e) and gdp_ell
($fcc714) — Alcyon calls entered by `jsr` as vdi_gdp's arms leave the machine (`test/vdi_arcs.py`).

    $fcc914  x = smul_div(icos(ANGLE), XRAD, 32767) + XC into ptsin[point], then y = YC - smul_div(isin(ANGLE),
             YRAD, 32767) into ptsin[point + 1] — PTSIN read once, the scratch re-read after the x is stored
    $fcc79e  CLIP: nothing when XC + XRAD < XMINCL, XC - XRAD > XMAXCL, YC + YRAD < YMINCL or YC - YRAD > YMAXCL;
             ANGLE = START = BEG_ANG, the point; for step 1 .. N_STEPS - 1 ANGLE = smul_div(DEL_ANG, step, N_STEPS)
             + START, the point; ANGLE = END_ANG, the point; contrl[1] = N_STEPS + 1; a pie (3, 7): N_STEPS += 1,
             the centre as the next point, contrl[1] again; an arc (2, 6): v_pline, else plygn — contrl[5] re-read
             at every test through the CONTRL held since the points
    $fcc62e  BEG_ANG / END_ANG = intin[0..1], DEL_ANG = END - BEG (+3600 below 0); XRAD = ptsin[6], YRAD =
             smul_div(XRAD, DEV_TAB[3], DEV_TAB[4]); clc_nsteps; XC / YC = ptsin[0..1]; clc_arc
    $fcc714  the angles as gdp_arc; XC, YC, XRAD, YRAD = ptsin[0..3]; WS_XFM_MODE < 2: YRAD = DEV_TAB[1] - YRAD;
             clc_nsteps; clc_arc

Every drawing case runs over `vdi_raster.CANVAS` with the fill fields staged apart from the line fields, so a
point one pixel off, or a pie closed in the wrong pen, changes bits the ROM left alone.

THE ATTRIBUTION PASS IS OFF (`vdi.READS_A_POINTER_IT_WRITES`) for the cases that reach wline or arrow through
v_pline — a wide arc, an arc with arrowheads: wline puts LINEA_PTSIN back after each segment, so the poisoned run
builds the curve through an inverted PTSIN at $ffe6xx. Every other case runs poisoned.

"""
import pytest

import vdi
import vdi_arcs
import vdi_raster
from case import merge_pokes
from vdi_arcs import TURN, VDI_GDP_ARC, VDI_GDP_ELLIPTICAL_ARC, VDI_GDP_ELLIPTICAL_PIE, VDI_GDP_PIE, workstation
from vdi_fill import DESKTOP_CLIP

WIDE = vdi.READS_A_POINTER_IT_WRITES


# ================================================================================================
# clc_pts
# ================================================================================================
# Every octant's middle and edges, a turn and past it (isin brings those down), two turns, and below 0 (isin
# reads below its table).
ANGLES = (0, 1, 225, 450, 675, 899, 900, 1234, 1350, 1800, 2250, 2700, 3150, 3599, TURN, TURN + 1, 5000,
          2 * TURN + 450, -1, -450)
RADII = {"round": (80, 73), "flat": (150, 12), "tall": (9, 90), "zero": (0, 0), "negative": (-40, -25),
         "huge": (30000, 20000)}


def point_pokes(angle, xrad, yrad, *, xc=160, yc=100, ptsin=vdi.VDI_PTSIN_COPY):
    return merge_pokes(vdi.linea_pokes(GDP_ANGLE=angle, GDP_XC=xc, GDP_YC=yc, GDP_XRAD=xrad, GDP_YRAD=yrad),
                       vdi.pointer_pokes(ptsin=ptsin))


def run_point(point, pokes):
    return vdi_arcs.run_call("VDI_ROM_CLC_PTS", (point,), pokes)


@pytest.mark.parametrize("angle", ANGLES)
@pytest.mark.parametrize("radii", RADII)
def test_clc_pts(angle, radii):
    run_point(4, point_pokes(angle, *RADII[radii]))


@pytest.mark.parametrize("point", (0, 1, 130, 258))
def test_clc_pts_at_every_index_clc_arc_uses(point):
    run_point(point, point_pokes(1234, 70, 60, xc=-30000, yc=30000))


def test_clc_pts_index_is_signed():
    """A negative index is sign-extended before it is doubled (`movea.w` / `adda.l`): the point lands BELOW
    PTSIN. Only a direct call passes one — clc_arc's run 0 up."""
    run_point(-4, point_pokes(700, 50, 50, ptsin=vdi.VDI_PTSIN_COPY + 16))


def test_clc_pts_re_reads_the_radius_after_the_x_store():
    """PTSIN over GDP_YRAD: the x lands on the y radius, and the y is measured with it."""
    result = run_point(0, point_pokes(600, 50, 40, ptsin=vdi.LINEA_GDP_YRAD))
    assert result.linea("GDP_YRAD") == 184      # XC + 50 cos 60, as the sine table has it


# ================================================================================================
# clc_arc, as the circle and ellipse arms leave it
# ================================================================================================
def run_arc(pokes, **kwargs):
    return vdi_arcs.run_call("VDI_ROM_CLC_ARC", (), pokes, **kwargs)


def past_the_reject(result):
    """Did clc_arc get past its trivial reject? Its first store after it is LINEA_GDP_ANGLE."""
    return vdi.LINEA_GDP_ANGLE in result.info["writes"]


CIRCLES = {"small": (160, 100, 20), "medium": (120, 90, 60), "large, 128 steps": (160, 105, 520),
           "off the left": (5, 100, 40), "off the top": (160, 15, 40), "across three edges": (300, 190, 90)}


@pytest.mark.parametrize("name", CIRCLES)
@pytest.mark.parametrize("perimeter", (0, 1))
def test_circle(name, perimeter):
    run_arc(vdi_arcs.circle_arm_pokes(*CIRCLES[name], workstation(perimeter=perimeter)))


@pytest.mark.parametrize("pattern", ("solid", "8 rows", "16-row hatch"))
@pytest.mark.parametrize("mode", tuple(vdi_raster.MODES))
def test_circle_every_mode_and_pattern(pattern, mode):
    run_arc(vdi_arcs.circle_arm_pokes(150, 110, 45, workstation(pattern=pattern, mode=mode, perimeter=1)))


ELLIPSES = {"flat": (160, 100, 140, 20), "tall": (80, 110, 15, 85), "zero radii": (100, 100, 0, 0)}


@pytest.mark.parametrize("name", ELLIPSES)
def test_ellipse(name):
    run_arc(vdi_arcs.ellipse_pokes(*ELLIPSES[name], workstation(perimeter=1)))


# XC ± XRAD / YC ± YRAD just past each clip edge (nothing drawn) and just touching it (drawn).
TRIVIAL = {"left": ((-41, 100), (-40, 100)), "right": ((360, 100), (359, 100)),
           "above": ((160, -26), (160, -25)), "below": ((160, 236), (160, 235))}
TRIVIAL_RADII = (40, 36)                   # XRAD, YRAD: so XMINCL 0 / YMINCL 11 / XMAXCL 319 / YMAXCL 199 edges


@pytest.mark.parametrize("side", TRIVIAL)
def test_trivially_clipped_away_and_just_kept(side):
    missed, touching = TRIVIAL[side]
    missed_result = run_arc(vdi_arcs.ellipse_pokes(*missed, *TRIVIAL_RADII, workstation(clip=DESKTOP_CLIP)))
    touching_result = run_arc(vdi_arcs.ellipse_pokes(*touching, *TRIVIAL_RADII, workstation(clip=DESKTOP_CLIP)))
    assert not past_the_reject(missed_result) and past_the_reject(touching_result)


def test_no_trivial_reject_without_clipping():
    """CLIP off: an ellipse wholly off the clip rectangle (but on the screen) is drawn."""
    run_arc(vdi_arcs.ellipse_pokes(160, 100, 30, 20, workstation(clip=None, XMN_CLIP=200, XMX_CLIP=300)))


@pytest.mark.parametrize("xc", (100, -100))
def test_clip_reject_sums_wrap_as_words(xc):
    """XC + XRAD past 32767 wraps negative (rejected as left of the clip), and XC - XRAD past -32768 wraps
    positive (right of it): the ROM's `add.w` / `sub.w` then a signed compare — unwrapped, both would draw."""
    result = run_arc(vdi_arcs.ellipse_pokes(xc, 100, 32700, 20, workstation()))
    assert not past_the_reject(result)


def test_a_pie_moved_to_an_arc_by_its_own_centre():
    """CONTRL laid inside ptsin where the pie's centre lands on contrl[5]: the centre's x (6, an elliptical arc)
    replaces the GDP number, and the re-read test draws the curve through v_pline instead of plygn."""
    xrad, yrad = 40, 30
    steps = vdi_arcs.n_steps(xrad, yrad)
    centre_word = 2 * (steps + 1)
    contrl_at = vdi.VDI_PTSIN_COPY + centre_word * vdi.WORD_BYTES - vdi.CONTRL_SUBFUNCTION
    pokes = vdi_arcs.ellipse_pokes(VDI_GDP_ELLIPTICAL_ARC, 100, xrad, yrad, workstation(clip=DESKTOP_CLIP))
    pokes = merge_pokes(pokes, vdi.linea_pokes(CONTRL=contrl_at), {contrl_at: vdi.contrl(11, 4, subfunction=VDI_GDP_ELLIPTICAL_PIE)})
    result = run_arc(pokes)
    assert result.word(contrl_at + vdi.CONTRL_SUBFUNCTION) == VDI_GDP_ELLIPTICAL_ARC


# ================================================================================================
# gdp_arc and gdp_ell, from the call's arrays
# ================================================================================================
def run_gdp(name, pokes, **kwargs):
    return vdi_arcs.run_call(name, (), pokes, **kwargs)


def arc_pokes(gdp, begin, end, *, xc=160, yc=105, radius=60, work=None):
    return vdi_arcs.gdp_pokes(gdp, work or workstation(perimeter=1), intin=(begin, end),
                              ptsin=(xc, yc, 0, 0, 0, 0, radius, 0))


def ell_pokes(gdp, begin, end, *, xc=160, yc=105, xrad=90, yrad=50, work=None):
    return vdi_arcs.gdp_pokes(gdp, work or workstation(perimeter=1), intin=(begin, end), ptsin=(xc, yc, xrad, yrad))


# (begin, end): every quadrant, a sweep that wraps past 0 (negative difference), a full turn, none, and angles
# outside 0..3600 as a caller may pass them.
SWEEPS = {"first quadrant": (100, 800), "three quadrants": (450, 3150), "wraps past 0": (3000, 600),
          "full turn": (0, TURN), "none": (900, 900), "past a turn": (3000, 4500), "negative begin": (-900, 900),
          "backwards a turn": (TURN, 0), "reflex": (2000, 1000)}


@pytest.mark.parametrize("sweep", SWEEPS)
@pytest.mark.parametrize("gdp", (VDI_GDP_ARC, VDI_GDP_PIE))
def test_gdp_arc(sweep, gdp):
    result = run_gdp("VDI_ROM_GDP_ARC", arc_pokes(gdp, *SWEEPS[sweep]))
    begin, end = SWEEPS[sweep]
    assert result.linea("GDP_DEL_ANG") == end - begin + (TURN if end < begin else 0)


@pytest.mark.parametrize("sweep", SWEEPS)
@pytest.mark.parametrize("gdp", (VDI_GDP_ELLIPTICAL_ARC, VDI_GDP_ELLIPTICAL_PIE))
def test_gdp_ell(sweep, gdp):
    run_gdp("VDI_ROM_GDP_ELL", ell_pokes(gdp, *SWEEPS[sweep]))


@pytest.mark.parametrize("mode", (-1, 0, 1, 2, 3))
def test_gdp_ell_normalised_coordinates_measure_the_y_radius_from_the_last_row(mode):
    """WS_XFM_MODE below 2 (signed: NDC is 0): YRAD = DEV_TAB[1] - ptsin[3] — 199 - 150 = 49 here; from 2 up,
    ptsin[3] itself."""
    work = workstation(perimeter=1, XFM_MODE=mode)
    result = run_gdp("VDI_ROM_GDP_ELL", ell_pokes(VDI_GDP_ELLIPTICAL_PIE, 300, 2000, yrad=150, work=work))
    assert result.linea("GDP_YRAD") == (199 - 150 if mode < vdi.VDI_XFM_MODE_RC else 150)


def test_gdp_arc_reads_the_end_angle_after_storing_the_begin():
    """INTIN laid over GDP_ANGLE: intin[1] is GDP_BEG_ANG, read after intin[0] was stored there."""
    pokes = merge_pokes(arc_pokes(VDI_GDP_PIE, 0, 0), vdi.linea_pokes(INTIN=vdi.LINEA_GDP_ANGLE, GDP_ANGLE=1300))
    result = run_gdp("VDI_ROM_GDP_ARC", pokes)
    assert result.linea("GDP_END_ANG") == 1300


@pytest.mark.parametrize("radius", (0, -30, 1, 700))
def test_gdp_arc_radii(radius):
    run_gdp("VDI_ROM_GDP_ARC", arc_pokes(VDI_GDP_PIE, 200, 3300, radius=radius))


@pytest.mark.parametrize("aspect", ("medium", "high"))
def test_gdp_arc_other_aspects(aspect):
    run_gdp("VDI_ROM_GDP_ARC", merge_pokes(arc_pokes(VDI_GDP_PIE, 450, 2700), vdi_arcs.vdi_lines.aspect_pokes(aspect)))


@pytest.mark.parametrize("index", range(7))
def test_arc_outline_every_line_style(index):
    run_gdp("VDI_ROM_GDP_ARC", arc_pokes(VDI_GDP_ARC, 300, 3300, work=workstation(index=index, UD_LS=0xF0F3)))


@pytest.mark.parametrize("width", (3, 9))
def test_wide_arc(width):
    run_gdp("VDI_ROM_GDP_ARC", arc_pokes(VDI_GDP_ARC, 1000, 3000, work=workstation(width=width)), **WIDE)


@pytest.mark.parametrize("ends", (("arrow", "square"), ("square", "arrow"), ("arrow", "arrow")))
def test_arc_arrowheads(ends):
    begin, end = ends
    run_gdp("VDI_ROM_GDP_ELL", ell_pokes(VDI_GDP_ELLIPTICAL_ARC, 200, 2500, work=workstation(begin=begin, end=end)),
            **WIDE)


def test_unclipped_pie_on_the_screen():
    run_gdp("VDI_ROM_GDP_ARC", arc_pokes(VDI_GDP_PIE, 450, 3000, radius=50, work=workstation(clip=None, perimeter=1)))


# ---- Tier 3: a point, a curve drawn filled and one clipped away, and each arm's worker ------------------------
vdi_arcs.register_call("an interpolated angle", "VDI_ROM_CLC_PTS", (4,), point_pokes(1234, 80, 73))
vdi_arcs.register_call("circle, radius 60, filled and outlined", "VDI_ROM_CLC_ARC", (),
                       vdi_arcs.circle_arm_pokes(120, 90, 60, workstation(perimeter=1)))
vdi_arcs.register_call("trivially clipped away", "VDI_ROM_CLC_ARC", (),
                       vdi_arcs.ellipse_pokes(*TRIVIAL["left"][0], 40, 36, workstation()))
vdi_arcs.register_call("pie, three quadrants, outlined", "VDI_ROM_GDP_ARC", (), arc_pokes(VDI_GDP_PIE, *SWEEPS["three quadrants"]))
vdi_arcs.register_call("arc, dash-dot", "VDI_ROM_GDP_ARC", (),
                       arc_pokes(VDI_GDP_ARC, *SWEEPS["three quadrants"], work=workstation(index=3)))
vdi_arcs.register_call("elliptical pie, wraps past 0", "VDI_ROM_GDP_ELL", (),
                       ell_pokes(VDI_GDP_ELLIPTICAL_PIE, *SWEEPS["wraps past 0"]))
vdi_arcs.register_call("elliptical arc, one quadrant", "VDI_ROM_GDP_ELL", (),
                       ell_pokes(VDI_GDP_ELLIPTICAL_ARC, *SWEEPS["first quadrant"]))
vdi_arcs.register_call("elliptical arc, clipped away", "VDI_ROM_GDP_ELL", (),
                       ell_pokes(VDI_GDP_ELLIPTICAL_ARC, *SWEEPS["first quadrant"], xc=-200))
