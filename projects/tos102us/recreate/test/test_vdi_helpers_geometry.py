"""The VDI's CLIPPING and GDP helpers (`src/vdi/helpers.c`): clip_code, clc_nsteps, quad_xform, and the
fill-attribute pair s_fa_attr / r_fa_attr a filled outline borrows the workstation through.

Alcyon calls all, entered by `jsr` with their word arguments (`test/vdi_helpers.py`). The attribute pair
takes none and works on the workstation LINEA_CUR_WORK names, so its cases stage a workstation AS THE
DISPATCHER LEAVES IT (`vdi.dispatched_pokes` / `vdi.virtual_workstation`), whose GDP-scratch words and
Line-A copies start stale so that every store shows.
"""
import pytest

from harness import addrs

import case
import vdi
import vdi_helpers
from vdi_helpers import answer, run_call

WORD_BYTES = vdi_helpers.WORD_BYTES
STALE = 0x5A5A


# ---- clip_code, $fcc092 ----------------------------------------------------------------------------
LEFT, RIGHT, ABOVE, BELOW = 1, 2, 4, 8
CLIP = {"XMINCL": 10, "YMINCL": 20, "XMAXCL": 100, "YMAXCL": 50}


def clip_code(x, y, rectangle=None):
    pokes = vdi.linea_pokes(**(rectangle or CLIP))
    return answer(run_call("VDI_ROM_CLIP_CODE", case.word_args(x, y), (x, y), pokes))


@pytest.mark.parametrize("x,y,code", (
    (50, 30, 0), (10, 20, 0), (100, 50, 0),                      # inside, and both corners: inclusive
    (9, 30, LEFT), (101, 30, RIGHT), (50, 19, ABOVE), (50, 51, BELOW),
    (9, 19, LEFT + ABOVE), (101, 51, RIGHT + BELOW), (9, 51, LEFT + BELOW), (101, 19, RIGHT + ABOVE),
    (-32768, 32767, LEFT + BELOW), (32767, -32768, RIGHT + ABOVE),  # signed compares
))
def test_clip_code_is_the_outcode(x, y, code):
    assert clip_code(x, y) == code


def test_clip_code_compares_signed_against_a_negative_rectangle():
    rectangle = {"XMINCL": -50, "YMINCL": -40, "XMAXCL": -10, "YMAXCL": -5}
    assert clip_code(-30, -20, rectangle) == 0
    assert clip_code(0, -41, rectangle) == RIGHT + ABOVE


# ---- clc_nsteps, $fcc6b4 ---------------------------------------------------------------------------

def clc_nsteps(xrad, yrad):
    pokes = vdi.linea_pokes(GDP_XRAD=xrad, GDP_YRAD=yrad, GDP_N_STEPS=STALE)
    return run_call("VDI_ROM_CLC_NSTEPS", {}, (), pokes)


@pytest.mark.parametrize("xrad,yrad,steps", (
    (0, 0, 32), (127, 0, 32), (131, 0, 32), (132, 0, 33), (0, 200, 50), (200, 199, 50), (199, 200, 50),
    (100, 100, 32), (512, 3, 128), (515, 0, 128), (516, 0, 128), (0x7FFF, 0, 128), (-400, -8, 32),
    (-32768, 600, 128),
))
def test_clc_nsteps_is_a_quarter_of_the_larger_radius_held_to_32_128(xrad, yrad, steps):
    assert clc_nsteps(xrad, yrad).linea("GDP_N_STEPS") == steps


# ---- quad_xform, $fcced6 ---------------------------------------------------------------------------
X_OUT = vdi_helpers.ANSWERS_AT
Y_OUT = X_OUT + WORD_BYTES


def quad_xform(quadrant, x, y):
    frame = case.args(">hhhII", quadrant, x, y, X_OUT, Y_OUT)
    pokes = {X_OUT: vdi.pack_words(STALE, STALE)}
    return run_call("VDI_ROM_QUAD_XFORM", frame, (quadrant, x, y, X_OUT, Y_OUT), pokes)


@pytest.mark.parametrize("quadrant", (1, 2, 3, 4))
@pytest.mark.parametrize("x,y", ((7, 9), (-7, 9), (-32768, 32767)))
def test_quad_xform_signs_the_point_into_its_quadrant(quadrant, x, y):
    result = quad_xform(quadrant, x, y)
    x_sign = 1 if quadrant in (1, 4) else -1
    y_sign = 1 if quadrant in (1, 2) else -1
    assert [vdi.signed_word(w) for w in result.words(X_OUT, 2)] == [vdi.signed_word((x_sign * x) & 0xFFFF),
                                                           vdi.signed_word((y_sign * y) & 0xFFFF)]


@pytest.mark.parametrize("quadrant", (0, 5, -1, 0x7FFF))
def test_quad_xform_outside_1_to_4_stores_nothing(quadrant):
    assert quad_xform(quadrant, 7, 9).words(X_OUT, 2) == [STALE, STALE]


