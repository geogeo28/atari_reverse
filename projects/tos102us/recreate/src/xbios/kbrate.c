/* XBIOS Kbrate (function 35) — $fc309a.
 *
 * Reports the keyboard auto-repeat timing and optionally replaces either half of it. The two values
 * are adjacent BYTES — $0e82 is the delay before a held key starts repeating and $0e83 the interval
 * between repeats, both in vertical blanks — and the routine reports them as the WORD they form.
 *
 *      move.w  KBRATE_DELAY,d0     ; the old pair: delay in the high byte, repeat in the low
 *      tst.w   4(sp)
 *      bmi.s   .done               ; negative delay: report only, and do not look at the repeat
 *      move.w  4(sp),d1
 *      move.b  d1,KBRATE_DELAY     ; the LOW byte of the delay word
 *      tst.w   6(sp)
 *      bmi.s   .done
 *      move.w  6(sp),d1
 *      move.b  d1,KBRATE_REPEAT
 *   .done:
 *      rts
 *
 * THE TWO ARGUMENTS ARE NOT INDEPENDENT. A negative `delay` skips the repeat store as well, so
 * Kbrate(-1, 3) changes nothing — the ROM's `bmi` jumps past both. A reconstruction that tested each
 * argument on its own would differ on exactly that call, and it is the case this file exists for.
 *
 * THE RESULT IS A WORD OF A 32-BIT REGISTER, and the ROM's `move.w` leaves the high half of D0 as
 * the caller had it. So the C takes the D0 the dispatcher left and returns one: a `uint16_t` result
 * would describe half the register and silently agree with a reconstruction that had cleared the
 * other half, which is exactly what Tickcal next door DOES do (`clr.l d0` first) and this does not.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "m68k_idioms.h"

uint32_t xbios_kbrate(uint8_t *image, uint32_t entry_d0, uint16_t delay, uint16_t repeat)
{
    uint16_t previous = be16(image + KBRATE_DELAY);

    if (!keeps_current_value_word(delay)) {
        image[KBRATE_DELAY] = (uint8_t)delay;
        if (!keeps_current_value_word(repeat))
            image[KBRATE_REPEAT] = (uint8_t)repeat;
    }
    return set_low_word(entry_d0, previous);
}
