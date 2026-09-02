/* text.c — the character blitter and its two drivers.
 *
 * draw_char @ 0x13710 is the leaf everything on-screen that is not a sprite goes through: the
 * status panel's score, the title screen's credits, the high-score table, the name entry. It masks
 * an 8x8 four-plane glyph into one screen cell. draw_bcd_number @ 0x136f6 and draw_text_record
 * @ 0x12e40 are its two callers-of-record.
 *
 * The font lives in bss (`A_font_glyphs`), loaded from extchars.dat by `_start`, so every test here
 * stages the real 1920 bytes of that file before drawing anything.
 */
#include "machine.h"
#include "text.h"
#include "video.h"

/* Where a column's cell starts, relative to the row's base.
 *
 * TWO SEPARATE `adda.w`s, and both sign-extend. The pair offset is computed as a WORD
 * (`and.w #$fffe,d1 / lsl.w #2,d1`), so a column at or above 0x2000 shifts its own high bit out and
 * lands somewhere else entirely, and one whose product has bit 15 set addresses BACKWARDS from the
 * row base. Faithful; the game's columns are 0..39. */
uint32_t text_cell_address(uint32_t row_base, uint16_t column) {
    uint16_t pair = (uint16_t)((column & COLUMN_PAIR_MASK) << COLUMN_PAIR_SHIFT);
    uint32_t cell = addr_add(row_base, sign_ext16(pair));

    return addr_add(cell, sign_ext16((uint16_t)(column & COLUMN_ODD_BIT)));
}

/* Which glyph a character draws.
 *
 * The threshold test is a SIGNED word compare, so a character that arrived sign-extended from a
 * negative byte takes the table arm and indexes below the table. The table's own byte is then
 * `ext.w`-ed, so a glyph number with bit 7 set is NEGATIVE and the blit reads before the font.
 * Both are what the instructions do; the shipped table holds 0x00..0x2f and the shipped strings are
 * ASCII, so neither arm is reached by the game's own data. */
static uint16_t glyph_number(const uint8_t *image, uint16_t character) {
    uint32_t entry;

    if ((int16_t)character >= (int16_t)CHAR_FIRST_LETTER)
        return (uint16_t)(character - LETTER_GLYPH_BIAS);
    entry = addr_add(A_char_to_glyph_table, sign_ext16((uint16_t)(character - CHAR_MAP_FIRST)));
    return (uint16_t)sign_ext8(image[entry]);
}

/* Eight rows of {mask, plane0..3}: the mask ANDs the background away and the plane byte ORs the
 * glyph in, one plane at a time.
 *
 * THE AND AND THE OR ARE TWO SEPARATE STORES, with the glyph's plane byte read between them. That
 * is only observable if the glyph data and the screen cell are the same bytes, which the game never
 * arranges — it is written out because it is what the routine does, not because a case reaches it.
 */
static void blit_glyph(uint8_t *image, uint32_t cell, uint16_t glyph) {
    uint32_t source = addr_add(A_font_glyphs, sign_ext16((uint16_t)(glyph * GLYPH_BYTES)));

    for (unsigned row = 0; row < GLYPH_ROWS; row++) {
        uint8_t mask = image[source];

        source = addr_add(source, 1);
        for (unsigned plane = 0; plane < SCREEN_PLANES; plane++) {
            uint8_t *pixel = image + addr_add(cell, plane * PLANE_STRIDE);
            uint8_t bits;

            *pixel = (uint8_t)(*pixel & mask);
            bits = image[source];
            source = addr_add(source, 1);
            *pixel = (uint8_t)(*pixel | bits);
        }
        cell = addr_add(cell, SCREEN_ROW_BYTES);
    }
}

/* Characters 1 and 2 paint the whole cell one value rather than reading the font. */
static void fill_cell(uint8_t *image, uint32_t cell, uint8_t value) {
    for (unsigned row = 0; row < GLYPH_ROWS; row++) {
        for (unsigned plane = 0; plane < SCREEN_PLANES; plane++)
            image[addr_add(cell, plane * PLANE_STRIDE)] = value;
        cell = addr_add(cell, SCREEN_ROW_BYTES);
    }
}

/* THE SPACE IS A NO-OP, not a cleared cell — it leaves whatever was under it, which is why the
 * font has a separate "clear" character at 1. The three special characters are compared as BYTES
 * (`cmp.b`) while the letter threshold below is a WORD compare, so a character with junk in its
 * high byte can be the space and cannot be a letter. */
void draw_char(uint8_t *image, uint32_t row_base, uint16_t column, uint16_t character) {
    uint32_t cell;

    if ((uint8_t)character == CHAR_SPACE)
        return;
    cell = text_cell_address(row_base, column);
    if ((uint8_t)character == CHAR_CLEAR_CELL)
        fill_cell(image, cell, CELL_CLEAR_BYTE);
    else if ((uint8_t)character == CHAR_FILL_CELL)
        fill_cell(image, cell, CELL_FILL_BYTE);
    else
        blit_glyph(image, cell, glyph_number(image, character));
}

