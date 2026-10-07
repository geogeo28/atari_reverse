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
import copy
import ctypes
import functools
import gc
import os
import re
import signal
import struct
import subprocess
import sys
import types
import weakref
from collections import namedtuple
from pathlib import Path

import pytest

from harness import BASE_IMAGE, BENCH_DIR

sys.path.insert(0, str(BENCH_DIR))

import tier3                                               # noqa: E402  (the registry and the bar)
# ...and the caller a transcription row is netted by, whose cost `trap.py` measures.
import trap                                                # noqa: E402
# ...and the VDI's door and pure helpers, whose declared contracts and C signatures the VDI calls derive from.
import aes                                                 # noqa: E402
import aes_event                                           # noqa: E402
import case                                                # noqa: E402
import fork_pool                                           # noqa: E402
import routines                                            # noqa: E402
import transcription                                       # noqa: E402
import vdi                                                 # noqa: E402
import vdi_helpers                                         # noqa: E402
# ...and the glue generator, whose thunks mechanism (T→G) counts.
import shipped_glue                                        # noqa: E402
from recreate_kit import rom_bench                          # noqa: E402
from recreate_kit.rom_bench import Measurement, RomBench   # noqa: E402
from harness import addrs, emu, make_image                  # noqa: E402
import opcodes                                             # noqa: E402
import staging                                             # noqa: E402
import test_aes_fmdo                                       # noqa: E402
import test_boot_snapshot                                  # noqa: E402


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


@pytest.fixture(scope="module")
def sessions(bench):
    """The sessions measured, once per worker (`tier3.Sessions`): a session's sliced rows share one pair of runs."""
    return tier3.Sessions(bench)


@pytest.fixture(scope="module")
def measurement_of(bench, sessions):
    """A row's `Measurement`, measured once per worker — mechanism (T) asks it of a routine's `.S` rows
    for each of its C rows, and those are the same few rows every time."""
    measured = {}

    def measurement(row):
        key = (row.symbol, row.case)
        if key not in measured:
            measured[key] = tier3.measure(row, bench, sessions)
        return measured[key]
    return measurement


def _row_id(row):
    return f"{row.symbol}-{row.case}"


def _sliced_session_of_a_case(params):
    """The SLICED session a case is about, by what it is parametrized over — a Tier 3 row (`row`), a registered row's
    name (`name`) or a row's key (`key`) — as the group it is collected with (`test/conftest.py`); None for every
    other case. A session's rows, its companions and its partition then run back to back, on the worker that holds
    its one pair of runs (`sessions`) and its one companion's (`_COMPANIONS_RUN`)."""
    row, name, key = params.get("row"), params.get("name"), params.get("key")
    if isinstance(key, tuple) and key in ROWS_BY_KEY:
        row = ROWS_BY_KEY[key]
    if isinstance(row, tier3.Row):
        name = row.registered
    if not isinstance(name, str) or name not in aes_event.SLICED_ROWS:
        return None
    return next(row_name for row_name, session in aes_event.INTERRUPTED_ROWS.items() if session is aes_event.session_of(name))


ROWS_BY_KEY = {(row.symbol, row.case): row for row in tier3.ROWS}


# ---- the measuring pass spread over processes (`tier3.measured_rows`) --------------------------------------------------
def _printed_of(row, measured):
    """Every figure the table prints of a row, and the lines it prints below it."""
    figures = (tier3._costs(measured), measured.ratio, tier3.gated_ratio(row, measured), tier3.glue_cycles_of(measured))
    below = [tier3._through_the_os_line(measured, 0)] if tier3.goes_through_the_os(row) else []
    below += [tier3._own_split_line(measured, 0)] if tier3.calls_into_c(row) else []
    return figures, below


def _a_sample_of_shares():
    """One share in every SAMPLE_EVERY of the single rows — and the sliced session of the fewest rows, whole."""
    shares = tier3._shares(tier3.ROWS)
    sessions = [share for share in shares if len(share) > 1]
    return [min(sessions, key=len), *[share for share in shares if len(share) == 1][::SAMPLE_EVERY]]


SAMPLE_EVERY = 40
FORKS = 3


def test_the_shares_are_every_row_once_and_a_session_s_rows_together():
    shares = tier3._shares(tier3.ROWS)
    assert sorted(index for share in shares for index in share) == list(range(len(tier3.ROWS)))
    sliced = [share for share in shares if tier3.ROWS[share[0]].slice]
    assert sliced and sliced == shares[:len(sliced)], "the sessions are not measured first"
    for share in sliced:
        session = tier3.session_of(tier3.ROWS[share[0]])
        assert [tier3.ROWS[index] for index in share] == tier3.rows_of_the_session(session)
    assert all(len(share) == 1 for share in shares[len(sliced):])


def test_rows_measured_by_forks_are_the_rows_measured_in_process(bench):
    """THE TABLE'S OWN PREMISE, on a sample (the whole table by `--jobs 1` and by any other count is held equal line
    for line when the mechanism changes — recreate/README.md): a measurement made in a fork and sent back is, figure
    for figure and line for line, the one this process makes — a session's sliced rows, priced off one pair of
    runs, among them — and comes back in ROWS' order whatever order the forks finished in."""
    sample = _a_sample_of_shares()
    assert len(sample) > 20 and len(sample[0]) > 1
    here = tier3.measured_rows(bench, shares=sample)
    forked = tier3.measured_rows(bench, FORKS, shares=sample)
    assert [row for row, _measured in forked] == [row for row, _measured in here]
    assert [row for row, _measured in here] == [tier3.ROWS[index] for index in sorted(sum(sample, []))]
    for (row, ours), (_row, theirs) in zip(here, forked):
        assert _printed_of(row, theirs) == _printed_of(row, ours), f"{row.symbol} / {row.case}"


@pytest.mark.parametrize("jobs", (tier3.SERIAL, FORKS), ids=("in process", "by forks"))
def test_a_row_whose_measurement_is_refused_ends_the_pass_by_the_first_such_row(bench, monkeypatch, jobs):
    """A row's measurement is its second differential: one that raises ends the pass — in a fork, it is carried back
    and raised here — and of two, the one FIRST in ROWS' order is the one that speaks, as in a serial pass."""
    sample = [share for share in tier3._shares(tier3.ROWS) if len(share) == 1][::SAMPLE_EVERY][:8]
    refused = [tier3.ROWS[sample[index][0]] for index in (5, 2)]
    first = tier3.ROWS[min(sample[2][0], sample[5][0])]
    measure = tier3.measure

    def refusing(row, *named):
        assert not any(row is each for each in refused), f"refused: {row.symbol} / {row.case}"
        return measure(row, *named)
    monkeypatch.setattr(tier3, "measure", refusing)
    with pytest.raises(AssertionError, match="refused: " + re.escape(f"{first.symbol} / {first.case}")):
        tier3.measured_rows(bench, jobs, shares=sample[::-1])


def test_a_fork_that_dies_measuring_a_row_ends_the_pass_by_name(bench, monkeypatch):
    """THE RED for a bench that HANGS on a dead fork (a segfault of the oracle, an out-of-memory kill): the pass was a
    `multiprocessing.Pool`'s, which starts another worker and waits for the lost share for ever — `make bench`, a
    prerequisite of every gate, still waiting after 45 s (measured). The pass ends, by name, with no table."""
    sample = [share for share in tier3._shares(tier3.ROWS) if len(share) == 1][::SAMPLE_EVERY][:8]
    victim = tier3.ROWS[sample[3][0]]
    measure = tier3.measure

    def dying(row, *named):
        if row is victim:
            os.kill(os.getpid(), signal.SIGKILL)
        return measure(row, *named)
    monkeypatch.setattr(tier3, "measure", dying)
    with pytest.raises(fork_pool.Died, match="tier3's measuring pass: a fork DIED"):
        tier3.measured_rows(bench, FORKS, shares=sample)


def test_every_row_asked_for_comes_back_or_the_pass_says_which_did_not(bench, monkeypatch):
    """...and a share that comes back without one of its rows (no fork died, nothing raised) is not a shorter table:
    the pass is held to the rows it was asked for."""
    sample = [share for share in tier3._shares(tier3.ROWS) if len(share) == 1][::SAMPLE_EVERY][:4]
    measured_in_a_fork = tier3._measured_in_a_fork
    monkeypatch.setattr(tier3, "_measured_in_a_fork", lambda share: [] if share == sample[1] else measured_in_a_fork(share))
    with pytest.raises(AssertionError, match="asked for 4 rows and 3 came back: missing"):
        tier3.measured_rows(bench, shares=sample)
pytestmark = pytest.mark.collected_with(by=_sliced_session_of_a_case)


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
def test_the_m68k_build_equals_the_original_and_is_within_the_bar(row, bench, dispatch, measurement_of, sessions):
    """One row: measure both sides over one case — which raises if the m68k build diverged — then
    put the measurement through the same `verdict` the table prints. (A session's sliced rows are measured
    off one pair of runs, `sessions`: each still raises for itself.)"""
    measured = tier3.measure(row, bench, sessions)
    state = tier3.verdict(row, measured, dispatch, measurement_of)
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
    if tier3.is_transcribed_c_row(row):
        return (f"{cost}, over the {tier3.TIER3_FUNCTION_BAR:.2f} bar — and the routine is TRANSCRIBED "
                f"(include/transcribed.h), but its `.S` rows no longer carry it: one is over the bar and not "
                f"`own` (T←), or there is none. Mechanism (T) admits the C only while the `.S` a target build ships "
                f"is priced at or under the bar on every row — or, where it calls C, on its own instructions")
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
        assert tier3.gated_ratio(rows[key], measured) > tier3.TIER3_FUNCTION_BAR, (
            f"tier3.PERF_ACCEPTED carries {key} as an ACCEPTANCE ({pinned:.3f}x, over the "
            f"{tier3.TIER3_FUNCTION_BAR:.2f} bar), but it now measures {tier3.gated_ratio(rows[key], measured):.3f}x — "
            f"under it. Drop the acceptance: it is excusing a cost that is no longer paid")


# ---- the numerator's flags: the target build keeps the ROM's read-after-store order ------------------

RECREATE = Path(__file__).resolve().parents[1]
# The flag `atari/target.mk` carries for it (its comment says why), and every expansion that must carry it:
# the ROM build's, and both Tier 3 blobs' — the C twins' and the shipped configuration's.
NO_STRICT_ALIASING = "-fno-strict-aliasing"
TARGET_FLAG_EXPANSIONS = ((RECREATE, "BENCH_CFLAGS"), (RECREATE, "SHIPPED_CFLAGS"), (RECREATE / "atari", "CFLAGS"))


def _expanded(directory, variable):
    """`variable` as the makefile in `directory` expands it — make's answer, not a reading of the text."""
    probe = f"include Makefile\nprint-flags:\n\t@echo $({variable})\n"
    return subprocess.run(["make", "-s", "-f", "-", "print-flags"], input=probe, cwd=directory, capture_output=True,
                          text=True, check=True).stdout.split()


@pytest.mark.parametrize("directory, variable", TARGET_FLAG_EXPANSIONS, ids=lambda each: str(each))
def test_every_target_build_compiles_without_type_based_aliasing(directory, variable):
    assert NO_STRICT_ALIASING in _expanded(directory, variable), (
        f"{variable} ({directory.name}/Makefile) lacks {NO_STRICT_ALIASING}: GCC may then carry a read across a "
        f"store of another width, which the ROM never does and only an overlap case on target would show")


# ---- the VDI helpers' calls: ONE statement of each C signature --------------------------------------

REGISTER_HELPERS = [name for name in vdi.PRIMITIVES if routines.core_symbol(name) in vdi_helpers.REGISTER_SIGNATURES]


@pytest.mark.parametrize("name", REGISTER_HELPERS)
def test_a_register_helper_s_host_signature_is_its_declared_contract(name):
    """The Alcyon helpers' Tier 3 calls are DERIVED from `vdi.ALCYON`; the three register routines' come
    from `vdi.declare_primitive` instead, so this is where the two statements of one C signature are held
    equal: the image, a longword per argument register, a results pointer when the answer is several
    registers, and D0 returned when it is among them."""
    contract = vdi.PRIMITIVES[name]
    restype, argtypes = vdi_helpers.REGISTER_SIGNATURES[routines.core_symbol(name)]
    several = (ctypes.POINTER(vdi.LONG_ARG),) if len(contract.results) > 1 else ()
    assert tuple(argtypes) == (vdi.IMAGE_ARG, *(vdi.LONG_ARG,) * len(contract.arguments), *several)
    assert (restype is vdi.LONG_ARG) == ("d0" in contract.results)


# ---- MECHANISM (T): a TRANSCRIBED routine's C rows, carried by its `.S` rows and by nothing else ----

# A C row (T) carries — far over the bar, so no pin or leaf rule could be what admits it instead.
TRANSCRIBED_C_ROW = ("linea_hline", "one pixel, replace")


def test_every_transcribed_routine_ships_a_priced_s_row():
    """(T) is only as good as the `.S` rows it reads: a TRANSCRIBED routine with none has nothing to be
    carried by, and its C rows would red — this names the routine instead of each of its rows."""
    unpriced = sorted(tier3.TRANSCRIBED_AT[address] for address, rows in tier3.SHIPPED_ROWS.items() if not rows)
    assert not unpriced, (f"{unpriced} are in include/transcribed.h with no `.S` row in Tier 3 — register "
                          f"their transcription cases (`transcription.register_transcription`)")


def test_no_transcribed_c_row_carries_a_written_acceptance():
    """The rule REPLACES the entries: an acceptance beside it would carry the C rows on its own the day
    the `.S` stopped doing so, which is exactly the state (T) exists to refuse."""
    written = sorted(key for key in tier3.PERF_ACCEPTED if tier3.is_transcribed_c_row(tier3.row_named(key)))
    assert not written, f"tier3.PERF_ACCEPTED writes down {written}, which mechanism (T) carries — drop them"


def test_the_rule_carries_a_transcribed_c_row(bench, dispatch, measurement_of):
    row = tier3.row_named(TRANSCRIBED_C_ROW)
    measured = tier3.measure(row, bench)
    assert measured.ratio > tier3.TIER3_FUNCTION_BAR, "the premise: this C row is over the bar"
    assert tier3.verdict(row, measured, dispatch, measurement_of) == "transcribed"


def test_one_s_row_drifting_over_the_bar_reds_the_c_rows(bench, dispatch, measurement_of):
    """Every `.S` row but one measured as it is, that one just over the bar: the C row goes OVER."""
    row = tier3.row_named(TRANSCRIBED_C_ROW)
    measured = tier3.measure(row, bench)
    drifted = tier3.SHIPPED_ROWS[tier3.rom_address(row)][-1]
    over = tier3.TIER3_FUNCTION_BAR + tier3.RATIO_TOLERANCE

    def with_one_drifted(each):
        return _ratio_only(over) if each is drifted else measurement_of(each)
    assert tier3.verdict(row, measured, dispatch, with_one_drifted) == "OVER"


def test_a_routine_whose_s_rows_are_gone_reds_the_c_rows(bench, dispatch, measurement_of, monkeypatch):
    row = tier3.row_named(TRANSCRIBED_C_ROW)
    measured = tier3.measure(row, bench)
    monkeypatch.setitem(tier3.SHIPPED_ROWS, tier3.rom_address(row), ())
    assert tier3.verdict(row, measured, dispatch, measurement_of) == "OVER"


def _ratio_only(ratio):
    """A `.S` row's measurement reduced to the one number (T) reads of a routine that calls no C."""
    return types.SimpleNamespace(ratio=ratio)


def test_a_written_entry_for_a_s_row_carries_no_c_row(bench, dispatch, measurement_of, monkeypatch):
    """(T) is STRICT: a `.S` row over the bar with an acceptance of its own does not carry its routine's C rows — the
    entry would say nothing about the C, and it once carried the escape's whole C twin on 24 of them."""
    row = tier3.row_named(TRANSCRIBED_C_ROW)
    measured = tier3.measure(row, bench)
    pinned = tier3.SHIPPED_ROWS[tier3.rom_address(row)][0]
    over = tier3.TIER3_FUNCTION_BAR + tier3.RATIO_TOLERANCE
    monkeypatch.setitem(tier3.PERF_ACCEPTED, (pinned.symbol, pinned.case), (over, "an entry for a `.S` row"))

    def with_the_pinned_one_over(each):
        return _ratio_only(over) if each is pinned else measurement_of(each)
    assert tier3.verdict(row, measured, dispatch, with_the_pinned_one_over) == "OVER"


