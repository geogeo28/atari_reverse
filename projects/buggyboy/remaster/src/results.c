/* results.c — the per-leg results screen (recreate's results.c draw_leg_results @0x125f2).
 *
 * Paints the between-legs results screen onto remaster's native models: background fills, four result
 * panels (two masked-row blits + two tiled-column copies from buf_c), two label rows, the leg-time
 * digits, and the per-leg dashboard graphic. Row 1 chains one concatenated string across five labels;
 * row 2 draws five buf_a strings, each tinted by a per-leg palette byte indexed by (row - leg).
 *
 * Reuses the shared primitives: rm_glyph_run / rm_num_run (text.h), cell_transp (plane.h) for the
 * masked result-row blit, and the rm_fill_* family (fill.h). See flow.h for the asset model.
 */
#include <string.h>

#include "fill.h"
#include "flow.h"
#include "plane.h"
#include "st.h"
#include "text.h"

#define ROW_STRIDE SCREEN_ROW_BYTES

/* ---- result-panel block blitters (buf_c src -> draw buffer) ---- */
#define RESULT_ROW_BLOCKS 3        /* stacked copies of the 32-row source block */
#define RESULT_ROW_ROWS   32
#define RESULT_COL_COLS   5        /* tiled columns */
#define RESULT_COL_ROWS   7
#define RESULT_COL_BYTES  16       /* bytes per row; also the column pitch (4 longwords) */

/* Tile a 7-row, 16-byte column 5 times across; the source block is reused per column (plain copy). */
static void draw_result_col(Framebuffer *fb, const uint8_t *gfx, Offset dst_off, uint32_t src_off) {
    uint8_t *px = fb->px;
    const uint8_t *src = gfx + src_off;
    Offset dst = (Offset)sx16((uint16_t)dst_off);
    for (int col = 0; col < RESULT_COL_COLS; col++)
        for (int row = 0; row < RESULT_COL_ROWS; row++)
            memcpy(px + dst + col * RESULT_COL_BYTES + row * ROW_STRIDE,
                   src + row * ROW_STRIDE, RESULT_COL_BYTES);
}

/* Stack a 32-row masked-transparency blit 3 times down; the source block is reused per block. */
static void draw_result_row(Framebuffer *fb, const uint8_t *gfx, Offset dst_off, uint32_t src_off) {
    uint8_t *px = fb->px;
    const uint8_t *src = gfx + src_off;
    Offset dst = (Offset)sx16((uint16_t)dst_off);
    for (int block = 0; block < RESULT_ROW_BLOCKS; block++)
        for (int row = 0; row < RESULT_ROW_ROWS; row++)
            cell_transp(px, dst + (block * RESULT_ROW_ROWS + row) * ROW_STRIDE,
                        src + row * ROW_STRIDE);
}

/* ---- dashboard graphic (masked blit from buf_c) — cell_dashboard (plane.h) ---- */
#define DASH_SRC_OFF 0x11c20       /* dashboard graphic at gfx + this */
#define DASH_DST     0x1948        /* draw-buffer offset the dashboard is stamped at */

/* ---- draw_leg_results ---- */
#define LEG_LABEL_ROWS    5
#define LEG_ROW_DST_STEP  0xa00    /* screen dst step between label rows */
#define LEG_ROW_STR_STRIDE 0xc     /* bytes between per-row buf_a strings / digit records */
#define LEG_ROW1_COLOR    8
#define LEG_DIGITS_COLOR  4
#define NUM_MAX_CELLS_M1  0x13     /* draw_num_thunk preset cell count-1 */

void rm_draw_leg_results(Framebuffer *fb, const RmResultsAssets *a, uint16_t leg) {
    const uint8_t *cp = a->color_pairs;
    rm_fill_words(fb, cp, 1, 0x76b);                 /* clear the top of the screen to colour 1 */
    rm_fill_rect(fb, cp, 0x9a8, 6, 8, 0x48);         /* results panel background */
    draw_result_row(fb, a->gfx, 0x540, 0x12430);
    draw_result_row(fb, a->gfx, 0x588, 0x12438);
    draw_result_col(fb, a->gfx, 0x548, 0x11a30);
    draw_result_col(fb, a->gfx, 0x3748, 0x11f30);
    rm_fill_rect(fb, cp, 0x590, 1, 0, 0x57);         /* left divider column */
    rm_fill_span(fb, cp, 0x3b60, 1, 0x833);          /* bottom band */

    /* Row 1: five labels from one concatenated buffer, colour 8; the string cursor chains across. */
    Plane4 r1_lo, r1_hi;
    rm_color_fill(cp, LEG_ROW1_COLOR, COLOR_MASK_TEXT, &r1_lo, &r1_hi);
    Offset si = 0;
    Offset dst = 0xa10;
    for (int i = 0; i < LEG_LABEL_ROWS; i++, dst += LEG_ROW_DST_STEP)
        si = rm_glyph_run(fb, (Offset)sx16((uint16_t)dst), r1_lo, r1_hi, a->font, a->title, si,
                          TEXT_MAX_CELLS_M1, 0);

    /* Row 2: five per-leg label strings from buf_a, each with its own palette colour ([row - leg]). */
    dst = 0xa18;
    for (int i = 0; i < LEG_LABEL_ROWS; i++, dst += LEG_ROW_DST_STEP) {
        uint8_t colour = a->leg_palette[i - (int)leg];
        Plane4 fill_lo, fill_hi;
        rm_color_fill(cp, colour, COLOR_MASK_TEXT, &fill_lo, &fill_hi);
        rm_glyph_run(fb, (Offset)sx16((uint16_t)dst), fill_lo, fill_hi, a->font, a->row_names,
                     (Offset)(i * LEG_ROW_STR_STRIDE), TEXT_MAX_CELLS_M1, 0);
    }

    Plane4 d_lo, d_hi;
    rm_color_fill(cp, LEG_DIGITS_COLOR, COLOR_MASK_NUM, &d_lo, &d_hi);
    rm_num_run(fb, (Offset)sx16(0xa48), d_lo, d_hi, a->num_sprites, a->num_glyph_tbl,
               a->leg_digits, (Offset)(leg * LEG_ROW_STR_STRIDE), NUM_MAX_CELLS_M1);

    cell_dashboard(fb->px, (Offset)sx16(DASH_DST), a->gfx, DASH_SRC_OFF);
}
