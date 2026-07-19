/* text.h — remaster of the shared glyph blitter (recreate's text_body @0x5a2c).
 *
 * Draws a run of paired-glyph character cells into the framebuffer. Each cell is 8 bytes (16 px, 4
 * planes); the string is character *pairs* packed one pair per cell (char1 -> the cell's first pixel
 * byte, char2 -> the second). recreate's draw_hud_gauge0 / draw_hud_bar / draw_text all converge on
 * this body — here it is one native primitive the HUD's gauge cluster (phases 6b/7) builds on.
 */
#ifndef RM_TEXT_H
#define RM_TEXT_H

#include "st.h"

#define GLYPH_BYTES     16     /* 8 rows x 2 bytes per 1bpp glyph; char N at font + N*16 */
#define TEXT_CELL_ROWS  8      /* rows blitted per character cell */
#define TEXT_MAX_CELLS_M1 0x13 /* draw_hud_bar / draw_text preset cell count-1 */

/* Draw glyph pairs from str[si..] into px at byte offset `dst`, tinted by (fill_lo, fill_hi), for at
 * most cells_m1+1 cells. Stops early on a 0 first byte; a 0 second byte substitutes glyph 0x2f and
 * ends after that cell. Returns the advanced string index (past the terminator, +1, as the 68k
 * leaves A3); if end_dst is non-NULL, reports the dst one cell past the last drawn so consecutive
 * runs chain on the same cursors. font points at the glyph table base (glyph N at font + N*16). */
Offset rm_glyph_run(uint8_t *px, Offset dst, Plane4 fill_lo, Plane4 fill_hi,
                    const uint8_t *font, const uint8_t *str, Offset si,
                    uint16_t cells_m1, Offset *end_dst);

#endif /* RM_TEXT_H */
