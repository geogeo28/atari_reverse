/* fill.h — solid-colour screen fills into the framebuffer (recreate's fill_span family @0x12e5c).
 *
 * A colour index selects an 8-byte, 4-plane pattern from color_pairs; a fill copies that cell
 * repeatedly. Mirrors recreate/src/screen.c: fill_span (a run of cells), fill_words (from offset 0),
 * fill_screen (the whole buffer) and fill_rect (a cells x rows rectangle stepping one scanline).
 * Byte-identical to the 68k `move.l` pairs, so these are the between-legs flow's background fills.
 */
#ifndef RM_FILL_H
#define RM_FILL_H

#include "screen.h"
#include "st.h"

#define FILL_CELL    8                              /* one 16-px 4-plane cell; also color_pairs stride */
#define SCREEN_CELLS (SCREEN_BYTES / FILL_CELL)      /* 4000: the whole draw buffer in fill cells */

/* 8-byte fill pattern for a colour index (color_pairs entry, word-offset like the 68k). The offset is
 * sign-extended like its sibling rm_color_fill (and recreate's color_pattern): idx*FILL_CELL is taken
 * as a signed 16-bit displacement before it indexes color_pairs. */
static inline const uint8_t *rm_color_pattern(const uint8_t *color_pairs, uint16_t idx) {
    int16_t off = (int16_t)(uint16_t)(idx * FILL_CELL);
    return color_pairs + (int32_t)off;
}

#define COLOR_MASK_TEXT 0xf      /* text colour index is masked to 4 bits */
#define COLOR_MASK_NUM  0xffff   /* the number path uses the full colour word */

/* The two colour-plane fill longs for a colour index: color_pairs[(idx & mask) << 3] and its +4 half
 * (recreate's color_fill). The text path masks the index to 0xf; the number path uses the full word
 * (mask 0xffff). Shared by the glyph/number tint in the flow draw surfaces. */
static inline void rm_color_fill(const uint8_t *color_pairs, uint16_t idx, uint16_t mask,
                                 Plane4 *fill_lo, Plane4 *fill_hi) {
    int16_t off = (int16_t)(uint16_t)((idx & mask) << 3);
    *fill_lo = be32(color_pairs + (int32_t)off);
    *fill_hi = be32(color_pairs + (int32_t)off + 4);
}

/* Copy one 8-byte colour cell as two longwords (the original's `move.l` pair). */
static inline void rm_fill_cell(uint8_t *px, Offset at, const uint8_t *pattern) {
    wr32(px + at,     be32(pattern));
    wr32(px + at + 4, be32(pattern + 4));
}

/* fill_span: cells_m1+1 cells from the (sign-extended) dst offset. */
static inline void rm_fill_span(Framebuffer *fb, const uint8_t *color_pairs, Offset dst_off,
                                uint16_t color_idx, uint16_t cells_m1) {
    const uint8_t *pat = rm_color_pattern(color_pairs, color_idx);
    Offset dst = (Offset)sx16((uint16_t)dst_off);
    for (uint32_t i = 0; i <= (uint32_t)cells_m1; i++)
        rm_fill_cell(fb->px, dst + i * FILL_CELL, pat);
}

/* fill_words: fill_span from offset 0. */
static inline void rm_fill_words(Framebuffer *fb, const uint8_t *color_pairs,
                                 uint16_t color_idx, uint16_t cells_m1) {
    rm_fill_span(fb, color_pairs, 0, color_idx, cells_m1);
}

/* fill_screen: fill the whole draw buffer in one colour. */
static inline void rm_fill_screen(Framebuffer *fb, const uint8_t *color_pairs, uint16_t color_idx) {
    rm_fill_words(fb, color_pairs, color_idx, SCREEN_CELLS - 1);
}

/* fill_rect: a (cells_m1+1) x (rows_m1+1) rectangle, one scanline stride between rows. */
static inline void rm_fill_rect(Framebuffer *fb, const uint8_t *color_pairs, Offset dst_off,
                                uint16_t color_idx, uint16_t cells_m1, uint16_t rows_m1) {
    const uint8_t *pat = rm_color_pattern(color_pairs, color_idx);
    Offset dst = (Offset)sx16((uint16_t)dst_off);
    for (uint32_t r = 0; r <= (uint32_t)rows_m1; r++, dst += SCREEN_ROW_BYTES)
        for (uint32_t i = 0; i <= (uint32_t)cells_m1; i++)
            rm_fill_cell(fb->px, dst + i * FILL_CELL, pat);
}

#endif /* RM_FILL_H */
