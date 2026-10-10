"""THE EVENT DOOR — how a battery runs an AES routine that reaches the event layer (`aes/evdoor.h`), and the MACHINES
such a routine is run over, each the state the ROM's own scheduler leaves.

THE DOOR. A C core calls the event layer (ev_multi, ap_rdwr, ...) through its wrapper in `aes/evdoor.h`, which calls
the entry's C twin — EVERY entry is REBOUND (`REBOUND`: derived from the library's markers, which the wrapper's own
spelling defines) — and off target first packs the routine's Alcyon frame and hands it to `recreate_call_event_door`:
an ARRIVAL. `event_hook` binds that hook per case: it notes the frame and lays the interrupt due at that call, answers
ARRIVED, and the twin runs over the candidate's image; its return is reported to a second hook
(`recreate_event_door_returned`). Keyed BY ROM ADDRESS (`address_hook.AddressHook`): an entry the case does not bind
is refused, and the core halts by name.

While a twin runs the door is CLOSED: a call of any entry through its wrapper from inside one is refused by name (a
twin calls another entry's core), and the return a wrapper reports must answer the innermost arrival in flight.
THE ANSWER IT REPORTS IS COMPARED with the ROM routine's own, door call by door call (`vet_the_answers_handed_back`:
D0 where the ROM's watched run comes back from the same call) — as what each call is HANDED is, below — AND SO IS
THE IMAGE IT RETURNS OVER, page by page (`image_pages`), and the image the candidate holds at EVERY DISPATCH of a
run that goes on through the host's model (`vet_the_images_at_the_dispatcher`).
NOTHING OF THE ROM IS RUN AT AN ARRIVAL. (Until band 4 wave 3's retirement every arrival also made the ROM routine's
NESTED RUN over a copy of the image — the twin's SHADOW, a flip's red proof, which held the twin at its own call to
that run. Every flip is made, every call that blocks is continued for real, and the shadow held nothing a twin's
leaf battery and the door case's own compare do not: it named a wrong twin EARLIER, at the call. Fifty wrong-twin
mutants were swept before and after it went: the same 49 killed, one equivalent; ONE of them the door users'
batteries killed only by the shadow's words (an answer its caller does not read) — which is what the answers
handed back hold now, and the images at each return and each dispatch what its image compare held, with no run of
the ROM. STATUS.md's wave log has the tables.)

THE EVENT LAYER'S OWN C — a twin, a wait, a list routine — is run by its LEAF battery, entered at the routine: its
returning arms in a fork first (`run_core_guarded`), its SWITCHING arms held to the ROM's own run at dsptch
(`switches_where_the_rom_does`, `rom_at_dsptch`). A watched run ENTERED AT a door entry makes no door call of it
(`DoorStops.entered_at`): the outermost entry reached inside is door call 0, on both shores.

A REBOUND TWIN IS HELD BY ITS LEAF BATTERY; THE DOOR CASES HOLD THE COMPOSITION. Measured at the pilot (22 real mutants
of `aes_tak_flag`, the door batteries of seven routines, 1,126 tests): with the shadow (above) off or on, the door
cases let through five twins that are NOT the ROM's routine — every mutant of the refusal with a real other owner, of the owner's
and the pointer's widths, of the wait list — because a door case reaches an entry only in the states its caller makes
(the lock free or the caller's own; the refusal arm once, with no owner). The shadow saw the same states: it changed
WHERE a red was named (at the twin's call, not at the session's end), never what was covered. The twin's own battery
(`test_aes_evsync.py`) kills all five alone. So every arm of a twin is its LEAF battery's to reach — its own rows,
entered at the entry itself (`test_tier3.py` holds that every twin has them, from the day it is linked) — and "the
door cases cover it" is no coverage argument for a twin. What the door cases hold is what no leaf battery can: that the
callers still arrive with the same frames, at the same ordinals, and take the same deliveries.

A TWIN CALLS ANOTHER ENTRY'S CORE, NEVER ITS WRAPPER (`aes/evdoor.h` says why): the hook counts every wrapper call
as an arrival, the watches count the outermost call only.

WHAT EACH CALL HANDS THE DOOR is compared too (`run_event`): the frame of every door call the C makes, its MOBLKs and
its message read through their pointers, against the frame the ROM's own run hands the same entry — read off that run
WATCHED at the entries (`DoorStops`, the kit's `rom_bench.watched`). The event layer often answers the same whatever a
frame says (a button that is up satisfies the rise before any rectangle is looked at), so the image alone cannot see a
rectangle or a flag the C got wrong.

WHERE A TWIN REACHES THE DISPATCHER (dsptch) the call would BLOCK — nothing it waits for is satisfied (its process
left WAITING), and on the machine the scheduler switches away until something is — or, its process still READY,
YIELD (switch away and be switched back). The dispatcher's hook REFUSES either, by its own name (the core then
halts, so a case meaning to show it runs the core in a child process, `refusal`) — unless the case switches the
host's model on (`aes_switch`). The dispatcher's guard the snapshot holds (`AES_INDISP`, a bare `rts` in dsptch)
is asked nothing: it would answer "no event", an outcome no machine has.

WHAT DIFFERS BY NATURE: the BIOS trap's register save. The event layer polls the keyboard through the VDI, whose BIOS
`trap #13` saves D3-D7/A3-A7 below `savptr` ($90c in the snapshot: `$8de..$905`, then the return PC and SR): A6 and A7
are the stack the trap was taken on — the caller's frame and depth — and the rest whatever the CALLER held in registers
no routine between changed (gr_watchbox's D4 reaches it through ev_multi untouched): a C caller's are not the ROM
caller's. `TRAP_SAVE_DROP` drops the ten
longwords by name, only where the ROM's run stores them — the PC and SR stay compared. A priced row (`register`) is the
same machine with `savptr` moved into the stack band (`gemdos.machine`'s arrangement): the save lands where nothing
compares it, so Tier 3 and the row's companion drop nothing but the Line-F mask word.

THE MACHINES: the state the ROM's own SCHEDULER leaves, never a poked list. The snapshot is inside the dispatcher's own
loop (`AES_ROM_DISP_LOOP`: forker, then idle until a process is ready) with nothing running and both processes parked
in their evnt_multi. So a running process is made the way the machine makes one: the event PD0 waits for is delivered
— a key in the keyboard's ring (`pd0_running`), the left button pressed (`button_down`), each by the interrupt's own
ROM code over the snapshot as it stands (`_interrupt_over`: rlr NULL, the dispatcher's guard set, as the machine takes
them) — and the dispatcher's loop run from where the snapshot waits, its forker posting the event, idle moving PD0 to
the ready list, switchto entering it; the run stops where PD0 comes out of its evnt_multi (`AES_ROM_EV_MULTI_RETURN`),
its waits cancelled by ev_multi's own tail. `machine()` then hides the cursor as the running process would (the ROM's
gsx_moff); `shown_machine()` leaves it as the snapshot shows it. Every other derivation runs the ROM's code over such a
machine and keeps only what the run wrote (`case.written_by`), named with the routine that made it — and none may reach
the dispatcher (`derived`).

INTERRUPTS AT A DOOR ENTRY (`interrupted`): the mouse moved or the button changed WHILE a routine waits — what one run
cannot reach — delivered as the machine takes them, at the entry of a routine's k-th door call, on both shores: the
ROM's own interrupt code run over the ROM's memory there, its writes laid into the ROM's run and into the C's image at
its k-th call alike — the C's image first checked to hold what the ROM's memory held where they land (`_laid_into`);
the C (in a child) then held to the ROM byte for byte. A case that BLOCKS is held the same way to the ROM's memory at
the entry of the call that blocks, or at dsptch where a rebound entry's twin stops (`interrupted` again, ending
blocked: `blocked_then_woken`'s first half, `_watched_through`). ONE run of the ROM's routine computes every
delivery (`deliveries`: set aside at each delivery's entry, continued there), so a long sequence — keys TYPED one per
wait (`key`, `typed`) — costs a run, not a run per key. A case priced at Tier 3 carries its deliveries in its row
(`register_interrupted`), and every run of its original lays them at the same calls (`delivering`, `replayed`).

A LONG SESSION (the file selector listing, scrolled, typed into; a dialog typed full) DECLARES ITS OWN DERIVATION
BUDGET (`budget=`: `_budget_of`, held both ways — the run fits it by the margin, and needed it) and is PRICED BY ITS
SLICES, a Tier 3 row each (`register_slices`, "A SESSION PRICED BY ITS SLICES" below): the run between two arrivals
both shores make at one PC, each shore marked there and ours held to the ROM's at both ends.
"""
import ast
import atexit
import collections
import contextlib
import copy
import ctypes
import dataclasses
import faulthandler
import functools
import hashlib
import importlib
import inspect
import itertools
import mmap
import operator
import os
import re
import signal
import struct
import subprocess
import sys
import traceback
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, _lib, addrs, arm_candidate, bench_tier3, emu, make_image
from recreate_kit import rom_bench
from recreate_kit.os_map import OS_BUS_ADDR_MASK

import abi
import aes
import aes_gsx
import case
import gemdos
import isr
import routines
import vdi
import vdi_entry
import vdi_helpers
import vdi_mouse
import zygote
from address_hook import REFUSED_ANSWER, STOPS_THE_SESSION, AddressHook, as_the_case_s_outcome, bind_pointer
from case import merge_pokes
from derived import Unreadable as NotReadableByValue
from derived import kept as kept_on_disk

# ---- the door's entries: what each is handed, its frame and the inputs it points at --------------------------------
# ev_multi(flags, mouse 1, mouse 2, timer, button, message, answers): the MOBLKs are read; the message buffer and the
# answers are written by the event layer, so only whether each is handed at all. ap_rdwr(code, process, length,
# buffer): a write's buffer is read, `length` bytes.
LONG_BYTES = aes.LONG_BYTES
EV_MULTI_FRAME = struct.Struct(">hIIIIII")
AP_RDWR_FRAME = struct.Struct(">hhhI")
MOBLK_BYTES = aes.EV_MOBLK_WORDS * aes.WORD_BYTES
WORD_MASK = aes.WORD_MASK
LONG_IN_A_FRAME = vdi.FRAME_FORMATS[vdi.LONG_ARG]      # `struct`'s letter for a longword argument of a frame
Handed = namedtuple("Handed", "routine arguments")


def _pointee(image, pointer, size):
    """The `size` bytes `pointer` reaches through the 24-bit bus, or None for a NULL pointer."""
    if not pointer:
        return None
    at = pointer & OS_BUS_ADDR_MASK
    return bytes(image[at:at + size])


def _ev_multi_inputs(image, flags, mouse1, mouse2, timer, button, message, answers):
    return (flags, _pointee(image, mouse1, MOBLK_BYTES), _pointee(image, mouse2, MOBLK_BYTES), timer, button,
            bool(message), bool(answers))


def _ap_rdwr_inputs(image, code, process, length, buffer):
    return (code, process, length, _pointee(image, buffer, length) if code == aes.AP_RDWR_WRITE else bool(buffer))


# The semaphore calls (tak_flag, unsync) are handed the semaphore, read whole; ev_block its code and parameter as they
# are (a semaphore's address for the mutex wait, a value for others); ct_chgown the new owner and the control
# rectangle, read.
SPB_BYTES = aes.header_constants("wmupdate.h")["SPB_BYTES"]
SEMAPHORE_FRAME = struct.Struct(">I")
EV_BLOCK_FRAME = struct.Struct(">hI")
CT_CHGOWN_FRAME = struct.Struct(">II")


def _semaphore_inputs(image, semaphore):
    return (_pointee(image, semaphore, SPB_BYTES),)


# ...but for a pipe's wait (ev_block's codes 1 and 2: aqueue's read and write), whose parameter is the ADDRESS OF A QPB
# its caller keeps on its own stack — ap_rdwr hands ev_block the address of its own arguments (`move.l a6,(sp) /
# addi.l #10,(sp)`, $fe65c8), a place in each shore's caller's frame, another by nature: what is handed is what the
# pointer NAMES, the QPB's three fields read through it (and a write's bytes through its buffer), as ev_multi's MOBLKs
# are read through theirs.
EVWAIT = aes.header_constants("evwait.h")
PIPE_WAITS = (EVWAIT["IASYNC_READ"], EVWAIT["IASYNC_WRITE"])
# THE ONE LAYOUT OF A QPB — the process, the count, the buffer (`aes/pdpipe.h`: QPB_*) — its two words SIGNED, as
# the ROM reads them: the process id is handed on as fpdnm's `int` ($fe5998 `move.w (a3),(sp)`) and the count is
# compared signed ($fe59b0 `cmp.w 2(a3),d0` / `bge`).
QPB = struct.Struct(">hhI")
assert QPB.size == aes.header_constants("pdpipe.h")["QPB_BYTES"]


def _qpb_inputs(image, code, qpb):
    """What a pipe's wait is handed through the QPB at `qpb`: its process and count, and — a write's — the bytes at
    its buffer; a read's buffer only as handed or not."""
    process, count, buffer = QPB.unpack(_pointee(image, qpb, QPB.size))
    return (process, count, _pointee(image, buffer, count) if code == EVWAIT["IASYNC_WRITE"] else bool(buffer))


def _ev_block_inputs(image, code, parameter):
    return (code, _qpb_inputs(image, code, parameter) if code in PIPE_WAITS and parameter else parameter)


def _ct_chgown_inputs(image, owner, rect):
    return (owner, _pointee(image, rect, aes.GRECT_BYTES))


# WHAT A CALL THAT BLOCKS ON A PIPE MUST BE FOUND TO HAVE PARKED (`Entry.parks`, over what the call was handed —
# `Handed.arguments` — and the image it blocked over): the QPB's process and count, or None for a call that queues no
# pipe wait. ap_rdwr's QPB is its own arguments; ev_block's the one its parameter names; ev_multi builds its own for
# a MESSAGE — the running process, one message's bytes ($fe6b40 `move.w 28(a0),-8(a6)`, $fe6b46 `move.w #16,-6(a6)`).
def _ap_rdwr_parks(_image, code, process, length, _buffer):
    return (process, length) if code in PIPE_WAITS else None


def _ev_block_parks(_image, code, parameter):
    return parameter[:2] if code in PIPE_WAITS and parameter else None


def _ev_multi_parks(image, flags, *_rest):
    if not flags & aes.EV_MU_MESAG:
        return None
    running = case.long_in(image, aes.AES_RLR) & OS_BUS_ADDR_MASK
    return aes.signed(case.word_in(image, running + aes.PD_PID)), MESSAGE_BYTES


def _parks_nothing(_image, *_arguments):
    return None


# post_button is handed a PD, the buttons' state and the clicks, each as it is.
POST_BUTTON_FRAME = struct.Struct(">Ihh")


def _post_button_inputs(image, process, button, clicks):
    return (process, button, clicks)


# ev_button is handed the clicks, the buttons' mask and the state it waits for, each as it is; its answer words are
# written, so only whether they are handed at all.
EV_BUTTON_FRAME = struct.Struct(">hhhI")


def _ev_button_inputs(image, clicks, mask, state, answers):
    return (clicks, mask, state, bool(answers))


# THE ENTRIES, ONE ROW EACH, and everything the door's protocol asks about an entry decided by its row: the ROM
# routines the door stands for — every C call of the event layer, keyed by its address (`aes/evdoor.h`'s wrappers) —
# each with its Alcyon FRAME and how its arguments are READ through it. The frame GCC's caller leaves a TWIN is read
# by the same row (`handed_at_a_twin`: a longword per field of the frame).
# ...WHAT IT ANSWERS — the word of D0 its callers read, or nothing: post_button leaves D0 its EVB walk's end (`move.l
# a3,d0` at $fe5346: its wrapper is `void` — a twin is not bent to return a leftover); unsync writes D0 on ONE of its
# three paths only, `move.l a4,d0` = 0 with nobody waiting ($fe4ece) — still holding the lock it leaves the D0 it was
# ENTERED with, its caller's, which no C caller holds: its word is compared with nothing, though its wrapper hands one
# on. The column decides what THE ANSWERS HANDED BACK compare (`vet_the_answers_handed_back`, below);
# `test_aes_event.py` holds each row's answer to its wrapper's own return type, that one named.
# ...and WHAT IT PARKS where it blocks on a pipe (`parks`, above): asked of the row, so no routine is named where a
# parked QPB is vetted.
ANSWERS_A_WORD, ANSWERS_NOTHING = aes.WORD_ANSWER, None
Entry = namedtuple("Entry", "frame inputs answers parks", defaults=(_parks_nothing,))
ENTRY_PREFIX = "AES_ROM_"
ENTRY_FRAMES = {"AES_ROM_EV_MULTI": Entry(EV_MULTI_FRAME, _ev_multi_inputs, ANSWERS_A_WORD, _ev_multi_parks),
                "AES_ROM_AP_RDWR": Entry(AP_RDWR_FRAME, _ap_rdwr_inputs, ANSWERS_A_WORD, _ap_rdwr_parks),
                "AES_ROM_TAK_FLAG": Entry(SEMAPHORE_FRAME, _semaphore_inputs, ANSWERS_A_WORD),
                "AES_ROM_UNSYNC": Entry(SEMAPHORE_FRAME, _semaphore_inputs, ANSWERS_NOTHING),
                "AES_ROM_EV_BLOCK": Entry(EV_BLOCK_FRAME, _ev_block_inputs, ANSWERS_A_WORD, _ev_block_parks),
                "AES_ROM_CT_CHGOWN": Entry(CT_CHGOWN_FRAME, _ct_chgown_inputs, ANSWERS_A_WORD),
                "AES_ROM_POST_BUTTON": Entry(POST_BUTTON_FRAME, _post_button_inputs, ANSWERS_NOTHING),
                "AES_ROM_EV_BUTTON": Entry(EV_BUTTON_FRAME, _ev_button_inputs, ANSWERS_A_WORD)}
ENTRY_NAMES = tuple(ENTRY_FRAMES)
ENTRIES = tuple(getattr(addrs, name) for name in ENTRY_NAMES)
_ENTRY_AT = {getattr(addrs, name): row for name, row in ENTRY_FRAMES.items()}
FRAME_BYTES = {entry: row.frame.size for entry, row in _ENTRY_AT.items()}
for _name, _row in ENTRY_FRAMES.items():   # each held to its wrapper's (`aes/evdoor.h`)
    assert _row.frame.size == getattr(aes, f"EVDOOR_{_name.removeprefix(ENTRY_PREFIX)}_FRAME_BYTES"), _name


def entry_frame(name, *arguments):
    """The Alcyon frame of a call of the entry `addrs.<name>` with `arguments`, as its ROM callers push it."""
    return ENTRY_FRAMES[name].frame.pack(*arguments)


def answers(routine):
    """Does the entry at `routine` answer — the word its callers read — or nothing?"""
    return _ENTRY_AT[routine].answers is not ANSWERS_NOTHING


def parked_by(call, image):
    """The `(process, count)` of the QPB the door `call` (a `Handed`), blocked on a pipe over `image`, must be found
    to have parked — None for a call that queues no pipe wait (its entry's row says: `Entry.parks`)."""
    return _ENTRY_AT[call.routine].parks(image, *call.arguments)


def handed(routine, frame, image):
    """What a call of `routine` with the Alcyon `frame` hands it over `image`: its words and longs, each pointer to an
    input read through, each pointer to an output only as handed or not (`Handed`)."""
    row = _ENTRY_AT[routine]
    return Handed(routine, row.inputs(image, *row.frame.unpack(frame)))


def handed_at(entry, sp, memory):
    """...the call a run stopped at `entry` makes, its frame where the call left it: above the return address at `sp`."""
    start = sp + LONG_BYTES
    return handed(entry, bytes(memory[start:start + FRAME_BYTES[entry]]), memory)


def handed_at_a_twin(entry, sp, memory):
    """...and the call a run stopped at the first instruction of `entry`'s C TWIN makes, read off the frame GCC's caller
    left at `sp`: the return address, the image pointer, then every argument in a longword of its own — a word in its
    low half. Answered as the ROM entry's Alcyon frame is (`handed`), so the two shores' calls compare."""
    layout = _ENTRY_AT[entry].frame
    at, values = sp + LONG_BYTES + LONG_BYTES, []
    for code in layout.format.lstrip(">"):
        slot = case.long_in(memory, at)
        values.append(slot if code == LONG_IN_A_FRAME else aes.signed(slot & WORD_MASK))
        at += LONG_BYTES
    return handed(entry, layout.pack(*values), memory)


# ---- REBOUND: the entries whose WRAPPER calls a C twin ---------------------------------------------------------------
# An entry is REBOUND once its wrapper is spelt through `EVDOOR_REBOUND` (`aes/evdoor.h`): the wrapper then calls the
# twin — the core its name spells (`routines.core_symbol`: `aes_tak_flag`) — and the library carries the entry's MARKER,
# defined by that very spelling (`src/aes/evdoor.c`). Derived from the build, never listed: the hook answers a rebound
# entry ARRIVED and refuses any other, so a hook and a wrapper that disagree halt by name (`test_aes_event.py`; Tier 3
# derives the same set from the blob — a twin linked, no `jsr` into its ROM routine left — and `test_tier3.py` holds
# the two equal). A twin that merely EXISTS — the library exports it, no wrapper spelt for it — is PENDING: a C core
# like any other, held by its own leaf battery and reached by the event layer's C.
MARKER_PREFIX = "evdoor_rebound_"


def marker_of(name):
    """The symbol a library carries for the rebound entry `addrs.<name>`."""
    return MARKER_PREFIX + name.removeprefix(ENTRY_PREFIX).lower()


def twins_in(lib):
    """The door's entries `lib` (a candidate) exports a C twin of — rebound, or pending."""
    return frozenset(getattr(addrs, name) for name in ENTRY_NAMES if hasattr(lib, routines.core_symbol(name)))


def _marked_entry(lib, marker):
    """The address `lib`'s `marker` holds: a `const uint32_t` of the library."""
    return ctypes.c_uint32.in_dll(lib, marker).value


def rebound_in(lib):
    """The door's entries whose wrapper calls its twin in `lib` (a candidate): the ones it carries the marker of, each
    marker held to its entry's address and to a twin the library does export."""
    marked = {name: _marked_entry(lib, marker_of(name)) for name in ENTRY_NAMES if hasattr(lib, marker_of(name))}
    for name, entry in marked.items():
        assert entry == getattr(addrs, name), f"{marker_of(name)} names {entry:#x}, which is not {name}"
        assert hasattr(lib, routines.core_symbol(name)), (
            f"{name} is spelt rebound and the library exports no {routines.core_symbol(name)}")
    return frozenset(marked.values())


REBOUND = rebound_in(_lib)
PENDING = twins_in(_lib) - REBOUND


# ---- THE LONGWORD A WAIT PARKED ON A PIPE DIFFERS IN BY NATURE ---------------------------------------------------------
# aqueue keeps a pipe wait's QPB BY ITS ADDRESS in the EVB it queues (`evb->parm = qpb`), and the routines that wait
# on a pipe keep that QPB IN THEIR OWN FRAME: ap_rdwr's is its own arguments from the process id on (`move.l a6,(sp) /
# addi.l #10,(sp)`, $fe65c8); ev_multi's, for a MESSAGE, three stores into its locals (`-8(a6)`: $fe6b40..$fe6b4c,
# its address handed on by `move.l a6,(sp) / subq.l #8,(sp)`, $fe6b52). A place in a stack — the ROM routine's frame
# on one shore, the C twin's own QPB (off target: its host slot, one per process) on the other. A wait that is served
# where it is queued leaves nothing of it; one that PARKS leaves that longword in the EVB, at dsptch.
#
# WHICH EVB, AND WHOSE QPB, IS READ OFF THE MACHINE — no routine is named: every EVB of the RUNNING process's event
# list that is queued on a pipe's wait list (any process's readers or writers) and whose parameter is an address IN
# THE STACK BAND. (Not "the newest EVB": ev_multi queues its timer's wait AFTER its message's, $fe6b88. And a QPB a
# case stages outside the stack band is one address on both shores: compared, never dropped.) The longword is dropped
# BY NAME and VETTED, never as a window: the same EVBs on both shores, each shore's longword an address in that
# shore's stack band, the eight bytes each names the SAME QPB. The waits' leaf battery holds its parked cases by the
# same rule (`switches_where_the_rom_does` asks it for every case); here it is also the door's: a door user's run
# that blocks inside a rebound entry (`interrupted`) — which is held, too, to the QPB its entry's row says the call
# parks (`parked_by`).
ParkedQpb = namedtuple("ParkedQpb", "evb qpb_at")
MOST_PIPE_WAITS = aes.AES_EVB_COUNT     # a list of EVBs is no longer than the EVBs there are: a walk past it has a cycle


def _evbs_linked_from(image, head_at, link):
    """The EVBs of the list whose head longword is at `head_at`, each linked to the next through its field `link`."""
    evbs, evb = [], case.long_in(image, head_at) & OS_BUS_ADDR_MASK
    while evb and len(evbs) <= MOST_PIPE_WAITS:
        evbs.append(evb)
        evb = case.long_in(image, evb + link) & OS_BUS_ADDR_MASK
    assert len(evbs) <= MOST_PIPE_WAITS, f"the list of EVBs at {head_at:#x} does not end"
    return evbs


def _waiting_on_a_pipe(image):
    """Every EVB queued on a pipe's wait list over `image`: each static process's readers and writers."""
    return frozenset(evb for process in range(aes.AES_PD_COUNT) for which in (aes.PD_QUEUE_READERS, aes.PD_QUEUE_WRITERS)
                     for evb in _evbs_linked_from(image, aes.AES_PD_TABLE + process * aes.PD_BYTES + which, aes.EVB_LINK))


def waiting_on_a_pipe(image):
    """`_waiting_on_a_pipe`, for a watch that reads a queued wait's QPB again (`aes_switching.Switching`)."""
    return _waiting_on_a_pipe(image)


def parked_qpbs(image):
    """The pipe waits the RUNNING process has parked over `image` with a QPB in a stack (above): a `ParkedQpb` each —
    the wait's EVB, the address its parameter holds — in the order of the process's event list."""
    running = case.long_in(image, aes.AES_RLR) & OS_BUS_ADDR_MASK
    if not running:
        return ()
    on_a_pipe = _waiting_on_a_pipe(image)
    return tuple(ParkedQpb(evb, case.long_in(image, evb + aes.EVB_PARM) & OS_BUS_ADDR_MASK)
                 for evb in _evbs_linked_from(image, running + aes.PD_EVLIST, aes.EVB_NEXT)
                 if evb in on_a_pipe and (case.long_in(image, evb + aes.EVB_PARM) & OS_BUS_ADDR_MASK) in case.STACK_BAND)


def _qpb_in_the_stack_band(who, read, at):
    assert at in case.STACK_BAND and at + QPB.size - 1 in case.STACK_BAND, (
        f"{who}: the parked wait's parameter {at:#x} is no place in the stack band — not a QPB's address parked")
    return QPB.unpack(read(at, QPB.size))


def _read_from(image):
    return lambda at, size: bytes(image[at:at + size])


Parked = namedtuple("Parked", "dropped qpbs")
# WHERE OUR C KEEPS A QPB IT PARKS, off target: NOT "any stack address that holds the right eight bytes" — THE SLOT
# of the routine that waits, the running process's frame of it (`host_slot.h`: a role per routine that parks one,
# HOST_PROCESSES frames each, the process's id choosing one). A twin that built its QPB in ANOTHER process's frame,
# or in another routine's role, holds the same eight bytes at another address — and the bytes alone would pass it
# (measured on two mutants of ev_multi's twin: the address differed, the QPB did not, and the vet held).
QPB_SLOT_OF_AN_ENTRY = {addrs.AES_ROM_EV_MULTI: "HOST_SLOT_AES_EV_MULTI_QPB", addrs.AES_ROM_AP_RDWR: "HOST_SLOT_AES_AP_RDWR_QPB"}


def host_qpb_slot(role, process):
    """Where `host_slot.h` puts the QPB of the process `process` (its id) under the role `role`."""
    slots = aes.HOST_SLOTS
    return slots[role] + process * (slots[f"{role}_BYTES"] // slots["HOST_PROCESSES"])


def our_qpb_slots(image, routine=None):
    """The addresses OUR C may park the RUNNING process's QPB at over `image`: its frame of the role of `routine`
    (an entry that parks one: `QPB_SLOT_OF_AN_ENTRY`) — of every such role, for a routine that is none of them (a
    routine entered above or below the one that waits: the waits' own leaf cases)."""
    running = case.long_in(image, aes.AES_RLR) & OS_BUS_ADDR_MASK
    process = case.word_in(image, running + aes.PD_PID)
    roles = [QPB_SLOT_OF_AN_ENTRY[routine]] if routine in QPB_SLOT_OF_AN_ENTRY else QPB_SLOT_OF_AN_ENTRY.values()
    return frozenset(host_qpb_slot(role, process) for role in roles)


def _vet_our_qpb_s_place(who, ours, at, routine=None):
    slots = our_qpb_slots(ours, routine)
    assert at in slots, (
        f"{who}: our wait's QPB is at {at:#x}, which is no QPB slot of the running process"
        + (f" under {routine:#x}'s role" if routine in QPB_SLOT_OF_AN_ENTRY else "")
        + f" ({', '.join(f'{slot:#x}' for slot in sorted(slots))}: `host_slot.h`) — the QPB was built in another "
        f"process's frame, or another routine's")


def parked_where_blocked(who, ours, the_rom_s, *, routine=None):
    """WHAT TWO SHORES OF A CALL BLOCKED ON A PIPE DIFFER IN BY NATURE (above), VETTED — refused by name otherwise:
    a `Parked` — the EVB_PARM longword of every wait the ROM's shore parked with a QPB in its stack (`dropped`), and
    those QPBs (`(process, count, buffer)` each). `ours` must have parked the SAME EVBs, each with a parameter naming
    the same QPB AT ITS OWN SLOT (`our_qpb_slots`; `routine`: the entry whose call blocked, where the caller knows
    it). The ROM's QPB is read out of `the_rom_s` itself: its run's own stack is in its memory."""
    its, mine = parked_qpbs(the_rom_s), parked_qpbs(ours)
    assert [each.evb for each in mine] == [each.evb for each in its], (
        f"{who}: the pipe waits parked with a QPB in a stack are the EVBs {[f'{each.evb:#x}' for each in mine]}, the "
        f"ROM's {[f'{each.evb:#x}' for each in its]}")
    dropped, qpbs = set(), []
    for the_rom, own in zip(its, mine):
        if own.qpb_at == the_rom.qpb_at:
            # ONE address on both shores: a wait the MACHINE came with (an earlier routine's, parked before the one
            # under test was entered — both shores were staged with it), no place of either run's own. Nothing
            # differs by nature, so nothing is dropped: the longword is compared like any other.
            # ITS QPB'S BYTES ARE NOT HELD EQUAL, and cannot be: the address is a place in the frame of the routine
            # that parked the wait, and A STAGED MACHINE CARRIES NO STACK BAND — the ROM's memory holds that frame
            # (or, by now, whatever lies where it was), our image holds nothing there (measured: the waits' own
            # battery's ev_mwait entered under a parked message wait — the ROM's eight bytes (254, 16608, 0), ours
            # zeros; three cases). What holds such a QPB is the case of the routine that PARKED it, compared there.
            continue
        rom_qpb = _qpb_in_the_stack_band(f"{who} (the ROM's run)", _read_from(the_rom_s), the_rom.qpb_at)
        our_qpb = _qpb_in_the_stack_band(who, _read_from(ours), own.qpb_at)
        assert our_qpb == rom_qpb, (
            f"{who}: the QPB the parked wait names ({our_qpb}) is not the ROM's ({rom_qpb}) — the wait's EVB {own.evb:#x}")
        _vet_our_qpb_s_place(who, ours, own.qpb_at, routine)
        dropped.update(range(own.evb + aes.EVB_PARM, own.evb + aes.EVB_PARM + LONG_BYTES))
        qpbs.append(rom_qpb)
    return Parked(frozenset(dropped), tuple(qpbs))


def parked_qpb_drop(who, ours, the_rom_s, *, routine=None):
    """...the bytes alone: what a compare of the two shores leaves out (`parked_where_blocked`)."""
    return parked_where_blocked(who, ours, the_rom_s, routine=routine).dropped


# ...AND AT A RETURN the same longword may be LEFT BEHIND: a wait that was queued and then cancelled or answered —
# ev_multi's message wait taken off by acancel, a woken ap_rdwr's by apret — gives its EVB back to the free list AS IT
# IS, the QPB's address still in its parameter (get_evb clears an EVB only when it is next taken). Found by the ROM
# run's LEDGER, which a returning case has: an EVB_PARM the run STORED that holds an address in the stack band. Vetted
# as the parked one is: on our shore too an address in the stack band, naming the same QPB.
EVBS = tuple(aes.AES_EVB_TABLE + index * aes.EVB_BYTES for index in range(aes.AES_EVB_COUNT))
QPB_ADDRESS_WHY = ("a QPB's address a pipe wait was queued with, left in its EVB: a place in the waiting routine's own "
                   "frame — the ROM routine's on one shore, the C's own on the other (off target its host slot)")


def qpb_addresses_kept(read, stored):
    """`{an EVB_PARM's address: the QPB it names}` for every EVB whose parameter is among the addresses `stored` (a
    ROM run's write ledger) and holds an address in the stack band — `read(at, size)` that run's memory, its own
    stack included."""
    kept = {}
    for evb in EVBS:
        at = evb + aes.EVB_PARM
        parm = int.from_bytes(read(at, LONG_BYTES), "big") & OS_BUS_ADDR_MASK
        if all(at + offset in stored for offset in range(LONG_BYTES)) and parm in case.STACK_BAND:
            kept[at] = _qpb_in_the_stack_band("the ROM's run", read, parm)
    return kept


def vetted_qpb_addresses(who, ours, kept, routine=None):
    """THE LONGWORDS `kept` (`qpb_addresses_kept` of the ROM's run) DIFFER IN BY NATURE, VETTED against `ours` (our
    shore's image, its stack band in it) — refused by name otherwise: each of ours the address of a QPB SLOT of the
    running process naming the SAME QPB — the slot of `routine`'s OWN role where the row's routine is an entry that
    parks one (`our_qpb_slots`: a twin that built its QPB in another entry's slot is refused, as the parked arm
    refuses it), any role's for a routine that is none (the wait freed is an inner routine's). The `(lo, hi, why)`
    windows to drop."""
    for at, rom_qpb in kept.items():
        ours_at = case.long_in(ours, at) & OS_BUS_ADDR_MASK
        our_qpb = _qpb_in_the_stack_band(who, _read_from(ours), ours_at)
        assert our_qpb == rom_qpb, (
            f"{who}: the QPB the parked wait names ({our_qpb}) is not the ROM's ({rom_qpb}) — left in the EVB at "
            f"{at - aes.EVB_PARM:#x}")
        _vet_our_qpb_s_place(who, ours, ours_at, routine)
    return tuple((at, at + LONG_BYTES, QPB_ADDRESS_WHY) for at in kept)


@kept_on_disk
def _qpb_addresses_a_return_leaves(name, arguments, machine):
    image = make_image(aes.staged(name, vdi.as_signed(name, arguments), machine))
    final, writes, regs = emu.run(image, getattr(addrs, name), stop_pc=addrs.AES_ROM_DSPTCH)
    return {} if regs["checkpoint"] else qpb_addresses_kept(_read_from(final), writes)


def qpb_addresses_a_return_leaves(name, arguments, machine):
    """The QPB addresses the ROM's RETURNING run of `addrs.<name>` over `machine` leaves in EVBs
    (`qpb_addresses_kept`; none for a run that reaches the dispatcher): a derivation, kept by content."""
    return _qpb_addresses_a_return_leaves(name, tuple(arguments), machine)


def uda_of(pd, image):
    """Where the UDA of the process at `pd` lies over `image` — its saved context, its supervisor stack above it."""
    return case.long_in(image, pd + aes.PD_UDA) & OS_BUS_ADDR_MASK


def _a_door_user_s_parked_qpb(name, calls, image, rom_memory):
    """...and where a door USER's run blocks (`_watched_through`: compared at dsptch): the ROM's QPB is a place in
    its own run's stack, read through its own longword — and it is the QPB the row of the LAST call's entry says
    that call parks (`parked_by`: its process and count; none, for a call that queues no pipe wait). Nothing, for a
    run that made no door call."""
    if not calls:
        return frozenset()
    parked = parked_where_blocked(name, image, rom_memory, routine=calls[-1].routine)
    expected = parked_by(calls[-1], rom_memory)
    found = [qpb[:2] for qpb in parked.qpbs]
    assert found == ([tuple(expected)] if expected is not None else []), (
        f"{name}: the call that blocked parked the QPBs {found} (process, bytes) — it was handed {calls[-1]}, which "
        f"parks {expected}")
    return parked.dropped


# The hook's answers (`aes/evdoor.h`): ARRIVED, nothing run — the entry's twin runs next; or refused (AddressHook's
# REFUSED_ANSWER).
ARRIVED = aes.EVDOOR_ARRIVED
assert REFUSED_ANSWER == aes.EVDOOR_REFUSED
HOOK_SYMBOL = "recreate_call_event_door"
PROTOTYPE = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32,
                             ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32)
EVENT_DOOR = AddressHook(HOOK_SYMBOL, PROTOTYPE)
# ...and the hook a rebound entry's twin's answer is handed to, once it has returned.
RETURNED_SYMBOL = "recreate_event_door_returned"
RETURNED_PROTOTYPE = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.c_uint32)
DOOR_RETURNS = AddressHook(RETURNED_SYMBOL, RETURNED_PROTOTYPE)
IMAGE_BYTES = len(BASE_IMAGE)


# How the door refuses a call at whose dsptch the machine would switch processes (`_at_the_dispatcher`'s words): the
# caller WAITING, or still READY (it made another process ready, which runs first). Its own words, not "would block"
# alone, which the core's halt line spells for either ("a call that would block ... or yield").
BLOCKS, YIELDS = "the call would block", "the call would yield"


def switch_at(image):
    """The kind of switch a run that reached dsptch over `image` makes, read off the process it runs for: still
    WAITING ($fe40d8), the call BLOCKS; READY, it YIELDS — disp puts the one back on the ready list ($fe4dc4) rather
    than the not-ready one."""
    running = case.long_in(image, aes.AES_RLR) & OS_BUS_ADDR_MASK
    return BLOCKS if case.word_in(image, running + aes.PD_STAT) == aes.PD_STAT_WAITING else YIELDS


def _at_the_dispatcher(who, final):
    """Why a run that reached dsptch (`who`: "... reached the dispatcher") is refused, by the kind of switch it would
    make over `final` (`switch_at`). Either way the machine switches processes, which one run cannot."""
    if switch_at(final) == BLOCKS:
        return (f"{who} (dsptch, {addrs.AES_ROM_DSPTCH:#x}) — the call "
                f"would block: nothing it waits for is satisfied, and the machine would switch away until something "
                f"is, which no host core follows (the case staged nothing the call waits for, and switched no model on)")
    return (f"{who} (dsptch, {addrs.AES_ROM_DSPTCH:#x}) with its "
            f"process still ready — the call would yield: the machine would run the other processes first, which no "
            f"host core follows")


# ---- THE DISPATCHER'S HOOK (`aes/switch.h`: `recreate_dispatch`) -------------------------------------------------------
# What a C twin that reaches dsptch calls. It REFUSES, always, by name — the call would block, or yield
# (`_at_the_dispatcher`, read off the image as the C left it at dsptch): a switch is what no host core follows, and
# the snapshot's guard (`AES_INDISP`, under which the ROM's dsptch is a bare `rts`) is asked nothing — no process runs
# with it set. The core then halts, so a case meaning to show the refusal runs in a child, whose stderr carries these
# words (`bind_in_a_child` binds the same refuser into the child's library).
DISPATCH_SYMBOL = "recreate_dispatch"
DISPATCH_PROTOTYPE = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint8))


