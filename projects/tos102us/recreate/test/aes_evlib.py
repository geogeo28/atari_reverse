"""THE WAITS' MACHINES — what `src/aes/evwait.c` and `src/aes/evlib.c` are proved over (`test_aes_evwait*.py`,
`test_aes_evlib*.py`).

EVERY MACHINE IS AN ARRIVAL, as the lists' are (`aes_evasync`): a SCENARIO is the ROM's own run of something a process
does — an application's evnt_keybd, evnt_button, evnt_mouse, evnt_timer, evnt_mesag, appl_write, wind_update, an
evnt_multi, each over a machine the scheduler made — WATCHED at the eighteen routines' entries
(`aes_event.EntryStops`): each time the run reaches one, the machine there (every byte of RAM the run changed, the
stack band aside) and the frame its caller pushed are kept. A case is the differential of that routine from that
machine with that frame: the ROM's own call, at the moment it makes it.

A CALL THAT RETURNS is an ordinary differential, its C first in a fork (`aes_event.run_core_guarded`). A CALL THAT
REACHES THE DISPATCHER — a wait nothing satisfies BLOCKS, unsync's hand-over YIELDS — is held where the C stops: the
dispatcher's hook refuses it by name, and the image the C left there is the ROM's memory AT DSPTCH, every list, EVB,
PD, CDA and counter the wait wrote (`switched`).

WHAT DIFFERS BY NATURE, each a named drop made only where the ROM's run stores it (`DROPS`): the Line-F mask word; and
spl7_save's SR save word under adelay's bracket (`aes/switch.h`). ONE MORE, for a blocked ap_rdwr alone
(`qpb_address_drop`): the QPB a parked pipe wait keeps in its EVB is ap_rdwr's own argument frame — an address in its
caller's stack, which a C caller's is not.

A THIRD PROCESS (two delays pending; two waits on the screen's lock) is `aes_pdpipe`'s STAGED APPLICATION, the
labelled class: its scenarios carry the label and register no row.

THE WAITS, WOKEN (the module's last part): what takes each blocked scenario on through the dispatcher to its return
(`WAKES`: the ROM's own interrupts at the dispatcher's idles, and the screen manager's own write for a wait on a
pipe), the scenarios no returning run wakes and why (`NOT_WOKEN`), the machines only a run through the dispatcher
makes (the screen manager holding the lock in its menu, queued on it by its own BEG_UPDATE, handed it; writing to a
full pipe), and the rows that switch (`register_woken`: `aes_switching`).

ARGUMENT-CLASS MACHINES (`after_iasync`): the ROM's own iasync called MORE THAN ONCE for the running process over a
scheduler's machine — a wait queued and not waited for (iasync does not block: ev_block's mwait does). No ROM caller
leaves them — evnt_multi queues one wait of each kind — but every list, EVB and event bit in them is the ROM's own
work: two and three delays pending (the delta list's walk and its insert between two), two waits of one process on the
screen's lock, nine event bits held. Their scenarios say so in their names.
"""
import functools
import struct
from collections import namedtuple

from harness import addrs, emu, make_image

import abi
import aes
import aes_evasync as evasync
import aes_event
import aes_pdpipe
import aes_switch
import aes_switching
import case
import derived
import test_aes_fmlib                   # its key queue, polled by the ROM's chkkbd and forker
import test_aes_wm_update as wm_update  # ...and its states of the screen's lock
import vdi
from case import merge_pokes

EVWAIT = aes_event.EVWAIT
EVLIB = aes.header_constants("evlib.h")
WORD_BYTES, LONG_BYTES = aes.WORD_BYTES, aes.LONG_BYTES
IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG

