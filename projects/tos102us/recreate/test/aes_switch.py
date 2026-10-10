"""THE PROCESS SWITCH'S SHAPES — what `src/aes/switch.S`, `src/aes/irq.S` and `src/aes/evdisp.c` are proved over
(`test_aes_switch*.py`, `test_aes_irq.py`, `test_aes_evdisp*.py`).

A context switch is the one thing of the AES no single routine's differential holds: its subject is the CPU's own
state — the registers, two stack pointers, the status register — stored in one process's UDA and loaded from
another's, on a stack the caller did not come in on. So this module is the shapes that hold it, each named for what
it compares and what it cannot:

  * THE STAGED CALLERS (V6). savestate and switchto are entered, on BOTH shores, by a caller staged in the machine
    that builds what dsptch and disp build — the `rte` frame, the pushed A0, disp's `link` — with ONE register file
    (`transcription.run_transcription`). So the UDA's context block IS compared there, byte for byte, the one place
    it can be: for a C caller it is the host's own CPU state.
  * THE CONTEXT DROPS (V4), `(lo, hi, why)` each and each only where the ROM's run stores it: a process's UDA
    context, the dispatcher's stack, the dispatcher's SR save word — for every run in which OUR side is C, or C under
    our disp's `jsr`s, where those bytes hold return addresses and frames of another build.
  * THE SCHEDULER DRIVER (V3): one run of the ROM through its own dispatcher, each interrupt of a case delivered at
    the n-th IDLE — where the machine waits for one.
  * THE HOST'S MODEL OF THE SWITCH, SWITCHED ON PER CASE: `scheduling(...)` binds the dispatcher's
    hook to the C scheduler (`aes_disp`) for one run, the idle hook to the case's deliveries and the process hook to
    a nested run of the ROM; every other run of the suite keeps the hook that refuses at dsptch.
  * THE GLUE, entered as the ROM's own interrupt code enters it — and THE GLUE THE BUILD INSTALLS: the two code
    addresses gsx_setmb hands the VDI, and the longwords of the machine that then hold one.
  * THE STACKS: how deep a blob's own code can take the dispatcher's 640 bytes and the glue's private stacks, READ
    OFF THE BUILD (every path of its listing), the runs that hold that reading to the truth, and what the ROM's own
    interrupt handlers need on top.
"""
import ctypes
import functools
import mmap
import re
import struct
import subprocess
import sys
import types
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, _lib, addrs, bench_tier3, emu, make_image
from recreate_kit import rom_bench

import abi
import aes
import aes_event
import case
import derived
import isr
import rom_data
import transcription
import vdi
import vdi_helpers
from address_hook import answered_or_recorded, as_the_case_s_outcome, bind_pointer, raise_what_stops_the_session
from case import merge_pokes
from opcodes import (DROP_STACK_BYTES, DROP_STACK_LONG, JSR_ABSOLUTE_LONG, PUSH_ADDRESS_SHORT, PUSH_RETURN_PC, PUSH_SR,
                     PUSH_STACK_LONG, RTE, RTS)

LONG_BYTES, WORD_BYTES = aes.LONG_BYTES, aes.WORD_BYTES
EVDISP, CTRL = aes.header_constants("evdisp.h"), aes.header_constants("ctrl.h")
AES_CT_MOUSE_SHOWN, CT_MOUSE_GRAB = CTRL["AES_CT_MOUSE_SHOWN"], CTRL["CT_MOUSE_GRAB"]

DSPTCH, DISP = "AES_ROM_DSPTCH", "AES_ROM_DISP"
SPL7_SAVE, SPL_RESTORE, CLI, STI = "AES_ROM_SPL7_SAVE", "AES_ROM_SPL_RESTORE", "AES_ROM_CLI", "AES_ROM_STI"
GOTOPGM, SAVESTATE, SWITCHTO = "AES_ROM_GOTOPGM", "AES_ROM_SAVESTATE", "AES_ROM_SWITCHTO"

# The fork functions' entries in our build, by the ROM address each stands for (`aes/evfork.h`): what a queue entry's
# code is on each shore — the one map Tier 3's relocation of a ROM-made queue and its vets share.
FORK_ENTRY_SYMBOLS = aes_event.FORK_ENTRY_SYMBOLS

# THE TWO BLOBS a build is held on, by the directory each is built in (None: the bench blob's own): the one Tier 3
# prices plain C on, and the shipped configuration's — every pin and differential of the switch's batteries runs on both.
BLOBS = isr.BLOBS

# ---- THE STAGED CALLERS (V6) ----------------------------------------------------------------------------------------------
# Both shores enter a caller at the run's own stack top, the sentinel under SP, the routine's longword at
# `abi.FIRST_ARG` (the ROM's entry on one shore, the blob's on the other: `transcription`) and the UDA's address in
# the longword above it. The routine's address is never loaded into a register: savestate stores every one of them.
BAND_OFFSET = 0x2500                    # past test/aes_fslib.py's replay band (+$2000), below aes_pdpipe.py's (+$3400)
BAND_BYTES = 0x100
BAND_AT = aes.SPAN.claim(aes.WINDOW_AT + BAND_OFFSET, BAND_BYTES,
                         "test/aes_switch.py: the switch's staged callers, a basepage and its program")
CALLER_STRIDE = 0x20
CALLERS_BYTES = 4 * CALLER_STRIDE
POOL = transcription.CallerPool(BAND_AT, BAND_AT + CALLERS_BYTES, CALLER_STRIDE, grow="aes_switch.CALLERS_BYTES")
BASEPAGE_AT = BAND_AT + CALLERS_BYTES                  # gotopgm's: a basepage of which only p_tbase is read
BASEPAGE_BYTES_STAGED = 0x10                           # p_lowtpa, p_hitpa, p_tbase: as far as gotopgm reads
assert addrs.BASEPAGE_TBASE + LONG_BYTES <= BASEPAGE_BYTES_STAGED
PROGRAM_AT = BASEPAGE_AT + BASEPAGE_BYTES_STAGED       # ...and the program it names: one instruction
assert PROGRAM_AT + 2 * WORD_BYTES <= BAND_AT + BAND_BYTES
UDA_ARGUMENT_AT = abi.FIRST_ARG + LONG_BYTES           # above the routine longword a caller jumps through

PUSH_A0 = b"\x2f\x08"                                  # move.l  a0,-(sp)
LINK_A6 = b"\x4e\x56"                                  # link    a6,#<d16>
STORE_STACK_LONG_AT_SP = b"\x2e\xaf"                   # move.l  <d16>(sp),(sp)
LOWER_STACK = DROP_STACK_BYTES                         # lea     <d16>(sp),sp, here with a negative displacement
JMP_ABSOLUTE_SHORT = b"\x4e\xf8"                       # jmp     <xxx>.w
JMP_ABSOLUTE_LONG = b"\x4e\xf9"                        # jmp     <xxx>.l
END_THE_RUN = JMP_ABSOLUTE_SHORT + struct.pack(">H", emu.SENTINEL)
DISP_LOCAL_BYTES = 4                                   # disp's `link a6,#-4`: the argument slot its calls share ($fe4d9e)


def _from_sp(pushed, entry_offset):
    """The displacement, from SP once `pushed` bytes lie under the entry's, of what was `entry_offset` above it."""
    return struct.pack(">h", pushed + entry_offset)


def savestate_caller_stub():
    """savestate entered as disp enters it, for the process whose UDA the case names: the `rte` frame dsptch builds
    out of the return address (here the run's sentinel: the PC the process would resume at), dsptch's pushed A0,
    disp's `link` and its argument slot — then the routine, by a pushed address; and where savestate comes back to
    (on the dispatcher's stack, the frame pointer disp's) the run is ENDED: nothing lies on that stack to return by."""
    routine, uda = abi.FIRST_ARG - emu.STACK_TOP, UDA_ARGUMENT_AT - emu.STACK_TOP
    frame = WORD_BYTES + LONG_BYTES + LONG_BYTES + DISP_LOCAL_BYTES     # SR, A0, the saved A6, the slot
    back = len(PUSH_STACK_LONG) + WORD_BYTES + len(RTS) + WORD_BYTES    # from the `pea`'s extension word
    stub = (PUSH_SR + PUSH_A0 + LINK_A6 + struct.pack(">h", -DISP_LOCAL_BYTES)
            + STORE_STACK_LONG_AT_SP + _from_sp(frame, uda)
            + PUSH_RETURN_PC + struct.pack(">h", back)
            + PUSH_STACK_LONG + _from_sp(frame + LONG_BYTES, routine) + RTS
            + END_THE_RUN)
    return stub, SAVESTATE_CALLER_COST


def switchto_caller_stub():
    """switchto entered as disp enters it: a return address it never uses, the UDA above it — BELOW the frame the
    UDA's supervisor stack pointer names (the machine's: savestate's own caller laid it just under the run's stack
    top), which the pushes must not reach."""
    routine, uda = abi.FIRST_ARG - emu.STACK_TOP, UDA_ARGUMENT_AT - emu.STACK_TOP
    stub = (LOWER_STACK + struct.pack(">h", -CLEAR_OF_THE_FRAME)
            + PUSH_STACK_LONG + _from_sp(CLEAR_OF_THE_FRAME, uda)
            + PUSH_RETURN_PC + struct.pack(">h", len(PUSH_STACK_LONG) + WORD_BYTES + len(RTS) + WORD_BYTES)
            + PUSH_STACK_LONG + _from_sp(CLEAR_OF_THE_FRAME + 2 * LONG_BYTES, routine) + RTS)
    return stub, SWITCHTO_CALLER_COST


# What each caller costs (`transcription.assert_caller_cost` measures every registered caller against it): savestate's
# eight instructions, switchto's five — and the stand-in switchto's is measured over, which drops what the caller
# pushed and returns to the sentinel as switchto's `rte` does.
SAVESTATE_CALLER_COST = (8, 132)
SWITCHTO_CALLER_COST = (5, 88)
CLEAR_OF_THE_FRAME = 16                 # how far the caller lowers SP: past the frame and what savestate's caller pushed
SWITCHTO_STAND_IN = LOWER_STACK + struct.pack(">h", CLEAR_OF_THE_FRAME + 2 * LONG_BYTES) + RTS
SWITCHTO_STAND_IN_COST = (2, 24)
SAVESTATE_CALLER = POOL.staged("savestate", savestate_caller_stub)
SWITCHTO_CALLER = POOL.staged("switchto", switchto_caller_stub, routine=SWITCHTO_STAND_IN,
                              routine_cost=SWITCHTO_STAND_IN_COST)
# ...where savestate's caller leaves the frame the UDA then names: the SR's word under the run's stack top, the PC
# the sentinel the run was entered with.
PARKED_FRAME_AT = emu.STACK_TOP - WORD_BYTES

SwitchCase = namedtuple("SwitchCase", "caller pokes")


def entered_with_a_uda(caller, uda, pokes):
    """`pokes` with `uda` where the switch's callers read it."""
    return SwitchCase(caller, merge_pokes(pokes, {UDA_ARGUMENT_AT: struct.pack(">I", uda)}))


# ---- THE INTERRUPTS' GLUE (`src/aes/irq.S`), entered as the VDI's interrupt code enters it ----------------------------------
# A glue has a REGISTER contract (D0, D1: the buttons, or the mouse's point) and runs on a private stack that lies in
# compared RAM, so neither Tier 3 relation enters it: the C relation hands no register, and the transcription relation
# drops nothing — while two things differ here BY NATURE between the ROM's glue and ours: the frames on the private
# stack (the ROM's Alcyon frames and Line-F exception frames, our thunk's and GCC's) and the CODE a forkq under it
# queues (the fork function's ROM address, our build's own entry). So this is a differential of its own: the ROM's
# glue and a blob's entered over ONE machine with ONE register file — the machine and the registers an ARRIVAL of the
# ROM's own interrupt code at the glue (`glue_arrival`), or the tick's own entry — and held equal everywhere else.
GLUE_STACK_TOP, TICK_STACK_TOP = EVDISP["AES_GLUE_STACK_TOP"], EVDISP["AES_TICK_STACK_TOP"]
# What each private stack may grow down to: the tick's, the other glue's stack top; the button and motion glue's, the
# last global the ROM names beneath it (the tick's countdown, a longword).
GLUE_STACK_BOTTOM = aes.AES_TIMER_COUNTDOWN + LONG_BYTES
Glue = namedtuple("Glue", "symbol rom stack")
BUTTON_GLUE = Glue("aes_rom_button_glue", addrs.AES_ROM_BUTTON_GLUE, (GLUE_STACK_BOTTOM, GLUE_STACK_TOP))
MOTION_GLUE = Glue("aes_rom_motion_glue", addrs.AES_ROM_MOTION_GLUE, (GLUE_STACK_BOTTOM, GLUE_STACK_TOP))
TICK_GLUE = Glue("aes_rom_tick_glue", addrs.AES_ROM_TICK_GLUE, (GLUE_STACK_TOP, TICK_STACK_TOP))
GLUE_AT = {glue.rom: glue for glue in (BUTTON_GLUE, MOTION_GLUE, TICK_GLUE)}
# THE GLUE THE BUILD INSTALLS ITSELF and the longwords of the machine that hold one are the relocation registry's
# (`aes_event.GLUE_CODES`): Tier 3 relocates exactly these between the shores, and nothing is dropped.
GLUE_ENTRY_SYMBOLS, GLUE_CODE_SLOTS = aes_event.GLUE_ENTRY_SYMBOLS, aes_event.GLUE_CODE_SLOTS
assert GLUE_ENTRY_SYMBOLS == {BUTTON_GLUE.rom: BUTTON_GLUE.symbol, MOTION_GLUE.rom: MOTION_GLUE.symbol}
USER_BUT, USER_MOT = vdi.field("LINEA", "USER_BUT").at, vdi.field("LINEA", "USER_MOT").at
CUR_FLAG = vdi.field("LINEA", "CUR_FLAG").at            # byte: bit 0 = the cursor moved, the vertical blank's to redraw
PSG_MIXER, PSG_REGISTERS = 7, 16
GLUE_INSNS = 20_000                     # one glue's run: a tick that runs a click out is some 300
# What a glue owes its caller in registers: the button's and the motion's save D0-D2/A0-A2 round their call, so the
# whole file; the tick's saves nothing — the scratch its callees leave is whoever compiled them's.
EVERY_REGISTER = tuple(emu.REPORTED_REGS)
KEPT_BY_ANY_CALLEE = tuple(name for name in emu.REPORTED_REGS if name not in ("d0", "d1", "d2", "a0", "a1", "a2"))
GlueArrival = namedtuple("GlueArrival", "glue registers machine")
GlueRun = namedtuple("GlueRun", "memory registers wrote")


def glue_arrival(interrupt, machine):
    """THE ROM'S OWN CALL of a glue: `interrupt` (an `aes_event.Interrupt` — the VDI's mouse interrupt over a packet)
    run over `machine` until it reaches the button's or the motion's glue: the registers it is entered with and the
    machine there, the interrupt's own stack frames left out."""
    memory = make_image(machine)
    for at, data in (interrupt.inputs or {}).items():
        memory[at:at + len(data)] = data
    try:
        result = rom_bench.original_entered(memory, interrupt.entry, frozenset(GLUE_AT), interrupt.regs,
                                            max_insns=GLUE_INSNS)
        assert result["status"] == emu.BENCH_DOOR, f"the interrupt at {interrupt.entry:#x} called no glue"
        glue, registers = GLUE_AT[emu.bench_door_pc()], dict(result["regs"])
    finally:
        emu.bench_abort()
    return GlueArrival(glue, {name: registers[name] for name in emu.REPORTED_REGS},
                       aes_event.as_pokes(memory, without=case.STACK_BAND, upto=addrs.ST_RAM_BYTES))


