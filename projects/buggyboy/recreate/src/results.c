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
#include "draw.h"

#define RESULT_ROW_BLOCKS  3       /* stacked copies of the source block (outer d5=2) */
#define RESULT_ROW_ROWS    32      /* rows per block (inner d4=0x1f) */
#define RESULT_COL_COLS    5       /* tiled columns (outer d3=4) */
#define RESULT_COL_ROWS    7       /* rows per column (inner d4=6) */
#define RESULT_COL_BYTES   16      /* bytes copied per row; also the column pitch (4 longwords) */

/* buf_c source pointer at a caller offset (adda.l buf_c to A1). */
static uint32_t buf_c_src(const uint8_t *image, uint32_t src_off) {
    return be32(image + A_buf_c) + src_off;
}

void g_draw_result_col(uint8_t *image, uint32_t dst_off, uint32_t src_off) {
    uint32_t src = buf_c_src(image, src_off);
    uint32_t dst = draw_dst(image, dst_off);
    for (int col = 0; col < RESULT_COL_COLS; col++)
        for (int row = 0; row < RESULT_COL_ROWS; row++)
            memcpy(image + dst + col * RESULT_COL_BYTES + row * ROW_STRIDE,
                   image + src + row * ROW_STRIDE, RESULT_COL_BYTES);
}

/* One 8-byte (4-plane, 16-pixel) masked row: keep the dest where the source is transparent. */
static void blit_result_row(uint8_t *image, uint32_t dst, uint32_t src) {
    blit_transp_cell(image, dst, src);
}

void g_draw_result_row(uint8_t *image, uint32_t dst_off, uint32_t src_off) {
    uint32_t src = buf_c_src(image, src_off);
    uint32_t dst = draw_dst(image, dst_off);
    for (int block = 0; block < RESULT_ROW_BLOCKS; block++)
        for (int row = 0; row < RESULT_ROW_ROWS; row++)
            blit_result_row(image,
                            dst + (block * RESULT_ROW_ROWS + row) * ROW_STRIDE,
                            src + row * ROW_STRIDE);
}

/* --- draw_dashboard @ 0x150a4 --- Masked blit of the fixed dashboard graphic from buf_c
 * (D0 = dst offset). 40 rows, each 8 groups of 4 dest words. Per group the four source words
 * are (mask, a, b, c): every dest word keeps the background where mask is set, and the group's
 * four dest words take ink a, b, b, c (the middle word is written twice — a longword op in the
 * original draws two screen words from one source word). Source and dest step one scanline. */
#define DASH_SRC_OFF   0x11c20     /* dashboard graphic at buf_c + this */
#define DASH_ROWS      40          /* dbf #$27 */
#define DASH_GROUPS    8           /* 8 groups of 4 dest words = 32 words (0x40 bytes) per row */

void g_draw_dashboard(uint8_t *image, uint32_t dst_off) {
    uint32_t src = buf_c_src(image, DASH_SRC_OFF);
    uint32_t dst = draw_dst(image, dst_off);
    for (int row = 0; row < DASH_ROWS; row++, dst += ROW_STRIDE, src += ROW_STRIDE) {
        uint32_t d = dst, s = src;
        for (int g = 0; g < DASH_GROUPS; g++, d += 8, s += 8) {
            uint16_t mask = be16(image + s);
            uint16_t ink_a = be16(image + s + 2);
            uint16_t ink_b = be16(image + s + 4);
            uint16_t ink_c = be16(image + s + 6);
            wr16(image + d,     (uint16_t)((be16(image + d)     & mask) | ink_a));
            wr16(image + d + 2, (uint16_t)((be16(image + d + 2) & mask) | ink_b));
            wr16(image + d + 4, (uint16_t)((be16(image + d + 4) & mask) | ink_b));
            wr16(image + d + 6, (uint16_t)((be16(image + d + 6) & mask) | ink_c));
        }
    }
}

