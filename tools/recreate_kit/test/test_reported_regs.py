"""Pin the register set every run reports back, kit-side.

`osh_run` reports D0..D7 then A0..A6 — the full `movem` set bar A7 — and that set is the
OBSERVABILITY WINDOW every project's differential sees through: a routine whose outputs live in
registers the oracle does not report cannot be pinned by a case at all, only by whatever memory it
happens to touch. Wonder Boy stopped short of three reconstructions for exactly that reason while the
window was D0/D1/A0/A1 (`projects/wonderboy/recreate/STATUS.md`, batches 3 and 10).

That is a KIT-WIDE property, so it is pinned here as well as in the projects that consume it — the
placement rule `test_entry_state.py` and `test_os_map.py` follow. The same obstacle applies:
`harness`/`emu` bind a project's candidate `.so` at import and this directory deliberately binds no
project, so `reported_regs_probe.c` drives `osh_run` in C.

Two halves, because they pin different things:

* the probe pins the ORACLE's behaviour — a distinct mark in every reported register, and a canary
  one slot past the set that a run writing more than it declares would smash;
* the textual cases at the bottom pin `oracle/emu.py`'s mirror against `oracle/shim.c`, because the
  Python side ALLOCATES the buffer the C side fills. They parse both sources rather than importing
  either: `emu` needs a bound project and a built oracle, and this suite must run in a bare checkout.
  (`emu.run` also checks the same agreement against the loaded `.so` at import, which catches a
  STALE build — a different failure from the two sources drifting.)

`probe_build.compile_probe` builds the probe from the oracle's own sources rather than linking the
shared `liboracle.so`, so a narrowed report cannot hide behind an up-to-date-looking artifact (the
mtime relink trap), and a checkout with nothing built skips rather than fails.
"""
import re
import subprocess

import pytest

from pathlib import Path

from probe_build import KIT, SHIM, compile_probe

PROBE_SRC = Path(__file__).with_name("reported_regs_probe.c")
EMU = KIT / "oracle" / "emu.py"

# The window, in the order a caller indexes it. A7 is NOT here: it is the harness's stack pointer,
# forced to the run's `sp` on entry and popped back by the rts, so its final value states the
# harness's own convention rather than anything the function computed (emu.run's `min_a7` reports the
# one thing about it a case can use). Every claim below is about this list.
REPORTED = tuple(f"d{i}" for i in range(8)) + tuple(f"a{i}" for i in range(7))
RUNS = ("written", "passthrough")


def _build_and_run(tmp_path):
    """Compile the probe against the oracle's own sources, run it, and return its stdout."""
    binary = compile_probe(PROBE_SRC, tmp_path)
    return subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    """{run: [(reg, expected, reported), ...]} from the probe, plus the two canary slots."""
    out = _build_and_run(tmp_path_factory.mktemp("reported_regs"))
    rows = {run: [] for run in RUNS}
    for run, reg, expected, reported in re.findall(r"^(\w+) (\w+) (\d+) (\d+)$", out, re.M):
        if run in rows:
            rows[run].append((reg, int(expected), int(reported)))
    canaries = re.search(r"^canary (\d+) (\d+)$", out, re.M)
    assert canaries, f"the probe printed no canary line:\n{out}"
    return {"rows": rows, "canaries": (int(canaries.group(1)), int(canaries.group(2)))}


@pytest.mark.parametrize("run", RUNS)
def test_the_probe_reports_every_register_in_the_declared_order(results, run):
    """Guard the fixture itself: a probe that stopped printing a register — or one whose slot order
    drifted — would make the value assertions below vacuously pass on what is left."""
    assert tuple(reg for reg, _, _ in results["rows"][run]) == REPORTED, (
        f"{run}: the probe reported {[reg for reg, _, _ in results['rows'][run]]}, not the "
        f"{list(REPORTED)} osh_run declares")


def test_the_probes_values_are_distinct_within_a_run(results):
    """Vacuity guard for the two cases below: if two registers were seeded with the SAME value, a
    report that mixed up their slots would still compare equal."""
    for run in RUNS:
        expected = [value for _, value, _ in results["rows"][run]]
        assert len(set(expected)) == len(REPORTED), f"{run}: seeded values repeat: {expected}"
        assert 0 not in expected, f"{run}: a seeded value is 0, which a never-written slot also holds"


@pytest.mark.parametrize("reg", REPORTED)
def test_a_register_the_routine_wrote_comes_back(results, reg):
    """`movem.l (table).l,d0-d7/a0-a6` puts a distinct mark in each; each must come back in its own
    slot. This is the window itself: before it was widened, everything past d1/a1 was unobservable."""
    _, expected, reported = next(row for row in results["rows"]["written"] if row[0] == reg)
    assert reported == expected, (
        f"the run left {expected:#x} in {reg} and osh_run reported {reported:#x} — the register is "
        f"not reported, or not in the slot the caller indexes for it")


@pytest.mark.parametrize("reg", REPORTED)
def test_a_register_the_routine_never_touches_reports_its_entry_value(results, reg):
    """The other half: over a bare `rts`, the report must be the live register file (what the caller
    set), not anything the one `movem` above happens to produce."""
    _, expected, reported = next(row for row in results["rows"]["passthrough"] if row[0] == reg)
    assert reported == expected, (
        f"{reg} entered holding {expected:#x} and was reported as {reported:#x} — an untouched "
        f"register is not being read back out of the CPU")


def test_a7_is_not_reported_and_nothing_is_written_past_the_set(results):
    """The decision, stated as a test: A7 is the harness's own and is deliberately absent, so the
    slot after the last reported register must come back untouched. A run that quietly wrote one more
    value would be overrunning every caller's buffer, which is emu.run's as much as this probe's."""
    assert "a7" not in REPORTED
    written, passthrough = results["canaries"]
    assert written == passthrough, "the two runs disagree about the canary slot"
    assert written == 0xdeadbeef, (
        f"osh_run wrote {written:#x} one slot past the {len(REPORTED)} registers it declares — the "
        f"reported set and OSH_OUT_REGS have drifted apart")


def _c_define(name):
    m = re.search(rf"^#define\s+{name}\s+(\d+)\b", SHIM.read_text(), re.M)
    assert m, f"{SHIM.name} defines no {name}"
    return int(m.group(1))


def _py_tuple(source, name):
    m = re.search(rf"^{name} = \(([^)]*)\)", source, re.M)
    assert m, f"{EMU.name} has no `{name} = (...)` tuple"
    return tuple(re.findall(r'"(\w+)"', m.group(1)))


def test_emu_names_exactly_the_registers_the_shim_reports():
    """Cross-language pin (CLAUDE.md §5): the C fills the buffer, the PYTHON allocates it, and they
    cannot import each other. A mirror that named fewer registers would read slots the run wrote —
    or, naming more, hand the shim a buffer it overruns."""
    source = EMU.read_text()
    dnames, anames = _py_tuple(source, "_DREG_NAMES"), _py_tuple(source, "_AREG_NAMES")
    assert "REPORTED_REGS = _DREG_NAMES + _AREG_NAMES[:-1]" in source, (
        f"{EMU.name} no longer derives REPORTED_REGS by dropping a7 from the A registers; this pin "
        f"parses that one shape, so restate it here if the derivation changed on purpose")
    assert dnames + anames[:-1] == REPORTED
    assert _c_define("OSH_OUT_DREGS") == len(dnames)
    assert _c_define("OSH_OUT_AREGS") == len(anames) - 1, (
        "shim.c reports a different number of address registers than emu.py names — one of them "
        "counts a7 and the other does not")
