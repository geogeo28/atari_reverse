"""THE INPUT LAYER's posts (`src/aes/evinput.c`): geminput's posts, the owners and the click counter.

    nq(key, queue)            the key at the queue's rear (dropped when 8 are queued), the rear round the ring
    downorup(buttons, parm)   sense != ((mask & (state ^ buttons)) == 0): the three low bytes of a button wait's
                              parameter, and the high byte its sense
    post_keybd(pd, key)       to pd's first keyboard wait (evremove, the key its answer), else nq into its CDA's queue
    post_button(pd, b, n)     each of pd's button waits downorup(b) satisfies: answer := b << 16, evremove(min(n, the
                              clicks it asked for), UNSIGNED)
    post_mouse(pd, x, y)      each of pd's mouse waits inorout satisfies: evremove(0)
    inorout(evb, x, y)        inside(x, y, the wait's rectangle) != the wait's LEAVE flag
    mowner(x, y)              1 in the control rectangle, -1 on the menu bar or a window, 0 on the desktop
    set_mown(mp, kp)          gl_mowner = gl_cowner = mp; post_mouse and post_button(1 click) to it; gl_kowner = kp
    ct_chgown(pd, rect)       set_ctrl(rect); set_mown(pd, pd); D0 0
    b_click(buttons)          the button interrupt's click counter
    b_delay(ticks)            ...counted down; at 0 forkq(bchange, clicks) (and the change since, if any)

EVERY MACHINE IS THE ROM'S OWN, at the moment the ROM makes the call (`aes_evinput`: the ARRIVALS of the VDI's mouse
interrupt, the tick, the dispatcher's loop and a running process's calls, watched) — and every frame the one its
caller pushed, but for the cases SAID to hand one no caller does (an ARGUMENT-CLASS case: a pointer with a top byte,
a count or a parameter no caller makes, handed directly over a ROM-made machine) and the ONE said to stage a field
(b_click with no multi-click wait pending: `$c84e` is never 0 while the desktop runs).

post_button AND ct_chgown ARE DOOR ENTRIES (`aes/evdoor.h`): their sections below are their LEAF BATTERIES — every
arm, every list shape the scheduler makes, and the 68000's integer semantics each on a case — and their rows are
registered at the entry itself.

THE C RUNS FIRST IN A CHILD — a fork of the worker at every run (`aes_evinput.run_over`).
"""
import struct

import pytest

import harness
from harness import BASE_IMAGE, addrs, make_image

import aes
import aes_evasync as evasync
import aes_event
import aes_evinput as evinput
import case
from aes_evinput import (B_CLICK, B_DELAY, CT_CHGOWN, DOWNORUP, INOROUT, MOWNER, NQ, POST_BUTTON, POST_KEYBD,
                         POST_MOUSE, SCREEN_MANAGER, SET_MOWN, SHELL)
from case import merge_pokes

pytestmark = pytest.mark.collected_with(by=aes_event.scenario_of_a_case)
ROUTINES = (NQ, DOWNORUP, POST_KEYBD, POST_BUTTON, POST_MOUSE, INOROUT, MOWNER, SET_MOWN, CT_CHGOWN, B_CLICK, B_DELAY)
EVI, FM = evinput.EVI, evinput.FM
WU = aes.header_constants("wmupdate.h")
GL_MOWNER, GL_KOWNER, GL_COWNER = WU["AES_GL_MOWNER"], WU["AES_GL_KOWNER"], EVI["AES_GL_COWNER"]
BDESIRED, BTRUE, BCLICK = EVI["AES_GL_BDESIRED"], EVI["AES_GL_BTRUE"], EVI["AES_GL_BCLICK"]
CLICK_TICKS, DCLICK, BPEND = aes.AES_GL_CLICK_TICKS, aes.AES_GL_DCLICK, evasync.BPEND
SNAPSHOT_DCLICK = case.word_in(BASE_IMAGE, DCLICK)
KEY_QUEUE, REAR, COUNT, ENTRIES = FM["CDA_KEY_QUEUE"], EVI["CQUEUE_REAR"], FM["CQUEUE_COUNT"], FM["CQUEUE_ENTRIES"]
IN_CONTROL, MANAGER_S, DESKTOP = EVI["MOWNER_IN_CONTROL"], EVI["MOWNER_SCREEN_MANAGER"], EVI["MOWNER_DESKTOP"]
LEFT, RIGHT = 1, 2                      # the AES's buttons: a bit each
RETURN_KEY_CODE = evinput.RETURN_KEY_CODE
BAR_SCENARIO = evasync.THE_BAR_WAKES_THE_MANAGER
KEY, PRESS, CLICK = "a key wakes the desk", "a press wakes the desk", "a click wakes the desk"
DOUBLE = "a double click wakes the desk"
HAND_BACK = "the screen manager hands the mouse back"
TWO_RECTS = "two rectangles, one left"
TYPED_AHEAD = "a key typed ahead of a wait for a press"
TEN_KEYS = "ten keys nobody reads"


run = evinput.run


before = aes_event.before


def completed_with(result, evb):
    """`(is completed, answer)` of the EVB after a run."""
    fields = evasync.evb_of(result.final, evb)
    return evb in evasync.completed(result.final), fields["RETURN"]


waits, fork_queue, button_change = evinput.waits, evinput.fork_queue, evinput.button_change


# ---- every arrival of every scenario ------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", evinput.SCENARIOS)
def test_a_scenario_s_arrivals_are_the_ones_it_declares(name):
    assert len(evinput.scenario(name).arrivals) == len(evinput.SCENARIOS[name].arrivals)


@pytest.mark.parametrize("name", evinput.SCENARIOS)
def test_an_arrival_s_machine_keeps_nothing_of_the_run_s_own(name):
    """No poke of any arrival's lies in the stack band or over the packet an interrupt was handed."""
    kept = [(arrival.name, at) for arrival in evinput.scenario(name).arrivals for at, data in arrival.machine.items()
            if any(address in evinput.NOT_THE_MACHINE_S for address in (at, at + len(data) - 1))]
    assert not kept


@pytest.mark.parametrize("arrival", evinput.cases(*ROUTINES), ids=evinput.case_id)
def test_every_arrival(arrival):
    run(evinput.arrival(*arrival))


def test_every_routine_arrives_in_some_scenario():
    arrived = {routine for declared in evinput.SCENARIOS.values() for routine in declared.arrivals}
    assert arrived == set(evinput.ROUTINES)


# Each routine through its caller's call word (b_click has none: the button glue's `jsr` is its one caller).
THROUGH_LINE_F = {NQ: (TYPED_AHEAD, 0), DOWNORUP: (PRESS, 0), POST_KEYBD: (KEY, 0), POST_BUTTON: (PRESS, 0),
                  POST_MOUSE: (HAND_BACK, 1), INOROUT: (HAND_BACK, 1), MOWNER: (PRESS, 0), SET_MOWN: (HAND_BACK, 0),
                  CT_CHGOWN: (HAND_BACK, 0), B_DELAY: (PRESS, 10)}


