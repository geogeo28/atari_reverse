"""BUS ERRORS AS A CASE FACILITY — harness-local (the user's ruling D5, 2026-10-29: "Harness-local"; NO KIT EDIT).

The oracle's CPU takes no bus error: an access where a 68000's bus would time out (no device answers — the blitter's
registers on an ST, RAM past the end of a machine's memory) is answered by the kit's own rules instead, a read of an
unmodelled I/O byte answered 0 and refused by name after the run. So a run whose ROM code DEPENDS on the fault — a
probe that points vector 2 at its own tail and touches the address — is stopped AT THE FAULTING INSTRUCTION and the
exception taken there as a 68000 takes it (`taken`): the fourteen-byte group-0 frame pushed on the supervisor stack,
SP lowered, the trace bit cleared, the PC loaded from vector 2 as the machine holds it at that instant, no register
but SP, SR and PC touched.

A FAULT IS DECLARED ON A CASE, NEVER ASSUMED (`Fault`): the instruction's address and words, the address it drives
— computed from the instruction's effective address over the CPU's registers at the stop and held equal to the
declared one — and where vector 2 must lead. Anything else at the stop is REFUSED BY NAME: another instruction, an
access to another address (an undeclared address does not fault: the run goes on and the kit's own rule answers it),
a vector pointing elsewhere, a fault taken in user mode. `aes_boot`'s blitter probe (`$fc0f34`, band 5 wave 0: "a kit
accessor is owed") was the first use; it is now one declaration of this facility (`aes_boot.THE_BLITTER_PROBE`), and
`boot.py`'s runner takes any list of them.

WHAT THE FRAME HOLDS. Group 0: (special status, access address, instruction register, SR, PC). The status word's low
five bits are R/W, I/N and the function code; its upper eleven are, on a 68000, the instruction register's (the
manual leaves them undefined) — Hatari's own choice for them is not consulted, and no ROM handler here reads them. The
PC stacked is the instruction's own advanced past its extension word (the 68000 has prefetched it when the data
access faults). Every fault declared so far is a READ in supervisor data space; a declaration says so (`Fault.read`).
"""
import struct
from collections import namedtuple

import aes
import case
import stopped_cpu

LONG_MASK, WORD_BYTES = aes.LONG_MASK, aes.WORD_BYTES
BUS = aes.OS_BUS_ADDR_MASK
VECTOR_BUS_ERROR = 0x008

FRAME = struct.Struct(">HIHHI")
FRAME_BYTES = FRAME.size
STATUS_READ, STATUS_SUPERVISOR_DATA = 0x10, 0x5
STATUS_FROM_THE_INSTRUCTION = 0xffe0

# THE EFFECTIVE ADDRESS of a single-operand instruction's source field (its low six bits): the modes a probe uses. Any
# other mode is refused by name — a declaration this facility cannot hold to the instruction is not taken on trust.
EA_MODE_SHIFT, EA_FIELD_MASK = 3, 0x7
EA_INDIRECT, EA_DISPLACED, EA_OTHER = 2, 5, 7               # (An), d16(An), the absolute / PC / immediate group
EA_ABSOLUTE_WORD, EA_ABSOLUTE_LONG = 0, 1                   # ...of EA_OTHER, by its register field
ADDRESS_REGISTER = "a{}"


class Refused(RuntimeError):
    """The run met something the model does not serve: said by name, never answered by a guess."""


Fault = namedtuple("Fault", "what at words access handler read", defaults=(True,))
Fault.__doc__ = """ONE DECLARED BUS ERROR: `what` it is (said in every refusal), the faulting instruction's address
`at` and its `words` (the opcode, then the extension words its effective address reads), the `access` address it
drives — what the 68000 puts on the bus, 32 bits as the CPU forms it — and the `handler` vector 2 must hold when it
faults (the probe's own tail). `read`: the access is a read (the only kind declared so far)."""


def _signed_word(value):
    return value - 0x10000 if value & 0x8000 else value


