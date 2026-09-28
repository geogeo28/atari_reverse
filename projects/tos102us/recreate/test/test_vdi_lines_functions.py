"""The two functions (`src/vdi/lines.c`): v_pline ($fcb9e0, opcode 6) and v_pmarker ($fcba7a, opcode 7), entered
as the dispatcher's `jsr` leaves the machine over a DISPATCHED workstation.

    $fcb9e0  LN_MASK = VDI_LINE_STYLES[LINE_INDEX] below 6 (a negative index reads the words before the table),
             else UD_LS; COLBITn = LINE_COLOR & 1 << n; width exactly 1: polyline, then arrow when BEG|END bit 0;
             any other width: wline
    $fcba7a  LINE_INDEX / COLOR / WIDTH / BEG / END saved and set to 0 / MARK_COLOR / 1 / 0 / 0, LINEA_CLIP = 1
             (left set); per point, the shape MARK_INDEX names: per polyline, contrl[1] = its count (left at the
             last), its offsets * MARK_SCALE (low word) + the point into the frame, PTSIN at it, v_pline; PTSIN
             back, the five fields back

WHAT IS NOT STAGED: a WS_MARK_INDEX outside the six shapes takes its shape pointer from the neighbouring switch
tables' code addresses and reads 68000 code as counts — vsm_type never stores one.
"""
import pytest

from harness import addrs

import vdi
import vdi_lines
import vdi_raster
from case import merge_pokes
from vdi_lines import WIDEST, circle_pokes, line_workstation

PATH = [(20, 30), (140, 90), (60, 170), (300, 120)]


def pline_pokes(path=PATH, *, count=None, **fields):
    return vdi_lines.path_pokes("VDI_ROM_V_PLINE", path, line_workstation(onto=circle_pokes(5), **fields),
                                count=count)


def run_pline(pokes, **kwargs):
    return vdi_lines.run_function("VDI_ROM_V_PLINE", pokes, **kwargs)


ARROW_END_BIT = vdi_lines.ENDS["arrow"]


def reaches_arrow(width, begin, end):
    """Whether v_pline's one-pixel path calls arrow — which runs unpoisoned (`vdi.READS_A_POINTER_IT_WRITES`)."""
    return width == 1 and (vdi_lines.ENDS[begin] | vdi_lines.ENDS[end]) & ARROW_END_BIT


# ---- v_pline -------------------------------------------------------------------------------------------
LINE_INDEXES = (0, 1, 2, 3, 4, 5, 6, 7, -1, -3, -32768)


@pytest.mark.parametrize("index", LINE_INDEXES)
def test_v_pline_every_line_style(index):
    """The six ROM styles, the user style from 6 on, and negative indexes reading the words below the table —
    over no points, since every line $a003 draws rotates LN_MASK."""
    result = run_pline(pline_pokes(index=index, UD_LS=0x3C3C, count=0))
    expected = 0x3C3C if index >= vdi_lines.VDI_LINE_STYLE_USER else vdi.rom_word(vdi.VDI_LINE_STYLES + 2 * index)
    assert result.linea("LN_MASK") == expected


@pytest.mark.parametrize("colour", (0, 0b0101, 0b1010, 0b1111, 0xFFF0 | 0b0110))
def test_v_pline_colour_bits(colour):
    result = run_pline(pline_pokes(colour=colour))
    assert [result.linea(name) for name in vdi_raster.COLBITS] == [colour & 1 << plane for plane in range(4)]


@pytest.mark.parametrize("mode", vdi_raster.MODES)
@pytest.mark.parametrize("width", (1, 3, 11))
def test_v_pline_every_mode_and_width(mode, width):
    run_pline(pline_pokes(mode=mode, width=width, index=3))


@pytest.mark.parametrize("width", (0, -3, 2), ids=("0", "-3", "2"))
def test_v_pline_staged_widths_other_than_1_go_to_wline(width):
    """Only a width of exactly 1 is a polyline: 0 and below are wide lines too (a radius of 0)."""
    run_pline(pline_pokes(width=width))


@pytest.mark.parametrize("ends", (("arrow", "square"), ("square", "arrow"), ("arrow", "arrow"), ("round", "round"),
                                  ("arrow and round bits", "square")), ids=str)
@pytest.mark.parametrize("width", (1, 5), ids=("one pixel", "wide"))
def test_v_pline_arrowheads(ends, width):
    begin, end = ends
    unpoisoned = vdi.READS_A_POINTER_IT_WRITES if reaches_arrow(width, begin, end) else {}
    run_pline(pline_pokes(width=width, begin=begin, end=end), **unpoisoned)


@pytest.mark.parametrize("clip", (None, (40, 40, 200, 150)), ids=("unclipped", "tight"))
def test_v_pline_clipped(clip):
    run_pline(pline_pokes(clip=clip, width=1))


