/* highscore.c — the ROLE OF HONOUR screen, the game-over screen's own half, and the ranking that
 * decides whether the player's score belongs in the table.
 *
 * The table's five entries are score-plus-record pairs (highscore.h), so drawing the screen is the
 * logo, a heading, and then each entry's own record and score at the row the record already names.
 *
 * The other three routines of this subsystem are whole-function KIT-blocked and reach this file as
 * SLICES instead: `game_over_screen` (0x12e66) and `highscore_check_and_insert` (0x12eae) each
 * contribute the half that does not touch the keyboard, and `highscore_enter_name` (0x12fd4) is the
 * `ikbd_send_cmd` @ 0x14444 wall itself and contributes nothing. STATUS.md says which is which, and
 * include/highscore.h carries each slice's `[start, end)` beside its prototype.
 */
#include "machine.h"
#include "highscore.h"
#include "hud.h"
#include "score.h"
#include "text.h"
#include "video.h"

static uint32_t highscore_entry(unsigned row) {
    return addr_add(A_highscore_table, row * HIGHSCORE_ENTRY_BYTES);
}

/* Carry every entry below `rank` one row down, LAST ONE FIRST, so that row `rank` is free.
 *
 * Only the score and the fifteen name characters move; include/highscore.h says why the record's
 * column, row and terminator stay put. The bound is what the original spells as `move.w #$2,d1 /
 * sub.w d0,d1` and a `dbf`, plus the `cmp.w #$3,d0` / `beq` that jumps the loop entirely — and that
 * branch is load-bearing rather than an optimisation, because at a counter of 3 the `dbf` count
 * would be -1 and the shift would run 65,536 times. `row > rank` is the same statement without a
 * second branch: at rank HIGHSCORE_ENTRIES - 1 it simply moves nothing. */
static void highscore_shift_down(uint8_t *image, unsigned rank) {
    for (unsigned row = HIGHSCORE_ENTRIES - 1u; row > rank; row--) {
        uint32_t into = highscore_entry(row);
        uint32_t from = highscore_entry(row - 1u);

        wr32(image + into, be32(image + from));
        for (unsigned character = 0; character < HIGHSCORE_SHIFT_NAME_BYTES; character++)
            image[into + HIGHSCORE_NAME_OFFSET + character] =
                image[from + HIGHSCORE_NAME_OFFSET + character];
    }
}

/* Clear the draw buffer, put the logo and the heading up, then one record and one score per entry.
 *
 * THE SCORES ARE DRAWN AFTER ALL SIX RECORDS, not interleaved with them, and — this is the part a
 * reader will not guess — each score's row is a `lea` DISPLACEMENT OF THE ROUTINE'S OWN, not the row
 * byte of the record beside it. The two agree entry for entry in the shipped table (110, 122, 134,
 * 146, 158 on both sides), so nothing on screen shows the difference; but the routine does not read
 * the record for it, and a table whose record rows had been edited would put the names and the
 * scores on different lines. test_highscore.py drives exactly that, so the two are not conflated.
 */
void role_of_honour_screen(uint8_t *image) {
    uint32_t buffer = be32(image + A_screen_back);

    screen_clear(image, buffer);
    hud_blit_zynaps_logo(image, buffer, LOGO_TITLE_OFFSET);
    draw_text_record(image, buffer, A_msg_role_of_honour, NULL);
    for (unsigned entry = 0; entry < HIGHSCORE_ENTRIES; entry++)
        draw_text_record(image, buffer,
                         addr_add(A_highscore_table,
                                  entry * HIGHSCORE_ENTRY_BYTES + HIGHSCORE_ENTRY_RECORD), NULL);
    for (unsigned entry = 0; entry < HIGHSCORE_ENTRIES; entry++) {
        uint32_t row_base = addr_add(buffer, HIGHSCORE_FIRST_SCORE_OFFSET
                                             + entry * HIGHSCORE_SCORE_ROW_STEP);
        uint32_t score = be32(image + addr_add(A_highscore_table,
                                               entry * HIGHSCORE_ENTRY_BYTES));

        draw_bcd_number(image, row_base, HIGHSCORE_DIGITS_COLUMN, score);
    }
    screen_flip_buffers(image);
}

