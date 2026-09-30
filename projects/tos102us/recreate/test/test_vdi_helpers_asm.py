"""`src/vdi/helpers.S` — the hand-68000 helpers the target build ships as the ROM's own instructions.

Their C (`src/vdi/helpers.c`) is what every Tier 1 case proves; it measures over the 1.10 bar against
these routines (`bench/tier3.py`), so by the user's rule the target carries the ROM's code instead. Two
claims hold it: its BYTES are the ROM's, every one — checked here — and it BEHAVES as the ROM, image and
whole register file, through Tier 3's transcription relation over each routine's own Tier 1 cases (in
its battery, beside the C cases it mirrors).
"""
import pytest

from harness import BASE_IMAGE, addrs

import transcription
from opcodes import RTS

# Each routine's extent in the ROM: where the next routine starts. get_kbshift's last word is the `rts`
# the ROM ALSO enters as vdi_nop ($fca652), so its extent runs through that word. (clamp_mouse is not here:
# `mouse.S` carries it, in the mouse ISR's region, and pins it there.)
ROUTINE_BYTES = {
    "VDI_ROM_SORT_WORDS": 0x22,
    "VDI_ROM_SMUL_DIV": 0x32,
    "VDI_ROM_GET_KBSHIFT": 0x0C,
    "VDI_ROM_CLC_DDA": 0x32,
    "VDI_ROM_ACT_SIZ": 0x52,
    "VDI_ROM_GEMDOS_CALL": 0x10,
    "VDI_ROM_VR_TRNFM": 0xA0,
}
# ...and the extents the NEXT routine's own `addrs.h` name confirms.
FOLLOWED_BY = {"VDI_ROM_SORT_WORDS": "VDI_ROM_SMUL_DIV", "VDI_ROM_SMUL_DIV": "LINEA_ROM_CONCAT", "VDI_ROM_CLC_DDA": "VDI_ROM_ACT_SIZ",
               "VDI_ROM_GEMDOS_CALL": "VDI_ROM_FONT_BYTESWAP", "VDI_ROM_VR_TRNFM": "VDI_ROM_VS_COLOR"}


REGIONS = {name: transcription.pinned_region(getattr(addrs, name), getattr(addrs, name) + size, name)
           for name, size in ROUTINE_BYTES.items()}


@pytest.mark.parametrize("name", sorted(ROUTINE_BYTES))
def test_the_transcription_is_the_rom_s_bytes_exactly(name):
    """THE BYTE PIN: no word excused — where GNU as would choose another encoding, `helpers.S` spells the
    ROM's words (`m68k_encodings.h`)."""
    transcription.assert_transcribed(REGIONS[name])


@pytest.mark.parametrize("name,following", sorted(FOLLOWED_BY.items()))
def test_each_extent_ends_where_the_next_routine_begins(name, following):
    assert getattr(addrs, name) + ROUTINE_BYTES[name] == getattr(addrs, following)


def test_get_kbshift_ends_in_the_shared_rts():
    assert addrs.VDI_ROM_GET_KBSHIFT + ROUTINE_BYTES["VDI_ROM_GET_KBSHIFT"] - len(RTS) == addrs.VDI_ROM_NOP
    assert bytes(BASE_IMAGE[addrs.VDI_ROM_NOP:addrs.VDI_ROM_NOP + len(RTS)]) == RTS
