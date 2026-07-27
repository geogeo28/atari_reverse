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
#define DASH_DST     0x1948        /* draw-buffer offset the dashboard is stamped at */

/* ---- draw_leg_results ----
 * The background is laid down first as two CONTIGUOUS spans that between them cover the whole buffer:
 * the top fill runs from offset 0 for LEG_TOP_CELLS_M1+1 cells (= 15200 bytes, which is exactly
 * LEG_BOTTOM_DST) and the bottom band covers the rest, so the two counts sum to SCREEN_CELLS. The panel,
 * the four result blocks and the divider are then painted over it. */
#define LEG_LABEL_ROWS    5
#define LEG_ROW_DST_STEP  0xa00    /* screen dst step between label rows */
#define LEG_ROW_STR_STRIDE 0xc     /* bytes between per-row buf_a strings / digit records */
#define LEG_ROW1_COLOR    8
#define LEG_DIGITS_COLOR  4
#define NUM_MAX_CELLS_M1  0x13     /* draw_num_thunk preset cell count-1 — the leg rows AND the
                                    * score lines pass the same preset (one fact, one name) */

#define LEG_BG_COLOR       1       /* the screen background: both spans, and the divider that re-paints it */
#define LEG_TOP_CELLS_M1   0x76b   /* fill_words cell count-1: everything above LEG_BOTTOM_DST */
#define LEG_BOTTOM_DST     0x3b60  /* where the top fill ends and the bottom band begins */
#define LEG_BOTTOM_CELLS_M1 0x833  /* fill_span cell count-1: LEG_BOTTOM_DST to the end of the buffer */
#define LEG_PANEL_DST      0x9a8   /* results-panel background rectangle */
#define LEG_PANEL_COLOR    6
#define LEG_PANEL_CELLS_M1 8
#define LEG_PANEL_ROWS_M1  0x48
/* A one-cell-wide background stripe: byte column 144 of row 8, running 88 rows down. That column sits
 * just RIGHT of the panel (which spans columns 72..143 from row 15), and over its first 7 rows it repaints
 * the last cell of the LEG_RESULT_COL1 tile block (columns 72..151) — trimming that block back. It
 * does the same for LEG_RESULT_COL2's run (rows 88..94), which is why it spans all 88 rows. */
#define LEG_DIVIDER_DST    0x590
#define LEG_DIVIDER_CELLS_M1 0     /* one cell wide (the sibling fills name their count, so name this too) */
#define LEG_DIVIDER_ROWS_M1 0x57
/* The four result panels: two masked-row blits stacked down, two tiled-column copies. Each is a
 * (draw-buffer dst, buf_c arena offset) pair — a->gfx is the UNPACKED graphics arena, so these index
 * decoded bytes, not offsets into the GRAPHICS.GRA file. */
#define LEG_RESULT_ROW1_DST 0x540
#define LEG_RESULT_ROW1_SRC 0x12430
#define LEG_RESULT_ROW2_DST 0x588
#define LEG_RESULT_ROW2_SRC 0x12438
#define LEG_RESULT_COL1_DST 0x548
#define LEG_RESULT_COL1_SRC 0x11a30
#define LEG_RESULT_COL2_DST 0x3748
#define LEG_RESULT_COL2_SRC 0x11f30
#define LEG_ROW1_DST       0xa10   /* first label of the chained row-1 run */
#define LEG_ROW2_DST       0xa18   /* first label of the per-leg row-2 run */
#define LEG_DIGITS_DST     0xa48   /* the leg-time digits */

