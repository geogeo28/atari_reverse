/* text.c — glyph blitters: text (shared body @ 0x5a2c), numbers (@ 0x5ab6), and the divider
 * + text panels (@ 0x26e6..) built on top of them.
 *
 * The text entries draw a run of characters into the draw buffer, one 8-byte (16-pixel,
 * 4-plane) cell per character:
 *   draw_text        @ 0x159fa -> draw_text_row with the cell count preset to 0x13
 *   draw_text_row    @ 0x159fc   dst = buffer + D0.w, colour from D1, count from D5
 *   draw_hud_gauge0  @ 0x15a08   like draw_text_row but dst = A0 (caller-absolute)
 *   draw_hud_bar     @ 0x15a24   dst = A0, fill preset in D2/D3, count preset to 0x13
 * All four converge on one body: the string is character *pairs*. Each pair packs two 1bpp
 * FONT_GLYPHS entries into a single cell — char1's row word splits hi-byte -> AND mask,
 * lo-byte -> ink; char2's two row bytes do the same for the other pixel byte. Ink is masked
 * by the two colour planes (fill_lo/fill_hi) and OR'd in. A 0 first byte ends the string; a
 * 0 second byte substitutes glyph 0x2f and draws that one last cell. The number entries
 * (draw_num/_thunk) blit pre-rendered digit sprites from buf_c instead — see num_body below.
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"
#include "draw.h"

#define TEXT_MAX_CELLS_M1  0x13    /* draw_text / draw_hud_bar preset cell count-1 */
#define LAST_HALF_GLYPH    0x2f    /* char2 substitute when the second byte is 0 */

/* Blit one character cell's row: (dst & mask) | (ink & plane) for each of the two planes. */
static void blit_row(uint8_t *image, uint32_t cell, uint32_t mask, uint32_t ink, uint32_t fill_lo, uint32_t fill_hi) {
    wr32(image + cell,     (be32(image + cell)     & mask) | (ink & fill_lo));
    wr32(image + cell + 4, (be32(image + cell + 4) & mask) | (ink & fill_hi));
}

/* Shared body: draw character pairs from str_ptr into dst until the string ends (a 0 first
 * byte) or the cell budget (cells_m1 + 1) is exhausted. Returns the advanced string pointer
 * (68k A3 at rts, past the 0-pair terminator); if end_dst is non-NULL it also reports the dst
 * left in A0 (one cell past the last drawn) so a following draw on the same registers (e.g.
 * draw_hud_bar after draw_text) can chain. */
static uint32_t text_body_ex(uint8_t *image, uint32_t dst, uint32_t fill_lo, uint32_t fill_hi,
                             uint32_t str_ptr, uint16_t cells_m1, uint32_t *end_dst) {
    uint16_t remaining = cells_m1;
    for (;;) {
        uint8_t char1 = image[str_ptr++];
        if (char1 == 0) break;
        uint8_t char2 = image[str_ptr++];
        if (char2 == 0) { char2 = LAST_HALF_GLYPH; remaining = 0; }

        uint32_t glyph1 = A_font_glyphs + char1 * GLYPH_BYTES;
        uint32_t glyph2 = A_font_glyphs + char2 * GLYPH_BYTES;
        uint32_t cell = dst;
        for (int row = 0; row < TEXT_CELL_ROWS; row++, cell += ROW_STRIDE, glyph1 += 2, glyph2 += 2) {
            uint16_t g1 = be16(image + glyph1);
            uint16_t g2 = be16(image + glyph2);
            uint16_t mask16, ink16;
            glyph_pair(g1, g2, &mask16, &ink16);
            blit_row(image, cell, dup16(mask16), dup16(ink16), fill_lo, fill_hi);
        }
        dst += CELL_WIDTH;
        remaining = (uint16_t)(remaining - 1);
        if (remaining == 0xffff) break;
    }
    if (end_dst) *end_dst = dst;
    return str_ptr + 1;                 /* addq.l #1,a3 on both exit paths (@0x5a80) */
}

static uint32_t text_body(uint8_t *image, uint32_t dst, uint32_t fill_lo, uint32_t fill_hi,
                          uint32_t str_ptr, uint16_t cells_m1) {
    return text_body_ex(image, dst, fill_lo, fill_hi, str_ptr, cells_m1, 0);
}

/* fill_lo/fill_hi for a colour index: color_pairs[(idx & idx_mask) << 3] and its +4 half.
 * The text path masks the index to 0xf; the number path uses the full word (idx_mask 0xffff). */
static void color_fill(const uint8_t *image, uint32_t color_idx, uint16_t idx_mask, uint32_t *fill_lo, uint32_t *fill_hi) {
    int16_t off = (int16_t)(uint16_t)((color_idx & idx_mask) << 3);
    *fill_lo = be32(image + A_color_pairs + (int32_t)off);
    *fill_hi = be32(image + A_color_pairs + (int32_t)off + 4);
}

