"""The TEXT LAYER's two measuring inquiries — `src/vdi/text.c`:

    vqt_extent (116, $fce62a)      vqt_width (117, $fce7f0)

Both read the CURRENT FONT through LINEA_CUR_FONT and a character's advance out of its offset table. The ROM
fonts are all monospaced and have no horizontal offset table, so besides them the cases stage the one font
that reaches the other arms — a proportional GDOS face with a HOR_TABLE (`vdi_text_c.proportional_font`).

vqt_extent SUMS IN MEMORY (VDI_EXTENT_SCRATCH, and the height beside it) and reads both back for every
corner it answers, so its overlap cases lay intin and ptsout over those two words.
"""
import pytest

from harness import addrs

import vdi
import vdi_helpers
import vdi_text
import vdi_text_c as text
from vdi_text import font_field
from vdi_text_c import header_at, proportional_advance, proportional_font, rom_advance, rom_header_pokes

WORD = vdi.WORD_BYTES
DOUBLE = vdi_helpers.VDI_DDA_DOUBLE
SCALE_UP, SCALE_DOWN = vdi_helpers.VDI_SCALE_UP, vdi_helpers.VDI_SCALE_DOWN
THICKEN, SKEW, OUTLINE = vdi.VDI_STYLE_THICKEN_MASK, vdi.VDI_STYLE_SKEW_MASK, vdi.VDI_STYLE_OUTLINE_MASK
PROPORTIONAL = header_at(0)
FIRST_32 = header_at(1)               # the ROM 8x8 from character 32: its own offset table, 32 entries in
WRAPPING = header_at(2)               # the 8x8 over every character 0..$ffff, with a HOR_TABLE
PROPORTIONAL_32 = header_at(3)        # the proportional face from character 32, its tables 32 entries in
FONTS = {**vdi_text.FONTS, "proportional": PROPORTIONAL, "first 32": FIRST_32, "wrapping": WRAPPING,
         "proportional 32": PROPORTIONAL_32}
FONT_POKES = vdi.merge_pokes(
    proportional_font(PROPORTIONAL),
    rom_header_pokes(FIRST_32, "8x8", FIRST_ADE=32, OFF_TABLE=font_field("8x8", "OFF_TABLE") + 32 * WORD),
    rom_header_pokes(WRAPPING, "8x8", FIRST_ADE=0, LAST_ADE=0xFFFF, HOR_TABLE=text.WRAPPED_HOR_TABLE,
                     FLAGS=font_field("8x8", "FLAGS") | vdi.FONT_FLAG_HOR_TABLE_MASK),
    {text.WRAPPED_HOR_ENTRY_AT: bytes([0x85, 0x06])},
    rom_header_pokes(PROPORTIONAL_32, "8x8", ID=3, FIRST_ADE=32, LAST_ADE=text.PROPORTIONAL_LAST,
                     OFF_TABLE=text.PROPORTIONAL_OFF_AT + 32 * WORD,
                     FLAGS=vdi.FONT_FLAG_SWAPPED_MASK))
HELLO = tuple(map(ord, "Hello, world"))


def machine(font, *, style=0, rotation=0, scale=None, virtual=None):
    """The workstation dispatched with `font` current, the effects `style`, the rotation, and — `scale` a
    (DDA increment, direction) pair — scaling on."""
    record = dict(CUR_FONT=FONTS[font], STYLE=style, CHUP=rotation)
    if scale is not None:
        record.update(SCALED=1, DDA_INC=scale[0], T_SCLSTS=scale[1])
    if virtual is not None:
        return vdi.virtual_workstation(virtual, onto=FONT_POKES, **record)
    return vdi.dispatched_pokes(onto=FONT_POKES, **record)


def stale_scratch():
    return {vdi.VDI_EXTENT_SCRATCH: vdi.pack_words(vdi.STALE_WORD, vdi.STALE_WORD)}


def advance(font, character):
    if font in ("proportional", "proportional 32"):
        return proportional_advance(character)
    if font == "first 32":
        return rom_advance("8x8", character)
    return rom_advance(font, character)


