"""XBIOS Setscreen (function $05) @ $fc0ab8 — the logical base, the physical base, the resolution.

Three settings behind one call, each skipped when its own argument is negative, and — unlike
`Kbrate`, whose negative first argument skips the second store as well — INDEPENDENT: the ROM's
three `bmi`s each fall through to the next test. `Setscreen(-1, base, -1)` is the ordinary screen
flip and is what this routine is called for at run time.

TWO OF THE THREE ARE VERIFIED HERE AND THE THIRD HALTS. The resolution arm ends in
`jsr $fca914`, the console driver's re-initialisation — a font choice, the Line-A/VT52 setup at
$fc4a48, a dozen words of console state and a tail call — which is a subsystem rather than an
instruction, and whose other end (the VBL handler reloading $ff8260 from the byte the arm stores) is
the interrupt half of this wave. `setscreen.c` says why a HALF-reconstructed arm would be worse than
none; the cases below drive the two arms that are whole, and the ones at the bottom hold the third's
absence to something checkable.

THE PHYSICAL BASE IS NOT STORED AS A LONGWORD. `move.b 9(sp),$ffff8201` / `move.b 10(sp),$ffff8203`
takes bits 23..16 and 15..8 out of the argument and drops the rest — bits 31..24 never reach the
chip and bits 7..0 do not exist (`physbase.c`). Those two stores are off-image on both sides, so
what compares them is `hw.h`'s ordered write ledger: address, width and value, in order, on every
case (TRAP_MODEL.md, Phase 10). A reconstruction that made no store at all is byte-for-byte
identical to a correct one without it.

IT SETS NO RESULT, AND THAT IS A CLAIM ABOUT D0. Both reconstructed arms fall through to the same
`rts` without touching the register, so the caller's own comes back whole — the core takes the
entering D0 and returns it, and `case.FULL_D0` compares all 32 bits of it on every case here. A
`void` core would have agreed with one that invented a status.
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs

import abi
import case

_lib.xbios_setscreen.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32, ctypes.c_uint32,
                                 ctypes.c_uint32, ctypes.c_uint16]
_lib.xbios_setscreen.restype = ctypes.c_uint32

# "Leave this one alone", at each argument's own width — the ROM tests `tst.l` for the two bases and
# `tst.w` for the resolution.
KEEP_LONG = 0xFFFFFFFF
KEEP_WORD = 0xFFFF
# The screen the snapshot is showing (`test_xbios_physbase.py` pins it against the shifter's own
# registers) and a second one a page below it, for the case that stores what is already there.
SNAPSHOT_BASE = 0x0F8000
ANOTHER_BASE = 0x090000
# A caller's D0 with both halves marked, for the claim that the routine leaves the whole register.
MARKED_D0 = 0xDEAD_BEEF


def argument_poke(logical, physical, resolution):
    """The three argument slots, where the dispatcher's caller would have left them: two longwords
    and a word, at 4(sp), 8(sp) and 12(sp)."""
    return {abi.FIRST_ARG: struct.pack(">IIH", logical & 0xFFFFFFFF, physical & 0xFFFFFFFF,
                                              resolution & 0xFFFF)}


def run(logical, physical, resolution=KEEP_WORD, entry_d0=0, pokes=None, poison=True):
    # Every case in this file keeps the resolution, and this is what says so rather than the reader
    # having to check: a non-negative one HALTS the candidate at the top of the unreconstructed arm
    # (`setscreen.c`), so a case that passed one would die in the core rather than red on a claim.
    assert resolution & 0x8000, "the resolution arm halts the candidate — see the module docstring"

    def glue(lib, buf):
        return lib.xbios_setscreen(buf, entry_d0, logical & 0xFFFFFFFF, physical & 0xFFFFFFFF,
                                   resolution & 0xFFFF)

    return case.run(addrs.XBIOS_SETSCREEN,
                    {"a5": 0, "d0": entry_d0,
                     "_pokes": {**argument_poke(logical, physical, resolution), **(pokes or {})}},
                    glue, poison=poison)


def shifter_stores(base):
    """The two ledger entries a physical base of `base` must produce, in the ROM's own order."""
    return [(addrs.SHIFTER_BASE_HIGH, 1, (base >> 16) & 0xFF),
            (addrs.SHIFTER_BASE_MID, 1, (base >> 8) & 0xFF)]


