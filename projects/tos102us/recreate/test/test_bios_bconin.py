"""BIOS Bconin (function 2) @ $fc098c — take one character off a device, blocking until there is one.

The entry walks the vector table at $053e and jumps into the driver, and the driver POLLS: it calls
the device's own status routine in a loop and only then takes a record out of the ring. Nothing in a
differential run can end that loop — no interrupt fires — so every case here stages the record
first, which is exactly what the IKBD or MIDI interrupt handler would have done (`iorec.py`). A case
that did not would run BOTH cores for ever: the reconstruction spins on the same two ring fields the
ROM does, which is the honest reconstruction of a routine whose body is a wait.

TWO DRIVERS ARE IN REACH, and they differ in more than their ring:

* the console's ($fc223c) reads the IKBD ring in FOUR-byte records — a scancode word and an ASCII
  word — and returns the whole longword;
* MIDI's ($fc2060) reads ONE byte, with `move.b`, into the D0 its status routine had just set to
  -1. So MIDI input returns $ffffff00 | byte (`addrs.MIDI_RESULT_PREFIX`). That is not a
  transcription slip, and a reconstruction that returned the byte would differ on every MIDI
  character.

Both advance the head BEFORE reading, and both wrap it to 0 on reaching the ring's size rather than
subtracting — the wrap cases below are what separate that from a modulo. And both STORE the advanced
head only after the record is out, which one case here is built to see.

The printer's and the RS232's input drivers ($fc2104, $fc2150) poll the MFP and the ACIA and hold
the line, so they are out of ROM mode's reach and out of this file (../README.md).
"""
import struct

import pytest

from harness import _lib, addrs

import bcon
import case
import iorec

DEVICE_CONSOLE, DEVICE_MIDI = 2, 3
NO_DRIVER_DEVICES = (4, 5, 6, 7)

ENTRY_D0 = addrs.BIOS_BCONIN

run = bcon.runner(addrs.BIOS_BCONIN, _lib.bios_bconin)


def head_after(info, ring):
    """The head the ORACLE left, out of its own write ledger — so a driver that read the record but
    never advanced the head is visible rather than merely returning the right value once."""
    return case.written(info, ring + addrs.IOREC_HEAD, 2)


def test_the_table_in_ram_reaches_the_two_reconstructed_drivers():
    """WHICH driver each device number reaches is RAM, not ROM — read it rather than assume it."""
    entries = bcon.table_entries(addrs.XCONIN_TABLE)
    assert entries[DEVICE_CONSOLE] == addrs.XCONIN_CON
    assert entries[DEVICE_MIDI] == addrs.XCONIN_MIDI
    assert all(entries[device] == addrs.ROM_BARE_RTS for device in NO_DRIVER_DEVICES)


# ---- the console: four-byte records out of the IKBD ring -----------------------------------------

# A scancode/ASCII longword as the IKBD handler builds one: 'A' on the 'a' key, unshifted.
A_KEY = 0x001E0061


@pytest.mark.parametrize("key", (A_KEY, 0, 0xFFFFFFFF, 0x0048_0000, 0x1234_5678))
def test_the_console_returns_the_whole_longword_at_the_advanced_head(key):
    """`move.l 0(a1,d1.w),d0`, and the head is advanced BEFORE the load — so the record read is the
    one at head+4, which is where the interrupt handler put it."""
    ring = addrs.IOREC_IKBD
    pokes = iorec.staged(ring, 0, addrs.IOREC_KEY_BYTES,
                         [(addrs.IOREC_KEY_BYTES, struct.pack(">I", key))])
    info = run(DEVICE_CONSOLE, pokes)
    assert info["regs"]["d0"] == key
    assert head_after(info, ring) == addrs.IOREC_KEY_BYTES


@pytest.mark.parametrize("head", (0, 4, 8, 0x40, 0xF0))
def test_the_console_advances_the_head_by_one_record(head):
    ring = addrs.IOREC_IKBD
    next_head = head + addrs.IOREC_KEY_BYTES
    pokes = iorec.staged(ring, head, next_head, [(next_head, struct.pack(">I", A_KEY))])
    info = run(DEVICE_CONSOLE, pokes)
    assert info["regs"]["d0"] == A_KEY
    assert head_after(info, ring) == next_head


def test_the_console_head_wraps_to_zero_on_reaching_the_ring_s_size():
    """`cmp.w size,d1 / bcs` — UNSIGNED, and the arm it skips is `moveq #0,d1`, so the wrap lands on
    0 rather than on head+4-size. The IKBD ring is $100 bytes, so the last record starts at $fc."""
    ring = addrs.IOREC_IKBD
    size = iorec.size_of(ring)
    pokes = iorec.staged(ring, size - addrs.IOREC_KEY_BYTES, 0, [(0, struct.pack(">I", A_KEY))])
    info = run(DEVICE_CONSOLE, pokes)
    assert info["regs"]["d0"] == A_KEY
    assert head_after(info, ring) == 0


