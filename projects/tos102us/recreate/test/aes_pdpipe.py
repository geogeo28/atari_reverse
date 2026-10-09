"""PROCESSES AND THEIR PIPES — the machines `src/aes/pdpipe.c`'s batteries run over, each made by the ROM's own code,
and THE STAGED APPLICATION: the one way this suite makes a third process.

THE MACHINES. A process descriptor, a pipe, a wait on a pipe are the scheduler's state: none is poked. Each is what a
ROM run leaves (`aes_event.derived`: the run's writes, the stack band out) over a machine the scheduler made
(`aes_event.machine`: PD0 running; `screen_manager_running`: PD1 running, PD0 still parked in the desk's evnt_multi):
  * a pipe holding messages: the ROM's own ap_rdwr(WRITE) — appl_write's implementation — once a message (`sent`);
  * an EVENT BLOCK as aqueue is handed one: the ROM's ap_rdwr stopped where iasync calls aqueue (`at_aqueue`) — the EVB
    taken off the free list, on the running process's list, its event bit taken — with what iasync hands beside it;
  * a WRITER WAITING on a full pipe, its reader running (`writer_waiting`): the screen manager fills PD0's pipe and
    blocks in the write that no longer fits (`aes_event.parked`), and the dispatcher's own loop then runs PD0 out of
    the desk's evnt_multi — whose message wait the first write was handed to.
What a CALLER hands in is staged in this module's band: a name, a QPB, a message, a buffer to read into.

A STAGED APPLICATION (`staged_application`). The snapshot has two processes, and no accessory. A THIRD is made the way
the machine makes one — the ROM's own pstart, run by PD0, over the spare static PD — and what is staged is only its
PROGRAM: a stub of exactly three instructions that pushes one immediate, makes ONE Line-F call of the ROM's own call
word, and jumps to the oracle's sentinel (`stub`; `vet_the_stub` holds any stub to that shape). It is a LABELLED
MACHINE CLASS: every case over it names the class (`STAGED_APPLICATION`, in its id or its docstring — a battery holds
its own cases to that), is Tier 1 only (never registered as a row), and is never cited as what a real machine does — a
real third process is an accessory, loaded from disk.
`started` is the same machine after the dispatcher has ENTERED the application: PD0 parked waiting for a key, the
application running at its stub's first instruction. `called` is THAT SAME RUN of the dispatcher's loop carried on —
the application's own program, on the stack and with the registers switchto left it — until its one call has parked
it and the loop begins again; `resumed` wakes PD0 again by a key — three processes, the third waiting on what its
program asked for. A later battery that needs the application to run on (a call that returns, a second wait) drives
the scheduler from `staged_application(...).machine` with its own interrupts.

THE C RUNS FIRST IN A FORK, every run of it (`run`: `aes_event.run_core_guarded`) — and a case that MEANS to show a
halt or a return in a child does so in one too (`refused`, `refused_leaving`, `answered`: `aes_event.core_in_a_fork`).

THE ATTRIBUTION PASS runs on every case, but for the cases that say why not (`steered=`), whose pass is narrowed to
their reasons: see STEERS_*.
"""
import functools
import struct
from collections import namedtuple

from harness import addrs, emu, make_image
from recreate_kit.os_map import OS_BUS_ADDR_MASK

import abi
import aes
import aes_event
import case
import vdi
from case import merge_pokes
from opcodes import LINE_F, PUSH_LONG_IMMEDIATE, PUSH_WORD_IMMEDIATE

IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG
PD_MATCH, FPDNM, GETPD, PSTART = "AES_ROM_PD_MATCH", "AES_ROM_FPDNM", "AES_ROM_GETPD", "AES_ROM_PSTART"
UDA_INSUPER, PSETUP, DOQ, AQUEUE, AP_FIND = ("AES_ROM_UDA_INSUPER", "AES_ROM_PSETUP", "AES_ROM_DOQ", "AES_ROM_AQUEUE",
                                             "AES_ROM_AP_FIND")
