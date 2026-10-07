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

ARGUMENT-CLASS MACHINES (`after_iasync`): the ROM's own iasync called MORE THAN ONCE for the running process over a
scheduler's machine — a wait queued and not waited for (iasync does not block: ev_block's mwait does). No ROM caller
leaves them — evnt_multi queues one wait of each kind — but every list, EVB and event bit in them is the ROM's own
work: two and three delays pending (the delta list's walk and its insert between two), two waits of one process on the
screen's lock, nine event bits held. Their scenarios say so in their names.
"""
import functools
import struct

from harness import addrs, emu, make_image

import abi
import aes
import aes_evasync as evasync
import aes_event
import aes_pdpipe
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
def settled(name, arguments, machine):
    """`(pokes, dropped)` of a PRICED row of `name` over `machine`: the words the ROM's run stores that differ by
    nature — spl7_save's SR save word, the Line-F mask word — each staged at the value the run leaves and dropped at
    Tier 3 by name, for the row's companion to compare with nothing dropped (`aes.undropped`)."""
    image = make_image(aes.staged(name, vdi.as_signed(name, arguments), machine))
    _final, writes, _regs = aes_event._rom_run(image, getattr(addrs, name))     # ONE run settles both words
    return aes_event.settled_where_stored(dict(machine), writes, aes_event.MASK_WORD_AND_SPL)


def register(label, routine, arguments, machine, *, through_line_f=False):
    """One row of `routine` over an arrival's `machine` with its frame `arguments` (`aes_evasync.register_rows`) —
    priced direct, verified through its call word. A call that reaches the dispatcher is Tier 1 only (a row's run
    returns)."""
    if through_line_f:
        return aes.register(label, routine, arguments, machine, through_line_f=True)
    pokes, dropped = settled(routine, arguments, machine)
    answered = routine != UNSYNC or unsync_answers(machine, arguments[0])
    return aes.ROWS.register(
        f"{aes.routines.core_symbol(routine)}, {label}", getattr(addrs, routine), aes.staged(routine, arguments, pokes),
        dropped=dropped, answered=answered,
        undropped=functools.partial(aes.undropped, routine, arguments, pokes, answer_compared=answered) if dropped
        else None)
