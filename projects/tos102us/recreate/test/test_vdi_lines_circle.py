"""The quarter circle and what is drawn from it (`src/vdi/lines.c`): cir_dda ($fcca86), perp_off ($fccd92) and
do_circ ($fccf4e) — Alcyon calls, entered by `jsr` over their frames.

    $fcca86  NUM_QC_LINES = width * pw / ph / 2 + 1 (each product's low word); LINE_CW = width; the octant by
             the midpoint rule over radius (width + 1) / 2, Q[y] = x then Q[x] = y; then each of NUM_QC_LINES
             rows the average of the octant rows (2i + 1) * ph / pw / 2 spans — in place
    $fccd92  the quadrant of (x, y); quad_xform to |x|, |y|; walk (Q[r], r) from r = 0 while the word cross
             product |Q[r]·|y| - r·|x|| shrinks (ties to the nearer-diagonal point); quad_xform back in place
    $fccf4e  nothing unless NUM_QC_LINES > 0; row 0, then rows -k and +k: X1 = x - Q[k], X2 = Q[k] + x, clip_line
             (whatever CLIP says), $a003

WHAT IS NOT STAGED, and why: a pixel height of 0, or an aspect wider than tall, divides by zero in cir_dda
(vector 5 — the host core refuses it by name); a width whose radius doubles past a word (32,767 and up) walks the
octant out of RAM; perp_off over a quarter circle cir_dda never built can walk off its end; perp_off's first cross
product at exactly 32,767 is compared with two locals nothing has stored yet (stack garbage in the ROM).
"""
import pytest


import vdi
import vdi_lines
import vdi_raster
from case import merge_pokes
from vdi_lines import ASPECTS, OFFSET_AT, WIDEST, circle_pokes

# ---- cir_dda ------------------------------------------------------------------------------------------
STALE_CIRCLE = tuple(0x5A00 + row for row in range(vdi_lines.QUARTER_CIRCLE_WORDS))


def cir_dda_pokes(width, aspect="low"):
    """The width in a dispatched workstation, the aspect, and a quarter circle of stale words — so every word
    cir_dda writes shows, and every word it leaves keeps its stale value."""
    return merge_pokes(vdi.dispatched_pokes(LINE_WIDTH=width), vdi_lines.aspect_pokes(aspect),
                       vdi.linea_pokes(Q_CIRCLE=STALE_CIRCLE, NUM_QC_LINES=0x5A5A, LINE_CW=0x5A5A))


def run_cir_dda(width, aspect="low"):
    return vdi_lines.run_call("VDI_ROM_CIR_DDA", (), cir_dda_pokes(width, aspect))


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("width", range(1, WIDEST + 1, 2))
def test_cir_dda_every_width_vsl_width_leaves(aspect, width):
    result = run_cir_dda(width, aspect)
    assert result.linea("LINE_CW") == width


@pytest.mark.parametrize("width", (0, 2, 4, 10, 40, -1, -2, -5))
def test_cir_dda_staged_widths(width):
    """Even widths (a record vsl_width never leaves) and none: a width of 0 or below has a radius of 0, so the
    octant is one word; NUM_QC_LINES counts from the product's sign."""
    run_cir_dda(width)


# The octant's last row reaches Q[radius]: width 79 writes Q[40], which is LINEA_STR_MODE.
PAST_THE_QUARTER_CIRCLE = 79


def test_cir_dda_a_staged_width_past_the_quarter_circle_writes_str_mode():
    """The octant reaches Q[radius] = Q[40], which is the string input mode: nothing bounds the width."""
    pokes = merge_pokes(cir_dda_pokes(PAST_THE_QUARTER_CIRCLE), vdi.linea_pokes(STR_MODE=0x5A5A))
    assert vdi_lines.run_call("VDI_ROM_CIR_DDA", (), pokes).linea("STR_MODE") != 0x5A5A


@pytest.mark.parametrize("pixel_size", ((1, 32767), (-338, 372), (338, -372), (32767, 32767), (-32768, -1)),
                         ids=("thin", "negative width", "negative height", "large", "divs overflow"))
def test_cir_dda_products_past_a_word(pixel_size):
    """Products whose low word is all the ROM divides; a quotient `divs.w` overflows (-32768 / -1) leaves
    its dividend. Each staged so every row spans at least one octant row (no zero divide)."""
    pokes = merge_pokes(cir_dda_pokes(9), {vdi_lines.PIXEL_SIZE_AT: vdi.pack_words(*pixel_size)})
    vdi_lines.run_call("VDI_ROM_CIR_DDA", (), pokes)


def test_cir_dda_a_virtual_workstation():
    pokes = merge_pokes(vdi.virtual_workstation(5, LINE_WIDTH=13), vdi_lines.aspect_pokes("low"),
                        vdi.linea_pokes(Q_CIRCLE=STALE_CIRCLE))
    assert vdi_lines.run_call("VDI_ROM_CIR_DDA", (), pokes).linea("LINE_CW") == 13


# ---- perp_off ------------------------------------------------------------------------------------------
# Directions round the compass and on both axes, near-diagonal ones where the walk ties, and ones whose
# products overflow a word (the cross product then wraps).
DIRECTIONS = [(dx, dy) for dx in (-9, -3, 0, 2, 7) for dy in (-8, -1, 0, 5, 11)] + [
    (300, 300), (-300, 300), (41, -40), (1000, 1), (1, 1000), (-32768, 5), (5, -32768), (32767, 32767),
    (20000, -30000), (-12345, 6789), (0, -32768),
    # neg.w leaves -32768 across: row 1's cross product has the low word $8000, which reads NEGATIVE, so the walk
    # leaves row 0 and the left half's quadrant (2 or 3 by y's sign, y == 0 here) decides which way y points.
    (-32768, 0)]
