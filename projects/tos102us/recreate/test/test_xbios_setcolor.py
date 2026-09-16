"""XBIOS Setcolor (function $07) @ $fc0b0e — one shifter colour register, reported and replaced.

The other half of `Setpalette`'s row of sixteen words at $ff8240, reached the opposite way: this one
writes the register itself, now, wherever the beam happens to be, and hands back what was in it.

THREE CLAIMS, AND EACH IS A DIFFERENT INSTRUCTION.

  * THE INDEX CANNOT LEAVE THE ROW. `add.w d1,d1` doubles inside a WORD and `andi.w #$1f` then keeps
    five bits, so the byte offset is even and in 0..30 for every argument there is: colour 16 is
    colour 0, colour -1 ($ffff, doubled to $fffe) is colour 15, and there is no bounds test anywhere.
    A reconstruction that masked with $3f, or that dropped the doubling, diverges on the cases
    parametrized below — and one that computed the product in 32 bits does NOT, which is a fact
    about the mask rather than a gap in these cases (see that test).
  * THE MASK IS ON THE WAY OUT, NOT ON THE WAY IN. `andi.w #$777` is applied to the value REPORTED,
    because an ST shifter decodes three bits per gun; the value STORED goes to the register exactly
    as the caller gave it. On a real machine the two are indistinguishable, and here the hardware
    write ledger is what tells them apart (TRAP_MODEL.md, Phase 10).
  * THE RESULT IS A WORD OF A 32-BIT REGISTER. `move.w 0(a0,d1.w),d0` leaves D0's high half as the
    caller had it, so the core takes the caller's D0 and returns the whole register — `kbrate.c`'s
    note, over a routine whose low word comes from the chip rather than from RAM.

THE READ-BACK IS A DECLARED WORD. `io_seed` is keyed by BYTE, so a case declares BOTH bytes of the
register it expects to be read and a half-declared one refuses whole, naming the byte that is missing
(TRAP_MODEL.md, Phase 15). That is also what makes the index claims sharp: the register the routine
actually reads is the one whose declaration was used, and the ordered read ledger says which.

The routine touches no image byte at all — one declared read, one ledgered store, and D0.
"""
import ctypes

import pytest

from harness import _lib, addrs, differential, emu, report

import case

_lib.xbios_setcolor.argtypes = [ctypes.c_uint32, ctypes.c_uint16, ctypes.c_uint16]
_lib.xbios_setcolor.restype = ctypes.c_uint32

KEEP = 0xFFFF
# A caller's D0 with a marked high half, for the claim about what the `move.w` leaves alone.
MARKED_D0 = 0xDEAD_0000
# The sixteen colour registers the index arithmetic can reach, derived from the mask rather than
# counted out: five bits of even byte offset is sixteen words.
REGISTERS = tuple(range(addrs.SHIFTER_PALETTE,
                        addrs.SHIFTER_PALETTE + addrs.SETCOLOR_INDEX_MASK + 1,
                        addrs.PALETTE_ENTRY_BYTES))


def _entry_word(index):
    """What a case declares register `index` held: red 4, green the index's high bit, blue its low
    three — an ST colour word, DISTINCT per register so that a reconstruction reading the wrong one
    diverges on the value rather than by luck, and entirely INSIDE $777 so that what a case reports
    is what it declared. The masking claims below use words that are not."""
    return 0x0400 | (((index >> 3) & 1) << 4) | (index & 7)


ENTRY_ROW = {reg: _entry_word(index) for index, reg in enumerate(REGISTERS)}


def declared(register, value):
    """The two `io_seed` bytes of one palette register."""
    return {register: (value >> 8) & 0xFF, register + 1: value & 0xFF}


def register_of(colour):
    """Which register the ROM's `add.w`/`andi.w #$1f` sends `colour` to."""
    return addrs.SHIFTER_PALETTE + ((colour * addrs.PALETTE_ENTRY_BYTES) & addrs.SETCOLOR_INDEX_MASK)


