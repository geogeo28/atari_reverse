"""Calling Flying Shark's routines under the oracle, in memory the differential can actually see.

This program is hand-written assembly with a REGISTER ABI everywhere: a routine takes its arguments
in d0/a0/... and most write their answer into the image, where `differential` compares it byte for
byte. One that answers only in registers has a vacuously empty diff, so `register_call_pokes` does
what Zynaps' and Joust's do — poke a short 68000 stub into free image space, enter the oracle THERE,
and let the stub store the registers that matter into ordinary, fully-diffed memory. The stub is
poked identically on both sides; the candidate never executes it, its glue mirrors the same stores
at the same address.

THE SCRATCH MAP IS NOT MERELY "SOMEWHERE ABOVE THE PROGRAM", and this game is the reason the
distinction has teeth. Flying Shark scrolls by moving the video base through a 0x1f900-byte
CIRCULAR framebuffer that `boot_init` places immediately below whatever XBIOS `Physbase` answers
(`include/globals.h`, "the screen ring") — so the ring is not part of the program, it is a second
region of live game memory whose address the harness chooses. A stub or a scratch buffer parked
inside it would be memory the game overwrites for its own reasons the moment a ported draw routine
runs. `test_constants.py` pins the map clear of the program, the ring and the staged-file table.
"""
import harness  # noqa: F401  — imported for its side effect: it binds the kit to this project

# ---- where the harness puts the screen ring ------------------------------------------------------
#
# THE MODEL'S OWN Physbase CANNOT BE USED. `os.h` answers XBIOS Physbase with OS_SCREEN_BASE
# (0x8000), and boot_init's first act on it is `subi.l #$1f900,d0` — which underflows to
# 0xfffe8700, so every screen base the game derives would sit outside the image entirely: the
# oracle drops those writes on the floor and a candidate indexing `image + base` walks off the
# buffer (which is exactly what `make guarded` faults on). So the fixture PLACES the ring instead,
# by applying boot_init's own arithmetic to a Physbase of its own choosing.
#
# The choice: a Physbase that puts the ring's low limit on a clean 0x10000 boundary above the
# program's 0x5aede end and below the scratch map. boot_init rounds STRICTLY up — `addi.l #$100,d0`
# then `clr.b d0`, so an already-aligned raw base still gains 0x100 — which is why this is 0x7f800
# and not 0x7f900. `test_image_model.py` runs the real routine and pins the arithmetic.
SCREEN_RING_PHYSBASE = 0x7f800
SCREEN_RING_BASE = 0x60000          # = round_up_256(SCREEN_RING_PHYSBASE - 0x1f900)
# The whole surface the four rotating bases can address: the ring itself, plus one 0x7d00-byte frame
# read from its highest base. `include/globals.h` owns the two constants; test_constants.py pins
# these against them, so the span cannot drift from the model the cores compile against.
SCREEN_RING_BYTES = 0x1f900
SCREEN_BYTES = 0x7d00
SCREEN_RING_SPAN = (SCREEN_RING_BASE, SCREEN_RING_BASE + SCREEN_RING_BYTES + SCREEN_BYTES)

# ---- free image space, above all of that and far below the TOS model's staged-file table --------
STUB = 0x90000        # where the oracle enters
RESULT = 0x90100      # where the stub stores results the image diff could not otherwise see
SCRATCH = 0x91000     # a test's own source/destination buffers
# The largest span a case may build from SCRATCH. Pinned below the staged-file table by
# test_constants.py, so a battery that widens it has to move the map rather than overrun the table.
SCRATCH_BYTES = 0x20000

# ---- the stub builders, and the two words every one of them is made of ---------------------------
_JSR_ABS_LONG = 0x4eb9   # jsr xxx.l — mode 111 reg 001
_RTS = 0x4e75


def _word(value):
    return value.to_bytes(2, "big")


def _jsr(routine):
    """`jsr routine.l`, the call every stub below is built around."""
    return _word(_JSR_ABS_LONG) + routine.to_bytes(4, "big")


