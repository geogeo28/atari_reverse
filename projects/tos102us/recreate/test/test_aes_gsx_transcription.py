"""The VDI binding's atoms the target build ships as the ROM's own instructions (`src/aes/gsx.S`): gsx2, gsx_ncode,
gsx_1code, gsx_mon and gsx_fix.

Their C (`src/aes/gsx.c`) is what every Tier 1 case proves (`test_aes_gsx.py`); it measures over the 1.10 bar on its
own cycles (`bench/tier3.py`, mechanism (V); gsx_1code's at 1.40, and it is gsx_mon's `bsr.w` callee as well) — so by
the user's rule the target carries the ROM's code. Two claims hold it: its BYTES are the ROM's, every one of four regions (two
words RELOCATED to where their targets are linked), and it BEHAVES as the ROM — the image, the screen and the whole
register file — through Tier 3's transcription relation, over the C battery's own machine and shapes. gsx2's `trap #2`
is the machine's on both sides: the snapshot's vector, the ROM's VDI.

THE CALLER. `transcription.run_transcription` enters both sides at a staged caller that jumps through the routine
longword at `abi.FIRST_ARG`; an Alcyon frame is staged above it and pushed a longword at a time by the rectangle
helpers' frame caller (`test_aes_rect_transcription.frame_caller_stub`), staged in a pool of this battery's own. A
frame of an odd number of words (gsx_ncode's three) is pushed with one word of padding above it, which the routine
never reads.
"""
import pytest

from harness import BASE_IMAGE, addrs

import abi
import aes
import aes_gsx as gsx
import test_aes_gsx as battery
import test_aes_rect_transcription as rect_transcription
import transcription
from case import merge_pokes
from opcodes import RTS
from transcription import ABSOLUTE, PC_RELATIVE, Relocated

# ---- the byte pin ---------------------------------------------------------------------------------------------------
# Each routine's length to its last `rts` (`test_each_region_ends_on_the_rom_s_own_rts`): gsx2 runs up to mul_div.
GSX_1CODE_BYTES = 0x18                  # $fe87f0..$fe8807
GSX_MON_BYTES = 0x20                    # $fe8a8e..$fe8aad
GSX_FIX_BYTES = 0x3C                    # $fda992..$fda9cd
GSX2_REGION = transcription.pinned_region(addrs.AES_ROM_GSX2, addrs.AES_ROM_MUL_DIV, "AES_ROM_GSX2")
NCODE_REGION = transcription.pinned_region(addrs.AES_ROM_GSX_NCODE, addrs.AES_ROM_GSX_1CODE + GSX_1CODE_BYTES,
                                           "AES_ROM_GSX_NCODE", ("AES_ROM_GSX_1CODE",))
MON_REGION = transcription.pinned_region(addrs.AES_ROM_GSX_MON, addrs.AES_ROM_GSX_MON + GSX_MON_BYTES, "AES_ROM_GSX_MON")
FIX_REGION = transcription.pinned_region(addrs.AES_ROM_GSX_FIX, addrs.AES_ROM_GSX_FIX + GSX_FIX_BYTES, "AES_ROM_GSX_FIX")
REGIONS = {"gsx2": GSX2_REGION, "gsx_ncode and gsx_1code": NCODE_REGION, "gsx_mon": MON_REGION, "gsx_fix": FIX_REGION}

NCODE_JUMPS_TO_GSX2 = 0xFE87EC          # the operand of gsx_ncode's `jmp $fecb5a.l`
MON_CALLS_1CODE = 0xFE8AA0              # ...and the displacement of gsx_mon's `bsr.w $fe87f0`
RELOCATED = {
    NCODE_JUMPS_TO_GSX2: Relocated(ABSOLUTE, "AES_ROM_GSX2", "gsx_ncode's tail call of gsx2, where the .S links it"),
    MON_CALLS_1CODE: Relocated(PC_RELATIVE, "AES_ROM_GSX_NCODE", "gsx_mon's call of gsx_1code, into its region"),
}


@pytest.mark.parametrize("region", sorted(REGIONS))
def test_the_transcription_is_the_rom_s_bytes_exactly(region):
    """THE BYTE PIN: every word the ROM's but the two references into another region, each the value its target's
    place in the blob gives — gsx_ncode's `jmp` spelt as the ROM's absolute form (`m68k_encodings.h`)."""
    transcription.assert_transcribed(REGIONS[region], relocated=RELOCATED)


def test_each_region_ends_on_the_rom_s_own_rts():
    """Every region stops at an `rts`: gsx2's the word before mul_div, gsx_1code's, gsx_mon's, gsx_fix's form arm's."""
    for region in REGIONS.values():
        assert bytes(BASE_IMAGE[region.hi - len(RTS):region.hi]) == RTS, f"${region.lo:x}..${region.hi:x}"


