"""The HARDWARE WRITE ledger, end to end through a real `harness.differential()` — Phase 10.

`test_hw_model.py` next door drives the two implementations directly and pins what each RECORDS.
What it cannot reach is the layer between them: `_vet_hw_write_state`, the per-case `hw_waiver` that
turns the comparison off for one address, and the ABI check that refuses a candidate which cannot
answer for a store the oracle made. This suite runs the miniature project of `kit_smoke_project.py`
— three stores as 68000 code against the same three as C — and measures those.

WHY EVERY CASE HERE IS ABOUT AN INVISIBLE EFFECT. The oracle DROPS a store above the image, and the
candidate makes none through the image pointer either, so both sides' memory is identical whatever
the reconstruction did. Every mutant below therefore passes the byte diff; the ordered write stream
is the only thing that separates it from a correct run, which is exactly the claim being measured.
"""
import contextlib

import pytest

from kit_smoke_project import (ACIA_DATA, ACIA_SEND_ENTRY, ACIA_STATUS, ACIA_TX_RDY,
                               HW_WRITE_ENTRY, IKBD_COMMAND, PEN0_COLOUR, PEN_PAIR_COLOURS,
                               SHIFTER_PEN0, SHIFTER_PEN1, bind)

harness = bind()
emu = harness.emu

# The three stores the .PRG makes, as the ledger records them: (address, width in bytes, value).
# The widths come from the harness's mirror of os.h rather than from three literals here, so a suite
# asserting an expected stream cannot drift from the tags the C actually records.
BYTE, WORD, LONG = (harness.OS_HW_WRITE_WIDTH_8, harness.OS_HW_WRITE_WIDTH_16,
                    harness.OS_HW_WRITE_WIDTH_32)
THE_THREE_STORES = [
    (SHIFTER_PEN0, WORD, PEN0_COLOUR),
    (SHIFTER_PEN1, LONG, PEN_PAIR_COLOURS),
    (ACIA_DATA, BYTE, IKBD_COMMAND),
]

MISMATCH = "hardware write stream mismatch"


def _run(glue_name, entry=HW_WRITE_ENTRY, **kwargs):
    """Run one of the .PRG's storing routines against a `kit_candidate.c` glue function."""
    return harness.differential(entry, {}, lambda lib, buf: getattr(lib, glue_name)(buf), **kwargs)


@contextlib.contextmanager
def _named(why):
    """Put a row's own argument into the failure when its case stops behaving as the row claims.

    A bare `assert why` next to the `pytest.raises` reads as a check and is not one — the label is a
    non-empty literal in every row. This makes it earn its place: if the mutant is no longer caught,
    the reader is told WHICH claim the suite has lost rather than only which glue function.
    """
    try:
        yield
    except BaseException as failure:
        failure.args = (f"{failure.args[0] if failure.args else failure}\n  the row claims: {why}",)
        raise


def test_the_smoke_prg_stores_to_the_addresses_the_candidate_does():
    """`kit_candidate.c` spells the three registers as literals of its own, because it is C and
    cannot ask the .PRG. Pin the ORACLE's stream equal to what this module names, so an address or a
    value corrected on one side fails as a drift rather than as a mutant that stopped being caught.
    """
    _, info = _run("g_hw_writes_the_three")
    assert info["regs"]["hw_writes"] == THE_THREE_STORES


def test_a_correct_reconstruction_of_three_hardware_stores_is_green():
    """The whole plumbing, end to end: the same three stores as 68000 code and as C, compared as one
    ordered stream.

    The image comparison contributes NOTHING here — neither side writes an image byte, which is the
    situation this surface exists for — so a green result is entirely the write stream's word.
    """
    diffs, _ = _run("g_hw_writes_the_three")
    assert diffs == []


# One row per way a store stream can differ; the second column is the row's own argument, which is
# what the failure names when a mutant stops being caught.
DIVERGENCES = (
    ("g_hw_writes_one_short", "a store the original makes is MISSING"),
    ("g_hw_writes_one_extra", "an EXTRA store, at an address the run does touch"),
    ("g_hw_writes_reordered", "the same three stores in the wrong ORDER"),
    ("g_hw_writes_the_wrong_width", "the right value at the right address, one width too wide"),
    ("g_hw_writes_the_wrong_value", "one bit wrong in the colour"),
    ("g_hw_writes_nothing", "a reconstruction that reaches no hardware at all"),
)


@pytest.mark.parametrize("glue,why", DIVERGENCES)
def test_each_shape_of_divergence_reds(glue, why):
    """One case per way a store stream can differ. Each of these leaves the image byte-for-byte
    identical to a correct run's, so a suite without the ledger would call every one of them
    verified — which is the measurement, not the assertion."""
    with pytest.raises(AssertionError, match=MISMATCH), _named(why):
        _run(glue)


