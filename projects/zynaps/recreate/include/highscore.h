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

/* WHAT THE SHIFT-DOWN ACTUALLY MOVES, and it is not the whole entry: `move.l -22(a0),(a0)`, then
 * `lea 6(a0),a0` and fifteen `move.b -22(a0),(a0)+`. So the score longword and the fifteen name
 * characters are carried down a row, while the record's own COLUMN and ROW bytes (+4, +5) and its
 * terminator (+0x15) stay where they are — which is exactly right, because those three describe the
 * ROW ON SCREEN and not the entry. A shift of all 22 bytes would carry row 110's coordinates onto
 * row 122 and the table would print itself on top of itself. */
#define HIGHSCORE_SHIFT_NAME_BYTES 0xfu   /* `move.w #$e,d0` + dbf */
#define HIGHSCORE_NAME_OFFSET 6u          /* `lea 6(a0),a0` — HIGHSCORE_ENTRY_RECORD + column+row */
/* The ranking scan starts at the LAST entry and walks BACKWARDS (`lea -22(a0),a0`), so its `dbf`
 * counter is a rank counted from the bottom. Stopping on the very first compare leaves it at
 * HIGHSCORE_ENTRIES - 1, and that is the "did not rate" answer — the one arm that leaves the
 * routine at 0x12f5a instead of 0x12f0e. Falling out of the loop leaves it at -1: the score beat
 * every entry. The table row the new score takes is the counter plus one. */
#define HIGHSCORE_NOT_RATED_COUNTER (HIGHSCORE_ENTRIES - 1u)

/* `lea 2560(a0),a0` — row 16, where `game_over_screen` prints the player's digit after the
 * GAME OVER PLAYER record. NOT include/hud.h's PLAYER_NAME_ROW_OFFSET, which is row 80: the two
 * screens print the same two pieces at different heights. */
#define GAME_OVER_DIGIT_ROW_OFFSET 0xa00u

/* BORROWED: ../out/globals.tsv assigns 0x199d9 to the **text** subsystem, with the rest of the
 * `A_msg_*` family, and `include/text.h` does not spell it — this is its first reader. Named here
 * under the same rule STATUS.md's "## Borrowed globals" table carries; moving it into text.h beside
 * its eight siblings is one line there and one deletion here. */
#define A_msg_game_over_player 0x199d9u

/* The heading above the five rows is `A_msg_role_of_honour` in include/text.h, with the other
 * shipped records; the five name records are the table's own, at HIGHSCORE_ENTRY_RECORD. */

/* Where the five SCORES go, and it is not read from the records: `role_of_honour_screen` carries a
 * `lea` displacement per entry, 1920 bytes (twelve rows) apart from 17600 (row 110). The shipped
 * records name the same five rows, so the screen looks the same either way — but the routine never
 * consults them, and src/highscore.c says why that distinction is kept. */
#define HIGHSCORE_FIRST_SCORE_OFFSET 0x44c0u
#define HIGHSCORE_SCORE_ROW_STEP 0x780u

void role_of_honour_screen(uint8_t *image);
/* [0x12e66, 0x12e94) — `game_over_screen`'s own body, stopping at the `bsr` into
 * `highscore_check_and_insert`. That routine is KIT-blocked (STATUS.md), so this is a checkpoint
 * slice and not a whole function. */
void game_over_screen_prologue(uint8_t *image);
/* [0x12eb2, 0x12f0e) and [0x12eb2, 0x12f5a) — the pure half of `highscore_check_and_insert`: where
 * the score ranks, and the shift-down that makes room for it. Entered mid-routine because that
 * routine's own entry at 0x12eae opens with a `bsr` into a screen clear, and left at whichever of
 * the two addresses the ranking chose. Returns the TABLE ROW the new score takes, or
 * HIGHSCORE_ENTRIES when it did not rate. */
unsigned highscore_rank_and_shift(uint8_t *image);

#endif /* ZYNAPS_HIGHSCORE_H */
