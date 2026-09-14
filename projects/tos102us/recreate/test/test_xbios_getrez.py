"""XBIOS Getrez (function 4) @ $fc0aac — the shifter's current screen resolution.

THE FIRST RECONSTRUCTION IN THIS PROJECT THAT READS A HARDWARE REGISTER, and it is three
instructions: `moveq #0,d0` / `move.b $ffff8260,d0` / `and.b #3,d0`. Its sibling `Logbase` reports a
system variable and `Random` an OS global; this one asks the machine, and until the DECLARED I/O MAP
existed there was no way to ask it honestly — `$ff8260` is named by no Phase-7 slot, so both cores
answered it a fabricated 0 and a differential would have gone green reporting LOW resolution
whatever machine the case meant. `test_boot_snapshot.py` drives the refusal that made that loud.

WHAT A CASE DECLARES IS THE MACHINE, not a convenience: `io_seed={SHIFTER_RESOLUTION: byte}` says
"the shifter held this", the harness hands the identical byte to both sides, and the ordered I/O
read ledger — address, width and value — is compared on every case (TRAP_MODEL.md, Phase 15). The
routine touches no image byte at all, so that ledger plus D0 is the whole of what a green means.

ARGUMENTS: none. Getrez takes none, so the only entry convention that matters is the dispatcher's
A5 = 0 — which is load-bearing here rather than incidental, because the ROM reaches the register
through a 16-bit displacement off it (`move.b -32160(a5),d0`).
"""
import ctypes

import pytest

from harness import _lib, addrs, arm_candidate, differential, emu, report

_lib.xbios_getrez.restype = ctypes.c_uint8

# Every byte of the register whose low two bits the ST really produces, plus what the three ST
# resolutions are called. The high six bits are undefined on an ST and the ROM masks them away,
# which is what the wider sweep below is about.
ST_LOW, ST_MEDIUM, ST_HIGH = 0, 1, 2
RESOLUTIONS = (ST_LOW, ST_MEDIUM, ST_HIGH)


def _glue(lib, buf):
    del buf                       # the shifter is not in the image; see the module docstring
    return lib.xbios_getrez()


def run(register_byte, poison=True):
    """One differential of XBIOS Getrez against a declared shifter byte. Returns its info."""
    diffs, info = differential(addrs.XBIOS_GETREZ, {"a5": 0}, _glue,
                               io_seed={addrs.SHIFTER_RESOLUTION: register_byte}, poison=poison)
    assert not diffs, report(diffs)
    assert info["ret"] == info["regs"]["d0"], (
        f"the candidate returned {info['ret']:#x} where the ROM left {info['regs']['d0']:#x} in D0")
    return info


@pytest.mark.parametrize("resolution", RESOLUTIONS)
def test_it_reports_the_resolution_the_case_declares(resolution):
    """The three modes an ST shifter really sits in. Parametrized rather than run once, because a
    reconstruction that hardcoded any single answer would pass a one-value case — which is exactly
    what a port written against the fabricated 0 looks like."""
    info = run(resolution)
    assert info["regs"]["d0"] == resolution
    assert info["regs"]["io_events"] == [(addrs.SHIFTER_RESOLUTION, 1, resolution)], (
        "the ROM did not read the shifter, so this case compared nothing about the register")


# The bytes the mask's behaviour turns on: each of the four values it can produce, the first byte
# with a high bit set, the byte whose low bits are zero and whose high bits are all ones, a byte with
# nothing but high bits, and the all-ones byte. A reconstruction that returned the raw byte, masked
# with `$07`, or compared the whole byte against 2 diverges on at least one of them.
MASK_BOUNDARIES = (0x00, 0x01, 0x02, 0x03, 0x04, 0x7F, 0xFC, 0xFF)


@pytest.mark.parametrize("register_byte", MASK_BOUNDARIES)
def test_only_the_low_two_bits_reach_the_caller(register_byte):
    """`and.b #3,d0`, against the ROM, at the bytes the mask turns on.

    The upper six bits are not defined on an ST — an STE uses bit 2 of the neighbouring register,
    not this one — and the ROM masks them rather than trusting them. What a DIFFERENTIAL adds over
    the sweep below is the ROM's own agreement, which is a claim about the INSTRUCTION and needs a
    handful of bytes rather than all of them: eight that exercise every boundary the mask has.
    """
    assert run(register_byte, poison=False)["regs"]["d0"] == register_byte & addrs.GETREZ_MODE_MASK


