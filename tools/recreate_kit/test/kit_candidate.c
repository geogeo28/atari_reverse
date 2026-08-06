/* kit_candidate.c — the reconstruction side of test_psg_differential.py's miniature project.
 *
 * The kit binds no game, so it has no candidate .so and therefore no way to exercise
 * harness.differential() itself — the code that COMPARES the two sides of the PSG model. This is the
 * smallest thing that fixes that: three glue functions over ../include/psg.h, built into a .so with
 * the rest of $(KIT)/src, and bound as a one-function "project" whose .PRG holds the same
 * read-modify-write in 68000 code. What it pins is the harness plumbing, not the model — the model's
 * own pins are psg_model_probe.c next door, which drives both implementations directly.
 *
 * Every function takes the image pointer, because that is the shape harness's `glue(lib, buf)` hands
 * a candidate. None of them touches it: the whole point is that this routine's effect is entirely
 * off-image, so the byte diff sees nothing and only the ledger comparison can judge it.
 */
#include <stdint.h>

#include "psg.h"

/* The mixer's two top bits are the PSG's port A/B I/O DIRECTION lines, which `ori.b #$3f` leaves
 * alone — so they are exactly what the read-back exists to preserve, and what a fabricated 0 would
 * destroy. Same routine as the .PRG's, instruction for instruction. */
#define MIXER_REG    7
#define SILENCE_MASK 0x3f

/* The faithful reconstruction: read the mixer, merge the silence mask, write it back. */
void g_psg_rmw(uint8_t *image) {
    (void)image;
    uint8_t mixer = psg_port_read(MIXER_REG);
    psg_port_write(MIXER_REG, (uint8_t)(mixer | SILENCE_MASK));
}

/* MUTANT: reads the mixer and never writes it back. It touches no image byte — neither does the
 * correct one — so the differential's byte diff is blind to it and only _vet_psg_state can red. */
void g_psg_rmw_skips_the_write(uint8_t *image) {
    (void)image;
    psg_port_read(MIXER_REG);
}

/* A candidate that does not reach the chip at all, for the cases about what happens when the ORACLE
 * uses the path and the candidate cannot answer for it. */
void g_psg_untouched(uint8_t *image) {
    (void)image;
}
