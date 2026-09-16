"""How a case enters an INTERRUPT HANDLER, and how it stages the routines one calls.

The trap routines every other battery here proves are CALLED: the dispatcher leaves a return address
at `(sp)`, the routine ends in `rts`, and `emu.run`'s sentinel is waiting there. An interrupt handler
is entered by the MACHINE. Nothing called it, it takes no argument, it returns no result, and it
ends in `rte` — which pops a STATUS REGISTER and a PC out of the exception frame the 68000's own
exception processing pushed. Enter one at its first instruction with the frame a trap routine has
and the `rte` resumes at whatever the sentinel longword happens to spell.

So a case stages the frame, and this module is the one place that says how.

THE ENTRY IS A TRAMPOLINE, two instructions long and planted in the same dead RAM a case stages
anything else in:

    movea.l #<frame>,sp             ; where the frame is
    jmp     <handler>.l

`emu.run` forces A7 to `emu.STACK_TOP` and plants the sentinel there, and neither can be asked for
anything else — so the frame's own placement is the trampoline's first instruction, and the frame is
POKED rather than pushed. Six bytes: the SR the interrupt was taken at, and `emu.SENTINEL` as the PC
it resumes at, so the handler's own `rte` ends the run exactly where an `rts` ends a trap routine's.

WHERE THE FRAME GOES IS THE CASE'S CHOICE, and there are two right answers:

* `FRAME_IN_STACK_BAND` — just under `emu.STACK_TOP`, so the frame AND everything the handler pushes
  below it land in the band `harness.diff_spans()` already drops. That is right for the three
  handlers that do not touch their own frame (they `movem` their registers over it and `rte`), and
  it costs the case nothing: no exclusion, no staging, and the stray-write guard treats the pushes
  as the stack they are.
* `STAGED_FRAME` — in the staging band, i.e. in COMPARED image. The HBL handler's whole body is a
  store into its own frame's SR word, so its differential needs the frame where the byte diff can
  see it; the two bytes it pushes its D0 into are then the case's to exclude, and nothing else.

WHAT THE HANDLERS CALL is staged the same way `test_xbios_supexec.py` stages Supexec's routine, and
for the same reason: `swv_vec`, `_vblqueue`'s slots, `scr_dump`, `etv_timer` and KBDVECS' two service
vectors are longwords in RAM, so what runs there is an INPUT of the handler rather than a fact about
the ROM. Each staged routine is a PAIR — the 68000 stub the oracle jumps to, and a Python function
with the same effect for the candidate, which reaches it through `include/staged_call.h`'s hook. The
hook dispatches BY ADDRESS, so a decoy staged beside the named routine means something on both
sides.
"""
import ctypes
import struct
from collections import namedtuple

import abi
import case
import staging
import test_xbios_supexec as supexec
import trap
from harness import BASE_IMAGE, _lib, addrs, emu

# ---- the band this module and its batteries stage into -------------------------------------------
# The top of `staging.SCRATCH`, which the other batteries fill from the bottom (Getmpb's parameter
# block and Protobt's boot sector at +0, Keytbl's tables at +0x100, Supexec's decoys as far as
# +0xc06). Declared as one span so a battery can say which part of it is its own, and covered by
# `test_boot_snapshot.py`'s claim that the whole staging band is dead RAM in this capture.
ISR_BAND = staging.SCRATCH + 0xD00
ISR_BAND_BYTES = 0x300
assert ISR_BAND + ISR_BAND_BYTES <= staging.SCRATCH + staging.SCRATCH_BYTES
# ...and clear of the two bands BELOW it, which is the bound a comment was holding: a collision
# there would corrupt a trampoline for BOTH cores at once — green on the byte diff, because both
# read the same wrong image. The trap dispatcher's battery owns [+0x800, +0xc00) (`test/trap.py`),
# and Supexec's decoys sit at +0x800, +0xa00 and +0xc00 with a stub apiece above them.
assert trap.TRAP_BAND + trap.TRAP_BAND_BYTES <= ISR_BAND
assert (supexec.STUB_AT + max(supexec.DECOY_ALTERNATIVES) + supexec.DECOY_STUB_BYTES
        <= ISR_BAND), "Supexec's decoys reach into the band this module stages in"