# ---- the logical base -----------------------------------------------------------------------------

# Bases that say something different about the store: an ordinary one, zero (a screen at address 0 is
# nonsense and the routine does not care — it stores, it does not validate), the largest NON-negative
# longword, and the value the machine already holds.
LOGICAL_BASES = (ANOTHER_BASE, 0x000000, 0x7FFFFFFF, SNAPSHOT_BASE)


@pytest.mark.parametrize("logical", LOGICAL_BASES)
def test_a_non_negative_logical_base_lands_in_v_bas_ad(logical):
    """Read back out of the ORACLE's write ledger, so a field the routine never stored is a KeyError
    naming it rather than a stale byte that happens to read right — and so `SNAPSHOT_BASE`, which is
    already there, is a store the poison pass has to attribute."""
    info = run(logical, KEEP_LONG)
    assert case.written_long(info, addrs.SYSVAR_V_BAS_AD) == logical
    assert info["regs"]["hw_writes"] == [], "a call with a negative physical base touched the chip"


@pytest.mark.parametrize("logical", (KEEP_LONG, 0x80000000, 0xFFFFFFFE))
def test_a_negative_logical_base_leaves_v_bas_ad_alone(logical):
    """`tst.l`/`bmi` — every pointer with bit 31 set only reports, of which -1 is the documented
    spelling. $80000000 is the boundary itself."""
    info = run(logical, KEEP_LONG)
    assert addrs.SYSVAR_V_BAS_AD not in info["writes"]


# ---- the physical base ----------------------------------------------------------------------------

# Bases that say something different about WHICH bytes reach the chip: an ordinary one; one whose
# four bytes are all distinct, which is the only shape that separates "bits 23..8" from any other
# pair; one whose dropped low byte is non-zero; and the largest non-negative longword, whose top byte
# is $7f and must not appear in either store.
PHYSICAL_BASES = (ANOTHER_BASE, 0x12345678, 0x00ABCDEF, 0x7FFFFFFF)


@pytest.mark.parametrize("physical", PHYSICAL_BASES)
def test_a_non_negative_physical_base_reaches_the_shifter_as_two_bytes(physical):
    info = run(KEEP_LONG, physical)
    assert info["regs"]["hw_writes"] == shifter_stores(physical), (
        "the ROM did not store bits 23..16 then 15..8 of the argument to $ff8201 and $ff8203")
    assert info["writes"] == {}, "a call with a negative logical base wrote the image"


@pytest.mark.parametrize("physical", (KEEP_LONG, 0x80000000, 0xFFFFFFFE))
def test_a_negative_physical_base_leaves_the_shifter_alone(physical):
    info = run(KEEP_LONG, physical)
    assert info["regs"]["hw_writes"] == []


def test_the_dropped_bytes_are_dropped_and_not_rounded():
    """$12345678 sets the screen to $345600. The top byte is not an error and the low byte is not
    rounded up — neither has a register, so neither is looked at."""
    info = run(KEEP_LONG, 0x12345678, poison=False)
    assert [value for _addr, _width, value in info["regs"]["hw_writes"]] == [0x34, 0x56]


# ---- the two together -----------------------------------------------------------------------------