/* --- init_leg_dash @ 0x12d38 --- Builds the per-leg dashboard graphic that g_draw_dashboard
 * later blits. Two steps, both keyed by leg_index:
 *   1. Seed the dashboard progress-marker record (dash_marker, a long) from the per-leg table at
 *      buf_a + DASH_MARKER_TBL. game_update then walks this marker along the dashboard map.
 *   2. Expand the raw per-leg block (mem_base + leg*DASH_LEG_STRIDE) into buf_c + DASH_SRC_OFF,
 *      doubling it horizontally: each unit reads two source words W0,W1 (4 bytes) and writes four
 *      dest words W0,W1,W1,W1 (8 bytes) — a 68k move.l re-emits W1 twice. DASH_ROWS rows of
 *      DASH_GROUPS units; the source is packed contiguously (stride DASH_SRC_STRIDE) while the
 *      dest steps a full scanline (ROW_STRIDE = 0x40 written + 0x60 skip). */
#define DASH_MARKER_TBL   0x7f8      /* per-leg marker-seed longs at buf_a + this */
#define DASH_LEG_STRIDE   0x500      /* raw per-leg dashboard block = DASH_ROWS * DASH_SRC_STRIDE */
#define DASH_SRC_STRIDE   0x20       /* raw source bytes per row (DASH_GROUPS units x 4 bytes) */

void g_init_leg_dash(uint8_t *image) {
    int16_t leg = (int16_t)be16(image + A_leg_index);
    wr32(image + A_dash_marker, be32(image + be32(image + A_buf_a) + DASH_MARKER_TBL + leg * 4));

    uint32_t src = be32(image + A_mem_base) + sign_ext16(leg * DASH_LEG_STRIDE);
    uint32_t dst = buf_c_src(image, DASH_SRC_OFF);
    for (int row = 0; row < DASH_ROWS; row++, dst += ROW_STRIDE, src += DASH_SRC_STRIDE) {
        uint32_t d = dst, s = src;
        for (int unit = 0; unit < DASH_GROUPS; unit++, d += 8, s += 4) {
            uint16_t w0 = be16(image + s);
            uint16_t w1 = be16(image + s + 2);
            wr16(image + d,     w0);
            wr16(image + d + 2, w1);
            wr16(image + d + 4, w1);
            wr16(image + d + 6, w1);
        }
    }
}

/* --- probe_collision @ 0x110a4 --- Advances the dashboard progress-marker (dash_marker) one step
 * along the track drawn in the dashboard bitmap. First it erases the marker's current dot, then it
 * probes the eight neighbour cells (A_probe_deltas: {delta_bit, delta_x} per direction). A neighbour
 * "hits" the track when the AND of two source words at that cell has the probed bit set; on the
 * first hit the marker record is updated to that cell and the scan stops. No hit leaves the marker
 * position unchanged (only the old dot erased). The marker is {y: byte, bit: byte(low nibble),
 * x: word}; when a probed bit crosses a cell's 16-bit span the y offset steps one cell (PROBE_Y_STEP).
 * Called at the end of draw_leg_labels and from game_update. */
#define DASH_PROBE_ORIGIN  (DASH_SRC_OFF + 2)  /* marker coordinates are relative to buf_c + this */
#define PROBE_DIRS         8                    /* neighbour cells probed (table entries) */
#define PROBE_CELL_BITS    0x10                 /* bits spanned per cell before y steps a row */
#define PROBE_Y_STEP       8                    /* y-offset delta when the bit crosses a cell */

