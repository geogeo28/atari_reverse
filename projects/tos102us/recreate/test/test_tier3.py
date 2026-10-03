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
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

from harness import BENCH_DIR

sys.path.insert(0, str(BENCH_DIR))

import tier3                                               # noqa: E402  (the registry and the bar)
# ...and the caller a transcription row is netted by, whose cost `trap.py` measures.
import trap                                                # noqa: E402
# ...and the VDI's door and pure helpers, whose declared contracts and C signatures the VDI calls derive from.
import aes                                                 # noqa: E402
import aes_event                                           # noqa: E402
import case                                                # noqa: E402
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
def measurement_of(bench):
    """A row's `Measurement`, measured once per worker — mechanism (T) asks it of a routine's `.S` rows
    for each of its C rows, and those are the same few rows every time."""
    measured = {}

    def measurement(row):
        key = (row.symbol, row.case)
        if key not in measured:
            measured[key] = tier3.measure(row, bench)
        return measured[key]
    return measurement


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
def test_the_m68k_build_equals_the_original_and_is_within_the_bar(row, bench, dispatch, measurement_of):
    """One row: measure both sides over one case — which raises if the m68k build diverged — then
    put the measurement through the same `verdict` the table prints."""
    measured = tier3.measure(row, bench)
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
    monkeypatch.setattr(tier3, "goes_through_the_door", lambda _row: False)
    with pytest.raises(AssertionError, match="OUTSIDE the event door's windows"):
        tier3._measure_through_the_os(row, bench)


def test_the_door_watch_stops_at_the_entries_alone_and_refuses_one_entered_but_by_a_door_call():
    """The watch stops at the door's entries THEMSELVES (a set of exact PCs, never a band that would swallow the AES
    text between them), then at the return address the call left — and at the dispatcher, where a call that would
    switch processes is refused by name; and a door entry reached from a return address no door call leaves is
    refused."""
    windows = tier3.our_windows(tier3.BUILT_ELF)
    entry, back = min(windows.entries), min(windows.returns)
    stack = 0x100
    memory = bytearray(stack) + back.to_bytes(4, "big") + bytes(max(aes_event.FRAME_BYTES.values()))
    assert windows.first == frozenset(aes_event.ENTRIES)
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


def test_the_door_calls_are_the_door_s_entries_and_their_users_the_aes_s():
    """Derived from the blob, held to the door's own list: every `jsr` of the m68k build into the AES's text lands on an
    entry the event door serves, and every row reaching one is a routine of the AES's text."""
    assert set(tier3.door_calls(tier3.BUILT_ELF).values()) == set(aes_event.ENTRIES)
    through = [row for row in tier3.ROWS if tier3.goes_through_the_door(row)]
    assert {row.symbol for row in through} >= {"aes_gr_stilldn", "aes_gr_watchbox", "aes_ap_sendmsg"}
    assert all(aes.AES_TEXT[0] <= tier3.rom_address(row) < aes.AES_TEXT[1] for row in through)


def test_the_door_rule_vets_the_call_graph_it_derives_from(monkeypatch):
    def vetted(_graph):
        raise _Vetted
    monkeypatch.setattr(tier3, "vet_no_row_is_ambiguous", vetted)
    with pytest.raises(_Vetted):
        tier3._reaching_the_door.__wrapped__()


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


def _an_interrupted_companion_drops_nothing(name, registered, monkeypatch):
    """...an interrupted row's: every `aes_event.differing` its companion makes compares all but the stack band, over
    the row's own machine — and over the row's own deliveries, neither derived again nor taken through the bench's
    second differential (the row's own pricing is that)."""
    left_out, differing = [], aes_event.differing

    def recorded(image, rom_memory, not_compared=None):
        left_out.append(not_compared)
        return differing(image, rom_memory, not_compared)
    monkeypatch.setattr(aes_event, "differing", recorded)
    redone = []
    monkeypatch.setattr(aes_event, "deliveries", lambda *case_of: redone.append("deliveries"))
    monkeypatch.setattr(aes_event, "bench_differential", lambda *case_of: redone.append("bench_differential"))
    result = case.tier3_undropped()[name]()
    assert left_out and all(each == frozenset(case.STACK_BAND) for each in left_out), left_out
    assert vdi.make_image(registered[3]) == vdi.make_image(result.staged), f"{name}: the companion ran another machine"
    assert result.delivered == test_boot_snapshot.delivered_of(registered) and not redone, redone


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