def test_the_reordered_mutant_is_invisible_to_everything_else(monkeypatch):
    """`_vet_hw_write_state` is load-bearing, and this measures it rather than asserting it.

    `g_hw_writes_reordered` makes exactly the three stores the original makes, at the same addresses,
    the same widths and the same values — so the image, the registers and every other ledger are a
    correct run's. With the comparison stubbed out the differential comes back GREEN. Restore it and
    the same run reds. That gap IS the check's value.
    """
    monkeypatch.setattr(harness, "_vet_hw_write_state", lambda entry, o_regs, waived: None)
    diffs, _ = _run("g_hw_writes_reordered")
    assert diffs == [], "the mutant changed an image byte, so this case measures the wrong thing"

    monkeypatch.undo()
    with pytest.raises(AssertionError, match=MISMATCH):
        _run("g_hw_writes_reordered")


REFUSED = "os_. call\\(s\\) the TOS model REFUSES"


def test_a_store_into_the_image_is_refused_rather_than_ledgered():
    """`hw_write*` is the HARDWARE door. A candidate that reaches image memory through it has stored
    where the byte diff should have seen it, and the oracle logs no such entry either — so it is a
    refusal, which `_vet_no_os_refusal` turns into "this case tested nothing"."""
    with pytest.raises(AssertionError, match=REFUSED):
        _run("g_hw_writes_into_the_image")


def test_the_untranslated_address_form_is_refused_rather_than_masked():
    """`$ffff8240` and `$ff8240` are one register to the 68000's 24-bit bus, and the ORACLE folds
    them together because that is what the bus does to an instruction's operand. This door does not:
    a reconstruction spells the address itself, and masking here would let the two sides ledger two
    spellings of one register — reporting an address bug that is really a form one, and defeating an
    address-keyed `hw_waiver`, which could then match one side only.

    The mutant is a CORRECT store at a real register in the wrong form, so nothing but the form
    separates it from `g_hw_writes_the_three`'s first store."""
    with pytest.raises(AssertionError, match=REFUSED):
        _run("g_hw_writes_the_untranslated_form")


# ---------------------------------------------------------------- the per-case waiver

WAIVER_REASON = "the candidate models this routine's palette half as a no-op, for this test"


def test_a_waived_address_is_dropped_from_both_sides_and_recorded():
    """The opt-out, and the two things that make it honest.

    `g_hw_writes_one_short` misses the palette longword and nothing else. Waiving that ONE address
    makes the case green — and leaves the other two stores compared, which the next case measures.
    The waiver is recorded in `harness.HW_WAIVERS` with its reason, so a run can be asked which
    addresses it stopped looking at. It is recorded ONCE however many cases apply it, which is why
    this asserts membership rather than a slice of new entries.
    """
    diffs, _ = _run("g_hw_writes_one_short", hw_waiver={SHIFTER_PEN1: WAIVER_REASON})
    assert diffs == []
    assert harness.HW_WAIVERS.count((HW_WRITE_ENTRY, SHIFTER_PEN1, WAIVER_REASON)) == 1

    # ...and applying it a second time does not append a second copy.
    _run("g_hw_writes_one_short", hw_waiver={SHIFTER_PEN1: WAIVER_REASON})
    assert harness.HW_WAIVERS.count((HW_WRITE_ENTRY, SHIFTER_PEN1, WAIVER_REASON)) == 1


def test_a_waiver_covers_only_the_address_it_names():
    """The same waiver against a mutant that ALSO gets the colour wrong: the waived longword is
    excused and the un-waived word still reds. A waiver that switched the whole comparison off would
    make this green, which is the difference between an address list and a flag."""
    with pytest.raises(AssertionError, match=MISMATCH):
        _run("g_hw_writes_one_short_and_the_wrong_colour",
             hw_waiver={SHIFTER_PEN1: WAIVER_REASON})


def test_a_waiver_retires_itself_when_the_candidate_starts_writing():
    """The waiver's premise is that the reconstruction makes no access at that address. The day
    somebody gives it a body the premise is false, and without this the waiver would go on dropping
    BOTH sides' entries — a green suite over stores nobody compares, with the project's STATUS row
    claiming they are pinned. So a candidate that reaches a waived address fails the case.

    `g_hw_writes_the_three` is the CORRECT reconstruction, which is the point: it is not a mutant,
    and the case still reds — the finding is about the waiver, not about the code it excused."""
    with pytest.raises(AssertionError, match="the waiver's premise"):
        _run("g_hw_writes_the_three", hw_waiver={SHIFTER_PEN1: WAIVER_REASON})