def scaled(width, scale):
    if scale is None:
        return width
    if scale[0] == DOUBLE:
        return (2 * width) & 0xFFFF
    return vdi_helpers.answer(vdi_helpers.run_call("VDI_ROM_ACT_SIZ", vdi.case.word_arg(width), (width,),
                                                   vdi.linea_pokes(DDA_INC=scale[0], T_SCLSTS=scale[1])))


# ==== vqt_extent =======================================================================================
def extent_call(font, string, **kwargs):
    pokes = vdi.function_pokes("VDI_ROM_VQT_EXTENT", intin=string, workstation_pokes=machine(font, **kwargs))
    return vdi.merge_pokes(pokes, stale_scratch())


def vqt_extent(pokes):
    return vdi.run_function("VDI_ROM_VQT_EXTENT", pokes)


def expected_box(font, string, style=0, scale=None):
    """(width, height) as the ROM builds them."""
    header = vdi.make_image(FONT_POKES) if font not in vdi_text.FONTS else vdi.BASE_IMAGE
    field = lambda name: vdi.read_field(header, "FONT", name, FONTS[font])                    # noqa: E731
    width = scaled(sum(advance(font, character) for character in string) & 0xFFFF, scale)
    if style & THICKEN and not field("FLAGS") & vdi.FONT_FLAG_MONOSPACE_MASK:
        width += field("THICKEN") * len(string)
    if style & SKEW:
        width += field("LEFT_OFFSET") + field("RIGHT_OFFSET")
    height = field("TOP") + field("BOTTOM") + 1
    if style & OUTLINE:
        width, height = width + 2 * len(string), height + 2
    return width & 0xFFFF, height & 0xFFFF


def corners(rotation, width, height):
    """The four corners the ROM answers — at 270 degrees ITS OWN, not the box turned."""
    return {0: [0, 0, width, 0, width, height, 0, height],
            900: [height, 0, height, width, 0, width, 0, 0],
            1800: [width, height, 0, height, 0, 0, width, 0],
            2700: [0, height, 0, 0, height, 0, width, height]}[rotation]


@pytest.mark.parametrize("rotation", (0, 900, 1800, 2700))
@pytest.mark.parametrize("font", ("6x6", "8x8", "8x16", "proportional", "first 32", "proportional 32"))
def test_vqt_extent_answers_the_box_for_each_right_angle(font, rotation):
    result = vqt_extent(extent_call(font, HELLO, rotation=rotation))
    assert result.ptsout(8) == corners(rotation, *expected_box(font, HELLO))
    assert result.contrl(vdi.CONTRL_N_PTSOUT) == 4
    assert result.word(vdi.VDI_RESULT) == vdi.VDI_RESULT_SET


@pytest.mark.parametrize("rotation", (450, 1, 3600, 0xFC7C))
def test_vqt_extent_answers_no_corners_for_another_rotation(rotation):
    """contrl[2] says 4 all the same; the width and height are still left in the scratch words."""
    result = vqt_extent(extent_call("proportional", HELLO, rotation=rotation))
    assert result.ptsout(8) == [vdi.FILL * 0x101] * 8
    assert result.contrl(vdi.CONTRL_N_PTSOUT) == 4
    assert result.words(vdi.VDI_EXTENT_SCRATCH, 2) == list(expected_box("proportional", HELLO))


STYLES = (THICKEN, SKEW, OUTLINE, THICKEN | SKEW | OUTLINE, 0x0100 | THICKEN, 0x00FF)


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("font", ("8x8", "proportional"))
def test_vqt_extent_widens_for_the_effects(font, style):
    """Bold widens only a font NOT flagged monospace — never a ROM one; the low byte's bits are the ones
    tested (`btst` on $29f5), so $0100 is no effect at all."""
    result = vqt_extent(extent_call(font, HELLO, style=style))
    assert result.ptsout(8) == corners(0, *expected_box(font, HELLO, style & 0xFF))


SCALES = ((DOUBLE, SCALE_UP), (0x8000, SCALE_UP), (0xC000, SCALE_DOWN), (0x2000, SCALE_UP))


