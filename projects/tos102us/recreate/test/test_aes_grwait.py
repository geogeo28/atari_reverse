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
case holds what the C did up to it — the object's state, both frames it handed the door — to the ROM's own run stopped
where it blocks (`aes_event.rom_watched`). WHAT ONE RUN CANNOT REACH (unpinned, honestly): the 0 answer, an `out` pass
ended by the button's rise — the button is the mouse interrupt's, which the oracle does not take mid-run.
"""
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
    assert returncode != 0 and "would block" in stderr and "hook refused" in stderr, stderr


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
    assert result.answer() == LEAVE
    assert result.object(SELECTOR, obj)["STATE"] == states[0], "the object is left drawn in the `in` state"


@THROUGH
def test_gr_watchbox_through_its_callers_word(through_line_f):
    result = aes_event.run_event("AES_ROM_GR_WATCHBOX", (SELECTOR, OK, SELECTED, NORMAL), running(), drawing=True,
                                 through_line_f=through_line_f)
    assert result.answer() == LEAVE


SECOND_PASS = {"OK": OK, "Cancel": CANCEL, "the arrow": ARROW}
WATCHBOX_DOOR_CALLS = 2                # pass 1's wait, answered; pass 2's, refused


@pytest.mark.parametrize("obj", SECOND_PASS.values(), ids=SECOND_PASS)
def test_gr_watchbox_s_second_pass_draws_the_out_state_then_waits_as_the_rom_s(obj):
    """The button down, the object outside the mouse: pass 1 answered, the object drawn `out`, pass 2's wait — for the
    mouse to enter — refused as one that would block. Up to it, the C is the ROM's run stopped where the ROM blocks:
    the object's state, and both frames handed the door (the leave flag toggled between them)."""
    arguments = (SELECTOR, obj, SELECTED, CROSSED)
    returncode, stderr, image = aes_event.refusal("AES_ROM_GR_WATCHBOX", button_down(), arguments)
    assert returncode != 0 and "would block" in stderr, stderr
    calls, rom_memory, returned = aes_event.rom_watched("AES_ROM_GR_WATCHBOX", arguments, button_down(), blocks=True)
    assert not returned, "the premise: the ROM's run blocks in its second pass"
    assert aes.read_object(image, SELECTOR, obj)["STATE"] == aes.read_object(rom_memory, SELECTOR, obj)["STATE"] == CROSSED
    assert aes_event.handed_in(stderr) == calls and len(calls) == WATCHBOX_DOOR_CALLS


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