def _refused_at_the_dispatcher(buf):
    print(_at_the_dispatcher("the dispatcher's hook: the C reached the dispatcher", ctypes.string_at(buf, IMAGE_BYTES)),
          file=sys.stderr, flush=True)
    return REFUSED_ANSWER


DISPATCH_REFUSER = DISPATCH_PROTOTYPE(_refused_at_the_dispatcher)
bind_pointer(DISPATCH_SYMBOL, DISPATCH_REFUSER)


# ---- an arrival, and its twin's return ---------------------------------------------------------------------------------
# The door calls the candidate made in the run in flight, in order: what each arrival was handed — in the hook's
# RECORDED pass alone, as `AddressHook.calls` is (an attribution pass would hand the frames again).
HANDED = []


def _in_the_recorded_pass(call):
    if EVENT_DOOR.in_recorded_pass:
        HANDED.append(call)


# THE ANSWERS HANDED BACK — the frames' other half. A door case compares what each call is HANDED with the ROM's own
# call; this compares what each call ANSWERS: the word a twin returns (its wrapper reports it to the return hook) with
# the ROM routine's D0 where the ROM's own watched run comes back from the same door call (`DoorStops.answers`). A
# caller that does not read an answer (mn_do does not ask which rectangle came; fm_button reads none of ev_button's)
# ends the same whatever the twin answered, so the image and the frames cannot see it — this does, AT THE CALL, and
# names it. NO RUN OF THE ROM IS MADE FOR IT: both sides are runs the case makes anyway. (It took the place of the
# answer half of the SHADOW, band 4 wave 3's retirement; the image half's is the third field, below.)
# `(entry, answer)` each, in the order the calls RETURN — which is the order they are made: a door call from inside a
# twin is refused, so none is open while another returns. A call that never returns (the one a run blocks in) has
# no answer on either shore.
# ...AND THE IMAGE EACH LEAVES WHERE IT RETURNS — a third field, `image_pages` (further down: "THE IMAGE AT A STOP"):
# the candidate's image at the return hook, the ROM's memory where its watched run comes back from the same call.
# What a twin stored and a later call undoes shows here and at no end.
# NOT TAKEN (NO_IMAGE_TAKEN) on the one road whose two shores are staged apart: a case run THROUGH ITS CALLER'S
# LINE-F WORD, whose candidate runs over the staged caller's stub where the ROM's watched run of the frames is the
# routine entered directly — the same case entered directly is its sibling, and takes them. BOTH SHORES OR NEITHER:
# NO_IMAGE_TAKEN in the third field is the one way to carry none, the road tells both shores the same
# (`begin_a_door_run`, `_vet_the_frames_handed`), and a call with an image on one shore only is refused.
NO_IMAGE_TAKEN = None
ANSWERED = []                          # ...of the candidate's run in flight, in the return hook's RECORDED pass
_LEFT_OUT_BESIDE = [()]                # ...and the windows its road leaves out of every page beside (`begin_a_door_run`)


def _answered_in_the_recorded_pass(routine, answer, buf):
    if DOOR_RETURNS.in_recorded_pass:
        beside = _LEFT_OUT_BESIDE[0]
        ANSWERED.append((routine, answer, NO_IMAGE_TAKEN if beside is NO_IMAGE_TAKEN else candidate_s_pages(buf, beside)))


def vet_the_answers_handed_back(name, ours, the_rom_s):
    """THE TWINS' ANSWERS ARE THE ROM ROUTINES' (above): `ours` and `the_rom_s`, `(entry, answer, pages)` of each
    door call that returned, in order — as many, at the same entries, and the WORD equal wherever the entry answers
    one (`answers`: post_button and unsync answer nothing a caller reads, and are not compared) — AND THE IMAGE EACH
    LEFT WHERE IT RETURNED, page for page: taken on BOTH shores or (NO_IMAGE_TAKEN) on NEITHER. Refused by name."""
    assert [each[0] for each in ours] == [each[0] for each in the_rom_s], (
        f"{name}: the door calls that returned are {[f'{each[0]:#x}' for each in ours]}, the ROM's own run's "
        f"{[f'{each[0]:#x}' for each in the_rom_s]}")
    for nth, ((entry, mine, my_pages), (_entry, its, its_pages)) in enumerate(zip(ours, the_rom_s)):
        assert not answers(entry) or mine & WORD_MASK == its & WORD_MASK, (
            f"{name}: door call {nth}, entry {entry:#x}: the twin answered {mine & WORD_MASK:#x} where the ROM's "
            f"routine answers {its & WORD_MASK:#x}")
        assert (my_pages is NO_IMAGE_TAKEN) == (its_pages is NO_IMAGE_TAKEN), (
            f"{name}: door call {nth}, entry {entry:#x}: the image where it returns was taken on one shore only (the "
            f"C's: {my_pages is not NO_IMAGE_TAKEN}; the ROM's: {its_pages is not NO_IMAGE_TAKEN}) — a road takes it on "
            f"both, or says NO_IMAGE_TAKEN to both")
        differ = () if my_pages is NO_IMAGE_TAKEN else pages_that_differ(my_pages, its_pages)
        assert not differ, (
            f"{name}: door call {nth}, entry {entry:#x}: the twin left another image than the ROM's routine where it "
            f"returns — in {', '.join(differ)}")


# THE LINE-F MASK WORD IS NEVER LAID INTO THE C'S IMAGE. It is the Line-F handler's own self-patched `movem` mask
# (`aes.LINE_F_MASK_WINDOW`): every NON-EMPTY masked Alcyon return of a ROM run rewrites it (an empty one, `f001`,
# skips the store: $fee8e2 `andi.w #$ffe` / $fee8e6 `beq`), and the C — no Line-F return of its own — never does.
# Where it ends differs BY NATURE: the ROM's caller makes its OWN non-empty masked return after the door call (mn_bar's,
# gr_rubwind's wm_update's: the word holds that mask), the C makes none. Tier 1 drops it where the ROM's run stores it
# and Tier 3 drops it with each row's undropped COMPANION (`aes.undropped`), which stages it at the value the ROM's
# run leaves: leaving the C's image as it found it — at a delivery too (`_laid_into`) — is what lets the companion
# still see a C that writes the word itself.
LINE_F_MASK_BYTES = frozenset(at for lo, hi, _why in aes.LINE_F_MASK_WINDOW for at in range(lo, hi))


# `running`: the arrivals of ONE BINDING's candidate run in flight whose twins have not returned yet — what each was
# handed (`Handed`), a list of the binding's own (`event_hook`, emptied each time a case opens it; `bind_in_a_child`),
# never the module's. EVERY arrival takes a place in it and gives it up when its twin's return is reported: the list
# is what says A TWIN IS RUNNING.
def _vet_no_twin_is_running(routine, running, nested_arrivals=None):
    """A DOOR CALL FROM INSIDE A TWIN IS REFUSED BY NAME. The hook counts every wrapper call as an arrival; the watched
    runs — the ROM's, and our blob's — count the OUTERMOST call only (`aes/evdoor.h`: A TWIN CALLS ANOTHER ENTRY'S
    CORE, NEVER ITS WRAPPER). The build holds that no twin refers to the door's hooks (`test_aes_event.py`, over the
    call graph); this holds it where it would happen, whatever road the call came by.

    HOW IT IS REFUSED is the binding's. In a CHILD the refusal is raised: the hook answers REFUSED, the core halts,
    and the child's stderr carries these words. IN PROCESS a halt is the worker's death — an abort inside pytest,
    every captured word lost with it (a serial run reports nothing at all) — so a binding in process hands
    `nested_arrivals`, its own list: the refusal is KEPT there, the call carried on as the door would serve it, and
    the case failed by these words when its pass closes (`event_hook`), whatever else it then failed by."""
    if not running:
        return
    refusal = AssertionError(
        f"the event door: {routine:#x} was called through its wrapper INSIDE the twin of {running[-1].routine:#x} — a "
        f"nested arrival, which no watched run counts: a twin calls another entry's core (`aes_<entry>`), never "
        f"`evdoor_<entry>`")
    if nested_arrivals is None:
        raise refusal
    nested_arrivals.append(refusal)


def _in_place(buf):
    """The candidate's image a hook is handed as `buf` (a C pointer, or the buffer itself), viewed as its bytes WHERE
    IT LIES: read or written in place, no sixteen megabytes copied for the few a hook looks at."""
    return (ctypes.c_uint8 * IMAGE_BYTES).from_address(ctypes.cast(buf, ctypes.c_void_p).value)


def _arrived(routine, noted, running, nested_arrivals=None):
    """The effect of an ARRIVAL at the rebound `routine`: what it was handed `noted` — read through the image in
    place — and its place taken in `running` until its twin's return is reported (`_returned`). Nothing is run, over
    the candidate's image or any other: its twin does that. Refused by name: an arrival while another twin runs
    (`_vet_no_twin_is_running`, `nested_arrivals` its)."""
    def arrive(buf, frame, frame_bytes):
        _vet_no_twin_is_running(routine, running, nested_arrivals)
        call = handed(routine, ctypes.string_at(frame, frame_bytes), _in_place(buf))
        noted(call)
        running.append(call)
        return ARRIVED
    return arrive


def _returned(routine, running, answered):
    """...and of its twin's return: the arrival's place given up, the word the twin answered and the image it
    returns over `answered(routine, answer, buf)` — and THE RETURN ANSWERS THE INNERMOST ARRIVAL IN FLIGHT, refused by name otherwise (a return reported
    with none in flight, or for another entry than the one whose twin runs: a wrapper and a hook that lost count of
    one another)."""
    def returned(buf, answer):
        assert running, f"the event door: the twin of {routine:#x} returned, and no arrival of this binding is in flight"
        arrival = running.pop()
        assert arrival.routine == routine, (
            f"the event door: the twin of {routine:#x} returned, and the innermost arrival in flight is "
            f"{arrival.routine:#x}'s")
        answered(routine, answer, buf)
    return returned


def _describe_unawaited_returns(refused):
    return (f"a twin's return was reported for {', '.join(f'{at:#x}' for at in refused)}, which this case binds as no "
            f"rebound entry")


def _describe_refusals(refused):
    return (f"the event door was called for {', '.join(f'{at:#x}' for at in refused)}, which this case does not serve "
            f"— it serves {', '.join(f'{at:#x}' for at in ENTRIES)}")


def event_hook(entries=ENTRIES):
    """The binding `aes.run_function`'s `hook` opens per case: each of `entries` the library marks REBOUND noted as
    an arrival, its twin's return awaited and its answer noted (`_arrived`, `_returned`: the two hooks, opened
    together); any other address refused."""
    running, nested_arrivals = [], []
    effects = {entry: _arrived(entry, _in_the_recorded_pass, running, nested_arrivals) for entry in entries if entry in REBOUND}
    returns = {entry: _returned(entry, running, _answered_in_the_recorded_pass) for entry in effects}
    both = aes.doors(functools.partial(EVENT_DOOR.staged, effects, _describe_refusals),
                     functools.partial(DOOR_RETURNS.staged, returns, _describe_unawaited_returns))

    @contextlib.contextmanager
    def opened():
        running.clear()                 # a run that ended inside a twin's call left its arrival behind: not this run's
        nested_arrivals.clear()
        try:
            with both() as passes:
                yield passes
        finally:
            # A NESTED ARRIVAL's refusal, kept while the run carried on (`_vet_no_twin_is_running`), then a RETURN's
            # that answered no arrival: each is the case's failure, whatever else the run then failed by — it names
            # the call the protocol went wrong at. WHATEVER THE EFFECT RAISED: a `pytest.fail` or a KeyError is no
            # AssertionError, and its words are the diagnosis all the same (`as_the_case_s_outcome`; what stops
            # the session has stopped it already).
            refused = nested_arrivals + [raised if isinstance(raised, AssertionError) else as_the_case_s_outcome(routine, raised)
                                         for routine, raised in DOOR_RETURNS.raised
                                         if not isinstance(raised, STOPS_THE_SESSION)]
            if refused:
                raise refused[0]
    return opened


# ---- WHAT THE EVENT LAYER'S OWN C CALLS OUT THROUGH: the VDI it polls with, the routines it is handed -------------------
# The event layer POLLS: chkkbd asks the VDI for the shift keys and a key (vq_key_s, vsin_mode, vsm_string), mchange
# for the mouse while a recording plays (vsm_locator) — functions the AES's graphics never reach
# (`aes_gsx.REACHED_FUNCTIONS`), served beside those. And it CALLS WHAT IT IS HANDED through the register-carrying hook:
# a FORK FUNCTION — the code of a queue entry, the ROM's address off target (`aes/evfork.h`), served by the candidate's
# own core over the entry's one longword, taken apart as the function's Alcyon frame — and the cursor routine drawrat
# calls: the ROM's bare `rts` (AES_ROM_JUSTRETF) in the snapshot, and while a recording plays THE VDI's OWN (`$fcff0a`
# default_user_cur, which ap_tplay saves in `$947a`), served by the candidate's VDI core over D0 and D1.
# ONE SPELLING, for the input's leaf battery, ev_multi's, and — once ev_multi is REBOUND, so that chkkbd and forker
# run in C under every door call — the door's own bindings, in process and in a child (`polls_in_c`).
# ...and ap_tplay's exchange of the cursor routine (vex_curv: a playback hands the VDI justretf at its first mouse
# record and puts the VDI's own back at its end; its vex_motv is `aes_gsx.REACHED_FUNCTIONS`').
POLLED_FUNCTIONS = ("VDI_ROM_VQ_KEY_S", "VDI_ROM_VSIN_MODE", "VDI_ROM_STRING", "VDI_ROM_LOCATOR", "VDI_ROM_VEX_CURV")
FORK_FUNCTIONS = {"AES_ROM_KCHANGE": (None, (vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.WORD_ARG)),
                  "AES_ROM_BCHANGE": (None, (vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.WORD_ARG)),
                  "AES_ROM_MCHANGE": (None, (vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.WORD_ARG)),
                  "AES_ROM_TCHANGE": (None, (vdi.IMAGE_ARG, vdi.LONG_ARG))}
for _name, (_restype, _argtypes) in FORK_FUNCTIONS.items():
    aes.declare_alcyon(_name, _restype, _argtypes)


@functools.cache
def vdi_functions():
    """`aes_gsx.vdi_functions()` with the input functions the event layer polls with."""
    table = dict(aes_gsx.vdi_functions())
    for name in POLLED_FUNCTIONS:
        aes_gsx.opcode_of(name)             # a name with no `_OPCODE` sibling is no VDI function: refused here
        table.update(vdi_entry.function(name))
    return table


def vdi_hook():
    """`aes_gsx.vdi_hook`, the polled functions served too."""
    return isr.staged_routines(vdi_functions())


def _fork_function_served_by(lib, name):
    signature = vdi.ALCYON[name]
    core = getattr(lib, routines.core_symbol(name))
    if lib is not _lib:                 # a child's own library: its function is handed the declared signature
        core.argtypes, core.restype = list(signature.argtypes), signature.restype
    frame = struct.Struct(">" + "".join(vdi.FRAME_FORMATS[argtype] for argtype in vdi.frame_argtypes(name)))
    assert frame.size == LONG_BYTES, f"{name}: a fork function's frame is its queue entry's one longword"

    def effect(buf, registers):
        core(buf, *frame.unpack(struct.pack(">I", registers[isr.REGISTER["a0"]])))
    return effect


def handed_routine_effects(lib=_lib):
    """`{address: effect(buf, registers)}` of the routines the event layer's C is handed BY VALUE and calls through
    the register-carrying hook (above), each served by `lib`'s own core."""
    def default_user_cur(buf, registers):
        lib.vdi_default_user_cur(buf, registers[isr.REGISTER["d0"]], registers[isr.REGISTER["d1"]])
    return {**{getattr(addrs, name): _fork_function_served_by(lib, name) for name in FORK_FUNCTIONS},
            addrs.AES_ROM_JUSTRETF: lambda buf, registers: None,
            addrs.VDI_ROM_DEFAULT_USER_CUR: default_user_cur}


@functools.cache
def handed_routines():
    """...as `aes.alcyon_object_hook`'s map, over the worker's library: `{address: (no stub, effect)}`."""
    return {address: (b"", effect) for address, effect in handed_routine_effects().items()}


def event_layer_hooks():
    """THE BINDING OF AN EVENT-LAYER CORE THAT POLLS AND RUNS THE FORK QUEUE (chkkbd, mchange, forker, drawrat —
    and ev_multi, which calls two of them before anything else): `aes.run_function`'s `hook`. A NAMED hook
    (`named_hook`): the zygote may open it for a fork."""
    return aes.doors(vdi_hook, aes.alcyon_object_hook(handed_routines()))()


EVENT_LAYER_HOOKS = event_layer_hooks   # ...declared a NAMED hook where `named_hook` is defined, further down


def polls_in_c(rebound=None):
    """Does the event layer's keyboard poll run IN C under a door call — ev_multi (the one entry that polls: chkkbd,
    then forker and whatever was queued) REBOUND in the library a binding serves (`rebound`: the worker's by
    default)? Then every door case's binding serves what that C calls out through (above), and drops the trap frame's
    PC and SR no host VDI parks (`TRAP_FRAME_DROP`)."""
    return addrs.AES_ROM_EV_MULTI in (REBOUND if rebound is None else rebound)


def door_hook(drawing, objects=None):
    """The binding a door user's case opens: the door alone, or with the VDI's cores (`aes_gsx.vdi_hook`) too for one
    that `drawing` — and with the routines a tree walker it reaches is handed (`objects`, `aes.alcyon_object_hook`'s
    `{address: (stub, effect)}`: ob_draw's just_draw, draw_change's newrect). WHERE THE POLL RUNS IN C (`polls_in_c`)
    every case binds the VDI — the polled functions with it — and the handed routines, whatever it draws."""
    polls = polls_in_c()
    hooks = ((vdi_hook if polls else aes_gsx.vdi_hook,) if drawing or polls else ()) + (event_hook(),)
    handed = door_objects(objects)
    hooks += (aes.alcyon_object_hook(handed),) if handed else ()
    return aes.doors(*hooks) if len(hooks) > 1 else hooks[0]


def door_objects(objects=None):
    """What a door user's register hook serves IN PROCESS (`aes.alcyon_object_hook`'s map): the case's own walked
    routines (`objects`) — and, where the poll runs in C, the routines the event layer is handed
    (`handed_routines`). The one spelling, for `door_hook` and for a battery that builds its binding itself (the file
    selector's real-GEMDOS sessions)."""
    return {**(handed_routines() if polls_in_c() else {}), **(objects or {})}


def door_vdi_functions():
    """...and the VDI functions such a binding serves: the AES's graphics', and the polled ones where the poll runs
    in C."""
    return vdi_functions() if polls_in_c() else aes_gsx.vdi_functions()


# THE SAME DOOR IN A CHILD PROCESS (`vdi_helpers.refusal_over`'s `bind`), where a refusal ends the run and the case reads
# its stderr: every hook a door user's core reaches bound for its one call with no pass to open — the event door, every
# entry an arrival and any other address refused; the VDI's cores a drawing routine calls through `recreate_call_vector`
# (`aes_gsx.vdi_functions`); and the register-carrying hook (`_child_walkers`) — into `lib`, the candidate the CHILD
# loaded and calls (which need not be the one its `harness` import would load: a pointer left NULL there is a crash,
# not a refusal). The frames the door was handed are printed with a refusal (`HANDED_LINE`), for the case to read back
# (`handed_in`).
_TEST_DIR = str(Path(__file__).resolve().parent)
_CHILD_TRAMPOLINES = []
HANDED_LINE = "the door was handed: "
ANSWERED_LINE = "the door's calls answered: "
# A CHILD THE C ITSELF ENDS (`recreate_not_reconstructed`: an `abort()`, no exit and no hook of this binding's) never
# reaches the place where it says those two lines. Such a road asks its child to SAY EACH DOOR CALL AS IT GOES — one
# line where a call arrives, one where it returns — by running SAY_EACH_DOOR_CALL first (`door_child`'s `before`).
EACH_HANDED_LINE = "a door call was handed: "
EACH_ANSWERED_LINE = "a door call answered: "
SAYS_EACH_DOOR_CALL = [False]
SAY_EACH_DOOR_CALL = "aes_event.SAYS_EACH_DOOR_CALL[0] = True; "
CHILD_VDI_REFUSED = 3                  # the child's exit status when a VDI call it was not staged for is refused
# ...when the register hook hands it a routine it does not serve: apart from `vdi_helpers.CHILD_ORPHANED`, its parent
# gone.
CHILD_OBJECT_REFUSED = 5
# ...when the C's image does not hold, at an address an interrupt's delivery writes, what the ROM's memory held there
# before it (`_laid_into`): the delta is then not the machine's for the C.
CHILD_DELIVERY_REFUSED = 6
# ...when a twin's return answers no arrival in flight (`_returned`): the hook it is reported to is `void`, so the
# child would otherwise carry on with the door's count of its calls lost.
CHILD_RETURN_REFUSED = 7


def child_binding(*, objects=False, entries=None, interrupts=None, before=""):
    """The `bind` source of a door user's child (`bind_in_a_child`'s arguments, as source): `objects` serves the walked
    routines, `entries` narrows the door's, `interrupts` delivers interrupts at door calls (`interrupted`), and `before`
    is source the child runs first (a case's own change to this module, e.g. a smaller cap)."""
    arguments = ["lib"]
    arguments += [f"entries={tuple(entries)!r}"] if entries is not None else []
    arguments += ["objects=True"] if objects else []
    arguments += [f"interrupts={interrupts!r}"] if interrupts is not None else []
    return (f"import sys; sys.path.insert(0, {_TEST_DIR!r}); import aes_event; {before}"
            f"aes_event.bind_in_a_child({', '.join(arguments)})")


CHILD_BINDING = child_binding()
# THE DOORS A ROUTINE'S CHILD NEEDS BESIDE THE EVENT DOOR's (a `trap #1`: the file selector's GEMDOS), as source its
# child runs before the event door is bound — `lib` the candidate it loaded, `buf` its image — declared once per
# routine by the module that owns its machines (`declare_child_doors`); `interrupted` binds them in every child of it.
CHILD_DOORS = {}


def declare_child_doors(name, source):
    """`addrs.<name>`'s core reaches a door beside the event door's: `source` binds it in the routine's children."""
    assert name not in CHILD_DOORS, f"{name}: its child's doors are declared twice"
    CHILD_DOORS[name] = source


def _child_vdi(buf, routine, argument):
    """The VDI's cores in a child: a routine no reached function is refused by name, and ENDS the child — the hook is
    `void`, so the core would otherwise carry on as if it had drawn. The polled functions are served where the poll
    runs in C (`_CHILD_POLLS`: set by the child's binding, off its own library)."""
    function = (vdi_functions() if _CHILD_POLLS else aes_gsx.vdi_functions()).get(routine)
    try:
        assert function, f"the candidate transferred control to {routine:#x}, which is no VDI function the AES reaches"
        function[1](buf, argument)
    except Exception as refused:       # a callback cannot raise into C: the child ends here, by name
        print(refused, file=sys.stderr, flush=True)
        os._exit(CHILD_VDI_REFUSED)


def _refused_by_the_register_hook(routine):
    """Why a child refuses `routine`, handed through the register hook: a walked routine it was bound without
    `objects`, or one of the routines an application or the OS hands by value, which no child serves."""
    walked = {getattr(addrs, name): name for name in aes.WALKED_ROUTINES}
    if routine in walked:
        return (f"the candidate handed a tree walk {walked[routine]} ({routine:#x}), which this child serves only when "
                f"bound with `objects`")
    return (f"the candidate called {routine:#x} through the register hook — no walked routine "
            f"({', '.join(aes.WALKED_ROUTINES)}) but a routine handed by value (a USERDEF's far_call, sh_find's routine, "
            f"the mouse interrupt's USER_BUT, the fill's SEEDABORT, a Line-A entry — or a fork function, a cursor "
            f"routine: served only where the event layer's poll runs in C, `polls_in_c`), which this child does not serve")


_CHILD_POLLS = []                       # a child whose library polls in C (`bind_in_a_child`): not empty


def _child_walkers(lib, objects, polls=False):
    """The register-carrying hook in a child, ALWAYS bound: with `objects`, every routine a tree walk is handed by
    value served by the CHILD's own core (`aes.walked_routine_effects`) — and, where the poll runs in C (`polls`), the
    routines the event layer is handed (`handed_routine_effects`); any other routine ENDS the child by name
    (`_refused_by_the_register_hook`). Left as the child's `isr` import binds it,
    the hook would refuse such a call SILENTLY (no pass is open, and the hook is `void`): the walk would draw nothing,
    and the case compare a screen the C never drew (measured: mn_do's drop-down, absent)."""
    effects = {**(handed_routine_effects(lib) if polls else {}), **(aes.walked_routine_effects(lib=lib) if objects else {})}

    def serve(buf, routine, registers):
        effect = effects.get(routine)
        if effect is None:
            print(_refused_by_the_register_hook(routine), file=sys.stderr, flush=True)
            os._exit(CHILD_OBJECT_REFUSED)
        effect(buf, registers)
    return isr.CALL_VECTOR_REGISTERS(serve)


DELIVERY_NOT_LAID = "the event door: laying an interrupt's delivery at the C's door call raised"


def _laid_into(buf, delivery):
    """An interrupt's `delivery` (`deliveries`: `(found, wrote)`) laid into the candidate's image `buf` (a C pointer,
    viewed as the image's bytes) at its door call. CHECKED FIRST: the delta is the ROM's interrupt code run over the
    ROM's memory, so it is the machine's for the C only where the C's image holds what the ROM's memory held — `found`,
    at every address the delivery writes (what neither shore compares aside, `_NOT_COMPARED`); laid over a C that
    diverged there, it would erase the divergence. A mismatch ENDS the child by name. The Line-F mask word is not laid
    (`LINE_F_MASK_BYTES`): the C's image keeps the word as it found it.

    WHATEVER ELSE THE CHECK OR THE LAYING RAISES ENDS THE CHILD TOO, BY NAME (FORK_RAISED: the harness's error, never
    the C's). This runs inside the door's callback, where nothing can be raised into C: ctypes would print the
    exception and carry on, the delivery NOT LAID (or half laid), the twin run over a machine no interrupt reached —
    and the case's later compare would red on bytes, far from the reason."""
    try:
        image = _in_place(buf)
        found, wrote = delivery
        _vet_found(image, found, "the C's door call")
        _lay(image, wrote, lays_the_mask_word=False)
    except AssertionError as refused:
        print(refused, file=sys.stderr, flush=True)
        os._exit(CHILD_DELIVERY_REFUSED)
    except Exception as raised:        # ...a delivery that could not be LAID is no delivery laid
        print(f"{DELIVERY_NOT_LAID}: {raised!r}", file=sys.stderr, flush=True)
        os._exit(FORK_RAISED)


def bind_in_a_child(lib, entries=ENTRIES, objects=False, interrupts=None, dispatching=None, left_out_beside=()):
    """`child_binding`'s call: the door — each entry `lib` marks rebound an arrival (`rebound_in`; any other refused),
    the twin's return and the dispatcher's hook with it — the VDI's cores and the walked routines bound into `lib`.
    `interrupts` (`deliveries`' `{ordinal: (found, wrote)}`) lays each interrupt's effect into the image at the door
    call of that ordinal, before its twin runs (`_laid_into`) — and the frames handed are printed at
    the child's exit too, so a call that RETURNS reports them; with a refusal at the dispatcher's hook as well, where
    a twin that blocks ends.

    A DOOR CHILD UNDER THE SCHEDULER'S MODEL (`dispatching`: `(buf) -> the dispatcher's answer` — `aes_switch`'s,
    the C scheduler run over the image): the twin that reaches the dispatcher's hook is RUN ON — the model
    dispatches, the call comes back and the door user's loop goes on, to its return. What the twin holds where it
    blocks, and what it does once woken, are held by the case: the same call ending blocked against the ROM's
    memory at dsptch (`blocked_then_woken`'s first half), and this run against the ROM's own through its
    dispatcher — its image at EVERY dispatch among the rest (`vet_the_images_at_the_dispatcher`: `dispatching` takes
    it). `left_out_beside`: the windows such a road leaves out of every page of an image taken at a stop
    (`image_pages`). THE CHILD ALWAYS SAYS WHAT ITS DOOR CALLS WERE HANDED AND ANSWERED where it ends — at its exit,
    or with a refusal at the dispatcher's hook — so whoever made it can hold them (`door_child`)."""
    calls, answers_back, running, rebound = [], [], [], rebound_in(lib)

    def handed(call):
        calls.append(call)
        if SAYS_EACH_DOOR_CALL[0]:
            print(f"{EACH_HANDED_LINE}{tuple(call)!r}", file=sys.stderr, flush=True)
    effects = {entry: _arrived(entry, handed, running) for entry in entries if entry in rebound}

    def answered(routine, answer, buf):
        answers_back.append((routine, answer, candidate_s_pages(buf, left_out_beside)))
        if SAYS_EACH_DOOR_CALL[0]:
            print(f"{EACH_ANSWERED_LINE}{answers_back[-1]!r}", file=sys.stderr, flush=True)
    returns = {entry: _returned(entry, running, answered) for entry in effects}

    def _the_child_s_own_python_raised(where, raised):
        """A callback cannot raise into C — ctypes prints what it raised and answers an undefined word, and the twin
        RUNS ON, to a child that exits 0. So what this child's own Python raises at the dispatcher ends it, by name."""
        print(f"the event door: {where} raised {raised!r}", file=sys.stderr, flush=True)
        print(_handed_line(calls, answers_back), file=sys.stderr, flush=True)
        os._exit(FORK_RAISED)

    def refused_at_the_dispatcher(buf):
        print(_handed_line(calls, answers_back), file=sys.stderr, flush=True)
        return _refused_at_the_dispatcher(buf)

    def dispatched(buf):
        try:
            return dispatching(buf)
        except Exception as raised:
            _the_child_s_own_python_raised("the dispatcher's hook under the model", raised)

    def returned(buf, routine, answer):
        try:
            returns[routine](buf, answer)
        except Exception as refused:   # a KeyError too: a return reported for no rebound entry of this child's
            print(refused if isinstance(refused, AssertionError) else
                  f"the event door: the return of {routine:#x} raised {refused!r}", file=sys.stderr, flush=True)
            print(_handed_line(calls, answers_back), file=sys.stderr, flush=True)
            os._exit(CHILD_RETURN_REFUSED)

    def dispatch(buf, routine, frame, frame_bytes):
        if routine not in effects:
            print(_describe_refusals([routine]), file=sys.stderr)
            return REFUSED_ANSWER
        if len(calls) in (interrupts or {}):
            _laid_into(buf, interrupts[len(calls)])
        try:
            return effects[routine](buf, frame, frame_bytes)
        except Exception as refused:   # a callback cannot raise into C (ctypes would answer an undefined word): refused
            # The core halts next: this is its reason, in the child's stderr — a refusal's own words (a nested
            # arrival's), or what an effect raised.
            print(refused if isinstance(refused, AssertionError) else
                  f"the event door: the arrival at {routine:#x} raised {refused!r}", file=sys.stderr)
            print(_handed_line(calls, answers_back), file=sys.stderr)
            return REFUSED_ANSWER
    polls = polls_in_c(rebound)
    _CHILD_POLLS[:] = [polls] if polls else []
    door, vdi_cores, walkers = PROTOTYPE(dispatch), isr.CALL_VECTOR(_child_vdi), _child_walkers(lib, objects, polls)
    twins_return = RETURNED_PROTOTYPE(returned)
    dispatcher = DISPATCH_PROTOTYPE(dispatched if dispatching else refused_at_the_dispatcher)
    _CHILD_TRAMPOLINES.extend((door, vdi_cores, walkers, twins_return, dispatcher))
    bind_pointer(HOOK_SYMBOL, door, lib)
    bind_pointer(RETURNED_SYMBOL, twins_return, lib)
    bind_pointer(DISPATCH_SYMBOL, dispatcher, lib)
    bind_pointer(isr.CALL_VECTOR_SYMBOL, vdi_cores, lib)
    bind_pointer(isr.REGISTERS_HOOK_SYMBOL, walkers, lib)
    atexit.register(lambda: print(_handed_line(calls, answers_back), file=sys.stderr))     # (a refusal aborts: a return's)


def _handed_line(calls, answers_back):
    """What a child says of its door calls, two lines: what each was handed, and what each that returned answered."""
    return f"{HANDED_LINE}{[tuple(call) for call in calls]!r}\n{ANSWERED_LINE}{answers_back!r}"


def every_said_in(stderr, line_said):
    """WHAT A CHILD SAID on each line of `stderr` that begins `line_said`, in order: the Python value it printed
    there (`repr`)."""
    return [ast.literal_eval(line.removeprefix(line_said)) for line in stderr.splitlines() if line.startswith(line_said)]


def said_in(stderr, line_said, otherwise=None):
    """...and on the FIRST such line — `otherwise` for a child that printed none (one that ended before it could say)."""
    said = every_said_in(stderr, line_said)
    return said[0] if said else otherwise


def handed_in(stderr):
    """The door calls a child was handed, as it printed them where it ended (`HANDED_LINE`) — or, for one the C
    itself ended, call by call as it went (EACH_HANDED_LINE): `Handed` each, in order."""
    said = said_in(stderr, HANDED_LINE)
    return [Handed(*call) for call in (every_said_in(stderr, EACH_HANDED_LINE) if said is None else said)]


def answered_in(stderr):
    """The answers a child's door calls handed back, as it printed them (`ANSWERED_LINE`, or EACH_ANSWERED_LINE as
    it went): `(entry, answer, pages)` each, in order — none for a child that printed no such line (one that ended
    before its door was bound)."""
    said = said_in(stderr, ANSWERED_LINE)
    return [tuple(each) for each in (every_said_in(stderr, EACH_ANSWERED_LINE) if said is None else said)]


def refusal(name, pokes, values, *, bind=CHILD_BINDING, io_seed=None, seconds=vdi_helpers.CHILD_SECONDS, answered=False,
            read_back=True):
    """What `addrs.<name>`'s core says over `pokes` with the frame `values`, in a CHILD process with the door bound
    (`vdi_helpers.refusal_over`; `bind=None` for a core that reaches no hook): `(returncode, stderr, image)`. The
    values typed as the routine's declared signature — THE ONE PLACE a frame's values become a fresh interpreter's C
    arguments (a fork's are `core_in_a_fork`'s, by the same declared signature); a child still running after `seconds`
    raises `subprocess.TimeoutExpired` (a core that loops where the ROM ends).
    `answered`: a core that returns prints its answer, at its declared width (`vdi_helpers.answer_in`). `read_back`
    False: the image is not read back (None), for a caller that reads no byte of it."""
    signature = vdi.ALCYON[name]
    arguments = [(f"ctypes.{argtype.__name__}", str(value))
                 for argtype, value in zip(signature.argtypes[1:], values, strict=True)]
    restype = f"ctypes.{signature.restype.__name__}" if answered and signature.restype else None
    return vdi_helpers.refusal_over(routines.core_symbol(name), pokes, io_seed, arguments=arguments, bind=bind,
                                    seconds=seconds, restype=restype, read_back=read_back)


# THE C RUNS FIRST IN A CHILD — the guard a battery of the event layer runs its C behind wherever that C may not come
# back. A DOOR USER's core that loops where the ROM's run ends (each ev_multi it makes answered at once, the loop never
# left), a LIST routine's that walks a list which no longer ends or stores through a link that is no address (the
# host's refusal: an abort), a twin whose wrapper and hook disagree (a halt): in process each is a worker spinning
# until the watchdog ends it, or dead — a crash, no failure. In a child it is a timeout or a non-zero exit, and the
# case FAILS by it (`_vet_returned`: one assertion, whichever child).
#
# TWO KINDS OF CHILD, and which one a core takes is not its battery's word:
#   * A DOOR USER's is a FRESH INTERPRETER (`returns_in_a_child`, `run_guarded`): its hooks are bound per child, and it
#     is given CHILD_RETURN_SECONDS, far above the measured 2-4 s. Run ONCE, before the differential, over the case's
#     machine — the door's cases run no attribution pass (`POISON_STEERS_THE_EVENT_LAYER`).
#   * A core that reaches NO hook (a list routine, a PD's, tak_flag) runs in a FORK of the worker AT THE CALL ITSELF
#     (`run_core_guarded`, through `aes.run_function`'s `first`): every run of the C the kit makes — the plain pass's
#     and the attribution pass's, over the very image and library state it hands that run — is made in a fork first.
#     So the poisoned run, where an inverted link or count is likeliest to send a core astray, is guarded as the plain
#     one is, and the fork's verdict cannot depend on the test before it: it is the same call, a moment early.
# EVERY HOOK IS REFUSED IN A FORK, by name (`FORK_UNSERVED_HOOKS`: each bound to a refuser that names it and ends the
# fork with FORK_REACHED_A_HOOK) — so a core that reaches one is never guarded vacuously (a `void` hook left as the
# worker's import bound it would refuse silently, and the fork return): its case fails, told to take the other road.
# The dispatcher's hook alone is left as the worker holds it — bound at this module's import, for every run in process
# and so for every fork: it refuses by name, a block told from a yield.
#
# WHAT A FORK MAY DO: call the C and `_exit` — no test code, no import, nothing of pytest's (a fork of a process that
# may hold threads). Its descriptor 2 AND its `sys.stderr` are the guard's pipe, so the C's refusal and whatever a
# Python hook prints both reach the failure's message under any capture; a fork whose own Python raises says so, with
# its traceback, under an exit status of its own (FORK_RAISED: a harness error, never booked to the C). AN ORPHAN
# CANNOT OUTLIVE ITS ALARM: `signal.alarm` is the fork's first act, so one whose worker died is gone within
# CORE_RETURN_SECONDS (recreate/README.md gives the check that sees one meanwhile: its command line is the worker's).
CHILD_RETURN_SECONDS = 30
CORE_RETURN_SECONDS = 10               # a forked core's alarm: a thousand times a call's cost — a spin, not a slow machine
STDERR_FD = 2                          # where the C's refusal writes: the descriptor, whatever `sys.stderr` is under pytest
FORK_RAISED = 8                        # a fork's exit status when its own Python raised: the harness's error
FORK_REACHED_A_HOOK = 9                # ...and when the core reached a hook no fork serves
_CHILD_STATUSES = (CHILD_VDI_REFUSED, vdi_helpers.CHILD_ORPHANED, CHILD_OBJECT_REFUSED, CHILD_DELIVERY_REFUSED,
                   CHILD_RETURN_REFUSED, FORK_RAISED, FORK_REACHED_A_HOOK)
assert len(set(_CHILD_STATUSES)) == len(_CHILD_STATUSES), "two kinds of child's end share an exit status"
# Every hook the candidate has but the dispatcher's — the event door's two, the two the VDI's cores and the walked
# routines leave through, and the other components' (GEMDOS's handler and clock, Supexec's routine, the disk driver's
# vectors), each by its pointer's name in the library: `test_aes_event.py` holds the list to the library's own exports.
# ...and THE SCHEDULER MODEL's three (`aes/evdisp.h`: the poll hook, asked at every poll of idle; the idle hook, where
# the n-th idle's interrupt is laid; and the process hook, a foreign process as a nested ROM run), in a library that
# links it.
SCHEDULER_HOOKS = tuple(symbol for symbol in ("recreate_poll", "recreate_idle", "recreate_process") if hasattr(_lib, symbol))
FORK_UNSERVED_HOOKS = (HOOK_SYMBOL, RETURNED_SYMBOL, isr.CALL_VECTOR_SYMBOL, isr.REGISTERS_HOOK_SYMBOL,
                       "recreate_call_gemdos_handler", "recreate_publish_clock", "recreate_call_routine",
                       "recreate_call_disk_vector", *SCHEDULER_HOOKS)
