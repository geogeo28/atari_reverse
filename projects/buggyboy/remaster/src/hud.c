/* hud.c — remaster of the in-race HUD (recreate's draw_hud @0x1555e).
 *
 * Ported so far — the pure plane-write phases plus the gauge cluster and dashboard-variant sprite:
 *   Phase 3  dashboard-variant sprite  a masked buf_c sprite chosen by dsp_variant_idx
 *   Phase 4  flag-sequence bars   one lit vertical bar per matched-in-a-row flag
 *   Phase 5  colour-tinted bars    five columns tinted from color_pairs via a scrolling cursor
 *   Phase 6a fuel/tacho gauge      one fixed multi-row column per remaining bonus unit
 *   Phase 6b blinking small gauge  shown instead of 6a when no bonus units remain
 *   Phase 7  main gauge cluster    gauge0 + five bars (glyph blitter) + the dashboard graphic
 *   Phase 8  crash / bonus tally   drain time/units/rollovers -> score; draw the number + bars
 * All eight phases are ported. Off-framebuffer work (add_score arithmetic where it doesn't feed a
 * drawn buffer, sound, the abort-flag countdown) is deliberately omitted. See STATUS.md.
 *
 * The framebuffer is ST hardware format (see st.h); byte offsets below are relative to the draw
 * buffer origin (fb->px[0]) and each row steps one scanline (SCREEN_ROW_BYTES). The layout matches
 * recreate exactly because the equivalence harness diffs these bytes against recreate's output.
 */
#include <string.h>

#include "game.h"
#include "plane.h"
#include "screen.h"
#include "st.h"
#include "text.h"

#define ROW_STRIDE SCREEN_ROW_BYTES

/* Phase 4 — flag-sequence "collected" bars. */
#define FLAG_BAR_TOP_DST   0x248        /* top strip cleared before the bars */
#define FLAG_BAR_CLEAR_BIT 0xfffefffe   /* clear the low bit of each plane word */
#define FLAG_BAR_TOP_ROWS  16
#define FLAG_BAR_TOP_BACK  0x9f8        /* rewind after the top strip (to +0x250) */
#define FLAG_BAR_MID_ROWS  14           /* lit rows between the two dark caps, per bar */
#define FLAG_BAR_COL_BACK  0x960        /* rewind to the next bar column (net +8 per bar) */

/* Phase 5 — five colour-tinted bars from a scrolling colour-index cursor. */
#define COLOR_BAR_DST      0x2f0
#define COLOR_BAR_PRECLEAR 0xbfffbfff   /* clear bit14 of each plane word (top cap) */
#define COLOR_BAR_COLS     5
#define COLOR_BAR_ROWS     12
#define COLOR_BAR_COL_BACK 0x818        /* rewind to the next column (net +8 per column) */
#define COLOR_PAIR_STRIDE  8            /* bytes per colour in color_pairs (colour_idx << 3) */

/* Phase 6a — fuel/tacho gauge column pattern (15 rows per bonus unit). */
#define FUEL_BASE          0x1798
#define FUEL_EDGE          0x80018001   /* AND: keep only the plane edge bits (top/bottom caps) */
#define FUEL_NEAR_FULL     0x7ffe7ffe
#define FUEL_MID           0x40024002
#define FUEL_LOW           0x5ffa5ffa
#define FUEL_MASK_KEEP     0x1ff81ff8   /* bits kept from the mask source before OR-ing FUEL_MID */
#define FUEL_COL_BACK      0x8c0        /* rewind to the next column (net +8 per unit) */

/* Phase 6b — blinking small gauge (drawn instead of 6a when no bonus units remain). */
#define SMALL_GAUGE_DST    0x2038
#define SMALL_GAUGE_COLOR  6
#define GAUGE_BLINK_BIT    2            /* draw only when this bit of (gauge_blink - 1) is set */

/* Phase 7 — main gauge cluster (one gauge0 + five bars, dst/string cursors threaded across) then
 * the dashboard graphic. All inputs are static: colour 0xf, a fixed label/bar string, a fixed
 * buf_c graphic — so this phase draws the same pixels every frame. */
