/* wonderboy_target.h — the two seams between the reconstruction and the shim.
 *
 * NOT A SHADOW OF A KIT HEADER. Joust needs `shim_include/os.h` because the helpers it replaces are
 * `static inline` in the kit and have no link symbol; every kit symbol Wonder Boy calls is a real
 * one, so the seam there is the LINK — `build.sh` leaves the kit's `src/hw.c`, `src/psg.c`,
 * `src/sched.c`, `src/os_refusal.c` and `src/dosound_log.c` out and links `wonderboy_backend.c`
 * instead. `shim_include/` is on the include path only for this file and `string.h`.
 *
 * WHAT IS DECLARED HERE is the pair of things that CANNOT be a link-time replacement, because the
 * reconstruction's own code has to name them: the shifter writes it sinks. `../src/game.c` and
 * `../src/stage.c` carry a `#ifdef WB_ON_TARGET` arm — three lines each — that forwards their sink
 * helpers to the two functions below. Off target the arm does not compile and the differential `.so`
 * is byte-identical, which `build.sh`'s own check asserts rather than assumes.
 */
#ifndef WONDERBOY_TARGET_H
#define WONDERBOY_TARGET_H

#include <stdint.h>

/* Where the 1 MiB image array actually is. The reconstruction addresses everything as an offset
 * inside it, so an address the game publishes to the HARDWARE has to have this added.
 * 256-aligned, and asserted so — see wonderboy_backend.c's screen-base translation. */
uint32_t wb_target_image_base(void);

/* The two sinks, made real (wonderboy_backend.c). `reg` is the absolute shifter register the
 * reconstruction named, in the 24-bit bus form its own constants use ($ff8201, $ff8203, $ff8240+). */
void wb_target_shifter_byte(uint32_t reg, uint8_t value);
void wb_target_shifter_word(uint32_t reg, uint16_t value);

/* What the last screen-base translation actually put on the bus, for the smoke's read-back. */
extern uint32_t wb_target_screen_base;

/* How many iterations `flip_screen`'s two vblank waits have taken between them. `sched_poll16`
 * returns a constant and hands back an ordinary image read, so nothing about the call itself can
 * show it working; what this counts is that the spins were real and that a level-4 interrupt ended
 * them. M2's record carries it (wonderboy_backend.c). */
extern uint32_t wb_target_poll16_calls;

#endif /* WONDERBOY_TARGET_H */
