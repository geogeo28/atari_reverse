"""Pin the HARNESS PLUMBING of the seeded hardware read model — `harness.differential`'s own code.

`test_hw_model.py` next door pins the MODEL: both implementations of it, driven directly from C.
What it cannot reach is the layer between them — `_seed_candidate_hw`, `_vet_hw_state`,
`_vet_hw_reads_are_declared` — because those live in `harness`, which binds a project's compiled
candidate at import, and this directory deliberately binds no project.

`kit_smoke_project.bind()` is what supplies one (see that module for why it is shared): its `.PRG`
holds Wonder Boy's tempo-selector reads as hand-assembled 68000 code, and its candidate `.so` holds
their C counterparts in `kit_candidate.c`.

WHAT IT PINS, and the one thing to keep in view while reading it: **PHASE 7'S REFUSAL LIVES HERE,
NOT IN `emu.run`**. Phase 6's model refuses an undeclared PSG read for every caller; this one serves
the fabricated 0 to a bare `emu.run` — which is how the workspace drives relocators, Copylock and
bootstrap code — and refuses only where something is being VERIFIED. Both halves of that split are
cases below, because a "fix" in either direction is the kind that looks like tidying.

  * the green case: the same two reads as 68000 code and as C, one declaration handed to both sides;
  * an undeclared read REFUSES the differential and names the `hw_seed=` to add — while the same run
    through `emu.run` is served and does not raise;
  * `_vet_hw_state` catches a mutant NOTHING ELSE can: two reads in the wrong order, every other
    surface identical;
  * `_seed_candidate_hw` really seeds the candidate. Stubbed out, the same correct reconstruction
    reads an address it was never given and is refused;
  * a candidate missing the hardware ABI is refused by NAME while the oracle reads the addresses;
  * the three refusals that no declaration can fix: a read after the run's own write, a wide read,
    and a SECOND read of a VOLATILE address — beside its control, the same shape on a STATIC address,
    which is served;
  * the audio-capture veto still stands over a differential, and `emu.run` refuses a `hw_seed` under
    the mode — the two guards around the capture fold.
"""
import pytest

# The one the .PRG does NOT plant, spelled once here so the table pin below is an EQUALITY and not
# a prefix: the counter's MID byte has no routine, since one volatile address is enough to measure
# the flag and Wonder Boy is where the pair is really read.
VCOUNT_MID = 0xFF8207

from kit_smoke_project import (HW_READ_ENTRY, MFP_GPIP, RMW_ENTRY, SHIFTER_SYNC,
                               SHIFTER_VCOUNT_LOW, STATIC_TWICE_ENTRY, SYNC_ONLY_ENTRY,
                               VOLATILE_TWICE_ENTRY, WIDE_READ_ENTRY, WRITE_THEN_READ_ENTRY, bind)

harness = bind()
emu = harness.emu

# The bytes the cases declare. DELIBERATELY NEITHER the audio-capture profile's nor 0 — the same
# rule `hw_model_probe.c` states for DECLARED_BYTE, and it is load-bearing HERE too. Seeded with the
# profile's own bytes ($b0/$02), every green case below would stay green if the mode's declaration
# leaked into a disarmed run; seeded with 0, it would stay green if the seed were never installed at
# all. With these, either defect reds. The model serves a BYTE, not a machine, and what this suite
# tests is the plumbing that carries it — so no case here needs the real machine's values, and the
# only two that involve the profile read it from `emu.hw_capture_profile()`.
DECLARED_GPIP = 0x5A
DECLARED_SYNC = 0xA5
DECLARED_VCOUNT = 0x3C                # ...and the same rule for the volatile slot's own cases
DECLARED = {MFP_GPIP: DECLARED_GPIP, SHIFTER_SYNC: DECLARED_SYNC}
# ...and a declaration whose two bytes are EQUAL, so that a mutant reading them in the wrong order
# differs from a correct run in nothing but the order.
SAME_BYTE = 0x42
BOTH_THE_SAME = {MFP_GPIP: SAME_BYTE, SHIFTER_SYNC: SAME_BYTE}


