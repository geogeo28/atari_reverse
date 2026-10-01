"""VDI vr_trnfm (opcode 110, $fd2d32) and its two transposes, $fd2db4 (copy) and $fd2d80 (in place).

A DEVICE form interleaves its planes word by word — for each 16-pixel word, plane 0, 1, ... — and GEM's
STANDARD form lays one plane after another; each is the other transposed. The source MFDB's `stand`
says which it holds, and the DESTINATION MFDB's `stand` is set to the other (its other fields are the
caller's). When the two addresses are equal the ROM transposes IN PLACE by rotation, which is a
different routine with different loop bounds, so every shape runs both ways.

Entered as the dispatcher's `jsr` leaves the machine (`vdi.call_pokes`, the two MFDB pointers at
contrl[7..10]). Every form word is distinct (`form_word`), so a word landing one slot off is a wrong
value rather than a plausible one.
"""
import pytest

from harness import addrs

import case
import routines
import vdi
import vdi_helpers
import test_vdi_bus_pointers as bus

NAME = "VDI_ROM_VR_TRNFM"
SOURCE_MFDB = vdi.SOURCE_MFDB_AT
DESTINATION_MFDB = vdi.DESTINATION_MFDB_AT
SOURCE_AT = vdi_helpers.SOURCE_FORM_AT
DESTINATION_AT = vdi_helpers.DESTINATION_FORM_AT
FORM_WORDS = vdi_helpers.RASTER_FORM_BYTES // vdi_helpers.WORD_BYTES
DEVICE, STANDARD = vdi.MFDB_FORMAT_DEVICE, vdi.MFDB_FORMAT_STANDARD
STALE_STAND = 0x5A5A


def form_word(plane, word):
    """A word no other (plane, word) of any form here shares."""
    return 0x1000 * (plane + 1) + word


def device_form(planes, words):
    return [form_word(plane, word) for word in range(words) for plane in range(planes)]


def standard_form(planes, words):
    return [form_word(plane, word) for plane in range(planes) for word in range(words)]


def trnfm_pokes(planes, height, width, stand, *, in_place=False, same_mfdb=False, tag=0, form_tags=(0, 0)):
    """A source MFDB and form of `planes` x `height` x `width` words in format `stand`, and a
    destination MFDB whose `stand` is stale — at the same address as the source when `in_place`, and the
    source record itself when `same_mfdb`. Every other word of both forms is FILLed. `tag` is a top byte on
    LINEA_CONTRL and both MFDB pointers, `form_tags` the (source, destination) forms' own."""
    words = height * width
    form = device_form(planes, words) if stand == DEVICE else standard_form(planes, words)
    destination_at = SOURCE_AT if in_place else DESTINATION_AT
    geometry = {"H": height, "WDWIDTH": width, "NPLANES": planes}
    pokes = vdi.merge_pokes(
        {SOURCE_AT: vdi.pack_words(*form) + bytes([vdi.FILL]) * (2 * (FORM_WORDS - len(form))),
         DESTINATION_AT: bytes([vdi.FILL]) * vdi_helpers.RASTER_FORM_BYTES},
        vdi.mfdb_pokes(SOURCE_MFDB, ADDR=SOURCE_AT | form_tags[0], STAND=stand, **geometry),
        vdi.mfdb_pokes(DESTINATION_MFDB, ADDR=destination_at | form_tags[1], STAND=STALE_STAND, **geometry))
    destination_mfdb = SOURCE_MFDB if same_mfdb else DESTINATION_MFDB
    call = vdi.call_pokes(addrs.VDI_ROM_VR_TRNFM_OPCODE, pointers=(SOURCE_MFDB | tag, destination_mfdb | tag))
    return vdi.merge_pokes(pokes, call, vdi.linea_pokes(CONTRL=vdi.CONTRL_AT | tag))


def vr_trnfm(pokes):
    return vdi.run_function(NAME, pokes)


# Planes 1..4, an ODD width, a single word, and a form of one row.
SHAPES = ((4, 2, 3), (1, 3, 1), (2, 1, 5), (3, 2, 2), (4, 1, 1), (2, 4, 3))


@pytest.mark.parametrize("in_place", (False, True))
@pytest.mark.parametrize("planes,height,width", SHAPES)
def test_device_to_standard(planes, height, width, in_place):
    result = vr_trnfm(trnfm_pokes(planes, height, width, DEVICE, in_place=in_place))
    at = SOURCE_AT if in_place else DESTINATION_AT
    words = height * width
    assert result.words(at, planes * words) == standard_form(planes, words)
    assert result.word(DESTINATION_MFDB + vdi.MFDB_STAND) == STANDARD


@pytest.mark.parametrize("in_place", (False, True))
@pytest.mark.parametrize("planes,height,width", SHAPES)
def test_standard_to_device(planes, height, width, in_place):
    result = vr_trnfm(trnfm_pokes(planes, height, width, STANDARD, in_place=in_place))
    at = SOURCE_AT if in_place else DESTINATION_AT
    words = height * width
    assert result.words(at, planes * words) == device_form(planes, words)
    assert result.word(DESTINATION_MFDB + vdi.MFDB_STAND) == DEVICE


def test_a_copy_leaves_its_source_and_the_rest_of_its_destination():
    result = vr_trnfm(trnfm_pokes(4, 2, 3, DEVICE))
    assert result.words(SOURCE_AT, 24) == device_form(4, 6)
    assert result.after(DESTINATION_AT + 48, 16) == bytes([vdi.FILL]) * 16


def test_any_nonzero_stand_is_standard():
    """`tst.w`: a `stand` of 2 is read as the standard format and turned into the device one."""
    result = vr_trnfm(trnfm_pokes(2, 1, 3, 2))
    assert result.words(DESTINATION_AT, 6) == device_form(2, 3)
    assert result.word(DESTINATION_MFDB + vdi.MFDB_STAND) == DEVICE


