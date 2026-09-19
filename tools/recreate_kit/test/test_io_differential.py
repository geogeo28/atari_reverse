"""Pin the HARNESS PLUMBING of the DECLARED I/O MAP — `harness.differential`'s own code.

`test_io_model.py` next door pins the MODEL: both implementations of it, driven directly from C.
What it cannot reach is the layer between them — `_seed_candidate_io`, `_vet_io_state`,
`_vet_io_reads_are_declared` — because those live in `harness`, which binds a project's compiled
candidate at import, and this directory deliberately binds no project.

`kit_smoke_project.bind()` is what supplies one (see that module for why it is shared): its `.PRG`
holds XBIOS Getrez's own read of `$ff8260` as hand-assembled 68000 code, plus the two-read, word-read
and write-then-read shapes, and its candidate `.so` holds their C counterparts in `kit_candidate.c`.

WHAT IT PINS:

  * the green case: the same read as 68000 code and as C, one declaration handed to both sides;
  * the DECLARED / UNDECLARED pair. Undeclared, the read is the silent 0 it has always been —
    served, counted, and refused only where something is being VERIFIED, which is Phase 7's split
    kept verbatim. The refusal names the address AND the `io_seed=` that answers it;
  * `_vet_io_state` catches two mutants NOTHING ELSE can: two reads in the wrong order, and a byte
    read where the original read a word — every other surface identical in both;
  * `_seed_candidate_io` really seeds the candidate. Stubbed out, the same correct reconstruction
    refuses instead of reading;
  * the one refusal no declaration can fix: a read of a byte the run itself stored to;
  * ONE DOOR, TWO MODELS: a Phase-7 named slot declared through `io_seed` is ROUTED into the named
    set rather than refused, on both shores at once, while the YM2149's block, an address below the
    I/O page and the untranslated `$ffff8260` form are refused by name;
  * the WRITE-THROUGH arm end to end: a declaration marked `emu.write_through` makes a store replace
    what a later read is served, so the .PRG's store-and-verify loop — the MFP timer programmer's
    own shape — runs as an ordinary differential. With the mark stripped by `_seed_candidate_io`
    the same faithful core reds, which is that installer shown load-bearing for the new column.
"""
import pytest

from kit_smoke_project import (ACIA_LINE_BIT, FDC_BUSY_BIT, FDC_STATUS, HW_POLL_UNTIL_IDLE_ENTRY,
                               HW_READ_ENTRY, IO_LATCHED_BYTE, IO_POLL_UNTIL_READY_ENTRY,
                               IO_READ_ENTRY, IO_READ_PAIR_ENTRY,
                               IO_STORE_AND_VERIFY_ENTRY, IO_WORD_READ_ENTRY,
                               IO_WRITE_THEN_READ_ENTRY, MFP_GPIP, PALETTE_0_HI, PALETTE_0_LO,
                               RESOLUTION_MONO, SHIFTER_RESOLUTION, SHIFTER_SYNC,
                               STATIC_TWICE_ENTRY, VIDEO_BASE_HI, VIDEO_BASE_MID, bind)

harness = bind()
emu = harness.emu

# The bytes the cases declare. DELIBERATELY NOT 0: seeded with 0, every green case below would stay
# green if the declaration were never installed at all, since 0 is exactly what an undeclared read
# answers. The model serves a BYTE, not a machine, and what this suite tests is the plumbing that
# carries it — so no case here needs the real ST's values.
DECLARED_RESOLUTION = 0x02            # what Getrez would report: the ST's monochrome mode
DECLARED_PALETTE_HI = 0x07
DECLARED_PALETTE_LO = 0x77
PALETTE_WORD = DECLARED_PALETTE_HI << 8 | DECLARED_PALETTE_LO

RESOLUTION_ONLY = {SHIFTER_RESOLUTION: DECLARED_RESOLUTION}
# ...and a declaration whose two bytes are EQUAL, so that a mutant reading them in the wrong order
# differs from a correct run in nothing but the order.
SAME_BYTE = 0x42
BOTH_THE_SAME = {SHIFTER_RESOLUTION: SAME_BYTE, VIDEO_BASE_HI: SAME_BYTE}
THE_PALETTE = {PALETTE_0_HI: DECLARED_PALETTE_HI, PALETTE_0_LO: DECLARED_PALETTE_LO}

# The 68000's access widths as os.h records them in a ledger entry: a BYTE COUNT.
BYTE, WORD = 1, 2

# ---- the DECLARED SEQUENCE's cases (TRAP_MODEL.md, "Phase 16") ------------------------------------
# What a poll loop needs and a constant cannot give: the first read says BUSY and the second says
# READY, so the loop makes exactly two passes. Declared `[0x00]` it would spin to the instruction
# cap; declared `0x01` as a constant it would exit on the first read and the case would be measuring
# one read where the machine made two.
FDC_BUSY = 0x00
FDC_READY = 1 << FDC_BUSY_BIT
FDC_DRAIN = {FDC_STATUS: [FDC_BUSY, FDC_READY]}
# ...and the same demand at a Phase-7 NAMED SLOT. GPIP bit 4 is ACTIVE LOW — clear means a 6850 is
# still asserting — so an ACIA handler's two-pass entry reads it asserted and then idle. Every other
# bit is set in both bytes, so a core testing the wrong bit does not end where this one does.
GPIP_ACIA_ASSERTED = 0xFF & ~(1 << ACIA_LINE_BIT)
GPIP_ACIA_IDLE = 0xFF
GPIP_TWO_PASS = {MFP_GPIP: [GPIP_ACIA_ASSERTED, GPIP_ACIA_IDLE]}


def _run(glue_name, entry=IO_READ_ENTRY, io_seed=None, **kwargs):
    """Run one of the .PRG's I/O-read routines against a `kit_candidate.c` glue function."""
    return harness.differential(entry, dict(kwargs),
                                lambda lib, buf: getattr(lib, glue_name)(buf), io_seed=io_seed)


