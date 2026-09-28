"""The TEXT LAYER's size and face setters — `src/vdi/text.c`:

    make_header ($fce116, their Alcyon call)   vst_height (12, $fcdfd0)   vst_point (107, $fce26c)
    vst_font (21, $fce47c)

THE RING THEY WALK is the snapshot's, with a GDOS set behind it in the loaded slot (`LOADED`): the system face
in THREE slots (the ROM 6x6; the RAM 8x8 -> 8x16; a loaded 18-point), face 2 at four sizes, face 5, and face 2
AGAIN behind face 5, where no walk reaches it. Every header is a copy of a ROM one with its size changed.

WHAT A SETTER ANSWERS IS SCALED WHEN THE FIT IS NOT EXACT: the scratch header (`make_header`) built over the
chosen font by the DDA — which every case here therefore reaches through the real clc_dda and act_siz — and
made the current font. So the cases read the RECORD and the scratch header back as well as the answers.

NO CASE POISONS (`vdi.READS_A_POINTER_IT_WRITES`): each routine writes LINEA_CUR_FONT / WS_CUR_FONT and READS
them again (vst_font its own array pointers), so the attribution pass's inverted pointer takes make_header's
copy_name into the I/O page ($ff8089, read at $fce116+40). What stands in is staging: the scratch header, the
arrays and the scale fields start stale.
"""
import pytest

from harness import addrs

import case
import vdi
import vdi_helpers
import vdi_text_c as text
from vdi_text import font_field
from vdi_text_c import chain_pokes, header_at

WORD = vdi.WORD_BYTES
DOUBLE = vdi_helpers.VDI_DDA_DOUBLE
SCALE_UP = vdi_helpers.VDI_SCALE_UP
SYSTEM = vdi.FONT_SYSTEM_FACE
SCRATCH_HEAD = vdi.WS_SCRATCH_HEAD

# ---- the ring's loaded chain -------------------------------------------------------------------------------
LOADED = (("8x16", dict(ID=SYSTEM, POINT=18, TOP=20)),
          ("8x8", dict(ID=2, POINT=8, TOP=6)),
          ("8x8", dict(ID=2, POINT=10, TOP=9)),
          ("8x16", dict(ID=2, POINT=14, TOP=13)),
          ("8x16", dict(ID=2, POINT=20, TOP=19)),
          ("8x8", dict(ID=5, POINT=10, TOP=9)),
          ("8x16", dict(ID=2, POINT=36, TOP=33)))
CHAIN = chain_pokes(LOADED)
HEADERS = CHAIN[1]
SYSTEM_18, SWISS_8, SWISS_10, SWISS_14, SWISS_20, DUTCH_10, SWISS_36 = HEADERS
# A font of a face the ring does not hold — as WS_CUR_FONT is left naming one after vst_unload_fonts.
UNLOADED = header_at(len(LOADED))
UNLOADED_POKES = text.rom_header_pokes(UNLOADED, "8x8", ID=9, POINT=12, TOP=9)


def machine(current, *, virtual=None, onto=None, **record):
    """The ring above, dispatched, with `current` the workstation's font, WS_SCALED set and its scratch header
    stale — what an earlier scaled size leaves."""
    scratch = {}
    fonts = vdi.merge_pokes(UNLOADED_POKES, onto)
    work = text.loaded_machine(CHAIN, virtual=virtual, onto=fonts, **{"CUR_FONT": current, "SCALED": 1, **record})
    at = text.work_at(work)
    scratch[at + SCRATCH_HEAD] = bytes([vdi.FILL]) * vdi.FONT_HEADER_BYTES
    return vdi.merge_pokes(work, scratch, vdi.linea_pokes(DDA_INC=vdi.STALE_WORD))


def expected_size_answer(image, font):
    top = vdi.read_field(image, "FONT", "TOP", font)
    return [vdi.read_field(image, "FONT", "MAX_CHAR_WIDTH", font), top,
            vdi.read_field(image, "FONT", "MAX_CELL_WIDTH", font),
            (top + vdi.read_field(image, "FONT", "BOTTOM", font) + 1) & 0xFFFF]


