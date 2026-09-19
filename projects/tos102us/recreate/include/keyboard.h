/* keyboard.h — the scancode half of the IKBD's input chain, and the record it leaves in the IOREC.
 *
 * `include/acia_packets.h` is the other half: it decides a byte under $f6 is a scancode and hands it
 * here. What follows is the whole of TOS's keyboard, in two routines — the shift/CapsLock/auto-
 * repeat state machine, and the translation of a scancode into the four-byte record `Bconin` reads.
 *
 * TWO CALLERS, NOT ONE. `kbd_queue_key` is also where TIMER C's auto-repeat injects the held key
 * ($fc310c), which is why it takes the IOREC the ROM leaves in A0 rather than naming `IOREC_IKBD`
 * itself: the two callers each `lea $c76,a0` for themselves, and the parameter is that register.
 */
#ifndef TOS102US_KEYBOARD_H
#define TOS102US_KEYBOARD_H

#include <stdint.h>

/* The IKBD IOREC's four-byte record, as the ROM's `swap`/`lsl.l`/`lsr.w` dance builds it:
 * kbshift, scancode, a zero, ASCII. The zero byte is not a field — it is the low half of the
 * scancode WORD the record's first half is. */
#define KEY_RECORD_KBSHIFT_SHIFT  24
#define KEY_RECORD_SCANCODE_SHIFT 16
#define KEY_RECORD_ASCII_SHIFT    0
/* ...and what `btst #3,conterm` clear leaves of it: `andi.l #$00ffffff`, which drops the shift
 * state and leaves the other three bytes alone. */
#define KEY_RECORD_WITHOUT_KBSHIFT 0x00ffffffu

/* `$fc2b5c` — the scancode arm of `acia_take_byte`: the four modifier keys and CapsLock into
 * `KBSHIFT`, the auto-repeat state `Kbrate` configures, and then the key path for everything else.
 * `iorec` is the A0 the caller carries through to `kbd_queue_key`. */
void kbd_scancode(uint8_t *image, uint8_t scancode, uint32_t iorec);

/* `$fc2c42` — a scancode into the ring: the key click, the three `Keytbl` tables, the CONTROL and
 * ALTERNATE rewrites (including the emulated mouse, which does not queue anything at all), and the
 * ring's own wrap and full rules. */
void kbd_queue_key(uint8_t *image, uint8_t scancode, uint32_t iorec);

#endif /* TOS102US_KEYBOARD_H */
