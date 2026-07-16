/* blit.c — object sprite blitters (blit_obj_* @ 0x10bdc..).
 *
 * These draw a roadside-object sprite into the draw buffer one scanline per row. Every
 * variant is built from one per-row primitive (left- or right-anchored) driven by a
 * different scan pattern:
 *   near (Ln/Rn)   fixed x, a straight vertical column; masked rows step one scanline (160),
 *                  a full-width row steps by the object stride (width).
 *   far  (Lf/Rf)   x slants by one per row, every row steps by width (perspective recession).
 *   road-walk (*2) x per row comes from road_width_tbl plus a per-variant ramp.
 * The per-row primitive picks a regime from x: off-edge (skip or full-fill), fully inside
 * the road (solid 10-cell fill), or straddling the edge (antialiased masked column from
 * A_blit_mask_L/R plus a solid interior of the whole cells beside it).
 *
 * The g_* glue maps the 68000 register ABI to these; each notes its register map. All
 * 16-bit register arithmetic wraps mod 2^16, mirrored with explicit int16/uint16.
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

static uint32_t load32(const uint8_t *image, uint32_t addr) { return be32(image + addr); }
static void     store32(uint8_t *image, uint32_t addr, uint32_t value) { wr32(image + addr, value); }

/* Byte-aligned draw column from a screen x: x/2 with the low 3 bits cleared (8-byte cell). */
#define COL_ALIGN 0xfff8
static uint16_t aligned_col(uint16_t x) { return (uint16_t)((int16_t)x >> 1) & COL_ALIGN; }

/* Solid full-width row: 10 two-longword colour cells. */
static void full_row(uint8_t *image, uint32_t dst, uint32_t fill_lo, uint32_t fill_hi) {
    for (int cell = 0; cell < OBJ_FULL_CELLS; cell++, dst += 16) {
        store32(image, dst, fill_lo);     store32(image, dst + 4, fill_hi);
        store32(image, dst + 8, fill_lo); store32(image, dst + 12, fill_hi);
    }
}

/* One left-anchored row at row base `dst`, screen x. Returns the status word the caller
 * chains on: the column off-left, or (edge-width) when full, or 0xffff/mask when masked. */
static uint32_t row_left(uint8_t *image, uint32_t dst, uint16_t x, int16_t width, uint32_t fill_lo, uint32_t fill_hi) {
    uint16_t half_x   = (uint16_t)((int16_t)x >> 1);
    uint16_t edge_col = half_x & COL_ALIGN;

    if ((int16_t)edge_col < 0) return edge_col;            /* off the left edge: no draw */
    if ((int16_t)(edge_col - (uint16_t)width) >= 0) {      /* fully inside: solid fill */
        full_row(image, dst, fill_lo, fill_hi);
        return (uint32_t)(uint16_t)(edge_col - (uint16_t)width);
    }
    /* straddling the edge: masked edge cell + solid interior to its left */
    uint32_t edge_mask = load32(image, A_blit_mask_L + sign_ext16((x & 0xf) << 2));
    uint32_t edge_ptr = dst + sign_ext16(edge_col);
    store32(image, edge_ptr,     (load32(image, edge_ptr)     & edge_mask) | (fill_lo & ~edge_mask));
    store32(image, edge_ptr + 4, (load32(image, edge_ptr + 4) & edge_mask) | (fill_hi & ~edge_mask));

    uint16_t interior_cells = half_x >> 3;
    if (interior_cells == 0) return edge_mask;
    uint32_t interior_ptr = dst;
    for (uint16_t cell = 0; cell < interior_cells; cell++, interior_ptr += 8) {
        store32(image, interior_ptr, fill_lo); store32(image, interior_ptr + 4, fill_hi);
    }
    return 0xffff;
}

/* One right-anchored row. Off-right fills the whole row; inside the width it draws a masked
 * edge cell plus a solid interior extending rightward. No meaningful return (callers void). */
static void row_right(uint8_t *image, uint32_t dst, uint16_t x, int16_t width, uint32_t fill_lo, uint32_t fill_hi) {
    uint16_t col = aligned_col(x);

    if ((int16_t)col < 0) { full_row(image, dst, fill_lo, fill_hi); return; }  /* off the right edge */
    if ((int16_t)(col - (uint16_t)width) >= 0) return;                         /* past the width */

    uint32_t edge_mask = load32(image, A_blit_mask_R + sign_ext16((x & 0xf) << 2));
    uint32_t edge_ptr = dst + sign_ext16(col);
    store32(image, edge_ptr,     (load32(image, edge_ptr)     & edge_mask) | (fill_lo & ~edge_mask));
    store32(image, edge_ptr + 4, (load32(image, edge_ptr + 4) & edge_mask) | (fill_hi & ~edge_mask));

    int16_t remaining = (int16_t)(col - (uint16_t)width) + 8;
    uint32_t interior_ptr = edge_ptr + 8;
    for (; remaining < 0; remaining += 8, interior_ptr += 8) {
        store32(image, interior_ptr, fill_lo); store32(image, interior_ptr + 4, fill_hi);
    }
}

/* ---- near variants: fixed x, straight vertical column ---- */
/* A6 buf_base, D2 width, D3 row_offset, D4 x, D5/D6 fill, D7 rows-1 */