_HOOK_REFUSER = ctypes.CFUNCTYPE(None)  # whatever a hook's own arguments: its refuser reads none, and never returns


def _refused_in_a_fork(symbol):
    def refuse():
        os.write(STDERR_FD, f"the fork: the core reached the hook {symbol}, which no fork serves".encode())
        os._exit(FORK_REACHED_A_HOOK)
    return _HOOK_REFUSER(refuse)


_FORK_REFUSERS = {symbol: _refused_in_a_fork(symbol) for symbol in FORK_UNSERVED_HOOKS}


def _the_fork_s_whole_life(call, said_on, seconds, serves=()):
    """What a fork does, and all it does: its alarm set, its two stderrs the pipe `said_on`, every hook refused — but
    the ones it `serves`, left as the worker held them — then `call()` — and `_exit`, whatever happened."""
    status = FORK_RAISED
    try:
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        # FIRST: it bounds all that follows, and an orphan's life. (The interval timer, not `alarm`: seconds may be a
        # fraction — `alarm` takes whole ones and raised on 2.5 HERE, before the fork's stderr was its pipe: a fork
        # that "raised" for no reason anybody could read.)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        os.dup2(said_on, STDERR_FD)
        # (A worker's stdout is xdist's own channel. LINE-BUFFERED, as an interpreter's own stderr is: what a hook
        # prints before the C halts — a refusal's words, with no flush of its own — must be out before the abort.)
        sys.stdout = sys.stderr = open(STDERR_FD, "w", buffering=1, closefd=False)
        faulthandler.disable()                      # the worker's dump on SIGABRT would bury the refusal's own words
        for symbol, refuser in _FORK_REFUSERS.items():
            if symbol not in serves:
                bind_pointer(symbol, refuser)
        call()
        status = 0
    except BaseException:                           # a SystemExit too: nothing leaves a fork but `_exit`
        os.write(STDERR_FD, f"{FORK_S_PYTHON_RAISED}:\n{traceback.format_exc()}".encode())
    finally:
        with contextlib.suppress(Exception):
            sys.stderr.flush()
        os._exit(status)


FORK_S_PYTHON_RAISED = "the fork's own Python raised — the harness's error, not the C's"


# THE HOOKS A FORK MAY BE LEFT SERVING (`serves`), and only inside a case's open pass: the two a core draws and calls
# a handed routine through — the VDI's cores and the register-carrying hook. The fork is made AT THE CALL, inside the
# pass, so the worker's bindings are the fork's already: left alone, they serve the forked run as they will serve
# the run in process a moment later (their records are the fork's own copy, and die with it). For a core of the
# event layer that draws or calls a fork function and reaches NO DOOR (chkkbd, mchange, forker): a fresh interpreter
# per case is what such a battery cannot pay. The event door's two hooks are never among them — a door user's child is
# a fresh interpreter, its door bound for it.
# ...and the scheduler model's (SCHEDULER_HOOKS), with the dispatcher's own hook: a case of the model binds them all
# in its pass (the dispatcher's to the model instead of the refuser) and its fork runs the model — the ROM's own runs
# of a foreign process and of an idle's interrupt made in the fork.
FORK_SERVABLE_HOOKS = frozenset({isr.CALL_VECTOR_SYMBOL, isr.REGISTERS_HOOK_SYMBOL, *SCHEDULER_HOOKS})


# ...and ONE KIND OF FORK IS LEFT EVERY HOOK ITS CASE'S PASS BOUND (EVERY_HOOK_OF_THE_PASS): a door user run IN PROCESS
# with a binding no fresh interpreter can rebuild — the file selector over REAL GEMDOS, its staged disk and its
# recorders the case's own (`aes_fslib.run_session`). Its guard is the fork made at the call, inside the pass, the
# event door's two hooks with the rest: what each records there (the frames handed, the VDI calls noted) is the
# fork's own copy and dies with it, and the run in process a moment later records them once.
EVERY_HOOK_OF_THE_PASS = frozenset(FORK_UNSERVED_HOOKS)


def in_a_fork(call, seconds=CORE_RETURN_SECONDS, serves=()):
    """`call()` made in a FORK of this process (`_the_fork_s_whole_life`): `(exit code, stderr)` — the code negative
    for a signal (the host's refusal aborts; SIGALRM ends a call still running after `seconds`, and with it a fork
    whose parent died), FORK_RAISED for a fork whose Python raised, FORK_REACHED_A_HOOK for a core that reached a
    hook the fork does not serve (`serves`: FORK_SERVABLE_HOOKS' at most — or EVERY_HOOK_OF_THE_PASS, itself). The
    fork never returns into this process's code."""
    assert serves is EVERY_HOOK_OF_THE_PASS or frozenset(serves) <= FORK_SERVABLE_HOOKS, (
        f"a fork serves {sorted(FORK_SERVABLE_HOOKS)} at most, not {sorted(frozenset(serves) - FORK_SERVABLE_HOOKS)}")
    reading, writing = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(reading)
        _the_fork_s_whole_life(call, writing, seconds, serves)
    os.close(writing)
    with os.fdopen(reading, "rb") as said:
        stderr = said.read().decode(errors="replace")
    return os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1]), stderr


# ---- THE GUARD'S FORK, MADE BY THE ZYGOTE WHERE ONE STANDS IN FOR THE WORKER -----------------------------------------
# A fork costs what its parent holds resident, and a worker holds a gigabyte by the time these batteries run; the
# session's ZYGOTE (`zygote.py`: forked when the session starts, `test/conftest.py`) holds the harness and the
# candidate alone, so a fork OF IT costs a tenth. The zygote is handed a run BY CONTENT — the core's symbol and its
# declared types, the values, and the image the kit handed the run, copied into the mapping both share — and makes the
# very fork the worker would have made (`in_a_fork`: the same alarm, the same refusers, the same two stderrs) — over
# an image that is GUARDED on every run (`zygote.py` says why a stand-in owes that): a core that indexes out of its
# image fails its guard by name, in `make test` as under the guarded-image plugin.
#
# WHERE IT STANDS IN: only where its library is in the state the worker's is. So NOT for a fork that `serves` a hook
# (the case's pass bound it in the worker), NOT for a run whose case seeded the library's models (`aes.CoreRun.seeded`:
# the zygote arms the kit's defaults, which is what an unseeded differential armed), NOT while the worker's
# dispatcher hook is another's than this module's refuser, and NOT for a "core" that is no function of the library (a
# test's stand-in). Every such fork is the worker's own, as every fork was. A process with no zygote — a script, a
# child interpreter, the bench — forks itself too.
#
# AND NOT FOR A TEST THAT PATCHES (ZYGOTE_SIDELINED, set by `test/conftest.py` for every test that takes
# `monkeypatch`): the zygote froze this module, and the kit beneath it, as the session started — an attribute patched
# on the fork's side is the worker's fork's and never the zygote's.
#
# A FORK THAT SERVES A HOOK IS THE ZYGOTE'S TOO WHERE THE HOOK IS NAMED (`named_hook`). The worker's own fork of
# such a run is made inside the case's open pass and inherits its binding; the zygote has no pass of the worker's —
# but a binding that is a MODULE-LEVEL builder closed over nothing of a case (the event layer's: the VDI's cores and
# the handed routines, each served by the library's own core) is the same binding wherever it is opened. So it is
# named, "module:attribute"; the zygote resolves the name in ITS interpreter and its fork opens the pass itself
# (`inside_its_own_pass`) round the one call. A hook built per case (a closure, a partial over a case's data) has no
# name, and its forks stay the worker's.
#
# AND A DOOR USER'S CHILD (`door_child`) is a fork of the zygote where its binding is the door's standard one
# (`bind_in_a_child`: nothing of the worker's needed), in place of a fresh interpreter: the same binding, the same
# one call, the same exit statuses, the lines a fresh interpreter prints as it exits printed by the fork's own exit
# functions alone (`_exit_as_an_interpreter_does`).
GUARD_ZYGOTE = []                       # this process's, or nothing (`start_the_guard_s_zygote`)
ZYGOTE_SIDELINED = False
ZYGOTE_SERVED_BY = "aes_event:_served_in_the_zygote"
A_CORE_S_FORK, A_DOOR_CHILD = "a core's fork", "a door user's child"       # what a request of the zygote asks for
ForkedCore = namedtuple("ForkedCore", "symbol restype argtypes typed takes_image answered seconds hook serves",
                        defaults=(None, ()))
DoorChild = namedtuple("DoorChild", "symbol restype argtypes typed objects interrupts answered seconds doors")
_POINTER_TO = "POINTER:"
# WHO MADE EACH CHILD OF THIS PROCESS, counted: the zygote's fork, the worker's own, a fresh interpreter — printed as
# the process ends where AES_FORKS_REPORT is set (the measurement a speed claim about them rests on).
FORKS_MADE = collections.Counter()
FORKS_REPORT = "AES_FORKS_REPORT"
BY_THE_ZYGOTE, BY_THIS_PROCESS, A_FRESH_INTERPRETER = "the zygote's forks", "this process's forks", "fresh interpreters"
if os.environ.get(FORKS_REPORT):
    atexit.register(lambda: FORKS_MADE and print(f"aes_event: children made by pid {os.getpid()}: {dict(FORKS_MADE)}",
                                                 file=sys.stderr))
_NAMED_HOOKS = {}                       # `{id(a hook): (its name, the hook)}` — the hook kept, so its id is its own


def named_hook(module, attribute, hook):
    """`hook` (an `aes.run_function` `hook`: a zero-argument builder of a binding), DECLARED to be the module-level
    value `module.attribute` and nothing of a case's: the zygote may then make the forks that serve it (above).
    Answers the hook, for `ATTRIBUTE = aes_event.named_hook(__name__, "ATTRIBUTE", <the builder>)`.

    ONE NAME PER HOOK: a second declaration of the same object under another name is refused (taken silently, the
    name would have the zygote resolve a hook its first declarer never bound).
    AND THE MODULE MUST BE ONE THE ZYGOTE ALREADY HOLDS (`ZYGOTE_HOLDS`: what this process had imported when it
    forked its zygote — this module and all it imports): the zygote NEVER imports for a hook. A battery's helper
    module is not among them — importing one makes its machines, and took a zygote from 10 MB to 214 MB, every later
    fork paying for it. A hook named in such a module is served all the same: by the worker's own forks, as an
    unnamed one is (`the_zygote_stands_in`). To have the zygote's, alias a hook of this module
    (`HOOKS = aes_event.EVENT_LAYER_HOOKS`), or declare the builder here."""
    name = f"{module}:{attribute}"
    known, _hook = _NAMED_HOOKS.get(id(hook), (name, hook))
    assert known == name, f"{name}: this hook is declared already, as {known} — one name per hook"
    _NAMED_HOOKS[id(hook)] = (name, hook)
    return hook


def name_of_a_hook(hook):
    """The name `hook` was declared under (`named_hook`), or None."""
    name, named = _NAMED_HOOKS.get(id(hook), (None, None))
    return name if named is hook else None


named_hook(__name__, "EVENT_LAYER_HOOKS", EVENT_LAYER_HOOKS)


def hook_named(name):
    """The hook the name spells, resolved in THIS interpreter — held to be a declared one, in a module this
    interpreter HOLDS ALREADY: nothing is imported for it (`named_hook`'s rule; the zygote's side of it)."""
    module, _, attribute = name.partition(":")
    assert module in sys.modules, (
        f"{name}: a named hook lives in a module the zygote holds when it starts ({module} is not imported here) — "
        f"the zygote imports nothing for a hook")
    hook = getattr(sys.modules[module], attribute)
    assert name_of_a_hook(hook) == name, f"{name} is no hook declared under that name (`named_hook`)"
    return hook


def _named_where_the_zygote_holds_it(hook):
    """Is `hook` a NAMED one whose module the zygote holds (`ZYGOTE_HOLDS`)?"""
    name = name_of_a_hook(hook)
    return name is not None and name.partition(":")[0] in ZYGOTE_HOLDS


def _ctype_name(ctype):
    """A ctypes type of a core's signature BY NAME, for the pipe: None, a simple type, or a pointer to one."""
    if ctype is None:
        return None
    if issubclass(ctype, ctypes._Pointer):
        return _POINTER_TO + _ctype_name(ctype._type_)
    assert getattr(ctypes, ctype.__name__, None) is ctype, f"{ctype!r}: not a type `ctypes` names"
    return ctype.__name__


def _ctype_named(name):
    if name is None:
        return None
    if name.startswith(_POINTER_TO):
        return ctypes.POINTER(_ctype_named(name.removeprefix(_POINTER_TO)))
    return getattr(ctypes, name)


def one_run_of(core, typed, buffer, answered):
    """ONE RUN OF A CORE AS A FORK MAKES IT, whoever forks: the library's models armed as an unseeded differential
    arms them (`arm_candidate`), the core called over `buffer` (None: a core that takes no image) with `typed`, its
    answer printed for the parent where it is `answered`."""
    def call():
        arm_candidate()
        answer = core(*typed) if buffer is None else core(buffer, *typed)
        if answered:
            print(f"{vdi_helpers.ANSWER_LINE}{answer}", file=sys.stderr)
    return call


def _typed_core(symbol, restype, argtypes):
    """The library's function `symbol`, typed for ONE request — a function object OF ITS OWN (`_lib[symbol]`: ctypes
    makes one per subscript, where the attribute is one object for the library's life): the types a request names
    are that request's, and the zygote's own `_lib.<symbol>` is left as it was for every fork after it."""
    core = _lib[symbol]
    core.restype = _ctype_named(restype)
    core.argtypes = None if argtypes is None else [_ctype_named(each) for each in argtypes]
    return core


def _served_in_the_zygote(buffer, request):
    """IN THE ZYGOTE (`ZYGOTE_SERVED_BY`): the fork a request asks for, made over `buffer`, the shared image."""
    kind, *fields = request
    return {A_CORE_S_FORK: _forked_in_the_zygote, A_DOOR_CHILD: _a_door_child_in_the_zygote}[kind](buffer, fields)


def _forked_in_the_zygote(buffer, request):
    """...`in_a_fork` of one run of a core — inside a pass of its named hook the fork opens, where it serves one."""
    made = ForkedCore(*request)
    core = _typed_core(made.symbol, made.restype, made.argtypes)
    call = one_run_of(core, made.typed, buffer if made.takes_image else None, made.answered)
    if made.hook:
        call = inside_its_own_pass(hook_named(made.hook), call)
    return in_a_fork(call, made.seconds, made.serves)


def _exit_as_an_interpreter_does(call):
    """`call`, in a fork that stands in for a FRESH INTERPRETER: the exit functions it inherited dropped first (they
    are its parent's), and the ones the call's own code registered — a child's last lines: the frames it was handed,
    a battery's digest — run once it has returned, as an interpreter runs them when it exits. A call that halts or
    ends its process runs none, there as here."""
    def as_a_child():
        atexit._clear()
        call()
        atexit._run_exitfuncs()
    return as_a_child


exit_as_an_interpreter_does = _exit_as_an_interpreter_does    # ...for a door child another module forks (`aes_switch`)


def _a_door_child_in_the_zygote(buffer, request):
    """...and of A DOOR USER'S CHILD: the door bound into the library for the fork's one call (`bind_in_a_child`),
    then the core called over the shared image."""
    made = DoorChild(*request)
    core = _typed_core(made.symbol, made.restype, made.argtypes)

    def call():
        if made.doors:
            # THE ROUTINE'S DECLARED CHILD DOORS (`declare_child_doors`), run IN THE FORK as a fresh interpreter runs
            # them first — `lib` the candidate, `buf` its image: whatever they import or bind is this fork's alone
            # (the zygote itself never imports a battery's module: `named_hook`).
            exec(made.doors, {"lib": _lib, "buf": buffer})      # the module's own declared source, never a case's
        bind_in_a_child(_lib, objects=made.objects, interrupts=made.interrupts)
        answer = core(buffer, *made.typed)
        if made.answered:
            print(f"{vdi_helpers.ANSWER_LINE}{answer}", file=sys.stderr)
    # (Every hook is refused as the fork begins, as in any fork; the child's binding then binds the five it serves.)
    return in_a_fork(_exit_as_an_interpreter_does(call), made.seconds)


# WHAT THE ZYGOTE FROZE, and how a later change of it is SEEN. The zygote is this process as it stood when it was
# forked: the modules it had imported (ZYGOTE_HOLDS) and every module-level value of the ones a fork's behaviour is
# read off (FROZEN_MODULES). A test that takes `monkeypatch` has the zygote sidelined by the suite's rule
# (`test/conftest.py`) — but a value REBOUND any other way (`unittest.mock.patch`, a plain assignment and a `finally`)
# would split the two makers without a word: the worker's fork under the patch, the zygote's without it. So the
# zygote stands in only while those modules' values ARE the ones it froze (`_as_the_zygote_froze_them`: by
# identity, a name at a time; what the worker has ADDED since is its own).
# A TEST THAT MEANS THE ZYGOTE WHILE IT PATCHES THE WORKER'S SIDE says so by this value of ZYGOTE_SIDELINED (falsy:
# the zygote is not sidelined — and distinct from the module's own False: the patches are the test's word, so the
# frozen values are not asked about).
ZYGOTE_HOLDS = frozenset()
FROZEN_MODULES = ("aes_event", "aes", "isr", "aes_gsx", "vdi_entry", "vdi_helpers")
# WHAT IS NOT FROZEN, by module: this module's own two switches for the zygote.
_NOT_FROZEN = {"aes_event": frozenset({"ZYGOTE_SIDELINED", "ZYGOTE_HOLDS"})}
# ...and A MODULE'S LAZY CACHE IS FROZEN BY ITS SHAPE: a name bound FROM None, ONCE, by the first asker, to an answer
# that is the same in any process (the zygote's fork makes its own when it asks): `isr._BENCH`, the cross-compiled
# blob. Held frozen at None, the first test of a process that loaded the blob — every transcription pin does —
# sidelined its zygote for the rest of its life (measured: one battery's 1,066 forks the worker's own again after
# one test of another's). So the ONE transition None -> its first value is the cache's own, and the value it then
# holds is what is frozen: bound AGAIN — a `mock.patch` of the blob, a sweep's own bench assigned and put back in a
# `finally` — the worker's fork would run another bench than the zygote's, and the zygote is sidelined as for any
# other rebound value.
LAZY_CACHES = {"isr": frozenset({"_BENCH"})}
_FROZEN = {}                            # `{module name: {attribute: id(value)}}`, as the zygote was forked
_FIRST_BOUND = {}                       # `{(module name, a lazy cache): the value it was first bound to}`, held alive


class _MeantUnderPatches:
    def __bool__(self):
        return False

    def __repr__(self):
        return "MEANT_UNDER_PATCHES"


MEANT_UNDER_PATCHES = _MeantUnderPatches()


def _values_of(module):
    not_frozen = _NOT_FROZEN.get(module, frozenset())
    return {name: id(value) for name, value in vars(sys.modules[module]).items() if name not in not_frozen}


def _as_frozen(module, name, now, frozen):
    """Is `module.name`, which holds `now`, what the zygote froze (`frozen`: its id then) — or a lazy cache's one
    binding from None (above)?"""
    if id(now) == frozen:
        return True
    if name not in LAZY_CACHES.get(module, ()) or frozen != id(None) or now is None:
        return False
    return _FIRST_BOUND.setdefault((module, name), now) is now


def _as_the_zygote_froze_them():
    """Are the FROZEN_MODULES' module-level values the very objects the zygote was forked with?"""
    return all(_as_frozen(module, name, vars(sys.modules[module]).get(name), value)
               for module, frozen in _FROZEN.items() for name, value in frozen.items())


def start_the_guard_s_zygote():
    """Fork THIS process's zygote now (`test/conftest.py`: as a session starts, before the batteries are imported).
    Ended with the process (`atexit`)."""
    global ZYGOTE_HOLDS
    assert not the_zygote_runs(), "this process has its zygote already"
    ZYGOTE_HOLDS = frozenset(sys.modules)
    GUARD_ZYGOTE[:] = [zygote.Zygote(IMAGE_BYTES, ZYGOTE_SERVED_BY)]
    _FROZEN.clear()
    _FIRST_BOUND.clear()
    _FROZEN.update({module: _values_of(module) for module in FROZEN_MODULES if module in sys.modules})
    atexit.register(stop_the_guard_s_zygote)


def stop_the_guard_s_zygote():
    for each in GUARD_ZYGOTE:
        each.stop()
    GUARD_ZYGOTE.clear()


def the_zygote_runs():
    return (bool(GUARD_ZYGOTE) and not ZYGOTE_SIDELINED and GUARD_ZYGOTE[0].running()
            and (ZYGOTE_SIDELINED is MEANT_UNDER_PATCHES or _as_the_zygote_froze_them()))


def _the_dispatcher_s_hook_is_the_refuser():
    return (ctypes.c_void_p.in_dll(_lib, DISPATCH_SYMBOL).value
            == ctypes.cast(DISPATCH_REFUSER, ctypes.c_void_p).value)


def the_zygote_stands_in(made, serves=(), hook=None):
    """May the zygote make the fork of the run `made` (an `aes.CoreRun`) for this process? The rule above: a fork that
    `serves` hooks only where the case's `hook` is a NAMED one."""
    return (the_zygote_runs() and (not serves or _named_where_the_zygote_holds_it(hook)) and not made.seeded
            and isinstance(made.core, ctypes._CFuncPtr) and _the_dispatcher_s_hook_is_the_refuser())


def _ctypes_named(core):
    return (_ctype_name(core.restype), None if core.argtypes is None else tuple(_ctype_name(each) for each in core.argtypes))


def _by_the_zygote(made, seconds, answered=False, serves=(), hook=None):
    """`(exit code, stderr)` of `made`'s run in a fork OF THE ZYGOTE — `in_a_fork`'s answer, made there."""
    request = ForkedCore(made.core.__name__, *_ctypes_named(made.core), tuple(made.typed), made.buf is not None,
                         answered, seconds, name_of_a_hook(hook) if serves else None, tuple(serves))
    return GUARD_ZYGOTE[0].ask((A_CORE_S_FORK, *request), None if made.buf is None else ctypes.addressof(made.buf))


def _the_zygote_is_gone(gone):
    GUARD_ZYGOTE.clear()
    print(f"aes_event: {gone} — this process makes its own forks from here on", file=sys.stderr)


def guard_fork(call, made, seconds=CORE_RETURN_SECONDS, serves=(), answered=False, hook=None):
    """THE ONE DOOR A CORE'S FORK IS MADE BY: `(exit code, stderr, the zygote that made the fork — or None)` of
    `call()` — one run of a core, `made` the same run by content (an `aes.CoreRun`; `answered`: its answer printed,
    `core_in_a_fork`'s; `hook`: the case's binding, whose pointers the fork `serves`) — in a fork: the zygote's where
    it stands in (`the_zygote_stands_in`), this process's own (`in_a_fork`) everywhere else, and where the zygote
    died (said once, on stderr: the verdict is the same fork's)."""
    if the_zygote_stands_in(made, serves, hook):
        asked = GUARD_ZYGOTE[0]
        try:
            answer = (*_by_the_zygote(made, seconds, answered, serves, hook), asked)
            FORKS_MADE[BY_THE_ZYGOTE] += 1
            return answer
        except zygote.Gone as gone:
            _the_zygote_is_gone(gone)
    FORKS_MADE[BY_THIS_PROCESS] += 1
    return (*in_a_fork(call, seconds, serves), None)


def _vet_returned(name, values, returncode, stderr):
    """THE GUARD'S ONE ASSERTION: the child that ran `addrs.<name>`'s core with the frame `values` came back."""
    called = f"{name}{tuple(values)}"
    assert returncode != FORK_RAISED, f"{called}: the guard itself failed, no verdict on the C — {stderr}"
    assert returncode != FORK_REACHED_A_HOOK, (
        f"{called}: {stderr} — a core that reaches a hook is guarded in a fresh interpreter, its hooks bound "
        f"(`run_guarded`), never in a fork")
    assert returncode == 0, f"{called}: the C did not return in a child ({returncode}): {stderr}"


def forked_first(name, values, serves=(), hook=None):
    """`aes.run_function`'s `first` for a core that reaches no door: each of its runs made in a fork first, and held
    to have returned there (`_vet_returned`) — the hooks it `serves` left as the case's pass bound them (`hook`: that
    pass's builder — a named one's forks are the zygote's)."""
    def first(call, made):
        returncode, stderr, _by = guard_fork(call, made, serves=serves, hook=hook)
        _vet_returned(name, values, returncode, stderr)
    return first


def forked_inside_its_pass(name, values, seconds=CHILD_RETURN_SECONDS):
    """`aes.run_function`'s `first` for a DOOR USER RUN IN PROCESS UNDER A BINDING OF ITS CASE'S OWN
    (EVERY_HOOK_OF_THE_PASS, above): each run of its C made first in a fork of this process — every hook as the open
    pass bound it — and held to have returned there (`_vet_returned`). A core that halts (a VDI function, a handed
    routine or a door entry the binding does not serve) or spins fails its case BY ITS OWN WORDS, in the guard's
    message: in process it was the worker's death, no word said."""
    def first(call, _made):
        FORKS_MADE[BY_THIS_PROCESS] += 1
        returncode, stderr = in_a_fork(call, seconds, EVERY_HOOK_OF_THE_PASS)
        _vet_returned(name, values, returncode, stderr)
    return first


def run_core_guarded(name, arguments, pokes, *, serves=(), **kwargs):
    """THE DIFFERENTIAL OF A CORE THAT REACHES NO DOOR, every run of its C FIRST IN A FORK (above): `aes.run_function`
    of `addrs.<name>` over `pokes`, `kwargs` its own (`steered=` among them, and the `hook=` whose pointers the fork
    `serves`: FORK_SERVABLE_HOOKS) — the run door of the lists', the processes', the lock's, the input's and the
    waits' batteries. A core that reaches the DISPATCHER fails its case here by the hook's own words — a block told
    from a yield — in the guard's message: a case that MEANS to show the switch is `switches_where_the_rom_does`'s."""
    assert not serves or kwargs.get("hook"), f"{name}: a fork serves the hooks its case's pass binds — and it binds none"
    return aes.run_function(name, arguments, pokes, first=forked_first(name, arguments, serves, kwargs.get("hook")),
                            **kwargs)


# ---- THE ONE STEERING LOOP ---------------------------------------------------------------------------------------------
# A STEERED CASE names the reasons its attribution pass is narrowed to (`aes.run_function`'s `steered=`) — and none
# for nothing: a reason named where the pass does not need it leaves its words un-inverted and a skipped store of one
# unseen. Which reasons a case needs is ASKED OF THE PASS: each is tried WITHOUT, and kept only where that fails.
# Three things about the asking, each measured on the event layer's batteries:
#   * THE PLAIN PASS IS MADE ONCE (`Trials`): the ROM's run, the C's, the compare are one deterministic run whatever
#     the narrowed pass is asked — made for the first trial and handed to every other (`aes.run_function`'s `plain=`);
#   * STEERING IS NOT MONOTONIC, so the asking goes TO A FIXPOINT where the layer says (`fixpoint`): a reason the pass
#     fails without WHILE ANOTHER IS STILL NAMED can be needless once that other is gone (a key typed and a press
#     queued: the fork queue's counters). After a round that dropped a reason, the reasons it had kept BEFORE its
#     last drop are asked again (those kept after it were tried against the set as it now stands). One round ends on
#     a set the AES_STEERED_FOR_NOTHING sweep may refuse;
#   * THE ANSWER IS KEPT BY CONTENT (`_reasons_needed`): a trial that FAILS is the dear one (the narrowed ROM run,
#     derailed, runs to its cap), and every worker that meets the case, the guarded suite beside it and the next run
#     of the same tree would find the same reasons. What is kept decides NO verdict: the run that returns is made
#     every time, with exactly those reasons, and the sweep asks each.
class Trials:
    """THE DIFFERENTIALS OF ONE RETURNING CASE, AS ITS STEERING ASKS THEM: `trials(reasons)` is the case with its
    attribution pass narrowed to `reasons` — with none, under the kit's own WHOLE pass. `run(**passes)` is the
    case's one door (`run_core_guarded` over its routine, frame, machine and limits), handed the passes each trial
    names. The plain pass is made once (above), and the last run that passed is remembered with its reasons."""

    def __init__(self, run):
        self._run, self._plain, self.passed = run, None, None

    def __call__(self, reasons):
        self.passed = None
        if not reasons:
            self.passed = reasons, self._run()
            return self.passed[1]
        if self._plain is None:
            self._plain = self._run(poison=False).info
        self.passed = reasons, self._run(steered=reasons, plain=self._plain)
        return self.passed[1]


# The trials of the question being asked (`_reasons_needed`): a kept derivation is a function of its arguments alone,
# and the door its trials go through — a function of those arguments and no more — is handed beside them.
_ASKING = []


@kept_on_disk
def _reasons_needed(question, certain, asked, fixpoint):
    """WHICH OF `asked` THE CASE'S PASS NEEDS beside `certain`, as their indices (none, and nothing certain: it
    passes the kit's whole pass): each tried without, kept where that fails — to a fixpoint, with `fixpoint`.

    KEPT BY CONTENT, though its trials run the candidate — which a derivation's contract otherwise excludes — because
    the tree's key holds the candidate's library as this process loaded it (and a process whose library is not the
    project's own keeps nothing). `question` is the key's: the case, read by value."""
    del question
    trials = _ASKING[-1]
    named, again = certain + asked, asked
    while again:
        kept, kept_before_the_last_drop = [], 0
        for reason in again:
            without = tuple(other for other in named if other is not reason)
            try:
                trials(without)
            except (AssertionError, RuntimeError):
                kept.append(reason)     # the pass fails without it: the reason stays, held by the run that returns
                continue
            named, kept_before_the_last_drop = without, len(kept)
        again = tuple(kept[:kept_before_the_last_drop]) if fixpoint else ()
    return tuple(index for index, reason in enumerate(asked) if any(reason is other for other in named))


def steered_as_needed(trials, question, certain, asked, *, fixpoint):
    """A case's differential (`trials`: a `Trials`) with its attribution pass NARROWED to `certain` and the fewest of
    `asked` it passes with (`_reasons_needed`: asked once per tree — `question` its key, None for a case nobody can
    read by value, asked every time). The trials are made with the AES_STEERED_FOR_NOTHING sweep off (it would
    refuse a trial for a reason still to be asked about); under it the run that returns is made again, so the sweep
    itself re-asks every reason left, `certain`'s too."""
    sweeping = os.environ.pop(aes.STEERED_FOR_NOTHING_SWEEP, None)
    _ASKING.append(trials)
    try:
        if question is None:
            needed = _reasons_needed.derive(question, certain, asked, fixpoint)
        else:
            try:
                needed = _reasons_needed(question, certain, asked, fixpoint)
            except NotReadableByValue:      # a hook or a reason nobody can read by value: asked every time
                needed = _reasons_needed.derive(question, certain, asked, fixpoint)
    finally:
        _ASKING.pop()
        if sweeping is not None:
            os.environ[aes.STEERED_FOR_NOTHING_SWEEP] = sweeping
    reasons = certain + tuple(asked[index] for index in needed)
    if not sweeping and trials.passed and len(trials.passed[0]) == len(reasons) and all(
            mine is its for mine, its in zip(trials.passed[0], reasons)):
        return trials.passed[1]         # ...the last trial was this very run: not made again
    return trials(reasons)


def _question_of(name, arguments, machine, limits):
    """A steered case as `_reasons_needed`'s key reads it: its routine, frame, machine and limits — its hook BY NAME
    (`named_hook`); None for a case whose hook has none (a binding built per case: nobody can read it by value)."""
    hook = limits.get("hook")
    if hook is not None and name_of_a_hook(hook) is None:
        return None
    rest = tuple(sorted((key, value) for key, value in limits.items() if key != "hook"))
    return name, tuple(arguments), machine, rest, name_of_a_hook(hook) if hook is not None else None


def run_core_steered(name, arguments, pokes, certain=(), asked=(), *, fixpoint=False, **kwargs):
    """`run_core_guarded`, THE ATTRIBUTION PASS STEERED AS THE CASE'S LAYER SAYS (above): the kit's own pass, whole,
    where no reason is named; narrowed to `certain` — the reasons that steer every such case — and to each of
    `asked` ONLY WHERE THE PASS FAILS WITHOUT IT. The door for a layer that keeps its own table of which reasons are
    `certain` and which `asked` for a routine (`aes_evlib.steered_by`, `aes_evinput.steered_by`: one round, as their
    tables were proved by); a routine that calls into several layers takes `run_layer_case`, which derives them."""
    certain, asked = tuple(certain), tuple(asked)
    if not asked:                       # nothing to ask: ONE run, the kit's own plain pass and narrowed one in it
        return run_core_guarded(name, arguments, pokes, **({"steered": certain} if certain else {}), **kwargs)
    trials = Trials(lambda **passes: run_core_guarded(name, arguments, pokes, **passes, **kwargs))
    return steered_as_needed(trials, _question_of(name, arguments, pokes, kwargs), certain, asked, fixpoint=fixpoint)


# ---- WHAT STEERS A CASE'S ATTRIBUTION PASS, DERIVED ----------------------------------------------------------------------
# Each layer's helper module DECLARES its reasons (`aes.steers(...)`: module-level values — a list's links, a pipe's
# index, the event bits, the fork queue's counters ...) and keeps a table of which routine each steers. A routine
# that calls into several layers (ev_multi: all four) would need a fifth table restating theirs. It needs none: a
# reason can steer a case only if the ROM's run STORES one of its words (the pass inverts stored bytes alone), and
# whether it DOES steer is what the pass itself says (`run_core_steered`'s `asked`: tried without, named only where
# that fails). So the candidates are read off the modules, the membership off the run; a layer's own table is a
# speed hint (`certain`: no trial run), held like every reason by the AES_STEERED_FOR_NOTHING sweep.
STEERING_MODULES = ["aes_pdpipe", "aes_evlib", "aes_evinput"]


def declare_steering_module(name):
    """`name` (a helper module of a layer's battery) declares steering reasons at its top level too."""
    if name not in STEERING_MODULES:
        STEERING_MODULES.append(name)
        steering_reasons.cache_clear()


@functools.cache
def steering_reasons():
    """Every reason the layers' helper modules declare, once each, in the modules' order."""
    reasons = []
    for module in STEERING_MODULES:
        for value in vars(importlib.import_module(module)).values():
            if isinstance(value, aes.Steers) and not any(value is known for known in reasons):
                reasons.append(value)
    return tuple(reasons)


@kept_on_disk
def _stored_by_the_rom(name, arguments, machine):
    image = make_image(aes.staged(name, vdi.as_signed(name, arguments), machine))
    _final, writes, _regs = emu.run(image, getattr(addrs, name), stop_pc=addrs.AES_ROM_DSPTCH)
    return frozenset(case.written_by(writes))


def steering_asked(name, arguments, machine, certain=()):
    """The reasons a returning case of `addrs.<name>` over `machine` ASKS its pass about (`run_core_steered`): every
    declared reason, `certain`'s aside, one of whose words the ROM's own run stores."""
    stored = _stored_by_the_rom(name, tuple(arguments), machine)
    return tuple(reason for reason in steering_reasons() if not any(reason is known for known in certain)
                 and any(at in stored for lo, hi in reason.spans for at in range(lo, hi)))


def run_layer_case(name, arguments, machine, *, hook=None, certain=(), also=(), dropped_windows=None, **kwargs):
    """THE DIFFERENTIAL OF AN EVENT-LAYER ROUTINE THAT RETURNS, whatever layers it calls into: every run of its C first
    in a fork (`run_core_guarded` — `hook`'s pointers left served there, for a core that polls or runs the fork
    queue: EVENT_LAYER_HOOKS), compared outside EVENT_LAYER_DROPS where the ROM's run stores them (or the case's own
    `dropped_windows`), THE ATTRIBUTION PASS STEERED BY DERIVATION (above) AND TO A FIXPOINT (`steered_as_needed`):
    every declared reason whose words the ROM's run stores is asked, with the reasons the CASE says may steer it
    (`also`); a case that asks none runs under the kit's whole pass. `certain`: reasons taken for needed wherever
    they are among the asked — A SPEED HINT (it spares the trial that fails without one), held like every reason by
    the AES_STEERED_FOR_NOTHING sweep. A QPB's address the ROM's run leaves in a freed EVB is dropped by name, vetted
    against the C's own (`qpb_addresses_a_return_leaves`). A case that names its own `steered=` or `poison=` is run
    as it says."""
    hooked = {"hook": hook, "serves": SERVED_IN_A_FORK} if hook else {}
    drops = EVENT_LAYER_DROPS if dropped_windows is None else dropped_windows
    kept = qpb_addresses_a_return_leaves(name, arguments, machine)
    if kept:                            # vetted against the C's own image at its return: one more run of it, in a fork
        forked = core_in_a_fork(name, arguments, machine, read_back=True, hook=hook)
        assert forked.returncode == 0, f"{name}: the ROM's run returns; the C's fork ended {forked.returncode}: {forked.stderr}"
        drops += vetted_qpb_addresses(name, forked.image, kept, getattr(addrs, name))
    limits = {"dropped_windows": drops, **hooked, **kwargs}
    if "steered" in kwargs or "poison" in kwargs:
        return run_core_guarded(name, arguments, machine, **limits)
    trials = Trials(lambda **passes: run_core_guarded(name, arguments, machine, **passes, **limits))
    asked = steering_asked(name, arguments, machine) + tuple(also)
    if not asked:
        return trials(asked)
    for_certain = tuple(reason for reason in asked if any(reason is known for known in certain))
    the_rest = tuple(reason for reason in asked if not any(reason is known for known in for_certain))
    return steered_as_needed(trials, _question_of(name, arguments, machine, limits), for_certain, the_rest, fixpoint=True)


Forked = namedtuple("Forked", "returncode stderr image answer")


def inside_its_own_pass(hook, call):
    """`call`, made INSIDE A PASS OF `hook` THE FORK OPENS ITSELF (`aes.run_function`'s `hook`: a zero-argument
    builder of a case's binding) — for a core run in a fork outside any case's pass, which calls out through hooks
    (the VDI's cores under a keyboard poll, a fork function through the register hook) before it returns or halts.
    A call the binding does not serve is recorded and fails the fork by name as the pass closes (FORK_RAISED)."""
    def hooked():
        with hook() as bound:
            bound.recording(lambda _lib, _buf: call())(None, None)
    return hooked


