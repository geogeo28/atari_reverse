"""THE EVENT BLOCKS' LISTS' MACHINES — what `src/aes/evasync.c`'s routines are proved over (`test_aes_evasync*.py`).

EVERY MACHINE IS AN ARRIVAL. signal, azombie, get_evb, evinsert, takeoff, apret, acancel and evremove work on the
scheduler's lists and a process's event blocks: its EVBs, the wait list each is on, the completed list, the free
list, the not-ready and the woken lists. None of that is poked here. A SCENARIO is the ROM's own run of something the
machine does — the dispatcher's loop taking an interrupt, a running process's evnt_multi, a message sent — WATCHED at
the eight routines' entries (`arrivals`): each time the run reaches one, the machine there (every byte of RAM the run
has changed, the stack band aside) and the frame the caller pushed are kept, as an `Arrival`. A case is then the
differential of that routine from that machine with that frame: the ROM's own call, at the moment it makes it, with
every list as the scheduler and the routines before it left them.

HOW A SCENARIO IS COMPOSED, each step the event door's own (`aes_event`): a process running as the dispatcher makes it
(`machine`, `screen_manager_running`); a call of its that finds nothing and PARKS it (`parked`, on its own supervisor
stack — and, watched, the same call on the run's stack up to dsptch, for the arrivals on the way in: `blocking`); the
interrupts that end the wait, each the ROM's own interrupt code over the machine as it stands (`key`, `press`,
`move_to`, the tick glue); then the dispatcher's loop from where it waits, to where a process comes out of its
evnt_multi (`woken`). Two delays pending at once need a THIRD process: `aes_pdpipe`'s staged application, the
labelled class — its scenarios carry the label and register no row.

WHAT A WATCHED RUN IS HELD TO: `aes_event.run_watched`'s rules — the derivation budget by its margin, no refusal by the
model — and its arrivals to the sequence the scenario DECLARES (`SCENARIOS`), which `test_aes_evasync.py` pins: the
cases are parametrized from the declaration, so a worker computes only the scenarios its cases ask for.
"""
import functools
import struct
from collections import namedtuple

from harness import BASE_IMAGE, addrs, make_image

import aes
import aes_event
import aes_pdpipe
import case
import derived
import test_aes_fmlib                   # two scenarios are composed of another battery's machines: its key queue...
import test_aes_wm_update               # ...and the screen lock held with a process queued on it
import vdi
from case import merge_pokes

EV = aes.header_constants("evasync.h")
WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES
IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG

# ---- the routines, and how each is called ----------------------------------------------------------------------------
SIGNAL, AZOMBIE, GET_EVB, EVINSERT = "AES_ROM_SIGNAL", "AES_ROM_AZOMBIE", "AES_ROM_GET_EVB", "AES_ROM_EVINSERT"
TAKEOFF, APRET, ACANCEL, EVREMOVE = "AES_ROM_TAKEOFF", "AES_ROM_APRET", "AES_ROM_ACANCEL", "AES_ROM_EVREMOVE"
SIGNATURES = {
    SIGNAL: (None, (IMAGE, LONG)),
    AZOMBIE: (None, (IMAGE, LONG)),
    GET_EVB: (aes.LONG_ANSWER, (IMAGE,)),
    EVINSERT: (None, (IMAGE, LONG, LONG)),
    TAKEOFF: (None, (IMAGE, LONG)),
    APRET: (aes.WORD_ANSWER, (IMAGE, WORD)),
    ACANCEL: (aes.WORD_ANSWER, (IMAGE, WORD)),
    EVREMOVE: (None, (IMAGE, LONG, WORD)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)
ROUTINES = tuple(SIGNATURES)
LAYER = aes_event.Layer(ROUTINES)       # a run WATCHED at the eight routines' entries (`aes_event.Layer`)
ENTRIES, FRAMES = LAYER.entries, LAYER.frames

# ---- the lists, read out of an image ---------------------------------------------------------------------------------
ZOMBIE_LIST, ELINKOFF, BPEND = aes.AES_ZOMBIE_LIST, EV["AES_ELINKOFF"], EV["AES_GL_BPEND"]
BUTTON_STATE = EV["AES_EV_BUTTON_STATE"]
NOCANCEL, COMPLETE, DELAY = EV["EVB_FLAG_NOCANCEL"], EV["EVB_FLAG_COMPLETE"], EV["EVB_FLAG_DELAY"]
LEAVING = EV["EVB_FLAG_LEAVE"]
SHELL, SCREEN_MANAGER = aes.SHELL_PD, aes.SCREEN_MANAGER_PD
RLR_IN_FORKER = aes.AES_RLR_IN_FORKER
LIST_LIMIT = aes.AES_EVB_COUNT + 1      # no list of EVBs is longer than the EVBs there are


def evlist(image, pd):
    """The EVBs of the process `pd`, by EVB_NEXT."""
    return aes.list_of(image, pd + aes.PD_EVLIST, aes.EVB_NEXT, LIST_LIMIT)


def wait_list(image, head):
    """The EVBs on the wait list whose head is at `head` (or the completed list), by EVB_LINK."""
    return aes.list_of(image, head, aes.EVB_LINK, LIST_LIMIT)


def completed(image):
    return wait_list(image, ZOMBIE_LIST)


def free_evbs(image):
    return aes.list_of(image, aes.AES_EUL, aes.EVB_NEXT, LIST_LIMIT)


def evb_of(image, evb):
    """An EVB's fields, by name."""
    return {name: aes.read_field(image, "EVB", name, evb) for name in aes.FIELDS["EVB"]}


def running(image):
    """The running process — AES_RLR_IN_FORKER while forker runs the fork functions."""
    return case.long_in(image, aes.AES_RLR)


# ---- the band a scenario's evnt_multi is handed its rectangles, its message buffer and its answers in ----------------
BAND_OFFSET = 0x3A40                    # past test_aes_fmdo.py's band (+$3a00), below aes_fslib.py's (+$3c00)
BAND_BYTES = 0x40
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES,
                         "test/aes_evasync.py: two MOBLKs, a message buffer, evnt_multi's answers")
