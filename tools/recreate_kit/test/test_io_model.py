"""Pin the DECLARED I/O MAP — both sides of it — kit-side.

The model (TRAP_MODEL.md, "Phase 15") is Phase 7 generalised in the address and nowhere else: a case
declares ANY byte of the I/O page the named models do not own, both cores serve exactly those bytes
on every read of them, an undeclared byte stays the counted-and-refusable 0 it has always been, and
the served reads land in an ordered ledger the harness compares. It is the third modeled surface
with an implementation on each shore, `oracle/shim.c` for the original and `src/hw.c` for a
reconstruction, and the two must agree exactly.

That is a KIT-WIDE property, so it is pinned here rather than in the first project to need it (the
placement rule `test_psg_model.py` and `test_hw_model.py` follow). The obstacle is the usual one:
this directory binds no project, and `harness`/`emu` both load a candidate `.so` at import, so the
oracle is unreachable from Python here. `io_model_probe.c` drives both sides in C instead — which
also lets the MUTANT cases below stand in for the reconstruction this suite does not have.

`probe_build.compile_probe` builds it from the oracle's own sources plus `src/hw.c`, so a reverted
guard reddens immediately instead of hiding behind an up-to-date-looking `liboracle.so`.
"""
import re

from pathlib import Path

import pytest

from probe_build import compile_probe, run_probe

KIT = Path(__file__).resolve().parents[1]
PROBE_SRC = Path(__file__).with_name("io_model_probe.c")
CANDIDATE_SRC = (KIT / "src" / "hw.c", KIT / "src" / "os_refusal.c")

# The addresses the probe declares, and the bytes it declares them to — its own constants, spelled
# here because the probe's C and this table are the two halves of one claim.
# `test_the_probe_addresses_are_the_registers_they_name` keeps them honest against os.h and the ROM.
SHIFTER_RESOLUTION = 0xFF8260   # what XBIOS Getrez reads: the model's founding case
PALETTE_0_HI = 0xFF8240         # ...and one colour word, which is the WIDE shape
PALETTE_0_LO = 0xFF8241
VIDEO_BASE_HI = 0xFF8201        # ...and a second single byte, so "two reads in order" is a claim
UNDECLARED_IO_ADDR = 0xFF8604   # the FDC status register, which no case here declares
MFP_GPIP = 0xFFFA01             # a Phase-7 NAMED SLOT — this model must refuse to shadow it
PSG_PORT_DATA = 0xFF8802        # ...and a byte of Phase 6's chip, likewise

RESOLUTION_MONO = 0x02          # bits 0-1 = 2: the ST's monochrome mode, which Getrez reports
PALETTE_HI_BYTE = 0x07
PALETTE_LO_BYTE = 0x77
VIDEO_BASE_BYTE = 0x03
OTHER_BYTE = 0xA5
FABRICATED = 0x00               # what an UNDECLARED I/O byte is served: unchanged since the kit's
                                # first run, counted rather than refused here (see `undeclared_read`)

# The four addresses almost every case declares — the probe's ALL_ADDRS/ALL_VALUES.
ALL_DECLARED = 4
# The 68000's three access widths, as os.h records them in a ledger entry: a BYTE COUNT.
BYTE, WORD, LONG = 1, 2, 4

# The declared-map size the CAP case must produce. Read from os.h rather than restated, because the
# claim is "one past the cap is dropped" and a hardcoded 256 would go on passing if the cap moved.
IO_SEED_MAX = int(re.search(r"^#define\s+OS_IO_SEED_MAX\s+(\d+)",
                            (KIT / "include" / "os.h").read_text(), re.M).group(1))


def _scalars(*, d1=0, declared=ALL_DECLARED, unmodeled=0, unmodeled_first=0, stale=0, stale_first=0,
             hw_unseeded=0, hw_nlog=0, nlog=0):
    """One oracle case's whole scalar claim, with the quiet defaults named once.

    Nine keys and most cases are about one of them, so spelling every row in full would bury the one
    that matters in eight zeros — and a row that quietly omitted a key would stop measuring it (see
    `test_every_probe_key_is_claimed_by_some_case`). The defaults are the SILENT state: nothing
    unmodeled, nothing stale, the named set untouched.
    """
    return {"d1": d1, "declared": declared, "unmodeled": unmodeled,
            "unmodeled_first": unmodeled_first, "stale": stale, "stale_first": stale_first,
            "hw_unseeded": hw_unseeded, "hw_nlog": hw_nlog, "nlog": nlog}


