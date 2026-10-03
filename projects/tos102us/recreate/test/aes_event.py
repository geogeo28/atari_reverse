"""THE EVENT DOOR — how a battery runs an AES routine that reaches the event layer (`aes/evdoor.h`), and the MACHINES
such a routine is run over, each the state the ROM's own scheduler leaves.

THE DOOR. A C core calls the event layer (ev_multi, ap_rdwr, ...) through its wrapper in `aes/evdoor.h`, which off
target packs the routine's Alcyon frame and hands it to `recreate_call_event_door`. `event_hook` binds that hook, per
case, to a NESTED ORACLE RUN: the ROM routine, at its own address, over a copy of the candidate's image with the frame
where a `jsr` leaves it (`abi.FIRST_ARG`); its writes are laid back over the candidate's image and its D0 answered. So
both shores run the ROM's own event layer over the same machine — the ORACLE inline, through the caller's Line-F word,
the candidate through the door — and the differential is about the C round it. Keyed BY ROM ADDRESS
(`address_hook.AddressHook`): an entry the case does not serve is refused, and the core halts by name.

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
the entry of the call that blocks (`refused_where_the_rom_blocks`). ONE run of the ROM's routine computes every
delivery (`deliveries`: set aside at each delivery's entry, continued there), so a long sequence — keys TYPED one per
wait (`key`, `typed`) — costs a run, not a run per key. A case priced at Tier 3 carries its deliveries in its row
(`register_interrupted`), and every run of its original lays them at the same calls (`delivering`, `replayed`).
"""
import ast
import atexit
import ctypes
import functools
import operator
import os
import struct
import sys
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, addrs, bench_tier3, emu, make_image
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


# ---- what a nested run may spend -----------------------------------------------------------------------------------
# A nested run's cap, and the margin EVERY nested run is held to under it — at run time (`nested_run`), so no table of
# the deepest calls can go stale under it. The deepest the batteries reach, every one a call the event layer answers, is
# mn_do's first ev_multi over its two rectangles with the mouse moved onto a title by an interrupt at its entry, 1,697
# instructions (`test_aes_event.DEEPEST_CALLS` names it beside each entry's deepest); 20 times that is 33,940, and the
# cap is 40,000, a round figure with room above that. The margin is for the event layer's longer answering paths a later
# caller stages: a run inside it is refused by name, the cap to be raised from that run.
NESTED_RUN_INSNS = 40_000
NESTED_RUN_MARGIN = 20
# The hook's answer: served, its D0 in the out-parameter, or refused (AddressHook's REFUSED_ANSWER, 0).
SERVED = 1
HOOK_SYMBOL = "recreate_call_event_door"
PROTOTYPE = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32,
                             ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32))
EVENT_DOOR = AddressHook(HOOK_SYMBOL, PROTOTYPE)
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
    assert not regs["checkpoint"], _at_the_dispatcher(routine, final)
    touched = [name for name in HARDWARE_STREAMS if regs[name]]
    assert not touched, f"the event door: {routine:#x} touched the hardware ({', '.join(touched)}) — the door serves none"
    assert not regs["writes_truncated"], f"the event door: {routine:#x} overflowed the write ledger"
    assert regs["ninsns"] * NESTED_RUN_MARGIN <= NESTED_RUN_INSNS, (
        f"the event door: {routine:#x} spent {regs['ninsns']} instructions — inside NESTED_RUN_INSNS' margin of "
        f"{NESTED_RUN_MARGIN}: raise the cap, from this run")
    return Nested(writes, regs["d0"], regs["ninsns"])


def _at_the_dispatcher(routine, final):
    """Why a nested run of `routine` that reached dsptch is refused, read off the process it was running for: still
    WAITING ($fe40d8), the call would BLOCK; READY, it would YIELD — disp puts the one back on the ready list ($fe4dc4)
    rather than the not-ready one. Either way the machine switches processes, which one run cannot."""
    running = case.long_in(final, aes.AES_RLR) & OS_BUS_ADDR_MASK
    if case.word_in(final, running + aes.PD_STAT) == aes.PD_STAT_WAITING:
        return (f"the event door: {routine:#x} reached the dispatcher (dsptch, {addrs.AES_ROM_DSPTCH:#x}) — the call "
                f"would block: nothing it waits for is satisfied, and the machine would switch away until something "
                f"is, which one nested run cannot model (the case staged nothing the call waits for)")
    return (f"the event door: {routine:#x} reached the dispatcher (dsptch, {addrs.AES_ROM_DSPTCH:#x}) with its "
            f"process still ready — the call would yield: the machine would run the other processes first, which one "
            f"nested run cannot model")


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


