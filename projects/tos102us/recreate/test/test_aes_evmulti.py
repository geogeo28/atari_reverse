"""evnt_multi (`src/aes/evmulti.c`): the twin of the event door's last entry, and its LEAF BATTERY.

    ev_multi(flags, mo1, mo2, timer, button, message, rets)                                            ($fe6998)
      chkkbd(); forker();
      what = 0
      KEYBD:  a key in rlr's own queue                -> rets[4] = dq(); what |= 1
      BUTTON: rlr owns the mouse, and
                more than one change posted and downorup(the buttons BEFORE the last change, button)
                                                      -> $c792 = those; rets[5] = their clicks; what |= 2
                else downorup(the buttons, button)    -> $c792 = the buttons; rets[5] = the clicks; what |= 2
      M1, M2: ev_mchk(mo)                             -> what |= 4, 8
      TIMER:  timer == 0                              -> what |= $20
      MESAG:  rlr's pipe holds anything (signed)      -> ev_mesag(message); what |= $10
      if (!what) { one iasync per event asked: 5, 7(button), 6(mo1), 6(mo2), 1(&{rlr's pid, 16, message}),
                   3(timer / the tick's ms); came = mwait(all) | acancel(all) }
      ev_rets(rets); if (!(flags & BUTTON)) rets[2] = the buttons
      if (!what) { each wait that came, in the order key, buttons, mo1, mo2, message, timer: apret —
                   rets[4] = the key's; rets[5] = the buttons', rets[2] = $c792 }
      if (what & $10) $97fe = 0
      return what

EVERY MACHINE IS THE ROM'S OWN (`aes_evmulti`), every frame an application's evnt_multi — but for the ARGUMENT-CLASS
cases, each labelled where it stands (a pointer with a top byte, the answers laid over a word the routine reads, a
field poked to the edge of its width).

A CALL THAT BLOCKS is held to the ROM's memory AT DSPTCH — and, WOKEN, as ONE RETURNING RUN: a row that switches
(`aes_evmulti.WAKES`), the twin blocked and woken through the host's scheduler at Tier 1 and through OUR dispatcher
on the bench, each wake priced on its own cycles.

A ROM FINDING the cases pin, from ev_multi's side: THE BUTTONS IT ANSWERS ARE STALE unless a button event came. ev_rets
runs BEFORE the aprets and hands out $c792, the high word of the last answer apret took IN AN EARLIER CALL — a
woken mouse wait's rectangle WIDTH. ev_multi stores the real buttons over it only when no button event was asked for.
On the snapshot's own machine the screen manager's evnt_multi, asking for the buttons and its rectangle, answers
buttons = 216 with no button down.
"""
import collections
import functools
import re
import struct
from pathlib import Path

import pytest

from harness import BASE_IMAGE, addrs, bench_tier3, make_image
from recreate_kit import rom_bench

import aes
import aes_evasync as evasync
import aes_event
import aes_evlib as evlib
import aes_evmulti as evm
import aes_pdpipe
import aes_switch
import aes_switching as switching
import case
import opcodes
from aes_evmulti import BUTTON, BUTTONS, CLICKS, EV_MULTI, EVERY_EVENT, KEY, KEYBD, M1, M2, MESAG, STALE, TIMER, Y, call
from case import merge_pokes

FM = aes.header_constants("fmlib.h")
EV = evasync.EV
SHELL, SCREEN_MANAGER = evm.SHELL, evm.SCREEN_MANAGER
READ_PAST_THE_PIPE = "a read of more bytes than the pipe holds"     # `pdpipe.c`'s refusal, as its own battery reads it
ANSWERS_AT, MESSAGE_AT = evm.ANSWERS_AT, evm.MESSAGE_AT
BUTTON_STATE, BPEND = evasync.BUTTON_STATE, evasync.BPEND
SENT_MARK = evm.SENT_MARK
MOWNER = aes.header_constants("wmupdate.h")["AES_GL_MOWNER"]
WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES
NOTHING_ANSWERED = [STALE] * evm.ANSWER_WORDS


def before(made):
    """The image a `Call` is run over."""
    return make_image(evm.machine_of(made))


# THE TESTS OF ONE CASE ARE COLLECTED BACK TO BACK (`conftest.py`'s marker: a parametrized test by its case's name, a
# test that reads one case by `of_the_case`), and what a case's run left is kept for the few tests that follow it —
# no longer: a kept result holds the images its run left, sixteen megabytes each (every case kept for the process's
# life was two gigabytes a worker). In pytest's own order the tests of one case are a function apart, and under
# xdist a steal hands them to another worker, which runs the case again.
pytestmark = pytest.mark.collected_with(by=lambda params: params.get("name"))
of_the_case = pytest.mark.collected_with
CASES_KEPT = 3                          # a test reads two cases at most; a group's neighbour may be a third


@functools.lru_cache(maxsize=CASES_KEPT)
def ran(table, name):
    """The case of a call of `aes_evmulti`'s tables, run once for the tests of that case (above)."""
    return evm.run(getattr(evm, table)[name])


def word(image, at):
    return case.word_in(image, at)


def mouse(image):
    return word(image, aes.AES_XRAT), word(image, aes.AES_YRAT)


EIGHT_BITS_HELD = 0xFF                  # a process's event bits with the ROM's iasync's eight waits of no kind held
THE_NINTH_AND_TENTH_BITS = 0x300        # ...and the bits of the two waits queued after them ($100, $200)


def events(image, pd=SHELL):
    """A process's three event words: the bits its EVBs hold, those it waits for, those that came."""
    return tuple(word(image, pd + field) for field in (aes.PD_EVBITS, aes.PD_EVWAIT, aes.PD_EVFLG))


def evb_table(image):
    return bytes(image[aes.AES_EVB_TABLE:aes.AES_EVB_TABLE + aes.AES_EVB_COUNT * aes.EVB_BYTES])


# ---- the host's stand-in for the frame's QPB (FIRST in the file: a library that kept it would abort every later
# in-process run of a call that queues a message wait, the worker with it — which is no failing test) -----------------------
def test_the_qpb_s_host_slot_is_given_back_when_the_call_returns():
    """OFF TARGET ALONE (`host_slot.h`): a call that queued a message wait and RETURNED has given its process's slot
    back — the same process's next call claims it again. Two calls in one fork: both return."""
    returncode, stderr = evm.twice_in_a_fork(evm.THE_MOUSE_ANOTHER_S["on the bar: a rectangle come, a message wait cancelled"])
    assert returncode == 0, f"the second call did not return ({returncode}): {stderr}"


# ---- every call ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", evm.RETURNING)
def test_every_call_that_returns(name):
    assert not isinstance(ran("RETURNING", name), evm.Switched)


@pytest.mark.parametrize("name", evm.NOTHING_COME)
def test_every_call_nothing_has_come_for_blocks_as_the_rom_s_does_at_dsptch(name):
    switched = ran("NOTHING_COME", name)
    assert isinstance(switched, evm.Switched) and evm.BLOCKS in switched.stderr
    assert evm.answers(switched.image) == NOTHING_ANSWERED       # no answer is written before the wait


THROUGH_ITS_CALL_WORD = ("a key queued", "a message in the pipe", "a click, the button wanted down",
                         "on the bar: every event asked, three come at once")


@pytest.mark.parametrize("name", THROUGH_ITS_CALL_WORD)
def test_a_call_made_through_its_line_f_word(name):
    made = evm.RETURNING[name]
    evm.returning(made.arguments, evm.machine_of(made), through_line_f=True)


# ---- the events answered -----------------------------------------------------------------------------------------------------
CAME = {
    "a key queued": KEYBD, "three keys queued": KEYBD, "Alt-= queued, Alt held": KEYBD,
    "the key queue's front round the ring": KEYBD, "a key queued, the button up as wanted too": KEYBD | BUTTON,
    "a key queued and not asked for, the button up": BUTTON, "the button up, as wanted": BUTTON,
    "the button down, as wanted": BUTTON, "either button not up, the left down": BUTTON,
    "the mouse in the rectangle it is to enter": M1, "the mouse out of the rectangle it is to leave": M1,
    "the second rectangle alone": M2, "both rectangles": M1 | M2, "the first rectangle of two": M1,
    "the second rectangle of two": M2, "a timer of no time": TIMER, "a timer of no time, a key not come": TIMER,
    "a message in the pipe": MESAG, "two messages in the pipe": MESAG, "the pipe full": MESAG,
    "a message and a timer of no time": MESAG | TIMER, "every event come at once": EVERY_EVENT,
    "a message in the pipe and not asked for, a timer of no time": TIMER,
    "a key queued, a message asked for and not come": KEYBD,
    "a key queued, flags above the six set": KEYBD, "the screen manager's own message": MESAG,
    "a rectangle and the buttons asked, after a mouse wait was woken": M1,
    "a rectangle alone, after a mouse wait was woken": M1,
    "the screen manager's own call: a key, the buttons, its rectangle": M1,
    "the screen manager, the button up as wanted": BUTTON,
    "every event by the screen manager, a rectangle come": M1,
    "the button up as wanted, after a mouse wait was woken": BUTTON,
    "a key typed": KEYBD, "a key typed and not asked for": BUTTON, "a key typed into a full queue": KEYBD,
    "a press": BUTTON, "a click, the button wanted down": BUTTON, "a click, the button wanted up": BUTTON,
    "a click, either button wanted not up": BUTTON, "the left held, the right clicked: the left wanted down": BUTTON,
    "a double click": BUTTON, "a right press": BUTTON, "a release": BUTTON, "the mouse moved into the rectangle": M1,
    "the fork queue full of moves, a timer of no time": TIMER,
    "a press, then the mouse moved away": BUTTON | M1, "a key typed and a press": KEYBD | BUTTON,
    "ticks, no timer running": TIMER,
    "the mouse moved onto the bar, the button up as wanted": BUTTON, "the mouse moved onto the bar, to enter it": M1,
    "on the bar: the button up as wanted": BUTTON, "on the bar: the first rectangle": M1,
    "on the bar: the second rectangle": M2, "on the bar: the buttons and both rectangles at once": BUTTON | M1 | M2,
    "on the bar: every event asked, three come at once": BUTTON | M1 | M2,
    "on the bar: three come at once, a key's and a timer's waits cancelled": BUTTON | M1 | M2,
    "on the bar: a rectangle come, the buttons not": M1,
    "on the bar: the buttons come, a key and a timer cancelled": BUTTON,
    "on the bar: a rectangle come, a message wait cancelled": M1,
    "on the bar: the buttons come, a rectangle's wait cancelled": BUTTON,
    "on the bar: a rectangle come, a double-click wait cancelled": M1,
    "pressed on the bar: the button down as wanted": BUTTON,
    "on the bar, eight event bits held (the ROM's iasync): three come at once": BUTTON | M1 | M2,
}


def test_every_returning_call_s_events_are_stated():
    assert CAME.keys() == evm.RETURNING.keys()


@pytest.mark.parametrize("name", CAME)
def test_it_answers_the_events_that_came_and_no_other(name):
    assert evm.came(ran("RETURNING", name)) == CAME[name]


# ---- it polls first ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", evm.POLLS_FIRST)
def test_an_event_that_has_come_is_answered_with_nothing_queued_and_nothing_waited_for(name):
    """The path every caller that does not block takes: no EVB taken (the whole table as it was), the process's three
    event words as they were — mwait, which stores the events waited for, was never called."""
    made = evm.POLLS_FIRST[name]
    image, result = before(made), ran("RETURNING", name)
    running = evasync.running(image)
    assert evb_table(result.final) == evb_table(image) and events(result.final, running) == events(image, running)
    assert evasync.free_evbs(result.final) == evasync.free_evbs(image)


def front_key(image, pd=SHELL):
    queue = case.long_in(image, pd + aes.PD_CDA) + FM["CDA_KEY_QUEUE"]
    return word(image, queue + FM["CQUEUE_KEYS"] + word(image, queue + FM["CQUEUE_FRONT"]) * WORD_BYTES)


@pytest.mark.parametrize("name, key, shift", (("a key queued", None, 0), ("Alt-= queued, Alt held", evlib.ALT_EQUALS, evlib.ALT_HELD),
                                               ("the key queue's front round the ring", None, 0)))
def test_a_queued_key_is_taken_into_the_fifth_answer(name, key, shift):
    made = evm.POLLS_FIRST[name]
    image, result = before(made), ran("RETURNING", name)
    count = case.long_in(image, SHELL + aes.PD_CDA) + aes.CDA_KEY_COUNT
    answered = evm.answers(result.final)
    assert answered[KEY] == front_key(image) != 0 and (key is None or answered[KEY] == key)
    assert answered[:KEY] == [*mouse(image), 0, shift] and answered[CLICKS] == STALE
    assert word(result.final, count) == word(image, count) - 1


@of_the_case("a key queued and not asked for, the button up")
def test_a_key_not_asked_for_stays_queued():
    made = evm.POLLS_FIRST["a key queued and not asked for, the button up"]
    count = case.long_in(before(made), SHELL + aes.PD_CDA) + aes.CDA_KEY_COUNT
    result = ran("RETURNING", "a key queued and not asked for, the button up")
    assert word(result.final, count) == word(before(made), count) == 1 and evm.answers(result.final)[KEY] == STALE


