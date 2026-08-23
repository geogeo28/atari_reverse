/* boot.h — the boot chain's reconstructed routines (src/boot.c).
 *
 * The addresses, geometry and dispatch table are in wonderboy.h, which is the header test/layout.py
 * scrapes; only the signatures are here. src/boot.c's banner says which part of the boot chain this
 * is and ../STATUS.md's batch 44 phase A carries the inventory of the rest.
 */
#ifndef WONDERBOY_BOOT_H
#define WONDERBOY_BOOT_H

#include <stdint.h>

/* $f93c: `count_minus_1 + 1` longwords from `src` to `dst`, ascending. */
void copy_longs(uint8_t *image, uint32_t src, uint32_t dst, uint16_t count_minus_1);

/* $f938: one 32000-byte screen, `copy_longs` with the count preset. */
void copy_screen(uint8_t *image, uint32_t src, uint32_t dst);

/* $f926: WB_SCREEN_CLEAR_LONGS longwords of zero from WB_SCREEN_LOW — both screen buffers and the
 * gap between them. */
void clear_both_screens(uint8_t *image);

/* $e67e: copy every tile WB_TILE_INDEX_TABLE names out of the depacked WB_TILE_BANK into
 * WB_TILE_BITMAPS in table order, rewriting each entry with its own position as it goes.
 * NO `rts` in the original — it falls through into the boot's continuation at $e6c6. */
void bg_tile_install(uint8_t *image);

/* $e92c / $e938 / $e948 / $e95e: `count_minus_1 + 1` cells of 5, 10, 15 or 20 words from `src` to
 * `dst`. Each returns the advanced destination, which is what the caller keeps. */
uint32_t sprite_cru_copy_5w(uint8_t *image, uint32_t src, uint32_t dst, uint16_t count_minus_1);
uint32_t sprite_cru_copy_10w(uint8_t *image, uint32_t src, uint32_t dst, uint16_t count_minus_1);
uint32_t sprite_cru_copy_15w(uint8_t *image, uint32_t src, uint32_t dst, uint16_t count_minus_1);
uint32_t sprite_cru_copy_20w(uint8_t *image, uint32_t src, uint32_t dst, uint16_t count_minus_1);

/* $e87c: turn the raw SPRITES.CRU at WB_SPRITE_CRU_LOAD into the cells at WB_SPRITE_CRU_CELLS,
 * marked by WB_STAGE_NUMBER's row of WB_SPRITE_CRU_MASK_TABLE. Returns WB_SPRITE_CRU_INSTALLED, or
 * WB_SPRITE_CRU_UNKNOWN_COPIER if the dispatch table held a longword that is none of the four
 * copiers — which the original would have `jsr`ed through and no shipped input produces. Its
 * caller's `bsr.w` at $e6e8 spends no register, so both codes are out of band. */
uint32_t sprites_cru_install(uint8_t *image);

#endif /* WONDERBOY_BOOT_H */
