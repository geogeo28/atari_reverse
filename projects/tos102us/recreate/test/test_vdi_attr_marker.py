"""VDI MARKER attributes — vsm_height (19), vsm_type (18), vsm_color (20): `src/vdi/attributes.c`.

    vsm_height  h = ptsin[1] into SIZ_TAB[9]..SIZ_TAB[11]; WS_MARK_HEIGHT = h;
                scale = (h + SIZ_TAB[9]/2) / SIZ_TAB[9] (`divs.w`); WS_MARK_SCALE = scale;
                contrl[2]=1; ptsout = (scale*SIZ_TAB[8], scale*SIZ_TAB[9]) (`muls.w`); VDI_RESULT = 1
    vsm_type    t = intin[0]-1; t outside 0..5 -> 2 (the asterisk); WS_MARK_INDEX = t; intout[0] = t+1; contrl[4]=1 LAST
    vsm_color   vsl_color's clamp and map into WS_MARK_COLOR, with contrl[4]=1 LAST

vsm_height is the setter here with real arithmetic: the scale rounds the height to the nearest whole
multiple of the smallest marker, so the cases cross every rounding boundary of the captured SIZ_TAB
(11-pixel steps, rounding at +6) and run once over a staged table, which is what shows all three
sizes are READ rather than spelt. It is also one of the few functions that sets VDI_RESULT, which the
dispatcher cleared (`vdi.dispatcher_copies` stages it cleared).
"""
import pytest

from harness import BASE_IMAGE

import vdi
import vdi_attributes as attr

HEIGHT, TYPE, COLOR = "VDI_ROM_VSM_HEIGHT", "VDI_ROM_VSM_TYPE", "VDI_ROM_VSM_COLOR"
WORD_EDGES = (-0x8000, 0x7FFF)
SIZ_TAB = vdi.linea(BASE_IMAGE, "SIZ_TAB")


def expected_marker(height, table):
    narrowest = table[vdi.VDI_SIZ_TAB_MIN_MARK_WIDTH_INDEX]
    lowest = table[vdi.VDI_SIZ_TAB_MIN_MARK_HEIGHT_INDEX]
    height = max(lowest, min(height, table[vdi.VDI_SIZ_TAB_MAX_MARK_HEIGHT_INDEX]))
    scale = (height + lowest // 2) // lowest
    return height, scale, [scale * narrowest & 0xFFFF, scale * lowest & 0xFFFF]


def height_pokes(height, onto=None, virtual=False):
    return attr.call(HEIGHT, ptsin=(attr.STALE, height), virtual=virtual, onto=onto,
                     fields={"MARK_HEIGHT": attr.STALE, "MARK_SCALE": attr.STALE})


@pytest.mark.parametrize("height", (11, 16, 17, 22, 27, 28, 87, 88, 89, 10, 0, -1, *WORD_EDGES))
def test_vsm_height_clamps_scales_and_answers_the_size_it_gives(height):
    result = attr.run(HEIGHT, height_pokes(height))
    stored, scale, point = expected_marker(height, SIZ_TAB)
    assert (result.workstation("MARK_HEIGHT"), result.workstation("MARK_SCALE")) == (stored, scale)
    assert result.ptsout(2) == point
    assert result.contrl(vdi.CONTRL_N_PTSOUT) == 1
    assert result.word(vdi.VDI_RESULT) == vdi.VDI_RESULT_SET


# A table a program rewrote through `$a000`'s base: smaller steps, so the rounding is at +3 of 6.
STAGED = list(SIZ_TAB)
STAGED[vdi.VDI_SIZ_TAB_MIN_MARK_WIDTH_INDEX] = 7
STAGED[vdi.VDI_SIZ_TAB_MIN_MARK_HEIGHT_INDEX] = 6
STAGED[vdi.VDI_SIZ_TAB_MAX_MARK_HEIGHT_INDEX] = 40


@pytest.mark.parametrize("height", (5, 6, 8, 9, 40, 41))
def test_vsm_height_reads_all_three_sizes_out_of_siz_tab(height):
    result = attr.run(HEIGHT, height_pokes(height, onto=vdi.linea_pokes(SIZ_TAB=STAGED)))
    stored, scale, point = expected_marker(height, STAGED)
    assert (result.workstation("MARK_HEIGHT"), result.workstation("MARK_SCALE")) == (stored, scale)
    assert result.ptsout(2) == point


@pytest.mark.parametrize("marker", (1, 3, 6, 0, 7, -1, *WORD_EDGES))
def test_vsm_type_defaults_to_the_asterisk(marker):
    result = attr.run(TYPE, attr.call(TYPE, (marker,), fields={"MARK_INDEX": attr.STALE}))
    stored = marker - 1 if 1 <= marker <= 6 else 2
    assert result.workstation("MARK_INDEX") == stored
    assert result.intout(1) == [stored + 1]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1


@pytest.mark.parametrize("colour", (0, 1, 15, 16, -1, *WORD_EDGES))
def test_vsm_color_answers_the_index_and_stores_its_pen(colour):
    result = attr.run(COLOR, attr.call(COLOR, (colour,), fields={"MARK_COLOR": attr.STALE}))
    index = colour if 0 <= colour < 16 else 1
    assert result.intout(1) == [index]
    assert result.workstation("MARK_COLOR") == attr.rom_map_col(index)
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1


ORDERED = ((TYPE, "MARK_INDEX", (4,), ()), (COLOR, "MARK_COLOR", (6,), ()), (HEIGHT, "MARK_SCALE", (), (0, 30)))


@pytest.mark.parametrize("name, field, intin, ptsin", ORDERED)
def test_the_stores_land_in_the_roms_order(name, field, intin, ptsin):
    for _label, pokes in attr.overlap_cases(name, field, intin, ptsin):
        attr.run(name, pokes)


@pytest.mark.parametrize("field", ("MARK_HEIGHT", "MARK_SCALE"))
def test_the_height_s_point_lands_in_the_roms_order(field):
    for _label, pokes in attr.point_overlap_cases(HEIGHT, field, (0, 30)):
        attr.run(HEIGHT, pokes)


@pytest.mark.parametrize("name, field, intin, ptsin", ORDERED)
def test_a_virtual_workstation_is_the_one_written(name, field, intin, ptsin):
    result = attr.run(name, attr.call(name, intin, ptsin, virtual=True, fields={field: attr.STALE}))
    assert result.workstation(field, at=vdi.VIRTUAL_WORK_AT) != attr.STALE
    attr.assert_physical_untouched(result)


attr.register("rounded up", HEIGHT, height_pokes(17))
attr.register("capped", HEIGHT, height_pokes(200))
attr.register("in range", TYPE, attr.call(TYPE, (4,)))
attr.register("out of range", TYPE, attr.call(TYPE, (0,)))
attr.register("in range", COLOR, attr.call(COLOR, (5,)))
attr.register("out of range", COLOR, attr.call(COLOR, (-1,)))
