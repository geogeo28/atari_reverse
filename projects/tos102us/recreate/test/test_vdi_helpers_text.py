"""The VDI's TEXT helpers (`src/vdi/helpers.c`): the scaler's clc_dda and act_siz, copy_name, and
font_byteswap.

The scaler is a DDA over a word accumulator: clc_dda turns (actual, requested) sizes into an increment
and a direction (LINEA_DDA_INC is the dispatcher's copy of the workstation's, so act_siz's cases stage
the Line-A field directly), and act_siz steps a size through it. Both are hand 68000 and both have a
DIVIDE or a CARRY at their centre, which is where their cases sit.
"""
import pytest

from harness import BASE_IMAGE, addrs

import case
import staging
import vdi
import vdi_helpers
from vdi_helpers import answer, run_call
from vdi_text_c import intel_order

WORD_BYTES = vdi_helpers.WORD_BYTES
STALE = 0x5A5A
DOUBLE = vdi_helpers.VDI_DDA_DOUBLE
SCALE_DOWN, SCALE_UP = vdi_helpers.VDI_SCALE_DOWN, vdi_helpers.VDI_SCALE_UP


# ---- clc_dda, $fcedd0 ------------------------------------------------------------------------------

def clc_dda(actual, requested):
    pokes = vdi.linea_pokes(T_SCLSTS=STALE)
    return run_call("VDI_ROM_CLC_DDA", case.word_args(actual, requested), (actual, requested), pokes)


@pytest.mark.parametrize("actual,requested,increment,direction", (
    (8, 4, 0x8000, SCALE_DOWN),
    (16, 15, 0xF000, SCALE_DOWN),
    (8, 0, 0x2000, SCALE_DOWN),        # a request of 0 is taken as 1
    (8, 8, 0x0000, SCALE_DOWN),        # EQUAL: 65536 overflows divu.w — ROM-UNREACHABLE, $fce07a skips it
    (8, -3, 0x0000, SCALE_DOWN),       # a negative request is a huge unsigned one: overflow again
    (-4, -6, 0xFFFD, SCALE_DOWN),      # ...and a negative actual a huge divisor — no ROM font has one
    (8, 9, 0x2000, SCALE_UP),          # up: the EXCESS as the fraction
    (8, 12, 0x8000, SCALE_UP),
    (8, 15, 0xE000, SCALE_UP),
    (8, 16, DOUBLE, SCALE_UP),         # twice the size: the doubling marker
    (8, 100, DOUBLE, SCALE_UP),
    (0, 5, DOUBLE, SCALE_UP),          # nothing to divide by, and no divide made (ROM-unreachable too)
    (-4, 2, DOUBLE, SCALE_UP),         # an excess over a negative actual, compared signed (likewise)
))
def test_clc_dda(actual, requested, increment, direction):
    result = clc_dda(actual, requested)
    assert answer(result) & 0xFFFF == increment
    assert result.linea("T_SCLSTS") == direction


def test_clc_dda_by_zero_is_refused_by_name_on_the_host():
    """Scaling DOWN to an actual size of 0 divides by it: vector 5 on the machine, a refusal by name
    here (`vdi/helpers.h`)."""
    returncode, stderr = vdi_helpers.refusal("vdi_clc_dda", ["ctypes.c_void_p", "ctypes.c_int16", "ctypes.c_int16"],
                                             "buf, 0, 0")
    assert returncode != 0
    assert "not reconstructed: divu.w by zero" in stderr


# ---- act_siz, $fcee02 ------------------------------------------------------------------------------

def act_siz_pokes(size, increment, direction):
    return vdi.merge_pokes(vdi.linea_pokes(DDA_INC=increment, T_SCLSTS=direction), case.word_arg(size))


def act_siz(size, increment, direction=SCALE_DOWN, **kwargs):
    return answer(run_call("VDI_ROM_ACT_SIZ", case.word_arg(size), (size,),
                           vdi.linea_pokes(DDA_INC=increment, T_SCLSTS=direction), **kwargs))


def carries(size, increment):
    """How many times the half-full accumulator carries in `size` steps."""
    accumulator, count = vdi_helpers.VDI_DDA_ACCUMULATOR_START, 0
    for _ in range(size):
        accumulator += increment
        count += accumulator >> 16
        accumulator &= 0xFFFF
    return count


@pytest.mark.parametrize("size", (5, -3, 0x4000, 0))
def test_act_siz_doubles_on_the_marker(size):
    assert act_siz(size, DOUBLE) & 0xFFFF == (2 * size) & 0xFFFF


@pytest.mark.parametrize("direction", (SCALE_DOWN, SCALE_UP))
@pytest.mark.parametrize("size", (0, -1, -32767))
def test_act_siz_of_nothing_is_nothing_either_way(size, direction):
    assert act_siz(size, 0x8000, direction) == 0


# (2, $8001): the accumulator lands on exactly 0 with a carry, and the next step's sum then EQUALS the
# increment — no carry, which a `<=` carry test would count.
@pytest.mark.parametrize("size,increment", ((10, 0x8000), (16, 0xF000), (3, 0x2000), (10, 0), (1, 0x8001),
                                            (2, 0x8001), (1, 0x8000)))
