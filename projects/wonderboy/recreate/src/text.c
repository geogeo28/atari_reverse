/* text.c — the glyph plotter at $bf4e..$c030, both entry points.
 *
 * WHAT THE 88 IS. The plotter writes one byte per plane at +0/+2/+4/+6 and then moves the cursor on
 * by WB_TEXT_BUFFER_LINE, which is NOT a 160-byte screen scanline. Its destination is the off-screen
 * message buffer at WB_TEXT_BUFFER, 88 bytes (176 pixels) wide; $bd8a composes a box there and
 * blits it out 88 bytes at a time with a 72-byte skip, and 88 + 72 is the screen's own 160. So the
 * row advance is the buffer's line, and the plotter is not a screen routine at all.
 *
 * WHY THE RETURNED CURSOR ALTERNATES. Four planes of two bytes make an 8-byte group holding TWO
 * 8-pixel cells: the high byte of each plane word and the low one. So the next cell is one byte on
 * from an even cursor and seven from an odd one — which the original spells as a `btst #0` on the
 * cursor its eight rows ENDED on and two `lea`s that rewind past the body.
 *
 * ONE DEVIATION, and it is arithmetic rather than behaviour. The original returns
 * `ended - 621` / `ended - 615`, where `ended` is the start plus the body it just walked; this
 * returns `cursor + 1` / `cursor + 7`, which is the same address for every input because the body
 * span and the two displacements are the same numbers. The image's own two displacements are
 * reconstructed from the geometry and pinned against the bytes by test/test_text.py, so a wrong
 * WB_TEXT_BUFFER_LINE fails at the entry rather than turning into a plausible cursor here.
 */
#include <stdint.h>

#include "machine.h"
#include "text.h"
#include "wonderboy.h"

/* Where the fourth plane byte of a row sits relative to the row's own start. */
#define TEXT_LAST_PLANE_OFFSET ((WB_PLANES - 1u) * WB_PLANE_STRIDE)

/* `subi.b #$20,d0` is a BYTE op: it changes d0's low byte and leaves the other three alone. */
#define TEXT_BYTE_MASK 0xffu

uint32_t text_plot_glyph(uint8_t *image, uint32_t glyph, uint32_t cursor) {
    uint32_t source = glyph;
    uint32_t row_at = cursor;

    for (unsigned row = 0; row < WB_TEXT_GLYPH_ROWS; row++) {
        for (unsigned plane = 0; plane < WB_PLANES; plane++) {
            image[addr_add(row_at, plane * WB_PLANE_STRIDE)] = image[source];
            source = addr_add(source, 1);
        }
        /* The LAST row has no advance — the original's seven `lea 82(a1),a1` sit between rows, and
         * that is what leaves the cursor mid-row for the parity test below. */
        if (row + 1 < WB_TEXT_GLYPH_ROWS)
            row_at = addr_add(row_at, WB_TEXT_BUFFER_LINE);
    }

    uint32_t ended = addr_add(row_at, TEXT_LAST_PLANE_OFFSET);
    return addr_add(cursor, (ended & 1u) ? WB_TEXT_CELL_ADVANCE_ODD : WB_TEXT_CELL_ADVANCE_EVEN);
}

uint32_t text_plot_char(uint8_t *image, uint32_t code, uint32_t cursor) {
    /* `subi.b #$20,d0` on the low byte only, `lsl.l #5,d0` on the whole longword, and then
     * `lea (0,a0,d0.w),a0` — a WORD index, SIGN-EXTENDED. The game only ever arrives here with a
     * zero-extended byte in d0, so the sign extension is reachable from a case and not from the
     * game; test/test_text.py seeds a d0 that reaches it. */
    uint32_t index = (code & ~(uint32_t)TEXT_BYTE_MASK)
                     | ((code - WB_TEXT_FIRST_GLYPH_CHAR) & TEXT_BYTE_MASK);
    uint32_t glyph = addr_add(WB_TEXT_GLYPH_TABLE, sign_ext16(index << WB_TEXT_GLYPH_SHIFT));

    return text_plot_glyph(image, glyph, cursor);
}