MOBLK_BYTES = aes_event.MOBLK_BYTES
FIRST_RECT_AT = BAND_AT
SECOND_RECT_AT = FIRST_RECT_AT + MOBLK_BYTES
MESSAGE_AT = SECOND_RECT_AT + MOBLK_BYTES + WORD_BYTES
ANSWERS_AT = MESSAGE_AT + aes_event.MESSAGE_BYTES
ANSWER_WORDS = 6                        # mouse x, y, buttons, shift keys, the key, the clicks ($fe6bd6, $fe6bf2)
assert ANSWERS_AT + ANSWER_WORDS * WORD_BYTES <= BAND_AT + BAND_BYTES

MU_KEYBD, MU_BUTTON, MU_M1, MU_M2 = aes.EV_MU_KEYBD, aes.EV_MU_BUTTON, aes.EV_MU_M1, aes.EV_MU_M2
MU_MESAG, MU_TIMER = aes.EV_MU_MESAG, aes.EV_MU_TIMER
LEAVE, ENTER = 1, 0                     # a MOBLK's first word: wait for the mouse to leave the rectangle, or enter it


def moblk(leave, x, y, w, h):
    return struct.pack(">5h", leave, x, y, w, h)


def button_wait(clicks, mask=aes_event.LEFT_BUTTON, state=aes_event.LEFT_BUTTON):
    """ev_multi's button parameter: the clicks, the buttons' mask and the state waited for ($fe68a4 packs the same)."""
    return clicks << aes.BUTTON_PARM_CLICKS_SHIFT | mask << aes.BUTTON_PARM_MASK_SHIFT | state


def ev_multi_frame(flags, *, first=None, second=None, timer=0, button=0):
    """`(frame, pokes)`: evnt_multi's frame for `flags`, its MOBLKs staged in the band."""
    pokes = merge_pokes({FIRST_RECT_AT: first} if first else None, {SECOND_RECT_AT: second} if second else None)
    frame = aes_event.EV_MULTI_FRAME.pack(flags, FIRST_RECT_AT if first else 0, SECOND_RECT_AT if second else 0, timer,
                                          button, MESSAGE_AT, ANSWERS_AT)
    return frame, pokes


# ---- a run WATCHED at the eight routines' entries (`aes_event.Layer`: the family every layer's battery shares) ---------
Arrival, Watched = aes_event.LayerArrival, aes_event.Watched
machine_of = LAYER.machine_of           # `memory` as pokes over the snapshot, the stack band out


