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
#include "draw.h"

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
            g_stop_music_chk(image, A_dosound_crash);
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

/* --- draw_hud @ 0x1555e --- The in-race HUD, drawn straight into the current draw buffer
 * (A6 = physbase_tbl[flip_idx], derived here, not passed). Phases, in order:
 *   1. Speedometer  — format the speed byte into a "/N NN" digit string (hundreds prefix,
 *      leading-blank tens).
 *   2. Timer        — format the bonus-time word into two leading-blank digits (0 if game over).
 *   3. Dashboard-variant sprite — a masked 1-cell-wide column blit from buf_c, unless dsp_toggle.
 *   4. Flag-sequence bars — one lit vertical bar per matched-in-a-row flag.
 *   5. Colour bars  — five columns tinted from color_pairs, indexed by a scrolling colour cursor.
 *   6. Fuel/tacho gauge — a fixed multi-row bar pattern (one column per bonus unit); or, when no
 *      units remain, a blinking small gauge (draw_hud_gauge0 + optional draw_hud_bar).
 *   7. Main gauge cluster — draw_hud_gauge0 + five draw_hud_bars (A0 dst and A3 string threaded
 *      across the calls) + the dashboard graphic (draw_dashboard).
 *   8. Crash fx     — run draw_crash_fx once the crash arm-timer goes negative, else decay it.
 * The many raw longword writes below are the 68000's unrolled plane blits; offsets are byte
 * offsets into the draw buffer and each row steps one scanline (ROW_STRIDE). */

#define HUD_DIGIT_DIV      10       /* speed/time split into tens + units */
#define HUD_SPEED_HUNDREDS 200      /* prefix "/2" and subtract at this speed */
#define HUD_SPEED_HUNDRED  100      /* prefix "/1" and subtract at this speed */
#define HUD_BLANK          0x2f     /* '/' renders as a blank glyph (leading-zero suppression) */
#define HUD_PREFIX_00      0x2f2f   /* speedometer prefix: "//" (<100) */

/* Phase 3: dashboard-variant masked sprite blit. */
#define HUD_DSP_TBL        0x1854c  /* records: {src_off:long, dst_off:word, rows-1:word} @ +idx */

/* Phase 4: flag-sequence "collected" bars. */
#define FLAG_BAR_TOP_DST   0x248    /* top strip cleared before the bars */
#define FLAG_BAR_CLEAR_BIT 0xfffefffe  /* clear the low bit of each plane word */
#define FLAG_BAR_TOP_ROWS  16
#define FLAG_BAR_TOP_BACK  0x9f8    /* rewind after the top strip (to buffer + 0x250) */
#define FLAG_BAR_MID_ROWS  14       /* lit rows between the two dark caps, per bar */
#define FLAG_BAR_COL_BACK  0x960    /* rewind to the next bar column (net +8 per bar) */

/* Phase 5: five colour-tinted bars. */
#define COLOR_BAR_DST      0x2f0
#define COLOR_BAR_MASK_SRC 0x17d14  /* per-row {mask, ink} words (advances across all columns) */
#define COLOR_BAR_CIDX_TBL 0x17e40  /* per-column colour-index bytes */
#define COLOR_BAR_PRECLEAR 0xbfffbfff  /* clear bit14 of each plane word (top cap) */
#define COLOR_BAR_COLS     5
#define COLOR_BAR_ROWS     12
#define COLOR_BAR_COL_BACK 0x818    /* rewind to the next column (net +8 per column) */

/* Phase 6a: fuel/tacho gauge column pattern (15 rows). */
#define FUEL_BASE          0x1798
#define FUEL_MASK_SRC      0x17f08  /* two mask longs blended into the mid rows */
#define FUEL_EDGE          0x80018001  /* AND: keep only the plane edge bits (top/bottom caps) */
#define FUEL_NEAR_FULL     0x7ffe7ffe
#define FUEL_MID           0x40024002
#define FUEL_LOW           0x5ffa5ffa
#define FUEL_MASK_KEEP     0x1ff81ff8  /* bits kept from the mask source before OR-ing FUEL_MID */
#define FUEL_COL_BACK      0x8c0     /* rewind to the next column (net +8 per unit) */