def core_in_a_fork(name, values, pokes, *, seconds=CORE_RETURN_SECONDS, answered=False, read_back=False, hook=None):
    """What `addrs.<name>`'s core says over `pokes` with the frame `values` in a FORK, for a case that MEANS to show
    a halt or a return there (`refusal`'s fork kind: no interpreter started, no image file): a `Forked` — the exit
    code and stderr (`guard_fork`), the image as the core left it (`read_back`: the fork runs over a mapping it shares
    with this process, so every store made before a halt is there) and the core's answer (`answered`, at its declared
    width; None for a core that did not return). The library's models are armed as a differential arms them
    (`arm_candidate`): the verdict is this call's, whatever test ran before. `hook`: the binding of a core that
    calls out before it ends, opened by the fork for its one run (`inside_its_own_pass`) — the two hooks a fork may
    serve (FORK_SERVABLE_HOOKS) are then left as the worker holds them, every other refused by name as ever."""
    core = getattr(_lib, routines.core_symbol(name))
    typed = vdi.as_signed(name, values)
    serves = tuple(sorted(FORK_SERVABLE_HOOKS)) if hook else ()
    # THE IMAGE IS COPIED ONCE MORE, into the mapping the fork runs over: the zygote's own (`Zygote.ask` copies it
    # there) where the zygote stands in, one this call shares with its own fork everywhere else.
    start = make_image(pokes)
    by_the_zygote = the_zygote_stands_in(aes.CoreRun(core, typed, start, seeded=False), serves, hook)
    over = start if by_the_zygote else mmap.mmap(-1, IMAGE_BYTES)
    if not by_the_zygote:
        over[:] = start
    buf = (ctypes.c_uint8 * IMAGE_BYTES).from_buffer(over)
    call = one_run_of(core, typed, buf, answered)
    returncode, stderr, by = guard_fork(inside_its_own_pass(hook, call) if hook else call,
                                        aes.CoreRun(core, typed, buf, seeded=False), seconds, serves, answered=answered,
                                        hook=hook)
    if by_the_zygote and by is None:    # the zygote died under this very call, and the worker's fork in its place ran
        # over an image this process does not share: made again, the worker's own from the start
        return core_in_a_fork(name, values, pokes, seconds=seconds, answered=answered, read_back=read_back, hook=hook)
    image = None
    if read_back:                       # ...out of the mapping the fork ran over: the zygote's, or this call's own
        image = by.image() if by else bytes(over)
    return Forked(returncode, stderr, image, vdi_helpers.answer_in(stderr) if answered else None)


# ---- A CALL THAT SWITCHES: the C at the dispatcher's hook against the ROM AT DSPTCH -------------------------------------
# A routine of the event layer whose run reaches dsptch — a wait nothing satisfies BLOCKS, a hand-over YIELDS — has no
# return to compare. What both shores have is the machine AT DSPTCH: every list, EVB and PD the routine wrote before
# it asked for the switch (nothing of the switch is stored yet: savestate comes after). The ROM's is its own run of
# the routine, entered at it and stopped at dsptch (`rom_at_dsptch`); the C's is the image it holds when it calls the
# dispatcher's hook, which refuses by name — read back out of the fork it ran in: the host's model of the
# switch, for the event layer's own batteries (a door USER's blocking case is `interrupted`, ending blocked:
# `blocked_then_woken`'s first half).
HALTED_AT_THE_DISPATCHER = "the dispatcher: the case's hook refused the call"     # `aes/switch.h`'s halt line
AtDsptch = namedtuple("AtDsptch", "memory writes switches")
Switched = namedtuple("Switched", "image rom_memory stderr parked", defaults=((),))


def _staged(name, arguments, pokes):
    """`pokes` with the frame of `addrs.<name>(arguments)` where a `jsr` leaves it: a routine a battery declared by
    its signature (`aes.staged`), or — undeclared — a door entry, by its row's frame (`entry_frame`)."""
    if name in vdi.ALCYON:
        return aes.staged(name, arguments, pokes)
    return merge_pokes(pokes, {abi.FIRST_ARG: entry_frame(name, *arguments)})


def rom_at_dsptch(name, arguments, pokes, *, budget=None):
    """The ROM's own `addrs.<name>` over `pokes` with the frame `arguments`, entered AT the routine and run until it
    reaches dsptch — an `AtDsptch`: its memory there, what it wrote on the way, and the kind of switch it asks for
    (BLOCKS / YIELDS, `switch_at`). A derivation's prefix (`stopped_at`: its budget and margin); refused by name where
    the run returns without reaching the dispatcher."""
    final, writes, _regs = stopped_at(make_image(_staged(name, arguments, pokes)), getattr(addrs, name),
                                      addrs.AES_ROM_DSPTCH, budget)
    return AtDsptch(bytes(final), writes, switch_at(final))


def switches_where_the_rom_does(name, arguments, pokes, *, switches=BLOCKS, dropped=(), budget=None,
                                seconds=CORE_RETURN_SECONDS, hook=None):
    """A case that MEANS the switch: `addrs.<name>`'s core over `pokes` with the frame `arguments`, in a fork, HALTS
    AT THE DISPATCHER'S HOOK — refused as a call that `switches` (BLOCKS, or YIELDS) — where the ROM's own run of the
    routine reaches dsptch asking for the same kind of switch, and the image the C holds there is the ROM's memory at
    dsptch: everywhere but the stack band, the Line-F mask word, the trap's saved registers (and, for a core that
    polled the keyboard, the trap frame's PC and SR: `TRAP_FRAME_DROP`), the SR save words the ROM's run stored
    (`not_compared_where_the_rom_stored`) and THE ADDRESS OF A QPB A PIPE WAIT PARKED IN A STACK — found on the
    machine and vetted (`parked_where_blocked`), for every case, whatever its routine. `dropped` (`(lo, hi, why)` each,
    as a differential's `dropped_windows`): what THIS case differs in by nature beside — each REQUIRED to be bytes
    the ROM's run stored, whole: a drop over anything else is refused by name. `hook`: the binding of a core that
    calls out BEFORE it switches (ev_multi polls the keyboard through the VDI and runs the fork queue first),
    opened by the fork (`core_in_a_fork`). Answers `Switched(image, rom_memory, stderr, parked)` for the case's own
    assertions — `parked` the QPBs found parked, `(process, count, buffer)` each."""
    the_rom_s = rom_at_dsptch(name, arguments, pokes, budget=budget)
    assert the_rom_s.switches == switches, (
        f"{name}: the premise — at dsptch the ROM's run is one where {switches} — does not hold: {the_rom_s.switches}")
    # (Over the machine WITH the call's frame where the ROM's run has it: a frame longer than the stack band's reach —
    # ev_multi's twenty-six bytes — is compared, and the C, which reads none of it, must not differ there.)
    forked = core_in_a_fork(name, arguments, _staged(name, arguments, pokes), seconds=seconds, read_back=True, hook=hook)
    assert forked.returncode not in (0, FORK_RAISED, FORK_REACHED_A_HOOK), (
        f"{name}: the ROM's run reaches the dispatcher ({switches}); the C's fork ended {forked.returncode}: {forked.stderr}")
    assert HALTED_AT_THE_DISPATCHER in forked.stderr and switches in forked.stderr, (
        f"{name}: the ROM's run reaches the dispatcher ({switches}); the C did not halt at the dispatcher's hook as "
        f"one that does:\n{forked.stderr}")
    by_nature = frozenset(at for lo, hi, _why in dropped for at in range(lo, hi))
    assert by_nature <= the_rom_s.writes.keys(), (
        f"{name}: dropped at dsptch, and not stored by the ROM's run: "
        f"{[f'{at:#x}' for at in sorted(by_nature - the_rom_s.writes.keys())]} — a drop names what the run WROTE")
    not_compared = not_compared_where_the_rom_stored(the_rom_s.memory, _staged(name, arguments, pokes))
    not_compared |= frozenset(at for at in TRAP_FRAME_BYTES if at in the_rom_s.writes)
    parked = parked_where_blocked(name, forked.image, the_rom_s.memory, routine=getattr(addrs, name))
    differ = differing(forked.image, the_rom_s.memory, not_compared | by_nature | parked.dropped)
    assert not differ, "at dsptch, " + _describe_differences(name, forked.image, the_rom_s.memory, differ)
    return Switched(forked.image, the_rom_s.memory, forked.stderr, parked.qpbs)


# WHO HOLDS A CHILD'S DOOR CALLS — `door_child`'s `door_calls`, which has NO DEFAULT: every road that makes a door
# user's child says it. WATCHED: `door_child` itself makes the ROM's own watched run of the call and holds what the
# child said of each door call to it — the frames handed, the answers handed back, the image at each return
# (`hold_a_child_s_door_calls`). Or a `HeldElsewhere`: WHY this road cannot or need not, and WHO holds them, in words
# at the call.
WATCHED = "held to the ROM's own watched run of the call"


class HeldElsewhere(str):
    """Why a door user's child is not held to the ROM's watched run where it is made — and who holds its door calls."""


def hold_a_child_s_door_calls(name, values, pokes, stderr, delivered=None, budget=None, calls=None):
    """WHAT A CHILD SAID OF ITS DOOR CALLS (`stderr`: the two lines it prints where it ends, `_handed_line`) IS THE
    ROM'S OWN — the ROM's watched run of `addrs.<name>` over `pokes`, `delivered` laid at its door calls (or
    `calls`, a watched run its caller has made already: a `Calls`, images taken): every frame handed, every answer
    handed back and the image at each return (`vet_the_answers_handed_back`). A child that ended before it could
    say (a halt that is no dispatcher's refusal: its caller holds how it ended) is asked nothing — but one held to
    a run ALREADY MADE is held to it whatever it said: its road has it say each call as it goes
    (SAY_EACH_DOOR_CALL), and one that said none made none."""
    if calls is None:
        if HANDED_LINE not in stderr:
            return
        calls, _memory, _result = _watched_through(name, values, pokes, delivered or {}, budget=budget)
    assert handed_in(stderr) == calls, f"{name}: the door was handed {handed_in(stderr)}, the ROM's run hands {calls}"
    vet_the_answers_handed_back(name, answered_in(stderr), calls.answers)


def door_child(name, values, pokes, *, door_calls, budget=None, **binding):
    """A DOOR USER's child (`_a_door_child`: its arguments), ITS DOOR CALLS HELD — by this call (`door_calls` WATCHED:
    the ROM's watched run of the same call, under `budget` where it declares one, `interrupts` laid at the same door
    calls; or the `Calls` of a watched run the caller made, for a call whose ROM run is ended somewhere a plain
    watched run is not) or by whoever `door_calls` says (a `HeldElsewhere`). `refusal`'s `(returncode, stderr,
    image)`."""
    watched_already = isinstance(door_calls, Calls)
    assert door_calls == WATCHED or watched_already or (isinstance(door_calls, HeldElsewhere) and door_calls), (
        f"{name}: a door user's child says who holds its door calls — WATCHED, the ROM's watched `Calls` its caller "
        f"made, or a `HeldElsewhere` with its reason")
    returncode, stderr, image = _a_door_child(name, values, pokes, **binding)
    if watched_already or door_calls == WATCHED:
        hold_a_child_s_door_calls(name, values, pokes, stderr, binding.get("interrupts"), budget,
                                  calls=door_calls if watched_already else None)
    return returncode, stderr, image


def _a_door_child(name, values, pokes, *, objects=False, interrupts=None, before="", seconds=vdi_helpers.CHILD_SECONDS,
                  answered=False, read_back=True):
    """A DOOR USER's core `addrs.<name>` over `pokes` with the frame `values`, in a CHILD with the door's standard
    binding (`bind_in_a_child`: every entry served or an arrival, the VDI's cores, the walked routines with
    `objects`, `interrupts` laid at its door calls): `refusal`'s `(returncode, stderr, image)`. A FORK OF THE ZYGOTE
    where one runs for this process (above) — and a fresh interpreter (`refusal`) everywhere else: with no zygote,
    under a test that patches (ZYGOTE_SIDELINED), and for a child that runs A CASE'S OWN source first (`before`:
    run in that interpreter). `before` that is THE ROUTINE'S DECLARED CHILD DOORS and nothing else
    (`CHILD_DOORS[name]`: a constant its module declared once, `declare_child_doors`) is the zygote's all the same —
    its fork runs that source first, as the interpreter would (the file selector's GEMDOS replay: 117 interpreters a
    suite run, each importing this whole module again to bind one hook). A child still running after `seconds`
    raises `subprocess.TimeoutExpired`, whichever made it."""
    if the_zygote_runs() and before in ("", CHILD_DOORS.get(name, "")):
        signature, asked = vdi.ALCYON[name], GUARD_ZYGOTE[0]
        # ...the call typed by the routine's declared signature, its answer printed where it declares one (`refusal`'s
        # own two rules).
        request = DoorChild(routines.core_symbol(name), _ctype_name(signature.restype),
                            tuple(_ctype_name(each) for each in signature.argtypes), tuple(vdi.as_signed(name, values)),
                            bool(objects), interrupts, answered and signature.restype is not None, seconds, before)
        start = make_image(pokes)
        try:
            returncode, stderr = asked.ask((A_DOOR_CHILD, *request),
                                           ctypes.addressof((ctypes.c_uint8 * IMAGE_BYTES).from_buffer(start)))
        except zygote.Gone as gone:
            _the_zygote_is_gone(gone)
        else:
            FORKS_MADE[BY_THE_ZYGOTE] += 1
            if returncode == -signal.SIGALRM:
                raise subprocess.TimeoutExpired(f"the zygote's fork of {name}", seconds, stderr=stderr)
            return returncode, stderr, asked.image() if read_back else None
    FORKS_MADE[A_FRESH_INTERPRETER] += 1
    return refusal(name, pokes, values, bind=child_binding(objects=objects, interrupts=interrupts, before=before),
                   seconds=seconds, answered=answered, read_back=read_back)


# The door users' guards that returned, by CONTENT — (routine, frame, binding, THE IMAGE the pokes make: laid over
# each other in the order `make_image` lays them, `merge_pokes`): one child per distinct call in a worker (a case run
# both directly and through its Line-F word is the same C call twice). Never by the machine's identity — a freed
# dict's address is the next one's — nor by its pokes sorted: two machines of the same overlapping pokes laid in
# another order are two images, and the second would pass unguarded on the first's word (`test_aes_event.py` holds
# both).
_RETURNED_IN_A_CHILD = set()


HELD_BY_THE_DIFFERENTIAL_THAT_FOLLOWS = HeldElsewhere(
    "`run_guarded`'s guard: the same C over the same call runs IN PROCESS next (`run_event`), its frames, answers and "
    "images held there to the ROM's watched run — under the case's own cap and budget, refused in their words")


HELD_AFTER_ITS_RETURN = HeldElsewhere("`returns_in_a_child` holds them itself, once the child is seen to have returned")


def returns_in_a_child(name, values, pokes, *, objects=False, seconds=CHILD_RETURN_SECONDS, door_calls=WATCHED):
    """A DOOR USER's core `addrs.<name>` over `pokes` with the frame `values` RETURNS in a child — a fresh interpreter,
    the event door bound (`refusal`; the walked routines served with `objects`): the guard `run_guarded` runs before
    its in-process differential — ITS DOOR CALLS HELD to the ROM's watched run like any child's (`door_child`'s
    WATCHED), or by the differential `run_guarded` makes next (the `HeldElsewhere` it says). Once per distinct
    call and holder in a worker."""
    bind = child_binding(objects=bool(objects))
    guarded = (name, tuple(values), bind, tuple(merge_pokes(pokes).items()), door_calls == WATCHED)
    if guarded in _RETURNED_IN_A_CHILD:
        return
    held_here = door_calls == WATCHED   # ...after HOW it ended is held: a child that did not return is refused by that
    returncode, stderr, _image = door_child(name, values, pokes, door_calls=HELD_AFTER_ITS_RETURN if held_here else door_calls,
                                            objects=bool(objects), seconds=seconds, read_back=False)
    _vet_returned(name, values, returncode, stderr)
    if held_here:
        hold_a_child_s_door_calls(name, values, pokes, stderr)
    _RETURNED_IN_A_CHILD.add(guarded)


# ---- the ROM's own calls of the door's entries: its run WATCHED ------------------------------------------------------
# Where a ROM caller's Line-F word returns to: the word after it — the address the Line-F handler pushes before its
# `jmp (a0)` into the entry ($fee8d0), so the one on the stack at the entry's first instruction.
ROM_RETURNS = frozenset(at + aes.WORD_BYTES for name in ENTRY_NAMES
                        for sites in aes.line_f_call_sites(name).values() for at in sites)


EXCEPTION_FRAME_PC = aes.WORD_BYTES     # a 68000 exception frame: the status register's word, then the return PC


class Blocked(AssertionError):
    """A watched run (`DoorStops(..., blocks=True)`) reached the dispatcher inside a door call: the call would block.
    An AssertionError, so a run that was not meant to block — a Tier 3 row, a replay — is refused by its words."""


M68K_REG_D0 = 0                         # Musashi's register number of D0 (`m68k_register_t`)


def _d0_at_the_stop():
    """D0 of the bench run in flight, where its watch has stopped it: the oracle's own CPU, read."""
    return emu._LIB.m68k_get_reg(None, M68K_REG_D0)


class Calls(list):
    """The door calls a watched run made (`Handed` each, in order) — with `answers`, the `(entry, D0)` of each that
    RETURNED (`DoorStops.answers`): what the answers a candidate's twins hand back are held to."""

    answers = ()


class DoorStops:
    """A WATCH (`rom_bench.watched`) over a run that calls the door's `entries`: it stops at each entry ITSELF — the
    door a set of exact PCs (`emu.bench_door_arm`), so nothing between the entries is stopped at — `opened(pc, sp,
    memory)` called there and the return address the call left on the stack becoming the next stop, where `closed()`
    is called and the entries are watched again. Refused by name: an entry reached from a return address that is none
    of `returns` (the run reached the event layer by another road). With `blocks`, a stop at the DISPATCHER inside a call
    too, which ends the run there (`Blocked`): where the call blocks — for a case comparing it with a door's refusal,
    and for any other run a refusal by name, not a run spinning to its budget.

    `delivered` (`deliveries`' `{ordinal: (found, wrote)}`) lays each interrupt into the run's memory at the entry of
    the door call of that ordinal, before `opened` — CHECKED FIRST: the memory must hold `found` at every address the
    delivery writes (what neither shore compares aside, `_NOT_COMPARED`), or the delta is not the machine's for this run
    and the stop refuses by name (`_vet_found`). `calls`: the door calls entered so far.

    A run MARKED (`marked_with`, a session priced by its slices: `Marks`) is told of every arrival outside a door
    call — at each door entry, once its delivery is laid, and at each TRAP HANDLER its marks name, which the run then
    stops at too: there the exception frame's return address becomes the next stop, as a door call's does, so a trap
    taken inside the trap (GEMDOS's own BIOS calls) or inside a door call (the event layer's keyboard poll) is no
    arrival, on either shore.

    `twins` (`{PC: entry}`, a run of OUR build's): the first instruction of each REBOUND entry's C twin as that build
    places it — an ARRIVAL like a stop at a ROM entry, and under the ROM entry's name: the same ordinal among the
    door calls, the same delivery laid, the same mark taken (`entry_at`), its call read off GCC's frame (`call_at`),
    and everything up to the twin's return inside the call — so the VDI traps a twin's keyboard poll takes are no
    arrivals, as the ROM routine's are none. A twin is entered from wherever the compiler placed its call — a `jsr`,
    ALWAYS: a tail `jmp` would leave it its caller's CALLER's return address (the run's sentinel, for a row entered at
    the caller), so the wrappers and the twins' own calls of one another are spelt to stay calls
    (`EVDOOR_A_CALL_NOT_A_JUMP`, `include/transcribed.h`), and `test_tier3.py` holds both blobs to it. Its return
    address is therefore no fixed site of `returns`, but it is BOUNDED — inside `twins_called_from`, the `(lo, hi)`
    of our build's own text: a twin reached with any other return address (the ROM's text, a stack address, the
    sentinel) was reached by no call of ours, and is refused by name.

    A RUN ENTERED AT ONE OF ITS OWN STOPS (`entered_at`: the PC the run starts at — a door entry's own row or case, a
    twin's) is not an arrival there: the routine was entered, not called, and its return address is the run's
    sentinel. The bench stops at a listed PC BEFORE executing it, the run's first included: that stop — the run's
    first, nothing executed yet — is taken as the entry it is, and the PC left out of the next stops, as
    `EntryStops` leaves out the entry it stands at (a recursive arrival is seen only once another stop came between).
    The outermost entry reached INSIDE the entered routine is then door call 0, on both shores. Such a routine is the
    event layer's own, and may reach the dispatcher itself, outside any door call: with `blocks` the run ends there
    too (`Blocked`), and `calls` is what it had entered — none, for a wait that blocks at once.

    `dispatchers` (a run of OUR build's, with `blocks`): where that build places ITS OWN dsptch (`aes/switch.h`:
    the `.S` entry a twin that waits calls) — a stop like the ROM's, for the same refusal. A twin runs none of the
    ROM's text, so a watch that named the ROM's dsptch alone would let a twin that blocks run our dispatcher's idle
    loop to the oracle's budget: a spin of sixteen million instructions where the refusal is one stop.

    `first`: the stops outside every door call — what the run starts with, and what each stop outside a call arms
    again. A subclass that watches more adds to it (`aes_fslib.GemdosCalls`).

    `answers`: `(entry, D0)` of every door call that RETURNED, in order — the run's D0 read at the stop where the
    call comes back (the ROM routine's answer, behind its Line-F return; a twin's, on a blob) — and, for a watch
    told to take them (`images`: the windows its road leaves out beside, `()` for none; None: not taken), THE
    MEMORY THERE AS ITS PAGES (`image_pages`), a third field."""

    def __init__(self, entries, returns, opened=None, closed=None, *, blocks=False, delivered=None, twins=None,
                 twins_called_from=None, entered_at=None, dispatchers=()):
        self.twins = dict(twins or {})
        assert not self.twins or twins_called_from, "a watch at twins names the text their calls come from"
        assert blocks or not dispatchers, "a watch that names a build's own dispatcher is one that `blocks`"
        self._twins_called_from = twins_called_from
        self.entries, self.returns = frozenset(entries) | frozenset(self.twins), frozenset(returns)
        self._inside = frozenset({addrs.AES_ROM_DSPTCH, *dispatchers}) if blocks else frozenset()
        self.first = self.entries
        self.entered_at_an_entry, self._enters_at = False, None
        self.entered_at(entered_at)
        # A watch's own `_opened` / `_closed` (a subclass's methods) are NOT handed here: a bound method kept on its
        # own instance is a reference cycle, and the watch — with its marks, a memory per slice end — would then
        # outlive its run until a later collection (measured: 1.9 GB peak in one test where 1 GB is in use).
        if opened is not None:
            self._opened = opened
        if closed is not None:
            self._closed = closed
        self._in_call, self._open_entry = False, None
        self._delivered = delivered or {}
        self.calls = 0
        self.answers, self.images = [], NO_IMAGE_TAKEN
        self.marks, self._marked_trap, self._trap_returns_to = None, None, None

    def _opened(self, pc, sp, memory):
        """A door call entered at `pc`: nothing, unless `opened` was given or a subclass says."""

    def _closed(self):
        """...and returned from."""

    def entry_at(self, pc):
        """The door entry a stop at `pc` arrives at: `pc` itself, or the ROM entry a twin there stands for."""
        return self.twins.get(pc, pc)

    def call_at(self, pc, sp, memory):
        """What the call a run stopped at the entry `pc` hands it (`handed_at`, or a twin's `handed_at_a_twin`)."""
        return handed_at_a_twin(self.twins[pc], sp, memory) if pc in self.twins else handed_at(pc, sp, memory)

    def entered_at(self, pc):
        """This watch, over a run ENTERED AT `pc`: where that is one of its stops (an entry, a twin's first
        instruction), no arrival there — and the dispatcher watched outside the door calls too (the class's note)."""
        if pc in self.entries:
            self.entered_at_an_entry, self._enters_at = True, pc
            self.first = self.first | self._inside
        return self

    def marked_with(self, marks):
        """This watch, its run MARKED by `marks` (`Marks`): stopped at the trap handlers they name as well."""
        self.marks = marks
        self.first = self.first | marks.traps
        return self

    def _called_by_our_build(self, pc, back):
        """Is `pc` a twin's first instruction, reached with a return address in our build's own text?"""
        return pc in self.twins and self._twins_called_from[0] <= back < self._twins_called_from[1]

    @property
    def between_calls(self):
        """Is the run outside every door call — so a stop at an entry opens the next?"""
        return not self._in_call

    def foreign_window_opened(self):
        """ANOTHER PROCESS THAN THE RUN'S OWN IS ENTERED (told by the watch that follows the run through the
        dispatcher, `aes_switching.Switching`, which arms none of this watch's stops until that process's turn is
        over): a watch that prices its calls says what a call open across the turn is net of
        (`tier3.DoorWindows`) — and A MARKED RUN'S MARKS ARE TOLD, whatever the watch counts: a mark is an arrival
        of the run's own process, and what another process's turn spends is no part of any slice (`Marks`)."""
        if self.marks:
            self.marks.foreign_window_opened()

    def foreign_window_closed(self):
        """...and the run's own process is resumed."""
        if self.marks:
            self.marks.foreign_window_closed()

    def opens_a_call_at(self, pc):
        """Would a stop at `pc`, as the watch stands, OPEN A DOOR CALL — an arrival, where a delivery is laid and an
        interrupt taken? Not the run's own entry (its first stop: entered, not called), not a marked trap or its
        return, not the dispatcher reached outside every call."""
        return (not self._in_call and self._enters_at is None and self._trap_returns_to is None
                and pc in self.entries)

    def stopped(self, pc, sp, memory):
        if self._enters_at is not None:
            entered, self._enters_at = self._enters_at, None
            assert pc == entered, (
                f"a run entered at {entered:#x}, one of its watch's stops, first stopped at {pc:#x}: it was entered "
                f"elsewhere")
            return self.first - {pc}    # entered, not called: no arrival — and a stop may not arm the PC it stands at
        if self._trap_returns_to is not None:
            assert pc == self._trap_returns_to, (
                f"the run took the trap at {pc:#x} INSIDE the trap at {self._marked_trap:#x}, and is marked at both: an "
                f"arrival there counts in a run marked at {pc:#x} alone and not in this one, so a `trap_taken` "
                f"ordinal at it names two different arrivals — cut the session at one of the two handlers only")
            self._trap_returns_to = None
            return self.first
        if not self._in_call and pc in self._inside:
            raise Blocked(f"the run reached the dispatcher (dsptch, {pc:#x}) outside any door call, after "
                          f"{self.calls}: the routine it was entered at is the event layer's own, and "
                          f"{SWITCHES_AT_THE_DISPATCHER}")
        if not self._in_call and pc not in self.entries:
            self.marks.arrived(pc, self.calls, memory)
            self._marked_trap, self._trap_returns_to = pc, case.long_in(memory, sp + EXCEPTION_FRAME_PC)
            # Inside a marked trap only its return is an arrival — and the OTHER handlers the run is marked at stay
            # armed, so that one of them nested in this one is refused by name (above) rather than left uncounted.
            return frozenset({self._trap_returns_to}) | (self.marks.traps - {pc})
        if not self._in_call:
            back = case.long_in(memory, sp)
            assert back in self.returns or self._called_by_our_build(pc, back), (
                f"the run reached the door's entry {pc:#x} from {back:#x} — not a door call")
            if self.calls in self._delivered:
                found, wrote = self._delivered[self.calls]
                _vet_found(memory, found, f"door call {self.calls} ({pc:#x})")
                _lay(memory, wrote)
            if self.marks:
                self.marks.arrived(self.entry_at(pc), self.calls, memory)
            self._opened(pc, sp, memory)
            self.calls += 1
            self._in_call, self._open_entry = True, self.entry_at(pc)
            return frozenset({back}) | self._inside
        if pc in self._inside:
            raise Blocked(f"the run reached the dispatcher (dsptch, {pc:#x}) inside door call {self.calls - 1}: "
                          f"{SWITCHES_AT_THE_DISPATCHER} — nothing it waits for was delivered to it (an interrupt "
                          f"missing, or laid at another call)")
        self.answers.append((self._open_entry, _d0_at_the_stop(),
                             NO_IMAGE_TAKEN if self.images is NO_IMAGE_TAKEN else image_pages(memory, self.images)))
        self._closed()
        self._in_call = False
        return self.first


class Ended(Exception):
    """A watched run reached a PC its watch ends it at (`EntryStops`)."""


class EntryStops:
    """A WATCH (`rom_bench.watched`, through `run_watched`) AT ARBITRARY ROM ENTRIES — `entries`, any routines of the
    ROM: THE ROM'S OWN CALL, AT THE MOMENT IT MAKES IT. The run stops at each entry's first instruction, where
    `arrived(pc, sp, memory)` is called — the frame its caller pushed above the return address at `sp`, the memory as
    every routine before it left it. `DoorStops` is the same idea keyed to the door's entries and their Line-F
    return sites, with ordinals, deliveries and marks; this one asks nothing of who calls.

    WHEN AN ENTRY IS WATCHED AGAIN — what a caller must know. A stop may not arm the PC it stands at (the run would
    stop there again having run nothing), so the entry arrived at is left out of the NEXT stops, its call's return
    address taken in its place; every stop after that one arms every entry again. So:
      * an entry is unwatched from its arrival to the run's next stop — its own return, or another entry reached
        inside it. A RECURSIVE entry's inner arrival is seen only if another stop came between: watch none;
      * an entry whose caller never comes back to that return address — the call PARKS its process — stays unwatched
        until some other stop: another process's call of the same entry before any is NOT seen.
    Nothing here can tell either from a call that was never made. What holds a watched run to what it saw is the
    sequence its scenario DECLARES (`aes_evasync.SCENARIOS`: the arrivals, in order, asserted) — a missed arrival is a
    declared one that did not come.

    The run ENDS (`Ended`, raised out of the run) at any PC of `ends`, `ended(memory)` called first — once it has
    passed `once_past`, when one is named: a run that ends where it began (the dispatcher's loop, back in it after a
    process has parked). A run with no end named returns. REFUSED BY NAME: a gate that is itself an end, and a run
    that would end having executed nothing — an end that is the run's own entry, with no gate before it: the memory
    `ended` is handed would be the machine as it was STAGED, which no ROM instruction made."""

    def __init__(self, entries, arrived, ends=(), ended=None, once_past=None):
        self._entries, self._ends, self._gate = frozenset(entries), frozenset(ends), once_past
        assert once_past not in self._ends, (
            f"a watch that ends at {once_past:#x} only once past {once_past:#x} ends at its gate: the first stop there "
            f"would open the gate and the second end the run, nothing run between")
        self._arrived, self._ended = arrived, ended
        self._watched = self._entries | (self._ends if once_past is None else {once_past})
        self.first = self._watched

    def _next_stops(self, pc, stops):
        """`stops`, the stops a stop at `pc` answers — never `pc` itself: the kit's watch loop would stop there again
        at once, for ever (no instruction run, so no budget spent)."""
        assert pc not in stops, f"a watch stopped at {pc:#x} may not arm {pc:#x}: the run would never leave it"
        return stops

    def stopped(self, pc, sp, memory):
        if pc == self._gate:
            self._gate, self._watched = None, self._entries | self._ends
        elif pc in self._ends:
            assert _instructions_run(), (
                f"the watched run would END at {pc:#x} having executed nothing — an end that is the run's own entry: "
                f"name what it must pass first (`once_past`), or the machine handed on is the one that was staged")
            if self._ended is not None:
                self._ended(memory)
            raise Ended
        if pc not in self._entries:
            return self._next_stops(pc, self._watched)
        self._arrived(pc, sp, memory)
        return self._next_stops(pc, (self._watched - {pc}) | {case.long_in(memory, sp)})


def _vet_found(memory, found, where):
    """`memory` holds `found` (`{address: bytes}`) at every address outside what neither shore compares
    (`_NOT_COMPARED`): else refused by name."""
    differ = [at + offset for at, data in found.items() for offset, value in enumerate(data)
              if at + offset not in _NOT_COMPARED and memory[at + offset] != value]
    assert not differ, (
        f"the event door: the run's memory differs from the ROM's where an interrupt is delivered at {where}, at "
        f"{', '.join(f'{at:#x}' for at in differ[:COMPARED_DIFFERENCES_SHOWN])} — the delivery would erase it")


def _lay(memory, wrote, lays_the_mask_word=True):
    """`wrote` (`{address: bytes}`) laid into `memory` — the Line-F mask word's bytes left out unless
    `lays_the_mask_word`."""
    for at, data in wrote.items():
        for offset, value in enumerate(data):
            if lays_the_mask_word or at + offset not in LINE_F_MASK_BYTES:
                memory[at + offset] = value


def lay(memory, wrote, lays_the_mask_word=True):
    """`_lay`, for a battery that lays a delivery itself (the scheduler model's idle hook)."""
    return _lay(memory, wrote, lays_the_mask_word)


def vet_found(memory, found, where):
    """`_vet_found`, for the same."""
    return _vet_found(memory, found, where)


def run_watched(memory, entry, watch, io_seed=None, budget=None):
    """The ROM's own `entry` run over `memory` — its frame at `abi.FIRST_ARG`, where `emu.run` leaves it — by the bench's
    door, entered as `emu.run` enters it (`rom_bench.original_entered`: its register file, no chip declared) and
    WATCHED by `watch` (`DoorStops`, `rom_bench.watched`): the run's result, or None for a run the watch ended where it
    blocks (`Blocked`). The same run as `emu.run`'s, instruction for instruction, held to what a derivation is — under
    its budget by DERIVATION_MARGIN (DERIVATION_INSNS, or the `budget` its row declares: `_budget_of`), refused if the
    model could not serve it; `memory` is its own, written in place. Vetted HOWEVER the run ends: a watch that ends it
    early by raising (a run stopped at an entry, `_AtTheEntry`) leaves a prefix a case may build on, held to the same
    refusals and margin; a run that ENDED — returned, or blocked — is held to its declared budget from above too
    (`_vet_not_stale`)."""
    insns = _budget_of(entry, budget)
    try:
        result = rom_bench.original_entered(memory, entry, watch.first, io_seed=io_seed, max_insns=insns)
        result = rom_bench.watched(result, entry, watch, memory, max_insns=insns)
    except Blocked:
        result = None
    finally:
        rom_bench.vet_the_run_just_made(f"the ROM's watched run of {entry:#x}")
        _vet_the_margin(entry, _instructions_run(), budget)
    _vet_not_stale(entry, _instructions_run(), budget)
    return result


def _instructions_run():
    """The instructions the bench run just ended — at its end or at the stop a watch raised in — has spent: the
    oracle's running total (what each segment's result reports), read because a run a watch ended by raising hands
    back no result."""
    return emu._LIB.osh_num_insns()


def run_cost():
    """`{"insns", "cycles"}`: what the bench run in flight has spent so far — the oracle's running totals, read at a
    stop (a slice's mark, `Marks`) or once the run has ended."""
    return {"insns": _instructions_run(), "cycles": emu._LIB.osh_num_cycles()}


def rom_watched(name, arguments, pokes, io_seed=None, *, blocks=False, budget=None, left_out_beside=()):
    """The ROM's own `addrs.<name>`, run over `pokes` with the frame `arguments`, WATCHED at the door's entries
    (`_watched_through`, nothing delivered): `(calls, memory, returned)` — what it hands each entry it calls, in order
    (`handed_at`: each frame where its Line-F word left it, read through its pointers as it stands at the call), the
    memory it left (at the entry of the blocking call, for one that blocks), and whether it returned (False: `blocks`,
    and it reached the dispatcher inside a call). `budget`: the run's own, declared (`_budget_of`)."""
    calls, memory, result = _watched_through(name, arguments, pokes, {}, io_seed=io_seed, blocks=blocks, budget=budget,
                                             left_out_beside=left_out_beside)
    return calls, memory, result is not None


def rom_handed(name, arguments, pokes, io_seed=None, budget=None, left_out_beside=()):
    """What the ROM's own `addrs.<name>` hands each door entry it calls, in order (`rom_watched`) — a `Calls`: with
    what each call answered and the memory where it came back (`left_out_beside`: `image_pages`')."""
    return rom_watched(name, arguments, pokes, io_seed, budget=budget, left_out_beside=left_out_beside)[0]


def _vet_the_frames_handed(name, arguments, pokes, io_seed, budget=None):
    """The door calls the candidate made (`HANDED`) are the ROM's own, frame for frame (`rom_handed`) — and the
    answers its twins handed back (`ANSWERED`) the ROM routines' (`vet_the_answers_handed_back`)."""
    ours, the_rom_s = list(HANDED), rom_handed(name, arguments, pokes, io_seed, budget, left_out_beside=_LEFT_OUT_BESIDE[0])
    assert ours == the_rom_s, (
        f"{name}: the door was handed {ours} where the ROM's own run hands {the_rom_s} — a frame the event layer's "
        f"answer did not show")
    vet_the_answers_handed_back(name, list(ANSWERED), the_rom_s.answers)


def begin_a_door_run(left_out_beside=()):
    """A door case's run BEGINS: nothing handed, nothing answered yet (`HANDED`, `ANSWERED`) — and
    `left_out_beside`, the windows its road leaves out of every page of an image taken at a return (`image_pages`:
    real GEMDOS's three; the ROM's watched run of the case is told the same)."""
    HANDED.clear()
    ANSWERED.clear()
    _LEFT_OUT_BESIDE[:] = [left_out_beside if left_out_beside is NO_IMAGE_TAKEN else tuple(left_out_beside)]


# ---- what differs by nature: the BIOS trap's saved registers -------------------------------------------------------
# ---- A LAYER'S OWN RUNS, WATCHED AT ITS ROUTINES' ENTRIES: the one family the event layer's batteries derive by --------
# THE LISTS', THE WAITS' AND THE INPUT LAYER'S MACHINES ARE ALL ARRIVALS (`aes_evasync`, `aes_evlib`, `aes_evinput`): the
# ROM's own run of something the machine does, stopped at each entry of the routines a battery proves (`EntryStops`),
# the machine there and the frame the caller pushed kept. What differs between the three is DATA — which routines,
# what a machine leaves out, which argument points into its caller's stack and where it is restaged, which end a run
# may return before — so it is one `Layer` each, and one `Scenarios` for what each declares of its runs.
# (`LayerArrival`, not `Arrival`: that name is a marked run's timeline entry's, further down — and a kept derivation's
# answer names its types by where they live.)
LayerArrival = namedtuple("LayerArrival", "name arguments machine")     # a routine reached: its frame, the machine there
Watched = namedtuple("Watched", "arrivals machine")                      # a run: its arrivals in order, the machine it left


def before(arrival):
    """The machine an arrival is at, as an image: what a case of the family reads its routine's start from."""
    return make_image(arrival.machine)


def fork_queue(image):
    """The entries queued for forker, oldest first: `(code, data)` each — the fork function, its longword."""
    head, count = case.word_in(image, aes.AES_FORK_HEAD), case.word_in(image, aes.AES_FORK_COUNT)
    entries = []
    for index in range(count):
        at = aes.AES_FORK_QUEUE + (head + index) % aes.AES_FORK_ENTRIES * aes.FORK_ENTRY_BYTES
        entries.append((case.long_in(image, at + aes.FORK_CODE), case.long_in(image, at + aes.FORK_DATA)))
    return entries


def button_change(buttons, clicks):
    """The queue entry of a button change, as b_delay queues it: bchange, over the buttons and the clicks."""
    return addrs.AES_ROM_BCHANGE, aes.words_long(buttons, clicks)


def scenario_of_a_case(params):
    """`conftest.py`'s `collected_with(by=...)` for a battery of arrivals: a case's group is its arrival's scenario
    (one ROM run derives every arrival of it), None for a case that takes no arrival."""
    return (params.get("arrival") or (None,))[0]


class _LayerWatch:
    """The watch of ONE run at a layer's entries: a `LayerArrival` kept at each, the run ENDED (`Ended`) at one of `ends`
    (once past `once_past`) — or at the `stop_at[1]`-th arrival at the routine `stop_at[0]`, for a run nothing else
    ends (an idle that would poll for ever): the machine at the end kept."""

    def __init__(self, layer, ends=(), once_past=None, stop_at=None):
        self._layer, self._stop_at, self._seen = layer, stop_at, 0
        self.arrivals, self.at_the_end, self.stopped_by_count = [], [], False
        self.watch = EntryStops(layer.entries, self._arrived, ends, self._ended, once_past)

    def _ended(self, memory):
        self.at_the_end.append(self._layer.machine_of(memory))

    def _arrived(self, pc, sp, memory):
        if self._stop_at and self._layer.entries[pc] == self._stop_at[0]:
            self._seen += 1
            if self._seen == self._stop_at[1]:
                self._ended(memory)
                self.stopped_by_count = True
                raise Ended
        self.arrivals.append(self._layer.arrival_at(pc, sp, memory))

    def result(self):
        return Watched(tuple(self.arrivals), self.at_the_end[0] if self.at_the_end else None)


