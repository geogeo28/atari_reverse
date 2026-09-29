"""v_opnwk (opcode 1, $fcb694) — the physical workstation opened (`src/vdi/workstation.c`).

    DEV_TAB <- $fd3598 (45), INQ_TAB <- $fd360a (45), INQ_TAB[14] <- $fd32f4, SIZ_TAB <- $fd35f2 (12)
    RAM 8x8 / 8x16 headers <- ROM ($fd40d2 / $fd5b2e, 90 bytes each); FONT_RING[1] = the RAM 8x8
    setres -> 2 medium: DEV_TAB[0] 639, [3] 169, [13] 4; INQ_TAB[4] 2
           -> 3 mono:   DEV_TAB[0] 639, [1] 399, [3] 372, [13] 2, [35] 0, [39] 2; INQ_TAB[1] 1, [4] 1, [5] 0;
                        the 8x8's point 9 and default flag off, the 8x16's point 10 and default flag on
    the physical record handle 1, contrl[6] = 1, current, alone (WS_NEXT 0); LINE_CW = -1
    text_init; init_wk; the four input modes 0; M_HID_CT 1; GCURX/GCURY = DEV_TAB[0]/2, DEV_TAB[1]/2
    init_timer_mouse; REQ_COL <- vq_color(index, realized) for index < DEV_TAB[13], over its own frame's arrays

Each open is a differential over a STALE machine (`test/vdi_workstation.py`), with the shifter's mode and every
palette register declared, and LINEA_PLANES what the console was set up for in that mode: 4 planes low, 2 medium,
1 mono. The palette read is the realized one, so REQ_COL is what the shifter holds, per mille.

SETRES' TWO SWITCHING ARMS HALT inside XBIOS Setscreen (`src/vdi/screen.c`), and are pinned as the screen battery
pins them: in a child process over a SHARED image, the mode named in the halt — and, since v_opnwk has stored
the tables, the fonts and the ring before it calls setres, the child's image is held to the ORIGINAL's run to the
same checkpoint, everything outside the stack band: every store before the switch made, none after.
"""
from pathlib import Path

import pytest

from harness import BASE_IMAGE, addrs, differing_addresses, emu

import vdi
import vdi_helpers
import vdi_screen as screen
import vdi_workstation as ws
from case import merge_pokes

H = ws.WORKSTATION_H
PALETTE = addrs.parse(Path(__file__).resolve().parents[1] / "include/vdi/palette.h", known={**addrs.ADDRS, **vdi.CONSTANTS})
# Each gun's nibble in a palette register, red first.
GUN_SHIFTS = tuple(gun * PALETTE["PALETTE_GUN_BITS"] for gun in reversed(range(PALETTE["PALETTE_GUNS"])))
LOW_PLANES, MEDIUM_PLANES, MONO_PLANES = 4, 2, PALETTE["PALETTE_MONO_PLANES"]
MODES = {"low": (addrs.SHIFTER_MODE_LOW, LOW_PLANES), "medium": (addrs.SHIFTER_MODE_MEDIUM, MEDIUM_PLANES),
         "mono": (addrs.SHIFTER_MODE_HIGH, MONO_PLANES)}


def rom_words(at, count):
    return [vdi.rom_word(at + index * vdi.WORD_BYTES) for index in range(count)]


def opnwk(mode, intin=ws.GEM_INTIN, pokes=None):
    mode_byte, planes = MODES[mode]
    return ws.run_opnwk(mode_byte, intin, planes, pokes)


def realized(index, planes):
    """The three per-mille guns vq_color answers for `index` over `palette_io`'s registers."""
    if planes == MONO_PLANES:
        inverted = (index ^ ws.palette_word(0)) >> PALETTE["PALETTE_MONO_INVERT_BIT"] & 1
        return [PALETTE["PALETTE_PER_MILLE_MAX"] if inverted else 0] * PALETTE["PALETTE_GUNS"]
    pen = vdi.rom_word(vdi.VDI_MAP_COL + index * vdi.WORD_BYTES) & ((1 << planes) - 1)
    word = ws.palette_word(pen)
    return [vdi.rom_word(vdi.VDI_VQ_COLOR_LEVELS + vdi.WORD_BYTES * (word >> shift & PALETTE["PALETTE_GUN_LEVEL_MASK"]))
            for shift in GUN_SHIFTS]


