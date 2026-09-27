"""VDI TEXT attributes — vst_effects (106), vst_alignment (39), vst_rotation (13), vst_color (22):
`src/vdi/attributes.c`.

    vst_effects    e = intin[0] & INQ_TAB[2]; WS_STYLE = e; intout[0] = e; contrl[4]=1
    vst_alignment  h = intin[0] outside 0..2 -> 0: intout[0], WS_H_ALIGN; then v = intin[1] outside 0..5 -> 0:
                   intout[1], WS_V_ALIGN; contrl[4]=2
    vst_rotation   a = ((intin[0] + 450) / 900) * 900 — `add.w`, `divs.w`, `muls.w`; WS_CHUP = a; intout[0] = a;
                   contrl[4]=1
    vst_color      vsl_color's clamp and map, into WS_TEXT_COLOR

vst_rotation has no range check and word arithmetic all the way: an angle past 32,317 wraps NEGATIVE in
the `add.w` and comes back as -32,400, and a negative angle rounds towards zero rather than down
(`divs.w` truncates). Both are driven. None of the four writes the dispatcher's Line-A copies
(LINEA_STYLE, LINEA_CHUP, the two alignment words at VDI_TEXT_H/V_ALIGN): every case stages the record
STALE, so the copies are too, and holds them unchanged.
"""
import pytest

from harness import BASE_IMAGE

import vdi
import vdi_attributes as attr

EFFECTS, ALIGNMENT, ROTATION, COLOR = ("VDI_ROM_VST_EFFECTS", "VDI_ROM_VST_ALIGNMENT", "VDI_ROM_VST_ROTATION",
                                       "VDI_ROM_VST_COLOR")
WORD_EDGES = (-0x8000, 0x7FFF)
SNAPSHOT_EFFECTS = vdi.linea(BASE_IMAGE, "INQ_TAB")[vdi.VDI_INQ_TAB_EFFECTS_INDEX]


def effects_table(mask):
    table = vdi.linea(BASE_IMAGE, "INQ_TAB")
    table[vdi.VDI_INQ_TAB_EFFECTS_INDEX] = mask
    return vdi.linea_pokes(INQ_TAB=table)


@pytest.mark.parametrize("mask", (None, 0x0005))
@pytest.mark.parametrize("effects", (0x0000, 0x001F, 0x0020, 0x8001, 0xFFFF))
def test_vst_effects_keeps_only_the_effects_the_device_has(effects, mask):
    onto = None if mask is None else effects_table(mask)
    result = attr.run(EFFECTS, attr.call(EFFECTS, (effects,), onto=onto, fields={"STYLE": attr.STALE}))
    kept = effects & (SNAPSHOT_EFFECTS if mask is None else mask)
    assert result.workstation("STYLE") == kept
    assert result.intout(1) == [kept]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1
    assert result.linea("STYLE") == attr.STALE


@pytest.mark.parametrize("horizontal, vertical", ((0, 0), (2, 5), (3, 6), (-1, -1), (1, 3), WORD_EDGES))
def test_vst_alignment_clamps_each_half_to_zero(horizontal, vertical):
    pokes = attr.call(ALIGNMENT, (horizontal, vertical), fields={"H_ALIGN": attr.STALE, "V_ALIGN": attr.STALE})
    result = attr.run(ALIGNMENT, pokes)
    kept = [horizontal if 0 <= horizontal <= 2 else 0, vertical if 0 <= vertical <= 5 else 0]
    assert [result.workstation("H_ALIGN"), result.workstation("V_ALIGN")] == kept
    assert result.intout(2) == kept
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 2
    assert [result.word(vdi.VDI_TEXT_H_ALIGN), result.word(vdi.VDI_TEXT_V_ALIGN)] == [attr.STALE] * 2


def rounded(angle):
    """The ROM's word arithmetic: a wrapping add, a truncating divide."""
    shifted = (angle + 450 + 0x8000) % 0x10000 - 0x8000
    quotient = abs(shifted) // 900 * (1 if shifted >= 0 else -1)
    return (quotient * 900) & 0xFFFF


@pytest.mark.parametrize("angle", (0, 449, 450, 451, 899, 900, 1349, 1350, 2700, 3600, 3700, -449, -450, -451,
                                   -1350, -1351, 32317, 32318, *WORD_EDGES))
def test_vst_rotation_rounds_to_a_quarter_turn_in_word_arithmetic(angle):
    result = attr.run(ROTATION, attr.call(ROTATION, (angle,), fields={"CHUP": attr.STALE}))
    assert result.workstation("CHUP") == rounded(angle)
    assert result.intout(1) == [rounded(angle)]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1
    assert result.linea("CHUP") == attr.STALE


def test_the_wrap_is_the_rom_s():
    """Pinned in figures rather than through `rounded`: 32,318 + 450 wraps to -32,768."""
    assert rounded(32318) == -32400 & 0xFFFF and rounded(32317) == 32400 and rounded(-450) == 0


@pytest.mark.parametrize("colour", (0, 1, 15, 16, -1, *WORD_EDGES))
def test_vst_color_answers_the_index_and_stores_its_pen(colour):
    result = attr.run(COLOR, attr.call(COLOR, (colour,), fields={"TEXT_COLOR": attr.STALE}))
    index = colour if 0 <= colour < 16 else 1
    assert result.intout(1) == [index]
    assert result.workstation("TEXT_COLOR") == attr.rom_map_col(index)
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1


ORDERED = ((EFFECTS, "STYLE", (0x1F,)), (ALIGNMENT, "H_ALIGN", (1, 4)), (ALIGNMENT, "V_ALIGN", (2, 3)),
           (ROTATION, "CHUP", (1800,)), (COLOR, "TEXT_COLOR", (9,)))


@pytest.mark.parametrize("name, field, intin", ORDERED)
def test_the_stores_land_in_the_roms_order(name, field, intin):
    for _label, pokes in attr.overlap_cases(name, field, intin):
        attr.run(name, pokes)


@pytest.mark.parametrize("name, field, intin", ORDERED)
def test_a_virtual_workstation_is_the_one_written(name, field, intin):
    result = attr.run(name, attr.call(name, intin, virtual=True, fields={field: attr.STALE}))
    assert result.workstation(field, at=vdi.VIRTUAL_WORK_AT) != attr.STALE
    attr.assert_physical_untouched(result)


attr.register("masked", EFFECTS, attr.call(EFFECTS, (0xFFFF,)))
attr.register("in range", ALIGNMENT, attr.call(ALIGNMENT, (1, 3)))
attr.register("out of range", ALIGNMENT, attr.call(ALIGNMENT, (3, 6)))
attr.register("rounded up", ROTATION, attr.call(ROTATION, (1350,)))
attr.register("negative", ROTATION, attr.call(ROTATION, (-1351,)))
attr.register("in range", COLOR, attr.call(COLOR, (5,)))
attr.register("out of range", COLOR, attr.call(COLOR, (16,)))