def _describe_refusals(refused):
    return (f"the event door was called for {', '.join(f'{at:#x}' for at in refused)}, which this case does not serve "
            f"— it serves {', '.join(f'{at:#x}' for at in ENTRIES)}")


def event_hook(io_seed=None, entries=ENTRIES):
    """The binding `aes.run_function`'s `hook` opens per case: each of `entries` served by its nested run (the case's
    declared I/O bytes handed on), any other address refused."""
    return functools.partial(EVENT_DOOR.staged, {entry: _served(entry, io_seed) for entry in entries}, _describe_refusals)


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
    """`child_binding`'s call: the door, the VDI's cores and the walked routines bound into `lib`. `interrupts`
    (`deliveries`' `{ordinal: (found, wrote)}`) lays each interrupt's effect into the image at the door call of that
    ordinal, before it is served (`_laid_into`) — and the frames handed are printed at the child's exit too, so a call
    that RETURNS reports them."""
    calls = []
    effects = {entry: _served(entry, None, calls.append) for entry in entries}

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
    _CHILD_TRAMPOLINES.extend((door, vdi_cores, walkers))
    bind_pointer(HOOK_SYMBOL, door, lib)
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


def refusal(name, pokes, values, *, bind=CHILD_BINDING, io_seed=None, seconds=vdi_helpers.CHILD_SECONDS, answered=False):
    """What `addrs.<name>`'s core says over `pokes` with the frame `values`, in a CHILD process with the door bound
    (`vdi_helpers.refusal_over`): `(returncode, stderr, image)`. The values typed as the routine's declared signature;
    a child still running after `seconds` raises `subprocess.TimeoutExpired` (a core that loops where the ROM ends).
    `answered`: a core that returns prints its answer, at its declared width (`vdi_helpers.answer_in`)."""
    signature = vdi.ALCYON[name]
    arguments = [(f"ctypes.{argtype.__name__}", str(value)) for argtype, value in zip(signature.argtypes[1:], values)]
    restype = f"ctypes.{signature.restype.__name__}" if answered and signature.restype else None
    return vdi_helpers.refusal_over(routines.core_symbol(name), pokes, io_seed, arguments=arguments, bind=bind,
                                    seconds=seconds, restype=restype)


# A DOOR USER'S C RUN FIRST IN A CHILD: a core that loops where the ROM's run ends (each ev_multi it makes answered at
# once, the loop never left) would hang the case in-process until the watchdog ended the worker — a crash, no failure.
# In a child it is a timeout, and the case FAILS by it (`refusal`'s `seconds`, far above the measured child's 2-4 s).
CHILD_RETURN_SECONDS = 30
# The guards that returned, by (routine, frame, machine, objects): one child per distinct call in a worker — a case run
# both directly and through its Line-F word is the same C call twice.
_RETURNED_IN_A_CHILD = set()


def returns_in_a_child(name, values, pokes, *, objects=False, seconds=CHILD_RETURN_SECONDS):
    """`addrs.<name>`'s core over `pokes` with the frame `values` RETURNS in a child (`refusal`, the walked routines
    served with `objects`) — the guard a door user's case runs before its in-process differential (`run_guarded`)."""
    guarded = (name, tuple(values), bool(objects), tuple((at, bytes(data)) for at, data in sorted(pokes.items())))
    if guarded in _RETURNED_IN_A_CHILD:
        return
    returncode, stderr, _image = refusal(name, pokes, values, bind=child_binding(objects=bool(objects)),
                                         seconds=seconds)
    assert returncode == 0, stderr
    _RETURNED_IN_A_CHILD.add(guarded)


