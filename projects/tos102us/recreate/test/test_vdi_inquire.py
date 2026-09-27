"""The VDI's INQUIRIES of the workstation and the input devices — `src/vdi/inquire.c`:

    vql_attributes (35, $fcbd7e)  vqm_attributes (36, $fcbdda)  vqf_attributes (37, $fcbe3a)
    vq_extnd (102, $fcb8d0)       vst_unload_fonts (120, $fced9a)
    vq_mouse (124, $fcb156)       vq_key_s (128, $fcb30a)
    and the two that do nothing: the shared `rts` of opcodes 4/10/27/34 ($fca652) and valuator (29, $fcb198).

(The text inquiries — vqt_attributes, vqt_name, vqt_fontinfo — are `test_vdi_inquire_text.py`.)

Every case enters the function as the dispatcher's `jsr` leaves the machine, over a DISPATCHED
workstation, and stages the record fields it reads with values no default has, so a field read from
the wrong offset answers a wrong number. The colour a record keeps is a hardware PEN and is answered
through VDI_REV_MAP_COL, so the pens are all sixteen.

THE ORDER OF THE STORES is pinned where an overlap can show it: intout laid over contrl[4] says whether
the count was written before or after the answer (`vdi.intout_over`).
"""
import pytest

from harness import BASE_IMAGE, addrs, emu

import vdi
from vdi_inquire import POINTERS_REWRITTEN, RELOADED_HIGH_WORD, ptsout_reloaded, vdi_index_of_pen

PENS = range(vdi.VDI_MAP_COL_ENTRIES)
A_HANDLE = 5
# A write mode on the dispatcher's copy that the record does not hold: what a function reading the
# RECORD would answer differs by one mode from one reading the copy. The dispatcher always leaves the
# two equal, so this is a SOURCE pin over a state no call enters with — never an arm.
RECORD_MODE, COPY_MODE = 1, 3


def run(name, pokes, **kwargs):
    return vdi.run_function(name, pokes, **kwargs)


def wrote_only_the_stack(result):
    return all(emu.STACK_GUARD_LO <= at < emu.STACK_BAND_HI for at in result.info["writes"])


# ==== the two that do nothing =========================================================================

@pytest.mark.parametrize("name,opcode", (("VDI_ROM_NOP", addrs.VDI_ROM_NOP_OPCODE),
                                         ("VDI_ROM_NOP", addrs.VDI_ROM_NOP_OPCODE_10),
                                         ("VDI_ROM_NOP", addrs.VDI_ROM_NOP_OPCODE_27),
                                         ("VDI_ROM_NOP", addrs.VDI_ROM_NOP_OPCODE_34),
                                         ("VDI_ROM_VALUATOR", addrs.VDI_ROM_VALUATOR_OPCODE)))
def test_the_empty_functions_answer_nothing_not_even_a_count(name, opcode):
    """contrl[4] stays as the dispatcher cleared it and intout as FILLed: nothing but the stack moves."""
    result = run(name, vdi.call_pokes(opcode, intin=(1, 2, 3)))
    assert wrote_only_the_stack(result)
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 0


# ==== vql / vqm / vqf_attributes ======================================================================

def line_record(pen, **values):
    return dict(LINE_INDEX=4, LINE_COLOR=pen, LINE_WIDTH=7, **values)


@pytest.mark.parametrize("pen", PENS)
def test_vql_answers_style_colour_mode_and_width(pen):
    result = run("VDI_ROM_VQL_ATTRIBUTES", vdi.function_pokes("VDI_ROM_VQL_ATTRIBUTES",
                                                workstation_pokes=vdi.dispatched_pokes(**line_record(pen, WRT_MODE=2))))
    assert result.intout(3) == [5, vdi_index_of_pen(pen), 3]
    assert result.ptsout(2) == [7, 0]
    assert (result.contrl(vdi.CONTRL_N_PTSOUT), result.contrl(vdi.CONTRL_N_INTOUT)) == (1, 3)
    assert result.word(vdi.VDI_RESULT) == 0, "vql leaves VDI_RESULT as the dispatcher cleared it"


