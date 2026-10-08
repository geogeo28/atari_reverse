"""A WAIT QUEUED, AND WAITED FOR (`src/aes/evwait.c`): gemasync's iasync and mwait, geminput's five kinds of wait and
the semaphore's release.

    iasync(code, parm)   evb = get_evb(); onto rlr's list; evb->pd = rlr; the first event bit rlr's EVBs do not hold;
                         code 1 aqueue(read) 2 aqueue(write) 3 adelay 4 amutex 5 akbin 6 amouse 7 abutton, else nothing;
                         answers the bit                                                            ($fe40ec)
    mwait(mask)          rlr->evwait = mask; none of them come: rlr->stat = WAITING, dsptch; answers rlr->evflg ($fe40b2)
    akbin(evb)           a key queued: evb->return = dq(), azombie; else evinsert(the CDA's keyboard wait)   ($fe5520)
    adelay(evb, ticks)   0 → 1; under spl7: the countdown armed or shortened; evb into the delta list        ($fe5566)
    abutton(evb, parm)   downorup(the buttons, parm): return = buttons << 16, azombie; else (clicks > 1: bpend++)
                         evb->parm = parm, evinsert(the CDA's button wait)                           ($fe55f8)
    amouse(evb, moblk)   the MOBLK copied; inside != its leave flag: azombie; else the LEAVE flag, x/y → parm,
                         w/h → return, evinsert(the CDA's mouse wait)                                ($fe5666)
    amutex(evb, spb)     tak_flag(spb): azombie; else evinsert(spb's wait list)                       ($fe4e8e)
    unsync(spb)          count--; 0: no waiter → owner 0; else wait = first->link, owner = first->pd, count 1,
                         azombie(first), dsptch                                                      ($fe4eb8)

EVERY MACHINE IS THE ROM's OWN, at the moment the ROM makes the call (`aes_evlib`: the ARRIVALS of an application's
evnt_keybd / evnt_button / evnt_mouse / evnt_timer / evnt_mesag / appl_read / appl_write / wind_update / evnt_multi,
watched at the routines' entries) — and every frame the one its caller pushed, but for the cases SAID to hand one no
caller does (ARGUMENT-CLASS cases, each labelled where it stands): a code iasync's callers never hand, a mask mwait's
never do, a pointer with a top byte, amutex over a lock tak_flag takes (its callers come only after tak_flag refused),
and a semaphore staged in the band (the ROM keeps one, the screen's).

A CALL THAT REACHES THE DISPATCHER is held where the C stops, to the ROM's memory AT DSPTCH (`aes_evlib.switched`): a
wait nothing satisfies leaves mwait's process WAITING (a block); unsync's hand-over leaves its caller READY (a yield).

UNSYNC's LEAF BATTERY (the twin of a door entry): every arm — still held, the last hold with nobody waiting, a
release too many, the hand-over to an only waiter and to the first of two (twice: a staged application's wait before
the screen manager's, and two waits of the screen manager's own) — the pointer on the bus, the count as the WORD it
is, the owner as the LONG it is.

REFUSED BY NAME off target: iasync with no EVB free (`evwait.c`: get_evb's "none" is not tested by the ROM, which
builds the wait at address 0 — a bus error on a 68000; held through ev_multi, `test_aes_evmulti.py`).
UNPINNED, and why: akbin's key count as a byte (the queue holds eight); adelay's ticks counted with no delay pending
as a long (65,536 ticks counted and none pending).
"""
import struct

import pytest

from harness import make_image

import aes
import aes_evasync as evasync
import aes_event
import aes_evlib as evlib
import aes_pdpipe
import case
import test_aes_wm_update as wm_update
from aes_evlib import ABUTTON, ADELAY, AKBIN, AMOUSE, AMUTEX, IASYNC, MWAIT, UNSYNC
from aes_gsx import THROUGH
from case import merge_pokes

pytestmark = pytest.mark.collected_with(by=aes_event.scenario_of_a_case)
ROUTINES = (IASYNC, MWAIT, AKBIN, ADELAY, ABUTTON, AMOUSE, AMUTEX, UNSYNC)
APPLICATION = evlib.STAGED_APPLICATION
SHELL, SCREEN_MANAGER, THIRD = evlib.SHELL, evlib.SCREEN_MANAGER, aes_pdpipe.SPARE_PD
FM = aes.header_constants("fmlib.h")
EV = evasync.EV


before = aes_event.before


def evb_of(image, evb):
    return evasync.evb_of(image, evb & aes.LONG_MASK & ~aes.BUS_TAG)


def cda_list(image, field):
    """The EVBs on a wait list of the running process's CDA."""
    return evasync.wait_list(image, case.long_in(image, aes.AES_GL_CDA) + field)


def process_word(image, field, pd=None):
    return case.word_in(image, (evasync.running(image) if pd is None else pd) + field)


# ---- every arrival of every scenario ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", evlib.SCENARIOS)
def test_a_scenario_s_arrivals_are_the_ones_it_declares(name):
    """...and the ones that reach the dispatcher are the ones it declares to (`aes_evlib.SWITCHING`: what the cases
    are split by)."""
    assert len(evlib.scenario(name)) == len(evlib.SCENARIOS[name].arrivals)
    assert evlib.reaching_the_dispatcher(name) == evlib.SWITCHING.get(name, ())


@pytest.mark.parametrize("name", evlib.SCENARIOS)
def test_an_arrival_s_machine_keeps_nothing_of_the_run_s_own_stack(name):
    band = case.STACK_BAND
    assert not [(arrival.name, at) for arrival in evlib.scenario(name) for at, data in arrival.machine.items()
                if at < band.stop and band.start < at + len(data)]