SIGNATURES = {
    PD_MATCH: (aes.WORD_ANSWER, (IMAGE, LONG, WORD, LONG)),
    FPDNM: (aes.LONG_ANSWER, (IMAGE, LONG, WORD)),
    GETPD: (aes.LONG_ANSWER, (IMAGE,)),
    UDA_INSUPER: (None, (IMAGE, LONG)),
    PSETUP: (None, (IMAGE, LONG, LONG)),
    PSTART: (aes.LONG_ANSWER, (IMAGE, LONG, LONG, LONG)),
    DOQ: (None, (IMAGE, WORD, LONG, LONG)),
    AQUEUE: (None, (IMAGE, WORD, LONG, LONG)),
    AP_FIND: (aes.WORD_ANSWER, (IMAGE, LONG)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)

PDPIPE = aes.header_constants("pdpipe.h")
APMSG = aes.header_constants("apmsg.h")
MESSAGE_BYTES = aes_event.MESSAGE_BYTES
MESSAGE_OWN_WORDS = (MESSAGE_BYTES - APMSG["AP_MSG_WORDS"]) // aes.WORD_BYTES     # five, after the three every message has
WM_REDRAW = aes.header_constants("wmupdate.h")["WM_REDRAW"]
AP_RDWR_READ, AP_RDWR_WRITE = 1, aes.AP_RDWR_WRITE     # iasync's codes for aqueue ($fef7a2: arms 1 and 2)
SHELL_PID, SCREEN_MANAGER_PID, APPLICATION_PID = 0, 1, 2
STATIC_PDS = tuple(aes.AES_PD_TABLE + index * aes.PD_BYTES for index in range(aes.AES_PD_COUNT))
SPARE_PD = STATIC_PDS[APPLICATION_PID]                  # the third static PD: never started in the snapshot
SNAPSHOT_STATIC_PIDS = 2                                # the static PDs gem_main set up: the shell's and the screen manager's
PIPE_MESSAGES = aes.PD_QUEUE_BYTES // MESSAGE_BYTES     # the messages a pipe holds: eight

# ---- the band: what a caller hands in ---------------------------------------------------------------------------------
BAND_OFFSET = 0x3400                   # in the form/menu/window layers' part of the window, clear of every claim
BAND_BYTES = 0x240
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES,
                         "test/aes_pdpipe.py: names, a QPB, messages, a staged application's stub, a long write")
NAME_AT = BAND_AT                      # a name looked for: nine characters, their NUL, and what a longer one runs into
NAME_BYTES = 0x20
QPB_AT = NAME_AT + NAME_BYTES          # a QPB: the process, the count, the buffer
QPB_ROOM = 0x10
MESSAGE_AT = QPB_AT + QPB_ROOM         # what a write hands in: up to two messages' bytes
MESSAGE_ROOM = 0x30
BUFFER_AT = MESSAGE_AT + MESSAGE_ROOM  # what a read copies into
BUFFER_BYTES = 0x30
STUB_AT = BUFFER_AT + BUFFER_BYTES     # the staged application's program...
STUB_BYTES = 0x10
APPLICATION_NAME_AT = STUB_AT + STUB_BYTES             # ...and the name pstart is handed for it
LONG_WRITE_AT = BAND_AT + 0x100        # a write of more than a pipe holds (a message and the PDs it runs on over) — or
                                       # the room a WHOLE pipe is read into
LONG_WRITE_BYTES = 0x100
ELSEWHERE_AT = LONG_WRITE_AT + LONG_WRITE_BYTES        # a pipe's bytes where no PD holds them: three messages' room
ELSEWHERE_BYTES = 0x40
assert APPLICATION_NAME_AT + NAME_BYTES <= LONG_WRITE_AT and ELSEWHERE_AT + ELSEWHERE_BYTES == BAND_AT + BAND_BYTES


STALE_BUFFER = {BUFFER_AT: bytes([case.SLACK_FILL]) * BUFFER_BYTES}      # the read buffer before a read: a byte not copied shows


def name_pokes(name, at=NAME_AT):
    """`name` (bytes) and its NUL at `at`, the rest of the name's room STALE: a byte copied past the NUL shows."""
    assert len(name) < NAME_BYTES
    return {at: name + b"\0" + bytes([case.SLACK_FILL]) * (NAME_BYTES - len(name) - 1)}


QPB = aes_event.QPB                    # the process, the count, the buffer: the one layout (`aes_event.QPB`)


def qpb_pokes(pid, count, buffer, at=QPB_AT):
    """A QPB at `at` — refused by name where its `count` bytes at `buffer` would lie over a staged application's
    PROGRAM: the stub's room is directly behind the read buffer's, and a read of more than the buffer holds would
    rewrite it (the application then entered would be no longer the class's)."""
    first = buffer & OS_BUS_ADDR_MASK
    assert not (first < STUB_AT + STUB_BYTES and STUB_AT < first + count), (
        f"a QPB of {count} bytes at {buffer:#x} lies over a staged application's stub ({STUB_AT:#x}): a read there "
        f"would rewrite its program")
    return {at: QPB.pack(pid, count, buffer)}


def message(type_, *words, extra=0, sender=SHELL_PID):
    """A message as GEM lays it: the type, the sender, the bytes past the sixteen, five words of its own."""
    assert len(words) <= MESSAGE_OWN_WORDS
    return struct.pack(f">3h{MESSAGE_OWN_WORDS}h", type_, sender, extra, *words, *[0] * (MESSAGE_OWN_WORDS - len(words)))


def redraw(window, x, y, w, h):
    return message(WM_REDRAW, window, x, y, w, h)