@pytest.mark.parametrize("scale", SCALES)
def test_vqt_extent_scales_the_sum_before_the_effects(scale):
    style = THICKEN | SKEW | OUTLINE
    result = vqt_extent(extent_call("proportional", HELLO, style=style, scale=scale))
    assert result.ptsout(8) == corners(0, *expected_box("proportional", HELLO, style, scale))


# Characters the offset table is indexed BELOW for: under the first character, and $8000 or more past it.
@pytest.mark.parametrize("font,string", (("first 32", (31, 0, 65)), ("8x8", (0x8000, 0xFFFF, 0x9234)),
                                         ("wrapping", (0x4000, 0x7FFF, 0x8001))))
def test_vqt_extent_indexes_the_offset_table_sign_extended(font, string):
    """Each advance read at `table + 2 * sext(character - first)`, the ROM's own words wherever that lands."""
    image = vdi.make_image(FONT_POKES)
    table, first = (vdi.read_field(image, "FONT", name, FONTS[font]) for name in ("OFF_TABLE", "FIRST_ADE"))
    width = 0
    for character in string:
        entry = table + vdi.signed_word((character - first) & 0xFFFF) * WORD
        width += vdi.rom_word(entry + WORD) - vdi.rom_word(entry)
    assert vqt_extent(extent_call(font, string)).ptsout(8)[2] == width & 0xFFFF


def test_vqt_extent_of_no_characters():
    result = vqt_extent(extent_call("proportional", ()))
    assert result.ptsout(8) == corners(0, 0, expected_box("proportional", ())[1])


def test_vqt_extent_count_is_signed():
    """contrl[3] = $8000: no character summed (`blt` against a negative count)."""
    pokes = vdi.merge_pokes(extent_call("proportional", HELLO),
                            {vdi.CONTRL_AT + vdi.CONTRL_N_INTIN: vdi.pack_words(0x8000)})
    assert vqt_extent(pokes).ptsout(3)[2] == 0


def test_vqt_extent_sums_in_memory():
    """intin laid over the dispatcher's two alignment copies and then the SUM itself: the third character
    read is the width summed so far — which a sum kept in a register would read as the 0 it was cleared to."""
    work = vdi.dispatched_pokes(onto=FONT_POKES, CUR_FONT=PROPORTIONAL, H_ALIGN=2, V_ALIGN=3)
    pokes = vdi.merge_pokes(vdi.function_pokes("VDI_ROM_VQT_EXTENT", intin=(0, 0, 0), workstation_pokes=work),
                            stale_scratch(), vdi.linea_pokes(INTIN=vdi.VDI_TEXT_H_ALIGN))
    so_far = proportional_advance(2) + proportional_advance(3)
    assert proportional_advance(so_far) != proportional_advance(0), "the sum in memory must read differently"
    assert vqt_extent(pokes).word(vdi.VDI_EXTENT_SCRATCH) == so_far + proportional_advance(so_far)


def test_vqt_extent_reads_the_scratch_back_for_every_corner():
    """ptsout laid two words below the width: corner word 2 rewrites the width, word 3 CLEARS the height,
    and every later height is read back as that 0."""
    pokes = vdi.merge_pokes(extent_call("proportional", HELLO),
                            vdi.linea_pokes(PTSOUT=vdi.VDI_EXTENT_SCRATCH - 2 * WORD))
    width, _height = expected_box("proportional", HELLO)
    assert vqt_extent(pokes).words(vdi.VDI_EXTENT_SCRATCH - 2 * WORD, 8) == [0, 0, width, 0, width, 0, 0, 0]


def test_vqt_extent_on_a_virtual_workstation():
    result = vqt_extent(vdi.merge_pokes(
        vdi.function_pokes("VDI_ROM_VQT_EXTENT", intin=HELLO, workstation_pokes=machine("proportional", virtual=6)),
        stale_scratch()))
    assert result.ptsout(8) == corners(0, *expected_box("proportional", HELLO))


# ==== vqt_width ========================================================================================
def width_call(font, character, **kwargs):
    return vdi.function_pokes("VDI_ROM_VQT_WIDTH", intin=(character,), workstation_pokes=machine(font, **kwargs))