# ==== make_header ======================================================================================
def header_machine(font, increment, direction, *, virtual=None):
    work = machine(font, virtual=virtual)
    return vdi.merge_pokes(work, vdi.linea_pokes(DDA_INC=increment, T_SCLSTS=direction))


def make_header(pokes):
    return vdi_helpers.run_call("VDI_ROM_MAKE_HEADER", {}, (), pokes, **vdi.READS_A_POINTER_IT_WRITES)


HEADER_SOURCES = (vdi.FONT_ROM_6X6, vdi.FONT_RAM_8X8, vdi.FONT_ROM_8X16, SWISS_14)
DDAS = ((DOUBLE, SCALE_UP), (0x8000, SCALE_UP), (0x2000, SCALE_UP), (0xC000, vdi_helpers.VDI_SCALE_DOWN),
        (0x0001, vdi_helpers.VDI_SCALE_DOWN))


@pytest.mark.parametrize("increment,direction", DDAS)
@pytest.mark.parametrize("font", HEADER_SOURCES)
def test_make_header_scales_the_current_font_into_the_scratch_header(font, increment, direction):
    result = make_header(header_machine(font, increment, direction))
    scratch = vdi.VDI_PHYS_WORK + SCRATCH_HEAD
    assert result.linea("CUR_FONT") == scratch
    assert (result.workstation("CUR_FONT"), result.workstation("SCALED")) == (scratch, 1)
    image = result.final
    assert vdi.read_field(image, "FONT", "POINT", scratch) == (vdi.read_field(image, "FONT", "POINT", font) * 2) & 0xFFFF
    assert vdi.read_field(image, "FONT", "NAME", scratch) == vdi.read_field(image, "FONT", "NAME", font)
    assert vdi.read_field(image, "FONT", "NEXT", scratch) == vdi.FILL * 0x01010101     # not copied


def test_make_header_doubles_the_top_three_plus_one():
    """Under the doubling marker the top, ascent and half are `2n + 1`; the descent and the rest are
    act_siz's plain doubling."""
    result = make_header(header_machine(vdi.FONT_ROM_8X16, DOUBLE, SCALE_UP))
    scratch = vdi.VDI_PHYS_WORK + SCRATCH_HEAD
    field = lambda name: vdi.read_field(result.final, "FONT", name, scratch)                   # noqa: E731
    assert (field("TOP"), field("ASCENT"), field("HALF")) == tuple(2 * font_field("8x16", name) + 1
                                                                   for name in ("TOP", "ASCENT", "HALF"))
    assert (field("DESCENT"), field("BOTTOM")) == (2 * font_field("8x16", "DESCENT"), 2 * font_field("8x16", "BOTTOM"))


def test_make_header_on_a_virtual_workstation():
    result = make_header(header_machine(SWISS_10, 0x8000, SCALE_UP, virtual=6))
    assert result.workstation("CUR_FONT", vdi.VIRTUAL_WORK_AT) == vdi.VIRTUAL_WORK_AT + SCRATCH_HEAD
    assert result.workstation("SCALED") == vdi.workstation(vdi.BASE_IMAGE, "SCALED")


# ==== vst_height =======================================================================================
def height_call(current, requested, **record):
    work = machine(current, **record)
    return vdi.function_pokes("VDI_ROM_VST_HEIGHT", ptsin=(vdi.STALE_WORD, requested), workstation_pokes=work)


def vst_height(pokes):
    return vdi.run_function("VDI_ROM_VST_HEIGHT", pokes, **vdi.READS_A_POINTER_IT_WRITES)


