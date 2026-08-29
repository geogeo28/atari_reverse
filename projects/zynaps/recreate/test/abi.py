"""Calling Zynaps' routines under the oracle, in memory the differential can actually see.

Every routine ported so far takes its arguments in registers, and most write their answer into the
image, where `differential` compares it byte for byte. One does not: `sound_lookup_tune` @ 0x16b32
returns a pointer in A1 and a table offset in D1 and touches no memory at all, so its diff would be
vacuously empty. `register_call_pokes` fixes that the way Joust's does — poke a short 68000 stub
into free image space, enter the oracle THERE, and let the stub store the registers that matter into
ordinary, fully-diffed memory. The stub is poked identically on both sides; the candidate never
executes it, its glue mirrors the same stores at the same address. The `jsr` return address goes on
the oracle's own stack, inside the guard band the differential already drops.

THE SCRATCH MAP IS NOT MERELY "SOMEWHERE ABOVE THE PROGRAM". Zynaps hard-codes its two framebuffers
at absolute RAM addresses (`../names.txt`, `screen_back` / `screen_front` and the comment on
0x1002c) rather than asking XBIOS for one, so there is a 63 KB hole in the middle of the free space
that belongs to the game. A stub or a scratch buffer parked there would be memory the game writes
for its own reasons the moment a ported routine touches the screen — a false green today and a
baffling failure the day the first draw routine lands. `test_constants.py` pins the map clear of
both the program and the framebuffers.
"""
import random

import harness  # noqa: F401  — imported for its side effect: it binds the kit to this project

# The game's own hard-coded screen buffers, from ../names.txt (`screen_back` 0x1797e = 0x70300,
# `screen_front` 0x17982 = 0x78000; a 320x200 4-plane frame is 0x7d00 bytes). They are contiguous:
# 0x70300 + 0x7d00 == 0x78000, so together they occupy [0x70300, 0x7fd00).
SCREEN_BACK = 0x70300
SCREEN_FRONT = 0x78000
SCREEN_BYTES = 0x7d00
SCREEN_SPAN = (SCREEN_BACK, SCREEN_FRONT + SCREEN_BYTES)

# Free image space: above the framebuffers above (which are themselves above the program, whose
# text + bss end at 0x6e96e) and far below the TOS model's staged-file table at 0xbf000.
STUB = 0x80000        # where the oracle enters
RESULT = 0x80100      # where the stub stores results the image diff could not otherwise see
SCRATCH = 0x81000     # a test's own source/destination buffers
# The largest span any case builds from SCRATCH: test_sprite.py's zero-width preshift case walks
# 64 Ki words. Pinned below the staged-file table by test_constants.py.
SCRATCH_BYTES = 0x20000

_MOVE_L_TO_A0_POSTINC = 0x20c0   # `move.l <ea>,(a0)+`, long, dest mode 011 reg 000; | the source ea
_SOURCE_EA = {"d": 0x00, "a": 0x08}   # source mode field: 000 = Dn, 001 = An


def _store_through_a0(register):
    """One `move.l <register>,(a0)+` instruction word."""
    kind, number = register[0], int(register[1])
    return (_MOVE_L_TO_A0_POSTINC | _SOURCE_EA[kind] | number).to_bytes(2, "big")


def register_call_pokes(routine, stores):
    """Pokes that call `routine` (register ABI) and store `stores` through A0.

        jsr     routine
        move.l  <stores[0]>,(a0)+
        ...
        rts

    Point A0 at RESULT through the run's registers; the listed registers then land as consecutive
    longwords in diffed memory, in the order given.
    """
    code = (b"\x4e\xb9" + routine.to_bytes(4, "big")            # jsr imm.l
            + b"".join(_store_through_a0(r) for r in stores)
            + b"\x4e\x75")                                      # rts
    return {STUB: code}


# `Scc <ea>` — 0101 cccc 11 mmmrrr — with the destination fixed at (A0) (mode 010, register 000).
# It stores 0xff when the condition holds and 0x00 when it does not; those two bytes ARE the answer
# the differential compares, so a reconstruction mirrors them rather than picking its own encoding
# (include/enemy.h, SCC_BYTE_TRUE / SCC_BYTE_FALSE).
_SCC_TO_A0 = {"cs": 0x55d0, "eq": 0x57d0}


