"""THE EVENT DOOR — how a battery runs an AES routine that reaches the event layer (`aes/evdoor.h`), and the MACHINES
such a routine is run over, each the state the ROM's own scheduler leaves.

THE DOOR. A C core calls the event layer (ev_multi, ap_rdwr, ...) through its wrapper in `aes/evdoor.h`, which off
target packs the routine's Alcyon frame and hands it to `recreate_call_event_door`. `event_hook` binds that hook, per
case, to a NESTED ORACLE RUN: the ROM routine, at its own address, over a copy of the candidate's image with the frame
where a `jsr` leaves it (`abi.FIRST_ARG`); its writes are laid back over the candidate's image and its D0 answered. So
both shores run the ROM's own event layer over the same machine — the ORACLE inline, through the caller's Line-F word,
the candidate through the door — and the differential is about the C round it. Keyed BY ROM ADDRESS
(`address_hook.AddressHook`): an entry the case does not serve is refused, and the core halts by name.

A REBOUND ENTRY — one with a C twin, its wrapper calling it (`REBOUND`: derived from the library's exports) — is no
longer served: its call is an ARRIVAL. The hook notes the frame and lays the interrupt due at that call, as at any door
call, answers ARRIVED, and the twin runs over the candidate's image; its return is reported to a second hook
(`recreate_event_door_returned`). While an entry's flip is in flight it is SHADOWED: the nested run is still made, over
a copy of the image at the arrival, and the twin held to it when it returns (`vet_the_shadow`) — every door case that
calls the entry is then a differential of the twin AT ITS OWN CALL. A twin that reaches dsptch calls the DISPATCHER'S
HOOK (`aes/switch.h`), which refuses by name, a block told from a yield as the door tells them.

A REBOUND TWIN IS HELD BY ITS LEAF BATTERY; THE DOOR CASES HOLD THE COMPOSITION. Measured at the pilot (22 real mutants
of `aes_tak_flag`, the door batteries of seven routines, 1,126 tests): with the shadow off or on, the door cases let
through five twins that are NOT the ROM's routine — every mutant of the refusal with a real other owner, of the owner's
and the pointer's widths, of the wait list — because a door case reaches an entry only in the states its caller makes
(the lock free or the caller's own; the refusal arm once, with no owner). The shadow sees the same states: it changes
WHERE a red is named (at the twin's call, not at the session's end), never what is covered. The twin's own battery
(`test_aes_evsync.py`) kills all five alone. So every arm of a twin is its LEAF battery's to reach — its own rows,
entered at the entry itself (`test_tier3.py` holds that every rebound entry has them) — and "the shadow / the door
cases cover it" is no coverage argument for a flip. What the door cases hold is what no leaf battery can: that the
callers still arrive with the same frames, at the same ordinals, and take the same deliveries.

A TWIN CALLS ANOTHER ENTRY'S CORE, NEVER ITS WRAPPER (`aes/evdoor.h` says why): the hook counts every wrapper call
as an arrival, the watches count the outermost call only.

WHAT EACH CALL HANDS THE DOOR is compared too (`run_event`): the frame of every door call the C makes, its MOBLKs and
its message read through their pointers, against the frame the ROM's own run hands the same entry — read off that run
WATCHED at the entries (`DoorStops`, the kit's `rom_bench.watched`). The event layer often answers the same whatever a
frame says (a button that is up satisfies the rise before any rectangle is looked at), so the image alone cannot see a
rectangle or a flag the C got wrong.

WHAT THE NESTED RUN MAY NOT DO, each refused by name (the core then halts, so a case meaning to show it runs the core in
a child process, `refusal`):
  * reach the DISPATCHER (dsptch): the call would BLOCK — nothing it waits for is satisfied (its process left
    WAITING), and on the machine the scheduler switches away until something is. One run has no interrupt to end the
    wait, and the dispatcher's guard the snapshot holds (`AES_INDISP`, a bare `rts` in dsptch) would answer "no event":
    an outcome no machine has. A process still READY there would YIELD (switch away and be switched back); no entry's
    answering path does (measured, `test_aes_event.py`), so that is refused too, by its own name;
  * run past `NESTED_RUN_INSNS`, or within NESTED_RUN_MARGIN times of it (the cap is re-justified from that run);
  * touch the hardware — every stream of the nested run must be empty, since the candidate's ledgers never see it;
  * overflow the write ledger, which would lay back a partial run.

WHAT DIFFERS BY NATURE: the BIOS trap's register save. The event layer polls the keyboard through the VDI, whose BIOS
`trap #13` saves D3-D7/A3-A7 below `savptr` ($90c in the snapshot: `$8de..$905`, then the return PC and SR): A6 and A7
are the stack the trap was taken on — the caller's frame and depth — and the rest whatever the CALLER held in registers
no routine between changed (gr_watchbox's D4 reaches it through ev_multi untouched): a C caller's are not the ROM
caller's, nor the nested run's, entered at the top of the stack band with its own. `TRAP_SAVE_DROP` drops the ten
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
the entry of the call that blocks, or at dsptch where a rebound entry's twin stops (`refused_where_the_rom_blocks`,
`_watched_through`). ONE run of the ROM's routine computes every
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
import contextlib
import copy
import ctypes
import faulthandler
import functools
import inspect
import itertools
import mmap
import operator
import os
import signal
import struct
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
import vdi_helpers
import vdi_mouse
from address_hook import REFUSED_ANSWER, AddressHook, bind_pointer
from case import merge_pokes

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


def _ev_block_inputs(image, code, parameter):
    return (code, parameter)


def _ct_chgown_inputs(image, owner, rect):
    return (owner, _pointee(image, rect, aes.GRECT_BYTES))


# post_button is handed a PD, the buttons' state and the clicks, each as it is.
POST_BUTTON_FRAME = struct.Struct(">Ihh")


def _post_button_inputs(image, process, button, clicks):
    return (process, button, clicks)


# ev_button is handed the clicks, the buttons' mask and the state it waits for, each as it is; its answer words are
# written, so only whether they are handed at all.
EV_BUTTON_FRAME = struct.Struct(">hhhI")


def _ev_button_inputs(image, clicks, mask, state, answers):
    return (clicks, mask, state, bool(answers))


# THE ENTRIES, one row each: the ROM routines the door serves — every C call of the event layer, keyed by its address
# (`aes/evdoor.h`'s wrappers) — each with its Alcyon frame and how its arguments are read.
ENTRY_FRAMES = {"AES_ROM_EV_MULTI": (EV_MULTI_FRAME, _ev_multi_inputs),
                "AES_ROM_AP_RDWR": (AP_RDWR_FRAME, _ap_rdwr_inputs),
                "AES_ROM_TAK_FLAG": (SEMAPHORE_FRAME, _semaphore_inputs),
                "AES_ROM_UNSYNC": (SEMAPHORE_FRAME, _semaphore_inputs),
                "AES_ROM_EV_BLOCK": (EV_BLOCK_FRAME, _ev_block_inputs),
                "AES_ROM_CT_CHGOWN": (CT_CHGOWN_FRAME, _ct_chgown_inputs),
                "AES_ROM_POST_BUTTON": (POST_BUTTON_FRAME, _post_button_inputs),
                "AES_ROM_EV_BUTTON": (EV_BUTTON_FRAME, _ev_button_inputs)}
ENTRY_NAMES = tuple(ENTRY_FRAMES)
ENTRIES = tuple(getattr(addrs, name) for name in ENTRY_NAMES)
_FRAME_OF = {getattr(addrs, name): frame for name, frame in ENTRY_FRAMES.items()}
FRAME_BYTES = {entry: layout.size for entry, (layout, _inputs) in _FRAME_OF.items()}
for _name, (_layout, _inputs) in ENTRY_FRAMES.items():   # each held to its wrapper's (`aes/evdoor.h`)
    assert _layout.size == getattr(aes, f"EVDOOR_{_name.removeprefix('AES_ROM_')}_FRAME_BYTES"), _name


def handed(routine, frame, image):
    """What a call of `routine` with the Alcyon `frame` hands it over `image`: its words and longs, each pointer to an
    input read through, each pointer to an output only as handed or not (`Handed`)."""
    layout, inputs = _FRAME_OF[routine]
    return Handed(routine, inputs(image, *layout.unpack(frame)))


def handed_at(entry, sp, memory):
    """...the call a run stopped at `entry` makes, its frame where the call left it: above the return address at `sp`."""
    start = sp + LONG_BYTES
    return handed(entry, bytes(memory[start:start + FRAME_BYTES[entry]]), memory)


def handed_at_a_twin(entry, sp, memory):
    """...and the call a run stopped at the first instruction of `entry`'s C TWIN makes, read off the frame GCC's caller
    left at `sp`: the return address, the image pointer, then every argument in a longword of its own — a word in its
    low half. Answered as the ROM entry's Alcyon frame is (`handed`), so the two shores' calls compare."""
    layout, _inputs = _FRAME_OF[entry]
    at, values = sp + LONG_BYTES + LONG_BYTES, []
    for code in layout.format.lstrip(">"):
        slot = case.long_in(memory, at)
        values.append(slot if code == LONG_IN_A_FRAME else aes.signed(slot & WORD_MASK))
        at += LONG_BYTES
    return handed(entry, layout.pack(*values), memory)


# ---- REBOUND: the entries that have a C twin ------------------------------------------------------------------------
# An entry is REBOUND once the library exports its twin — the core its name spells (`routines.core_symbol`:
# `aes_tak_flag`) — and its wrapper calls it (`aes/evdoor.h`). Derived from the build, never listed: the hook answers a
# rebound entry ARRIVED and any other SERVED, and a wrapper that disagrees halts by name (a twin exported, its wrapper
# left on the nested run: `test_aes_event.py`, and Tier 3's own derivation from the blob in `test_tier3.py`).
def rebound_in(lib):
    """The door's entries `lib` (a candidate) has a C twin of."""
    return frozenset(getattr(addrs, name) for name in ENTRY_NAMES if hasattr(lib, routines.core_symbol(name)))


