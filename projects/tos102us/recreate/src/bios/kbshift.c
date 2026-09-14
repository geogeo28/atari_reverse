/* BIOS Kbshift (function 11) — $fc0a34.
 *
 * Reports the keyboard's shift/control/alt state byte, and optionally replaces it. The byte lives at
 * $0e61 — the address the OS header publishes as `pkbshift` ($fc0024), which is how a program that
 * cannot call the BIOS finds it.
 *
 *      moveq   #0,d0
 *      move.b  KBSHIFT,d0          ; the OLD state, zero-extended: the return value
 *      move.w  4(sp),d1
 *      bmi.s   .done               ; a NEGATIVE mode is "report only"
 *      move.b  d1,KBSHIFT          ; ...otherwise the LOW BYTE of the mode word replaces it
 *   .done:
 *      rts
 *
 * THE TEST IS ON THE WORD AND THE STORE IS OF THE BYTE, which is the one thing a reconstruction can
 * get wrong here without a case noticing: `mode` = $0080 sets the state to $80 (bit 7 of a BYTE is
 * not the sign of a WORD), while `mode` = $ff80 reports without storing. Both are in the battery.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "m68k_idioms.h"

uint32_t bios_kbshift(uint8_t *image, uint16_t mode)
{
    uint8_t previous = image[KBSHIFT];

    if (!keeps_current_value_word(mode))
        image[KBSHIFT] = (uint8_t)mode;
    return previous;
}