# TWO TRAMPOLINES PER HANDLER, at a fixed address apiece: `bench/tier3.py` needs to get from the
# entry a case runs back to the ROM routine the row is about, and a fixed slot is what lets it.
#
# The DIRECT one is what a Tier 1 case and a C row use: only the ORACLE runs it (our core is a C
# function the harness calls), so it may name its handler outright and it writes nothing at all.
# The SHARED one is `measure_transcription`'s, where BOTH sides run it over ONE image and have to
# reach different handlers — the ROM's and our own `src/bios/isr.S` stub — so it reads its target
# from `abi.FIRST_ARG`, the one longword the two runs may legitimately differ in.
TRAMPOLINE_STRIDE = 0x10
SHARED_TRAMPOLINE_BASE = ISR_BAND + 0x40
# ...and the HBL's frame, which is the one that has to sit in compared image (see the docstring).
STAGED_FRAME = ISR_BAND + 0x80
# Everything above is a battery's to lay out: stubs, markers, queues.
STUB_BAND = ISR_BAND + 0xA0

# The default: the frame in the band the diff drops, with the handler's own pushes below it. It sits
# `emu.STACK_SCRATCH` deep inside the region the stray-write guard calls a legitimate frame.
FRAME_IN_STACK_BAND = emu.STACK_TOP - addrs.EXCEPTION_FRAME_BYTES

# What the interrupted code was running at, as the frame's SR word: supervisor, interrupt mask 3.
# Only the HBL reads it, and its battery chooses its own; for the other three it is an input nothing
# looks at, declared rather than left at zero so that a handler which started reading it would show.
RESUME_SR = 0x2300

Handler = namedtuple("Handler", "name constant entry vector")

# THE FOUR LIVE VECTORS, and `vector` is a claim rather than a label: `test_the_vector_table_still
# _points_at_this_handler` reads that slot out of the captured snapshot, so a handler reconstructed
# at an address the machine does not dispatch to reddens instead of proving something about nothing.
# `constant` is the `addrs.h` name of the ROM address, and the C core's symbol is that name LOWER
# CASED — the convention `bench/tier3.py` already derives every trap routine's symbol by, so an ISR
# row needs no second spelling of either.
HANDLERS = (
    Handler("HBL", "ISR_HBL", addrs.ISR_HBL, addrs.VECTOR_HBL),
    Handler("VBL", "ISR_VBL", addrs.ISR_VBL, addrs.VECTOR_VBL),
    Handler("timer C", "ISR_TIMER_C", addrs.ISR_TIMER_C, addrs.VECTOR_TIMER_C),
    Handler("ACIA", "ISR_ACIA", addrs.ISR_ACIA, addrs.VECTOR_ACIA),
)
for _handler in HANDLERS:
    assert getattr(addrs, _handler.constant) == _handler.entry
HANDLER_AT = {handler.entry: handler for handler in HANDLERS}
TRAMPOLINE_AT = {handler.entry: ISR_BAND + index * TRAMPOLINE_STRIDE
                 for index, handler in enumerate(HANDLERS)}
SHARED_TRAMPOLINE_AT = {handler.entry: SHARED_TRAMPOLINE_BASE + index * TRAMPOLINE_STRIDE
                        for index, handler in enumerate(HANDLERS)}
# ...and the way back, which is what `bench/tier3.py` reads: a row's entry is a trampoline, and the
# function it is a row ABOUT is the handler that trampoline jumps to. Two maps rather than one,
# because the two entries mean different things to that file — a direct trampoline is a C row and a
# shared one is a TRANSCRIPTION row, measured through the other relation.
HANDLER_OF_TRAMPOLINE = {at: HANDLER_AT[entry] for entry, at in TRAMPOLINE_AT.items()}
HANDLER_OF_SHARED_TRAMPOLINE = {at: HANDLER_AT[entry]
                                for entry, at in SHARED_TRAMPOLINE_AT.items()}
# ...and the band's INTERNAL layout, asserted rather than left to the offsets looking plausible. A
# fifth `Handler` row would otherwise put a trampoline on top of `STAGED_FRAME` — the HBL's frame in
# COMPARED image — and the collision would surface as an unreadable byte diff rather than here.
assert ISR_BAND + len(HANDLERS) * TRAMPOLINE_STRIDE <= SHARED_TRAMPOLINE_BASE
assert SHARED_TRAMPOLINE_BASE + len(HANDLERS) * TRAMPOLINE_STRIDE <= STAGED_FRAME
assert STAGED_FRAME + addrs.EXCEPTION_FRAME_BYTES <= STUB_BAND

