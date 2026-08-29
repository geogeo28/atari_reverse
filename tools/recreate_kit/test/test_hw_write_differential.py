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

from kit_smoke_project import (ACIA_DATA, ACIA_RECEIVE_ENTRY, ACIA_RECEIVE_TWICE_ENTRY,
                               ACIA_SEND_ENTRY, ACIA_SEND_THEN_RECEIVE_ENTRY, ACIA_STATUS,
                               ACIA_TX_RDY,
                               HW_RMW_ENTRY, HW_WRITE_ENTRY, IKBD_COMMAND,
                               MFP_ACIA_CHANNEL_BIT, MFP_IERB, MFP_ISRA,
                               PEN0_COLOUR, PEN_PAIR_COLOURS,
                               SHIFTER_MODE, SHIFTER_PEN0, SHIFTER_PEN1, bind)

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


# ---------------------------------------------------------------- the ACIA data slot

# Two bytes an IKBD really puts on the port, used as the declarations below: the joystick packet's
# own header, and a key-release scancode (bit 7 set over the press code for '1').
IKBD_JOYSTICK_HEADER = 0xFD
IKBD_RELEASE_SCANCODE = 0x82


@pytest.mark.parametrize("declared", (IKBD_JOYSTICK_HEADER, IKBD_RELEASE_SCANCODE))
def test_the_acia_data_port_serves_the_byte_the_case_declares(declared):
    """An ACIA interrupt handler's entry read, which is the whole reason `$fffc02` is a slot.

    Before it, a read of the data port was an ordinary off-image `0` — unledgered, undeclared and
    identical on both sides, so a handler that branched on the byte took the same wrong arm twice
    and the differential agreed with itself. That is Phase 7's founding defect at the one address
    Phase 7 had left out.

    TWO DECLARATIONS, because the byte is the CASE's and not the model's: unlike the status port next
    door the data port carries no default, so what a run is served has to follow what it declared
    rather than one fixed answer that would pass either way.
    """
    diffs, info = _run("g_hw_acia_receive", entry=ACIA_RECEIVE_ENTRY,
                       hw_seed={ACIA_DATA: declared})
    assert diffs == []
    assert info["regs"]["hw_events"] == [(ACIA_STATUS, ACIA_TX_RDY), (ACIA_DATA, declared)]


def test_an_undeclared_acia_data_read_is_refused():
    """...and NOTHING fills in under it. The status port has a model default because a quiescent
    6850 always settles at TDRE-set; what the data port holds is whatever the controller last sent,
    which no default can stand in for. So an undeclared read is the ordinary Phase 7 refusal."""
    with pytest.raises(AssertionError, match="does not declare") as raised:
        _run("g_hw_acia_receive", entry=ACIA_RECEIVE_ENTRY)
    assert hex(ACIA_DATA) in str(raised.value)


def test_two_acia_data_reads_in_one_run_are_refused():
    """VOLATILE, and this is the case that makes it a rule rather than a comment.

    Each read POPS the receive register, so two reads in one run take two different bytes off the
    controller and one declaration cannot describe both. The candidate is faithful — it makes the
    same two `hw_read8` calls — so without the refusal the two streams would match entry for entry
    and the run would come back green about a port that never moved.

    The remedy is the case's SHAPE and not a bigger declaration, which is why the message must not
    offer one: a handler that reads the port twice is two runs, each declaring the byte the machine
    held then.
    """
    with pytest.raises(AssertionError, match="MORE THAN ONCE in one run") as raised:
        _run("g_hw_acia_receives_twice", entry=ACIA_RECEIVE_TWICE_ENTRY,
             hw_seed={ACIA_DATA: IKBD_JOYSTICK_HEADER})
    message = str(raised.value)
    assert hex(ACIA_DATA) in message
    assert "hw_seed={" not in message, (
        "the refusal offers a declaration as the remedy, which cannot work — one declaration is one "
        "byte, and a handler that reads the port twice needs two runs")


def test_sending_on_the_acia_does_not_make_a_later_receive_stale():
    """THE SPLIT-REGISTER EXEMPTION, and the case it exists for.

    Every other modeled address is one register, so "the run wrote it and then read it back" means
    the seed no longer describes what a read yields, and the model refuses. `$fffc02` is not one
    register: a write lands in the 6850's TRANSMIT register and a read pops its RECEIVE register.
    So the send-then-service shape every real IKBD routine has — and every Zynaps slice that composes
    `ikbd_send_cmd` with ACIA servicing will have — is a legitimate run, and refusing it would be a
    diagnosis that does not hold with a remedy (end the case before the write) that throws the case
    away.

    The control is `test_a_write_then_a_read_of_one_modeled_byte_is_refused` above, which is the same
    shape at a one-register address and must still red.
    """
    diffs, info = _run("g_hw_acia_send_then_receive", entry=ACIA_SEND_THEN_RECEIVE_ENTRY,
                       hw_seed={ACIA_DATA: IKBD_JOYSTICK_HEADER})
    assert diffs == []
    assert info["regs"]["hw_writes"] == [(ACIA_DATA, BYTE, IKBD_COMMAND)]
    assert info["regs"]["hw_events"] == [(ACIA_DATA, IKBD_JOYSTICK_HEADER)]


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


# ------------------------------------------- the READ-MODIFY-WRITE operations (hw.h's bset/bclr/and)

