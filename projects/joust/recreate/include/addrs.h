/* addrs.h — the Joust globals that MORE THAN ONE subsystem touches, by Ghidra address.
 *
 * Every address here is a Ghidra address (image offset + the 0x10000 load base fixed by
 * project.toml / PrgLoader) and mirrors a `var` line in ../../names.txt, which stays the source
 * of truth for the name.
 *
 * A global moves here the moment a second subsystem reads it; one that only its own layer touches
 * stays in that layer's header (draw.h, object.h, ...). Two headers spelling out the same address
 * is the arrangement to avoid: no translation unit includes both, so nothing would diagnose the
 * copies drifting apart.
 */
#ifndef JOUST_ADDRS_H
#define JOUST_ADDRS_H

#define IMAGE_LOAD_BASE 0x10000u   /* where the program image starts; some code holds addresses
                                    * into itself as relocated constants (see rng.c) */

#define A_screen_base       0x10ddeu  /* .l — base of the screen every draw routine addresses from */
#define A_rng_ptr           0x10dfeu  /* .l — the pseudo-random cursor walking the program image */
#define A_playfield_bottom  0x10d60u  /* .l — screen address of the lava surface; a sprite reaching it dies */
#define A_object_table      0x10f36u  /* player 1's object slot, and the object table's base */

/* The sprite-draw scratch: a caller stages one sprite here and a blitter reads it back. The drawing
 * layer both writes and consumes it; the object layer stages it for the blitters it hands over to. */
#define A_draw_dst          0x10de8u  /* .l */
#define A_draw_src          0x10df0u  /* .l */

/* WIDTH CLASH, FAITHFULLY REPRODUCED. draw_shift and draw_rows are read as BYTES by the rider
 * blitters (draw_object_data) and by the object layer, and as WORDS by the pterodactyl one
 * (blit_sprite_planes) — and a byte read at the word's address takes its HIGH half, so the two
 * readings do not even agree on which half carries the value. The writers split the same way
 * (0x131b4 stores a byte, 0x15006 a word), so each subsystem is self-consistent and the clash only
 * shows if they interleave. Each reconstruction reads exactly the width its own instruction reads. */
#define A_draw_shift        0x10df4u  /* pixel shift within the cell; .b to those readers, .w to the pterodactyl */
#define A_draw_rows         0x10df6u  /* sprite height;               .b to those readers, .w to the pterodactyl */

#endif /* JOUST_ADDRS_H */