# ---- MECHANISM (T←): a `.S` that calls C through thunks of its own, carried on its OWN instructions ------------

# An escape `.S` row the console's C takes far over the bar, whose own instructions are the ROM's to the cycle...
OWN_ROW = ("vdi_rom_escape", "v_curup, the cursor drawn")
# ...and one of the escape's C rows, which (T) carries only while every `.S` row is within the bar or `own`.
ESCAPE_C_ROW = ("vdi_escape", "v_curup, the cursor drawn")
# ...and one that jumps to a ROM routine both sides run from the same bytes, so its own instructions are a sliver of it.
SHARED_CODE_ROW = ("vdi_rom_escape", "v_dspcur, forced")
# The cheapest spill there is: one callee-saved register pushed and popped round the dispatch, `move.l %d2,-(%sp)` /
# `move.l (%sp)+,%d2`, 12 cycles each. A private blob with exactly that in escape.S measured the row's own ratio at 1.27.
SPILL_CYCLES = 24


def _with_own_spill(measured, cycles):
    """`measured` with `cycles` more on OUR side, every one of them inside the `.S`'s own instructions."""
    spilled = copy.copy(measured)
    spilled.recreate_cycles += cycles
    ours, original = measured.own_cycles
    spilled.own_cycles = (ours + cycles, original)
    return spilled


def test_the_own_rule_carries_a_s_row_over_the_bar_by_its_own_instructions(dispatch, measurement_of):
    row = tier3.row_named(OWN_ROW)
    measured = measurement_of(row)
    assert measured.ratio > tier3.TIER3_FUNCTION_BAR, "the premise: the console's C takes this row over the bar"
    assert tier3.pin_of(row) is None, "the rule carries it, so no entry may"
    ours, original = measured.own_cycles
    assert ours == original, "the escape's own instructions are the ROM's, byte for byte, so they cost the ROM's"
    assert tier3.verdict(row, measured, dispatch, measurement_of) == "own"


def test_a_spill_in_the_s_own_instructions_reds_its_row(dispatch, measurement_of):
    row = tier3.row_named(OWN_ROW)
    spilled = _with_own_spill(measurement_of(row), SPILL_CYCLES)
    assert tier3.own_ratio(spilled) > tier3.TIER3_FUNCTION_BAR
    assert tier3.verdict(row, spilled, dispatch, measurement_of) == "OVER"


def test_a_spill_reds_a_row_even_under_the_bar(dispatch, measurement_of):
    """A row that only jumps to code both sides share (v_dspcur's v_show_c) is under the bar as a whole — the spill
    must not hide in that average."""
    row = tier3.row_named(SHARED_CODE_ROW)
    spilled = _with_own_spill(measurement_of(row), SPILL_CYCLES)
    assert spilled.ratio <= tier3.TIER3_FUNCTION_BAR, "the premise: the whole row stays under the bar"
    assert tier3.verdict(row, spilled, dispatch, measurement_of) == "OVER"


def test_a_spilled_s_row_no_longer_carries_the_c_rows(bench, dispatch, measurement_of):
    row = tier3.row_named(ESCAPE_C_ROW)
    measured = tier3.measure(row, bench)
    assert measured.ratio > tier3.TIER3_FUNCTION_BAR, "the premise: the escape's C twin is over the bar"
    assert tier3.verdict(row, measured, dispatch, measurement_of) == "transcribed"
    spilled_row = tier3.row_named(OWN_ROW)

    def with_one_spilled(each):
        return _with_own_spill(measurement_of(each), SPILL_CYCLES) if each is spilled_row else measurement_of(each)
    assert tier3.verdict(row, measured, dispatch, with_one_spilled) == "OVER"


@pytest.mark.parametrize("cited", tier3.CONSOLE_C_ACCEPTED_BY, ids=lambda key: key[1])
def test_the_own_rule_carries_nothing_without_each_acceptance_it_cites(cited, dispatch, measurement_of, monkeypatch):
    """The rest of a (T←) row is the console's C, and its cost is carried where the console's own rows are accepted —
    CITED, not re-typed: delete one of those acceptances and the escape's rows go OVER with it."""
    row = tier3.row_named(OWN_ROW)
    measured = measurement_of(row)
    monkeypatch.delitem(tier3.PERF_ACCEPTED, cited)
    assert tier3.verdict(row, measured, dispatch, measurement_of) == "OVER"


@pytest.mark.parametrize("cited", tier3.CONSOLE_C_ACCEPTED_BY, ids=lambda key: key[1])
def test_every_cited_acceptance_is_a_console_row_accepted_over_the_bar(cited):
    row = tier3.row_named(cited)
    assert row.entry == addrs.BIOS_BCONOUT and row.case.startswith("console"), cited
    assert tier3.PERF_ACCEPTED[cited][0] > tier3.TIER3_FUNCTION_BAR


def test_no_written_acceptance_names_a_row_the_own_rule_carries(bench):
    """The rule REPLACES the escape's entries, as (T) and (T→G) replace theirs: a written entry for a `.S` row the own
    rule carries would outlive the day the `.S`'s own instructions grew."""
    carried = [key for key in tier3.PERF_ACCEPTED
               if tier3.calls_into_c(row := tier3.row_named(key))
               and tier3.carried_by_its_own_instructions(row, tier3.measure(row, bench))]
    assert not carried, f"tier3.PERF_ACCEPTED writes down {carried}, which mechanism (T←) carries — drop them"


# ---- MECHANISM (T→): the C that calls a transcribed routine, measured as it ships -------------------

@functools.cache
def _shipped_measurement(key):
    """A (T→) row's `Measurement`, once per process: the shipped blob prices it whatever bench is handed, and
    no test mutates it (`_with_body_grown_to` builds a new one)."""
    row = tier3.row_named(key)
    assert tier3.ships_through_a_call(row), key
    return tier3.measure(row, tier3.shipped_bench())


# A row whose whole excess, measured on the C twins, is the callee's C: far over the bar there, and at the
# ROM's cost once the call enters the `.S` — so which blob measured it is unmistakable.
THROUGH_A_CALL_ROW = ("vdi_v_hide_c", "the arrow removed")


def test_every_c_caller_of_a_transcribed_core_ships_through_a_call():
    """The rows (T→) measures as shipped include every direct caller the door names: the reach is DERIVED
    from the m68k build's call graph, and a caller outside it would be priced with the C twin in it."""
    callers = {caller for caller, _core in transcription.C_CALLERS_OF_TRANSCRIBED_CORES}
    assert callers <= tier3._reaching_transcribed_cores()


def test_a_row_that_ships_through_a_call_is_measured_on_the_shipped_blob(bench, dispatch, measurement_of):
    row = tier3.row_named(THROUGH_A_CALL_ROW)
    assert tier3.ships_through_a_call(row)
    on_the_twins = bench.measure(row.entry, row.symbol, args=row.args, regs=row.regs, pokes=row.pokes,
                                 returns=row.returns)
    assert on_the_twins.ratio > tier3.TIER3_FUNCTION_BAR, "the premise: through the C twin it is over the bar"
    measured = _shipped_measurement(THROUGH_A_CALL_ROW)
    assert measured.ratio <= tier3.TIER3_FUNCTION_BAR
    assert tier3.verdict(row, measured, dispatch, measurement_of) == "through"


def test_a_row_that_ships_through_a_call_goes_over_with_its_callee(bench, dispatch, measurement_of):
    """Nothing carries a (T→) row but its own measurement: the same row costing what a drifted `.S` would
    make it cost — the thunks' cycles unchanged, everything behind them over the bar — is OVER; there is no
    entry for it to hide behind, and the glue rule (T→G) takes off only the thunks."""
    row = tier3.row_named(THROUGH_A_CALL_ROW)
    measured = _shipped_measurement(THROUGH_A_CALL_ROW)
    over = _with_body_grown_to(measured, bench, tier3.TIER3_FUNCTION_BAR + tier3.RATIO_TOLERANCE)
    assert tier3.pin_of(row) is None
    assert tier3.verdict(row, over, dispatch, measurement_of) == "OVER"


# ---- the CALL GRAPH (T→) is derived from: its IMMEDIATE-ADDRESS rule, on a synthetic listing ---------------
# GCC calls a function it names several times through a register it loaded with `move.l #<address>`, which
# objdump prints in DECIMAL and without the name — so only the symbol table can say it is a call. Nothing
# in today's build reaches a transcribed core that way (the rule's edges are GEMDOS callbacks), so no row
# would redden if it went: this listing is its pin.
LOADER_AT, HELPER_AT, INSIDE_HELPER = 0x30000, 0x30100, 0x30102
IMMEDIATE_CALL_LISTING = f"""
{LOADER_AT:08x} <loader>:
   {LOADER_AT:x}:\t243c 0003 0100 \tmovel #{HELPER_AT},%d2
   {LOADER_AT + 6:x}:\t4e92           \tjsr %a2@
   {LOADER_AT + 8:x}:\t263c 0003 0102 \tmovel #{INSIDE_HELPER},%d3
{HELPER_AT:08x} <helper>:
   {HELPER_AT:x}:\t4e75           \trts
"""


def test_the_call_graph_reads_an_address_loaded_as_an_immediate():
    """`#<decimal>` equal to a function's START is a reference to it; one inside a function is not."""
    starts = {LOADER_AT: "loader", HELPER_AT: "helper"}
    graph = transcription.graph_of_listing(IMMEDIATE_CALL_LISTING, {}, starts)
    assert graph == {"loader": {"helper"}, "helper": set()}


# ...and the same immediate used as DATA: compared, and stored into the image (a Line-A field), where no call
# can follow — the value only happens to equal a function's start.
COMPARER_AT = 0x30200
IMMEDIATE_DATA_LISTING = f"""
{COMPARER_AT:08x} <comparer>:
   {COMPARER_AT:x}:\t0c80 0003 0100 \tcmpil #{HELPER_AT},%d0
   {COMPARER_AT + 6:x}:\t277c 0003 0100 2958 \tmovel #{HELPER_AT},%a3@(10584)
   {COMPARER_AT + 14:x}:\t0681 0003 0100 \taddil #{HELPER_AT},%d1
{HELPER_AT:08x} <helper>:
   {HELPER_AT:x}:\t4e75           \trts
"""


def test_the_call_graph_reads_no_call_into_an_immediate_used_as_data():
    starts = {COMPARER_AT: "comparer", HELPER_AT: "helper"}
    graph = transcription.graph_of_listing(IMMEDIATE_DATA_LISTING, {}, starts)
    assert graph == {"comparer": set(), "helper": set()}


# ...and the QUALIFICATION of a name several functions share, by where each is DEFINED (`transcription.symbol_origins`): two
# statics' CLONES (`.isra.0` in one file, `.constprop.0` in another) are two functions, where folding the suffixes
# alone merged them; a global and the clone GCC split off it in its own file are one.
FIRST_CLONE_AT, SECOND_CLONE_AT, GLOBAL_AT, PART_AT, LEFT_AT, RIGHT_AT = 0x31000, 0x31100, 0x31200, 0x31300, 0x31400, 0x31500
CLONES_LISTING = f"""
{FIRST_CLONE_AT:08x} <outline.isra.0>:
   {FIRST_CLONE_AT:x}:\t4eb9 0003 1400 \tjsr {LEFT_AT:x} <left>
{SECOND_CLONE_AT:08x} <outline.constprop.0>:
   {SECOND_CLONE_AT:x}:\t4eb9 0003 1500 \tjsr {RIGHT_AT:x} <right>
{GLOBAL_AT:08x} <vdi_row>:
   {GLOBAL_AT:x}:\t6100 00fe      \tbsrw {PART_AT:x} <vdi_row.part.0>
{PART_AT:08x} <vdi_row.part.0>:
   {PART_AT:x}:\t4eb9 0003 1400 \tjsr {LEFT_AT:x} <left>
{LEFT_AT:08x} <left>:
   {LEFT_AT:x}:\t4e75           \trts
{RIGHT_AT:08x} <right>:
   {RIGHT_AT:x}:\t4e75           \trts
"""
CLONES_ORIGINS = {(FIRST_CLONE_AT, "outline.isra.0"): "a.c", (SECOND_CLONE_AT, "outline.constprop.0"): "b.c",
                  (GLOBAL_AT, "vdi_row"): transcription.GLOBAL_ORIGIN, (PART_AT, "vdi_row.part.0"): "row.c",
                  (LEFT_AT, "left"): transcription.GLOBAL_ORIGIN, (RIGHT_AT, "right"): transcription.GLOBAL_ORIGIN}


def test_the_call_graph_keeps_two_statics_clones_apart_and_folds_a_globals_own():
    graph = transcription.graph_of_listing(CLONES_LISTING, {}, {}, CLONES_ORIGINS)
    assert graph == {"outline@a.c": {"left"}, "outline@b.c": {"right"}, "vdi_row": {"left"}, "left": set(),
                     "right": set()}


# A reference with no address printed, to a name two functions share: it cannot say which, so it names both — an
# edge too many prices a row on the shipped blob, where the refusal it met before stopped the whole graph.
ADDRESSLESS_LISTING = CLONES_LISTING + f"""
{RIGHT_AT + 0x100:08x} <caller>:
   {RIGHT_AT + 0x100:x}:\t4ebb 0000      \tjsr %pc@(0) <outline.isra.0>
"""


def test_the_call_graph_reads_an_addressless_reference_to_a_shared_name_as_every_one_of_them():
    origins = {**CLONES_ORIGINS, (RIGHT_AT + 0x100, "caller"): transcription.GLOBAL_ORIGIN}
    graph = transcription.graph_of_listing(ADDRESSLESS_LISTING, {}, {}, origins)
    assert graph["caller"] == {"outline@a.c", "outline@b.c"}


@pytest.mark.parametrize("symbol", ("vdi_v_clswk", sorted(transcription.TRANSCRIBED_CORES)[0]))
def test_a_row_symbol_the_call_graph_qualified_is_refused(symbol):
    """A static sharing a Tier 3 row's (or a transcribed core's) name: the name is ambiguous in the graph (T→) is
    derived from, and the gate says so rather than pricing the row on whichever node the bare name finds."""
    graph = {symbol: set(), f"{symbol}@other.c": set()}
    with pytest.raises(AssertionError, match=symbol):
        tier3.vet_no_row_is_ambiguous(graph)
    tier3.vet_no_row_is_ambiguous({symbol: set()})


# ---- MECHANISM (T→G): a (T→) row over the bar only by the cycles of the thunks it calls through ------------

# The row the glue carries: do_arrow's arrowhead, whose shipped excess is 94% thunk (13 smul_div calls, 8
# filled_poly ones) and whose C bodies are at parity net of them.
GLUE_ROW = ("vdi_do_arrow", "one-pixel line, walked past short segments")
# ...and a row over the bar EVEN NET of its glue: vq_key_s's own (A) + (D) body, which only its written entry
# carries — the real row the rule must refuse.
OVER_NET_OF_GLUE_ROW = ("vdi_vq_key_s", "every bit set but Control")


def _with_body_grown_to(measured, bench, net_ratio):
    """`measured` with the recreate's cycles OUTSIDE the glue grown until its net ratio is `net_ratio`: the
    shape a regression in the caller's own body would have, the thunks' cycles left as they were."""
    glue = tier3.glue_cycles_of(measured)
    grown = Measurement((0, measured.original_cycles), (0, round(net_ratio * measured.original_net) + glue + bench.overhead[1]),
                        bench.overhead)
    grown.glue_cycles = glue
    return grown


