/* blit.c — remaster of the two fine-x (sub-pixel) 4-plane masked-sprite blit engines that the
 * roadside-object dispatcher feeds: blit_objshift (recreate's @0x14680, colour-indexed) and
 * blit_objshift2 (@0x13ed6, plain masked OR). Both shift each 16-pixel source column to an arbitrary
 * pixel x so a sprite straddles two 16-pixel destination columns (col0 = dst+aligned_col, col1 =
 * col0+8), walking one scanline up per row.
 *
 * These are the leaf writers under draw_object_list. Unlike recreate's single flat image, the
 * destination (framebuffer) and the source (sprite arena) are separate buffers here: `dst`/`dst_off`
 * name the target, `src`/`src_off` the sprite pixels. That is the only structural change — the shift/
 * mask/ladder arithmetic is transcribed 1:1 (16-bit register wraps mirrored with explicit
 * int16/uint16), so the output is byte-identical (see test/test_blit.py).
 */
#include "game.h"
#include "screen.h"
#include "st.h"

/* ---- shared fine-x geometry ---- */
#define OBJSH_NIBBLE     0xf     /* fine-x / colour-index low nibble */
#define OBJSH_SUBPX_BITS 16      /* left-shift count = 16 - fine_x */
#define OBJSH_CELL_BYTES 8       /* one 16-pixel 4-plane cell / column step */
#define OBJSH_PLANES     4
#define COL_ALIGN        0xfff8  /* aligned_col = ((int16)x >> 1) & this (8-byte column) */

static uint16_t objsh_aligned_col(uint16_t x) {
    return (uint16_t)((int16_t)x >> 1) & (uint16_t)COL_ALIGN;
}

/* Rotate a 32-bit value left (68k rol.l); count is 1..16 here. */
static uint32_t rotl32(uint32_t v, unsigned count) {
    count &= 31;
    return count ? ((v << count) | (v >> (32 - count))) : v;
}

/* Masked OR-in of one plane word into a destination column: keep the background where mask is set,
 * drop in the shifted pixels (68k `and.w mask,(ptr)` + `or.w pix,(ptr)`). */
static void plane_write(uint8_t *dst, Offset ptr, uint16_t mask, uint16_t pix) {
    wr16(dst + ptr, (uint16_t)((be16(dst + ptr) & mask) | pix));
}

/* ============================================================================================
 * blit_objshift @0x14680 — colour-indexed fine-x masked sprite blitter.
 *
 * The transparency SHOW mask is ~(A|B|C) & D from four source plane words, with a load-bearing
 * 0xFFFF high word (68k moveq #$ff seed) that rotates into the straddled column. Pixels are gated by
 * a per-plane colour fill (from color_pairs[colour]). Two width families: base_cells 1 (0x14680
 * "0x98") / 2 (0x144ac "0x90").
 * ============================================================================================ */
#define OBJSH_RIGHT_BOUND 0x98    /* absolute right screen bound (aligned_col) */
#define OBJSH_ROW_REWIND  0xa8    /* base per-row dst rewind (Δ = this + 8*(cells-1)) */
#define OBJSH_MASK_HI     0xffff0000u

static uint32_t objsh_build_mask(const uint8_t *src, uint32_t p) {
    uint16_t a = be16(src + p), b = be16(src + p + 2), c = be16(src + p + 4), d = be16(src + p + 6);
    return OBJSH_MASK_HI | (uint16_t)(~(a | b | c) & d);
}

/* The colour fill half consumed per plane: plane0 = fill_lo hi, 1 = fill_lo lo, 2 = fill_hi hi,
 * 3 = fill_hi lo (the asm's swap-toggled order). */
static uint16_t objsh_fill_half(Plane4 fill_lo, Plane4 fill_hi, int plane) {
    Plane4 reg = (plane < 2) ? fill_lo : fill_hi;
    return (uint16_t)((plane & 1) ? (reg & 0xffff) : (reg >> OBJSH_SUBPX_BITS));
}

/* The three loop cursors carried by value between cells and rows: the two destination columns and the
 * source pointer. Passing this by value (not by pointer) keeps col0/col1/sp register-pinned once the
 * static cell helpers inline — the by-pointer shape address-took them and forced per-cell memory RMW
 * plus movel sp@,sp@ spill shuffling (PERF30 A1). */
