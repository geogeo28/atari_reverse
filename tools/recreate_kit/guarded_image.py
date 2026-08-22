"""An opt-in pytest plugin that runs every CANDIDATE on a GUARDED image, so a raw
`image + <computed address>` access that leaves the buffer FAULTS instead of scribbling on the host
heap.

    PYTHONPATH=<reverse>/tools .venv/bin/python -m pytest -q -n auto \
        -p recreate_kit.guarded_image test

WHAT IT IS FOR. The oracle puts every address on the 68000's 24-bit bus and then bounds it against
the image: an access outside reads as zero and a write is dropped (`oracle/shim.c`). A reconstruction
that indexes its `uint8_t *image` directly does neither, so an address the game computed out of its
own memory — a record pointer, a descriptor, a collision-map cell — reaches the HOST HEAP. The two
cores then agree only while whatever is next to the buffer happens to hold what the image would have.
That is invisible to the differential in both directions: it passes when the heap is quiet and it
kills the pytest worker when the page is not mapped. Project headers should route such addresses
through a bus helper (Wonder Boy's `include/bus.h`); this plugin is how you find the ones that do not.

IT REPLACES `harness.candidate_image` AND NOTHING ELSE, which is the whole reason that seam exists.
An earlier draft wrapped the `glue` argument of `harness.differential` instead and had to walk
`sys.modules` rebinding every battery's `from harness import differential` — which left
`leaf.run_candidate_only`'s own buffer unguarded, so a raw access reachable only from a
candidate-only case would have run outside the census while the sweep reported it clean.

WHY THE GUARD IS THIS BIG. `addr_add` is a plain 32-bit add, so a raw index can reach anywhere in the
4 GiB above the buffer — a page-sized guard sails straight over it. Every computed address in these
reconstructions is a `uint32_t`, so the reachable set is upward only and the guard BELOW is there
purely for a signed slip (an `int` offset in an `image + n` expression); it is sized to the 68000's
own 24-bit reach rather than to a full negative `int32`, and an access further down than that lands
on whatever the allocator put there. The reservation is PROT_NONE and never touched, so it costs
address space and no memory.

WHY IT IS NOT `make test`. A fault is a dead worker, not a named assertion: under `-n auto` xdist
reports which test was running and carries on, which makes the run a CENSUS of the class rather than
a pass/fail gate. It also cannot see a raw access that stays inside the buffer — it bounds the class,
it does not prove the addresses right. Standing use is a periodic sweep beside
`tools/test_hw_portability.py`, and what it finds gets pinned by an ordinary differential case.

DARWIN AND BSD ONLY, and it says so up front rather than failing on the first differential: `MAP_ANON`
is `0x1000` here and `0x20` on Linux, where `0x1000` means something else entirely.

COST: one `memmove` of the image per candidate run, which the ordinary `bytearray` copy it replaces
was doing anyway. Measured on the sweep below: ~50-60 s guarded against ~42 s plain.

FIRST USE: Wonder Boy batch 43 phase C, whose STATUS.md section OWNS the numbers — an earlier draft
of this docstring quoted three different totals from two different versions of this plugin, which is
exactly the drift the single-owner rule exists for. The reading, taken with the plugin as it now
stands and against the reconstruction restored to that batch's HEAD, is **5 crashing cases of 6,140
and 0 after the fix**: `scene_run_frame`'s scene descriptor 2.4 GiB past the buffer,
`actor_step_right_against_map`'s actor record at $fffff0, and the two pins written to catch them.
"""
import ctypes
import ctypes.util
import sys

_PROT_NONE = 0
_PROT_READ_WRITE = 1 | 2
_MAP_PRIVATE = 0x0002
_MAP_ANON_BSD = 0x1000            # Darwin/BSD; Linux spells MAP_ANONYMOUS 0x20 and 0x1000 otherwise
_NO_FD = -1

# A raw index is a `uint32_t` subscript, so it reaches 4 GiB UP and cannot go down by construction.
# The lower reserve is for a signed slip only, and is bounded at the 68000's own reach rather than at
# a full negative int32 — see the docstring, which states what that leaves uncovered.
GUARD_ABOVE = 1 << 32
GUARD_BELOW = 1 << 24

_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
_libc.mmap.restype = ctypes.c_void_p
_libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int,
                       ctypes.c_int, ctypes.c_longlong]
_libc.mprotect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]

_image = None
_runs = 0