def mark_record(pen, **values):
    return dict(MARK_INDEX=3, MARK_COLOR=pen, MARK_HEIGHT=22, **values)


@pytest.mark.parametrize("pen", PENS)
def test_vqm_answers_the_marker_type_zero_based_and_sets_the_result(pen):
    """`move.w 60(a4)` with no `addq`: the stored 0-based type, where vql and vqf add one."""
    result = run("VDI_ROM_VQM_ATTRIBUTES", vdi.function_pokes("VDI_ROM_VQM_ATTRIBUTES",
                                                workstation_pokes=vdi.dispatched_pokes(**mark_record(pen, WRT_MODE=0))))
    assert result.intout(3) == [3, vdi_index_of_pen(pen), 1]
    assert result.ptsout(2) == [0, 22]
    assert (result.contrl(vdi.CONTRL_N_PTSOUT), result.contrl(vdi.CONTRL_N_INTOUT)) == (1, 3)
    assert result.word(vdi.VDI_RESULT) == vdi.VDI_RESULT_SET


def fill_record(pen, **values):
    return dict(FILL_STYLE=2, FILL_COLOR=pen, FILL_INDEX=17, FILL_PER=0, **values)


@pytest.mark.parametrize("pen", PENS)
def test_vqf_answers_interior_colour_style_mode_and_perimeter(pen):
    result = run("VDI_ROM_VQF_ATTRIBUTES", vdi.function_pokes("VDI_ROM_VQF_ATTRIBUTES",
                                                workstation_pokes=vdi.dispatched_pokes(**fill_record(pen, WRT_MODE=3))))
    assert result.intout(5) == [2, vdi_index_of_pen(pen), 18, 4, 0]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 5
    assert result.contrl(vdi.CONTRL_N_PTSOUT) == 0, "no points, and contrl[2] is not written"
    assert result.ptsout(1) == [vdi.FILL * 0x101]


# (the function, its record's fields, which intout word is the write mode)
ATTRIBUTE_INQUIRIES = (
    ("VDI_ROM_VQL_ATTRIBUTES", line_record, 2),
    ("VDI_ROM_VQM_ATTRIBUTES", mark_record, 2),
    ("VDI_ROM_VQF_ATTRIBUTES", fill_record, 3),
)


@pytest.mark.parametrize("name,record,mode_word", ATTRIBUTE_INQUIRIES)
def test_the_write_mode_is_the_dispatcher_s_copy_plus_one(name, record, mode_word):
    pokes = vdi.merge_pokes(vdi.function_pokes(name, workstation_pokes=vdi.dispatched_pokes(**record(0, WRT_MODE=RECORD_MODE))),
                            vdi.linea_pokes(WRT_MODE=COPY_MODE))
    assert run(name, pokes).intout(mode_word + 1)[mode_word] == COPY_MODE + 1


# Pens outside the table: $4000 reads $8000 bytes ABOVE REV_MAP_COL (a 16-bit index would wrap below
# it), $ffff the word just before it (MAP_COL's last), $8000 the furthest below. No setter stores
# one — the record's pen is always mapped — so this pins the ADDRESS arithmetic, not an arm.
OUTSIDE_PENS = (0x4000, 0xFFFF, 0x8000, 0x7FFF)


@pytest.mark.parametrize("pen", OUTSIDE_PENS)
@pytest.mark.parametrize("name,record,_mode_word", ATTRIBUTE_INQUIRIES)
def test_a_pen_indexes_rev_map_col_sign_extended_in_32_bits(name, record, _mode_word, pen):
    result = run(name, vdi.function_pokes(name, workstation_pokes=vdi.dispatched_pokes(**record(pen))))
    assert result.intout(2)[1] == vdi_index_of_pen(pen)


# One past the top of a word: the ROM's `addq.w #1` wraps a style of $ffff to 0.
def test_a_style_index_of_ffff_answers_zero():
    result = run("VDI_ROM_VQL_ATTRIBUTES", vdi.function_pokes("VDI_ROM_VQL_ATTRIBUTES",
                                                workstation_pokes=vdi.dispatched_pokes(LINE_INDEX=0xFFFF)))
    assert result.intout(1) == [0]