@pytest.mark.parametrize("routine", THROUGH_LINE_F, ids=evinput.short)
def test_each_routine_through_its_call_word(routine):
    scenario, which = THROUGH_LINE_F[routine]
    run(evinput.at(scenario, routine, which), through_line_f=True)


def test_b_click_has_no_call_word():
    assert not aes.line_f_call_sites(B_CLICK)


@pytest.mark.parametrize("watched, unwatched", (
    (evinput.PRESS, aes_event.press), (evinput.RELEASE, aes_event.release), (evinput.DOUBLE_CLICK, aes_event.double_click),
    (evinput.BAR, aes_event.move_to(*aes_event.MENU_BAR_POINT)), (evinput.sequence(*[evinput.tick] * 3), aes_event.ticks(3))),
    ids=("a press", "a release", "a double click", "a move", "ticks"))
def test_a_watched_interrupt_leaves_what_its_unwatched_twin_leaves(watched, unwatched):
    """The interrupts of this battery are `aes_event`'s own, with a watch on them: the same machine, byte for byte,
    outside the stack band."""
    ours = make_image(watched({}).machine)
    theirs = make_image(merge_pokes({}, unwatched(make_image({}))))
    differ = [at for at in range(addrs.ST_RAM_BYTES) if ours[at] != theirs[at] and at not in evinput.NOT_THE_MACHINE_S]
    assert not differ


def test_a_step_s_image_is_what_its_pokes_make_under_whatever_base_image_is_in_force():
    """A step hands its run's own buffer on as the next step's image (`aes_evinput.image_of`) — which is
    `make_image` of the machine it answered ONLY over the snapshot: the two bands a machine keeps nothing of are put
    back from the snapshot. THE RED for the buffer handed on under another base (`harness.set_base_image`: the sweep
    over what no capture reproduces): the next step then ran over the snapshot's band where `make_image` lays the
    other base's — one machine, two images, by whether the step before happened to be the last one made."""
    made = evinput.tick({})
    assert evinput.seen_in(made.machine) is evinput._LAST_MADE[1], "the premise: over the snapshot the buffer is handed on"
    assert bytes(evinput.image_of(made.machine)) == bytes(make_image(made.machine))
    another = bytearray(BASE_IMAGE)
    another[case.STACK_BAND.start] ^= 0xFF
    previous = harness.set_base_image(bytes(another))
    try:
        made = evinput.tick({})
        handed, built = bytes(evinput.image_of(made.machine)), bytes(make_image(made.machine))
    finally:
        harness.set_base_image(previous)
    assert handed == built and built[case.STACK_BAND.start] == another[case.STACK_BAND.start]


# ---- nq --------------------------------------------------------------------------------------------------------------------
def queue_of(image, pd=SHELL):
    """`(the keys in the ring's eight slots, rear, count)` of `pd`'s key queue."""
    queue = case.long_in(image, pd + aes.PD_CDA) + KEY_QUEUE
    return ([case.word_in(image, queue + slot * aes.WORD_BYTES) for slot in range(ENTRIES)],
            case.word_in(image, queue + REAR), case.word_in(image, queue + COUNT))


def test_nq_puts_the_key_at_the_rear_and_counts_it():
    arrival = evinput.at(TYPED_AHEAD, NQ)
    _keys, rear, count = queue_of(before(arrival))
    result = run(arrival)
    keys, rear_after, count_after = queue_of(result.final)
    assert (rear, count) == (0, 0) and keys[0] == RETURN_KEY_CODE and (rear_after, count_after) == (1, 1)


def test_nq_s_rear_goes_round_the_ring():
    """The eighth key of eight nobody read: stored in the last slot, the rear back at 0, the queue full."""
    arrival = evinput.at(TEN_KEYS, NQ, ENTRIES - 1)
    assert queue_of(before(arrival))[1:] == (ENTRIES - 1, ENTRIES - 1)
    result = run(arrival)
    keys, rear, count = queue_of(result.final)
    assert keys[ENTRIES - 1] == RETURN_KEY_CODE and (rear, count) == (0, ENTRIES)


def a_full_queue():
    """The desk's key queue FULL: the machine at the last key poll of ten keys nobody read (chkkbd then polls no
    more: `test_aes_evfork.py`)."""
    arrival = evinput.at(TEN_KEYS, evinput.CHKKBD, ENTRIES + 1)
    assert queue_of(before(arrival))[2] == ENTRIES
    return arrival


def test_nq_drops_a_key_for_a_full_queue():
    """AN ARGUMENT-CLASS CASE (nq called directly over the ROM-made full queue: chkkbd never polls a key for a full
    one, so no caller hands it one): nothing stored."""
    arrival = a_full_queue()
    queue = case.long_in(before(arrival), SHELL + aes.PD_CDA) + KEY_QUEUE
    result = evinput.run_over(NQ, (0x1234, queue), arrival.machine)
    assert aes.stored_nothing(result) and queue_of(result.final) == queue_of(before(arrival))


def staged_queue(keys, front, rear, count):
    """A key queue NO CDA HOLDS, staged where an argument can name it (`evinput.ARGUMENT_AT`, eight slots in): its ring,
    front, rear and count."""
    return {evinput.ARGUMENT_AT + 8 * aes.WORD_BYTES: struct.pack(f">{ENTRIES}H3h", *keys, front, rear, count)}


@pytest.mark.parametrize("rear, count, slot, rear_after, count_after", (
    (3, -1, 3, 4, 0), (-1, 2, -1, 0, 3), (-4, 0, -4, -3, 1), (7, 7, 7, 0, 8), (8, 0, 8, 9, 1)),
    ids=("a negative count is not full", "a negative rear stores below the ring", "...and counts up toward it",
         "the last slot wraps", "a rear at 8 is past the wrap"))
def test_nq_reads_the_rear_and_the_count_as_signed_words(rear, count, slot, rear_after, count_after):
    """ARGUMENT-CLASS CASES (a queue staged as nq's argument, holding a rear and a count no CDA's queue holds): the
    count is compared SIGNED (`bge`) and the rear extended SIGNED into the slot's address (`movea.w`), and the wrap is
    `== 8` exactly."""
    queue = evinput.ARGUMENT_AT + 8 * aes.WORD_BYTES
    machine = merge_pokes(aes_event.machine(), {evinput.ARGUMENT_AT: bytes(evinput.ARGUMENT_BYTES)},
                          staged_queue([0x1111 * (slot_ + 1) for slot_ in range(ENTRIES)], 0, rear, count))
    result = evinput.run_over(NQ, (0x7E57, queue), machine)
    assert result.word(queue + slot * aes.WORD_BYTES) == 0x7E57
    assert (aes.signed(result.word(queue + REAR)), aes.signed(result.word(queue + COUNT))) == (rear_after, count_after)


