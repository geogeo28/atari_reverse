"""Pin the SEEDED HARDWARE READ MODEL — both sides of it — kit-side.

The model (TRAP_MODEL.md, "Phase 7") makes a branch on a hardware byte verifiable: a byte read of
one of a small NAMED SET of addresses is answered from a file the CASE declares, and an address
nothing declared is served the 0 it has always been served *and recorded*, so that
`harness.differential` — not `emu.run` — can refuse the case. It is the second modeled surface with
an implementation on each shore, `oracle/shim.c` for the original and `src/hw.c` for a
reconstruction, and the two must agree exactly, because the harness compares their ordered read
streams and their declared files.

That is a KIT-WIDE property, so it is pinned here rather than in the first project to need it (the
placement rule `test_psg_model.py` next door follows). The obstacle is the usual one: this directory
binds no project, and `harness`/`emu` both load a candidate `.so` at import, so the oracle is
unreachable from Python here. `hw_model_probe.c` drives both sides in C instead — which also lets the
MUTANT cases below stand in for the reconstruction this suite does not have.

`probe_build.compile_probe` builds it from the oracle's own sources plus `src/hw.c`, so a reverted
guard reddens immediately instead of hiding behind an up-to-date-looking `liboracle.so`.
"""
import re

from pathlib import Path

import pytest

from probe_build import compile_probe, run_probe

KIT = Path(__file__).resolve().parents[1]
PROBE_SRC = Path(__file__).with_name("hw_model_probe.c")
CANDIDATE_SRC = (KIT / "src" / "hw.c", KIT / "src" / "os_refusal.c")

# The modeled set's SLOT numbers (os.h's OS_HW_SLOT_*). Spelled here rather than imported, because
# the one Python mirror a bare checkout can import (`os_map`) deliberately holds no copy of the
# hardware table — emu.py reads it from the .so instead. `test_the_slots_are_the_addresses_os_h_names`
# below is what keeps these two numbers honest against the C.
GPIP = 0            # $fffa01, the MFP GPIP: bit 7 = monitor detect
SYNC = 1            # $ff820a, the shifter's sync mode: bit 1 = 50 Hz
VMID = 2            # $ff8207, the shifter's video address counter, mid byte
VLOW = 3            # $ff8209, ...and its low byte
ACIA = 4            # $fffc00, the IKBD ACIA's status: bit 1 = the transmit register is empty
NSLOTS = 5

# The bytes the probe's cases use. DECLARED is what a case declares (deliberately not the capture
# profile's, so a case served the profile where it asked for its own declaration is visible); OTHER
# is what a case declares when it must show WHICH declaration was installed.
DECLARED = 0x5A
OTHER = 0xA5
FABRICATED = 0x00   # what an undeclared address is served: the model's own 0, recorded as such
# The two bits the whole phase is about, in the capture profile's byte (shim.c names them
# MFP_GPIP_COLOUR / SHIFTER_SYNC_50HZ; kit_smoke_project.py names the whole bytes). Both CLEAR is
# the monochrome 60 Hz machine an unmodeled read's 0 reports, which is the failure the mode closes.
GPIP_COLOUR_MONITOR = 0x80
SYNC_50HZ = 0x02
GPIP_BIT = 1 << GPIP
SYNC_BIT = 1 << SYNC
VMID_BIT = 1 << VMID
VLOW_BIT = 1 << VLOW
ACIA_BIT = 1 << ACIA
# What the probe declares when it declares EVERY slot — its own ALL_SLOTS_DECLARED, spelled the same
# way so that a slot added to os.h's table lands on both sides at once rather than in the C alone.
ALL_KNOWN = (1 << NSLOTS) - 1
# ...and the two the audio-capture profile has bytes for, which is a different set and stays one
# even as the table grows. The video-counter slots are deliberately outside it (shim.c).
PROFILE_PAIR = GPIP_BIT | SYNC_BIT

# What the MODEL declares when the case does not (os.h's os_hw_model_defaults). Exactly one slot has
# a default — the ACIA status, whose byte a send loop's exit depends on and which no case should have
# to spell — so `_file` and `_known` below fold it in and every row states what a run really leaves
# rather than what the case alone declared.
ACIA_TX_RDY = 0x02
MODEL_DEFAULTS = {ACIA: ACIA_TX_RDY}
DEFAULTED = ACIA_BIT


