"""THE EVENT BLOCKS' LISTS (`src/aes/evasync.c`): gemasync's list routines and geminput's evremove.

    signal(evb)          evb->pd's PD_EVFLG |= evb's mask; that process — not the running one, on the not-ready list
                         (walked to it or to its end) and waiting for an event that came — PD_STAT 0, off the
                         not-ready list, onto the head of the woken list
    azombie(evb)         onto the head of the completed list (its head's stand-in predecessor $c846), EVB_FLAG := 2,
                         signal
    get_evb()            the free list's first EVB taken, its 28 bytes cleared; 0 with none
    evinsert(evb, list)  at the head of the wait list at `list`: pred := list - 4, link := the old first
    takeoff(evb)         off its wait list; a delay with one after it adds its ticks to that one; onto the free list
    apret(mask)          the running PD's EVB of exactly `mask`: off the completed list and its PD's, the bit cleared in
                         PD_EVBITS / PD_EVWAIT / PD_EVFLG, freed; answers its answer's low word, the high word to $c792;
                         100 with no such EVB, 101 with one not completed
    acancel(mask)        each of the running PD's EVBs among `mask`: completed → kept, its bit answered; else off its
                         PD's list, takeoff, the bit cleared in PD_EVBITS / PD_EVWAIT
    evremove(evb, ret)   $c84e counted down (never below 1) when (parm >> 16 & $ff) > 1; answer |= ret; off its wait
                         list; azombie

EVERY MACHINE IS THE ROM's OWN, at the moment the ROM makes the call (`aes_evasync`: the ARRIVALS of a watched run of
the dispatcher's loop, of a running process's evnt_multi, of a message sent, of the screen's lock released) — and every
frame the one its caller pushed, but for the cases SAID to hand one no caller does: a pointer with a top byte (the bus
drops it), apret and acancel with a mask their callers never hand (the arms no caller reaches), an EVB put on a list
that lies over it (the order of evinsert's reads and stores).

THE ATTRIBUTION PASS, NARROWED WHERE THE LISTS STEER IT (`aes.run_function`'s `steered=`, the one spelling). These
routines read the links they store: the pass hands both runs the inverse of every byte the ROM's run stored, and the
poisoned runs follow an inverted link off RAM — into the I/O page, which no model serves, or onto an odd address,
which the C refuses by name. Measured over all 187 arrivals, the whole pass forced on, each in a child: takeoff's 24
pass it (it stores through the links it read before, and reads none it stored), signal's 5 that wake nobody (their
one store is PD_EVFLG, ORed), the acancel that cancels nothing and the aprets that refuse — those run the WHOLE pass
(`steered_by`). Every other case says the lists steer it (`aes_pdpipe.STEERS_THE_LISTS`) and runs the pass narrowed to that: every stored
byte that is no link inverted, so a flag, a mask, an answer or a count the C did not store shows.
"""
import inspect
import sys

import pytest

from harness import BASE_IMAGE, make_image
from recreate_kit.os_map import OS_BUS_ADDR_MASK

import aes
import aes_evasync as ev
import aes_event
import aes_pdpipe as pp
import case
import vdi
from aes_gsx import THROUGH
from aes_evasync import (ACANCEL, APRET, AZOMBIE, EVINSERT, EVREMOVE, GET_EVB, SCREEN_MANAGER, SHELL, SIGNAL, TAKEOFF)

pytestmark = pytest.mark.collected_with(by=lambda params: (params.get("arrival") or (None,))[0])
KEY, EVERYTHING = "a key wakes the desk", ev.EVERY_EVENT
# evinsert's fourth arrival of that scenario — the second rectangle's wait, onto the list the first one's is on: the
# one arrival that finds a wait list holding an EVB already.
ONTO_A_LIST_THAT_HOLDS_ONE = (EVERYTHING, 3)


# ---- the run door ----------------------------------------------------------------------------------------------------
def before(arrival):
    """The machine an arrival is at, as an image."""
    return make_image(arrival.machine)


def bus(address):
    """A pointer as the bus carries it: its top byte dropped."""
    return address & OS_BUS_ADDR_MASK


def process_of(image, evb):
    return case.long_in(image, bus(evb) + aes.EVB_PD)


def wakes(arrival, evb):
    """Does signal(evb) over `arrival`'s machine wake a process — move it from the not-ready list to the woken one?"""
    image = before(arrival)
    pd = process_of(image, evb)
    events = case.word_in(image, pd + aes.PD_EVFLG) | case.word_in(image, bus(evb) + aes.EVB_MASK)
    return (pd != ev.running(image) and pd in aes.list_of(image, aes.AES_NRL)
            and bool(events & case.word_in(image, pd + aes.PD_EVWAIT)))


def cancels_nothing(arrival, mask):
    """Does acancel(mask) over `arrival`'s machine take no EVB off any list — every wait of the running process among
    `mask` completed already (kept), or none among it?"""
    image = before(arrival)
    return all(evb in ev.completed(image) or not ev.evb_of(image, evb)["MASK"] & mask
               for evb in ev.evlist(image, bus(ev.running(image))))


def frees_nothing(arrival, mask):
    """Does apret(mask) over `arrival`'s machine refuse — the running process holding no completed EVB of exactly
    `mask` — and so store nothing?"""
    image = before(arrival)
    return not any(ev.evb_of(image, evb)["MASK"] == mask and evb in ev.completed(image)
                   for evb in ev.evlist(image, bus(ev.running(image))))


# The cases that run the WHOLE attribution pass: each stores through no link it reads after storing it.
STORES_THROUGH_NO_LINK_IT_STORED = {
    TAKEOFF: lambda arrival, arguments: True,
    SIGNAL: lambda arrival, arguments: not wakes(arrival, arguments[0]),
    ACANCEL: lambda arrival, arguments: cancels_nothing(arrival, arguments[0]),
    APRET: lambda arrival, arguments: frees_nothing(arrival, arguments[0]),
}


