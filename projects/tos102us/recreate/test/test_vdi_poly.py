"""The polygon layer (`src/vdi/fill.c`): $a006 filled_poly ($fca05e), clip_line ($fcbf16), polyline
($fcbe8c), plygn ($fcc0ea) and v_fillarea ($fcbbc0, opcode 9).

    $fca05e  per edge i -> i + 1 (contrl[1] of them): dy = 0 skipped; crossing when Y1 - y1 and Y1 - y2
             differ in sign bit; x1 + round(2dx(Y1 - y1) / dy / 2) into the list at $16da, FILL_INT += 1
             / sort / pairs through $a004, x-clipped when CLIP
    $fcbf16  outcodes (clip_code) of both ends until both 0 (-> 1) or sharing a bit (-> 0); the first end
             outside is cut by its lowest bit, smul_div for the other coordinate
    $fcbe8c  LSTLIN = 0 .. 1 on the last segment; each segment clip_line'd when CLIP, then $a003
    $fcc0ea  COLBIT from the fill colour, the rows' min/max (clipped: YMINCL - 1, at least 1), the closing
             point at ptsin[n], $a006 from maxy down to miny + 1, the perimeter when FILL_PER == 1

Every drawing case runs over `vdi_raster.CANVAS`, so a span one pixel off, or a row filled that the ROM
skipped, changes bits the ROM left alone.

THE STRICT MUTATION SWEEP's survivors in this layer (`recreate/README.md`, "Mutation sweeps"), each EQUIVALENT:
$a006 not skipping a horizontal edge, or counting a sign-bit XOR of 0 as a crossing (dy = 0 is the only way
to either, and its two differences are equal, so their XOR is never negative); a pair's cut made inclusive at
XMINCL or XMAXCL, or X1/X2 re-stored inside the clipped path (the same value stored); a zero quotient halved
by the negative path (both give 0); plygn's bottom cut inclusive (FILL_MAXY = YMAXCL either way).
"""
import pytest

from harness import addrs

import vdi
import vdi_fill
import vdi_raster
from case import merge_pokes
from vdi_raster import MODES

# ---- polygons ----------------------------------------------------------------------------------------
POLYGONS = {
    "triangle": [(40, 30), (150, 120), (10, 100)],
    "concave arrow": [(20, 60), (80, 20), (80, 45), (160, 45), (160, 75), (80, 75), (80, 100)],
    "bowtie": [(30, 20), (130, 90), (130, 20), (30, 90)],
    "pentagram": [(100, 20), (130, 110), (55, 55), (145, 55), (70, 110)],
    "rectangle": [(33, 40), (95, 40), (95, 70), (33, 70)],
    "off both sides": [(-500, 30), (800, 60), (160, 150), (-40, 120)],
}
# A comb of 12 teeth: 24 crossings on a row through them, which runs the list past $1702.
COMB = [(10, 150)] + [point for tooth in range(12) for point in ((10 + 24 * tooth + 6, 100), (10 + 24 * tooth + 12, 150))] \
    + [(300, 190), (10, 190)]
POLYGONS["comb"] = COMB
# An edge whose 2dx overflows the word: x from -20000 to 20000.
POLYGONS["huge"] = [(-20000, 20), (20000, 140), (100, 180)]
# Edges whose y spans more than a word holds: the differences wrap, and the quotient overflows `divs.w`,
# leaving the product in the register.
POLYGONS["y wraps"] = [(100, -30000), (20000, 30000), (10, 190), (10, 10)]
# Rectangles whose sides sit ON the tight clip's edges below: a pair ending exactly at XMINCL, and one
# starting exactly at XMAXCL — each one pixel wide once clipped.
POLYGONS["ends at XMINCL"] = [(30, 20), (50, 20), (50, 60), (30, 60)]
POLYGONS["starts at XMAXCL"] = [(120, 20), (140, 20), (140, 60), (120, 60)]


def closed(points):
    return points + points[:1]


