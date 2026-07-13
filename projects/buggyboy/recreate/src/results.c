/* results.c — results-screen block blitters (draw_result_row/col @ 0x15016..).
 *
 * Both copy a precomputed source block from buf_c (A1 = byte offset into buf_c) into the draw
 * buffer at buffer[flip_idx] + D0 (D0 a signed word offset). Neither takes a colour index.
 *   draw_result_col  tiles a 7-row, 16-byte column 5 times across; the source is reused for
 *                    each column, so the same block repeats horizontally. A plain copy.
 *   draw_result_row  stacks a 32-row blit 3 times down; the source is reused for each block.
 *                    Each row is a 4-word transparency blit built from four source words
 *                    A,B,C,D: mask = D & ~(A|B|C) selects where the dest shows through, planes
 *                    0-2 take A/B/C, and plane 3 takes D's leftover (non-A/B/C) bits.
 */
#include <string.h>
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

#define RESULT_ROW_BLOCKS  3       /* stacked copies of the source block (outer d5=2) */
#define RESULT_ROW_ROWS    32      /* rows per block (inner d4=0x1f) */
#define RESULT_COL_COLS    5       /* tiled columns (outer d3=4) */
#define RESULT_COL_ROWS    7       /* rows per column (inner d4=6) */
#define RESULT_COL_BYTES   16      /* bytes copied per row; also the column pitch (4 longwords) */

/* buf_c source pointer at a caller offset (adda.l buf_c to A1). */
static uint32_t buf_c_src(const uint8_t *image, uint32_t src_off) {
    return be32(image + A_buf_c) + src_off;
}

/* Draw buffer (physbase_tbl[flip_idx]) plus a sign-extended word offset (adda.w). */
static uint32_t buffer_dst(const uint8_t *image, uint32_t dst_off) {
    int16_t flip_idx = (int16_t)be16(image + A_flip_idx);
    return be32(image + A_physbase_tbl + flip_idx) + sign_ext16(dst_off);
}

void g_draw_result_col(uint8_t *image, uint32_t dst_off, uint32_t src_off) {
    uint32_t src = buf_c_src(image, src_off);
    uint32_t dst = buffer_dst(image, dst_off);
    for (int col = 0; col < RESULT_COL_COLS; col++)
        for (int row = 0; row < RESULT_COL_ROWS; row++)
            memcpy(image + dst + col * RESULT_COL_BYTES + row * ROW_STRIDE,
                   image + src + row * ROW_STRIDE, RESULT_COL_BYTES);
}

/* One 8-byte (4-plane, 16-pixel) masked row: keep the dest where the source is transparent. */
static void blit_result_row(uint8_t *image, uint32_t dst, uint32_t src) {
    uint16_t a = be16(image + src);
    uint16_t b = be16(image + src + 2);
    uint16_t c = be16(image + src + 4);
    uint16_t d = be16(image + src + 6);
    uint16_t mask = (uint16_t)(~(a | b | c) & d);
    wr16(image + dst,     (uint16_t)((be16(image + dst)     & mask) | a));
    wr16(image + dst + 2, (uint16_t)((be16(image + dst + 2) & mask) | b));
    wr16(image + dst + 4, (uint16_t)((be16(image + dst + 4) & mask) | c));
    wr16(image + dst + 6, (uint16_t)((be16(image + dst + 6) & mask) | (uint16_t)(d & ~mask)));
}

void g_draw_result_row(uint8_t *image, uint32_t dst_off, uint32_t src_off) {
    uint32_t src = buf_c_src(image, src_off);
    uint32_t dst = buffer_dst(image, dst_off);
    for (int block = 0; block < RESULT_ROW_BLOCKS; block++)
        for (int row = 0; row < RESULT_ROW_ROWS; row++)
            blit_result_row(image,
                            dst + (block * RESULT_ROW_ROWS + row) * ROW_STRIDE,
                            src + row * ROW_STRIDE);
}
