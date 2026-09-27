"""$a004 hline ($fca57e), its mid-function entries $fca58a / $fca5a2, and vector 8's CPU body $fd1ae0:
`src/vdi/raster.c`.

    $fca57e  a4 = $299a / d4-d6 = X1, Y1, X2
    $fca58a  a0 = PATPTR + (d5 & PATMSK) * 2 / d0 = MULTIFILL ? 32 : 0      <- the contour fill ($fcfb62)
    $fca5a2  d1/d2 = the groups, d4/d6 = FRINGE masks (one group: ANDed)   <- $a003's horizontal arm
             move.l VECTOR_HLINE,a5 / jmp (a5)
    $fd1ae0  a1 = the row's left group / jmp to WRT_MODE's arm ($fd1b0e) — the arms the rectangle shares

A span is drawn in EVERY write mode, in colours whose planes differ, over a canvas whose planes differ
(`vdi_raster.CANVAS`), at every shape a span can have: one pixel, inside one word, a whole word, two
words, and many — each fringe at column 0, 15 and between. The three mid entries are run with the
registers their real callers leave, and the body with what `$fca5a2` hands it.
"""
import pytest

from harness import addrs

import vdi
import vdi_raster
from case import merge_pokes
from vdi_raster import MODES

# (x1, x2) spans: one pixel; inside one group; one whole group; two groups, each fringe partial; and
# many groups with a partial and a whole fringe — and one ending on a group's LAST pixel.
SPANS = {"one pixel": (37, 37), "inside a group": (33, 44), "a whole group": (32, 47),
         "two groups": (40, 60), "many groups": (5, 300), "to a group's end": (16, 79)}
ROW = 101


def hline_pokes(span, *, mode, colour, pattern="solid", y=ROW, extra=None):
    x1, x2 = span
    patterned = vdi_raster.user_pattern_pokes() if pattern == "user" else vdi_raster.pattern_pokes(pattern)
    return vdi_raster.drawing_pokes(mode=mode, colour=colour,
                                    extra=merge_pokes(patterned, vdi.linea_pokes(X1=x1, Y1=y, X2=x2), extra))


def run(pokes):
    return vdi.run_primitive("LINEA_ROM_HLINE", {}, pokes)


@pytest.mark.parametrize("span", SPANS.values(), ids=SPANS.keys())
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("colour", vdi_raster.COLOURS)
def test_every_mode_and_colour_over_every_span(span, mode, colour):
    run(hline_pokes(span, mode=mode, colour=colour, pattern="8 rows"))


@pytest.mark.parametrize("colour", vdi_raster.COLOURS)
def test_a_solid_replace_span_is_the_colour_exactly_between_its_ends(colour):
    """The claim in pixels, besides the differential: x1..x2 become the colour, x1 - 1 and x2 + 1 do
    not change."""
    x1, x2 = SPANS["many groups"]
    result = run(hline_pokes((x1, x2), mode="replace", colour=colour))
    assert all(result.pixel(x, ROW) == colour for x in range(x1, x2 + 1))
    for outside in (x1 - 1, x2 + 1):
        assert result.pixel(outside, ROW) == vdi.read_pixel(vdi_raster.CANVAS_IMAGE, outside, ROW)


@pytest.mark.parametrize("pattern", ("solid", "8 rows", "16-row hatch", "user"))
@pytest.mark.parametrize("y", (ROW, 8, 15, 199))
@pytest.mark.parametrize("mode", MODES)
def test_the_pattern_row_is_y_masked_by_patmsk(pattern, y, mode):
    """PATPTR + (Y1 & PATMSK) * 2: the rows at y = 8, 15 and 199 are rows 0, 7/15 and 7/7 of an 8-row
    pattern and a 16-row one; the user pattern is MULTI-PLANE, so each plane reads its own 16 rows."""
    run(hline_pokes(SPANS["many groups"], mode=mode, colour=0b0110, pattern=pattern, y=y))


@pytest.mark.parametrize("skew", vdi_raster.WIDTH_SKEWS)
@pytest.mark.parametrize("mode", MODES)
def test_the_row_is_placed_by_bytes_lin_not_width(skew, mode):
    """Two fields hold a line's bytes, BYTES_LIN and WIDTH: the body places its one row by BYTES_LIN
    ($fd1ae6 `muls.w -2(a4),d5`). WIDTH a group off it either way puts any other reading on another row."""
    run(hline_pokes(SPANS["two groups"], mode=mode, colour=0b0101, extra=vdi_raster.width_skew_pokes(skew)))


@pytest.mark.parametrize("shape", (vdi_raster.MEDIUM, vdi_raster.HIGH), ids=("medium", "high"))
@pytest.mark.parametrize("mode", MODES)
def test_fewer_planes(shape, mode):
    run(hline_pokes(SPANS["many groups"], mode=mode, colour=0b0101, pattern="16-row hatch",
                    extra=vdi_raster.geometry_pokes(shape)))