#define GAUGE_MAIN_DST     0x238
#define GAUGE_MAIN_COLOR   0xf
#define GAUGE_CELLS_M1     0x98         /* gauge0 upper-bound budget; the label terminates first */
#define GAUGE_BAR1_ADV     0xa90        /* dst deltas applied between the chained sub-draws */
#define GAUGE_BAR2_ADV     0x4c0
#define GAUGE_BAR5_BACK    0xae0

/* Phase 7 dashboard — masked blit of the fixed dashboard graphic (recreate's draw_dashboard). */
#define DASHBOARD_DST      0x280
#define DASH_ROWS          40
#define DASH_GROUPS        8            /* 8 groups of 4 dest words (0x40 bytes) per row */

/* Phases 1-2 — speed/time digit strings. These write into the gauge-cluster string buffer (the
 * speed/time text buffers overlap it), so phase 7's bars render the live speedometer/timer digits.
 * Offsets are into the gauge string (A_hud_speed_txt / A_hud_time_txt minus the string base). */
#define HUD_TEXT_LEN       0xe6         /* the shared HUD-text region [0x18172, 0x18258) */
#define GAUGE_OFF          0xa6         /* gauge string 0x18218 within the HUD-text region */
#define HUD_SPEED_TXT_OFF  0x24         /* A_hud_speed_txt (0x1823c) - gauge string base (0x18218) */
#define HUD_TIME_TXT_OFF   0x2e         /* A_hud_time_txt  (0x18246) - gauge string base */
#define HUD_DIGIT_DIV      10           /* tens/units split */
#define HUD_SPEED_HUNDREDS 200          /* prefix "/2" and subtract at this speed */
#define HUD_SPEED_HUNDRED  100          /* prefix "/1" and subtract at this speed */
#define HUD_BLANK          0x2f         /* '/' renders as a blank glyph (leading-zero suppression) */
#define HUD_PREFIX_00      0x2f2f       /* speedometer prefix "//" (<100) */

/* Phase 8 — crash / end-of-race bonus tally (recreate's draw_crash_fx @0x15872). Runs when the
 * crash-arm timer has gone negative. It drains the bonus time / units / score-digit rollovers into
 * the score, then redraws the score number (num blitter) and the gauge bars. The score number, the
 * bar strings and the rollover records overlap in one HUD-text region, so we work on a mutable copy
 * of it (crash_buf) — offsets below are relative to its base (recreate addr - 0x18172). The score
 * arithmetic (add_score) and sound are off-framebuffer where they don't feed a drawn buffer. */
#define CRASH_NUM_STR_OFF  0x00         /* CRASH_STR_NUM  0x18172 */
#define CRASH_BAR1_OFF     0x08         /* CRASH_STR_BAR1 0x1817a */
#define CRASH_ROLLOVER_OFF 0x1c         /* rollover records 0x1818e (stride 0xe) */
#define CRASH_HUD_LAP_OFF  0x68         /* CRASH_HUD_LAP  0x181da ('0' + crash_lap) */
#define CRASH_BAR2_OFF     0x5a         /* CRASH_STR_BAR2 0x181cc */
#define CRASH_ROLL_STRIDE  0xe
#define CRASH_ROLL_TARGET  0x60         /* a record is done when 0x60 - digit[-1] - digit == 0 */
#define CRASH_ROLL_HI      0x35         /* the tens digit that resets instead of carrying */
#define CRASH_FRAME_MIN    0xa          /* the drain body runs once crash_frame reaches this */
#define CRASH_NUM_DST      0x4770       /* draw_num dst */
#define CRASH_BAR_FIRST    0x54b8
#define CRASH_BAR_LOOP     0x5cd0
#define CRASH_BAR_LOOP_STEP 0x500
#define CRASH_BAR5_A       0x6ba0
#define CRASH_BAR5_B       0x73c0
#define CRASH_BAR_FIN_A    0x5480
#define CRASH_BAR_FIN_B    0x5ca0
#define CRASH_YOFF_IDLE    0x18         /* bar y-offset when no active bars */

/* Phase 3 — dashboard-variant masked sprite. A record {src_off, dst_off, rows-1} picked by
 * dsp_variant_idx selects one sprite in buf_c (via dsp_src). Per row the source is a 4-plane cell
 * {mask, inkA, inkB, inkC}: the first source word is the transparency mask (kept where set); inkA/B
 * fill the first two plane words, inkC (broadcast) the last two. Skipped while dsp_toggle is set. */
