/* sprite.c — masked buggy / foreground sprites (draw_fg_sprite .. draw_buggy @ 0x1518a..).
 *
 * These blit a 4-plane sprite into the draw buffer using the shared transparency cell
 * (blit_transp_cell), bottom row first and walking one scanline up (OBJ_ROW_UP) per row.
 * draw_buggy_wheels is the shared blit body (A0 dst, A1 src, D4 rows-1); draw_fg_sprite sets
 * those up from the animation tables (behind a spin/curve gate) and falls into it.
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"
#include "draw.h"

#define CELL_BYTES    8        /* one 16-pixel, 4-plane transparency cell */
#define WHEELS_CELLS  4        /* cells per row (64 px wide) */

/* draw_buggy_wheels @ 0x151f6 — A0 dst, A1 src, D4 rows-1. Each row is WHEELS_CELLS transparency
 * cells; dst and src both step one scanline up (OBJ_ROW_UP) after the row. */
void g_draw_buggy_wheels(uint8_t *image, uint32_t dst, uint32_t src, uint32_t rows_m1) {
    int rows = (int16_t)rows_m1 + 1;
    for (int r = 0; r < rows; r++, dst -= OBJ_ROW_UP, src -= OBJ_ROW_UP)
        for (int cell = 0; cell < WHEELS_CELLS; cell++)
            blit_transp_cell(image, dst + cell * CELL_BYTES, src + cell * CELL_BYTES);
}
