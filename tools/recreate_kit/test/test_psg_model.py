"""Pin the SEEDED PSG READ MODEL — both sides of it — kit-side.

The model (TRAP_MODEL.md, "Phase 6") makes a read-modify-write of the YM2149 runnable: a byte read
of `$ff8800` is answered from a register file the CASE seeds, and a register nothing declared and
nothing wrote is refused rather than invented. It is the one modeled surface with an implementation
on each shore — `oracle/shim.c` for the original, `src/psg.c` for a reconstruction — and the two must
agree exactly, because `harness.differential` compares their ledgers and their register files.

That is a KIT-WIDE property, so it is pinned here rather than in the first project to need it (the
placement rule `test_os_map.py` and `test_entry_state.py` follow). The obstacle is the usual one:
this directory binds no project, and `harness`/`emu` both load a candidate `.so` at import, so the
oracle is unreachable from Python here. `psg_model_probe.c` drives both sides in C instead — which
also lets the two MUTANT cases below stand in for the reconstruction this suite does not have.

`probe_build.compile_probe` builds it from the oracle's own sources plus `src/psg.c`, so a reverted
guard reddens immediately instead of hiding behind an up-to-date-looking `liboracle.so`.
"""
import re
import subprocess
import sys

from pathlib import Path

import pytest

from probe_build import compile_probe

KIT = Path(__file__).resolve().parents[1]
PROBE_SRC = Path(__file__).with_name("psg_model_probe.c")
CANDIDATE_SRC = (KIT / "src" / "psg.c", KIT / "src" / "os_refusal.c")

sys.path.insert(0, str(KIT.parent))                   # reverse/tools, so `recreate_kit` imports
from recreate_kit import os_map   # noqa: E402  (importable with nothing built, unlike harness/emu)

# The chip's register count and the ledger's event kinds, from the one Python mirror of os.h that a
# bare checkout can import (test_os_memory_map.py pins both against the C). The probe prints one F
# line per register and one L line per event.
NREGS = os_map.OS_PSG_NREGS
WRITE = os_map.OS_PSG_EVENT_WRITE
READ = os_map.OS_PSG_EVENT_READ
MIXER = 7                     # the register every case works on (the mixer / port-direction byte)
DECOY = 8                     # ...and the one the transposed-read mutant reads INSTEAD, seeded to
                              # the same byte, so only the ledger's read entry separates the two
SEED = 0xC0                   # what the case declares the chip held: the two port-DIRECTION bits
SILENCE = 0x3F                # the `ori.b #$3f` a silencing routine merges in
SILENCED = SEED | SILENCE     # 0xff — what the read-modify-write must produce
FABRICATED = SILENCE          # what the SAME routine produces if the read is answered 0: the false
                              # green the model exists to prevent, and mutant 2's output
WRITTEN = 0x0A                # the write-then-read-back case's value
LEAK_PROBE = 10               # the register the arm-from-off leak case selects, then must lose
UNSELECTED = 0                # where a bare data write lands when nothing selected a register
MIXER_BIT = 1 << MIXER
DECOY_BIT = 1 << DECOY


def _file(**registers):
    """The expected register file: every register 0 but the ones named."""
    return {reg: registers.get(f"r{reg}", 0) for reg in range(NREGS)}


