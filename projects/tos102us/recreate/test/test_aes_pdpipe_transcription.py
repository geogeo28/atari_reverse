"""gemdosif's two leaves under pstart the target build ships as the ROM's own instructions (`src/aes/pdpipe.S`):
uda_insuper and psetup.

Their C (`src/aes/pdpipe.c`) is what every Tier 1 case proves (`test_aes_pdpipe.py`); it measures over the 1.10 bar —
uda_insuper 1.50, psetup 1.24, each the image pointer's floor on a routine of a few instructions — so by the user's
rule the target carries the ROM's code. Two claims hold it: its BYTES are the ROM's, every one of the one region, and
it BEHAVES as the ROM — the image and the whole register file — through Tier 3's transcription relation, over the C
battery's own machines.

NOTHING IS DROPPED HERE: both sides are entered from one staged caller with one register file, so the status register
psetup parks in its save word is the same word on both — the one place that word is compared (the drop,
`aes_event.SR_PSETUP_DROP`, is the C twin's, whose caller is another's).

THE CALLER is the VDI binding's frame caller (`test_aes_gsx_transcription.entered`): the Alcyon frame staged above the
routine's longword and pushed a longword at a time.
"""
import pytest

from harness import BASE_IMAGE, addrs

import aes
import aes_pdpipe as pp
import test_aes_gsx_transcription as frames
import test_aes_pdpipe as battery
import transcription
from opcodes import RTS

UDA_INSUPER, PSETUP = pp.UDA_INSUPER, pp.PSETUP
PSETUP_BYTES = 0x2C                     # $fe397a..$fe39a5, to its `rts`
REGION = transcription.pinned_region(addrs.AES_ROM_UDA_INSUPER, addrs.AES_ROM_PSETUP + PSETUP_BYTES,
                                     UDA_INSUPER, (PSETUP,))


def test_the_transcription_is_the_rom_s_bytes_exactly():
    """THE BYTE PIN: every word the ROM's — no reference leaves the region."""
    transcription.assert_transcribed(REGION, relocated={})


def test_the_region_is_the_two_routines_and_ends_on_psetup_s_rts():
    assert bytes(BASE_IMAGE[REGION.hi - len(RTS):REGION.hi]) == RTS
    assert bytes(BASE_IMAGE[addrs.AES_ROM_PSETUP - len(RTS):addrs.AES_ROM_PSETUP]) == RTS, "uda_insuper ends where psetup begins"


CASES = {
    (UDA_INSUPER, "the spare UDA"): ((battery.SPARE_UDA,), pp.running),
    (UDA_INSUPER, "the screen manager's, set already"): ((aes.AES_UDA1,), pp.running),
    (UDA_INSUPER, "on the bus"): ((battery.SPARE_UDA | aes.BUS_TAG,), pp.running),
    (PSETUP, "the spare PD"): ((pp.SPARE_PD, battery.CODE), pp.running),
    (PSETUP, "the PD on the bus, a PC with a top byte"): ((pp.SPARE_PD | aes.BUS_TAG, battery.CODE | aes.BUS_TAG), pp.running),
    (PSETUP, f"{pp.STAGED_APPLICATION}'s PD: a second frame under the first"):
        ((pp.SPARE_PD, battery.CODE), battery.with_the_application),
}


@pytest.mark.parametrize("name,shape", sorted(CASES), ids=lambda value: value)
def test_the_transcription_behaves_as_the_rom(name, shape):
    arguments, machine = CASES[(name, shape)]
    frames.run(name, arguments, machine())


# Tier 3's rows: each routine over the machine a caller hands it. The staged application's is Tier 1 only (the class:
# `test_aes_pdpipe.test_no_registered_row_runs_over_a_staged_application` reads this battery's rows too).
for (_name, _shape), (_arguments, _machine) in sorted(CASES.items()):
    if pp.STAGED_APPLICATION not in _shape:
        frames.register(_shape, _name, _arguments, _machine())
