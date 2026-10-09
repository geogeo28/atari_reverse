"""The record-and-refuse hook's own guarantees (`test/address_hook.py`), each pinned by one claim.

The batteries that use the hook exercise it only on its happy path: no green case reaches a key nothing
staged, calls outside a pass, or loops past the cap — those are the defects the hook exists to catch,
so a battery never shows them. These claims drive the REAL door, Supexec's `recreate_call_routine`
through the real core, with no differential around it: what is under test is the hook, not the ROM.
Every claim stages inside `staged()`, so nothing it installs outlives it.
"""
import contextlib
import ctypes

import pytest

import address_hook
import gemdos
import gemdos_fs
import isr
import test_xbios_supexec as supexec
from harness import _lib

HOOK = supexec.HOOK
NAMED = supexec.STUB_AT
OTHER = supexec.STUB_AT + supexec.DECOY_ALTERNATIVES[0]
NAMED_RESULT = 0x1111_1111
OTHER_RESULT = 0x2222_2222
# The candidate's image, for a core that only hands it on to the hook: one byte, which each effect
# marks so a claim can see whether it ran.
IMAGE_BYTES = 1
UNMARKED, NAMED_MARK, OTHER_MARK = 0, 1, 2
REFUSAL_REPORT = "refused by the hook"


def effect(mark, result):
    def routine(buf):
        buf[0] = mark
        return result
    return routine


BOTH = {NAMED: effect(NAMED_MARK, NAMED_RESULT), OTHER: effect(OTHER_MARK, OTHER_RESULT)}


def staged(effects=BOTH):
    return HOOK.staged(effects, lambda refused: f"{REFUSAL_REPORT}: {refused}")


def refusal_expected():
    """A claim that makes the hook refuse ends its `staged()` block in the refusal report."""
    return pytest.raises(AssertionError, match=REFUSAL_REPORT)


def fresh_image():
    return (ctypes.c_ubyte * IMAGE_BYTES)()


def call(buf, routine):
    return _lib.xbios_supexec(buf, routine)


def in_one_pass(*routines):
    """Every routine in `routines`, called by the core inside ONE recorded pass."""
    buf = fresh_image()
    results = HOOK.recording(lambda lib, image: [call(image, at) for at in routines])(_lib, buf)
    return results, buf


def test_a_call_is_served_by_the_effect_staged_at_its_own_key():
    with staged():
        results, buf = in_one_pass(OTHER)
    assert results == [OTHER_RESULT] and buf[0] == OTHER_MARK
    assert HOOK.calls == [(OTHER,)] and not HOOK.refused


def test_a_key_nothing_staged_is_refused_recorded_and_reported():
    with refusal_expected(), staged({NAMED: effect(NAMED_MARK, NAMED_RESULT)}):
        results, buf = in_one_pass(OTHER)
    assert results == [address_hook.REFUSED_ANSWER] and buf[0] == UNMARKED
    assert HOOK.refused == [OTHER]


# THE THREE TESTS THAT CALL THE HOOK WHILE NO PASS IS OPEN, ON PURPOSE (`address_hook.OUTSIDE_A_PASS`: any other test
# that does fails at its teardown, `conftest.py`).
CALLS_OUTSIDE_A_PASS_ON_PURPOSE = ("test_a_call_before_any_pass_is_refused_even_with_its_key_staged",
                                   "test_a_call_after_a_finished_pass_is_refused_and_not_recorded",
                                   "test_a_pass_closes_even_when_its_run_raises")


def test_a_call_before_any_pass_is_refused_even_with_its_key_staged():
    buf = fresh_image()
    with refusal_expected(), staged():
        assert call(buf, NAMED) == address_hook.REFUSED_ANSWER
    assert buf[0] == UNMARKED, "a call no case was running was served out of the staged table"
    assert HOOK.refused == [NAMED] and HOOK.calls == []


def test_a_call_after_a_finished_pass_is_refused_and_not_recorded():
    """The pass CLOSES: a stray call once the run is over is not served out of the case's table and
    not appended to the case's own `calls`."""
    buf = fresh_image()
    with refusal_expected(), staged():
        in_one_pass(NAMED)
        assert call(buf, NAMED) == address_hook.REFUSED_ANSWER
    assert buf[0] == UNMARKED
    assert HOOK.refused == [NAMED] and HOOK.calls == [(NAMED,)]