/* draw_text (D0 dst, D1 colour, A3 string) returning the advanced A3 — orchestrators that
 * lay out several labels from one concatenated buffer chain calls through this. */
uint32_t draw_text_chain(uint8_t *image, uint32_t dst_off, uint32_t color_idx, uint32_t str_ptr) {
    uint32_t fill_lo, fill_hi;
    color_fill(image, color_idx, 0xf, &fill_lo, &fill_hi);
    return text_body(image, draw_dst(image, dst_off), fill_lo, fill_hi, str_ptr, TEXT_MAX_CELLS_M1);
}

void g_draw_text(uint8_t *image, uint32_t dst_off, uint32_t color_idx, uint32_t str_ptr) {
    draw_text_chain(image, dst_off, color_idx, str_ptr);
}

void g_draw_text_row(uint8_t *image, uint32_t dst_off, uint32_t color_idx, uint32_t cells_m1, uint32_t str_ptr) {
    uint32_t fill_lo, fill_hi;
    color_fill(image, color_idx, 0xf, &fill_lo, &fill_hi);
    text_body(image, draw_dst(image, dst_off), fill_lo, fill_hi, str_ptr, (uint16_t)cells_m1);
}

void g_draw_hud_gauge0(uint8_t *image, uint32_t dst, uint32_t color_idx, uint32_t cells_m1, uint32_t str_ptr) {
    uint32_t fill_lo, fill_hi;
    color_fill(image, color_idx, 0xf, &fill_lo, &fill_hi);
    text_body(image, dst, fill_lo, fill_hi, str_ptr, (uint16_t)cells_m1);
}

void g_draw_hud_bar(uint8_t *image, uint32_t dst, uint32_t fill_lo, uint32_t fill_hi, uint32_t str_ptr) {
    text_body(image, dst, fill_lo, fill_hi, str_ptr, TEXT_MAX_CELLS_M1);
}

/* draw_hud_bar returning the advanced A3 (past this bar's 0-terminated substring), so a caller
 * drawing consecutive bars from one string buffer chains them as the 68000 does (a3 persists). */
uint32_t draw_hud_bar_chain(uint8_t *image, uint32_t dst, uint32_t fill_lo, uint32_t fill_hi, uint32_t str_ptr) {
    return text_body_ex(image, dst, fill_lo, fill_hi, str_ptr, TEXT_MAX_CELLS_M1, 0);
}

/* draw_hud chains BOTH the dst (A0) and the string cursor (A3) across its gauge0/bar sub-draws,
 * exactly as the 68000 leaves those registers at each `rts`. These variants report the advanced
 * A0 via *end_dst (one cell past the last drawn) and return the advanced A3. draw_hud_gauge0
 * derives its fill from the colour index and inherits the caller's cell budget (D5); draw_hud_bar
 * takes the fill directly (D2/D3) and presets the budget to 0x13. */
uint32_t draw_hud_gauge0_chain(uint8_t *image, uint32_t dst, uint32_t color_idx, uint32_t cells_m1,
                               uint32_t str_ptr, uint32_t *end_dst) {
    uint32_t fill_lo, fill_hi;
    color_fill(image, color_idx, 0xf, &fill_lo, &fill_hi);
    return text_body_ex(image, dst, fill_lo, fill_hi, str_ptr, (uint16_t)cells_m1, end_dst);
}

uint32_t draw_hud_bar_chain_dst(uint8_t *image, uint32_t dst, uint32_t fill_lo, uint32_t fill_hi,
                                uint32_t str_ptr, uint32_t *end_dst) {
    return text_body_ex(image, dst, fill_lo, fill_hi, str_ptr, TEXT_MAX_CELLS_M1, end_dst);
}

/* --- number blitter (draw_num @ 0x15a86, draw_num_thunk @ 0x15a84) ---
 * Unlike the text body, digits are single string bytes and their sprites are pre-rendered
 * (by unpack_graphics) into buf_c at NUM_GLYPH_BUF_OFF, one 15-row sprite per digit laid out
 * at the screen row stride; num_glyph_tbl gives each digit's byte offset there. The per-row
 * blit is identical (word0 -> AND mask, word1 -> ink, two colour planes). */
#define NUM_CELL_ROWS      15      /* rows blitted per digit (dbf #$e) */
#define NUM_GLYPH_BUF_OFF  0xbb80  /* digit sprite buffer at buf_c + this (48000) */
#define NUM_MAX_CELLS_M1   0x13    /* draw_num_thunk preset cell count-1 */