void rm_draw_leg_results(Framebuffer *fb, const RmResultsAssets *a, uint16_t leg) {
    const uint8_t *cp = a->color_pairs;
    rm_fill_words(fb, cp, LEG_BG_COLOR, LEG_TOP_CELLS_M1);
    rm_fill_rect(fb, cp, LEG_PANEL_DST, LEG_PANEL_COLOR, LEG_PANEL_CELLS_M1, LEG_PANEL_ROWS_M1);
    draw_result_row(fb, a->gfx, LEG_RESULT_ROW1_DST, LEG_RESULT_ROW1_SRC);
    draw_result_row(fb, a->gfx, LEG_RESULT_ROW2_DST, LEG_RESULT_ROW2_SRC);
    draw_result_col(fb, a->gfx, LEG_RESULT_COL1_DST, LEG_RESULT_COL1_SRC);
    draw_result_col(fb, a->gfx, LEG_RESULT_COL2_DST, LEG_RESULT_COL2_SRC);
    rm_fill_rect(fb, cp, LEG_DIVIDER_DST, LEG_BG_COLOR, LEG_DIVIDER_CELLS_M1, LEG_DIVIDER_ROWS_M1);
    rm_fill_span(fb, cp, LEG_BOTTOM_DST, LEG_BG_COLOR, LEG_BOTTOM_CELLS_M1);

    /* Row 1: five labels from one concatenated buffer, colour 8; the string cursor chains across. */
    Plane4 r1_lo, r1_hi;
    rm_color_fill(cp, LEG_ROW1_COLOR, COLOR_MASK_TEXT, &r1_lo, &r1_hi);
    Offset si = 0;
    Offset dst = LEG_ROW1_DST;
    for (int i = 0; i < LEG_LABEL_ROWS; i++, dst += LEG_ROW_DST_STEP)
        si = rm_glyph_run(fb, (Offset)sx16((uint16_t)dst), r1_lo, r1_hi, a->font, a->title, si,
                          TEXT_MAX_CELLS_M1, 0);

    /* Row 2: five per-leg label strings from buf_a, each with its own palette colour ([row - leg]). */
    dst = LEG_ROW2_DST;
    for (int i = 0; i < LEG_LABEL_ROWS; i++, dst += LEG_ROW_DST_STEP) {
        uint8_t colour = a->leg_palette[i - (int)leg];
        Plane4 fill_lo, fill_hi;
        rm_color_fill(cp, colour, COLOR_MASK_TEXT, &fill_lo, &fill_hi);
        rm_glyph_run(fb, (Offset)sx16((uint16_t)dst), fill_lo, fill_hi, a->font, a->row_names,
                     (Offset)(i * LEG_ROW_STR_STRIDE), TEXT_MAX_CELLS_M1, 0);
    }

    Plane4 d_lo, d_hi;
    rm_color_fill(cp, LEG_DIGITS_COLOR, COLOR_MASK_NUM, &d_lo, &d_hi);
    rm_num_run(fb, (Offset)sx16(LEG_DIGITS_DST), d_lo, d_hi, a->num_sprites, a->num_glyph_tbl,
               a->leg_digits, (Offset)(leg * LEG_ROW_STR_STRIDE), NUM_MAX_CELLS_M1);

    cell_dashboard(fb->px, (Offset)sx16(DASH_DST), a->gfx, RM_DASH_SRC_OFF);
}

/* ---- leg-name menu panel (recreate's g_draw_divider / draw_panel / g_draw_panel5 @text.c) ----
 *
 * The right-hand leg-select menu: a divider (a colour-3 rectangle bounded by two vertical lines) then
 * a column of colour-7 labels chained from one concatenated string. It overlays the leg-select and
 * get-ready screens; the attract results-carousel (Phase D) does NOT draw it. */
#define DIVIDER_FILL_DST   0x4118      /* fill_rect: dst, colour 3, DIVIDER_FILL_CELLS_M1 x _ROWS_M1 */
#define DIVIDER_FILL_COLOR 3
#define DIVIDER_FILL_CELLS_M1 0xd
#define DIVIDER_FILL_ROWS_M1  0x57
#define DIVIDER_LINE_DST   0x411a      /* first vertical line; the second is +DIVIDER_LINE_COL2 */
#define DIVIDER_LINE_COL2  0x68
#define DIVIDER_LINE_ROWS  0x58        /* 88 rows */
#define DIVIDER_LINE_LEFT  0x00ff      /* plane pattern at the first line */
#define DIVIDER_LINE_RIGHT 0xff00      /* plane pattern at the second line */
#define PANEL_TEXT_COLOR   7

void rm_draw_divider(Framebuffer *fb, const uint8_t *color_pairs) {
    rm_fill_rect(fb, color_pairs, DIVIDER_FILL_DST, DIVIDER_FILL_COLOR,
                 DIVIDER_FILL_CELLS_M1, DIVIDER_FILL_ROWS_M1);
    uint8_t *px = fb->px;
    Offset line = (Offset)sx16(DIVIDER_LINE_DST);
    for (int row = 0; row < DIVIDER_LINE_ROWS; row++, line += ROW_STRIDE) {
        wr16(px + line, DIVIDER_LINE_LEFT);
        wr16(px + line + DIVIDER_LINE_COL2, DIVIDER_LINE_RIGHT);
    }
}

/* Draw the divider then `count` colour-7 labels from one concatenated string, chaining the cursor
 * (recreate's draw_panel: each text run resumes where the previous one ended). */
