/* ground.c — remaster of draw_ground (recreate's g_draw_ground @0x10ff2).
 *
 * Fills the ground/horizon band below the road. Scans up to GROUND_SCAN_ENTRIES scanline descriptors
 * for the first draw marker — 0x1a a horizon colour gradient (a band record picks 1-3 solid-colour
 * scanlines), 0x1c a solid ground fill (1 scanline, 2 for the nearest entry) — and draws that one
 * band, then returns. The band's screen offset comes from the per-entry offset table indexed by the
 * view column. Entry i selects band (GROUND_SCAN_ENTRIES-1 - i), so the descriptor scan runs from the
 * farthest band inward.
 *
 * Byte-for-byte identical output to recreate's core (see test/test_ground.py).
 */
#include "game.h"
#include "screen.h"
#include "st.h"

#define GROUND_COL_STRIDE   0x22        /* per-entry stride in the offset table */
#define GROUND_MARK_GRADIENT 0x1a
#define GROUND_MARK_SOLID    0x1c
#define GROUND_BAND_STRIDE   8          /* one gradient record */
#define GROUND_ROW_LONGS     10         /* 10 * 16 bytes = one 160-byte scanline */
#define GROUND_SOLID_ROWS_M1     9      /* solid fill: 1 scanline */
#define GROUND_SOLID_ROWS_M1_TOP 0x13   /* nearest entry (band==0): 2 scanlines */
#define GROUND_LIT_PLANES    0xffffffffu /* lit ground row (band>=9): moveq #$ff sign-extends */
#define GROUND_NEAR_BAND     9          /* band >= this is "distant" (lit / gradient clamp) */
#define GROUND_MID_BAND      5          /* gradient band clamp midpoint */
#define GROUND_GRAD_LAST     6          /* highest gradient record index (rec = (6-band)*stride) */

/* Base of the band in the draw buffer: the entry's signed word offset, indexed by the view column. */
static Offset ground_dst(const GroundAssets *a, uint32_t col, int16_t view) {
    return sx16(be16(a->col_tbl + col + sx16((uint16_t)view)));
}

/* Write one 160-byte scanline as the longword pattern (lo, hi, lo, hi) x GROUND_ROW_LONGS. */
static Offset ground_row(Framebuffer *fb, Offset dst, Plane4 lo, Plane4 hi) {
    for (int j = 0; j < GROUND_ROW_LONGS; j++) {
        wr32(fb->px + dst, lo);     wr32(fb->px + dst + 4, hi);
        wr32(fb->px + dst + 8, lo); wr32(fb->px + dst + 12, hi);
        dst += 16;
    }
    return dst;
}

/* 0x1a: a colour gradient of (bands+1) scanlines, colours from the band record. */
static void ground_gradient(const GroundAssets *a, Framebuffer *fb, uint32_t col, int16_t view,
                            int band) {
    if (band >= GROUND_NEAR_BAND) band = GROUND_GRAD_LAST;
    else if (band >= GROUND_MID_BAND) band = GROUND_MID_BAND;   /* else keep band */
    const uint8_t *rec = a->band_records + (GROUND_GRAD_LAST - band) * GROUND_BAND_STRIDE;
    Offset dst = ground_dst(a, col, view);
    int bands = *rec++;                        /* dbf count */
    dst -= 2 * *rec++;                          /* suba.w d2 twice (backup) */
    for (int b = bands; b >= 0; b--) {
        const uint8_t *pattern = a->color_pairs + *rec++;   /* colour byte -> color_pairs offset */
        dst = ground_row(fb, dst, be32(pattern), be32(pattern + 4));
    }
}

/* 0x1c: a solid fill; lit (planes set) when the entry is distant, else black. */
static void ground_solid(const GroundAssets *a, Framebuffer *fb, uint32_t col, int16_t view,
                         int band) {
    Offset dst = ground_dst(a, col, view);
    Plane4 lo = (band >= GROUND_NEAR_BAND) ? GROUND_LIT_PLANES : 0;
    int rows_m1 = (band == 0) ? GROUND_SOLID_ROWS_M1_TOP : GROUND_SOLID_ROWS_M1;
    for (int r = 0; r <= rows_m1; r++) {
        wr32(fb->px + dst, lo);     wr32(fb->px + dst + 4, 0);
        wr32(fb->px + dst + 8, lo); wr32(fb->px + dst + 12, 0);
        dst += 16;
    }
}

void rm_draw_ground(const GroundState *s, const GroundAssets *a, Framebuffer *fb) {
    uint32_t col = 0;
    for (int i = 0; i < GROUND_SCAN_ENTRIES; i++, col += GROUND_COL_STRIDE) {
        int band = GROUND_SCAN_ENTRIES - 1 - i;
        uint8_t marker = s->markers[i];
        if (marker == GROUND_MARK_GRADIENT) { ground_gradient(a, fb, col, s->view, band); return; }
        if (marker == GROUND_MARK_SOLID)    { ground_solid(a, fb, col, s->view, band); return; }
    }
}
