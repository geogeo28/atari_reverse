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
/* `lsl.l #3,d3` in `sprite_bank_build_preshift8` — the count above spelt as a shift, which is how
 * the original turns one frame's length into a whole bank's. One fact, so the shift is written
 * here beside the count it belongs to rather than as a second, unexplained 3 in the .c. */
#define SPRITE_PRESHIFT_SLOT_SHIFT 3u

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

/* BORROWED, and it should not stay here. `mothership_sprite_preshift` @ 0x15838 is the routine that
 * arms the boss encounter, so it writes four MOTHERSHIP-owned bytes on its way out. Three of them
 * are already named in include/mothership.h and are included from there; this fourth one is not, and
 * that header belongs to another agent this wave (README.md, "Adding a function"). It is named here
 * so the routine can be ported at all, and it MOVES to mothership.h the next time that subsystem is
 * opened — `../out/globals.tsv` says the boss owns it. STATUS.md carries the same note.
 * names.txt: `boss_sequence_active # ctx` (also read as: boss_in_playfield, mothership_active). */
#define A_boss_sequence_active 0x19aadu

/* ================================================================================================
 * `draw_sprite_masked` @ 0x15ace — how it indexes a preshift bank, and the two masks it clips x
 * with. Both `and.w`s are on the entity's x: the first forces it EVEN, so only the eight even
 * sub-cell phases are ever asked for, and the second picks the phase out of it.
 * ============================================================================================= */
#define SPRITE_X_EVEN_MASK    0xfffeu  /* `and.w #$fffe,d0` */
#define SPRITE_X_PHASE_MASK      0xfu  /* `and.w #$f,d0` — the pixel within the 16-pixel cell */
#define SPRITE_X_CELL_MASK    0xfff0u  /* `and.w #$fff0,d0`, then `lsr.w #1` = cell * 8 bytes */

/* ================================================================================================
 * `draw_sprite_masked_collide` @ 0x15b7c — the sibling blitter, which also REPORTS whether the
 * sprite landed on background pixels. Two things make its shape different from 0x15ace's:
 *
 *   * IT DRAWS ACROSS TWO CELLS. The preshift banks are built by ROTATING each 16-pixel word
 *     (`sprite_preshift8_2px` above), so a word rotated right by `s` pixels carries the pixels that
 *     belong in the NEXT cell along in its top `s` bits. `shift_mask_table` is the keep-mask that
 *     re-splits it: entry `s` is `0xffff >> s`, stored TWICE OVER so one longword serves a plane
 *     PAIR (0xffff,0xffff,0x3fff,0x3fff,0x0fff,0x0fff,...,0x0003,0x0003). The index is `s * 2` and
 *     the read is a LONG, which would overlap for an odd `s` — but `bclr #0` has already forced x
 *     even, so `s * 2` is always a multiple of four and the eight longwords actually read are
 *     disjoint. The doubling is what makes that work, not an overlap.
 *   * ITS X ORIGIN IS 0x40, NOT 0. This blitter's records are in WORLD coordinates, so screen
 *     column 0 is world x SPRITE_COLLIDE_ORIGIN_X and the playfield's first row is world y
 *     PLAYFIELD_TOP_Y (video.h). The three x bands below are therefore world values, and only the
 *     middle one subtracts the origin before indexing the row.
 * ============================================================================================= */
#define A_shift_mask_table 0x1821eu   /* names.txt # ctx (also read as: sprite_shift_mask_tbl) */
#define SPRITE_SHIFT_MASK_STRIDE 2u   /* `lsl.w #1,d0` — a WORD step into a table of longwords */
/* One 16-pixel four-plane screen cell, the unit both blitters step by. It is VIDEO geometry and it
 * is deliberately not spelt `SCREEN_CELL_*`: `include/video.h` owns every other `SCREEN_*` name and
 * belongs to another agent, so claiming one here would collide with the natural definition the day
 * that header wants it (`test_constants.py` refuses a name defined in two files). The same eight
 * bytes are also `SCROLL_PHASE_STEP` in scroll.h, read there as a column phase rather than a cell —
 * two facts, two names; `test_sprite.py` holds this one against the row stride it divides. */
#define SPRITE_CELL_BYTES 8u
#define SPRITE_CELL_LONGS 2u          /* ...read as planes 0+1, then planes 2+3 */

#define SPRITE_COLLIDE_ORIGIN_X    0x40u  /* `sub.w #$40,d0` — world x of screen column 0 */
#define SPRITE_COLLIDE_LEFT_EDGE   0x30u  /* `cmp.w #$30,d0` + `bgt` — at or left of this, nothing */
/* `cmp.w #$170,d0` + `ble` — the last x the MIDDLE band takes. Not "the last x with both cells on
 * screen": 0x170 maps to screen offset 152, the row's last cell, so the band's second cell lands at
 * `screen + 160` — the first cell of the NEXT row. That is what the original does and the
 * differential pins it (`test_collide_across_the_row` drives x = 0x170); narrowing the edge to stop
 * the wrap would be removing behaviour, not fixing a bug. */
#define SPRITE_COLLIDE_RIGHT_EDGE 0x170u
#define SPRITE_COLLIDE_RIGHT_OFF  0x180u  /* `cmp.w #$180,d0` + `blt` — at or right of it, nothing */
/* `mulu.w #$5,d2` — half a one-cell frame per row, which is this routine's own D2: it works the
 * preshift step out from the record's height instead of taking it as an argument as 0x15ace does. */
#define SPRITE_COLLIDE_ROW_HALF_WORDS 5u

void ship_sprite_deinterleave(uint8_t *image, uint32_t src, uint32_t dst);
uint32_t sprite_preshift8_2px(uint8_t *image, uint32_t src, uint32_t dst, uint16_t frame_bytes);
uint32_t sprite_preshift4_4px(uint8_t *image, uint32_t src, uint32_t dst, uint16_t frame_bytes);
void asteroid_preshift_bank(uint8_t *image, uint32_t bank);
void mothership_sprite_expand(uint8_t *image);
void draw_sprite_masked(uint8_t *image, uint32_t entity, uint16_t preshift_bytes_per_pixel);
void sprite_bank_build_preshift8(uint8_t *image, uint32_t src, uint32_t dst, uint32_t frame_bytes,
                                 uint16_t frame_count_minus_one);
void mothership_sprite_preshift(uint8_t *image);
void draw_sprite_masked_collide(uint8_t *image, uint32_t entity, uint32_t hit_flag);

#endif /* ZYNAPS_SPRITE_H */