def flag_call_pokes(routine, condition):
    """Pokes that call `routine` and store the FLAG it answers in, through A0.

        jsr     routine
        s<cond> (a0)
        rts

    A 68000 routine whose answer is a condition code — the script VM's handlers return "run the next
    opcode" in the CARRY, and the class-bitmap test returns its bit in Z — writes no memory the image
    diff could compare, so the stub turns that bit into a byte the diff CAN see. `condition` is the
    Scc suffix the caller's own branch uses (`bcs` -> "cs", `beq` -> "eq"), so the stub asks the
    same question the game asks.

    Point A0 at RESULT through the run's registers; the flag byte lands there.

    IT STORES THE FLAG AND NOTHING ELSE, deliberately. A routine that answers in a flag AND a
    register is served by comparing the register against the oracle's own (`differential`'s
    `info["regs"]`), which is what `test_enemy.py`'s enemy_alloc_slot cases do — so the stub needs no
    second store, and adding one before a caller exists would ship an unassembled encoding that no
    case in the suite executes.
    """
    code = (b"\x4e\xb9" + routine.to_bytes(4, "big")            # jsr imm.l
            + _SCC_TO_A0[condition].to_bytes(2, "big")
            + b"\x4e\x75")                                      # rts
    return {STUB: code}


# --- a second stub shape: routines that CLOBBER A0, so it cannot be the result cursor ------------
#
# `register_call_pokes` above stores through A0, which only works while the routine leaves A0 alone.
# `copy_block_words` @ 0x13858 walks A0 as its source pointer, and the sine routines leave their
# answer in D0 while using A0 for the table, so those need a store that names its own destination.
# `movem.l <list>,RESULT` is that store: one instruction, an absolute-long destination, and a
# register list the case chooses.
_MOVEM_L_TO_ABS_LONG = 0x48f9    # movem.l <list>,xxx.l — dir 0 (regs to memory), mode 111 reg 001
_MOVEM_BIT = {**{f"d{n}": n for n in range(8)}, **{f"a{n}": 8 + n for n in range(7)}}


def register_dump_pokes(routine, registers):
    """Pokes that call `routine` and `movem.l` the named registers to RESULT.

        jsr     routine
        movem.l <registers>,RESULT
        rts

    Unlike `register_call_pokes` this needs no register of its own, so it suits a routine that walks
    A0. THE ORDER IS THE INSTRUCTION'S, NOT THE CALLER'S: `movem.l` always stores D0..D7 then
    A0..A6 ascending, whatever order the list was written in, and the candidate glue must mirror
    that. So the argument is required to be in that order already — a list that is not is a bug in
    the case rather than something to sort silently, since the glue beside it would then be storing
    in an order the test author did not read.
    """
    bits = [_MOVEM_BIT[name] for name in registers]
    assert bits == sorted(set(bits)), (
        f"{registers} is not in movem order — the instruction stores d0..d7 then a0..a6 ascending, "
        f"and the candidate glue mirrors that order")
    mask = sum(1 << bit for bit in bits)
    code = (b"\x4e\xb9" + routine.to_bytes(4, "big")            # jsr imm.l
            + _MOVEM_L_TO_ABS_LONG.to_bytes(2, "big")
            + mask.to_bytes(2, "big") + RESULT.to_bytes(4, "big")
            + b"\x4e\x75")                                      # rts
    return {STUB: code}


# --- APPENDED: recording the CONDITION CODES, for a routine whose whole answer is a flag ---
#
# The four type-class tests (0x12dc6, 0x13d3e, 0x13d6e, 0x140f6) and `collision_chain_walk`
# (0x12d44) answer their callers in the 68000's Z flag: every call site's next instruction is a
# `beq`. `register_call_pokes` above cannot record that. Storing a data register instead would be
# recording scratch, and — worse — would pass whenever the scratch happened to agree, which is
# exactly the coincidental green the poison pass exists to catch. `Scc` is the instruction that
# turns a condition into data, so the stub below stores the flag FIRST and the registers after,
# since `move.l` sets the flags itself.
_SEQ_TO_A0_POSTINC = 0x57d8   # `seq (a0)+`: 0101 cond=0111 11, dest mode 011 reg 000
_ADDQ_L_1_A0 = 0x5288         # `addq.l #1,a0` — the pad that re-aligns A0 for the longword stores
_MOVEA_L_IMM_TO_A0 = 0x207c   # `movea.l #imm32,a0` — and `movea` is the move that leaves CCR alone