def effective_address(words):
    """The address the instruction `words` drives over the CPU's registers as it stands, 32 bits — or REFUSED BY NAME
    for an addressing mode this facility does not decode."""
    opcode = words[0]
    mode, field = (opcode >> EA_MODE_SHIFT) & EA_FIELD_MASK, opcode & EA_FIELD_MASK
    if mode == EA_INDIRECT:
        return stopped_cpu.register(ADDRESS_REGISTER.format(field))
    if mode == EA_DISPLACED:
        return (stopped_cpu.register(ADDRESS_REGISTER.format(field)) + _signed_word(words[1])) & LONG_MASK
    if mode == EA_OTHER and field == EA_ABSOLUTE_WORD:
        return _signed_word(words[1]) & LONG_MASK
    if mode == EA_OTHER and field == EA_ABSOLUTE_LONG:
        return words[1] << 16 | words[2]
    raise Refused(f"the opcode {opcode:#06x} addresses its operand by mode {mode}/{field}: this facility decodes (An), "
                  f"d16(An) and the absolute modes only, and takes no fault it cannot hold to the instruction")


def _vet_it_is_the_fault_declared(memory, fault):
    """The run stands at `fault.at`: refused by name unless it is the instruction declared, driving the address
    declared, with vector 2 leading where declared, in supervisor mode."""
    words = tuple(case.word_in(memory, fault.at + WORD_BYTES * n) for n in range(len(fault.words)))
    if words != tuple(fault.words):
        raise Refused(f"{fault.what}: the run stands at {fault.at:#x} over the words {[f'{w:#06x}' for w in words]}, "
                      f"not the instruction declared to fault there")
    driven = effective_address(words)
    if driven != fault.access & LONG_MASK:
        raise Refused(f"{fault.what}: the instruction at {fault.at:#x} drives {driven:#x}, not {fault.access:#x} — an "
                      f"undeclared address does not fault")
    vector = case.long_in(memory, VECTOR_BUS_ERROR) & BUS
    if vector != fault.handler:
        raise Refused(f"{fault.what}: vector 2 holds {vector:#x}, not {fault.handler:#x} — the fault would not lead "
                      f"where it is declared to")
    if not stopped_cpu.register("sr") & stopped_cpu.SR_SUPERVISOR:
        raise Refused(f"{fault.what}: a bus error at {fault.at:#x} taken in user mode: the model pushes on the stack "
                      f"the CPU stands on")


def taken(memory, fault):
    """THE STOPPED CPU, standing at `fault.at`, TAKES THE DECLARED BUS ERROR (vetted first, each refusal by name): the
    frame pushed, SP lowered, the trace bit cleared, the PC loaded from vector 2. Answers the frame's bytes by address
    (the harness's store: the CPU would have made it)."""
    _vet_it_is_the_fault_declared(memory, fault)
    status, pc, sp = stopped_cpu.register("sr"), stopped_cpu.register("pc"), stopped_cpu.register("a7")
    opcode = fault.words[0]
    access_kind = STATUS_READ if fault.read else 0
    frame = FRAME.pack(opcode & STATUS_FROM_THE_INSTRUCTION | access_kind | STATUS_SUPERVISOR_DATA,
                       fault.access & LONG_MASK, opcode, status, pc + WORD_BYTES * len(fault.words))
    sp -= FRAME_BYTES
    memory[sp:sp + FRAME_BYTES] = frame
    stopped_cpu.set_register("a7", sp)
    stopped_cpu.set_register("sr", status & ~stopped_cpu.SR_TRACE)
    stopped_cpu.set_register("pc", case.long_in(memory, VECTOR_BUS_ERROR) & BUS)
    return {sp: frame}


def entered_over(memory):
    """The CPU stands at the handler, the exception just `taken`: the fourteen bytes at ITS stack pointer, read out
    of the machine — what the 68000 pushed, wherever the model put it. (Where it stands needs no check: `taken`
    vetted vector 2 as the declared handler and loaded the PC from it.)"""
    sp = stopped_cpu.register("a7")
    return {sp: bytes(memory[sp:sp + FRAME_BYTES])}


def stops_of(faults):
    """`{the faulting instruction's address: its Fault}` of the declarations `faults` — one fault an address, and no
    fault whose handler is itself a declared fault (a run would fault into a fault for ever, never progressing)."""
    stops = {}
    for fault in faults:
        if fault.at in stops:
            raise Refused(f"two faults declared at {fault.at:#x}: {stops[fault.at].what!r} and {fault.what!r}")
        stops[fault.at] = fault
    for fault in stops.values():
        if fault.handler in stops:
            raise Refused(f"{fault.what}: its handler {fault.handler:#x} is itself a declared fault "
                          f"({stops[fault.handler].what!r}) — the run would fault there for ever")
    return stops