/* game_over_screen_prologue — [0x12e66, 0x12e94), everything `game_over_screen` does before it asks
 * whether the score rated.
 *
 * Clear the playfield, print GAME OVER PLAYER into the back buffer, and put the player's digit at
 * the column the record ran out at — the same `draw_text_record` leftover `player_intro_screen`
 * uses, at a different row. What the slice stops short of is the `bsr` into
 * `highscore_check_and_insert` and the palette restore on ITS not-rated arm — which is why this
 * file does NOT call `install_frontend_palette`, the copy src/hud.c keeps static for its own two
 * screens: the game-over screen makes it four instructions past this slice's end.
 *
 * IT DOES NOT FLIP THE BUFFERS, unlike the two front-end screens in src/hud.c: the high-score
 * screens that follow draw into the same back buffer, so the whole sequence is composed first. */
void game_over_screen_prologue(uint8_t *image) {
    uint32_t buffer;
    uint16_t column;

    playfield_clear(image);
    buffer = be32(image + A_screen_back);
    draw_text_record(image, buffer, A_msg_game_over_player, &column);
    draw_char(image, addr_add(buffer, GAME_OVER_DIGIT_ROW_OFFSET), column,
              (uint16_t)sign_ext8((uint8_t)(image[A_current_player_index]
                                            + PLAYER_DIGIT_CHAR_ZERO)));
}

/* highscore_rank_and_shift — [0x12eb2, 0x12f0e) and [0x12eb2, 0x12f5a).
 *
 * The pure half of `highscore_check_and_insert`: find where the player's score belongs in the
 * five-entry table and shift the entries below it down a row. The half beyond this slice draws
 * NEW HIGH SCORE and runs the on-screen keyboard, which is KIT-blocked.
 *
 * `cmp.l (a0),d1` + `ble` IS A SIGNED LONGWORD COMPARE and the scores are packed BCD, so a table
 * entry with bit 31 set — 0x80000000 up, which BCD spells as eight thousand million — reads as
 * negative and every player score beats it. The shipped table holds nothing like that; the compare
 * is transcribed as signed because that is the instruction.
 *
 * The answer is the table ROW, which the original leaves in D6 and turns into an address at 0x12f0e.
 * HIGHSCORE_ENTRIES means "did not rate", which is the arm that leaves at 0x12f5a instead. */
unsigned highscore_rank_and_shift(uint8_t *image) {
    int32_t score = (int32_t)be32(image + A_player_score_bcd);
    /* The `dbf` counter, and it is SIGNED because falling out of the loop leaves it at -1. */
    int counter = (int)HIGHSCORE_ENTRIES - 1;
    unsigned rank;

    while (counter >= 0 && score > (int32_t)be32(image + highscore_entry((unsigned)counter)))
        counter--;
    if (counter == (int)HIGHSCORE_NOT_RATED_COUNTER)
        return HIGHSCORE_ENTRIES;

    rank = (unsigned)(counter + 1);
    highscore_shift_down(image, rank);
    return rank;
}

/* Register map: none in; everything is clobbered. */
void g_role_of_honour_screen(uint8_t *image) {
    role_of_honour_screen(image);
}

/* Register map: none in. A0 carries the draw buffer and D1 the column the record left behind. */
void g_game_over_screen_prologue(uint8_t *image) {
    game_over_screen_prologue(image);
}

/* Register map: none in; the answer is D6, and the glue returns it so a case can compare the rank
 * as well as the shifted bytes. */
uint32_t g_highscore_rank_and_shift(uint8_t *image) {
    return highscore_rank_and_shift(image);
}