def test_nq_s_queue_is_put_on_the_bus():
    arrival = evinput.at(TYPED_AHEAD, NQ)
    key, queue = arrival.arguments
    result = run(arrival, (key, queue | aes.BUS_TAG))
    assert queue_of(result.final)[1:] == (1, 1)


# ---- downorup ----------------------------------------------------------------------------------------------------------------
def parameter(sense, clicks, mask, state):
    return (sense << aes.BUTTON_PARM_SENSE_SHIFT | clicks << aes.BUTTON_PARM_CLICKS_SHIFT
            | mask << aes.BUTTON_PARM_MASK_SHIFT | state)


# ARGUMENT-CLASS CASES, every one: downorup reads its two arguments and nothing else, so each is handed directly (over
# the desk running). The parameters a ROM caller hands are among them (the snapshot's two button waits: $00020101 the
# desk's, $0001ff01 the screen manager's).
THE_DESK_S_WAIT = parameter(0, 2, LEFT, LEFT)                       # a double click of the left button
THE_SCREEN_MANAGER_S_WAIT = parameter(0, 1, aes.BYTE_MASK, LEFT)    # one click, every button looked at: the left one down
DOWNORUP_CASES = {
    "the desk's wait, the button down": (LEFT, THE_DESK_S_WAIT, 1),
    "the desk's wait, the button up": (0, THE_DESK_S_WAIT, 0),
    "the screen manager's wait, the right button": (RIGHT, THE_SCREEN_MANAGER_S_WAIT, 0),
    "a wait for the button up, it is up": (0, parameter(0, 1, LEFT, 0), 1),
    "a wait for the button up, it is down": (LEFT, parameter(0, 1, LEFT, 0), 0),
    "the other button is not looked at": (LEFT | RIGHT, parameter(0, 1, RIGHT, 0), 0),
    "nor a bit above the mask's byte": (0x0100, parameter(0, 1, 0xFF, 0), 1),
    "both buttons wanted, one down": (LEFT, parameter(0, 1, 3, 3), 0),
    "both buttons wanted, both down": (3, parameter(0, 1, 3, 3), 1),
    "the sense set: NOT in the state": (LEFT, parameter(1, 1, 3, 0), 1),
    "the sense set, and in the state": (0, parameter(1, 1, 3, 0), 0),
    "a sense of 2 is satisfied in the state": (0, parameter(2, 1, LEFT, 0), 1),
    "...and out of it": (LEFT, parameter(2, 1, LEFT, 0), 1),
    "a sense with its top bit set is a byte still": (LEFT, parameter(0x80, 1, LEFT, 0), 1),
    "a sense of $ff": (0, parameter(0xFF, 1, LEFT, 0), 1),
    "an empty mask is always in its state": (3, parameter(0, 1, 0, 0), 1),
    "the clicks are not looked at": (LEFT, parameter(0, 0xFF, LEFT, LEFT), 1),
    "a button above the two a mouse has, under a mask that names it": (0x04, parameter(0, 1, 0xFF, 0), 0),
    "a state bit above them too": (0, parameter(0, 1, 0xFF, 0x40), 0),
}


@pytest.mark.parametrize("buttons, parm, answer", DOWNORUP_CASES.values(), ids=DOWNORUP_CASES)
def test_downorup(buttons, parm, answer):
    result = evinput.run_over(DOWNORUP, (buttons, parm), aes_event.machine())
    assert result.answer() == answer and aes.stored_nothing(result)


def test_downorup_as_ev_multi_and_post_button_call_it():
    """The ROM's own calls: ev_multi's test of a wait before it queues it (the button up: not satisfied), and
    post_button's of the same wait with the press (satisfied)."""
    scenario = "a double click to a wait for one click"
    assert [run(evinput.at(scenario, DOWNORUP, which)).answer() for which in range(3)] == [0, 0, 1]


# ---- post_keybd ----------------------------------------------------------------------------------------------------------------
def test_post_keybd_completes_the_wait_of_a_process_waiting_for_a_key():
    arrival = evinput.at(KEY, POST_KEYBD)
    pd, key = arrival.arguments
    waiting, = waits(before(arrival), pd, aes.CDA_KEYBOARD_WAIT)
    result = run(arrival)
    assert pd == SHELL and completed_with(result, waiting) == (True, RETURN_KEY_CODE)
    assert not waits(result.final, pd, aes.CDA_KEYBOARD_WAIT) and queue_of(result.final)[2] == 0
    assert aes.list_of(result.final, aes.AES_DRL) == [SHELL], "the desk is woken"


def test_post_keybd_queues_the_key_of_a_process_not_waiting_for_one():
    arrival = evinput.at(TYPED_AHEAD, POST_KEYBD)
    assert not waits(before(arrival), SHELL, aes.CDA_KEYBOARD_WAIT)
    result = run(arrival)
    assert queue_of(result.final)[0][0] == RETURN_KEY_CODE and queue_of(result.final)[2] == 1
    assert not evasync.completed(result.final)


@pytest.mark.parametrize("scenario", (KEY, TYPED_AHEAD), ids=("a wait", "no wait"))
def test_post_keybd_s_process_is_put_on_the_bus(scenario):
    arrival = evinput.at(scenario, POST_KEYBD)
    pd, key = arrival.arguments
    run(arrival, (pd | aes.BUS_TAG, key))


# ---- post_button: the entry's LEAF BATTERY ---------------------------------------------------------------------------------------
# THE LIST SHAPES THE SCHEDULER MAKES: a process has ONE evnt call pending, and evnt_multi queues one button wait —
# so a CDA's button wait list holds NO wait or ONE, in every ROM-made machine (two need two calls of one process).
# Both are here; the walk's own order (the link read BEFORE the wait is posted) is held by the one-wait case with
# the completed list not empty — evremove rewrites the wait's link with the completed list's head, which a walk
# reading the link afterwards follows.
ONE_CLICK_WAIT = "a double click to a wait for one click"
EITHER = "a wait for either button, the right one pressed"


def posted(scenario, which=0, arguments=None):
    """post_button's `which`-th arrival of `scenario` run: `(the result, the process, its button waits before)`."""
    arrival = evinput.at(scenario, POST_BUTTON, which)
    pd = arrival.arguments[0]
    return run(arrival, arguments), pd, waits(before(arrival), pd, aes.CDA_BUTTON_WAIT)


def test_post_button_completes_the_wait_the_press_satisfies():
    """The desk's double-click wait, the left button down after ONE click: completed with the state in the answer's
    high word and the one click in its low — fewer than it asked for."""
    result, pd, (waiting,) = posted(PRESS)
    assert pd == SHELL and completed_with(result, waiting) == (True, aes.words_long(LEFT, 1))
    assert not waits(result.final, pd, aes.CDA_BUTTON_WAIT) and aes.list_of(result.final, aes.AES_DRL) == [SHELL]


def test_post_button_answers_the_clicks_that_came_when_they_are_what_was_asked():
    result, _pd, (waiting,) = posted(DOUBLE)
    assert completed_with(result, waiting) == (True, aes.words_long(LEFT, 2))


