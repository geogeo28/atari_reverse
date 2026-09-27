"""VDI FILL attributes — vsf_interior (23), vsf_style (24), vsf_color (25), vsf_udpat (112), and the pattern
pointer both of the first two end in, st_fl_ptr ($fcc9a6): `src/vdi/attributes.c`.

    vsf_interior  contrl[4]=1; i = intin[0]; i outside 0..4 -> 0 (hollow); WS_FILL_STYLE = i; intout[0] = i; st_fl_ptr
    vsf_style     contrl[4]=1; s = intin[0]; outside 1..24 under the PATTERN interior, 1..12 under any other -> 1;
                  intout[0] = s; WS_FILL_INDEX = s-1; st_fl_ptr
    vsf_color     vsl_color's clamp and map, into WS_FILL_COLOR
    vsf_udpat     n = contrl[3]: 16 -> WS_MULTIFILL = 0, 16 * INQ_TAB[4] -> 1, anything else -> NOTHING AT ALL;
                  then n words of intin into WS_UD_PATRN
    st_fl_ptr     WS_PATPTR / WS_PATMSK from (WS_FILL_STYLE, WS_FILL_INDEX): hollow and solid a one-row
                  pattern (mask 0); pattern and hatch index one of FOUR tables — a mask word and then
                  (mask+1)-row patterns — picked by a threshold (8, 6) and rebased; user: WS_UD_PATRN, mask 15

THE ROM BUG THIS PINS. The style bound is the interior CURRENT WHEN THE STYLE IS SET, and nothing
re-checks it when the interior changes: vsf_interior(pattern), vsf_style(24), vsf_interior(hatch) —
three legal calls in a row — leaves hatch style 24, which st_fl_ptr rebases into the second hatch table
and walks 12 patterns past its end, into MAP_COL. `test_a_pattern_style_carried_into_hatch_points_past_the_table`
drives exactly that sequence, each call starting from the machine the one before it left (`case.continued`).

None of these writes the Line-A copies the dispatcher made (LINEA_PATPTR / PATMSK / MULTIFILL): every
case stages the record's pointer and mask STALE, so the copies are too, and holds them unchanged.
"""
import pytest

from harness import BASE_IMAGE, addrs, emu, make_image

import case
import vdi
import vdi_attributes as attr

INTERIOR, STYLE, COLOR, UDPAT = ("VDI_ROM_VSF_INTERIOR", "VDI_ROM_VSF_STYLE", "VDI_ROM_VSF_COLOR",
                                 "VDI_ROM_VSF_UDPAT")
WORD_EDGES = (-0x8000, 0x7FFF)
STALE_POINTER = 0x5A5A5A5A
STALE_FIELDS = {"PATPTR": STALE_POINTER, "PATMSK": attr.STALE}
HOLLOW, SOLID, PATTERN, HATCH, USER = (vdi.VDI_INTERIOR_HOLLOW, vdi.VDI_INTERIOR_SOLID, vdi.VDI_INTERIOR_PATTERN,
                                       vdi.VDI_INTERIOR_HATCH, vdi.VDI_INTERIOR_USER)


def expected_pattern(interior, index, work=vdi.VDI_PHYS_WORK):
    """(PATPTR, PATMSK) st_fl_ptr leaves, from the ROM's own table words."""
    if interior == HOLLOW:
        return vdi.VDI_PATTERN_HOLLOW, 0
    if interior == SOLID:
        return vdi.VDI_PATTERN_SOLID, 0
    if interior == USER:
        return work + vdi.field("WS", "UD_PATRN").at, 15
    lower, upper, count = ((vdi.VDI_PATTERNS_LOWER, vdi.VDI_PATTERNS_UPPER, vdi.VDI_PATTERNS_LOWER_COUNT)
                           if interior == PATTERN else
                           (vdi.VDI_HATCHES_LOWER, vdi.VDI_HATCHES_UPPER, vdi.VDI_HATCHES_LOWER_COUNT))
    table, rebased = (lower, index) if index < count else (upper, index - count)
    mask = vdi.rom_word(table)
    return table + vdi.VDI_PATTERN_TABLE_HEADER_BYTES + rebased * (mask + 1) * vdi.WORD_BYTES, mask


