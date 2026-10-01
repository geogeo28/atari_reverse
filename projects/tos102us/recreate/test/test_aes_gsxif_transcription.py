"""gemgsxif's Line-F-free leaves the target build ships as the ROM's own instructions (`src/aes/gsxif.S`): gsx_mret,
ratinit, gsx_mxmy and gsx_button.

Their C (`src/aes/gsxif.c`) is what every Tier 1 case proves (`test_aes_gsxif.py`, `test_aes_gsxif_workstation.py`);
it measures over the 1.10 bar — the three leaves on the image pointer each global costs them, ratinit on its own
cycles (mechanism (V)) — so by the user's rule the target carries the ROM's code. Two claims hold it: its BYTES are
the ROM's, every one of three regions (ratinit's `bsr.w` RELOCATED to where gsx_1code is linked), and it BEHAVES as
the ROM — the image, the screen and the whole register file — through Tier 3's transcription relation, over the C
batteries' own machines and shapes, entered by `test_aes_gsx_transcription.py`'s frame callers.
"""
import pytest

from harness import BASE_IMAGE, addrs

import aes
import aes_gsx as gsx
import test_aes_gsx_transcription as atoms
import test_aes_gsxif as battery
import transcription
from case import merge_pokes
from opcodes import RTS
from transcription import PC_RELATIVE, Relocated

# ---- the byte pin ---------------------------------------------------------------------------------------------------
# Each region runs to its last routine's `rts` (`test_each_region_ends_on_the_rom_s_own_rts`).
RATINIT_BYTES = 0x14                    # $fe88e4..$fe88f7
BUTTON_BYTES = 0x08                     # $fe8a6a..$fe8a71
MRET_REGION = transcription.pinned_region(addrs.AES_ROM_GSX_MRET, addrs.AES_ROM_GSX_NCODE, "AES_ROM_GSX_MRET")
RATINIT_REGION = transcription.pinned_region(addrs.AES_ROM_RATINIT, addrs.AES_ROM_RATINIT + RATINIT_BYTES,
                                             "AES_ROM_RATINIT")
MXMY_REGION = transcription.pinned_region(addrs.AES_ROM_GSX_MXMY, addrs.AES_ROM_GSX_BUTTON + BUTTON_BYTES,
                                          "AES_ROM_GSX_MXMY", ("AES_ROM_GSX_BUTTON",))
REGIONS = {"gsx_mret": MRET_REGION, "ratinit": RATINIT_REGION, "gsx_mxmy and gsx_button": MXMY_REGION}

RATINIT_CALLS_1CODE = 0xFE88EC          # the displacement of ratinit's `bsr.w $fe87f0`
RELOCATED = {RATINIT_CALLS_1CODE: Relocated(PC_RELATIVE, "AES_ROM_GSX_NCODE", "ratinit's call of gsx_1code, into its region")}


@pytest.mark.parametrize("region", sorted(REGIONS))
def test_the_transcription_is_the_rom_s_bytes_exactly(region):
    """THE BYTE PIN: every word the ROM's but ratinit's `bsr.w` displacement, the value gsx_1code's place in the blob
    gives (it is in `gsx.S`'s gsx_ncode region)."""
    transcription.assert_transcribed(REGIONS[region], relocated=RELOCATED)


def test_each_region_ends_on_the_rom_s_own_rts():
    for region in REGIONS.values():
        assert bytes(BASE_IMAGE[region.hi - len(RTS):region.hi]) == RTS, f"${region.lo:x}..${region.hi:x}"


# ---- the relation over the C batteries' shapes --------------------------------------------------------------------
ANSWERS, LONG_BYTES = battery.ANSWERS, aes.LONG_BYTES
CASES = {
    ("AES_ROM_GSX_MRET", "both answers"): ((ANSWERS, ANSWERS + LONG_BYTES), gsx.machine(battery.STALE_ANSWERS)),
    ("AES_ROM_GSX_MRET", "the address over gl_mlen"): ((aes.AES_GL_MLEN, ANSWERS), gsx.machine(merge_pokes(
        battery.STALE_ANSWERS, aes.field_pokes("AES", GL_MLEN=battery.MLEN)))),
    ("AES_ROM_GSX_MXMY", "both answers"): ((ANSWERS, ANSWERS + aes.WORD_BYTES), gsx.machine(merge_pokes(
        battery.STALE_ANSWERS, battery.STATE_POKES))),
    ("AES_ROM_GSX_MXMY", "x over yrat"): ((battery.STATE_FIELDS[1], ANSWERS), gsx.machine(battery.STATE_POKES)),
    ("AES_ROM_GSX_BUTTON", "both buttons"): ((), gsx.machine(aes.field_pokes("AES", BUTTON=3))),
    ("AES_ROM_RATINIT", "the cursor shown again"): ((), gsx.machine()),
    ("AES_ROM_RATINIT", "over the snapshot's drawn cursor"): ((), gsx.shown_machine()),
}


@pytest.mark.parametrize("name,shape", sorted(CASES), ids=lambda value: value)
def test_the_transcription_behaves_as_the_rom(name, shape):
    arguments, pokes = CASES[(name, shape)]
    atoms.run(name, arguments, pokes)


def test_the_pointers_top_bytes_reach_the_transcription_as_they_reach_the_rom():
    atoms.run("AES_ROM_GSX_MXMY", (ANSWERS | aes.BUS_TAG, (ANSWERS + aes.WORD_BYTES) | aes.BUS_TAG),
              gsx.machine(battery.STATE_POKES))


for (_name, _shape), (_arguments, _pokes) in sorted(CASES.items()):
    atoms.register(_shape, _name, _arguments, _pokes)
