/* acia_packets.h — the input half of the two 6850s: what the ACIA handler's two KBDVECS vectors do.
 *
 * `src/bios/ikbd.c` is the handler; it asks each chip in turn through `midisys` and `ikbdsys`, which
 * are the two routines declared here. Everything below them reads ONE byte out of a data port and
 * decides what it is:
 *
 *   * a MIDI byte goes straight to `midivec`, which in a stock machine is `midi_queue_byte` below;
 *   * an IKBD byte is either the CONTINUATION of a packet the previous byte started — the state is
 *     one byte, `IKBD_PACKET_KIND` — or a PACKET HEADER ($f6..$ff) or a SCANCODE (anything under
 *     it), and the scancode half is `include/keyboard.h`'s.
 *
 * WHAT MAKES ANY OF IT RUNNABLE is the declared SEQUENCE (`TRAP_MODEL.md`, Phase 16): every read of
 * a 6850's data port POPS the receive register, so a case drains a packet by declaring a LIST of
 * bytes on `$fffc02` and one on the status register beside it. Before that model these routines
 * could not be entered at all.
 */
#ifndef TOS102US_ACIA_PACKETS_H
#define TOS102US_ACIA_PACKETS_H

#include <stdint.h>

/* `$fc29fc` / `$fc2a0c` — KBDVECS' `midisys` and `ikbdsys`. Two entries three instructions long
 * that fall into one shared body, differing only in which IOREC, which 6850 and which of the two
 * overrun vectors they name. */
void midi_acia_service(uint8_t *image);
void ikbd_acia_service(uint8_t *image);

/* `$fc2a42` — the byte itself. `iorec` is the ROM's own A0, and it is the DISCRIMINANT as well as a
 * destination: the routine's first test is `cmpa.l #$c76,a0`, so anything that is not the IKBD's
 * record is MIDI. `acia_base` is the 6850's status register; the data port is two bytes above it. */
void acia_take_byte(uint8_t *image, uint32_t iorec, uint32_t acia_base);

/* `$fc2e3a` — the ROM's own `midivec`: one raw byte into a ring whose record is a single byte. The
 * captured machine holds this address in `KBDVECS_MIDIVEC`, but it is reached through that RAM
 * vector and not by name, so a case may stage anything else there. Its arguments are the registers
 * the caller leaves: A0 the IOREC, D0 the byte. */
void midi_queue_byte(uint8_t *image, uint32_t iorec, uint8_t byte);

#endif /* TOS102US_ACIA_PACKETS_H */