def test_a_pass_closes_even_when_its_run_raises():
    with refusal_expected(), staged():
        with contextlib.suppress(ZeroDivisionError):
            HOOK.recording(lambda lib, image: 1 // 0)(_lib, fresh_image())
        call(fresh_image(), NAMED)
    assert HOOK.refused == [NAMED]


def test_an_effect_that_raises_fails_the_case_by_name():
    """A ctypes callback cannot raise through to its C caller, so an effect's own refusal (an assertion) is
    recorded and the case fails on the way out — rather than printed and answered, the run carrying on green."""
    def refusing(_buf):
        raise AssertionError("this effect refuses")
    with pytest.raises(AssertionError, match="this effect refuses"), staged({NAMED: refusing}):
        results, _buf = in_one_pass(NAMED)
    assert results == [address_hook.REFUSED_ANSWER]


class _NoException(BaseException):
    """Something an effect might raise that is no `Exception`."""


WHAT_IS_NO_EXCEPTION = {"pytest.fail": pytest.fail.Exception("a vet inside the effect"),
                        "a BaseException": _NoException("a vet inside the effect")}


@pytest.mark.parametrize("raised", WHAT_IS_NO_EXCEPTION.values(), ids=WHAT_IS_NO_EXCEPTION)
def test_an_effect_that_raises_what_is_no_exception_fails_the_case_all_the_same(raised):
    """RED while the hook recorded an `Exception` alone: `pytest.fail` inside an effect — a vet it makes — raises a
    BaseException that is none, which left the hook's `except`, was printed by ctypes ("Exception ignored on
    calling ctypes callback") and the case passed GREEN, the effect's work done and its refusal lost. Recorded like
    any other: the call is answered as a refused one, and the case fails by the effect's own words."""
    def refusing(buf):
        buf[0] = NAMED_MARK
        raise raised
    with pytest.raises(AssertionError, match=f"the effect staged at {NAMED:#x} raised {type(raised).__name__}: "
                                             f"a vet inside the effect") as failed:
        with staged({NAMED: refusing}):
            results, buf = in_one_pass(NAMED)
    assert results == [address_hook.REFUSED_ANSWER] and buf[0] == NAMED_MARK, "the effect ran, and raised after its work"
    assert HOOK.raised == [(NAMED, raised)] and failed.value.__cause__ is raised


def _an_effect_that_raises(raised):
    def effect(buf):
        buf[0] = NAMED_MARK
        raise raised
    return effect


def test_an_effect_s_failure_names_its_type_and_where_it_was_raised():
    """RED while the message was `str(raised)`: a bare `assert` in a helper, a KeyboardInterrupt, a KeyError read
    "raised: " with nothing after the colon or a bare key — no type, no line. The failure names the exception's
    TYPE and carries its traceback, down to the line of the effect that raised."""
    def vetting(_buf):
        assert HOOK.calls is None                       # an assert with no message of its own
    with pytest.raises(AssertionError, match="raised AssertionError: ") as failed:
        with staged({NAMED: vetting}):
            in_one_pass(NAMED)
    assert "in vetting" in str(failed.value) and "assert HOOK.calls is None" in str(failed.value)
    with pytest.raises(AssertionError, match="raised KeyError: 'a key no table holds'"):
        with staged({NAMED: _an_effect_that_raises(KeyError("a key no table holds"))}):
            in_one_pass(NAMED)


@pytest.mark.parametrize("stop", [KeyboardInterrupt(), SystemExit(3), pytest.exit.Exception("the user's own pytest.exit")],
                         ids=["Ctrl-C", "an exit", "pytest.exit"])
def test_what_stops_the_session_inside_an_effect_stops_it_once_the_c_has_returned(stop):
    """RED while it was recorded as one more failure (and, before that, printed by ctypes and the test PASSED): a
    Ctrl-C that landed inside an effect made one red line with an empty reason and the session went on to the next
    test. It cannot cross the C callback — the call is answered as a refused one — and it is RAISED AGAIN, itself,
    where the binding closes: even when the run has by then failed for a reason of its own."""
    with pytest.raises(type(stop)) as stopped:
        with staged({NAMED: _an_effect_that_raises(stop)}):
            results, _buf = in_one_pass(NAMED)
    assert stopped.value is stop and results == [address_hook.REFUSED_ANSWER]
    with pytest.raises(type(stop)) as stopped:
        with staged({NAMED: _an_effect_that_raises(stop)}):
            in_one_pass(NAMED)
            raise AssertionError("what the run then failed by: the final image differs")
    assert stopped.value is stop


PYTEST_S_OWN_OUTCOMES = {"a skip": lambda: pytest.skip.Exception("this machine has no blitter"),
                         "an xfail": lambda: pytest.xfail.Exception("a known defect of the ROM's")}


@pytest.mark.parametrize("outcome", PYTEST_S_OWN_OUTCOMES.values(), ids=PYTEST_S_OWN_OUTCOMES)
def test_an_outcome_pytest_is_asked_for_inside_an_effect_is_that_outcome(outcome):
    """...and `pytest.skip` inside an effect skips the case — it was FAILED, "raised: skip me" — as `pytest.xfail`
    xfails it: each raised again ITSELF where the binding closes (an xfail is a `Failed` to pytest's own classes:
    told apart, or it reads as a failure)."""
    asked = outcome()
    with pytest.raises(type(asked)) as raised:
        with staged({NAMED: _an_effect_that_raises(asked)}):
            in_one_pass(NAMED)
    assert raised.value is asked


def test_calls_holds_the_first_pass_alone():
    with staged():
        in_one_pass(NAMED)
        in_one_pass(OTHER)
    assert HOOK.calls == [(NAMED,)], "the attribution pass's calls leaked into the plain pass's list"


def test_a_later_pass_is_still_served():
    with staged():
        in_one_pass(NAMED)
        results, buf = in_one_pass(OTHER)
    assert results == [OTHER_RESULT] and buf[0] == OTHER_MARK


def test_one_pass_records_no_more_than_the_cap():
    with staged():
        in_one_pass(*[NAMED] * (address_hook.CALLS_MAX + 1))
    assert len(HOOK.calls) == address_hook.CALLS_MAX


def test_the_ledgers_outlive_the_block_but_the_table_does_not():
    with staged():
        in_one_pass(NAMED)
    assert HOOK.calls == [(NAMED,)]
    results, buf = in_one_pass(NAMED)
    assert results == [address_hook.REFUSED_ANSWER] and buf[0] == UNMARKED
    assert HOOK.refused == [NAMED]


def test_staging_starts_every_ledger_empty():
    with refusal_expected(), staged({}):
        in_one_pass(NAMED)
    with staged():
        assert HOOK.calls == [] and HOOK.refused == []


def test_the_module_aliases_survive_staging():
    """`staged()` CLEARS the ledgers and never rebinds them — these aliases are what the batteries read."""
    for alias, hook in ((isr.CALLS, isr._HOOK), (gemdos.HANDLER_CALLS, gemdos._HANDLER_HOOK),
                        (gemdos_fs.DISK_CALLS, gemdos_fs._DISK_HOOK)):
        with hook.staged({}, str):
            pass
        assert alias is hook.calls


def test_a_call_outside_a_pass_is_kept_for_its_test_s_teardown():
    """WHAT MAKES AN UNBOUND DOOR LOUD: a call while no pass is open is kept in `address_hook.OUTSIDE_A_PASS` by the
    pointer's symbol and its key — where `refused` is cleared by the next case's `staged()`, unread — and the fixture
    that reads it at every test's teardown (`conftest.py`) lets these three by name alone."""
    assert set(CALLS_OUTSIDE_A_PASS_ON_PURPOSE) <= set(globals())
    before = list(address_hook.OUTSIDE_A_PASS)
    call(fresh_image(), NAMED)
    assert address_hook.OUTSIDE_A_PASS == before + [(HOOK.symbol, NAMED)]
    with staged():
        pass
    assert HOOK.refused == [] and address_hook.OUTSIDE_A_PASS == before + [(HOOK.symbol, NAMED)]
    address_hook.OUTSIDE_A_PASS.clear()     # this test's own call: read here, not left for its teardown


# ---- ...AND IN A PROCESS NOBODY READS THE RECORD OF, THE CALL ENDS IT BY NAME -------------------------------------------------
def _ended_by_name(returncode, stderr):
    return returncode == address_hook.OUTSIDE_A_PASS_STATUS and address_hook.OUTSIDE_A_PASS_SAID in stderr and HOOK.symbol in stderr


def test_a_call_outside_a_pass_in_a_fork_ends_the_fork_by_name():
    """A FORK OF THE WORKER LEFT SERVING THE HOOK (the guard's fork made at the call, the zygote's, a model's): its
    record is its own copy and dies with it — so the call ends the fork at once, with a status of its own and the
    hook's symbol and key on its stderr, which the fork's parent reads as its case's failure. And the worker's own
    record is untouched: the fork's call is not this test's."""
    import aes_event

    returncode, stderr = aes_event.in_a_fork(lambda: call(fresh_image(), NAMED), serves=aes_event.EVERY_HOOK_OF_THE_PASS)
    assert _ended_by_name(returncode, stderr) and f"{NAMED:#x}" in stderr, (returncode, stderr)
    assert address_hook.OUTSIDE_A_PASS_STATUS not in aes_event._CHILD_STATUSES + (0,)
    assert address_hook.OUTSIDE_A_PASS == []


A_FRESH_INTERPRETER_S_CALL = ("import ctypes, test_xbios_supexec as supexec; from harness import _lib; "
                              "_lib.xbios_supexec((ctypes.c_ubyte * 1)(), supexec.STUB_AT)")


def test_a_call_outside_a_pass_in_a_fresh_interpreter_ends_it_by_name():
    """A FRESH INTERPRETER (a door user's child): no fixture of pytest's runs there, so nobody reads its record —
    the same end, by name."""
    import os
    import subprocess
    import sys

    child = subprocess.run([sys.executable, "-c", A_FRESH_INTERPRETER_S_CALL], capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}, timeout=60)
    assert _ended_by_name(child.returncode, child.stderr), (child.returncode, child.stderr[-600:])


def test_the_record_is_taken_once():
    """`taken()` hands the record to its one reader and empties it: a record read at a test's setup is not read
    again at its teardown, and one made before a test is that test's error (`conftest.py`), never cleared unread."""
    call(fresh_image(), NAMED)
    assert address_hook.taken() == [(HOOK.symbol, NAMED)] and address_hook.taken() == []
    assert address_hook.said([(HOOK.symbol, NAMED)]) == f"{HOOK.symbol} at {NAMED:#x}"

