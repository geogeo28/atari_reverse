/* ikbd.h — the two ACIA senders `src/xbios/acia.c` holds, for the cores that send through them.
 *
 * `Initmous` builds an IKBD command packet in RAM and then `bsr`s into `Ikbdws`'s own loop at
 * `$fc221c`, and `Initmous(0)` `bsr`s into the single-byte sender at `$fc21f2` — so these are calls
 * the ROM itself makes across what are separate files here, and the compiler should check them.
 */
#ifndef TOS102US_IKBD_H
#define TOS102US_IKBD_H

#include <stdint.h>

/* $fc21f2 — one byte to the IKBD's 6850, after spinning on the status register's TDRE bit. */
void ikbd_send_byte(uint8_t byte);

/* $fc201a — the same for the MIDI 6850, which has no settling delay. `Bconout(MIDI:)` ($fc2016) and
 * `Bconout(IKBD:)` ($fc21ee) ARE these two, one `move.w 6(sp),d1` further up. */
void midi_send_byte(uint8_t byte);

/* $fc221c — `Ikbdws`'s loop: `count + 1` bytes from `at`, each through `ikbd_send_byte`. */
void ikbd_send_string(const uint8_t *image, uint16_t count, uint32_t at);

#endif /* TOS102US_IKBD_H */