# ---- the ROM's own calls of the door's entries: its run WATCHED ------------------------------------------------------
# Where a ROM caller's Line-F word returns to: the word after it — the address the Line-F handler pushes before its
# `jmp (a0)` into the entry ($fee8d0), so the one on the stack at the entry's first instruction.
ROM_RETURNS = frozenset(at + aes.WORD_BYTES for name in ENTRY_NAMES
                        for sites in aes.line_f_call_sites(name).values() for at in sites)


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
    and the stop refuses by name (`_vet_found`). `calls`: the door calls entered so far."""

    def __init__(self, entries, returns, opened, closed=lambda: None, *, blocks=False, delivered=None):
        self.entries, self.returns = frozenset(entries), frozenset(returns)
        self.first = self.entries
        self._inside = frozenset({addrs.AES_ROM_DSPTCH}) if blocks else frozenset()
        self._opened, self._closed, self._in_call = opened, closed, False
        self._delivered = delivered or {}
        self.calls = 0

    @property
    def between_calls(self):
        """Is the run outside every door call — so a stop at an entry opens the next?"""
        return not self._in_call

    def stopped(self, pc, sp, memory):
        if not self._in_call:
            back = case.long_in(memory, sp)
            assert back in self.returns, (
                f"the run reached the door's entry {pc:#x} from {back:#x} — not a door call")
            if self.calls in self._delivered:
                found, wrote = self._delivered[self.calls]
                _vet_found(memory, found, f"door call {self.calls} ({pc:#x})")
                _lay(memory, wrote)
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


def run_watched(memory, entry, watch, io_seed=None):
    """The ROM's own `entry` run over `memory` — its frame at `abi.FIRST_ARG`, where `emu.run` leaves it — by the bench's
    door, entered as `emu.run` enters it (`rom_bench.original_entered`: its register file, no chip declared) and
    WATCHED by `watch` (`DoorStops`, `rom_bench.watched`): the run's result, or None for a run the watch ended where it
    blocks (`Blocked`). The same run as `emu.run`'s, instruction for instruction, held to what a derivation is — under
    DERIVATION_INSNS by DERIVATION_MARGIN, refused if the model could not serve it; `memory` is its own, written in
    place. Vetted HOWEVER the run ends: a watch that ends it early by raising (a run stopped at an entry,
    `_AtTheEntry`) leaves a prefix a case may build on, held to the same refusals and margin."""
    try:
        result = rom_bench.original_entered(memory, entry, watch.first, io_seed=io_seed, max_insns=DERIVATION_INSNS)
        result = rom_bench.watched(result, entry, watch, memory, max_insns=DERIVATION_INSNS)
    except Blocked:
        result = None
    finally:
        rom_bench.vet_the_run_just_made(f"the ROM's watched run of {entry:#x}")
        _vet_the_margin(entry, _instructions_run())
    return result


def _instructions_run():
    """The instructions the bench run just ended — at its end or at the stop a watch raised in — has spent: the
    oracle's running total (what each segment's result reports), read because a run a watch ended by raising hands
    back no result."""
    return emu._LIB.osh_num_insns()


def rom_watched(name, arguments, pokes, io_seed=None, *, blocks=False):
    """The ROM's own `addrs.<name>`, run over `pokes` with the frame `arguments`, WATCHED at the door's entries
    (`_watched_through`, nothing delivered): `(calls, memory, returned)` — what it hands each entry it calls, in order
    (`handed_at`: each frame where its Line-F word left it, read through its pointers as it stands at the call), the
    memory it left (at the entry of the blocking call, for one that blocks), and whether it returned (False: `blocks`,
    and it reached the dispatcher inside a call)."""
    calls, memory, result = _watched_through(name, arguments, pokes, {}, io_seed=io_seed, blocks=blocks)
    return calls, memory, result is not None


def rom_handed(name, arguments, pokes, io_seed=None):
    """What the ROM's own `addrs.<name>` hands each door entry it calls, in order (`rom_watched`)."""
    return rom_watched(name, arguments, pokes, io_seed)[0]


def _vet_the_frames_handed(name, arguments, pokes, io_seed):
    """The door calls the candidate made (`HANDED`) are the ROM's own, frame for frame (`rom_handed`)."""
    ours, the_rom_s = list(HANDED), rom_handed(name, arguments, pokes, io_seed)
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
              **kwargs):
    """`aes.run_function` of `addrs.<name>` over `pokes`, the event door bound (and the VDI's cores, `drawing`, and a
    walker's routines, `objects`: `door_hook`), the mask word and the trap's saved registers dropped where the ROM's
    run stores them, unpoisoned (above) — and every frame the candidate handed the door compared with the ROM's own
    call's."""
    HANDED.clear()
    result = aes.run_function(name, arguments, pokes, hook=door_hook(drawing, io_seed, objects), io_seed=io_seed,
                              dropped_windows=dropped_windows, **{**POISON_STEERS_THE_EVENT_LAYER, **kwargs})
    _vet_the_frames_handed(name, arguments, pokes, io_seed)
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