def _glue_run(memory, entry, registers):
    emu.install_chip_seeds()
    try:
        result = emu.run_bench(memory, entry, 0, emu.STACK_TOP, emu.SENTINEL, max_insns=GLUE_INSNS,
                               seed_regs=rom_bench.entry_registers(registers))
        wrote, truncated = emu.bench_writes(memory)
    finally:
        emu.bench_abort()
    rom_bench.vet_the_run_just_made(f"the glue at {entry:#x}")
    assert result["status"] != emu.BENCH_DOOR and not truncated, f"the glue at {entry:#x} did not end, or overflowed the ledger"
    return GlueRun(memory, result["regs"], frozenset(wrote))


def glue_on_the_rom(arrival):
    """The ROM's glue entered as `arrival` has it — by `jsr`, on the run's stack: its memory, registers and stores."""
    return _glue_run(make_image(arrival.machine), arrival.glue.rom, arrival.registers)


def glue_on(blob, arrival):
    """...and `blob`'s, over the same machine with the same register file."""
    memory = make_image(arrival.machine)
    memory[blob.base:blob.base + len(blob.blob)] = blob.blob
    return _glue_run(memory, blob.entry(arrival.glue.symbol), arrival.registers)


def vet_the_glue(blob, arrival, kept=EVERY_REGISTER):
    """`blob`'s glue against the ROM's over `arrival`, both run and held (`vet_the_glue_s_runs`). Answers
    `(the ROM's run, ours)`."""
    the_rom_s, ours = glue_on_the_rom(arrival), glue_on(blob, arrival)
    vet_the_glue_s_runs(blob, arrival.glue, the_rom_s, ours, kept)
    return the_rom_s, ours


def vet_the_glue_s_runs(blob, glue, the_rom_s, ours, kept=EVERY_REGISTER):
    """OUR run of `glue` (`blob`'s) against THE ROM'S over one arrival: the registers `kept` and the whole image
    equal — outside the run's stack, the blob, and what differs BY NATURE, each held as what it is:
      * THE GLUE'S PRIVATE STACK, whole: another build's frames. Held instead: the ROM's run stored in it (the drop
        names something), and OURS STAYS INSIDE IT — below the stack's bottom, where the saved stack pointers and
        the tick's own counters lie, it stores at no address the ROM's run does not;
      * A QUEUED FORK FUNCTION'S CODE: where the ROM's run stored a queue entry's code, ours holds the entry of THE
        SAME fork function (`FORK_ENTRY_SYMBOLS`), and nowhere else may the queue differ;
      * THE LINE-F MASK WORD, where the ROM's run stored it (its Alcyon callees' masked returns: `aes.LINE_F_MASK_WHY`)."""
    lo, hi = glue.stack
    stack = frozenset(range(lo, hi))
    assert the_rom_s.wrote & stack, f"{glue.symbol}: the ROM's run stored nothing on its private stack"
    assert ours.wrote & stack, f"{glue.symbol}: our run stored nothing on its private stack — it ran on another"
    spilt = sorted(at for at in ours.wrote - the_rom_s.wrote if lo - (hi - lo) <= at < lo)
    assert not spilt, (f"{glue.symbol}: our run stored BELOW its private stack's bottom ({lo:#x}), from "
                       f"{spilt[0]:#x}, where the ROM's run stores nothing: the frames of our build's C do not fit the "
                       f"{hi - lo} bytes the ROM's fit in")
    differing_registers = {name: (the_rom_s.registers[name], ours.registers[name]) for name in kept
                           if the_rom_s.registers[name] != ours.registers[name]}
    assert not differing_registers, f"{glue.symbol}: registers (the ROM's, ours) {differing_registers}"
    codes = frozenset(at + offset for at in aes_event.FORK_CODE_SLOTS if at in the_rom_s.wrote
                      for offset in range(LONG_BYTES))
    for at in sorted(codes)[::LONG_BYTES]:
        queued = case.long_in(the_rom_s.memory, at)
        assert case.long_in(ours.memory, at) == blob.entry(FORK_ENTRY_SYMBOLS[queued]), (
            f"{glue.symbol}: the ROM queued the fork function at {queued:#x}; ours queued "
            f"{case.long_in(ours.memory, at):#x}, not its own entry of that function")
    mask_word = aes_event.LINE_F_MASK_BYTES & the_rom_s.wrote
    not_compared = frozenset(case.STACK_BAND) | stack | codes | mask_word | frozenset(range(blob.base, blob.end))
    differ = aes_event.differing(ours.memory, the_rom_s.memory, not_compared)
    assert not differ, (f"{glue.symbol}: memory differs at "
                        f"{[f'{at:#x}' for at in differ[:aes_event.COMPARED_DIFFERENCES_SHOWN]]}")


def deepest_on(run, stack):
    """How many bytes of `stack` (`(bottom, top)`) `run` used: from its lowest store there to the top."""
    lo, hi = stack
    return hi - min(at for at in run.wrote if lo <= at < hi)


# ---- THE STACKS, STATICALLY: how deep a blob's own code can go below an entry ----------------------------------------------
# The dispatcher's stack is 640 bytes and the glue's two are 92 and 96: what our build's frames may use of each is a
# property of THE BUILD, not of the cases that happen to run — so it is READ OFF THE BLOB'S LISTING: every
# instruction of every function reachable from an entry, each one's effect on the stack pointer followed down every
# branch, each call's callee added under the depth at its site. The reading REFUSES what it cannot follow, each
# shape by name — a bound is no bound if a shape was skipped:
#   * an instruction that sets SP it does not know; two paths that meet at different depths; recursion;
#   * A CALL THROUGH A POINTER (`jsr (a1)`) whose routine is not one this function names BY VALUE: a pointer read
#     out of the machine (mchange's cursor routine, out of AES_DRWADDR; forker's fork function, out of the queue) or
#     handed in as an argument. Such a call is DECLARED by its caller (`through_a_pointer`: what the machine's
#     pointer can hold) or refused — the callees a function names by value are not what a pointer of the machine
#     holds;
#   * a call through a register NOTHING is known to load (no candidate at all);
#   * A TRAP OTHER THAN `trap #2` (GEMDOS, the BIOS, the XBIOS): the OS's own frames under it are counted nowhere;
#   * A PATH THAT RUNS OFF A LISTED BODY'S LAST INSTRUCTION where an `rts` or a jump was expected.
# What it reads is how far SP GOES — an allocation counts whether or not a store reaches its last byte, as an
# interrupt taken there would land below it.
#   * a `jsr`/`bsr` by name is that callee, four bytes deeper (the return address); a `jmp` by name its tail;
#   * a call THROUGH A REGISTER GCC LOADED BY VALUE (it keeps a function it calls twice in a register, or spills its
#     address to a frame slot) is the functions that register can hold: read off the loads themselves;
#   * `trap #2` is the OS's, not the blob's: the deepest SP a trap is taken at is answered beside the bound, for
#     whoever knows what the trap handler needs under it (`trap_need_under`, measured);
#   * a glue's `lea <its stack top>,sp` starts the count again (the private stack), and its `movea.l <saved>,sp`
#     ends it (the interrupted stack back: what follows is not on the private one).
_LISTED_LABEL = transcription.LISTED_FUNCTION
_LISTED_LINE = re.compile(r"^\s*([0-9a-f]+):\t[0-9a-f ]+\t(.+)$")
_NAMED_TARGET = re.compile(r"\b([0-9a-f]+) <([\w.]+)(?:\+0x[0-9a-f]+)?>\)?$")
_TRANSFER = re.compile(r"^(jmp|jsr|bsr[swl]?|bra[swl]?|b(?:hi|ls|cc|cs|ne|eq|vc|vs|pl|mi|ge|lt|gt|le)[swl]?|db\w+)$")
_ENDS_A_PATH = ("rts", "rte", "rtr")
_SP_BY_A_CONSTANT = re.compile(r"^(lea %sp@\((-?\d+)\)|(addq[lw]|adda[lw]|subq[lw]|suba[lw]) #(-?\d+)),%sp$")
_REGISTERS = [f"%d{n}" for n in range(8)] + [f"%a{n}" for n in range(6)] + ["%fp", "%sp"]
OPERAND_BYTES = {"l": LONG_BYTES, "w": WORD_BYTES, "b": WORD_BYTES}      # a byte pushed keeps SP even
TRAP_2 = "trap #2"
_A_TRAP = re.compile(r"^trap #\d+$")
# WHAT A REGISTER (or the frame's slots, as one place) IS LOADED WITH, instruction by instruction — the reading's
# whole knowledge of a call through a pointer:
_CALL_THROUGH = re.compile(r"^(?:jsr|jmp) (%(?:a\d|fp))@$")
_LOAD_OF_AN_ADDRESS = re.compile(r"^lea (?:%pc@\()?([0-9a-f]+) <([\w.]+)(?:\+0x[0-9a-f]+)?>\)?,(%(?:a\d|fp))$")
_LOAD_OF_AN_IMMEDIATE = re.compile(r"^movea?l #(\d+),(%(?:[ad]\d|fp)|%sp@\(-?\d+\)|%sp@)$")
_COPY = re.compile(r"^movea?l (%(?:[ad]\d|fp)|%sp@\(-?\d+\)|%sp@),(%(?:[ad]\d|fp)|%sp@\(-?\d+\)|%sp@)$")
_REGISTER_RESTORED = re.compile(r"^movem?a?l %sp@\+,")
_STORES_TO = re.compile(r",(%(?:[ad]\d|fp))$")
A_FRAME_SLOT = "a frame slot"           # every `d(sp)` of a function, as ONE place: what it spills an address to
FROM_THE_MACHINE = "a pointer read out of memory, or computed"
A_NUMBER = "a number"
# `deepest`, bytes below the entry's SP, down the calls `path` names; `at_a_trap` the deepest SP a trap is taken at
# (None: none is reached), down `trap_path`.
StackUse = namedtuple("StackUse", "deepest path at_a_trap trap_path")


def _registers_in(listed):
    """How many registers a `movem` list names (`%d2-%d7/%a2-%fp`)."""
    count = 0
    for span in listed.split("/"):
        first, _, last = span.partition("-")
        count += _REGISTERS.index(last or first) - _REGISTERS.index(first) + 1
    return count


def _stack_effect(text):
    """How many bytes one listed instruction moves SP DOWN by (negative: up), calls and returns apart."""
    mnemonic, _, operands = text.partition(" ")
    constant = _SP_BY_A_CONSTANT.match(text)
    if constant:
        if constant.group(2) is not None:
            return -int(constant.group(2))
        return int(constant.group(4)) * (1 if constant.group(3).startswith("sub") else -1)
    if mnemonic == "pea":
        return LONG_BYTES
    if mnemonic.startswith("link"):
        return LONG_BYTES - int(operands.rsplit("#", 1)[1])
    pushes, pops = operands.endswith("%sp@-"), "%sp@+" in operands.split(",")[0] and "," in operands
    assert mnemonic != "unlk" and not operands.endswith(",%sp"), f"the stack reading does not follow `{text}`"
    if not (pushes or pops):
        return 0
    size = OPERAND_BYTES[mnemonic[-1]]
    if mnemonic.startswith("movem"):
        size *= _registers_in(operands.split(",")[1 if pops else 0])
    return size if pushes else -size


def listed_functions_of(listing, ends):
    """`{name: [(address, text)]}` of every function `listing` labels: one `ends` (`{start: end}`) sizes read to its
    end and no further (in the shipped blob a displaced C core keeps its body and loses its name), one it does not
    size — a transcription's entry — to the next label."""
    functions, body, end = {}, None, None
    for line in listing.splitlines():
        label, listed = _LISTED_LABEL.match(line), _LISTED_LINE.match(line)
        if label:
            body, end = functions.setdefault(label.group(2), []), ends.get(int(label.group(1), 16))
        elif listed and body is not None and (end is None or int(listed.group(1), 16) < end):
            body.append((int(listed.group(1), 16), listed.group(2).strip()))
    return functions


@functools.cache
def _listed_functions(elf):
    ends = {symbol.start: symbol.start + symbol.size for symbol in transcription.symbol_table(elf) if symbol.size}
    return listed_functions_of(transcription.listing(elf), ends)


def _depth_of(reached):
    return -1 if reached[0] is None else reached[0]


def _place(operand):
    return A_FRAME_SLOT if operand.startswith("%sp@") else operand


class _Loads:
    """What a place of ONE function — a register, or its frame's slots as one place — holds where a call goes
    through it: functions BY VALUE (`lea <f>,a2`; `move.l #<f's address>,d2`, or spilt to a frame slot), another
    place's content (a copy), or FROM_THE_MACHINE — anything else stored there. Read AT THE CALL, back through its
    own block to the load that reaches it (a scratch register is loaded and called a line apart, and holds a dozen
    other things elsewhere); where the block holds no load, every load of the function (a register GCC keeps a
    function in across its body). A register popped back off the stack is its caller's value again: no load."""

    def __init__(self, body, starts):
        self._body, self._starts = body, starts
        local = {at for at, _text in body}
        self._targets = {int(target.group(1), 16) for _at, text in body for target in [_NAMED_TARGET.search(text)]
                         if target and int(target.group(1), 16) in local and _TRANSFER.match(text.split(" ")[0])}
        self._index = {at: index for index, (at, _text) in enumerate(body)}

    def _load(self, text):
        """`(the place stored to, what is stored)` by one instruction, or None: a function's name, `("copy", place)`,
        or FROM_THE_MACHINE."""
        address, immediate, copy = _LOAD_OF_AN_ADDRESS.match(text), _LOAD_OF_AN_IMMEDIATE.match(text), _COPY.match(text)
        if address:
            function = self._starts.get(int(address.group(1), 16))
            return address.group(3), function or FROM_THE_MACHINE
        if immediate:
            # ...an immediate that is no function's address is a number (an offset into the image): not code.
            return _place(immediate.group(2)), self._starts.get(int(immediate.group(1)), A_NUMBER)
        if copy:
            return _place(copy.group(2)), ("copy", _place(copy.group(1)))
        stored = _STORES_TO.search(text)
        if stored and not _REGISTER_RESTORED.match(text):
            return stored.group(1), FROM_THE_MACHINE
        return None

    def _everywhere(self, place, seen):
        """Every load of `place` in the function, copies followed where each is made."""
        held = set()
        for index, (_at, text) in enumerate(self._body):
            load = self._load(text)
            if load and load[0] == place:
                held |= self._resolved(load[1], index, seen)
        if place == A_FRAME_SLOT:
            # The slots are one place and hold the function's data too: of what is spilt there only the functions
            # named by value count — and where none is, the slot called through is an ARGUMENT, the caller's pointer.
            return {function for function in held if function not in (FROM_THE_MACHINE, A_NUMBER)} or {FROM_THE_MACHINE}
        return held

    def _resolved(self, loaded, index, seen):
        if isinstance(loaded, tuple):
            return self.held_at(index, loaded[1], seen)
        return {loaded}

    def held_at(self, index, place, seen=frozenset()):
        """What `place` holds where the instruction of `index` reads it: function names, FROM_THE_MACHINE, A_NUMBER."""
        if (index, place) in seen:
            return set()
        seen = seen | {(index, place)}
        if place != A_FRAME_SLOT:
            for before in range(index - 1, -1, -1):
                if self._body[before + 1][0] in self._targets:
                    break                               # a block's head: another path joins here, with its own loads
                load = self._load(self._body[before][1])
                if load and load[0] == place:
                    return self._resolved(load[1], before, seen)
        return self._everywhere(place, seen)

    def held_by_the_call_at(self, at, place):
        return self.held_at(self._index[at], place)


