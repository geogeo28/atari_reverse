"""The VDI's TEXT inquiries — `src/vdi/inquire.c`:

    vqt_attributes (38, $fce5b0)  vqt_name (130, $fce8ca)  vqt_fontinfo (131, $fce95a)

Each reads a FONT HEADER: the current one through LINEA_CUR_FONT (the dispatcher's copy of
WS_CUR_FONT), or — vqt_name — the one the FONT RING numbers. So the cases stage fonts of their own, in
`vdi.FONT_AT`'s band, and hand them to the machine the way it would get them: as a workstation's
CUR_FONT, or as its LOADED_FONTS, which the dispatcher copies into the ring's loaded slot.

THE RING IN THE SNAPSHOT is [ROM 6x6] [RAM 8x8 -> RAM 8x16] [0] [0], and all three fonts are face 1 —
so against it every element vqt_name is asked for answers the 6x6 header, found or fallen back to
alike. That is why the walk is proved over a LONGER ring: a loaded chain of several faces, runs of one
id, ids that come back, and slots past an empty one.
"""
import pytest

from harness import addrs

import case
import vdi
from vdi_inquire import POINTERS_REWRITTEN, RELOADED_HIGH_WORD, ptsout_reloaded, vdi_index_of_pen

HEADER = vdi.FONT_HEADER_BYTES
NAME_BYTES = vdi.FONT_NAME_BYTES
NAME_WORDS = 1 + NAME_BYTES                   # what contrl[4] says: the id and 32 characters
A_HANDLE = 6
SYSTEM_FACE = 1                               # the id of all three ROM fonts


def font_at(slot):
    """Where staged font number `slot` goes: headers back to back in the font band."""
    return vdi.FONT_AT + slot * HEADER


def staged_font(slot, face, name, following=0, **fields):
    """A font header with its id, name and FONT_NEXT, and any other `fields` by name."""
    return vdi.font_pokes(font_at(slot), ID=face, NAME=name.encode("latin-1"), NEXT=following, **fields)


def run(name, pokes, **kwargs):
    return vdi.run_function(name, pokes, **kwargs)


# ==== one staged font with every metric distinct ======================================================
METRICS = dict(TOP=13, ASCENT=11, HALF=7, DESCENT=3, BOTTOM=4, MAX_CHAR_WIDTH=9, MAX_CELL_WIDTH=10,
               LEFT_OFFSET=2, RIGHT_OFFSET=5, THICKEN=1, FIRST_ADE=32, LAST_ADE=250, FLAGS=0)
METRIC_FACE = 14


def metric_font(**overrides):
    return staged_font(0, METRIC_FACE, "Dutch 11", **{**METRICS, **overrides})


def current_font_machine(font_pokes, *, virtual=False, **record):
    """A workstation whose CUR_FONT is the staged font — dispatched over it, so MONO_STATUS is its."""
    if virtual:
        return vdi.virtual_workstation(A_HANDLE, onto=font_pokes, CUR_FONT=font_at(0), **record)
    return vdi.dispatched_pokes(onto=font_pokes, CUR_FONT=font_at(0), **record)


# ==== vqt_attributes =================================================================================
TEXT_RECORD = dict(CHUP=900, H_ALIGN=2, V_ALIGN=5, WRT_MODE=3)


@pytest.mark.parametrize("pen", range(vdi.VDI_MAP_COL_ENTRIES))
def test_vqt_attributes_answers_the_font_and_the_record(pen):
    """The write mode 0-based out of the RECORD, where the other attribute inquiries add one."""
    work = current_font_machine(metric_font(), TEXT_COLOR=pen, **TEXT_RECORD)
    result = run("VDI_ROM_VQT_ATTRIBUTES", vdi.function_pokes("VDI_ROM_VQT_ATTRIBUTES", workstation_pokes=work))
    assert result.intout(6) == [METRIC_FACE, vdi_index_of_pen(pen), 900, 2, 5, 3]
    assert result.ptsout(4) == [9, 13, 10, 13 + 4 + 1]
    assert (result.contrl(vdi.CONTRL_N_PTSOUT), result.contrl(vdi.CONTRL_N_INTOUT)) == (2, 6)
    assert result.word(vdi.VDI_RESULT) == vdi.VDI_RESULT_SET