# ---- appl_find AS A PROGRAM CALLS IT: the ROM's own `trap #2` door ------------------------------------------------------
# ap_find copies its name into a frame with no bound, on over its CALLER's saved A6 — so where the ROM stops returning
# depends on where that caller's frame lies (`aes/pdpipe.h`, THE PREMISE). The caller that matters is the real one:
# aes_dispatch, entered by the trap handler on the running process's own UDA stack. The parameter block a program
# hands the trap is staged in the band: the control array (the opcode, no intin, one intout, one addrin), the block's
# six pointers, and the arrays — over the message's and the read buffer's room, which an appl_find leaves alone.
CONTROL_AT = MESSAGE_AT
CONTROL_WORDS = 5                      # the opcode, then the counts of intin, intout, addrin and addrout
PARAMETER_BLOCK = struct.Struct(">6I")  # control, global, intin, intout, addrin, addrout
ARRAY_ROOM = 0x8                       # an array of this call's: a word of intout, a pointer of addrin
PARAMETER_BLOCK_AT = CONTROL_AT + 2 * ARRAY_ROOM
INTOUT_AT = BUFFER_AT
ADDRIN_AT = INTOUT_AT + ARRAY_ROOM
GLOBAL_AT = ADDRIN_AT + ARRAY_ROOM
assert PARAMETER_BLOCK_AT + PARAMETER_BLOCK.size <= MESSAGE_AT + MESSAGE_ROOM
UNANSWERED = 0x5A5A                    # the intout word before the call: an answer never written shows
TrapCall = namedtuple("TrapCall", "answer callers_a6 final")


def _appl_find_staged(name, machine):
    no_intin, one_intout, one_addrin, no_addrout = 0, 1, 1, 0
    control = struct.pack(f">{CONTROL_WORDS}H", addrs.AES_ROM_AP_FIND_OPCODE, no_intin, one_intout, one_addrin, no_addrout)
    block = PARAMETER_BLOCK.pack(CONTROL_AT, GLOBAL_AT, 0, INTOUT_AT, ADDRIN_AT, 0)
    return merge_pokes(machine, name_pokes(name), {CONTROL_AT: control, PARAMETER_BLOCK_AT: block,
                                                   INTOUT_AT: struct.pack(">H", UNANSWERED),
                                                   ADDRIN_AT: struct.pack(">I", NAME_AT)})


def appl_find_by_trap(name, machine=None):
    """The ROM's appl_find(`name`) as the running process of `machine` (`running()`: PD0) calls it — through the trap
    handler from where it takes the process's UDA stack (`GEM_TRAP2_AES_ON_UDA`) to where aes_entry has returned
    (`GEM_TRAP2_AES_BACK`), under the oracle's own cap. A `TrapCall`: the answer in intout, the A6 ap_find's `link`
    saves (its caller's, aes_dispatch's frame) and the image after. A run that never comes back raises `emu.run`'s
    RuntimeError."""
    image = make_image(_appl_find_staged(name, running() if machine is None else machine))
    entered = {"d0": addrs.GEM_SELECTOR_AES, "d1": PARAMETER_BLOCK_AT}
    _at_entry, _writes, registers = emu.run(image, addrs.GEM_TRAP2_AES_ON_UDA, dict(entered), stop_pc=addrs.AES_ROM_AP_FIND)
    assert registers["checkpoint"], "the trap's run never reached ap_find"
    final, _writes, returned = emu.run(image, addrs.GEM_TRAP2_AES_ON_UDA, dict(entered), stop_pc=addrs.GEM_TRAP2_AES_BACK)
    assert returned["checkpoint"], "the trap's run ended elsewhere than back from aes_entry"
    return TrapCall(aes.signed(case.word_in(final, INTOUT_AT)), registers["a6"], final)


# ---- psetup's SR: the one word of these routines that differs by nature ------------------------------------------------
# psetup parks the status register in its own save word round its stores (`move.w sr,$8998`): the caller's condition
# codes, whatever instruction ran last — another's for any C caller, and nothing a host core can store. Dropped by
# name (`aes_event.SR_DROPS`, the one table), only where the ROM's run stores it — so by every case of this module,
# whichever routine it runs: which ones reach psetup's bracket is the ROM's run's to say, not a list's. A priced row
# stages the word at the value the run leaves and takes its companion with nothing dropped (`register`), as every row
# does for the Line-F mask word.
DROPS = aes.LINE_F_MASK_WINDOW + aes_event.SR_PSETUP_DROP


# ---- THE ATTRIBUTION PASS, and the cases it STEERS ----------------------------------------------------------------------
# `aes.run_function`'s `steered=` (which says what the opt-out is, and how a reason is HELD: the pass narrowed to it).
# The reasons of these routines and of the lists' (`aes_evasync`), each naming THE WORDS THAT STEER — a case names
# every one its run meets, the one it meets FIRST first.
def _words(*fields, of, size):
    return tuple((record + field, record + field + size) for record in of for field in fields)


UDAS = (aes.AES_THEGLO, aes.AES_UDA1, aes.AES_UDA2)
STEERS_THE_STACK = aes.steers(
    "the stack pointer a PD's UDA saved, which psetup pushes its frame through and stores back: inverted it is ODD — "
    "the 68000's address error, refused by the host's accessors",
    *_words(aes.UDA_SUPER_SP, of=UDAS, size=aes.LONG_BYTES))
STEERS_THE_PD_COUNT = aes.steers(
    "the count of static PDs handed out (and of accessories), which getpd indexes the PD table by and stores back "
    "counted on: inverted it is NEGATIVE — the 'PD' getpd then numbers, marks and hands on lies below the table",
    (aes.AES_STATIC_PIDS, aes.AES_STATIC_PIDS + aes.WORD_BYTES),
    (aes.AES_ACCESSORY_COUNT, aes.AES_ACCESSORY_COUNT + aes.WORD_BYTES))
