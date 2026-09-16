"""How a case enters the TRAP DISPATCHER — the caller it stages, and the frame that caller builds.

Every other battery in this project enters a ROM routine the way the dispatcher leaves it: A5 = 0, a
`jsr` frame, the arguments above the return address (`abi.py`). THE DISPATCHER ITSELF cannot be
entered that way. It is an exception handler: the 68000 reaches it with a group-2 exception frame on
the supervisor stack — the SR word, then the return PC — it pops the function number off the
CALLER's stack below that, and it leaves through `rte`. So a case has to stage a CALLER.

    caller:   move.w  #<argument>,-(sp)     the words a `Bconin(2)` caller pushes...
              move.w  #<function>,-(sp)     ...and the function number on top of them
              pea     back(pc)              the return PC a `trap` would have pushed...
              move.w  sr,-(sp)              ...and the SR, which is the whole of the frame
              move.l  <handler>(sp),-(sp)   the dispatcher to enter...
              rts                           ...entered exactly as `trap #13` enters it
    back:     lea     <n>(sp),sp            the dispatcher leaves the caller's words; drop them
              rts                           -> the oracle's sentinel

`test_the_hand_built_frame_is_the_one_a_real_trap_builds` is what says the four lines above really
are a `trap #13`: the same case run through a caller that TRAPS, and the two runs required
indistinguishable. The hand-built one is what the Tier 3 row needs, because of the last trick here.

WHY THE HANDLER COMES OFF THE STACK rather than being assembled into the stub. Tier 3's second
differential runs the ORIGINAL and our m68k build over ONE image (`rom_bench.RomBench`), so the two
sides cannot be given different stubs — and they must reach different handlers, the ROM's $fc07f8
and our own `src/bios/trap.S`. The one place the two runs legitimately differ is the run's own stack
band, which `harness.diff_spans()` drops: `emu.run` leaves the longword at `abi.FIRST_ARG` as the
case poked it, and `emu.run_bench` writes `arg0` over it. So the stub reads its handler from there,
both sides enter at the SAME staged caller, and which dispatcher runs is the only difference between
them.

Every stub is spelt out instruction by instruction below, out of `opcodes.py`'s named words, for
`test_xbios_supexec.py`'s reason: the 68000 half and the claim the case makes about it have to be
visibly the same routine.
"""
import struct

from harness import addrs, emu

import abi
import staging
from opcodes import (COPY_LONG_ABSOLUTE, DROP_STACK_BYTES, LOAD_ADDRESS_IMMEDIATE, LOAD_IMMEDIATE,
                    PUSH_RETURN_PC, PUSH_SR, PUSH_STACK_LONG, PUSH_WORD_IMMEDIATE, RTS,
                    SET_USER_STACK, STORE_A5_ABSOLUTE, TRAP_BIOS, TRAP_XBIOS)

# ---- the band this battery owns, inside the one `staging.py` describes --------------------------
# Declared as ONE span with its own base, the shape `test/isr.py` uses, so that a battery can say
# which part of the staging band is its own: the pointer-argument batteries fill it from the bottom
# (Getmpb's and Protobt's buffers at +0, Keytbl's tables at +0x100..+0x300) and the interrupt
# handlers' trampolines take the top (+0xd00). This sits between them.
TRAP_BAND = staging.SCRATCH + 0x800
TRAP_BAND_BYTES = 0x400
assert TRAP_BAND + TRAP_BAND_BYTES <= staging.SCRATCH + staging.SCRATCH_BYTES

CALLER_AT = TRAP_BAND               # the caller above: a hand-built frame, and a jump through (sp)
TRAP_CALLER_AT = TRAP_BAND + 0x40   # ...and the same caller through a real `trap #13`
USER_CALLER_AT = TRAP_BAND + 0x80   # ...and one that enters as a USER-mode caller does
ROUTINE_AT = TRAP_BAND + 0xc0       # a routine of the case's own, for the INDIRECT entry
WITNESS_AT = TRAP_BAND + 0x100      # ...and what that routine records about its own entry

