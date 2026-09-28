"""The TEXT LAYER's two ring builders — `src/vdi/text.c`:

    text_init ($fcde9c, v_opnwk's Alcyon call)      vst_load_fonts (119, $fced06)

text_init fixes the ring's slots (0 the ROM 6x6, 2 and 3 emptied), then walks it — the 6x6 and the chain
v_opnwk left in slot 1 — for the default font, the face count, the system face's character sizes and
heights, and any form still in Intel byte order. vst_load_fonts takes GDOS's chain for a workstation,
swapping and flagging each form not yet turned, and counts its faces.

EVERY CASE STAGES WHAT BOTH WRITE AS STALE, so a store one core makes and the other does not is a byte that
differs — and every case runs `case.run`'s attribution pass as well.
"""
import pytest

from harness import addrs

import case
import vdi
import vdi_helpers
import vdi_text_c as text
from vdi_text import font_field
from vdi_text_c import chain_pokes, header_at, intel_forms, rom_form

WORD = vdi.WORD_BYTES
LONG = vdi.LONG_BYTES
STALE_FONT = header_at(15)            # a header address nothing else stages, for a stale pointer
STALE_SYSTEM_SLOT = vdi.FONT_ROM_8X16  # a real font in slot 0, so a walk that kept it measures the wrong sizes
SIZ = vdi.LINEA_SIZ_TAB
DEV = vdi.LINEA_DEV_TAB


def test_the_band_is_dead_memory_in_this_snapshot():
    text.assert_dead_in_the_snapshot()


# ==== text_init =======================================================================================
def stale_text_init_state():
    """Everything text_init writes, stale: the four character sizes, the two DEV_TAB counts, the face
    count, the ring's three slots it sets, DEF_FONT and CUR_FONT."""
    return vdi.merge_pokes(
        {SIZ: vdi.pack_words(*[vdi.STALE_WORD] * 4),
         DEV + vdi.VDI_DEV_TAB_CHAR_HEIGHTS_INDEX * WORD: vdi.pack_words(vdi.STALE_WORD),
         DEV + vdi.VDI_DEV_TAB_FACES_INDEX * WORD: vdi.pack_words(vdi.STALE_WORD)},
        vdi.linea_pokes(FONT_COUNT=vdi.STALE_WORD, DEF_FONT=STALE_FONT, CUR_FONT=STALE_FONT,
                        FONT_RING=[STALE_SYSTEM_SLOT, vdi.FONT_RAM_8X8, STALE_FONT, STALE_FONT]))


def text_init(pokes=None):
    staged = vdi.merge_pokes(stale_text_init_state(), pokes)
    return vdi_helpers.run_call("VDI_ROM_TEXT_INIT", {}, (), staged)


def sizes(result):
    return result.words(SIZ, 4)


def counts(result):
    """(DEV_TAB[5] heights, DEV_TAB[10] faces, FONT_COUNT)."""
    return (result.word(DEV + vdi.VDI_DEV_TAB_CHAR_HEIGHTS_INDEX * WORD),
            result.word(DEV + vdi.VDI_DEV_TAB_FACES_INDEX * WORD), result.linea("FONT_COUNT"))


def test_text_init_over_the_snapshot_ring_rebuilds_what_boot_left():
    """The 6x6, then the RAM 8x8 -> 8x16 chain: widths 5..7, heights 4..13 (the three tops), three
    system-face heights, one face, and the 8x8 — the one flagged default — as DEF_FONT and CUR_FONT. Slots 2
    and 3 are emptied BEFORE the walk, so the stale pointers staged there are never followed."""
    result = text_init()
    assert sizes(result) == [5, 4, 7, 13]
    assert counts(result) == (3, 1, 1)
    assert result.linea("FONT_RING") == [vdi.FONT_ROM_6X6, vdi.FONT_RAM_8X8, 0, 0]
    assert (result.linea("DEF_FONT"), result.linea("CUR_FONT")) == (vdi.FONT_RAM_8X8, vdi.FONT_RAM_8X8)


