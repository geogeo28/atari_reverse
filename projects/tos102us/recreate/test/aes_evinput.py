"""THE INPUT LAYER'S MACHINES — what `src/aes/evinput.c` and `src/aes/evfork.c` are proved over
(`test_aes_evinput*.py`, `test_aes_evfork*.py`).

EVERY MACHINE IS AN ARRIVAL (`aes_evasync`'s shape, at this layer's entries): a SCENARIO is the ROM's own run of
something the machine does, WATCHED at the entries of the input layer's routines (`aes_event.EntryStops`); each time
the run reaches one, the machine there and the frame its caller pushed are kept. A case is the differential of that
routine from that machine with that frame — the ROM's own call, at the moment it makes it.

WHAT RUNS IN A SCENARIO, each step the ROM's own code over the machine the step before left:
  * AN INTERRUPT, WATCHED (`mouse_packet`, `tick`): the VDI's mouse interrupt over a packet (it calls the AES's button
    glue — b_click — and motion glue — forkq(mchange)) and the AES's tick glue (b_delay, forkq(tchange)): the fork
    queue is FILLED BY THE ROM'S OWN ISRs, never poked. `aes_event.press` / `move_to` / `ticks` are the same
    interrupts unwatched; `test_aes_evinput.py` holds a watched one to its unwatched twin, byte for byte.
  * A KEY (`aes_event.key`): the BIOS's keyboard handler — no routine of this layer runs in it (the AES POLLS).
  * THE DISPATCHER'S LOOP from where the snapshot waits in it (`dispatcher`): forker runs the queue — the fork
    functions, the posts — and idle polls the keyboard (chkkbd), until a process comes out of its evnt_multi, or
    for a machine nothing wakes until the n-th poll of an idle that would spin for ever.
  * A RUNNING PROCESS'S CALL (`call`): evnt_multi, wind_update, appl_trecord, appl_tplay — to its return or to dsptch.
"""
import struct
from collections import namedtuple

from harness import BASE_IMAGE, addrs, emu, make_image
from recreate_kit import rom_bench

import aes
import aes_event
import aes_evasync
import aes_pdpipe
import case
import derived
import isr
import routines
import test_aes_wm_update
import vdi
from case import merge_pokes

EVI = aes.header_constants("evinput.h")
EVF = aes.header_constants("evfork.h")
FM = aes.header_constants("fmlib.h")
WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES
IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG

# ---- the routines, and how each is called ----------------------------------------------------------------------------
NQ, DOWNORUP, POST_KEYBD = "AES_ROM_NQ", "AES_ROM_DOWNORUP", "AES_ROM_POST_KEYBD"
POST_BUTTON, POST_MOUSE, INOROUT = "AES_ROM_POST_BUTTON", "AES_ROM_POST_MOUSE", "AES_ROM_INOROUT"
MOWNER, SET_MOWN, CT_CHGOWN = "AES_ROM_MOWNER", "AES_ROM_SET_MOWN", "AES_ROM_CT_CHGOWN"
B_CLICK, B_DELAY = "AES_ROM_B_CLICK", "AES_ROM_B_DELAY"
FORKQ, FORKER, CHKKBD = "AES_ROM_FORKQ", "AES_ROM_FORKER", "AES_ROM_CHKKBD"
KCHANGE, BCHANGE, MCHANGE, TCHANGE = "AES_ROM_KCHANGE", "AES_ROM_BCHANGE", "AES_ROM_MCHANGE", "AES_ROM_TCHANGE"
DRAWRAT = "AES_ROM_DRAWRAT"
SIGNATURES = {
    NQ: (None, (IMAGE, WORD, LONG)),
    DOWNORUP: (aes.WORD_ANSWER, (IMAGE, WORD, LONG)),
    POST_KEYBD: (None, (IMAGE, LONG, WORD)),
    POST_BUTTON: (None, (IMAGE, LONG, WORD, WORD)),
    POST_MOUSE: (None, (IMAGE, LONG, WORD, WORD)),
    INOROUT: (aes.WORD_ANSWER, (IMAGE, LONG, WORD, WORD)),
    MOWNER: (aes.WORD_ANSWER, (IMAGE, WORD, WORD)),
    SET_MOWN: (None, (IMAGE, LONG, LONG)),
    CT_CHGOWN: (aes.WORD_ANSWER, (IMAGE, LONG, LONG)),
    B_CLICK: (None, (IMAGE, WORD)),
    B_DELAY: (None, (IMAGE, WORD)),
    FORKQ: (None, (IMAGE, LONG, LONG)),
    FORKER: (None, (IMAGE,)),
    CHKKBD: (None, (IMAGE,)),
    KCHANGE: (None, (IMAGE, WORD, WORD)),
    BCHANGE: (None, (IMAGE, WORD, WORD)),
    MCHANGE: (None, (IMAGE, WORD, WORD)),
    TCHANGE: (None, (IMAGE, LONG)),
    DRAWRAT: (None, (IMAGE, WORD, WORD)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)
ROUTINES = tuple(SIGNATURES)
# The routines that reach NO hook: each run of their C is guarded in a fork of the worker (`aes_event.run_core_guarded`).
# The other four reach the VDI's (`recreate_call_vector`: chkkbd's and mchange's polls) or the register-carrying one
# (`recreate_call_vector_registers`: forker's fork functions, drawrat's cursor routine) — `run`, below.
REACH_A_HOOK = (FORKER, CHKKBD, MCHANGE, DRAWRAT)
FORK_GUARDED = tuple(name for name in ROUTINES if name not in REACH_A_HOOK)
FORK_FUNCTIONS = (KCHANGE, BCHANGE, MCHANGE, TCHANGE)

SHELL, SCREEN_MANAGER = aes.SHELL_PD, aes.SCREEN_MANAGER_PD

# ---- a run WATCHED at the layer's entries (`aes_event.Layer`: the family every layer's battery shares) -----------------
Arrival, Watched = aes_event.LayerArrival, aes_event.Watched
PACKET_BYTES = 3                        # a relative mouse packet: the header, dx, dy (`aes_event._packet`)
# What no machine keeps of a watched run: its own stack frames, and the packet an interrupt was handed (an input
# staged for the run alone, as `aes_event`'s unwatched interrupts stage it).
NOT_THE_MACHINE_S = frozenset(case.STACK_BAND) | frozenset(range(aes_event.PACKET_AT, aes_event.PACKET_AT + PACKET_BYTES))


_SNAPSHOT = bytes(BASE_IMAGE)        # ...as bytes: a slice of it laid into a run's buffer is one copy
_NOT_KEPT = ((case.STACK_BAND.start, case.STACK_BAND.stop), (aes_event.PACKET_AT, aes_event.PACKET_AT + PACKET_BYTES))


# THE IMAGE OF THE MACHINE A STEP JUST MADE, kept for the step after it (one slot, held by the machine's own identity —
# the slot keeps the dict alive, so its identity cannot be another's): a click's count is eleven ticks, each a run
# over the machine the tick before left, and building a sixteen-megabyte image from pokes for each is most of a
# scenario. THE RUN'S OWN BUFFER is that image — nothing reads it after its run — once the two bands a machine keeps
# nothing of are put back in it; and the step after TAKES it (its run stores into it), so nothing is copied at all.
# OVER THE SNAPSHOT ALONE: a machine is its pokes over the snapshot (`machine_of`), and the buffer is `make_image` of
# them only while the snapshot is the base in force. Under another (`harness.set_base_image`: the sweep that scrambles
# what no capture reproduces) nothing is remembered, and every step's image is built from its pokes over THAT base —
# what `make_image` makes of them, by `make_image`.
_LAST_MADE = [None, None]
_SNAPSHOT_S_KEY = derived.image_key(_SNAPSHOT)


def _kept(memory):
    """`machine_of(memory)` — and `memory` itself, the run's own buffer, made that machine's image and remembered for
    the next step (`image_of`): the caller reads it no more."""
    pokes = machine_of(memory)
    if derived.base_key() != _SNAPSHOT_S_KEY:
        _LAST_MADE[:] = None, None
        return pokes
    for lo, hi in _NOT_KEPT:
        memory[lo:hi] = _SNAPSHOT[lo:hi]
    _LAST_MADE[:] = pokes, memory
    return pokes


def image_of(pokes):
    """`make_image(pokes)`, to run over — the remembered image TAKEN, when `pokes` is the machine the step before just
    made (remembered no longer: the run stores into it), built from the pokes otherwise."""
    if pokes is not _LAST_MADE[0]:
        return make_image(pokes)
    image = _LAST_MADE[1]
    _LAST_MADE[:] = None, None
    return image


def seen_in(pokes):
    """...the same image to READ, left where it is for the step that will run over it: a caller stores nothing in it."""
    return _LAST_MADE[1] if pokes is _LAST_MADE[0] else make_image(pokes)


# ...a rectangle an arrival's caller held in its own frame, restaged (`_Arrivals`), and appl_trecord's buffer.
BAND_OFFSET = 0x3B00                    # past test/aes_evasync.py's band (+$3a40), below aes_fslib.py's (+$3c00)
BAND_BYTES = 0xC0
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES,
                         "test/aes_evinput.py: a rectangle a caller held in its frame, appl_trecord's buffer, "
                         "an argument's record, a cursor routine")