def _file(**slots):
    """The expected declared-byte file: the model's own defaults, then every slot the case names."""
    return {slot: slots.get(f"s{slot}", MODEL_DEFAULTS.get(slot, 0)) for slot in range(NSLOTS)}


def _known(declared=0):
    """...and the expected known-mask: what the case declared, plus what the model declares for it."""
    return declared | DEFAULTED


def _file_all(value):
    """...and the file a probe case that declared EVERY slot leaves. Spelled as "all of them"
    rather than slot by slot so that a slot added to os.h's table lands here automatically — which
    is what those cases are claiming (the probe seeds `ALL_SLOTS_DECLARED` with one byte)."""
    return {slot: value for slot in range(NSLOTS)}


# One entry per case the probe runs. `scalars` are exact; `ledger` is the ordered (slot, value) read
# stream — which is the ENTIRE observable effect of a modeled read, since it touches no image byte;
# `file` is the whole declared-byte file, so a case cannot claim one byte and leave the other
# unwatched.
#
# THE TABLE IS THE ASSERTION, and each row's comment is its argument. A narrative test below is kept
# only where it pins something no row can — a relation BETWEEN cases (the two sides agreeing, a
# mutant separated from a correct run, what a capture was served compared against the profile it
# installs) or a fact about the SOURCE rather than about a run. Re-asserting a row in prose adds a
# second place to update and no coverage: the mutation sweep is what says the rows carry it, and it
# does.
ORACLE_CASES = {
    # An address the case DECLARED reads back as declared, and declaring it is not consumed by one
    # run — the seed is the run's entry state, re-installed each time, not a one-shot. Nor does it
    # SURVIVE one: withdraw it (`undeclared_read`, two rows down, over the identical image and the
    # identical routine) and the read is served 0 again with `known` back to 0. Without that
    # per-run reinstall a case could be verified against a byte another case declared, and under
    # `pytest -n auto` which case that is would not be stable — the defect ENTRY_SR closed for the
    # condition codes.
    "declared_read": dict(scalars={"d1": DECLARED, "unseeded": 0, "stale": 0, "wide": 0,
                                   "known": _known(GPIP_BIT), "nlog": 1},
                          ledger=[(GPIP, DECLARED)], file=_file(s0=DECLARED)),
    "declared_read_again": dict(scalars={"d1": DECLARED, "unseeded": 0, "stale": 0, "wide": 0,
                                         "known": _known(GPIP_BIT), "nlog": 1},
                                ledger=[(GPIP, DECLARED)], file=_file(s0=DECLARED)),
    # ...and withdrawing it restores the fabrication. THIS ROW IS PHASE 7'S ONE DIVERGENCE FROM
    # PHASE 6, and a "fix" in either direction is the tidy-looking change to watch for: an undeclared
    # PSG register sinks the run inside emu.run, an undeclared hardware byte does NOT. It is served
    # the same 0 the shim answered before this model existed — so a bare emu.run's behaviour is
    # unchanged, which is what keeps the relocator/Copylock/bootstrap suites green — and only
    # RECORDED, in `unseeded`, which is what lets harness.differential refuse the case. The read is
    # ledgered either way: the candidate logs its own refused read, so a stream missing it here
    # would diverge for the wrong reason. (The harness-level half is
    # test_hw_differential.py::test_a_bare_emu_run_of_the_same_routine_is_served_rather_than_refused,
    # which asserts it against a real run rather than against this table.)
    "undeclared_read": dict(scalars={"d1": FABRICATED, "unseeded": GPIP_BIT, "stale": 0, "wide": 0,
                                     "known": _known(), "nlog": 1},
                            ledger=[(GPIP, FABRICATED)], file=_file()),
    # Declaring ONE address declares one address. The mask is per-slot, so a case that seeds the
    # GPIP and reads the sync byte is as undeclared as one that seeds nothing.
    # THE VIDEO COUNTER, the pair the model grew for Wonder Boy's $51ac. Declared, both bytes are
    # served and both land in the ordered ledger under their own slots.
    "vcount_pair_declared": dict(scalars={"d1": DECLARED, "unseeded": 0, "stale": 0, "wide": 0,
                                          "known": _known(VMID_BIT | VLOW_BIT), "nlog": 2},
                                 ledger=[(VMID, DECLARED), (VLOW, DECLARED)],
                                 file=_file(s2=DECLARED, s3=DECLARED)),
    # ...and a declaration of the OLD pair is not theirs: both reads are the fabricated 0 the model
    # answered before they were named, now TALLIED under their own bits where before this change
    # they were an unmodeled off-image read that nothing recorded at all.
    "vcount_pair_undeclared": dict(scalars={"d1": FABRICATED, "unseeded": VMID_BIT | VLOW_BIT,
                                            "stale": 0, "wide": 0, "known": _known(GPIP_BIT), "nlog": 2},
                                   ledger=[(VMID, FABRICATED), (VLOW, FABRICATED)],
                                   file=_file(s0=DECLARED)),
    # A WRITE to a counter byte and then a read of it: the seed no longer describes the slot, which
    # is the stale shape the sync byte has one address over.
    "vcount_write_then_read": dict(scalars={"d1": DECLARED, "unseeded": 0, "stale": VLOW_BIT,
                                            "wide": 0, "known": ALL_KNOWN, "nlog": 1},
                                   ledger=[(VLOW, DECLARED)], file=_file_all(DECLARED)),
    # A VOLATILE byte read TWICE: served both times (the model has one byte to give) and TALLIED,
    # which is what harness.differential turns into a refusal. Without it os.h's "read once per run"
    # is a comment the next handler to poll a counter quietly falsifies.
    "volatile_read_twice": dict(scalars={"d1": DECLARED, "unseeded": 0, "stale": 0, "wide": 0,
                                         "reread": VLOW_BIT, "known": ALL_KNOWN, "nlog": 2},
                                ledger=[(VLOW, DECLARED), (VLOW, DECLARED)],
                                file=_file_all(DECLARED)),
    # ...and a STATIC one read twice is served twice with nothing tallied: the monitor-detect byte
    # really does answer the same thing every time, and the tempo head reads it for two bits.
    "static_read_twice": dict(scalars={"d1": DECLARED, "unseeded": 0, "stale": 0, "wide": 0,
                                       "reread": 0, "known": ALL_KNOWN, "nlog": 2},
                              ledger=[(GPIP, DECLARED), (GPIP, DECLARED)],
                              file=_file_all(DECLARED)),
    "other_address_undeclared": dict(scalars={"d1": FABRICATED, "unseeded": SYNC_BIT, "stale": 0,
                                              "wide": 0, "known": _known(GPIP_BIT), "nlog": 1},
                                     ledger=[(SYNC, FABRICATED)], file=_file(s0=DECLARED)),
    # Two reads of two addresses, both declared to the SAME byte: only their ORDER separates this
    # stream from the reverse one, which is what the ledger comparison adds over a set of reads.
    # Declaring ONE address declares one address (the row above): the mask is per-slot, so a case
    # that seeds the GPIP and reads the sync byte is as undeclared as one that seeds nothing.
    "two_reads_in_order": dict(scalars={"d1": DECLARED, "unseeded": 0, "stale": 0, "wide": 0,
                                        "known": ALL_KNOWN, "nlog": 2},
                               ledger=[(SYNC, DECLARED), (GPIP, DECLARED)],
                               file=_file_all(DECLARED)),
    # A WIDE read taking a modeled byte in. Served nothing (d1 is the ordinary off-image 0) and NOT
    # ledgered — the model has no answer for the neighbouring MFP/shifter registers it would also
    # have to hand back, so it records the access instead of inventing them. Recorded by SLOT, not
    # as a count: the refusal has to name the address a reader must act on. `unseeded` stays 0 —
    # reporting a wide read as a missing DECLARATION would send them to add a hw_seed that cannot
    # serve it. All three rows use an address a 68000 can really execute that width at; the kit
    # builds Musashi with M68K_EMULATE_ADDRESS_ERROR off, so a case planted at an odd address would
    # quietly stop measuring the refusal the day that flag moved.
    "word_read": dict(scalars={"d1": 0, "unseeded": 0, "stale": 0, "wide": GPIP_BIT,
                               "known": _known(GPIP_BIT), "nlog": 0},
                      ledger=[], file=_file(s0=DECLARED)),
    "long_read": dict(scalars={"d1": 0, "unseeded": 0, "stale": 0, "wide": SYNC_BIT,
                               "known": _known(GPIP_BIT), "nlog": 0},
                      ledger=[], file=_file(s0=DECLARED)),
    # ...including one that straddles INTO the byte from below, the case a start-address equality
    # test misses (hw_portability.py's lattice has the same case for the PSG block).
    # A long read whose span covers $ff8209 AND $ff820a, so it takes in TWO modeled slots — which
    # is what os_hw_slots_touched is for, and what a wide-read tally over a growing table has to
    # keep reporting rather than collapsing to the first one it meets.
    "long_read_straddling_in": dict(scalars={"d1": 0, "unseeded": 0, "stale": 0,
                                             "wide": SYNC_BIT | VLOW_BIT,
                                             "known": _known(GPIP_BIT), "nlog": 0},
                                    ledger=[], file=_file(s0=DECLARED)),
    # The run WROTE the address and then read it back — Wonder Boy's own shape, `move.b #2,$ff820a`
    # at $f91c and `btst #1,$ff820a` at $17c90, so any whole-frame run covers both. The write is
    # dropped (the model reproduces what these addresses ANSWER, not what storing to them does), so
    # the read is served the ENTRY declaration, which an instruction of this very run has
    # contradicted. Recorded in `stale`, its own cause because its remedy is its own: no declaration
    # can fix it, so `unseeded` stays 0 rather than offering one.
    "write_then_read": dict(scalars={"d1": DECLARED, "unseeded": 0, "stale": SYNC_BIT, "wide": 0,
                                     "known": ALL_KNOWN, "nlog": 1},
                            ledger=[(SYNC, DECLARED)], file=_file_all(DECLARED)),
    # ...while a write NOTHING reads back is the ordinary invisible hardware write it always was:
    # `stale` stays 0, or refusing it would sink runs that read nothing at all.
    "write_only": dict(scalars={"d1": 0, "unseeded": 0, "stale": 0, "wide": 0, "known": ALL_KNOWN,
                                "nlog": 0},
                       ledger=[], file=_file_all(DECLARED)),
    # The audio-capture fold. Off the mode, nothing declared: both reads are the silent 0 that made
    # a replayer pick the MONOCHROME tempo, which is why the mode exists at all.
    "profile_pair_undeclared": dict(scalars={"d1": FABRICATED, "unseeded": PROFILE_PAIR, "stale": 0,
                                             "wide": 0, "known": _known(), "nlog": 2},
                                    ledger=[(GPIP, FABRICATED), (SYNC, FABRICATED)], file=_file()),
    # Under the mode the same run is served the profile — because the mode INSTALLS A SEED over this
    # model rather than keeping a switch of its own. The bytes are claimed against
    # `osh_hw_capture_profile()` rather than restated, in the case below.
    "profile_pair_under_capture": dict(scalars={"unseeded": 0, "stale": 0, "wide": 0,
                                                "known": _known(PROFILE_PAIR), "nlog": 2}),
    # ...and the mode's declaration WINS over a case's, which is why emu.run refuses to take one.
    # ...and it declares the PROFILE PAIR and no more, even with every slot in the case's own seed:
    # the mode has bytes for two of the modeled set and says so (shim.c's HW_CAPTURE_PROFILE_KNOWN);
    # the ACIA's default is the model's, not the mode's, and is folded in by `_known` either way.
    "capture_overrides_a_seed": dict(scalars={"unseeded": 0, "stale": 0, "wide": 0,
                                              "known": _known(PROFILE_PAIR), "nlog": 2}),
    # ...but does not survive the mode. No reset call in between: the next run reinstalls the case's
    # own declaration, which is what stops the profile leaking into a differential.
    "after_capture_the_case_seed_returns": dict(scalars={"d1": OTHER, "unseeded": 0, "stale": 0,
                                                         "wide": 0, "known": ALL_KNOWN, "nlog": 2},
                                                ledger=[(GPIP, OTHER), (SYNC, OTHER)],
                                                file=_file_all(OTHER)),
    # The bench is the OTHER door into the oracle — no OS traps, a C function measured for cycles —
    # and it reaches this model through the same enter_from_reset. So the per-run reinstall belongs
    # THERE rather than in osh_run alone: with it in osh_run only, a bench issued after a declared
    # run would inherit that run's bytes AND its ledger, and report its own hardware reads with
    # another run's in front of them.
    "bench_starts_from_the_seed": dict(scalars={"d1": 0, "unseeded": 0, "stale": 0, "wide": 0,
                                                "known": ALL_KNOWN, "nlog": 0},
                                       ledger=[], file=_file_all(DECLARED)),
}