@pytest.mark.parametrize("name,record,_mode_word", ATTRIBUTE_INQUIRIES)
def test_a_virtual_workstation_is_answered_from_its_own_record(name, record, _mode_word):
    work = vdi.virtual_workstation(A_HANDLE, **record(9))
    physical = run(name, vdi.function_pokes(name))
    virtual = run(name, vdi.function_pokes(name, workstation_pokes=work))
    assert virtual.intout(2) != physical.intout(2)
    assert virtual.intout(2)[1] == vdi_index_of_pen(9)


@pytest.mark.parametrize("name,count", (("VDI_ROM_VQL_ATTRIBUTES", 3), ("VDI_ROM_VQM_ATTRIBUTES", 3),
                                        ("VDI_ROM_VQF_ATTRIBUTES", 5)))
def test_the_counts_are_written_after_the_answer(name, count):
    assert run(name, vdi.intout_over(vdi.function_pokes(name))).contrl(vdi.CONTRL_N_INTOUT) == count


def test_vql_writes_the_point_count_after_the_points():
    """ptsout laid over contrl[2]: ptsout[0] (the width) is written there first, then the count 1."""
    pokes = vdi.merge_pokes(vdi.function_pokes("VDI_ROM_VQL_ATTRIBUTES", workstation_pokes=vdi.dispatched_pokes(LINE_WIDTH=9)),
                            vdi.linea_pokes(PTSOUT=vdi.CONTRL_AT + vdi.CONTRL_N_PTSOUT))
    assert run("VDI_ROM_VQL_ATTRIBUTES", pokes).contrl(vdi.CONTRL_N_PTSOUT) == 1


def test_vql_writes_no_count_before_its_answers():
    """contrl laid so that contrl[4] IS LINEA_WRT_MODE, which vql reads for its third answer: its one
    count store comes after that read, so the mode answered is the copy's own, plus one."""
    work = vdi.dispatched_pokes(**line_record(0, WRT_MODE=2))
    pokes = vdi.merge_pokes(vdi.function_pokes("VDI_ROM_VQL_ATTRIBUTES", workstation_pokes=work),
                            vdi.linea_pokes(CONTRL=vdi.LINEA_WRT_MODE - vdi.CONTRL_N_INTOUT))
    assert run("VDI_ROM_VQL_ATTRIBUTES", pokes).intout(3)[2] == 3


@pytest.mark.parametrize("name,record,points", (("VDI_ROM_VQL_ATTRIBUTES", line_record, [7, 0]),
                                                ("VDI_ROM_VQM_ATTRIBUTES", mark_record, [0, 22])))
def test_the_ptsout_pointer_is_read_after_the_intout_answers(name, record, points):
    """intout[2], the copy's write mode + 1, on the pointer (`vdi_inquire.ptsout_reloaded`)."""
    work = vdi.dispatched_pokes(**record(0, WRT_MODE=RELOADED_HIGH_WORD - 1))
    result = run(name, ptsout_reloaded(vdi.function_pokes(name, workstation_pokes=work), 2), **POINTERS_REWRITTEN)
    assert result.ptsout(2) == points


# ==== vq_extnd ========================================================================================
# Tables no two words of which agree, staged BEFORE the dispatcher's copies (which then overwrite
# DEV_TAB[10] and INQ_TAB[19] from the record, as they do on every call).
DEV_RAMP = [0x1100 + i for i in range(vdi.VDI_DEV_TAB_WORDS)]
INQ_RAMP = [0x2200 + i for i in range(vdi.VDI_INQ_TAB_WORDS)]
SIZ_RAMP = [0x3300 + i for i in range(vdi.VDI_SIZ_TAB_WORDS)]
CLIP = dict(XMN_CLIP=11, YMN_CLIP=22, XMX_CLIP=300, YMX_CLIP=190)


