"""init_wk ($fcd402) — the record set-up both opens end in (`src/vdi/workstation.c`).

    intin[1] line type 0..7 -> less one (0 as -1), else 0      intin[2] line colour -> MAP_COL, else colour 1
    intin[3] marker type 1..6 -> less one, else 2              intin[4] marker colour
    intin[6] text colour (intin[5], the face, skipped)         SIZ_TAB[9] marker height, scale 1
    intin[7] interior 0..4, else 0                              intin[8] style 1..24 under PATTERN, else 1..12,
                                                                         stored AS GIVEN (1-based: a ROM bug)
    intin[9] fill colour     intin[10] coordinate system        st_fl_ptr; the rest at their defaults
    contrl[2] = 6, contrl[4] = 45; intout = DEV_TAB, ptsout = SIZ_TAB; VDI_RESULT = 1

Entered as its two callers leave the machine: the open call's arrays staged, and the record LINEA_CUR_WORK names
FILLed — v_opnvwk's is a fresh block, v_opnwk's the physical record. Every colour index is read against DEV_TAB[13]
at the compare, so a case stages a smaller bound too.

THE READS AND STORES INTERLEAVE in intin's order, and the pointers are each loaded once: intin laid over the record
shows a stored attribute read back by a later intin word, and the answers laid over contrl, over each other, over
DEV_TAB itself and over the Line-A pointers show which store comes last and when each pointer is read.
"""
import pytest

from harness import addrs

import vdi
import vdi_helpers
import vdi_inquire
import vdi_workstation as ws
from case import merge_pokes

H = ws.WORKSTATION_H
WORK = vdi.VIRTUAL_WORK_AT
COLOURS = vdi.linea(vdi.BASE_IMAGE, "DEV_TAB")[vdi.VDI_DEV_TAB_COLOURS_INDEX]
INIT_OPCODE = addrs.VDI_ROM_V_OPNVWK_OPCODE


def pen(index):
    return vdi.rom_word(vdi.VDI_MAP_COL + vdi.WORD_BYTES * index)


def init_pokes(intin=ws.GEM_INTIN, pokes=None):
    """v_opnvwk's call with `intin`, the new record at the virtual band made current and FILLed."""
    call = vdi.call_pokes(INIT_OPCODE, intin, workstation_pokes=vdi.virtual_workstation(ws.FIRST_VIRTUAL_HANDLE))
    return merge_pokes(call, ws.stale_record(WORK), pokes)


def init(intin=ws.GEM_INTIN, pokes=None, **kwargs):
    return vdi_helpers.run_call(ws.INIT_WK, {}, (), init_pokes(intin, pokes), **kwargs)


def field(result, name):
    return vdi.signed_word(result.workstation(name, WORK))


def test_gem_s_open_sets_every_attribute_and_answers_the_tables():
    result = init()
    assert [field(result, name) for name in ("LINE_INDEX", "MARK_INDEX", "FILL_STYLE", "FILL_INDEX", "XFM_MODE")] == \
        [0, 0, 0, 1, 2]
    assert [result.workstation(name, WORK) for name in ("LINE_COLOR", "MARK_COLOR", "TEXT_COLOR", "FILL_COLOR")] == \
        [pen(1)] * 4
    assert result.workstation("MARK_HEIGHT", WORK) == result.linea("SIZ_TAB")[vdi.VDI_SIZ_TAB_MIN_MARK_HEIGHT_INDEX]
    assert result.workstation("CUR_FONT", WORK) == result.linea("DEF_FONT")
    assert result.workstation("XMX_CLIP", WORK) == result.linea("DEV_TAB")[vdi.VDI_DEV_TAB_MAX_X_INDEX]
    assert result.workstation("UD_PATRN", WORK)[:16] == [vdi.rom_word(vdi.VDI_UD_PATTERN_DEFAULT + 2 * row)
                                                        for row in range(16)]
    assert (result.contrl(vdi.CONTRL_N_PTSOUT), result.contrl(vdi.CONTRL_N_INTOUT)) == (6, vdi.VDI_DEV_TAB_WORDS)
    assert result.intout(vdi.VDI_DEV_TAB_WORDS + 1) == result.linea("DEV_TAB") + [vdi.FILL * 0x101]
    assert result.ptsout(vdi.VDI_SIZ_TAB_WORDS) == result.linea("SIZ_TAB")
    assert result.word(vdi.VDI_RESULT) == vdi.VDI_RESULT_SET


def test_the_font_and_the_face_count_are_the_ring_s_as_it_stands():
    """WS_CUR_FONT is DEF_FONT and WS_NUM_FONTS is FONT_COUNT, each read at the store — a GDOS machine's, not the
    snapshot's one face and its 8x8."""
    result = init(pokes=vdi.linea_pokes(FONT_COUNT=3, DEF_FONT=vdi.FONT_RAM_8X16))
    assert (result.workstation("NUM_FONTS", WORK), result.workstation("CUR_FONT", WORK)) == (3, vdi.FONT_RAM_8X16)