/* Phase 6b: blinking small gauge. */
#define SMALL_GAUGE_DST    0x2038
#define SMALL_GAUGE_STR    0x18206
#define SMALL_GAUGE_COLOR  6
#define GAUGE_BLINK_BIT    2        /* draw only when this bit of gauge_blink is set */

/* Phase 7: main gauge cluster (dst deltas applied between the chained sub-draws). */
#define GAUGE_MAIN_DST     0x238
#define GAUGE_MAIN_STR     0x18218
#define GAUGE_MAIN_COLOR   0xf
#define GAUGE_BAR1_ADV     0xa90
#define GAUGE_BAR2_ADV     0x4c0
#define GAUGE_BAR5_BACK    0xae0
/* draw_hud_gauge0 never loads D5 — it inherits the caller's. Here that is the scanline stride D5
 * left at 0x98 by the earlier phases, minus whatever cells a phase-6b gauge0/bar already drew
 * (the shared body's `dbf d5` decrements it). We pass 0x98: it is only an upper bound on cells,
 * and every HUD label (the phase-7 string is "TIM=", 2 cells) terminates on its NUL long before
 * any inherited budget — so the exact leaked value is unobservable for the shipped data. */
#define GAUGE_CELLS_M1     0x98
#define DASHBOARD_DST      0x280

/* Phase 8. */
#define HUD_CRASH_DECAY    2

