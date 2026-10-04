"""`test/conftest.py` held on itself: how the suite is spread over xdist's workers, and the order it is collected in.

Both are costs, not verdicts — no case passes or fails by them — so nothing else in the suite would say that either
was lost: a run back under xdist's `load` (one worker running the file selector's sessions alone), or a session's
cases collected a file apart again (each derived on several workers)."""
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

import aes_event
import conftest
import test_aes_fs_input as fs_input
import test_aes_fs_input_rows as fs_rows
import test_tier3

RECREATE = Path(__file__).resolve().parent.parent
A_FAST_FILE = "test/test_case.py"       # a few tests that import no battery: a whole pytest run of it is seconds


# ---- the distribution ------------------------------------------------------------------------------------------------
def _configured(arguments, **options):
    """The `--dist` a run ends with: `pytest_configure` over a config whose command line was `arguments` and whose
    options (`dist`, as xdist's `pytest_cmdline_main` has left it by then) are `options`."""
    config = types.SimpleNamespace(option=types.SimpleNamespace(**options), addinivalue_line=lambda *_line: None,
                                   invocation_params=types.SimpleNamespace(args=tuple(arguments)))
    conftest.pytest_configure(config)
    return getattr(config.option, "dist", None)


COMMAND_LINES = {
    "the makefile's own": (("-q", "-n", "auto", "test"), "load", conftest.STEALING),
    "an override that names no distribution": (("-n4", "-k", "fuzz"), "load", conftest.STEALING),
    "a distribution of its own": (("-n", "4", "--dist", "load"), "load", "load"),
    "...spelt with =": (("-n4", "--dist=loadfile"), "loadfile", "loadfile"),
    "...xdist's own default asked for by name": (("-n4", "--dist=load"), "load", "load"),
    "...or by its short form": (("-n4", "-d"), "load", "load"),
    "a serial run": (("-n0",), "no", "no"),
}


@pytest.mark.parametrize("arguments, dist, ends_with", COMMAND_LINES.values(), ids=COMMAND_LINES)
def test_a_run_under_xdist_steals_unless_its_command_line_names_a_distribution(arguments, dist, ends_with):
    assert _configured(arguments, dist=dist) == ends_with


def test_a_run_without_xdist_is_left_alone():
    """`-p no:xdist` (a mutation sweep's private runs): no `--dist` option exists, and none is made up."""
    assert _configured(("-p", "no:xdist", "test")) is None


