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
  * run past `NESTED_RUN_INSNS`;
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
ROM code over the snapshot as it stands (`_interrupt`: rlr NULL, the dispatcher's guard set, as the machine takes
them) — and the dispatcher's loop run from where the snapshot waits, its forker posting the event, idle moving PD0 to
the ready list, switchto entering it; the run stops where PD0 comes out of its evnt_multi (`AES_ROM_EV_MULTI_RETURN`),
its waits cancelled by ev_multi's own tail. `machine()` then hides the cursor as the running process would (the ROM's
gsx_moff). Every other derivation runs the ROM's code over such a machine and keeps only what the run wrote
(`case.written_by`), named with the routine that made it — and none may reach the dispatcher (`derived`).
"""
import ast
import ctypes
import functools
import operator
import os
import struct
import sys
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, addrs, emu, make_image
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


# THE ENTRIES, one row each: the ROM routines the door serves — every C call of the event layer, keyed by its address
# (`aes/evdoor.h`'s wrappers) — each with its Alcyon frame and how its arguments are read.
ENTRY_FRAMES = {"AES_ROM_EV_MULTI": (EV_MULTI_FRAME, _ev_multi_inputs),
                "AES_ROM_AP_RDWR": (AP_RDWR_FRAME, _ap_rdwr_inputs)}
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
# A nested run's cap. The deepest the batteries reach — every one of them a call the event layer answers — is ap_rdwr
# handing a message to PD0's parked wait, 933 instructions (`test_aes_event.py` names it, beside ev_multi answering a
# mouse rectangle, 806, and holds the cap at NESTED_RUN_MARGIN times the deeper); the margin is for the event layer's
# longer answering paths a later caller stages.
NESTED_RUN_INSNS = 20_000
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


def _served(routine, io_seed, noted=_in_the_recorded_pass):
    """The effect serving `routine`: what it was handed `noted` (`HANDED`, in the recorded pass), the nested run over
    the candidate's image, laid back, its D0 answered."""
    def serve(buf, frame, frame_bytes, answer):
        image, frame = ctypes.string_at(buf, IMAGE_BYTES), ctypes.string_at(frame, frame_bytes)
        noted(handed(routine, frame, image))
        try:
            nested = nested_run(routine, image, frame, io_seed)
        except AssertionError as refused:
            print(refused, file=sys.stderr)         # the core halts next: this is its reason, in the child's stderr
            raise
        for at, value in nested.writes.items():
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


def door_hook(drawing, io_seed=None):
    """The binding a door user's case opens: the door alone, or with the VDI's cores (`aes_gsx.vdi_hook`) too for one
    that `drawing`."""
    return aes.doors(aes_gsx.vdi_hook, event_hook(io_seed)) if drawing else event_hook(io_seed)


# THE SAME DOOR IN A CHILD PROCESS (`vdi_helpers.refusal_over`'s `bind`), where a refusal ends the run and the case reads
# its stderr: every hook a door user's core reaches bound for its one call with no pass to open — the event door, every
# entry served and any other refused, and the VDI's cores a drawing routine calls through `recreate_call_vector`
# (`aes_gsx.vdi_functions`) — into `lib`, the candidate the CHILD loaded and calls (which need not be the one its
# `harness` import would load: a pointer left NULL there is a crash, not a refusal). The frames the door was handed
# are printed with a refusal (`HANDED_LINE`), for the case to read back (`handed_in`).
_TEST_DIR = str(Path(__file__).resolve().parent)
CHILD_BINDING = f"import sys; sys.path.insert(0, {_TEST_DIR!r}); import aes_event; aes_event.bind_in_a_child(lib)"
_CHILD_TRAMPOLINES = []
HANDED_LINE = "the door was handed: "
CHILD_VDI_REFUSED = 3                  # the child's exit status when a VDI call it was not staged for is refused


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


def bind_in_a_child(lib, entries=ENTRIES):
    calls = []
    effects = {entry: _served(entry, None, calls.append) for entry in entries}

    def dispatch(buf, routine, frame, frame_bytes, answer):
        if routine not in effects:
            print(_describe_refusals([routine]), file=sys.stderr)
            return REFUSED_ANSWER
        try:
            return effects[routine](buf, frame, frame_bytes, answer)
        except Exception as refused:   # a callback cannot raise into C (ctypes would answer an undefined word): refused
            if not isinstance(refused, AssertionError):
                print(f"the event door: serving {routine:#x} raised {refused!r}", file=sys.stderr)
            print(HANDED_LINE + repr([tuple(call) for call in calls]), file=sys.stderr)
            return REFUSED_ANSWER
    _CHILD_TRAMPOLINES.extend((PROTOTYPE(dispatch), isr.CALL_VECTOR(_child_vdi)))
    bind_pointer(HOOK_SYMBOL, _CHILD_TRAMPOLINES[-2], lib)
    bind_pointer(isr.CALL_VECTOR_SYMBOL, _CHILD_TRAMPOLINES[-1], lib)


