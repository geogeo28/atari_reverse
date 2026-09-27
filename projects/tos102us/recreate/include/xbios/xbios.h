/* The XBIOS cores one ANOTHER XBIOS core calls.
 *
 * Deliberately not an inventory of `src/xbios/`: everything else in there is reached only from
 * Python, through the candidate `.so`'s symbol table, and a declaration nobody includes is a second
 * place for a signature to drift. This header holds the cross-translation-unit calls the ROM itself
 * makes, so the compiler checks them.
 */
#ifndef TOS102US_XBIOS_H
#define TOS102US_XBIOS_H

#include <stdint.h>

/* $fc1510 — `Protobt` ($fc1636) calls it for a serial number that will not fit in three bytes. */
uint32_t xbios_random(uint8_t *image);

/* $fc2ea4 — `Ongibit` ($fc2edc) and `Offgibit` ($fc2f02) each call it twice, entering two
 * instructions in at $fc2eac with the two arguments already in D0/D1. */
uint8_t xbios_giaccess(uint16_t data, uint16_t reg_and_flag);

/* $fc2edc / $fc2f02 — port A's two read-modify-writes. `Bconout(PRT:)` ($fc2090) pulses the
 * Centronics strobe through their BODIES ($fc2ee2 / $fc2f08), which is the same routine entered
 * below its argument fetch with the mask already in D2; `entry_d0` is what both give back. */
uint32_t xbios_ongibit(uint32_t entry_d0, uint16_t bits);
uint32_t xbios_offgibit(uint32_t entry_d0, uint16_t bits);

/* $fc2f28 — `Initmous`. The VDI's mouse_init ($fca86a) and mouse_off ($fca882) take it through the
 * machine's own `trap #14` on target; off target they call it directly (`src/vdi/mouse.c`). */
uint32_t xbios_initmous(uint8_t *image, uint16_t mode, uint32_t param, uint32_t vector);

#endif /* TOS102US_XBIOS_H */
