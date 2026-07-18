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

/* --- made-the-table tail: the interactive initials-entry screen (0x2412 made path) --- */

#define NAME_FIELD_OFF   8       /* the 3-char initials sit at row + 8 (0x2470: a0 = insert dst + 8) */
#define TUNE_RANK1       4       /* moveq #4,d0 before the row loop -> jingle for a rank-1 score */
#define TUNE_OTHER       3       /* moveq #3,d0 after the first row miss -> jingle for ranks 2..9 */
#define CD_SUB_PERIOD    0x11    /* countdown_timer ticks down once every 0x11 sub-frames */
#define CD_TENS_DIV      10      /* "TIME nn" = tens/units of countdown_timer */
#define NAME_CHAR_LO     0x41    /* 'A': char decremented below this wraps to NAME_CHAR_DEL */
#define NAME_CHAR_WRAP   0x61    /* 'a': char incremented to here wraps back to 'A' */
#define NAME_CHAR_DEL    0x60    /* '`': the delete sentinel (fire on it backs up a char) */
#define NAME_CHAR_HOLD   0x5f    /* '_': placeholder left in the backed-out slot */
#define SEL_REPEAT       3       /* auto-repeat delay reload after a successful char step */
#define INPUT_DEC_MASK   0x5     /* up (1) | left (4): step the char down */
#define INPUT_INC_MASK   0xa     /* down (2) | right (8): step the char up */
#define INPUT_FIRE       0x80
#define INPUT_ANY        0x8f    /* fire + all four directions */
#define NAME_FLASH_MASK  0xe     /* anim_counter & this indexes the color-3 flash table (word stride) */
#define NAME_FLASH_REG   3       /* the palette register the name-entry screen flashes */
#define TAIL_VSYNCS      0x78    /* dbf #0x78 -> 121 Vsyncs after the screen (0x259c) */

/* g_hiscore_countdown @0x2472..0x24b4 — one name-entry frame's countdown tick: advance the sub-frame
 * counter, drop countdown_timer every CD_SUB_PERIOD frames, and render it as the two "TIME nn"
 * digits. Returns 1 when the timer underflows (name entry times out -> 0x257c), else 0. */
int g_hiscore_countdown(uint8_t *image) {
    int16_t sub = (int16_t)be16(image + A_countdown_sub);
    wr16(image + A_countdown_sub, (uint16_t)(sub + 1));
    if (sub - CD_SUB_PERIOD >= 0) {                    /* sub was >= 0x11 */
        wr16(image + A_countdown_sub, 0);
        int16_t timer = (int16_t)(be16(image + A_countdown_timer) - 1);
        wr16(image + A_countdown_timer, (uint16_t)timer);
        if (timer < 0) return 1;                       /* timed out */
    }
    int16_t timer = (int16_t)be16(image + A_countdown_timer);
    int tens = timer / CD_TENS_DIV;
    image[A_time_digit_hi] = tens ? (uint8_t)(tens + ASCII_ZERO) : ASCII_SLASH;
    image[A_time_digit_lo] = (uint8_t)((timer - tens * CD_TENS_DIV) + ASCII_ZERO);
    return 0;
}

/* g_hiscore_charstep @0x24ea..0x2542 — one name-entry frame's character selection. Up/left steps the
 * current initial down (wrapping 'A'->'`'), down/right steps it up (wrapping past 'z'->'A'); each is
 * gated by its own auto-repeat delay. `name_ptr` is the current initial's image address. */
void g_hiscore_charstep(uint8_t *image, uint32_t name_ptr) {
    uint16_t in = be16(image + A_input_state);

    int16_t dec = (int16_t)(be16(image + A_leg_dec_delay) - 1);
    wr16(image + A_leg_dec_delay, (uint16_t)dec);
    if (dec < 0 && (in & INPUT_DEC_MASK)) {
        uint8_t c = (uint8_t)(image[name_ptr] - 1);
        image[name_ptr] = c;
        if ((int8_t)(c - NAME_CHAR_LO) < 0) image[name_ptr] = NAME_CHAR_DEL;   /* below 'A' -> '`' */
        else { wr16(image + A_leg_dec_delay, SEL_REPEAT); wr16(image + A_leg_inc_delay, 0); }
    }

    int16_t inc = (int16_t)(be16(image + A_leg_inc_delay) - 1);
    wr16(image + A_leg_inc_delay, (uint16_t)inc);
    if (inc < 0 && (in & INPUT_INC_MASK)) {
        uint8_t c = (uint8_t)(image[name_ptr] + 1);
        image[name_ptr] = c;
        if ((int8_t)(c - NAME_CHAR_WRAP) < 0) { wr16(image + A_leg_inc_delay, SEL_REPEAT); wr16(image + A_leg_dec_delay, 0); }
        else image[name_ptr] = NAME_CHAR_LO;                                   /* reached 'a' -> 'A' */
    }
}