# Every oracle case asserts the WHOLE scalar set, so a scalar added to the probe's report must be
# named in every expectation. `reread` is 0 everywhere but the two volatile cases above — a default
# rather than twenty-odd copies of the same line, and the strict comparison is unchanged.
for _case in ORACLE_CASES.values():
    _case["scalars"].setdefault("reread", 0)

CANDIDATE_CASES = {
    # The faithful reconstruction: it reads the declared byte, refuses nothing, and logs the read.
    "cand_declared_read": dict(scalars={"d1": DECLARED, "refusals": 0, "known": ALL_KNOWN,
                                        "nlog": 1},
                               ledger=[(GPIP, DECLARED)], file=_file_all(DECLARED)),
    # MUTANT: it reads the OTHER modeled address, declared to the same byte. The value it branches
    # on, the declared file and the (empty) image effect are all a correct run's — only the ledger's
    # slot separates them.
    "cand_wrong_address": dict(scalars={"d1": DECLARED, "refusals": 0, "known": ALL_KNOWN,
                                        "nlog": 1},
                               ledger=[(SYNC, DECLARED)], file=_file_all(DECLARED)),
    # MUTANT: it never reads and hardcodes the answer — what a port written against a fabricated 0
    # looks like. Its ledger is empty where the oracle's has an entry.
    "cand_skips_the_read": dict(scalars={"d1": DECLARED, "refusals": 0, "known": ALL_KNOWN,
                                         "nlog": 0},
                                ledger=[], file=_file_all(DECLARED)),
    # The read the ORACLE serves 0, made against no declaration: the candidate must TALLY rather
    # than answer — refusing on one side only is the false green — and log it anyway.
    "cand_undeclared_read": dict(scalars={"d1": 0, "refusals": 1, "known": _known(), "nlog": 1},
                                 ledger=[(GPIP, FABRICATED)], file=_file()),
    # An address outside the modeled set: refused AND unlogged, since the oracle records nothing for
    # it either and an entry here would diverge the streams for a reason that is not about a read.
    # Quietly serving 0 for, say, the FDC status at $ff8604 would be the fabrication over again under
    # a new name — and that address in particular cannot be modeled this way at all, since a poll
    # loop needs its answer to CHANGE between two reads and a per-run constant cannot
    # (TRAP_MODEL.md, Phase 7's non-goal).
    "cand_unmodeled_address": dict(scalars={"d1": 0, "refusals": 1, "known": ALL_KNOWN, "nlog": 0},
                                   ledger=[], file=_file_all(DECLARED)),
    # g_hw_reset really clears: a case declaring nothing does not see the previous case's bytes.
    # It runs before EVERY candidate run, the poison re-run included — the state is process-global,
    # so without the clear a candidate reads a byte this case never declared and stays green on it,
    # and under `pytest -n auto` which case it inherited is not even stable.
    "cand_seed_does_not_leak": dict(scalars={"d1": 0, "refusals": 1, "known": _known(), "nlog": 1},
                                    ledger=[(GPIP, FABRICATED)], file=_file()),
}