typedef struct { Offset col0, col1; uint32_t sp; } ObjshCursor;

/* STRADDLE cell: 32-bit left shift straddles both columns; high half -> col0, low half -> col1. */
static ObjshCursor objsh_straddle_cell(uint8_t *dst, const uint8_t *src, ObjshCursor cur,
                                       unsigned shl, Plane4 fill_lo, Plane4 fill_hi) {
    uint32_t mask32 = rotl32(objsh_build_mask(src, cur.sp), shl);
    uint16_t mask_hi = (uint16_t)(mask32 >> OBJSH_SUBPX_BITS);   /* col0 */
    uint16_t mask_lo = (uint16_t)mask32;                         /* col1 */
    for (int plane = 0; plane < OBJSH_PLANES; plane++) {
        uint32_t pix32 = (uint32_t)be16(src + cur.sp) << shl;
        cur.sp += 2;
        uint16_t fill = objsh_fill_half(fill_lo, fill_hi, plane);
        uint16_t pix_lo = (uint16_t)((pix32 & 0xffff) & fill);
        uint16_t pix_hi = (uint16_t)((pix32 >> OBJSH_SUBPX_BITS) & fill);
        if (plane == OBJSH_PLANES - 1) { pix_lo &= (uint16_t)~mask_lo; pix_hi &= (uint16_t)~mask_hi; }
        plane_write(dst, cur.col1, mask_lo, pix_lo);   /* col1 first */
        plane_write(dst, cur.col0, mask_hi, pix_hi);
        cur.col0 += 2; cur.col1 += 2;
    }
    return cur;
}

/* EDGE cell (single on-screen column): mask built + shifted as the full 32-bit register (rol.l shl
 * for LEFT, lsr.l shr for RIGHT); low word gates the column. Pixels shift as words. RIGHT walks col0,
 * LEFT walks col1. always_inline: it has two call sites, so GCC's size heuristic leaves it a real
 * call otherwise — which re-spills the cursor across the call and defeats the register-pinning. */
static inline __attribute__((always_inline))
ObjshCursor objsh_edge_cell(uint8_t *dst, const uint8_t *src, ObjshCursor cur,
                            unsigned shift, int is_right, Plane4 fill_lo, Plane4 fill_hi) {
    uint32_t m32 = objsh_build_mask(src, cur.sp);
    uint16_t mask = (uint16_t)(is_right ? (m32 >> shift) : rotl32(m32, shift));
    Offset ptr = is_right ? cur.col0 : cur.col1;
    for (int plane = 0; plane < OBJSH_PLANES; plane++) {
        uint16_t word = be16(src + cur.sp);
        cur.sp += 2;
        uint16_t pix = is_right ? (uint16_t)(word >> shift) : (uint16_t)((uint32_t)word << shift);
        pix = (uint16_t)(pix & objsh_fill_half(fill_lo, fill_hi, plane));
        if (plane == OBJSH_PLANES - 1) pix &= (uint16_t)~mask;
        plane_write(dst, ptr, mask, pix);
        ptr += 2;
    }
    if (is_right) cur.col0 = ptr; else cur.col1 = ptr;
    return cur;
}

enum objsh_family { OBJSH_CLIP, OBJSH_BASE, OBJSH_LEFT, OBJSH_RIGHT };

static ObjshCursor objsh_row(uint8_t *dst, const uint8_t *src, ObjshCursor cur,
                             enum objsh_family fam, int straddle, unsigned shl, unsigned shr,
                             Plane4 fill_lo, Plane4 fill_hi) {
    if (fam == OBJSH_LEFT) {
        cur = objsh_edge_cell(dst, src, cur, shl, /*is_right=*/0, fill_lo, fill_hi);
        cur.col0 += OBJSH_CELL_BYTES;
    }
    for (int i = 0; i < straddle; i++)
        cur = objsh_straddle_cell(dst, src, cur, shl, fill_lo, fill_hi);
    if (fam == OBJSH_RIGHT) {
        cur = objsh_edge_cell(dst, src, cur, shr, /*is_right=*/1, fill_lo, fill_hi);
        cur.col1 += OBJSH_CELL_BYTES;
    }
    return cur;
}

/* Colour-indexed fine-x blit. `stride` is the per-row src-stride word (recreate's blit_mode: 8 or
 * 0xa8). base_cells 1 / 2 select the width family. */
