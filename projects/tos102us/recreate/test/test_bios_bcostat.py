"""BIOS Bcostat (function 8) @ $fc0994 — "can this device take another character?"

The same four-instruction walk as Bconstat, over the table at $055e — and, since a case may DECLARE
the byte a driver reads (TRAP_MODEL.md, Phases 7 and 15), the one BIOS entry here whose whole table
is in reach. Five drivers, five shapes, none of them a loop:

  * the console's ($fc226c) is `moveq #-1,d0 / rts`: the screen is never busy;
  * the printer's ($fc2124) tests MFP GPIP bit 0, the Centronics BUSY line — and keeps the -1 when
    the bit is CLEAR, so the branch reads the opposite way round to the answer;
  * the IKBD 6850's ($fc21dc) and MIDI 6850's ($fc2004) test bit 1 of their status registers, TDRE,
    one register block apart;
  * the RS232's ($fc219a) reads NO hardware at all: it advances its OUTPUT ring's tail by one record
    and asks whether that lands on the head, which is a full ring.

That last one is a finding rather than a port: this file and `src/bios/bcon.c` both used to say all
four "poll the MFP or an ACIA", and the RS232's never touched either.

WHAT EACH DECLARED BYTE IS PINNED BY. The value a driver answers is `d0`, which `case.run` compares
against the ROM's; the READ ITSELF leaves nothing else behind, so the ordered read stream is what
says the reconstruction asked the machine rather than remembering the answer — `hw_events` for the
two NAMED slots ($fffa01, $fffc00) and `io_events` for MIDI's ($fffc04), which is the kit's
bookkeeping and not the case's: all three are declared through the one `io_seed` door.
"""
import pytest

from harness import _lib, addrs

import bcon
import iorec

READY = 0xFFFFFFFF
NOT_READY = 0

DEVICE_PRINTER = 0
DEVICE_RS232 = 1
DEVICE_CONSOLE = 2
DEVICE_IKBD = 3
DEVICE_MIDI = 4
NO_DRIVER_DEVICES = (5, 6, 7)
# Every device whose driver reads a hardware byte, with the address it reads and the bit it tests.
# The table is the battery: three drivers, one shape, and the sweep below runs each over both sides
# of its own bit.
HARDWARE_DEVICES = {
    DEVICE_PRINTER: (addrs.MFP_GPIP, addrs.MFP_GPIP_PRINTER_BUSY_BIT),
    DEVICE_IKBD: (addrs.IKBD_ACIA_STATUS, 1),
    DEVICE_MIDI: (addrs.MIDI_ACIA_STATUS, 1),
}
# ...and which way round each bit reads. The printer's is a BUSY line — set means it cannot take a
# byte — where the two ACIAs' is TDRE, "the transmitter is empty", which means it can.
READY_WHEN_SET = {DEVICE_PRINTER: False, DEVICE_IKBD: True, DEVICE_MIDI: True}

# The bytes a case declares. Every bit but the one under test is SET in one and CLEAR in the other,
# so a reconstruction testing another bit — or the whole byte — cannot pass both halves of a sweep.
ALL_BITS = 0xFF

ENTRY_D0 = addrs.BIOS_BCOSTAT

run = bcon.runner(addrs.BIOS_BCOSTAT, _lib.bios_bcostat)


def declare(device, bit_set):
    """The `io_seed` for one hardware device, with its own bit set or clear and every other bit the
    other way round."""
    address, bit = HARDWARE_DEVICES[device]
    other_bits = 0 if bit_set else ALL_BITS
    return {address: (other_bits & ~(1 << bit)) | (bit_set << bit)}


def test_the_table_in_ram_is_the_one_this_file_describes():
    """...every entry of it, because every entry is now a driver this file claims. A device that
    stopped being the routine named here would otherwise send its case down another arm and pass."""
    entries = bcon.table_entries(addrs.XCOSTAT_TABLE)
    assert entries[DEVICE_PRINTER] == addrs.XCOSTAT_PRT
    assert entries[DEVICE_RS232] == addrs.XCOSTAT_RS232
    assert entries[DEVICE_CONSOLE] == addrs.XCOSTAT_CON
    assert entries[DEVICE_IKBD] == addrs.XCOSTAT_IKBD
    assert entries[DEVICE_MIDI] == addrs.XCOSTAT_MIDI
    assert all(entries[device] == addrs.ROM_BARE_RTS for device in NO_DRIVER_DEVICES)


def test_the_console_is_never_busy():
    assert run(DEVICE_CONSOLE)["regs"]["d0"] == READY