def test_every_routine_arrives_in_some_scenario_returning_and_reaching_the_dispatcher_where_it_can():
    arrive = {routine for declared in evlib.SCENARIOS.values() for routine in declared.arrivals}
    assert arrive == set(evlib.ROUTINES)
    reach = {evlib.SCENARIOS[name].arrivals[nth] for name, nth in evlib.cases(switching=True)}
    # Every routine with dsptch in its closure — but ev_dclick, ev_rets, ev_mchk and the five kinds of wait, which
    # only queue; and iasync, whose callers wait afterwards.
    assert reach == {MWAIT, UNSYNC, evlib.EV_BLOCK, evlib.AP_RDWR, evlib.EV_KEYBD, evlib.EV_BUTTON, evlib.EV_MOUSE, evlib.EV_MESAG, evlib.EV_TIMER}


@pytest.mark.parametrize("arrival", evlib.cases(*ROUTINES, switching=True), ids=evlib.case_id)
def test_every_arrival_that_reaches_the_dispatcher_is_the_rom_s_at_dsptch(arrival):
    evlib.run(evlib.arrival(*arrival))


@THROUGH
@pytest.mark.parametrize("arrival", evlib.cases(*ROUTINES, switching=False), ids=evlib.case_id)
def test_every_arrival_that_returns(arrival, through_line_f):
    evlib.run(evlib.arrival(*arrival), through_line_f=through_line_f)


def test_the_scenarios_over_a_staged_application_carry_its_label_and_no_other_does():
    """The label is the class's (`aes_pdpipe.STAGED_APPLICATION`): a scenario that starts from one says so in its
    name, so every case made of it does."""
    over_one = {name for name in evlib.SCENARIOS if name.startswith(APPLICATION)}
    assert len(over_one) == 6
    assert all(APPLICATION not in name for name in set(evlib.SCENARIOS) - over_one)


# ---- iasync ----------------------------------------------------------------------------------------------------------------
def test_iasync_takes_the_first_free_evb_for_the_running_process():
    arrival = evlib.at("evnt_keybd, none", IASYNC)
    image = before(arrival)
    free, held_before = evasync.free_evbs(image), evasync.evlist(image, SHELL)
    result = evlib.run(arrival)
    evb = free[0]
    assert evasync.free_evbs(result.final) == free[1:] and evasync.evlist(result.final, SHELL) == [evb] + held_before
    block = evb_of(result.final, evb)
    assert (block["PD"], block["MASK"], result.answer()) == (SHELL, 1, 1)
    assert process_word(result.final, aes.PD_EVBITS) == process_word(image, aes.PD_EVBITS) | 1


def test_iasync_gives_each_wait_of_a_process_the_next_free_event_bit():
    """evnt_multi's six waits: bits 1, 2, 4, 8, 16, 32 — each found by shifting past the bits the process's EVBs hold."""
    name = "evnt_multi for every event"
    answers = [evlib.run(evlib.at(name, IASYNC, which)).answer() for which in range(6)]
    assert answers == [1 << which for which in range(6)]


def test_iasync_queues_for_the_screen_manager_when_it_runs():
    arrival = evlib.at("evnt_multi by the screen manager for a rectangle", IASYNC)
    result = evlib.run(arrival)
    evb = evasync.free_evbs(before(arrival))[0]
    assert evb_of(result.final, evb)["PD"] == SCREEN_MANAGER and evasync.evlist(result.final, SCREEN_MANAGER)[0] == evb


@pytest.mark.parametrize("code", (0, 8, -1, 0x7FFF, 0x0105), ids=("0", "8", "-1", "$7fff", "$105: a low byte of 5"))
def test_iasync_with_a_code_of_no_wait_queues_the_evb_on_no_wait_list(code):
    """AN ARGUMENT-CLASS CASE (a code no caller hands), over the scheduler's own machine: `subq.w #1 / cmp.w #6 /
    bhi` — unsigned — sends every code outside 1..7 past the table. The EVB is the process's, with its bit, on no
    list: a wait nothing will ever end."""
    machine = evlib.desk_running()
    evb = evasync.free_evbs(make_image(machine))[0]
    result = evlib.returning(IASYNC, (code, 0x12345678), machine)
    block = evb_of(result.final, evb)
    assert result.answer() == 1 and (block["LINK"], block["PRED"], block["FLAG"], block["PARM"]) == (0, 0, 0, 0)
    assert evasync.evlist(result.final, SHELL) == [evb]


def test_iasync_names_the_running_process_by_the_long_rlr_holds():
    """AN ARGUMENT-CLASS CASE OVER A POKED FIELD (`rlr`, staged with a top byte: no ROM run stores one): the EVB's
    process is `rlr` as it stands — `move.l $c794,12(a5)` — not its bus address."""
    tagged = merge_pokes(evlib.desk_running(), aes.field_pokes("AES", RLR=SHELL | aes.BUS_TAG))
    evb = evasync.free_evbs(make_image(tagged))[0]
    result = evlib.returning(IASYNC, (evlib.KEYBOARD, 0), tagged)
    assert evb_of(result.final, evb)["PD"] == SHELL | aes.BUS_TAG


# ---- mwait -----------------------------------------------------------------------------------------------------------------
def test_mwait_answers_at_once_when_an_event_of_its_mask_has_come():
    arrival = evlib.at("evnt_keybd, a key queued", MWAIT)
    mask, = arrival.arguments
    result = evlib.run(arrival)
    assert result.answer() == process_word(before(arrival), aes.PD_EVFLG) == mask
    assert process_word(result.final, aes.PD_EVWAIT) == mask
    assert process_word(result.final, aes.PD_STAT) == aes.PD_STAT_READY


def test_mwait_leaves_its_process_waiting_and_enters_the_dispatcher_when_none_has():
    arrival = evlib.at("evnt_keybd, none", MWAIT)
    switched = evlib.run(arrival)
    assert evlib.BLOCKS in switched.stderr
    assert process_word(switched.image, aes.PD_STAT) == aes.PD_STAT_WAITING
    assert process_word(switched.image, aes.PD_EVWAIT) == arrival.arguments[0]