# THE C CORE'S NAME AND THE STUB'S, which are two symbols for one handler: `isr_vbl` is the handler
# as C, which Tier 1 proves, and `isr_vbl_entry` is `src/bios/isr.S` — the ROM's own entry sequence
# around it, which is what a shipped ROM installs in the vector. The suffix is the whole of the
# convention, so neither `bench/tier3.py` nor a battery spells either name a second time.
STUB_SUFFIX = "_entry"


def stub_symbol(constant):
    """The `src/bios/isr.S` symbol for one handler, from its `addrs.h` name."""
    return f"{constant.lower()}{STUB_SUFFIX}"

KBDVECS_BYTES = addrs.KBDVECS_LONGWORDS * addrs.VECTOR_BYTES

# The 68000 opcode words the stubs below are assembled from, named rather than spelt at the site —
# a stub is the only thing in a case that is machine code, so an unnamed word here is a bug nothing
# but a hand decode would find.
MOVEA_L_IMMEDIATE_SP = 0x2E7C       # `movea.l #<long>,sp`
JMP_ABSOLUTE_LONG = 0x4EF9          # `jmp <long>.l`
PUSH_LONG_ABSOLUTE = 0x2F39         # `move.l <long>.l,-(sp)`
RTS_WORD = 0x4E75                   # ...the `rts` the push above is jumped through
MOVE_B_IMMEDIATE_ABSOLUTE = 0x13FC  # `move.b #<byte>,<long>.l`  (the immediate is a WORD)
MOVE_W_IMMEDIATE_ABSOLUTE = 0x33FC  # `move.w #<word>,<long>.l`
MOVE_L_IMMEDIATE_ABSOLUTE = 0x23FC  # `move.l #<long>,<long>.l`
MOVE_W_FRAME_ABSOLUTE = 0x33EF      # `move.w <d16>(sp),<long>.l`
ARGUMENT_AT_4_SP = 4                # ...and the displacement a pushed word sits at, past the `jsr`
RTE = b"\x4e\x73"
RTS = b"\x4e\x75"

# What the two trampoline instructions cost on the ORACLE's side, and nothing on ours: our C is
# entered directly by `run_bench`. `bench/tier3.py` takes it off the ORIGINAL's column so that an
# ISR row is the handler's own cost rather than the handler plus the staging that reached it.
# The 68000's book figures — `movea.l #imm32,An` is 12 cycles and `jmp (xxx).L` is 12 — and
# `test_bios_hbl.py::test_the_staged_entry_costs_what_tier_3_takes_off_the_original` measures the
# whole minimal run against them rather than leaving the pair asserted here.
STAGED_ENTRY_COST = (2, 24)         # instructions, 68000 cycles

# ...and what the SHARED trampoline costs, which is the other subtraction: a transcription row is
# entered at it on BOTH sides, so `bench/tier3.py` passes this as `shared_entry` and `Measurement`
# takes it off both columns. Measured the same way, by the probe beside the one above.
SHARED_ENTRY_COST = (3, 56)

# How far a handler case may run before the oracle refuses it. The default covers every case these
# batteries stage; the cursor inversion's ZERO-count arm is 65,536 passes and raises it (see
# `test_bios_vbl.py`), and the ACIA's own negative control lowers it to a few thousand.
DEFAULT_MAX_INSNS = 200_000


def trampoline_bytes(frame, target):
    """The two instructions that put the frame where `target` will `rte` through it, and jump."""
    return struct.pack(">HIHI", MOVEA_L_IMMEDIATE_SP, frame, JMP_ABSOLUTE_LONG, target)


def shared_trampoline_bytes(frame):
    """...and the three that do the same for a run whose HANDLER is not the same on both sides.

    `measure_transcription` runs the original and our `src/bios/isr.S` stub over ONE image and hands
    each its own entry through `abi.FIRST_ARG` — the longword `emu.run` leaves as the case poked it
    and `emu.run_bench` writes `arg0` over, inside the band `harness.diff_spans()` drops. So the
    target is READ from there rather than assembled in, exactly as `test/trap.py`'s staged caller
    reads the dispatcher it enters.

    IT PUSHES AND RETURNS rather than loading an address register and jumping, and that is the whole
    reason the push comes after the stack pointer is placed: an address register would still be
    holding OUR entry when the handler gave it back, where the original's held the ROM's, and the
    transcription relation compares the whole register file. The push lands four bytes below the
    frame instead, which is why a transcription case's frame belongs in the band the diff drops.
    """
    return struct.pack(">HIHIH", MOVEA_L_IMMEDIATE_SP, frame,
                       PUSH_LONG_ABSOLUTE, abi.FIRST_ARG, RTS_WORD)