def extnd_pokes(flag, *, blit_mode=0, inq_tab=INQ_RAMP):
    tables = vdi.linea_pokes(DEV_TAB=DEV_RAMP, INQ_TAB=inq_tab, SIZ_TAB=SIZ_RAMP, BLIT_MODE=blit_mode)
    work = vdi.dispatched_pokes(onto=tables, **CLIP)
    return vdi.function_pokes("VDI_ROM_VQ_EXTND", intin=(flag,), workstation_pokes=work)


def test_vq_extnd_0_answers_the_open_workstation_tables():
    result = run("VDI_ROM_VQ_EXTND", extnd_pokes(0))
    assert result.intout(vdi.VDI_DEV_TAB_WORDS) == result.linea("DEV_TAB")
    assert result.ptsout(vdi.VDI_SIZ_TAB_WORDS) == SIZ_RAMP
    assert (result.contrl(vdi.CONTRL_N_PTSOUT), result.contrl(vdi.CONTRL_N_INTOUT)) == (6, 45)
    assert result.word(vdi.VDI_RESULT) == vdi.VDI_RESULT_SET
    assert result.intout(vdi.VDI_DEV_TAB_WORDS + 1)[-1] == vdi.FILL * 0x101, "45 words and no more"


@pytest.mark.parametrize("flag", (1, 0x0100, 0x8000, 0xFFFF))
@pytest.mark.parametrize("blit_mode,speed", ((0, 1000), (1, 5000), (2, 1000), (3, 5000)))
def test_vq_extnd_nonzero_answers_clip_inq_tab_and_a_speed_by_the_blit_mode(flag, blit_mode, speed):
    """`tst.w`: $0100 is extended. The speed is bit 0 of the mode $fc4e06 answers, over INQ_TAB[6]."""
    result = run("VDI_ROM_VQ_EXTND", extnd_pokes(flag, blit_mode=blit_mode))
    expected = result.linea("INQ_TAB")
    expected[vdi.VDI_INQ_TAB_SPEED_INDEX] = speed
    assert result.intout(vdi.VDI_INQ_TAB_WORDS) == expected
    assert result.ptsout(vdi.VDI_SIZ_TAB_WORDS) == [11, 22, 300, 190] + [0] * 8
    assert result.word(vdi.VDI_RESULT) == vdi.VDI_RESULT_SET


def test_vq_extnd_answers_the_snapshot_s_own_tables():
    """No staging but the call: the tables v_opnwk left, both arms."""
    plain = run("VDI_ROM_VQ_EXTND", vdi.function_pokes("VDI_ROM_VQ_EXTND", intin=(0,)))
    assert plain.intout(vdi.VDI_DEV_TAB_WORDS) == vdi.linea(BASE_IMAGE, "DEV_TAB")
    extended = run("VDI_ROM_VQ_EXTND", vdi.function_pokes("VDI_ROM_VQ_EXTND", intin=(1,)))
    assert extended.intout(vdi.VDI_INQ_TAB_WORDS) == vdi.linea(BASE_IMAGE, "INQ_TAB")


def intin_over_intout(pokes, flag):
    """intin laid over intout, with intin[0] = `flag` — what a binding passing one array for both does."""
    return vdi.merge_pokes(pokes, vdi.linea_pokes(INTIN=vdi.INTOUT_AT), {vdi.INTOUT_AT: vdi.pack_words(flag)})


def test_vq_extnd_reads_intin_again_after_answering_so_the_plain_arm_answers_a_speed():
    """THE SECOND READ of intin[0] decides the speed. With intin over intout it reads DEV_TAB[0]
    (nonzero), so the PLAIN inquiry writes the speed over DEV_TAB[6]."""
    result = run("VDI_ROM_VQ_EXTND", intin_over_intout(extnd_pokes(0, blit_mode=1), 0))
    expected = result.linea("DEV_TAB")
    expected[vdi.VDI_INQ_TAB_SPEED_INDEX] = 5000
    assert result.intout(vdi.VDI_DEV_TAB_WORDS) == expected
    assert result.ptsout(vdi.VDI_SIZ_TAB_WORDS) == SIZ_RAMP, "the FIRST read chose the plain tables"