def test_the_console_answer_does_not_depend_on_the_caller_s_d0():
    """`moveq #-1,d0` sets the whole register, which is what separates this driver from the bare
    `rts` the no-driver devices reach."""
    assert run(DEVICE_CONSOLE, entry_d0=bcon.MARKED_D0)["regs"]["d0"] == READY


@pytest.mark.parametrize("device", sorted(HARDWARE_DEVICES))
@pytest.mark.parametrize("bit_set", (False, True))
def test_a_hardware_driver_answers_the_bit_the_machine_holds(device, bit_set):
    """BOTH SIDES OF EACH BIT, declared. Before the byte could be declared these three answered a
    fabricated 0 on both sides — so every case agreed with itself on whichever branch that chose,
    which is the false green the seeded models exist to close.

    The `ready when set` column is the driver's own sense, and it is why one table row per device is
    not enough: the printer's BUSY line and the 6850s' TDRE read opposite ways, and a reconstruction
    that inverted one would pass a battery that only ever asked the other.
    """
    expected = READY if bit_set == READY_WHEN_SET[device] else NOT_READY
    assert run(device, io_seed=declare(device, bit_set))["regs"]["d0"] == expected


@pytest.mark.parametrize("device", sorted(HARDWARE_DEVICES))
def test_a_hardware_driver_really_reads_the_register(device):
    """...and the read is in the ordered stream, which is its only witness: a `btst` leaves no image
    byte and no register a differential compares, so a core that remembered the answer instead of
    asking would be separable from a correct one by nothing else.

    WHICH stream it lands in is the kit's bookkeeping: `$fffa01` and `$fffc00` are Phase-7 NAMED
    SLOTS and `$fffc04` is an ordinary declared byte, so the case writes one `io_seed` and the reads
    come back in two different ledgers.
    """
    address, _bit = HARDWARE_DEVICES[device]
    declaration = declare(device, bit_set=True)
    info = run(device, io_seed=declaration)
    byte = declaration[address]
    streams = info["regs"]["hw_events"] + [(at, value) for at, _w, value in info["regs"]["io_events"]]
    assert streams == [(address, byte)], (
        f"device {device}'s driver did not read {address:#x} exactly once")


def test_the_rs232_reads_no_hardware_at_all():
    """THE FINDING this battery is built on: `$fc219a`'s whole body is its own OUTPUT ring. It was
    described — here and in `src/bios/bcon.c` — as polling the MFP or an ACIA, and the `bsr` in the
    middle of it goes to `$fc28ea`, which is the ring's wrap arithmetic."""
    info = run(DEVICE_RS232)
    assert (info["regs"]["hw_events"], info["regs"]["io_events"]) == ([], [])


# The RS232 output ring's own arithmetic, as the three cases that matter. `size` is what the snapshot
# holds (256), and a tail one short of the head is the ring with exactly one byte of room left.
RS232_SIZE = iorec.size_of(addrs.IOREC_RS232_OUT)


@pytest.mark.parametrize("head, tail, expected, why", (
    (0, 0, READY, "empty: the tail advances to 1, which is not the head"),
    (2, 1, NOT_READY, "the tail one short of the head is FULL — one more byte would make them equal"),
    (0, RS232_SIZE - 1, NOT_READY, "the tail at the last slot WRAPS to 0, which is the head"),
    (1, RS232_SIZE - 1, READY, "...and the same wrap with the head one on is room for one more"),
))
def test_the_rs232_output_ring_is_full_exactly_when_one_more_byte_would_reach_the_head(
        head, tail, expected, why):
    """`addq.w #1,d1 / cmp.w 4(a0),d1 / bcs` is an UNSIGNED compare whose skipped arm is
    `moveq #0,d1`: an index that REACHES the ring's size restarts at 0 rather than wrapping
    modulo it. The two wrap rows are what pin that — at `size - 1` the next index is 0, not `size`.
    """
    pokes = iorec.staged(addrs.IOREC_RS232_OUT, head=head, tail=tail)
    assert run(DEVICE_RS232, pokes=pokes)["regs"]["d0"] == expected, why


@pytest.mark.parametrize("device", NO_DRIVER_DEVICES)
def test_a_device_with_no_driver_returns_the_dispatch_s_own_scratch(device):
    bcon.assert_no_driver(run, device)


def test_the_device_index_is_computed_in_a_word():
    """`lsl.w #2`: device $4002 is the console."""
    assert run(0x4002)["regs"]["d0"] == READY