def test_a_correct_reconstruction_of_a_declared_io_read_is_green():
    """The whole plumbing, end to end: XBIOS Getrez's own read as 68000 code and as C, one
    declaration handed to both sides, the ordered stream compared and equal.

    The image comparison contributes NOTHING here — neither routine writes an image byte, which is
    the situation this surface exists for — so a green result is entirely the read stream's word.
    """
    diffs, info = _run("g_io_reads_the_resolution", io_seed=RESOLUTION_ONLY)
    assert diffs == []
    assert info["regs"]["io_events"] == [(SHIFTER_RESOLUTION, BYTE, DECLARED_RESOLUTION)], (
        "the oracle did not serve the declared read, so nothing was compared")
    assert info["regs"]["d1"] & 0xFF == DECLARED_RESOLUTION, (
        "the oracle read something other than the declared byte — the declaration is not reaching "
        "the instruction this case is about")


def test_the_same_read_undeclared_refuses_and_names_the_declaration_that_answers_it():
    """THE PAIR THAT IS THE MODEL'S WHOLE POINT, against ONE routine: declared it is served and
    compared; undeclared it is a fabricated 0 both sides agree on, and the case is refused.

    The refusal is ROM mode's (`_vet_rom_io_reads_are_modelled`), so a `.PRG` project like this
    smoke one is NOT refused — it gets the silent 0 it has always had, which is what makes this
    model free for every already-ported game. What the case pins here is therefore the OTHER half:
    the tally the refusal keys on, the first address it would name, and the fact that the read was
    served rather than ledgered.

    `test_boot_snapshot.py` in `projects/tos102us` is where the refusal itself fires, over the same
    address in a real ROM-mode binding.
    """
    diffs, info = _run("g_io_untouched", io_seed=None)
    assert diffs == []
    assert (info["regs"]["io_unmodeled_reads"], info["regs"]["io_unmodeled_first"]) == (
        1, SHIFTER_RESOLUTION), (
        "the undeclared read was not counted, so the ROM-mode refusal has nothing to fire on")
    assert info["regs"]["io_events"] == [], (
        "an UNDECLARED read was ledgered — the candidate refuses its own and logs nothing, so the "
        "two streams would diverge for a reason that is not about this read")

    # ...and the refusal itself, driven through the vet with the run's own report. The smoke project
    # is not a ROM binding, so the mode is forced for the length of this claim.
    with pytest.raises(AssertionError, match=f"{SHIFTER_RESOLUTION:#x}") as raised:
        _vet_as_rom_mode(IO_READ_ENTRY, info["regs"])
    assert "io_seed=" in str(raised.value), (
        "the refusal did not name the declaration that answers it — a refusal a reader cannot act "
        "on is a refusal that gets suppressed")


def _vet_as_rom_mode(entry, o_regs):
    """Run the ROM-mode I/O refusal over a `.PRG` project's run report.

    The vet is a no-op off ROM mode by design (a game's unmodeled I/O reads are nobody's enumerated
    list), and this directory's smoke project is a `.PRG` binding — so the flag is forced for the
    length of one call rather than the suite building a second, ROM-mode project it could not bind
    in the same process.
    """
    was = emu.ROM_MODE
    emu.ROM_MODE = True
    try:
        harness._vet_rom_io_reads_are_modelled(entry, o_regs)
    finally:
        emu.ROM_MODE = was


def test_the_wrong_order_mutant_that_only_the_read_stream_comparison_can_catch(monkeypatch):
    """`_vet_io_state` is load-bearing, and this measures it rather than asserting it.

    `g_io_reads_the_pair_backwards` reads the same two addresses in the other order, and the case
    declares both to the SAME byte — so the values, the map and the (untouched) image are a correct
    run's exactly. With the comparison stubbed out the differential comes back GREEN. Restore it and
    the same run reds. That gap IS the check's value.
    """
    monkeypatch.setattr(harness, "_vet_io_state", lambda entry, o_regs: None)
    diffs, _ = _run("g_io_reads_the_pair_backwards", entry=IO_READ_PAIR_ENTRY,
                    io_seed=BOTH_THE_SAME)
    assert diffs == [], (
        "the mutant changed an image byte, so this case is not measuring the off-image comparison")

    monkeypatch.undo()
    with pytest.raises(AssertionError, match="declared I/O read stream mismatch"):
        _run("g_io_reads_the_pair_backwards", entry=IO_READ_PAIR_ENTRY, io_seed=BOTH_THE_SAME)


def test_a_word_read_is_two_declared_bytes_and_one_ledger_entry():
    """The WIDE shape, which is where this model parts company with Phase 7.

    Phase 7 REFUSES a 16-bit read that takes in a modeled byte, because the neighbouring register
    could not be described at all and would have to be fabricated as 0. Here the neighbour is
    declarable, so a case that declares BOTH bytes of the palette word has said what the word holds
    — and the entry carries the WIDTH, which is what makes the next case's mutant visible.
    """
    diffs, info = _run("g_io_reads_the_palette_word", entry=IO_WORD_READ_ENTRY,
                       io_seed=THE_PALETTE)
    assert diffs == []
    assert info["regs"]["io_events"] == [(PALETTE_0_HI, WORD, PALETTE_WORD)]
    assert info["regs"]["d1"] & 0xFFFF == PALETTE_WORD, (
        "the oracle's word read did not assemble the two declared bytes big-endian")


def test_reading_the_same_word_as_two_bytes_is_a_separable_mutant():
    """...and the mutant that only the entry's WIDTH separates from a correct run.

    `g_io_reads_the_palette_as_two_bytes` reads the identical two declared bytes and would compute
    the identical value from them; on the machine it is a different instruction pair, with a
    different bus profile and a different result on a register the shifter latches a word at a time.
    Two entries of width 1 against the oracle's one of width 2 is the whole of what says so.
    """
    with pytest.raises(AssertionError, match="declared I/O read stream mismatch"):
        _run("g_io_reads_the_palette_as_two_bytes", entry=IO_WORD_READ_ENTRY, io_seed=THE_PALETTE)


def test_a_candidate_that_never_reads_is_caught_too():
    """The other mutant of the same class: a port that hardcodes what it should have read, which is
    what code written against a fabricated 0 looks like once the byte is declared. Its stream is
    empty where the oracle's has an entry, and nothing else about the run differs at all."""
    with pytest.raises(AssertionError, match="declared I/O read stream mismatch"):
        _run("g_io_untouched", io_seed=RESOLUTION_ONLY)


