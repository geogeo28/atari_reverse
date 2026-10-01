"""The graphics library's leaves the target build ships as the ROM's own instructions (`src/aes/gemgraf.S`): gr_inside,
gr_crack, gsx_gclip, gsx_chkclip and gsx_bxpts.

Their C (`src/aes/gemgraf.c`) is what every Tier 1 case proves (`test_aes_gemgraf.py`, `test_aes_gemgraf_gr.py`); it
measures over the 1.10 bar against these routines (gsx_bxpts at 2.07, gsx_chkclip at 1.99), so by the user's rule the
target carries the ROM's code. Two claims hold it: its BYTES are the ROM's, every one of four regions (no reference
leaves any of them), and it BEHAVES as the ROM — the image and the whole register file — through Tier 3's
transcription relation, over the C batteries' own machine and shapes. THE CALLER is the VDI binding atoms' frame
caller and its pool (`test_aes_gsx_transcription.run` / `.register`); a frame of an odd number of words is pushed with
one word of padding above it, which the routine never reads.
"""
import pytest

from harness import BASE_IMAGE, addrs

import aes
import aes_gsx as gsx
import test_aes_gemgraf as graf
import test_aes_gemgraf_gr as gr
import test_aes_gsx_transcription as atoms
import transcription
from case import merge_pokes
from opcodes import RTS
from test_aes_gemgraf import CHKCLIP, rect_at, rect_pokes

# ---- the byte pin ---------------------------------------------------------------------------------------------------
# Each region's length to its last `rts` (`test_each_region_ends_on_the_rom_s_own_rts`): gr_inside runs up to
# gr_rect, gr_crack to gr_gicon and gsx_bxpts to gsx_box; gsx_chkclip's last `rts` is the desk's helper's neighbour.
CHKCLIP_BYTES = 0x44                    # $fda864..$fda8a7
INSIDE_REGION = transcription.pinned_region(addrs.AES_ROM_GR_INSIDE, addrs.AES_ROM_GR_RECT, "AES_ROM_GR_INSIDE")
CRACK_REGION = transcription.pinned_region(addrs.AES_ROM_GR_CRACK, addrs.AES_ROM_GR_GICON, "AES_ROM_GR_CRACK")
CLIP_REGION = transcription.pinned_region(addrs.AES_ROM_GSX_GCLIP, addrs.AES_ROM_GSX_CHKCLIP + CHKCLIP_BYTES,
                                          "AES_ROM_GSX_GCLIP", ("AES_ROM_GSX_CHKCLIP",))
BXPTS_REGION = transcription.pinned_region(addrs.AES_ROM_GSX_BXPTS, addrs.AES_ROM_GSX_BOX, "AES_ROM_GSX_BXPTS")
REGIONS = {"gr_inside": INSIDE_REGION, "gr_crack": CRACK_REGION, "gsx_gclip and gsx_chkclip": CLIP_REGION,
           "gsx_bxpts": BXPTS_REGION}


@pytest.mark.parametrize("region", sorted(REGIONS))
def test_the_transcription_is_the_rom_s_bytes_exactly(region):
    """THE BYTE PIN: every word the ROM's — `and.w #imm,dN` spelt as the ROM's word (`m68k_encodings.h`)."""
    transcription.assert_transcribed(REGIONS[region])


def test_each_region_ends_on_the_rom_s_own_rts():
    for region in REGIONS.values():
        assert bytes(BASE_IMAGE[region.hi - len(RTS):region.hi]) == RTS, f"${region.lo:x}..${region.hi:x}"


# ---- the relation over the C batteries' shapes ---------------------------------------------------------------------
def clip_case(label):
    clip, rect, _answer = CHKCLIP[label]
    return (rect_at(0),), gsx.machine(merge_pokes(graf.clip_pokes(*clip), rect_pokes(*rect)))


CASES = {
    ("AES_ROM_GR_INSIDE", "in by 2"): ((rect_at(0), 2), gsx.machine(rect_pokes(40, 30, 100, 50))),
    ("AES_ROM_GR_INSIDE", "out by 2"): ((rect_at(0), -2), gsx.machine(rect_pokes(40, 30, 100, 50))),
    ("AES_ROM_GR_INSIDE", "twice the thickness wraps"): ((rect_at(0), 0x4000), gsx.machine(rect_pokes(0, 0, 0, 0))),
    ("AES_ROM_GR_CRACK", "replace"): ((0x11F3, *gr.CRACK_POINTERS), gsx.machine(graf.STALE_ANSWERS)),
    ("AES_ROM_GR_CRACK", "transparent"): ((0x1234, *gr.CRACK_POINTERS), gsx.machine(graf.STALE_ANSWERS)),
    ("AES_ROM_GR_CRACK", "every pointer one word"): ((0x12B4, *(gr.BORDER,) * 5), gsx.machine(graf.STALE_ANSWERS)),
    ("AES_ROM_GSX_GCLIP", "the clip out"): ((rect_at(0),), gsx.machine(rect_pokes(*[aes.STALE_WORD] * 4))),
    ("AES_ROM_GSX_GCLIP", "over the clip words"): ((aes.AES_GL_YCLIP,), gsx.machine()),
    ("AES_ROM_GSX_BXPTS", "a box's corners"): ((rect_at(0),), gsx.machine(rect_pokes(40, 30, 100, 50))),
    ("AES_ROM_GSX_BXPTS", "the right edge wraps"): ((rect_at(0),), gsx.machine(rect_pokes(0x7FF0, 10, 0x20, 0x8000))),
    **{("AES_ROM_GSX_CHKCLIP", label): clip_case(label) for label in CHKCLIP},
}


@pytest.mark.parametrize("name,shape", sorted(CASES), ids=lambda value: value)
def test_the_transcription_behaves_as_the_rom(name, shape):
    arguments, pokes = CASES[(name, shape)]
    atoms.run(name, arguments, pokes)


@pytest.mark.parametrize("name, arguments, pokes", (
    ("AES_ROM_GR_INSIDE", (rect_at(0) | aes.BUS_TAG, 2), rect_pokes(40, 30, 100, 50)),
    ("AES_ROM_GR_CRACK", (0x11F3, *(at | aes.BUS_TAG for at in gr.CRACK_POINTERS)), graf.STALE_ANSWERS),
    ("AES_ROM_GSX_GCLIP", (rect_at(0) | aes.BUS_TAG,), None),
    ("AES_ROM_GSX_CHKCLIP", (rect_at(0) | aes.BUS_TAG,), rect_pokes(30, 30, 10, 10)),
    ("AES_ROM_GSX_BXPTS", (rect_at(0) | aes.BUS_TAG,), rect_pokes(40, 30, 100, 50)),
), ids=("gr_inside", "gr_crack", "gsx_gclip", "gsx_chkclip", "gsx_bxpts"))
def test_a_tagged_pointer_reaches_the_transcription_as_it_reaches_the_rom(name, arguments, pokes):
    atoms.run(name, arguments, gsx.machine(pokes))


_ROWS = (("AES_ROM_GR_INSIDE", "in by 2"), ("AES_ROM_GR_CRACK", "replace"), ("AES_ROM_GR_CRACK", "transparent"),
         ("AES_ROM_GSX_GCLIP", "the clip out"), ("AES_ROM_GSX_CHKCLIP", "inside"),
         ("AES_ROM_GSX_CHKCLIP", "no clip width: everything"), ("AES_ROM_GSX_CHKCLIP", "x + w short of the clip"),
         ("AES_ROM_GSX_BXPTS", "a box's corners"))
for _name, _shape in _ROWS:
    atoms.register(_shape, _name, *CASES[(_name, _shape)])