def test_every_thunk_is_a_sized_range_of_the_shipped_blob():
    """The glue the rule counts is exactly the generated thunks and the Alcyon entries: one disjoint sized range each."""
    ranges = tier3.glue_ranges()
    assert len(ranges) == len(shipped_glue.thunked_cores()) + len(tier3.ALCYON_ENTRIES)
    assert all(start < end <= following for (start, end), (following, _) in zip(ranges, ranges[1:])), ranges


def test_the_glue_rule_carries_a_row_over_the_bar_only_by_its_thunks(bench, dispatch, measurement_of):
    row = tier3.row_named(GLUE_ROW)
    measured = _shipped_measurement(GLUE_ROW)
    assert measured.ratio > tier3.TIER3_FUNCTION_BAR, "the premise: as shipped this row is over the bar"
    assert tier3.pin_of(row) is None, "the rule carries it, so no entry may"
    assert tier3.ratio_net_of_glue(measured) <= tier3.TIER3_FUNCTION_BAR
    assert tier3.verdict(row, measured, dispatch, measurement_of) == "glue"


def test_the_glue_rule_refuses_the_row_when_its_own_body_grows(bench, dispatch, measurement_of):
    """The same row with its glue unchanged and its BODY past the bar net of it: OVER, and nothing else."""
    row = tier3.row_named(GLUE_ROW)
    measured = _shipped_measurement(GLUE_ROW)
    grown = _with_body_grown_to(measured, bench, tier3.TIER3_FUNCTION_BAR + tier3.RATIO_TOLERANCE)
    assert tier3.ratio_net_of_glue(grown) > tier3.TIER3_FUNCTION_BAR
    assert tier3.verdict(row, grown, dispatch, measurement_of) == "OVER"


def test_the_glue_rule_refuses_a_real_row_over_the_bar_net_of_its_glue(bench, dispatch, measurement_of, monkeypatch):
    """RED on a measured row, not a made-up one: vq_key_s pays glue too, but its body alone is over the bar,
    so with its written entry gone the rule leaves it OVER."""
    row = tier3.row_named(OVER_NET_OF_GLUE_ROW)
    measured = _shipped_measurement(OVER_NET_OF_GLUE_ROW)
    assert tier3.glue_cycles_of(measured) > 0, "the premise: this row calls through a thunk"
    assert tier3.ratio_net_of_glue(measured) > tier3.TIER3_FUNCTION_BAR
    monkeypatch.delitem(tier3.PERF_ACCEPTED, OVER_NET_OF_GLUE_ROW)
    assert tier3.verdict(row, measured, dispatch, measurement_of) == "OVER"


def test_no_written_acceptance_is_for_a_row_the_glue_rule_carries(bench):
    """The rule REPLACES such entries, as (T)'s does: an acceptance over the bar for a (T→) row is only for a
    body that is over the bar NET of its glue — the day it is not, the entry goes."""
    carried = []
    for key, (pinned, _why) in tier3.PERF_ACCEPTED.items():
        row = tier3.row_named(key)
        if pinned > tier3.TIER3_FUNCTION_BAR and tier3.ships_through_a_call(row):
            if tier3.ratio_net_of_glue(tier3.measure(row, bench)) <= tier3.TIER3_FUNCTION_BAR:
                carried.append(key)
    assert not carried, f"tier3.PERF_ACCEPTED writes down {carried}, which mechanism (T→G) carries — drop them"


# ---- MECHANISM (V): C that reaches the VDI by `trap #2`, priced on the AES's own cycles -----------------------------
# A drawing call whose whole run is the ROM's VDI on both sides (the polyline's 31,000 cycles round its AES wrapper's
# few hundred), and a body the rule cannot carry: gsx_moff's open nest, where nothing is shared and its own ratio is
# the whole one — over the bar by the image pointer, (A), and accepted at that number.
OS_ROW = ("aes_v_pline", "a triangle")
OS_ROW_ACCEPTED = ("aes_gsx_moff", "the nest already open")
# A cost moved into the OS both run, as a refused measurement stages it: one instruction's worth.
SHARED_CYCLES_MOVED = 4
# A body delayed by a loop of about this many cycles: the size of spill the rule exists to see, and a fraction of the
# polyline's whole run the whole-run ratio would never notice.
DELAY_CYCLES = 2000


def _with_own_delay(measured, cycles):
    """`measured` with `cycles` more on OUR side, every one of them inside the AES's own C."""
    delayed = copy.copy(measured)
    delayed.recreate_cycles += cycles
    ours, original = measured.own_cycles
    delayed.own_cycles = (ours + cycles, original)
    return delayed


def test_a_row_through_the_os_is_priced_on_its_own_cycles(dispatch, measurement_of):
    row = tier3.row_named(OS_ROW)
    measured = measurement_of(row)
    ours, original = measured.own_cycles
    assert 0 < ours < measured.recreate_net and 0 < original < measured.original_net, "the OS both ran is in neither"
    assert tier3.gated_ratio(row, measured) == tier3.own_ratio(measured) != measured.ratio
    assert tier3.pin_of(row) is None, "the rule carries it, so no entry may"
    assert tier3.verdict(row, measured, dispatch, measurement_of) == "net"


def test_a_delayed_body_reds_its_row_while_the_whole_run_stays_under_the_bar(dispatch, measurement_of):
    """THE RED the mechanism exists for: ~2,000 cycles more of the AES's own C is a few percent of a polyline's run —
    the whole ratio stays under the bar — and several times the wrapper's own cost, which the own ratio shows."""
    row = tier3.row_named(OS_ROW)
    delayed = _with_own_delay(measurement_of(row), DELAY_CYCLES)
    assert delayed.ratio <= tier3.TIER3_FUNCTION_BAR, "the premise: the whole run hides the delay"
    assert tier3.own_ratio(delayed) > tier3.TIER3_FUNCTION_BAR
    assert tier3.verdict(row, delayed, dispatch, measurement_of) == "OVER"


# The rows under the bar on their own cycles only while the thunks' are off: with the glue counted back, over it.
OS_ROWS_UNDER_ONLY_NET_OF_THE_GLUE = (("aes_vst_height", "the large font's"), ("aes_gsx_moff", "the snapshot's cursor: v_hide_c"))


@pytest.mark.parametrize("key", OS_ROWS_UNDER_ONLY_NET_OF_THE_GLUE, ids=lambda key: f"{key[0]} / {key[1]}")
def test_a_row_through_the_os_under_the_bar_only_net_of_its_glue_is_glue(key, dispatch, measurement_of):
    """(V) stacks (T→G)'s lenience — its own cycles exclude the thunks — so it LABELS it as (T→G) does: a row whose own
    ratio is under the bar and whose ratio with the glue counted back is over it reads `glue`, never `net`."""
    row = tier3.row_named(key)
    measured = measurement_of(row)
    assert tier3.own_ratio(measured) <= tier3.TIER3_FUNCTION_BAR < tier3.own_ratio_with_glue(measured)
    assert tier3.verdict(row, measured, dispatch, measurement_of) == "glue"


def test_a_row_through_the_os_is_net_only_with_its_glue_under_the_bar(dispatch, measurement_of):
    """The polyline is `net` with its thunks counted back too; the same row with its glue grown past the bar is not."""
    row = tier3.row_named(OS_ROW)
    measured = measurement_of(row)
    assert tier3.own_ratio_with_glue(measured) <= tier3.TIER3_FUNCTION_BAR
    ours, original = measured.own_cycles
    heavy = copy.copy(measured)
    heavy.glue_cycles = int(original * tier3.TIER3_FUNCTION_BAR) - ours + 1
    assert tier3.verdict(row, heavy, dispatch, measurement_of) == "glue"


def test_an_accepted_row_through_the_os_is_held_to_its_own_number(dispatch, measurement_of, monkeypatch):
    """The open nest's entry is written at its OWN ratio — the number that ships, as it enters no thunk: gone, the row
    is OVER; moved, it has DRIFTED."""
    row = tier3.row_named(OS_ROW_ACCEPTED)
    measured = measurement_of(row)
    assert tier3.own_ratio(measured) > tier3.TIER3_FUNCTION_BAR
    assert tier3.verdict(row, measured, dispatch, measurement_of) == "accepted"
    assert tier3.verdict(row, _with_own_delay(measured, DELAY_CYCLES), dispatch, measurement_of) == "DRIFTED"
    monkeypatch.delitem(tier3.PERF_ACCEPTED, OS_ROW_ACCEPTED)
    assert tier3.verdict(row, measured, dispatch, measurement_of) == "OVER"


def test_a_pin_on_a_row_through_the_os_is_its_own_ratio_with_the_glue(dispatch, measurement_of, monkeypatch):
    """A pin under the bar (a cost no differential sees) is written at the number that SHIPS, as a (T→) row's is: the
    own ratio with the thunks' cycles counted back. The polyline pinned there holds; pinned at its own ratio net of
    the glue, or at its whole one, it has drifted."""
    row = tier3.row_named(OS_ROW)
    measured = measurement_of(row)
    shipped = tier3.own_ratio_with_glue(measured)
    assert min(abs(measured.ratio - shipped), abs(tier3.own_ratio(measured) - shipped)) > tier3.RATIO_TOLERANCE, (
        "the premise: the three differ")
    monkeypatch.setitem(tier3.PERF_ACCEPTED, OS_ROW, (shipped, "pinned by this test"))
    assert tier3.verdict(row, measured, dispatch, measurement_of) == "pinned"
    for elsewhere in (tier3.own_ratio(measured), measured.ratio):
        monkeypatch.setitem(tier3.PERF_ACCEPTED, OS_ROW, (elsewhere, "pinned by this test"))
        assert tier3.verdict(row, measured, dispatch, measurement_of) == "DRIFTED"


@pytest.mark.parametrize("key", OS_ROWS_UNDER_ONLY_NET_OF_THE_GLUE, ids=lambda key: f"{key[0]} / {key[1]}")
def test_a_pinned_row_through_the_os_still_splits_net_from_glue(key, dispatch, measurement_of, monkeypatch):
    """A pin does not end the split: a row under the bar only net of its glue, pinned at what ships, still reads `glue`."""
    row = tier3.row_named(key)
    measured = measurement_of(row)
    monkeypatch.setitem(tier3.PERF_ACCEPTED, key, (tier3.own_ratio_with_glue(measured), "pinned by this test"))
    assert tier3.verdict(row, measured, dispatch, measurement_of) == "glue"


def test_no_written_acceptance_names_a_row_the_os_rule_carries(measurement_of):
    """The rule REPLACES such entries, as (T→G)'s does: an entry over the bar for a (V) row is only for a body over the
    bar on its OWN cycles — the day it is not, the entry goes."""
    carried = [key for key, (pinned, _why) in tier3.PERF_ACCEPTED.items()
               if pinned > tier3.TIER3_FUNCTION_BAR and tier3.goes_through_the_os(row := tier3.row_named(key))
               and tier3.own_ratio(measurement_of(row)) <= tier3.TIER3_FUNCTION_BAR]
    assert not carried, f"tier3.PERF_ACCEPTED writes down {carried}, which mechanism (V) carries — drop them"


def test_only_the_aes_s_graphics_go_through_the_os():
    """The rule is derived from the m68k call graph, so it is pinned to what it reaches: C of the AES's own text, and
    every one of those rows' symbols holding or calling a `trap #2`."""
    through = [row for row in tier3.ROWS if tier3.goes_through_the_os(row)]
    assert through, "the premise: some row reaches the VDI by `trap #2`"
    assert all(aes.AES_TEXT[0] <= tier3.rom_address(row) < aes.AES_TEXT[1] for row in through), (
        sorted({row.symbol for row in through if not aes.AES_TEXT[0] <= tier3.rom_address(row) < aes.AES_TEXT[1]}))
    assert "aes_gsx2" in tier3.trap_2_functions(tier3.BUILT_ELF)


# A (V) row whose C enters an Alcyon entry: ob_draw hands everyobj `aes_just_draw_alcyon` by value.
ALCYON_ENTRY_ROW = ("aes_ob_draw", "the window tree")


def test_an_alcyon_entry_is_glue_on_a_row_through_the_os_not_measured_as_shipped(bench, monkeypatch):
    """The Alcyon entries are linked in both blobs, so a (V) row priced on the plain one still books the entry's cycles
    as glue — never as its C body's. Measured here with the row's shipping forced off."""
    row = tier3.row_named(ALCYON_ENTRY_ROW)
    monkeypatch.setattr(tier3, "ships_through_a_call", lambda _row: False)
    measured = tier3.measure(row, bench)
    assert tier3.glue_cycles_of(measured) > 0, "the entry's cycles were booked as the C body's"


def test_the_os_rule_refuses_our_build_running_the_aes_s_own_rom_bytes(bench, monkeypatch):
    """Our side may reach the ROM only through the trap: a run whose AES spans hold more than the original spent
    there (here: the original's own count understated by one instruction) is refused, never credited to the ROM."""
    row = tier3.row_named(OS_ROW)
    understated = tier3._original_own_cycles(row) - 4
    monkeypatch.setattr(tier3, "_original_own_cycles", lambda _row: understated)
    with pytest.raises(AssertionError, match="inside the AES's own ROM spans"):
        tier3.measure(row, bench)


class _Vetted(Exception):
    """Raised by a stand-in for the vet, to show a derivation calls it."""


def test_the_os_rule_vets_the_call_graph_it_derives_from(monkeypatch):
    """(V) reads the same call graph (T→) does, so it runs the same vet ITSELF — a row whose symbol the graph qualified
    would otherwise silently not be (V), whichever derivation happened to run first."""
    def vetted(_graph):
        raise _Vetted
    monkeypatch.setattr(tier3, "vet_no_row_is_ambiguous", vetted)
    with pytest.raises(_Vetted):
        tier3._reaching_the_trap.__wrapped__()


def test_the_os_rule_refuses_a_shared_cost_the_two_sides_do_not_share(bench, monkeypatch):
    """The measurement itself holds the OS both run to the same cycles on both sides: our run made to spend a cycle more
    OUTSIDE our blob (here: added to its whole count, as a jump into ROM code past the trap would) is refused."""
    row = tier3.row_named(OS_ROW)
    measure_call = tier3._measure_call

    def spent_more_outside(blob, row, watch=None, original_watch=None):
        measured = measure_call(blob, row, watch, original_watch)
        measured.recreate_cycles += SHARED_CYCLES_MOVED
        return measured
    monkeypatch.setattr(tier3, "_measure_call", spent_more_outside)
    with pytest.raises(AssertionError, match="the OS both sides run cost"):
        tier3.measure(row, bench)


# ---- (EV): C that reaches the event layer through the event door ------------------------------------------------------
# Two door rows: gr_stilldn over ev_multi answering its mouse rectangle under the button down (the event layer's longest
# answering run of the battery's), and gr_watchbox, which draws (V) and waits (EV) in one row.
EV_ROW = ("aes_gr_stilldn", "the button down, inside, waiting to enter: the rectangle")
EV_DRAWING_ROW = ("aes_gr_watchbox", "OK, selected while inside: it rose, inside")


@pytest.mark.parametrize("key", (EV_ROW, EV_DRAWING_ROW), ids=lambda key: key[0])
def test_a_row_through_the_event_door_is_priced_net_of_its_windows(key, dispatch, measurement_of):
    """The ROM's ev_multi runs on both sides and is in neither's own: one window, its cycles off the ROM's AES-span
    cycles, the whole run's ratio near 1 and the own ratio the C's."""
    row = tier3.row_named(key)
    measured = measurement_of(row)
    assert tier3.goes_through_the_door(row) and len(measured.door_windows) == 1
    ours, original = measured.own_cycles
    assert 0 < ours < measured.recreate_net and 0 < original < measured.original_net - sum(measured.door_windows)
    assert tier3.verdict(row, measured, dispatch, measurement_of) in ("net", "glue")


# A body delayed by about three times gr_stilldn's own cost — a fraction of the event layer's run it waits in.
EV_DELAY_CYCLES = 1000


