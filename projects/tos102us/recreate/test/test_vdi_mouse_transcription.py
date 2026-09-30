"""`src/vdi/mouse.S` — the mouse and cursor routines as the ROM wrote them, which the target build ships because
their C measures over Tier 3's 1.10 bar (`include/transcribed.h`).

Two claims hold it, neither of which needs the C: its WORDS are the ROM's, region by region, save the
references that measure to where mouse.S itself is linked (each relocated to its exact value); and it BEHAVES as
the ROM over the batteries' own cases — the same image, the whole register file and the same traffic, through
Tier 3's transcription relation (`transcription.run_transcription`), the fragment pointers a draw leaves cleared on both
sides (`vdi_mouse.CODE_POINTERS`).

THE STRICT MUTATION SWEEP over mouse.S's behaviour cases: one survivor, clamp_mouse's high bound `ble` as
`blt`, EQUIVALENT (a position AT the bound is stored as the bound). Its low bound's `bge` is told from `bgt`
only by x = 0 against a negative DEV_TAB[0] (`test_clamp_mouse`).
"""

import pytest

from harness import addrs

import test_vdi_helpers_input as helpers_input_cases
import test_vdi_input as input_cases
import test_vdi_mouse as mouse_cases
import test_vdi_sprite as sprite_cases
import transcription
import vdi
import vdi_mouse as mouse
from case import merge_pokes

# ---- the words -------------------------------------------------------------------------------------------
# The three VDI vector exchanges ($fcff68..$fcffaf), whose C ships: `mouse.S` keeps their SPACE and not
# their bytes, so the pin skips them — and the VBL's `bsr.s` across them, pinned in the first region, is
# what holds the second where the ROM has it.
REGIONS = (
    transcription.pinned_region(0xFCFE28, addrs.VDI_ROM_VEX_BUTV, "VDI_ROM_MOUSE_ISR",
                                ("VDI_ROM_CLAMP_MOUSE", "VDI_ROM_DEFAULT_USER_CUR", "VDI_ROM_VBL_DRAW_CURSOR")),
    transcription.pinned_region(addrs.LINEA_ROM_DRAW_SPRITE, 0xFD0346, "LINEA_ROM_DRAW_SPRITE",
                                ("LINEA_ROM_UNDRAW_SPRITE", "LINEA_ROM_HIDE_MOUSE", "VDI_ROM_SHOW_CURSOR", "VDI_ROM_VSC_FORM")),
    transcription.pinned_region(0xFCA7C0, 0xFCA7CA, "VDI_ROM_POLL_CHOICE", ()),
    transcription.pinned_region(0xFCA88A, 0xFCA914, "VDI_ROM_POLL_LOCATOR", ()),
)
_OWN = "LINEA_ROM_DRAW_SPRITE"
_FRAGMENT = "an absolute address of one of draw_sprite's own fragments, which names mouse.S's"
_SPREAD_LEA = (0xFD0034, 0xFD0042)                       # `lea (fragment).l,a3`, ror and rol
_ROW_TABLE = range(0xFD007C, 0xFD0094, 4)                # (store, row loop) per clip
_OP_TABLE = range(0xFD00C8, 0xFD00E8, 4)                 # the eight combines
RELOCATED = {
    0xFD0028: transcription.Relocated(transcription.PC_RELATIVE, "LINEA_ROM_CONCAT",
                                      "draw_sprite's `bsr.w` to concat, which measures to where raster.S puts it"),
    **{at: transcription.Relocated(transcription.ABSOLUTE, _OWN, f"a `lea` of a spread fragment: {_FRAGMENT}") for at in _SPREAD_LEA},
    **{at: transcription.Relocated(transcription.ABSOLUTE, _OWN, f"the clip table: {_FRAGMENT}") for at in _ROW_TABLE},
    **{at: transcription.Relocated(transcription.ABSOLUTE, _OWN, f"the combine table: {_FRAGMENT}") for at in _OP_TABLE},
}