def test_mwait_for_six_events_none_of_them_come_blocks():
    arrival = evlib.at("evnt_multi for every event", MWAIT)
    assert arrival.arguments == (0x3F,) and evlib.BLOCKS in evlib.run(arrival).stderr


# ARGUMENT-CLASS CASES (a mask no caller hands), over the machine the ROM's own evnt_keybd has at its mwait with its
# key come (PD_EVFLG 1): what mwait tests is `evflg & mask`, a WORD.
@pytest.mark.parametrize("mask, comes_back", ((2, False), (3, True), (0, False), (-1, True), (-2, False)),
                         ids=("another event", "that one among others", "no event", "every event", "every other"))
def test_mwait_blocks_unless_an_event_of_the_mask_itself_has_come(mask, comes_back):
    arrival = evlib.at("evnt_keybd, a key queued", MWAIT)
    result = evlib.run(arrival, (mask,))
    assert isinstance(result, evlib.Switched) != comes_back
    assert process_word(evlib.image_after(result), aes.PD_EVWAIT) == mask & aes.WORD_MASK
    if comes_back:
        assert result.answer() == 1


@pytest.mark.parametrize("mask", (1, 2, 3), ids=("the first", "the second", "both"))
def test_mwait_answers_every_event_that_has_come_not_only_its_mask_s(mask):
    """AN ARGUMENT-CLASS MACHINE (`aes_evlib.two_events_come`)."""
    machine = evlib.two_events_come()
    assert process_word(make_image(machine), aes.PD_EVFLG) == 3
    assert evlib.returning(MWAIT, (mask,), machine).answer() == 3


NINTH_EVENT = 0x100                     # the first event bit above the mask's low byte


def test_mwait_tests_its_mask_as_a_word():
    """AN ARGUMENT-CLASS MACHINE (`aes_evlib.the_ninth_event_alone_come`): the one event come is bit 8, and a wait
    for it comes straight back — `and.w`: a mask tested by its low byte would find nothing come, and block."""
    machine = evlib.the_ninth_event_alone_come()
    assert process_word(make_image(machine), aes.PD_EVFLG) == NINTH_EVENT
    result = evlib.held(MWAIT, (NINTH_EVENT,), machine)
    assert not isinstance(result, evlib.Switched) and result.answer() == NINTH_EVENT


# ---- akbin -----------------------------------------------------------------------------------------------------------------
def key_taken(scenario):
    arrival = evlib.at(scenario, AKBIN)
    image = before(arrival)
    queue = case.long_in(image, aes.AES_GL_CDA) + FM["CDA_KEY_QUEUE"]
    front = case.word_in(image, queue + FM["CQUEUE_FRONT"])
    key = case.word_in(image, queue + FM["CQUEUE_KEYS"] + front * aes.WORD_BYTES)
    return image, evlib.run(arrival), arrival.arguments[0], key, queue


@pytest.mark.parametrize("scenario, queued", (("evnt_keybd, a key queued", 1), ("evnt_keybd, three keys queued", 3),
                                              ("evnt_keybd, the queue's front round the ring", 2)),
                         ids=("one", "three", "the front at the ring's last slot"))
def test_akbin_takes_a_queued_key_and_completes_the_wait(scenario, queued):
    image, result, evb, key, queue = key_taken(scenario)
    assert case.word_in(image, queue + FM["CQUEUE_COUNT"]) == queued
    assert case.word_in(result.final, queue + FM["CQUEUE_COUNT"]) == queued - 1
    block = evb_of(result.final, evb)
    assert block["RETURN"] == key and block["FLAG"] == evasync.COMPLETE and evasync.completed(result.final)[0] == evb
    assert cda_list(result.final, aes.CDA_KEYBOARD_WAIT) == []


def test_akbin_keeps_a_key_above_7fff_as_the_word_it_is():
    """Alt-= is the BIOS's $8300: the answer's high word stays clear (`swap / clr.w / swap`), where a sign-extended
    key would fill it."""
    _image, result, evb, key, _queue = key_taken("evnt_keybd, Alt-= queued")
    assert key == evlib.ALT_EQUALS and evb_of(result.final, evb)["RETURN"] == evlib.ALT_EQUALS


def test_akbin_with_no_key_queued_waits_on_the_cda_s_keyboard_list():
    arrival = evlib.at("evnt_keybd, none", AKBIN)
    result = evlib.run(arrival)
    evb, = arrival.arguments
    assert cda_list(result.final, aes.CDA_KEYBOARD_WAIT) == [evb] and evb not in evasync.completed(result.final)
    assert evb_of(result.final, evb)["RETURN"] == 0


@pytest.mark.parametrize("scenario", ("evnt_keybd, a key queued", "evnt_keybd, none"))
def test_akbin_takes_its_evb_through_the_bus(scenario):
    """AN ARGUMENT-CLASS CASE: the EVB's pointer with a top byte, which the links then carry as handed."""
    arrival = evlib.at(scenario, AKBIN)
    evlib.run(arrival, (arrival.arguments[0] | aes.BUS_TAG,))


# ---- adelay ----------------------------------------------------------------------------------------------------------------
def delayed(scenario):
    arrival = evlib.at(scenario, ADELAY)
    image = before(arrival)
    result = evlib.run(arrival)
    evb, ticks = arrival.arguments
    return image, result, evb, aes.signed(ticks, 32)


def delay_list(image):
    return [(evb, aes.signed(evb_of(image, evb)["PARM"], 32)) for evb in evasync.wait_list(image, EV["AES_DELAY_LIST"])]


def countdown(image):
    return aes.signed(case.long_in(image, aes.AES_TIMER_COUNTDOWN), 32)


def test_adelay_arms_the_countdown_and_starts_the_list_when_no_delay_is_pending():
    image, result, evb, ticks = delayed("evnt_timer")
    assert ticks == evlib.A_TIMER_MS // evlib.TICK_MS and delay_list(image) == [] and countdown(image) == 0
    assert delay_list(result.final) == [(evb, ticks)] and countdown(result.final) == ticks
    assert case.long_in(result.final, aes.AES_TIMER_ELAPSED) == 0
    block = evb_of(result.final, evb)
    assert block["FLAG"] == evasync.DELAY and block["PRED"] == EV["AES_DELAY_LIST"] - aes.EVB_LINK