def test_a_delayed_body_through_the_door_reds_its_row_while_the_whole_run_stays_under_the_bar(dispatch, measurement_of):
    """THE RED (EV) exists for: ~1,000 cycles more of gr_stilldn's C are a fraction of the event layer's run — the whole
    ratio stays under the bar — and three times the routine's own cost."""
    row = tier3.row_named(EV_ROW)
    delayed = _with_own_delay(measurement_of(row), EV_DELAY_CYCLES)
    assert delayed.ratio <= tier3.TIER3_FUNCTION_BAR, "the premise: the whole run hides the delay"
    assert tier3.verdict(row, delayed, dispatch, measurement_of) == "OVER"


def test_the_door_rule_holds_the_two_sides_windows_equal(bench, monkeypatch):
    """THE RED for the ROM's side: its windows are measured off its own watched run, never assumed to be ours — a window
    of the ROM's one cycle dearer than ours (a door call taking the event layer down a cheaper path) is refused, never
    credited to the ROM's own."""
    row = tier3.row_named(EV_ROW)
    original_windows = tier3._original_windows

    def one_cycle_dearer(row):
        watch, cycles, own = original_windows(row)
        watch.windows[0] += 1
        return watch, cycles, own
    monkeypatch.setattr(tier3, "_original_windows", one_cycle_dearer)
    with pytest.raises(AssertionError, match="window by window"):
        tier3._measure_through_the_os(row, bench)


def test_the_original_s_windows_are_read_off_its_own_run(bench):
    """The ROM's watched run is its run — the same cycles as the one priced — and has as many windows as ours, each the
    event layer's cost in AES text."""
    row = tier3.row_named(EV_ROW)
    watch, cycles, _own = tier3._original_windows(row)
    measured = tier3._measure_through_the_os(row, bench)
    assert cycles == measured.original_cycles
    assert tuple(watch.windows) == measured.door_windows and len(watch.windows) == 1 and watch.windows[0] > 0



def test_the_door_rule_holds_the_two_sides_frames_equal(bench, monkeypatch):
    """...and what each call hands the door, the same way: a frame the event layer's answer would not show (a timer
    nothing asks for) is red on the target build too, where the frame sits in the uncompared stack band."""
    row = tier3.row_named(EV_ROW)
    original_windows = tier3._original_windows

    def another_timer(row):
        watch, cycles, own = original_windows(row)
        call = watch.handed[0]
        flags, first, second, timer, *rest = call.arguments
        watch.handed[0] = call._replace(arguments=(flags, first, second, timer + 1, *rest))
        return watch, cycles, own
    monkeypatch.setattr(tier3, "_original_windows", another_timer)
    with pytest.raises(AssertionError, match="a frame the image does not show"):
        tier3._measure_through_the_os(row, bench)


def test_the_door_rule_refuses_rom_aes_code_run_outside_a_window(bench, monkeypatch):
    """Our side may reach the AES's text only through the door: the same row measured with no window opened (its run
    unwatched, as a C reaching ROM code by any other road would be) is refused, never credited to the ROM."""
    row = tier3.row_named(EV_ROW)
    monkeypatch.setattr(tier3, "arrives_at_an_entry", lambda _row: False)
    with pytest.raises(AssertionError, match="OUTSIDE the event door's windows"):
        tier3._measure_through_the_os(row, bench)


def test_the_door_watch_stops_at_the_entries_alone_and_refuses_one_entered_but_by_a_door_call():
    """The watch stops at the door's entries THEMSELVES (a set of exact PCs, never a band that would swallow the AES
    text between them), then at the return address the call left — and at the dispatcher, where a call that would
    switch processes is refused by name; and a door entry reached from a return address no door call leaves is
    refused."""
    windows = tier3.our_windows(tier3.BUILT_ELF)
    entry, back = min(tier3.door_calls(tier3.BUILT_ELF).values()), min(windows.returns)
    stack = A_STACK_AT
    memory = bytearray(stack) + back.to_bytes(4, "big") + bytes(max(aes_event.FRAME_BYTES.values()))
    assert windows.first == (frozenset(aes_event.ENTRIES) - aes_event.REBOUND) | frozenset(tier3.twin_entries(tier3.BUILT_ELF))
    assert windows.stopped(entry, stack, memory) == frozenset({back, addrs.AES_ROM_DSPTCH})
    memory[stack:stack + 4] = (back + 2).to_bytes(4, "big")
    with pytest.raises(AssertionError, match="not a door call"):
        tier3.our_windows(tier3.BUILT_ELF).stopped(entry, stack, memory)


# A row registered with its answer not compared (`aes.register`'s `answer_compared`): w_move while drawing is held, which
# leaves its caller's D0.
UNANSWERED_ROW = ("aes_w_move", "drawing held, moved")


def test_a_row_registered_unanswered_is_priced_comparing_no_answer():
    assert tier3.row_named(UNANSWERED_ROW).returns == tier3.RETURNS_NOTHING
    assert tier3.row_named(("aes_w_move", "a window moved")).returns != tier3.RETURNS_NOTHING, "the premise: w_move answers"


# Three door users, each with THE ONE ENTRY IT CALLS: which of them still go through the door — a `jsr` into the ROM's
# routine — is read off what the build has rebound, so a flip edits nothing here.
A_USER_AND_ITS_ONE_ENTRY = {"aes_gr_stilldn": addrs.AES_ROM_EV_MULTI, "aes_gr_watchbox": addrs.AES_ROM_EV_MULTI,
                            "aes_ap_sendmsg": addrs.AES_ROM_AP_RDWR}


def test_the_door_calls_are_the_door_s_entries_and_their_users_the_aes_s():
    """Derived from the blob, held to the door's own list: every `jsr` of the m68k build into the AES's text lands on an
    entry the event door still serves by the ROM's routine — every entry but the rebound ones — and every row reaching
    one is a routine of the AES's text. A user of ONE entry goes through the door exactly while that entry is the
    ROM's; rebound, it arrives at the twin (and is still WATCHED)."""
    assert set(tier3.door_calls(tier3.BUILT_ELF).values()) == set(aes_event.ENTRIES) - aes_event.REBOUND
    through = [row for row in tier3.ROWS if tier3.goes_through_the_door(row)]
    served = {user for user, entry in A_USER_AND_ITS_ONE_ENTRY.items() if entry not in aes_event.REBOUND}
    assert {row.symbol for row in through} & set(A_USER_AND_ITS_ONE_ENTRY) == served
    assert {row.symbol for row in tier3.ROWS if tier3.arrives_at_an_entry(row)} >= set(A_USER_AND_ITS_ONE_ENTRY)
    assert all(aes.AES_TEXT[0] <= tier3.rom_address(row) < aes.AES_TEXT[1] for row in through)


def test_the_door_rule_vets_the_call_graph_it_derives_from(monkeypatch):
    def vetted(_graph):
        raise _Vetted
    monkeypatch.setattr(tier3, "vet_no_row_is_ambiguous", vetted)
    with pytest.raises(_Vetted):
        tier3._reaching_the_door.__wrapped__()


# ---- THE ARRIVALS RULE: a REBOUND entry — an arrival of both runs, no window ---------------------------------------------
# wind_update(BEG_UPDATE) over the free lock: one door call, tak_flag's, rebound (`src/aes/evsync.c`).
REBOUND_ROW = ("aes_wm_update", "the lock taken")
A_STACK_AT = 0x100                     # where a watch's unit tests lay a frame: any address of a scratch memory


BLOBS = {"the bench blob": lambda: tier3.BUILT_ELF, "the shipped blob": lambda: transcription.SHIPPED_ELF}


@pytest.mark.parametrize("elf", BLOBS.values(), ids=BLOBS)
def test_the_blob_s_rebound_and_pending_entries_are_the_host_s(elf):
    """THE DERIVED REBOUND TEST. Every door entry is reached by our build's C OUTSIDE the event layer one way: by a
    `jsr` into the ROM's routine (its wrapper the ROM's call), or by its twin alone (its wrapper spelt through
    `EVDOOR_REBOUND`: no `jsr` left) — never neither. The entries with no `jsr` left are the ones the host's hook
    answers ARRIVED for (`aes_event.REBOUND`, read off the library's markers), and the twins linked beside a `jsr` the
    host's PENDING ones — on both blobs: a wrapper flipped on one build and not the other, or a twin one build links
    and the other does not, is red here."""
    served, twins = set(tier3.door_calls(elf()).values()), set(tier3.twin_entries(elf()).values())
    assert served | twins == set(aes_event.ENTRIES), "an entry with neither a `jsr` into the ROM nor a twin"
    assert tier3.rebound_entries(elf()) == twins - served == aes_event.REBOUND
    assert twins & served == aes_event.PENDING


def test_a_twin_awaiting_its_flip_is_rebound_nowhere(monkeypatch):
    """RED for the derivation the flips rest on: a twin that merely EXISTS flips nothing. ev_multi's ROM routine taken
    for a twin's first instruction — linked, its `jsr` still there: pending, not rebound; and the ROM's watch of a row
    that reaches it through the door still opens its window (`arrived_at_by_a_twin` names no entry the row reaches by
    a `jsr`)."""
    twins = {**tier3.twin_entries(tier3.BUILT_ELF), addrs.AES_ROM_EV_MULTI: addrs.AES_ROM_EV_MULTI}
    monkeypatch.setattr(tier3, "twin_entries", lambda _elf: twins)
    assert addrs.AES_ROM_EV_MULTI not in tier3.rebound_entries(tier3.BUILT_ELF)
    assert addrs.AES_ROM_TAK_FLAG in tier3.rebound_entries(tier3.BUILT_ELF)
    assert tier3.arrived_at_by_a_twin.__wrapped__(EV_ROW[0]) == frozenset()


# wind_update's OWN door calls (`src/aes/wmupdate.c`: the lock taken, released, waited for) — fm_own's, which it
# also reaches, apart.
WIND_UPDATE_S_OWN_ENTRIES = frozenset({addrs.AES_ROM_TAK_FLAG, addrs.AES_ROM_UNSYNC, addrs.AES_ROM_EV_BLOCK})


def test_a_row_s_arrivals_by_a_twin_are_its_outermost_calls_and_one_entry_reached_both_ways_is_refused(monkeypatch):
    """The ROM's watch opens no window at the entries a row's routine reaches BY THEIR TWIN — read off the call graph,
    the twins not walked into: of wind_update's own three, the ones the build has rebound (tak_flag since flip 1); the
    others it still holds a `jsr` to. An entry the same routine reaches BOTH ways is refused by name (shown: tak_flag,
    which it reaches by the twin, taken for one it `jsr`s too)."""
    by_a_twin = tier3.arrived_at_by_a_twin(REBOUND_ROW[0])
    assert by_a_twin & WIND_UPDATE_S_OWN_ENTRIES == WIND_UPDATE_S_OWN_ENTRIES & aes_event.REBOUND >= {addrs.AES_ROM_TAK_FLAG}
    assert tier3.arrived_at_by_a_twin("aes_tak_flag") == frozenset(), "a twin's own row enters it: no arrival"
    assert tier3._door_calls_held_by()[REBOUND_ROW[0]] == WIND_UPDATE_S_OWN_ENTRIES - aes_event.REBOUND, (
        "...and the rest of its own are a `jsr` each, inline")
    held = tier3._door_calls_held_by()
    monkeypatch.setattr(tier3, "_door_calls_held_by", lambda: {**held, REBOUND_ROW[0]: frozenset({addrs.AES_ROM_TAK_FLAG})})
    with pytest.raises(AssertionError, match="BOTH by the twin and by a `jsr`"):
        tier3.arrived_at_by_a_twin.__wrapped__(REBOUND_ROW[0])


def _leaf_rows(entries):
    """`{entry name: its twin's OWN priced rows}` for the door's `entries` — the rows of the registry entered at the
    routine itself (`<its core>, ...`: its leaf battery's), not at a caller of it."""
    return {name: [row for row in tier3.ROWS if row.symbol == routines.core_symbol(name) and not row.transcription]
            for name in aes_event.ENTRY_NAMES if getattr(addrs, name) in entries}


def test_every_twin_has_a_leaf_battery_s_rows():
    """A REBOUND TWIN IS HELD BY ITS LEAF BATTERY (`aes_event`'s docstring: the door cases reach an entry only in the
    states its callers make, and the shadow sees no more). WHAT THIS HOLDS, and no more: that such a battery EXISTS —
    every entry the build links a twin of has at least one priced row of its own, entered at the routine itself.
    EVERY TWIN, rebound OR PENDING: a twin's battery is owed the day the twin lands, so the gap is red in the wave
    that built it and not at its flip (ap_rdwr's twin sat a phase with no row, and nothing said so). THAT THE BATTERY
    REACHES EVERY ARM of its twin is not derived here: it is the strict mutation sweep's and the coverage build's to
    show, entry by entry (STATUS's wave log). RED: ev_multi, taken for a twin, has none."""
    twins = aes_event.REBOUND | aes_event.PENDING
    leaf = _leaf_rows(twins)
    assert len(leaf) == len(twins) >= 1 and all(leaf.values()), (
        f"a twin with no leaf battery (no priced row of its own): {[name for name, rows in leaf.items() if not rows]}")
    assert all(tier3.rom_address(row) == getattr(addrs, name) for name, rows in leaf.items() for row in rows)
    unheld = _leaf_rows(twins | {addrs.AES_ROM_EV_MULTI})
    assert [name for name, rows in unheld.items() if not rows] == ["AES_ROM_EV_MULTI"]


def test_a_row_arrives_by_a_twin_at_its_outermost_calls_only(monkeypatch):
    """What a twin calls is INSIDE its call: a routine that calls ev_button's twin, which calls ev_block's, arrives at
    ev_button alone — ev_block's arrival is nobody's door call, and its ROM routine's cycles, reached inside the ROM's
    ev_button, are no window of the row's either."""
    graph = {"a_caller": {"aes_ev_button", "a_helper"}, "a_helper": set(), "aes_ev_button": {"aes_ev_block"},
             "aes_ev_block": set()}
    monkeypatch.setattr(transcription, "call_graph", lambda _elf: graph)
    monkeypatch.setattr(tier3, "_twin_symbols", lambda: {"aes_ev_button": addrs.AES_ROM_EV_BUTTON,
                                                         "aes_ev_block": addrs.AES_ROM_EV_BLOCK})
    monkeypatch.setattr(tier3, "_door_calls_held_by", lambda: {})
    assert tier3.arrived_at_by_a_twin.__wrapped__("a_caller") == {addrs.AES_ROM_EV_BUTTON}
    assert tier3.arrived_at_by_a_twin.__wrapped__("aes_ev_button") == {addrs.AES_ROM_EV_BLOCK}, "its own row: entered"


# ---- A TWIN'S OWN ROW, WATCHED: entered at the twin, no arrival there (`DoorStops.entered_at`) -----------------------------
TWIN_ROW = ("aes_tak_flag", "free: taken")


def test_a_twin_s_own_row_is_watched_and_enters_its_twin_without_arriving(bench, monkeypatch):
    """A twin that calls another twin's core has its OWN rows among the watched ones (`_arriving_at_an_entry`) — and
    such a row's two runs are ENTERED at the entry: the ROM's at its routine, ours at the twin's first instruction,
    each with the run's sentinel for a return address. Neither is a door call: nothing is counted, no window opens,
    and the row is priced as the C it is. Shown on tak_flag's own row taken for watched (wave 1 derives it so for
    ap_rdwr, ev_button and the waits)."""
    row = tier3.row_named(TWIN_ROW)
    unwatched = tier3._measure_through_the_os(row, bench)
    monkeypatch.setattr(tier3, "arrives_at_an_entry", lambda _row: True)
    measured, _blob, original, windows = tier3._held_through_the_os(row, bench)
    assert original.calls == windows.calls == 0 and measured.door_windows == () and measured.rebound_calls == 0
    assert original.entered_at_an_entry and windows.entered_at_an_entry
    assert measured.own_cycles == unwatched.own_cycles
    assert (measured.recreate_cycles, measured.original_cycles) == (unwatched.recreate_cycles, unwatched.original_cycles)


@pytest.mark.parametrize("shore, refused_at", (("_original_windows", addrs.AES_ROM_TAK_FLAG), ("our_windows", None)),
                         ids=("the ROM's run", "ours"))
