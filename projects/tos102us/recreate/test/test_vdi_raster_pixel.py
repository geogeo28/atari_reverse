"""concat ($fca1b8), $a001 put_pixel ($fcface) and $a002 get_pixel ($fcfb16): `src/vdi/raster.c`.

    concat:     mulsw BYTES_LIN,d1 / d2 = (x & ~15) asr SHIFT[PLANES] / d1 += d2.l / d0.w = x & 15
    put_pixel:  concat(ptsin[0]) / per plane: ror.w intin[0] -> or/and the pixel's bit
    get_pixel:  concat(ptsin[0]) / from the LAST plane down: addx the bit into D0

concat is the address arithmetic every pixel routine and the sprite and TextBlt bands share; its shift
table only has right answers for 1, 2, 4 and 8 planes, so each of the ST's three screen shapes is run.
put_pixel has NO clipping and no write mode: a colour index straight into every plane.
"""
import pytest

from harness import BASE_IMAGE, addrs

import case
import vdi
import vdi_raster
from case import merge_pokes

# Points at both ends of a group, across a group boundary, and at the screen's far corner.
POINTS = ((0, 0), (15, 11), (16, 12), (37, 100), (319, 199))
# D0's HIGH word as the caller leaves it: concat writes only the low word.
CALLER_HIGH_WORD = 0x5A5A_0000


def point_pokes(x, y, *, colour=None, onto=None):
    """ptsin[0] = (x, y) and, for put_pixel, intin[0] = colour, through the Line-A pointers."""
    arrays = {vdi.PTSIN_AT: vdi.pack_words(x, y)}
    if colour is not None:
        arrays[vdi.INTIN_AT] = vdi.pack_words(colour)
    return merge_pokes(onto, vdi.linea_pokes(PTSIN=vdi.PTSIN_AT, INTIN=vdi.INTIN_AT), arrays)


def rom_long(address):
    return case.long_in(BASE_IMAGE, address)


def test_the_opcode_table_serves_these_primitives_at_their_numbers():
    """`$fc9f0c` indexes LINEA_OPCODE_TABLE by the $Axxx number: the addresses these batteries enter
    are the ones $a001..$a005 reach."""
    served = {1: addrs.LINEA_ROM_PUT_PIXEL, 2: addrs.LINEA_ROM_GET_PIXEL, 3: addrs.LINEA_ROM_LINE,
              4: addrs.LINEA_ROM_HLINE, 5: addrs.LINEA_ROM_FILLED_RECT}
    for opcode, routine in served.items():
        assert rom_long(vdi.LINEA_OPCODE_TABLE + opcode * vdi.LONG_BYTES) == routine


# ---- concat ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("shape", (vdi_raster.LOW, vdi_raster.MEDIUM, vdi_raster.HIGH), ids=("low", "medium", "high"))
@pytest.mark.parametrize("point", POINTS)
def test_concat_answers_the_group_offset_and_the_bit(shape, point):
    x, y = point
    planes, bytes_per_line = shape
    result = vdi.run_primitive("LINEA_ROM_CONCAT", {"d0": CALLER_HIGH_WORD | x, "d1": y},
                               vdi_raster.geometry_pokes(shape))
    regs = result.info["regs"]
    assert regs["d1"] == y * bytes_per_line + x // vdi.PIXELS_PER_GROUP * planes * vdi.WORD_BYTES
    assert regs["d0"] == CALLER_HIGH_WORD | x % vdi.PIXELS_PER_GROUP


def test_concat_reads_bytes_lin_not_width():
    """Two fields hold a line's bytes, BYTES_LIN (-2) and WIDTH (+2); concat multiplies by the first."""
    y = POINTS[3][1]
    result = vdi.run_primitive("LINEA_ROM_CONCAT", {"d0": 0, "d1": y},
                               vdi.linea_pokes(WIDTH=vdi.SCREEN.bytes_per_line + vdi.WORD_BYTES))
    assert result.info["regs"]["d1"] == y * vdi.SCREEN.bytes_per_line


