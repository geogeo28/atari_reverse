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
#include "draw.h"     /* dup16 (shared 68k swap+move.w idiom) */

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

/* Which sprite family the aligned column selects (spec §3). */
enum objsh_family { OBJSH_CLIP, OBJSH_BASE, OBJSH_LEFT, OBJSH_RIGHT };

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

/* Parameterized width-family core. `base_cells` = the number of straddle cells a fully-on-screen
 * (BASE) sprite draws; it selects the width family and its dispatch thresholds:
 *   base_cells==1 -> the 0x14680 entry (base ceiling 0x98; only LEFT-1/BASE/RIGHT-1 reachable).
 *   base_cells==2 -> the 0x144ac entry (base ceiling 0x90; 2-cell base, LEFT-2/RIGHT-2 reachable).
 * The 68000 packs these as separate entry points into ONE unrolled blitter (BLIT_OBJSHIFT_SPEC.md §5),
 * the wider entries walking further down the shared LEFT/RIGHT clip ladders. Collapsed to one loop:
 *   LEFT   (aligned_col < 0):        k = clipped leading columns = -A/8; s = base_cells - k straddles
 *          after an a2-only lead edge, and the k-1 fully-clipped columns are skipped (a0/a1 += 8 each,
 *          the ladder's addq.l). k > base_cells -> off the left edge, no draw.
 *   RIGHT  (aligned_col >= ceiling): s = (RIGHT_BOUND - A)/8 straddles before an a0-only trail edge;
 *          s < 0 -> off the right edge, no draw. (RIGHT_BOUND is the absolute screen bound, 0x98.)
 *   BASE   (0 <= A < ceiling):       base_cells straddles, no edge.
 * Per row: Δa0=Δa2 = ROW_REWIND + 8*(total_cells-1), a1 also rewinds by the (a3) stride + 8*(total_cells-1).
 * a0/a1/a3 are image offsets read/written like blit.c's other glue; color_pairs is real image data. */
static void blit_objshift_family(uint8_t *image, uint32_t x, uint32_t color, uint32_t rows_m1,
                                 uint32_t dst, uint32_t src, uint32_t stride_ptr, int base_cells) {
    unsigned fine_x = (unsigned)(x & OBJSH_NIBBLE);           /* from the ORIGINAL x, before asr */
    unsigned shl = OBJSH_SUBPX_BITS - fine_x;                 /* d6 = 16 - fine_x */
    unsigned shr = fine_x;                                    /* d7 = fine_x */

    uint16_t col_off = (uint16_t)((color & OBJSH_NIBBLE) << 3);
    uint32_t fill_lo = load32(image, A_color_pairs + col_off);        /* d3: planes 0,1 */
    uint32_t fill_hi = load32(image, A_color_pairs + col_off + 4);    /* d5: planes 2,3 */

    int16_t A = (int16_t)aligned_col((uint16_t)x);
    int16_t base_ceiling = (int16_t)(OBJSH_RIGHT_BOUND - OBJSH_CELL_BYTES * (base_cells - 1));

    enum objsh_family fam;
    int straddle, skips = 0;
    if (A < 0) {
        int k = (int)(-A) / OBJSH_CELL_BYTES;                 /* clipped-off leading columns */
        if (k > base_cells) return;                           /* off the left edge -> rts */
        fam = OBJSH_LEFT; straddle = base_cells - k; skips = k - 1;
    } else if ((int16_t)(A - base_ceiling) >= 0) {
        int s = (OBJSH_RIGHT_BOUND - A) / OBJSH_CELL_BYTES;
        if (s < 0) return;                                    /* off the right edge -> rts */
        fam = OBJSH_RIGHT; straddle = s;
    } else {
        fam = OBJSH_BASE; straddle = base_cells;
    }

    /* Rewind's `s` term is total_cells-1 in every body (BASE: base_cells; LEFT/RIGHT: straddle+edge). */
    int total_cells = straddle + (fam == OBJSH_BASE ? 0 : 1);
    uint16_t rewind = (uint16_t)(OBJSH_ROW_REWIND + OBJSH_CELL_BYTES * (total_cells - 1));
    uint16_t a1_extra = (uint16_t)(OBJSH_CELL_BYTES * (total_cells - 1));
    int rows = (int16_t)rows_m1 + 1;

    uint32_t a1 = src + (uint32_t)(OBJSH_CELL_BYTES * skips);            /* ladder's addq.l #8,a1 */
    uint32_t a0 = (dst + sign_ext16((uint16_t)A)) + (uint32_t)(OBJSH_CELL_BYTES * skips);
    uint32_t a2 = a0 + OBJSH_CELL_BYTES;                     /* movea.l a0,a2; addq.l #8,a2 (once) */
    for (int row = 0; row < rows; row++) {
        objsh_row(image, &a0, &a2, &a1, fam, straddle, shl, shr, fill_lo, fill_hi);
        a0 = (uint32_t)(a0 - sign_ext16(rewind));            /* suba.w #Δ,a0 (a2 tracks a0+8) */
        a2 = (uint32_t)(a2 - sign_ext16(rewind));            /* suba.w #Δ,a2 */
        a1 = (uint32_t)(a1 - sign_ext16(be16(image + stride_ptr)));   /* suba.w (a3),a1 */
        a1 = (uint32_t)(a1 - sign_ext16(a1_extra));                   /* suba.w #extra,a1 */
    }
}

/* 0x14680 entry — the "0x98" width family (base draws one straddle cell). Register map: D0 x,
 * D1 colour, D4 rows-1, A0 dst, A1 src, A3 stride_ptr. */
void g_blit_objshift(uint8_t *image, uint32_t x, uint32_t color, uint32_t rows_m1,
                     uint32_t dst, uint32_t src, uint32_t stride_ptr) {
    blit_objshift_family(image, x, color, rows_m1, dst, src, stride_ptr, /*base_cells=*/1);
}

/* 0x144ac entry — the "0x90" width family (base draws two straddle cells). Same register ABI; used
 * by the wider roadside-object types dispatched through draw_object_list's jump table. */
void g_blit_objshift_w2(uint8_t *image, uint32_t x, uint32_t color, uint32_t rows_m1,
                        uint32_t dst, uint32_t src, uint32_t stride_ptr) {
    blit_objshift_family(image, x, color, rows_m1, dst, src, stride_ptr, /*base_cells=*/2);
}

/* ============================================================================================
 * blit_objshift2 @ 0x13ed6 — the SECOND sub-pixel (fine-x shifted) 4-plane masked sprite blitter,
 * used by the roadside object-type handlers (the 0x13e68 family calls it via the 0x13e8e glue).
 *
 * DISTINCT from g_blit_objshift @ 0x14680 above: its transparency "show" mask is built from only
 * TWO source words (~(w0 | w1)), it never loads color_pairs, and the pixel copy is a plain shifted
 * OR (no colour indexing / fill). PURE LEAF. See BLIT_OBJSHIFT2_SPEC.md for the full byte decode.
 *
 * a0 = col0 (left dst column), a2 = col1 = a0 + 8. Every case is built from three cell primitives
 * that all mask with ~(w0|w1) of two source words: a STRADDLE cell (both columns, 32-bit lsl/rol by
 * shl = 16-fine_x), a LEFT-EDGE cell (col1 only, 16-bit lsl by shl), and a RIGHT-EDGE cell (col0
 * only, 16-bit lsr by shr = fine_x). Width dispatch on the signed aligned column picks the family:
 *   aligned_col <= -32 or >= 0xa0 -> off-screen, no draw.
 *   LEFT  (-24/-16/-8): 1 LE-cell + {0,1,2} straddle cells.
 *   BASE  (0..0x80):    3 straddle cells.
 *   WIDE  (0x88/0x90/0x98): {2,1,0} straddle cells + 1 RE-cell.
 * All cases net a0 -= 0xA0 (one scanline up) and a1 -= 0x50 (sprite src stride) per row.
 * All 16-bit register arithmetic wraps mod 2^16, mirrored with explicit int16/uint16.
 */