def test_vqt_attributes_answers_the_snapshot_s_system_font():
    result = run("VDI_ROM_VQT_ATTRIBUTES", vdi.function_pokes("VDI_ROM_VQT_ATTRIBUTES"))
    top, bottom = vdi.rom_word(vdi.FONT_ROM_6X6 + vdi.FONT_TOP), vdi.rom_word(vdi.FONT_ROM_6X6 + vdi.FONT_BOTTOM)
    assert result.intout(1) == [SYSTEM_FACE]
    assert result.ptsout(4)[3] == top + bottom + 1


def test_vqt_attributes_reads_the_write_mode_from_the_record_not_the_copy():
    """A SOURCE pin over a state the dispatcher never leaves (it copies WS_WRT_MODE into the Line-A
    word on every call): the copy moved, the record kept — the answer is the record's."""
    work = current_font_machine(metric_font(), **TEXT_RECORD)
    pokes = vdi.merge_pokes(vdi.function_pokes("VDI_ROM_VQT_ATTRIBUTES", workstation_pokes=work), vdi.linea_pokes(WRT_MODE=1))
    assert run("VDI_ROM_VQT_ATTRIBUTES", pokes).intout(6)[5] == TEXT_RECORD["WRT_MODE"]


def test_vqt_attributes_reads_the_font_through_the_line_a_copy():
    """...and the font through LINEA_CUR_FONT, not WS_CUR_FONT: the same kind of source pin."""
    work = current_font_machine(metric_font(), **TEXT_RECORD)
    pokes = vdi.merge_pokes(vdi.function_pokes("VDI_ROM_VQT_ATTRIBUTES", workstation_pokes=work),
                            vdi.linea_pokes(CUR_FONT=vdi.FONT_ROM_6X6))
    assert run("VDI_ROM_VQT_ATTRIBUTES", pokes).intout(1) == [SYSTEM_FACE]


@pytest.mark.parametrize("pen", (0x4000, 0xFFFF, 0x8000))
def test_vqt_attributes_indexes_rev_map_col_sign_extended_in_32_bits(pen):
    work = current_font_machine(metric_font(), TEXT_COLOR=pen)
    result = run("VDI_ROM_VQT_ATTRIBUTES", vdi.function_pokes("VDI_ROM_VQT_ATTRIBUTES", workstation_pokes=work))
    assert result.intout(2)[1] == vdi_index_of_pen(pen)


def test_vqt_attributes_cell_height_wraps_in_a_word():
    """`add.w`, `addq.w #1`: TOP + BOTTOM + 1 at $ffff + 0 + 1 is 0."""
    work = current_font_machine(metric_font(TOP=0xFFFF, BOTTOM=0))
    result = run("VDI_ROM_VQT_ATTRIBUTES", vdi.function_pokes("VDI_ROM_VQT_ATTRIBUTES", workstation_pokes=work))
    assert result.ptsout(4)[3] == 0


def test_vqt_attributes_reads_the_top_after_the_first_point():
    """ptsout laid over the font's FONT_TOP: ptsout[0] (the character width) is stored there before the
    ROM reads the top (`$fce5f2`), so the top it answers is that width."""
    at = font_at(0) + vdi.FONT_TOP
    work = current_font_machine(metric_font())
    pokes = vdi.merge_pokes(vdi.function_pokes("VDI_ROM_VQT_ATTRIBUTES", workstation_pokes=work), vdi.linea_pokes(PTSOUT=at))
    width = METRICS["MAX_CHAR_WIDTH"]
    assert run("VDI_ROM_VQT_ATTRIBUTES", pokes).words(at, 2) == [width, width]