class StackReading:
    """The stack use of one blob's functions (above), each read once. `through_a_pointer`: `{caller: callees}` for
    a caller whose call through a pointer OF THE MACHINE is declared (forker: the four fork entries a queue entry
    can hold)."""

    def __init__(self, elf, through_a_pointer=None):
        self._functions = _listed_functions(elf)
        self._starts = {symbol.start: symbol.name for symbol in transcription.symbol_table(elf) if symbol.kind in "Tt"}
        self._declared = dict(through_a_pointer or {})
        self._use, self._reading, self._loads = {}, [], {}

    @classmethod
    def of_listing(cls, functions, starts=None, through_a_pointer=None):
        """...the same reading over `functions` (`{name: [(address, text)]}`) handed as they are: the reading's
        own tests."""
        reading = cls.__new__(cls)
        reading._functions, reading._starts = functions, dict(starts or {})
        reading._declared, reading._use, reading._reading, reading._loads = dict(through_a_pointer or {}), {}, [], {}
        return reading

    def _through_a_pointer(self, function, register, at):
        """The functions `function`'s call through `register` at `at` can reach — or the refusal."""
        if function not in self._loads:
            self._loads[function] = _Loads(self._functions[function], self._starts)
        held = self._loads[function].held_by_the_call_at(at, register)
        callees = held - {FROM_THE_MACHINE, A_NUMBER}
        if FROM_THE_MACHINE in held:
            assert function in self._declared, (
                f"{function} calls through {register} at {at:#x}, which holds {FROM_THE_MACHINE} — not a function "
                f"it names by value: the stack reading follows such a call only where its caller DECLARES what the "
                f"machine's pointer can hold (`through_a_pointer`)")
            callees |= set(self._declared[function])
        assert callees, (f"{function} calls through {register} at {at:#x} and nothing it loads there names a "
                         f"function: the stack reading has no callee to follow")
        return sorted(callees)

    def of(self, function):
        """The `StackUse` of `function` entered with its return address already on the stack."""
        if function not in self._use:
            assert function not in self._reading, f"the stack reading does not follow recursion: {self._reading + [function]}"
            assert function in self._functions, f"the stack reading has no listing of {function}"
            self._reading.append(function)
            try:
                self._use[function] = self._read(function)
            finally:
                self._reading.pop()
        return self._use[function]

    def _callees_at(self, function, at, text, target):
        if target:
            return [target.group(2)]
        through = _CALL_THROUGH.match(text)
        # OWED, AES band 5 wave 2: A JUMP THROUGH A TABLE IN THE FUNCTION'S OWN TEXT (`jmp %pc@(2,%d0:w)` — the opcode
        # switch, `src/aes/gemsuper.c`'s COMPILED_AS_A_JUMP_TABLE, the one function built with one) is refused here
        # with every other transfer the reading does not follow: the reading learns the table — its sixteen-bit
        # distances, each an arm of the same body — when a path it is asked for first goes through the switch.
        assert through, f"{function}: the stack reading does not follow the transfer `{text}` at {at:#x}"
        return self._through_a_pointer(function, through.group(1), at)

    def _read(self, function):
        body = self._functions[function]
        following = {at: after for (at, _text), (after, _next) in zip(body, body[1:])}
        texts, depth_at, todo = dict(body), {}, [(body[0][0], 0)]
        deepest, trapped = (0, ()), (None, ())          # each `(depth, the calls under this function that lead there)`
        while todo:
            at, depth = todo.pop()
            if at in depth_at:
                assert depth_at[at] == depth, f"{function}: two paths reach {at:#x} at depths {depth_at[at]} and {depth}"
                continue
            depth_at[at], text = depth, texts[at]
            mnemonic, target = text.split(" ")[0], _NAMED_TARGET.search(text)
            assert not _A_TRAP.match(text) or text == TRAP_2, (
                f"{function} takes `{text}` at {at:#x}: the stack reading counts no frame of the OS under a trap "
                f"other than `{TRAP_2}`")
            if text == TRAP_2:
                trapped = max(trapped, (depth, ()), key=_depth_of)
            if mnemonic in _ENDS_A_PATH:
                continue
            if _TRANSFER.match(mnemonic):
                local = target and int(target.group(1), 16) in texts
                calls = mnemonic.startswith(("jsr", "bsr"))
                if local and not calls:
                    todo.append((int(target.group(1), 16), depth))
                else:
                    under = depth + (LONG_BYTES if calls else 0)
                    deepest = max(deepest, (under, ()))
                    for callee in self._callees_at(function, at, text, target):
                        use = self.of(callee)
                        deepest = max(deepest, (under + use.deepest, use.path))
                        if use.at_a_trap is not None:
                            trapped = max(trapped, (under + use.at_a_trap, use.trap_path), key=_depth_of)
                if mnemonic.startswith(("jmp", "bra")):
                    continue
            elif text.startswith("lea ") and text.endswith(",%sp") and "%sp@" not in text:
                depth = 0                               # a glue's own stack: counted from its top
            elif text.startswith("moveal ") and text.endswith(",%sp"):
                continue                                # ...and left: the interrupted stack again
            else:
                depth += _stack_effect(text)
            deepest = max(deepest, (depth, ()))
            assert at in following, (f"{function}: a path runs off the listed body's last instruction (`{text}` at "
                                     f"{at:#x}) — neither a return nor a jump ends it")
            todo.append((following[at], depth))
        return StackUse(deepest[0], (function, *deepest[1]), trapped[0], (function, *trapped[1]))


# ---- WHAT A SOURCE OF THE SWITCH'S KIND HOLDS BESIDE THE ROM'S BYTES: its thunks, and nothing else ----------------------------
# The pins hold each ENTRY (its bytes, its stream); the thunks under them — our own instructions, which take an
# Alcyon frame into a C call — are held here: each one's BODY, instruction for instruction, the C it calls named;
# and that the entries and thunks of a source LIE END TO END, what follows the last being the assembler's fill up
# to the next object's first symbol — so no byte of the source lies outside a sized symbol (an instruction after a
# `.size` would otherwise ride along unpinned).
_SYMBOL_NOISE = re.compile(r" <[^>]*>")
ASSEMBLER_FILL = b"\x4e\x71"            # `nop`: what gas pads a code section with
IMAGE_ONLY_THUNK = ("pea 0", "jsr {body}", "addql #4,%sp", "rts")
ONE_LONG_THUNK = ("movel %sp@(4),%sp@-", "pea 0", "jsr {body}", "addql #8,%sp", "rts")
ONE_WORD_THUNK = ("movew %sp@(4),%d0", "extl %d0", "movel %d0,%sp@-", "pea 0", "jsr {body}", "addql #8,%sp", "rts")
TWO_LONGS_THUNK = ("movel %sp@(8),%sp@-", "movel %sp@(8),%sp@-", "pea 0", "jsr {body}", "lea %sp@(12),%sp", "rts")


def vet_a_thunk(blob, thunk, shape, body):
    """`thunk` of `blob` is `shape` (one of the four above) into the C `body`: every instruction, and whom it calls."""
    listed = [(text, _NAMED_TARGET.search(text)) for _at, text in _listed_functions(blob.elf)[thunk]]
    read = tuple(f"jsr {target.group(2)}" if text.startswith("jsr") and target else _SYMBOL_NOISE.sub("", text)
                 for text, target in listed)
    assert read == tuple(line.format(body=body) for line in shape), f"{thunk} is not its shape into {body}: {read}"


def vet_laid_end_to_end(blob, symbols):
    """`symbols` of `blob` lie END TO END in that order, each as long as the table sizes it, and from the last one's
    end to the next symbol the blob defines there is the assembler's fill and no instruction. (What lies BEFORE the
    first is held on the source's own object — `first_symbol_offsets`: in a linked blob the bytes ahead of it are
    another object's, sized or not.)"""
    table = {symbol.name: symbol for symbol in transcription.symbol_table(blob.elf)}
    at = table[symbols[0]].start
    for name in symbols:
        assert table[name].start == at, f"{name} begins at {table[name].start:#x}: {at:#x} is where the one before it ends"
        at += table[name].size
    following = min(symbol.start for symbol in table.values() if symbol.start >= at and symbol.name not in symbols)
    fill = bytes(blob.blob[at - blob.base:following - blob.base])
    assert fill == ASSEMBLER_FILL * (len(fill) // len(ASSEMBLER_FILL)) and len(fill) < LONG_BYTES, (
        f"after {symbols[-1]} ({at:#x}) and before the next symbol ({following:#x}) lie bytes of no symbol: {fill.hex()}")


def first_symbol_offsets(objects):
    """`{object: (its first text symbol, that symbol's offset in the object)}` for each assembled `objects` (paths):
    0 where the source's first instruction is its first label's — anything else is bytes ahead of every symbol."""
    first = {}
    for path in objects:
        listed = subprocess.run(["m68k-elf-nm", "-n", "--defined-only", str(path)], capture_output=True, text=True,
                                check=True).stdout.split("\n")
        text = [line.split() for line in listed if len(line.split()) == 3 and line.split()[1] in "Tt"]
        first[path] = (text[0][2], int(text[0][0], 16))
    return first


# ---- THE DISPATCHER'S STACK, MEASURED: disp's loop entered as savestate leaves it -----------------------------------------
# What the static reading cannot give — how far the OS goes below a `trap #2` (the AES's trap handler, the VDI's
# dispatcher and the function called: ROM code on both shores) — and what holds the reading to the truth: a run from
# disp's loop (forker, idle), SP where savestate leaves it, over a machine with forks queued, to disp's call of
# switchto — or, in a machine nothing wakes, to the second keyboard poll at which it waits for an interrupt. The run
# is stopped at the trap handler's entry and where each trap returns: how deep SP was at the trap, and — the stack
# below it laid with a pattern first — how far the OS's own code wrote under it.
# THE CALLS THROUGH A POINTER OF THE MACHINE under disp, and what each pointer can hold (`StackReading`): forker's
# `jsr (a0)` — a queue entry's code, one of the four fork functions; and the cursor routine mchange (drawrat, inlined)
# calls out of AES_DRWADDR — the AES's own bare `rts`, or the VDI's default routine a played-back recording's
# vex_curv hands back.
DRAWRAT_S_ROUTINES = ("aes_rom_justretf", "vdi_rom_default_user_cur")
THROUGH_A_POINTER = {"aes_forker": sorted(FORK_ENTRY_SYMBOLS.values()), "aes_mchange": DRAWRAT_S_ROUTINES}
DISP_S_C = ("disp_to_aes_disp_act", "disp_to_aes_mwait_act", "disp_to_aes_forker", "disp_to_aes_idle")
BENCH_ENTRY_BYTES = 2 * LONG_BYTES      # the bench lays its sentinel and one argument at the SP it is handed
EXCEPTION_FRAME_BYTES = WORD_BYTES + LONG_BYTES
LoopRun = namedtuple("LoopRun", "deepest traps")      # bytes below disp's SP; `(depth at the trap, bytes under it)` each
THE_SECOND_WAIT = 2


PATTERN_STEP, PATTERN_BIAS = 7, 3       # odd, so the 256 bytes of the pattern are all there before one repeats


def _untouched(at):
    """The pattern the stack under a trap's frame is laid with: a byte that tells its own address, so the lowest one
    the OS's code stored over is found by reading."""
    return (at * PATTERN_STEP + PATTERN_BIAS) & aes.BYTE_MASK


class _LoopStops:
    """THE WATCH OF A RUN FROM DISP'S LOOP (`rom_bench.watched`): stopped at `switchto` and at idle's `poll` — where it
    ENDS the run (`aes_event.Ended`): at disp's call of switchto, or at the second poll at which the machine waits
    for an interrupt — and at the VDI's trap handler and where each trap returns: `traps`, `(how deep SP was at the
    trap, how far the OS wrote under it)` each, the stack below the trap's frame laid with a pattern first."""

    def __init__(self, switchto, poll, lo, sp):
        self.first = frozenset({switchto, poll, aes_event.VDI_TRAP})
        self._switchto, self._poll, self._lo, self._sp = switchto, poll, lo, sp
        self._taken_at, self._waits, self.traps = None, 0, []

    def stopped(self, pc, frame, memory):
        back = None
        if pc == self._switchto:
            raise aes_event.Ended
        if pc == self._poll:
            self._waits += waits_for_an_interrupt(memory)
            if self._waits == THE_SECOND_WAIT:
                raise aes_event.Ended
        elif pc == aes_event.VDI_TRAP:
            self._taken_at, back = frame + EXCEPTION_FRAME_BYTES, case.long_in(memory, frame + aes_event.EXCEPTION_FRAME_PC)
            for at in range(self._lo, frame):
                memory[at] = _untouched(at)
        else:                           # ...back from the trap: what its handler stored under the frame
            lowest = next((at for at in range(self._lo, self._taken_at) if memory[at] != _untouched(at)), self._taken_at)
            self.traps.append((self._sp - self._taken_at, self._taken_at - lowest))
        return (self.first | ({back} if back else set())) - {pc}


def _loop_run(memory, loop, switchto, poll):
    """A `LoopRun` of the dispatcher's loop at `loop` over `memory`, entered on the dispatcher's stack as savestate
    leaves it and watched to its end (`_LoopStops`): one run, under one budget, vetted."""
    lo, sp = DISPATCHER_STACK[0], DISPATCHER_STACK[1] - BENCH_ENTRY_BYTES
    watch = _LoopStops(switchto, poll, lo, sp)
    emu.install_chip_seeds()
    try:
        result = emu.run_bench(memory, loop, 0, sp, emu.SENTINEL, max_insns=SCHEDULED_INSNS, door=watch.first,
                               seed_regs=rom_bench.entry_registers())
        rom_bench.watched(result, loop, watch, memory, max_insns=SCHEDULED_INSNS)
    except aes_event.Ended:
        pass
    else:
        raise AssertionError(f"the loop at {loop:#x} ran to the run's sentinel")
    finally:
        emu.bench_abort()
    rom_bench.vet_the_run_just_made(f"the dispatcher's loop at {loop:#x}")
    wrote, truncated = emu.bench_writes(memory)
    assert not truncated, f"the loop at {loop:#x} overflowed the write ledger"
    on_the_stack = [at for at in wrote if lo <= at < sp]
    return LoopRun(sp - min(on_the_stack) if on_the_stack else 0, tuple(watch.traps))


@functools.cache
def _calls_before_disp_s_loop():
    """How many Line-F call words the ROM's disp holds before its loop: each is a `jsr`, four bytes longer, in ours."""
    return sum(text is None for _at, text in rom_data.instructions(addrs.AES_ROM_DISP, addrs.AES_ROM_DISP_LOOP))