# ---- the frame callers ----------------------------------------------------------------------------------------------
# One caller per distinct frame size, every battery entering through `entered` sharing them (five in use at wave 2:
# frames of 0, 1, 2, 3 and 6 longwords). `frame_caller_stub(n)` is 16 + 4n bytes, so the stride holds a frame of up to
# MAX_FRAME_LONGS, and the band one caller for every size 0..MAX_FRAME_LONGS, with a spare.
MAX_FRAME_LONGS = 8
CALLER_STRIDE = 0x30
assert len(rect_transcription.frame_caller_stub(MAX_FRAME_LONGS)[0]) <= CALLER_STRIDE
CALLERS_BYTES = (MAX_FRAME_LONGS + 1 + 1) * CALLER_STRIDE
CALLERS_OFFSET = gsx.BAND_OFFSET + gsx.BAND_BYTES     # right above the door's band
CALLERS_AT = aes.SPAN.claim(aes.WINDOW_AT + CALLERS_OFFSET, CALLERS_BYTES, "test/test_aes_gsx_transcription.py: frame callers")
POOL = transcription.CallerPool(CALLERS_AT, CALLERS_AT + CALLERS_BYTES, CALLER_STRIDE,
                                grow="test_aes_gsx_transcription.MAX_FRAME_LONGS (and CALLER_STRIDE past 8 longwords)")
FRAME_ARGUMENTS_AT = rect_transcription.FRAME_ARGUMENTS_AT


def frame_caller(longwords):
    return POOL.staged(("frame", longwords), lambda: rect_transcription.frame_caller_stub(longwords))


def entered(name, arguments, pokes):
    """`pokes` with `name`'s Alcyon frame of `arguments` where its frame caller reads it (padded to a longword), and
    that caller."""
    frame = aes.alcyon_frame(name, *arguments).get(abi.FIRST_ARG, b"")
    frame += bytes(-len(frame) % aes.LONG_BYTES)
    return frame_caller(len(frame) // aes.LONG_BYTES), merge_pokes(pokes, {FRAME_ARGUMENTS_AT: frame} if frame else None)


def run(name, arguments, pokes):
    caller, staged = entered(name, arguments, pokes)
    return transcription.run_transcription(name, staged, caller=caller)


def register(label, name, arguments, pokes):
    caller, staged = entered(name, arguments, pokes)
    return transcription.register_transcription(name, label, staged, caller=caller)


# ---- the relation over the C battery's shapes --------------------------------------------------------------------
NEST = battery.nest_pokes
CASES = {
    ("AES_ROM_GSX2", "vsl_color 3"): ((), gsx.machine(battery.vsl_color_pokes(3))),
    ("AES_ROM_GSX2", "a handle no workstation has"):
        ((), gsx.machine(merge_pokes(battery.vsl_color_pokes(3), aes.field_pokes("AES", GSX_HANDLE=battery.UNKNOWN_HANDLE)))),
    ("AES_ROM_GSX_NCODE", "vqt_attributes"): ((addrs.VDI_ROM_VQT_ATTRIBUTES_OPCODE, 0, 0), gsx.machine()),
    ("AES_ROM_GSX_NCODE", "v_gtext, three characters"):
        (battery.NCODE_CALLS["v_gtext, three characters"][:3], gsx.machine(battery.NCODE_CALLS["v_gtext, three characters"][3])),
    ("AES_ROM_GSX_1CODE", "vswr_mode 3"): (battery.ONE_WORD_CALLS["vswr_mode 3 (XOR)"], gsx.machine()),
    ("AES_ROM_GSX_1CODE", "vsl_udsty $5555"): (battery.ONE_WORD_CALLS["vsl_udsty $5555"], gsx.machine()),
    ("AES_ROM_GSX_MON", "the nest unwound: v_show_c"): ((), gsx.machine()),
    ("AES_ROM_GSX_MON", "the nest still open"): ((), gsx.machine(NEST(2))),
    ("AES_ROM_GSX_MON", "no nest: wraps to -1"): ((), gsx.machine(NEST(0))),
    ("AES_ROM_GSX_FIX", "the screen"): ((gsx.mfdb_at(0), 0, 0, 0), gsx.machine(battery.STALE_MFDB)),
    ("AES_ROM_GSX_FIX", "an icon's form"): ((gsx.mfdb_at(0), gsx.form_at(0), 2, 16), gsx.machine(battery.STALE_MFDB)),
    ("AES_ROM_GSX_FIX", "a width that wraps"): ((gsx.mfdb_at(0), gsx.form_at(0), 0x2000, -1), gsx.machine(battery.STALE_MFDB)),
    ("AES_ROM_GSX_FIX", "over work_out"): ((aes.AES_GL_WS - aes.WORD_BYTES, 0, 0, 0), gsx.machine()),
    ("AES_ROM_GSX_FIX", "a form whose address's low word is 0"):
        ((gsx.mfdb_at(0), battery.WORD_ZERO_FORM, 2, 16), gsx.machine(battery.STALE_MFDB)),
}


@pytest.mark.parametrize("name,shape", sorted(CASES), ids=lambda value: value)
def test_the_transcription_behaves_as_the_rom(name, shape):
    arguments, pokes = CASES[(name, shape)]
    run(name, arguments, pokes)


def test_the_mfdb_pointer_s_top_byte_reaches_the_transcription_as_it_reaches_the_rom():
    run("AES_ROM_GSX_FIX", (gsx.mfdb_at(0) | aes.BUS_TAG, 0, 0, 0), gsx.machine(battery.STALE_MFDB))


for (_name, _shape), (_arguments, _pokes) in sorted(CASES.items()):
    register(_shape, _name, _arguments, _pokes)