uint32_t g_blit_obj_Ln(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t row_offset,
                       uint32_t x, uint32_t fill_lo, uint32_t fill_hi, uint32_t rows_minus1) {
    int16_t obj_width = (int16_t)width;
    uint16_t screen_x = (uint16_t)x;
    uint32_t dst = buf_base + sign_ext16(row_offset);
    int rows = (int16_t)rows_minus1 + 1;

    uint16_t edge_col = aligned_col(screen_x);
    if ((int16_t)edge_col < 0) return edge_col;
    int full = (int16_t)(edge_col - (uint16_t)obj_width) >= 0;
    int32_t stride = full ? -(int32_t)obj_width : -(int32_t)OBJ_ROW_UP;

    uint32_t status = 0;
    for (int row = 0; row < rows; row++, dst = (uint32_t)((int32_t)dst + stride))
        status = row_left(image, dst, screen_x, obj_width, fill_lo, fill_hi);
    return status;
}

void g_blit_obj_Rn(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t row_offset,
                   uint32_t x, uint32_t fill_lo, uint32_t fill_hi, uint32_t rows_minus1) {
    int16_t obj_width = (int16_t)width;
    uint16_t screen_x = (uint16_t)x;
    uint32_t dst = buf_base + sign_ext16(row_offset);
    int rows = (int16_t)rows_minus1 + 1;

    uint16_t col = aligned_col(screen_x);
    int32_t stride = ((int16_t)col < 0) ? -(int32_t)obj_width : -(int32_t)OBJ_ROW_UP;
    for (int row = 0; row < rows; row++, dst = (uint32_t)((int32_t)dst + stride))
        row_right(image, dst, screen_x, obj_width, fill_lo, fill_hi);
}

/* ---- far variants: x slants by one per row, stride = object width ---- */

uint32_t g_blit_obj_Lf(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t row_offset,
                       uint32_t x, uint32_t fill_lo, uint32_t fill_hi, uint32_t rows_minus1) {
    int16_t obj_width = (int16_t)width;
    uint16_t cur_x = (uint16_t)x;
    uint32_t dst = buf_base + sign_ext16(row_offset);
    int rows = (int16_t)rows_minus1 + 1;

    uint32_t status = 0;
    for (int row = 0; row < rows; row++, dst = (uint32_t)((int32_t)dst - obj_width), cur_x = (uint16_t)(cur_x - 1))
        status = row_left(image, dst, cur_x, obj_width, fill_lo, fill_hi);
    return status;
}

void g_blit_obj_Rf(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t row_offset,
                   uint32_t x, uint32_t fill_lo, uint32_t fill_hi, uint32_t rows_minus1) {
    int16_t obj_width = (int16_t)width;
    uint16_t cur_x = (uint16_t)x;
    uint32_t dst = buf_base + sign_ext16(row_offset);
    int rows = (int16_t)rows_minus1 + 1;

    for (int row = 0; row < rows; row++, dst = (uint32_t)((int32_t)dst - obj_width), cur_x = (uint16_t)(cur_x + 1))
        row_right(image, dst, cur_x, obj_width, fill_lo, fill_hi);
}

/* ---- road-walk variants: blit the object down the curving road ----
 * Walk road_width_tbl (paired shorts: [flag, x-offset]) from OBJ_ROAD_START_OFF: skip the
 * leading inactive rows (flag >= 0), then draw each active row (flag < 0) until the band
 * ends. The screen x per row is the pair's x-offset plus a per-variant linear ramp in the
 * remaining-row counter. Every row advances one pair and steps the buffer by the width.
 */
static void road_walk(uint8_t *image, uint32_t buf_base, int16_t width, uint32_t fill_lo,
                      uint32_t fill_hi, int is_left, int ramp_mul, int ramp_add) {
    uint32_t dst = buf_base + OBJ_ROAD_START_OFF;
    uint32_t tbl_ptr = A_road_width_tbl;
    int counter = OBJ_ROAD_ROWS;

    while ((int16_t)be16(image + tbl_ptr) >= 0) {          /* skip leading inactive rows */
        tbl_ptr += 4; dst = (uint32_t)((int32_t)dst - width);
        if (--counter < 0) return;
    }
    for (;;) {
        if ((int16_t)be16(image + tbl_ptr) >= 0) return;   /* end of the active band */
        int16_t x_off = (int16_t)be16(image + tbl_ptr + 2);
        uint16_t x = (uint16_t)(x_off + counter * ramp_mul + ramp_add);
        tbl_ptr += 4;
        if (is_left) row_left(image, dst, x, width, fill_lo, fill_hi);
        else         row_right(image, dst, x, width, fill_lo, fill_hi);
        dst = (uint32_t)((int32_t)dst - width);
        if (--counter < 0) return;
    }
}

/* A6 buf_base, D2 width, D5/D6 fill; x per row comes from the road table + ramp. */
void g_blit_obj_Ln2(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t fill_lo, uint32_t fill_hi) {
    road_walk(image, buf_base, (int16_t)width, fill_lo, fill_hi, /*is_left=*/1, /*ramp_mul=*/1, /*ramp_add=*/0x41);
}
void g_blit_obj_Lf2(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t fill_lo, uint32_t fill_hi) {
    road_walk(image, buf_base, (int16_t)width, fill_lo, fill_hi, /*is_left=*/1, /*ramp_mul=*/3, /*ramp_add=*/-0x7b);
}
void g_blit_obj_Rn2(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t fill_lo, uint32_t fill_hi) {
    road_walk(image, buf_base, (int16_t)width, fill_lo, fill_hi, /*is_left=*/0, /*ramp_mul=*/-1, /*ramp_add=*/0xfe);
}
void g_blit_obj_Rf2(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t fill_lo, uint32_t fill_hi) {
    road_walk(image, buf_base, (int16_t)width, fill_lo, fill_hi, /*is_left=*/0, /*ramp_mul=*/-3, /*ramp_add=*/0x1ba);
}
/* ============================================================================================
 * blit_objshift @ 0x14680 — sub-pixel (fine-x shifted) 4-plane masked-transparency sprite blitter.
 *
 * The innermost sprite engine: the fine-x cousin of blit_transp_cell (draw.h) and the blit_obj_*
 * family above. Where those blit at cell granularity, this shifts each 16-pixel source column left
 * by (16 - fine_x) (BASE/LEFT) or right by fine_x (RIGHT clipped edge) so a sprite lands at an
 * arbitrary pixel x, straddling two 16-pixel destination columns (a0 = col0, a2 = a0 + 8 = col1).
 *
 * PURE LEAF. The register contract (see names.txt proto): D0 screen x, D1 colour index, D4 rows-1,
 * A0 dst scanline base, A1 src sprite stream, A3 -> per-row src-stride word. See BLIT_OBJSHIFT_SPEC.md.
 */