# (intin[1], WS_LINE_INDEX): 1..7 less one, 0 as -1 (the clamp passes 0..7), everything else 0 — signed.
@pytest.mark.parametrize("given,stored", ((0, -1), (1, 0), (7, 6), (8, 0), (-1, 0), (0x7FFF, 0), (-0x8000, 0)))
def test_the_line_type_is_stored_less_one_and_0_as_minus_1(given, stored):
    assert field(init(ws.open_intin(LINE_TYPE=given)), "LINE_INDEX") == stored


# (intin[3], WS_MARK_INDEX): the word less one, in 0..5, else 2 — so 0 and -$8000 (whose less-one wraps) are 2.
@pytest.mark.parametrize("given,stored", ((0, 2), (1, 0), (6, 5), (7, 2), (-1, 2), (-0x8000, 2), (0x7FFF, 2)))
def test_the_marker_type_is_stored_less_one_else_the_asterisk(given, stored):
    assert field(init(ws.open_intin(MARK_TYPE=given)), "MARK_INDEX") == stored


COLOUR_FIELDS = {"LINE_COLOUR": "LINE_COLOR", "MARK_COLOUR": "MARK_COLOR", "TEXT_COLOUR": "TEXT_COLOR",
                 "FILL_COLOUR": "FILL_COLOR"}


@pytest.mark.parametrize("given", tuple(COLOUR_FIELDS))
@pytest.mark.parametrize("index,expected", ((0, 0), (COLOURS - 1, COLOURS - 1), (COLOURS, 1), (-1, 1), (0x7FFF, 1)))
def test_each_colour_is_mapped_and_one_out_of_range_is_colour_1(given, index, expected):
    result = init(ws.open_intin(**{given: index}))
    assert result.workstation(COLOUR_FIELDS[given], WORK) == pen(expected)


@pytest.mark.parametrize("index,expected", ((3, 3), (4, 1)))
def test_the_colour_bound_is_dev_tab_13_as_it_stands(index, expected):
    """Medium resolution's four colours: DEV_TAB[13] read at the compare, not the snapshot's sixteen."""
    bound = {vdi.LINEA_DEV_TAB + vdi.VDI_DEV_TAB_COLOURS_INDEX * vdi.WORD_BYTES: vdi.pack_words(4)}
    result = init(ws.open_intin(LINE_COLOUR=index, FILL_COLOUR=index), bound)
    assert result.workstation("LINE_COLOR", WORK) == result.workstation("FILL_COLOR", WORK) == pen(expected)


# (interior, style, stored interior, stored style): 0..4 else hollow; 1..24 under PATTERN, 1..12 otherwise, else 1.
INTERIORS = ((0, 12, 0, 12), (0, 13, 0, 1), (1, 1, 1, 1), (2, 1, 2, 1), (2, 24, 2, 24), (2, 25, 2, 1), (2, 0, 2, 1),
             (3, 12, 3, 12), (3, 13, 3, 1), (3, 24, 3, 1), (4, 5, 4, 5), (5, 24, 0, 1), (-1, 3, 0, 3), (0x7FFF, 2, 0, 2))


@pytest.mark.parametrize("interior,style,stored_interior,stored_style", INTERIORS)
def test_the_fill_interior_and_its_style_range(interior, style, stored_interior, stored_style):
    """The style is stored AS GIVEN — 1-based, where vsf_style stores it less one — so st_fl_ptr, which reads it
    0-based, points WS_PATPTR at the pattern AFTER the one asked for (the differential holds it to the ROM's)."""
    result = init(ws.open_intin(FILL_INTERIOR=interior, FILL_STYLE=style))
    assert (field(result, "FILL_STYLE"), field(result, "FILL_INDEX")) == (stored_interior, stored_style)


def test_the_pattern_is_the_one_after_the_style_asked_for():
    """Pattern style 1 opens as style 2's pattern: WS_PATPTR is the LOWER table's second, not its first."""
    rows = vdi.rom_word(vdi.VDI_PATTERNS_LOWER) + 1
    first = vdi.VDI_PATTERNS_LOWER + vdi.VDI_PATTERN_TABLE_HEADER_BYTES
    result = init(ws.open_intin(FILL_INTERIOR=vdi.VDI_INTERIOR_PATTERN, FILL_STYLE=1))
    assert result.workstation("PATPTR", WORK) == first + rows * vdi.WORD_BYTES


@pytest.mark.parametrize("mode", (0, 2, -0x8000))
def test_the_coordinate_system_is_stored_as_given(mode):
    assert field(init(ws.open_intin(XFM_MODE=mode)), "XFM_MODE") == mode


# ---- the ORDER, where an overlap shows it -------------------------------------------------------------------------
# The two cases that lay an answer over a Line-A POINTER run without the attribution pass (READS_A_POINTER_IT_WRITES):
# the pass inverts that pointer before the run, and both cores follow it off the image (measured: the host process
# dies of SIGBUS). The stale record and the FILLed arrays stand in for it.

