"""XBIOS Offgibit (function $1d) @ $fc2f02 — clear bits of the YM2149's port A.

`Ongibit`'s twin, and the ROM's two bodies differ in ONE INSTRUCTION: `and.b d2,d0` where the other
has `or.b`. Everything `test_xbios_ongibit.py`'s docstring says about the route through `Giaccess`,
the three-entry access ledger, the low byte of the argument, the outer interrupt bracket and the D0
the `movem` pair hands back holds here word for word, and this file reuses that battery's declared
entry file rather than keeping a second copy of it.

THE ARGUMENT IS THE MASK TO KEEP, NOT THE BITS TO CLEAR — which is the trap in the pair and the
reason the two have separate files rather than one parametrized one. `Offgibit($ef)` clears bit 4;
`Offgibit($10)` clears the other SEVEN. A reconstruction written as "clear the bits the argument
names" is the natural reading of the routine's NAME and is wrong for every argument but $00 and $ff,
and the cases below are chosen so that it diverges on all of them.

TOS CALLS THE BODY ITSELF, ONE INSTRUCTION LOWER. $fc2ed8 is `moveq #-17,d2 / bra.s $fc2f08` — an
entry BELOW the argument fetch, with the mask $ef already in D2, which is the OS's own "clear port A
bit 4". It is this same body with a constant rather than a third routine, so nothing here
reconstructs it; `gibit.c` records where it is.
"""
import ctypes

import pytest

from harness import _lib, addrs, in_diff

import case
# The declared chip state is the pair's, not this file's: one entry byte for port A and a distinct
# one per other register, so a reconstruction that selected the wrong register is served a different
# value on either routine. A second copy here would be a second machine to keep level. `MARKED_D0`
# and the ledger SHAPE come from there for the same reason — the two routines make the same three
# chip accesses and give the same register back, and only the byte written differs.
from test_xbios_ongibit import ENTRY_FILE, ENTRY_PORT_A, MARKED_D0, expected_events

_lib.xbios_offgibit.argtypes = [ctypes.c_uint32, ctypes.c_uint16]
_lib.xbios_offgibit.restype = ctypes.c_uint32


def run(keep, entry_d0=0, poison=True):
    def glue(lib, buf):
        del buf                     # the chip is not in the image; see the module docstring
        return lib.xbios_offgibit(entry_d0, keep & 0xFFFF)

    return case.run(addrs.XBIOS_OFFGIBIT,
                    {"a5": 0, "d0": entry_d0, "_pokes": case.word_arg(keep)}, glue,
                    psg_seed=ENTRY_FILE, poison=poison)


# Masks that say something different about the AND. Each `~(1 << bit)` clears exactly one line, which
# is what every caller of this routine does; TOS's own $ef is one of them. Then the two ends — $ff
# keeps everything and $00 clears the port — and $55/$aa, which have bits on both sides of the entry
# byte and are the pair a reconstruction that inverted the argument gets exactly backwards.
SINGLE_BIT_CLEARS = tuple((~(1 << bit)) & 0xFF for bit in range(8))
MASKS = SINGLE_BIT_CLEARS + (0xFF, 0x00, 0x55, 0xAA)


@pytest.mark.parametrize("keep", MASKS)
def test_it_keeps_the_bits_the_argument_names_and_clears_the_rest(keep):
    """THE CASE THE PAIR EXISTS FOR. The argument is a KEEP mask: a reconstruction that spelt it as
    `port_a & ~keep` — "clear what was asked for", which is what the routine's name suggests —
    produces a different byte for every mask here but $00 and $ff, and those two are included so
    that the claim does not rest on the ones where the two agree."""
    info = run(keep)
    assert info["regs"]["psg_events"] == expected_events(ENTRY_PORT_A & keep)


def test_the_two_routines_are_not_the_same_function():
    """`or.b` against `and.b`, said as a comparison. Over the same entry byte and the same mask the
    pair must disagree — which is what makes each file's own cases claims about ITS instruction
    rather than about the shared read-modify-write around it."""
    from test_xbios_ongibit import run as ongibit
    mask = 0x0F
    assert ENTRY_PORT_A | mask != ENTRY_PORT_A & mask
    assert ongibit(mask, poison=False)["regs"]["psg_events"] == expected_events(ENTRY_PORT_A | mask)
    assert run(mask, poison=False)["regs"]["psg_events"] == expected_events(ENTRY_PORT_A & mask)


