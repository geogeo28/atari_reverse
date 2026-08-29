/* highscore.h — the ROLE OF HONOUR table and the screens around it (src/highscore.c).
 * Subsystem: highscore.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 *
 * THE TABLE IS FIVE 22-BYTE ENTRIES, and each one is a BCD score followed by a `draw_text_record`
 * record — the same {column, row, characters..., 0} shape include/text.h describes. So the name row
 * needs no separate layout: the record carries its own column and row, and the five shipped rows
 * are 110, 122, 134, 146 and 158, which is where `role_of_honour_screen` draws the scores too.
 *
 *   +0x00  .l  the entry's score, packed BCD
 *   +0x04  .b  the record's column (0x10 in all five)
 *   +0x05  .b  the record's row
 *   +0x06      15 characters of name, then the record's 0 terminator
 */
#ifndef ZYNAPS_HIGHSCORE_H
#define ZYNAPS_HIGHSCORE_H

#include <stdint.h>

#define A_highscore_table 0x19d5au
#define HIGHSCORE_ENTRIES 5u
#define HIGHSCORE_ENTRY_BYTES 0x16u  /* `mulu.w #$16,d0` in highscore_check_and_insert */
#define HIGHSCORE_ENTRY_RECORD 4u    /* the text record starts one longword in */
#define HIGHSCORE_DIGITS_COLUMN 0xeu /* `move.w #$e,d1` — the rightmost digit's column */

/* The heading above the five rows is `A_msg_role_of_honour` in include/text.h, with the other
 * shipped records; the five name records are the table's own, at HIGHSCORE_ENTRY_RECORD. */

/* Where the five SCORES go, and it is not read from the records: `role_of_honour_screen` carries a
 * `lea` displacement per entry, 1920 bytes (twelve rows) apart from 17600 (row 110). The shipped
 * records name the same five rows, so the screen looks the same either way — but the routine never
 * consults them, and src/highscore.c says why that distinction is kept. */
#define HIGHSCORE_FIRST_SCORE_OFFSET 0x44c0u
#define HIGHSCORE_SCORE_ROW_STEP 0x780u

void role_of_honour_screen(uint8_t *image);

#endif /* ZYNAPS_HIGHSCORE_H */
