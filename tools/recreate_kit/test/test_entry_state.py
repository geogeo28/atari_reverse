"""Pin the CPU state `osh_run` starts every run from, kit-side.

`oracle/shim.c` forces `SR = ENTRY_SR` after `m68k_pulse_reset()` because a 68000 reset does NOT
clear the condition codes: without the force, a run inherits whatever CCR the previous run in the
same process left, and every `abcd`/`sbcd`/`addx`/`roxl` differential becomes order-dependent
(TRAP_MODEL.md, "The entry state every run begins from").

That is a KIT-WIDE property, so it is pinned here as well as in the project whose reconstructions
surfaced it — the same placement rule `test_os_map.py` follows. The obstacle is that this directory
binds no project, and `harness`/`emu` both load a candidate `.so` at import, so the oracle cannot be
reached from Python here at all. `entry_state_probe.c` drives `osh_run` in C instead.

The build below compiles the oracle's own sources rather than linking the shared `liboracle.so`,
which is what keeps this honest: `shim.c` is recompiled on every run, so a reverted force reddens
immediately instead of being hidden behind an up-to-date-looking artifact (the mtime relink trap).
The generated opcode table and the Musashi clone are gitignored build products; without them there is
nothing to compile, so the suite skips rather than fails.
"""
import re
import subprocess

import pytest

from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
PROBE_SRC = Path(__file__).with_name("entry_state_probe.c")

MUSASHI = KIT / "oracle" / "musashi"
GENDIR = KIT / "oracle" / "build"
ORACLE_SRC = (MUSASHI / "m68kcpu.c", GENDIR / "m68kops.c", MUSASHI / "softfloat" / "softfloat.c",
              KIT / "oracle" / "shim.c")

# run name -> the byte `abcd d1,d0` must leave in d0. The two zero adds bracket a run that leaves X
# set, so they are the same question asked before and after; they must give the same answer.
EXPECTED = {"first_zero_add": 0, "arming_wrap": 0, "second_zero_add": 0}


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    """Build and run the probe once; return {run name: the byte d0 held}."""
    missing = [str(src) for src in ORACLE_SRC if not src.exists()]
    if missing:
        pytest.skip(f"the oracle's sources are not built here ({', '.join(missing)}) — "
                    f"run a project's `make oracle` first")
    binary = tmp_path_factory.mktemp("entry_state") / "probe"
    # -O0 because this compiles ~800 KiB of generated opcode table on every run and the optimiser
    # changes nothing the probe asks about; -DM68K_EMULATE_TRACE=0 mirrors kit.mk's OCFLAGS, which
    # shim.c refuses to build without.
    subprocess.run(
        ["cc", "-O0", "-DM68K_EMULATE_TRACE=0",
         f"-I{KIT / 'include'}", f"-I{MUSASHI}", f"-I{GENDIR}", f"-I{MUSASHI / 'softfloat'}",
         *[str(src) for src in ORACLE_SRC], str(PROBE_SRC), "-o", str(binary)],
        check=True, capture_output=True, text=True)
    out = subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout
    return {name: int(value) for name, value in re.findall(r"^(\S+) (\d+)$", out, re.M)}


def test_the_probe_reports_every_run(results):
    """Guard the fixture itself: a probe that stopped printing (or a parse that stopped matching)
    would make the assertions below vacuously pass."""
    assert set(results) == set(EXPECTED), (
        f"probe runs and expectations disagree — only in probe: {sorted(set(results) - set(EXPECTED))}, "
        f"only in EXPECTED: {sorted(set(EXPECTED) - set(results))}")


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