def _stub(*parts):
    """The pokes for a stub assembled from `parts` and ended with an `rts`, poked at STUB.

    One place that knows a stub lives at STUB and returns, so a new shape is the instructions it
    adds rather than another copy of the frame — and a shape that forgot its `rts` would run off
    into whatever the image holds next, which is the failure this shared frame removes.
    """
    return {STUB: b"".join(parts) + _word(_RTS)}


_MOVEQ = 0x7000          # moveq #<data>,Dn — | (n << 9) | the data byte
_SUBQ_B_1 = 0x5300       # subq.b #1,Dn — | n


def _moveq(number, value):
    """`moveq #value,d<number>` — the one-word way to put a small signed immediate in a register.

    The whole byte range is reachable: 0x80..0xff arrive as -128..-1, which leaves the low byte the
    caller asked for and sign in the rest, exactly as the game's own `move.w #$n,d0` sites do not.
    """
    return _word(_MOVEQ | (number << 9) | (value & 0xff))


_MOVE_L_TO_A0_POSTINC = 0x20c0   # `move.l <ea>,(a0)+`, long, dest mode 011 reg 000; | the source ea
_SOURCE_EA = {"d": 0x00, "a": 0x08}   # source mode field: 000 = Dn, 001 = An


def _store_through_a0(register):
    """One `move.l <register>,(a0)+` instruction word."""
    kind, number = register[0], int(register[1])
    return _word(_MOVE_L_TO_A0_POSTINC | _SOURCE_EA[kind] | number)


def register_call_pokes(routine, stores):
    """Pokes that call `routine` (register ABI) and store `stores` through A0.

        jsr     routine
        move.l  <stores[0]>,(a0)+
        ...
        rts

    Point A0 at RESULT through the run's registers; the listed registers then land as consecutive
    longwords in diffed memory, in the order given. The `jsr` return address goes on the oracle's
    own stack, inside the guard band the differential already drops.

    Only usable while `routine` leaves A0 alone — which most of this game's leaves do not, since a
    register ABI hands arguments in A0 as readily as in D0. A routine that walks A0 needs a stub
    that names its own destination instead: `register_dump_pokes` below.
    """
    return _stub(_jsr(routine), *(_store_through_a0(r) for r in stores))


# --- a stub for a routine that CLOBBERS A0: one store that names its own destination -------------
#
# `register_call_pokes` above stores THROUGH A0, which only works while the routine leaves A0 alone.
# `build_text_display_list` @ 0x10698 walks A0 as its script cursor and answers in A1, D1 and D2, so
# it needs a store that names its own destination. `movem.l <list>,RESULT` is that store: one
# instruction, an absolute-long destination, and a register list the case chooses.
_MOVEM_L_TO_ABS_LONG = 0x48f9   # movem.l <list>,xxx.l — dir 0 (regs to memory), mode 111 reg 001
_MOVEM_BIT = {**{f"d{n}": n for n in range(8)}, **{f"a{n}": 8 + n for n in range(7)}}


def register_dump_pokes(routine, registers):
    """Pokes that call `routine` (register ABI) and `movem.l` the named registers to RESULT.

        jsr     routine
        movem.l <registers>,RESULT
        rts

    Needs no register of its own, unlike `register_call_pokes`, so it suits a routine that walks A0.
    THE ORDER IS THE INSTRUCTION'S, NOT THE CALLER'S: `movem.l` always stores D0..D7 then A0..A6
    ascending whatever order the list was written in, and the candidate's glue must mirror that. So
    the argument is required to be in that order already — a list that is not is a bug in the case
    rather than something to sort silently, since the glue beside it would then be storing in an
    order the test author did not read.
    """
    bits = [_MOVEM_BIT[name] for name in registers]
    assert bits == sorted(set(bits)), (
        f"{registers} is not in movem order — the instruction stores d0..d7 then a0..a6 ascending, "
        f"and the candidate glue mirrors that order")
    mask = sum(1 << bit for bit in bits)
    return _stub(_jsr(routine),
                 _word(_MOVEM_L_TO_ABS_LONG) + _word(mask) + RESULT.to_bytes(4, "big"))