def test_concat_of_a_negative_x_sign_extends_its_group():
    """(x & ~15) is shifted as a SIGNED word and added as a long: x = -1 is one group BEFORE the row."""
    result = vdi.run_primitive("LINEA_ROM_CONCAT", {"d0": 0xFFFF, "d1": 1}, {})
    assert result.info["regs"]["d1"] == vdi.SCREEN.bytes_per_line - vdi.SCREEN.planes * vdi.WORD_BYTES


# Plane counts past the table's eight index the bytes of the code after it, and `asr.w d3,d2` takes the
# byte MODULO 64: 13 reads $29 (41) and 18 reads $ac (44), counts of 16 or more, which leave only x's sign.
# PLANES is the caller's to write, so these are inputs a program can hand $a001/$a002 — not the VDI's.
LARGE_SHIFT_PLANES = (13, 18)
SHIFT_COUNT_MODULUS = 64
# x far enough right that any count under 16 would leave a group in the offset — and one negative.
LARGE_SHIFT_XS = (1000, 0x7FF0, 0xFFF0)
LARGE_SHIFT_POINT = (LARGE_SHIFT_XS[0], POINTS[1][1])


def concat_shift(planes):
    return BASE_IMAGE[vdi_raster.HEADER["RASTER_CONCAT_SHIFT_TABLE"] + planes] % SHIFT_COUNT_MODULUS


@pytest.mark.parametrize("planes", LARGE_SHIFT_PLANES)
@pytest.mark.parametrize("x", LARGE_SHIFT_XS)
def test_concat_of_a_count_of_16_or_more_leaves_the_sign_of_x(planes, x):
    y = POINTS[1][1]
    assert concat_shift(planes) >= vdi.PIXELS_PER_GROUP, "the byte these plane counts index"
    result = vdi.run_primitive("LINEA_ROM_CONCAT", {"d0": x, "d1": y}, vdi.linea_pokes(PLANES=planes))
    sign = -1 if vdi.signed_word(x) < 0 else 0
    assert result.info["regs"]["d1"] == (y * vdi.SCREEN.bytes_per_line + sign) & 0xFFFF_FFFF


@pytest.mark.parametrize("planes", LARGE_SHIFT_PLANES)
def test_put_pixel_with_a_count_of_16_or_more_writes_the_row_s_first_group(planes):
    """...which puts every x >= 0 in the row's first group: x = 1000 writes group 0's planes."""
    vdi.run_primitive("LINEA_ROM_PUT_PIXEL", {}, point_pokes(*LARGE_SHIFT_POINT, colour=0x5A5A,
                                                             onto=merge_pokes(vdi_raster.CANVAS,
                                                                              vdi.linea_pokes(PLANES=planes))))


# ---- $a001 put_pixel -------------------------------------------------------------------------------------

@pytest.mark.parametrize("colour", range(1 << vdi.SCREEN.planes))
def test_put_pixel_writes_every_colour_index(colour):
    x, y = POINTS[3]
    result = vdi.run_primitive("LINEA_ROM_PUT_PIXEL", {}, point_pokes(x, y, colour=colour, onto=vdi_raster.CANVAS))
    assert result.pixel(x, y) == colour


@pytest.mark.parametrize("point", POINTS)
def test_put_pixel_touches_its_bit_and_no_other(point):
    """Over the canvas, a colour that differs from the pixel's in every plane: the rest of the group's
    words, whose bits differ plane by plane, must come back as they were (the differential)."""
    x, y = point
    colour = (1 << vdi.SCREEN.planes) - 1 - vdi.read_pixel(vdi_raster.CANVAS_IMAGE, x, y)
    result = vdi.run_primitive("LINEA_ROM_PUT_PIXEL", {}, point_pokes(x, y, colour=colour, onto=vdi_raster.CANVAS))
    assert result.pixel(x, y) == colour


