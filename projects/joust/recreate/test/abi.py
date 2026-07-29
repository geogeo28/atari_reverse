"""Calling Joust's routines under the oracle, in memory the differential can actually see.

`emu.run` starts the original with A7 at the top of the image, and `differential` deliberately
stops comparing there (`emu.STACK_GUARD_LO`), because the C reconstruction has no machine stack to
match. That is a problem for two of Joust's calling conventions:

  * its C-style routines take arguments on the caller's stack and write their results back into the
    same block, so a frame built at A7 would land in the band the diff drops; and
  * its register-argument routines can return results in D1/D2, which an image diff cannot see at
    all (`emu.run` reports only D0/D1/A0/A1).

Both helpers below fix that by poking a short 68000 stub into free image space above the program
and entering the oracle there, so every byte that matters ends up in ordinary, fully-diffed memory.
The stub is poked identically on both sides — the candidate never executes it. Whether it writes
the machine stack at all differs per helper: the stack-ABI stub deliberately writes none (see
`stack_call_pokes`), while the register-ABI one `jsr`s and so pushes a return address, which is
fine because it lands inside the guard band the diff already drops.
"""
import harness  # noqa: F401  — binds the kit, which puts its oracle/ on sys.path for the next line
import emu

# Free image space: above the program (which ends at 0x2b7ae) and far below the TOS model's staged
# file table at 0xbf000 and the stack guard above that.
STUB = 0x40000        # where the oracle enters
ARG_BLOCK = 0x40100   # a stack routine's argument block: what it sees at 4(a7)
RESULT = 0x40200      # where the register-ABI stub stores results the diff could not otherwise see

_RETURN_SLOT = ARG_BLOCK - 4   # the longword a stack routine's rts pops


def stack_call_pokes(routine):
    """Pokes that make the oracle call `routine` with its argument block at ARG_BLOCK.

        movea.l #ARG_BLOCK-4, a7     ; so 4(a7) is ARG_BLOCK, in diffed memory
        jmp     routine              ; its rts pops the sentinel pre-poked into the slot below

    Pre-poking the return slot rather than pushing it (`jsr`) means the oracle performs no stack
    write of its own, so every byte it writes is the routine's own output. Merge the result into a
    test's poke dict, then run `differential(abi.STUB, ...)`.
    """
    code = (b"\x2e\x7c" + _RETURN_SLOT.to_bytes(4, "big")     # movea.l #imm,a7
            + b"\x4e\xf9" + routine.to_bytes(4, "big"))       # jmp imm.l
    return {STUB: code, _RETURN_SLOT: emu.SENTINEL.to_bytes(4, "big")}


def register_call_pokes(routine):
    """Pokes that call `routine` (register ABI) and store its D1/D2 results through A0.

        jsr     routine
        move.l  d1,(a0)+
        move.l  d2,(a0)+
        rts

    Point A0 at RESULT through the run's registers; the two longwords then land in diffed memory.
    The `jsr` return address goes on the oracle's own stack, inside the guard band the differential
    already drops, so it costs the comparison nothing.
    """
    code = (b"\x4e\xb9" + routine.to_bytes(4, "big")          # jsr imm.l
            + b"\x20\xc1\x20\xc2\x4e\x75")                    # move.l d1,(a0)+ ; d2,(a0)+ ; rts
    return {STUB: code}
