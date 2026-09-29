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
import ctypes
import functools
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))

import tier3                                               # noqa: E402  (the registry and the bar)
# ...and the caller a transcription row is netted by, whose cost `trap.py` measures.
import trap                                                # noqa: E402
# ...and the VDI's door and pure helpers, whose declared contracts and C signatures the VDI calls derive from.
import case                                                # noqa: E402
import vdi                                                 # noqa: E402
import vdi_helpers                                         # noqa: E402
# ...and the glue generator, whose thunks mechanism (T→G) counts.
import shipped_glue                                        # noqa: E402
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


@pytest.fixture(scope="module")
def ratio_of(bench):
    """A row's measured ratio, measured once per worker — mechanism (T) asks it of a routine's `.S` rows
    for each of its C rows, and those are the same few rows every time."""
    measured = {}

    def ratio(row):
        key = (row.symbol, row.case)
        if key not in measured:
            measured[key] = tier3.measure(row, bench).ratio
        return measured[key]
    return ratio


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
def test_the_m68k_build_equals_the_original_and_is_within_the_bar(row, bench, dispatch, ratio_of):
    """One row: measure both sides over one case — which raises if the m68k build diverged — then
    put the measurement through the same `verdict` the table prints."""
    measured = tier3.measure(row, bench)
    state = tier3.verdict(row, measured, dispatch, ratio_of)
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
                f"(include/vdi/transcribed.h), but its `.S` rows no longer carry it: one is over the bar, "
                f"or there is none. Mechanism (T) admits the C only while the `.S` a target build ships is "
                f"priced at or under the bar on every row")
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

REGISTER_HELPERS = [name for name in vdi.PRIMITIVES if vdi.core_symbol(name) in vdi_helpers.REGISTER_SIGNATURES]


@pytest.mark.parametrize("name", REGISTER_HELPERS)
def test_a_register_helper_s_host_signature_is_its_declared_contract(name):
    """The Alcyon helpers' Tier 3 calls are DERIVED from `vdi.ALCYON`; the three register routines' come
    from `vdi.declare_primitive` instead, so this is where the two statements of one C signature are held
    equal: the image, a longword per argument register, a results pointer when the answer is several
    registers, and D0 returned when it is among them."""
    contract = vdi.PRIMITIVES[name]
    restype, argtypes = vdi_helpers.REGISTER_SIGNATURES[vdi.core_symbol(name)]
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
    assert not unpriced, (f"{unpriced} are in include/vdi/transcribed.h with no `.S` row in Tier 3 — register "
                          f"their transcription cases (`vdi.register_transcription`)")


def test_no_transcribed_c_row_carries_a_written_acceptance():
    """The rule REPLACES the entries: an acceptance beside it would carry the C rows on its own the day
    the `.S` stopped doing so, which is exactly the state (T) exists to refuse."""
    written = sorted(key for key in tier3.PERF_ACCEPTED if tier3.is_transcribed_c_row(tier3.row_named(key)))
    assert not written, f"tier3.PERF_ACCEPTED writes down {written}, which mechanism (T) carries — drop them"


def test_the_rule_carries_a_transcribed_c_row(bench, dispatch, ratio_of):
    row = tier3.row_named(TRANSCRIBED_C_ROW)
    measured = tier3.measure(row, bench)
    assert measured.ratio > tier3.TIER3_FUNCTION_BAR, "the premise: this C row is over the bar"
    assert tier3.verdict(row, measured, dispatch, ratio_of) == "transcribed"


def test_one_s_row_drifting_over_the_bar_reds_the_c_rows(bench, dispatch, ratio_of):
    """Every `.S` row but one measured as it is, that one just over the bar: the C row goes OVER."""
    row = tier3.row_named(TRANSCRIBED_C_ROW)
    measured = tier3.measure(row, bench)
    drifted = tier3.SHIPPED_ROWS[tier3.rom_address(row)][-1]
    over = tier3.TIER3_FUNCTION_BAR + tier3.RATIO_TOLERANCE

    def with_one_drifted(each):
        return over if each is drifted else ratio_of(each)
    assert tier3.verdict(row, measured, dispatch, with_one_drifted) == "OVER"