def test_the_candidate_really_gets_the_cases_declaration(monkeypatch):
    """`_seed_candidate_io` is load-bearing: the candidate must run against THIS case's map.

    Two arms, each through the REAL installer captured before the patch — never a hand-rolled copy,
    which would keep passing the day the installer changed (a new reset to make, an encoder
    swapped) and go on "proving" a comparison against plumbing the harness no longer runs:

    * given the WRONG declaration, the candidate serves a different byte for the same address and
      the stream comparison catches it. That is the shape of a candidate holding another case's map;
    * given NO declaration, it refuses through `os_refused()` and `_vet_no_os_refusal` throws the
      case away. That is the shape of a fresh worker, or of an installer that stopped being called.

    An empty map is installed EXPLICITLY rather than the installer being stubbed to a no-op: the
    candidate's map survives between cases, so a no-op would leave whichever declaration the
    previous case installed and the result would depend on collection order.
    """
    seed_candidate_io = harness._seed_candidate_io
    monkeypatch.setattr(harness, "_seed_candidate_io",
                        lambda io_seed: seed_candidate_io({SHIFTER_RESOLUTION: SAME_BYTE}))
    with pytest.raises(AssertionError, match="declared I/O read stream mismatch"):
        _run("g_io_reads_the_resolution", io_seed=RESOLUTION_ONLY)

    monkeypatch.setattr(harness, "_seed_candidate_io", lambda io_seed: seed_candidate_io({}))
    with pytest.raises(AssertionError, match="REFUSES to serve"):
        _run("g_io_reads_the_resolution", io_seed=RESOLUTION_ONLY)


def test_a_read_of_a_byte_the_run_itself_wrote_is_refused_and_not_declarable():
    """Phase 15's one refusal, and it is Phase 7's staleness rule at an address-keyed model.

    The `.PRG` routine stores `$02` into `$ff8260` and then reads it back. The model drops hardware
    writes, so the read is served the byte the case declared the machine held ON ENTRY while an
    instruction of this very run has replaced it — and no bigger declaration can fix that, which is
    why the message prescribes a different CASE rather than a different seed.

    Declared, deliberately: the point is that a case CAN declare this byte and still be wrong.
    """
    with pytest.raises(AssertionError, match="already STORED to") as raised:
        _run("g_io_writes_then_reads", entry=IO_WRITE_THEN_READ_ENTRY, io_seed=RESOLUTION_ONLY)
    message = str(raised.value)
    assert f"{SHIFTER_RESOLUTION:#x}" in message, "the refusal did not name the address"
    assert "io_seed={0xff8260: 0x02}" in message, (
        "the refusal did not render the case's declaration as a reader would type it — Python's "
        "decimal dict cannot be matched against the address in the disassembly")


# ---- the WRITE-THROUGH arm ----------------------------------------------------------------------
#
# What the .PRG stores into the register the loop verifies, and the byte the case declares it held
# BEFORE that — deliberately different, so "served what the run wrote" and "served what the case
# declared" are two visible answers rather than one.
LATCHING_REGISTER_ENTRY = 0x11
WRITE_THROUGH_LOOP = {VIDEO_BASE_MID: emu.write_through(LATCHING_REGISTER_ENTRY)}
# ...and the same for the single store-then-read routine, which is the shape without the loop. Its
# declared ENTRY byte is again not the byte the routine stores (`RESOLUTION_MONO`), so "served what
# the run wrote" and "served what the case declared" are two visible answers here too.
WRITE_THROUGH_RESOLUTION = {SHIFTER_RESOLUTION: emu.write_through(LATCHING_REGISTER_ENTRY)}


def test_a_store_and_verify_loop_runs_as_an_ordinary_differential_when_the_byte_latches():
    """THE ARM'S WHOLE POINT, over the shape that demanded it: the MFP timer programmer's
    `move.b` / `cmp.b` / `bne` — store the byte, read the register back, go round again until the
    chip agrees (`projects/tos102us`, `$fc260e`).

    It terminates only because the register LATCHED what was stored: declared as a per-run constant
    the compare could never come true, and the oracle would die at the instruction cap. ONE entry in
    the read stream is the other half of the claim — the loop ran once — so a reconstruction whose
    loop reads a different number of times is separated by the stream rather than by luck.
    """
    diffs, info = _run("g_io_stores_and_verifies", entry=IO_STORE_AND_VERIFY_ENTRY,
                       io_seed=WRITE_THROUGH_LOOP)
    assert diffs == []
    assert info["regs"]["io_events"] == [(VIDEO_BASE_MID, BYTE, IO_LATCHED_BYTE)], (
        "the verify was not served what the loop had just stored, so the loop that terminated was "
        "not the one this case is about")
    assert info["regs"]["io_stale_reads"] == 0, (
        "a write-through read back was counted as STALE — the arm marks the declaration rather than "
        "invalidating it, and `_vet_io_reads_are_declared` would refuse every case that used it")
    assert [(address, value) for address, _width, value in info["regs"]["hw_writes"]] == \
        [(VIDEO_BASE_MID, IO_LATCHED_BYTE)], "the store did not reach the Phase 10 ledger unchanged"


def test_the_same_loop_declared_as_a_constant_never_terminates():
    """...and its control, which is what says the arm and not the declaration is doing the work.

    Without the mark the same map serves the entry byte on every read, the `bne` is always taken,
    and the ORACLE runs to the instruction cap — the state this whole arm was built to leave.
    """
    with pytest.raises(RuntimeError, match="did not reach rts"):
        emu.run(harness.make_image(), IO_STORE_AND_VERIFY_ENTRY, {},
                io_seed={VIDEO_BASE_MID: LATCHING_REGISTER_ENTRY}, max_insns=20_000)


@pytest.mark.parametrize("mutant", ("g_io_stores_without_verifying", "g_io_verifies_before_it_stores",
                                    "g_io_stores_another_value"))