def test_post_button_answers_no_more_clicks_than_the_wait_asked_for():
    """Two clicks to a wait for one: answered one."""
    result, _pd, (waiting,) = posted(ONE_CLICK_WAIT)
    assert aes.high_word(evasync.evb_of(before(evinput.at(ONE_CLICK_WAIT, POST_BUTTON)), waiting)["PARM"]) == 1
    assert completed_with(result, waiting) == (True, aes.words_long(LEFT, 1))


def test_post_button_leaves_a_wait_the_buttons_do_not_satisfy():
    """The click's RELEASE posted to the desk — whose wait the press before it completed already: no wait is left —
    and the right button to the desk's wait for the left: left queued, nothing stored but the Line-F mask word."""
    result, pd, queued = posted(CLICK, 1)
    assert not queued and aes.stored_nothing(result)
    result, pd, (waiting,) = posted("a right press wakes nobody")
    assert waits(result.final, pd, aes.CDA_BUTTON_WAIT) == [waiting] and not evasync.completed(result.final)
    assert aes.stored_nothing(result)


def test_post_button_reads_the_sense_and_the_clicks_as_bytes_of_one_word():
    """A wait for EITHER button (clicks $0101: the sense byte set, one click): the right button down satisfies it,
    and the clicks it asked for are the low byte — one."""
    result, _pd, (waiting,) = posted(EITHER)
    assert completed_with(result, waiting) == (True, aes.words_long(RIGHT, 1))


def test_post_button_to_the_screen_manager():
    """A press on the menu bar's right goes to the screen manager's own wait (any button, one click)."""
    result, pd, (waiting,) = posted("a press on the bar's right")
    assert pd == SCREEN_MANAGER and completed_with(result, waiting) == (True, aes.words_long(LEFT, 1))
    assert aes.list_of(result.final, aes.AES_DRL) == [SCREEN_MANAGER]


def test_post_button_with_a_wait_completed_before_it():
    """The completed list NOT empty when the wait is posted (the mouse wait of the same idle, completed first):
    evremove puts the wait at the completed list's head, its link the EVB completed before — a walk that read the
    link AFTER posting would post that one too."""
    arrival = evinput.at(HAND_BACK, POST_BUTTON, 1)
    assert len(evasync.completed(before(arrival))) == 2, "the premise: the two rectangles' waits completed just before"
    result = run(arrival)
    assert len(evasync.completed(result.final)) == 3


def test_post_button_compares_the_clicks_unsigned():
    """AN ARGUMENT-CLASS CASE (clicks no caller hands: $ffff): `bls` — above the two the wait asked for, so the two
    are answered; a signed compare would answer -1."""
    arrival = evinput.at(PRESS, POST_BUTTON)
    pd, button, _clicks = arrival.arguments
    waiting, = waits(before(arrival), pd, aes.CDA_BUTTON_WAIT)
    result = run(arrival, (pd, button, -1))
    assert completed_with(result, waiting) == (True, aes.words_long(LEFT, 2))


def test_post_button_reads_the_clicks_asked_for_as_a_byte():
    """AN ARGUMENT-CLASS CASE (two clicks, handed directly, to the ROM-made wait for EITHER button — clicks word
    $0101): the clicks asked for are the LOW BYTE, one — not the word, 257."""
    arrival = evinput.at(EITHER, POST_BUTTON)
    pd, button, _clicks = arrival.arguments
    waiting, = waits(before(arrival), pd, aes.CDA_BUTTON_WAIT)
    assert completed_with(run(arrival, (pd, button, 2)), waiting) == (True, aes.words_long(RIGHT, 1))


def test_post_button_walks_a_list_of_two():
    """AN ARGUMENT-CLASS CASE — the one way a button wait list of TWO is had (a process has one evnt call pending, so
    no machine holds one): a "process" staged as the argument, whose CDA pointer names the desk's own CDA FOUR BYTES
    DOWN — where the button wait list is read, the desk's two MOUSE waits are. Both are ROM-made EVBs; read as button
    waits their parameters (a rectangle's x and y) have an empty mask, which any buttons satisfy. Both are posted:
    the second is reached by the link read BEFORE the first was taken off its list."""
    arrival = evinput.at(HAND_BACK, POST_MOUSE, 1)
    image = before(arrival)
    cda = case.long_in(image, SHELL + aes.PD_CDA)
    both = evasync.wait_list(image, cda + aes.CDA_MOUSE_WAIT)
    named = cda + aes.CDA_MOUSE_WAIT - aes.CDA_BUTTON_WAIT
    machine = merge_pokes(arrival.machine, {evinput.ARGUMENT_AT + aes.PD_CDA: struct.pack(">I", named)})
    result = evinput.run_over(POST_BUTTON, (evinput.ARGUMENT_AT, LEFT, 1), machine)
    assert len(both) == 2 and all(evb in evasync.completed(result.final) for evb in both)
    assert all(evasync.evb_of(result.final, evb)["RETURN"] == aes.words_long(LEFT, 1) for evb in both)


def test_post_button_walks_past_a_wait_the_buttons_do_not_satisfy():
    """AN ARGUMENT-CLASS CASE — the list of two again (the same device), its FIRST wait NOT satisfied and its second
    satisfied: two ROM-made mouse waits whose y, read as a button wait's mask and state, is $0100 (mask 1, state 0:
    not the left button down) and $0101 (mask 1, state 1). The first stays; the walk goes on to the second."""
    not_satisfied, satisfied = 0x0100, 0x0101
    frame, pokes = evasync.ev_multi_frame(evasync.MU_M1 | evasync.MU_M2, first=evasync.moblk(evasync.ENTER, 10, satisfied, 5, 5),
                                        second=evasync.moblk(evasync.ENTER, 10, not_satisfied, 5, 5))
    parked = aes_event.parked(addrs.AES_ROM_EV_MULTI, frame, merge_pokes(aes_event.machine(), pokes))
    image = make_image(parked)
    cda = case.long_in(image, SHELL + aes.PD_CDA)
    first, second = evasync.wait_list(image, cda + aes.CDA_MOUSE_WAIT)
    assert [evasync.evb_of(image, evb)["PARM"] & aes.WORD_MASK for evb in (first, second)] == [not_satisfied, satisfied]
    named = cda + aes.CDA_MOUSE_WAIT - aes.CDA_BUTTON_WAIT
    machine = merge_pokes(parked, {evinput.ARGUMENT_AT + aes.PD_CDA: struct.pack(">I", named)})
    result = evinput.run_over(POST_BUTTON, (evinput.ARGUMENT_AT, LEFT, 1), machine)
    assert evasync.completed(result.final) == [second] and evasync.wait_list(result.final, cda + aes.CDA_MOUSE_WAIT) == [first]