def _a_real_run(*arguments):
    """A whole pytest run of A_FAST_FILE as `make test` makes one (the kit on the path), verbose: its output."""
    environment = dict(os.environ, PYTHONPATH=str(RECREATE.parents[2] / "tools"), PYTHONDONTWRITEBYTECODE="1")
    ran = subprocess.run([sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider", *arguments, A_FAST_FILE],
                         cwd=RECREATE, env=environment, capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    return ran.stdout


REAL_RUNS = {"an override with no distribution": (("-n", "2"), "WorkStealingScheduling"),
             "an override with its own": (("-n", "2", "--dist", "load"), "LoadScheduling"),
             "xdist switched off": (("-p", "no:xdist"), "passed")}


@pytest.mark.parametrize("arguments, said", REAL_RUNS.values(), ids=REAL_RUNS)
def test_a_real_run_is_scheduled_as_its_command_line_leaves_it(arguments, said):
    """THE PIN, on xdist itself: a run that overrides PYTEST_ARGS without a `--dist` (every override the kit's
    README documents) is still scheduled by work stealing; one that names its own keeps it; and with xdist off the
    suite still runs."""
    assert said in _a_real_run(*arguments)


# ---- the order: a session's cases back to back -------------------------------------------------------------------------
class _Item:
    """What the collection hook reads of an item: its id, its closest `collected_with` marker, and — a test
    function's alone — its parameters."""

    def __init__(self, nodeid, mark=None, params=None):
        self.nodeid, self._mark = nodeid, mark
        if params is not None:
            self.callspec = types.SimpleNamespace(params=params)

    def get_closest_marker(self, name):
        return self._mark if self._mark is not None and self._mark.name == name else None


def _module_s_mark(module):
    """The `collected_with` mark `module` declares for all its cases (`pytestmark`)."""
    return module.pytestmark.mark


def _ids(items):
    return [item.nodeid for item in items]


def test_each_group_s_members_are_moved_up_behind_its_first_and_nothing_else_moves():
    named = pytest.mark.collected_with("one").mark
    by_letter = pytest.mark.collected_with(by=lambda params: params.get("letter")).mark
    items = [_Item("m.py::a"), _Item("m.py::b", named), _Item("m.py::c[x]", by_letter, {"letter": "x"}),
             _Item("m.py::d"), _Item("m.py::e[y]", by_letter, {"letter": "y"}), _Item("m.py::f", named),
             _Item("m.py::g[x]", by_letter, {"letter": "x"}), _Item("m.py::h[none]", by_letter, {}),
             _Item("other.py::i[x]", by_letter, {"letter": "x"})]
    assert _ids(conftest.grouped(items)) == ["m.py::a", "m.py::b", "m.py::f", "m.py::c[x]", "m.py::g[x]", "m.py::d",
                                             "m.py::e[y]", "m.py::h[none]", "other.py::i[x]"]


def test_an_item_that_is_no_test_function_s_is_no_group_s():
    """A doctest's item, a plugin's own: no `callspec`, perhaps no marker at all — asked for no parameters, left where
    it is, and the collection not failed for it."""
    asked = []
    by_parameters = pytest.mark.collected_with(by=lambda params: asked.append(params)).mark
    assert conftest.group_of(_Item("README.md::doctest")) is None
    assert conftest.group_of(_Item("m.py::m.function", by_parameters)) is None and asked == [{}]


def test_the_file_selector_s_sessions_are_each_collected_back_to_back():
    """THE DECLARATION IS THE BATTERY'S (RED: without `test_aes_fs_input.pytestmark` nothing is grouped): its two
    tests over every session, collected a function after the other, end up a session after the other."""
    mark, functions = _module_s_mark(fs_input), ("through", "draws")
    items = [_Item(f"test/test_aes_fs_input.py::{function}[{name}]", mark, {"name": name})
             for function in functions for name in fs_input.SESSIONS]
    another = _Item("test/test_aes_fs_input.py::another[name]", mark, {"name": "no session's"})
    assert _ids(conftest.grouped([*items, another])) == [
        *(f"test/test_aes_fs_input.py::{function}[{name}]" for name in fs_input.SESSIONS for function in functions),
        another.nodeid]


def test_every_case_of_the_priced_sessions_names_its_session():
    """...and each test of `test_aes_fs_input_rows.py` is collected with the priced session it runs over."""
    tests = {name: test for name, test in vars(fs_rows).items() if name.startswith("test_")}
    assert tests
    for name, test in tests.items():
        (group,), = (mark.args for mark in getattr(test, "pytestmark", ()) if mark.name == conftest.GROUP_MARKER)
        assert group in fs_rows.PRICED_SESSIONS, name


def test_a_sliced_session_s_rows_companions_and_partition_are_collected_back_to_back():
    """Tier 3 (RED: without `test_tier3.pytestmark` nothing is grouped): a sliced session's row tests, its companions
    (by the registered name) and its partition (by its first row) are one group, in the order they were collected;
    every other row stays where it was."""
    tier3, mark = test_tier3.tier3, _module_s_mark(test_tier3)
    rows = [_Item(f"test/test_tier3.py::row[{row.symbol}-{row.case}]", mark, {"row": row}) for row in tier3.ROWS]
    keys = [_Item(f"test/test_tier3.py::key[{key}]", mark, {"key": key}) for key in test_tier3.SLICED_ROWS]
    companions = [_Item(f"test/test_tier3.py::companion[{row.registered}]", mark, {"name": row.registered})
                  for row in tier3.ROWS if row.registered]
    ordered = conftest.grouped([*rows, *keys, *companions])
    sessions = [id(aes_event.session_of(name)) if name in aes_event.SLICED_ROWS else None
                for name in (_registered_name_of(item) for item in ordered)]
    sliced = {session for session in sessions if session is not None}
    assert len(sliced) == len(test_tier3.SESSIONS_SLICED) > 1
    for session in sliced:
        places = [place for place, each in enumerate(sessions) if each == session]
        assert places == list(range(places[0], places[-1] + 1)), "a session's cases are not back to back"
        assert len(places) > len(tier3.rows_of_the_session(aes_event.session_of(_registered_name_of(ordered[places[0]]))))
    unsliced = [item.nodeid for item, session in zip(ordered, sessions) if session is None]
    assert unsliced == [item.nodeid for item in (*rows, *keys, *companions)
                        if _registered_name_of(item) not in aes_event.SLICED_ROWS]


def _registered_name_of(item):
    """The registered row a fake Tier 3 item is about, whichever way it is parametrized."""
    params = item.callspec.params
    if "row" in params:
        return params["row"].registered
    return params["name"] if "name" in params else test_tier3.ROWS_BY_KEY[params["key"]].registered