def test_the_smoke_prg_reads_the_addresses_the_model_actually_names():
    """`kit_smoke_project` spells the two addresses as literals, because it plants them into 68000
    code before anything is bound and cannot ask the `.so`. Pin them equal to the model's own table
    here, where `emu` IS bound (CLAUDE.md §5: one canonical definition, the other pinned by a test).

    Unpinned, an address corrected in `os.h` would leave the `.PRG` reading one the model no longer
    names — and the failure would read as "the oracle did not read the tempo pair", sending the
    reader to the routine rather than to the drift.
    """
    # THE WHOLE TABLE, spelled once here and equal: a prefix pin would let an address be inserted
    # ahead of these two — which renumbers every slot the ledger reports — and still pass.
    assert (MFP_GPIP, SHIFTER_SYNC, VCOUNT_MID, SHIFTER_VCOUNT_LOW) == emu.HW_ADDRS, (
        f"the smoke project plants reads of {MFP_GPIP:#x}/{SHIFTER_SYNC:#x}/"
        f"{SHIFTER_VCOUNT_LOW:#x} but the model names "
        f"{', '.join(f'{a:#x}' for a in emu.HW_ADDRS)}")


def _tempo_pair(glue_name, hw_seed=None, entry=HW_READ_ENTRY, **kwargs):
    """Run one of the .PRG's hardware-read routines against a `kit_candidate.c` glue function."""
    return harness.differential(entry, dict(kwargs),
                                lambda lib, buf: getattr(lib, glue_name)(buf),
                                hw_seed=hw_seed)


def test_a_correct_reconstruction_of_a_declared_hardware_read_is_green():
    """The whole plumbing, end to end: the same two reads as 68000 code and as C, one declaration
    handed to both sides, the ordered stream compared and equal.

    The image comparison contributes NOTHING here — neither routine writes an image byte, which is
    the situation this surface exists for — so a green result is entirely the read stream's word.
    """
    diffs, info = _tempo_pair("g_hw_reads_the_pair", hw_seed=DECLARED)
    assert diffs == []
    assert info["regs"]["hw_events"] == [(MFP_GPIP, DECLARED_GPIP), (SHIFTER_SYNC, DECLARED_SYNC)], (
        "the oracle did not read the tempo pair, so nothing was compared")
    assert info["regs"]["d1"] & 0xFF == DECLARED_GPIP, (
        "the oracle branched on something other than the declared byte — the declaration is not "
        "reaching the instruction this case is about")


def test_an_undeclared_hardware_read_refuses_the_differential():
    """THE PHASE 7 REFUSAL, and the false green it closes.

    Undeclared, both sides read a fabricated 0: GPIP bit 7 clear says "monochrome monitor" and sync
    bit 1 clear says "60 Hz", so the reconstruction and the original take the same wrong branch and
    the diff agrees with itself. That is the `$ffff820a` defect BuggyBoy shipped — green through its
    entire differential, and only visible on real hardware.

    The remedy is named in the message, with the addresses to declare, because a refusal a reader
    cannot act on is a refusal that gets suppressed.
    """
    with pytest.raises(AssertionError, match="hw_seed=") as raised:
        _tempo_pair("g_hw_reads_the_pair")
    assert "0xfffa01" in str(raised.value) and "0xff820a" in str(raised.value), (
        "the refusal did not name the addresses the case must declare")


def test_a_bare_emu_run_of_the_same_routine_is_served_rather_than_refused():
    """The OTHER half of the split, and the reason the refusal is not in `emu.run`.

    A bare run is how this workspace drives a game's relocator, its Copylock and its bootstrap
    (`test_copylock.py`, `test_bootstrap.py`) — code whose hardware reads are nobody's enumerated
    list. Refusing there would sink those runs to close a false green they cannot have: nothing is
    being verified, so nothing can be falsely verified. So the read is served the 0 it has always
    been served, and merely RECORDED.

    Stated as a case because "make the model always-on" is exactly the tidy-looking change that
    would regress them.
    """
    _, _, out_regs = emu.run(harness.make_image(), HW_READ_ENTRY)
    assert out_regs["hw_unseeded"] == [MFP_GPIP, SHIFTER_SYNC], (
        "the undeclared reads were not recorded, so harness.differential has nothing to refuse on")
    assert out_regs["hw_events"] == [(MFP_GPIP, 0), (SHIFTER_SYNC, 0)], (
        "a bare run's answer changed — it must stay the fabricated 0, which is what makes this "
        "split zero-regression for every existing emu.run caller")