def test_post_button_compares_the_clicks_handed_as_a_word():
    """AN ARGUMENT-CLASS CASE (256 clicks, which no caller hands) to the desk's wait for two: the WORD is above two,
    so two are answered — its low byte alone is 0."""
    arrival = evinput.at(PRESS, POST_BUTTON)
    pd, button, _clicks = arrival.arguments
    waiting, = waits(before(arrival), pd, aes.CDA_BUTTON_WAIT)
    assert completed_with(run(arrival, (pd, button, 0x100)), waiting) == (True, aes.words_long(LEFT, 2))


def test_post_button_reads_all_eight_bits_of_the_clicks_asked_for():
    """A ROM-MADE wait for SEVENTEEN clicks (evnt_multi's own parameter) and twenty handed (ARGUMENT-CLASS: no caller
    counts so many): seventeen answered — every bit of the byte."""
    asked, handed = 17, 20
    frame, pokes = evasync.ev_multi_frame(evasync.MU_BUTTON, button=evasync.button_wait(asked))
    parked = aes_event.parked(addrs.AES_ROM_EV_MULTI, frame, merge_pokes(aes_event.machine(), pokes))
    waiting, = waits(make_image(parked), SHELL, aes.CDA_BUTTON_WAIT)
    result = evinput.run_over(POST_BUTTON, (SHELL, LEFT, handed), parked)
    assert evasync.evb_of(result.final, waiting)["RETURN"] == aes.words_long(LEFT, asked)


def test_post_button_answers_no_clicks_at_all():
    """AN ARGUMENT-CLASS CASE (0 clicks): the least of the two is answered, 0."""
    arrival = evinput.at(PRESS, POST_BUTTON)
    pd, button, _clicks = arrival.arguments
    waiting, = waits(before(arrival), pd, aes.CDA_BUTTON_WAIT)
    assert completed_with(run(arrival, (pd, button, 0)), waiting) == (True, aes.words_long(LEFT))


def test_post_button_stores_the_state_as_an_unsigned_word():
    """AN ARGUMENT-CLASS CASE (a button word with its top bit set, which downorup's byte mask does not look at):
    `clr.l d0 / move.w` — the answer's high word is the word, nothing extended over the clicks."""
    arrival = evinput.at(PRESS, POST_BUTTON)
    pd, _button, clicks = arrival.arguments
    waiting, = waits(before(arrival), pd, aes.CDA_BUTTON_WAIT)
    assert completed_with(run(arrival, (pd, 0x8001 - 0x10000, clicks)), waiting) == (True, aes.words_long(0x8001, 1))


def test_post_button_s_process_is_put_on_the_bus():
    arrival = evinput.at(PRESS, POST_BUTTON)
    pd, button, clicks = arrival.arguments
    waiting, = waits(before(arrival), pd, aes.CDA_BUTTON_WAIT)
    assert completed_with(run(arrival, (pd | aes.BUS_TAG, button, clicks)), waiting)[0]


# ---- inorout, post_mouse ------------------------------------------------------------------------------------------------------
# A wait list is LIFO (evinsert puts a wait at its head): of evnt_multi's two rectangles the SECOND is the list's first.
ROUND_FIRST, ROUND_LAST = "two rectangles, the other left", TWO_RECTS      # where the rectangle round the mouse lies


def test_inorout_s_four_answers():
    """Entered and waited to be entered; left and waited to be left; still inside one waited to be left; still
    outside one waited to be entered."""
    entered = run(evinput.at(BAR_SCENARIO, INOROUT))
    left = run(evinput.at(ROUND_LAST, INOROUT, 1))
    still_inside = run(evinput.at(ROUND_LAST, INOROUT, 0))
    still_outside = run(evinput.at("a rectangle not entered", INOROUT))
    assert [each.answer() for each in (entered, left, still_inside, still_outside)] == [1, 1, 0, 0]
    assert all(aes.stored_nothing(each) for each in (entered, left, still_inside, still_outside))


@pytest.mark.parametrize("x, y, answer", ((149, 95, 1), (150, 90, 0), (169, 109, 0), (170, 95, 1), (160, 110, 1),
                                          (-1, 95, 1), (160, -32768, 1)),
                         ids=("left of it", "its corner", "its last pixel", "right of it", "below it", "x negative",
                              "y the least word"))
def test_inorout_s_point_against_the_rectangle_s_edges(x, y, answer):
    """ARGUMENT-CLASS CASES (points handed directly; the wait is the ROM's own: LEAVE the rectangle round the mouse)."""
    arrival = evinput.at(ROUND_LAST, INOROUT, 1)
    evb = arrival.arguments[0]
    assert evasync.evb_of(before(arrival), evb)["PARM"] == aes.words_long(evasync.ROUND_THE_MOUSE[0], evasync.ROUND_THE_MOUSE[1])
    assert run(arrival, (evb, x, y)).answer() == answer


def test_inorout_reads_the_one_flag_bit():
    """AN ARGUMENT-CLASS CASE (an EVB no caller hands: a mouse wait already COMPLETED, its flag word 2 — not the LEAVE
    bit, `btst #3`): still a wait to ENTER its rectangle."""
    arrival = evinput.at(HAND_BACK, POST_BUTTON, 1)      # after post_mouse completed the desk's two rectangle waits
    image = before(arrival)
    entered = next(evb for evb in evasync.completed(image)
                   if evasync.evb_of(image, evb)["PARM"] == aes.words_long(evinput.ROUND_THE_BAR_POINT[0], evinput.ROUND_THE_BAR_POINT[1]))
    assert evasync.evb_of(image, entered)["FLAG"] == evasync.COMPLETE
    inside_ = evinput.run_over(INOROUT, (entered, *aes_event.MENU_BAR_POINT), arrival.machine)
    outside = evinput.run_over(INOROUT, (entered, 300, 150), arrival.machine)
    assert (inside_.answer(), outside.answer()) == (1, 0)


def test_inorout_s_wait_is_put_on_the_bus():
    arrival = evinput.at(ROUND_LAST, INOROUT, 1)
    evb, x, y = arrival.arguments
    assert run(arrival, (evb | aes.BUS_TAG, x, y)).answer() == 1


def test_post_mouse_completes_both_waits_of_two():
    """The desk's two rectangle waits, both satisfied when the mouse is handed back to it: each completed, answered
    0, the list emptied — the second reached by the link read before the first was taken off."""
    arrival = evinput.at(HAND_BACK, POST_MOUSE, 1)
    pd = arrival.arguments[0]
    both = waits(before(arrival), pd, aes.CDA_MOUSE_WAIT)
    result = run(arrival)
    assert len(both) == 2 and all(evb in evasync.completed(result.final) for evb in both)
    assert not waits(result.final, pd, aes.CDA_MOUSE_WAIT)


def test_post_mouse_completes_the_first_of_two_and_leaves_the_second():
    arrival = evinput.at(ROUND_FIRST, POST_MOUSE, 0)
    pd = arrival.arguments[0]
    first, second = waits(before(arrival), pd, aes.CDA_MOUSE_WAIT)
    result = run(arrival)
    assert evasync.completed(result.final) == [first] and waits(result.final, pd, aes.CDA_MOUSE_WAIT) == [second]


