/* road.c — remaster of render_road (the pseudo-3D road rasterizer, recreate's g_render_road @0x19144).
 *
 * Draws the perspective road surface into the bottom 96 scanlines (rows 104..199) one line at a
 * time, in seven successive `dbf` bands (A, then B/C/D each a near + a far copy) over a shared
 * cursor set. Each scanline pulls a 32-bit control long from the width table (blit-variant flags in
 * the high word, road half-width in the low), adds a per-row perspective offset from the param
 * stream, and dispatches on the flag bits to a 16-pixel-column 4-plane blit: it copies road-texture
 * columns from `tex` (a flag-chosen sub-region) into the road band, fills the interior/shoulders
 * with solid plane patterns, and masks the road edge with a per-row mask.
 *
 * This is a faithful, idiomatic port of recreate's verified layer-2 bands (src/road.c rr_band_*_l2 +
 * include/road_bands.h), which are proven byte-for-byte against the Musashi oracle. The one change
 * is addressing: recreate threads a flat `image` and computes `image + offset` everywhere; here the
 * draw target is a Framebuffer and the texture source is a native pointer (`src`). Masks are always
 * read from the buf_b region before any const-texture path reassigns `src`, so a native `src`
 * pointer models both the buf_b strips and the STATIC const strips without a base-select flag.
 *
 * 16-bit-faithful throughout: control low words wrap mod 2^16 and branches after a `.w` op test the
 * word sign — mirrored with (uint16_t)/(int16_t) casts, exactly as recreate does.
 */
#include "game.h"
#include "screen.h"
#include "st.h"
#include "road_const.h"     /* RR_* engine constants + rr_regs field offsets, shared with road_band.S */

_Static_assert(RR_ROW_LONG_PAIRS * 8 == RR_ROW_STRIDE_D2, "full-row fill must advance exactly one scanline stride");

/* Threaded cursors that survive band-to-band. dst is a byte offset into fb->px; the source/table
 * cursors (a3..a6, edge_const) are native pointers into their RoadInput buffers. */
typedef struct {
    Framebuffer   *fb;
    Offset         dst;            /* on-screen road-band cursor (a2) */
    const uint8_t *tex;            /* texture strip base for the current band group (a3) */
    const uint8_t *param;          /* perspective/param word stream, monotonic (a4) */
    const uint8_t *width;          /* width/control table, reset per band group (a5) */
    const uint8_t *edge;           /* edge-run word table (a6) */
    const uint8_t *edge_const;     /* const edge-texture strips */
    const uint8_t *width_base;     /* `width` reset target */
    int16_t        stride;         /* 160 bytes/scanline (d2) */
    uint16_t       d7;             /* column-align mask (0 in band A, 0xfff8 from the first group on) */
} rr_regs;

/* Pin road_const.h's RR_OFF_* to the real struct layout on the 32-bit target, so road_band.S reads the
 * right fields. The `sizeof(void*) != 4 ||` short-circuit disables the check on the 64-bit host (whose
 * 8-byte-pointer layout differs and never meets the asm) and enforces it on the m68k target. */
_Static_assert(sizeof(void *) != 4 || __builtin_offsetof(rr_regs, dst)        == RR_OFF_DST,        "RR_OFF_DST");
_Static_assert(sizeof(void *) != 4 || __builtin_offsetof(rr_regs, tex)        == RR_OFF_TEX,        "RR_OFF_TEX");
_Static_assert(sizeof(void *) != 4 || __builtin_offsetof(rr_regs, param)      == RR_OFF_PARAM,      "RR_OFF_PARAM");
_Static_assert(sizeof(void *) != 4 || __builtin_offsetof(rr_regs, width)      == RR_OFF_WIDTH,      "RR_OFF_WIDTH");
_Static_assert(sizeof(void *) != 4 || __builtin_offsetof(rr_regs, edge)       == RR_OFF_EDGE,       "RR_OFF_EDGE");
_Static_assert(sizeof(void *) != 4 || __builtin_offsetof(rr_regs, edge_const) == RR_OFF_EDGE_CONST, "RR_OFF_EDGE_CONST");
_Static_assert(sizeof(void *) != 4 || __builtin_offsetof(rr_regs, stride)     == RR_OFF_STRIDE,     "RR_OFF_STRIDE");
_Static_assert(sizeof(void *) != 4 || __builtin_offsetof(rr_regs, d7)         == RR_OFF_D7,         "RR_OFF_D7");
/* road_band.S uses the fb pointer (rr_regs.fb, RR_OFF_FB) directly as the pixel base — valid because
 * Framebuffer is just its px[] array; pin that so a future field before px can't silently shift it. */
_Static_assert(__builtin_offsetof(Framebuffer, px) == 0, "fb pointer must equal &fb->px[0]");

/* ---- 68000 word-op helpers (word ops touch only the low 16 bits, then branch on bit 15) ---- */
static inline uint32_t rr_wset(uint32_t r, uint16_t low) { return (r & 0xffff0000u) | low; }
static inline uint32_t rr_notw(uint32_t r) { return rr_wset(r, (uint16_t)~(uint16_t)r); }
/* dbf: decrement the low word; loop while the result != -1 (0xffff). Returns true to keep looping. */
static inline int rr_dbf(uint32_t *r) { uint16_t w = (uint16_t)(*r) - 1; *r = rr_wset(*r, w); return w != 0xffff; }
static inline int16_t rr_wsub(uint16_t a, uint16_t b) { return (int16_t)(uint16_t)(a - b); }
static inline int16_t rr_wadd(uint16_t a, uint16_t b) { return (int16_t)(uint16_t)(a + b); }

/* ---- blit primitives: dst is a REAL pointer cursor into fb->px, src a native texture cursor; both
 * post-increment like the 68k `(an)+` addressing (PERF30 A4/P4 — walking a native pointer emits
 * displacement/post-increment stores instead of the base+index `fb->px + Offset` recompute per write).
 * The caller forms `uint8_t *dst = fb->px + <offset>` once per row/tail; the offset stays 32-bit
 * (mod 2^32) so it never goes negative on the 64-bit host — see st.h's pointer-walking rule. ---- */