def test_the_mutant_that_only_the_read_stream_comparison_can_catch(monkeypatch):
    """`_vet_hw_state` is load-bearing, and this measures it rather than asserting it.

    `g_hw_reads_the_pair_backwards` reads the same two addresses in the other order, and the case
    declares both to the SAME byte — so the values it branches on, the declared file and the
    (untouched) image are a correct run's exactly. With the comparison stubbed out the differential
    comes back GREEN. Restore it and the same run reds. That gap IS the check's value.
    """
    monkeypatch.setattr(harness, "_vet_hw_state", lambda entry, o_regs: None)
    diffs, _ = _tempo_pair("g_hw_reads_the_pair_backwards", hw_seed=BOTH_THE_SAME)
    assert diffs == [], (
        "the mutant changed an image byte, so this case is not measuring the off-image comparison")

    monkeypatch.undo()
    with pytest.raises(AssertionError, match="modeled hardware read stream mismatch"):
        _tempo_pair("g_hw_reads_the_pair_backwards", hw_seed=BOTH_THE_SAME)


def test_the_two_model_implementations_disagreeing_is_caught_by_the_declared_bytes(monkeypatch):
    """`_vet_hw_state`'s SECOND comparison, which the read stream cannot make for it.

    The stream compares what each side was *served*; the declared-byte file compares what each side
    was *given*. Here the candidate is seeded with BOTH addresses declared while the case declares
    only the sync byte — so both sides read the sync byte and serve the same value, the streams
    match entry for entry, and only the known-mask separates them. That is the shape of the two
    model implementations drifting (a slot numbering changed on one side, the capture profile
    leaking in), which is what the file comparison is for.

    Delete the file compare and this case goes green, which is why it exists: a branch a mutation
    survives is a branch the suite does not have.
    """
    # The REAL installer, captured before the patch and then called with a different argument — not
    # a hand-rolled copy of it. A copy would keep passing the day the real one changed (a new reset
    # to make, an encoder swapped), and this case would go on "proving" the comparison against
    # plumbing the harness no longer runs.
    seed_candidate_hw = harness._seed_candidate_hw
    monkeypatch.setattr(harness, "_seed_candidate_hw",
                        lambda hw_seed: seed_candidate_hw(DECLARED))
    with pytest.raises(AssertionError, match="the declared hardware bytes diverged"):
        harness.differential(SYNC_ONLY_ENTRY, {}, lambda lib, buf: lib.g_hw_reads_the_sync(buf),
                             hw_seed={SHIFTER_SYNC: DECLARED_SYNC})


def test_a_candidate_that_never_reads_is_caught_too():
    """The other mutant of the same class: a port that hardcodes what it should have read, which is
    what code written against a fabricated 0 looks like once the byte is declared. Its stream is
    empty where the oracle's has two entries."""
    with pytest.raises(AssertionError, match="modeled hardware read stream mismatch"):
        _tempo_pair("g_hw_untouched", hw_seed=DECLARED)


def test_the_candidate_is_really_seeded_before_it_runs(monkeypatch):
    """`_seed_candidate_hw` is load-bearing too: without it the candidate reads an address nothing
    declared, refuses through `os_refused()`, and `_vet_no_os_refusal` throws the case away.

    That is the failure a ONE-SIDED declaration produces — the oracle served the read, the candidate
    did not — and it is exactly what "refusing on one side is a false green" is about, caught rather
    than passed.

    The candidate's state is cleared first, by the very call being stubbed out: it is process-global,
    so without that the run would inherit whatever the previous case left in it and the failure would
    depend on test order rather than on the missing declaration.
    """
    harness._seed_candidate_hw(None)
    monkeypatch.setattr(harness, "_seed_candidate_hw", lambda hw_seed: None)
    with pytest.raises(AssertionError, match=r"os_\* call\(s\) the TOS model REFUSES") as raised:
        _tempo_pair("g_hw_reads_the_pair", hw_seed=DECLARED)
    # ...and the refusal NAMES the addresses. `os_refused()` is one tally shared by every refusing
    # helper, so without the hint this reds with a bare count and a list of causes about console
    # keys and file handles — sending the reader to look for a missing Bconstat gate.
    message = str(raised.value)
    assert f"{MFP_GPIP:#x}" in message and f"{SHIFTER_SYNC:#x}" in message, (
        "the candidate-side refusal does not say which modeled hardware address it was about")


def test_a_candidate_without_the_hardware_abi_is_refused_by_name(monkeypatch):
    """The optional-ABI arm. A candidate built outside kit.mk exports no `src/hw.c` symbols, and is
    served only while the oracle reads no modeled address — so the moment it does, the refusal must
    name the symbols that are missing rather than leave the reader guessing which of six they are.
    """
    monkeypatch.setattr(harness, "_has_hw_ledger", False)
    monkeypatch.setattr(harness, "_missing_hw_ledger", ["g_hw_log_slots"])
    with pytest.raises(AssertionError, match="exports no g_hw_log_slots"):
        _tempo_pair("g_hw_untouched", hw_seed=DECLARED)