def _settled_interrupted(name, arguments, machine, interrupts):
    """`machine` as a row taken through `interrupts` stages it — `savptr` moved into the stack band (`register`'s
    reason) and the mask word at the value the ROM's run leaves, refused where that run blocks — and the DELIVERIES that
    run took: `(pokes, delivered)`. ONE derivation serves the row: the settled machine differs from the one the
    deliveries were derived over in the mask word alone, which no interrupt reads and no delivery is checked at
    (`_NOT_COMPARED`) — every replay over the settled machine checks the rest (`DoorStops`), and
    `test_boot_snapshot.py` derives every registered row's deliveries again over its settled machine to pin it."""
    pokes = merge_pokes(machine, savptr_in_the_band())
    _calls, delivered, rom_memory, result = rom_interrupted(name, arguments, pokes, interrupts)
    assert result, f"{name}: a priced row returns — the ROM's run taken through these interrupts blocks"
    mask_word = case.word_in(rom_memory, aes.AES_LINEF_MASK_WORD)
    return merge_pokes(pokes, aes.field_pokes("AES", LINEF_MASK_WORD=mask_word)), delivered


def interrupted_row(label, name, arguments, machine, interrupts):
    """A `VERIFIED_CASES` row of a door user TAKEN THROUGH `interrupts`, named `<core>, <label>`, over `machine` as such
    a row stages it (`_settled_interrupted`): the row carries its DELIVERIES, which every run of its ORIGINAL lays at
    the same door calls — Tier 3's on both sides (`delivering`), the snapshot's sweeps (`replayed`)."""
    return _interrupted_row(label, name, arguments, *_settled_interrupted(name, arguments, machine, interrupts))


def _interrupted_row(label, name, arguments, pokes, delivered):
    return case.verified_row(f"{routines.core_symbol(name)}, {label}", getattr(addrs, name), {},
                             aes.staged(name, arguments, pokes), delivered=delivered)


# The rows `register_interrupted` registered, `{row name: (name, arguments, settled pokes, interrupts, delivered)}`: what
# a row's deliveries were derived from, for the cases that derive them again (`rederived`).
INTERRUPTED_ROWS = {}


def rederived(row_name):
    """The deliveries of the registered row `row_name` DERIVED AGAIN, over the snapshot as it stands now
    (`harness.set_base_image`): the interrupts' own code run afresh — for the sweep that fills the snapshot's MASK with
    noise, where an interrupt reading a masked byte must show it (the deliveries derived over the pristine snapshot,
    laid as they are, would hide it)."""
    assert row_name in INTERRUPTED_ROWS, f"{row_name}: no row taken through interrupts registered by that name"
    name, arguments, pokes, interrupts, _delivered = INTERRUPTED_ROWS[row_name]
    return deliveries(name, arguments, pokes, interrupts)


def register_interrupted(label, name, arguments, machine, interrupts, *, objects=False):
    """One PRICED `interrupted_row`, registered (`aes.ROWS`) — the mask word dropped at Tier 3 with the COMPANION a
    drop needs: the same interrupted differential (`interrupted`, `objects` its, over the row's own deliveries),
    comparing every byte outside the stack band. The row's own pricing is its second differential, so the companion
    does not make one again."""
    pokes, delivered = _settled_interrupted(name, arguments, machine, interrupts)
    row_name, entry, _regs, staged, *_rest = _interrupted_row(label, name, arguments, pokes, delivered)
    INTERRUPTED_ROWS[row_name] = (name, arguments, pokes, interrupts, delivered)
    companion = functools.partial(interrupted, name, arguments, pokes, interrupts, objects=objects,
                                  not_compared=frozenset(case.STACK_BAND), delivered=delivered,
                                  second_differential=False)
    return aes.ROWS.register(row_name, entry, staged, dropped=aes.LINE_F_MASK_WINDOW, undropped=companion,
                             delivered=delivered)


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
assert MESSAGE_AT + MESSAGE_BYTES <= BAND_AT + BAND_BYTES
# Each derivation's budget, and the margin every derivation is held to under it (`_rom_run`, and the ROM's watched runs):
# the deepest of them, the ROM's draw_change of a lower window moved and resized, watched for its door calls
# (`test_aes_wm_update.deepest_derivation()`, which `test_aes_event.py` runs under the margin), measured at 244,097
# instructions — 6.1 times under.
DERIVATION_INSNS = 1_500_000
DERIVATION_MARGIN = 5


