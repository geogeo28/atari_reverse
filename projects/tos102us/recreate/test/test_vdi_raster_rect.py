"""$a005 filled rectangle ($fcfc56) and vector 6's CPU body $fd1b16: `src/vdi/raster.c`.

    $fcfc56  d4-d7 = X1, Y1, X2, Y2 / CLIP: each edge clipped, the four STORED BACK ($fcfc98) — and on a
             miss too, as far as the clip had got ($fcfc50 `movem.w d4-d7,(a0) / rts`)
             d0/d1 = the groups, d4/d6 = FRINGE masks / move.l VECTOR_RECT_FILL,a5 / jmp (a5)
    $fd1b16  a frame of the loop's constants, then per row: jsr the WRT_MODE arm (the hline's own),
             the pattern row + 2 wrapped PAST PATMSK * 2, A1 on by WIDTH - planes * 2

Rectangles in every write mode and colour, over the canvas, with each ROM pattern and the multi-plane
user pattern over more rows than it has; a clip that cuts each edge, and one that misses on each side.
"""
import pytest

from harness import addrs

import vdi
import vdi_raster
from case import merge_pokes
from vdi_raster import MODES

# (x1, y1, x2, y2): one pixel; one group wide, over a whole 16-row pattern and past it; many groups.
RECTS = {"one pixel": (37, 90, 37, 90), "one group, 20 rows": (33, 5, 44, 24),
         "many groups": (5, 60, 300, 75), "two groups": (40, 100, 60, 103)}
# The clip the captured desktop has (the menu bar's 11 rows excluded) — and a tight one to cut each edge.
TIGHT_CLIP = (50, 20, 200, 40)


def rect_pokes(rect, *, mode, colour, pattern="solid", clip=None, extra=None):
    x1, y1, x2, y2 = rect
    patterned = vdi_raster.user_pattern_pokes() if pattern == "user" else vdi_raster.pattern_pokes(pattern)
    corners = vdi.linea_pokes(X1=x1, Y1=y1, X2=x2, Y2=y2)
    if clip is None:
        clipping = vdi.linea_pokes(CLIP=0)
    else:
        xmin, ymin, xmax, ymax = clip
        clipping = vdi.linea_pokes(CLIP=1, XMINCL=xmin, YMINCL=ymin, XMAXCL=xmax, YMAXCL=ymax)
    return vdi_raster.drawing_pokes(mode=mode, colour=colour, extra=merge_pokes(patterned, corners, clipping, extra))


def run(pokes):
    return vdi.run_primitive("LINEA_ROM_FILLED_RECT", {}, pokes)


def corners(result):
    return tuple(result.linea(name) for name in ("X1", "Y1", "X2", "Y2"))


@pytest.mark.parametrize("rect", RECTS.values(), ids=RECTS.keys())
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("colour", vdi_raster.COLOURS)
def test_every_mode_and_colour_unclipped(rect, mode, colour):
    result = run(rect_pokes(rect, mode=mode, colour=colour, pattern="8 rows"))
    assert corners(result) == rect, "unclipped, the corners are not written back"


@pytest.mark.parametrize("pattern", ("solid", "8 rows", "16-row hatch", "user"))
@pytest.mark.parametrize("mode", MODES)
def test_the_pattern_rows_wrap_across_more_rows_than_it_has(pattern, mode):
    """20 rows from y = 5: an 8-row pattern wraps twice and a 16-row one once, from row 5."""
    run(rect_pokes(RECTS["one group, 20 rows"], mode=mode, colour=0b0110, pattern=pattern))


def test_the_pattern_row_wraps_by_compare_not_by_mask():
    """The body steps the row by one word and resets it only PAST PATMSK * 2, so a PATMSK that is not
    2^n - 1 — here 5, over the 8-row pattern — cycles six rows where `y & PATMSK` would jump about.
    Line-A takes PATMSK from the caller, so this is a reachable input rather than a VDI one."""
    run(rect_pokes(RECTS["one group, 20 rows"], mode="replace", colour=0b1111, pattern="8 rows",
                   extra=vdi.linea_pokes(PATMSK=5)))


@pytest.mark.parametrize("shape", (vdi_raster.MEDIUM, vdi_raster.HIGH), ids=("medium", "high"))
@pytest.mark.parametrize("mode", MODES)
def test_fewer_planes(shape, mode):
    run(rect_pokes(RECTS["many groups"], mode=mode, colour=0b0101, pattern="16-row hatch",
                   extra=vdi_raster.geometry_pokes(shape)))


def test_rows_step_by_width_and_start_by_bytes_lin():
    """The first row is placed with BYTES_LIN ($fd1b2e) and each next one WIDTH on ($fd1b50): with the
    two different, the rectangle shears — which pins which field each step reads."""
    run(rect_pokes(RECTS["one group, 20 rows"], mode="replace", colour=0b1010,
                   extra=vdi_raster.width_skew_pokes(vdi_raster.WIDTH_SKEWS[1])))


