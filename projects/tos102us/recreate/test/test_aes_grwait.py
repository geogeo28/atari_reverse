"""AES gemgrlib's box loops that WAIT ON THE MOUSE — `src/aes/grwait.c`, through the event door (`test/aes_event.py`).

    gr_stilldn    ev_multi(BUTTON | M1, its own frame as the MOBLK, no second rectangle, no timer, one rise of the
                  left button, no message, its answer words); 1 unless the answer has MU_BUTTON
    gr_watchbox   gsx_sclip(gl_rscreen); ob_actxywh into its saved D2/D3; then until gr_stilldn answers 0: ob_change to
                  `in` (then `out`, then `in` ...), the leave flag toggled, gr_stilldn over the object's rectangle; D0 the
                  leave flag

THE MACHINES, each the ROM scheduler's own (`aes_event.machine`): PD0 running, woken by a key (the button up), and PD0
running, woken by the left button's press (the button down). The mouse is the snapshot's, at (159, 99) — inside every
rectangle below that says so. Every row's wait is one the event layer ANSWERS: a wait nothing satisfies would block —
the machine switches away until the mouse moves or the button rises — and the door refuses it by name (below), never
answering the "no event" the snapshot's dispatcher guard would.

gr_watchbox's SECOND PASS is reached over the button down with the object NOT under the mouse: the first pass's wait —
for the mouse to leave an object it is outside — is answered at once (the button still down), the loop draws the `out`
state and the second pass's wait, for the mouse to enter, BLOCKS. The door refuses that wait (a child process), and the
case holds what the C did up to it — the whole image, both frames it handed the door — to the ROM's own run AT DSPTCH.
The passes AFTER it — the mouse moved in, out, the button's rise ending an `out` pass with the 0 answer — are what a
machine reaches when an interrupt arrives: delivered at the entry of a pass's wait, the same on both shores
(`aes_event.interrupted`) — or WHILE THE LOOP IS BLOCKED, where the machine waits for it: at the dispatcher's idle.

EVERY WAIT THAT BLOCKS IS TAKEN ON THROUGH ITS WAKE (`aes_event.blocked_then_woken`: STILLDN_WOKEN, WATCHBOX_WOKEN):
the call held where it blocks, and then run to its return through the dispatcher — the ROM's own, and the host's
model with the door bound — the interrupt that wakes it delivered at an idle. The worst of each is a priced row that
SWITCHES (`aes_event.register_woken`), its door call open across the switch, on two counts.
"""
import functools
import struct

import pytest

import aes
import aes_event
import aes_gsx as gsx
import vdi

aes.declare_alcyon("AES_ROM_GR_STILLDN", aes.WORD_ANSWER, (vdi.IMAGE_ARG,) + (vdi.WORD_ARG,) * 5)
aes.declare_alcyon("AES_ROM_GR_WATCHBOX", aes.WORD_ANSWER,
                   (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.WORD_ARG, vdi.WORD_ARG, vdi.WORD_ARG))

THROUGH = gsx.THROUGH
LEAVE, ENTER = 1, 0                    # gr_stilldn's flag: wait for the mouse to leave, or to enter
ENDED_IN, ENDED_OUT = 1, 0             # gr_watchbox's answer: the button rose with the mouse in the object, or out of it
STILL_DOWN, RISEN = 1, 0
AROUND_THE_MOUSE = (140, 80, 40, 40)   # a rectangle the snapshot's mouse is inside
AWAY_FROM_THE_MOUSE = (0, 0, 10, 10)   # ...and one it is not
SELECTOR = aes.resource_tree(0)        # the file selector: OK (21), Cancel (22), the TOUCHEXIT arrow (4)
OK, CANCEL, ARROW = 21, 22, 4          # ...none of them under the snapshot's mouse
NORMAL, SELECTED, CROSSED = 0x00, 0x01, 0x02


def running():
    return aes_event.machine()


def button_down():
    return aes_event.machine(aes_event.button_down)


# ---- the door, first, in a child process ------------------------------------------------------------------------------
@pytest.mark.parametrize("name, values", (("AES_ROM_GR_STILLDN", (LEAVE, *AROUND_THE_MOUSE)),
                                          ("AES_ROM_GR_WATCHBOX", (SELECTOR, OK, SELECTED, NORMAL))),
                         ids=("gr_stilldn", "gr_watchbox"))
def test_each_returns_through_the_door_in_a_child(name, values):
    """A door call the nested run refuses halts the core (`aes/evdoor.h`); in-process that ends the whole run instead of
    failing a case, so each routine is first run in a child process over PD0 running, where it must return."""
    returncode, stderr, _image = aes_event.refusal(name, running(), values)
    assert returncode == 0, stderr


