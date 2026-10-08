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

A CALL THAT IS WOKEN — the events it blocked for come: an interrupt's, another process's message — is held by its TAIL
(`woken`): mwait's return, the cancel of the waits that did not come and the answers of those that did, run in C over
THE ROM'S OWN MEMORY WHERE THE PROCESS RESUMES. The dispatcher's hook is served by the ROM's run of its own dispatcher
(no host model of the switch: the process parked, the interrupts taken, the other process's write, the loop), and the
image the twin returns with is the ROM's where its routine returns. With the case that holds the same call AT DSPTCH
it is the whole call but the switch itself. What that leaves unheld is said at `woken`.

WHAT DIFFERS BY NATURE, each a named drop made only where the ROM's run stores it: the Line-F mask word; the BIOS
trap's saved registers and frame under the keyboard poll; spl7_save's SR save word under adelay's and tchange's
brackets; and the ADDRESS OF THE QPB a message wait was queued with — a local of ev_multi's own frame in the ROM, a
place in the stack band on each shore — in its EVB where the wait PARKS, and still in it, FREED, where the call
returns with the wait cancelled (an EVB is freed as it is): vetted to name the same eight bytes on both shores.
"""
import ctypes
import functools
import mmap
import struct
import sys
from collections import namedtuple

from harness import _lib, addrs, arm_candidate, make_image

import aes
import aes_evasync as evasync
import aes_event
import aes_evinput
import aes_evlib as evlib
import aes_pdpipe
import case
import derived
import routines
import vdi
import vdi_helpers
from address_hook import REFUSED_ANSWER, bind_pointer
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


# ---- A CALL WOKEN: THE TAIL AFTER A REAL WAKE, the dispatcher's hook served by the ROM's own run --------------------------
# THE ROM'S SHORE (`rom_woken`, a derivation kept by content — the ROM alone): the process parks in its evnt_multi
# (`aes_event.parked`: the ROM's routine entered on the process's own stack, run into the dispatcher); for a wake BY
# ANOTHER PROCESS the mouse onto the menu bar wakes the SCREEN MANAGER through the ROM's dispatcher, its own
# appl_write (the ROM's ap_rdwr) serves the parked wait THROUGH THE QPB IN THE WAITING PROCESS'S FRAME, and it parks in
# an evnt_multi of its own; then the case's interrupts are taken, each the ROM's own interrupt code; then the
# dispatcher's loop runs — to W, the memory where the process RESUMES inside mwait (AES_ROM_EV_MWAIT_RESUMED), and on
# to F, where it comes out of ev_multi, D0 its answer.
# OUR SHORE: the twin over the same machine, in a fork whose dispatcher hook — the one a blocking case's refuses —
# LAYS W over the image (all of RAM but the stack band) and answers "returned". mwait's return, acancel, ev_rets and
# the aprets then run in C, and the image the twin returns with is F: EVERYWHERE outside the stack band but the bytes
# that differ BY NATURE, each only where the ROM's own run stored it after the resume (F is not W there) AND VETTED —
# the C holds W's byte there, having stored nothing: the ROM's own frames (the process's UDA: its stack is its own),
# the Line-F mask word, an SR save word. Nothing else is left out; no window is dropped whole.
#
# WHAT THIS HOLDS, AND WHAT IT DOES NOT. Everything the C wrote BEFORE the hook is overwritten by W, so that half is
# not compared HERE: the case that holds the same call AT DSPTCH is (`switched` — a woken case's first assertion).
# What carries across the hook is the C's own frame — the waits' event bits, the flags, what arrived, the QPB's
# claim — which is what the tail reads. And it is the HOST build's tail: on target a real switch saves and restores
# GCC's frame through savestate and switchto on the process's own stack, which no case can run until a row that
# switches to another process exists.
RAM_BYTES = addrs.ST_RAM_BYTES
BUS = aes_event.OS_BUS_ADDR_MASK
UDAS = (aes.AES_THEGLO, aes.AES_UDA1, aes.AES_UDA2, aes.AES_UDA2_STACK_TOP + LONG_BYTES)     # each UDA ends where the next begins
# The evnt_multi THE WRITER parks in once it has written: a key's wait alone (the keyboard is the desk's: no key of a
# case's wakes it), its answers never stored — the run ends where the process it woke comes out.
THE_WRITER_S_OWN_WAIT = aes_event.EV_MULTI_FRAME.pack(KEYBD, 0, 0, 0, 0, 0, ANSWERS_AT)
RomWoken = namedtuple("RomWoken", "pd resumed final came")
Woken = namedtuple("Woken", "image resumed final came by_nature")
HOOK_REACHED_AGAIN = "the dispatcher's hook was reached a second time: a woken call's tail waits for nothing"


def _uda_of(image, pd):
    """The addresses of the UDA of the process at `pd`: its saved state and its own supervisor stack."""
    uda = case.long_in(image, pd + aes.PD_UDA) & BUS
    assert uda in UDAS[:-1], f"the process at {pd:#x} has its UDA at {uda:#x}, none of the three"
    return range(uda, UDAS[UDAS.index(uda) + 1])


@derived.kept
def _rom_woken(arguments, machine, written, interrupts):
    frame = aes_event.EV_MULTI_FRAME.pack(*vdi.as_signed(EV_MULTI, arguments))
    pd = evasync.running(make_image(machine)) & BUS
    parked = aes_event.parked(addrs.AES_ROM_EV_MULTI, frame, machine)
    if written:
        writer = aes_event.woken_onto_the_menu_bar(parked)
        wrote = aes_pdpipe.sent(writer, case.word_in(make_image(machine), pd + aes.PD_PID), written)
        parked = aes_event.parked(addrs.AES_ROM_EV_MULTI, THE_WRITER_S_OWN_WAIT, wrote)
    woken_machine = evasync.taken(parked, *interrupts)
    resumed, _writes, regs = aes_event.stopped_at(make_image(woken_machine), addrs.AES_ROM_DISP_LOOP,
                                                  addrs.AES_ROM_EV_MWAIT_RESUMED)
    # WHOSE mwait resumed: the parked process's, and the one ITS ev_multi called — the frame mwait resumes over is in
    # that process's own stack and returns into ev_multi's text.
    returns_to = case.long_in(resumed, (regs["a6"] & BUS) + LONG_BYTES)
    assert (evasync.running(resumed) & BUS == pd and regs["a6"] & BUS in _uda_of(resumed, pd)
            and addrs.AES_ROM_EV_MULTI < returns_to < addrs.AES_ROM_EV_MULTI_RETURN), (
        f"the first mwait to resume is not the one the evnt_multi of the PD at {pd:#x} called: running "
        f"{evasync.running(resumed):#x}, its frame at {regs['a6']:#x}, returning to {returns_to:#x}")
    final, _writes, regs = aes_event.stopped_at(make_image(woken_machine), addrs.AES_ROM_DISP_LOOP,
                                                addrs.AES_ROM_EV_MULTI_RETURN)
    assert evasync.running(final) & BUS == pd, f"another process than the PD at {pd:#x} came out of its evnt_multi first"
    return RomWoken(pd, aes_event.as_pokes(resumed, upto=RAM_BYTES), aes_event.as_pokes(final, upto=RAM_BYTES),
                    regs["d0"] & aes.WORD_MASK)


def rom_woken(made, interrupts=(), written=None):
    """THE ROM'S SHORE of a `Call` that blocks and is woken (above): `interrupts` taken while it is parked, and —
    `written` — another process's message first. A `RomWoken`: the process, the machines W and F as pokes, the
    events the ROM's ev_multi answers."""
    return _rom_woken(tuple(made.arguments), machine_of(made), written, tuple(interrupts))


def _the_twin_s_tail(made, resumed):
    """`(exit code, stderr, image)` of the twin over a `Call`'s machine in a fork whose dispatcher hook lays
    `resumed` — W, an image — outside the stack band and answers that the call came back. Once: a second call of
    the hook is refused by name."""
    core, typed = getattr(_lib, routines.core_symbol(EV_MULTI)), vdi.as_signed(EV_MULTI, made.arguments)
    over = mmap.mmap(-1, aes_event.IMAGE_BYTES)
    over[:] = make_image(aes.staged(EV_MULTI, typed, machine_of(made)))
    shared = (ctypes.c_uint8 * aes_event.IMAGE_BYTES).from_buffer(over)
    band, served = case.STACK_BAND, []

    def serve(image):
        if served:
            print(HOOK_REACHED_AGAIN, file=sys.stderr, flush=True)
            return REFUSED_ANSWER
        served.append(True)
        ctypes.memmove(image, resumed[:band.start], band.start)
        ctypes.memmove(ctypes.addressof(image.contents) + band.stop, resumed[band.stop:RAM_BYTES], RAM_BYTES - band.stop)
        return not REFUSED_ANSWER
    hook = aes_event.DISPATCH_PROTOTYPE(serve)          # held by this frame for the fork's whole life

    def tail(_lib_, buf):
        arm_candidate()
        bind_pointer(aes_event.DISPATCH_SYMBOL, hook)   # in the fork alone: the worker's hook stays the refuser
        print(f"{vdi_helpers.ANSWER_LINE}{core(buf, *typed)}", file=sys.stderr)
    with HOOKS() as bound:
        returncode, stderr = aes_event.in_a_fork(lambda: bound.recording(tail)(_lib, shared), serves=SERVED_IN_A_FORK)
    return returncode, stderr, bytes(over)


def woken(made, interrupts=(), written=None):
    """A `Call` THAT BLOCKS AND IS WOKEN, its tail held to the ROM (above): a `Woken` — the twin's image at its
    return, the ROM's W and F, the events both answered, and the addresses left out by nature (vetted)."""
    rom = rom_woken(made, interrupts, written)
    resumed, final = bytes(make_image(rom.resumed)), bytes(make_image(rom.final))
    returncode, stderr, image = _the_twin_s_tail(made, resumed)
    assert returncode == 0, f"the ROM's evnt_multi is woken and returns; the twin's fork ended {returncode}: {stderr}"
    answered = vdi_helpers.answer_in(stderr) & aes.WORD_MASK
    assert answered == rom.came, f"woken, the twin answers the events {answered:#x}, the ROM's routine {rom.came:#x}"
    its_own = (*_uda_of(final, rom.pd), *aes_event.LINE_F_MASK_BYTES, *aes_event.SR_SAVE_BYTES)
    by_nature = frozenset(at for at in its_own if final[at] != resumed[at])
    wrote_there = [at for at in sorted(by_nature) if image[at] != resumed[at]]
    assert not wrote_there, (
        f"woken, the twin stored where only the ROM's own frames and save words are: "
        f"{[f'{at:#x}' for at in wrote_there[:aes_event.COMPARED_DIFFERENCES_SHOWN]]}")
    differ = aes_event.differing(image, final, frozenset(case.STACK_BAND) | by_nature)
    assert not differ, "where the woken call returns, " + aes_event.describe_differences(EV_MULTI, image, final, differ)
    return Woken(image, resumed, final, answered, by_nature)


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

# ---- THE CALLS THAT BLOCK AND ARE WOKEN (`woken`) ----------------------------------------------------------------------------
Wake = namedtuple("Wake", "call interrupts written", defaults=((), None))
SENT_MARK = EVLIB["AES_CTL_MESSAGE_SENT"]
A_TIMER_S_TICKS = evasync.ticks(A_TIMER_TICKS)


def by_an_interrupt(name, *interrupts):
    """A call of NOTHING_COME woken by `interrupts` taken in ONE idle of the dispatcher."""
    return Wake(NOTHING_COME[name], interrupts)


def marked(made):
    """A `Call` with AN ARGUMENT-CLASS POKE beside its ROM-made machine: the control manager's "sent" mark staged
    SET (the control manager sets it after it sends a window message, a run this battery does not make), so that the
    tail's clear of it — or its leaving it — is seen."""
    return made._replace(staged=merge_pokes(made.staged, {SENT_MARK: struct.pack(">H", 1)}))


def by_a_writer(made, *interrupts):
    """A call woken BY ANOTHER PROCESS'S MESSAGE — the screen manager's own appl_write to the waiting process — and
    by `interrupts` taken before the dispatcher runs it again; the "sent" mark staged set (`marked`)."""
    return Wake(marked(made), interrupts, evlib.A_MESSAGE)


EIGHT_BITS_HELD_A_KEY_THE_BUTTONS = "eight event bits held (the ROM's iasync): a key, the buttons, two rectangles"
EIGHT_BITS_HELD_A_MESSAGE_A_TIMER = "eight event bits held (the ROM's iasync): a message and a timer"
WOKEN_BY_AN_INTERRUPT = {
    "a key wakes: a key, none queued": by_an_interrupt("a key, none queued", RETURN),
    "a press wakes: the button down, which is up": by_an_interrupt("the button down, which is up", aes_event.press),
    "a release wakes: the button up, which is down": by_an_interrupt("the button up, which is down", aes_event.release),
    "a double click wakes: a double click": by_an_interrupt("a double click", aes_event.double_click),
    "a single click wakes: a double click": by_an_interrupt("a double click", CLICK),
    "entering wakes: a rectangle the mouse is not in": by_an_interrupt("a rectangle the mouse is not in", INTO_ELSEWHERE),
    "leaving wakes: a rectangle the mouse is to leave": by_an_interrupt("a rectangle the mouse is to leave", AWAY),
    "entering wakes: the second rectangle alone": by_an_interrupt("the second rectangle alone", INTO_ELSEWHERE),
    "leaving wakes: two rectangles": by_an_interrupt("two rectangles", AWAY),
    "the ticks wake: a timer": by_an_interrupt("a timer", A_TIMER_S_TICKS),
    "a tick wakes: a timer of less than a tick": by_an_interrupt("a timer of less than a tick", evasync.ticks(1)),
    "a key wakes: a key and a message": by_an_interrupt("a key and a message", RETURN),
    "the ticks wake: a message and a timer": by_an_interrupt("a message and a timer", A_TIMER_S_TICKS),
    "a key wakes: a key and the buttons": by_an_interrupt("a key and the buttons", RETURN),
    "a press wakes: a key and the buttons": by_an_interrupt("a key and the buttons", aes_event.press),
    "a key and a press in one idle: a key and the buttons": by_an_interrupt("a key and the buttons", RETURN, aes_event.press),
    "a press wakes: the buttons and a rectangle": by_an_interrupt("the buttons and a rectangle", aes_event.press),
    "a press, then entering, in one idle: the buttons and a rectangle": by_an_interrupt(
        "the buttons and a rectangle", aes_event.press, INTO_ELSEWHERE),
    "a key wakes: every event": by_an_interrupt("every event", RETURN),
    "a double click wakes: every event": by_an_interrupt("every event", aes_event.double_click),
    "leaving wakes: every event": by_an_interrupt("every event", AWAY),
    "entering wakes: every event": by_an_interrupt("every event", INTO_ELSEWHERE),
    "the ticks wake: every event": by_an_interrupt("every event", A_TIMER_S_TICKS),
    "a key, a double click, leaving and the ticks in one idle: every event": by_an_interrupt(
        "every event", RETURN, aes_event.double_click, AWAY, A_TIMER_S_TICKS),
    "a key wakes: eight bits held, a key, the buttons, two rectangles": by_an_interrupt(EIGHT_BITS_HELD_A_KEY_THE_BUTTONS, RETURN),
    "the ticks wake: eight bits held, a message and a timer": by_an_interrupt(EIGHT_BITS_HELD_A_MESSAGE_A_TIMER, A_TIMER_S_TICKS),
    "a release wakes: every event, the button held": by_an_interrupt("every event, the button held", aes_event.release),
    "a key wakes, the sent mark set: a key and a message": Wake(marked(NOTHING_COME["a key and a message"]), (RETURN,)),
}
WOKEN_BY_A_WRITER = {
    "a writer wakes: a message, none in the pipe": by_a_writer(NOTHING_COME["a message, none in the pipe"]),
    "a writer wakes: a message and a timer": by_a_writer(NOTHING_COME["a message and a timer"]),
    "a writer and the ticks in one wake: a message and a timer": by_a_writer(NOTHING_COME["a message and a timer"], A_TIMER_S_TICKS),
    "a writer wakes: a key and a message": by_a_writer(NOTHING_COME["a key and a message"]),
    "a writer wakes: every event": by_a_writer(NOTHING_COME["every event"]),
    "a writer and the ticks in one wake: every event": by_a_writer(NOTHING_COME["every event"], A_TIMER_S_TICKS),
    "a writer and the ticks: eight bits held, a message and a timer": by_a_writer(
        NOTHING_COME[EIGHT_BITS_HELD_A_MESSAGE_A_TIMER], A_TIMER_S_TICKS),
    "a writer and a key in one wake: a key and a message": by_a_writer(NOTHING_COME["a key and a message"], RETURN),
    "a writer, a key and the ticks in one wake: every event": by_a_writer(NOTHING_COME["every event"], RETURN, A_TIMER_S_TICKS),
    "a writer and the mouse into the rectangle: a rectangle and a message": by_a_writer(
        call(desk, M1 | MESAG, first=NOT_IN), INTO_ELSEWHERE),
    "a writer, a key, a press, the mouse, the ticks: every event": by_a_writer(
        NOTHING_COME["every event"], RETURN, aes_event.press, INTO_ELSEWHERE, A_TIMER_S_TICKS),
    "a writer, the desk waiting for the bar's rectangle too": by_a_writer(call(desk, M1 | MESAG, first=ON_THE_BAR)),
    "a writer, then the mouse away: both rectangles and a message": by_a_writer(
        call(desk, M1 | M2 | MESAG, first=NOT_OUT, second=NOT_IN), AWAY, INTO_ELSEWHERE),
}
WOKEN = {**WOKEN_BY_AN_INTERRUPT, **WOKEN_BY_A_WRITER}
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
