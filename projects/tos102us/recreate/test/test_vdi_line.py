"""$a003 line ($fca1ea), its CPU vertical body $fd19dc (vector 7), and $fca3f4 line_plane_words:
`src/vdi/raster.c`.

    $fca1ea  d4-d7 = X1, Y1, X2, Y2
             Y1 = Y2  -> $fca2e0: XOR without LSTLIN moves X2 one toward X1 AND STORES IT; the span
                         through $fca5a2 with LN_MASK itself as the one-row pattern; LN_MASK rotated
             X1 = X2  -> move.l VECTOR_VLINE,a5 / jmp (a5)                          ($fd19dc)
             else     -> $fca320: a Bresenham from the left end, y-major or x-major, one of eight loops
                         by WRT_MODE ($fca3d4's table), each pixel a `jmp` into per-plane code
                         `$fca3f4` built on the stack

Every line body stores LN_MASK rotated by its pixel count BEFORE drawing, spends the style's top bit per
pixel, and in XOR drops the LAST pixel unless LSTLIN says this is a polyline's last segment. The lines
run from the middle of the screen into all eight octants, along both diagonals' 45 degrees, and one
step long; vertical and horizontal ones both ways round; each in every write mode, LSTLIN on and off,
and in the ROM's own dashed styles.
"""
import pytest

from harness import BASE_IMAGE, addrs

import case
import vdi
import vdi_raster
from case import merge_pokes
from vdi_raster import LINE_STYLES, MODES

CENTRE = (160, 100)
# (dx, dy) from the centre: the eight octants (shallow and steep in each quadrant), the four 45-degree
# diagonals, the shortest diagonal there is, and two slopes that put the error on 0.
# Screen y grows DOWN, so north is -dy.
OCTANTS = {"ENE": (53, -17), "NNE": (17, -53), "NNW": (-17, -53), "WNW": (-53, -17),
           "WSW": (-53, 17), "SSW": (-17, 53), "SSE": (17, 53), "ESE": (53, 17)}
DIAGONALS = {"45 SE": (40, 40), "45 NE": (40, -40), "45 NW": (-40, -40), "45 SW": (-40, 40),
             "one step": (1, 1), "one step up": (1, -1),
             # ...and slopes of exactly 2 and 1/2, whose error lands on 0: `bmi` steps the minor axis there
             "2:1 shallow": (34, -17), "1:2 steep": (-17, 34)}
LSTLIN = (0, 1)


def line_pokes(start, end, *, mode, colour, style=LINE_STYLES[0], lstlin=1, extra=None):
    (x1, y1), (x2, y2) = start, end
    return vdi_raster.drawing_pokes(mode=mode, colour=colour, extra=merge_pokes(
        vdi.linea_pokes(X1=x1, Y1=y1, X2=x2, Y2=y2, LN_MASK=style, LSTLIN=lstlin), extra))


def from_centre(delta):
    return CENTRE, (CENTRE[0] + delta[0], CENTRE[1] + delta[1])


def run(pokes):
    return vdi.run_primitive("LINEA_ROM_LINE", {}, pokes)


def rotated(style, count):
    count %= 16
    return (style << count | style >> (16 - count)) & 0xFFFF


# ---- diagonal ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("delta", {**OCTANTS, **DIAGONALS}.values(), ids={**OCTANTS, **DIAGONALS}.keys())
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("lstlin", LSTLIN)
def test_diagonal_lines_in_every_octant_mode_and_lstlin(delta, mode, lstlin):
    start, end = from_centre(delta)
    result = run(line_pokes(start, end, mode=mode, colour=0b0101, style=LINE_STYLES[3], lstlin=lstlin))
    pixels = max(abs(delta[0]), abs(delta[1])) + 1
    if mode == "xor" and not lstlin:
        pixels -= 1
    assert result.linea("LN_MASK") == rotated(LINE_STYLES[3], pixels), "rotated past the pixels drawn"