def _our_vdi_under_the_trap(memory, blob):
    """`memory` (the blob laid in) with the build's OWN VDI under `trap #2`, as a ROM that ships links it: the BIOS's
    door ($fc4ebc: `jsr <the VDI's entry>` / `rte` — not reconstructed, so STAGED, the same two instructions) calls
    the blob's `vdi_rom_entry`, and that entry's `jsr` of the dispatcher — which the blob spells with the ROM's
    address (`src/vdi/entry.S`) — lands in the blob's C through the image-only thunk every C core is entered by."""
    assert case.long_in(memory, addrs.SYSVAR_VDI_ENTRY) == addrs.GEM_TRAP2_VDI_DOOR, "the premise: the BIOS's VDI door"
    entry, into_c = blob.entry("vdi_rom_entry"), VDI_STUBS_AT + len(JSR_ABSOLUTE_LONG) + LONG_BYTES + len(RTE)
    door = JSR_ABSOLUTE_LONG + struct.pack(">I", entry) + RTE
    thunk = (PUSH_ADDRESS_SHORT + bytes(WORD_BYTES) + JSR_ABSOLUTE_LONG + struct.pack(">I", blob.entry("vdi_dispatch"))
             + DROP_STACK_LONG + RTS)
    assert len(door) + len(thunk) == VDI_STUBS_BYTES
    memory[VDI_STUBS_AT:VDI_STUBS_AT + VDI_STUBS_BYTES] = door + thunk
    memory[addrs.SYSVAR_VDI_ENTRY:addrs.SYSVAR_VDI_ENTRY + LONG_BYTES] = struct.pack(">I", VDI_STUBS_AT)
    call = JSR_ABSOLUTE_LONG + struct.pack(">I", addrs.VDI_ROM_DISPATCH)
    sites = [at for at in range(entry, entry + VDI_ENTRY_BYTES, WORD_BYTES) if bytes(memory[at:at + len(call)]) == call]
    assert len(sites) == 1, f"vdi_rom_entry calls the dispatcher at {sites}: one `jsr` was expected"
    memory[sites[0] + len(JSR_ABSOLUTE_LONG):sites[0] + len(call)] = struct.pack(">I", into_c)


def our_loop_run(blob, machine, our_vdi=False):
    """`blob`'s disp entered AT ITS LOOP over `machine` (pokes: a machine inside the dispatcher, forks queued by the
    ROM's interrupts — their codes relocated to the blob's entries, as Tier 3 lays a ROM-made queue into our build).
    `our_vdi`: the build's own VDI under each `trap #2`, where the machine has the ROM's."""
    tier3 = bench_tier3()
    memory = make_image(machine)
    memory[blob.base:blob.base + len(blob.blob)] = blob.blob
    tier3.map_fork_codes(memory, tier3.fork_relocation(blob.elf, "aes_forker"))
    if our_vdi:
        _our_vdi_under_the_trap(memory, blob)
    loop = (blob.entry("aes_rom_disp") + addrs.AES_ROM_DISP_LOOP - addrs.AES_ROM_DISP
            + _calls_before_disp_s_loop() * (transcription.JSR_BYTES - WORD_BYTES))
    return _loop_run(memory, loop, blob.entry("aes_rom_switchto"), blob.entry("aes_chkkbd"))


@derived.kept
def the_rom_s_loop_run(machine):
    """...and the ROM's own, over the same machine."""
    return _loop_run(make_image(machine), addrs.AES_ROM_DISP_LOOP, addrs.AES_ROM_DISP_SWITCHTO, addrs.AES_ROM_CHKKBD)


def dispatcher_stack_reading(blob):
    """`(the deepest our build's own code can take the dispatcher's stack, the deepest it can be at a trap)` under
    disp's four `jsr`s into C — each `StackUse`'s bytes with the return address disp's `jsr` pushed — and the two
    `StackUse`s they are read off (their paths, for whoever asks why)."""
    reading = StackReading(blob.elf, THROUGH_A_POINTER)
    uses = [reading.of(thunk) for thunk in DISP_S_C]
    deepest = max(uses, key=lambda use: use.deepest)
    trapped = max(uses, key=lambda use: _depth_of((use.at_a_trap,)))
    return LONG_BYTES + deepest.deepest, LONG_BYTES + trapped.at_a_trap, deepest, trapped


# ---- WHAT AN INTERRUPT NEEDS OF THE STACK IT IS TAKEN ON: the ROM's handlers from their vectors, AND OUR OWN ENTRIES -------
# An interrupt taken inside the dispatcher lands on the dispatcher's stack: the 68000's frame, then whatever the
# handler pushes before it is done — or before the AES's glue moves to a stack of its own. MEASURED, each handler
# entered with an exception frame, over a machine THE CURSOR IS SHOWN IN (the ROM's own gsx_mon
# over the snapshot, which holds it hidden): the three bytes of a mouse packet through the ACIA's handler (the last
# reaches the VDI's mouse interrupt and the AES's glue), a key's make code, eight system ticks through Timer C's
# (every fourth reaches the VDI's tick and, through the AES's glue, the routine it displaced — on the INTERRUPTED
# stack), and the vertical blank that then redraws the cursor the packet moved.
# TWO MACHINES, and they do not need the same:
#   * THE ROM'S OWN HANDLERS, entered from their vectors (`interrupt_needs`) — what lands on the dispatcher's stack
#     while the BIOS under our AES is the ROM's;
#   * OUR BUILD'S OWN ENTRIES (`our_interrupt_needs`: `src/bios/isr.S`'s isr_acia_entry, isr_timer_c_entry,
#     isr_vbl_entry — what a ROM that ships puts in the three vectors). Each is the ROM's own handler, instruction
#     for instruction, so it needs what the ROM's needs. MEASURED all the same and not assumed: a C body under an
#     entry — which is what each had — saves every callee-saved register GCC's ABI names on the interrupted stack
#     (40-52 bytes the ROM's handler, which runs on in the registers it has just saved, never pushes). What the
#     vectors BELOW the entry name is the machine's — the IKBD's service routine and the BIOS's packet machine
#     (not reconstructed as entries), the VDI's mouse interrupt, tick and cursor routine and the AES's glue (ours
#     are the ROM's bytes: the same stack).
# THE NESTING THE MASK ALLOWS (read off the ROM, $fc06de / $fc30c4 / $fc29ce, and `isr.S`): the dispatcher's own code
# runs with interrupts open; a vertical blank is level 4 and its handler never raises the mask (the VDI's cursor
# routine at $fcff2a draws at the level it was called at), so AN MFP INTERRUPT (level 6: the ACIA's or Timer C's)
# IS TAKEN INSIDE IT AT ITS DEEPEST; neither MFP handler lowers the mask, so two do not nest and nothing nests on
# one (the AES's forkq brackets with spl7 and restores what it found: 6); a horizontal blank (level 2, eight bytes)
# is taken only over code at level 0-1 and never inside another handler. THE WORST is the sum of a vertical blank's
# need and the larger MFP handler's.
INTERRUPT_STUB_AT = PROGRAM_AT + 2 * LONG_BYTES         # in this battery's band, past gotopgm's one instruction
INTERRUPT_STUB_BYTES = 14
VDI_STUBS_AT = INTERRUPT_STUB_AT + INTERRUPT_STUB_BYTES + WORD_BYTES
VDI_STUBS_BYTES = 22                                   # the staged door (`jsr`, `rte`) and the thunk into the C dispatcher
VDI_ENTRY_BYTES = 0x60                                 # vdi_rom_entry, to its `rts` ($fc9f9e..$fc9ff8)
# ...and the two slot routines a case stages BESIDE the VDI's own in the machine's `_vblqueue`: one that keeps no
# register (`isr.keeps_nothing`), a marker behind it, and the byte each leaves.
KEEPS_NOTHING_AT = VDI_STUBS_AT + VDI_STUBS_BYTES
SLOT_MARKS_AT = BAND_AT + BAND_BYTES - 2                # the last two bytes of the band
SLOT_BEHIND_AT = KEEPS_NOTHING_AT + len(isr.keeps_nothing(SLOT_MARKS_AT)[0])
assert SLOT_BEHIND_AT + len(isr.store_byte(isr.MARK, SLOT_MARKS_AT + 1) + RTS) <= SLOT_MARKS_AT
PUSH_RETURN_AND_SR = PUSH_RETURN_PC + struct.pack(">h", len(PUSH_SR) + len(JMP_ABSOLUTE_LONG) + LONG_BYTES + WORD_BYTES) + PUSH_SR
A_MOUSE_PACKET = (aes_event.NO_BUTTON_PACKET, 5, 3)    # the IKBD's three bytes: the header, dx, dy
ACIA_INTERRUPTING_WITH_A_BYTE = 0x80 | addrs.ACIA_RECEIVE_FULL
NO_ACIA_WAITS = 0xFF                                   # MFP_GPIP as the handler's loop reads it: nothing more to serve
A_COLOUR_MONITOR = 0x80                                # ...and as the vertical blank reads it: no monochrome monitor
TICKS_MEASURED = 8
# ...and how many more a held key's repeat is waited for at most: Kbrate's initial delay and its interval are counted
# in SERVICED ticks, one in four (the snapshot's are 15 and 2) — a first press repeats within their sum, and a wait
# longer than that is the "already repeating" arm's wrap, which no case here means to measure.
TICKS_A_SERVICED_ONE = 4


def ticks_to_a_repeat_at_most(image):
    return TICKS_A_SERVICED_ONE * (image[addrs.KBRATE_DELAY] + image[addrs.KBRATE_REPEAT] + 1)


THE_DIVIDER_BEFORE_A_SERVICED_TICK = 0x4444            # `rol.w`: the one of its four states that comes out negative
# (delay, interval left) from which the next serviced tick injects: the delay run out — or running out in that very
# tick — and one tick of the interval left.
THE_REPEAT_IS_DUE = ((0, 1), (1, 1))
AN_ARROW_KEY = addrs.SCANCODE_CURSOR_UP                # with Alternate held, a mouse movement
MOUSE_POSITION = slice(vdi.LINEA_GCURX, vdi.LINEA_GCURY + WORD_BYTES)
InterruptNeeds = namedtuple("InterruptNeeds", "acia timer_c vbl")
# OUR entries by the vector each is installed in.
OUR_ENTRIES = {addrs.VECTOR_ACIA: "isr_acia_entry", addrs.VECTOR_TIMER_C: "isr_timer_c_entry",
               addrs.VECTOR_VBL: "isr_vbl_entry"}
A_DISK_OPERATION_IN_FLIGHT = struct.pack(">H", 1)       # SYSVAR_FLOCK, nonzero: the floppy's VBL service stands off


def _interrupt_entered(image, entry, until=0, **seeds):
    """The handler at `entry` entered as an interrupt enters it — an exception frame under it — over `image`
    IN PLACE (what it wrote laid in, its own stack apart): how many bytes of the interrupted stack it used.
    `until`: a PC the run is ended at, for a handler measured up to there."""
    stub = PUSH_RETURN_AND_SR + JMP_ABSOLUTE_LONG + struct.pack(">I", entry) + RTS
    assert len(stub) == INTERRUPT_STUB_BYTES
    staged = bytearray(image)
    staged[INTERRUPT_STUB_AT:INTERRUPT_STUB_AT + len(stub)] = stub
    _final, writes, _regs = emu.run(staged, INTERRUPT_STUB_AT, {}, stop_pc=until, **seeds)
    for at, data in case.written_by(writes).items():
        image[at:at + len(data)] = data
    return emu.STACK_TOP - min(at for at in writes if at in case.STACK_BAND)


def cursor_shown(onto):
    """`onto` continued by the ROM's own gsx_mon: THE CURSOR SHOWN, as a desktop that waits for its user has it (the
    snapshot was taken with it hidden)."""
    delta, _final, _regs = aes_event.derived(addrs.AES_ROM_GSX_MON, onto)
    return merge_pokes(onto, delta)


def grabbed_while_shown(onto):
    """...and then by the ROM's own ct_mouse(TRUE), the control manager's grab of the mouse: it keeps what it found —
    the cursor SHOWN — in AES_CT_MOUSE_SHOWN, THE WORD AFTER THE FORK QUEUE'S COUNT. What tells a count read as the
    word it is from one read as a longword: no other machine holds anything there."""
    shown = cursor_shown(onto)
    delta, _final, _regs = aes_event.derived(addrs.AES_ROM_CT_MOUSE, shown, frame=struct.pack(">h", CT_MOUSE_GRAB))
    grabbed = merge_pokes(shown, delta)
    assert AES_CT_MOUSE_SHOWN == aes.AES_FORK_COUNT + WORD_BYTES and case.word_in(make_image(grabbed), AES_CT_MOUSE_SHOWN)
    return grabbed


@functools.cache
def _where_the_cursor_routine_returns():
    """The `rts` of the VDI's vertical-blank cursor routine (_vblqueue's first slot): both its arms end there."""
    return next(at for at, text in rom_data.instructions(addrs.VDI_ROM_VBL_DRAW_CURSOR, addrs.VDI_ROM_VEX_BUTV)
                if text == "rts")


QUIET_PSG = {register: aes.BYTE_MASK if register == PSG_MIXER else 0 for register in range(PSG_REGISTERS)}
ACIA_SEEDS = {addrs.IKBD_ACIA_STATUS: ACIA_INTERRUPTING_WITH_A_BYTE, addrs.MFP_GPIP: NO_ACIA_WAITS}
VBL_SEEDS = {"hw_seed": {addrs.MFP_GPIP: A_COLOUR_MONITOR}, "psg_seed": QUIET_PSG}


def _received(image, entry_of, *scancodes_and_packets):
    """Each byte through the ACIA's handler at `entry_of(VECTOR_ACIA)`, in turn: the need of each."""
    return [_interrupt_entered(image, entry_of(addrs.VECTOR_ACIA),
                               io_seed={**ACIA_SEEDS, addrs.IKBD_ACIA_DATA: byte & aes.BYTE_MASK})
            for byte in scancodes_and_packets]


def _ticked_until_the_held_key_repeats(image, entry_of):
    """Timer C's handler entered tick after tick until THE AUTO-REPEAT INJECTS THE HELD KEY — the one tick in which
    the handler calls the keyboard's queue-a-key routine ($fc2c42): the need of each tick, the injecting one last.
    The state is the machine's own: the key's make code came through the ACIA's handler, and the initial delay and
    the interval are counted down by the ticks themselves."""
    needs, at_most = [], ticks_to_a_repeat_at_most(image)
    for _tick in range(at_most):
        due = (image[addrs.SYSVAR_KB_REPEAT_DELAY], image[addrs.SYSVAR_KB_REPEAT_LEFT]) in THE_REPEAT_IS_DUE
        serviced = case.word_in(image, addrs.SYSVAR_TIMER_C_DIVIDER) == THE_DIVIDER_BEFORE_A_SERVICED_TICK
        needs.append(_interrupt_entered(image, entry_of(addrs.VECTOR_TIMER_C), psg_seed=QUIET_PSG))
        if due and serviced:
            assert image[addrs.SYSVAR_KB_REPEAT_LEFT] == image[addrs.KBRATE_REPEAT], "the premise: the interval was reloaded"
            return needs
    raise AssertionError(f"the held key did not repeat within {at_most} ticks")