/* copy one long (half a 16-pixel 4-plane column) src->dst, advancing both. */
static inline void rr_copy_long(uint8_t **dst, const uint8_t **src) {
    wr32(*dst, be32(*src)); *src += 4; *dst += 4;
}
/* copy one long masked by the full-long edge mask. */
static inline void rr_copy_long_masked(uint8_t **dst, const uint8_t **src, Plane4 mask) {
    wr32(*dst, be32(*src) & mask); *src += 4; *dst += 4;
}
/* write one forward shoulder-fill pair (interior plane long, then edge plane long). */
static inline void rr_fill_pair(uint8_t **dst, Plane4 lo, Plane4 hi) {
    wr32(*dst, lo); *dst += 4; wr32(*dst, hi); *dst += 4;
}
/* write one backward shoulder-fill pair (predecrement — the 68k `move.l dN,-(a0)` tail fill). */
static inline void rr_fill_pair_rev(uint8_t **dst, Plane4 lo, Plane4 hi) {
    *dst -= 4; wr32(*dst, hi); *dst -= 4; wr32(*dst, lo);
}
/* word RMW on the framebuffer: word[at] &= mask.w (the 68k `and.w dN,-4(a0)` masks a long's hi word). */
static inline void rr_andw(uint8_t *at, Plane4 mask) {
    wr16(at, (uint16_t)(be16(at) & (uint16_t)mask));
}
/* solid-fill a whole 160-byte scanline starting at `at` (the 68k `moveq #9,dbf` ten-times loop of
 * (lo,hi,lo,hi) writes — i.e. RR_ROW_LONG_PAIRS (lo,hi) pairs). */
static void rr_fill_row(uint8_t *at, Plane4 lo, Plane4 hi) {
    for (int i = 0; i < RR_ROW_LONG_PAIRS; i++, at += 8) { wr32(at, lo); wr32(at + 4, hi); }
}
/* solid-fill the left shoulder [row_start, row_start + col): col is column-aligned. */
static void rr_fill_shoulder(uint8_t *row_start, int16_t col, Plane4 lo, Plane4 hi) {
    for (int cell = (int)((uint16_t)col >> 3); cell > 0; cell--, row_start += 8) {
        wr32(row_start, lo); wr32(row_start + 4, hi);
    }
}
/* draw the antialiased edge cell (one 16-pixel column) at dst: two longs, the first hi-word masked. */
static void rr_draw_edge_cell(uint8_t **dst, const uint8_t **src, Plane4 mask) {
    uint8_t *edge = *dst;
    rr_copy_long(dst, src);
    rr_andw(edge, mask);
    rr_copy_long(dst, src);
}

/* Inter-band-group step: rewind dst up the screen, advance the texture to the next sub-block and the
 * edge cursor down, and reset the width cursor to its base. */
static inline void rr_group_step(rr_regs *r) {
    r->dst  -= RR_DST_BAND_STEP;
    r->tex  += RR_SRC_BAND_STEP;
    r->edge -= RR_EDGE_BAND_STEP;
    r->width = r->width_base;
}


/* =====================================================================================
 * Band A — a two-pass renderer. Each scanline has a road "edge" column at dst + col
 * (col = the aligned road half-width). Forward from the edge it copies texture longs then
 * gap-fills; backward it fills the left shoulder. A negative aligned width (road off the left edge)
 * degenerates to a single forward fill.
 * ===================================================================================== */

/* shoulder/interior plane-pattern select (the backward-fill colours). */
static void rr_band_A_shoulder_pattern(uint32_t ctrl, int center, Plane4 *lo, Plane4 *hi) {
    *lo = 0x0000ffffu;
    *hi = 0x0000ffffu;
    if (!center) {                                    /* split */
        if ((int32_t)ctrl < 0 && (ctrl & RR_F_PLANE_HI)) { *lo = 0xffffffffu; *hi = 0; }
    } else {                                          /* centre */
        if ((ctrl & RR_F_SRC_CONST) && (int32_t)ctrl >= 0 && !(ctrl & RR_F_PLANE_HI))
            *lo = 0xffffffffu;
    }
    if (ctrl & RR_F_WIDE) {
        *lo = 0xffffffffu; *hi = 0;
        if (ctrl & RR_F_SRC_100) {
            *lo = 0;
            if (!(ctrl & RR_F_SRC_400)) *lo = 0x0000ffffu;
        }
    }
}

/* backward left-shoulder fill: from the edge cell (`base + edge_off`) leftward, writing (lo,hi) cells.
 * `width` counts down a cell (8 bytes) at a time; a cell still past the row end (>= stride) is skipped;
 * the walk stops when the position goes negative or the run `count` is exhausted.
 *
 * Two phases so no pointer is ever formed past px[]'s one-past-end: `edge_off` (= row_dst + col) can be
 * beyond the framebuffer when col overshoots the row (bottom rows, full-width road), and those are
 * exactly the skipped cells. The skip prefix (width >= stride) walks in Offset space; once width drops
 * into the row the cursor is in-bounds, so the write suffix walks a real pointer with the A4
 * predecrement stores (base+index per write would defeat that and cost ~8k cyc — measured). width only
 * shrinks, so once < stride every remaining cell writes — the skip test drops out of the hot loop. */
static void rr_band_A_shoulder_fill(uint8_t *base, Offset edge_off, int16_t width, uint32_t count,
                                    int16_t stride, Plane4 lo, Plane4 hi) {
    Offset shoulder = edge_off;
    for (;;) {                                                  /* skip phase (off-row cells) */
        width = rr_wsub((uint16_t)width, 8);
        if (width < 0) return;
        if (rr_wsub((uint16_t)width, (uint16_t)stride) < 0) break;   /* dropped into the row */
        shoulder -= 8;
        if (!rr_dbf(&count)) return;
    }
    uint8_t *cur = base + shoulder;                             /* write phase (in-bounds cells) */
    for (;;) {
        rr_fill_pair_rev(&cur, lo, hi);
        if (!rr_dbf(&count)) return;
        width = rr_wsub((uint16_t)width, 8);
        if (width < 0) return;
    }
}

/* forward interior for a SPLIT row: 4 texture longs (last edge-masked when `masked_edge`) for a wide
 * gap, or 2 for a narrow one, then gap-fill to the row end. Entered only when pos = col - stride < 0. */
static void rr_band_A_interior_split(uint8_t **dst, const uint8_t **src, int16_t pos,
                                     int masked_edge, Plane4 edge_mask, Plane4 gap_lo, Plane4 gap_hi) {
    if (rr_wadd((uint16_t)pos, 8) >= 0) {             /* narrow gap: 2 longs */
        rr_copy_long(dst, src);
        rr_copy_long(dst, src);
    } else {                                          /* wide gap: 4 longs (last masked on the C variant) */
        rr_copy_long(dst, src);
        rr_copy_long(dst, src);
        rr_copy_long(dst, src);
        if (masked_edge) rr_copy_long_masked(dst, src, edge_mask);
        else             rr_copy_long(dst, src);
    }
    pos = rr_wadd((uint16_t)rr_wadd((uint16_t)pos, 8), 8);
    while (pos < 0) { rr_fill_pair(dst, gap_lo, gap_hi); pos = rr_wadd((uint16_t)pos, 8); }
}