# One entry per case the probe runs. `scalars` are exact; `ledger` is the ordered (kind, reg, value)
# stream — READS INCLUDED, which is what separates a transposed read-modify-write from a correct one;
# `file` is the whole modeled register file, so a case cannot claim one byte and leave the other
# fifteen unwatched.
EXPECTED = {
    # A register the case DECLARED reads back as declared, and declaring it is not consumed by one
    # run — the seed is the run's entry state, re-installed each time, not a one-shot.
    "seeded_read": dict(scalars={"d1": SEED, "unseeded": 0, "no_select": 0, "unmodeled": 0,
                                 "known": MIXER_BIT, "nlog": 1},
                        ledger=[(READ, MIXER, SEED)], file=_file(r7=SEED)),
    "seeded_read_again": dict(scalars={"d1": SEED, "unseeded": 0, "no_select": 0, "unmodeled": 0,
                                       "known": MIXER_BIT, "nlog": 1},
                              ledger=[(READ, MIXER, SEED)], file=_file(r7=SEED)),
    # ...and withdrawing it restores the refusal: the read is served 0 (the run continues, exactly as
    # a refused trap does) but `unseeded` names register 7, which is what makes emu.run reject it.
    "unseeded_read": dict(scalars={"d1": 0, "unseeded": MIXER_BIT, "no_select": 0, "unmodeled": 0,
                                   "known": 0, "nlog": 1},
                          ledger=[(READ, MIXER, 0)], file=_file()),
    # A read with nothing selected: refused in its OWN tally, and seeding cannot help — the case is
    # missing an instruction, not a declaration. The register 7 the seed declares is beside the point,
    # which is why the seed is left in place here.
    "read_before_any_select": dict(scalars={"d1": 0, "unseeded": 0, "no_select": 1, "unmodeled": 0,
                                            "known": MIXER_BIT, "nlog": 1},
                                   ledger=[(READ, UNSELECTED, 0)], file=_file(r7=SEED)),
    # A select whose upper nibble is set. UNMODELED, not masked down to register 14 — and the latch is
    # left alone, so nothing about the chip changed.
    "high_nibble_select": dict(scalars={"d1": 0, "unseeded": 0, "no_select": 0, "unmodeled": 1,
                                        "known": MIXER_BIT, "nlog": 0},
                               ledger=[], file=_file(r7=SEED)),
    # The routine the whole model exists for — Wonder Boy's snd_psg_silence in four instructions.
    "rmw": dict(scalars={"d1": SILENCED, "unseeded": 0, "no_select": 0, "unmodeled": 0,
                         "known": MIXER_BIT, "nlog": 2},
                ledger=[(READ, MIXER, SEED), (WRITE, MIXER, SILENCED)], file=_file(r7=SILENCED)),
    # The same routine with the seed withdrawn. Its own write still lands, so the FILE is not empty —
    # but the read that came first was refused, and the value it merged is the fabricated one.
    "rmw_unseeded": dict(scalars={"d1": FABRICATED, "unseeded": MIXER_BIT, "no_select": 0,
                                  "unmodeled": 0, "known": MIXER_BIT, "nlog": 2},
                         ledger=[(READ, MIXER, 0), (WRITE, MIXER, FABRICATED)],
                         file=_file(r7=FABRICATED)),
    # The same routine again with the DECOY register declared alongside the mixer, holding the same
    # byte — the run the transposed-read mutant below has to be told apart from.
    "rmw_two_seeded": dict(scalars={"d1": SILENCED, "unseeded": 0, "no_select": 0, "unmodeled": 0,
                                    "known": MIXER_BIT | DECOY_BIT, "nlog": 2},
                           ledger=[(READ, MIXER, SEED), (WRITE, MIXER, SILENCED)],
                           file=_file(r7=SILENCED, r8=SEED)),
    # The same reset reached through osh_run_bench, the oracle's OTHER entry point: it lives in
    # enter_from_reset, which both share, so a bench after a seeded run starts from the SEED rather
    # than from that run's leftovers ($c0 back in register 7, not the $ff `rmw_two_seeded` wrote).
    "bench_after_a_seeded_run": dict(scalars={"d1": 0, "unseeded": 0, "no_select": 0,
                                              "unmodeled": 0,
                                              "known": MIXER_BIT | DECOY_BIT, "nlog": 0},
                                     ledger=[], file=_file(r7=SEED, r8=SEED)),
    # A register this run wrote itself needs no seed: the chip reads back its own store.
    "write_then_read": dict(scalars={"d1": WRITTEN, "unseeded": 0, "no_select": 0, "unmodeled": 0,
                                     "known": MIXER_BIT, "nlog": 2},
                            ledger=[(WRITE, MIXER, WRITTEN), (READ, MIXER, WRITTEN)],
                            file=_file(r7=WRITTEN)),
    # The ordered ledger over a write-only run: same register twice keeps both entries in order, and
    # a written 0 is recorded (and marks the register known) where "never written" does not. This is
    # the regression pin every psg_writes() consumer rests on — its WRITE projection must not move.
    "write_only": dict(scalars={"d1": 0, "unseeded": 0, "no_select": 0, "unmodeled": 0,
                                "known": (1 << 0) | MIXER_BIT | (1 << LEAK_PROBE), "nlog": 4},
                       ledger=[(WRITE, 0, 0x11), (WRITE, MIXER, SILENCE), (WRITE, MIXER, 0x0F),
                               (WRITE, LEAK_PROBE, 0x00)],
                       file=_file(r0=0x11, r7=0x0F, r10=0x00)),
    # Still refused, seed or no seed: $ff8802 is write-only on the chip, and it is counted as an
    # UNSERVABLE access rather than an unseeded read, because the remedy is different (there is none).
    "data_port_read": dict(scalars={"d1": 0, "unseeded": 0, "no_select": 0, "unmodeled": 1,
                                    "known": MIXER_BIT, "nlog": 0},
                           ledger=[], file=_file(r7=SEED)),

    # --- the audio-capture mode: the same model RELAXED, over the same chip state ---
    # A differential run first, so neither the file NOR the latch is empty when the mode is armed:
    # this one selects register 10 and writes it.
    "before_capture": dict(scalars={"d1": 0, "unseeded": 0, "no_select": 0, "unmodeled": 0,
                                    "known": MIXER_BIT | (1 << LEAK_PROBE), "nlog": 1},
                           ledger=[(WRITE, LEAK_PROBE, WRITTEN)],
                           file=_file(r7=SEED, r10=WRITTEN)),
    # Arming from OFF starts a fresh capture: BOTH halves of that chip state are gone. The bare data
    # write lands in the latch's placeholder register 0, not in the 10 the previous run selected —
    # which is the leak this case exists for.
    "capture_bare_write_after_arming": dict(
        scalars={"d1": 0, "unseeded": 0, "no_select": 0, "unmodeled": 0, "known": 1, "nlog": 1},
        ledger=[(WRITE, UNSELECTED, WRITTEN)], file=_file(r0=WRITTEN)),
    # Reading an undeclared register answers 0 instead of refusing — the mode's own fabrication.
    "capture_unknown_reads_zero": dict(scalars={"d1": 0, "unseeded": 0, "no_select": 0,
                                                "unmodeled": 0, "known": 0, "nlog": 1},
                                       ledger=[(READ, MIXER, 0)], file=_file()),
    # ...and the file then spans runs, which is what an extractor ticking once per VBL rests on.
    "capture_write_tick": dict(scalars={"d1": 0, "unseeded": 0, "no_select": 0, "unmodeled": 0,
                                        "known": MIXER_BIT, "nlog": 1},
                               ledger=[(WRITE, MIXER, WRITTEN)], file=_file(r7=WRITTEN)),
    "capture_next_tick_reads_it": dict(scalars={"d1": WRITTEN, "unseeded": 0, "no_select": 0,
                                                "unmodeled": 0, "known": MIXER_BIT, "nlog": 1},
                                       ledger=[(READ, MIXER, WRITTEN)], file=_file(r7=WRITTEN)),

    # --- the candidate side (src/psg.c), same seeds, same routines, then three mutants ---
    "cand_rmw": dict(scalars={"d1": SEED, "refusals": 0, "known": MIXER_BIT, "nlog": 2},
                     ledger=[(READ, MIXER, SEED), (WRITE, MIXER, SILENCED)],
                     file=_file(r7=SILENCED)),
    "cand_skips_the_write": dict(scalars={"d1": SEED, "refusals": 0, "known": MIXER_BIT, "nlog": 1},
                                 ledger=[(READ, MIXER, SEED)], file=_file(r7=SEED)),
    "cand_ignores_the_read": dict(scalars={"d1": 0, "refusals": 0, "known": MIXER_BIT, "nlog": 1},
                                  ledger=[(WRITE, MIXER, SILENCE)], file=_file(r7=SILENCE)),
    # The correct run the transposed one must be told apart from: same seed, both registers declared.
    "cand_rmw_two_seeded": dict(scalars={"d1": SEED, "refusals": 0,
                                         "known": MIXER_BIT | DECOY_BIT, "nlog": 2},
                                ledger=[(READ, MIXER, SEED), (WRITE, MIXER, SILENCED)],
                                file=_file(r7=SILENCED, r8=SEED)),
    # MUTANT 3: reads the DECOY and writes the mixer. Identical file, identical known mask, identical
    # WRITE stream — the read entry is the whole difference.
    "cand_reads_the_wrong_register": dict(scalars={"d1": SEED, "refusals": 0,
                                                   "known": MIXER_BIT | DECOY_BIT, "nlog": 2},
                                          ledger=[(READ, DECOY, SEED), (WRITE, MIXER, SILENCED)],
                                          file=_file(r7=SILENCED, r8=SEED)),
    "cand_unseeded_read": dict(scalars={"d1": 0, "refusals": 1, "known": 0, "nlog": 1},
                               ledger=[(READ, MIXER, 0)], file=_file()),
    # A register number the chip does not have: both the write and the read refuse, and neither
    # reaches the ledger or the file. The oracle answers the same mistake with `unmodeled`.
    "cand_out_of_range_register": dict(scalars={"d1": 0, "refusals": 2, "known": MIXER_BIT,
                                                "nlog": 0},
                                       ledger=[], file=_file(r7=SEED)),
}


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    """Build and run the probe once; return {case: {"scalars", "ledger", "file"}}."""
    binary = compile_probe(PROBE_SRC, tmp_path_factory.mktemp("psg_model"), CANDIDATE_SRC)
    out = subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout
    cases = {}
    for case, key, value in re.findall(r"^K (\S+) (\S+) (\d+)$", out, re.M):
        cases.setdefault(case, {"scalars": {}, "ledger": [], "file": {}})["scalars"][key] = int(value)
    for case, _index, kind, reg, value in re.findall(r"^L (\S+) (\d+) (\d+) (\d+) (\d+)$", out, re.M):
        cases[case]["ledger"].append((int(kind), int(reg), int(value)))
    for case, reg, value in re.findall(r"^F (\S+) (\d+) (\d+)$", out, re.M):
        cases[case]["file"][int(reg)] = int(value)
    return cases


