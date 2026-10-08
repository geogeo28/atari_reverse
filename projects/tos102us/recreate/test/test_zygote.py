"""`zygote.py`'s own mechanism, over zygotes of this file's (each test makes its own, served by a function here): what
crosses the pipes and the shared image, what a zygote holds of its parent, and how it ends. What the GUARD asks of its
zygote — which forks it may make for a worker, and that each is the fork the worker would have made — is
`test_aes_event.py`'s.
"""
import ctypes
import ctypes.util
import mmap
import os
import select
import signal
import sys
import threading
import time

import pytest

import zygote
from recreate_kit.guarded_image import GUARD_ABOVE, GUARD_BELOW

IMAGE_BYTES = 0x10000                   # a small image: the mechanism is the same at any size
SERVED_BY = f"{__name__}:_served"
A_BYTE_AT, A_BYTE, ANOTHER_BYTE = 0x1234, 0x5A, 0xA5
GONE_WITHIN_SECONDS = 4 * zygote.PARENT_POLL_SECONDS


def _served(buffer, request):
    """What this file's zygotes do with a request, IN THE ZYGOTE."""
    what, *arguments = request
    if what == "echo":
        return arguments
    if what == "pid":
        return os.getpid(), os.getppid()
    if what == "peek":
        return buffer[arguments[0]]
    if what == "poke":
        buffer[arguments[0]] = arguments[1]
        return None
    if what == "holds":
        return [fd for fd in arguments[0] if _is_open(fd)]
    if what == "raise":
        raise RuntimeError("raised in the zygote")
    if what == "say":                   # ...on the zygote's own stderr, no newline: left in its buffer, unflushed
        print(arguments[0], end="", file=sys.stderr)
        return None
    if what == "a fork's stderr":
        return _what_a_fork_writes_as_it_takes_its_own_stderr()
    if what == "die":
        os._exit(1)
    raise AssertionError(f"no such request: {what}")


def _what_a_fork_writes_as_it_takes_its_own_stderr():
    """IN THE ZYGOTE: fork; the fork makes a pipe its descriptor 2 and replaces `sys.stderr` — as every fork that
    reports to its parent does — and leaves at once. What came down the pipe: nothing the fork itself wrote."""
    reading, writing = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(reading)
        os.dup2(writing, zygote.STDERR_FD)
        sys.stdout = sys.stderr = open(zygote.STDERR_FD, "w", buffering=1, closefd=False)   # the old object goes, flushed
        os._exit(0)
    os.close(writing)
    with os.fdopen(reading, "rb") as said:
        written = said.read().decode()
    os.waitpid(pid, 0)
    return written