# One entry per case the probe runs. `scalars` are exact; `ledger` is the ordered
# (address, width, value) stream of SERVED reads — which is the ENTIRE observable effect of such a
# read, since it touches no image byte and a routine that reads a register only to clear it leaves
# no register behind either.
#
# THE TABLE IS THE ASSERTION, and each row's comment is its argument. A narrative test below is kept
# only where it pins something no row can: a relation BETWEEN cases (the two sides agreeing, a mutant
# separated from a correct run) or a fact about the SOURCE rather than about a run.
ORACLE_CASES = {
    # An address the case DECLARED reads back as declared, and declaring it is not consumed by one
    # run — the declaration is the run's entry state, re-installed each time, not a one-shot. Nor
    # does it SURVIVE one: withdraw it (`undeclared_read`, over the identical image and the
    # identical routine) and the read is the counted 0 again. Without that per-run reinstall a case
    # could be verified against a byte another case declared, and under `pytest -n auto` which case
    # that is would not be stable.
    "declared_read": dict(scalars=_scalars(d1=RESOLUTION_MONO, nlog=1),
                          ledger=[(SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)]),
    "declared_read_again": dict(scalars=_scalars(d1=RESOLUTION_MONO, nlog=1),
                                ledger=[(SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)]),
    # ...and withdrawing it restores the fabrication, WITH THE TALLY THAT MAKES IT REFUSABLE. This
    # row is the model's contract with `emu.run`, kept verbatim from Phase 7: the read is served the
    # same 0 the shim answered before this model existed — so a bare `emu.run` driving a boot is
    # unchanged, which is what keeps this whole model free for every project that declares nothing —
    # and only RECORDED, which is what lets `harness._vet_rom_io_reads_are_modelled` refuse it.
    # It is NOT ledgered: the candidate refuses its own read and logs nothing either, so an entry
    # here would diverge the streams for a reason that is not about this read.
    "undeclared_read": dict(scalars=_scalars(d1=FABRICATED, declared=0, unmodeled=1,
                                             unmodeled_first=SHIFTER_RESOLUTION),
                            ledger=[]),
    # A declared byte read TWICE is served twice and ledgered twice, and that is the model's stated
    # LIMIT rather than an oversight. Phase 7 refuses a second read of a VOLATILE slot because the
    # machine changes it between reads; here every declaration is a per-run CONSTANT by definition,
    # and a register whose two reads must DIFFER — an FDC status poll, a DMA counter — is Phase 8's
    # shape and not this one's. The row is what says a "fix" adding a re-read refusal would be a
    # change to the model rather than a repair.
    "declared_read_twice": dict(scalars=_scalars(d1=RESOLUTION_MONO, nlog=2),
                                ledger=[(SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO),
                                        (SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)]),
    # The ORDER of two reads, which is the whole of what the ledger comparison adds over the value:
    # a reconstruction that read the same two addresses the other way round computes the same
    # result from the same bytes and is separable by nothing else.
    "two_reads_in_order": dict(scalars=_scalars(d1=RESOLUTION_MONO, nlog=2),
                               ledger=[(VIDEO_BASE_HI, BYTE, VIDEO_BASE_BYTE),
                                       (SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)]),
    # A WORD IS TWO DECLARED BYTES, big-endian, in ONE ledger entry of width 2. This is the honest
    # generalisation of Phase 7's wide-read refusal: there the neighbouring register could not be
    # described at all so the access had to be refused, here it can be, so a case that declared both
    # bytes has said what the word holds.
    "word_read_both_bytes_declared": dict(
        scalars=_scalars(d1=PALETTE_HI_BYTE << 8 | PALETTE_LO_BYTE, nlog=1),
        ledger=[(PALETTE_0_HI, WORD, PALETTE_HI_BYTE << 8 | PALETTE_LO_BYTE)]),
    # ...and ALL OR NOTHING is the other half of it: declare the high byte alone and the whole access
    # is refused, with the tally naming the byte that is MISSING ($ff8241) rather than the address
    # the access started at. Serving the half it had would fabricate the other half, which is the
    # class this model exists to close — and the ledger must stay EMPTY, or the candidate (which
    # refuses whole) would be a half-entry short.
    "word_read_half_declared": dict(scalars=_scalars(d1=FABRICATED, declared=2, unmodeled=1,
                                                     unmodeled_first=PALETTE_0_LO),
                                    ledger=[]),
    # ...and a LONG read, served when all four bytes are declared. BOTH sides spell this width: the
    # oracle decodes whatever the ROM really executes and `io_read32` is what a reconstruction of
    # that instruction calls, so `cand_long_read` below must produce this very entry.
    "long_read_all_four_declared": dict(
        scalars=_scalars(d1=(PALETTE_HI_BYTE << 24 | PALETTE_LO_BYTE << 16 | OTHER_BYTE << 8
                             | RESOLUTION_MONO), declared=4, nlog=1),
        ledger=[(PALETTE_0_HI, LONG, PALETTE_HI_BYTE << 24 | PALETTE_LO_BYTE << 16
                 | OTHER_BYTE << 8 | RESOLUTION_MONO)]),
    # THE STALENESS RULE, which is Phase 7's at an address-keyed model: the run stored to the byte
    # and then read it back, so the declaration describes a machine an instruction of this very run
    # has already changed. The read is still SERVED and still ledgered — both sides do the same
    # thing, so the streams agree — and the refusal is the harness's, on the tally.
    "write_then_read": dict(scalars=_scalars(d1=RESOLUTION_MONO, stale=1,
                                             stale_first=SHIFTER_RESOLUTION, nlog=1),
                            ledger=[(SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)]),
    # ...while a write NOTHING reads back is the ordinary invisible hardware write it always was:
    # dropped, ledgered by Phase 10, and no business of this model's.
    "write_only": dict(scalars=_scalars(), ledger=[]),
    # ...and the staleness note is PER RUN. Without the clear, one case's store would refuse every
    # later case that reads the same byte — under `pytest -n auto`, unpredictably.
    "after_the_write_the_next_run_is_clean": dict(
        scalars=_scalars(d1=RESOLUTION_MONO, nlog=1),
        ledger=[(SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)]),
    # THE WRITE-THROUGH ARM. A marked declaration says the register LATCHES what the run stores and
    # reads it back, so the store REPLACES what a later read is served — which is how a routine that
    # writes a register and re-reads it becomes an ordinary differential instead of the staleness
    # refusal above. Nothing is fabricated by it: the byte served is one the run itself produced,
    # identically on both shores. `stale` stays 0, which is the row's other half — a marked byte is
    # not a declaration the run invalidated.
    "write_through_read_back": dict(scalars=_scalars(d1=OTHER_BYTE, nlog=1),
                                    ledger=[(SHIFTER_RESOLUTION, BYTE, OTHER_BYTE)]),
    # ...and a marked byte the run never stores to is an ORDINARY declaration, served the byte the
    # case declared. It is also the per-run reset, over the run that follows the store above: the
    # live byte is re-copied from the declaration at the top of every run, so one case's store
    # cannot reach the next — under `pytest -n auto`, unpredictably which.
    "write_through_never_stored_reads_the_declaration": dict(
        scalars=_scalars(d1=RESOLUTION_MONO, nlog=1),
        ledger=[(SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)]),
    # ...and the STORE-AND-VERIFY loop the arm exists for, which is the MFP timer programmer's own
    # shape: store, read back, go round again until the chip agrees. ONE read in the ledger is the
    # claim — the loop ran once — and it is what pins a reconstruction's loop SHAPE to the ROM's:
    # one that read twice, or that never read, produces a different stream. Undeclared the compare
    # can never come true and the run dies at the instruction cap; declared as a per-run CONSTANT it
    # dies there too. Terminating at all is the arm's doing.
    "write_through_store_and_verify_loop": dict(scalars=_scalars(d1=0, nlog=1),
                                                ledger=[(SHIFTER_RESOLUTION, BYTE, OTHER_BYTE)]),
    # ...and a WIDE store straddling a MARKED byte and an unmarked one. Each covered byte gets its
    # own answer — the marked half latches, the unmarked half keeps its declaration AND goes stale —
    # so the word read after it is half what the run wrote and half what the case declared. A store
    # that latched the whole access would serve both halves the written word and the staleness tally
    # would be empty; both halves of that are measured here.
    "a_wide_store_straddles_a_marked_byte_and_an_unmarked_one": dict(
        scalars=_scalars(d1=OTHER_BYTE << 8 | PALETTE_LO_BYTE, declared=2, stale=1,
                         stale_first=PALETTE_0_LO, nlog=1),
        ledger=[(PALETTE_0_HI, WORD, OTHER_BYTE << 8 | PALETTE_LO_BYTE)]),
    # PRECEDENCE, and the whole of what "must not be double-modelled" means: a Phase-7 named slot
    # offered here is NOT installed (four of the five declarations land), and a read of it still
    # reaches Phase 7 — `hw_unseeded` names it and the NAMED set's ledger has the entry, while this
    # model's stays empty. Were it installed, one model would serve the byte while the other's rules
    # (the volatile re-read, the model default, the split-register exemption) went unenforced.
    "named_slot_is_not_shadowed": dict(scalars=_scalars(d1=FABRICATED, hw_unseeded=1 << 0,
                                                        hw_nlog=1),
                                       ledger=[]),
    # ...and a WRITE-THROUGH mark buys no admission. The same five declarations with the named slot
    # marked still install four, so a case cannot reach past `os_io_seedable` by claiming a register
    # latches — the mark qualifies a declaration this model accepted, it does not make one.
    "a_named_slot_marked_write_through_is_still_not_installed": dict(
        scalars=_scalars(d1=FABRICATED, hw_unseeded=1 << 0, hw_nlog=1), ledger=[]),
    # ...and the same for the YM2149's block, which Phase 6 owns along with two refusals of its own.
    # Only the INSTALL is measured here: what a read of the chip's ports does is another model's
    # subject, and this row's claim is that such a byte never enters this map at all.
    "psg_port_is_not_declarable": dict(scalars=_scalars(declared=1), ledger=[]),
    # ...and an address BELOW the I/O page, which is ordinary off-image memory: it has read 0 since
    # the kit's first run, no model declares it, and an address down there is a defect in the case.
    "an_address_below_the_page_is_not_declarable": dict(scalars=_scalars(declared=1), ledger=[]),
    # ...and an UNTRANSLATED spelling of a register that IS in the page ($ffff8260, which the
    # 68000's 24 address lines fold onto $ff8260 before anything decodes it). Every read reaches the
    # rule in the folded form, so a row keyed on the long one serves nothing while the case believes
    # its byte is declared — a declaration no read can ever match, which is why `os_io_is_page`
    # bounds the bus before it tests the page. emu.py refuses such a key by name; this row is the C
    # shore's own rule, which a caller that never goes through emu.py reaches instead.
    "an_untranslated_address_is_not_declarable": dict(scalars=_scalars(declared=1), ledger=[]),
    # A DUPLICATE is installed ONCE and the FIRST value wins. A Python caller cannot produce one (a
    # dict has one value per key) but the C ABI can, and without the check the map's size would
    # disagree with the case's — which is exactly what `emu.run` compares to catch the two shores'
    # rules drifting.
    "a_duplicate_declaration_is_installed_once": dict(
        scalars=_scalars(d1=RESOLUTION_MONO, declared=1, nlog=1),
        ledger=[(SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)]),
    # ...and one entry past OS_IO_SEED_MAX is DROPPED rather than written past the array. The
    # shortfall is what both callers report — `emu.run` raises on it, the candidate charges a
    # refusal — so a map that did not fit is loud rather than a run served fewer bytes than it asked.
    "one_past_the_cap_is_dropped": dict(scalars=_scalars(declared=IO_SEED_MAX), ledger=[]),
    # The declaration is per-RUN state and the BENCH shares it: both entry points go through
    # `enter_from_reset`, so a bench run starts from the case's map with an empty ledger. Without
    # that, a perf measurement would run against whatever the last differential left.
    "bench_starts_from_the_declaration": dict(scalars=_scalars(), ledger=[]),
}