def test_the_probe_reports_every_case(probe):
    """Guard the fixture itself: a probe that stopped printing (or a parse that stopped matching)
    would make every assertion below vacuously pass."""
    assert set(probe) == set(EXPECTED), (
        f"probe cases and expectations disagree — only in probe: {sorted(set(probe) - set(EXPECTED))}, "
        f"only in EXPECTED: {sorted(set(EXPECTED) - set(probe))}")


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_the_case_reports_what_the_model_promises(probe, case):
    """Every scalar the case claims, exactly. A key the probe prints and no case claims is caught by
    the equality below, so the two sides cannot drift apart quietly."""
    assert probe[case]["scalars"] == EXPECTED[case]["scalars"], (
        f"{case}: the model reported {probe[case]['scalars']}, not {EXPECTED[case]['scalars']}")


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_the_case_leaves_the_register_file_it_promises(probe, case):
    assert probe[case]["file"] == EXPECTED[case]["file"], (
        f"{case}: the modeled register file is {probe[case]['file']}, not {EXPECTED[case]['file']}")


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_the_case_logs_the_access_stream_it_promises(probe, case):
    """The ordered ledger, reads included. Its WRITE projection is what every project's
    `psg_writes()` consumer rests on, and `write_only` is the regression pin over a recorded
    sequence — so the read entries have to be additions to the stream, never edits of it."""
    assert probe[case]["ledger"] == EXPECTED[case]["ledger"], (
        f"{case}: the ledger is {probe[case]['ledger']}, not {EXPECTED[case]['ledger']}")


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_the_write_projection_of_the_stream_is_writes_and_nothing_else(probe, case):
    """`emu.psg_writes()` is the ledger filtered to `OS_PSG_EVENT_WRITE`, and it is the audio
    extractor's data feed and every existing consumer's contract. Pinned per case rather than once,
    so that a read entry mis-tagged as a write shows up as a phantom register write here."""
    writes = [(reg, value) for kind, reg, value in probe[case]["ledger"] if kind == WRITE]
    expected = [(reg, value) for kind, reg, value in EXPECTED[case]["ledger"] if kind == WRITE]
    assert writes == expected, (
        f"{case}: the write projection is {writes}, not {expected}")