@pytest.mark.parametrize("style", LINE_STYLES)
@pytest.mark.parametrize("colour", vdi_raster.COLOURS)
@pytest.mark.parametrize("mode", ("replace", "reverse"))
def test_diagonal_styles_and_colours(style, colour, mode):
    run(line_pokes(*from_centre(OCTANTS["SSE"]), mode=mode, colour=colour, style=style))


def test_a_solid_replace_diagonal_is_the_colour_at_both_ends():
    start, end = from_centre(DIAGONALS["45 NW"])
    result = run(line_pokes(start, end, mode="replace", colour=0b1011))
    assert result.pixel(*start) == result.pixel(*end) == 0b1011


@pytest.mark.parametrize("shape", (vdi_raster.MEDIUM, vdi_raster.HIGH), ids=("medium", "high"))
@pytest.mark.parametrize("mode", MODES)
def test_diagonal_fewer_planes(shape, mode):
    run(line_pokes(*from_centre(OCTANTS["NNE"]), mode=mode, colour=0b0110, style=LINE_STYLES[1],
                   extra=vdi_raster.geometry_pokes(shape)))


# Past LINE_PLANES_MAX planes both line bodies return before anything ($fca328 / $fd19e4 `cmp.w #8,d3 /
# bhi`) — their 20-byte stack buffer has room for 8 plane words and the `jmp` — so nothing is drawn and
# LN_MASK is NOT rotated. PLANES is the caller's to write, so a program reaches it through $a003. The
# guard's own edge, 8 planes, still draws.
TOO_MANY_PLANES = vdi_raster.LINE_PLANES_MAX + 1
GUARD_EDGE = (vdi_raster.LINE_PLANES_MAX, TOO_MANY_PLANES)


def assert_nothing_drawn(result, style):
    assert not any(vdi.SCREEN.base <= at < vdi.SCREEN.base + vdi.SCREEN.bytes for at in result.info["writes"])
    assert result.linea("LN_MASK") == style, "the style is stored rotated only past the guard"


@pytest.mark.parametrize("planes", GUARD_EDGE)
@pytest.mark.parametrize("mode", MODES)
def test_diagonal_at_the_plane_guard(mode, planes):
    result = run(line_pokes(*from_centre(OCTANTS["ESE"]), mode=mode, colour=0b0101, style=LINE_STYLES[3],
                            extra=vdi.linea_pokes(PLANES=planes)))
    if planes == TOO_MANY_PLANES:
        assert_nothing_drawn(result, LINE_STYLES[3])


def test_diagonal_steps_by_width_and_starts_by_bytes_lin():
    run(line_pokes(*from_centre(OCTANTS["ENE"]), mode="replace", colour=0b1111,
                   extra=vdi_raster.width_skew_pokes(vdi_raster.WIDTH_SKEWS[1])))


# ---- vertical ----------------------------------------------------------------------------------------
# (x, y1, y2): down and up across 50 rows, the shortest vertical line there is, and a column 15 one.
VERTICALS = {"down": (37, 20, 70), "up": (37, 70, 20), "two pixels": (48, 99, 100), "column 15": (15, 30, 40)}


@pytest.mark.parametrize("line", VERTICALS.values(), ids=VERTICALS.keys())
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("lstlin", LSTLIN)
def test_vertical_lines(line, mode, lstlin):
    x, y1, y2 = line
    result = run(line_pokes((x, y1), (x, y2), mode=mode, colour=0b1010, style=LINE_STYLES[5], lstlin=lstlin))
    pixels = abs(y2 - y1) + 1 - (mode == "xor" and not lstlin)
    assert result.linea("LN_MASK") == rotated(LINE_STYLES[5], pixels)


@pytest.mark.parametrize("style", LINE_STYLES)
@pytest.mark.parametrize("colour", vdi_raster.COLOURS)
def test_vertical_styles_and_colours(style, colour):
    x, y1, y2 = VERTICALS["down"]
    run(line_pokes((x, y1), (x, y2), mode="transparent", colour=colour, style=style))