# ---- gr_stilldn ------------------------------------------------------------------------------------------------------
# (machine, leave, rectangle, answer): every way ev_multi ANSWERS gr_stilldn's two events.
EMPTY_AT_THE_MOUSE = (159, 99, 0, 0)   # a rectangle with nothing inside: the mouse has always left it
OVER_NEGATIVE_WORDS = (-20, -10, 300, 200)
STILLDN = {
    "the button up, waiting to leave: it rose": (running, LEAVE, AROUND_THE_MOUSE, RISEN),
    "the button up, waiting to enter: the rise wins over the rectangle": (running, ENTER, AROUND_THE_MOUSE, RISEN),
    "the button up, outside, waiting to enter: it rose": (running, ENTER, AWAY_FROM_THE_MOUSE, RISEN),
    "the button down, inside, waiting to enter: the rectangle": (button_down, ENTER, AROUND_THE_MOUSE, STILL_DOWN),
    "the button down, outside, waiting to leave: the rectangle": (button_down, LEAVE, AWAY_FROM_THE_MOUSE, STILL_DOWN),
    "the button down, an empty rectangle at the mouse, waiting to leave: left": (button_down, LEAVE, EMPTY_AT_THE_MOUSE,
                                                                                STILL_DOWN),
    "the button down, a rectangle at negative words, waiting to enter: inside": (button_down, ENTER, OVER_NEGATIVE_WORDS,
                                                                                STILL_DOWN),
}
# ...and the waits nothing satisfies: the button down and the mouse where the rectangle says it is to stay. On the
# machine they BLOCK; the door refuses them (`aes_event.nested_run`), in a child process, since the core then halts.
WOULD_BLOCK = {
    "the button down, inside, waiting to leave": (LEAVE, AROUND_THE_MOUSE),
    "the button down, outside, waiting to enter": (ENTER, AWAY_FROM_THE_MOUSE),
    "the button down, an empty rectangle, waiting to enter": (ENTER, EMPTY_AT_THE_MOUSE),
}


@pytest.mark.parametrize("machine, leave, rectangle, answer", STILLDN.values(), ids=STILLDN)
def test_gr_stilldn(machine, leave, rectangle, answer):
    result = aes_event.run_event("AES_ROM_GR_STILLDN", (leave, *rectangle), machine())
    assert result.answer() == answer


@THROUGH
def test_gr_stilldn_through_its_callers_word(through_line_f):
    result = aes_event.run_event("AES_ROM_GR_STILLDN", (ENTER, *AROUND_THE_MOUSE), button_down(),
                                 through_line_f=through_line_f)
    assert result.answer() == STILL_DOWN


@pytest.mark.parametrize("leave, rectangle", WOULD_BLOCK.values(), ids=WOULD_BLOCK)
def test_a_wait_nothing_satisfies_is_refused_as_one_that_would_block(leave, rectangle):
    returncode, stderr, _image = aes_event.refusal("AES_ROM_GR_STILLDN", button_down(), (leave, *rectangle))
    assert returncode != 0 and aes_event.BLOCKS in stderr and "hook refused" in stderr, stderr


# ---- gr_watchbox -----------------------------------------------------------------------------------------------------
def watchbox(machine, tree, obj, states):
    return aes_event.run_event("AES_ROM_GR_WATCHBOX", (tree, obj, *states), machine(), drawing=True)


WATCHBOX = {
    "OK, selected while inside: it rose, inside": (running, OK, (SELECTED, NORMAL)),
    "Cancel": (running, CANCEL, (SELECTED, NORMAL)),
    "the arrow, crossed while inside": (running, ARROW, (CROSSED, NORMAL)),
    "OK, drawn normal while inside": (running, OK, (NORMAL, SELECTED)),
}


@pytest.mark.parametrize("machine, obj, states", WATCHBOX.values(), ids=WATCHBOX)
def test_gr_watchbox_ends_in_its_first_pass_when_the_button_is_up(machine, obj, states):
    result = watchbox(machine, SELECTOR, obj, states)
    assert result.answer() == ENDED_IN
    assert result.object(SELECTOR, obj)["STATE"] == states[0], "the object is left drawn in the `in` state"


@THROUGH
def test_gr_watchbox_through_its_callers_word(through_line_f):
    result = aes_event.run_event("AES_ROM_GR_WATCHBOX", (SELECTOR, OK, SELECTED, NORMAL), running(), drawing=True,
                                 through_line_f=through_line_f)
    assert result.answer() == ENDED_IN


SECOND_PASS = {"OK": OK, "Cancel": CANCEL, "the arrow": ARROW}
WATCHBOX_DOOR_CALLS = 2                # pass 1's wait, answered; pass 2's, which blocks