# ...and the CANDIDATE's side, driven through `src/hw.c` exactly as `harness.differential` drives it.
# `d1` is what the body returned, `refusals` the `os_refused()` tally the harness throws a case away
# on, `declared` the map size, `nlog` the ledger's length.
CANDIDATE_CASES = {
    # The faithful reconstruction: it reads the declared byte, refuses nothing, and logs the read.
    "cand_declared_read": dict(scalars={"d1": RESOLUTION_MONO, "refusals": 0,
                                        "declared": ALL_DECLARED, "nlog": 1},
                               ledger=[(SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)]),
    # MUTANT: it never reads and hardcodes the answer — what a port written against a fabricated 0
    # looks like once the byte is declared. Its ledger is empty where the oracle's has an entry.
    "cand_skips_the_read": dict(scalars={"d1": RESOLUTION_MONO, "refusals": 0,
                                         "declared": ALL_DECLARED, "nlog": 0},
                                ledger=[]),
    # An address in no declaration REFUSES and is NOT ledgered — the oracle records nothing for it
    # either (it counts an unmodeled read and answers 0), so an entry here would diverge the streams
    # for a reason that is not about this read.
    "cand_undeclared_read": dict(scalars={"d1": 0, "refusals": 1, "declared": ALL_DECLARED,
                                          "nlog": 0},
                                 ledger=[]),
    # A WORD read of two declared bytes: one entry of width 2, big-endian — the same entry the
    # oracle's own `move.w` produces, which is what makes the two streams comparable at all.
    "cand_palette_word": dict(scalars={"d1": PALETTE_HI_BYTE << 8 | PALETTE_LO_BYTE, "refusals": 0,
                                       "declared": ALL_DECLARED, "nlog": 1},
                              ledger=[(PALETTE_0_HI, WORD, PALETTE_HI_BYTE << 8 | PALETTE_LO_BYTE)]),
    # MUTANT: two byte reads where the original made one word read. It computes the IDENTICAL value
    # from the IDENTICAL declared bytes and touches no image byte, so the width in the ledger entry
    # is the only thing that separates it — which is why the entry carries one.
    "cand_palette_as_two_bytes": dict(
        scalars={"d1": PALETTE_HI_BYTE << 8 | PALETTE_LO_BYTE, "refusals": 0,
                 "declared": ALL_DECLARED, "nlog": 2},
        ledger=[(PALETTE_0_HI, BYTE, PALETTE_HI_BYTE), (PALETTE_0_LO, BYTE, PALETTE_LO_BYTE)]),
    # The wrong-address pair, against a declaration giving BOTH addresses the same byte: the value
    # returned, the map and the (empty) image effect are a correct run's exactly. See
    # `test_the_wrong_address_mutant_differs_from_a_correct_run_only_in_the_ledger`.
    "cand_twinned_right_address": dict(scalars={"d1": RESOLUTION_MONO, "refusals": 0, "declared": 2,
                                                "nlog": 1},
                                       ledger=[(SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)]),
    "cand_twinned_wrong_address": dict(scalars={"d1": RESOLUTION_MONO, "refusals": 0, "declared": 2,
                                                "nlog": 1},
                                       ledger=[(VIDEO_BASE_HI, BYTE, RESOLUTION_MONO)]),
    # The LONG read's candidate half: ONE entry of width 4, big-endian, matching the oracle's own
    # `move.l` above. Without `io_read32` a faithful port of that instruction had no spelling at all.
    "cand_long_read": dict(
        scalars={"d1": (PALETTE_HI_BYTE << 24 | PALETTE_LO_BYTE << 16 | OTHER_BYTE << 8
                        | RESOLUTION_MONO), "refusals": 0, "declared": 4, "nlog": 1},
        ledger=[(PALETTE_0_HI, LONG, PALETTE_HI_BYTE << 24 | PALETTE_LO_BYTE << 16
                 | OTHER_BYTE << 8 | RESOLUTION_MONO)]),
    # MUTANT: two word reads where the original made one long read. It computes the IDENTICAL value
    # from the IDENTICAL declared bytes, so — as with the byte/word pair above — the entry's WIDTH is
    # the only thing that separates it.
    "cand_long_read_as_two_words": dict(
        scalars={"d1": (PALETTE_HI_BYTE << 24 | PALETTE_LO_BYTE << 16 | OTHER_BYTE << 8
                        | RESOLUTION_MONO), "refusals": 0, "declared": 4, "nlog": 2},
        ledger=[(PALETTE_0_HI, WORD, PALETTE_HI_BYTE << 8 | PALETTE_LO_BYTE),
                (PALETTE_0_HI + 2, WORD, OTHER_BYTE << 8 | RESOLUTION_MONO)]),
    # A HALF-declared word refuses WHOLE rather than serving the byte it does have — the oracle's
    # own rule, so that a case missing one declaration fails on both shores at once.
    "cand_word_half_declared": dict(scalars={"d1": 0, "refusals": 1, "declared": 2, "nlog": 0},
                                    ledger=[]),
    # `g_io_reset` really clears: a case declaring nothing must not read through the previous one's
    # map. That is the same false green the per-run reinstall closes on the oracle's side.
    "cand_declaration_does_not_leak": dict(scalars={"d1": 0, "refusals": 1, "declared": 0,
                                                    "nlog": 0},
                                           ledger=[]),
    # The WRITE-THROUGH arm on the candidate shore, which must serve what the oracle's rows above
    # serve: `cand_write_through_read_back`'s entry is `write_through_read_back`'s, byte for byte
    # (`test_the_two_sides_serve_the_same_byte_for_the_same_declaration` compares them).
    "cand_write_through_read_back": dict(scalars={"d1": OTHER_BYTE, "refusals": 0,
                                                  "declared": ALL_DECLARED, "nlog": 1},
                                         ledger=[(SHIFTER_RESOLUTION, BYTE, OTHER_BYTE)]),
    # ...and a marked byte never stored to is an ordinary declaration on this side too.
    "cand_write_through_never_stored": dict(scalars={"d1": RESOLUTION_MONO, "refusals": 0,
                                                     "declared": ALL_DECLARED, "nlog": 1},
                                            ledger=[(SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)]),
    # MUTANT: it reads BEFORE it stores, so it is served the ENTRY byte where the original was
    # served what it had just written — which is exactly what a port written against the model
    # WITHOUT this arm does. Same address, same width, same store: only the VALUE separates it.
    "cand_write_through_read_before_store": dict(
        scalars={"d1": RESOLUTION_MONO, "refusals": 0, "declared": ALL_DECLARED, "nlog": 1},
        ledger=[(SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)]),
    # MUTANT: it stores a DIFFERENT byte, which the register latches — so one wrong store moves both
    # the write ledger's value and the read ledger's.
    "cand_write_through_stores_another_value": dict(
        scalars={"d1": RESOLUTION_MONO, "refusals": 0, "declared": ALL_DECLARED, "nlog": 1},
        ledger=[(SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)]),
    # ...and the SAME store against an UNMARKED declaration keeps today's rule verbatim: the read is
    # served the byte the case declared, on both shores, and the refusal is the harness's on the
    # oracle's staleness tally. This is the row that says the arm is opt-in per address.
    "cand_unmarked_write_then_read": dict(scalars={"d1": RESOLUTION_MONO, "refusals": 0,
                                                   "declared": ALL_DECLARED, "nlog": 1},
                                          ledger=[(SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)]),
    # ...and the WIDE store straddling the two rules: half latched, half declared.
    "cand_wide_store_straddle": dict(
        scalars={"d1": OTHER_BYTE << 8 | PALETTE_LO_BYTE, "refusals": 0, "declared": 2, "nlog": 1},
        ledger=[(PALETTE_0_HI, WORD, OTHER_BYTE << 8 | PALETTE_LO_BYTE)]),
    # ...and a declaration os.h's rule REJECTED charges a refusal on this side too — offered with
    # the four ordinary ones, so "four of five installed" is the measurement rather than "none of
    # one" — which is what stops a case that bypassed `emu.seed_split` from running against a map
    # quietly smaller than the one it wrote.
    "cand_rejected_declaration": dict(scalars={"d1": RESOLUTION_MONO, "refusals": 1,
                                               "declared": ALL_DECLARED, "nlog": 1},
                                      ledger=[(SHIFTER_RESOLUTION, BYTE, RESOLUTION_MONO)]),
}