def _reserve(size):
    """One process-wide image with PROT_NONE either side, built on first use."""
    global _image
    if _image is None:
        span = GUARD_BELOW + size + GUARD_ABOVE
        base = _libc.mmap(None, span, _PROT_NONE, _MAP_PRIVATE | _MAP_ANON_BSD, _NO_FD, 0)
        if base in (None, ctypes.c_void_p(-1).value):
            raise OSError(ctypes.get_errno(), "guarded_image: mmap of the reservation failed")
        body = base + GUARD_BELOW
        if _libc.mprotect(ctypes.c_void_p(body), size, _PROT_READ_WRITE) != 0:
            raise OSError(ctypes.get_errno(), "guarded_image: mprotect of the image failed")
        _image = (ctypes.c_uint8 * size).from_address(body)
    return _image


def pytest_configure(config):
    """Refuse a platform whose mmap flags these are not, before any test runs."""
    del config
    if not sys.platform.startswith(("darwin", "freebsd", "openbsd", "netbsd")):
        raise RuntimeError(
            f"guarded_image: MAP_ANON is {_MAP_ANON_BSD:#x} on Darwin/BSD and means something else "
            f"on {sys.platform}. Resolve the flag for this platform before running the sweep — "
            f"failing here is the point, so that a wrong flag cannot read as a clean census.")


def pytest_collection_modifyitems(session, config, items):
    """Replace the candidate-buffer seam, once the harness is importable.

    IN EVERY MODULE THAT HOLDS IT, not just the one a test imports. A project binds the kit through
    a shim that does `from recreate_kit.harness import *`, which COPIES the name — so patching the
    shim leaves `recreate_kit.harness.differential` calling the kit module's own unguarded binding,
    and the sweep guards only the handful of candidate-only runners that go through the shim. That is
    exactly what happened on this plugin's first parallel run, and `_runs` is what said so: 4 guarded
    calls against 6,140 cases.
    """
    del session, config, items
    import harness                                    # the project's shim; binds the kit

    from . import harness as kit_harness
    original = kit_harness.candidate_image
    size = harness.IMAGE_SIZE

    def candidate_image(img):
        global _runs
        buffer = _reserve(size)
        ctypes.memmove(buffer, bytes(img), size)
        _runs += 1
        return buffer

    rebound = []
    for name, module in list(sys.modules.items()):
        if getattr(module, "candidate_image", None) is original:
            module.candidate_image = candidate_image
            rebound.append(name)
    print(f"[guarded_image] candidate_image replaced in: {', '.join(sorted(rebound))}",
          file=sys.stderr)


def _worker(config):
    """This process's xdist worker id, or None when it is the controller / a plain `-n0` run."""
    return getattr(config, "workerinput", {}).get("workerid")


def pytest_sessionfinish(session, exitstatus):
    """A sweep that guarded NOTHING is a lie, so say so rather than exit 0.

    THE RULE IS PER-SWEEP AND THE COUNTER IS PER-PROCESS, which is two misfires rather than one and
    both are recorded because the second was found before it fired:

      1. the CONTROLLER collects and runs nothing, so its own count is always zero. It reddened a
         green sweep on this plugin's first parallel run.
      2. a WORKER can be handed a slice with no differential in it — a shard of pin/census cases —
         and its count is zero for a reason that is not a defect. Checking per worker would red a
         sweep at random as the slices move.

    So each worker reports its count to the controller through xdist's own channel and the
    CONTROLLER sums them: one assertion, over the run the rule is actually about. Without xdist there
    is one process and it is both. *A control's own machinery is code, and it gets the same gate.*
    """
    config = session.config
    worker = _worker(config)
    if worker is not None:                                   # a worker: report, never judge
        config.workeroutput["guarded_runs"] = _runs
        print(f"[guarded_image] {worker} guarded {_runs} candidate runs", file=sys.stderr)
        return
    total = _runs + sum(_worker_totals.values())
    where = ("this process" if not _worker_totals
             else f"{len(_worker_totals)} worker(s)")
    if exitstatus == 0 and total == 0:
        raise RuntimeError(
            f"guarded_image: not one candidate run in {where} went through harness.candidate_image, "
            f"so this sweep guarded nothing. Either it ran no differential, or something allocates "
            f"its own candidate buffer and needs routing through the seam.")
    print(f"[guarded_image] {total} candidate runs were guarded across {where}", file=sys.stderr)


# --- the controller's side of that channel -------------------------------------------------------
_worker_totals = {}


def pytest_testnodedown(node, error):
    """Take each worker's count as it finishes. `workeroutput` is xdist's own worker->controller
    channel, so this needs no file and no shared state."""
    del error
    output = getattr(node, "workeroutput", None) or {}
    if "guarded_runs" in output:
        _worker_totals[node.gateway.id] = output["guarded_runs"]