#define OBJSH2_FINE_MASK      0x000f       /* x & 0xF -> fine_x (the RIGHT-shift count d7)        */
#define OBJSH2_SHIFT_BASE     16           /* shl = 16 - fine_x (the LEFT-shift count d6)         */
#define OBJSH2_RIGHT_BOUND    0x88         /* subi.w #$88 dispatch threshold (17 ST columns)      */
#define OBJSH2_COL_BYTES      8            /* one 4-plane 16-pixel column = 8 bytes (addq #8)     */
#define OBJSH2_MASK_INIT      0xffffffffu  /* moveq #$ff,d1 sign-extends 0xff -> all ones         */
#define OBJSH2_LADDER_STEP    8            /* addq/subq #8 step down the LEFT/RIGHT clip ladders   */
#define OBJSH2_LEFT_OFF_COL   (-32)        /* aligned_col <= this -> off the left edge, no draw    */
#define OBJSH2_RIGHT_OFF_COL  0xa0         /* aligned_col >= this -> off the right edge, no draw   */
/* Per-row rewind constants (suba.w #d3,a0/a2; suba.w #d5,a1). Kept as the literal table values
 * (d3 = 0xA0 + 8*cells, d5 = 0x50 + 4*cells) to stay byte-exact rather than derived. */
#define OBJSH2_REWIND3_DST    0xb8         /* 3 cells: BASE, L2C, W2                               */
#define OBJSH2_REWIND3_SRC    0x5c
#define OBJSH2_REWIND2_DST    0xb0         /* 2 cells: L1C, W1                                    */
#define OBJSH2_REWIND2_SRC    0x58
#define OBJSH2_REWIND1_DST    0xa8         /* 1 cell:  L0C, W0                                    */
#define OBJSH2_REWIND1_SRC    0x54

/* STRADDLE cell (0x13efc): mask = ~(w0|w1) with the high word kept 0xFFFF (moveq #$ff seed), rotated
 * left 32-bit by shl so it straddles both columns; then two plane words are lsl.l shl'd, low half OR'd
 * into col1 and high half into col0. Advances a0/a2 by 8 and a1 by 4 (the mask reads at (a1)/(a1+2)
 * do NOT advance; the two (a1)+ copies do). Mirrors the 68k register moves literally (spec §4a/§6). */
static void objsh2_straddle_cell(uint8_t *image, uint32_t *a0, uint32_t *a2, uint32_t *a1, unsigned shl) {
    uint16_t w0 = be16(image + *a1);
    uint16_t w1 = be16(image + *a1 + 2);
    uint32_t d1 = OBJSH2_MASK_INIT;                          /* moveq #$ff,d1                       */
    d1 = (d1 & 0xffff0000u) | w0;                            /* move.w (a1),d1                      */
    d1 = (d1 & 0xffff0000u) | (uint16_t)(d1 | w1);           /* or.w 2(a1),d1  (word op)            */
    d1 = (d1 & 0xffff0000u) | (uint16_t)(~d1);              /* not.w d1  -> hi word stays 0xFFFF   */
    d1 = rotl32(d1, shl);                                    /* rol.l d6,d1                         */
    uint32_t d2 = dup16((uint16_t)d1);                       /* move.w;swap;move.w -> col1 AND-mask */
    uint32_t swapped = (d1 >> 16) | (d1 << 16);              /* move.l d1,d0 ; swap d0              */
    d1 = (d1 & 0xffff0000u) | (uint16_t)swapped;             /* move.w d0,d1 -> col0 AND-mask       */
    store32(image, *a0, load32(image, *a0) & d1);            /* and.l d1,(a0)                       */
    store32(image, *a2, load32(image, *a2) & d2);            /* and.l d2,(a2)                       */

    for (int i = 0; i < 2; i++) {                            /* two plane words, low -> col1, hi -> col0 */
        uint32_t pix = (uint32_t)be16(image + *a1) << shl;   /* moveq #0,d0; move.w (a1)+,d0; lsl.l d6 */
        *a1 += 2;
        wr16(image + *a2, (uint16_t)(be16(image + *a2) | (uint16_t)pix));        /* or.w d0,(a2)+   */
        wr16(image + *a0, (uint16_t)(be16(image + *a0) | (uint16_t)(pix >> 16)));/* swap; or.w (a0)+ */
        *a0 += 2; *a2 += 2;
    }
    /* trailing "opaque fill outside the show mask" longword for each column: dst = (dst & m) | ~m. */
    store32(image, *a0, (load32(image, *a0) & d1) | ~d1);    /* and.l d1,(a0); or.l ~d1,(a0)+       */
    *a0 += 4;
    store32(image, *a2, (load32(image, *a2) & d2) | ~d2);    /* and.l d2,(a2); or.l ~d2,(a2)+       */
    *a2 += 4;
}

/* LEFT-EDGE cell (0x1411c): the clipped-off left column is discarded; only col1 (a2) is drawn. The
 * mask is (w1|w0) shifted LEFT as a WORD by shl, inverted; pixels shift left as words (no straddle).
 * Advances a1 by 4, a2 by 8, and bumps a0 by 8 past the discarded column. Mirrors 68k moves (§4b). */
static void objsh2_left_edge_cell(uint8_t *image, uint32_t *a0, uint32_t *a2, uint32_t *a1, unsigned shl) {
    uint32_t both = load32(image, *a1);                      /* move.l (a1),d0 = (w0<<16)|w1        */
    uint16_t lo = (uint16_t)((uint16_t)both | be16(image + *a1)); /* or.w (a1)+,d0 -> lo = w1|w0    */
    *a1 += 2;
    uint16_t mask = (uint16_t)(~(uint16_t)(lo << shl));      /* lsl.w d6,d0 ; not.w d0             */
    uint32_t d2 = dup16(mask);                               /* dup16 -> col1 AND-mask             */
    store32(image, *a2, load32(image, *a2) & d2);            /* and.l d2,(a2)                       */
    uint16_t w0 = (uint16_t)(both >> 16);                    /* swap d0 -> old high half (w0)       */
    wr16(image + *a2, (uint16_t)(be16(image + *a2) | (uint16_t)(w0 << shl)));    /* lsl.w; or.w (a2)+ */
    *a2 += 2;
    uint16_t w1 = be16(image + *a1);                         /* move.w (a1)+,d0                     */
    *a1 += 2;
    wr16(image + *a2, (uint16_t)(be16(image + *a2) | (uint16_t)(w1 << shl)));    /* lsl.w; or.w (a2)+ */
    *a2 += 2;
    store32(image, *a2, (load32(image, *a2) & d2) | ~d2);    /* and.l d2,(a2); or.l ~d2,(a2)+       */
    *a2 += 4;
    *a0 += OBJSH2_COL_BYTES;                                 /* addq.l #8,a0 (skip discarded column)*/
}

/* RIGHT-EDGE cell (0x142b6): the clipped-off right column is discarded; only col0 (a0) is drawn. The
 * mask is (w1|w0) shifted RIGHT as a WORD by shr = fine_x, inverted; pixels shift right as words.
 * Advances a1 by 4, a0 by 8, and bumps a2 by 8 to keep the shared rewind correct. (§4c). */
