/* XBIOS Random (function $11) — $fc1510.
 *
 * The ROM's own pseudo-random generator: a 32-bit linear congruential state in the OS's BSS, seeded
 * on first use from the 200 Hz system tick, advanced once per call, and reported as its middle 24
 * bits.
 *
 *      link    a6,#-4              ; Alcyon C frame; the slot is lmul's scratch, not this one's
 *      tst.l   RANDOM_SEED
 *      bne.s   .advance
 *        move.l  SYSVAR_HZ_200,d0  ; seed = hz200 in BOTH halves of the longword
 *        moveq   #16,d1
 *        asl.l   d1,d0
 *        or.l    SYSVAR_HZ_200,d0
 *        move.l  d0,RANDOM_SEED
 *   .advance:
 *      move.l  #RANDOM_MULTIPLIER,-(sp)
 *      move.l  RANDOM_SEED,-(sp)
 *      jsr     ROM_LMUL            ; the C runtime's signed 32x32 -> LOW 32 multiply
 *      addq    #8,sp
 *      addq.l  #1,d0
 *      move.l  d0,RANDOM_SEED
 *      move.l  RANDOM_SEED,d0
 *      asr.l   #8,d0
 *      and.l   #RANDOM_MASK,d0
 *
 * WHY THE C IS A PLAIN UNSIGNED MULTIPLY. `ROM_LMUL` tracks the two operands' signs, multiplies the
 * magnitudes through three 16x16 `mulu`s, and negates the result when exactly one was negative —
 * which is the LOW 32 BITS of the product either way, because negation, truncation and the partial
 * sums are all modulo 2^32. `(uint32_t)(seed * RANDOM_MULTIPLIER)` is the same 32 bits for every
 * input, including the two the sign dance would otherwise make special (0 and 0x80000000).
 *
 * ...AND WHY THE ARITHMETIC SHIFT IS AN UNSIGNED ONE HERE. `asr.l #8` sign-extends into bits 24..31,
 * and the mask that follows takes exactly bits 0..23 — where the two shifts agree.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"

uint32_t xbios_random(uint8_t *image)
{
    uint32_t seed = be32(image + RANDOM_SEED);
    if (seed == 0) {
        uint32_t tick = be32(image + SYSVAR_HZ_200);
        seed = (tick << 16) | tick;          /* `asl.l #16` then `or.l` the WHOLE longword back in */
        wr32(image + RANDOM_SEED, seed);
    }
    seed = (uint32_t)(seed * RANDOM_MULTIPLIER) + 1;
    wr32(image + RANDOM_SEED, seed);
    return (seed >> RANDOM_SHIFT) & RANDOM_MASK;
}
