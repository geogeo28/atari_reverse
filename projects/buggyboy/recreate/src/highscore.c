/* highscore.c — high-score table: default init (init_scoretable @ 0x1047a) + update
 * (update_highscore @ 0x1238e).
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

/* g_hiscore_gameover — the "missed the table" tail of update_highscore (0x23e6..0x240e, then the
 * shared key-drain at 0x25de). The prefix (g_update_highscore) sets results_mode = 2 for this path;
 * game_main calls this next. It redraws the results screen, plays the game-over jingle (tune 2),
 * waits for it to finish, and drains pending keys.
 *
 * Verified by reading, not execution: the two waits (g_wait_music_off spins on mzflag; the key drain
 * polls Crawio) never terminate under the oracle, so this joins the interactive tail that the
 * harness cannot run to rts. Every step maps 1:1 to the disassembly and reuses verified callees
 * (draw_results_screen, xbios_setpalette, flip_screen, play_event_tune) in the original's order. */
#define TUNE_GAME_OVER 2       /* moveq #2,d0 before the miss-path play_event_tune (0x2400) */

void g_hiscore_gameover(uint8_t *image) {
    g_draw_results_screen(image);
    g_xbios_setpalette(image, A_results_screen_pal);   /* a0 = 0x17fc2 */
    g_flip_screen(image);
    g_draw_results_screen(image);
    g_flip_screen(image);
    g_play_event_tune(image, TUNE_GAME_OVER);          /* game-over jingle */
    g_wait_music_off(image);                           /* 0x2406: spin until mzflag clears (PRG only) */
    while (g_console_scancode(image) != 0) { }         /* 0x25de: drain pending keys */
}

/* init_scoretable @0x1047a — write the default high-score table (5 legs x 9 rows). Each 0xe-byte
 * row is "/" + two default score digits (from A_default_scores) + "000\0\0" + "...\0" + a rank
 * character ('1'..'9') + \0, giving scores 40000..10000 with a "..." placeholder name; a 2-byte
 * separator follows each leg's 9 rows (HIGHSCORE_LEG_STRIDE = 9*0xe + 2). No args. */
#define SCORETABLE_LEGS  5         /* d4 = 4 */
#define SCORE_PAD00      0x3030    /* the "00" that follows the '0' after the two default digits */
#define NAME_PLACEHOLDER 0x2e2e2e00u   /* "...\0" default name */
#define RANK_CHAR_FIRST  '1'

void g_init_scoretable(uint8_t *image) {
    uint32_t dst = A_highscore_table;
    for (int leg = 0; leg < SCORETABLE_LEGS; leg++) {
        uint32_t digits = A_default_scores;
        uint8_t rank = RANK_CHAR_FIRST;
        for (int row = 0; row < HIGHSCORE_ROWS; row++) {
            image[dst++] = '/';
            image[dst++] = image[digits++];        /* two default score digits */
            image[dst++] = image[digits++];
            image[dst++] = '0';
            wr16(image + dst, SCORE_PAD00); dst += 2;
            wr16(image + dst, 0);           dst += 2;
            wr32(image + dst, NAME_PLACEHOLDER); dst += 4;
            image[dst++] = rank++;
            image[dst++] = 0;
        }
        wr16(image + dst, 0); dst += 2;            /* per-leg separator */
    }
}