# (current font, requested height, the font chosen, scaled?)
HEIGHTS = (
    (SWISS_10, 6, SWISS_8, False),          # the smallest, exactly
    (SWISS_10, 3, SWISS_8, True),           # below every size: the first, scaled DOWN
    (SWISS_10, 0, SWISS_8, True),           # clc_dda takes a request of 0 as 1
    (SWISS_10, 9, SWISS_10, False),
    (SWISS_10, 11, SWISS_10, True),         # up by a fraction
    (SWISS_8, 16, SWISS_14, True),
    (SWISS_8, 19, SWISS_20, False),
    (SWISS_8, 30, SWISS_20, True),          # 30 - 19 < 19: a fraction
    (SWISS_8, 40, SWISS_20, True),          # 40 - 19 >= 19: the doubling marker — and never face 2's 36
    (SWISS_8, 0xFFFB, SWISS_20, True),      # -5: UNSIGNED against the tops, the largest; clc_dda overflows
    (DUTCH_10, 9, DUTCH_10, False),
    (DUTCH_10, 20, DUTCH_10, True),
    (vdi.FONT_ROM_6X6, 4, vdi.FONT_ROM_6X6, False),
    (vdi.FONT_ROM_6X6, 13, vdi.FONT_RAM_8X16, False),     # the system face across its first two slots...
    (vdi.FONT_ROM_6X6, 20, SYSTEM_18, False),             # ...and on into the loaded one
    (vdi.FONT_RAM_8X8, 15, vdi.FONT_RAM_8X16, True),      # the loaded 20 does not fit: that slot skipped
    (SYSTEM_18, 5, vdi.FONT_ROM_6X6, True),               # a face's FIRST font is the 6x6, whatever the current
)


@pytest.mark.parametrize("current,requested,chosen,scaled", HEIGHTS)
def test_vst_height_takes_the_tallest_size_that_fits(current, requested, chosen, scaled):
    result = vst_height(height_call(current, requested))
    image = result.final
    answered = vdi.VDI_PHYS_WORK + SCRATCH_HEAD if scaled else chosen
    assert result.linea("CUR_FONT") == answered
    assert (result.workstation("CUR_FONT"), result.workstation("SCALED")) == (answered, int(scaled))
    assert result.workstation("PTS_MODE") == 0
    if scaled:
        assert vdi.read_field(image, "FONT", "ID", answered) == vdi.read_field(image, "FONT", "ID", chosen)
        assert result.workstation("DDA_INC") == result.linea("DDA_INC")
        assert result.workstation("T_SCLSTS") == result.linea("T_SCLSTS")
    assert result.ptsout(4) == expected_size_answer(image, answered)
    assert result.contrl(vdi.CONTRL_N_PTSOUT) == 2
    assert result.word(vdi.VDI_RESULT) == vdi.VDI_RESULT_SET


def test_vst_height_in_normalised_coordinates_measures_from_the_bottom():
    """XFM_MODE 0: the height asked is DEV_TAB[1] + 1 - ptsin[1] — here 13, the RAM 8x16 exactly."""
    last_row = vdi.linea(vdi.BASE_IMAGE, "DEV_TAB")[vdi.VDI_DEV_TAB_MAX_Y_INDEX]
    result = vst_height(height_call(vdi.FONT_ROM_6X6, last_row + 1 - 13, XFM_MODE=0))
    assert result.linea("CUR_FONT") == vdi.FONT_RAM_8X16


def test_vst_height_after_the_fonts_are_unloaded_scales_the_header_at_address_0():
    """THE CURRENT FONT'S FACE NOT IN THE RING: the walk finds nothing, and its 0 is taken as the font — the
    vector table read as a header, its top the high word of the Line-A vector — scaled, made current, and
    answered from."""
    result = vst_height(height_call(UNLOADED, 13))
    scratch = vdi.VDI_PHYS_WORK + SCRATCH_HEAD
    assert result.linea("CUR_FONT") == scratch
    assert vdi.read_field(result.final, "FONT", "ID", scratch) == vdi.rom_word(vdi.FONT_ID)
    assert result.ptsout(4) == expected_size_answer(result.final, scratch)


def chain_through_the_bus_call():
    """vst_height over the unloaded font given the face of the "font" at address 0 — a walk that puts a
    pointer's non-zero HIGH BYTE on the bus."""
    work = machine(UNLOADED, onto=text.rom_header_pokes(UNLOADED, "8x8", ID=vdi.rom_word(vdi.FONT_ID)))
    return vdi.function_pokes("VDI_ROM_VST_HEIGHT", ptsin=(0, 0xFFFF), workstation_pokes=work)