EXPECTED = {**ORACLE_CASES, **CANDIDATE_CASES}
# The capture profile is printed as an `F` block of its own rather than as a case, so it is claimed
# separately from the run cases above.
PROFILE_CASE = "capture_profile"


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    """Build and run the probe once; return {case: {"scalars", "ledger", "file"}}."""
    return run_probe(compile_probe(PROBE_SRC, tmp_path_factory.mktemp("hw_model"), CANDIDATE_SRC))


def test_the_probe_reports_every_case(probe):
    """Guard the fixture itself: a probe that stopped printing (or a parse that stopped matching)
    would make every assertion below vacuously pass."""
    reported = set(probe) - {PROFILE_CASE}
    assert reported == set(EXPECTED), (
        f"probe cases and expectations disagree — only in probe: {sorted(reported - set(EXPECTED))}, "
        f"only in EXPECTED: {sorted(set(EXPECTED) - reported)}")


def test_the_slots_are_the_addresses_os_h_names():
    """The slot numbers this file spells must be os.h's, or every ledger claim above is about the
    wrong address while still comparing equal. Parsed rather than imported: `os_map` holds no copy
    of the hardware table (emu.py reads it from the .so), and this suite runs in a bare checkout."""
    source = (KIT / "include" / "os.h").read_text()
    defines = dict(re.findall(r"^#define\s+(OS_HW_\w+)\s+(0x[0-9a-fA-F]+|\d+)u?", source, re.M))
    assert int(defines["OS_HW_SLOT_MFP_GPIP"], 0) == GPIP
    assert int(defines["OS_HW_SLOT_SHIFTER_SYNC"], 0) == SYNC
    assert int(defines["OS_HW_SLOT_SHIFTER_VCOUNT_MID"], 0) == VMID
    assert int(defines["OS_HW_SLOT_SHIFTER_VCOUNT_LOW"], 0) == VLOW
    assert int(defines["OS_HW_NSLOTS"], 0) == NSLOTS
    assert int(defines["OS_HW_MFP_GPIP"], 0) == 0xFFFA01
    assert int(defines["OS_HW_SHIFTER_SYNC"], 0) == 0xFF820A
    assert int(defines["OS_HW_SHIFTER_VCOUNT_MID"], 0) == 0xFF8207
    assert int(defines["OS_HW_SHIFTER_VCOUNT_LOW"], 0) == 0xFF8209


