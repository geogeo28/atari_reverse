"""WORK SPREAD OVER FORKS OF THIS PROCESS — a pass that ENDS, whatever a fork does.

The bench's measuring pass and the derivations' warming pass each hand a list of shares to forks of the process that
holds the registry (a fork inherits it; nothing is imported twice). `multiprocessing.Pool` was the first spelling,
and a Pool whose worker DIES — a segfault of the oracle, an out-of-memory kill — starts another worker and loses the
share: `imap_unordered` waits for it for ever, and `make bench` is a prerequisite of every gate (measured: a row whose
measurement SIGSEGVs, still waiting after 45 s). Here a dead fork ENDS the pass, by name (`Died`); a pass in which no
share came back for `seconds` ends too, its forks killed (`Stuck`); and what comes back is held to be every share
asked for, each once.
"""
import concurrent.futures
import multiprocessing
from concurrent.futures.process import BrokenProcessPool


class Died(RuntimeError):
    """A fork of the pass died before it answered."""


class Stuck(RuntimeError):
    """No share of the pass came back within its time."""


def _kill_the_forks_of(pool):
    """A fork that is stuck would otherwise be joined as the pool closes, and again at this process's exit, for ever."""
    for process in list((getattr(pool, "_processes", None) or {}).values()):
        process.kill()


def over_forks(function, shares, jobs, seconds, what):
    """`{nth: function(shares[nth])}` for EVERY share, each made in one of `jobs` forks of this process. `what` names
    the pass in a failure; `seconds` is how long the pass may go with NO share coming back — the longest share's own
    time, with a loaded machine's margin."""
    shares, made = list(shares), {}
    with concurrent.futures.ProcessPoolExecutor(jobs, mp_context=multiprocessing.get_context("fork")) as pool:
        pending = {pool.submit(function, share): nth for nth, share in enumerate(shares)}
        try:
            while pending:
                done, _waiting = concurrent.futures.wait(pending, timeout=seconds,
                                                         return_when=concurrent.futures.FIRST_COMPLETED)
                if not done:
                    raise Stuck(f"{what}: no share came back in {seconds} s — {len(pending)} of {len(shares)} still "
                                f"out, the first {shares[min(pending.values())]!r}; its forks were killed")
                for future in done:
                    made[pending[future]] = future.result()
                    del pending[future]
        except BrokenProcessPool as broken:
            out = sorted(pending.values())
            raise Died(f"{what}: a fork DIED before it answered (a signal: a segfault, a kill) — {len(out)} of "
                       f"{len(shares)} shares never came back, the first {shares[out[0]]!r}: no verdict on any of "
                       f"them") from broken
        finally:
            if pending:
                _kill_the_forks_of(pool)
    assert sorted(made) == list(range(len(shares))), f"{what}: the shares that came back are not the shares asked"
    return made
