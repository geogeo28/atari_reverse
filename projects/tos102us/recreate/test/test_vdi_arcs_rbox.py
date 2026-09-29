"""The rounded box (`src/vdi/arcs.c`): gdp_rbox ($fcc284), an Alcyon call entered by `jsr` from vdi_gdp's arms 8
and 9 with A5 = LINEA_PTSIN, as the arm leaves it (`test/vdi_arcs.py`).

    $fcc284  arb_corner(A5, 0); X1..Y2 = ptsin[0..3] (Y1 the lower edge); XRAD = DEV_TAB[0] >> 6 held to
             (X2 - X1) / 2, YRAD = smul_div(XRAD, DEV_TAB[3], DEV_TAB[4]) held to (Y1 - Y2) / 2; the quarter-round
             (0, YRAD), (XRAD cos, YRAD sin) at 67.5 / 45 / 22.5 degrees, (XRAD, 0) into ptsin[0..9]; the lower
             right corner at words 10.., the lower left at 20.., the upper left at 30.., the upper right over the
             quarter-round at 0.., each about XC / YC re-read at every store; point 20 = point 0; contrl[1] = 21;
             GDP 8: LN_MASK by WS_LINE_INDEX, COLBIT from WS_LINE_COLOR, polyline at width 1 else wline;
             otherwise plygn

THE ATTRIBUTION PASS IS OFF for the wide outline (wline puts LINEA_PTSIN back after each segment, and the
poisoned run would build the box through an inverted PTSIN). Every other case runs poisoned.

BOXES WIDER OR TALLER THAN A WORD (`WRAPPED`): X2 - X1 or Y1 - Y2 wraps (`sub.w`), so the radius is held to a
negative half-size and the corners wrap. Their OUTLINES go through clip_line on wrapped endpoints, which on some
geometries never ends — so each one (the filled too: a core that outlined it would cycle there) first runs the
host core alone in a child process (`host_returns`), and a reconstruction that cycles where the ROM returns
FAILS there rather than hanging the suite.

UNPINNED: a GDP number other than 8 or 9 (vdi_gdp's switch sends only those here, and every other is plygn's);
the outlines whose wrapped segments send clip_line ($fcbf16) into a cycle — HUGE outlined at any width,
(0, 40, 32767, 160) at width 3, (-16384, 40, 16400, 160) and the flat (-20000, 100, 20000, 100): no rts, the
whole machine state repeating with a period of 196 instructions (HUGE, measured). The box's body up to its
`bsr polyline` is the filled one's, which HUGE stages.
"""
import subprocess

import pytest

from harness import BASE_IMAGE

import vdi
import vdi_arcs
import vdi_helpers
import vdi_lines
import vdi_raster
from case import merge_pokes
from vdi_arcs import RBOX_REGISTERS, rbox_pokes

WIDE = vdi.READS_A_POINTER_IT_WRITES

# (x0, y0, x1, y1) as a caller may pass them: every corner order, boxes narrower / shorter than two radii (the
# radius held to the half-size), a line, a point.
BOXES = {"upper left, lower right": (40, 30, 200, 150), "lower right, upper left": (200, 150, 40, 30),
         "lower left, upper right": (40, 150, 200, 30), "upper right, lower left": (200, 30, 40, 150),
         "narrow": (100, 20, 106, 180), "short": (20, 90, 300, 93), "a line": (60, 100, 260, 100),
         "a point": (150, 120, 150, 120), "odd half-sizes": (33, 41, 70, 88)}
# Wider than a word: X2 - X1 wraps negative (`sub.w`), and so does the half-width the radius is held to.
HUGE = (-20000, 40, 20000, 160)
# ...and the wrapped boxes whose outlines the ROM finishes, at widths 1 and 3 (measured to an rts).
WRAPPED = {"x wraps, -100..32700": (-100, 40, 32700, 160), "x wraps to -32768": (-1, 40, 32767, 160),
           "a full word, -32768..32767": (-32768, 20, 32767, 190), "reversed, 100..-32700": (100, 50, -32700, 150),
           "both wrap": (-20000, -30000, 20000, 30000), "y wraps": (150, -20000, 170, 20000),
           "x wraps, 5..-32766": (5, 60, -32766, 120)}
# The host core runs such a box in milliseconds; a child still running after this has cycled.
HOST_RETURN_SECONDS = 10


def run_rbox(pokes, **kwargs):
    return vdi_arcs.run_call("VDI_ROM_GDP_RBOX", (), pokes, regs=RBOX_REGISTERS, **kwargs)