def test_the_regions_are_where_the_rom_s_routines_are():
    assert (REGIONS[0].lo, REGIONS[1].lo, REGIONS[2].lo, REGIONS[3].lo) == (
        addrs.VDI_ROM_MOUSE_ISR, addrs.LINEA_ROM_DRAW_SPRITE, addrs.VDI_ROM_POLL_CHOICE, addrs.VDI_ROM_POLL_LOCATOR)
    assert REGIONS[2].hi == addrs.VDI_ROM_POLL_KEY and REGIONS[3].hi == 0xFCA914


@pytest.mark.parametrize("region", REGIONS, ids=[f"${region.lo:x}" for region in REGIONS])
def test_each_region_is_the_rom_s_words(region):
    transcription.assert_transcribed(region, relocated=RELOCATED)


# ---- the behaviour, over the batteries' own cases ---------------------------------------------------------
_FG, _BG = sprite_cases.ALL_REPLACE_OPS


@pytest.mark.parametrize("where", ((101, 51), (2, 51), (318, 90), (100, 3), (100, 198), (160 + 11, 100), (160 + 12, 100),
                                   (304 + 4, 100), (100, 184 + 6)))
@pytest.mark.parametrize("planes", (1, 0, -1))
def test_draw_sprite(where, planes):
    pokes = sprite_cases.draw_pokes(fg=_FG, bg=_BG, planes=planes, hot_x=4, hot_y=6)
    mouse.run_transcription("LINEA_ROM_DRAW_SPRITE", pokes, mouse.sprite_registers(*where))


def test_draw_sprite_stepping_by_width():
    pokes = merge_pokes(sprite_cases.draw_pokes(fg=_FG, bg=_BG), vdi.linea_pokes(WIDTH=152))
    mouse.run_transcription("LINEA_ROM_DRAW_SPRITE", pokes, mouse.sprite_registers(150, 60))


@pytest.mark.parametrize("resolution", ("medium", "high"))
def test_draw_sprite_in_one_and_two_planes(resolution):
    pokes = sprite_cases.draw_pokes(mouse.RESOLUTIONS[resolution], fg=_FG, bg=_BG)
    mouse.run_transcription("LINEA_ROM_DRAW_SPRITE", pokes, mouse.sprite_registers(333, 111))


@pytest.mark.parametrize("planes", (1, 2, 3, 4))
@pytest.mark.parametrize("long_rows", (False, True))
def test_undraw_sprite(planes, long_rows):
    status = sprite_cases.VALID | (sprite_cases.LONG_ROWS if long_rows else 0)
    pokes = merge_pokes(mouse.canvas_pokes(), vdi.linea_pokes(PLANES=planes),
                        sprite_cases.save_block(7, vdi.SCREEN.base + 160 * 20 + 16, status, sprite_cases.AREA))
    mouse.run_transcription("LINEA_ROM_UNDRAW_SPRITE", pokes, {"a2": mouse.SAVE_BLOCK_AT})


def test_undraw_sprite_with_nothing_saved():
    mouse.run_transcription("LINEA_ROM_UNDRAW_SPRITE", mouse.save_block_pokes(fill=sprite_cases.NOTHING_SAVED), {"a2": mouse.SAVE_BLOCK_AT})


@pytest.mark.parametrize("depth", (0, 1, 2))
def test_hide_and_show(depth):
    mouse.run_transcription("LINEA_ROM_HIDE_MOUSE", vdi.linea_pokes(M_HID_CT=depth, CUR_FLAG=0x5B))
    pokes = merge_pokes(vdi.linea_pokes(M_HID_CT=depth, GCURX=40, GCURY=30), mouse.canvas_pokes())
    mouse.run_transcription("VDI_ROM_SHOW_CURSOR", pokes)


def test_show_at_the_overflowing_depth():
    mouse.run_transcription("VDI_ROM_SHOW_CURSOR", vdi.linea_pokes(M_HID_CT=0x8000))


@pytest.mark.parametrize("colours", ((3, 12), (-1, 0x7FFF), (16, -16), (0x8000, -32752)))
def test_vsc_form(colours):
    intin = (0xFFFB, 0x1C, 4, colours[0] & 0xFFFF, colours[1] & 0xFFFF) + mouse.RANDOM_ROWS
    mouse.run_transcription("VDI_ROM_VSC_FORM", mouse_cases.call("VDI_ROM_VSC_FORM", intin))