EXPECTED = {**ORACLE_CASES, **CANDIDATE_CASES}


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    """Build and run the probe once; return {case: {"scalars", "ledger", "file"}}."""
    return run_probe(compile_probe(PROBE_SRC, tmp_path_factory.mktemp("io_model"), CANDIDATE_SRC))


def test_the_probe_reports_every_case(probe):
    """Guard the fixture itself: a probe that stopped printing (or a parse that stopped matching)
    would make every assertion below vacuously pass."""
    assert set(probe) == set(EXPECTED), (
        f"probe cases and expectations disagree — only in probe: {sorted(set(probe) - set(EXPECTED))}"
        f", only in EXPECTED: {sorted(set(EXPECTED) - set(probe))}")


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_the_case_reports_what_the_model_promises(probe, case):
    """Every scalar the case claims, exactly."""
    assert probe[case]["scalars"] == EXPECTED[case]["scalars"], (
        f"{case}: the model reported {probe[case]['scalars']}, not {EXPECTED[case]['scalars']}")


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_the_case_logs_the_read_stream_it_promises(probe, case):
    """The ordered SERVED-read stream. It is the WHOLE observable effect of a declared read: the
    access touches no image byte, and a routine that reads a register only to clear it leaves no
    register behind either."""
    assert probe[case]["ledger"] == EXPECTED[case]["ledger"], (
        f"{case}: the ledger is {probe[case]['ledger']}, not {EXPECTED[case]['ledger']}")