def _is_open(fd):
    try:
        os.fstat(fd)
    except OSError:
        return False
    return True


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _awaited(happened, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if happened():
            return True
        time.sleep(0.05)
    return happened()


@pytest.fixture
def made():
    """A zygote of the test's own, stopped when the test ends."""
    zygotes = []

    def make(**named):
        zygotes.append(zygote.Zygote(IMAGE_BYTES, SERVED_BY, **named))
        return zygotes[-1]
    yield make
    for each in zygotes:
        each.stop()
        assert _awaited(lambda: not _alive(each.pid), GONE_WITHIN_SECONDS), f"the zygote {each.pid} outlived its test"


def test_a_request_is_served_in_another_process_whose_parent_is_this_one(made):
    its = made()
    assert its.ask(("echo", 1, b"two", (3,))) == [1, b"two", (3,)]
    assert its.ask(("pid",)) == (its.pid, os.getpid()) and its.pid != os.getpid()


def test_the_image_is_one_mapping_the_two_processes_share(made):
    """The image a request names is COPIED into the mapping before the request is served, the zygote reads it there,
    and what the zygote stores there this process reads back (`image`); a request that names none finds the mapping
    as the last one left it."""
    its = made()
    staged = (ctypes.c_uint8 * IMAGE_BYTES)()
    staged[A_BYTE_AT] = A_BYTE
    assert its.ask(("peek", A_BYTE_AT), ctypes.addressof(staged)) == A_BYTE
    its.ask(("poke", A_BYTE_AT, ANOTHER_BYTE))
    assert its.image()[A_BYTE_AT] == ANOTHER_BYTE and len(its.image()) == IMAGE_BYTES
    assert staged[A_BYTE_AT] == A_BYTE, "the request's own image is copied, never written through"
    assert its.ask(("peek", A_BYTE_AT)) == ANOTHER_BYTE


def test_a_serving_function_that_raises_fails_the_request_by_its_traceback_and_the_zygote_goes_on(made):
    its = made()
    with pytest.raises(AssertionError, match="(?s)the zygote's own Python raised.*raised in the zygote") as failed:
        its.ask(("raise",))
    assert "Traceback" in str(failed.value)
    assert its.ask(("echo", "still there")) == ["still there"]


def test_what_the_zygote_itself_printed_is_in_no_fork_s_stderr(made):
    """RED before the zygote's own stderr was line-buffered and flushed as each request is served: a line the
    ZYGOTE had printed and not yet written (a hook's module warning at import; here a line with no newline) stayed
    in its `sys.stderr`'s buffer, every fork inherited the buffer, and wrote it out as its own stderr — a fork's
    refusal read by its parent began with the zygote's words."""
    its = made()
    its.ask(("say", "the zygote's own words"))
    assert its.ask(("a fork's stderr",)) == ""
    assert its.ask(("a fork's stderr",)) == ""


def test_a_zygote_that_died_is_gone_by_name_and_stays_gone(made):
    its = made()
    with pytest.raises(zygote.Gone, match=f"the zygote \\(pid {its.pid}\\) is gone"):
        its.ask(("die",))
    assert not its.running() and not _alive(its.pid), "a dead zygote is reaped"
    with pytest.raises(zygote.Gone, match="has no zygote"):
        its.ask(("echo",))


def test_a_stopped_zygote_is_reaped(made):
    its = made()
    assert _alive(its.pid)
    its.stop()
    assert not its.running() and not _alive(its.pid)
    its.stop()                          # ...and stopping it again is nothing


NEVER_SECONDS = 600                     # what a stuck zygote or fork sleeps: far past every bound held here


def _stuck(buffer, request):
    """A zygote's whole service: it never comes back from its first request."""
    time.sleep(NEVER_SECONDS)


def test_stopping_a_zygote_that_does_not_leave_kills_it():
    """`stop` closes the pipes and the zygote leaves at its next read — and one that does not (here: stuck in a
    request nobody is waiting for) is killed after STOP_SECONDS, so no session's end waits on a zygote for ever.
    (The stop is made on a thread of its own, so a stop that DID wait for ever fails this test instead of hanging
    it.)"""
    its = zygote.Zygote(IMAGE_BYTES, f"{__name__}:_stuck")
    zygote._send(its._requests, ("anything",))     # ...taken, never answered: the zygote is in its service now
    began = time.monotonic()
    stopping = threading.Thread(target=its.stop, daemon=True)
    stopping.start()
    stopping.join(zygote.STOP_SECONDS + GONE_WITHIN_SECONDS)
    stopped_after, still_stopping = time.monotonic() - began, stopping.is_alive()
    if _alive(its.pid):
        os.kill(its.pid, signal.SIGKILL)        # a RED run must not leave the stuck zygote it proves
    assert not still_stopping, "stopping a zygote that does not leave waited on it for ever"
    assert zygote.STOP_SECONDS <= stopped_after, "the zygote was killed before it was given its time to leave"


def test_a_zygote_holds_none_of_its_parent_s_descriptors(made):
    """An xdist worker's channel to its controller is a descriptor every fork of the worker inherits: held open in a
    zygote, the controller would not see the worker die. Shown with a pipe opened BEFORE the zygote is made: the
    zygote holds neither end — and the pipe reads END OF FILE the moment this process closes its writing end."""
    reading, writing = os.pipe()
    its = made()
    assert its.ask(("holds", (reading, writing))) == []
    os.close(writing)
    ready, _, _ = select.select([reading], [], [], GONE_WITHIN_SECONDS)
    assert ready and os.read(reading, 1) == b"", "another process still holds the pipe's writing end"
    os.close(reading)


def test_a_fork_of_the_parent_has_no_zygote(made):
    """A zygote is its MAKER's: in a fork of the maker — the worker's own forks are made beside it — `running` is
    False and `ask` refuses, so two processes never write one zygote's pipes."""
    its = made()
    reading, writing = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            said = b"N" if not its.running() else b"Y"
            try:
                its.ask(("echo",))
            except zygote.Gone:
                said += b"G"
            os.write(writing, said)
        finally:
            os._exit(0)
    os.close(writing)
    os.waitpid(pid, 0)
    assert os.read(reading, 2) == b"NG"
    os.close(reading)
    assert its.ask(("echo", "the maker's still")) == ["the maker's still"]


A_FORK_S_LIFE_SECONDS = 20              # how long the parent's other fork lives on: far past the bound held below


def _a_parent_that_makes_a_zygote_and_waits(told):
    """A fork of this test: it makes a zygote, then ANOTHER fork of its own that lives on (as a worker's own guard
    fork may, for its alarm's ten seconds: it holds every descriptor its parent held, the writing end of the zygote's
    request pipe among them) — tells both pids on `told`, and sleeps until it is killed."""
    pid = os.fork()
    if pid:
        return pid
    try:
        its = zygote.Zygote(IMAGE_BYTES, SERVED_BY)
        other = os.fork()
        if other == 0:
            signal.alarm(A_FORK_S_LIFE_SECONDS)
            time.sleep(A_FORK_S_LIFE_SECONDS)
            os._exit(0)
        os.write(told, f"{its.pid} {other}\n".encode())
        time.sleep(NEVER_SECONDS)
    finally:
        os._exit(0)


@pytest.mark.parametrize("ended_by", (signal.SIGKILL, signal.SIGTERM), ids=("killed", "terminated"))
def test_a_zygote_whose_parent_dies_is_gone_within_a_poll(ended_by):
    """THE ORPHAN'S BOUND: a parent that dies closes no pipe while a fork of it lives — the fork holds the writing end
    for its own ten seconds — so the zygote asks who its parent is every PARENT_POLL_SECONDS and leaves when it is no
    longer the process that made it. Shown with such a fork ALIVE when the parent is killed: the pipe stays open, and
    only the poll ends the zygote."""
    reading, writing = os.pipe()
    parent = _a_parent_that_makes_a_zygote_and_waits(writing)
    os.close(writing)
    try:
        with os.fdopen(reading) as told:
            orphan, other = (int(pid) for pid in told.readline().split())
        assert _alive(orphan), "the premise: the zygote is there while its parent lives"
    finally:
        os.kill(parent, ended_by)
        os.waitpid(parent, 0)
    gone = _awaited(lambda: not _alive(orphan), GONE_WITHIN_SECONDS)
    held_open = _alive(other)
    for left in (orphan, other):                # a RED run must not leave the very orphan it proves
        if _alive(left):
            os.kill(left, signal.SIGKILL)
    assert held_open, "the premise: the parent's other fork — and with it the pipe's writing end — outlived the zygote"
    assert gone, f"the zygote {orphan} outlived its parent by more than {GONE_WITHIN_SECONDS} s"


def _read_in_a_fork(address):
    """The exit status of a fork that reads one byte at `address`: 0, or the negative signal that ended it."""
    pid = os.fork()
    if pid == 0:
        signal.signal(signal.SIGSEGV, signal.SIG_DFL)   # pytest's faulthandler would write the worker's stacks first
        signal.signal(signal.SIGBUS, signal.SIG_DFL)
        ctypes.string_at(address, 1)
        os._exit(0)
    return os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1])