def test_vqt_attributes_reads_the_ptsout_pointer_after_the_intout_answers():
    """intout[5], the record's write mode, on the pointer (`vdi_inquire.ptsout_reloaded`)."""
    work = current_font_machine(metric_font(), WRT_MODE=RELOADED_HIGH_WORD)
    pokes = ptsout_reloaded(vdi.function_pokes("VDI_ROM_VQT_ATTRIBUTES", workstation_pokes=work), 5)
    assert run("VDI_ROM_VQT_ATTRIBUTES", pokes, **POINTERS_REWRITTEN).ptsout(4) == [9, 13, 10, 13 + 4 + 1]


def test_vqt_attributes_writes_its_counts_after_the_answer():
    work = current_font_machine(metric_font())
    pokes = vdi.intout_over(vdi.function_pokes("VDI_ROM_VQT_ATTRIBUTES", workstation_pokes=work))
    assert run("VDI_ROM_VQT_ATTRIBUTES", pokes).contrl(vdi.CONTRL_N_INTOUT) == 6


# ==== vqt_fontinfo ===================================================================================
# LINEA_STYLE's bits: 1 = bold (THICKEN answered), 4 = italic (both OFFSETs answered). The others
# (light, outline, underline) change nothing here.
STYLES = (0, 1, 4, 5, 0x3A, 0xFF, 0x0100)


@pytest.mark.parametrize("style", STYLES)
def test_vqt_fontinfo_answers_the_metrics_and_the_effects_the_style_asks_for(style):
    work = current_font_machine(metric_font(), STYLE=style)
    result = run("VDI_ROM_VQT_FONTINFO", vdi.function_pokes("VDI_ROM_VQT_FONTINFO", workstation_pokes=work))
    bold, italic = style & 1, style & 4
    assert result.intout(2) == [32, 250]
    assert result.ptsout(10) == [10, 4, 1 if bold else 0, 3, 2 if italic else 0, 7, 5 if italic else 0, 11, 0, 13]
    assert (result.contrl(vdi.CONTRL_N_PTSOUT), result.contrl(vdi.CONTRL_N_INTOUT)) == (5, 2)
    assert result.word(vdi.VDI_RESULT) == vdi.VDI_RESULT_SET


def test_vqt_fontinfo_answers_the_snapshot_s_system_font_on_a_virtual_workstation():
    font = vdi.FONT_ROM_6X6
    work = vdi.virtual_workstation(A_HANDLE, STYLE=5)
    result = run("VDI_ROM_VQT_FONTINFO", vdi.function_pokes("VDI_ROM_VQT_FONTINFO", workstation_pokes=work))
    assert result.intout(2) == [vdi.rom_word(font + vdi.FONT_FIRST_ADE), vdi.rom_word(font + vdi.FONT_LAST_ADE)]
    assert result.ptsout(10)[9] == vdi.rom_word(font + vdi.FONT_TOP)


def test_vqt_fontinfo_reads_the_ptsout_pointer_after_the_intout_answers():
    """intout[1], the last character, on the pointer (`vdi_inquire.ptsout_reloaded`)."""
    work = current_font_machine(metric_font(LAST_ADE=RELOADED_HIGH_WORD), STYLE=0)
    pokes = ptsout_reloaded(vdi.function_pokes("VDI_ROM_VQT_FONTINFO", workstation_pokes=work), 1)
    assert run("VDI_ROM_VQT_FONTINFO", pokes, **POINTERS_REWRITTEN).ptsout(10) == [10, 4, 0, 3, 0, 7, 0, 11, 0, 13]


# LINEA_STYLE IS TESTED TWICE, each `btst` just before the answer it decides — so ptsout laid over it
# shows each read point: a metric stored on the style word before a test is what that test sees.
# (the ptsout word laid on LINEA_STYLE, the metric that lands there, the ten words answered)
STYLE_OVERLAPS = (
    (1, dict(BOTTOM=5), [10, 5, 1, 3, 2, 7, 5, 11, 0, 13]),     # both tests see the bottom: bold, italic
    (3, dict(DESCENT=5), [10, 4, 0, 5, 2, 7, 5, 11, 0, 13]),    # only the second sees the descent: italic
)