def test_post_mouse_completes_the_last_of_two_and_leaves_the_first():
    arrival = evinput.at(ROUND_LAST, POST_MOUSE, 0)
    pd = arrival.arguments[0]
    first, second = waits(before(arrival), pd, aes.CDA_MOUSE_WAIT)
    result = run(arrival)
    assert evasync.completed(result.final) == [second] and waits(result.final, pd, aes.CDA_MOUSE_WAIT) == [first]


def test_post_mouse_leaves_the_one_wait_left_unsatisfied():
    arrival = evinput.at(TWO_RECTS, POST_MOUSE, 1)
    pd = arrival.arguments[0]
    result = run(arrival)
    assert len(waits(result.final, pd, aes.CDA_MOUSE_WAIT)) == 1 and aes.stored_nothing(result)


def test_post_mouse_to_a_process_with_no_mouse_wait():
    arrival = evinput.at("the screen taken", POST_MOUSE)
    assert not waits(before(arrival), arrival.arguments[0], aes.CDA_MOUSE_WAIT) and aes.stored_nothing(run(arrival))


def test_post_mouse_s_process_is_put_on_the_bus():
    arrival = evinput.at(HAND_BACK, POST_MOUSE, 1)
    pd, x, y = arrival.arguments
    result = run(arrival, (pd | aes.BUS_TAG, x, y))
    assert not waits(result.final, pd, aes.CDA_MOUSE_WAIT)


# ---- mowner ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("scenario, answer", (
    (PRESS, IN_CONTROL), ("a press on the bar's right", MANAGER_S), ("a press on a window's title", MANAGER_S),
    ("a press on the desktop beside a window", DESKTOP), ("a press inside the control rectangle", IN_CONTROL),
    ("a press on the bar with the screen owned", IN_CONTROL)),
    ids=("the control rectangle", "the menu bar", "a window", "the desktop", "the screen owned",
         "the menu bar inside the control rectangle: the rectangle first"))
def test_mowner(scenario, answer):
    result = run(evinput.at(scenario, MOWNER))
    assert result.answer() == answer and aes.stored_nothing(result)


# ---- set_mown, and ct_chgown: the entry's LEAF BATTERY ---------------------------------------------------------------------------
# ct_chgown has no arm of its own: set_ctrl, then set_mown, whose two posts are the posts' own batteries above. What
# its battery holds is the composition at the entry — the rectangle copied, the three owners stored, the new owner's
# waits posted (none; two mouse waits and a button wait) — and its answer.
def owners(image):
    return tuple(case.long_in(image, at) for at in (GL_MOWNER, GL_COWNER, GL_KOWNER))


def ctrl_rect(image):
    return tuple(aes.signed(case.word_in(image, WU["AES_CTRL_RECT"] + 2 * index)) for index in range(4))


def rect_at(image, at):
    return tuple(aes.signed(case.word_in(image, (at & aes.OS_BUS_ADDR_MASK) + 2 * index)) for index in range(4))


@pytest.mark.parametrize("routine", (SET_MOWN, CT_CHGOWN), ids=evinput.short)
def test_the_mouse_handed_back_posts_the_new_owner_s_waits(routine):
    """The screen manager, the left button down on the bar, hands the mouse and the keyboard back to the desk
    (w_setactive's ct_chgown): the desk's two rectangle waits and its wait for a press all completed, the desk woken."""
    arrival = evinput.at(HAND_BACK, routine)
    image = before(arrival)
    assert owners(image)[0] == SCREEN_MANAGER and evasync.running(image) == SCREEN_MANAGER
    pending = waits(image, SHELL, aes.CDA_MOUSE_WAIT) + waits(image, SHELL, aes.CDA_BUTTON_WAIT)
    result = run(arrival)
    assert len(pending) == 3 and all(evb in evasync.completed(result.final) for evb in pending)
    assert owners(result.final) == (SHELL, SHELL, SHELL) and aes.list_of(result.final, aes.AES_DRL) == [SHELL]


def test_ct_chgown_copies_the_rectangle_and_answers_0():
    arrival = evinput.at(HAND_BACK, CT_CHGOWN)
    _owner, rect = arrival.arguments
    result = run(arrival)
    assert ctrl_rect(result.final) == rect_at(before(arrival), rect)
    assert result.answer() == 0 and result.long_answer() == 0, "the end of post_button's walk: a null link"


def test_ct_chgown_to_the_running_process_with_no_wait():
    """wind_update(BEG_MCTRL): the desk takes the whole screen — nothing to post, the owners its own."""
    arrival = evinput.at("the screen taken", CT_CHGOWN)
    result = run(arrival)
    assert owners(result.final) == (SHELL, SHELL, SHELL) and ctrl_rect(result.final) == (0, 0, 320, 200)
    assert result.answer() == 0 and not evasync.completed(result.final)


def test_ct_chgown_s_rectangle_is_put_on_the_bus_and_its_owner_stored_whole():
    """AN ARGUMENT-CLASS CASE (pointers with a top byte): the rectangle is read through the bus; the owner is STORED
    as the 32 bits handed (`move.l d0,$9afa`) and dereferenced on the bus for the posts."""
    arrival = evinput.at(HAND_BACK, CT_CHGOWN)
    owner, rect = arrival.arguments
    result = run(arrival, (owner | aes.BUS_TAG, rect | aes.BUS_TAG))
    assert owners(result.final) == (owner | aes.BUS_TAG,) * 3 and ctrl_rect(result.final) == rect_at(before(arrival), rect)
    assert len(evasync.completed(result.final)) == 3


def test_ct_chgown_copies_the_rectangle_before_it_stores_the_owners():
    """AN ARGUMENT-CLASS CASE (a "rectangle" no caller hands: the eight bytes at gl_mowner itself): set_ctrl copies
    them BEFORE set_mown stores the new owner over the first four — the control rectangle is the OLD owner's bytes."""
    arrival = evinput.at(HAND_BACK, CT_CHGOWN)
    old = bytes(before(arrival)[GL_MOWNER:GL_MOWNER + 8])
    result = run(arrival, (SHELL, GL_MOWNER))
    assert bytes(result.final[WU["AES_CTRL_RECT"]:WU["AES_CTRL_RECT"] + 8]) == old
    assert int.from_bytes(old[:4], "big") == SCREEN_MANAGER != SHELL == result.long(GL_MOWNER)


def test_set_mown_posts_one_click_to_a_wait_for_two():
    """The mouse handed back to the DESK'S OWN wait (the snapshot's: a double click), the button down: completed with
    ONE click — set_mown's post says one, whatever the wait asked for."""
    arrival = evinput.at("the screen manager hands the mouse back to the desk's own wait", SET_MOWN)
    waiting, = waits(before(arrival), SHELL, aes.CDA_BUTTON_WAIT)
    assert aes.high_word(evasync.evb_of(before(arrival), waiting)["PARM"]) == 2
    assert completed_with(run(arrival), waiting) == (True, aes.words_long(LEFT, 1))


