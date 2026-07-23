/* plane.h — write patterns for one ST "cell": the two plane-longs of a 16-pixel 4-plane column,
 * lo at byte offset `at` and hi at `at`+4 in the framebuffer bytes `px`. Every ST blit in the game
 * is built from these three ops. Masks are uniform across a cell here, so cell_and takes one; fills
 * and overlays may differ per half, so they take a lo and a hi value.
 */
#ifndef RM_PLANE_H
#define RM_PLANE_H

#include "screen.h"
#include "st.h"

/* Set the two plane-longs (pass the same value for both when the cell is uniform). */
static inline void cell_fill(uint8_t *px, Offset at, Plane4 lo, Plane4 hi) {
    wr32(px + at, lo);
    wr32(px + at + 4, hi);
}

/* Clear bits: AND both plane-longs with `mask`. */
static inline void cell_and(uint8_t *px, Offset at, Plane4 mask) {
    wr32(px + at,     be32(px + at)     & mask);
    wr32(px + at + 4, be32(px + at + 4) & mask);
}

/* Overlay ink over the background: keep the background where `mask` is set, OR in `ink` gated by
 * the per-half colour fill. (This is the masked-glyph / colour-bar blit.) */
static inline void cell_overlay(uint8_t *px, Offset at, Plane4 mask, Plane4 ink,
                                Plane4 fill_lo, Plane4 fill_hi) {
    wr32(px + at,     (be32(px + at)     & mask) | (ink & fill_lo));
    wr32(px + at + 4, (be32(px + at + 4) & mask) | (ink & fill_hi));
}

/* Transparency-blit one 8-byte cell (16 px, 4 planes) from the four source plane words A,B,C,D at
 * `src` into `px` at `at`. mask = ~(A|B|C) & D shows the background through where the sprite is
 * transparent; planes 0-2 take A/B/C, plane 3 takes D's leftover (non-A/B/C) bits. This is the
 * shared masked-sprite primitive (buggy body / foreground / lower-body sprites). `src` points into
 * the asset arena; `px` is the framebuffer — the two are distinct buffers (a sprite never composits
 * into itself), unlike recreate's single-image cousin. */
static inline void cell_transp(uint8_t *px, Offset at, const uint8_t *src) {
    uint16_t a = be16(src);
    uint16_t b = be16(src + 2);
    uint16_t c = be16(src + 4);
    uint16_t d = be16(src + 6);
    uint16_t mask = (uint16_t)(~(a | b | c) & d);
    wr16(px + at,     (uint16_t)((be16(px + at)     & mask) | a));
    wr16(px + at + 2, (uint16_t)((be16(px + at + 2) & mask) | b));
    wr16(px + at + 4, (uint16_t)((be16(px + at + 4) & mask) | c));
    wr16(px + at + 6, (uint16_t)((be16(px + at + 6) & mask) | (uint16_t)(d & ~mask)));
}

/* The dashboard graphic (recreate's draw_dashboard): a masked blit of DASH_ROWS rows, each DASH_GROUPS
 * groups of four dest words. Per group the four source words are (mask, a, b, c); each dest word keeps
 * the background where mask is set and OR-s in ink a, b, b, c (the middle source word feeds two screen
 * words). `gfx`+`src` is the source block, `px`+`dst` the destination; both step one scanline per row.
 * Shared by the HUD's fixed dashboard (phase 7) and the per-leg results dashboard. */
#define DASH_ROWS   40
#define DASH_GROUPS 8             /* 8 groups of 4 dest words (0x40 bytes) per row */

static inline void cell_dashboard(uint8_t *px, Offset dst, const uint8_t *gfx, Offset src) {
    for (int row = 0; row < DASH_ROWS; row++, dst += SCREEN_ROW_BYTES, src += SCREEN_ROW_BYTES) {
        Offset d = dst, s = src;
        for (int g = 0; g < DASH_GROUPS; g++, d += 8, s += 8) {
            uint16_t mask = be16(gfx + s);
            uint16_t ink_a = be16(gfx + s + 2), ink_b = be16(gfx + s + 4), ink_c = be16(gfx + s + 6);
            wr16(px + d,     (uint16_t)((be16(px + d)     & mask) | ink_a));
            wr16(px + d + 2, (uint16_t)((be16(px + d + 2) & mask) | ink_b));
            wr16(px + d + 4, (uint16_t)((be16(px + d + 4) & mask) | ink_b));
            wr16(px + d + 6, (uint16_t)((be16(px + d + 6) & mask) | ink_c));
        }
    }
}

#endif /* RM_PLANE_H */