def test_vsc_form_over_its_own_form():
    pokes = merge_pokes(mouse_cases.call("VDI_ROM_VSC_FORM"), vdi.linea_pokes(
        INTIN=vdi.LINEA_M_POS_HX, M_POS_HX=3, M_POS_HY=5, M_PLANES=1, M_CDB_BG=2, M_CDB_FG=6, MASK_FORM=mouse.RANDOM_ROWS))
    mouse.run_transcription("VDI_ROM_VSC_FORM", pokes)


def isr_pokes(header, dx, dy, routines, **state):
    return merge_pokes(mouse_cases.isr_pokes(routines, **state), mouse_cases.packet(header, dx, dy),
                       mouse.staged(routines))


@pytest.mark.parametrize("header,dx,dy,stat", ((0xFA, 3, -2, 0), (0xF8, -1, 1, 0), (0xF8, 0, 0, 0x21),
                                               (0xF0, 5, 5, 0), (0xF9, 0, 0, 0), (0xF8, 0, -3, 0)))
def test_the_isr(header, dx, dy, stat):
    routines = mouse_cases.isr_routines(mouse_cases.BUTTON_ANSWER, mouse_cases.MOTION_ANSWER)
    mouse.run_transcription("VDI_ROM_MOUSE_ISR", isr_pokes(header, dx, dy, routines, stat=stat),
                            {"a0": mouse.PACKET_AT, **mouse_cases.ENTRY})


def test_the_isr_with_the_default_cursor_routine():
    routines = mouse_cases.isr_routines(mouse_cases.BUTTON_ANSWER, default_cursor=True)
    mouse.run_transcription("VDI_ROM_MOUSE_ISR", isr_pokes(0xFA, 7, 7, routines),
                            {"a0": mouse.PACKET_AT, **mouse_cases.ENTRY})


def test_the_isr_under_a_held_lock():
    mouse.run_transcription("VDI_ROM_MOUSE_ISR", isr_pokes(0xFA, 7, 7, mouse_cases.isr_routines(), flag=1),
                            {"a0": mouse.PACKET_AT, **mouse_cases.ENTRY})


@pytest.mark.parametrize("hidden", (0, 1))
def test_default_user_cur(hidden):
    mouse.run_transcription("VDI_ROM_DEFAULT_USER_CUR", vdi.linea_pokes(M_HID_CT=hidden), {"d0": 0x1234_0102, "d1": 7})


@pytest.mark.parametrize("flag,held", ((0x81, 0), (0x80, 0), (0x01, 1)))
def test_the_vbl(flag, held):
    pokes = vdi.linea_pokes(CUR_FLAG=flag, CUR_X=40, CUR_Y=20, MOUSE_FLAG=held)
    mouse.run_transcription("VDI_ROM_VBL_DRAW_CURSOR", pokes)


# clamp_mouse, which mouse.S carries because the ISR's `bsr.s` reaches it: the C battery's shapes live in
# `test_vdi_helpers_input.py`; this is the one that tells `bge` from `bgt` at the low bound — x = 0 against a
# NEGATIVE DEV_TAB[0], which the ROM clamps DOWN to it.
@pytest.mark.parametrize("x, y, dev_tab", ((0, 3, (-5, 399)), (-1, 400, (639, 399))))
def test_clamp_mouse(x, y, dev_tab):
    mouse.run_transcription("VDI_ROM_CLAMP_MOUSE", vdi.linea_pokes(DEV_TAB=list(dev_tab)),
                            helpers_input_cases.clamp_registers(x, y))


def test_poll_choice():
    mouse.run_transcription("VDI_ROM_POLL_CHOICE", input_cases.machine(), {"d0": 0xDEAD_BEEF})


@pytest.mark.parametrize("status,keys", ((0x40, ()), (0x80, ()), (0xE7, ()), (0x00, (input_cases.A_KEY,)), (0x21, ()),
                                         (0x03, ())))
def test_poll_locator(status, keys):
    pokes = input_cases.machine(merge_pokes(mouse.keys_pokes(*keys), vdi.linea_pokes(CUR_MS_STAT=status)))
    mouse.run_transcription("VDI_ROM_POLL_LOCATOR", pokes)