/* g_hiscore_name_entry — the made-the-table tail of update_highscore (0x2412 made path onward). The
 * prefix set results_mode = 0 and hiscore_pos = rank+1; game_main calls this next. It plays the
 * name-entry jingle (tune TUNE_RANK1 for a #1 score, else TUNE_OTHER), then runs the initials-entry
 * screen: a vblank-paced loop rendering the results + a "TIME nn" countdown while the player dials in
 * three initials with the joystick, ending on the third confirm or on timeout. It closes with the
 * shared results fade, 121 Vsyncs, and the tune/input waits + key drain.
 *
 * Verified piecewise: the per-frame countdown and char-select are diffed against the oracle
 * (g_hiscore_countdown / g_hiscore_charstep slices); the surrounding draws, the fire-confirm pointer
 * walk, and the terminal waits (hardware seams that never return under the oracle) are read-verified,
 * each step mapping 1:1 to the disassembly. */
void g_hiscore_name_entry(uint8_t *image) {
    uint16_t rank1 = be16(image + A_hiscore_pos);                    /* 1-based rank */
    uint16_t leg = be16(image + A_leg_index);
    uint32_t table = A_highscore_table + (uint16_t)(leg * HIGHSCORE_LEG_STRIDE);
    uint32_t p = table + (uint16_t)((rank1 - 1) * HIGHSCORE_ROW) + NAME_FIELD_OFF;   /* row + 8 */

    g_play_event_tune(image, rank1 == 1 ? TUNE_RANK1 : TUNE_OTHER);  /* 0x2450: d0 = 4 (rank 1) / 3 */
    g_draw_results_screen(image);
    g_xbios_setpalette(image, A_results_screen_pal);
    g_flip_screen(image);
    g_draw_results_screen(image);
    g_flip_screen(image);

    int chars_left = 2;                                             /* d3 = 2 (initials 3,2,1) */
    int timed_out = 0;
    for (;;) {                                                      /* outer loop (0x2472) */
        for (;;) {                                                 /* per-frame loop until a fresh fire */
            if (g_hiscore_countdown(image)) { timed_out = 1; break; }
            g_draw_results_screen(image);
            uint16_t counter = (uint16_t)(be16(image + A_anim_counter) + 1);
            wr16(image + A_anim_counter, counter);
            g_xbios_setcolor(image, NAME_FLASH_REG,
                             be16(image + A_name_anim_tbl + (counter & NAME_FLASH_MASK)));
            g_flip_screen(image);
            g_read_joystick(image);
            uint16_t in = be16(image + A_input_state);
            uint16_t prev = be16(image + A_input_prev);
            g_hiscore_charstep(image, p);
            if (!(prev & INPUT_FIRE) && (in & INPUT_FIRE)) break;   /* fresh fire press (0x2542) */
        }
        if (timed_out) break;

        if (image[p] == NAME_CHAR_DEL) {                            /* fire on '`' -> back up a char */
            if (chars_left != 2) {
                image[p - 1] = image[p];                            /* 0x2566: shift '`' back */
                image[p] = NAME_CHAR_HOLD;                          /* 0x2568: leave '_' */
                chars_left += 1;
                p -= 1;
            }
            continue;                                               /* 0x2570: re-enter the frame loop */
        }
        image[p + 1] = image[p];                                    /* 0x2574: seed the next initial */
        chars_left -= 1;
        p += 1;
        if (chars_left == -1) { image[p] = 0; break; }              /* all three entered (0x257a) */
    }

    /* shared tail (0x257c): clear the rank, fade the results screen, hold, then wait out the tune. */
    wr16(image + A_hiscore_pos, 0);
    g_draw_results_screen(image);
    g_xbios_setpalette(image, A_results_screen_pal);
    g_flip_screen(image);
    g_draw_results_screen(image);
    g_flip_screen(image);
    for (int i = TAIL_VSYNCS; i >= 0; i--) g_vsync();               /* 0x259c: 121 Vsyncs */
    do { g_read_joystick(image); } while (be16(image + A_input_state) & INPUT_ANY);   /* 0x25ae: wait release */
    for (;;) {                                                      /* 0x25bc: wait tune-end or fresh input */
        g_read_joystick(image);
        if (be16(image + A_input_state) & INPUT_ANY) break;
        if (image[A_mzflag] == 0) break;
    }
    g_TURNOFF(image);                                               /* 0x25d2 */
    image[A_fxflag] = 0;                                            /* 0x25d8 */
    while (g_console_scancode(image) != 0) { }                     /* 0x25de: drain pending keys */
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