@pytest.mark.parametrize("word,metric,answered", STYLE_OVERLAPS)
def test_vqt_fontinfo_tests_the_style_after_the_points_before_it(word, metric, answered):
    at = vdi.LINEA_STYLE - word * vdi.WORD_BYTES
    work = current_font_machine(metric_font(**metric), STYLE=0)
    pokes = vdi.merge_pokes(vdi.function_pokes("VDI_ROM_VQT_FONTINFO", workstation_pokes=work), vdi.linea_pokes(PTSOUT=at))
    assert run("VDI_ROM_VQT_FONTINFO", pokes).words(at, 10) == answered


def test_vqt_fontinfo_writes_its_counts_after_the_answer():
    pokes = vdi.intout_over(vdi.function_pokes("VDI_ROM_VQT_FONTINFO", workstation_pokes=current_font_machine(metric_font())))
    assert run("VDI_ROM_VQT_FONTINFO", pokes).contrl(vdi.CONTRL_N_INTOUT) == 2


# ==== vqt_name =======================================================================================
# A LOADED chain, as GDOS would link it: two sizes of one face, a second face, the FIRST face again
# (a new face to the walk, which compares with the previous id only), and a face with a full name.
LOADED_CHAIN = (
    (2, "Swiss 10"),
    (2, "Swiss 12"),
    (5, "Dutch \x81ber"),                    # a character over $7f, answered sign-extended
    (2, "Swiss again"),
    (9, "A" * NAME_BYTES),                   # 32 characters: no NUL inside FONT_NAME
)
# The faces that ring numbers: 1 = the ROM 6x6 (the RAM 8x8 and 8x16 are face 1 again), then the chain.
FACES = (vdi.FONT_ROM_6X6, font_at(0), font_at(2), font_at(3), font_at(4))


def chain_pokes(chain=LOADED_CHAIN):
    fonts = {}
    for slot, (face, name) in enumerate(chain):
        following = font_at(slot + 1) if slot + 1 < len(chain) else 0
        fonts = vdi.merge_pokes(fonts, staged_font(slot, face, name, following, FIRST_ADE=32))
    return fonts


def name_pokes(element, *, chain=LOADED_CHAIN, onto=None):
    fonts = vdi.merge_pokes(onto, chain_pokes(chain)) if chain else onto
    work = vdi.dispatched_pokes(onto=fonts, LOADED_FONTS=font_at(0) if chain else 0)
    return vdi.function_pokes("VDI_ROM_VQT_NAME", intin=(element,), workstation_pokes=work)


def expected_name(image, font):
    """The id, then the name up to its NUL — read on past FONT_NAME if there is none there — each
    character sign-extended, the NUL written, then zeros up to intout[33]: 34 words in all."""
    words = [case.word_in(image, font + vdi.FONT_ID)]
    at = font + vdi.FONT_NAME
    while image[at]:
        words.append(image[at] | (0xFF00 if image[at] & 0x80 else 0))
        at += 1
    words.append(0)
    return words + [0] * max(0, NAME_WORDS + 1 - len(words))


@pytest.mark.parametrize("element", range(1, len(FACES) + 1))
def test_vqt_name_numbers_the_faces_along_the_ring(element):
    pokes = name_pokes(element)
    result = run("VDI_ROM_VQT_NAME", pokes)
    expected = expected_name(result.final, FACES[element - 1])
    assert result.intout(len(expected)) == expected
    assert result.contrl(vdi.CONTRL_N_INTOUT) == NAME_WORDS


def test_vqt_name_writes_34_words_and_says_33():
    """THE UNCOUNTED NUL: '6x6 system font' is 15 characters, so intout[16] is its NUL and the zero
    fill runs from intout[17] to intout[33] — one word past the 33 contrl[4] reports."""
    result = run("VDI_ROM_VQT_NAME", name_pokes(1))
    assert result.intout(NAME_WORDS + 2)[NAME_WORDS:] == [0, vdi.FILL * 0x101]