/* forward interior for a CENTRE/WIDE row: a narrow gap copies 2 longs and stops; a wide gap copies 4
 * longs then gap-fills, bounded by both the row end and the run `count`. */
static void rr_band_A_interior_center(uint8_t **dst, const uint8_t **src, int16_t pos,
                                      uint32_t count, Plane4 gap_lo, Plane4 gap_hi) {
    if (rr_wadd((uint16_t)pos, 8) >= 0) {             /* narrow gap: 2 longs, no fill */
        rr_copy_long(dst, src);
        rr_copy_long(dst, src);
        return;
    }
    rr_copy_long(dst, src);
    rr_copy_long(dst, src);
    rr_copy_long(dst, src);
    rr_copy_long(dst, src);
    pos = rr_wadd((uint16_t)pos, 8);
    for (;;) {
        pos = rr_wadd((uint16_t)pos, 8);
        if (pos >= 0) break;
        rr_fill_pair(dst, gap_lo, gap_hi);
        if (!rr_dbf(&count)) break;
    }
}

/* Bands A and C inline into rm_render_road, bands B/D are separate calls — the shape plain C compiles
 * (PERF30 A4 — three resident cursor-sets; localizing A/C regressed +7,526). always_inline forces it:
 * once rm_render_road calls the external asm band-D core, GCC's auto-inliner de-inlines band A into a
 * cold `.constprop` clone (+17k cyc), so A and both C halves are pinned inline here to keep them
 * resident. See rm_render_road's slice-1 cost note. */
static inline __attribute__((always_inline)) void rr_band_A(rr_regs *r) {
    Framebuffer *fb = r->fb;
    const int16_t stride = r->stride;
    uint32_t rows = 0x5f;                             /* 96 scanlines */

    for (;;) {
        const uint8_t *src = r->tex;
        Offset row_dst = r->dst;

        uint32_t ctrl = be32(r->width); r->width += 4;
        uint16_t half_width = (uint16_t)(ctrl + be16(r->param)); r->param += 2;
        ctrl = (ctrl & 0xffff0000u) | half_width;
        src += sx16((uint16_t)((ctrl & 0xf) << 4));           /* fine-x sub-column */
        Plane4 edge_mask = be32(src + RR_MASK_OFF_HI);        /* unconditional (band A) */
        int16_t edge_seed = (int16_t)be16(r->param); r->param += 2;

        Plane4 fill_lo = 0xffffffffu, fill_hi = 0x0000ffffu;  /* interior/gap plane pattern */
        if (ctrl & RR_F_PLANE_HI) fill_hi = 0xffff0000u;

        int is_split = (ctrl & RR_F_SPLIT_A) && !(ctrl & RR_F_WIDE) && (ctrl & RR_F_SKIP_ABC);
        int plane_hi = (ctrl & RR_F_PLANE_HI) != 0;
        uint32_t count_long;

        /* ---- source-strip dispatch (sets src, fill pattern, count_long) ---- */
        if (is_split) {
            r->edge += 2;
            src += sx16((uint16_t)edge_seed);
            count_long = be32(r->param); r->param += 4;         /* move.l (a4)+ */
            fill_hi = 0;
            if (plane_hi) {
                fill_lo = 0; src += RR_SRC_A800;
                if (be16(r->edge - 2) != 0) src += RR_SRC_0A00;
            } else {
                src += sx16(be16(r->edge - 2));
            }
        } else {
            if (!(ctrl & RR_F_SPLIT_A)) {                       /* centre-run */
                src += sx16((uint16_t)edge_seed) + sx16(be16(r->edge)); r->edge += 2;
                if (ctrl & RR_F_PLANE_HI) src += RR_SRC_5800;
                else if ((ctrl & RR_F_SRC_CONST) && (int32_t)ctrl >= 0) src = r->edge_const + RR_CONST_5BAA;
            } else if (ctrl & RR_F_WIDE) {                      /* wide src select */
                r->edge += 2;
                fill_hi = 0; src += RR_SRC_5000;
                if (ctrl & RR_F_SRC_400) {
                    src += RR_SRC_0400;
                    if (!(ctrl & RR_F_SRC_100)) { src += RR_SRC_0100; fill_lo = 0; }
                } else if (!(ctrl & RR_F_SRC_100)) {
                    src += RR_SRC_0100; fill_lo = 0x0000ffffu;
                }
            } else {                                            /* hi/const src select */
                r->edge += 2;
                if (ctrl & RR_F_PLANE_HI) src += RR_SRC_5800;
                else if ((ctrl & RR_F_SRC_CONST) && (int32_t)ctrl >= 0) src = r->edge_const + RR_CONST_5BAA;
            }
            count_long = be32(r->param); r->param += 4;         /* move.l (a4)+ */
        }

        int16_t col = (int16_t)((uint16_t)((int16_t)half_width >> 1) & RR_D7_WORD_MASK);

        if (col < 0) {
            /* ---- narrow: a single forward fill, no shoulder pass ---- */
            uint8_t *dst = fb->px + row_dst;
            if (is_split) {
                uint32_t count = 0x13;
                if (rr_wadd((uint16_t)col, 8) >= 0) {           /* copy an edge cell first */
                    count = 0x12; src += 8;
                    if (plane_hi) { rr_copy_long(&dst, &src); rr_copy_long(&dst, &src); }
                    else          { rr_copy_long(&dst, &src);
                                    rr_copy_long_masked(&dst, &src, edge_mask); }
                }
                do { rr_fill_pair(&dst, fill_lo, fill_hi); } while (rr_dbf(&count));
            } else {                                            /* narrow centre */
                src += 8;
                int16_t col_cells = rr_wadd((uint16_t)col, 8);
                if (col_cells >= 0) { rr_copy_long(&dst, &src); rr_copy_long(&dst, &src); }
                else                { col_cells = rr_wadd((uint16_t)col_cells, 8); }
                col_cells = (int16_t)((int16_t)col_cells >> 3);
                uint32_t count = (uint16_t)((count_long & 0xffff) + (uint16_t)col_cells);
                if ((int16_t)count >= 0)
                    do { rr_fill_pair(&dst, fill_lo, fill_hi); } while (rr_dbf(&count));
            }
            r->dst += stride;
            if (!rr_dbf(&rows)) break;
            continue;
        }

        /* ---- wide: forward texture blit from the edge, then a backward shoulder fill ---- */
        Offset edge_off = row_dst + sx16((uint16_t)col);
        int16_t pos = rr_wsub((uint16_t)col, (uint16_t)stride);
        if (pos < 0) {                                        /* col < stride: the forward dst is in-bounds */
            uint8_t *dst = fb->px + edge_off;
            if (is_split) rr_band_A_interior_split(&dst, &src, pos, !plane_hi, edge_mask,
                                                   fill_lo, fill_hi);
            else          rr_band_A_interior_center(&dst, &src, pos, count_long & 0xffff,
                                                    fill_lo, fill_hi);
        }
        Plane4 sh_lo, sh_hi;
        rr_band_A_shoulder_pattern(ctrl, /*center=*/!is_split, &sh_lo, &sh_hi);
        rr_band_A_shoulder_fill(fb->px, edge_off, col, count_long >> 16, stride, sh_lo, sh_hi);

        r->dst += stride;
        if (!rr_dbf(&rows)) break;
    }
}


