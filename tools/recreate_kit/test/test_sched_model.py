"""Pin the SCHEDULED WRITE MODEL — both sides of it — kit-side.

The model (os.h, "SCHEDULED WRITES"; TRAP_MODEL.md, "Phase 8") is what makes a routine that
BUSY-WAITS on memory runnable at all. Nothing changes the image while a differential run is in
flight, so a `cmpi.b #$99,$879 / bne.s *-6` never ends on either side; the byte it waits for is
written by something outside the routine, and the case declares that store. The oracle applies it
before the Nth arrival at the wait's compare (`oracle/shim.c`); a reconstruction reaches the same
store through `src/sched.c`'s `sched_poll8`, whose Nth POLL is that same event.

That is a KIT-WIDE property, so it is pinned here rather than in the first project to need it (the
placement rule `test_hw_model.py` next door follows). The obstacle is the usual one: this directory
binds no project, and `harness`/`emu` both load a candidate `.so` at import, so the oracle is
unreachable from Python here. `sched_model_probe.c` drives both sides in C instead — which also lets
the MUTANT candidate bodies below stand in for the reconstruction this suite does not have.

THE RED CASE IS THE POINT. `no_schedule` runs the same spin with nothing declared and does not
return: without this capability there is no differential for such a routine, only an instruction cap.

`probe_build.compile_probe` builds the probe from the oracle's own sources plus `src/sched.c`, so a
reverted guard reddens immediately instead of hiding behind an up-to-date-looking `liboracle.so`.
"""
import re

from pathlib import Path

import pytest

from probe_build import compile_probe, run_probe

KIT = Path(__file__).resolve().parents[1]
OS_H = KIT / "include" / "os.h"
EMU_PY = KIT / "oracle" / "emu.py"
PROBE_SRC = Path(__file__).with_name("sched_model_probe.c")
CANDIDATE_SRC = (KIT / "src" / "sched.c", KIT / "src" / "os_refusal.c")

# The probe's own constants, restated here because a claim that reads `watch == HELD` says what it
# means and `watch == 25` does not. `test_the_probe_and_this_suite_agree_on_the_bytes` pins them.
HELD = 0x19          # what the watched byte holds while the wait is waiting
WANT = 0x99          # ...and the release it is waiting for
SCRATCH_LONG = (0x11, 0x22, 0x33, 0x44)   # the longword the two-entry case stores
SCRATCH_BYTE = 0x5A
# The two spins that never end: the probe's instruction cap, and its candidate bodies' poll guard.
PROBE_MAX_INSNS = 64
CAND_POLL_CAP = 16
# The planted wait is a compare and a branch back, so an unreleased one arrives at its trigger once
# every two instructions — which is what turns the cap into an expected arrival count.
WAIT_INSNS_PER_ITERATION = 2



@pytest.fixture(scope="module")
def cases(tmp_path_factory):
    return run_probe(compile_probe(PROBE_SRC, tmp_path_factory.mktemp("sched_model"), CANDIDATE_SRC))


def scalars(cases, name):
    assert name in cases, f"the probe printed no case {name!r} — it and this suite have drifted"
    return cases[name]["scalars"]


def scratch(cases, name):
    s = scalars(cases, name)
    return tuple(s[f"scratch{i}"] for i in range(4))


# ---- the capability, and what it is worth ------------------------------------------------------

def test_a_wait_on_a_byte_nothing_writes_does_not_return_without_a_schedule(cases):
    """RED FIRST, and the whole reason the model exists.

    The planted routine is Wonder Boy's pause wait in miniature: a byte compare and a branch back to
    it. With nothing declared, the byte never changes and the run ends at the instruction cap with
    its memory mid-execution — which `emu.run` reports as "did not reach rts". No differential can be
    written for such a routine at all until something outside it can store.
    """
    s = scalars(cases, "no_schedule")
    assert s["reached"] == 0
    assert (s["count"], s["applied"], s["arrivals"]) == (0, 0, 0)
    assert s["watch"] == HELD, "nothing declared a store, so nothing may have changed the byte"


def test_the_declared_store_lands_before_the_nth_arrival_and_the_wait_ends(cases):
    s = scalars(cases, "released_at_the_third_arrival")
    assert s["reached"] == 1
    assert s["applied"] == 1
    assert s["arrivals"] == 3, "the wait re-executed its compare three times, the third released"
    assert s["watch"] == WANT and s["d1"] == WANT