static void num_body(uint8_t *image, uint32_t dst, uint32_t fill_lo, uint32_t fill_hi, uint32_t str_ptr, uint16_t cells_m1) {
    uint16_t remaining = cells_m1;
    uint32_t glyph_base = be32(image + A_buf_c) + NUM_GLYPH_BUF_OFF;
    do {
        uint8_t digit = image[str_ptr++];
        if (digit == 0) return;
        uint32_t src = glyph_base + be16(image + A_num_glyph_tbl + digit * 2);
        uint32_t cell = dst;
        for (int row = 0; row < NUM_CELL_ROWS; row++, cell += ROW_STRIDE, src += ROW_STRIDE) {
            uint32_t mask = dup16(be16(image + src));
            uint32_t ink  = dup16(be16(image + src + 2));
            blit_row(image, cell, mask, ink, fill_lo, fill_hi);
        }
        dst += CELL_WIDTH;
        remaining = (uint16_t)(remaining - 1);
    } while (remaining != 0xffff);
}

/* D0 dst offset, D1 colour (not masked, unlike text), D5 cell count-1, A3 digit string. */
void g_draw_num(uint8_t *image, uint32_t dst_off, uint32_t color_idx, uint32_t cells_m1, uint32_t str_ptr) {
    uint32_t fill_lo, fill_hi;
    color_fill(image, color_idx, 0xffff, &fill_lo, &fill_hi);
    num_body(image, draw_dst(image, dst_off), fill_lo, fill_hi, str_ptr, (uint16_t)cells_m1);
}

/* draw_num_thunk: draw_num with the cell count preset to 0x13. */
void g_draw_num_thunk(uint8_t *image, uint32_t dst_off, uint32_t color_idx, uint32_t str_ptr) {
    g_draw_num(image, dst_off, color_idx, NUM_MAX_CELLS_M1, str_ptr);
}

/* --- divider + text panels (draw_divider @ 0x126e6, draw_panel2/3/5 @ 0x1271c..) ---
 * draw_divider paints a filled rectangle then two vertical lines; each panel draws the
 * divider then a fixed set of labels. The labels are one concatenated ASCII buffer (two
 * chars per cell, 0-pair terminated); draw_text threads A3 across the calls, so each label
 * resumes where the previous one ended — text_body returns that advanced pointer. */
#define DIVIDER_FILL_DST      0x4118   /* fill_rect: D0 dst, D1 colour, D3 cells-1, D4 rows-1 */
#define DIVIDER_FILL_COLOR    3
#define DIVIDER_FILL_CELLS_M1 0xd
#define DIVIDER_FILL_ROWS_M1  0x57
#define DIVIDER_LINE_DST      0x411a   /* first vertical line; second is +DIVIDER_LINE_COL2 */
#define DIVIDER_LINE_COL2     0x68
#define DIVIDER_LINE_ROWS     0x58     /* 88 rows (dbf #$57) */
#define DIVIDER_LINE_LEFT     0x00ff   /* plane pattern written at the first line */
#define DIVIDER_LINE_RIGHT    0xff00   /* plane pattern written at the second line */
#define PANEL_TEXT_COLOR      7

void g_draw_divider(uint8_t *image) {
    g_fill_rect(image, DIVIDER_FILL_DST, DIVIDER_FILL_COLOR, DIVIDER_FILL_CELLS_M1, DIVIDER_FILL_ROWS_M1);
    uint32_t line = draw_dst(image, DIVIDER_LINE_DST);
    for (int row = 0; row < DIVIDER_LINE_ROWS; row++, line += ROW_STRIDE) {
        wr16(image + line, DIVIDER_LINE_LEFT);
        wr16(image + line + DIVIDER_LINE_COL2, DIVIDER_LINE_RIGHT);
    }
}

/* draw the divider then `count` labels from one concatenated buffer, chaining A3. */
static void draw_panel(uint8_t *image, uint32_t str_base, const uint16_t *label_dst, int count) {
    g_draw_divider(image);
    uint32_t fill_lo, fill_hi;
    color_fill(image, PANEL_TEXT_COLOR, 0xf, &fill_lo, &fill_hi);
    uint32_t str_ptr = str_base;
    for (int i = 0; i < count; i++)
        str_ptr = text_body(image, draw_dst(image, label_dst[i]), fill_lo, fill_hi, str_ptr, TEXT_MAX_CELLS_M1);
}

/* Label string bases (Ghidra addrs) and per-label dst offsets, baked into each panel. */
#define PANEL5_STR 0x1803c
#define PANEL3_STR 0x18092
#define PANEL2_STR 0x180d4

void g_draw_panel5(uint8_t *image) {
    static const uint16_t dst[] = {0x4620, 0x5028, 0x5a30, 0x6438, 0x6e20};
    draw_panel(image, PANEL5_STR, dst, 5);
}

void g_draw_panel3(uint8_t *image) {
    static const uint16_t dst[] = {0x5020, 0x5a28, 0x6430};
    draw_panel(image, PANEL3_STR, dst, 3);
}

