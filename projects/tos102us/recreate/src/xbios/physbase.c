/* XBIOS Physbase (function $02) — $fc0a92.
 *
 * Where the SHIFTER is reading the picture from, asked of the chip rather than of RAM — which is the
 * whole difference between this and `Logbase` ($fc0aa6) next door, whose answer is the system
 * variable `_v_bas_ad`. The two disagree whenever a program has flipped the screen and the VBL has
 * not yet caught up, which is exactly when a program asks.
 *
 *      moveq   #0,d0
 *      move.b  SHIFTER_BASE_HIGH,d0    ; $ffff8201 -> the 24-bit $ff8201: address bits 23..16
 *      lsl.w   #8,d0
 *      move.b  SHIFTER_BASE_MID,d0     ; $ffff8203: bits 15..8
 *      lsl.l   #8,d0
 *      rts
 *
 * THE LOW EIGHT BITS OF THE ADDRESS DO NOT EXIST. An ST shifter latches two bytes and supplies eight
 * zero bits below them, which is why a screen is 256-byte aligned and why the result of this routine
 * can never be odd. The final `lsl.l #8` IS those bits.
 *
 * THE TWO SHIFTS ARE DIFFERENT WIDTHS AND ONLY THE SECOND ONE'S WIDTH IS LOAD-BEARING. The first is
 * `lsl.w`, and it runs over a register `moveq #0,d0` has just cleared and `move.b` has put ONE byte
 * into — so there is nothing above bit 7 for a width to keep or drop, and `lsl.l #8` there computes
 * the same number for every pair the chip can hold. The second is `lsl.l`, and it is where the width
 * decides: it carries the whole assembled word up into bits 23..8, where an `lsl.w` would shift
 * inside the low word and throw the HIGH byte away — every screen base above $00ffff, which is all
 * of them. Written as the arithmetic the pair amounts to, it is `((high << 8) | mid) << 8`, and the
 * ROM's own `moveq` is what makes that a whole 32-bit answer rather than a word.
 *
 * NO IMAGE ARGUMENT, like `xbios_getrez` and `xbios_giaccess`: the routine's whole input is off
 * image. What the differential compares is `hw.h`'s ordered I/O read ledger — the two addresses, in
 * this order, with the bytes the case declared — plus the value returned (TRAP_MODEL.md, Phase 15).
 */
#include <stdint.h>

#include "hw.h"
#include "addrs.h"

/* How far the HIGH register sits above the MID one: $ff8201 holds address bits 23..16 and $ff8203
 * bits 15..8, so assembling the pair means lifting one byte over the other. The same 8 as
 * `SHIFTER_BASE_SHIFT` below it and not the same fact — that one is the eight address bits the
 * shifter has no register for at all (`addrs.h`), which is why each shift names its own. */
#define SHIFTER_BASE_HIGH_OVER_MID 8

uint32_t xbios_physbase(void)
{
    uint32_t high = io_read8(SHIFTER_BASE_HIGH);
    uint32_t mid = io_read8(SHIFTER_BASE_MID);

    return ((high << SHIFTER_BASE_HIGH_OVER_MID) | mid) << SHIFTER_BASE_SHIFT;
}