def test_the_three_ways_a_port_of_that_loop_goes_wrong_are_each_caught(mutant):
    """The negative controls, each touching no image byte at all.

    `g_io_stores_without_verifying` skips the read back and assumes the answer, which is what a port
    written before this arm existed looks like: its read stream is EMPTY where the oracle's carries
    the verify. `g_io_verifies_before_it_stores` makes the same two accesses in the other ORDER, so
    it is served the byte the case declared the machine held on entry rather than the byte it wrote.
    And `g_io_stores_another_value` stores the wrong byte, which the register then latches — one
    wrong store moving the write ledger's value and the read ledger's together.
    """
    with pytest.raises(AssertionError, match="stream mismatch"):
        _run(mutant, entry=IO_STORE_AND_VERIFY_ENTRY, io_seed=WRITE_THROUGH_LOOP)



def test_the_write_through_mark_really_reaches_the_candidate(monkeypatch):
    """`_seed_candidate_io` carries the new COLUMN, and this measures it rather than asserting it.

    The patch strips every mark out of the declaration and installs the rest through the REAL
    installer — never a hand-rolled copy, for `test_the_candidate_really_gets_the_cases_declaration`'s
    reason — so the candidate holds the same addresses and the same bytes and only the write-through
    column differs. The faithful core then reads back the byte the case DECLARED where the oracle
    reads back the byte the run STORED, which is the mutant class the arm exists to make impossible.

    The single store-then-read routine rather than the loop, deliberately: a candidate loop under an
    unmarked declaration would spin forever rather than red.
    """
    declared_marks = sum(isinstance(value, emu.write_through)
                         for value in WRITE_THROUGH_RESOLUTION.values())
    seed_candidate_io = harness._seed_candidate_io
    monkeypatch.setattr(harness, "_seed_candidate_io", lambda io_seed: seed_candidate_io(
        {addr: emu.io_seed_byte(value) for addr, value in (io_seed or {}).items()}))
    with pytest.raises(AssertionError, match="declared I/O read stream mismatch"):
        _run("g_io_writes_then_reads", entry=IO_WRITE_THEN_READ_ENTRY,
             io_seed=WRITE_THROUGH_RESOLUTION)
    # ...and the candidate's OWN account of the column it was handed agrees that it got none. The
    # ledger mismatch above is the behavioural half; this is the structural one, and it is what says
    # the .so is the post-column build rather than a stale one whose `g_io_reset` never took a
    # writeback argument at all (harness._HW_LEDGER_ABI).
    assert harness._lib.g_io_writeback_count() == 0

    monkeypatch.undo()
    diffs, info = _run("g_io_writes_then_reads", entry=IO_WRITE_THEN_READ_ENTRY,
                       io_seed=WRITE_THROUGH_RESOLUTION)
    assert diffs == []
    assert info["regs"]["io_events"] == [(SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)], (
        "the read back was not served the byte the routine stored")
    assert harness._lib.g_io_writeback_count() == declared_marks
    assert info["regs"]["io_declared"] == len(WRITE_THROUGH_RESOLUTION), (
        "the oracle installed a different number of bytes than the case declared, so the marked "
        "count above is being compared against the wrong map")


def test_an_unmarked_declaration_keeps_the_staleness_refusal_verbatim():
    """The arm is OPT-IN PER ADDRESS, which is what makes it cost every already-ported project
    nothing: the very same routine and the very same byte, declared without the mark, is still the
    refusal `test_a_read_of_a_byte_the_run_itself_wrote_is_refused_and_not_declarable` measures —
    and the message renders the mark that would answer it."""
    with pytest.raises(AssertionError, match="already STORED to") as raised:
        _run("g_io_writes_then_reads", entry=IO_WRITE_THEN_READ_ENTRY, io_seed=RESOLUTION_ONLY)
    assert "write_through" in str(raised.value), (
        "the refusal did not name the declaration that answers it, which is now a mark rather than "
        "a different case shape")


def test_the_staleness_refusal_over_a_sequenced_address_renders_the_list_and_prescribes_a_remedy():
    """The same store-then-read routine with the address declared as a LIST rather than a byte.

    The refusal QUOTES THE CASE'S OWN DECLARATION back at it, so the formatter has to render every
    shape a declaration can take: a list formatted as one byte is a `TypeError` inside the vet, and
    what the reader gets is a traceback about `list.__format__` where the diagnosis should be.

    The REMEDY has to be right for a list too. `write_through` is the answer for a constant and is
    not on offer here — a list and a mark are two contradictory claims about what the read after a
    store answers, refused at the door — and neither is a longer list, since the refusal is about the
    store rather than about how many reads were described. So the message must send the reader to the
    case's shape, and prescribing the mark would send them to write a declaration `emu` rejects.
    """
    sequenced = {SHIFTER_RESOLUTION: [DECLARED_RESOLUTION, SAME_BYTE]}
    with pytest.raises(AssertionError, match="already STORED to") as raised:
        _run("g_io_writes_then_reads", entry=IO_WRITE_THEN_READ_ENTRY, io_seed=sequenced)
    message = str(raised.value)
    assert f"[{DECLARED_RESOLUTION:#04x}, {SAME_BYTE:#04x}]" in message, (
        "the refusal did not render the list the case declared, so it cannot be the declaration a "
        "reader is being asked to change")
    assert f"io_seed={{{SHIFTER_RESOLUTION:#x}: write_through(" not in message, (
        "the refusal PRESCRIBED a mark for a SEQUENCED address, which `emu.io_seed_entries` refuses "
        "— the reader would be sent to write a declaration that cannot be installed")
    assert "refused at the door" in message, (
        "the refusal does not say why the mark a reader would reach for next is not on offer here")
    assert "run it up to the write" in message, "the refusal names no remedy at all"


def test_a_write_through_claim_on_a_phase_7_named_slot_is_refused_by_name():
    """The one address class the mark may not be made on, and the refusal names the model that owns
    it. `emu.seed_split` routes a named slot into Phase 7's installer, which has no write-through
    arm at all — so carrying the claim across would drop it silently and serve the case a byte its
    own source says the run had replaced."""
    with pytest.raises(ValueError, match="NAMED SLOT") as raised:
        harness.differential(HW_READ_ENTRY, {}, lambda lib, buf: lib.g_hw_reads_the_pair(buf),
                             io_seed={MFP_GPIP: emu.write_through(GPIP_BYTE),
                                      SHIFTER_SYNC: SYNC_BYTE})
    assert "write_through" in str(raised.value) and "hw_seed" in str(raised.value)