void g_draw_hud(uint8_t *image) {
    const uint32_t buf = draw_buffer(image);

    /* Phase 1: speedometer digits. */
    uint16_t v = image[A_speed + 1];               /* low byte of the speed word */
    uint16_t speed_prefix = HUD_PREFIX_00;
    uint8_t speed_blank = HUD_BLANK;               /* leading char if the tens digit is 0 */
    if (v >= HUD_SPEED_HUNDREDS) {
        speed_prefix = HUD_PREFIX_00 + 3;          /* "/2" */
        v -= HUD_SPEED_HUNDREDS;
        speed_blank = '0';
    } else if (v >= HUD_SPEED_HUNDRED) {
        speed_prefix = HUD_PREFIX_00 + 2;          /* "/1" */
        v -= HUD_SPEED_HUNDRED;
        speed_blank = '0';
    }
    wr16(image + A_hud_speed_txt, speed_prefix);
    uint16_t sq = v / HUD_DIGIT_DIV;
    image[A_hud_speed_txt + 2] = (uint8_t)sq ? (uint8_t)('0' + sq) : speed_blank;
    image[A_hud_speed_txt + 3] = (uint8_t)('0' + (v - sq * HUD_DIGIT_DIV));

    /* Phase 2: timer digits (blanked to 0 when the game is over). */
    uint16_t t = be16(image + A_time_left);
    if (be16(image + A_game_over_flag) != 0) t = 0;
    uint16_t tq = t / HUD_DIGIT_DIV;
    image[A_hud_time_txt + 1] = (uint8_t)tq ? (uint8_t)('0' + (uint8_t)tq) : HUD_BLANK;
    image[A_hud_time_txt + 2] = (uint8_t)('0' + (uint8_t)(t - tq * HUD_DIGIT_DIV));

    /* Phase 3: dashboard-variant masked sprite (skipped while dsp_toggle is set). */
    if (be16(image + A_dsp_toggle) == 0) {
        uint16_t idx = be16(image + A_dsp_variant_idx);
        uint32_t src = be32(image + A_buf_c) + be32(image + HUD_DSP_TBL + idx);
        uint32_t dst = buf + sign_ext16(be16(image + HUD_DSP_TBL + 4 + idx));
        int16_t rows = (int16_t)be16(image + HUD_DSP_TBL + 6 + idx);
        for (int r = 0; r <= rows; r++) {
            uint32_t mask = dup16(be16(image + src));
            wr32(image + dst, be32(image + dst) & mask);
            wr16(image + dst,     (uint16_t)(be16(image + src + 2) | be16(image + dst)));
            wr16(image + dst + 2, (uint16_t)(be16(image + src + 4) | be16(image + dst + 2)));
            wr32(image + dst + 4, (be32(image + dst + 4) & mask) | dup16(be16(image + src + 6)));
            dst += ROW_STRIDE;
            src += ROW_STRIDE;
        }
    }

    /* Phase 4: one lit vertical bar per matched-in-a-row flag. */
    int16_t seq = (int16_t)be16(image + A_flag_seq_count);
    if (seq >= 1) {
        uint32_t a = buf + FLAG_BAR_TOP_DST;
        for (int r = 0; r < FLAG_BAR_TOP_ROWS; r++, a += ROW_STRIDE) {
            wr32(image + a,     be32(image + a)     & FLAG_BAR_CLEAR_BIT);
            wr32(image + a + 4, be32(image + a + 4) & FLAG_BAR_CLEAR_BIT);
        }
        a -= FLAG_BAR_TOP_BACK;
        for (int c = 0; c < seq; c++) {
            wr32(image + a, 0); wr32(image + a + 4, 0); a += ROW_STRIDE;   /* dark cap */
            for (int r = 0; r < FLAG_BAR_MID_ROWS; r++, a += ROW_STRIDE) {
                wr32(image + a,     FLAG_BAR_CLEAR_BIT);
                wr32(image + a + 4, FLAG_BAR_CLEAR_BIT);
            }
            wr32(image + a, 0); wr32(image + a + 4, 0);                    /* dark cap */
            a += 8 - FLAG_BAR_COL_BACK;
        }
    }

    /* Phase 5: five colour-tinted bars from a scrolling colour-index cursor. */
    uint32_t a = buf + COLOR_BAR_DST;
    uint32_t mask_src = COLOR_BAR_MASK_SRC;
    uint32_t cidx = COLOR_BAR_CIDX_TBL
                  + sign_ext16(be16(image + A_flag_seq_off))
                  + sign_ext16(be16(image + A_dsp_color_scroll));
    for (int col = 0; col < COLOR_BAR_COLS; col++) {
        int16_t off = (int16_t)(uint16_t)(image[cidx++] << 3);
        uint32_t fill_lo = be32(image + A_color_pairs + (int32_t)off);
        uint32_t fill_hi = be32(image + A_color_pairs + (int32_t)off + 4);
        wr32(image + a,     be32(image + a)     & COLOR_BAR_PRECLEAR);
        wr32(image + a + 4, be32(image + a + 4) & COLOR_BAR_PRECLEAR);
        a += ROW_STRIDE;
        for (int r = 0; r < COLOR_BAR_ROWS; r++, a += ROW_STRIDE) {
            uint32_t mask = dup16(be16(image + mask_src));
            uint32_t ink  = dup16(be16(image + mask_src + 2));
            mask_src += 4;
            wr32(image + a,     (be32(image + a)     & mask) | (ink & fill_lo));
            wr32(image + a + 4, (be32(image + a + 4) & mask) | (ink & fill_hi));
        }
        a -= COLOR_BAR_COL_BACK;
    }

    /* Phase 6: fuel/tacho gauge (one column per bonus unit), or a blinking small gauge. */
    int16_t lap = (int16_t)be16(image + A_crash_lap);
    if (lap >= 1) {
        uint32_t f_lo = (be32(image + FUEL_MASK_SRC)     & FUEL_MASK_KEEP) | FUEL_MID;
        uint32_t f_hi = (be32(image + FUEL_MASK_SRC + 4) & FUEL_MASK_KEEP) | FUEL_MID;
        uint32_t g = buf + FUEL_BASE;
        for (int c = 0; c < lap; c++) {
            wr32(image + g, be32(image + g) & FUEL_EDGE); wr32(image + g + 4, be32(image + g + 4) & FUEL_EDGE); g += ROW_STRIDE;
            wr32(image + g, FUEL_NEAR_FULL); wr32(image + g + 4, FUEL_NEAR_FULL); g += ROW_STRIDE;
            wr32(image + g, FUEL_MID); wr32(image + g + 4, FUEL_MID); g += ROW_STRIDE;
            for (int r = 0; r < 4; r++, g += ROW_STRIDE) { wr32(image + g, f_lo); wr32(image + g + 4, f_hi); }
            wr32(image + g, FUEL_MID); wr32(image + g + 4, FUEL_MID); g += ROW_STRIDE;
            for (int r = 0; r < 5; r++, g += ROW_STRIDE) { wr32(image + g, FUEL_LOW); wr32(image + g + 4, FUEL_LOW); }
            wr32(image + g, FUEL_NEAR_FULL); wr32(image + g + 4, FUEL_NEAR_FULL); g += ROW_STRIDE;
            wr32(image + g, be32(image + g) & FUEL_EDGE); wr32(image + g + 4, be32(image + g + 4) & FUEL_EDGE);
            g += 8 - FUEL_COL_BACK;
        }
    } else {
        int16_t blink = (int16_t)(be16(image + A_gauge_blink) - 1);
        wr16(image + A_gauge_blink, (uint16_t)blink);
        if (blink < 0) {
            wr16(image + A_gauge_blink, 0);
        } else if (blink & GAUGE_BLINK_BIT) {
            uint32_t end, str;
            str = draw_hud_gauge0_chain(image, buf + SMALL_GAUGE_DST, SMALL_GAUGE_COLOR,
                                        GAUGE_CELLS_M1, SMALL_GAUGE_STR, &end);
            if (be16(image + A_gauge_blink_on) != 0)
                draw_hud_bar_chain_dst(image, end, 0, 0xffffffff, str, &end);
        }
    }

    /* Phase 7: the main gauge cluster; A0 (dst) and A3 (string) thread across every sub-draw. */
    uint32_t g_lo = be32(image + A_color_pairs + (GAUGE_MAIN_COLOR << 3));
    uint32_t g_hi = be32(image + A_color_pairs + (GAUGE_MAIN_COLOR << 3) + 4);
    uint32_t end, str;
    str = draw_hud_gauge0_chain(image, buf + GAUGE_MAIN_DST, GAUGE_MAIN_COLOR, GAUGE_CELLS_M1, GAUGE_MAIN_STR, &end);
    str = draw_hud_bar_chain_dst(image, end + GAUGE_BAR1_ADV, g_lo, g_hi, str, &end);
    str = draw_hud_bar_chain_dst(image, end + GAUGE_BAR2_ADV, g_lo, g_hi, str, &end);
    str = draw_hud_bar_chain_dst(image, end, 0, 0xffffffff, str, &end);
    str = draw_hud_bar_chain_dst(image, end, 0xffffffff, 0xffffffff, str, &end);
    draw_hud_bar_chain_dst(image, end - GAUGE_BAR5_BACK, 0x0000ffff, 0xffffffff, str, 0);   /* last bar: nothing chains after */
    g_draw_dashboard(image, DASHBOARD_DST);

    /* Phase 8: crash-fx arm timer. */
    int16_t crash_t = (int16_t)be16(image + A_hud_crash_timer);
    if (crash_t != 0) {
        if (crash_t < 0)
            g_draw_crash_fx(image, buf);
        else
            wr16(image + A_hud_crash_timer, (uint16_t)(crash_t - HUD_CRASH_DECAY));
    }
}
