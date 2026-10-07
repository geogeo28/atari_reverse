"""Pin the CPU state `osh_run` starts every run from, kit-side.

`oracle/shim.c` forces `SR = ENTRY_SR` after `m68k_pulse_reset()` because a 68000 reset does NOT
clear the condition codes: without the force, a run inherits whatever CCR the previous run in the
same process left, and every `abcd`/`sbcd`/`addx`/`roxl` differential becomes order-dependent
(TRAP_MODEL.md, "The entry state every run begins from").

That is a KIT-WIDE property, so it is pinned here as well as in the project whose reconstructions
surfaced it — the same placement rule `test_os_map.py` follows. The obstacle is that this directory
binds no project, and `harness`/`emu` both load a candidate `.so` at import, so the oracle cannot be
reached from Python here at all. `entry_state_probe.c` drives `osh_run` in C instead.

`probe_build.compile_probe` builds it from the oracle's own sources rather than linking the shared
`liboracle.so`, which is what keeps this honest: `shim.c` is recompiled on every run, so a reverted
force reddens immediately instead of being hidden behind an up-to-date-looking artifact (the mtime
relink trap), and a checkout with nothing built skips rather than fails.
"""
import re
import subprocess

import pytest

from pathlib import Path

from probe_build import compile_probe

PROBE_SRC = Path(__file__).with_name("entry_state_probe.c")

# run name -> the byte `abcd d1,d0` must leave in d0. The two zero adds bracket a run that leaves X
# set, so they are the same question asked before and after; they must give the same answer.
# ...and the same zero add made through the OTHER door (`osh_run_bench`) straight after another wrap: a force that
# lived in `osh_run` alone would leave every bench run inheriting the last run's condition codes.
EXPECTED = {"first_zero_add": 0, "arming_wrap": 0, "second_zero_add": 0, "bench_arming_wrap": 0, "bench_zero_add": 0}
# ...and the USER STACK POINTER a run finds on entry (`move.l usp,a0`), READ THROUGH EACH DOOR straight after a run
# that leaves one behind: a force in one door alone reddens the read through the other (entry_state_probe.c).
A_USER_STACK = 0x00123456              # entry_state_probe.c's: what its arming run leaves in USP
ENTRY_USP = 0                          # shim.c's ENTRY_USP
READS_OF_THE_USP = {"first_usp": "osh_run", "first_bench_usp": "osh_run_bench",
                    "second_bench_usp": "osh_run_bench, after a run that left one",
                    "second_usp": "osh_run, after a run that left one"}
ARMING_RUNS = ("arming_usp", "rearming_usp")
EXPECTED_USP = {**dict.fromkeys(READS_OF_THE_USP, ENTRY_USP), **dict.fromkeys(ARMING_RUNS, A_USER_STACK)}


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    """Build and run the probe once; return {run name: the byte d0 held}."""
    binary = compile_probe(PROBE_SRC, tmp_path_factory.mktemp("entry_state"))
    out = subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout
    return {name: int(value) for name, value in re.findall(r"^(\S+) (\d+)$", out, re.M)}


def test_the_probe_reports_every_run(results):
    """Guard the fixture itself: a probe that stopped printing (or a parse that stopped matching)
    would make the assertions below vacuously pass."""
    claimed = set(EXPECTED) | set(EXPECTED_USP)
    assert set(results) == claimed, (
        f"probe runs and expectations disagree — only in probe: {sorted(set(results) - claimed)}, "
        f"only in EXPECTED: {sorted(claimed - set(results))}")


@pytest.mark.parametrize("run", sorted(EXPECTED))
def test_a_run_gives_the_result_a_clear_entry_ccr_produces(results, run):
    assert results[run] == EXPECTED[run], (
        f"{run}: `abcd` left {results[run]:#04x} in d0, not the {EXPECTED[run]:#04x} an entry X of 0 "
        f"gives — osh_run is not forcing ENTRY_SR after the reset")


def test_two_identical_runs_agree_across_one_that_sets_the_extend_bit(results):
    """The defect stated as the property it broke: identical runs must give identical answers
    whatever ran between them. This is what a differential rests on, and what made four Wonder Boy
    cases redden under `-n auto` and pass on their own."""
    assert results["first_zero_add"] == results["second_zero_add"], (
        "the same run answered differently either side of one that set the extend bit — the oracle "
        "is carrying the CCR across runs, so every abcd/sbcd/addx/roxl differential is "
        "order-dependent")


def test_a_bench_run_enters_with_the_condition_codes_clear_too(results):
    """The same zero add through `osh_run_bench`, straight after a run that left X set: 0. A force in `osh_run`
    alone answers 1 here and 0 in every test above."""
    assert results["bench_zero_add"] == 0, (
        "a run entered through osh_run_bench inherited the extend bit of the run before it — the entry SR is "
        "forced in one door and not in the place both share (`enter_from_reset`)")


@pytest.mark.parametrize("run", ARMING_RUNS)
def test_the_arming_run_really_leaves_a_user_stack_pointer_behind(results, run):
    """The premise of the pin below: without it the reads agree because nothing was left to inherit."""
    assert results[run] == A_USER_STACK, (
        f"the arming run left USP at {results[run]:#x}, not {A_USER_STACK:#x} — the probe arms nothing")


@pytest.mark.parametrize("read", sorted(READS_OF_THE_USP))
def test_a_run_enters_with_the_user_stack_pointer_the_kit_forces_whatever_ran_before(results, read):
    """`move.l usp,a0` through EACH door, before and straight after a run that left a user stack pointer: every
    read finds ENTRY_USP. Without the force a read finds what the run before it left — and a routine that SAVES
    its USP (an operating system's context save) then leaves an image that depends on which run came before it in
    the process (projects/tos102us: twenty verified rows hashed differently under `make bench`'s import order than
    in an xdist worker's — every one of them a BENCH run's, the door a read through `osh_run` alone never holds)."""
    assert results[read] == ENTRY_USP, (
        f"a run entered through {READS_OF_THE_USP[read]} found USP at {results[read]:#x}: the oracle carries the "
        f"user stack pointer across runs through that door")
