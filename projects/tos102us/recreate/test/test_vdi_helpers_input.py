"""The VDI's two INPUT register routines (`src/vdi/helpers.c`): clamp_mouse and get_kbshift.

Both are hand 68000 reached by `jsr` with a register contract, declared here once
(`vdi.declare_primitive`) — which is also how `bench/tier3.py` calls their cores. Each is entered with
junk in its answer registers' HIGH words, because the ROM writes only the low words and hands the
caller's high words back; the cores take the entry registers and return them whole.
"""
import pytest

from harness import addrs

import vdi
import vdi_helpers

CLAMP = "VDI_ROM_CLAMP_MOUSE"
KBSHIFT = "VDI_ROM_GET_KBSHIFT"

X_HIGH = 0x1234_0000
Y_HIGH = 0xFEDC_0000


def low(value):
    return value & 0xFFFF


# ---- clamp_mouse, $fcfedc --------------------------------------------------------------------------
# The captured screen is 320 x 200: DEV_TAB[0] and [1] are its last column and row.
LAST_X, LAST_Y = 319, 199


def clamp_registers(x, y):
    return {"d0": X_HIGH | low(x), "d1": Y_HIGH | low(y)}


def clamp_mouse(x, y, pokes=None):
    regs = vdi.run_primitive(CLAMP, clamp_registers(x, y), pokes or {}).info["regs"]
    assert (regs["d0"] & 0xFFFF_0000, regs["d1"] & 0xFFFF_0000) == (X_HIGH, Y_HIGH)
    return low(regs["d0"]), low(regs["d1"])


def test_the_captured_screen_is_the_one_the_clamp_cases_assume():
    result = vdi.run_primitive(CLAMP, clamp_registers(0, 0), {})
    assert result.linea("DEV_TAB")[:2] == [LAST_X, LAST_Y]


@pytest.mark.parametrize("x,y,clamped", (
    (160, 100, (160, 100)), (0, 0, (0, 0)), (LAST_X, LAST_Y, (LAST_X, LAST_Y)),
    (-1, 100, (0, 100)), (LAST_X + 1, 100, (LAST_X, 100)), (160, -1, (160, 0)),
    (160, LAST_Y + 1, (160, LAST_Y)), (-32768, 32767, (0, LAST_Y)), (32767, -32768, (LAST_X, 0)),
))
def test_clamp_mouse_holds_the_position_to_the_screen(x, y, clamped):
    assert clamp_mouse(x, y) == clamped


def test_clamp_mouse_reads_the_bounds_from_dev_tab():
    """A high-resolution DEV_TAB, and a NEGATIVE bound: 0 is past -5, so it is clamped DOWN to it."""
    assert clamp_mouse(700, 450, vdi.linea_pokes(DEV_TAB=[639, 399])) == (639, 399)
    assert clamp_mouse(0, 3, vdi.linea_pokes(DEV_TAB=[-5, 399])) == (low(-5), 3)


# ---- get_kbshift, $fca648 --------------------------------------------------------------------------
KBSHIFT_ENTRY_D0 = 0xC0DE_5A5A      # the low word is overwritten whole; the high word is the caller's


def kbshift_pokes(state):
    return {addrs.KBSHIFT: bytes([state])}


@pytest.mark.parametrize("state", (0x00, 0x01, 0x0F, 0x10, 0x35, 0x7F, 0xFF))
def test_get_kbshift_answers_the_four_modifier_bits(state):
    """Shifts, Control and Alternate; Caps Lock and the mouse-button bits above them are masked off,
    and the WHOLE low word is written (`andi.w`), not just the byte `move.b` loaded."""
    regs = vdi.run_primitive(KBSHIFT, {"d0": KBSHIFT_ENTRY_D0}, kbshift_pokes(state)).info["regs"]
    assert regs["d0"] == (KBSHIFT_ENTRY_D0 & 0xFFFF_0000) | (state & 0x0F)


# ---- the transcriptions (clamp_mouse in `src/vdi/mouse.S`, get_kbshift in `helpers.S`), same shapes ------

@pytest.mark.parametrize("x,y", ((160, 100), (-1, LAST_Y + 1), (LAST_X + 1, -1), (-32768, 32767), (LAST_X, 0)))
def test_clamp_mouse_transcription_behaves_as_the_rom(x, y):
    vdi_helpers.run_transcription(CLAMP, {}, clamp_registers(x, y))


@pytest.mark.parametrize("state", (0x00, 0x10, 0x35, 0xFF))
def test_get_kbshift_transcription_behaves_as_the_rom(state):
    vdi_helpers.run_transcription(KBSHIFT, kbshift_pokes(state), {"d0": KBSHIFT_ENTRY_D0})


# ---- the rows Tier 3 prices ------------------------------------------------------------------------
vdi.register("vdi_clamp_mouse, both clamped", addrs.VDI_ROM_CLAMP_MOUSE, {}, regs=clamp_registers(-3, LAST_Y + 9))
vdi.register("vdi_clamp_mouse, inside", addrs.VDI_ROM_CLAMP_MOUSE, {}, regs=clamp_registers(160, 100))
vdi.register("vdi_get_kbshift, the modifier keys", addrs.VDI_ROM_GET_KBSHIFT, kbshift_pokes(0x35), regs={"d0": KBSHIFT_ENTRY_D0})
# ...and the same rows for the `.S` the target build ships.
vdi_helpers.register_transcription(CLAMP, "both clamped", {}, clamp_registers(-3, LAST_Y + 9))
vdi_helpers.register_transcription(CLAMP, "inside", {}, clamp_registers(160, 100))
vdi_helpers.register_transcription(KBSHIFT, "the modifier keys", kbshift_pokes(0x35), {"d0": KBSHIFT_ENTRY_D0})