REBOUND = rebound_in(_lib)
# THE SHADOW: a rebound entry's twin held, AT ITS OWN CALL, to the ROM routine it replaces — the nested run the door
# served the entry by, made over a copy of the image the twin arrives with; when the twin returns, its answer (the
# word a wrapper hands on) and the image it left are the nested run's, outside what neither shore compares
# (`_NOT_COMPARED`: the nested run's own frames, the Line-F mask word its masked return rewrites, the trap's saved
# registers). It turns every door case that calls the entry into a differential of the twin at the entry: a wrong twin
# reds where it is called, not at the end of the session that called it. For the entries of the flip in flight — once a
# flip has stood, its entries leave this set and their twins' own batteries hold them.
SHADOWED = frozenset({addrs.AES_ROM_TAK_FLAG})
assert SHADOWED <= REBOUND, "a shadowed entry has no twin in the library"
Shadow = namedtuple("Shadow", "call before nested")


def shadow_of(call, image, frame, io_seed=None):
    """The shadow of the door `call` (a `Handed`) arriving over `image` with `frame`: the ROM routine's nested run."""
    return Shadow(call, image, nested_run(call.routine, image, frame, io_seed))


def vet_the_shadow(shadow, image, answer):
    """The twin that arrived as `shadow` returned `answer` and left `image`: both the ROM routine's — refused by name."""
    routine = shadow.call.routine
    assert answer & WORD_MASK == shadow.nested.answer & WORD_MASK, (
        f"the shadow: the twin of {routine:#x} answered {answer & WORD_MASK:#x} where the ROM's routine, run over the "
        f"image the call arrived with, answers {shadow.nested.answer & WORD_MASK:#x} — the call {shadow.call}")
    # THE PASSING CASE IS ONE COMPARE of sixteen megabytes, not a walk of them: the image the call arrived with, the
    # nested run's COMPARED writes laid in, is the whole image of a twin that is its shadow and wrote nothing of what
    # neither shore compares. Only a twin that is not that — it differs, or it wrote in the stack band — pays the
    # address-by-address compare (`differing`, which leaves the same bytes out): the same verdict, with the list a
    # refusal names.
    the_rom_s = bytearray(shadow.before)
    for at, value in shadow.nested.writes.items():
        if at not in _NOT_COMPARED:
            the_rom_s[at] = value
    if image == the_rom_s:
        return
    differ = differing(image, the_rom_s)
    assert not differ, (
        f"the shadow: the twin of {routine:#x} left another image than the ROM's routine run over the image the call "
        f"arrived with — the call {shadow.call} — " + _describe_differences("the twin", image, the_rom_s, differ))


# ---- what a nested run may spend -----------------------------------------------------------------------------------
# A nested run's cap, and the margin EVERY nested run is held to under it — at run time (`nested_run`), so no table of
# the deepest calls can go stale under it. The deepest the batteries reach, every one a call the event layer answers, is
# mn_do's first ev_multi over its two rectangles with the mouse moved onto a title by an interrupt at its entry, 1,697
# instructions (`test_aes_event.DEEPEST_CALLS` names it beside each entry's deepest); 20 times that is 33,940, and the
# cap is 40,000, a round figure with room above that. The margin is for the event layer's longer answering paths a later
# caller stages: a run inside it is refused by name, the cap to be raised from that run.
NESTED_RUN_INSNS = 40_000
NESTED_RUN_MARGIN = 20
# The hook's answers (`aes/evdoor.h`): SERVED, the ROM routine's D0 in the out-parameter; ARRIVED, nothing run — the
# entry is rebound, and its twin runs next; or refused (AddressHook's REFUSED_ANSWER).
SERVED, ARRIVED = aes.EVDOOR_SERVED, aes.EVDOOR_ARRIVED
assert REFUSED_ANSWER == aes.EVDOOR_REFUSED
HOOK_SYMBOL = "recreate_call_event_door"
PROTOTYPE = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32,
                             ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32))
EVENT_DOOR = AddressHook(HOOK_SYMBOL, PROTOTYPE)
# ...and the hook a rebound entry's twin's answer is handed to, once it has returned.
RETURNED_SYMBOL = "recreate_event_door_returned"
RETURNED_PROTOTYPE = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.c_uint32)
DOOR_RETURNS = AddressHook(RETURNED_SYMBOL, RETURNED_PROTOTYPE)
IMAGE_BYTES = len(BASE_IMAGE)
# The streams a nested run may not have made (`emu.run`'s ledgers): the candidate's own never see them.
HARDWARE_STREAMS = ("psg_events", "hw_events", "io_events", "hw_writes")


Nested = namedtuple("Nested", "writes answer insns")


def nested_run(routine, image, frame, io_seed=None):
    """The ROM `routine` over a copy of `image` with its Alcyon `frame` at `abi.FIRST_ARG`: its writes, its D0 and its
    instruction count (`Nested`), refused by name if it would block or yield, ran past its cap, touched the hardware
    or overflowed the write ledger."""
    staged = bytearray(image)
    staged[abi.FIRST_ARG:abi.FIRST_ARG + len(frame)] = frame
    try:
        final, writes, regs = emu.run(staged, routine, max_insns=NESTED_RUN_INSNS, io_seed=io_seed,
                                      stop_pc=addrs.AES_ROM_DSPTCH)
    except RuntimeError as refused:
        if f"within {NESTED_RUN_INSNS} instructions" in str(refused):
            raise AssertionError(f"the event door: {routine:#x} did not return within {NESTED_RUN_INSNS} "
                                 f"instructions ({refused})") from None
        raise AssertionError(f"the event door: the oracle refused the nested run of {routine:#x}: {refused}") from None
    assert not regs["checkpoint"], _at_the_dispatcher(f"the event door: {routine:#x} reached the dispatcher", final)
    touched = [name for name in HARDWARE_STREAMS if regs[name]]
    assert not touched, f"the event door: {routine:#x} touched the hardware ({', '.join(touched)}) — the door serves none"
    assert not regs["writes_truncated"], f"the event door: {routine:#x} overflowed the write ledger"
    assert regs["ninsns"] * NESTED_RUN_MARGIN <= NESTED_RUN_INSNS, (
        f"the event door: {routine:#x} spent {regs['ninsns']} instructions — inside NESTED_RUN_INSNS' margin of "
        f"{NESTED_RUN_MARGIN}: raise the cap, from this run")
    return Nested(writes, regs["d0"], regs["ninsns"])


def _at_the_dispatcher(who, final):
    """Why a run that reached dsptch (`who`: "... reached the dispatcher") is refused, read off the process it was
    running for over `final`: still WAITING ($fe40d8), the call would BLOCK; READY, it would YIELD — disp puts the one
    back on the ready list ($fe4dc4) rather than the not-ready one. Either way the machine switches processes, which
    one run cannot."""
    running = case.long_in(final, aes.AES_RLR) & OS_BUS_ADDR_MASK
    if case.word_in(final, running + aes.PD_STAT) == aes.PD_STAT_WAITING:
        return (f"{who} (dsptch, {addrs.AES_ROM_DSPTCH:#x}) — the call "
                f"would block: nothing it waits for is satisfied, and the machine would switch away until something "
                f"is, which one nested run cannot model (the case staged nothing the call waits for)")
    return (f"{who} (dsptch, {addrs.AES_ROM_DSPTCH:#x}) with its "
            f"process still ready — the call would yield: the machine would run the other processes first, which one "
            f"nested run cannot model")


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


# ---- serving a call ---------------------------------------------------------------------------------------------------
# The door calls the candidate made in the run in flight, in order: what `_served` was handed — in the hook's RECORDED
# pass alone, as `AddressHook.calls` is (an attribution pass would hand the frames again).
HANDED = []


def _in_the_recorded_pass(call):
    if EVENT_DOOR.in_recorded_pass:
        HANDED.append(call)


# THE LINE-F MASK WORD IS NOT LAID BACK. It is the Line-F handler's own self-patched `movem` mask
# (`aes.LINE_F_MASK_WINDOW`): every NON-EMPTY masked Alcyon return of the nested run rewrites it (an empty one, `f001`,
# skips the store: $fee8e2 `andi.w #$ffe` / $fee8e6 `beq`), and the C — no Line-F return of its own — never does.
# Where it ends differs BY NATURE: the ROM's caller makes its OWN non-empty masked return after the door call (mn_bar's,
# gr_rubwind's wm_update's: the word holds that mask), the C makes none (the word would hold the door's last). Tier 1
# drops it where the ROM's run stores it and Tier 3 drops it with each row's undropped COMPANION (`aes.undropped`),
# which stages it at the value the ROM's run leaves: leaving the C's image as it found it is what lets the companion
# still see a C that writes the word itself — laid back, every door row whose routine returns by a mask after its last
# door call would differ there in the companion (measured: mn_bar, gr_rubbox, mn_do ...).
LINE_F_MASK_BYTES = frozenset(at for lo, hi, _why in aes.LINE_F_MASK_WINDOW for at in range(lo, hi))


