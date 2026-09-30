"""A test that never returns ENDS the run, naming itself on the REAL stderr, under every capture mode
(`recreate_kit.watchdog`, the plugin kit.mk loads into every suite).

The candidate is host C entered through ctypes, and nothing in Python can interrupt a loop there. The watchdog is
faulthandler's thread; each case here runs a CHILD pytest over a spinning test with the budget shortened, under the
three capture shapes the plugin exists for — pytest's default fd capture (which swallowed the stack of the per-call
guard this replaced), `--capture=sys` (where that guard raised on arming) and xdist (a worker "crashed" with no
stack) — and reads the child's own stderr, which is the terminal a person would be watching.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2]         # reverse/tools, so `recreate_kit` imports in the child
BUDGET_SECONDS = 0.5
CHILD_SECONDS = 60              # a child still running after this is the hang the watchdog exists to end
SPINNING_TEST = "test_spins_here"

SPINNING_SUITE = f"""
def test_returns():
    pass

def {SPINNING_TEST}():
    while True:
        pass
"""

# Two tests that each take most of the budget, so the pair runs past it: a timer that were not re-armed per test —
# or that a returned test left armed — would end this run.
UNDER_BUDGET_SECONDS = BUDGET_SECONDS * 0.7
RETURNING_SUITE = f"""
import time

def test_first():
    time.sleep({UNDER_BUDGET_SECONDS})

def test_second():
    time.sleep({UNDER_BUDGET_SECONDS})
"""

# ...and a session end that outlasts the budget: a timer the last test left armed would fire there.
SLOW_SESSION_END = f"""
import time

def pytest_sessionfinish():
    time.sleep({BUDGET_SECONDS * 1.5})
"""

USAGE_ERROR = 4                 # pytest's exit status for a refused command line / configuration


def _child_pytest(tmp_path, suite, *args, conftest=""):
    (tmp_path / "test_child.py").write_text(textwrap.dedent(suite))
    (tmp_path / "conftest.py").write_text(textwrap.dedent(conftest))
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "recreate_kit.watchdog",
               "--watchdog-seconds", str(BUDGET_SECONDS), *args, str(tmp_path)]
    return subprocess.run(command, capture_output=True, text=True, timeout=CHILD_SECONDS,
                          env={"PYTHONPATH": str(TOOLS), "PATH": ""})


@pytest.mark.parametrize("capture", ([], ["--capture=sys"], ["-n", "2"]), ids=("fd", "sys", "xdist"))
def test_a_spinning_test_ends_the_run_with_its_name_and_stack_on_the_real_stderr(tmp_path, capture):
    run = _child_pytest(tmp_path, SPINNING_SUITE, *capture)
    assert run.returncode != 0, run.stdout
    assert "Timeout" in run.stderr and f"in {SPINNING_TEST}" in run.stderr, (run.stdout, run.stderr)


def test_under_xdist_the_controller_names_the_crashed_test(tmp_path):
    run = _child_pytest(tmp_path, SPINNING_SUITE, "-n", "2")
    assert f"crashed while running 'test_child.py::{SPINNING_TEST}'" in run.stdout, run.stdout


def test_returning_tests_are_unaffected(tmp_path):
    """The control: the budget is per TEST — two tests whose sum passes the budget both pass, and the session's
    own end, past the budget again, is not a test the timer was left armed for."""
    run = _child_pytest(tmp_path, RETURNING_SUITE, conftest=SLOW_SESSION_END)
    assert run.returncode == 0 and "2 passed" in run.stdout, (run.stdout, run.stderr)


def test_an_outer_faulthandler_timeout_is_refused_rather_than_clobbered(tmp_path):
    """faulthandler has ONE timer: arming it per test would silently disarm pytest's own `faulthandler_timeout`."""
    run = _child_pytest(tmp_path, RETURNING_SUITE, "-o", "faulthandler_timeout=5")
    assert run.returncode == USAGE_ERROR and "owns faulthandler's one timer" in run.stderr, run.stderr