STEERS_THE_INDEX = aes.steers(
    "a pipe's index, which doq adds to the pipe's address for the bytes it moves: inverted it is ODD (a write reads "
    "its message's type back at an odd address: the address error again) and negative (a read's `what is left` is "
    "then 64 KB moved: the ROM's run does not return)",
    *_words(aes.PD_QUEUE_INDEX, of=STATIC_PDS, size=aes.WORD_BYTES))
# ...and the two an OVERLAP case adds, whose run stores over what it was handed: the pipe's own pointer (a write at a
# negative index, a read into the PD's own fields), the QPB the case stages (a read whose buffer IS the QPB).
STEERS_THE_QUEUE_POINTER = aes.steers(
    "a PD's pointer to its pipe, which doq moves the bytes through: the case's own copy lands on it, and inverted it "
    "is an address outside the machine",
    *_words(aes.PD_QUEUE_ADDRESS, of=STATIC_PDS, size=aes.LONG_BYTES))
STEERS_THE_QPB = aes.steers(
    "the QPB the case hands in, which its own copy lands on: its count and its buffer, inverted, are another call's "
    "— a negative count, a buffer outside the machine",
    (QPB_AT, QPB_AT + QPB.size))
# EVERY LINK OF EVERY LIST the scheduler keeps: an EVB's three, a PD's own and its three lists' heads, a CDA's three
# wait lists' heads (its keyboard's, its mouse's, its buttons': the longwords between its first word and its key
# queue), the screen lock's waiters, and the lists' own heads.
CDA_WAIT_LISTS = (aes.WORD_BYTES, aes.header_constants("fmlib.h")["CDA_KEY_QUEUE"])
EVBS = aes_event.EVBS
CDAS = tuple(aes.AES_CDA_TABLE + index * aes.CDA_BYTES for index in range(aes.AES_PD_COUNT))
LIST_HEADS = (aes.AES_RLR, aes.AES_NRL, aes.AES_DRL, aes.AES_EUL, aes.AES_ZOMBIE_LIST,
              aes.header_constants("evasync.h")["AES_DELAY_LIST"],
              aes.header_constants("wmupdate.h")["AES_WIND_SPB"] + aes.header_constants("wmupdate.h")["SPB_WAIT"])
STEERS_THE_LISTS = aes.steers(
    "the lists' links — an EVB's, a PD's, a wait list's or a scheduler list's head — which signal, azombie, evinsert, "
    "takeoff, apret and acancel read and store THROUGH: an inverted link is ODD (the address error again) or an "
    "address outside the machine (a read of the I/O page no model serves)",
    *_words(aes.EVB_NEXT, aes.EVB_LINK, aes.EVB_PRED, of=EVBS, size=aes.LONG_BYTES),
    *_words(aes.PD_LINK, aes.PD_EVLIST, aes.PD_QUEUE_READERS, aes.PD_QUEUE_WRITERS, of=STATIC_PDS, size=aes.LONG_BYTES),
    *((cda + CDA_WAIT_LISTS[0], cda + CDA_WAIT_LISTS[1]) for cda in CDAS),
    *((head, head + aes.LONG_BYTES) for head in LIST_HEADS))


def run(name, arguments, machine, **kwargs):
    """The guarded differential (`aes_event.run_core_guarded`: every run of the C first in a fork) of one of these
    routines over `machine` — one of this module's, its running process the scheduler's own (never
    `aes.leaf_machine`'s lever, which would put PD0 over the screen manager where it runs) — psetup's SR save word
    dropped where the ROM's run stores it. `steered=`: why THIS case runs without the kit's attribution pass (the
    reasons above); without it, it runs with it."""
    kwargs.setdefault("dropped_windows", DROPS)
    return aes_event.run_core_guarded(name, arguments, machine, **kwargs)


def _in_a_fork(name, arguments, machine, **asked):
    return aes_event.core_in_a_fork(name, arguments, machine, **asked)


def refused(name, arguments, machine):
    """The host core of `name` over `machine` in a FORK (`aes_event.core_in_a_fork`: these cores reach no hook),
    where a halt by name ends the fork and not the suite: `(returncode, stderr)`. A core still running after the
    fork's alarm (`aes_event.CORE_RETURN_SECONDS`) is ended by it: a loop that does not end FAILS its case rather
    than hanging the suite."""
    said = _in_a_fork(name, arguments, machine)
    return said.returncode, said.stderr


def refused_leaving(name, arguments, machine):
    """...and the image as the core left it, every store it made before a halt in it: `(returncode, stderr, image)`."""
    said = _in_a_fork(name, arguments, machine, read_back=True)
    return said.returncode, said.stderr, said.image


def answered(name, arguments, machine):
    """...and a core that is expected to RETURN there: `(returncode, stderr, its answer as a signed word)` — None for
    one that halted."""
    said = _in_a_fork(name, arguments, machine, answered=True)
    return said.returncode, said.stderr, None if said.answer is None else aes.signed(said.answer)