def steered_by(arrival, arguments):
    """What steers the attribution pass in a case of `arrival`'s routine with `arguments` — the lists' links — or
    None for the cases that run the whole pass (measured: the module's docstring)."""
    whole = STORES_THROUGH_NO_LINK_IT_STORED.get(arrival.name, lambda arrival, arguments: False)(arrival, arguments)
    return None if whole else pp.STEERS_THE_LISTS


# THE C RUNS FIRST IN A CHILD. A list routine that goes wrong does not answer wrongly: it walks a list that no longer
# ends, or stores through a link that is no address — in process, a worker spinning until the watchdog ends it or
# aborted by the host's refusal (an odd address, a store above RAM), and no failure reported. In a child either is this
# case's own: an alarm or a non-zero exit, asserted — `aes_event.run_core_guarded`: every run of the C the kit makes,
# the attribution pass's too, in a FORK of the worker first.


def run_over(name, arguments, machine, **kwargs):
    """The differential of `addrs.<name>` over `machine` with the frame `arguments`: its C first in a fork."""
    return aes_event.run_core_guarded(name, arguments, machine, **kwargs)


def run(arrival, arguments=None, **kwargs):
    """The differential of `arrival`'s routine over its machine — with the frame its caller pushed, or `arguments`."""
    arguments = arrival.arguments if arguments is None else arguments
    return run_over(arrival.name, arguments, arrival.machine, steered=steered_by(arrival, arguments), **kwargs)


def lists(image):
    """The scheduler's three lists and the EVBs' two, as a dict."""
    return {"running": ev.running(image), "not ready": aes.list_of(image, aes.AES_NRL),
            "woken": aes.list_of(image, aes.AES_DRL), "completed": ev.completed(image), "free": ev.free_evbs(image)}


# ---- every arrival of every scenario, as the ROM calls it and through its call word ----------------------------------
@pytest.mark.parametrize("name", ev.SCENARIOS)
def test_a_scenario_s_arrivals_are_the_ones_it_declares(name):
    assert len(ev.scenario(name)) == len(ev.SCENARIOS[name].arrivals)


@pytest.mark.parametrize("name", ev.SCENARIOS)
def test_an_arrival_s_machine_keeps_nothing_of_the_run_s_own_stack(name):
    """A machine is what the ROM's run CHANGED, its own frames aside: no poke of any arrival's lies in the stack band,
    where every case stages its frame afresh — a row made of one carries no dead frame of the run that made it."""
    band = case.STACK_BAND
    in_the_band = [(arrival.name, at) for arrival in ev.scenario(name) for at, data in arrival.machine.items()
                   if at < band.stop and band.start < at + len(data)]
    assert not in_the_band


@THROUGH
@pytest.mark.parametrize("arrival", ev.cases(), ids=ev.case_id)
def test_every_arrival(arrival, through_line_f):
    run(ev.arrival(*arrival), through_line_f=through_line_f)


def test_a_list_is_walked_through_the_bus_link_by_link():
    """`aes.list_of` — the one walker — answers each record as the bus carries it, a link stored WITH A TOP BYTE (a
    caller's tagged pointer, kept as handed) followed like any other: the head's, and one further down the list. A
    walker's own test over a laid list, no machine's state."""
    first, second = pp.EVBS[:2]
    laid = {ev.ZOMBIE_LIST: (first | aes.BUS_TAG).to_bytes(aes.LONG_BYTES, "big"),
            first + aes.EVB_LINK: (second | aes.BUS_TAG).to_bytes(aes.LONG_BYTES, "big"),
            second + aes.EVB_LINK: bytes(aes.LONG_BYTES)}
    assert ev.completed(make_image(laid)) == [first, second]


def test_every_routine_arrives_in_some_scenario():
    assert {routine for declared in ev.SCENARIOS.values() for routine in declared.arrivals} == set(ev.ROUTINES)


# ---- signal ------------------------------------------------------------------------------------------------------------
def signalled(scenario, which=0):
    """signal's `which`-th arrival of `scenario`: `(the lists before, the result, the EVB's process, its event)`."""
    arrival = ev.at(scenario, SIGNAL, which)
    image = before(arrival)
    evb, = arrival.arguments
    result = run(arrival)
    return lists(image), result, process_of(image, evb), case.word_in(image, evb + aes.EVB_MASK)


def posted(result, pd, event):
    return bool(result.word(pd + aes.PD_EVFLG) & event)


def test_signal_wakes_the_first_process_of_the_not_ready_list():
    """Inside forker (AES_RLR -1): the desk, parked first, is posted its key, made ready and moved to the woken list."""
    was, result, pd, event = signalled("a key wakes the desk")
    assert (was["running"], was["not ready"], was["woken"]) == (ev.RLR_IN_FORKER, [SHELL, SCREEN_MANAGER], [])
    assert pd == SHELL and posted(result, pd, event)
    after = lists(result.final)
    assert (after["not ready"], after["woken"]) == ([SCREEN_MANAGER], [SHELL])
    assert result.word(SHELL + aes.PD_STAT) == aes.PD_STAT_READY


def test_signal_walks_the_not_ready_list_to_a_process_behind_another():
    """The screen manager, second on the list: unlinked from the desk, which stays."""
    was, result, pd, _event = signalled("the mouse onto the bar wakes the screen manager")
    assert was["not ready"] == [SHELL, SCREEN_MANAGER] and pd == SCREEN_MANAGER
    after = lists(result.final)
    assert (after["not ready"], after["woken"]) == ([SHELL], [SCREEN_MANAGER])


def test_signal_posts_a_second_event_to_a_process_already_woken():
    """The desk's key, after its press woke it in the same forker pass: it is on the woken list, not the not-ready one —
    the walk ends past the screen manager, the event is posted and no list moves."""
    was, result, pd, event = signalled("a press and a key in one idle wake the desk", 1)
    assert pd == SHELL and SHELL not in was["not ready"] and was["not ready"] == [SCREEN_MANAGER]
    assert posted(result, pd, event)
    after = lists(result.final)
    assert (after["not ready"], after["woken"]) == (was["not ready"], was["woken"])