RECT_AT, RECT_BYTES = BAND_AT, 8
RECORD_AT, RECORD_BYTES = BAND_AT + 0x10, 0x40
# ...and what an ARGUMENT-CLASS case hands in that no machine holds: a record its argument points at (a key queue, a
# process's CDA pointer) and a cursor routine with the two words it logs.
ARGUMENT_AT, ARGUMENT_BYTES = BAND_AT + 0x60, 0x40
CURSOR_ROUTINE_AT, CURSOR_LOG_AT = BAND_AT + 0xA0, BAND_AT + 0xB0
assert RECORD_AT + RECORD_BYTES <= ARGUMENT_AT and ARGUMENT_AT + ARGUMENT_BYTES <= CURSOR_ROUTINE_AT
assert CURSOR_LOG_AT + 2 * WORD_BYTES <= BAND_AT + BAND_BYTES


def _rectangle_moved_out_of_the_stack(name, arguments, memory, machine):
    """ct_chgown handed a rectangle IN ITS CALLER'S OWN FRAME (w_setactive's local): the band a machine keeps nothing
    of. Restaged where a case's frame can name it — the same eight bytes, another address (`aes_event.Layer`'s
    `restaged`)."""
    if name != CT_CHGOWN or arguments[1] not in case.STACK_BAND:
        return arguments, machine
    rectangle = bytes(memory[arguments[1]:arguments[1] + RECT_BYTES])
    return (arguments[0], RECT_AT), merge_pokes(machine, {RECT_AT: rectangle})


LAYER = aes_event.Layer(ROUTINES, left_out=NOT_THE_MACHINE_S, restaged=_rectangle_moved_out_of_the_stack)
ENTRIES, FRAMES = LAYER.entries, LAYER.frames
machine_of = LAYER.machine_of           # `memory` as pokes over the snapshot, but the run's own (NOT_THE_MACHINE_S)


def watched(pokes, entry, ends=(), frame=b"", once_past=None, stop_at=None, must_end=False):
    """The ROM's `entry` over `pokes` (its `frame` where a `jsr` leaves it), WATCHED at the layer's entries
    (`aes_event.Layer.watched`) until it reaches one of `ends`, or its `stop_at` arrival (`(routine, nth)`), or
    returns: every arrival, in order, and the machine at the end — for a run that returned, the memory it left.
    `must_end`: the `stop_at` arrival is only a BOUND (a loop that would spin for ever), and reaching it is refused by
    name."""
    return LAYER.watched(pokes, entry, ends, frame, once_past, stop_at, must_end)


def interrupt(pokes, entry, regs=None, inputs=None):
    """AN INTERRUPT's ROM code `entry` over `pokes`, WATCHED at the layer's entries (`rom_bench.watched_original`:
    entered with `regs`, `inputs` staged for the run alone): its arrivals, and the machine it leaves — held to a
    derivation's margin and the model's refusals, as `aes_event.run_watched` holds its runs."""
    memory = image_of(pokes)
    for at, data in (inputs or {}).items():
        memory[at:at + len(data)] = data
    seen = LAYER.watch()
    try:
        rom_bench.watched_original(memory, entry, seen.watch, regs, max_insns=aes_event.DERIVATION_INSNS)
    finally:
        rom_bench.vet_the_run_just_made(f"the watched interrupt at {entry:#x}")
    insns = aes_event.run_cost()["insns"]
    assert insns * aes_event.DERIVATION_MARGIN <= aes_event.DERIVATION_INSNS, f"the interrupt at {entry:#x} ran {insns}"
    return Watched(tuple(seen.arrivals), _kept(memory))


# ---- the steps a scenario is composed of: each `step(pokes)` answers a Watched ----------------------------------------
# THE INTERRUPTS ARE `aes_event`'s OWN SEQUENCES (its one spelling of what a user does: PRESSING, CLICKING, `moving_to`
# ...), taken here by a runner that WATCHES each at the layer's entries (`interrupt`) where `aes_event.taken_in_place`
# only keeps what was written — `test_aes_evinput.py` holds a watched one to its unwatched twin, byte for byte.
NO_BUTTON, LEFT_DOWN = aes_event.NO_BUTTON_PACKET, aes_event.LEFT_DOWN_PACKET


def taken_watched(sequence_of_interrupts):
    """`aes_event`'s sequence of interrupts as a step: each the ROM's own interrupt code, watched, over the machine
    the one before left — the sequence reading the machine as it goes (the image the last step kept, `seen_in`)."""
    def step(pokes):
        made = Watched((), pokes)
        for each in sequence_of_interrupts(lambda: seen_in(made.machine)):
            more = interrupt(made.machine, *each)
            made = Watched(made.arrivals + more.arrivals, more.machine)
        return made
    return step


def mouse_packet(header, dx=0, dy=0):
    """The VDI's mouse interrupt over one relative packet: `header` its buttons, (`dx`, `dy`) its move."""
    return taken_watched(lambda _image_now: iter((aes_event.mouse_packet(header, dx, dy),)))


tick = taken_watched(aes_event.ticking(1))                              # one tick of the system timer
until_the_click_is_counted = taken_watched(aes_event.click_counted)     # ticks until an open click count has run out


def unwatched(interrupt_):
    """One of `aes_event`'s interrupts (`key(...)`, `ticks(n)`) as a step: no arrival kept."""
    def step(pokes):
        return Watched((), merge_pokes(pokes, interrupt_(make_image(pokes))))
    return step


def sequence(*steps):
    """`steps`, one after the other, as one step."""
    def step(pokes):
        arrivals = ()
        for each in steps:
            made = each(pokes)
            arrivals, pokes = arrivals + made.arrivals, made.machine
        return Watched(arrivals, pokes)
    return step