static void hud_dsp_sprite(const HudState *s, const HudAssets *a, Framebuffer *fb) {
    if (s->dsp_toggle) return;
    uint8_t *px = fb->px;
    const uint8_t *rec = a->dsp_table + s->dsp_variant_idx;
    const uint8_t *src = a->dsp_src + be32(rec);              /* src_off rebased into dsp_src */
    Offset dst = (Offset)sx16(be16(rec + 4));                /* buffer-relative dst */
    int16_t rows = (int16_t)be16(rec + 6);                   /* loop runs rows+1 times */
    for (int r = 0; r <= rows; r++, dst += ROW_STRIDE, src += ROW_STRIDE) {
        Plane4 mask = dup16(be16(src));
        wr32(px + dst, be32(px + dst) & mask);               /* keep background where mask is set */
        wr16(px + dst,     (uint16_t)(be16(src + 2) | be16(px + dst)));
        wr16(px + dst + 2, (uint16_t)(be16(src + 4) | be16(px + dst + 2)));
        wr32(px + dst + 4, (be32(px + dst + 4) & mask) | dup16(be16(src + 6)));
    }
}

static void hud_flag_bars(const HudState *s, Framebuffer *fb) {
    if (s->flag_seq_count < 1) return;
    uint8_t *px = fb->px;
    Offset a = FLAG_BAR_TOP_DST;
    for (int r = 0; r < FLAG_BAR_TOP_ROWS; r++, a += ROW_STRIDE)
        cell_and(px, a, FLAG_BAR_CLEAR_BIT);
    a -= FLAG_BAR_TOP_BACK;
    for (int c = 0; c < s->flag_seq_count; c++) {
        cell_fill(px, a, 0, 0); a += ROW_STRIDE;                        /* dark cap */
        for (int r = 0; r < FLAG_BAR_MID_ROWS; r++, a += ROW_STRIDE)    /* lit body */
            cell_fill(px, a, FLAG_BAR_CLEAR_BIT, FLAG_BAR_CLEAR_BIT);
        cell_fill(px, a, 0, 0);                                         /* dark cap */
        a += 8 - FLAG_BAR_COL_BACK;                                     /* net +8 to next bar */
    }
}

static void hud_color_bars(const HudState *s, const HudAssets *assets, Framebuffer *fb) {
    uint8_t *px = fb->px;
    Offset a = COLOR_BAR_DST;
    Offset mask_off = 0;                                               /* into color_bar_mask */
    int32_t cidx = sx16(s->flag_seq_off) + sx16(s->dsp_color_scroll);  /* scrolling cursor */
    for (int col = 0; col < COLOR_BAR_COLS; col++) {
        int16_t off = (int16_t)(uint16_t)(assets->color_bar_cidx[cidx + col] << 3);
        Plane4 fill_lo = be32(assets->color_pairs + off);
        Plane4 fill_hi = be32(assets->color_pairs + off + 4);
        cell_and(px, a, COLOR_BAR_PRECLEAR); a += ROW_STRIDE;          /* top cap */
        for (int r = 0; r < COLOR_BAR_ROWS; r++, a += ROW_STRIDE) {
            Plane4 mask = dup16(be16(assets->color_bar_mask + mask_off));
            Plane4 ink  = dup16(be16(assets->color_bar_mask + mask_off + 2));
            mask_off += 4;
            cell_overlay(px, a, mask, ink, fill_lo, fill_hi);
        }
        a -= COLOR_BAR_COL_BACK;
    }
}

static void hud_fuel_gauge(const HudState *s, const HudAssets *assets, Framebuffer *fb) {
    if (s->crash_lap < 1) return;
    uint8_t *px = fb->px;
    Plane4 f_lo = (be32(assets->fuel_mask)     & FUEL_MASK_KEEP) | FUEL_MID;
    Plane4 f_hi = (be32(assets->fuel_mask + 4) & FUEL_MASK_KEEP) | FUEL_MID;
    Offset g = FUEL_BASE;
    for (int c = 0; c < s->crash_lap; c++) {
        cell_and(px, g, FUEL_EDGE);                        g += ROW_STRIDE;   /* top cap */
        cell_fill(px, g, FUEL_NEAR_FULL, FUEL_NEAR_FULL);  g += ROW_STRIDE;
        cell_fill(px, g, FUEL_MID, FUEL_MID);              g += ROW_STRIDE;
        for (int r = 0; r < 4; r++, g += ROW_STRIDE) cell_fill(px, g, f_lo, f_hi);
        cell_fill(px, g, FUEL_MID, FUEL_MID);              g += ROW_STRIDE;
        for (int r = 0; r < 5; r++, g += ROW_STRIDE) cell_fill(px, g, FUEL_LOW, FUEL_LOW);
        cell_fill(px, g, FUEL_NEAR_FULL, FUEL_NEAR_FULL);  g += ROW_STRIDE;
        cell_and(px, g, FUEL_EDGE);                                           /* bottom cap */
        g += 8 - FUEL_COL_BACK;                                        /* net +8 to next unit */
    }
}