# ---- the routines, and how each is called ----------------------------------------------------------------------------
IASYNC, MWAIT, AKBIN, ADELAY = "AES_ROM_IASYNC", "AES_ROM_EV_MWAIT", "AES_ROM_AKBIN", "AES_ROM_ADELAY"
ABUTTON, AMOUSE, AMUTEX, UNSYNC = "AES_ROM_ABUTTON", "AES_ROM_AMOUSE", "AES_ROM_AMUTEX", "AES_ROM_UNSYNC"
EV_BLOCK, AP_RDWR, EV_KEYBD, EV_BUTTON = "AES_ROM_EV_BLOCK", "AES_ROM_AP_RDWR", "AES_ROM_EV_KEYBD", "AES_ROM_EV_BUTTON"
EV_MOUSE, EV_MESAG, EV_TIMER, EV_RETS = "AES_ROM_EV_MOUSE", "AES_ROM_EV_MESAG", "AES_ROM_EV_TIMER", "AES_ROM_EV_RETS"
EV_MCHK, EV_DCLICK = "AES_ROM_EV_MCHK", "AES_ROM_EV_DCLICK"
SIGNATURES = {
    IASYNC: (aes.WORD_ANSWER, (IMAGE, WORD, LONG)),
    MWAIT: (aes.WORD_ANSWER, (IMAGE, WORD)),
    AKBIN: (None, (IMAGE, LONG)),               # iasync pushes the parameter beside the EVB: akbin reads the EVB alone
    ADELAY: (None, (IMAGE, LONG, LONG)),
    ABUTTON: (None, (IMAGE, LONG, LONG)),
    AMOUSE: (None, (IMAGE, LONG, LONG)),
    AMUTEX: (None, (IMAGE, LONG, LONG)),
    UNSYNC: (aes.WORD_ANSWER, (IMAGE, LONG)),
    EV_BLOCK: (aes.WORD_ANSWER, (IMAGE, WORD, LONG)),
    AP_RDWR: (aes.WORD_ANSWER, (IMAGE, WORD, WORD, WORD, LONG)),
    EV_KEYBD: (aes.WORD_ANSWER, (IMAGE,)),
    EV_BUTTON: (aes.WORD_ANSWER, (IMAGE, WORD, WORD, WORD, LONG)),
    EV_MOUSE: (aes.WORD_ANSWER, (IMAGE, LONG, LONG)),
    EV_MESAG: (aes.WORD_ANSWER, (IMAGE, LONG)),
    EV_TIMER: (aes.WORD_ANSWER, (IMAGE, LONG)),
    EV_RETS: (None, (IMAGE, LONG)),
    EV_MCHK: (aes.WORD_ANSWER, (IMAGE, LONG)),
    EV_DCLICK: (aes.WORD_ANSWER, (IMAGE, WORD, WORD)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    if _name not in vdi.ALCYON:         # ev_block's and the other entries' may be the door's own declarations already
        aes.declare_alcyon(_name, _restype, _argtypes)
ROUTINES = tuple(SIGNATURES)
# Every routine here runs behind the fork guard (`aes_event.run_core_guarded`, `switched`): none reaches a hook a fork
# refuses — the dispatcher's alone, which a fork serves by refusing (`test_aes_event.py` holds the list to the host
# build's call graph).
FORK_GUARDED = ROUTINES

# ---- what the routines are handed, staged in the lists' band (`aes_evasync`) and the pipes' (`aes_pdpipe`) ------------
MOBLK_AT, SECOND_MOBLK_AT, ANSWERS_AT = evasync.FIRST_RECT_AT, evasync.SECOND_RECT_AT, evasync.ANSWERS_AT
BUFFER_AT, MESSAGE_AT, QPB_AT = aes_pdpipe.BUFFER_AT, aes_pdpipe.MESSAGE_AT, aes_pdpipe.QPB_AT
EV_RETS_WORDS = 4                       # the mouse's x and y, the buttons, the shift keys ($fe682a..$fe6864)
STALE_ANSWERS = {ANSWERS_AT: struct.pack(">H", aes.STALE_WORD) * evasync.ANSWER_WORDS}    # an answer not written shows
LEAVE, ENTER = evasync.LEAVE, evasync.ENTER
moblk, button_wait = evasync.moblk, evasync.button_wait
ROUND_THE_MOUSE, ELSEWHERE = evasync.ROUND_THE_MOUSE, evasync.ELSEWHERE
TICK_MS = evasync.TICK_MS
SHELL, SCREEN_MANAGER = aes.SHELL_PD, aes.SCREEN_MANAGER_PD
SHELL_PID, SCREEN_MANAGER_PID = aes_pdpipe.SHELL_PID, aes_pdpipe.SCREEN_MANAGER_PID
WIND_SPB = wm_update.WIND_SPB
SPB_COUNT, SPB_OWNER, SPB_WAIT = wm_update.SPB_COUNT, wm_update.SPB_OWNER, wm_update.WU["SPB_WAIT"]
BEG_UPDATE, END_UPDATE = aes.WM_BEG_UPDATE, aes.WM_END_UPDATE
CODES = {name.removeprefix("IASYNC_").lower(): value for name, value in EVWAIT.items()
         if name.startswith("IASYNC_") and name != "IASYNC_FIRST_EVENT"}
READ, WRITE, DELAY, MUTEX = CODES["read"], CODES["write"], CODES["delay"], CODES["mutex"]
KEYBOARD, MOUSE, BUTTON = CODES["keyboard"], CODES["mouse"], CODES["button"]
NO_WAIT = 0                             # a code iasync's table has no wait for: the EVB is taken, and queued nowhere
STAGED_APPLICATION = aes_pdpipe.STAGED_APPLICATION

# ---- what differs by nature ------------------------------------------------------------------------------------------
# The Line-F mask word, and spl7_save's SR save word under adelay's bracket (`aes_event.SR_DROPS`): each dropped only
# where the ROM's run stores it.
DROPS = aes.LINE_F_MASK_WINDOW + aes_event.sr_drops(aes.AES_SR_SPL)


# THE ATTRIBUTION PASS, and what steers it here beside the lists' links and a pipe's index (`aes_pdpipe.STEERS_*`):
STEERS_THE_EVENT_BITS = aes.steers(
    "a process's three event words: iasync gives a wait the first bit PD_EVBITS does not hold, mwait blocks unless "
    "PD_EVFLG holds a bit of its mask, and apret finds the EVB by that bit — inverted (every bit held) the wait gets "
    "no bit at all, and the run reaches the dispatcher instead of returning",
    *((pd + field, pd + field + WORD_BYTES) for pd in aes_pdpipe.STATIC_PDS
      for field in (aes.PD_EVBITS, aes.PD_EVWAIT, aes.PD_EVFLG)))
STEERS_THE_LISTS, STEERS_THE_INDEX = aes_pdpipe.STEERS_THE_LISTS, aes_pdpipe.STEERS_THE_INDEX
STEERS_THE_LOCK = aes.steers(
    "the screen lock's count and owner, which tak_flag stores and amutex's road is decided by: inverted, the lock is "
    "another's — the wait parks instead of returning",
    (wm_update.WIND_SPB, wm_update.WIND_SPB + wm_update.SPB_OWNER + LONG_BYTES))


def _in_the_stack_band(address):
    return (address & aes_event.OS_BUS_ADDR_MASK) in case.STACK_BAND


def qpb_address_drop(evb):
    """The one drop a BLOCKED ap_rdwr adds: the QPB's address a parked pipe wait keeps in its EVB (`aqueue`'s
    `evb->parm = qpb`) — ap_rdwr's own argument frame in the ROM, a place in its caller's stack; the C's QPB is a
    local of its own (off target: its process's host slot). Never dropped unvetted: `held` holds both addresses to
    the stack band and the eight bytes each names to the same QPB (`vet_the_parked_qpb`)."""
    return ((evb + aes.EVB_PARM, evb + aes.EVB_PARM + LONG_BYTES,
             "a parked pipe wait's QPB address: ap_rdwr's own arguments, a place in its caller's stack"),)


def parked_qpb(name, arguments, machine):
    """The QPB a call of `name` that PARKS leaves its wait pointing at — `(process, count, buffer)`, each as handed —
    or None for a call that parks none: ap_rdwr waiting on a pipe (with any other code it hands ev_block the same
    address, and no routine keeps it), and ev_mesag, which reads the running process's own pipe."""
    if name == AP_RDWR and arguments[0] in WAITS_ON_A_PIPE:
        _code, process, count, buffer = arguments
        return aes.signed(process), aes.signed(count), buffer & aes.LONG_MASK
    if name == EV_MESAG:
        image = make_image(machine)
        pid = case.word_in(image, (evasync.running(image) & aes_event.OS_BUS_ADDR_MASK) + aes.PD_PID)
        return aes.signed(pid), len(A_MESSAGE), arguments[0] & aes.LONG_MASK
    return None


def vet_the_parked_qpb(name, arguments, machine, switched):
    """THE NAMED DROP'S OTHER HALF, for every case that makes it — the door's own rule (`aes_event.parked_qpb_drop`:
    the wait's EVB the same on both shores, each shore's parameter an address in that shore's stack band, the eight
    bytes each names the same QPB) — and here the QPB is known: THE ONE THE CALL WAS HANDED, the process, the count
    and the buffer (`parked_qpb`)."""
    vetted = aes_event.parked_qpb_drop(name, switched.image, switched.rom_memory)
    assert min(vetted) == evasync.free_evbs(make_image(machine))[0] + aes.EVB_PARM, f"{name}: another EVB vetted than dropped"
    ours = case.long_in(switched.image, min(vetted))
    assert aes_pdpipe.QPB.unpack_from(switched.image, ours) == parked_qpb(name, arguments, machine), (
        f"{name}: the parked wait names the QPB {aes_pdpipe.QPB.unpack_from(switched.image, ours)}, "
        f"handed {parked_qpb(name, arguments, machine)}")


# ---- a run WATCHED at the eighteen routines' entries (`aes_event.Layer`: the family every layer's battery shares) -------
Arrival, Watched = aes_event.LayerArrival, aes_event.Watched
QPB_BYTES = aes_pdpipe.QPB.size
ROM_QPB_AT = abi.FIRST_ARG + WORD_BYTES     # ap_rdwr's QPB in a run entered at it: its frame past the code word ($fe65ca)


def _qpb_moved_out_of_the_stack(name, arguments, memory, machine):
    """An arrival handed a QPB IN ITS CALLER'S STACK (ev_block and iasync under ap_rdwr, whose QPB is its own
    arguments): the stack band is no part of a machine — every case stages its own frame there — so the QPB's eight
    bytes are kept in the pipes' band and the pointer re-aimed (`aes_event.Layer`'s `restaged`)."""
    if name not in (EV_BLOCK, IASYNC) or arguments[0] not in (READ, WRITE) or not _in_the_stack_band(arguments[1]):
        return arguments, machine
    at = arguments[1] & aes_event.OS_BUS_ADDR_MASK
    return (arguments[0], QPB_AT), merge_pokes(machine, {QPB_AT: bytes(memory[at:at + QPB_BYTES])})


# A call is watched "to its return or to dsptch": dsptch is the one end a run may return without reaching.
LAYER = aes_event.Layer(ROUTINES, restaged=_qpb_moved_out_of_the_stack, may_return_before={addrs.AES_ROM_DSPTCH})
ENTRIES, FRAMES = LAYER.entries, LAYER.frames
machine_of = LAYER.machine_of           # `memory` as pokes over the snapshot, the stack band out
frame_of = LAYER.frame_of               # the Alcyon frame of `addrs.<name>` for its arguments


def watched(pokes, entry, ends=frozenset(), frame=b"", once_past=None):
    """The ROM's `entry` over `pokes` (its `frame` where a `jsr` leaves it), WATCHED AT THE ROUTINES' ENTRIES
    (`aes_event.Layer.watched`) until it reaches one of `ends` (after `once_past`, when named) or returns: every
    `Arrival`, in order, and the machine at the end."""
    return LAYER.watched(pokes, entry, ends, frame, once_past)


def called(machine, name, *arguments):
    """A RUNNING process's own call of the ROM's `addrs.<name>` over `machine`, to its return or to dsptch: the
    arrivals."""
    frame = frame_of(name, arguments) if name in FRAMES else aes_event.frame_of(*arguments)
    return watched(machine, getattr(addrs, name), {addrs.AES_ROM_DSPTCH}, frame).arrivals


# ---- THE ROM AT DSPTCH, AND THE C HELD TO IT ---------------------------------------------------------------------------
BLOCKS, YIELDS = aes_event.BLOCKS, aes_event.YIELDS
Switched = aes_event.Switched


@derived.kept
def _switches(name, arguments, machine):
    image = make_image(aes.staged(name, vdi.as_signed(name, arguments), machine))
    _final, _writes, regs = emu.run(image, getattr(addrs, name), stop_pc=addrs.AES_ROM_DSPTCH)
    return bool(regs["checkpoint"])


def switches(name, arguments, machine):
    """Does the ROM's call reach the dispatcher (a block, or a yield) rather than return? Asked of the ROM's own run
    of it — a derivation, kept by content."""
    return _switches(name, tuple(arguments), machine)


def switched(name, arguments, pokes, how=BLOCKS, dropped=()):
    """A CALL THAT REACHES THE DISPATCHER, held where the C stops (`aes_event.switches_where_the_rom_does`): the
    ROM's run reaches dsptch asking for the switch `how` names; the C, in a fork, halts at the dispatcher's hook as
    one that does; and the image it holds there is the ROM's memory AT DSPTCH — outside the stack band, the mask
    word, the SR save words and `dropped`. The `Switched`, for the case's own assertions."""
    return aes_event.switches_where_the_rom_does(name, arguments, pokes, switches=how, dropped=dropped)


# ---- THE MACHINES a scenario starts from: each the scheduler's own -----------------------------------------------------
def _answers_stale(machine):
    return merge_pokes(machine, STALE_ANSWERS)


@functools.cache
def desk_running():
    """PD0 running (`aes_event.machine`), the answer words stale."""
    return _answers_stale(aes_pdpipe.running())


@functools.cache
def manager_running():
    """The SCREEN MANAGER running, PD0 parked in the desk's evnt_multi."""
    return _answers_stale(aes_pdpipe.screen_manager_running())


@functools.cache
def key_queued(count=1):
    """PD0 running with keys queued for it (`test_aes_fmlib.queued`: polled by the ROM's chkkbd and forker)."""
    return _answers_stale(test_aes_fmlib.queued(count))


@functools.cache
def key_queued_round_the_ring():
    """...two keys queued after seven were queued and flushed: the queue's front is its last slot, and the next
    one taken wraps it."""
    return _answers_stale(test_aes_fmlib.queued(2, 7))


ALT_KEY, EQUALS_KEY = 0x38, 0x0D           # make codes: Alt, and `=` — together the BIOS's key $8300, bit 15 set
ALT_EQUALS = 0x8300                     # ...that key, as the keyboard queue holds it
ALT_HELD = 0x08                         # the shift state with Alt down (Kbshift's bit 3), as AES_KSTATE keeps it


@functools.cache
def alt_key_queued():
    """PD0 running with Alt held and Alt-= queued: a key whose word is NEGATIVE ($8300), the shift state not 0."""
    return _answers_stale(test_aes_fmlib.polled(aes_event.pd0_running(), ALT_KEY, EQUALS_KEY))


@functools.cache
def after_a_mouse_wait():
    """PD0 running again after an evnt_multi that PARKED for the mouse to leave a rectangle and was woken by it
    leaving — every step the scheduler's: the last answer apret took was that mouse wait's."""
    frame, pokes = evasync.ev_multi_frame(evasync.MU_M1 | evasync.MU_KEYBD, first=moblk(LEAVE, *ROUND_THE_MOUSE))
    parked = aes_event.parked(addrs.AES_ROM_EV_MULTI, frame, merge_pokes(desk_running(), pokes))
    running, _final, _registers = aes_event.dispatched(evasync.taken(parked, evasync.AWAY), SHELL)
    return _answers_stale(running)


@functools.cache
def after_a_timer_ran_out():
    """PD0 running again after an evnt_multi that parked for a timer the tick glue then counted out: no delay
    pending, the countdown 0 — and the ticks counted so far as the glue left them."""
    frame, pokes = evasync.ev_multi_frame(evasync.MU_TIMER, timer=A_TIMER_MS)
    parked = aes_event.parked(addrs.AES_ROM_EV_MULTI, frame, merge_pokes(desk_running(), pokes))
    running, _final, _registers = aes_event.dispatched(evasync.taken(parked, evasync.ticks(A_TIMER_MS // TICK_MS)), SHELL)
    return _answers_stale(running)


@functools.cache
def desk_running_the_mouse_on_the_bar():
    """PD0 running while the mouse is on the menu bar — the SCREEN MANAGER's then, which is parked waiting for the
    screen's lock PD0 holds (`test_aes_wm_update.waited_on`)."""
    return _answers_stale(wm_update.waited_on())


@functools.cache
def writer_waiting():
    """PD0 running, its pipe full, the SCREEN MANAGER parked in a write that no longer fits
    (`aes_pdpipe.writer_waiting`)."""
    return _answers_stale(aes_pdpipe.writer_waiting())


@functools.cache
def button_held():
    """PD0 running with the left button DOWN (`aes_event.button_down`)."""
    return _answers_stale(aes_event.machine(aes_event.button_down))


@functools.cache
def holding(count):
    """PD0 running with `count` messages in its own pipe (`aes_pdpipe.holding`: the ROM's own appl_writes)."""
    return _answers_stale(aes_pdpipe.holding(count))


@functools.cache
def lock_held_by_the_desk():
    """The SCREEN MANAGER running, the screen's lock PD0's (PD0 took it and parked for a key; the mouse onto the menu
    bar woke PD1)."""
    return aes_event.woken_onto_the_menu_bar(aes_event.parked(addrs.AES_ROM_EV_MULTI, wm_update.KEY_WAIT,
                                                               wm_update.locked()))


A_DELAY_MS = 400                        # the staged application's delay, where one is pending: 20 ticks


@functools.cache
def delay_pending(milliseconds=A_DELAY_MS):
    """A STAGED APPLICATION's machine: PD0 running while the application waits in its evnt_timer(`milliseconds`) —
    one delay on the delay list, the countdown armed."""
    application = aes_pdpipe.staged_application("AES_ROM_EV_TIMER", milliseconds)
    return _answers_stale(aes_pdpipe.resumed(aes_pdpipe.called(application)))


@functools.cache
def _lock_application():
    """The staged application whose one call is wind_update(BEG_UPDATE), made by PD0 while it holds the lock with the
    screen manager queued on it (`test_aes_wm_update.waited_on`)."""
    return aes_pdpipe.staged_application("AES_ROM_WM_UPDATE", BEG_UPDATE, onto=wm_update.waited_on())


def _second_waiter_queues():
    """A STAGED APPLICATION's scenario: PD0, holding the lock with the screen manager queued on it, parks for a key;
    the dispatcher enters the application, whose wind_update(BEG_UPDATE) is refused and queues it on the lock BEFORE
    the screen manager; the run ends where the dispatcher's loop begins again."""
    application = _lock_application()
    return watched(aes_pdpipe._maker_parked(application), addrs.AES_ROM_DISP_LOOP, {addrs.AES_ROM_DISP_LOOP},
                   once_past=application.stub)


@functools.cache
def two_waiters():
    """A STAGED APPLICATION's machine: PD0 running again (Return), the lock its own, TWO processes queued on it —
    the application first (the last to wait), the screen manager behind it."""
    machine = _answers_stale(aes_pdpipe.resumed(_second_waiter_queues().machine))
    image = make_image(machine)
    waiting = evasync.wait_list(image, WIND_SPB + SPB_WAIT)
    assert [case.long_in(image, evb + aes.EVB_PD) for evb in waiting] == [aes_pdpipe.SPARE_PD, SCREEN_MANAGER]
    return machine


# ---- ARGUMENT-CLASS MACHINES: the ROM's own iasync, called more than once for one process -------------------------------
def after_iasync(machine, code, parameter):
    """`machine` after the ROM's own iasync(code, parameter) by its running process: one more wait queued (or
    completed where it was queued), and not waited for."""
    written, _final, _registers = aes_event.derived(addrs.AES_ROM_IASYNC, machine, frame=frame_of(IASYNC, (code, parameter)))
    return merge_pokes(machine, written)


def after_apret(machine, event):
    """`machine` after the ROM's own apret(event) by its running process: the completed wait of that bit answered."""
    written, _final, _registers = aes_event.derived(addrs.AES_ROM_APRET, machine, frame=struct.pack(">h", event))
    return merge_pokes(machine, written)


THE_BUTTON_UP = button_wait(evasync.SINGLE, aes_event.LEFT_BUTTON, 0)     # a button wait the snapshot's mouse satisfies


@functools.cache
def two_events_come():
    """PD0 with TWO waits completed and not yet answered: for a key that is queued and for the button up, which it
    is. (No ROM caller leaves two: evnt_multi answers a satisfied wait on its fast path before it queues any.)"""
    return after_iasync(after_iasync(key_queued(), KEYBOARD, 0), BUTTON, THE_BUTTON_UP)


EVENT_BITS_IN_A_BYTE = 8


@functools.cache
def eight_event_bits_held():
    """PD0 holding its eight LOW event bits — eight waits of a code no wait has (the EVB keeps its bit, on no list):
    the next wait's bit is $100."""
    machine = desk_running()
    for _wait in range(EVENT_BITS_IN_A_BYTE):
        machine = after_iasync(machine, NO_WAIT, 0)
    return machine


@functools.cache
def the_ninth_event_alone_come():
    """PD0 with nine button waits satisfied and the low eight answered (the ROM's own apret, a bit at a time): the
    one event come and not answered is bit 8, PD_EVFLG == $100."""
    machine = desk_running()
    for _wait in range(EVENT_BITS_IN_A_BYTE + 1):
        machine = after_iasync(machine, BUTTON, THE_BUTTON_UP)
    for bit in range(EVENT_BITS_IN_A_BYTE):
        machine = after_apret(machine, 1 << bit)
    return machine


@functools.cache
def delays_pending(*ticks):
    """PD0 running with one delay of each of `ticks` queued, in that order: the delay list two or three processes'
    evnt_timers would make, made by one."""
    machine = desk_running()
    for each in ticks:
        machine = after_iasync(machine, DELAY, each)
    return machine


@functools.cache
def two_waits_of_one_process_on_the_lock():
    """PD0 running again (Return), the screen's lock its own, and TWO waits of the SCREEN MANAGER queued on it with a
    wait of no kind taken between them — so the second's NEXT (its process's event list: that wait) is not its LINK
    (the lock's list: the first). The screen manager, the lock PD0's, queues the three itself, waits for either
    (the ROM's own mwait parks it) and PD0 is woken by its key."""
    machine = after_iasync(lock_held_by_the_desk(), MUTEX, WIND_SPB)
    machine = after_iasync(after_iasync(machine, NO_WAIT, 0), MUTEX, WIND_SPB)
    first, second = evasync.wait_list(make_image(machine), WIND_SPB + SPB_WAIT)
    either = evasync.evb_of(make_image(machine), first)["MASK"] | evasync.evb_of(make_image(machine), second)["MASK"]
    parked = aes_event.parked(addrs.AES_ROM_EV_MWAIT, struct.pack(">h", either), machine)
    return _answers_stale(aes_pdpipe.resumed(parked))


# ---- THE SCENARIOS -------------------------------------------------------------------------------------------------------
WM_UPDATE = "AES_ROM_WM_UPDATE"
A_TIMER_MS = evasync.A_TIMER_MS
A_MESSAGE = evasync.A_MESSAGE
SINGLE, DOUBLE = evasync.SINGLE, evasync.DOUBLE
LEFT, UP, DOWN = aes_event.LEFT_BUTTON, 0, aes_event.LEFT_BUTTON
FULL_PIPE = aes_pdpipe.PIPE_MESSAGES
RIGHT = 2                               # the right button's bit of the AES's record of the buttons
EITHER = 0x100                          # a button wait's clicks with its high byte set: wait for the masked buttons NOT in the state
A_LEAVE_FLAG_ABOVE_ITS_BYTE = 0x100     # a MOBLK's leave flag no bit of whose LOW byte is set: amouse tests the word
SERVES_A_WRITER = "appl_read while the screen manager waits to write"       # a scenario two batteries price rows of
WIDE_STATE = 0x0201                     # a state whose high byte reaches the mask's byte (`or.w 12(a6),d1`, $fe68b8)
OUTSIDE_THE_MASK = 3                    # a state with a bit its mask (the left button's) does not have: ORed in all the same
WIDE_MASK = 0x0201                      # a mask whose high byte the WORD shift loses (`lsl.w #8,d1`): a long's would reach the clicks
ABOVE_THE_SCREEN = (300, -10, 20, 5)    # a rectangle whose y is negative: amouse's `add.l` borrows from its x
OF_NEGATIVE_HEIGHT = (300, 150, 20, -5)  # ...and one whose h is: the borrow is from its w
THE_MENU_BAR = (0, 0, 640, 11)          # a rectangle round `aes_event.MENU_BAR_POINT`
DCLICK_RATES = range(EVLIB["AES_DCLICK_RATES"])     # the ROM's table of milliseconds: `aes/evlib.h` says where it ends
ANOTHER_MESSAGE = aes_pdpipe.message(evasync.MN_SELECTED_MESSAGE + 1, evasync.AN_ITEM, evasync.A_TITLE)
MU = evasync


ITS_OWN = "the process queued itself (the ROM's iasync)"
BEHIND_TWO_DELAYS = f"evnt_timer behind two delays {ITS_OWN}"
BETWEEN_TWO_DELAYS = f"evnt_timer between two delays {ITS_OWN}"
BEHIND_THREE_DELAYS = f"evnt_timer behind three delays {ITS_OWN}"
TWO_WAITS_OF_ONE_PROCESS = "wind_update(END), two waits of the screen manager on the lock (the ROM's iasync)"


def _multi(machine, flags, **parameters):
    def run():
        frame, pokes = evasync.ev_multi_frame(flags, **parameters)
        return watched(merge_pokes(machine(), pokes), addrs.AES_ROM_EV_MULTI, {addrs.AES_ROM_DSPTCH}, frame).arrivals
    return run


def _call(machine, name, *arguments, staged=None):
    return lambda: called(merge_pokes(machine(), staged), name, *arguments)


def _woken_by(*interrupts):
    """The dispatcher's loop from where the snapshot waits, an interrupt taken, to where a process comes out of its
    evnt_multi — whose tail answers through ev_rets."""
    return lambda: watched(evasync.taken({}, *interrupts), addrs.AES_ROM_DISP_LOOP, {addrs.AES_ROM_EV_MULTI_RETURN}).arrivals


def _moblk(leave, rect, at=MOBLK_AT):
    return {at: moblk(leave, *rect)}


THE_LOCK_THE_MENU_HOLDS = "wind_update(BEG), the lock the screen manager's menu holds"
RUNS = {
    # the single waits, as an application calls them
    "evnt_keybd, a key queued": _call(key_queued, EV_KEYBD),
    "evnt_keybd, none": _call(desk_running, EV_KEYBD),
    "evnt_button for the button up, which is up": _call(desk_running, EV_BUTTON, SINGLE, LEFT, UP, ANSWERS_AT),
    "evnt_button for the button down, which is down": _call(button_held, EV_BUTTON, SINGLE, LEFT, DOWN, ANSWERS_AT),
    "evnt_button for a press": _call(desk_running, EV_BUTTON, SINGLE, LEFT, DOWN, ANSWERS_AT),
    "evnt_button for a double click": _call(desk_running, EV_BUTTON, DOUBLE, LEFT, DOWN, ANSWERS_AT),
    "evnt_mouse to enter the rectangle the mouse is in": _call(
        desk_running, EV_MOUSE, MOBLK_AT, ANSWERS_AT, staged=_moblk(ENTER, ROUND_THE_MOUSE)),
    "evnt_mouse to leave a rectangle the mouse is not in": _call(
        desk_running, EV_MOUSE, MOBLK_AT, ANSWERS_AT, staged=_moblk(LEAVE, ELSEWHERE)),
    "evnt_mouse to leave the rectangle the mouse is in": _call(
        desk_running, EV_MOUSE, MOBLK_AT, ANSWERS_AT, staged=_moblk(LEAVE, ROUND_THE_MOUSE)),
    "evnt_mouse to enter a rectangle the mouse is not in": _call(
        desk_running, EV_MOUSE, MOBLK_AT, ANSWERS_AT, staged=_moblk(ENTER, ELSEWHERE)),
    "evnt_keybd, three keys queued": _call(lambda: key_queued(3), EV_KEYBD),
    "evnt_keybd, Alt-= queued": _call(alt_key_queued, EV_KEYBD),
    "evnt_button for the button up, Alt held": _call(alt_key_queued, EV_BUTTON, SINGLE, LEFT, UP, ANSWERS_AT),
    "evnt_keybd, the queue's front round the ring": _call(key_queued_round_the_ring, EV_KEYBD),
    "evnt_button for the right button down": _call(desk_running, EV_BUTTON, SINGLE, RIGHT, RIGHT, ANSWERS_AT),
    "evnt_button for either button not up, which they are": _call(
        desk_running, EV_BUTTON, EITHER | SINGLE, LEFT | RIGHT, UP, ANSWERS_AT),
    "evnt_button for either button not up, the left down": _call(
        button_held, EV_BUTTON, EITHER | SINGLE, LEFT | RIGHT, UP, ANSWERS_AT),
    "evnt_button with a state wider than a byte": _call(desk_running, EV_BUTTON, SINGLE, LEFT, WIDE_STATE, ANSWERS_AT),
    "evnt_button with state bits outside its mask": _call(desk_running, EV_BUTTON, SINGLE, LEFT, OUTSIDE_THE_MASK, ANSWERS_AT),
    "evnt_button with a mask wider than a byte": _call(desk_running, EV_BUTTON, SINGLE, WIDE_MASK, DOWN, ANSWERS_AT),
    "evnt_mouse to enter a rectangle above the screen": _call(
        desk_running, EV_MOUSE, MOBLK_AT, ANSWERS_AT, staged=_moblk(ENTER, ABOVE_THE_SCREEN)),
    "evnt_mouse to enter a rectangle of negative height": _call(
        desk_running, EV_MOUSE, MOBLK_AT, ANSWERS_AT, staged=_moblk(ENTER, OF_NEGATIVE_HEIGHT)),
    "evnt_mouse with a leave flag of 2": _call(
        desk_running, EV_MOUSE, MOBLK_AT, ANSWERS_AT, staged=_moblk(2, ROUND_THE_MOUSE)),
    "evnt_mouse to enter the rectangle the mouse is in, the button down": _call(
        button_held, EV_MOUSE, MOBLK_AT, ANSWERS_AT, staged=_moblk(ENTER, ROUND_THE_MOUSE)),
    "evnt_mouse with a leave flag of $100, the mouse outside": _call(
        desk_running, EV_MOUSE, MOBLK_AT, ANSWERS_AT, staged=_moblk(A_LEAVE_FLAG_ABOVE_ITS_BYTE, ELSEWHERE)),
    "evnt_timer": _call(desk_running, EV_TIMER, A_TIMER_MS),
    "evnt_timer after a timer ran out": _call(after_a_timer_ran_out, EV_TIMER, A_TIMER_MS),
    "evnt_timer of a negative time": _call(desk_running, EV_TIMER, -A_TIMER_MS),
    "evnt_timer of no time": _call(desk_running, EV_TIMER, 0),
    "evnt_mesag, a message in the pipe": _call(lambda: holding(1), EV_MESAG, BUFFER_AT),
    "evnt_mesag, two messages in the pipe": _call(lambda: holding(2), EV_MESAG, BUFFER_AT),
    "evnt_mesag, none": _call(desk_running, EV_MESAG, BUFFER_AT),
    "evnt_mesag, the pipe full": _call(lambda: holding(FULL_PIPE), EV_MESAG, BUFFER_AT),
    **{f"evnt_dclick sets rate {rate}": _call(desk_running, EV_DCLICK, rate, 1) for rate in DCLICK_RATES},
    "evnt_dclick asks the rate": _call(desk_running, EV_DCLICK, 1, 0),
    # appl_write and appl_read
    "appl_write to the parked desk": _call(manager_running, AP_RDWR, WRITE, SHELL_PID, len(A_MESSAGE), MESSAGE_AT,
                                           staged={MESSAGE_AT: A_MESSAGE}),
    "appl_write to its own pipe": _call(desk_running, AP_RDWR, WRITE, SHELL_PID, len(A_MESSAGE), MESSAGE_AT,
                                        staged={MESSAGE_AT: A_MESSAGE}),
    "appl_write to a full pipe": _call(lambda: holding(FULL_PIPE), AP_RDWR, WRITE, SHELL_PID, len(A_MESSAGE), MESSAGE_AT,
                                       staged={MESSAGE_AT: A_MESSAGE}),
    "appl_read, a message in the pipe": _call(lambda: holding(1), AP_RDWR, READ, SHELL_PID, len(A_MESSAGE), BUFFER_AT),
    "appl_read, none": _call(desk_running, AP_RDWR, READ, SHELL_PID, len(A_MESSAGE), BUFFER_AT),
    "appl_write of two messages at once": _call(desk_running, AP_RDWR, WRITE, SHELL_PID, 2 * len(A_MESSAGE), MESSAGE_AT,
                                                staged={MESSAGE_AT: A_MESSAGE + ANOTHER_MESSAGE}),
    "appl_write to the screen manager's pipe": _call(desk_running, AP_RDWR, WRITE, SCREEN_MANAGER_PID, len(A_MESSAGE),
                                                     MESSAGE_AT, staged={MESSAGE_AT: A_MESSAGE}),
    "appl_read of the screen manager's pipe, empty": _call(desk_running, AP_RDWR, READ, SCREEN_MANAGER_PID,
                                                           len(A_MESSAGE), BUFFER_AT),
    SERVES_A_WRITER: _call(writer_waiting, AP_RDWR, READ, SHELL_PID,
                                                               len(A_MESSAGE), BUFFER_AT),
    "appl_read of a full pipe": _call(lambda: holding(FULL_PIPE), AP_RDWR, READ, SHELL_PID, len(A_MESSAGE), BUFFER_AT),
    # the screen's lock
    "wind_update(END), the lock held once": _call(wm_update.locked, WM_UPDATE, ("w", END_UPDATE)),
    "wind_update(END), the lock held twice": _call(lambda: wm_update.locked(times=2), WM_UPDATE, ("w", END_UPDATE)),
    "wind_update(END), nothing held": _call(wm_update.running, WM_UPDATE, ("w", END_UPDATE)),
    "wind_update(END), the screen manager waiting for the lock": _call(wm_update.waited_on, WM_UPDATE, ("w", END_UPDATE)),
    "wind_update(BEG), the lock another's": _call(lock_held_by_the_desk, WM_UPDATE, ("w", BEG_UPDATE)),
    "wind_update(BEG), the lock released once too often": _call(wm_update.released_unbalanced, WM_UPDATE,
                                                                ("w", BEG_UPDATE)),
    # ...the lock ANOTHER'S AND ITS HOLDER A ROM-RUN PROCESS: the screen manager's own menu, which gives it up (the
    # waiter's tail, which the harness-parked holder above leaves unrun, is run here; its builder is made below)
    THE_LOCK_THE_MENU_HOLDS: _call(lambda: the_manager_s_menu_holds_the_lock(), WM_UPDATE, ("w", BEG_UPDATE)),
    # evnt_multi: every kind of wait queued at once; its fast paths; its tail after a wake
    "evnt_multi for every event": _multi(
        desk_running, MU.MU_KEYBD | MU.MU_BUTTON | MU.MU_M1 | MU.MU_M2 | MU.MU_MESAG | MU.MU_TIMER,
        first=moblk(LEAVE, *ROUND_THE_MOUSE), second=moblk(ENTER, *ELSEWHERE), timer=A_TIMER_MS,
        button=button_wait(DOUBLE)),
    "evnt_multi for a message, one in the pipe": _multi(lambda: holding(1), MU.MU_MESAG),
    "evnt_multi for a rectangle the mouse is in": _multi(desk_running, MU.MU_M1, first=moblk(ENTER, *ROUND_THE_MOUSE)),
    "evnt_multi by the screen manager for a rectangle": _multi(manager_running, MU.MU_M1,
                                                               first=moblk(ENTER, *ROUND_THE_MOUSE)),
    "evnt_multi for the rectangle the mouse is in, the mouse the screen manager's": _multi(
        desk_running_the_mouse_on_the_bar, MU.MU_M1, first=moblk(ENTER, *THE_MENU_BAR)),
    "evnt_multi for two rectangles, the mouse where neither asks": _multi(
        desk_running, MU.MU_M1 | MU.MU_M2, first=moblk(LEAVE, *ROUND_THE_MOUSE), second=moblk(ENTER, *ELSEWHERE)),
    "evnt_multi to leave a rectangle the mouse is not in": _multi(desk_running, MU.MU_M1, first=moblk(LEAVE, *ELSEWHERE)),
    "evnt_multi for a rectangle the mouse is in, after a mouse wait was woken": _multi(
        after_a_mouse_wait, MU.MU_M1, first=moblk(LEAVE, *ROUND_THE_MOUSE)),
    "a key wakes the desk": _woken_by(evasync.RETURN),
    "a press wakes the desk": _woken_by(aes_event.press),
    evasync.THE_BAR_WAKES_THE_MANAGER: _woken_by(evasync.ONTO_THE_BAR),
    "a press, then the mouse moves, in one idle": _woken_by(aes_event.press, evasync.AWAY),
    # argument-class machines (the module's docstring): one process's own waits, queued by the ROM's iasync
    BEHIND_TWO_DELAYS: _call(lambda: delays_pending(10, 20), EV_TIMER, 50 * TICK_MS),
    BETWEEN_TWO_DELAYS: _call(lambda: delays_pending(10, 30), EV_TIMER, 15 * TICK_MS),
    BEHIND_THREE_DELAYS: _call(lambda: delays_pending(10, 20, 40), EV_TIMER, 100 * TICK_MS),
    TWO_WAITS_OF_ONE_PROCESS: _call(two_waits_of_one_process_on_the_lock, WM_UPDATE, ("w", END_UPDATE)),
    # a third process: the staged application
    f"{STAGED_APPLICATION}: evnt_timer shorter than the delay pending": _call(delay_pending, EV_TIMER, A_DELAY_MS // 2),
    f"{STAGED_APPLICATION}: evnt_timer longer than the delay pending": _call(delay_pending, EV_TIMER, A_DELAY_MS * 2),
    f"{STAGED_APPLICATION}: evnt_timer as long as the delay pending": _call(delay_pending, EV_TIMER, A_DELAY_MS),
    f"{STAGED_APPLICATION}: evnt_timer of a negative time, a delay pending": _call(delay_pending, EV_TIMER, -A_TIMER_MS),
    f"{STAGED_APPLICATION}: a second process queues on the lock": lambda: _second_waiter_queues().arrivals,
    f"{STAGED_APPLICATION}: wind_update(END), two processes waiting for the lock": _call(
        two_waiters, WM_UPDATE, ("w", END_UPDATE)),
}


# @DECLARED-BEGIN
# The arrivals each scenario DECLARES, in order (measured; `scenario` holds every run to them).
DECLARED = {
    "evnt_keybd, a key queued": (EV_KEYBD, EV_BLOCK, IASYNC, AKBIN, MWAIT),
    "evnt_keybd, none": (EV_KEYBD, EV_BLOCK, IASYNC, AKBIN, MWAIT),
    "evnt_button for the button up, which is up": (EV_BUTTON, EV_BLOCK, IASYNC, ABUTTON, MWAIT, EV_RETS),
    "evnt_button for the button down, which is down": (EV_BUTTON, EV_BLOCK, IASYNC, ABUTTON, MWAIT, EV_RETS),
    "evnt_button for a press": (EV_BUTTON, EV_BLOCK, IASYNC, ABUTTON, MWAIT),
    "evnt_button for a double click": (EV_BUTTON, EV_BLOCK, IASYNC, ABUTTON, MWAIT),
    "evnt_mouse to enter the rectangle the mouse is in": (EV_MOUSE, EV_BLOCK, IASYNC, AMOUSE, MWAIT, EV_RETS),
    "evnt_mouse to leave a rectangle the mouse is not in": (EV_MOUSE, EV_BLOCK, IASYNC, AMOUSE, MWAIT, EV_RETS),
    "evnt_mouse to leave the rectangle the mouse is in": (EV_MOUSE, EV_BLOCK, IASYNC, AMOUSE, MWAIT),
    "evnt_mouse to enter a rectangle the mouse is not in": (EV_MOUSE, EV_BLOCK, IASYNC, AMOUSE, MWAIT),
    "evnt_keybd, three keys queued": (EV_KEYBD, EV_BLOCK, IASYNC, AKBIN, MWAIT),
    "evnt_keybd, Alt-= queued": (EV_KEYBD, EV_BLOCK, IASYNC, AKBIN, MWAIT),
    "evnt_button for the button up, Alt held": (EV_BUTTON, EV_BLOCK, IASYNC, ABUTTON, MWAIT, EV_RETS),
    "evnt_keybd, the queue's front round the ring": (EV_KEYBD, EV_BLOCK, IASYNC, AKBIN, MWAIT),
    "evnt_button for the right button down": (EV_BUTTON, EV_BLOCK, IASYNC, ABUTTON, MWAIT),
    "evnt_button for either button not up, which they are": (EV_BUTTON, EV_BLOCK, IASYNC, ABUTTON, MWAIT),
    "evnt_button for either button not up, the left down": (EV_BUTTON, EV_BLOCK, IASYNC, ABUTTON, MWAIT, EV_RETS),
    "evnt_button with a state wider than a byte": (EV_BUTTON, EV_BLOCK, IASYNC, ABUTTON, MWAIT),
    "evnt_button with state bits outside its mask": (EV_BUTTON, EV_BLOCK, IASYNC, ABUTTON, MWAIT),
    "evnt_button with a mask wider than a byte": (EV_BUTTON, EV_BLOCK, IASYNC, ABUTTON, MWAIT),
    "evnt_mouse to enter a rectangle above the screen": (EV_MOUSE, EV_BLOCK, IASYNC, AMOUSE, MWAIT),
    "evnt_mouse to enter a rectangle of negative height": (EV_MOUSE, EV_BLOCK, IASYNC, AMOUSE, MWAIT),
    "evnt_mouse with a leave flag of 2": (EV_MOUSE, EV_BLOCK, IASYNC, AMOUSE, MWAIT, EV_RETS),
    "evnt_mouse to enter the rectangle the mouse is in, the button down": (
        EV_MOUSE, EV_BLOCK, IASYNC, AMOUSE, MWAIT, EV_RETS),
    "evnt_mouse with a leave flag of $100, the mouse outside": (EV_MOUSE, EV_BLOCK, IASYNC, AMOUSE, MWAIT, EV_RETS),
    "evnt_timer": (EV_TIMER, EV_BLOCK, IASYNC, ADELAY, MWAIT),
    "evnt_timer after a timer ran out": (EV_TIMER, EV_BLOCK, IASYNC, ADELAY, MWAIT),
    "evnt_timer of a negative time": (EV_TIMER, EV_BLOCK, IASYNC, ADELAY, MWAIT),
    "evnt_timer of no time": (EV_TIMER, EV_BLOCK, IASYNC, ADELAY, MWAIT),
    "evnt_mesag, a message in the pipe": (EV_MESAG, AP_RDWR, EV_BLOCK, IASYNC, MWAIT),
    "evnt_mesag, two messages in the pipe": (EV_MESAG, AP_RDWR, EV_BLOCK, IASYNC, MWAIT),
    "evnt_mesag, none": (EV_MESAG, AP_RDWR, EV_BLOCK, IASYNC, MWAIT),
    "evnt_mesag, the pipe full": (EV_MESAG, AP_RDWR, EV_BLOCK, IASYNC, MWAIT),
    "evnt_dclick sets rate 0": (EV_DCLICK,),
    "evnt_dclick sets rate 1": (EV_DCLICK,),
    "evnt_dclick sets rate 2": (EV_DCLICK,),
    "evnt_dclick sets rate 3": (EV_DCLICK,),
    "evnt_dclick sets rate 4": (EV_DCLICK,),
    "evnt_dclick asks the rate": (EV_DCLICK,),
    "appl_write to the parked desk": (AP_RDWR, EV_BLOCK, IASYNC, MWAIT),
    "appl_write to its own pipe": (AP_RDWR, EV_BLOCK, IASYNC, MWAIT),
    "appl_write to a full pipe": (AP_RDWR, EV_BLOCK, IASYNC, MWAIT),
    "appl_read, a message in the pipe": (AP_RDWR, EV_BLOCK, IASYNC, MWAIT),
    "appl_read, none": (AP_RDWR, EV_BLOCK, IASYNC, MWAIT),
    "appl_write of two messages at once": (AP_RDWR, EV_BLOCK, IASYNC, MWAIT),
    "appl_write to the screen manager's pipe": (AP_RDWR, EV_BLOCK, IASYNC, MWAIT),
    "appl_read of the screen manager's pipe, empty": (AP_RDWR, EV_BLOCK, IASYNC, MWAIT),
    SERVES_A_WRITER: (AP_RDWR, EV_BLOCK, IASYNC, MWAIT),
    "appl_read of a full pipe": (AP_RDWR, EV_BLOCK, IASYNC, MWAIT),
    "wind_update(END), the lock held once": (UNSYNC,),
    "wind_update(END), the lock held twice": (UNSYNC,),
    "wind_update(END), nothing held": (UNSYNC,),
    "wind_update(END), the screen manager waiting for the lock": (UNSYNC,),
    "wind_update(BEG), the lock another's": (EV_BLOCK, IASYNC, AMUTEX, MWAIT),
    "wind_update(BEG), the lock released once too often": (EV_BLOCK, IASYNC, AMUTEX, MWAIT),
    THE_LOCK_THE_MENU_HOLDS: (EV_BLOCK, IASYNC, AMUTEX, MWAIT),
    "evnt_multi for every event": (
        EV_MCHK, EV_MCHK, IASYNC, AKBIN, IASYNC, ABUTTON, IASYNC, AMOUSE, IASYNC, AMOUSE, IASYNC, IASYNC, ADELAY, MWAIT),
    "evnt_multi for a message, one in the pipe": (EV_MESAG, AP_RDWR, EV_BLOCK, IASYNC, MWAIT, EV_RETS),
    "evnt_multi for a rectangle the mouse is in": (EV_MCHK, EV_RETS),
    "evnt_multi by the screen manager for a rectangle": (EV_MCHK, IASYNC, AMOUSE, MWAIT),
    "evnt_multi for the rectangle the mouse is in, the mouse the screen manager's": (
        EV_MCHK, IASYNC, AMOUSE, MWAIT, EV_RETS),
    "evnt_multi for two rectangles, the mouse where neither asks": (
        EV_MCHK, EV_MCHK, IASYNC, AMOUSE, IASYNC, AMOUSE, MWAIT),
    "evnt_multi to leave a rectangle the mouse is not in": (EV_MCHK, EV_RETS),
    "evnt_multi for a rectangle the mouse is in, after a mouse wait was woken": (EV_MCHK, EV_RETS),
    "a key wakes the desk": (EV_RETS,),
    "a press wakes the desk": (EV_RETS,),
    evasync.THE_BAR_WAKES_THE_MANAGER: (EV_RETS,),
    "a press, then the mouse moves, in one idle": (EV_RETS,),
    BEHIND_TWO_DELAYS: (EV_TIMER, EV_BLOCK, IASYNC, ADELAY, MWAIT),
    BETWEEN_TWO_DELAYS: (EV_TIMER, EV_BLOCK, IASYNC, ADELAY, MWAIT),
    BEHIND_THREE_DELAYS: (EV_TIMER, EV_BLOCK, IASYNC, ADELAY, MWAIT),
    TWO_WAITS_OF_ONE_PROCESS: (UNSYNC,),
    f"{STAGED_APPLICATION}: evnt_timer shorter than the delay pending": (EV_TIMER, EV_BLOCK, IASYNC, ADELAY, MWAIT),
    f"{STAGED_APPLICATION}: evnt_timer longer than the delay pending": (EV_TIMER, EV_BLOCK, IASYNC, ADELAY, MWAIT),
    f"{STAGED_APPLICATION}: evnt_timer as long as the delay pending": (EV_TIMER, EV_BLOCK, IASYNC, ADELAY, MWAIT),
    f"{STAGED_APPLICATION}: evnt_timer of a negative time, a delay pending": (
        EV_TIMER, EV_BLOCK, IASYNC, ADELAY, MWAIT),
    f"{STAGED_APPLICATION}: a second process queues on the lock": (EV_BLOCK, IASYNC, AMUTEX, MWAIT),
    f"{STAGED_APPLICATION}: wind_update(END), two processes waiting for the lock": (UNSYNC,),
}
# ...and which of them REACH THE DISPATCHER (each one's index in its scenario): a wait nothing satisfies, a
# hand-over.
SWITCHING = {
    "evnt_keybd, none": (0, 1, 4),
    "evnt_button for a press": (0, 1, 4),
    "evnt_button for a double click": (0, 1, 4),
    "evnt_mouse to leave the rectangle the mouse is in": (0, 1, 4),
    "evnt_mouse to enter a rectangle the mouse is not in": (0, 1, 4),
    "evnt_button for the right button down": (0, 1, 4),
    "evnt_button for either button not up, which they are": (0, 1, 4),
    "evnt_button with a state wider than a byte": (0, 1, 4),
    "evnt_button with state bits outside its mask": (0, 1, 4),
    "evnt_button with a mask wider than a byte": (0, 1, 4),
    "evnt_mouse to enter a rectangle above the screen": (0, 1, 4),
    "evnt_mouse to enter a rectangle of negative height": (0, 1, 4),
    "evnt_timer": (0, 1, 4),
    "evnt_timer after a timer ran out": (0, 1, 4),
    "evnt_timer of a negative time": (0, 1, 4),
    "evnt_timer of no time": (0, 1, 4),
    "evnt_mesag, none": (0, 1, 2, 4),
    "appl_write to a full pipe": (0, 1, 3),
    "appl_read, none": (0, 1, 3),
    "appl_read of the screen manager's pipe, empty": (0, 1, 3),
    "wind_update(END), the screen manager waiting for the lock": (0,),
    "wind_update(BEG), the lock another's": (0, 3),
    "wind_update(BEG), the lock released once too often": (0, 3),
    THE_LOCK_THE_MENU_HOLDS: (0, 3),
    "evnt_multi for every event": (13,),
    "evnt_multi by the screen manager for a rectangle": (3,),
    "evnt_multi for two rectangles, the mouse where neither asks": (6,),
    BEHIND_TWO_DELAYS: (0, 1, 4),
    BETWEEN_TWO_DELAYS: (0, 1, 4),
    BEHIND_THREE_DELAYS: (0, 1, 4),
    TWO_WAITS_OF_ONE_PROCESS: (0,),
    f"{STAGED_APPLICATION}: evnt_timer shorter than the delay pending": (0, 1, 4),
    f"{STAGED_APPLICATION}: evnt_timer longer than the delay pending": (0, 1, 4),
    f"{STAGED_APPLICATION}: evnt_timer as long as the delay pending": (0, 1, 4),
    f"{STAGED_APPLICATION}: evnt_timer of a negative time, a delay pending": (0, 1, 4),
    f"{STAGED_APPLICATION}: a second process queues on the lock": (0, 3),
    f"{STAGED_APPLICATION}: wind_update(END), two processes waiting for the lock": (0,),
}
# @DECLARED-END
assert DECLARED.keys() == RUNS.keys()
SCENARIOS = {name: evasync.Scenario(RUNS[name], DECLARED[name]) for name in RUNS}


@derived.kept
def _run_of(name):
    """The ROM's run of the scenario `name`: a derivation, kept by content."""
    return SCENARIOS[name].run()


# Each scenario's run held to what it declares (`aes_event.Scenarios`): `scenario(name)` its arrivals, `case_id`,
# `arrival(name, nth)`, `at(name, routine, which)`.
_SCENARIOS = aes_event.Scenarios(DECLARED, _run_of)
scenario, case_id, arrival, at = _SCENARIOS.scenario, _SCENARIOS.case_id, _SCENARIOS.arrival, _SCENARIOS.at


def reaching_the_dispatcher(name):
    """The ordinals of the scenario's arrivals whose ROM call reaches the dispatcher — what SWITCHING declares, and
    a test holds it to (`test_aes_evwait.py`: asked per scenario there, not of every process that imports the rows)."""
    return tuple(nth for nth, made in enumerate(scenario(name)) if switches(made.name, made.arguments, made.machine))


def cases(*routines, switching=None):
    """`(scenario, nth)` for every declared arrival at one of `routines` (every routine, by default) — those that
    reach the dispatcher alone (`switching` True), or those that return (False)."""
    return [(name, nth) for name, nth in _SCENARIOS.cases(*routines)
            if switching is None or switching == (nth in SWITCHING.get(name, ()))]


# ---- THE RUN DOOR --------------------------------------------------------------------------------------------------------
WAITS_ON_A_PIPE = (READ, WRITE)
# The routines whose RETURNING run makes one whole wait — queued, found come, answered: the event bits steer it.
WHOLE_WAITS = (EV_BLOCK, AP_RDWR, EV_KEYBD, EV_BUTTON, EV_MOUSE, EV_MESAG, EV_TIMER)
# ...and those that store through no link and read no word they stored: the kit's whole attribution pass.
STORE_THROUGH_NO_LINK = (MWAIT, EV_RETS, EV_MCHK, EV_DCLICK, UNSYNC)


def _write_fits(arguments, machine):
    """Does the write iasync is handed (its QPB at `arguments[1]`) fit the pipe as `machine` holds it?"""
    image = make_image(machine)
    pid, count, _buffer = aes_pdpipe.QPB.unpack_from(image, arguments[1] & aes_event.OS_BUS_ADDR_MASK)
    return aes.PD_QUEUE_BYTES - case.word_in(image, aes_pdpipe.STATIC_PDS[pid] + aes.PD_QUEUE_INDEX) >= count


def _moves_a_message(name, arguments, machine):
    """Does the pipe's index steer the pass? A whole wait on a pipe: yes. iasync alone: only a WRITE that fits (doq
    reads the message's type back through the index it stores; a read's index is stored and not read again)."""
    if name == IASYNC:
        return arguments[0] == WRITE and _write_fits(arguments, machine)
    return name == EV_MESAG or (name in (AP_RDWR, EV_BLOCK) and arguments[0] in WAITS_ON_A_PIPE)


def steered_by(name, arguments, machine):
    """What steers the attribution pass in a RETURNING case of `name` — the reasons, the first met first — or None
    for a case that runs the kit's whole pass (measured over every arrival; `AES_STEERED_FOR_NOTHING` re-asks)."""
    if name in STORE_THROUGH_NO_LINK:
        return None
    if name == AMUTEX and (takes_the_lock(machine, arguments[1]) or lock(make_image(machine), arguments[1])[0] == -1):
        return None     # taken: no link read back. Refused at count -1: the count stored back, inverted, is a FREE lock's
    reasons = ((STEERS_THE_EVENT_BITS,) if name in WHOLE_WAITS else ()) + (STEERS_THE_LISTS,)
    return reasons + ((STEERS_THE_INDEX,) if _moves_a_message(name, arguments, machine) else ())


def lock(image, semaphore=WIND_SPB):
    """A semaphore as `(count, owner, the processes waiting, first first)`."""
    semaphore &= aes_event.OS_BUS_ADDR_MASK
    waiting = [case.long_in(image, evb + aes.EVB_PD) for evb in evasync.wait_list(image, semaphore + SPB_WAIT)]
    return aes.signed(case.word_in(image, semaphore + SPB_COUNT)), case.long_in(image, semaphore + SPB_OWNER), waiting


def takes_the_lock(machine, semaphore):
    """Would tak_flag(semaphore) over `machine` take it — free, or the running process's own?"""
    image = make_image(machine)
    count, owner, _waiting = lock(image, semaphore)
    return count == 0 or owner == evasync.running(image)


def unsync_answers(machine, semaphore=WIND_SPB):
    """Is unsync's D0 its own over `machine` — the last hold given up with nobody waiting (`aes/evwait.h`)?"""
    count, _owner, waiting = lock(make_image(machine), semaphore)
    return count == 1 and not waiting


def returning(name, arguments, machine, **kwargs):
    """The differential of a call that RETURNS, its C first in a fork (`aes_event.run_core_guarded`), the drops made
    where the ROM's run stores them (`DROPS`), steered as `steered_by` says unless the case says itself."""
    if name == UNSYNC:
        kwargs.setdefault("answer_compared", unsync_answers(machine, arguments[0]))
    if "steered" in kwargs:             # the case says itself — None: the kit's whole pass
        if kwargs["steered"] is None:
            del kwargs["steered"]
        return aes_event.run_core_guarded(name, arguments, machine, dropped_windows=DROPS, **kwargs)
    certain = steered_by(name, arguments, machine) or ()
    return aes_event.run_core_steered(name, arguments, machine, certain, dropped_windows=DROPS, **kwargs)


def how_it_switches(name):
    """unsync's hand-over leaves its caller READY: a yield. Every other road to the dispatcher is mwait's: a block."""
    return YIELDS if name == UNSYNC else BLOCKS


def qpb_drop_of(name, arguments, machine):
    """A blocked call's one drop (`qpb_address_drop`) where it parks a QPB (`parked_qpb`: ap_rdwr on a pipe,
    ev_mesag), whose wait takes the first free EVB of `machine`; none for any other call."""
    if parked_qpb(name, arguments, machine) is None:
        return ()
    return qpb_address_drop(evasync.free_evbs(make_image(machine))[0])


def held(name, arguments, machine, **kwargs):
    """THE CASE of `addrs.<name>` over `machine`, whichever way the ROM's call ends: a `Switched` for one that
    reaches the dispatcher (`switched` — a parked QPB's address dropped by name AND vetted, `vet_the_parked_qpb`), the
    differential's result for one that returns (`returning`)."""
    if not switches(name, arguments, machine):
        return returning(name, arguments, machine, **kwargs)
    dropped = qpb_drop_of(name, arguments, machine)
    result = switched(name, arguments, machine, how_it_switches(name), dropped)
    if dropped:
        vet_the_parked_qpb(name, arguments, machine, result)
    return result


def run(arrival, arguments=None, **kwargs):
    """...of `arrival`'s routine over its machine, with the frame its caller pushed or `arguments`."""
    return held(arrival.name, arrival.arguments if arguments is None else arguments, arrival.machine, **kwargs)


def image_after(result):
    """The machine a case left: where the C stopped at the dispatcher's hook, or the differential's final image."""
    return result.image if isinstance(result, Switched) else result.final


# ---- TWO PROCESSES' ap_rdwr FRAMES LIVE AT ONCE ------------------------------------------------------------------------
def parked_qpb_at(result, machine):
    """Where a call that parked over `machine` left its QPB, on the C's shore: its wait's parameter."""
    return evasync.evb_of(result.image, evasync.free_evbs(make_image(machine))[0])["PARM"]


@functools.cache
def reader_parked_in_its_own_frame():
    """`(machine, the reader's QPB address)`: the SCREEN MANAGER running while PD0 is parked in ITS OWN appl_read —
    the ROM's own run of it parks PD0 (`aes_event.parked`), the mouse onto the bar wakes the manager — with ONE
    pointer re-aimed, by nature: the parked wait's QPB is PD0's ap_rdwr's argument frame, a place on PD0's own stack
    (in its UDA, in the ROM's run); a C process's is where the C's own parked appl_read by PD0 leaves it — read off
    that run (`run`: the fork's image at the dispatcher's hook) — so the QPB's eight bytes are laid there and the
    wait's parameter aimed at them. What a host build must then hold: the manager's own ap_rdwr, whose QPB is live at
    the same time, does not land on it."""
    arrival = at("appl_read, none", AP_RDWR)
    parked = aes_event.parked(addrs.AES_ROM_AP_RDWR, frame_of(AP_RDWR, arrival.arguments), desk_running())
    machine = aes_event.woken_onto_the_menu_bar(parked)
    image = make_image(machine)
    waiting, = evasync.wait_list(image, SHELL + aes.PD_QUEUE_READERS)
    the_rom_s = evasync.evb_of(image, waiting)["PARM"]
    assert parked_qpb(AP_RDWR, arrival.arguments, arrival.machine) == aes_pdpipe.QPB.unpack_from(image, the_rom_s)
    ours = parked_qpb_at(run(arrival), arrival.machine)
    return merge_pokes(machine, {waiting + aes.EVB_PARM: struct.pack(">I", ours),
                                 ours: bytes(image[the_rom_s:the_rom_s + QPB_BYTES])}), ours


# ---- Tier 3's rows -----------------------------------------------------------------------------------------------------
def register(label, routine, arguments, machine, *, through_line_f=False):
    """One row of `routine` over an arrival's `machine` with its frame `arguments` (`aes_evasync.register_rows`) —
    priced direct, with what the one settling stages and drops (`aes_event.register_row`); verified through its call
    word. A call that reaches the dispatcher is no row of this kind (its run does not return without the
    dispatcher): `register_woken`."""
    if through_line_f:
        return aes.register(label, routine, arguments, machine, through_line_f=True)
    answered = routine != UNSYNC or unsync_answers(machine, arguments[0])
    return aes_event.register_row(label, routine, arguments, machine, answer_compared=answered)


# ---- THE WAITS, WOKEN: a blocked call taken on through the dispatcher to its return ---------------------------------------
# WHAT WAKES EACH SCENARIO'S WAIT, by ROM-run means alone (`aes_switching`: `{idle: interrupt}`, each the ROM's own
# interrupt code taken where the dispatcher idles): a key, a press, a move, ticks — and, for a wait on a pipe, ANOTHER
# PROCESS'S OWN WRITE: the snapshot's screen manager walked down its menu (THE MENU CHAIN — the mouse onto a title,
# onto an item, a press: ctlmgr's own appl_write of MN_SELECTED to the desk).
RETURN, PRESS, AWAY = evasync.RETURN, aes_event.press, evasync.AWAY
DOUBLE_CLICK = aes_event.double_click
RIGHT_PRESS = functools.partial(aes_event.taken_in_place, sequence=aes_event.RIGHT_PRESSING)
A_CLICK = functools.partial(aes_event.taken_in_place, sequence=aes_event.CLICKING)
ONTO_THE_BAR = evasync.ONTO_THE_BAR
A_MENU_TITLE, AN_ITEM_UNDER_IT = aes_event.THE_VIEW_TITLE_S_POINT, aes_event.VIEW_S_PLAIN_ITEM_S_POINT
A_POINT_ON_THE_DESKTOP = aes_event.A_POINT_ON_THE_DESKTOP
OFF_THE_BAR = aes_event.move_to(*A_POINT_ON_THE_DESKTOP)
A_FEW_PIXELS = 5                        # ...inside a rectangle's corner, clear of its edge
INTO_ELSEWHERE = aes_event.move_to(ELSEWHERE[0] + A_FEW_PIXELS, ELSEWHERE[1] + A_FEW_PIXELS)
INTO_THE_RECTANGLE_ROUND_THE_MOUSE = aes_event.move_to(ROUND_THE_MOUSE[0] + A_FEW_PIXELS, ROUND_THE_MOUSE[1] + A_FEW_PIXELS)
THE_MANAGER_S_RECTANGLE = "evnt_multi by the screen manager for a rectangle"
THE_MENU_CHAIN = aes_event.THE_MENU_CHAIN
ticks = aes_event.ticks
A_TIMER_TICKS = evasync.A_TIMER_TICKS
# What gives up the lock the screen manager's menu holds (`the_manager_s_menu_holds_the_lock`), at two idles: the
# mouse off the bar, then a click — ctlmgr leaves its menu and its own END_UPDATE hands the lock to whoever waits. (A
# press alone does not: ctlmgr then waits for the button to come up IN A LOOP OF YIELDS — the dispatcher never idles,
# and there is no idle to deliver the release at.)
THE_MENU_LET_GO = {0: OFF_THE_BAR, 1: A_CLICK}
# ...scenario by scenario. A DELAY BEHIND OTHERS OF THE SAME PROCESS is run out a delay at a time: the tick glue
# counts no tick while a run-out countdown waits for tchange to arm the next, so each delay's ticks are an idle's.
WAKES = {
    "evnt_keybd, none": {0: RETURN},
    "evnt_button for a press": {0: PRESS},
    "evnt_button for a double click": {0: DOUBLE_CLICK},
    "evnt_button for the right button down": {0: RIGHT_PRESS},
    "evnt_button for either button not up, which they are": {0: PRESS},
    "evnt_button with a state wider than a byte": {0: PRESS},
    "evnt_button with state bits outside its mask": {0: PRESS},
    "evnt_button with a mask wider than a byte": {0: PRESS},
    "evnt_mouse to leave the rectangle the mouse is in": {0: AWAY},
    "evnt_mouse to enter a rectangle the mouse is not in": {0: INTO_ELSEWHERE},
    "evnt_timer": {0: ticks(A_TIMER_TICKS)},
    "evnt_timer after a timer ran out": {0: ticks(A_TIMER_TICKS)},
    "evnt_timer of no time": {0: ticks(1)},
    "evnt_mesag, none": THE_MENU_CHAIN,
    "appl_read, none": THE_MENU_CHAIN,
    "wind_update(END), the screen manager waiting for the lock": {},
    "evnt_multi for every event": {0: RETURN},
    "evnt_multi for two rectangles, the mouse where neither asks": {0: AWAY},
    # ...the screen manager's own wait: woken by the mouse ENTERING its rectangle, whoever the mouse is (a move out
    # of it — what this table once tried — satisfies no wait to enter, and the scenario stood among NOT_WOKEN).
    THE_MANAGER_S_RECTANGLE: {0: INTO_THE_RECTANGLE_ROUND_THE_MOUSE},
    BEHIND_TWO_DELAYS: {0: ticks(10), 1: ticks(10), 2: ticks(30)},
    BETWEEN_TWO_DELAYS: {0: ticks(10), 1: ticks(5)},
    BEHIND_THREE_DELAYS: {0: ticks(10), 1: ticks(10), 2: ticks(20), 3: ticks(60)},
    TWO_WAITS_OF_ONE_PROCESS: {},
    THE_LOCK_THE_MENU_HOLDS: THE_MENU_LET_GO,
    f"{STAGED_APPLICATION}: evnt_timer shorter than the delay pending": {0: ticks(A_DELAY_MS // 2 // TICK_MS)},
    f"{STAGED_APPLICATION}: wind_update(END), two processes waiting for the lock": {},
}
# THE BLOCKED SCENARIOS NO RETURNING RUN WAKES, each with what would have to happen and cannot (held, each, by the
# ROM's own run: `test_aes_evlib_woken.py`) — `(how the ROM's run ends, what was tried, why nothing wakes it)`.
# "TRIED" IS ONE HAND-PICKED DELIVERY, AND A HAND-PICKED DELIVERY CAN BE THE WRONG ONE (the screen manager's rectangle
# stood here, "tried" with a move OUT of a rectangle it waits to ENTER). So the class is held by A SWEEP, not by the
# pick: EVERY_INTERRUPT below, each taken alone at the dispatcher's first idle, AND EVERY_CHAIN — what one interrupt
# alone cannot bring: several in turn at successive idles, one between two processes' turns — over every arrival
# of every scenario here (`swept`): none may return in the caller. Where the wait is another PROCESS's to
# satisfy (a pipe's other end, a lock's holder: `tried` is then nothing) the stated reason is A FACT OF THE MACHINE,
# read off it (`ONLY_ANOTHER_PROCESS`: who holds the lock and what THAT process waits for, who could read or write
# the pipe), the sweep says no interrupt does it instead, and the moves onto the bar give the snapshot's other
# process its turns.
# WHAT THE SWEEP DOES NOT SAY, AND SO SAYS APART (`swept`'s three other answers): a member under which the run ends IN
# ANOTHER PROCESS shows nothing of the waiter — and for the two scenarios whose lock is held by A HARNESS-PARKED
# PROCESS (`THE_HOLDER_IS_HARNESS_PARKED`) that is what a key does: it un-parks the holder, whose continuation is the
# sentinel. Those two are NOT "cannot be woken": their waiter's tail is NOT RUN on this machine — an UNPINNED tail,
# which the SAME CALL over a ROM-run holder runs instead (`THE_LOCK_THE_MENU_HOLDS`, among `WAKES`: the screen
# manager's menu holding the lock, given up by the mouse off the bar and a click — ev_block's and mwait's arrivals
# both taken on to their return). A chain NOT_TAKEN is no evidence at all.
NEVER = "the ROM's own run idles for ever"
ANOTHER_PROCESS_RETURNS = "the ROM's own run reaches its return in another process"
UNDER_THE_RECTANGLE_ABOVE_THE_SCREEN = aes_event.move_to(ABOVE_THE_SCREEN[0] + A_FEW_PIXELS, 0)
MORE_TICKS_THAN_ANY_TIME = 300          # every time a scenario waits for is shorter: 60 ticks at most (BEHIND_THREE_DELAYS)
# WHAT AN INTERRUPT CAN BRING A WAIT: a key, every kind of button event, the ticks, and the mouse INTO AND OUT OF every
# rectangle a scenario names (and to the screen's nearest point where a rectangle holds none).
EVERY_INTERRUPT = {
    "Return": RETURN, "a press": PRESS, "a click": A_CLICK, "a double click": DOUBLE_CLICK, "a right press": RIGHT_PRESS,
    "more ticks than any time": ticks(MORE_TICKS_THAN_ANY_TIME),
    "the mouse into the rectangle round where it was": INTO_THE_RECTANGLE_ROUND_THE_MOUSE,
    "the mouse into the other rectangle": INTO_ELSEWHERE,
    "the mouse out of both, into neither": aes_event.move_to(*A_POINT_ON_THE_DESKTOP),
    "the mouse onto the menu bar": ONTO_THE_BAR,
    "the mouse under the rectangle above the screen": UNDER_THE_RECTANGLE_ABOVE_THE_SCREEN,
    "the mouse onto the first row of the rectangle of negative height": aes_event.move_to(
        OF_NEGATIVE_HEIGHT[0] + A_FEW_PIXELS, OF_NEGATIVE_HEIGHT[1]),
}
RETURNS = "the ROM's own run returns to the caller"
NOT_WOKEN = {
    "evnt_mouse to enter a rectangle above the screen": (
        NEVER, {0: UNDER_THE_RECTANGLE_ABOVE_THE_SCREEN}, "no place of the mouse is above the screen's first line"),
    "evnt_mouse to enter a rectangle of negative height": (
        NEVER, {0: INTO_ELSEWHERE}, "a rectangle of negative height holds no point"),
    "evnt_timer of a negative time": (
        NEVER, {0: ticks(A_TIMER_TICKS)}, "a negative countdown is counted further down: no tick brings it to 0"),
    "appl_write to a full pipe": (
        NEVER, {}, "the desk waits to write into its own full pipe, which it alone reads"),
    "appl_read of the screen manager's pipe, empty": (
        NEVER, {}, "nobody writes to the screen manager's pipe: the desk would, and it is the reader"),
    "wind_update(BEG), the lock another's": (
        NEVER, {}, "the lock's holder is the desk, parked FOR A KEY by a HARNESS call: its release is no ROM run's — a "
                   "key un-parks the HOLDER, whose continuation is the run's sentinel, so the waiter's tail is NOT RUN "
                   "on this machine (UNPINNED here, not unwakeable: the same call over a ROM-RUN holder is "
                   "`THE_LOCK_THE_MENU_HOLDS`, woken to its return)"),
    "wind_update(BEG), the lock released once too often": (
        NEVER, {}, "a lock counted to -1 has no owner to give it up (the ROM finding of `test_aes_wm_update`)"),
    f"{STAGED_APPLICATION}: evnt_timer longer than the delay pending": (
        ANOTHER_PROCESS_RETURNS, {0: ticks(2 * A_DELAY_MS // TICK_MS)},
        "the application's delay runs out first and its stub's way out is the run's sentinel"),
    f"{STAGED_APPLICATION}: evnt_timer as long as the delay pending": (
        ANOTHER_PROCESS_RETURNS, {0: ticks(A_DELAY_MS // TICK_MS)}, "both delays run out in one tick; the application is entered first"),
    f"{STAGED_APPLICATION}: evnt_timer of a negative time, a delay pending": (
        NEVER, {0: ticks(A_TIMER_TICKS)}, "a negative delay goes BEFORE the pending one, which grows: neither runs out"),
    f"{STAGED_APPLICATION}: a second process queues on the lock": (
        NEVER, {}, "the application waits for a lock the desk holds, and the desk is parked for a key by a harness call: "
                   "a key ends the run in the desk (UNPINNED tail, as the lock another's)"),
}
assert not WAKES.keys() & NOT_WOKEN.keys() and WAKES.keys() | NOT_WOKEN.keys() == SWITCHING.keys()


@derived.kept
def _taken_alone(name, frame, machine, interrupt):
    """How the ROM's own run of `addrs.<name>` (its frame, over `machine`) ENDS with `interrupt` — a name of
    EVERY_INTERRUPT — taken at the dispatcher's first idle and nothing after: RETURNS, NEVER, or
    ANOTHER_PROCESS_RETURNS. A derivation, kept by content. Any other end is the driver's own refusal, raised."""
    try:
        the_rom_s = aes_switch.scheduled(getattr(addrs, name), frame, machine, {0: EVERY_INTERRUPT[interrupt]})
    except AssertionError as refused:
        ends = {"idles for ever AFTER its deliveries": NEVER, "its return in ANOTHER process": ANOTHER_PROCESS_RETURNS}
        how = [end for said, end in ends.items() if said in str(refused)]
        if not how:
            raise
        return how[0]
    assert the_rom_s.ended == aes_switch.RETURNED
    return RETURNS


def woken_alone_by(scenario, nth):
    """THE SWEEP'S FIRST HALF: the names of EVERY_INTERRUPT that, taken alone at the dispatcher's first idle, make the
    ROM's own run of the scenario's `nth` arrival — a call that blocks — RETURN IN ITS CALLER."""
    made = arrival(scenario, nth)
    frame = frame_of(made.name, made.arguments)
    return {interrupt for interrupt in EVERY_INTERRUPT if _taken_alone(made.name, frame, made.machine, interrupt) == RETURNS}


# ---- ...AND THE CHAINS: what no single interrupt at the first idle can bring ---------------------------------------------------
# One interrupt alone answers nothing for a wake that takes SEVERAL: the screen manager's own write (the mouse onto a
# title, onto an item, a press: three idles, three turns of it), a delay queued behind others of its process (run
# out a delay at a time, an idle each), a lock its holder gives up only once its menu is left AND clicked off, a key
# that arrives between two processes' turns. A CHAIN is what arrives at SUCCESSIVE IDLES, in order (`at_idles`) —
# the run takes as many of them as it idles before it ends: the chain's answer is that of its SHORTEST PREFIX that
# does not leave the machine idling — and what arrives at a POLL OF THE DISPATCHER THAT IS NO IDLE (`at_polls`:
# `aes_switch.scheduled`'s; a chain whose poll the run never makes, or makes as an idle, is not taken at all — the
# pair that takes the same two at idles 0 and 1 is a member too).
#   * THE MENU CHAIN — the one writer a returning run of this machine has (its click a press AND its release);
#   * TICKS AT SUCCESSIVE IDLES — more than any time, four times: the tick glue counts no tick while a run-out
#     countdown waits for tchange to arm the next, so each queued delay's ticks are an idle's;
#   * PAIRS AT IDLES 0 AND 1 — an event OF EACH KIND (`OF_EACH_KIND`: a key, a button, the ticks, the mouse into a
#     rectangle and out of every one) AFTER AN OPENER that changes whose the mouse, the keyboard and the screen
#     are: the mouse onto the menu bar (the other process's turn: its menu, the lock), and the mouse off it;
#   * AT THE POLL AFTER THE FIRST IDLE — a key, a click, the ticks, once the mouse onto the bar has woken the screen
#     manager and before it runs.
# A chain's interrupts are NAMES (`TAKEN_IN_A_CHAIN`: EVERY_INTERRUPT's, and the menu's two points), so what its first
# interrupt does alone is the first half's own answer, asked once.
# THE MENU CHAIN ENDS IN A CLICK, NOT A PRESS HELD (what `WAKES` delivers, where the desk is the one written to and
# returns at once): a press held on the item is, in every scenario whose caller is NOT that reader, waited out by
# ctlmgr in a loop of yields — SPINS, below: one fact of the ROM's ctlmgr, shown once (`test_aes_evlib_woken.py`),
# where each such run would spend a derivation's whole budget to say it again.
Chain = namedtuple("Chain", "at_idles at_polls", defaults=({},))
THE_POLL_AFTER_THE_FIRST_IDLE = 1       # poll 0 is idle 0 (the opener); forker runs its fork; idle polls again: this one
TICKS_AT_SUCCESSIVE_IDLES = 4           # one more than the delays any scenario queues before its own (BEHIND_THREE_DELAYS)
ONTO_THE_MENU_BAR, OFF_IT = "the mouse onto the menu bar", "the mouse out of both, into neither"
TAKEN_BETWEEN_TWO_TURNS = ("Return", "a click", "more ticks than any time")
OF_EACH_KIND = (*TAKEN_BETWEEN_TWO_TURNS, "the mouse into the rectangle round where it was", OFF_IT)
ONTO_THE_VIEW_TITLE, ONTO_ITS_PLAIN_ITEM = "the mouse onto the View title", "the mouse onto its plain item"
TAKEN_IN_A_CHAIN = {**EVERY_INTERRUPT, ONTO_THE_VIEW_TITLE: aes_event.ONTO_THE_VIEW_TITLE,
                    ONTO_ITS_PLAIN_ITEM: aes_event.ONTO_ITS_PLAIN_ITEM}
NOT_TAKEN = "the ROM's own run makes no such poll: the chain is not this machine's"
# ...and A THIRD WAY NOT TO BE WOKEN, which only a chain reaches: the button pressed and HELD on an item of the
# screen manager's dropped menu — ctlmgr waits for it to come up IN A LOOP OF YIELDS, the dispatcher never idles
# again (there is no idle to deliver the release at) and the caller never runs: a derivation's whole budget spent.
SPINS = "the ROM's own run neither returns nor idles again: its processes yield to one another for ever"
OUT_OF_BUDGET = "did not return to the sentinel within"
EVERY_CHAIN = {
    "the menu chain": Chain((ONTO_THE_VIEW_TITLE, ONTO_ITS_PLAIN_ITEM, "a click")),
    "more ticks than any time, at each of four successive idles": Chain(("more ticks than any time",) * TICKS_AT_SUCCESSIVE_IDLES),
    **{f"{opener}, then {interrupt} at the next idle": Chain((opener, interrupt))
       for opener in (ONTO_THE_MENU_BAR, OFF_IT) for interrupt in OF_EACH_KIND if interrupt != opener},
    **{f"{ONTO_THE_MENU_BAR}, then {interrupt} at the poll after it": Chain(
        (ONTO_THE_MENU_BAR,), {THE_POLL_AFTER_THE_FIRST_IDLE: interrupt}) for interrupt in TAKEN_BETWEEN_TWO_TURNS},
}
_ENDS = {"idles for ever AFTER its deliveries": NEVER, "its return in ANOTHER process": ANOTHER_PROCESS_RETURNS,
         "an idle's delivery is named at the idle": NOT_TAKEN, "polls: nothing was delivered at": NOT_TAKEN}


def ends_taken_through(name, frame, machine, at_idles, at_polls=None):
    """How the ROM's own run ENDS with `at_idles` (names of TAKEN_IN_A_CHAIN) taken at its first idles and `at_polls`
    (`{poll: name}`) at its polls that are no idle: RETURNS, NEVER, ANOTHER_PROCESS_RETURNS, NOT_TAKEN or SPINS. Any
    other end is the driver's own refusal, raised."""
    at_idle = {idle: TAKEN_IN_A_CHAIN[interrupt] for idle, interrupt in enumerate(at_idles)}
    at_polls = {poll: TAKEN_IN_A_CHAIN[interrupt] for poll, interrupt in (at_polls or {}).items()}
    try:
        the_rom_s = aes_switch.scheduled(getattr(addrs, name), frame, machine, at_idle, at_polls=at_polls)
    except AssertionError as refused:
        how = [end for said, end in _ENDS.items() if said in str(refused)]
        if not how:
            raise
        return how[0]
    except RuntimeError as spent:
        if OUT_OF_BUDGET not in str(spent):
            raise
        return SPINS
    return RETURNS if the_rom_s.ended == aes_switch.RETURNED else NEVER


@derived.kept
def _taken_in_turn(name, frame, machine, chain):
    """How the ROM's own run of `addrs.<name>` (its frame, over `machine`) ENDS taken through `chain` — a name of
    EVERY_CHAIN: the answer of the chain's shortest prefix that does not leave the machine idling (a run that has
    returned takes nothing more) — its first interrupt alone answered as the first half answers it. A derivation,
    kept by content."""
    made, how = EVERY_CHAIN[chain], NEVER
    for taken in range(1, len(made.at_idles) + 1):
        at_polls = made.at_polls if taken == len(made.at_idles) else {}
        if taken == 1 and not at_polls and made.at_idles[0] in EVERY_INTERRUPT:
            how = _taken_alone(name, frame, machine, made.at_idles[0])
        else:
            how = ends_taken_through(name, frame, machine, made.at_idles[:taken], at_polls)
        if how != NEVER:
            break
    return how


def woken_in_turn_by(scenario, nth):
    """...THE SECOND HALF: the names of EVERY_CHAIN that make that run return in its caller."""
    made = arrival(scenario, nth)
    frame = frame_of(made.name, made.arguments)
    return {chain for chain in EVERY_CHAIN if _taken_in_turn(made.name, frame, made.machine, chain) == RETURNS}


def swept(scenario, nth):
    """THE SWEEP, WHOLE, AND EVERY ANSWER OF IT: `{member: how the ROM's own run of the scenario's `nth` arrival ends
    taken through it}` — an interrupt alone, a chain; RETURNS (in its caller), NEVER, ANOTHER_PROCESS_RETURNS,
    NOT_TAKEN or SPINS. Only the first is a wake; ONLY THE SECOND IS EVIDENCE THAT THE MEMBER DOES NOT WAKE IT:
      * ANOTHER_PROCESS_RETURNS says the run ENDED before the caller could be seen woken or not — another process
        reached the run's sentinel (a harness-parked one's continuation, a staged application's way out) — so what
        that member would have done to the waiter is NOT KNOWN;
      * NOT_TAKEN says the chain was never delivered (the run makes no such poll): it says nothing at all.
    A battery that holds "nothing wakes it" pins which members answered which, never only that none returned."""
    made = arrival(scenario, nth)
    frame = frame_of(made.name, made.arguments)
    return {**{interrupt: _taken_alone(made.name, frame, made.machine, interrupt) for interrupt in EVERY_INTERRUPT},
            **{chain: _taken_in_turn(made.name, frame, made.machine, chain) for chain in EVERY_CHAIN}}


def what_wakes(scenario, nth):
    """Every member of the sweep — an interrupt alone, a chain — that makes the ROM's own run of the scenario's `nth`
    arrival RETURN IN ITS CALLER."""
    return {member for member, ended in swept(scenario, nth).items() if ended == RETURNS}


def the_sweep_wakes(scenario, nth):
    """Does SOME member of the sweep wake that arrival — the first found, an interrupt alone before a chain (None:
    none does)? What holds the sweep to finding every wake a registered row is known to make, at the cost of the
    members up to the first that does."""
    made = arrival(scenario, nth)
    frame = frame_of(made.name, made.arguments)
    alone = (interrupt for interrupt in EVERY_INTERRUPT if _taken_alone(made.name, frame, made.machine, interrupt) == RETURNS)
    in_turn = (chain for chain in EVERY_CHAIN if _taken_in_turn(made.name, frame, made.machine, chain) == RETURNS)
    return next(alone, None) or next(in_turn, None)


# ---- WHAT ONLY ANOTHER PROCESS COULD SATISFY: the stated reason, as a fact of the ROM-made machine --------------------------
# Five scenarios of NOT_WOKEN wait for nothing an interrupt brings (their `tried` is nothing): a pipe's other end, a
# lock's holder. WHY nothing wakes each is a statement about WHO — and is read off the machine the call is made
# over, at every arrival of the scenario (`held_by_no_process_that_could`), not left as a sentence.
def _parked(image, pd):
    """Is the process `pd` PARKED over `image`: on the not-ready list, neither running nor ready nor woken?"""
    return (pd in aes.list_of(image, aes.AES_NRL)
            and pd not in aes.list_of(image, aes.AES_RLR) + aes.list_of(image, aes.AES_DRL))


def _pipe(image, pid):
    """The pipe of the process `pid` as `(the bytes it holds, the processes waiting to read it, ...to write it)`."""
    pd = aes_pdpipe.STATIC_PDS[pid]
    waiting = [[case.long_in(image, evb + aes.EVB_PD) for evb in evasync.wait_list(image, pd + queue)]
               for queue in (aes.PD_QUEUE_READERS, aes.PD_QUEUE_WRITERS)]
    return case.word_in(image, pd + aes.PD_QUEUE_INDEX), *waiting


def _the_others(image):
    """Every process of the machine but the one making the call: the not-ready list's."""
    return [pd for pd in aes.list_of(image, aes.AES_NRL) if pd != evasync.running(image)]


def _its_own_full_pipe_nobody_else_reads(image):
    """THE DESK WRITES INTO ITS OWN FULL PIPE: the pipe is the caller's and holds all it can; no process waits to
    read it; and the machine's only other process is parked — a parked process reads nothing."""
    held, readers, _writers = _pipe(image, SHELL_PID)
    others = _the_others(image)
    return (evasync.running(image) == SHELL and held == aes.PD_QUEUE_BYTES and not readers
            and others == [SCREEN_MANAGER] and _parked(image, SCREEN_MANAGER))


def _an_empty_pipe_nobody_else_writes(image):
    """THE DESK READS THE SCREEN MANAGER'S EMPTY PIPE: it holds nothing; no process waits to write it; and the
    machine's only other process — the pipe's own — is parked: a parked process writes nothing."""
    held, _readers, writers = _pipe(image, SCREEN_MANAGER_PID)
    return (evasync.running(image) == SHELL and held == 0 and not writers
            and _the_others(image) == [SCREEN_MANAGER] and _parked(image, SCREEN_MANAGER))


def waits_for_a_key(image, pd):
    """Does the process `pd` WAIT FOR A KEY over `image`: an EVB of its own on its keyboard's wait list?"""
    keyboard = case.long_in(image, pd + aes.PD_CDA) + aes.CDA_KEYBOARD_WAIT
    return pd in [case.long_in(image, evb + aes.EVB_PD) for evb in evasync.wait_list(image, keyboard)]


def _a_lock_whose_holder_is_parked_for_a_key(holder):
    """THE LOCK IS ANOTHER PROCESS'S, AND THAT PROCESS IS PARKED WAITING FOR A KEY: held at least once by `holder`,
    who is not the caller, stands on the not-ready list — AND WHAT IT WAITS FOR IS READ TOO: a key. So this is NOT
    "nothing can wake the waiter": a key un-parks the HOLDER, whose continuation is a harness call's (the sentinel) —
    the run ends there, in another process (`swept`: ANOTHER_PROCESS_RETURNS), and the waiter's tail is NOT RUN. The
    fact says who holds the lock and why no ROM run of this machine gives it up; it does not say the wait cannot be
    woken (`NOT_WOKEN`'s entry: an UNPINNED tail on this machine; `THE_LOCK_THE_MENU_HOLDS` runs it)."""
    def fact(image):
        count, owner, _waiting = lock(image)
        return (count >= 1 and owner == holder != evasync.running(image) and _parked(image, holder)
                and waits_for_a_key(image, holder))
    return fact


def _a_lock_nobody_holds(image):
    """THE LOCK COUNTED TO -1 HAS NO OWNER: nobody to give it up."""
    count, owner, _waiting = lock(image)
    return (count, owner) == (-1, 0)


ONLY_ANOTHER_PROCESS = {
    "appl_write to a full pipe": _its_own_full_pipe_nobody_else_reads,
    "appl_read of the screen manager's pipe, empty": _an_empty_pipe_nobody_else_writes,
    "wind_update(BEG), the lock another's": _a_lock_whose_holder_is_parked_for_a_key(SHELL),
    "wind_update(BEG), the lock released once too often": _a_lock_nobody_holds,
    f"{STAGED_APPLICATION}: a second process queues on the lock": _a_lock_whose_holder_is_parked_for_a_key(SHELL),
}
# THE TWO WHOSE HOLDER IS A HARNESS-PARKED PROCESS: not "cannot be woken" — THE WAITER'S TAIL IS NOT RUN ON THIS MACHINE.
THE_HOLDER_IS_HARNESS_PARKED = ("wind_update(BEG), the lock another's", f"{STAGED_APPLICATION}: a second process queues on the lock")
assert ONLY_ANOTHER_PROCESS.keys() == {scenario for scenario, (_how, tried, _why) in NOT_WOKEN.items() if not tried}


def held_by_no_process_that_could(scenario, nth):
    """Is the scenario's stated reason TRUE OF THE MACHINE its `nth` arrival is made over (`ONLY_ANOTHER_PROCESS`)?"""
    return ONLY_ANOTHER_PROCESS[scenario](make_image(arrival(scenario, nth).machine))


def a_pipe_wait_s_qpb_is_no_part_of(arrival):
    """Is `arrival` mwait's own, entered UNDER a wait on a pipe whose QPB lay in its caller's frame (ap_rdwr's
    arguments, under appl_read and evnt_mesag)? The stack band is no part of a staged machine, so the queued wait
    names eight bytes of whatever the case's own frame leaves there: a writer would be served through them. (The
    same wait is woken, its QPB the ROM's own, in the arrivals above it: ap_rdwr's, ev_mesag's, ev_block's.)"""
    image = make_image(arrival.machine)
    return arrival.name == MWAIT and any(wait.qpb_at in case.STACK_BAND for wait in aes_event.parked_qpbs(image))


def woken_counterpart(scenario, nth):
    """THE WOKEN COUNTERPART of the scenario's `nth` arrival — a call that reaches the dispatcher — as a row that
    switches (`aes_switching.SwitchingRow`, registered nowhere): the same routine, frame and machine, taken on through
    the dispatcher by the scenario's wake. unsync answers nothing a caller reads on its hand-over."""
    made = arrival(scenario, nth)
    return aes_switching.SwitchingRow(f"{case_id((scenario, nth))}, woken", made.name, tuple(made.arguments),
                                      lambda: made.machine, WAKES[scenario], answered=made.name != UNSYNC)


# ---- THE MACHINES ONLY A RUN THROUGH THE DISPATCHER MAKES ---------------------------------------------------------------------
def after_the_wait(name, arguments, machine, at_idle):
    """`machine` (a running process's) AFTER ITS PROCESS'S OWN CALL of `addrs.<name>` blocked and was woken — the ROM's
    one run of it through the ROM's dispatcher, the interrupts `at_idle` taken at its idles: what every process of
    the machine did meanwhile is the ROM's own code (`aes_switching.left_by`: every byte that run stored)."""
    return aes_switching.left_by(name, arguments, machine, at_idle)


A_KEY_S_WAIT = (KEYBOARD, 0)
A_KEY_AFTER_THE_BAR = {0: ONTO_THE_BAR, 1: RETURN}


@functools.cache
def the_manager_s_menu_holds_the_lock():
    """PD0 running while THE SCREEN MANAGER HOLDS THE SCREEN'S LOCK: the desk waited for a key, the mouse went onto
    the menu bar — ctlmgr's own BEG_UPDATE takes the lock and it waits, its menu bar live — and Return woke the desk.
    (An application's evnt_keybd: the desk's saved context is then that call's, not an ev_block's own.)"""
    return _answers_stale(after_the_wait(EV_KEYBD, (), aes_event.machine(), A_KEY_AFTER_THE_BAR))


@functools.cache
def the_manager_queued_itself_on_the_lock():
    """PD0 running, the lock its own, THE SCREEN MANAGER QUEUED ON IT BY ITS OWN BEG_UPDATE — not a harness call's
    (`test_aes_wm_update.waited_on`): the desk took the lock and waited for a key, the mouse onto the bar woke ctlmgr,
    whose BEG_UPDATE tak_flag refused; Return woke the desk. Its continuation is the ROM's: it can be entered."""
    return _answers_stale(after_the_wait(EV_BLOCK, A_KEY_S_WAIT, wm_update.locked(), A_KEY_AFTER_THE_BAR))


@functools.cache
def the_manager_handed_the_lock():
    """...and after the desk's unsync: the lock THE SCREEN MANAGER'S, which is READY behind the desk — the next
    process the dispatcher enters."""
    return _answers_stale(after_the_wait(UNSYNC, (WIND_SPB,), the_manager_queued_itself_on_the_lock(), {}))


@functools.cache
def the_manager_writing_to_a_full_pipe():
    """THE SCREEN MANAGER running, the desk's pipe FULL of its own writes (`aes_pdpipe.the_desk_s_pipe_filled_by_the_
    manager`) and one more staged to write, with its QPB: the write that blocks until the desk has read."""
    full = aes_pdpipe.the_desk_s_pipe_filled_by_the_manager()
    blocked = aes_pdpipe.BLOCKED_WRITE
    return merge_pokes(full, {MESSAGE_AT: blocked}, aes_pdpipe.qpb_pokes(SHELL_PID, len(blocked), MESSAGE_AT))


THE_BLOCKED_WRITE = (WRITE, SHELL_PID, len(aes_pdpipe.BLOCKED_WRITE), MESSAGE_AT)


# evnt_mesag over an empty pipe, woken by the screen manager's own write (the menu chain): ap_rdwr's wait is queued
# with the address of its own arguments, served through it by ANOTHER process, and freed with the address still in
# the EVB. Registered nowhere: the row the registrar's own tests and the blob's QPB vet are made over
# (`test_aes_switching_registrar.py`, `test_aes_switching.py`).
A_MESSAGE_WAITED_FOR = aes_switching.SwitchingRow("a wait for a message; woken by the screen manager's own write",
                                                  EV_MESAG, (BUFFER_AT,), desk_running, THE_MENU_CHAIN)


# ---- Tier 3's rows THAT SWITCH ------------------------------------------------------------------------------------------------
def woken_at(label, scenario, routine):
    """A row that switches, to be: the scenario's arrival at `routine` — the ROM's own call, where it makes it —
    taken on through the dispatcher by the scenario's wake (`WAKES`)."""
    made = at(scenario, routine)
    return aes_switching.SwitchingRow(label, routine, tuple(made.arguments), lambda: made.machine, WAKES[scenario],
                                      answered=routine != UNSYNC)


def woken_over(label, routine, arguments, machine, at_idle):
    """...and one over a machine only a run through the dispatcher makes (above), `machine` its zero-argument maker."""
    return aes_switching.SwitchingRow(label, routine, tuple(arguments), machine, dict(at_idle), answered=routine != UNSYNC)


def register_woken(rows):
    """Each of `rows` (`woken_at` / `woken_over`) registered and priced (`aes_switching.register_row`): `{the row's
    name in the registry: the row}`."""
    return {aes_switching.row_name(row): row for row in map(aes_switching.register_row, rows)}
