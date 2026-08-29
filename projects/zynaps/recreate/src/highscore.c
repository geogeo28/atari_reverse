/* highscore.c — the ROLE OF HONOUR screen.
 *
 * The table's five entries are score-plus-record pairs (highscore.h), so drawing the screen is the
 * logo, a heading, and then each entry's own record and score at the row the record already names.
 *
 * The other three routines of this subsystem are not here: `game_over_screen` (0x12e66),
 * `highscore_check_and_insert` (0x12eae) and `highscore_enter_name` (0x12fd4) all reach
 * `ikbd_send_cmd` @ 0x14444, which is blocked at the KIT level — see STATUS.md.
 */
#include "machine.h"
#include "highscore.h"
#include "hud.h"
#include "text.h"
#include "video.h"

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

/* Register map: none in; everything is clobbered. */
void g_role_of_honour_screen(uint8_t *image) {
    role_of_honour_screen(image);
}