void g_probe_collision(uint8_t *image) {
    uint32_t base = buf_c_src(image, DASH_PROBE_ORIGIN);
    uint8_t  y0   = image[A_dash_marker];            /* d4: byte y offset */
    uint8_t  bit0 = image[A_dash_marker + 1] & 0xf;  /* d5: bit index 0..15 */
    uint16_t x0   = be16(image + A_dash_marker + 2); /* d6: word x offset */

    /* Erase the marker's current dot (clear its bit in the dashboard bitmap). */
    uint32_t cur = base + y0 + sign_ext16(x0);
    wr16(image + cur, (uint16_t)(be16(image + cur) & ~(1u << bit0)));

    uint32_t tbl = A_probe_deltas;
    for (int dir = 0; dir < PROBE_DIRS; dir++, tbl += 4) {
        int16_t y   = (int16_t)(uint16_t)y0;
        int16_t bit = (int16_t)bit0 + (int16_t)be16(image + tbl);
        if (bit < 0)                    y += PROBE_Y_STEP;   /* underflowed the cell -> step down */
        else if (bit >= PROBE_CELL_BITS) y -= PROBE_Y_STEP;  /* overflowed the cell -> step up */
        bit &= 0xf;
        int16_t x = (int16_t)x0 + (int16_t)be16(image + tbl + 2);

        uint32_t a = base + sign_ext16((uint16_t)y) + sign_ext16((uint16_t)x);
        uint16_t probe = (uint16_t)(be16(image + a) & be16(image + a + 4));
        if (probe & (1u << bit)) {                            /* neighbour on the track -> move here */
            wr16(image + A_dash_marker + 2, (uint16_t)x);
            image[A_dash_marker + 1] = (uint8_t)bit;
            image[A_dash_marker]     = (uint8_t)y;
            return;
        }
    }
}

/* --- draw_leg_results @ 0x125f2 --- Paints the per-leg results screen: background fills, the
 * four result panels (row/col blitters), two rows of labels, the leg time digits, and the
 * dashboard. No register arguments; layout coordinates and colours are baked into the code.
 * The first label row chains A3 through one concatenated string; the second draws five rows
 * from buf_a (stride LEG_ROW_STR_STRIDE) with a per-row colour from a palette string indexed
 * by leg_index. All screen/fill/blit primitives are the already-verified g_* leaves. */
#define LEG_TITLE_STR       0x18028   /* concatenated label strings for the first row */
#define LEG_ROW_PALETTE     0x17e9f   /* per-row colour bytes, indexed downward by leg_index */
#define LEG_LABEL_ROWS      5
#define LEG_ROW_DST_STEP    0xa00     /* screen dst step between label rows */
#define LEG_ROW_STR_OFF     0x848     /* buf_a offset of the second row's label strings */
#define LEG_ROW_STR_STRIDE  0xc       /* bytes between those per-row strings */
#define LEG_DIGITS_OFF      0x884     /* buf_a offset of the leg time/score digit string */

void g_draw_leg_results(uint8_t *image) {
    g_fill_words(image, 1, 0x76b);                 /* clear the screen to colour 1 */
    g_fill_rect(image, 0x9a8, 6, 8, 0x48);         /* results panel background */
    g_draw_result_row(image, 0x540, 0x12430);
    g_draw_result_row(image, 0x588, 0x12438);
    g_draw_result_col(image, 0x548, 0x11a30);
    g_draw_result_col(image, 0x3748, 0x11f30);
    g_fill_rect(image, 0x590, 1, 0, 0x57);         /* left divider column */
    g_fill_span(image, 0x3b60, 1, 0x833);          /* bottom band */

    /* Row 1: five labels from one concatenated buffer, colour 8; A3 chains across the calls. */
    uint32_t str = LEG_TITLE_STR;
    uint32_t dst = 0xa10;
    for (int i = 0; i < LEG_LABEL_ROWS; i++, dst += LEG_ROW_DST_STEP)
        str = draw_text_chain(image, dst, 8, str);

    /* Row 2: five per-leg label strings from buf_a, each with its own palette colour. */
    uint32_t row_str = be32(image + A_buf_a) + LEG_ROW_STR_OFF;
    uint32_t palette = LEG_ROW_PALETTE - sign_ext16(be16(image + A_leg_index));   /* suba.w */
    dst = 0xa18;
    for (int i = 0; i < LEG_LABEL_ROWS; i++, dst += LEG_ROW_DST_STEP)
        g_draw_text(image, dst, image[palette + i], row_str + i * LEG_ROW_STR_STRIDE);

    uint16_t leg = be16(image + A_leg_index);
    g_draw_num_thunk(image, 0xa48, 4, be32(image + A_buf_a) + LEG_DIGITS_OFF + leg * LEG_ROW_STR_STRIDE);
    g_draw_dashboard(image, 0x1948);
}