def handed_in(stderr):
    """The door calls a refused child was handed, as it printed them (`HANDED_LINE`): `Handed` each, in order."""
    line, = (line for line in stderr.splitlines() if line.startswith(HANDED_LINE))
    return [Handed(*call) for call in ast.literal_eval(line.removeprefix(HANDED_LINE))]


def refusal(name, pokes, values, *, bind=CHILD_BINDING, io_seed=None):
    """What `addrs.<name>`'s core says over `pokes` with the frame `values`, in a CHILD process with the door bound
    (`vdi_helpers.refusal_over`): `(returncode, stderr, image)`. The values typed as the routine's declared signature."""
    argtypes = vdi.ALCYON[name].argtypes[1:]
    arguments = [(f"ctypes.{argtype.__name__}", str(value)) for argtype, value in zip(argtypes, values)]
    return vdi_helpers.refusal_over(routines.core_symbol(name), pokes, io_seed, arguments=arguments, bind=bind)


# ---- the ROM's own calls of the door's entries: its run WATCHED ------------------------------------------------------
# Where a ROM caller's Line-F word returns to: the word after it — the address the Line-F handler pushes before its
# `jmp (a0)` into the entry ($fee8d0), so the one on the stack at the entry's first instruction.
ROM_RETURNS = frozenset(at + aes.WORD_BYTES for name in ENTRY_NAMES
                        for sites in aes.line_f_call_sites(name).values() for at in sites)


class Blocked(Exception):
    """A watched run (`DoorStops(..., blocks=True)`) reached the dispatcher inside a door call: the ROM would block."""


class DoorStops:
    """A WATCH (`rom_bench.watched`) over a run that calls the door's `entries`: it stops at each entry ITSELF — the
    door a set of exact PCs (`emu.bench_door_arm`), so nothing between the entries is stopped at — `opened(pc, sp,
    memory)` called there and the return address the call left on the stack becoming the next stop, where `closed()`
    is called and the entries are watched again. Refused by name: an entry reached from a return address that is none
    of `returns` (the run reached the event layer by another road). With `blocks`, a stop at the DISPATCHER inside a call
    too, which ends the run there (`Blocked`): where the ROM's call blocks, for a case comparing it with a door's
    refusal."""

    def __init__(self, entries, returns, opened, closed=lambda: None, *, blocks=False):
        self.entries, self.returns = frozenset(entries), frozenset(returns)
        self.first = self.entries
        self._inside = frozenset({addrs.AES_ROM_DSPTCH}) if blocks else frozenset()
        self._opened, self._closed, self._in_call = opened, closed, False

    def stopped(self, pc, sp, memory):
        if not self._in_call:
            back = case.long_in(memory, sp)
            assert back in self.returns, (
                f"the run reached the door's entry {pc:#x} from {back:#x} — not a door call")
            self._opened(pc, sp, memory)
            self._in_call = True
            return frozenset({back}) | self._inside
        if pc in self._inside:
            raise Blocked(pc)
        self._closed()
        self._in_call = False
        return self.first


def run_watched(memory, entry, watch, io_seed=None):
    """The ROM's own `entry` run over `memory` — its frame at `abi.FIRST_ARG`, where `emu.run` leaves it — by the bench's
    door (`emu.run_bench`, `rom_bench.watched`), WATCHED by `watch` (`DoorStops`): the run's result, or None for a run
    the watch ended where it blocks (`Blocked`). The same run as `emu.run`'s, instruction for instruction, held to what
    a derivation is — under DERIVATION_INSNS by DERIVATION_MARGIN, refused if the model could not serve it; `memory` is
    its own, written in place."""
    try:
        result = emu.run_bench(memory, entry, case.long_in(memory, abi.FIRST_ARG), emu.STACK_TOP, emu.SENTINEL,
                               max_insns=DERIVATION_INSNS, door=watch.first, io_seed=io_seed)
        result = rom_bench.watched(result, entry, watch, memory, max_insns=DERIVATION_INSNS)
    except Blocked:
        result = None
    rom_bench.vet_the_run_just_made(f"the ROM's watched run of {entry:#x}")
    if result:
        _vet_the_margin(entry, result["ninsns"])
    return result