def test_vst_height_follows_a_chain_on_from_address_0_through_the_24_bit_bus():
    """...and when the unloaded font's id is the word at address 0, that "font" matches its own face: the
    walk takes it and follows its FONT_NEXT — the vector longword at 84, whose high byte is not zero — into
    the ROM, as the 68000's 24-bit bus reaches it."""
    assert vdi.case.long_in(vdi.BASE_IMAGE, vdi.FONT_NEXT) >> 24, "the longword at 84 has a high byte"
    result = vst_height(chain_through_the_bus_call())
    assert result.linea("CUR_FONT") == vdi.VDI_PHYS_WORK + SCRATCH_HEAD


def test_vst_height_on_a_virtual_workstation():
    result = vst_height(height_call(SWISS_10, 11, virtual=6))
    assert result.workstation("CUR_FONT", vdi.VIRTUAL_WORK_AT) == vdi.VIRTUAL_WORK_AT + SCRATCH_HEAD
    assert result.workstation("CUR_FONT") == vdi.workstation(vdi.BASE_IMAGE, "CUR_FONT")     # the physical one untouched


def test_vst_height_clears_pts_mode_before_it_reads_ptsin():
    """ptsin[1] laid on WS_PTS_MODE (a stale 7): cleared first, so the height asked is 0 — the smallest."""
    pokes = vdi.merge_pokes(height_call(SWISS_10, 13, PTS_MODE=7),
                            vdi.linea_pokes(PTSIN=vdi.VDI_PHYS_WORK + vdi.WS_PTS_MODE - WORD))
    result = vst_height(pokes)
    assert result.linea("CUR_FONT") == vdi.VDI_PHYS_WORK + SCRATCH_HEAD
    assert vdi.read_field(result.final, "FONT", "ID", result.linea("CUR_FONT")) == 2


def test_vst_height_writes_contrl_2_before_the_points():
    pokes = vdi.merge_pokes(height_call(SWISS_10, 9), vdi.linea_pokes(PTSOUT=vdi.CONTRL_AT + vdi.CONTRL_N_PTSOUT))
    assert vst_height(pokes).contrl(vdi.CONTRL_N_PTSOUT) == vdi.read_field(vdi.make_image(CHAIN[0]), "FONT",
                                                                           "MAX_CHAR_WIDTH", SWISS_10)


def test_vst_height_reads_the_top_after_the_first_point():
    """ptsout laid on the chosen font's TOP: the width stored there first is the top then answered."""
    pokes = vdi.merge_pokes(height_call(SWISS_10, 9), vdi.linea_pokes(PTSOUT=SWISS_10 + vdi.FONT_TOP))
    result = vst_height(pokes)
    width = vdi.read_field(vdi.make_image(CHAIN[0]), "FONT", "MAX_CHAR_WIDTH", SWISS_10)
    assert result.words(SWISS_10 + vdi.FONT_TOP, 2) == [width, width]


# ==== vst_point ========================================================================================
def point_call(current, requested, **record):
    work = machine(current, **record)
    return vdi.function_pokes("VDI_ROM_VST_POINT", intin=(requested,), workstation_pokes=work)


def vst_point(pokes):
    return vdi.run_function("VDI_ROM_VST_POINT", pokes, **vdi.READS_A_POINTER_IT_WRITES)


# (current font, requested points, the font answered from, its point size, scaled by two?)
POINTS = (
    (SWISS_10, 8, SWISS_8, 8, False),
    (SWISS_10, 5, SWISS_8, 8, False),         # below every size: the first, unscaled (16 > 5)
    (SWISS_10, 0xFFFD, SWISS_8, 8, False),    # -3, SIGNED: below every size
    (SWISS_10, 12, SWISS_10, 10, False),      # the doubled 8 is 16 > 12
    (SWISS_10, 14, SWISS_14, 14, False),
    (SWISS_10, 17, SWISS_8, 16, True),        # 16 > 14 and <= 17: the 8 doubled
    (SWISS_10, 28, SWISS_14, 28, True),       # the 14 doubled, exactly
    (SWISS_10, 50, SWISS_20, 40, True),       # the 20 doubled
    (SWISS_10, 0x7FFF, SWISS_20, 40, True),
    (DUTCH_10, 25, DUTCH_10, 20, True),
    (DUTCH_10, 19, DUTCH_10, 10, False),      # 20 > 19
    (vdi.FONT_ROM_6X6, 16, vdi.FONT_ROM_6X6, 16, True),   # THE SNAPSHOT'S OWN FACE: the 6x6 doubled beats the 10
    (vdi.FONT_ROM_6X6, 18, SYSTEM_18, 18, False),
    (vdi.FONT_ROM_6X6, 19, SYSTEM_18, 18, False),         # 16 is not above 18
    (vdi.FONT_ROM_6X6, 36, SYSTEM_18, 36, True),
)


