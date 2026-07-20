/* scroll.c — remaster of blit_road_scroll (recreate's g_blit_road_scroll @0x10326).
 *
 * Horizontal fine-scroll of the double-wide road playfield (in buf_c) onto the screen's road band
 * (rows 0..103, disjoint from render_road's 104..199). Each frame:
 *   - advance hscroll_pos by seg_head*scroll_speed, wrapped into [0, SCROLL_WRAP); its low nibble is
 *     the fine bit shift, the rest a coarse byte offset into the source row;
 *   - blit ROAD_ROWS scanlines of ROAD_COLS 4-plane 16-pixel columns: each column pairs its plane
 *     word with the next column's word and rotates left by the fine shift (rol.l), sliding pixels;
 *   - once the scroll passes EDGE_THRESH the row's tail wraps to the source row start (a masked seam
 *     column then full wrap columns);
 *   - fill the area above the band with the plane pattern.
 *
 * Faithful port of the oracle-verified recreate function: the flat image + absolute-address access
 * becomes a Framebuffer draw target and a native `playfield` pointer (buf_c + screen_offset, supplied
 * by the caller). Word ops wrap mod 2^16 and branch on bit 15 — mirrored with 16-bit casts.
 */
#include "game.h"
#include "screen.h"
#include "st.h"

#define OBJ_ROAD_START_OFF 0x3480    /* draw-buffer offset where the scroll band begins (row 84) */
#define ROAD_PLANES        4         /* interleaved bitplanes per 16-pixel column */
#define ROAD_COL_BYTES     8         /* ROAD_PLANES words: one 16-pixel, 4-plane column */
#define ROAD_ROWS          0x14      /* scanlines blitted */
#define ROAD_COLS          0x14      /* columns per scanline (160-byte row) */
#define SCROLL_WRAP        0x280     /* hscroll_pos wraps modulo this (double screen width) */
#define SRC_ROW_STRIDE     0x140     /* source row pitch in buf_c (double-wide playfield) */
#define EDGE_THRESH        0x140     /* hscroll_pos >= this starts wrapping the row tail */
#define SEAM_MASK_BASE     0xffff    /* seam mask = this << shift */
#define ROAD_TOP_FILL      0xffff0000u /* plane pattern filling the area above the road band */

/* Rotate a 32-bit value left by s (0..31); s==0 is identity (avoids the >>32 UB). */
static uint32_t rol32(uint32_t v, unsigned s) {
    return s ? ((v << s) | (v >> (32 - s))) : v;
}

/* Fine-shift one 4-plane, 16-pixel column: each plane word is paired with the next column's word
 * (ROAD_COL_BYTES ahead in the source) and rotated left by shift; the low word is written to dst. */
static void scroll_column(Framebuffer *fb, Offset dst, const uint8_t *src, unsigned shift) {
    for (int p = 0; p < ROAD_PLANES; p++) {
        uint32_t pair = ((uint32_t)be16(src + ROAD_COL_BYTES + p * 2) << 16) | be16(src + p * 2);
        wr16(fb->px + dst + p * 2, (uint16_t)rol32(pair, shift));
    }
}

void rm_blit_road_scroll(ScrollState *s, const uint8_t *playfield, Framebuffer *fb) {
    uint16_t delta = (uint16_t)((int16_t)s->seg_head * (int16_t)s->scroll_speed);   /* muls.w, low word */
    s->hscroll_step2 = (uint16_t)(delta * 2);

    uint16_t h = (uint16_t)(s->hscroll_pos + delta);
    if ((int16_t)h < 0) h += SCROLL_WRAP;
    else if ((int16_t)(h - SCROLL_WRAP) >= 0) h -= SCROLL_WRAP;
    s->hscroll_pos = h;

    unsigned shift = h & 0xf;
    uint16_t coarse = (uint16_t)(((int16_t)h >> 1) & 0xfff8);          /* asr.w #1, andi.w */
    const uint8_t *wrap_base = playfield;                             /* buf_c + screen_offset */
    const uint8_t *src_base = wrap_base + sx16(coarse);
    Offset dst_base = OBJ_ROAD_START_OFF;

    /* When the scroll passes EDGE_THRESH, the last `edge` columns wrap to the source row start. */
    int edge = -1;
    unsigned main_cols = ROAD_COLS;
    if ((int16_t)(h - EDGE_THRESH) >= 0) {
        edge = (uint16_t)(h - EDGE_THRESH) >> 4;
        main_cols = ROAD_COLS - edge;
    }

    for (unsigned row = 0; row < ROAD_ROWS; row++) {
        const uint8_t *src = src_base + row * SRC_ROW_STRIDE;
        const uint8_t *wrap = wrap_base + row * SRC_ROW_STRIDE;
        Offset dst = dst_base + row * SCREEN_ROW_BYTES;

        for (unsigned c = 0; c < main_cols; c++)
            scroll_column(fb, dst + c * ROAD_COL_BYTES, src + c * ROAD_COL_BYTES, shift);

        if (edge >= 0) {
            /* Seam: mask the last main column, then OR in the wrap column's fractional pixels. */
            Offset seam = dst + (main_cols - 1) * ROAD_COL_BYTES;
            uint16_t mask = (uint16_t)(SEAM_MASK_BASE << shift);
            for (int p = 0; p < ROAD_PLANES; p++) {
                uint16_t frac = (uint16_t)rol32((uint32_t)be16(wrap + p * 2) << 16, shift);
                wr16(fb->px + seam + p * 2, (uint16_t)((be16(fb->px + seam + p * 2) & mask) | frac));
            }
            for (int c = 0; c < edge; c++)
                scroll_column(fb, dst + (main_cols + c) * ROAD_COL_BYTES, wrap + c * ROAD_COL_BYTES, shift);
        }
    }

    for (Offset off = 0; off < OBJ_ROAD_START_OFF; off += 4)
        wr32(fb->px + off, ROAD_TOP_FILL);
}