def run(colour, value, held=None, entry_d0=0, poison=True):
    """One differential of XBIOS Setcolor, declaring `held` in the register the case expects it to
    read (its own entry from `ENTRY_ROW` by default). Returns the oracle's info."""
    register = register_of(colour)
    held = ENTRY_ROW[register] if held is None else held

    def glue(lib, buf):
        del buf                       # the palette is not in the image; see the module docstring
        return lib.xbios_setcolor(entry_d0, colour & 0xFFFF, value & 0xFFFF)

    return case.run(addrs.XBIOS_SETCOLOR,
                    {"a5": 0, "d0": entry_d0, "_pokes": case.word_args(colour, value)}, glue,
                    io_seed=declared(register, held), poison=poison)


def reported(info):
    """The WORD the routine reports — D0's low half, which is all it sets."""
    return info["regs"]["d0"] & 0xFFFF


# ---- which register, and what it reports ----------------------------------------------------------

@pytest.mark.parametrize("colour", range(len(REGISTERS)))
def test_each_colour_reads_and_reports_its_own_register(colour):
    """All sixteen, against a row with a distinct word per register: the value alone says which one
    was read, and the ordered read ledger says it again with the address."""
    register = register_of(colour)
    info = run(colour, KEEP)
    assert reported(info) == ENTRY_ROW[register]
    assert info["regs"]["io_events"] == [(register, 2, ENTRY_ROW[register])], (
        "the ROM did not read one WORD of the colour register the index names")


# Colour numbers that WRAP, as (the argument, the colour it lands on) — the in-range ones are the
# parametrized case above, and a pair naming itself would restate it. 16 and 24 wrap onto 0 and 8;
# $8000's doubling wraps the WORD to 0; $ffff (-1) doubles to $fffe and lands on colour 15; $0fff is
# an arbitrary large one.
WRAPPING_COLOURS = ((16, 0), (24, 8), (0x8000, 0), (0xFFFF, 15), (0x0FFF, 15))


@pytest.mark.parametrize("colour,equivalent", WRAPPING_COLOURS)
def test_the_index_wraps_into_the_row_rather_than_leaving_it(colour, equivalent):
    """No bounds test exists and none is needed. A reconstruction that masked with $3f leaves the row
    for colours 16..31, and one that dropped the doubling sends every odd colour to its neighbour.

    WHAT THIS CANNOT CATCH, measured rather than assumed: the WIDTH of the doubling. `add.w` wraps at
    $10000 and a 32-bit product does not, but the five-bit mask discards every bit the wrap could
    have moved — so a core computing it either way is the same function, and a mutant that does is
    EQUIVALENT rather than a hole (`palette.c` says so at the call site). $8000 and $ffff are here as
    the arguments that WOULD separate them if the mask were wider."""
    assert register_of(colour) == register_of(equivalent)
    info = run(colour, KEEP)
    assert reported(info) == ENTRY_ROW[register_of(equivalent)]


# ---- the mask on the way out ----------------------------------------------------------------------

# Register contents that the reporting mask acts on: all bits set; the bits OUTSIDE $777 alone, which
# a reconstruction that forgot the mask reports and a correct one reports as 0; the mask itself; and
# one value with bits on both sides of it.
MASK_BOUNDARIES = ((0xFFFF, 0x0777), (0xF888, 0x0000), (0x0777, 0x0777), (0x0F5A, 0x0752))


@pytest.mark.parametrize("held,expected", MASK_BOUNDARIES)
def test_only_three_bits_per_gun_are_reported(held, expected):
    """`andi.w #$777,d0` — the twelve bits an ST shifter decodes, out of a register that reads back
    whatever the hardware felt like in the other four."""
    assert reported(run(0, KEEP, held=held, poison=False)) == expected


# ---- the store ------------------------------------------------------------------------------------

# Values that separate "stored as given" from "stored masked": one inside the mask, one with every
# bit set, one with only bits outside the mask, and 0.
STORED_VALUES = (0x0123, 0x7FFF, 0x7888, 0x0000)


