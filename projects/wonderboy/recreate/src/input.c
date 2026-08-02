/* input.c — the joystick edge pipeline: joy1_latch_edge ($88c) and joy1_newly_pressed ($682).
 *
 * The game reads its controls off an IKBD interrupt, not off a port: `ikbd_joy1_byte_handler`
 * ($858) stores each joystick-1 report byte in $877 as it arrives. That byte is asynchronous, so
 * the frame loop takes a copy of it — joy1_latch_edge, called once per frame from $882 — and keeps
 * the previous copy beside it; joy1_newly_pressed then turns the two into a rising-edge mask, which
 * is what makes a button do something once rather than every frame it is held.
 *
 * Both are pure byte moves over three fixed addresses: no hardware, no OS, no callee. The whole
 * effect of the latch is two bytes of memory; the whole effect of the edge is d0, and BOTH halves
 * of d0 matter — see g_joy1_newly_pressed.
 */
#include "input.h"
#include "wonderboy.h"

/* `move.b joy1_prev,d0 / move.b joy1_current,d1 / eor.b d1,d0 / and.b d1,d0`. Written in the
 * original's order rather than as the equivalent `current & ~prev`: the eor-then-and is what the
 * 68000 does, and this is the recreate track. */
uint8_t joy1_newly_pressed(const uint8_t *image) {
    uint8_t current = image[WB_JOY1_CURRENT];
    return (uint8_t)((image[WB_JOY1_PREV] ^ current) & current);
}

void joy1_latch_edge(uint8_t *image) {
    image[WB_JOY1_PREV] = image[WB_JOY1_CURRENT];
    image[WB_JOY1_CURRENT] = image[WB_JOY1_STATE];
}

/* Differential glue. Every instruction of joy1_newly_pressed is a `.b` op on d0, and a 68000 byte
 * op leaves the register's top 24 bits alone — so the value the routine returns is its caller's own
 * d0 with only the low byte replaced. A C function has no such register to inherit, so the harness
 * hands it the d0 the oracle was entered with and the whole longword stays diffable (the same
 * shape as g_rad_depack's entry stack pointer). All three of its callers in ../decomp.c take the
 * result as a byte, so the high bits are dead in the game and live only here, where they are what
 * pins the operand size. */
uint32_t g_joy1_newly_pressed(const uint8_t *image, uint32_t entry_d0) {
    const uint32_t d0_above_low_byte = 0xffffff00u;
    return (entry_d0 & d0_above_low_byte) | joy1_newly_pressed(image);
}
