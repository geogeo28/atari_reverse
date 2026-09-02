/* text.h — the character blitter and the two routines that drive it (src/text.c). Subsystem: text.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 */
#ifndef ZYNAPS_TEXT_H
#define ZYNAPS_TEXT_H

#include <stddef.h>   /* NULL — draw_text_record's second output is optional */
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

/* ---- the shipped records ---------------------------------------------------------------------
 *
 * The eight the front-end screens print, in `../out/globals.tsv`'s `text` subsystem where they
 * belong. All eight names are `# ctx` in `../names.txt` — read off the call site rather than off
 * anything that produces them, so a later reading may rename them; `A_msg_player` is the map's
 * `text_player` spelt like its seven `msg_*` siblings.
 *
 * `test_text.py`'s own SHIPPED_RECORDS still carries these as bare literals, and its twelve include
 * four more (`msg_game_over_player`, `msg_new_high_score`, `msg_please_enter_your_name`,
 * `msg_you_are_not_rated`) that no ported routine reaches yet. The day the high-score screens land,
 * those four join this block and that battery's list becomes a MIRRORS-pinned one.
 */
#define A_msg_prepare_for_combat      0x1991eu
#define A_msg_player                  0x19933u  /* names.txt has the corrected address already */
#define A_msg_converted_by_microwish  0x1993du
#define A_msg_coding_howie            0x19956u
#define A_msg_graphics_pete_lyon      0x19967u
#define A_msg_music_and_sound_fx      0x1997eu
#define A_msg_menu_one_or_two_players 0x199a3u
#define A_msg_role_of_honour          0x199c8u

/* Where a character cell starts, relative to a row's base — the two `adda.w`s above, spelt once.
 * Shared rather than private to draw_char because `draw_lives_icons` (src/hud.c) computes a cell
 * address with the SAME four instructions over two destination pointers at once. */
uint32_t text_cell_address(uint32_t row_base, uint16_t column);

void draw_char(uint8_t *image, uint32_t row_base, uint16_t column, uint16_t character);
void draw_bcd_number(uint8_t *image, uint32_t row_base, uint16_t rightmost_column, uint32_t digits);
/* `end_column` receives D1 — the column one past the last character drawn — or is NULL. */
uint32_t draw_text_record(uint8_t *image, uint32_t row_base, uint32_t record,
                          uint16_t *end_column);

/* ================================================================================================
 * THE ASM TWINS — src/asm/text.S, substituted for the three routines below on the TARGET build.
 *
 * The same seam include/scroll.h and include/sprite.h carry, with the same guarantees: the C stays
 * the reference and stays compiled (test/test_text.py and test/test_hud.py prove it equal to the
 * original, test/test_asm_text.py proves each twin equal to it, both byte for byte over the whole
 * image), so the substitution changes the program's SPEED and nothing else.
 *
 * `draw_score_panel_asm` IS DECLARED HERE THOUGH ITS C CORE LIVES IN hud.h, because in the original
 * the three are ONE routine: 0x136c8 has no `rts` and runs off its own end into draw_bcd_number at
 * 0x136f6, which reaches draw_char at 0x13710 by a `bsr`. One `.S` transcribes all three and one
 * seam macro switches all three, so splitting the declaration across two headers would only hide
 * that. hud.h's own declaration of `draw_score_panel` points here.
 * ============================================================================================= */
#ifdef ZY_ASM_TEXT
void draw_score_panel_asm(uint8_t *image, uint32_t buffer);
void draw_char_asm(uint8_t *image, uint32_t row_base, uint16_t column, uint16_t character);
void draw_bcd_number_asm(uint8_t *image, uint32_t row_base, uint16_t rightmost_column,
                         uint32_t digits);
#define ZY_TEXT(fn) fn##_asm
#else
#define ZY_TEXT(fn) fn
#endif

#endif /* ZYNAPS_TEXT_H */