def test_a_read_after_the_run_wrote_the_address_is_refused_and_not_seedable():
    """Wonder Boy writes `move.b #2,$ff820a` at $f91c and reads bit 1 of the same address at $17c90,
    so a run covering both is a real case rather than a hypothetical one.

    The model drops hardware writes, so such a read is served the byte the case declared the machine
    held ON ENTRY — which an instruction of that very run has replaced. Declaring it harder cannot
    help, so the refusal says so and names the two remedies that exist.
    """
    with pytest.raises(AssertionError, match="and then READ one back") as raised:
        _tempo_pair("g_hw_untouched", hw_seed=DECLARED, entry=WRITE_THEN_READ_ENTRY)
    message = str(raised.value)
    assert "Adding one cannot fix it" in message, (
        "the refusal reads as a missing declaration, which would send the reader to add a hw_seed "
        "the run's own store contradicts")
    assert f"{SHIFTER_SYNC:#x}: {DECLARED_SYNC:#04x}" in message, (
        "the case's seed is echoed in Python's decimal dict form — a reader cannot match "
        "`{16775690: 165}` against the address in the disassembly, which is the one thing this "
        "message exists to let them do")


def test_a_stale_read_says_so_even_when_the_case_declared_nothing():
    """The SAME run with no declaration at all is stale *and* undeclared — one read sets both masks.

    Reported as "declare it", the reader adds the `hw_seed` the message asks for, re-runs, and only
    then learns it is not seedable. So the narrower diagnosis wins: `_vet_hw_reads_are_declared`
    tests stale first. Without this case the ordering is an implementation detail nothing holds.
    """
    with pytest.raises(AssertionError, match="and then READ one back") as raised:
        _tempo_pair("g_hw_untouched", entry=WRITE_THEN_READ_ENTRY)
    message = str(raised.value)
    assert "hw_seed={" not in message, (
        "the undeclared refusal won over the stale one, so the message offers a remedy that cannot "
        "work — the reader adds the seed and hits the un-seedable refusal on the next run")
    assert "no hw_seed was given" in message, (
        "with no seed the message still says `hw_seed=None declares what the machine held on "
        "ENTRY`, which states the opposite of what it means")


def test_a_wide_read_of_a_modeled_address_is_refused_and_names_it():
    """Only a BYTE read is served. A word read takes in the shifter register beside the sync byte,
    which the model would have to fabricate as 0 — the same false green one address over, so it is
    refused rather than served a partial answer.

    The refusal NAMES the address, like the other two: the surface behind it is a slot mask rather
    than a count, so a reader is not left bisecting "one of these N".
    """
    with pytest.raises(AssertionError, match="16- or 32-bit access") as raised:
        _tempo_pair("g_hw_untouched", hw_seed=DECLARED, entry=WIDE_READ_ENTRY)
    assert hex(SHIFTER_SYNC) in str(raised.value) and hex(MFP_GPIP) not in str(raised.value), (
        "the refusal listed the whole modeled set instead of the address the run actually read wide")


def test_a_second_read_of_a_volatile_address_is_refused_and_not_seedable():
    """THE VOLATILE REFUSAL, at the differential level rather than at the probe's.

    A seed is a per-run CONSTANT, and the shifter's video counter advances every few scanlines — so
    a run that reads `$ff8209` twice is served the first read's byte for the second one, and the
    case would be verified against a value the address cannot have held twice. That is the
    admissibility argument for putting a counter in the model at all, and this is the case that
    makes it a rule instead of a comment.

    The candidate here is FAITHFUL — it makes the same two reads through `hw_read8`, and the
    candidate side has no re-read refusal of its own — so with `_vet_hw_reads_are_declared`'s
    volatile branch removed the streams match entry for entry, the image is untouched on both sides,
    and the differential comes back green about a counter that never moved. Measured: with the branch
    reverted this case reds with DID NOT RAISE, which is the false green named exactly.

    Declared, deliberately. The undeclared refusal would fire on the same run, and a case that let it
    win would pass while measuring nothing about volatility.
    """
    with pytest.raises(AssertionError, match="MORE THAN ONCE in one run") as raised:
        _tempo_pair("g_hw_reads_the_vcount_twice", hw_seed={SHIFTER_VCOUNT_LOW: DECLARED_VCOUNT},
                    entry=VOLATILE_TWICE_ENTRY)
    message = str(raised.value)
    assert hex(SHIFTER_VCOUNT_LOW) in message, (
        "the refusal did not name the address the case must do something about")
    assert "hw_seed={" not in message, (
        "the refusal offers a declaration as the remedy, which cannot work — one declaration is one "
        "byte, and the case needs a different SHAPE (end it earlier, or split it in two)")