def test_the_record_is_read_before_the_advanced_head_is_stored():
    """THE ORDER OF THE DRIVER'S LAST THREE INSTRUCTIONS, and the only ring that can show it.

    `movea.l (a0),a1 / move.l 0(a1,d1.w),d0 / move.w d1,6(a0)`: the record is loaded and only then is
    the head written. Every other case here reads a record somewhere else in the buffer, where the
    two orders are indistinguishable. This one points the ring's buffer AT THE RING, so the record
    at head+4 IS the ring's own size and head words — and the store that follows changes the second
    of them. The ROM answers with the head as the caller found it; a reconstruction that advanced
    the head first answers with the head it had just written, four higher.
    """
    ring = addrs.IOREC_IKBD
    old_head, advanced = 0, addrs.IOREC_KEY_BYTES
    size = iorec.size_of(ring)
    assert advanced < size, "the case needs a head that does not wrap"
    pokes = {**iorec.buffer_poke(ring, ring), **iorec.staged(ring, old_head, advanced)}
    info = run(DEVICE_CONSOLE, pokes)
    assert info["regs"]["d0"] == (size << 16) | old_head, (
        "the record read was not the ring's own size and head as they stood before the store")
    assert head_after(info, ring) == advanced


# ---- MIDI: one byte a record, laid into the status routine's -1 -----------------------------------

@pytest.mark.parametrize("byte", (0x00, 0x01, 0x7F, 0x80, 0x90, 0xFE, 0xFF))
def test_midi_returns_the_byte_inside_the_minus_one_its_status_left(byte):
    """The quirk this file exists for: `move.b` writes D0's low byte only, over the $ffffffff the
    status driver set. A reconstruction returning the bare byte differs on every one of these."""
    ring = addrs.IOREC_MIDI
    pokes = iorec.staged(ring, 0, addrs.IOREC_MIDI_BYTES,
                         [(addrs.IOREC_MIDI_BYTES, bytes([byte]))])
    info = run(DEVICE_MIDI, pokes)
    assert info["regs"]["d0"] == addrs.MIDI_RESULT_PREFIX | byte
    assert head_after(info, ring) == addrs.IOREC_MIDI_BYTES


@pytest.mark.parametrize("head", (0, 1, 2, 0x3F))
def test_midi_advances_the_head_by_a_single_byte(head):
    """One byte a record, where the console's is four — the two drivers are otherwise identical, so
    a reconstruction sharing one width passes the console's cases and fails these."""
    ring = addrs.IOREC_MIDI
    pokes = iorec.staged(ring, head, head + 1, [(head + 1, b"\x42")])
    info = run(DEVICE_MIDI, pokes)
    assert info["regs"]["d0"] == addrs.MIDI_RESULT_PREFIX | 0x42
    assert head_after(info, ring) == head + 1


def test_the_midi_head_wraps_to_zero_on_reaching_the_ring_s_size():
    ring = addrs.IOREC_MIDI
    pokes = iorec.staged(ring, iorec.size_of(ring) - 1, 0, [(0, b"\x7e")])
    info = run(DEVICE_MIDI, pokes)
    assert info["regs"]["d0"] == addrs.MIDI_RESULT_PREFIX | 0x7E
    assert head_after(info, ring) == 0


def test_the_two_drivers_read_their_own_ring():
    """Staging the console's ring must not make MIDI ready, and the other way round."""
    key_pokes = iorec.staged(addrs.IOREC_IKBD, 0, addrs.IOREC_KEY_BYTES,
                             [(addrs.IOREC_KEY_BYTES, struct.pack(">I", A_KEY))])
    midi_pokes = iorec.staged(addrs.IOREC_MIDI, 0, 1, [(1, b"\x55")])
    assert run(DEVICE_CONSOLE, {**key_pokes, **midi_pokes})["regs"]["d0"] == A_KEY
    assert run(DEVICE_MIDI, {**key_pokes, **midi_pokes})["regs"]["d0"] == \
        addrs.MIDI_RESULT_PREFIX | 0x55


@pytest.mark.parametrize("device", NO_DRIVER_DEVICES)
def test_a_device_with_no_driver_returns_the_dispatch_s_own_scratch(device):
    """The shared `rts` again — and here it is the one arm of Bconin that does NOT block."""
    bcon.assert_no_driver(run, device)
