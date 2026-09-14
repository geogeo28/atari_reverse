"""BIOS Drvmap (function 10) @ $fc0a2e — which drives GEMDOS has mounted, as a bitmap.

Two instructions, and the whole of the case is therefore about the INPUT: the snapshot's own
`_drvbits` (A: and B:, the machine the capture was taken on), and then values that would separate a
reconstruction reading a longword from one reading a word or a byte.
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs

import case

_lib.bios_drvmap.restype = ctypes.c_uint32

# The floppy machine the snapshot was captured on: A: and B: and nothing else.
SNAPSHOT_DRVBITS = 0b11


def drvbits_poke(drvbits):
    return {addrs.SYSVAR_DRVBITS: drvbits.to_bytes(4, "big")}


def run(pokes=None, poison=True):
    def glue(lib, buf):
        return lib.bios_drvmap(buf)

    return case.run(addrs.BIOS_DRVMAP, {"a5": 0, "_pokes": pokes or {}}, glue, poison=poison)


def test_the_snapshot_is_the_two_floppy_drives():
    """The machine the capture was taken on, asserted rather than assumed — a snapshot from a
    different configuration would otherwise quietly change what the default case proves."""
    drvbits = int.from_bytes(bytes(BASE_IMAGE[addrs.SYSVAR_DRVBITS:addrs.SYSVAR_DRVBITS + 4]), "big")
    assert drvbits == SNAPSHOT_DRVBITS
    assert run()["regs"]["d0"] == SNAPSHOT_DRVBITS


@pytest.mark.parametrize("drvbits", (0, 1, 0x0000_ffff, 0x0001_0000, 0x8000_0000, 0xffff_ffff,
                                     0x1234_5678))
def test_the_whole_longword_is_reported(drvbits):
    """A reconstruction that read a word would agree on the first three of these and on none of the
    rest; one that read a byte would agree only on 0 and 1."""
    assert run(drvbits_poke(drvbits))["regs"]["d0"] == drvbits
