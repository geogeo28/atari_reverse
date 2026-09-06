"""Pin what a GEMDOS Pterm does to a RUN — the half `test_os_model.py` cannot reach.

That suite drives the trap through `shim.c`'s decode directly and pins the ledger entry, the exit
code and the fact that nothing after the trap executes. What it cannot see is the layer above:
`emu.run`'s report of WHICH ending a run had, its refusal of a checkpoint the run terminates before,
and `harness.differential`'s rejection of a candidate that goes on running past its own `os_pterm`.
All three need a bound project with a built candidate, which is what `kit_smoke_project` is
(`test_write_ledger.py` states the arrangement in full).

WHY THE ENDING NEEDS REPORTING AT ALL. `osh_run` answers the same "reached" for a run that returned
and one that terminated, because a terminated run's final memory is exactly as trustworthy. But
several projects prove a routine never comes back by pairing a checkpoint diff with a
`pytest.raises(match="did not reach rts")`, and over a path that ends in `Pterm` that proof now
passes by TERMINATING rather than by never returning. `out_regs["terminated"]` is what such a pair
should assert instead (TRAP_MODEL.md, Phase 13).

The module skips whole when the shared oracle or a C compiler is absent — `oracle/build/` is
gitignored, so a bare checkout is a normal state to be in.
"""
import pytest

from kit_smoke_project import (PTERM_AFTER_TRAP, PTERM_CANARY, PTERM_CANARY_UNSET, PTERM_ENTRY,
                               PTERM_EXIT_CODE, RMW_ENTRY, MIXER_REG, PORT_DIR_BITS, bind)

harness = bind()
emu = harness.emu


def _pterm_run(**run_args):
    return emu.run(harness.make_image(), PTERM_ENTRY, **run_args)


def test_a_terminating_run_ends_as_cleanly_as_a_returning_one():
    """It reaches the sentinel, so `emu.run` returns rather than raising — and it records the exit
    code, which is the only surface the ending has. A run rejected here instead would make every
    routine whose tail is `Pterm` untestable, which is what the model change was for."""
    mem, _, out_regs = _pterm_run()
    assert out_regs["events"] == [(harness.OS_EVENT_PTERM, PTERM_EXIT_CODE)]
    assert mem[PTERM_CANARY] == PTERM_CANARY_UNSET, (
        "the instruction after the trap ran, so the model returned from Pterm instead of ending")


def test_the_run_reports_WHICH_ending_it_had():
    """`osh_run`'s boolean cannot say, and a "this routine never returns" proof needs to know: over a
    path ending in Pterm the oracle DOES stop, so such a proof would otherwise pass by terminating.
    Paired with its control, or the flag could simply be always-true."""
    assert _pterm_run()[2]["terminated"] is True
    returning = emu.run(harness.make_image(), RMW_ENTRY, psg_seed={MIXER_REG: PORT_DIR_BITS})
    assert returning[2]["terminated"] is False, "an ordinary `rts` run was reported as terminated"


def test_a_checkpoint_the_run_terminates_before_is_refused():
    """The case named the PC it wanted the state at and did not get there. Comparing at the
    termination instead would answer a different question with no sign that it had."""
    with pytest.raises(RuntimeError, match="ended at a GEMDOS Pterm before reaching checkpoint"):
        _pterm_run(stop_pc=PTERM_AFTER_TRAP)


def test_a_candidate_that_terminates_where_the_original_did_agrees():
    """The positive half: `os_pterm` on one side and the trap on the other put the same entry in the
    two ledgers, so the case passes with nothing else to compare — the routine writes no memory."""
    diffs, info = harness.differential(PTERM_ENTRY, {}, lambda lib, buf: lib.g_pterm(buf))
    assert not diffs
    assert info["regs"]["events"] == [(harness.OS_EVENT_PTERM, PTERM_EXIT_CODE)]


def test_a_candidate_that_runs_on_past_its_own_pterm_is_refused():
    """`os_pterm`'s contract is on the CALLER, and this is the surface that enforces it. The oracle's
    run ended at the trap and can never record a second event, so one on this side is a
    reconstruction that carried on — and it writes no image byte, so nothing else would see it."""
    with pytest.raises(AssertionError, match="refus"):
        harness.differential(PTERM_ENTRY, {}, lambda lib, buf: lib.g_pterm_then_speaks(buf))
