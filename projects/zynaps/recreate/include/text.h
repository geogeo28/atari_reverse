/* text.h — the character blitter and the two routines that drive it (src/text.c). Subsystem: text.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 */
#ifndef ZYNAPS_TEXT_H
#define ZYNAPS_TEXT_H

#include <stdint.h>

/* ---- the screen the glyphs land on -----------------------------------------------------------
 *
 * A 320x200 four-plane ST frame: 16 pixels per 8-byte group, the four planes interleaved as words,
 * so one 8-pixel character cell is ONE BYTE in each plane and the four are 2 bytes apart.
 *
 * `SCREEN_ROW_BYTES` is the whole frame's row stride and so is really the video subsystem's, not
 * text's — but there is no include/video.h yet, and a subsystem reads another's global by including
 * its header rather than restating the number (README.md, "Adding a function"). It lives here until
 * one exists; test_constants.py's duplicate check is what will say so the day it does.
 */
#define PLANE_STRIDE      2u     /* (a0) / 2(a0) / 4(a0) / 6(a0) — one byte per plane, 2 apart */
#define SCREEN_PLANES     4u
/* A character cell is 8 pixels wide, so a PAIR of columns shares one 16-pixel group: the even
 * column selects the group (8 bytes each) and the odd bit picks the byte within it. */
#define COLUMN_PAIR_MASK  0xfffeu  /* `and.w #$fffe,d1` — the column pair */
#define COLUMN_PAIR_SHIFT 2u       /* `lsl.w #2,d1` — that pair index times the 8-byte group */
#define COLUMN_ODD_BIT    1u       /* `and.w #$1,d1` — +1 byte for the right-hand cell */

/* ---- the font --------------------------------------------------------------------------------
 *
 * `A_font_glyphs` is where `_start` loads extchars.dat (1920 bytes = 48 glyphs); it is bss, so a
 * test that draws anything has to stage the real file there. Each glyph is 8 rows of five bytes:
 * one AND mask that punches the cell out of the background, then the four plane bytes OR'd over it.
 */
#define A_font_glyphs           0x6be6eu
#define A_char_to_glyph_table   0x198d6u  /* one glyph index per character from 0x20 up */
#define GLYPH_BYTES  0x28u  /* `mulu.w #$28,d0` — 8 rows x {mask, plane0..3} */
#define GLYPH_ROWS   8u

/* ---- the three characters that are not glyphs ------------------------------------------------
 *
 * Tested in this order and all three BEFORE the font is consulted. The space is a no-op — it draws
 * nothing at all rather than clearing its cell, which is what makes 1 (clear) a separate character.
 */
#define CHAR_SPACE       0x20u
#define CHAR_CLEAR_CELL  1u    /* fills all four planes with 0x00 */
#define CHAR_FILL_CELL   2u    /* ...and this one with 0xff — the name-entry cursor */
#define CELL_CLEAR_BYTE  0x00u
#define CELL_FILL_BYTE   0xffu

/* A character at or above 'A' maps to a glyph arithmetically ('A' -> 10, straight after the ten
 * digits); anything below it goes through the table, biased by the first character it describes. */
#define CHAR_FIRST_LETTER 0x41u
#define LETTER_GLYPH_BIAS 0x37u
#define CHAR_MAP_FIRST    0x20u

/* ---- draw_bcd_number / draw_text_record ------------------------------------------------------ */
#define BCD_DIGITS       8u    /* `moveq #$7,d7` + `dbf` — eight nibbles of a longword */
#define BCD_DIGIT_MASK   0xfu
#define CHAR_DIGIT_ZERO  0x30u
#define TEXT_RECORD_TERMINATOR 0u

void draw_char(uint8_t *image, uint32_t row_base, uint16_t column, uint16_t character);
void draw_bcd_number(uint8_t *image, uint32_t row_base, uint16_t rightmost_column, uint32_t digits);
uint32_t draw_text_record(uint8_t *image, uint32_t row_base, uint32_t record);

#endif /* ZYNAPS_TEXT_H */
