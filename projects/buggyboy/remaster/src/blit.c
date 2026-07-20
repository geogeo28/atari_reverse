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

/* STRADDLE cell: 32-bit left shift straddles both columns; high half -> col0, low half -> col1. */
static void objsh_straddle_cell(uint8_t *dst, const uint8_t *src, Offset *col0, Offset *col1,
                                uint32_t *sp, unsigned shl, Plane4 fill_lo, Plane4 fill_hi) {
    uint32_t mask32 = rotl32(objsh_build_mask(src, *sp), shl);
    uint16_t mask_hi = (uint16_t)(mask32 >> OBJSH_SUBPX_BITS);   /* col0 */
    uint16_t mask_lo = (uint16_t)mask32;                         /* col1 */
    for (int plane = 0; plane < OBJSH_PLANES; plane++) {
        uint32_t pix32 = (uint32_t)be16(src + *sp) << shl;
        *sp += 2;
        uint16_t fill = objsh_fill_half(fill_lo, fill_hi, plane);
        uint16_t pix_lo = (uint16_t)((pix32 & 0xffff) & fill);
        uint16_t pix_hi = (uint16_t)((pix32 >> OBJSH_SUBPX_BITS) & fill);
        if (plane == OBJSH_PLANES - 1) { pix_lo &= (uint16_t)~mask_lo; pix_hi &= (uint16_t)~mask_hi; }
        plane_write(dst, *col1, mask_lo, pix_lo);   /* col1 first */
        plane_write(dst, *col0, mask_hi, pix_hi);
        *col0 += 2; *col1 += 2;
    }
}

/* EDGE cell (single on-screen column): mask built + shifted as the full 32-bit register (rol.l shl
 * for LEFT, lsr.l shr for RIGHT); low word gates the column. Pixels shift as words. */
static void objsh_edge_cell(uint8_t *dst, const uint8_t *src, Offset *ptr, uint32_t *sp,
                            unsigned shift, int is_right, Plane4 fill_lo, Plane4 fill_hi) {
    uint32_t m32 = objsh_build_mask(src, *sp);
    uint16_t mask = (uint16_t)(is_right ? (m32 >> shift) : rotl32(m32, shift));
    for (int plane = 0; plane < OBJSH_PLANES; plane++) {
        uint16_t word = be16(src + *sp);
        *sp += 2;
        uint16_t pix = is_right ? (uint16_t)(word >> shift) : (uint16_t)((uint32_t)word << shift);
        pix = (uint16_t)(pix & objsh_fill_half(fill_lo, fill_hi, plane));
        if (plane == OBJSH_PLANES - 1) pix &= (uint16_t)~mask;
        plane_write(dst, *ptr, mask, pix);
        *ptr += 2;
    }
}

enum objsh_family { OBJSH_CLIP, OBJSH_BASE, OBJSH_LEFT, OBJSH_RIGHT };

static void objsh_row(uint8_t *dst, const uint8_t *src, Offset *col0, Offset *col1, uint32_t *sp,
                      enum objsh_family fam, int straddle, unsigned shl, unsigned shr,
                      Plane4 fill_lo, Plane4 fill_hi) {
    if (fam == OBJSH_LEFT) {
        objsh_edge_cell(dst, src, col1, sp, shl, /*is_right=*/0, fill_lo, fill_hi);
        *col0 += OBJSH_CELL_BYTES;
    }
    for (int i = 0; i < straddle; i++)
        objsh_straddle_cell(dst, src, col0, col1, sp, shl, fill_lo, fill_hi);
    if (fam == OBJSH_RIGHT) {
        objsh_edge_cell(dst, src, col0, sp, shr, /*is_right=*/1, fill_lo, fill_hi);
        *col1 += OBJSH_CELL_BYTES;
    }
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

    uint32_t sp = src_off + (uint32_t)(OBJSH_CELL_BYTES * skips);
    Offset col0 = (dst_off + sx16((uint16_t)A)) + (uint32_t)(OBJSH_CELL_BYTES * skips);
    Offset col1 = col0 + OBJSH_CELL_BYTES;
    for (int row = 0; row < rows; row++) {
        objsh_row(dst, src, &col0, &col1, &sp, fam, straddle, shl, shr, fill_lo, fill_hi);
        col0 = (Offset)(col0 - sx16(rewind));
        col1 = (Offset)(col1 - sx16(rewind));
        sp = (uint32_t)(sp - sx16((uint16_t)stride));
        sp = (uint32_t)(sp - sx16(src_extra));
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