# ---- the mid-function entries, with their callers' registers ---------------------------------------

@pytest.mark.parametrize("span", SPANS.values(), ids=SPANS.keys())
@pytest.mark.parametrize("mode", MODES)
def test_the_patterned_entry_takes_x1_y_x2_from_registers(span, mode):
    """$fca58a, as the contour fill enters it: D4 = x1, D5 = y, D6 = x2 — the Line-A X1/Y1/X2 are NOT
    read (staged elsewhere), and the pattern row is still y & PATMSK."""
    x1, x2 = span
    pokes = hline_pokes((0, 0), mode=mode, colour=0b1001, pattern="user", y=0)
    vdi.run_primitive("LINEA_ROM_HLINE_PATTERNED", {**vdi_raster.BASE_REGISTERS, "d4": x1, "d5": 57, "d6": x2}, pokes)


@pytest.mark.parametrize("stride", (0, vdi_raster.MULTIFILL_PLANE_WORDS * vdi.WORD_BYTES))
@pytest.mark.parametrize("span", SPANS.values(), ids=SPANS.keys())
@pytest.mark.parametrize("mode", MODES)
def test_the_span_entry_draws_through_the_pattern_word_at_a0(span, mode, stride):
    """$fca5a2, as $a003's horizontal arm enters it: A0 = LN_MASK's own address as a one-row pattern,
    stride 0 — and with a stride, the multi-plane user pattern's planes."""
    x1, x2 = span
    pattern_at = vdi.LINEA_LN_MASK if stride == 0 else vdi_raster.USER_PATTERN_AT
    pokes = hline_pokes((0, 0), mode=mode, colour=0b0011, pattern="user",
                        extra=vdi.linea_pokes(LN_MASK=vdi_raster.LINE_STYLES[3]))
    vdi.run_primitive("LINEA_ROM_HLINE_SPAN",
                      {**vdi_raster.BASE_REGISTERS, "d4": x1, "d5": 150, "d6": x2, "a0": pattern_at, "d0": stride},
                      pokes)


def body_registers(span, y, pattern_at, stride):
    """What `$fca5a2` hands vector 8, computed the way it does."""
    x1, x2 = span
    left_group, words, left, right = vdi_raster.span_fringes(x1, x2)
    return {**vdi_raster.BASE_REGISTERS, "d0": stride, "d1": left_group, "d2": words,
            "d4": left, "d5": y, "d6": right, "a0": pattern_at}


@pytest.mark.parametrize("span", SPANS.values(), ids=SPANS.keys())
@pytest.mark.parametrize("mode", MODES)
def test_the_cpu_body_entered_directly(span, mode):
    """$fd1ae0 by `jsr`, with the registers `$fca5a2` leaves: the contract the C front end calls it by."""
    pokes = hline_pokes((0, 0), mode=mode, colour=0b1100, pattern="user")
    vdi.run_primitive("LINEA_ROM_CPU_HLINE", body_registers(span, 33, vdi_raster.USER_PATTERN_AT + 6,
                                                         vdi_raster.MULTIFILL_PLANE_WORDS * vdi.WORD_BYTES), pokes)


vdi_raster.register("one pixel, replace", "LINEA_ROM_HLINE", hline_pokes(SPANS["one pixel"], mode="replace", colour=0b0101))
vdi_raster.register("many groups, transparent 8-row pattern", "LINEA_ROM_HLINE",
                    hline_pokes(SPANS["many groups"], mode="transparent", colour=0b1010, pattern="8 rows"))
vdi_raster.register("two groups, xor user pattern", "LINEA_ROM_HLINE",
                    hline_pokes(SPANS["two groups"], mode="xor", colour=0, pattern="user"))
vdi_raster.register("contour fill's registers", "LINEA_ROM_HLINE_PATTERNED",
                    hline_pokes((0, 0), mode="reverse", colour=0b0110, pattern="16-row hatch"),
                    regs={**vdi_raster.BASE_REGISTERS, "d4": 40, "d5": 57, "d6": 60})
vdi_raster.register("the line style, one pixel", "LINEA_ROM_HLINE_SPAN", hline_pokes((0, 0), mode="replace", colour=0b1001),
                    regs={**vdi_raster.BASE_REGISTERS, "d4": 37, "d5": 150, "d6": 37, "a0": vdi.LINEA_LN_MASK, "d0": 0})
# The body's seven register arguments take eight C arguments, past the six a Tier 3 call can pass
# (`harness.STACK_ARGS_BYTES`): its C is priced inside every row above, and the `.S` on rows of its own.
for label, span, mode in (("one pixel, replace", "one pixel", "replace"), ("many groups, xor", "many groups", "xor")):
    vdi_raster.register(label, "LINEA_ROM_CPU_HLINE", hline_pokes((0, 0), mode=mode, colour=0b1100, pattern="user"),
                        regs=body_registers(SPANS[span], 33, vdi_raster.USER_PATTERN_AT, 0), c_row=False)