def test_adelay_arming_the_countdown_clears_the_ticks_counted_so_far():
    """After a timer ran out (the tick glue's own count left at 5, no delay pending): a new delay starts the count
    again."""
    image, result, evb, ticks = delayed("evnt_timer after a timer ran out")
    assert case.long_in(image, aes.AES_TIMER_ELAPSED) == ticks != 0 and countdown(image) == 0
    assert case.long_in(result.final, aes.AES_TIMER_ELAPSED) == 0 and countdown(result.final) == ticks


def test_adelay_of_no_tick_waits_for_one():
    _image, result, evb, ticks = delayed("evnt_timer of no time")
    assert ticks == 0 and delay_list(result.final) == [(evb, 1)] and countdown(result.final) == 1


def test_adelay_of_a_negative_time_arms_a_negative_countdown():
    """A ROM FINDING: evnt_timer of a negative time queues a delay of negative ticks, and the countdown is armed with
    it — nothing is refused."""
    _image, result, evb, ticks = delayed("evnt_timer of a negative time")
    assert ticks < 0 and delay_list(result.final) == [(evb, ticks)] and countdown(result.final) == ticks


def test_adelay_before_a_longer_delay_shortens_the_countdown_and_leaves_that_one_the_difference():
    image, result, evb, ticks = delayed(f"{APPLICATION}: evnt_timer shorter than the delay pending")
    (pending, left), = delay_list(image)
    assert ticks < left == countdown(image)
    assert delay_list(result.final) == [(evb, ticks), (pending, left - ticks)] and countdown(result.final) == ticks
    assert evb_of(result.final, pending)["PRED"] == evb


def test_adelay_behind_a_shorter_delay_keeps_the_countdown_and_its_own_difference():
    image, result, evb, ticks = delayed(f"{APPLICATION}: evnt_timer longer than the delay pending")
    (pending, left), = delay_list(image)
    assert ticks > left
    assert delay_list(result.final) == [(pending, left), (evb, ticks - left)] and countdown(result.final) == left
    assert evb_of(result.final, evb)["PRED"] == pending and evb_of(result.final, evb)["LINK"] == 0


def test_adelay_as_long_as_the_delay_pending_goes_before_it():
    """`ble`: an equal delay stops the walk — the new one first, the old one behind it with no ticks of its own."""
    image, result, evb, ticks = delayed(f"{APPLICATION}: evnt_timer as long as the delay pending")
    (pending, left), = delay_list(image)
    assert ticks == left and delay_list(result.final) == [(evb, ticks), (pending, 0)]


def test_adelay_of_a_negative_time_goes_before_a_pending_delay_which_grows():
    """The compares are SIGNED: negative ticks are fewer than any delay's, the countdown takes them, and the delay
    pending is left its ticks PLUS their size."""
    image, result, evb, ticks = delayed(f"{APPLICATION}: evnt_timer of a negative time, a delay pending")
    (pending, left), = delay_list(image)
    assert ticks < 0 < left
    assert delay_list(result.final) == [(evb, ticks), (pending, left - ticks)] and countdown(result.final) == ticks


@pytest.mark.parametrize("scenario, pending, place, left", (
    (evlib.BEHIND_TWO_DELAYS, [10, 10], 2, [10, 10, 30]),
    (evlib.BETWEEN_TWO_DELAYS, [10, 20], 1, [10, 5, 15]),
    (evlib.BEHIND_THREE_DELAYS, [10, 10, 20], 3, [10, 10, 20, 60]),
), ids=("behind two", "between two", "behind three"))
def test_adelay_walks_past_every_shorter_delay_and_goes_in_where_the_walk_stops(scenario, pending, place, left):
    """ARGUMENT-CLASS MACHINES (`aes_evlib.delays_pending`): the walk is a LOOP — each delay passed takes its ticks
    off the new one's — and an insert between two rewrites both neighbours: the one before links to it, the one
    after keeps the difference and names it its predecessor."""
    image, result, evb, _ticks = delayed(scenario)
    assert [ticks for _evb, ticks in delay_list(image)] == pending
    after = delay_list(result.final)
    assert [ticks for _evb, ticks in after] == left and after[place][0] == evb
    assert evb_of(result.final, evb)["PRED"] == after[place - 1][0] and countdown(result.final) == countdown(image)
    if place + 1 < len(after):
        assert evb_of(result.final, after[place + 1][0])["PRED"] == evb


TICKS_ABOVE_A_WORD = 0x10000            # a long whose low word is 0


def test_adelay_of_65536_ticks_is_not_a_delay_of_no_tick():
    """AN ARGUMENT-CLASS CASE (evnt_timer of 21 minutes: an application's own to ask): `tst.l d7` — a long. Tested
    as a word it would be "no tick", and wait one."""
    arrival = evlib.at("evnt_timer", ADELAY)
    evb, _ticks = arrival.arguments
    result = evlib.run(arrival, (evb, TICKS_ABOVE_A_WORD))
    assert delay_list(result.final) == [(evb, TICKS_ABOVE_A_WORD)] and countdown(result.final) == TICKS_ABOVE_A_WORD


def test_adelay_behind_a_countdown_of_65536_ticks_leaves_it_running():
    """AN ARGUMENT-CLASS MACHINE (`aes_evlib.delays_pending`): `tst.l $9492` — a countdown whose low word is 0 is
    running all the same: a longer delay behind it neither re-arms it nor clears the ticks counted."""
    machine = evlib.delays_pending(TICKS_ABOVE_A_WORD)
    result = evlib.returning(IASYNC, (evlib.DELAY, 2 * TICKS_ABOVE_A_WORD), machine)
    assert countdown(result.final) == TICKS_ABOVE_A_WORD
    assert [ticks for _evb, ticks in delay_list(result.final)] == [TICKS_ABOVE_A_WORD, TICKS_ABOVE_A_WORD]