def frame_bytes(resume_sr):
    """The 68000 group-1/2 exception frame: the SR to restore, then the PC to resume at.

    The PC is always `emu.SENTINEL`, because that is what ENDS the run — the same address `emu.run`
    plants for a trap routine's `rts`, reached here through the handler's own `rte`.
    """
    frame = bytearray(addrs.EXCEPTION_FRAME_BYTES)
    struct.pack_into(">H", frame, addrs.EXCEPTION_FRAME_SR, resume_sr)
    struct.pack_into(">I", frame, addrs.EXCEPTION_FRAME_PC, emu.SENTINEL)
    return bytes(frame)


def entry_pokes(entry, frame=FRAME_IN_STACK_BAND, resume_sr=RESUME_SR):
    """Everything staging ONE handler's entry: BOTH trampolines, the frame they point at, and the
    handler longword the shared one reads.

    Both are staged on every case, and deliberately: a Tier 1 case and its transcription row are the
    same spec (`registered` and `transcribed` below), so one image shape serves both and neither can
    come to describe a machine the other was not run over. The unused one is fourteen bytes of dead
    RAM that nothing branches to.
    """
    return {TRAMPOLINE_AT[entry]: trampoline_bytes(frame, entry),
            SHARED_TRAMPOLINE_AT[entry]: shared_trampoline_bytes(frame),
            abi.FIRST_ARG: struct.pack(">I", entry),
            frame: frame_bytes(resume_sr)}


def case_pokes(entry, frame=FRAME_IN_STACK_BAND, resume_sr=RESUME_SR, routines=None, pokes=None):
    """EVERYTHING one handler case stages: its entry, the routines it plants, and its own pokes.

    One expression, because `run` and `registered` must stage the identical image — a registered
    case that differed from the case a battery proved would carry a Tier 3 ratio about a run nobody
    verified, which is exactly what deriving the rows from `VERIFIED_CASES` exists to prevent.
    """
    return {**entry_pokes(entry, frame, resume_sr),
            **{at: code for at, (code, _effect) in (routines or {}).items()},
            **(pokes or {})}


# A case SPEC is a dict in `run`'s own keyword vocabulary — `entry`, and any of `frame`,
# `resume_sr`, `routines`, `pokes`, `regs`, `psg_seed`, `io_seed` — plus the `name` a registry row
# needs. The two functions below turn ONE spec into the two things this project asks of a case: the
# `VERIFIED_CASES` row Tier 3 and the snapshot mask read, and the differential that proves it. One
# object, so a registered row cannot come to describe a run nobody verified.
_SPEC_KEYS = ("frame", "resume_sr", "routines", "pokes", "regs", "psg_seed", "io_seed")


def registered(spec):
    """One `test_boot_snapshot.VERIFIED_CASES` row for a handler case.

    Its ENTRY is the trampoline, because that is what a case runs; `HANDLER_OF_TRAMPOLINE` is how
    `bench/tier3.py` gets from it back to the ROM routine the row is about.
    """
    entry = spec["entry"]
    return (spec["name"], TRAMPOLINE_AT[entry],
            {**DIRTY_REGISTERS, **spec.get("regs", {})},
            case_pokes(entry, spec.get("frame", FRAME_IN_STACK_BAND),
                       spec.get("resume_sr", RESUME_SR), spec.get("routines"), spec.get("pokes")),
            spec.get("psg_seed"), spec.get("io_seed"))


def run_spec(spec, glue, **overrides):
    """...and the DIFFERENTIAL of that same spec."""
    return run(spec["entry"], glue,
               **{key: spec[key] for key in _SPEC_KEYS if key in spec}, **overrides)


# The TRANSCRIPTION row's shape, which is `bench/tier3.py`'s other relation: `trap.CASES`' tuple with
# the handler's ROM address added, because an ISR case is entered at a trampoline and the row is
# about the handler that trampoline reaches.
Transcription = namedtuple("Transcription",
                           "name symbol caller regs pokes psg_seed io_seed shared_entry handler")


