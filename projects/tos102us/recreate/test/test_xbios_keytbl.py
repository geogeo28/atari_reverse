"""XBIOS Keytbl (function 16) @ $fc302e — replace the keyboard's scancode translation tables.

Three longword arguments, each installed into the `keytbl` struct at $0e62 unless it is negative,
and the struct's own address comes back. It is how a program installs a foreign keyboard layout, and
the IKBD interrupt handler reads the result on every keypress.

The three arguments are INDEPENDENT here — unlike Kbrate next door, where a negative first argument
skips the second — so the battery walks the combinations of "install" and "leave alone" rather than
testing them one at a time. All three negative is the corner two other cases already make, so the
product below leaves it to them.
"""
import ctypes
import itertools
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs

import abi
import case
import staging

_lib.xbios_keytbl.argtypes = [ctypes.POINTER(ctypes.c_ubyte)] + [ctypes.c_uint32] * 3
_lib.xbios_keytbl.restype = ctypes.c_uint32

KEEP = 0xFFFFFFFF                      # the documented "leave this one alone"
# The struct's three longwords, in the order Keytbl takes them and Bioskeys restores them.
TABLE_FIELDS = (addrs.KEYTBL_FIELD_UNSHIFTED, addrs.KEYTBL_FIELD_SHIFTED,
                addrs.KEYTBL_FIELD_CAPSLOCK)
# Three distinct staged tables, so installing the WRONG field is a divergence on the value rather
# than a coincidence. They are never read — Keytbl only stores the pointers — so they are ordinary
# addresses in the staging band rather than tables anybody laid out.
STAGED = tuple(staging.SCRATCH + 0x100 * i for i in (1, 2, 3))
# Every combination of install/keep except the all-keep corner, which has two cases of its own.
INSTALL_COMBINATIONS = tuple(flags for flags in itertools.product((False, True), repeat=3)
                             if any(flags))


def argument_poke(tables):
    """Three longwords at 4(sp), as the caller pushed them."""
    return {abi.FIRST_ARG: struct.pack(">III", *(t & 0xFFFFFFFF for t in tables))}


def run(tables, poison=True):
    def glue(lib, buf):
        return lib.xbios_keytbl(buf, *(t & 0xFFFFFFFF for t in tables))

    return case.run(addrs.XBIOS_KEYTBL, {"a5": 0, "_pokes": argument_poke(tables)}, glue,
                    poison=poison)


def field(image, index):
    at = addrs.KEYTBL_STRUCT + TABLE_FIELDS[index]
    return int.from_bytes(bytes(image[at:at + 4]), "big")


def written_field(info, index):
    return case.written_long(info, addrs.KEYTBL_STRUCT + TABLE_FIELDS[index])


def test_the_snapshot_holds_the_rom_s_own_three_tables():
    """Which is what makes "install" visible: every field starts at a ROM address."""
    assert [field(BASE_IMAGE, i) for i in range(3)] == [addrs.KEYTBL_UNSHIFTED_ROM,
                                                        addrs.KEYTBL_SHIFTED_ROM,
                                                        addrs.KEYTBL_CAPSLOCK_ROM]


def test_the_struct_s_address_is_the_return_value_whatever_was_installed():
    """`move.l #$0e62,d0` — a constant, and the same one the OS header publishes at $fc0024."""
    assert run((KEEP, KEEP, KEEP))["regs"]["d0"] == addrs.KEYTBL_STRUCT
    assert run(STAGED)["regs"]["d0"] == addrs.KEYTBL_STRUCT


def test_all_three_negative_installs_nothing():
    assert not run((KEEP, KEEP, KEEP))["writes"], "a read-only Keytbl wrote to the struct"


@pytest.mark.parametrize("install", INSTALL_COMBINATIONS)
def test_each_field_is_installed_independently(install):
    """Seven cases over the three flags. A reconstruction that bailed out on the first negative
    argument — the shape Kbrate really has — passes (T,T,T) and fails five of these."""
    tables = tuple(STAGED[i] if install[i] else KEEP for i in range(3))
    info = run(tables)
    for i in range(3):
        if install[i]:
            assert written_field(info, i) == STAGED[i]
        else:
            at = addrs.KEYTBL_STRUCT + TABLE_FIELDS[i]
            assert at not in info["writes"], f"field {i} was written although its argument was -1"


@pytest.mark.parametrize("table", (0, 1, 0x7FFFFFFF, 0x00FFFFFF))
def test_a_non_negative_pointer_is_installed_however_implausible(table):
    """The test is `tst.l`/`bmi` and nothing else: 0 is a valid table as far as this routine is
    concerned, and so is $7fffffff. Only bit 31 means "keep"."""
    assert written_field(run((table, KEEP, KEEP)), 0) == table


@pytest.mark.parametrize("table", (0x80000000, 0xFFFFFFFE, 0xDEADBEEF, KEEP))
def test_every_pointer_with_bit_31_set_keeps_the_field(table):
    assert not run((table, table, table))["writes"]