#define OBJSH_NIBBLE       0xf      /* fine-x / colour-index low nibble mask */
#define OBJSH_SUBPX_BITS   16       /* left-shift count d6 = 16 - fine_x */
#define OBJSH_COLOR_STRIDE 8        /* colour index * 8 = byte offset into color_pairs */
#define OBJSH_RIGHT_BOUND  0x98     /* aligned_col >= this -> RIGHT/clipped family */
#define OBJSH_CELL_BYTES   8        /* one 16-pixel 4-plane cell / one column step */
#define OBJSH_ROW_REWIND   0xa8     /* base per-row a0/a2 rewind (Δ = this + CELL_BYTES*straddle) */
#define OBJSH_PLANES       4
#define OBJSH_LEFT_EDGE_COL (-8)    /* the one reachable LEFT case: aligned_col == -8 */

/* Rotate a 32-bit value left (68k rol.l); count is 1..16 here so no mod-32 subtlety. */
static uint32_t rotl32(uint32_t v, unsigned count) {
    count &= 31;
    return count ? ((v << count) | (v >> (32 - count))) : v;
}

/* Build the cell's 32-bit mask register from the four plane words at *a1. The 68k `moveq #$ff,d2`
 * sign-extends 0xff to 0xFFFFFFFF, so the mask longword's HIGH word is 0xFFFF (not 0) going into the
 * rol.l/lsr.l — those set bits shift/rotate into the other 16-pixel column and are load-bearing. The
 * low word is the SHOW mask ~(A|B|C) & D (identical to blit_transp_cell). */
#define OBJSH_MASK_HI_FILL 0xffff0000u   /* moveq #$ff sign-extension into the mask's high word */
static uint32_t objsh_build_mask(const uint8_t *image, uint32_t a1) {
    uint16_t a = be16(image + a1);
    uint16_t b = be16(image + a1 + 2);
    uint16_t c = be16(image + a1 + 4);
    uint16_t d = be16(image + a1 + 6);
    return OBJSH_MASK_HI_FILL | (uint16_t)(~(a | b | c) & d);
}

/* Masked OR-in of one plane word into a destination column (68k `and.w mask,(ptr)` +
 * `or.w pix,(ptr)` collapsed): keep the background where mask is set, drop in the shifted pixels. */
static void objsh_plane_write(uint8_t *image, uint32_t ptr, uint16_t mask, uint16_t pix) {
    wr16(image + ptr, (uint16_t)((be16(image + ptr) & mask) | pix));
}

/* The colour fill halves consumed per plane, in the fixed swap-toggled order the asm walks:
 * plane0 = d3 hi, plane1 = d3 lo, plane2 = d5 hi, plane3 = d5 lo. */
static uint16_t objsh_fill_half(uint32_t fill_lo /*d3*/, uint32_t fill_hi /*d5*/, int plane) {
    uint32_t reg = (plane < 2) ? fill_lo : fill_hi;
    return (uint16_t)((plane & 1) ? (reg & 0xffff) : (reg >> OBJSH_SUBPX_BITS));
}

/* STRADDLE cell (BASE + non-edge): 32-bit left shift straddles both columns (a0 = col0, a2 = col1).
 * mask32 = rotl32(mask, shl); MASK_HI gates col0, MASK_LO gates col1. Each plane word is shifted
 * left by shl (32-bit): high half -> col0, low half -> col1, each masked by the plane's fill half.
 * Every plane keeps the background via (dst & mask); plane 3 (the D leftover) additionally masks its
 * pixels with ~mask so it lights only the opaque bits — exactly blit_transp_cell's plane-3 rule.
 * Advances a0/a2/a1 by one cell. */
static void objsh_straddle_cell(uint8_t *image, uint32_t *a0, uint32_t *a2, uint32_t *a1,
                                unsigned shl, uint32_t fill_lo, uint32_t fill_hi) {
    uint32_t mask32 = rotl32(objsh_build_mask(image, *a1), shl);
    uint16_t mask_hi = (uint16_t)(mask32 >> OBJSH_SUBPX_BITS);   /* col0 (a0) */
    uint16_t mask_lo = (uint16_t)mask32;                         /* col1 (a2) */
    for (int plane = 0; plane < OBJSH_PLANES; plane++) {
        uint32_t pix32 = (uint32_t)be16(image + *a1) << shl;
        *a1 += 2;
        uint16_t fill = objsh_fill_half(fill_lo, fill_hi, plane);
        uint16_t pix_lo = (uint16_t)((pix32 & 0xffff) & fill);
        uint16_t pix_hi = (uint16_t)((pix32 >> OBJSH_SUBPX_BITS) & fill);
        if (plane == OBJSH_PLANES - 1) {                        /* D leftover: pixels &= ~mask */
            pix_lo &= (uint16_t)~mask_lo;
            pix_hi &= (uint16_t)~mask_hi;
        }
        objsh_plane_write(image, *a2, mask_lo, pix_lo);         /* col1 first */
        objsh_plane_write(image, *a0, mask_hi, pix_hi);
        *a0 += 2; *a2 += 2;
    }
}