def transcribed(spec):
    """One whole-handler TRANSCRIPTION case from the same spec a battery registers.

    `registered` above prices the C CORE against the ROM; this prices `src/bios/isr.S` — the stub a
    shipped ROM installs in the vector, brackets and all — through `RomBench.measure_transcription`,
    which holds it to the whole register file the original left as well as to the image and the chip.
    Both are built from the one spec, so the two rows are two relations over one verified run.
    """
    entry = spec["entry"]
    frame = spec.get("frame", FRAME_IN_STACK_BAND)
    # The shared trampoline pushes its target four bytes below the frame, and the two sides push
    # DIFFERENT targets — so those bytes have to be ones the comparison drops. A staged frame in
    # compared image would surface as an unreadable diff at `frame - 4` instead of here.
    from harness import in_diff

    assert not in_diff(frame - addrs.VECTOR_BYTES), (
        f"a transcription case's frame at {frame:#x} leaves the shared trampoline's push in "
        f"COMPARED image, where the two sides legitimately differ — use the default frame")
    return Transcription(
        spec["name"], stub_symbol(HANDLER_AT[entry].constant), SHARED_TRAMPOLINE_AT[entry],
        {**DIRTY_REGISTERS, **spec.get("regs", {})},
        case_pokes(entry, frame, spec.get("resume_sr", RESUME_SR), spec.get("routines"),
                   spec.get("pokes")),
        spec.get("psg_seed"), spec.get("io_seed"), SHARED_ENTRY_COST, HANDLER_AT[entry])


# ---- the LITERAL TRANSCRIPTION, word for word against the ROM -------------------------------------
# `src/bios/isr.S` carries the ROM's own entry and exit sequences, and this is what says so: the
# assembled words are read back out of the cross-compiled blob and compared with the ROM's own. The
# Tier 3 transcription row proves the stub BEHAVES like the original over a handful of cases; this
# proves the instructions ARE the original's everywhere the stub is not calling our C.
#
# THE OFFSETS ARE THE `.S`'s OWN LAYOUT, and they are meant to be: a stub that grew an instruction is
# a transcription somebody changed, and the right place for that to surface is here.
LiteralSpan = namedtuple("LiteralSpan", "at rom_at length excused")

# What an ASSEMBLER may legitimately spell differently, per span, by byte offset within it. Each
# entry is a claim that the two words are the same instruction; `assert_the_stub_is_the_rom_s_bytes`
# requires an excused word to actually DIFFER, so an excuse that stopped being needed reds instead of
# standing for ever.
_BRANCH_TO_OUR_OWN_BODY = ("a branch displacement, which measures to the end of OUR body — the "
                           "`jsr` into the C core is not the length of the ROM's inline one")
_ANDI_ENCODING = ("GNU as spells `and.w #imm,Dn` as ANDI ($0240); the ROM's assembler chose AND "
                  "with an immediate source ($c07c). Same operation, same size, same 8 cycles")
_SIGN_EXTENDED_IO_ADDRESS = ("the ROM spells the MFP's register sign-extended ($fffffa11) where "
                             "`addrs.h` names it $fffa11 — one address on a 24-bit bus")

LITERAL_SPANS = {
    "ISR_HBL": (LiteralSpan(0x00, addrs.ISR_HBL, 0x16, {0x06: _ANDI_ENCODING}),),
    "ISR_VBL": (LiteralSpan(0x00, addrs.ISR_VBL, 0x14, {0x0E: _BRANCH_TO_OUR_OWN_BODY}),
                LiteralSpan(0x20, addrs.ISR_VBL_RELEASE, 0x0C, {})),
    "ISR_TIMER_C": (LiteralSpan(0x00, addrs.ISR_TIMER_C, 0x12, {0x0C: _BRANCH_TO_OUR_OWN_BODY}),
                    LiteralSpan(0x1E, addrs.ISR_TIMER_C_ACKNOWLEDGE, 0x0E,
                                {0x08: _SIGN_EXTENDED_IO_ADDRESS})),
    "ISR_ACIA": (LiteralSpan(0x00, addrs.ISR_ACIA, 0x04, {}),
                 LiteralSpan(0x10, addrs.ISR_ACIA_RESTORE, 0x06, {})),
}
assert set(LITERAL_SPANS) == {handler.constant for handler in HANDLERS}

WORD_BYTES = 2
_BENCH = None


def _blob():
    """The cross-compiled cores, loaded once per process.

    Lazily, because a battery must still IMPORT when the blob has not been built — `make test`
    builds it first (kit.mk's `test: $(BENCH_BIN)`), and `RomBench.require` fails loudly rather
    than skipping when something else does not.
    """
    global _BENCH
    if _BENCH is None:
        from recreate_kit.rom_bench import RomBench

        _BENCH = RomBench()
    return _BENCH