/* Phase 6b — the blinking small gauge, drawn instead of 6a when no bonus units remain. It shows
 * only on the lit blink phase: draw when bit1 of (gauge_blink - 1) is set (and the counter hasn't
 * wrapped negative). A gauge0 label, plus an extra bar underneath when gauge_blink_on. */
static void hud_small_gauge(const HudState *s, const HudAssets *a, Framebuffer *fb) {
    if (s->crash_lap >= 1) return;                       /* 6a drew the fuel columns instead */
    int16_t blink = (int16_t)(s->gauge_blink - 1);
    if (blink < 0 || !(blink & GAUGE_BLINK_BIT)) return; /* dark blink phase: nothing this frame */
    Plane4 f_lo = be32(a->color_pairs + SMALL_GAUGE_COLOR * COLOR_PAIR_STRIDE);
    Plane4 f_hi = be32(a->color_pairs + SMALL_GAUGE_COLOR * COLOR_PAIR_STRIDE + 4);
    Offset end, si = 0;
    si = rm_glyph_run(fb, SMALL_GAUGE_DST, f_lo, f_hi, a->font, a->small_gauge_str, si,
                      GAUGE_CELLS_M1, &end);
    if (s->gauge_blink_on)
        rm_glyph_run(fb, end, 0, 0xffffffff, a->font, a->small_gauge_str, si, TEXT_MAX_CELLS_M1, 0);
}

/* Phase 7 — the main gauge cluster: draw_hud_gauge0 then five draw_hud_bars, with the dst (A0) and
 * string cursor (A3) threaded across each sub-draw exactly as the 68000 leaves them. `str` is the
 * gauge string with the phase-1/2 speed/time digits already formatted in. */
static void hud_gauge_cluster(const HudAssets *a, const uint8_t *str, Framebuffer *fb) {
    Plane4 g_lo = be32(a->color_pairs + GAUGE_MAIN_COLOR * COLOR_PAIR_STRIDE);
    Plane4 g_hi = be32(a->color_pairs + GAUGE_MAIN_COLOR * COLOR_PAIR_STRIDE + 4);
    /* gauge0 derives its fill from the colour index (masked 0xf — here the same as g_lo/g_hi). */
    Plane4 f_lo = be32(a->color_pairs + (GAUGE_MAIN_COLOR & 0xf) * COLOR_PAIR_STRIDE);
    Plane4 f_hi = be32(a->color_pairs + (GAUGE_MAIN_COLOR & 0xf) * COLOR_PAIR_STRIDE + 4);
    const uint8_t *font = a->font;
    Offset end, si = 0;
    si = rm_glyph_run(fb, GAUGE_MAIN_DST, f_lo, f_hi, font, str, si, GAUGE_CELLS_M1, &end);
    si = rm_glyph_run(fb, end + GAUGE_BAR1_ADV, g_lo, g_hi, font, str, si, TEXT_MAX_CELLS_M1, &end);
    si = rm_glyph_run(fb, end + GAUGE_BAR2_ADV, g_lo, g_hi, font, str, si, TEXT_MAX_CELLS_M1, &end);
    si = rm_glyph_run(fb, end, 0, 0xffffffff, font, str, si, TEXT_MAX_CELLS_M1, &end);
    si = rm_glyph_run(fb, end, 0xffffffff, 0xffffffff, font, str, si, TEXT_MAX_CELLS_M1, &end);
    rm_glyph_run(fb, end - GAUGE_BAR5_BACK, 0x0000ffff, 0xffffffff, font, str, si, TEXT_MAX_CELLS_M1, 0);
}

