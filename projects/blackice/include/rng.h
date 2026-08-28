/*
 * rng.h - the one source of randomness, seeded per level.
 *
 * DESIGN 4.3 names the generator: a 32-bit linear congruential generator,
 * `state = state * RNG_MULTIPLIER + RNG_INCREMENT`, seeded from the level
 * header's `rng_seed`.  ALL simulation randomness draws from it and nothing
 * else, which is what makes a replay reproducible.
 *
 * The low bits of an LCG are notoriously short-period (bit 0 alternates), so
 * rng_next returns the HIGH half of the state.  That is also why rng_below can
 * take a remainder without smuggling the bad bits back in.
 *
 * The state lives in GameState so a replay can be snapshotted and hashed.
 *
 * 68000 cost: the multiply is 32x32, which is a __mulsi3 call (~250 cycles).
 * That is affordable because the sim draws at most a handful of numbers per
 * 25 Hz tick - it is never in a per-column or per-pixel path.
 */
#ifndef BLACKICE_RNG_H
#define BLACKICE_RNG_H

#include <stdint.h>

/* Numerical Recipes' LCG parameters, as DESIGN 4.3 spells them. */
#define RNG_MULTIPLIER   1664525u
#define RNG_INCREMENT    1013904223u
/* Used when a level carries no seed of its own; any value is a legal LCG state. */
#define RNG_DEFAULT_SEED 0xACE1u

typedef struct {
    uint32_t state;
} Rng;

void     rng_seed(Rng *rng, uint32_t seed);
/* The high 16 bits of the next state: the half whose period is full. */
uint16_t rng_next(Rng *rng);

/* Uniform-enough value in [0, limit).  `limit` must be non-zero. */
uint16_t rng_below(Rng *rng, uint16_t limit);

#endif /* BLACKICE_RNG_H */
