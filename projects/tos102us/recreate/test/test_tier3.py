"""TIER 3's GATE: every verified function priced, at or under the bar, and the m68k build proved
equal.

`../README.md` states the rule this file enforces — "Bar: **≤ 1.10** per function; a function over
the bar is a perf item, not a verified row, until it is either brought under ... or explicitly
accepted with the measured cost". A ratio printed by `make bench` is a report and a report is not a
gate: nothing reddens when nobody runs it. This is the same registry (`../bench/tier3.py`) run by
`make test`, and `tier3.verdict` is the one rule both read.

THREE THINGS ARE GATED HERE, and the third is the one that was missing while the ratio column was
being built:

* the RATIO — under the bar, or carried by a `tier3.PERF_ACCEPTED` entry that says what it measured;
* a PINNED ratio still measuring what it was pinned at, which is the only surface a cost the Tier 1
  differential cannot see has at all (`xbios_giaccess`'s interrupt bracket — `ipl.h`);
* that every VERIFIED CASE HAS A ROW. A function reconstructed without one carries no ratio and no
  second differential, and nothing said so: `make bench` printed a table that was complete about
  itself. `tier3.UNPRICED` is the answer, derived from `test_boot_snapshot.VERIFIED_CASES` rather
  than from a list beside it.

EVERY CASE HERE IS ALSO A SECOND DIFFERENTIAL, and that is the larger half of what it buys. Tier 1
proves the HOST build of a core equals the ROM; this runs a THIRD build — the same C through
`m68k-elf-gcc` with the shipped ROM's flags — over the same case and requires the same image, the
same return value, the same callee-saved file, the same off-image streams and no refusal on either
side (`tools/recreate_kit/rom_bench.py`). `docs/on-target-execution.md`'s bug class 6 is exactly a
target build going wrong where a host build is right, and nothing else in this project looks for it.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))

import tier3                                               # noqa: E402  (the registry and the bar)
# ...and the caller a transcription row is netted by, whose cost `trap.py` measures.
import trap                                                # noqa: E402
from recreate_kit.rom_bench import Measurement, RomBench   # noqa: E402


@pytest.fixture(scope="module")
def bench():
    """The cross-compiled cores, loaded once per worker.

    FAILS rather than skips when the blob is absent — `RomBench.require` says why, and `make test`
    builds it (kit.mk's `test: $(BENCH_BIN)`), so an absent one is a broken target build and not a
    tree nobody built.
    """
    return RomBench()


@pytest.fixture(scope="module")
def dispatch(bench):
    """What a `trap #13` call spends before the leaf runs, measured once per worker.

    The LEAF RULE is a fraction of it (`tier3.dispatch_cycles`), so every verdict below needs it —
    and it is two more oracle runs, not a number to re-measure per row.
    """
    return tier3.dispatch_cycles(lambda key: tier3.measure(tier3.row_named(key), bench))


def _row_id(row):
    return f"{row.symbol}-{row.case}"


def test_every_verified_case_carries_a_bench_row():
    """A reconstructed function with no Tier 3 row is the state the numerator exists to end.

    The required set is `test_boot_snapshot.VERIFIED_CASES` — the list a battery's own case
    constructors build and the snapshot mask is checked against — so a wave that verifies a function
    and forgets its row reddens HERE, rather than leaving a table that is complete about itself.
    What a new row needs is one `tier3.CALL` entry saying how the C is called; everything else is
    already in that list.
    """
    assert not tier3.UNPRICED, (
        f"{len(tier3.UNPRICED)} verified case(s) have no Tier 3 row: {', '.join(tier3.UNPRICED)}. "
        f"Add the routine to `bench/tier3.py`'s CALL table — its C arguments and the width its "
        f"signature returns — and the row builds itself from the case")


def test_no_two_rows_share_a_name():
    """`PERF_ACCEPTED` is keyed by `(symbol, case)`, so two rows with one name would share an
    acceptance — and the second would be excused by, and pinned to, the first's measurement."""
    names = [(row.symbol, row.case) for row in tier3.ROWS]
    assert len(set(names)) == len(names), (
        f"two Tier 3 rows share a (symbol, case) name: "
        f"{sorted(name for name in names if names.count(name) > 1)}")


@pytest.mark.parametrize("row", tier3.ROWS, ids=_row_id)
def test_the_m68k_build_equals_the_original_and_is_within_the_bar(row, bench, dispatch):
    """One row: measure both sides over one case — which raises if the m68k build diverged — then
    put the measurement through the same `verdict` the table prints."""
    measured = tier3.measure(row, bench)
    state = tier3.verdict(row, measured, dispatch)
    assert state not in tier3.FAILED, _why(row, measured, state)


def _why(row, measured, state):
    """The refusal in full: what it cost, what the rule made of it, and the move out of it."""
    cost = (f"{row.symbol} / {row.case} costs {measured.ratio:.3f}x the original "
            f"({measured.recreate_cycles} cycles against {measured.original_cycles}, each including "
            f"the {measured.overhead_cycles} the entry itself charges)")
    if state == "DRIFTED":
        pinned, why = tier3.pin_of(row)
        return (f"{cost}, but it is PINNED at {pinned:.3f}x — {why}. It has moved more than "
                f"{tier3.RATIO_TOLERANCE:.2f}, which is a change somebody made: nothing here is "
                f"sampled. Re-pin it in tier3.PERF_ACCEPTED with the new measurement, or put back "
                f"what moved")
    return (f"{cost}, over the {tier3.TIER3_FUNCTION_BAR:.2f} bar. Bring it under — the levers are "
            f"in ../README.md, \"Tier 3\" — or accept it in tier3.PERF_ACCEPTED with the measured "
            f"cost and a reason")


def test_no_pinned_ratio_is_stale(bench):
    """A pin is a decision about a measured cost, so it must not outlive the measurement.

    Two ways it can. Naming a row the registry no longer has — the case was renamed, the function
    re-cased — where it excuses nothing and pins nothing. And standing ABOVE the bar over a row that
    has since come back UNDER it, where it would go on excusing a cost nobody is paying, and would
    silently excuse the next regression too.

    A pin recorded UNDER the bar is a different claim and does not go stale that way: it is there
    because the cycle count is the only surface something in the row has, and it staying under the
    bar is what it says. Its own staleness is drift, which every row's case above already refuses.
    """
    rows = {(row.symbol, row.case): row for row in tier3.ROWS}
    for key, (pinned, _why) in tier3.PERF_ACCEPTED.items():
        assert key in rows, (
            f"tier3.PERF_ACCEPTED names {key}, which is not a row of tier3.ROWS — the case was "
            f"renamed or dropped, and a pin that matches nothing pins nothing")
        if pinned <= tier3.TIER3_FUNCTION_BAR:
            continue
        measured = tier3.measure(rows[key], bench)
        assert measured.ratio > tier3.TIER3_FUNCTION_BAR, (
            f"tier3.PERF_ACCEPTED carries {key} as an ACCEPTANCE ({pinned:.3f}x, over the "
            f"{tier3.TIER3_FUNCTION_BAR:.2f} bar), but it now measures {measured.ratio:.3f}x — "
            f"under it. Drop the acceptance: it is excusing a cost that is no longer paid")


# ---- the LEAF RULE, which is the one verdict that is not a written entry ------------------------

# What a `trap #13` costs before the leaf it dispatches to runs, as this table measures it. Pinned
# for `RESET_OBSERVATION`'s reason: it is the denominator the rule's fraction is taken of, so a
# dispatcher that grew would quietly widen the slack every leaf is judged by, and nothing else in
# the suite reads this number.
DISPATCH_CYCLES = 464

# The ISR row the rule must NOT admit, and the reason it is the right control: mechanism (A) is part
# of its excess too, exactly as it is the whole of a leaf's — and it is seven times the slack. A rule
# that passed it would be accepting anything (A) touched rather than anything small.
ISR_OVER_THE_SLACK = ("isr_vbl", "a frame with everything queued")

# A row the listing does NOT name, and an excess small enough that only the naming can refuse it.
UNNAMED_ROW = ("bios_setexc", "read")
TRIVIAL_EXCESS = 2


def test_the_dispatch_cost_the_rule_is_a_fraction_of(dispatch):
    assert dispatch == DISPATCH_CYCLES, (
        f"a whole trap call costs {dispatch} cycles before the leaf runs, not the "
        f"{DISPATCH_CYCLES} the leaf rule's slack was written against — every (A)-only leaf is now "
        f"judged against a different denominator, so re-read tier3.IMAGE_POINTER_LEAVES")


@pytest.mark.parametrize("key", sorted(tier3.IMAGE_POINTER_LEAVES), ids=lambda key: "-".join(key))
def test_the_leaf_rule_admits_every_row_it_names(key, bench, dispatch):
    """Each named row measured, and the rule asked about it.

    A name here is a claim that the image-pointer load is the WHOLE of that row's excess; if the row
    has grown a second cost the excess walks out of the slack and this reds, which is the same
    service the written entry it replaced performed and the reason the list is not a silencer.
    """
    row = tier3.row_named(key)
    measured = tier3.measure(row, bench)
    excess = measured.recreate_net - measured.original_net
    assert tier3.rule_admits(row, measured, dispatch), (
        f"{key} is named an (A)-only trap leaf but costs {excess} cycles over the original — past "
        f"the {tier3.LEAF_SLACK_CYCLES}-cycle slack or past {tier3.LEAF_SLACK_FRACTION:.1%} of the "
        f"{dispatch + measured.original_net}-cycle call it is part of. Either the core grew a "
        f"second cost, in which case name it in PERF_ACCEPTED, or the excess is real")


def _carrying(measured, bench, excess):
    """`measured`'s row with a different EXCESS over the original and nothing else changed — the
    shape a regression in that core would have, without a core that has one."""
    return Measurement((0, measured.original_cycles),
                       (0, measured.original_cycles + excess), bench.overhead)


def _fraction_budget(measured, dispatch):
    """...and what the rule's second test allows that row: a fraction of the whole dispatched call."""
    return tier3.LEAF_SLACK_FRACTION * (dispatch + measured.original_net)


def test_the_leaf_rule_refuses_an_excess_the_size_of_a_serviced_blank(bench, dispatch):
    """The smallest leaf, carrying the excess `isr_vbl / a frame with everything queued` really
    measures.

    The slack is what makes the rule a rule rather than a blanket, so the refusal is driven with a
    MEASURED number — that ISR row's own excess, a whole serviced vertical blank through an image
    pointer and four staged calls — rather than an invented one.
    """
    isr = tier3.measure(tier3.row_named(ISR_OVER_THE_SLACK), bench)
    excess = isr.recreate_net - isr.original_net
    leaf = tier3.row_named(tier3.DISPATCH_LEAF)
    measured = tier3.measure(leaf, bench)
    assert tier3.rule_admits(leaf, measured, dispatch), "the leaf's own measurement is admitted"
    assert not tier3.rule_admits(leaf, _carrying(measured, bench, excess), dispatch), (
        f"the leaf rule admitted a {excess}-cycle excess on {tier3.DISPATCH_LEAF} — the slack is "
        f"{tier3.LEAF_SLACK_CYCLES} cycles, and an ISR arm's worth of excess is not a pointer load")


# The rule has TWO tests and they bind on different rows, so an excess that only one of them refuses
# is the only way to pin either. On the SMALLEST leaf the fraction is the tighter — 7.5% of a
# 496-cycle call is 37 cycles against the 40-cycle slack — and on the largest it is the other way
# round, because the leaf's own cycles are inside the call the fraction is taken of. Both cases
# below assert which half is doing the refusing before they ask, so WIDENING EITHER CONSTANT reds
# here rather than quietly admitting more.
BIGGEST_LEAF = ("bios_getmpb", "bios_getmpb")
OVER_THE_SLACK = tier3.LEAF_SLACK_CYCLES + 2
INSIDE_THE_SLACK = tier3.LEAF_SLACK_CYCLES - 2


def test_the_absolute_slack_is_what_refuses_it_on_the_biggest_leaf(bench, dispatch):
    row = tier3.row_named(BIGGEST_LEAF)
    measured = tier3.measure(row, bench)
    assert OVER_THE_SLACK <= _fraction_budget(measured, dispatch), (
        f"the premise has moved: {OVER_THE_SLACK} cycles is no longer inside {BIGGEST_LEAF}'s "
        f"fraction budget, so this case no longer tests the absolute slack at all")
    assert not tier3.rule_admits(row, _carrying(measured, bench, OVER_THE_SLACK), dispatch), (
        f"{OVER_THE_SLACK} cycles over the original was admitted on {BIGGEST_LEAF}, where only the "
        f"{tier3.LEAF_SLACK_CYCLES}-cycle slack refuses it — the slack has been widened, and an "
        f"excess that size is no longer one image-pointer load")


def test_the_fraction_is_what_refuses_it_on_the_smallest_leaf(bench, dispatch):
    row = tier3.row_named(tier3.DISPATCH_LEAF)
    measured = tier3.measure(row, bench)
    assert INSIDE_THE_SLACK > _fraction_budget(measured, dispatch), (
        f"the premise has moved: {INSIDE_THE_SLACK} cycles is now inside {tier3.DISPATCH_LEAF}'s "
        f"fraction budget, so this case no longer tests the fraction at all")
    assert not tier3.rule_admits(row, _carrying(measured, bench, INSIDE_THE_SLACK), dispatch), (
        f"{INSIDE_THE_SLACK} cycles over the original was admitted on {tier3.DISPATCH_LEAF}, where "
        f"only the {tier3.LEAF_SLACK_FRACTION:.1%} fraction refuses it — a two-instruction routine "
        f"cannot pay that for a pointer load")


def test_the_rule_refuses_a_row_it_does_not_name(bench, dispatch):
    """The NAMING is the claim, and it is the half neither slack can make.

    `IMAGE_POINTER_LEAVES` says "(A) is the whole of this row's excess", which only a reader of the
    ROM's instructions and the C's can assert. Drop that test from the rule and every small excess
    anywhere becomes admissible — including one that is small for a reason nobody looked at — so an
    unnamed row is driven here with an excess of two cycles, where nothing but the naming refuses it.
    """
    row = tier3.row_named(UNNAMED_ROW)
    assert UNNAMED_ROW not in tier3.IMAGE_POINTER_LEAVES, "the premise: this row is not named"
    measured = tier3.measure(row, bench)
    assert not tier3.rule_admits(row, _carrying(measured, bench, TRIVIAL_EXCESS), dispatch), (
        f"the leaf rule admitted {UNNAMED_ROW}, which it does not name — the rule is no longer "
        f"asking whether anybody has read the row, only whether its excess is small")


def test_a_transcription_rows_ratio_is_netted_by_the_caller_it_measured(bench):
    """The plumbing between `trap.py`'s measured caller and the `Measurement` that uses it.

    `test_rom_bench.py` pins the arithmetic and `test_bios_trap.py` pins the constant; what neither
    can see is the row carrying the wrong one, or none. Netting a 642-cycle call by 106 instead of
    by nothing moves its ratio by less than the table prints, so this is the only surface the wiring
    has.
    """
    row = tier3.row_named(tier3.DISPATCH_WHOLE_CALL)
    assert row.shared_entry == trap.caller_cost(), (
        f"{tier3.DISPATCH_WHOLE_CALL} carries {row.shared_entry} as the caller both sides run, not "
        f"the {trap.caller_cost()} its own shape measures")
    measured = tier3.measure(row, bench)
    assert measured.original_net == \
        measured.original_cycles - RESET_OBSERVATION[1] - row.shared_entry[1]


def test_no_named_leaf_has_come_back_under_the_bar(bench, dispatch):
    """A name whose row no longer needs it is `PERF_ACCEPTED`'s staleness, in the rule's shape: it
    would go on admitting the next regression on that row without anybody deciding to."""
    for key in sorted(tier3.IMAGE_POINTER_LEAVES):
        row = tier3.row_named(key)
        assert tier3.measure(row, bench).ratio > tier3.TIER3_FUNCTION_BAR, (
            f"{key} is named an (A)-only leaf the rule carries, but it now measures under the "
            f"{tier3.TIER3_FUNCTION_BAR:.2f} bar on its own. Drop the name")


# What Musashi's reset exception costs, and what it therefore adds to EVERY run of either entry
# point: one observed instruction that executes nothing, and the 68000's own 40-cycle reset. Named
# here rather than in the kit because this is the pin, not the mechanism — `RomBench` measures the
# pair on an empty function and requires the two doors to agree; this says what the answer is, so a
# CPU model whose reset cost changed reddens here instead of quietly moving every ratio.
RESET_OBSERVATION = (1, 40)


def test_the_entry_overhead_is_the_reset_and_nothing_else(bench):
    assert bench.overhead == RESET_OBSERVATION, (
        f"the oracle charges {bench.overhead} (insns, cycles) before an entry executes anything, "
        f"not the {RESET_OBSERVATION} a 68000's reset exception costs. Every Tier 3 ratio is "
        f"computed net of that number, so it has to be the right one")