def _vet_the_margin(entry, insns):
    assert insns * DERIVATION_MARGIN <= DERIVATION_INSNS, (
        f"the derivation's run of {entry:#x} spent {insns} instructions — inside DERIVATION_INSNS' margin of "
        f"{DERIVATION_MARGIN}: raise the budget, from this run")


def _rom_run(image, entry, regs=None, stop_pc=0):
    """`emu.run` of a derivation: under DERIVATION_INSNS by DERIVATION_MARGIN, its write ledger whole."""
    final, writes, regs_out = emu.run(image, entry, dict(regs or {}), max_insns=DERIVATION_INSNS, stop_pc=stop_pc)
    assert not regs_out["writes_truncated"], f"the derivation's run of {entry:#x} overflowed the write ledger"
    _vet_the_margin(entry, regs_out["ninsns"])
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
    return b"".join(struct.pack(">H", value & 0xFFFF) if kind == "w" else struct.pack(">I", value)
                    for kind, value in items)


def _woken(pokes, pd=aes.SHELL_PD):
    """`pokes` (laid over the snapshot as it is) with the event the parked `pd` waits for, then the DISPATCHER'S OWN
    LOOP run from where the snapshot waits in it (`AES_ROM_DISP_LOOP`): forker posts the event to the wait, idle moves
    the process to the ready list, switchto enters it — and the run stops where it comes out of its evnt_multi
    (`AES_ROM_EV_MULTI_RETURN`), its waits cancelled by ev_multi's own tail. The delta, the event's pokes in it; `pd`
    the one running, alone on the ready list."""
    final, writes, regs = _rom_run(make_image(pokes), addrs.AES_ROM_DISP_LOOP, stop_pc=addrs.AES_ROM_EV_MULTI_RETURN)
    assert regs["checkpoint"], "the dispatcher's loop switched to no process that came out of its evnt_multi"
    assert aes.list_of(final, aes.AES_RLR) == [pd], f"the event woke another process than the PD at {pd:#x}"
    return merge_pokes(pokes, case.written_by(writes))


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
    image, written = bytearray(make_image(onto or {})), {}
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


COMPARED_BLOCK_BYTES = 0x1000          # images compared a block at a time, bytewise only inside a block that differs


def _differing_addresses(one, other):
    """The addresses two images (bytes-like, of one size) differ at, in order."""
    one, other = bytes(one), bytes(other)
    return [at for block in range(0, len(one), COMPARED_BLOCK_BYTES)
            if one[block:block + COMPARED_BLOCK_BYTES] != other[block:block + COMPARED_BLOCK_BYTES]
            for at in range(block, min(block + COMPARED_BLOCK_BYTES, len(one))) if one[at] != other[at]]


def _changed(before, after):
    """The bytes `after` differs from `before` at, as pokes."""
    return {at: bytes([after[at]]) for at in _differing_addresses(before, after)}


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
    return merge_pokes(onto, _changed(image, memory))


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
    run_on = bytearray(image)
    for at, data in (inputs or {}).items():
        run_on[at:at + len(data)] = data
    _final, writes, _regs = _rom_run(run_on, entry, regs)
    written = case.written_by(writes)
    for at, data in written.items():
        image[at:at + len(data)] = data
    return written


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
        written = merge_pokes(written, _interrupt_over(image, addrs.AES_ROM_TICK_GLUE))
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
Interrupted = namedtuple("Interrupted", "calls returned answer rom_memory image delivered staged")
_NOT_COMPARED = frozenset(case.STACK_BAND) | frozenset(at for lo, hi, _why in DOOR_DROPS for at in range(lo, hi))


def _as_sequence(interrupts):
    return interrupts if isinstance(interrupts, tuple) else (interrupts,)


class _AtTheEntry(Exception):
    """A watched run stopped at the entry of the door call of the ordinal asked for: its memory there, what was
    delivered at it laid in, and the call it makes (`handed_at`)."""

    def __init__(self, memory, call):
        super().__init__()
        self.memory, self.call = memory, call


