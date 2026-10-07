"""Pin the bench door's STOP SET (`emu.bench_door_arm` with a set of PCs, shim.c's `osh_bench_door_stops`): a watch over
calls scattered through a text stops at the listed PCs alone, where a band over them all would also stop at every
instruction between them — and a band still stops at every PC inside it, as it always has.

Over a hand-assembled probe of NOPs, run by the real shim (`emu.run_bench`).
"""
import struct

import pytest

import kit_smoke_project

kit_smoke_project.bind()

import emu           # noqa: E402  (importable only once a project is bound)
from recreate_kit import rom_bench   # noqa: E402

PROBE_AT = 0x20000                    # the probe's code, above the vector page and the poked block
NOP, RTS = 0x4E71, 0x4E75
PROBE_NOPS = 8
INSTRUCTION_BYTES = 2
FIRST_STOP = PROBE_AT + 2 * INSTRUCTION_BYTES
SECOND_STOP = PROBE_AT + 5 * INSTRUCTION_BYTES
PROBE_INSNS = PROBE_NOPS + 1          # the NOPs and the `rts`


def _probe():
    image = bytearray(kit_smoke_project.IMAGE_SIZE)
    program = struct.pack(f">{PROBE_NOPS + 1}H", *[NOP] * PROBE_NOPS, RTS)
    image[PROBE_AT:PROBE_AT + len(program)] = program
    return image


def _run(image, door):
    return emu.run_bench(image, PROBE_AT, arg0=0, sp=emu.STACK_TOP, sentinel=emu.SENTINEL, door=door)


def test_a_stop_set_stops_at_its_pcs_alone_and_the_run_is_the_unwatched_one():
    """The two listed PCs stop the run, in turn; the PCs between them, inside the set's hull, execute; and the run's
    total is the unwatched run's, instruction for instruction."""
    whole = _run(_probe(), None)
    image = _probe()
    try:
        first = _run(image, frozenset({FIRST_STOP, SECOND_STOP}))
        assert (first["status"], emu.bench_door_pc()) == (emu.BENCH_DOOR, FIRST_STOP)
        emu.bench_door_arm(frozenset({SECOND_STOP}))
        second = emu.bench_resume(PROBE_AT, max_insns=PROBE_INSNS)
        assert (second["status"], emu.bench_door_pc()) == (emu.BENCH_DOOR, SECOND_STOP), "a PC inside the hull stopped"
        emu.bench_door_arm(None)
        last = emu.bench_resume(PROBE_AT, max_insns=PROBE_INSNS)
    finally:
        emu.bench_abort()
    assert last["status"] == emu.BENCH_SENTINEL
    assert (last["ninsns"], last["cycles"]) == (whole["ninsns"], whole["cycles"])


def test_a_band_still_stops_at_every_pc_inside_it():
    """`osh_bench_door` clears any stop list: a band armed after a set stops at a PC the set never listed."""
    image = _probe()
    after = SECOND_STOP + INSTRUCTION_BYTES
    try:
        _run(image, frozenset({SECOND_STOP}))
        emu.bench_door_arm((after, INSTRUCTION_BYTES))
        stopped = emu.bench_resume(PROBE_AT, max_insns=PROBE_INSNS)
        assert (stopped["status"], emu.bench_door_pc()) == (emu.BENCH_DOOR, after)
    finally:
        emu.bench_abort()


def test_a_stop_set_past_what_the_shim_holds_is_refused():
    with pytest.raises(ValueError, match="at most"):
        emu.bench_door_arm(frozenset(range(PROBE_AT, PROBE_AT + 2 * (emu.BENCH_DOOR_STOPS_MAX + 1), 2)))


class _ArmsWhereItStopped:
    """A watch that leaves its door over the PC it is stopped at: the real shim then stops every resume at once."""

    first = frozenset({FIRST_STOP})

    def stopped(self, pc, sp, memory):
        return frozenset({pc})


def test_the_real_shim_s_watch_loop_refuses_a_door_left_over_its_stop_instead_of_spinning():
    """Over the real shim (`rom_bench.watched`): the door left over the stop is refused by name. Before the refusal
    this never returned — a resume that stops where it stands runs no instruction, and the budget the loop counts
    down is the run's instructions."""
    image = _probe()
    stopped = _run(image, _ArmsWhereItStopped.first)
    assert (stopped["status"], emu.bench_door_pc()) == (emu.BENCH_DOOR, FIRST_STOP)
    with pytest.raises(RuntimeError, match=f"armed the PC it is stopped at \\({FIRST_STOP:#x}\\)"):
        rom_bench.watched(stopped, PROBE_AT, _ArmsWhereItStopped(), image, max_insns=PROBE_INSNS)
    assert _run(_probe(), None)["status"] == emu.BENCH_SENTINEL, "the refusal left the shim unable to run"


class _ServicesItsStop:
    """A watch that SERVICES its stop — resumes the run past the door, as a callback's `rts` does
    (`emu.bench_door_return`, `asm_twin`'s own door service) — and keeps its door: a stub called again and again."""

    first = frozenset({FIRST_STOP})

    def __init__(self):
        self.stops = []

    def stopped(self, pc, sp, memory):
        self.stops.append(pc)
        emu.bench_door_return(0, pc + INSTRUCTION_BYTES, sp)
        return frozenset({FIRST_STOP})


def test_a_watch_that_moves_the_run_past_its_door_and_keeps_the_door_is_no_spin():
    """THE RED for a refusal that asked where the run STOPPED and not where it RESUMES: this watch's resume does not
    stop where it stands — the PC was moved past the door — and was refused "for ever" all the same. The PC is read
    after the watch answers: the run goes on to its end, stopped once."""
    image = _probe()
    stopped = _run(image, _ServicesItsStop.first)
    watch = _ServicesItsStop()
    result = rom_bench.watched(stopped, PROBE_AT, watch, image, max_insns=PROBE_INSNS)
    assert (result["status"], watch.stops) == (emu.BENCH_SENTINEL, [FIRST_STOP])


A_TWICE_STOPPED_RUN_S_BUDGET = 2 * PROBE_INSNS      # each resume is handed what is left: a margin, not the exact count


class _AnswersAOneShotDoor:
    first = frozenset({FIRST_STOP})

    def __init__(self):
        self.stops = []

    def stopped(self, pc, sp, memory):
        self.stops.append(pc)
        return iter([SECOND_STOP]) if pc == FIRST_STOP else None


def test_a_door_answered_as_a_one_shot_iterable_is_armed_as_it_was_asked_about():
    """THE RED for a check that EMPTIED the door it was asked about: a generator of PCs read by the refusal's check
    armed no stop at all, and the run went on to its end UNWATCHED — the second stop silently lost."""
    image = _probe()
    watch = _AnswersAOneShotDoor()
    result = rom_bench.watched(_run(image, _AnswersAOneShotDoor.first), PROBE_AT, watch, image,
                               max_insns=A_TWICE_STOPPED_RUN_S_BUDGET)
    assert (result["status"], watch.stops) == (emu.BENCH_SENTINEL, [FIRST_STOP, SECOND_STOP])