static void draw_panel(Framebuffer *fb, const uint8_t *color_pairs, const uint8_t *font,
                       const uint8_t *str, const uint16_t *label_dst, int count) {
    rm_draw_divider(fb, color_pairs);
    Plane4 fill_lo, fill_hi;
    rm_color_fill(color_pairs, PANEL_TEXT_COLOR, COLOR_MASK_TEXT, &fill_lo, &fill_hi);
    Offset si = 0;
    for (int i = 0; i < count; i++)
        si = rm_glyph_run(fb, (Offset)sx16(label_dst[i]), fill_lo, fill_hi, font, str, si,
                          TEXT_MAX_CELLS_M1, 0);
}

void rm_draw_panel5(Framebuffer *fb, const RmResultsAssets *a) {
    static const uint16_t dst[] = {0x4620, 0x5028, 0x5a30, 0x6438, 0x6e20};
    draw_panel(fb, a->color_pairs, a->font, a->panel5_str, dst, 5);
}

/* The F10 reload-menu panels (recreate's g_draw_panel3 / g_draw_panel2): same divider + chained-label
 * body as panel5, with the reload prompt's / confirmation's own label string and per-label dst offsets. */
void rm_draw_panel3(Framebuffer *fb, const RmResultsAssets *a) {
    static const uint16_t dst[] = {0x5020, 0x5a28, 0x6430};
    draw_panel(fb, a->color_pairs, a->font, a->panel3_str, dst, 3);
}

void rm_draw_panel2(Framebuffer *fb, const RmResultsAssets *a) {
    static const uint16_t dst[] = {0x5030, 0x5a38};
    draw_panel(fb, a->color_pairs, a->font, a->panel2_str, dst, 2);
}

/* ---- draw_results_screen (recreate's g_draw_results_screen @0x1225a) — the RACE-END / name-entry
 * results screen. Distinct from draw_leg_results (the between-legs carousel): its own title, palettes
 * and strings. Two runtime words shape it: `mode` (0 = the score made the table / name entry, 2 =
 * missed) sets the row count (9 - mode) and gates the "missed" label block; `pos` (1-based rank, 0 =
 * none) offsets the per-row palette cursors and gates the score / "TIME nn" line. Row 1 chains one
 * concatenated buffer (a->title, resuming past the title) across (9 - mode) labels; row 2 draws the
 * highscore rows, each a label+bar gauge pair reusing the label's leftover dst + fill. */
#define RS_FILL_COLOR      1
#define RS_TITLE_DST       0x518
#define RS_TITLE_COLOR     0xc
#define RS_MAX_ROWS        8          /* row count = RS_MAX_ROWS - mode + 1 (dbf #(8-mode)) */
#define RS_ROW1_DST        0xde0
#define RS_ROW_STEP        0x8c0      /* screen dst step between rows */
#define RS_ROW2_DST        0xe00
#define RS_BAR_GAP         0x18       /* dst advance from the label end to its bar gauge */
/* row 2 base = leg * HS_LEG_STRIDE + mode * HS_ROW into the highscore table (mode skips the top
 * `mode` already-known rows). Geometry shared with the flow — HS_LEG_STRIDE / HS_ROW from flow.h. */
#define RS_LEGTIME_DST     0x62c8
#define RS_LEGTIME_COLOR   0xd
#define RS_LEGTIME_OFF     0x80c      /* buf_a + this + leg * RS_LEGTIME_STRIDE: the leg-time string */
#define RS_LEGTIME_STRIDE  0xc
#define RS_SCORE_DST       0x6340
#define RS_SCORE_COLOR     0xf
#define RS_SCORE_NUM_DST   0x6980     /* the digits, from the score-line cursor past its label */
#define RS_MODE_DST1       0x4ed8
#define RS_MODE_DST2       0x53e0
#define RS_MODE_DST3       0x5400
#define RS_MODE_COLOR      0xe
#define RS_MODE_STR2_OFF   0xc2       /* hud_text + this = image 0x18234 (the third missed-block label) */
#define RS_DASH_DST        0x6070     /* the per-leg dashboard graphic (same src as leg-results) */
#define RS_FINAL_OFF       0x910      /* buf_a + this + leg * 0x10: word0 = screen dst, +2 = the string */
#define RS_FINAL_STRIDE    0x10
#define RS_FINAL_COLOR     1

/* draw_text (D0 dst, D1 colour, A3 string) returning the advanced string index — the results screen
 * chains several labels from one buffer through this, exactly as recreate threads A3. */