def test_signal_puts_a_woken_process_before_the_one_already_woken():
    """The timer woke the desk; the mouse onto the bar then wakes the screen manager in the same pass: the woken list
    holds it first, the desk behind it."""
    was, result, pd, _event = signalled("the timer comes and the mouse goes onto the bar in one idle", 1)
    assert pd == SCREEN_MANAGER and was["woken"] == [SHELL] and was["not ready"] == [SCREEN_MANAGER]
    after = lists(result.final)
    assert (after["not ready"], after["woken"]) == ([], [SCREEN_MANAGER, SHELL])


def test_signal_of_the_running_process_s_own_event_moves_nothing():
    """A queued key read: the EVB is the running process's — its event is posted, and it stays where it is."""
    was, result, pd, event = signalled("a queued key read")
    assert pd == was["running"] == SHELL and posted(result, pd, event)
    assert lists(result.final) == was


def test_signal_wakes_a_parked_process_while_another_runs():
    """A message sent by the screen manager to the desk, parked on its message wait."""
    was, result, pd, _event = signalled("a message to the parked desk", 1)
    assert (was["running"], pd, was["not ready"]) == (SCREEN_MANAGER, SHELL, [SHELL])
    after = lists(result.final)
    assert (after["not ready"], after["woken"], after["running"]) == ([], [SHELL], SCREEN_MANAGER)


# signal's LAST TEST — a process on the not-ready list that does not wait for the event posted — no caller reaches:
# signal is azombie's alone, for an EVB on its process's list, and a parked process waits for every EVB it holds (mwait
# stores the whole set in PD_EVWAIT before it reaches dsptch, $fe40bc). Pinned by handing signal, over a machine of the
# ROM's, an EVB no caller does: a FREE one, which still names the desk and an event of the wider wait it was part of.
def test_signal_of_an_event_its_parked_process_does_not_wait_for_wakes_nobody():
    machine = ev.parked_for_a_key_after_a_wider_wait()
    image = make_image(machine)
    waited = case.word_in(image, SHELL + aes.PD_EVWAIT)
    stale = next(evb for evb in ev.free_evbs(image)
                 if process_of(image, evb) == SHELL and not ev.evb_of(image, evb)["MASK"] & waited)
    event = ev.evb_of(image, stale)["MASK"]
    assert aes.list_of(image, aes.AES_NRL)[0] == SHELL and ev.running(image) != SHELL and event
    result = run_over(SIGNAL, (stale,), machine)
    assert posted(result, SHELL, event) and lists(result.final) == lists(image)
    assert result.word(SHELL + aes.PD_STAT) == aes.PD_STAT_WAITING


# ---- azombie -----------------------------------------------------------------------------------------------------------
HEAD_STAND_IN = ev.ZOMBIE_LIST - case.long_in(BASE_IMAGE, ev.ELINKOFF)


def completed_by(scenario, which=0):
    arrival = ev.at(scenario, AZOMBIE, which)
    evb, = arrival.arguments
    return before(arrival), run(arrival), evb


def test_azombie_onto_an_empty_completed_list():
    image, result, evb = completed_by("a key wakes the desk")
    assert ev.completed(image) == [] and ev.completed(result.final) == [evb]
    assert ev.evb_of(result.final, evb)["PRED"] == HEAD_STAND_IN
    assert ev.evb_of(result.final, evb)["FLAG"] == ev.COMPLETE


def test_azombie_onto_a_completed_list_that_holds_another():
    """The first's predecessor becomes the new head."""
    image, result, evb = completed_by("a press and a key in one idle wake the desk", 1)
    first, = ev.completed(image)
    assert ev.completed(result.final) == [evb, first] and ev.evb_of(result.final, first)["PRED"] == evb


@pytest.mark.parametrize("scenario, which, flag", (
    ("a message to the parked desk", 1, ev.NOCANCEL),
    (EVERYTHING, 0, ev.DELAY),
    ("the mouse leaves a rectangle while a double click is waited for", 0, ev.LEAVING),
), ids=("a wait being served", "a delay", "a mouse wait for a rectangle left"))
def test_azombie_leaves_the_flag_complete_alone(scenario, which, flag):
    image, result, evb = completed_by(scenario, which)
    assert ev.evb_of(image, evb)["FLAG"] == flag and ev.evb_of(result.final, evb)["FLAG"] == ev.COMPLETE


# ---- get_evb -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("arrival", ev.cases(GET_EVB), ids=ev.case_id)
def test_get_evb_takes_the_first_free_evb_and_clears_it(arrival):
    arrival = ev.arrival(*arrival)
    free = ev.free_evbs(before(arrival))
    result = run(arrival)
    assert result.long_answer() == free[0] and ev.free_evbs(result.final) == free[1:]
    assert result.after(free[0], aes.EVB_BYTES) == bytes(aes.EVB_BYTES)


def test_get_evb_clears_an_evb_that_held_a_wait():
    """The free list's first is the EVB the desk's last wait used: its fields are not zero before."""
    arrival = ev.at("a key ends a wait with a timer running", GET_EVB)
    image = before(arrival)
    assert any(image[ev.free_evbs(image)[0]:][:aes.EVB_BYTES])
    run(arrival)


# ---- evinsert ----------------------------------------------------------------------------------------------------------
def inserted(scenario, which):
    arrival = ev.at(scenario, EVINSERT, which)
    evb, head = arrival.arguments
    return ev.wait_list(before(arrival), head), run(arrival), evb, head


def test_evinsert_onto_an_empty_wait_list():
    """The keyboard wait of the desk's CDA: the EVB alone on it, its predecessor the head's stand-in."""
    was, result, evb, head = inserted(EVERYTHING, 0)
    assert was == [] and ev.wait_list(result.final, head) == [evb]
    assert ev.evb_of(result.final, evb)["PRED"] == head - aes.EVB_LINK


def test_evinsert_puts_the_last_to_wait_first():
    """The second mouse rectangle, onto the list the first one waits on: at the HEAD, the first behind it and its
    predecessor now this EVB."""
    was, result, evb, head = inserted(*ONTO_A_LIST_THAT_HOLDS_ONE)
    assert len(was) == 1 and ev.wait_list(result.final, head) == [evb, was[0]]
    assert ev.evb_of(result.final, was[0])["PRED"] == evb


