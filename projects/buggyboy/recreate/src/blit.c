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
