"""How the suite is SPREAD over xdist's workers, and its collection ORDER — where either decides the cost.

THE DISTRIBUTION. xdist's default `load` hands each worker a contiguous run of tests up front — some 450 here — and
this suite's cost is not spread evenly: one file of whole file-selector SESSIONS (seconds each, where most tests take
milliseconds) landed on one worker, which ran it alone while the other nine idled (measured: 397 s of wall for 391 s
of that one file). `worksteal` lets an idle worker take tests from the longest queue. It is set HERE and not in a
makefile's PYTEST_ARGS, which every override replaces (`make test PYTEST_ARGS="-n4 -k fuzz"`): any run under xdist
that names no `--dist` of its own gets it, and a run without xdist (`-p no:xdist`, where the option does not exist) is
left alone.

THE ORDER. What a SESSION costs is paid once per process and shared by its cases: the file selector's is derived once
(`aes_fs_sessions.machine_of`: the ROM's own run of it over the staged disk, the replay's script) and its C runs in ONE
child (`aes_fs_sessions.taken`); a priced session's slice rows are measured off one pair of runs (`tier3.Sessions`) and
share one companion. Collected in pytest's own order — every session through one test function, then every session
through the next — the cases of one session are a file apart, and a steal hands the far ones to another worker: each
then derives the session again (measured: the second function's cases 80 s summed on one worker, 164 s spread over
ten). So the cases of ONE session are collected back to back, where the first of them stood; a steal takes a queue's
tail half, which splits a group only at its one boundary.

WHICH CASES ARE ONE SESSION'S is the test's to say, not this file's: the marker `collected_with` — on a test, or on a
whole module (`pytestmark`) — as `collected_with(name)`, the group's name, or `collected_with(by=function)`, a function
of the case's parameters answering its group's name (None: the case is no session's; a keyword, because pytest takes
a mark called with one function for that function's decorator). Nothing is added, removed or renamed: the same items,
the same ids — only their order inside their own module.

THE GUARD'S ZYGOTE (`zygote.py`, `aes_event.guard_fork`) is forked HERE, as the session starts in a process that will
run tests — an xdist worker, or the one process of a run without xdist — because what a fork costs is what its parent
holds, and at this moment the process holds the harness and nothing else: the batteries' registries (hundreds of
megabytes) are imported by the collection that follows. The controller of an xdist run, and a run that only collects,
make none; nor does any process with AES_NO_ZYGOTE in its environment — every fork is then the worker's own, as it
was before there was a zygote (the A/B a change to the mechanism is measured and held equal by).

A TEST THAT PATCHES ANYTHING DERIVES EVERYTHING ITSELF, AND FORKS FOR ITSELF. `derived.kept` serves a ROM-only
derivation from disk by the content of the tree, the base image and its arguments — and a test that takes
`monkeypatch` may change what none of those sees: a module's budget, a function a derivation calls, a counter on the
derivations made. And the zygote makes a guard's fork out of the modules as IT holds them, frozen when the session
started: an attribute a test patches on the fork's side (`arm_candidate`, a refuser, a seed) is seen by the worker's
own fork and never by the zygote's (measured: a patched arming that raises — exit 8 from the worker's fork, 0 from the
zygote's, where the patch never ran). So for every such test BOTH are put out of use, for the test alone
(`derived.DERIVED_OFF`, `aes_event.ZYGOTE_SIDELINED`): what it asks is made, and forked, under its patches. A test
that MEANS the zygote while it patches the worker's side says so (`aes_event.ZYGOTE_SIDELINED` back to False).

THE TREE'S KEY (`derived.py`) names the tree THIS PROCESS IS MADE OF, so `derived` is this file's FIRST import: it
stamps the tree's files as the process finds them, before any module that derives is read. What was read before it
(this file, the kit's plugins named on the command line) is held by the other half of that rule — nothing is kept for
a process a file changed under since it began.

WHAT THE CACHE WAS HELD TO in a run is said at its end: how many of the answers its processes were served they made
again and found equal (`derived.SAMPLED`), summed over the workers.
"""
import derived                          # FIRST (above): the tree stamped before anything that derives is imported