# ---- takeoff -----------------------------------------------------------------------------------------------------------
def taken_off(scenario, which):
    arrival = ev.at(scenario, TAKEOFF, which)
    evb, = arrival.arguments
    return before(arrival), run(arrival), evb


def head_of(image, evb):
    """The wait list's head an EVB at the front of it hangs from: its stand-in predecessor's link."""
    return ev.evb_of(image, evb)["PRED"] + aes.EVB_LINK


def test_takeoff_of_the_only_evb_on_its_wait_list():
    image, result, evb = taken_off("a key wakes the desk", 0)
    head = head_of(image, evb)
    assert ev.wait_list(image, head) == [evb] and ev.wait_list(result.final, head) == []
    assert ev.free_evbs(result.final) == [evb] + ev.free_evbs(image)


def test_takeoff_of_an_evb_with_one_after_it():
    """The second rectangle's wait, at the head with the first's behind: the first is left at the head, its
    predecessor the head's stand-in — and its parameter untouched: no delay, though the EVB taken off has a parameter
    of its own (its rectangle's x and y)."""
    image, result, evb = taken_off(EVERYTHING, 1)
    head = head_of(image, evb)
    after, = ev.wait_list(image, head)[1:]
    assert ev.evb_of(image, evb)["PARM"] and not ev.evb_of(image, evb)["FLAG"] & ev.DELAY
    assert ev.wait_list(result.final, head) == [after]
    assert ev.evb_of(result.final, after)["PRED"] == ev.evb_of(image, evb)["PRED"]
    assert ev.evb_of(result.final, after)["PARM"] == ev.evb_of(image, after)["PARM"]


def test_takeoff_of_a_delay_with_none_after_it():
    """A key ends a wait whose timer still runs: the delay list emptied, nothing handed on."""
    image, result, evb = taken_off("a key ends a wait with a timer running", 0)
    fields = ev.evb_of(image, evb)
    assert fields["FLAG"] == ev.DELAY and fields["LINK"] == 0 and fields["PARM"]
    assert ev.wait_list(result.final, head_of(image, evb)) == []


# TWO DELAYS PENDING needs a third process: the screen manager asks for no timer, and a process has one evnt_multi at a
# time. Over the labelled class (`aes_evasync.STAGED_APPLICATION`): Tier 1 only, and no claim about a real machine's
# third process, which is an accessory.
DELAY_LIST = ev.EV["AES_DELAY_LIST"]
TICK_MS = ev.TICK_MS
TWO_DELAYS = {"ahead": f"{ev.STAGED_APPLICATION}: a key ends a wait whose delay has a longer one behind it",
              "behind": f"{ev.STAGED_APPLICATION}: a key ends a wait whose delay is behind a shorter one"}


def ticks_left(image):
    """The delay list, as each EVB's ticks after the one before it."""
    return [ev.evb_of(image, evb)["PARM"] for evb in ev.wait_list(image, DELAY_LIST)]


SHORT_TICKS, LONGER_TICKS = ev.A_SHORT_TIMER_MS // TICK_MS, ev.A_LONGER_TIMER_MS // TICK_MS


def test_takeoff_of_a_delay_hands_its_ticks_to_the_one_after_it():
    """`STAGED_APPLICATION`: the desk's delay of 200 ms cancelled with the application's of 600 behind it — the list
    holds differences, so the application's 400 after the desk's becomes 600 from now."""
    image, result, evb = taken_off(TWO_DELAYS["ahead"], 0)
    short, longer = SHORT_TICKS, LONGER_TICKS
    assert ev.wait_list(image, DELAY_LIST)[0] == evb and ticks_left(image) == [short, longer - short]
    assert ticks_left(result.final) == [longer]


def test_takeoff_of_a_delay_behind_another_hands_nothing_on():
    """`STAGED_APPLICATION`: ...and the desk's of 600 ms behind the application's of 200 — off the list's end, the
    application's untouched."""
    image, result, evb = taken_off(TWO_DELAYS["behind"], 0)
    short, longer = SHORT_TICKS, LONGER_TICKS
    assert ev.wait_list(image, DELAY_LIST)[1] == evb and ticks_left(image) == [short, longer - short]
    assert ticks_left(result.final) == [short]


def test_signal_wakes_the_process_between_two_others():
    """`STAGED_APPLICATION`: three parked — the application, the desk, the screen manager. The desk is unlinked from
    between them."""
    was, result, pd, _event = signalled(TWO_DELAYS["ahead"])
    application = was["not ready"][0]
    assert was["not ready"] == [application, SHELL, SCREEN_MANAGER] and pd == SHELL
    after = lists(result.final)
    assert (after["not ready"], after["woken"]) == ([application, SCREEN_MANAGER], [SHELL])


def test_every_case_over_the_staged_application_names_the_class():
    """THE CLASS IS LABELLED (`aes_pdpipe`): a case of this battery written over a two-delays scenario — a third
    process's machine — says so, `STAGED_APPLICATION` in its docstring; the cases parametrized over EVERY scenario
    carry the label in their ids, which are the scenarios' names."""
    module = sys.modules[__name__]
    unlabelled = [name for name, function in vars(module).items()
                  if name.startswith("test_") and callable(function) and OVER_THE_APPLICATION in inspect.getsource(function)
                  and "STAGED_APPLICATION" not in inspect.getsource(function)]
    assert not unlabelled, unlabelled
    assert all(ev.STAGED_APPLICATION in scenario for scenario in TWO_DELAYS.values())
    over_a_third_process = [name for name in ev.SCENARIOS if "application" in inspect.getsource(ev.SCENARIOS[name].run)]
    assert sorted(over_a_third_process) == sorted(TWO_DELAYS.values()), "a scenario over an application without the label"


OVER_THE_APPLICATION = "TWO_DELAYS["