void rm_blit_objshift(uint8_t *dst, Offset dst_off, const uint8_t *src, uint32_t src_off,
                      uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                      const uint8_t *color_pairs, int base_cells) {
    unsigned fine_x = (unsigned)(x & OBJSH_NIBBLE);
    unsigned shl = OBJSH_SUBPX_BITS - fine_x;
    unsigned shr = fine_x;

    uint16_t col_off = (uint16_t)((color & OBJSH_NIBBLE) << 3);
    Plane4 fill_lo = be32(color_pairs + col_off);        /* planes 0,1 */
    Plane4 fill_hi = be32(color_pairs + col_off + 4);    /* planes 2,3 */

    int16_t A = (int16_t)objsh_aligned_col(x);
    int16_t base_ceiling = (int16_t)(OBJSH_RIGHT_BOUND - OBJSH_CELL_BYTES * (base_cells - 1));

    enum objsh_family fam;
    int straddle, skips = 0;
    if (A < 0) {
        int k = (int)(-A) / OBJSH_CELL_BYTES;
        if (k > base_cells) return;                       /* off the left edge */
        fam = OBJSH_LEFT; straddle = base_cells - k; skips = k - 1;
    } else if ((int16_t)(A - base_ceiling) >= 0) {
        int s = (OBJSH_RIGHT_BOUND - A) / OBJSH_CELL_BYTES;
        if (s < 0) return;                                /* off the right edge */
        fam = OBJSH_RIGHT; straddle = s;
    } else {
        fam = OBJSH_BASE; straddle = base_cells;
    }

    int total_cells = straddle + (fam == OBJSH_BASE ? 0 : 1);
    uint16_t rewind = (uint16_t)(OBJSH_ROW_REWIND + OBJSH_CELL_BYTES * (total_cells - 1));
    uint16_t src_extra = (uint16_t)(OBJSH_CELL_BYTES * (total_cells - 1));
    int rows = (int16_t)rows_m1 + 1;

    ObjshCursor cur;
    cur.sp = src_off + (uint32_t)(OBJSH_CELL_BYTES * skips);
    cur.col0 = (dst_off + sx16((uint16_t)A)) + (uint32_t)(OBJSH_CELL_BYTES * skips);
    cur.col1 = cur.col0 + OBJSH_CELL_BYTES;
    for (int row = 0; row < rows; row++) {
        cur = objsh_row(dst, src, cur, fam, straddle, shl, shr, fill_lo, fill_hi);
        cur.col0 = (Offset)(cur.col0 - sx16(rewind));
        cur.col1 = (Offset)(cur.col1 - sx16(rewind));
        cur.sp = (uint32_t)(cur.sp - sx16((uint16_t)stride));
        cur.sp = (uint32_t)(cur.sp - sx16(src_extra));
    }
}

/* ============================================================================================
 * blit_objshift2 @0x13ed6 — plain (no colour) fine-x masked sprite blitter. SHOW mask is ~(w0|w1)
 * from two source words; pixels copied plain-shifted and OR'd. Three width families
 * (width_idx 0/1/2 = base ceiling 0x88/0x90/0x98).
 * ============================================================================================ */
#define OBJSH2_RIGHT_BOUND 0x88
#define OBJSH2_LADDER_STEP 8
#define OBJSH2_MASK_INIT   0xffffffffu
#define OBJSH2_BASE_STRADDLE 3
#define OBJSH2_REWIND3_DST 0xb8
#define OBJSH2_REWIND3_SRC 0x5c
#define OBJSH2_REWIND2_DST 0xb0
#define OBJSH2_REWIND2_SRC 0x58
#define OBJSH2_REWIND1_DST 0xa8
#define OBJSH2_REWIND1_SRC 0x54

/* objshift2 carries the same {col0, col1, sp} cursor triple but is NOT value-passed: unlike objshift
 * its baseline has no mem-to-mem cursor shuffle (the cell body walks col0/col1 in address registers via
 * wr32(dst + *col0)), and its cost is arithmetic/RMW-bound. Forcing the cursors register-resident across
 * the row loop only steals the address registers the RMW cell needs and spills the loop counter instead
 * (measured +1.98 ms, PERF30 A1). The by-pointer shape lets GCC free the cursors during the cell body,
 * which is the better tradeoff here — so it stays. */