def test_without_entered_at_a_twin_s_own_row_is_refused_as_no_door_call(bench, monkeypatch, shore, refused_at):
    """RED (G3's probe, C1): either shore watched with its run's own entry among the stops — as every watch was — is
    stopped at instruction 0 and refused, "not a door call": the ROM's at its entry, ours at the twin."""
    row = tier3.row_named(TWIN_ROW)
    monkeypatch.setattr(tier3, "arrives_at_an_entry", lambda _row: True)
    make = getattr(tier3, shore)

    def never_entered(*run, **named):
        made = make(*run, **named)
        watch = made[0] if isinstance(made, tuple) else made
        watch.entered_at = lambda _pc: watch
        return made
    if shore == "our_windows":
        monkeypatch.setattr(tier3, shore, never_entered)
        refused_at = next(pc for pc, entry in tier3.twin_entries(bench.elf).items() if entry == addrs.AES_ROM_TAK_FLAG)
    else:
        monkeypatch.setattr(tier3, "DoorWindows", type("NeverEntered", (tier3.DoorWindows,),
                                                       {"entered_at": lambda self, _pc: self}))
    with pytest.raises(AssertionError, match=f"reached the door's entry {refused_at:#x} from .* not a door call"):
        tier3._measure_through_the_os(row, bench)


# ---- EVDOOR_TWIN: a twin keeps a first instruction to arrive at (`include/transcribed.h`) --------------------------------
_A_TWIN_S_DEFINITION = r"^(EVDOOR_TWIN\n)?(?:\w+ )+{twin}\(uint8_t \*image[^;{{]*\)\n{{"
A_SAME_FILE_CALLER = """
/* A caller of the twin's core in its own file, as the event layer's C is (amutex, ev_block). */
uint16_t aes_same_file_caller(uint8_t *image, uint32_t semaphore)
{
    if (aes_tak_flag(image, semaphore))
        return 1;
    set_bus_word(image, semaphore + SPB_COUNT, 0);
    return 0;
}
"""


def _definitions_of(twin):
    """`twin`'s definitions in the AES's C: `(file, whether EVDOOR_TWIN precedes it)` each."""
    pattern = re.compile(_A_TWIN_S_DEFINITION.format(twin=twin), re.MULTILINE)
    return [(source.name, bool(defined.group(1))) for source in sorted((RECREATE / "src" / "aes").glob("*.c"))
            for defined in pattern.finditer(source.read_text())]


def test_every_twin_is_defined_with_evdoor_twin():
    """Every door entry's C twin the blob links — rebound or pending — is defined ONCE, with `EVDOOR_TWIN`."""
    twins = [routines.core_symbol(name) for name in aes_event.ENTRY_NAMES
             if getattr(addrs, name) in tier3.twin_entries(tier3.BUILT_ELF).values()]
    assert "aes_tak_flag" in twins
    unmarked = {twin: _definitions_of(twin) for twin in twins if [marked for _file, marked in _definitions_of(twin)] != [True]}
    assert not unmarked, f"twins not defined once with EVDOOR_TWIN (`include/transcribed.h`): {unmarked}"


_A_CALL, _A_JUMP = re.compile(r"\t(jsr|bsr\w*|jbsr)\b"), re.compile(r"\t(jmp|jra|bra\w*|jbra)\b")
ONE_CALL, ONE_JUMP, NO_TRANSFER = (1, 0), (0, 1), (0, 0)


def _transfers_in(source_text, function, variable, scratch):
    """`(calls, jumps)`: how many of each `function` makes in the m68k object of `source_text`, compiled as the blob
    of `variable`'s flags compiles a source — a `jsr` TOLD FROM a `jmp`: a tail jump into a twin is no call of it. (A
    call inside one file is relocated against its SECTION, so its target's name is not in the object: the instruction
    is.)"""
    source, built = scratch / f"{variable}.c", scratch / f"{variable}.o"
    source.write_text(source_text)
    subprocess.run(["m68k-elf-gcc", *_expanded(RECREATE, variable), "-c", str(source), "-o", str(built)], cwd=RECREATE,
                   check=True, capture_output=True)
    listed = subprocess.run(["m68k-elf-objdump", "-dr", str(built)], check=True, capture_output=True, text=True).stdout
    body = re.search(rf"<{function}>:\n(.*?)(?:\n\n|\Z)", listed, re.DOTALL).group(1)
    return len(_A_CALL.findall(body)), len(_A_JUMP.findall(body))


@pytest.mark.parametrize("variable", ("BENCH_CFLAGS", "SHIPPED_CFLAGS"))
def test_evdoor_twin_keeps_a_same_file_caller_s_call_a_call(variable, tmp_path):
    """RED (G3's probe, A7): a second function of `evsync.c` calling `aes_tak_flag` compiles, under the shipped flags,
    with the twin INLINED — no call, so no arrival at the twin's first instruction, and the row unwatched on our side
    alone. With `EVDOOR_TWIN` (`noipa`) the call is a call. Both blobs' flags."""
    evsync = (RECREATE / "src" / "aes" / "evsync.c").read_text()
    assert evsync.count("EVDOOR_TWIN\n") == 1
    assert _transfers_in(evsync + A_SAME_FILE_CALLER, "aes_same_file_caller", variable, tmp_path) == ONE_CALL
    inlined = _transfers_in(evsync.replace("EVDOOR_TWIN\n", "") + A_SAME_FILE_CALLER, "aes_same_file_caller",
                            variable, tmp_path)
    assert inlined == NO_TRANSFER, "the premise: without the attribute GCC inlines the twin, and no call is left"


# ---- A TWIN IS CALLED, NEVER JUMPED TO (`EVDOOR_A_CALL_NOT_A_JUMP`, `include/transcribed.h`) --------------------------------
# Callers that RETURN what a twin answers, as wind_update returns unsync's and ap_sendmsg ap_rdwr's: through the
# rebound wrapper (word and void), and — the premise — by the twin's core alone, which GCC makes a tail jump.
CALLERS_IN_RETURN_POSITION = """
#include "aes/evdoor.h"

void aes_probe_void(uint8_t *image, uint32_t semaphore);
EVDOOR_REBOUND_VOID(probe_void, TAK_FLAG, (uint8_t *image, uint32_t semaphore), 0, semaphore)

uint16_t aes_returns_the_wrapper_s(uint8_t *image, int16_t code)
{
    if (code)
        return 3;
    return evdoor_tak_flag(image, AES_WIND_SPB);
}

void aes_ends_on_the_void_wrapper(uint8_t *image, uint32_t semaphore)
{
    evdoor_probe_void(image, semaphore);
}

uint16_t aes_returns_the_core_s(uint8_t *image, int16_t code)
{
    if (code)
        return 3;
    return aes_tak_flag(image, AES_WIND_SPB);
}
"""


@pytest.mark.parametrize("variable", ("BENCH_CFLAGS", "SHIPPED_CFLAGS"))
def test_a_rebound_wrapper_in_return_position_is_a_call_of_its_twin(variable, tmp_path):
    """THE RED, measured with the six pending entries rebound at once (17 of the 222 door rows refused "reached the
    door's entry … from 0x2 — not a door call", and `make bench` dead): a caller that returns a rebound wrapper's answer compiled to a tail `jmp` into
    the twin — entered with its caller's CALLER's return address, the run's sentinel for a row entered at the caller.
    The wrappers, word and void, keep the call a `jsr` under both blobs' flags; the twin's core returned bare is the
    `jmp` (the premise: what the wrapper's statement prevents)."""
    source = CALLERS_IN_RETURN_POSITION.replace("AES_WIND_SPB", f"{aes.header_constants('wmupdate.h')['AES_WIND_SPB']:#x}")
    assert _transfers_in(source, "aes_returns_the_wrapper_s", variable, tmp_path) == ONE_CALL
    assert _transfers_in(source, "aes_ends_on_the_void_wrapper", variable, tmp_path) == ONE_CALL
    assert _transfers_in(source, "aes_returns_the_core_s", variable, tmp_path) == ONE_JUMP, "the premise"


@pytest.mark.parametrize("elf", BLOBS.values(), ids=BLOBS)
def test_no_twin_is_jumped_to_on_either_blob(elf, monkeypatch):
    """...and THE BLOBS THEMSELVES, whatever spelt each call: every instruction that names a twin's first instruction
    is a `jsr` — no tail jump, no branch, no address taken to call through — so every arrival at a twin holds a return
    address inside our text, which is what the watches close it at. A twin that returns ANOTHER twin's core's answer
    (`return aes_ev_block(...)`) is held here too. RED: one listed `jmp`."""
    references = tier3.references_to_twins(elf())
    assert ("jsr", "aes_tak_flag") in references, "the premise: the lock's twin is called"
    jumped_to = tier3.twins_reached_otherwise_than_by_a_call(elf())
    assert not jumped_to, (
        f"a twin reached otherwise than by a call: {jumped_to} — after the call, `EVDOOR_A_CALL_NOT_A_JUMP` "
        f"(`include/transcribed.h`)")
    twin = tier3._placed(elf())["aes_tak_flag"]
    listing = transcription.listing(elf())
    monkeypatch.setattr(transcription, "listing", lambda _elf: listing + f"   30000:\t4ef9 0003 0000 \tjmp {twin:x} <aes_tak_flag>\n")
    assert tier3.twins_reached_otherwise_than_by_a_call(elf()) == [("jmp", "aes_tak_flag")]


# ---- AN SR SAVE WORD'S DROP IS SYMMETRIC: our run stores the word too (`tier3.vet_our_run_stored_its_sr_words`) ----------
# psetup's own row: the ROM's run parks the status register in $8998 round its stores, and so does our build's.
SR_DROPPING_ROW = ("aes_psetup", "the spare PD")


def test_a_row_that_drops_an_sr_save_word_is_held_to_our_run_s_store_of_it(bench, monkeypatch):
    """The kit vets a drop against the ORIGINAL's ledger alone; an SR save word is dropped because BOTH runs store it,
    each with its own caller's SR — so our run's ledger is read too. Green: psetup's bracket is in our build, and the
    word in our ledger. RED: a build that stored nothing there (its mask bracket compiled away: the ledger taken for
    empty) is refused by name, where the drop alone would have hidden it. A row that drops no such word reads no
    ledger."""
    row = tier3.row_named(SR_DROPPING_ROW)
    assert tier3.sr_save_words_dropped(row) == [(aes.AES_SR_PSETUP, aes.AES_SR_PSETUP + aes.WORD_BYTES)]
    tier3.measure(row, bench)
    ours = tier3.emu.bench_writes(BASE_IMAGE)[0]
    assert {aes.AES_SR_PSETUP, aes.AES_SR_PSETUP + 1} <= ours.keys(), "our run's own ledger, read once it has ended"
    tier3.vet_our_run_stored_its_sr_words(row, ours)
    with pytest.raises(AssertionError, match=f"OUR run never stored .'{aes.AES_SR_PSETUP + 1:#x}'"):
        tier3.vet_our_run_stored_its_sr_words(row, {aes.AES_SR_PSETUP: 0x23})
    assert tier3.sr_save_words_dropped(tier3.row_named(REBOUND_ROW)) == []
    tier3.vet_our_run_stored_its_sr_words(tier3.row_named(REBOUND_ROW), {})
    monkeypatch.setattr(tier3.emu, "bench_writes", lambda _memory: ({}, False))
    with pytest.raises(AssertionError, match="its interrupt-mask bracket is missing from the build's path"):
        tier3.measure(row, bench)


# ---- THE SWITCH: dsptch's twenty bytes, a kind of the build contract of its own (`src/aes/switch.S`) ---------------------
DSPTCH = "aes_dsptch"
DSPTCH_BYTES = 20                      # $fe387c..$fe388f: spl7_save follows at $fe3890
A_TWIN_THAT_SWITCHES = """
#include <stdint.h>
#include "aes/switch.h"
#include "transcribed.h"

EVDOOR_TWIN
uint16_t aes_probe_wait(uint8_t *image, uint32_t semaphore)
{
    (void)semaphore;
    aes_dsptch(image);
    return 0;
}
"""


@pytest.fixture(scope="module")
def make_lists():
    """`atari/target.mk`'s `.S` lists, as make itself expands them."""
    names = ("TRANSCRIBED_SOURCES", "ALCYON_ENTRY_SOURCES", "SWITCH_SOURCES")
    probe = "".join(f"\t@echo {name}=$({name})\n" for name in names)
    makefile = f"RECREATE := {RECREATE}\nKIT := {RECREATE.parents[2] / 'tools' / 'recreate_kit'}\n" \
               f"include {RECREATE}/atari/target.mk\nall:\n{probe}"
    out = subprocess.run(["make", "-s", "-f", "-", "all"], input=makefile, capture_output=True, text=True, check=True).stdout
    return {name: values.split() for name, _, values in (line.partition("=") for line in out.splitlines())}


def test_the_switch_is_its_own_kind_of_the_build_contract(make_lists):
    """`switch.S` is no transcription (no row, no C twin a build excludes, no thunk) and no Alcyon entry: listed apart,
    as make expands the lists; its entries the names the C calls — `aes_dsptch` — which the table derives NO core
    name equal to (a row `aes_rom_dsptch` would make `aes_dsptch` "the C twin the ROM build must not link", and the
    shipped blob would generate a thunk of that name over the entry: G3's C5)."""
    switch = make_lists["SWITCH_SOURCES"]
    assert switch == transcription.switch_sources() and [Path(source).name for source in switch] == ["switch.S"]
    assert not set(switch) & (set(make_lists["TRANSCRIBED_SOURCES"]) | set(make_lists["ALCYON_ENTRY_SOURCES"]))
    assert transcription.SWITCH_ENTRIES == {DSPTCH}
    assert not transcription.SWITCH_ENTRIES & (set(transcription.TRANSCRIBED) | set(transcription.ALCYON_ENTRIES))
    assert not transcription.SWITCH_ENTRIES & {transcription.transcribed_core(entry) for entry in transcription.TRANSCRIBED}
    assert not transcription.SWITCH_ENTRIES & set(shipped_glue.thunked_cores())
    every_s = set(map(str, (RECREATE / "src" / "aes").glob("*.S"))) | set(map(str, (RECREATE / "src" / "vdi").glob("*.S")))
    assert every_s == set(make_lists["TRANSCRIBED_SOURCES"]) | set(make_lists["ALCYON_ENTRY_SOURCES"]) | set(switch), (
        "a `.S` of the table's components that is of none of the three kinds")


@pytest.mark.parametrize("blob", (lambda: RomBench(), tier3.shipped_bench), ids=BLOBS)
def test_dsptch_is_the_rom_s_twenty_bytes_on_both_blobs(blob):
    """BYTE-EXACT, absolute operands and all: the guard's `tst.b indisp`, the frame's two pushes and the `jmp` to the
    ROM's own disp — the only instruction of our build but the door's `jsr`s that leaves for the AES's text, and no
    `jsr`: so no door call of the derivations above."""
    blob = blob()
    at = blob.entry(DSPTCH)
    ours = bytes(blob.blob[at - blob.base:at - blob.base + DSPTCH_BYTES])
    assert ours == bytes(BASE_IMAGE[addrs.AES_ROM_DSPTCH:addrs.AES_ROM_DSPTCH + DSPTCH_BYTES])
    assert ours[-aes.LONG_BYTES:] == addrs.AES_ROM_DISP.to_bytes(aes.LONG_BYTES, "big"), "its last operand: disp"
    assert addrs.AES_ROM_DISP not in tier3.door_calls(blob.elf).values()


