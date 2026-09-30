"""`src/vdi/fill.S` — $a006 filled_poly, fill_span and end_pts as the ROM wrote them, which the target build
ships because their C measures over Tier 3's 1.10 bar (`include/transcribed.h`).

Two claims hold it, neither needing the C: its WORDS are the ROM's, region by region, save the five branch
displacements into helpers.S and raster.S (each relocated to its exact value); and it BEHAVES as the ROM
over the batteries' own cases — the same image, the whole register file and the same traffic, through Tier
3's transcription relation.

THE STRICT MUTATION SWEEP over fill.S's behaviour cases (the byte pin excluded, which catches every mutant):
three survivors are EQUIVALENT — a horizontal edge let through to the crossing test (its XOR is 0, never
negative, so `divs.w` is never reached) and a pair's cut made inclusive at either clip edge (the same word
stored) — and `adda.w a3,a5` as `adda.l` differs only for PLANES $4000 and up, whose 16K-word reads a pixel
exceed the transcription relation's instruction budget: the byte pin alone holds that instruction.
"""

import pytest

import test_vdi_fill_contour as contour
import test_vdi_poly as poly
import transcription
import vdi
import vdi_fill
import vdi_raster
from case import merge_pokes

REGIONS = (
    transcription.pinned_region(0xFCA05E, 0xFCA164, "LINEA_ROM_FILLED_POLY", ()),
    transcription.pinned_region(0xFCFB54, 0xFCFC50, "LINEA_ROM_FILL_SPAN", ("LINEA_ROM_END_PTS",)),
)
_ACROSS = "a displacement into another file's region, which measures to where the blob links it"
RELOCATED = {
    0xFCA0E0: transcription.Relocated(transcription.PC_RELATIVE, "VDI_ROM_SORT_WORDS", f"$a006's `bsr.w` to sort_words: {_ACROSS}"),
    0xFCA106: transcription.Relocated(transcription.PC_RELATIVE, "LINEA_ROM_HLINE", f"$a006's unclipped `bsr.w` to $a004: {_ACROSS}"),
    0xFCA158: transcription.Relocated(transcription.PC_RELATIVE, "LINEA_ROM_HLINE", f"$a006's clipped `bsr.w` to $a004: {_ACROSS}"),
    0xFCFB64: transcription.Relocated(transcription.PC_RELATIVE, "LINEA_ROM_HLINE_PATTERNED",
                                      f"fill_span's `bra.w` into $a004's patterned entry: {_ACROSS}"),
    0xFCFB96: transcription.Relocated(transcription.PC_RELATIVE, "LINEA_ROM_CONCAT", f"end_pts' `bsr.w` to concat: {_ACROSS}"),
}


@pytest.mark.parametrize("region", REGIONS, ids=[f"${region.lo:x}" for region in REGIONS])
def test_each_region_is_the_rom_s_words(region):
    transcription.assert_transcribed(region, relocated=RELOCATED)


# ---- the behaviour ----------------------------------------------------------------------------------------

# Every polygon clipped, and unclipped every one whose spans stay in RAM (`test_vdi_poly.UNCLIPPABLE`).
POLY_CASES = {**{f"{name}, clipped": (name, poly.TIGHT_CLIP) for name in poly.POLYGONS},
              **{f"{name}, unclipped": (name, None) for name in poly.POLYGONS if name not in poly.UNCLIPPABLE}}


@pytest.mark.parametrize("name, clip", POLY_CASES.values(), ids=POLY_CASES.keys())
def test_filled_poly(name, clip):
    points = poly.POLYGONS[name]
    for row in poly.rows_of(points):
        vdi_fill.run_transcription("LINEA_ROM_FILLED_POLY", poly.poly_pokes(points, row, clip=clip))


def test_filled_poly_an_odd_crossing():
    vdi_fill.run_transcription("LINEA_ROM_FILLED_POLY", poly.poly_pokes(poly.ZIGZAG, 50, count=len(poly.ZIGZAG) - 1))


@pytest.mark.parametrize("mode", vdi_raster.MODES)
def test_fill_span(mode):
    pokes = vdi_raster.drawing_pokes(mode=mode, colour=0b0110, extra=vdi_raster.user_pattern_pokes())
    vdi_fill.run_transcription("LINEA_ROM_FILL_SPAN", pokes, (7, 250, 33))


END_PTS_POINTS = ((70, 60), (0, 20), (319, 20), (41, 31), (5, 199), (60, 11), (60, 10), (60, 200))


@pytest.mark.parametrize("point", END_PTS_POINTS)
@pytest.mark.parametrize("seed_type", (0, 1))
def test_end_pts(point, seed_type):
    screen = contour.screen_bytes(contour.random_field(0.2, seed=point[0] * 1000 + point[1]))
    pokes = merge_pokes(vdi_fill.fill_workstation(colour=3, onto=screen),
                        contour.search_pokes(seed_type, contour.BACKGROUND))
    vdi_fill.run_transcription("LINEA_ROM_END_PTS", pokes, (*point, contour.XLEFT_AT, contour.XRIGHT_AT))


@pytest.mark.parametrize("clip", (None, poly.TIGHT_CLIP), ids=("unclipped", "clipped"))
def test_filled_poly_an_overflowed_quotient(clip):
    """`bpl` after an overflowing `divs.w` reads the PRODUCT's sign (`test_vdi_poly`)."""
    vdi_fill.run_transcription("LINEA_ROM_FILLED_POLY", poly.poly_pokes(poly.PRODUCT_LOW_WORD_8000,
                                                                        poly.PRODUCT_LOW_WORD_8000_ROW, clip=clip))


# The plane counts whose step is not a word ($4000 up, and 0) read 16K words or more a pixel — past the
# transcription relation's instruction budget — so here the walk crosses groups at the counts a screen has
# and one it has not; the byte pin holds the `adda.w` those others turn on (`test_vdi_fill_contour`).
@pytest.mark.parametrize("planes", (1, 2, 3, 8))
def test_end_pts_by_plane_count(planes):
    pokes = merge_pokes(vdi_fill.fill_workstation(colour=3, onto=contour.canvas("box"), clip=(0, 0, 40, 199)),
                        contour.search_pokes(0, contour.BOUNDARY), vdi.linea_pokes(PLANES=planes))
    vdi_fill.run_transcription("LINEA_ROM_END_PTS", pokes, (17, 3, contour.XLEFT_AT, contour.XRIGHT_AT))


def test_end_pts_bounds_the_top_on_the_word_difference():
    pokes = merge_pokes(vdi_fill.fill_workstation(colour=3, onto=contour.canvas("box"), clip=(0, -32700, 319, 199)),
                        contour.search_pokes(0, contour.BOUNDARY))
    vdi_fill.run_transcription("LINEA_ROM_END_PTS", pokes, (60, 100, contour.XLEFT_AT, contour.XRIGHT_AT))
