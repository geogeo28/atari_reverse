/* text.c — the message box: its once-a-frame driver at $bd8a and the glyph plotter at $bf4e..$c030.
 *
 * THE LIFECYCLE, which is what $bd8a turned out to be. game_main_loop's one `jsr $bd8a.l` runs it
 * every frame and it has three arms, picked by the two flag bytes:
 *
 *   * WB_TEXT_REQUEST != 0 — a message id was posted since the last frame. WB_TEXT_REQUEST_DISMISS
 *     takes the box down and composes nothing; any other value is a 1-based index into the message
 *     table, whose record gives the box's height and its top scanline and then the string. The box
 *     is COMPOSED into WB_TEXT_BUFFER on this frame and deliberately NOT blitted — that arm returns
 *     at the end of the string, so the first frame a message is requested on draws nothing.
 *   * WB_TEXT_REQUEST == 0 and WB_TEXT_BOX_ACTIVE != 0 — the box is up. Tick its countdown if one
 *     was ever armed, then blit the already-composed buffer to WB_SCREEN_BACK. This is the arm that
 *     runs on all but one frame of a message's life: the buffer is composed once and re-blitted,
 *     which is why the buffer exists at all.
 *   * both zero — nothing to do, and no byte is written.
 *
 * So the buffer is a CACHE, not a scratchpad, and WB_TEXT_BOX_ROWS / WB_TEXT_BOX_TOP_LINE are what
 * carry the composed box's geometry from the compose frame to every blit frame after it.
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
#include "scroll.h"     /* copy_constant_longwords — the blit below is that run of `move.l (a0)+,(a1)+` */
#include "text.h"
#include "wonderboy.h"

/* The box's row is a STRAIGHT run of `move.l (a0)+,(a1)+`, spelt by scroll.h's ladder — which can
 * only spell a run it has a case for, and copies NOTHING past that. */
_Static_assert(WB_TEXT_BLIT_LONGWORDS <= COPY_CONSTANT_RUN_MAX_LONGWORDS,
               "the message box's row must be a length copy_constant_run has a case for");

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

/* --- $bd8a: the message box's frame ------------------------------------------------------------ */

/* The eight frame glyphs, in the order the original's eight `bsr text_plot_glyph` sites pass them.
 * Each row's three glyphs are consecutive, which is what `plot_frame_row` indexes by. */
enum {
    FRAME_TOP_LEFT, FRAME_TOP_EDGE, FRAME_TOP_RIGHT,
    FRAME_LEFT_EDGE, FRAME_RIGHT_EDGE,
    FRAME_BOTTOM_LEFT, FRAME_BOTTOM_EDGE, FRAME_BOTTOM_RIGHT,
};

static uint32_t frame_glyph(unsigned role) {
    return WB_TEXT_FRAME_GLYPHS + role * WB_TEXT_GLYPH_BYTES;
}

/* `move.w #$63f,d0 / lea $c03a.l,a0 / clr.l (a0)+ / dbf` — the whole buffer, every compose. */
static void clear_message_buffer(uint8_t *image) {
    for (uint32_t at = 0; at < WB_TEXT_BUFFER_LEN; at += sizeof(uint32_t))
        wr32(image + WB_TEXT_BUFFER + at, 0);
}

/* One horizontal frame row: the left corner, WB_TEXT_BOX_EDGE_CELLS of the edge glyph under a
 * `dbf`, then the right corner. `left_corner` picks which row — the three glyphs it uses are that
 * one and the two after it. */
static uint32_t plot_frame_row(uint8_t *image, uint32_t cursor, unsigned left_corner) {
    cursor = text_plot_glyph(image, frame_glyph(left_corner), cursor);

    uint16_t remaining = WB_TEXT_BOX_EDGE_CELLS - 1u;   /* `move.w #$13,d0` */
    do {
        cursor = text_plot_glyph(image, frame_glyph(left_corner + 1u), cursor);
    } while (remaining-- != 0);

    return text_plot_glyph(image, frame_glyph(left_corner + 2u), cursor);
}

/* The box outline: the top row, WB_TEXT_BOX_ROWS - 2 interior rows of two edge cells, the bottom
 * row. Only the height varies; the width is the WB_TEXT_BOX_CELLS the unrolled top row spells. */