def test_a_scenario_s_application_is_vetted_before_the_dispatcher_enters_it(monkeypatch):
    """`STAGED_APPLICATION`: the two-delays scenarios run the dispatcher into the application's stub by a watched run
    of their own — the application is vetted there as on every road in (`aes_pdpipe.vet_the_application`) — one that no longer is what it
    names (here: another delay than its stub pushes) is refused before the loop runs."""
    made = pp.staged_application
    monkeypatch.setattr(pp, "staged_application",
                        lambda call, argument: made(call, argument)._replace(argument=argument + ev.TICK_MS))
    with pytest.raises(AssertionError, match="does not push the argument its application names"):
        ev.SCENARIOS[TWO_DELAYS["ahead"]].run()


# ---- apret -------------------------------------------------------------------------------------------------------------
def answered(scenario, which=0):
    arrival = ev.at(scenario, APRET, which)
    mask, = arrival.arguments
    image = before(arrival)
    return image, run(arrival), next(evb for evb in ev.evlist(image, ev.running(image))
                                     if ev.evb_of(image, evb)["MASK"] == mask)


HIGH_WORD = ev.EV["EVB_RETURN_HIGH_SHIFT"]     # an answer's high word: the buttons' state, a rectangle's width
CLICKS = ev.EV["EVB_PARM_CLICKS_SHIFT"]        # a parameter's: a button wait's clicks, a mouse wait's x


def test_a_wait_s_clicks_lie_where_ev_multi_packs_them():
    """ONE LAYOUT, named by two headers — the shift evremove reads a button wait's clicks by (`aes/evasync.h`) and the
    one ev_multi's callers pack them by (`aes/evdoor.h`): pinned equal, no header including the other."""
    assert CLICKS == aes.EV_BUTTON_CLICKS_SHIFT


def button_answer(clicks):
    """A button wait's answer: the buttons' state (the left one down) over the clicks."""
    return aes_event.LEFT_BUTTON << HIGH_WORD | clicks


def test_apret_answers_the_key_and_frees_its_evb():
    image, result, evb = answered("a key wakes the desk")
    answer = ev.evb_of(image, evb)["RETURN"]
    assert result.answer() == answer and answer >> HIGH_WORD == 0 and result.word(ev.BUTTON_STATE) == 0
    assert ev.completed(result.final) == [] and ev.evlist(result.final, SHELL) == []
    assert ev.free_evbs(result.final)[0] == evb
    assert [result.word(SHELL + field) for field in (aes.PD_EVBITS, aes.PD_EVWAIT, aes.PD_EVFLG)] == [0, 0, 0]


def test_apret_answers_the_clicks_and_leaves_the_buttons_state():
    """A double click: the answer's low word the clicks, its high word — the buttons — left in the word ev_rets reads."""
    image, result, evb = answered("a double click ends a double-click wait")
    assert ev.evb_of(image, evb)["RETURN"] == button_answer(ev.DOUBLE)
    assert result.answer() == ev.DOUBLE and result.word(ev.BUTTON_STATE) == aes_event.LEFT_BUTTON


def test_apret_of_a_mouse_wait_leaves_its_rectangle_s_width_as_the_buttons_state():
    """A ROM QUIRK: a mouse wait keeps its rectangle's width and height where a button wait keeps its answer, and
    apret stores the high word of whichever it frees."""
    image, result, evb = answered("the mouse leaves a rectangle while a double click is waited for")
    _x, _y, width, height = ev.ROUND_THE_MOUSE
    assert ev.evb_of(image, evb)["RETURN"] == width << HIGH_WORD | height
    assert result.answer() == height and result.word(ev.BUTTON_STATE) == width


def test_apret_finds_an_evb_behind_others_on_both_lists():
    """A press, then the mouse leaving: the button's EVB is second on the process's list and second on the completed
    list — taken off both, the mouse's left on both, and the mouse's bit left in the three event words."""
    image, result, evb = answered("a press, then the mouse leaves, in one idle")
    other, = (each for each in ev.evlist(image, SHELL) if each != evb)
    assert ev.evlist(image, SHELL) == [other, evb] and ev.completed(image) == [other, evb]
    assert ev.evlist(result.final, SHELL) == [other] and ev.completed(result.final) == [other]
    kept = ev.evb_of(image, other)["MASK"]
    assert [result.word(SHELL + field) for field in (aes.PD_EVBITS, aes.PD_EVWAIT, aes.PD_EVFLG)] == [kept] * 3


def test_apret_takes_the_head_of_a_completed_list_with_one_behind():
    """A press and a key: the key's EVB heads the completed list, the press's behind it becomes its head."""
    image, result, evb = answered("a press and a key in one idle wake the desk")
    assert ev.completed(image)[0] == evb and len(ev.completed(image)) == 2
    behind = ev.completed(image)[1]
    assert ev.completed(result.final) == [behind] and ev.evb_of(result.final, behind)["PRED"] == HEAD_STAND_IN


# apret's two refusals: NO CALLER REACHES THEM. ev_block and ev_multi call apret only for a mask iasync answered them
# and an event that came — a bit of PD_EVFLG, which only signal sets, for an EVB azombie has just put on the completed
# list, or a bit acancel kept, which it keeps only for a completed EVB (EVB_FLAG is 0, 4 or 8 until azombie makes it
# 2); and an EVB leaves the completed list in apret alone. The arms are pinned by handing apret, over a machine of the
# ROM's, a mask its caller does not: at evnt_multi's acancel — the waits not yet cancelled — a mask no EVB has (100),
# the mask of a wait whose event did not come (101), and two EVBs' masks ORed (100: the mask is matched whole).
NO_SUCH_EVENT = 0x4000


def at_the_cancel(scenario="a key wakes the desk"):
    """evnt_multi's acancel arrival, as a machine to hand apret over — and the running process's EVBs there, by mask
    (in its list's order)."""
    arrival = ev.at(scenario, ACANCEL)
    image = before(arrival)
    waits = {ev.evb_of(image, evb)["MASK"]: evb for evb in ev.evlist(image, ev.running(image))}
    return arrival._replace(name=APRET), waits, image


