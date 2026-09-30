"""`src/vdi/raster.S` — the pixel / scanline primitives as the ROM wrote them, which the target build
ships because their C measures over Tier 3's 1.10 bar (`include/transcribed.h`, the TRANSCRIBED table).

Two claims hold it, neither of which needs the C: its WORDS are the ROM's, region by region, save the
references that measure to where raster.S itself is linked (each relocated to its exact value); and it
BEHAVES as the ROM over the batteries' own cases — the same image, the whole register file and the same
traffic, through Tier 3's transcription relation (`transcription.run_transcription`).
"""

import pytest

import test_vdi_line as line
import test_vdi_raster_hline as hline
import test_vdi_raster_pixel as pixel
import test_vdi_raster_rect as rect
import transcription
import vdi
import vdi_raster
from vdi_raster import MODES

# ---- the words -------------------------------------------------------------------------------------------
# Each region the ROM's, with the `.S` entry whose offset in it anchors it and every other entry inside.
REGIONS = (
    transcription.pinned_region(0xFCA1B8, 0xFCA20A, "LINEA_ROM_CONCAT", ("LINEA_ROM_LINE",)),
    transcription.pinned_region(0xFCA2E0, 0xFCA5CA, "LINEA_ROM_LINE_PLANE_WORDS", ("LINEA_ROM_HLINE", "LINEA_ROM_HLINE_PATTERNED", "LINEA_ROM_HLINE_SPAN")),
    transcription.pinned_region(0xFCFACE, 0xFCFB54, "LINEA_ROM_PUT_PIXEL", ("LINEA_ROM_GET_PIXEL",)),
    transcription.pinned_region(0xFCFC50, 0xFCFCCC, "LINEA_ROM_FILLED_RECT", ()),
    transcription.pinned_region(0xFD19DC, 0xFD1CC4, "LINEA_ROM_CPU_VLINE", ("LINEA_ROM_CPU_HLINE", "LINEA_ROM_CPU_RECT_FILL")),
)
# The words no spelling reproduces, each relocated to its target's place in the blob (`transcription.Relocated`):
# the displacements of the branches from one region into another, and the one absolute reference to a
# table of the transcription's own.
_ACROSS = "a displacement from one region into another, which measures to where raster.S puts it"
_LINE_ARMS = "LINEA_ROM_LINE_PLANE_WORDS"            # the region $a003's two arms are in
RELOCATED = {
    0xFCA1FC: transcription.Relocated(transcription.PC_RELATIVE, _LINE_ARMS, f"$a003's `beq.w` to its horizontal arm: {_ACROSS}"),
    0xFCA202: transcription.Relocated(transcription.PC_RELATIVE, _LINE_ARMS, f"$a003's `bne.w` to its diagonal arm: {_ACROSS}"),
    0xFCFADC: transcription.Relocated(transcription.PC_RELATIVE, "LINEA_ROM_CONCAT", f"put_pixel's `bsr.w` to concat: {_ACROSS}"),
    0xFCFB22: transcription.Relocated(transcription.PC_RELATIVE, "LINEA_ROM_CONCAT", f"get_pixel's `bsr.w` to concat: {_ACROSS}"),
    0xFD19F6: transcription.Relocated(transcription.PC_RELATIVE, _LINE_ARMS,
                                      f"the vertical body's `bsr.w` to line_plane_words: {_ACROSS}"),
    0xFCFCA6: transcription.Relocated(transcription.ABSOLUTE, _LINE_ARMS,
                                      "$a005's `lea (table).l` of the fringe masks: the ROM's own table at $fca55c, which "
                                      "raster.S carries in its second region — so the reference is to raster.S's copy"),
}


@pytest.mark.parametrize("region", REGIONS, ids=[f"${region.lo:x}" for region in REGIONS])
def test_each_region_is_the_rom_s_words(region):
    transcription.assert_transcribed(region, relocated=RELOCATED)


@pytest.mark.parametrize("registers", sorted({*vdi_raster.CODE_POINTERS.values(), vdi_raster.DIAGONAL_CODE_POINTERS}))
def test_a_code_pointer_caller_clears_its_registers_and_nothing_else(registers):
    """Its cost is `test_transcribed.py`'s to measure, with every other caller's; what is this file's
    is the promise that makes it a narrow mask — the named registers zeroed, every other left as it was."""
    left = transcription.assert_caller_cost(vdi_raster.code_pointer_caller(registers))
    assert transcription.changed_from_dirty(left) == set(registers)
    assert all(left[name] == 0 for name in registers)