static void plot_message_frame(uint8_t *image, uint8_t rows) {
    uint32_t cursor = plot_frame_row(image, WB_TEXT_BUFFER, FRAME_TOP_LEFT);
    cursor = addr_add(cursor, WB_TEXT_ROW_ADVANCE);

    /* `move.b $c032,d0 / subq.w #3,d0` then `dbf`: a height below WB_TEXT_BOX_MIN_ROWS wraps the
     * WORD count and would draw 65536 rows. Reproduced by construction (uint16_t, do/while) and out
     * of reach through the shipped table, whose smallest height is WB_TEXT_BOX_MIN_ROWS exactly. */
    uint16_t remaining = (uint16_t)(rows - WB_TEXT_BOX_MIN_ROWS);
    do {
        cursor = text_plot_glyph(image, frame_glyph(FRAME_LEFT_EDGE), cursor);
        cursor = addr_add(cursor, WB_TEXT_INTERIOR_SKIP);
        cursor = text_plot_glyph(image, frame_glyph(FRAME_RIGHT_EDGE), cursor);
        cursor = addr_add(cursor, WB_TEXT_ROW_ADVANCE);
    } while (remaining-- != 0);

    plot_frame_row(image, cursor, FRAME_BOTTOM_LEFT);
}

/* Where a text line starts: `lea $c03b.l,a1 / mulu.w #$2c0,d1 / lea (0,a1,d1.w),a1`. The multiply
 * is 32-bit but the index is its LOW WORD, SIGN-EXTENDED. */
static uint32_t text_line_cursor(uint16_t line) {
    return addr_add(WB_TEXT_TEXT_ORIGIN, sign_ext16((uint32_t)line * WB_TEXT_CELL_ROW_BYTES));
}

/* The record's string. WB_TEXT_NEWLINE is tested BEFORE the terminator, and nothing clamps a line
 * to the box's WB_TEXT_BOX_EDGE_CELLS interior — the shipped data has one message whose longest
 * line is 21 characters and really does overwrite the frame's right edge (test_text.py states it,
 * and also that no line is long enough to run off the buffer row). */
static void plot_message_text(uint8_t *image, uint32_t string) {
    uint16_t line = WB_TEXT_FIRST_TEXT_LINE;
    uint32_t cursor = text_line_cursor(line);

    for (;;) {
        uint8_t code = image[string];
        string = addr_add(string, 1);

        if (code == WB_TEXT_NEWLINE) {
            /* `addq.l #1,d6` is a longword add on a register only `move.w #$1,d6` ever wrote, but
             * every reader of it takes the low word — so a 16-bit counter is the same line. */
            line++;
            cursor = text_line_cursor(line);
            continue;
        }
        if (code == WB_TEXT_STRING_END)
            return;

        cursor = text_plot_char(image, code, cursor);
    }
}

/* The arm WB_TEXT_REQUEST picks: latch the message's geometry, then draw it into the buffer. */
static void compose_requested_message(uint8_t *image, uint8_t request) {
    if (request == WB_TEXT_REQUEST_DISMISS) {
        image[WB_TEXT_REQUEST] = 0;
        image[WB_TEXT_BOX_ACTIVE] = 0;
        return;
    }

    /* A lifetime posted alongside the request is latched here and the countdown armed.
     * WB_TEXT_LIFETIME_ARMED has only two operand sites in the whole image — this write and the
     * `tst.w` on the blit arm — so nothing ever disarms it: once one timed message has been shown,
     * every later box ticks WB_TEXT_LIFETIME_LEFT whether or not it asked for a lifetime. */
    if (be16(image + WB_TEXT_LIFETIME_REQUEST) != 0) {
        wr16(image + WB_TEXT_LIFETIME_LEFT, be16(image + WB_TEXT_LIFETIME_REQUEST));
        wr16(image + WB_TEXT_LIFETIME_REQUEST, 0);
        wr16(image + WB_TEXT_LIFETIME_ARMED, WB_TEXT_LIFETIME_ARMED_SET);
    }
    image[WB_TEXT_BOX_ACTIVE] = WB_TEXT_BOX_ACTIVE_SET;    /* `st $c031.l` */

    /* `subi.b #$1,d0 / lsl.w #2,d0 / lea (0,a6,d0.w),a6` — a BYTE subtract on a zero-extended byte
     * and then a WORD index, so an id past WB_TEXT_MESSAGE_COUNT reads a "pointer" out of the
     * record bytes rather than reaching far memory. No writer in the image posts one. */
    uint32_t entry = (uint32_t)(uint8_t)(request - WB_TEXT_MESSAGE_FIRST_ID)
                     << WB_TEXT_MESSAGE_PTR_SHIFT;
    uint32_t record = be32(image + addr_add(WB_TEXT_MESSAGE_TABLE, sign_ext16(entry)));

    image[WB_TEXT_BOX_ROWS] = image[addr_add(record, WB_TEXT_RECORD_ROWS)];
    image[WB_TEXT_BOX_TOP_LINE] = image[addr_add(record, WB_TEXT_RECORD_TOP_LINE)];
    image[WB_TEXT_REQUEST] = 0;                            /* the request is consumed */

    clear_message_buffer(image);
    plot_message_frame(image, image[WB_TEXT_BOX_ROWS]);
    plot_message_text(image, addr_add(record, WB_TEXT_RECORD_STRING));
}