@of_the_case("a key typed")
def test_a_key_typed_while_the_process_was_busy_is_polled_posted_and_answered():
    """The key is in the keyboard's ring when the call begins: chkkbd polls it through the VDI and queues kchange,
    forker runs it (post_keybd: nobody waits, so nq), and the fast path takes it."""
    made = evm.WHILE_IT_WAS_BUSY["a key typed"]
    assert word(before(made), case.long_in(before(made), SHELL + aes.PD_CDA) + aes.CDA_KEY_COUNT) == 0
    assert evm.answers(ran("RETURNING", "a key typed").final)[KEY] == aes_event.RETURN_KEY << 8 | ord("\r")


@of_the_case("a key typed into a full queue")
def test_a_key_typed_into_a_full_queue_is_left_in_the_keyboard_s_ring():
    """chkkbd polls only while the owner's queue has room: the call answers the OLDEST queued key, and the typed one
    is still unread."""
    made = evm.WHILE_IT_WAS_BUSY["a key typed into a full queue"]
    image, result = before(made), ran("RETURNING", "a key typed into a full queue")
    assert evm.answers(result.final)[KEY] == front_key(image)
    assert aes_event.fork_queue(result.final) == []


@of_the_case("the fork queue full of moves, a timer of no time")
def test_a_full_fork_queue_is_run_empty_before_anything_is_looked_at():
    """Every entry of the queue a move the ROM's motion glue queued while the process was busy: forker runs them all
    — the routine's dearest call, and Tier 3's worst row."""
    made = evm.WHILE_IT_WAS_BUSY["the fork queue full of moves, a timer of no time"]
    assert len(aes_event.fork_queue(before(made))) == aes.AES_FORK_ENTRIES
    assert aes_event.fork_queue(ran("RETURNING", "the fork queue full of moves, a timer of no time").final) == []


# ---- the buttons -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name, buttons, clicks", (
    ("the button up, as wanted", 0, 0), ("the button down, as wanted", evm.LEFT, 1),
    ("either button not up, the left down", evm.LEFT, 1), ("a press", evm.LEFT, 1), ("a double click", evm.LEFT, 2),
    ("a right press", evm.RIGHT, 1), ("a release", 0, 1), ("a click, the button wanted up", 0, 1),
))
def test_the_buttons_as_they_are_satisfy_a_button_event(name, buttons, clicks):
    """...the buttons into the third answer (through $c792, which ev_rets hands out) and the last change's clicks
    into the sixth."""
    result = ran("RETURNING", name)
    answered = evm.answers(result.final)
    assert (answered[BUTTONS], answered[CLICKS]) == (buttons, clicks) and answered[KEY] == STALE
    assert word(result.final, BUTTON_STATE) == word(result.final, aes.AES_BUTTON) == buttons


@of_the_case("a click, the button wanted down")
def test_a_click_that_came_and_went_still_answers_a_wait_for_the_button_down():
    """A press AND its release were posted before the call (two changes): the button is up again, and the wait for it
    DOWN is answered by the buttons BEFORE the last change — the click record's, with its clicks."""
    made = evm.WHILE_IT_WAS_BUSY["a click, the button wanted down"]
    result = ran("RETURNING", "a click, the button wanted down")
    answered = evm.answers(result.final)
    assert word(before(made), aes.AES_MTRANS) == 0 and len(aes_event.fork_queue(before(made))) == 2
    assert word(result.final, aes.AES_BUTTON) == 0 and word(result.final, aes.AES_PR_BUTTON) == evm.LEFT
    assert (answered[BUTTONS], answered[CLICKS]) == (evm.LEFT, word(result.final, aes.AES_PR_MCLICK))
    assert word(result.final, aes.AES_MTRANS) == 0          # ev_rets cleared the count


@of_the_case("the left held, the right clicked: the left wanted down")
def test_the_click_record_s_buttons_answer_alone_where_the_buttons_as_they_are_would_too():
    """The left held, the right clicked (two changes), the left wanted down: the buttons BEFORE the last change
    (both) and the buttons as they are (the left) both satisfy the wait — the ROM answers the record's and does not
    try the others."""
    result = ran("RETURNING", "the left held, the right clicked: the left wanted down")
    assert word(result.final, aes.AES_PR_BUTTON) == evm.LEFT | evm.RIGHT and word(result.final, aes.AES_BUTTON) == evm.LEFT
    assert evm.answers(result.final)[BUTTONS] == evm.LEFT | evm.RIGHT == word(result.final, BUTTON_STATE)


@of_the_case("a click, either button wanted not up")
def test_the_click_record_is_tried_with_the_whole_button_parameter():
    """A click that came and went, EITHER button wanted not up (the flag is in the parameter's HIGH word): the buttons
    as they are (both up) do not answer; the record's — the left down — do."""
    result = ran("RETURNING", "a click, either button wanted not up")
    assert word(result.final, aes.AES_BUTTON) == 0 and evm.answers(result.final)[BUTTONS] == evm.LEFT


@of_the_case("the screen manager, the button up as wanted")
def test_the_mouse_s_owner_is_compared_with_the_running_process():
    """The SCREEN MANAGER running, the mouse its own: the fast path's button test is its to pass — no wait queued."""
    made = evm.POLLS_FIRST["the screen manager, the button up as wanted"]
    image = before(made)
    assert evasync.running(image) == SCREEN_MANAGER == case.long_in(image, MOWNER)
    assert evm.came(ran("RETURNING", "the screen manager, the button up as wanted")) == BUTTON


@of_the_case("a press, the button wanted up")
def test_one_change_alone_is_not_looked_for_in_the_click_record():
    """A press, the button wanted UP: one change posted — the buttons before it (up) would satisfy the wait, and are
    not tried. The call blocks, a wait queued."""
    switched = ran("NOTHING_COME", "a press, the button wanted up")
    assert word(switched.image, aes.AES_MTRANS) == 1 and word(switched.image, aes.AES_PR_BUTTON) == 0
    assert len(evasync.wait_list(switched.image, case.long_in(switched.image, aes.AES_GL_CDA) + aes.CDA_BUTTON_WAIT)) == 1


@of_the_case("a press, then the mouse moved away")
def test_a_press_answers_where_it_was_made_not_where_the_mouse_is_now():
    made = evm.WHILE_IT_WAS_BUSY["a press, then the mouse moved away"]
    result = ran("RETURNING", "a press, then the mouse moved away")
    assert evm.answers(result.final)[:Y + 1] == list(mouse(before(made))) != list(mouse(result.final)) == list(evasync.OUTSIDE)


# ---- THE ROM FINDING: the buttons answered are stale unless a button event came -----------------------------------------------
@of_the_case("a rectangle and the buttons asked, after a mouse wait was woken")
def test_the_buttons_answered_after_a_mouse_wait_are_its_rectangle_s_width():
    """PD0's evnt_multi parked for the mouse to leave a rectangle 20 wide and was woken by it: apret left that wait's
    high word in $c792. The NEXT evnt_multi, asking for the buttons and a rectangle, gets the rectangle — and answers
    buttons = 20, no button down."""
    result = ran("RETURNING", "a rectangle and the buttons asked, after a mouse wait was woken")
    width = evm.ROUND_THE_MOUSE[2]
    assert word(result.final, aes.AES_BUTTON) == 0 and evm.answers(result.final)[BUTTONS] == width


@of_the_case("a rectangle alone, after a mouse wait was woken")
def test_the_buttons_answered_are_the_buttons_when_no_button_event_is_asked_for():
    """...the same machine, the rectangle alone: ev_multi stores the buttons themselves over ev_rets' third answer."""
    result = ran("RETURNING", "a rectangle alone, after a mouse wait was woken")
    assert word(result.final, BUTTON_STATE) == evm.ROUND_THE_MOUSE[2] and evm.answers(result.final)[BUTTONS] == 0


@of_the_case("the button up as wanted, after a mouse wait was woken")
def test_a_button_event_that_came_answers_the_buttons_whatever_was_left():
    result = ran("RETURNING", "the button up as wanted, after a mouse wait was woken")
    assert evm.answers(result.final)[BUTTONS] == 0 == word(result.final, BUTTON_STATE)


THE_MANAGER_S_OWN = "the screen manager's own call: a key, the buttons, its rectangle"


@of_the_case(THE_MANAGER_S_OWN)
def test_the_screen_manager_s_own_evnt_multi_answers_216_buttons_on_the_snapshot_s_machine():
    """NO ARGUMENT CLASS, nothing staged but the answers' place: the screen manager as the mouse entering the bar's
    rectangle woke it, making THE CALL ITS OWN CODE MAKES (`aes_evmulti.THE_MANAGER_S_OWN_CALL`: the frame the ROM's
    control manager builds, its MOBLK the AES's own). Its last answered wait was that mouse wait, and what its apret
    left in $c792 is the rectangle's width — handed out as the buttons, no button down."""
    made = evm.POLLS_FIRST[THE_MANAGER_S_OWN]
    image, result = before(made), ran("RETURNING", THE_MANAGER_S_OWN)
    leftover = word(image, BUTTON_STATE)
    assert evasync.running(image) == SCREEN_MANAGER and word(image, aes.AES_BUTTON) == 0
    assert leftover == word(BASE_IMAGE, aes.header_constants("mnlib.h")["AES_GL_RMNACTV"] + aes.GRECT_W) != 0
    assert evm.answers(result.final)[BUTTONS] == leftover


# `move.l #long,-(sp)`, `clr.l -(sp)`, `move.w #word,-(sp)`: the three instructions the ROM pushes a frame's constants with.
PUSH_A_LONG, PUSH_A_WORD = (int.from_bytes(opcode, "big") for opcode in (opcodes.PUSH_LONG_IMMEDIATE, opcodes.PUSH_WORD_IMMEDIATE))
PUSH_NO_LONG = 0x42A7                   # clr.l -(sp)


def test_the_frame_the_rom_s_control_manager_pushes_is_the_case_s():
    """...read off the ROM's own text: the pushes of that frame — no message buffer, the button parameter, no timer,
    the MOBLK twice, the flags — stand in the ROM once ($fe49fc: ctlmgr's call), and the case's frame is theirs."""
    flags, first, second, timer, button, message, _answers = evm.THE_MANAGER_S_OWN_CALL.arguments
    pushes = struct.pack(">HHIHHIHIHH", PUSH_NO_LONG, PUSH_A_LONG, button, PUSH_NO_LONG, PUSH_A_LONG, second,
                         PUSH_A_LONG, first, PUSH_A_WORD, flags)
    assert (timer, message) == (0, 0) and bytes(BASE_IMAGE).count(pushes) == 1


# ---- the mouse another process's: the waits are satisfied where they are queued, and the tail runs --------------------------
def taken(image, count):
    """The EVBs `count` waits queued over `image` take, in order: the free list's first."""
    return evasync.free_evbs(image)[:count]


@of_the_case("pressed on the bar: the button down as wanted")
def test_a_button_wait_satisfied_where_it_is_queued_is_answered_through_apret():
    """PD0 with the mouse the screen manager's: the fast path does not look at the buttons; abutton does. The wait is
    completed where it is queued, mwait returns at once, and the answers are apret's: no clicks, and the buttons
    apret left in $c792."""
    made = evm.THE_MOUSE_ANOTHER_S["pressed on the bar: the button down as wanted"]
    image, result = before(made), ran("RETURNING", "pressed on the bar: the button down as wanted")
    assert case.long_in(image, MOWNER) == SCREEN_MANAGER != evasync.running(image)
    answered = evm.answers(result.final)
    assert (answered[BUTTONS], answered[CLICKS]) == (evm.LEFT, 0) and word(result.final, BUTTON_STATE) == evm.LEFT
    assert evasync.free_evbs(result.final) == evasync.free_evbs(image) and events(result.final)[2] == 0
    assert evb_table(result.final) != evb_table(image)      # an EVB was taken, and given back


@of_the_case("on the bar: the buttons and both rectangles at once")
def test_the_waits_that_came_are_answered_in_the_order_buttons_first_rectangle_second():
    """Three waits completed where they were queued, none cancelled: each apret puts its EVB back at the head of the
    free list, so the list ends in the REVERSE of the order they were answered in."""
    made = evm.THE_MOUSE_ANOTHER_S["on the bar: the buttons and both rectangles at once"]
    image, result = before(made), ran("RETURNING", "on the bar: the buttons and both rectangles at once")
    the_buttons, first, second = taken(image, 3)
    assert evasync.free_evbs(result.final)[:3] == [second, first, the_buttons]
    assert evasync.completed(result.final) == [] and events(result.final) == (events(image)[0], 0, 0)


@of_the_case("on the bar: every event asked, three come at once")
def test_the_waits_that_did_not_come_are_cancelled():
    """Every event asked for, three completed where they were queued: the key's, the message's and the timer's waits
    are taken off their lists and freed (acancel) before anything is answered — nothing of the call stays queued."""
    made = evm.THE_MOUSE_ANOTHER_S["on the bar: every event asked, three come at once"]
    image, result = before(made), ran("RETURNING", "on the bar: every event asked, three come at once")
    final = result.final
    assert sorted(evasync.free_evbs(final)) == sorted(evasync.free_evbs(image)) and evasync.evlist(final, SHELL) == []
    assert evasync.wait_list(final, EV["AES_DELAY_LIST"]) == [] == evasync.wait_list(final, SHELL + aes.PD_QUEUE_READERS)
    cda = case.long_in(final, aes.AES_GL_CDA)
    assert all(evasync.wait_list(final, cda + wait) == evasync.wait_list(image, cda + wait)
               for wait in (aes.CDA_KEYBOARD_WAIT, aes.CDA_BUTTON_WAIT, aes.CDA_MOUSE_WAIT))
    assert events(final) == (events(image)[0], 0, 0)


