"""VDI vsf_perimeter (opcode 104, $fcb45c) — the VDI's worked example: `src/vdi/vdi.c`.

    movea.l CUR_WORK,a4 / movea.l INTOUT,a5 / movea.l INTIN,a0
    tst.w   (a0)            -> 0: clr.w (a5), clr.w 34(a4)    else: move.w #1 to both
    movea.l CONTRL,a0 / move.w #1,8(a0)

Small on purpose: it reaches every surface a VDI function has — intin through a Line-A pointer, the
workstation through `LINEA_CUR_WORK`, and an answer in intout and in contrl[4] — so a battery for any
other function is this file with its own cases. It is entered DIRECTLY, as the dispatcher's `jsr`
leaves the machine (`test/vdi.py`), and the whole of its wiring is the `addrs.h` pair
`VDI_ROM_VSF_PERIMETER` / `VDI_ROM_VSF_PERIMETER_OPCODE`: the C symbol and the Tier 3 entry are derived.
"""
import pytest

from harness import addrs

import vdi

NAME = "VDI_ROM_VSF_PERIMETER"
# What the workstation's flag holds before the call, so that BOTH arms move a byte — a reconstruction
# that skipped the store would otherwise pass over a 0 or a 1 the snapshot already had.
STALE_FLAG = 0x5A5A
# intin[0] values: zero, the two ends of the word, a flag whose only bit is in the HIGH byte (a
# `tst.b` would call it zero), and the plain 1 an application passes.
FLAGS = (0, 1, 2, 0x0100, 0x8000, 0xFFFF)
A_HANDLE = 7


def perimeter_pokes(flag, *, workstation_pokes=None):
    """A vsf_perimeter call over the physical workstation, dispatched, or over `workstation_pokes`."""
    staged_work = workstation_pokes or vdi.dispatched_pokes(FILL_PER=STALE_FLAG)
    return vdi.call_pokes(addrs.VDI_ROM_VSF_PERIMETER_OPCODE, intin=(flag,), workstation_pokes=staged_work)


def run(pokes):
    return vdi.run_function(NAME, pokes)


@pytest.mark.parametrize("flag", FLAGS)
def test_the_flag_is_stored_normalised_in_intout_and_the_workstation(flag):
    """`tst.w` then a constant: any nonzero WORD is 1, in both places, and contrl[4] says one word."""
    result = run(perimeter_pokes(flag))
    outlined = int(flag != 0)
    assert result.intout(1) == [outlined]
    assert result.workstation("FILL_PER") == outlined
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1
    assert result.contrl(vdi.CONTRL_N_PTSOUT) == 0, "the routine answers no points"


@pytest.mark.parametrize("flag", (0, 1))
def test_the_workstation_written_is_the_one_cur_work_names(flag):
    """A VIRTUAL workstation made current: the store lands in it, and the physical record — which a
    reconstruction reading `VDI_PHYS_WORK` rather than `LINEA_CUR_WORK` would write — is untouched."""
    result = run(perimeter_pokes(flag, workstation_pokes=vdi.virtual_workstation(A_HANDLE, FILL_PER=STALE_FLAG)))
    assert result.workstation("FILL_PER", at=vdi.VIRTUAL_WORK_AT) == flag
    assert not any(vdi.VDI_PHYS_WORK <= at < vdi.VDI_PHYS_WORK + vdi.WS_BYTES for at in result.info["writes"])


@pytest.mark.parametrize("flag", (0, 0x0100))
def test_contrl_is_written_last(flag):
    """The ORDER, which only an overlap can show: intout laid over contrl[4]. The ROM stores the flag
    there first and then contrl[4] = 1, so the word ends 1 whatever the flag was; the other order
    would leave the flag."""
    pokes = vdi.merge_pokes(perimeter_pokes(flag),
                            vdi.linea_pokes(INTOUT=vdi.CONTRL_AT + vdi.CONTRL_N_INTOUT))
    assert run(pokes).contrl(vdi.CONTRL_N_INTOUT) == 1


vdi.register("vdi_vsf_perimeter, outlined", addrs.VDI_ROM_VSF_PERIMETER, perimeter_pokes(1))
vdi.register("vdi_vsf_perimeter, not outlined", addrs.VDI_ROM_VSF_PERIMETER, perimeter_pokes(0))