def test_the_register_file_does_not_survive_a_run(probe):
    """A run must start from the CASE's declared contents and nothing else.

    `rmw` leaves register 7 holding $ff. `rmw_unseeded` runs the identical routine over the identical
    image with the seed withdrawn — and its read is refused, so the previous run's write did not
    carry over. Without that reset a case could be verified against a register another case wrote,
    and under `pytest -n auto` which case that is would not be stable: the same defect ENTRY_SR
    closed for the condition codes.
    """
    assert probe["rmw"]["file"][MIXER] == SILENCED, "the rmw case did not write the register at all"
    assert probe["rmw_unseeded"]["scalars"]["unseeded"] == MIXER_BIT, (
        "register 7 was still readable in the next run, so the model carries state between runs")


def test_a_bench_after_a_seeded_run_starts_from_the_seed(probe):
    """`osh_run_bench` is a second door into the oracle — no OS traps, a C function measured for
    cycles — and it reaches the PSG model through the same `enter_from_reset`.

    So the model's per-run reset belongs THERE rather than in `osh_run` alone. With it in `osh_run`
    only, a bench issued after a seeded run inherits that run's registers and its ledger: the perf
    measurement is then reading a chip another case wrote, and under `pytest -n auto` which case that
    was is not stable — the same defect the per-run re-seed closed for ordinary runs.
    """
    ran, benched = probe["rmw_two_seeded"], probe["bench_after_a_seeded_run"]
    assert ran["file"][MIXER] == SILENCED, "the run before the bench did not write the register"
    assert benched["file"][MIXER] == SEED, (
        "the bench inherited the previous run's register file instead of re-seeding from the case")
    assert benched["scalars"]["nlog"] == 0, (
        "the bench inherited the previous run's ledger, so its own PSG traffic would be reported "
        "with another run's in front of it")