def _needs_measured(image, entry_of, vbl_until=0):
    """The three handlers' needs over `image` (the cursor shown), each entered at `entry_of(vector)` — THE WORST OF
    EVERY ARM a handler has here: a mouse packet's bytes and a key's make code; ticks that are divided away and
    ticks that reach the VDI's; the tick that injects a held PLAIN key's repeat; and the one that injects a held
    ALT+ARROW's, which is a mouse packet made by the keyboard and so the VDI's mouse interrupt and the AES's glue
    under timer C. Every state is made by the handlers' own runs.
    RETURN IS PRESSED, RELEASED AND PRESSED AGAIN: the snapshot was taken with Return the repeating key (the key
    that ended the boot's last prompt), and a make code of the key ALREADY repeating takes the handler's other arm —
    both counters zeroed, the next repeat a whole wrap of the interval away (some thousand ticks): that arm is
    measured by the first make, and not waited on. After its break the make is a first press: Kbrate's delay and interval loaded, the repeat due within `ticks_to_a_repeat_at_most`."""
    received = _received(image, entry_of, *A_MOUSE_PACKET, aes_event.RETURN_KEY)
    assert (image[addrs.SYSVAR_KB_REPEAT_DELAY], image[addrs.SYSVAR_KB_REPEAT_LEFT]) == (0, 0), (
        "the premise: the make of the key already repeating took that arm — measured, with the rest")
    received += _received(image, entry_of, aes_event.RETURN_KEY | addrs.SCANCODE_RELEASE, aes_event.RETURN_KEY)
    assert (image[addrs.SYSVAR_KB_REPEAT_DELAY], image[addrs.SYSVAR_KB_REPEAT_LEFT]) == (
        image[addrs.KBRATE_DELAY], image[addrs.KBRATE_REPEAT]), "the premise: a first press loads Kbrate's two counts"
    assert image[CUR_FLAG], "the premise: the packet moved a cursor that is shown — the next vertical blank redraws it"
    ticked = [_interrupt_entered(image, entry_of(addrs.VECTOR_TIMER_C), psg_seed=QUIET_PSG) for _tick in range(TICKS_MEASURED)]
    assert min(ticked) < max(ticked), "the premise: the ticks measured include one that reaches the VDI's tick and one that does not"
    tail = case.word_in(image, addrs.IOREC_IKBD + addrs.IOREC_TAIL)
    ticked += _ticked_until_the_held_key_repeats(image, entry_of)
    assert case.word_in(image, addrs.IOREC_IKBD + addrs.IOREC_TAIL) != tail, "the premise: the repeat queued the held Return"
    received += _received(image, entry_of, aes_event.RETURN_KEY | addrs.SCANCODE_RELEASE, addrs.SCANCODE_ALTERNATE,
                          AN_ARROW_KEY)
    moved_to = bytes(image[MOUSE_POSITION])
    ticked += _ticked_until_the_held_key_repeats(image, entry_of)
    assert bytes(image[MOUSE_POSITION]) != moved_to, "the premise: the repeat of Alt + an arrow moved the mouse"
    blank = _interrupt_entered(image, entry_of(addrs.VECTOR_VBL), until=vbl_until, **VBL_SEEDS)
    assert not image[CUR_FLAG], "the premise: the vertical blank redrew the cursor"
    return InterruptNeeds(max(received), max(ticked), blank)


@derived.kept
def interrupt_needs():
    """`InterruptNeeds`: the bytes of the interrupted stack each of the ROM's three handlers used at its worst."""
    image = make_image(cursor_shown(aes_event.machine()))
    needs = _needs_measured(image, lambda vector: case.long_in(image, vector))
    # ...and the vertical blank's whole need is its need where the cursor routine returns: what OUR entry's is read at.
    again = make_image(cursor_shown(aes_event.machine()))
    assert _needs_measured(again, lambda vector: case.long_in(again, vector), _where_the_cursor_routine_returns()) == needs
    return needs


def _the_shown_machine_with(blob):
    image = make_image(cursor_shown(aes_event.machine()))
    image[blob.base:blob.base + len(blob.blob)] = blob.blob
    # A LABELLED ARGUMENT-CLASS POKE: with `flock` clear our vertical blank reaches the floppy's own service, which
    # is not reconstructed and HALTS (`src/bios/vbl.c`, floppy_vbl) — so the blank is measured on the arm that is.
    image[addrs.SYSVAR_FLOCK:addrs.SYSVAR_FLOCK + WORD_BYTES] = A_DISK_OPERATION_IN_FLIGHT
    return image


def our_interrupt_needs(blob):
    """`InterruptNeeds` of `blob`'s OWN ENTRIES (`OUR_ENTRIES`), over the same machine, bytes and ticks. The vertical
    blank is read WHERE THE CURSOR ROUTINE RETURNS — the handler's deepest, as the ROM's own is (`interrupt_needs`);
    the whole run's is `our_vertical_blank_redrawing_the_cursor`'s, and a test holds the two equal."""
    image = _the_shown_machine_with(blob)
    return _needs_measured(image, lambda vector: blob.entry(OUR_ENTRIES[vector]), _where_the_cursor_routine_returns())


def _the_machine_whose_cursor_moved(blob):
    """`_the_shown_machine_with(blob)` after a mouse packet through the ROM's own ACIA handler: the shown cursor has
    moved, and the next vertical blank's first slot — the VDI's cursor routine — redraws it."""
    image = _the_shown_machine_with(blob)
    for byte in A_MOUSE_PACKET:
        _interrupt_entered(image, case.long_in(image, addrs.VECTOR_ACIA),
                           io_seed={**ACIA_SEEDS, addrs.IKBD_ACIA_DATA: byte & aes.BYTE_MASK})
    assert image[CUR_FLAG], "the premise: the packet moved a cursor that is shown"
    return image


def our_vertical_blank_redrawing_the_cursor(blob):
    """`blob`'s isr_vbl_entry run TO ITS `rte` over the machine a mouse packet has just moved the shown cursor in: the
    bytes of the interrupted stack it used. (The VDI's cursor routine returns with A6 = $fd00fe when it redraws, and
    the ROM's handler holds nothing in a register across a slot: `include/staged_call.h`, the two shapes that give
    their routine every register.)"""
    return _interrupt_entered(_the_machine_whose_cursor_moved(blob), blob.entry(OUR_ENTRIES[addrs.VECTOR_VBL]), **VBL_SEEDS)


BlankRun = namedtuple("BlankRun", "final registers")


def vertical_blanks_over_a_slot_that_keeps_nothing(blob):
    """`(the ROM's handler's BlankRun, our entry's)` over ONE machine: the cursor shown and just moved (the ROM's own
    runs), and — A LABELLED ARGUMENT-CLASS STAGING of two slot routines — the machine's own `_vblqueue` holding, behind
    the VDI's cursor routine, a routine that leaves all ones in D0-D7/A0-A6 and a marker behind that. Each handler is
    entered with `isr.DIRTY_REGISTERS` and run to its `rte`."""
    image = _the_machine_whose_cursor_moved(blob)
    queue = case.long_in(image, addrs.SYSVAR_VBLQUEUE)
    behind_the_cursor_routine = queue + addrs.VBLQUEUE_ENTRY_BYTES
    assert case.long_in(image, queue) == addrs.VDI_ROM_VBL_DRAW_CURSOR and case.word_in(image, addrs.SYSVAR_NVBLS) >= 3
    assert not any(image[behind_the_cursor_routine:behind_the_cursor_routine + 2 * addrs.VBLQUEUE_ENTRY_BYTES])
    staged = {KEEPS_NOTHING_AT: isr.keeps_nothing(SLOT_MARKS_AT)[0],
              SLOT_BEHIND_AT: isr.store_byte(isr.MARK, SLOT_MARKS_AT + 1) + RTS,
              behind_the_cursor_routine: struct.pack(">II", KEEPS_NOTHING_AT, SLOT_BEHIND_AT)}
    for at, data in staged.items():
        image[at:at + len(data)] = data
    runs = []
    for entry in (case.long_in(image, addrs.VECTOR_VBL), blob.entry(OUR_ENTRIES[addrs.VECTOR_VBL])):
        stub = PUSH_RETURN_AND_SR + JMP_ABSOLUTE_LONG + struct.pack(">I", entry) + RTS
        machine = bytearray(image)
        machine[INTERRUPT_STUB_AT:INTERRUPT_STUB_AT + len(stub)] = stub
        final, _writes, left = emu.run(machine, INTERRUPT_STUB_AT, dict(isr.DIRTY_REGISTERS), **VBL_SEEDS)
        runs.append(BlankRun(final, {name: left[name] for name in isr.DIRTY_REGISTERS}))
    return tuple(runs)


# The bytes of the staged entry that name the handler entered: the one place the two runs' machines differ by design.
THE_ENTRY_NAMED = range(INTERRUPT_STUB_AT + len(PUSH_RETURN_AND_SR) + len(JMP_ABSOLUTE_LONG),
                        INTERRUPT_STUB_AT + len(PUSH_RETURN_AND_SR) + len(JMP_ABSOLUTE_LONG) + LONG_BYTES)


def worst_interrupt_need(needs=None):
    """The most an interrupt takes of the stack it lands on: a vertical blank, and an MFP interrupt inside it — of
    `needs`, or the ROM's own handlers'."""
    needs = needs or interrupt_needs()
    return needs.vbl + max(needs.acia, needs.timer_c)


# ---- THE DISPATCHER'S C: disp_act, mwait_act and idle (`src/aes/evdisp.c`) -------------------------------------------------
IMAGE, LONG = vdi.IMAGE_ARG, vdi.LONG_ARG
DISP_ACT, MWAIT_ACT, IDLE = "AES_ROM_DISP_ACT", "AES_ROM_MWAIT_ACT", "AES_ROM_IDLE"
SIGNATURES = {DISP_ACT: (None, (IMAGE, LONG)), MWAIT_ACT: (None, (IMAGE, LONG)), IDLE: (None, (IMAGE,))}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)
ROUTINES = tuple(SIGNATURES)
# disp_act and mwait_act reach no hook: each run of their C is guarded in a plain fork. idle polls the keyboard
# through the VDI (and, where it would wait for an interrupt, asks the idle hook): its forks serve the drawing hooks.
SERVED_IN_A_FORK = aes_event.SERVED_IN_A_FORK + aes_event.SCHEDULER_HOOKS
FORK_GUARDED = {DISP_ACT: (), MWAIT_ACT: (), IDLE: SERVED_IN_A_FORK}
LAYER = aes_event.Layer(ROUTINES)
Arrival = aes_event.LayerArrival
SHELL, SCREEN_MANAGER, SPARE_PD = aes.SHELL_PD, aes.SCREEN_MANAGER_PD, aes.AES_PD_TABLE + 2 * aes.PD_BYTES
END_UPDATE_FRAME = aes_event.frame_of(("w", aes.header_constants("wmupdate.h")["WM_END_UPDATE"]))


# THIS MODULE IMPORTS NO BATTERY, AND NO HELPER THAT IMPORTS ONE: the door users' batteries register their switching
# rows through it (`aes_switching` stands on it), and `aes_evasync` imports two of them — imported here, a battery
# that asked for the registrar would find this module half made. What a scenario takes from one is asked for where
# the scenario is RUN.
def _key_wait_frame():
    """PD0's evnt_multi for a key alone, as the asynchronous waits' battery stages it."""
    import aes_evasync
    return aes_evasync.ev_multi_frame(aes.EV_MU_KEYBD)[0]


def _the_lock_waited_on():
    """The screen's lock held by the desk, the screen manager queued on it (`test_aes_wm_update.waited_on`)."""
    import test_aes_wm_update
    return test_aes_wm_update.waited_on()


def _keyed_ahead():
    """The snapshot — both processes parked, the dispatcher idling — with Return typed and not yet polled."""
    return aes_event.typed_ahead(None, aes_event.RETURN_KEY)


A_DELAY_MS = 100


