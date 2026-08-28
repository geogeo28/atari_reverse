/*
 * rng.c - the deterministic 32-bit LCG named by DESIGN 4.3.
 *
 * See rng.h for why the caller is handed the high half of the state and never
 * the low one.
 */
#include "rng.h"

#define RNG_HIGH_HALF_SHIFT 16

void rng_seed(Rng *rng, uint32_t seed)
{
    /*
     * Every 32-bit value is a legal LCG state - unlike the xorshift this
     * replaced, zero is not a fixed point - so a seed is taken as given and
     * only an absent one falls back to the default.
     */
    rng->state = seed;
}

uint16_t rng_next(Rng *rng)
{
    rng->state = rng->state * RNG_MULTIPLIER + RNG_INCREMENT;
    return (uint16_t)(rng->state >> RNG_HIGH_HALF_SHIFT);
}

uint16_t rng_below(Rng *rng, uint16_t limit)
{
    return (uint16_t)(rng_next(rng) % limit);
}
