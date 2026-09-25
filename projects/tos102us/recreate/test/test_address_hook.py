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
