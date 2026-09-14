/* XBIOS Getrez (function $04) — $fc0aac.
 *
 * The shifter's current screen resolution, as the two bits the hardware keeps it in.
 *
 *      moveq   #0,d0
 *      move.b  SHIFTER_RESOLUTION(a5),d0   ; a5 = 0, so this is $ffff8260 -> the 24-bit $ff8260
 *      and.b   #GETREZ_MODE_MASK,d0
 *      rts
 *
 * THREE INSTRUCTIONS, AND THE POINT OF RECONSTRUCTING IT IS THE MIDDLE ONE. The read is of an
 * address no Phase-7 slot names, so before the DECLARED I/O MAP existed both cores answered it a
 * fabricated 0 and a differential over this routine would have gone green reporting "low
 * resolution" whatever machine the case meant. It now reads through `io_read8`, and the case
 * declares the byte with `io_seed={SHIFTER_RESOLUTION: <byte>}` — an input of the run, exactly as a
 * declared YM2149 register or a declared MFP GPIP byte is (TRAP_MODEL.md, Phase 15).
 *
 * THE `moveq` IS NOT MODELLED AND NOTHING IS LOST BY IT: it clears the whole of D0 so that the
 * following byte move leaves bits 8..31 zero, which is what returning a `uint8_t` already means —
 * and the differential compares D0 as the oracle left it against the value this returns, so a
 * reconstruction that let a high bit through would red rather than be excused.
 */
#include <stdint.h>

#include "hw.h"
#include "addrs.h"

/* NO IMAGE ARGUMENT, like `xbios_giaccess` next door and for its reason: this routine's whole
 * effect is off-image. What the differential compares here is hw.h's ordered I/O read ledger — the
 * address, the width and the byte served — plus the value returned. */
uint8_t xbios_getrez(void)
{
    return io_read8(SHIFTER_RESOLUTION) & GETREZ_MODE_MASK;
}