def test_the_same_store_with_nothing_read_back_is_an_ordinary_run():
    """...and its control, which is what says the refusal is about the READ and not about the store.

    Undeclared, the same routine's store is the ordinary invisible hardware write it has always
    been — ledgered by Phase 10, no business of this model's — and the read that follows is the
    silent 0, counted rather than stale. A staleness rule that fired on the write alone would refuse
    every case that configures a register before doing anything.
    """
    diffs, info = _run("g_io_writes_the_resolution", entry=IO_WRITE_THEN_READ_ENTRY)
    assert diffs == []
    assert info["regs"]["io_stale_reads"] == 0, (
        "a store to an address NOTHING declared was recorded as stale, so the rule fires on the "
        "write rather than on a declaration the write invalidated")
    assert info["regs"]["hw_writes"], "the store did not reach the Phase 10 ledger"


# What the routing case declares the two named slots the smoke .PRG's hardware-read routine reads.
GPIP_BYTE, SYNC_BYTE = 0xB0, 0x02


def test_a_named_slot_declared_through_io_seed_is_routed_into_the_named_set():
    """ONE DOOR, TWO MODELS — the whole of what the case author has to know.

    A reader of a disassembly sees `$fffa01` and `$ff8260` as the same kind of thing: a byte the
    machine held on entry. Which of them Phase 7 happens to NAME is the kit's bookkeeping, so
    `io_seed` takes both and `emu.seed_split` hands the named one to Phase 7's own installer before
    either side is seeded. The models stay two — separate rules, separate ledgers — and this is the
    end-to-end proof that BOTH shores route: the reads land in the NAMED set's stream (which the
    candidate's `hw_read8` fills) and this model's stays empty, which can only happen if the oracle
    and the candidate agreed about who owns the address.
    """
    diffs, info = harness.differential(
        HW_READ_ENTRY, {}, lambda lib, buf: lib.g_hw_reads_the_pair(buf),
        io_seed={MFP_GPIP: GPIP_BYTE, SHIFTER_SYNC: SYNC_BYTE})
    assert diffs == []
    assert info["regs"]["hw_events"] == [(MFP_GPIP, GPIP_BYTE), (SHIFTER_SYNC, SYNC_BYTE)], (
        "the declaration did not reach the Phase-7 model, so nothing routed")
    assert info["regs"]["io_events"] == [], (
        "a named slot was served by the declared I/O map as well — one byte would be ledgered by "
        "one model while the other's rules went unenforced")


def test_declaring_one_address_through_both_doors_is_refused():
    """...and the one shape routing makes possible that the two separate doors could not.

    Two declarations of one byte are two claims about one machine, and which of them won would be
    `seed_split`'s iteration order rather than the case's meaning.
    """
    with pytest.raises(ValueError, match="declared by BOTH"):
        harness.differential(HW_READ_ENTRY, {}, lambda lib, buf: lib.g_hw_reads_the_pair(buf),
                             hw_seed={MFP_GPIP: GPIP_BYTE}, io_seed={MFP_GPIP: SYNC_BYTE})


def test_declaring_one_address_as_a_list_and_a_hw_seed_byte_is_refused_by_the_same_rule():
    """...and a LIST is the same two claims, refused the same way rather than quietly winning.

    A sequenced address leaves `io_seed` for the THIRD table, so `hw_seed`'s byte would stay
    installed beside it: the case would hold two live declarations of one byte, and which one a read
    was served by would be which model reached it first. The refusal has to be made where the
    routing is, because after it the two are in different tables and nothing can see both.
    """
    with pytest.raises(ValueError, match="declared by BOTH"):
        harness.differential(HW_READ_ENTRY, {}, lambda lib, buf: lib.g_hw_reads_the_pair(buf),
                             hw_seed={MFP_GPIP: GPIP_BYTE},
                             io_seed={MFP_GPIP: [GPIP_ACIA_ASSERTED, GPIP_ACIA_IDLE]})


def test_the_addresses_no_routing_can_reach_are_refused_by_name():
    """The exclusions that survive the one door, each named with the remedy.

    The YM2149's block is not routable at all, and the reason is the chip's: Phase 6's file is keyed
    by REGISTER NUMBER and a read of `$ff8800` answers whatever the run last latched, so an
    address-keyed byte could not say which register it declared. Below the I/O page is ordinary
    off-image memory. And the UNTRANSLATED `$ffff8260` form is an address the machine's 24-bit bus
    never carries, so a map keyed on it holds an entry no read can match — the message names the
    form the decode really produces, and says which model owns it when that one is not this.
    """
    with pytest.raises(ValueError, match="psg_seed"):
        _run("g_io_untouched", io_seed={emu.os_map.OS_PSG_PORT_SELECT: 0x07})
    with pytest.raises(ValueError, match="below the I/O page"):
        _run("g_io_untouched", io_seed={IO_READ_ENTRY: 0x01})
    with pytest.raises(ValueError, match=f"{SHIFTER_RESOLUTION:#x}"):
        _run("g_io_untouched", io_seed={0xFFFF8260: DECLARED_RESOLUTION})
    with pytest.raises(ValueError, match="NAMED SLOT") as raised:
        _run("g_io_untouched", io_seed={0xFFFFFA01: GPIP_BYTE})
    assert f"{MFP_GPIP:#x}" in str(raised.value), (
        "the refusal did not name the register the untranslated form really addresses, which is the "
        "one thing a reader has to change it to")


def test_marking_an_excluded_address_write_through_is_refused_by_the_same_rule():
    """...and the mark changes NONE of the other exclusions, which is the half a new keyword could
    have got wrong: the address is judged before the value is, so a YM2149 port, an address below
    the page and the untranslated form are refused by the same messages whether the declaration is a
    plain byte or a `write_through` one. A mark is a qualifier on a declaration this model accepted,
    never a way to make one it did not."""
    with pytest.raises(ValueError, match="psg_seed"):
        _run("g_io_untouched", io_seed={emu.os_map.OS_PSG_PORT_SELECT: emu.write_through(0x07)})
    with pytest.raises(ValueError, match="below the I/O page"):
        _run("g_io_untouched", io_seed={IO_READ_ENTRY: emu.write_through(0x01)})
    with pytest.raises(ValueError, match=f"{SHIFTER_RESOLUTION:#x}"):
        _run("g_io_untouched", io_seed={0xFFFF8260: emu.write_through(DECLARED_RESOLUTION)})