def test_a_routine_whose_s_rows_are_gone_reds_the_c_rows(bench, dispatch, ratio_of, monkeypatch):
    row = tier3.row_named(TRANSCRIBED_C_ROW)
    measured = tier3.measure(row, bench)
    monkeypatch.setitem(tier3.SHIPPED_ROWS, tier3.rom_address(row), ())
    assert tier3.verdict(row, measured, dispatch, ratio_of) == "OVER"


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
    callers = {caller for caller, _core in vdi.C_CALLERS_OF_TRANSCRIBED_CORES}
    assert callers <= tier3._reaching_transcribed_cores()


def test_a_row_that_ships_through_a_call_is_measured_on_the_shipped_blob(bench, dispatch, ratio_of):
    row = tier3.row_named(THROUGH_A_CALL_ROW)
    assert tier3.ships_through_a_call(row)
    on_the_twins = bench.measure(row.entry, row.symbol, args=row.args, regs=row.regs, pokes=row.pokes,
                                 returns=row.returns)
    assert on_the_twins.ratio > tier3.TIER3_FUNCTION_BAR, "the premise: through the C twin it is over the bar"
    measured = _shipped_measurement(THROUGH_A_CALL_ROW)
    assert measured.ratio <= tier3.TIER3_FUNCTION_BAR
    assert tier3.verdict(row, measured, dispatch, ratio_of) == "through"


def test_a_row_that_ships_through_a_call_goes_over_with_its_callee(bench, dispatch, ratio_of):
    """Nothing carries a (T→) row but its own measurement: the same row costing what a drifted `.S` would
    make it cost — the thunks' cycles unchanged, everything behind them over the bar — is OVER; there is no
    entry for it to hide behind, and the glue rule (T→G) takes off only the thunks."""
    row = tier3.row_named(THROUGH_A_CALL_ROW)
    measured = _shipped_measurement(THROUGH_A_CALL_ROW)
    over = _with_body_grown_to(measured, bench, tier3.TIER3_FUNCTION_BAR + tier3.RATIO_TOLERANCE)
    assert tier3.pin_of(row) is None
    assert tier3.verdict(row, over, dispatch, ratio_of) == "OVER"


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
    graph = vdi.graph_of_listing(IMMEDIATE_CALL_LISTING, {}, starts)
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
    graph = vdi.graph_of_listing(IMMEDIATE_DATA_LISTING, {}, starts)
    assert graph == {"comparer": set(), "helper": set()}


# ...and the QUALIFICATION of a name several functions share, by where each is DEFINED (`vdi.symbol_origins`): two
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
                  (GLOBAL_AT, "vdi_row"): vdi.GLOBAL_ORIGIN, (PART_AT, "vdi_row.part.0"): "row.c",
                  (LEFT_AT, "left"): vdi.GLOBAL_ORIGIN, (RIGHT_AT, "right"): vdi.GLOBAL_ORIGIN}


def test_the_call_graph_keeps_two_statics_clones_apart_and_folds_a_globals_own():
    graph = vdi.graph_of_listing(CLONES_LISTING, {}, {}, CLONES_ORIGINS)
    assert graph == {"outline@a.c": {"left"}, "outline@b.c": {"right"}, "vdi_row": {"left"}, "left": set(),
                     "right": set()}


# A reference with no address printed, to a name two functions share: it cannot say which, so it names both — an
# edge too many prices a row on the shipped blob, where the refusal it met before stopped the whole graph.
ADDRESSLESS_LISTING = CLONES_LISTING + f"""
{RIGHT_AT + 0x100:08x} <caller>:
   {RIGHT_AT + 0x100:x}:\t4ebb 0000      \tjsr %pc@(0) <outline.isra.0>
"""


def test_the_call_graph_reads_an_addressless_reference_to_a_shared_name_as_every_one_of_them():
    origins = {**CLONES_ORIGINS, (RIGHT_AT + 0x100, "caller"): vdi.GLOBAL_ORIGIN}
    graph = vdi.graph_of_listing(ADDRESSLESS_LISTING, {}, {}, origins)
    assert graph["caller"] == {"outline@a.c", "outline@b.c"}


