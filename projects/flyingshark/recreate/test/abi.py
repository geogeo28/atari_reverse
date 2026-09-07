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

_MOVE_L_TO_A0_POSTINC = 0x20c0   # `move.l <ea>,(a0)+`, long, dest mode 011 reg 000; | the source ea
_SOURCE_EA = {"d": 0x00, "a": 0x08}   # source mode field: 000 = Dn, 001 = An
_JSR_ABS_LONG = 0x4eb9
_RTS = 0x4e75


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
    longwords in diffed memory, in the order given. The `jsr` return address goes on the oracle's
    own stack, inside the guard band the differential already drops.

    Only usable while `routine` leaves A0 alone — which most of this game's leaves do not, since a
    register ABI hands arguments in A0 as readily as in D0. A routine that walks A0 needs a stub
    that names its own destination (Zynaps' `register_dump_pokes`, a `movem.l <list>,RESULT`); it is
    not here because nothing has needed it yet, and an unassembled encoding no case executes is a
    liability rather than a head start.
    """
    code = (_JSR_ABS_LONG.to_bytes(2, "big") + routine.to_bytes(4, "big")
            + b"".join(_store_through_a0(r) for r in stores)
            + _RTS.to_bytes(2, "big"))
    return {STUB: code}