/* Paint one plane word over the background: keep the background where `mask` is set, OR in `ink`. */
static inline void overlay_word(uint8_t *p, uint16_t mask, uint16_t ink) {
    wr16(p, (be16(p) & mask) | ink);
}

/* Phase 7 — the dashboard graphic: a masked blit from buf_c. Per group of four dest words the four
 * source words are (mask, a, b, c); each dest word keeps the background where mask is set and OR-s
 * in ink a, b, b, c (the middle word twice — one source word feeds two screen words). */
static void hud_dashboard(const HudAssets *a, Framebuffer *fb) {
    uint8_t *px = fb->px;
    Offset dst = DASHBOARD_DST, src = 0;                   /* src 0 = dashboard_src base (buf_c gfx) */
    const uint8_t *g = a->dashboard_src;
    for (int row = 0; row < DASH_ROWS; row++, dst += ROW_STRIDE, src += ROW_STRIDE) {
        Offset d = dst, s = src;
        for (int grp = 0; grp < DASH_GROUPS; grp++, d += 8, s += 8) {
            uint16_t mask = be16(g + s);
            uint16_t ink_a = be16(g + s + 2), ink_b = be16(g + s + 4), ink_c = be16(g + s + 6);
            overlay_word(px + d,     mask, ink_a);
            overlay_word(px + d + 2, mask, ink_b);
            overlay_word(px + d + 4, mask, ink_b);
            overlay_word(px + d + 6, mask, ink_c);
        }
    }
}

/* Render a decimal digit as its ASCII char, or `blank` when it is 0 (leading-zero suppression).
 * Shared by the speedometer and timer, which both draw a blanked tens digit + a units digit. */
static uint8_t digit_or_blank(uint16_t digit, uint8_t blank) {
    return digit ? '0' + digit : blank;
}

/* Phase 1 — format the speedometer digits into the gauge string: a "/N" hundreds prefix then a
 * leading-blank tens digit and a units digit. */
static void hud_format_speed(uint16_t speed, uint8_t *str) {
    uint16_t v = speed & 0xff;                       /* low byte of the speed word */
    uint16_t prefix = HUD_PREFIX_00;
    uint8_t blank = HUD_BLANK;                        /* leading char when the tens digit is 0 */
    if (v >= HUD_SPEED_HUNDREDS)    { prefix = HUD_PREFIX_00 + 3; v -= HUD_SPEED_HUNDREDS; blank = '0'; }
    else if (v >= HUD_SPEED_HUNDRED) { prefix = HUD_PREFIX_00 + 2; v -= HUD_SPEED_HUNDRED;  blank = '0'; }
    wr16(str + HUD_SPEED_TXT_OFF, prefix);
    str[HUD_SPEED_TXT_OFF + 2] = digit_or_blank(v / HUD_DIGIT_DIV, blank);
    str[HUD_SPEED_TXT_OFF + 3] = '0' + v % HUD_DIGIT_DIV;
}

/* Phase 2 — format the bonus-timer digits (blanked to 0 when the game is over). */
static void hud_format_time(uint16_t time_left, bool game_over, uint8_t *str) {
    uint16_t t = game_over ? 0 : time_left;
    str[HUD_TIME_TXT_OFF + 1] = digit_or_blank(t / HUD_DIGIT_DIV, HUD_BLANK);
    str[HUD_TIME_TXT_OFF + 2] = '0' + t % HUD_DIGIT_DIV;
}

/* Phase 8 — crash / end-of-race bonus tally. Drains time/units/rollovers into the score, then draws
 * the score number + gauge bars. `text` is the shared HUD-text buffer (crash offsets are relative to
 * its base, 0x18172); phase 8 is last, so it mutates it in place. Runs only once the crash-arm timer
 * is negative (else phase 8 just decays the timer — off-frame). */
