"""A pytest plugin that ENDS a test which never returns, naming it, instead of letting it hang the run.

    PYTHONPATH=<reverse>/tools .venv/bin/python -m pytest -p recreate_kit.watchdog test

kit.mk's `test` and `guarded` targets and the kit's own Makefile load it, so every project's suite runs under it;
a mutation sweep that drives pytest itself passes the same `-p` (and the PYTHONPATH that makes it importable).

WHY. A candidate is host C entered through ctypes, and nothing in Python can interrupt a loop there: a spinning
mutant, or a reconstruction that spins where the original returns, used to hang `make test` — and a sweep's run
until its own timeout called the mutant ABNORMAL without saying where. faulthandler's watchdog is a THREAD that needs
no help from the stuck one: past the budget it prints every thread's stack and ends the process with status 1.

WHY A PLUGIN, AND AT THIS ALTITUDE. The guard used to be armed around each candidate call inside
`harness.differential`, and was wrong four ways, all measured:
  * under pytest's default fd capture it wrote the stack into the capture file, which died with the process — a
    serial run ended silently and an xdist worker "crashed" with no stack;
  * under `--capture=sys` stderr has no file descriptor, so arming it raised and every differential errored;
  * faulthandler has ONE timer per process, and re-arming/cancelling it per call silently disarmed pytest's own
    `faulthandler_timeout` (or any outer timer);
  * it covered only the differential's two calls — not the direct `_lib` calls, the asm twins or the Tier 3 bench.
So the plugin arms ONE timer per TEST (setup, call and teardown, as pytest's own `faulthandler_timeout` does) and
writes it to a duplicate of the REAL stderr taken at configure time — when pytest's capture is suspended — which
is the same move pytest's faulthandler plugin makes. Under xdist the worker's stack reaches the controller's
terminal and the controller reports "worker ... crashed while running <test>"; serially the stack alone names it.

ONE TIMER, ONE OWNER. An outer `faulthandler_timeout` would be clobbered by this timer (or clobber it), so the
combination is refused at configure time rather than resolved in silence: drop the option, or pass
`-p no:recreate_kit.watchdog` to run under pytest's own timer instead.

A WATCHDOG EXIT IS NOT A FAILED TEST. The process ends with status 1 and no assertion ran, so a mutation sweep's
strict classifier counts it ABNORMAL, never KILLED (tos102us `recreate/README.md`, "Mutation sweeps").
"""
import faulthandler
import os
import sys

import pytest

# THE PER-TEST BUDGET, in seconds — far above any honest test, so only a hang reaches it. Set from the longest
# single test phase measured across the kit's projects under `make test` (-n auto, --durations): buggyboy's
# test_blit_objsprite.py::test_hi_fuzz at 46 s is the maximum (wonderboy, tos102us, zynaps and the rest stay
# under 10 s); the budget allows ~6.5x that for a loaded machine and the guarded-image sweep's extra cost.
TEST_BUDGET_SECONDS = 300

_BUDGET_OPTION = "--watchdog-seconds"


def pytest_addoption(parser):
    parser.addoption(_BUDGET_OPTION, type=float, default=TEST_BUDGET_SECONDS,
                     help=f"end the process, printing every stack, when one test runs longer than this "
                          f"(default {TEST_BUDGET_SECONDS} s; recreate_kit.watchdog)")


def _outer_timeout(config):
    """pytest's own `faulthandler_timeout`, or 0 when it is unset or its plugin is not loaded."""
    try:
        return float(config.getini("faulthandler_timeout") or 0)
    except ValueError:                                   # `-p no:faulthandler`: the option does not exist
        return 0


class _Watchdog:
    """The duplicated stderr and the budget, held for the session."""

    def __init__(self, seconds):
        self.seconds = seconds
        self.stderr = os.dup(sys.__stderr__.fileno())

    @pytest.hookimpl(wrapper=True, trylast=True)
    def pytest_runtest_protocol(self, item):
        del item
        faulthandler.dump_traceback_later(self.seconds, exit=True, file=self.stderr)
        try:
            return (yield)
        finally:
            faulthandler.cancel_dump_traceback_later()

    @pytest.hookimpl(tryfirst=True)
    def pytest_enter_pdb(self):
        """A debugger session is not a hang."""
        faulthandler.cancel_dump_traceback_later()

    def close(self):
        faulthandler.cancel_dump_traceback_later()
        os.close(self.stderr)


_WATCHDOG_NAME = "recreate_kit.watchdog.timer"


def pytest_configure(config):
    outer = _outer_timeout(config)
    if outer > 0:
        raise pytest.UsageError(
            f"recreate_kit.watchdog owns faulthandler's one timer, and faulthandler_timeout={outer:g} asks for it "
            f"too — one would silently disarm the other. Drop faulthandler_timeout (the watchdog's own budget is "
            f"{_BUDGET_OPTION}), or pass -p no:recreate_kit.watchdog to run under pytest's timer instead")
    config.pluginmanager.register(_Watchdog(config.getoption(_BUDGET_OPTION)), _WATCHDOG_NAME)


def pytest_unconfigure(config):
    watchdog = config.pluginmanager.get_plugin(_WATCHDOG_NAME)
    if watchdog is not None:
        watchdog.close()
        config.pluginmanager.unregister(watchdog)
