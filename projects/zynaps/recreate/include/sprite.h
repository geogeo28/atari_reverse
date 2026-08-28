/* sprite.h — the boot-time sprite table builders in src/sprite.c. Subsystem: sprite / video.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 */
#ifndef ZYNAPS_SPRITE_H
#define ZYNAPS_SPRITE_H

#include <stdint.h>

/* The preshift bank both builders fill: eight frame-sized slots, one per 2-pixel phase.
 * names.txt 0x153c0: "-> 8-slot 2px preshift bank"; the draw side re-splits it with the keep-masks
 * at `shift_mask_table` (0x1821e). Shared by both entries below, hence its home here. */
#define SPRITE_PRESHIFT_SLOTS 8u

void ship_sprite_deinterleave(uint8_t *image, uint32_t src, uint32_t dst);
uint32_t sprite_preshift8_2px(uint8_t *image, uint32_t src, uint32_t dst, uint16_t frame_bytes);
uint32_t sprite_preshift4_4px(uint8_t *image, uint32_t src, uint32_t dst, uint16_t frame_bytes);

#endif /* ZYNAPS_SPRITE_H */