def test_the_two_bases_are_independent():
    """THE CLAIM `Kbrate` DOES NOT HAVE. A negative logical base does not skip the physical store,
    and the pair set together sets both — three calls, because "independent" is a statement about
    the combinations rather than about either one."""
    both = run(ANOTHER_BASE, 0x00ABCDEF)
    assert case.written_long(both, addrs.SYSVAR_V_BAS_AD) == ANOTHER_BASE
    assert both["regs"]["hw_writes"] == shifter_stores(0x00ABCDEF)

    logical_only = run(ANOTHER_BASE, KEEP_LONG)
    assert case.written_long(logical_only, addrs.SYSVAR_V_BAS_AD) == ANOTHER_BASE
    assert logical_only["regs"]["hw_writes"] == []

    physical_only = run(KEEP_LONG, 0x00ABCDEF)
    assert addrs.SYSVAR_V_BAS_AD not in physical_only["writes"]
    assert physical_only["regs"]["hw_writes"] == shifter_stores(0x00ABCDEF)


def test_a_call_that_keeps_everything_does_nothing_at_all():
    """`Setscreen(-1, -1, -1)` — every arm skipped, so the routine is three tests and an `rts`. The
    case that would catch a reconstruction which stored a default somewhere."""
    info = run(KEEP_LONG, KEEP_LONG, KEEP_WORD)
    assert info["writes"] == {} and info["regs"]["hw_writes"] == []


@pytest.mark.parametrize("logical,physical", ((ANOTHER_BASE, 0x00ABCDEF), (KEEP_LONG, KEEP_LONG)))
def test_the_callers_whole_d0_comes_back(logical, physical):
    """NEITHER RECONSTRUCTED ARM WRITES D0: both fall through to the same `rts`, so the caller's own
    register survives the call. `case.run` compares the candidate's result against the ROM's D0 on
    every case in this file; these two mark BOTH halves of it, over the arm that stores and the arm
    that does nothing, so a core that had invented a result — a status, or the base it stored — is
    separable. (The resolution arm WOULD leave `Vsync`'s sampled `_frclock` there, and it halts.)"""
    info = run(logical, physical, entry_d0=MARKED_D0, poison=False)
    assert info["regs"]["d0"] == MARKED_D0


# ---- the resolution arm, which is NOT reconstructed -------------------------------------------------

def test_the_resolution_arm_still_jumps_into_the_console_driver():
    """WHY THE ARM IS ABSENT, held to something that would change if the ROM did.

    `setscreen.c` halts on a non-negative resolution because the arm ends in a call into the console
    driver's re-initialisation. That is a claim about the ROM's own bytes, and this is it: the
    instruction at $fc0af6 is a `jsr` to an address inside the ROM which is not one of the routines
    this project has reconstructed. A reader who wants the arm has to reconstruct THAT, and this case
    is what says so from the suite rather than only from a comment.
    """
    jsr_at = 0xFC0AF6
    opcode = int.from_bytes(bytes(BASE_IMAGE[jsr_at:jsr_at + 2]), "big")
    target = int.from_bytes(bytes(BASE_IMAGE[jsr_at + 2:jsr_at + 6]), "big")
    assert opcode == 0x4EB9, "the resolution arm no longer ends in a `jsr <abs.l>`"
    assert addrs.ROM_BASE <= target < addrs.ROM_BASE + addrs.ROM_BYTES
    assert target == 0xFCA914, (
        f"the console re-initialisation moved to {target:#x}; setscreen.c's halt names $fca914")


def test_the_oracles_cost_is_what_status_reports():
    """The Tier 3 denominator for the two cases priced. `ninsns` counts one more than the
    instructions executed (the reset iteration; shim.c's run loop says why)."""
    from harness import emu, make_image
    for logical, physical, expected in ((ANOTHER_BASE, 0x00ABCDEF, (11, 202)),
                                        (KEEP_LONG, KEEP_LONG, (8, 130))):
        _final, _writes, regs = emu.run(make_image(argument_poke(logical, physical, KEEP_WORD)),
                                        addrs.XBIOS_SETSCREEN, {"a5": 0})
        assert (regs["ninsns"], regs["cycles"]) == expected, (
            f"Setscreen({logical:#x}, {physical:#x}) now costs {regs['ninsns']} insns / "
            f"{regs['cycles']} cycles — STATUS.md's Tier 3 denominator for this row is stale")