def test_vq_extnd_extended_with_inq_tab_0_zero_answers_no_speed():
    """...and the other way round: extended by the first read, but INQ_TAB[0] = 0 copied over intin[0]
    makes the second read say "plain", so INQ_TAB[6] is answered as it stands."""
    result = run("VDI_ROM_VQ_EXTND", intin_over_intout(extnd_pokes(1, blit_mode=1, inq_tab=[0] + INQ_RAMP[1:]), 1))
    assert result.intout(vdi.VDI_INQ_TAB_WORDS) == result.linea("INQ_TAB")
    assert result.ptsout(vdi.VDI_SIZ_TAB_WORDS)[:4] == [11, 22, 300, 190], "the FIRST read chose the extended tables"


def test_vq_extnd_loads_the_intout_pointer_again_for_the_speed():
    """intout laid over LINEA_INTOUT itself, and INQ_TAB[0..1] the address of the intout band: the copy
    rewrites the pointer, and the ROM's reload (`movea.l $29aa,a0`) puts the speed in the band — at the
    old address the copy's INQ_TAB[6] stands."""
    inq_tab = [vdi.INTOUT_AT >> 16, vdi.INTOUT_AT & 0xFFFF] + INQ_RAMP[2:]
    pokes = vdi.merge_pokes(extnd_pokes(1, blit_mode=1, inq_tab=inq_tab), vdi.linea_pokes(INTOUT=vdi.LINEA_INTOUT))
    result = run("VDI_ROM_VQ_EXTND", pokes, **POINTERS_REWRITTEN)
    speed_at = vdi.VDI_INQ_TAB_SPEED_INDEX * vdi.WORD_BYTES
    assert result.word(vdi.INTOUT_AT + speed_at) == 5000
    assert result.word(vdi.LINEA_INTOUT + speed_at) == INQ_RAMP[vdi.VDI_INQ_TAB_SPEED_INDEX]


def test_vq_extnd_writes_its_counts_first():
    """intout over contrl[4]: DEV_TAB[0] is left there, not 45."""
    result = run("VDI_ROM_VQ_EXTND", vdi.intout_over(extnd_pokes(0)))
    assert result.contrl(vdi.CONTRL_N_INTOUT) == DEV_RAMP[0]


# ==== vst_unload_fonts ================================================================================
LOADED = vdi.FONT_AT
STALE = dict(LOADED_FONTS=LOADED, SCRPT2=0x1234, SCRTCHP=0x00ABCDEF, NUM_FONTS=9)
FONT_COUNT = 4


@pytest.mark.parametrize("virtual", (False, True))
def test_vst_unload_fonts_resets_the_record_s_font_state(virtual):
    at = vdi.VIRTUAL_WORK_AT if virtual else vdi.VDI_PHYS_WORK
    onto = vdi.linea_pokes(FONT_COUNT=FONT_COUNT)
    work = vdi.virtual_workstation(A_HANDLE, onto=onto, **STALE) if virtual else vdi.dispatched_pokes(onto=onto, **STALE)
    result = run("VDI_ROM_VST_UNLOAD_FONTS", vdi.function_pokes("VDI_ROM_VST_UNLOAD_FONTS", workstation_pokes=work))
    assert result.workstation("LOADED_FONTS", at) == 0
    assert result.workstation("SCRPT2", at) == vdi.rom_word(vdi.VDI_SCRPT2_DEFAULT) == 204
    assert result.workstation("SCRTCHP", at) == vdi.VDI_TEXT_SCRATCH
    assert result.workstation("NUM_FONTS", at) == FONT_COUNT
    record = range(at, at + vdi.WS_BYTES)
    assert all(a in record or emu.STACK_GUARD_LO <= a < emu.STACK_BAND_HI for a in result.info["writes"]), \
        "it writes the record and nothing else: not the ring's loaded slot, not CUR_FONT, no count"


# ==== vq_mouse and vq_key_s ============================================================================

def mouse_pokes(buttons=2, x=123, y=45):
    return vdi.merge_pokes(vdi.function_pokes("VDI_ROM_VQ_MOUSE"), vdi.linea_pokes(MOUSE_BT=buttons, GCURX=x, GCURY=y))