def _served(routine, io_seed, noted=_in_the_recorded_pass):
    """The effect serving `routine`: what it was handed `noted` (`HANDED`, in the recorded pass), the nested run over
    the candidate's image, laid back (the Line-F mask word aside, above), its D0 answered."""
    def serve(buf, frame, frame_bytes, answer):
        image, frame = ctypes.string_at(buf, IMAGE_BYTES), ctypes.string_at(frame, frame_bytes)
        noted(handed(routine, frame, image))
        try:
            nested = nested_run(routine, image, frame, io_seed)
        except AssertionError as refused:
            print(refused, file=sys.stderr)         # the core halts next: this is its reason, in the child's stderr
            raise
        for at, value in nested.writes.items():
            if at not in LINE_F_MASK_BYTES:
                buf[at] = value
        answer[0] = nested.answer
        return SERVED
    return serve


# `shadows`: the arrivals of ONE BINDING's candidate run in flight whose twins have not returned yet, innermost last —
# a list of the binding's own (`event_hook`, emptied each time a case opens it; `bind_in_a_child`), never the module's.
SHADOW_NOT_MADE = None                 # an arrival's place in `shadows` while — and if — its shadow's making raised


def _arrived(routine, io_seed, noted, shadows):
    """The effect of an ARRIVAL at the rebound `routine`: what it was handed `noted`, as a served call's is, and — for a
    shadowed entry — its shadow made over the image as it arrives (`shadow_of`), kept in `shadows` for the twin's
    return (`_returned`). The call's place is taken BEFORE its shadow is made: a nested run that is refused leaves the
    place empty, and the return — should the core carry on — finds its own call's, not an outer one's. Nothing is
    run over the candidate's image: its twin does that."""
    def arrive(buf, frame, frame_bytes, _answer):
        image, frame = ctypes.string_at(buf, IMAGE_BYTES), ctypes.string_at(frame, frame_bytes)
        call = handed(routine, frame, image)
        noted(call)
        if routine in SHADOWED:
            shadows.append(SHADOW_NOT_MADE)
            shadows[-1] = shadow_of(call, image, frame, io_seed)
        return ARRIVED
    return arrive


def _returned(routine, shadows):
    """...and of its twin's return, the word it answered handed on: a shadowed entry's twin held to its shadow."""
    def returned(buf, answer):
        if routine not in SHADOWED:
            return
        assert shadows, f"the shadow: the twin of {routine:#x} returned, and no arrival of this binding is in flight"
        shadow = shadows.pop()
        assert shadow is not SHADOW_NOT_MADE and shadow.call.routine == routine, (
            f"the shadow: the twin of {routine:#x} returned, and the arrival it answers has no shadow of its own "
            f"(its nested run was refused, or another entry's call is the innermost in flight)")
        vet_the_shadow(shadow, ctypes.string_at(buf, IMAGE_BYTES), answer)
    return returned


def _describe_unawaited_returns(refused):
    return (f"a twin's return was reported for {', '.join(f'{at:#x}' for at in refused)}, which this case binds as no "
            f"rebound entry")


def _describe_refusals(refused):
    return (f"the event door was called for {', '.join(f'{at:#x}' for at in refused)}, which this case does not serve "
            f"— it serves {', '.join(f'{at:#x}' for at in ENTRIES)}")


def event_hook(io_seed=None, entries=ENTRIES):
    """The binding `aes.run_function`'s `hook` opens per case: each of `entries` served by its nested run (the case's
    declared I/O bytes handed on) or — a REBOUND one — noted as an arrival, its twin's return awaited (`_arrived`,
    `_returned`: the two hooks, opened together); any other address refused."""
    shadows = []
    effects = {entry: _arrived(entry, io_seed, _in_the_recorded_pass, shadows) if entry in REBOUND
               else _served(entry, io_seed) for entry in entries}
    returns = {entry: _returned(entry, shadows) for entry in entries if entry in REBOUND}
    both = aes.doors(functools.partial(EVENT_DOOR.staged, effects, _describe_refusals),
                     functools.partial(DOOR_RETURNS.staged, returns, _describe_unawaited_returns))

    @contextlib.contextmanager
    def opened():
        shadows.clear()                 # a run that ended inside a twin's call left its arrival behind: not this run's
        try:
            with both() as passes:
                yield passes
        finally:
            # A SHADOW's refusal is the case's failure, whatever else the run then failed by (a twin that diverged at
            # its call usually leaves a final image that differs too): it names the call the twin went wrong at.
            refused = [raised for _routine, raised in DOOR_RETURNS.raised if isinstance(raised, AssertionError)]
            if refused:
                raise refused[0]
    return opened


def door_hook(drawing, io_seed=None, objects=None):
    """The binding a door user's case opens: the door alone, or with the VDI's cores (`aes_gsx.vdi_hook`) too for one
    that `drawing` — and with the routines a tree walker it reaches is handed (`objects`, `aes.alcyon_object_hook`'s
    `{address: (stub, effect)}`: ob_draw's just_draw, draw_change's newrect)."""
    hooks = ((aes_gsx.vdi_hook,) if drawing else ()) + (event_hook(io_seed),)
    hooks += (aes.alcyon_object_hook(objects),) if objects else ()
    return aes.doors(*hooks) if len(hooks) > 1 else hooks[0]


# THE SAME DOOR IN A CHILD PROCESS (`vdi_helpers.refusal_over`'s `bind`), where a refusal ends the run and the case reads
# its stderr: every hook a door user's core reaches bound for its one call with no pass to open — the event door, every
# entry served and any other refused; the VDI's cores a drawing routine calls through `recreate_call_vector`
# (`aes_gsx.vdi_functions`); and the register-carrying hook (`_child_walkers`) — into `lib`, the candidate the CHILD
# loaded and calls (which need not be the one its `harness` import would load: a pointer left NULL there is a crash,
# not a refusal). The frames the door was handed are printed with a refusal (`HANDED_LINE`), for the case to read back
# (`handed_in`).
_TEST_DIR = str(Path(__file__).resolve().parent)
_CHILD_TRAMPOLINES = []
HANDED_LINE = "the door was handed: "
CHILD_VDI_REFUSED = 3                  # the child's exit status when a VDI call it was not staged for is refused
# ...when the register hook hands it a routine it does not serve: apart from `vdi_helpers.CHILD_ORPHANED`, its parent
# gone.
CHILD_OBJECT_REFUSED = 5
# ...when the C's image does not hold, at an address an interrupt's delivery writes, what the ROM's memory held there
# before it (`_laid_into`): the delta is then not the machine's for the C.
CHILD_DELIVERY_REFUSED = 6
# ...when a rebound entry's twin is not its shadow (`vet_the_shadow`): the hook it reports to is `void`, so the child
# would otherwise carry on over the image the twin left.
CHILD_SHADOW_REFUSED = 7


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
    `void`, so the core would otherwise carry on as if it had drawn."""
    function = aes_gsx.vdi_functions().get(routine)
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
            f"the mouse interrupt's USER_BUT, the fill's SEEDABORT, a Line-A entry), which no child serves")


def _child_walkers(lib, objects):
    """The register-carrying hook in a child, ALWAYS bound: with `objects`, every routine a tree walk is handed by
    value served by the CHILD's own core (`aes.walked_routine_effects`); any other routine — every one, without
    `objects` — ENDS the child by name (`_refused_by_the_register_hook`). Left as the child's `isr` import binds it,
    the hook would refuse such a call SILENTLY (no pass is open, and the hook is `void`): the walk would draw nothing,
    and the case compare a screen the C never drew (measured: mn_do's drop-down, absent)."""
    effects = aes.walked_routine_effects(lib=lib) if objects else {}

    def serve(buf, routine, registers):
        effect = effects.get(routine)
        if effect is None:
            print(_refused_by_the_register_hook(routine), file=sys.stderr, flush=True)
            os._exit(CHILD_OBJECT_REFUSED)
        effect(buf, registers)
    return isr.CALL_VECTOR_REGISTERS(serve)


def _laid_into(buf, delivery):
    """An interrupt's `delivery` (`deliveries`: `(found, wrote)`) laid into the candidate's image `buf` (a C pointer,
    viewed as the image's bytes) at its door call. CHECKED FIRST: the delta is the ROM's interrupt code run over the
    ROM's memory, so it is the machine's for the C only where the C's image holds what the ROM's memory held — `found`,
    at every address the delivery writes (what neither shore compares aside, `_NOT_COMPARED`); laid over a C that
    diverged there, it would erase the divergence. A mismatch ENDS the child by name. The Line-F mask word is not laid,
    as `_served` lays none: the C's image keeps the word as it found it."""
    image = (ctypes.c_uint8 * IMAGE_BYTES).from_address(ctypes.addressof(buf.contents))
    found, wrote = delivery
    try:
        _vet_found(image, found, "the C's door call")
    except AssertionError as refused:
        print(refused, file=sys.stderr, flush=True)
        os._exit(CHILD_DELIVERY_REFUSED)
    _lay(image, wrote, lays_the_mask_word=False)


def bind_in_a_child(lib, entries=ENTRIES, objects=False, interrupts=None):
    """`child_binding`'s call: the door — each entry served, or an arrival where `lib` has its twin (`rebound_in`), the
    twin's return and the dispatcher's hook with it — the VDI's cores and the walked routines bound into `lib`.
    `interrupts` (`deliveries`' `{ordinal: (found, wrote)}`) lays each interrupt's effect into the image at the door
    call of that ordinal, before it is served or its twin runs (`_laid_into`) — and the frames handed are printed at
    the child's exit too, so a call that RETURNS reports them; with a refusal at the dispatcher's hook as well, where
    a twin that blocks ends."""
    calls, shadows, rebound = [], [], rebound_in(lib)
    effects = {entry: _arrived(entry, None, calls.append, shadows) if entry in rebound else _served(entry, None, calls.append)
               for entry in entries}
    returns = {entry: _returned(entry, shadows) for entry in entries if entry in rebound}

    def refused_at_the_dispatcher(buf):
        print(_handed_line(calls), file=sys.stderr, flush=True)
        return _refused_at_the_dispatcher(buf)

    def returned(buf, routine, answer):
        try:
            returns[routine](buf, answer)
        except Exception as refused:   # a KeyError too: a return reported for no rebound entry of this child's
            print(refused if isinstance(refused, AssertionError) else
                  f"the event door: the return of {routine:#x} raised {refused!r}", file=sys.stderr, flush=True)
            print(_handed_line(calls), file=sys.stderr, flush=True)
            os._exit(CHILD_SHADOW_REFUSED)

    def dispatch(buf, routine, frame, frame_bytes, answer):
        if routine not in effects:
            print(_describe_refusals([routine]), file=sys.stderr)
            return REFUSED_ANSWER
        if len(calls) in (interrupts or {}):
            _laid_into(buf, interrupts[len(calls)])
        try:
            return effects[routine](buf, frame, frame_bytes, answer)
        except Exception as refused:   # a callback cannot raise into C (ctypes would answer an undefined word): refused
            if not isinstance(refused, AssertionError):
                print(f"the event door: serving {routine:#x} raised {refused!r}", file=sys.stderr)
            print(_handed_line(calls), file=sys.stderr)
            return REFUSED_ANSWER
    door, vdi_cores, walkers = PROTOTYPE(dispatch), isr.CALL_VECTOR(_child_vdi), _child_walkers(lib, objects)
    twins_return, dispatcher = RETURNED_PROTOTYPE(returned), DISPATCH_PROTOTYPE(refused_at_the_dispatcher)
    _CHILD_TRAMPOLINES.extend((door, vdi_cores, walkers, twins_return, dispatcher))
    bind_pointer(HOOK_SYMBOL, door, lib)
    bind_pointer(RETURNED_SYMBOL, twins_return, lib)
    bind_pointer(DISPATCH_SYMBOL, dispatcher, lib)
    bind_pointer(isr.CALL_VECTOR_SYMBOL, vdi_cores, lib)
    bind_pointer(isr.REGISTERS_HOOK_SYMBOL, walkers, lib)
    if interrupts is not None:         # a refusal aborts the core, so this runs only for a call that returned
        atexit.register(lambda: print(_handed_line(calls), file=sys.stderr))


def _handed_line(calls):
    return HANDED_LINE + repr([tuple(call) for call in calls])


def handed_in(stderr):
    """The door calls a refused child was handed, as it printed them (`HANDED_LINE`): `Handed` each, in order."""
    line, = (line for line in stderr.splitlines() if line.startswith(HANDED_LINE))
    return [Handed(*call) for call in ast.literal_eval(line.removeprefix(HANDED_LINE))]


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
# The dispatcher's hook alone is served as it is everywhere: it refuses by name, a block told from a yield.
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
                   CHILD_SHADOW_REFUSED, FORK_RAISED, FORK_REACHED_A_HOOK)