# ---- the rows Tier 3 prices: the worst realistic case of each ------------------------------------------------
mouse.register_transcription("LINEA_ROM_DRAW_SPRITE", "four planes, two groups",
                             sprite_cases.draw_pokes(fg=_FG, bg=_BG, hot_x=1, hot_y=1), mouse.sprite_registers(101, 51))
mouse.register_transcription("LINEA_ROM_DRAW_SPRITE", "four planes, clipped left",
                             sprite_cases.draw_pokes(fg=_FG, bg=_BG, hot_x=6, hot_y=1), mouse.sprite_registers(2, 51))
mouse.register_transcription("LINEA_ROM_DRAW_SPRITE", "one plane, by xor",
                             sprite_cases.draw_pokes(mouse.HIGH, fg=1, bg=1, planes=-1), mouse.sprite_registers(300, 200))
mouse.register_transcription("LINEA_ROM_UNDRAW_SPRITE", "four planes, long rows", merge_pokes(
    mouse.canvas_pokes(), sprite_cases.save_block(16, vdi.SCREEN.base + 160 * 50 + 48,
                                                  sprite_cases.VALID | sprite_cases.LONG_ROWS, sprite_cases.AREA)),
    {"a2": mouse.SAVE_BLOCK_AT})
mouse.register_transcription("LINEA_ROM_UNDRAW_SPRITE", "nothing saved", mouse.save_block_pokes(fill=sprite_cases.NOTHING_SAVED),
                             {"a2": mouse.SAVE_BLOCK_AT})
mouse.register_transcription("LINEA_ROM_HIDE_MOUSE", "the arrow removed", {})
mouse.register_transcription("LINEA_ROM_HIDE_MOUSE", "already hidden", vdi.linea_pokes(M_HID_CT=1))
mouse.register_transcription("VDI_ROM_SHOW_CURSOR", "drawn",
                             merge_pokes(vdi.linea_pokes(M_HID_CT=1, GCURX=40, GCURY=30), mouse.canvas_pokes()))
mouse.register_transcription("VDI_ROM_SHOW_CURSOR", "still hidden", vdi.linea_pokes(M_HID_CT=2))
mouse.register_transcription("VDI_ROM_VSC_FORM", "a form", mouse_cases.call("VDI_ROM_VSC_FORM", mouse_cases.FORM_INTIN))
mouse.register_transcription("VDI_ROM_DEFAULT_USER_CUR", "queued", {}, {"d0": 10, "d1": 20})
mouse.register_transcription("VDI_ROM_VBL_DRAW_CURSOR", "the arrow moved", vdi.linea_pokes(CUR_FLAG=1, CUR_X=40, CUR_Y=20))
mouse.register_transcription("VDI_ROM_VBL_DRAW_CURSOR", "nothing queued", vdi.linea_pokes(CUR_FLAG=0))
_ISR = {"a0": mouse.PACKET_AT, **mouse_cases.ENTRY}
mouse.register_transcription("VDI_ROM_MOUSE_ISR", "a button and motion", isr_pokes(
    0xFA, 3, -2, mouse_cases.isr_routines(mouse_cases.BUTTON_ANSWER, default_cursor=True)), _ISR)
mouse.register_transcription("VDI_ROM_MOUSE_ISR", "motion only", isr_pokes(
    0xF8, -1, 1, mouse_cases.isr_routines(default_cursor=True)), _ISR)
mouse.register_transcription("VDI_ROM_MOUSE_ISR", "not a mouse packet", isr_pokes(
    0xF0, 0, 0, mouse_cases.isr_routines()), _ISR)
mouse.register_transcription("VDI_ROM_POLL_CHOICE", "the stub", input_cases.machine(), {"d0": input_cases.MONO})
mouse.register_transcription("VDI_ROM_POLL_LOCATOR", "motion", input_cases.machine(
    merge_pokes(mouse.keys_pokes(), vdi.linea_pokes(CUR_MS_STAT=0x21))))
mouse.register_transcription("VDI_ROM_POLL_LOCATOR", "a button", input_cases.machine(vdi.linea_pokes(CUR_MS_STAT=0x40)))