def a_delay_run_out_and_the_mouse_on_the_bar():
    """The desk parked in an evnt_multi for a delay (the ROM's own call, to the dispatcher's loop), then the mouse
    moved onto the menu bar and every tick of the delay taken: two forks queued, a wait of each process due."""
    import aes_evasync
    frame, pokes = aes_evasync.ev_multi_frame(aes.EV_MU_TIMER, timer=A_DELAY_MS)
    image = make_image(aes_event.parked(addrs.AES_ROM_EV_MULTI, frame, merge_pokes(aes_event.machine(), pokes)))
    aes_event.move_to(*aes_event.MENU_BAR_POINT)(image)
    aes_event.ticks(A_DELAY_MS // aes_evasync.TICK_MS)(image)
    return aes_event.as_pokes(image, upto=addrs.ST_RAM_BYTES)


# EACH SCENARIO IS THE ROM'S OWN RUN of something the scheduler does, watched at the three routines' entries: the
# machine it starts from, the ROM entry it runs, the frame (bytes, or a builder asked where the scenario is run),
# where it ends (nothing: it returns) and the arrivals it DECLARES, in order.
Scenario = namedtuple("Scenario", "start entry frame ends arrivals")
SCENARIOS = {
    # forker finds nothing, idle's poll queues the key; forker posts it (the desk woken), idle moves the desk to the
    # empty ready list; the desk is entered.
    "a key wakes the desk": Scenario(_keyed_ahead, addrs.AES_ROM_DISP_LOOP, b"", (addrs.AES_ROM_EV_MULTI_RETURN,),
                                     (IDLE, IDLE, DISP_ACT)),
    # the desk asks for a key and none has come: it is put on the not-ready list, the screen manager's already there.
    "the desk blocks": Scenario(aes_event.machine, addrs.AES_ROM_EV_MULTI, _key_wait_frame, (addrs.AES_ROM_DISP_LOOP,),
                                (MWAIT_ACT,)),
    # the desk calls the dispatcher with nothing else ready: back on the (empty) ready list, one idle poll, resumed.
    "the desk yields": Scenario(aes_event.machine, addrs.AES_ROM_DSPTCH, b"", (), (DISP_ACT, IDLE)),
    # the desk gives the screen's lock to the screen manager, which waits for it: the desk is put back first, then
    # idle moves the woken screen manager BEHIND it — a walk past one process.
    "the lock handed to the screen manager": Scenario(_the_lock_waited_on, addrs.AES_ROM_WM_UPDATE,
                                                      END_UPDATE_FRAME, (), (DISP_ACT, IDLE, DISP_ACT)),
    # both processes parked, and two forks queued by the interrupts before the dispatcher runs: forker wakes BOTH in
    # one pass, and idle moves two woken processes — to where the dispatcher is about to enter the first.
    "a delay run out and the mouse on the bar: two processes woken at once": Scenario(
        a_delay_run_out_and_the_mouse_on_the_bar, addrs.AES_ROM_DISP_LOOP, b"", (addrs.AES_ROM_DISP_SWITCHTO,),
        (IDLE, DISP_ACT, DISP_ACT)),
}


@derived.kept
def _run_of(name):
    """The ROM's run of the scenario `name`: a derivation, kept by content."""
    declared = SCENARIOS[name]
    frame = declared.frame() if callable(declared.frame) else declared.frame
    return LAYER.watched(declared.start(), declared.entry, set(declared.ends), frame)


_SCENARIOS = aes_event.Scenarios({name: declared.arrivals for name, declared in SCENARIOS.items()}, _run_of,
                                 arrivals_of=lambda made: made.arrivals)
scenario, case_id, cases = _SCENARIOS.scenario, _SCENARIOS.case_id, _SCENARIOS.cases
arrival, at = _SCENARIOS.arrival, _SCENARIOS.at
short = aes_event.short_name


# ---- THE CONTEXT DROPS (V4): `(lo, hi, why)` each, and each ONLY WHERE THE ROM'S RUN STORES IT -----------------------------
uda_of = aes_event.uda_of


def uda_context_drop(uda):
    """A process's SAVED CONTEXT, as savestate stores it: the register block, A6 and the two stack pointers."""
    return ((uda + aes.UDA_REGS, uda + aes.UDA_TRAP_SSP,
             "a process's saved context (savestate's: D0-A5, A6, the supervisor and the user stack pointer): the CPU "
             "state of whoever called dsptch — a host core's caller has none, and our build's holds its own frames' "
             "addresses; compared byte for byte where both shores enter with one register file "
             "(`test_aes_switch.py`, savestate's rows)"),)


D1_SLOT = aes.UDA_REGS + LONG_BYTES     # the register block's second longword: D1, then D2


def line_f_scratch_drop(uda):
    """...and the two longwords of it that differ when both shores DO enter with one register file and ours is a
    build: D1 and D2 as the Line-F handler leaves them for the routine it enters — the call word's offset, the
    caller's status register ($fee8c2..$fee8e0) — where our disp `jsr`s savestate with the caller's own."""
    return ((uda + D1_SLOT, uda + D1_SLOT + 2 * LONG_BYTES,
             "D1 and D2 of a saved context: the Line-F handler's own leavings in the ROM (savestate is entered through "
             "it), the caller's registers where disp's call is a `jsr` (`src/aes/switch.S`)"),)


DISPATCHER_STACK = aes_event.DISPATCHER_STACK
DISPATCHER_STACK_WHY = ("the dispatcher's own stack ($899a..$8c1a), which savestate moves to: return addresses and "
                        "frames of the build that ran on it — the ROM's Alcyon frames and Line-F exception frames, "
                        "our thunks' and GCC's, none at all for a host core")
# OUR SHORE OF A TIER 3 ROW THAT DROPS IT (`bench/tier3.py`: `RomBench.measure`, `spans_put_back`, which reads this
# window). GCC's frames under our disp go DEEPER than Alcyon's, so our run stores bytes there the ROM's run never
# did — and a drop names what the ORIGINAL stored (`rom_bench.vet_dropped`), nothing else. The stack is dead once
# switchto has left it: our image's is put back as our run found it, and what then differs is exactly what the ROM's
# run stored — the row's named, vetted drop (`aes_event.stored_spans`). How deep our build can go is held where it is read off
# the build (`StackReading`; `test_aes_evdisp_model.py`).
DISPATCHER_STACK_DROP = ((*DISPATCHER_STACK, DISPATCHER_STACK_WHY),)


# ---- THE SCHEDULER DRIVER (V3): ONE RUN OF THE ROM THROUGH ITS OWN DISPATCHER, INTERRUPTS DELIVERED AT THE n-th IDLE -------
# The machine WAITS FOR AN INTERRUPT in one place: idle's loop about to poll the keyboard with nothing ready, nothing
# woken and nothing queued (`AES_ROM_IDLE_LOOP`). Each such arrival of a run is an IDLE, numbered from 0 as the run
# makes them, whichever process's dispatch it is in; a case says what is delivered at which (`{idle: interrupt}`, an
# interrupt as `aes_event.interrupted` takes one: `aes_event.key(...)`, `press`, `ticks(n)`, `move_to(x, y)`), and the
# driver delivers it there — the run set aside, the ROM's own interrupt code run over a copy of the memory, what it
# wrote laid in, the run continued at the very instruction — exactly as `interrupted` delivers at a door call.
# An idle with nothing to deliver is PASSED (the poll that follows may find a key typed ahead); a second one in a row
# after the case's last delivery is the machine idling for ever: the run is ended there (IDLES), not spun.
#
# ...AND AT A POLL THAT IS NO IDLE (`at_polls`). idle polls the keyboard EVERY time round its loop — with a process
# ready, one woken or a fork queued too — so an interrupt that arrives between two processes' turns is taken THERE,
# and a key is then polled before the process an earlier interrupt woke has run: the one way a real machine answers
# a key AND a message in one wake (the writer woken first, the key posted while it has yet to write). Every arrival
# at idle's poll is a POLL, numbered from 0 as the run makes them, idles among them; a case names a poll that is no
# idle by that ordinal. A delivery named at a poll that IS an idle is refused (it is `at_idle`'s, by the idle's own
# ordinal: one spelling a delivery), and so is one named at a poll the run never makes.
#
# ...AND AT THE DOOR CALLS OF THE PROCESS THAT MADE THE CALL, IN THE SAME RUN (a door USER's: a loop whose waits take
# an interrupt each, the last of which BLOCKS and is woken by one more — taken at an idle). ONE DERIVATION TAKES BOTH:
# the run is watched at the door's entries too (`aes_event.DoorStops`, as `aes_event.interrupted` watches one), its
# door calls numbered as the run makes them, what each is handed kept (`calls`), and the interrupt a case names at a
# call's ordinal taken at that call's entry (`at_calls`). THE DOOR WATCH IS THE CALLER'S OWN PROCESS'S: from the
# moment the ROM's disp enters ANOTHER process until it enters the caller again no door entry is a stop — the screen
# manager makes door calls of its own, from the very return addresses the caller's calls come from, and they are no
# call of the row's (`aes_switching.Switching` follows a row's replay the same way, on both shores).
# ...AND IT IS THE CALLER'S OWN CODE'S: from the caller's dsptch until disp enters a process again no door entry is a
# stop either. What the DISPATCHER's forker calls there is the dispatcher's — bchange's post_button, for a button
# change delivered while the caller is inside the dispatcher. Under a DOOR USER blocked inside a door call it was
# never counted (an entry reached inside an open call is no call). Where NO door call is open it was the run's "next
# door call": for a caller that YIELDS by a dsptch of its own (the screen manager's handlers waiting a button up:
# band 5 wave 1) — which the C's own forker, calling the entry's core, hands to no door, so the host's model and the
# ROM's run disagreed on a call neither's caller made — AND FOR A ROW THAT IS ITSELF A DOOR ENTRY (entered at the
# entry, no call open while it sleeps): EIGHTEEN PRE-EXISTING ROWS' `Scheduled.calls` AND `.answers` LOST THAT
# post_button BY THIS RULE (aes_ev_multi 11, aes_ap_tplay 4, aes_dispatch 2, aes_ev_block 1 — a button taken at an
# idle or a poll of theirs). Harmless, and held: none of the eighteen is a door user (no compare ever read those
# lists for them), and what the rule leaves out of each is the forker's post_button and nothing else
# (`test_aes_switching.py`, `THE_EIGHTEEN`: the run with the rule off holds exactly those calls
# more) — a caller's own call cannot be reclassified silently.
RETURNED, IDLES = "the call returned", "the machine idles: every process waits, nothing more is delivered"
Scheduled = namedtuple("Scheduled",
                       "memory d0 delivered idles entered ended started calls at_calls polls at_polls answers dispatches",
                       defaults=((), {}, None, {}, (), ()))
# Where a delivery of one scheduled run was taken.
AT_AN_IDLE, AT_A_DOOR_CALL, AT_A_POLL = "at an idle", "at a door call", "at a poll that is no idle"
SCHEDULED_INSNS = aes_event.DERIVATION_INSNS       # a nested process's cap: the same order as a derivation's
_IDLE_STOPS = {addrs.AES_ROM_IDLE_LOOP: frozenset({addrs.AES_ROM_IDLE_POLLED, addrs.AES_ROM_DISP_SWITCHTO}),
               addrs.AES_ROM_IDLE_POLLED: frozenset({addrs.AES_ROM_IDLE_LOOP, addrs.AES_ROM_DISP_SWITCHTO}),
               addrs.AES_ROM_DISP_SWITCHTO: frozenset({addrs.AES_ROM_IDLE_LOOP, addrs.AES_ROM_IDLE_POLLED})}
EVERY_STOP = frozenset(_IDLE_STOPS)
# ...and dsptch's own entry, where the caller's process asks for the switch: nothing of the switch is stored yet, and
# a host core stands at the dispatcher's hook — the one point of a run through the dispatcher both shores share.
THE_CALLER_S_DISPATCH = frozenset({addrs.AES_ROM_DSPTCH})


def waits_for_an_interrupt(memory):
    """Does the machine of `memory`, at idle's poll, wait for an interrupt: no process ready, none woken, no fork
    queued — the three words idle's own loop tests."""
    return not (case.long_in(memory, aes.AES_RLR) or case.long_in(memory, aes.AES_DRL)
                or case.word_in(memory, aes.AES_FORK_COUNT))


def what_idle_tests(memory):
    """...those three words as `memory` holds them, `{address: bytes}`: WHAT A DELIVERY AT A POLL THAT IS NO IDLE IS
    CHECKED AGAINST, on every shore, beside the bytes it writes — the machine stands there as the ROM's own run did
    (which process is ready, which woken, how many forks queued). An idle needs no such check (all three are zero);
    a poll taken at another point of idle's loop — after the woken were moved, say — holds others."""
    return {at: bytes(memory[at:at + size]) for at, size in ((aes.AES_RLR, LONG_BYTES), (aes.AES_DRL, LONG_BYTES),
                                                             (aes.AES_FORK_COUNT, WORD_BYTES))}


@functools.cache
def _idle_s_test_of_the_count():
    """Where the ROM's idle tests the fork queue's count: its one instruction that names the word."""
    at, = [at for at, text in rom_data.instructions(addrs.AES_ROM_IDLE, addrs.AES_ROM_DISP)
           if text and text.startswith("tstw") and f"{aes.AES_FORK_COUNT:#x}" in text]
    return at


class _InTurn:
    """A watch (`rom_bench.watched`) that stops a run at each of `stops` in turn and ENDS it at the last."""

    def __init__(self, stops):
        self.first, self._later = frozenset({stops[0]}), list(stops[1:])

    def stopped(self, _pc, _sp, _memory):
        if not self._later:
            raise aes_event.Ended
        return frozenset({self._later.pop(0)})


def _the_rom_s_idle_reaches(machine, *stops):
    """Does the ROM's own idle, entered over `machine`, reach each of `stops` in turn?"""
    memory, watch = make_image(aes.staged(IDLE, (), machine)), _InTurn(stops)
    try:
        result = rom_bench.original_entered(memory, addrs.AES_ROM_IDLE, watch.first, max_insns=SCHEDULED_INSNS)
        rom_bench.watched(result, addrs.AES_ROM_IDLE, watch, memory, max_insns=SCHEDULED_INSNS)
    except aes_event.Ended:
        return True
    finally:
        emu.bench_abort()
        rom_bench.vet_the_run_just_made(f"the ROM's idle, watched for {[f'{stop:#x}' for stop in stops]}")
    return False


def the_rom_s_idle_tests_the_count(machine):
    """...its test of the fork queue's count: the word the interrupts count too, READ."""
    return _the_rom_s_idle_reaches(machine, _idle_s_test_of_the_count())


def the_rom_s_idle_polls_again(machine):
    """...its poll A SECOND TIME — back at its loop's head after the first came back: it found nothing to return
    for, and spins."""
    return _the_rom_s_idle_reaches(machine, addrs.AES_ROM_IDLE_POLLED, addrs.AES_ROM_IDLE_LOOP)


def dispatcher_stop(pc, memory, entered, idles, delivered=False, polls=None):
    """ONE STOP of a run through the ROM's own dispatcher, read — the one reading of its three stops, whoever drives
    the run: at disp's call of switchto `entered(pd)`, for the process at the ready list's head; at idle's poll
    `polls()` (where given: every poll, an idle or not) and then `idles()`, where the machine waits for an interrupt
    — or waited, and has just been `delivered` one there. Answers the stops to arm next: never the PC it stands at."""
    if pc == addrs.AES_ROM_DISP_SWITCHTO:
        entered(case.long_in(memory, aes.AES_RLR) & aes_event.OS_BUS_ADDR_MASK)
    elif pc == addrs.AES_ROM_IDLE_LOOP:
        waited = delivered or waits_for_an_interrupt(memory)
        if polls:
            polls()
        if waited:
            idles()
    return _IDLE_STOPS[pc]


class _Idling:
    """The watch of one scheduled run (`aes_event.interrupting`'s): stopped at idle's poll, at the instruction after
    it and at disp's call of switchto — never arming the PC it stands at — and, WHILE THE CALLER'S OWN PROCESS RUNS,
    at the door's entries (`door`: an `aes_event.DoorStops` that does not `block`; `caller` the PD that made the
    call). It counts the POLLS and, among them, the IDLES, says what is due at each and at each door call (`due`:
    keyed `(AT_AN_IDLE, n)`, `(AT_A_POLL, n)` or `(AT_A_DOOR_CALL, n)`), keeps the processes the dispatcher enters,
    and ENDS the run (`aes_event.Ended`) where the machine idles for ever."""
    # From the caller's own dsptch until disp enters a process, a door entry is the DISPATCHER's call and no stop
    # (above). False only in the RED that shows what the rule keeps out.
    KEEPS_THE_DISPATCHER_S_CALLS_OUT = True

    def __init__(self, memory, at_idle, door, caller, at_calls=None, at_polls=None):
        self._memory, self.at_idle, self._at_calls, self.at_polls = memory, dict(at_idle), at_calls or {}, dict(at_polls or {})
        self._door, self._caller, self._door_armed, self._elsewhere = door, caller, frozenset(door.first), False
        self._in_the_dispatcher = False     # ...from the caller's own dsptch until disp enters a process (above)
        self.first = EVERY_STOP | self._door_armed | THE_CALLER_S_DISPATCH
        self.dispatches = []            # the memory at each dsptch of the CALLER's own process, as its pages
        self.polls, self.idles, self.entered, self._quiet, self._due = 0, 0, [], False, False
        self.stood = {}                 # `{poll: what_idle_tests}` where a delivery was taken at a poll that is no idle

    def due(self, _watch, pc):
        if pc in THE_CALLER_S_DISPATCH:
            return None
        if pc not in EVERY_STOP:
            return self._due_at_a_door_call(pc)
        if pc != addrs.AES_ROM_IDLE_LOOP:
            return None
        if not waits_for_an_interrupt(self._memory):
            interrupt = self.at_polls.pop(self.polls, None)
            if interrupt is None:
                return None
            self.stood[self.polls] = what_idle_tests(self._memory)
            return (AT_A_POLL, self.polls), interrupt
        assert self.polls not in self.at_polls, (
            f"a delivery is named at poll {self.polls}, which is idle {self.idles} of the run: an idle's delivery is "
            f"named at the idle (`at_idle`)")
        interrupt = self.at_idle.pop(self.idles, None)
        self._due = interrupt is not None
        return ((AT_AN_IDLE, self.idles), interrupt) if self._due else None

    def _due_at_a_door_call(self, pc):
        # Asked at an ARRIVAL only, as the door's own derivation asks (`aes_event._run_interrupting`).
        if not self._door.opens_a_call_at(pc):
            return None
        interrupt = aes_event.interrupt_at(self._at_calls, self._door.calls, pc)
        return ((AT_A_DOOR_CALL, self._door.calls), interrupt) if interrupt else None

    def stopped(self, pc, sp, memory):
        if pc in THE_CALLER_S_DISPATCH:
            self.dispatches.append(aes_event.image_pages(memory, self._door.images or ()))
            self._in_the_dispatcher = self.KEEPS_THE_DISPATCHER_S_CALLS_OUT
        elif pc in EVERY_STOP:
            if pc == addrs.AES_ROM_DISP_SWITCHTO:
                self._in_the_dispatcher = False             # a process is entered: the caller, or another (`_entered`)
            dispatcher_stop(pc, memory, self._entered, self._an_idle, delivered=self._due, polls=self._a_poll)
        else:
            self._door_armed = frozenset(self._door.stopped(pc, sp, memory))
        # (No door entry is a dispatcher's stop, so a stop at one may arm all three of those again. dsptch itself is
        # watched WHILE THE CALLER'S OWN PROCESS RUNS — another process's dispatch is that process's — and, like any
        # stop, never armed where the run stands.)
        if self._elsewhere or self._in_the_dispatcher:
            return EVERY_STOP - {pc}
        return ((EVERY_STOP | THE_CALLER_S_DISPATCH) - {pc}) | self._door_armed

    def _entered(self, pd):
        self.entered.append(pd)
        self._elsewhere = pd != self._caller

    def _a_poll(self):
        self.polls += 1

    def _an_idle(self):
        if self._quiet and not self._due and not self.at_idle:
            raise aes_event.Ended
        self._quiet, self._due, self.idles = not self._due, False, self.idles + 1


def _taken_where(delivered, where):
    """The deliveries of one scheduled run taken `where` (AT_AN_IDLE / AT_A_DOOR_CALL), by their ordinal there."""
    return {ordinal: taken for (kind, ordinal), taken in delivered.items() if kind == where}


def scheduled(entry, frame, machine, at_idle=None, budget=None, at_calls=None, at_polls=None, left_out_beside=()):
    """THE ROM'S OWN RUN of `entry` (its Alcyon `frame` where a `jsr` leaves it) over `machine`, a running process's
    call, THROUGH THE DISPATCHER, each interrupt of `at_idle` delivered at the idle of its ordinal — and each of
    `at_calls` (`{door call: interrupt}`, or a schedule: `aes_event.Waits`) at the entry of the caller's door call of
    that ordinal, each of `at_polls` at the poll of its ordinal, which is no idle (above) — by
    `aes_event.interrupting`, the one loop that takes an interrupt inside a watched run: a
    `Scheduled` — the memory it left, its D0, `delivered` (`{idle: (found, wrote)}`, as `aes_event.deliveries`
    answers door calls), how many idles it made, the processes its dispatcher ENTERED in order (each switchto), how
    it `ended` (RETURNED, or IDLES), the RAM it `started` from (what a reader compares its stores against —
    `not_compared`: the megabyte, not the sixteen of the image a second time), the door `calls` the caller's process
    made (what each was handed, read after its interrupt), `at_calls`, the deliveries taken at them (`{door call:
    (found, wrote)}`), how many `polls` its dispatcher's idle made (idles among them) and `at_polls`, the deliveries
    taken at those that were no idle — each one's `found` WITH the three words idle tests (`what_idle_tests`).
    `budget`: a derivation's (`aes_event`'s rules), for a run past the default. `left_out_beside`: `(lo, hi, why)`
    windows a ROW names as its own by nature (`aes_switching.SwitchingRow.also_dropped`), left out of every image
    taken at a stop beside the model's two (`left_out_under_the_model`) — the model's child is told the same.
    REFUSED BY NAME: a delivery named at an idle, a poll or a door call the run never makes."""
    memory = make_image(merge_pokes(machine, {abi.FIRST_ARG: frame} if frame else None))
    started, calls = bytes(memory[:RAM_BYTES]), []
    caller = case.long_in(started, aes.AES_RLR)
    door = aes_event.DoorStops(aes_event.ENTRIES, aes_event.ROM_RETURNS,
                               lambda pc, sp, over: calls.append(aes_event.handed_at(pc, sp, over)), entered_at=entry)
    door.images = left_out_under_the_model(caller & aes_event.OS_BUS_ADDR_MASK) + tuple(left_out_beside)
    watch = _Idling(memory, at_idle or {}, door, caller & aes_event.OS_BUS_ADDR_MASK, at_calls, at_polls)
    aes_event.begin_a_schedule(at_calls)
    try:
        delivered, result = aes_event.interrupting(memory, entry, watch, watch.due, budget)
        ended, d0 = RETURNED, result["d0"]
    except aes_event.Ended:
        # The loop's own ledger of what it delivered goes with the exception: a run that ends idle is one of a case
        # that delivers nothing (a wait nothing wakes).
        assert not at_idle and not at_calls and not at_polls, (
            f"the scheduled run of {entry:#x} idles for ever AFTER its deliveries: not a case this keeps")
        delivered, ended, d0 = {}, IDLES, None
    assert not watch.at_idle, (f"the scheduled run of {entry:#x} made {watch.idles} idles: nothing was delivered at "
                               f"{sorted(watch.at_idle)}")
    assert not watch.at_polls, (f"the scheduled run of {entry:#x} made {watch.polls} polls: nothing was delivered at "
                                f"{sorted(watch.at_polls)}")
    taken_at_calls = _taken_where(delivered, AT_A_DOOR_CALL)
    never_made = aes_event.undelivered(at_calls, taken_at_calls)
    assert not never_made, (f"the scheduled run of {entry:#x} made {door.calls} door call(s): nothing was delivered "
                            f"at {never_made}")
    assert ended == IDLES or case.long_in(memory, aes.AES_RLR) == caller, (
        f"the scheduled run of {entry:#x} reached its return in ANOTHER process than the one that made the call "
        f"({case.long_in(memory, aes.AES_RLR):#x}): a process of the machine whose own call was the harness's — its "
        f"continuation ends at the run's sentinel, which no process of a real machine does")
    taken_at_polls = {poll: (merge_pokes(watch.stood[poll], found), wrote)
                      for poll, (found, wrote) in _taken_where(delivered, AT_A_POLL).items()}
    return Scheduled(memory, d0, _taken_where(delivered, AT_AN_IDLE), watch.idles, tuple(watch.entered), ended, started,
                     tuple(calls), taken_at_calls, watch.polls, taken_at_polls, tuple(door.answers), tuple(watch.dispatches))


# ---- THE HOST'S MODEL OF THE SWITCH, SWITCHED ON PER CASE ------------------------------------------------------------------
# `aes_dsptch` off target asks `recreate_dispatch` (`aes/switch.h`), whose binding everywhere refuses. A case of this
# battery binds it — for its own runs alone — to THE C SCHEDULER, `aes_disp` (`src/aes/evdisp.c`: disp's own loop over
# the savestate and switchto models), and the two hooks that model asks:
#   * the POLL hook, at every poll of idle, an idle or not: it counts them, and lays the delivery the ROM's run took
#     at a poll of that ordinal that was no idle (`Scheduled.at_polls`);
#   * the IDLE hook, at each idle of the run: it lays the delivery the ROM's own scheduled run took at the idle of the
#     same ordinal (the same bytes, vetted against the memory they land on, as `interrupted` lays one at a door
#     call), passes an idle the ROM's run passed, and REFUSES one the ROM's run did not make — the C would wait for
#     ever where the ROM did not;
#   * the PROCESS hook, where the scheduler enters ANOTHER process than its caller: that process is run AS THE ROM'S
#     OWN CODE — a nested run of the ROM from switchto over a copy of the image, through whatever its own dispatcher
#     then does (its idles numbered on in the same sequence), until the ROM's disp is about to enter the CALLER
#     again; its memory is laid back and the C's call returns. With `foreign=False` it refuses by name.
#
# WHAT A FOREIGN PROCESS'S RUN IS NOT LAID BACK OVER (STORED_BY_NO_C): the dispatcher's own stack and the Line-F mask
# word — the bytes of a run through the dispatcher that are one BUILD's and never the machine's: the ROM's
# dispatcher frames (dead once its switchto has left them) and the Line-F handler's self-patched mask (rewritten
# before every use, by no C). The ROM's own code stores them during another process's turn; no C of ours ever does.
# The image keeps each AS THE C FOUND IT — as the door keeps the mask word out of a delivery
# (`aes_event.LINE_F_MASK_BYTES`) — so what a companion holds there is one thing on every row, however many times it
# dispatches: the value its machine stages, which a C that stored there would differ from. (Laid back, the image held
# there whatever the LAST foreign turn left, which the ROM's own run goes on to overwrite in every later dispatch of
# the caller — a row that blocked again after another process's turn then differed from the ROM's run in the
# dispatcher's stack, on no fault of the C: measured, mn_do woken twice after the desk's turn, 24 bytes.)
# EACH OF THE TWO IS NEEDED, AND NOTHING MORE IS LEFT OUT: without the stack, or without the mask word, the companion
# of a row another process runs in differs (`test_aes_switching.py` holds each RED). THE SR SAVE WORDS ARE LAID BACK
# AND COMPARED, as every other byte of the foreign turn is — they stood in this rule once, and no row's companion
# needed them there: the words a foreign turn's brackets park are what the ROM's whole run leaves.
POLL_SYMBOL, IDLE_SYMBOL, PROCESS_SYMBOL = "recreate_poll", "recreate_idle", "recreate_process"
STORED_BY_NO_C = (DISPATCHER_STACK, *((lo, hi) for lo, hi, _why in aes.LINE_F_MASK_WINDOW))
IDLE_PROTOTYPE = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint8))
PROCESS_PROTOTYPE = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.c_uint32)
REFUSED, SERVED = 0, 1
THE_C_SCHEDULER_S, A_PROCESS_OF_THE_ROM_S = "the C scheduler's", "a process the ROM's own code runs"    # whose dispatcher polls
IMAGE_BYTES, RAM_BYTES = aes_event.IMAGE_BYTES, addrs.ST_RAM_BYTES
HOOK_SYMBOLS = (aes_event.DISPATCH_SYMBOL, POLL_SYMBOL, IDLE_SYMBOL, PROCESS_SYMBOL)
THE_GUARD_COUNTED_ONCE = 1              # AES_INDISP inside disp: savestate's `addq.b #1` over the zero dsptch tested
A_LEAF_S_FREE_IDLE = 1                  # an idle entered with nothing ready may still find a key at its poll: once