# --- driving and reading the X FLAG, for a routine whose first `abcd` adds it --------------------
#
# X is the one condition bit with neither an entry register to set it nor an `Scc` suffix to read
# it, and the oracle enters every routine at SR = 0x2700 (oracle/shim.c), so X = 0 unless a stub
# makes it otherwise. `score_add_bcd` @ 0x10bec is entered through nine wrappers whose `movem.l` and
# `lea` leave the condition codes alone, so what its first `abcd` adds is the CALLER's X — an input.
# Its last `abcd` leaves one in turn, which is the X the caller's next instruction sees.
_ADDX_B_D1_D1 = 0xd301

EXTEND_CLEAR, EXTEND_SET = 0, 1
# The register the setter borrows to make X, for a routine that does not read it. Overridable
# per case: `item_drop_if_formation_cleared` takes its x in D0, and takes no D7 at all.
EXTEND_SETTER_SCRATCH = "d0"
BOTH_EXTENDS = (EXTEND_CLEAR, EXTEND_SET)

# The register the stub's `addx.b d1,d1` leaves the outgoing flag in, and the mask that reads it.
_EXTEND_ANSWER_REGISTER = "d1"
_EXTEND_ANSWER_MASK = 0xff


def oracle_extend(info):
    """The X flag the ORACLE left, out of a `differential` run entered through `extend_call_pokes`."""
    return info["regs"][_EXTEND_ANSWER_REGISTER] & _EXTEND_ANSWER_MASK


def extend_call_pokes(routine, extend_in=EXTEND_CLEAR, scratch=EXTEND_SETTER_SCRATCH):
    r"""Pokes that drive the X FLAG INTO `routine` and leave the X IT LEAVES in D1, as 0 or 1.

        moveq   #0,<scratch>    ;  \  only when extend_in
        subq.b  #1,<scratch>    ;  /   borrows, so X := 1
        jsr     routine
        moveq   #0,d1           ; sets N/Z/V/C and leaves X alone
        addx.b  d1,d1           ; 0 + 0 + X
        rts

    It stores nothing: D1 is a reported register, so the case reads the oracle's through
    `differential`'s `info["regs"]` (via `oracle_extend`) and compares it against what the
    candidate's glue returned.

    THE SETTER CLOBBERS `scratch`, so it must be a register `routine` does not read — the default D0
    suits every score wrapper (each opens with a `movem.l` that saves A0 and A1 and nothing else),
    while a routine taking an argument in D0 names a spare one instead. A wrong choice fails loudly:
    the oracle then runs on a register the candidate's glue was never handed.
    """
    number = int(scratch[1])
    setter = (_moveq(number, 0) + _word(_SUBQ_B_1 | number)) if extend_in else b""
    return _stub(setter, _jsr(routine),
                 _moveq(int(_EXTEND_ANSWER_REGISTER[1]), 0), _word(_ADDX_B_D1_D1))


def call_sequence_with_d0_pokes(steps):
    """Pokes that `moveq` an argument into D0 before each `jsr`, and then `rts`.

        moveq   #steps[0][1],d0
        jsr     steps[0][0]
        ...
        rts

    `call_sequence_pokes` above cannot express a sequence whose calls take DIFFERENT arguments, and
    the sound module's does: starting an effect over a running tune is `music_start(tune)` then a
    run of ticks then `sfx_start(effect)` then more ticks, three different D0 values in one run.
    Each step is `(routine, d0)` with `d0` in -128..127 or 0..255 (the byte is what every entry in
    this game reads; the immediate is emitted signed).

    The ticks in such a sequence take no argument at all and are listed with any D0 — the module's
    `sound_vbl_tick` reads none, and `moveq` before it is one harmless word.

    RUNNING SEVERAL CALLS IN ONE ORACLE RUN is the point, not an economy: `harness.differential`
    rebuilds the image from the base for every call, so N separate cases would each re-run frame 1
    of a module whose state carries from one frame to the next. It also puts the whole N-frame
    chip-register stream into ONE PSG ledger, where the order ACROSS frames is compared and not
    only within them. Every routine listed must preserve the registers the next one needs — the
    stub emits nothing between the calls — which the four sound entries do, `movem.l` at both ends.
    """
    return _stub(*(_moveq(0, argument) + _jsr(routine) for routine, argument in steps))
