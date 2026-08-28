/* rng.h — the pseudo-random generator (src/rng.c). Subsystem: util.
 *
 * Names and addresses are ../../names.txt's. A global lives in the header of the subsystem that
 * OWNS the data; another subsystem that needs to read it includes this header. See README.md,
 * "Adding a function".
 */
#ifndef ZYNAPS_RNG_H
#define ZYNAPS_RNG_H

#include <stdint.h>

/* .l — the 32-bit LFSR state, names.txt `rng_lfsr_state`. It lives in the initialised tail of the
 * text segment and ships seeded to 0x83e4f2b3. Nothing outside this subsystem addresses it anyway:
 * all 17 call sites go through rand16 rather than touching the state. */
#define A_rng_lfsr_state 0x195f4u

uint16_t rand16(uint8_t *image);

#endif /* ZYNAPS_RNG_H */