class Layer:
    """THE ROUTINES ONE BATTERY PROVES (`routines`: their `addrs` names, each declared — `aes.declare_alcyon`), as a
    watch of the ROM's own run needs them: `entries` (`{address: name}`), `frames` (each one's Alcyon frame, a
    `struct.Struct`), and
      * `left_out` — what no machine of the layer keeps of a run (`as_pokes`' `without`): the stack band, every run's
        own frames, which each case stages afresh; a layer adds what its runs are handed for themselves alone;
      * `restaged(name, arguments, memory, machine)` -> `(arguments, machine)` — for AN ARGUMENT THAT POINTS INTO ITS
        CALLER'S STACK (a QPB that is ap_rdwr's own frame, a rectangle that is w_setactive's local): the band a
        machine keeps nothing of, so the bytes are laid in the layer's own band and the pointer re-aimed — the one
        argument of an arrival that is not the ROM's own, by nature: the routine reads the same bytes at another
        address;
      * `may_return_before` — the ends a run may RETURN without reaching (dsptch, for a call made "to its return or
        to the dispatcher"); a run that returns before any other end it was given is refused by name."""

    def __init__(self, routines, *, left_out=case.STACK_BAND, restaged=None, may_return_before=()):
        self.routines = tuple(routines)
        self.entries = {getattr(addrs, name): name for name in self.routines}
        self.frames = {name: struct.Struct(">" + "".join(vdi.FRAME_FORMATS[argtype] for argtype in vdi.frame_argtypes(name)))
                       for name in self.routines}
        self._left_out, self._restaged, self._may_return_before = left_out, restaged, frozenset(may_return_before)

    def machine_of(self, memory):
        """`memory` as pokes over the snapshot (`as_pokes`): every byte of RAM that differs from it, but the run's own."""
        return as_pokes(memory, without=self._left_out, upto=addrs.ST_RAM_BYTES)

    def frame_of(self, name, arguments):
        """The Alcyon frame of `addrs.<name>` for `arguments`: a word the signed word it is, a long its 32 bits."""
        return self.frames[name].pack(*(value & aes.LONG_MASK if argtype == vdi.LONG_ARG else aes.signed(value)
                                        for argtype, value in zip(vdi.frame_argtypes(name), arguments, strict=True)))

    def arrival_at(self, pc, sp, memory):
        """The `LayerArrival` of a run stopped at the entry `pc`: the frame its caller pushed above the return address at
        `sp`, the machine there."""
        name = self.entries[pc]
        frame = self.frames[name]
        arguments = frame.unpack(bytes(memory[sp + LONG_BYTES:sp + LONG_BYTES + frame.size]))
        machine = self.machine_of(memory)
        if self._restaged is not None:
            arguments, machine = self._restaged(name, arguments, memory, machine)
        return LayerArrival(name, arguments, machine)

    def watch(self, ends=(), once_past=None, stop_at=None):
        """A watch of one run at the layer's entries (`_LayerWatch`: `.watch` for the run, `.arrivals`, `.result()`)."""
        return _LayerWatch(self, ends, once_past, stop_at)

    def watched(self, pokes, entry, ends=(), frame=b"", once_past=None, stop_at=None, must_end=False):
        """The ROM's `entry` over `pokes` (its `frame` where a `jsr` leaves it), WATCHED AT THE LAYER'S ENTRIES until
        it reaches one of `ends` (after `once_past`, when named), or its `stop_at` arrival (`(routine, nth)`), or
        returns: a `Watched` — every arrival, in order, and the machine at the end (for a run that returned, the
        memory it left). `must_end`: the `stop_at` arrival is only a BOUND (a loop that would spin for ever), and
        reaching it is refused by name."""
        memory = make_image(merge_pokes(pokes, {abi.FIRST_ARG: frame} if frame else None))
        seen = self.watch(ends, once_past, stop_at)
        try:
            run_watched(memory, entry, seen.watch)
        except Ended:
            assert not (must_end and seen.stopped_by_count), (
                f"the run of {entry:#x} reached none of its ends before its {stop_at[1]}th arrival at {stop_at[0]}: "
                f"after {[short_name(arrival.name) for arrival in seen.arrivals]}")
            return seen.result()
        unreached = frozenset(ends) - self._may_return_before
        assert not unreached and not stop_at, (
            f"the run of {entry:#x} returned before it reached "
            f"{', '.join(f'{end:#x}' for end in sorted(unreached)) or 'its stopping arrival'}")
        return Watched(tuple(seen.arrivals), self.machine_of(memory))


def short_name(routine):
    """A routine's `addrs` name as a case's id and a message spell it: `AES_ROM_B_CLICK` -> `b_click`."""
    return routine.removeprefix(ENTRY_PREFIX).lower()


class Scenarios:
    """A BATTERY'S SCENARIOS: `declared` — `{name: the arrivals its run DECLARES, in order}`, what the cases are
    parametrized from — and `run_of(name)`, the ROM's run of one (a derivation: `derived.kept`), whose arrivals
    (`arrivals_of(what it answers)`: the answer itself, or a `Watched`'s) are HELD to the declaration the first time a
    process asks: a missed arrival is a declared one that did not come. Made once per process, like every machine."""

    def __init__(self, declared, run_of, arrivals_of=lambda made: made):
        self.declared, self._run_of, self._arrivals_of, self._made = dict(declared), run_of, arrivals_of, {}

    def scenario(self, name):
        """What the scenario `name`'s run answers, its arrivals held to the sequence it declares."""
        if name not in self._made:
            made = self._run_of(name)
            arrived = tuple(arrival.name for arrival in self._arrivals_of(made))
            assert arrived == self.declared[name], (
                f"{name}: the ROM's run arrives at {[short_name(each) for each in arrived]}, "
                f"declared {[short_name(each) for each in self.declared[name]]}")
            self._made[name] = made
        return self._made[name]

    def cases(self, *routines):
        """`(scenario, nth)` for every declared arrival at one of `routines` (every routine, by default)."""
        return [(name, nth) for name, arrivals in self.declared.items() for nth, routine in enumerate(arrivals)
                if not routines or routine in routines]

    def case_id(self, pair):
        name, nth = pair
        return f"{name}: {nth} {short_name(self.declared[name][nth])}"

    def arrival(self, name, nth):
        return self._arrivals_of(self.scenario(name))[nth]

    def nth_of(self, name, routine, which=0):
        """The index of the `which`-th declared arrival at `routine` in the scenario `name`."""
        return [nth for nth, declared in enumerate(self.declared[name]) if declared == routine][which]

    def at(self, name, routine, which=0):
        """The `which`-th arrival at `routine` of the scenario `name`."""
        return self.arrival(name, self.nth_of(name, routine, which))


# WHERE THE KEYBOARD POLL'S TRAP SAVE LIES IS THE CAPTURE'S, NOT A NUMBER: `savptr` as the boot snapshot holds it. The
# ROM's boot sets it to the save area's TOP (`move.l #$93a,savptr(a5)` at $fc02f2: BOOT_SAVPTR_IMMEDIATE its
# operand) and every BIOS trap in flight holds it one frame lower — and the snapshot is taken at a vertical blank
# that interrupts the desktop's idle loop AT WHATEVER PHASE it is in (`tools/boot_snapshot.py`): between two polls
# (savptr at the top, the save at $90c..$93a) or INSIDE one (a frame lower, $8de..$90c — measured, two captures of
# the same boot). Every run staged over the snapshot starts with that `savptr`, on both shores.
BOOT_SAVPTR_IMMEDIATE = 0xfc02f4
SAVE_AREA_TOP = case.long_in(BASE_IMAGE, BOOT_SAVPTR_IMMEDIATE)
SNAPSHOT_SAVPTR = case.long_in(BASE_IMAGE, addrs.SYSVAR_SAVPTR)
assert SNAPSHOT_SAVPTR <= SAVE_AREA_TOP and (SAVE_AREA_TOP - SNAPSHOT_SAVPTR) % addrs.TRAP_SAVE_FRAME_BYTES == 0, (
    f"the snapshot's savptr ({SNAPSHOT_SAVPTR:#x}) is no whole number of trap frames below the save area's top "
    f"({SAVE_AREA_TOP:#x}, the ROM's own at boot)")
TRAP_SAVE_AT = SNAPSHOT_SAVPTR - addrs.TRAP_SAVE_FRAME_BYTES
TRAP_SAVE_DROP = ((TRAP_SAVE_AT, TRAP_SAVE_AT + addrs.TRAP_SAVED_REGISTERS * LONG_BYTES,
                   "the BIOS trap's saved D3-D7/A3-A7 under the event layer's keyboard poll: the registers it was taken "
                   "with — the caller's frame, depth and whatever it holds in them, which a C caller's are not"),)
# ...and the rest of that trap's save frame, above the ten registers: the exception frame's PC and SR as the BIOS's
# dispatcher copies them. The PC is the VDI's own `trap #13` return site, which the reconstructed VDI — calling the
# BIOS's core, no trap taken — never parks; the SR is the status register the VDI was called with. Dropped only
# under a C that POLLS (chkkbd, mchange while a recording plays, and whatever calls them: the input's leaf battery,
# ev_multi's — and, ev_multi being rebound, every door case).
TRAP_FRAME_DROP = ((TRAP_SAVE_AT + addrs.TRAP_SAVED_REGISTERS * LONG_BYTES, TRAP_SAVE_AT + addrs.TRAP_SAVE_FRAME_BYTES,
                    "the PC and SR of the keyboard poll's BIOS trap, as its dispatcher saves them: the VDI's own trap "
                    "site and its caller's status register — a host VDI takes no trap"),)
TRAP_FRAME_BYTES = frozenset(at for lo, hi, _why in TRAP_FRAME_DROP for at in range(lo, hi))
DOOR_DROPS = aes.LINE_F_MASK_WINDOW + TRAP_SAVE_DROP + (TRAP_FRAME_DROP if polls_in_c() else ())


# ---- ...and the scheduler's status-register SAVE WORDS -----------------------------------------------------------------
# The scheduler parks the status register in a word of RAM round each of its interrupt-mask brackets (`aes/switch.h`).
# What lands there is the SR its caller ran under — the condition codes of the last instruction before the bracket
# among them — which is the caller's CPU state: a C caller's is not the ROM caller's (on target), and the host has
# none to store. ONE TABLE, `{save word: why it is dropped}`: a word is dropped BY NAME, only where the ROM's run
# stores it — so no battery lists the routines that reach a bracket (a `dropped_windows` entry on a case whose run
# never stores the word drops nothing) — and at Tier 3 with the undropped companion every drop needs. The
# dispatcher's own (savestate / switchto, AES_SR_DISPATCH) is here with the switch's host MODEL (`aes/evdisp.h`): a
# core that stops at dsptch never reaches it — the ROM's run to dsptch stores none either, so nothing is dropped —
# and one run through the model stores no word where the ROM's savestate and switchto each store theirs
# (`test_aes_event.py` holds the table to the header's save words, every one).
SR_DROPS = {
    aes.AES_SR_DISPATCH: "the dispatcher's SR save word: the status register savestate was entered under and "
                         "switchto resumes with — the caller's CPU state (`aes/switch.h`); the host model of the "
                         "switch stores nothing there",
    aes.AES_SR_PSETUP: "psetup's SR save word: the status register of whoever called it, parked round its stores "
                       "(`aes/switch.h`); the C stores nothing there off target and its own caller's on it",
    aes.AES_SR_SPL: "spl7_save's SR save word: the status register of whoever asked for the mask (tchange and adelay "
                    "re-arming the tick), parked until spl_restore (`aes/switch.h`); the C stores nothing there off "
                    "target and its own caller's on it",
}


def sr_drops(*words):
    """The `dropped_windows` of the SR save `words` (every one of `SR_DROPS`, when none is named)."""
    return tuple((word, word + aes.WORD_BYTES, SR_DROPS[word]) for word in (words or SR_DROPS))


SR_PSETUP_DROP = sr_drops(aes.AES_SR_PSETUP)
SR_SAVE_BYTES = frozenset(at for lo, hi, _why in sr_drops() for at in range(lo, hi))


def stored_spans(window, stored):
    """`window` (`(lo, hi, why)`) cut to the runs of bytes of it in `stored` — what a Tier 3 drop may name: a byte
    the ORIGINAL's run wrote, and no other (`rom_bench.vet_dropped`)."""
    lo, hi, why = window
    spans, start = [], None
    for address in range(lo, hi + 1):
        inside = address < hi and address in stored
        if inside and start is None:
            start = address
        elif not inside and start is not None:
            spans.append((start, address, why))
            start = None
    return tuple(spans)


def settled_in_windows(machine, writes, staged, dropped=None):
    """A PRICED ROW's bytes that differ by nature, SETTLED — THE ONE SPELLING, for a word and for a window alike:
    `(pokes, drops)`. `machine` with EVERY BYTE of the windows `staged` (`(lo, hi, why)` each) that the ROM's run
    which made `writes` STORED, staged at the value that run left — the run reads none of them before it stores it,
    so it rewrites each with itself, and a differential of the row's machine with nothing dropped then holds a C
    that stores none (the row's companion). And the windows `dropped` (those staged, unless a row drops fewer: what
    its own build stores as the ROM does stays compared) cut to the bytes that run stored, in their order: the
    row's named Tier 3 drops. A byte the run left alone is neither staged nor dropped: the row's compare holds it."""
    left = {at: bytes([writes[at]]) for lo, hi, _why in staged for at in range(lo, hi) if at in writes}
    drops = tuple(span for window in (staged if dropped is None else dropped) for span in stored_spans(window, writes))
    return (merge_pokes(machine, left) if left else machine), drops


def settled_where_stored(machine, writes, words):
    """...for WORDS (`(the word's address, its named drop)`: the Line-F mask word, an SR save word): each one the run
    STORED staged and dropped, in `words`' order; a word it left alone neither. A WORD IS SETTLED WHOLE: the drop's
    reason names a `move.w` (the handler's mask store, a status register parked) — a run that stored ONE BYTE of
    such a word did something else there (another variable's byte store, a wild pointer), which no reason here
    names: REFUSED by name, a finding to rule on, never staged and dropped in silence."""
    for word, _drop in words:
        stored = [at for at in range(word, word + aes.WORD_BYTES) if at in writes]
        assert len(stored) in (0, aes.WORD_BYTES), (
            f"the ROM's run stored HALF of the word at {word:#x} that differs by nature (the byte at "
            f"{stored[0]:#x} alone): not the word store its drop names — rule on it before any row settles it")
    return settled_in_windows(machine, writes, tuple(window for _word, drop in words for window in drop))


# ...and the two a wait's or an input routine's row settles: the Line-F mask word, and spl7_save's SR save word.
MASK_WORD_AND_SPL = ((aes.AES_LINEF_MASK_WORD, aes.LINE_F_MASK_WINDOW), (aes.AES_SR_SPL, sr_drops(aes.AES_SR_SPL)))
# EVERY WORD THAT DIFFERS BY NATURE, for a registrar that names no routine: the mask word, then each SR save word of
# the table — whichever of them a row's ROM run stores is settled, the rest left compared.
WORDS_BY_NATURE = ((aes.AES_LINEF_MASK_WORD, aes.LINE_F_MASK_WINDOW),) + tuple((word, sr_drops(word)) for word in SR_DROPS)
# What an event-layer core that POLLS is compared outside of, where the ROM's run stores it: the mask word, the BIOS
# trap's saved registers and its frame's PC and SR (a host VDI takes no trap), the SR save words.
EVENT_LAYER_DROPS = aes.LINE_F_MASK_WINDOW + TRAP_SAVE_DROP + TRAP_FRAME_DROP + sr_drops()
SERVED_IN_A_FORK = (isr.CALL_VECTOR_SYMBOL, isr.REGISTERS_HOOK_SYMBOL)


# ---- A FORK FUNCTION'S ADDRESS IN THE QUEUE IS A CODE VALUE --------------------------------------------------------------
# b_click, b_delay, chkkbd (and mchange, through b_delay) queue a fork function by an IMMEDIATE — the ROM's address in
# the ROM, the function's own entry in a build linked elsewhere (`aes/evfork.h`). The host core stores the ROM's, and
# Tier 1 compares it; at Tier 3 a code longword is RELOCATED between the shores and compared exactly, never dropped
# (`bench/tier3.py`: the queue's, a recording's, the glue's). ONE SPELLING of where the queue's lie, for that
# relocation and for every vet of a queued code: each entry's code longword, and the entry of OUR build that stands
# for each ROM fork function.
FORK_ENTRIES_AT = range(aes.AES_FORK_QUEUE, aes.AES_FORK_QUEUE + aes.AES_FORK_ENTRIES * aes.FORK_ENTRY_BYTES,
                        aes.FORK_ENTRY_BYTES)
FORK_CODE_SLOTS = tuple(entry + aes.FORK_CODE for entry in FORK_ENTRIES_AT)
FORK_ENTRY_SYMBOLS = {addrs.AES_ROM_KCHANGE: "aes_kchange_fork", addrs.AES_ROM_BCHANGE: "aes_bchange_fork",
                      addrs.AES_ROM_MCHANGE: "aes_mchange_fork", addrs.AES_ROM_TCHANGE: "aes_tchange_fork"}
# ...and THE GLUE THE BUILD INSTALLS ITSELF (`gsxif.c`: gsx_setmb_aes hands the VDI the ROM's two off target and the
# blob's own entries on it) — a code address in compared RAM as a queue entry's code is — and the longwords of the
# machine that hold one: the VDI's two vectors, the AES's contrl[7..8] it was handed in, and — where a glue was
# installed already — what a vex call DISPLACED (contrl[9..10], then the AES's two save longwords).
GLUE_ENTRY_SYMBOLS = {addrs.AES_ROM_BUTTON_GLUE: "aes_rom_button_glue", addrs.AES_ROM_MOTION_GLUE: "aes_rom_motion_glue"}
GLUE_CODE_SLOTS = (vdi.field("LINEA", "USER_BUT").at, vdi.field("LINEA", "USER_MOT").at, aes.AES_GSX_CONTRL_PTR,
                   aes.AES_GSX_CONTRL_PTR2, aes.AES_OLD_BUTTON, aes.AES_OLD_MOTION)
# THE RELOCATION REGISTRY: every place of the machine that holds A CODE ADDRESS OF THE BUILD, declared ONCE, here,
# beside the slots — `what` it is, the longwords it lies in (`slots`), the entry of our build that stands for each
# ROM routine (`symbols`), and whether our image is mapped AT A RUN'S ENTRY too (`at_entry`) or only where it ends.
# Tier 3 reads nothing else (`bench/tier3.py`, `code_relocations`): our image at a run's entry, the image it leaves,
# a delivery laid into it and a slice's mark are all mapped through it.
#   * the fork queue's codes ARE mapped at entry: our forker `jsr`s what an entry holds;
#   * the glue's ARE NOT: a vex call hands what it DISPLACED to wherever its caller's contrl lies — a displaced value
#     travels out of the registry's slots — so our image at entry is the ROM-made machine as it is.
RelocatedCode = namedtuple("RelocatedCode", "what slots symbols at_entry")
FORK_CODES = RelocatedCode("a fork function's code in the fork queue", FORK_CODE_SLOTS, FORK_ENTRY_SYMBOLS, True)
# ...and THE ROUTINE THAT DRAWS NOTHING (justretf), which a playback hands the VDI twice (ap_tplay: vex_curv, vex_motv)
# and gets back, displaced, when it puts the VDI's own back — in contrl[9..10] where appl_tplay returns. The glues'
# own table stays the two glues (the dispatcher's battery and the interrupts' hold it to them).
HANDED_ENTRY_SYMBOLS = {**GLUE_ENTRY_SYMBOLS, addrs.AES_ROM_JUSTRETF: "aes_rom_justretf"}
GLUE_CODES = RelocatedCode("a glue's address handed to the VDI", GLUE_CODE_SLOTS, HANDED_ENTRY_SYMBOLS, False)
# ...and THE GEMDOS GLUE'S OWN TEXT, NAMED IN RAM (band 5: pgmld, which ships as the ROM's instructions —
# `src/aes/gemdosif.S`): `__DOS` parks the return address it was reached with, and pgmld reaches it by `bsr` from its
# own body, so AES_TRAP1_RETURN holds A SITE INSIDE pgmld — `$fe39ce` / `$fe39fa` in the ROM, the `.S`'s own in a
# build; the command tail it hands Pexec is the address of a zero word of its own text (`$fe39b4`); and `__DOS`
# leaves by `jmp (a0)`, the site in A0. Mapped at a run's EXIT alone (a machine holds none of them before pgmld runs).
# WHICH RUNS ARE MAPPED: those that can PARK a text site — a `.S` entry's own (`TEXT_SITE_ENTRIES`) and a C CALLER's
# that reaches the `.S` through its thunk on the shipped blob (`TEXT_SITE_CALLERS`). NONE OF THE SECOND KIND EXISTS
# YET: pgmld has no C caller, so no thunk is generated for it and `aes_pgmld` on the shipped blob is still the weak C
# twin (which parks the ROM's sites, as the data they are). ITS FIRST C CALLER IS THE ACCESSORY LOADER (sndcli,
# wave 3): its pair goes into `transcription.C_CALLERS_OF_TRANSCRIBED_CORES` — which `test_transcribed.py` holds to
# the build's own call graph, and from which `bench/shipped_glue.py` generates the thunk — and its name HERE
# (`test_aes_pgmld.py` reds while the two disagree).
# THE SLOTS: the one longword of the machine, and the longwords of a recording trap's ledger that can hold one — its
# recorder's module declares those where it lays the ledger out (`declare_text_site_slots`: `test/aes_gemdosif.py`,
# a module this one cannot import — it is built on this one — so the list is completed at ITS import, never a test
# module's).
TEXT_SITE_SYMBOLS = {addrs.AES_PGMLD_PEXEC_RETURN: "aes_rom_pgmld_pexec_return",
                     addrs.AES_PGMLD_MSHRINK_RETURN: "aes_rom_pgmld_mshrink_return",
                     addrs.AES_PGMLD_EMPTY_TAIL: "aes_rom_pgmld_empty_tail"}
TEXT_SITE_ENTRIES = ("aes_rom_pgmld",)  # the `.S` entries whose own run parks them
TEXT_SITE_CORE = "aes_pgmld"            # ...the C core a caller names to reach that `.S` (through its thunk)
TEXT_SITE_CALLERS = ()                  # ...and the C callers that do: none yet (above)
TEXT_SITE_SLOTS = [aes.AES_TRAP1_RETURN]
TEXT_SITES = RelocatedCode("a site of the GEMDOS glue's own text named in RAM", TEXT_SITE_SLOTS, TEXT_SITE_SYMBOLS, False)


def declare_text_site_slots(*slots):
    """Longwords of a recording trap's ledger that can hold one of `TEXT_SITE_SYMBOLS` (its recorder's module's)."""
    TEXT_SITE_SLOTS.extend(slot for slot in slots if slot not in TEXT_SITE_SLOTS)


CODE_RELOCATIONS = (FORK_CODES, GLUE_CODES, TEXT_SITES)
# ...and THE SCREEN MANAGER'S ENTRY (band 5 wave 2: ctlmgr in C). ictlmgr hands pstart ctlmgr's own address TWICE, by
# value — `$fe4a7e` the load address pstart keeps in the PD (p_ldaddr), `$fe4a8c` the code psetup pushes, under a status
# word, on the new process's own stack: the frame switchto's `rte` pops at its first entry — the ROM's ctlmgr in the
# ROM, the build's own entry (`aes_rom_ctlmgr`) in a build linked elsewhere. THE SLOTS are those two longwords of the
# machine: PD1's p_ldaddr, and the PC of psetup's frame at the top of PD1's stack (dead from its first entry on, and
# inside the stack span its frames then cover). Each is spelt here by the ROM's own constants (gem_main's table of PDs,
# the stack top it gives UDA1) and HELD to what every booted machine's own pointers say (`aes_boot.entry_slots`,
# `test_aes_boot.py`). Mapped at entry too: a machine whose screen manager is ours holds our entry there from its
# first entry on (`aes_boot.booted(..., ours=)`: THE TAKEOVER IS THIS MAPPING, applied where the ROM's boot stands at
# that `rte`, and nothing else is written but the blob).
# NOT YET AMONG `CODE_RELOCATIONS`: Tier 3 reads that tuple whole (`tier3.code_relocations` refuses a relocation no
# site maps), and no row runs on a machine that holds this one until the flip (slice D) — which adds it there with
# the site that maps it. Until then its one reader is the takeover.
ICTLMGR_LDADDR_AT, ICTLMGR_CODE_AT = 0xfe4a7e, 0xfe4a8c
MOVE_L_IMMEDIATE_TO_D7, PUSH_L_IMMEDIATE = 0x2e3c, 0x2f3c


def _immediate_at(at, opcode, what):
    """The longword the ROM's instruction at `at` — which must be `opcode` — carries by value."""
    found, immediate = struct.unpack_from(">HI", BASE_IMAGE, at)
    assert found == opcode, f"the ROM's instruction at {at:#x} is not {what}"
    return immediate


SCREEN_MANAGER_ROM_ENTRY = _immediate_at(ICTLMGR_CODE_AT, PUSH_L_IMMEDIATE, "ictlmgr's push of ctlmgr's address")
assert SCREEN_MANAGER_ROM_ENTRY == _immediate_at(ICTLMGR_LDADDR_AT, MOVE_L_IMMEDIATE_TO_D7, "ictlmgr's load of it"), (
    "ictlmgr hands pstart two addresses: the entry and the load address are no longer one routine")
SCREEN_MANAGER_ENTRY_SYMBOL = "aes_rom_ctlmgr"
SCREEN_MANAGER_ENTRY_SLOTS = (aes.SCREEN_MANAGER_PD + aes.PD_LDADDR, aes.AES_UDA1_STACK_TOP - LONG_BYTES)
SCREEN_MANAGER_ENTRY = RelocatedCode("the screen manager's entry", SCREEN_MANAGER_ENTRY_SLOTS,
                                     {SCREEN_MANAGER_ROM_ENTRY: SCREEN_MANAGER_ENTRY_SYMBOL}, True)
# EVERY RELOCATION DECLARED BESIDE THE TUPLE AND NOT IN IT, BY NAME: `{what: (why it is not mapped at Tier 3 yet, the
# slice that owes its site)}`. `test_aes_boot.py` holds that each `RelocatedCode` of this module is in the tuple or
# here — never neither — and that THIS IS EMPTY once any Tier 3 row runs on a takeover machine.
DECLARED_NOT_YET_MAPPED_AT_TIER3 = {
    SCREEN_MANAGER_ENTRY.what: ("no Tier 3 row runs on a machine whose screen manager is ours before the flip; "
                                "`tier3.code_relocations` refuses a relocation no site of its own maps",
                                "band 5 wave 2, slice D (the flip): bench/tier3.py"),
}
# THE DISPATCHER'S OWN STACK ($899a..$8c1a), which savestate moves to: what a Tier 3 row that drops it has put back
# on our shore (`bench/tier3.py`, `spans_put_back`), and the dispatcher's battery names its drop by.
DISPATCHER_STACK = (aes.header_constants("evdisp.h")["AES_DISPATCHER_STACK_BOTTOM"], aes.AES_DISPATCHER_STACK_TOP)


# ---- ONE REGISTRAR FOR A LEAF ROW OF THE EVENT LAYER -------------------------------------------------------------------
_SETTLED_AT = (frozenset(at for word, _drop in WORDS_BY_NATURE for at in range(word, word + aes.WORD_BYTES))
               | frozenset(range(addrs.SYSVAR_SAVPTR, addrs.SYSVAR_SAVPTR + LONG_BYTES)))


@kept_on_disk
def _stored_where_a_row_settles(name, arguments, machine):
    """ONE ROM run of `addrs.<name>` over `machine`, kept by content: what it stored of the bytes a row's settling
    reads — the words that differ by nature, and `savptr`."""
    image = make_image(aes.staged(name, vdi.as_signed(name, arguments), machine))
    _final, writes, _regs = _rom_run(image, getattr(addrs, name))
    return {at: value for at, value in writes.items() if at in _SETTLED_AT}


def settled(name, arguments, machine, *, polls=False):
    """`(pokes, drops)` of a DIRECT PRICED ROW of `addrs.<name>` over `machine`, from one run of the ROM's routine
    (two, where the first is found to take a BIOS trap): EVERY word that differs by nature which that run stores —
    the Line-F mask word, an SR save word (`SR_DROPS`) — STAGED at the value the run leaves and dropped at Tier 3 by
    name, for the row's companion to compare with nothing dropped; `savptr` moved into the stack band where the run
    takes the trap (`register`'s arrangement: the save lands where nothing compares it) — from the start with
    `polls`, for a routine a layer knows to poll (chkkbd, forker: the move is then made whether THIS run polls or
    not, one machine for all a routine's rows). THE ONE SPELLING of a leaf row's settling: no routine is named, the
    run says. A CODE ADDRESS the run queues or records (a fork function's) is no drop: Tier 3 relocates it and
    compares it exactly (`bench/tier3.py`), the host stores the ROM's."""
    if polls:
        machine = merge_pokes(machine, savptr_in_the_band())
    stored = _stored_where_a_row_settles(name, tuple(arguments), machine)
    if addrs.SYSVAR_SAVPTR in stored and not polls:
        return settled(name, arguments, machine, polls=True)
    return settled_where_stored(machine, stored, WORDS_BY_NATURE)


def register_row(label, name, arguments, machine, *, hook=None, through_line_f=False, priced=True, answer_compared=True,
                 polls=False):
    """ONE `VERIFIED_CASES` ROW of an event-layer routine `addrs.<name>` over `machine` with the frame `arguments`,
    named `<core>, <label>`: priced direct with what `settled` stages and drops, its companion (`aes.undropped`, with
    the routine's `hook` where it calls out) made for it; verified and unpriced through its Line-F call word
    (`through_line_f`), or with `priced` False (a row no blob can run yet, said beside it). A call that reaches the
    dispatcher registers no row: a row's run returns."""
    if through_line_f:
        return aes.register(label, name, arguments, machine, through_line_f=True, hook=hook,
                            answer_compared=answer_compared)
    row_name, entry = f"{routines.core_symbol(name)}, {label}", getattr(addrs, name)
    pokes, drops = settled(name, arguments, machine, polls=polls)
    staged = aes.staged(name, arguments, pokes)
    if not priced:
        return aes.ROWS.register(row_name, entry, staged, priced=False, answered=answer_compared)
    kept = qpb_addresses_a_return_leaves(name, arguments, pokes)
    if kept:
        # A QPB's ADDRESS LEFT IN A FREED EVB differs on EVERY pair of shores (the ROM routine's frame, the blob's,
        # the host slot): dropped at Tier 3 by name, and its companion is the host differential with THAT LONGWORD
        # ALONE left out — vetted there against the C's own image (`_companion_but_for_the_qpbs`).
        drops += tuple((at, at + LONG_BYTES, QPB_ADDRESS_WHY) for at in kept)
        companion = functools.partial(_companion_but_for_the_qpbs, name, arguments, pokes, hook, answer_compared)
    else:
        companion = functools.partial(aes.undropped, name, arguments, pokes, hook, None, answer_compared) if drops else None
    return aes.ROWS.register(row_name, entry, staged, dropped=drops, undropped=companion, answered=answer_compared)


def _companion_but_for_the_qpbs(name, arguments, pokes, hook, answer_compared):
    """A priced row's COMPANION where its run leaves a QPB's address in an EVB: the same machine as a differential
    with nothing dropped BUT those longwords — each vetted first against the C's own image at its return (a fork)."""
    kept = qpb_addresses_a_return_leaves(name, arguments, pokes)
    forked = core_in_a_fork(name, arguments, pokes, read_back=True, hook=hook)
    assert forked.returncode == 0, f"{name}: the row's C did not return in a fork ({forked.returncode}): {forked.stderr}"
    vetted = vetted_qpb_addresses(name, forked.image, kept, getattr(addrs, name))
    return aes.run_function(name, arguments, pokes, dropped_windows=vetted,
                            hook=hook, answer_compared=answer_compared, **aes.COMPANION_UNPOISONED)


def savptr_in_the_band():
    """`savptr` moved into the stack band, the save frame filled: the trap's save then lands where neither shore
    compares (`gemdos.machine`'s arrangement, without its trampoline slot)."""
    return {addrs.SYSVAR_SAVPTR: struct.pack(">I", gemdos.SAVPTR_AT),
            gemdos.FRAME_AT: bytes([gemdos.FRAME_FILL]) * addrs.TRAP_SAVE_FRAME_BYTES}


# ---- the run doors ---------------------------------------------------------------------------------------------------
# WHAT A DOOR USER'S DIFFERENTIAL DROPS where the ROM's run stores it: the door's two windows, and the SR save words —
# a rebound entry's twin stores none off target (`aes/switch.h`): where a door user's call reaches a mask bracket
# through a twin (ev_multi with a timer reaches adelay; forker, tchange after the ticks) the word differs by nature.
DOOR_RUN_DROPS = DOOR_DROPS + sr_drops()
# THE ATTRIBUTION PASS DOES NOT RUN through the door, MEASURED: it inverts every byte the ROM's run stored — the event
# layer's fork queue, its CDA, its EVBs' links — and the poisoned ROM run follows them: over every door row's machine
# (each the scheduler's own, `machine`) the poisoned run of ap_sendmsg, gr_stilldn and gr_watchbox alike did not
# return within 200,000 instructions. What stands in for it is staging — a door user's own stores land in words a
# battery stages STALE (a message buffer, an object's state set to what it is not), so a store the C skipped differs —
# and the frames each door call is handed, compared with the ROM's (`_vet_the_frames_handed`).
POISON_STEERS_THE_EVENT_LAYER = {"poison": False}


def run_event(name, arguments, pokes, *, drawing=False, io_seed=None, dropped_windows=None, objects=None,
              budget=None, cap=None, **kwargs):
    """`aes.run_function` of `addrs.<name>` over `pokes`, the event door bound (and the VDI's cores, `drawing`, and a
    walker's routines, `objects`: `door_hook`), the mask word, the trap's saved registers and the SR save words
    dropped where the ROM's run stores them (`DOOR_RUN_DROPS`), unpoisoned (above) — and every frame the candidate
    handed the door compared with the ROM's own call's. TWO RUNS, TWO LIMITS, each declared only where its run needs it and held both ways by name:
    `cap` — the differential's own (`emu.run`'s `max_insns`), for an original past DIFFERENTIAL_INSNS: the case's own
    number, or its battery's (`battery_cap`) — THE ONE DOOR a cap comes in by (`capped`, `vet_the_cap`: a raw
    `max_insns` is refused by name);
    `budget` — the derivation budget of the ROM's watched run of the frames (`_budget_of`), for a run past what
    DERIVATION_INSNS admits. A run that needs the budget needs the cap too, and the one number then serves both."""
    begin_a_door_run(NO_IMAGE_TAKEN if kwargs.get("through_line_f") else ())
    cap = budget if cap is None else cap
    dropped_windows = DOOR_RUN_DROPS if dropped_windows is None else dropped_windows
    result = capped_run(name, cap, kwargs, lambda **limits: aes.run_function(
        name, arguments, pokes, hook=door_hook(drawing, objects), io_seed=io_seed,
        dropped_windows=dropped_windows, **{**POISON_STEERS_THE_EVENT_LAYER, **limits}))
    _vet_the_frames_handed(name, arguments, pokes, io_seed, budget)
    return result


def run_guarded(name, arguments, pokes, *, objects=None, **kwargs):
    """A door user's case: its C FIRST IN A CHILD — a PRECONDITION (`returns_in_a_child`, the walked routines served
    there when `objects` names any): a core that loops where the ROM's run ends fails the case by a timeout, where
    in-process it would hang the worker — then the differential (`run_event`, `objects` and the rest its)."""
    returns_in_a_child(name, arguments, pokes, objects=bool(objects), door_calls=HELD_BY_THE_DIFFERENTIAL_THAT_FOLLOWS)
    return run_event(name, arguments, pokes, objects=objects, **kwargs)


# The rows `register` has made, by name: what the door users' census reads the registry by (`test_tier3.py`).
DOOR_USER_ROWS = []


def register(label, name, arguments, pokes, *, drawing=False, io_seed=None, objects=None, answer_compared=True,
             also_dropped=()):
    """One priced `VERIFIED_CASES` row of a door user, named `<core>, <label>` — over `pokes` with `savptr` moved into
    the stack band, so the trap's save lands where neither the row nor its companion compares it and Tier 3 drops
    nothing for it (the cost is the same: the trap saves the same frame, elsewhere). SETTLED BY THE ONE SPELLING
    (`settled_where_stored`, as a leaf row's: `settled`): every word that differs by nature which the ROM's run of
    the row stores — the Line-F mask word, an SR save word a twin's bracket parks — staged at the value the run
    leaves and dropped at Tier 3 by name, with the companion that drops nothing. `objects` and `answer_compared` as
    `run_event`'s and `aes.register`'s. `also_dropped`: `((lo, hi, why), ...)` THIS ROW's own Tier 3 drops beside
    them — bytes both builds store, each its own by nature (the marshal's copy back of its caller's stack words) —
    which the same companion compares, nothing dropped."""
    machine, hook = merge_pokes(pokes, savptr_in_the_band()), door_hook(drawing, objects)
    settled_pokes, drops = settled_where_stored(machine, _stored_by_a_door_row(name, arguments, machine, io_seed),
                                                WORDS_BY_NATURE)
    drops = tuple(drops) + tuple(also_dropped)
    row_name = f"{routines.core_symbol(name)}, {label}"
    DOOR_USER_ROWS.append(row_name)
    companion = functools.partial(aes.undropped, name, arguments, settled_pokes, hook, io_seed, answer_compared)
    return aes.ROWS.register(row_name, getattr(addrs, name), aes.staged(name, arguments, settled_pokes), io_seed=io_seed,
                             dropped=drops, answered=answer_compared, undropped=companion if drops else None)


def _stored_by_a_door_row(name, arguments, machine, io_seed):
    """What the ROM's run of a door user's row stores of the words that differ by nature (`_SETTLED_AT`'s) — kept by
    content for a run that declares no I/O (a seed's values are the kit's own objects: asked of the ROM every time)."""
    if io_seed is None:
        return _stored_where_a_row_settles(name, tuple(arguments), machine)
    image = make_image(aes.staged(name, vdi.as_signed(name, arguments), machine))
    _final, writes, _regs = emu.run(image, getattr(addrs, name), io_seed=io_seed)
    return {at: value for at, value in writes.items() if at in _SETTLED_AT}


Derived = namedtuple("Derived", "delivered rom_memory")


def _settled_interrupted(name, arguments, machine, interrupts, budget=None, derived=None):
    """`machine` as a row taken through `interrupts` stages it — `savptr` moved into the stack band (`register`'s
    reason) and the mask word at the value the ROM's run leaves, refused where that run blocks — and the DELIVERIES that
    run took: `(pokes, delivered)`. ONE derivation serves the row: the settled machine differs from the one the
    deliveries were derived over in the mask word alone, which no interrupt reads and no delivery is checked at
    (`_NOT_COMPARED`) — every replay over the settled machine checks the rest (`DoorStops`), and
    `test_boot_snapshot.py` derives every registered row's deliveries again over its settled machine to pin it.

    `derived` (a `Derived`): what a ROM run of this very case that RETURNED has already derived over `machine` — its
    deliveries and the memory it left (`interrupted`'s, handed on to its second differential). It is this function's
    own run exactly where `machine` already keeps `savptr` in the band (the same bytes run again would derive the same);
    over any other machine it is not, and the run is made."""
    pokes = merge_pokes(machine, savptr_in_the_band())
    if derived is not None and pokes == merge_pokes(machine):
        delivered, rom_memory = derived
        mask_word = case.word_in(rom_memory, aes.AES_LINEF_MASK_WORD)
        sr_words = _sr_words_an_interrupted_run_left(rom_memory, aes.staged(name, arguments, pokes), delivered)
    else:
        delivered, mask_word, sr_words = _taken_through(name, tuple(arguments), pokes, interrupts, budget)
    return _SettledRow(merge_pokes(pokes, aes.field_pokes("AES", LINEF_MASK_WORD=mask_word), sr_words), delivered,
                       sr_words)