def test_adelay_takes_its_evb_through_the_bus():
    """AN ARGUMENT-CLASS CASE: the EVB's pointer with a top byte."""
    arrival = evlib.at("evnt_timer", ADELAY)
    evlib.run(arrival, (arrival.arguments[0] | aes.BUS_TAG, arrival.arguments[1]))


# ---- abutton ---------------------------------------------------------------------------------------------------------------
def buttoned(scenario):
    arrival = evlib.at(scenario, ABUTTON)
    image = before(arrival)
    return image, evlib.run(arrival), arrival.arguments[0], arrival.arguments[1]


@pytest.mark.parametrize("scenario, buttons", (
    ("evnt_button for the button up, which is up", 0),
    ("evnt_button for the button down, which is down", evlib.LEFT),
    ("evnt_button for either button not up, the left down", evlib.LEFT),
))
def test_abutton_completes_a_wait_the_buttons_already_satisfy_with_the_buttons_as_its_answer(scenario, buttons):
    image, result, evb, _wanted = buttoned(scenario)
    assert case.word_in(image, aes.AES_BUTTON) == buttons
    block = evb_of(result.final, evb)
    assert block["RETURN"] == aes.words_long(buttons) and block["FLAG"] == evasync.COMPLETE
    assert cda_list(result.final, aes.CDA_BUTTON_WAIT) == []
    assert case.word_in(result.final, evasync.BPEND) == case.word_in(image, evasync.BPEND)


@pytest.mark.parametrize("scenario, counted", (
    ("evnt_button for a press", 0),
    ("evnt_button for a double click", 1),
    ("evnt_button for the right button down", 0),
    ("evnt_button for either button not up, which they are", 0),
    ("evnt_button with a state wider than a byte", 0),
    ("evnt_multi for every event", 1),
))
def test_abutton_queues_a_wait_the_buttons_do_not_satisfy_and_counts_a_multi_click_one(scenario, counted):
    """The parameter kept whole in the EVB; a wait for more than one click — the LOW BYTE of the clicks word, so the
    "either button" bit above it does not count — one more among those pending."""
    image, result, evb, wanted = buttoned(scenario)
    block = evb_of(result.final, evb)
    assert block["PARM"] == wanted and block["RETURN"] == 0 and evb not in evasync.completed(result.final)
    assert cda_list(result.final, aes.CDA_BUTTON_WAIT)[0] == evb
    assert case.word_in(result.final, evasync.BPEND) == case.word_in(image, evasync.BPEND) + counted


def test_abutton_counts_a_wait_for_128_clicks_among_the_multi_click_ones():
    """AN ARGUMENT-CLASS CASE (a click count no application hands): the clicks' low BYTE is compared as the WORD it
    was masked to (`and.w #$ff / cmp.w #1 / ble`) — $80 is 128 clicks, more than one; as a signed byte it is not."""
    machine = evlib.desk_running()
    result = evlib.returning(IASYNC, (evlib.BUTTON, evlib.button_wait(0x80, evlib.LEFT, evlib.DOWN)), machine)
    assert case.word_in(result.final, evasync.BPEND) == case.word_in(make_image(machine), evasync.BPEND) + 1


def test_abutton_takes_its_evb_through_the_bus():
    """AN ARGUMENT-CLASS CASE: the EVB's pointer with a top byte."""
    for scenario in ("evnt_button for the button up, which is up", "evnt_button for a double click"):
        arrival = evlib.at(scenario, ABUTTON)
        evlib.run(arrival, (arrival.arguments[0] | aes.BUS_TAG, arrival.arguments[1]))


# ---- amouse ----------------------------------------------------------------------------------------------------------------
def moused(scenario, which=0):
    arrival = evlib.at(scenario, AMOUSE, which)
    image = before(arrival)
    evb, moblk = arrival.arguments
    return image, evlib.run(arrival), evb, struct.unpack_from(">5h", image, moblk)


@pytest.mark.parametrize("scenario", (
    "evnt_mouse to enter the rectangle the mouse is in",
    "evnt_mouse to leave a rectangle the mouse is not in",
    "evnt_mouse with a leave flag of 2",
    "evnt_mouse with a leave flag of $100, the mouse outside",
))
def test_amouse_completes_a_wait_the_mouse_already_satisfies(scenario):
    """...and a leave flag that is neither 0 nor 1 is never what `inside` answers — compared as a WORD — so such a
    wait is always satisfied."""
    _image, result, evb, _moblk = moused(scenario)
    block = evb_of(result.final, evb)
    assert block["FLAG"] == evasync.COMPLETE and (block["PARM"], block["RETURN"]) == (0, 0)
    assert cda_list(result.final, aes.CDA_MOUSE_WAIT) == []


@pytest.mark.parametrize("scenario, which, leaving", (
    ("evnt_mouse to leave the rectangle the mouse is in", 0, True),
    ("evnt_mouse to enter a rectangle the mouse is not in", 0, False),
    ("evnt_mouse to enter a rectangle above the screen", 0, False),
    ("evnt_mouse to enter a rectangle of negative height", 0, False),
    ("evnt_multi for every event", 0, True),
    ("evnt_multi for every event", 1, False),
))
def test_amouse_queues_a_wait_with_its_rectangle_packed_into_the_evb(scenario, which, leaving):
    """x and y in the parameter, w and h in the ANSWER — each pair `(first << 16) + second`, the second SIGN-EXTENDED:
    a negative y or h borrows one from the word above it."""
    image, result, evb, (leave, x, y, width, height) = moused(scenario, which)
    block = evb_of(result.final, evb)
    assert bool(leave) == leaving and block["FLAG"] == (evasync.LEAVING if leaving else 0)
    high = aes.HIGH_WORD_SHIFT
    assert block["PARM"] == ((x << high) + y) & aes.LONG_MASK and block["RETURN"] == ((width << high) + height) & aes.LONG_MASK
    assert cda_list(result.final, aes.CDA_MOUSE_WAIT)[0] == evb
    assert cda_list(result.final, aes.CDA_MOUSE_WAIT)[1:] == cda_list(image, aes.CDA_MOUSE_WAIT)


