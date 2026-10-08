"""A ZYGOTE: a small fork of this process, taken EARLY, that makes this process's forks for it.

WHY. A fork costs what its PARENT holds resident — the parent's page tables are write-protected for it, entry by
entry (measured: 1.2 ms of a process of 85 MB, 13.5 ms at 650 MB, 23 ms at 1 GB) — and an xdist worker of this suite
is 700 MB to 1.1 GB by the time its batteries run, each of whose cases guards its C in a fork first
(`aes_event.forked`): 4,500 forks a run, a third of those batteries' cost. A zygote is forked ONCE, when the session
starts and the process holds almost nothing; what a later fork is to run is handed to it BY CONTENT, and it forks:
a fork of the zygote costs what the ZYGOTE holds, whatever its parent has grown to.

WHAT CROSSES. A request (anything picklable) down one pipe and its reply up another, and ONE IMAGE: a mapping both
processes share, made before the fork — the parent copies the image a run is to start from into it, the zygote's fork
runs over it IN PLACE, and the parent reads what the run left there (`image`). The mapping is GUARDED, always
(below): a candidate that indexes past either end of the image faults in the zygote's fork.

WHAT A REQUEST MEANS is not this module's: a `Zygote` is handed `served_by`, "module:function", imported IN THE
ZYGOTE (the parent need not have imported it), and called as `function(buffer, request)` for each request — the buffer
the shared image as a ctypes array — its answer the reply.

A ZYGOTE NEVER OUTLIVES ITS PARENT BY MORE THAN A POLL: it waits for a request PARENT_POLL_SECONDS at a time and
leaves when its parent is no longer the process that made it (a SIGKILLed worker closes no pipe a fork of it still
holds). It holds none of its parent's descriptors but its two pipe ends and stderr — an xdist worker's channel to the
controller would otherwise stay open in it, and the controller would not see the worker die. And it is NOBODY'S
ZYGOTE BUT ITS MAKER'S: a fork of the parent (`Zygote.running` asks the pid) has none.
"""
import contextlib
import ctypes
import ctypes.util
import importlib
import mmap
import os
import pickle
import select
import signal
import struct
import sys
import time
import traceback
from collections import namedtuple

PARENT_POLL_SECONDS = 1.0
STOP_SECONDS = 3 * PARENT_POLL_SECONDS  # how long a zygote whose pipes were closed is given to leave before it is killed
STOP_POLL_SECONDS = 0.002
STDIN_FD, STDOUT_FD, STDERR_FD = 0, 1, 2
MOST_DESCRIPTORS_CLOSED = 1 << 16       # where a process whose limit is "unlimited" stops looking for descriptors to close
_LENGTH = struct.Struct(">I")           # a message's header: its pickled bytes' count


class Gone(Exception):
    """The zygote is not there: never started here, stopped, or dead."""


# ---- the shared image ------------------------------------------------------------------------------------------------
# ALWAYS GUARDED, whatever the worker's own candidate image is: PROT_NONE below the image and above it, the
# guarded-image plugin's own distances (`recreate_kit.guarded_image`: 16 MB below — the 68000's reach, for a signed
# slip — and 4 GiB above, every `image + <a uint32>` there is). NOT a choice of strictness but what a stand-in owes: a
# fork of the WORKER faults wherever the worker itself would, so its guard kept a wild pointer from ever running in
# process; a fork of the ZYGOTE has another address space, and beside an unguarded image a wild store can land on
# mapped memory THERE and pass — then kill the worker (measured: a core storing a gigabyte past its image passed 5
# guards of 20 and crashed the worker 9 times). Guarded, every out-of-image access a core can compute faults in the
# fork, by name, on any run — so the zygote's guard is at least the worker's own everywhere.
_PROT_NONE = 0
_NO_FD = -1
_MAP_FIXED = 0x10                       # the one flag `mmap` does not name: the same value on Darwin, the BSDs and Linux


def _guarded_mapping(image_bytes):
    """`(the address of a SHARED image of `image_bytes`, the reservation it lies in: its base and its span)` — the
    reservation its own, PROT_NONE, GUARD_BELOW under the image and GUARD_ABOVE over it: address space, and no
    memory."""
    from recreate_kit import guarded_image

    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    libc.mmap.restype = ctypes.c_void_p
    libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_longlong]
    failed = ctypes.c_void_p(-1).value
    span = guarded_image.GUARD_BELOW + image_bytes + guarded_image.GUARD_ABOVE
    base = libc.mmap(None, span, _PROT_NONE, mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS, _NO_FD, 0)
    if base in (None, failed):
        raise OSError(ctypes.get_errno(), "zygote: mmap of the guarded reservation failed")
    body = libc.mmap(base + guarded_image.GUARD_BELOW, image_bytes, mmap.PROT_READ | mmap.PROT_WRITE,
                     mmap.MAP_SHARED | mmap.MAP_ANONYMOUS | _MAP_FIXED, _NO_FD, 0)
    if body in (None, failed):
        raise OSError(ctypes.get_errno(), "zygote: mmap of the shared image inside its guards failed")
    return body, (base, span)


# ---- the two pipes -----------------------------------------------------------------------------------------------------
def _read_exactly(fd, count):
    data = b""
    while len(data) < count:
        more = os.read(fd, count - len(data))
        if not more:
            raise Gone("the other end of the zygote's pipe closed")
        data += more
    return data


def _send(fd, message):
    data = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
    data = _LENGTH.pack(len(data)) + data
    while data:
        data = data[os.write(fd, data):]


def _receive(fd):
    length, = _LENGTH.unpack(_read_exactly(fd, _LENGTH.size))
    return pickle.loads(_read_exactly(fd, length))