def watched(obj, label, at_idle, at_calls=None):
    """gr_watchbox over `obj` outside the mouse, the button down — a call that BLOCKS, as a row that switches."""
    return aes_event.woken_row(label, "AES_ROM_GR_WATCHBOX", (SELECTOR, obj, SELECTED, CROSSED), button_down, at_idle,
                               at_calls, objects=True)


@pytest.mark.parametrize("obj", SECOND_PASS.values(), ids=SECOND_PASS)
def test_gr_watchbox_s_second_pass_draws_the_out_state_waits_as_the_rom_s_and_is_woken_by_the_rise(obj):
    """The button down, the object outside the mouse: pass 1 answered, the object drawn `out`, pass 2's wait — for the
    mouse to enter — BLOCKS. Up to it, the C is the ROM's run where the ROM blocks: the whole image at dsptch, the
    object's state in it, and both frames handed the door (the leave flag toggled between them). AND ON THROUGH THE
    WAKE: the button's rise, delivered while the loop is blocked, ends the `out` pass with the 0 answer — the object
    left drawn `out`, no third wait made."""
    held, ran = aes_event.blocked_then_woken(watched(obj, "the second pass, woken by the rise", {0: aes_event.release}))
    assert aes.read_object(held.image, SELECTOR, obj)["STATE"] == CROSSED and len(held.calls) == WATCHBOX_DOOR_CALLS
    assert (ran.answer, len(ran.calls)) == (ENDED_OUT, WATCHBOX_DOOR_CALLS)
    assert aes.read_object(ran.image, SELECTOR, obj)["STATE"] == CROSSED


@functools.cache
def the_middle_of(obj):
    """The middle of `obj` on the screen, read off the rectangle the ROM's own gr_watchbox hands its first wait."""
    calls, _memory, _returned = aes_event.rom_watched("AES_ROM_GR_WATCHBOX", (SELECTOR, obj, SELECTED, CROSSED),
                                                      button_down(), blocks=True)
    _leave, x, y, w, h = struct.unpack(">5h", calls[0].arguments[1])
    return x + w // 2, y + h // 2


ELSEWHERE = (0, 0)                     # a point outside every object of the selector
# The passes after the second, each wait's interrupt delivered at its entry (`aes_event.interrupted`), the button down
# and the object outside the mouse throughout pass 1: what ends the loop, its answer (the leave flag: 1 inside, 0
# out), how many passes the ROM's run made — or None where its last wait blocks.
INTERRUPTED = {
    "the button rises at the second wait: out, 0": (lambda obj: {1: aes_event.release}, ENTER, 2),
    "the mouse enters, then the button rises: in, 1": (lambda obj: {1: aes_event.move_to(*the_middle_of(obj)),
                                                                     2: aes_event.release}, ENDED_IN, 3),
    "in, out again, then the rise: 0": (lambda obj: {1: aes_event.move_to(*the_middle_of(obj)),
                                                     2: aes_event.move_to(*ELSEWHERE), 3: aes_event.release}, ENDED_OUT, 4),
    "the mouse enters, the third wait blocks": (lambda obj: {1: aes_event.move_to(*the_middle_of(obj))}, None, 3),
}


@pytest.mark.parametrize("interrupts, answer, passes", INTERRUPTED.values(), ids=INTERRUPTED)
def test_gr_watchbox_s_later_passes_as_interrupts_reach_them(interrupts, answer, passes):
    taken = aes_event.interrupted("AES_ROM_GR_WATCHBOX", (SELECTOR, OK, SELECTED, CROSSED), button_down(),
                                  interrupts(OK), objects=True)
    assert (taken.answer, len(taken.calls)) == (answer, passes)
    assert taken.returned == (answer is not None)


# ---- THE WAITS THAT BLOCK, WOKEN: the interrupt delivered at the dispatcher's idle, the loop run to its return ---------
# gr_stilldn's three waits nothing satisfies (WOULD_BLOCK), each with what ends it: (leave, rectangle, {idle:
# interrupt}, the answer).
INTO_THE_FAR_RECTANGLE = (5, 5)        # a point inside AWAY_FROM_THE_MOUSE
STILLDN_WOKEN = {
    "the button down, inside, waiting to leave; woken by the rise": (LEAVE, AROUND_THE_MOUSE, {0: aes_event.release}, RISEN),
    "the button down, inside, waiting to leave; woken by the mouse leaving": (
        LEAVE, AROUND_THE_MOUSE, {0: aes_event.move_to(*ELSEWHERE)}, STILL_DOWN),
    "the button down, outside, waiting to enter; woken by the mouse entering": (
        ENTER, AWAY_FROM_THE_MOUSE, {0: aes_event.move_to(*INTO_THE_FAR_RECTANGLE)}, STILL_DOWN),
    "the button down, an empty rectangle, waiting to enter; woken by the rise alone": (
        ENTER, EMPTY_AT_THE_MOUSE, {0: aes_event.release}, RISEN),
}
THE_DEAREST_STILLDN = "the button down, inside, waiting to leave; woken by the rise"