@pytest.mark.parametrize("buttons,x,y", ((0, 0, 0), (2, 123, 45), (3, 319, 199), (1, 0xFFFF, 0x8000)))
def test_vq_mouse_answers_the_buttons_and_the_position(buttons, x, y):
    result = run("VDI_ROM_VQ_MOUSE", mouse_pokes(buttons, x, y))
    assert result.intout(1) == [buttons]
    assert result.ptsout(2) == [x, y]
    assert (result.contrl(vdi.CONTRL_N_PTSOUT), result.contrl(vdi.CONTRL_N_INTOUT)) == (1, 1)


def test_vq_mouse_writes_the_count_after_the_buttons():
    assert run("VDI_ROM_VQ_MOUSE", vdi.intout_over(mouse_pokes(buttons=2))).contrl(vdi.CONTRL_N_INTOUT) == 1


def key_pokes(kbshift):
    return vdi.merge_pokes(vdi.function_pokes("VDI_ROM_VQ_KEY_S"), {addrs.KBSHIFT: bytes([kbshift])})


# The four modifier bits pass; Caps Lock (bit 4) and the emulated mouse buttons (5, 6) do not.
@pytest.mark.parametrize("kbshift", (0x00, 0x01, 0x0F, 0x10, 0x5A, 0xFF, 0x80))
def test_vq_key_s_answers_the_four_modifier_bits(kbshift):
    result = run("VDI_ROM_VQ_KEY_S", key_pokes(kbshift))
    assert result.intout(1) == [kbshift & 0x0F]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1


def test_vq_key_s_writes_the_count_before_the_answer():
    """The other order from vq_mouse: contrl[4] = 1 first, so intout over it is left the shift state."""
    assert run("VDI_ROM_VQ_KEY_S", vdi.intout_over(key_pokes(0x0C))).contrl(vdi.CONTRL_N_INTOUT) == 0x0C


# ==== Tier 3: the worst realistic rows ================================================================
vdi.register("vdi_nop, opcode 4", addrs.VDI_ROM_NOP, vdi.call_pokes(addrs.VDI_ROM_NOP_OPCODE))
vdi.register("vdi_valuator, opcode 29", addrs.VDI_ROM_VALUATOR, vdi.call_pokes(addrs.VDI_ROM_VALUATOR_OPCODE))
vdi.register("vdi_vql_attributes, a virtual workstation", addrs.VDI_ROM_VQL_ATTRIBUTES,
             vdi.function_pokes("VDI_ROM_VQL_ATTRIBUTES", workstation_pokes=vdi.virtual_workstation(A_HANDLE, **line_record(9))))
vdi.register("vdi_vqm_attributes, a virtual workstation", addrs.VDI_ROM_VQM_ATTRIBUTES,
             vdi.function_pokes("VDI_ROM_VQM_ATTRIBUTES", workstation_pokes=vdi.virtual_workstation(A_HANDLE, **mark_record(9))))
vdi.register("vdi_vqf_attributes, a virtual workstation", addrs.VDI_ROM_VQF_ATTRIBUTES,
             vdi.function_pokes("VDI_ROM_VQF_ATTRIBUTES", workstation_pokes=vdi.virtual_workstation(A_HANDLE, **fill_record(9))))
vdi.register("vdi_vq_extnd, plain", addrs.VDI_ROM_VQ_EXTND, extnd_pokes(0))
vdi.register("vdi_vq_extnd, extended", addrs.VDI_ROM_VQ_EXTND, extnd_pokes(1))
vdi.register("vdi_vst_unload_fonts, loaded fonts", addrs.VDI_ROM_VST_UNLOAD_FONTS,
             vdi.function_pokes("VDI_ROM_VST_UNLOAD_FONTS", workstation_pokes=vdi.dispatched_pokes(**STALE)))
vdi.register("vdi_vq_mouse, a button and a position", addrs.VDI_ROM_VQ_MOUSE, mouse_pokes())
vdi.register("vdi_vq_key_s, every bit set but Control", addrs.VDI_ROM_VQ_KEY_S, key_pokes(0xFB))
