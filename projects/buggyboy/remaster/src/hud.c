/* hud.c — remaster of the in-race HUD (recreate's draw_hud @0x1555e).
 *
 * Ported so far — the pure plane-write phases that read only scalar state + small static tables
 * (no buf_c sprites, no glyph/gauge helpers):
 *   Phase 4  flag-sequence bars   one lit vertical bar per matched-in-a-row flag
 *   Phase 5  colour-tinted bars    five columns tinted from color_pairs via a scrolling cursor
 *   Phase 6a fuel/tacho gauge      one fixed multi-row column per remaining bonus unit
 * Still to port (drive footprint coverage to 100%): phase 3 (dashboard-variant buf_c sprite),
 * phases 6b/7 (blinking gauge + main gauge cluster + dashboard, via the glyph helpers), phase 8
 * (crash fx). See STATUS.md.
 *
 * The framebuffer is ST hardware format (see st.h); byte offsets below are relative to the draw
 * buffer origin (fb->px[0]) and each row steps one scanline (SCREEN_ROW_BYTES). The layout matches
 * recreate exactly because the equivalence harness diffs these bytes against recreate's output.
 */
#include "game.h"
#include "screen.h"
#include "st.h"

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

static void hud_flag_bars(const HudState *s, uint8_t *px) {
    if (s->flag_seq_count < 1) return;
    uint32_t a = FLAG_BAR_TOP_DST;
    for (int r = 0; r < FLAG_BAR_TOP_ROWS; r++, a += ROW_STRIDE) {
        wr32(px + a,     be32(px + a)     & FLAG_BAR_CLEAR_BIT);
        wr32(px + a + 4, be32(px + a + 4) & FLAG_BAR_CLEAR_BIT);
    }
    a -= FLAG_BAR_TOP_BACK;
    for (int c = 0; c < s->flag_seq_count; c++) {
        wr32(px + a, 0); wr32(px + a + 4, 0); a += ROW_STRIDE;          /* dark cap */
        for (int r = 0; r < FLAG_BAR_MID_ROWS; r++, a += ROW_STRIDE) {  /* lit body */
            wr32(px + a,     FLAG_BAR_CLEAR_BIT);
            wr32(px + a + 4, FLAG_BAR_CLEAR_BIT);
        }
        wr32(px + a, 0); wr32(px + a + 4, 0);                           /* dark cap */
        a += 8 - FLAG_BAR_COL_BACK;                                     /* net +8 to next bar */
    }
}

static void hud_color_bars(const HudState *s, const HudAssets *assets, uint8_t *px) {
    uint32_t a = COLOR_BAR_DST;
    uint32_t mask_off = 0;                                             /* into color_bar_mask */
    int32_t cidx = sx16(s->flag_seq_off) + sx16(s->dsp_color_scroll);  /* scrolling cursor */
    for (int col = 0; col < COLOR_BAR_COLS; col++) {
        int16_t off = (int16_t)(uint16_t)(assets->color_bar_cidx[cidx + col] << 3);
        uint32_t fill_lo = be32(assets->color_pairs + off);
        uint32_t fill_hi = be32(assets->color_pairs + off + 4);
        wr32(px + a,     be32(px + a)     & COLOR_BAR_PRECLEAR);        /* top cap */
        wr32(px + a + 4, be32(px + a + 4) & COLOR_BAR_PRECLEAR);
        a += ROW_STRIDE;
        for (int r = 0; r < COLOR_BAR_ROWS; r++, a += ROW_STRIDE) {
            uint32_t mask = dup16(be16(assets->color_bar_mask + mask_off));
            uint32_t ink  = dup16(be16(assets->color_bar_mask + mask_off + 2));
            mask_off += 4;
            wr32(px + a,     (be32(px + a)     & mask) | (ink & fill_lo));
            wr32(px + a + 4, (be32(px + a + 4) & mask) | (ink & fill_hi));
        }
        a -= COLOR_BAR_COL_BACK;
    }
}

static void hud_fuel_gauge(const HudState *s, const HudAssets *assets, uint8_t *px) {
    if (s->crash_lap < 1) return;
    uint32_t f_lo = (be32(assets->fuel_mask)     & FUEL_MASK_KEEP) | FUEL_MID;
    uint32_t f_hi = (be32(assets->fuel_mask + 4) & FUEL_MASK_KEEP) | FUEL_MID;
    uint32_t g = FUEL_BASE;
    for (int c = 0; c < s->crash_lap; c++) {
        wr32(px + g, be32(px + g) & FUEL_EDGE); wr32(px + g + 4, be32(px + g + 4) & FUEL_EDGE); g += ROW_STRIDE;
        wr32(px + g, FUEL_NEAR_FULL); wr32(px + g + 4, FUEL_NEAR_FULL); g += ROW_STRIDE;
        wr32(px + g, FUEL_MID); wr32(px + g + 4, FUEL_MID); g += ROW_STRIDE;
        for (int r = 0; r < 4; r++, g += ROW_STRIDE) { wr32(px + g, f_lo); wr32(px + g + 4, f_hi); }
        wr32(px + g, FUEL_MID); wr32(px + g + 4, FUEL_MID); g += ROW_STRIDE;
        for (int r = 0; r < 5; r++, g += ROW_STRIDE) { wr32(px + g, FUEL_LOW); wr32(px + g + 4, FUEL_LOW); }
        wr32(px + g, FUEL_NEAR_FULL); wr32(px + g + 4, FUEL_NEAR_FULL); g += ROW_STRIDE;
        wr32(px + g, be32(px + g) & FUEL_EDGE); wr32(px + g + 4, be32(px + g + 4) & FUEL_EDGE);
        g += 8 - FUEL_COL_BACK;                                        /* net +8 to next unit */
    }
}

/* Overlay the ported HUD phases onto the current frame in fb. */
void rm_draw_hud(const HudState *s, const HudAssets *assets, Framebuffer *fb) {
    hud_flag_bars(s, fb->px);
    hud_color_bars(s, assets, fb->px);
    hud_fuel_gauge(s, assets, fb->px);
}