def vqt_width(pokes):
    return vdi.run_function("VDI_ROM_VQT_WIDTH", pokes)


def signed_byte(value):
    return (value - 0x100 if value & 0x80 else value) & 0xFFFF


@pytest.mark.parametrize("font,character", (("6x6", 0), ("8x8", 65), ("8x16", 255), ("first 32", 32),
                                            ("first 32", 255), ("proportional 32", 70)))
def test_vqt_width_answers_a_monospaced_advance_and_no_offsets(font, character):
    result = vqt_width(width_call(font, character))
    assert result.intout(1) == [character]
    assert result.ptsout(6) == [advance(font, character), vdi.FILL * 0x101, 0, vdi.FILL * 0x101, 0, vdi.FILL * 0x101]
    assert (result.contrl(vdi.CONTRL_N_PTSOUT), result.contrl(vdi.CONTRL_N_INTOUT)) == (3, 1)
    assert result.word(vdi.VDI_RESULT) == vdi.VDI_RESULT_SET


@pytest.mark.parametrize("font,character", (("first 32", 31), ("first 32", 0), ("first 32", 256), ("8x8", 0x100),
                                            ("8x8", 0xFFFF), ("proportional", 0x8000)))
def test_vqt_width_answers_minus_1_outside_the_font(font, character):
    """UNSIGNED bounds: $ffff and $8000 are past the last, not below the first. ptsout[0] is left alone; its
    two offsets were cleared first all the same."""
    result = vqt_width(width_call(font, character))
    assert result.intout(1) == [0xFFFF]
    assert result.ptsout(5) == [vdi.FILL * 0x101, vdi.FILL * 0x101, 0, vdi.FILL * 0x101, 0]
    assert result.contrl(vdi.CONTRL_N_PTSOUT) == 3


@pytest.mark.parametrize("character", (0, 32, 65, 70, 101, 255))
def test_vqt_width_answers_the_hor_table_s_offsets_signed(character):
    result = vqt_width(width_call("proportional", character))
    left, right = text.proportional_hor()[2 * character:2 * character + 2]
    assert result.ptsout(5) == [proportional_advance(character), vdi.FILL * 0x101, signed_byte(left),
                                vdi.FILL * 0x101, signed_byte(right)]


@pytest.mark.parametrize("scale", SCALES)
def test_vqt_width_scales_the_advance_in_place(scale):
    result = vqt_width(width_call("proportional", 69, scale=scale))
    assert result.ptsout(1) == [scaled(proportional_advance(69), scale)]


def test_vqt_width_indexes_the_hor_table_by_a_wrapped_word():
    """$4000 characters past the first: the offset table at +$8002 (a 32-bit doubling), the HOR table
    through a doubled index that WRAPS to -$8000 — the two bytes staged 32 KB below its base."""
    result = vqt_width(width_call("wrapping", 0x4000))
    assert result.ptsout(5)[2:] == [signed_byte(0x85), vdi.FILL * 0x101, signed_byte(0x06)]


@pytest.mark.parametrize("character", (0x8000, 0xFFFF, 0x7FFF))
def test_vqt_width_indexes_the_offset_table_sign_extended(character):
    result = vqt_width(width_call("wrapping", character))
    below = font_field("8x8", "OFF_TABLE") + vdi.signed_word(character) * WORD
    assert result.ptsout(1) == [(vdi.rom_word(below + WORD) - vdi.rom_word(below)) & 0xFFFF]


def test_vqt_width_clears_the_offsets_before_it_reads_intin():
    """ptsout[2] laid on intin[0]: cleared first, so the character asked is 0."""
    pokes = vdi.merge_pokes(width_call("proportional", 65), vdi.linea_pokes(PTSOUT=vdi.INTIN_AT - 2 * WORD))
    assert vqt_width(pokes).intout(1) == [0]


@pytest.mark.parametrize("character", (65, 1))
def test_vqt_width_writes_its_counts_after_the_answer(character):
    assert vqt_width(vdi.intout_over(width_call("first 32", character))).contrl(vdi.CONTRL_N_INTOUT) == 1