assert len(set(_CHILD_STATUSES)) == len(_CHILD_STATUSES), "two kinds of child's end share an exit status"
# Every hook the candidate has but the dispatcher's — the event door's two, the two the VDI's cores and the walked
# routines leave through, and the other components' (GEMDOS's handler and clock, Supexec's routine, the disk driver's
# vectors), each by its pointer's name in the library: `test_aes_event.py` holds the list to the library's own exports.
FORK_UNSERVED_HOOKS = (HOOK_SYMBOL, RETURNED_SYMBOL, isr.CALL_VECTOR_SYMBOL, isr.REGISTERS_HOOK_SYMBOL,
                       "recreate_call_gemdos_handler", "recreate_publish_clock", "recreate_call_routine",
                       "recreate_call_disk_vector")
_HOOK_REFUSER = ctypes.CFUNCTYPE(None)  # whatever a hook's own arguments: its refuser reads none, and never returns


def _refused_in_a_fork(symbol):
    def refuse():
        os.write(STDERR_FD, f"the fork: the core reached the hook {symbol}, which no fork serves".encode())
        os._exit(FORK_REACHED_A_HOOK)
    return _HOOK_REFUSER(refuse)


_FORK_REFUSERS = {symbol: _refused_in_a_fork(symbol) for symbol in FORK_UNSERVED_HOOKS}


def _the_fork_s_whole_life(call, said_on, seconds):
    """What a fork does, and all it does: its alarm set, its two stderrs the pipe `said_on`, every hook refused, then
    `call()` — and `_exit`, whatever happened."""
    status = FORK_RAISED
    try:
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.alarm(seconds)                       # FIRST: it bounds all that follows, and an orphan's life
        os.dup2(said_on, STDERR_FD)
        sys.stdout = sys.stderr = open(STDERR_FD, "w", closefd=False)      # a worker's stdout is xdist's own channel
        faulthandler.disable()                      # the worker's dump on SIGABRT would bury the refusal's own words
        for symbol, refuser in _FORK_REFUSERS.items():
            bind_pointer(symbol, refuser)
        bind_pointer(DISPATCH_SYMBOL, DISPATCH_REFUSER)
        call()
        status = 0
    except BaseException:                           # a SystemExit too: nothing leaves a fork but `_exit`
        os.write(STDERR_FD, f"{FORK_S_PYTHON_RAISED}:\n{traceback.format_exc()}".encode())
    finally:
        with contextlib.suppress(Exception):
            sys.stderr.flush()
        os._exit(status)


FORK_S_PYTHON_RAISED = "the fork's own Python raised — the harness's error, not the C's"


def in_a_fork(call, seconds=CORE_RETURN_SECONDS):
    """`call()` made in a FORK of this process (`_the_fork_s_whole_life`): `(exit code, stderr)` — the code negative
    for a signal (the host's refusal aborts; SIGALRM ends a call still running after `seconds`, and with it a fork
    whose parent died), FORK_RAISED for a fork whose Python raised, FORK_REACHED_A_HOOK for a core that reached a
    hook. The fork never returns into this process's code."""
    reading, writing = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(reading)
        _the_fork_s_whole_life(call, writing, seconds)
    os.close(writing)
    with os.fdopen(reading, "rb") as said:
        stderr = said.read().decode(errors="replace")
    return os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1]), stderr


def _vet_returned(name, values, returncode, stderr):
    """THE GUARD'S ONE ASSERTION: the child that ran `addrs.<name>`'s core with the frame `values` came back."""
    called = f"{name}{tuple(values)}"
    assert returncode != FORK_RAISED, f"{called}: the guard itself failed, no verdict on the C — {stderr}"
    assert returncode != FORK_REACHED_A_HOOK, (
        f"{called}: {stderr} — a core that reaches a hook is guarded in a fresh interpreter, its hooks bound "
        f"(`run_guarded`), never in a fork")
    assert returncode == 0, f"{called}: the C did not return in a child ({returncode}): {stderr}"


def forked_first(name, values):
    """`aes.run_function`'s `first` for a core that reaches no hook: each of its runs made in a fork first, and held
    to have returned there (`_vet_returned`)."""
    def first(call):
        _vet_returned(name, values, *in_a_fork(call))
    return first


def run_core_guarded(name, arguments, pokes, **kwargs):
    """THE DIFFERENTIAL OF A CORE THAT REACHES NO HOOK, every run of its C FIRST IN A FORK (above): `aes.run_function`
    of `addrs.<name>` over `pokes`, `kwargs` its own (`steered=` among them) — the run door of the lists', the
    processes' and the lock's batteries."""
    return aes.run_function(name, arguments, pokes, first=forked_first(name, arguments), **kwargs)


Forked = namedtuple("Forked", "returncode stderr image answer")


def core_in_a_fork(name, values, pokes, *, seconds=CORE_RETURN_SECONDS, answered=False, read_back=False):
    """What `addrs.<name>`'s core — one that reaches no hook — says over `pokes` with the frame `values` in a FORK, for
    a case that MEANS to show a halt or a return there (`refusal`'s fork kind: no interpreter started, no image
    file): a `Forked` — the exit code and stderr (`in_a_fork`), the image as the core left it (`read_back`: the fork
    runs over a mapping it shares with this process, so every store made before a halt is there) and the core's
    answer (`answered`, at its declared width; None for a core that did not return). The library's models are armed
    as a differential arms them (`arm_candidate`): the verdict is this call's, whatever test ran before."""
    shared = mmap.mmap(-1, IMAGE_BYTES)
    shared[:] = make_image(pokes)
    buf = (ctypes.c_uint8 * IMAGE_BYTES).from_buffer(shared)
    core = getattr(_lib, routines.core_symbol(name))
    typed = vdi.as_signed(name, values)

    def call():
        arm_candidate()
        answer = core(buf, *typed)
        if answered:
            print(f"{vdi_helpers.ANSWER_LINE}{answer}", file=sys.stderr)
    returncode, stderr = in_a_fork(call, seconds)
    return Forked(returncode, stderr, bytes(shared) if read_back else None,
                  vdi_helpers.answer_in(stderr) if answered else None)


# The door users' guards that returned, by CONTENT — (routine, frame, binding, THE IMAGE the pokes make: laid over
# each other in the order `make_image` lays them, `merge_pokes`): one child per distinct call in a worker (a case run
# both directly and through its Line-F word is the same C call twice). Never by the machine's identity — a freed
# dict's address is the next one's — nor by its pokes sorted: two machines of the same overlapping pokes laid in
# another order are two images, and the second would pass unguarded on the first's word (`test_aes_event.py` holds
# both).
_RETURNED_IN_A_CHILD = set()