def test_act_siz_scaling_down_counts_the_carries_and_answers_at_least_one(size, increment):
    assert act_siz(size, increment, SCALE_DOWN) == max(carries(size, increment), 1)


@pytest.mark.parametrize("size,increment", ((10, 0x8000), (16, 0x2000), (3, 0), (1, 0x8001), (2, 0x8001)))
def test_act_siz_scaling_up_adds_a_line_a_step(size, increment):
    assert act_siz(size, increment, SCALE_UP) == size + carries(size, increment)


@pytest.mark.parametrize("direction,up", ((0x0100, False), (0xFFFE, False), (3, True), (0x8001, True)))
def test_act_siz_reads_only_bit_0_of_the_direction(direction, up):
    """`btst #0,$29df`: the LOW byte's bit 0 — a high byte of $01 is still down."""
    assert act_siz(10, 0x8000, direction) == (15 if up else 5)


def test_act_siz_of_the_most_negative_size_runs_32768_steps():
    """`subq.w #1` of $8000 is $7fff, not negative: 32768 steps (`dbf`), not "a size below 1"."""
    lines = act_siz(-32768, 0xFFFE, SCALE_UP, max_insns=1_000_000)
    assert lines & 0xFFFF == 0x8000 + carries(0x8000, 0xFFFE)


# ---- copy_name, $fce0ee ----------------------------------------------------------------------------
NAME_BYTES = vdi.FONT_NAME_BYTES
NAME_FROM = vdi_helpers.NAME_AT
NAME_TO = NAME_FROM + 0x40
NAME = bytes(range(0x41, 0x41 + NAME_BYTES + 4))       # four bytes past the name that must not move


def copy_name(source, destination):
    pokes = {NAME_FROM: NAME, NAME_TO: bytes([vdi.FILL]) * (NAME_BYTES + 4)}
    frame = case.long_args(source, destination)
    return run_call("VDI_ROM_COPY_NAME", frame, (source, destination), pokes)


def test_copy_name_copies_thirty_two_bytes_and_no_more():
    result = copy_name(NAME_FROM, NAME_TO)
    assert result.after(NAME_TO, NAME_BYTES + 4) == NAME[:NAME_BYTES] + bytes([vdi.FILL]) * 4


def test_copy_name_copies_forwards_byte_by_byte():
    """Onto itself one byte up: a forward byte copy smears the first byte along, which a block move
    that honoured the overlap would not."""
    result = copy_name(NAME_FROM, NAME_FROM + 1)
    assert result.after(NAME_FROM, NAME_BYTES + 1) == NAME[:1] * (NAME_BYTES + 1)


# ---- font_byteswap, $fcfaac ------------------------------------------------------------------------
FORM_AT = vdi_helpers.FONT_FORM_AT
FORM_ROOM = 0x40
# A form too big for the window: in the free RAM above the oracle's stack band, CLAIMED there
# (`staging.HIGH_BANDS`) and held dead below, so the case's own ramp is the only thing in it. Not a
# registered row — see the wrap test.
BIG_FORM_BYTES = 0x20000
BIG_FORM_AT = staging.HIGH_BANDS.claim(0x90000, BIG_FORM_BYTES, "test_vdi_helpers_text.py: a whole-bank font form")
WHOLE_BANK_INSNS = 1_000_000      # 65536 words at four instructions each, and room


def test_the_big_form_band_is_dead_memory_in_this_snapshot():
    """Compared like any image, so live bytes there would not be hidden — they would make the wrap
    cases a statement about the desktop's leftovers as well as about the routine."""
    assert bytes(BASE_IMAGE[BIG_FORM_AT:BIG_FORM_AT + BIG_FORM_BYTES]) == bytes(BIG_FORM_BYTES)


def ramp(length, seed=0x11):
    return bytes((seed + 7 * i) & 0xFF for i in range(length))


def byteswap_pokes(width, height, form_at=FORM_AT, form_bytes=FORM_ROOM):
    return vdi.merge_pokes(vdi.linea_pokes(FWIDTH=width, DELY=height, FBASE=form_at),
                           {form_at: ramp(form_bytes)})


def font_byteswap(pokes, **kwargs):
    return run_call("VDI_ROM_FONT_BYTESWAP", {}, (), pokes, **kwargs)


@pytest.mark.parametrize("width,height", ((3, 2), (1, 2), (8, 4), (3, 3), (1, 3)))
def test_font_byteswap_turns_every_word_of_the_form(width, height):
    """An ODD product leaves its last byte, and everything past the form, where it was."""
    result = font_byteswap(byteswap_pokes(width, height))
    words = width * height // 2
    form = ramp(FORM_ROOM)
    assert result.after(FORM_AT, FORM_ROOM) == intel_order(form[:2 * words]) + form[2 * words:]