def rom_watched(name, arguments, pokes, io_seed=None, *, blocks=False):
    """The ROM's own `addrs.<name>`, run over `pokes` with the frame `arguments`, WATCHED at the door's entries
    (`DoorStops`): `(calls, memory, returned)` — what it hands each entry it calls, in order (`handed_at`: each frame
    where its Line-F word left it, read through its pointers as it stands at the call), the memory it left, and whether
    it returned (False: `blocks`, and it reached the dispatcher inside a call)."""
    calls = []
    memory = bytearray(make_image(aes.staged(name, arguments, pokes)))
    result = run_watched(memory, getattr(addrs, name),
                         DoorStops(ENTRIES, ROM_RETURNS, lambda pc, sp, memory: calls.append(handed_at(pc, sp, memory)),
                                   blocks=blocks), io_seed)
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


def run_event(name, arguments, pokes, *, drawing=False, io_seed=None, dropped_windows=DOOR_DROPS, **kwargs):
    """`aes.run_function` of `addrs.<name>` over `pokes`, the event door bound (and the VDI's cores, `drawing`), the
    mask word and the trap's saved registers dropped where the ROM's run stores them, unpoisoned (above) — and every
    frame the candidate handed the door compared with the ROM's own call's."""
    HANDED.clear()
    result = aes.run_function(name, arguments, pokes, hook=door_hook(drawing, io_seed), io_seed=io_seed,
                              dropped_windows=dropped_windows, **{**POISON_STEERS_THE_EVENT_LAYER, **kwargs})
    _vet_the_frames_handed(name, arguments, pokes, io_seed)
    return result


def register(label, name, arguments, pokes, *, drawing=False, io_seed=None):
    """One priced `VERIFIED_CASES` row of a door user, named `<core>, <label>` (`aes.register`: the mask word staged at
    the value the run leaves, dropped at Tier 3 with its companion) — over `pokes` with `savptr` moved into the stack
    band, so the trap's save lands where neither the row nor its companion compares it and Tier 3 drops nothing else.
    The cost is the same: the trap saves the same frame, elsewhere."""
    return aes.register(label, name, arguments, merge_pokes(pokes, savptr_in_the_band()), hook=door_hook(drawing, io_seed),
                        io_seed=io_seed)


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
# Each derivation's budget, and the margin every derivation is held to under it (`_rom_run`): the deepest of them, a
# window moved by the ROM's wm_set (`test_aes_wmlib.moved`, which `test_aes_event.py` runs under the margin), measured at
# 181,233 instructions — 5.5 times under.
DERIVATION_INSNS = 1_000_000
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


def _interrupt(entry, pokes, regs=None):
    """What an INTERRUPT's ROM code `entry` WROTE over the snapshot and `pokes` as they stand — no lever beneath them:
    the machine takes an interrupt with whatever process state it has (the snapshot's: rlr NULL, the dispatcher's guard
    set) — and the run's final image."""
    final, writes, _regs = _rom_run(make_image(pokes), entry, regs)
    return case.written_by(writes), final


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
    """The Alcyon frame of a routine no C core declares a signature for yet (`aes.staged` packs a declared one's):
    ("w" | "l", value) items in push order, each word the signed or unsigned word it is."""
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


def keys(*scancodes, onto=None):
    """The IKBD ring holding a key per make code of `scancodes`, unread, over `onto` (the snapshot by default): the
    BIOS's own keyboard handler run once per key from its scancode arm (KBD_SCANCODE) in the state the ACIA interrupt
    reaches it in — D0 the byte, A0 the keyboard's ring (what `acia_take_byte` hands it), A5 the handler's base — the
    ASCII its own Keytbl lookup. The event layer polls the ring through the VDI on every ev_multi. A delta, to lay over
    `onto`."""
    state = {}
    for scancode in scancodes:
        delta, _final = _interrupt(addrs.KBD_SCANCODE, merge_pokes(onto, state),
                                   {"d0": scancode, "a0": addrs.IOREC_IKBD, "a5": ACIA_HANDLER_A5})
        state = merge_pokes(state, delta)
    return state


@functools.cache
def pd0_running():
    """PD0 RUNNING, as the scheduler makes it: Return pressed (`keys`) — the key the desk's evnt_multi waits for — and
    the dispatcher's loop run until PD0 comes out of that evnt_multi with it (`_woken`): PD0 alone on the ready list
    and off the not-ready list, PD_STAT 0, its waits cancelled, the dispatcher's guard cleared by switchto, PD1 still
    parked. A delta, to lay over a machine."""
    return _woken(keys(RETURN_KEY))


