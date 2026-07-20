/* scroll.c — remaster of blit_road_scroll (recreate's g_blit_road_scroll @0x10326), optimized.
 *
 * Horizontal fine-scroll of the double-wide road playfield (in buf_c) onto the screen's road band
 * (rows 0..103, disjoint from render_road's 104..199). recreate rotates every plane-word every frame
 * (a variable-count rol.l — 20 rows x 20 cols x 4 planes = 1600 rotates/frame, the pipeline's worst
 * C-vs-asm ratio). We win by precomputing: the fine-shift is constant across a frame and the playfield
 * is static per leg, so rm_scroll_prebuild builds RM_SCROLL_SHIFTS pre-rotated copies once, and the
 * per-frame blit is a plain column copy from copy[shift] — no rotates. Copy 0 is the raw playfield
 * (rotate by 0 is identity), so the edge seam reads its raw words for the masked wrap blend.
 *
 * Byte-for-byte identical output to recreate's rotate-based core (see test/test_scroll.py).
 */
#include "game.h"
#include "screen.h"
#include "st.h"

#define OBJ_ROAD_START_OFF 0x3480    /* draw-buffer offset where the scroll band begins (row 84) */
#define ROAD_COL_BYTES     8         /* one 16-pixel, 4-plane column (4 plane words) */
#define ROAD_PLANES        4
#define ROAD_ROWS          0x14      /* scanlines blitted */
#define ROAD_COLS          0x14      /* columns per scanline (160-byte row) */
#define SCROLL_WRAP        0x280     /* hscroll_pos wraps modulo this (double screen width) */
#define SRC_ROW_STRIDE     0x140     /* source row pitch in the playfield (double-wide) */
#define EDGE_THRESH        0x140     /* hscroll_pos >= this starts wrapping the row tail */
#define SEAM_MASK_BASE     0xffff    /* seam mask = this << shift */
#define ROAD_TOP_FILL      0xffff0000u /* plane pattern filling the area above the road band */
#define FINE_MASK          0xf       /* hscroll_pos & this = the fine bit shift */
#define COARSE_MASK        0xfff8    /* (hscroll_pos >> 1) & this = the column-aligned byte offset */

/* One 16-bit plane-word fine-scrolled by `shift` (0..15): `cur` shifted up, the top `shift` bits of
 * the next column's same-plane word `next` brought in from the right. (= low 16 of rol32(next:cur).) */
static inline uint16_t scroll_word(uint16_t cur, uint16_t next, unsigned shift) {
    return shift ? (uint16_t)((cur << shift) | (next >> (16 - shift))) : cur;
}

void rm_scroll_prebuild(const uint8_t *playfield, uint8_t *shifted) {
    for (unsigned s = 0; s < RM_SCROLL_SHIFTS; s++) {
        uint8_t *out = shifted + s * RM_SCROLL_WINDOW;
        for (uint32_t b = 0; b < RM_SCROLL_WINDOW; b += 2)      /* each plane-word combines with the */
            wr16(out + b, scroll_word(be16(playfield + b),      /* same plane one column (8 bytes) on */
                                      be16(playfield + b + ROAD_COL_BYTES), s));
    }
}

/* Copy a contiguous run of `nbytes` (multiple of 4) of pre-rotated columns to the framebuffer. Both
 * ends are word-aligned, so this is a straight long copy (no per-column bookkeeping). */
static inline void copy_run(Framebuffer *fb, Offset dst, const uint8_t *src, uint32_t nbytes) {
    for (uint32_t i = 0; i < nbytes; i += 4) wr32(fb->px + dst + i, be32(src + i));
}

void rm_blit_road_scroll(ScrollState *s, const uint8_t *shifted, Framebuffer *fb) {
    uint16_t delta = (uint16_t)((int16_t)s->seg_head * (int16_t)s->scroll_speed);   /* muls.w, low word */
    s->hscroll_step2 = (uint16_t)(delta * 2);

    uint16_t h = (uint16_t)(s->hscroll_pos + delta);
    if ((int16_t)h < 0) h += SCROLL_WRAP;
    else if ((int16_t)(h - SCROLL_WRAP) >= 0) h -= SCROLL_WRAP;
    s->hscroll_pos = h;

    unsigned shift = h & FINE_MASK;
    uint32_t coarse = (uint32_t)(uint16_t)(((int16_t)h >> 1) & COARSE_MASK);
    const uint8_t *sh = shifted + (uint32_t)shift * RM_SCROLL_WINDOW;   /* this frame's pre-rotated copy */
    const uint8_t *raw = shifted;                                      /* copy 0 == the raw playfield */

    /* When the scroll passes EDGE_THRESH the last `edge` columns wrap to the source row start. */
    int edge = -1;
    unsigned main_cols = ROAD_COLS;
    if ((int16_t)(h - EDGE_THRESH) >= 0) {
        edge = (uint16_t)(h - EDGE_THRESH) >> 4;
        main_cols = ROAD_COLS - edge;
    }

    for (unsigned row = 0; row < ROAD_ROWS; row++) {
        uint32_t src_off = coarse + row * SRC_ROW_STRIDE;
        uint32_t wrap_off = row * SRC_ROW_STRIDE;
        Offset dst = OBJ_ROAD_START_OFF + row * SCREEN_ROW_BYTES;

        copy_run(fb, dst, sh + src_off, main_cols * ROAD_COL_BYTES);   /* the main columns, in bulk */

        if (edge >= 0) {
            /* Seam: mask the last main column, then OR in the wrap column's fractional pixels (the top
             * `shift` bits of the raw wrap words — copy 0 is the raw playfield). */
            Offset seam = dst + (main_cols - 1) * ROAD_COL_BYTES;
            uint16_t mask = (uint16_t)(SEAM_MASK_BASE << shift);
            for (int p = 0; p < ROAD_PLANES; p++) {
                uint16_t frac = (uint16_t)(be16(raw + wrap_off + p * 2) >> (16 - shift));
                wr16(fb->px + seam + p * 2, (uint16_t)((be16(fb->px + seam + p * 2) & mask) | frac));
            }
            copy_run(fb, dst + main_cols * ROAD_COL_BYTES, sh + wrap_off, (uint32_t)edge * ROAD_COL_BYTES);
        }
    }

    for (Offset off = 0; off < OBJ_ROAD_START_OFF; off += 4)
        wr32(fb->px + off, ROAD_TOP_FILL);
}