# What the .PRG's `bset #6,$fffa09` / `bclr #0,$fffa0f` / `andi.b #$fc,$ff8260` leave in the ledger.
# Every read half is of an address the seeded READ model does not name, so the oracle serves a
# fabricated 0 and stores what that 0 produces: the bit alone, a zero, and a zero.
FABRICATED_READ = 0
THE_THREE_READ_MODIFY_WRITES = [
    (MFP_IERB, BYTE, FABRICATED_READ | (1 << MFP_ACIA_CHANNEL_BIT)),
    (MFP_ISRA, BYTE, FABRICATED_READ),
    (SHIFTER_MODE, BYTE, FABRICATED_READ),
]


def _rmw(glue_name, **kwargs):
    """Run the .PRG's read-modify-write trio against a `kit_candidate.c` glue function."""
    return _run(glue_name, entry=HW_RMW_ENTRY, **kwargs)


def test_the_smoke_prg_read_modify_writes_the_registers_the_candidate_does():
    """`kit_candidate.c` spells the three registers and the bit as literals of its own, exactly as
    `test_the_smoke_prg_stores_to_the_addresses_the_candidate_does` says of the plain stores. Pin the
    ORACLE's stream equal to what this module names, so an address corrected on one side fails as a
    drift rather than as a mutant that quietly stopped being caught.

    It is also the measurement behind `hw.h`'s claim about what src/hw.c must produce: these three
    values ARE the bytes the oracle's own `bset`/`bclr`/`andi.b` computed from its fabricated 0.
    """
    _, info = _rmw("g_hw_rmw_the_three")
    assert info["regs"]["hw_writes"] == THE_THREE_READ_MODIFY_WRITES


def test_a_correct_reconstruction_of_three_read_modify_writes_is_green():
    """The trio spelt as the OPERATIONS it is — `hw_bset8`, `hw_bclr8`, `hw_and8` — against the same
    three instructions as 68000 code. Nothing here writes an image byte, so a green result is
    entirely the write stream's word."""
    diffs, _ = _rmw("g_hw_rmw_the_three")
    assert diffs == []


def test_the_operations_are_indistinguishable_off_target_from_the_defect_they_retire():
    """THE MEASUREMENT THAT SAYS WHY THE OPERATIONS EXIST, and it is a GREEN one.

    `g_hw_rmw_spelt_as_plain_stores` is the shape every project shipped before these names: compute
    the value from the fabricated 0 and call `hw_write8`. It passes — the ledger holds the byte, and
    off target the byte is the same. What differs is what a TARGET build compiles: the operations
    become the real `bset`/`bclr`/`andi.b` on the register and preserve the bits the original
    preserves, while the plain stores clobber them (0x40 over TOS's whole IERB, every in-service
    channel acknowledged at once, 0 into the resolution register).

    So no off-target surface can separate the two, and that is the finding rather than a gap to
    close: the operation has to be SPELT, because nothing downstream can infer it.
    """
    diffs, info = _rmw("g_hw_rmw_spelt_as_plain_stores")
    assert diffs == []
    assert info["regs"]["hw_writes"] == THE_THREE_READ_MODIFY_WRITES


def test_a_bset_of_the_wrong_bit_reds():
    """Half of what the ledger CAN see. A `bset`'s ledgered value is `0 | (1 << bit)`, a different
    byte for every bit, so the channel it opens is pinned as tightly as any plain store's value."""
    with pytest.raises(AssertionError, match=MISMATCH):
        _rmw("g_hw_rmw_sets_the_wrong_bit")


def test_a_bclr_of_the_wrong_bit_is_green_and_that_is_the_residual():
    """...and the other half, which is GREEN and stays honestly so. A `bclr` stores `0 & ~bit`, which
    is 0 for every bit, so the ledger holds the address and the width and NOT the channel. On target
    the two are different instructions; off target no surface here separates them. A routine that
    needs the channel held wants a sink of its own or the address in the seeded READ model."""
    diffs, _ = _rmw("g_hw_rmw_clears_the_wrong_bit")
    assert diffs == []


def test_splitting_a_mask_into_two_bit_clears_reds():
    """WHY `hw_and8` IS ITS OWN OPERATION rather than a pair of `hw_bclr8` calls.

    `andi.b #$fc` clears two bits with ONE store, and on target two `bclr`s would leave the same
    register contents — so the temptation to spell it as a pair is real. The ledger compares the
    ordered store STREAM, so the pair diverges it: four entries against three, and a reader sent
    hunting a register bug that is really a spelling one. One instruction, one call, one entry."""
    with pytest.raises(AssertionError, match=MISMATCH):
        _rmw("g_hw_rmw_splits_the_mask_into_two_bit_clears")


@pytest.mark.parametrize("glue,why", (
    ("g_hw_rmw_into_the_image", "an operation aimed at image memory, where the byte diff should see it"),
    ("g_hw_rmw_the_untranslated_form", "the untranslated `$ffff8260` spelling of a real register"),
))
def test_the_operations_refuse_the_addresses_a_store_refuses(glue, why):
    """The new door is the same address check as `hw_write8`'s — it goes through one `hw_log_write`
    — so neither refusal can be reached by writing `hw_bset8` where `hw_write8` was refused."""
    with pytest.raises(AssertionError, match=REFUSED), _named(why):
        _rmw(glue)