@pytest.mark.parametrize("symbol", ("vdi_v_clswk", sorted(vdi.TRANSCRIBED_CORES)[0]))
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
    """The glue the rule counts is exactly the generated thunks: one disjoint sized range each."""
    ranges = tier3.glue_ranges()
    assert len(ranges) == len(shipped_glue.thunked_cores())
    assert all(start < end <= following for (start, end), (following, _) in zip(ranges, ranges[1:])), ranges


def test_the_glue_rule_carries_a_row_over_the_bar_only_by_its_thunks(bench, dispatch, ratio_of):
    row = tier3.row_named(GLUE_ROW)
    measured = _shipped_measurement(GLUE_ROW)
    assert measured.ratio > tier3.TIER3_FUNCTION_BAR, "the premise: as shipped this row is over the bar"
    assert tier3.pin_of(row) is None, "the rule carries it, so no entry may"
    assert tier3.ratio_net_of_glue(measured) <= tier3.TIER3_FUNCTION_BAR
    assert tier3.verdict(row, measured, dispatch, ratio_of) == "glue"


def test_the_glue_rule_refuses_the_row_when_its_own_body_grows(bench, dispatch, ratio_of):
    """The same row with its glue unchanged and its BODY past the bar net of it: OVER, and nothing else."""
    row = tier3.row_named(GLUE_ROW)
    measured = _shipped_measurement(GLUE_ROW)
    grown = _with_body_grown_to(measured, bench, tier3.TIER3_FUNCTION_BAR + tier3.RATIO_TOLERANCE)
    assert tier3.ratio_net_of_glue(grown) > tier3.TIER3_FUNCTION_BAR
    assert tier3.verdict(row, grown, dispatch, ratio_of) == "OVER"


def test_the_glue_rule_refuses_a_real_row_over_the_bar_net_of_its_glue(bench, dispatch, ratio_of, monkeypatch):
    """RED on a measured row, not a made-up one: vq_key_s pays glue too, but its body alone is over the bar,
    so with its written entry gone the rule leaves it OVER."""
    row = tier3.row_named(OVER_NET_OF_GLUE_ROW)
    measured = _shipped_measurement(OVER_NET_OF_GLUE_ROW)
    assert tier3.glue_cycles_of(measured) > 0, "the premise: this row calls through a thunk"
    assert tier3.ratio_net_of_glue(measured) > tier3.TIER3_FUNCTION_BAR
    monkeypatch.delitem(tier3.PERF_ACCEPTED, OVER_NET_OF_GLUE_ROW)
    assert tier3.verdict(row, measured, dispatch, ratio_of) == "OVER"


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


# ---- a row's DROPPED spans (`RomBench.measure`'s `dropped`, `vdi.TIER3_DROPPED`) ---------------------------------
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


@pytest.mark.parametrize("name", sorted(vdi.TIER3_DROPPED))
def test_every_dropped_row_has_a_differential_that_drops_nothing(name, monkeypatch):
    """What makes a Tier 3 drop safe is a Tier 1 differential of the SAME machine that still compares those bytes:
    each dropped row's registered companion runs, every `case.run` it makes is at the row's entry with nothing
    dropped, and it staged the row's own pokes."""
    runs, run = [], case.run

    def recorded(entry, regs, glue, **kwargs):
        runs.append((entry, kwargs.get("dropped", ()), kwargs.get("dropped_windows", ())))
        return run(entry, regs, glue, **kwargs)

    monkeypatch.setattr(case, "run", recorded)
    result = vdi.TIER3_UNDROPPED[name]()
    registered, = (row for row in vdi.CASES if row[0] == name)
    assert runs and all(entry == registered[1] and not dropped and not windows for entry, dropped, windows in runs), runs
    assert vdi.make_image(registered[3]) == vdi.make_image(result.staged), f"{name}: the companion ran another machine"
