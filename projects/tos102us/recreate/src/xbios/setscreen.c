/* XBIOS Setscreen (function $05) — $fc0ab8.
 *
 * Three independent settings behind one call: where the VDI draws (`_v_bas_ad`), where the shifter
 * reads (its two base bytes), and which resolution the machine is in. Each is skipped when its
 * argument is negative, which is TOS's spelling of "leave this one alone".
 *
 *      tst.l   4(sp)                   ; logical
 *      bmi.s   .physical
 *        move.l  4(sp),SYSVAR_V_BAS_AD
 *   .physical:
 *      tst.l   8(sp)
 *      bmi.s   .resolution
 *        move.b  9(sp),SHIFTER_BASE_HIGH   ; bits 23..16 of the LONGWORD at 8(sp)
 *        move.b  10(sp),SHIFTER_BASE_MID   ; ...and bits 15..8
 *   .resolution:
 *      tst.w   12(sp)
 *      bmi.s   .done
 *        move.b  13(sp),$44c           ; sshiftmd, the resolution the VBL reloads $ff8260 from
 *        bsr.w   $fc07d0               ; Vsync — change it at the blank, not mid-frame
 *        move.b  $44c,$ff8260
 *        clr.w   $452                  ; vblsem: lock the VBL out of the console re-init
 *        jsr     $fca914               ; ...which is what re-initialises it
 *        move.w  #1,$452
 *   .done:
 *      rts
 *
 * THE PHYSICAL BASE IS STORED FROM THE MIDDLE TWO BYTES OF ITS ARGUMENT, not from the whole
 * longword: `9(sp)` and `10(sp)` are bits 23..16 and 15..8 of the address at `8(sp)`, and bits 31..24
 * and 7..0 are dropped. That is not an economy, it is the register pair's shape (`physbase.c`), and
 * it means `Setscreen(-1, $12345678, -1)` sets the screen to `$340000 | $5600` — the low byte is
 * discarded rather than rounded, and the top byte never reaches the chip at all.
 *
 * EACH ARGUMENT IS TESTED AT ITS OWN WIDTH AND THE THREE ARE INDEPENDENT — unlike `Kbrate`, whose
 * first negative argument skips the second store as well. Here the `bmi`s fall through to the next
 * test, so `Setscreen(-1, base, -1)` is an ordinary call.
 *
 * THE RESOLUTION ARM IS NOT RECONSTRUCTED, AND HALTS RATHER THAN DOING ITS FIRST HALF. Its store,
 * its `Vsync` and its write to $ff8260 are all reconstructible; what follows them is not. `$fca914`
 * is the console driver's re-initialisation — it re-reads the resolution, picks a font
 * ($fd40d2 or $fd5b2e), calls the Line-A/VT52 setup at $fc4a48, rewrites a dozen words of console
 * state at $2974..$2995 and tail-calls $fca654 — i.e. a subsystem of its own, and one the
 * INTERRUPT half of this wave owns the other end of (the VBL handler at $fc06de reloads $ff8260
 * from the very byte this arm stores). A reconstruction that did the arm's first half and then
 * returned would leave the console describing the old resolution while the shifter showed the new
 * one, and no case could tell it from the whole routine: the differential would red on the image the
 * ROM's re-init wrote, but a CALLER would get a machine in a state the ROM never leaves it in. So
 * the arm halts at its top, before any of its stores (`recreate.h`: an unreconstructed arm must not
 * return, and must not half-run either).
 *
 * WHAT IS THEREFORE VERIFIED HERE is the two-argument shape every screen flip uses — which is what
 * `Setscreen` is called for at run time, the resolution being a thing a program does once if ever.
 */
#include <stdint.h>

#include "hw.h"
#include "machine.h"
#include "recreate.h"
#include "addrs.h"
#include "m68k_idioms.h"

/* `entry_d0` is the D0 the dispatcher left. Both reconstructed arms end at the same `rts` without
 * touching the register, so what the caller gets back is what it came in with (`gibit.c` makes the
 * same claim the other way, through a `movem`). The resolution arm's `bsr` to `Vsync` WOULD leave
 * the sampled `_frclock` there — and that arm halts below, so no case reaches it. */
uint32_t xbios_setscreen(uint8_t *image, uint32_t entry_d0, uint32_t logical, uint32_t physical,
                         uint16_t resolution)
{
    if (!keeps_current_value_long(logical))
        wr32(image + SYSVAR_V_BAS_AD, logical);

    /* Bits 23..16 and 15..8 of the argument — `9(sp)` and `10(sp)`, the two bytes the shifter has
     * registers for, spelt as `vbl.c` spells the same pair on the way out. */
    if (!keeps_current_value_long(physical)) {
        hw_write8(SHIFTER_BASE_HIGH, physical >> (2 * SHIFTER_BASE_SHIFT));
        hw_write8(SHIFTER_BASE_MID, physical >> SHIFTER_BASE_SHIFT);
    }

    if (!keeps_current_value_word(resolution))
        recreate_not_reconstructed(
            "XBIOS Setscreen's resolution change: the console re-initialisation at $fca914");
    return entry_d0;
}