@pytest.mark.parametrize("in_place", (False, True))
@pytest.mark.parametrize("planes,height,width", ((4, 0, 3), (4, 2, 0), (0, 2, 3)))
def test_an_empty_form_moves_nothing_but_the_flag(planes, height, width, in_place):
    result = vr_trnfm(trnfm_pokes(planes, height, width, DEVICE, in_place=in_place))
    assert result.after(DESTINATION_AT, 16) == bytes([vdi.FILL]) * 16
    assert result.word(DESTINATION_MFDB + vdi.MFDB_STAND) == STANDARD


def test_one_mfdb_for_both_flips_its_own_flag():
    """The source's format is read before the destination's flag is stored, so one record for both
    ends up saying what it now holds."""
    result = vr_trnfm(trnfm_pokes(3, 1, 2, DEVICE, in_place=True, same_mfdb=True))
    assert result.words(SOURCE_AT, 6) == standard_form(3, 2)
    assert result.word(SOURCE_MFDB + vdi.MFDB_STAND) == STANDARD


def test_there_and_back_in_place():
    """Device -> standard -> device over one buffer, the second call starting from the machine the
    first ENDED in (`case.continued`) with its source MFDB now saying standard."""
    first = vr_trnfm(trnfm_pokes(4, 2, 3, DEVICE, in_place=True, same_mfdb=True))
    second = vr_trnfm(case.continued(first))
    assert second.words(SOURCE_AT, 24) == device_form(4, 6)
    assert second.word(SOURCE_MFDB + vdi.MFDB_STAND) == DEVICE


# ---- the 24-bit bus: contrl, both MFDBs and both forms are a program's pointers -----------------------------------

@pytest.mark.parametrize("in_place", (False, True))
@pytest.mark.parametrize("stand", (DEVICE, STANDARD))
def test_every_pointer_with_a_top_byte_reaches_the_same_forms(stand, in_place):
    every = bus.TOP_BYTE
    tagged = vr_trnfm(trnfm_pokes(4, 2, 3, stand, in_place=in_place, tag=every, form_tags=(every, every)))
    at = SOURCE_AT if in_place else DESTINATION_AT
    assert tagged.words(at, 24) == (standard_form if stand == DEVICE else device_form)(4, 6)
    assert tagged.word(DESTINATION_MFDB + vdi.MFDB_STAND) == (STANDARD if stand == DEVICE else DEVICE)


@pytest.mark.parametrize("in_place", (False, True))
def test_the_host_core_returns_over_tagged_pointers(in_place):
    """...and the host core alone over them, in a child, through both transposes: a pointer the C dereferences
    unmasked reaches past the host image and faults, which FAILS here rather than killing the differential's worker."""
    every = bus.TOP_BYTE
    pokes = trnfm_pokes(4, 2, 3, DEVICE, in_place=in_place, tag=every, form_tags=(every, every))
    returncode, stderr, _image = vdi_helpers.refusal_over(routines.core_symbol(NAME), pokes, read_back=False)
    assert returncode == 0, stderr


def test_forms_differing_only_in_the_top_byte_are_copied_not_rotated():
    """`cmpa.l` compares the WHOLE longwords: one form, named once tagged, is two forms to the ROM — the copy
    transposes it over itself, word by word, reading what it already wrote (not the rotation's standard form)."""
    result = vr_trnfm(trnfm_pokes(4, 2, 3, DEVICE, in_place=True, form_tags=(bus.TOP_BYTE, 0)))
    assert result.words(SOURCE_AT, 24) != standard_form(4, 6)


# ---- the transcription (`src/vdi/helpers.S`), over the same shapes ----------------------------------

@pytest.mark.parametrize("in_place", (False, True))
@pytest.mark.parametrize("stand", (DEVICE, STANDARD))
@pytest.mark.parametrize("planes,height,width", SHAPES + ((4, 0, 3), (0, 2, 3)))
def test_the_transcription_behaves_as_the_rom(planes, height, width, stand, in_place):
    vdi_helpers.run_transcription(NAME, trnfm_pokes(planes, height, width, stand, in_place=in_place))


# ---- the rows Tier 3 prices ------------------------------------------------------------------------
vdi.register("vdi_vr_trnfm, device to standard, a copy", addrs.VDI_ROM_VR_TRNFM, trnfm_pokes(4, 2, 3, DEVICE))
vdi.register("vdi_vr_trnfm, standard to device, a copy", addrs.VDI_ROM_VR_TRNFM, trnfm_pokes(4, 2, 3, STANDARD))
vdi.register("vdi_vr_trnfm, device to standard, in place", addrs.VDI_ROM_VR_TRNFM,
             trnfm_pokes(4, 2, 3, DEVICE, in_place=True))
vdi.register("vdi_vr_trnfm, standard to device, in place", addrs.VDI_ROM_VR_TRNFM,
             trnfm_pokes(4, 2, 3, STANDARD, in_place=True))
vdi.register("vdi_vr_trnfm, one word", addrs.VDI_ROM_VR_TRNFM, trnfm_pokes(1, 1, 1, DEVICE))
# ...and the same rows for the `.S` the target build ships.
for _label, _stand, _in_place in (("device to standard, a copy", DEVICE, False),
                                  ("standard to device, a copy", STANDARD, False),
                                  ("device to standard, in place", DEVICE, True),
                                  ("standard to device, in place", STANDARD, True)):
    vdi_helpers.register_transcription(NAME, _label, trnfm_pokes(4, 2, 3, _stand, in_place=_in_place))
vdi_helpers.register_transcription(NAME, "one word", trnfm_pokes(1, 1, 1, DEVICE))