def pattern_of(result, at=vdi.VDI_PHYS_WORK):
    return result.workstation("PATPTR", at), result.workstation("PATMSK", at)


def assert_copies_untouched(result):
    """The dispatcher's copies still hold the STALE record they were made from."""
    assert (result.linea("PATPTR"), result.linea("PATMSK")) == (STALE_POINTER, attr.STALE)


# ---- the four tables, as the ROM lays them out --------------------------------------------------------

def test_the_four_tables_are_contiguous_and_end_at_the_hollow_row():
    """Each table's mask word, its pattern count and its rows account for every byte up to the next —
    which is what names them: 8 x 4-row patterns, 16 x 8, 6 x 8 hatches, 6 x 16."""
    layout = ((vdi.VDI_PATTERNS_UPPER, 16), (vdi.VDI_PATTERNS_LOWER, 8), (vdi.VDI_HATCHES_LOWER, 6),
              (vdi.VDI_HATCHES_UPPER, 6))
    at = vdi.VDI_PATTERNS_UPPER
    for table, patterns in layout:
        assert at == table
        at += vdi.VDI_PATTERN_TABLE_HEADER_BYTES + patterns * (vdi.rom_word(table) + 1) * vdi.WORD_BYTES
    assert at == vdi.VDI_PATTERN_HOLLOW
    assert (vdi.rom_word(vdi.VDI_PATTERN_HOLLOW), vdi.rom_word(vdi.VDI_PATTERN_SOLID)) == (0x0000, 0xFFFF)


# ---- vsf_interior -------------------------------------------------------------------------------------
STAGED_INDEX = 3            # a style every table has, so each interior's pointer is a distinct row


@pytest.mark.parametrize("interior", (0, 1, 2, 3, 4, 5, -1, *WORD_EDGES))
def test_vsf_interior_clamps_to_hollow_and_repoints_the_pattern(interior):
    pokes = attr.call(INTERIOR, (interior,), fields={"FILL_STYLE": attr.STALE, "FILL_INDEX": STAGED_INDEX,
                                                     **STALE_FIELDS})
    result = attr.run(INTERIOR, pokes)
    kept = interior if 0 <= interior <= 4 else HOLLOW
    assert result.workstation("FILL_STYLE") == kept
    assert result.intout(1) == [kept]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1
    assert pattern_of(result) == expected_pattern(kept, STAGED_INDEX)
    assert_copies_untouched(result)


# ---- vsf_style ----------------------------------------------------------------------------------------
STYLES = ([(PATTERN, style) for style in (1, 8, 9, 24, 25, 0, -1, *WORD_EDGES)]
          + [(HATCH, style) for style in (1, 6, 7, 12, 13)]
          + [(HOLLOW, 13), (SOLID, 12), (USER, 3), (USER, 25)])


@pytest.mark.parametrize("interior, style", STYLES)
def test_vsf_style_bounds_by_the_current_interior(interior, style):
    pokes = attr.call(STYLE, (style,), fields={"FILL_STYLE": interior, "FILL_INDEX": attr.STALE, **STALE_FIELDS})
    result = attr.run(STYLE, pokes)
    count = 24 if interior == PATTERN else 12
    kept = style if 1 <= style <= count else 1
    assert result.intout(1) == [kept]
    assert result.workstation("FILL_INDEX") == kept - 1
    assert pattern_of(result) == expected_pattern(interior, kept - 1)
    assert_copies_untouched(result)


# ---- st_fl_ptr, entered directly -----------------------------------------------------------------------

def st_fl_ptr_pokes(interior, index, virtual=False):
    return attr.workstation(virtual=virtual, FILL_STYLE=interior, FILL_INDEX=index, **STALE_FIELDS)


def run_st_fl_ptr(pokes, **kwargs):
    """st_fl_ptr entered by `jsr`, as vsf_interior and vsf_style call it: no arguments, no result."""
    def glue(lib, buf):
        lib.vdi_st_fl_ptr.restype = None
        return lib.vdi_st_fl_ptr(buf)

    info = case.run(addrs.VDI_ROM_ST_FL_PTR, {"_pokes": pokes}, glue, width=case.NO_RESULT, **kwargs)
    return vdi.Result(info, pokes)