def register(label, name, arguments, machine, *, through_line_f=False):
    """One row of `name` (`aes_event.register_row`): priced direct, verified through its call word. A row whose ROM
    run stores psetup's SR save word — WHICH ROWS REACH THE BRACKET IS EACH ROW'S OWN RUN'S TO SAY, never a routine's
    first row's for the rest — stages it at the value the run leaves, drops it at Tier 3 beside the mask word where
    the run stores that too, and takes the companion that drops neither."""
    return aes_event.register_row(label, name, arguments, dict(machine), through_line_f=through_line_f)


# ---- pipes, as the ROM's own ap_rdwr leaves them ----------------------------------------------------------------------
def _ap_rdwr(machine, code, pid, count, buffer):
    """`machine` continued by the ROM's ap_rdwr(code, pid, count, buffer) — which may not reach the dispatcher
    (`aes_event.derived`: a write with room, a read with data)."""
    frame = aes_event.AP_RDWR_FRAME.pack(code, pid, count, buffer)
    written, _final, _regs = aes_event.derived(addrs.AES_ROM_AP_RDWR, machine, frame=frame)
    return merge_pokes(machine, written)


def sent(machine, to, *messages):
    """`machine` after its running process wrote each of `messages` (bytes) into process `to`'s pipe: the ROM's own
    ap_rdwr(WRITE), once a message."""
    for sending in messages:
        machine = _ap_rdwr(merge_pokes(machine, {MESSAGE_AT: sending}), AP_RDWR_WRITE, to, len(sending), MESSAGE_AT)
    return machine


NUMBERED_WORD = 0x100                  # a numbered message's third word: its type, a bit set above it


def numbered(count, first=1):
    """`count` messages no two of which merge: types from `first` up, each one's words made of its type."""
    return [message(type_, type_, -type_, NUMBERED_WORD + type_) for type_ in range(first, first + count)]


@functools.cache
def running():
    """PD0 running (`aes_event.machine`), the band's read buffer STALE."""
    return aes_event.machine(onto=STALE_BUFFER)


@functools.cache
def screen_manager_running():
    """PD1 running, PD0 parked in the desk's evnt_multi — waiting, among the rest, to READ its pipe."""
    return aes_event.machine(aes_event.screen_manager_running, onto=STALE_BUFFER)


@functools.cache
def holding(count, first=1):
    """PD0 running with `count` numbered messages in its own pipe."""
    return sent(running(), SHELL_PID, *numbered(count, first))


# ---- an EVB as aqueue is handed one ----------------------------------------------------------------------------------------
AtAqueue = namedtuple("AtAqueue", "machine writing evb qpb")
# iasync at its call of aqueue ($fe4154 / $fe4160): the EVB in its A5, the QPB's address in its D7, and the frame it
# pushed below its three saved registers (`link a6,#0; movem.l d6-d7/a5,-(sp)`) — the QPB, the EVB, the writing WORD.
IASYNC_SAVED_BYTES = 3 * aes.LONG_BYTES
IASYNC_WRITING_WORD = -(IASYNC_SAVED_BYTES + aes.LONG_BYTES + aes.WORD_BYTES)


def _handed_by_iasync(final, registers):
    """What iasync hands aqueue in a ROM run stopped at aqueue's entry: `(writing, evb, qpb)`, read off iasync's own
    registers and frame."""
    writing = aes.signed(case.word_in(final, registers["a6"] + IASYNC_WRITING_WORD))
    assert case.long_in(final, registers["a6"] + IASYNC_WRITING_WORD + aes.WORD_BYTES) == registers["a5"], (
        "iasync's frame does not hold the EVB of its A5: the run was not stopped at its call of aqueue")
    return writing, registers["a5"], registers["d7"]


def at_aqueue(machine, code, pid, count, buffer):
    """The ROM's ap_rdwr(code, pid, count, buffer) over `machine`, stopped where iasync calls aqueue: the machine
    there, with the `writing` word and the EVB iasync hands aqueue — the EVB off the free list and on the running
    process's, its event bit taken — and a QPB: the ROM's own lies in ap_rdwr's frame, on the oracle's stack, so the
    same three fields are restaged at QPB_AT."""
    frame = aes_event.AP_RDWR_FRAME.pack(code, pid, count, buffer)
    start = dict(machine)
    final, writes, registers = aes_event.stopped_at(make_image(merge_pokes(start, {abi.FIRST_ARG: frame})),
                                                    addrs.AES_ROM_AP_RDWR, addrs.AES_ROM_AQUEUE)
    writing, evb, handed = _handed_by_iasync(final, registers)
    assert bytes(final[handed:handed + PDPIPE["QPB_BYTES"]]) == frame[aes.WORD_BYTES:], "iasync's D7 is not the QPB"
    there = merge_pokes(start, case.written_by(writes), qpb_pokes(pid, count, buffer))
    return AtAqueue(there, writing, evb, QPB_AT)