def assert_the_stub_is_the_rom_s_bytes(constant):
    """Every literal word of one handler's `src/bios/isr.S` stub against the ROM's own."""
    bench = _blob()
    symbol = stub_symbol(constant)
    at = bench.entry(symbol) - bench.base
    for span in LITERAL_SPANS[constant]:
        ours = bytes(bench.blob[at + span.at:at + span.at + span.length])
        theirs = bytes(BASE_IMAGE[span.rom_at:span.rom_at + span.length])
        assert len(ours) == span.length, f"{symbol} is shorter than its {span.length}-byte span"
        for offset in range(0, span.length, WORD_BYTES):
            our_word = ours[offset:offset + WORD_BYTES]
            their_word = theirs[offset:offset + WORD_BYTES]
            why = span.excused.get(offset)
            where = f"{symbol}+{span.at + offset:#x} against {span.rom_at + offset:#06x}"
            if why is None:
                assert our_word == their_word, (
                    f"{where}: the stub assembles to {our_word.hex()} where the ROM has "
                    f"{their_word.hex()}. It is a TRANSCRIPTION — either put the ROM's instruction "
                    f"back, or excuse the word in `isr.LITERAL_SPANS` with why they are the same")
            else:
                assert our_word != their_word, (
                    f"{where}: excused as \"{why}\", but the two words are now identical "
                    f"({our_word.hex()}) — drop the excuse rather than leaving it standing")


# ---- the register file a handler is entered with -------------------------------------------------
# Deliberately dirty, and different in every register: an interrupt lands on whatever the interrupted
# code was holding, and the three big handlers here open with a `movem.l` whose whole job is to give
# it back. `assert_registers_survived` is what turns that into a claim.
DIRTY_REGISTERS = {
    "d0": 0xD0D0_0000, "d1": 0xD1D1_0001, "d2": 0xD2D2_0002, "d3": 0xD3D3_0003,
    "d4": 0xD4D4_0004, "d5": 0xD5D5_0005, "d6": 0xD6D6_0006, "d7": 0xD7D7_0007,
    "a0": 0x000A_0000, "a1": 0x000A_0001, "a2": 0x000A_0002, "a3": 0x000A_0003,
    "a4": 0x000A_0004, "a5": 0x000A_0005, "a6": 0x000A_0006,
}


def assert_registers_survived(info, registers=DIRTY_REGISTERS):
    """Every register the handler was entered with, back as it was — the ORACLE's claim alone.

    The reconstruction is a C function with no emulated register file, so nothing on this side could
    reproduce a `movem.l d0-a6,-(sp)` / `movem.l (sp)+,d0-a6`; what the claim holds is the ORIGINAL,
    and with it the premise every one of these cases rests on — that a handler leaves the interrupted
    program exactly as it found it, so the only thing a differential has to compare is memory and the
    chip.
    """
    left = {name: info["regs"][name] for name in registers}
    assert left == dict(registers), (
        f"the handler did not give every register back: {left} against {dict(registers)}")


# ---- the routines a handler calls ----------------------------------------------------------------
# The candidate's half of `include/staged_call.h`: (image, routine address, pushed argument).
CALL_VECTOR = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_ubyte),
                               ctypes.c_uint32, ctypes.c_uint32)
NO_ARGUMENT = 0xFFFF_FFFF           # staged_call.h's STAGED_CALL_NO_ARGUMENT

_STAGED = {}                        # address -> effect(buf, argument), for the run in flight
_UNSTAGED = []                      # ...and addresses the candidate jumped to that nothing staged
# The ordered (address, argument) the CANDIDATE made, ONE LIST PER CANDIDATE RUN. A differential
# makes two of them when `poison` is on, and the attribution pass's is not the case's: poisoning an
# output can steer the reconstruction down another path entirely (the VBL's own semaphore, inverted,
# closes the whole body), so a single accumulating list would hold a mixture nobody could read.
# `CALLS` below is the PLAIN pass's, which is the one every claim here is about.
_PASSES = []
CALLS = []
# How many calls one candidate run may make before the list stops growing. A handler that LOOPS —
# the ACIA's `btst #4,$fffa01 / beq` is a real one — calls a staged routine per pass, and the
# reconstruction is host code with no instruction cap the way the oracle has: a defect in that
# condition is an endless loop, and an unbounded record of it is an endless ALLOCATION (measured
# during this wave's mutation sweep: a mutant that polled the wrong GPIP bit reached 15 GB before it
# was killed). Far above any case here, so a run under the cap is an ordinary run.
CALLS_MAX = 1 << 16