# ---- the behaviour, over the batteries' own cases ---------------------------------------------------------

@pytest.mark.parametrize("point", pixel.POINTS)
def test_concat_put_and_get(point):
    x, y = point
    vdi_raster.run_transcription("LINEA_ROM_CONCAT", {}, {"d0": pixel.CALLER_HIGH_WORD | x, "d1": y})
    vdi_raster.run_transcription("LINEA_ROM_PUT_PIXEL", pixel.point_pokes(x, y, colour=x % 16, onto=vdi_raster.CANVAS))
    vdi_raster.run_transcription("LINEA_ROM_GET_PIXEL", pixel.point_pokes(x, y, onto=vdi_raster.CANVAS))


@pytest.mark.parametrize("x,y", ((0xFFFF, 0), (0xFFF0, 1)))
def test_concat_of_a_negative_x(x, y):
    """(x & ~15) shifted ARITHMETICALLY and added as a LONG: a negative group before row 0 borrows from
    D1's high word."""
    vdi_raster.run_transcription("LINEA_ROM_CONCAT", {}, {"d0": x, "d1": y})


@pytest.mark.parametrize("planes", pixel.LARGE_SHIFT_PLANES)
@pytest.mark.parametrize("x", pixel.LARGE_SHIFT_XS)
def test_concat_and_put_of_a_count_of_16_or_more(planes, x):
    pokes = vdi.linea_pokes(PLANES=planes)
    vdi_raster.run_transcription("LINEA_ROM_CONCAT", pokes, {"d0": x, "d1": pixel.POINTS[1][1]})
    vdi_raster.run_transcription("LINEA_ROM_PUT_PIXEL", pixel.point_pokes(*pixel.LARGE_SHIFT_POINT, colour=0x5A5A,
                                                                          onto=vdi.merge_pokes(vdi_raster.CANVAS, pokes)))


def test_get_pixel_keeps_a_word_past_16_planes():
    vdi_raster.run_transcription("LINEA_ROM_GET_PIXEL", pixel.word_overflow_pokes())


@pytest.mark.parametrize("span", hline.SPANS.values(), ids=hline.SPANS.keys())
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("pattern", ("8 rows", "user"))
def test_hline_and_its_entries(span, mode, pattern):
    pokes = hline.hline_pokes(span, mode=mode, colour=0b0110, pattern=pattern)
    vdi_raster.run_transcription("LINEA_ROM_HLINE", pokes)
    x1, x2 = span
    vdi_raster.run_transcription("LINEA_ROM_HLINE_PATTERNED", pokes,
                                 {**vdi_raster.BASE_REGISTERS, "d4": x1, "d5": 57, "d6": x2})
    vdi_raster.run_transcription("LINEA_ROM_HLINE_SPAN", pokes, {**vdi_raster.BASE_REGISTERS, "d4": x1, "d5": 150,
                                                            "d6": x2, "a0": vdi.LINEA_LN_MASK, "d0": 0})
    vdi_raster.run_transcription("LINEA_ROM_CPU_HLINE", pokes,
                                 hline.body_registers(span, 33, vdi_raster.USER_PATTERN_AT, 0))


@pytest.mark.parametrize("span", hline.SPANS.values(), ids=hline.SPANS.keys())
@pytest.mark.parametrize("mode", MODES)
def test_the_hline_body_steps_a_multi_plane_pattern(span, mode):
    """The body's pattern handling, which a stride of 0 never runs: A0 steps A2 = 32 bytes a plane
    through the user pattern, as the contour fill's MULTIFILL entry hands it."""
    vdi_raster.run_transcription("LINEA_ROM_CPU_HLINE", hline.hline_pokes((0, 0), mode=mode, colour=0b1100, pattern="user"),
                                 hline.body_registers(span, 33, vdi_raster.USER_PATTERN_AT + vdi.WORD_BYTES,
                                                      vdi_raster.MULTIFILL_PLANE_WORDS * vdi.WORD_BYTES))