def at_aqueue_from_the_dispatcher(application, machine):
    """The dispatcher's own loop run over `machine` (nothing running) until `application` — entered there, vetted as
    it lies there first (`vet_the_application`) — reaches aqueue in the one call of its PROGRAM: the machine there,
    and what iasync hands aqueue, the QPB where the process's own frame holds it (its UDA's stack, the AES's own
    RAM)."""
    vet_the_application(application, make_image(machine))
    there, final, registers = aes_event.dispatched(machine, application.pd, addrs.AES_ROM_AQUEUE)
    return AtAqueue(there, *_handed_by_iasync(final, registers))


# ---- a writer waiting on a full pipe, its reader running ---------------------------------------------------------------------
BLOCKED_TYPE = 0x40                             # a type no numbered message of a full pipe has
BLOCKED_WRITE = numbered(1, first=BLOCKED_TYPE)[0]     # the write that no longer fits


def _blocked(machine, to, count, buffer):
    """`machine` continued by its running process's ap_rdwr(WRITE) of `count` bytes at `buffer` to process `to`,
    which PARKS it (the pipe has no room): its EVB on that pipe's writers' list. A delta."""
    return aes_event.parked(addrs.AES_ROM_AP_RDWR, aes_event.AP_RDWR_FRAME.pack(AP_RDWR_WRITE, to, count, buffer), machine)


def blocked_writing(machine, to, sending=BLOCKED_WRITE, at=MESSAGE_AT):
    """...of the bytes `sending`, staged at `at`."""
    return _blocked(merge_pokes(machine, {at: sending}), to, len(sending), at)


def the_desk_s_pipe_filled_by_the_manager():
    """THE SCREEN MANAGER running (the mouse on the menu bar), THE DESK'S PIPE FULL OF ITS WRITES — the ROM's own
    appl_writes (`sent`): the first handed straight to the desk's parked message wait (the desk woken, onto the woken
    list), eight more filling its pipe; numbered messages, which the desktop reads and ignores. The one builder of
    that machine, for every battery whose next write must block. A delta."""
    return sent(aes_event.screen_manager_running(), SHELL_PID, *numbered(1 + PIPE_MESSAGES))


def _manager_waiting_to_write(count, buffer, staged=None):
    """THE SCREEN MANAGER WAITING TO WRITE, PD0 RUNNING over its own FULL pipe. PD1 runs (the mouse on the menu bar),
    PD0 parked in the desk's evnt_multi: PD1's first write is handed straight to PD0's message wait (PD0 woken, onto
    the woken list), its next eight fill PD0's pipe, and its write of `count` more bytes at `buffer` does not fit —
    it PARKS (`aes_event.parked`), its EVB on the pipe's writers' list. The dispatcher's own loop then runs PD0, which
    comes out of the desk's evnt_multi with the first message (`aes_event.dispatched`). A delta."""
    machine = the_desk_s_pipe_filled_by_the_manager()
    parked = _blocked(merge_pokes(machine, staged), SHELL_PID, count, buffer)
    running, _final, _registers = aes_event.dispatched(parked, aes.SHELL_PD)
    return merge_pokes(running, STALE_BUFFER)


@functools.cache
def writer_waiting(sending=BLOCKED_WRITE, at=MESSAGE_AT):
    """...its write the bytes `sending`, staged at `at`: one message that no longer fits, by default."""
    return _manager_waiting_to_write(len(sending), at, {at: sending})


@functools.cache
def writer_waiting_to_write_its_own_evb(count):
    """...its write `count` bytes FROM THE EVENT BLOCK ITS WAIT WILL BE: the head of the free list as the write
    begins, which iasync takes for it — a caller's pointer like any other. `(the machine, the EVB)`."""
    machine = the_desk_s_pipe_filled_by_the_manager()
    evb = case.long_in(make_image(machine), aes.AES_EUL)
    return _manager_waiting_to_write(count, evb), evb


# ---- THE STAGED APPLICATION ----------------------------------------------------------------------------------------------------
STAGED_APPLICATION = "a staged application"            # the class's label: in the name of every case over one
JMP_ABSOLUTE_SHORT = b"\x4e\xf8"                        # jmp     <xxx>.w
STUB_INSTRUCTIONS = 3                                   # what the class allows: a push, one Line-F call, the way out
_PUSHES = {PUSH_WORD_IMMEDIATE: (">H", aes.WORD_MASK), PUSH_LONG_IMMEDIATE: (">I", aes.LONG_MASK)}
# WHICH call a stub may make, by name — the shape alone would admit any Line-F routine that takes one immediate, one
# that calls through a pointer it is handed among them. Each of these parks or returns on the scheduler's own state
# and takes nothing but its one argument, pushed at the WIDTH the routine reads it at (a word pushed for a long would
# still decode as "a push, a call, the way out"); a new one is added here, with its reason, by the wave that needs it.
Allowed = namedtuple("Allowed", "why push")
ALLOWED_CALLS = {
    "AES_ROM_EV_MESAG": Allowed("a wait for a message: its one long is the buffer", PUSH_LONG_IMMEDIATE),
    "AES_ROM_EV_TIMER": Allowed("a delay: its one long is the milliseconds", PUSH_LONG_IMMEDIATE),
    "AES_ROM_WM_UPDATE": Allowed("the screen's lock taken or given back: its one word is BEG_UPDATE / END_UPDATE",
                                 PUSH_WORD_IMMEDIATE),
}
_ALLOWED_TARGETS = {getattr(addrs, call): call for call in ALLOWED_CALLS}
Application = namedtuple("Application", "machine pd pid stub call argument stored")


