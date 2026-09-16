"""XBIOS Dosound (function $20) @ $fc3074 — hand a sound list to the 200 Hz timer path.

Four instructions, and only the last of them is not `Kbrate`'s shape: report the cursor the driver is
reading from, replace it unless the argument is negative — and then CLEAR $0e8e.

THAT `clr.b` IS THE HANDSHAKE AND IT IS THE CASE THIS FILE EXISTS FOR. $0e8e is the driver's "ticks
still to wait" ($fc3138: `move.b $0e8e,d0 / beq .run / subq.b #1,d0 / move.b d0,$0e8e`), so a list
handed over while a previous one's pause is still counting down would not be started for up to 255
ticks. Clearing it makes the very next tick begin the new list. A reconstruction that stored only the
pointer is correct in every audible sense and differs by one byte here — which is the byte.

THE DRIVER ITSELF IS NOT HERE. $fc312a walks the list, writes $ff8800/$ff8802 directly and keeps its
own ramp byte at $0e8f; it runs from the timer interrupt, not from this call, and it is the interrupt
half of this wave. The boundary between the two is the two bytes below.

THE RESULT IS THE WHOLE OF D0. `move.l $0e8a,d0` is a longword load, so unlike `Setprt` next door
this one leaves no half of the caller's register behind.
"""
import ctypes
import struct

import pytest

from harness import BASE_IMAGE, _lib, addrs

import abi
import case

_lib.xbios_dosound.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32]
_lib.xbios_dosound.restype = ctypes.c_uint32

KEEP = 0xFFFFFFFF
# What the captured desktop holds: no list playing, and no pause outstanding. Asserted rather than
# assumed — the case that stores 0 over 0 depends on it.
SNAPSHOT_LIST, SNAPSHOT_DELAY = 0, 0
# A pause the driver is part way through, for the cases about the `clr.b`: nothing else in the
# routine would move it, so a non-zero value is the only way to see the store at all.
A_PENDING_DELAY = 0x2A


def argument_poke(list_pointer):
    return {abi.FIRST_ARG: struct.pack(">I", list_pointer & 0xFFFFFFFF)}


def state_poke(list_pointer, delay):
    """The driver's two fields as a case stages them: the cursor and the tick countdown."""
    return {addrs.SOUND_LIST_POINTER: struct.pack(">I", list_pointer & 0xFFFFFFFF),
            addrs.SOUND_LIST_DELAY: bytes([delay])}


def run(list_pointer, held=SNAPSHOT_LIST, delay=SNAPSHOT_DELAY, poison=True):
    def glue(lib, buf):
        return lib.xbios_dosound(buf, list_pointer & 0xFFFFFFFF)

    return case.run(addrs.XBIOS_DOSOUND,
                    {"a5": 0, "_pokes": {**argument_poke(list_pointer),
                                         **state_poke(held, delay)}}, glue, poison=poison)


def test_the_snapshot_has_no_sound_playing():
    assert int.from_bytes(bytes(BASE_IMAGE[addrs.SOUND_LIST_POINTER:
                                           addrs.SOUND_LIST_POINTER + 4]), "big") == SNAPSHOT_LIST
    assert BASE_IMAGE[addrs.SOUND_LIST_DELAY] == SNAPSHOT_DELAY


# Pointers that say something different about the store: an ordinary list in the TPA; 0, which is how
# the driver is told there is nothing to play; the largest NON-negative longword; and the value
# already there, which only the poison pass can attribute.
LIST_POINTERS = (0x000A_1234, 0x0000_0000, 0x7FFF_FFFF, SNAPSHOT_LIST)


@pytest.mark.parametrize("list_pointer", LIST_POINTERS)
def test_a_non_negative_pointer_becomes_the_drivers_cursor(list_pointer):
    """Read back out of the ORACLE's write ledger, so a field the routine never stored is a KeyError
    naming it rather than a stale byte that reads right."""
    info = run(list_pointer)
    assert case.written_long(info, addrs.SOUND_LIST_POINTER) == list_pointer