import os
import sys

import pytest

STEALING = "worksteal"
XDIST_S_OWN_DEFAULT = "load"           # what `-n` alone makes of `--dist` (xdist's `pytest_cmdline_main`)
GROUP_MARKER = "collected_with"


def _names_a_distribution(arguments):
    """Did the command line choose a `--dist` (or its short form `-d`) itself?"""
    return any(argument in ("--dist", "-d") or argument.startswith("--dist=") for argument in arguments)


def pytest_configure(config):
    config.addinivalue_line("markers", f"{GROUP_MARKER}(name) / {GROUP_MARKER}(by=function): the cases of one session, "
                                       f"collected back to back — by the group's name, or a function of a case's "
                                       f"parameters answering it")
    if getattr(config.option, "dist", None) == XDIST_S_OWN_DEFAULT and not _names_a_distribution(config.invocation_params.args):
        config.option.dist = STEALING


def group_of(item):
    """The group `item` is collected with — `(its module, the key its marker answers)` — or None for every other
    item: one with no marker, one whose marker's function answers None, an item that is no test function's (a
    doctest's, a plugin's own: no parameters to ask)."""
    marker = item.get_closest_marker(GROUP_MARKER)
    if marker is None:
        return None
    if "by" in marker.kwargs:
        key = marker.kwargs["by"](getattr(getattr(item, "callspec", None), "params", {}))
    else:
        key, = marker.args
    return None if key is None else (item.nodeid.partition("::")[0], key)


def grouped(items, group_of=group_of):
    """`items` with each group's members moved up behind the first of them; every other item stays where it was."""
    groups = [group_of(item) for item in items]
    members = {}
    for item, group in zip(items, groups):
        if group is not None:
            members.setdefault(group, []).append(item)
    ordered, placed = [], set()
    for item, group in zip(items, groups):
        if group is None:
            ordered.append(item)
        elif group not in placed:
            placed.add(group)
            ordered.extend(members[group])
    return ordered


def pytest_collection_modifyitems(items):
    items[:] = grouped(items)


NO_ZYGOTE = "AES_NO_ZYGOTE"


def _runs_tests(config):
    """Will THIS process run tests — a worker, or a session with no workers — rather than only hand them out?"""
    return hasattr(config, "workerinput") or not getattr(config.option, "numprocesses", None)


def pytest_sessionstart(session):
    config = session.config
    if _runs_tests(config) and not config.option.collectonly and not os.environ.get(NO_ZYGOTE):
        import aes_event
        aes_event.start_the_guard_s_zygote()


@pytest.fixture(autouse=True)
def a_test_that_patches_derives_and_forks_for_itself(request):
    if "monkeypatch" in request.fixturenames:
        monkeypatch = request.getfixturevalue("monkeypatch")
        monkeypatch.setenv(derived.DERIVED_OFF, "patched: this test derives for itself")
        aes_event = sys.modules.get("aes_event")
        if aes_event is not None:
            monkeypatch.setattr(aes_event, "ZYGOTE_SIDELINED", True)


# ---- what the cache was held to, said at the run's end -----------------------------------------------------------------
SAMPLED_BY_A_WORKER = "derived_sampled"
_SAMPLED_BY_WORKERS = []


def pytest_sessionfinish(session):
    aes_event = sys.modules.get("aes_event")
    if aes_event is not None:
        aes_event.stop_the_guard_s_zygote()
    if hasattr(session.config, "workeroutput"):
        session.config.workeroutput[SAMPLED_BY_A_WORKER] = len(derived.SAMPLED)


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    _SAMPLED_BY_WORKERS.append(getattr(node, "workeroutput", {}).get(SAMPLED_BY_A_WORKER, 0))


def pytest_terminal_summary(terminalreporter):
    sampled = _SAMPLED_BY_WORKERS or [len(derived.SAMPLED)]
    terminalreporter.write_line(f"derived: {sum(sampled)} kept answers made again and found equal, in {len(sampled)} "
                                f"process{'es' if len(sampled) > 1 else ''} (`derived.SAMPLED`)")