/* EDGE cell (single column): the sprite's leading (LEFT) or trailing (RIGHT) 16px column is clipped
 * off-screen, so only one on-screen column is drawn. The MASK is built + shifted as the full 32-bit
 * register (rol.l shl for LEFT, lsr.l shr for RIGHT), then its LOW word gates the column. The PIXELS
 * shift as WORDs (lsl.w/lsr.w — no straddle spill). LEFT writes (a2) shifted left by shl = 16-fine_x;
 * RIGHT writes (a0) shifted right by shr = fine_x. Plane 3 (D leftover) uses the inverse mask. */
static void objsh_edge_cell(uint8_t *image, uint32_t *ptr, uint32_t *a1,
                            unsigned shift, int is_right, uint32_t fill_lo, uint32_t fill_hi) {
    uint32_t m32 = objsh_build_mask(image, *a1);
    uint16_t mask = (uint16_t)(is_right ? (m32 >> shift) : rotl32(m32, shift));
    for (int plane = 0; plane < OBJSH_PLANES; plane++) {
        uint16_t word = be16(image + *a1);
        *a1 += 2;
        uint16_t pix = is_right ? (uint16_t)(word >> shift)
                                : (uint16_t)((uint32_t)word << shift);
        uint16_t fill = objsh_fill_half(fill_lo, fill_hi, plane);
        pix = (uint16_t)(pix & fill);
        if (plane == OBJSH_PLANES - 1) pix &= (uint16_t)~mask;   /* D leftover: pixels &= ~mask */
        objsh_plane_write(image, *ptr, mask, pix);
        *ptr += 2;
    }
}

/* Which sprite family the aligned column selects (spec §3.4). Only these three are reachable from
 * the documented entry; wider clipped columns rts without drawing. */
enum objsh_family { OBJSH_CLIP, OBJSH_BASE, OBJSH_LEFT, OBJSH_RIGHT };

static enum objsh_family objsh_dispatch(uint16_t aligned_col) {
    if ((int16_t)aligned_col < 0)
        return (int16_t)aligned_col == OBJSH_LEFT_EDGE_COL ? OBJSH_LEFT : OBJSH_CLIP;
    if ((int16_t)(aligned_col - OBJSH_RIGHT_BOUND) >= 0)
        return aligned_col == OBJSH_RIGHT_BOUND ? OBJSH_RIGHT : OBJSH_CLIP;
    return OBJSH_BASE;
}

/* One row of the sprite. `straddle` = number of two-column S cells; LEFT prepends an a2-only lead
 * edge (then re-syncs a0 by one cell), RIGHT appends an a0-only trail edge. a0/a2/a1 advance across
 * the cells; the caller applies the per-row rewind. shl = 16-fine_x, shr = fine_x. */
static void objsh_row(uint8_t *image, uint32_t *a0, uint32_t *a2, uint32_t *a1,
                      enum objsh_family fam, int straddle, unsigned shl, unsigned shr,
                      uint32_t fill_lo, uint32_t fill_hi) {
    if (fam == OBJSH_LEFT) {
        objsh_edge_cell(image, a2, a1, shl, /*is_right=*/0, fill_lo, fill_hi);
        *a0 += OBJSH_CELL_BYTES;                 /* re-sync a0 to the first visible column */
    }
    for (int i = 0; i < straddle; i++)
        objsh_straddle_cell(image, a0, a2, a1, shl, fill_lo, fill_hi);
    if (fam == OBJSH_RIGHT) {
        objsh_edge_cell(image, a0, a1, shr, /*is_right=*/1, fill_lo, fill_hi);
        *a2 += OBJSH_CELL_BYTES;                 /* keep a2 in step (dead bookkeeping) */
    }
}

/* Glue: map the 68000 register ABI to the row loop. a0/a1/a3 are image offsets read/written like
 * blit.c's other glue. color_pairs is real image data (not staged). Register map: D0 x, D1 colour,
 * D4 rows-1, A0 dst, A1 src, A3 stride_ptr. */
void g_blit_objshift(uint8_t *image, uint32_t x, uint32_t color, uint32_t rows_m1,
                     uint32_t dst, uint32_t src, uint32_t stride_ptr) {
    unsigned fine_x = (unsigned)(x & OBJSH_NIBBLE);           /* from the ORIGINAL x, before asr */
    unsigned shl = OBJSH_SUBPX_BITS - fine_x;                 /* d6 = 16 - fine_x */
    unsigned shr = fine_x;                                    /* d7 = fine_x */

    uint16_t col_off = (uint16_t)((color & OBJSH_NIBBLE) << 3);
    uint32_t fill_lo = load32(image, A_color_pairs + col_off);        /* d3: planes 0,1 */
    uint32_t fill_hi = load32(image, A_color_pairs + col_off + 4);    /* d5: planes 2,3 */

    uint16_t col = aligned_col((uint16_t)x);
    enum objsh_family fam = objsh_dispatch(col);
    if (fam == OBJSH_CLIP) return;

    /* Straddle-cell count drawn per row vs. the rewind's `s` term differ for BASE: BASE draws one
     * S cell but rewinds by only ROW_REWIND (its cell advance is already the whole width). LEFT/RIGHT
     * draw `s` S cells (0 on the reachable entry path) plus one edge cell, and rewind by 8*s extra.
     * Only s == 0 is reachable from the documented entry; the deeper unrolled bodies (s = 1..3) are
     * dead but would parameterize identically here. */
    int straddle_cells = (fam == OBJSH_BASE) ? 1 : 0;
    int rewind_cells = (fam == OBJSH_BASE) ? 0 : straddle_cells;
    uint16_t rewind = (uint16_t)(OBJSH_ROW_REWIND + OBJSH_CELL_BYTES * rewind_cells);
    uint16_t a1_extra = (uint16_t)(OBJSH_CELL_BYTES * rewind_cells);
    int rows = (int16_t)rows_m1 + 1;

    uint32_t a1 = src;
    uint32_t a0 = dst + sign_ext16(col);
    uint32_t a2 = a0 + OBJSH_CELL_BYTES;                     /* movea.l a0,a2; addq.l #8,a2 (once) */
    for (int row = 0; row < rows; row++) {
        objsh_row(image, &a0, &a2, &a1, fam, straddle_cells, shl, shr, fill_lo, fill_hi);
        a0 = (uint32_t)(a0 - sign_ext16(rewind));            /* suba.w #Δ,a0 (a2 tracks a0+8) */
        a2 = (uint32_t)(a2 - sign_ext16(rewind));            /* suba.w #Δ,a2 */
        a1 = (uint32_t)(a1 - sign_ext16(be16(image + stride_ptr)));   /* suba.w (a3),a1 */
        a1 = (uint32_t)(a1 - sign_ext16(a1_extra));                   /* suba.w #extra,a1 */
    }
}