@pytest.mark.parametrize("list_pointer", (KEEP, 0x8000_0000, 0xFFFF_FFFE))
def test_a_negative_pointer_only_reports(list_pointer):
    """`move.l 4(sp),d1` / `bmi` — tested as a LONG, so every pointer with bit 31 set reports, and
    $ffffffff is only the documented spelling of that family. Nothing legitimate is refused: every
    address on a 24-bit bus has bit 31 clear."""
    info = run(list_pointer, held=0x000A_1234, delay=A_PENDING_DELAY)
    assert info["writes"] == {}, "a report-only call touched the driver's state"


@pytest.mark.parametrize("list_pointer", LIST_POINTERS)
def test_storing_a_list_clears_the_tick_countdown(list_pointer):
    """THE `clr.b`. The driver is part way through a 42-tick pause; handing it a list must make the
    next tick start that list instead of finishing the pause."""
    info = run(list_pointer, delay=A_PENDING_DELAY)
    assert info["writes"][addrs.SOUND_LIST_DELAY] == 0


def test_the_countdown_is_cleared_even_when_it_is_already_zero():
    """...and it is a STORE and not a conditional one — attributed by the poison pass, which inverts
    the byte first, so a reconstruction that skipped it reds instead of matching the snapshot's own
    zero by coincidence."""
    info = run(0x000A_1234, delay=0)
    assert info["writes"][addrs.SOUND_LIST_DELAY] == 0


def test_a_report_only_call_leaves_a_pause_running():
    """The other side of the same byte: `bmi` jumps PAST the `clr.b`, so `Dosound(-1)` does not
    disturb a list that is playing. A reconstruction that cleared the countdown unconditionally
    passes every case above."""
    info = run(KEEP, held=0x000A_1234, delay=A_PENDING_DELAY)
    assert addrs.SOUND_LIST_DELAY not in info["writes"]


@pytest.mark.parametrize("held", (0x000A_1234, 0x0000_0000, 0xFFFF_FFFF))
def test_it_reports_the_cursor_it_is_replacing(held):
    """The read happens BEFORE the `bmi`, so a call that stores reports the OLD cursor rather than
    the one it stored — and the whole longword of it, which is what `move.l` means."""
    assert run(0x000B_0000, held=held)["regs"]["d0"] == held


@pytest.mark.parametrize("held", (0x000A_1234, 0xFFFF_FFFF))
def test_a_report_only_call_reports_the_same_thing(held):
    assert run(KEEP, held=held, delay=A_PENDING_DELAY)["regs"]["d0"] == held


def test_it_touches_nothing_but_those_five_bytes():
    """The cursor and the countdown, and no chip at all: the ports belong to the driver."""
    info = run(0x000A_1234, delay=A_PENDING_DELAY, poison=False)
    assert sorted(info["writes"]) == (
        [addrs.SOUND_LIST_POINTER + i for i in range(4)] + [addrs.SOUND_LIST_DELAY])
    assert info["regs"]["psg_events"] == [], "Dosound drove the chip; that is the 200 Hz path's job"


def test_the_oracles_cost_is_what_status_reports():
    """The Tier 3 denominator for the two cases priced. `ninsns` counts one more than the
    instructions executed (the reset iteration; shim.c's run loop says why)."""
    from harness import emu, make_image
    for list_pointer, expected in ((0x000A_1234, (7, 128)), (KEEP, (5, 98))):
        _final, _writes, regs = emu.run(
            make_image({**argument_poke(list_pointer),
                        **state_poke(SNAPSHOT_LIST, A_PENDING_DELAY)}),
            addrs.XBIOS_DOSOUND, {"a5": 0})
        assert (regs["ninsns"], regs["cycles"]) == expected, (
            f"Dosound({list_pointer:#x}) now costs {regs['ninsns']} insns / {regs['cycles']} "
            f"cycles — STATUS.md's Tier 3 denominator for this row is stale")