/* Register map: A0 = the row's base address in a screen buffer, D1.w = the column, D0.b = the
 * character. A0 is saved and restored across the call and D1 comes back untouched — which is what
 * lets draw_bcd_number below step the column itself. */
void g_draw_char(uint8_t *image, uint32_t row_base, uint32_t column_reg, uint32_t character_reg) {
    draw_char(image, row_base, (uint16_t)column_reg, (uint16_t)character_reg);
}

/* Eight packed-BCD digits, right to left from `rightmost_column`.
 *
 * `lsr.l #4` walks the longword a nibble at a time, so the digit drawn first is the LOW nibble and
 * the column steps backwards — and the count is a fixed eight, so a score of 0 draws eight zeroes
 * rather than one. */
void draw_bcd_number(uint8_t *image, uint32_t row_base, uint16_t rightmost_column,
                     uint32_t digits) {
    for (unsigned i = 0; i < BCD_DIGITS; i++) {
        uint16_t digit = (uint16_t)((digits & BCD_DIGIT_MASK) + CHAR_DIGIT_ZERO);

        draw_char(image, row_base, rightmost_column, digit);
        digits >>= 4;
        rightmost_column = (uint16_t)(rightmost_column - 1);
    }
}

/* Register map: A0 = the row base, D1.w = the column of the RIGHTMOST digit, D6 = the packed-BCD
 * longword. D6 comes back shifted empty and D1 eight columns to the left, but no caller reads
 * either — every call site reloads both — so only the pixels are compared. */
void g_draw_bcd_number(uint8_t *image, uint32_t row_base, uint32_t column_reg, uint32_t digits) {
    draw_bcd_number(image, row_base, (uint16_t)column_reg, digits);
}

/* A {column.b, row.b, characters..., 0} record, drawn from `row_base`.
 *
 * The column is SIGN-extended and the row ZERO-extended (`ext.w d1` against `and.w #$ff,d2`), which
 * is not symmetry lost in transcription: the row scales a 160-byte stride into a 32-bit offset and
 * a negative one would address before the buffer, while a negative column is just a cell to the
 * left of the base. Each character is sign-extended too, so a byte at or above 0x80 reaches
 * draw_char as a negative word — no shipped string has one.
 *
 * IT HAS TWO OUTPUTS, and both are live. The return value is the cursor ONE PAST the terminator,
 * which is A6's value on return: the record's own length is never stated, so a caller walking a
 * list of records depends on it. `end_column` is D1, the column one past the last character drawn,
 * and nothing reloads D1 — `player_intro_screen` and `game_over_screen` both print the player's
 * digit at exactly that column, so "PLAYER" and its number stay one string. Pass NULL for it when
 * only the cursor is wanted.
 *
 * ITS `draw_char` GOES THROUGH THE SEAM, and it is the one call in this file that has to. This
 * routine has no twin, so on the target build it is LIVE — every string the game draws reaches the
 * character blitter through here — while `draw_bcd_number` above is the reference for a routine
 * that does have one and is never called there. atari/build.sh's asm-twin gate is structurally
 * blind to this call (an intra-file call is not an undefined reference, so its `nm -u` scrape
 * cannot see it), which is exactly why it is worth a sentence rather than a wrapper alone. */
uint32_t draw_text_record(uint8_t *image, uint32_t row_base, uint32_t record,
                          uint16_t *end_column) {
    uint16_t column = (uint16_t)sign_ext8(image[record]);
    uint32_t row = image[record + 1];
    uint32_t base = addr_add(row_base, row * SCREEN_ROW_BYTES);
    uint32_t cursor = addr_add(record, 2);

    for (;;) {
        uint8_t character = image[cursor];

        cursor = addr_add(cursor, 1);
        if (character == TEXT_RECORD_TERMINATOR) {
            if (end_column)
                *end_column = column;
            return cursor;
        }
        ZY_TEXT(draw_char)(image, base, column, (uint16_t)sign_ext8(character));
        column = (uint16_t)(column + 1);
    }
}

/* Register map: A0 = the screen buffer's base, A6 = the record. A0 is saved and restored; A6 is
 * BOTH an input and an output, so the stub dumps it at `result` — see test/abi.py. D1's leftover is
 * this routine's other output and is dumped by the CALLERS that use it, not here: no case enters at
 * 0x12e40 to read it, so the stub would be storing a register nothing in this battery asks about. */
void g_draw_text_record(uint8_t *image, uint32_t row_base, uint32_t record, uint32_t result) {
    wr32(image + result, draw_text_record(image, row_base, record, NULL));
}
