/* hud.c — crash / game-over HUD effect (draw_crash_fx @ 0x15872).
 *
 * draw_crash_fx runs the end-of-race sequence once the crash gate (crash_active) is set: it drains
 * the bonus time / units into the score (add_score + stop_music_chk), rolls a score-digit table
 * over, arms the abort countdown, then redraws the score number (draw_num) and the gauge bars
 * (draw_hud_bar) into the buffer passed in A6. Every sub-draw here is already verified; the fill for
 * the bars is the colour fill draw_num leaves in D2/D3 (color_pairs[colour]). A6 = draw buffer.
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

#define CRASH_FRAME_MIN   0xa       /* the effect body runs once crash_frame reaches this */
#define CRASH_ABORT_INIT  0x33      /* abort_flag armed here when the bonus is exhausted */
#define CRASH_ROLLOVER_TBL 0x1818e  /* score-digit rollover records (stride 0xe); modified in place */
#define CRASH_ROLL_STRIDE 0xe
#define CRASH_ROLL_TARGET 0x60      /* a record is done when 0x60 - digit[-1] - digit == 0 */
#define CRASH_ROLL_HI     0x35      /* the tens digit that resets instead of carrying */
#define CRASH_SCORE_SRC   0x18246   /* score long copied to the HUD score line */
#define CRASH_HUD_SCORE   0x181f0   /* HUD score line (dst of the copy) */
#define CRASH_HUD_LAP     0x181da   /* HUD lap digit ('0' + crash_lap) */
#define CRASH_STR_NUM     0x18172   /* draw_num string */
#define CRASH_STR_BAR1    0x1817a   /* draw_hud_bar string (active bars) */
#define CRASH_STR_BAR2    0x181cc   /* draw_hud_bar string (frame bars) */
#define CRASH_COLOR_TBL   0x17f5a   /* per-frame colour index (indexed crash_frame & 7) */
#define SCORE_DELTA_TIME  0x1737c   /* add_score delta while draining time_left */
#define SCORE_DELTA_ROLL  0x17382   /* add_score delta for a bonus unit / digit rollover */
#define CRASH_NUM_DST     0x4770    /* draw_num dst offset */
#define CRASH_BAR_FIRST   0x54b8    /* first active bar */
#define CRASH_BAR_LOOP    0x5cd0    /* active-bar loop base */
#define CRASH_BAR_LOOP_STEP 0x500
#define CRASH_BAR5_A      0x6ba0    /* extra bars when crash_bars == 5 */
#define CRASH_BAR5_B      0x73c0
#define CRASH_BAR_FIN_A   0x5480    /* frame bars (always) */
#define CRASH_BAR_FIN_B   0x5ca0
#define CRASH_YOFF_IDLE   0x18      /* bar y-offset when no active bars */

void g_draw_crash_fx(uint8_t *image, uint32_t buffer) {
    if (be16(image + A_crash_active) == 0) {
        wr16(image + A_abort_flag, 0xffff);
        return;
    }

    uint16_t frame = (uint16_t)(be16(image + A_crash_frame) + 1);
    wr16(image + A_crash_frame, frame);

    if ((int16_t)frame >= CRASH_FRAME_MIN) {         /* cmpi #0xa; bmi skips the body */
        uint32_t delta = 0;
        int do_score = 0;
        if (be16(image + A_time_left) != 0) {
            wr16(image + A_time_left, (uint16_t)(be16(image + A_time_left) - 1));
            delta = SCORE_DELTA_TIME; do_score = 1;
        } else if (be16(image + A_crash_lap) != 0) {
            wr16(image + A_crash_lap, (uint16_t)(be16(image + A_crash_lap) - 1));
            delta = SCORE_DELTA_ROLL; do_score = 1;
        } else {
            uint16_t recs = be16(image + A_crash_bars);
            uint32_t p = CRASH_ROLLOVER_TBL;
            for (int i = (int)recs - 1; i >= 0; i--, p += CRASH_ROLL_STRIDE) {
                if ((uint8_t)(CRASH_ROLL_TARGET - image[p - 1] - image[p]) != 0) {
                    if (image[p] == CRASH_ROLL_HI) {
                        image[p] = (uint8_t)(image[p] - 5);
                    } else {
                        image[p] = (uint8_t)(image[p] + 5);
                        image[p - 1] = (uint8_t)(image[p - 1] - 1);
                    }
                    delta = SCORE_DELTA_ROLL; do_score = 1;
                    break;
                }
            }
            if (!do_score && be16(image + A_abort_flag) == 0)
                wr16(image + A_abort_flag, CRASH_ABORT_INIT);
        }
        if (do_score) {
            g_add_score(image, delta);
            g_stop_music_chk(image);
        }
    }

    wr32(image + CRASH_HUD_SCORE, be32(image + CRASH_SCORE_SRC));
    image[CRASH_HUD_LAP] = (uint8_t)('0' + be16(image + A_crash_lap));

    uint16_t color = image[CRASH_COLOR_TBL + (frame & 7)];
    g_draw_num_thunk(image, CRASH_NUM_DST, color, CRASH_STR_NUM);

    /* draw_num left color_pairs[color] in D2/D3; the bars reuse it as their fill. */
    uint32_t fill_lo = be32(image + A_color_pairs + (color << 3));
    uint32_t fill_hi = be32(image + A_color_pairs + (color << 3) + 4);

    uint16_t bars = be16(image + A_crash_bars);
    uint32_t str1 = CRASH_STR_BAR1;                  /* the bars chain one string buffer via A3 */
    if (bars != 0) {
        str1 = draw_hud_bar_chain(image, buffer + CRASH_BAR_FIRST, fill_lo, fill_hi, str1);
        for (int i = 0; i < bars; i++)
            str1 = draw_hud_bar_chain(image, buffer + CRASH_BAR_LOOP + i * CRASH_BAR_LOOP_STEP,
                                      fill_lo, fill_hi, str1);
        wr16(image + A_crash_bar_yoff, 0);
    } else {
        wr16(image + A_crash_bar_yoff, CRASH_YOFF_IDLE);
    }

    uint16_t yoff = be16(image + A_crash_bar_yoff);
    uint32_t str2 = CRASH_STR_BAR2;                  /* A3 reset for the frame bars */
    if (bars == 5) {
        str2 = draw_hud_bar_chain(image, buffer + CRASH_BAR5_A + yoff, fill_lo, fill_hi, str2);
        str2 = draw_hud_bar_chain(image, buffer + CRASH_BAR5_B + yoff, fill_lo, fill_hi, str2);
    }
    str2 = draw_hud_bar_chain(image, buffer + CRASH_BAR_FIN_A + yoff, fill_lo, fill_hi, str2);
    draw_hud_bar_chain(image, buffer + CRASH_BAR_FIN_B + yoff, fill_lo, fill_hi, str2);

    if (be16(image + A_abort_flag) != 0)
        wr16(image + A_abort_flag, (uint16_t)(be16(image + A_abort_flag) - 2));
}