def test_set_mown_posts_the_buttons_as_they_are_not_a_press():
    """The desk waits for a press; the mouse goes onto the bar and the screen manager hands it back with NO button
    down: set_mown posts the buttons as they ARE — the desk's wait for a press is not satisfied, and stays."""
    arrival = evinput.at("the screen manager hands the mouse back with no button down", SET_MOWN)
    image = before(arrival)
    waiting, = waits(image, SHELL, aes.CDA_BUTTON_WAIT)
    assert case.word_in(image, aes.header_constants("gsx.h")["AES_BUTTON"]) == 0, "the premise: no button down"
    result = run(arrival)
    assert waits(result.final, SHELL, aes.CDA_BUTTON_WAIT) == [waiting] and waiting not in evasync.completed(result.final)


def test_set_mown_stores_the_keyboard_s_owner_apart():
    """AN ARGUMENT-CLASS CASE (two different owners, which ct_chgown never hands): the mouse's and the control
    owner's are the first, the keyboard's the second."""
    arrival = evinput.at(HAND_BACK, SET_MOWN)
    result = run(arrival, (SHELL, SCREEN_MANAGER))
    assert owners(result.final) == (SHELL, SHELL, SCREEN_MANAGER)


# ---- b_click ----------------------------------------------------------------------------------------------------------------
def click_state(image):
    return {"ticks": case.word_in(image, CLICK_TICKS), "clicks": case.word_in(image, BCLICK),
            "opened on": case.word_in(image, BTRUE), "last seen": case.word_in(image, BDESIRED)}


def test_b_click_opens_a_count_on_a_press_while_a_multi_click_wait_is_pending():
    arrival = evinput.at(PRESS, B_CLICK)
    assert case.word_in(before(arrival), BPEND) == 1 and click_state(before(arrival))["ticks"] == 0
    result = run(arrival)
    assert click_state(result.final) == {"ticks": SNAPSHOT_DCLICK, "clicks": 1, "opened on": LEFT, "last seen": LEFT}
    assert not fork_queue(result.final)


def test_b_click_only_notes_a_release_inside_the_count():
    arrival = evinput.at(DOUBLE, B_CLICK, 1)
    result = run(arrival)
    assert click_state(result.final) == {"ticks": SNAPSHOT_DCLICK, "clicks": 1, "opened on": LEFT, "last seen": 0}


def test_b_click_counts_the_button_pressed_again_and_lengthens_the_count():
    arrival = evinput.at(DOUBLE, B_CLICK, 2)
    result = run(arrival)
    assert click_state(result.final) == {"ticks": SNAPSHOT_DCLICK + EVI["CLICK_EXTENSION_TICKS"], "clicks": 2,
                                         "opened on": LEFT, "last seen": LEFT}


def test_b_click_only_notes_another_button_inside_the_count():
    arrival = evinput.at("the right button pressed inside the left one's count", B_CLICK, 1)
    result = run(arrival)
    assert click_state(result.final) == {"ticks": SNAPSHOT_DCLICK, "clicks": 1, "opened on": LEFT,
                                         "last seen": LEFT | RIGHT}


def test_b_click_queues_a_release_at_once():
    """No count open, the button released: a button change of one click, queued for forker."""
    arrival = evinput.at("the button released", B_CLICK)
    result = run(arrival)
    assert fork_queue(result.final) == [button_change(0, 1)] and click_state(result.final)["last seen"] == 0
    assert click_state(result.final)["ticks"] == 0


def test_b_click_with_the_buttons_as_it_last_saw_them_does_nothing():
    """AN ARGUMENT-CLASS CASE (the VDI's mouse interrupt calls the button routine only for a CHANGE, so no caller
    hands b_click the state it holds): over the machine a double click leaves with its count still open — the button
    down, the one the count was opened on — the same button again is NOT a third click."""
    machine = evinput.at(DOUBLE, B_DELAY, 0).machine
    assert click_state(make_image(machine)) == {"ticks": SNAPSHOT_DCLICK + EVI["CLICK_EXTENSION_TICKS"], "clicks": 2,
                                                "opened on": LEFT, "last seen": LEFT}
    assert aes.stored_nothing(evinput.run_over(B_CLICK, (LEFT,), machine))


def test_b_click_queues_a_press_at_once_when_no_multi_click_wait_is_pending():
    """THE ONE CASE OVER A STAGED FIELD, labelled: `$c84e` (gl_bpend) is never 0 while the desktop runs (the desk
    queues a double-click wait in its first evnt_multi and the count never goes below 1: `aes/evasync.h`), so the
    arm "a press, nothing pending" is reached by no ROM-made machine of this snapshot — sh_main alone clears the
    word. Staged 0 here: the press is queued at once, no count opened."""
    arrival = evinput.at(PRESS, B_CLICK)
    staged = merge_pokes(arrival.machine, {BPEND: bytes(aes.WORD_BYTES)})
    result = evinput.run_over(B_CLICK, arrival.arguments, staged)
    assert fork_queue(result.final) == [button_change(LEFT, 1)] and click_state(result.final)["ticks"] == 0


def test_a_cancelled_multi_click_wait_leaves_b_click_opening_counts():
    """THE FINDING, CONFIRMED ON b_click's SIDE: `$c84e` after a multi-click wait was cancelled (evnt_multi for every
    event, the timer came: `aes_evasync`) is 2 with NO button wait pending at all — and b_click, which reads the
    word as "is any multi-click wait pending", still opens a click count on a press: the press is delayed by the
    whole double-click time for a process that asked for no double click."""
    back = evasync.watched(evasync.taken(
        aes_event.parked(addrs.AES_ROM_EV_MULTI, *_every_event()), evasync.ticks(evasync.A_TIMER_TICKS)),
        addrs.AES_ROM_DISP_LOOP, {addrs.AES_ROM_EV_MULTI_RETURN}).machine
    image = make_image(back)
    assert case.word_in(image, BPEND) == 2 and not waits(image, SHELL, aes.CDA_BUTTON_WAIT)
    pressed = evinput.mouse_packet(evinput.LEFT_DOWN)(back)
    arrival, = pressed.arrivals
    result = run(arrival)
    assert arrival.name == B_CLICK and click_state(result.final)["ticks"] == SNAPSHOT_DCLICK
    assert not fork_queue(result.final)


def _every_event():
    frame, pokes = evasync.ev_multi_frame(
        evasync.MU_KEYBD | evasync.MU_BUTTON | evasync.MU_M1 | evasync.MU_M2 | evasync.MU_MESAG | evasync.MU_TIMER,
        first=evasync.moblk(evasync.LEAVE, *evasync.ROUND_THE_MOUSE), second=evasync.moblk(evasync.ENTER, *evasync.ELSEWHERE),
        timer=evasync.A_TIMER_MS, button=evasync.button_wait(evasync.DOUBLE))
    return frame, merge_pokes(aes_event.machine(), pokes)