def test_amouse_s_second_wait_goes_before_the_first_on_the_mouse_list():
    image, result, evb, _moblk = moused("evnt_multi for every event", 1)
    first, = cda_list(image, aes.CDA_MOUSE_WAIT)
    assert cda_list(result.final, aes.CDA_MOUSE_WAIT) == [evb, first]


def test_amouse_clears_the_leave_flag_of_an_evb_that_carries_one():
    """AN ARGUMENT-CLASS CASE (an EVB no caller hands: iasync's is always fresh, its flag 0): at evnt_multi's second
    mouse wait — to ENTER a rectangle — amouse is handed the FIRST wait's EVB, which waits to LEAVE one. The flag is
    cleared in place (`andi.w #-9`), the rest of the word kept."""
    arrival = evlib.at("evnt_multi for every event", AMOUSE, 1)
    image = before(arrival)
    first, = cda_list(image, aes.CDA_MOUSE_WAIT)
    assert evb_of(image, first)["FLAG"] == evasync.LEAVING
    result = evlib.run(arrival, (first, arrival.arguments[1]))
    assert evb_of(result.final, first)["FLAG"] == 0


def test_amouse_reads_its_rectangle_from_its_copy_of_a_moblk_its_own_stores_land_on():
    """AN ARGUMENT-CLASS CASE (a pointer an application may hand — evnt_mouse's MOBLK is its own, anywhere — over the
    scheduler's machine): the MOBLK ten bytes into the EVB the wait is about to take. Its leave flag is the EVB's
    predecessor's low word (0), its x and y the EVB's process (PD0's high and low words), its w and h the EVB's
    PARAMETER (0, 0). The mouse is not inside a rectangle of no size, so the wait queues: the parameter is stored —
    OVER w and h — and the answer still keeps the w and h that were COPIED first."""
    machine = evlib.desk_running()
    evb = evasync.free_evbs(make_image(machine))[0]
    moblk_over_the_evb = evb + aes.EVB_PRED + aes.WORD_BYTES
    assert moblk_over_the_evb + aes.EV_MOBLK_RECT + aes.GRECT_W == evb + aes.EVB_PARM
    block = evb_of(evlib.returning(IASYNC, (evlib.MOUSE, moblk_over_the_evb), machine).final, evb)
    assert block["PARM"] == aes.signed(SHELL & aes.WORD_MASK) & aes.LONG_MASK != 0 and block["RETURN"] == 0


def test_amouse_takes_its_evb_and_its_moblk_through_the_bus():
    """AN ARGUMENT-CLASS CASE: both pointers with a top byte."""
    for scenario in ("evnt_mouse to enter the rectangle the mouse is in", "evnt_mouse to leave the rectangle the mouse is in"):
        arrival = evlib.at(scenario, AMOUSE)
        evlib.run(arrival, tuple(pointer | aes.BUS_TAG for pointer in arrival.arguments))


# ---- amutex ----------------------------------------------------------------------------------------------------------------
def test_amutex_queues_the_caller_on_a_lock_another_process_holds():
    arrival = evlib.at("wind_update(BEG), the lock another's", AMUTEX)
    image = before(arrival)
    result = evlib.run(arrival)
    evb, spb = arrival.arguments
    assert evlib.lock(image) == (1, SHELL, []) and evlib.lock(result.final) == (1, SHELL, [SCREEN_MANAGER])
    assert evb_of(result.final, evb)["PRED"] == spb + evlib.SPB_WAIT - aes.EVB_LINK


def test_amutex_queues_the_caller_on_a_lock_released_once_too_often():
    """The count -1, no owner (`test_aes_wm_update`'s finding): tak_flag refuses, and the caller waits on a lock
    nobody holds."""
    arrival = evlib.at("wind_update(BEG), the lock released once too often", AMUTEX)
    result = evlib.run(arrival)
    assert evlib.lock(result.final) == (-1, 0, [SHELL])


def test_amutex_puts_a_second_waiter_before_the_first():
    """A STAGED APPLICATION's arrival: its wind_update(BEG_UPDATE) while PD0 holds the lock with the screen manager
    queued — the last to wait is the list's first."""
    arrival = evlib.at(f"{APPLICATION}: a second process queues on the lock", AMUTEX)
    image = before(arrival)
    result = evlib.run(arrival)
    assert evlib.lock(image) == (1, SHELL, [SCREEN_MANAGER]) and evlib.lock(result.final) == (1, SHELL, [THIRD, SCREEN_MANAGER])


@pytest.mark.parametrize("machine, holds", ((evlib.desk_running, 1), (wm_update.locked, 2)), ids=("a free lock", "its own"))
def test_amutex_over_a_lock_tak_flag_takes_completes_the_wait(machine, holds):
    """AN ARGUMENT-CLASS CASE: amutex's callers come to it only after tak_flag refused (wind_update's own test,
    $feca82), so no ROM run reaches this arm. Over the scheduler's machine at iasync's own call of it — the EVB the
    ROM's iasync made for a mutex wait — with the lock free or the caller's own: taken, the wait completed."""
    made = evlib.watched(machine(), evlib.addrs.AES_ROM_IASYNC, frame=evlib.frame_of(IASYNC, (evlib.MUTEX, evlib.WIND_SPB))).arrivals
    arrival, = [each for each in made if each.name == AMUTEX]
    result = evlib.run(arrival)
    evb, _spb = arrival.arguments
    assert evlib.lock(result.final) == (holds, SHELL, []) and evb_of(result.final, evb)["FLAG"] == evasync.COMPLETE
    assert evasync.completed(result.final)[0] == evb