@pytest.mark.parametrize("value", (2.5, "x", None, 0x100, -1))
def test_a_value_that_is_not_a_byte_is_refused_as_the_docstring_promises(value):
    """`io_seed_entries` promises a ValueError for every rejection, and a value is a rejection too.

    `0 <= value <= 0xFF` alone does not deliver that: a float passes it silently (2.5 would be
    handed to a `c_uint8` and truncated to 2, so the run would be served a byte the case never
    wrote), and a string raises `TypeError` from the comparison instead — an error whose message
    names neither the address nor the model.
    """
    with pytest.raises(ValueError, match="is not a byte"):
        _run("g_io_untouched", io_seed={SHIFTER_RESOLUTION: value})
    # ...and the same inside a `write_through` wrapper, whose byte goes through the identical rule:
    # the mark qualifies a declaration, it does not exempt one.
    with pytest.raises(ValueError, match="is not a byte"):
        _run("g_io_untouched", io_seed={SHIFTER_RESOLUTION: emu.write_through(value)})


def test_a_declaration_mutated_after_it_was_encoded_is_re_encoded():
    """`io_seed_entries` memoises its last encoding, and this is the guard that keeps that honest.

    The memo is keyed on the dict's IDENTITY *and* its CONTENTS, because a case is free to fill or
    edit a dict it has already passed — a builder that starts from `{}` and adds registers is the
    obvious shape. Keyed on identity alone, the second run would be served the first run's map: both
    shores would read the silent 0 for the newly declared byte, agree on it, and the case would go
    green against a byte the model invented, with its own source saying the byte was declared.
    """
    declaration = {}
    assert emu.io_seed_entries(declaration) == ((), (), ())
    declaration[SHIFTER_RESOLUTION] = DECLARED_RESOLUTION
    assert emu.io_seed_entries(declaration) == ((SHIFTER_RESOLUTION,), (DECLARED_RESOLUTION,),
                                                (emu.os_map.OS_IO_DECLARED_CONSTANT,)), (
        "the memo served the empty encoding for a dict that has since been filled")
    # ...and the WRITE-THROUGH column is part of what the memo has to notice: marking an address a
    # case has already declared changes no key and no byte, so a memo comparing either alone would
    # serve the unmarked encoding and the candidate would refuse the read back it is now entitled to.
    declaration[SHIFTER_RESOLUTION] = emu.write_through(DECLARED_RESOLUTION)
    assert emu.io_seed_entries(declaration) == ((SHIFTER_RESOLUTION,), (DECLARED_RESOLUTION,),
                                                (emu.os_map.OS_IO_WRITE_THROUGH,)), (
        "the memo served the UNMARKED encoding for a declaration that has since been marked")
    declaration[SHIFTER_RESOLUTION] = DECLARED_RESOLUTION
    diffs, info = _run("g_io_reads_the_resolution", io_seed=declaration)
    assert diffs == []
    assert info["regs"]["io_events"] == [(SHIFTER_RESOLUTION, BYTE, DECLARED_RESOLUTION)]


def test_a_declaration_the_run_never_reads_is_left_alone():
    """Declaring more than the run uses is ORDINARY, not an error: a case describes the machine it
    means, and which bytes a particular routine happens to touch is not the case's business. Only
    the reads that HAPPENED are ledgered, so the extra declaration leaves no trace at all."""
    diffs, info = _run("g_io_reads_the_resolution", io_seed={**RESOLUTION_ONLY, **THE_PALETTE})
    assert diffs == []
    assert info["regs"]["io_events"] == [(SHIFTER_RESOLUTION, BYTE, DECLARED_RESOLUTION)]
    assert info["regs"]["io_declared"] == 3, "the oracle did not install the whole declaration"


def test_a_case_that_declares_nothing_is_untouched_by_the_model():
    """The zero-regression property every already-ported project rests on, as a case.

    A run that declares no I/O byte serves none, so both ledgers are empty and compare equal — which
    is why adding this model changed no project's suite. `test_the_pair` above shows the counted
    read is still there; this one shows the comparison it feeds costs nothing.
    """
    diffs, info = _run("g_io_untouched", entry=IO_READ_PAIR_ENTRY)
    assert diffs == []
    assert (info["regs"]["io_events"], info["regs"]["io_declared"]) == ([], 0)
    assert info["regs"]["io_unmodeled_reads"] == 2, (
        "the two undeclared reads were not counted, so this case is not running the routine it names")


# ---- the DECLARED SEQUENCE, end to end (TRAP_MODEL.md, "Phase 16") --------------------------------

def test_a_poll_loop_runs_against_a_declared_sequence_and_is_green():
    """THE SHAPE NEITHER CONSTANT MODEL CAN DESCRIBE, as a whole differential.

    The `.PRG` reads the FDC's status register until its busy bit clears and the C core does the
    same. Under a per-run constant the run is not merely unfaithful, it is unrunnable: `0x00` spins
    to the instruction cap and `0x01` exits on the first read. The list is what makes both sides make
    the SAME TWO reads, and the ordered stream is what compares them — the routine writes no image
    byte, so a green result here is entirely that stream's word.
    """
    diffs, info = _run("g_io_polls_until_ready", entry=IO_POLL_UNTIL_READY_ENTRY,
                       io_seed=FDC_DRAIN)
    assert diffs == []
    assert info["regs"]["io_events"] == [(FDC_STATUS, BYTE, FDC_BUSY),
                                         (FDC_STATUS, BYTE, FDC_READY)], (
        "the oracle did not drain the list, so the loop ended for some other reason and nothing "
        "this case is about was compared")
    assert info["regs"]["io_seq_spent"] == 0