def test_every_probe_key_is_claimed_by_some_case(probe):
    """A scalar the probe prints that NO case claims would otherwise be measured by nothing.

    The case above compares the whole dict, so this direction is already covered for the keys a row
    names — what it adds is the ORACLE/CANDIDATE split: the two reports print different key sets, and
    a key added to one `report_*` and to none of that half's rows would surface here as a mismatch
    in the row rather than as a whole surface shipping unpinned.
    """
    for case, reported in sorted(probe.items()):
        assert set(reported["scalars"]) == set(EXPECTED[case]["scalars"]), (
            f"{case}: the probe prints {sorted(reported['scalars'])} but the table claims "
            f"{sorted(EXPECTED[case]['scalars'])}. A key on one side only is a surface nothing "
            f"measures")


def test_the_two_sides_serve_the_same_byte_for_the_same_declaration(probe):
    """The relation the whole model rests on, which no single row states: given ONE declaration, the
    oracle's read and the candidate's produce the same ledger entry.

    `harness._vet_io_state` compares exactly these two streams on every case, so a drift between the
    two implementations would surface there as a reconstruction bug — the hardest kind to diagnose,
    because the reconstruction is correct.
    """
    assert probe["declared_read"]["ledger"] == probe["cand_declared_read"]["ledger"], (
        "the oracle and the candidate served different entries for the same declared byte — the two "
        "implementations of one model have drifted")
    assert (probe["word_read_both_bytes_declared"]["ledger"]
            == probe["cand_palette_word"]["ledger"]), (
        "the oracle's word read and the candidate's io_read16 produced different entries, so a "
        "faithful reconstruction of a `move.w` would red against a correct oracle")
    assert (probe["long_read_all_four_declared"]["ledger"] == probe["cand_long_read"]["ledger"]), (
        "the oracle's long read and the candidate's io_read32 produced different entries, so a "
        "faithful reconstruction of a `move.l` would red against a correct oracle")
    assert (probe["write_through_read_back"]["ledger"]
            == probe["cand_write_through_read_back"]["ledger"]), (
        "the oracle latched a store the candidate's hw_write8 did not (or the other way round) — a "
        "faithful reconstruction of a store-and-verify loop would red against a correct oracle, and "
        "the WRITE-THROUGH column is the one rule the two shores must decode alike")
    assert (probe["a_wide_store_straddles_a_marked_byte_and_an_unmarked_one"]["ledger"]
            == probe["cand_wide_store_straddle"]["ledger"]), (
        "the two shores split a wide store across the marked and unmarked halves differently")


