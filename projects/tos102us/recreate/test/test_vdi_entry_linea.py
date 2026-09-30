"""The Line-A exception ($fc9f0c, vector $28): `src/vdi/entry.c`'s C twin, entered DIRECTLY (`test/vdi_entry.py`).

    movea.l 2(sp),a1 / move.w (a1),d2 / and.w #$fff,d2 / addq.l #2,a1 / move.l a1,2(sp)
    cmp.w #15,d2 / bhi -> rte / lsl.w #2,d2 / movea.l table(pc,d2.w),a1 / movem d3-d7/a3-a5 / jsr (a1) / movem / rte

The frame is staged in the VDI window, so the stepped PC the handler writes back is compared image, and the `rte`
resumes at the staged `rts` after the $Axxx word. A served opcode is run end to end: the ROM's primitive on one side,
its C core on the other, as the register hook's effect — D0/D1/A0 handed back compared. What this path cannot show
is what the `.S` alone ships: the `movem` bracket, the `rte` and the whole register file, which
`test_vdi_entry_transcription.py` holds to the ROM.

IT DOES NOT POISON (`vdi.READS_A_POINTER_IT_WRITES`): the handler reads the stacked PC and writes it back, and the
attribution pass would invert it before the read and send the handler to an address no case staged.
"""
import pytest

from harness import addrs

import test_vdi_linea_init  # noqa: F401  ($a000's contract)
import test_vdi_raster_pixel as pixel
import transcription
import vdi
import vdi_entry as entry
import vdi_fill
from opcodes import LINE_A

INIT, PUT, GET = "LINEA_ROM_INIT", "LINEA_ROM_PUT_PIXEL", "LINEA_ROM_GET_PIXEL"
INIT_OPCODE, PUT_OPCODE, GET_OPCODE = 0, 1, 2
UNPOISONED = vdi.READS_A_POINTER_IT_WRITES
# A point and colour the pixel pair reach: every plane's bit changes.
POINT, COLOUR = (37, 100), 0b1010
SEED_ABOVE_THE_CLIP = (10, 5)


def run(opcode_word, pokes=None, name=None, registers=None):
    """`opcode_word` through the handler; `name` the primitive it serves (None: none), whose answers are compared."""
    if name is None:
        return entry.run_direct(opcode_word, registers, pokes, **UNPOISONED)
    return entry.run_direct(opcode_word, registers, pokes, entry.primitive(name), entry.answered(name), **UNPOISONED)


def assert_resumed_past_the_word(result):
    assert result.long(entry.FRAME_AT + addrs.EXCEPTION_FRAME_PC) == entry.OPCODE_WORD_AT + vdi.WORD_BYTES


def test_a000_answers_the_block_through_the_hook():
    result, calls = run(LINE_A | INIT_OPCODE, name=INIT)
    assert calls == [addrs.LINEA_ROM_INIT]
    assert result.info["regs"]["d0"] == result.info["regs"]["a0"] == vdi.LINEA_BASE
    assert_resumed_past_the_word(result)


def test_a001_puts_the_pixel():
    pokes = pixel.point_pokes(*POINT, colour=COLOUR)
    result, calls = run(LINE_A | PUT_OPCODE, pokes, PUT)
    assert calls == [addrs.LINEA_ROM_PUT_PIXEL]
    assert result.pixel(*POINT) == COLOUR


def test_a002_answers_the_pixel_in_d0():
    pokes = vdi.pixel_pokes({POINT: COLOUR}, onto=pixel.point_pokes(*POINT))
    result, _calls = run(LINE_A | GET_OPCODE, pokes, GET, registers={"d0": 0xFFFF_FFFF})
    assert result.info["regs"]["d0"] & vdi.LINEA_OPCODE_MASK == COLOUR


def test_a00f_the_last_the_table_serves_is_called():
    """$a00f, the contour fill, from a seed above the clip, where it fills nothing — the table's last entry, called."""
    work = vdi_fill.fill_workstation(colour=COLOUR, mode="replace", pattern="solid", clip=vdi_fill.DESKTOP_CLIP)
    pokes = vdi.merge_pokes(vdi.function_pokes("VDI_ROM_V_CONTOURFILL", intin=(COLOUR,), ptsin=SEED_ABOVE_THE_CLIP,
                                               workstation_pokes=work), vdi_fill.default_seedabort_pokes())
    _result, calls = run(LINE_A | vdi.LINEA_OPCODE_LAST, pokes, "LINEA_ROM_CONTOUR_FILL")
    assert calls == [addrs.LINEA_ROM_CONTOUR_FILL]


# Opcodes the table does not serve: the first past it, the highest the mask leaves, and two whose served-looking
# low bits sit under a bit the mask keeps ($a100, $a800) — a narrower mask would serve them.
UNSERVED = (0x10, vdi.LINEA_OPCODE_MASK, 0x100, 0x800)


@pytest.mark.parametrize("number", UNSERVED)
def test_an_unserved_opcode_only_steps_the_pc(number):
    result, calls = run(LINE_A | number)
    assert calls == []
    assert_resumed_past_the_word(result)


def test_the_word_s_top_nibble_is_masked_off():
    """Only the low twelve bits select: a staged $f000 over $a000's number is served as $a000."""
    result, calls = run(0xF000 | INIT_OPCODE, name=INIT)
    assert calls == [addrs.LINEA_ROM_INIT]


# ---- the rows: verified, not priced — each is entered at the trampoline, not the routine (`vdi.register`) --------
for _label, _word, _pokes in (("$a000", LINE_A | INIT_OPCODE, None),
                              ("$a001", LINE_A | PUT_OPCODE, pixel.point_pokes(*POINT, colour=COLOUR)),
                              ("$a010, unserved", LINE_A | 0x10, None)):
    vdi.register(f"linea_dispatch, {_label}", entry.TRAMPOLINE_AT, entry.direct_pokes(_word, _pokes),
                 regs=dict(transcription.DIRTY), priced=False)
