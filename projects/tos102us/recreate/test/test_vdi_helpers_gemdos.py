"""The VDI's `trap #1` door, gemdos_call ($fcfa9c) — `src/vdi/helpers.c`, and `helpers.S` on target.

    move.l (sp)+,LINEA_RETSAV / trap #1 / move.l LINEA_RETSAV,-(sp) / rts

The VDI makes two GEMDOS calls through it — `Malloc` for a virtual workstation and `Mfree` to give one
back — and each case here is one of them, the ORACLE taking the machine's real `trap #1` into the ROM's
GEMDOS and the CANDIDATE handing the same words to the reconstructed dispatcher (`src/gemdos/
dispatch.c`), its `Malloc`/`Mfree` handler bound to the reconstructed memory manager. So the claim is
the whole call: the parked return address, the words GEMDOS was handed, the pool it changed and D0.

THREE WINDOWS ARE DROPPED (`vdi_helpers.GEMDOS_DOOR_WINDOWS`; `case.run`'s `dropped_windows`, so only the bytes
of each the ROM's run stores), each the reconstruction's own documented hole rather than scratch:
  * p_run's REGISTER-SAVE AREA (BASEPAGE_SAVED_D0 .. the frame pointer), which the trap entry writes —
    `src/gemdos/trap1.S` on target, and there is no trap entry on the host;
  * GEMDOS's own STACK below GEMDOS_SUPERVISOR_STACK, which that entry switches to: the ROM
    dispatcher's frames, return addresses into the ROM among them;
  * the TERMINATION RECORD, which `src/gemdos/dispatch.c` does not write (its header says why, and
    `test_gemdos_dispatch.py` measures the twelve bytes).

NOTHING HERE POISONS, for `test/gemdos_memory.py`'s reason: the memory manager chases the list heads it
writes, and an inverted one leads both sides into the I/O page. LINEA_RETSAV is staged FILLed instead,
so a skipped park shows.

TIER 3 PRICES THE `.S`, NOT THE C — AND THE C's TARGET BRANCH IS EXECUTED BY NO BUILD. The core has two
branches (`helpers.c`): off target it hands the words to the reconstructed dispatcher, which is what
every case above runs; on target it is an inline `trap #1`. Only Tier 3 could run that one, and not over
these cases: the real trap's entry writes p_run's register-save area and GEMDOS's stack — spans that
differ between the two shores BY NATURE (the registers each side held at the trap, a return PC into the
C or into the ROM), which the cases above drop and Tier 3's relation, comparing the image whole, cannot.
So the C's rows are verified and UNPRICED, and the target branch is UNEXERCISED: it is compiled into
the bench blob and nothing more, and since gemdos_call is TRANSCRIBED the shipped build links the `.S`
in its place (`test_the_c_target_branch_ships_nowhere` pins both halves). The `.S` takes the trap from
the ROM's own instructions, but
GEMDOS's dispatcher saves the register the entry popped the trap's return PC into, so that PC — an
address inside the `.S` on one side and inside the ROM on the other — lands on GEMDOS's stack too. So
the transcription's cases point the `trap #1` VECTOR (RAM, `VECTOR_TRAP_GEMDOS`) at a staged handler
that records the words it was trapped with and answers a D0, identically on both sides: what is priced
and compared is the door — its park, its trap frame, its answer and its return — and not GEMDOS.
"""
import pytest

from harness import BASE_IMAGE, addrs, emu, make_image

import case
import gemdos
import gemdos_memory
import vdi
import vdi_helpers
from vdi_helpers import GEMDOS_DOOR_WINDOWS, GEMDOS_HANDLERS, RETSAV_STALE

NAME = "VDI_ROM_GEMDOS_CALL"
WORKSTATION_BYTES = vdi.WS_BYTES                 # what v_opnvwk asks for ($fcd61a)
# What the ROM parks: the address its caller's `jsr` returns to — here the run's own sentinel.
RETURN_SITE = emu.SENTINEL


def frame(function, argument):
    return case.args(">HI", function, argument & 0xFFFF_FFFF)