/* `lea $c03a.l,a0 / movea.l $750.w,a1 / ...` — the composed buffer onto the back screen, one
 * WB_TEXT_BUFFER_LINE per scanline with a WB_TEXT_BLIT_SKIP between them. */
static void blit_message_box(uint8_t *image) {
    uint32_t source = WB_TEXT_BUFFER;
    /* `mulu.w #$a0,d0` is a 32-bit product but `lea 48(a1,d0.w),a1` indexes with its low word,
     * SIGN-EXTENDED — so a top line whose scanline offset overflows a signed word places the box
     * BELOW WB_SCREEN_BACK rather than far past it. The shipped records only ever ask for 50 or 60,
     * so test/test_text.py seeds the state byte directly to reach it. */
    uint32_t dest = addr_add(be32(image + WB_SCREEN_BACK),
                             sign_ext16((uint32_t)image[WB_TEXT_BOX_TOP_LINE] * WB_SCREEN_LINE));
    dest = addr_add(dest, WB_TEXT_BLIT_X_BYTES);

    /* `lsl.l #3,d0 / subq.l #1,d0` on a zero-extended byte, counted down by a WORD `dbf`. */
    uint32_t scanlines = (uint32_t)image[WB_TEXT_BOX_ROWS] << WB_TEXT_BLIT_ROW_SHIFT;
    uint16_t remaining = (uint16_t)(scanlines - 1u);
    do {
        copy_constant_longwords(image, &source, &dest, WB_TEXT_BLIT_LONGWORDS);
        dest = addr_add(dest, WB_TEXT_BLIT_SKIP);
    } while (remaining-- != 0);
}

/* The arm WB_TEXT_BOX_ACTIVE picks: age the box, then draw the frame it already composed. */
static void tick_and_blit_message_box(uint8_t *image) {
    /* `clr.b $c030.l` on an arm only ever reached with it already zero, so it changes no byte.
     * Kept because it is a write the ORIGINAL makes and the cases state the oracle's write set
     * exactly; test/test_text.py records that dropping it here is an equivalence no case can kill. */
    image[WB_TEXT_REQUEST] = 0;

    if (be16(image + WB_TEXT_LIFETIME_ARMED) != 0) {
        uint16_t left = (uint16_t)(be16(image + WB_TEXT_LIFETIME_LEFT) - 1u);
        wr16(image + WB_TEXT_LIFETIME_LEFT, left);
        if (left == 0)
            image[WB_TEXT_BOX_ACTIVE] = 0;
    }

    /* The expiring frame is still drawn: `clr.b $c031.l` falls through into the blit. */
    blit_message_box(image);
}

void text_run_message_box(uint8_t *image) {
    uint8_t request = image[WB_TEXT_REQUEST];
    if (request != 0) {
        compose_requested_message(image, request);
        return;
    }
    if (image[WB_TEXT_BOX_ACTIVE] != 0)
        tick_and_blit_message_box(image);
}