@pytest.mark.parametrize("key", ("0xff8244", None, 1.5, -1))
def test_a_waiver_key_that_is_not_an_address_is_refused(key):
    """The ledgers hold integers, so a key of any other type matches nothing and waives nothing —
    and the case then reds naming the very address the author believes is excused. Silent, and easy
    to write when a waiver dict is built from a table or a format string."""
    with pytest.raises(AssertionError, match="is not an address"):
        _run("g_hw_writes_one_short", hw_waiver={key: WAIVER_REASON})


@pytest.mark.parametrize("reason", ("", "   ", None, 7))
def test_a_waiver_without_a_reason_is_refused(reason):
    """Waiving an address removes the only surface that can see the traffic there, so the case has
    to say why. An opt-out nobody has to justify becomes the default way past a red."""
    with pytest.raises(AssertionError, match="has no reason"):
        _run("g_hw_writes_one_short", hw_waiver={SHIFTER_PEN1: reason})


def test_a_waiver_that_is_not_an_address_map_is_refused():
    """`hw_waiver` is `{address: reason}`. A bare truthy value would read as "waive everything",
    which is the one thing this parameter must not be able to say."""
    with pytest.raises(TypeError, match="hw_waiver must be"):
        _run("g_hw_writes_one_short", hw_waiver=True)


# ---------------------------------------------------------------- the ACIA status slot

def test_the_send_loop_terminates_on_the_models_own_default():
    """`ikbd_send_cmd`'s shape, and the whole reason the ACIA status slot carries a MODEL DEFAULT.

    Neither side declares anything. The status byte is served TDRE-set from `os_hw_model_defaults`,
    so the .PRG's `beq.s` back to its own `btst` is taken zero times and the C `while` runs once —
    and the read is LEDGERED, which is what makes "the candidate polled at all" a fact rather than an
    assumption. Before Phase 10 the shim answered this address 0x02 from a hard-coded `return` that
    nothing compared.
    """
    diffs, info = _run("g_hw_acia_send", entry=ACIA_SEND_ENTRY)
    assert diffs == []
    assert info["regs"]["hw_events"] == [(ACIA_STATUS, ACIA_TX_RDY)]
    assert info["regs"]["hw_writes"] == [(ACIA_DATA, BYTE, IKBD_COMMAND)]


def test_a_case_may_declare_another_status_and_its_declaration_wins():
    """The default fills in UNDER a case's declaration, never over it. Declared with every bit set —
    still TDRE, so both sides still leave on the first poll — the ledger reports the case's byte and
    not the model's."""
    declared = 0xFF
    _, info = _run("g_hw_acia_send", entry=ACIA_SEND_ENTRY, hw_seed={ACIA_STATUS: declared})
    assert info["regs"]["hw_events"] == [(ACIA_STATUS, declared)]


def test_a_status_with_TDRE_clear_is_a_run_the_model_cannot_serve():
    """The slot is STATIC: one declaration describes every read of it, so a declaration with the bit
    CLEAR means the .PRG's `beq.s` is taken for ever. That is the model's non-goal stated as a run —
    the oracle spends its instruction cap and `emu.run` throws the case away — and it is why the
    default has the bit SET rather than being a fabricated 0.

    The cap is tiny on purpose: the spin is two instructions, and the point is that it never ends.
    """
    with pytest.raises(Exception, match="instruction"):
        _run("g_hw_acia_send", entry=ACIA_SEND_ENTRY, hw_seed={ACIA_STATUS: 0}, max_insns=200)


# ---------------------------------------------------------------- the widened staged-file table

def test_the_staged_file_table_holds_its_full_slot_count():
    """`OS_FS_SLOTS` grew from 8 to 32 for Zynaps's boot, which opens about thirty files in one
    straight line. Stage the full count and check every one resolves to its own handle — the table
    is written entry by entry, so a slot that ran past the end would take the next file's bytes with
    it (os.h's compile-time check is the other half of this)."""
    files = [(f"f{slot}.dat", bytes([slot]) * 4) for slot in range(harness.OS_FS_SLOTS)]
    pokes, handles = harness.stage_files(files)
    assert len(handles) == harness.OS_FS_SLOTS
    assert handles[files[0][0]] == harness.OS_FS_FIRST_HANDLE
    assert handles[files[-1][0]] == harness.OS_FS_FIRST_HANDLE + harness.OS_FS_SLOTS - 1
    # Each entry's own table row, and each file's own staging block: no two share an address.
    assert len(pokes) == 2 * harness.OS_FS_SLOTS


def test_one_file_past_the_table_is_refused():
    """The boundary from the other side. Nothing in the C could catch this — `os_fopen` walks
    `OS_FS_SLOTS` entries and would simply never see the extra one, while its bytes sat on top of the
    first staged file's."""
    files = [(f"f{slot}.dat", b"x") for slot in range(harness.OS_FS_SLOTS + 1)]
    with pytest.raises(AssertionError, match="slot table"):
        harness.stage_files(files)