/* =====================================================================================
 * Band B — near copy (SPLIT_B blit) then far copy (a distinct, wider blit tail). Default fill is
 * lo=0xffff0000 / hi=0x0000ffff, the edge mask (loaded only on MASK_A) masks the HIGH WORD of the
 * split long, and the two tails place the road differently.
 *
 * rr_band_B_c is the byte-exact C REFERENCE (always compiled, as band D's). PERF30 road-asm slice 2 ships
 * a hand-m68k core (src/asm/road_band.S rr_band_B_asm) reached via RR_BAND_B_FN; test/test_asm_road.py
 * pins the two byte-identical under Musashi. `unused`: the shipping asm build reaches band B through the
 * asm and never calls this, but keeping it compiled (as blit.c/objshift2.S do) is what makes the A/B clean.
 * ===================================================================================== */
static __attribute__((unused)) void rr_band_B_c(rr_regs *r, uint32_t rows_m1, int second) {
    Framebuffer *fb = r->fb;
    const int16_t stride = r->stride;
    const uint16_t col_mask = r->d7;  /* column-align mask (68k d7) */
    /* Localize the band cursors so GCC keeps them in registers: through `r` the compiler must assume
     * every framebuffer store may alias r->*, and reloads/rewrites the struct fields per scanline
     * (PERF30 A4 profile — `movel %aN,%a2@(12/16/20)` per row). tex/edge_const are read-only here;
     * param/width/edge/dst advance and are written back once at return. Deliberately NOT applied to
     * bands A/C: measured +7,526 cyc there (A/C inline into rm_render_road; three resident cursor-sets
     * spill) — see PERF30.md. */
    const uint8_t *tex = r->tex, *edge_const = r->edge_const;
    const uint8_t *param = r->param, *width = r->width, *edge = r->edge;
    Offset dst_row = r->dst;
    uint32_t remaining = rows_m1;

    for (;;) {
        const uint8_t *src = tex;
        uint8_t *dst = fb->px + dst_row;

        uint32_t ctrl = be32(width); width += 4;
        uint16_t half_width = (uint16_t)(ctrl + be16(param)); param += 2;
        ctrl = (ctrl & 0xffff0000u) | half_width;
        src += sx16((uint16_t)((ctrl & 0xf) << 4));           /* fine-x sub-column */
        int16_t edge_seed = (int16_t)be16(param); param += 2;

        Plane4 fill_lo = 0xffff0000u, fill_hi = 0x0000ffffu, edge_mask = 0xffffffffu;
        if (ctrl & RR_F_MASK_A) { fill_lo = 0; edge_mask = be32(src + RR_MASK_OFF_HI); }

        /* ---- source-strip dispatch ---- */
        if (!(ctrl & RR_F_SPLIT_B)) {                          /* no-split: edge-relative strip */
            src += sx16((uint16_t)edge_seed) + sx16(be16(edge)); edge += 2;
            if (ctrl & RR_F_PLANE_HI) src += RR_SRC_5800;
        } else if ((ctrl & RR_F_SKIP_ABC) && (int32_t)ctrl < 0) {
            edge += 2; dst_row += stride;                    /* flagged blank scanline */
            if (!rr_dbf(&remaining)) break;
            continue;
        } else {
            edge += 2;
            if (ctrl & RR_F_WIDE) {                            /* wide/solid-centre strip */
                fill_hi = 0; src += RR_SRC_4700;
                if (ctrl & RR_F_SRC_400) {
                    src += RR_SRC_0400;
                    if (!(ctrl & RR_F_SRC_100)) src = edge_const + RR_CONST_5B7A;
                } else {
                    fill_lo = rr_notw(fill_lo);
                    if (!(ctrl & RR_F_SRC_100)) src = edge_const + RR_CONST_5B9A;
                }
            } else if (ctrl & RR_F_PLANE_HI) {
                src += RR_SRC_5800;
            }
        }

        int16_t col = (int16_t)((uint16_t)((int16_t)half_width >> 1) & col_mask);

        if (!second) {
            /* ---- near tail: edge cell at row_start + 8 + col, forward shoulder fill ---- */
            dst += 8; src += 8;
            dst += sx16((uint16_t)col);
            int16_t e = rr_wadd((uint16_t)col, 8);
            if (e < 0) {
                rr_fill_row(fb->px + dst_row, fill_lo, fill_hi);   /* road off-screen: fill row */
            } else {
                int16_t rem = rr_wsub((uint16_t)e, (uint16_t)stride);
                if (rem < 0) {
                    rr_copy_long(&dst, &src);
                    rr_andw(dst - 4, edge_mask);                /* mask high word of the long */
                    rr_copy_long(&dst, &src);
                    rem = rr_wadd((uint16_t)rem, 8);
                    while (rem < 0) {                          /* forward shoulder fill */
                        rr_fill_pair(&dst, fill_lo, fill_hi);
                        rem = rr_wadd((uint16_t)rem, 8);
                    }
                }
            }
            dst_row += stride;                                 /* both arms advance exactly one row */
            if (!rr_dbf(&remaining)) break;
            continue;
        }

        /* ---- far tail: wider blit ---- */
        if (col < 0) {                                          /* road off-screen: counted fill */
            int16_t rem = rr_wadd((uint16_t)col, 8);
            uint32_t cells = (rem < 0) ? 0x13 : 0x12;
            if (rem >= 0) {                                     /* one masked edge cell first */
                src += 8;
                rr_copy_long(&dst, &src);
                rr_andw(dst - 4, edge_mask);
                rr_copy_long(&dst, &src);
            }
            do { rr_fill_pair(&dst, fill_lo, fill_hi); } while (rr_dbf(&cells));
            dst_row += stride;
            if (!rr_dbf(&remaining)) break;
            continue;
        }

        int16_t rem = rr_wsub((uint16_t)col, (uint16_t)stride);
        if (rem < 0) {
            dst += sx16((uint16_t)col);                         /* in-bounds: col < stride */
            rem = rr_wadd((uint16_t)rem, 8);
            if (rem < 0) {                                      /* 4 longs, third masked */
                rr_copy_long(&dst, &src);
                rr_copy_long(&dst, &src);
                rr_copy_long(&dst, &src);
                rr_andw(dst - 4, edge_mask);
                rr_copy_long(&dst, &src);
            } else {                                            /* 2 longs */
                rr_copy_long(&dst, &src);
                rr_copy_long(&dst, &src);
            }
            rem = rr_wadd((uint16_t)rem, 8);
            while (rem < 0) {                                   /* forward shoulder fill */
                rr_fill_pair(&dst, fill_lo, fill_hi);
                rem = rr_wadd((uint16_t)rem, 8);
            }
        }
        dst_row += stride;
        if (!rr_dbf(&remaining)) break;
    }
    r->param = param; r->width = width; r->edge = edge; r->dst = dst_row;
}