def register_call_eq_flag_pokes(routine, result, stores=()):
    """Pokes that call `routine` and store its Z flag, then `stores`, at `result`.

        jsr     routine
        movea.l #result,a0      ; AFTER the call, and `movea` does not touch the flags
        seq     (a0)+           ; 0xff if Z was set at the rts, 0x00 if it was clear
        addq.l  #1,a0           ; the byte above leaves A0 odd, and `move.l` needs it even
        move.l  <stores[0]>,(a0)+
        ...
        rts

    So `result`+0 is the flag, `result`+1 is touched by neither side — which is what makes it a
    usable canary — and the listed registers follow as longwords from `result`+2.

    THE STUB LOADS A0 ITSELF rather than taking it through the run's registers, unlike
    `register_call_pokes` above. Two of the routines this serves take their own argument in A0
    (`object_type_is_collidable`) or use it as scratch (`collision_chain_walk`), so a caller-set A0
    would either be overwritten before the call or point at the record when the stores land.
    """
    code = (b"\x4e\xb9" + routine.to_bytes(4, "big")            # jsr imm.l
            + _MOVEA_L_IMM_TO_A0.to_bytes(2, "big") + result.to_bytes(4, "big")
            + _SEQ_TO_A0_POSTINC.to_bytes(2, "big")
            + _ADDQ_L_1_A0.to_bytes(2, "big")
            + b"".join(_store_through_a0(r) for r in stores)
            + b"\x4e\x75")                                      # rts
    return {STUB: code}


# The default noise margin either side of a seeded span. IT IS NOT TIDINESS: most of what these
# routines write is bss, which the loaded image already holds as zeroes, so a candidate clearing or
# copying sixteen bytes too far would write zeroes over zeroes and the diff would stay empty. The
# margin is what turns "wrote past the end" into a difference.
GUARD_BYTES = 16


def seed_spans(seed, spans, guard=0):
    """Noise over every byte a run touches, as a poke dict — the batteries' one seeder.

    `spans` is an iterable of (lo, hi); `guard` widens each by that many bytes either side. Spans
    are widened FIRST and merged after, so two pokes never cover one byte: `harness.make_image`
    applies a poke dict in insertion order and the later one silently wins, which reads as "both
    regions were seeded" when only one was.

    Shared rather than per-battery because the merge is load-bearing and was written three times in
    one change, one of the copies without it (test_video.py's block-blit overlaps, where the
    destination poke swallowed the source strip's noise and both its guard bands).
    """
    widened = sorted([lo - guard, hi + guard] for lo, hi in spans)
    merged = []
    for lo, hi in widened:
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    rng = random.Random(seed)
    return {lo: rng.randbytes(hi - lo) for lo, hi in merged}


def indexed_table(entries, entry_bytes, values):
    """A table of `entries` big-endian fields of `entry_bytes` each, zero but for `values`.

    `values` is {index: value}. Two batteries seed the collision subsystem's 21-long tables this way
    — `test_collision.py`'s chain cases and `test_weapon.py`'s `bomb_update` cases — and this is
    shared for the same reason `seed_spans` above is: the loop has ALREADY been written wrong twice
    in this project, by two different authors, both times as `rows[start:][:n] = …`. That assigns
    into a COPY of the slice, so the mark is silently dropped and every case runs against an
    all-zero table — a whole battery going vacuous while staying green. STATUS.md records both
    occurrences; this is the one place that cannot make the mistake again.

    Two refusals, because a caller that trips either has already lost the coverage it thinks it has:
    an index outside the table (which would otherwise APPEND, growing the poke past the table into
    whatever follows it), and a value too wide for one entry.
    """
    table = bytearray(entries * entry_bytes)
    for index, value in values.items():
        assert 0 <= index < entries, f"index {index} is outside the {entries}-entry table"
        assert value >> (8 * entry_bytes) == 0, (
            f"{value:#x} does not fit one {entry_bytes}-byte entry")
        start = index * entry_bytes
        table[start:start + entry_bytes] = value.to_bytes(entry_bytes, "big")
    return bytes(table)


def call_sequence_pokes(routines):
    """Pokes that `jsr` each routine in `routines`, in order, and then `rts`.

        jsr     routines[0]
        jsr     routines[1]
        ...
        rts

    For a routine whose interesting behaviour is what it does over SEVERAL calls — the sound
    driver's VBL tick, whose state carries from one frame to the next. Running the sequence as ONE
    oracle run is what lets the differential compare it at all: `differential` rebuilds the image
    from BASE_IMAGE for every call, so N separate cases would each re-run frame 1. It also puts the
    whole N-frame chip-register stream into one PSG ledger, where the ORDER across frames is
    compared and not only within them.

    EVERY ROUTINE LISTED MUST PRESERVE THE REGISTERS THE NEXT ONE NEEDS, and that is the caller's
    check, not something this builder can make: the stub emits nothing between the calls. The sound
    driver's routines preserve everything (`movem.l` at both ends); a routine that preserves only
    some of its registers can still be chained, but the case has to say which register it is
    leaning on and why that holds — see `test_fileio.py::test_load_leaves_the_handle_word_behind`,
    which leans on the trap model leaving A0 alone.
    """
    code = b"".join(b"\x4e\xb9" + routine.to_bytes(4, "big") for routine in routines)
    return {STUB: code + b"\x4e\x75"}


