/* scroll_const.h — the road fine-scroll's geometry constants and the two seams its TWO routes share:
 * the C reference (src/scroll.c) and the STE hardware-blitter route (src/blitter_scroll.c). ONE source
 * of truth (CLAUDE.md §5) — exactly the blit_const.h / road_const.h precedent, extended with the small
 * inlines the routes must run IDENTICALLY rather than in two copies:
 *
 *   rm_scroll_advance   the per-frame scalar head — state mutation, not pixels. It must run exactly
 *                       ONCE per call whichever route draws, so it lives here and both routes call it.
 *   rm_scroll_seam_row  the 4-plane masked wrap blend at the last main column of one row. The blitter
 *                       route keeps this on the CPU (20 rows x 4 words), so it is shared, not re-derived.
 *
 * Unlike blit_const.h this header is C-only (no .S includes it), so it can carry those inlines and the
 * ScrollGeometry they produce.
 */
#ifndef RM_SCROLL_CONST_H
#define RM_SCROLL_CONST_H

#include "game.h"          /* ScrollState, RM_SCROLL_WINDOW */
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
#define SEAM_WORD_BITS     16        /* plane-word width: the seam's fraction is the top (16 - shift) bits */
#define ROAD_TOP_FILL      0xffff0000u /* plane pattern filling the area above the road band */
#define FINE_MASK          0xf       /* hscroll_pos & this = the fine bit shift */
#define COARSE_MASK        0xfff8    /* (hscroll_pos >> 1) & this = the column-aligned byte offset */

/* A whole 160-byte screen row is exactly ROAD_COLS columns, which is what lets the blitter route cover a
 * full row with one x_count and lets a partial row be main_cols columns of the same walk. */
typedef char rm_scroll_row_is_whole_columns[(ROAD_COLS * ROAD_COL_BYTES == SCREEN_ROW_BYTES) ? 1 : -1];

/* What one frame's scroll position resolves to. Produced by rm_scroll_advance, consumed by both routes. */
typedef struct {
    unsigned shift;      /* fine bit shift 0..15 (hscroll_pos & FINE_MASK) */
    uint32_t coarse;     /* byte offset of the first source column within a source row */
    int      edge;       /* columns wrapped from the row start; -1 until the scroll passes EDGE_THRESH */
    unsigned main_cols;  /* columns copied straight out of this frame's pre-rotated copy */
} ScrollGeometry;

/* The per-frame scalar head: advance hscroll_pos by seg_head * scroll_speed, publish the doubled step,
 * and resolve the position into this frame's geometry. Pure state mutation — no pixels — so a route that
 * draws differently still runs THIS, once, and leaves ScrollState byte-identical. */
static inline ScrollGeometry rm_scroll_advance(ScrollState *s) {
    uint16_t delta = (uint16_t)((int16_t)s->seg_head * (int16_t)s->scroll_speed);   /* muls.w, low word */
    s->hscroll_step2 = (uint16_t)(delta * 2);

    uint16_t h = (uint16_t)(s->hscroll_pos + delta);
    if ((int16_t)h < 0) h += SCROLL_WRAP;
    else if ((int16_t)(h - SCROLL_WRAP) >= 0) h -= SCROLL_WRAP;
    s->hscroll_pos = h;

    ScrollGeometry geo;
    geo.shift = h & FINE_MASK;
    geo.coarse = (uint32_t)(uint16_t)(((int16_t)h >> 1) & COARSE_MASK);
    /* When the scroll passes EDGE_THRESH the last `edge` columns wrap to the source row start. */
    geo.edge = -1;
    geo.main_cols = ROAD_COLS;
    if ((int16_t)(h - EDGE_THRESH) >= 0) {
        geo.edge = (uint16_t)(h - EDGE_THRESH) >> 4;
        geo.main_cols = ROAD_COLS - (unsigned)geo.edge;
    }
    return geo;
}

/* This frame's pre-rotated copy of the playfield; copy 0 is the raw playfield the seam reads. */
static inline const uint8_t *rm_scroll_copy(const uint8_t *shifted, unsigned shift) {
    return shifted + (uint32_t)shift * RM_SCROLL_WINDOW;
}

/* The wrap seam for one row: mask off the `shift` bits the wrap column owns in the last main column,
 * then OR in the top `shift` bits of the RAW wrap words. `seam` addresses that column's plane 0,
 * `wrap_raw` the row's first raw source column.
 *
 * A shift of 0 makes this a NO-OP by construction — the mask is all ones and the fraction shifts a
 * 16-bit word right by 16 (int-promoted, so 0) — which is why the blitter route skips the whole seam
 * pass when shift == 0 instead of re-writing bytes it would not change. */
static inline void rm_scroll_seam_row(uint8_t *seam, const uint8_t *wrap_raw, unsigned shift) {
    uint16_t mask = (uint16_t)(SEAM_MASK_BASE << shift);
    for (int p = 0; p < ROAD_PLANES; p++) {
        uint16_t frac = (uint16_t)(be16(wrap_raw + p * 2) >> (SEAM_WORD_BITS - shift));
        wr16(seam + p * 2, (uint16_t)((be16(seam + p * 2) & mask) | frac));
    }
}

/* Draw one ALREADY-ADVANCED scroll frame with the 68000 reference engine (src/scroll.c). Split out of
 * rm_blit_road_scroll so the blitter route can run the head once and still fall back to these exact
 * pixels; rm_blit_road_scroll is head + this. */
void rm_scroll_draw(const ScrollGeometry *geo, const uint8_t *shifted, Framebuffer *fb);

/* ---- the STE hardware-blitter route (src/blitter_scroll.c) ---------------------------------------
 * Declared here, next to the geometry it consumes, because these entry points take a ScrollState /
 * ScrollGeometry and include/blitter.h deliberately does not pull in game.h (only the route's bind,
 * which needs neither, lives there). DEFINED only by the m68k blitter build — the host .so links
 * src/scroll.c alone and never names them. */
void rm_blit_road_scroll_draw(const ScrollGeometry *geo, const uint8_t *shifted, Framebuffer *fb);
void rm_blit_road_scroll_dispatch(ScrollState *s, const uint8_t *shifted, Framebuffer *fb);
/* The boot-bound seam src/frame.c calls: the blitter dispatch on a blitter machine, rm_blit_road_scroll
 * (the C reference) otherwise. ONE declaration so the pointer type cannot drift from its definition. */
extern void (*rm_blit_road_scroll_fn)(ScrollState *, const uint8_t *, Framebuffer *);

#endif /* RM_SCROLL_CONST_H */