/* ============================================================================================
 * roadside-object sprite draw-handler family @ 0x14620 / 0x1465c / 0x14664 (+ shared tail 0x14676).
 *
 * Mid-level "draw one roadside-object sprite" helpers that sit between draw_object_list (the
 * dispatcher) and the g_blit_objshift leaf above. They read a per-object DESCRIPTOR record (via A2)
 * plus view_flags / a parity flag, set up the blit registers and the per-row src stride, and call
 * g_blit_objshift. Three entry points share the geometry and the final blit:
 *   0x14620 (draw_obj_sprite_hi)  shared subroutine: derive geometry from the record + view_flags,
 *                                 first blit (mode 8), rename D3->D0 / D5->D4 across the call.
 *   0x1465c (draw_obj_handler_dbl) table handler: save colour, run 0x14620, restore colour, tail.
 *   0x14664 (draw_obj_handler_lo)  table handler: dst = A6 + fixed band, src += per-parity word, tail.
 *   0x14676 (draw_obj_blit_tail)   shared tail: set mode 0xa8, fall straight into g_blit_objshift.
 * See BLIT_OBJSPRITE_SPEC.md for the full instruction decode. All 16-bit register arithmetic wraps
 * mod 2^16, mirrored with explicit int16/uint16.
 */
#define A_blit_mode      0x18cb0    /* per-row src-stride/mode word the leaf reads via A3 */
#define A_view_parity    0x18c60    /* per-view parity flag word (&2 selects the src offset) */
#define OBJH_MODE_MAIN   0x8        /* mode word for the 0x14620 first pass */
#define OBJH_MODE_TAIL   0xa8       /* mode word for the 0x14676 tail/second pass */
#define OBJH_BAND_LO     0x3ac0     /* fixed dst-band offset from A6 (0x14664) */
#define OBJH_PARITY_MASK 0x2        /* moveq #2; and.w view_parity -> {0,2} */
#define OBJH_SRC_REWIND  0xa0       /* suba.w #0xa0,a1: rewind src one band (= OBJD_WIDTH) */
/* Descriptor-record layout (in buf_a, resolved by draw_object_list into these helpers' registers,
 * so referenced here only for context): word@rec+8 = x screen offset (re-read by move.w -(a2),d3);
 * rec+0xc = per-view rows-1 byte table (indexed 4(a2,d7), a2=rec+8) and per-parity src-offset base
 * (indexed 2(a2,d2), a2=rec+0xa). */

/* Shared tail (0x14676): write mode 0xa8, then fall through into g_blit_objshift (one blit). */
static void draw_obj_blit_tail(uint8_t *image, uint32_t x, uint32_t colour, uint32_t rows_m1,
                               uint32_t dst, uint32_t src) {
    wr16(image + A_blit_mode, OBJH_MODE_TAIL);
    g_blit_objshift(image, x, colour, rows_m1, dst, src, A_blit_mode);
}

/* Renamed registers 0x14620 leaves for its caller's tail: movem rename D3->D0, D5->D4; A0=sprite
 * top; A1 rewound one band. */
struct obj_hi_out { uint16_t d0_x; uint16_t d4_rows; uint32_t a0_dst; uint32_t a1_src; };

/* 0x14620 shared helper. Register map: D0 x accum, D1 colour (passed through), D2 width (=0xa0),
 * D4 rows seed, D7 caller vertical offset, A0 dst scanline base, A1 src stream, A2 = rec+0xa. */