FAULTS = (-int(signal.SIGSEGV), -int(signal.SIGBUS))
PAGE = mmap.PAGESIZE
PROT_READ_ONLY = 1


def _is_reserved_in_a_fork(page):
    """Is the page at `page` MAPPED (whatever its protection)? Asked by changing its protection, in a fork — which
    the kernel refuses for a page no mapping holds."""
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    libc.mprotect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    pid = os.fork()
    if pid == 0:
        os._exit(0 if libc.mprotect(page, PAGE, PROT_READ_ONLY) == 0 else 1)
    return os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1]) == 0


def test_a_zygote_s_image_has_no_readable_byte_either_side_of_it(made):
    """THE IMAGE IS GUARDED, on every run: it lies in the guarded-image plugin's own surroundings, so a candidate that
    indexes past either end FAULTS in the zygote's fork — which a stand-in for the worker owes (beside an unguarded
    image a wild store could land on memory mapped in the zygote's fork alone, pass its guard, and kill the worker).
    The mapping is one address range in both processes, so what a fork of this process finds beside it is what a
    fork of the zygote finds. The image itself is still the shared one, both ways."""
    its = made()
    assert _read_in_a_fork(its.address) == 0 and _read_in_a_fork(its.address + IMAGE_BYTES - 1) == 0
    assert _read_in_a_fork(its.address - 1) in FAULTS, "a byte below the image is readable"
    assert _read_in_a_fork(its.address + IMAGE_BYTES) in FAULTS, "a byte above the image is readable"
    # ...and what faults there is THE RESERVATION — the guarded-image plugin's own distances either side of the image,
    # to its two ends (a page that is mapped can have its protection asked for; a hole cannot):
    base, span = its.reservation
    assert (its.address - base, span) == (GUARD_BELOW, GUARD_BELOW + IMAGE_BYTES + GUARD_ABOVE)
    for page in (base, its.address - PAGE, its.address + IMAGE_BYTES, base + span - PAGE):
        assert _read_in_a_fork(page) in FAULTS and _is_reserved_in_a_fork(page), (
            f"the page at {page - its.address:+#x} from the image is no part of its guards")
    its.ask(("poke", A_BYTE_AT, A_BYTE))
    assert its.image()[A_BYTE_AT] == A_BYTE