def still_down(label):
    leave, rectangle, at_idle, _answer = STILLDN_WOKEN[label]
    return aes_event.woken_row(label, "AES_ROM_GR_STILLDN", (leave, *rectangle), button_down, at_idle)


def test_every_wait_of_gr_stilldn_that_blocks_has_its_woken_counterpart():
    assert {(leave, rectangle) for leave, rectangle, _at_idle, _answer in STILLDN_WOKEN.values()} == set(WOULD_BLOCK.values())


@pytest.mark.parametrize("label", STILLDN_WOKEN, ids=STILLDN_WOKEN)
def test_gr_stilldn_s_wait_that_blocks_is_woken_as_the_rom_s(label):
    """The wait held where it blocks — one frame handed, the image the ROM's at dsptch — and taken on through the
    dispatcher: the interrupt at the idle, the answer the event that came (the rise wins: 0; the rectangle: 1)."""
    held, ran = aes_event.blocked_then_woken(still_down(label))
    assert len(held.calls) == len(ran.calls) == 1 and ran.answer == STILLDN_WOKEN[label][3]


# gr_watchbox's later passes REACHED FROM A BLOCKED ONE: (label, {idle: interrupt}, {door call: interrupt} or None,
# the answer, how many passes).
def _watchbox_woken():
    inside = aes_event.move_to(*the_middle_of(OK))
    return {
        "the mouse enters at the second wait; the third blocks; the rise wakes it: in, 1": (
            {0: aes_event.release}, {1: inside}, ENDED_IN, 3),
        "blocked three times: the mouse in, out again, then the rise: 0": (
            {0: inside, 1: aes_event.move_to(*ELSEWHERE), 2: aes_event.release}, None, ENDED_OUT, 4),
    }


WATCHBOX_WOKEN = ("the mouse enters at the second wait; the third blocks; the rise wakes it: in, 1",
                  "blocked three times: the mouse in, out again, then the rise: 0")


def watched_over_ok(label):
    at_idle, at_calls, _answer, _passes = _watchbox_woken()[label]
    return watched(OK, label, at_idle, at_calls)


@pytest.mark.parametrize("label", WATCHBOX_WOKEN)
def test_gr_watchbox_s_later_passes_as_the_wakes_of_a_blocked_loop_reach_them(label):
    """The loop blocked and woken, pass after pass: an interrupt at a wait's ENTRY and then one at an idle (ONE
    derivation takes both), and a loop that blocks three times in one call — each wake through the dispatcher, the
    same passes, the same answer, the same frames, the whole image."""
    _at_idle, _at_calls, answer, passes = _watchbox_woken()[label]
    _held, ran = aes_event.blocked_then_woken(watched_over_ok(label))
    assert (ran.answer, len(ran.calls)) == (answer, passes)


def test_gr_watchbox_s_tree_is_put_on_the_bus():
    result = watchbox(running, SELECTOR | aes.BUS_TAG, OK, (SELECTED, NORMAL))
    assert result.object(SELECTOR, OK)["STATE"] == SELECTED


def test_gr_watchbox_clips_the_whole_screen_by_value():
    """gl_rscreen's address is what gr_setup's immediate holds ($fe85b2): the C hands the value, the clip is the screen."""
    result = watchbox(running, SELECTOR, OK, (SELECTED, NORMAL))
    clip = [result.field("AES", name) for name in ("GL_XCLIP", "GL_YCLIP", "GL_WCLIP", "GL_HCLIP")]
    assert clip == result.words(aes.AES_GL_RSCREEN, aes.GRECT_BYTES // aes.WORD_BYTES)


# ---- the registry ----------------------------------------------------------------------------------------------------
for _label, (_machine, _leave, _rectangle, _answer) in STILLDN.items():
    aes_event.register(_label, "AES_ROM_GR_STILLDN", (_leave, *_rectangle), _machine())
for _label, (_machine, _obj, _states) in WATCHBOX.items():
    aes_event.register(_label, "AES_ROM_GR_WATCHBOX", (SELECTOR, _obj, *_states), _machine(), drawing=True)
# ...and THE ROWS THAT SWITCH: gr_stilldn's dearest wait that blocks, woken through the dispatcher, and BOTH of
# gr_watchbox's shapes — the one that answers 1 takes an interrupt at a door call before the wait that blocks, and
# is the only blob row a tail of the loop that answered 0 whatever the pass would differ on (measured: that mutant
# passed the three-wakes row, whose answer is 0).
aes_event.register_woken(still_down(THE_DEAREST_STILLDN))
for _label in WATCHBOX_WOKEN:
    aes_event.register_woken(watched_over_ok(_label))