def _watched_through(name, arguments, pokes, delivered, stop_at=None, *, io_seed=None, blocks=True):
    """The ROM's own `addrs.<name>` WATCHED at the door's entries, `delivered` (`deliveries`' `{ordinal: (found,
    wrote)}`) laid into its memory at the entry of each door call of that ordinal, each checked first (`DoorStops`):
    `(calls, memory, result)` — the frames handed, read after; the memory it left, or at the entry of the call that
    blocks (`blocks`: stopped at the dispatcher inside a call); its result, None where it blocked. Stopped at the entry
    of the call of ordinal `stop_at` instead, by `_AtTheEntry`."""
    calls, at_the_entry = [], []
    memory = bytearray(make_image(aes.staged(name, arguments, pokes)))

    def opened(pc, sp, memory):
        call = handed_at(pc, sp, memory)
        if len(calls) == stop_at:
            raise _AtTheEntry(bytes(memory), call)
        calls.append(call)
        at_the_entry[:] = [bytes(memory)]
    watch = DoorStops(ENTRIES, ROM_RETURNS, opened, blocks=blocks, delivered=delivered)
    result = run_watched(memory, getattr(addrs, name), watch, io_seed)
    return calls, (memory if result else at_the_entry[0]), result


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


def _run_interrupting(memory, entry, interrupts):
    """The ROM's own `entry` over `memory` (its frame at abi.FIRST_ARG), ONE watched run that takes each interrupt of
    `interrupts` at the entry of its door call (above): `(delivered, result)` — `{ordinal: (found, wrote)}`, and the
    run's result, None where it blocked. Held to DERIVATION_INSNS by its margin over every segment, each segment's
    refusals vetted as it ends. The last segment's vets run on a run that ENDED (returned or blocked) only: after an
    interrupt's own run failed, the oracle's counters are that run's, and a vet of them would replace its error."""
    if isinstance(interrupts, Waits):
        interrupts.begin_run()
    watch = DoorStops(ENTRIES, ROM_RETURNS, lambda *_stop: None, blocks=True)
    delivered, spent = {}, 0
    who = f"the ROM's interrupted run of {entry:#x}"
    result = rom_bench.original_entered(memory, entry, watch.first, max_insns=DERIVATION_INSNS)
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
            left = DERIVATION_INSNS - spent - result["ninsns"]
            assert left > 0, f"{who} did not return within {DERIVATION_INSNS} instructions"
            result = emu.bench_resume(entry, max_insns=left)
    except Blocked:
        result = None
    finally:
        emu.bench_abort()
    rom_bench.vet_the_run_just_made(who)
    _vet_the_margin(entry, spent + _instructions_run())
    return delivered, result


def deliveries(name, arguments, pokes, interrupts):
    """What each interrupt of `interrupts` WRITES, run over the ROM's own memory at the entry of the door call it is
    delivered at — `{ordinal: interrupt or (interrupt, ...)}`, or a SCHEDULE `interrupts(ordinal, entry)` answering
    one (or None) at every call (`typed`): `{ordinal: (found, wrote)}` — the bytes that memory held at each address the
    delivery writes, then what it wrote there. ONE run of the routine takes them all (`_run_interrupting`); an ordinal
    the run never reaches, or a schedule left with interrupts `pending`, is refused by name."""
    memory = bytearray(make_image(aes.staged(name, arguments, pokes)))
    delivered, _result = _run_interrupting(memory, getattr(addrs, name), interrupts)
    undelivered = interrupts.pending if isinstance(interrupts, Waits) else sorted(set(interrupts) - set(delivered))
    assert not undelivered, f"{name}: the ROM's run made no door call to deliver {undelivered} at"
    return delivered


def rom_interrupted(name, arguments, pokes, interrupts, delivered=None):
    """The ROM's own `addrs.<name>` over `pokes` with the frame `arguments`, WATCHED at the door's entries, each of
    `interrupts` delivered over its memory at the entry of that door call (`deliveries`; or `delivered`, derived
    already) — then REPLAYED: one run laying them in at no cost, each checked against the memory it lands on
    (`_watched_through`), the run every shore is compared with: `(calls, delivered, memory, result)` — the frames handed
    (each read after the interrupt), the deliveries (`{ordinal: (found, wrote)}`), the memory it left (or, for a run
    that BLOCKS, its memory at the entry of the blocking call), and the run's result (None: it blocked)."""
    if delivered is None:
        delivered = deliveries(name, arguments, pokes, interrupts)
    calls, memory, result = _watched_through(name, arguments, pokes, delivered)
    return calls, delivered, memory, result


