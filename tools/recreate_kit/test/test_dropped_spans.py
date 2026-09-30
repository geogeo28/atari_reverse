"""A VETTED DROP leaves the attribution (poison) pass running over every other byte.

`harness.differential(..., dropped=)` is for a documented divergence outside the stack, handed to the kit as
DATA (`drops.Dropped`: fixed spans and per-run windows): a byte the
original stores and the reconstruction, by design, does not (TOS 1.02's AES Line-F mask word, which
every masked return rewrites and a C `rts` never does). Filtering such a byte out AFTER the kit had
run was the shape before it: the plain diff still held the dropped byte, the kit's `poison and not
diffs` gate saw a difference and skipped the pass in silence — and with it the one check that sees a
store the candidate SKIPPED over a byte that already held the right value.

So the routine here stores an OUTPUT byte and the DROPPED byte, the case stages the output at the
value the routine leaves (a skipped store is invisible to the plain diff), and a candidate that
skips it must still redden, on the attribution pass, with the other byte dropped.

The module skips whole when the shared oracle or a C compiler is absent (`kit_smoke_project.bind`).
"""
import pytest

from kit_smoke_project import (DROP_OUTPUT_AT, DROP_OUTPUT_VALUE, DROP_SECOND_SPAN_AT, DROP_SPAN_AT,
                               DROP_SPAN_VALUE, OUTPUT_AND_BRANCHING_DROP_ENTRY, OUTPUT_AND_DROP_ENTRY,
                               OUTPUT_AND_SKIPPABLE_DROP_ENTRY, READS_ITS_DROP_ENTRY, bind)

harness = bind()
import emu   # noqa: E402  (importable only once a project is bound, which bind() is what does)
from recreate_kit.drops import Dropped   # noqa: E402  (bind() put reverse/tools on the path)

WHY = "the byte this reconstruction documents it never writes"
DROP_SPAN = (DROP_SPAN_AT, DROP_SPAN_AT + 1, WHY)
SECOND_SPAN = (DROP_SECOND_SPAN_AT, DROP_SECOND_SPAN_AT + 1, WHY)
THE_SPAN_DROPPED = Dropped(spans=(DROP_SPAN,))
# The window over both dropped bytes: each run drops only what it stores of it.
BOTH_BYTES_WINDOW = (DROP_SPAN_AT, DROP_SECOND_SPAN_AT + 1, WHY)
# The output already holding what the routine stores, so the plain diff cannot see a skipped store.
OUTPUT_PRESET = {DROP_OUTPUT_AT: bytes([DROP_OUTPUT_VALUE])}


def _stores_the_output(_lib, buf):
    buf[DROP_OUTPUT_AT] = DROP_OUTPUT_VALUE


def _stores_nothing(_lib, _buf):
    """The reconstruction that SKIPS the output store — right by coincidence over OUTPUT_PRESET."""


def _run(glue, entry=OUTPUT_AND_DROP_ENTRY, **kwargs):
    return harness.differential(entry, {"_pokes": dict(OUTPUT_PRESET)}, glue, poison=True, **kwargs)


def test_the_dropped_byte_is_left_out_and_the_output_attributed():
    """The control: a candidate that makes the store passes with the byte dropped — the drop is neither
    poisoned nor compared on the attribution pass, or this would fail there on the canary."""
    diffs, _info = _run(_stores_the_output, dropped=THE_SPAN_DROPPED)
    assert diffs == []


def test_a_dropped_byte_is_not_poisoned():
    """A routine that READS its dropped byte first: a canary there would steer the oracle's poisoned run past
    the output store, and the compare would redden on a store the candidate did make."""
    diffs, _info = _run(_stores_the_output, READS_ITS_DROP_ENTRY, dropped=THE_SPAN_DROPPED)
    assert diffs == []


def test_a_skipped_store_is_caught_in_a_case_that_drops_a_byte():
    """THE CASE THE AFTER-THE-FACT FILTER LOST: the dropped byte kept the plain diff non-empty, so the
    pass never ran and a candidate that skipped the output passed."""
    with pytest.raises(AssertionError, match=r"attribution \(poison\) check.*0x30050"):
        _run(_stores_nothing, dropped=THE_SPAN_DROPPED)


