/* aes/trp14.h — THE AES's XBIOS DOOR (`src/aes/trp14.S`, `trp14.c`): `$fee488`, four hand instructions —
 *
 *     move.l (sp)+,$95b2 / trap #14 / move.l $95b2,-(sp) / rts
 *
 * Its caller pushes an XBIOS frame — the function word, then whatever that function takes — and calls it (a Line-F
 * word): the door PARKS ITS OWN RETURN ADDRESS in AES_XBIOS_RETURN so that the trap finds the caller's words at (sp),
 * and returns through the longword. Not re-entrant, as gemdosif's `__DOS` is not. D0 is the XBIOS's answer.
 *
 * A DOOR OVER ITS CALLER'S FRAME has no C spelling (the frame is whatever was pushed), so the build ships the ROM's own
 * instructions. The C twin serves THE ONE SHAPE BAND 5's CODE CALLS IT WITH — the function word alone (sh_main's
 * Getrez, `$feb1ea`) — and takes the return address as a host argument (the VDI's gemdos_call precedent). The desk's
 * other shapes (band 6) are the `.S`'s on target and halt by name off it.
 */
#ifndef TOS102US_AES_TRP14_H
#define TOS102US_AES_TRP14_H

#ifndef __ASSEMBLER__
#include <stdint.h>

uint32_t aes_trp14(uint8_t *image, uint32_t return_site, uint16_t function);                         /* $fee488 */
#endif

#endif /* TOS102US_AES_TRP14_H */
