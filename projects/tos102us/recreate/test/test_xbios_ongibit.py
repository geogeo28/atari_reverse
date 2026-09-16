"""XBIOS Ongibit (function $1e) @ $fc2edc — set bits of the YM2149's port A.

Port A is where an ST keeps everything that is neither sound nor an ACIA: the two drive selects, the
side select, the printer strobe and the RS232 handshake lines. Setting one of them means preserving
the other seven, so the routine is a read-modify-write — and it makes it through `Giaccess` rather
than through the ports, `bsr`-ing two instructions INSIDE that routine ($fc2eac) with its arguments
already in D0/D1.

WHAT THAT MEANS FOR A CASE: the chip is reached three times, in one order, and the order is the
claim. `Giaccess` reads the selected register back after writing it, so the ordered PSG access ledger
is READ 14 / WRITE 14 / READ 14 — and the third entry is what says the write went to port A rather
than to whatever the select latch happened to hold (TRAP_MODEL.md, Phase 6). `psg_seed={14: byte}`
is what the case declares the chip held.

ONLY THE LOW BYTE OF THE ARGUMENT REACHES THE CHIP. `moveq #0,d2` / `move.w 4(sp),d2` zero-extends
the word and `or.b d2,d0` then uses one byte of it — the high byte is not masked away, it is never
read. So `Ongibit($ff01)` sets bit 0 and nothing else, which is why the sweeps below are over WORDS.

IT SETS NO RESULT, AND THAT IS A CLAIM ABOUT D0. `movem.l (sp)+,d0-d2` puts the caller's D0 back
over the byte the second `Giaccess` read, which is the difference between this and `Giaccess` itself
— whose whole point is the byte it hands back. So the core takes the entering D0 and returns it, and
`case.FULL_D0` compares all 32 bits of it against the D0 the ROM left: a `void` core would have said
nothing about the register and would have agreed with one that handed the port byte back.

THE OUTER INTERRUPT BRACKET (`ori.w #$700,sr` around BOTH calls, not just each one) is what makes the
read-modify-write atomic against the 200 Hz sound driver, which writes $ff8800 from a timer
interrupt. It is invisible here — the oracle enters at IPL 7 and reports no SR — and shows only in
the Tier 3 cycle count, which is why `bench/tier3.py` pins this row.
"""
import ctypes

import pytest

from harness import OS_PSG_EVENT_READ, OS_PSG_EVENT_WRITE, _lib, addrs, in_diff

import case

_lib.xbios_ongibit.argtypes = [ctypes.c_uint32, ctypes.c_uint16]
_lib.xbios_ongibit.restype = ctypes.c_uint32

# What a case declares port A held on entry: a byte with bits on both sides of every mask below, so
# "preserved the other seven" is separable from "wrote the mask" on the value rather than by luck.
ENTRY_PORT_A = 0xA5
# The other fifteen registers, declared too, so that a reconstruction reading the WRONG one is served
# a DIFFERENT byte rather than refused — a refusal reads as a harness problem, a wrong value as the
# defect it is.
ENTRY_FILE = {reg: (0x30 ^ (reg * 0x11)) & 0xFF for reg in range(addrs.GIACCESS_REGISTER_MASK + 1)}
ENTRY_FILE[addrs.PSG_PORT_A] = ENTRY_PORT_A
# A caller's D0 with both halves marked, for the claim that the `movem` pair gives the whole register
# back — and marked in the LOW byte too, which is the half the second `Giaccess` read lands in.
MARKED_D0 = 0xDEAD_BEEF


def expected_events(result):
    """The chip accesses both routines make, in order: select-and-read, select-write-and-read-back."""
    return [(OS_PSG_EVENT_READ, addrs.PSG_PORT_A, ENTRY_PORT_A),
            (OS_PSG_EVENT_WRITE, addrs.PSG_PORT_A, result),
            (OS_PSG_EVENT_READ, addrs.PSG_PORT_A, result)]


def run(bits, entry_d0=0, poison=True):
    def glue(lib, buf):
        del buf                     # the chip is not in the image; see the module docstring
        return lib.xbios_ongibit(entry_d0, bits & 0xFFFF)

    return case.run(addrs.XBIOS_ONGIBIT,
                    {"a5": 0, "d0": entry_d0, "_pokes": case.word_arg(bits)}, glue,
                    psg_seed=ENTRY_FILE, poison=poison)


