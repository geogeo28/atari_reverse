"""XBIOS Bioskeys (function 24) @ $fc305a — put the ROM's own keyboard tables back.

Three immediate stores into the `keytbl` struct at $0e62 and nothing else: it is Keytbl's undo, the
call a program makes to hand the US layout back after installing its own.

IT RETURNS NOTHING. The routine sets no result at all, so what a caller finds in D0 is whatever the
trap dispatcher left — and the reconstruction is `void` for that reason, which the cases declare with
`case.NO_RESULT` rather than by omitting the check.

The three constants it stores are the scancode tables at $fc2288/$fc2308/$fc2388, which
COMPONENTS.md verifies by eye ($fc2298 is the string `qwertyuiop[]`). The case below asserts that
independently, so `addrs.h` naming the wrong table would redden here and not merely agree with
itself.
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs

import case
import test_xbios_keytbl as keytbl

_lib.xbios_bioskeys.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
_lib.xbios_bioskeys.restype = None

ROM_TABLES = (addrs.KEYTBL_UNSHIFTED_ROM, addrs.KEYTBL_SHIFTED_ROM, addrs.KEYTBL_CAPSLOCK_ROM)
# Scancode $10 is the 'q' key, and the row it opens is what says a table is the table it claims.
QWERTY_SCANCODE = 0x10
QWERTY_ROWS = (b"qwertyuiop[]", b"QWERTYUIOP{}", b"QWERTYUIOP[]")


def run(pokes=None, poison=True):
    def glue(lib, buf):
        lib.xbios_bioskeys(buf)

    return case.run(addrs.XBIOS_BIOSKEYS, {"a5": 0, "_pokes": pokes or {}}, glue,
                    width=case.NO_RESULT, poison=poison)


def test_the_three_tables_are_the_scancode_tables_they_claim_to_be():
    """Read out of the mapped ROM: at scancode $10 each table spells its own keyboard row."""
    for table, row in zip(ROM_TABLES, QWERTY_ROWS):
        at = table + QWERTY_SCANCODE
        assert bytes(BASE_IMAGE[at:at + len(row)]) == row, f"{table:#x} is not the table it is named"


def test_the_three_tables_are_installed_over_whatever_was_there():
    """The sharp case: install three staged tables with Keytbl first, then ask Bioskeys to undo it.
    The pokes stand in for that call, so this file stays a differential of Bioskeys alone."""
    pokes = {addrs.KEYTBL_STRUCT: b"".join(t.to_bytes(4, "big") for t in keytbl.STAGED)}
    info = run(pokes)
    for index, table in enumerate(ROM_TABLES):
        assert keytbl.written_field(info, index) == table


def test_it_stores_all_three_even_when_they_are_already_there():
    """The snapshot already holds exactly these, so nothing in the image moves — which is precisely
    the shape a candidate could pass by doing nothing.

    WHAT CATCHES THAT IS `poison=True`: the attribution pass inverts every oracle-written byte and
    re-runs both cores, so a candidate that skipped a store leaves the canary behind and diverges.
    `info["writes"]` below is the ORACLE's own ledger and can never redden for a candidate; it is
    asserted because it states a fact about the ROM — three unconditional stores rather than three
    compare-and-skips.
    """
    info = run(poison=True)
    for index, table in enumerate(ROM_TABLES):
        assert keytbl.written_field(info, index) == table


@pytest.mark.parametrize("index", range(3))
def test_each_field_is_written_separately(index):
    """Three `move.l #imm,abs` stores: clearing one field and leaving the other two is the shape
    that separates three stores from one twelve-byte copy that happened to be right."""
    at = addrs.KEYTBL_STRUCT + keytbl.TABLE_FIELDS[index]
    info = run({at: b"\x00\x00\x00\x00"})
    assert keytbl.written_field(info, index) == ROM_TABLES[index]