static Offset rs_text_chain(Framebuffer *fb, const uint8_t *cp, const uint8_t *font,
                            uint16_t dst, uint16_t color, const uint8_t *str, Offset si) {
    Plane4 lo, hi;
    rm_color_fill(cp, color, COLOR_MASK_TEXT, &lo, &hi);
    return rm_glyph_run(fb, (Offset)sx16(dst), lo, hi, font, str, si, TEXT_MAX_CELLS_M1, 0);
}

void rm_draw_results_screen(Framebuffer *fb, const RmResultsScreenAssets *a,
                            uint16_t mode, uint16_t pos, uint16_t leg) {
    const uint8_t *cp = a->color_pairs;
    const uint8_t *font = a->font;
    rm_fill_screen(fb, cp, RS_FILL_COLOR);

    /* Title (colour 0xc); row 1's (9 - mode) labels then chain on through the same title buffer. */
    Offset si = rs_text_chain(fb, cp, font, RS_TITLE_DST, RS_TITLE_COLOR, a->title, 0);
    si += (Offset)sx16((uint16_t)(mode << 2));
    const uint8_t *pal_a = a->palette_a;             /* cursor at 0x17ead, indexed [i - pos] */
    Offset dst = RS_ROW1_DST;
    for (int16_t c = (int16_t)(RS_MAX_ROWS - mode), i = 0; c != -1; c--, i++, dst += RS_ROW_STEP)
        si = rs_text_chain(fb, cp, font, (uint16_t)dst, pal_a[i - (int)pos], a->title, si);

    /* Row 2: (9 - mode) label+bar pairs from the highscore table, colour from palette B. Each bar
     * reuses the label's leftover dst (+RS_BAR_GAP) and fill; the cursor chains label -> bar -> +1. */
    const uint8_t *pal_b = a->palette_b;
    const uint8_t *hs = a->highscore;
    Offset hsi = (Offset)((uint16_t)(leg * HS_LEG_STRIDE) + (uint16_t)(mode * HS_ROW));
    dst = RS_ROW2_DST;
    for (int16_t c = (int16_t)(RS_MAX_ROWS - mode), i = 0; c != -1; c--, i++, dst += RS_ROW_STEP) {
        Plane4 lo, hi;
        rm_color_fill(cp, pal_b[i - (int)pos], COLOR_MASK_TEXT, &lo, &hi);
        Offset label_end;
        hsi = rm_glyph_run(fb, (Offset)sx16((uint16_t)dst), lo, hi, font, hs, hsi, TEXT_MAX_CELLS_M1, &label_end);
        hsi = rm_glyph_run(fb, label_end + RS_BAR_GAP, lo, hi, font, hs, hsi, TEXT_MAX_CELLS_M1, 0);
        hsi += 1;
    }

    rs_text_chain(fb, cp, font, RS_LEGTIME_DST, RS_LEGTIME_COLOR, a->buf_a,
                  (Offset)(RS_LEGTIME_OFF + leg * RS_LEGTIME_STRIDE));

    if (pos != 0) {                                  /* the score / "TIME nn" line (drawn only when ranked) */
        Offset ssi = rs_text_chain(fb, cp, font, RS_SCORE_DST, RS_SCORE_COLOR, a->score_line, 0);
        Plane4 lo, hi;
        rm_color_fill(cp, RS_SCORE_COLOR, COLOR_MASK_NUM, &lo, &hi);
        rm_num_run(fb, (Offset)sx16(RS_SCORE_NUM_DST), lo, hi, a->num_sprites, a->num_glyph_tbl,
                   a->score_line, ssi, NUM_MAX_CELLS_M1);
    }
    if (mode != 0) {                                 /* the "missed the table" label block */
        Offset msi = rs_text_chain(fb, cp, font, RS_MODE_DST1, RS_MODE_COLOR, a->mode_str, 0);
        rs_text_chain(fb, cp, font, RS_MODE_DST2, RS_MODE_COLOR, a->mode_str, msi);
        rs_text_chain(fb, cp, font, RS_MODE_DST3, RS_MODE_COLOR, a->hud_text, RS_MODE_STR2_OFF);
    }
    cell_dashboard(fb->px, (Offset)sx16(RS_DASH_DST), a->gfx, RM_DASH_SRC_OFF);

    /* Final label: buf_a[final]'s first word is its screen dst, the string follows at +2. */
    Offset fin = (Offset)(RS_FINAL_OFF + leg * RS_FINAL_STRIDE);
    rs_text_chain(fb, cp, font, be16(a->buf_a + fin), RS_FINAL_COLOR, a->buf_a, fin + 2);
}
