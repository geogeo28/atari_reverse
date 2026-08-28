/* rng.c — the pseudo-random word generator (rand16 @ 0x13bf8).
 *
 * A 32-bit Galois LFSR: each step shifts the state left one bit and folds the tap mask back in
 * whenever the bit that left the top was a 1. The bit that left is also the bit HANDED BACK — the
 * original collects sixteen of them with `roxl.w #1,d0`, which rotates D0 left through X, and X is
 * exactly the `lsl.l`'s carry-out preserved across the fold (`move.w sr,d6` / `move.w d6,ccr`
 * bracket the `eori.l`, whose own flag writes are thrown away).
 *
 * So the result is the next sixteen output bits of the sequence, most significant first, and the
 * state left behind is the sequence advanced sixteen steps. 17 call sites use it, for everything
 * from enemy spawn jitter to the attract-mode demo.
 */
#include "machine.h"
#include "rng.h"

#define RNG_STEP_BITS 16u          /* `moveq #$f,d4` + `dbf`: sixteen single-bit steps */
#define RNG_TAP_MASK  0x1d872b41u  /* `eori.l #$1d872b41,d5`, applied on a 1 bit out of the top */

uint16_t rand16(uint8_t *image) {
    uint32_t state = be32(image + A_rng_lfsr_state);
    uint16_t result = 0;

    for (unsigned step = 0; step < RNG_STEP_BITS; step++) {
        unsigned bit_out = state >> 31;
        state <<= 1;
        if (bit_out)
            state ^= RNG_TAP_MASK;
        result = (uint16_t)((result << 1) | bit_out);
    }

    wr32(image + A_rng_lfsr_state, state);
    return result;
}

/* Register map: no inputs; D0 out = the word (its high half is zero, from the entry `moveq #0,d0`),
 * and the advanced state is written back to A_rng_lfsr_state where the image diff can see it. */
uint32_t g_rand16(uint8_t *image) {
    return rand16(image);
}
