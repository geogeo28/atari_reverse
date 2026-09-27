"""VDI vector exchanges — vex_timv (118), vex_butv (125), vex_motv (126), vex_curv (127): `src/vdi/attributes.c`.

    vex_butv/motv/curv  contrl[9..10] = USER_BUT/MOT/CUR; USER_x = contrl[7..8]
    vex_timv            the same exchange on USER_TIM, INSIDE `move.w sr,-(sp) / ori.w #$700,sr / ... /
                        move.w (sp)+,sr`; then `Tickcal` through `trap #13`, its low word into intout[0]

Nothing is CALLED: the longwords are exchanged, and in the snapshot they point into the AES — which is
why these cases need no stub (`vdi/linea.h`'s policy is for a routine that calls through one). What the
cases stage is a new routine address — the ROM's own `rts` at `VDI_ROM_NOP`, which is USER_TIM's
default, and an arbitrary longword with bytes in every position — and the old slot filled, so the
answer written there is a changed byte.

TWO ROM FACTS PINNED. vex_timv answers a word in intout[0] and NEVER SETS contrl[4]: the dispatcher's
clear stands, so a caller is told no words came back. And only vex_timv masks interrupts round its
exchange; the three mouse vectors, which the IKBD interrupt calls through, are exchanged unmasked. The
mask is a no-op off target (`ipl.h`), so its surface is Tier 3's cycle count, not these cases.

vex_timv REACHES THE BIOS through the ROM's own `trap #13`, which on the oracle frames 46 bytes below
`savptr`: the cases declare `savptr` inside the dropped stack band exactly as the GEMDOS batteries do
(`test/gemdos.py`, `machine`), and — for the same reason — do not poison.
"""
import struct

import pytest

from harness import BASE_IMAGE, addrs

import gemdos
import vdi
import vdi_attributes as attr

VECTORS = {"VDI_ROM_VEX_TIMV": "USER_TIM", "VDI_ROM_VEX_BUTV": "USER_BUT", "VDI_ROM_VEX_MOTV": "USER_MOT",
           "VDI_ROM_VEX_CURV": "USER_CUR"}
OLD_SLOT_FILL = 0xA5A5A5A5
NEW_ROUTINES = (addrs.VDI_ROM_NOP, 0x00123456)
TIMV = "VDI_ROM_VEX_TIMV"


def savptr_pokes():
    """`savptr` in the dropped band and the frame below it declared, as `gemdos.machine` stages them."""
    return {addrs.SYSVAR_SAVPTR: struct.pack(">I", gemdos.SAVPTR_AT),
            gemdos.FRAME_AT: bytes([gemdos.FRAME_FILL]) * addrs.TRAP_SAVE_FRAME_BYTES}


def exchange_pokes(name, routine, period=None):
    """The call with `routine` at contrl[7..8], the old slot filled, and — for vex_timv — `savptr`
    declared and the timer period `period` (the snapshot's when None)."""
    onto = None
    if name == TIMV:
        onto = savptr_pokes()
        if period is not None:
            onto[addrs.SYSVAR_TIMR_MS] = struct.pack(">H", period)
    return attr.call(name, (), onto=onto, pointers=(routine, OLD_SLOT_FILL))


def run(name, pokes):
    return attr.run(name, pokes, poison=name != TIMV)


@pytest.mark.parametrize("routine", NEW_ROUTINES)
@pytest.mark.parametrize("name", VECTORS)
def test_the_vector_and_the_old_slot_exchange(name, routine):
    result = run(name, exchange_pokes(name, routine))
    assert result.linea(VECTORS[name]) == routine
    assert result.long(vdi.CONTRL_AT + vdi.CONTRL_POINTER_B) == vdi.linea(BASE_IMAGE, VECTORS[name])
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 0


@pytest.mark.parametrize("name", [name for name in VECTORS if name != TIMV])
def test_a_mouse_vector_exchange_answers_nothing(name):
    result = run(name, exchange_pokes(name, addrs.VDI_ROM_NOP))
    assert result.intout(1) == [vdi.FILL * 0x0101]


@pytest.mark.parametrize("period", (None, 0x1234, 0x8000, 0xFFFF))
def test_vex_timv_answers_the_timer_period_and_no_count(period):
    result = run(TIMV, exchange_pokes(TIMV, addrs.VDI_ROM_NOP, period))
    expected = period if period is not None else int.from_bytes(bytes(BASE_IMAGE[addrs.SYSVAR_TIMR_MS:
                                                                                 addrs.SYSVAR_TIMR_MS + 2]), "big")
    assert result.intout(1) == [expected]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 0, "the ROM never says it answered"


# THE EXCHANGE ORDER — the old routine stored into contrl[9..10] BEFORE the new one is read out of
# contrl[7..8] and stored — shows only when contrl[9..10] IS the vector: contrl laid over the Line-A
# vectors, which no caller does. Then the ROM's store of the old routine over itself changes nothing and
# the new one lands; a reconstruction storing the vector first would have the old routine put back over
# it. One case per mouse vector (vex_timv shares the exchange, `exchange_vector`).
def contrl_over_vector_pokes(name, routine):
    contrl_at = vdi.field("LINEA", VECTORS[name]).at - vdi.CONTRL_POINTER_B
    return attr.merge_pokes(attr.call(name, ()), vdi.linea_pokes(CONTRL=contrl_at),
                            {contrl_at + vdi.CONTRL_POINTER_A: struct.pack(">I", routine)})


@pytest.mark.parametrize("name", [name for name in VECTORS if name != TIMV])
def test_the_old_routine_is_stored_before_the_new_one_is_read(name):
    routine = NEW_ROUTINES[1]
    assert run(name, contrl_over_vector_pokes(name, routine)).linea(VECTORS[name]) == routine


for _name in VECTORS:
    attr.register("exchange", _name, exchange_pokes(_name, addrs.VDI_ROM_NOP))
