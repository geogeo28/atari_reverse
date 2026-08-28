/*
 * rng.h - the one source of randomness, seeded per level.
 *
 * A 16-bit xorshift with the (7, 9, 8) triple: full period of 65535, one
 * register wide, three shifts and three eors on the 68000.  The state lives in
 * GameState so a replay can be snapshotted and hashed.
 */
#ifndef BLACKICE_RNG_H
#define BLACKICE_RNG_H

#include <stdint.h>

#define RNG_DEFAULT_SEED 0xACE1u    /* any non-zero value; zero is a fixed point */

typedef struct {
    uint16_t state;
} Rng;

void     rng_seed(Rng *rng, uint16_t seed);
uint16_t rng_next(Rng *rng);

/* Uniform-enough value in [0, limit).  `limit` must be non-zero. */
uint16_t rng_below(Rng *rng, uint16_t limit);

#endif /* BLACKICE_RNG_H */