def test_the_mask_holds_over_every_byte_the_register_could_hold():
    """...and the whole 256-value range, HOST-SIDE against the armed candidate.

    Sweeping the range through the differential works and costs about two seconds; what is wrong
    with it is the SHAPE of the claim, not the time. 256 identical runs of a three-instruction ROM
    routine are 256 restatements of one fact the eight cases above already pin — that the ROM and
    the reconstruction agree — while the thing the range is really about is the reconstruction's own
    mask, which no oracle is needed to ask. So the candidate is armed with each declaration exactly
    as `differential` arms it and asked directly.
    """
    for register_byte in range(0x100):
        arm_candidate(io_seed={addrs.SHIFTER_RESOLUTION: register_byte})
        assert _lib.xbios_getrez() == register_byte & addrs.GETREZ_MODE_MASK, (
            f"the reconstruction let bits outside {addrs.GETREZ_MODE_MASK:#04x} through for a "
            f"register byte of {register_byte:#04x}")


def test_the_register_is_not_served_out_of_the_image():
    """The claim ROM mode has to get right, one register over from `test_xbios_giaccess`'s.

    `$ff8260` is numerically INSIDE this project's 16 MB image and must still reach the declared
    map. A decoy planted at that very address is what says so: a shim that served the image would
    answer the decoy instead of the declared byte, and the routine would report the decoy's low bits.
    """
    decoy = 0xFF                  # its low two bits are 3, which no declared byte below produces
    diffs, info = differential(addrs.XBIOS_GETREZ,
                               {"a5": 0, "_pokes": {addrs.SHIFTER_RESOLUTION: bytes([decoy])}},
                               _glue, io_seed={addrs.SHIFTER_RESOLUTION: ST_HIGH})
    assert not diffs, report(diffs)
    assert info["regs"]["d0"] == ST_HIGH, "the read answered the image, not the declared I/O map"


def test_an_undeclared_read_of_the_same_register_refuses_the_case():
    """THE PAIR, over ONE routine: declared it is served and compared, undeclared it is refused.

    This is the whole of what the model bought, said in one file. Without a declaration the oracle
    reads the fabricated 0, the candidate would read the same 0, and the case would go green
    reporting ST LOW resolution — an answer nobody claimed and which is wrong on two machines out of
    three. `harness._vet_rom_io_reads_are_modelled` refuses it instead, names the register, and
    prescribes the declaration that answers it.

    The refusal fires before the candidate runs at all, so the glue is never reached: a case whose
    ORACLE was served a fabricated byte cannot be made honest by anything the reconstruction does.
    """
    with pytest.raises(AssertionError, match=f"{addrs.SHIFTER_RESOLUTION:#x}") as raised:
        differential(addrs.XBIOS_GETREZ, {"a5": 0}, _glue)
    assert "io_seed=" in str(raised.value), (
        "the refusal did not prescribe the declaration that answers it — a refusal a reader cannot "
        "act on is a refusal that gets suppressed")


def test_the_register_may_not_be_declared_through_the_named_slot_model():
    """...and the other half of the remedy: the two models' address sets are DISJOINT.

    `$ff8260` is not a Phase-7 slot, so `hw_seed` cannot answer it — and says so by name rather than
    installing nothing and letting the run read the fabricated 0 while the case's own source claims
    the byte was declared. That silent shape is the failure this refusal exists to prevent, and it
    is the mistake a reader who knows `hw_seed` and not `io_seed` will make first.
    """
    with pytest.raises(ValueError, match="does not serve"):
        differential(addrs.XBIOS_GETREZ, {"a5": 0}, _glue,
                     hw_seed={addrs.SHIFTER_RESOLUTION: ST_HIGH})


def test_the_oracles_cost_is_what_status_reports():
    """The Tier 3 denominator for this row, measured rather than estimated — and pinned, so the
    number in STATUS.md cannot quietly stop being the one the oracle produces.

    `ninsns` counts one more than the instructions executed (the reset iteration; shim.c's run loop
    says why), and is asserted as the oracle reports it.
    """
    from harness import make_image
    _final, _writes, regs = emu.run(make_image(), addrs.XBIOS_GETREZ, {"a5": 0},
                                    io_seed={addrs.SHIFTER_RESOLUTION: ST_HIGH})
    assert (regs["ninsns"], regs["cycles"]) == (5, 82), (
        f"Getrez now costs {regs['ninsns']} insns / {regs['cycles']} cycles — STATUS.md's Tier 3 "
        f"denominator for this row is stale")
