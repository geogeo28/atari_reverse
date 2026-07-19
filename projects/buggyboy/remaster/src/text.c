/* text.c — remaster glyph blitter (recreate's text_body @0x5a2c; see text.h).
 *
 * Font glyphs are 1bpp, 16 bytes each (8 rows x 2 bytes). A character *pair* packs into one 4-plane
 * cell: char1's row word gives the high byte of the cell's (mask, ink) words, char2's the low byte.
 * The ink is masked by the two colour planes (fill_lo/fill_hi) and OR'd over the background.
 */
#include "text.h"
#include "screen.h"
#include "st.h"

#define ROW_STRIDE      SCREEN_ROW_BYTES
#define CELL_WIDTH      8       /* bytes to the next character cell (16 px, 4 planes) */
#define LAST_HALF_GLYPH 0x2f    /* char2 substitute when the second byte is 0 ('/' -> blank) */

/* Pack two 1bpp glyph row words into a cell's (mask, ink): char1 -> high byte, char2 -> low byte. */
static void glyph_pair(uint16_t g1, uint16_t g2, uint16_t *mask, uint16_t *ink) {
    *mask = (uint16_t)((g1 & 0xff00) | (g2 >> 8));
    *ink  = (uint16_t)(((g1 & 0x00ff) << 8) | (g2 & 0x00ff));
}

/* One cell row: (bg & mask) | (ink & plane) for each of the two 16-px plane pairs. mask/ink are
 * already broadcast into both halves of the long. */
static void blit_row(uint8_t *px, Offset cell, Plane4 mask, Plane4 ink,
                     Plane4 fill_lo, Plane4 fill_hi) {
    wr32(px + cell,     (be32(px + cell)     & mask) | (ink & fill_lo));
    wr32(px + cell + 4, (be32(px + cell + 4) & mask) | (ink & fill_hi));
}

Offset rm_glyph_run(uint8_t *px, Offset dst, Plane4 fill_lo, Plane4 fill_hi,
                    const uint8_t *font, const uint8_t *str, Offset si,
                    uint16_t cells_m1, Offset *end_dst) {
    uint16_t remaining = cells_m1;
    for (;;) {
        uint8_t char1 = str[si++];
        if (char1 == 0) break;
        uint8_t char2 = str[si++];
        if (char2 == 0) { char2 = LAST_HALF_GLYPH; remaining = 0; }   /* draw this last cell only */

        const uint8_t *glyph1 = font + char1 * GLYPH_BYTES;
        const uint8_t *glyph2 = font + char2 * GLYPH_BYTES;
        Offset cell = dst;
        for (int row = 0; row < TEXT_CELL_ROWS; row++, cell += ROW_STRIDE, glyph1 += 2, glyph2 += 2) {
            uint16_t mask16, ink16;
            glyph_pair(be16(glyph1), be16(glyph2), &mask16, &ink16);
            blit_row(px, cell, dup16(mask16), dup16(ink16), fill_lo, fill_hi);
        }
        dst += CELL_WIDTH;
        if (--remaining == 0xffff) break;                            /* budget exhausted */
    }
    if (end_dst) *end_dst = dst;
    return si + 1;                                                   /* addq.l #1,a3 on both exits */
}
