"""XBIOS Physbase (function $02) @ $fc0a92 — where the SHIFTER is reading the picture from.

Its sibling `Logbase` reports the system variable `_v_bas_ad`; this one asks the chip, out of two
bytes at $ff8201 and $ff8203 that hold address bits 23..16 and 15..8. The eight bits below them do
not exist — the shifter supplies zeroes — which is why an ST screen is 256-byte aligned and why this
routine can never return an odd address.

WHAT A CASE DECLARES IS THE MACHINE: `io_seed={SHIFTER_BASE_HIGH: hi, SHIFTER_BASE_MID: lo}` says
"the shifter held this pair", the harness hands the identical bytes to both sides, and the ordered
I/O read ledger — address, width and value, in order — is compared on every case (TRAP_MODEL.md,
Phase 15). The routine touches no image byte at all, so that ledger plus D0 is the whole of what a
green means, and the ORDER in it is a real claim: a reconstruction that read the two registers the
other way round assembles the same number out of a swapped pair and is separable by nothing else.

ARGUMENTS: none. The only entry convention that matters is the dispatcher's A5 = 0, which is not
even load-bearing here — the ROM spells both addresses absolutely (`move.b $ffff8201,d0`) rather
than off A5 as `Getrez` does.
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs, arm_candidate, differential, emu, report

import case

_lib.xbios_physbase.restype = ctypes.c_uint32

# The screen the captured snapshot is showing, as the two bytes the shifter holds it in. Asserted
# against `_v_bas_ad` in its own case below rather than taken on trust.
SNAPSHOT_BASE = 0x0F8000


def register_pair(base):
    """The two declared bytes for a 24-bit screen base."""
    return {addrs.SHIFTER_BASE_HIGH: (base >> 16) & 0xFF,
            addrs.SHIFTER_BASE_MID: (base >> 8) & 0xFF}


def _glue(lib, buf):
    del buf                       # the shifter is not in the image; see the module docstring
    return lib.xbios_physbase()


def run(base, poison=True, pokes=None):
    """One differential of XBIOS Physbase against a declared register pair. Returns its info."""
    return case.run(addrs.XBIOS_PHYSBASE, {"a5": 0, "_pokes": pokes or {}}, _glue,
                    io_seed=register_pair(base), poison=poison)


def test_the_snapshot_shows_the_screen_logbase_reports():
    """The one case whose numbers are the machine's rather than the battery's: the captured desktop
    has `_v_bas_ad` and the shifter agreeing, which is what makes SNAPSHOT_BASE a real base and not
    an invented one."""
    assert int.from_bytes(bytes(BASE_IMAGE[addrs.SYSVAR_V_BAS_AD:addrs.SYSVAR_V_BAS_AD + 4]),
                          "big") == SNAPSHOT_BASE


# Every pair that says something about the assembly, and each says something different:
#   - the snapshot's own screen;
#   - a pair whose two bytes are DISTINCT and neither zero, which is the only shape a swap moves;
#   - the two halves alone, so a reconstruction that dropped either is separable from one that did
#     not by the value rather than by luck;
#   - $800000, whose high byte has bit 7 set — the `lsl.w #8` runs while that byte is the whole
#     register, and a reconstruction that shifted the LONG there would still agree, but one that
#     assembled the pair in a signed 16-bit intermediate would not;
#   - $ffff00, the largest base the pair can describe, which is also the one that says bit 24 and
#     above stay clear.
BASES = (SNAPSHOT_BASE, 0x123400, 0x780000, 0x005600, 0x800000, 0xFF0000, 0x00FF00, 0xFFFF00)


@pytest.mark.parametrize("base", BASES)
def test_it_assembles_the_base_the_case_declares(base):
    info = run(base)
    assert info["regs"]["d0"] == base
    assert info["regs"]["io_events"] == [(addrs.SHIFTER_BASE_HIGH, 1, (base >> 16) & 0xFF),
                                         (addrs.SHIFTER_BASE_MID, 1, (base >> 8) & 0xFF)], (
        "the ROM did not read the two base registers in that order, so this case compared nothing "
        "about which register is which")


@pytest.mark.parametrize("base", BASES)
def test_the_low_eight_bits_of_the_address_do_not_exist(base):
    """`lsl.l #8` with nothing shifted in: the shifter has no register for them. A reconstruction
    that had assembled the pair into bits 15..0 instead passes every claim about WHICH byte is which
    and fails here."""
    assert run(base, poison=False)["regs"]["d0"] & 0xFF == 0


def test_the_two_registers_are_not_interchangeable():
    """THE SWAP, said as a comparison rather than as a value. Both orderings are run, and the claim
    is that they differ — which is what makes the ledger's ORDER above a fact about the routine and
    not a restatement of the declaration."""
    straight = run(0x123400, poison=False)["regs"]["d0"]
    swapped = run(0x341200, poison=False)["regs"]["d0"]
    assert straight == 0x123400 and swapped == 0x341200
    assert straight != swapped


def test_the_whole_pair_holds_over_every_byte_either_register_could_hold():
    """...and the 65,536-value range, HOST-SIDE against the armed candidate.

    `test_xbios_getrez.py`'s argument, one register wider: driving the range through the differential
    would be tens of thousands of restatements of the fact the eight cases above already pin — that
    the ROM and the reconstruction agree — where the thing the range is about is the reconstruction's
    own arithmetic, which no oracle is needed to ask. Swept as two lines through the square rather
    than the whole of it, because the assembly is separable in each byte independently.
    """
    for high in range(0x100):
        arm_candidate(io_seed=register_pair((high << 16) | 0x5A00))
        assert _lib.xbios_physbase() == (high << 16) | 0x5A00
    for mid in range(0x100):
        arm_candidate(io_seed=register_pair(0xA50000 | (mid << 8)))
        assert _lib.xbios_physbase() == 0xA50000 | (mid << 8)


def test_the_registers_are_not_served_out_of_the_image():
    """The claim ROM mode has to get right, as `test_xbios_getrez.py` makes it one register over:
    $ff8201 and $ff8203 are numerically INSIDE this project's 16 MB image and must still reach the
    declared map. A shim that served the image would answer the decoys."""
    decoys = {addrs.SHIFTER_BASE_HIGH: b"\xde", addrs.SHIFTER_BASE_MID: b"\xad"}
    info = run(SNAPSHOT_BASE, poison=False, pokes=decoys)
    assert info["regs"]["d0"] == SNAPSHOT_BASE, "the reads answered the image, not the declared map"


@pytest.mark.parametrize("declared,missing", ((addrs.SHIFTER_BASE_HIGH, addrs.SHIFTER_BASE_MID),
                                              (addrs.SHIFTER_BASE_MID, addrs.SHIFTER_BASE_HIGH)))
def test_declaring_only_one_of_the_pair_refuses_the_case_by_naming_the_other(declared, missing):
    """HALF A DECLARATION IS NOT A DECLARATION, and the refusal has to name the byte that is absent
    rather than the routine.

    Two registers is the smallest routine where the shape is reachable at all — `Getrez` reads one,
    so its declaration is present or it is not — and it is the mistake a reader makes when a routine
    acquires a second register: the case keeps working for the first read and the second is served
    the fabricated 0, so the base comes back with one byte of a machine that does not exist.
    """
    with pytest.raises(AssertionError, match=f"{missing:#x}"):
        differential(addrs.XBIOS_PHYSBASE, {"a5": 0}, _glue, io_seed={declared: 0x12})


def test_the_oracles_cost_is_what_status_reports():
    """The Tier 3 denominator for this row, measured rather than estimated. `ninsns` counts one more
    than the instructions executed (the reset iteration; shim.c's run loop says why)."""
    from harness import make_image
    _final, _writes, regs = emu.run(make_image(), addrs.XBIOS_PHYSBASE, {"a5": 0},
                                    io_seed=register_pair(SNAPSHOT_BASE))
    assert (regs["ninsns"], regs["cycles"]) == (7, 138), (
        f"Physbase now costs {regs['ninsns']} insns / {regs['cycles']} cycles — STATUS.md's Tier 3 "
        f"denominator for this row is stale")