LEFT_BUTTON = 1                        # the AES's record of the buttons down (AES_BUTTON): a bit each, left bit 0
MOUSE_PACKET_HEADER = vdi_mouse.MOUSE_H["MOUSE_PACKET_HEADER_MASK"]   # a relative packet, no button down
MOUSE_PACKET_LEFT_BUTTON = 0x02        # ...the left button down: bit 1 of the header's MOUSE_PACKET_BUTTONS_MASK


def _packet(header, dx=0, dy=0):
    """A relative mouse packet at PACKET_AT, as the IKBD's handler hands it on."""
    return {PACKET_AT: struct.pack(">Bbb", header, dx, dy)}


@functools.cache
def button_down():
    """The left button DOWN, PD0 running: a packet with the left button down through the VDI's mouse interrupt
    (`VDI_ROM_MOUSE_ISR`, A0 the packet — what the IKBD's mousevec runs), which records the button in its own state
    (MOUSE_BT, CUR_MS_STAT) and calls the AES's button glue (vex_butv's, `AES_ROM_BUTTON_GLUE`: b_click opens the
    click count); then the tick glue ($fed426, vex_timv's) until b_delay's count is final (AES_GL_CLICK_TICKS 0) —
    each an interrupt over the snapshot (`_interrupt`) — then the dispatcher's loop (`_woken`), whose forker posts the
    press to the button wait PD0 is parked in (PD0 owns the mouse) and switches to it. The button stays down, the VDI's
    record and the AES's agreeing. A delta."""
    state, final = _interrupt(addrs.VDI_ROM_MOUSE_ISR, _packet(MOUSE_PACKET_HEADER | MOUSE_PACKET_LEFT_BUTTON),
                              {"a0": PACKET_AT})
    for _tick in range(case.word_in(final, aes.AES_GL_CLICK_TICKS)):
        delta, final = _interrupt(addrs.AES_ROM_TICK_GLUE, state)
        state = merge_pokes(state, delta)
    assert case.word_in(final, aes.AES_GL_CLICK_TICKS) == 0, "the ticks did not resolve the click"
    woken = _woken(state)
    assert case.word_in(make_image(woken), aes.AES_BUTTON) == LEFT_BUTTON, "the press did not leave the button down"
    return woken


@functools.cache
def _hidden_over(woken):
    """The snapshot after `woken()`, then the ROM's gsx_moff — the cursor hidden by the running process, as every
    drawing caller does before it draws — contrl[0..3] stale before it."""
    return aes_gsx.hidden(merge_pokes(aes_gsx.CONTRL_STALE, woken()))


def machine(woken=pd0_running, onto=None):
    """THE DOOR'S MACHINE: PD0 running as `woken` makes it (`pd0_running`, `button_down`), the cursor hidden after
    (`_hidden_over`), contrl[0..3] stale again (`aes_gsx.machine`'s arrangement), `onto` over it."""
    return merge_pokes(_hidden_over(woken), aes_gsx.CONTRL_STALE, onto)


MOUSE_STEP = 127                       # the most one packet moves: a signed byte


def _mouse_packet(x, y, state):
    """`state` with ONE relative packet toward (`x`, `y`) through the VDI's mouse interrupt ($fcfe28, A0 the packet —
    what the IKBD's mousevec runs), which moves the cursor and calls the AES's motion glue (it queues mchange); None
    once the cursor is there."""
    image = make_image(state)
    dx = max(-MOUSE_STEP, min(MOUSE_STEP, x - case.word_in(image, vdi.LINEA_GCURX)))
    dy = max(-MOUSE_STEP, min(MOUSE_STEP, y - case.word_in(image, vdi.LINEA_GCURY)))
    if not dx and not dy:
        return None
    delta, _final = _interrupt(addrs.VDI_ROM_MOUSE_ISR, merge_pokes(state, _packet(MOUSE_PACKET_HEADER, dx, dy)),
                               {"a0": PACKET_AT})
    return merge_pokes(state, delta)


# A point of the MENU BAR, one packet up from the snapshot's mouse: the rectangle the screen manager's evnt_multi waits
# for the mouse to enter (measured: the one move of those tried that wakes it, with MU_M1).
MENU_BAR_POINT = (159, 5)


@functools.cache
def screen_manager_running():
    """PD1 RUNNING — the SCREEN MANAGER — and PD0 still parked in the desk's evnt_multi, as the scheduler makes it: the
    mouse moved onto the menu bar (`_mouse_packet`, over the snapshot), the rectangle PD1 waits for it to enter, and
    the dispatcher's loop run until PD1 comes out of its evnt_multi with it (`_woken`). A delta."""
    return _woken(_mouse_packet(*MENU_BAR_POINT, {}), aes.SCREEN_MANAGER_PD)


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
