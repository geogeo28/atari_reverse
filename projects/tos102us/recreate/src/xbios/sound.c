/* The two XBIOS calls that hand state to the 200 Hz timer-C path — $fc3074 and $fc3088.
 *
 * Both are the same three-instruction shape as `Kbrate` next door: report what is there, replace it
 * unless the argument is negative. They are together because both describe the SAME driver's world
 * — the one at $fc312a the timer enters 200 times a second — and neither does any of its work.
 *
 *   Dosound ($20, $fc3074)   move.l  SOUND_LIST_POINTER,d0   ; the old cursor, reported in full
 *                            move.l  4(sp),d1
 *                            bmi.s   .done
 *                              move.l  d1,SOUND_LIST_POINTER
 *                              clr.b   SOUND_LIST_DELAY
 *                         .done:
 *                            rts
 *
 *   Setprt  ($21, $fc3088)   move.w  PRINTER_CONFIG,d0       ; ...the old config, in D0's LOW half
 *                            tst.w   4(sp)
 *                            bmi.s   .done
 *                              move.w  4(sp),PRINTER_CONFIG
 *                         .done:
 *                            rts
 *
 * THE DRIVER IS NOT HERE AND MUST NOT BE. $fc312a is what walks the list Dosound plants: it reads a
 * command byte, writes $ff8800/$ff8802 directly, and keeps its own ramp byte at $0e8f. It runs from
 * the timer interrupt, not from this call, and it belongs to the interrupt half of this wave. What
 * `Dosound` does is hand it a cursor — and the `clr.b` is the handshake: $0e8e is the driver's
 * "ticks still to wait", so clearing it makes the NEXT tick start the new list instead of finishing
 * the old one's pause. A reconstruction that stored only the pointer would be silent for up to 255
 * ticks, and nothing but that byte says so.
 *
 * THE TWO REPORT AT DIFFERENT WIDTHS, and it is the ROM's own instructions rather than a choice.
 * Dosound's `move.l` leaves a clean 32-bit D0, so its result is the whole register; Setprt's
 * `move.w` writes D0's low half only and the caller's high half survives — which is why this one
 * takes the entry D0 as an argument and returns a longword, the shape `kbrate.c` states in full.
 *
 * NEITHER TESTS WHAT IT REPORTS. Both read their variable BEFORE the `bmi`, so a call that changes
 * nothing still reports, and a call that stores reports the value it is replacing rather than the
 * one it stored.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "m68k_idioms.h"
#include "sound.h"

/* Where the 200 Hz driver should read its next sound command from, reporting where it was reading
 * from before. A negative pointer only reports — and every real address on a 24-bit bus is
 * non-negative, so nothing legitimate is refused by that (`m68k_idioms.h`). */
uint32_t xbios_dosound(uint8_t *image, uint32_t list)
{
    uint32_t previous = be32(image + SOUND_LIST_POINTER);

    if (!keeps_current_value_long(list))
        sound_start_list(image, list);
    return previous;
}

/* The printer description GEMDOS and the screen dumper read (`$fc2090` tests bit 4 of it for the
 * printer's type). `entry_d0` is the D0 the dispatcher left; only its low word is written. */
uint32_t xbios_setprt(uint8_t *image, uint32_t entry_d0, uint16_t config)
{
    uint16_t previous = be16(image + PRINTER_CONFIG);

    if (!keeps_current_value_word(config))
        wr16(image + PRINTER_CONFIG, config);
    return set_low_word(entry_d0, previous);
}
