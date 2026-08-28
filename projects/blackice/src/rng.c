/*
 * rng.c - the deterministic 16-bit xorshift.
 *
 * The (7, 9, 8) triple gives the full 65535-state period.  Three shifts and
 * three eors on the 68000: about 60 cycles, no table and no state outside the
 * caller's Rng.
 */
#include "rng.h"

#define XORSHIFT_A 7
#define XORSHIFT_B 9
#define XORSHIFT_C 8

void rng_seed(Rng *rng, uint16_t seed)
{
    /* Zero is the one fixed point of the recurrence, so it can never be a seed. */
    rng->state = seed ? seed : RNG_DEFAULT_SEED;
}

uint16_t rng_next(Rng *rng)
{
    uint16_t x = rng->state;

    x ^= (uint16_t)(x << XORSHIFT_A);
    x ^= (uint16_t)(x >> XORSHIFT_B);
    x ^= (uint16_t)(x << XORSHIFT_C);
    rng->state = x;
    return x;
}

uint16_t rng_below(Rng *rng, uint16_t limit)
{
    return (uint16_t)(rng_next(rng) % limit);
}