PERP_WIDTHS = (3, 5, 15, WIDEST)


def perp_off_pokes(width, direction, aspect="low"):
    return merge_pokes(circle_pokes(width, aspect), {OFFSET_AT: vdi.pack_words(*direction)})


def run_perp_off(width, direction, aspect="low"):
    return vdi_lines.run_call("VDI_ROM_PERP_OFF", (OFFSET_AT, OFFSET_AT + vdi.WORD_BYTES),
                              perp_off_pokes(width, direction, aspect))


@pytest.mark.parametrize("width", PERP_WIDTHS)
@pytest.mark.parametrize("direction", DIRECTIONS, ids=str)
def test_perp_off(width, direction):
    """The answer is a point of the quarter circle, signed back into the direction's quadrant."""
    result = run_perp_off(width, direction)
    _x, y = (vdi.signed_word(word) for word in result.words(OFFSET_AT, 2))
    rows, _width, _circle = vdi_lines.quarter_circle(width)
    assert abs(y) < rows


@pytest.mark.parametrize("aspect", ("medium", "high"))
@pytest.mark.parametrize("direction", ((5, 11), (-9, 2), (7, -1)), ids=str)
def test_perp_off_other_aspects(aspect, direction):
    run_perp_off(9, direction, aspect)


# A first cross product one short of the walk's starting best: Q[0] * |y| = 32,766 over width 1's circle (Q[0] =
# 1) and width 3's (Q[0] = 2) — updated, where a best starting lower would compare it with the two locals
# nothing has stored yet. (32,767 itself is that comparison, and is not staged: see the module docstring.)
@pytest.mark.parametrize("width,direction", ((1, (5, 32766)), (3, (-7, 16383))), ids=("width 1", "width 3"))
def test_perp_off_a_first_cross_product_one_under_the_start(width, direction):
    run_perp_off(width, direction)


def test_perp_off_the_last_row_down_to_x_1():
    """A near-horizontal direction walks to the last row, and down it until x is 1."""
    run_perp_off(WIDEST, (1, 32767))


# ---- do_circ -------------------------------------------------------------------------------------------

def do_circ_pokes(width, *, mode="replace", colour=0b1011, clip=(0, 0, 319, 199), style=0xFFFF, lstlin=0,
                  aspect="low"):
    xmin, ymin, xmax, ymax = clip
    return vdi_raster.drawing_pokes(mode=mode, colour=colour, extra=merge_pokes(
        circle_pokes(width, aspect), vdi.linea_pokes(LN_MASK=style, LSTLIN=lstlin, CLIP=0, XMINCL=xmin,
                                                     YMINCL=ymin, XMAXCL=xmax, YMAXCL=ymax)))


def run_do_circ(centre, pokes):
    return vdi_lines.run_call("VDI_ROM_DO_CIRC", centre, pokes)


@pytest.mark.parametrize("width", (3, 7, 15, WIDEST))
@pytest.mark.parametrize("mode", vdi_raster.MODES)
def test_do_circ_every_mode(width, mode):
    run_do_circ((100, 80), do_circ_pokes(width, mode=mode))


@pytest.mark.parametrize("centre", ((2, 3), (318, 100), (160, 198), (-5, 50), (400, 400)), ids=str)
def test_do_circ_clipped_at_every_edge_and_wholly_off(centre):
    """clip_line is asked whatever CLIP says (it is staged 0): rows cut at the clip's sides, rows above and
    below it dropped, and a disc wholly off the screen draws nothing."""
    run_do_circ(centre, do_circ_pokes(WIDEST))


def test_do_circ_a_tight_clip_and_a_dashed_style():
    run_do_circ((100, 80), do_circ_pokes(15, clip=(95, 75, 104, 84), style=0xF0F0, mode="xor", lstlin=1))


@pytest.mark.parametrize("aspect", ("medium", "high"))
def test_do_circ_other_aspects(aspect):
    run_do_circ((100, 80), do_circ_pokes(11, aspect=aspect))


@pytest.mark.parametrize("rows", (0, -3), ids=("none", "negative"))
def test_do_circ_draws_nothing_without_rows(rows):
    """The snapshot's own state (NUM_QC_LINES 0) and a negative count: the `ble` leaves before any store."""
    pokes = merge_pokes(do_circ_pokes(9), vdi.linea_pokes(NUM_QC_LINES=rows, X1=0x5A5A))
    assert run_do_circ((100, 80), pokes).linea("X1") == 0x5A5A


# ---- Tier 3 --------------------------------------------------------------------------------------------
vdi_lines.register_call("the widest line", "VDI_ROM_CIR_DDA", (), cir_dda_pokes(WIDEST))
vdi_lines.register_call("a one-pixel line", "VDI_ROM_CIR_DDA", (), cir_dda_pokes(1))
vdi_lines.register_call("width 15, a steep direction", "VDI_ROM_PERP_OFF", (OFFSET_AT, OFFSET_AT + vdi.WORD_BYTES),
                        perp_off_pokes(15, (-3, 11)))
vdi_lines.register_call("the widest, a shallow direction", "VDI_ROM_PERP_OFF", (OFFSET_AT, OFFSET_AT + vdi.WORD_BYTES),
                        perp_off_pokes(WIDEST, (300, 7)))
vdi_lines.register_call("width 15, replace", "VDI_ROM_DO_CIRC", (100, 80), do_circ_pokes(15))
vdi_lines.register_call("width 3, xor", "VDI_ROM_DO_CIRC", (100, 80), do_circ_pokes(3, mode="xor"))
