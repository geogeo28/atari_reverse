/* text.c — text glyph blitters (shared body @ 0x5a2c).
 *
 * Four entry points draw a run of characters into the draw buffer, one 8-byte (16-pixel,
 * 4-plane) cell per character:
 *   draw_text        @ 0x159fa -> draw_text_row with the cell count preset to 0x13
 *   draw_text_row    @ 0x159fc   dst = buffer + D0.w, colour from D1, count from D5
 *   draw_hud_gauge0  @ 0x15a08   like draw_text_row but dst = A0 (caller-absolute)
 *   draw_hud_bar     @ 0x15a24   dst = A0, fill preset in D2/D3, count preset to 0x13
 * All four converge on one body: the string is character *pairs*. Each pair packs two 1bpp
 * FONT_GLYPHS entries into a single cell — char1's row word splits hi-byte -> AND mask,
 * lo-byte -> ink; char2's two row bytes do the same for the other pixel byte. Ink is masked
 * by the two colour planes (fill_lo/fill_hi) and OR'd in. A 0 first byte ends the string; a
 * 0 second byte substitutes glyph 0x2f and draws that one last cell.
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
static void blit_row(uint8_t *image, uint32_t cell, uint32_t mask, uint32_t ink,
                     uint32_t fill_lo, uint32_t fill_hi) {
    wr32(image + cell,     (be32(image + cell)     & mask) | (ink & fill_lo));
    wr32(image + cell + 4, (be32(image + cell + 4) & mask) | (ink & fill_hi));
}

/* Shared body: draw character pairs from str_ptr into dst until the string ends or the cell
 * budget (cells_m1 + 1) is exhausted. */
static void text_body(uint8_t *image, uint32_t dst, uint32_t fill_lo, uint32_t fill_hi,
                      uint32_t str_ptr, uint16_t cells_m1) {
    uint16_t remaining = cells_m1;
    do {
        uint8_t char1 = image[str_ptr];
        if (char1 == 0) return;
        uint8_t char2 = image[str_ptr + 1];
        str_ptr += 2;
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
    } while (remaining != 0xffff);
}

/* Draw buffer (physbase_tbl[flip_idx]) plus a sign-extended word offset (adda.w). */
static uint32_t buffer_dst(const uint8_t *image, uint32_t dst_off) {
    int16_t flip_idx = (int16_t)be16(image + A_flip_idx);
    return be32(image + A_physbase_tbl + flip_idx) + sign_ext16(dst_off);
}

/* fill_lo/fill_hi for a colour index: color_pairs[(idx & 0xf) << 3] and its +4 half. */
static void color_fill(const uint8_t *image, uint32_t color_idx, uint32_t *fill_lo, uint32_t *fill_hi) {
    uint16_t off = (uint16_t)((color_idx & 0xf) << 3);
    *fill_lo = be32(image + A_color_pairs + off);
    *fill_hi = be32(image + A_color_pairs + off + 4);
}

void g_draw_text(uint8_t *image, uint32_t dst_off, uint32_t color_idx, uint32_t str_ptr) {
    uint32_t fill_lo, fill_hi;
    color_fill(image, color_idx, &fill_lo, &fill_hi);
    text_body(image, buffer_dst(image, dst_off), fill_lo, fill_hi, str_ptr, TEXT_MAX_CELLS_M1);
}

void g_draw_text_row(uint8_t *image, uint32_t dst_off, uint32_t color_idx,
                     uint32_t cells_m1, uint32_t str_ptr) {
    uint32_t fill_lo, fill_hi;
    color_fill(image, color_idx, &fill_lo, &fill_hi);
    text_body(image, buffer_dst(image, dst_off), fill_lo, fill_hi, str_ptr, (uint16_t)cells_m1);
}

void g_draw_hud_gauge0(uint8_t *image, uint32_t dst, uint32_t color_idx,
                       uint32_t cells_m1, uint32_t str_ptr) {
    uint32_t fill_lo, fill_hi;
    color_fill(image, color_idx, &fill_lo, &fill_hi);
    text_body(image, dst, fill_lo, fill_hi, str_ptr, (uint16_t)cells_m1);
}

void g_draw_hud_bar(uint8_t *image, uint32_t dst, uint32_t fill_lo, uint32_t fill_hi, uint32_t str_ptr) {
    text_body(image, dst, fill_lo, fill_hi, str_ptr, TEXT_MAX_CELLS_M1);
}