def moves(*deltas):
    """The mouse moved by each of `deltas`, a packet each, no button changed (the buttons as the VDI holds them)."""
    return taken_watched(aes_event.moving_by(*deltas))


def move_to(x, y):
    """The mouse moved to (`x`, `y`), a packet at a time (`aes_event.move_to`'s packets, watched)."""
    return taken_watched(aes_event.moving_to(x, y))


PRESS, RELEASE = taken_watched(aes_event.PRESSING), taken_watched(aes_event.RELEASING)
CLICK, DOUBLE_CLICK = taken_watched(aes_event.CLICKING), taken_watched(aes_event.DOUBLE_CLICKING)


IDLE_POLLS_BOUND = 40                   # an idle that polls this often wakes nobody: more than any scenario's keys
# HOW FAR A MACHINE NOTHING WAKES IS RUN, in idle's keyboard polls (`dispatcher(polls)` stops AT that poll — the loop
# polls first, then serves the fork queue): to the second poll is ONE whole pass, the forks the interrupts queued
# served; to the third a second pass, for what the first pass's own poll or forks queued in turn (a key polled, a
# timer run out); to the fifth, the four passes a recording's end key takes to come through.
ONE_PASS, TWO_PASSES, FOUR_PASSES = 2, 3, 5


def dispatcher(polls=None):
    """THE DISPATCHER'S LOOP from where the snapshot waits in it: until a process comes out of its evnt_multi — or,
    with `polls`, until idle's `polls`-th keyboard poll (a machine nothing wakes: the loop would poll for ever)."""
    def step(pokes):
        if polls:
            return watched(pokes, addrs.AES_ROM_DISP_LOOP, stop_at=(CHKKBD, polls))
        return watched(pokes, addrs.AES_ROM_DISP_LOOP, {addrs.AES_ROM_EV_MULTI_RETURN},
                       stop_at=(CHKKBD, IDLE_POLLS_BOUND), must_end=True)
    return step


def call(entry, frame, parks=False, staged=None):
    """A running process's call of the ROM's `entry` with `frame` (and `staged` pokes it reads): to its return, or —
    one that `parks` — to dsptch, the machine then the one `aes_event.parked` makes (the call made again on the
    process's own stack, to the dispatcher's loop)."""
    def step(pokes):
        pokes = merge_pokes(pokes, staged)
        if not parks:
            return watched(pokes, entry, frame=frame)
        on_the_way_in = watched(pokes, entry, {addrs.AES_ROM_DSPTCH}, frame)
        return Watched(on_the_way_in.arrivals, aes_event.parked(entry, frame, pokes))
    return step


def evnt_multi(flags, parks=True, **parameters):
    """A running process's evnt_multi (`aes_evasync.ev_multi_frame`'s parameters) — one that PARKS it, unless said to
    return (an event it asks for has come already)."""
    frame, pokes = aes_evasync.ev_multi_frame(flags, **parameters)
    return call(addrs.AES_ROM_EV_MULTI, frame, parks=parks, staged=pokes)


def run_scenario(start, *steps):
    """`steps` over the machine `start` (pokes, or a callable making them): the Watched of the whole."""
    return sequence(*steps)(start() if callable(start) else start)


# ---- THE SCENARIOS ------------------------------------------------------------------------------------------------------
# Each: the machine it starts from, the steps, and the arrivals it DECLARES, in order (`DECLARED`: what the cases are
# parametrized from, and what the run is held to — a missed arrival is a declared one that did not come). The
# snapshot's two processes are parked in their evnt_multi: the desk (PD0) for a key, a DOUBLE click and a message, the
# screen manager (PD1) for a key, a press and the mouse onto the menu bar.
Scenario = namedtuple("Scenario", "start steps arrivals")
SNAPSHOT = {}
MU_KEYBD, MU_BUTTON, MU_M1, MU_M2 = aes.EV_MU_KEYBD, aes.EV_MU_BUTTON, aes.EV_MU_M1, aes.EV_MU_M2
MU_TIMER = aes.EV_MU_TIMER
moblk, button_wait = aes_evasync.moblk, aes_evasync.button_wait
LEAVE, ENTER = aes_evasync.LEAVE, aes_evasync.ENTER
RETURN = unwatched(aes_event.key(aes_event.RETURN_KEY))
RETURN_KEY_CODE = 0x1C0D                # what the BIOS hands on for Return: the scan code, the ASCII
LEFT_SHIFT_KEY, CONTROL_KEY, BACKSLASH_KEY = 0x2A, 0x1D, 0x2B       # make codes: Control-\ ends a recording
BAR = move_to(*aes_event.MENU_BAR_POINT)
BAR_S_RIGHT = (300, 5)                  # on the menu bar, right of its titles: the bar's, not the active rectangle's
ROUND_THE_BAR_POINT = (150, 0, 20, 10)  # a rectangle the menu bar point lies in, and the snapshot's mouse does not
ROUND_THE_MOUSE, WHOLE_SCREEN, ELSEWHERE = aes_evasync.ROUND_THE_MOUSE, aes_evasync.WHOLE_SCREEN, aes_evasync.ELSEWHERE
OUTSIDE = aes_evasync.OUTSIDE
INSIDE_ELSEWHERE = (ELSEWHERE[0] + 5, ELSEWHERE[1] + 5)        # ...two packets from the snapshot's mouse
SNAPSHOT_S_MOUSE = aes_event._cursor(BASE_IMAGE)
A_WINDOW = (100, 60, 200, 100)          # a window over the snapshot's mouse...
BESIDE_IT = (20, 180)                   # ...one of the desktop beside it, below the menu bar
ITS_TITLE = (150, 63)                   # ...and a point of its title bar: the window's, outside its work area
EITHER_BUTTON = 0x101                   # a button wait's clicks with the SENSE byte set: one click, NOT the state
BOTH_BUTTONS = 3
A_TIMER_MS, A_TIMER_TICKS = aes_evasync.A_TIMER_MS, aes_evasync.A_TIMER_TICKS
TAKE_THE_SCREEN = aes_event.frame_of(("w", aes.header_constants("wmupdate.h")["WM_BEG_MCTRL"]))
QUEUE_AND_ONE = aes.AES_FORK_ENTRIES + 2        # more moves than the fork queue holds: the last two are dropped
RING_HALF = 20                          # moves queued and run, then as many again: the tail and the head wrap
A_FULL_KEY_QUEUE = FM["CQUEUE_ENTRIES"]
KEYS_NOBODY_READS = A_FULL_KEY_QUEUE + 2
SLOP = EVF["CLICK_SLOP"]

def recording(events):
    """The desk's appl_trecord of `events` events into RECORD_AT: it arms the recorder and parks in a delay."""
    assert events * aes.FORK_ENTRY_BYTES <= RECORD_BYTES
    return call(addrs.AES_ROM_AP_TRECD, aes_event.frame_of(("l", RECORD_AT), ("w", events)), parks=True)


# appl_tplay's records (`$fe66f8`): what each event is, by number — and the longword forkq is handed with it.
PLAYED_BUTTON, PLAYED_MOUSE = 1, 2
PLAY_SCALE = 100                        # appl_tplay's third argument: the recording's own speed