def test_nth_1_lands_before_the_very_first_execution_of_the_trigger(cases):
    """One arrival, not two — which is the post-reset observation `osh_run`'s loop skips.

    Musashi's first `m68k_execute()` after a reset spends the reset's own cycles and executes no
    instruction, so the loop sees the entry PC twice. Every other counter in the shim has always
    included that observation and changing them would move pinned perf numbers; the arrival count
    may not, because it is compared against the candidate's poll count. This case is what holds it,
    and it is aimed at the entry PC precisely because that is the only PC the phantom can be.
    """
    s = scalars(cases, "released_at_the_first_arrival")
    assert s["reached"] == 1
    assert (s["applied"], s["arrivals"]) == (1, 1)
    assert s["watch"] == WANT


def test_an_entry_whose_trigger_pc_is_never_executed_never_comes_due(cases):
    """...and the run then ends at the cap, which is what `emu.run` turns into a named cause."""
    s = scalars(cases, "trigger_pc_never_reached")
    assert s["reached"] == 0
    assert (s["count"], s["applied"], s["arrivals"]) == (1, 0, 0)
    assert s["watch"] == HELD


def test_the_instruction_index_trigger_fires_without_naming_a_pc(cases):
    """The oracle-only trigger kind: it counts instructions, so it books no arrival.

    A differential refuses one (`harness._vet_schedule_is_runnable`) because the candidate has no
    instruction counter to match it against — the count that stays 0 here is exactly the comparison
    that would be missing.
    """
    s = scalars(cases, "released_at_an_instruction_index")
    assert s["reached"] == 1
    assert (s["applied"], s["arrivals"]) == (1, 0)
    assert s["watch"] == WANT


def test_two_entries_run_together_and_the_widths_are_big_endian(cases):
    s = scalars(cases, "two_entries_and_a_longword")
    assert s["reached"] == 1
    assert s["applied"] == 2
    assert scratch(cases, "two_entries_and_a_longword") == SCRATCH_LONG
    assert s["watch"] == WANT


def test_an_entry_fires_at_most_once_however_many_times_its_trigger_arrives(cases):
    """The first entry comes due at arrival 1 and the run makes five; `applied` says it fired once.

    A tally rather than a byte, because the store is idempotent — re-applying it would leave the
    image identical, so only the count can separate "once" from "every arrival".
    """
    s = scalars(cases, "two_entries_and_a_longword")
    # ONE arrival per instruction, not one per entry: both entries name this PC and the run executes
    # it five times. The count is compared against the candidate's POLL count, and a wait polls once
    # per iteration whatever the case hung on it.
    assert s["arrivals"] == 5, "five executions of the shared trigger, counted once each"
    assert s["applied"] == 2, "one store each, not one per arrival"


def test_arrivals_go_on_being_counted_after_the_entry_has_fired(cases):
    """The count is of EXECUTIONS of the trigger, not of pending entries.

    `harness._vet_schedule_ran_the_same_wait` compares this total against a candidate's poll count,
    and a port that kept polling after the release would otherwise be invisible — so the counter has
    to keep counting once every entry is spent. Driven by a store that fires and does NOT release:
    the wait runs to the instruction cap, and every one of its iterations must be in the total.
    """
    s = scalars(cases, "a_fired_entry_that_does_not_release_the_wait")
    assert (s["applied"], s["refused"]) == (1, 0), "the store was made"
    assert s["reached"] == 0 and s["watch"] == HELD, "...and it released nothing"
    assert s["arrivals"] == PROBE_MAX_INSNS // WAIT_INSNS_PER_ITERATION, (
        f"the wait ran to the cap, so every one of its iterations is an arrival; got {s['arrivals']}")


def test_a_store_that_leaves_the_image_is_refused_rather_than_made(cases):
    s = scalars(cases, "a_store_outside_the_image")
    assert (s["applied"], s["refused"]) == (0, 1)
    assert s["reached"] == 0, "the wait it was meant to release therefore never ends"
    assert s["watch"] == HELD


def test_entries_past_the_cap_are_dropped_and_counted(cases):
    """`count` reports what the run really carries, so a case declaring more fails loudly.

    Silently carrying fewer stores than the case declared is the shape that reads as "the wait loop
    just never ended" — `emu.schedule_entries` refuses the same overflow one level up.
    """
    s = scalars(cases, "more_entries_than_the_cap")
    assert s["count"] == _os_h_int("OS_SCHED_MAX")
    assert s["applied"] == s["count"]
    assert scratch(cases, "more_entries_than_the_cap")[0] == SCRATCH_BYTE