@pytest.mark.parametrize("current,requested,source,point,scaled", POINTS)
def test_vst_point_takes_the_largest_size_or_a_doubled_one(current, requested, source, point, scaled):
    result = vst_point(point_call(current, requested))
    image = result.final
    answered = vdi.VDI_PHYS_WORK + SCRATCH_HEAD if scaled else source
    assert result.linea("CUR_FONT") == answered
    assert (result.workstation("CUR_FONT"), result.workstation("SCALED")) == (answered, int(scaled))
    assert result.workstation("PTS_MODE") == 1
    if scaled:
        assert (result.workstation("DDA_INC"), result.linea("DDA_INC"), result.workstation("T_SCLSTS")) == (
            DOUBLE, DOUBLE, SCALE_UP)
        assert vdi.read_field(image, "FONT", "ID", answered) == vdi.read_field(image, "FONT", "ID", source)
    assert result.intout(1) == [point]
    assert result.ptsout(4) == expected_size_answer(image, answered)
    assert (result.contrl(vdi.CONTRL_N_PTSOUT), result.contrl(vdi.CONTRL_N_INTOUT)) == (2, 1)
    assert result.word(vdi.VDI_RESULT) == vdi.VDI_RESULT_SET


def test_vst_point_after_the_fonts_are_unloaded_answers_from_address_0():
    result = vst_point(point_call(UNLOADED, 12))
    assert result.linea("CUR_FONT") == 0
    assert result.intout(1) == [vdi.rom_word(vdi.FONT_POINT)]


def test_vst_point_sets_pts_mode_before_it_reads_intin():
    """intin[0] laid on WS_PTS_MODE: set to 1 first, so one point is asked — the smallest size."""
    pokes = vdi.merge_pokes(point_call(SWISS_10, 20), vdi.linea_pokes(INTIN=vdi.VDI_PHYS_WORK + vdi.WS_PTS_MODE))
    assert vst_point(pokes).intout(1) == [8]


def test_vst_point_writes_its_counts_before_the_answer():
    assert vst_point(vdi.intout_over(point_call(SWISS_10, 17))).contrl(vdi.CONTRL_N_INTOUT) == 16


def test_vst_point_on_a_virtual_workstation():
    result = vst_point(point_call(SWISS_10, 28, virtual=6))
    assert result.workstation("CUR_FONT", vdi.VIRTUAL_WORK_AT) == vdi.VIRTUAL_WORK_AT + SCRATCH_HEAD
    assert result.workstation("DDA_INC", vdi.VIRTUAL_WORK_AT) == DOUBLE


# ==== vst_font =========================================================================================
def font_call(current, face, pts_mode, **record):
    work = machine(current, PTS_MODE=pts_mode, **record)
    return vdi.function_pokes("VDI_ROM_VST_FONT", intin=(face,), workstation_pokes=work)


def vst_font(pokes):
    return vdi.run_function("VDI_ROM_VST_FONT", pokes, **vdi.READS_A_POINTER_IT_WRITES)


# (current font, face, WS_PTS_MODE, the font finally current, scaled?)
FACES = (
    (SWISS_14, 5, 0, DUTCH_10, True),                  # vst_height(13) of face 5: its 9 scaled up
    (SWISS_14, 5, 1, DUTCH_10, False),                 # vst_point(14) of face 5: the 10, as 20 > 14
    (SWISS_14, SYSTEM, 0, vdi.FONT_RAM_8X16, False),   # vst_height(13): the 8x16 exactly
    (SWISS_10, SYSTEM, 1, vdi.FONT_RAM_8X16, False),   # vst_point(10): the 8x16 exactly
    (SWISS_14, 7, 0, vdi.FONT_RAM_8X16, False),        # no face 7: the ROM 6x6, then as face 1
    (vdi.FONT_ROM_6X6, 2, 0, SWISS_8, True),           # vst_height(4): the smallest scaled down
    (vdi.FONT_ROM_6X6, 2, 1, SWISS_8, False),          # vst_point(8)
    (SWISS_36, 2, 1, SWISS_20, True),                  # vst_point(36): the 20 doubled — 36 is never reached
)