def rows_of(points):
    """The rows at and either side of every vertex, and the middle one — those on the screen: $a006 draws
    whatever row Y1 names, and one off the screen writes past the framebuffer."""
    ys = [y for _x, y in points]
    rows = {min(ys) - 1, (min(ys) + max(ys)) // 2, max(ys) + 1} | {y + step for y in ys for step in (-1, 0, 1)}
    return sorted(row for row in rows if 0 <= row < vdi.SCREEN.height)


def poly_pokes(points, row, *, mode="replace", colour=0b0110, clip=None, pattern="8 rows", count=None,
               extra=None):
    """$a006 staged directly: PTSIN at the entry's copy holding `points` (closed unless `count` says
    otherwise), contrl[1] = the edges, Y1 = `row`, the drawing state `$a004` reads, and CLIP."""
    edges = len(points) if count is None else count
    clipping = vdi.linea_pokes(CLIP=0) if clip is None else vdi.linea_pokes(
        CLIP=1, XMINCL=clip[0], YMINCL=clip[1], XMAXCL=clip[2], YMAXCL=clip[3])
    return vdi_raster.drawing_pokes(mode=mode, colour=colour, extra=merge_pokes(
        vdi_raster.pattern_pokes(pattern), vdi_fill.points_pokes(closed(points), count=edges),
        vdi.linea_pokes(Y1=row), clipping, extra))


def run_poly(pokes):
    return vdi.run_primitive("LINEA_ROM_FILLED_POLY", {}, pokes)


# Unclipped, "huge" and "y wraps" run spans ~15 KB past their rows — off the end of RAM, where the oracle
# drops a store.
UNCLIPPABLE = ("huge", "y wraps")


@pytest.mark.parametrize("name", [name for name in POLYGONS if name not in UNCLIPPABLE])
def test_every_row_of_every_polygon(name):
    points = POLYGONS[name]
    for row in rows_of(points):
        run_poly(poly_pokes(points, row))


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("colour", vdi_raster.COLOURS)
def test_every_mode_and_colour(mode, colour):
    run_poly(poly_pokes(POLYGONS["pentagram"], 60, mode=mode, colour=colour, pattern="16-row hatch"))


TIGHT_CLIP = (50, 0, 120, 199)
LINEA_OPCODE = 6                    # $a006


@pytest.mark.parametrize("name", ("pentagram", "comb", "off both sides", *UNCLIPPABLE, "ends at XMINCL", "starts at XMAXCL"))
def test_clipped_in_x_pairs_cut_and_missed(name):
    """Pairs straddling XMINCL and XMAXCL are cut, pairs wholly left or right are skipped with X1/X2 left
    stored — the comb's teeth fall on every side of the tight clip."""
    points = POLYGONS[name]
    for row in rows_of(points):
        run_poly(poly_pokes(points, row, clip=TIGHT_CLIP))


ZIGZAG = [(10, 10), (50, 100), (90, 10), (130, 100)]


def test_an_open_path_leaves_an_odd_crossing_dropped():
    """contrl[1] one short of the closing edge: three crossings on row 50, the last never paired. (ONE
    crossing would be `dbf` from -1: 65,536 pairs read past the list — not staged.)"""
    result = run_poly(poly_pokes(ZIGZAG, 50, count=len(ZIGZAG) - 1))
    assert result.linea("GDP_FILL_INT") == 3


def test_the_crossing_list_runs_past_the_text_alignment_words():
    result = run_poly(poly_pokes(COMB, 120))
    assert result.linea("GDP_FILL_INT") == 24


# An edge whose quotient overflows `divs.w` with a product >= 0 whose LOW WORD is $8000: 2dx = 16,384 times
# Y1 - y1 = 32,766 over dy = -2. The branch reads the whole product's sign, so the word halves as a positive
# one — to $c000 — where its own sign would negate it to $4000.
PRODUCT_LOW_WORD_8000_ROW = 100
PRODUCT_LOW_WORD_8000 = [(0, PRODUCT_LOW_WORD_8000_ROW - 32766), (8192, PRODUCT_LOW_WORD_8000_ROW - 32768)]


@pytest.mark.parametrize("clip", (None, (0, 0, 319, 199)), ids=("unclipped", "clipped"))
def test_an_overflowed_quotient_halves_by_the_product_s_sign(clip):
    result = run_poly(poly_pokes(PRODUCT_LOW_WORD_8000, PRODUCT_LOW_WORD_8000_ROW, clip=clip))
    assert result.linea("GDP_FILL_INT") == 2


def test_through_the_line_a_exception():
    """What a program does: `dc.w $a006`, the handler saving D3-D7/A3-A5 round it."""
    vdi.run_through_exception("LINEA_ROM_FILLED_POLY", LINEA_OPCODE, {}, poly_pokes(POLYGONS["concave arrow"], 50))


def test_the_user_pattern_multi_plane():
    run_poly(poly_pokes(POLYGONS["bowtie"], 50, extra=vdi_raster.user_pattern_pokes()))


# ---- clip_line -------------------------------------------------------------------------------------------
CLIP = (50, 20, 200, 150)
LINES = {
    "inside": (60, 30, 190, 140), "both left": (10, 30, 40, 140), "both below": (60, 160, 190, 190),
    "left end cut": (10, 30, 100, 90), "right end cut": (100, 30, 260, 90), "top cut": (80, 0, 120, 100),
    "bottom cut": (80, 100, 120, 199), "both ends cut": (0, 0, 319, 199), "second end first": (100, 30, 0, 90),
    "corner miss": (0, 100, 100, 0), "steep through corner": (40, 10, 60, 30), "negative": (-300, -200, 400, 300),
    "vertical crossing": (120, -50, 120, 250), "horizontal crossing": (-10, 80, 330, 80),
}


def line_pokes(line, clip=CLIP):
    x1, y1, x2, y2 = line
    xmin, ymin, xmax, ymax = clip
    return vdi.linea_pokes(X1=x1, Y1=y1, X2=x2, Y2=y2, XMINCL=xmin, YMINCL=ymin, XMAXCL=xmax, YMAXCL=ymax)


@pytest.mark.parametrize("line", LINES.values(), ids=LINES.keys())
def test_clip_line(line):
    result = vdi_fill.run_call("VDI_ROM_CLIP_LINE", (), line_pokes(line))
    kept = vdi_fill.answer(result)
    ends = [vdi.signed_word(result.linea(name)) for name in ("X1", "Y1", "X2", "Y2")]
    if kept:
        xmin, ymin, xmax, ymax = CLIP
        assert xmin <= ends[0] <= xmax and xmin <= ends[2] <= xmax and ymin <= ends[1] <= ymax and ymin <= ends[3] <= ymax


# ---- polyline ----------------------------------------------------------------------------------------------
PATHS = {"none": [], "one point": [(60, 60)], "one segment": [(20, 30), (140, 90)],
         "zigzag": [(10, 10), (100, 60), (40, 120), (300, 190), (160, 5)],
         "clipped away and back": [(60, 60), (300, 5), (310, 190), (70, 100)]}


# A contrl whose element 1 (the point count) is LSTLIN.
CONTRL_OVER_LSTLIN = vdi.LINEA_LSTLIN - vdi.CONTRL_N_PTSIN


def polyline_pokes(path, *, clip=None, mode="replace", style=0xF0F0, colour=0b1001):
    clipping = vdi.linea_pokes(CLIP=0) if clip is None else vdi.linea_pokes(
        CLIP=1, XMINCL=clip[0], YMINCL=clip[1], XMAXCL=clip[2], YMAXCL=clip[3])
    return vdi_raster.drawing_pokes(mode=mode, colour=colour, extra=merge_pokes(
        vdi_fill.points_pokes(path), clipping, vdi.linea_pokes(LN_MASK=style, LSTLIN=0x5A5A)))


@pytest.mark.parametrize("path", PATHS.values(), ids=PATHS.keys())
@pytest.mark.parametrize("clip", (None, CLIP), ids=("unclipped", "clipped"))
def test_polyline(path, clip):
    result = vdi_fill.run_call("VDI_ROM_POLYLINE", (), polyline_pokes(path, clip=clip), max_insns=FILL_INSNS)
    assert result.linea("LSTLIN") == (1 if len(path) >= 2 else 0)


def test_polyline_clears_lstlin_before_reading_the_count():
    """contrl laid over the Line-A block so contrl[1] IS LSTLIN: `clr.w LSTLIN` comes first, so the count
    read is 0 and nothing is drawn — where the other order would draw two segments."""
    pokes = merge_pokes(polyline_pokes(PATHS["zigzag"]), vdi.linea_pokes(CONTRL=CONTRL_OVER_LSTLIN, LSTLIN=3))
    result = vdi_fill.run_call("VDI_ROM_POLYLINE", (), pokes, max_insns=FILL_INSNS)
    assert result.linea("LSTLIN") == 0


@pytest.mark.parametrize("mode", MODES)
def test_polyline_every_mode_the_last_segment_keeps_its_last_pixel(mode):
    """XOR drops each segment's last pixel unless LSTLIN — which only the last segment has."""
    vdi_fill.run_call("VDI_ROM_POLYLINE", (), polyline_pokes(PATHS["zigzag"], mode=mode, clip=vdi_fill.DESKTOP_CLIP),
                      max_insns=FILL_INSNS)


# ---- plygn and v_fillarea ------------------------------------------------------------------------------------

def fillarea_pokes(points, *, perimeter=0, clip=vdi_fill.DESKTOP_CLIP, mode="replace", colour=0b0101,
                   pattern="8 rows", **values):
    work = vdi_fill.fill_workstation(colour=colour, mode=mode, pattern=pattern, clip=clip, perimeter=perimeter,
                                     onto=vdi_raster.CANVAS, **values)
    flat = [coordinate for point in points for coordinate in point]
    return vdi.function_pokes("VDI_ROM_V_FILLAREA", ptsin=flat, workstation_pokes=work)


# A polygon's rows and its outline through $a003 take more than the differential's default budget.
FILL_INSNS = 4_000_000


def run_fillarea(pokes):
    return vdi.run_function("VDI_ROM_V_FILLAREA", pokes, max_insns=FILL_INSNS)


@pytest.mark.parametrize("name", POLYGONS)
@pytest.mark.parametrize("perimeter", (0, 1), ids=("filled", "outlined"))
def test_v_fillarea(name, perimeter):
    points = POLYGONS[name]
    result = run_fillarea(fillarea_pokes(points, perimeter=perimeter))
    assert result.contrl(vdi.CONTRL_N_PTSIN) == len(points) + perimeter, "the perimeter's point is LEFT counted"


@pytest.mark.parametrize("mode", MODES)
def test_v_fillarea_every_mode_outlined(mode):
    run_fillarea(fillarea_pokes(POLYGONS["concave arrow"], perimeter=1, mode=mode, colour=0b1010))


def test_a_perimeter_word_other_than_1_draws_no_outline():
    run_fillarea(fillarea_pokes(POLYGONS["triangle"], perimeter=2))


def test_the_clip_rows_top_at_row_0_leave_rows_0_and_1_unfilled():
    """YMINCL = 0: FILL_MINY becomes -1, raised to 1 — the scan stops above row 2."""
    result = run_fillarea(fillarea_pokes([(20, -30), (200, -10), (120, 60)], clip=vdi_fill.WHOLE_SCREEN_CLIP))
    assert result.linea("GDP_FILL_MINY") == 1


@pytest.mark.parametrize("points", ([(20, 1), (200, 5), (120, 9)], [(20, 1), (200, 30), (120, 60)],
                                    [(20, 170), (200, 190), (120, 230)], [(20, 300), (200, 310), (120, 330)]),
                         ids=("above", "cut at the top", "cut at the bottom", "below"))
def test_rows_clipped_or_missed(points):
    """Wholly above or below the desktop's clip: nothing — not even the closing point is written. Cut at
    the top: from YMINCL - 1 = 10, so row 11 is the last filled."""
    result = run_fillarea(fillarea_pokes(points))
    if points[1] == (200, 30):
        assert result.linea("GDP_FILL_MINY") == vdi_fill.DESKTOP_CLIP[1] - 1


@pytest.mark.parametrize("points", ([(20, 1), (200, 5), (120, 11)], [(20, 199), (200, 210), (120, 230)]),
                         ids=("its lowest row on YMINCL", "its highest row on YMAXCL"))
def test_rows_touching_the_clip_edge(points):
    """A polygon that only TOUCHES the clip keeps its outline: the misses are strict (`blt`/`bgt`), so a lowest
    row at YMINCL fills that one row, and a highest at YMAXCL fills none but still draws the perimeter."""
    run_fillarea(fillarea_pokes(points, perimeter=1))


@pytest.mark.parametrize("points", ([(60, 60)], [(20, 30), (140, 90)]), ids=("one point", "two points"))
@pytest.mark.parametrize("perimeter", (0, 1), ids=("filled", "outlined"))
def test_degenerate_polygons(points, perimeter):
    run_fillarea(fillarea_pokes(points, perimeter=perimeter))


def test_no_points():
    run_fillarea(fillarea_pokes([], perimeter=1))


def test_unclipped_with_the_user_pattern():
    run_fillarea(fillarea_pokes(POLYGONS["off both sides"], clip=None, pattern="solid",
                                FILL_STYLE=vdi.VDI_INTERIOR_USER, MULTIFILL=1, UD_PATRN=vdi_raster.USER_PATTERN_ROWS,
                                PATMSK=vdi_raster.USER_PATTERN_MASK))


@pytest.mark.parametrize("name", ("bowtie", "comb", "y wraps"))
def test_plygn_entered_as_its_callers_do(name):
    """As v_pline's arrows and the GDP's shapes reach it: a `jsr` with no frame."""
    vdi_fill.run_call("VDI_ROM_PLYGN", (), fillarea_pokes(POLYGONS[name], perimeter=1), max_insns=FILL_INSNS)


# ---- Tier 3 ------------------------------------------------------------------------------------------------
vdi.register("linea_filled_poly, pentagram row, 8 rows", addrs.LINEA_ROM_FILLED_POLY, poly_pokes(POLYGONS["pentagram"], 60))
vdi.register("linea_filled_poly, comb row, clipped", addrs.LINEA_ROM_FILLED_POLY, poly_pokes(COMB, 120, clip=TIGHT_CLIP))
# ...and the same two as rows of `fill.S`, the transcription the target build ships.
vdi_fill.register_transcription("pentagram row, 8 rows", "LINEA_ROM_FILLED_POLY", poly_pokes(POLYGONS["pentagram"], 60))
vdi_fill.register_transcription("comb row, clipped", "LINEA_ROM_FILLED_POLY", poly_pokes(COMB, 120, clip=TIGHT_CLIP))
vdi_fill.register_call("both ends cut", "VDI_ROM_CLIP_LINE", (), line_pokes(LINES["both ends cut"]))
vdi_fill.register_call("inside", "VDI_ROM_CLIP_LINE", (), line_pokes(LINES["inside"]))
vdi_fill.register_call("zigzag, clipped", "VDI_ROM_POLYLINE", (),
                       polyline_pokes(PATHS["zigzag"], clip=vdi_fill.DESKTOP_CLIP))
vdi.register("vdi_v_fillarea, triangle outlined", addrs.VDI_ROM_V_FILLAREA,
             fillarea_pokes(POLYGONS["triangle"], perimeter=1))
vdi.register("vdi_v_fillarea, one point", addrs.VDI_ROM_V_FILLAREA, fillarea_pokes([(60, 60)]))
vdi_fill.register_call("bowtie outlined", "VDI_ROM_PLYGN", (), fillarea_pokes(POLYGONS["bowtie"], perimeter=1))