static void objsh2_right_edge_cell(uint8_t *image, uint32_t *a0, uint32_t *a2, uint32_t *a1, unsigned shr) {
    uint32_t both = load32(image, *a1);                      /* move.l (a1),d0 = (w0<<16)|w1        */
    uint16_t lo = (uint16_t)((uint16_t)both | be16(image + *a1)); /* or.w (a1)+,d0 -> lo = w1|w0    */
    *a1 += 2;
    uint16_t mask = (uint16_t)(~(uint16_t)(lo >> shr));      /* lsr.w d7,d0 ; not.w d0             */
    uint32_t d1 = dup16(mask);                               /* dup16 -> col0 AND-mask             */
    store32(image, *a0, load32(image, *a0) & d1);            /* and.l d1,(a0)                       */
    uint16_t w0 = (uint16_t)(both >> 16);                    /* swap d0 -> old high half (w0)       */
    wr16(image + *a0, (uint16_t)(be16(image + *a0) | (uint16_t)(w0 >> shr)));    /* lsr.w; or.w (a0)+ */
    *a0 += 2;
    uint16_t w1 = be16(image + *a1);                         /* move.w (a1)+,d0                     */
    *a1 += 2;
    wr16(image + *a0, (uint16_t)(be16(image + *a0) | (uint16_t)(w1 >> shr)));    /* lsr.w; or.w (a0)+ */
    *a0 += 2;
    store32(image, *a0, (load32(image, *a0) & d1) | ~d1);    /* and.l d1,(a0); or.l ~d1,(a0)+       */
    *a0 += 4;
    *a2 += OBJSH2_COL_BYTES;                                 /* addq.l #8,a2 (rewind bookkeeping)   */
}

/* Which family the signed aligned column selects (spec §3). Every listed case is reachable. */
enum objsh2_edge { OBJSH2_EDGE_NONE, OBJSH2_EDGE_LEFT, OBJSH2_EDGE_RIGHT };

/* Run one row: LEFT prepends a LE-cell, WIDE appends a RE-cell, all around `straddle` S-cells. */
static void objsh2_row(uint8_t *image, uint32_t *a0, uint32_t *a2, uint32_t *a1,
                       enum objsh2_edge edge, int straddle, unsigned shl, unsigned shr) {
    if (edge == OBJSH2_EDGE_LEFT)
        objsh2_left_edge_cell(image, a0, a2, a1, shl);
    for (int i = 0; i < straddle; i++)
        objsh2_straddle_cell(image, a0, a2, a1, shl);
    if (edge == OBJSH2_EDGE_RIGHT)
        objsh2_right_edge_cell(image, a0, a2, a1, shr);
}

/* Glue: map the 68000 register ABI to the row loop. a0/a1 are image offsets read/written like the
 * other blit.c glue. Register map: D0 x, D4 rows-1, A0 dst scanline base, A1 src sprite stream.
 * (d3/d5 are internal rewind constants owned by the leaf, not inputs; the caller's d3 is the glue's
 * outer column-group counter, external to this leaf.) */