/* =====================================================================================
 * Band C-near. The edge mask is read unconditionally and masks a FULL long on the split edge cell.
 * Two tails feed the row: a fast edge-split tail ([edge cell | left-shoulder fill]) and a merge tail
 * (a narrow [texture | one-cell fill | texture] blit around the column).
 * ===================================================================================== */
static inline __attribute__((always_inline)) void rr_band_C_near(rr_regs *r, uint32_t rows_m1) {
    Framebuffer *fb = r->fb;
    const int16_t stride = r->stride;
    uint32_t remaining = rows_m1;

    for (;;) {
        const uint8_t *src = r->tex;
        uint8_t *dst = fb->px + r->dst;

        uint32_t ctrl = be32(r->width); r->width += 4;
        uint16_t half_width = (uint16_t)(ctrl + be16(r->param)); r->param += 2;
        ctrl = (ctrl & 0xffff0000u) | half_width;
        src += sx16((uint16_t)((ctrl & 0xf) << 4));           /* fine-x sub-column */
        int16_t edge_seed = (int16_t)be16(r->param); r->param += 2;

        Plane4 edge_mask = be32(src + RR_MASK_OFF_LO);         /* unconditional (band C) */
        Plane4 fill_lo = 0xffffffffu, fill_hi = 0x0000ffffu;
        if (ctrl & RR_F_PLANE_HI) fill_hi = 0xffff0000u;

        int16_t col = (int16_t)((uint16_t)((int16_t)half_width >> 1) & RR_D7_WORD_MASK);

        /* ---- source-strip dispatch: also decides which tail paints the row ---- */
        int fast_split = 0, do_src_select = 0;
        if (!(ctrl & RR_F_SPLIT_C)) {                          /* no-split: edge-relative strip */
            src += sx16((uint16_t)edge_seed) + sx16(be16(r->edge)); r->edge += 2;
            do_src_select = 1;
        } else {
            r->edge += 2;
            if (ctrl & RR_F_WIDE) {                            /* wide/solid-centre strip */
                fill_hi = 0; src += RR_SRC_3E00;
                if (ctrl & RR_F_SRC_400) {
                    src += RR_SRC_0400;
                    if (!(ctrl & RR_F_SRC_100)) { src += RR_SRC_0100; fill_lo = 0; }
                } else if (!(ctrl & RR_F_SRC_100)) {
                    src += RR_SRC_0100; fill_lo = 0x0000ffffu;
                }
            } else if (ctrl & RR_F_SKIP_D) {
                fast_split = 1;
            } else {
                do_src_select = 1;
            }
        }
        if (do_src_select) {                                   /* plane-hi / const strip */
            if (ctrl & RR_F_PLANE_HI) src += RR_SRC_5800;
            else if ((ctrl & RR_F_SRC_CONST) && (int32_t)ctrl >= 0) src = r->edge_const + RR_CONST_5BAA;
        }

        if (fast_split) {
            fill_hi = 0;
            if (col >= 0) {
                src += sx16((uint16_t)edge_seed);
                dst += sx16((uint16_t)col);
                int full_row;
                if (ctrl & RR_F_PLANE_HI) {
                    fill_lo = 0; src += RR_SRC_A800;
                    if (be16(r->edge - 2) != 0) src += RR_SRC_0A00;
                    full_row = rr_wsub((uint16_t)col, (uint16_t)stride) >= 0;
                    if (!full_row) { rr_copy_long(&dst, &src); rr_copy_long(&dst, &src); }
                } else {
                    src += sx16(be16(r->edge - 2));
                    full_row = rr_wsub((uint16_t)col, (uint16_t)stride) >= 0;
                    if (!full_row) { rr_copy_long(&dst, &src);
                                     rr_copy_long_masked(&dst, &src, edge_mask); }
                }
                if (full_row) {
                    rr_fill_row(fb->px + r->dst, fill_lo, fill_hi);
                    r->dst += stride;
                    if (!rr_dbf(&remaining)) break;
                    continue;
                }
                /* left shoulder: (col/8) whole cells back from the row start */
                int16_t shoulder_cells = (int16_t)(((uint16_t)col >> 3) - 1);
                if (shoulder_cells >= 0) {
                    uint8_t *sh = fb->px + r->dst; uint32_t cnt = (uint16_t)shoulder_cells;
                    do { rr_fill_pair(&sh, fill_lo, fill_hi); } while (rr_dbf(&cnt));
                }
            }
            /* col < 0 draws nothing (road off the left edge) */
            r->dst += stride; if (!rr_dbf(&remaining)) break;
            continue;
        }

        /* ---- merge tail: narrow blit around the column ---- */
        int16_t left = rr_wsub((uint16_t)col, 8);              /* col - 8 */
        if (left < 0) {
            if (col >= 0) { rr_copy_long(&dst, &src); rr_copy_long(&dst, &src); }
        } else {
            dst += sx16((uint16_t)left);
            int16_t rem = rr_wsub((uint16_t)left, (uint16_t)stride);
            if (rem < 0) {
                rr_fill_pair(&dst, fill_lo, fill_hi);
                if (rr_wadd((uint16_t)rem, 8) < 0) {           /* still room: two texture cells */
                    rr_copy_long(&dst, &src);
                    rr_copy_long(&dst, &src);
                }
            }
        }
        r->dst += stride; if (!rr_dbf(&remaining)) break;
    }
}