def playing(*records):
    """The desk's appl_tplay of `records` (`(kind, data)` each) from RECORD_AT — the buffer an application hands it, its
    argument's record: the ROM's own ap_tplay sets gl_play for a mouse record, saves the VDI's cursor routine in
    `$947a`, queues each event and yields to the dispatcher for it."""
    assert len(records) * aes.FORK_ENTRY_BYTES <= RECORD_BYTES
    frame = aes_event.frame_of(("l", RECORD_AT), ("w", len(records)), ("w", PLAY_SCALE))
    return call(addrs.AES_ROM_AP_TPLAY, frame, staged={RECORD_AT: b"".join(struct.pack(">II", *record) for record in records)})


def played_move(x, y):
    return PLAYED_MOUSE, (x & aes.WORD_MASK) << aes.HIGH_WORD_SHIFT | y & aes.WORD_MASK


def played_buttons(buttons, clicks):
    return PLAYED_BUTTON, buttons << aes.HIGH_WORD_SHIFT | clicks


right_press = taken_watched(aes_event.RIGHT_PRESSING)


def a_window_open():
    return aes_event.window_chain(aes_event.EVERY_GADGET, *A_WINDOW, aes_event.machine())[0]


def screen_owned():
    return test_aes_wm_update.owned()


def press_then_move(dx, dy):
    """A press, then a move inside its click count (the count still open when forker runs the move)."""
    return (mouse_packet(LEFT_DOWN), moves((dx, dy)), dispatcher())


A_PLAYED_POINT = (200, 120)
LEFT_OF_THE_SCREEN = (-1, 100)          # a played x no mouse reaches: mchange stores the EVENT's words while it plays
A_BUTTON_WORD_ABOVE_ITS_BYTE = 0x0100   # a played button word whose low byte is 0
WAIT_FOR_A_KEY = evnt_multi(MU_KEYBD)
WAIT_FOR_A_PRESS = evnt_multi(MU_BUTTON, button=button_wait(1))
STAGED_APPLICATION = aes_pdpipe.STAGED_APPLICATION


def two_delays(own_ms, application_ms):
    """A STAGED APPLICATION's machine (the labelled class, Tier 1 only): the desk starts it and waits for `own_ms`;
    the dispatcher enters the application, whose one call is ev_timer(`application_ms`) — both delays on the delay
    list, the machine idle."""
    def start():
        application = aes_pdpipe.staged_application("AES_ROM_EV_TIMER", application_ms)
        frame, pokes = aes_evasync.ev_multi_frame(MU_TIMER, timer=own_ms)
        parked = aes_event.parked(addrs.AES_ROM_EV_MULTI, frame, merge_pokes(application.machine, pokes))
        aes_pdpipe.vet_the_application(application, make_image(parked))
        return aes_evasync.watched(parked, addrs.AES_ROM_DISP_LOOP, {addrs.AES_ROM_DISP_LOOP},
                                   once_past=addrs.AES_ROM_SAVESTATE).machine
    return start


