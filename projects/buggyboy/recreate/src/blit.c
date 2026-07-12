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
    uint16_t edge_col = half_x & 0xfff8;

    if ((int16_t)edge_col < 0) return edge_col;            /* off the left edge: no draw */
    if ((int16_t)(edge_col - (uint16_t)width) >= 0) {      /* fully inside: solid fill */
        full_row(image, dst, fill_lo, fill_hi);
        return (uint32_t)(uint16_t)(edge_col - (uint16_t)width);
    }
    /* straddling the edge: masked edge cell + solid interior to its left */
    uint32_t edge_mask = load32(image, A_blit_mask_L + (uint32_t)(int32_t)(int16_t)((x & 0xf) << 2));
    uint32_t edge_ptr = dst + (uint32_t)(int32_t)(int16_t)edge_col;
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
    uint16_t col = (uint16_t)((int16_t)x >> 1) & 0xfff8;

    if ((int16_t)col < 0) { full_row(image, dst, fill_lo, fill_hi); return; }  /* off the right edge */
    if ((int16_t)(col - (uint16_t)width) >= 0) return;                         /* past the width */

    uint32_t edge_mask = load32(image, A_blit_mask_R + (uint32_t)(int32_t)(int16_t)((x & 0xf) << 2));
    uint32_t edge_ptr = dst + (uint32_t)(int32_t)(int16_t)col;
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
    uint32_t dst = buf_base + (uint32_t)(int32_t)(int16_t)row_offset;
    int rows = (int16_t)rows_minus1 + 1;

    uint16_t edge_col = (uint16_t)((int16_t)screen_x >> 1) & 0xfff8;
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
    uint32_t dst = buf_base + (uint32_t)(int32_t)(int16_t)row_offset;
    int rows = (int16_t)rows_minus1 + 1;

    uint16_t col = (uint16_t)((int16_t)screen_x >> 1) & 0xfff8;
    int32_t stride = ((int16_t)col < 0) ? -(int32_t)obj_width : -(int32_t)OBJ_ROW_UP;
    for (int row = 0; row < rows; row++, dst = (uint32_t)((int32_t)dst + stride))
        row_right(image, dst, screen_x, obj_width, fill_lo, fill_hi);
}

/* ---- far variants: x slants by one per row, stride = object width ---- */

uint32_t g_blit_obj_Lf(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t row_offset,
                       uint32_t x, uint32_t fill_lo, uint32_t fill_hi, uint32_t rows_minus1) {
    int16_t obj_width = (int16_t)width;
    uint16_t cur_x = (uint16_t)x;
    uint32_t dst = buf_base + (uint32_t)(int32_t)(int16_t)row_offset;
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
    uint32_t dst = buf_base + (uint32_t)(int32_t)(int16_t)row_offset;
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