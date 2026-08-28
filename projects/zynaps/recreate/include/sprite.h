/* sprite.h — the boot-time sprite table builders in src/sprite.c. Subsystem: sprite / video.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 */
#ifndef ZYNAPS_SPRITE_H
#define ZYNAPS_SPRITE_H

#include <stdint.h>

/* THE PRESHIFT BANK'S DEPTH — one fact, one name, and every bank in this file has it. Eight
 * frame-sized slots, one per 2-pixel phase of a 16-pixel cell; names.txt 0x153c0 reads it as
 * "-> 8-slot 2px preshift bank", the draw side re-splits it with the keep-masks at
 * `shift_mask_table` (0x1821e), and `draw_sprite_masked` indexes the rotated banks and the
 * roxr-shifted ones (asteroid, mothership) with the identical `(x & 0xf) * half-a-frame` step. So
 * the asteroid's eight frames and the mothership's eight are THIS eight, not three coincidences. */
#define SPRITE_PRESHIFT_SLOTS 8u

/* ================================================================================================
 * THE MASKED SPRITE FORMAT, which the asteroid and mothership banks below are both in and which
 * `draw_sprite_masked` @ 0x15ace consumes: a row is five words — a MASK word then the four colour
 * planes — and a sprite wider than 16 pixels is stored as separate 16-pixel CELLS, each a whole
 * `rows x 10` block, rather than interleaved row by row. A mask bit of 1 keeps the background (the
 * blank cell the expanders write is 0xffff and four zero planes), which is also why a right shift
 * feeds 1s into the mask and 0s into the planes.
 * ============================================================================================= */
#define SPRITE_MASKED_ROW_WORDS  5u      /* `move.w / move.l / move.l` per cell per row */
#define SPRITE_MASKED_ROW_BYTES 10u
#define SPRITE_MASK_WORD         0u      /* the mask's word index within a row */
#define SPRITE_MASK_TRANSPARENT 0xffffu  /* `move.w #$ffff,(a5)+` — a wholly see-through cell */

/* ================================================================================================
 * The asteroid banks. `_start` @ 0x1571a preshifts six of them, 0x1e00 bytes apart from 0x1a8ae —
 * the same store `clear_backdrop_page0` uses for the front end (video.h says so). A bank is
 * SPRITE_PRESHIFT_SLOTS frames of one 48x32 masked sprite: two cells of real pixels and a blank
 * third, which is the room a 14-pixel shift needs.
 * ============================================================================================= */
#define ASTEROID_FRAME_ROWS 32u   /* `move.w #$1f,d0` + dbf */
#define ASTEROID_FRAME_CELLS 3u   /* the `roxr` chain's three links: (a0), 320(a0), 640(a0) */
#define ASTEROID_CELL_BYTES (ASTEROID_FRAME_ROWS * SPRITE_MASKED_ROW_BYTES)   /* the 320 above */
#define ASTEROID_FRAME_BYTES (ASTEROID_FRAME_CELLS * ASTEROID_CELL_BYTES)     /* `lea 960(a0),a0` */

/* ================================================================================================
 * The boss sprite, as `mothership_sprite_expand` @ 0x157ca lays it out. The disk file is a 64x40
 * masked sprite — four cells, no margin — and the expander writes SPRITE_PRESHIFT_SLOTS identical
 * five-cell frames so that the preshifter has a blank cell to shift into, exactly as the asteroid
 * builder does.
 *
 * THE TWO ADDRESSES ARE `include/mothership.h`'s, not this header's: that subsystem owns the boss's
 * data (`../out/globals.tsv`), so they are included to be READ rather than restated — which is also
 * what keeps `test_constants.py`'s one-address-one-name check satisfied.
 *
 * THE GEOMETRY BELOW IS THIS SUBSYSTEM'S OWN, and it is deliberately NOT spelt `MOTHERSHIP_*`.
 * mothership.h reads the same store at a different granularity — its `MOTHERSHIP_FRAME_BYTES` is
 * 0xa0, one unshifted frame of the rotate banks its own routines build, while the expander's frame
 * is the five-cell 2000-byte one below. Two readings of one buffer, both verified, so they get two
 * names rather than one name with two meanings. Worth merging into mothership.h by whoever ends up
 * owning both readings.
 * ============================================================================================= */
#define BOSS_SPRITE_ROWS 40u    /* `move.w #$27,d1` + dbf */
#define BOSS_SPRITE_SOURCE_CELLS 4u   /* the four (a0)+ -> (aN)+ cells; the fifth is synthesised */
#define BOSS_SPRITE_FRAME_CELLS 5u
#define BOSS_SPRITE_CELL_BYTES (BOSS_SPRITE_ROWS * SPRITE_MASKED_ROW_BYTES)  /* `lea 400`s */
#define BOSS_SPRITE_FRAME_BYTES (BOSS_SPRITE_FRAME_CELLS * BOSS_SPRITE_CELL_BYTES)  /* 2000 */

/* ================================================================================================
 * `draw_sprite_masked` @ 0x15ace — how it indexes a preshift bank, and the two masks it clips x
 * with. Both `and.w`s are on the entity's x: the first forces it EVEN, so only the eight even
 * sub-cell phases are ever asked for, and the second picks the phase out of it.
 * ============================================================================================= */
#define SPRITE_X_EVEN_MASK    0xfffeu  /* `and.w #$fffe,d0` */
#define SPRITE_X_PHASE_MASK      0xfu  /* `and.w #$f,d0` — the pixel within the 16-pixel cell */
#define SPRITE_X_CELL_MASK    0xfff0u  /* `and.w #$fff0,d0`, then `lsr.w #1` = cell * 8 bytes */

void ship_sprite_deinterleave(uint8_t *image, uint32_t src, uint32_t dst);
uint32_t sprite_preshift8_2px(uint8_t *image, uint32_t src, uint32_t dst, uint16_t frame_bytes);
uint32_t sprite_preshift4_4px(uint8_t *image, uint32_t src, uint32_t dst, uint16_t frame_bytes);
void asteroid_preshift_bank(uint8_t *image, uint32_t bank);
void mothership_sprite_expand(uint8_t *image);
void draw_sprite_masked(uint8_t *image, uint32_t entity, uint16_t preshift_bytes_per_pixel);

#endif /* ZYNAPS_SPRITE_H */