static void hud_crash_fx(const HudState *s, const HudAssets *a, uint8_t *text, Framebuffer *fb) {
    if (!(s->hud_crash_timer < 0)) return;   /* timer >= 0: decay only (no draw this frame) */
    if (!s->crash_active) return;            /* draw_crash_fx bails (arms abort_flag; off-frame) */

    uint16_t frame = (uint16_t)(s->crash_frame + 1);
    int16_t crash_lap = s->crash_lap;

    if ((int16_t)frame >= CRASH_FRAME_MIN) {
        const uint8_t *delta = 0;
        if (s->time_left != 0) {
            delta = a->score_delta_time;                 /* time_left-- is off-frame */
        } else if (crash_lap != 0) {
            crash_lap -= 1;
            delta = a->score_delta_roll;
        } else {
            for (int i = (int)s->crash_bars - 1, p = CRASH_ROLLOVER_OFF; i >= 0;
                 i--, p += CRASH_ROLL_STRIDE) {
                if ((uint8_t)(CRASH_ROLL_TARGET - text[p - 1] - text[p]) != 0) {
                    if (text[p] == CRASH_ROLL_HI) text[p] -= 5;
                    else { text[p] += 5; text[p - 1] -= 1; }
                    delta = a->score_delta_roll;
                    break;
                }
            }                                            /* the abort_flag arm here is off-frame */
        }
        if (delta) rm_score_add(text + RM_HUD_SCORE_BCD_OFF, text + RM_HUD_SCORE_STR_OFF, delta, s->game_over);
    }

    text[CRASH_HUD_LAP_OFF] = (uint8_t)('0' + crash_lap);

    uint8_t color = a->crash_color_tbl[frame & 7];
    Plane4 fill_lo = be32(a->color_pairs + color * COLOR_PAIR_STRIDE);
    Plane4 fill_hi = be32(a->color_pairs + color * COLOR_PAIR_STRIDE + 4);
    rm_num_run(fb, CRASH_NUM_DST, fill_lo, fill_hi, a->num_sprites, a->num_glyph_tbl,
               text, CRASH_NUM_STR_OFF, TEXT_MAX_CELLS_M1);

    uint16_t bars = s->crash_bars;
    Offset si = CRASH_BAR1_OFF;
    Offset yoff = CRASH_YOFF_IDLE;
    if (bars != 0) {
        si = rm_glyph_run(fb, CRASH_BAR_FIRST, fill_lo, fill_hi, a->font, text, si, TEXT_MAX_CELLS_M1, 0);
        for (int i = 0; i < bars; i++)
            si = rm_glyph_run(fb, CRASH_BAR_LOOP + (Offset)i * CRASH_BAR_LOOP_STEP, fill_lo, fill_hi,
                              a->font, text, si, TEXT_MAX_CELLS_M1, 0);
        yoff = 0;
    }
    si = CRASH_BAR2_OFF;
    if (bars == 5) {
        si = rm_glyph_run(fb, CRASH_BAR5_A + yoff, fill_lo, fill_hi, a->font, text, si, TEXT_MAX_CELLS_M1, 0);
        si = rm_glyph_run(fb, CRASH_BAR5_B + yoff, fill_lo, fill_hi, a->font, text, si, TEXT_MAX_CELLS_M1, 0);
    }
    si = rm_glyph_run(fb, CRASH_BAR_FIN_A + yoff, fill_lo, fill_hi, a->font, text, si, TEXT_MAX_CELLS_M1, 0);
    rm_glyph_run(fb, CRASH_BAR_FIN_B + yoff, fill_lo, fill_hi, a->font, text, si, TEXT_MAX_CELLS_M1, 0);
    /* the abort_flag decay tail is off-frame */
}

/* Overlay the ported HUD phases onto the current frame in fb. */
void rm_draw_hud(const HudState *s, const HudAssets *assets, Framebuffer *fb) {
    /* One mutable copy of the HUD-text region: phases 1-2 format the speed/time digits into it, the
     * phase-7 gauge cluster and phase-8 crash tally then render (their buffers overlap it). */
    uint8_t text[HUD_TEXT_LEN];
    memcpy(text, assets->hud_text, HUD_TEXT_LEN);
    uint8_t *gauge_str = text + GAUGE_OFF;
    hud_format_speed(s->speed, gauge_str);
    hud_format_time(s->time_left, s->game_over, gauge_str);

    hud_dsp_sprite(s, assets, fb);
    hud_flag_bars(s, fb);
    hud_color_bars(s, assets, fb);
    hud_fuel_gauge(s, assets, fb);
    hud_small_gauge(s, assets, fb);
    hud_gauge_cluster(assets, gauge_str, fb);
    hud_dashboard(assets, fb);
    hud_crash_fx(s, assets, text, fb);
}