static void objsh2_straddle_cell(uint8_t *dst, const uint8_t *src, Offset *col0, Offset *col1,
                                 uint32_t *sp, unsigned shl) {
    uint16_t w0 = be16(src + *sp);
    uint16_t w1 = be16(src + *sp + 2);
    uint32_t mask_col0 = OBJSH2_MASK_INIT;
    mask_col0 = (mask_col0 & 0xffff0000u) | w0;
    mask_col0 = (mask_col0 & 0xffff0000u) | (uint16_t)(mask_col0 | w1);
    mask_col0 = (mask_col0 & 0xffff0000u) | (uint16_t)(~mask_col0);
    mask_col0 = rotl32(mask_col0, shl);
    uint32_t mask_col1 = dup16((uint16_t)mask_col0);
    uint32_t swapped = (mask_col0 >> 16) | (mask_col0 << 16);
    mask_col0 = (mask_col0 & 0xffff0000u) | (uint16_t)swapped;
    wr32(dst + *col0, be32(dst + *col0) & mask_col0);
    wr32(dst + *col1, be32(dst + *col1) & mask_col1);

    for (int i = 0; i < 2; i++) {
        uint32_t pix = (uint32_t)be16(src + *sp) << shl;
        *sp += 2;
        wr16(dst + *col1, (uint16_t)(be16(dst + *col1) | (uint16_t)pix));
        wr16(dst + *col0, (uint16_t)(be16(dst + *col0) | (uint16_t)(pix >> 16)));
        *col0 += 2; *col1 += 2;
    }
    wr32(dst + *col0, (be32(dst + *col0) & mask_col0) | ~mask_col0);
    *col0 += 4;
    wr32(dst + *col1, (be32(dst + *col1) & mask_col1) | ~mask_col1);
    *col1 += 4;
}

static void objsh2_left_edge_cell(uint8_t *dst, const uint8_t *src, Offset *col0, Offset *col1,
                                  uint32_t *sp, unsigned shl) {
    uint32_t both = be32(src + *sp);
    uint16_t lo = (uint16_t)((uint16_t)both | be16(src + *sp));
    *sp += 2;
    uint16_t mask = (uint16_t)(~(uint16_t)(lo << shl));
    uint32_t mask_col1 = dup16(mask);
    wr32(dst + *col1, be32(dst + *col1) & mask_col1);
    uint16_t w0 = (uint16_t)(both >> 16);
    wr16(dst + *col1, (uint16_t)(be16(dst + *col1) | (uint16_t)(w0 << shl)));
    *col1 += 2;
    uint16_t w1 = be16(src + *sp);
    *sp += 2;
    wr16(dst + *col1, (uint16_t)(be16(dst + *col1) | (uint16_t)(w1 << shl)));
    *col1 += 2;
    wr32(dst + *col1, (be32(dst + *col1) & mask_col1) | ~mask_col1);
    *col1 += 4;
    *col0 += OBJSH_CELL_BYTES;
}

static void objsh2_right_edge_cell(uint8_t *dst, const uint8_t *src, Offset *col0, Offset *col1,
                                   uint32_t *sp, unsigned shr) {
    uint32_t both = be32(src + *sp);
    uint16_t lo = (uint16_t)((uint16_t)both | be16(src + *sp));
    *sp += 2;
    uint16_t mask = (uint16_t)(~(uint16_t)(lo >> shr));
    uint32_t mask_col0 = dup16(mask);
    wr32(dst + *col0, be32(dst + *col0) & mask_col0);
    uint16_t w0 = (uint16_t)(both >> 16);
    wr16(dst + *col0, (uint16_t)(be16(dst + *col0) | (uint16_t)(w0 >> shr)));
    *col0 += 2;
    uint16_t w1 = be16(src + *sp);
    *sp += 2;
    wr16(dst + *col0, (uint16_t)(be16(dst + *col0) | (uint16_t)(w1 >> shr)));
    *col0 += 2;
    wr32(dst + *col0, (be32(dst + *col0) & mask_col0) | ~mask_col0);
    *col0 += 4;
    *col1 += OBJSH_CELL_BYTES;
}

enum objsh2_edge { OBJSH2_EDGE_NONE, OBJSH2_EDGE_LEFT, OBJSH2_EDGE_RIGHT };

