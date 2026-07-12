/* blit.c — object sprite blitters (blit_obj_* @ 0x10bdc..).
 *
 * These draw a vertical column of a roadside-object sprite into the draw buffer, one
 * scanline per row, from the bottom up. The x position selects one of three regimes:
 *   - off the left edge (x/2 < 0): nothing to draw;
 *   - fully within the road (edge column >= width): solid full-width fill, stride = width;
 *   - straddling the left edge: an antialiased masked edge column (mask from A_blit_mask_L)
 *     plus a solid interior fill of the whole cells to its left.
 * The return value is a status the caller (draw_object) chains on.
 *
 * All 16-bit register arithmetic wraps mod 2^16, mirrored here with explicit int16/uint16.
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

static uint32_t rd(const uint8_t *m, uint32_t a) { return be32(m + a); }
static void     wr(uint8_t *m, uint32_t a, uint32_t v) { wr32(m + a, v); }

/* Draw one left-edge object column, near variant (blit_obj_Ln @ 0x10bdc).
 *   dst      destination row base (draw buffer + row offset)
 *   width    sprite width in bytes; doubles as the full-fill vertical stride
 *   x        screen x of the object's left edge
 *   fill_lo/fill_hi  the two-longword solid colour
 *   rows     number of scanline rows to draw
 */
uint32_t blit_obj_left_near(uint8_t *m, uint32_t dst, int16_t width, uint16_t x,
                            uint32_t fill_lo, uint32_t fill_hi, int rows) {
    uint16_t half_x   = (uint16_t)((int16_t)x >> 1);   /* x / 2, sign-preserving */
    uint16_t edge_col = half_x & 0xfff8;               /* byte-aligned left edge */

    if ((int16_t)edge_col < 0) return edge_col;        /* object off the left edge */

    if ((int16_t)(edge_col - (uint16_t)width) >= 0) {
        /* object spans the full width: solid fill, vertical stride = width */
        uint32_t row = dst;
        for (int r = 0; r < rows; r++, row = (uint32_t)((int32_t)row - width)) {
            uint32_t p = row;
            for (int cell = 0; cell < OBJ_FULL_CELLS; cell++, p += 16) {
                wr(m, p, fill_lo);     wr(m, p + 4, fill_hi);
                wr(m, p + 8, fill_lo); wr(m, p + 12, fill_hi);
            }
        }
        return (uint32_t)(uint16_t)(edge_col - (uint16_t)width);
    }

    /* straddling the edge: antialiased masked edge column, drawn bottom-up */
    uint32_t edge_mask = rd(m, A_blit_mask_L + (uint32_t)(int32_t)(int16_t)((x & 0xf) << 2));
    uint32_t edge_ptr = dst + (uint32_t)(int32_t)(int16_t)edge_col;
    for (int r = 0; r < rows; r++, edge_ptr -= OBJ_ROW_UP) {
        wr(m, edge_ptr,     (rd(m, edge_ptr)     & edge_mask) | (fill_lo & ~edge_mask));
        wr(m, edge_ptr + 4, (rd(m, edge_ptr + 4) & edge_mask) | (fill_hi & ~edge_mask));
    }

    /* solid interior fill of the whole cells left of the edge */
    uint16_t interior_cells = half_x >> 3;
    if (interior_cells == 0) return edge_mask;         /* no interior: return the mask */
    uint32_t status = 0;
    uint32_t row = dst;
    for (int r = 0; r < rows; r++, row -= OBJ_ROW_UP) {
        uint32_t p = row;
        for (uint16_t cell = 0; cell < interior_cells; cell++, p += 8) {
            wr(m, p, fill_lo); wr(m, p + 4, fill_hi);
        }
        status = 0xffff;
    }
    return status;
}

uint32_t g_blit_obj_Ln(uint8_t *m, uint32_t a6, uint32_t d2, uint32_t d3,
                       uint32_t d4, uint32_t d5, uint32_t d6, uint32_t d7) {
    uint32_t dst = a6 + (uint32_t)(int32_t)(int16_t)d3;
    return blit_obj_left_near(m, dst, (int16_t)d2, (uint16_t)d4, d5, d6, (int16_t)d7 + 1);
}