def test_the_capture_profile_declares_exactly_the_slots_it_has_bytes_for():
    """The audio-capture fold's one latent trap, pinned STRUCTURALLY because no run can reach it.

    `g_hw_capture_profile` is a designated initializer, so a slot added to os.h's table gets a
    silent `0` in it. If the mode's known-mask were spelled "every slot", that fabricated `0` would
    be installed as a DECLARED answer — invisible to `g_hw_unseeded`, indistinguishable from a real
    declaration, and reporting a machine nobody described. That is the monochrome-profile failure
    the mode exists to close, one address over.

    With only two slots today, "every slot" and "these two" are the same number, so a behavioural
    case cannot tell them apart — the mutation sweep confirmed it survives every run-level case.
    The honest pin is therefore over the SOURCE: the mask must name the same slots the profile
    array gives bytes to. It is the check that fires the day a third address is added, which is the
    only day it matters.
    """
    shim = (KIT / "oracle" / "shim.c").read_text()
    profile = re.search(r"g_hw_capture_profile\[OS_HW_NSLOTS\]\s*=\s*\{(.*?)\};", shim, re.S)
    assert profile, "the capture profile's initializer is not where this pin looks for it"
    has_bytes = set(re.findall(r"\[(OS_HW_SLOT_\w+)\]", profile.group(1)))

    mask = re.search(r"#define HW_CAPTURE_PROFILE_KNOWN((?:.*?\\\n)*.*)", shim)
    assert mask, "HW_CAPTURE_PROFILE_KNOWN is not where this pin looks for it"
    declared = set(re.findall(r"OS_HW_SLOT_\w+", mask.group(1)))

    assert declared == has_bytes, (
        f"the audio-capture mode declares {sorted(declared)} but its profile only gives bytes to "
        f"{sorted(has_bytes)}. A slot in the first set and not the second is served a fabricated 0 "
        f"marked as a real declaration — the failure the mode exists to close; one in the second "
        f"and not the first is a byte the mode computed and then refused to serve")


