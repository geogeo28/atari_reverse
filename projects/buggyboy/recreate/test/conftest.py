"""conftest.py — differential-suite fixtures.

Coverage hook (opt-in, off by default): when the env var COVGAP_DIR is set (only tools/coverage_gap.py
does this), turn on the oracle's executed-PC tracking for this process and, at session end, dump the
accumulated bitset to COVGAP_DIR/<worker>.bin. Under pytest-xdist each worker is its own process, so
each dumps its own file and coverage_gap.py OR-merges them. With COVGAP_DIR unset this file does
nothing, so a normal `make test` is unaffected.
"""
import os
from pathlib import Path

_COVDIR = os.environ.get("COVGAP_DIR")

if _COVDIR:
    import harness   # noqa: F401  — binds the shared kit, putting its oracle/ on sys.path
    import emu


def pytest_configure(config):
    if _COVDIR:
        emu.cov_enable(True)
        emu.cov_reset()


def pytest_sessionfinish(session, exitstatus):
    if not _COVDIR:
        return
    worker = getattr(session.config, "workerinput", {}).get("workerid", "main")
    Path(_COVDIR, f"{worker}.bin").write_bytes(emu.cov_data())