def test_text_init_takes_the_last_default_along_the_ring():
    """High resolution's flags, as v_opnwk patches them ($fcb7b6 / $fcb7be): the 8x8 no longer default, the
    8x16 default — which DEF_FONT, and so CUR_FONT, then names."""
    flags = {vdi.FONT_RAM_8X8 + vdi.FONT_FLAGS: vdi.pack_words(font_field("8x8", "FLAGS") ^ vdi.FONT_FLAG_DEFAULT_MASK),
             vdi.FONT_RAM_8X16 + vdi.FONT_FLAGS: vdi.pack_words(font_field("8x16", "FLAGS") | vdi.FONT_FLAG_DEFAULT_MASK)}
    result = text_init(flags)
    assert (result.linea("DEF_FONT"), result.linea("CUR_FONT")) == (vdi.FONT_RAM_8X16, vdi.FONT_RAM_8X16)


def test_text_init_with_no_default_keeps_the_stale_one():
    """No font flagged default: DEF_FONT is never stored, and CUR_FONT is set from whatever it held."""
    flags = {vdi.FONT_RAM_8X8 + vdi.FONT_FLAGS: vdi.pack_words(font_field("8x8", "FLAGS") ^ vdi.FONT_FLAG_DEFAULT_MASK)}
    result = text_init(flags)
    assert (result.linea("DEF_FONT"), result.linea("CUR_FONT")) == (STALE_FONT, STALE_FONT)


def test_text_init_with_slot_1_empty_walks_the_6x6_alone():
    result = text_init(vdi.linea_pokes(FONT_RING=[STALE_FONT, 0]))
    assert sizes(result) == [5, 4, 5, 4]
    assert counts(result) == (1, 1, 1)


# A slot-1 chain of several faces: the system face's sizes come from face 1 alone, compared UNSIGNED — a
# width of $8000 is the largest, not the most negative, and a top of $ffff is not a new smallest — and the
# faces are counted by CHANGES of id along the walk, so face 1 coming back is one more face.
MIXED_CHAIN = (("8x16", dict(ID=vdi.FONT_SYSTEM_FACE, MAX_CHAR_WIDTH=0x8000, TOP=0xFFFF, FLAGS=0x0C)),
               ("8x8", dict(ID=2, MAX_CHAR_WIDTH=0x7F00, TOP=2, FLAGS=0x0C)),
               ("8x8", dict(ID=vdi.FONT_SYSTEM_FACE, MAX_CHAR_WIDTH=3, TOP=3, FLAGS=0x0D)))


def test_text_init_measures_the_system_face_alone_and_unsigned():
    chain, headers = chain_pokes(MIXED_CHAIN)
    result = text_init(vdi.merge_pokes(chain, vdi.linea_pokes(FONT_RING=[STALE_FONT, headers[0]])))
    assert sizes(result) == [3, 3, 0x8000, 0xFFFF]
    assert counts(result) == (3, 3, 3)
    assert result.linea("DEF_FONT") == headers[2]


# THE BYTE SWAP: a slot-1 chain whose forms are still in Intel order (FLAGS without the swapped bit), each a
# copy of the ROM font's own form turned round — so after the walk they are the ROM's forms again.
def unswapped_ring():
    forms, (form_8x8, form_8x16) = intel_forms("8x8", "8x16")
    chain, headers = chain_pokes((("8x8", dict(DAT_TABLE=form_8x8, FLAGS=font_field("8x8", "FLAGS") ^ vdi.FONT_FLAG_SWAPPED_MASK)),
                                  ("8x16", dict(DAT_TABLE=form_8x16,
                                                FLAGS=font_field("8x16", "FLAGS") ^ vdi.FONT_FLAG_SWAPPED_MASK))))
    return vdi.merge_pokes(forms, chain, vdi.linea_pokes(FONT_RING=[STALE_FONT, headers[0]])), headers, (form_8x8, form_8x16)


def test_text_init_turns_an_intel_form_and_leaves_its_flag_clear():
    """Both forms turned back into the ROM's; neither font FLAGGED as turned (text_init has no `eori`), and
    font_byteswap's three Line-A inputs left as the last font's."""
    pokes, headers, (form_8x8, form_8x16) = unswapped_ring()
    result = text_init(pokes)
    assert result.after(form_8x8, len(rom_form("8x8"))) == rom_form("8x8")
    assert result.after(form_8x16, len(rom_form("8x16"))) == rom_form("8x16")
    assert all(not result.word(header + vdi.FONT_FLAGS) & vdi.FONT_FLAG_SWAPPED_MASK for header in headers)
    assert (result.linea("FBASE"), result.linea("FWIDTH"), result.linea("DELY")) == (
        form_8x16, font_field("8x16", "FORM_WIDTH"), font_field("8x16", "FORM_HEIGHT"))