# Masks that say something different about the OR: each single bit (eight cases, so a reconstruction
# that set the wrong one diverges); a mask already set in the entry byte, which must change nothing;
# the whole byte; and 0, which must leave the port as it was and still write it.
SINGLE_BITS = tuple(1 << bit for bit in range(8))
MASKS = SINGLE_BITS + (ENTRY_PORT_A, 0xFF, 0x00)


@pytest.mark.parametrize("bits", MASKS)
def test_it_sets_the_bits_and_preserves_the_rest(bits):
    """The whole claim, over the chip's ordered access ledger — which is the only witness there is:
    the port is off-image, so nothing in the memory diff could tell a correct write from none."""
    info = run(bits)
    assert info["regs"]["psg_events"] == expected_events(ENTRY_PORT_A | bits)


@pytest.mark.parametrize("bits", (0x0100, 0xFF00, 0xA500, 0x1200))
def test_the_high_byte_of_the_argument_is_never_read(bits):
    """`or.b d2,d0` — so an argument whose low byte is 0 writes the port back unchanged however many
    bits are set above it.

    WHAT THIS KILLS is a core that took the argument's OTHER half, `bits >> 8`: every case here then
    sets the bits of that high byte, and $ff00 writes $ff where the ROM writes the entry byte. What
    it does NOT kill — measured, not assumed — is a core that OR-ed the whole WORD: `Giaccess`
    narrows what it is given to a byte (`giaccess.c`), and the port byte is already zero-extended,
    so the bits above 7 are dropped on the way to the chip and the mutant is EQUIVALENT rather than
    a hole (`gibit.c` says so at the cast)."""
    info = run(bits, poison=False)
    assert info["regs"]["psg_events"] == expected_events(ENTRY_PORT_A)


@pytest.mark.parametrize("bits", (0x0001, 0xFF01, 0x8001))
def test_the_low_byte_is_read_whatever_is_above_it(bits):
    """...and the other half of the same claim, so that "never read" is not satisfied by a
    reconstruction that ignored the argument altogether."""
    assert run(bits, poison=False)["regs"]["psg_events"] == expected_events(ENTRY_PORT_A | 1)


def test_the_write_is_always_made_even_when_nothing_changes():
    """`Ongibit(0)` is three chip accesses and not one. There is no `tst`/`bmi` here and no "nothing
    to do" arm — a reconstruction that skipped a write whose value equalled the read is separable
    only by this ledger."""
    info = run(0, poison=False)
    assert len(info["regs"]["psg_events"]) == 3
    assert info["regs"]["psg_events"][1] == (OS_PSG_EVENT_WRITE, addrs.PSG_PORT_A, ENTRY_PORT_A)


def test_it_reads_and_writes_port_a_and_no_other_register():
    """Every access names register 14. The entry file declares a DIFFERENT byte for each of the
    other fifteen, so a reconstruction that selected one of them is served its byte and diverges on
    the value as well as on the register."""
    events = run(0x04, poison=False)["regs"]["psg_events"]
    assert {reg for _kind, reg, _value in events} == {addrs.PSG_PORT_A}


def test_the_callers_whole_d0_comes_back_and_no_compared_image_byte_moves():
    """`movem.l (sp)+,d0-d2` puts the caller's D0 back, so the byte the second `Giaccess` read never
    reaches the caller — and the routine's whole effect is the chip. Both halves of the register are
    marked, because the byte that would leak into it is one byte wide.

    "No COMPARED image byte" rather than "no write": the two `movem`s and the two `move.w sr` push
    onto the machine stack, which is inside the band the diff drops and is where those belong."""
    info = run(0x04, entry_d0=MARKED_D0, poison=False)
    assert info["regs"]["d0"] == MARKED_D0
    landed = sorted(address for address in info["writes"] if in_diff(address))
    assert landed == [], f"Ongibit stored into compared image at {[hex(a) for a in landed]}"
    assert info["regs"]["hw_writes"] == []


def test_the_oracles_cost_is_what_status_reports():
    """The Tier 3 denominator for this row, and the one the interrupt bracket shows up in. `ninsns`
    counts one more than the instructions executed (the reset iteration)."""
    from harness import emu, make_image
    _final, _writes, regs = emu.run(make_image(case.word_arg(0x04)), addrs.XBIOS_ONGIBIT,
                                    {"a5": 0}, psg_seed=ENTRY_FILE)
    assert (regs["ninsns"], regs["cycles"]) == (45, 664), (
        f"Ongibit now costs {regs['ninsns']} insns / {regs['cycles']} cycles — STATUS.md's Tier 3 "
        f"denominator for this row is stale")