static void objsh2_row(uint8_t *dst, const uint8_t *src, Offset *col0, Offset *col1, uint32_t *sp,
                       enum objsh2_edge edge, int straddle, unsigned shl, unsigned shr) {
    if (edge == OBJSH2_EDGE_LEFT) objsh2_left_edge_cell(dst, src, col0, col1, sp, shl);
    for (int i = 0; i < straddle; i++) objsh2_straddle_cell(dst, src, col0, col1, sp, shl);
    if (edge == OBJSH2_EDGE_RIGHT) objsh2_right_edge_cell(dst, src, col0, col1, sp, shr);
}

void rm_blit_objshift2(uint8_t *dst, Offset dst_off, const uint8_t *src, uint32_t src_off,
                       uint16_t x, uint16_t rows_m1, int width_idx) {
    unsigned fine_x = (unsigned)(x & OBJSH_NIBBLE);
    unsigned shl = OBJSH_SUBPX_BITS - fine_x;
    unsigned shr = fine_x;

    int16_t col = (int16_t)((int16_t)(uint16_t)x >> 1) & (int16_t)COL_ALIGN;
    int16_t base_ceiling = (int16_t)(OBJSH2_RIGHT_BOUND + OBJSH2_LADDER_STEP * width_idx);
    Offset col0 = (Offset)(dst_off + sx16((uint16_t)col));
    uint32_t sp = src_off;

    enum objsh2_edge edge;
    int straddle;
    uint16_t rewind_dst, rewind_src;

    if (col < 0) {
        int16_t c = col;
        int rung;
        edge = OBJSH2_EDGE_LEFT; straddle = -1;
        for (rung = width_idx; rung <= OBJSH2_BASE_STRADDLE - 1; rung++) {
            c = (int16_t)(c + OBJSH2_LADDER_STEP);
            if (c >= 0) { straddle = (OBJSH2_BASE_STRADDLE - 1) - rung; break; }
            if (rung < OBJSH2_BASE_STRADDLE - 1) { sp += 4; col0 += OBJSH_CELL_BYTES; }
        }
        if (straddle < 0) return;                         /* off the left edge */
    } else if ((int16_t)(col - base_ceiling) >= 0) {
        int16_t c = (int16_t)(col - OBJSH2_RIGHT_BOUND);
        c = (int16_t)(c - OBJSH2_LADDER_STEP);
        if (c < 0) straddle = 2;
        else {
            c = (int16_t)(c - OBJSH2_LADDER_STEP);
            if (c < 0) straddle = 1;
            else {
                c = (int16_t)(c - OBJSH2_LADDER_STEP);
                if (c < 0) straddle = 0;
                else return;                              /* off the right edge */
            }
        }
        edge = OBJSH2_EDGE_RIGHT;
    } else {
        edge = OBJSH2_EDGE_NONE;
        straddle = OBJSH2_BASE_STRADDLE - width_idx;
    }

    int cells = straddle + (edge == OBJSH2_EDGE_NONE ? 0 : 1);
    switch (cells) {
        case 3: rewind_dst = OBJSH2_REWIND3_DST; rewind_src = OBJSH2_REWIND3_SRC; break;
        case 2: rewind_dst = OBJSH2_REWIND2_DST; rewind_src = OBJSH2_REWIND2_SRC; break;
        default: rewind_dst = OBJSH2_REWIND1_DST; rewind_src = OBJSH2_REWIND1_SRC; break;
    }

    Offset col1 = col0 + OBJSH_CELL_BYTES;
    int rows = (int16_t)rows_m1 + 1;
    for (int row = 0; row < rows; row++) {
        objsh2_row(dst, src, &col0, &col1, &sp, edge, straddle, shl, shr);
        col0 = (Offset)(col0 - sx16(rewind_dst));
        col1 = (Offset)(col1 - sx16(rewind_dst));
        sp = (uint32_t)(sp - sx16(rewind_src));
    }
}