@pytest.mark.parametrize("pattern", ("16-row hatch", "user"))
@pytest.mark.parametrize("corners", rect.RECTS.values(), ids=rect.RECTS.keys())
@pytest.mark.parametrize("mode", MODES)
def test_the_rect_body_walks_a_pattern(pattern, corners, mode):
    """...and the rectangle body's: the first row masked by a PATMSK that is not 0, the row wrapping past
    it, and — the user pattern, MULTIFILL — the 32-byte plane stride."""
    vdi_raster.run_transcription("LINEA_ROM_CPU_RECT_FILL", rect.rect_pokes((0, 0, 0, 0), mode=mode, colour=0b0110,
                                                                            pattern=pattern),
                                 rect.body_registers(corners))


@pytest.mark.parametrize("corners", {**rect.RECTS, **rect.CUTS, **rect.MISSES}.values(),
                         ids={**rect.RECTS, **rect.CUTS, **rect.MISSES}.keys())
@pytest.mark.parametrize("mode", MODES)
def test_filled_rect_and_its_body(corners, mode):
    vdi_raster.run_transcription("LINEA_ROM_FILLED_RECT",
                                 rect.rect_pokes(corners, mode=mode, colour=0b1001, pattern="user", clip=rect.TIGHT_CLIP))
    if corners in rect.RECTS.values():
        vdi_raster.run_transcription("LINEA_ROM_CPU_RECT_FILL", rect.rect_pokes((0, 0, 0, 0), mode=mode, colour=0b0011),
                                     rect.body_registers(corners))


@pytest.mark.parametrize("delta", {**line.OCTANTS, **line.DIAGONALS}.values(),
                         ids={**line.OCTANTS, **line.DIAGONALS}.keys())
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("lstlin", line.LSTLIN)
def test_diagonal_lines(delta, mode, lstlin):
    vdi_raster.run_transcription("LINEA_ROM_LINE", line.line_pokes(*line.from_centre(delta), mode=mode, colour=0b0101,
                                                               style=vdi_raster.LINE_STYLES[3], lstlin=lstlin),
                                 code_pointers=vdi_raster.DIAGONAL_CODE_POINTERS)


@pytest.mark.parametrize("planes", line.GUARD_EDGE)
@pytest.mark.parametrize("mode", MODES)
def test_the_line_bodies_at_the_plane_guard(planes, mode):
    """8 planes draw and 9 return untouched — the diagonal arm, and the vertical body both through $a003
    and entered directly."""
    guard = vdi.linea_pokes(PLANES=planes)
    vdi_raster.run_transcription("LINEA_ROM_LINE", line.line_pokes(*line.from_centre(line.OCTANTS["ESE"]), mode=mode,
                                                               colour=0b0101, extra=guard),
                                 code_pointers=vdi_raster.DIAGONAL_CODE_POINTERS)
    x, y1, y2 = line.VERTICALS["down"]
    pokes = line.line_pokes((x, y1), (x, y2), mode=mode, colour=0b1010, extra=guard)
    vdi_raster.run_transcription("LINEA_ROM_LINE", pokes)
    vdi_raster.run_transcription("LINEA_ROM_CPU_VLINE", pokes, line.vline_body_registers(line.VERTICALS["down"]))


@pytest.mark.parametrize("vertical", line.VERTICALS.values(), ids=line.VERTICALS.keys())
@pytest.mark.parametrize("mode", MODES)
def test_vertical_lines_and_the_body(vertical, mode):
    x, y1, y2 = vertical
    pokes = line.line_pokes((x, y1), (x, y2), mode=mode, colour=0b1010, style=vdi_raster.LINE_STYLES[5], lstlin=0)
    vdi_raster.run_transcription("LINEA_ROM_LINE", pokes)
    vdi_raster.run_transcription("LINEA_ROM_CPU_VLINE", pokes, line.vline_body_registers(vertical))


@pytest.mark.parametrize("horizontal", line.HORIZONTALS.values(), ids=line.HORIZONTALS.keys())
@pytest.mark.parametrize("mode", MODES)
def test_horizontal_lines(horizontal, mode):
    x1, x2, y = horizontal
    vdi_raster.run_transcription("LINEA_ROM_LINE", line.line_pokes((x1, y), (x2, y), mode=mode, colour=0b1001,
                                                               style=vdi_raster.LINE_STYLES[1], lstlin=0))


@pytest.mark.parametrize("colour", vdi_raster.COLOURS)
def test_line_plane_words(colour):
    vdi_raster.run_transcription("LINEA_ROM_LINE_PLANE_WORDS", vdi_raster.colour_pokes(colour),
                                 {**vdi_raster.BASE_REGISTERS, "d3": vdi.SCREEN.planes, "a2": vdi_raster.PLANE_WORDS_AT})