class _SettledRow(tuple):
    """`_settled_interrupted`'s `(pokes, delivered)` — and `sr_words`, the SR save words it staged beside the mask
    word (the ones the row's Tier 3 drops name: `sr_drops_of`)."""

    def __new__(cls, pokes, delivered, sr_words):
        settled = super().__new__(cls, (pokes, delivered))
        settled.sr_words = tuple(sorted(sr_words))
        return settled


def _sr_words_an_interrupted_run_left(rom_memory, staged, delivered):
    """`{word: its bytes}`: the SR save words an interrupted ROM run's OWN stores changed (`SR_DROPS`; a delivered
    interrupt's store is laid into both shores alike, and is none of the run's: `_with_the_deliveries_laid`) — what a
    row taken through interrupts stages at the value the run leaves, and drops (`sr_drops_of`)."""
    started = _with_the_deliveries_laid(staged, delivered)
    return {word: bytes(rom_memory[word:word + aes.WORD_BYTES]) for word in SR_DROPS
            if any(rom_memory[at] != _started_with(started, at) for at in range(word, word + aes.WORD_BYTES))}


def sr_drops_of(sr_words):
    """The drops of the SR save words a settled row staged (`_SettledRow.sr_words`) — none, for every row whose run
    reaches no bracket."""
    return sr_drops(*sr_words) if sr_words else ()


@kept_on_disk
def _taken_through(name, arguments, pokes, interrupts, budget):
    """A priced row's own derivation — the ROM's run of `addrs.<name>` over `pokes` taken through `interrupts`
    (`rom_interrupted`), refused where it blocks: `(its deliveries, the mask word it leaves, the SR save words its own
    stores changed)`. Kept by content."""
    _calls, delivered, rom_memory, result = rom_interrupted(name, arguments, pokes, interrupts, budget=budget)
    assert result, f"{name}: a priced row returns — the ROM's run taken through these interrupts blocks"
    return (delivered, case.word_in(rom_memory, aes.AES_LINEF_MASK_WORD),
            _sr_words_an_interrupted_run_left(rom_memory, aes.staged(name, arguments, pokes), delivered))


def interrupted_row(label, name, arguments, machine, interrupts, budget=None):
    """A `VERIFIED_CASES` row of a door user TAKEN THROUGH `interrupts`, named `<core>, <label>`, over `machine` as such
    a row stages it (`_settled_interrupted`): the row carries its DELIVERIES, which every run of its ORIGINAL lays at
    the same door calls — Tier 3's on both sides (`delivering`), the snapshot's sweeps (`replayed`). `budget`: the
    row's own derivation budget, declared (`_budget_of`)."""
    return _interrupted_row(label, name, arguments, *_settled_interrupted(name, arguments, machine, interrupts, budget))


def _interrupted_row(label, name, arguments, pokes, delivered):
    return case.verified_row(f"{routines.core_symbol(name)}, {label}", getattr(addrs, name), {},
                             aes.staged(name, arguments, pokes), delivered=delivered)


# The rows `register_interrupted` registered, `{row name: InterruptedRow}`: what a row's deliveries were derived from
# (and under which declared budget, None for the default), for the cases that derive them again (`rederived`).
InterruptedRow = namedtuple("InterruptedRow", "name arguments pokes interrupts delivered budget sr_words", defaults=((),))
INTERRUPTED_ROWS = {}


def session_of(row_name):
    """The SESSION the registered row `row_name` is of — its `InterruptedRow`, or None for a row not taken through
    interrupts. The rows `register_slices` registers of one session are ONE record (`is`): one machine, one set of
    deliveries, one derivation. A SLICED SESSION THAT SWITCHES (`register_woken_slices`) is one record the same way:
    its registered `aes_switching.Registered`, the same object under each of its slices' names."""
    if row_name in SLICED_ROWS and row_name in SWITCHING_ROWS:
        return SWITCHING_ROWS[row_name]
    return INTERRUPTED_ROWS.get(row_name)


class OncePerSession:
    """What a consumer computes "per row" over the rows of ONE SLICED SESSION is one computation: a session's slice
    rows differ in their names and their slices alone (`register_slices` registers each from the same
    `InterruptedRow`), so the ORIGINAL's run of each, its deliveries derived again, its companion's differential, its
    pair of bench runs are the same run. THE ONE MEMO of it, for every holder (a sweep, a table, a test module).

    A memo answers ONE computation, named where it is built — `compute`, over whatever its holder holds fixed (a base
    image, a build): a second image or build is a second memo, never this one asked again. `memo(row_name, machine,
    *arguments)` is `compute(*arguments)`, made for the first row asked of a session and answered to its others —
    whose `machine` (what the run is over: all of a row but its name and slice) must then EQUAL the first's, refused
    by name: the premise the answer rests on. Kept for sliced sessions alone: any other row is a session of its own,
    with nothing to answer it to, and is computed every time."""

    def __init__(self, compute):
        self._compute = compute
        self._made = {}                 # by the session's identity; the session kept, so its id is never reused

    def __call__(self, row_name, machine, *arguments):
        if row_name not in SLICED_ROWS:
            return self._compute(*arguments)
        session = session_of(row_name)
        if id(session) not in self._made:
            self._made[id(session)] = (session, machine, self._compute(*arguments))
        _session, made_over, value = self._made[id(session)]
        assert machine == made_over, (
            f"{row_name}: the rows of its session are not one machine — they cannot share a run")
        return value


# ---- A ROW THAT SWITCHES: what its run is taken through, beside the door calls ---------------------------------------------
# A row whose call BLOCKS AND IS WOKEN leaves by the dispatcher and comes back by it: its interrupts are delivered
# where the machine WAITS for one — the dispatcher's idle (`aes_switch.scheduled`: the n-th idle of the run, whichever
# process's dispatch it is in) — and no unwatched run has that point. `Switches` is such a row's NINTH FIELD, in the
# place a door row's `{door call: (found, wrote)}` has (`test_boot_snapshot.delivered_of`), and NEITHER A DICT NOR A
# TUPLE: a reader that indexes it by a door call's ordinal fails where it reads (a TypeError), instead of laying an
# idle's interrupt at a door call — and it is true with nothing delivered too, as a row that switches is one:
#   `at_idles`  `{idle: (found, wrote)}` — as `deliveries` answers door calls; empty for a wake the dispatcher's own
#               poll makes (a key typed ahead);
#   `idles`     how many idles the ROM's own run makes: what every run of the row is held to, on either shore;
#   `process`   the PD of the process that makes the call: every other one the dispatcher enters is FOREIGN;
#   `at_calls`  the row's door-call deliveries, where it has any too;
#   `at_polls`  `{poll: (found, wrote)}` — what the run takes at a POLL of the dispatcher that is NO IDLE: idle polls the
#               keyboard every time round its loop, a process ready or woken too, and a key that arrives there is
#               polled before that process runs (a key and a message in one wake are made no other way);
#   `polls`     how many polls of the dispatcher's idle the ROM's own run makes, idles among them — every run of the
#               row is held to it; None for a hand-made record that holds no run to a count.
# The watch that takes a run through one is `aes_switching.Switching` (imported where it is asked for: that module
# imports this one); `SWITCHING_ROWS` is the registered rows' register, as `INTERRUPTED_ROWS` is the door's.
@dataclasses.dataclass(frozen=True)
class Switches:
    at_idles: dict
    idles: int
    process: int
    at_calls: dict = dataclasses.field(default_factory=dict)
    at_polls: dict = dataclasses.field(default_factory=dict)
    polls: int = None

    def _replace(self, **changed):
        """This, with `changed` — a row's own spelling (`namedtuple._replace`) for a record that is no tuple."""
        return dataclasses.replace(self, **changed)


SWITCHING_ROWS = {}


def switching(delivered):
    """`delivered` (a row's ninth field) as the `Switches` it is, or None for a row whose run switches nowhere."""
    return delivered if isinstance(delivered, Switches) else None


def at_door_calls(delivered):
    """...and the row's `{door call: (found, wrote)}`, whichever it is."""
    return delivered.at_calls if isinstance(delivered, Switches) else (delivered or {})


def rederived(row_name):
    """The deliveries of the registered row `row_name` DERIVED AGAIN, over the snapshot as it stands now
    (`harness.set_base_image`): the interrupts' own code run afresh — for the sweep that fills the snapshot's MASK with
    noise, where an interrupt reading a masked byte must show it (the deliveries derived over the pristine snapshot,
    laid as they are, would hide it). A row that switches is derived again by its own register (`SWITCHING_ROWS`)."""
    if row_name in SWITCHING_ROWS:
        return SWITCHING_ROWS[row_name].rederived()
    assert row_name in INTERRUPTED_ROWS, f"{row_name}: no row taken through interrupts registered by that name"
    row = INTERRUPTED_ROWS[row_name]
    return deliveries(row.name, row.arguments, row.pokes, row.interrupts, row.budget)


def register_interrupted(label, name, arguments, machine, interrupts, *, objects=False, budget=None):
    """One PRICED `interrupted_row`, registered (`aes.ROWS`) — the mask word dropped at Tier 3 with the COMPANION a
    drop needs: the same interrupted differential (`interrupted`, `objects` its, over the row's own deliveries),
    comparing every byte outside the stack band. The row's own pricing is its second differential, so the companion
    does not make one again. `budget`: the row's own derivation budget, declared (`_budget_of`) — every derivation of
    the row (this one, its companion's, `rederived`) is held to it, both ways."""
    settled = _settled_interrupted(name, arguments, machine, interrupts, budget)
    pokes, delivered = settled
    return _registered(label, InterruptedRow(name, arguments, pokes, interrupts, delivered, budget, settled.sr_words),
                       _companion(name, arguments, pokes, interrupts, delivered, objects, budget))


def _companion(name, arguments, pokes, interrupts, delivered, objects, budget):
    """A registered row's COMPANION: its interrupted differential over the row's own deliveries, every byte outside
    the stack band compared, the bench's second differential left to the row's pricing."""
    return functools.partial(interrupted, name, arguments, pokes, interrupts, objects=objects,
                             not_compared=frozenset(case.STACK_BAND), delivered=delivered, second_differential=False,
                             budget=budget)


def _registered(label, row, companion):
    """`row` (an `InterruptedRow`, settled) registered as `<core>, <label>` with its `companion`: recorded
    (`INTERRUPTED_ROWS`), and a priced row of `aes.ROWS` — the mask word dropped at Tier 3."""
    row_name, entry, _regs, staged, *_rest = _interrupted_row(label, row.name, row.arguments, row.pokes, row.delivered)
    INTERRUPTED_ROWS[row_name] = row
    return aes.ROWS.register(row_name, entry, staged, dropped=aes.LINE_F_MASK_WINDOW + sr_drops_of(row.sr_words),
                             undropped=companion, delivered=row.delivered)


# ---- the machines, each the ROM's own -----------------------------------------------------------------------------------
# The band the derivations and the door's batteries stage in: a mouse packet, a window's rectangle, a message buffer.
BAND_OFFSET = 0x6D0                    # the gap between test/aes.py's Line-F caller and test_aes_gemgraf's band (+$700)
BAND_BYTES = 0x30
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES,
                         "test/aes_event.py: a mouse packet, a window's rectangle, a message buffer")
PACKET_AT = BAND_AT                    # a relative mouse packet: the header, dx, dy
WINDOW_RECT_AT = BAND_AT + 0x4         # the GRECT wm_create and wm_open are handed
MESSAGE_AT = BAND_AT + 0x10            # a message buffer
MESSAGE_BYTES = aes.header_constants("apmsg.h")["AP_MSG_BYTES"]
# evnt_multi's frame for A KEY, AND NOTHING ELSE, WAITED FOR — how a process is parked where a case needs it parked
# (`parked`): no rectangle, no timer, no button, no message; its answers over the band's message buffer.
KEY_WAIT = EV_MULTI_FRAME.pack(aes.EV_MU_KEYBD, 0, 0, 0, 0, 0, MESSAGE_AT)
assert MESSAGE_AT + MESSAGE_BYTES <= BAND_AT + BAND_BYTES
# Each derivation's DEFAULT budget, and the margin every derivation is held to under it (`_rom_run`, and the ROM's watched
# runs):
# the deepest of them, the ROM's draw_change of a lower window moved and resized, watched for its door calls
# (`test_aes_wm_update.deepest_derivation()`, which `test_aes_event.py` runs under the margin), measured at 244,097
# instructions — 6.1 times under.
DERIVATION_INSNS = 1_500_000
DERIVATION_MARGIN = 5
# A ROW'S OWN BUDGET. A long interactive session — the file selector listing a directory, a dialog typed into for forty
# keys — runs past what DERIVATION_INSNS admits under its margin (300,000 instructions), and raising the default for
# it would loosen the bound on every other derivation: a short one that began to spin would run five times longer
# before it was refused. So the case that needs more DECLARES it (`budget=`, on `interrupted`, `register_interrupted`,
# `register_slices`, `run_event` ...), from its measured run — and the declaration is held BOTH WAYS, by name:
#   * the run must fit it by DERIVATION_MARGIN, as every derivation fits the default (`_vet_the_margin`);
#   * a run that ENDED (returned, or blocked at a door call) must have NEEDED it (`_vet_not_stale`): a run the
#     default admits by its margin declares for nothing — the question is the RUN's spend, not the declaration's size
#     (a budget of DERIVATION_INSNS + 1 over a run of 200,000 instructions passed every other rule) — and a
#     declaration more than DERIVATION_STALE times the least that admits the run (its spend times the margin) is
#     STALE: written for a longer run than the case now makes, or by guess. One no greater than DERIVATION_INSNS
#     declares nothing whatever the run, and is refused before it (`_budget_of`).
# So a declared budget B over a run of N instructions holds  DERIVATION_INSNS < 5 N <= B <= 10 N.
# THE IN-PROCESS DIFFERENTIAL of a door case (`run_event`) is another run with another default — `emu.run`'s own cap,
# DIFFERENTIAL_INSNS, a bare limit with no margin under it — so what raises it is declared under its own name (`cap=`)
# and held the same way (`vet_the_cap`): needed (the run is past the default), fitted by DERIVATION_MARGIN, not stale.
# A run of 200,001..300,000 instructions needs the cap and no budget; past that it needs both, and one declaration
# (`budget=`) serves both runs.
# ONE DOOR FOR A CAP (`capped_run`): every in-process differential of the event door's batteries that runs past the
# oracle's own cap is capped and vetted there — `run_event`, and the file selector's runs (`aes_fslib`) — and a raw
# `max_insns` handed past it is refused by name. A BATTERY whose cases share one cap declares it once, from its
# deepest run measured (`battery_cap`: held to that run both ways at the declaration; every run under it then held to
# the margin) — the same rule, the need shown where the battery re-measures that run.
DERIVATION_STALE = 2
DIFFERENTIAL_INSNS = inspect.signature(emu.run).parameters["max_insns"].default


def _budget_of(entry, declared):
    """The instructions a derivation's run of `entry` may spend: DERIVATION_INSNS, or the budget its row `declared` —
    refused by name unless it is above the default, which it would otherwise only restate."""
    if declared is None:
        return DERIVATION_INSNS
    assert declared > DERIVATION_INSNS, (
        f"the derivation's run of {entry:#x} declares a budget of {declared} instructions, no more than "
        f"DERIVATION_INSNS ({DERIVATION_INSNS}): the declaration is stale — the default already covers it, drop it")
    return declared


def _vet_the_margin(entry, insns, declared=None):
    """A derivation's run of `entry` that spent `insns` fits its budget DERIVATION_MARGIN times over: the default, or
    the one its row `declared` — each refused in its own words, naming what to raise."""
    if declared is None:
        assert insns * DERIVATION_MARGIN <= DERIVATION_INSNS, (
            f"the derivation's run of {entry:#x} spent {insns} instructions — inside DERIVATION_INSNS' margin of "
            f"{DERIVATION_MARGIN}: raise the budget, from this run")
        return
    assert insns * DERIVATION_MARGIN <= _budget_of(entry, declared), (
        f"the derivation's run of {entry:#x} spent {insns} instructions — inside its declared budget's ({declared}) "
        f"margin of {DERIVATION_MARGIN}: raise the row's budget to at least {insns * DERIVATION_MARGIN}, from this run")


def _vet_not_stale(entry, insns, declared):
    """A derivation's run of `entry` that ENDED (returned, or blocked) after `insns` instructions NEEDED the budget its
    row `declared`: refused by name where DERIVATION_INSNS admits the run by its margin (the default would have served
    it), and where the declaration is more than DERIVATION_STALE times what admits the run (above). Only a run that
    ended says what its case needs — a prefix a watch stopped at an entry is held to the margin alone."""
    if declared is None:
        return
    least = insns * DERIVATION_MARGIN
    assert least > DERIVATION_INSNS, (
        f"the derivation's run of {entry:#x} declares a budget of {declared} instructions and spent {insns}: the "
        f"declaration is stale — DERIVATION_INSNS ({DERIVATION_INSNS}) admits this run by its margin of "
        f"{DERIVATION_MARGIN}, the default already covers it, drop it")
    assert declared <= least * DERIVATION_STALE, (
        f"the derivation's run of {entry:#x} declares a budget of {declared} instructions and spent {insns}: the "
        f"declaration is stale — {least} admits this run (its margin of {DERIVATION_MARGIN}), and a declared budget "
        f"may be at most {DERIVATION_STALE} times that ({least * DERIVATION_STALE}); declare it again, from this run")


class BatteryCap(namedtuple("BatteryCap", "insns deepest")):
    """A cap ONE declaration makes for a whole BATTERY's in-process runs (`battery_cap`): `insns`, declared from the
    `deepest` of those runs measured."""


def battery_cap(insns, deepest):
    """A battery's cap of `insns` instructions, DECLARED from its `deepest` run measured — held here as a case's own
    is (`_vet_a_case_s_cap`): that run needed it, fits it by DERIVATION_MARGIN and did not declare it stale. Each run
    under it is then held to the margin alone (`vet_the_cap`): whether the battery needs its cap is the deepest run's
    to show, where the battery re-measures it."""
    _vet_a_case_s_cap(None, deepest, insns)
    return BatteryCap(insns, deepest)


def capped_run(name, cap, kwargs, run):
    """THE ONE DOOR an in-process differential of `addrs.<name>` past the oracle's own cap goes through: `run(**limits)`
    (an `aes.run_function` of it, the case's other `kwargs` among `limits`) capped at `cap` — a case's own number, its
    battery's `BatteryCap`, or None for a run DIFFERENTIAL_INSNS covers — and the cap then held to the ORIGINAL's
    spend (`vet_the_cap`). Refused by name: a raw `max_insns` among `kwargs` (a cap no rule would hold), and an
    original that did not return under a declared cap."""
    assert "max_insns" not in kwargs, (
        f"{name}: a raw max_insns ({kwargs['max_insns']}) was handed past the cap's door — declare it as the case's "
        f"`cap=`, which is held both ways")
    insns = cap.insns if isinstance(cap, BatteryCap) else cap
    try:
        result = run(**kwargs, **({} if insns is None else {"max_insns": insns}))
    except RuntimeError as refused:
        if insns is None or f"within {insns} instructions" not in str(refused):
            raise
        raise AssertionError(f"{name}: the ROM's run did not return within its declared cap ({insns}): raise the cap, "
                             f"from this run") from None
    vet_the_cap(getattr(addrs, name), result.info["regs"]["ninsns"], cap)
    return result


def vet_the_cap(entry, insns, cap):
    """An in-process differential of `entry` whose ORIGINAL spent `insns` under `cap` is held to it by name: a
    BATTERY's cap (`BatteryCap`) by DERIVATION_MARGIN — not asked whether this run needed it — and a case's OWN number
    both ways (`_vet_a_case_s_cap`). None: the run declared no cap."""
    if cap is None:
        return
    if not isinstance(cap, BatteryCap):
        return _vet_a_case_s_cap(entry, insns, cap)
    least = insns * DERIVATION_MARGIN
    assert least <= cap.insns, (
        f"the differential of {entry:#x} spent {insns} instructions — inside its battery's declared cap's ({cap.insns}) "
        f"margin of {DERIVATION_MARGIN}: raise the battery's cap to at least {least}, from this run")


def _vet_a_case_s_cap(entry, insns, cap):
    """A differential of `entry` (None: a battery's deepest run, at its declaration) whose ORIGINAL spent `insns` under
    the `cap` declared for it needed it, fits it by DERIVATION_MARGIN and did not declare it stale — each refused in
    its own words."""
    who = "a battery's deepest run" if entry is None else f"the differential of {entry:#x}"
    assert insns > DIFFERENTIAL_INSNS, (
        f"{who} declares a cap of {cap} instructions and its original spent {insns}: the "
        f"declaration is stale — the oracle's own cap ({DIFFERENTIAL_INSNS}) already covers it, drop it")
    least = insns * DERIVATION_MARGIN
    assert least <= cap, (
        f"{who} spent {insns} instructions — inside its declared cap's ({cap}) margin of "
        f"{DERIVATION_MARGIN}: raise the case's cap to at least {least}, from this run")
    assert cap <= least * DERIVATION_STALE, (
        f"{who} declares a cap of {cap} instructions and its original spent {insns}: the "
        f"declaration is stale — {least} admits this run (its margin of {DERIVATION_MARGIN}), and a declared cap may "
        f"be at most {DERIVATION_STALE} times that ({least * DERIVATION_STALE}); declare it again, from this run")


def _rom_run(image, entry, regs=None, stop_pc=0, budget=None):
    """`emu.run` of a derivation: under DERIVATION_INSNS — or the `budget` its case declares (`_budget_of`) — by
    DERIVATION_MARGIN, its write ledger whole."""
    final, writes, regs_out = emu.run(image, entry, dict(regs or {}), max_insns=_budget_of(entry, budget),
                                      stop_pc=stop_pc)
    assert not regs_out["writes_truncated"], f"the derivation's run of {entry:#x} overflowed the write ledger"
    _vet_the_margin(entry, regs_out["ninsns"], budget)
    return final, writes, regs_out


def stopped_at(image, entry, stop_pc, budget=None):
    """A derivation's PREFIX: the ROM's `entry` over `image` (its frame staged) run until it first reaches `stop_pc` —
    `(final, writes, regs)`, as `emu.run` answers — under the `budget` its case declares (`_budget_of`): the run's CAP,
    and what it is held to by its margin; refused by name where the run never reaches the stop. A prefix is not asked
    whether it NEEDED its budget (`_vet_not_stale`): only a run that ended says what its case needs."""
    final, writes, regs_out = _rom_run(image, entry, stop_pc=stop_pc, budget=budget)
    assert regs_out["checkpoint"], f"the derivation's run of {entry:#x} never reached {stop_pc:#x}"
    return final, writes, regs_out


@kept_on_disk
def _derived_run(entry, machine, regs):
    """The ROM's run of `entry` over `machine`, as a KEPT derivation answers it: `(every byte it wrote, what the run
    reports)` — a megabyte's ledger at most, where the image it leaves is sixteen. THAT IMAGE IS THE MACHINE WITH THE
    LEDGER LAID IN IT, which is held here, at the run, so `derived` may make it so on a hit."""
    final, writes, regs_out = _rom_run(make_image(machine), entry, regs, stop_pc=addrs.AES_ROM_DSPTCH)
    assert not regs_out["checkpoint"], (
        f"the derivation's run of {entry:#x} reached the dispatcher (dsptch, {addrs.AES_ROM_DSPTCH:#x}): it would "
        f"switch processes")
    assert _with_the_writes_laid_in(machine, writes) == final, (
        f"the run of {entry:#x} left an image that is not its machine with its write ledger laid in it")
    return writes, regs_out


def _with_the_writes_laid_in(machine, writes):
    """The image a run of `machine` that wrote `writes` leaves: the machine, the return address the oracle plants
    for the run (no store of the run's: it is in no ledger), and the ledger over both."""
    image = make_image(machine)
    image[emu.STACK_TOP:emu.STACK_TOP + emu.SENTINEL_SLOT_BYTES] = emu.SENTINEL.to_bytes(emu.SENTINEL_SLOT_BYTES, "big")
    for at, value in writes.items():
        image[at] = value
    return image


def derived(entry, pokes, regs=None, frame=b""):
    """What the ROM's run of `entry` over `aes.leaf_machine()` and `pokes` WROTE, the stack band out — and the run. A
    machine of this module's in `pokes` (`pd0_running`, `machine`) brings its own running process: the lever's poked
    one beneath it is overwritten by the scheduler's. The run may not reach the DISPATCHER (it stops there, refused):
    a dsptch a process-level routine reaches would switch processes — a block or a yield — which a derivation that
    keeps only one run's writes cannot carry. The run itself is kept by content (`_derived_run`): every registry
    asks some eighty of these at import, in every process."""
    machine = merge_pokes(aes.leaf_machine(), pokes, {abi.FIRST_ARG: frame} if frame else None)
    writes, regs_out = _derived_run(entry, machine, regs)
    return case.written_by(writes), _with_the_writes_laid_in(machine, writes), regs_out


def scheduler_state(image, pd):
    """What the scheduler's invariants say of `pd` RUNNING over `image`, as a dict — every one checkable at a glance."""
    return {"ready list": aes.list_of(image, aes.AES_RLR), "not ready": pd in aes.list_of(image, aes.AES_NRL),
            "status": case.word_in(image, pd + aes.PD_STAT), "dispatcher guard": image[aes.AES_INDISP],
            "waits": case.long_in(image, pd + aes.PD_EVLIST)}


def running_as_switchto_leaves_it(pd):
    """...and what they say of a process the dispatcher switched to and that came out of its evnt_multi: alone on the
    ready list and off the not-ready one, PD_STAT ready, the dispatcher's guard cleared ($fe394e), no wait left."""
    return {"ready list": [pd], "not ready": False, "status": aes.PD_STAT_READY, "dispatcher guard": 0, "waits": 0}


def frame_of(*items):
    """An Alcyon frame as its raw words and longs — for an ORACLE-ONLY run of the ROM's routine (`derived`, `parked`,
    a battery's `rom_derived`), which consults no declared signature (`aes.staged` packs a C core's case from its
    declared one): ("w" | "l", value) items in push order, each word the signed or unsigned word it is."""
    return b"".join(struct.pack(">H", value & WORD_MASK) if kind == "w" else struct.pack(">I", value)
                    for kind, value in items)


def dispatched(pokes, pd, comes_out_at=addrs.AES_ROM_EV_MULTI_RETURN, *, alone=True):
    """THE DISPATCHER'S OWN LOOP run over `pokes` from where the snapshot waits in it (`AES_ROM_DISP_LOOP`) UNTIL A
    PROCESS COMES OUT — the run stopped at `comes_out_at` (where a process parked in its evnt_multi comes out of it,
    by default; a staged application's first instruction; a routine it was parked inside), refused by name where the
    loop never gets there or the process then running is not `pd` — ALONE on the ready list, unless the case says
    another is ready too (`alone` False: a staged application not yet entered; `pd` is then the list's first):
    `(the delta, final, regs)` — `pokes` with everything the loop wrote (forker's posts, idle's and switchto's
    lists, the frames the process came back out through), the image and the registers at the stop."""
    final, writes, regs = stopped_at(make_image(pokes), addrs.AES_ROM_DISP_LOOP, comes_out_at)
    ready = aes.list_of(final, aes.AES_RLR)
    assert ready[:1] == [pd] and not (alone and ready[1:]), (
        f"the dispatcher's loop entered another process than the PD at {pd:#x}"
        + (", or not it alone" if alone else "") + f": the ready list is {[f'{each:#x}' for each in ready]}")
    return merge_pokes(pokes, case.written_by(writes)), final, regs


def _woken(pokes, pd=aes.SHELL_PD):
    """`pokes` (laid over the snapshot as it is) with the event the parked `pd` waits for, then the dispatcher's loop
    (`dispatched`): forker posts the event to the wait, idle moves the process to the ready list, switchto enters it
    — and the run stops where it comes out of its evnt_multi, its waits cancelled by ev_multi's own tail. The delta,
    the event's pokes in it; `pd` the one running, alone on the ready list."""
    return dispatched(pokes, pd)[0]


RETURN_KEY = 0x1C                      # a make code: the 6301's byte for Return
# The BIOS keyboard handler's own base register: the ACIA interrupt handler's `lea 0,a5` ($fc29d2), which every arm it
# reaches addresses the BIOS's variables off ($fc2b5c `move.b $e61(a5),d1`).
ACIA_HANDLER_A5 = 0


def _keyed(image, scancode):
    """The key of make code `scancode` through the BIOS's own keyboard handler, run from its scancode arm
    (KBD_SCANCODE) in the state the ACIA interrupt reaches it in — D0 the byte, A0 the keyboard's ring (what
    `acia_take_byte` hands it), A5 the handler's base — the ASCII its own Keytbl lookup: an interrupt
    (`_interrupt_over`) over `image` in place, whatever process state it holds. What it wrote."""
    return _interrupt_over(image, addrs.KBD_SCANCODE, {"d0": scancode, "a0": addrs.IOREC_IKBD, "a5": ACIA_HANDLER_A5})


def key(scancode):
    """A KEY PRESSED — an interrupt `interrupted` can deliver at a door call, as `press` is: `key(scancode)(image)`
    answers what the keyboard handler wrote (`_keyed`), the key then in the IKBD ring, which the event layer polls
    through the VDI on every ev_multi."""
    return functools.partial(_keyed, scancode=scancode)


def keys(*scancodes, onto=None):
    """The IKBD ring holding a key per make code of `scancodes`, unread, over `onto` (the snapshot by default): each
    `key` an interrupt over whatever process state `onto` holds (the snapshot's: rlr NULL, the dispatcher's guard set).
    A delta, to lay over `onto`."""
    image, written = make_image(onto or {}), {}
    for scancode in scancodes:
        written = merge_pokes(written, key(scancode)(image))
    return written


def typed_ahead(machine, *scancodes):
    """`machine` with a key per make code of `scancodes` already in the IKBD ring, unread — typed before the call
    (`keys`, over `machine`)."""
    return merge_pokes(machine, keys(*scancodes, onto=machine))


KEYTBL_CODES = 128                     # make codes a Keytbl table maps (addrs.h: three 128-byte tables)


def scancode_of(character):
    """The make code of the key a typist presses for `character`: the one the snapshot's own UNSHIFTED Keytbl table
    (KEYTBL_STRUCT) maps to it. Refused by name for a character no unshifted key types. THE SNAPSHOT'S table, not the
    case machine's: the keyboard handler (`key`) looks the code up through the machine's own Keytbl pointer, so over a
    machine that had moved it (an application's Keytbl call, which no case stages) the key would type that table's
    character — C and ROM still agreeing, the case's text no longer what it says."""
    table = case.long_in(BASE_IMAGE, addrs.KEYTBL_STRUCT + addrs.KEYTBL_FIELD_UNSHIFTED)
    codes = [code for code in range(KEYTBL_CODES) if BASE_IMAGE[table + code] == ord(character)]
    assert codes, f"no unshifted key types {character!r}"
    return codes[0]


class Waits:
    """A SCHEDULE of interrupts (`deliveries`' callable `interrupts`): `interrupts[k]` — an interrupt or a tuple of them
    (`key`, `press`, `move_to(x, y)` ...) — delivered at the entry of the k-th call of the door's entry `at`, counted
    from 0; a call with no row takes nothing. The waits a routine makes are numbered as it makes them, whatever other
    door calls come between (a dialog's own wm_update, a nested routine's). Each run BEGINS it afresh (`begin_run`,
    which the run that asks it calls before its first instruction), then asks it at EVERY door call, in order (refused
    by name otherwise), and it checks the entry at every call: a second run — the replay, a row's registration over its
    settled machine, another routine — is answered at its own waits and nowhere else. `pending`: the rows the current
    run's waits have not reached — every row, for a run that made no door call."""

    def __init__(self, interrupts, at=addrs.AES_ROM_EV_MULTI):
        self._interrupts, self._at = dict(interrupts), at
        self.begin_run()

    def begin_run(self):
        """A run begins: its waits counted from none, its door calls from call 0."""
        self._next_ordinal = self._waits = 0

    def derived_content(self):
        """What a kept derivation is asked ABOUT, of a schedule (`derived.ASKED_ABOUT`): its rows and its entry — not
        how far the last run counted."""
        return self._interrupts, self._at

    def counted(self):
        """How far the current run has counted: `(its door calls, its waits)`."""
        return self._next_ordinal, self._waits

    def counted_to(self, counted):
        """...and the schedule put where a run that counted so far leaves it (a kept derivation's: `_deliveries`)."""
        self._next_ordinal, self._waits = counted

    @property
    def pending(self):
        return tuple(self._interrupts[wait] for wait in sorted(self._interrupts) if wait >= self._waits)

    def __call__(self, ordinal, entry):
        assert ordinal == self._next_ordinal, (
            f"a schedule asked at door call {ordinal} where the run's next is {self._next_ordinal}: it counts the "
            f"waits of a run asked at every call, in order")
        self._next_ordinal += 1
        if entry != self._at:
            return None
        self._waits += 1
        return self._interrupts.get(self._waits - 1)


def typed(*pressed, at=addrs.AES_ROM_EV_MULTI):
    """The keys `pressed` TYPED into a routine, as a typist presses them — each item text (a key per character,
    `scancode_of`) or a make code (`RETURN_KEY`, an arrow) — each key delivered at the entry of the next call of `at`
    (ev_multi by default): a `Waits` schedule, one key per wait, which ONE watched run of the routine delivers whole
    (`deliveries`)."""
    return Waits(dict(enumerate(key(code) for code in scancodes_of(*pressed))), at)


def scancodes_of(*pressed):
    """The make codes of the keys `pressed`: each item text (a key per character, `scancode_of`) or a make code."""
    return [code for item in pressed for code in (map(scancode_of, item) if isinstance(item, str) else (item,))]


def woken_by_a_key(onto=None):
    """PD0 woken by Return (`keys`) — the key the desk's evnt_multi waits for — and the dispatcher's loop run until PD0
    comes out of that evnt_multi with it (`_woken`), over `onto` (the snapshot as it waits, by default): what an
    interrupt delivered before the key (a mouse moved, `mouse_moved_to`) is taken by the same forker. A delta, the
    key's and `onto`'s pokes in it."""
    return _woken(typed_ahead(onto, RETURN_KEY))


@functools.cache
def pd0_running():
    """PD0 RUNNING, as the scheduler makes it (`woken_by_a_key`, over the snapshot): PD0 alone on the ready list and off
    the not-ready list, PD_STAT 0, its waits cancelled, the dispatcher's guard cleared by switchto, PD1 still parked.
    A delta, to lay over a machine."""
    return woken_by_a_key()


# A RUNNING PROCESS PARKS: a call of its that reaches dsptch saves its context in its UDA and enters the dispatcher's
# loop. `parked` makes that call where the process's own would run — on its OWN supervisor stack, below the SP it last
# parked with, where nothing live lies — and stops where the loop begins, keeping all it wrote: its frames too, which
# it comes back out through when it is woken (`_woken`).
PARKED_FRAME_ROOM = 32                 # below that SP: the return slot and the call's frame (ev_multi's, 26 bytes)


# Images are compared a block at a time, then a LINE at a time inside a block that differs, bytewise only inside a line
# that does: a machine differs from another in a few bytes of a few blocks, and walking each such block byte by byte
# was most of what keeping a machine as pokes cost (measured: 2.4 ms a machine, half of a scenario's derivation).
COMPARED_BLOCK_BYTES = 0x1000
COMPARED_LINE_BYTES = 0x40


def _differing_spans(one, other, lo, hi, step):
    """The `step`-byte spans of [lo, hi) two images differ in: each one's start."""
    return [at for at in range(lo, hi, step) if one[at:at + step] != other[at:at + step]]


def _differing_addresses(one, other, upto=None):
    """The addresses two images (bytes-like, of one size) differ at, in order — below `upto`, when one is named."""
    one, other = bytes(one[:upto]), bytes(other[:upto])
    size = len(one)
    return [at for block in _differing_spans(one, other, 0, size, COMPARED_BLOCK_BYTES)
            for line in _differing_spans(one, other, block, min(block + COMPARED_BLOCK_BYTES, size), COMPARED_LINE_BYTES)
            for at in range(line, min(line + COMPARED_LINE_BYTES, size)) if one[at] != other[at]]


@functools.lru_cache(maxsize=None)
def _spans_left_out(without):
    """`without` — a set of addresses, or a range of them — as its `(lo, hi)` runs, in order."""
    if isinstance(without, range) and without.step == 1:
        return ((without.start, without.stop),) if len(without) else ()
    spans = []
    for at in sorted(without):
        if spans and spans[-1][1] == at:
            spans[-1][1] = at + 1
        else:
            spans.append([at, at + 1])
    return tuple((lo, hi) for lo, hi in spans)


_A_RUN_THAT_DIFFERS = re.compile(rb"[^\x00]+")


def as_pokes(memory, over=BASE_IMAGE, *, without=frozenset(), upto=None):
    """AN IMAGE AS POKES: every byte `memory` differs from `over` at (the snapshot, by default), merged into runs —
    `without` (a set of addresses, or a range: `case.STACK_BAND` for a run's own frames, which every case stages
    afresh) left out, and nothing from `upto` up when one is named (`addrs.ST_RAM_BYTES`: a machine is its RAM). How a
    machine a ROM run made is kept: laid over `over` again, it is that machine.

    A BLOCK AT A TIME — the two blocks compared whole, and where they differ XORed as integers, the runs of non-zero
    bytes found by a pattern — because a scenario keeps a machine at EVERY arrival (hundreds of them), and a dict
    entry per differing byte, merged, was five milliseconds each (`test_aes_event.py` holds this to the definition,
    spelt per byte, over random images)."""
    size = min(len(memory), len(over)) if upto is None else min(upto, len(memory), len(over))
    left_out = _spans_left_out(without if isinstance(without, (range, frozenset)) else frozenset(without))
    pokes, open_run = {}, None
    for block in range(0, size, COMPARED_BLOCK_BYTES):
        end = min(block + COMPARED_BLOCK_BYTES, size)
        ours, theirs = memory[block:end], over[block:end]
        if ours == theirs:
            open_run = None
            continue
        differ = bytearray((int.from_bytes(ours, "big") ^ int.from_bytes(theirs, "big")).to_bytes(end - block, "big"))
        for lo, hi in left_out:
            if lo < end and block < hi:
                lo, hi = max(lo, block) - block, min(hi, end) - block
                differ[lo:hi] = bytes(hi - lo)
        ends_open = None
        for run in _A_RUN_THAT_DIFFERS.finditer(differ):
            start = block + run.start()
            if run.start() == 0 and open_run is not None:       # ...a run that began in the block before
                start = open_run
            pokes[start] = bytes(memory[start:block + run.end()])
            if block + run.end() == end:
                ends_open = start
        open_run = ends_open
    return pokes