@pytest.mark.parametrize("shape", (vdi_raster.MEDIUM, vdi_raster.HIGH), ids=("medium", "high"))
def test_vertical_fewer_planes(shape):
    x, y1, y2 = VERTICALS["up"]
    run(line_pokes((x, y1), (x, y2), mode="replace", colour=0b0110, style=LINE_STYLES[2],
                   extra=vdi_raster.geometry_pokes(shape)))


def test_vertical_steps_by_width_and_starts_by_bytes_lin():
    x, y1, y2 = VERTICALS["down"]
    run(line_pokes((x, y1), (x, y2), mode="xor", colour=0,
                   extra=vdi_raster.width_skew_pokes(vdi_raster.WIDTH_SKEWS[0])))


@pytest.mark.parametrize("planes", GUARD_EDGE)
@pytest.mark.parametrize("mode", MODES)
def test_vertical_at_the_plane_guard(mode, planes):
    x, y1, y2 = VERTICALS["down"]
    result = run(line_pokes((x, y1), (x, y2), mode=mode, colour=0b1010, style=LINE_STYLES[5],
                            extra=vdi.linea_pokes(PLANES=planes)))
    if planes == TOO_MANY_PLANES:
        assert_nothing_drawn(result, LINE_STYLES[5])


def vline_body_registers(line):
    x, y1, y2 = line
    return {**vdi_raster.VLINE_BODY_REGISTERS, "d4": x, "d5": y1, "d6": x, "d7": y2}


@pytest.mark.parametrize("line", VERTICALS.values(), ids=VERTICALS.keys())
@pytest.mark.parametrize("mode", MODES)
def test_the_vertical_body_entered_directly(line, mode):
    """$fd19dc by `jsr`, with the registers $a003 leaves: D0 = 2, D4..D7 the corners."""
    vdi.run_primitive("LINEA_ROM_CPU_VLINE", vline_body_registers(line),
                      line_pokes((0, 0), (0, 0), mode=mode, colour=0b0111, style=LINE_STYLES[4], lstlin=0))


# ---- horizontal ----------------------------------------------------------------------------------------
# (x1, x2, y): rightward and leftward across many groups, inside one group, and a single point.
HORIZONTALS = {"right": (5, 300, 150), "left": (300, 5, 150), "inside a group": (35, 42, 7),
               "leftward in a group": (42, 35, 7), "a point": (37, 37, 60), "two pixels": (47, 48, 61)}


@pytest.mark.parametrize("line", HORIZONTALS.values(), ids=HORIZONTALS.keys())
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("lstlin", LSTLIN)
def test_horizontal_lines(line, mode, lstlin):
    x1, x2, y = line
    result = run(line_pokes((x1, y), (x2, y), mode=mode, colour=0b1001, style=LINE_STYLES[1], lstlin=lstlin))
    drops_last = mode == "xor" and not lstlin and x1 != x2
    stored_x2 = x2 - (1 if x2 > x1 else -1) if drops_last else x2
    assert result.linea("X2") == stored_x2, "XOR's shortened end is STORED in X2"
    assert result.linea("LN_MASK") == rotated(LINE_STYLES[1], abs(stored_x2 - x1) + 1)


@pytest.mark.parametrize("skew", vdi_raster.WIDTH_SKEWS)
@pytest.mark.parametrize("mode", MODES)
def test_horizontal_places_its_row_by_bytes_lin_not_width(skew, mode):
    """The horizontal arm draws through the hline body, which places the row by BYTES_LIN alone."""
    x1, x2, y = HORIZONTALS["left"]
    run(line_pokes((x1, y), (x2, y), mode=mode, colour=0b0110, style=LINE_STYLES[4],
                   extra=vdi_raster.width_skew_pokes(skew)))


@pytest.mark.parametrize("style", LINE_STYLES)
@pytest.mark.parametrize("colour", vdi_raster.COLOURS)
def test_horizontal_styles_and_colours(style, colour):
    """The style word is the span's pattern AS IT STANDS — not rotated to the line's first pixel."""
    x1, x2, y = HORIZONTALS["right"]
    run(line_pokes((x1, y), (x2, y), mode="replace", colour=colour, style=style))


