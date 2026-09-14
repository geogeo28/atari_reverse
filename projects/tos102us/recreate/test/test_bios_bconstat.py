"""BIOS Bconstat (function 1) @ $fc0984 — "is there a character waiting on this device?"

The entry is a four-instruction walk of the vector table at $051e and a JUMP into the driver it
names, so a case that enters here runs BOTH — and the reconstruction has to be both. The drivers
this file can reach are the three whose whole body is a ring in RAM (RS232 $c54, the console's IKBD
$c76, MIDI $d84) plus the devices that have no input driver at all and land on the ROM's shared
`rts`. The printer has no input status either, and the console's answer is the KEYBOARD's — device 2
is a screen for output and an IKBD for input.

THE EMPTY RING IS THE DEFAULT. The snapshot's desktop is idle with every ring drained, so a case
that wants a "ready" answer stages a tail past the head (`iorec.py`).

THE THREE DRIVERS ARE THREE COPIES of the same six instructions, at $fc2138, $fc2226 and $fc2044 —
separate ROM code, not one routine called three times — so the sweep over head/tail arrangements
runs on one of them and the other two carry a pair of cases each. What ties a driver to ITS ring is
`test_each_ring_is_read_and_not_another`, which is per device.

WHAT THE NO-DRIVER DEVICES RETURN is the other half of the file, and it is shared with Bconin and
Bcostat (`bcon.py`): the ROM jumps to a bare `rts`, so the answer is whatever the dispatch left in
D0. Garbage, but deterministic garbage, and a reconstruction that returned 0 for "no driver" would
be wrong in a way no user of Bconstat would ever notice.
"""
import pytest

from harness import BASE_IMAGE, _lib, addrs

import bcon
import iorec

READY, NOT_READY = 0xFFFFFFFF, 0

# The BIOS device numbers, named. 4..7 have no input driver on this ROM; the printer (0) has none
# either, which is why it sits with them rather than with the three rings.
DEVICE_PRINTER, DEVICE_RS232, DEVICE_CONSOLE, DEVICE_MIDI = 0, 1, 2, 3
RING_DEVICES = ((DEVICE_RS232, addrs.IOREC_RS232), (DEVICE_CONSOLE, addrs.IOREC_IKBD),
                (DEVICE_MIDI, addrs.IOREC_MIDI))
NO_DRIVER_DEVICES = (DEVICE_PRINTER, 4, 5, 6, 7)

# D0 as the trap dispatcher leaves it: the routine's own address, which it loaded to jump through.
# Named for `test_boot_snapshot.py`'s table, which enters the ROM the way this file does.
ENTRY_D0 = addrs.BIOS_BCONSTAT

run = bcon.runner(addrs.BIOS_BCONSTAT, _lib.bios_bconstat)

# Head/tail arrangements that must all read "ready": adjacent either way round, a whole record
# apart, mid-ring, at the ring's last record, and the two extremes of the word.
HEAD_TAIL_PAIRS = ((0, 1), (1, 0), (0, 4), (0x40, 0x44), (0xfc, 0), (0, 0xffff), (0xffff, 0))
# ...swept on the console's driver, with a pair apiece on the other two copies.
READY_CASES = ([(DEVICE_CONSOLE, addrs.IOREC_IKBD, head, tail) for head, tail in HEAD_TAIL_PAIRS]
               + [(DEVICE_RS232, addrs.IOREC_RS232, 0, 4),
                  (DEVICE_RS232, addrs.IOREC_RS232, 0xffff, 0),
                  (DEVICE_MIDI, addrs.IOREC_MIDI, 0, 1),
                  (DEVICE_MIDI, addrs.IOREC_MIDI, 0, 0xffff)])
# ...and the same shape for "not ready": a sweep of indexes on one driver, one apiece on the others.
EQUAL_CASES = ([(DEVICE_CONSOLE, addrs.IOREC_IKBD, index) for index in (0, 1, 0x40, 0xfe, 0xffff)]
               + [(DEVICE_RS232, addrs.IOREC_RS232, 0x40), (DEVICE_MIDI, addrs.IOREC_MIDI, 0xffff)])


def test_the_table_in_ram_is_the_one_this_file_describes():
    """WHICH DRIVER each device reaches is a fact about the RAM the capture holds, not about the ROM
    — the boot copies the table from $fc09ae and anything may replace an entry afterwards. Read out
    of the snapshot, so a different machine reddens here instead of proving the wrong driver."""
    entries = bcon.table_entries(addrs.XCONSTAT_TABLE)
    assert entries[DEVICE_RS232] == addrs.XCONSTAT_RS232
    assert entries[DEVICE_CONSOLE] == addrs.XCONSTAT_CON
    assert entries[DEVICE_MIDI] == addrs.XCONSTAT_MIDI
    assert all(entries[device] == addrs.ROM_BARE_RTS for device in NO_DRIVER_DEVICES)


@pytest.mark.parametrize("device,ring", RING_DEVICES)
def test_a_drained_ring_answers_not_ready(device, ring):
    """The snapshot AS CAPTURED — no poke at all: the idle desktop left all three rings drained, so
    the default image is already the empty case and this says so rather than assuming it."""
    indices = bytes(BASE_IMAGE[ring + addrs.IOREC_HEAD:ring + addrs.IOREC_TAIL + 2])
    assert indices[:2] == indices[2:], f"the snapshot's ring at {ring:#x} is not drained"
    assert run(device)["regs"]["d0"] == NOT_READY


@pytest.mark.parametrize("device,ring,head,tail", READY_CASES)
def test_any_difference_between_head_and_tail_is_ready(device, ring, head, tail):
    """`cmpm.w` compares the two words and nothing else — it does not ask which is ahead, or by how
    much, so a ring whose tail has wrapped BELOW its head is still ready."""
    assert run(device, iorec.staged(ring, head, tail))["regs"]["d0"] == READY


@pytest.mark.parametrize("device,ring,index", EQUAL_CASES)
def test_equal_head_and_tail_is_not_ready_whatever_they_hold(device, ring, index):
    assert run(device, iorec.staged(ring, index, index))["regs"]["d0"] == NOT_READY


def test_each_ring_is_read_and_not_another():
    """Three drivers, three rings: filling ONE must move only its own device's answer. A
    reconstruction that named the wrong ring passes every case above, where all three are drained
    together."""
    for device, ring in RING_DEVICES:
        pokes = iorec.staged(ring, 0, 4)
        for other_device, _other_ring in RING_DEVICES:
            expected = READY if other_device == device else NOT_READY
            assert run(other_device, pokes)["regs"]["d0"] == expected, (
                f"device {other_device} answered device {device}'s ring")


@pytest.mark.parametrize("device", NO_DRIVER_DEVICES)
def test_a_device_with_no_driver_returns_the_dispatch_s_own_scratch(device):
    """`jmp` to the shared `rts` at $fc0670: D0 is the dispatch's, with the table offset in its low
    word and the caller's own high word untouched (`bcon.no_driver_result`)."""
    bcon.assert_no_driver(run, device)


def test_the_device_index_is_computed_in_a_word():
    """`lsl.w #2`: device $4002 indexes entry 2, the console, exactly as device 2 does."""
    pokes = iorec.staged(addrs.IOREC_IKBD, 0, 4)
    assert run(0x4002, pokes)["regs"]["d0"] == READY
    assert run(0x4000, pokes)["regs"]["d0"] == run(DEVICE_PRINTER, pokes)["regs"]["d0"]