def parked(entry, frame, onto):
    """`onto` (a process RUNNING) continued by its call of the ROM's `entry` with the Alcyon `frame`, which PARKS it:
    the run stopped where the dispatcher's loop begins (`AES_ROM_DISP_LOOP`), the process off the ready list. A delta,
    `onto`'s pokes in it."""
    image = make_image(onto)
    pd = case.long_in(image, aes.AES_RLR) & OS_BUS_ADDR_MASK
    sp = case.long_in(image, case.long_in(image, pd + aes.PD_UDA) + aes.UDA_SUPER_SP) - PARKED_FRAME_ROOM
    assert LONG_BYTES + len(frame) <= PARKED_FRAME_ROOM, "the frame does not fit below the process's last SP"
    memory = bytearray(image)
    memory[sp + LONG_BYTES:sp + LONG_BYTES + len(frame)] = frame
    first = int.from_bytes(frame[:LONG_BYTES].ljust(LONG_BYTES, b"\0"), "big")
    emu.install_chip_seeds()            # no chip declared, as `emu.run` declares none (`rom_bench.original_entered`)
    try:
        result = emu.run_bench(memory, entry, first, sp, emu.SENTINEL, max_insns=DERIVATION_INSNS,
                               door={addrs.AES_ROM_DISP_LOOP}, seed_regs=rom_bench.entry_registers())
    finally:
        emu.bench_abort()
    rom_bench.vet_the_run_just_made(f"the parking run of {entry:#x}")
    assert result["status"] == emu.BENCH_DOOR, f"the call of {entry:#x} returned: the process did not park"
    _vet_the_margin(entry, result["ninsns"])
    assert pd not in aes.list_of(memory, aes.AES_RLR), f"the call of {entry:#x} left its process ready"
    return merge_pokes(onto, as_pokes(memory, image, upto=addrs.ST_RAM_BYTES))


LEFT_BUTTON = 1                        # the AES's record of the buttons down (AES_BUTTON): a bit each, left bit 0
MOUSE_PACKET_HEADER = vdi_mouse.MOUSE_H["MOUSE_PACKET_HEADER_MASK"]   # a relative packet, no button down
MOUSE_PACKET_LEFT_BUTTON = 0x02        # ...the left button down: bit 1 of the header's MOUSE_PACKET_BUTTONS_MASK
MOUSE_PACKET_RIGHT_BUTTON = 0x01       # ...the right: bit 0 — the VDI's numbering SWAPPED (`vdi/mouse.h`)
MOUSE_STAT_BUTTONS_MASK = vdi_mouse.MOUSE_H["MOUSE_STAT_BUTTONS_MASK"]
MOUSE_STAT_RIGHT_BUTTON = 0x02         # CUR_MS_STAT's buttons as the VDI numbers them: left bit 0, right bit 1


def _packet(header, dx=0, dy=0):
    """A relative mouse packet at PACKET_AT, as the IKBD's handler hands it on."""
    return {PACKET_AT: struct.pack(">Bbb", header, dx, dy)}


def _interrupt_over(image, entry, regs=None, inputs=None):
    """An INTERRUPT's ROM code `entry` run over `image` as it stands — a bytearray, the machine at any instruction
    boundary — with `inputs` (a packet the IKBD hands on) staged for the run alone: what it WROTE, laid into `image`,
    the stack band out (its own frames, which on the machine land below the interrupted SP)."""
    run_on = image                      # `emu.run` runs a copy of what it is handed: `image` itself is not written
    if inputs:
        run_on = bytearray(image)
        for at, data in inputs.items():
            run_on[at:at + len(data)] = data
    _final, writes, _regs = _rom_run(run_on, entry, regs)
    written = case.written_by(writes)
    for at, data in written.items():
        image[at:at + len(data)] = data
    return written


# ---- THE MACHINE'S INTERRUPTS, SPELT ONCE ------------------------------------------------------------------------------
# ONE INTERRUPT is the ROM's own handler, the registers it is entered with and what is staged for its run alone (a
# packet the IKBD hands on): an `Interrupt`. WHAT A USER DOES is a SEQUENCE of them that depends on the machine as it
# goes — a press is a packet and then as many ticks as the click count it opened; a move is packets until the cursor
# is there — so a sequence is a generator over `image_now()`, the machine's image at the moment it asks: it yields the
# next interrupt, whoever runs it runs it, and the sequence reads the machine again. TWO RUNNERS take the same
# sequences: this module's, over an image in place, answering what was written (`taken_in_place`: `press`, `release`,
# `move_to` ... — what `interrupted` delivers at a door call), and `aes_evinput`'s, watched at the input layer's
# entries, answering the arrivals too. One spelling of each interrupt, so the two cannot come to differ.
Interrupt = namedtuple("Interrupt", "entry regs inputs")
TICK = Interrupt(addrs.AES_ROM_TICK_GLUE, None, None)      # the system timer's: the AES's tick glue (vex_timv's)


def mouse_packet(header, dx=0, dy=0):
    """The VDI's mouse interrupt over one relative packet (`VDI_ROM_MOUSE_ISR`, A0 the packet — what the IKBD's
    mousevec runs): `header` its buttons, (`dx`, `dy`) its move. It records the buttons (MOUSE_BT, CUR_MS_STAT), moves
    the cursor, and calls the AES's button glue (b_click) and motion glue (it queues mchange)."""
    return Interrupt(addrs.VDI_ROM_MOUSE_ISR, {"a0": PACKET_AT}, _packet(header, dx, dy))


def in_turn(*sequences):
    """`sequences`, one after the other, as one."""
    def sequence(image_now):
        for each in sequences:
            yield from each(image_now)
    return sequence


def packets(*headers):
    """A packet per header of `headers`, the mouse not moved."""
    def sequence(_image_now):
        yield from (mouse_packet(header) for header in headers)
    return sequence


def click_counted(image_now):
    """Ticks until an open click count has run out: as many as the count holds (AES_GL_CLICK_TICKS), each counting it
    down (b_delay), the last resolving the click — the change queued for forker. Held to have resolved it."""
    for _tick in range(case.word_in(image_now(), aes.AES_GL_CLICK_TICKS)):
        yield TICK
    assert case.word_in(image_now(), aes.AES_GL_CLICK_TICKS) == 0, "the ticks did not resolve the click"


def ticking(count):
    """`count` ticks."""
    def sequence(_image_now):
        yield from [TICK] * count
    return sequence


LEFT_DOWN_PACKET = MOUSE_PACKET_HEADER | MOUSE_PACKET_LEFT_BUTTON
RIGHT_DOWN_PACKET = MOUSE_PACKET_HEADER | MOUSE_PACKET_RIGHT_BUTTON
NO_BUTTON_PACKET = MOUSE_PACKET_HEADER
# The buttons changed by packets inside the click delay, then the delay run out: the left button PRESSED (the press
# queued for forker, posted to no wait yet), RELEASED, CLICKED (pressed and released inside one count), DOUBLE-CLICKED
# (pressed, released and pressed again: the second press counted by b_click, the button left down), the right PRESSED.
PRESSING = in_turn(packets(LEFT_DOWN_PACKET), click_counted)
RELEASING = in_turn(packets(NO_BUTTON_PACKET), click_counted)
CLICKING = in_turn(packets(LEFT_DOWN_PACKET, NO_BUTTON_PACKET), click_counted)
DOUBLE_CLICKING = in_turn(packets(LEFT_DOWN_PACKET, NO_BUTTON_PACKET, LEFT_DOWN_PACKET), click_counted)
RIGHT_PRESSING = in_turn(packets(RIGHT_DOWN_PACKET), click_counted)


def taken_in_place(image, sequence):
    """`sequence` taken over `image` IN PLACE, each interrupt the ROM's own code over the image as the one before left
    it (`_interrupt_over`): what they wrote."""
    written = {}
    for interrupt in sequence(lambda: image):
        written = merge_pokes(written, _interrupt_over(image, *interrupt))
    return written


def tick(image):
    """A TICK of the system timer over `image` in place: the AES's tick glue (vex_timv's, `AES_ROM_TICK_GLUE` — the
    click delay counted down, a pending timer's elapsed ticks queued for forker). What it wrote — an interrupt
    `interrupted` can deliver."""
    return _interrupt_over(image, *TICK)


def _ticked(image, count):
    return taken_in_place(image, ticking(count))


def ticks(count):
    """`count` ticks, one after the other: `ticks(n)(image)` answers what they wrote — an interrupt, as `tick` is."""
    return functools.partial(_ticked, count=count)


def press(image):
    """The left button PRESSED over `image` in place, as the machine takes it whatever process runs (PRESSING): the
    press queued for forker, posted to no wait yet. What it wrote — an interrupt `interrupted` can deliver."""
    return taken_in_place(image, PRESSING)


def double_click(image):
    """A DOUBLE CLICK over `image` in place (DOUBLE_CLICKING): the button left down. What it wrote."""
    return taken_in_place(image, DOUBLE_CLICKING)


def release(image):
    """...the button RELEASED (RELEASING: a packet with no button down): the release queued for forker the same way."""
    return taken_in_place(image, RELEASING)


def _delivered(interrupt, onto):
    """What `interrupt` (`press`, `release`, `move_to`'s) WROTE over `onto` (the snapshot by default): a delta."""
    return interrupt(make_image(onto))


def pressed(onto=None):
    """The left button PRESSED over `onto` (`press`). A delta, to lay over `onto`."""
    return _delivered(press, onto)


def released(onto=None):
    """The left button RELEASED over `onto` (`release`) — the button up again, as no packet that only MOVES the mouse
    leaves it (`mouse_moved_to` keeps the buttons as they are). A delta, to lay over `onto`."""
    return _delivered(release, onto)


@functools.cache
def button_down():
    """The left button DOWN, PD0 running: the button `pressed` over the snapshot, then the dispatcher's loop
    (`_woken`), whose forker posts the press to the button wait PD0 is parked in (PD0 owns the mouse) and switches to
    it. The button stays down, the VDI's record and the AES's agreeing. A delta."""
    woken = _woken(pressed())
    assert case.word_in(make_image(woken), aes.AES_BUTTON) == LEFT_BUTTON, "the press did not leave the button down"
    return woken


@functools.cache
def _hidden_over(woken):
    """The snapshot after `woken()`, then the ROM's gsx_moff — the cursor hidden by the running process, as every
    drawing caller does before it draws — contrl[0..3] stale before it."""
    return aes_gsx.hidden(merge_pokes(aes_gsx.CONTRL_STALE, woken()))


def machine(woken=pd0_running, onto=None):
    """THE DOOR'S MACHINE: PD0 running as `woken` makes it (`pd0_running`, `button_down`), the cursor hidden after
    (`_hidden_over`) — what an application's graf_mouse(M_OFF) leaves, and every drawing caller's own gsx_moff —
    contrl[0..3] stale again (`aes_gsx.machine`'s arrangement), `onto` over it."""
    return merge_pokes(_hidden_over(woken), aes_gsx.CONTRL_STALE, onto)


def shown_machine(woken=pd0_running, onto=None):
    """...and the same process running with the cursor SHOWN — the snapshot's own cursor (gl_moff `aes_gsx.NEST_SHOWN`),
    which nothing hid: what a caller that hides nothing runs over (menu_bar's dispatcher arm, an application's
    graf_dragbox / graf_rubberbox), contrl[0..3] stale, `onto` over it."""
    return merge_pokes(woken(), aes_gsx.CONTRL_STALE, onto)


MOUSE_STEP = 127                       # the most one packet moves: a signed byte


def _packet_buttons(image):
    """The buttons a packet the IKBD sends now carries: those the VDI's interrupt recorded from the last one
    (CUR_MS_STAT), in the packet's own numbering — the IKBD reports the buttons in every packet, moved or not."""
    held = image[vdi.LINEA_CUR_MS_STAT] & MOUSE_STAT_BUTTONS_MASK
    return ((MOUSE_PACKET_LEFT_BUTTON if held & LEFT_BUTTON else 0)
            | (MOUSE_PACKET_RIGHT_BUTTON if held & MOUSE_STAT_RIGHT_BUTTON else 0))


def _cursor(image):
    """Where the VDI's mouse interrupt has the cursor (GCURX, GCURY)."""
    return case.word_in(image, vdi.LINEA_GCURX), case.word_in(image, vdi.LINEA_GCURY)


def moving_by(*deltas):
    """The mouse moved by each of `deltas`, a packet each, no button changed (the buttons as the VDI holds them:
    `_packet_buttons`)."""
    def sequence(image_now):
        for dx, dy in deltas:
            yield mouse_packet(MOUSE_PACKET_HEADER | _packet_buttons(image_now()), dx, dy)
    return sequence


def moving_to(x, y):
    """The mouse MOVED to (`x`, `y`): relative packets toward it, MOUSE_STEP at most each, the buttons as they are
    held, until the cursor is there. REFUSED by name where a packet leaves the cursor where it was: the interrupt
    clamps it to the screen, so a point past an edge is one no packet reaches."""
    def sequence(image_now):
        while True:
            cursor = _cursor(image_now())
            dx = max(-MOUSE_STEP, min(MOUSE_STEP, x - cursor[0]))
            dy = max(-MOUSE_STEP, min(MOUSE_STEP, y - cursor[1]))
            if not dx and not dy:
                return
            yield from moving_by((dx, dy))(image_now)
            assert _cursor(image_now()) != cursor, (
                f"the mouse cannot be moved to ({x}, {y}): a packet of ({dx}, {dy}) left the cursor at {cursor} — the "
                f"mouse interrupt clamps it to the screen")
    return sequence


def _moved(image, x, y):
    return taken_in_place(image, moving_to(x, y))


def move_to(x, y):
    """The mouse MOVED to (`x`, `y`) (`moving_to`): each packet an interrupt over `image` in place — an interrupt
    `interrupted` can deliver: `move_to(x, y)(image)` answers what they wrote."""
    return functools.partial(_moved, x=x, y=y)


def mouse_moved_to(x, y, onto):
    """`onto` continued by the packets that move the mouse to (`x`, `y`) (`move_to`, each an interrupt over whatever
    process state `onto` holds), the buttons KEPT as `onto` holds them. The AES's own record of the mouse follows only
    when forker runs the motion glue's queued mchange — in the dispatcher's loop, or the running process's next
    ev_multi."""
    return merge_pokes(onto, _delivered(move_to(x, y), onto))


# A point of the MENU BAR, one packet up from the snapshot's mouse: the rectangle the screen manager's evnt_multi waits
# for the mouse to enter (measured: the one move of those tried that wakes it, with MU_M1).
MENU_BAR_POINT = (159, 5)
# ...AND THE POINTS OF THE MENU CHAIN, on the snapshot's own screen — one home for every battery that walks it: "View"
# on the bar, the plain item under it once the menu is dropped, and a point of the desktop below the bar, under no
# dropped menu and on no window. THE CHAIN, as a scheduled run takes it (`{idle: interrupt}`): the mouse onto the
# title wakes the screen manager, which drops the menu; the mouse onto the item; the press — and the screen
# manager's own appl_write of MN_SELECTED to the desk: the one writer a returning run of this machine has.
THE_VIEW_TITLE_S_POINT, VIEW_S_PLAIN_ITEM_S_POINT = (136, 5), (150, 23)
A_POINT_ON_THE_DESKTOP = (20, 180)
ONTO_THE_VIEW_TITLE, ONTO_ITS_PLAIN_ITEM = move_to(*THE_VIEW_TITLE_S_POINT), move_to(*VIEW_S_PLAIN_ITEM_S_POINT)
THE_MENU_CHAIN = {0: ONTO_THE_VIEW_TITLE, 1: ONTO_ITS_PLAIN_ITEM, 2: press}


def woken_onto_the_menu_bar(onto=None):
    """PD1 — the SCREEN MANAGER — woken over `onto` (the snapshot as it waits, by default): the mouse moved onto the
    menu bar (`mouse_moved_to`: one packet), the rectangle PD1 waits for it to enter, and the dispatcher's loop run
    until PD1 comes out of its evnt_multi with it (`_woken`). A delta, `onto`'s pokes in it."""
    return _woken(mouse_moved_to(*MENU_BAR_POINT, onto or {}), aes.SCREEN_MANAGER_PD)


@functools.cache
def screen_manager_running():
    """PD1 RUNNING and PD0 still parked in the desk's evnt_multi, as the scheduler makes it
    (`woken_onto_the_menu_bar`, over the snapshot). A delta."""
    return woken_onto_the_menu_bar()


def window_created(kind, x, y, w, h, onto=None):
    """A window CREATED by the ROM's wm_create(kind, rect) over `onto` (`pd0_running()` by default): `(the machine,
    the handle)` — the handle -1 when every window is in use."""
    state = merge_pokes(pd0_running() if onto is None else onto, {WINDOW_RECT_AT: struct.pack(">4h", x, y, w, h)})
    delta, _final, regs = derived(addrs.AES_ROM_WM_CREATE, state, frame=frame_of(("w", kind), ("l", WINDOW_RECT_AT)))
    return merge_pokes(state, delta), aes.signed(regs["d0"])


def window_chain(kind, x, y, w, h, onto=None):
    """A window CREATED and OPENED by the ROM — wm_create(kind, rect) then wm_open(handle, rect) — over `onto`
    (`pd0_running()` by default): `(the machine, the handle)`. wm_open posts PD0 a redraw message (its pipe)."""
    state, handle = window_created(kind, x, y, w, h, onto)
    assert handle >= 0, "wm_create found no free window"
    delta, _final, _regs = derived(addrs.AES_ROM_WM_OPEN, state, frame=frame_of(("w", handle), ("l", WINDOW_RECT_AT)))
    return merge_pokes(state, delta), handle


# A window of EVERY GADGET (`aes/wmlib.h`'s WK_*), and bit 3, GEM's MOVER, which no routine of the window library reads:
# the kind the desk's own windows carry.
WK_MOVER = 0x0008
EVERY_GADGET = functools.reduce(operator.or_, (value for name, value in aes.header_constants("wmlib.h").items()
                                               if name.startswith("WK_")), WK_MOVER)


# ---- INTERRUPTS AT A DOOR ENTRY: the C and the ROM taken through the same sequence -----------------------------------
# A real machine takes an interrupt at any instruction boundary — at the entry of a routine's k-th call of the event
# layer among them. Both shores can deliver exactly that: the ROM's own run, WATCHED at the door's entries (`DoorStops`,
# its memory the run's own, read on resume), takes the interrupt's effect at the entry of its k-th door call; the C's
# door applies the SAME bytes at its k-th call, before that call is served (`bind_in_a_child`'s `interrupts`), once it
# has checked that the C's image holds what the ROM's memory held at every address they write (`_laid_into`). The
# effect is the ROM's own interrupt code (`press`, `release`, `move_to`: the VDI's mouse interrupt and the AES's tick
# glue) run over the ROM's memory as it stands at that entry — never a poke. Its frames on the INTERRUPTED stack are
# left out (`case.written_by`: the stack band, where on the machine they land below the interrupted SP); what the glue
# writes on the AES's OWN interrupt stacks ($94f2 and $9552 down) is fixed memory the machine writes too, and
# delivered — the SP the glue parks there ($9482, $9486) the one value no machine holds: the stack-band SP the oracle
# entered the interrupt on, where the machine parks the interrupted process's SSP. Both shores receive it alike, and
# only the glue's own exit reads it. A sequence of them reaches what one run cannot: the mouse moving and the button
# changing WHILE a routine waits.
#
# THE COMPARISON is of the whole image, outside the stack band (the C's frame locals are host slots there, the ROM's
# frames its own), the door's two documented windows (`DOOR_DROPS`, whole: the mask word the C never writes and the
# trap's saved registers, the caller's own on each shore) and an SR save word the ROM's run STORED (`SR_DROPS`: one it left
# alone is compared, so a C that wrote it differs): with the ROM's final memory when its run returns — its answer and
# every frame the door was handed too — or with its memory at the ENTRY of the call that blocks, the point where the C's
# door refuses the same call (a case that ends blocked: `blocked_then_woken`'s first half).
COMPARED_DIFFERENCES_SHOWN = 16        # how many differing bytes a failure names
Interrupted = namedtuple("Interrupted", "calls returned answer rom_memory image delivered staged stderr")
_NOT_COMPARED = frozenset(case.STACK_BAND) | frozenset(at for lo, hi, _why in DOOR_DROPS for at in range(lo, hi))


def _as_sequence(interrupts):
    return interrupts if isinstance(interrupts, tuple) else (interrupts,)


# ---- THE IMAGE AT A STOP, PAGE BY PAGE — what two shores hold at a door call's RETURN, and at a DISPATCH ----------------
# A door case compares the whole image where its run ENDS. What a twin stored and a later call (or the wake's own
# aprets) put right again shows at no end: it shows where the twin RETURNS, and where it reaches the DISPATCHER. Both
# shores stop there anyway — the candidate at the door's return hook and at the dispatcher's, the ROM's watched run
# at the address a door call comes back to and at dsptch — so each takes the RAM as it stands there, PAGE BY PAGE
# (a digest a page: a megabyte a stop is not kept, and a child says its own in a line), and the two are held
# equal, the pages that differ named. (The image half of the SHADOW, without its nested run: band 4 wave 3.)
# WHAT IS LEFT OUT OF EVERY PAGE, on both shores alike — the ONE list, wider than a run's end needs because nothing
# here knows what the ROM's run stored: what neither shore compares at an end (`_NOT_COMPARED`: the stack band, the
# Line-F mask word, the keyboard poll's trap save), the trap frame above it and EVERY SR save word, whole; the
# windows a road names beside (`also`: under the host's model the caller's saved context and the dispatcher's stack,
# which no host core stores — `aes_switch.left_out_under_the_model`; over real GEMDOS its three windows); and
# A QPB'S PLACE — the parameter of an EVB where its LONGWORD IS AN ADDRESS OF THE STACK BAND (a QPB's, parked or
# left in a freed EVB: a place in each shore's own stack — vetted where a run blocks and where it ends,
# `parked_where_blocked` / `vetted_qpb_addresses`). THAT ONE IS DECIDED BY EACH SHORE'S OWN VALUE, SO IT IS MARKED,
# NOT BLANKED: the page's digest reads WHERE a place was left out, and a stack address on one shore against
# anything else on the other — zero too — is another page. The whole longword must be the address (both shores
# store a QPB's with its top byte clear: an address under any other top byte is compared as the value it is).
IMAGE_PAGE_BYTES = 0x4000
PAGE_DIGEST_BYTES = 4
# What every page leaves out, as spans: the keyboard poll's trap save and frame — ONE trap frame under the snapshot's
# `savptr` (TRAP_SAVE_AT: where a capture decides, above) — and three that no capture moves, BY NUMBER: the SR save
# words, the Line-F mask word, the stack band.
THE_POLL_S_TRAP_SAVE = (TRAP_SAVE_AT, TRAP_SAVE_AT + addrs.TRAP_SAVE_FRAME_BYTES)
FIXED_IN_EVERY_PAGE = ((0x8994, 0x899a), (0xcc44, 0xcc46), (case.STACK_BAND[0], case.STACK_BAND[-1] + 1))
EVERY_PAGE_LEAVES_OUT = tuple(sorted((THE_POLL_S_TRAP_SAVE, *FIXED_IN_EVERY_PAGE)))


@functools.cache
def _left_out_of_every_page():
    """`[(lo, hi)]`: the spans of RAM no page's digest reads (above), folded."""
    spans = []
    for at in sorted(at for at in _NOT_COMPARED | SR_SAVE_BYTES | TRAP_FRAME_BYTES if at < addrs.ST_RAM_BYTES):
        if spans and spans[-1][1] == at:
            spans[-1][1] = at + 1
        else:
            spans.append([at, at + 1])
    folded = tuple((lo, hi) for lo, hi in spans)
    # ...AND THEY ARE THESE FOUR (EVERY_PAGE_LEAVES_OUT): the keyboard poll's trap save and frame, one frame under
    # the snapshot's savptr, and by number the SR save words ($8994), the Line-F mask word ($cc44) and the stack
    # band — a list that grew would leave more out, unseen.
    assert folded == EVERY_PAGE_LEAVES_OUT, (
        f"every page leaves out {[(hex(lo), hex(hi)) for lo, hi in folded]}, not "
        f"{[(hex(lo), hex(hi)) for lo, hi in EVERY_PAGE_LEAVES_OUT]}")
    return folded


def image_pages(memory, also=()):
    """The RAM of `memory` (a run's, or a candidate's image) as its pages' digests, what differs by nature left out
    (above; `also`: `(lo, hi, why)` windows a road leaves out beside)."""
    ram = bytearray(memory[:addrs.ST_RAM_BYTES])
    for lo, hi in (*_left_out_of_every_page(), *((lo, hi) for lo, hi, _why in also)):
        ram[lo:hi] = bytes(hi - lo)
    a_qpb_s_place = {page: [] for page in range(0, addrs.ST_RAM_BYTES, IMAGE_PAGE_BYTES)}
    for evb in EVBS:
        at = evb + aes.EVB_PARM
        if int.from_bytes(ram[at:at + LONG_BYTES], "big") in case.STACK_BAND:
            ram[at:at + LONG_BYTES] = bytes(LONG_BYTES)
            a_qpb_s_place[at - at % IMAGE_PAGE_BYTES].append(at.to_bytes(LONG_BYTES, "big"))
    return tuple(hashlib.blake2b(bytes(ram[page:page + IMAGE_PAGE_BYTES]) + b"".join(marked),
                                 digest_size=PAGE_DIGEST_BYTES).hexdigest() for page, marked in a_qpb_s_place.items())


def candidate_s_pages(buf, also=()):
    """...of the candidate's image, as a hook is handed it (`buf`: a C pointer)."""
    return image_pages(ctypes.string_at(buf, addrs.ST_RAM_BYTES), also)


def pages_that_differ(ours, the_rom_s):
    """The pages two `image_pages` differ in, as a refusal names them: `$lo..$hi` each."""
    return [f"${nth * IMAGE_PAGE_BYTES:x}..${(nth + 1) * IMAGE_PAGE_BYTES - 1:x}"
            for nth, (mine, its) in enumerate(zip(ours, the_rom_s)) if mine != its]


DISPATCHED_LINE = "the images at the dispatcher: "


def vet_the_images_at_the_dispatcher(name, ours, the_rom_s):
    """THE IMAGE THE C HOLDS AT EACH DISPATCH OF ITS RUN IS THE ROM'S AT THE SAME DISPATCH (`image_pages` each, in
    order: the candidate's at the dispatcher's hook, the ROM's where its own process reaches dsptch) — as many
    dispatches, and every page equal. The FIRST of a run is what a case ending blocked compares byte for byte; this
    holds the SECOND and every later one too, where a twin's store before the block is undone by the wake after
    it. Refused by the dispatch's ordinal and the pages."""
    assert len(ours) == len(the_rom_s), (
        f"{name}: the C reached the dispatcher {len(ours)} time(s), the ROM's own process {len(the_rom_s)}")
    for nth, (mine, its) in enumerate(zip(ours, the_rom_s)):
        differ = pages_that_differ(mine, its)
        assert not differ, (
            f"{name}: dispatch {nth}: the image the C holds at the dispatcher is not the ROM's where its run reaches "
            f"dsptch the same time — in {', '.join(differ)}")


class _AtTheEntry(Exception):
    """A watched run stopped at the entry of the door call of the ordinal asked for: its memory there, what was
    delivered at it laid in, and the call it makes (`handed_at`)."""

    def __init__(self, memory, call):
        super().__init__()
        self.memory, self.call = memory, call


def _watched_through(name, arguments, pokes, delivered, stop_at=None, *, io_seed=None, blocks=True, budget=None,
                     left_out_beside=()):
    """The ROM's own `addrs.<name>` WATCHED at the door's entries, `delivered` (`deliveries`' `{ordinal: (found,
    wrote)}`) laid into its memory at the entry of each door call of that ordinal, each checked first (`DoorStops`):
    `(calls, memory, result)` — the frames handed, read after; the memory it left, or WHERE THE C STOPS for a call that
    blocks (`blocks`: stopped at the dispatcher inside a call); its result, None where it blocked. Stopped at the entry
    of the call of ordinal `stop_at` instead, by `_AtTheEntry`.

    WHERE THE C STOPS at a call that blocks: the entry's twin runs on to the dispatcher's hook, and its image is the
    ROM's AT DSPTCH — every list, EVB and PD the wait wrote compared (nothing of the switch is stored yet: savestate
    comes after)."""
    calls = Calls()
    memory = make_image(_staged(name, arguments, pokes))

    def opened(pc, sp, memory):
        call = handed_at(pc, sp, memory)
        if len(calls) == stop_at:
            raise _AtTheEntry(bytes(memory), call)
        calls.append(call)
    watch = DoorStops(ENTRIES, ROM_RETURNS, opened, blocks=blocks, delivered=delivered, entered_at=getattr(addrs, name))
    calls.answers = watch.answers       # ...the list the watch goes on filling: read once the run has ended
    watch.images = left_out_beside if left_out_beside is NO_IMAGE_TAKEN else tuple(left_out_beside)
    result = run_watched(memory, getattr(addrs, name), watch, io_seed, budget)
    if result:
        return calls, memory, result
    # (A run ENTERED AT an entry that reached the dispatcher outside any door call blocked in the routine itself.)
    assert calls or watch.entered_at_an_entry, f"{name}: the run blocked before any door call"
    return calls, bytes(memory), result


def rom_entered(name, arguments, pokes, delivered, ordinal):
    """The ROM's own `addrs.<name>` over `pokes` with the frame `arguments`, WATCHED and stopped at the entry of its door
    call of `ordinal`, `delivered` (`{ordinal: (found, wrote)}`) laid in at each entry up to it and at it: `(memory,
    call)` — its memory there, and what the call is handed. THE REFERENCE PATH (with `_watched_through`'s `stop_at` and
    `_AtTheEntry`): the run-per-ordinal scheme `deliveries` replaced, kept for the test that pins the two equal."""
    try:
        _watched_through(name, arguments, pokes, delivered, stop_at=ordinal)
    except _AtTheEntry as stopped:
        return stopped.memory, stopped.call
    raise AssertionError(f"{name}: the ROM's run made no door call of ordinal {ordinal} to interrupt")


# ONE RUN DELIVERS EVERY INTERRUPT (`deliveries`). An interrupt's code is the ROM's, run by the oracle — and the oracle
# is one CPU: an `emu.run` inside a watched run's stop derails it (measured). So at the entry of each door call an
# interrupt is delivered at, the run is SET ASIDE (its memory and register file kept; `emu.bench_abort`), the
# interrupt run over a copy of the memory there, its writes laid in, and the run CONTINUED from that very entry
# (`continued_at`): re-entered there by a bench run seeded with the register file the stop left, its door on the entry
# alone so it stops before executing anything, the return-address slot its entry store overwrote put back. What the
# re-entry cannot carry is the status register — the oracle's forced entry SR again, the condition codes cleared — which
# no Alcyon entry reads before it sets them; and the run every case compares against is not this one but the REPLAY
# (`rom_interrupted`), one run laying the deliveries at no cost, each checked against the memory it lands on
# (`DoorStops`' `delivered`): a continuation that strayed would be refused there by name. Measured ONCE, over every
# interrupted case of the batteries then: the deliveries equal byte for byte those of one run per ordinal, the earlier
# scheme, whose cost grew with the square of the ordinals; PINNED over three cases (`test_aes_event.py`'s
# SEVERAL_DELIVERIES), which the reference's own cost keeps from being every one.
RE_ENTRY_SLOT_BYTES = LONG_BYTES       # the return-address slot the re-entry's sentinel store overwrites


def continued_at(memory, pc, sp, registers):
    """The run set aside at the door entry `pc` (A7 `sp`, `registers` the file the stop left) re-entered there: a bench
    run stopped at `pc` before its first instruction, `memory`'s return-address slot as the call left it."""
    held = bytes(memory[sp:sp + RE_ENTRY_SLOT_BYTES])
    emu.install_chip_seeds()            # no chip declared, as at the run's entry — not whatever ran in between
    result = emu.run_bench(memory, pc, case.long_in(memory, sp + RE_ENTRY_SLOT_BYTES), sp, emu.SENTINEL,
                           max_insns=DERIVATION_INSNS, door=frozenset({pc}),
                           seed_regs=[registers[name] for name in emu.REPORTED_REGS])
    assert (result["status"], emu.bench_door_pc(), result["ninsns"]) == (emu.BENCH_DOOR, pc, 0), (
        f"the run set aside at {pc:#x} was not re-entered there")
    memory[sp:sp + RE_ENTRY_SLOT_BYTES] = held
    return result


def _interrupt_at(interrupts, ordinal, entry):
    """What `interrupts` delivers at the door call of `ordinal` (to `entry`): its entry for that ordinal, or a
    schedule's answer (`typed`) — None for nothing."""
    return interrupts(ordinal, entry) if isinstance(interrupts, Waits) else interrupts.get(ordinal)


def interrupt_at(interrupts, ordinal, entry):
    """`_interrupt_at`, for a driver that takes a run's door-call interrupts itself (`aes_switch.scheduled`: the run
    that takes them at door calls AND at idles); `interrupts` None for a run that names none."""
    return _interrupt_at(interrupts or {}, ordinal, entry)


def begin_a_schedule(interrupts):
    """A run that will ask `interrupts` at its door calls BEGINS: a schedule's waits counted from none (`Waits`)."""
    if isinstance(interrupts, Waits):
        interrupts.begin_run()


def undelivered(interrupts, delivered):
    """What `interrupts` named that the run which took `delivered` (`{ordinal: (found, wrote)}`) never reached: a
    schedule's rows still `pending`, or the ordinals no door call had."""
    if isinstance(interrupts, Waits):
        return interrupts.pending
    return sorted(set(interrupts or ()) - set(delivered))


def _taken(memory, interrupt):
    """`interrupt` (or a tuple of them) run over a copy of `memory`: `(found, wrote)` — what `memory` holds at every
    address it writes, then what it wrote there."""
    image, wrote = bytearray(memory), {}
    for each in _as_sequence(interrupt):
        wrote = merge_pokes(wrote, each(image))
    return {at: bytes(memory[at:at + len(data)]) for at, data in wrote.items()}, wrote


def interrupting(memory, entry, watch, due_at, budget=None):
    """THE ONE LOOP THAT TAKES INTERRUPTS INSIDE A WATCHED ROM RUN (above): the ROM's own `entry` over `memory` (its
    frame at abi.FIRST_ARG), stopped where `watch` stops it, and at each stop ASKED — `due_at(watch, pc)`, before the
    watch takes the stop — for the interrupt due there: None, or `(key, interrupt)` — the run then set aside, the
    interrupt (or tuple of them) taken over the memory as it stands (`_taken`), its writes laid in, the run continued
    from that very stop (`continued_at`). `(delivered, result)` — `{key: (found, wrote)}`, and the run's result, None
    where the watch ended it as blocked (`Blocked`); any other end a watch raises (`Ended`) leaves through here, the
    run aborted. Held to its budget (DERIVATION_INSNS, or the `budget` its row declares: `_budget_of`) by its margin
    over every segment — and from above (`_vet_not_stale`) — each segment's refusals vetted as it ends. The last
    segment's vets run on a run that ENDED (returned or blocked) only: after an interrupt's own run failed, the
    oracle's counters are that run's, and a vet of them would replace its error. WHO ASKS: the door's own deliveries
    (`_run_interrupting`: at the entry of a door call), and a scheduler driver (at the n-th idle)."""
    delivered, spent, insns = {}, 0, _budget_of(entry, budget)
    who = f"the ROM's interrupted run of {entry:#x}"
    result = rom_bench.original_entered(memory, entry, watch.first, max_insns=insns)
    try:
        while result["status"] == emu.BENCH_DOOR:
            pc, sp = emu.bench_door_pc(), emu.bench_door_sp()
            due = due_at(watch, pc)
            if due:
                key, interrupt = due
                spent += result["ninsns"]
                rom_bench.vet_the_run_just_made(who)
                registers = result["regs"]
                emu.bench_abort()
                delivered[key] = _taken(memory, interrupt)
                _lay(memory, delivered[key][1])
                result = continued_at(memory, pc, sp, registers)
            emu.bench_door_arm(watch.stopped(pc, sp, memory))
            left = insns - spent - result["ninsns"]
            assert left > 0, f"{who} did not return within {insns} instructions"
            result = emu.bench_resume(entry, max_insns=left)
    except Blocked:
        result = None
    finally:
        emu.bench_abort()
    rom_bench.vet_the_run_just_made(who)
    _vet_the_margin(entry, spent + _instructions_run(), budget)
    _vet_not_stale(entry, spent + _instructions_run(), budget)
    return delivered, result


def _run_interrupting(memory, entry, interrupts, budget=None):
    """The ROM's own `entry` over `memory`, ONE watched run that takes each interrupt of `interrupts` at the entry of
    its door call (`interrupting`): `(delivered, result)` — `{ordinal: (found, wrote)}`, and the run's result, None
    where it blocked."""
    begin_a_schedule(interrupts)

    def due_at(watch, pc):
        # Asked at an ARRIVAL only: the run's own entry (entered, not called) is no door call, and an interrupt
        # taken there would be door call 0's, delivered a second time when the run reaches it.
        interrupt = _interrupt_at(interrupts, watch.calls, pc) if watch.opens_a_call_at(pc) else None
        return (watch.calls, interrupt) if interrupt else None
    return interrupting(memory, entry, DoorStops(ENTRIES, ROM_RETURNS, blocks=True, entered_at=entry), due_at, budget)


def deliveries(name, arguments, pokes, interrupts, budget=None):
    """What each interrupt of `interrupts` WRITES, run over the ROM's own memory at the entry of the door call it is
    delivered at — `{ordinal: interrupt or (interrupt, ...)}`, or a SCHEDULE `interrupts(ordinal, entry)` answering
    one (or None) at every call (`typed`): `{ordinal: (found, wrote)}` — the bytes that memory held at each address the
    delivery writes, then what it wrote there. ONE run of the routine takes them all (`_run_interrupting`, under the
    `budget` its row declares); an ordinal the run never reaches, or a schedule left with interrupts `pending`, is
    refused by name."""
    delivered, counted = _deliveries(name, tuple(arguments), pokes, interrupts, budget)
    if isinstance(interrupts, Waits):
        interrupts.counted_to(counted)  # ...as the run left the schedule, whether it was made here or kept
    return delivered


@kept_on_disk
def _deliveries(name, arguments, pokes, interrupts, budget):
    """`deliveries`' one run — a ROM-only derivation, kept by content: the routine, its frame, the machine, the
    interrupts by what they are (a schedule by its rows, `Waits.derived_content`) and the budget. `(the deliveries,
    how far the run counted a schedule)` — the second what the run leaves of a `Waits` beside its answer, so a
    caller finds the schedule as a run leaves it either way."""
    memory = make_image(_staged(name, arguments, pokes))
    delivered, _result = _run_interrupting(memory, getattr(addrs, name), interrupts, budget)
    never_made = undelivered(interrupts, delivered)
    assert not never_made, f"{name}: the ROM's run made no door call to deliver {never_made} at"
    return delivered, interrupts.counted() if isinstance(interrupts, Waits) else None


def rom_interrupted(name, arguments, pokes, interrupts, delivered=None, budget=None):
    """The ROM's own `addrs.<name>` over `pokes` with the frame `arguments`, WATCHED at the door's entries, each of
    `interrupts` delivered over its memory at the entry of that door call (`deliveries`; or `delivered`, derived
    already) — then REPLAYED: one run laying them in at no cost, each checked against the memory it lands on
    (`_watched_through`), the run every shore is compared with: `(calls, delivered, memory, result)` — the frames handed
    (each read after the interrupt), the deliveries (`{ordinal: (found, wrote)}`), the memory it left (or, for a run
    that BLOCKS, its memory at dsptch), and the run's result (None: it blocked). `budget`:
    the case's own, declared (`_budget_of`), which both runs are held to."""
    if delivered is None:
        delivered = deliveries(name, arguments, pokes, interrupts, budget)
    calls, memory, result = _watched_through(name, arguments, pokes, delivered, budget=budget)
    return calls, delivered, memory, result


