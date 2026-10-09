"""EVNT_MULTI's MACHINES — what `src/aes/evmulti.c` is proved over (`test_aes_evmulti*.py`).

A CASE IS AN APPLICATION'S OWN evnt_multi: ev_multi is what the AES's dispatcher calls for function 25, over the frame
the application's parameters make, so a case is a FRAME (`call`: the flags, two MOBLKs, a timer, a button parameter,
a message buffer, the answers) handed over a MACHINE THE ROM MADE — a process running as the scheduler leaves it
(`aes_evlib`'s machines), and, for what happened while that process was busy, the ROM's own interrupts taken over it
(`after`: a key in the keyboard's ring, the mouse's packets through the VDI's interrupt and the AES's glue, the tick)
— which ev_multi's own chkkbd and forker then find and post, in C under the twin as in the ROM under its routine.

A CALL THAT RETURNS is an ordinary differential, its C first in a fork whose hooks serve the VDI's cores (chkkbd's
polls) and the fork functions (forker's `jsr (a0)`). A CALL THAT BLOCKS — nothing it asks for has come — is held where
the C stops: the dispatcher's hook refuses it by name, and the image the C holds there is the ROM's memory AT DSPTCH,
every EVB, list, PD word and counter its waits wrote (`held`).

A CALL THAT IS WOKEN — the events it blocked for come: an interrupt's, another process's message — is ONE RETURNING
RUN on every shore, a ROW THAT SWITCHES (`WAKES`, `aes_switching`): the ROM's routine through the ROM's dispatcher,
the interrupts delivered at its idles; the twin through the host's scheduler (Tier 1, nothing dropped but the run's
own stack) and, on the bench, through OUR dsptch, disp, savestate and switchto — its frame parked on the process's
own stack and resumed inside our mwait. The case that holds the same call AT DSPTCH stays, as the surface that says
WHICH half of a blocking call differs.

WHAT DIFFERS BY NATURE, each a named drop made only where the ROM's run stores it: the Line-F mask word; the BIOS
trap's saved registers and frame under the keyboard poll; spl7_save's SR save word under adelay's and tchange's
brackets; and the ADDRESS OF THE QPB a message wait was queued with — a local of ev_multi's own frame in the ROM, a
place in the stack band on each shore — in its EVB where the wait PARKS, and still in it, FREED, where the call
returns with the wait cancelled (an EVB is freed as it is): vetted to name the same eight bytes on both shores.
"""
import ctypes
import functools
import struct
from collections import namedtuple

from harness import _lib, addrs, arm_candidate, make_image

import aes
import aes_evasync as evasync
import aes_event
import aes_evinput
import aes_evlib as evlib
import aes_pdpipe
import aes_switching
import case
import routines
import vdi
from case import merge_pokes

EVM = aes.header_constants("evmulti.h")
EVLIB = evlib.EVLIB
WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES
IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG

# ---- the routine, and how it is called ---------------------------------------------------------------------------------
EV_MULTI = "AES_ROM_EV_MULTI"
if EV_MULTI not in vdi.ALCYON:
    aes.declare_alcyon(EV_MULTI, aes.WORD_ANSWER, (IMAGE, WORD, LONG, LONG, LONG, LONG, LONG, LONG))
ROUTINES = (EV_MULTI,)

# The event layer's shared binding (`aes_event`): the VDI's cores chkkbd polls through and the fork functions forker
# calls, served in the guard's forks too.
HOOKS, SERVED_IN_A_FORK = aes_event.EVENT_LAYER_HOOKS, aes_event.SERVED_IN_A_FORK
# ev_multi runs behind the fork guard, its fork serving the two hooks chkkbd and forker call through.
FORK_GUARDED = {EV_MULTI: SERVED_IN_A_FORK}