def refused(mask):
    arrival, _waits, _image = at_the_cancel()
    return run(arrival, (mask,))


def test_apret_of_an_event_no_evb_has_answers_100_and_stores_nothing():
    result = refused(NO_SUCH_EVENT)
    assert result.answer() == ev.EV["APRET_NO_EVB"] and aes.stored_nothing(result)


def test_apret_of_a_wait_not_completed_answers_101_and_stores_nothing():
    _arrival, waits, image = at_the_cancel()
    pending = next(mask for mask, evb in waits.items() if evb not in ev.completed(image))
    result = refused(pending)
    assert result.answer() == ev.EV["APRET_NOT_COMPLETE"] and aes.stored_nothing(result)


def test_apret_matches_the_whole_mask():
    """Two waits' masks ORed is no EVB's mask — though each bit is one's."""
    _arrival, waits, _image = at_the_cancel()
    one, other = sorted(waits)[:2]
    assert refused(one | other).answer() == ev.EV["APRET_NO_EVB"]


def test_apret_of_the_completed_wait_among_pending_ones():
    """...and over the same machine, the mask of the wait that DID complete: found behind two pending waits on the
    desk's list, which stay."""
    arrival, waits, image = at_the_cancel()
    done, = (mask for mask, evb in waits.items() if evb in ev.completed(image))
    assert ev.evlist(image, SHELL)[-1] == waits[done]
    result = run(arrival, (done,))
    assert ev.evlist(result.final, SHELL) == ev.evlist(image, SHELL)[:-1]


# THE UNLINK FROM THE PROCESS'S LIST STORES THE FREED EVB'S OWN LINK ($fe4226 `move.l (a5),(a4)`) — and in every call
# the ROM makes that link is 0: ev_multi's aprets run in the order it queued its waits and iasync pushes each at the
# list's head, so the first apret always takes the DEEPEST EVB, the last on the list. NO CALLER HANDS the other shape
# (labelled, as apret's refusals above are): over evnt_multi's own machine at its acancel, with two waits completed,
# apret is handed the mask of the completed wait that has ANOTHER BEHIND IT — the one its caller would take second.
@pytest.mark.parametrize("scenario", ("a press and a key in one idle wake the desk",
                                      "the mouse onto the bar and a press in one idle"))
def test_apret_of_a_completed_wait_with_another_behind_it_on_its_process_s_list(scenario):
    arrival, waits, image = at_the_cancel(scenario)
    listed = list(waits.values())
    mask, evb = next((mask, evb) for mask, evb in waits.items() if evb in ev.completed(image) and evb != listed[-1])
    assert ev.evb_of(image, evb)["NEXT"], "the premise: the EVB freed is not the last of its process's list"
    result = run(arrival, (mask,))
    assert ev.evlist(result.final, ev.running(image)) == [each for each in listed if each != evb]


# ---- acancel -----------------------------------------------------------------------------------------------------------
def cancelled(scenario):
    arrival = ev.at(scenario, ACANCEL)
    image = before(arrival)
    return image, run(arrival), ev.evlist(image, ev.running(image))


def test_acancel_keeps_the_completed_wait_and_frees_the_rest():
    image, result, waits = cancelled(EVERYTHING)
    done, = (evb for evb in waits if evb in ev.completed(image))
    assert result.answer() == ev.evb_of(image, done)["MASK"] == ev.MU_TIMER
    assert ev.evlist(result.final, SHELL) == [done] and len(waits) == ev.WAITS_OF_EVERY_EVENT
    assert result.word(SHELL + aes.PD_EVBITS) == result.word(SHELL + aes.PD_EVWAIT) == ev.MU_TIMER
    assert ev.free_evbs(result.final)[:ev.QUEUED_OF_EVERY_EVENT] == [evb for evb in reversed(waits) if evb != done]


def test_acancel_leaves_the_event_that_came_posted():
    """PD_EVFLG is left as it is — the completed wait's event still posted, for apret to clear — while PD_EVBITS and
    PD_EVWAIT lose the cancelled waits' bits. (A cancelled wait's own bit is never set in PD_EVFLG: only signal sets
    one, for a completed EVB.)"""
    image, result, waits = cancelled("a key wakes the desk")
    done, = (ev.evb_of(image, evb)["MASK"] for evb in waits if evb in ev.completed(image))
    assert result.word(SHELL + aes.PD_EVFLG) == case.word_in(image, SHELL + aes.PD_EVFLG) == done
    assert result.word(SHELL + aes.PD_EVBITS) == result.word(SHELL + aes.PD_EVWAIT) == done


def test_acancel_answers_every_completed_wait():
    """A press and a key: both kept, both answered."""
    image, result, waits = cancelled("a press and a key in one idle wake the desk")
    done = [evb for evb in waits if evb in ev.completed(image)]
    assert len(done) == 2 and ev.evlist(result.final, SHELL) == done
    assert result.answer() == ev.evb_of(image, done[0])["MASK"] | ev.evb_of(image, done[1])["MASK"]


def test_acancel_of_a_completed_wait_at_the_head_goes_on_from_it():
    """The screen manager's mouse wait, completed, heads its list; the two behind it are cancelled."""
    image, result, waits = cancelled("the mouse onto the bar wakes the screen manager")
    assert waits[0] in ev.completed(image) and ev.evlist(result.final, SCREEN_MANAGER) == waits[:1]


# acancel's SKIP — an EVB whose event is not among the mask — no caller reaches: evnt_multi cancels with the masks of
# every wait it queued, and a process holds no other. Pinned by handing acancel, over evnt_multi's own machine there, a
# mask of fewer events.
@pytest.mark.parametrize("which", (0, 1, 2), ids=("the first wait alone", "the second", "the third"))
def test_acancel_of_some_events_leaves_the_other_waits(which):
    arrival = ev.at("a key wakes the desk", ACANCEL)
    image = before(arrival)
    waits = ev.evlist(image, SHELL)
    mask = ev.evb_of(image, waits[which])["MASK"]
    result = run(arrival, (mask,))
    pending = waits[which] not in ev.completed(image)
    assert ev.evlist(result.final, SHELL) == [evb for evb in waits if not (pending and evb == waits[which])]
    assert result.answer() == (0 if pending else mask)


