/* BIOS Setexc (function 5) — $fc0a72.
 *
 * Reads an exception vector and, unless the caller asked for a read, replaces it. This is the whole
 * of TOS's vector installation: every AUTO-folder program, every desk accessory and the OS's own
 * GEMDOS init reach the 68000's vector table through these nine instructions.
 *
 *      move.w  4(sp),d0            ; the vector NUMBER, as a word
 *      lsl.w   #2,d0               ; ...times four — IN THE WORD, so it wraps at $10000
 *      suba.l  a0,a0
 *      lea     0(a0,d0.w),a0       ; ...and is SIGN-EXTENDED into the address
 *      move.l  (a0),d0             ; the old vector: the return value
 *      move.l  6(sp),d1
 *      bmi.s   .done               ; a NEGATIVE handler is "report only"
 *      move.l  d1,(a0)
 *   .done:
 *      rts
 *
 * THERE IS NO BOUNDS CHECK, and the arithmetic that stands in for one is the reason this routine is
 * worth its own file. The index is computed in a WORD, so vector $4000 is vector 0; and the result
 * is then sign-extended, so vector $2000 addresses $ffff8000 — the I/O page — rather than $8000.
 * Both are reproduced here rather than clamped, because a reconstruction that clamped would differ
 * from the ROM exactly where a program with a wild vector number does.
 *
 * The second of those two is out of a case's reach rather than untested: $ffff8000 is the I/O page,
 * and ROM mode refuses a run that reads an I/O byte no hardware model declares (../README.md). So
 * the bound is stated as a host-only assert instead — the reconstruction says which addresses it
 * claims to describe, rather than indexing its `uint8_t *image` into host memory to find out.
 *
 * `handler` is tested as a SIGNED LONG, so $ffffffff (the documented "just tell me") and any other
 * address with bit 31 set are both reads. Every real vector value has bit 31 clear — the 68000's
 * address bus is 24 bits — so nothing legitimate is refused by that.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#endif
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "m68k_idioms.h"

uint32_t bios_setexc(uint8_t *image, uint16_t vector, uint32_t handler)
{
    uint32_t at = word_index(vector, VECTOR_BYTES);
    uint32_t previous;

#ifdef RECREATE_HOST_DIFFERENTIAL
    /* HOST-ONLY, the way the kit prescribes (kit.mk: "asserted where there is a process to abort").
     * On target the 68000's address ALU wraps into the I/O page and this is not there to stop it. */
    assert(at < ST_RAM_BYTES);
#endif
    previous = be32(image + at);

    if (!keeps_current_value_long(handler))
        wr32(image + at, handler);
    return previous;
}
