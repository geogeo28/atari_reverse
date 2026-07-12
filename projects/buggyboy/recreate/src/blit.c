/* blit.c — object sprite blitters (blit_obj_* @ 0x10bdc..).
 *
 * These draw a roadside-object sprite into the draw buffer one scanline per row. Every
 * variant is built from one per-row primitive (left- or right-anchored) driven by a
 * different scan pattern:
 *   near (Ln/Rn)  fixed x, a straight vertical column; masked rows step one scanline (160),
 *                 a full-width row steps by the object stride D2.
 *   far  (Lf/Rf)  x slants by one per row, every row steps by D2 (perspective recession).
 * The per-row primitive picks a regime from x: off-edge (skip or full-fill), fully inside
 * the road (solid 10-cell fill), or straddling the edge (antialiased masked column from
 * A_blit_mask_L/R plus a solid interior of the whole cells beside it).
 *
 * All 16-bit register arithmetic wraps mod 2^16, mirrored with explicit int16/uint16.
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

static uint32_t rd(const uint8_t *m, uint32_t a) { return be32(m + a); }
static void     wr(uint8_t *m, uint32_t a, uint32_t v) { wr32(m + a, v); }

/* Solid full-width row: 10 two-longword colour cells. */
static void full_row(uint8_t *m, uint32_t dst, uint32_t lo, uint32_t hi) {
    for (int cell = 0; cell < OBJ_FULL_CELLS; cell++, dst += 16) {
        wr(m, dst, lo);     wr(m, dst + 4, hi);
        wr(m, dst + 8, lo); wr(m, dst + 12, hi);
    }
}

/* One left-anchored row at row base `dst`, screen x. Returns the status word the caller
 * chains on: the column off-left, or (edge-width) when full, or 0xffff/mask when masked. */
static uint32_t row_left(uint8_t *m, uint32_t dst, uint16_t x, int16_t width,
                         uint32_t lo, uint32_t hi) {
    uint16_t half_x   = (uint16_t)((int16_t)x >> 1);
    uint16_t edge_col = half_x & 0xfff8;

    if ((int16_t)edge_col < 0) return edge_col;            /* off the left edge: no draw */
    if ((int16_t)(edge_col - (uint16_t)width) >= 0) {      /* fully inside: solid fill */
        full_row(m, dst, lo, hi);
        return (uint32_t)(uint16_t)(edge_col - (uint16_t)width);
    }
    /* straddling the edge: masked edge cell + solid interior to its left */
    uint32_t mask = rd(m, A_blit_mask_L + (uint32_t)(int32_t)(int16_t)((x & 0xf) << 2));
    uint32_t p = dst + (uint32_t)(int32_t)(int16_t)edge_col;
    wr(m, p,     (rd(m, p)     & mask) | (lo & ~mask));
    wr(m, p + 4, (rd(m, p + 4) & mask) | (hi & ~mask));

    uint16_t cells = half_x >> 3;
    if (cells == 0) return mask;
    uint32_t q = dst;
    for (uint16_t c = 0; c < cells; c++, q += 8) { wr(m, q, lo); wr(m, q + 4, hi); }
    return 0xffff;
}

/* One right-anchored row. Off-right fills the whole row; inside the width it draws a masked
 * edge cell plus a solid interior extending rightward. No meaningful return (callers void). */
static void row_right(uint8_t *m, uint32_t dst, uint16_t x, int16_t width,
                      uint32_t lo, uint32_t hi) {
    uint16_t col = (uint16_t)((int16_t)x >> 1) & 0xfff8;

    if ((int16_t)col < 0) { full_row(m, dst, lo, hi); return; }   /* off the right edge */
    if ((int16_t)(col - (uint16_t)width) >= 0) return;            /* past the width: nothing */

    uint32_t mask = rd(m, A_blit_mask_R + (uint32_t)(int32_t)(int16_t)((x & 0xf) << 2));
    uint32_t p = dst + (uint32_t)(int32_t)(int16_t)col;
    wr(m, p,     (rd(m, p)     & mask) | (lo & ~mask));
    wr(m, p + 4, (rd(m, p + 4) & mask) | (hi & ~mask));

    int16_t s = (int16_t)(col - (uint16_t)width) + 8;
    uint32_t q = p + 8;
    for (; s < 0; s += 8, q += 8) { wr(m, q, lo); wr(m, q + 4, hi); }
}

/* ---- near variants: fixed x, straight vertical column ---- */

uint32_t g_blit_obj_Ln(uint8_t *m, uint32_t a6, uint32_t d2, uint32_t d3,
                       uint32_t d4, uint32_t d5, uint32_t d6, uint32_t d7) {
    int16_t width = (int16_t)d2;
    uint16_t x = (uint16_t)d4;
    uint32_t dst = a6 + (uint32_t)(int32_t)(int16_t)d3;
    int rows = (int16_t)d7 + 1;

    uint16_t edge_col = (uint16_t)((int16_t)x >> 1) & 0xfff8;
    if ((int16_t)edge_col < 0) return edge_col;
    int full = (int16_t)(edge_col - (uint16_t)width) >= 0;
    int32_t stride = full ? -(int32_t)width : -(int32_t)OBJ_ROW_UP;

    uint32_t status = 0;
    for (int r = 0; r < rows; r++, dst = (uint32_t)((int32_t)dst + stride))
        status = row_left(m, dst, x, width, d5, d6);
    return status;
}

void g_blit_obj_Rn(uint8_t *m, uint32_t a6, uint32_t d2, uint32_t d3,
                   uint32_t d4, uint32_t d5, uint32_t d6, uint32_t d7) {
    int16_t width = (int16_t)d2;
    uint16_t x = (uint16_t)d4;
    uint32_t dst = a6 + (uint32_t)(int32_t)(int16_t)d3;
    int rows = (int16_t)d7 + 1;

    uint16_t col = (uint16_t)((int16_t)x >> 1) & 0xfff8;
    int32_t stride = ((int16_t)col < 0) ? -(int32_t)width : -(int32_t)OBJ_ROW_UP;
    for (int r = 0; r < rows; r++, dst = (uint32_t)((int32_t)dst + stride))
        row_right(m, dst, x, width, d5, d6);
}

/* ---- far variants: x slants by one per row, stride = object width ---- */

uint32_t g_blit_obj_Lf(uint8_t *m, uint32_t a6, uint32_t d2, uint32_t d3,
                       uint32_t d4, uint32_t d5, uint32_t d6, uint32_t d7) {
    int16_t width = (int16_t)d2;
    uint16_t x = (uint16_t)d4;
    uint32_t dst = a6 + (uint32_t)(int32_t)(int16_t)d3;
    int rows = (int16_t)d7 + 1;

    uint32_t status = 0;
    for (int r = 0; r < rows; r++, dst = (uint32_t)((int32_t)dst - width), x = (uint16_t)(x - 1))
        status = row_left(m, dst, x, width, d5, d6);
    return status;
}

void g_blit_obj_Rf(uint8_t *m, uint32_t a6, uint32_t d2, uint32_t d3,
                   uint32_t d4, uint32_t d5, uint32_t d6, uint32_t d7) {
    int16_t width = (int16_t)d2;
    uint16_t x = (uint16_t)d4;
    uint32_t dst = a6 + (uint32_t)(int32_t)(int16_t)d3;
    int rows = (int16_t)d7 + 1;

    for (int r = 0; r < rows; r++, dst = (uint32_t)((int32_t)dst - width), x = (uint16_t)(x + 1))
        row_right(m, dst, x, width, d5, d6);
}