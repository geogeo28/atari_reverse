/* The two BIOS calls whose whole body is one system-variable read — $fc0a2e and $fc0a8a.
 *
 * They are together because they are the same routine twice over: load a system variable into D0
 * and return. Nothing else in the BIOS is that small, and splitting them into two files would put
 * two lines of C behind two headers.
 *
 *   Drvmap  ($fc0a2e)   move.l  SYSVAR_DRVBITS,d0
 *                       rts
 *
 *   Tickcal ($fc0a8a)   clr.l   d0
 *                       move.w  SYSVAR_TIMR_MS,d0
 *                       rts
 *
 * BOTH LEAVE A CLEAN 32-BIT D0 — Drvmap because the variable is a longword, Tickcal because of the
 * `clr.l` that precedes its word read. That is worth saying out loud, because the neighbouring
 * routines in this block (Kbrate, Cursconf) do NOT clear D0 first and return a word into whatever
 * the caller had in the high half.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"

/* Which drives GEMDOS has: bit 0 = A:, bit 1 = B:, and so on up to bit 31. The BIOS never computes
 * it here — the boot and the disk drivers keep `_drvbits` current and this only reports it. */
uint32_t bios_drvmap(const uint8_t *image)
{
    return be32(image + SYSVAR_DRVBITS);
}

/* Milliseconds between two system-timer ticks, for a caller that wants to turn `_hz_200` into real
 * time. The ROM keeps it as a WORD and zero-extends it, so the result is never negative. */
uint32_t bios_tickcal(const uint8_t *image)
{
    return be16(image + SYSVAR_TIMR_MS);
}