def delivering(delivered, entered_at=None):
    """A watch over a run of a row whose interrupts are DELIVERED (`register_interrupted`): `delivered` laid at its door
    calls, each checked first, and a call that reaches the dispatcher refused by name (`DoorStops`) — the ROM's replays
    (`replayed`) and Tier 3's original. `entered_at`: the PC the run starts at — a door entry's own row makes no door
    call of its entry (`DoorStops.entered_at`). A row that SWITCHES (`Switches`) is watched at the dispatcher instead
    (`aes_switching.the_rom_s`): its interrupts laid at its idles, the processes its dispatcher enters followed."""
    if switching(delivered):
        import aes_switching            # ...which imports this module
        return aes_switching.the_rom_s(delivered, entered_at)
    return DoorStops(ENTRIES, ROM_RETURNS, blocks=True, delivered=delivered, entered_at=entered_at)


def replayed(image, entry, delivered, regs=None, io_seed=None):
    """The ROM's own `entry` over `image` (its frame staged), `delivered` laid at its door calls (`delivering`, which
    checks each), answered as `emu.run` answers — `(final, writes, regs)` (`rom_bench.watched_original`) — and refused
    as it is: what an unwatched run of the same row would be, for every consumer that runs a row's ORIGINAL (the
    snapshot's sweeps)."""
    watch = delivering(delivered, entry)
    final, writes, regs_out = rom_bench.watched_original(bytearray(image), entry, watch, regs, io_seed=io_seed)
    rom_bench.vet_the_run_just_made(f"the ROM's replay of {entry:#x}")
    if switching(delivered):            # ...and a row that switches ended as it says: its idles made, its deliveries laid
        watch.vet_ended(f"the ROM's replay of {entry:#x}")
    return final, writes, regs_out


def _started_with(started, at):
    """The byte a ROM run began with at `at`: `started` the image it ran over — or the merged pokes it was staged with
    (`aes.staged`), read off them with the base image under: no sixteen-megabyte image is made for four bytes."""
    if not isinstance(started, dict):
        return started[at]
    return next((data[at - start] for start, data in started.items() if start <= at < start + len(data)), BASE_IMAGE[at])


def not_compared_where_the_rom_stored(rom_memory, started):
    """THE ONE RULE FOR AN SR SAVE WORD, wherever two shores are compared: what neither compares is `_NOT_COMPARED`
    and an SR save byte (`SR_DROPS`) ONLY WHERE THE ROM'S RUN STORED IT — where `rom_memory`, the ROM's memory AS IT IS
    COMPARED, no longer holds the byte the run `started` with (the image it ran over, or the pokes it was staged
    with). A byte the ROM's run left alone is compared, and a C that wrote it differs.

    BY THE MEMORY, NOT BY THE RUN'S LEDGER, because the memory is what is compared and the ledger is not always its
    own: a run stopped at the ENTRY of the call that blocks has stored more since. (A store of the very byte the run
    started with leaves nothing to drop: the C, which stores no SR off target, holds that byte too — and one that
    wrote another there is seen, where a ledger's word for it would have hidden it.)"""
    return _NOT_COMPARED | frozenset(at for at in SR_SAVE_BYTES if rom_memory[at] != _started_with(started, at))


def _with_the_deliveries_laid(staged, delivered):
    """What an INTERRUPTED run's memory would hold had the run itself stored nothing: the machine it was `staged`
    with and every delivery laid over it, in the order of their door calls. The start `interrupted` asks the rule
    above about — its ROM memory is not one run's: a DELIVERED interrupt's own store of an SR save word is laid into
    the C's image too (`_laid_into`), and is no store of the ROM's run to drop the byte for."""
    return merge_pokes(staged, *(wrote for _ordinal, (_found, wrote) in sorted(delivered.items())))


def differing(image, rom_memory, not_compared=None):
    """The addresses `image` and `rom_memory` differ at, outside what neither shore compares (`_NOT_COMPARED`, or
    `not_compared`)."""
    excluded = _NOT_COMPARED if not_compared is None else not_compared
    return [at for at in _differing_addresses(image, rom_memory) if at not in excluded]


def first_to_differ(ours, the_rom_s):
    """Where two sequences first differ: the index of the first element that is not the other's — the shorter's
    length where one only runs on past it — or None for two equal ones."""
    differ = next((nth for nth, (mine, its) in enumerate(zip(ours, the_rom_s)) if mine != its), None)
    if differ is None and len(ours) != len(the_rom_s):
        differ = min(len(ours), len(the_rom_s))
    return differ


def _describe_differences(name, image, rom_memory, differ):
    shown = ", ".join(f"{at:#x} oracle={rom_memory[at]:#04x} cand={image[at]:#04x}"
                      for at in differ[:COMPARED_DIFFERENCES_SHOWN])
    return f"{name}: {len(differ)} bytes differ from the ROM's run: {shown}"


describe_differences = _describe_differences      # ...for a battery that words its own compare (the switch's, ev_multi's)


def _answer_at_its_width(name, d0):
    """D0 at the width `addrs.<name>`'s core declares its answer (`vdi.ALCYON`): its word, its long, or None."""
    restype = vdi.ALCYON[name].restype
    return None if restype is None else d0 & ((1 << (8 * ctypes.sizeof(restype))) - 1)


# How a WATCHED run refuses a call that reached dsptch (`DoorStops`' `blocks`): the watch stops there before
# dsptch decides which, so its words name both.
SWITCHES_AT_THE_DISPATCHER = "the call would switch processes (block or yield)"


HELD_BY_INTERRUPTED = HeldElsewhere(
    "`interrupted` holds them itself, against the watched run it has already made — after it has held how the run "
    "ended and the image there, so that a run that ended otherwise is refused by what it did, not by a call's count")


def interrupted(name, arguments, machine, interrupts, *, objects=False, seconds=CHILD_RETURN_SECONDS, switches=BLOCKS,
                not_compared=None, delivered=None, second_differential=True, budget=None):
    """`addrs.<name>` over `machine` with the frame `arguments`, TAKEN THROUGH `interrupts` — `{ordinal: interrupt or
    (interrupt, ...)}`, each delivered at the entry of the door call of that ordinal (`press`, `release`, `move_to(x,
    y)`, `key`), or a schedule (`typed`) — on both shores: the ROM's own run (`rom_interrupted`) and the C in a child
    (`bind_in_a_child`, the walked routines served with `objects`), the C held to the ROM: whether it returned (else it
    switched processes at the same call, refused as one that `switches`), its answer, every frame the door was handed and
    the whole image (`differing`, outside `not_compared` — by default `_NOT_COMPARED` and the SR save words the ROM's
    run stored, `not_compared_where_the_rom_stored`) — and, at each delivery, its image where the delivery writes
    (`_laid_into`). A case whose ROM run RETURNS is then taken through the bench's SECOND
    DIFFERENTIAL too (`bench_differential`), which a child cannot make — every one, by construction, so no list of them
    can fall behind the batteries (a case that IS a registered row is priced by Tier 3 already, and skipped there);
    `second_differential=False` only for a registered row's companion, whose row is priced. `delivered`: the
    deliveries, derived already (`rom_interrupted`). Answers `Interrupted(calls, returned, answer, rom_memory, image,
    delivered, staged, stderr)` for the case's own assertions — `staged` the machine with the frame, as a row registers
    it; `stderr` what the C's child printed (a routine's own child doors may report there: `declare_child_doors`).
    `budget`: the case's own derivation budget, DECLARED from its measured run (`_budget_of`) — a session too long for
    DERIVATION_INSNS' margin; every ROM run of the case is held to it, both ways."""
    calls, delivered, rom_memory, result = rom_interrupted(name, arguments, machine, interrupts, delivered, budget)
    returncode, stderr, image = door_child(name, arguments, machine, door_calls=HELD_BY_INTERRUPTED, objects=objects,
                                           interrupts=delivered,
                                           before=CHILD_DOORS.get(name, ""), seconds=seconds, answered=True)
    returned = result is not None
    # A return that answered no arrival is the case's failure by the door's own words, whichever way the ROM's run
    # ended (the wrapper and the hook lost count of one another: no later compare means what it says).
    assert returncode != CHILD_RETURN_REFUSED, f"{name}: a twin's return answered no arrival in flight:\n{stderr}"
    if returned:
        assert returncode == 0, f"{name}: the ROM's run returned, the C's child did not:\n{stderr}"
        answer = _answer_at_its_width(name, result["d0"])
        assert vdi_helpers.answer_in(stderr) == answer, (
            f"{name}: the C answered {vdi_helpers.answer_in(stderr)}, the ROM's run {answer}")
    else:
        assert returncode != 0 and switches in stderr, (
            f"{name}: the ROM's run switches at a door call, the C's did not — refused as one that {switches}:\n{stderr}")
        answer = None
    assert handed_in(stderr) == calls, f"{name}: the door was handed {handed_in(stderr)}, the ROM's run hands {calls}"
    staged = aes.staged(name, arguments, machine)
    if not_compared is None:
        not_compared = not_compared_where_the_rom_stored(rom_memory, _with_the_deliveries_laid(staged, delivered))
    by_nature = frozenset() if returned else _a_door_user_s_parked_qpb(name, calls, image, rom_memory)
    differ = differing(image, rom_memory, not_compared | by_nature)
    assert not differ, _describe_differences(name, image, rom_memory, differ)
    # ...and, once the END is the ROM's byte for byte, what each door call ANSWERED and LEFT where it returned: what
    # a caller did not read, and what a later call put right.
    vet_the_answers_handed_back(name, answered_in(stderr), calls.answers)
    if returned and second_differential:
        bench_differential(name, arguments, machine, interrupts, budget, Derived(delivered, rom_memory))
    return Interrupted(calls, returned, answer, rom_memory, image, delivered, staged, stderr)


@functools.cache
def _tier3():
    """bench/tier3.py and the cross-compiled cores (`RomBench`), loaded where the first case asks: the module imports
    every battery, so importing it here at this module's import would be circular."""
    tier3 = bench_tier3()
    return tier3, tier3.RomBench()


@functools.cache
def _registered_image(row_name):
    """The staged image of the registered row `row_name` (`INTERRUPTED_ROWS`), as its run starts."""
    row = INTERRUPTED_ROWS[row_name]
    return bytes(make_image(aes.staged(row.name, row.arguments, row.pokes)))


def _registered_twin(name, arguments, pokes, delivered):
    """The registered row (`register_interrupted`) this case's row would BE — the same routine, the same staged image
    and the same deliveries — or None."""
    image = bytes(make_image(aes.staged(name, arguments, pokes)))
    return next((row_name for row_name, row in INTERRUPTED_ROWS.items()
                 if row.name == name and row.delivered == delivered and _registered_image(row_name) == image), None)


def bench_differential(name, arguments, machine, interrupts, budget=None, derived=None):
    """The bench's SECOND DIFFERENTIAL of a case TAKEN THROUGH `interrupts` whose ROM run returns: the case as a row
    (`interrupted_row`), measured (`tier3.measure`) — the callee-saved registers, the odd-access surface, the write
    ledger the mask word's drop is vetted against, both sides' refusal tallies, the streams, the whole image: what the
    C's Tier 1 child cannot report. A case whose row IS a registered one (`_registered_twin`) is not measured a third
    time: Tier 3 prices that row (`make bench`'s table, `test_tier3.py`'s row test) — it must be priced, by name.
    `budget`: the case's own derivation budget, declared (`_budget_of`). `derived`: what the case's ROM run has
    derived already (`_settled_interrupted`), so a session is not derived a second time for its row — TRUSTED, not
    re-derived, where `machine` already keeps `savptr` in the band: the row is then priced over the deliveries handed
    in. Only `interrupted` may pass it, with the deliveries and memory of the ROM run it has just made over this very
    machine and these interrupts; a caller holding deliveries from anywhere else passes None, and the run is made."""
    settled = _settled_interrupted(name, arguments, machine, interrupts, budget, derived)
    pokes, delivered = settled
    twin = _registered_twin(name, arguments, pokes, delivered)
    if twin:
        assert twin in {row[0] for row in aes.ROWS.cases}, f"{twin}: its deliveries are recorded, but no priced row"
        return
    tier3, bench = _tier3()
    row = tier3._row(_interrupted_row("taken through interrupts", name, arguments, pokes, delivered))
    tier3.measure(row._replace(dropped=aes.LINE_F_MASK_WINDOW + sr_drops_of(settled.sr_words)), bench)


# ---- A DOOR USER'S CALL THAT BLOCKS, TAKEN ON THROUGH THE WAKE ------------------------------------------------------------
# A door user that waits (a dialog with nothing typed, a box loop with the mouse still, a menu dropped) has two
# halves, as a wait of the event layer has: what it does UP TO THE CALL THAT BLOCKS, and what it does once the
# dispatcher runs it again. The first is held where the C stops when nothing models the switch — at the dispatcher's
# hook, against the ROM's memory at dsptch (`interrupted`, ending blocked). THE SECOND IS A ROW THAT SWITCHES
# (`aes_switching`): the same call, the interrupt that wakes it delivered where the machine waits for one — at the
# dispatcher's idle — and the loop run on to its return, by the ROM through its own dispatcher and by the C through
# the host's model with THE DOOR BOUND IN THE SAME CHILD (`aes_switch.modelled`'s `door`: every arrival noted, the
# twin run on through the dispatcher's hook). Its interrupts are of two kinds, and one
# derivation takes both (`aes_switch.scheduled`): `at_calls`, at the entry of a door call (what a loop's earlier
# waits take, as `interrupted` delivers them), and `at_idle`, at an idle (what wakes a wait that blocked).
# The three spellings a battery needs — a module that imports this one imports the registrar, so each asks for it
# where it is called.
def woken_row(label, name, arguments, machine, at_idle, at_calls=None, *, objects=False, answered=True, budget=None):
    """A DOOR USER'S CALL THAT BLOCKS AND IS WOKEN, as a row that switches (`aes_switching.SwitchingRow`): `machine` a
    zero-argument builder, `at_idle` `{idle: interrupt}`, `at_calls` `{door call: interrupt}` or a schedule
    (`Waits`); `objects`: its C walks trees (the walked routines served in its child); `answered` False for an arm
    that sets no D0; `budget`: its own derivation budget, declared (`_budget_of`: a whole session of the file
    selector). The routine's declared child doors (`CHILD_DOORS`) are its child's."""
    import aes_switch
    import aes_switching
    door = aes_switch.DoorUser(bool(objects), CHILD_DOORS.get(name, ""))
    return aes_switching.SwitchingRow(label, name, tuple(arguments), machine, dict(at_idle or {}), answered, at_calls, door,
                                      budget=budget)


def held_through_its_wake(row):
    """`row`'s TIER 1 (`aes_switching.companion`): the C through the host's model, the door bound, held to the ROM's
    own run through its dispatcher — the same idles, the same answer, every frame the door was handed, every byte
    outside the run's own stack. Its `CompanionRun`, for the case's own assertions (`.answer`, `.calls`, `.image`,
    `.entered`)."""
    import aes_switching
    return aes_switching.companion(row)


def blocked_then_woken(row, switches=BLOCKS):
    """BOTH HALVES OF A DOOR USER'S CALL THAT SWITCHES: `(held, ran)` — `held` the call taken through its door-call
    interrupts alone, which ENDS AT THE DISPATCHER: the C refused at its hook as one that `switches` (BLOCKS, or
    YIELDS), its whole image the ROM's AT DSPTCH (`interrupted`: what a transient store before the switch would show
    in, and no later compare); `ran` the same call taken on through the dispatcher to its return
    (`held_through_its_wake`)."""
    held = interrupted(row.name, row.arguments, row.machine(), row.at_calls or {}, objects=row.door.objects,
                       switches=switches, budget=row.budget)
    assert not held.returned, f"{row.name}: the premise — with nothing delivered at an idle the call switches — does not hold"
    return held, held_through_its_wake(row)


def register_woken(row):
    """`row` REGISTERED: one priced row that switches (`aes_switching.register_row`) — a door user's, held on TWO
    COUNTS like any row round a rebound entry, its call open across the switch."""
    import aes_switching
    return aes_switching.register_row(row)


# ---- A SESSION PRICED BY ITS SLICES -----------------------------------------------------------------------------------
# A long interactive routine — the file selector listing a directory, scrolled, clicked and typed into before its
# Return — is ONE call no single row prices honestly: its whole run is hundreds of thousands of instructions (past
# `emu.run`'s 200,000, the bench's cap on an unwatched original), and one ratio over all of it lets the listing's bulk
# dilute a scroll's or a key's — the worst shape hidden in the average. So the session is priced by its SLICES, a row
# each: the run between two ARRIVALS both shores make at the SAME PC, running the same bytes from there —
#   * a DOOR CALL (`door_call`: the nth call of one of the door's entries — a wait, the screen's lock taken);
#   * a TRAP TAKEN (`trap_taken`: the nth arrival at a trap's handler, outside any door call — a VDI call, a GEMDOS
#     call: what cuts a stretch that makes no door call);
#   * the routine's ENTRY and its RETURN.
# BOTH SHORES RUN THE WHOLE SESSION — the C cannot be entered in the middle of its routine — watched and MARKED at the
# two arrivals (`Marks`, `DoorStops.marked_with`): what each has spent there, and its memory. The slice's cost is the
# difference of the two marks, shore by shore (`spent`); and the slice is the ROM's only if the C REACHED ITS START AS
# THE ROM DID, which is checked, by name (`vet_the_marks_agree`): the same door call (a slice started a call late is
# another slice), the same memory outside what neither shore compares (a C that diverged before the start runs the
# slice over another machine — its ratio would be of two different computations), and the same again at its end. The
# whole run's own differential still holds everything else (the bench's second differential: registers, ledgers, the
# final image).
# EACH SLICE IS UNDER THE CAP (SLICE_INSNS, on the ROM's own run of it): one over it is refused by name, to be cut
# finer — at a trap, where no door call falls inside it.
# WHAT A MARK HOLDS, AND WHAT IT DOES NOT. A DOOR CALL is matched by its ordinal and by the door calls entered before
# it (`calls`, held equal on both shores). A TRAP ARRIVAL is matched by its ORDINAL AT ITS HANDLER and by the MEMORY
# there — nothing counts the traps taken before a mark against the ROM's. So work that touches only registers and
# the routine's own stack (which no mark compares) may sit on either side of a trap in our build and on the other in
# the ROM's: its cost then moves between the two slices that meet at that trap, unseen by either mark. Between two
# REGISTERED slices that is a wash; at the edge of a registered slice it would carry cost out of the table, into a
# stretch no row prices. What keeps it in is THE PARTITION (`bench/tier3.py`'s `uncovered_stretches`, held by
# `test_tier3.py`): each session is also cut whole — at every DOOR CALL (the arrivals both shores are held to by
# count) and at its registered slices' own ends, both shores' timelines held to the same arrivals after the same door
# calls — and every stretch no registered slice covers is priced like a slice and held at or under the routine's
# worst registered row. Cost that left a slice across a trap is then in the stretch beside it, and priced there.
# A SLICE'S MARKS ARE ONE PROCESS'S — THE ROW'S (a session whose run SWITCHES: a wait of it blocks, the machine leaves
# by the dispatcher and comes back by it; `register_woken_slices`). A mark is an ARRIVAL OF THE ROW'S PROCESS, so:
#   * NO MARK IS TAKEN INSIDE A FOREIGN WINDOW (another process's turn, `aes_switching`): the watch that follows the
#     run through the dispatcher arms none of the door watch's stops there, the marks are told where a window opens
#     and closes (`Marks.foreign_window_opened` / `_closed`, through `DoorStops`), and an arrival handed to them in
#     between is REFUSED BY NAME — the screen manager makes door calls and takes traps at the very PCs a slice is
#     cut at, and one counted would shift every later ordinal of the row's own;
#   * WHAT A MARK HOLDS A RUN TO HAVE SPENT IS WHAT THE ROW'S PROCESS SPENT: each running total net of the windows
#     closed before it (`Marks._spent`) — instructions and cycles too, so the cap is held on the row's own run and a
#     slice's cost is never another process's. The windows inside a slice are kept beside it (`foreign_inside`: how
#     many, and what they cost), the two shores held to the same ones (`vet_the_marks_agree`: an end reached on the
#     other side of another process's turn is another slice);
#   * THE MEMORY AT A MARK IS COMPARED OUTSIDE WHAT THE ROW DROPS (`tier3._differing_at_a_mark`) — a switching row's
#     drops among them (the saved context, the dispatcher's stack, the mask word, a bracket's SR word), each of which
#     differs by nature from the first dispatch on, long before the run's end.
SLICE_INSNS = DIFFERENTIAL_INSNS       # `emu.run`'s own default budget: what one unwatched row may spend
ENTRY, RETURN = "the routine's entry", "the routine's return"


class At(namedtuple("At", "pc nth")):
    """An ARRIVAL: the `nth` time (from 0) a run reaches `pc` outside a door call — a door's entry (`door_call`) or a
    trap's handler (`trap_taken`)."""

    def __str__(self):
        return f"arrival {self.nth} at {self.pc:#x}"


def door_call(entry, nth):
    """The `nth` call (from 0) of the door's `entry` (`addrs.AES_ROM_EV_MULTI` ...): a slice's end."""
    assert entry in ENTRIES, f"{entry:#x} is no entry of the event door ({', '.join(ENTRY_NAMES)})"
    return At(entry, nth)


def trap_taken(handler, nth):
    """The `nth` arrival (from 0) at the trap handler `handler`, outside any door call and any marked trap: a slice's
    end where the routine makes no door call. `handler` is the PC BOTH shores' trap reaches — the ROM's own
    (`trap_handler`: GEM's `trap #2` for a VDI call), or a stub a case stages in the vector.

    THE ORDINAL IS OF THE RUN'S MARKS: inside a marked trap nothing is an arrival, so were a session cut at two
    handlers ONE OF WHICH IS TAKEN INSIDE THE OTHER (a GEMDOS call the VDI makes, both marked), the inner one's
    arrivals would count in a run marked at it alone (`slice_cost`, a row's own runs) and not in the session's one
    run marked at both (`Marks`' `others`) — the same ordinal, two arrivals. No session does today (the selector's
    sessions are cut at the VDI's handler and at the replay's GEMDOS stub, which takes no trap, and no VDI call of
    theirs reaches GEMDOS); a run that did is REFUSED BY NAME where it happens (`DoorStops.stopped`)."""
    assert handler not in ENTRIES, f"{handler:#x} is a door entry: name its call with `door_call`"
    return At(handler, nth)


def trap_handler(vector, pokes=None):
    """The handler the exception `vector` (its address: `addrs.VECTOR_TRAP_GEM` ...) holds over `pokes`."""
    return case.long_in(make_image(pokes or {}), vector) & OS_BUS_ADDR_MASK


VDI_TRAP = trap_handler(addrs.VECTOR_TRAP_GEM)        # the ROM's own `trap #2` handler: where a VDI call arrives
GEMDOS_TRAP = trap_handler(addrs.VECTOR_TRAP_GEMDOS)  # ...and its `trap #1` handler's: a GEMDOS call
Slice = namedtuple("Slice", "start stop")
# `windows`: the foreign windows closed before the mark; `foreign`: what they spent, total by total (`Marks`).
Mark = namedtuple("Mark", "calls spent memory windows foreign", defaults=(0, None))
A_MARK_OF_ANOTHER_PROCESS = ("a mark is an arrival of the ROW's process, and this one is inside a foreign window — "
                             "another process's turn: its door calls and its traps are none of the session's slices")
Arrival = namedtuple("Arrival", "at calls spent")


class Marks:
    """The MARKS of one run of a session at the two ends of `slice_` (a `Slice`): at each, the door calls entered so
    far, what the run has spent (`cost()`: a dict of running totals — instructions, cycles, whatever its shore is
    priced on) and its memory there. Taken by the run's watch at each arrival (`DoorStops.marked_with`) and, for an
    end that is the routine's RETURN, by whoever made the run, once it has ended (`returned`). ENTRY is marked from the
    first: nothing spent, no door call made, and no memory — both shores start from one image.

    ONE RUN MARKS EVERY SLICE OF ITS SESSION: `others` are the session's other slices, marked at their ends by the
    same run, and `cut_to(slice_)` is this run's marks read for another of them — so a session's rows are priced off
    one pair of runs, not a pair each. With `every_door_call`, the run's `timeline` is kept too: an `Arrival` at
    EVERY door call it makes and at every end it is marked at, in order, the RETURN's last, each with what the run
    had spent — so what each shore spent between any two of them can be read, and the stretches no slice prices
    priced as well (`bench/tier3.py`'s `uncovered_stretches`). Off by default: the cost is read at every door call.

    THE MARKS ARE THE ROW'S PROCESS'S (a run that switches; the note above): told where a foreign window opens and
    closes, they take no arrival inside one (refused by name) and keep every total NET of the windows closed so
    far — `spent` at a mark, and on the timeline, is what the row's own process had spent; `windows` and `foreign`
    of a mark are how many windows closed before it and what they cost."""

    def __init__(self, slice_, cost, others=(), every_door_call=False):
        for start, stop in (slice_, *others):
            assert start != RETURN and stop != ENTRY and start != stop, f"no run is between {start} and {stop}"
        self.slice, self._cost = slice_, cost
        self._ends = frozenset(end for each in (slice_, *others) for end in each)
        marked = (*(ENTRIES if every_door_call else ()), *(end.pc for end in self._ends if isinstance(end, At)))
        self._arrivals = dict.fromkeys(marked, 0)
        self._taken = {ENTRY: Mark(0, None, None)}
        self.timeline = [] if every_door_call else None
        self._window_at, self._in_windows, self._windows = None, {}, 0

    def foreign_window_opened(self):
        """Another process than the row's is entered: no arrival is the row's until it is resumed."""
        assert self._window_at is None, "a foreign window opened inside a foreign window: the watch lost a resume"
        self._window_at = self._cost()

    def foreign_window_closed(self):
        """...and the row's process is resumed: what the window spent comes off every total from here on."""
        assert self._window_at is not None, "a foreign window closed that never opened"
        self._in_windows = {name: self._in_windows.get(name, 0) + total - self._window_at[name]
                            for name, total in self._cost().items()}
        self._window_at, self._windows = None, self._windows + 1

    def _spent(self):
        """The run's totals AS THE ROW'S PROCESS SPENT THEM: `cost()`, net of every foreign window closed so far."""
        return {name: total - self._in_windows.get(name, 0) for name, total in self._cost().items()}

    def cut_to(self, slice_):
        """This run's marks, read for `slice_` — one of the slices it was marked at (`others`)."""
        assert set(slice_) <= self._ends, f"the run was not marked at {slice_.start} and {slice_.stop}"
        cut = copy.copy(self)           # the same run: its marks and timeline shared, its slice its own
        cut.slice = slice_
        return cut

    @property
    def traps(self):
        """The PCs this run is stopped at beyond the door's entries: its ends' that are trap handlers."""
        return frozenset(self._arrivals) - frozenset(ENTRIES)

    def arrived(self, pc, calls, memory):
        """The run arrived at `pc` (a door entry, a marked trap's handler) with `calls` door calls entered."""
        if pc not in self._arrivals:
            return
        assert self._window_at is None, f"arrival {self._arrivals[pc]} at {pc:#x}: {A_MARK_OF_ANOTHER_PROCESS}"
        here = At(pc, self._arrivals[pc])
        self._arrivals[pc] += 1
        on_the_timeline = self.timeline is not None and (pc in ENTRIES or here in self._ends)
        if not (on_the_timeline or here in self._ends):
            return
        spent = self._spent()
        if on_the_timeline:
            self.timeline.append(Arrival(here, calls, spent))
        if here in self._ends:
            self._taken[here] = Mark(calls, spent, bytes(memory), self._windows, dict(self._in_windows))

    def returned(self, calls):
        """The run RETURNED, `calls` door calls made in all: marked, its memory left to the whole run's differential."""
        assert self._window_at is None, f"the run's return: {A_MARK_OF_ANOTHER_PROCESS}"
        self._taken[RETURN] = Mark(calls, self._spent(), None, self._windows, dict(self._in_windows))
        if self.timeline is not None:
            self.timeline.append(Arrival(RETURN, calls, self._taken[RETURN].spent))

    def at(self, end, whose):
        """The mark at `end` — refused by name where the run (`whose`) never arrived there."""
        assert end in self._taken, (
            f"{whose} never reached {end}: the session has no such slice (its arrivals at that PC: "
            f"{self._arrivals.get(getattr(end, 'pc', None), 0)})")
        return self._taken[end]

    def ends(self, whose):
        """`(start, stop)`: the two marks — refused by name where the run reached the stop no later than the start."""
        start, stop = (self.at(end, whose) for end in self.slice)
        if start.spent is not None:
            assert stop.spent["insns"] > start.spent["insns"], (
                f"{whose} reached {self.slice.stop} (after {stop.spent['insns']} instructions) before "
                f"{self.slice.start} (after {start.spent['insns']}): no slice runs backwards")
        return start, stop

    def spent(self, whose):
        """What the run spent INSIDE the slice: each of `cost()`'s totals at the stop, less what it was at the start."""
        start, stop = self.ends(whose)
        return {name: total - (start.spent or {}).get(name, 0) for name, total in stop.spent.items()}

    def foreign_inside(self, whose):
        """THE FOREIGN WINDOWS INSIDE THE SLICE: `(how many, {total: what they spent})` — the windows closed between
        its two marks, in neither shore's figures for it (`spent` is net of them)."""
        start, stop = self.ends(whose)
        before = start.foreign or {}
        return stop.windows - start.windows, {name: total - before.get(name, 0) for name, total in (stop.foreign or {}).items()}


def vet_the_marks_agree(case_name, ours, the_rom_s, differing_at):
    """THE SLICE IS THE SAME SLICE ON BOTH SHORES: our run's marks (`ours`, a `Marks`) against the ROM's, end by end —
    reached after the same number of door calls AND OF FOREIGN WINDOWS (a run that switches: an end reached on the
    other side of another process's turn is another slice, its cost net of another thing), and holding the same
    memory there (`differing_at(ours, the ROM's)`: the addresses two memories differ at, outside what neither shore
    compares). Refused by name: a slice OUR run starts at another door call than the ROM's, a run that DIVERGED
    BEFORE THE SLICE'S START, one that diverged inside it."""
    pairs = zip(ours.slice, the_rom_s.slice, ours.ends("our run"), the_rom_s.ends("the ROM's run"),
                ("starts", "ends"), ("before the slice's start", "inside the slice"))
    for end, the_rom_s_end, mine, the_rom, verb, where in pairs:
        assert mine.calls == the_rom.calls, (
            f"{case_name}: our slice {verb} at door call {mine.calls} ({end}) where the ROM's {verb} at door call "
            f"{the_rom.calls} ({the_rom_s_end}) — another slice of the session than the ROM's")
        assert mine.windows == the_rom.windows, (
            f"{case_name}: our slice {verb} ({end}) after {mine.windows} foreign window(s) where the ROM's {verb} after "
            f"{the_rom.windows} — the mark lies on the other side of another process's turn: another slice than the "
            f"ROM's, net of another thing")
        if mine.memory is None:
            continue
        differ = differing_at(mine.memory, the_rom.memory)
        shown = ", ".join(f"{at:#x} the ROM's={the_rom.memory[at]:#04x} ours={mine.memory[at]:#04x}"
                          for at in differ[:COMPARED_DIFFERENCES_SHOWN])
        assert not differ, (
            f"{case_name}: our run diverged {where} — at {end} (door call {mine.calls}) {len(differ)} bytes differ "
            f"from the ROM's run there: {shown}")


# A byte of the door's own staging band no case stages, reads or writes: where a RED test takes a run ASTRAY — a
# divergence nothing else shows.
UNREAD_BYTE = BAND_AT + BAND_BYTES - 1


def astray(watch, flips):
    """`watch` with its run taken ASTRAY (a RED test's build): UNREAD_BYTE inverted in the run's memory at each stop
    `flips(watch, nth)` says — `nth` the stop's ordinal, the watch as it stands before the stop is taken. Inverted
    twice, the byte is the ROM's again: a run astray over a stretch and back, which only a mark inside it can see."""
    stopped, stops = watch.stopped, itertools.count()

    def inverted(pc, sp, memory):
        if flips(watch, next(stops)):
            memory[UNREAD_BYTE] ^= 0xFF
        return stopped(pc, sp, memory)
    watch.stopped = inverted
    return watch


def vet_under_the_slice_cap(case_name, slice_, insns):
    """A slice the ROM's own run spends `insns` instructions in is under SLICE_INSNS — else refused by name."""
    assert insns <= SLICE_INSNS, (
        f"{case_name}: the slice from {slice_.start} to {slice_.stop} runs {insns} ROM instructions, past SLICE_INSNS "
        f"({SLICE_INSNS}): cut it finer — at a door call inside it, or at a trap it takes (`trap_taken`)")


def _marked_run(entry, memory, delivered, marks, budget):
    """The ROM's own `entry` over `memory` (its frame staged, written in place), `delivered` laid at its door calls,
    WATCHED and marked by `marks` (`Marks`, `Timeline`): the door calls it made. The run must return — a session priced
    by its slices ends — under the `budget` it declares (`_budget_of`)."""
    watch = DoorStops(ENTRIES, ROM_RETURNS, blocks=True, delivered=delivered, entered_at=entry).marked_with(marks)
    result = run_watched(memory, entry, watch, budget=budget)
    assert result, f"{entry:#x}: a session priced by its slices returns — this one switches processes at a door call"
    return watch.calls


def rom_sliced(name, arguments, pokes, delivered, slice_, *, budget=None, **marked):
    """The ROM's own `addrs.<name>` over `pokes` with the frame `arguments`, `delivered` laid at its door calls, WATCHED
    and MARKED at `slice_`'s ends (`Marks`, each mark `run_cost()` and the memory there; `marked` its options: the
    session's other slices, every door call): `(marks, memory)` — its marks and the memory it left. The ROM's side of
    a slice's pricing, and the whole of a slice's measurement where the ROM is the oracle on both shores."""
    marks, memory = Marks(slice_, run_cost, **marked), make_image(_staged(name, arguments, pokes))
    marks.returned(_marked_run(getattr(addrs, name), memory, delivered, marks, budget))
    return marks, memory


class Timeline:
    """Every arrival of one run at the door's entries and at the trap handlers `traps`, in order (`arrivals`: an
    `Arrival` each — the `At` it is, the door calls entered so far, what the run had spent): a watch's marks
    (`DoorStops.marked_with`), for choosing where a session is cut."""

    def __init__(self, traps=()):
        self.traps = frozenset(traps)
        self._counted, self.arrivals = {}, []

    def arrived(self, pc, calls, _memory):
        nth = self._counted.get(pc, 0)
        self._counted[pc] = nth + 1
        self.arrivals.append(Arrival(At(pc, nth), calls, run_cost()))

    def foreign_window_opened(self):
        raise AssertionError("a Timeline is of a run that switches nowhere (`_marked_run`): its arrivals are counted "
                             "in whichever process makes them — cut a session that switches by its `Marks`")

    foreign_window_closed = foreign_window_opened


def rom_timeline(name, arguments, pokes, delivered, traps=(), *, budget=None):
    """The ROM's own session — `addrs.<name>` over `pokes`, `delivered` laid at its door calls — as its `Timeline`'s
    arrivals: every door call and every arrival at the handlers `traps`, each with what the run had spent there, then
    `(RETURN, calls, spent)`. What a battery reads to cut the session into slices under the cap."""
    timeline = Timeline(traps)
    calls = _marked_run(getattr(addrs, name), make_image(_staged(name, arguments, pokes)), delivered, timeline, budget)
    return timeline.arrivals + [Arrival(RETURN, calls, run_cost())]


def slice_cost(name, arguments, pokes, delivered, slice_, *, budget=None):
    """What the ROM's own run of the session spends inside `slice_` — `{"insns", "cycles"}` — the slice held under the
    cap (`rom_sliced`, `vet_under_the_slice_cap`): the measurement a battery cuts its session by, before it registers
    a slice."""
    marks, _memory = rom_sliced(name, arguments, pokes, delivered, slice_, budget=budget)
    spent = marks.spent(f"{name}: the ROM's run")
    vet_under_the_slice_cap(name, slice_, spent["insns"])
    return spent


# ...and the same three over a REGISTERED session (`row`: its `InterruptedRow` — its routine, frame, machine,
# deliveries and declared budget, as `session_of` / `tier3.registered` answer it).
def sliced_of(row, slice_, **marked):
    """`rom_sliced` of the registered session `row`."""
    return rom_sliced(row.name, row.arguments, row.pokes, row.delivered, slice_, budget=row.budget, **marked)


def timeline_of(row, traps=()):
    """`rom_timeline` of it."""
    return rom_timeline(row.name, row.arguments, row.pokes, row.delivered, traps, budget=row.budget)


def slice_cost_of(row, slice_):
    """`slice_cost` of it."""
    return slice_cost(row.name, row.arguments, row.pokes, row.delivered, slice_, budget=row.budget)


# The slice each sliced row is priced on, `{row name: Slice}` (`register_slices`): what Tier 3 reads beside the row.
SLICED_ROWS = {}


def register_slices(name, arguments, machine, interrupts, slices, *, objects=False, budget=None):
    """ONE SESSION — `addrs.<name>` over `machine` with the frame `arguments`, taken through `interrupts`
    (`register_interrupted`'s row, under the `budget` it declares) — registered as a PRICED ROW PER SLICE of `slices`
    (`{label: Slice}`), each named `<core>, <label>`: every row the same session's (its machine, its deliveries, ONE
    derivation for them all; the companion each drop needs is the whole session's differential), each priced by Tier 3
    on its own slice alone (`SLICED_ROWS`), held there to the ROM at both its ends (`vet_the_marks_agree`) and under
    the cap. A session with nothing delivered
    is refused: an unwatched original has no run to mark."""
    settled = _settled_interrupted(name, arguments, machine, interrupts, budget)
    pokes, delivered = settled
    assert delivered, f"{name}: a session priced by its slices is taken through interrupts — this one has none"
    row = InterruptedRow(name, arguments, pokes, interrupts, delivered, budget, settled.sr_words)
    companion = _companion(name, arguments, pokes, interrupts, delivered, objects, budget)
    registered = []
    for label, slice_ in slices.items():
        registered.append(_registered(label, row, companion))
        SLICED_ROWS[registered[-1][0]] = Slice(*slice_)
    return registered


def register_woken_slices(row, slices):
    """ONE SESSION THAT SWITCHES — `row`, a door user's call whose waits BLOCK and are woken (`woken_row`, with the
    `budget` it declares) — registered as a PRICED ROW PER SLICE of `slices` (`{label: Slice}`), each named `<core>,
    <label>`: every row the same session's (ONE settling from the ROM's own run through its dispatcher, one
    `aes_switching.Registered` under every name: `session_of`), each carrying the session's `Switches`, its Tier 3
    drops and the companion they need (the door child under the host's model, over the whole session), and each
    priced on its own slice alone — between two arrivals OF THE ROW'S PROCESS, net of every foreign window
    (`Marks`), on TWO COUNTS where a rebound entry's call lies inside it: the wait that blocks is one, the switch
    in its cost. REGISTERED BY THE ONE REGISTRAR (`aes_switching.register_row`, under each slice's name). The
    session's row as registered."""
    import aes_switching
    core = routines.core_symbol(row.name)
    sliced = {f"{core}, {label}": Slice(*slice_) for label, slice_ in slices.items()}
    SLICED_ROWS.update(sliced)
    return aes_switching.register_row(row, under=tuple(sliced))