def test_the_wrong_address_mutant_differs_from_a_correct_run_only_in_the_ledger(probe):
    """The negative control that says WHY the ledger is compared at all.

    Both cases declare two addresses to the SAME byte, so the mutant returns the same value from the
    same map and touches no image byte. Every surface a differential has is identical except the
    ordered stream — which is the whole argument for keeping one.
    """
    right, wrong = probe["cand_twinned_right_address"], probe["cand_twinned_wrong_address"]
    assert right["scalars"] == wrong["scalars"], (
        "the two cases were supposed to be indistinguishable outside the ledger, so this case is no "
        "longer measuring what it claims")
    assert right["ledger"] != wrong["ledger"], (
        "a candidate reading the WRONG declared address produced the same ledger as a correct one — "
        "nothing in a differential could tell them apart")


def test_the_mark_is_what_changes_the_byte_a_read_back_is_served(probe):
    """The arm's whole claim, as the relation no single row states: ONE candidate body, TWO
    declarations, two different answers.

    `cand_write_through_read_back` and `cand_unmarked_write_then_read` run the SAME store-then-read
    core against the same four addresses and the same four bytes; the only difference is the
    write-through column. Marked, the read is served what the core stored; unmarked, it is served
    what the case declared — which is the behaviour every existing case keeps, and is why adding the
    arm changed no project's suite.
    """
    marked, unmarked = probe["cand_write_through_read_back"], probe["cand_unmarked_write_then_read"]
    assert marked["scalars"]["nlog"] == unmarked["scalars"]["nlog"] == 1, (
        "the two cases no longer make one read each, so they are not the same core any more")
    assert marked["ledger"] != unmarked["ledger"], (
        "the write-through column changed nothing about what a read back is served — the arm is "
        "not load-bearing, and every case above would pass without it")
    assert unmarked["ledger"] == probe["cand_declared_read"]["ledger"], (
        "an UNMARKED declaration no longer serves the byte the case declared, so the arm is not "
        "opt-in per address and every already-ported project's map has changed meaning")