def watched(pokes, entry, ends, frame=b"", once_past=None):
    """The ROM's `entry` over `pokes` (its `frame` where a `jsr` leaves it), WATCHED AT THE EIGHT ROUTINES' ENTRIES
    (`aes_event.Layer.watched`: the `Arrival` kept at each — the frame its caller pushed, the machine there) until it
    reaches one of `ends` (after `once_past`, when named) — or returns, with no end named for it: every arrival, in
    order, and the machine at the end."""
    return LAYER.watched(pokes, entry, ends, frame, once_past)


def arrivals(pokes, entry, ends, frame=b""):
    """...the arrivals alone."""
    return watched(pokes, entry, ends, frame).arrivals


# ---- the steps a scenario is composed of -----------------------------------------------------------------------------
ticks = aes_event.ticks                  # `ticks(n)`: n ticks of the system timer, an interrupt `taken` delivers


def taken(pokes, *interrupts):
    """`pokes` continued by `interrupts` (`aes_event.key(...)`, `press`, `move_to(x, y)`, `ticks(n)`), each the ROM's
    own interrupt code over the machine as the one before left it."""
    image = make_image(pokes)
    for interrupt in interrupts:
        pokes = merge_pokes(pokes, interrupt(image))
    return pokes


def woken(pokes):
    """The dispatcher's loop from where it waits, over `pokes` (an interrupt taken), to where a process comes out of
    its evnt_multi: the arrivals."""
    return arrivals(pokes, addrs.AES_ROM_DISP_LOOP, {addrs.AES_ROM_EV_MULTI_RETURN})


def blocking(pokes, entry, frame):
    """A running process's call of `entry` that finds nothing and reaches dsptch: the arrivals on the way in."""
    return arrivals(pokes, entry, {addrs.AES_ROM_DSPTCH}, frame)


def returning(pokes, entry, frame):
    """...and one that returns: every arrival of the call."""
    return arrivals(pokes, entry, frozenset(), frame)


def waited_and_woken(machine, frame, *interrupts):
    """A process running over `machine` calls evnt_multi with `frame`, parks, and is woken by `interrupts`: the
    arrivals of the call on its way in, then those of the dispatcher's loop and of evnt_multi's tail."""
    on_the_way_in = blocking(machine, addrs.AES_ROM_EV_MULTI, frame)
    parked = aes_event.parked(addrs.AES_ROM_EV_MULTI, frame, machine)
    return on_the_way_in + woken(taken(parked, *interrupts))


# ---- THE SCENARIOS -----------------------------------------------------------------------------------------------------
# Each: how the ROM's run is made, and the arrivals it DECLARES, in order — what the cases are parametrized from, and
# what the run is held to (`scenario`). The snapshot's two processes are parked in their evnt_multi: the desk (PD0) for
# a key, a double click and a message, the screen manager (PD1) for a key, a press and the mouse onto the menu bar.
Scenario = namedtuple("Scenario", "run arrivals")
RETURN = aes_event.key(aes_event.RETURN_KEY)
ONTO_THE_BAR = aes_event.move_to(*aes_event.MENU_BAR_POINT)
# A rectangle round the snapshot's mouse, and a point outside it.
ROUND_THE_MOUSE = (150, 90, 20, 20)
OUTSIDE = (300, 150)
AWAY = aes_event.move_to(*OUTSIDE)
WHOLE_SCREEN = (0, 0, 640, 200)
ELSEWHERE = (300, 150, 20, 20)          # a rectangle the mouse is not in, its x and y not 0 (a mouse wait's parameter)
# A rectangle whose x has a LOW BYTE of 1 — evremove reads the low byte of a mouse wait's x as its clicks
# (`aes/evasync.h`): one click, where the whole word would be 257 — and a point inside it.
AT_X_257 = (257, 0, 100, 100)
INSIDE_X_257 = aes_event.move_to(300, 50)
TICK_MS = case.word_in(BASE_IMAGE, EV["AES_GL_TICK_MS"])     # 20: what ev_multi divides a timer's milliseconds by
A_TIMER_MS = 100
A_TIMER_TICKS = A_TIMER_MS // TICK_MS
A_LONG_TIMER_MS = 1000
SINGLE, DOUBLE = 1, 2
AP_WRITE = aes.AP_RDWR_WRITE
MN_SELECTED_MESSAGE = 10                # the message a menu selection is sent by (GEM's MN_SELECTED: mn_do's, band 3)
A_TITLE, AN_ITEM = 5, 30                # ...its two words: any title and item of a menu tree
A_MESSAGE = aes_pdpipe.message(MN_SELECTED_MESSAGE, A_TITLE, AN_ITEM, sender=aes_pdpipe.SCREEN_MANAGER_PID)
EV_BLOCK_KEYBOARD = 5                   # iasync's code for a keyboard wait ($fef7a2's fifth arm, akbin)
END_UPDATE = aes.WM_END_UPDATE          # wm_update's code: the screen lock released