def host_returns(pokes):
    """The host gdp_rbox over `pokes`, alone in a child process: a core that cycles, or faults off the image,
    FAILS the case here, where the differential would hang or kill its worker."""
    try:
        returncode, stderr, _image = vdi_helpers.refusal_over(vdi.core_symbol("VDI_ROM_GDP_RBOX"), pokes,
                                                              seconds=HOST_RETURN_SECONDS, read_back=False)
    except subprocess.TimeoutExpired:
        pytest.fail(f"the host gdp_rbox did not return within {HOST_RETURN_SECONDS} s")
    assert returncode == 0, stderr


@pytest.mark.parametrize("name", BOXES)
@pytest.mark.parametrize("outlined", (True, False))
def test_rbox(name, outlined):
    result = run_rbox(rbox_pokes(BOXES[name], outlined=outlined, perimeter=1))
    assert result.word(vdi.CONTRL_AT + vdi.CONTRL_N_PTSIN) == vdi_arcs.VDI_RBOX_POINTS + (not outlined)


@pytest.mark.parametrize("index", range(7))
def test_outline_every_line_style(index):
    run_rbox(rbox_pokes(BOXES["upper left, lower right"], index=index, UD_LS=0xC3F1))


def test_outline_negative_style_reads_below_the_table():
    run_rbox(rbox_pokes(BOXES["odd half-sizes"], index=-2))


@pytest.mark.parametrize("mode", vdi_raster.MODES)
@pytest.mark.parametrize("colour", vdi_raster.COLOURS)
def test_outline_every_mode_and_colour(mode, colour):
    run_rbox(rbox_pokes(BOXES["lower left, upper right"], mode=mode, colour=colour, index=3))


@pytest.mark.parametrize("width", (3, 9))
def test_wide_outline(width):
    run_rbox(rbox_pokes(BOXES["upper right, lower left"], width=width), **WIDE)


@pytest.mark.parametrize("width", (-3, -1))
def test_a_negative_width_outlines_wide(width):
    """What vsl_width stores when a program lowered SIZ_TAB's widest line below 1 (`test_vdi_attr_line.py`,
    -3 comes back as -3): the box's `cmpi.w #1` / `bne` ($fcc60c) sends anything but 1 to wline."""
    table = vdi.linea(BASE_IMAGE, "SIZ_TAB")
    table[vdi.VDI_SIZ_TAB_MAX_LINE_WIDTH_INDEX] = width
    run_rbox(rbox_pokes(BOXES["upper left, lower right"], width=width, onto=vdi.linea_pokes(SIZ_TAB=table)), **WIDE)


@pytest.mark.parametrize("pattern", vdi_raster.PATTERNS)
@pytest.mark.parametrize("mode", vdi_raster.MODES)
def test_filled_every_pattern_and_mode(pattern, mode):
    run_rbox(rbox_pokes(BOXES["odd half-sizes"], outlined=False, pattern=pattern, mode=mode, perimeter=1))


@pytest.mark.parametrize("outlined", (True, False))
def test_clipped(outlined):
    run_rbox(rbox_pokes((-40, -20, 120, 90), outlined=outlined, clip=(10, 20, 100, 199)))


def test_wider_than_a_word():
    """Filled: the radius is held to the wrapped (negative) half-width, and plygn fills what that makes."""
    pokes = rbox_pokes(HUGE, outlined=False)
    host_returns(pokes)
    result = run_rbox(pokes)
    assert vdi.signed_word(result.linea("GDP_XRAD")) < 0


@pytest.mark.parametrize("name", WRAPPED)
def test_wrapped_filled(name):
    """"y wraps" is the one whose Y1 - Y2 wraps alone: YRAD held to the negative half-height."""
    pokes = rbox_pokes(WRAPPED[name], outlined=False)
    host_returns(pokes)
    run_rbox(pokes)


@pytest.mark.parametrize("name", WRAPPED)
def test_wrapped_wide_outline(name):
    """At width 3 (wline, which moves LINEA_PTSIN) the attribution pass is off; width 1 is the poisoned run below."""
    pokes = rbox_pokes(WRAPPED[name], width=3)
    host_returns(pokes)
    run_rbox(pokes, **WIDE)


@pytest.mark.parametrize("name", WRAPPED)
def test_wrapped_outline_poisoned(name):
    """At width 1 (polyline, which leaves LINEA_PTSIN alone) the attribution pass can stay on."""
    pokes = rbox_pokes(WRAPPED[name])
    host_returns(pokes)
    run_rbox(pokes)


