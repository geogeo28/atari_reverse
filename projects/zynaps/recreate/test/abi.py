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