# The two cases that deliberately claim a SUBSET of the scalars the probe prints: what they were
# SERVED is pinned against `osh_hw_capture_profile()` in a case of its own, rather than restated as
# constants here, so their `d1` and `nlog` are claimed and their served bytes are not. Enumerated by
# name so that "this case claims less" stays a decision rather than a habit — see
# test_every_probe_key_is_claimed_by_some_case.
SUBSET_CASES = ("profile_pair_under_capture", "capture_overrides_a_seed")


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_the_case_reports_what_the_model_promises(probe, case):
    """Every scalar the case claims, exactly.

    The two SUBSET_CASES claim fewer keys than the probe prints, so this filters to what each case
    claims — which on its own would let a NEW key the probe grew go unclaimed by everything.
    `test_every_probe_key_is_claimed_by_some_case` is the other half, and closes that directly.
    """
    expected = EXPECTED[case]["scalars"]
    reported = {key: value for key, value in probe[case]["scalars"].items() if key in expected}
    assert reported == expected, (
        f"{case}: the model reported {probe[case]['scalars']}, not {expected}")


def test_every_probe_key_is_claimed_by_some_case(probe):
    """A scalar the probe prints that NO case claims would otherwise be measured by nothing.

    The case above filters to the keys each row names, because two rows deliberately claim a subset
    — so a key added to `report_oracle`/`report_candidate` and to no row slips through it silently,
    and a whole surface (the next `unseeded`-shaped tally) ships unpinned while the suite stays
    green. This is the direct check: outside the two named subset cases, the keys the probe printed
    and the keys the table claims must be the SAME set, in both directions.

    Both directions matter. A key claimed and no longer printed is the other drift — the probe
    stopped reporting a surface and the filter above turns the row into a no-op.
    """
    for case, reported in sorted(probe.items()):
        if case in SUBSET_CASES or case == PROFILE_CASE:
            continue
        assert set(reported["scalars"]) == set(EXPECTED[case]["scalars"]), (
            f"{case}: the probe prints {sorted(reported['scalars'])} but the table claims "
            f"{sorted(EXPECTED[case]['scalars'])}. A key on one side only is a surface nothing "
            f"measures — add it to the row, or to SUBSET_CASES with the reason it is pinned "
            f"elsewhere")
    for case in SUBSET_CASES:
        assert set(EXPECTED[case]["scalars"]) < set(probe[case]["scalars"]), (
            f"{case} is listed as a subset case but claims every key the probe prints — drop it "
            f"from SUBSET_CASES so the check above covers it")