# --- a third stub shape: an INTERRUPT handler, which returns with `rte` and not `rts` -------------
#
# `emu.run` enters a routine with one return address on the stack and stops when the `rts` pops it.
# An interrupt handler pops a whole 68000 exception frame instead — the status register as a word,
# then the interrupted PC as a longword — so entering one directly would return to whatever those
# six bytes happened to be. This stub builds the frame the handler expects and jumps into it:
#
#     pea     resume          ; the frame's PC longword
#     move.w  #SR,-(a7)       ; ...and the status register beneath it
#     jmp     handler         ; the handler's `rte` pops both and lands on `resume`
#   resume:
#     rts                     ; ...which is the ordinary return emu.run is waiting for
#
# Both pushes land inside the stack-guard band the differential already drops, so the frame itself
# is never compared — only what the handler did with the rest of the image.
_PEA_ABS_LONG = 0x4879           # pea xxx.l
_MOVE_W_IMM_TO_PREDEC_A7 = 0x3f3c
_JMP_ABS_LONG = 0x4ef9
# Supervisor set, interrupt mask 3 — the state an interrupt is taken in, and the one the model
# already runs in (it never leaves supervisor mode; TRAP_MODEL.md, Phase 2).
INTERRUPT_SR = 0x2300
_INTERRUPT_STUB_RESUME = 16      # pea (6) + move.w (4) + jmp (6)


def interrupt_frame_pokes(handler):
    """Pokes that enter `handler` around a 68000 interrupt frame, so its `rte` returns cleanly."""
    resume = STUB + _INTERRUPT_STUB_RESUME
    code = (_PEA_ABS_LONG.to_bytes(2, "big") + resume.to_bytes(4, "big")
            + _MOVE_W_IMM_TO_PREDEC_A7.to_bytes(2, "big") + INTERRUPT_SR.to_bytes(2, "big")
            + _JMP_ABS_LONG.to_bytes(2, "big") + handler.to_bytes(4, "big")
            + b"\x4e\x75")                                      # rts, at `resume`
    assert len(code) == _INTERRUPT_STUB_RESUME + 2, "the resume offset no longer names the rts"
    return {STUB: code}


# --- APPENDED: the FLAG stub for a routine that CLOBBERS A0 --------------------------------------
#
# `flag_call_pokes` above stores through the caller's A0, which only works while the routine leaves
# it alone. Several script-VM handlers do not: every one that reaches `entity_set_velocity_from_angle`
# (0x142d4) walks A0 over the cosine table, and `actor_script_op_bounce_fall` reaches
# `collision_chain_walk` (0x12d44), which walks it over the entity table. With the caller's stub the
# `Scc` then lands wherever the callee left A0 — the oracle writes one byte into the TEXT segment and
# never touches the flag at all, which reads as a candidate bug rather than as a stub that no longer
# fits (measured: `sine_table` came back one byte different and the flag byte came back as its
# canary). This shape loads A0 itself, after the call and through the `movea` that leaves CCR alone,
# exactly as `register_call_eq_flag_pokes` above does and for the same reason.
def flag_call_self_addressed_pokes(routine, condition, result):
    """Pokes that call `routine` and store the FLAG it answers in, at `result`.

        jsr     routine
        movea.l #result,a0      ; AFTER the call, and `movea` does not touch the flags
        s<cond> (a0)
        rts

    Unlike `flag_call_pokes`, the run's own A0 is free — so a case using this one is NOT also
    asserting that the routine preserved it. Prefer `flag_call_pokes` wherever the routine does;
    `test_enemy.py`'s `A0_CLOBBERING_ENTRIES` is the roster of the ones that cannot, and the test
    beside it proves that roster both minimal and complete.

    ITS SKELETON IS `register_call_eq_flag_pokes`' ABOVE with the condition parameterised and no
    stores — three encoders in this file now share `jsr / movea.l #result,a0 / Scc / rts`. The merge
    is a `condition` parameter on that function, and it is NOT done here because this file is
    append-only while several agents hold it at once (README.md, "Adding a function"): changing an
    existing body would turn every other agent's append into a conflict. Recorded in
    projects/zynaps/recreate/STATUS.md so it is merged deliberately rather than forgotten.
    """
    code = (b"\x4e\xb9" + routine.to_bytes(4, "big")            # jsr imm.l
            + _MOVEA_L_IMM_TO_A0.to_bytes(2, "big") + result.to_bytes(4, "big")
            + _SCC_TO_A0[condition].to_bytes(2, "big")
            + b"\x4e\x75")                                      # rts
    return {STUB: code}