@pytest.mark.parametrize("outlined", (True, False))
def test_unclipped_on_the_screen(outlined):
    run_rbox(rbox_pokes(BOXES["upper left, lower right"], outlined=outlined, clip=None))


@pytest.mark.parametrize("aspect", ("medium", "high"))
def test_other_resolutions(aspect):
    """DEV_TAB[0] 639 and the aspect: a radius of 9, the y radius scaled from it."""
    pokes = merge_pokes(rbox_pokes(BOXES["upper left, lower right"], outlined=False),
                        vdi.linea_pokes(DEV_TAB=[639]), vdi_lines.aspect_pokes(aspect))
    result = run_rbox(pokes)
    assert result.linea("GDP_XRAD") == 639 >> vdi_arcs.VDI_RBOX_RADIUS_SHIFT


@pytest.mark.parametrize("at", (vdi.LINEA_GDP_FILL_MAXY, vdi.LINEA_GDP_FILL_MINY, vdi.LINEA_GDP_BEG_ANG))
def test_the_centre_is_re_read_at_every_store(at):
    """PTSIN in the arc scratch: at FILL_MAXY the lower-right corner's second point is stored over XRAD and XC;
    at FILL_MINY its first point's y lands on XC before its x is placed about it (a backward corner stores y
    first); at BEG_ANG the lower-left corner's first y lands on XC just AFTER its x was placed (a forward one
    stores x first) — and every later store reads what they left (the box and the fill run over the moved words)."""
    pokes = merge_pokes(rbox_pokes((40, 30, 200, 150), outlined=False),
                        {at: vdi.pack_words(40, 30, 200, 150)}, vdi.pointer_pokes(ptsin=at))
    result = vdi_arcs.run_call("VDI_ROM_GDP_RBOX", (), pokes, regs={"a5": at})
    assert result.linea("GDP_XC") != 200 - 4


@pytest.mark.parametrize("outlined", (True, False))
def test_ptsin_is_read_again_after_the_sort(outlined):
    """PTSIN laid at $29a4, over Line-A's own INTIN low word, PTSIN and INTOUT high word: arb_corner's sort
    MOVES the pointer — x swapped (INTIN's low word, staged PTSIN_AT's, above $29a4), y swapped (0 below
    INTOUT's high word) — onto PTSIN_AT, where the box is staged, and the ROM reloads it after the sort
    ($fcc298 `movea.l $29a6,a5`) and builds the box there. A structural pin of the order, like
    `test_vs_clip_reads_the_ptsin_pointer_once_before_its_sort`: through the trap PTSIN is always the copy. A core
    that did NOT reload would build the box over Line-A's own pointers and follow them off the image, so it runs
    in a child first (`host_returns`)."""
    ptsin_at = vdi.field("LINEA", "PTSIN").at - vdi.WORD_BYTES
    moved_to = vdi.PTSIN_AT
    assert ptsin_at < (moved_to & 0xFFFF) and (moved_to >> 16) == (vdi.INTOUT_AT >> 16) > 0
    pokes = merge_pokes(rbox_pokes(BOXES["upper left, lower right"], outlined=outlined),
                        {moved_to: vdi.pack_words(*BOXES["upper left, lower right"])},
                        vdi.linea_pokes(PTSIN=ptsin_at, INTIN=moved_to, INTOUT=vdi.INTOUT_AT))
    host_returns(pokes)
    result = vdi_arcs.run_call("VDI_ROM_GDP_RBOX", (), pokes, regs={"a5": ptsin_at}, **vdi.READS_A_POINTER_IT_WRITES)
    assert result.linea("PTSIN") == moved_to


# ---- Tier 3: the outline at one pixel and wide, and the fill -------------------------------------------------
vdi_arcs.register_call("outlined, one pixel", "VDI_ROM_GDP_RBOX", (), rbox_pokes(BOXES["upper left, lower right"]),
                       regs=RBOX_REGISTERS)
vdi_arcs.register_call("outlined, width 3", "VDI_ROM_GDP_RBOX", (), rbox_pokes(BOXES["upper left, lower right"], width=3),
                       regs=RBOX_REGISTERS)
vdi_arcs.register_call("filled, outlined", "VDI_ROM_GDP_RBOX", (),
                       rbox_pokes(BOXES["odd half-sizes"], outlined=False, perimeter=1), regs=RBOX_REGISTERS)
vdi_arcs.register_call("a point, filled", "VDI_ROM_GDP_RBOX", (), rbox_pokes(BOXES["a point"], outlined=False),
                       regs=RBOX_REGISTERS)
