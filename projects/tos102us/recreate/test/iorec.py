"""Staging an IOREC ring: what a case does instead of an interrupt.

The BIOS's input drivers read a ring that an interrupt handler fills, and no interrupt fires during
a differential run — the oracle enters at IPL 7 and the routine masks to 7 itself. So a case that
wants `Bconin` to return a key stages one: it writes the record into the ring's buffer and moves the
TAIL past the head, which is exactly what the IKBD or MIDI handler would have done.

The ring's base address and size are read from the SNAPSHOT rather than written down here — they are
what the boot put there, and a case that assumed them would stop describing the machine the moment a
capture came from a different configuration.
"""
import struct

from harness import BASE_IMAGE, addrs


def buffer_of(ring):
    """The ring's data buffer, as the boot left it."""
    return int.from_bytes(bytes(BASE_IMAGE[ring + addrs.IOREC_BUFFER:
                                           ring + addrs.IOREC_BUFFER + 4]), "big")


def size_of(ring):
    """...and its length in BYTES, which is what the head and tail index."""
    return int.from_bytes(bytes(BASE_IMAGE[ring + addrs.IOREC_SIZE:
                                           ring + addrs.IOREC_SIZE + 2]), "big")


def buffer_poke(ring, base):
    """Point the ring's DATA BUFFER somewhere else.

    The buffer address is an ordinary longword field of the record, so a case may move it — and one
    case has to: pointing a ring's buffer AT THE RING makes the record the driver reads overlap the
    head word it is about to store, which is the only arrangement in which the ROM's read-before-
    store order is visible at all (`src/bios/bcon.c`).
    """
    return {ring + addrs.IOREC_BUFFER: base.to_bytes(4, "big")}


def staged(ring, head, tail, records=()):
    """Pokes that set the ring's head and tail and lay `records` — (offset, bytes) — in its buffer.

    Head and tail are adjacent words at +6 and +8, so they go in as one four-byte poke; anything that
    set only one of them would leave the case describing half a ring.
    """
    pokes = {ring + addrs.IOREC_HEAD: struct.pack(">HH", head & 0xFFFF, tail & 0xFFFF)}
    base = buffer_of(ring)
    for offset, data in records:
        pokes[base + offset] = data
    return pokes