/* =====================================================================================
 * Band C-far. Preamble + src dispatch match C-near, but the fast edge-split path selects the source
 * strip first and consumes one extra param word, and the merge tail is bidirectional (forward
 * texture longs when the road grows rightward, a BACKWARD shoulder fill when it recedes).
 * ===================================================================================== */
static inline __attribute__((always_inline)) void rr_band_C_far(rr_regs *r, uint32_t rows_m1) {
    Framebuffer *fb = r->fb;
    const int16_t stride = r->stride;
    uint32_t remaining = rows_m1;

    for (;;) {
        const uint8_t *src = r->tex;
        uint8_t *dst = fb->px + r->dst;

        uint32_t ctrl = be32(r->width); r->width += 4;
        uint16_t half_width = (uint16_t)(ctrl + be16(r->param)); r->param += 2;
        ctrl = (ctrl & 0xffff0000u) | half_width;
        src += sx16((uint16_t)((ctrl & 0xf) << 4));           /* fine-x sub-column */
        int16_t edge_seed = (int16_t)be16(r->param); r->param += 2;

        Plane4 edge_mask = be32(src + RR_MASK_OFF_LO);         /* unconditional (band C) */
        Plane4 fill_lo = 0xffffffffu, fill_hi = 0x0000ffffu;
        if (ctrl & RR_F_PLANE_HI) fill_hi = 0xffff0000u;

        /* ---- fast edge-split path (its own tail; consumes an extra param word) ---- */
        if ((ctrl & RR_F_SPLIT_C) && !(ctrl & RR_F_WIDE) && (ctrl & RR_F_SKIP_D)) {
            r->edge += 2;
            src += sx16((uint16_t)edge_seed);
            r->param += 2;                                     /* far-only extra param word */
            int16_t col;
            fill_hi = 0;
            if (ctrl & RR_F_PLANE_HI) {
                fill_lo = 0; src += RR_SRC_A800;
                if (be16(r->edge - 2) != 0) src += RR_SRC_0A00;
            } else {
                src += sx16(be16(r->edge - 2));
            }
            col = (int16_t)((uint16_t)((int16_t)half_width >> 1) & r->d7);
            if (col < 0) {                                     /* road near/off the left edge */
                int16_t e = rr_wadd((uint16_t)col, 8);
                if (e >= 0) { src += 8; rr_copy_long(&dst, &src); rr_copy_long(&dst, &src); }
            } else {
                int16_t rem = rr_wsub((uint16_t)col, (uint16_t)stride);
                if (rem >= 0) {
                    rr_fill_row(fb->px + r->dst, fill_lo, fill_hi);
                    r->dst += stride;
                    if (!rr_dbf(&remaining)) break;
                    continue;
                }
                dst += sx16((uint16_t)col);                    /* in-bounds: col < stride */
                int16_t e = rr_wadd((uint16_t)rem, 8);
                if (e < 0) {                                   /* 4 longs (masked 2nd on non-hi) */
                    rr_copy_long(&dst, &src);
                    if (!(ctrl & RR_F_PLANE_HI)) rr_copy_long_masked(&dst, &src, edge_mask);
                    else                         rr_copy_long(&dst, &src);
                    rr_copy_long(&dst, &src);
                    rr_copy_long(&dst, &src);
                } else {                                       /* 2 longs (masked 2nd on non-hi) */
                    rr_copy_long(&dst, &src);
                    if (!(ctrl & RR_F_PLANE_HI)) rr_copy_long_masked(&dst, &src, edge_mask);
                    else                         rr_copy_long(&dst, &src);
                }
                /* left shoulder: (col>>3 - 1) forward pairs from the row start */
                int16_t cells = (int16_t)(((uint16_t)col >> 3) - 1);
                if (cells >= 0) {
                    uint8_t *sh = fb->px + r->dst; uint32_t cnt = (uint16_t)cells;
                    do { rr_fill_pair(&sh, fill_lo, fill_hi); } while (rr_dbf(&cnt));
                }
            }
            r->dst += stride;
            if (!rr_dbf(&remaining)) break;
            continue;
        }

        /* ---- shared src dispatch (feeds the merge tail) ---- */
        if (!(ctrl & RR_F_SPLIT_C)) {                          /* no-split: edge-relative strip */
            src += sx16((uint16_t)edge_seed) + sx16(be16(r->edge)); r->edge += 2;
            if (ctrl & RR_F_PLANE_HI) src += RR_SRC_5800;
            else if ((ctrl & RR_F_SRC_CONST) && (int32_t)ctrl >= 0) src = r->edge_const + RR_CONST_5BAA;
        } else if (ctrl & RR_F_WIDE) {                         /* WIDE strip */
            r->edge += 2;
            fill_hi = 0; src += RR_SRC_3E00;
            if (ctrl & RR_F_SRC_400) {
                src += RR_SRC_0400;
                if (!(ctrl & RR_F_SRC_100)) { src += RR_SRC_0100; fill_lo = 0; }
            } else if (!(ctrl & RR_F_SRC_100)) {
                src += RR_SRC_0100; fill_lo = 0x0000ffffu;
            }
        } else {                                               /* SPLIT_C, !WIDE, !SKIP_D: plane-hi/const */
            r->edge += 2;
            if (ctrl & RR_F_PLANE_HI) src += RR_SRC_5800;
            else if ((ctrl & RR_F_SRC_CONST) && (int32_t)ctrl >= 0) src = r->edge_const + RR_CONST_5BAA;
        }

        /* ---- merge tail (reads one more param word): a bidirectional blit ---- */
        int16_t count = (int16_t)be16(r->param); r->param += 2;    /* shoulder-fill count */
        int16_t col = (int16_t)((uint16_t)((int16_t)half_width >> 1) & r->d7);
        if (col < 0) {                                         /* road off the left edge */
            if (rr_wadd((uint16_t)col, 8) >= 0) {
                src += 8; rr_copy_long(&dst, &src); rr_copy_long(&dst, &src);
            }
            r->dst += stride;
            if (!rr_dbf(&remaining)) break;
            continue;
        }

        /* place at the column; width tracks the reverse-fill extent. */
        dst += sx16((uint16_t)col);
        int16_t width = col;
        int16_t col_rem = rr_wsub((uint16_t)col, (uint16_t)stride);   /* col - stride */
        if (col_rem >= 0 && rr_wsub((uint16_t)col_rem, 8) >= 0) {
            /* road spans the whole row: advance dst, reverse-fill (count - (rem-8)/8) pairs. */
            col_rem = rr_wsub((uint16_t)col_rem, 8);
            r->dst += stride;
            int16_t n = rr_wsub((uint16_t)count, (uint16_t)((uint16_t)col_rem >> 3));
            if (n >= 0) {
                uint8_t *shoulder = fb->px + r->dst; uint32_t cnt = (uint16_t)n;
                do { rr_fill_pair_rev(&shoulder, fill_lo, fill_hi); } while (rr_dbf(&cnt));
            }
            if (!rr_dbf(&remaining)) break;
            continue;
        }

        /* Otherwise either col-stride < 0 (clear the running count, copy 2 longs first), or
         * stride <= col < stride+8 (straight in). */
        if (col_rem < 0) {
            col_rem = 0;
            rr_copy_long(&dst, &src); rr_copy_long(&dst, &src);
        } else {
            col_rem = rr_wsub((uint16_t)col_rem, 8);
        }
        col_rem = rr_wadd((uint16_t)col_rem, 8);
        rr_copy_long(&dst, &src); rr_copy_long(&dst, &src);
        col_rem = rr_wadd((uint16_t)col_rem, 8);
        dst -= sx16((uint16_t)col_rem);                        /* suba.w d0,a0 */

        /* reverse-fill while the width stays >= 0 and the count hasn't underflowed. */
        uint32_t cnt = (uint16_t)count;
        for (;;) {
            width = rr_wsub((uint16_t)width, 8);
            if (width < 0) break;
            rr_fill_pair_rev(&dst, fill_lo, fill_hi);
            if (!rr_dbf(&cnt)) break;
        }
        r->dst += stride;
        if (!rr_dbf(&remaining)) break;
    }
}