void g_blit_objshift2(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t dst, uint32_t src) {
    unsigned fine_x = (unsigned)(x & OBJSH2_FINE_MASK);      /* d7 = x & 0xF (before the asr)       */
    unsigned shl = OBJSH2_SHIFT_BASE - fine_x;               /* d6 = 16 - fine_x                    */
    unsigned shr = fine_x;                                   /* d7 = fine_x                         */

    /* aligned_col = ((int16)x >> 1) & 0xFFF8; the signed value (post-add into a0) drives dispatch. */
    int16_t col = (int16_t)((int16_t)(uint16_t)x >> 1) & (int16_t)COL_ALIGN;
    uint32_t a0 = (uint32_t)(dst + sign_ext16((uint16_t)col));
    uint32_t a1 = src;

    enum objsh2_edge edge;
    int straddle;
    uint16_t rewind_dst, rewind_src;

    if (col < 0) {
        /* LEFT ladder (0x14104): walk forward over fully-clipped columns until the first partial. */
        int16_t c = col;
        for (;;) {
            c = (int16_t)(c + OBJSH2_LADDER_STEP);
            if (c >= 0) { straddle = 2; break; }             /* aligned_col == -8  -> L2C           */
            a1 += 4; a0 += OBJSH2_COL_BYTES;                 /* skip one fully-clipped column       */
            c = (int16_t)(c + OBJSH2_LADDER_STEP);
            if (c >= 0) { straddle = 1; break; }             /* aligned_col == -16 -> L1C           */
            a1 += 4; a0 += OBJSH2_COL_BYTES;
            c = (int16_t)(c + OBJSH2_LADDER_STEP);
            if (c >= 0) { straddle = 0; break; }             /* aligned_col == -24 -> L0C           */
            return;                                          /* aligned_col <= -32 -> off left, no draw */
        }
        edge = OBJSH2_EDGE_LEFT;
    } else if ((int16_t)(col - OBJSH2_RIGHT_BOUND) >= 0) {
        /* RIGHT/WIDE ladder (0x1429c): d0 = aligned_col - 0x88 on entry. */
        int16_t c = (int16_t)(col - OBJSH2_RIGHT_BOUND);
        c = (int16_t)(c - OBJSH2_LADDER_STEP);
        if (c < 0) straddle = 2;                             /* aligned_col == 0x88 -> W2           */
        else {
            c = (int16_t)(c - OBJSH2_LADDER_STEP);
            if (c < 0) straddle = 1;                         /* aligned_col == 0x90 -> W1           */
            else {
                c = (int16_t)(c - OBJSH2_LADDER_STEP);
                if (c < 0) straddle = 0;                     /* aligned_col == 0x98 -> W0           */
                else return;                                 /* aligned_col >= 0xa0 -> off right     */
            }
        }
        edge = OBJSH2_EDGE_RIGHT;
    } else {
        edge = OBJSH2_EDGE_NONE;                             /* BASE: 0 <= aligned_col <= 0x80       */
        straddle = 3;
    }

    /* Rewind constants keyed on the number of cells per row (edge cell counts as one column pair). */
    int cells = straddle + (edge == OBJSH2_EDGE_NONE ? 0 : 1);
    switch (cells) {
        case 3: rewind_dst = OBJSH2_REWIND3_DST; rewind_src = OBJSH2_REWIND3_SRC; break;
        case 2: rewind_dst = OBJSH2_REWIND2_DST; rewind_src = OBJSH2_REWIND2_SRC; break;
        default: rewind_dst = OBJSH2_REWIND1_DST; rewind_src = OBJSH2_REWIND1_SRC; break;
    }

    uint32_t a2 = a0 + OBJSH2_COL_BYTES;                     /* movea.l a0,a2; addq.l #8,a2 (once)  */
    int rows = (int16_t)rows_m1 + 1;                         /* dbf d4 counts d4+1 rows             */
    for (int row = 0; row < rows; row++) {
        objsh2_row(image, &a0, &a2, &a1, edge, straddle, shl, shr);
        a0 = (uint32_t)(a0 - sign_ext16(rewind_dst));        /* suba.w #d3,a0                       */
        a2 = (uint32_t)(a2 - sign_ext16(rewind_dst));        /* suba.w #d3,a2                       */
        a1 = (uint32_t)(a1 - sign_ext16(rewind_src));        /* suba.w #d5,a1                       */
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

/* ============================================================================================
 * Shared object-sprite blit engine @ 0x131f6..0x13df8 — the SIBLING of g_blit_objshift2 above.
 *
 * ONE parameterized fine-x-shifted 4-plane masked-transparency sprite blitter with ~18 alternate
 * entry points (each roadside object-type handler presets a width bound + base cell count then
 * joins the shared body). Same three-primitive shell as objshift2 (STRADDLE / LEFT-EDGE /
 * RIGHT-EDGE), same a0=col0 / a2=a0+8=col1 pairing, same per-row `suba.w d3,{a0,a2,a1}; dbf`
 * rewind. It differs from objshift2 in exactly two ways:
 *   (a) the transparency SHOW mask is built from FOUR source words `~(w0|w1|w2|~w3)` (= the
 *       objsh_build_mask / blit_transp_cell formula) instead of two, and
 *   (b) there is NO colour indexing — pixels are copied plain-shifted and OR'd, no color_pairs
 *       and no d3/d5 colour AND (contrast g_blit_objshift @ 0x14680).
 * The mask SEED here is `moveq #$ff,d2` = 0xFFFFFFFF (0xFF sign-extends: HIGH word 0xFFFF going
 * into rol.l/lsr.l, exactly like g_blit_objshift's objsh_build_mask) — `move.w (a1),d2` then sets
 * only the low word to the show mask. (The OBJ_BLIT_ENGINE_SPEC CORRECTION 1 claiming a 0x0000 high
 * word is wrong: 0xFF is a negative signed byte, so moveq sign-extends it — verified vs the oracle.)
 *
 * PURE LEAF. Writes only the draw buffer via A0/A2, reads sprite words from A1. See
 * OBJ_BLIT_ENGINE_SPEC.md for the full byte decode of all four width families + the 18 entries.
 * All 16-bit register arithmetic wraps mod 2^16, mirrored with explicit int16/uint16.
 */
#define OBJSPRITE_FINE_MASK   0x000f       /* d7 = x & 0xF -> fine_x (the RIGHT-shift count)       */
#define OBJSPRITE_SHIFT_BASE  16           /* d6 = 16 - fine_x (the LEFT-shift count)              */
#define OBJSPRITE_COL_ALIGN   0xfff8       /* aligned_col = ((int16)x >> 1) & this                 */
#define OBJSPRITE_CELL_BYTES  8            /* one 4-plane 16-pixel column = 8 bytes (addq #8)      */
#define OBJSPRITE_PLANES      4            /* four plane words per cell (the extra vs objshift2)   */
#define OBJSPRITE_LADDER_STEP 8            /* addq/subq #8 step down the LEFT/WIDE clip ladders    */
#define OBJSPRITE_WIDTHS      4            /* four width families (0x80/0x88/0x90/0x98)            */
/* Width bounds and per-body rewind constants, indexed by width_idx = (WIDTH - 0x80) / 8. Kept as
 * the literal table values (the body's `move.w #d3,d3`) to stay byte-exact, not derived. */
#define OBJSPRITE_WIDTH_80    0x80         /* width_idx 0: BASE d3 0xC0, 4 straddle cells          */
#define OBJSPRITE_WIDTH_98    0x98         /* width_idx 3: BASE d3 0xA8, 1 straddle cell           */
#define OBJSPRITE_REWIND_C0   0xc0         /* per-row rewind for a 4-cell row (BASE w0x80 / 3-strad L/W) */
#define OBJSPRITE_BASE_CELLS  4            /* BASE straddle cells for width_idx 0 (4 - width_idx)  */
/* Helper 0x145fc (view-transform) masks. `moveq #$e0,d3` sign-extends to 0xFFFFFFE0, so the
 * `and.w (a3),d3` masks the record word with the WORD 0xFFE0 (NOT 0x00E0 — the spec CORRECTION 5
 * is wrong; verified vs the oracle: a0 gains word[1] & 0xFFE0, sign-extended by the adda.w). */
#define VIEW_XFORM_OFF_MASK   0xffe0       /* record word[1] & this (sign-extended) -> a0 nudge   */
#define VIEW_XFORM_ROW_MASK   0x001f       /* record word[1] & this -> row-count clip (moveq #$1f) */

/* aligned_col = ((int16)x >> 1) & 0xFFF8 (COL_ALIGN clears the low 3 bits = 8-byte column). */
static uint16_t objsprite_aligned_col(uint16_t x) {
    return (uint16_t)((int16_t)(uint16_t)x >> 1) & (uint16_t)OBJSPRITE_COL_ALIGN;
}

/* Build the cell's 32-bit mask SEED from the four plane words at a1. The 68k `moveq #$ff,d2`
 * sign-extends 0xFF (a negative signed byte) to 0xFFFFFFFF, so the mask longword's HIGH word is
 * 0xFFFF; `move.w (a1),d2` then overwrites only the low word with the SHOW mask ~(w0|w1|w2|~w3)
 * = ~w0 & ~w1 & ~w2 & w3. The 0xFFFF high word is load-bearing: it rotates/shifts into the OTHER
 * 16-pixel column. This is the identical seed + formula as objsh_build_mask (0x14680). */
static uint32_t objsprite_mask_seed(const uint8_t *image, uint32_t a1) {
    return objsh_build_mask(image, a1);      /* 0xffff0000 | (uint16_t)(~(w0|w1|w2) & w3) */
}

/* Masked OR-in of one plane word into a destination column word (68k `and.w mask,(ptr)` then
 * `or.w pix,(ptr)`): keep the background where the mask is set, drop in the shifted pixels. */
static void objsprite_plane_write(uint8_t *image, uint32_t ptr, uint16_t mask, uint16_t pix) {
    wr16(image + ptr, (uint16_t)((be16(image + ptr) & mask) | pix));
}

/* STRADDLE cell (§3b, e.g. 0x321a): writes BOTH columns. mask32 = rotl32(build_mask, shl) where
 * build_mask carries a 0xFFFF high word (the moveq #$ff seed) that rotates into the straddled
 * column; high half gates col0 (a0), low half gates col1 (a2). Each of the four plane
 * words is 32-bit left-shifted by shl: high half -> col0, low half -> col1, and every output word
 * keeps the background via (dst & mask). Plane 3 (the D leftover) additionally masks its pixels
 * with ~mask so it lights only the opaque bits. Advances a0/a2/a1 by one cell (8 bytes). */
static void objsprite_straddle_cell(uint8_t *image, uint32_t *a0, uint32_t *a2, uint32_t *a1, unsigned shl) {
    uint32_t mask32 = rotl32(objsprite_mask_seed(image, *a1), shl);
    uint16_t col0_mask = (uint16_t)(mask32 >> OBJSPRITE_SHIFT_BASE);   /* swap d1 -> col0 (a0) mask */
    uint16_t col1_mask = (uint16_t)mask32;                            /* d2.w -> col1 (a2) mask    */
    for (int plane = 0; plane < OBJSPRITE_PLANES; plane++) {
        uint32_t pix32 = (uint32_t)be16(image + *a1) << shl;
        *a1 += 2;
        uint16_t col1_pix = (uint16_t)pix32;
        uint16_t col0_pix = (uint16_t)(pix32 >> OBJSPRITE_SHIFT_BASE);
        if (plane == OBJSPRITE_PLANES - 1) {                          /* D leftover: pixels &= ~mask */
            col1_pix = (uint16_t)(col1_pix & (uint16_t)~col1_mask);
            col0_pix = (uint16_t)(col0_pix & (uint16_t)~col0_mask);
        }
        objsprite_plane_write(image, *a2, col1_mask, col1_pix);       /* col1 first (or.w d0,(a2)+) */
        objsprite_plane_write(image, *a0, col0_mask, col0_pix);
        *a0 += 2; *a2 += 2;
    }
}

/* LEFT-EDGE cell (§3c, 0x36fc): the clipped-off col0 is discarded; only col1 (a2) is drawn. The
 * mask is rol.l'd but only its low word (d2.w) is used; pixels shift left as WORDs (lsl.w, no
 * straddle spill). Plane 3 uses the inverse mask. Advances a1/a2 by 8; the caller bumps a0 +8. */
static void objsprite_left_edge_cell(uint8_t *image, uint32_t *a2, uint32_t *a1, unsigned shl) {
    uint16_t mask = (uint16_t)rotl32(objsprite_mask_seed(image, *a1), shl);
    for (int plane = 0; plane < OBJSPRITE_PLANES; plane++) {
        uint16_t pix = (uint16_t)((uint32_t)be16(image + *a1) << shl);  /* lsl.w d6,d0 (word shift) */
        *a1 += 2;
        if (plane == OBJSPRITE_PLANES - 1) pix = (uint16_t)(pix & (uint16_t)~mask);
        objsprite_plane_write(image, *a2, mask, pix);
        *a2 += 2;
    }
}

/* RIGHT-EDGE cell (§3d, 0x3a8a): the clipped-off col1 is discarded; only col0 (a0) is drawn. The
 * mask is lsr.l'd by shr = fine_x (low word used); pixels shift right as WORDs (lsr.w). Plane 3
 * uses the inverse mask. Advances a1/a0 by 8; the caller bumps a2 +8. */
static void objsprite_right_edge_cell(uint8_t *image, uint32_t *a0, uint32_t *a1, unsigned shr) {
    uint16_t mask = (uint16_t)(objsprite_mask_seed(image, *a1) >> shr);
    for (int plane = 0; plane < OBJSPRITE_PLANES; plane++) {
        uint16_t pix = (uint16_t)(be16(image + *a1) >> shr);            /* lsr.w d7,d0 (word shift) */
        *a1 += 2;
        if (plane == OBJSPRITE_PLANES - 1) pix = (uint16_t)(pix & (uint16_t)~mask);
        objsprite_plane_write(image, *a0, mask, pix);
        *a0 += 2;
    }
}

/* Which family the signed aligned column selects (§2 dispatch). */
enum objsprite_family { OBJSPRITE_CLIP, OBJSPRITE_BASE, OBJSPRITE_LEFT, OBJSPRITE_WIDE };

/* One row: LEFT prepends an a2-only edge cell (then re-syncs a0 by one cell), WIDE appends an
 * a0-only edge cell (then bumps a2 by one cell); `straddle` two-column cells run between/around
 * them (BASE has neither edge). Mirrors §3b/§3c/§3d cell order per family (§4/§5b/§6b). */
static void objsprite_row(uint8_t *image, uint32_t *a0, uint32_t *a2, uint32_t *a1,
                          enum objsprite_family fam, int straddle, unsigned shl, unsigned shr) {
    if (fam == OBJSPRITE_LEFT) {
        objsprite_left_edge_cell(image, a2, a1, shl);
        *a0 += OBJSPRITE_CELL_BYTES;                 /* addq.l #8,a0: skip the discarded col0 */
    }
    for (int i = 0; i < straddle; i++)
        objsprite_straddle_cell(image, a0, a2, a1, shl);
    if (fam == OBJSPRITE_WIDE) {
        objsprite_right_edge_cell(image, a0, a1, shr);
        *a2 += OBJSPRITE_CELL_BYTES;                 /* addq.l #8,a2: rewind bookkeeping */
    }
}

/* The shared parameterized core (§2 dispatch + §4/§5/§6 bodies). `width_idx` = (WIDTH - 0x80)/8
 * selects the width bound (WIDTH = 0x80 + 8*width_idx) and the entry rung of both clip ladders.
 * a0_pre = the dst base AFTER `adda.w aligned_col,a0` (the alt entry 0x13204 supplies this and the
 * pre-decoded shl/shr/aligned_col directly). Per-row rewind d3 = 0xC0 - 8*(cells drawn beyond one),
 * modeled as the literal `move.w #d3,d3` each body loads: d3 = 0xC0 - 8*width_idx for BASE, and
 * d3 = 0xC0 - 8*rung for the ladder body that fired (rung = the ladder step that triggered). */
static void objsprite_core(uint8_t *image, uint16_t aligned_col, unsigned shl, unsigned shr,
                           uint16_t rows_m1, uint32_t a0_pre, uint32_t a1_init, int width_idx) {
    uint32_t a0 = a0_pre;
    uint32_t a1 = a1_init;
    enum objsprite_family fam;
    int straddle;
    int rung;                            /* ladder step that fired; d3 = 0xC0 - 8*rung */

    if ((int16_t)aligned_col < 0) {
        /* §5a LEFT ladder: walk toward 0 in 8-byte steps from the width's entry rung; each
         * non-triggering rung discards one fully-clipped column from a1 AND a0. */
        int16_t d0 = (int16_t)aligned_col;
        fam = OBJSPRITE_CLIP;
        for (rung = width_idx; rung < OBJSPRITE_WIDTHS; rung++) {
            d0 = (int16_t)(d0 + OBJSPRITE_LADDER_STEP);
            if (d0 >= 0) { fam = OBJSPRITE_LEFT; break; }
            a1 += OBJSPRITE_CELL_BYTES;
            a0 += OBJSPRITE_CELL_BYTES;
        }
        if (fam == OBJSPRITE_CLIP) return;           /* fully off-left: draw nothing (rts) */
        straddle = (OBJSPRITE_WIDTHS - 1) - rung;    /* bodies 0x36f4/0x3742/0x37f0/0x38fe = 0/1/2/3 */
    } else {
        int16_t width = (int16_t)(OBJSPRITE_WIDTH_80 + OBJSPRITE_LADDER_STEP * width_idx);
        int16_t d0 = (int16_t)((int16_t)aligned_col - width);
        if (d0 < 0) {
            fam = OBJSPRITE_BASE;
            straddle = OBJSPRITE_BASE_CELLS - width_idx;   /* 4/3/2/1 straddle cells */
            rung = width_idx;                              /* BASE d3 = 0xC0 - 8*width_idx */
        } else {
            /* §6a WIDE ladder: subtract 8 per rung from the width's entry rung; no column skip. */
            fam = OBJSPRITE_CLIP;
            for (rung = width_idx; rung < OBJSPRITE_WIDTHS; rung++) {
                d0 = (int16_t)(d0 - OBJSPRITE_LADDER_STEP);
                if (d0 < 0) { fam = OBJSPRITE_WIDE; break; }
            }
            if (fam == OBJSPRITE_CLIP) return;             /* fully off-right: draw nothing (rts) */
            straddle = (OBJSPRITE_WIDTHS - 1) - rung;      /* bodies 0x3a82/0x3ad0/0x3b7e/0x3c8c */
        }
    }

    uint16_t d3 = (uint16_t)(OBJSPRITE_REWIND_C0 - OBJSPRITE_LADDER_STEP * rung);   /* move.w #d3,d3 */
    uint32_t a2 = a0 + OBJSPRITE_CELL_BYTES;             /* movea.l a0,a2; addq.l #8,a2 (once) */
    int rows = (int16_t)rows_m1 + 1;                     /* dbf d4 draws d4+1 rows */
    for (int row = 0; row < rows; row++) {
        objsprite_row(image, &a0, &a2, &a1, fam, straddle, shl, shr);
        a0 = (uint32_t)(a0 - sign_ext16(d3));            /* suba.w d3,a0 */
        a2 = (uint32_t)(a2 - sign_ext16(d3));            /* suba.w d3,a2 */
        a1 = (uint32_t)(a1 - sign_ext16(d3));            /* suba.w d3,a1 */
    }
}

/* The fine-x prologue (§2, e.g. 0x131f6): derive fine_x/shl/shr + aligned_col from x, add the
 * aligned column into a0, then run the core. The width prologues 0x131f6/0x133b6/0x1352c/0x13642
 * are byte-identical except the WIDTH immediate + BASE d3 (folded into width_idx). */
static void objsprite_entry(uint8_t *image, uint16_t x, uint16_t rows_m1, uint32_t dst, uint32_t src,
                            int width_idx) {
    unsigned fine_x = (unsigned)(x & OBJSPRITE_FINE_MASK);      /* moveq #$f,d7; and.w d0,d7 */
    unsigned shl = OBJSPRITE_SHIFT_BASE - fine_x;               /* moveq #$10,d6; sub.w d7,d6 */
    unsigned shr = fine_x;
    uint16_t col = objsprite_aligned_col(x);                    /* asr.w #1; andi.w #$fff8 */
    uint32_t a0_pre = (uint32_t)(dst + sign_ext16(col));        /* adda.w d0,a0 */
    objsprite_core(image, col, shl, shr, rows_m1, a0_pre, src, width_idx);
}

/* Helper 0x145fc — view-transform (reconstruct inline, §8). A pure register/pointer transform
 * (NO memory WRITE) driven by a per-view record at A_obj_view_xform (0x1722a): pick the record via
 * a word popped off the caller's a2 (predecrement) + view_flags*2, then rewind a1 by word[0],
 * nudge a0 by sign_ext16(word[1] & 0xFFE0), and clip the row count by (word[1] & 0x1F). Returns the
 * a0/a1/rows and the a2 left −2. It cannot be image-verified alone (no writes); verify it only
 * THROUGH a caller (t39/t38/t37) that runs it then blits. */
struct objsprite_view_xform { uint32_t a0; uint32_t a1; uint16_t rows_m1; uint32_t a2; };
static struct objsprite_view_xform
objsprite_view_transform(const uint8_t *image, uint32_t a6, uint32_t a1, uint16_t rows_m1, uint32_t a2) {
    uint32_t rec_word0_ptr = a2 - 2;                            /* adda.w -(a2),a3 : a2 -= 2 */
    uint32_t a3 = A_obj_view_xform + sign_ext16(be16(image + rec_word0_ptr));
    uint16_t view2 = (uint16_t)(be16(image + A_view_flags) * 2);   /* add.w d3,d3 */
    a3 += sign_ext16(view2);                                    /* adda.w d3,a3 -> per-view record */
    uint32_t a0 = a6;                                           /* movea.l a6,a0 */
    a1 = (uint32_t)(a1 - sign_ext16(be16(image + a3)));         /* suba.w (a3)+,a1 */
    a3 += 2;
    uint16_t rec1 = be16(image + a3);                           /* word[1] (a3 not advanced again) */
    a0 = (uint32_t)(a0 + sign_ext16((uint16_t)(rec1 & VIEW_XFORM_OFF_MASK)));  /* adda.w (word[1]&0xFFE0),a0 */
    uint16_t rows_out = (uint16_t)(rows_m1 - (uint16_t)(rec1 & VIEW_XFORM_ROW_MASK));  /* sub.w d3,d4 */
    struct objsprite_view_xform out = { a0, a1, rows_out, rec_word0_ptr };
    return out;
}

/* ---- glue: one g_objsprite_t<N> per distinct-preset entry (§7). Register map per proto lines in
 * names.txt. The width prologue heads (t4/t2/t1) and the alt entry (t53) are the four join points;
 * the tiny wrappers preset a0 (via a6 + a record word) or run the view transform / draw_obj_sprite_hi
 * first, then fall into the same prologue. ---- */

/* 0x131f6 (t4): bare width-0x80 prologue. D0 x, D4 rows-1, A0 dst, A1 src. */
void g_objsprite_t4(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t dst, uint32_t src) {
    objsprite_entry(image, (uint16_t)x, (uint16_t)rows_m1, dst, src, 0);
}
/* 0x1352c (t2): bare width-0x90 prologue. */
void g_objsprite_t2(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t dst, uint32_t src) {
    objsprite_entry(image, (uint16_t)x, (uint16_t)rows_m1, dst, src, 2);
}
/* 0x13642 (t1): bare width-0x98 prologue. */
void g_objsprite_t1(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t dst, uint32_t src) {
    objsprite_entry(image, (uint16_t)x, (uint16_t)rows_m1, dst, src, 3);
}
/* 0x133b6 (width-0x88 prologue join; reached only via the t39/t34/t3 wrappers, never a table head). */
void g_objsprite_w88(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t dst, uint32_t src) {
    objsprite_entry(image, (uint16_t)x, (uint16_t)rows_m1, dst, src, 1);
}

/* 0x13204 (t53): ALT ENTRY at `adda.w d0,a0` — skips the fine-x/aligned-col calc. The caller
 * pre-sets d0 = aligned_col (a signed multiple of 8), d6 = shl, d7 = shr(fine_x), a0 = the
 * pre-add dst base, a1 = src, d4 = rows-1. Joins the width-0x80 dispatch at 0x13206. */
void g_objsprite_t53(uint8_t *image, uint32_t aligned_col, uint32_t shl, uint32_t shr,
                     uint32_t rows_m1, uint32_t dst, uint32_t src) {
    uint16_t col = (uint16_t)aligned_col;
    uint32_t a0_pre = (uint32_t)(dst + sign_ext16(col));       /* adda.w d0,a0 */
    objsprite_core(image, col, (unsigned)shl, (unsigned)shr, (uint16_t)rows_m1, a0_pre, src, 0);
}

/* Wrapper family 3 — `movea.l a6,a0; adda.w -(a2),a0` then bra to the width prologue (t34/t33/t32):
 * a0 = a6 + sign_ext16(word@--a2), then a fresh fine-x prologue on the caller's D0. */
static void objsprite_a6_wrapper(uint8_t *image, uint16_t x, uint16_t rows_m1, uint32_t a6,
                                 uint32_t a2, uint32_t src, int width_idx) {
    uint32_t a0 = (uint32_t)(a6 + sign_ext16(be16(image + a2 - 2)));
    objsprite_entry(image, x, rows_m1, a0, src, width_idx);
}
void g_objsprite_t34(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t a6, uint32_t a2, uint32_t src) {
    objsprite_a6_wrapper(image, (uint16_t)x, (uint16_t)rows_m1, a6, a2, src, 1);   /* -> width 0x88 */
}
void g_objsprite_t33(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t a6, uint32_t a2, uint32_t src) {
    objsprite_a6_wrapper(image, (uint16_t)x, (uint16_t)rows_m1, a6, a2, src, 2);   /* -> width 0x90 */
}
void g_objsprite_t32(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t a6, uint32_t a2, uint32_t src) {
    objsprite_a6_wrapper(image, (uint16_t)x, (uint16_t)rows_m1, a6, a2, src, 3);   /* -> width 0x98 */
}

/* Wrapper family 1 — `bsr 0x145fc` (view transform) then bra to the width prologue (t39/t38/t37).
 * The transform adjusts a0 (from a6), a1, and rows-1, leaving a2 −2; the prologue then recomputes
 * the fine-x geometry from the caller's D0. */
static void objsprite_xform_wrapper(uint8_t *image, uint16_t x, uint16_t rows_m1, uint32_t a6,
                                    uint32_t a1, uint32_t a2, int width_idx) {
    struct objsprite_view_xform t = objsprite_view_transform(image, a6, a1, rows_m1, a2);
    objsprite_entry(image, x, t.rows_m1, t.a0, t.a1, width_idx);
}
void g_objsprite_t39(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t a6, uint32_t a1, uint32_t a2) {
    objsprite_xform_wrapper(image, (uint16_t)x, (uint16_t)rows_m1, a6, a1, a2, 1);   /* -> width 0x88 */
}
void g_objsprite_t38(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t a6, uint32_t a1, uint32_t a2) {
    objsprite_xform_wrapper(image, (uint16_t)x, (uint16_t)rows_m1, a6, a1, a2, 2);   /* -> width 0x90 */
}
void g_objsprite_t37(uint8_t *image, uint32_t x, uint32_t rows_m1, uint32_t a6, uint32_t a1, uint32_t a2) {
    objsprite_xform_wrapper(image, (uint16_t)x, (uint16_t)rows_m1, a6, a1, a2, 3);   /* -> width 0x98 */
}

/* Wrapper family 4 — scan-table x-build then bra to the width prologue (t42 @0x13512 -> w0x90,
 * t41 @0x13628 -> w0x98). a0 = a6 + sign_ext16(word@a2) (POST-increment a2); then D0 is rebuilt as
 * word@(a5 + sign_ext16(-scan_off)) + word@a4 + word@a2 and the prologue recomputes fine_x from it.
 * (d7 is set to -scan_off here but the prologue's `moveq #$f,d7; and.w d0,d7` overwrites it.) */
static void objsprite_scan_wrapper(uint8_t *image, uint16_t rows_m1, uint32_t a6, uint32_t a2,
                                   uint32_t a4, uint32_t a5, uint32_t src, int width_idx) {
    uint32_t a0 = (uint32_t)(a6 + sign_ext16(be16(image + a2)));   /* adda.w (a2)+,a0 (post-inc) */
    uint32_t a2_next = a2 + 2;
    int16_t neg_scan = (int16_t)-(int16_t)be16(image + A_obj_scan_off);   /* move.w scan_off,d7; neg.w */
    uint16_t x = (uint16_t)(be16(image + a5 + sign_ext16((uint16_t)neg_scan))   /* move.w (0,a5,d7.w),d0 */
                            + be16(image + a4)                                   /* add.w (a4),d0 */
                            + be16(image + a2_next));                            /* add.w (a2),d0 */
    objsprite_entry(image, x, rows_m1, a0, src, width_idx);
}
void g_objsprite_t42(uint8_t *image, uint32_t rows_m1, uint32_t a6, uint32_t a2,
                     uint32_t a4, uint32_t a5, uint32_t src) {
    objsprite_scan_wrapper(image, (uint16_t)rows_m1, a6, a2, a4, a5, src, 2);   /* -> width 0x90 */
}
void g_objsprite_t41(uint8_t *image, uint32_t rows_m1, uint32_t a6, uint32_t a2,
                     uint32_t a4, uint32_t a5, uint32_t src) {
    objsprite_scan_wrapper(image, (uint16_t)rows_m1, a6, a2, a4, a5, src, 3);   /* -> width 0x98 */
}

/* Wrapper family 2 — `bsr 0x14620` (draw_obj_sprite_hi, ALREADY VERIFIED) then FALL THROUGH into
 * the width prologue (t3 @0x133b2 -> w0x88, t49 @0x13528 -> w0x90, t16/17/43/48 @0x1363e -> w0x98).
 * The bsr'd helper draws the first (mode-8) pass and RENAMES its outputs into the registers the
 * prologue then consumes: D3->D0 (base_col x), D5->D4 (rows-1), A0 = sprite-top, A1 rewound one
 * band. The second pass is this engine's prologue on those renamed registers. Same register
 * contract as draw_obj_sprite_hi (D0 x, D1 colour, D2 width, D4 rows seed, D7 voff, A0 dst, A1 src,
 * A2 rec+0xa). Colour (D1) is unused by this engine (no colour indexing). */
static void objsprite_hi_wrapper(uint8_t *image, uint16_t x, uint16_t colour, uint16_t width,
                                 uint16_t rows_seed, uint16_t voff, uint32_t dst, uint32_t src,
                                 uint32_t rec_cursor, int width_idx) {
    struct obj_hi_out r = draw_obj_sprite_hi(image, x, colour, width, rows_seed, voff, dst, src,
                                             rec_cursor);
    objsprite_entry(image, r.d0_x, r.d4_rows, r.a0_dst, r.a1_src, width_idx);
}
void g_objsprite_t3(uint8_t *image, uint32_t x, uint32_t colour, uint32_t width, uint32_t rows_seed,
                    uint32_t voff, uint32_t dst, uint32_t src, uint32_t rec_cursor) {
    objsprite_hi_wrapper(image, (uint16_t)x, (uint16_t)colour, (uint16_t)width, (uint16_t)rows_seed,
                         (uint16_t)voff, dst, src, rec_cursor, 1);      /* -> width 0x88 */
}
void g_objsprite_t49(uint8_t *image, uint32_t x, uint32_t colour, uint32_t width, uint32_t rows_seed,
                     uint32_t voff, uint32_t dst, uint32_t src, uint32_t rec_cursor) {
    objsprite_hi_wrapper(image, (uint16_t)x, (uint16_t)colour, (uint16_t)width, (uint16_t)rows_seed,
                         (uint16_t)voff, dst, src, rec_cursor, 2);      /* -> width 0x90 */
}
void g_objsprite_t16(uint8_t *image, uint32_t x, uint32_t colour, uint32_t width, uint32_t rows_seed,
                     uint32_t voff, uint32_t dst, uint32_t src, uint32_t rec_cursor) {
    objsprite_hi_wrapper(image, (uint16_t)x, (uint16_t)colour, (uint16_t)width, (uint16_t)rows_seed,
                         (uint16_t)voff, dst, src, rec_cursor, 3);      /* -> width 0x98 (t16/17/43/48) */
}

/* ============================================================================================
 * draw_object_list @ 0x1306e — the per-frame roadside-object display-list dispatcher (register-glue).
 *
 * Two nested loops walk the object list. Per outer row it reads a dst scanline word and an x-offset
 * table word from the a5 stream; per object (15 per row) it reads a flag word from a3 and dispatches:
 *   - a SPECIAL pass first, only when the flag word is negative — its record lives at buf_a+0x21d0+d6;
 *   - a NORMAL pass, keyed on the flag word's low 6 bits (object type 0..63) — its record lives at
 *     buf_a + 0x8a0 + type*0xd0 (+d6), and carries colour, a buf_c-relative src long, rows, a vertical
 *     seed byte, the jump-table index, and per-object x/dst offsets.
 * Both passes resolve the type's word offset in obj_type_jumptable and jsr the matching handler
 * (objsprite engine t1/t2/t4/w88, the t4+t1 stub, or the blit_objshift handler_lo families). The
 * 68000 saves/restores D2/D3/D4/D6/A0/A3 around each jsr, so the per-object dst adjustments (vertical
 * offset + x offset) are temporary — the row's base a0 and the loop counter survive. See names.txt.
 *
 * Register map (kept for the byte-exact port): A5 list stream, A3 flag stream, A6 draw buffer,
 * D4 outer row count-1, D6 record byte offset (−0x10 per row), D1 colour (threaded; the NORMAL pass
 * sets it fresh from the record, the SPECIAL pass carries the last value). D2 = 0xa0 width (const). */
#define OBJ_SPECIAL_BASE 0x21d0     /* buf_a-relative base of the special-object record (+d6) */
#define OBJ_TYPE_BASE    0x8a0      /* buf_a-relative base of the per-type records */
#define OBJ_TYPE_STRIDE  0xd0       /* bytes per per-type record (muls.w #0xd0,type) */
#define OBJ_COLOUR_OFF   0x10       /* colour word at type_base − this (read before +d6) */
#define OBJ_VSEED_OFF    0xb        /* vertical seed byte at data_base − this */
#define OBJ_REC_ROWS     0x04       /* record field: rows-1 word */
#define OBJ_REC_JUMP     0x06       /* record field: obj_type_jumptable index word */
#define OBJ_REC_DSTADJ   0x08       /* record field: a0 += this word (normal); special record's cursor */
#define OBJ_REC_XADJ     0x0a       /* record field: x += this word (normal); normal record's cursor */
#define OBJ_HANDLER_SRCADJ 0x02     /* handler_lo: src += word@(cursor + this + parity) */
#define OBJ_BONUS_MIN_TYPE 6        /* bonus window clamps object types below this up to it */
#define OBJ_ROWS_ONLY    0x3f       /* flag word low bits = object type */
#define OBJ_ROW_OBJECTS  0xe        /* inner loop runs this+1 (=15) objects per row */
#define OBJ_D6_STEP      0x10       /* d6 decrement per outer row */
#define OBJ_STUB_X_ADV   0x40       /* the 0x131ac stub: t1's x = t4's x + this */
#define OBJ_STUB_SRC_ADV 0x20       /* the 0x131ac stub: t1's src = t4's src + this */
/* Resolved jump-table targets (Ghidra addresses = A_obj_type_jumptable + the stored word offset). */
#define OBJ_H_NOOP 0x13df8          /* bare rts */
#define OBJ_H_T1   0x13642
#define OBJ_H_T2   0x1352c
#define OBJ_H_W88  0x133b6
#define OBJ_H_T4   0x131f6
#define OBJ_H_STUB 0x131ac          /* t4 then t1 with x+=0x40, src+=0x20 */
#define OBJ_H_LO1  0x1466a          /* handler_lo mid-entry, 0x98 width family */
#define OBJ_H_LO2  0x144b2          /* handler_lo mid-entry, 0x90 width family */

/* handler_lo mid-entry (0x1466a / 0x144b2): adjust src by a per-view-parity record word, set the
 * tail mode, and blit the object at the width family selected by base_cells. dst comes from the
 * dispatcher's a0 (the mid-entries skip the a6+0x3ac0 dst setup of the 0x14664/0x144ac full entries). */
static void obj_handler_lo(uint8_t *image, uint16_t x, uint16_t colour, uint16_t rows_m1,
                           uint32_t dst, uint32_t src, uint32_t rec_cursor, int base_cells) {
    uint16_t parity = (uint16_t)(OBJH_PARITY_MASK & be16(image + A_view_parity));   /* 0 or 2 */
    src = (uint32_t)(src + sign_ext16(be16(image + rec_cursor + OBJ_HANDLER_SRCADJ + parity)));
    wr16(image + A_blit_mode, OBJH_MODE_TAIL);                                       /* mode = 0xa8 */
    blit_objshift_family(image, x, colour, rows_m1, dst, src, A_blit_mode, base_cells);
}

/* Resolve the object type's word offset in obj_type_jumptable and dispatch to the matching handler.
 * The objsprite engine handlers and the stub ignore colour/rec_cursor; only handler_lo uses them. */
static void obj_dispatch(uint8_t *image, uint16_t jumpidx, uint16_t x, uint16_t colour,
                         uint16_t rows_m1, uint32_t dst, uint32_t src, uint32_t rec_cursor) {
    int16_t off = (int16_t)be16(image + A_obj_type_jumptable + jumpidx);
    uint32_t target = (uint32_t)(A_obj_type_jumptable + off);
    switch (target) {
        case OBJ_H_NOOP: break;
        case OBJ_H_T1:  g_objsprite_t1(image, x, rows_m1, dst, src); break;
        case OBJ_H_T2:  g_objsprite_t2(image, x, rows_m1, dst, src); break;
        case OBJ_H_W88: g_objsprite_w88(image, x, rows_m1, dst, src); break;
        case OBJ_H_T4:  g_objsprite_t4(image, x, rows_m1, dst, src); break;
        case OBJ_H_STUB:
            g_objsprite_t4(image, x, rows_m1, dst, src);
            g_objsprite_t1(image, (uint16_t)(x + OBJ_STUB_X_ADV), rows_m1, dst,
                           src + OBJ_STUB_SRC_ADV);
            break;
        case OBJ_H_LO1: obj_handler_lo(image, x, colour, rows_m1, dst, src, rec_cursor, 1); break;
        case OBJ_H_LO2: obj_handler_lo(image, x, colour, rows_m1, dst, src, rec_cursor, 2); break;
        default: break;   /* unreachable with valid records */
    }
}

/* Glue for draw_object_list. a5/a3 are image offsets (the two input streams); a6 = draw buffer.
 * d4_outer = outer row count-1, d6 = starting record byte offset, d1_in = incoming colour. */
void g_draw_object_list(uint8_t *image, uint32_t a5, uint32_t a3, uint32_t a6,
                        uint32_t d4_outer, uint32_t d6, uint32_t d1_in) {
    uint32_t buf_a = load32(image, A_buf_a);
    uint32_t buf_c = load32(image, A_buf_c);
    uint16_t colour = (uint16_t)d1_in;                 /* d1 threads across objects */

    a5 = (uint32_t)(a5 + sign_ext16(be16(image + A_obj_scan_off)));   /* adda.w 0x18c58,a5 */

    int outer = (int16_t)(uint16_t)d4_outer + 1;
    for (int oi = 0; oi < outer; oi++) {
        uint32_t a0 = (uint32_t)(a6 + sign_ext16(be16(image + a5))); a5 += 2;         /* row dst base */
        uint32_t a4 = (uint32_t)(A_obj_xoff_tbl + sign_ext16(be16(image + a5))); a5 += 2;

        for (int inner = OBJ_ROW_OBJECTS; inner >= 0; inner--) {
            /* SPECIAL pass: only when the flag word is negative. */
            if ((int16_t)be16(image + a3) < 0) {
                uint16_t x = be16(image + a5);                        /* peeked; consumed below */
                uint32_t a2 = (uint32_t)(buf_a + OBJ_SPECIAL_BASE + sign_ext16((uint16_t)d6));
                uint32_t src = (uint32_t)(buf_c + load32(image, a2));
                uint16_t rows = be16(image + a2 + OBJ_REC_ROWS);
                uint16_t jumpidx = be16(image + a2 + OBJ_REC_JUMP);
                obj_dispatch(image, jumpidx, x, colour, rows, a0, src, a2 + OBJ_REC_DSTADJ);
            }
            /* NORMAL pass. */
            uint16_t x = be16(image + a5); a5 += 2;
            uint16_t type = (uint16_t)(be16(image + a3) & OBJ_ROWS_ONLY); a3 += 2;
            if (type != 0) {
                if (be16(image + A_bonus_timer) != 0 && (int16_t)(type - OBJ_BONUS_MIN_TYPE) < 0)
                    type = OBJ_BONUS_MIN_TYPE;                        /* bonus-window clamp */
                x = (uint16_t)(x + be16(image + a4));                 /* add.w (a4),d0 */
                uint32_t type_base = (uint32_t)(buf_a + OBJ_TYPE_BASE
                                                + sign_ext16((uint16_t)(type * OBJ_TYPE_STRIDE)));
                colour = be16(image + type_base - OBJ_COLOUR_OFF);    /* d1 = colour (before +d6) */
                uint32_t data_base = (uint32_t)(type_base + sign_ext16((uint16_t)d6));
                uint32_t src = (uint32_t)(buf_c + load32(image, data_base));
                uint16_t rows = be16(image + data_base + OBJ_REC_ROWS);
                /* vertical offset: (vseed − rows).b * view_flags >> 4 * width, subtracted from a0. */
                uint16_t v = (uint16_t)(uint8_t)(image[data_base - OBJ_VSEED_OFF] - (uint8_t)rows);
                v = (uint16_t)(v * be16(image + A_view_flags));       /* mulu.w view_flags */
                v = (uint16_t)(v >> 4);                               /* lsr.w #4 */
                v = (uint16_t)(v * OBJD_WIDTH);                       /* mulu.w #0xa0 (width) */
                uint32_t dst = (uint32_t)(a0 - sign_ext16(v));        /* suba.w d7,a0 (temporary) */
                uint16_t jumpidx = be16(image + data_base + OBJ_REC_JUMP);
                dst = (uint32_t)(dst + sign_ext16(be16(image + data_base + OBJ_REC_DSTADJ)));
                x = (uint16_t)(x + be16(image + data_base + OBJ_REC_XADJ));
                obj_dispatch(image, jumpidx, x, colour, rows, dst, src, data_base + OBJ_REC_XADJ);
            }
        }
        a3 += 2;                                    /* addq.l #2,a3 */
        d6 = (uint16_t)(d6 - OBJ_D6_STEP);          /* subi.w #0x10,d6 */
    }
}