# THE USER-MODE CALLER'S STACK IS NOT IN THAT BAND, and it cannot be. Under the `move.l usp,sp` arm
# the dispatcher runs on the USER stack — its `jsr` plants ITS OWN return address there — so that
# memory holds the address of whichever dispatcher ran, which is the one thing the two sides of the
# second differential are meant to differ in. A machine stack is not output, and the harness already
# has a band it drops for exactly that reason, so the case puts its user stack inside it: far enough
# below `emu.STACK_TOP` that the run's own supervisor frame (a few dozen bytes) never reaches it,
# and far enough above `emu.STACK_GUARD_LO` that the user caller's own pushes stay inside.
USER_STACK_BELOW_TOP = 0x800
USER_STACK_AT = emu.STACK_TOP - USER_STACK_BELOW_TOP
USER_STACK_BYTES = 0x40         # ...and how much of it the case's own words and sentinel may take
# Headroom BELOW the user stack for what the run pushes onto it: the dispatcher's own `jsr` return
# address and everything the called routine pushes under that. Both are the oracle's scratch rather
# than output, so they must land inside the dropped band and not below it.
USER_STACK_HEADROOM = 0x100

# Said as assertions rather than as the paragraph above, because "far enough" is the kind of claim
# that stops being true when a constant on either side moves and nothing reads the prose. Below: the
# pushes stay inside the dropped band. Above: the run's own SUPERVISOR frame comes DOWN from
# `emu.STACK_TOP` and may legitimately reach `emu.STACK_SCRATCH` bytes into it, which is exactly the
# depth this stack must stay clear of.
assert emu.STACK_GUARD_LO + USER_STACK_HEADROOM <= USER_STACK_AT
assert USER_STACK_AT + USER_STACK_BYTES <= emu.STACK_TOP - emu.STACK_SCRATCH

# What the staged routine records, in the order it stores them. Named offsets rather than three
# addresses, so the routine's stores and the assertions about them index one layout.
WITNESS_A5 = WITNESS_AT                     # long: A5 as the dispatcher handed it over
WITNESS_SAVPTR = WITNESS_AT + 4             # long: savptr DURING the call — i.e. the frame's depth

# The register file BOTH SIDES are entered with, and it covers every register on purpose: a
# transcription is held to the whole file it leaves (`RomBench.measure_transcription`), and a
# register nobody named would enter as 0 on both sides and agree for that reason alone.
#
# The value is distinctive, per register, and is not a plausible address in this machine — an
# address register the dispatcher hands to a `jsr` is one the case chose, and every other one is
# carried rather than dereferenced.
ENTRY_SEED = 0xC0FFEE00
ENTRY_REGS = {name: ENTRY_SEED + index for index, name in enumerate(emu.REPORTED_REGS)}

# ...and what the staged routine leaves in the registers the dispatcher does NOT give back, so that
# a reconstruction which tidied one of them away has something to redden against.
SCRIBBLE = 0x5CB1BB00

# The SR a USER-mode caller's exception frame carries: supervisor bit clear, the oracle's own
# interrupt mask, condition codes clear. It is what makes the dispatcher take its `move.l usp,sp`
# arm, and it is the only thing that does.
USER_MODE_SR = 0x0700

# A `pea (d16,pc)` counts its displacement from the EXTENSION WORD, which is two bytes into the
# instruction — so a stub naming a label ahead of itself measures from there.
PEA_EXTENSION_WORD_AT = 2
WORD_BYTES = 2                          # ...the width of one pushed argument, and of the number

# ---- what a staged caller COSTS, which every row of this battery is quoted net of ----------------
# A handler can only be entered through a caller, so a Tier 3 row for the dispatcher is a WHOLE CALL
# and the caller's own cost sits in both of its columns. `rom_bench.Measurement` takes it off BOTH,
# so these are the numbers that decide what the ratio is about — and they are MEASURED, through a
# null dispatcher, by `test_bios_trap.py::test_each_caller_shape_costs_what_the_rows_are_net_of`
# rather than read off the 68000's tables.
#
# THREE SHAPES, because there are three callers below and they do not cost the same. A supervisor
# caller pushes each argument word itself; a user-mode caller's words are already on the user stack
# (`user_stack`), so its cost does not move with them, and its two extra instructions — the `movea.l`
# and the `move.l a0,usp` that plant that stack — are its own.
SUPERVISOR_CALLER_COST = (7, 106)       # `caller(function)`, no arguments
ARGUMENT_WORD_COST = (1, 12)            # ...and each argument word above that: `move.w #imm,-(sp)`
USER_CALLER_COST = (8, 108)             # `user_mode_caller(function)`, whatever its arguments are