def expected_tables(mode):
    """DEV_TAB / INQ_TAB as `mode` opens them (the entries text_init rewrites aside)."""
    dev = rom_words(vdi.VDI_DEV_TAB_DEFAULT, vdi.VDI_DEV_TAB_WORDS)
    inq = rom_words(vdi.VDI_INQ_TAB_DEFAULT, vdi.VDI_INQ_TAB_WORDS)
    inq[vdi.VDI_INQ_TAB_MAX_VERTICES_INDEX] = vdi.rom_word(vdi.VDI_MAX_VERTICES_DEFAULT)
    if mode == "medium":
        dev[vdi.VDI_DEV_TAB_MAX_X_INDEX] = H["VDI_OPNWK_WIDE_MAX_X"]
        dev[vdi.VDI_DEV_TAB_PIXEL_WIDTH_INDEX] = H["VDI_OPNWK_MEDIUM_PIXEL_WIDTH"]
        dev[vdi.VDI_DEV_TAB_COLOURS_INDEX] = H["VDI_OPNWK_MEDIUM_COLOURS"]
        inq[vdi.VDI_INQ_TAB_PLANES_INDEX] = H["VDI_OPNWK_MEDIUM_PLANES"]
    elif mode == "mono":
        dev[vdi.VDI_DEV_TAB_MAX_X_INDEX] = H["VDI_OPNWK_WIDE_MAX_X"]
        dev[vdi.VDI_DEV_TAB_MAX_Y_INDEX] = H["VDI_OPNWK_HIGH_MAX_Y"]
        dev[vdi.VDI_DEV_TAB_PIXEL_WIDTH_INDEX] = H["VDI_OPNWK_HIGH_PIXEL_WIDTH"]
        dev[vdi.VDI_DEV_TAB_COLOURS_INDEX] = H["VDI_OPNWK_HIGH_COLOURS"]
        dev[vdi.VDI_DEV_TAB_COLOUR_CAPABLE_INDEX] = H["VDI_OPNWK_HIGH_COLOUR_CAPABLE"]
        dev[vdi.VDI_DEV_TAB_PALETTE_INDEX] = H["VDI_OPNWK_HIGH_PALETTE"]
        inq[vdi.VDI_INQ_TAB_BACKGROUNDS_INDEX] = H["VDI_OPNWK_HIGH_BACKGROUNDS"]
        inq[vdi.VDI_INQ_TAB_PLANES_INDEX] = H["VDI_OPNWK_HIGH_PLANES"]
        inq[vdi.VDI_INQ_TAB_LUT_INDEX] = H["VDI_OPNWK_HIGH_LUT"]
    return dev, inq


# DEV_TAB[5] and [10] are text_init's to count (faces, heights) and INQ_TAB[19] the dispatcher's copy; the rest
# of each table is v_opnwk's alone.
TEXT_INIT_DEV = (vdi.VDI_DEV_TAB_CHAR_HEIGHTS_INDEX, vdi.VDI_DEV_TAB_FACES_INDEX)


def without(words, indexes):
    return [word for index, word in enumerate(words) if index not in indexes]


@pytest.mark.parametrize("mode", MODES)
def test_the_device_tables_are_the_defaults_patched_for_the_mode(mode):
    result = opnwk(mode)
    dev, inq = expected_tables(mode)
    assert without(result.linea("DEV_TAB"), TEXT_INIT_DEV) == without(dev, TEXT_INIT_DEV)
    assert result.linea("INQ_TAB") == inq
    assert result.linea("SIZ_TAB")[4:] == rom_words(vdi.VDI_SIZ_TAB_DEFAULT, vdi.VDI_SIZ_TAB_WORDS)[4:]
    assert result.intout(vdi.VDI_DEV_TAB_WORDS) == result.linea("DEV_TAB"), "init_wk answers the tables as patched"