WOKEN = (EVREMOVE, AZOMBIE, SIGNAL)     # an event posted to a wait by a fork function
WAITS = (GET_EVB, EVINSERT)             # a wait queued by iasync
EVERY_EVENT = "every event waited for, the timer comes"
QUEUED_OF_EVERY_EVENT = 5               # its waits put on a wait list: a key, a button, two rectangles, a message
WAITS_OF_EVERY_EVENT = QUEUED_OF_EVERY_EVENT + 1        # ...and its delay's, which adelay places itself


def _woken_by(*interrupts):
    return lambda: woken(taken({}, *interrupts))


def _evnt_multi(flags, interrupts, **parameters):
    def run():
        frame, pokes = ev_multi_frame(flags, **parameters)
        return waited_and_woken(merge_pokes(aes_event.machine(), pokes), frame, *interrupts)
    return run


def _message_to_the_desk():
    frame = aes_event.AP_RDWR_FRAME.pack(AP_WRITE, case.word_in(BASE_IMAGE, SHELL + aes.PD_PID), len(A_MESSAGE),
                                         MESSAGE_AT)
    return returning(merge_pokes(aes_event.screen_manager_running(), {MESSAGE_AT: A_MESSAGE}), addrs.AES_ROM_AP_RDWR,
                     frame)


def _queued_key_read():
    """...over `test_aes_fmlib`'s key queue, polled by the ROM's chkkbd and forker."""
    return returning(test_aes_fmlib.queued(1), addrs.AES_ROM_EV_BLOCK,
                     aes_event.EV_BLOCK_FRAME.pack(EV_BLOCK_KEYBOARD, 0))


def _lock_released_to_a_waiter():
    """...over `test_aes_wm_update`'s lock: PD0 holding it with PD1 queued on it, every step the scheduler's."""
    return blocking(test_aes_wm_update.waited_on(), addrs.AES_ROM_WM_UPDATE, aes_event.frame_of(("w", END_UPDATE)))


@functools.cache
def parked_for_a_key_after_a_wider_wait():
    """The desk PARKED waiting for a key alone, after an evnt_multi for every event that the timer ended: the free list
    then holds the EVBs of that wider wait as takeoff and apret left them — each still naming the desk and an event
    bit the desk no longer waits for. A machine for the one arm of signal no caller reaches (`test_aes_evasync.py`)."""
    frame, pokes = ev_multi_frame(MU_KEYBD | MU_BUTTON | MU_M1 | MU_M2 | MU_MESAG | MU_TIMER,
                                  first=moblk(LEAVE, *ROUND_THE_MOUSE), second=moblk(ENTER, *ELSEWHERE),
                                  timer=A_TIMER_MS, button=button_wait(SINGLE))
    parked = aes_event.parked(addrs.AES_ROM_EV_MULTI, frame, merge_pokes(aes_event.machine(), pokes))
    back = watched(taken(parked, ticks(A_TIMER_TICKS)), addrs.AES_ROM_DISP_LOOP, {addrs.AES_ROM_EV_MULTI_RETURN})
    return aes_event.parked(addrs.AES_ROM_EV_MULTI, aes_event.KEY_WAIT, back.machine)


# A THIRD PROCESS — two delays pending at once — is `aes_pdpipe`'s STAGED APPLICATION, the labelled machine class: the
# ROM's own pstart over a stub of three instructions that makes ONE Line-F call (here ev_timer). Every scenario over it
# carries the class's label in its name and registers no row.
STAGED_APPLICATION = aes_pdpipe.STAGED_APPLICATION
# A scenario every layer of the family declares under one name: its own run of the same thing a user does.
THE_BAR_WAKES_THE_MANAGER = "the mouse onto the bar wakes the screen manager"