def caller_cost(args=(), user_mode=False):
    """The `(instructions, cycles)` one of the callers below costs, for the shape a case staged."""
    if user_mode:
        return USER_CALLER_COST
    insns, cycles = SUPERVISOR_CALLER_COST
    per_insn, per_cycle = ARGUMENT_WORD_COST
    return (insns + len(args) * per_insn, cycles + len(args) * per_cycle)


# Which registers the dispatcher's `movem` pair promises the caller back, and which it does not.
# THE SECOND HALF IS AS MUCH A FACT AS THE FIRST — it is `docs/on-target-execution.md`'s d2/a2 class,
# where GCC believed a TOS trap preserved registers the ROM has never preserved.
PRESERVED = ("d3", "d4", "d5", "d6", "d7", "a3", "a4", "a5", "a6")
NOT_PRESERVED = ("d0", "d1", "d2", "a0", "a1", "a2")

# ...and the six split by WHAT THE CALLER ACTUALLY RECEIVES, which is not the same question. Five of
# them are the called routine's values, arriving untouched — that is the pass-through the trap's ABI
# leaves open. A1 is the exception: the dispatcher's EPILOGUE reloads it from `savptr` to unwind the
# frame, so whatever the routine left in A1 is gone by the `rte` and the caller gets the save area's
# top instead. Measured, not assumed: the first shape of this battery asserted the scribble for all
# six and A1 came back as $93a.
PASSED_THROUGH = ("d0", "d1", "d2", "a0", "a2")
DISPATCHER_SCRATCH = ("a1",)
# ...and the split is EXHAUSTIVE, which is the half a reader cannot see from two tuples: a register
# dropped from both lists would simply stop being asserted about, and the battery would go on
# passing over five of the six the ROM does not preserve.
assert set(PASSED_THROUGH) | set(DISPATCHER_SCRATCH) == set(NOT_PRESERVED)
assert not set(PASSED_THROUGH) & set(DISPATCHER_SCRATCH)


def word(value):
    """A 68000 operand word, and `longword` below it — public because the battery assembles stubs of
    its own out of the same opcode constants."""
    return struct.pack(">H", value & 0xFFFF)


def longword(value):
    return struct.pack(">I", value & 0xFFFFFFFF)


def caller(function, args=()):
    """The staged caller at `CALLER_AT`: push the arguments and the function number, build the
    exception frame by hand, and enter the handler the case put at `abi.FIRST_ARG`.

    `args` are the argument WORDS in the order the C prototype has them, and they are pushed in
    reverse, which is what leaves the first one directly above the return address the `jsr` inside
    the dispatcher will plant — the frame every other battery in this project pokes directly.
    """
    pushed_words = len(args) + 1                        # the arguments, and the function number
    # Where the handler longword is, measured from the stack pointer at the `move.l` that reads it:
    # everything this stub has pushed by then — the caller's words and the exception frame — and
    # then the run's own sentinel slot, which `abi.FIRST_ARG` is one longword above.
    handler_at = (abi.FIRST_ARG - emu.STACK_TOP
                  + WORD_BYTES * pushed_words + addrs.TRAP_EXCEPTION_FRAME_BYTES)
    body = b"".join(PUSH_WORD_IMMEDIATE + word(value) for value in reversed(args))
    body += PUSH_WORD_IMMEDIATE + word(function)
    tail = PUSH_SR + PUSH_STACK_LONG + word(handler_at) + RTS
    body += PUSH_RETURN_PC + word(len(tail) + PEA_EXTENSION_WORD_AT)
    return body + tail + DROP_STACK_BYTES + word(WORD_BYTES * pushed_words) + RTS


def trap_caller(function, args=(), opcode=TRAP_BIOS):
    """...and the same caller through a REAL `trap`, which is the control `caller()` is checked
    against. Reaches whatever the machine's own vector table holds, so it can only ever run the
    ORIGINAL — which is exactly what makes it the control."""
    pushed_words = len(args) + 1
    body = b"".join(PUSH_WORD_IMMEDIATE + word(value) for value in reversed(args))
    body += PUSH_WORD_IMMEDIATE + word(function) + opcode
    return body + DROP_STACK_BYTES + word(WORD_BYTES * pushed_words) + RTS