# ---- s_fa_attr, $fcd056, and r_fa_attr, $fcd0c2 ----------------------------------------------------
WORKSTATION = {"FILL_COLOR": 3, "LINE_COLOR": 5, "FILL_PER": 0, "LINE_BEG": 1, "LINE_END": 2}
SAVED = ("GDP_SAVED_FILL_COLOR", "GDP_SAVED_FILL_PER", "GDP_SAVED_BEG_STYLE", "GDP_SAVED_END_STYLE")
# The Line-A words s_fa_attr overwrites, staged with values no arm stores so a skipped store shows.
LINE_A_STALE = {"LN_MASK": STALE, "PATPTR": 0x5A5A_5A5A, "PATMSK": STALE, "MULTIFILL": STALE,
                **{name: STALE for name in SAVED}}


def attribute_pokes(workstation_pokes=None):
    staged = workstation_pokes if workstation_pokes is not None else vdi.dispatched_pokes(**WORKSTATION)
    return vdi.merge_pokes(staged, vdi.linea_pokes(**LINE_A_STALE))


def s_fa_attr(pokes):
    return run_call("VDI_ROM_S_FA_ATTR", {}, (), pokes)


def r_fa_attr(pokes):
    return run_call("VDI_ROM_R_FA_ATTR", {}, (), pokes)


def test_s_fa_attr_saves_the_fill_and_sets_a_solid_outline_in_the_line_colour():
    result = s_fa_attr(attribute_pokes())
    assert [result.linea(name) for name in SAVED] == [3, 0, 1, 2]
    assert [result.workstation(name) for name in ("FILL_COLOR", "FILL_PER", "LINE_BEG", "LINE_END")] == [5, 1, 0, 0]
    assert result.linea("LN_MASK") == case.word_in(result.final, vdi.VDI_LINE_STYLES) == 0xFFFF
    assert (result.linea("PATPTR"), result.linea("PATMSK"), result.linea("MULTIFILL")) == (vdi.VDI_PATTERN_SOLID, 0, 0)


def test_s_fa_attr_works_on_the_workstation_cur_work_names():
    """A virtual workstation made current: its fields move and the physical record's do not."""
    staged = attribute_pokes(vdi.virtual_workstation(7, **WORKSTATION))
    result = s_fa_attr(staged)
    assert result.workstation("FILL_COLOR", at=vdi.VIRTUAL_WORK_AT) == 5
    assert not any(vdi.VDI_PHYS_WORK <= at < vdi.VDI_PHYS_WORK + vdi.WS_BYTES for at in result.info["writes"])


def test_r_fa_attr_puts_back_the_four_it_saved():
    saved = vdi.linea_pokes(GDP_SAVED_FILL_COLOR=9, GDP_SAVED_FILL_PER=1, GDP_SAVED_BEG_STYLE=2,
                            GDP_SAVED_END_STYLE=1)
    result = r_fa_attr(vdi.merge_pokes(attribute_pokes(), saved))
    assert [result.workstation(name) for name in ("FILL_COLOR", "FILL_PER", "LINE_BEG", "LINE_END")] == [9, 1, 2, 1]
    assert result.linea("LN_MASK") == STALE, "r_fa_attr leaves the Line-A pattern and style to the dispatcher"


def test_the_pair_round_trips_the_workstation():
    """s_fa_attr and then r_fa_attr, the second run starting from the machine the first ENDED in
    (`case.continued`): the workstation's four fields are what they were."""
    first = s_fa_attr(attribute_pokes())
    second = r_fa_attr(case.continued(first))
    assert [second.workstation(name) for name in ("FILL_COLOR", "FILL_PER", "LINE_BEG", "LINE_END")] == \
        [WORKSTATION[name] for name in ("FILL_COLOR", "FILL_PER", "LINE_BEG", "LINE_END")]


# ---- the rows Tier 3 prices ------------------------------------------------------------------------
vdi.register("vdi_clip_code, a corner", addrs.VDI_ROM_CLIP_CODE,
             vdi.merge_pokes(vdi.linea_pokes(**CLIP), case.word_args(101, 51)))
vdi.register("vdi_clip_code, inside", addrs.VDI_ROM_CLIP_CODE,
             vdi.merge_pokes(vdi.linea_pokes(**CLIP), case.word_args(50, 30)))
vdi.register("vdi_clc_nsteps, held to the minimum", addrs.VDI_ROM_CLC_NSTEPS,
             vdi.linea_pokes(GDP_XRAD=20, GDP_YRAD=10, GDP_N_STEPS=STALE))
vdi.register("vdi_clc_nsteps, within the bounds", addrs.VDI_ROM_CLC_NSTEPS,
             vdi.linea_pokes(GDP_XRAD=199, GDP_YRAD=200, GDP_N_STEPS=STALE))
vdi.register("vdi_quad_xform, the second quadrant", addrs.VDI_ROM_QUAD_XFORM,
             vdi.merge_pokes({X_OUT: vdi.pack_words(STALE, STALE)}, case.args(">hhhII", 2, 7, 9, X_OUT, Y_OUT)))
vdi.register("vdi_s_fa_attr, a solid outline in the line colour", addrs.VDI_ROM_S_FA_ATTR, attribute_pokes())
vdi.register("vdi_r_fa_attr, four fields put back", addrs.VDI_ROM_R_FA_ATTR, attribute_pokes())