@pytest.mark.parametrize("variable", ("BENCH_CFLAGS", "SHIPPED_CFLAGS"))
def test_a_twin_that_calls_the_dispatcher_links_against_the_switch(variable, tmp_path):
    """THE PROBE TWIN: C that calls `aes_dsptch` — as unsync's and the waits' twins do — compiled under each blob's
    flags and LINKED with the switch's `.S` alone: the name resolves to the `.S` entry (before `switch.S` the target
    declared the name and nothing defined it: every such twin was a link error), by a plain `jsr`, and what it enters
    is the ROM's bytes."""
    source, linked = tmp_path / "probe.c", tmp_path / "probe.elf"
    source.write_text(A_TWIN_THAT_SWITCHES)
    subprocess.run(["m68k-elf-gcc", *_expanded(RECREATE, variable), "-Wl,--build-id=none", "-Wl,-e0", str(source),
                    *transcription.switch_sources(), "-o", str(linked)], cwd=RECREATE, check=True, capture_output=True)
    listed = transcription.listing(linked)
    placed = {symbol.name: symbol.start for symbol in transcription.symbol_table(linked)}
    assert re.search(rf"jsr {placed[DSPTCH]:x} <{DSPTCH}>", listed), listed
    unlinked = subprocess.run(["m68k-elf-gcc", *_expanded(RECREATE, variable), "-Wl,-e0", str(source), "-o", str(linked)],
                              cwd=RECREATE, capture_output=True, text=True)
    assert unlinked.returncode != 0 and f"undefined reference to `{DSPTCH}'" in unlinked.stderr, "the premise"


def test_a_rebound_entry_s_call_is_an_arrival_with_no_window(bench):
    """Both runs arrive at tak_flag — the ROM's at its routine, ours at the twin — and are handed the same frame; no
    window is taken off: the ROM routine's cycles (its Line-F word's handler with them) are the ROM's own, the twin's
    ours, and nothing is shared."""
    row = tier3.row_named(REBOUND_ROW)
    measured, _blob, original, windows = tier3._held_through_the_os(row, bench)
    assert measured.door_windows == (0,) and tuple(original.windows) == (0,)
    assert original.handed == windows.handed and [call.routine for call in windows.handed] == [addrs.AES_ROM_TAK_FLAG]
    assert tier3.shared_cycles(measured) == (0, 0)
    ours, the_rom_s = measured.own_cycles
    assert 0 < ours < the_rom_s == measured.original_net


def test_a_twin_is_an_arrival_only_from_our_build_s_own_text():
    """A twin's return address is no fixed call site, but it is BOUNDED: inside the blob's text, where every call of
    our build returns to. Reached with any other — the ROM's text here — it is refused by name, as a served entry
    reached by no door call is; from the blob's own text it opens its call."""
    twin = next(iter(tier3.twin_entries(tier3.BUILT_ELF)))
    lo, hi = tier3.text_span(tier3.BUILT_ELF)
    stack = A_STACK_AT

    def reached_from(back):
        memory = bytearray(stack) + back.to_bytes(4, "big") + bytes(2 * 4 + max(aes_event.FRAME_BYTES.values()) * 2)
        return tier3.our_windows(tier3.BUILT_ELF).stopped(twin, stack, memory)
    assert reached_from(hi - 2) == frozenset({hi - 2, addrs.AES_ROM_DSPTCH}) and lo <= twin < hi
    with pytest.raises(AssertionError, match="names the text their calls come from"):
        aes_event.DoorStops((), (), twins={twin: addrs.AES_ROM_TAK_FLAG})
    for elsewhere in (hi, lo - 2, addrs.AES_ROM_WM_UPDATE):
        with pytest.raises(AssertionError, match="not a door call"):
            reached_from(elsewhere)


def test_a_call_s_kind_is_what_the_watch_saw_not_a_window_that_came_out_empty(bench):
    """The table's line under a row tells a REBOUND entry's call from a served one by what the watch saw the call BE:
    a served door call that cost no cycle of the AES's ROM is still a door window, and is not printed as a call of a
    rebound entry — which the lock's one call is."""
    measured, _blob, _original, _windows = tier3._held_through_the_os(tier3.row_named(REBOUND_ROW), bench)
    assert (measured.door_windows, measured.rebound_calls) == ((0,), 1)
    assert "1 call(s) of a rebound entry" in tier3._through_the_os_line(measured, 0)
    measured.rebound_calls = 0             # the same window of nothing, of a call the ROM SERVED
    line = tier3._through_the_os_line(measured, 0)
    assert "the event layer's 0 of it in 1 door window(s)" in line and "rebound" not in line


def test_a_twin_s_call_is_read_off_the_frame_gcc_pushes():
    """A twin's arguments each fill a longword above the return address and the image pointer, a WORD in its low half:
    ev_button's three words and a pointer, read back as the Alcyon frame its ROM callers push."""
    clicks, mask, state, answers = 2, 1, -1, aes_event.MESSAGE_AT
    stack = A_STACK_AT
    memory = bytearray(stack) + struct.pack(">IIiiiI", 0, 0, clicks, mask, state, answers) + bytes(aes_event.IMAGE_BYTES)
    call = aes_event.handed_at_a_twin(addrs.AES_ROM_EV_BUTTON, stack, memory)
    assert call == aes_event.handed(addrs.AES_ROM_EV_BUTTON, aes_event.EV_BUTTON_FRAME.pack(clicks, mask, state, answers),
                                    memory)


def test_our_frame_at_a_twin_is_held_to_the_rom_s_call(bench, monkeypatch):
    """THE RED for the frames at an arrival: our twin's call read off another slot of GCC's frame (the image pointer's)
    hands another semaphore than the ROM's call — refused, on the target build, as a served entry's frame is."""
    row = tier3.row_named(REBOUND_ROW)
    handed_at_a_twin = aes_event.handed_at_a_twin
    monkeypatch.setattr(aes_event, "handed_at_a_twin",
                        lambda entry, sp, memory: handed_at_a_twin(entry, sp - aes.LONG_BYTES, memory))
    with pytest.raises(AssertionError, match="a frame the image does not show"):
        tier3._measure_through_the_os(row, bench)


def _ours_watched_by(monkeypatch, watch_of):
    """Our blob's watch made by `watch_of(calls, returns, delivered)` — `calls` the blob's door calls."""
    def our_windows(elf, delivered=None):
        calls = tier3.door_calls(elf)
        return watch_of(calls, [at + tier3.JSR_ABSOLUTE_BYTES for at in calls], delivered)
    monkeypatch.setattr(tier3, "our_windows", our_windows)


def test_an_arrival_our_run_does_not_count_lays_every_delivery_a_call_late(bench, monkeypatch):
    """THE RED for the arrival's ORDINAL (a delivery laid one arrival late, on a row whose door call 0 is the rebound
    tak_flag): our run watched at the ROM-served entries alone counts its first wait as door call 0, lays the move
    owed to it at the next, and is refused at the wait that got nothing — by name."""
    row = _interrupted_row()
    assert min(row.delivered) == 1, "the premise: door call 0 is the lock's tak_flag, the first delivery at call 1"
    _ours_watched_by(monkeypatch, lambda calls, returns, delivered: tier3.DoorWindows(calls.values(), returns, delivered))
    with pytest.raises(AssertionError, match=_refused_inside_call(0)):
        tier3._measure_through_the_os(row, bench)


def test_a_twin_that_runs_the_aes_s_rom_is_refused_by_name(bench, monkeypatch):
    """A twin's call opens no window, so a cycle of the AES's ROM run inside one would be booked to nobody: refused.
    Shown by taking the ROM's ev_multi our blob `jsr`s for a twin's first instruction."""
    row = tier3.row_named(EV_ROW)
    wait = addrs.AES_ROM_EV_MULTI
    _ours_watched_by(monkeypatch, lambda calls, returns, delivered: tier3.DoorWindows(
        (), returns, delivered, twins={wait: wait}, twins_called_from=(min(returns), max(returns) + 1)))
    with pytest.raises(AssertionError, match=f"our twin of {wait:#x} ran [0-9]+ cycles of the AES's own ROM"):
        tier3._measure_through_the_os(row, bench)


def test_a_row_arriving_at_a_twin_alone_is_watched(monkeypatch):
    """The rows whose runs are watched are derived from BOTH ways an entry is reached: with no `jsr` into the ROM left
    (every entry rebound), a caller of a twin still arrives — and the twin's own row does not (it is entered, not
    called)."""
    monkeypatch.setattr(tier3, "_reaching_the_door", lambda: frozenset())
    arriving = tier3._arriving_at_an_entry.__wrapped__()
    graph = transcription.call_graph(tier3.BUILT_ELF)
    assert "aes_tak_flag" in graph["aes_wm_update"] and "aes_tak_flag" not in graph["aes_fm_do"], "the premise"
    assert "aes_wm_update" in arriving and "aes_fm_do" in arriving and "aes_tak_flag" not in arriving
    monkeypatch.setattr(tier3, "_arriving_at_an_entry", lambda: arriving)
    monkeypatch.setattr(tier3, "_reaching_the_trap", lambda: frozenset())
    assert tier3.arrives_at_an_entry(tier3.row_named(REBOUND_ROW)) and tier3.goes_through_the_os(tier3.row_named(REBOUND_ROW))
    assert not tier3.arrives_at_an_entry(tier3.row_named(EV_ROW)), "the premise: gr_stilldn calls no twin"
    assert not tier3.arrives_at_an_entry(tier3.row_named(("aes_tak_flag", "free: taken")))


def test_the_table_s_line_counts_a_rebound_entry_s_calls_apart_from_the_windows(bench):
    """Under a row: the windows taken off both sides, and the calls of a rebound entry, which are in the own cycles."""
    rebound = tier3._through_the_os_line(tier3._measure_through_the_os(tier3.row_named(REBOUND_ROW), bench), 0)
    served = tier3._through_the_os_line(tier3._measure_through_the_os(tier3.row_named(EV_ROW), bench), 0)
    assert "1 call(s) of a rebound entry in the own cycles" in rebound and "door window(s)" not in rebound
    assert "in 1 door window(s)" in served and "rebound" not in served


# ---- (EV) a row TAKEN THROUGH INTERRUPTS: the same deliveries at the same door calls on every run ------------------------
# gr_dragbox with the cursor shown, the mouse moved at its second door call and the button released at its third
# (`test_aes_grdrag.WORST_INTERRUPTED`): the ROM's watched original (`RomBench.measure`'s `original_watch`), its
# windows' run (`_original_windows`) and our blob's run each lay the row's deliveries at the entry of the same call.
INTERRUPTED_ROW = ("aes_gr_dragbox", "moved, the cursor shown")


def _interrupted_row():
    row = tier3.row_named(INTERRUPTED_ROW)
    assert row.delivered, "the premise: the row is taken through interrupts"
    return row


def _ours_delivered(monkeypatch, delivered_of):
    """Our blob's watch laying `delivered_of(the row's deliveries)` instead of the row's own."""
    our_windows = tier3.our_windows
    monkeypatch.setattr(tier3, "our_windows", lambda elf, delivered=None: our_windows(elf, delivered_of(delivered)))


def _refused_inside_call(ordinal):
    return f"inside door call {ordinal}: {re.escape(aes_event.SWITCHES_AT_THE_DISPATCHER)}"


def test_an_interrupted_row_s_windows_are_read_off_its_own_run_too(bench):
    """...and on a row TAKEN THROUGH INTERRUPTS, whose original has no unwatched run to anchor it: the watched run the
    windows (and the ROM's own cycles) are read off is the run the measurement priced — its deliveries laid on both."""
    row = _interrupted_row()
    watch, cycles, _own = tier3._original_windows(row)
    measured = tier3._measure_through_the_os(row, bench)
    assert cycles == measured.original_cycles
    assert tuple(watch.windows) == measured.door_windows and len(watch.windows) > max(row.delivered)


def test_a_row_taken_through_interrupts_is_priced_with_them_laid_on_both_sides(dispatch, measurement_of):
    """A window per door call on both sides — its first delivery past the first — and the row priced like any (EV) row."""
    row = _interrupted_row()
    measured = measurement_of(row)
    assert len(measured.door_windows) > max(row.delivered) > 0
    assert tier3.verdict(row, measured, dispatch, measurement_of) in ("net", "glue")


def test_an_interrupt_laid_on_the_rom_s_side_alone_is_refused_at_the_call_that_waits_for_it(bench, monkeypatch):
    """THE RED for our side: our blob handed nothing at the row's first delivery's call reaches the dispatcher there,
    refused by name — not a run spinning to its budget."""
    row = _interrupted_row()
    _ours_delivered(monkeypatch, lambda delivered: {})
    with pytest.raises(AssertionError, match=_refused_inside_call(min(row.delivered))):
        tier3._measure_through_the_os(row, bench)


def test_an_interrupt_laid_on_our_side_alone_is_refused_at_the_call_that_waits_for_it(bench, monkeypatch):
    """...and for the ROM's: its original handed nothing blocks at the same call, refused by the same words."""
    row = _interrupted_row()
    _ours_delivered(monkeypatch, lambda delivered: row.delivered)
    with pytest.raises(AssertionError, match=_refused_inside_call(min(row.delivered))):
        tier3._measure_through_the_os(row._replace(delivered={}), bench)


def test_an_interrupt_laid_one_call_late_is_refused_at_the_call_that_waits_for_it(bench, monkeypatch):
    """...and one call late on our side: the call it was owed to waits for it, and is refused there by name."""
    row = _interrupted_row()
    _ours_delivered(monkeypatch, lambda delivered: {ordinal + 1: taken for ordinal, taken in delivered.items()})
    with pytest.raises(AssertionError, match=_refused_inside_call(min(row.delivered))):
        tier3._measure_through_the_os(row, bench)


def test_an_interrupt_laid_over_memory_it_was_not_derived_over_is_refused_by_name(bench, monkeypatch):
    """A delivery is the ROM's interrupt code run over the ROM's memory at that entry: laid over a run whose memory
    differs where it writes, it would erase the difference — refused by name on whichever side the memory differs."""
    row = _interrupted_row()
    ordinal = min(row.delivered)
    found, wrote = row.delivered[ordinal]
    at = min(address for address in found if address not in aes_event._NOT_COMPARED)

    def diverged(delivered):
        return {**delivered, ordinal: ({**found, at: bytes([found[at][0] ^ 1]) + found[at][1:]}, wrote)}
    _ours_delivered(monkeypatch, diverged)
    with pytest.raises(AssertionError, match=f"where an interrupt is delivered at door call {ordinal}.*{at:#x}"):
        tier3._measure_through_the_os(row, bench)


# ---- (EV)'s SLICES: a row priced on one slice of a long session (`aes_event.register_slices`) ----------------------------
# fm_do's long typing session (`test_aes_fmdo.SESSION_SLICES`): 38 keys, 728,664 ROM instructions, registered as five
# rows — the slices that start or stop at the entry, a door call, a trap taken and the return.
WAIT = addrs.AES_ROM_EV_MULTI
SLICED_ROWS = tuple(("aes_fm_do", label) for label in test_aes_fmdo.SESSION_SLICES)
A_KEY_S_ROW = ("aes_fm_do", f"{test_aes_fmdo.KEYS_IN_THE_SESSION}: the last character typed")
# A short session to cut whole: six keys typed one per wait, the last the Return (a registered row, unsliced).
SHORT_SESSION_ROW = ("aes_fm_do", "typed, Left, Delete, Right, Return")
UNREAD_BYTE = aes_event.UNREAD_BYTE     # where a RED test takes our run astray (`aes_event.astray`)


def _sliced_row(key=A_KEY_S_ROW):
    row = tier3.row_named(key)
    assert row.slice and row.delivered, "the premise: the row is one slice of a session taken through interrupts"
    return row


@pytest.mark.parametrize("key", SLICED_ROWS, ids=[case_label for _symbol, case_label in SLICED_ROWS])
def test_a_sliced_row_is_priced_on_its_slice_alone(key, bench, dispatch, measurement_of):
    """Each registered slice carries its `Slice` into its row, is priced on what the ROM's own run spends inside it
    (`aes_event.slice_cost`, the ROM alone) — far under the session's whole run — and passes like any (EV) row."""
    row = _sliced_row(key)
    assert row.slice == aes_event.SLICED_ROWS[row.registered]
    spent = aes_event.slice_cost_of(tier3.registered(row), row.slice)
    measured = measurement_of(row)
    assert (measured.original_insns, measured.original_cycles) == (spent["insns"], spent["cycles"])
    assert measured.original_insns < aes_event.SLICE_INSNS < test_aes_fmdo.SESSION_INSNS
    assert tier3.verdict(row, measured, dispatch, measurement_of) in ("net", "glue")