def user_mode_caller(function, args=()):
    """A caller that enters the dispatcher the way a USER-mode program does.

    The arguments are on the USER stack and the frame's SR says the caller was not supervisor, which
    is the whole of what the dispatcher's `btst #13` / `move.l usp,sp` arm reads. Nothing else in
    this project ever executes that arm: every other case is a supervisor caller, because the oracle
    enters every run in supervisor mode.

    The frame is still built by hand — a real `trap` from user mode would reach the ROM's vector and
    could never run our own transcription — so the SR word is an immediate rather than `move.w sr`.
    """
    pushed_words = len(args) + 1
    prologue = LOAD_ADDRESS_IMMEDIATE + longword(USER_STACK_AT) + SET_USER_STACK
    # Nothing of the CALLER's is on the supervisor stack here — its words are on the user stack —
    # so the only thing between the stack pointer and the sentinel slot is the exception frame.
    handler_at = abi.FIRST_ARG - emu.STACK_TOP + addrs.TRAP_EXCEPTION_FRAME_BYTES
    tail = PUSH_WORD_IMMEDIATE + word(USER_MODE_SR) + PUSH_STACK_LONG + word(handler_at) + RTS
    prologue += PUSH_RETURN_PC + word(len(tail) + PEA_EXTENSION_WORD_AT)
    # `back` runs in USER mode on the user stack, where the case has left the same words a
    # supervisor caller pushes — and, above them, the sentinel this `rts` returns to.
    return prologue + tail + DROP_STACK_BYTES + word(WORD_BYTES * pushed_words) + RTS


def user_stack(function, args=()):
    """What the user-mode caller's stack holds: its argument words, its function number, and the
    sentinel return address the `rts` after the call pops."""
    words = b"".join(word(value) for value in (function, *args)) + longword(emu.SENTINEL)
    assert len(words) <= USER_STACK_BYTES, "the user stack's words no longer fit the band above it"
    return {USER_STACK_AT: words}


def staged_routine():
    """A routine of the case's own, for the dispatch table's INDIRECT entry to reach.

    It is the only way to watch the dispatcher call something whose body the case wrote, and it
    records the two things about the call that have no other surface: the A5 the dispatcher entered
    it with (which the `suba.l a5,a5` is supposed to have zeroed) and the savptr the dispatcher left
    installed (which says a frame was pushed, and how deep). Then it scribbles on every register the
    dispatcher does NOT restore, so that the pass-through is a compared fact rather than a belief.
    """
    body = STORE_A5_ABSOLUTE + longword(WITNESS_A5)
    body += COPY_LONG_ABSOLUTE + longword(addrs.SYSVAR_SAVPTR) + longword(WITNESS_SAVPTR)
    for index, name in enumerate(NOT_PRESERVED):
        body += LOAD_IMMEDIATE[name] + longword(SCRIBBLE + index)
    return body + RTS


# The routine is staged at `ROUTINE_AT` and writes its witness at `WITNESS_AT`, so its body has to
# FIT between them — a register added to `NOT_PRESERVED` lengthens it by six bytes, and the first
# byte past the gap would land on the witness it is about to write and be read back as one.
assert ROUTINE_AT + len(staged_routine()) <= WITNESS_AT


def scribbled(name):
    """What `staged_routine` leaves in one of the registers the dispatcher does not preserve."""
    return SCRIBBLE + NOT_PRESERVED.index(name)


def save_area_top():
    """Where `savptr` stands in the captured snapshot — the top of the BIOS's register-save area.

    Read out of the machine rather than written down: it is a system variable the boot sets, and a
    case that spelt it would be describing some other machine the day the snapshot moved.
    """
    from harness import BASE_IMAGE

    return int.from_bytes(bytes(BASE_IMAGE[addrs.SYSVAR_SAVPTR:addrs.SYSVAR_SAVPTR + 4]), "big")


SAVE_AREA_TOP = save_area_top()
# One nesting level's frame, and where the two halves of it are. The dispatcher pushes the SR word
# and the return PC first and the ten registers below them, so the frame runs DOWNWARDS from the
# save area's top and the exception frame is at its high end.
FRAME_AT = SAVE_AREA_TOP - addrs.TRAP_SAVE_FRAME_BYTES
SAVED_SR_AT = SAVE_AREA_TOP - 2
SAVED_PC_AT = SAVE_AREA_TOP - addrs.TRAP_EXCEPTION_FRAME_BYTES