@pytest.mark.parametrize("width,height,words", (
    (1, 1, 0x10000),            # one byte halves to 0 words, and `subq.w #1` + `dbf` makes that 65536
    (0, 5, 0x10000),
    (0x100, 0x200, 0x10000),    # $20000 bytes: the product's low word is 0
    (0x100, 0x123, 0x1180),     # $12300 bytes: only the low word $2300 is halved
))
def test_font_byteswap_halves_only_the_product_s_low_word(width, height, words):
    result = font_byteswap(byteswap_pokes(width, height, BIG_FORM_AT, BIG_FORM_BYTES), max_insns=WHOLE_BANK_INSNS)
    form = ramp(BIG_FORM_BYTES)
    assert result.after(BIG_FORM_AT, BIG_FORM_BYTES) == intel_order(form[:2 * words]) + form[2 * words:]


# ---- the transcriptions (`src/vdi/helpers.S`), over the same shapes ---------------------------------

@pytest.mark.parametrize("actual,requested", ((8, 4), (8, 0), (8, 8), (8, -3), (-4, -6), (8, 12), (8, 16), (0, 5),
                                              (-4, 2)))
def test_clc_dda_transcription_behaves_as_the_rom(actual, requested):
    vdi_helpers.run_transcription("VDI_ROM_CLC_DDA", vdi.linea_pokes(T_SCLSTS=STALE), frame=case.word_args(actual, requested))


@pytest.mark.parametrize("size,increment,direction", ((5, DOUBLE, SCALE_DOWN), (0, 0x8000, SCALE_UP), (-1, 0x8000, 0),
                                                      (10, 0x8000, SCALE_DOWN), (10, 0, SCALE_DOWN),
                                                      (10, 0x8000, SCALE_UP), (16, 0x2000, 0x0100),
                                                      (16, 0x2000, 3)))
def test_act_siz_transcription_behaves_as_the_rom(size, increment, direction):
    pokes = vdi.linea_pokes(DDA_INC=increment, T_SCLSTS=direction)
    vdi_helpers.run_transcription("VDI_ROM_ACT_SIZ", pokes, frame=case.word_arg(size))


# ---- the rows Tier 3 prices ------------------------------------------------------------------------
vdi.register("vdi_clc_dda, scaling down", addrs.VDI_ROM_CLC_DDA,
             vdi.merge_pokes(vdi.linea_pokes(T_SCLSTS=STALE), case.word_args(16, 15)))
vdi.register("vdi_clc_dda, scaling up", addrs.VDI_ROM_CLC_DDA,
             vdi.merge_pokes(vdi.linea_pokes(T_SCLSTS=STALE), case.word_args(8, 12)))
vdi.register("vdi_clc_dda, doubled", addrs.VDI_ROM_CLC_DDA,
             vdi.merge_pokes(vdi.linea_pokes(T_SCLSTS=STALE), case.word_args(8, 20)))
vdi.register("vdi_act_siz, sixteen lines down", addrs.VDI_ROM_ACT_SIZ, act_siz_pokes(16, 0xF000, SCALE_DOWN))
vdi.register("vdi_act_siz, sixteen lines up", addrs.VDI_ROM_ACT_SIZ, act_siz_pokes(16, 0x2000, SCALE_UP))
vdi.register("vdi_act_siz, doubled", addrs.VDI_ROM_ACT_SIZ, act_siz_pokes(16, DOUBLE, SCALE_UP))
vdi.register("vdi_act_siz, one line", addrs.VDI_ROM_ACT_SIZ, act_siz_pokes(1, 0x8000, SCALE_DOWN))
vdi.register("vdi_copy_name, thirty-two bytes", addrs.VDI_ROM_COPY_NAME,
             vdi.merge_pokes({NAME_FROM: NAME, NAME_TO: bytes([vdi.FILL]) * (NAME_BYTES + 4)},
                             case.long_args(NAME_FROM, NAME_TO)))
vdi.register("vdi_font_byteswap, a form of sixteen words", addrs.VDI_ROM_FONT_BYTESWAP, byteswap_pokes(8, 4))
vdi.register("vdi_font_byteswap, one word", addrs.VDI_ROM_FONT_BYTESWAP, byteswap_pokes(1, 2))
# ...and the same rows for the `.S` the target build ships.
vdi_helpers.register_transcription("VDI_ROM_CLC_DDA", "scaling down", vdi.linea_pokes(T_SCLSTS=STALE),
                                   frame=case.word_args(16, 15))
vdi_helpers.register_transcription("VDI_ROM_CLC_DDA", "scaling up", vdi.linea_pokes(T_SCLSTS=STALE),
                                   frame=case.word_args(8, 12))
vdi_helpers.register_transcription("VDI_ROM_CLC_DDA", "doubled", vdi.linea_pokes(T_SCLSTS=STALE),
                                   frame=case.word_args(8, 20))
for _label, _size, _increment, _direction in (("sixteen lines down", 16, 0xF000, SCALE_DOWN),
                                              ("sixteen lines up", 16, 0x2000, SCALE_UP),
                                              ("doubled", 16, DOUBLE, SCALE_UP), ("one line", 1, 0x8000, SCALE_DOWN)):
    vdi_helpers.register_transcription("VDI_ROM_ACT_SIZ", _label, vdi.linea_pokes(DDA_INC=_increment, T_SCLSTS=_direction),
                                       frame=case.word_arg(_size))
