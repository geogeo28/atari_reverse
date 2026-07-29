/* joust.h — the reconstruction's public API, plus the screen geometry its routines share.
 *
 * Joust runs on a 320x200 Atari ST low-resolution screen: 16 colours from four interleaved
 * bitplanes. Pixels are grouped into 16-pixel cells of four bitplane words, and every routine
 * here steps in whole cells, so the three constants below fix the entire memory layout.
 */
#ifndef JOUST_H
#define JOUST_H

#include <stdint.h>

#define SCREEN_ROW_BYTES 0xa0u   /* 160: one low-res scanline (320 px / 16 px per cell * 8 bytes) */
#define CELL_PIXELS      16u     /* pixels spanned by one 4-plane cell */
#define CELL_BYTES       8u      /* bytes in one 4-plane cell (four bitplane words) */

/* The 68000 counts a loop down with `subq` + `bne`, which tests only the operand size: the loop
 * always runs at least once, and a zero count wraps to the full range of that size. */
#define COUNT_MASK_BYTE  0xffu     /* `subq.b #1,dn`: 0 means 256 passes */
#define COUNT_MASK_WORD  0xffffu   /* `subq.w #1,dn`: 0 means 65536 passes */

static inline unsigned loop_passes(uint32_t count, uint32_t size_mask) {
    return ((count - 1u) & size_mask) + 1u;
}

/* --- rng.c --- */
void rng_advance(uint8_t *image, uint32_t mix);

/* --- screen.c --- */
uint32_t pos_to_screen(const uint8_t *image, uint16_t x, uint16_t y, uint16_t *shift);
void screen_to_pos(const uint8_t *image, uint32_t addr, uint16_t shift, uint16_t *x, uint16_t *y);

/* --- fill.c --- */
void make_fill_pattern(uint32_t colour, uint32_t *planes01, uint32_t *planes23);
uint32_t fill_pattern_n(uint8_t *image, uint32_t dst, uint16_t count,
                        uint32_t planes01, uint32_t planes23);

/* --- blit.c --- */
void blit_copy(uint8_t *image, uint32_t dst, uint32_t src, uint16_t cols, uint16_t rows);
void blit_or(uint8_t *image, uint32_t dst, uint32_t src, uint16_t cols, uint16_t rows);
void blit_andnot(uint8_t *image, uint32_t dst, uint32_t src, uint16_t cols, uint16_t rows);

#endif /* JOUST_H */
