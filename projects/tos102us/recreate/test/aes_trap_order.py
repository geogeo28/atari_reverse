"""CALL ORDER, AS A SURFACE: the traps a routine takes — GEMDOS's, GEM's (the VDI), the BIOS's, the XBIOS's — as ONE
ORDINAL LEDGER in the order the machine takes them, with what a few longwords of RAM HOLD AT EACH.

WHY. A routine that makes several calls out leaves, at its end, an image that says nothing of their order where
the calls commute in memory: a save buffer freed before or after the workstation left graphics, a handler given back
before or after the mouse form was set, a vector stored before or after the Setexc beside it. On iron the order is
the behaviour (an Mfree after the workstation closed; a critical error arriving between the two). Each battery's own
ledger (the VDI's calls, GEMDOS's script, the BIOS's recorder) holds ONE door's sequence, and none the interleaving.

HOW, ON BOTH SHORES WITH ONE WATCH. A trap arrives where its vector points, whichever build takes it: the ROM's
routine and our build's on a blob run over the SAME machine, so the four handlers are the same four addresses on
both shores. `TrapOrder` is a bench watch (`rom_bench.watched`) armed at them: at each arrival it notes the trap,
the function the call names and the witness longwords, arms the trap's own return (a stop may not arm the PC it
stands at) and, there, the handlers again. Nothing is staged, nothing costs a cycle, and no row's machine changes.

WHAT IT HOLDS, AND WHAT IT DOES NOT: the order of the m68k build's traps on THE TWO BLOBS, against the ROM's. THE HOST
BUILD'S ORDER IS HELD BY NOTHING — it takes no trap (its doors are hooks and direct C calls, the BIOS's with no hook
at all): a host-only reordering is invisible, and is the same C the blobs are built from.

WHAT A CALL'S FUNCTION IS: the word its caller pushed last (GEMDOS, the BIOS, the XBIOS — taken in supervisor mode,
held below: the frame is then on the stack the exception frame is) and, for GEM's `trap #2`, the VDI opcode of the
AES's own parameter block (D0/D1 are no memory; the AES's bindings all call through that block).
"""
from collections import namedtuple

from harness import addrs, make_image

import aes
import aes_event
import case

GEMDOS, GEM, BIOS, XBIOS = 1, 2, 13, 14
VECTORS = {GEMDOS: addrs.VECTOR_TRAP_GEMDOS, GEM: addrs.VECTOR_TRAP_GEM, BIOS: addrs.VECTOR_TRAP_BIOS,
           XBIOS: addrs.VECTOR_TRAP_XBIOS}
ETV_CRITIC = 0x404                      # the critical-error handler's vector (Setexc's $101)
# What is read at each call: the two vectors GEM takes and what it saved of each, and the mouse's hide count.
WITNESSES = (addrs.VECTOR_TRAP_GEM, addrs.SYSVAR_VDI_ENTRY, ETV_CRITIC, aes.AES_OLD_CRITIC, aes.AES_GL_MOFF)
SUPERVISOR = 0x2000                     # of a stacked status register
EXCEPTION_FRAME_BYTES = aes.WORD_BYTES + aes.LONG_BYTES
BUS = aes_event.OS_BUS_ADDR_MASK
GSX_PB_CONTRL = aes.header_constants("gsx.h")["AES_GSX_PB_CONTRL"]
Call = namedtuple("Call", "trap function held")


def _handlers(memory):
    """`{the trap: where it arrives}`, as the vectors stand in `memory` — BY VECTOR: two vectors pointed at one
    address are two entries (a map by address would keep one and call every arrival there that trap's)."""
    return {trap: case.long_in(memory, vector) & BUS for trap, vector in VECTORS.items()}


def _trap_arriving_at(pc, handlers):
    """The one trap whose vector points at `pc` — refused by name where two do (the arrival alone cannot say which
    was taken: a machine that stages one stub behind two vectors needs a stub each)."""
    arriving = [trap for trap, at in handlers.items() if at == pc]
    assert arriving, f"the watch stopped at {pc:#x}, where no trap arrives"
    assert len(arriving) == 1, f"traps {arriving} all arrive at {pc:#x}: one handler behind two vectors — the order watch cannot tell them apart"
    return arriving[0]


def _function(trap, sp, memory):
    if trap == GEM:
        return case.word_in(memory, case.long_in(memory, GSX_PB_CONTRL) & BUS)
    assert case.word_in(memory, sp) & SUPERVISOR, f"trap #{trap} taken in user mode: its frame is on a stack no watch is handed"
    return case.word_in(memory, sp + EXCEPTION_FRAME_BYTES)


class TrapOrder:
    """The watch (above). `made`: a `Call` each, in order. `machine`: the run's memory at its entry (the vectors a
    routine re-points — install_trap2's, a scripted handler's — are read again at every stop)."""

    def __init__(self, machine, witnesses=WITNESSES):
        self.made, self._witnesses, self._returns = [], tuple(witnesses), []
        self.first = set(_handlers(machine).values())

    def stopped(self, pc, sp, memory):
        handlers = _handlers(memory)
        if self._returns and pc == self._returns[-1]:
            self._returns.pop()
        else:
            trap = _trap_arriving_at(pc, handlers)
            self.made.append(Call(trap, _function(trap, sp, memory), tuple(case.long_in(memory, at) for at in self._witnesses)))
            self._returns.append(case.long_in(memory, sp + aes_event.EXCEPTION_FRAME_PC) & BUS)
        return (set(handlers.values()) | set(self._returns[-1:])) - {pc}

    def held(self, nth, witness):
        """What the longword `witness` held as the `nth` call was made."""
        return self.made[nth].held[self._witnesses.index(witness)]

    def names(self):
        """`[(trap, function), ...]`: the calls alone."""
        return [(call.trap, call.function) for call in self.made]


def on_both_shores(tier3, bench, row, witnesses=WITNESSES):
    """`row` (a Tier 3 row of a C routine) measured on `bench` with BOTH runs watched: `(the ROM's TrapOrder, ours)` —
    and the row's whole second differential made on the way (the image, the answer, the registers)."""
    machine = make_image(row.pokes)
    the_rom_s, ours = TrapOrder(machine, witnesses), TrapOrder(machine, witnesses)
    tier3._measure_call(bench, row, watch=ours, original_watch=the_rom_s)
    return the_rom_s, ours