@of_the_case("on the bar: a rectangle come, a message wait cancelled")
def test_a_cancelled_message_wait_leaves_its_qpb_s_address_in_the_freed_evb():
    """A ROM FACT the differential drops BY NAME, vetted (`aes_event.run_layer_case`): an EVB is freed as it is, so the
    address of the QPB the message wait was queued with — a local of ev_multi's frame — is still in its parameter at
    the return, until get_evb next clears it."""
    made = evm.THE_MOUSE_ANOTHER_S["on the bar: a rectangle come, a message wait cancelled"]
    (parm_at, qpb), = aes_event.qpb_addresses_a_return_leaves(EV_MULTI, made.arguments, evm.machine_of(made)).items()
    assert qpb == (evm.SHELL_PID, evm.MESSAGE_BYTES, MESSAGE_AT)
    assert parm_at - aes.EVB_PARM in evasync.free_evbs(ran("RETURNING", "on the bar: a rectangle come, a message wait cancelled").final)


@of_the_case("on the bar: a rectangle come, a double-click wait cancelled")
def test_a_double_click_wait_that_is_cancelled_stays_counted():
    """A ROM FINDING, from ev_multi's side (the lists' battery pins acancel's): abutton counts a wait for more than
    one click into $c84e, and acancel's takeoff does not count it out — every evnt_multi that asks for a double
    click and is ended by ANOTHER event leaves the count one higher."""
    made = evm.THE_MOUSE_ANOTHER_S["on the bar: a rectangle come, a double-click wait cancelled"]
    result = ran("RETURNING", "on the bar: a rectangle come, a double-click wait cancelled")
    assert word(result.final, BPEND) == word(before(made), BPEND) + 1


@of_the_case("on the bar, eight event bits held (the ROM's iasync): three come at once")
def test_event_bits_above_the_low_byte_are_waited_for_and_answered_as_words():
    """AN ARGUMENT-CLASS MACHINE (`aes_evmulti.eight_bits_held_on_the_bar`): the waits' bits are $100..$2000; every
    one is found come, cancelled or answered by its WORD."""
    made = evm.THE_MOUSE_ANOTHER_S["on the bar, eight event bits held (the ROM's iasync): three come at once"]
    image, result = before(made), ran("RETURNING", "on the bar, eight event bits held (the ROM's iasync): three come at once")
    assert events(image)[0] == EIGHT_BITS_HELD and events(result.final) == (EIGHT_BITS_HELD, 0, 0)
    assert sorted(evasync.free_evbs(result.final)) == sorted(evasync.free_evbs(image))


# ---- nothing has come: what is queued, in which order -----------------------------------------------------------------------
@of_the_case("every event")
def test_every_event_is_queued_key_buttons_rectangles_message_timer_and_waited_for():
    """Six waits, six EVBs taken in that order (the message's BEFORE the timer's — the fast path tests them the other
    way round), each on its own list, the process's bits and the events it waits for all six, the process WAITING."""
    made = evm.NOTHING_COME["every event"]
    image, switched = before(made), ran("NOTHING_COME", "every event")
    key, the_buttons, first, second, message, timer = taken(image, 6)
    at = switched.image
    cda = case.long_in(at, aes.AES_GL_CDA)
    assert evasync.evlist(at, SHELL) == [timer, message, second, first, the_buttons, key]
    assert [evasync.evb_of(at, evb)["MASK"] for evb in (key, the_buttons, first, second, message, timer)] == [1, 2, 4, 8, 16, 32]
    assert evasync.wait_list(at, cda + aes.CDA_KEYBOARD_WAIT) == [key]
    assert evasync.wait_list(at, cda + aes.CDA_BUTTON_WAIT) == [the_buttons]
    assert evasync.wait_list(at, cda + aes.CDA_MOUSE_WAIT) == [second, first]
    assert evasync.wait_list(at, SHELL + aes.PD_QUEUE_READERS) == [message]
    assert evasync.wait_list(at, EV["AES_DELAY_LIST"]) == [timer]
    assert events(at) == (EVERY_EVENT, EVERY_EVENT, 0) and word(at, SHELL + aes.PD_STAT) == aes.PD_STAT_WAITING
    assert evasync.evb_of(at, the_buttons)["PARM"] == evm.A_DOUBLE_CLICK and word(at, BPEND) == word(image, BPEND) + 1
    assert switched.parked == ((evm.SHELL_PID, evm.MESSAGE_BYTES, MESSAGE_AT),)


@of_the_case("a message and a timer")
def test_an_event_bit_is_the_wait_s_not_the_flag_s():
    """A message and a timer alone: their waits take the first two bits, in the order they are queued."""
    made = evm.NOTHING_COME["a message and a timer"]
    image, switched = before(made), ran("NOTHING_COME", "a message and a timer")
    message, timer = taken(image, 2)
    assert [evasync.evb_of(switched.image, evb)["MASK"] for evb in (message, timer)] == [1, 2]
    assert evasync.wait_list(switched.image, SHELL + aes.PD_QUEUE_READERS) == [message]
    assert evasync.wait_list(switched.image, EV["AES_DELAY_LIST"]) == [timer] and events(switched.image)[1] == 3


