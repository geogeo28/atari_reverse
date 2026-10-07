"""`fork_pool.over_forks` held to its promise: a pass over forks ENDS — with every share's answer, or by name."""
import os
import signal
import time

import pytest

import fork_pool

JOBS = 3
A_PASS_THAT_HANGS_IS_ENDED_WITHIN_SECONDS = 30
STUCK_AFTER_SECONDS = 1.0
# What a stuck share sleeps: twice the bound a pass is held to — so a pass that WAITED for it (not ended by name, or
# ended and then joined) is past the bound when it comes back, and fails here rather than hanging the suite.
A_STUCK_SHARE_SLEEPS_SECONDS = 2 * A_PASS_THAT_HANGS_IS_ENDED_WITHIN_SECONDS


def _squared(number):
    return os.getpid(), number * number


def test_every_share_is_made_once_in_a_fork_and_answered_under_its_own_place():
    shares = list(range(40))
    made = fork_pool.over_forks(_squared, shares, JOBS, A_PASS_THAT_HANGS_IS_ENDED_WITHIN_SECONDS, "a pass")
    assert sorted(made) == shares and [made[nth][1] for nth in shares] == [number * number for number in shares]
    makers = {pid for pid, _answer in made.values()}
    assert os.getpid() not in makers and 1 <= len(makers) <= JOBS


def _refusing_seven(number):
    assert number != 7, "seven is refused"
    return number


def test_what_a_share_raises_is_raised_here():
    with pytest.raises(AssertionError, match="seven is refused"):
        fork_pool.over_forks(_refusing_seven, range(12), JOBS, A_PASS_THAT_HANGS_IS_ENDED_WITHIN_SECONDS, "a pass")


def _killed_at_five(number):
    if number == 5:
        os.kill(os.getpid(), signal.SIGKILL)
    return number


def test_a_fork_that_dies_ends_the_pass_by_name_and_does_not_hang_it():
    """THE RED for a pool that loses a dead worker's share and waits for it for ever (`multiprocessing.Pool`: still
    waiting after 45 s, measured): the pass ends, saying a fork died and that no verdict was reached."""
    started = time.monotonic()
    with pytest.raises(fork_pool.Died, match=r"the bench: a fork DIED before it answered .* never came back"):
        fork_pool.over_forks(_killed_at_five, range(12), JOBS, A_PASS_THAT_HANGS_IS_ENDED_WITHIN_SECONDS, "the bench")
    assert time.monotonic() - started < A_PASS_THAT_HANGS_IS_ENDED_WITHIN_SECONDS


def _stuck_at_two(number):
    if number == 2:
        time.sleep(A_STUCK_SHARE_SLEEPS_SECONDS)
    return os.getpid()


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_a_pass_no_share_comes_back_from_is_ended_by_name_and_its_forks_killed():
    """...and a fork that neither answers nor dies: once nothing has come back for the pass's own time, it is ended
    by name with the share still out, and no fork of it is left behind to be waited on at exit."""
    started = time.monotonic()
    with pytest.raises(fork_pool.Stuck, match=r"the bench: no share came back in 1.0 s — 1 of 6 still out, the first 2"):
        fork_pool.over_forks(_stuck_at_two, range(6), JOBS, STUCK_AFTER_SECONDS, "the bench")
    assert time.monotonic() - started < A_PASS_THAT_HANGS_IS_ENDED_WITHIN_SECONDS
    forks = set(fork_pool.over_forks(_stuck_at_two, [0, 1, 3], JOBS, A_PASS_THAT_HANGS_IS_ENDED_WITHIN_SECONDS, "a pass").values())
    assert forks and not any(_alive(pid) for pid in forks), "a finished pass left a fork running"
