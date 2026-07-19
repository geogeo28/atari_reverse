/* hud.c — remaster of the in-race HUD (recreate's draw_hud @0x1555e).
 *
 * Ported so far — the pure plane-write phases plus the gauge cluster:
 *   Phase 4  flag-sequence bars   one lit vertical bar per matched-in-a-row flag
 *   Phase 5  colour-tinted bars    five columns tinted from color_pairs via a scrolling cursor
 *   Phase 6a fuel/tacho gauge      one fixed multi-row column per remaining bonus unit
 *   Phase 7  main gauge cluster    gauge0 + five bars (glyph blitter) + the dashboard graphic
 * Still to port: phase 3 (dashboard-variant buf_c sprite), phase 6b (blinking small gauge),
 * phase 8 (crash fx). See STATUS.md.
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
#define GAUGE_STR_LEN      64
#define HUD_SPEED_TXT_OFF  0x24         /* A_hud_speed_txt (0x1823c) - gauge string base (0x18218) */
#define HUD_TIME_TXT_OFF   0x2e         /* A_hud_time_txt  (0x18246) - gauge string base */
#define HUD_DIGIT_DIV      10           /* tens/units split */
#define HUD_SPEED_HUNDREDS 200          /* prefix "/2" and subtract at this speed */
#define HUD_SPEED_HUNDRED  100          /* prefix "/1" and subtract at this speed */
#define HUD_BLANK          0x2f         /* '/' renders as a blank glyph (leading-zero suppression) */
#define HUD_PREFIX_00      0x2f2f       /* speedometer prefix "//" (<100) */

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
static void hud_format_time(uint16_t time_left, int16_t game_over, uint8_t *str) {
    uint16_t t = game_over != 0 ? 0 : time_left;
    str[HUD_TIME_TXT_OFF + 1] = digit_or_blank(t / HUD_DIGIT_DIV, HUD_BLANK);
    str[HUD_TIME_TXT_OFF + 2] = '0' + t % HUD_DIGIT_DIV;
}

/* Overlay the ported HUD phases onto the current frame in fb. */
void rm_draw_hud(const HudState *s, const HudAssets *assets, Framebuffer *fb) {
    /* Phases 1-2 format the speed/time digits into a mutable copy of the gauge string, which the
     * phase-7 gauge cluster then renders (the text buffers overlap that string). */
    uint8_t str[GAUGE_STR_LEN];
    memcpy(str, assets->gauge_str, GAUGE_STR_LEN);
    hud_format_speed(s->speed, str);
    hud_format_time(s->time_left, s->game_over, str);

    hud_flag_bars(s, fb);
    hud_color_bars(s, assets, fb);
    hud_fuel_gauge(s, assets, fb);
    hud_gauge_cluster(assets, str, fb);
    hud_dashboard(assets, fb);
}