def _dispatch(buf, routine, argument):
    # A ctypes callback cannot raise through to its caller — the exception is printed and the call
    # returns — so everything it refuses is RECORDED and `run` reports it as the case's failure.
    # THAT INCLUDES A CALL FROM OUTSIDE `run`: nothing staged anything, so applying the last case's
    # effect to this buffer would be the worst answer available. `_PASSES` empty is how that shows.
    if not _PASSES:
        _UNSTAGED.append(routine)
        return
    if len(_PASSES[-1]) < CALLS_MAX:
        _PASSES[-1].append((routine, argument))
    effect = _STAGED.get(routine)
    if effect is None:
        _UNSTAGED.append(routine)
        return
    effect(buf, argument)


# Held for the process's lifetime: the .so keeps the raw pointer, and a trampoline the garbage
# collector freed would be a jump into released memory.
_HOOK = CALL_VECTOR(_dispatch)
ctypes.c_void_p.in_dll(_lib, "recreate_call_vector").value = \
    ctypes.cast(_HOOK, ctypes.c_void_p).value


def store_byte(value, address):
    """`move.b #value,(address).l` — the smallest stub that leaves a mark in compared image."""
    return struct.pack(">HHI", MOVE_B_IMMEDIATE_ABSOLUTE, value, address)


def poke(buf, address, data):
    """Write `data` into the CANDIDATE's image — a ctypes array, which takes one byte at a time
    rather than a slice of a `bytes`. The mirror of a stub's `move.x #value,(address).l`."""
    for offset, byte in enumerate(data):
        buf[address + offset] = byte


def store_word(value, address):
    """`move.w #value,(address).l` — 0x33fc, the immediate word, then the long address."""
    return struct.pack(">HHI", MOVE_W_IMMEDIATE_ABSOLUTE, value, address)


def store_long(value, address):
    """`move.l #value,(address).l` — 0x23fc, the immediate longword, then the long address."""
    return struct.pack(">HII", MOVE_L_IMMEDIATE_ABSOLUTE, value, address)


def store_frame_word(address):
    """`move.w 4(sp),(address).l` — a stub that reports the WORD its caller pushed in front of it.

    Four bytes above SP: two of return address and then the argument, which is where timer C's
    `move.w timr_ms,-(sp)` leaves it. A caller that pushed a four-byte slot instead would leave the
    high half here, so this is the stub that tells the ROM's `move.w` from a C call's widening.
    """
    return struct.pack(">HHI", MOVE_W_FRAME_ABSOLUTE, ARGUMENT_AT_4_SP, address)


# ---- what a battery reads out of the snapshot, and the smallest routine it can stage -------------
def long_in_snapshot(address):
    """The big-endian longword the CAPTURED machine holds at `address`."""
    return int.from_bytes(bytes(BASE_IMAGE[address:address + 4]), "big")


def word_in_snapshot(address):
    """...and the word."""
    return int.from_bytes(bytes(BASE_IMAGE[address:address + 2]), "big")


def vector_in_snapshot(vector):
    """...and a vector slot, which is a longword with a claim attached: the handler the machine
    really dispatches to."""
    return long_in_snapshot(vector)


# The byte a staged routine leaves behind, and where the Nth of them leaves it. Not 0 or $ff: a
# marker has to be a value the snapshot's dead RAM does not already hold, and one the poison pass
# (which inverts) does not turn into another marker.
MARK = 0x5A
MARKS = STUB_BAND + 0x100


def marker_routine(index=0):
    """A staged routine that leaves its own byte at `MARKS + index` and returns — the smallest a
    call can be, and readable afterwards as an ORDER rather than only as a fact.

    Returns the PAIR every staged routine is: the 68000 stub the oracle jumps to, and the same
    effect in Python for the candidate.
    """
    at = MARKS + index

    def effect(buf, _argument):
        buf[at] = MARK
    return store_byte(MARK, at) + RTS, effect


def marked(info, index=0):
    """Did the routine `marker_routine(index)` staged run?"""
    return info["writes"].get(MARKS + index) == MARK