def test_the_same_loop_undeclared_never_terminates():
    """The pair that says the LIST is load-bearing, and it is driven rather than described.

    With no declaration the status byte is the fabricated 0 this whole family of models exists to
    close — and 0 is "still busy", so the loop runs to the oracle's instruction cap. That is the
    honest failure: loud, on the ORACLE, before any comparison. (The candidate would spin too, which
    is why `kit_candidate.c`'s loop carries a bound of its own.)
    """
    with pytest.raises(Exception) as raised:
        harness.differential(IO_POLL_UNTIL_READY_ENTRY, {},
                             lambda lib, buf: lib.g_io_polls_once(buf), max_insns=2000)
    assert "rts" in str(raised.value) or "cap" in str(raised.value).lower(), (
        f"the run ended for a reason other than the instruction cap: {raised.value}")


def test_a_constant_declaration_cannot_express_the_same_loop():
    """...and neither can the model one door along, which is the argument for a THIRD shape.

    The same routine, the same door, a byte instead of a list: `0x01` ends the loop on its FIRST
    read, so the case would be measuring one read where the machine makes two — a green run down a
    path the machine never took. The row is what says a list is not a convenience over a constant.
    """
    diffs, info = _run("g_io_polls_until_ready", entry=IO_POLL_UNTIL_READY_ENTRY,
                       io_seed={FDC_STATUS: FDC_READY})
    assert diffs == []
    assert info["regs"]["io_events"] == [(FDC_STATUS, BYTE, FDC_READY)], (
        "a constant declaration no longer ends the loop on its first read, so this case is not the "
        "control it claims to be")


def test_a_core_that_reads_once_where_the_original_drained_twice_is_caught():
    """NEGATIVE CONTROL 1: the port that services one byte and drops the loop.

    It is the surviving mutant `projects/zynaps/recreate/STATUS.md` records for its own ACIA handler,
    and it touches no image byte — so the ordered read stream is the only surface that separates it
    from a correct run.
    """
    with pytest.raises(AssertionError) as raised:
        _run("g_io_polls_once", entry=IO_POLL_UNTIL_READY_ENTRY, io_seed=FDC_DRAIN)
    assert "read stream mismatch" in str(raised.value)


def test_a_core_that_reads_one_time_too_many_is_refused_on_its_own_shore():
    """NEGATIVE CONTROL 2a: the drain that runs off the end of the case's own list, on the CANDIDATE.

    The oracle's loop ends at the list's second byte, so only the reconstruction reads a third time —
    and that read is refused rather than served the last byte again. What throws the case away is
    therefore the candidate's own `os_refused()` tally, which is the half of "refusing on ONE side is
    a false green" this shore owns. A sticky last byte here would have made the mutant identical to a
    correct run on every surface a differential has.
    """
    with pytest.raises(AssertionError) as raised:
        _run("g_io_polls_one_time_too_many", entry=IO_POLL_UNTIL_READY_ENTRY, io_seed=FDC_DRAIN)
    message = str(raised.value)
    assert "REFUSES" in message, message
    assert "PAST THE END" in message, (
        "the refusal did not name the SEQUENCE as a cause, so the reader is sent to hunt for a "
        "missing Bconstat gate instead")
    # ...and it names WHICH read of WHICH address ran off the end, from the candidate's own spent
    # counters — the oracle's run stayed inside the list, so nothing else in this refusal can. It is
    # the difference between a cause offered to every case that declares a list and a fact about
    # this one: "the list is short" and "the loop reads it more times than you thought" are
    # different repairs, and only the index tells them apart.
    assert f"read {len(FDC_DRAIN[FDC_STATUS])} of {FDC_STATUS:#x}" in message, message


def test_an_oracle_that_reads_past_the_end_names_the_address_and_the_read():
    """NEGATIVE CONTROL 2b: the same over-read on the ORACLE, which is where the tally lives.

    The `.PRG` reads `$fffa01` twice and the case declares a list of ONE byte, so the second read is
    past the end on both shores. The oracle's refusal is the one with the diagnosis: it names the
    address AND the READ INDEX, because "the list is short" and "this routine reads the register more
    times than the case expected" are different repairs and only the count tells them apart.
    """
    with pytest.raises(AssertionError) as raised:
        _run("g_hw_reads_the_gpip_twice", entry=STATIC_TWICE_ENTRY,
             io_seed={MFP_GPIP: [GPIP_ACIA_IDLE]})
    message = str(raised.value)
    assert f"{MFP_GPIP:#x}" in message and "past the" in message.lower(), message
    assert "read 1" in message, "the refusal does not say WHICH read ran off the end"
    assert "io_seed=" in message, "the refusal does not prescribe the longer list that answers it"


def test_two_sequenced_addresses_read_in_the_wrong_order_are_caught():
    """NEGATIVE CONTROL 3: two lists consumed in the wrong order.

    Each address still yields ITS OWN first byte whichever is read first, so the values the two cores
    compute are identical and neither touches the image. Only the ordered stream separates them —
    which is the same argument the constant map makes, now over state that ADVANCES, where reading
    the wrong one first also leaves every later read of both addresses out of step.
    """
    pair = {SHIFTER_RESOLUTION: [SAME_BYTE, SAME_BYTE], VIDEO_BASE_HI: [SAME_BYTE, SAME_BYTE]}
    diffs, _info = _run("g_io_reads_the_pair", entry=IO_READ_PAIR_ENTRY, io_seed=pair)
    assert diffs == [], "the faithful core no longer matches, so the mutant below proves nothing"
    with pytest.raises(AssertionError) as raised:
        _run("g_io_reads_the_pair_backwards", entry=IO_READ_PAIR_ENTRY, io_seed=pair)
    assert "read stream mismatch" in str(raised.value)