def test_the_probe_addresses_are_the_registers_they_name():
    """The addresses this file spells must be the ones the models really own, or every row above is
    about the wrong register while still comparing equal.

    Parsed rather than imported: `os_map` holds no copy of the hardware table (emu.py reads it from
    the .so), and this suite runs in a bare checkout. Only the two the OTHER models own are pinned
    against os.h — the rest are ST registers, whose addresses are the machine's and are named in the
    probe's own comments.
    """
    source = (KIT / "include" / "os.h").read_text()
    defines = dict(re.findall(r"^#define\s+(OS_\w+)\s+(0x[0-9a-fA-F]+|\d+)u?", source, re.M))
    assert int(defines["OS_HW_MFP_GPIP"], 0) == MFP_GPIP, (
        "the Phase-7 slot this suite offers to the I/O map has moved, so the precedence case is "
        "declaring an ordinary address and passing for the wrong reason")
    assert int(defines["OS_PSG_PORT_DATA"], 0) == PSG_PORT_DATA
    assert int(defines["OS_HW_IO_PAGE"], 0) <= SHIFTER_RESOLUTION, (
        "the addresses this suite declares are below the I/O page, so every 'declared' row is "
        "really measuring the rejection path")


def test_the_admissible_set_is_the_refused_set():
    """The pairing the model's honesty rests on, pinned over the SOURCE because no run can show it.

    `io_serve` counts an unmodeled read for every byte at or above `os_io_is_page`, and
    `os_io_seedable` admits a declaration over the same predicate. Were the two spelled separately —
    a seed limited to the three DECODED blocks, say, while the tally covered the whole page — an
    address in the gap between them would be refused by `_vet_rom_io_reads_are_modelled` with no
    declaration able to answer it: a refusal whose remedy does not exist, which is worse than the
    silent 0 it replaced. One predicate is what makes that impossible, and this is the check that
    fires the day someone narrows one of them.
    """
    source = (KIT / "include" / "os.h").read_text()
    seedable = re.search(r"os_io_seedable\(uint32_t bus_addr\) \{(.*?)\n\}", source, re.S)
    assert seedable, "os_io_seedable is not where this pin looks for it"
    assert "os_io_is_page(bus_addr)" in seedable.group(1), (
        "os_io_seedable no longer derives its page test from os_io_is_page, so the set a case may "
        "declare and the set the refusal fires on can now drift apart")

    shim = (KIT / "oracle" / "shim.c").read_text()
    serve = re.search(r"static int io_serve\(.*?\n\}", shim, re.S)
    assert serve, "io_serve is not where this pin looks for it"
    assert "os_io_is_page(lo)" in serve.group(0), (
        "the oracle's serve path no longer gates on os_io_is_page, so it may be counting unmodeled "
        "reads over a different range than a case can declare")