def test_vqt_name_reads_a_full_name_on_into_first_ade():
    """32 characters and no NUL in FONT_NAME: the 33rd byte read is FONT_FIRST_ADE's high byte (0 for
    a first character of 32), so the NUL lands at intout[33] and nothing is zero-filled."""
    result = run("VDI_ROM_VQT_NAME", name_pokes(len(FACES)))
    assert result.intout(NAME_WORDS + 1) == [9] + [ord("A")] * NAME_BYTES + [0]


# Elements that are no face: 0, negatives, and one past the last — all the ROM 6x6, the fallback.
@pytest.mark.parametrize("element", (0, 0xFFFF, 0x8000, len(FACES) + 1, 0x7FFF))
def test_vqt_name_answers_the_rom_6x6_for_an_element_the_ring_has_no_face_for(element):
    result = run("VDI_ROM_VQT_NAME", name_pokes(element))
    expected = expected_name(result.final, vdi.FONT_ROM_6X6)
    assert result.intout(len(expected)) == expected


@pytest.mark.parametrize("element", (1, 2))
def test_vqt_name_over_the_snapshot_ring_answers_face_1_for_everything(element):
    """No loaded fonts: face 1 is the 6x6, and element 2 falls back to the same header."""
    result = run("VDI_ROM_VQT_NAME", name_pokes(element, chain=()))
    expected = expected_name(result.final, vdi.FONT_ROM_6X6)
    assert result.intout(len(expected)) == expected


def test_vqt_name_stops_at_the_first_empty_slot():
    """The ring's slots are walked until a ZERO SLOT, so a font in slot 3 behind an empty loaded slot
    is never reached: element 2 falls back to the 6x6 rather than finding it."""
    ring = vdi.linea_pokes(FONT_RING=[vdi.FONT_ROM_6X6, vdi.FONT_RAM_8X8, 0, font_at(0)])
    fonts = vdi.merge_pokes(ring, staged_font(0, 7, "Behind the gap"))
    work = vdi.dispatched_pokes(onto=fonts, LOADED_FONTS=0)
    result = run("VDI_ROM_VQT_NAME", vdi.function_pokes("VDI_ROM_VQT_NAME", intin=(2,), workstation_pokes=work))
    assert result.intout(1) == [SYSTEM_FACE]


def test_vqt_name_remembers_the_last_id_across_slots():
    """A loaded chain that STARTS with face 1 continues the RAM 8x16's run: its first font is not a new
    face, so element 2 is the second font of the chain."""
    chain = ((SYSTEM_FACE, "System again"), (3, "Three"))
    result = run("VDI_ROM_VQT_NAME", name_pokes(2, chain=chain))
    assert result.intout(1) == [3]


def test_vqt_name_writes_its_count_last():
    assert run("VDI_ROM_VQT_NAME", vdi.intout_over(name_pokes(3))).contrl(vdi.CONTRL_N_INTOUT) == NAME_WORDS


# ==== Tier 3: the worst realistic rows ================================================================
vdi.register("vdi_vqt_attributes, a virtual workstation", addrs.VDI_ROM_VQT_ATTRIBUTES,
             vdi.function_pokes("VDI_ROM_VQT_ATTRIBUTES", workstation_pokes=current_font_machine(metric_font(), virtual=True)))
vdi.register("vdi_vqt_fontinfo, bold italic", addrs.VDI_ROM_VQT_FONTINFO,
             vdi.function_pokes("VDI_ROM_VQT_FONTINFO", workstation_pokes=current_font_machine(metric_font(), STYLE=5)))
vdi.register("vdi_vqt_fontinfo, plain", addrs.VDI_ROM_VQT_FONTINFO,
             vdi.function_pokes("VDI_ROM_VQT_FONTINFO", workstation_pokes=current_font_machine(metric_font(), STYLE=0)))
vdi.register("vdi_vqt_name, the snapshot's face 1", addrs.VDI_ROM_VQT_NAME, name_pokes(1, chain=()))
vdi.register("vdi_vqt_name, the last loaded face", addrs.VDI_ROM_VQT_NAME, name_pokes(len(FACES) - 1))
vdi.register("vdi_vqt_name, past the ring", addrs.VDI_ROM_VQT_NAME, name_pokes(len(FACES) + 1))