def test_acancel_of_no_event_stores_nothing():
    result = run(ev.at("a key wakes the desk", ACANCEL), (0,))
    assert result.answer() == 0 and aes.stored_nothing(result)


# ---- evremove ----------------------------------------------------------------------------------------------------------
def removed(scenario, which=0):
    arrival = ev.at(scenario, EVREMOVE, which)
    evb, answer = arrival.arguments
    return before(arrival), run(arrival), evb, answer & aes.WORD_MASK


def pending(image):
    return case.word_in(image, ev.BPEND)


def test_evremove_keeps_the_answer_and_completes_the_wait():
    """The desk's key: the key's word ORed into the answer, the EVB off the keyboard wait and onto the completed list."""
    image, result, evb, answer = removed("a key wakes the desk")
    assert ev.evb_of(result.final, evb)["RETURN"] == ev.evb_of(image, evb)["RETURN"] | answer
    assert ev.wait_list(result.final, head_of(image, evb)) == [] and ev.completed(result.final) == [evb]
    assert pending(result.final) == pending(image)


def test_evremove_ors_the_clicks_into_the_buttons_state():
    """A button wait's answer already holds the buttons in its high word (post_button's): the clicks are ORed in."""
    image, result, evb, answer = removed("a double click ends a double-click wait")
    assert ev.evb_of(image, evb)["RETURN"] == button_answer(0) and answer == ev.DOUBLE
    assert ev.evb_of(result.final, evb)["RETURN"] == button_answer(ev.DOUBLE)


def test_evremove_counts_a_multi_click_wait_down():
    """...and the pending multi-click waits, 2 (the snapshot's 1, and this wait), are counted down to 1."""
    image, result, _evb, _answer = removed("a double click ends a double-click wait")
    assert (pending(image), pending(result.final)) == (2, 1)


def test_evremove_never_counts_the_multi_click_waits_below_one():
    """The desk's own double-click wait, the only one pending in the snapshot: the count stays 1."""
    image, result, evb, _answer = removed("a press wakes the desk")
    assert ev.evb_of(image, evb)["PARM"] >> CLICKS == ev.DOUBLE and (pending(image), pending(result.final)) == (1, 1)


def test_evremove_of_a_wait_for_no_clicks_counts_nothing_down():
    """A key, with a double click waited for beside it (2 pending): a keyboard wait's parameter is 0."""
    image, result, evb, _answer = removed("a key ends a wait for a double click")
    assert ev.evb_of(image, evb)["PARM"] == 0 and (pending(image), pending(result.final)) == (2, 2)


def test_evremove_reads_a_mouse_wait_s_rectangle_as_its_clicks():
    """A ROM QUIRK: no kind is tested, and a mouse wait keeps its rectangle's x where a button wait keeps its clicks.
    The mouse leaves a rectangle at x 150 while a double click is waited for: the pending multi-click waits are
    counted down by a wait that asked for no click."""
    image, result, evb, _answer = removed("the mouse leaves a rectangle while a double click is waited for")
    assert ev.evb_of(image, evb)["PARM"] >> CLICKS == ev.ROUND_THE_MOUSE[0]
    assert (pending(image), pending(result.final)) == (2, 1)


def test_evremove_reads_the_low_byte_of_the_clicks():
    """...and at x 257 — a low byte of 1, one click — it is not."""
    image, result, evb, _answer = removed("the mouse enters a rectangle at x 257 while a double click is waited for")
    x = ev.evb_of(image, evb)["PARM"] >> CLICKS
    assert x == ev.AT_X_257[0] and x & ev.EV["EVB_PARM_CLICKS_MASK"] == ev.EV["ONE_CLICK"]
    assert (pending(image), pending(result.final)) == (2, 2)


def test_evremove_of_a_wait_behind_another_on_its_list():
    """Two rectangles, the first one's wait behind the second's on the mouse wait: taken off the list's end."""
    image, result, evb, _answer = removed("two rectangles, the first one waited for left")
    ahead = ev.evb_of(image, evb)["PRED"]
    head = head_of(image, ahead)
    assert ev.wait_list(image, head) == [ahead, evb] and ev.wait_list(result.final, head) == [ahead]


def test_evremove_of_a_wait_ahead_of_another_on_its_list():
    """...and the second one's, at the head: the first's becomes the head, its predecessor the head's stand-in."""
    image, result, evb, _answer = removed("two rectangles, the second one waited for left")
    head = head_of(image, evb)
    behind, = ev.wait_list(image, head)[1:]
    assert ev.wait_list(result.final, head) == [behind]
    assert ev.evb_of(result.final, behind)["PRED"] == ev.evb_of(image, evb)["PRED"]


A_KEY_FROM_80_UP = 0x9C0D                # a key's word, its scan code $9c: the top bit set


def test_evremove_s_answer_is_an_unsigned_word():
    """A key's word with its top bit set — a scan code from $80 up, which a Keytbl table can map — ORed in as a word:
    the answer's high word stays 0. No delivery here types one, so the frame's word is the case's."""
    arrival = ev.at("a key wakes the desk", EVREMOVE)
    evb, _answer = arrival.arguments
    result = run(arrival, (evb, A_KEY_FROM_80_UP))
    assert ev.evb_of(result.final, evb)["RETURN"] == A_KEY_FROM_80_UP


# ---- pointers with a top byte: the bus drops it, the lists keep it ---------------------------------------------------
TAGGED = {
    SIGNAL: ("a key wakes the desk", 0), AZOMBIE: ("a press and a key in one idle wake the desk", 1),
    TAKEOFF: (EVERYTHING, 1), EVREMOVE: ("two rectangles, the second one waited for left", 0),
    EVINSERT: ONTO_A_LIST_THAT_HOLDS_ONE,
}