@pytest.mark.parametrize("case", sorted(case for case in EXPECTED if "ledger" in EXPECTED[case]))
def test_the_case_logs_the_read_stream_it_promises(probe, case):
    """The ordered read stream. It is the WHOLE observable effect of a modeled read: the access
    touches no image byte, and the branch it steers may leave no trace either."""
    assert probe[case]["ledger"] == EXPECTED[case]["ledger"], (
        f"{case}: the ledger is {probe[case]['ledger']}, not {EXPECTED[case]['ledger']}")


@pytest.mark.parametrize("case", sorted(case for case in EXPECTED if "file" in EXPECTED[case]))
def test_the_case_leaves_the_declared_bytes_it_promises(probe, case):
    assert probe[case]["file"] == EXPECTED[case]["file"], (
        f"{case}: the declared-byte file is {probe[case]['file']}, not {EXPECTED[case]['file']}")


def test_the_capture_mode_is_the_same_model_with_a_seed_installed(probe):
    """The FOLD, measured rather than asserted: the mode has no read path of its own any more.

    What it serves must be exactly `osh_hw_capture_profile()` — the seed it installs — for both
    addresses, and the same run off the mode with nothing declared must serve 0. Pinning it against
    the profile rather than against restated constants is what makes this a fold: if the mode ever
    grew a second answer beside the model, the two would differ here.
    """
    profile = probe[PROFILE_CASE]["file"]
    assert profile[GPIP] & GPIP_COLOUR_MONITOR, (
        "the capture profile's GPIP does not report a COLOUR monitor, so a replayer would still pick "
        "the monochrome tempo — which is the entire reason the mode serves these bytes")
    assert profile[SYNC] & SYNC_50HZ, "the capture profile's sync byte does not report 50 Hz"

    served = probe["profile_pair_under_capture"]["ledger"]
    assert served == [(GPIP, profile[GPIP]), (SYNC, profile[SYNC])], (
        "the audio-capture mode served something other than the seed it installs, so it has a read "
        "path of its own again and the two can drift")
    assert probe["profile_pair_undeclared"]["ledger"] == [(GPIP, 0), (SYNC, 0)], (
        "the profile is being served off the mode too, so the mode's fabrication has become every "
        "differential's — which is exactly what harness._vet_audio_capture_off exists to prevent")