def _said(words):
    print(words, file=sys.stderr, flush=True)
    return REFUSED


def _refusing_what_raises(hook, symbol, raised_in):
    """`hook()` (the binding of `symbol`), WHATEVER IT RAISES turned into a REFUSAL and kept in `raised_in`, for the
    binding to give it its outcome as it closes (`address_hook.answered_or_recorded`: the one mechanism) — AND SAID
    BY NAME on stderr, which is all a fork that serves the C has to say it with: a vet that raised inside a hook
    (the machine differs where a delivery is laid) would otherwise read as an idle SERVED with nothing delivered."""
    recorded = len(raised_in)
    answer = answered_or_recorded(hook, symbol, raised_in)
    for _symbol, raised in raised_in[recorded:]:
        _said(f"the scheduler's hook raised {type(raised).__name__}: {raised}")
    return answer


class _BackAtTheCaller(Exception):
    """The ROM's dispatcher, run for another process, is about to enter the process that called the C's."""


class _IdleRefused(Exception):
    """...or idles where the case delivers nothing more."""


def _unbound_poll(_buf):
    return _said("the poll hook: the dispatcher polls, and no case's binding is open (`aes_switch.scheduling`)")


def _unbound_idle(_buf):
    return _said("the idle hook: the dispatcher idles, and no case's binding is open (`aes_switch.scheduling`)")


def _unbound_process(_buf, uda, _caller_s_uda):
    return _said(f"the process hook: the dispatcher would enter the process whose UDA is {uda:#x}, and no case's "
                 f"binding is open (`aes_switch.scheduling`)")


_UNBOUND = (IDLE_PROTOTYPE(_unbound_poll), IDLE_PROTOTYPE(_unbound_idle), PROCESS_PROTOTYPE(_unbound_process))
for _symbol, _refuser in zip((POLL_SYMBOL, IDLE_SYMBOL, PROCESS_SYMBOL), _UNBOUND):
    bind_pointer(_symbol, _refuser)


def _pointer(symbol):
    return ctypes.c_void_p.in_dll(_lib, symbol)


class Scheduling:
    """ONE CASE'S BINDING OF THE MODEL, opened round its runs (`aes.run_function`'s `hook` protocol: `recording(glue)`
    wraps each run of the candidate). `reference`: the ROM's own `Scheduled` run of the case — its deliveries (at
    its idles, and at its polls that are no idle) and its idle count are what the hooks lay and hold; None for a
    LEAF case of idle, which delivers nothing and may pass A_LEAF_S_FREE_IDLE idle. `model`: the dispatcher's hook bound to the C scheduler. `foreign`: another process
    than the caller run as the ROM's own code."""

    def __init__(self, reference=None, *, model=True, foreign=False):
        self._delivered = dict(reference.delivered) if reference else {}
        self._at_polls = dict(reference.at_polls) if reference else {}
        self._free = reference.idles if reference else A_LEAF_S_FREE_IDLE
        self._model, self._foreign = model, foreign
        self.polls, self.idles, self.entered = 0, 0, []
        self._callbacks = (IDLE_PROTOTYPE(self._poll), IDLE_PROTOTYPE(self._idle), PROCESS_PROTOTYPE(self._process))
        self._previous, self._raised = None, []

    def __enter__(self):
        self._previous = [_pointer(symbol).value for symbol in HOOK_SYMBOLS]
        if self._model:
            _pointer(aes_event.DISPATCH_SYMBOL).value = ctypes.cast(_lib.aes_disp, ctypes.c_void_p).value
        for symbol, callback in zip((POLL_SYMBOL, IDLE_SYMBOL, PROCESS_SYMBOL), self._callbacks):
            bind_pointer(symbol, callback)
        return self

    def __exit__(self, raising, *_details):
        for symbol, value in zip(HOOK_SYMBOLS, self._previous):
            _pointer(symbol).value = value
        raise_what_stops_the_session(self._raised)
        if self._raised and raising is None:
            raise as_the_case_s_outcome(*self._raised[0])

    def recording(self, glue):
        def run(lib, buf):
            self.polls, self.idles, self.entered = 0, 0, []
            return glue(lib, buf)
        return run

    def _poll_over(self, memory, where):
        """The poll of the next ordinal, taken over `memory`: what the ROM's run took at that poll — one that was no
        idle — laid as an idle's delivery is. SERVED always: a poll with nothing due is passed."""
        ordinal, self.polls = self.polls, self.polls + 1
        if ordinal in self._at_polls:
            found, wrote = self._at_polls[ordinal]
            aes_event.vet_found(memory, found, f"poll {ordinal} ({where})")
            aes_event.lay(memory, wrote, lays_the_mask_word=False)
        return SERVED

    def _idle_over(self, memory, where):
        """The idle of the next ordinal, taken over `memory` (anything indexable in place): SERVED, or REFUSED."""
        ordinal, self.idles = self.idles, self.idles + 1
        assert memory[aes.AES_INDISP] == THE_GUARD_COUNTED_ONCE, (
            f"idle {ordinal} ({where}): the machine idles with the dispatcher's guard at {memory[aes.AES_INDISP]} — "
            f"idle runs inside disp alone, after savestate counted it once from zero; with it clear an interrupt "
            f"taken here would call dsptch and switch")
        if ordinal in self._delivered:
            found, wrote = self._delivered[ordinal]
            aes_event.vet_found(memory, found, f"idle {ordinal} ({where})")
            # ...the Line-F mask word left out, as the door leaves it out of a delivery (`aes_event.LINE_F_MASK_BYTES`): the
            # ROM's interrupt code rewrites it and no C does.
            aes_event.lay(memory, wrote, lays_the_mask_word=False)
            return SERVED
        if ordinal < self._free:
            return SERVED
        return _said(f"the idle hook: idle {ordinal} ({where}) — the dispatcher idles once more than the ROM's own "
                     f"run did ({self._free}): the call would block, the machine waiting for an interrupt no case "
                     f"delivers")

    @staticmethod
    def _ram_of(buf):
        return (ctypes.c_uint8 * RAM_BYTES).from_address(ctypes.addressof(buf.contents))

    def _poll(self, buf):
        return _refusing_what_raises(lambda: self._poll_over(self._ram_of(buf), THE_C_SCHEDULER_S), POLL_SYMBOL, self._raised)

    def _idle(self, buf):
        return _refusing_what_raises(lambda: self._idle_over(self._ram_of(buf), THE_C_SCHEDULER_S), IDLE_SYMBOL, self._raised)

    def _process(self, buf, uda, caller_s_uda):
        return _refusing_what_raises(lambda: self._process_run(buf, uda, caller_s_uda), PROCESS_SYMBOL, self._raised)

    def _process_run(self, buf, uda, caller_s_uda):
        if not self._foreign:
            return _said(f"the process hook: the dispatcher would enter the process whose UDA is {uda:#x} — another "
                         f"than its caller's ({caller_s_uda:#x}) — and the case does not run it: the call would "
                         f"switch away")
        found = ctypes.string_at(buf, RAM_BYTES)
        memory = bytearray(ctypes.string_at(buf, IMAGE_BYTES))
        served = self._the_rom_runs_the_process(memory, uda, caller_s_uda)
        if served == SERVED:
            for lo, hi in STORED_BY_NO_C:
                memory[lo:hi] = found[lo:hi]
            ctypes.memmove(ctypes.addressof(buf.contents), bytes(memory[:RAM_BYTES]), RAM_BYTES)
        return served

    def _the_rom_runs_the_process(self, memory, uda, caller_s_uda):
        """The process of `uda` run AS THE ROM'S OWN CODE over `memory`, from switchto, through whatever its own
        dispatcher then does, until that dispatcher is about to enter the caller again: SERVED, or REFUSED."""
        def entered(pd):
            if uda_of(pd, memory) == caller_s_uda:
                raise _BackAtTheCaller
            self.entered.append(pd)

        def idles():
            if self._idle_over(memory, A_PROCESS_OF_THE_ROM_S) == REFUSED:
                raise _IdleRefused

        def polls():
            self._poll_over(memory, A_PROCESS_OF_THE_ROM_S)

        watch = types.SimpleNamespace(stopped=lambda pc, _sp, over: dispatcher_stop(pc, over, entered, idles, polls=polls))
        emu.install_chip_seeds()
        try:
            result = emu.run_bench(memory, addrs.AES_ROM_SWITCHTO, uda, emu.STACK_TOP, emu.SENTINEL,
                                   max_insns=SCHEDULED_INSNS, door=EVERY_STOP, seed_regs=rom_bench.entry_registers())
            rom_bench.watched(result, addrs.AES_ROM_SWITCHTO, watch, memory, max_insns=SCHEDULED_INSNS)
        except _BackAtTheCaller:
            rom_bench.vet_the_run_just_made(f"the ROM's run of the process whose UDA is {uda:#x}")
            return SERVED
        except _IdleRefused:
            return REFUSED
        finally:
            emu.bench_abort()
        return _said(f"the process hook: the process whose UDA is {uda:#x} ran to the run's sentinel")


