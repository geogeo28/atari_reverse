/* highscore.c — high-score table update (update_highscore @ 0x1238e).
 *
 * Verified to a CHECKPOINT: this reconstructs the deterministic prefix — the ranking, the row
 * shift, and the score/name insert (the part that populates highscore_table, so the results
 * screen's SCORE/NAME rows fill in) — and stops there, like _start/main. The rest of the real
 * function is the interactive name-entry loop (it busy-polls the IKBD, Vsyncs, and waits on
 * MZFLAG); it can't be run to rts under the current oracle, so it is verified by reading, not
 * execution (see HARNESS.md). Two checkpoints match the two prefix exits:
 *   made the table -> stop_pc 0x12450 (just after the insert, before play_event_tune)
 *   didn't make it -> stop_pc 0x123e6 (just after results_mode=2 / hiscore_pos=0)
 *
 * The new score is 6 ASCII digits at score_bcd (0x1824c..0x18251); a leading '0' is blanked to
 * '/' first. Rows are ranked by a byte-wise compare (higher digits sort first). On a hit the rows
 * below shift down one (dropping the last) and the 12-byte score+name record is inserted.
 */
#include <string.h>
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

#define SCORE_CMP_BYTES  6      /* digits compared per row (cmp.b loop, dbra #5) */
#define RECORD_BYTES     12     /* score+name record inserted (3 longwords from score_bcd) */
#define COUNTDOWN_START  0x1e   /* name-entry countdown (30 -> "TIME 30") */
#define ASCII_ZERO       '0'    /* 0x30 */
#define ASCII_SLASH      '/'    /* 0x2f: a blanked leading zero ('0' - 1) */
#define SHIFT_SRC_OFF    0x70   /* shift walk starts one row below the last (table + 0x70/0x7e) */
#define SHIFT_DST_OFF    0x7e

/* Does the new score outrank the row at `row`? A byte-wise compare of SCORE_CMP_BYTES digits: the
 * first byte where row < new (signed cmp.b) means the new score belongs here; row > new (or all
 * equal) means keep looking lower. */
static int outranks_row(const uint8_t *image, uint32_t row, uint32_t score) {
    for (int i = 0; i < SCORE_CMP_BYTES; i++) {
        if ((int8_t)(uint8_t)(image[row + i] - image[score + i]) < 0) return 1;   /* row < new */
        if (image[row + i] != image[score + i]) return 0;                          /* row > new */
    }
    return 0;                                                                       /* all equal */
}

/* Shift the rows from the insertion point down one slot (dropping the last), high address to low
 * so the overlapping copy is safe — mirrors the 68k pointer walk. Only the first RECORD_BYTES of
 * each 0xe-byte row move (the top 2 bytes stay put). `iters` = rows to move = 8 - rank0. */
static void shift_rows_down(uint8_t *image, uint32_t table, int iters) {
    uint32_t src = table + SHIFT_SRC_OFF, dst = table + SHIFT_DST_OFF;
    for (int n = 0; n < iters; n++) {
        src -= 2; dst -= 2;
        for (int k = 0; k < 3; k++) {                  /* three longwords, pre-decrement both */
            src -= 4; dst -= 4;
            wr32(image + dst, be32(image + src));
        }
    }
}

void g_update_highscore(uint8_t *image) {
    g_EGOFF(image);                                    /* stop the envelope generator */

    if (image[A_score_bcd] == ASCII_ZERO)              /* blank a leading zero: '0' -> '/' */
        image[A_score_bcd] = ASCII_SLASH;

    uint16_t leg = be16(image + A_leg_index);
    uint32_t table = A_highscore_table + (uint16_t)(leg * HIGHSCORE_LEG_STRIDE);

    int rank0 = 0;                                     /* 0-based insertion row */
    uint32_t row = table;
    int made = 0;
    for (; rank0 < HIGHSCORE_ROWS; rank0++, row += HIGHSCORE_ROW) {
        if (outranks_row(image, row, A_score_bcd)) { made = 1; break; }
    }

    if (!made) {                                       /* checkpoint 0x123e6 */
        wr16(image + A_results_mode, 2);
        wr16(image + A_hiscore_pos, 0);
        return;
    }

    /* made the table at row `rank0` (1-based rank rank0 + 1) — checkpoint 0x12450 */
    wr16(image + A_results_mode, 0);
    wr16(image + A_hiscore_pos, (uint16_t)(rank0 + 1));
    wr16(image + A_countdown_timer, COUNTDOWN_START);
    wr16(image + A_countdown_sub, 0);
    shift_rows_down(image, table, 8 - rank0);          /* 0 iters when inserting at the last row */
    memcpy(image + row, image + A_score_bcd, RECORD_BYTES);
}
