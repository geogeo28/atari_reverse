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
#include "scroll_const.h"   /* the geometry constants + the head/seam seams shared with the blitter route */

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
 * ends are word-aligned, so this is a straight long copy (no per-column bookkeeping). Written as a
 * POST-INCREMENT pointer walk, not an indexed `base + i` loop, for the same reason the top fill below
 * is: GCC emits `move.l (aN)+,(aM)+` (20 cyc) for this shape and a double-indexed
 * `move.l (aN,dI.l),(aM,dI.l)` + index bookkeeping (~17 cyc more per long) for the indexed one —
 * measured +13,690 cyc/frame on tools/bench.py's gate frame, the whole difference. */
static inline void copy_run(uint8_t *dst, const uint8_t *src, uint32_t nbytes) {
    const uint8_t *end = src + nbytes;
    while (src < end) { wr32(dst, be32(src)); src += 4; dst += 4; }
}

void rm_scroll_draw(const ScrollGeometry *geo, const uint8_t *shifted, Framebuffer *fb) {
    unsigned shift = geo->shift, main_cols = geo->main_cols;
    uint32_t coarse = geo->coarse;
    int edge = geo->edge;
    const uint8_t *sh = rm_scroll_copy(shifted, shift);   /* this frame's pre-rotated copy */
    const uint8_t *raw = shifted;                         /* copy 0 == the raw playfield */

    for (unsigned row = 0; row < ROAD_ROWS; row++) {
        uint32_t src_off = coarse + row * SRC_ROW_STRIDE;
        uint32_t wrap_off = row * SRC_ROW_STRIDE;
        Offset dst = OBJ_ROAD_START_OFF + row * SCREEN_ROW_BYTES;

        copy_run(fb->px + dst, sh + src_off, main_cols * ROAD_COL_BYTES);   /* the main columns, in bulk */

        if (edge >= 0) {
            /* Seam: mask the last main column, then OR in the wrap column's fractional pixels (the top
             * `shift` bits of the raw wrap words — copy 0 is the raw playfield). */
            Offset seam = dst + (main_cols - 1) * ROAD_COL_BYTES;
            rm_scroll_seam_row(fb->px + seam, raw + wrap_off, shift);
            copy_run(fb->px + dst + main_cols * ROAD_COL_BYTES, sh + wrap_off,
                     (uint32_t)edge * ROAD_COL_BYTES);
        }
    }

    /* Fill the area above the road band with the plane pattern. This is the bulk of the blit's cost
     * (13 KB of a constant), so use a post-increment pointer unrolled 8x rather than an indexed
     * `fb->px + off` loop (which GCC leaves as address-recompute + store per long). OBJ_ROAD_START_OFF
     * is a multiple of 32, so no remainder. The asm barrier launders the constant into a register so
     * the stores are `move.l dN,(a0)` (12 cyc) instead of `move.l #imm,(a0)` (20 cyc, operand refetched
     * every store); it is a no-op on the host build. wr32 (not a raw store) keeps host byte order. */
    uint8_t *p = fb->px, *end = fb->px + OBJ_ROAD_START_OFF;
    Plane4 fill = ROAD_TOP_FILL;
    __asm__("" : "+r"(fill));
    while (p < end) {
        wr32(p, fill);      wr32(p + 4, fill);  wr32(p + 8, fill);  wr32(p + 12, fill);
        wr32(p + 16, fill); wr32(p + 20, fill); wr32(p + 24, fill); wr32(p + 28, fill);
        p += 32;
    }
}

void rm_blit_road_scroll(ScrollState *s, const uint8_t *shifted, Framebuffer *fb) {
    ScrollGeometry geo = rm_scroll_advance(s);
    rm_scroll_draw(&geo, shifted, fb);
}