def test_a_schedule_does_not_survive_into_the_next_run(cases):
    """Immediately after a run whose entries all fired, an empty schedule leaves the wait spinning.

    The oracle is process-global and shared under ``pytest -n auto``; a list left installed would
    fire inside whichever case ran next.
    """
    s = scalars(cases, "no_schedule_after_a_scheduled_run")
    assert s["reached"] == 0
    assert (s["count"], s["applied"], s["arrivals"]) == (0, 0, 0)
    assert s["watch"] == HELD


# ---- the candidate side, and what the poll count catches ---------------------------------------

def test_the_candidate_polls_once_per_iteration_and_matches_the_oracles_arrivals(cases):
    """The pairing the whole model rests on: three arrivals on one side, three polls on the other."""
    oracle = scalars(cases, "released_at_the_third_arrival")
    cand = scalars(cases, "cand_polls_the_wait")
    assert cand["polls"] == oracle["arrivals"] == 3
    assert cand["applied"] == oracle["applied"] == 1
    assert cand["watch"] == oracle["watch"] == WANT


@pytest.mark.parametrize("name,polls,watch", [
    ("cand4_polls_the_wait", 4, WANT),
    ("cand4_polls_once_then_reads", 1, HELD),
    ("cand4_polls_twice_per_iteration", 5, WANT),
])
def test_the_poll_count_separates_a_faithful_wait_from_two_mutants(cases, name, polls, watch):
    """Neither mutant can be caught by memory, and one of them cannot be caught by anything else.

    `polls_once_then_reads` reads the image directly after a single poll — the shape of a port
    written against a byte that "is already there" — and its wait never ends, so on this side it
    stops at the body's own guard. `polls_twice_per_iteration` ends with the SAME image as the
    faithful body, because the agent's store comes off the same list either way; only the count
    separates them, which is why `harness.differential` compares it against the oracle's arrivals.
    """
    s = scalars(cases, name)
    assert s["polls"] == polls
    assert s["watch"] == watch


def test_an_nth_that_aliases_the_ports_polling_rate_hides_the_double_poll(cases):
    """A measured hole, stated rather than papered over.

    At `nth = 3` the double-poller's extra poll lands on the iteration the release was due anyway: it
    ends with the same image, the same applied count AND the same poll count as the faithful body, so
    nothing separates them. The mutant is only visible at an `nth` that is not a multiple of the
    port's polls-per-iteration — which is why a case that drives a wait should drive more than one.
    """
    faithful = scalars(cases, "cand_polls_the_wait")
    aliased = scalars(cases, "cand_polls_twice_at_an_aliasing_nth")
    assert (aliased["polls"], aliased["watch"], aliased["applied"]) == \
           (faithful["polls"], faithful["watch"], faithful["applied"])


def test_the_capped_wait_is_the_faithful_body_while_the_release_arrives(cases):
    """`sched_wait8` is what a reconstruction calls, and it must be the bare poll loop plus a bound —
    same polls, same store, same byte, no refusal — or every port would be paying for the cap."""
    bare = scalars(cases, "cand_polls_the_wait")
    capped = scalars(cases, "cand_waits_and_is_released")
    assert (capped["polls"], capped["applied"], capped["watch"]) == \
           (bare["polls"], bare["applied"], bare["watch"])
    assert (capped["exhausted"], capped["os_refusals"]) == (0, 0)


def test_a_wait_the_schedule_never_releases_is_CAPPED_rather_than_infinite(cases):
    """THE HANG CLASS, closed. The entry fires and stores the byte the wait ALREADY holds, so the
    release never comes — the shape a case gets when its declared value does not match the compare,
    and the shape that made six of this model's first-sweep mutants hang the whole suite instead of
    failing it.

    Three things are asserted together because each alone would let a wrong fix through: the wait
    ENDS (it polled exactly OS_SCHED_POLL_MAX times, not for ever), it says WHICH kind of failure it
    was (`g_sched_exhausted`), and it lands in the ONE tally `harness.differential` reads after every
    candidate run (`os_refused`), which is what turns it into a rejected case rather than a silence.
    """
    s = scalars(cases, "cand_a_wait_that_is_never_released")
    assert s["applied"] == 1 and s["watch"] == HELD, "the store was made and released nothing"
    assert s["polls"] == _os_h_int("OS_SCHED_POLL_MAX"), "it stopped at the cap"
    assert s["exhausted"] == 1
    assert s["os_refusals"] == 1, "and the harness's own refusal tally saw it"
    assert s["d1"] == 0, "the body honoured the 0 rather than carrying on"