@pytest.mark.parametrize("keep", (0x00FF, 0xFF00, 0x5AFF, 0xA500))
def test_only_the_low_byte_of_the_argument_is_read(keep):
    """`moveq #0,d2` / `move.w 4(sp),d2` / `and.b d2,d0` — the high byte is never looked at, so
    $ff00 clears the whole port exactly as $0000 does and $5aff keeps it exactly as $00ff does.

    WHAT THIS KILLS is a core that took the argument's OTHER half, `keep >> 8`: $ff00 would then
    keep the whole port where the ROM clears it, and $00ff would clear it where the ROM keeps it —
    the two ends, backwards. What it does NOT kill — measured, not assumed — is a core that AND-ed
    the whole WORD: `Giaccess` narrows what it is given to a byte (`giaccess.c`) and the port byte
    is already zero-extended, so `$a5 & $ff00` reaches the chip as the same 0 the ROM's `and.b`
    computes. That mutant is EQUIVALENT, and `gibit.c` says so at the cast."""
    assert run(keep, poison=False)["regs"]["psg_events"] == expected_events(ENTRY_PORT_A & keep)


def test_the_write_is_always_made_even_when_nothing_changes():
    """`Offgibit($ff)` is three chip accesses and not one — there is no "nothing to do" arm, and the
    ledger is the only thing that could say so."""
    info = run(0xFF, poison=False)
    assert info["regs"]["psg_events"] == expected_events(ENTRY_PORT_A)


def test_it_reads_and_writes_port_a_and_no_other_register():
    events = run(0xEF, poison=False)["regs"]["psg_events"]
    assert {reg for _kind, reg, _value in events} == {addrs.PSG_PORT_A}


def test_the_callers_whole_d0_comes_back_and_no_compared_image_byte_moves():
    """`movem.l (sp)+,d0-d2` puts the caller's D0 back, both halves of it. The writes that remain
    are the `movem` and `move.w sr` pushes, inside the band the diff drops, where a machine stack
    belongs."""
    info = run(0xEF, entry_d0=MARKED_D0, poison=False)
    assert info["regs"]["d0"] == MARKED_D0
    landed = sorted(address for address in info["writes"] if in_diff(address))
    assert landed == [], f"Offgibit stored into compared image at {[hex(a) for a in landed]}"
    assert info["regs"]["hw_writes"] == []


def test_the_internal_entry_that_clears_bit_4_is_still_above_this_body():
    """WHY $fc2ed8 IS NOT RECONSTRUCTED, held to the ROM's own bytes: `moveq #-17,d2` followed by a
    short branch into this routine BELOW its argument fetch. It is this body with a constant, and a
    reader who finds a caller of $fc2ed8 should land here rather than hunt for a third routine."""
    from harness import BASE_IMAGE
    internal_entry, shared_tail = 0xFC2ED8, 0xFC2F08
    moveq = int.from_bytes(bytes(BASE_IMAGE[internal_entry:internal_entry + 2]), "big")
    branch = int.from_bytes(bytes(BASE_IMAGE[internal_entry + 2:internal_entry + 4]), "big")
    assert moveq == 0x74EF, "the internal entry no longer loads $ef into D2"
    assert branch >> 8 == 0x60, "the internal entry no longer ends in a short branch"
    assert internal_entry + 4 + (branch & 0xFF) == shared_tail, (
        "the internal entry no longer branches into Offgibit's body")
    assert addrs.XBIOS_OFFGIBIT < shared_tail, "the shared tail is not inside Offgibit"


def test_the_oracles_cost_is_what_status_reports():
    """The Tier 3 denominator for this row, and the one the interrupt bracket shows up in. `ninsns`
    counts one more than the instructions executed (the reset iteration)."""
    from harness import emu, make_image
    _final, _writes, regs = emu.run(make_image(case.word_arg(0xEF)), addrs.XBIOS_OFFGIBIT,
                                    {"a5": 0}, psg_seed=ENTRY_FILE)
    assert (regs["ninsns"], regs["cycles"]) == (45, 664), (
        f"Offgibit now costs {regs['ninsns']} insns / {regs['cycles']} cycles — STATUS.md's Tier 3 "
        f"denominator for this row is stale")