def test_text_init_run_twice_turns_the_form_back_again():
    """No flag set, so a SECOND text_init — a second v_opnwk — swaps the same form back into Intel order."""
    pokes, _headers, (form_8x8, _form_8x16) = unswapped_ring()
    again = text_init(case.continued(text_init(pokes)))
    assert again.after(form_8x8, len(rom_form("8x8"))) == text.intel_order(rom_form("8x8"))


# ==== vst_load_fonts ==================================================================================
# GDOS's call: contrl[7..8] the effects buffer, contrl[9] its split, contrl[10..11] the chain — one word past
# the eleven `vdi.contrl` lays out, so the case's contrl is staged in the text band, whole.
SCRATCH_BUFFER = 0x0003_2100
SCRATCH_SPLIT = 0x0180


def load_call(chain_first, *, work=None, intout_at=None):
    """vst_load_fonts over `work` (a dispatched workstation, the physical one by default) with LINEA_CONTRL
    pointed at a twelve-word contrl naming `chain_first`."""
    work = work if work is not None else vdi.dispatched_pokes()
    pokes = vdi.function_pokes("VDI_ROM_VST_LOAD_FONTS", workstation_pokes=work)
    handle = vdi.read_field(vdi.make_image(work), "WS", "HANDLE", text.work_at(work))
    contrl = (vdi.contrl(addrs.VDI_ROM_VST_LOAD_FONTS_OPCODE, handle=handle)
              + SCRATCH_BUFFER.to_bytes(LONG, "big") + SCRATCH_SPLIT.to_bytes(WORD, "big")
              + chain_first.to_bytes(LONG, "big"))
    assert len(contrl) == text.LONG_CONTRL_BYTES
    pointers = vdi.linea_pokes(CONTRL=text.LONG_CONTRL_AT, **({} if intout_at is None else {"INTOUT": intout_at}))
    return vdi.merge_pokes(pokes, {text.LONG_CONTRL_AT: contrl}, pointers)


def run_load(pokes):
    return vdi.run_function("VDI_ROM_VST_LOAD_FONTS", pokes)


def gdos_chain():
    """Three fonts as GDOS links them: face 2 at two sizes, each with its form still in Intel order (copies of
    the ROM 6x6's and 8x8's), and face 7, whose form is already turned and flagged so."""
    forms, (form_6x6, form_8x8) = intel_forms("6x6", "8x8")
    unswapped = vdi.FONT_FLAG_MONOSPACE_MASK
    chain, headers = chain_pokes((("6x6", dict(ID=2, POINT=8, DAT_TABLE=form_6x6, FLAGS=unswapped)),
                                  ("8x8", dict(ID=2, POINT=10, DAT_TABLE=form_8x8, FLAGS=unswapped)),
                                  ("8x16", dict(ID=7, POINT=14))))
    return vdi.merge_pokes(forms, chain), headers, (form_6x6, form_8x8)


def test_vst_load_fonts_takes_a_gdos_chain():
    fonts, headers, (form_6x6, form_8x8) = gdos_chain()
    work = text.loaded_machine(onto=fonts, NUM_FONTS=1, SCRTCHP=vdi.VDI_TEXT_SCRATCH, SCRPT2=vdi.STALE_WORD)
    result = run_load(load_call(headers[0], work=work))
    assert result.intout(1) == [2]
    assert result.word(text.LONG_CONTRL_AT + vdi.CONTRL_N_INTOUT) == 1
    assert (result.workstation("LOADED_FONTS"), result.workstation("NUM_FONTS")) == (headers[0], 3)
    assert (result.workstation("SCRTCHP"), result.workstation("SCRPT2")) == (SCRATCH_BUFFER, SCRATCH_SPLIT)
    assert result.after(form_6x6, len(rom_form("6x6"))) == rom_form("6x6")
    assert result.after(form_8x8, len(rom_form("8x8"))) == rom_form("8x8")
    assert [result.word(header + vdi.FONT_FLAGS) for header in headers] == [
        vdi.FONT_FLAG_MONOSPACE_MASK | vdi.FONT_FLAG_SWAPPED_MASK] * 2 + [font_field("8x16", "FLAGS")]