static struct obj_hi_out
draw_obj_sprite_hi(uint8_t *image, uint16_t x, uint16_t colour, uint16_t width,
                   uint16_t rows_seed, uint16_t voff, uint32_t dst, uint32_t src, uint32_t rec_cursor) {
    uint16_t rows_copy = rows_seed;                                  /* move.w d4,d5 (survives blit) */
    uint32_t rec_xoff = rec_cursor - 2;                              /* move.w -(a2),d3 -> a2 = rec+8 */
    uint16_t xoff = be16(image + rec_xoff);                          /* D3 = word@rec+8 */
    dst = (uint32_t)(dst - sign_ext16(xoff));                        /* suba.w d3,a0 */
    dst = (uint32_t)(dst + sign_ext16(voff));                        /* adda.w d7,a0 */
    uint16_t base_col = (uint16_t)(xoff + x);                        /* add.w d0,d3 (D0 unchanged) */

    uint16_t view = (uint16_t)(be16(image + A_view_flags) >> 1);     /* view index 0..3 */
    uint8_t rows_byte = image[rec_xoff + 4 + view];                  /* move.b 4(a2,d7.w),d4 (a2=rec+8) */
    /* move.b writes only D4's low byte; the high byte keeps the rows_seed high byte, and the leaf
     * reads (int16_t)D4 — so the effective rows-1 is rows_seed's high byte over rows_byte. */
    uint16_t rows_m1 = set_low_byte(rows_seed, rows_byte);

    uint32_t dst_top = (uint32_t)(dst - sign_ext16(width));          /* movea.l a0,a2; suba.w d2,a2 */
    uint16_t height = (uint16_t)(width * rows_byte);                 /* mulu.w d4,d2 (low 16 bits used) */
    dst_top = (uint32_t)(dst_top - sign_ext16(height));             /* suba.w d2,a2 -> sprite top (A2) */

    /* The blit runs with A0 = dst (the -xoff+voff scanline base); A2/dst_top is pushed here and
     * restored to A0 only AFTER the call — it is the caller's sprite-top, not the blit's dst. */
    wr16(image + A_blit_mode, OBJH_MODE_MAIN);                       /* mode word = 8 */
    g_blit_objshift(image, x, colour, rows_m1, dst, src, A_blit_mode);

    struct obj_hi_out out = {                                        /* movem rename D3->D0, D5->D4 */
        base_col, rows_copy, dst_top,                                /* movea.l (a7)+,a0 -> sprite-top */
        (uint32_t)(src - sign_ext16(OBJH_SRC_REWIND)),              /* suba.w #0xa0,a1 */
    };
    return out;
}

/* 0x14620 glue. */
void g_draw_obj_sprite_hi(uint8_t *image, uint32_t x, uint32_t colour, uint32_t width,
                          uint32_t rows_seed, uint32_t voff, uint32_t dst, uint32_t src,
                          uint32_t rec_cursor) {
    draw_obj_sprite_hi(image, (uint16_t)x, (uint16_t)colour, (uint16_t)width, (uint16_t)rows_seed,
                       (uint16_t)voff, dst, src, rec_cursor);
}

/* 0x1465c handler: colour-preserving double draw (mode 8 pass, then mode 0xa8 tail). */
void g_draw_obj_handler_dbl(uint8_t *image, uint32_t x, uint32_t colour, uint32_t width,
                            uint32_t rows_seed, uint32_t voff, uint32_t dst, uint32_t src,
                            uint32_t rec_cursor) {
    struct obj_hi_out r = draw_obj_sprite_hi(image, (uint16_t)x, (uint16_t)colour, (uint16_t)width,
                                             (uint16_t)rows_seed, (uint16_t)voff, dst, src, rec_cursor);
    draw_obj_blit_tail(image, r.d0_x, colour, r.d4_rows, r.a0_dst, r.a1_src);   /* colour restored */
}

/* 0x14664 handler: dst from A6, src adjusted by a per-parity record word, single tail blit. */
void g_draw_obj_handler_lo(uint8_t *image, uint32_t x, uint32_t colour, uint32_t rows_m1,
                           uint32_t src, uint32_t rec_cursor, uint32_t base) {
    uint32_t dst = (uint32_t)(base + sign_ext16(OBJH_BAND_LO));      /* a6 + 0x3ac0 */
    uint16_t parity = (uint16_t)(OBJH_PARITY_MASK & be16(image + A_view_parity));   /* 0 or 2 */
    src = (uint32_t)(src + sign_ext16(be16(image + rec_cursor + 2 + parity)));      /* adda.w 2(a2,d2),a1 */
    draw_obj_blit_tail(image, x, colour, rows_m1, dst, src);
}

/* --- draw_object @0x1087e --- Scale + position the current roadside object from road_width_tbl,
 * then dispatch to the blit_obj_* variants. Scans road_width_tbl for the first visible row (a
 * negative long), walks the object's consecutive rows computing left/right screen edges (max/min)
 * and per-edge scanline offsets into the A_obj_* state block, optionally clears/paints a centre
 * band, and calls the near/far x left/right blits (plus a second "scale2" pass). A6 = draw buffer.
 * The eight blits read their inputs from registers; here we pass the matching A_obj_* fields. */
#define OBJD_SCAN_ROWS   0x5f
#define OBJD_TOP_CLEAR   0x4100      /* pre-scan clear ends here (predecrement) */
#define OBJD_TOP_ROWS    0x4a        /* pre-scan clear dbf count */
#define OBJD_TOP_LONGS   8           /* longwords cleared per pre-scan row */
#define OBJD_BAND_LONGS  10          /* longwords per scale2 clear / centre-band row (40 bytes) */
#define OBJD_BASE_ROW    0x59        /* base_off = (this - i/2) * width */
#define OBJD_CENTER_SPAN 0x6b        /* centre-band row-count derivation # ctx */
#define OBJD_CENTER_BIAS (-0x2a)     /* centre-band row-count bias (moveq #$d6 sign-extended) # ctx */
#define OBJD_CLEAR_TAIL  0xa8        /* added to the clear count when the row past the object is visible # ctx */
#define OBJD_F_LEFT      0x40000000u
#define OBJD_F_RIGHT     0x20000000u
#define OBJD_F_FAR       0x10000000u
#define OBJD_F_SCALE2    0x08000000u
#define OBJD_WIDTH       0xa0        /* D2 width for every blit */
#define OBJD_LE_BIAS     0x36        /* left-edge screen bias */
#define OBJD_RE_BIAS     0x109       /* right-edge screen bias */
#define OBJD_ROW_MAX     0xc7        /* (this - row) * width = scanline offset */
#define OBJD_VPOS_CLAMP  0x54
#define OBJD_VPOS_BIAS   0x73