/* ============================================================================================
 * objsprite engine @0x131f6 — the third fine-x blitter (the sibling of blit_objshift2). Same three-
 * primitive shell (straddle / left-edge / right-edge) and the same col0/col1 pairing, but its SHOW
 * mask is built from FOUR source words ~(w0|w1|w2)&w3 (the blit_transp_cell / objsh_build_mask
 * formula, 0xFFFF high word) and there is NO colour indexing — pixels are copied plain-shifted and
 * OR'd. Four width families width_idx 0..3 (WIDTH 0x80/0x88/0x90/0x98). PURE LEAF. Used by the
 * roadside-object dispatcher's t1/t2/t4/w88/t53 handlers.
 * ============================================================================================ */
#define OBJSP_WIDTH_80    0x80    /* width_idx 0 base width; WIDTH = this + 8*width_idx */
#define OBJSP_WIDTHS      4       /* four width families */
#define OBJSP_LADDER_STEP 8
#define OBJSP_REWIND_C0   0xc0    /* per-row rewind base (d3 = this - 8*rung) */
#define OBJSP_BASE_CELLS  4       /* BASE straddle cells for width_idx 0 (4 - width_idx) */

/* STRADDLE cell: like objsh but no colour fill (pixels copied plain). */
static void objsp_straddle_cell(uint8_t *dst, const uint8_t *src, Offset *col0, Offset *col1,
                                uint32_t *sp, unsigned shl) {
    uint32_t mask32 = rotl32(objsh_build_mask(src, *sp), shl);
    uint16_t col0_mask = (uint16_t)(mask32 >> OBJSH_SUBPX_BITS);
    uint16_t col1_mask = (uint16_t)mask32;
    for (int plane = 0; plane < OBJSH_PLANES; plane++) {
        uint32_t pix32 = (uint32_t)be16(src + *sp) << shl;
        *sp += 2;
        uint16_t col1_pix = (uint16_t)pix32;
        uint16_t col0_pix = (uint16_t)(pix32 >> OBJSH_SUBPX_BITS);
        if (plane == OBJSH_PLANES - 1) {
            col1_pix = (uint16_t)(col1_pix & (uint16_t)~col1_mask);
            col0_pix = (uint16_t)(col0_pix & (uint16_t)~col0_mask);
        }
        plane_write(dst, *col1, col1_mask, col1_pix);   /* col1 first */
        plane_write(dst, *col0, col0_mask, col0_pix);
        *col0 += 2; *col1 += 2;
    }
}

/* LEFT-EDGE cell: only col1 drawn, mask rol.l'd (low word used), pixels shift left as words. */
static void objsp_left_edge_cell(uint8_t *dst, const uint8_t *src, Offset *col1, uint32_t *sp,
                                 unsigned shl) {
    uint16_t mask = (uint16_t)rotl32(objsh_build_mask(src, *sp), shl);
    for (int plane = 0; plane < OBJSH_PLANES; plane++) {
        uint16_t pix = (uint16_t)((uint32_t)be16(src + *sp) << shl);
        *sp += 2;
        if (plane == OBJSH_PLANES - 1) pix = (uint16_t)(pix & (uint16_t)~mask);
        plane_write(dst, *col1, mask, pix);
        *col1 += 2;
    }
}

/* RIGHT-EDGE cell: only col0 drawn, mask lsr.l'd by shr, pixels shift right as words. */
static void objsp_right_edge_cell(uint8_t *dst, const uint8_t *src, Offset *col0, uint32_t *sp,
                                  unsigned shr) {
    uint16_t mask = (uint16_t)(objsh_build_mask(src, *sp) >> shr);
    for (int plane = 0; plane < OBJSH_PLANES; plane++) {
        uint16_t pix = (uint16_t)(be16(src + *sp) >> shr);
        *sp += 2;
        if (plane == OBJSH_PLANES - 1) pix = (uint16_t)(pix & (uint16_t)~mask);
        plane_write(dst, *col0, mask, pix);
        *col0 += 2;
    }
}

enum objsp_family { OBJSP_CLIP, OBJSP_BASE, OBJSP_LEFT, OBJSP_WIDE };

static void objsp_row(uint8_t *dst, const uint8_t *src, Offset *col0, Offset *col1, uint32_t *sp,
                      enum objsp_family fam, int straddle, unsigned shl, unsigned shr) {
    if (fam == OBJSP_LEFT) {
        objsp_left_edge_cell(dst, src, col1, sp, shl);
        *col0 += OBJSH_CELL_BYTES;
    }
    for (int i = 0; i < straddle; i++)
        objsp_straddle_cell(dst, src, col0, col1, sp, shl);
    if (fam == OBJSP_WIDE) {
        objsp_right_edge_cell(dst, src, col0, sp, shr);
        *col1 += OBJSH_CELL_BYTES;
    }
}