def test_vst_load_fonts_leaves_the_ring_to_the_dispatcher():
    """WS_LOADED_FONTS is set, the ring's loaded slot is not: the NEXT dispatch copies it."""
    fonts, headers, _forms = gdos_chain()
    pokes = vdi.merge_pokes(load_call(headers[0], work=text.loaded_machine(onto=fonts)),
                            vdi.linea_pokes(FONT_RING=[vdi.FONT_ROM_6X6, vdi.FONT_RAM_8X8, STALE_FONT, 0]))
    assert run_load(pokes).linea("FONT_RING")[vdi.LINEA_FONT_RING_LOADED] == STALE_FONT


def test_vst_load_fonts_counts_a_face_each_time_the_id_changes():
    """Faces 2, 5, 2: three faces — the walk compares with the PREVIOUS id only. All flagged turned, so no
    form is touched; and the word count wraps (`add.w`)."""
    chain, headers = chain_pokes((("8x8", dict(ID=2)), ("8x8", dict(ID=5)), ("8x16", dict(ID=2))))
    result = run_load(load_call(headers[0], work=text.loaded_machine(onto=chain, NUM_FONTS=0xFFFE)))
    assert result.intout(1) == [3]
    assert result.workstation("NUM_FONTS") == 1


def test_vst_load_fonts_answers_0_to_a_workstation_that_has_fonts():
    """Once only: nothing is taken, not even the buffer; intout[0] = 0, contrl[4] = 1."""
    fonts, headers, _forms = gdos_chain()
    work = text.loaded_machine(chain_pokes((("8x8", dict(ID=9)),), first_slot=5), onto=fonts,
                               SCRTCHP=vdi.VDI_TEXT_SCRATCH, NUM_FONTS=1)
    result = run_load(load_call(headers[0], work=work))
    assert result.intout(1) == [0]
    assert (result.workstation("SCRTCHP"), result.workstation("NUM_FONTS")) == (vdi.VDI_TEXT_SCRATCH, 1)
    assert result.word(header_at(0) + vdi.FONT_FLAGS) == vdi.FONT_FLAG_MONOSPACE_MASK


@pytest.mark.parametrize("already", (False, True))
def test_vst_load_fonts_writes_contrl_4_before_the_answer(already):
    """intout laid over contrl[4]: the count is stored FIRST, so the answer is what is left there."""
    fonts, headers, _forms = gdos_chain()
    work = (text.loaded_machine(chain_pokes((("8x8", dict(ID=9)),), first_slot=5), onto=fonts) if already
            else text.loaded_machine(onto=fonts))
    result = run_load(load_call(headers[0], work=work, intout_at=text.LONG_CONTRL_AT + vdi.CONTRL_N_INTOUT))
    assert result.word(text.LONG_CONTRL_AT + vdi.CONTRL_N_INTOUT) == (0 if already else 2)


def test_vst_load_fonts_on_a_virtual_workstation():
    fonts, headers, _forms = gdos_chain()
    work = text.loaded_machine(virtual=6, onto=fonts, NUM_FONTS=1)
    result = run_load(load_call(headers[0], work=work))
    assert result.workstation("LOADED_FONTS", vdi.VIRTUAL_WORK_AT) == headers[0]
    assert result.workstation("LOADED_FONTS") == 0


# ==== Tier 3: the worst realistic rows ================================================================
vdi.register("vdi_text_init, the snapshot's ring", addrs.VDI_ROM_TEXT_INIT, stale_text_init_state())
vdi.register("vdi_text_init, a chain of three faces", addrs.VDI_ROM_TEXT_INIT,
             vdi.merge_pokes(stale_text_init_state(), chain_pokes(MIXED_CHAIN)[0],
                             vdi.linea_pokes(FONT_RING=[STALE_FONT, chain_pokes(MIXED_CHAIN)[1][0]])))
vdi.register("vdi_vst_load_fonts, three GDOS fonts, two forms turned", addrs.VDI_ROM_VST_LOAD_FONTS,
             load_call(gdos_chain()[1][0], work=text.loaded_machine(onto=gdos_chain()[0])))
vdi.register("vdi_vst_load_fonts, already loaded", addrs.VDI_ROM_VST_LOAD_FONTS,
             load_call(gdos_chain()[1][0], work=text.loaded_machine(chain_pokes((("8x8", dict(ID=9)),), first_slot=5),
                                                                    onto=gdos_chain()[0])))
