"""BIOS Kbshift (function 11) @ $fc0a34 — read, and optionally set, the keyboard shift state.

The routine is five instructions, and every one of them is a place a reconstruction can differ:
the read is a BYTE zero-extended, the mode is tested as a WORD, and the store is of the mode's LOW
BYTE. `mode` = $0080 therefore SETS the state to $80 while $ff80 only reports it — the pair of cases
this file is built around.

The old state is returned whether or not the new one is stored, which is what makes Kbshift usable
as a swap; the differential compares the byte at $0e61 itself, so both halves are pinned.
"""
import ctypes

import pytest

from harness import BASE_IMAGE, _lib, addrs

import case

_lib.bios_kbshift.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint16]
_lib.bios_kbshift.restype = ctypes.c_uint32

# Every named bit of the state byte, so a case can say what it is setting rather than a hex constant.
SHIFT_RIGHT, SHIFT_LEFT, CONTROL, ALT, CAPSLOCK = 0x01, 0x02, 0x04, 0x08, 0x10


def argument_poke(mode):
    return case.word_arg(mode)


def state_poke(state):
    return {addrs.KBSHIFT: bytes([state])}


def run(mode, pokes=None, poison=True):
    def glue(lib, buf):
        return lib.bios_kbshift(buf, mode & 0xFFFF)

    return case.run(addrs.BIOS_KBSHIFT,
                    {"a5": 0, "_pokes": {**argument_poke(mode), **(pokes or {})}},
                    glue, poison=poison)


def test_the_snapshot_has_no_modifier_held():
    """The idle desktop: nothing is held down, so the DEFAULT case's old state is 0."""
    assert BASE_IMAGE[addrs.KBSHIFT] == 0


@pytest.mark.parametrize("mode", (-1, -2, 0x8000, 0xff80, 0xffff))
def test_a_negative_mode_reports_without_storing(mode):
    """`bmi` on the WORD: bit 15, not bit 7. $ff80 has bit 7 set and is still a read."""
    info = run(mode, state_poke(CONTROL | ALT))
    assert info["regs"]["d0"] == CONTROL | ALT
    assert addrs.KBSHIFT not in info["writes"], "a negative mode stored the state anyway"


@pytest.mark.parametrize("state", (0, SHIFT_LEFT, CONTROL | ALT, CAPSLOCK, 0x7f, 0x80, 0xff))
def test_the_old_state_is_the_whole_byte_zero_extended(state):
    """`moveq #0,d0` then `move.b`: $ff comes back as 255, not as -1."""
    assert run(-1, state_poke(state))["regs"]["d0"] == state


@pytest.mark.parametrize("mode", (0, 1, SHIFT_RIGHT | SHIFT_LEFT, 0x7f, 0x80, 0xff, 0x7fff))
def test_a_non_negative_mode_stores_its_low_byte(mode):
    """`move.b d1,$0e61`. $0080 is the sharp one: bit 7 of a byte is not the sign of a word, so this
    is a STORE — and $7fff stores $ff, which is where a reconstruction storing the word diverges."""
    info = run(mode, state_poke(CAPSLOCK))
    assert info["regs"]["d0"] == CAPSLOCK, "the OLD state is the result, not the new one"
    assert info["writes"][addrs.KBSHIFT] == (mode & 0xFF)


def test_storing_the_state_it_already_holds_is_still_a_store():
    """A candidate that skipped a store whose value already matched would leave an image identical
    to the ORACLE's, so the byte compare cannot see it. WHAT CATCHES IT IS `poison=True` — the
    attribution pass re-runs both cores over an image where every oracle-written byte is inverted,
    and a candidate that does not write the byte leaves the canary behind. `info["writes"]` below is
    the ORACLE's ledger and could never redden for a candidate; it is asserted because it states a
    fact about the ROM (that this arm stores rather than comparing first)."""
    info = run(CONTROL, state_poke(CONTROL), poison=True)
    assert info["writes"][addrs.KBSHIFT] == CONTROL