@THROUGH
@pytest.mark.parametrize("routine", TAGGED, ids=lambda name: name.removeprefix("AES_ROM_").lower())
def test_a_pointer_with_a_top_byte_is_put_on_the_bus(routine, through_line_f):
    """Each pointer argument tagged: dereferenced through the 24-bit bus, and STORED in the lists as it was handed."""
    arrival = ev.at(TAGGED[routine][0], routine, TAGGED[routine][1])
    pointers = vdi.frame_argtypes(routine)
    tagged = tuple(value | aes.BUS_TAG if argtype is ev.LONG else value
                   for argtype, value in zip(pointers, arrival.arguments))
    assert tagged != arrival.arguments
    run(arrival, tagged, through_line_f=through_line_f)


def test_azombie_stores_the_pointer_it_was_handed_top_byte_and_all():
    arrival = ev.at(TAGGED[AZOMBIE][0], AZOMBIE, TAGGED[AZOMBIE][1])
    evb, = arrival.arguments
    result = run(arrival, (evb | aes.BUS_TAG,))
    assert result.long(ev.ZOMBIE_LIST) == evb | aes.BUS_TAG


# ---- the ORDER of reads and stores, shown by a list that lies over the EVB put on it ---------------------------------
# No caller hands these: a wait list's head is a CDA's, a PD's or a semaphore's longword, never an EVB's own field.
def test_evinsert_reads_the_list_s_first_before_it_stores():
    """The "list" is the EVB's own predecessor field: its old value is the first, read before the EVB's predecessor is
    stored over it — so the EVB's link is that old value, and the store through the stand-in (the head itself) puts
    the EVB there."""
    arrival = ev.at(ONTO_A_LIST_THAT_HOLDS_ONE[0], EVINSERT, ONTO_A_LIST_THAT_HOLDS_ONE[1])
    evb, _head = arrival.arguments
    image = before(arrival)
    old = ev.evb_of(image, evb)["PRED"]
    result = run(arrival, (evb, evb + aes.EVB_PRED))
    assert ev.evb_of(result.final, evb)["LINK"] == old and ev.evb_of(result.final, evb)["PRED"] == evb


def test_azombie_of_the_evb_already_at_the_head_of_the_completed_list():
    """The completed list's head completed again: its link is read from the list AFTER nothing — it links to itself,
    and its predecessor, stored twice, ends as the head's stand-in."""
    arrival = ev.at("a key wakes the desk", SIGNAL)._replace(name=AZOMBIE)      # where the EVB heads the list
    evb, = arrival.arguments
    assert ev.completed(before(arrival))[:1] == [evb]
    result = run(arrival)
    assert ev.evb_of(result.final, evb)["LINK"] == evb and ev.evb_of(result.final, evb)["PRED"] == HEAD_STAND_IN


# ---- the registry: Tier 3's rows ---------------------------------------------------------------------------------------
# Every arrival of every scenario (the staged application's aside) was priced as a row would be (`make bench`'s
# instrument, 167 arrivals); each routine's WORST is registered first, labelled so, then the rows that show its other
# shapes. Measured and left out, none any routine's worst: the rest of the arrivals, each within its routine's range —
# signal 0.65..0.77, azombie 0.56..0.63, get_evb 0.83 every one, evinsert 0.48..0.50, takeoff 0.60..0.63, apret
# 0.72..0.79, acancel 0.68..0.78, evremove 0.51..0.57.
def register(label, scenario, routine, which=0, **kwargs):
    assert ev.STAGED_APPLICATION not in scenario, f"{scenario}: a staged application's machines are Tier 1 only"
    arrival = ev.at(scenario, routine, which)
    aes.register(label, routine, arrival.arguments, arrival.machine, **kwargs)


BAR = "the mouse onto the bar wakes the screen manager"
PRESS_THEN_LEAVE = "a press, then the mouse leaves, in one idle"
ROWS = (
    ("a process woken from behind another on the not-ready list", BAR, SIGNAL, 0),
    ("a process woken, first on the not-ready list", KEY, SIGNAL, 0),
    ("the running process's own event", "a queued key read", SIGNAL, 0),
    ("a process already woken", "a press and a key in one idle wake the desk", SIGNAL, 1),
    ("a wait of a process woken from behind another", BAR, AZOMBIE, 0),
    ("the running process's own wait", "a queued key read", AZOMBIE, 0),
    ("a parked process's wait, the completed list holding one", "a message to the parked desk", AZOMBIE, 1),
    ("an EVB that held a wait", "a key ends a wait with a timer running", GET_EVB, 0),
    ("onto a wait list that holds one", ONTO_A_LIST_THAT_HOLDS_ONE[0], EVINSERT, ONTO_A_LIST_THAT_HOLDS_ONE[1]),
    ("onto an empty wait list", EVERYTHING, EVINSERT, 0),
    ("a wait with one after it", EVERYTHING, TAKEOFF, 1),
    ("the only wait on its list", KEY, TAKEOFF, 0),
    ("a delay with none after it", "a key ends a wait with a timer running", TAKEOFF, 0),
    ("a wait behind another on both lists", PRESS_THEN_LEAVE, APRET, 0),
    ("a key's wait, alone on both lists", KEY, APRET, 0),
    ("both waits completed and kept", PRESS_THEN_LEAVE, ACANCEL, 0),
    ("one completed wait kept, two cancelled", KEY, ACANCEL, 0),
    ("one completed wait kept, five cancelled", EVERYTHING, ACANCEL, 0),
    ("a mouse wait, its process woken from behind another", BAR, EVREMOVE, 0),
    ("a double-click wait counted down", "a double click ends a double-click wait", EVREMOVE, 0),
    ("a key's wait", KEY, EVREMOVE, 0),
)
# ...and each routine through its call word: verified, unpriced.
THROUGH_LINE_F = {**TAGGED, GET_EVB: ("a key ends a wait with a timer running", 0), APRET: (KEY, 0), ACANCEL: (KEY, 0)}


def _register_rows():
    for label, scenario, routine, which in ROWS:
        register(label, scenario, routine, which)
    for routine, (scenario, which) in THROUGH_LINE_F.items():
        register("its caller's call", scenario, routine, which, through_line_f=True)


_register_rows()