static uint16_t objd_row_off(uint16_t row) {
    return (uint16_t)((uint16_t)(OBJD_ROW_MAX - row) * OBJD_WIDTH);
}
static uint16_t objd_vpos(uint16_t row, int scale2) {
    if (scale2) {
        uint16_t r = (uint16_t)(OBJD_SCAN_ROWS - row);
        return (uint16_t)(0xf + r + (r >> 1));
    }
    int16_t t = (int16_t)(OBJD_SCAN_ROWS - row);
    if (t >= OBJD_VPOS_CLAMP) t = OBJD_VPOS_CLAMP;      /* cmpi #$54; bmi keeps */
    return (uint16_t)(t + OBJD_VPOS_BIAS - row);
}
/* Write `longs` predecrement longwords per row for (rows+1) rows, alternating hi/lo (hi first). */
static uint32_t objd_fill_down(uint8_t *image, uint32_t a0, int rows, int longs, uint32_t hi, uint32_t lo) {
    for (int r = 0; r <= rows; r++)
        for (int j = 0; j < longs; j++) { a0 -= 4; wr32(image + a0, (j & 1) ? lo : hi); }
    return a0;
}

/* The centre/near fill is a two-longword (4-plane) pattern chosen by the shade sign: neutral when
 * shade == 0, else a one-plane pattern that leans left/right. Returns the pair (first, second). */
static void objd_shade_fill(int16_t shade, uint32_t *first, uint32_t *second) {
    *first = 0xffffffffu; *second = 0xffff0000u;               /* shade == 0 */
    if (shade > 0)      { *first = 0;           *second = 0x0000ffffu; }
    else if (shade < 0) { *first = 0x0000ffffu; *second = 0x0000ffffu; }
}