def test_the_capture_profile_overrides_a_case_seed_and_does_not_outlive_the_mode(probe):
    """The mode's declaration wins while it is armed — which is why `emu.run` refuses a `hw_seed`
    under it rather than installing one that would be silently ignored — and is gone the moment it
    is disarmed, with no reset call, because it is installed per RUN rather than at arming.

    The leak this closes is the one the PSG file had: process-global model state carried out of a
    capture into an unrelated differential, under `pytest -n auto` unreproducibly.
    """
    profile = probe[PROFILE_CASE]["file"]
    overridden = probe["capture_overrides_a_seed"]["ledger"]
    assert overridden == [(GPIP, profile[GPIP]), (SYNC, profile[SYNC])], (
        "a case's declaration won over the capture profile, so an extractor would render the song "
        "at whatever tempo the last differential happened to declare")
    assert probe["after_capture_the_case_seed_returns"]["ledger"] == [(GPIP, OTHER), (SYNC, OTHER)], (
        "the capture profile outlived the mode: the next run was served the 50 Hz colour-ST machine "
        "instead of the bytes its own case declared, which is a fabrication leaking into a "
        "differential")


def test_the_candidate_agrees_with_the_oracle_on_a_declared_read(probe):
    """The point of the whole change: the same read, made as 68000 code and as C, produces the same
    ordered stream — which is what `harness.differential` compares."""
    assert probe["cand_declared_read"]["ledger"] == probe["declared_read"]["ledger"]
    assert probe["cand_declared_read"]["file"][GPIP] == probe["declared_read"]["file"][GPIP]


@pytest.mark.parametrize("mutant", ("cand_wrong_address", "cand_skips_the_read"))
def test_a_mutant_candidate_is_caught_by_the_ordered_stream_and_by_nothing_else(probe, mutant):
    """The negative control, and the reason the comparison is over the STREAM rather than over the
    byte each side branched on.

      * `cand_wrong_address` reads the OTHER modeled address, declared to the same byte — so the
        value it branches on is identical, its declared file is identical, and it touches no image
        byte. On a real machine it branches on the monitor when it meant the sync rate.
      * `cand_skips_the_read` hardcodes the answer, which is what a port written against a
        fabricated 0 looks like once the byte is declared: same value, no read.

    Both are green on every other surface a differential has.
    """
    correct = probe["cand_declared_read"]
    assert probe[mutant]["scalars"]["d1"] == correct["scalars"]["d1"], (
        f"{mutant}: the value it branched on already differs, so the ordered stream is not what "
        f"catches it and this case proves nothing")
    assert probe[mutant]["file"] == correct["file"], (
        f"{mutant}: the declared-byte file already differs, so the ledger is not what catches it")
    assert probe[mutant]["ledger"] != correct["ledger"], (
        f"{mutant}: the ordered read stream matches a correct run's, so the mutant would pass the "
        f"differential with every surface green")


def test_an_undeclared_read_is_recorded_on_BOTH_sides(probe):
    """Refusing on one side only is a false green (TRAP_MODEL.md): the oracle's run continues with a
    fabricated 0 while the candidate would carry on with its own. So the candidate tallies through
    `os_refused()` — the required ABI every other refusing helper uses, which
    `harness._vet_no_os_refusal` raises on — and logs the read either way, so the streams stay
    comparable.
    """
    assert probe["undeclared_read"]["scalars"]["unseeded"] == GPIP_BIT, (
        "the oracle served an undeclared address without recording it")
    cand = probe["cand_undeclared_read"]
    assert cand["scalars"]["refusals"] == 1, (
        "the candidate served an undeclared address without tallying, so a reconstruction that read "
        "one would be compared against a byte the model invented")
    assert cand["ledger"] == probe["undeclared_read"]["ledger"], (
        "the two sides log a refused read differently, so an honest case would red on the stream "
        "comparison for a reason that is not the reconstruction's")