# ---- the zygote's own life ---------------------------------------------------------------------------------------------
Raised = namedtuple("Raised", "traceback")      # a reply: the serving function raised (the harness's error, by its text)


def _holding_only(*kept):
    """Close every descriptor of the parent's but `kept`; stdin and stdout become /dev/null."""
    kept = set(kept)
    limit = os.sysconf("SC_OPEN_MAX")
    for fd in range(STDERR_FD + 1, limit if 0 < limit <= MOST_DESCRIPTORS_CLOSED else MOST_DESCRIPTORS_CLOSED):
        if fd not in kept:
            with contextlib.suppress(OSError):
                os.close(fd)
    null = os.open(os.devnull, os.O_RDWR)
    os.dup2(null, STDIN_FD)
    os.dup2(null, STDOUT_FD)
    if null not in kept and null > STDERR_FD:
        os.close(null)


def _parent_left(requests, parent):
    """Wait for a request on `requests`: False when one is there, True when the parent is gone instead."""
    while not select.select([requests], [], [], PARENT_POLL_SECONDS)[0]:
        if os.getppid() != parent:
            return True
    return False


def _the_zygote_s_whole_life(requests, replies, address, image_bytes, served_by, parent):
    """What the zygote does, and all it does: serve requests until its parent closes the pipe or is gone — then
    `_exit`, whatever happened. Its fork of a request is the serving function's own business."""
    try:
        # (The parent's watchdog — `faulthandler.dump_traceback_later`'s thread — is not in a fork of it, and must
        # NOT be cancelled here: cancelling waits on a lock that thread held, for ever.)
        _holding_only(requests, replies, STDERR_FD)
        sys.stdin = open(os.devnull)
        # LINE-BUFFERED, AND EMPTY WHENEVER A REQUEST IS SERVED: what the zygote itself has printed and not yet
        # written (a warning at the serving module's import, a line with no newline) lies in this object's buffer —
        # and a fork inherits the buffer with the object: every later fork would write it out again as ITS OWN
        # stderr the moment it replaces the object (measured: three plain forks answered the zygote's import line).
        sys.stdout = sys.stderr = open(STDERR_FD, "w", buffering=1, closefd=False)
        module, _, function = served_by.partition(":")
        serve = getattr(importlib.import_module(module), function)
        buffer = (ctypes.c_uint8 * image_bytes).from_address(address)
        while not _parent_left(requests, parent):
            try:
                request = _receive(requests)
            except Gone:
                break
            try:
                sys.stderr.flush()                      # nothing of the zygote's own is in a fork's inheritance
                reply = serve(buffer, request)
            except Exception:                           # the reply names it: the parent raises, the zygote goes on
                reply = Raised(traceback.format_exc())
            _send(replies, reply)
    except BaseException:
        with contextlib.suppress(Exception):
            os.write(STDERR_FD, f"the zygote ended: {traceback.format_exc()}".encode())
    finally:
        os._exit(0)


# ---- the parent's side -------------------------------------------------------------------------------------------------
class Zygote:
    """One zygote of THIS process, forked as the object is made: its requests served by `served_by`
    ("module:function", imported there) over a shared, guarded image of `image_bytes`."""

    def __init__(self, image_bytes, served_by):
        self.image_bytes = image_bytes
        self.address, self.reservation = _guarded_mapping(image_bytes)
        requests_read, self._requests = os.pipe()
        self._replies, replies_write = os.pipe()
        self._owner = os.getpid()
        self.pid = os.fork()
        if self.pid == 0:
            os.close(self._requests)
            os.close(self._replies)
            _the_zygote_s_whole_life(requests_read, replies_write, self.address, image_bytes, served_by, self._owner)
        os.close(requests_read)
        os.close(replies_write)
        self._there = True

    def running(self):
        """Is it there, and THIS process's (a fork of its maker has none)?"""
        return self._there and self._owner == os.getpid()

    def _own(self):
        if not self.running():
            raise Gone("this process has no zygote")

    def _reaped(self):
        """Its pipes closed — it leaves at its next read — and the zygote reaped; forgotten. A zygote that has not
        left within STOP_SECONDS (it serves one request at a time and none is in flight here, so it is waiting for
        nothing) is KILLED: stopping one never waits on it for ever."""
        self._there = False
        for fd in (self._requests, self._replies):
            with contextlib.suppress(OSError):
                os.close(fd)
        with contextlib.suppress(OSError):
            deadline = time.monotonic() + STOP_SECONDS
            while os.waitpid(self.pid, os.WNOHANG) == (0, 0):
                if time.monotonic() > deadline:
                    os.kill(self.pid, signal.SIGKILL)
                    os.waitpid(self.pid, 0)
                    break
                time.sleep(STOP_POLL_SECONDS)

    def ask(self, request, image_address=None):
        """`request` served by the zygote — over a copy of the image at `image_address`, when one is named (the shared
        image is otherwise left as the last request left it): its reply. `Gone` when there is no zygote to ask, or it
        died; an AssertionError carrying its traceback when the serving function raised there."""
        self._own()
        if image_address is not None:
            ctypes.memmove(self.address, image_address, self.image_bytes)
        try:
            _send(self._requests, request)
            reply = _receive(self._replies)
        except (OSError, Gone) as failed:
            self._reaped()
            raise Gone(f"the zygote (pid {self.pid}) is gone: {failed}") from failed
        assert not isinstance(reply, Raised), f"the zygote's own Python raised — the harness's error:\n{reply.traceback}"
        return reply

    def image(self):
        """The shared image as the last request's run left it: a copy."""
        self._own()
        return ctypes.string_at(self.address, self.image_bytes)

    def stop(self):
        """End it and reap it; nothing, where it is gone already or not this process's."""
        if self.running():
            self._reaped()
