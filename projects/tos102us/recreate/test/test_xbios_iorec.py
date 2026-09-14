"""XBIOS Iorec (function 14) @ $fc28f6 — the address of a device's IOREC ring.

Three instructions over a three-longword table in the ROM at $fc2902, and NO BOUNDS CHECK: a device
number above 2 indexes past the table into the first instructions of `Rsconf` and hands the caller
those bytes as if they were an address. That is the routine's real behaviour and the reason the C
reads the image rather than switching on the device — so the out-of-range cases below compare the
ROM's own bytes, not a reconstruction's idea of them.

The index arithmetic is the BIOS dispatch's (`include/m68k_idioms.h`, `word_index`): `asl.l #2` but
indexed as `d1.w`, so a device of $4000 selects entry 0 — and a device whose product's bit 15 is set
indexes BACKWARDS off the table, which is the case this file ends on.
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs

import case

_lib.xbios_iorec.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16]
_lib.xbios_iorec.restype = ctypes.c_uint32

DEVICE_RS232, DEVICE_IKBD, DEVICE_MIDI = 0, 1, 2
RINGS = ((DEVICE_RS232, "IOREC_RS232"), (DEVICE_IKBD, "IOREC_IKBD"), (DEVICE_MIDI, "IOREC_MIDI"))

# A device whose word-sized index comes out NEGATIVE: $2000 * 4 is $8000 in a word, so `movea.w`
# sign-extends it to $ffff8000 and the entry read is $8000 BELOW the table rather than $8000 above
# it. Named here because both addresses appear in the case that separates them.
NEGATIVE_INDEX_DEVICE = 0x2000
SIGN_EXTENDED_INDEX = (((NEGATIVE_INDEX_DEVICE * addrs.IOREC_TABLE_ENTRY_BYTES) & 0xFFFF)
                       - 0x1_0000)
ZERO_EXTENDED_INDEX = (NEGATIVE_INDEX_DEVICE * addrs.IOREC_TABLE_ENTRY_BYTES) & 0xFFFF


def run(device, poison=True):
    def glue(lib, buf):
        return lib.xbios_iorec(buf, device & 0xFFFF)

    return case.run(addrs.XBIOS_IOREC, {"a5": 0, "_pokes": case.word_arg(device)}, glue,
                    poison=poison)


def longword_at(at):
    """The longword the IMAGE holds at `at` — the mapped ROM, or the zeros between RAM and it."""
    return int.from_bytes(bytes(BASE_IMAGE[at:at + addrs.IOREC_TABLE_ENTRY_BYTES]), "big")


@pytest.mark.parametrize("device,name", RINGS)
def test_each_device_answers_the_ring_addrs_h_names(device, name):
    """...and the three are the rings the Bconstat/Bconin drivers walk, which is what ties the two
    files' claims together: the same three addresses reached two different ways."""
    assert run(device)["regs"]["d0"] == getattr(addrs, name)


def test_the_table_in_rom_is_the_three_rings_and_they_are_distinct():
    """Read straight out of the mapped ROM. Distinct matters: a table of three equal pointers would
    pass every case above by accident."""
    entries = [longword_at(addrs.IOREC_TABLE + addrs.IOREC_TABLE_ENTRY_BYTES * i)
               for i in range(len(RINGS))]
    assert entries == [addrs.IOREC_RS232, addrs.IOREC_IKBD, addrs.IOREC_MIDI]
    assert len(set(entries)) == len(entries)


@pytest.mark.parametrize("device", (3, 4, 5))
def test_there_is_no_bounds_check_and_the_rom_past_the_table_is_read_as_an_address(device):
    """The three longwords after the table are `Rsconf`'s opening instructions. The routine hands
    them back without a glance, and a reconstruction that clamped, or returned 0, would differ."""
    expected = longword_at(addrs.IOREC_TABLE + addrs.IOREC_TABLE_ENTRY_BYTES * device)
    assert expected != addrs.IOREC_MIDI, "the case is only a case while it reads past the table"
    assert run(device)["regs"]["d0"] == expected


@pytest.mark.parametrize("device", (0x4000, 0x4001, 0x8002, 0xC001))
def test_the_index_is_taken_from_the_low_word_of_the_shifted_device(device):
    """`asl.l #2` then `d1.w`: only the low 14 bits of the device number can reach the index."""
    assert run(device)["regs"]["d0"] == run(device & 0x3FFF)["regs"]["d0"]


def test_a_negative_word_index_reads_below_the_table_and_not_above_it():
    """THE SIGN EXTENSION, which every case above is blind to because their indexes are small.

    Device $2000's index is $8000 — negative as a word — so the entry comes from $fba902, below both
    the ROM and RAM, where the image is zero. A reconstruction that zero-extended would read $fca902
    instead, which is inside the ROM and is an instruction rather than an address. Both addresses
    are asserted to hold DIFFERENT longwords, so this is a case and not a coincidence.
    """
    below = (addrs.IOREC_TABLE + SIGN_EXTENDED_INDEX) & 0xFFFF_FFFF
    above = addrs.IOREC_TABLE + ZERO_EXTENDED_INDEX
    assert longword_at(below) != longword_at(above), (
        "the two indexes read the same bytes, so this case could not tell them apart")
    assert run(NEGATIVE_INDEX_DEVICE)["regs"]["d0"] == longword_at(below)
