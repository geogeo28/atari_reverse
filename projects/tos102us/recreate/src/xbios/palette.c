/* The two XBIOS calls that set the shifter's colours — $fc0b06 and $fc0b0e.
 *
 * Together because they are the two halves of ONE row of sixteen registers at $ff8240, and they
 * reach it by opposite routes: `Setpalette` hands the whole row to the VERTICAL BLANK and returns,
 * while `Setcolor` writes one register itself, now, wherever the beam is. Splitting them into two
 * files would put the same row's arithmetic behind two headers and hide that pairing.
 *
 *   Setpalette ($06, $fc0b06)   move.l  4(sp),SYSVAR_COLORPTR
 *                               rts
 *
 *   Setcolor   ($07, $fc0b0e)   move.w  4(sp),d1
 *                               add.w   d1,d1
 *                               andi.w  #SETCOLOR_INDEX_MASK,d1
 *                               lea     SHIFTER_PALETTE,a0
 *                               move.w  0(a0,d1.w),d0       ; the OLD value...
 *                               andi.w  #SETCOLOR_VALUE_MASK,d0
 *                               tst.w   6(sp)
 *                               bmi.s   .done
 *                                 move.w  6(sp),0(a0,d1.w)  ; ...and the new one, UNMASKED
 *                            .done:
 *                               rts
 *
 * SETPALETTE DOES NOT APPLY ANYTHING, and it has no "negative means keep" arm either — the `tst`/
 * `bmi` every neighbour in this block opens with is simply absent, so EVERY argument is stored,
 * `-1` included. What consumes the pointer is the VBL handler at $fc06de, which tests it for zero,
 * copies sixteen words from it into $ff8240, and CLEARS it (`$fc074e`..`$fc0768`) — so a caller
 * that passes 0 cancels a pending palette, one that passes -1 makes the next vertical blank copy
 * sixteen words from $ffffffff, and the routine reports nothing about either. That handler belongs
 * to the interrupt half of this wave; this is the whole of the XBIOS end.
 *
 * SETCOLOR'S INDEX CANNOT LEAVE THE ROW. `add.w` doubles inside a WORD and `andi.w #$1f` then keeps
 * five bits, so the byte offset is always even and always in 0..30: colour 16 is colour 0, and
 * colour -1 ($ffff, doubled to $fffe) is colour 15. There is no bounds test anywhere and none is
 * needed — which is why this routine, unlike `Iorec` or `Setexc`, has no out-of-range arm to prove.
 * The mask is also what makes the DOUBLING's width not matter; see the note at the call site.
 *
 * THE MASK IS ON THE WAY OUT AND NOT ON THE WAY IN. `andi.w #$777` is applied to the value REPORTED,
 * because an ST shifter decodes three bits per gun and reads back garbage in the other twelve; the
 * value STORED goes to the register exactly as the caller gave it. A reconstruction that masked both
 * is indistinguishable on a real machine and diverges here on the hardware write ledger, which is
 * the ledger's point (TRAP_MODEL.md, Phase 10).
 *
 * NEITHER TOUCHES THE IMAGE THROUGH A POINTER THE CALLER SUPPLIES, and Setcolor does not touch the
 * image at all: its whole effect is one declared I/O read and one ledgered store.
 */
#include <stdint.h>

#include "hw.h"
#include "machine.h"
#include "addrs.h"
#include "m68k_idioms.h"

/* Where the next vertical blank should load sixteen palette words from, or 0 for "nothing pending".
 * The VBL is what reads it; nothing here validates the pointer, and the ROM does not either.
 *
 * `entry_d0` is the D0 the dispatcher left: `move.l 4(sp),$45a / rts` never touches the register, so
 * the caller's own comes back whole. Returning it rather than being `void` is what says so — a
 * `void` core would agree with one that had left the stored pointer there (`gibit.c`, `setprt`). */
uint32_t xbios_setpalette(uint8_t *image, uint32_t entry_d0, uint32_t palette)
{
    wr32(image + SYSVAR_COLORPTR, palette);
    return entry_d0;
}

/* One colour register, reported and optionally replaced. `entry_d0` is the D0 the dispatcher left:
 * the ROM's `move.w` writes only the low half, so the caller's high half comes back untouched. */
uint32_t xbios_setcolor(uint32_t entry_d0, uint16_t colour, uint16_t value)
{
    /* THE DOUBLING'S WIDTH IS NOT A BEHAVIOUR HERE AND IS STILL WORTH SAYING. The ROM doubles inside
     * a WORD (`add.w d1,d1`) so its product wraps at $10000 — and the five-bit mask discards every
     * bit that wrap could have moved, so a 32-bit product is the SAME FUNCTION for every argument
     * (measured: that mutant is equivalent, which is why `word_index` from m68k_idioms.h is not
     * used). What the cast buys is the CODEGEN: with it GCC emits the ROM's own `add.w`/`andi.w`
     * pair, without it a 32-bit `add.l`/`andi.l` and a `moveq` to widen — 6 cycles, measured on the
     * Tier 3 row. So it stays, as the narrower of two equal descriptions rather than as a guard. */
    uint32_t reg = SHIFTER_PALETTE + ((uint16_t)(colour * PALETTE_ENTRY_BYTES) & SETCOLOR_INDEX_MASK);
    uint16_t previous = io_read16(reg) & SETCOLOR_VALUE_MASK;

    if (!keeps_current_value_word(value))
        hw_write16(reg, value);
    return set_low_word(entry_d0, previous);
}