def ticks_of(milliseconds):
    return [tick] * (milliseconds // aes_evasync.TICK_MS)


RUNS = {
    "a key wakes the desk": (SNAPSHOT, RETURN, dispatcher()),
    "a press wakes the desk": (SNAPSHOT, PRESS, dispatcher()),
    "a click wakes the desk": (SNAPSHOT, CLICK, dispatcher()),
    "a double click wakes the desk": (SNAPSHOT, DOUBLE_CLICK, dispatcher()),
    "a right press wakes nobody": (SNAPSHOT, right_press, dispatcher(ONE_PASS)),
    "the right button pressed inside the left one's count": (
        SNAPSHOT, mouse_packet(LEFT_DOWN), mouse_packet(LEFT_DOWN | aes_event.MOUSE_PACKET_RIGHT_BUTTON),
        until_the_click_is_counted, dispatcher()),
    aes_evasync.THE_BAR_WAKES_THE_MANAGER: (SNAPSHOT, BAR, dispatcher()),
    "a key typed ahead of a wait for a press": (aes_event.machine, RETURN, WAIT_FOR_A_PRESS, dispatcher(TWO_PASSES)),
    "the shift key alone": (SNAPSHOT, unwatched(aes_event.key(LEFT_SHIFT_KEY)), dispatcher(TWO_PASSES)),
    "ten keys nobody reads": (aes_event.machine, *[RETURN] * KEYS_NOBODY_READS, WAIT_FOR_A_PRESS,
                              dispatcher(KEYS_NOBODY_READS + 3)),
    "a timer runs out": (aes_event.machine, evnt_multi(MU_TIMER, timer=A_TIMER_MS), *[tick] * A_TIMER_TICKS,
                         dispatcher()),
    "the button released": (aes_event.button_down, evnt_multi(MU_BUTTON, button=button_wait(1, state=0)), RELEASE,
                            dispatcher()),
    "more moves than the fork queue holds": (SNAPSHOT, moves(*[(1, 0)] * QUEUE_AND_ONE), dispatcher(ONE_PASS)),
    "the fork queue's ring wraps": (SNAPSHOT, moves(*[(1, 0)] * RING_HALF), dispatcher(ONE_PASS),
                                    moves(*[(-1, 0)] * RING_HALF), dispatcher(ONE_PASS)),
    "two rectangles, one left": (
        aes_event.machine,
        evnt_multi(MU_M1 | MU_M2, first=moblk(LEAVE, *ROUND_THE_MOUSE), second=moblk(LEAVE, *WHOLE_SCREEN)),
        move_to(*OUTSIDE), dispatcher()),
    "two rectangles, the other left": (
        aes_event.machine,
        evnt_multi(MU_M1 | MU_M2, first=moblk(LEAVE, *WHOLE_SCREEN), second=moblk(LEAVE, *ROUND_THE_MOUSE)),
        move_to(*OUTSIDE), dispatcher()),
    "a rectangle not entered": (aes_event.machine, evnt_multi(MU_M1, first=moblk(ENTER, *ELSEWHERE)),
                                moves((5, 0)), dispatcher(ONE_PASS)),
    "a move right ends a click's count": (SNAPSHOT, *press_then_move(SLOP + 1, 0)),
    "a move left ends a click's count": (SNAPSHOT, *press_then_move(-SLOP - 1, 0)),
    "a move down ends a click's count": (SNAPSHOT, *press_then_move(0, SLOP + 1)),
    "a move up ends a click's count": (SNAPSHOT, *press_then_move(0, -SLOP - 1)),
    "a press and its release, then a move ends the count": (
        SNAPSHOT, mouse_packet(LEFT_DOWN), mouse_packet(NO_BUTTON), moves((SLOP + 1, 0)), dispatcher()),
    "moves inside the slop leave a click's count open": (
        SNAPSHOT, mouse_packet(LEFT_DOWN),
        *(step for delta in ((SLOP, 0), (0, SLOP), (-SLOP, 0), (0, -SLOP)) for step in (moves(delta), dispatcher(ONE_PASS))),
        until_the_click_is_counted, dispatcher()),
    "a press on the bar's right": (SNAPSHOT, move_to(*BAR_S_RIGHT), PRESS, dispatcher()),
    "a press on a window's title": (a_window_open, WAIT_FOR_A_KEY, move_to(*ITS_TITLE), PRESS, dispatcher()),
    "a press on the desktop beside a window": (a_window_open, WAIT_FOR_A_KEY, move_to(*BESIDE_IT), PRESS, dispatcher(TWO_PASSES)),
    "a press inside the control rectangle": (screen_owned, WAIT_FOR_A_KEY, PRESS, dispatcher(TWO_PASSES)),
    "a press on the bar with the screen owned": (screen_owned, WAIT_FOR_A_KEY, BAR, PRESS, dispatcher(TWO_PASSES)),
    "a right press on a window's title": (a_window_open, WAIT_FOR_A_KEY, move_to(*ITS_TITLE), right_press, dispatcher(TWO_PASSES)),
    "a press off the bar while the mouse is the screen manager's": (
        SNAPSHOT, BAR, dispatcher(), move_to(*SNAPSHOT_S_MOUSE), PRESS,
        evnt_multi(MU_BUTTON, button=button_wait(1), parks=False)),
    "the mouse onto the bar and a key in one idle": (SNAPSHOT, BAR, RETURN, dispatcher()),
    "a double click and its release": (
        SNAPSHOT, mouse_packet(LEFT_DOWN), mouse_packet(NO_BUTTON), mouse_packet(LEFT_DOWN), mouse_packet(NO_BUTTON),
        until_the_click_is_counted, dispatcher()),
    "a rectangle entered two moves away": (
        aes_event.machine, evnt_multi(MU_M1, first=moblk(ENTER, *ELSEWHERE)), move_to(*INSIDE_ELSEWHERE), dispatcher()),
    "the screen manager hands the mouse back to the desk's own wait": (
        SNAPSHOT, BAR, PRESS, dispatcher(), call(addrs.AES_ROM_W_SETACTIVE, b"")),
    "the screen manager waits while the desk's key queue is full": (
        aes_event.machine, *[RETURN] * KEYS_NOBODY_READS, WAIT_FOR_A_PRESS, dispatcher(A_FULL_KEY_QUEUE + 3), BAR,
        dispatcher(), WAIT_FOR_A_KEY),
    "the mouse onto the bar with the screen owned": (screen_owned, WAIT_FOR_A_KEY, BAR, dispatcher(TWO_PASSES)),
    "the mouse onto the bar with the button down": (aes_event.button_down, WAIT_FOR_A_KEY, BAR, dispatcher(TWO_PASSES)),
    "the screen manager hands the mouse back": (
        aes_event.machine,
        evnt_multi(MU_M1 | MU_M2 | MU_BUTTON, first=moblk(ENTER, *ROUND_THE_BAR_POINT),
                   second=moblk(LEAVE, *ROUND_THE_MOUSE), button=button_wait(1)),
        BAR, PRESS, dispatcher(), call(addrs.AES_ROM_W_SETACTIVE, b"")),
    "a double click to a wait for one click": (aes_event.machine, WAIT_FOR_A_PRESS, DOUBLE_CLICK, dispatcher()),
    "a wait for either button, the right one pressed": (
        aes_event.machine, evnt_multi(MU_BUTTON, button=button_wait(EITHER_BUTTON, mask=BOTH_BUTTONS, state=0)),
        right_press, dispatcher()),
    "the screen taken": (aes_event.machine, call(addrs.AES_ROM_WM_UPDATE, TAKE_THE_SCREEN)),
    "a recording: two ticks merged, then a move": (
        aes_event.machine, recording(3), *[tick] * A_TIMER_TICKS, dispatcher(TWO_PASSES), *[tick] * A_TIMER_TICKS, dispatcher(TWO_PASSES),
        moves((5, 0)), dispatcher(TWO_PASSES)),
    "a recording ended by Control-backslash": (
        aes_event.machine, recording(4), moves((5, 0)), unwatched(aes_event.key(CONTROL_KEY)),
        unwatched(aes_event.key(BACKSLASH_KEY)), dispatcher(FOUR_PASSES)),
    "a recording of one event runs out": (aes_event.machine, recording(1), moves((5, 0)), dispatcher(ONE_PASS)),
    "a recording: a key": (aes_event.machine, recording(3), RETURN, dispatcher(TWO_PASSES)),
    "a recording: a press, then as many moves as the queue holds": (
        aes_event.machine, recording(4), mouse_packet(LEFT_DOWN), moves(*[(SLOP + 1, 0)] * aes.AES_FORK_ENTRIES),
        dispatcher(ONE_PASS)),
    "the screen manager hands the mouse back with no button down": (
        aes_event.machine, WAIT_FOR_A_PRESS, BAR, dispatcher(), call(addrs.AES_ROM_W_SETACTIVE, b"")),
    "a click on the bar while the screen manager waits for a key": (
        SNAPSHOT, BAR, dispatcher(), WAIT_FOR_A_KEY, CLICK, dispatcher(TWO_PASSES)),
    "the desk plays a move back": (aes_event.shown_machine, playing(played_move(*A_PLAYED_POINT))),      # the cursor SHOWN
    "a move played left of the screen, then a press and a move": (
        aes_event.machine, playing(played_move(*LEFT_OF_THE_SCREEN)), WAIT_FOR_A_KEY, mouse_packet(LEFT_DOWN),
        moves((1, 0)), dispatcher(ONE_PASS)),
    "a button word above its byte played, then a press on the bar's right": (
        aes_event.machine, playing(played_buttons(A_BUTTON_WORD_ABOVE_ITS_BYTE, 1)), WAIT_FOR_A_KEY,
        move_to(*BAR_S_RIGHT), PRESS, dispatcher(TWO_PASSES)),
    f"{STAGED_APPLICATION}: the first of two delays runs out": (
        two_delays(aes_evasync.A_SHORT_TIMER_MS, aes_evasync.A_LONGER_TIMER_MS),
        *ticks_of(aes_evasync.A_SHORT_TIMER_MS), dispatcher()),
    f"{STAGED_APPLICATION}: two delays run out together": (
        two_delays(aes_evasync.A_SHORT_TIMER_MS, aes_evasync.A_SHORT_TIMER_MS),
        *ticks_of(aes_evasync.A_SHORT_TIMER_MS), dispatcher()),
}


def _declared(compact):
    """A declared sequence from its compact spelling: `forker chkkbd b_delay*11 ...`."""
    arrivals = []
    for item in compact.split():
        name, _, count = item.partition("*")
        arrivals += [f"AES_ROM_{name.upper()}"] * int(count or 1)
    return tuple(arrivals)


DECLARED = {
    "a key wakes the desk":
        "forker chkkbd forkq forker kchange post_keybd chkkbd",
    "a press wakes the desk":
        "b_click b_delay*11 forkq forker bchange mowner post_button downorup chkkbd",
    "a click wakes the desk":
        "b_click*2 b_delay*11 forkq*2 forker bchange mowner post_button downorup bchange post_button chkkbd",
    "a double click wakes the desk":
        "b_click*3 b_delay*14 forkq forker bchange mowner post_button downorup chkkbd",
    "a right press wakes nobody":
        "b_click b_delay*11 forkq forker bchange post_button downorup chkkbd",
    "the right button pressed inside the left one's count":
        "b_click*2 b_delay*11 forkq*2 forker bchange mowner post_button downorup bchange post_button chkkbd",
    aes_evasync.THE_BAR_WAKES_THE_MANAGER:
        "forkq forker mchange post_mouse inorout chkkbd",
    "a key typed ahead of a wait for a press":
        "chkkbd forkq forker kchange post_keybd nq downorup*2 forker chkkbd*2",
    "the shift key alone":
        "forker chkkbd forkq forker kchange chkkbd",
    "ten keys nobody reads":
        "chkkbd forkq forker kchange post_keybd nq downorup*2 forker "
        + "chkkbd forkq forker kchange post_keybd nq " * (A_FULL_KEY_QUEUE - 1) + "chkkbd*5",
    "a timer runs out":
        "chkkbd forker b_delay*4 forkq b_delay forker tchange chkkbd",
    "the button released":
        "chkkbd forker downorup*2 b_click forkq forker bchange post_button downorup chkkbd",
    "more moves than the fork queue holds":
        f"forkq*{QUEUE_AND_ONE} forker " + "mchange post_mouse " * aes.AES_FORK_ENTRIES + "chkkbd",
    "the fork queue's ring wraps":
        (f"forkq*{RING_HALF} forker " + "mchange post_mouse " * RING_HALF + "chkkbd ") * 2,
    "two rectangles, one left":
        "chkkbd forker forkq*2 forker mchange post_mouse inorout*2 mchange post_mouse inorout chkkbd",
    "two rectangles, the other left":
        "chkkbd forker forkq*2 forker mchange post_mouse inorout*2 mchange post_mouse inorout chkkbd",
    "a rectangle not entered":
        "chkkbd forker forkq forker mchange post_mouse inorout chkkbd",
    "a move right ends a click's count":
        "b_click forkq forker mchange b_delay forkq post_mouse bchange mowner post_button downorup chkkbd",
    "a move left ends a click's count":
        "b_click forkq forker mchange b_delay forkq post_mouse bchange mowner post_button downorup chkkbd",
    "a move down ends a click's count":
        "b_click forkq forker mchange b_delay forkq post_mouse bchange mowner post_button downorup chkkbd",
    "a move up ends a click's count":
        "b_click forkq forker mchange b_delay forkq post_mouse bchange mowner post_button downorup chkkbd",
    "a press and its release, then a move ends the count":
        "b_click*2 forkq forker mchange b_delay forkq*2 post_mouse bchange mowner post_button downorup bchange post_button "
        "chkkbd",
    "moves inside the slop leave a click's count open":
        "b_click " + "forkq forker mchange post_mouse chkkbd " * 4
        + "b_delay*11 forkq forker bchange mowner post_button downorup chkkbd",
    "a press on the bar's right":
        "forkq*2 b_click b_delay*11 forkq forker mchange post_mouse mchange post_mouse bchange mowner post_button downorup chkkbd",
    "a press on a window's title":
        "chkkbd forker forkq b_click b_delay*11 forkq forker mchange post_mouse bchange mowner post_button downorup chkkbd",
    "a press on the desktop beside a window":
        "chkkbd forker forkq*2 b_click b_delay*11 forkq forker mchange post_mouse mchange post_mouse bchange mowner post_button chkkbd*2",
    "a press inside the control rectangle":
        "chkkbd forker b_click b_delay*11 forkq forker bchange mowner post_button chkkbd*2",
    "a press on the bar with the screen owned":
        "chkkbd forker forkq b_click b_delay*11 forkq forker mchange post_mouse bchange mowner post_button chkkbd*2",
    "a right press on a window's title":
        "chkkbd forker forkq b_click b_delay*11 forkq forker mchange post_mouse bchange post_button chkkbd*2",
    "a press off the bar while the mouse is the screen manager's":
        "forkq forker mchange post_mouse inorout chkkbd forkq b_click b_delay*11 forkq chkkbd forker mchange post_mouse "
        "bchange post_button downorup",
    "the mouse onto the bar and a key in one idle":
        "forkq forker mchange post_mouse inorout chkkbd forkq forker kchange post_keybd chkkbd",
    "a double click and its release":
        "b_click*4 b_delay*14 forkq*2 forker bchange mowner post_button downorup bchange post_button chkkbd",
    "a rectangle entered two moves away":
        "chkkbd forker forkq*2 forker mchange post_mouse inorout mchange post_mouse chkkbd",
    "the screen manager hands the mouse back to the desk's own wait":
        "forkq b_click b_delay*11 forkq forker mchange post_mouse inorout bchange post_button downorup chkkbd "
        "ct_chgown set_mown post_mouse post_button downorup",
    "the screen manager waits while the desk's key queue is full":
        "chkkbd forkq forker kchange post_keybd nq downorup*2 forker "
        + "chkkbd forkq forker kchange post_keybd nq " * (A_FULL_KEY_QUEUE - 1)
        + "chkkbd*3 forkq forker mchange post_mouse inorout chkkbd*2 forker",
    "the mouse onto the bar with the screen owned":
        "chkkbd forker forkq forker mchange post_mouse chkkbd*2",
    "the mouse onto the bar with the button down":
        "chkkbd forker forkq forker mchange post_mouse chkkbd*2",
    "the screen manager hands the mouse back":
        "chkkbd forker downorup*2 forkq b_click b_delay*11 forkq forker mchange post_mouse inorout bchange post_button "
        "downorup chkkbd ct_chgown set_mown post_mouse inorout*2 post_button downorup",
    "a double click to a wait for one click":
        "chkkbd forker downorup*2 b_click*3 b_delay*14 forkq forker bchange mowner post_button downorup chkkbd",
    "a wait for either button, the right one pressed":
        "chkkbd forker downorup*2 b_click b_delay*11 forkq forker bchange post_button downorup chkkbd",
    "the screen taken":
        "ct_chgown set_mown post_mouse post_button",
    "a recording: two ticks merged, then a move":
        "b_delay*4 forkq b_delay forker tchange chkkbd forker chkkbd b_delay*4 forkq b_delay forker tchange chkkbd "
        "forker chkkbd forkq forker mchange post_mouse chkkbd*2",
    "a recording ended by Control-backslash":
        "forkq forker mchange post_mouse chkkbd forkq forker kchange post_keybd nq chkkbd*3",
    "a recording of one event runs out":
        "forkq forker mchange post_mouse chkkbd",
    "a recording: a key":
        "forker chkkbd forkq forker kchange post_keybd nq chkkbd",
    "a recording: a press, then as many moves as the queue holds":
        f"b_click forkq*{aes.AES_FORK_ENTRIES} forker mchange b_delay forkq post_mouse "
        + "mchange post_mouse " * (aes.AES_FORK_ENTRIES - 1) + "bchange mowner post_button chkkbd",
    "the screen manager hands the mouse back with no button down":
        "chkkbd forker downorup*2 forkq forker mchange post_mouse inorout chkkbd ct_chgown set_mown post_mouse "
        "post_button downorup",
    "a click on the bar while the screen manager waits for a key":
        "forkq forker mchange post_mouse inorout chkkbd*2 forker b_click*2 b_delay*11 forkq*2 forker bchange post_button "
        "bchange post_button chkkbd*2",
    "the desk plays a move back":
        "forker chkkbd forkq forker mchange drawrat post_mouse chkkbd",
    "a move played left of the screen, then a press and a move":
        "forker chkkbd forkq forker mchange drawrat post_mouse chkkbd*2 forker b_click forkq forker mchange post_mouse "
        "chkkbd",
    "a button word above its byte played, then a press on the bar's right":
        "forker chkkbd forkq forker bchange post_button chkkbd*2 forker forkq*2 b_click b_delay*11 forkq forker "
        "mchange post_mouse mchange post_mouse bchange post_button chkkbd*2",
    f"{STAGED_APPLICATION}: the first of two delays runs out":
        "b_delay*9 forkq b_delay forker tchange chkkbd",
    f"{STAGED_APPLICATION}: two delays run out together":
        "b_delay*9 forkq b_delay forker tchange chkkbd",
}
assert DECLARED.keys() == RUNS.keys(), f"scenarios run and declared differ: {DECLARED.keys() ^ RUNS.keys()}"
SCENARIOS = {name: Scenario(start, tuple(steps), _declared(DECLARED[name])) for name, (start, *steps) in RUNS.items()}


@derived.kept
def _run_of(name):
    """The ROM's run of the scenario `name`: a derivation, kept by content."""
    return run_scenario(SCENARIOS[name].start, *SCENARIOS[name].steps)


# Each scenario's run — a `Watched` — its arrivals held to what it declares (`aes_event.Scenarios`): `scenario(name)`,
# `case_id`, `arrival(name, nth)`, `nth_of(name, routine, which)`, `at(name, routine, which)`.
_SCENARIOS = aes_event.Scenarios({name: declared.arrivals for name, declared in SCENARIOS.items()}, _run_of,
                                 arrivals_of=lambda made: made.arrivals)
scenario, case_id = _SCENARIOS.scenario, _SCENARIOS.case_id
arrival, nth_of, at = _SCENARIOS.arrival, _SCENARIOS.nth_of, _SCENARIOS.at
short = aes_event.short_name


# A scenario's LONG RUNS of one routine's arrivals are one shape many times over — a click count's eleven ticks, the
# thirty-two moves of a full queue: the cases keep the first and the last RUN_ENDS of each (the ends are where a run's
# shape changes: the count opened and run out, the queue empty and full, the ring's wrap).
RUN_ENDS = 3


def _thinned(indices):
    return indices if len(indices) <= 2 * RUN_ENDS else indices[:RUN_ENDS] + indices[-RUN_ENDS:]


def cases(*routines):
    """`(scenario, nth)` for the declared arrivals at each of `routines` (every routine, by default), a scenario's
    long runs of one routine thinned to their ends (RUN_ENDS)."""
    kept = []
    for name, declared in SCENARIOS.items():
        for routine in routines or ROUTINES:
            kept += [(name, nth) for nth in _thinned([nth for nth, each in enumerate(declared.arrivals) if each == routine])]
    return sorted(kept, key=lambda pair: (list(SCENARIOS).index(pair[0]), pair[1]))


# ---- the layer's state, read out of an image ------------------------------------------------------------------------------
def waits(image, pd, which):
    """The EVBs on `pd`'s CDA's wait list `which` (a CDA_*_WAIT offset)."""
    return aes_evasync.wait_list(image, case.long_in(image, pd + aes.PD_CDA) + which)


fork_queue, button_change = aes_event.fork_queue, aes_event.button_change      # the family's two readers of the queue


# ---- the run door ---------------------------------------------------------------------------------------------------------
# WHAT A CORE OF THIS LAYER CALLS THROUGH A HOOK, off target, is the event layer's own to say and is said once
# (`aes_event`, "WHAT THE EVENT LAYER'S OWN C CALLS OUT THROUGH"): the VDI's cores, the polled input functions among
# them, and the routines it is handed by value — a fork function, the cursor routine drawrat calls. THE SHARED BINDING
# is `aes_event.EVENT_LAYER_HOOKS` — a NAMED hook, so the forks that serve it are the zygote's.
HOOKS, SERVED_IN_A_FORK = aes_event.EVENT_LAYER_HOOKS, aes_event.SERVED_IN_A_FORK


# A CURSOR ROUTINE OF A CASE'S OWN, for drawrat's `jsr (*$947a)` — A POKED FIELD AND CODE, labelled as that where it
# is used: the call itself is held by the ROM's own playback machine (above); this one is for the words the VDI's
# routine does not show whole. What runs there is a longword in RAM, an input of
# the routine (`staged_call.h`) — so a case stages one, as the interrupt handlers' cases do: 68000 for the oracle
# (`move.w d0,<log> / move.w d1,<log + 2> / rts`), and for the candidate the same effect on the register-carrying
# hook's D0 and D1.
MOVE_W_D0_ABSOLUTE, MOVE_W_D1_ABSOLUTE, RTS = b"\x33\xc0", b"\x33\xc1", b"\x4e\x75"
CURSOR_ROUTINE = (MOVE_W_D0_ABSOLUTE + struct.pack(">I", CURSOR_LOG_AT)
                  + MOVE_W_D1_ABSOLUTE + struct.pack(">I", CURSOR_LOG_AT + WORD_BYTES) + RTS)
GSXIF = aes.header_constants("gsxif.h")


def _cursor_logged(buf, registers):
    for offset, register in ((0, "d0"), (WORD_BYTES, "d1")):
        word = registers[isr.REGISTER[register]] & aes.WORD_MASK
        buf[CURSOR_LOG_AT + offset], buf[CURSOR_LOG_AT + offset + 1] = word >> 8, word & aes.BYTE_MASK


CURSOR_STAGED = {CURSOR_ROUTINE_AT: CURSOR_ROUTINE, GSXIF["AES_DRWADDR"]: struct.pack(">I", CURSOR_ROUTINE_AT)}
CURSOR_HOOKS = aes.doors(aes_event.vdi_hook, aes.alcyon_object_hook({**aes_event.handed_routines(),
                                                                     CURSOR_ROUTINE_AT: (CURSOR_ROUTINE, _cursor_logged)}))
# What differs by nature where the ROM's run stores it: the Line-F mask word, the BIOS trap's register save under the
# keyboard poll and the PC and SR of its frame (`aes_event.TRAP_SAVE_DROP`, `TRAP_FRAME_DROP`), and spl7_save's SR
# save word under tchange's re-arm of the tick.
DROPS = (aes.LINE_F_MASK_WINDOW + aes_event.TRAP_SAVE_DROP + aes_event.TRAP_FRAME_DROP
         + aes_event.sr_drops(aes.AES_SR_SPL))


# ---- what steers the attribution pass in this layer (`aes.run_function`'s `steered=`) ----------------------------------
CDAS = aes_pdpipe.CDAS
STEERS_THE_LISTS = aes_pdpipe.STEERS_THE_LISTS
STEERS_THE_FORK_QUEUE = aes.steers(
    "the fork queue's head, tail and count — forkq and forker index the queue by the first two and forker loops on "
    "the third: inverted, the entry lies outside the machine and the loop runs 65,000 times",
    *((at, at + WORD_BYTES) for at in (aes.AES_FORK_HEAD, aes.AES_FORK_TAIL, aes.AES_FORK_COUNT)))
STEERS_THE_KEY_QUEUE = aes.steers(
    "a key queue's rear and count — nq stores the key THROUGH the rear and tests the count: inverted, the key lands "
    "outside the queue",
    *((cda + FM["CDA_KEY_QUEUE"] + field, cda + FM["CDA_KEY_QUEUE"] + field + WORD_BYTES)
      for cda in CDAS for field in (EVI["CQUEUE_REAR"], FM["CQUEUE_COUNT"])))
STEERS_THE_RECORDER = aes.steers(
    "the recorder's cursor and count — forker copies an entry THROUGH the cursor while the count is not 0",
    (aes.AES_RECORD_CURSOR, aes.AES_RECORD_CURSOR + LONG_BYTES), (aes.AES_RECORD_LEFT, aes.AES_RECORD_LEFT + WORD_BYTES),
    (aes.AES_GL_RECD, aes.AES_GL_RECD + WORD_BYTES))
STEERS_THE_OWNER = aes.steers(
    "the mouse's owner — bchange and mchange post THROUGH it, and re-decide it only under tests of words the run "
    "also stores (the buttons): inverted and not re-decided, the post walks the waits of no process",
    (aes.AES_GL_MOWNER, aes.AES_GL_MOWNER + LONG_BYTES))
STEERS_THE_KEYBOARD_BUFFER = aes.steers(
    "the keyboard's buffer indices — the BIOS under chkkbd's poll takes a key off the IKBD's IOREC by its head, "
    "which it stores: inverted, its read of the next key walks out of the buffer",
    (addrs.IOREC_IKBD + addrs.IOREC_HEAD, addrs.IOREC_IKBD + addrs.IOREC_HEAD + WORD_BYTES),
    (addrs.IOREC_IKBD + addrs.IOREC_TAIL, addrs.IOREC_IKBD + addrs.IOREC_TAIL + WORD_BYTES))
STEERS_THE_TRAP = aes.steers(
    "savptr — the BIOS's trap dispatcher, under the VDI's keyboard poll (and its locator's, while a recording plays), "
    "saves the registers THROUGH it and stores "
    "it back: inverted, the save lands outside the machine",
    (addrs.SYSVAR_SAVPTR, addrs.SYSVAR_SAVPTR + LONG_BYTES))
STEERS_THE_QUEUED_ENTRIES = aes.steers(
    "the fork queue's entries — one a fork function queues (b_delay's press, behind the move that ended its count) is "
    "one forker then CALLS: its code inverted is no routine's address",
    (aes.AES_FORK_QUEUE, aes.AES_FORK_QUEUE + aes.AES_FORK_ENTRIES * aes.FORK_ENTRY_BYTES))
# WHICH REASON STEERS WHICH ROUTINE — a word steers when the run READS it, as the machine holds it, on its way to a
# store; one the run stores FIRST (forkq's entry, set_mown's owner) or stores and never reads back (nq's rear, a
# tail that only names where the next entry goes — inverted, both shores store the entry at the same other address)
# steers nothing, and a reason named for it would leave its words un-inverted for nothing: a store of one the C
# skipped, where the value happens to be the machine's own, would go unseen. So a reason is named only where the
# pass FAILS without it. MEASURED, not argued (`AES_STEERED_FOR_NOTHING`, every case of both batteries, each reason
# left out in turn): a routine's row is the reasons its pass failed without in EVERY case that stores their words...
STEERS = {
    POST_KEYBD: (STEERS_THE_LISTS,), POST_BUTTON: (STEERS_THE_LISTS,), POST_MOUSE: (STEERS_THE_LISTS,),
    SET_MOWN: (STEERS_THE_LISTS,), CT_CHGOWN: (STEERS_THE_LISTS,), KCHANGE: (STEERS_THE_LISTS,),
    MCHANGE: (STEERS_THE_LISTS, STEERS_THE_TRAP), TCHANGE: (STEERS_THE_LISTS,), BCHANGE: (STEERS_THE_OWNER,),
    CHKKBD: (STEERS_THE_TRAP,), FORKER: (STEERS_THE_FORK_QUEUE, STEERS_THE_TRAP),
}
# ...and these are the ones it failed without in SOME: forker runs whatever was queued (a wait completed or none, the
# owner re-decided by bchange or stored by mchange, an entry recorded or the last record) and stores `rlr`, a list
# head, in every run; bchange's post finds a wait or none. No rule here says which case is which — so each such case
# ASKS: the pass is tried without the reason first (`run_over`), and the reason named only where that fails.
STEERS_SOME = {
    FORKER: (STEERS_THE_LISTS, STEERS_THE_OWNER, STEERS_THE_RECORDER, STEERS_THE_QUEUED_ENTRIES),
    BCHANGE: (STEERS_THE_LISTS,),
}
REASONS = (STEERS_THE_LISTS, STEERS_THE_FORK_QUEUE, STEERS_THE_KEY_QUEUE, STEERS_THE_RECORDER, STEERS_THE_OWNER,
           STEERS_THE_KEYBOARD_BUFFER, STEERS_THE_TRAP, STEERS_THE_QUEUED_ENTRIES)
assert all(reason in REASONS for table in (STEERS, STEERS_SOME) for reasons in table.values() for reason in reasons)


@derived.kept
def _stored_by_the_rom(name, arguments, machine):
    image = make_image(aes.staged(name, vdi.as_signed(name, arguments), machine))
    _final, writes, _regs = emu.run(image, getattr(addrs, name))
    return frozenset(case.written_by(writes))


def stored_by_the_rom(name, arguments, machine):
    """The addresses the ROM's own run of `addrs.<name>` over `machine` stores at (the stack band aside): a
    derivation, kept by content."""
    return _stored_by_the_rom(name, tuple(arguments), machine)


def steered_by(name, arguments, machine):
    """WHAT STEERS the attribution pass in the case of `addrs.<name>` over `machine`: `(certain, asked)` — of the
    routine's reasons (STEERS, STEERS_SOME), those one of whose words the ROM's run STORES: a word the run leaves
    alone is never inverted. `certain` steer every such case; each of `asked` is `run_over`'s to try without. A
    routine with no reason of either kind has nothing to ask the ROM's run, and none is made for it."""
    if name not in STEERS and name not in STEERS_SOME:
        return (), ()
    stored = stored_by_the_rom(name, arguments, machine)

    def met(reasons):
        return tuple(reason for reason in reasons
                     if any(at in stored for lo, hi in reason.spans for at in range(lo, hi)))
    return met(STEERS.get(name, ())), met(STEERS_SOME.get(name, ()))


def run(arrival, arguments=None, **kwargs):
    """The differential of `arrival`'s routine over its machine (`run_over`) — with the frame its caller pushed, or
    `arguments`."""
    return run_over(arrival.name, arrival.arguments if arguments is None else arguments, arrival.machine, **kwargs)


def run_over(name, arguments, machine, **kwargs):
    """The differential of `addrs.<name>` over `machine` with the frame `arguments`: every run of its C first in a
    fork (`aes_event.run_core_guarded`) — the hooks a core of REACH_A_HOOK calls through bound for the case, and left
    served in its forks. THE ATTRIBUTION PASS is the kit's own, whole, unless a reason steers the case (`steered_by`):
    then narrowed to the reasons that do — one that only steers SOME cases named after the pass has failed without
    it (`aes_event.run_core_steered`). A case that names its own `steered=` or `poison=` is run as it says."""
    hooked = {"hook": HOOKS, "serves": SERVED_IN_A_FORK} if name in REACH_A_HOOK else {}
    limits = {"dropped_windows": DROPS, **hooked, **kwargs}
    if "steered" in kwargs or "poison" in kwargs:
        return aes_event.run_core_guarded(name, arguments, machine, **limits)
    certain, asked = steered_by(name, arguments, machine)
    return aes_event.run_core_steered(name, arguments, machine, certain, asked, **limits)


# ---- the registry: Tier 3's rows ---------------------------------------------------------------------------------------
POLL_THE_KEYBOARD = (CHKKBD, FORKER)


def register(label, name, arguments, machine, *, through_line_f=False):
    """One `VERIFIED_CASES` row of `addrs.<name>` over an arrival's `machine` (`aes_event.register_row`: the one
    settling's pokes and drops, the companion with this layer's hooks) — told the one thing this layer knows by name:
    chkkbd and forker POLL the keyboard, so their rows' `savptr` is in the stack band whether a given run takes the
    BIOS trap or not."""
    return aes_event.register_row(label, name, arguments, machine, hook=HOOKS if name in REACH_A_HOOK else None,
                                  through_line_f=through_line_f, polls=name in POLL_THE_KEYBOARD)
