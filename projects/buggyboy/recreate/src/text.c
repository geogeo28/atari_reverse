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

#define GLYPH_BYTES        16      /* FONT_GLYPHS stride per character (char << 4) */
#define CELL_WIDTH         8       /* bytes to the next character column */
#define TEXT_MAX_CELLS_M1  0x13    /* draw_text / draw_hud_bar preset cell count-1 */
#define LAST_HALF_GLYPH    0x2f    /* char2 substitute when the second byte is 0 */

/* Duplicate a 16-bit pattern into both halves of a longword (68k swap + move.w idiom). */
static uint32_t dup16(uint16_t word) { return ((uint32_t)word << 16) | word; }

/* Blit one character cell's row: (dst & mask) | (ink & plane) for each of the two planes. */
static void blit_row(uint8_t *image, uint32_t cell, uint32_t mask, uint32_t ink, uint32_t fill_lo, uint32_t fill_hi) {
    wr32(image + cell,     (be32(image + cell)     & mask) | (ink & fill_lo));
    wr32(image + cell + 4, (be32(image + cell + 4) & mask) | (ink & fill_hi));
}

/* Shared body: draw character pairs from str_ptr into dst until the string ends (a 0 first
 * byte) or the cell budget (cells_m1 + 1) is exhausted. Returns the advanced string pointer
 * (68k A3 at rts, past the 0-pair terminator) so panel layouts can chain calls. */
static uint32_t text_body(uint8_t *image, uint32_t dst, uint32_t fill_lo, uint32_t fill_hi, uint32_t str_ptr, uint16_t cells_m1) {
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
            uint32_t mask = dup16((uint16_t)((g1 & 0xff00) | (g2 >> 8)));
            uint32_t ink  = dup16((uint16_t)(((g1 & 0x00ff) << 8) | (g2 & 0x00ff)));
            blit_row(image, cell, mask, ink, fill_lo, fill_hi);
        }
        dst += CELL_WIDTH;
        remaining = (uint16_t)(remaining - 1);
        if (remaining == 0xffff) break;
    }
    return str_ptr + 1;                 /* addq.l #1,a3 on both exit paths (@0x5a80) */
}

/* Draw buffer (physbase_tbl[flip_idx]) plus a sign-extended word offset (adda.w). */
static uint32_t buffer_dst(const uint8_t *image, uint32_t dst_off) {
    int16_t flip_idx = (int16_t)be16(image + A_flip_idx);
    return be32(image + A_physbase_tbl + flip_idx) + sign_ext16(dst_off);
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
    return text_body(image, buffer_dst(image, dst_off), fill_lo, fill_hi, str_ptr, TEXT_MAX_CELLS_M1);
}

void g_draw_text(uint8_t *image, uint32_t dst_off, uint32_t color_idx, uint32_t str_ptr) {
    draw_text_chain(image, dst_off, color_idx, str_ptr);
}

void g_draw_text_row(uint8_t *image, uint32_t dst_off, uint32_t color_idx, uint32_t cells_m1, uint32_t str_ptr) {
    uint32_t fill_lo, fill_hi;
    color_fill(image, color_idx, 0xf, &fill_lo, &fill_hi);
    text_body(image, buffer_dst(image, dst_off), fill_lo, fill_hi, str_ptr, (uint16_t)cells_m1);
}

void g_draw_hud_gauge0(uint8_t *image, uint32_t dst, uint32_t color_idx, uint32_t cells_m1, uint32_t str_ptr) {
    uint32_t fill_lo, fill_hi;
    color_fill(image, color_idx, 0xf, &fill_lo, &fill_hi);
    text_body(image, dst, fill_lo, fill_hi, str_ptr, (uint16_t)cells_m1);
}

void g_draw_hud_bar(uint8_t *image, uint32_t dst, uint32_t fill_lo, uint32_t fill_hi, uint32_t str_ptr) {
    text_body(image, dst, fill_lo, fill_hi, str_ptr, TEXT_MAX_CELLS_M1);
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
    num_body(image, buffer_dst(image, dst_off), fill_lo, fill_hi, str_ptr, (uint16_t)cells_m1);
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
    uint32_t line = buffer_dst(image, DIVIDER_LINE_DST);
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
        str_ptr = text_body(image, buffer_dst(image, label_dst[i]), fill_lo, fill_hi, str_ptr, TEXT_MAX_CELLS_M1);
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
