"""XBIOS Setprt (function $21) @ $fc3088 — the printer description GEMDOS and the screen dump read.

Three instructions, and the same shape as `Kbrate` next door minus its coupling: report the word at
$0e90, replace it unless the argument is negative. There is only one argument, so there is nothing
here for a second `bmi` to skip.

WHAT THE WORD MEANS is a fact about its READERS rather than about this routine, which stores whatever
it is given: $fc2090 tests bit 4 of it to choose between a dot-matrix and a daisy-wheel screen dump,
and $fc0d9e/$fc0dac read it in the printer BIOS driver. `Setprt` validates none of that — 16 bits of
caller's choice.

THE RESULT IS A WORD OF A 32-BIT REGISTER. `move.w $0e90,d0` leaves D0's high half as the caller had
it, so the core takes the caller's D0 and returns the whole register, and the cases compare the whole
of it — `kbrate.c`'s note again. Its neighbour `Dosound` is the contrast: a `move.l`, and a clean 32
bits.
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs

import case

_lib.xbios_setprt.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32, ctypes.c_uint16]
_lib.xbios_setprt.restype = ctypes.c_uint32

KEEP = 0xFFFF
# The configuration the boot leaves: every bit clear. Asserted rather than assumed — the case that
# stores 0 over 0 is the one the poison pass is for.
SNAPSHOT_CONFIG = 0x0000
# A caller's D0 with a marked high half, for the claim about what the `move.w` leaves alone.
MARKED_D0 = 0xDEAD_0000


def config_poke(config):
    return {addrs.PRINTER_CONFIG: config.to_bytes(2, "big")}


def run(config, held=SNAPSHOT_CONFIG, entry_d0=0, poison=True):
    def glue(lib, buf):
        return lib.xbios_setprt(buf, entry_d0, config & 0xFFFF)

    return case.run(addrs.XBIOS_SETPRT,
                    {"a5": 0, "d0": entry_d0,
                     "_pokes": {**case.word_arg(config), **config_poke(held)}}, glue, poison=poison)


def reported(info):
    """The WORD the routine reports — D0's low half, which is all it sets."""
    return info["regs"]["d0"] & 0xFFFF


def test_the_snapshot_holds_the_boots_printer_configuration():
    assert int.from_bytes(bytes(BASE_IMAGE[addrs.PRINTER_CONFIG:addrs.PRINTER_CONFIG + 2]),
                          "big") == SNAPSHOT_CONFIG


# Configurations that say something different about the store: the bit $fc2090 tests; a word with
# every bit the caller could set; the largest NON-negative word, which is the sign boundary from
# below; and the value already there, which only the poison pass can attribute.
CONFIGS = (0x0010, 0x0055, 0x7FFF, SNAPSHOT_CONFIG)


@pytest.mark.parametrize("config", CONFIGS)
def test_a_non_negative_configuration_is_stored_whole(config):
    """A WORD and not a byte: bit 4 is what the screen dump reads, and a reconstruction that stored
    only the low byte would pass that reader and lose everything above bit 7. Read back out of the
    ORACLE's write ledger, so a field never stored is a KeyError naming it."""
    info = run(config)
    assert case.written(info, addrs.PRINTER_CONFIG, 2) == config


@pytest.mark.parametrize("config", (KEEP, 0x8000, 0xFF80))
def test_a_negative_configuration_only_reports(config):
    """`tst.w 4(sp)` / `bmi` — tested at the ROM's own WIDTH, so $ff80 reports even though its low
    byte looks positive, and $8000 is the boundary itself."""
    info = run(config, held=0x0055)
    assert info["writes"] == {}


@pytest.mark.parametrize("held", (0x0000, 0x0010, 0xFFFF))
def test_it_reports_the_configuration_it_is_replacing(held):
    """The read happens BEFORE the `tst`, so a call that stores reports the OLD word. A
    reconstruction that reported what it had just written passes every report-only case."""
    assert reported(run(0x0055, held=held)) == held


@pytest.mark.parametrize("config", (KEEP, 0x0055))
def test_the_callers_high_half_of_d0_survives(config):
    """`move.w`, with no `clr.l d0` above it — on both arms. A `uint16_t` core would report the same
    number as one that had cleared the high half, which is what `Tickcal` really does and this does
    not."""
    info = run(config, held=0x0010, entry_d0=MARKED_D0, poison=False)
    assert info["regs"]["d0"] == MARKED_D0 | 0x0010


def test_it_touches_nothing_but_that_word():
    info = run(0x0055, poison=False)
    assert sorted(info["writes"]) == [addrs.PRINTER_CONFIG, addrs.PRINTER_CONFIG + 1]
    assert info["regs"]["hw_writes"] == [], "Setprt drove a chip; it only keeps a word of RAM"


def test_the_oracles_cost_is_what_status_reports():
    """The Tier 3 denominator for the two cases priced. `ninsns` counts one more than the
    instructions executed (the reset iteration; shim.c's run loop says why)."""
    from harness import emu, make_image
    for config, expected in ((0x0055, (6, 108)), (KEEP, (5, 90))):
        _final, _writes, regs = emu.run(
            make_image({**case.word_arg(config), **config_poke(SNAPSHOT_CONFIG)}),
            addrs.XBIOS_SETPRT, {"a5": 0, "d0": 0})
        assert (regs["ninsns"], regs["cycles"]) == expected, (
            f"Setprt({config:#x}) now costs {regs['ninsns']} insns / {regs['cycles']} cycles — "
            f"STATUS.md's Tier 3 denominator for this row is stale")