def intin_over_the_record(offset, words):
    """intin laid over the record at `offset`, holding `words` from intin[0]."""
    return merge_pokes(vdi.linea_pokes(INTIN=WORK + offset), {WORK + offset: vdi.pack_words(*words)})


def test_the_style_is_read_after_the_interior_is_stored():
    """intin[8] lies ON WS_FILL_STYLE: the style read is the interior (3, a hatch) just stored there."""
    offset = vdi.WS_FILL_STYLE - H["VDI_OPEN_FILL_STYLE"] * vdi.WORD_BYTES
    result = init(pokes=intin_over_the_record(offset, ws.open_intin(FILL_INTERIOR=3, FILL_STYLE=9)))
    assert (field(result, "FILL_STYLE"), field(result, "FILL_INDEX")) == (3, 3)


def test_the_fill_colour_is_read_after_the_style_is_stored():
    """intin[9] lies ON WS_FILL_INDEX: the fill colour index read is the style (5) just stored there."""
    offset = vdi.WS_FILL_INDEX - H["VDI_OPEN_FILL_COLOUR"] * vdi.WORD_BYTES
    result = init(pokes=intin_over_the_record(offset, ws.open_intin(FILL_INTERIOR=2, FILL_STYLE=5, FILL_COLOUR=9)))
    assert result.workstation("FILL_COLOR", WORK) == pen(5)


def test_the_counts_come_before_the_answers():
    """intout laid over contrl[4]: DEV_TAB[0] is left there, so the count was stored first."""
    result = init(pokes=vdi.intout_over({}))
    assert result.contrl(vdi.CONTRL_N_INTOUT) == result.linea("DEV_TAB")[0]


def test_ptsout_is_answered_after_intout():
    """ptsout laid over intout: SIZ_TAB is left over DEV_TAB's first twelve words."""
    result = init(pokes=vdi.linea_pokes(PTSOUT=vdi.INTOUT_AT))
    assert result.intout(vdi.VDI_DEV_TAB_WORDS) == result.linea("SIZ_TAB") + result.linea("DEV_TAB")[12:]


def test_intout_is_copied_a_word_at_a_time_forwards():
    """intout one word into DEV_TAB: each word is read after the one before was stored over it, so DEV_TAB[0]
    runs through the whole table and one word past it — a block move would have shifted the table instead."""
    result = init(pokes=vdi.linea_pokes(INTOUT=vdi.LINEA_DEV_TAB + vdi.WORD_BYTES))
    first = vdi.linea(vdi.BASE_IMAGE, "DEV_TAB")[0]
    assert result.linea("DEV_TAB") == [first] * vdi.VDI_DEV_TAB_WORDS
    assert result.word(vdi.LINEA_DEV_TAB + vdi.VDI_DEV_TAB_WORDS * vdi.WORD_BYTES) == first


def test_the_contrl_pointer_is_loaded_once_for_both_counts():
    """contrl[2] lies ON LINEA_CONTRL's high word: the 6 stored there moves the pointer, and contrl[4] still goes
    where the pointer first said — onto LINEA_INTIN's high word, which init_wk read long before."""
    at = vdi.LINEA_CONTRL - vdi.CONTRL_N_PTSOUT
    result = init(pokes=vdi.linea_pokes(CONTRL=at), **vdi.READS_A_POINTER_IT_WRITES)
    assert result.word(vdi.LINEA_CONTRL) == 6
    assert result.word(at + vdi.CONTRL_N_INTOUT) == vdi.VDI_DEV_TAB_WORDS


# The DEV_TAB word the reload case lays on LINEA_PTSOUT's high word: the LAST, so no later word lands on its low
# word, and one no clamp or default reads.
RELOAD_WORD = vdi.VDI_DEV_TAB_WORDS - 1


def test_the_ptsout_pointer_is_read_after_intout_is_answered():
    """intout laid so that DEV_TAB[44] lands on LINEA_PTSOUT's high word, which is staged a step low: SIZ_TAB
    reaches the ptsout band only because the pointer is read after that store (`vdi_inquire.ptsout_reloaded`)."""
    table = {vdi.LINEA_DEV_TAB + RELOAD_WORD * vdi.WORD_BYTES: vdi.pack_words(vdi_inquire.RELOADED_HIGH_WORD)}
    pokes = vdi_inquire.ptsout_reloaded(table, RELOAD_WORD)
    result = init(pokes=pokes, **vdi.READS_A_POINTER_IT_WRITES)
    assert result.ptsout(vdi.VDI_SIZ_TAB_WORDS) == result.linea("SIZ_TAB")


# ---- the rows Tier 3 prices ---------------------------------------------------------------------------------------
# GEM's open, and a patterned fill — st_fl_ptr's multiply arm, the most init_wk does.
for _label, _intin in (("GEM's open", ws.GEM_INTIN),
                       ("a pattern fill", ws.open_intin(FILL_INTERIOR=vdi.VDI_INTERIOR_PATTERN, FILL_STYLE=20))):
    vdi.register(f"vdi_init_wk, {_label}", addrs.VDI_ROM_INIT_WK, init_pokes(_intin))