def test_the_candidate_agrees_with_the_oracle_on_a_read_modify_write(probe):
    """The point of the whole change: the same routine, run as 68000 code and as C, produces the same
    access ledger and the same register file — which is what `harness.differential` compares."""
    assert probe["cand_rmw"]["ledger"] == probe["rmw"]["ledger"]
    assert probe["cand_rmw"]["file"] == probe["rmw"]["file"]
    assert probe["cand_rmw"]["scalars"]["known"] == probe["rmw"]["scalars"]["known"]


@pytest.mark.parametrize("mutant", ("cand_skips_the_write", "cand_ignores_the_read"))
def test_a_mutant_candidate_is_caught_by_both_off_image_surfaces(probe, mutant):
    """The negative control. Neither mutant touches the memory image at all — the PSG ports are
    off-image — so the byte diff sees nothing and only these two surfaces can catch them:

      * `cand_skips_the_write` reads the mixer and never writes it back;
      * `cand_ignores_the_read` writes the right register with the right mask but drops the bits the
        read-modify-write preserves. That one is the model's whole reason for existing: served a
        FABRICATED 0 read, `0 | $3f` and `read | $3f` agree, and this mutant would be green.
    """
    assert probe[mutant]["ledger"] != probe["rmw"]["ledger"], (
        f"{mutant}: the ordered access ledger matches a correct run's, so it would pass the "
        f"differential's stream comparison")
    assert probe[mutant]["file"] != probe["rmw"]["file"], (
        f"{mutant}: the modeled register file matches a correct run's, so it would pass the "
        f"differential's state comparison")


def test_a_transposed_read_is_caught_by_the_ledger_and_by_nothing_else(probe):
    """MUTANT 3, and the reason the ledger carries reads at all.

    `cand_reads_the_wrong_register` reads the DECOY register and writes the mixer. The decoy is
    seeded to the byte the mixer holds, so every OTHER surface agrees with a correct run exactly: the
    register file, its known mask, and the WRITE stream that used to be the whole ledger. A model
    that logged writes only would call this reconstruction verified — and on a real chip it merges
    the wrong register's bits, which is precisely the class the seeded read model exists to close.
    """
    correct, mutant = probe["cand_rmw_two_seeded"], probe["cand_reads_the_wrong_register"]
    assert mutant["file"] == correct["file"], (
        "the decoy is not seeded to the mixer's byte, so this case would be caught by the file "
        "comparison and proves nothing about the ledger")
    assert mutant["scalars"]["known"] == correct["scalars"]["known"]
    writes = [event for event in mutant["ledger"] if event[0] == WRITE]
    assert writes == [event for event in correct["ledger"] if event[0] == WRITE], (
        "the mutant's WRITE stream already differs, so the read entries are not what catches it")
    assert mutant["ledger"] != correct["ledger"], (
        "the ordered access ledger matches a correct run's, so a transposed read-modify-write "
        "would pass the differential with every surface green")
    assert correct["ledger"] == probe["rmw_two_seeded"]["ledger"], (
        "the candidate's correct run does not match the ORACLE's, so the comparison the mutant is "
        "measured against is not the one harness.differential makes")