@pytest.mark.parametrize("shape", (vdi_raster.MEDIUM, vdi_raster.HIGH), ids=("medium", "high"))
def test_put_pixel_serves_fewer_planes(shape):
    """PLANES words a group, and only the colour's low PLANES bits (a colour of $ff is one per plane)."""
    pokes = merge_pokes(vdi_raster.CANVAS, vdi_raster.geometry_pokes(shape))
    vdi.run_primitive("LINEA_ROM_PUT_PIXEL", {}, point_pokes(77, 51, colour=0xFF, onto=pokes))


# ---- $a002 get_pixel -------------------------------------------------------------------------------------

@pytest.mark.parametrize("point", POINTS)
def test_get_pixel_answers_the_colour_index(point):
    x, y = point
    result = vdi.run_primitive("LINEA_ROM_GET_PIXEL", {"d0": CALLER_HIGH_WORD}, point_pokes(x, y, onto=vdi_raster.CANVAS))
    assert result.info["regs"]["d0"] == vdi.read_pixel(vdi_raster.CANVAS_IMAGE, x, y), "moveq #0 clears D0 whole"


@pytest.mark.parametrize("shape", (vdi_raster.MEDIUM, vdi_raster.HIGH), ids=("medium", "high"))
def test_get_pixel_serves_fewer_planes(shape):
    pokes = merge_pokes(vdi_raster.CANVAS, vdi_raster.geometry_pokes(shape))
    vdi.run_primitive("LINEA_ROM_GET_PIXEL", {}, point_pokes(77, 51, onto=pokes))


# More than 16 planes: `addx.w d0,d0` keeps a WORD, so the planes read first (the last ones) are shifted
# out of it. 17 planes, with the word of the plane read first all ones: the ROM's answer loses its bit.
# (PLANES = 0 is the other end: `subq.w #1` then `dbf` reads 65,536 words below the pixel — a runaway
# no case stages.)
WORD_OVERFLOW_PLANES = 17


def word_overflow_pokes():
    """ptsin[0] in group 0 of a 17-plane screen, the word of the plane read first all ones."""
    x, y = POINTS[1]
    assert x < vdi.PIXELS_PER_GROUP, "group 0, whatever concat shifts (x & ~15) by"
    first_read = vdi.SCREEN.base + y * vdi.SCREEN.bytes_per_line + (WORD_OVERFLOW_PLANES - 1) * vdi.WORD_BYTES
    pokes = merge_pokes(vdi_raster.CANVAS, vdi.linea_pokes(PLANES=WORD_OVERFLOW_PLANES), {first_read: b"\xff\xff"})
    return point_pokes(x, y, onto=pokes)


def test_get_pixel_keeps_a_word_past_16_planes():
    result = vdi.run_primitive("LINEA_ROM_GET_PIXEL", {"d0": CALLER_HIGH_WORD}, word_overflow_pokes())
    assert result.info["regs"]["d0"] <= 0xFFFF, "a word, cleared whole by `moveq #0`"


# ---- through the exception, as a program calls them --------------------------------------------------------

def test_put_and_get_pixel_through_the_exception():
    x, y = POINTS[2]
    vdi.run_through_exception("LINEA_ROM_PUT_PIXEL", 1, {}, point_pokes(x, y, colour=9, onto=vdi_raster.CANVAS))
    result = vdi.run_through_exception("LINEA_ROM_GET_PIXEL", 2, {}, point_pokes(x, y, onto=vdi_raster.CANVAS))
    assert result.info["regs"]["d0"] == vdi.read_pixel(vdi_raster.CANVAS_IMAGE, x, y)


vdi_raster.register("the far corner", "LINEA_ROM_CONCAT", {}, regs={"d0": CALLER_HIGH_WORD | 319, "d1": 199})
vdi_raster.register("colour 9", "LINEA_ROM_PUT_PIXEL", point_pokes(*POINTS[3], colour=9, onto=vdi_raster.CANVAS))
vdi_raster.register("a pixel of the canvas", "LINEA_ROM_GET_PIXEL", point_pokes(*POINTS[3], onto=vdi_raster.CANVAS))
