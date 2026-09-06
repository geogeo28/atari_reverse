"""The ATTRIBUTION (poison) pass is a second candidate run, and it must be armed like the first.

`harness.differential(..., poison=True)` re-runs both cores on an image whose oracle-written bytes
are pre-inverted, so a candidate that matched only because its output landed where the right value
already sat now diverges. That re-run is a whole second run of the candidate, and every per-run model
the kit carries has to be rewound before it: the Dosound ledger, the refusal tally, the PSG and
hardware seeds, the schedule — and, since Phase 13, the off-image OS event ledger and the modeled
Malloc arena.

`harness.arm_candidate` exists precisely so that "arm the candidate" is one block reached by every
caller. The attribution pass had a HAND COPY of it instead, and the copy stopped at the four models
that existed when it was written: the poison run inherited the plain run's console output and
allocated where the plain run's arena had stopped, while the oracle started clean both times. Nothing
noticed, because the poison pass also did not compare either surface.

So this drives a routine with BOTH off-image effects — one console byte, one allocation — through a
poisoned differential and then reads back what the candidate's models hold. One run's worth is the
only right answer; two runs' worth is the hand copy.

The module skips whole when the shared oracle or a C compiler is absent — `oracle/build/` is
gitignored, so a bare checkout is a normal state to be in (`test_entry_state.py`'s convention).
"""
from kit_smoke_project import (CCONOUT_CHAR, EVENT_MALLOC_ENTRY, HEAP_RESULT, MALLOC_PROBE_SIZE,
                               bind)

harness = bind()
import emu   # noqa: E402  (importable only once a project is bound, which bind() is what does)


def _run(poison):
    """The routine through a differential: `Cconout('K')`, then `Malloc` into HEAP_RESULT."""
    return harness.differential(
        EVENT_MALLOC_ENTRY, {},
        lambda lib, buf: lib.g_logs_a_byte_and_allocates(buf, HEAP_RESULT, MALLOC_PROBE_SIZE,
                                                         CCONOUT_CHAR),
        poison=poison)


def _candidate_ledger():
    """The candidate's off-image OS event stream as `[(kind, value)]`, as `harness` reads it."""
    count = harness._lib.g_os_event_count()
    kinds, values = harness._lib.g_os_event_kinds(), harness._lib.g_os_event_values()
    return [(kinds[i], values[i]) for i in range(count)]


def test_the_plain_pass_leaves_one_runs_worth_of_state():
    """The control. Without it the poison case below could pass because the routine does nothing."""
    diffs, info = _run(poison=False)
    assert diffs == []
    assert info["regs"]["events"] == [(harness.OS_EVENT_CONOUT, CCONOUT_CHAR)]
    assert _candidate_ledger() == [(harness.OS_EVENT_CONOUT, CCONOUT_CHAR)]
    assert harness._lib.g_os_heap_pointer() == emu.OS_HEAP_BASE + MALLOC_PROBE_SIZE


def test_the_poison_pass_rearms_the_event_ledger_and_the_malloc_arena():
    """THE CASE THE HAND COPY FAILED. Two candidate runs happen here, and the models must hold one
    run's worth afterwards — the second console byte replacing the first, the arena at one block.

    Two runs' worth is what a poison pass that did not call `arm_candidate` left: a ledger of two
    entries compared against the oracle's one, and an arena a block further on than the oracle's.
    """
    diffs, _ = _run(poison=True)
    assert diffs == []
    assert _candidate_ledger() == [(harness.OS_EVENT_CONOUT, CCONOUT_CHAR)], (
        "the poison re-run inherited the plain run's console output — its ledger was never reset")
    assert harness._lib.g_os_heap_pointer() == emu.OS_HEAP_BASE + MALLOC_PROBE_SIZE, (
        "the poison re-run allocated where the plain run left off — the arena was never rewound")