MEASURED = ("original_insns", "original_cycles", "recreate_insns", "recreate_cycles", "glue_cycles", "own_cycles",
            "door_windows", "overhead_cycles")


def _as_measured(measured):
    return {total: getattr(measured, total) for total in MEASURED}


def test_a_session_s_rows_priced_off_one_pair_of_runs_are_what_each_row_s_own_runs_price(bench):
    """ONE PAIR OF RUNS FOR A SESSION (`tier3.Sessions`): every one of the session's five rows, cut out of the two
    runs that mark all their ends at once, is to the cycle the `Measurement` its own three runs make — both sides'
    costs, glue, own cycles, windows, overhead — and the session was measured once for the five."""
    measures, held = [], tier3._held_through_the_os

    def counted(*row_of, **marked):
        measures.append(marked)
        return held(*row_of, **marked)
    sessions = tier3.Sessions(bench)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tier3, "_held_through_the_os", counted)
        shared = {key: _as_measured(tier3.measure(_sliced_row(key), bench, sessions)) for key in SLICED_ROWS}
    assert len(measures) == 1 and len(measures[0]["others"]) == len(SLICED_ROWS) - 1
    assert shared == {key: _as_measured(tier3.measure(_sliced_row(key), bench)) for key in SLICED_ROWS}


def test_a_row_that_is_no_table_row_of_a_session_is_measured_by_its_own_runs(bench):
    """...and the memo serves the TABLE's rows alone: a case's variant of one (here its slice replaced) is measured by
    its own runs, whatever the memo holds."""
    sessions, row = tier3.Sessions(bench), _sliced_row()
    whole = row._replace(slice=aes_event.Slice(aes_event.ENTRY, aes_event.RETURN))
    priced = tier3.measure(row, bench, sessions)
    with pytest.raises(AssertionError, match="past SLICE_INSNS"):
        tier3.measure(whole, bench, sessions)
    assert _as_measured(tier3.measure(row, bench, sessions)) == _as_measured(priced)


def test_a_session_s_row_refused_at_its_own_mark_is_refused_alone(bench, monkeypatch):
    """THE RED through the memo: our run astray until past the first key's wait and back before the last key's — the
    rows whose ends lie inside that stretch are each refused by name when asked for; the last key's row, whose marks
    see nothing, is priced."""
    last_key = _sliced_row()
    healed_at, went = _door_calls_before(last_key, last_key.slice.start), []

    def from_the_first_stop_until_healed(watch, nth):
        """At the run's first stop, and again as it is about to enter door call `healed_at`."""
        flips = nth == 0 or (len(went) == 1 and watch.between_calls and watch.calls == healed_at)
        if flips:
            went.append(nth)
        return flips
    _our_run_astray(monkeypatch, from_the_first_stop_until_healed)
    sessions = tier3.Sessions(bench)
    assert tier3.measure(last_key, bench, sessions).original_insns
    first_wait = _sliced_row(SLICED_ROWS[0])
    with pytest.raises(AssertionError, match="our run diverged inside the slice"):
        tier3.measure(first_wait, bench, sessions)


@pytest.mark.parametrize("cap", (None, 1), ids=("its rows priced", "its rows refused, each refusal kept"))
def test_a_session_s_marks_are_dropped_once_its_rows_are_cut(cap, bench, monkeypatch):
    """THE MEMO KEEPS NO RUN: a session's two watches and their marks — a memory per slice end, sixteen megabytes each —
    are gone when `Sessions` has cut its rows, by the last reference going (the collector is OFF here), not by some
    later collection. RED both ways: a watch that is a reference cycle (its own bound methods handed to itself)
    outlives the call; so does one a kept refusal's traceback still reaches — here every row refused, under a slice
    cap of one instruction."""
    held, runs, row = tier3._held_through_the_os, [], _sliced_row()

    def recorded(*row_of, **marked):
        measured, blob, original, windows = held(*row_of, **marked)
        runs.extend(weakref.ref(each) for watch in (original, windows) for each in (watch, watch.marks))
        return measured, blob, original, windows
    monkeypatch.setattr(tier3, "_held_through_the_os", recorded)
    if cap is not None:
        monkeypatch.setattr(aes_event, "SLICE_INSNS", cap)
    gc.collect()
    gc.disable()
    try:
        sessions = tier3.Sessions(bench)
        if cap is None:
            assert sessions.measure(row).original_insns
        else:
            with pytest.raises(AssertionError, match="past SLICE_INSNS"):
                sessions.measure(row)
        assert len(runs) == 4 and all(run() is None for run in runs), "a watch or its marks outlived the session's pricing"
    finally:
        gc.enable()


# ---- WHAT NO SLICE PRICES: every stretch of a session between its registered slices (`tier3.uncovered_stretches`) ----
def _sessions_sliced():
    """One row per sliced session, the table's first of each: `{its case: the row}`."""
    first = {}
    for row in tier3.ROWS:
        if row.slice:
            first.setdefault(id(tier3.session_of(row)), row)
    return {f"{row.symbol}-{row.case}": row for row in first.values()}


SESSIONS_SLICED = _sessions_sliced()


def _worst_registered(symbol, measurement_of, but=()):
    """The worst own ratio among `symbol`'s priced rows through the OS (what the table prints for them), `but` aside."""
    rows = [row for row in tier3.ROWS if row.symbol == symbol and tier3.goes_through_the_os(row) and row.case not in but]
    worst = max(rows, key=lambda row: tier3.own_ratio(measurement_of(row)))
    return worst, tier3.own_ratio(measurement_of(worst))


def _vet_no_stretch_is_dearer(row, stretches, worst_row, worst):
    """Every stretch no slice prices is at or under the routine's worst registered row — else refused, by name."""
    for stretch in stretches:
        ratio = tier3.stretch_ratio(stretch)
        assert ratio <= worst, (
            f"{row.symbol}: the session of '{row.case}' spends {stretch.insns} ROM instructions from {stretch.start} "
            f"to {stretch.stop} that no registered slice prices, at an own ratio of {ratio:.4f} "
            f"({stretch.own_cycles[0]} cycles against the ROM's {stretch.own_cycles[1]}) — dearer than the routine's "
            f"worst registered row ({worst:.4f}, '{worst_row.case}'): register the stretch as a slice")


@pytest.mark.parametrize("row", SESSIONS_SLICED.values(), ids=SESSIONS_SLICED)
def test_no_stretch_between_a_session_s_slices_is_dearer_than_its_routine_s_worst_row(row, bench, measurement_of):
    """THE PARTITION: the session cut whole at every door call and every registered end, both shores; every stretch
    its registered slices leave unpriced is held at or under the worst row the table prints for the routine — so a
    dear stretch cannot hide in a gap between slices."""
    stretches = tier3.uncovered_stretches(row, bench)
    _vet_no_stretch_is_dearer(row, stretches, *_worst_registered(row.symbol, measurement_of))


def test_a_session_s_stretches_and_slices_partition_its_run(bench):
    """...and it IS a partition: with no slice counted as covering, the stretches are the whole run — their ROM
    instructions and both shores' own cycles sum to the unsliced session's, to the cycle (fm_do's 38 keys)."""
    row = _sliced_row()
    stretches = tier3.uncovered_stretches(row, bench, covered=())
    whole, _blob, _original, _windows = tier3._held_through_the_os(row, bench)
    assert sum(stretch.insns for stretch in stretches) == whole.original_insns
    assert tuple(map(sum, zip(*(stretch.own_cycles for stretch in stretches)))) == whole.own_cycles
    assert stretches[0].start == aes_event.ENTRY and stretches[-1].stop == aes_event.RETURN
    assert all(before.stop == after.start for before, after in zip(stretches, stretches[1:]))
    doors = sum(stretch.stop != aes_event.RETURN and stretch.stop.pc in aes_event.ENTRIES for stretch in stretches)
    assert doors == len(whole.door_windows), "a cut at every door call"


def test_a_session_s_uncovered_stretches_are_exactly_what_its_slices_leave(bench, sessions):
    """...and with the registered slices counted: the stretches and the five slices together are the whole run, no
    instruction and no own cycle in both or in neither."""
    row = _sliced_row()
    rows = tier3.rows_of_the_session(tier3.session_of(row))
    stretches = tier3.uncovered_stretches(row, bench)
    priced = [tier3.measure(each, bench, sessions) for each in rows]
    whole, _blob, _original, _windows = tier3._held_through_the_os(row, bench)
    assert sum(stretch.insns for stretch in stretches) + sum(each.original_insns for each in priced) == whole.original_insns
    own = [stretch.own_cycles for stretch in stretches] + [each.own_cycles for each in priced]
    assert tuple(map(sum, zip(*own))) == whole.own_cycles


def test_a_stretch_s_ratio_is_its_own_cycles_and_past_every_bar_where_ours_alone_spent_any():
    at = aes_event.door_call(WAIT, 0)
    assert tier3.stretch_ratio(tier3.Stretch(aes_event.ENTRY, at, 10, (3, 4))) == 0.75
    assert tier3.stretch_ratio(tier3.Stretch(aes_event.ENTRY, at, 10, (0, 0))) == 0
    assert tier3.stretch_ratio(tier3.Stretch(aes_event.ENTRY, at, 10, (1, 0))) > tier3.TIER3_FUNCTION_BAR


def test_the_rows_of_a_session_that_are_not_one_machine_are_refused_by_name(bench, monkeypatch):
    """THE MEMO'S PREMISE, held: a session's rows share a run because they are one machine — one that is not (here
    its I/O map another's) is refused before any run is shared."""
    row = _sliced_row()
    rows = tier3.rows_of_the_session(tier3.session_of(row))
    monkeypatch.setattr(tier3, "rows_of_the_session", lambda _session: [rows[0]._replace(io_seed={0: 0}), *rows[1:]])
    with pytest.raises(AssertionError, match="the rows of its session are not one machine"):
        tier3.Sessions(bench).measure(row)


def test_sessions_measured_over_one_build_are_not_answered_for_another(bench):
    """A MEMO IS ONE BUILD'S (RED): sessions made over one bench, asked for a row over another, are refused by name —
    never answered the first build's pricing."""
    another_build = copy.copy(bench)
    with pytest.raises(AssertionError, match="asked of sessions measured over another build"):
        tier3.measure(_sliced_row(), another_build, tier3.Sessions(bench))


def test_a_sliced_row_that_names_no_session_is_refused_by_name(bench):
    """A SLICED ROW IS FOUND BY ITS REGISTERED NAME (RED): one whose name no session answers to would be priced by
    three runs of its own without a word — the lever lost — so it is refused, wherever its session is asked for."""
    row = _sliced_row()
    assert tier3.session_of(row) is aes_event.session_of(row.registered) is tier3.registered(row)
    unregistered = row._replace(registered="aes_fm_do, a name no battery registered")
    for asked in (tier3.session_of, tier3.registered, lambda row: tier3.uncovered_stretches(row, bench)):
        with pytest.raises(AssertionError, match="a sliced row registered as .*which names no session"):
            asked(unregistered)
    unsliced = tier3.row_named(SHORT_SESSION_ROW)
    assert tier3.session_of(unsliced) is aes_event.session_of(unsliced.registered) and not unsliced.slice
    assert tier3.session_of(tier3.row_named(tier3.DISPATCH_LEAF)) is None


def test_a_dear_stretch_left_out_of_the_slice_table_is_refused_by_name(bench, measurement_of):
    """THE RED: fm_do's session with its worst slice — the last character typed — left out of the table: the stretch
    it priced is then a gap dearer than every row that is left, and the session is refused by name. (So are the keys
    just before it, which only that row's ratio covered: the gaps are held to what the table PRINTS.)"""
    row = _sliced_row()
    worst_row, _worst = _worst_registered(row.symbol, measurement_of)
    assert (worst_row.symbol, worst_row.case) == A_KEY_S_ROW, "the premise: the last key is fm_do's worst row"
    left = [each.slice for each in tier3.rows_of_the_session(tier3.session_of(row)) if each.slice != worst_row.slice]
    stretches = tier3.uncovered_stretches(row, bench, covered=left)
    next_worst_row, next_worst = _worst_registered(row.symbol, measurement_of, but={worst_row.case})
    dearer = {(stretch.start, stretch.stop) for stretch in stretches if tier3.stretch_ratio(stretch) > next_worst}
    assert tuple(worst_row.slice) in dearer
    with pytest.raises(AssertionError, match="that no registered slice prices.*dearer than the routine's worst"):
        _vet_no_stretch_is_dearer(row, stretches, next_worst_row, next_worst)


def test_a_trap_our_build_takes_that_the_rom_s_run_does_not_is_refused_by_name(bench, monkeypatch):
    """THE ARRIVALS ARE HELD EQUAL where the session is cut whole: our timeline with one arrival dropped (an end at a
    trap the C never took) is refused at the first arrival that differs."""
    held = tier3._held_through_the_os

    def one_arrival_short(*row_of, **marked):
        measured, blob, original, windows = held(*row_of, **marked)
        del windows.marks.timeline[1]
        return measured, blob, original, windows
    monkeypatch.setattr(tier3, "_held_through_the_os", one_arrival_short)
    with pytest.raises(AssertionError, match="the two runs do not make the same arrivals"):
        tier3.uncovered_stretches(_sliced_row(), bench)


TIMELINE_FAULTS = {
    "its last arrival never made": lambda timeline: timeline[:-1],
    "an arrival made a door call late": lambda timeline: [timeline[0]._replace(calls=timeline[0].calls + 1), *timeline[1:]],
}


@pytest.mark.parametrize("fault", TIMELINE_FAULTS.values(), ids=TIMELINE_FAULTS)
def test_our_timeline_is_held_to_the_rom_s_arrival_for_arrival(fault, bench, monkeypatch):
    """...and so is one that only stops short, or makes the same arrivals after other door calls."""
    held = tier3._held_through_the_os

    def faulted(*row_of, **marked):
        measured, blob, original, windows = held(*row_of, **marked)
        windows.marks.timeline = fault(windows.marks.timeline)
        return measured, blob, original, windows
    monkeypatch.setattr(tier3, "_held_through_the_os", faulted)
    with pytest.raises(AssertionError, match="the two runs do not make the same arrivals"):
        tier3.uncovered_stretches(_sliced_row(), bench)


def _cuts_of(row):
    """A session cut at every wait: the entry, each ev_multi it makes, the return."""
    waits = sum(call.routine == WAIT for call in tier3._original_windows(row)[0].handed)
    return (aes_event.ENTRY, *(aes_event.door_call(WAIT, nth) for nth in range(waits)), aes_event.RETURN)


def test_a_session_s_slices_sum_to_its_whole_row(bench):
    """THE ACCOUNTING: a session cut at every wait is priced slice by slice, and nothing is lost or counted twice —
    each side's instructions, cycles, glue and OWN cycles (the reset taken off the first slice alone), and the windows
    in order, sum to the unsliced row's."""
    row = tier3.row_named(SHORT_SESSION_ROW)
    whole = tier3.measure(row, bench)
    cuts = _cuts_of(row)
    assert len(cuts) > len(row.delivered) + 1
    slices = [tier3.measure(row._replace(slice=aes_event.Slice(*ends)), bench) for ends in zip(cuts, cuts[1:])]
    for total in ("original_insns", "original_cycles", "recreate_insns", "recreate_cycles", "glue_cycles"):
        assert sum(getattr(each, total) for each in slices) == getattr(whole, total), total
    assert tuple(map(sum, zip(*(each.own_cycles for each in slices)))) == whole.own_cycles
    assert sum((each.door_windows for each in slices), ()) == whole.door_windows
    assert [each.overhead_cycles for each in slices] == [whole.overhead_cycles] + [0] * (len(slices) - 1)


