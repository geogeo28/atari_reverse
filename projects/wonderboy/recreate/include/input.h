/* input.h — the joystick edge pipeline (src/input.c).
 *
 * Two leaves out of the game's per-frame input path; the three bytes they move between are
 * WB_JOY1_STATE / WB_JOY1_PREV / WB_JOY1_CURRENT in wonderboy.h, which also draws the pipeline.
 * The keyboard half of the same handler is vestigial — ../names.txt's `key_bits` comment shows no
 * scancode can ever match — so this IS the game's input, joystick only.
 */
#ifndef WONDERBOY_INPUT_H
#define WONDERBOY_INPUT_H

#include <stdint.h>

/* $682 — the bits set in joy1_current that were NOT set in joy1_prev, i.e. this frame's rising
 * edges. Returned in d0's LOW BYTE only; g_joy1_newly_pressed is what reproduces the rest of d0. */
uint8_t joy1_newly_pressed(const uint8_t *image);

/* $88c — shift the pipeline one frame down, so the next joy1_newly_pressed has something to diff. */
void joy1_latch_edge(uint8_t *image);

/* Differential glue: d0 as the ORIGINAL leaves it, given the d0 it was entered with. */
uint32_t g_joy1_newly_pressed(const uint8_t *image, uint32_t entry_d0);

#endif /* WONDERBOY_INPUT_H */