/* =====================================================================================
 * Band D — near then far copy. Each scanline paints
 *     [ left-shoulder solid fill | antialiased edge cell | copied road texture ]
 * The far copy widens the texture run and additionally handles the road sliding off the left edge.
 *
 * rr_band_D_c is the byte-exact C REFERENCE. It is ALWAYS compiled (as blit.c keeps rm_blit_objshift2),
 * so undefining the asm flag A/Bs the band on every build (RR_BAND_D_FN below just re-points). PERF30
 * road-asm slice 1 ships a hand-m68k core (src/asm/road_band.S); test/test_asm_road.py pins the two
 * byte-identical under Musashi. `unused`: the shipping asm build reaches band D through rr_band_D_asm and
 * never calls this, but keeping it compiled (measured: no perf effect) is what makes the A/B clean.
 * ===================================================================================== */
static __attribute__((unused)) void rr_band_D_c(rr_regs *r, uint32_t rows_m1, int second) {
    Framebuffer *fb = r->fb;
    const int16_t stride = r->stride;
    /* Localize the band cursors (same aliasing reason as rr_band_B): write back at return. */
    const uint8_t *tex = r->tex, *edge_const = r->edge_const;
    const uint8_t *param = r->param, *width = r->width, *edge = r->edge;
    Offset dst_row = r->dst;
    uint32_t remaining = rows_m1;

    for (;;) {
        const uint8_t *src = tex;

        uint32_t ctrl = be32(width); width += 4;
        uint16_t half_width = (uint16_t)(ctrl + be16(param)); param += 2;
        ctrl = (ctrl & 0xffff0000u) | half_width;
        src += sx16((uint16_t)((ctrl & 0xf) << 4));           /* fine-x sub-column */
        int16_t edge_seed = (int16_t)be16(param); param += 2;

        Plane4 fill_lo = 0xffff0000u, fill_hi = 0x0000ffffu, edge_mask = 0xffffffffu;
        if (ctrl & RR_F_MASK_A2) { fill_lo = 0; edge_mask = be32(src + RR_MASK_OFF_LO); }

        int16_t edge_off = (int16_t)be16(edge);                /* used only by the no-split strip */
        edge += 2;                                             /* edge cursor advances every row */

        /* ---- source-strip dispatch ---- */
        int skip_row = 0;
        if (!(ctrl & RR_F_SPLIT_D)) {                          /* straight strip (no edge split) */
            src += sx16((uint16_t)edge_seed) + sx16((uint16_t)edge_off);
            if (ctrl & RR_F_PLANE_HI) src += RR_SRC_5800;
        } else if ((ctrl & RR_F_SKIP_D) && (int32_t)ctrl < 0) {
            skip_row = 1;                                      /* flagged blank scanline */
        } else if (ctrl & RR_F_WIDE) {                         /* wide/solid-centre strip */
            fill_lo = 0; fill_hi = 0; src += RR_SRC_3500;
            if (ctrl & RR_F_SRC_400) {
                src += RR_SRC_0400;
                if (!(ctrl & RR_F_SRC_100)) src = edge_const + RR_CONST_5B7A;
            } else {
                fill_lo = rr_notw(fill_lo);                    /* 0 -> 0x0000ffff */
                if (!(ctrl & RR_F_SRC_100)) src = edge_const + RR_CONST_5B9A;
            }
        } else if (ctrl & RR_F_PLANE_HI) {                     /* edge-split strip, high plane */
            src += RR_SRC_5800;
        }

        if (!skip_row) {
            int16_t col = (int16_t)((uint16_t)((int16_t)half_width >> 1) & RR_D7_WORD_MASK);
            uint8_t *row_start = fb->px + dst_row;
            uint8_t *dst = row_start;

            if (col >= 0) {
                if (rr_wsub((uint16_t)col, (uint16_t)stride) >= 0) {
                    rr_fill_row(row_start, fill_lo, fill_hi);           /* road fills the row */
                } else {
                    dst += sx16((uint16_t)col);
                    rr_draw_edge_cell(&dst, &src, edge_mask);
                    /* far copy widens the texture run by two more columns when there is room. */
                    if (second && rr_wadd((uint16_t)rr_wsub((uint16_t)col, (uint16_t)stride), 8) < 0) {
                        rr_copy_long(&dst, &src);
                        rr_copy_long(&dst, &src);
                    }
                    rr_fill_shoulder(row_start, col, fill_lo, fill_hi);
                }
            } else if (second && rr_wadd((uint16_t)col, 8) >= 0) {
                /* far copy, road one cell off the left edge: draw two texture longs at row start. */
                src += 8;
                rr_copy_long(&dst, &src);
                rr_copy_long(&dst, &src);
            }
            /* near copy with col < 0: nothing drawn (road entirely off the left edge). */
        }

        dst_row += stride;
        if (!rr_dbf(&remaining)) break;
    }
    r->param = param; r->width = width; r->edge = edge; r->dst = dst_row;
}