/* The shared parameterized objsprite core (@0x13206). width_idx = (WIDTH - 0x80)/8 selects the
 * width bound + the entry rung of both clip ladders. col0_init = dst_off + aligned_col. */
static void objsp_core(uint8_t *dst, const uint8_t *src, uint16_t aligned_col, unsigned shl,
                       unsigned shr, uint16_t rows_m1, Offset col0_init, uint32_t src_init,
                       int width_idx) {
    Offset col0 = col0_init;
    uint32_t sp = src_init;
    enum objsp_family fam;
    int straddle, rung;

    if ((int16_t)aligned_col < 0) {
        int16_t col_walk = (int16_t)aligned_col;
        fam = OBJSP_CLIP;
        for (rung = width_idx; rung < OBJSP_WIDTHS; rung++) {
            col_walk = (int16_t)(col_walk + OBJSP_LADDER_STEP);
            if (col_walk >= 0) { fam = OBJSP_LEFT; break; }
            sp += OBJSH_CELL_BYTES;
            col0 += OBJSH_CELL_BYTES;
        }
        if (fam == OBJSP_CLIP) return;                    /* fully off-left */
        straddle = (OBJSP_WIDTHS - 1) - rung;
    } else {
        int16_t width = (int16_t)(OBJSP_WIDTH_80 + OBJSP_LADDER_STEP * width_idx);
        int16_t col_walk = (int16_t)((int16_t)aligned_col - width);
        if (col_walk < 0) {
            fam = OBJSP_BASE;
            straddle = OBJSP_BASE_CELLS - width_idx;
            rung = width_idx;
        } else {
            fam = OBJSP_CLIP;
            for (rung = width_idx; rung < OBJSP_WIDTHS; rung++) {
                col_walk = (int16_t)(col_walk - OBJSP_LADDER_STEP);
                if (col_walk < 0) { fam = OBJSP_WIDE; break; }
            }
            if (fam == OBJSP_CLIP) return;                /* fully off-right */
            straddle = (OBJSP_WIDTHS - 1) - rung;
        }
    }

    uint16_t rewind = (uint16_t)(OBJSP_REWIND_C0 - OBJSP_LADDER_STEP * rung);
    Offset col1 = col0 + OBJSH_CELL_BYTES;
    int rows = (int16_t)rows_m1 + 1;
    for (int row = 0; row < rows; row++) {
        objsp_row(dst, src, &col0, &col1, &sp, fam, straddle, shl, shr);
        col0 = (Offset)(col0 - sx16(rewind));
        col1 = (Offset)(col1 - sx16(rewind));
        sp = (uint32_t)(sp - sx16(rewind));
    }
}

/* Fine-x prologue (@0x131f6): derive fine_x/shl/shr + aligned_col from x, add the aligned column
 * into the dst, then run the core. `width_idx` folds in the width immediate (t4=0, w88=1, t2=2,
 * t1=3). */
void rm_objsprite(uint8_t *dst, Offset dst_off, const uint8_t *src, uint32_t src_off,
                  uint16_t x, uint16_t rows_m1, int width_idx) {
    unsigned fine_x = (unsigned)(x & OBJSH_NIBBLE);
    unsigned shl = OBJSH_SUBPX_BITS - fine_x;
    unsigned shr = fine_x;
    uint16_t col = objsh_aligned_col(x);
    Offset col0_init = (Offset)(dst_off + sx16(col));
    objsp_core(dst, src, col, shl, shr, rows_m1, col0_init, src_off, width_idx);
}

/* Alt entry (@0x13204, t53): the caller pre-computes aligned_col / shl / shr; skips the fine-x calc.
 * Joins the width-0x80 dispatch. */
void rm_objsprite_alt(uint8_t *dst, Offset dst_off, const uint8_t *src, uint32_t src_off,
                      uint16_t aligned_col, unsigned shl, unsigned shr, uint16_t rows_m1) {
    Offset col0_init = (Offset)(dst_off + sx16(aligned_col));
    objsp_core(dst, src, aligned_col, shl, shr, rows_m1, col0_init, src_off, 0);
}