def test_amutex_takes_both_pointers_through_the_bus():
    """AN ARGUMENT-CLASS CASE: the EVB's and the semaphore's pointers with a top byte."""
    arrival = evlib.at("wind_update(BEG), the lock another's", AMUTEX)
    result = evlib.run(arrival, tuple(pointer | aes.BUS_TAG for pointer in arrival.arguments))
    assert evlib.lock(result.final)[2] == [SCREEN_MANAGER]


# ---- unsync: the leaf battery ------------------------------------------------------------------------------------------------
def released(scenario, **kwargs):
    arrival = evlib.at(scenario, UNSYNC)
    return before(arrival), evlib.run(arrival, **kwargs)


def test_unsync_of_a_lock_held_twice_leaves_it_held():
    image, result = released("wind_update(END), the lock held twice")
    assert evlib.lock(image) == (2, SHELL, []) and evlib.lock(result.final) == (1, SHELL, [])


def test_unsync_of_the_last_hold_with_nobody_waiting_leaves_no_owner_and_answers_0():
    image, result = released("wind_update(END), the lock held once")
    assert evlib.lock(image) == (1, SHELL, []) and evlib.lock(result.final) == (0, 0, [])
    assert result.answer() == EV_NOBODY == 0 and result.info["regs"]["d0"] == 0


EV_NOBODY = evlib.EVWAIT["UNSYNC_NOBODY_WAITS"]


def test_unsync_with_nothing_held_counts_below_zero_and_touches_nothing_else():
    image, result = released("wind_update(END), nothing held")
    assert evlib.lock(image) == (0, 0, []) and evlib.lock(result.final) == (-1, 0, [])


def test_unsync_hands_the_lock_to_the_process_waiting_for_it_and_yields():
    image, switched = released("wind_update(END), the screen manager waiting for the lock")
    waiting, = evasync.wait_list(image, evlib.WIND_SPB + evlib.SPB_WAIT)
    assert evlib.lock(image) == (1, SHELL, [SCREEN_MANAGER])
    assert evlib.YIELDS in switched.stderr and evlib.lock(switched.image) == (1, SCREEN_MANAGER, [])
    assert evasync.completed(switched.image)[0] == waiting and evb_of(switched.image, waiting)["FLAG"] == evasync.COMPLETE
    # ...which makes the screen manager ready (on the woken list), while the releaser still runs.
    assert aes.list_of(switched.image, aes.AES_DRL) == [SCREEN_MANAGER] and evasync.running(switched.image) == SHELL
    assert process_word(switched.image, aes.PD_STAT) == aes.PD_STAT_READY


def test_unsync_hands_the_lock_to_the_first_of_two_waiters_and_leaves_the_second_a_stale_predecessor():
    """A STAGED APPLICATION's machine, and A ROM FINDING: the list's head moves to the second wait, but that EVB's
    predecessor is not rewritten — it still names the EVB just taken off, which azombie has put on the completed
    list. (Harmless while unsync is the list's only taker: it never reads a predecessor.)"""
    image, switched = released(f"{APPLICATION}: wind_update(END), two processes waiting for the lock")
    first, second = evasync.wait_list(image, evlib.WIND_SPB + evlib.SPB_WAIT)
    assert evlib.lock(image) == (1, SHELL, [THIRD, SCREEN_MANAGER])
    assert evlib.YIELDS in switched.stderr and evlib.lock(switched.image) == (1, THIRD, [SCREEN_MANAGER])
    assert evb_of(switched.image, second)["PRED"] == first and evasync.completed(switched.image)[0] == first
    assert aes.list_of(switched.image, aes.AES_DRL) == [THIRD]


def test_unsync_hands_the_lock_on_by_the_wait_list_s_link_not_the_process_s_list():
    """AN ARGUMENT-CLASS MACHINE (`aes_evlib.two_waits_of_one_process_on_the_lock`), no staged application in it: the
    lock's new first wait is the taken one's LINK (the first wait queued) — its NEXT, on its process's own event
    list, is the wait of no kind taken between the two."""
    image, switched = released(evlib.TWO_WAITS_OF_ONE_PROCESS)
    second, first = evasync.wait_list(image, evlib.WIND_SPB + evlib.SPB_WAIT)
    assert evb_of(image, second)["NEXT"] not in (first, 0) and evlib.lock(image) == (1, SHELL, [SCREEN_MANAGER] * 2)
    assert evlib.YIELDS in switched.stderr and evasync.wait_list(switched.image, evlib.WIND_SPB + evlib.SPB_WAIT) == [first]
    assert evlib.lock(switched.image) == (1, SCREEN_MANAGER, [SCREEN_MANAGER]) and evasync.completed(switched.image)[0] == second


@pytest.mark.parametrize("scenario", ("wind_update(END), the lock held once", "wind_update(END), the lock held twice",
                                      "wind_update(END), the screen manager waiting for the lock"))
def test_unsync_takes_the_semaphore_through_the_bus(scenario):
    """AN ARGUMENT-CLASS CASE: the semaphore's pointer with a top byte."""
    arrival = evlib.at(scenario, UNSYNC)
    evlib.run(arrival, (arrival.arguments[0] | aes.BUS_TAG,))


# ARGUMENT-CLASS CASES OVER A STAGED SEMAPHORE: the ROM keeps ONE semaphore, the screen's, whose count no run takes
# past a few holds. unsync is handed a pointer all the same: an SPB laid in the band, over the scheduler's own machine,
# shows the count is a WORD — decremented and tested as one — and that the wait list is read from the SPB handed.
STAGED_SPB_AT = evlib.MESSAGE_AT


def staged_spb(count, owner=SHELL, waiting=0):
    return {STAGED_SPB_AT: struct.pack(">hII", count, owner, waiting)}


@pytest.mark.parametrize("count, left", ((0x0100, 0x00FF), (0x0101, 0x0100), (-0x8000, 0x7FFF), (2, 1)),
                         ids=("$100", "$101: a low byte of 0 is not 0", "-$8000 wraps", "2"))
