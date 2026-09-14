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

#endif /* TOS102US_XBIOS_H */