# ---- b_delay ----------------------------------------------------------------------------------------------------------------
def test_b_delay_with_no_count_open_does_nothing():
    arrival = evinput.at("a timer runs out", B_DELAY)
    assert click_state(before(arrival))["ticks"] == 0 and aes.stored_nothing(run(arrival))


def test_b_delay_counts_a_tick_off():
    arrival = evinput.at(PRESS, B_DELAY)
    result = run(arrival)
    assert click_state(result.final)["ticks"] == SNAPSHOT_DCLICK - 1 and not fork_queue(result.final)


def test_b_delay_queues_the_press_when_the_count_runs_out():
    arrival = evinput.at(PRESS, B_DELAY, SNAPSHOT_DCLICK - 1)
    result = run(arrival)
    assert click_state(result.final)["ticks"] == 0 and fork_queue(result.final) == [button_change(LEFT, 1)]


def test_b_delay_queues_the_clicks_counted():
    arrival = evinput.at(DOUBLE, B_DELAY, SNAPSHOT_DCLICK + EVI["CLICK_EXTENSION_TICKS"] - 1)
    assert fork_queue(run(arrival).final) == [button_change(LEFT, 2)]


def test_b_delay_queues_the_change_since_the_count_was_opened_after_it():
    """A click — the button up again when the count runs out: the press with its one click, then the release."""
    arrival = evinput.at(CLICK, B_DELAY, SNAPSHOT_DCLICK - 1)
    assert fork_queue(run(arrival).final) == [button_change(LEFT, 1), button_change(0, 1)]


def test_b_delay_queues_the_release_after_a_double_click_as_one_click():
    """A double click and its release, all inside the count: the press with its TWO clicks, then the release — one."""
    arrival = evinput.at("a double click and its release", B_DELAY, SNAPSHOT_DCLICK + EVI["CLICK_EXTENSION_TICKS"] - 1)
    assert fork_queue(run(arrival).final) == [button_change(LEFT, 2), button_change(0, 1)]


def test_b_delay_of_the_whole_count_at_once():
    """mchange's call, the mouse moved inside the count: all its ticks, the press queued behind the move being run."""
    arrival = evinput.at("a move right ends a click's count", B_DELAY)
    assert arrival.arguments == (SNAPSHOT_DCLICK,)
    result = run(arrival)
    assert click_state(result.final)["ticks"] == 0 and fork_queue(result.final)[-1] == button_change(LEFT, 1)


@pytest.mark.parametrize("ticks, left", ((5, 6), (12, 0xFFFF), (-1, 12)), ids=("some", "past the end", "minus one"))
def test_b_delay_counts_as_a_word_and_queues_only_at_exactly_0(ticks, left):
    """ARGUMENT-CLASS CASES (ticks no caller hands — the tick's glue hands 1, mchange the count itself): the count is
    a word, stepped past 0 it wraps and nothing is queued."""
    arrival = evinput.at(PRESS, B_DELAY)
    result = run(arrival, (ticks,))
    assert click_state(result.final)["ticks"] == left and not fork_queue(result.final)


# ---- Tier 3 ------------------------------------------------------------------------------------------------------------------
# Every arrival of every scenario (a staged application's aside) is a candidate; each routine's WORST measured
# (`make bench`'s instrument over all of them) is registered first, then the rows that show its other shapes.
ROWS = (                                # each routine's WORST first (measured ratios beside the routine's first row)
    ("the eighth key: the rear round the ring", TEN_KEYS, NQ, ENTRIES - 1),                      # 0.55; 0.53
    ("a key into an empty queue", TYPED_AHEAD, NQ, 0),
    ("a wait the press satisfies", PRESS, DOWNORUP, 0),                                          # 0.33; 0.31..0.32
    ("a wait with its sense set", EITHER, DOWNORUP, 0),
    ("a wait the right button does not satisfy", "a right press wakes nobody", DOWNORUP, 0),
    ("a key to a waiting process", KEY, POST_KEYBD, 0),                                          # 0.47; 0.37..0.38
    ("a key to a process not waiting", TYPED_AHEAD, POST_KEYBD, 0),
    ("no wait", CLICK, POST_BUTTON, 1),                                                          # 0.67; 0.37..0.47
    ("one wait, satisfied: fewer clicks than asked", PRESS, POST_BUTTON, 0),
    ("one wait, satisfied: more clicks than asked", ONE_CLICK_WAIT, POST_BUTTON, 0),
    ("one wait, the completed list holding two", HAND_BACK, POST_BUTTON, 1),
    ("one wait, not satisfied", "a right press wakes nobody", POST_BUTTON, 0),
    ("no wait", "the screen taken", POST_MOUSE, 0),                                              # 0.64; 0.54..0.59
    ("one wait left, not satisfied", ROUND_LAST, POST_MOUSE, 1),
    ("two waits, the first satisfied", ROUND_FIRST, POST_MOUSE, 0),
    ("two waits, the last satisfied", ROUND_LAST, POST_MOUSE, 0),
    ("two waits, both satisfied", HAND_BACK, POST_MOUSE, 1),
    ("a rectangle entered", BAR_SCENARIO, INOROUT, 0),                                           # 0.55; 0.51..0.55
    ("a rectangle left", ROUND_LAST, INOROUT, 1),
    ("a rectangle not left", ROUND_LAST, INOROUT, 0),
    ("a rectangle not entered", "a rectangle not entered", INOROUT, 0),
    ("a window's title", "a press on a window's title", MOWNER, 0),                              # 0.64; 0.57..0.62
    ("the desktop beside a window", "a press on the desktop beside a window", MOWNER, 0),
    ("the menu bar", "a press on the bar's right", MOWNER, 0),
    ("the control rectangle", PRESS, MOWNER, 0),
    ("to the running process, no wait", "the screen taken", SET_MOWN, 0),                        # 0.64; 0.51
    ("the mouse handed back: three waits posted", HAND_BACK, SET_MOWN, 0),
    ("the mouse handed back: three waits posted", HAND_BACK, CT_CHGOWN, 0),                      # 0.50; 0.50
    ("the screen taken: no wait", "the screen taken", CT_CHGOWN, 0),
    ("a release queued at once", "the button released", B_CLICK, 0),                             # 0.75; 0.59..0.72
    ("a press opens a count", PRESS, B_CLICK, 0),
    ("the button again inside the count", DOUBLE, B_CLICK, 2),
    ("a release inside the count, noted", CLICK, B_CLICK, 1),
    ("a count run out", PRESS, B_DELAY, SNAPSHOT_DCLICK - 1),                                    # 0.86; 0.59..0.80
    ("a count run out, the buttons changed since: two queued", CLICK, B_DELAY, SNAPSHOT_DCLICK - 1),
    ("a tick counted off", PRESS, B_DELAY, 0),
    ("no count open", "a timer runs out", B_DELAY, 0),
)


evasync.register_rows(evinput.at, evinput.register, ROWS,
                      [(scenario, routine, which) for routine, (scenario, which) in THROUGH_LINE_F.items()])