def test_a_second_read_of_a_STATIC_address_is_served_rather_than_refused():
    """The control that says the refusal above is about VOLATILITY and not about repetition.

    A static byte is one the machine answers the same way every time, so ONE declaration describes
    every read of it and a run that reads `$fffa01` twice is correct — it must stay green. Without
    this case "refuse every re-read" is a tidy-looking simplification of the branch above, and
    nothing would catch it.
    """
    diffs, info = _tempo_pair("g_hw_reads_the_gpip_twice", hw_seed=DECLARED,
                              entry=STATIC_TWICE_ENTRY)
    assert diffs == []
    assert info["regs"]["hw_events"] == [(MFP_GPIP, DECLARED_GPIP), (MFP_GPIP, DECLARED_GPIP)], (
        "the oracle did not read the static byte twice, so this proves nothing about the exemption")


def test_a_declaration_the_run_never_reads_is_left_alone():
    """The limit of the guard, stated as a case so it cannot be tightened by accident.

    An over-declared input is ordinary — a case may declare a byte the branch it takes never reads —
    and refusing that would make `hw_seed` a claim about control flow rather than about the machine.
    The routine here reads only the sync byte while the case declares both.
    """
    diffs, info = harness.differential(
        SYNC_ONLY_ENTRY, {}, lambda lib, buf: lib.g_hw_reads_the_sync(buf), hw_seed=DECLARED)
    assert diffs == []
    assert info["regs"]["hw_events"] == [(SHIFTER_SYNC, DECLARED_SYNC)], (
        "the run read something other than the sync byte alone, so this proves nothing about an "
        "over-declared address")


def test_a_case_that_never_touches_the_model_is_unaffected_by_it():
    """ZERO REGRESSION, as a case. Every existing green differential in every project reads no
    modeled hardware address and declares none — and must stay green with the model in place, with
    both sides' streams empty rather than merely uncompared."""
    diffs, info = harness.differential(RMW_ENTRY, {}, lambda lib, buf: lib.g_psg_rmw(buf),
                                       psg_seed={7: 0xC0})
    assert diffs == []
    assert info["regs"]["hw_events"] == [], "the PSG routine read a modeled hardware address"
    assert info["regs"]["hw_unseeded"] == [] and info["regs"]["hw_stale"] == []


def test_a_differential_under_the_audio_capture_mode_is_still_refused():
    """The capture fold did not weaken the veto, which is the guard that keeps the mode's declared
    profile out of every differential. Under the mode the modeled addresses answer the 50 Hz
    colour-ST machine whatever the case says, so a green there would mean the reconstruction agrees
    with `shim.c`'s declaration rather than with the game's machine.
    """
    emu.audio_capture(True)
    try:
        with pytest.raises(AssertionError, match="AUDIO-CAPTURE mode is armed"):
            _tempo_pair("g_hw_reads_the_pair", hw_seed=DECLARED)
    finally:
        emu.audio_capture(False)


def test_a_hw_seed_passed_under_the_capture_mode_is_refused():
    """The other guard around the fold. The mode installs its OWN declaration over this model, so a
    case's would be silently ignored — and "silently ignored" is the failure this whole phase is
    about. `emu.run` refuses the pair outright rather than picking a winner.
    """
    with emu.audio_capturing():
        with pytest.raises(RuntimeError, match="hw_seed was passed"):
            emu.run(harness.make_image(), HW_READ_ENTRY, hw_seed=DECLARED)

        _, _, out_regs = emu.run(harness.make_image(), HW_READ_ENTRY)
        # `hw_capture_profile()` reports the slots the mode's own mask DECLARES and no others, so
        # this is back to comparing the run's ordered reads against the whole of it.
        assert out_regs["hw_events"] == list(emu.hw_capture_profile().items()), (
            "under the mode the run was served something other than the profile the mode declares")


def test_declaring_an_address_the_model_does_not_serve_is_refused():
    """`hw_seed` is over a NAMED set. A case declaring, say, the FDC status would otherwise install
    nothing, read a fabricated 0, and pass while testing the read it meant to declare not at all —
    the silent-argument mistake `_vet_psg_seed_reaches_the_path` catches one model over.
    """
    with pytest.raises(ValueError, match="does not serve"):
        _tempo_pair("g_hw_reads_the_pair", hw_seed={0xFF8604: 0x01})