def test_an_out_of_range_register_is_refused_on_BOTH_sides(probe):
    """A select the chip cannot decode. The ST's select port takes four bits and the YM2149 requires
    the upper nibble zero, so `move.b #$1e,$ff8800` is not "select register 14" — it is a write the
    model does not have an answer for. Masking it down would leave the oracle silently selecting 14
    while the candidate's psg_port_write refuses the same call, so both refuse.
    """
    assert probe["high_nibble_select"]["scalars"]["unmodeled"] == 1, (
        "the oracle masked a high-nibble select down to a register it does have")
    assert probe["high_nibble_select"]["ledger"] == [], (
        "the refused select still reached the ledger")
    assert probe["cand_out_of_range_register"]["scalars"]["refusals"] == 2, (
        "the candidate served an out-of-range register number instead of tallying, so a "
        "reconstruction that computed one would be compared against a register it never meant")


def test_a_read_before_any_select_is_refused_in_its_own_right(probe):
    """The entry LATCH is state too, and it is not seedable.

    A `$ff8800` read answers the latched register; with nothing selected there is no latched register
    and the 0 the model starts from is this file's convention, not the chip's. So it is refused —
    with its own tally, because its remedy is its own: the case is missing a `move.b #<reg>,$ff8800`,
    which is an instruction the run either executes or does not, not a byte a case can declare.
    """
    case = probe["read_before_any_select"]["scalars"]
    assert case["no_select"] == 1, "a read with nothing selected was served"
    assert case["unseeded"] == 0, (
        "the missing select was reported as a missing SEED, which would send the reader to add a "
        "psg_seed that cannot fix it")
    assert case["known"] == MIXER_BIT, (
        "the case did not carry a seed, so it does not show that seeding is beside the point here")


def test_arming_the_capture_mode_does_not_inherit_a_differential_run_s_chip_state(probe):
    """The hazard the shared chip state created, closed structurally — BOTH halves of it.

    The register file and the select latch are written by every differential run now, and the mode is
    what stops them being re-seeded per run — so a capture armed after a differential could otherwise
    start on that case's registers AND on the register it last selected, and under `pytest -n auto`
    on WHICH case is not reproducible. The latch half was the one that leaked: `before_capture`
    selects register 10, and with only the file cleared the bare data write below landed there.

    Arming from off therefore clears both; re-arming an already-armed capture still clears nothing
    (that pin lives in projects/wonderboy/recreate/test/test_audio_capture.py, which has a replayer).
    """
    assert probe["before_capture"]["file"][LEAK_PROBE] == WRITTEN, (
        "the differential run did not write the register it selected, so this case proves nothing")
    landed = probe["capture_bare_write_after_arming"]["file"]
    assert landed[LEAK_PROBE] == 0, (
        "arming the capture mode inherited the previous differential run's SELECT LATCH: a bare "
        "data write landed in the register that run selected")
    assert landed[UNSELECTED] == WRITTEN, (
        "the bare write did not land in the latch's placeholder register, so the case is not "
        "measuring where an unselected write goes")
    assert probe["capture_unknown_reads_zero"]["file"] == _file(), (
        "arming the capture mode inherited the previous differential run's register file")
    assert probe["capture_unknown_reads_zero"]["scalars"]["d1"] == 0, (
        "the capture mode refused an undeclared register instead of relaxing to 0")


def test_the_capture_mode_carries_the_register_file_between_runs(probe):
    """The other half of the relaxation: an extractor calls run() once per VBL tick, and tick N's
    read-back must see what tick N-1 wrote. Off the mode the same two runs would re-seed in between
    and the read would be refused (`rmw_unseeded` above pins that direction)."""
    assert probe["capture_next_tick_reads_it"]["scalars"]["d1"] == WRITTEN, (
        "the register file was cleared between two runs while the capture mode was armed")


def test_an_undeclared_register_is_refused_on_BOTH_sides(probe):
    """Refusing on one side only is a false green (TRAP_MODEL.md): the oracle's run is thrown away,
    while the candidate reads its fabricated value and carries on. So the candidate tallies through
    `os_refused()` — the same required ABI every other refusing helper uses — and
    `harness.differential` raises on it.
    """
    assert probe["unseeded_read"]["scalars"]["unseeded"] == MIXER_BIT, (
        "the oracle served an undeclared register instead of recording the refusal")
    assert probe["cand_unseeded_read"]["scalars"]["refusals"] == 1, (
        "the candidate served an undeclared register without tallying, so a reconstruction that "
        "read one would be compared against a value the model invented")