def test_undropped_the_byte_is_a_plain_difference_and_the_pass_does_not_run():
    """Why the drop has to reach the kit: left in, the byte differs, the kit hands the difference back and
    — correctly, for a diff that is not clean — runs no attribution pass, so the skipped store is unseen."""
    diffs, _info = _run(_stores_nothing)
    assert diffs == [(DROP_SPAN_AT, DROP_SPAN_VALUE, 0)]


def test_each_run_is_cut_by_its_own_ledger():
    """A window's extent is the RUN's. Here the poisoned run (its output byte inverted) also stores the second
    byte of the window, which the plain run skipped: cut by the plain run's ledger alone, the attribution
    compare would redden on a byte the case drops."""
    plain = emu.run(harness.make_image(dict(OUTPUT_PRESET)), OUTPUT_AND_BRANCHING_DROP_ENTRY, {})[1]
    assert DROP_SECOND_SPAN_AT not in plain, "the premise: the plain run skips the window's second byte"
    diffs, _info = _run(_stores_the_output, OUTPUT_AND_BRANCHING_DROP_ENTRY, dropped=Dropped(windows=(BOTH_BYTES_WINDOW,)))
    assert diffs == []


def test_a_fixed_span_is_vetted_against_the_plain_run_only():
    """A FIXED span is the case's claim about the run it describes — the plain one. Here poisoning steers the
    oracle PAST the second dropped byte, which the plain run stores: re-vetting the span against the poisoned run
    refused a correct case ("never writes") for a path the case never takes."""
    plain = emu.run(harness.make_image(dict(OUTPUT_PRESET)), OUTPUT_AND_SKIPPABLE_DROP_ENTRY, {})[1]
    assert DROP_SECOND_SPAN_AT in plain, "the premise: the plain run stores the second byte"
    diffs, _info = _run(_stores_the_output, OUTPUT_AND_SKIPPABLE_DROP_ENTRY,
                        dropped=Dropped(spans=(DROP_SPAN, SECOND_SPAN)))
    assert diffs == []


def test_a_window_with_no_reason_is_refused_even_where_the_run_stores_none_of_it():
    """A reasonless window cannot pass by being empty on the path one case takes."""
    unstored = (DROP_SECOND_SPAN_AT, DROP_SECOND_SPAN_AT + 1, "")
    with pytest.raises(AssertionError, match="no reason"):
        _run(_stores_the_output, dropped=Dropped(windows=(unstored,)))


def test_a_scheduled_store_over_a_dropped_byte_does_not_refuse_the_pass():
    """The attribution pass refuses a byte both the schedule and the run store, because the agent's store would
    overwrite its CANARY. A dropped byte gets no canary, so a schedule storing it clashes with nothing; the output
    byte beside it still does."""
    scheduled = emu.schedule_entries([{"pc": OUTPUT_AND_DROP_ENTRY, "addr": DROP_SPAN_AT, "width": 1, "value": 1}])
    ledger = {DROP_OUTPUT_AT: DROP_OUTPUT_VALUE, DROP_SPAN_AT: DROP_SPAN_VALUE}
    harness._vet_poison_is_attributable(OUTPUT_AND_DROP_ENTRY, scheduled, ledger, (DROP_SPAN,))
    with pytest.raises(AssertionError, match=f"would poison {DROP_SPAN_AT:#x}"):
        harness._vet_poison_is_attributable(OUTPUT_AND_DROP_ENTRY, scheduled, ledger, ())


def test_a_drop_over_a_byte_the_original_never_stores_is_refused():
    """The one rule for a drop (`drops.vet_dropped`), applied by the kit: a byte the original never
    stores can only be hiding the candidate's own stores."""
    unwritten = (DROP_SPAN_AT + 1, DROP_SPAN_AT + 2, WHY)
    with pytest.raises(AssertionError, match="never writes"):
        _run(_stores_the_output, dropped=Dropped(spans=(unwritten,)))