def test_the_candidate_refuses_the_same_out_of_image_store_the_oracle_refuses(cases):
    oracle = scalars(cases, "a_store_outside_the_image")
    cand = scalars(cases, "cand_a_store_outside_the_image")
    assert (cand["applied"], cand["refused"]) == (oracle["applied"], oracle["refused"]) == (0, 1)
    assert cand["polls"] == CAND_POLL_CAP, "its wait ran to the body's guard, unreleased"
    assert cand["watch"] == HELD


# ---- the sizes and the bytes, pinned against their sources -------------------------------------

def _c_define(source, name):
    """One `#define <name> <int literal>` out of C source, with an optional u/U suffix.

    ONE scraper for one grammar: the first draft had two in this file — this and an inline copy in
    the case below that accepted `u` but not `U` — so a probe writing `0x99U` would have reddened one
    claim and not the other, on a file nobody had edited.
    """
    m = re.search(rf"^#define\s+{name}\s+(0x[0-9a-fA-F]+|\d+)[uU]?\b", source, re.M)
    assert m, f"no `#define {name}` with an integer literal"
    return int(m.group(1), 0)


def _os_h_int(name):
    return _c_define(OS_H.read_text(), name)


def test_the_shim_reports_the_sizes_os_h_declares(cases):
    """`emu.py` reads both from the `.so` rather than restating them, so this is what pins the pair.

    A shim built against a different OS_SCHED_FIELDS would decode every entry at the wrong stride.
    """
    s = scalars(cases, "sizes")
    assert s["max"] == _os_h_int("OS_SCHED_MAX")
    assert s["fields"] == _os_h_int("OS_SCHED_FIELDS")


def test_the_probe_and_this_suite_agree_on_the_bytes():
    """The named constants above are the probe's own, read out of its source.

    Without this the claims would read as prose: a probe that changed WANT would leave every
    assertion here comparing two numbers that no longer mean what their names say.
    """
    src = PROBE_SRC.read_text()
    for name, value in (("HELD", HELD), ("WANT", WANT), ("SCRATCH_BYTE", SCRATCH_BYTE),
                        ("PROBE_MAX_INSNS", PROBE_MAX_INSNS), ("CAND_POLL_CAP", CAND_POLL_CAP)):
        assert _c_define(src, name) == value, f"{name} has moved in {PROBE_SRC.name}"
    m = re.search(r"^#define\s+SCRATCH_LONG\s+0x([0-9a-fA-F]{8})u\b", src, re.M)
    assert m and tuple(bytes.fromhex(m.group(1))) == SCRATCH_LONG


def test_the_widths_os_sched_store_carries_are_the_ones_emu_py_mirrors():
    """`emu.SCHED_WIDTHS` is a MIRROR of a rule that lives in C — `os_sched_store`'s width guard —
    and CLAUDE.md §5 requires the mirror to be pinned rather than duplicated. Its two neighbours
    already are (the sizes are read back from the `.so`, the trigger kinds are in
    test_os_memory_map.py's PINNED tuple); this is the third.

    Read out of os.h's own source, because the guard is a comparison rather than a #define: a width
    the mirror admits and the C refuses would be dropped at run time as `osh_sched_refused`, and one
    the C admits and the mirror refuses could never be declared at all.
    """
    guard = re.search(r"if \(width != (\d+) && width != (\d+) && width != (\d+)\)",
                      OS_H.read_text())
    assert guard, "os_sched_store's width guard has changed shape"
    # emu.py is PARSED, not imported: this directory binds no project and `emu` loads a candidate
    # .so at import. Same technique test_os_memory_map.py uses for the rest of the os.h mirror.
    mirror = re.search(r"^SCHED_WIDTHS = \(([^)]*)\)", EMU_PY.read_text(), re.M)
    assert mirror, "emu.py defines no SCHED_WIDTHS tuple"
    assert (tuple(sorted(int(g) for g in guard.groups()))
            == tuple(sorted(int(w) for w in mirror.group(1).split(",")))), (
        "os_sched_store and emu.SCHED_WIDTHS disagree about the widths the model carries")