@pytest.mark.parametrize("mode", MODES)
def test_the_ram_fonts_are_the_rom_s_and_mono_makes_the_8x16_the_default(mode):
    result = opnwk(mode)
    headers = {vdi.FONT_RAM_8X8: vdi.FONT_ROM_8X8, vdi.FONT_RAM_8X16: vdi.FONT_ROM_8X16}
    flags = {at: vdi.read_field(BASE_IMAGE, "FONT", "FLAGS", rom) for at, rom in headers.items()}
    if mode == "mono":
        flags = {vdi.FONT_RAM_8X8: flags[vdi.FONT_RAM_8X8] ^ vdi.FONT_FLAG_DEFAULT_MASK,
                 vdi.FONT_RAM_8X16: flags[vdi.FONT_RAM_8X16] | vdi.FONT_FLAG_DEFAULT_MASK}
    for at, rom in headers.items():
        copy = bytearray(BASE_IMAGE[rom:rom + vdi.FONT_HEADER_BYTES])
        copy[vdi.FONT_FLAGS:vdi.FONT_FLAGS + 2] = flags[at].to_bytes(2, "big")
        assert result.after(at, vdi.FONT_HEADER_BYTES) == bytes(copy)
    assert result.linea("FONT_RING")[vdi.LINEA_FONT_RING_BUILTIN] == vdi.FONT_RAM_8X8
    default = vdi.FONT_RAM_8X16 if mode == "mono" else vdi.FONT_RAM_8X8
    assert result.linea("DEF_FONT") == default, "text_init takes the LAST default along the ring"


@pytest.mark.parametrize("mode", MODES)
def test_the_physical_record_opens_alone_and_current(mode):
    result = opnwk(mode)
    dev, _inq = expected_tables(mode)
    assert result.contrl(vdi.CONTRL_HANDLE) == vdi.VDI_PHYS_HANDLE
    assert result.workstation("HANDLE") == vdi.VDI_PHYS_HANDLE
    assert result.workstation("NEXT") == 0
    assert result.linea("CUR_WORK") == vdi.VDI_PHYS_WORK
    assert result.workstation("XMX_CLIP") == dev[vdi.VDI_DEV_TAB_MAX_X_INDEX], "init_wk ran over the patched table"
    assert result.after(vdi.VIRTUAL_WORK_AT, vdi.WS_BYTES) == bytes([vdi.FILL]) * vdi.WS_BYTES
    assert vdi.signed_word(result.linea("LINE_CW")) == -1