def delivering(delivered):
    """A watch over a run of a row whose interrupts are DELIVERED (`register_interrupted`): `delivered` laid at its door
    calls, each checked first, and a call that reaches the dispatcher refused by name (`DoorStops`) — the ROM's replays
    (`replayed`) and Tier 3's original."""
    return DoorStops(ENTRIES, ROM_RETURNS, lambda *_stop: None, blocks=True, delivered=delivered)


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
                not_compared=None, delivered=None, second_differential=True):
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
    delivered, staged)` for the case's own assertions — `staged` the machine with the frame, as a row registers it."""
    calls, delivered, rom_memory, result = rom_interrupted(name, arguments, machine, interrupts, delivered)
    returncode, stderr, image = refusal(name, machine, arguments, seconds=seconds, answered=True,
                                        bind=child_binding(objects=objects, interrupts=delivered))
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
        bench_differential(name, arguments, machine, interrupts)
    return Interrupted(calls, returned, answer, rom_memory, image, delivered, aes.staged(name, arguments, machine))


@functools.cache
def _tier3():
    """bench/tier3.py and the cross-compiled cores (`RomBench`), loaded where the first case asks: the module imports
    every battery, so importing it here at this module's import would be circular."""
    tier3 = bench_tier3()
    return tier3, tier3.RomBench()


@functools.cache
def _registered_image(row_name):
    """The staged image of the registered row `row_name` (`INTERRUPTED_ROWS`), as its run starts."""
    name, arguments, pokes, _interrupts, _delivered = INTERRUPTED_ROWS[row_name]
    return bytes(make_image(aes.staged(name, arguments, pokes)))


def _registered_twin(name, arguments, pokes, delivered):
    """The registered row (`register_interrupted`) this case's row would BE — the same routine, the same staged image
    and the same deliveries — or None."""
    image = bytes(make_image(aes.staged(name, arguments, pokes)))
    return next((row_name for row_name, (routine, _arguments, _pokes, _interrupts, row_delivered)
                 in INTERRUPTED_ROWS.items()
                 if routine == name and row_delivered == delivered and _registered_image(row_name) == image), None)


def bench_differential(name, arguments, machine, interrupts):
    """The bench's SECOND DIFFERENTIAL of a case TAKEN THROUGH `interrupts` whose ROM run returns: the case as a row
    (`interrupted_row`), measured (`tier3.measure`) — the callee-saved registers, the odd-access surface, the write
    ledger the mask word's drop is vetted against, both sides' refusal tallies, the streams, the whole image: what the
    C's Tier 1 child cannot report. A case whose row IS a registered one (`_registered_twin`) is not measured a third
    time: Tier 3 prices that row (`make bench`'s table, `test_tier3.py`'s row test) — it must be priced, by name."""
    pokes, delivered = _settled_interrupted(name, arguments, machine, interrupts)
    twin = _registered_twin(name, arguments, pokes, delivered)
    if twin:
        assert twin in {row[0] for row in aes.ROWS.cases}, f"{twin}: its deliveries are recorded, but no priced row"
        return
    tier3, bench = _tier3()
    row = tier3._row(_interrupted_row("taken through interrupts", name, arguments, pokes, delivered))
    tier3.measure(row._replace(dropped=aes.LINE_F_MASK_WINDOW), bench)


def refused_where_the_rom_blocks(name, arguments, machine, *, objects=False, seconds=CHILD_RETURN_SECONDS,
                                 switches=BLOCKS):
    """A door user's call that BLOCKS (nothing it waits for satisfied) — or, `switches=YIELDS`, yields: the ROM's run
    reaches dsptch inside a door call, the C's child is refused at the same call as one that would, and up to it the C
    is the ROM's run stopped there — every frame handed, and the whole image against the ROM's memory at the ENTRY of
    the call (`interrupted`, with no interrupt). The same `Interrupted`, for the case's own assertions (`.calls`: how
    many passes it made)."""
    taken = interrupted(name, arguments, machine, {}, objects=objects, seconds=seconds, switches=switches)
    assert not taken.returned, f"{name}: the premise — the ROM's run switches at a door call — does not hold: it returned"
    return taken