def run(entry, glue, *, frame=FRAME_IN_STACK_BAND, resume_sr=RESUME_SR, pokes=None, regs=None,
        routines=None, exclude=None, poison=True, io_seed=None, psg_seed=None,
        max_insns=DEFAULT_MAX_INSNS):
    """One differential over the handler at `entry`, entered through its staged frame.

    `routines` is {address: (68000 stub bytes, effect(buf, argument))} — every routine this case
    stages, planted in the image for the ORACLE and bound to the hook for the CANDIDATE. `frame`,
    `resume_sr`, `exclude` and the seeds are `harness.differential`'s own; `regs` overrides part of
    the dirty register file a handler is entered with.
    """
    routines = routines or {}
    _STAGED.clear()
    _STAGED.update({at: effect for at, (_code, effect) in routines.items()})
    _UNSTAGED.clear()
    _PASSES.clear()
    CALLS.clear()

    def one_pass(lib, buf):
        """The battery's glue, with a fresh call list per candidate run — see `_PASSES`."""
        _PASSES.append([])
        return glue(lib, buf)

    staged = case_pokes(entry, frame, resume_sr, routines, pokes)
    try:
        info = case.run(TRAMPOLINE_AT[entry],
                        {**DIRTY_REGISTERS, **(regs or {}), "_pokes": staged}, one_pass,
                        width=case.NO_RESULT, poison=poison, exclude=exclude, io_seed=io_seed,
                        psg_seed=psg_seed, max_insns=max_insns)
    finally:
        # Nothing staged stays installed past the case that staged it: a later run that reached the
        # hook without going through here would otherwise apply THIS case's effect to its buffer.
        CALLS[:] = _PASSES[0] if _PASSES else []
        _STAGED.clear()
    assert not _UNSTAGED, (
        f"the candidate transferred control to {_UNSTAGED[0]:#x}, where this case staged no routine "
        f"— it staged {', '.join(f'{at:#x}' for at in sorted(routines))}")
    return info


# ---- the snapshot fields these four handlers read or poke ----------------------------------------
# Read by `test_boot_snapshot.py`, so the capture's non-deterministic MASK is checked against every
# byte a handler case touches. Here rather than in one battery because the four share most of them —
# `conterm` and the auto-repeat bytes are timer C's, the KBDVECS pair is the ACIA's, and the rest is
# the VBL's — and a per-battery copy would be four places for one span to go missing.
#
# Fields already declared by the trap batteries are NOT repeated: `SYSVAR_COLORPTR`,
# `SYSVAR_FRCLOCK`, `SOUND_LIST_POINTER`, `SYSVAR_V_BAS_AD`, `SYSVAR_HZ_200`, `CON_BLINK_RATE`,
# `CON_STATE_FLAGS` and `KBRATE_DELAY` are the screen, sound and console leaves' own.
CASE_SPANS = (
    (addrs.SYSVAR_ETV_TIMER, 4, "etv_timer, the vector timer C calls"),
    (addrs.SYSVAR_FLOCK, 2, "flock, the floppy VBL's gate"),
    (addrs.SYSVAR_DEFSHIFTMD, 4, "defshiftmd and sshiftmd, the resolution the follower restores"),
    (addrs.SYSVAR_VBLSEM, 8, "vblsem, nvbls and the whole _vblqueue longword"),
    (addrs.SYSVAR_SCREENPT, 4, "screenpt, the screen base Setscreen queues for the VBL"),
    (addrs.SYSVAR_VBCLOCK, 4, "_vbclock, the blanks the VBL serviced"),
    (addrs.SYSVAR_SWV_VEC, 4, "swv_vec, called on a monitor change"),
    (addrs.SYSVAR_CONTERM, 1, "conterm, timer C's key-repeat gate"),
    (addrs.SYSVAR_DUMPFLG, 2, "_dumpflg, the screen-dump request"),
    (addrs.SYSVAR_SCR_DUMP, 4, "scr_dump, the routine Scrdmp jumps through"),
    (addrs.FLOPPY_VBL_ENTERED, 1, "the byte the floppy VBL sets before its own gate"),
    (addrs.CON_CURSOR_DISABLE, 2, "the word that suppresses the cursor blink"),
    (addrs.CON_CELL_HEIGHT, 2, "the cursor cell's height"),
    (addrs.CON_BLINK_TIMER, 1, "the blinks left before the cursor toggles"),
    (addrs.CON_CURSOR_ADDRESS, 4, "where the cursor cell is on screen"),
    (addrs.CON_PLANES, 4, "the screen's planes and its line pitch"),
    (addrs.SYSVAR_KB_REPEAT_KEY, 3, "the auto-repeat scancode and its two countdowns"),
    (addrs.SYSVAR_TIMER_C_DIVIDER, 2, "timer C's fourth-tick divider"),
    (addrs.SOUND_RAMP_VALUE, 1, "the Dosound driver's ramp accumulator"),
    (addrs.KBDVECS, KBDVECS_BYTES, "KBDVECS, whose last two longwords the ACIA handler calls"),
    (FRAME_IN_STACK_BAND, addrs.EXCEPTION_FRAME_BYTES,
     "the exception frame a case stages under the oracle's stack"),
)