# Every table's first and last row, both thresholds from each side, and the user array.
POINTERS = ([(PATTERN, index) for index in (0, 7, 8, 23)] + [(HATCH, index) for index in (0, 5, 6, 11)]
            + [(HOLLOW, 0), (SOLID, 0), (USER, 0)])


@pytest.mark.parametrize("interior, index", POINTERS)
def test_st_fl_ptr_points_at_the_row_the_tables_give(interior, index):
    assert pattern_of(run_st_fl_ptr(st_fl_ptr_pokes(interior, index))) == expected_pattern(interior, index)


def test_st_fl_ptr_points_the_user_interior_at_the_current_workstation_s_own_array():
    result = run_st_fl_ptr(st_fl_ptr_pokes(USER, 0, virtual=True))
    assert pattern_of(result, vdi.VIRTUAL_WORK_AT) == expected_pattern(USER, 0, vdi.VIRTUAL_WORK_AT)


def test_a_pattern_style_carried_into_hatch_points_past_the_table():
    """vsf_interior(pattern), vsf_style(24), vsf_interior(hatch): hatch index 23 is rebased to 17 in a
    six-pattern table, and the pointer lands 17 x 16 rows in — on MAP_COL."""
    first = attr.run(INTERIOR, attr.call(INTERIOR, (PATTERN,), fields=STALE_FIELDS))
    second = attr.run(STYLE, merge_call(first, STYLE, (24,)))
    third = attr.run(INTERIOR, merge_call(second, INTERIOR, (HATCH,)))
    assert third.workstation("FILL_INDEX") == 23
    assert pattern_of(third) == (vdi.VDI_MAP_COL, vdi.rom_word(vdi.VDI_HATCHES_UPPER))


def merge_call(previous, name, intin):
    """The next call's arrays over the machine `previous` ended in. The dispatcher would re-copy the
    record into Line-A between the calls; no setter reads a copy, so the carried machine is the same
    to them."""
    arrays = vdi.function_pokes(name, intin, workstation_pokes={})
    return case.merge_pokes(case.continued(previous), arrays)


def test_an_interior_past_the_switch_stores_whatever_a5_held():
    """THE ONE ARM NOTHING REACHES, pinned on the ORACLE alone: the switch's `bhi` past 4 skips every
    arm and lands on the stores with A5 never loaded — PATPTR becomes the CALLER's A5 and PATMSK the
    0 D6 was cleared to. vsf_interior and the workstation's initialisation both clamp the interior
    first, so no call reaches it; the reconstruction HALTS there rather than invent a register, and
    this case is what says the halt stands for a real, unreachable arm."""
    callers_a5 = 0x00ABCDEF
    image = make_image(st_fl_ptr_pokes(5, 0))
    final, _writes, _regs = emu.run(image, addrs.VDI_ROM_ST_FL_PTR, {"a5": callers_a5})
    work = vdi.VDI_PHYS_WORK
    assert (vdi.read_field(final, "WS", "PATPTR", work), vdi.read_field(final, "WS", "PATMSK", work)) == (callers_a5, 0)


# ---- vsf_color ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("colour", (0, 1, 15, 16, -1, *WORD_EDGES))
def test_vsf_color_answers_the_index_and_stores_its_pen(colour):
    result = attr.run(COLOR, attr.call(COLOR, (colour,), fields={"FILL_COLOR": attr.STALE}))
    index = colour if 0 <= colour < 16 else 1
    assert result.intout(1) == [index]
    assert result.workstation("FILL_COLOR") == attr.rom_map_col(index)
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1


# ---- vsf_udpat ----------------------------------------------------------------------------------------
UD_ROWS = 16
SNAPSHOT_PLANES = vdi.linea(BASE_IMAGE, "INQ_TAB")[vdi.VDI_INQ_TAB_PLANES_INDEX]
STALE_PATTERN = [attr.STALE] * (UD_ROWS * 4)