def test_v_pline_a_virtual_workstation():
    work = vdi.virtual_workstation(7, onto=merge_pokes(vdi_raster.CANVAS, circle_pokes(5)), LINE_WIDTH=WIDEST,
                                   LINE_COLOR=0b0011, LINE_INDEX=1, LINE_BEG=2, LINE_END=1, CLIP=0)
    run_pline(vdi_lines.path_pokes("VDI_ROM_V_PLINE", PATH, work))


@pytest.mark.parametrize("count", (0, 1), ids=("no points", "one point"))
def test_v_pline_a_wide_line_of_fewer_than_two_points(count):
    run_pline(pline_pokes(width=9, count=count, end="round"))


# ---- v_pmarker -----------------------------------------------------------------------------------------
MARKS = [(40, 40), (100, 60), (3, 12), (318, 198), (160, 100)]
MARKER_TYPES = range(6)


def pmarker_pokes(marks=MARKS, *, index=2, scale=1, colour=0b1101, count=None, **fields):
    work = line_workstation(width=WIDEST, colour=0b0010, index=4, begin="arrow", end="round", MARK_INDEX=index,
                            MARK_SCALE=scale, MARK_COLOR=colour, **fields)
    return vdi_lines.path_pokes("VDI_ROM_V_PMARKER", marks, work, count=count)


def run_pmarker(pokes):
    return vdi_lines.run_function("VDI_ROM_V_PMARKER", pokes)


@pytest.mark.parametrize("index", MARKER_TYPES)
@pytest.mark.parametrize("scale", (1, 3, -2))
def test_v_pmarker_every_shape(index, scale):
    """Each shape at three scales, the borrowed line fields put back and CLIP left set."""
    result = run_pmarker(pmarker_pokes(index=index, scale=scale))
    assert result.workstation("LINE_WIDTH") == WIDEST and result.linea("CLIP") == 1


@pytest.mark.parametrize("mode", vdi_raster.MODES)
def test_v_pmarker_every_mode(mode):
    run_pmarker(pmarker_pokes(index=5, mode=mode, scale=4))


# Shape 1 (the cross) is two polylines of TWO points: over the five marks the caller asked for, contrl[1] is left
# at 2 — a count the caller's own 5 could not stand in for.
CROSS = 1
CROSS_POLYLINE_POINTS = 2


def test_v_pmarker_leaves_contrl_1_at_the_last_polyline_s_count():
    result = run_pmarker(pmarker_pokes(index=CROSS))
    assert len(MARKS) != CROSS_POLYLINE_POINTS
    assert result.contrl(vdi.CONTRL_N_PTSIN) == CROSS_POLYLINE_POINTS


@pytest.mark.parametrize("count", (0, 1), ids=("no marks", "one mark"))
def test_v_pmarker_few_marks(count):
    run_pmarker(pmarker_pokes(count=count))


def test_v_pmarker_clipped_by_the_workstation_s_rectangle():
    run_pmarker(pmarker_pokes(index=4, scale=6, clip=(30, 30, 110, 70)))


def test_v_pmarker_clips_whatever_the_workstation_says():
    """CLIP 0 in the workstation and its copy: v_pmarker sets LINEA_CLIP itself, so a mark across the copied
    rectangle's top (row 11) is still cut there."""
    run_pmarker(pmarker_pokes([(3, 12), (160, 8)], index=4, scale=5, clip=None))


def test_v_pmarker_a_scale_past_a_word():
    """The offset times the scale is `muls.w`, and only its low word is added to the point."""
    run_pmarker(pmarker_pokes(index=1, scale=0x4001))


# contrl laid over the marks so that contrl[1] is the SECOND mark's x: the count is read once, before any
# polyline stores its own count there — which the second mark then reads as its x.
def test_v_pmarker_reads_each_mark_after_the_marks_before_it_are_drawn():
    marks = [(80, 80), (5, 60), (120, 150)]
    pokes = merge_pokes(pmarker_pokes(marks, index=1),
                        vdi.linea_pokes(CONTRL=vdi.VDI_PTSIN_COPY + vdi.VDI_POINT_BYTES - vdi.CONTRL_N_PTSIN))
    pokes = merge_pokes(pokes, {vdi.VDI_PTSIN_COPY + vdi.VDI_POINT_BYTES: vdi.pack_words(len(marks))})
    run_pmarker(pokes)


# ---- Tier 3 --------------------------------------------------------------------------------------------
vdi.register("vdi_v_pline, one pixel, dash-dot, both arrowheads", addrs.VDI_ROM_V_PLINE,
             pline_pokes(index=3, begin="arrow", end="arrow"))
vdi.register("vdi_v_pline, width 9, round ends", addrs.VDI_ROM_V_PLINE, pline_pokes(width=9, begin="round", end="round"))
vdi.register("vdi_v_pline, one pixel, no points", addrs.VDI_ROM_V_PLINE, pline_pokes(count=0))
vdi.register("vdi_v_pmarker, five crosses", addrs.VDI_ROM_V_PMARKER, pmarker_pokes(index=1))
vdi.register("vdi_v_pmarker, one dot", addrs.VDI_ROM_V_PMARKER, pmarker_pokes(index=0, count=1))