def test_a_sequence_on_a_named_slot_is_routed_and_lands_in_the_named_set_s_ledger():
    """ONE DOOR, TWO MODELS, over a LIST: the case writes `io_seed` and the reads come back in
    Phase 7's OWN stream.

    The `.PRG` asks the MFP's GPIP until the ACIA line goes idle — TOS 1.02's ACIA handler's own
    question — and the C core reads it through `hw_read8`, which is the NAMED set's door. The case
    declares the list through `io_seed` all the same, because which addresses Phase 7 happens to name
    is the kit's bookkeeping rather than the case's.

    The claim is the SPLIT: the reads land in `hw_events` and this model's `io_events` stays empty,
    which only happens if BOTH shores routed the list to the same model. Were only one to route, the
    oracle would serve a byte the candidate refused and the mismatch would read as a reconstruction
    bug.
    """
    diffs, info = _run("g_hw_polls_until_idle", entry=HW_POLL_UNTIL_IDLE_ENTRY,
                       io_seed=GPIP_TWO_PASS)
    assert diffs == []
    assert info["regs"]["hw_events"] == [(MFP_GPIP, GPIP_ACIA_ASSERTED), (MFP_GPIP, GPIP_ACIA_IDLE)]
    assert info["regs"]["io_events"] == [], (
        "a named slot's sequenced reads landed in the declared map's ledger — the two models are "
        "serving one byte, and only one of them is enforcing its rules on it")
    assert info["regs"]["io_seq_declared"] == 1, (
        "the list was not installed at all, so the loop ended for some other reason")


def test_a_named_slot_s_sequence_replaces_the_volatile_re_read_refusal():
    """...and the refusal it MOVES, as the pair that says so.

    `$fffa01` is STATIC, so its two reads are legal with or without a list — what a list changes is
    that they can DIFFER. The volatile slot next door is where the bound really moves, and the
    control here is the same routine under a CONSTANT: the loop never ends, which is what the whole
    model is for.
    """
    with pytest.raises(Exception) as raised:
        harness.differential(HW_POLL_UNTIL_IDLE_ENTRY, {},
                             lambda lib, buf: lib.g_hw_polls_once(buf), max_insns=2000,
                             io_seed={MFP_GPIP: GPIP_ACIA_ASSERTED})
    assert "rts" in str(raised.value) or "cap" in str(raised.value).lower(), (
        f"a constant declaring the line ASSERTED no longer spins: {raised.value}")


def test_seed_candidate_seq_is_load_bearing(monkeypatch):
    """`_seed_candidate_seq` stubbed out, and the same FAITHFUL core reds.

    With the installer gone the candidate's table is whatever the previous case left — here nothing —
    so its first read is refused where the oracle serves the list's first byte. The point is not the
    particular failure but that there IS one: a declaration that reached only the oracle would have
    the candidate reading a machine the case never described.
    """
    monkeypatch.setattr(harness, "_seed_candidate_seq", lambda io_seq: None)
    with pytest.raises(AssertionError) as raised:
        _run("g_io_polls_until_ready", entry=IO_POLL_UNTIL_READY_ENTRY, io_seed=FDC_DRAIN)
    assert "refus" in str(raised.value).lower() or "read stream mismatch" in str(raised.value)


def test_the_sequence_vet_is_load_bearing(monkeypatch):
    """`_vet_io_sequences_are_servable` stubbed out, over the case ONLY THE ORACLE over-reads.

    The `.PRG` reads `$fffa01` twice against a list of one byte, so the oracle runs off the end; the
    candidate here reads it ONCE, so it charges no refusal of its own and has nothing to say. With
    the vet gone the case is still thrown away — the two streams differ by the refused read — but
    the DIAGNOSIS goes: nothing names the address, the read index or the list that answers it, and a
    reader is sent to compare two streams instead. That is what the vet contributes, and it is the
    half of the refusal the ORACLE owns.

    A candidate that over-reads TOO would be no measurement of this: its own spent counters report
    the same address and read index through `_seq_refusal_hint`, so the diagnosis survives the stub
    for a reason that is not the vet.
    """
    short = {MFP_GPIP: [GPIP_ACIA_IDLE]}
    monkeypatch.setattr(harness, "_vet_io_sequences_are_servable",
                        lambda entry, io_seed, o_regs: None)
    with pytest.raises(AssertionError) as raised:
        _run("g_hw_polls_once", entry=STATIC_TWICE_ENTRY, io_seed=short)
    assert "read 1" not in str(raised.value), (
        "the vet is not what reported the read past the end, so removing it changed nothing and it "
        "is pinning nothing")


def test_declaring_one_address_as_both_a_list_and_a_write_through_byte_is_refused():
    """The one inconsistent declaration the door can express, refused where the routing is.

    A list says "the next byte I named" and a `write_through` mark says "whatever the run stored";
    both describe what the read after a store answers, and which won would be an iteration order
    rather than the case's meaning.
    """
    with pytest.raises(ValueError) as raised:
        _run("g_io_polls_until_ready", entry=IO_POLL_UNTIL_READY_ENTRY,
             io_seed={FDC_STATUS: emu.write_through([FDC_BUSY, FDC_READY])})
    assert "write_through" in str(raised.value) and "SEQUENCE" in str(raised.value)


@pytest.mark.parametrize("declaration, wanted", (
    ({FDC_STATUS: []}, "EMPTY"),
    ({FDC_STATUS: [FDC_BUSY, 0x100]}, "not a byte"),
    ({FDC_STATUS: [FDC_BUSY, "ready"]}, "not a byte"),
    ({0xFFFF8604: [FDC_BUSY]}, "BUS FORM"),
    ({0x1000: [FDC_BUSY]}, "below the I/O page"),
    ({0xFF8802: [FDC_BUSY]}, "YM2149"),
))
def test_a_list_the_model_cannot_serve_is_a_ValueError_rather_than_a_dropped_row(declaration,
                                                                                wanted):
    """Every rejection is refused by NAME, for the constant map's reason: a case that declared a list
    this model may not serve would otherwise read the model BELOW it while its own source says a
    sequence was declared — which is the false green, with the declaration standing behind it."""
    with pytest.raises(ValueError) as raised:
        emu.io_seq_entries({addr: bytes_ for addr, bytes_ in declaration.items()})
    assert wanted in str(raised.value)


def test_a_case_that_declares_no_list_leaves_the_table_empty():
    """The zero-regression property, as a case: a run that declares no sequence installs none, so
    neither read path is diverted and every already-ported project's suite is unchanged."""
    diffs, info = _run("g_io_reads_the_resolution", io_seed=RESOLUTION_ONLY)
    assert diffs == []
    assert (info["regs"]["io_seq_declared"], info["regs"]["io_seq_spent"]) == (0, 0)
