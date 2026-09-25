"""The RECORD-AND-REFUSE hook: how a case answers a door the reconstruction calls out through.

Four cores reach something the host build cannot execute — a routine in RAM (`staged_call.h`'s
`recreate_call_vector`), Supexec's tail jump (`recreate_call_routine`), a GEMDOS handler
(`recreate_call_gemdos_handler`) and the disk driver's three BIOS vectors
(`recreate_call_disk_vector`) — and each leaves through a function pointer in the `.so` that a battery
binds to Python. Every one of those bindings needs the same guarantees, and four private copies had
drifted apart on them before this class existed (wave 8's review: one copy had no call cap, one
served calls from outside a pass):

* **dispatch BY KEY** (a routine or handler address, a BIOS function number), so a decoy staged beside
  the named routine means something on this side too;
* **a PASS HAS A BEGINNING AND AN END.** `recording()` opens one around each candidate run and closes
  it however the run ends, so "outside a pass" is every moment no candidate run is in flight — before
  a case, between its two runs, and after it;
* **`calls` is the FIRST pass's alone.** A differential with `poison` on runs the candidate twice, and
  poisoning an output can steer the reconstruction down another arm entirely, so the attribution
  pass's calls are served but not recorded;
* **a CAP on that list** (`CALLS_MAX`, below);
* **REFUSAL, recorded and reported.** A ctypes callback cannot raise through to its C caller — the
  exception is printed and the call returns — so a key nothing staged, and ANY call made while no pass
  is open, is written to `refused` and answered with `REFUSED_ANSWER`, and `staged()` fails the case
  on the way out. A call outside a pass is refused rather than served because no case is in flight:
  answering it out of the last case's table would be the worst answer available.

WHAT STAYS IN THE BATTERY is the table and the claim: which keys are staged, what each effect does to
the image, and the wording of the failure — those are statements about the routine.
"""
import contextlib
import ctypes

from harness import _lib

# How many calls ONE candidate run's recording may grow to before the list stops growing. The
# reconstruction is host code with no instruction cap the way the oracle has, so a defect that leaves
# a dispatched call looping is an endless ALLOCATION rather than a failure — a mutant that polled the
# wrong GPIP bit reached 15 GB before it was killed (measured in the BIOS wave's sweep). Far above any
# case in this project, so a run under the cap is an ordinary run.
CALLS_MAX = 1 << 16

# What a refused call returns to the C caller. Every hook with a result is answered with 0, which the
# refusal report then declares a fabrication; a `void` hook's ctypes trampoline discards it.
REFUSED_ANSWER = 0

# The pass whose calls are the case's: the plain run, which a differential makes first.
RECORDED_PASS = 1


def bind_pointer(symbol, trampoline):
    """Point the candidate `.so`'s function pointer `symbol` at a ctypes `trampoline`.

    The CALLER must hold `trampoline` for the process's lifetime: the `.so` keeps only the raw
    pointer, and a trampoline the garbage collector freed would be a jump into released memory.
    """
    ctypes.c_void_p.in_dll(_lib, symbol).value = ctypes.cast(trampoline, ctypes.c_void_p).value


class AddressHook:
    """One `.so` function pointer, bound for the process's lifetime to a dispatch-by-key recorder.

    `symbol` is the pointer's name in the candidate `.so` and `prototype` its `ctypes.CFUNCTYPE`,
    whose first two parameters are always (image, key). A call is recorded as `(key, *arguments)` and
    served by `effect(image, *arguments)`, whose return value is the call's result.
    """

    def __init__(self, symbol, prototype):
        self._effects = {}
        self._passes_begun = 0
        self._pass_open = False
        self.calls = []                 # the recorded pass's calls — the one every claim is about
        self.refused = []               # keys answered with REFUSED_ANSWER, in the order they came
        self._trampoline = prototype(self._dispatch)
        bind_pointer(symbol, self._trampoline)

    @contextlib.contextmanager
    def staged(self, effects, describe_refusals):
        """Install `{key: effect}` for ONE case, and fail it on the way out if anything was refused.

        `describe_refusals(refused)` is the battery's wording of that failure. The ledgers stay
        readable after the block; the effects do not, so a stray call later is refused rather than
        handed this case's table. Staged per case rather than at import because the pointer is ONE
        symbol in the `.so`, so two batteries that each bound a table at import would silently share
        whichever came last under `pytest -n auto`.

        `calls` and `refused` are CLEARED here, never rebound: modules export them under their own
        names (`isr.CALLS`, `gemdos.HANDLER_CALLS`, ...), and a new list would orphan those aliases.
        """
        self._effects = dict(effects)
        self._passes_begun = 0
        self.calls.clear()
        self.refused.clear()
        try:
            yield self
        finally:
            self._effects = {}
        assert not self.refused, describe_refusals(self.refused)

    def staged_routines(self, routines):
        """`staged()` for a door keyed by routine ADDRESS, whose table is the case's own
        `{address: (68000 stub bytes, effect)}` pairs — the stub is the oracle's half and needs no
        binding here."""
        def describe(refused):
            return (f"the candidate transferred control to {refused[0]:#x}, where this case staged no "
                    f"routine — it staged {', '.join(f'{at:#x}' for at in sorted(routines))}")
        return self.staged({at: effect for at, (_code, effect) in routines.items()}, describe)

    def recording(self, glue):
        """`glue(lib, buf)` inside an open pass — the glue is the only place that knows where one
        candidate run begins and ends."""
        def one_pass(lib, buf):
            self._passes_begun += 1
            self._pass_open = True
            try:
                return glue(lib, buf)
            finally:
                self._pass_open = False
        return one_pass

    def _dispatch(self, buf, key, *arguments):
        if not self._pass_open:
            self.refused.append(key)
            return REFUSED_ANSWER
        if self._passes_begun == RECORDED_PASS and len(self.calls) < CALLS_MAX:
            self.calls.append((key, *arguments))
        effect = self._effects.get(key)
        if effect is None:
            self.refused.append(key)
            return REFUSED_ANSWER
        return effect(buf, *arguments)