def scheduling(reference=None, **kwargs):
    """A zero-argument builder of one case's `Scheduling` — `aes.run_function`'s and `aes.doors`' `hook` shape."""
    return lambda: Scheduling(reference, **kwargs)


def hooks(reference=None, **kwargs):
    """THE HOOK of a case that runs the dispatcher's C: the event layer's own (the VDI's cores the keyboard poll calls,
    the fork functions forker calls) and the scheduler's binding."""
    return aes.doors(aes_event.EVENT_LAYER_HOOKS, scheduling(reference, **kwargs))


# A LEAF'S HOOKS: idle run alone polls the keyboard through the VDI and asks the idle hook, the model's own dispatch
# left off. A module-level value and nothing of a case's — but NOT a named one (`aes_event.named_hook`): the zygote
# makes the forks of a hook whose module it held when it was forked (`aes_event.ZYGOTE_HOLDS`), and it holds no
# battery's helper. The forks that serve these are the worker's own.
IDLE_HOOKS = hooks(model=False)

Modelled = namedtuple("Modelled", "returncode stderr image answer idles handed slots_held polls parked answered dispatched",
                      defaults=(None, None, None, None, None, None))
MODEL_SECONDS = 30                      # a nested run of a whole process inside a fork: seconds, not a core's ten
IDLES_LINE, POLLS_LINE = "the model idled: ", "the model polled: "
SLOTS_LINE = "the host slots held where the process was parked: "
PARKED_LINE = "the process was parked, and its host slots read: "


# ---- THE HOST SLOTS A ROUTINE HOLDS ACROSS A WAIT (`include/host_slot.h`) -----------------------------------------------------
# A door user hands the event layer the ADDRESS of locals of its own frame — its answer words, a MOBLK, a GRECT it
# goes on with after the wait — and off target each is a host slot, claimed before the wait and given back after it.
# Until a call could come back from a wait on the host (the model, with the door bound) nothing ever RAN a give-back
# after a wait, and nothing said which slots are live while their process is parked. Both are read off THE RUN:
#   * WHERE THE PROCESS IS PARKED (each dispatch of the run), the slots held are kept — what a second C process
#     inside the same routine would collide with (`host_slot.h`: "A SLOT PER PROCESS"). In wave 3 that cannot happen:
#     the only C process of a run is the caller, every other is the ROM's own code, which claims nothing. The day
#     the screen manager is C (band 5), each of these owes a frame per process, as the two QPBs have;
#   * WHERE THE CALL RETURNS, no slot may be held: a routine that came back from its wait and left a claim behind
#     would abort the NEXT call of it in the same process (`host_slot_take`'s assert) — refused here, by name, on
#     every door user's modelled run.
_SLOT_ID = re.compile(r"^\s*HOST_SLOT_ID_(\w+)(?:\s*=\s*HOST_SLOT_ID_(\w+)\s*\+\s*HOST_PROCESSES\s*-\s*1)?\s*,", re.M)
A_PROCESS_S_FRAME = "{role}, process {process}"
HOST_SLOT_HEADER = Path(__file__).resolve().parents[1] / "include" / "host_slot.h"


@functools.cache
def host_slot_ids():
    """The roles of `host_slot.h`'s held flags, by index: `enum host_slot` read off the header — a slot per process
    one name per process's frame."""
    header = HOST_SLOT_HEADER.read_text()
    body = header[header.index("enum host_slot {"):header.index("HOST_SLOT_ID_COUNT")]
    roles, per_process = [], aes.HOST_SLOTS["HOST_PROCESSES"]
    for role, first_frame in _SLOT_ID.findall(body):
        if first_frame:                 # `<ROLE>_LAST = <ROLE> + HOST_PROCESSES - 1`: the frames of processes 1..8
            roles[-1] = A_PROCESS_S_FRAME.format(role=first_frame, process=0)
            roles += [A_PROCESS_S_FRAME.format(role=first_frame, process=process) for process in range(1, per_process)]
        else:
            roles.append(role)
    return tuple(roles)


def host_slots_held():
    """The roles whose host slot the candidate holds claimed, now (`host_slots_held`, the library's own flags)."""
    held = (ctypes.c_ubyte * len(host_slot_ids())).in_dll(_lib, "host_slots_held")
    return [role for role, flag in zip(host_slot_ids(), held) if flag]


def _slots_in(stderr):
    lines = [line for line in stderr.splitlines() if line.startswith(SLOTS_LINE)]
    return tuple(lines[0].removeprefix(SLOTS_LINE).split(" | ")) if lines and lines[0] != SLOTS_LINE else ()


# A DOOR USER UNDER THE MODEL: what its fork binds beside the scheduler — the event door's own child binding
# (`aes_event.bind_in_a_child`): `objects`, the walked routines served (a tree walk's just_draw, newrect); `doors`,
# source the fork runs first for a routine that reaches a door of its own (`aes_event.CHILD_DOORS`).
DoorUser = namedtuple("DoorUser", "objects doors", defaults=(False, ""))


def _dispatched_in(stderr):
    """The images a door user's modelled run held at its dispatches, as its fork printed them — None for a fork
    that ended before saying."""
    said = aes_event.said_in(stderr, aes_event.DISPATCHED_LINE)
    return said if said is None else [tuple(pages) for pages in said]


def _counted_in(stderr, line_said):
    """The count a fork printed after `line_said` — None for one that ended before saying."""
    return aes_event.said_in(stderr, line_said)


def _the_c_scheduler():
    """`aes_disp` as a dispatcher's hook calls it: a function object of the fork's own, typed as the hook is."""
    disp = _lib["aes_disp"]
    disp.restype, disp.argtypes = ctypes.c_uint32, [ctypes.POINTER(ctypes.c_uint8)]
    return disp


def left_out_under_the_model(caller):
    """WHAT AN IMAGE TAKEN AT A STOP LEAVES OUT BESIDE UNDER THE MODEL (`aes_event.image_pages`' `also`) — ITS OWN
    LIST, TWO WINDOWS AND NO MORE, each whole: the saved context of the process `caller` (a PD: `uda_context_drop`,
    $44 bytes of its UDA — the shell's, $9c5a..$9c9e) and the dispatcher's stack ($899a..$8c1a), which the ROM's
    savestate and disp store at every switch and no host core does. NOT `model_drops` (the END compare's list,
    where each byte is dropped only where the ROM's run stored it — a stop in the middle of a run cannot ask that,
    so what is named here is left out WHOLE and must stay this narrow): pinned by number, with a byte either side
    of each window held red (`test_aes_event.py`)."""
    return uda_context_drop(uda_of(caller, BASE_IMAGE)) + DISPATCHER_STACK_DROP


def _a_door_user_s_run(run, buf, binding, door, at_calls, left_out_beside):
    """ONE RUN OF A DOOR USER UNDER THE MODEL, as its fork makes it: THE DOOR'S CHILD BINDING AND THE SCHEDULER'S IN
    ONE CHILD. The wrapper's arrival hook notes every frame and lays the interrupt due at a door call (`at_calls`);
    where a twin reaches the dispatcher's hook THE C SCHEDULER RUNS (`aes_disp`: `binding` lays the idles'
    deliveries and runs a foreign process as the ROM's own code) — the call comes back, and the door user's loop
    runs on to its return."""
    scheduler, parked_holding, readings = _the_c_scheduler(), [], []

    def dispatching(image):
        parked_holding.extend(role for role in host_slots_held() if role not in parked_holding)
        readings.append(aes_event.candidate_s_pages(image, left_out_beside))
        return scheduler(image)

    def call():
        if door.doors:
            exec(door.doors, {"lib": _lib, "buf": buf})         # the routine's own declared source, never a case's
        aes_event.bind_in_a_child(_lib, objects=door.objects, interrupts=at_calls, dispatching=dispatching,
                                  left_out_beside=left_out_beside)
        with binding:
            run()
            print(f"{IDLES_LINE}{binding.idles}\n{POLLS_LINE}{binding.polls}", file=sys.stderr)
        print(SLOTS_LINE + " | ".join(parked_holding), file=sys.stderr)
        print(f"{PARKED_LINE}{len(readings)}\n{aes_event.DISPATCHED_LINE}{readings!r}", file=sys.stderr)
        left = host_slots_held()
        assert not left, (f"the call RETURNED holding the host slot(s) {left} — claimed before a wait and not given "
                          f"back after it: the next call of the routine in this process would find them taken")
    return aes_event.exit_as_an_interpreter_does(call)


def modelled(symbol, typed, pokes, reference, *, answered=True, foreign=False, door=None, left_out_beside=()):
    """THE C `symbol` of the candidate (a core over the image, `typed` its values after it) run over `pokes` IN A
    FORK with the model switched on and held to `reference` (`hooks`): its exit code and stderr, the image it left —
    the fork runs over a mapping it shares with this process — its answer and how many idles and polls its run made (None
    each where it did not return).
    `door` (a `DoorUser`): the C is a DOOR USER's — a routine outside the event layer, which reaches it through the
    wrappers. Its fork binds the event door as a door child's is bound (`_a_door_user_s_run`), the interrupts the
    ROM's run took at its door calls laid at the same calls (`reference.at_calls`), and `handed` is what each of its
    door calls was handed, in order (None where the fork ended before saying), `answered` what each that returned
    answered and left (`aes_event.answered_in`), `dispatched` the image it held at each dispatch
    (`aes_event.image_pages`); `slots_held`, the host slots its
    routines held where its process was parked, and `parked`, how many times it was — each a reading of them: a run
    that says none was never audited (None where the fork ended before saying) — and a call that returns holding a
    slot is refused by name. `left_out_beside`: the row's own by-nature windows (`scheduled`'s), left out of the
    images a door user's child takes at its stops as they are out of the ROM's."""
    core = getattr(_lib, symbol)
    over = mmap.mmap(-1, IMAGE_BYTES)
    over[:] = make_image(pokes)
    buf = (ctypes.c_uint8 * IMAGE_BYTES).from_buffer(over)
    run = aes_event.one_run_of(core, typed, buf, answered)
    if door:
        binding = Scheduling(reference, model=False, foreign=foreign)
        at_calls = dict(reference.at_calls) if reference else {}
        caller = case.long_in(over, aes.AES_RLR) & aes_event.OS_BUS_ADDR_MASK
        returncode, stderr = aes_event.in_a_fork(
            _a_door_user_s_run(run, buf, binding, door, at_calls,
                               left_out_under_the_model(caller) + tuple(left_out_beside)), MODEL_SECONDS)
        dispatched = _dispatched_in(stderr)
        handed = aes_event.handed_in(stderr) if aes_event.HANDED_LINE in stderr else None
        answers_back = aes_event.answered_in(stderr)
        slots_held, parked = _slots_in(stderr), _counted_in(stderr, PARKED_LINE)
    else:
        binding = Scheduling(reference, foreign=foreign)

        def call():
            run()
            print(f"{IDLES_LINE}{binding.idles}\n{POLLS_LINE}{binding.polls}", file=sys.stderr)
        hooked = aes_event.inside_its_own_pass(aes.doors(aes_event.EVENT_LAYER_HOOKS, lambda: binding), call)
        returncode, stderr = aes_event.in_a_fork(hooked, MODEL_SECONDS, SERVED_IN_A_FORK)
        handed = slots_held = parked = answers_back = dispatched = None
    return Modelled(returncode, stderr, bytes(over), vdi_helpers.answer_in(stderr) if answered else None,
                    _counted_in(stderr, IDLES_LINE), handed, slots_held, _counted_in(stderr, POLLS_LINE), parked, answers_back,
                    dispatched)


# What a run of the model differs from the ROM's scheduled run in BY NATURE, each only where the ROM's run stored it
# (`not_compared`): the caller's saved context, the dispatcher's stack and its SR save word (above) — and the event
# layer's own, as every case of it drops them (`aes_event.EVENT_LAYER_DROPS`, the dispatcher's SR save word among them).
def model_drops(caller):
    return uda_context_drop(uda_of(caller, BASE_IMAGE)) + DISPATCHER_STACK_DROP + aes_event.EVENT_LAYER_DROPS


def not_compared(reference, drops):
    """The addresses of `drops` the ROM's scheduled run `reference` STORED — its memory against what it started
    from — with the run's own stack band and the Line-F mask word (which every Alcyon return of the ROM's run
    rewrites, an interrupt's own among them, often with the value it held)."""
    assert all(hi <= len(reference.started) for _lo, hi, _why in drops), "a drop outside the RAM a scheduled run keeps"
    return frozenset(case.STACK_BAND) | aes_event.LINE_F_MASK_BYTES | frozenset(
        at for lo, hi, _why in drops for at in range(lo, hi) if reference.memory[at] != reference.started[at])


def held_to_the_scheduled_run(name, reference, ran, drops, *, width=None):
    """THE COMPARISON of a modelled run `ran` with the ROM's scheduled run `reference` of the same call: the C
    returned where the ROM's run did, after AS MANY IDLES (its own and the processes' the ROM's code ran for it,
    one sequence), with its answer (at `width` bytes, when it answers), and the WHOLE IMAGE is
    the ROM's outside `drops` — each a `(lo, hi, why)`, and each byte of one dropped only where the ROM's run
    stored it. Answers the addresses it did not compare."""
    assert reference.ended == RETURNED, f"{name}: the premise — the ROM's scheduled run returns: {reference.ended}"
    assert ran.returncode == 0, f"{name}: the ROM's run returned; the C's fork ended {ran.returncode}:\n{ran.stderr}"
    assert ran.idles == reference.idles, (
        f"{name}: the C's run idled {ran.idles} times, the ROM's {reference.idles} — a wait more, or one fewer")
    if width:
        mask = (1 << 8 * width) - 1
        assert ran.answer & mask == reference.d0 & mask, (
            f"{name}: answers {ran.answer & mask:#x}, the ROM's run {reference.d0 & mask:#x}")
    left_out = not_compared(reference, drops)
    differ = aes_event.differing(ran.image, reference.memory, left_out)
    assert not differ, f"{name}: " + aes_event.describe_differences(name, ran.image, reference.memory, differ)
    return left_out