/* road_band.S is ALWAYS assembled (like objshift2.S); only the RR_BAND_?_FN dispatch keys off each
 * per-core flag, so undefining one genuinely A/Bs that band. The externs are declared unconditionally —
 * on the host build the asm object is not linked, but rm_render_road references them only when the flag is
 * set (and the differential entries only under RM_ROAD_DIFF), so no unresolved symbol is emitted. */
void rr_band_B_asm(rr_regs *r, uint32_t rows_m1, int second);   /* src/asm/road_band.S (slice 2) */
void rr_band_D_asm(rr_regs *r, uint32_t rows_m1, int second);   /* src/asm/road_band.S (slice 1) */
#ifdef RM_ASM_RR_BAND_B
#define RR_BAND_B_FN rr_band_B_asm
#else
#define RR_BAND_B_FN rr_band_B_c         /* host / no-asm build: band B IS the C reference */
#endif
#ifdef RM_ASM_RR_BAND_D
#define RR_BAND_D_FN rr_band_D_asm
#else
#define RR_BAND_D_FN rr_band_D_c         /* host / no-asm build: band D IS the C reference */
#endif

/* The seven-band pipeline. `param` streams monotonically across all bands; `width`/`edge`/d7 reset at
 * each group step. Band A runs alone; B/C/D each run a near then a far copy per group. A local
 * `rr_regs r = {...}` (not a helper taking rr_regs*) lets GCC keep the cursor fields in registers.
 *
 * PERF30 road-asm cost note (slices 1-2): the FIRST external asm band inside this otherwise-inlined C road
 * makes GCC de-inline band A into a cold `.constprop` clone (+17k cyc) — a ONE-TIME cost, not per band.
 * always_inline on A/C (above) keeps them resident. So slice 1 (band D alone) was ~break-even, but slice 2
 * (band B, RR_BAND_B_FN) adds its own saving with no further de-inline tax, taking the composite below the
 * pre-asm C floor. See PERF30.md "Road-asm slice 2". */
void rm_render_road(const RoadInput *in, Framebuffer *fb) {
    rr_regs r = {
        .fb         = fb,
        .dst        = RR_DST_ROAD_OFF,
        .tex        = in->tex,
        .param      = in->param,
        .width      = in->width_tbl,
        .edge       = in->edge_tbl,
        .edge_const = in->edge_const,
        .width_base = in->width_tbl,
        .stride     = RR_ROW_STRIDE_D2,
        .d7         = 0,                 /* band A never masks the width with d7 (scratch there) */
    };

    rr_band_A(&r);
    rr_group_step(&r);
    /* 0xfff8 from the first group step onward — so bands B/C/D always see d7 == RR_D7_WORD_MASK, the
     * invariant road_band.S's CONTRACT relies on (band B's asm + C both read r->d7; band D's asm reads it
     * while its C hardcodes the same value). */
    r.d7 = RR_D7_WORD_MASK;

    RR_BAND_B_FN(&r, RR_ROWS_B_NEAR, 0);/* near copy */
    RR_BAND_B_FN(&r, RR_ROWS_B_FAR, 1); /* far copy (distinct wider blit tail) */
    rr_group_step(&r);
    rr_band_C_near(&r, RR_ROWS_C_NEAR);
    rr_band_C_far(&r, RR_ROWS_C_FAR);   /* far copy (distinct fast-split + merge tail) */
    rr_group_step(&r);
    RR_BAND_D_FN(&r, RR_ROWS_D_NEAR, 0);/* near copy */
    RR_BAND_D_FN(&r, RR_ROWS_D_FAR, 1); /* far copy */
}

#ifdef RM_ROAD_DIFF
/* Bench-only differential entries (bench_main.c -> test/test_asm_road.py). The isolation BASELINE is
 * _allasm (both bands on their shipping cores); each band's _c entry swaps just that band to the C
 * reference, so comparing _c against _allasm isolates that band's output (C vs asm). There is only ONE
 * all-asm entry — running band D's and band B's asm variants would be the identical config and re-measure
 * the same ~340k-cyc code. The _noD/_noB no-op entries are the per-band positive controls. Compiled only
 * under -DRM_ROAD_DIFF (the bench); these out-of-line entries pass the bands by pointer and do not share
 * rm_render_road's body, so they cannot perturb its A/C inlining. */
typedef void (*rr_band_fn)(rr_regs *r, uint32_t rows_m1, int second);
static void rr_band_noop(rr_regs *r, uint32_t rows_m1, int second) { (void)r; (void)rows_m1; (void)second; }

static void render_road_pipeline(const RoadInput *in, Framebuffer *fb, rr_band_fn band_B, rr_band_fn band_D) {
    rr_regs r = {
        .fb = fb, .dst = RR_DST_ROAD_OFF, .tex = in->tex, .param = in->param,
        .width = in->width_tbl, .edge = in->edge_tbl, .edge_const = in->edge_const,
        .width_base = in->width_tbl, .stride = RR_ROW_STRIDE_D2, .d7 = 0,
    };
    rr_band_A(&r);
    rr_group_step(&r);
    r.d7 = RR_D7_WORD_MASK;
    band_B(&r, RR_ROWS_B_NEAR, 0);
    band_B(&r, RR_ROWS_B_FAR, 1);
    rr_group_step(&r);
    rr_band_C_near(&r, RR_ROWS_C_NEAR);
    rr_band_C_far(&r, RR_ROWS_C_FAR);
    rr_group_step(&r);
    band_D(&r, RR_ROWS_D_NEAR, 0);
    band_D(&r, RR_ROWS_D_FAR, 1);
}

/* The all-asm isolation baseline (both bands on their shipping cores) + each band swapped to its C ref /
 * a no-op (the other band stays shipping). */
void rm_render_road_allasm(const RoadInput *in, Framebuffer *fb)    { render_road_pipeline(in, fb, RR_BAND_B_FN, RR_BAND_D_FN); }
void rm_render_road_bandD_c(const RoadInput *in, Framebuffer *fb)   { render_road_pipeline(in, fb, RR_BAND_B_FN, rr_band_D_c); }
void rm_render_road_bandD_noD(const RoadInput *in, Framebuffer *fb) { render_road_pipeline(in, fb, RR_BAND_B_FN, rr_band_noop); }
void rm_render_road_bandB_c(const RoadInput *in, Framebuffer *fb)   { render_road_pipeline(in, fb, rr_band_B_c, RR_BAND_D_FN); }
void rm_render_road_bandB_noB(const RoadInput *in, Framebuffer *fb) { render_road_pipeline(in, fb, rr_band_noop, RR_BAND_D_FN); }
#endif