# ---- line_plane_words ----------------------------------------------------------------------------------
PLANE_WORDS_AT = vdi_raster.PLANE_WORDS_AT
PLANE_WORDS_BYTES = vdi_raster.PLANE_WORDS_BYTES


@pytest.mark.parametrize("colour", vdi_raster.COLOURS)
@pytest.mark.parametrize("planes", (1, 2, 4))
def test_line_plane_words_builds_the_per_plane_code(colour, planes):
    """`and.w d0,(a5)+` for a plane whose COLBIT is 0, `or.w d1,(a5)+` otherwise, then `jmp (a3)` —
    into A2's buffer (on the stack in the ROM; here a band the differential compares)."""
    pokes = merge_pokes(vdi_raster.colour_pokes(colour), {PLANE_WORDS_AT: bytes([case.SLACK_FILL]) * PLANE_WORDS_BYTES})
    result = vdi.run_primitive("LINEA_ROM_LINE_PLANE_WORDS",
                               {**vdi_raster.BASE_REGISTERS, "d3": planes, "a2": PLANE_WORDS_AT}, pokes)
    clear, set_, end = (case.word_in(BASE_IMAGE, vdi_raster.HEADER["RASTER_PLANE_OPCODES"]
                                     + vdi_raster.HEADER[f"RASTER_PLANE_OPCODE_{name}"])
                        for name in ("CLEAR", "SET", "END"))
    expected = [set_ if colour >> plane & 1 else clear for plane in range(planes)] + [end]
    assert result.words(PLANE_WORDS_AT, planes + 1) == expected


vdi_raster.register("one diagonal step, replace", "LINEA_ROM_LINE",
                    line_pokes(*from_centre(DIAGONALS["one step"]), mode="replace", colour=0b0101),
                    code_pointers=vdi_raster.DIAGONAL_CODE_POINTERS)
vdi_raster.register("steep diagonal, transparent dash-dot", "LINEA_ROM_LINE",
                    line_pokes(*from_centre(OCTANTS["NNE"]), mode="transparent", colour=0b1010, style=LINE_STYLES[3]),
                    code_pointers=vdi_raster.DIAGONAL_CODE_POINTERS)
vdi_raster.register("shallow diagonal, xor", "LINEA_ROM_LINE",
                    line_pokes(*from_centre(OCTANTS["WSW"]), mode="xor", colour=0, lstlin=0),
                    code_pointers=vdi_raster.DIAGONAL_CODE_POINTERS)
vdi_raster.register("vertical, replace", "LINEA_ROM_LINE", line_pokes((37, 20), (37, 70), mode="replace", colour=0b0110))
vdi_raster.register("vertical, two pixels, reverse", "LINEA_ROM_LINE",
                    line_pokes((48, 99), (48, 100), mode="reverse", colour=0b1001, style=LINE_STYLES[2]))
vdi_raster.register("horizontal, a point", "LINEA_ROM_LINE", line_pokes((37, 60), (37, 60), mode="replace", colour=0b1100))
vdi_raster.register("horizontal, many groups, xor", "LINEA_ROM_LINE",
                    line_pokes((300, 150), (5, 150), mode="xor", colour=0, lstlin=0, style=LINE_STYLES[1]))
vdi_raster.register("50 rows", "LINEA_ROM_CPU_VLINE", line_pokes((0, 0), (0, 0), mode="transparent", colour=0b0111),
                    regs=vline_body_registers(VERTICALS["down"]))
vdi_raster.register("two pixels, reverse", "LINEA_ROM_CPU_VLINE",
                    line_pokes((0, 0), (0, 0), mode="reverse", colour=0b1001, style=LINE_STYLES[2]),
                    regs=vline_body_registers(VERTICALS["two pixels"]))
vdi_raster.register("4 planes", "LINEA_ROM_LINE_PLANE_WORDS", vdi_raster.colour_pokes(0b0101),
                    regs={**vdi_raster.BASE_REGISTERS, "d3": 4, "a2": PLANE_WORDS_AT})