def register_rows(at, register, rows, through_line_f=()):
    """A LAYER'S ROWS REGISTERED — the one spelling the family's batteries end on. Each of `rows`, `(label, scenario,
    routine, which)`, is the ROM-made arrival `at(scenario, routine, which)` handed to the layer's `register(label,
    routine, arguments, machine)`: priced. Each of `through_line_f`, `(scenario, routine, which)`, is registered
    again as "its caller's call": verified through its Line-F call word, unpriced. A STAGED APPLICATION's machines
    are Tier 1 only: one named for a row is refused."""
    called = [("its caller's call", *through) for through in through_line_f]
    for is_called, (label, scenario, routine, which) in [*((False, row) for row in rows), *((True, row) for row in called)]:
        assert STAGED_APPLICATION not in scenario, f"{scenario}: a staged application's machines are Tier 1 only"
        arrival = at(scenario, routine, which)
        register(label, routine, arrival.arguments, arrival.machine, **({"through_line_f": True} if is_called else {}))
A_SHORT_TIMER_MS, A_LONGER_TIMER_MS = 200, 600


def _a_key_with_two_timers_running(own_ms, application_ms):
    """The desk starts the application, then waits for a key or `own_ms`; the dispatcher enters the application, whose
    one call is ev_timer(`application_ms`) — it parks, the machine idles with both delays on the delay list; Return
    then ends the desk's wait, and its evnt_multi cancels its delay."""
    def run():
        application = aes_pdpipe.staged_application("AES_ROM_EV_TIMER", application_ms)
        frame, pokes = ev_multi_frame(MU_KEYBD | MU_TIMER, timer=own_ms)
        machine = merge_pokes(application.machine, pokes)
        on_the_way_in = blocking(machine, addrs.AES_ROM_EV_MULTI, frame)
        parked = aes_event.parked(addrs.AES_ROM_EV_MULTI, frame, machine)
        aes_pdpipe.vet_the_application(application, make_image(parked))       # ...which the dispatcher enters next
        both_parked = watched(parked, addrs.AES_ROM_DISP_LOOP, {addrs.AES_ROM_DISP_LOOP},
                              once_past=addrs.AES_ROM_SAVESTATE)
        return on_the_way_in + both_parked.arrivals + woken(taken(both_parked.machine, RETURN))
    return run


