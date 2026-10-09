/* trp14.c — THE AES's XBIOS DOOR's C TWIN (`aes/trp14.h`): what Tier 1's host differential proves; the target ships
 * `trp14.S`.
 */
#include <stdint.h>

#include "machine.h"
#include "recreate.h"
#include "transcribed.h"
#include "aes/aes.h"
#include "aes/trp14.h"
#include "xbios/xbios.h"

/* $fee488 — trp14 over the function word alone: its caller's return address parked, the trap, the XBIOS's answer.
 * Off target the trap is the XBIOS routine's own C core — Getrez's, the one function band 5's code calls through
 * the door with nothing after the word; any other halts by name. */
TRANSCRIBED_CORE
uint32_t aes_trp14(uint8_t *image, uint32_t return_site, uint16_t function)
{
    wr32(image + AES_XBIOS_RETURN, return_site);
#ifdef RECREATE_HOST_DIFFERENTIAL
    if (function != XBIOS_GETREZ_FN)
        recreate_not_reconstructed("trp14: the AES's XBIOS door, over a function other than Getrez — the desk's "
                                   "calls (band 6); the target's is the ROM's own instructions (trp14.S)");
    return xbios_getrez();
#else
    /* The frame is the function word (a variable: the door serves whatever its caller names), the trap, the drop. */
    register uint32_t answer __asm__("d0") = function;

    __asm__ volatile ("move.w %0,-(%%sp)\n\t"
                      "trap #14\n\t"
                      "addq.l #2,%%sp"
                      : "+d"(answer)
                      :
                      : XBIOS_TRAP_CLOBBERS);
    return answer;
#endif
}