def test_unsync_counts_a_word(count, left):
    result = evlib.returning(UNSYNC, (STAGED_SPB_AT,), merge_pokes(evlib.desk_running(), staged_spb(count)))
    assert evlib.lock(result.final, STAGED_SPB_AT) == (left, SHELL, [])


A_TAGGED_OWNER = 0x12345678             # an owner no ROM run stores: every PD's address has a high word of 0


def test_unsync_of_a_staged_semaphore_s_last_hold_clears_its_owner():
    """...as a LONG (`clr.l 2(a5)`): all four bytes of an owner whose high word is not 0."""
    result = evlib.returning(UNSYNC, (STAGED_SPB_AT,), merge_pokes(evlib.desk_running(), staged_spb(1, A_TAGGED_OWNER)))
    assert evlib.lock(result.final, STAGED_SPB_AT) == (0, 0, []) and result.answer() == 0


def test_unsync_hands_over_the_owner_as_the_long_the_wait_names():
    """AN ARGUMENT-CLASS CASE OVER A POKED FIELD (the waiting EVB's process with a top byte: no ROM run stores one):
    the lock's owner is that long as it stands — `move.l 12(a4),2(a5)`."""
    machine = wm_update.waited_on()
    waiting, = evasync.wait_list(make_image(machine), evlib.WIND_SPB + evlib.SPB_WAIT)
    tagged = {waiting + aes.EVB_PD: struct.pack(">I", SCREEN_MANAGER | aes.BUS_TAG)}
    switched = evlib.switched(UNSYNC, (evlib.WIND_SPB,), merge_pokes(machine, tagged), evlib.YIELDS)
    assert case.long_in(switched.image, evlib.WIND_SPB + evlib.SPB_OWNER) == SCREEN_MANAGER | aes.BUS_TAG


def test_unsync_hands_a_staged_semaphore_to_the_wait_its_own_list_names():
    """...the screen manager's EVB, as it waits on the screen's lock: taken off THE SEMAPHORE HANDED (its list's
    head rewritten there, the screen's own left alone)."""
    machine = wm_update.waited_on()
    waiting, = evasync.wait_list(make_image(machine), evlib.WIND_SPB + evlib.SPB_WAIT)
    switched = evlib.switched(UNSYNC, (STAGED_SPB_AT,), merge_pokes(machine, staged_spb(1, waiting=waiting)), evlib.YIELDS)
    assert evlib.lock(switched.image, STAGED_SPB_AT) == (1, SCREEN_MANAGER, [])
    assert case.long_in(switched.image, evlib.WIND_SPB + evlib.SPB_WAIT) == waiting


# ---- the registry: Tier 3's rows ---------------------------------------------------------------------------------------
# Every RETURNING arrival of every scenario (the staged application's aside) was priced as a row would be (`make
# bench`'s instrument, 196 arrivals); each routine's WORST is registered first, then the rows that show its other
# shapes. Measured and left out, none any routine's worst: the rest, each within its routine's range — iasync
# 0.40..0.72, mwait 0.61 every one, akbin 0.40..0.49, adelay 0.51..0.59, abutton 0.41..0.46, amouse 0.42..0.71, amutex 0.47,
# unsync 0.45..0.57. A call that reaches the dispatcher is no row (a row's run returns): Tier 1, at dsptch.
SERVES_A_WRITER = evlib.SERVES_A_WRITER
EVERY_EVENT = "evnt_multi for every event"
ROWS = (
    ("a read of a full pipe", "appl_read of a full pipe", IASYNC, 0),
    ("a read that serves the process waiting to write", SERVES_A_WRITER, IASYNC, 0),
    ("a delay, the process's sixth wait", EVERY_EVENT, IASYNC, 5),
    ("a mouse wait behind another, the fourth wait", EVERY_EVENT, IASYNC, 3),
    ("a key wait, none queued", "evnt_keybd, none", IASYNC, 0),
    ("a button wait satisfied at once", "evnt_button for the button up, which is up", IASYNC, 0),
    ("its event come already", "evnt_keybd, a key queued", MWAIT, 0),
    ("a key queued", "evnt_keybd, a key queued", AKBIN, 0),
    ("the queue's front at the ring's last slot", "evnt_keybd, the queue's front round the ring", AKBIN, 0),
    ("no key queued", "evnt_keybd, none", AKBIN, 0),
    ("behind three delays pending", evlib.BEHIND_THREE_DELAYS, ADELAY, 0),
    ("no tick: one", "evnt_timer of no time", ADELAY, 0),
    ("the only delay", "evnt_timer", ADELAY, 0),
    ("the buttons as wanted", "evnt_button for the button up, which is up", ABUTTON, 0),
    ("a double click waited for", "evnt_button for a double click", ABUTTON, 0),
    ("a press waited for", "evnt_button for a press", ABUTTON, 0),
    ("the screen manager's wait to enter a rectangle", "evnt_multi by the screen manager for a rectangle", AMOUSE, 0),
    ("a second mouse wait, to enter", EVERY_EVENT, AMOUSE, 1),
    ("the mouse already where the wait asks", "evnt_mouse to enter the rectangle the mouse is in", AMOUSE, 0),
    ("a lock another process holds", "wind_update(BEG), the lock another's", AMUTEX, 0),
    ("the last hold, nobody waiting", "wind_update(END), the lock held once", UNSYNC, 0),
    ("a lock held twice", "wind_update(END), the lock held twice", UNSYNC, 0),
    ("nothing held", "wind_update(END), nothing held", UNSYNC, 0),
)
# ...and each routine through its call word: verified, unpriced.
THROUGH_LINE_F = {routine: next(row[1:] for row in ROWS if row[2] == routine) for routine in ROUTINES}


evasync.register_rows(evlib.at, evlib.register, ROWS, THROUGH_LINE_F.values())