void g_draw_object(uint8_t *image, uint32_t buffer) {
    uint32_t a1 = A_road_width_tbl;
    int8_t byte0 = (int8_t)image[a1];
    if (byte0 < 0 && (byte0 & 8))                          /* pre-scan clear of the road band */
        objd_fill_down(image, buffer + OBJD_TOP_CLEAR, OBJD_TOP_ROWS, OBJD_TOP_LONGS, 0, 0);

    int d4 = OBJD_SCAN_ROWS;                               /* find the first visible (negative) row */
    for (;;) {
        int32_t e = (int32_t)be32(image + a1); a1 += 4;
        if (e < 0) break;
        if (d4-- == 0) return;                             /* none in 96 rows */
    }

    uint32_t obj_desc = be32(image + a1 - 4);
    wr32(image + A_obj_desc, obj_desc);
    int scale2 = (obj_desc & OBJD_F_SCALE2) != 0;
    uint16_t i = (uint16_t)(OBJD_SCAN_ROWS - d4);          /* entry index */
    wr16(image + A_obj_base_off, (uint16_t)((uint16_t)(OBJD_BASE_ROW - (i >> 1)) * OBJD_WIDTH));

    /* Walk the object's consecutive visible rows tracking the screen edges. Register map (68k names
     * kept for the byte-exact port): d5 = running max left edge, d1 = its row; d6 = running min
     * right edge, d3 = its row; rd4 = current row (counts down); d7 = 2*(extra rows); a1 = live
     * road_width_tbl cursor; a5/a2 = table entry at the winning left/right edge (far branch). */
    int16_t d5 = -1000, d6 = 1000;
    int rd4 = d4, d1 = OBJD_SCAN_ROWS, d3 = OBJD_SCAN_ROWS, d7 = 0;
    uint32_t a2 = a1, a5 = a1;
    if (obj_desc & OBJD_F_FAR) {
        for (;;) {
            int16_t w = (int16_t)be16(image + a1 - 2);
            int16_t le = (int16_t)(OBJD_LE_BIAS + w + 2 * rd4);
            if ((int16_t)(d5 - le) < 0) { d5 = le; d1 = rd4; a5 = a1; }
            int16_t re = (int16_t)(OBJD_RE_BIAS + w - 2 * rd4);
            if ((int16_t)(re - d6) < 0) { d6 = re; d3 = rd4; a2 = a1; }
            if (rd4-- == 0) break;
            int32_t e = (int32_t)be32(image + a1); a1 += 4;
            if (e >= 0) break;
            d7 += 2;
        }
        d5 = (int16_t)(OBJD_LE_BIAS + d1 + (int16_t)be16(image + a5 - 2));
        d6 = (int16_t)(OBJD_RE_BIAS - d3 + (int16_t)be16(image + a2 - 2));
    } else {
        for (;;) {
            int16_t w = (int16_t)be16(image + a1 - 2);
            int16_t le = (int16_t)(OBJD_LE_BIAS + rd4 + w);
            if ((int16_t)(d5 - le) < 0) { d5 = le; d1 = rd4; }
            int16_t re = (int16_t)(OBJD_RE_BIAS - rd4 + w);
            if ((int16_t)(re - d6) < 0) { d6 = re; d3 = rd4; }
            if (rd4-- == 0) break;
            int32_t e = (int32_t)be32(image + a1); a1 += 4;
            if (e >= 0) break;
            d7 += 2;
        }
    }

    uint16_t uvar2 = (uint16_t)(rd4 + 1);
    d7 = (int)((uint16_t)(((uint16_t)d7 & 0xfffc) - 1));   /* clear-width count-1 */
    int16_t cda;                                           /* centre-band rows-1 (-1 = none) */
    int32_t nexte = (int32_t)be32(image + a1); a1 += 4;
    if (nexte < 0) {
        wr16(image + A_obj_clear_w, (uint16_t)(d7 + OBJD_CLEAR_TAIL));
        cda = -1;
    } else {
        wr16(image + A_obj_clear_w, (uint16_t)d7);
        int16_t d0 = (int16_t)((uint16_t)(OBJD_CENTER_SPAN - uvar2) >> 1);
        int16_t d2b = (int16_t)(OBJD_CENTER_BIAS - (int16_t)((uint16_t)uvar2 >> 1) + d0);
        if (d2b >= 0) d0 = (int16_t)(d0 - d2b);
        cda = (int16_t)(d0 * 4 - 1);
    }
    wr16(image + A_obj_center_rows, (uint16_t)cda);

    if (cda >= 0) {                                        /* near-pass edges (uses row uvar2) */
        int16_t w6 = (int16_t)be16(image + a1 - 6);        /* width of the first row past the object */
        wr16(image + A_obj_c_lx,   (uint16_t)(OBJD_LE_BIAS + uvar2 + w6));
        wr16(image + A_obj_c_rx,   (uint16_t)(OBJD_RE_BIAS - uvar2 + w6));
        wr16(image + A_obj_c_off,  objd_row_off(uvar2));
        wr16(image + A_obj_c_rows, objd_vpos(uvar2, scale2));
    }
    wr16(image + A_obj_lx,   (uint16_t)d5);
    wr16(image + A_obj_l_off, objd_row_off((uint16_t)d1));
    wr16(image + A_obj_l_rows, objd_vpos((uint16_t)d1, scale2));
    wr16(image + A_obj_rx,   (uint16_t)d6);
    wr16(image + A_obj_r_off, objd_row_off((uint16_t)d3));
    wr16(image + A_obj_r_rows, objd_vpos((uint16_t)d3, scale2));

    if (scale2) {                                          /* clear the road band + paint centre */
        uint32_t a0 = buffer + be16(image + A_obj_base_off);
        int16_t clw = (int16_t)be16(image + A_obj_clear_w);
        if (clw >= 0) a0 = objd_fill_down(image, a0, clw, OBJD_BAND_LONGS, 0, 0);
        if (cda >= 0) {
            uint32_t hi, lo;
            objd_shade_fill((int16_t)be16(image + A_obj_shade), &hi, &lo);
            objd_fill_down(image, a0, cda, OBJD_BAND_LONGS, lo, hi);   /* d1(lo) written first, then d0(hi) */
        }
    }

    /* --- first pass: left and/or right, near or far --- */
    uint32_t fill_lo = (obj_desc & OBJD_F_SCALE2) ? 0 : 0xffffffffu, fill_hi = 0;
    if (obj_desc & OBJD_F_LEFT) {
        if (!(obj_desc & OBJD_F_FAR)) {
            g_blit_obj_Ln(image, buffer, OBJD_WIDTH, be16(image + A_obj_l_off), be16(image + A_obj_lx),
                          fill_lo, fill_hi, be16(image + A_obj_l_rows));
            if (!(obj_desc & OBJD_F_SCALE2))
                g_blit_obj_Ln2(image, buffer, OBJD_WIDTH, fill_lo, fill_hi);
        } else {
            g_blit_obj_Lf(image, buffer, OBJD_WIDTH, be16(image + A_obj_l_off), be16(image + A_obj_lx),
                          fill_lo, fill_hi, be16(image + A_obj_l_rows));
            g_blit_obj_Lf2(image, buffer, OBJD_WIDTH, fill_lo, fill_hi);
        }
    }
    if (obj_desc & OBJD_F_RIGHT) {
        if (!(obj_desc & OBJD_F_FAR)) {
            g_blit_obj_Rn(image, buffer, OBJD_WIDTH, be16(image + A_obj_r_off), be16(image + A_obj_rx),
                          fill_lo, fill_hi, be16(image + A_obj_r_rows));
            if (!(obj_desc & OBJD_F_SCALE2))
                g_blit_obj_Rn2(image, buffer, OBJD_WIDTH, fill_lo, fill_hi);
        } else {
            g_blit_obj_Rf(image, buffer, OBJD_WIDTH, be16(image + A_obj_r_off), be16(image + A_obj_rx),
                          fill_lo, fill_hi, be16(image + A_obj_r_rows));
            g_blit_obj_Rf2(image, buffer, OBJD_WIDTH, fill_lo, fill_hi);
        }
    }
    if (cda < 0) return;

    /* --- second (near-object) pass --- shared offset/rows, shade-selected fill. */
    uint32_t f2_lo, f2_hi;
    objd_shade_fill((int16_t)be16(image + A_obj_shade), &f2_lo, &f2_hi);
    uint16_t c_off = be16(image + A_obj_c_off), c_rows = be16(image + A_obj_c_rows);
    if (obj_desc & OBJD_F_LEFT) {
        if (!(obj_desc & OBJD_F_FAR))
            g_blit_obj_Ln(image, buffer, OBJD_WIDTH, c_off, be16(image + A_obj_c_lx), f2_lo, f2_hi, c_rows);
        else
            g_blit_obj_Lf(image, buffer, OBJD_WIDTH, c_off, be16(image + A_obj_c_lx), f2_lo, f2_hi, c_rows);
    }
    if (obj_desc & OBJD_F_RIGHT) {
        if (!(obj_desc & OBJD_F_FAR))
            g_blit_obj_Rn(image, buffer, OBJD_WIDTH, c_off, be16(image + A_obj_c_rx), f2_lo, f2_hi, c_rows);
        else
            g_blit_obj_Rf(image, buffer, OBJD_WIDTH, c_off, be16(image + A_obj_c_rx), f2_lo, f2_hi, c_rows);
    }
}