def test_a_slice_our_build_starts_one_door_late_is_refused_by_name(bench, monkeypatch):
    """THE RED: our run marked from the NEXT wait — a door call later than the ROM's slice starts at."""
    row = _sliced_row()
    late = aes_event.Slice(aes_event.door_call(WAIT, row.slice.start.nth + 1), aes_event.RETURN)
    our_marks = tier3._our_marks
    monkeypatch.setattr(tier3, "_our_marks", lambda sliced, *rest: our_marks(sliced._replace(slice=late), *rest))
    refusal = r"our slice starts at door call (\d+) .* where the ROM's starts at door call (\d+) .* another slice"
    with pytest.raises(AssertionError, match=refusal) as refused:
        tier3.measure(row, bench)
    ours, the_rom_s = map(int, re.search(refusal, str(refused.value)).groups())
    assert ours == the_rom_s + 1


def _our_run_astray(monkeypatch, flips):
    """Our blob's run taken astray (`aes_event.astray`): UNREAD_BYTE inverted at each stop `flips(watch, nth)` says."""
    our_windows = tier3.our_windows
    monkeypatch.setattr(tier3, "our_windows", lambda elf, delivered=None: aes_event.astray(our_windows(elf, delivered), flips))


def _our_run_astray_until_after(monkeypatch, healed_after):
    """Our blob's run with `UNREAD_BYTE` inverted from its first door call until the first one past door call
    `healed_after`, where it is put back: a C astray over that stretch in a byte nothing reads or rewrites, and whose
    FINAL image is the ROM's — so the whole run's differential sees nothing."""
    _our_run_astray(monkeypatch, lambda watch, _nth: watch.between_calls and watch.calls in (0, healed_after + 1))


def _door_calls_before(row, end):
    """How many door calls the ROM's run of `row`'s session has entered when it reaches the slice end `end`."""
    marks, _memory = aes_event.sliced_of(tier3.registered(row), row.slice)
    return marks.at(end, "the ROM's run").calls


def test_a_slice_our_build_diverged_before_is_refused_by_name(bench, monkeypatch):
    """THE RED: our run reaches the slice's start after the ROM's door calls, having spent what it spends — over
    another machine, which it leaves again before it returns: only the mark at the slice's start can see it, and
    refuses by name."""
    row = _sliced_row()
    _our_run_astray_until_after(monkeypatch, _door_calls_before(row, row.slice.start))
    with pytest.raises(AssertionError, match=rf"our run diverged before the slice's start .*1 bytes differ.*"
                                             rf"{UNREAD_BYTE:#x}"):
        tier3.measure(row, bench)


def test_a_divergence_healed_before_the_slice_s_start_is_no_refusal(bench, monkeypatch):
    """...and the same stretch astray, put back BEFORE the slice starts, is not the slice's business: priced as ever."""
    row = _sliced_row()
    priced = tier3.measure(row, bench)
    _our_run_astray_until_after(monkeypatch, 0)
    assert tier3.measure(row, bench).own_cycles == priced.own_cycles


def test_a_slice_our_build_diverged_inside_is_refused_at_its_end(bench, monkeypatch):
    """A slice from the ENTRY has no memory to compare at its start; astray from the first door call to past its end,
    it is refused at the end."""
    row = _sliced_row(SLICED_ROWS[0])
    assert row.slice.start == aes_event.ENTRY
    _our_run_astray_until_after(monkeypatch, _door_calls_before(row, row.slice.stop))
    with pytest.raises(AssertionError, match="our run diverged inside the slice"):
        tier3.measure(row, bench)


def test_a_slice_s_own_cycles_are_held_to_the_os_both_sides_ran_inside_it(bench, monkeypatch):
    """The slice's own split is held as the whole run's is: what each side spent in the OS both ran — its slice's
    cycles less its own — must be equal INSIDE the slice. RED: our blob's tally read two cycles short at each mark
    past the first leaves the whole run's equality standing and the slice's own two cycles light."""
    row = _sliced_row()
    our_marks, marked = tier3._our_marks, []

    def two_cycles_short(*slice_of):
        marks = our_marks(*slice_of)
        cost = marks._cost

        def short():
            marked.append(None)
            return {**cost(), "blob": cost()["blob"] - 2 * (len(marked) > 1)}
        marks._cost = short
        return marks
    monkeypatch.setattr(tier3, "_our_marks", two_cycles_short)
    with pytest.raises(AssertionError, match="inside its slice the OS both sides run cost ours"):
        tier3.measure(row, bench)


def test_a_slice_over_the_cap_is_refused_by_name(bench, monkeypatch):
    row = _sliced_row()
    spent = tier3.measure(row, bench).original_insns
    monkeypatch.setattr(aes_event, "SLICE_INSNS", spent - 1)
    with pytest.raises(AssertionError, match=rf"runs {spent} ROM instructions, past SLICE_INSNS \({spent - 1}\): cut it "
                                             rf"finer"):
        tier3.measure(row, bench)


def test_a_sliced_row_with_nothing_delivered_is_refused_by_name(bench):
    with pytest.raises(AssertionError, match="a sliced row is taken through interrupts"):
        tier3.measure(_sliced_row()._replace(delivered={}), bench)


def test_a_drop_over_bytes_the_watched_original_never_writes_is_refused(bench):
    """The watched original's WRITE LEDGER (`emu.bench_writes`) keeps the row's drop vetted per byte: the mask word
    widened by a word the ROM's run never stores is refused, as an unwatched row's is."""
    row = _interrupted_row()
    (lo, hi, why), = row.dropped
    widened = row._replace(dropped=((lo, hi + aes.WORD_BYTES, why),))
    with pytest.raises(AssertionError, match=f"never writes, the first at {hi:#x}"):
        tier3.measure(widened, bench)


def test_an_interrupted_row_is_refused_on_an_odd_access_its_build_alone_makes(bench, monkeypatch):
    """The C of a row taken through interrupts gets the full second differential — here the odd-access surface: our
    build answered an odd access the watched original's run was not is refused."""
    none = {"odd_accesses": 0, "odd_addresses": (), "odd_first_pc": 0}
    answers = iter((none, dict(none, odd_accesses=1, odd_addresses=(_PROBE_TARGET + 1,))))
    monkeypatch.setattr(emu, "odd_accesses", lambda: next(answers))
    with pytest.raises(AssertionError, match="address error on a 68000"):
        tier3.measure(_interrupted_row(), bench)


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


def test_an_alcyon_answer_is_priced_at_every_width_the_differential_compares():
    """Two maps keyed by the same answer types, in two modules — the differential's (`aes.RESULT_WIDTHS`) and the
    table's (`tier3._ALCYON_RETURNS`): a width one knows and the other does not would be a routine verified at one
    width and priced at none."""
    import aes
    assert set(tier3._ALCYON_RETURNS) == set(aes.RESULT_WIDTHS)


# ---- a row's DROPPED spans (`RomBench.measure`'s `dropped`, `case.tier3_dropped()`) -------------------------------
# A row over the staged `trap #1`: the ROM parks its own return site in LINEA_RETSAV and our build its caller's.
DROPPED_ROW = ("vdi_v_clsvwk", "the middle one")


def test_a_rows_drop_is_load_bearing_and_nothing_else_differs():
    """Without its drop the row's own compare reds at exactly the parked return; with it, it measures."""
    row = tier3.row_named(DROPPED_ROW)
    assert row.dropped, "the premise: the row drops a span"
    with pytest.raises(AssertionError, match=f"left different memory.*first {vdi.LINEA_RETSAV + 1:#x}"):
        tier3.measure(row._replace(dropped=()), tier3.shipped_bench())
    tier3.measure(row, tier3.shipped_bench())


def test_a_drop_over_bytes_the_original_never_writes_is_refused():
    """A drop can only hide what the ROM writes too: one over bytes it never stores is refused, since what
    differs there could only be our build's stores."""
    row = tier3.row_named(DROPPED_ROW)
    unwritten = vdi_helpers.ANSWERS_AT          # quad_xform's answer words: nothing this row stages or writes
    widened = row._replace(dropped=row.dropped + ((unwritten, unwritten + vdi.LONG_BYTES, "nothing the ROM writes"),))
    with pytest.raises(AssertionError, match="never writes"):
        tier3.measure(widened, tier3.shipped_bench())


def test_a_drop_one_longword_wider_than_the_park_is_refused():
    """PER BYTE: RETSAV widened by the longword after it — which the ROM never stores — is refused, where a
    whole-span "the ROM changed something in it" test let it through."""
    row = tier3.row_named(DROPPED_ROW)
    (lo, hi, why), = row.dropped
    widened = row._replace(dropped=((lo, hi + vdi.LONG_BYTES, why),))
    with pytest.raises(AssertionError, match=f"never writes, the first at {hi:#x}"):
        tier3.measure(widened, tier3.shipped_bench())


@pytest.mark.parametrize("name", sorted(case.tier3_dropped()))
def test_every_dropped_row_has_a_differential_that_drops_nothing(name, monkeypatch):
    """What makes a Tier 3 drop safe is a Tier 1 differential of the SAME machine that still compares those bytes:
    each dropped row's registered companion runs, every `case.run` it makes is at the row's entry with nothing
    dropped, and it staged the row's own pokes. A row TAKEN THROUGH INTERRUPTS has no `case.run`: its companion is
    `aes_event.interrupted` itself, every compare it makes leaving out the stack band alone."""
    registered = case.registered_case(name)
    if test_boot_snapshot.delivered_of(registered):
        _an_interrupted_companion_drops_nothing(name, registered, monkeypatch)
        return
    runs, run = [], case.run

    def recorded(entry, regs, glue, **kwargs):
        runs.append((entry, kwargs.get("dropped", ()), kwargs.get("dropped_windows", ())))
        return run(entry, regs, glue, **kwargs)

    monkeypatch.setattr(case, "run", recorded)
    result = case.tier3_undropped()[name]()
    assert runs and all(entry == registered[1] and not dropped and not windows for entry, dropped, windows in runs), runs
    assert vdi.make_image(registered[3]) == vdi.make_image(result.staged), f"{name}: the companion ran another machine"


# A session's slice rows share ONE companion (`aes_event.register_slices`: the whole session's differential), so it
# is RUN once per worker for them all (`aes_event.OncePerSession`) and every row is then held to it: its own machine,
# its own deliveries. What is kept of the run is what the rows read — the machine it staged, the deliveries it ran
# under, what it left out of its compares and what it derived again — not its two sixteen-megabyte images.
CompanionRun = namedtuple("CompanionRun", "staged delivered left_out redone")


def _companion_run(name, monkeypatch):
    """The companion of the registered row `name`, run with every `aes_event.differing` it makes recorded
    (`left_out`: what each left uncompared) and every derivation it makes again refused a run of its own (`redone`)."""
    left_out, redone, differing = [], [], aes_event.differing

    def recorded(image, rom_memory, not_compared=None):
        left_out.append(not_compared)
        return differing(image, rom_memory, not_compared)
    monkeypatch.setattr(aes_event, "differing", recorded)
    monkeypatch.setattr(aes_event, "deliveries", lambda *case_of: redone.append("deliveries"))
    monkeypatch.setattr(aes_event, "bench_differential", lambda *case_of: redone.append("bench_differential"))
    result = case.tier3_undropped()[name]()
    return CompanionRun(result.staged, result.delivered, left_out, redone)


_COMPANIONS_RUN = aes_event.OncePerSession(_companion_run)


def _an_interrupted_companion_drops_nothing(name, registered, monkeypatch):
    """...an interrupted row's: every `aes_event.differing` its companion makes compares all but the stack band, over
    the row's own machine — and over the row's own deliveries, neither derived again nor taken through the bench's
    second differential (the row's own pricing is that)."""
    companions = case.tier3_undropped()
    assert all(companions[name] is companions[row_name] for row_name, session in aes_event.INTERRUPTED_ROWS.items()
               if session is aes_event.session_of(name)), f"{name}: the rows of its session do not share one companion"
    ran = _COMPANIONS_RUN(name, registered[1:], name, monkeypatch)
    assert ran.left_out and all(each == frozenset(case.STACK_BAND) for each in ran.left_out), ran.left_out
    assert vdi.make_image(registered[3]) == vdi.make_image(ran.staged), f"{name}: the companion ran another machine"
    assert ran.delivered == test_boot_snapshot.delivered_of(registered) and not ran.redone, ran.redone


# ---- THE ODD-ACCESS SURFACE: what a 68000 bombs on and this oracle's CPU completes ------------------------------------
# kit.mk builds Musashi with address errors off, so a word or long access at an odd address runs to the right answer
# here and takes an ADDRESS ERROR on the machine. The shim counts them (`emu.odd_accesses`) and `rom_bench` refuses an
# m68k build that makes one the original did not — which is what reddened every sh_envrn / sh_find row while their
# frame locals were `uint8_t` arrays of an odd size. These pin the instrument itself: a probe of absolute accesses, staged in
# the single-buffer band, at even and at odd addresses — a word and a long, read and written: the four callbacks.
_PROBE_AT = staging.POINTER_ARGUMENTS
_PROBE_TARGET = _PROBE_AT + 0x100
_ABSOLUTE_ACCESS_BYTES = 6                 # the opcode word and a long address
_WIDE_ACCESSES = {"move.w d0,<xxx>.l": opcodes.MOVE_W_D0_ABSOLUTE, "move.l d0,<xxx>.l": opcodes.MOVE_L_D0_ABSOLUTE,
                  "move.w <xxx>.l,d0": opcodes.MOVE_W_ABSOLUTE_D0, "move.l <xxx>.l,d0": opcodes.MOVE_L_ABSOLUTE_D0}


def _odd_accesses_of(opcode, *targets):
    """What the oracle counted over a run of `opcode` (an absolute word or long access) at each of `targets`."""
    image = make_image({})
    program = b"".join(opcode.to_bytes(2, "big") + target.to_bytes(4, "big") for target in targets) + opcodes.RTS
    image[_PROBE_AT:_PROBE_AT + len(program)] = program
    emu.run_bench(image, _PROBE_AT, arg0=0, sp=emu.STACK_TOP, sentinel=emu.SENTINEL)
    return emu.odd_accesses()


@pytest.mark.parametrize("opcode", _WIDE_ACCESSES.values(), ids=_WIDE_ACCESSES)
def test_the_oracle_counts_a_word_or_long_access_at_an_odd_address(opcode):
    """...every one, keeping the addresses in order and the instruction that made the first; and per run: an even access after them counts
    none."""
    odd = _odd_accesses_of(opcode, _PROBE_TARGET, _PROBE_TARGET + 1, _PROBE_TARGET + 3)
    assert odd == {"odd_accesses": 2, "odd_addresses": (_PROBE_TARGET + 1, _PROBE_TARGET + 3),
                   "odd_first_pc": _PROBE_AT + _ABSOLUTE_ACCESS_BYTES}
    assert _odd_accesses_of(opcode, _PROBE_TARGET)["odd_accesses"] == 0


def test_the_bench_refuses_an_odd_access_the_original_did_not_make():
    odd = _odd_accesses_of(opcodes.MOVE_W_D0_ABSOLUTE, _PROBE_TARGET + 1)
    none = {"odd_accesses": 0, "odd_addresses": (), "odd_first_pc": 0}
    with pytest.raises(AssertionError, match="address error on a 68000"):
        rom_bench._vet_no_odd_access("the probe", odd, none)
    elsewhere = dict(odd, odd_addresses=(_PROBE_TARGET + 3,))
    with pytest.raises(AssertionError, match="address error on a 68000"):
        rom_bench._vet_no_odd_access("the probe", odd, elsewhere)
    # ...and the ones the ORIGINAL makes too, at the same addresses, are the case's (vst_height's chain from 0).
    rom_bench._vet_no_odd_access("the probe", odd, odd)
    rom_bench._vet_no_odd_access("the probe", none, none)


def test_a_row_is_refused_on_an_odd_access_its_build_alone_makes(bench, monkeypatch):
    """...and the measurement asks it: a row whose m68k build is answered an odd access the original's run was not."""
    none = {"odd_accesses": 0, "odd_addresses": (), "odd_first_pc": 0}
    answers = iter((none, dict(none, odd_accesses=1, odd_addresses=(_PROBE_TARGET + 1,))))
    monkeypatch.setattr(emu, "odd_accesses", lambda: next(answers))
    with pytest.raises(AssertionError, match="address error on a 68000"):
        tier3.measure(tier3.row_named(tier3.DISPATCH_LEAF), bench)
