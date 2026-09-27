"""VDI LINE attributes — vsl_type (15), vsl_width (16), vsl_ends (108), vsl_color (17), vsl_udsty (113):
`src/vdi/attributes.c`.

    vsl_type    contrl[4]=1; s = intin[0]-1; s outside 0..6 -> 0;  WS_LINE_INDEX = s; intout[0] = s+1
    vsl_width   w = ptsin[0]; w<1 -> 1, w>SIZ_TAB[6] -> SIZ_TAB[6]; w = ((w-1)/2)*2+1 (`divs.w #2`);
                contrl[2]=1; WS_LINE_WIDTH = w; ptsout = (w, 0)
    vsl_ends    contrl[4]=2; each of intin[0..1] outside 0..2 -> 0; (WS_LINE_BEG, intout[0]), (WS_LINE_END, intout[1])
    vsl_color   contrl[4]=1; c = intin[0]; c outside 0..DEV_TAB[13]-1 -> 1; intout[0] = c; WS_LINE_COLOR = MAP_COL[c]
    vsl_udsty   WS_UD_LS = intin[0], raw — no clamp, no answer, no count

Every clamp is SIGNED (`bge`/`blt` on a word), so $8000 is below the range, not above it; each is
driven at both bounds, one past each, and the far ends of the word. The bounds vsl_width and vsl_color
read are Line-A tables a program can rewrite through `$a000`'s base, so each is also run over a
staged table, which is what shows the bound is READ rather than spelt.
"""
import pytest

from harness import BASE_IMAGE

import vdi
import vdi_attributes as attr

TYPE, WIDTH, ENDS, COLOR, UDSTY = ("VDI_ROM_VSL_TYPE", "VDI_ROM_VSL_WIDTH", "VDI_ROM_VSL_ENDS",
                                   "VDI_ROM_VSL_COLOR", "VDI_ROM_VSL_UDSTY")
WORD_EDGES = (-0x8000, 0x7FFF)


def siz_tab(image, index):
    return vdi.linea(image, "SIZ_TAB")[index]


# ---- vsl_type ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("style", (1, 2, 6, 7, 0, 8, -1, *WORD_EDGES))
def test_vsl_type_stores_the_style_zero_based_and_answers_it(style):
    result = attr.run(TYPE, attr.call(TYPE, (style,), fields={"LINE_INDEX": attr.STALE}))
    stored = style - 1 if 1 <= style <= 7 else 0
    assert result.workstation("LINE_INDEX") == stored
    assert result.intout(1) == [stored + 1]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1


# ---- vsl_width --------------------------------------------------------------------------------------
SNAPSHOT_WIDEST = 40        # SIZ_TAB[6] in the captured machine: EVEN, so the cap itself rounds down


def expected_width(width, widest):
    width = 1 if width < 1 else min(width, widest)
    quotient = abs(width - 1) // 2 * (1 if width - 1 >= 0 else -1)      # `divs.w` truncates to zero
    return quotient * 2 + 1


@pytest.mark.parametrize("width", (1, 2, 3, 4, 39, 40, 41, 0, -5, *WORD_EDGES))
def test_vsl_width_clamps_rounds_down_to_odd_and_answers_a_point(width):
    result = attr.run(WIDTH, attr.call(WIDTH, ptsin=(width, attr.STALE), fields={"LINE_WIDTH": attr.STALE}))
    assert siz_tab(result.final, vdi.VDI_SIZ_TAB_MAX_LINE_WIDTH_INDEX) == SNAPSHOT_WIDEST
    answered = expected_width(width, SNAPSHOT_WIDEST)
    assert result.workstation("LINE_WIDTH") == answered
    assert result.ptsout(2) == [answered, 0]
    assert result.contrl(vdi.CONTRL_N_PTSOUT) == 1
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 0, "the width answers a point, not a word"


# A table a program rewrote: an odd cap (kept as it is), and a cap BELOW 1, where the word `w - 1`
# goes negative and `divs.w` truncating towards zero is what makes -3 come back as -3 (a shift would
# make it -5). No workstation the ROM builds holds either; the Line-A table is the program's to write.
@pytest.mark.parametrize("widest, width", ((9, 9), (9, 20), (-3, 5), (0, 5)))
def test_vsl_width_reads_its_cap_out_of_siz_tab(widest, width):
    table = vdi.linea(BASE_IMAGE, "SIZ_TAB")
    table[vdi.VDI_SIZ_TAB_MAX_LINE_WIDTH_INDEX] = widest
    pokes = attr.call(WIDTH, ptsin=(width, 0), fields={"LINE_WIDTH": attr.STALE}, onto=vdi.linea_pokes(SIZ_TAB=table))
    result = attr.run(WIDTH, pokes)
    assert result.workstation("LINE_WIDTH") == expected_width(width, widest) & 0xFFFF


# ---- vsl_ends ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("begin, end", ((0, 0), (1, 2), (2, 1), (3, -1), (-1, 3), WORD_EDGES))
def test_vsl_ends_clamps_each_end_on_its_own(begin, end):
    result = attr.run(ENDS, attr.call(ENDS, (begin, end), fields={"LINE_BEG": attr.STALE, "LINE_END": attr.STALE}))
    kept = [value if 0 <= value <= 2 else 0 for value in (begin, end)]
    assert [result.workstation("LINE_BEG"), result.workstation("LINE_END")] == kept
    assert result.intout(2) == kept
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 2