def returns_in_a_child(name, values, pokes, *, objects=False, seconds=CHILD_RETURN_SECONDS):
    """A DOOR USER's core `addrs.<name>` over `pokes` with the frame `values` RETURNS in a child — a fresh interpreter,
    the event door bound (`refusal`; the walked routines served with `objects`): the guard `run_guarded` runs before
    its in-process differential. Once per distinct call in a worker."""
    bind = child_binding(objects=bool(objects))
    guarded = (name, tuple(values), bind, tuple(merge_pokes(pokes).items()))
    if guarded in _RETURNED_IN_A_CHILD:
        return
    returncode, stderr, _image = refusal(name, pokes, values, bind=bind, seconds=seconds, read_back=False)
    _vet_returned(name, values, returncode, stderr)
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
    arrivals, as the ROM routine's are none. A twin is entered from wherever the compiler placed its call (a `jsr`, a
    tail `jmp` whose return is its caller's): its return address is no fixed site of `returns`, but it is BOUNDED —
    inside `twins_called_from`, the `(lo, hi)` of our build's own text: a twin reached with any other return address
    (the ROM's text, a stack address) was reached by no call of ours, and is refused by name."""

    def __init__(self, entries, returns, opened=None, closed=None, *, blocks=False, delivered=None, twins=None,
                 twins_called_from=None):
        self.twins = dict(twins or {})
        assert not self.twins or twins_called_from, "a watch at twins names the text their calls come from"
        self._twins_called_from = twins_called_from
        self.entries, self.returns = frozenset(entries) | frozenset(self.twins), frozenset(returns)
        self.first = self.entries
        self._inside = frozenset({addrs.AES_ROM_DSPTCH}) if blocks else frozenset()
        # A watch's own `_opened` / `_closed` (a subclass's methods) are NOT handed here: a bound method kept on its
        # own instance is a reference cycle, and the watch — with its marks, a memory per slice end — would then
        # outlive its run until a later collection (measured: 1.9 GB peak in one test where 1 GB is in use).
        if opened is not None:
            self._opened = opened
        if closed is not None:
            self._closed = closed
        self._in_call = False
        self._delivered = delivered or {}
        self.calls = 0
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

    def marked_with(self, marks):
        """This watch, its run MARKED by `marks` (`Marks`): stopped at the trap handlers they name as well."""
        self.marks = marks
        self.first = self.entries | marks.traps
        return self

    def _called_by_our_build(self, pc, back):
        """Is `pc` a twin's first instruction, reached with a return address in our build's own text?"""
        return pc in self.twins and self._twins_called_from[0] <= back < self._twins_called_from[1]

    @property
    def between_calls(self):
        """Is the run outside every door call — so a stop at an entry opens the next?"""
        return not self._in_call

    def stopped(self, pc, sp, memory):
        if self._trap_returns_to is not None:
            assert pc == self._trap_returns_to, (
                f"the run took the trap at {pc:#x} INSIDE the trap at {self._marked_trap:#x}, and is marked at both: an "
                f"arrival there counts in a run marked at {pc:#x} alone and not in this one, so a `trap_taken` "
                f"ordinal at it names two different arrivals — cut the session at one of the two handlers only")
            self._trap_returns_to = None
            return self.first
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
            self._in_call = True
            return frozenset({back}) | self._inside
        if pc in self._inside:
            raise Blocked(f"the run reached the dispatcher (dsptch, {pc:#x}) inside door call {self.calls - 1}: "
                          f"{SWITCHES_AT_THE_DISPATCHER} — nothing it waits for was delivered to it (an interrupt "
                          f"missing, or laid at another call)")
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


def rom_watched(name, arguments, pokes, io_seed=None, *, blocks=False, budget=None):
    """The ROM's own `addrs.<name>`, run over `pokes` with the frame `arguments`, WATCHED at the door's entries
    (`_watched_through`, nothing delivered): `(calls, memory, returned)` — what it hands each entry it calls, in order
    (`handed_at`: each frame where its Line-F word left it, read through its pointers as it stands at the call), the
    memory it left (at the entry of the blocking call, for one that blocks), and whether it returned (False: `blocks`,
    and it reached the dispatcher inside a call). `budget`: the run's own, declared (`_budget_of`)."""
    calls, memory, result = _watched_through(name, arguments, pokes, {}, io_seed=io_seed, blocks=blocks, budget=budget)
    return calls, memory, result is not None


def rom_handed(name, arguments, pokes, io_seed=None, budget=None):
    """What the ROM's own `addrs.<name>` hands each door entry it calls, in order (`rom_watched`)."""
    return rom_watched(name, arguments, pokes, io_seed, budget=budget)[0]


def _vet_the_frames_handed(name, arguments, pokes, io_seed, budget=None):
    """The door calls the candidate made (`HANDED`) are the ROM's own, frame for frame (`rom_handed`)."""
    ours, the_rom_s = list(HANDED), rom_handed(name, arguments, pokes, io_seed, budget)
    assert ours == the_rom_s, (
        f"{name}: the door was handed {ours} where the ROM's own run hands {the_rom_s} — a frame the event layer's "
        f"answer did not show")


# ---- what differs by nature: the BIOS trap's saved registers -------------------------------------------------------
SNAPSHOT_SAVPTR = case.long_in(BASE_IMAGE, addrs.SYSVAR_SAVPTR)
TRAP_SAVE_AT = SNAPSHOT_SAVPTR - addrs.TRAP_SAVE_FRAME_BYTES
TRAP_SAVE_DROP = ((TRAP_SAVE_AT, TRAP_SAVE_AT + addrs.TRAP_SAVED_REGISTERS * LONG_BYTES,
                   "the BIOS trap's saved D3-D7/A3-A7 under the event layer's keyboard poll: the registers it was taken "
                   "with — the caller's frame, depth and whatever it holds in them, which a C caller's are not"),)
DOOR_DROPS = aes.LINE_F_MASK_WINDOW + TRAP_SAVE_DROP


# ---- ...and psetup's status-register save word ---------------------------------------------------------------------
# The scheduler parks the status register in a word of RAM round each of its interrupt-mask brackets (`aes/switch.h`).
# What lands there is the SR its caller ran under — the condition codes of the last instruction before the bracket
# among them — which is the caller's CPU state: a C caller's is not the ROM caller's (on target), and the host has
# none to store. psetup's word is dropped by name, only where the ROM's run stores it, by the cases whose routine
# reaches its bracket (`aes_pdpipe`'s) — and at Tier 3 with the undropped companion every drop needs. The dispatcher's
# (savestate / switchto, AES_SR_DISPATCH) and spl7_save's (AES_SR_SPL) get theirs when a case first reaches them.
SR_PSETUP_DROP = ((aes.AES_SR_PSETUP, aes.AES_SR_PSETUP + aes.WORD_BYTES,
                   "psetup's SR save word: the status register of whoever called it, parked round its stores "
                   "(`aes/switch.h`); the C stores nothing there off target and its own caller's on it"),)


def savptr_in_the_band():
    """`savptr` moved into the stack band, the save frame filled: the trap's save then lands where neither shore
    compares (`gemdos.machine`'s arrangement, without its trampoline slot)."""
    return {addrs.SYSVAR_SAVPTR: struct.pack(">I", gemdos.SAVPTR_AT),
            gemdos.FRAME_AT: bytes([gemdos.FRAME_FILL]) * addrs.TRAP_SAVE_FRAME_BYTES}


# ---- the run doors ---------------------------------------------------------------------------------------------------
# THE ATTRIBUTION PASS DOES NOT RUN through the door, MEASURED: it inverts every byte the ROM's run stored — the event
# layer's fork queue, its CDA, its EVBs' links — and the poisoned ROM run follows them: over every door row's machine
# (each the scheduler's own, `machine`) the poisoned run of ap_sendmsg, gr_stilldn and gr_watchbox alike did not
# return within 200,000 instructions. What stands in for it is staging — a door user's own stores land in words a
# battery stages STALE (a message buffer, an object's state set to what it is not), so a store the C skipped differs —
# and the frames each door call is handed, compared with the ROM's (`_vet_the_frames_handed`).
POISON_STEERS_THE_EVENT_LAYER = {"poison": False}


def run_event(name, arguments, pokes, *, drawing=False, io_seed=None, dropped_windows=DOOR_DROPS, objects=None,
              budget=None, cap=None, **kwargs):
    """`aes.run_function` of `addrs.<name>` over `pokes`, the event door bound (and the VDI's cores, `drawing`, and a
    walker's routines, `objects`: `door_hook`), the mask word and the trap's saved registers dropped where the ROM's
    run stores them, unpoisoned (above) — and every frame the candidate handed the door compared with the ROM's own
    call's. TWO RUNS, TWO LIMITS, each declared only where its run needs it and held both ways by name:
    `cap` — the differential's own (`emu.run`'s `max_insns`), for an original past DIFFERENTIAL_INSNS: the case's own
    number, or its battery's (`battery_cap`) — THE ONE DOOR a cap comes in by (`capped`, `vet_the_cap`: a raw
    `max_insns` is refused by name);
    `budget` — the derivation budget of the ROM's watched run of the frames (`_budget_of`), for a run past what
    DERIVATION_INSNS admits. A run that needs the budget needs the cap too, and the one number then serves both."""
    HANDED.clear()
    cap = budget if cap is None else cap
    result = capped_run(name, cap, kwargs, lambda **limits: aes.run_function(
        name, arguments, pokes, hook=door_hook(drawing, io_seed, objects), io_seed=io_seed,
        dropped_windows=dropped_windows, **{**POISON_STEERS_THE_EVENT_LAYER, **limits}))
    _vet_the_frames_handed(name, arguments, pokes, io_seed, budget)
    return result


def run_guarded(name, arguments, pokes, *, objects=None, **kwargs):
    """A door user's case: its C FIRST IN A CHILD — a PRECONDITION (`returns_in_a_child`, the walked routines served
    there when `objects` names any): a core that loops where the ROM's run ends fails the case by a timeout, where
    in-process it would hang the worker — then the differential (`run_event`, `objects` and the rest its)."""
    returns_in_a_child(name, arguments, pokes, objects=bool(objects))
    return run_event(name, arguments, pokes, objects=objects, **kwargs)


def register(label, name, arguments, pokes, *, drawing=False, io_seed=None, objects=None, answer_compared=True):
    """One priced `VERIFIED_CASES` row of a door user, named `<core>, <label>` (`aes.register`: the mask word staged at
    the value the run leaves, dropped at Tier 3 with its companion) — over `pokes` with `savptr` moved into the stack
    band, so the trap's save lands where neither the row nor its companion compares it and Tier 3 drops nothing else.
    The cost is the same: the trap saves the same frame, elsewhere. `objects` and `answer_compared` as `run_event`'s
    and `aes.register`'s."""
    return aes.register(label, name, arguments, merge_pokes(pokes, savptr_in_the_band()),
                        hook=door_hook(drawing, io_seed, objects), io_seed=io_seed, answer_compared=answer_compared)


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
    else:
        _calls, delivered, rom_memory, result = rom_interrupted(name, arguments, pokes, interrupts, budget=budget)
        assert result, f"{name}: a priced row returns — the ROM's run taken through these interrupts blocks"
    mask_word = case.word_in(rom_memory, aes.AES_LINEF_MASK_WORD)
    return merge_pokes(pokes, aes.field_pokes("AES", LINEF_MASK_WORD=mask_word)), delivered


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
InterruptedRow = namedtuple("InterruptedRow", "name arguments pokes interrupts delivered budget")
INTERRUPTED_ROWS = {}


def session_of(row_name):
    """The SESSION the registered row `row_name` is of — its `InterruptedRow`, or None for a row not taken through
    interrupts. The rows `register_slices` registers of one session are ONE record (`is`): one machine, one set of
    deliveries, one derivation."""
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


def rederived(row_name):
    """The deliveries of the registered row `row_name` DERIVED AGAIN, over the snapshot as it stands now
    (`harness.set_base_image`): the interrupts' own code run afresh — for the sweep that fills the snapshot's MASK with
    noise, where an interrupt reading a masked byte must show it (the deliveries derived over the pristine snapshot,
    laid as they are, would hide it)."""
    assert row_name in INTERRUPTED_ROWS, f"{row_name}: no row taken through interrupts registered by that name"
    row = INTERRUPTED_ROWS[row_name]
    return deliveries(row.name, row.arguments, row.pokes, row.interrupts, row.budget)


def register_interrupted(label, name, arguments, machine, interrupts, *, objects=False, budget=None):
    """One PRICED `interrupted_row`, registered (`aes.ROWS`) — the mask word dropped at Tier 3 with the COMPANION a
    drop needs: the same interrupted differential (`interrupted`, `objects` its, over the row's own deliveries),
    comparing every byte outside the stack band. The row's own pricing is its second differential, so the companion
    does not make one again. `budget`: the row's own derivation budget, declared (`_budget_of`) — every derivation of
    the row (this one, its companion's, `rederived`) is held to it, both ways."""
    pokes, delivered = _settled_interrupted(name, arguments, machine, interrupts, budget)
    return _registered(label, InterruptedRow(name, arguments, pokes, interrupts, delivered, budget),
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
    return aes.ROWS.register(row_name, entry, staged, dropped=aes.LINE_F_MASK_WINDOW, undropped=companion,
                             delivered=row.delivered)


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


def derived(entry, pokes, regs=None, frame=b""):
    """What the ROM's run of `entry` over `aes.leaf_machine()` and `pokes` WROTE, the stack band out — and the run. A
    machine of this module's in `pokes` (`pd0_running`, `machine`) brings its own running process: the lever's poked
    one beneath it is overwritten by the scheduler's. The run may not reach the DISPATCHER (it stops there, refused):
    a dsptch a process-level routine reaches would switch processes — a block or a yield — which a derivation that
    keeps only one run's writes cannot carry."""
    image = make_image(merge_pokes(aes.leaf_machine(), pokes, {abi.FIRST_ARG: frame} if frame else None))
    final, writes, regs_out = _rom_run(image, entry, regs, stop_pc=addrs.AES_ROM_DSPTCH)
    assert not regs_out["checkpoint"], (
        f"the derivation's run of {entry:#x} reached the dispatcher (dsptch, {addrs.AES_ROM_DSPTCH:#x}): it would "
        f"switch processes")
    return case.written_by(writes), final, regs_out


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


def as_pokes(memory, over=BASE_IMAGE, *, without=frozenset(), upto=None):
    """AN IMAGE AS POKES: every byte `memory` differs from `over` at (the snapshot, by default), merged into runs —
    `without` (a set of addresses: `case.STACK_BAND` for a run's own frames, which every case stages afresh) left
    out, and nothing from `upto` up when one is named (`addrs.ST_RAM_BYTES`: a machine is its RAM). How a machine a
    ROM run made is kept: laid over `over` again, it is that machine."""
    return merge_pokes({at: bytes([memory[at]]) for at in _differing_addresses(over, memory, upto) if at not in without})


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


def tick(image):
    """A TICK of the system timer over `image` in place: the AES's tick glue (vex_timv's, `AES_ROM_TICK_GLUE` — the
    click delay counted down, a pending timer's elapsed ticks queued for forker). What it wrote — an interrupt
    `interrupted` can deliver."""
    return _interrupt_over(image, addrs.AES_ROM_TICK_GLUE)


def _ticked(image, count):
    written = {}
    for _tick in range(count):
        written = merge_pokes(written, tick(image))
    return written


def ticks(count):
    """`count` ticks, one after the other: `ticks(n)(image)` answers what they wrote — an interrupt, as `tick` is."""
    return functools.partial(_ticked, count=count)


def _packets_resolved(image, *headers):
    """The buttons changed by a packet per header of `headers`, one after the other inside the click delay: each
    through the VDI's mouse interrupt (`VDI_ROM_MOUSE_ISR`, A0 the packet — what the IKBD's mousevec runs), which
    records them in its own state (MOUSE_BT, CUR_MS_STAT) and calls the AES's button glue (vex_butv's,
    `AES_ROM_BUTTON_GLUE`: b_click opens the click count); then the tick glue ($fed426, vex_timv's) until b_delay's
    count is final (AES_GL_CLICK_TICKS 0) — each an interrupt (`_interrupt_over`), over `image` in place. What they
    wrote."""
    written = {}
    for header in headers:
        written = merge_pokes(written, _interrupt_over(image, addrs.VDI_ROM_MOUSE_ISR, {"a0": PACKET_AT},
                                                       _packet(header)))
    for _tick in range(case.word_in(image, aes.AES_GL_CLICK_TICKS)):
        written = merge_pokes(written, tick(image))
    assert case.word_in(image, aes.AES_GL_CLICK_TICKS) == 0, "the ticks did not resolve the click"
    return written


def press(image):
    """The left button PRESSED over `image` in place, as the machine takes it whatever process runs (`_packets_resolved`):
    the press queued for forker, posted to no wait yet. What it wrote — an interrupt `interrupted` can deliver."""
    return _packets_resolved(image, MOUSE_PACKET_HEADER | MOUSE_PACKET_LEFT_BUTTON)


def double_click(image):
    """A DOUBLE CLICK over `image` in place: the left button pressed, released and pressed again inside the click
    delay, then the delay run out — the second press counted by b_click, the button left down. What it wrote."""
    down = MOUSE_PACKET_HEADER | MOUSE_PACKET_LEFT_BUTTON
    return _packets_resolved(image, down, MOUSE_PACKET_HEADER, down)


def release(image):
    """...the button RELEASED (a packet with no button down): the release queued for forker the same way."""
    return _packets_resolved(image, MOUSE_PACKET_HEADER)


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


def _step_toward(image, x, y):
    """ONE relative packet toward (`x`, `y`) — the buttons as they are held (`_packet_buttons`) — through the VDI's mouse
    interrupt ($fcfe28, A0 the packet), which moves the cursor and calls the AES's motion glue (it queues mchange), over
    `image` in place: what it wrote, or None once the cursor is there. REFUSED by name where the packet leaves the
    cursor where it was: the interrupt clamps it to the screen, so a point past an edge is one no packet reaches."""
    cursor = _cursor(image)
    dx = max(-MOUSE_STEP, min(MOUSE_STEP, x - cursor[0]))
    dy = max(-MOUSE_STEP, min(MOUSE_STEP, y - cursor[1]))
    if not dx and not dy:
        return None
    written = _interrupt_over(image, addrs.VDI_ROM_MOUSE_ISR, {"a0": PACKET_AT},
                              _packet(MOUSE_PACKET_HEADER | _packet_buttons(image), dx, dy))
    assert _cursor(image) != cursor, (
        f"the mouse cannot be moved to ({x}, {y}): a packet of ({dx}, {dy}) left the cursor at {cursor} — the mouse "
        f"interrupt clamps it to the screen")
    return written


def _cursor(image):
    """Where the VDI's mouse interrupt has the cursor (GCURX, GCURY)."""
    return case.word_in(image, vdi.LINEA_GCURX), case.word_in(image, vdi.LINEA_GCURY)


def _moved(image, x, y):
    written = {}
    while (step := _step_toward(image, x, y)) is not None:
        written = merge_pokes(written, step)
    return written


def move_to(x, y):
    """The mouse MOVED to (`x`, `y`): the packets that take it there, one at a time (`_step_toward`), each an interrupt
    over `image` in place — an interrupt `interrupted` can deliver: `move_to(x, y)(image)` answers what they wrote."""
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
# frames its own) and the door's two documented windows (`DOOR_DROPS`, whole: the mask word the C never writes and the
# trap's saved registers the C's nested runs leave): with the ROM's final memory when its run returns — its answer and
# every frame the door was handed too — or with its memory at the ENTRY of the call that blocks, the point where the C's
# door refuses the same call (`refused_where_the_rom_blocks`).
COMPARED_DIFFERENCES_SHOWN = 16        # how many differing bytes a failure names
Interrupted = namedtuple("Interrupted", "calls returned answer rom_memory image delivered staged stderr")
_NOT_COMPARED = frozenset(case.STACK_BAND) | frozenset(at for lo, hi, _why in DOOR_DROPS for at in range(lo, hi))


def _as_sequence(interrupts):
    return interrupts if isinstance(interrupts, tuple) else (interrupts,)


class _AtTheEntry(Exception):
    """A watched run stopped at the entry of the door call of the ordinal asked for: its memory there, what was
    delivered at it laid in, and the call it makes (`handed_at`)."""

    def __init__(self, memory, call):
        super().__init__()
        self.memory, self.call = memory, call


def _watched_through(name, arguments, pokes, delivered, stop_at=None, *, io_seed=None, blocks=True, budget=None,
                     rebound=None):
    """The ROM's own `addrs.<name>` WATCHED at the door's entries, `delivered` (`deliveries`' `{ordinal: (found,
    wrote)}`) laid into its memory at the entry of each door call of that ordinal, each checked first (`DoorStops`):
    `(calls, memory, result)` — the frames handed, read after; the memory it left, or WHERE THE C STOPS for a call that
    blocks (`blocks`: stopped at the dispatcher inside a call); its result, None where it blocked. Stopped at the entry
    of the call of ordinal `stop_at` instead, by `_AtTheEntry`.

    WHERE THE C STOPS at a call that blocks: an entry the ROM still serves is refused whole — its nested run reached
    the dispatcher, and nothing of it is laid — so the C's image is the ROM's at that call's ENTRY; a `rebound` entry's
    twin runs on, to the dispatcher's hook, and its image is the ROM's AT DSPTCH — every list, EVB and PD the wait
    wrote compared (nothing of the switch is stored yet: savestate comes after). `rebound`: REBOUND as it stands when
    the run is made (the one set the hook answers by, read at the same moment), unless a case names another."""
    rebound = REBOUND if rebound is None else rebound
    calls = []
    memory = make_image(aes.staged(name, arguments, pokes))
    # The memory at the entry of the last call opened — what a run that BLOCKS is compared at — kept in ONE buffer,
    # stored over at each call: a fresh sixteen-megabyte copy per door call was a third of a replay's cost.
    at_the_entry = bytearray(len(memory))

    def opened(pc, sp, memory):
        call = handed_at(pc, sp, memory)
        if len(calls) == stop_at:
            raise _AtTheEntry(bytes(memory), call)
        calls.append(call)
        at_the_entry[:] = memory
    watch = DoorStops(ENTRIES, ROM_RETURNS, opened, blocks=blocks, delivered=delivered)
    result = run_watched(memory, getattr(addrs, name), watch, io_seed, budget)
    assert result or calls, f"{name}: the run blocked before any door call"
    if result:
        return calls, memory, result
    return calls, (bytes(memory) if calls[-1].routine in rebound else bytes(at_the_entry)), result


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
# (`_continued_at`): re-entered there by a bench run seeded with the register file the stop left, its door on the entry
# alone so it stops before executing anything, the return-address slot its entry store overwrote put back. What the
# re-entry cannot carry is the status register — the oracle's forced entry SR again, the condition codes cleared — which
# no Alcyon entry reads before it sets them; and the run every case compares against is not this one but the REPLAY
# (`rom_interrupted`), one run laying the deliveries at no cost, each checked against the memory it lands on
# (`DoorStops`' `delivered`): a continuation that strayed would be refused there by name. Measured ONCE, over every
# interrupted case of the batteries then: the deliveries equal byte for byte those of one run per ordinal, the earlier
# scheme, whose cost grew with the square of the ordinals; PINNED over three cases (`test_aes_event.py`'s
# SEVERAL_DELIVERIES), which the reference's own cost keeps from being every one.
RE_ENTRY_SLOT_BYTES = LONG_BYTES       # the return-address slot the re-entry's sentinel store overwrites


def _continued_at(memory, pc, sp, registers):
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


def _taken(memory, interrupt):
    """`interrupt` (or a tuple of them) run over a copy of `memory`: `(found, wrote)` — what `memory` holds at every
    address it writes, then what it wrote there."""
    image, wrote = bytearray(memory), {}
    for each in _as_sequence(interrupt):
        wrote = merge_pokes(wrote, each(image))
    return {at: bytes(memory[at:at + len(data)]) for at, data in wrote.items()}, wrote


def _run_interrupting(memory, entry, interrupts, budget=None):
    """The ROM's own `entry` over `memory` (its frame at abi.FIRST_ARG), ONE watched run that takes each interrupt of
    `interrupts` at the entry of its door call (above): `(delivered, result)` — `{ordinal: (found, wrote)}`, and the
    run's result, None where it blocked. Held to its budget (DERIVATION_INSNS, or the `budget` its row declares:
    `_budget_of`) by its margin over every segment — and from above (`_vet_not_stale`) — each segment's refusals
    vetted as it ends. The last segment's vets run on a run that ENDED (returned or blocked) only: after an
    interrupt's own run failed, the oracle's counters are that run's, and a vet of them would replace its error."""
    if isinstance(interrupts, Waits):
        interrupts.begin_run()
    watch = DoorStops(ENTRIES, ROM_RETURNS, blocks=True)
    delivered, spent, insns = {}, 0, _budget_of(entry, budget)
    who = f"the ROM's interrupted run of {entry:#x}"
    result = rom_bench.original_entered(memory, entry, watch.first, max_insns=insns)
    try:
        while result["status"] == emu.BENCH_DOOR:
            pc, sp = emu.bench_door_pc(), emu.bench_door_sp()
            interrupt = _interrupt_at(interrupts, watch.calls, pc) if watch.between_calls else None
            if interrupt:
                spent += result["ninsns"]
                rom_bench.vet_the_run_just_made(who)
                registers = result["regs"]
                emu.bench_abort()
                delivered[watch.calls] = _taken(memory, interrupt)
                _lay(memory, delivered[watch.calls][1])
                result = _continued_at(memory, pc, sp, registers)
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


def deliveries(name, arguments, pokes, interrupts, budget=None):
    """What each interrupt of `interrupts` WRITES, run over the ROM's own memory at the entry of the door call it is
    delivered at — `{ordinal: interrupt or (interrupt, ...)}`, or a SCHEDULE `interrupts(ordinal, entry)` answering
    one (or None) at every call (`typed`): `{ordinal: (found, wrote)}` — the bytes that memory held at each address the
    delivery writes, then what it wrote there. ONE run of the routine takes them all (`_run_interrupting`, under the
    `budget` its row declares); an ordinal the run never reaches, or a schedule left with interrupts `pending`, is
    refused by name."""
    memory = make_image(aes.staged(name, arguments, pokes))
    delivered, _result = _run_interrupting(memory, getattr(addrs, name), interrupts, budget)
    undelivered = interrupts.pending if isinstance(interrupts, Waits) else sorted(set(interrupts) - set(delivered))
    assert not undelivered, f"{name}: the ROM's run made no door call to deliver {undelivered} at"
    return delivered


def rom_interrupted(name, arguments, pokes, interrupts, delivered=None, budget=None):
    """The ROM's own `addrs.<name>` over `pokes` with the frame `arguments`, WATCHED at the door's entries, each of
    `interrupts` delivered over its memory at the entry of that door call (`deliveries`; or `delivered`, derived
    already) — then REPLAYED: one run laying them in at no cost, each checked against the memory it lands on
    (`_watched_through`), the run every shore is compared with: `(calls, delivered, memory, result)` — the frames handed
    (each read after the interrupt), the deliveries (`{ordinal: (found, wrote)}`), the memory it left (or, for a run
    that BLOCKS, its memory at the entry of the blocking call), and the run's result (None: it blocked). `budget`:
    the case's own, declared (`_budget_of`), which both runs are held to."""
    if delivered is None:
        delivered = deliveries(name, arguments, pokes, interrupts, budget)
    calls, memory, result = _watched_through(name, arguments, pokes, delivered, budget=budget)
    return calls, delivered, memory, result


def delivering(delivered):
    """A watch over a run of a row whose interrupts are DELIVERED (`register_interrupted`): `delivered` laid at its door
    calls, each checked first, and a call that reaches the dispatcher refused by name (`DoorStops`) — the ROM's replays
    (`replayed`) and Tier 3's original."""
    return DoorStops(ENTRIES, ROM_RETURNS, blocks=True, delivered=delivered)


def replayed(image, entry, delivered, regs=None, io_seed=None):
    """The ROM's own `entry` over `image` (its frame staged), `delivered` laid at its door calls (`delivering`, which
    checks each), answered as `emu.run` answers — `(final, writes, regs)` (`rom_bench.watched_original`) — and refused
    as it is: what an unwatched run of the same row would be, for every consumer that runs a row's ORIGINAL (the
    snapshot's sweeps)."""
    final, writes, regs_out = rom_bench.watched_original(bytearray(image), entry, delivering(delivered), regs,
                                                         io_seed=io_seed)
    rom_bench.vet_the_run_just_made(f"the ROM's replay of {entry:#x}")
    return final, writes, regs_out


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


def _answer_at_its_width(name, d0):
    """D0 at the width `addrs.<name>`'s core declares its answer (`vdi.ALCYON`): its word, its long, or None."""
    restype = vdi.ALCYON[name].restype
    return None if restype is None else d0 & ((1 << (8 * ctypes.sizeof(restype))) - 1)


# How the door refuses a call at whose dsptch the machine would switch processes (`_at_the_dispatcher`'s words): the
# caller WAITING, or still READY (it made another process ready, which runs first). Its own words, not "would block"
# alone, which the core's halt line spells for either ("a call that would block ... or yield").
BLOCKS, YIELDS = "the call would block", "the call would yield"
# ...and how a WATCHED run refuses a call that reached dsptch (`DoorStops`' `blocks`): the watch stops there before
# dsptch decides which, so its words name both.
SWITCHES_AT_THE_DISPATCHER = "the call would switch processes (block or yield)"


def interrupted(name, arguments, machine, interrupts, *, objects=False, seconds=CHILD_RETURN_SECONDS, switches=BLOCKS,
                not_compared=None, delivered=None, second_differential=True, budget=None):
    """`addrs.<name>` over `machine` with the frame `arguments`, TAKEN THROUGH `interrupts` — `{ordinal: interrupt or
    (interrupt, ...)}`, each delivered at the entry of the door call of that ordinal (`press`, `release`, `move_to(x,
    y)`, `key`), or a schedule (`typed`) — on both shores: the ROM's own run (`rom_interrupted`) and the C in a child
    (`bind_in_a_child`, the walked routines served with `objects`), the C held to the ROM: whether it returned (else it
    switched processes at the same call, refused as one that `switches`), its answer, every frame the door was handed and
    the whole image (`differing`, outside `not_compared`: `_NOT_COMPARED` by default) — and, at each delivery, its image
    where the delivery writes (`_laid_into`). A case whose ROM run RETURNS is then taken through the bench's SECOND
    DIFFERENTIAL too (`bench_differential`), which a child cannot make — every one, by construction, so no list of them
    can fall behind the batteries (a case that IS a registered row is priced by Tier 3 already, and skipped there);
    `second_differential=False` only for a registered row's companion, whose row is priced. `delivered`: the
    deliveries, derived already (`rom_interrupted`). Answers `Interrupted(calls, returned, answer, rom_memory, image,
    delivered, staged, stderr)` for the case's own assertions — `staged` the machine with the frame, as a row registers
    it; `stderr` what the C's child printed (a routine's own child doors may report there: `declare_child_doors`).
    `budget`: the case's own derivation budget, DECLARED from its measured run (`_budget_of`) — a session too long for
    DERIVATION_INSNS' margin; every ROM run of the case is held to it, both ways."""
    calls, delivered, rom_memory, result = rom_interrupted(name, arguments, machine, interrupts, delivered, budget)
    returncode, stderr, image = refusal(name, machine, arguments, seconds=seconds, answered=True,
                                        bind=child_binding(objects=objects, interrupts=delivered,
                                                           before=CHILD_DOORS.get(name, "")))
    returned = result is not None
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
    differ = differing(image, rom_memory, not_compared)
    assert not differ, _describe_differences(name, image, rom_memory, differ)
    if returned and second_differential:
        bench_differential(name, arguments, machine, interrupts, budget, Derived(delivered, rom_memory))
    return Interrupted(calls, returned, answer, rom_memory, image, delivered, aes.staged(name, arguments, machine), stderr)


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
    pokes, delivered = _settled_interrupted(name, arguments, machine, interrupts, budget, derived)
    twin = _registered_twin(name, arguments, pokes, delivered)
    if twin:
        assert twin in {row[0] for row in aes.ROWS.cases}, f"{twin}: its deliveries are recorded, but no priced row"
        return
    tier3, bench = _tier3()
    row = tier3._row(_interrupted_row("taken through interrupts", name, arguments, pokes, delivered))
    tier3.measure(row._replace(dropped=aes.LINE_F_MASK_WINDOW), bench)


def refused_where_the_rom_blocks(name, arguments, machine, *, objects=False, seconds=CHILD_RETURN_SECONDS,
                                 switches=BLOCKS, budget=None):
    """A door user's call that BLOCKS (nothing it waits for satisfied) — or, `switches=YIELDS`, yields: the ROM's run
    reaches dsptch inside a door call, the C's child is refused at the same call as one that would, and up to it the C
    is the ROM's run stopped there — every frame handed, and the whole image against the ROM's memory at the ENTRY of
    the call (`interrupted`, with no interrupt). The same `Interrupted`, for the case's own assertions (`.calls`: how
    many passes it made). `budget`: the case's own derivation budget, declared (`_budget_of`)."""
    taken = interrupted(name, arguments, machine, {}, objects=objects, seconds=seconds, switches=switches, budget=budget)
    assert not taken.returned, f"{name}: the premise — the ROM's run switches at a door call — does not hold: it returned"
    return taken


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
Mark = namedtuple("Mark", "calls spent memory")
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
    priced as well (`bench/tier3.py`'s `uncovered_stretches`). Off by default: the cost is read at every door call."""

    def __init__(self, slice_, cost, others=(), every_door_call=False):
        for start, stop in (slice_, *others):
            assert start != RETURN and stop != ENTRY and start != stop, f"no run is between {start} and {stop}"
        self.slice, self._cost = slice_, cost
        self._ends = frozenset(end for each in (slice_, *others) for end in each)
        marked = (*(ENTRIES if every_door_call else ()), *(end.pc for end in self._ends if isinstance(end, At)))
        self._arrivals = dict.fromkeys(marked, 0)
        self._taken = {ENTRY: Mark(0, None, None)}
        self.timeline = [] if every_door_call else None

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
        here = At(pc, self._arrivals[pc])
        self._arrivals[pc] += 1
        on_the_timeline = self.timeline is not None and (pc in ENTRIES or here in self._ends)
        if not (on_the_timeline or here in self._ends):
            return
        spent = self._cost()
        if on_the_timeline:
            self.timeline.append(Arrival(here, calls, spent))
        if here in self._ends:
            self._taken[here] = Mark(calls, spent, bytes(memory))

    def returned(self, calls):
        """The run RETURNED, `calls` door calls made in all: marked, its memory left to the whole run's differential."""
        self._taken[RETURN] = Mark(calls, self._cost(), None)
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


def vet_the_marks_agree(case_name, ours, the_rom_s, differing_at):
    """THE SLICE IS THE SAME SLICE ON BOTH SHORES: our run's marks (`ours`, a `Marks`) against the ROM's, end by end —
    reached after the same number of door calls, and holding the same memory there (`differing_at(ours, the ROM's)`:
    the addresses two memories differ at, outside what neither shore compares). Refused by name: a slice OUR run
    starts at another door call than the ROM's, a run that DIVERGED BEFORE THE SLICE'S START, one that diverged
    inside it."""
    pairs = zip(ours.slice, the_rom_s.slice, ours.ends("our run"), the_rom_s.ends("the ROM's run"),
                ("starts", "ends"), ("before the slice's start", "inside the slice"))
    for end, the_rom_s_end, mine, the_rom, verb, where in pairs:
        assert mine.calls == the_rom.calls, (
            f"{case_name}: our slice {verb} at door call {mine.calls} ({end}) where the ROM's {verb} at door call "
            f"{the_rom.calls} ({the_rom_s_end}) — another slice of the session than the ROM's")
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
    watch = DoorStops(ENTRIES, ROM_RETURNS, blocks=True, delivered=delivered).marked_with(marks)
    result = run_watched(memory, entry, watch, budget=budget)
    assert result, f"{entry:#x}: a session priced by its slices returns — this one switches processes at a door call"
    return watch.calls


def rom_sliced(name, arguments, pokes, delivered, slice_, *, budget=None, **marked):
    """The ROM's own `addrs.<name>` over `pokes` with the frame `arguments`, `delivered` laid at its door calls, WATCHED
    and MARKED at `slice_`'s ends (`Marks`, each mark `run_cost()` and the memory there; `marked` its options: the
    session's other slices, every door call): `(marks, memory)` — its marks and the memory it left. The ROM's side of
    a slice's pricing, and the whole of a slice's measurement where the ROM is the oracle on both shores."""
    marks, memory = Marks(slice_, run_cost, **marked), make_image(aes.staged(name, arguments, pokes))
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


def rom_timeline(name, arguments, pokes, delivered, traps=(), *, budget=None):
    """The ROM's own session — `addrs.<name>` over `pokes`, `delivered` laid at its door calls — as its `Timeline`'s
    arrivals: every door call and every arrival at the handlers `traps`, each with what the run had spent there, then
    `(RETURN, calls, spent)`. What a battery reads to cut the session into slices under the cap."""
    timeline = Timeline(traps)
    calls = _marked_run(getattr(addrs, name), make_image(aes.staged(name, arguments, pokes)), delivered, timeline, budget)
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
    pokes, delivered = _settled_interrupted(name, arguments, machine, interrupts, budget)
    assert delivered, f"{name}: a session priced by its slices is taken through interrupts — this one has none"
    row = InterruptedRow(name, arguments, pokes, interrupts, delivered, budget)
    companion = _companion(name, arguments, pokes, interrupts, delivered, objects, budget)
    registered = []
    for label, slice_ in slices.items():
        registered.append(_registered(label, row, companion))
        SLICED_ROWS[registered[-1][0]] = Slice(*slice_)
    return registered