void g_draw_panel2(uint8_t *image) {
    static const uint16_t dst[] = {0x5030, 0x5a38};
    draw_panel(image, PANEL2_STR, dst, 2);
}

/* --- draw_results_screen @ 0x1225a --- The race-end results screen. No register arguments;
 * it drives the fill/text/num/dashboard leaves, threading the 68k A3 (string cursor) across
 * chained draws. Two runtime state words shape it: results_mode (0/2) sets the label-row
 * count (9 - mode) and gates an extra block; hiscore_pos offsets the per-row colour palettes
 * and gates the score line. The second row pairs each label with a bar gauge drawn from the
 * label's leftover A0/fill (draw_hud_bar reuses the glyph body on the same registers). */
#define RESULTS_TITLE_STR    0x184f8   /* title; the buffer continues into the row-1 labels */
#define RESULTS_ROW2_STR     0x18266   /* = highscore_table; row 2 shows entry leg*0x80 + mode*0xe */
#define RESULTS_SCORE_STR    0x18258   /* score line (drawn when hiscore_pos != 0) */
#define RESULTS_MODE_STR     0x18538   /* extra block (drawn when results_mode != 0) */
#define RESULTS_MODE_STR2    0x18234
#define RESULTS_PALETTE_A    0x17ead   /* row-1 per-row colour bytes, indexed down by hiscore_pos */
#define RESULTS_PALETTE_B    0x17ebf   /* row-2 palette */
#define RESULTS_ROW_STEP     0x8c0     /* screen dst step between rows */
#define RESULTS_BAR_GAP      0x18      /* A0 advance from the label end to its bar gauge */
#define RESULTS_MAX_ROWS     8         /* row count = RESULTS_MAX_ROWS - mode + 1 (dbf #(8-mode)) */

void g_draw_results_screen(uint8_t *image) {
    g_fill_screen(image, 1);
    uint32_t str = draw_text_chain(image, 0x518, 0xc, RESULTS_TITLE_STR);   /* title */

    uint16_t mode = be16(image + A_results_mode);
    uint16_t pos  = be16(image + A_hiscore_pos);
    uint16_t leg  = be16(image + A_leg_index);

    /* Row 1: (9 - mode) chained labels, colour from palette A; A3 resumes past the title. */
    uint32_t pal_a = RESULTS_PALETTE_A - sign_ext16(pos);
    str += sign_ext16((uint16_t)(mode << 2));
    uint32_t dst = 0xde0;
    for (int16_t c = (int16_t)(RESULTS_MAX_ROWS - mode), i = 0; c != -1; c--, i++, dst += RESULTS_ROW_STEP)
        str = draw_text_chain(image, dst, image[pal_a + i], str);

    /* Row 2: (9 - mode) label+bar pairs; A3 starts fresh, colour from palette B. Each bar reuses
     * the label's leftover dst (+RESULTS_BAR_GAP) and fill; A3 then chains label->bar->+1. */
    uint32_t pal_b = RESULTS_PALETTE_B - sign_ext16(pos);
    str = RESULTS_ROW2_STR + (uint16_t)(leg << 7) + (uint16_t)(mode * 0xe);
    dst = 0xe00;
    for (int16_t c = (int16_t)(RESULTS_MAX_ROWS - mode), i = 0; c != -1; c--, i++, dst += RESULTS_ROW_STEP) {
        uint32_t fill_lo, fill_hi, label_end;
        color_fill(image, image[pal_b + i], 0xf, &fill_lo, &fill_hi);
        str = text_body_ex(image, draw_dst(image, dst), fill_lo, fill_hi, str, TEXT_MAX_CELLS_M1, &label_end);
        str = text_body(image, label_end + RESULTS_BAR_GAP, fill_lo, fill_hi, str, TEXT_MAX_CELLS_M1);
        str += 1;
    }

    draw_text_chain(image, 0x62c8, 0xd, be32(image + A_buf_a) + 0x80c + leg * 0xc);

    if (pos != 0) {                                    /* score line */
        str = draw_text_chain(image, 0x6340, 0xf, RESULTS_SCORE_STR);
        g_draw_num_thunk(image, 0x6980, 0xf, str);
    }
    if (mode != 0) {                                   /* extra label block */
        str = draw_text_chain(image, 0x4ed8, 0xe, RESULTS_MODE_STR);
        draw_text_chain(image, 0x53e0, 0xe, str);
        draw_text_chain(image, 0x5400, 0xe, RESULTS_MODE_STR2);
    }
    g_draw_dashboard(image, 0x6070);

    /* Final label: its screen dst is the first word of the string; A3 continues past it. */
    uint32_t fin = be32(image + A_buf_a) + 0x910 + leg * 0x10;
    draw_text_chain(image, be16(image + fin), 1, fin + 2);
}