def _table_count(table):
    """A dispatch table's own count word, read out of the mapped ROM.

    The out-of-range case needs a function number the table does not have, and the honest way to
    name one is "the count itself" — read from the table rather than typed, so a ROM whose table
    grew would move the case with it instead of quietly testing an in-range number.
    """
    from harness import BASE_IMAGE

    return int.from_bytes(bytes(BASE_IMAGE[table:table + addrs.TRAP_TABLE_COUNT_BYTES]), "big")


BIOS_FUNCTION_COUNT = _table_count(addrs.BIOS_FUNCTION_TABLE)

# What the INDIRECT case puts in the machine: the dispatch table's entry 4 has bit 31 set over the
# RAM vector `hdv_rw`, so pointing that vector at a routine of the case's own is what makes the
# dispatcher call it. Shared with the battery, which makes several claims over the same staging.
INDIRECT = {addrs.HDV_RWABS: longword(ROUTINE_AT), ROUTINE_AT: staged_routine()}


def _case(name, symbol, stub_at, stub, staged, cost):
    """One case in the shape the battery and `bench/tier3.py` both read.

    The tuple is `VERIFIED_CASES`' with three fields added — the blob SYMBOL our side is entered
    through, the entry address, which for a handler is the staged CALLER rather than the routine,
    and what that caller COSTS — because a transcription is measured through a different relation
    than a C core (`RomBench.measure_transcription`), the registry has to carry which, and the
    caller's cost sits in both columns of the row and comes off both (`caller_cost` above).

    THE ROM ENTRY THE CASE POKES IS DERIVED FROM THE SYMBOL, not named beside it: they are one fact
    spelt twice — `bios_trap13` is `addrs.BIOS_TRAP13` — and a case that named the XBIOS entry under
    the BIOS symbol would be comparing two different handlers with nothing able to say so.
    """
    staged_pokes = {stub_at: stub, abi.FIRST_ARG: longword(getattr(addrs, symbol.upper()))}
    staged_pokes.update(staged)
    return (name, symbol, stub_at, dict(ENTRY_REGS), staged_pokes, cost)


def _supervisor_case(name, symbol, function, args=(), staged=None):
    """...as a SUPERVISOR caller stages it, which is every case but one."""
    return _case(name, symbol, CALLER_AT, caller(function, args), staged or {}, caller_cost(args))


def _user_mode_case(name, symbol, function, staged=None):
    """...and as a USER-mode caller does: its argument words are on the user stack rather than
    pushed by the stub, so the stack it needs is part of the case and its cost does not move with
    the arguments."""
    return _case(name, symbol, USER_CALLER_AT, user_mode_caller(function),
                 {**(staged or {}), **user_stack(function)}, caller_cost(user_mode=True))


# EVERY CASE THIS BATTERY VERIFIES, and the register `bench/tier3.py` prices. It is the dispatcher's
# counterpart of `test_boot_snapshot.VERIFIED_CASES`, kept here rather than there because those are
# C cores proved by `harness.differential` and these are one m68k transcription proved by the second
# differential of Tier 3's numerator — two different relations, and a list that mixed them would
# have to say which for every row anyway.
CASES = (
    _supervisor_case("BIOS Drvmap, no arguments", "bios_trap13", addrs.BIOS_DRVMAP_FN),
    _supervisor_case("BIOS Kbshift, one argument word", "bios_trap13", addrs.BIOS_KBSHIFT_FN,
                     args=(0xffff,)),
    _supervisor_case("a function number past the table's count", "bios_trap13",
                     BIOS_FUNCTION_COUNT),
    _supervisor_case("the INDIRECT table entry, through hdv_rw", "bios_trap13",
                     addrs.BIOS_RWABS_FN, staged=INDIRECT),
    _user_mode_case("a USER-mode caller, arguments on the user stack", "bios_trap13",
                    addrs.BIOS_RWABS_FN, staged=INDIRECT),
    _supervisor_case("XBIOS Logbase, the other table", "xbios_trap14", addrs.XBIOS_LOGBASE_FN),
)

# ...and how a row names itself in the Tier 3 table, per entry. Keyed by the blob symbol, because
# that is what says which of the two exception entries the case came in through.
LABELS = {"bios_trap13": "BIOS trap #13", "xbios_trap14": "XBIOS trap #14"}