def pushed(call, argument):
    """The push of `argument` a stub calling `addrs.<call>` makes: the instruction's word, then the immediate at the
    width ALLOWED_CALLS gives the routine's one argument."""
    push = ALLOWED_CALLS[call].push
    packed, mask = _PUSHES[push]
    return push + struct.pack(packed, argument & mask)


def stub(call, argument):
    """The staged application's WHOLE PROGRAM, three instructions: `move.w` or `move.l #argument,-(sp)` (`pushed`: the
    width is the call's); the ROM's own Line-F call word of `addrs.<call>` — one of ALLOWED_CALLS; `jmp (SENTINEL).w`
    — where the oracle's run ends, should the call return. `jmp` and not `pea; rts`: it writes nothing onto the
    process's stack."""
    program = (pushed(call, argument) + struct.pack(">H", aes.line_f_call_word(call)) + JMP_ABSOLUTE_SHORT
               + struct.pack(">H", emu.SENTINEL))
    vet_the_stub(program)
    return program


def _decoded(program):
    """`program`'s instructions in order, as the class reads them: `(kind, operand, the bytes it takes)` — refused by
    name at the first word that is none of the three the class allows."""
    at = 0
    while at < len(program):
        opcode = bytes(program[at:at + aes.WORD_BYTES])
        word = int.from_bytes(opcode, "big")
        if opcode in _PUSHES:
            size = aes.WORD_BYTES + struct.calcsize(_PUSHES[opcode][0])
            found = ("push", bytes(program[at + aes.WORD_BYTES:at + size]), size)
        elif aes.line_f_target(word) is not None:
            found = ("call", aes.line_f_target(word), aes.WORD_BYTES)
        elif opcode == JMP_ABSOLUTE_SHORT:
            found = ("leave", case.word_in(program, at + aes.WORD_BYTES), 2 * aes.WORD_BYTES)
        else:
            assert word & ~aes.LINEF_OFFSET_MASK != LINE_F, (
                f"a staged application's stub holds the Line-F word {word:#06x} at +{at}: a return, not a call")
            raise AssertionError(f"a staged application's stub holds {word:#06x} at +{at}: not a push of an "
                                 f"immediate, a Line-F call or the jump out")
        yield found
        at += found[-1]


def stub_instructions(program):
    """`program` split into the instructions the class allows, in order: `[("push", bytes), ("call", routine),
    ("leave", address)]` — refused by name at the first byte that is none of them."""
    return [(kind, operand) for kind, operand, _size in _decoded(program)]


def vet_the_stub(program):
    """A staged application's program is EXACTLY what the class allows: three instructions — one push of an immediate,
    ONE Line-F call of a routine ALLOWED_CALLS names, the jump to the oracle's sentinel — and nothing else. Refused
    by name otherwise."""
    instructions = stub_instructions(program)
    kinds = [kind for kind, _operand in instructions]
    assert kinds == ["push", "call", "leave"], (
        f"a staged application's stub is {kinds or 'empty'}: the class allows a push, one Line-F call and the jump "
        f"out — {STUB_INSTRUCTIONS} instructions, in that order")
    (_push, immediate), (_call, routine), (_leave, leaves_for) = instructions
    assert routine in _ALLOWED_TARGETS, (
        f"a staged application's stub calls {routine:#x}, which the class does not name: it allows "
        f"{', '.join(sorted(ALLOWED_CALLS))} (`ALLOWED_CALLS`, each with its reason)")
    width = struct.calcsize(_PUSHES[ALLOWED_CALLS[_ALLOWED_TARGETS[routine]].push][0])
    assert len(immediate) == width, (
        f"a staged application's stub pushes {len(immediate)} bytes for {_ALLOWED_TARGETS[routine]}, whose one argument "
        f"is {width} (`ALLOWED_CALLS`)")
    assert leaves_for == emu.SENTINEL, "a staged application's stub leaves for another address"
    assert len(program) <= STUB_BYTES, "a staged application's stub does not fit its band"


def laid_stub(image, at=STUB_AT):
    """The program a machine holds at `at`, AS IT LIES THERE: its instructions up to and including the first jump
    out, and the rest of the stub's room, which must be the band's zeroes — refused by name where no jump out ends
    it. What `vet_the_stub` is handed at every USE of an application (`_vet_the_application`)."""
    room = bytes(image[at:at + STUB_BYTES])
    size = 0
    for kind, _operand, bytes_taken in _decoded(room):
        size += bytes_taken
        if kind == "leave":
            break
    else:
        raise AssertionError("a staged application's stub never leaves: no jump out in its room")
    assert not any(room[size:]), "a staged application's stub is followed by bytes that are not the band's zeroes"
    return room[:size]


