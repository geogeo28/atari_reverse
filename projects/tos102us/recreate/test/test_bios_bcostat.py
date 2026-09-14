"""BIOS Bcostat (function 8) @ $fc0994 — "can this device take another character?"

The same four-instruction walk as Bconstat, over the table at $055e. Only ONE of its drivers is in
reach, and it is the shortest routine in the ROM: the console's ($fc226c) is `moveq #-1,d0 / rts`,
because the screen is never busy. The printer's, the RS232's, MIDI's and the IKBD's all poll the MFP
or an ACIA, so they are refused by ROM mode (../README.md) and are not reconstructed.

That leaves this file two claims, and they are worth having despite the size of the driver: that the
walk reaches the constant for device 2 and only device 2, and that devices 5..7 — which have no
output driver at all — return the dispatch's own scratch rather than "busy". A reconstruction that
answered READY for everything would pass a battery that only ever asked about the console.
"""
import pytest

from harness import _lib, addrs

import bcon

READY = 0xFFFFFFFF

DEVICE_CONSOLE = 2
NO_DRIVER_DEVICES = (5, 6, 7)
# The four whose driver polls a chip: printer, RS232, MIDI and the IKBD's own output line.
HARDWARE_DEVICES = (0, 1, 3, 4)

ENTRY_D0 = addrs.BIOS_BCOSTAT

run = bcon.runner(addrs.BIOS_BCOSTAT, _lib.bios_bcostat)


def test_the_table_in_ram_is_the_one_this_file_describes():
    """...including the four entries this project does NOT reconstruct, named so the reason they are
    absent stays checkable: each must still be a ROM routine, not the shared `rts`."""
    entries = bcon.table_entries(addrs.XCOSTAT_TABLE)
    assert entries[DEVICE_CONSOLE] == addrs.XCOSTAT_CON
    assert all(entries[device] == addrs.ROM_BARE_RTS for device in NO_DRIVER_DEVICES)
    for device in HARDWARE_DEVICES:
        entry = entries[device]
        assert entry != addrs.ROM_BARE_RTS and addrs.ROM_BASE <= entry, (
            f"device {device} no longer has a hardware driver — it may now be in reach")


def test_the_console_is_never_busy():
    assert run(DEVICE_CONSOLE)["regs"]["d0"] == READY


def test_the_console_answer_does_not_depend_on_the_caller_s_d0():
    """`moveq #-1,d0` sets the whole register, which is what separates this driver from the bare
    `rts` the no-driver devices reach."""
    assert run(DEVICE_CONSOLE, entry_d0=bcon.MARKED_D0)["regs"]["d0"] == READY


@pytest.mark.parametrize("device", NO_DRIVER_DEVICES)
def test_a_device_with_no_driver_returns_the_dispatch_s_own_scratch(device):
    bcon.assert_no_driver(run, device)


def test_the_device_index_is_computed_in_a_word():
    """`lsl.w #2`: device $4002 is the console."""
    assert run(0x4002)["regs"]["d0"] == READY
