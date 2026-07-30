"""Pin every refusal site in include/os.h to the candidate-side tally.

`harness.differential()` raises when the candidate makes an `os_*` call the TOS model refuses — that
is what stops a reconstruction from dropping a guard the original has and staying green
(TRAP_MODEL.md, "Refusing on ONE side is a false green"). The raise is only worth what the call
sites behind it are worth, and the game suites cannot pin those: a CORRECT reconstruction never
reaches a refusing helper, so reverting any single `return os_refused(...)` in os.h to a bare
`return` leaves all three differential suites green.

So this drives each helper directly. `os_refusal_probe.c` runs one case per branch and prints the
tally delta; the expectations live here, and a case the probe prints but this file does not claim is
a failure — so a new case cannot be added without stating what it should do.
"""
import re
import subprocess

import pytest

from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
PROBE_SRC = Path(__file__).with_name("os_refusal_probe.c")

# case name -> tally delta the case must produce. One entry per branch in the probe: a refusal moves
# the tally by exactly one, and every served call must leave it alone.
EXPECTED = {
    # os_gem_trap: an unmodeled subsystem and an unmodeled opcode in either subsystem
    "gem_bad_subsystem": 1, "gem_bad_aes_opcode": 1, "gem_bad_vdi_opcode": 1, "gem_served": 0,
    # BIOS console. Bconin refuses a blocking read the model cannot wait out...
    "bconstat_bad_device": 1, "bconstat_served": 0,
    "bconin_no_key": 1, "bconin_bad_device": 1, "bconin_served": 0,
    # ...but Crawio is non-blocking, so an idle console is a RESULT and must never tally. This is
    # the property that made os_console_take_key a separate helper.
    "crawio_read_idle": 0, "crawio_read_key": 0, "crawio_write": 0,
    # GEMDOS Super: only the three values the token model recognises are served
    "super_unknown_token": 1, "super_enter": 0, "super_inquire": 0, "super_restore": 0,
    # GEMDOS file I/O. os_fcreate refuses only THROUGH os_fopen, so its delta is 1, never 2 —
    # a second tally there would count one refused call twice.
    "fopen_unstaged": 1, "fopen_served": 0,
    "fcreate_unstaged": 1, "fcreate_served": 0,
    "fread_bad_handle": 1, "fread_closed_slot": 1, "fread_buffer_outside_image": 1,
    "fread_served": 0,
    "fwrite_bad_handle": 1, "fwrite_past_capacity": 1, "fwrite_buffer_outside_image": 1,
    "fwrite_served": 0,
    "fclose_bad_handle": 1, "fclose_served": 0,
}


@pytest.fixture(scope="module")
def deltas(tmp_path_factory):
    """Build and run the probe once; return {case name: tally delta}."""
    binary = tmp_path_factory.mktemp("os_refusal") / "probe"
    subprocess.run(
        ["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         f"-I{KIT / 'include'}", str(PROBE_SRC), str(KIT / "src" / "os_refusal.c"),
         "-o", str(binary)],
        check=True, capture_output=True, text=True)
    out = subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout
    return {name: int(delta) for name, delta in re.findall(r"^(\S+) (\d+)$", out, re.M)}


def test_probe_reports_every_case(deltas):
    """Guard the fixture itself: a probe that stopped printing (or a parse that stopped matching)
    would make every assertion below vacuously pass."""
    assert set(deltas) == set(EXPECTED), (
        f"probe cases and expectations disagree — only in probe: {sorted(set(deltas) - set(EXPECTED))}, "
        f"only in EXPECTED: {sorted(set(EXPECTED) - set(deltas))}")


@pytest.mark.parametrize("case", sorted(k for k, v in EXPECTED.items() if v))
def test_refusal_is_tallied(deltas, case):
    """A call the model cannot serve moves the tally by exactly one."""
    assert deltas[case] == EXPECTED[case], (
        f"{case}: tally moved by {deltas[case]}, expected {EXPECTED[case]} — os.h's refusal for "
        f"this branch does not go through os_refused(), so a candidate reaching it would pass "
        f"harness.differential() untested")


@pytest.mark.parametrize("case", sorted(k for k, v in EXPECTED.items() if not v))
def test_served_call_is_not_tallied(deltas, case):
    """The mirror half: a call the model DOES serve must leave the tally alone, or every case that
    makes it would fail the differential for no reason."""
    assert deltas[case] == 0, (
        f"{case}: tally moved by {deltas[case]} on a call the model serves — this would fail every "
        f"differential case that makes it")