# ptsout laid at the current font + 64, so ptsout[2] IS the high word of the font's HOR_TABLE: the ROM stores the
# left offset there ($fce890) and then READS THE POINTER AGAIN for the right one ($fce894) — a build that kept the
# first read takes the right offset from the old table (the target GCC's type-based alias analysis did). The
# table's high word must start at 0, since ptsout[2] is cleared before either read, so the table is the
# snapshot's own low RAM read as one: the system variables at $400, whose entry for character 5 has a small
# positive left byte — which moves the re-read into the snapshot's RAM at left * $10000 + $400, onto a right
# byte that differs from the entry's own.
PTSOUT_OVER_HOR_HIGH_WORD = vdi.FONT_HOR_TABLE - 2 * WORD
LOW_RAM_HOR_TABLE = 0x400
HOR_OVERLAP_CHARACTER = 5
HOR_OVERLAP_ENTRY = LOW_RAM_HOR_TABLE + text.HOR_ENTRY_BYTES * HOR_OVERLAP_CHARACTER
HOR_OVERLAP_LEFT = vdi.BASE_IMAGE[HOR_OVERLAP_ENTRY]
HOR_OVERLAP_MOVED_ENTRY = (HOR_OVERLAP_LEFT << 16) + HOR_OVERLAP_ENTRY
assert 0 < HOR_OVERLAP_LEFT < 0x10 and vdi.BASE_IMAGE[HOR_OVERLAP_MOVED_ENTRY + 1] != vdi.BASE_IMAGE[HOR_OVERLAP_ENTRY + 1], (
    "the snapshot's entry must move the re-read onto a right byte that differs")


def hor_overlap_call():
    return vdi.merge_pokes(width_call("proportional", HOR_OVERLAP_CHARACTER),
                           vdi.field_pokes("FONT", PROPORTIONAL, HOR_TABLE=LOW_RAM_HOR_TABLE),
                           vdi.linea_pokes(PTSOUT=PROPORTIONAL + PTSOUT_OVER_HOR_HIGH_WORD))


def test_vqt_width_reads_the_hor_table_again_after_storing_the_left_offset():
    ptsout = vqt_width(hor_overlap_call()).words(PROPORTIONAL + PTSOUT_OVER_HOR_HIGH_WORD, 5)
    assert ptsout[2] == HOR_OVERLAP_LEFT
    assert ptsout[4] == signed_byte(vdi.BASE_IMAGE[HOR_OVERLAP_MOVED_ENTRY + 1])


def test_vqt_width_on_a_virtual_workstation():
    result = vqt_width(vdi.function_pokes("VDI_ROM_VQT_WIDTH", intin=(66,),
                                          workstation_pokes=machine("proportional", virtual=6)))
    assert result.ptsout(1) == [proportional_advance(66)]


# ==== Tier 3: the worst realistic rows ================================================================
vdi.register("vdi_vqt_extent, twelve characters, 8x8", addrs.VDI_ROM_VQT_EXTENT, extent_call("8x8", HELLO))
vdi.register("vdi_vqt_extent, twelve characters, every effect, scaled", addrs.VDI_ROM_VQT_EXTENT,
             extent_call("proportional", HELLO, style=THICKEN | SKEW | OUTLINE, scale=(0x8000, SCALE_UP), rotation=900))
vdi.register("vdi_vqt_extent, one character", addrs.VDI_ROM_VQT_EXTENT, extent_call("8x8", (65,)))
vdi.register("vdi_vqt_width, 8x8", addrs.VDI_ROM_VQT_WIDTH, width_call("8x8", 65))
vdi.register("vdi_vqt_width, proportional, offsets, scaled", addrs.VDI_ROM_VQT_WIDTH,
             width_call("proportional", 69, scale=(0x8000, SCALE_UP)))
vdi.register("vdi_vqt_width, outside the font", addrs.VDI_ROM_VQT_WIDTH, width_call("first 32", 31))
vdi.register("vdi_vqt_width, ptsout over the font's HOR_TABLE", addrs.VDI_ROM_VQT_WIDTH, hor_overlap_call())