@pytest.mark.parametrize("value", STORED_VALUES)
@pytest.mark.parametrize("colour", (0, 7, 15))
def test_a_non_negative_value_is_stored_to_that_register_unmasked(colour, value):
    """THE HALF THAT A REAL MACHINE CANNOT SHOW. The shifter ignores the bits outside $777, so a
    reconstruction that masked the stored value too is correct on hardware and wrong here — which is
    what the ordered write ledger is for."""
    info = run(colour, value)
    assert info["regs"]["hw_writes"] == [(register_of(colour), 2, value)]


@pytest.mark.parametrize("value", (KEEP, 0x8000, 0xFF80))
def test_a_negative_value_reports_without_storing(value):
    """`tst.w 6(sp)` / `bmi` — tested at the ROM's own width, so $8000 is a read and the value's low
    byte says nothing. $ff80 is the one whose low byte looks positive."""
    info = run(3, value)
    assert info["regs"]["hw_writes"] == []
    assert reported(info) == ENTRY_ROW[register_of(3)]


def test_it_reports_the_value_it_is_replacing():
    """The read happens BEFORE the `bmi`, so a call that stores still reports the OLD contents. A
    reconstruction that reported what it had just written passes every keep-only case above."""
    info = run(5, 0x0246)
    assert reported(info) == ENTRY_ROW[register_of(5)]
    assert info["regs"]["hw_writes"] == [(register_of(5), 2, 0x0246)]


# ---- the width of the result ------------------------------------------------------------------------

@pytest.mark.parametrize("value", (KEEP, 0x0246))
def test_the_callers_high_half_of_d0_survives(value):
    """`move.w`, not `moveq #0,d0` first — the routine writes D0's low word and leaves the rest, on
    both arms. A `uint16_t` core would agree with one that had cleared it."""
    info = run(2, value, entry_d0=MARKED_D0, poison=False)
    assert info["regs"]["d0"] == MARKED_D0 | ENTRY_ROW[register_of(2)]


# ---- the model's own claims -------------------------------------------------------------------------

def test_the_register_is_not_served_out_of_the_image():
    """$ff8240 is numerically INSIDE this project's 16 MB image and must still reach the declared
    map, as `test_xbios_getrez.py` pins one register over. A decoy planted at the register would be
    reported instead of the declared word if the shim served the image."""
    register = register_of(4)
    diffs, info = differential(addrs.XBIOS_SETCOLOR,
                               {"a5": 0, "d0": 0,
                                "_pokes": {**case.word_args(4, KEEP), register: b"\x0d\xec"}},
                               lambda lib, buf: lib.xbios_setcolor(0, 4, KEEP),
                               io_seed=declared(register, ENTRY_ROW[register]))
    assert not diffs, report(diffs)
    assert reported(info) == ENTRY_ROW[register], "the read answered the image, not the declared map"


def test_declaring_only_one_byte_of_the_word_refuses_the_case():
    """A WIDE READ IS N DECLARED BYTES. The routine reads a word, so a case that declared one byte of
    it is refused whole and names the byte that is absent — rather than serving half a register and
    verifying the reconstruction against a word that is half fabricated."""
    register = register_of(0)
    with pytest.raises(AssertionError, match=f"{register + 1:#x}"):
        differential(addrs.XBIOS_SETCOLOR,
                     {"a5": 0, "d0": 0, "_pokes": case.word_args(0, KEEP)},
                     lambda lib, buf: lib.xbios_setcolor(0, 0, KEEP),
                     io_seed={register: 0x01})


def test_the_oracles_cost_is_what_status_reports():
    """The Tier 3 denominator for the two cases priced. `ninsns` counts one more than the
    instructions executed (the reset iteration; shim.c's run loop says why)."""
    from harness import make_image
    for colour, value, expected in ((3, KEEP, (10, 140)), (3, 0x0246, (11, 160))):
        register = register_of(colour)
        _final, _writes, regs = emu.run(make_image(case.word_args(colour, value)),
                                        addrs.XBIOS_SETCOLOR, {"a5": 0, "d0": 0},
                                        io_seed=declared(register, ENTRY_ROW[register]))
        assert (regs["ninsns"], regs["cycles"]) == expected, (
            f"Setcolor({colour}, {value:#x}) now costs {regs['ninsns']} insns / {regs['cycles']} "
            f"cycles — STATUS.md's Tier 3 denominator for this row is stale")