# ---- what a call hands in: the lists' band (`aes_evasync`) ---------------------------------------------------------------
FIRST_RECT_AT, SECOND_RECT_AT = evasync.FIRST_RECT_AT, evasync.SECOND_RECT_AT
MESSAGE_AT, ANSWERS_AT = evasync.MESSAGE_AT, evasync.ANSWERS_AT
ANSWER_WORDS = aes.EV_MULTI_ANSWER_WORDS
MESSAGE_BYTES = aes_event.MESSAGE_BYTES
STALE = aes.STALE_WORD
STALE_ANSWERS = {ANSWERS_AT: struct.pack(">H", STALE) * ANSWER_WORDS}
STALE_MESSAGE = {MESSAGE_AT: bytes([case.SLACK_FILL]) * MESSAGE_BYTES}
KEYBD, BUTTON, M1, M2 = aes.EV_MU_KEYBD, aes.EV_MU_BUTTON, aes.EV_MU_M1, aes.EV_MU_M2
MESAG, TIMER = aes.EV_MU_MESAG, aes.EV_MU_TIMER
EVERY_EVENT = KEYBD | BUTTON | M1 | M2 | MESAG | TIMER
Y, BUTTONS, SHIFT_KEYS = (EVLIB[f"EV_RETS_{name}"] // WORD_BYTES for name in ("Y", "BUTTONS", "SHIFT_KEYS"))
KEY, CLICKS = EVM["EV_MULTI_KEY"] // WORD_BYTES, EVM["EV_MULTI_CLICKS"] // WORD_BYTES
LEAVE, ENTER = evasync.LEAVE, evasync.ENTER
moblk, button_wait = evasync.moblk, evasync.button_wait
ROUND_THE_MOUSE, ELSEWHERE = evasync.ROUND_THE_MOUSE, evasync.ELSEWHERE
SINGLE, DOUBLE = evasync.SINGLE, evasync.DOUBLE
LEFT, RIGHT, UP = aes_event.LEFT_BUTTON, evlib.RIGHT, 0
SHELL, SCREEN_MANAGER = aes.SHELL_PD, aes.SCREEN_MANAGER_PD
TICK_MS = evasync.TICK_MS
A_TIMER_MS = evasync.A_TIMER_MS

Call = namedtuple("Call", "machine arguments staged")


def call(machine, flags, *, first=None, second=None, timer=0, button=0, message=MESSAGE_AT, answers=ANSWERS_AT,
         staged=None):
    """An application's evnt_multi over `machine` (a callable making the ROM-made pokes): the `flags`, the MOBLKs
    `first` and `second` staged in the band where handed, the `timer`'s milliseconds, the `button` parameter, the
    `message` buffer and the `answers` — both stale — and whatever else the case has `staged`."""
    pokes = merge_pokes(STALE_ANSWERS, STALE_MESSAGE, {FIRST_RECT_AT: first} if first else None,
                        {SECOND_RECT_AT: second} if second else None, staged)
    arguments = (flags, FIRST_RECT_AT if first else 0, SECOND_RECT_AT if second else 0, timer & aes.LONG_MASK, button,
                 message, answers)
    return Call(machine, arguments, pokes)


def machine_of(made):
    """The machine a `Call` is run over: the ROM-made one, the call's own staging laid in."""
    return merge_pokes(made.machine(), made.staged)


# ---- THE MACHINES: a process running, and what the ROM's interrupts did while it was busy ---------------------------------
def after(machine, *interrupts):
    """`machine()` continued by `interrupts` — each the ROM's own interrupt code over the machine as the one before
    left it (`aes_evasync.taken`): a key in the keyboard's ring, changes queued for forker — as a machine's maker."""
    @functools.cache
    def made():
        return evasync.taken(machine(), *interrupts)
    return made


def sequence(interrupts):
    """One of `aes_event`'s sequences of interrupts (CLICKING, RIGHT_PRESSING) as an interrupt `after` takes."""
    return functools.partial(aes_event.taken_in_place, sequence=interrupts)


desk, manager = evlib.desk_running, evlib.manager_running
RETURN = aes_event.key(aes_event.RETURN_KEY)
CLICK, RIGHT_PRESS = sequence(aes_event.CLICKING), sequence(aes_event.RIGHT_PRESSING)
# A RIGHT click — down and up again — with no button held, and with the left held all through (the packets' headers).
_NO_BUTTON, _LEFT_DOWN, _RIGHT_DOWN = aes_event.NO_BUTTON_PACKET, aes_event.LEFT_DOWN_PACKET, aes_event.RIGHT_DOWN_PACKET
RIGHT_CLICK = sequence(aes_event.in_turn(aes_event.packets(_RIGHT_DOWN, _NO_BUTTON), aes_event.click_counted))
RIGHT_CLICK_THE_LEFT_HELD = sequence(aes_event.in_turn(aes_event.packets(_LEFT_DOWN | _RIGHT_DOWN, _LEFT_DOWN),
                                                       aes_event.click_counted))
ONTO_THE_BAR, AWAY = evasync.ONTO_THE_BAR, evasync.AWAY
INTO_ELSEWHERE = aes_event.move_to(ELSEWHERE[0] + 5, ELSEWHERE[1] + 5)


# ---- THE ROM AT DSPTCH, AND THE C HELD TO IT -------------------------------------------------------------------------------
BLOCKS = aes_event.BLOCKS
Switched = aes_event.Switched
QPB = aes_event.QPB


def switches(arguments, machine):
    """Does the ROM's call block (reach the dispatcher) rather than return? Its own run's answer, kept by content."""
    return evlib.switches(EV_MULTI, arguments, machine)


def switched(arguments, machine):
    """A CALL THAT BLOCKS, held where the C stops (`aes_event.switches_where_the_rom_does`): the ROM's run reaches
    dsptch as one that blocks; the twin, in a fork that serves its hooks, halts at the dispatcher's hook as one that
    does; and the image it holds there is the ROM's memory AT DSPTCH — a parked message wait's QPB address found,
    vetted and dropped there (`Switched.parked`: the QPBs)."""
    return aes_event.switches_where_the_rom_does(EV_MULTI, arguments, machine, hook=HOOKS)


# ---- THE RUN DOOR ----------------------------------------------------------------------------------------------------------
# WHAT STEERS THE ATTRIBUTION PASS is derived (`aes_event.steering_asked`: every declared reason of the layers under
# ev_multi whose words the ROM's run STORES is asked — tried without first, named only where the pass fails without
# it). ev_multi declares one of its own:
STEERS_THE_BUTTON_CHANGES = aes.steers(
    "the count of button changes posted — bchange counts it up under forker and the fast path's button test decides "
    "by the count which buttons it tries: inverted, a click that came is not found and the run reaches the dispatcher",
    (aes.AES_MTRANS, aes.AES_MTRANS + WORD_BYTES))
aes_event.declare_steering_module(__name__)


def returning(arguments, machine, also=(), savptr_steers=True, **kwargs):
    """The differential of a call that RETURNS (`aes_event.run_layer_case`): every run of the twin first in a fork
    that serves its hooks, the layer's drops made where the ROM's run stores them — with the QPB's address a
    cancelled message wait left in its freed EVB, vetted — and the attribution pass steered by derivation, to a
    fixpoint (the event layer's one loop: `aes_event.steered_as_needed`): the declared reasons whose words the ROM's
    run stores, and what the case itself says may steer it (`also`), each named only where the pass fails without
    it; a call that asks no reason runs under the kit's whole pass.
    ONE REASON IS TAKEN FOR CERTAIN wherever the run stores its word, A SPEED HINT (it spares every case the trial
    that fails without it): `savptr`, which the BIOS trap under chkkbd's keyboard poll saves the registers through.
    Like every reason it is held by the AES_STEERED_FOR_NOTHING sweep — which found the one case it does not steer
    (`savptr_steers` False: a key count that, inverted, is a full queue the pass never polls).
    A case that says itself (`steered=`, `poison=`) is run as it says."""
    certain = (aes_evinput.STEERS_THE_TRAP,) if savptr_steers else ()
    return aes_event.run_layer_case(EV_MULTI, arguments, machine, hook=HOOKS, certain=certain, also=also, **kwargs)


def twice_in_a_fork(made):
    """`(exit code, stderr)` of the twin run TWICE over a `Call`'s machine, in ONE fork that serves its hooks: what
    a first call left held in the library — nothing of the image — is there for the second."""
    core, typed = getattr(_lib, routines.core_symbol(EV_MULTI)), vdi.as_signed(EV_MULTI, made.arguments)
    image = bytes(make_image(aes.staged(EV_MULTI, typed, machine_of(made))))

    def call():
        arm_candidate()
        with HOOKS() as bound:
            for _run in range(2):
                bound.recording(lambda _lib_, buf: core(buf, *typed))(_lib, (ctypes.c_uint8 * len(image)).from_buffer_copy(image))
    return aes_event.in_a_fork(call, serves=SERVED_IN_A_FORK)


def held(arguments, machine, **kwargs):
    """THE CASE, whichever way the ROM's call ends: a `Switched` for one that blocks, the differential's result for
    one that returns."""
    if switches(arguments, machine):
        return switched(arguments, machine)
    return returning(arguments, machine, **kwargs)


def run(made, **kwargs):
    """...of a `Call`."""
    return held(made.arguments, machine_of(made), **kwargs)


def image_after(result):
    return result.image if isinstance(result, Switched) else result.final


def answers(image, at=ANSWERS_AT):
    """The six answer words at `at` in `image`: the mouse, the buttons, the shift keys, the key, the clicks."""
    return [case.word_in(image, (at & aes_event.OS_BUS_ADDR_MASK) + index * WORD_BYTES) for index in range(ANSWER_WORDS)]


def came(result):
    """The events a returning call answered."""
    return result.answer() & aes.WORD_MASK


# ---- THE CALLS -------------------------------------------------------------------------------------------------------------
# The machines beside `aes_evlib`'s: what happened while the process was busy, and two processes' own.
on_the_bar = evlib.desk_running_the_mouse_on_the_bar    # PD0 running, the mouse the screen manager's (parked on PD0's lock)
key_queued, button_held = evlib.key_queued, evlib.button_held
typed = after(desk, RETURN)                             # a key in the keyboard's ring, not polled yet
pressed, clicked = after(desk, aes_event.press), after(desk, CLICK)     # a press / a press and its release, queued for forker
double_clicked, right_pressed = after(desk, aes_event.double_click), after(desk, RIGHT_PRESS)
right_clicked = after(desk, RIGHT_CLICK)                # a right press and its release: two changes, the right up again
left_held_right_clicked = after(button_held, RIGHT_CLICK_THE_LEFT_HELD)     # ...the left down before, during and after
released = after(button_held, aes_event.release)
moved = after(desk, INTO_ELSEWHERE)                     # the mouse moved into ELSEWHERE
# ...and moved in and out of it until THE FORK QUEUE IS FULL: every entry a move the ROM's motion glue queued, for
# forker to run one by one before anything is looked at (the glue queues no more into a full queue).
moved_until_the_fork_queue_is_full = after(desk, *(INTO_ELSEWHERE if nth % 2 == 0 else AWAY
                                                   for nth in range(aes.AES_FORK_ENTRIES)))
moved_onto_the_bar = after(desk, ONTO_THE_BAR)          # ...onto the menu bar: forker's mchange gives it to the screen manager
pressed_then_moved = after(desk, aes_event.press, AWAY)
pressed_on_the_bar = after(on_the_bar, aes_event.press)  # the button down, the mouse still the screen manager's
typed_and_pressed = after(desk, RETURN, aes_event.press)
A_FULL_KEY_QUEUE = aes_evinput.A_FULL_KEY_QUEUE
A_TIMER_TICKS = evasync.A_TIMER_TICKS
SHELL_PID, SCREEN_MANAGER_PID = aes_pdpipe.SHELL_PID, aes_pdpipe.SCREEN_MANAGER_PID


@functools.cache
def a_full_key_queue_and_one_more_typed():
    """PD0 running with its key queue FULL and one more key in the keyboard's ring: chkkbd leaves that one unpolled."""
    return evasync.taken(evlib.key_queued(A_FULL_KEY_QUEUE), RETURN)


@functools.cache
def a_key_queued_and_a_message():
    """PD0 running with a key queued and a message in its own pipe (the ROM's own appl_write)."""
    return aes_pdpipe.sent(merge_pokes(evlib.key_queued(), aes_pdpipe.STALE_BUFFER), SHELL_PID, evlib.A_MESSAGE)


@functools.cache
def the_manager_holding_a_message():
    """The SCREEN MANAGER running with a message in ITS pipe (its own appl_write to itself)."""
    return aes_pdpipe.sent(manager(), SCREEN_MANAGER_PID, evlib.A_MESSAGE)


@functools.cache
def the_manager_running_a_key_in_the_desk_s_queue():
    """The SCREEN MANAGER running while the desk, parked for a press, has a key in its queue: the desk parked with
    the key queued, and the mouse onto the bar woke the manager."""
    frame = aes_event.EV_MULTI_FRAME.pack(BUTTON, 0, 0, 0, THE_BUTTON_DOWN, MESSAGE_AT, ANSWERS_AT)
    return aes_event.woken_onto_the_menu_bar(aes_event.parked(addrs.AES_ROM_EV_MULTI, frame, evlib.key_queued()))


@functools.cache
def eight_bits_held_on_the_bar():
    """AN ARGUMENT-CLASS MACHINE (`aes_evlib.after_iasync`: the ROM's own iasync, eight waits of no kind): PD0, the
    mouse the screen manager's, holding its eight low event bits — the waits a call queues take bits from $100 up."""
    machine = on_the_bar()
    for _wait in range(evlib.EVENT_BITS_IN_A_BYTE):
        machine = evlib.after_iasync(machine, evlib.NO_WAIT, 0)
    return machine


# THE SCREEN MANAGER'S OWN CALL, as the ROM's control manager makes it ($fe49f4..$fe4a16): a key, the buttons and ONE
# rectangle — both MOBLK pointers its own mouse wait (GEM's gl_ctwait, whose rectangle is the menu bar's active one),
# no timer, either state of any button on one click, no message buffer.
CTWAIT = aes.header_constants("evinput.h")["AES_GL_CTWAIT_LEAVE"]
ANY_BUTTON = 0xFF
THE_MANAGER_S_BUTTONS = button_wait(SINGLE, ANY_BUTTON)             # ($fe4a02 move.l #$0001ff01,(sp))
THE_MANAGER_S_OWN_CALL = Call(manager, (KEYBD | BUTTON | M1, CTWAIT, CTWAIT, 0, THE_MANAGER_S_BUTTONS, 0, ANSWERS_AT),
                              STALE_ANSWERS)
IN, NOT_IN = moblk(ENTER, *ROUND_THE_MOUSE), moblk(ENTER, *ELSEWHERE)
OUT, NOT_OUT = moblk(LEAVE, *ELSEWHERE), moblk(LEAVE, *ROUND_THE_MOUSE)
ON_THE_BAR, OFF_THE_BAR = moblk(ENTER, *evlib.THE_MENU_BAR), moblk(LEAVE, *evlib.THE_MENU_BAR)
THE_BUTTON_UP, THE_BUTTON_DOWN = button_wait(SINGLE, state=UP), button_wait(SINGLE)
A_DOUBLE_CLICK = button_wait(DOUBLE)
THE_RIGHT_BUTTON_DOWN = button_wait(SINGLE, RIGHT, RIGHT)
EITHER_BUTTON_NOT_UP = button_wait(evlib.EITHER | SINGLE, LEFT | RIGHT, UP)
A_TIME_OF_NO_TICK = TICK_MS - 1                         # milliseconds that divide to no tick: adelay waits for one
THE_SHORTEST_TIME = 1                                   # one millisecond: not "no time" — the fast path tests for 0 alone
A_TIME_IN_THE_HIGH_WORD = 0x10000                       # a timer whose LOW word is 0: `tst.l` — it has not come
FLAGS_ABOVE_THE_SIX = 0xFFC0                            # the flags word's bits no event has
AN_UNKNOWN_FLAG = 0x40
EVERY = dict(first=NOT_OUT, second=NOT_IN, timer=A_TIMER_MS, button=A_DOUBLE_CLICK)
THREE_AT_ONCE = dict(first=ON_THE_BAR, second=OUT, button=THE_BUTTON_UP)    # ...on the bar, what the waits find satisfied
POLLS_FIRST = {         # an event that has come already: the fast path — nothing queued, nothing waited for
    "a key queued": call(key_queued, KEYBD),
    "three keys queued": call(lambda: evlib.key_queued(3), KEYBD),
    "Alt-= queued, Alt held": call(evlib.alt_key_queued, KEYBD),
    "the key queue's front round the ring": call(evlib.key_queued_round_the_ring, KEYBD),
    "a key queued, the button up as wanted too": call(key_queued, KEYBD | BUTTON, button=THE_BUTTON_UP),
    "a key queued and not asked for, the button up": call(key_queued, BUTTON, button=THE_BUTTON_UP),
    "the button up, as wanted": call(desk, BUTTON, button=THE_BUTTON_UP),
    "the button down, as wanted": call(button_held, BUTTON, button=THE_BUTTON_DOWN),
    "either button not up, the left down": call(button_held, BUTTON, button=EITHER_BUTTON_NOT_UP),
    "the mouse in the rectangle it is to enter": call(desk, M1, first=IN),
    "the mouse out of the rectangle it is to leave": call(desk, M1, first=OUT),
    "the second rectangle alone": call(desk, M2, second=IN),
    "both rectangles": call(desk, M1 | M2, first=IN, second=OUT),
    "the first rectangle of two": call(desk, M1 | M2, first=IN, second=NOT_IN),
    "the second rectangle of two": call(desk, M1 | M2, first=NOT_OUT, second=OUT),
    "a timer of no time": call(desk, TIMER),
    "a timer of no time, a key not come": call(desk, KEYBD | TIMER),
    "a message in the pipe": call(lambda: evlib.holding(1), MESAG),
    "two messages in the pipe": call(lambda: evlib.holding(2), MESAG),
    "the pipe full": call(lambda: evlib.holding(evlib.FULL_PIPE), MESAG),
    "a message and a timer of no time": call(lambda: evlib.holding(1), MESAG | TIMER),
    "a message in the pipe and not asked for, a timer of no time": call(lambda: evlib.holding(1), TIMER),
    "a key queued, a message asked for and not come": call(key_queued, KEYBD | MESAG),
    "every event come at once": call(a_key_queued_and_a_message, EVERY_EVENT, first=IN, second=OUT, button=THE_BUTTON_UP),
    "a key queued, flags above the six set": call(key_queued, FLAGS_ABOVE_THE_SIX | KEYBD),
    "the screen manager's own message": call(the_manager_holding_a_message, MESAG),
    # ...the buttons the answers hand out: the word the last answered wait of an EARLIER call left
    # (that machine's mouse has LEFT the rectangle round where it was)
    "a rectangle and the buttons asked, after a mouse wait was woken": call(
        evlib.after_a_mouse_wait, BUTTON | M1, first=NOT_OUT, button=THE_BUTTON_DOWN),
    "a rectangle alone, after a mouse wait was woken": call(evlib.after_a_mouse_wait, M1, first=NOT_OUT),
    # ...and the screen manager's, on the snapshot's own machine: woken by the mouse entering the bar's rectangle
    "the screen manager's own call: a key, the buttons, its rectangle": THE_MANAGER_S_OWN_CALL,
    "the screen manager, the button up as wanted": call(manager, BUTTON, button=THE_BUTTON_UP),     # ...it owns the mouse
    "every event by the screen manager, a rectangle come": call(manager, EVERY_EVENT, first=ON_THE_BAR, second=NOT_IN,
                                                                timer=A_TIMER_MS, button=A_DOUBLE_CLICK),
    "the button up as wanted, after a mouse wait was woken": call(evlib.after_a_mouse_wait, BUTTON, button=THE_BUTTON_UP),
}
WHILE_IT_WAS_BUSY = {   # what the interrupts queued before the call: chkkbd and forker post it, then the fast path
    "a key typed": call(typed, KEYBD),
    "a key typed and not asked for": call(typed, BUTTON, button=THE_BUTTON_UP),
    "a key typed into a full queue": call(a_full_key_queue_and_one_more_typed, KEYBD),
    "a press": call(pressed, BUTTON, button=THE_BUTTON_DOWN),
    "a press, the button wanted up": call(pressed, BUTTON, button=THE_BUTTON_UP),
    "a click, the button wanted down": call(clicked, BUTTON, button=THE_BUTTON_DOWN),
    "a click, the button wanted up": call(clicked, BUTTON, button=THE_BUTTON_UP),
    "a click, the right button wanted": call(clicked, BUTTON, button=THE_RIGHT_BUTTON_DOWN),
    "a click, either button wanted not up": call(clicked, BUTTON, button=EITHER_BUTTON_NOT_UP),
    # ...the buttons BEFORE the last change (both) and the buttons as they are (the left) would BOTH answer:
    "the left held, the right clicked: the left wanted down": call(left_held_right_clicked, BUTTON, button=THE_BUTTON_DOWN),
    "a double click": call(double_clicked, BUTTON, button=A_DOUBLE_CLICK),
    "a right press": call(right_pressed, BUTTON, button=THE_RIGHT_BUTTON_DOWN),
    "a release": call(released, BUTTON, button=THE_BUTTON_UP),
    "the mouse moved into the rectangle": call(moved, M1, first=NOT_IN),
    "the fork queue full of moves, a timer of no time": call(moved_until_the_fork_queue_is_full, TIMER),
    "a press, then the mouse moved away": call(pressed_then_moved, BUTTON | M1, first=NOT_OUT, button=THE_BUTTON_DOWN),
    "a key typed and a press": call(typed_and_pressed, KEYBD | BUTTON, button=THE_BUTTON_DOWN),
    "ticks, no timer running": call(after(desk, evasync.ticks(A_TIMER_TICKS)), TIMER),
}
THE_MOUSE_ANOTHER_S = {     # the fast path's button and rectangle tests refuse; the waits themselves do not ask
    "the mouse moved onto the bar, the button up as wanted": call(moved_onto_the_bar, BUTTON, button=THE_BUTTON_UP),
    "the mouse moved onto the bar, to enter it": call(moved_onto_the_bar, M1, first=ON_THE_BAR),
    "on the bar: the button up as wanted": call(on_the_bar, BUTTON, button=THE_BUTTON_UP),
    "on the bar: the first rectangle": call(on_the_bar, M1, first=ON_THE_BAR),
    "on the bar: the second rectangle": call(on_the_bar, M2, second=ON_THE_BAR),
    "on the bar: the buttons and both rectangles at once": call(on_the_bar, BUTTON | M1 | M2, **THREE_AT_ONCE),
    "on the bar: every event asked, three come at once": call(on_the_bar, EVERY_EVENT, timer=A_TIMER_MS, **THREE_AT_ONCE),
    "on the bar: three come at once, a key's and a timer's waits cancelled": call(
        on_the_bar, KEYBD | BUTTON | M1 | M2 | TIMER, timer=A_TIMER_MS, **THREE_AT_ONCE),
    "on the bar: a rectangle come, the buttons not": call(on_the_bar, BUTTON | M1, first=ON_THE_BAR, button=THE_BUTTON_DOWN),
    "on the bar: the buttons come, a key and a timer cancelled": call(
        on_the_bar, KEYBD | BUTTON | TIMER, timer=A_TIMER_MS, button=THE_BUTTON_UP),
    "on the bar: a rectangle come, a message wait cancelled": call(on_the_bar, M1 | MESAG, first=ON_THE_BAR),
    "on the bar: the buttons come, a rectangle's wait cancelled": call(
        on_the_bar, BUTTON | M2, second=OFF_THE_BAR, button=THE_BUTTON_UP),
    "on the bar: a rectangle come, a double-click wait cancelled": call(
        on_the_bar, BUTTON | M1, first=ON_THE_BAR, button=A_DOUBLE_CLICK),
    "on the bar: nothing come": call(on_the_bar, BUTTON | M1, first=OFF_THE_BAR, button=THE_BUTTON_DOWN),
    "pressed on the bar: the button down as wanted": call(pressed_on_the_bar, BUTTON, button=THE_BUTTON_DOWN),
    "on the bar, eight event bits held (the ROM's iasync): three come at once": call(
        eight_bits_held_on_the_bar, EVERY_EVENT, timer=A_TIMER_MS, **THREE_AT_ONCE),
}
NOTHING_COME = {            # every event asked for is queued, and the call blocks
    "a key, none queued": call(desk, KEYBD),
    "the button down, which is up": call(desk, BUTTON, button=THE_BUTTON_DOWN),
    "the button up, which is down": call(button_held, BUTTON, button=THE_BUTTON_UP),
    "a double click": call(desk, BUTTON, button=A_DOUBLE_CLICK),
    "either button not up, which they are": call(desk, BUTTON, button=EITHER_BUTTON_NOT_UP),
    "a rectangle the mouse is not in": call(desk, M1, first=NOT_IN),
    "a rectangle the mouse is to leave": call(desk, M1, first=NOT_OUT),
    "the second rectangle alone": call(desk, M2, second=NOT_IN),
    "two rectangles": call(desk, M1 | M2, first=NOT_OUT, second=NOT_IN),
    "a timer": call(desk, TIMER, timer=A_TIMER_MS),
    "a timer of less than a tick": call(desk, TIMER, timer=A_TIME_OF_NO_TICK),
    "a timer of one millisecond": call(desk, TIMER, timer=THE_SHORTEST_TIME),
    "a timer whose low word is 0": call(desk, TIMER, timer=A_TIME_IN_THE_HIGH_WORD),
    "a timer of a negative time": call(desk, TIMER, timer=-A_TIMER_MS),
    "a timer after a timer ran out": call(evlib.after_a_timer_ran_out, TIMER, timer=A_TIMER_MS),
    "a message, none in the pipe": call(desk, MESAG),
    "a message and a timer": call(desk, MESAG | TIMER, timer=A_TIMER_MS),
    "a key and a message": call(desk, KEYBD | MESAG),
    "a key and the buttons": call(desk, KEYBD | BUTTON, button=THE_BUTTON_DOWN),
    "the buttons and a rectangle": call(desk, BUTTON | M1, first=NOT_IN, button=THE_BUTTON_DOWN),
    "every event": call(desk, EVERY_EVENT, **EVERY),
    "every event, the button held": call(button_held, EVERY_EVENT, first=NOT_OUT, second=NOT_IN, timer=A_TIMER_MS,
                                         button=THE_BUTTON_UP),
    "every event, by the screen manager": call(manager, EVERY_EVENT, first=OFF_THE_BAR, second=NOT_IN, timer=A_TIMER_MS,
                                               button=A_DOUBLE_CLICK),
    "a message, by the screen manager": call(manager, MESAG),
    "no event at all": call(desk, 0),
    "a flag no event has": call(desk, AN_UNKNOWN_FLAG),
    "a press, the button wanted up": WHILE_IT_WAS_BUSY["a press, the button wanted up"],
    "a click, the right button wanted": WHILE_IT_WAS_BUSY["a click, the right button wanted"],
    "the mouse moved onto the bar, a key": call(moved_onto_the_bar, KEYBD),
    "a key typed and not asked for, a rectangle": call(typed, M1, first=NOT_IN),
    "on the bar: nothing come": THE_MOUSE_ANOTHER_S["on the bar: nothing come"],
    "eight event bits held (the ROM's iasync): a key, the buttons, two rectangles": call(
        evlib.eight_event_bits_held, KEYBD | BUTTON | M1 | M2, first=NOT_OUT, second=NOT_IN, button=A_DOUBLE_CLICK),
    "eight event bits held (the ROM's iasync): a message and a timer": call(
        evlib.eight_event_bits_held, MESAG | TIMER, timer=A_TIMER_MS),
    "two delays pending (the ROM's iasync): a timer between them": call(
        lambda: evlib.delays_pending(10, 30), TIMER, timer=15 * TICK_MS),
    "two events come and not answered (the ROM's iasync): the buttons, a rectangle": call(evlib.two_events_come, BUTTON | M1, first=NOT_IN,
                                                                      button=THE_BUTTON_DOWN),
}
for _blocking in ("a press, the button wanted up", "a click, the right button wanted"):
    del WHILE_IT_WAS_BUSY[_blocking]
del THE_MOUSE_ANOTHER_S["on the bar: nothing come"]
RETURNING = {**POLLS_FIRST, **WHILE_IT_WAS_BUSY, **THE_MOUSE_ANOTHER_S}

# ---- what a wake is made of -------------------------------------------------------------------------------------------------
SENT_MARK = EVLIB["AES_CTL_MESSAGE_SENT"]
A_TIMER_S_TICKS = evasync.ticks(A_TIMER_TICKS)


def marked(made):
    """A `Call` with AN ARGUMENT-CLASS POKE beside its ROM-made machine: the control manager's "sent" mark staged
    SET (the control manager sets it after it sends a window message, a run this battery does not make), so that the
    tail's clear of it — or its leaving it — is seen."""
    return made._replace(staged=merge_pokes(made.staged, {SENT_MARK: struct.pack(">H", 1)}))


EIGHT_BITS_HELD_A_KEY_THE_BUTTONS = "eight event bits held (the ROM's iasync): a key, the buttons, two rectangles"
EIGHT_BITS_HELD_A_MESSAGE_A_TIMER = "eight event bits held (the ROM's iasync): a message and a timer"


# ---- THE CALLS THAT BLOCK AND ARE WOKEN, AS ONE RETURNING RUN: the rows that switch (`aes_switching`) ----------------------
# A WAKE IS A CALL AND A SCHEDULE — what is delivered at which IDLE of the dispatcher the blocked call left by, as
# `aes_switch.scheduled` takes it. The ROM's routine runs it through the ROM's dispatcher; the twin through the host's
# scheduler (Tier 1: `aes_switching.companion`, nothing dropped) and, on the bench, through OUR dsptch, disp, savestate
# and switchto — its frame parked on the process's own stack and resumed (`aes_switching.measured_on`). Nothing lays
# memory under the twin: mwait's return, the cancel and the answers run over what the twin's own run made.
#   * BY AN INTERRUPT: the interrupts of a case, in ONE idle — the first, and the only one the run makes.
#   * BY A WRITER: THE MENU CHAIN. The mouse onto a title of the bar wakes the screen manager — the snapshot's own
#     other process, the ROM's code on every shore (a FOREIGN WINDOW) — which takes the mouse and drops the menu; the
#     mouse onto an item; the button pressed: the screen manager's own appl_write (mn_do's selection, sent by the
#     ROM's control manager) serves the desk's parked message wait THROUGH THE QPB OF THE WAITING CALL — the twin's
#     own, in its own frame — and the desk is entered again. What a case adds comes WITH THE PRESS, in that idle.
#     THE PRESS BRINGS ITS OWN TICKS: the snapshot's machine has a double-click wait counted (AES_GL_BPEND 1), so a
#     press opens a click count and the ticks that run it out (`aes_event.PRESSING`: AES_GL_DCLICK, 11) are ticks of
#     every delay pending — a timer of A_TIMER_MS runs out with the press, one of A_LONG_TIMER_MS does not.
#     THE WOKEN LIST IS LAST IN, FIRST OUT, and a key THAT ARRIVES IN THE SAME IDLE AS THE PRESS is that idle's last
#     fork (the dispatcher polls the keyboard after the interrupts queued theirs): it wakes the desk AFTER the press
#     woke the screen manager, so the desk runs FIRST and answers the key alone, no message written yet — unless
#     something woke it before the press did (the ticks: its timer). Both are cases below.
#   * AT A POLL THAT IS NO IDLE (`aes_switch.scheduled`'s `at_polls`). idle polls the keyboard every time round its
#     loop, so a key that arrives AFTER the press's forks have run — the screen manager woken and not yet moved to the
#     ready list — is polled there: kchange then wakes the desk BEHIND the manager, the manager runs first and
#     writes, and the desk answers A KEY AND A MESSAGE, nothing else, in one wake ($11). "Last in, first out" is a
#     fact of what arrives AT ONE IDLE; the order of two wakes across two polls is the order they come in.
Scheduled = namedtuple("Scheduled", "call at_idle at_polls", defaults=(None,))
THE_FIRST_IDLE, THE_PRESS_S_IDLE = 0, 2


def the_poll_after(idle):
    """The ordinal of the dispatcher's poll that FOLLOWS the idle `idle` of a menu chain's run: every idle of the
    chain takes a delivery whose fork wakes the screen manager, and idle polls once more — the manager woken, not
    yet ready — before it is entered. Two polls an idle, then: the idle's own, and this one (held on the ROM's run:
    `test_aes_evmulti.py`, the premise of a wake at a poll)."""
    return 2 * idle + 1


# "View" on the bar and its plain item (`evlib.A_MESSAGE`'s two words): the chain every battery walks
# (`aes_event.THE_MENU_CHAIN`), each idle's delivery a tuple here — what a case adds comes with the press.
ONTO_THE_TITLE, ONTO_THE_ITEM = aes_event.ONTO_THE_VIEW_TITLE, aes_event.ONTO_ITS_PLAIN_ITEM
THE_MENU_CHAIN = {idle: (interrupt,) for idle, interrupt in aes_event.THE_MENU_CHAIN.items()}
assert THE_MENU_CHAIN[THE_PRESS_S_IDLE] == (aes_event.press,)
A_LONG_TIMER_MS = evasync.A_LONG_TIMER_MS               # past the ticks a press brings: it has not come when the message has


def at_the_first_idle(name, *interrupts):
    """The call `name` of NOTHING_COME woken by `interrupts`, all delivered at the dispatcher's first idle."""
    return Scheduled(NOTHING_COME[name], {THE_FIRST_IDLE: interrupts})


def through_the_menu(made, *with_the_press):
    """A `Call` woken BY THE SCREEN MANAGER'S OWN MESSAGE (THE_MENU_CHAIN), `with_the_press` delivered in the idle the
    press is, after it; the "sent" mark staged set (`marked`: the menu's message does not set it)."""
    return Scheduled(marked(made), {**THE_MENU_CHAIN, THE_PRESS_S_IDLE: (aes_event.press, *with_the_press)})


EVERY_BUT_THE_TIMER_COME = dict(EVERY, timer=A_LONG_TIMER_MS)
A_KEY_AND_THE_MOUSE_ONTO_THE_BAR = "a key and the mouse onto the bar in one idle, two processes woken: a key, none queued"
WAKES_BY_AN_INTERRUPT = {
    "a key wakes: a key, none queued": at_the_first_idle("a key, none queued", RETURN),
    "a press wakes: the button down, which is up": at_the_first_idle("the button down, which is up", aes_event.press),
    "a release wakes: the button up, which is down": at_the_first_idle("the button up, which is down", aes_event.release),
    "a double click wakes: a double click": at_the_first_idle("a double click", aes_event.double_click),
    "a single click wakes: a double click": at_the_first_idle("a double click", CLICK),
    "entering wakes: a rectangle the mouse is not in": at_the_first_idle("a rectangle the mouse is not in", INTO_ELSEWHERE),
    "leaving wakes: a rectangle the mouse is to leave": at_the_first_idle("a rectangle the mouse is to leave", AWAY),
    "entering wakes: the second rectangle alone": at_the_first_idle("the second rectangle alone", INTO_ELSEWHERE),
    "leaving wakes: two rectangles": at_the_first_idle("two rectangles", AWAY),
    "the ticks wake: a timer": at_the_first_idle("a timer", A_TIMER_S_TICKS),
    "a tick wakes: a timer of less than a tick": at_the_first_idle("a timer of less than a tick", evasync.ticks(1)),
    "a key wakes: a key and a message": at_the_first_idle("a key and a message", RETURN),
    "the ticks wake: a message and a timer": at_the_first_idle("a message and a timer", A_TIMER_S_TICKS),
    "a key wakes: a key and the buttons": at_the_first_idle("a key and the buttons", RETURN),
    "a press wakes: a key and the buttons": at_the_first_idle("a key and the buttons", aes_event.press),
    "a key and a press in one idle: a key and the buttons": at_the_first_idle("a key and the buttons", RETURN, aes_event.press),
    "a press wakes: the buttons and a rectangle": at_the_first_idle("the buttons and a rectangle", aes_event.press),
    "a press, then entering, in one idle: the buttons and a rectangle": at_the_first_idle(
        "the buttons and a rectangle", aes_event.press, INTO_ELSEWHERE),
    "a key wakes: every event": at_the_first_idle("every event", RETURN),
    "a double click wakes: every event": at_the_first_idle("every event", aes_event.double_click),
    "leaving wakes: every event": at_the_first_idle("every event", AWAY),
    "entering wakes: every event": at_the_first_idle("every event", INTO_ELSEWHERE),
    "the ticks wake: every event": at_the_first_idle("every event", A_TIMER_S_TICKS),
    "a key, a double click, leaving and the ticks in one idle: every event": at_the_first_idle(
        "every event", RETURN, aes_event.double_click, AWAY, A_TIMER_S_TICKS),
    "a key wakes: eight bits held, a key, the buttons, two rectangles": at_the_first_idle(EIGHT_BITS_HELD_A_KEY_THE_BUTTONS, RETURN),
    "the ticks wake: eight bits held, a message and a timer": at_the_first_idle(EIGHT_BITS_HELD_A_MESSAGE_A_TIMER, A_TIMER_S_TICKS),
    "a release wakes: every event, the button held": at_the_first_idle("every event, the button held", aes_event.release),
    "a key wakes, the sent mark set: a key and a message": Scheduled(marked(NOTHING_COME["a key and a message"]),
                                                                    {THE_FIRST_IDLE: (RETURN,)}),
    # ...TWO PROCESSES WOKEN IN ONE IDLE: the move wakes the screen manager, the key the desk — idle moves both to the
    # ready list in one pass, the desk first (last in, first out), and the manager stands ready behind it.
    A_KEY_AND_THE_MOUSE_ONTO_THE_BAR: at_the_first_idle("a key, none queued", ONTO_THE_BAR, RETURN),
}
WAKES_BY_A_WRITER = {
    "a writer wakes: a message, none in the pipe": through_the_menu(NOTHING_COME["a message, none in the pipe"]),
    "a writer wakes: a message and a timer not run out": through_the_menu(call(desk, MESAG | TIMER, timer=A_LONG_TIMER_MS)),
    "a writer and the press's ticks in one wake: a message and a timer": through_the_menu(NOTHING_COME["a message and a timer"]),
    "a writer wakes: a key and a message": through_the_menu(NOTHING_COME["a key and a message"]),
    "a writer wakes: every event, the timer not run out": through_the_menu(call(desk, EVERY_EVENT, **EVERY_BUT_THE_TIMER_COME)),
    "a writer and the press's ticks in one wake: every event": through_the_menu(NOTHING_COME["every event"]),
    "a writer and the press's ticks: eight bits held, a message and a timer": through_the_menu(
        NOTHING_COME[EIGHT_BITS_HELD_A_MESSAGE_A_TIMER]),
    "a writer, a key and the press's ticks in one wake: a key, a message and a timer": through_the_menu(
        call(desk, KEYBD | MESAG | TIMER, timer=A_TIMER_MS), RETURN),
    "a writer, a key and the press's ticks in one wake: every event": through_the_menu(NOTHING_COME["every event"], RETURN),
    "a writer and the mouse into the rectangle: a rectangle and a message": through_the_menu(
        call(desk, M1 | MESAG, first=NOT_IN), INTO_ELSEWHERE),
    "a writer, a key, the mouse, the press's ticks: every event": through_the_menu(
        NOTHING_COME["every event"], RETURN, INTO_ELSEWHERE),
    "a writer, the desk waiting for the bar's rectangle too": through_the_menu(call(desk, M1 | MESAG, first=ON_THE_BAR)),
    "a writer, then the mouse away: both rectangles and a message": through_the_menu(
        call(desk, M1 | M2 | MESAG, first=NOT_OUT, second=NOT_IN), AWAY, INTO_ELSEWHERE),
}
# ...and the wake a writer does not make WHEN THE KEY COMES IN THE PRESS'S OWN IDLE: nothing woke the desk before the
# press did, so the key's wake is the last in and the desk runs ahead of the writer (above).
A_KEY_BEFORE_THE_WRITER_WRITES = "a key typed with the press wakes the desk before the writer writes: a key and a message"
WAKES_AHEAD_OF_THE_WRITER = {
    A_KEY_BEFORE_THE_WRITER_WRITES: through_the_menu(NOTHING_COME["a key and a message"], RETURN),
}
# ...and the wakes a key makes AT A POLL THAT IS NO IDLE (above): after the press's forks ran — a key and a message in
# one wake — and after the first move's, on OUR dispatcher's own poll: the key is polled while the screen manager
# stands woken, the manager has its turn, and the desk answers the key (the poll's place in idle's loop, held on
# every shore: `aes_switch.what_idle_tests`).
A_WRITER_AND_A_KEY = "a writer and a key in one wake: a key and a message"
A_KEY_WHILE_THE_MANAGER_STANDS_WOKEN = "a key polled while the screen manager stands woken: a key and a message"
WAKES_AT_A_POLL = {
    A_WRITER_AND_A_KEY: Scheduled(marked(NOTHING_COME["a key and a message"]), THE_MENU_CHAIN,
                                  {the_poll_after(THE_PRESS_S_IDLE): RETURN}),
    A_KEY_WHILE_THE_MANAGER_STANDS_WOKEN: Scheduled(NOTHING_COME["a key and a message"], {THE_FIRST_IDLE: (ONTO_THE_TITLE,)},
                                                    {the_poll_after(THE_FIRST_IDLE): RETURN}),
}
WAKES = {**WAKES_BY_AN_INTERRUPT, **WAKES_BY_A_WRITER, **WAKES_AHEAD_OF_THE_WRITER, **WAKES_AT_A_POLL}
ROW_LABEL = "blocked and woken — {}"


def switching_row(name):
    """The wake `name` of WAKES as a row that switches (`aes_switching.SwitchingRow`): ev_multi over the call's
    machine, taken through its schedule."""
    wake = WAKES[name]
    return aes_switching.SwitchingRow(ROW_LABEL.format(name), EV_MULTI, tuple(wake.call.arguments),
                                      functools.partial(machine_of, wake.call), wake.at_idle, at_polls=wake.at_polls)


# ...AND ONE PAST THE EVBs THERE ARE — AN ARGUMENT-CLASS MACHINE (the ROM's own iasync, eight waits of no kind: four
# EVBs left free) asked for every event: six waits. get_evb answers NULL for the fifth and the sixth, which iasync
# does not test, and both are queued over "the EVB at address 0" (`test_aes_evmulti.py` says what is pinned).
PAST_THE_LAST_EVB = call(evlib.eight_event_bits_held, EVERY_EVENT, **EVERY)


# ---- Tier 3's rows -----------------------------------------------------------------------------------------------------
def register(label, arguments, machine, *, through_line_f=False):
    """One row of ev_multi over `machine` with the frame `arguments` (`aes_event.register_row`): priced direct — the
    words that differ by nature settled from one run of the ROM's routine, `savptr` in the stack band from the start
    (it polls the keyboard), its companion run with the layer's hooks — or verified through its call word."""
    return aes_event.register_row(label, EV_MULTI, arguments, machine, hook=HOOKS, through_line_f=through_line_f,
                                  polls=True)