@pytest.mark.parametrize("current,face,pts_mode,chosen,scaled", FACES)
def test_vst_font_asks_the_new_face_for_the_old_size(current, face, pts_mode, chosen, scaled):
    pokes = font_call(current, face, pts_mode)
    result = vst_font(pokes)
    answered = vdi.VDI_PHYS_WORK + SCRATCH_HEAD if scaled else chosen
    assert result.linea("CUR_FONT") == answered
    assert result.workstation("CUR_FONT") == answered
    assert result.intout(1) == [vdi.read_field(result.final, "FONT", "ID", chosen)]
    assert (result.contrl(vdi.CONTRL_N_PTSOUT), result.contrl(vdi.CONTRL_N_INTOUT)) == (0, 1)
    assert [result.linea(name) for name in ("INTIN", "PTSIN", "PTSOUT")] == [vdi.INTIN_AT, vdi.VDI_PTSIN_COPY,
                                                                             vdi.PTSOUT_AT]
    assert result.ptsout(4) == [vdi.FILL * 0x101] * 4          # the setter answered into vst_font's frame


def test_vst_font_over_a_scaled_current_font():
    """Chained: vst_height(16) leaves the scratch header current (face 2 scaled from 13), and vst_font(2)
    then re-asks for ITS top — the header built by the first call, read by the second."""
    first = vst_height(height_call(SWISS_10, 16))
    redispatched = vdi.dispatched_pokes(onto=case.continued(first))
    result = vst_font(vdi.function_pokes("VDI_ROM_VST_FONT", intin=(2,), workstation_pokes=redispatched))
    assert result.linea("CUR_FONT") == vdi.VDI_PHYS_WORK + SCRATCH_HEAD
    assert result.intout(1) == [2]


def test_vst_font_writes_its_counts_before_the_answer():
    assert vst_font(vdi.intout_over(font_call(SWISS_14, 5, 0))).contrl(vdi.CONTRL_N_INTOUT) == 5


def test_vst_font_on_a_virtual_workstation():
    result = vst_font(font_call(SWISS_14, 5, 1, virtual=6))
    assert result.workstation("CUR_FONT", vdi.VIRTUAL_WORK_AT) == DUTCH_10
    assert result.workstation("CUR_FONT") == vdi.workstation(vdi.BASE_IMAGE, "CUR_FONT")


# ==== Tier 3: the worst realistic rows ================================================================
vdi.register("vdi_make_header, scaled up by a fraction", addrs.VDI_ROM_MAKE_HEADER,
             header_machine(SWISS_14, 0x2000, SCALE_UP))
vdi.register("vdi_make_header, doubled", addrs.VDI_ROM_MAKE_HEADER, header_machine(SWISS_14, DOUBLE, SCALE_UP))
vdi.register("vdi_vst_height, an exact size", addrs.VDI_ROM_VST_HEIGHT, height_call(SWISS_10, 19))
vdi.register("vdi_vst_height, scaled up", addrs.VDI_ROM_VST_HEIGHT, height_call(SWISS_10, 30))
# The target build does not mask a font pointer (its image is at 0 and the bus drops the high byte): this row
# puts one on the bus, so the target's unmasked path is under Tier 3's second differential.
vdi.register("vdi_vst_height, chain on from 0 through the 24-bit bus", addrs.VDI_ROM_VST_HEIGHT,
             chain_through_the_bus_call())
vdi.register("vdi_vst_point, an exact size", addrs.VDI_ROM_VST_POINT, point_call(SWISS_10, 14))
vdi.register("vdi_vst_point, doubled", addrs.VDI_ROM_VST_POINT, point_call(SWISS_10, 50))
vdi.register("vdi_vst_font, by height, scaled", addrs.VDI_ROM_VST_FONT, font_call(SWISS_14, 5, 0))
vdi.register("vdi_vst_font, by point", addrs.VDI_ROM_VST_FONT, font_call(SWISS_14, 5, 1))