def udpat_pokes(words, planes=None, virtual=False):
    """`words` pattern words (a ramp, so a row stored one place off is a wrong value), over a record
    whose MULTIFILL and pattern are STALE; `planes` restages INQ_TAB[4]."""
    onto = None
    if planes is not None:
        table = vdi.linea(BASE_IMAGE, "INQ_TAB")
        table[vdi.VDI_INQ_TAB_PLANES_INDEX] = planes
        onto = vdi.linea_pokes(INQ_TAB=table)
    ramp = tuple(0x1100 + row for row in range(words))
    return ramp, attr.call(UDPAT, ramp, virtual=virtual, onto=onto,
                           fields={"MULTIFILL": attr.STALE, "UD_PATRN": STALE_PATTERN, **STALE_FIELDS})


@pytest.mark.parametrize("words, planes, multifill", ((16, None, 0), (64, None, 1), (32, 2, 1), (16, 1, 0)))
def test_vsf_udpat_takes_one_plane_or_every_plane(words, planes, multifill):
    ramp, pokes = udpat_pokes(words, planes)
    result = attr.run(UDPAT, pokes)
    assert SNAPSHOT_PLANES == 4
    assert result.workstation("MULTIFILL") == multifill
    assert result.workstation("UD_PATRN") == list(ramp) + STALE_PATTERN[words:]
    assert pattern_of(result) == (STALE_POINTER, attr.STALE), "the pointer is not re-aimed"
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 0


@pytest.mark.parametrize("words, planes", ((32, None), (0, None), (48, None), (15, None), (64, 2)))
def test_vsf_udpat_refuses_any_other_count_and_stores_nothing(words, planes):
    _ramp, pokes = udpat_pokes(words, planes)
    result = attr.run(UDPAT, pokes)
    assert result.workstation("MULTIFILL") == attr.STALE
    assert result.workstation("UD_PATRN") == STALE_PATTERN
    assert not attr.writes_outside_the_stack(result), "a refused count writes nothing at all"


# ---- store order, and the virtual workstation ---------------------------------------------------------
ORDERED = ((INTERIOR, "FILL_STYLE", (2,)), (STYLE, "FILL_INDEX", (5,)), (COLOR, "FILL_COLOR", (7,)))


@pytest.mark.parametrize("name, field, intin", ORDERED)
def test_the_stores_land_in_the_roms_order(name, field, intin):
    for _label, pokes in attr.overlap_cases(name, field, intin):
        attr.run(name, pokes)


@pytest.mark.parametrize("name, field, intin", ORDERED + ((UDPAT, "MULTIFILL", tuple(range(16))),))
def test_a_virtual_workstation_is_the_one_written(name, field, intin):
    result = attr.run(name, attr.call(name, intin, virtual=True, fields={field: attr.STALE, **STALE_FIELDS}))
    attr.assert_physical_untouched(result)


# ---- Tier 3 ---------------------------------------------------------------------------------------------
attr.register("hatch, upper table", INTERIOR, attr.call(INTERIOR, (HATCH,), fields={"FILL_INDEX": 8}))
attr.register("out of range", INTERIOR, attr.call(INTERIOR, (9,)))
attr.register("pattern, upper table", STYLE, attr.call(STYLE, (20,), fields={"FILL_STYLE": PATTERN}))
attr.register("out of range", STYLE, attr.call(STYLE, (13,), fields={"FILL_STYLE": HATCH}))
attr.register("in range", COLOR, attr.call(COLOR, (5,)))
attr.register("out of range", COLOR, attr.call(COLOR, (16,)))
attr.register("every plane", UDPAT, udpat_pokes(64)[1])
attr.register("one plane", UDPAT, udpat_pokes(16)[1])
attr.register("refused", UDPAT, udpat_pokes(32)[1])
vdi.register("vdi_st_fl_ptr, pattern, upper table", addrs.VDI_ROM_ST_FL_PTR, st_fl_ptr_pokes(PATTERN, 20))
vdi.register("vdi_st_fl_ptr, user", addrs.VDI_ROM_ST_FL_PTR, st_fl_ptr_pokes(USER, 0))
