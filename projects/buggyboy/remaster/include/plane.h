/* plane.h — write patterns for one ST "cell": the two plane-longs of a 16-pixel 4-plane column,
 * lo at byte offset `at` and hi at `at`+4 in the framebuffer bytes `px`. Every ST blit in the game
 * is built from these three ops. Masks are uniform across a cell here, so cell_and takes one; fills
 * and overlays may differ per half, so they take a lo and a hi value.
 */
#ifndef RM_PLANE_H
#define RM_PLANE_H

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

#endif /* RM_PLANE_H */