SCENARIOS = {
    "a key wakes the desk": Scenario(
        _woken_by(RETURN), WOKEN + (ACANCEL, TAKEOFF, TAKEOFF, APRET)),
    THE_BAR_WAKES_THE_MANAGER: Scenario(
        _woken_by(ONTO_THE_BAR), WOKEN + (ACANCEL, TAKEOFF, TAKEOFF, APRET)),
    "a press wakes the desk": Scenario(
        _woken_by(aes_event.press), WOKEN + (ACANCEL, TAKEOFF, TAKEOFF, APRET)),
    "a press and a key in one idle wake the desk": Scenario(
        _woken_by(RETURN, aes_event.press), WOKEN + WOKEN + (ACANCEL, TAKEOFF, APRET, APRET)),
    "the mouse onto the bar and a press in one idle": Scenario(
        _woken_by(ONTO_THE_BAR, aes_event.press), WOKEN + WOKEN + (ACANCEL, TAKEOFF, APRET, APRET)),
    EVERY_EVENT: Scenario(
        _evnt_multi(MU_KEYBD | MU_BUTTON | MU_M1 | MU_M2 | MU_MESAG | MU_TIMER, (ticks(A_TIMER_TICKS),),
                    first=moblk(LEAVE, *ROUND_THE_MOUSE), second=moblk(ENTER, *ELSEWHERE),
                    timer=A_TIMER_MS, button=button_wait(DOUBLE)),
        WAITS * QUEUED_OF_EVERY_EVENT + (GET_EVB,) + WOKEN + (ACANCEL,) + (TAKEOFF,) * QUEUED_OF_EVERY_EVENT + (APRET,)),
    "a double click ends a double-click wait": Scenario(
        _evnt_multi(MU_BUTTON | MU_M1, (aes_event.double_click,), first=moblk(LEAVE, *ROUND_THE_MOUSE),
                    button=button_wait(DOUBLE)),
        WAITS * 2 + WOKEN + (ACANCEL, TAKEOFF, APRET)),
    "the mouse leaves a rectangle while a double click is waited for": Scenario(
        _evnt_multi(MU_BUTTON | MU_M1, (AWAY,), first=moblk(LEAVE, *ROUND_THE_MOUSE), button=button_wait(DOUBLE)),
        WAITS * 2 + WOKEN + (ACANCEL, TAKEOFF, APRET)),
    "the mouse enters a rectangle at x 257 while a double click is waited for": Scenario(
        _evnt_multi(MU_BUTTON | MU_M1, (INSIDE_X_257,), first=moblk(ENTER, *AT_X_257), button=button_wait(DOUBLE)),
        WAITS * 2 + WOKEN + (ACANCEL, TAKEOFF, APRET)),
    "a key ends a wait for a double click": Scenario(
        _evnt_multi(MU_KEYBD | MU_BUTTON, (RETURN,), button=button_wait(DOUBLE)),
        WAITS * 2 + WOKEN + (ACANCEL, TAKEOFF, APRET)),
    "a key ends a wait with a timer running": Scenario(
        _evnt_multi(MU_KEYBD | MU_TIMER, (RETURN,), timer=A_LONG_TIMER_MS),
        WAITS + (GET_EVB,) + WOKEN + (ACANCEL, TAKEOFF, APRET)),
    "two rectangles, the first one waited for left": Scenario(
        _evnt_multi(MU_M1 | MU_M2, (AWAY,), first=moblk(LEAVE, *ROUND_THE_MOUSE), second=moblk(LEAVE, *WHOLE_SCREEN)),
        WAITS * 2 + WOKEN + (ACANCEL, TAKEOFF, APRET)),
    "two rectangles, the second one waited for left": Scenario(
        _evnt_multi(MU_M1 | MU_M2, (AWAY,), first=moblk(LEAVE, *WHOLE_SCREEN), second=moblk(LEAVE, *ROUND_THE_MOUSE)),
        WAITS * 2 + WOKEN + (ACANCEL, TAKEOFF, APRET)),
    "a press, then the mouse leaves, in one idle": Scenario(
        _evnt_multi(MU_BUTTON | MU_M1, (aes_event.press, AWAY), first=moblk(LEAVE, *ROUND_THE_MOUSE),
                    button=button_wait(SINGLE)),
        WAITS * 2 + WOKEN + WOKEN + (ACANCEL, APRET, APRET)),
    "the timer comes and the mouse goes onto the bar in one idle": Scenario(
        _evnt_multi(MU_TIMER, (ticks(A_TIMER_TICKS), ONTO_THE_BAR), timer=A_TIMER_MS),
        (GET_EVB,) + WOKEN + WOKEN + (ACANCEL, TAKEOFF, TAKEOFF, APRET)),
    "a message to the parked desk": Scenario(
        _message_to_the_desk, (GET_EVB, AZOMBIE, SIGNAL, AZOMBIE, SIGNAL, APRET)),
    "a queued key read": Scenario(
        _queued_key_read, (GET_EVB, AZOMBIE, SIGNAL, APRET)),
    "the lock released to a waiter": Scenario(
        _lock_released_to_a_waiter, (AZOMBIE, SIGNAL)),
    f"{STAGED_APPLICATION}: a key ends a wait whose delay has a longer one behind it": Scenario(
        _a_key_with_two_timers_running(A_SHORT_TIMER_MS, A_LONGER_TIMER_MS),
        WAITS + (GET_EVB,) * 2 + WOKEN + (ACANCEL, TAKEOFF, APRET)),
    f"{STAGED_APPLICATION}: a key ends a wait whose delay is behind a shorter one": Scenario(
        _a_key_with_two_timers_running(A_LONGER_TIMER_MS, A_SHORT_TIMER_MS),
        WAITS + (GET_EVB,) * 2 + WOKEN + (ACANCEL, TAKEOFF, APRET)),
}


@derived.kept
def _run_of(name):
    """The ROM's run of the scenario `name`: a derivation, kept by content."""
    return SCENARIOS[name].run()


# What the scenarios declare, and each one's run held to it (`aes_event.Scenarios`): `scenario(name)` its arrivals,
# `cases(*routines)` the `(scenario, nth)` pairs a battery is parametrized from, `case_id`, `arrival(name, nth)`,
# `nth_of(name, routine, which)` and `at(name, routine, which)`.
DECLARED = aes_event.Scenarios({name: declared.arrivals for name, declared in SCENARIOS.items()}, _run_of)
scenario, cases, case_id = DECLARED.scenario, DECLARED.cases, DECLARED.case_id
arrival, nth_of, at = DECLARED.arrival, DECLARED.nth_of, DECLARED.at