def gemdos_call(function, argument, pokes=None):
    staged = vdi.merge_pokes(RETSAV_STALE, pokes, frame(function, argument))

    def glue(lib, buf):
        return lib.vdi_gemdos_call(buf, RETURN_SITE, function, argument)

    with gemdos.bound_handlers(GEMDOS_HANDLERS):
        info = case.run(addrs.VDI_ROM_GEMDOS_CALL, {"_pokes": staged}, gemdos.recording(glue), poison=False,
                        dropped_windows=GEMDOS_DOOR_WINDOWS)
    return vdi.Result(info, staged)


def test_malloc_through_the_door():
    """v_opnvwk's call: a workstation's worth of the TPA, its address in D0, and the door's own return
    address parked where the trap cannot disturb it."""
    result = gemdos_call(addrs.GEMDOS_MALLOC_FN, WORKSTATION_BYTES)
    block = result.info["regs"]["d0"]
    assert case.long_in(BASE_IMAGE, addrs.SYSVAR_MEMBOT) <= block < case.long_in(BASE_IMAGE, addrs.SYSVAR_MEMTOP)
    assert result.linea("RETSAV") == RETURN_SITE


def test_mfree_gives_that_block_back():
    """...and v_clsvwk's, over the machine the Malloc ENDED in (`case.continued`): the block is freed
    and D0 is GEMDOS's 0."""
    first = gemdos_call(addrs.GEMDOS_MALLOC_FN, WORKSTATION_BYTES)
    second = gemdos_call(addrs.GEMDOS_MFREE_FN, first.info["regs"]["d0"],
                         {**case.continued(first), **RETSAV_STALE})
    assert second.info["regs"]["d0"] == 0


def test_mfree_of_a_block_gemdos_never_gave_answers_its_error():
    result = gemdos_call(addrs.GEMDOS_MFREE_FN, vdi_helpers.BAND_AT)
    assert result.info["regs"]["d0"] == gemdos_memory.GEMDOS_EIMBA


# ---- the transcription (`src/vdi/helpers.S`), over a staged `trap #1` --------------------------------

@pytest.mark.parametrize("function,argument", ((addrs.GEMDOS_MALLOC_FN, WORKSTATION_BYTES),
                                               (addrs.GEMDOS_MFREE_FN, vdi_helpers.BAND_AT)))
def test_the_transcription_behaves_as_the_rom(function, argument):
    vdi_helpers.run_transcription(NAME, vdi_helpers.staged_gemdos_trap_pokes(), frame=frame(function, argument))


def test_the_staged_handler_records_the_frame_the_rom_door_traps_with():
    """The handler the transcription rows stand in for GEMDOS, run under the ROM's own door: it sees
    the function word and the longword the caller pushed, and its D0 is the door's answer."""
    pokes = vdi.merge_pokes(vdi_helpers.staged_gemdos_trap_pokes(), frame(addrs.GEMDOS_MALLOC_FN, WORKSTATION_BYTES))
    final, _writes, regs = emu.run(make_image(pokes), addrs.VDI_ROM_GEMDOS_CALL, {})
    assert vdi_helpers.trapped_calls(final) == [(addrs.GEMDOS_MALLOC_FN, WORKSTATION_BYTES)]
    assert regs["d0"] == vdi_helpers.TRAP_ANSWER


def test_the_c_target_branch_ships_nowhere():
    """The C core's `trap #1` branch has no differential (the docstring says why), which is safe only
    while nothing ships it: gemdos_call is TRANSCRIBED, so the ROM build takes the `.S`, and the C has no
    Tier 3 row that could be mistaken for a price of that branch."""
    assert vdi.transcription_symbol(NAME) in vdi.TRANSCRIBED
    assert vdi.core_symbol(NAME) in vdi_helpers.UNPRICED_CORES


# ---- the registry -------------------------------------------------------------------------------------
vdi.register("vdi_gemdos_call, Malloc", addrs.VDI_ROM_GEMDOS_CALL,
             vdi.merge_pokes(RETSAV_STALE, frame(addrs.GEMDOS_MALLOC_FN, WORKSTATION_BYTES)), priced=False)
vdi_helpers.register_transcription(NAME, "a trapped Malloc", vdi_helpers.staged_gemdos_trap_pokes(),
                                   frame=frame(addrs.GEMDOS_MALLOC_FN, WORKSTATION_BYTES))