# ---- clipping -----------------------------------------------------------------------------------------
# Each edge cut: (x1, y1, x2, y2) straddling one side of TIGHT_CLIP, then one straddling all four.
CUTS = {"left": (10, 25, 100, 30), "right": (100, 25, 250, 30), "top": (60, 5, 70, 30),
        "bottom": (60, 25, 70, 90), "all four": (0, 0, 319, 199), "inside": (60, 25, 70, 30),
        # ...and each side only TOUCHED: a far corner exactly on the clip edge still draws that one line
        "touching left": (10, 25, 50, 30), "touching right": (200, 25, 250, 30),
        "touching top": (60, 5, 70, 20), "touching bottom": (60, 40, 70, 90)}
# ...and each side missed: wholly left, right, above, below — and one the x clip trims before y misses.
MISSES = {"left": (10, 25, 40, 30), "right": (210, 25, 250, 30), "above": (60, 5, 70, 15),
          "below": (60, 50, 70, 60), "x trimmed, then y missed": (10, 50, 100, 60)}


def clipped(rect, clip):
    x1, y1, x2, y2 = rect
    xmin, ymin, xmax, ymax = clip
    return max(x1, xmin), max(y1, ymin), min(x2, xmax), min(y2, ymax)


@pytest.mark.parametrize("rect", CUTS.values(), ids=CUTS.keys())
@pytest.mark.parametrize("mode", MODES)
def test_a_clip_that_cuts_each_edge(rect, mode):
    result = run(rect_pokes(rect, mode=mode, colour=0b1001, pattern="user", clip=TIGHT_CLIP))
    assert corners(result) == clipped(rect, TIGHT_CLIP), "the clipped corners are stored back"


@pytest.mark.parametrize("rect", MISSES.values(), ids=MISSES.keys())
def test_a_clip_that_misses_draws_nothing_but_stores_what_it_had_clipped(rect):
    x1, y1, x2, y2 = rect
    xmin, _ymin, _xmax, _ymax = TIGHT_CLIP
    result = run(rect_pokes(rect, mode="replace", colour=0b1111, clip=TIGHT_CLIP))
    assert not any(vdi.SCREEN.base <= at < vdi.SCREEN.base + vdi.SCREEN.bytes for at in result.info["writes"])
    if rect == MISSES["x trimmed, then y missed"]:
        assert corners(result) == (xmin, y1, x2, y2), "X1 was clipped before Y missed, and is stored"


# ---- the body, entered directly -----------------------------------------------------------------------

def body_registers(rect):
    """What `$fcfc56` hands vector 6."""
    x1, y1, x2, y2 = rect
    left_group, words, left, right = vdi_raster.span_fringes(x1, x2)
    return {**vdi_raster.RECT_BODY_REGISTERS, "d0": left_group, "d1": words, "d4": left, "d5": y1,
            "d6": right, "d7": y2}


@pytest.mark.parametrize("rect", RECTS.values(), ids=RECTS.keys())
@pytest.mark.parametrize("mode", MODES)
def test_the_cpu_body_entered_directly(rect, mode):
    vdi.run_primitive("LINEA_ROM_CPU_RECT_FILL", body_registers(rect),
                      rect_pokes((0, 0, 0, 0), mode=mode, colour=0b0011, pattern="user"))


vdi_raster.register("one pixel, replace", "LINEA_ROM_FILLED_RECT", rect_pokes(RECTS["one pixel"], mode="replace", colour=0b0101))
vdi_raster.register("20 rows, transparent user pattern", "LINEA_ROM_FILLED_RECT",
                    rect_pokes(RECTS["one group, 20 rows"], mode="transparent", colour=0b1010, pattern="user"))
vdi_raster.register("many groups, clipped, xor", "LINEA_ROM_FILLED_RECT",
                    rect_pokes(CUTS["left"], mode="xor", colour=0, pattern="8 rows", clip=TIGHT_CLIP))
vdi_raster.register("clipped out", "LINEA_ROM_FILLED_RECT",
                    rect_pokes(MISSES["x trimmed, then y missed"], mode="replace", colour=1, clip=TIGHT_CLIP))
# The body's six register arguments take seven C arguments, past the six a Tier 3 call can pass
# (`harness.STACK_ARGS_BYTES`): its C is priced inside every row above, and the `.S` on rows of its own.
for label, rect, mode in (("one pixel, replace", "one pixel", "replace"), ("many groups, reverse", "many groups", "reverse")):
    vdi_raster.register(label, "LINEA_ROM_CPU_RECT_FILL", rect_pokes((0, 0, 0, 0), mode=mode, colour=0b0110,
                                                                pattern="16-row hatch"),
                        regs=body_registers(RECTS[rect]), c_row=False)