@pytest.mark.parametrize("name, ticks", (("a timer", evm.A_TIMER_TICKS), ("a timer of less than a tick", 1),
                                         ("a timer of one millisecond", 1),
                                         ("a timer whose low word is 0", evm.A_TIME_IN_THE_HIGH_WORD // evm.TICK_MS),
                                         ("a timer of a negative time", -evm.A_TIMER_TICKS)))
def test_a_timer_is_queued_in_ticks(name, ticks):
    """The milliseconds divided by the tick's as SIGNED LONGS; no tick is one tick (adelay); and a timer whose low
    word alone is 0 has NOT come — the fast path tests the long."""
    made = evm.NOTHING_COME[name]
    timer, = taken(before(made), 1)
    switched = ran("NOTHING_COME", name)
    assert aes.signed(evasync.evb_of(switched.image, timer)["PARM"], 32) == ticks
    assert evasync.wait_list(switched.image, EV["AES_DELAY_LIST"]) == [timer]


@of_the_case("a message, none in the pipe")
def test_a_message_wait_s_qpb_is_the_running_process_s_one_message_and_the_buffer():
    for name, pid, pd in (("a message, none in the pipe", evm.SHELL_PID, SHELL),
                          ("a message, by the screen manager", evm.SCREEN_MANAGER_PID, SCREEN_MANAGER)):
        switched = ran("NOTHING_COME", name)
        assert switched.parked == ((pid, evm.MESSAGE_BYTES, MESSAGE_AT),)
        assert len(evasync.wait_list(switched.image, pd + aes.PD_QUEUE_READERS)) == 1


@of_the_case("a message, none in the pipe")
def test_two_processes_message_waits_keep_their_qpbs_in_two_places():
    """The QPB is the calling PROCESS's (a local of its own frame, on its own stack in the ROM): the desk's parked
    message wait and the screen manager's leave their EVBs pointing at two places of the stack band, a process id
    apart — one place for both would hand a writer to the desk the manager's QPB the day both are parked at once."""
    places = {}
    for name, pd in (("a message, none in the pipe", SHELL), ("a message, by the screen manager", SCREEN_MANAGER)):
        switched = ran("NOTHING_COME", name)
        waiting, = evasync.wait_list(switched.image, pd + aes.PD_QUEUE_READERS)
        places[pd] = evasync.evb_of(switched.image, waiting)["PARM"]
    assert places[SCREEN_MANAGER] - places[SHELL] == (evm.SCREEN_MANAGER_PID - evm.SHELL_PID) * evm.QPB.size


@pytest.mark.parametrize("name", ("no event at all", "a flag no event has"))
def test_a_call_that_asks_for_no_event_blocks_for_good(name):
    """A ROM FINDING: nothing is queued, mwait is handed no event — and with none come it enters the dispatcher: a
    process no event will ever wake."""
    made = evm.NOTHING_COME[name]
    image, switched = before(made), ran("NOTHING_COME", name)
    assert evb_table(switched.image) == evb_table(image) and evasync.evlist(switched.image, SHELL) == []
    assert events(switched.image) == (0, 0, 0) and word(switched.image, SHELL + aes.PD_STAT) == aes.PD_STAT_WAITING


NO_EVB_FREE = "iasync: no EVB is free"


def test_past_the_last_evb_the_host_refuses_by_name():
    """A ROM DEFECT REACHED THROUGH ev_multi, on AN ARGUMENT-CLASS MACHINE (`aes_evmulti.PAST_THE_LAST_EVB`: four EVBs
    free, six waits asked — by counting, a state no machine reaches: every accessory brings five EVBs of its own and
    a process asks six at most). get_evb answers NULL for the fifth and iasync does not test it: the ROM builds the
    message's wait, then the timer's, in "the EVB at address 0". THE ORACLE lets those stores through — its run parks
    with the exception vectors' page rewritten — where a 68000 takes a bus error at the first (address 0 is ROM): the
    oracle's answer is not the machine's, so the host REFUSES BY NAME at iasync, after the four waits the ROM
    queues before it (every EVB of the table as the ROM's run has it) and with nothing stored at address 0. The
    target build keeps the ROM's plain stores."""
    made = evm.PAST_THE_LAST_EVB
    image, machine = before(made), evm.machine_of(made)
    the_rom_s = aes_event.rom_at_dsptch(EV_MULTI, made.arguments, machine)
    assert the_rom_s.memory[:aes.EVB_BYTES] != bytes(image[:aes.EVB_BYTES]), "the premise: the oracle's run stores at 0"
    refused = aes_event.core_in_a_fork(EV_MULTI, made.arguments, machine, read_back=True, hook=evm.HOOKS)
    assert refused.returncode not in (0, aes_event.FORK_RAISED) and NO_EVB_FREE in refused.stderr, refused.stderr
    assert len(evasync.free_evbs(image)) == 4 and evasync.free_evbs(refused.image) == []
    assert evb_table(refused.image) == evb_table(the_rom_s.memory)
    assert refused.image[:aes.EVB_BYTES] == bytes(image[:aes.EVB_BYTES])


# ---- a message that has come ----------------------------------------------------------------------------------------------------
def pipe(image, pd=SHELL):
    return bytes(image[pd + aes.PD_QUEUE:pd + aes.PD_QUEUE + word(image, pd + aes.PD_QUEUE_INDEX)])


@pytest.mark.parametrize("name, pd", (("a message in the pipe", SHELL), ("two messages in the pipe", SHELL),
                                      ("the pipe full", SHELL), ("the screen manager's own message", SCREEN_MANAGER)))
def test_a_message_in_the_running_process_s_pipe_is_read_into_the_buffer(name, pd):
    made = evm.POLLS_FIRST[name]
    image, result = before(made), ran("RETURNING", name)
    held = pipe(image, pd)
    assert held and result.after(MESSAGE_AT, evm.MESSAGE_BYTES) == held[:evm.MESSAGE_BYTES]
    assert pipe(result.final, pd) == held[evm.MESSAGE_BYTES:]


def test_half_a_message_in_the_pipe_reaches_the_pipes_named_refusal():
    """The ROM's own appl_write of EIGHT bytes, then a message asked for: the pipe holds something, so the fast path
    reads sixteen — more than it holds. The ROM's run never comes back (`pdpipe.c`: doq moves 64 KB of the AES's RAM
    over itself); the C reaches the pipes' refusal of it, by name, through ev_mesag."""
    half = aes_pdpipe.sent(merge_pokes(evm.desk(), aes_pdpipe.STALE_BUFFER), evm.SHELL_PID, evlib.A_MESSAGE[:evm.MESSAGE_BYTES // 2])
    made = call(lambda: half, MESAG)
    refused = aes_event.core_in_a_fork(EV_MULTI, made.arguments, evm.machine_of(made), hook=evm.HOOKS)
    assert refused.returncode not in (0, aes_event.FORK_RAISED) and READ_PAST_THE_PIPE in refused.stderr, refused.stderr


@of_the_case("a message in the pipe and not asked for, a timer of no time")
def test_a_message_not_asked_for_stays_in_the_pipe():
    made = evm.POLLS_FIRST["a message in the pipe and not asked for, a timer of no time"]
    result = ran("RETURNING", "a message in the pipe and not asked for, a timer of no time")
    assert pipe(result.final) == pipe(before(made)) != b"" and result.after(MESSAGE_AT, evm.MESSAGE_BYTES) == evm.STALE_MESSAGE[MESSAGE_AT]


@pytest.mark.parametrize("name, cleared", (("a message in the pipe", True), ("a message, none in the pipe", False),
                                           ("a timer of no time", False),
                                           ("a key queued, a message asked for and not come", False)))
def test_the_control_manager_s_sent_mark(name, cleared):
    """AN ARGUMENT-CLASS CASE OVER A POKED FIELD (the mark set: the control manager sets it after it sends a window
    message, a run this battery does not make): a message that CAME clears it; a call that blocks, or that answers
    another event — a message asked for or not — leaves it."""
    made = (evm.POLLS_FIRST if name in evm.POLLS_FIRST else evm.NOTHING_COME)[name]
    result = evm.held(made.arguments, merge_pokes(evm.machine_of(made), {SENT_MARK: struct.pack(">H", 1)}))
    assert word(evm.image_after(result), SENT_MARK) == (0 if cleared else 1)


# ---- ARGUMENT-CLASS CASES: pointers through the bus, widths, the order of reads and stores --------------------------------
TAG = aes.BUS_TAG
TAGGED = {
    "a rectangle come": call(evm.desk, M1 | M2, first=evm.IN, second=evm.OUT)._replace(
        arguments=(M1 | M2, evm.FIRST_RECT_AT | TAG, evm.SECOND_RECT_AT | TAG, 0, 0, MESSAGE_AT, ANSWERS_AT | TAG)),
    "a key queued": call(evm.key_queued, KEYBD, answers=ANSWERS_AT | TAG),
    "the button down": call(evm.button_held, BUTTON, button=evm.THE_BUTTON_DOWN, answers=ANSWERS_AT | TAG),
    "a message come": call(lambda: evlib.holding(1), MESAG, message=MESSAGE_AT | TAG, answers=ANSWERS_AT | TAG),
    "the waits come where they are queued": call(evm.on_the_bar, EVERY_EVENT, timer=evm.A_TIMER_MS, message=MESSAGE_AT | TAG,
                                                 answers=ANSWERS_AT | TAG, **evm.THREE_AT_ONCE)._replace(
        arguments=(EVERY_EVENT, evm.FIRST_RECT_AT | TAG, evm.SECOND_RECT_AT | TAG, evm.A_TIMER_MS, evm.THE_BUTTON_UP,
                   MESSAGE_AT | TAG, ANSWERS_AT | TAG)),
    "nothing come": call(evm.desk, EVERY_EVENT, message=MESSAGE_AT | TAG, answers=ANSWERS_AT | TAG, **evm.EVERY)._replace(
        arguments=(EVERY_EVENT, evm.FIRST_RECT_AT | TAG, evm.SECOND_RECT_AT | TAG, evm.A_TIMER_MS, evm.A_DOUBLE_CLICK,
                   MESSAGE_AT | TAG, ANSWERS_AT | TAG)),
}


@pytest.mark.parametrize("name", TAGGED)
def test_every_pointer_is_taken_through_the_bus(name):
    """The MOBLKs', the message buffer's and the answers' pointers with a top byte."""
    result = evm.run(TAGGED[name])
    if name == "nothing come":      # ...and a message wait's QPB keeps the buffer's LONG, tag and all
        assert result.parked == ((evm.SHELL_PID, evm.MESSAGE_BYTES, MESSAGE_AT | TAG),)
    else:
        assert evm.answers(evm.image_after(result))[:Y + 1] == list(mouse(evm.image_after(result)))


OVERLAPS = {
    # ev_rets stores $c792 over the buttons' own word, and the buttons stored over the third answer are read AFTER.
    "the buttons' word under the third answer, no button event asked": call(
        evm.button_held, M1, first=evm.IN, answers=aes.AES_BUTTON - BUTTONS * WORD_BYTES),
    # the key is stored over the count of button changes BEFORE the button test reads the count.
    "the count of button changes under the key's answer": call(
        evm.typed_and_pressed, KEYBD | BUTTON, button=evm.THE_BUTTON_UP, answers=aes.AES_MTRANS - KEY * WORD_BYTES),
    # the clicks are stored over the second MOBLK's leave flag BEFORE ev_mchk reads the MOBLK.
    "the second rectangle's flag under the clicks' answer": call(
        evm.pressed, BUTTON | M2, second=evm.IN, button=evm.THE_BUTTON_DOWN,
        answers=evm.SECOND_RECT_AT - CLICKS * WORD_BYTES),
    # the key is stored over the control manager's mark, which ev_mesag then clears: the key answered is lost.
    "the sent mark under the key's answer": call(evm.a_key_queued_and_a_message, KEYBD | MESAG,
                                                 answers=SENT_MARK - KEY * WORD_BYTES),
    # ...and the mouse's x over it, which the tail clears last.
    "the sent mark under the first answer": call(lambda: evlib.holding(1), MESAG, answers=SENT_MARK),
    # the message is read into the buffer first, the answers stored over it after.
    "the message buffer under the answers": call(lambda: evlib.holding(1), MESAG, answers=MESSAGE_AT),
    # apret's answer (no clicks) is stored over $c792, and the buttons stored over the third answer are read AFTER.
    "the buttons apret left under the clicks' answer": call(
        evm.pressed_on_the_bar, BUTTON, button=evm.THE_BUTTON_DOWN, answers=BUTTON_STATE - CLICKS * WORD_BYTES),
    # ...and so with each of ev_rets' other answers over the buttons' word: what is stored there is what is read.
    "the buttons' word under the first answer, no button event asked": call(evm.button_held, M1, first=evm.IN,
                                                                           answers=aes.AES_BUTTON),
    "the buttons' word under the second answer, no button event asked": call(
        evm.button_held, M1, first=evm.IN, answers=aes.AES_BUTTON - Y * WORD_BYTES),
    "the buttons' word under the fourth answer, no button event asked": call(
        evm.button_held, M1, first=evm.IN, answers=aes.AES_BUTTON - evm.SHIFT_KEYS * WORD_BYTES),
    # ev_rets stores the mouse over a MOBLK the fast path has read already.
    "the first rectangle under the answers": call(evm.desk, M1, first=evm.IN, answers=evm.FIRST_RECT_AT),
    # ...and over the buttons' word when the buttons are asked for: the answers are ev_rets' alone.
    "the buttons' word under the third answer, the buttons asked": call(
        evm.button_held, BUTTON, button=evm.THE_BUTTON_DOWN, answers=aes.AES_BUTTON - BUTTONS * WORD_BYTES),
    # the fast path stores the buttons that answered in $c792 BEFORE the clicks in their answer word — the click
    # record's arm (a right click that came and went: the record's buttons 2, its clicks 1)...
    "the buttons that answered under the clicks' answer, a right click that came and went": call(
        evm.right_clicked, BUTTON, button=evm.THE_RIGHT_BUTTON_DOWN, answers=BUTTON_STATE - CLICKS * WORD_BYTES),
    # ...and the arm of the buttons as they are (a right press).
    "the buttons that answered under the clicks' answer, a right press": call(
        evm.right_pressed, BUTTON, button=evm.THE_RIGHT_BUTTON_DOWN, answers=BUTTON_STATE - CLICKS * WORD_BYTES),
    # with no button event asked the buttons are stored over the third answer BEFORE the waits are answered: apret
    # then leaves the rectangle's wait's high word there.
    "the buttons apret left under the third answer, a rectangle's wait come where it is queued": call(
        evm.pressed_on_the_bar, M1, first=evm.ON_THE_BAR, answers=BUTTON_STATE - BUTTONS * WORD_BYTES),
}


@functools.lru_cache(maxsize=CASES_KEPT)
def overlaid(name):
    """The overlap case `name`, run: the words under the answers may steer the attribution pass too, and say so."""
    made = OVERLAPS[name]
    answers_at = made.arguments[-1]
    under = aes.steers("the words a case laid the answers over, which the routine reads after it has stored an answer "
                       "there: inverted, it reads another machine's", (answers_at, answers_at + evm.ANSWER_WORDS * WORD_BYTES))
    return evm.run(made, also=(under,))


@pytest.mark.parametrize("name", OVERLAPS)
def test_each_word_is_read_and_stored_where_the_rom_does(name):
    """The answers laid OVER a word the routine reads or stores, over the ROM's own machines: the ORDER of its reads
    and stores."""
    overlaid(name)


# ...and six of them read back: each shows the order it is named for.
@of_the_case("the sent mark under the key's answer")
def test_the_key_answered_is_lost_under_the_mark_a_message_then_clears():
    lost = overlaid("the sent mark under the key's answer")
    assert word(lost.final, SENT_MARK) == 0 and evm.came(lost) == KEYBD | MESAG


@of_the_case("the count of button changes under the key's answer")
def test_the_key_is_stored_before_the_button_test_reads_the_count_of_changes():
    """A press, the button wanted UP: one change posted, and the buttons before it are not tried — but for the key's
    word laid over the count, which is "more than one"."""
    by_the_key = overlaid("the count of button changes under the key's answer")
    plain = evm.run(call(evm.typed_and_pressed, KEYBD | BUTTON, button=evm.THE_BUTTON_UP))
    assert evm.came(by_the_key) == KEYBD | BUTTON and evm.came(plain) == KEYBD


@of_the_case("the buttons apret left under the clicks' answer")
def test_apret_s_answer_is_stored_over_the_buttons_it_left_before_they_are_read():
    over_the_leftover = overlaid("the buttons apret left under the clicks' answer")
    assert word(over_the_leftover.final, BUTTON_STATE) == 0 != word(over_the_leftover.final, aes.AES_BUTTON)


@pytest.mark.parametrize("name, buttons, clicks", (
    ("the buttons that answered under the clicks' answer, a right click that came and went", aes.AES_PR_BUTTON, aes.AES_PR_MCLICK),
    ("the buttons that answered under the clicks' answer, a right press", aes.AES_BUTTON, aes.AES_MCLICK)))
def test_the_fast_path_stores_the_buttons_that_answered_before_their_clicks(name, buttons, clicks):
    """...so the word both are stored in ends as the CLICKS (1), not the buttons (the right: 2)."""
    final = overlaid(name).final
    assert word(final, buttons) == evm.RIGHT != word(final, clicks) == word(final, BUTTON_STATE)


@of_the_case("the buttons apret left under the third answer, a rectangle's wait come where it is queued")
def test_the_buttons_are_stored_before_the_waits_are_answered():
    """...so $c792, under the third answer, ends as what the rectangle's apret left (0), not the button that is down."""
    result = overlaid("the buttons apret left under the third answer, a rectangle's wait come where it is queued")
    assert evm.came(result) == M1 and word(result.final, aes.AES_BUTTON) == evm.LEFT
    assert word(result.final, BUTTON_STATE) == 0


def poked(made, **fields):
    return made._replace(staged=merge_pokes(made.staged, *(
        {at: struct.pack(">I" if size == LONG_BYTES else ">H", value)} for (at, size), value in fields.values())))


CDA_OF = {pd: case.long_in(BASE_IMAGE, pd + aes.PD_CDA) for pd in (SHELL, SCREEN_MANAGER)}
# The words the argument-class cases below poke: each chosen for the one test of the ROM's it tells apart.
THE_TOP_BIT_ALONE, A_NEGATIVE_INDEX = 0x8000, 0xFFF0
A_COUNT_ABOVE_ITS_LOW_BYTE, A_COUNT_WITH_ITS_TOP_BIT_SET = 0x0100, 0x8001
POKED = {
    # `cmp.l`: the running process on the bus is not the mouse's owner — the fast path's button test is skipped (the
    # wait itself is satisfied where it is queued: the same answer, through an EVB).
    "the mouse's owner with a top byte": (
        poked(evm.POLLS_FIRST["the button up, as wanted"], owner=((MOWNER, LONG_BYTES), SHELL | TAG)), BUTTON),
    # `ble`, signed: a count of changes with its top bit set is "not more than one" — the click record is not tried,
    # and a click that came and went leaves the wait for the button down unanswered.
    "a negative count of button changes": (
        poked(evm.WHILE_IT_WAS_BUSY["a click, the button wanted down"], count=((aes.AES_MTRANS, WORD_BYTES), THE_TOP_BIT_ALONE)), None),
    # `ble`, signed: a pipe's index below 0 holds no message.
    "a negative pipe index": (
        poked(evm.POLLS_FIRST["a timer of no time"]._replace(arguments=(MESAG | TIMER, 0, 0, 0, 0, MESSAGE_AT, ANSWERS_AT)),
              index=((SHELL + aes.PD_QUEUE_INDEX, WORD_BYTES), A_NEGATIVE_INDEX)), TIMER),
    # `tst.w`: a key count whose low byte is 0 is a key queued.
    "a key count above its low byte": (
        poked(call(evm.desk, KEYBD), count=((CDA_OF[SHELL] + aes.CDA_KEY_COUNT, WORD_BYTES), A_COUNT_ABOVE_ITS_LOW_BYTE)), KEYBD),
    # the key queue is the RUNNING PROCESS's own (its PD's CDA), whatever AES_GL_CDA says.
    "the current CDA another process's": (
        poked(evm.POLLS_FIRST["a key queued"], cda=((aes.AES_GL_CDA, LONG_BYTES), CDA_OF[SCREEN_MANAGER])), KEYBD),
    # ...and the other way round — the one state in which a KEY's wait is completed where it is queued: the running
    # process's own queue is empty (the fast path), the current CDA's (akbin's) holds a key. The key is apret's answer.
    "the current CDA another process's, a key in its queue": (
        poked(call(evm.the_manager_running_a_key_in_the_desk_s_queue, KEYBD),
              cda=((aes.AES_GL_CDA, LONG_BYTES), CDA_OF[SHELL])), KEYBD),
    # an event bit come that no wait holds: the key's wait takes that bit, mwait finds it come, acancel cancels the
    # wait (it is not completed) and answers nothing — and the bit, mwait's answer alone, is answered all the same.
    "an event come that no wait holds": (
        poked(call(evm.desk, KEYBD), came=((SHELL + aes.PD_EVFLG, WORD_BYTES), 1)), KEYBD),
    # `tst.w / beq`: a key count with its TOP bit set is a key queued — "not zero", never "more than none".
    "a key count with its top bit set": (
        poked(call(evm.key_queued, KEYBD), count=((CDA_OF[SHELL] + aes.CDA_KEY_COUNT, WORD_BYTES), A_COUNT_WITH_ITS_TOP_BIT_SET)), KEYBD),
    # the tick's milliseconds are READ where the AES keeps them: halved, a timer is queued for twice the ticks.
    "the tick's milliseconds halved": (
        poked(evm.NOTHING_COME["a timer"], tick=((EV["AES_GL_TICK_MS"], WORD_BYTES), evm.TICK_MS // 2)), None),
}


# The one case `savptr` does not steer (`aes_evmulti.returning`): its poked key count, inverted with every stored byte,
# is a queue too full to poll — the narrowed pass takes no trap at all.
SAVPTR_DOES_NOT_STEER = ("a key count with its top bit set",)


@functools.lru_cache(maxsize=CASES_KEPT)
def poked_ran(name):
    return evm.run(POKED[name][0], savptr_steers=name not in SAVPTR_DOES_NOT_STEER)


@pytest.mark.parametrize("name", POKED)
def test_a_field_at_the_edge_of_its_width(name):
    """ARGUMENT-CLASS CASES OVER A POKED FIELD (each a state no run of this battery leaves): the width and the sign
    the ROM reads each word with. `None`: the call blocks."""
    _made, came = POKED[name]
    result = poked_ran(name)
    assert isinstance(result, evm.Switched) if came is None else evm.came(result) == came


@of_the_case("the current CDA another process's, a key in its queue")
def test_a_key_s_wait_completed_where_it_is_queued_answers_the_key_through_apret():
    """...the second of those cases, read back: the key the desk's queue held, in the fifth answer."""
    made, _came = POKED["the current CDA another process's, a key in its queue"]
    result = poked_ran("the current CDA another process's, a key in its queue")
    assert evm.answers(result.final)[KEY] == front_key(before(made), SHELL) != 0 and evm.answers(result.final)[CLICKS] == STALE


@of_the_case("an event come that no wait holds")
def test_an_event_bit_no_wait_holds_is_answered_as_a_key_of_100():
    """A ROM FINDING, on AN ARGUMENT-CLASS MACHINE (a poked field: no run of this battery leaves an event come with
    no wait): apret, asked for an event no EVB of the process holds, answers 100 — which evnt_multi hands out as
    THE KEY. The road there is `mwait() | acancel()`: the bit is mwait's alone."""
    assert evm.answers(poked_ran("an event come that no wait holds").final)[KEY] == EV["APRET_NO_EVB"] == 100


@of_the_case("the tick's milliseconds halved")
def test_a_timer_is_divided_by_the_tick_s_milliseconds_as_the_aes_holds_them():
    made, _came = POKED["the tick's milliseconds halved"]
    timer, = taken(before(made), 1)
    assert evasync.evb_of(poked_ran("the tick's milliseconds halved").image, timer)["PARM"] == 2 * evm.A_TIMER_TICKS


# ---- A CALL THAT BLOCKED, WOKEN — ONE RETURNING RUN ON EVERY SHORE (`aes_evmulti.WAKES`: rows that switch) --------------------
# Each wake is a REGISTERED ROW (`WOKEN_ROWS`, at the foot of this file): settled from the ROM's own run through its
# dispatcher, held at Tier 1 by the twin through the host's scheduler with nothing dropped (`aes_switching.companion`),
# and on each blob by the twin through OUR dispatcher — parked by our dsptch, disp and savestate on its own stack,
# resumed inside our mwait — priced on its own cycles. Nothing lays memory under the twin.
WRITER_WOKEN = MESAG                    # what a writer's wake answers when nothing else came
WAKE_CAME = {
    "a key wakes: a key, none queued": KEYBD, "a press wakes: the button down, which is up": BUTTON,
    "a release wakes: the button up, which is down": BUTTON, "a double click wakes: a double click": BUTTON,
    "a single click wakes: a double click": BUTTON, "entering wakes: a rectangle the mouse is not in": M1,
    "leaving wakes: a rectangle the mouse is to leave": M1, "entering wakes: the second rectangle alone": M2,
    "leaving wakes: two rectangles": M1 | M2, "the ticks wake: a timer": TIMER,
    "a tick wakes: a timer of less than a tick": TIMER, "a key wakes: a key and a message": KEYBD,
    "the ticks wake: a message and a timer": TIMER, "a key wakes: a key and the buttons": KEYBD,
    "a press wakes: a key and the buttons": BUTTON, "a key and a press in one idle: a key and the buttons": KEYBD | BUTTON,
    "a press wakes: the buttons and a rectangle": BUTTON,
    "a press, then entering, in one idle: the buttons and a rectangle": BUTTON | M1,
    "a key wakes: every event": KEYBD,
    # ...the ticks that count a double click's two clicks are the timer's too:
    "a double click wakes: every event": BUTTON | TIMER,
    "leaving wakes: every event": M1 | M2, "entering wakes: every event": M1 | M2, "the ticks wake: every event": TIMER,
    "a key, a double click, leaving and the ticks in one idle: every event": KEYBD | BUTTON | M1 | M2 | TIMER,
    "a key wakes: eight bits held, a key, the buttons, two rectangles": KEYBD,
    "the ticks wake: eight bits held, a message and a timer": TIMER,
    "a release wakes: every event, the button held": BUTTON,
    "a key wakes, the sent mark set: a key and a message": KEYBD,
    "a writer wakes: a message, none in the pipe": WRITER_WOKEN,
    "a writer wakes: a message and a timer not run out": WRITER_WOKEN,
    "a writer and the press's ticks in one wake: a message and a timer": MESAG | TIMER,
    "a writer wakes: a key and a message": WRITER_WOKEN,
    "a writer wakes: every event, the timer not run out": WRITER_WOKEN,
    "a writer and the press's ticks in one wake: every event": MESAG | TIMER,
    "a writer and the press's ticks: eight bits held, a message and a timer": MESAG | TIMER,
    "a writer, a key and the press's ticks in one wake: a key, a message and a timer": KEYBD | MESAG | TIMER,
    "a writer, a key and the press's ticks in one wake: every event": KEYBD | MESAG | TIMER,
    # ...the mouse is the WRITER's while its menu is down: the desk's rectangle waits are not posted in that wake.
    "a writer and the mouse into the rectangle: a rectangle and a message": WRITER_WOKEN,
    "a writer, a key, the mouse, the press's ticks: every event": KEYBD | MESAG | TIMER,
    "a writer, the desk waiting for the bar's rectangle too": WRITER_WOKEN,
    "a writer, then the mouse away: both rectangles and a message": WRITER_WOKEN,
    evm.A_KEY_BEFORE_THE_WRITER_WRITES: KEYBD,
    evm.A_WRITER_AND_A_KEY: KEYBD | MESAG,
    evm.A_KEY_WHILE_THE_MANAGER_STANDS_WOKEN: KEYBD,
    evm.A_KEY_AND_THE_MOUSE_ONTO_THE_BAR: KEYBD,
}
# THE SCREEN MANAGER'S TURNS in a writer's wake, READ OFF THE ROM'S OWN RUN (each case's premise): entered at the
# title, at the item and at the press — and once more after its write where the write is what wakes the desk; three
# where the press's ticks had woken the desk before the press woke it; where a key IN THE PRESS'S IDLE wakes the desk
# after the press (`aes_evmulti`: last in, first out) the desk runs before its third turn; a key polled AFTER the
# press's forks ran wakes the desk behind the manager, which has its third turn — and writes — first; and a key polled
# after the first move's leaves the manager the one turn that move woke it for.
ITS_TURNS = {name: 4 for name in evm.WAKES_BY_A_WRITER} | {
    name: 3 for name, came in WAKE_CAME.items() if name in evm.WAKES_BY_A_WRITER and came & TIMER} | {
    evm.A_KEY_BEFORE_THE_WRITER_WRITES: 2, evm.A_WRITER_AND_A_KEY: 3, evm.A_KEY_WHILE_THE_MANAGER_STANDS_WOKEN: 1}
tier3 = bench_tier3


def premise_of(name):
    """THE WAKE `name` AS ITS ROW'S PREMISE (`aes_switching.Premise`), out of the tables above: every delivery at the
    idle — or the poll — the wake names, as many idles as it names, the desk the caller, the screen manager's turns
    and then the desk, the events of WAKE_CAME answered."""
    wake = evm.WAKES[name]
    return switching.Premise(tuple(sorted(wake.at_idle)), len(wake.at_idle), SHELL,
                             (SCREEN_MANAGER,) * ITS_TURNS.get(name, 0) + (SHELL,), WAKE_CAME[name],
                             tuple(sorted(wake.at_polls or {})))


Woke = collections.namedtuple("Woke", "before after came")


@functools.lru_cache(maxsize=CASES_KEPT)
def through_the_dispatcher(name):
    """THE WAKE `name`, RUN AND HELD AT TIER 1 (`aes_switching.companion`): the twin, blocked and woken through the
    host's scheduler — a foreign process's turn the ROM's own code — answers what the ROM's run through its own
    dispatcher answers and leaves ITS image, every byte outside the run's own stack (a QPB's address in a freed EVB
    vetted). A `Woke`: the machine the call was made over, THE TWIN'S OWN IMAGE where it returned
    (`CompanionRun.image`: a test that reads an answer back reads what the C stored, whatever the companion left
    out) and the events answered."""
    held = switching.companion(WOKEN_ROWS[name])
    return Woke(make_image(held.staged), held.image, held.answer & aes.WORD_MASK)


def where_the_tail_begins(name):
    """The ROM's memory where the woken process of the wake `name` — resumed, mwait returned — calls acancel: what
    the tail of ev_multi finds. (Another process's own ev_multi reaches acancel too: the row's process's is kept.)"""
    row, found = WOKEN_ROWS[name], []
    made = switching.settled(row)

    def at_acancel(memory):
        if evasync.running(memory) & aes_event.OS_BUS_ADDR_MASK == made.switches.process:
            found.append(bytes(memory[:addrs.ST_RAM_BYTES]))
    watch = switching.the_rom_s(made.switches, addrs.AES_ROM_EV_MULTI, observing={addrs.AES_ROM_ACANCEL: at_acancel})
    rom_bench.watched_original(make_image(made.pokes), addrs.AES_ROM_EV_MULTI, watch)
    rom_bench.vet_the_run_just_made(f"the ROM's replay of {name}, observed where the tail begins")
    resumed, = found
    return resumed


def test_every_wake_s_events_are_stated_and_every_wake_is_a_registered_row_that_switches():
    assert WAKE_CAME.keys() == evm.WAKES.keys() == WOKEN_ROWS.keys() == PRICED.keys() == WHOLE_RUN.keys()
    registered = {name for name, held in aes_event.SWITCHING_ROWS.items() if held.row.name == EV_MULTI}
    assert registered == {switching.row_name(row) for row in WOKEN_ROWS.values()}
    assert len(evm.WAKES_BY_AN_INTERRUPT) == 29 and len(evm.WAKES_BY_A_WRITER) == 13 and len(evm.WAKES_AT_A_POLL) == 2


@pytest.mark.parametrize("name", evm.WAKES)
def test_the_rom_s_own_run_of_a_wake_is_what_its_name_says(name):
    """THE PREMISE, on the ROM's run through its own dispatcher over the row's settled machine: the call BLOCKS (the
    run idles), every delivery is taken at the idle — or the poll that is no idle — the case names, the dispatcher
    enters the screen manager as often as the case says and then the process that made the call — and its routine
    returns the events of the name. The row carries that run's deliveries (`aes_switching.vet_the_premise`: the
    settling changed nothing an interrupt reads or writes)."""
    the_rom_s = switching.vet_the_premise(WOKEN_ROWS[name], premise_of(name))
    assert the_rom_s.idles >= 1 and the_rom_s.polls > the_rom_s.idles, "it blocks: the machine idles, and polls on"


@pytest.mark.parametrize("name", evm.WAKES)
def test_a_call_blocked_and_woken_through_the_scheduler_returns_as_the_rom_s_does(name):
    """TIER 1 OF A WAKE (`through_the_dispatcher`): the whole call in C — the waits queued, the block, mwait's return, the cancel of
    the waits that did not come, ev_rets and the answers of those that did — through the host's scheduler: the events
    answered and the whole image are the ROM's where its routine returns, nothing left out but the run's own stack.
    WHAT THESE DO NOT HOLD, said: the OR of acancel's ANSWER into what arrived (`arrived |= aes_acancel(...)`,
    `src/aes/evmulti.c`). In every woken machine a completed EVB's bit is in PD_EVFLG — mwait's answer — and
    acancel's `kept` is those bits again: a twin that threw acancel's answer away passes all of them, as one that
    threw mwait's away passes these and dies only by the labelled case `an event come that no wait holds`.
    EQUIVALENT ON EVERY MACHINE THE ROM MAKES — NOCANCEL without COMPLETE never stands between two calls (`pdpipe.c`
    sets it and completes the EVB in one routine) — and UNPINNED: what would tell the two apart is an EVB of the
    mask marked "being served" and not complete at the tail, an argument-class machine no case here stages."""
    assert through_the_dispatcher(name).came == WAKE_CAME[name]


@pytest.mark.parametrize("name", evm.WAKES)
def test_a_woken_call_is_parked_and_resumed_by_our_own_dispatcher_on_both_blobs(name, blob):
    """THE SECOND DIFFERENTIAL OF THE REAL SWITCH, on each blob: the twin blocks in OUR mwait, our dsptch, disp and
    savestate park GCC's frame on the process's own stack, the deliveries land at the idles (and the polls) the ROM's
    run took them at, and the process is resumed inside our mwait — by our switchto, or, after the screen manager's
    turns, by the ROM's dispatcher on both shores (ONE foreign window, equal to the cycle, no cycle of our build
    inside). The image the ROM's but for the row's drops, the answer, every callee-saved register back, the whole
    run's cycles pinned — and, where a message was waited for, the wait SEEN to name the ROM's QPB in the twin's own
    frame while it was parked (`aes_switching.vet_our_qpbs`: it is through that frame another process's write lands)."""
    _measured, watch, foreign = switching.vet_on_a_blob(blob, WOKEN_ROWS[name], premise_of(name), PRICED[name].windows,
                                                        WHOLE_RUN[name])
    assert foreign.windows == bool(ITS_TURNS.get(name, 0))
    assert bool(watch.qpbs_seen) == bool(evm.WAKES[name].call.arguments[0] & MESAG)


@pytest.mark.parametrize("name", evm.WAKES)
def test_the_table_prices_a_woken_call_on_its_own_cycles(name):
    """WHAT THE TABLE READS (`aes_switching.vet_the_table_s_price`): the row's OWN cycles — ours at the blob's PCs, the
    ROM's in the AES's text less the screen manager's window — and THE CALLER'S OWN where its forks call a rebound
    entry, both pinned and both under the bar with their thunks; the window itself, in neither column. A row that
    moves says why."""
    switching.vet_the_table_s_price(WOKEN_ROWS[name], PRICED[name])


def test_every_wake_by_an_interrupt_is_of_a_call_held_at_dsptch():
    """THE HALF BEFORE THE BLOCK HAS A SURFACE OF ITS OWN (`aes_event.switches_where_the_rom_does`: it says WHICH half
    of a blocking call differs): for an interrupt's wake the very `Call` of NOTHING_COME (or that call with the mark
    staged: below)."""
    at_dsptch = {id(made) for made in evm.NOTHING_COME.values()}
    assert all(id(wake.call) in at_dsptch for name, wake in evm.WAKES_BY_AN_INTERRUPT.items() if "the sent mark set" not in name)


@pytest.mark.parametrize("name", [name for name, wake in evm.WAKES.items() if wake.call not in evm.NOTHING_COME.values()])
def test_a_wake_over_a_machine_of_its_own_is_held_at_dsptch_too(name):
    """...and a writer's case — its machine has the mark staged, some a frame no blocking case has — blocks as the
    ROM's does over that very machine."""
    assert isinstance(evm.run(evm.WAKES[name].call), evm.Switched)


KINDS_OF_DROP = {       # what a woken row drops at Tier 3, by the events its call asks for
    "the Line-F mask word": lambda flags: True, "the caller's saved context": lambda flags: True,
    "the dispatcher's stack": lambda flags: True,
    # adelay's and tchange's bracket: the call queues a timer
    "spl7_save's SR save word": lambda flags: bool(flags & TIMER),
    # the message wait's EVB, freed as it is — served or cancelled
    "a QPB's address left in a freed EVB": lambda flags: bool(flags & MESAG),
}


def _kind_of(drop, uda):
    lo, hi, why = drop
    windows = {"the Line-F mask word": aes.LINE_F_MASK_WINDOW, "the caller's saved context": aes_switch.uda_context_drop(uda),
               "the dispatcher's stack": aes_switch.DISPATCHER_STACK_DROP,
               "spl7_save's SR save word": aes_event.sr_drops(aes.AES_SR_SPL)}
    if why == aes_event.QPB_ADDRESS_WHY:
        return "a QPB's address left in a freed EVB"
    kind, = (kind for kind, ((low, high, _why),) in windows.items() if low <= lo and hi <= high)
    return kind


@pytest.mark.parametrize("name", evm.WAKES)
def test_what_a_woken_row_drops_is_what_differs_by_nature_and_nothing_else(name):
    """THE DROPS ARE NAMED, NOT BLANKET — and fewer than the tail-only compare left out: no frame of the ROM's own
    process stack, no window dropped whole. A woken row drops, each cut to the bytes the ROM's run stored: the Line-F
    mask word, the caller's saved context and the dispatcher's stack (what a switch is), the mask bracket's save
    word where the call queues a timer, and the one longword of a freed EVB that holds the message wait's QPB
    address where it asks for a message — the QPB the twin's own (the running process's, sixteen bytes, the buffer)."""
    row = WOKEN_ROWS[name]
    made, flags = switching.settled(row), row.arguments[0]
    uda = aes_event.uda_of(SHELL, make_image(made.pokes))
    assert sorted({_kind_of(drop, uda) for drop in made.drops}) == sorted(kind for kind, asked in KINDS_OF_DROP.items() if asked(flags))
    assert list(made.qpbs.values()) == [(evm.SHELL_PID, evm.MESSAGE_BYTES, MESSAGE_AT)] * bool(flags & MESAG)
    assert all(hi - lo == LONG_BYTES for lo, hi, why in made.drops if why == aes_event.QPB_ADDRESS_WHY)


@of_the_case("a key wakes: a key, none queued")
def test_a_key_wait_woken_through_the_dispatcher_answers_the_key_it_was_posted():
    """evremove kept the key in the wait's EVB; apret answers it into the fifth word, and nothing stays queued."""
    woken = through_the_dispatcher("a key wakes: a key, none queued")
    answered = evm.answers(woken.after)
    assert answered[KEY] == aes_event.RETURN_KEY << 8 | ord("\r") and answered[CLICKS] == STALE
    assert evasync.evlist(woken.after, SHELL) == [] and events(woken.after) == (0, 0, 0)
    assert sorted(evasync.free_evbs(woken.after)) == sorted(evasync.free_evbs(woken.before))


@pytest.mark.parametrize("name, buttons, clicks", (
    ("a press wakes: the button down, which is up", evm.LEFT, 1), ("a release wakes: the button up, which is down", 0, 1),
    ("a double click wakes: a double click", evm.LEFT, 2), ("a single click wakes: a double click", evm.LEFT, 1),
    ("a double click wakes: every event", evm.LEFT, 2)))
def test_a_button_wait_woken_through_the_dispatcher_answers_its_clicks_and_the_buttons_apret_left(name, buttons, clicks):
    """The clicks are apret's answer (its low word), the buttons its high word — left in $c792, read after."""
    answered = evm.answers(through_the_dispatcher(name).after)
    assert (answered[BUTTONS], answered[CLICKS]) == (buttons, clicks) and answered[KEY] == STALE


@of_the_case("leaving wakes: a rectangle the mouse is to leave")
def test_a_mouse_wait_woken_through_the_dispatcher_leaves_its_rectangle_s_width_where_the_buttons_are_handed_out():
    """THE ROM FINDING's other half, made by the twin itself: the rectangle's apret parks the wait's high word — the
    rectangle's WIDTH — in $c792. This call answers the real buttons (no button event was asked for); the NEXT one
    that asks for the buttons and gets another event hands the width out."""
    woken = through_the_dispatcher("leaving wakes: a rectangle the mouse is to leave")
    assert word(woken.after, BUTTON_STATE) == evm.ROUND_THE_MOUSE[2] != 0 and evm.answers(woken.after)[BUTTONS] == 0
    assert evm.answers(woken.after)[:Y + 1] == list(mouse(woken.after)) == list(evasync.OUTSIDE)


@of_the_case("a press, then entering, in one idle: the buttons and a rectangle")
def test_of_two_waits_woken_in_one_idle_the_buttons_are_read_before_the_rectangle_s_wait_is_answered():
    """Two waits come in one wake: the buttons' apret leaves the button in $c792, which is stored in the third answer
    BEFORE the rectangle's apret leaves its width there."""
    woken = through_the_dispatcher("a press, then entering, in one idle: the buttons and a rectangle")
    assert evm.answers(woken.after)[BUTTONS] == evm.LEFT and word(woken.after, BUTTON_STATE) == evm.ELSEWHERE[2]


@of_the_case("a writer wakes: a message, none in the pipe")
def test_the_screen_manager_s_own_message_wakes_the_call_and_the_tail_clears_the_sent_mark():
    """The screen manager's own appl_write — its menu's selection — served the parked wait THROUGH THE QPB OF THE
    WAITING CALL'S FRAME: the message is in the buffer where the process resumes, its pipe empty, the mark as it was
    staged. The tail answers the message's wait and — the one place on the wait path — clears the control manager's
    mark."""
    resumed, woken = where_the_tail_begins("a writer wakes: a message, none in the pipe"), through_the_dispatcher("a writer wakes: a message, none in the pipe")
    assert bytes(resumed[MESSAGE_AT:MESSAGE_AT + evm.MESSAGE_BYTES]) == evlib.A_MESSAGE and pipe(resumed) == b""
    assert bytes(woken.before[MESSAGE_AT:MESSAGE_AT + evm.MESSAGE_BYTES]) == evm.STALE_MESSAGE[MESSAGE_AT]
    assert word(resumed, SENT_MARK) == 1 and word(woken.after, SENT_MARK) == 0
    assert evasync.evlist(woken.after, SHELL) == [] and evasync.wait_list(woken.after, SHELL + aes.PD_QUEUE_READERS) == []


@of_the_case("a key wakes, the sent mark set: a key and a message")
def test_a_call_woken_by_a_key_with_no_message_come_leaves_the_sent_mark():
    """...a message asked for, a key come: the message's wait is cancelled, and the mark stays."""
    woken = through_the_dispatcher("a key wakes, the sent mark set: a key and a message")
    assert word(woken.after, SENT_MARK) == 1 and evasync.wait_list(woken.after, SHELL + aes.PD_QUEUE_READERS) == []


@of_the_case(evm.A_KEY_BEFORE_THE_WRITER_WRITES)
def test_a_key_typed_with_the_press_wakes_the_desk_before_the_writer_writes():
    """A ROM FACT OF THE REAL CHAIN, pinned (`aes_evmulti`: the woken list is last in, first out, and a key that
    arrives in the press's own idle is that idle's last fork): Return typed in the idle the press is delivered at, a
    key and a message asked for. The press wakes the screen manager, the key then the desk — which runs FIRST: it
    answers the key alone, its message wait CANCELLED, the buffer and the mark untouched, while the screen manager —
    its menu's selection not yet sent — has had two turns, not four. TRUE OF A KEY IN THAT IDLE, AND NO FURTHER: one
    that arrives a poll later is answered WITH the message (the next test)."""
    woken = through_the_dispatcher(evm.A_KEY_BEFORE_THE_WRITER_WRITES)
    assert woken.came == KEYBD and evm.answers(woken.after)[KEY] == aes_event.RETURN_KEY << 8 | ord("\r")
    assert bytes(woken.after[MESSAGE_AT:MESSAGE_AT + evm.MESSAGE_BYTES]) == evm.STALE_MESSAGE[MESSAGE_AT]
    assert word(woken.after, SENT_MARK) == 1 and evasync.wait_list(woken.after, SHELL + aes.PD_QUEUE_READERS) == []
    assert word(woken.after, SCREEN_MANAGER + aes.PD_STAT) != aes.PD_STAT_WAITING, "the screen manager is ready: its press came"


def _stood_at_the_poll(name):
    """`(the process ready, the one woken, the forks queued)` where the ROM's own run of the wake `name` took its
    delivery at a poll that is no idle (`aes_switch.what_idle_tests`, kept with the delivery's `found`)."""
    (found, _wrote), = switching.settled(WOKEN_ROWS[name]).switches.at_polls.values()
    return (int.from_bytes(found[aes.AES_RLR], "big"), int.from_bytes(found[aes.AES_DRL], "big"),
            int.from_bytes(found[aes.AES_FORK_COUNT], "big"))


@of_the_case(evm.A_WRITER_AND_A_KEY)
def test_a_key_polled_after_the_press_s_forks_ran_is_answered_with_the_writer_s_message():
    """A KEY AND A MESSAGE IN ONE WAKE, NOTHING ELSE ($11) — the wake the case above does not make, made by the same
    chain with the key ONE POLL LATER: the press's forks have run, the screen manager stands WOKEN (not ready yet,
    nothing queued: the premise, read off the ROM's run) and idle polls the keyboard again before it moves it. The
    key's wake of the desk is then behind the manager's: the manager has its third turn and writes, and the desk
    answers both — the key in the fifth word, the message in its buffer, the mark cleared, no wait of its left."""
    assert _stood_at_the_poll(evm.A_WRITER_AND_A_KEY) == (0, SCREEN_MANAGER, 0)
    woken = through_the_dispatcher(evm.A_WRITER_AND_A_KEY)
    assert woken.came == KEYBD | MESAG and evm.answers(woken.after)[KEY] == aes_event.RETURN_KEY << 8 | ord("\r")
    assert bytes(woken.after[MESSAGE_AT:MESSAGE_AT + evm.MESSAGE_BYTES]) == evlib.A_MESSAGE
    assert word(woken.before, SENT_MARK) == 1 and word(woken.after, SENT_MARK) == 0
    assert evasync.evlist(woken.after, SHELL) == [] and evasync.wait_list(woken.after, SHELL + aes.PD_QUEUE_READERS) == []


@of_the_case(evm.A_KEY_WHILE_THE_MANAGER_STANDS_WOKEN)
def test_a_key_polled_by_our_own_idle_while_the_manager_stands_woken_is_answered_after_its_turn():
    """THE SAME POLL ON OUR OWN DISPATCHER (the first move's: no process has run since the desk blocked, so the idle
    that polls is the row's own build's on a blob and the C scheduler's on the host). The manager stands woken where
    the key is laid — the delivery is REFUSED on a shore whose idle moved the woken before it polled — it has its
    one turn, and the desk answers the key alone; the menu the manager dropped is its own affair."""
    assert _stood_at_the_poll(evm.A_KEY_WHILE_THE_MANAGER_STANDS_WOKEN) == (0, SCREEN_MANAGER, 0)
    woken = through_the_dispatcher(evm.A_KEY_WHILE_THE_MANAGER_STANDS_WOKEN)
    assert woken.came == KEYBD and evm.answers(woken.after)[KEY] == aes_event.RETURN_KEY << 8 | ord("\r")
    assert evasync.wait_list(woken.after, SHELL + aes.PD_QUEUE_READERS) == [] and evasync.evlist(woken.after, SHELL) == []


@of_the_case(evm.A_KEY_AND_THE_MOUSE_ONTO_THE_BAR)
def test_two_processes_woken_in_one_idle_are_both_moved_to_the_ready_list_in_one_pass():
    """THE MOVE WAKES THE SCREEN MANAGER, THE KEY THE DESK, in one idle: forker runs both forks, and idle moves BOTH
    woken processes before the dispatcher enters one — the desk first (the woken list is last in, first out), the
    manager READY behind it, nothing left woken. (An idle that moved one a turn would leave the manager on the woken
    list where the call returns.)"""
    woken = through_the_dispatcher(evm.A_KEY_AND_THE_MOUSE_ONTO_THE_BAR)
    assert woken.came == KEYBD and case.long_in(woken.after, aes.AES_DRL) == 0
    assert evasync.running(woken.after) & aes_event.OS_BUS_ADDR_MASK == SHELL
    assert case.long_in(woken.after, SHELL + aes.PD_LINK) & aes_event.OS_BUS_ADDR_MASK == SCREEN_MANAGER
    assert word(woken.after, SCREEN_MANAGER + aes.PD_STAT) == aes.PD_STAT_READY


@of_the_case("a writer and the press's ticks in one wake: a message and a timer")
def test_a_message_and_a_timer_come_in_one_wake_through_the_menu_are_answered_message_first():
    """Both waits come — the press's ticks run the timer out, then the writer writes, before the dispatcher runs the
    process again: each apret puts its EVB back at the head of the free list, so the list begins with the timer's,
    then the message's."""
    woken = through_the_dispatcher("a writer and the press's ticks in one wake: a message and a timer")
    message, timer = taken(woken.before, 2)
    assert evasync.free_evbs(woken.after)[:2] == [timer, message] and evasync.evlist(woken.after, SHELL) == []


@of_the_case("a writer wakes: a message and a timer not run out")
def test_a_press_brings_the_ticks_of_its_click_count_and_a_longer_timer_has_not_come():
    """THE PREMISE OF "THE PRESS'S TICKS" (`aes_evmulti`): the machine counts a double-click wait (AES_GL_BPEND), so
    the menu's press opens a click count of AES_GL_DCLICK ticks and runs it out — more ticks than A_TIMER_MS, fewer
    than A_LONG_TIMER_MS: the long timer's wait is CANCELLED, its EVB freed, where the short one's is answered."""
    woken = through_the_dispatcher("a writer wakes: a message and a timer not run out")
    click_ticks = word(woken.before, aes.AES_GL_DCLICK)
    assert word(woken.before, BPEND) and evm.A_TIMER_TICKS <= click_ticks < evm.A_LONG_TIMER_MS // evm.TICK_MS
    assert evasync.wait_list(woken.after, EV["AES_DELAY_LIST"]) == [] and evasync.evlist(woken.after, SHELL) == []


@of_the_case("a key wakes: every event")
def test_the_waits_that_did_not_come_are_cancelled_after_the_wake():
    """Six waits queued, the key's come: the five others are taken off their lists and freed — the double-click
    wait's count left as it stands (the lists' finding)."""
    woken = through_the_dispatcher("a key wakes: every event")
    image, final = woken.before, woken.after
    cda = case.long_in(final, aes.AES_GL_CDA)
    assert sorted(evasync.free_evbs(final)) == sorted(evasync.free_evbs(image)) and evasync.evlist(final, SHELL) == []
    assert all(evasync.wait_list(final, at) == [] for at in (
        EV["AES_DELAY_LIST"], SHELL + aes.PD_QUEUE_READERS, cda + aes.CDA_KEYBOARD_WAIT, cda + aes.CDA_BUTTON_WAIT,
        cda + aes.CDA_MOUSE_WAIT))
    assert events(final) == (0, 0, 0) and word(final, BPEND) == word(image, BPEND) + 1


@of_the_case("a writer and the press's ticks: eight bits held, a message and a timer")
def test_event_bits_above_the_low_byte_woken_through_the_menu_are_answered_as_words():
    """AN ARGUMENT-CLASS MACHINE (the ROM's own iasync, eight waits of no kind): the message's and the timer's waits
    hold the bits $100 and $200; both come, both answered, the eight still held."""
    name = "a writer and the press's ticks: eight bits held, a message and a timer"
    assert events(where_the_tail_begins(name))[2] == THE_NINTH_AND_TENTH_BITS
    assert events(through_the_dispatcher(name).after) == (EIGHT_BITS_HELD, 0, 0)


# ---- no word an interrupt writes ------------------------------------------------------------------------------------------
# THE AUDIT, AS A TEST. A word an interrupt also writes must be counted and tested IN MEMORY, as the ROM does
# (`m68k_idioms.h`); ev_multi's own instructions touch NONE — chkkbd, forker and the waits do, each held by its own
# battery — and the twin's source names exactly the globals the ROM's routine names.
GEMBSS = range(0x8900, 0xCA00)          # the AES's globals (`aes/aes.h`)
THE_ROM_S_GLOBALS = {"AES_RLR", "AES_GL_MOWNER", "AES_MTRANS", "AES_PR_BUTTON", "AES_EV_BUTTON_STATE", "AES_PR_MCLICK",
                     "AES_BUTTON", "AES_MCLICK", "AES_GL_TICK_MS", "AES_CTL_MESSAGE_SENT"}
AN_INTERRUPT_WRITES = {     # the fork queue's head, tail, count and posted byte; the click counter; the buttons as last
    aes.AES_FORK_HEAD, aes.AES_FORK_TAIL, aes.AES_FORK_COUNT, aes.AES_FORK_POSTED, aes.AES_GL_CLICK_TICKS,      # seen;
    aes.header_constants("evinput.h")["AES_GL_BCLICK"], aes.header_constants("evinput.h")["AES_GL_BTRUE"],     # the tick's
    aes.header_constants("evinput.h")["AES_GL_BDESIRED"], aes.AES_TIMER_COUNTDOWN, aes.AES_TIMER_ELAPSED, BPEND}    # two longs
EVMULTI_C = Path(__file__).resolve().parents[1] / "src/aes/evmulti.c"
# ...the constants of every header the twin includes beside the door's own (`aes.CONSTANTS`).
INCLUDED = ("apmsg.h", "evasync.h", "evfork.h", "evinput.h", "evlib.h", "evmulti.h", "evwait.h", "fmlib.h", "pdpipe.h",
            "strings.h", "wmupdate.h")
EVERY_AES_HEADER = {**aes.CONSTANTS, **{name: value for header in INCLUDED
                                        for name, value in aes.header_constants(header).items()}}


def globals_named_by_the_rom_s_routine():
    """Every absolute long operand of ev_multi's own instructions that is an address of the AES's globals: read off
    the ROM's text a word at a time (an instruction's operand is word-aligned)."""
    text = BASE_IMAGE[addrs.AES_ROM_EV_MULTI:addrs.AES_ROM_EV_MULTI_RETURN]
    longs = {int.from_bytes(text[at:at + LONG_BYTES], "big") for at in range(0, len(text) - LONG_BYTES + 1, WORD_BYTES)}
    return {value for value in longs if value in GEMBSS}


def test_ev_multi_s_own_instructions_touch_no_word_an_interrupt_writes():
    named = globals_named_by_the_rom_s_routine()
    assert named == {EVERY_AES_HEADER[name] for name in THE_ROM_S_GLOBALS} and not named & AN_INTERRUPT_WRITES


def test_the_twin_names_the_globals_the_rom_s_routine_names_and_no_other():
    """...its source's `AES_*` names that are addresses of the AES's globals, comments aside."""
    code = re.sub(r"/\*.*?\*/", "", EVMULTI_C.read_text(), flags=re.DOTALL)
    included = set(re.findall(r'#include "aes/(\w+\.h)"', code))
    assert included - {"aes.h", "evdoor.h", "gsx.h"} == set(INCLUDED), "the headers the names below are read from"
    names = set(re.findall(r"\bAES_[A-Z0-9_]+\b", code))
    assert all(name in EVERY_AES_HEADER or name.startswith("AES_EV_MULTI_") for name in names), names - EVERY_AES_HEADER.keys()
    assert {name for name in names if EVERY_AES_HEADER.get(name, 0) in GEMBSS} == THE_ROM_S_GLOBALS


# ---- the registry: Tier 3's rows -----------------------------------------------------------------------------------------
# A CALL THAT BLOCKS IS A ROW WHERE IT IS WOKEN — a row that switches (`WOKEN_ROWS`, at the foot of this file); one
# nothing wakes has no run that returns, and is held at dsptch (Tier 1).
# EVERY RETURNING CALL of the tables was priced as a row would be; each SHAPE's worst is registered, the dearest
# first. THE ROUTINE'S WORST is the fork queue full of moves (0.87; 0.92 with the glue): the ratio climbs with the
# entries forker runs — one move 0.81, three 0.83, five 0.84, fifteen 0.87.
# THE PRESS FAMILY — a press, a click, a double click, a right press, a release queued by the ROM's button glue
# before the call, 0.68..0.82 — is priced since Tier 3 opens no window at an entry the build has rebound: the ROM's
# bchange, under the ROM's forker, reaches post_button (a rebound entry) by its Line-F call word, where our bchange
# calls post_button's core — an arrival on one shore and none on the other, which rebinding ev_multi itself changes
# on neither.
# Measured and left out, none its shape's worst: a key 0.71 (three queued, Alt-=, round the ring: the same); the
# buttons 0.71..0.72 (the screen manager's 0.72); a rectangle 0.71..0.73; a message 0.61..0.65; a key typed and asked
# for 0.64; a move onto the bar with the buttons asked 0.68; the waits come where they are queued 0.65..0.68; the
# screen manager's own call 0.69; a click with either button wanted not up 0.81 (the click's own row's shape).
# THE TWO ROWS WHOSE MESSAGE WAIT IS QUEUED AND CANCELLED are the only runs of the wait path's QPB — a local of GCC's
# frame handed on by its address — on the 68000 build: the address stays in the freed EVB, another longword on each
# shore by nature, dropped by name and vetted (`aes_event.register_row`).
ROWS = (
    ("the fork queue full of moves run while the process was busy, a timer of no time",
     "the fork queue full of moves, a timer of no time"),
    ("the left held, the right clicked while the process was busy: the click record's buttons",
     "the left held, the right clicked: the left wanted down"),
    ("a click that came and went while the process was busy, the button wanted down", "a click, the button wanted down"),
    ("a press while the process was busy, then the mouse moved away", "a press, then the mouse moved away"),
    ("a right press while the process was busy", "a right press"),
    ("a release while the process was busy", "a release"),
    ("a press while the process was busy", "a press"),
    ("a double click while the process was busy", "a double click"),
    ("a click that came and went while the process was busy, the button wanted up", "a click, the button wanted up"),
    ("a timer of no time, a key asked for and not come", "a timer of no time, a key not come"),
    ("a timer of no time", "a timer of no time"),
    ("the second rectangle alone", "the second rectangle alone"),
    ("a key queued", "a key queued"),
    ("the button up, as wanted", "the button up, as wanted"),
    ("both rectangles", "both rectangles"),
    ("a message, the pipe full", "the pipe full"),
    ("a message in the pipe", "a message in the pipe"),
    ("a key typed while the process was busy, and not asked for", "a key typed and not asked for"),
    ("every event come at once", "every event come at once"),
    ("a key typed and a press while the process was busy", "a key typed and a press"),
    ("the mouse moved onto the bar: its rectangle's wait come where it is queued", "the mouse moved onto the bar, to enter it"),
    ("a rectangle's wait come where it is queued", "on the bar: the second rectangle"),
    ("the buttons' wait come where it is queued", "on the bar: the button up as wanted"),
    ("three waits come where they are queued, a key's and a timer's cancelled",
     "on the bar: three come at once, a key's and a timer's waits cancelled"),
    ("three waits come where they are queued, a message's wait among the cancelled, eight event bits held",
     "on the bar, eight event bits held (the ROM's iasync): three come at once"),
    ("three waits come where they are queued, a message's wait among the cancelled",
     "on the bar: every event asked, three come at once"),
)
THROUGH_LINE_F = "a key queued"


def _registered():
    for label, name in ROWS:
        made = evm.RETURNING[name]
        evm.register(label, made.arguments, evm.machine_of(made))
    made = evm.RETURNING[THROUGH_LINE_F]
    evm.register("its caller's call", made.arguments, evm.machine_of(made), through_line_f=True)


_registered()


# ---- the registry: the rows that switch (`aes_evmulti.WAKES`) ---------------------------------------------------------------
# EVERY WAKE IS A ROW (`aes_switching.register`): the table, the sweeps, the companion's case and STATUS's pin pick
# it up. PRICED (`aes_switching.Priced`): what the table prices each on (`tier3.measure`, the shipped blob) — each
# shore's OWN cycles (ours, the ROM's: the screen manager's window in neither), THE CALLER'S OWN and the calls of
# rebound entries it is net of where the run makes one (ELEVEN rows: bchange's post_button under our forker, as the
# press family's rows above; ONE_COUNT for the rest), and the row's foreign window. Own 0.65..0.72, 0.68..0.77 with
# the thunks: the dispatcher's `.S` is the ROM's bytes less its Line-F traps, so a switch pulls a row DOWN.
# WHOLE_RUN: the second differential's own measurement on each blob (`aes_switching.measured_on`), the ROM's cycles
# and ours net of the entry both share. A row that moves says why.
Premise, Priced, NO_WINDOW, ONE_COUNT = switching.Premise, switching.Priced, switching.NO_WINDOW, (None, None)
BENCH, SHIPPED = "bench", "bench_shipped"
PRICED = {
    "a key wakes: a key, none queued":
        Priced((14670, 21704), *ONE_COUNT, NO_WINDOW),
    "a press wakes: the button down, which is up":
        Priced((16786, 24928), (15256, 21578), 1, NO_WINDOW),
    "a release wakes: the button up, which is down":
        Priced((16080, 23920), (14550, 20570), 1, NO_WINDOW),
    "a double click wakes: a double click":
        Priced((16876, 24992), (15284, 21596), 1, NO_WINDOW),
    "a single click wakes: a double click":
        Priced((18134, 26274), (16274, 22480), 2, NO_WINDOW),
    "entering wakes: a rectangle the mouse is not in":
        Priced((19754, 27396), *ONE_COUNT, NO_WINDOW),
    "leaving wakes: a rectangle the mouse is to leave":
        Priced((19886, 27562), *ONE_COUNT, NO_WINDOW),
    "entering wakes: the second rectangle alone":
        Priced((19786, 27420), *ONE_COUNT, NO_WINDOW),
    "leaving wakes: two rectangles":
        Priced((26108, 37524), *ONE_COUNT, NO_WINDOW),
    "the ticks wake: a timer":
        Priced((15196, 21698), *ONE_COUNT, NO_WINDOW),
    "a tick wakes: a timer of less than a tick":
        Priced((15006, 21508), *ONE_COUNT, NO_WINDOW),
    "a key wakes: a key and a message":
        Priced((17972, 27466), *ONE_COUNT, NO_WINDOW),
    "the ticks wake: a message and a timer":
        Priced((18522, 27460), *ONE_COUNT, NO_WINDOW),
    "a key wakes: a key and the buttons":
        Priced((17976, 27562), *ONE_COUNT, NO_WINDOW),
    "a press wakes: a key and the buttons":
        Priced((19422, 29170), (17892, 25820), 1, NO_WINDOW),
    "a key and a press in one idle: a key and the buttons":
        Priced((21606, 33358), (20076, 30008), 1, NO_WINDOW),
    "a press wakes: the buttons and a rectangle":
        Priced((20824, 31080), (19294, 27730), 1, NO_WINDOW),
    "a press, then entering, in one idle: the buttons and a rectangle":
        Priced((25948, 38168), (24418, 34818), 1, NO_WINDOW),
    "a key wakes: every event":
        Priced((33810, 51490), *ONE_COUNT, NO_WINDOW),
    "a double click wakes: every event":
        Priced((37378, 56750), (35822, 53348), 1, NO_WINDOW),
    "leaving wakes: every event":
        Priced((39578, 58940), *ONE_COUNT, NO_WINDOW),
    "entering wakes: every event":
        Priced((39578, 58940), *ONE_COUNT, NO_WINDOW),
    "the ticks wake: every event":
        Priced((33686, 50908), *ONE_COUNT, NO_WINDOW),
    "a key, a double click, leaving and the ticks in one idle: every event":
        Priced((47180, 72062), (45624, 68660), 1, NO_WINDOW),
    "a key wakes: eight bits held, a key, the buttons, two rectangles":
        Priced((29900, 43172), *ONE_COUNT, NO_WINDOW),
    "the ticks wake: eight bits held, a message and a timer":
        Priced((20472, 29092), *ONE_COUNT, NO_WINDOW),
    "a release wakes: every event, the button held":
        Priced((34522, 52072), (32992, 48722), 1, NO_WINDOW),
    "a key wakes, the sent mark set: a key and a message":
        Priced((17972, 27466), *ONE_COUNT, NO_WINDOW),
    "a writer wakes: a message, none in the pipe":
        Priced((17324, 25028), *ONE_COUNT, (1, 1139762, 278034)),
    "a writer wakes: a message and a timer not run out":
        Priced((20634, 29846), *ONE_COUNT, (1, 1139762, 278034)),
    "a writer and the press's ticks in one wake: a message and a timer":
        Priced((20996, 30306), *ONE_COUNT, (1, 1131220, 276254)),
    "a writer wakes: a key and a message":
        Priced((19970, 29270), *ONE_COUNT, (1, 1139762, 278034)),
    "a writer wakes: every event, the timer not run out":
        Priced((35828, 53312), *ONE_COUNT, (1, 1139762, 278034)),
    "a writer and the press's ticks in one wake: every event":
        Priced((36190, 53772), *ONE_COUNT, (1, 1131220, 276254)),
    "a writer and the press's ticks: eight bits held, a message and a timer":
        Priced((22956, 31938), *ONE_COUNT, (1, 1131220, 276254)),
    "a writer, a key and the press's ticks in one wake: a key, a message and a timer":
        Priced((24224, 35212), *ONE_COUNT, (1, 1135928, 279942)),
    "a writer, a key and the press's ticks in one wake: every event":
        Priced((36688, 54366), *ONE_COUNT, (1, 1135928, 279942)),
    "a writer and the mouse into the rectangle: a rectangle and a message":
        Priced((21368, 31180), *ONE_COUNT, (1, 1146706, 285068)),
    "a writer, a key, the mouse, the press's ticks: every event":
        Priced((36688, 54366), *ONE_COUNT, (1, 1142914, 287018)),
    "a writer, the desk waiting for the bar's rectangle too":
        Priced((21540, 31380), *ONE_COUNT, (1, 1139762, 278034)),
    "a writer, then the mouse away: both rectangles and a message":
        Priced((25758, 37728), *ONE_COUNT, (1, 1150402, 286746)),
    evm.A_KEY_BEFORE_THE_WRITER_WRITES:
        Priced((19966, 29342), *ONE_COUNT, (1, 954308, 240372)),
    evm.A_WRITER_AND_A_KEY:
        Priced((20382, 29772), *ONE_COUNT, (1, 1142416, 279668)),
    evm.A_KEY_WHILE_THE_MANAGER_STANDS_WOKEN:
        Priced((24294, 36578), *ONE_COUNT, (1, 789254, 148618)),
    evm.A_KEY_AND_THE_MOUSE_ONTO_THE_BAR:
        Priced((18694, 27944), *ONE_COUNT, NO_WINDOW),
}
WHOLE_RUN = {
    "a key wakes: a key, none queued":
        {BENCH: (43010, 37094), SHIPPED: (43010, 36904)},
    "a press wakes: the button down, which is up":
        {BENCH: (45214, 38188), SHIPPED: (45214, 38000)},
    "a release wakes: the button up, which is down":
        {BENCH: (44206, 37482), SHIPPED: (44206, 37294)},
    "a double click wakes: a double click":
        {BENCH: (45278, 38278), SHIPPED: (45278, 38090)},
    "a single click wakes: a double click":
        {BENCH: (46560, 39534), SHIPPED: (46560, 39348)},
    "entering wakes: a rectangle the mouse is not in":
        {BENCH: (51718, 45632), SHIPPED: (51718, 45296)},
    "leaving wakes: a rectangle the mouse is to leave":
        {BENCH: (51884, 45764), SHIPPED: (51884, 45428)},
    "entering wakes: the second rectangle alone":
        {BENCH: (51742, 45664), SHIPPED: (51742, 45328)},
    "leaving wakes: two rectangles":
        {BENCH: (61846, 52982), SHIPPED: (61846, 51858)},
    "the ticks wake: a timer":
        {BENCH: (41984, 36478), SHIPPED: (41984, 36502)},
    "a tick wakes: a timer of less than a tick":
        {BENCH: (41794, 36274), SHIPPED: (41794, 36312)},
    "a key wakes: a key and a message":
        {BENCH: (48772, 41054), SHIPPED: (48772, 40306)},
    "the ticks wake: a message and a timer":
        {BENCH: (47746, 40462), SHIPPED: (47746, 39928)},
    "a key wakes: a key and the buttons":
        {BENCH: (48868, 41058), SHIPPED: (48868, 40310)},
    "a press wakes: a key and the buttons":
        {BENCH: (49456, 41482), SHIPPED: (49456, 40736)},
    "a key and a press in one idle: a key and the buttons":
        {BENCH: (54664, 44682), SHIPPED: (54664, 43940)},
    "a press wakes: the buttons and a rectangle":
        {BENCH: (51366, 43226), SHIPPED: (51366, 42246)},
    "a press, then entering, in one idle: the buttons and a rectangle":
        {BENCH: (62490, 52478), SHIPPED: (62490, 51590)},
    "a key wakes: every event":
        {BENCH: (72796, 60088), SHIPPED: (72796, 56852)},
    "a double click wakes: every event":
        {BENCH: (77036, 62628), SHIPPED: (77036, 59400)},
    "leaving wakes: every event":
        {BENCH: (83262, 68964), SHIPPED: (83262, 65820)},
    "entering wakes: every event":
        {BENCH: (83262, 68964), SHIPPED: (83262, 65820)},
    "the ticks wake: every event":
        {BENCH: (71194, 58942), SHIPPED: (71194, 55708)},
    "a key, a double click, leaving and the ticks in one idle: every event":
        {BENCH: (97404, 77570), SHIPPED: (97404, 74442)},
    "a key wakes: eight bits held, a key, the buttons, two rectangles":
        {BENCH: (64478, 54982), SHIPPED: (64478, 52650)},
    "the ticks wake: eight bits held, a message and a timer":
        {BENCH: (49378, 42412), SHIPPED: (49378, 41878)},
    "a release wakes: every event, the button held":
        {BENCH: (72358, 59778), SHIPPED: (72358, 56544)},
    "a key wakes, the sent mark set: a key and a message":
        {BENCH: (48772, 41054), SHIPPED: (48772, 40306)},
    "a writer wakes: a message, none in the pipe":
        {BENCH: (1187094, 1180554), SHIPPED: (1187094, 1180410)},
    "a writer wakes: a message and a timer not run out":
        {BENCH: (1191912, 1184402), SHIPPED: (1191912, 1183912)},
    "a writer and the press's ticks in one wake: a message and a timer":
        {BENCH: (1183830, 1176222), SHIPPED: (1183830, 1175732)},
    "a writer wakes: a key and a message":
        {BENCH: (1191336, 1183858), SHIPPED: (1191336, 1183156)},
    "a writer wakes: every event, the timer not run out":
        {BENCH: (1215378, 1202912), SHIPPED: (1215378, 1199722)},
    "a writer and the press's ticks in one wake: every event":
        {BENCH: (1207296, 1194732), SHIPPED: (1207296, 1191542)},
    "a writer and the press's ticks: eight bits held, a message and a timer":
        {BENCH: (1185462, 1178182), SHIPPED: (1185462, 1177692)},
    "a writer, a key and the press's ticks in one wake: a key, a message and a timer":
        {BENCH: (1193444, 1184816), SHIPPED: (1193444, 1183768)},
    "a writer, a key and the press's ticks in one wake: every event":
        {BENCH: (1212598, 1199938), SHIPPED: (1212598, 1196748)},
    "a writer and the mouse into the rectangle: a rectangle and a message":
        {BENCH: (1200190, 1192542), SHIPPED: (1200190, 1191606)},
    "a writer, a key, the mouse, the press's ticks: every event":
        {BENCH: (1219584, 1206924), SHIPPED: (1219584, 1203734)},
    "a writer, the desk waiting for the bar's rectangle too":
        {BENCH: (1193446, 1185770), SHIPPED: (1193446, 1184834)},
    "a writer, then the mouse away: both rectangles and a message":
        {BENCH: (1210434, 1201628), SHIPPED: (1210434, 1199900)},
    evm.A_KEY_BEFORE_THE_WRITER_WRITES:
        {BENCH: (1005954, 998400), SHIPPED: (1005954, 997698)},
    evm.A_WRITER_AND_A_KEY:
        {BENCH: (1194492, 1186924), SHIPPED: (1194492, 1186222)},
    evm.A_KEY_WHILE_THE_MANAGER_STANDS_WOKEN:
        {BENCH: (855918, 845608), SHIPPED: (855918, 845030)},
    evm.A_KEY_AND_THE_MOUSE_ONTO_THE_BAR:
        {BENCH: (51268, 43178), SHIPPED: (51268, 43038)},
}


def _registered_wakes():
    return {name: switching.register_row(evm.switching_row(name)) for name in evm.WAKES}


WOKEN_ROWS = _registered_wakes()