def vet_the_application(application, image):
    """`application`, about to be ENTERED over `image` — by ANY road that runs the dispatcher into its stub (`started`,
    `called`, `at_aqueue_from_the_dispatcher`, a scenario's own watched run): the program lying at its stub is the
    class's (`vet_the_stub` of `laid_stub`), makes the call the application names and pushes the argument it names,
    at that call's width — a machine forged after its making is refused here."""
    program = laid_stub(image, application.stub)
    vet_the_stub(program)
    (_push, immediate), made_call, _leave = stub_instructions(program)
    assert made_call == ("call", getattr(addrs, application.call)), (
        f"a staged application's stub does not make the call its application names ({application.call})")
    assert immediate == pushed(application.call, application.argument)[aes.WORD_BYTES:], (
        f"a staged application's stub does not push the argument its application names ({application.argument:#x}): it "
        f"pushes {immediate.hex()}")


def staged_application(call, argument, name=b"STAGED", onto=None):
    """A THIRD PROCESS (`STAGED_APPLICATION`): the ROM's own pstart(stub, name, 0), run by the process running in
    `onto` (`aes_event.machine()`, PD0, when None) over the stub of `stub(call, argument)`. Answers an
    `Application`: the machine pstart leaves — the spare static PD named, numbered 2, its UDA's stack holding the
    frame psetup pushed (the stub's address under SR $2000), READY on the woken list, not yet run — with its PD, its
    id, its stub's address, and `stored`: every byte pstart's own run wrote (its ledger, the stack band out), which
    is ALL the machine differs by from the one it started from."""
    program = stub(call, argument)
    start = merge_pokes(aes_event.machine() if onto is None else onto, {STUB_AT: program.ljust(STUB_BYTES, b"\0")},
                        name_pokes(name, APPLICATION_NAME_AT))
    frame = aes_event.frame_of(("l", STUB_AT), ("l", APPLICATION_NAME_AT), ("l", 0))
    written, final, registers = aes_event.derived(addrs.AES_ROM_PSTART, start, frame=frame)
    pd = registers["d0"]
    assert pd == SPARE_PD, f"pstart made the PD at {pd:#x}, not the spare static one"
    assert aes.list_of(final, aes.AES_DRL)[0] == pd and case.word_in(final, pd + aes.PD_PID) == APPLICATION_PID
    return Application(merge_pokes(start, written), pd, APPLICATION_PID, STUB_AT, call, argument, written)


def _maker_parked(application):
    """`application`'s machine with the process that made it (PD0) PARKED in an ev_multi waiting for a key
    (`aes_event.parked`): nothing running, the application on the woken list — where the dispatcher's loop begins.
    The application vetted as it lies there (`vet_the_application`)."""
    parked = aes_event.parked(addrs.AES_ROM_EV_MULTI, aes_event.KEY_WAIT, application.machine)
    vet_the_application(application, make_image(parked))
    return parked


def started(application):
    """`application` ENTERED by the dispatcher: the process that made it parks waiting for a key (`_maker_parked`),
    and the dispatcher's own loop — idle moving the application off the woken list, switchto popping psetup's frame —
    is run until the stub's first instruction (`aes_event.dispatched`). The machine there: the application RUNNING,
    alone on the ready list, nothing of its program run. A delta."""
    running, _final, _registers = aes_event.dispatched(_maker_parked(application), application.pd, application.stub)
    return running


def called(application):
    """THE SAME RUN, CARRIED ON: the dispatcher's own loop over `_maker_parked(application)`, through the entry of the
    application at its stub (where `started` stops) and on — the stub's push and its one Line-F call, on the stack
    and with the registers switchto's `rte` left — until that call has PARKED the application and the loop begins
    AGAIN: nothing running, the application waiting on what its program asked for. One run of the ROM, never
    re-entered from the harness; refused by name where the call returns instead. A delta."""
    memory = make_image(_maker_parked(application))
    watch = aes_event.EntryStops((), None, ends={addrs.AES_ROM_DISP_LOOP}, once_past=application.stub)
    try:
        aes_event.run_watched(memory, addrs.AES_ROM_DISP_LOOP, watch)
    except aes_event.Ended:
        assert application.pd not in aes.list_of(memory, aes.AES_RLR), "the application's call left it ready"
        return aes_event.as_pokes(memory, without=case.STACK_BAND, upto=addrs.ST_RAM_BYTES)
    raise AssertionError(f"the application's call of {application.call} returned: it did not park")


def resumed(machine):
    """`machine` — the process that made the application still parked on the key wait `started` left it in — with
    Return typed and the dispatcher's own loop run until that process comes out of its ev_multi: PD0 running again,
    whatever the application waits for still waited for. A delta."""
    running, _final, _registers = aes_event.dispatched(aes_event.typed_ahead(machine, aes_event.RETURN_KEY), aes.SHELL_PD)
    return running


def woken_screen_manager(machine):
    """`machine` (nothing running) with the mouse moved onto the menu bar and the dispatcher's own loop run until the
    SCREEN MANAGER comes out of its evnt_multi with it — FIRST on the ready list, not alone on it: another process is
    ready too (a staged application not yet entered). A delta."""
    moved = aes_event.mouse_moved_to(*aes_event.MENU_BAR_POINT, machine)
    running, _final, _registers = aes_event.dispatched(moved, aes.SCREEN_MANAGER_PD, alone=False)
    return running