# ---- vsl_color --------------------------------------------------------------------------------------
SNAPSHOT_COLOURS = 16       # DEV_TAB[13] in the captured machine (low resolution)


@pytest.mark.parametrize("colour", (0, 1, 2, 15, 16, -1, *WORD_EDGES))
def test_vsl_color_answers_the_index_and_stores_its_pen(colour):
    result = attr.run(COLOR, attr.call(COLOR, (colour,), fields={"LINE_COLOR": attr.STALE}))
    assert vdi.linea(result.final, "DEV_TAB")[vdi.VDI_DEV_TAB_COLOURS_INDEX] == SNAPSHOT_COLOURS
    index = colour if 0 <= colour < SNAPSHOT_COLOURS else 1
    assert result.intout(1) == [index]
    assert result.workstation("LINE_COLOR") == attr.rom_map_col(index)
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1


@pytest.mark.parametrize("colour", (0, 1, 2))
def test_vsl_color_bounds_against_dev_tab_not_a_constant(colour):
    """DEV_TAB as the MONOCHROME workstation answers it: two colours."""
    result = attr.run(COLOR, attr.call(COLOR, (colour,), fields={"LINE_COLOR": attr.STALE}, onto=attr.colour_count_pokes(2)))
    index = colour if colour < 2 else 1
    assert result.intout(1) == [index]


@pytest.mark.parametrize("colour", (0, 5, 0x7FFF, -1))
@pytest.mark.parametrize("name,field", attr.COLOUR_SETTERS)
def test_every_colour_setter_bounds_against_the_count_itself(name, field, colour):
    """`cmp.w DEV_TAB[13],d7 / bge`: a count of $8000 is below every index, so every index is colour 1 —
    where a bound of the count LESS ONE would wrap to $7fff and let 0..$7fff through."""
    result = attr.run(name, attr.call(name, (colour,), fields={field: attr.STALE}, onto=attr.colour_count_pokes(-0x8000)))
    assert result.intout(1) == [1]
    assert result.workstation(field) == attr.rom_map_col(1)


def test_vsl_color_writes_the_current_workstation_not_the_physical_one():
    result = attr.run(COLOR, attr.call(COLOR, (3,), virtual=True, fields={"LINE_COLOR": attr.STALE}))
    assert result.workstation("LINE_COLOR", at=vdi.VIRTUAL_WORK_AT) == attr.rom_map_col(3)
    attr.assert_physical_untouched(result)


# ---- vsl_udsty ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("pattern", (0x0000, 0xFFFF, 0x5555, 0x8000, 0x0001))
def test_vsl_udsty_stores_the_word_raw_and_answers_nothing(pattern):
    result = attr.run(UDSTY, attr.call(UDSTY, (pattern,), fields={"UD_LS": attr.STALE}))
    assert result.workstation("UD_LS") == pattern
    assert result.intout(1) == [vdi.FILL * 0x0101], "no answer word"
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 0
    assert result.linea("LN_MASK") == vdi.linea(BASE_IMAGE, "LN_MASK"), (
        "the Line-A style mask the rasterizer uses is not this setter's to write")


# ---- every setter's store order, and one over a virtual workstation --------------------------------
ORDERED = ((TYPE, "LINE_INDEX", (3,), ()), (ENDS, "LINE_END", (1, 2), ()), (COLOR, "LINE_COLOR", (5,), ()),
           (WIDTH, "LINE_WIDTH", (), (7, 0)))


@pytest.mark.parametrize("name, field, intin, ptsin", ORDERED)
def test_the_stores_land_in_the_roms_order(name, field, intin, ptsin):
    for _label, pokes in attr.overlap_cases(name, field, intin, ptsin):
        attr.run(name, pokes)


def test_the_width_s_point_lands_in_the_roms_order():
    for _label, pokes in attr.point_overlap_cases(WIDTH, "LINE_WIDTH", (7, 0)):
        attr.run(WIDTH, pokes)


@pytest.mark.parametrize("name, field, intin, ptsin", ORDERED + ((UDSTY, "UD_LS", (0x1234,), ()),))
def test_a_virtual_workstation_is_the_one_written(name, field, intin, ptsin):
    result = attr.run(name, attr.call(name, intin, ptsin, virtual=True, fields={field: attr.STALE}))
    assert result.workstation(field, at=vdi.VIRTUAL_WORK_AT) != attr.STALE
    attr.assert_physical_untouched(result)


# ---- Tier 3: the realistic worst of each --------------------------------------------------------------
attr.register("in range", TYPE, attr.call(TYPE, (4,)))
attr.register("out of range", TYPE, attr.call(TYPE, (9,)))
attr.register("capped, rounded", WIDTH, attr.call(WIDTH, ptsin=(99, 0)))
attr.register("below 1", WIDTH, attr.call(WIDTH, ptsin=(0, 0)))
attr.register("in range", ENDS, attr.call(ENDS, (1, 2)))
attr.register("both out of range", ENDS, attr.call(ENDS, (3, -1)))
attr.register("in range", COLOR, attr.call(COLOR, (5,)))
attr.register("out of range", COLOR, attr.call(COLOR, (16,)))
attr.register("a pattern", UDSTY, attr.call(UDSTY, (0x5555,)))