@pytest.mark.parametrize("mode", MODES)
def test_the_inputs_are_reset_and_the_mouse_hidden_once_and_centred(mode):
    result = opnwk(mode)
    dev, _inq = expected_tables(mode)
    assert [result.linea(name) for name in ("LOC_MODE", "VAL_MODE", "CHC_MODE", "STR_MODE")] == [0] * 4
    assert result.linea("M_HID_CT") == 1
    assert (result.linea("GCURX"), result.linea("GCURY")) == (dev[vdi.VDI_DEV_TAB_MAX_X_INDEX] // 2,
                                                              dev[vdi.VDI_DEV_TAB_MAX_Y_INDEX] // 2)
    assert result.linea("USER_TIM") == addrs.VDI_ROM_NOP, "init_timer_mouse ran"


@pytest.mark.parametrize("mode", MODES)
def test_req_col_holds_the_realized_colour_of_every_index(mode):
    """One vq_color per colour DEV_TAB[13] counts, each reading the palette register its index maps to; the rest of
    REQ_COL left as it was. The caller's three pointers are put back."""
    _mode_byte, planes = MODES[mode]
    result = opnwk(mode)
    colours = expected_tables(mode)[0][vdi.VDI_DEV_TAB_COLOURS_INDEX]
    expected = [gun for index in range(colours) for gun in realized(index, planes)]
    expected += [vdi.STALE_WORD] * (vdi.VDI_REQ_COL_WORDS - len(expected))
    assert result.linea("REQ_COL") == expected
    assert [result.linea(name) for name in ("CONTRL", "INTIN", "INTOUT")] == [vdi.CONTRL_AT, vdi.INTIN_AT, vdi.INTOUT_AT]
    palette_reads = [event for event in result.info["regs"]["io_events"] if event[0] != addrs.SHIFTER_RESOLUTION]
    assert len(palette_reads) == colours


def test_medium_asked_in_medium_keeps_it():
    result = ws.run_opnwk(addrs.SHIFTER_MODE_MEDIUM, ws.open_intin(device=3), MEDIUM_PLANES)
    assert result.linea("DEV_TAB")[vdi.VDI_DEV_TAB_COLOURS_INDEX] == H["VDI_OPNWK_MEDIUM_COLOURS"]


def test_the_tables_are_copied_before_intin_is_read():
    """intin laid over DEV_TAB: setres reads DEV_TAB[0] (319, not 1 or 3 — low) and init_wk DEV_TAB[1..10] as the
    attributes, so a line type of DEV_TAB[1] = 199 is out of range and stored 0 — the defaults were copied first."""
    result = opnwk("low", pokes=vdi.linea_pokes(INTIN=vdi.LINEA_DEV_TAB))
    assert vdi.signed_word(result.workstation("LINE_INDEX")) == 0
    assert vdi.signed_word(result.workstation("XFM_MODE")) == vdi.rom_word(vdi.VDI_DEV_TAB_DEFAULT
                                                                          + H["VDI_OPEN_XFM_MODE"] * vdi.WORD_BYTES)


# ---- the two switching arms: a halt inside Setscreen, everything before it stored -----------------------------------
SWITCHING = ((addrs.SHIFTER_MODE_LOW, 3, addrs.SHIFTER_MODE_MEDIUM, LOW_PLANES),
             (addrs.SHIFTER_MODE_MEDIUM, 2, addrs.SHIFTER_MODE_LOW, MEDIUM_PLANES))
STACK_BAND = range(emu.STACK_GUARD_LO, emu.STACK_BAND_HI)
# ...and `savptr`, which the ROM's XBIOS entry has moved down by the register frame it saved and its exit would put
# back: in flight at the checkpoint, where the candidate, halting in Setscreen's C, never moved it — so it is left out
# of the compare on the ROM's side ALONE: the candidate's must still be the staged one.
IN_FLIGHT = range(addrs.SYSVAR_SAVPTR, addrs.SYSVAR_SAVPTR + vdi.LONG_BYTES)


@pytest.mark.parametrize("mode_byte,device,mode,planes", SWITCHING)
def test_a_resolution_change_halts_after_the_tables_and_before_anything_else(mode_byte, device, mode, planes):
    pokes = ws.opnwk_pokes(ws.open_intin(device=device), planes)
    returncode, stderr, image = vdi_helpers.refusal_over("vdi_v_opnwk", pokes, screen.io_shifter(mode_byte))
    assert returncode != 0
    assert f"Setscreen's resolution change to {mode}:" in stderr, stderr
    final, _writes, left = emu.run(bytearray(vdi.make_image(pokes)), addrs.VDI_ROM_V_OPNWK,
                                   stop_pc=addrs.XBIOS_SETSCREEN_RESOLUTION_ARM, io_seed=screen.io_shifter(mode_byte))
    assert left["d0"] == addrs.XBIOS_SETSCREEN, "the ROM did not stop inside Setscreen's resolution arm"
    differing = differing_addresses(memoryview(image), memoryview(final), ((0, len(image)),),
                                    lambda at: at in STACK_BAND or at in IN_FLIGHT)
    assert not differing, f"{len(differing)} byte(s) differ from the ROM's at the switch, the first at {differing[0]:#x}"
    staged = vdi.make_image(pokes)
    assert [image[at] for at in IN_FLIGHT] == [staged[at] for at in IN_FLIGHT], "the candidate moved savptr"
    assert image[vdi.FONT_RAM_8X16:vdi.FONT_RAM_8X16 + 2] == bytes(BASE_IMAGE[vdi.FONT_ROM_8X16:vdi.FONT_ROM_8X16 + 2])
    assert image[vdi.LINEA_REQ_COL:vdi.LINEA_REQ_COL + 2] == vdi.pack_words(vdi.STALE_WORD), "nothing after setres"


# ---- the rows Tier 3 prices ---------------------------------------------------------------------------------------
# Each mode kept, GEM's open: low reads sixteen palette registers, the worst.
for _mode, (_mode_byte, _planes) in MODES.items():
    vdi.register(f"vdi_v_opnwk, {_mode} kept", addrs.VDI_ROM_V_OPNWK, ws.opnwk_pokes(planes=_planes),
                 io_seed=ws.opnwk_io(_mode_byte))
