/* intermission.c — intermission-screen block blitter (intermission_poll @ 0x12914).
 *
 * Despite the "poll" name (inferred from call context, unconfirmed), this reads no input: it is a
 * table-driven plain block copy. A 9-entry control table (INTERMISSION_BLITS, inline right after
 * the function body) drives nine rectangular copies from a pre-rendered screen-layout graphic in
 * buf_c into the draw buffer (physbase_tbl[flip_idx] + 0x990). Each entry is three words:
 *   src_off (u16, unsigned)   dst_off (i16, signed)   dims (u16)
 * dims packs the row count-1 in the high byte and the inner 8-byte-unit count-1 in the low nibble,
 * so a row copies ((dims & 0xf) + 1) * 8 contiguous bytes and there are ((dims >> 8) + 1) rows.
 * Source and destination both step one scanline (ROW_STRIDE) per row — the source is stored at
 * screen pitch. No mask/transparency; src and dst bases are both recomputed fresh each entry.
 */
#include <string.h>
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

#define INTERMISSION_BLITS   0x1296a   /* inline control table: 9 x {src_off, dst_off, dims} words */
#define INTERMISSION_ENTRIES 9
#define INTERMISSION_SRC_OFF 0x32c80   /* source base = buf_c + this */
#define INTERMISSION_DST_OFF 0x990     /* dest base = physbase_tbl[flip_idx] + this */
#define BLIT_UNIT            8          /* bytes per inner unit (two longword moves) */

void g_intermission_poll(uint8_t *image) {
    int16_t flip_idx = (int16_t)be16(image + A_flip_idx);
    uint32_t dst_base = be32(image + A_physbase_tbl + flip_idx) + INTERMISSION_DST_OFF;
    uint32_t src_base = be32(image + A_buf_c) + INTERMISSION_SRC_OFF;

    uint32_t tbl = INTERMISSION_BLITS;
    for (int e = 0; e < INTERMISSION_ENTRIES; e++, tbl += 6) {
        uint32_t src = src_base + be16(image + tbl);                   /* unsigned src offset */
        uint32_t dst = dst_base + sign_ext16(be16(image + tbl + 2));   /* signed dst offset */
        uint16_t dims = be16(image + tbl + 4);
        uint32_t width = (uint32_t)((dims & 0xf) + 1) * BLIT_UNIT;
        int rows = (dims >> 8) + 1;
        for (int r = 0; r < rows; r++)
            memcpy(image + dst + r * ROW_STRIDE, image + src + r * ROW_STRIDE, width);
    }
}

/* --- draw_intermission @ 0x129ba --- The scrolling between-legs screen: a high-score table
 * (section 1), the leg-time numbers (section 2) and a two-line credit (section 3) all scroll
 * vertically together, driven by the signed scroll offset at A_int_scroll. Each row's screen
 * y-position is (scroll << 3) + a per-row base; a positive position clips against the top of the
 * visible band (INT_MAX_VIS rows) and a negative one scrolls the row up off screen, advancing the
 * source string past the clipped rows. Rows entirely off screen (negative remaining count) are
 * skipped. Sections 1 and 3 draw text rows (draw_text_row); section 2 draws digit sprites
 * (draw_num). All three share the clip-and-draw logic below. The scroll offset lives at A_int_scroll.
 *
 * Layout tables (const, inline in the program): section 1 = 15 entries, section 3 = 3 entries,
 * each 5 words {base, dst_add, max_rows, colour, str_off}. Section 1 draws 5 stacked rows per
 * entry (str = highscore_table + str_off + row*SEC1_STR_STEP). */
#define INT_TBL1          0x1858c   /* section 1 layout: 15 x 5 words */
#define INT_TBL3          0x18622   /* section 3 layout: 3 x 5 words */
#define INT_CREDITS_STR   0x180f4   /* section 3 string base (+ entry str_off) */
#define INT_TBL_ENTRY     10        /* 5 words per layout entry */
#define INT_FILL_DST      0x1f40    /* fill_span clears the scroll band: buffer + this */
#define INT_FILL_COLOR    6
#define INT_FILL_CELLS_M1 0x397
#define INT_BASE_ADJ      0x318     /* each entry's base is shifted up by this before scrolling */
#define INT_MAX_VIS       0x13      /* visible rows from the top of the band (positive-position clip) */
#define INT_SEC1_ROWS     5         /* stacked rows per section-1 entry */
#define INT_SEC1_STR_STEP 0x80      /* string advance between those rows */
#define INT_SEC2_ROWS     5
#define INT_SEC2_STR_OFF  0x884     /* section 2 numbers: buf_a + this + row*SEC2_STR_STEP */
#define INT_SEC2_STR_STEP 0xc
#define INT_SEC2_DST_BASE 0x2620    /* section 2 dst = y-position + this */
#define INT_SEC2_COLOR    0xd
#define INT_SEC2_MAX_ROWS 8         /* off-top row budget for the numbers (vs INT_MAX_VIS on-screen) */

/* Clip a scrolling row: base is the row's un-scrolled position. Returns the visible row count
 * (negative => fully off screen, skip) and writes the screen y-position to *ypos and advances
 * *str past clipped-off leading rows (by `str_step_clip` bytes each). off_top_budget is the row
 * count used when the row has scrolled above the band top. */
static int clip_scroll_row(uint8_t *image, int16_t base, uint32_t *str, int str_step_clip,
                           int16_t off_top_budget, int16_t *ypos) {
    int16_t pos = (int16_t)(((int16_t)be16(image + A_int_scroll) << 3) + base);
    if (pos < 0) {                                    /* scrolled above the band: clip the top rows */
        int16_t clip = (int16_t)(-pos) >> 3;
        *str += (uint32_t)str_step_clip * (uint16_t)clip;
        *ypos = 0;
        return off_top_budget - clip;
    }
    *ypos = pos;                                      /* within the band: clip against its bottom */
    return INT_MAX_VIS - (pos >> 3);
}

void g_draw_intermission(uint8_t *image) {
    g_fill_span(image, INT_FILL_DST, INT_FILL_COLOR, INT_FILL_CELLS_M1);

    /* Section 1: 15 entries x 5 stacked high-score text rows. */
    uint32_t t1 = INT_TBL1;
    for (int e = 0; e < 15; e++, t1 += INT_TBL_ENTRY) {
        int16_t base = (int16_t)(be16(image + t1) - INT_BASE_ADJ);
        int16_t dst_add = (int16_t)be16(image + t1 + 2);
        int16_t max_rows = (int16_t)be16(image + t1 + 4);
        int16_t colour = (int16_t)be16(image + t1 + 6);
        int16_t str_off = (int16_t)be16(image + t1 + 8);
        int16_t row_str = 0;
        for (int i = 0; i < INT_SEC1_ROWS; i++) {
            uint32_t str = A_highscore_table + sign_ext16((uint16_t)str_off) + sign_ext16((uint16_t)row_str);
            int16_t ypos;
            int16_t rows = (int16_t)clip_scroll_row(image, base, &str, 2, max_rows, &ypos);
            if (rows >= 0)
                g_draw_text_row(image, (uint16_t)(int16_t)(ypos + dst_add), (uint16_t)colour,
                                (uint16_t)rows, str);
            base += ROW_STRIDE;
            row_str += INT_SEC1_STR_STEP;
        }
    }

    /* Section 2: 5 scrolling leg-time numbers from buf_a. */
    int16_t base = (int16_t)(0x10 - INT_BASE_ADJ);
    int16_t num_str = 0;
    for (int i = 0; i < INT_SEC2_ROWS; i++) {
        uint32_t str = be32(image + A_buf_a) + INT_SEC2_STR_OFF + sign_ext16((uint16_t)num_str);
        int16_t ypos;
        int16_t rows = (int16_t)clip_scroll_row(image, base, &str, 1, INT_SEC2_MAX_ROWS, &ypos);
        if (rows >= 0)
            g_draw_num(image, (uint16_t)(int16_t)(ypos + INT_SEC2_DST_BASE), INT_SEC2_COLOR,
                       (uint16_t)rows, str);
        base += ROW_STRIDE;
        num_str += INT_SEC2_STR_STEP;
    }

    /* Section 3: 3 scrolling credit lines. */
    uint32_t t3 = INT_TBL3;
    for (int e = 0; e < 3; e++, t3 += INT_TBL_ENTRY) {
        int16_t b3 = (int16_t)(be16(image + t3) - INT_BASE_ADJ);
        int16_t dst_add = (int16_t)be16(image + t3 + 2);
        int16_t max_rows = (int16_t)be16(image + t3 + 4);
        int16_t colour = (int16_t)be16(image + t3 + 6);
        int16_t str_off = (int16_t)be16(image + t3 + 8);
        uint32_t str = INT_CREDITS_STR + sign_ext16((uint16_t)str_off);
        int16_t ypos;
        int16_t rows = (int16_t)clip_scroll_row(image, b3, &str, 2, max_rows, &ypos);
        if (rows >= 0)
            g_draw_text_row(image, (uint16_t)(int16_t)(ypos + dst_add), (uint16_t)colour,
                            (uint16_t)rows, str);
    }
}

/* --- fade_step @ 0x129a0 --- One animation step of the between-legs screen. It repaints the
 * backdrop (fill_screen colour 6), re-copies the static block layout (intermission_poll), stamps
 * the fixed Elite Systems header line (draw_text), then falls straight through into
 * draw_intermission to render the three scrolling sections. No register arguments; a prologue in
 * front of draw_intermission (no rts of its own — it shares draw_intermission's). */
#define FADE_FILL_COLOR  6
#define FADE_HEADER_DST  0x7448    /* draw buffer offset for the copyright header line */
#define FADE_HEADER_COLOR 0xf
#define FADE_HEADER_STR  0x18002   /* "/@/ELITE/SYSTEMS/INTERNATIONAL/1988/" (const image data) */

void g_fade_step(uint8_t *image) {
    g_fill_screen(image, FADE_FILL_COLOR);
    g_intermission_poll(image);
    g_draw_text(image, FADE_HEADER_DST, FADE_HEADER_COLOR, FADE_HEADER_STR);
    g_draw_intermission(image);
}

/* --- intermission @ 0x127a0 --- The attract-mode / between-legs loop. It never returns except on a
 * player abort (check_abort); the differential tests below reach each piece by entering at its PC.
 * Four phases run in a cycle (the tail `bra` loops back to the top):
 *   A) scrolling hi-score/credits screen: paint one draw_intermission frame per tick, timed by a
 *      free-running timer that advances the scroll and, when the scroll wraps, a dwell counter;
 *   B) warm up the next demo leg: advance leg_select, (re)init the leg, settle it with a burst of
 *      game_update, then paint the first rendered frame;
 *   C) play the demo: game_update + the full render pipeline per frame, for INT_C_FRAMES frames;
 *   D) results carousel: cycle draw_leg_results across legs 0..4, dwelling INT_D_DWELL frames each.
 * Phases A/C/D poll check_abort once per frame and return immediately on abort. Phase B has no poll.
 *
 * The counter arithmetic mirrors the 68k word ops (subq/addq + signed branch). The three phase
 * "step" helpers are the loop bodies, split out so each can be entered mid-function and diffed
 * against the oracle; g_intermission itself composes them with the prologue and Phase B. */
#define INT_SCROLL_INIT   0x63     /* prologue: initial scroll position */
#define INT_TIMER_INIT    0x3b     /* prologue: initial Phase-A timer */
#define INT_FRAME_INIT    0x14     /* prologue: initial scroll dwell counter */
#define INT_TIMER_WRAP    0x5c     /* Phase-A timer reloads here when it underflows */
#define INT_SCROLL_GATE   0x49     /* timer >= this advances the scroll one step */
#define INT_PAL_A         0x17fe2  /* prologue palette (xbios_setpalette A0; no image effect) */
#define INT_PAL_B         0x17fa2  /* Phase-B (demo warm-up) palette */
#define INT_PAL_D         0x17f62  /* Phase-D (results carousel) palette */
#define INT_B_WARMUP      0x33     /* Phase-B settle: game_update iterations (moveq #0x32 + dbf) */
#define INT_B_LEGFLAGS    0x5a0001 /* leg_flags_c90 seed for the demo leg */
#define INT_C_FRAMES      0x96     /* Phase-C demo length: frames until the counter breaks */
#define INT_D_DWELL       0x1a     /* Phase-D per-leg dwell (draw_leg_results frames before advancing) */
#define INT_LEGS          5        /* legs cycled by the attract loop */

/* Phase-A step (g_int_stepA) return codes. */
#define INT_A_CONTINUE 0
#define INT_A_ABORT    1           /* check_abort fired -> intermission returns */
#define INT_A_BREAK    2           /* dwell counter exhausted -> advance to Phase B */
/* Phase-D counter-slice (g_int_stepD_counter) return codes. */
#define INT_D_DRAW    0            /* dwell not elapsed: draw this frame */
#define INT_D_ADVANCE 1            /* dwell elapsed, next leg (init_leg_dash done): draw this frame */
#define INT_D_RESTART 2            /* legs exhausted: restart the whole cycle */

static uint16_t rdw(uint8_t *im, uint32_t a) { return be16(im + a); }
static void wrw(uint8_t *im, uint32_t a, uint16_t v) { wr16(im + a, v); }

/* Phase-A body (0x27cc): tick the free-running timer; while it sits in the gate window advance the
 * scroll one step, and when the scroll underflows tick the dwell counter down. Then paint one
 * scrolling frame and poll for abort. Returns INT_A_BREAK (dwell exhausted -> Phase B, before any
 * draw), INT_A_ABORT (player abort), or INT_A_CONTINUE. */
int g_int_stepA(uint8_t *image) {
    int16_t timer = (int16_t)(rdw(image, A_int_timer) - 1);
    if (timer < 0) timer = INT_TIMER_WRAP;
    wrw(image, A_int_timer, (uint16_t)timer);
    if ((int16_t)(timer - INT_SCROLL_GATE) >= 0) {
        int16_t scroll = (int16_t)(rdw(image, A_int_scroll) - 1);
        wrw(image, A_int_scroll, (uint16_t)scroll);
        if (scroll < 0) {
            wrw(image, A_int_scroll, 0);
            int16_t dwell = (int16_t)(rdw(image, A_int_frame) - 1);
            wrw(image, A_int_frame, (uint16_t)dwell);
            if (dwell < 0) return INT_A_BREAK;
        }
    }
    g_draw_intermission(image);
    g_flip_screen(image);
    return g_check_abort(image) != 0 ? INT_A_ABORT : INT_A_CONTINUE;
}

/* Phase-B leg pick (0x27fe..0x2814): advance the attract-mode leg selector (wrap at INT_LEGS) and
 * copy it into leg_index. The init/warm-up/draw tail runs inline in g_intermission. */
void g_int_phaseB_leg(uint8_t *image) {
    uint16_t sel = (uint16_t)(rdw(image, A_leg_select) + 1);
    if ((int16_t)(sel - INT_LEGS) >= 0) sel = 0;
    wrw(image, A_leg_select, sel);
    wrw(image, A_leg_index, sel);
}

/* Phase-D counter slice (0x28b0..0x28d8 / 0x27a0): tick the per-leg dwell counter; when it elapses
 * clear it and advance to the next leg (rebuilding its dashboard), or restart the whole cycle once
 * all legs have been shown. Returns before the draw_leg_results + flip + poll tail that
 * g_intermission runs. */
int g_int_stepD_counter(uint8_t *image) {
    uint16_t dwell = (uint16_t)(rdw(image, A_int_frame_hi) + 1);
    wrw(image, A_int_frame_hi, dwell);
    if ((int16_t)(dwell - INT_D_DWELL) < 0) return INT_D_DRAW;
    wrw(image, A_int_frame_hi, 0);
    uint16_t leg = (uint16_t)(rdw(image, A_leg_index) + 1);
    wrw(image, A_leg_index, leg);
    if ((int16_t)(leg - INT_LEGS) < 0) { g_init_leg_dash(image); return INT_D_ADVANCE; }
    wrw(image, A_leg_index, 0);
    return INT_D_RESTART;
}

void g_intermission(uint8_t *image) {
    for (;;) {
        /* prologue (0x27a0): seed the animation counters, then paint two backdrop frames. */
        wrw(image, A_int_frame, INT_FRAME_INIT);
        wrw(image, A_int_timer, INT_TIMER_INIT);
        wrw(image, A_int_scroll, INT_SCROLL_INIT);
        g_fade_step(image);
        g_xbios_setpalette(image, INT_PAL_A);
        g_flip_screen(image);
        g_fade_step(image);
        g_flip_screen(image);

        /* Phase A (0x27cc): scroll the hi-score/credits screen until the dwell counter runs out. */
        for (;;) {
            int a = g_int_stepA(image);
            if (a == INT_A_ABORT) return;
            if (a == INT_A_BREAK) break;
        }

        /* Phase B (0x27fe): pick + (re)init the next demo leg, settle it, paint the first frame. */
        g_int_phaseB_leg(image);
        g_init_leg_dash(image);
        g_draw_leg_labels(image);
        g_init_leg(image);
        wrw(image, A_dsp_toggle, (uint16_t)(rdw(image, A_dsp_toggle) - 1));
        wrw(image, A_leg_flags_sel, (uint16_t)(rdw(image, A_leg_flags_sel) + 4));
        wr32(image + A_leg_flags_c90, INT_B_LEGFLAGS);
        for (int i = 0; i < INT_B_WARMUP; i++) g_game_update(image);
        g_draw_frame(image);
        g_xbios_setpalette(image, INT_PAL_B);
        g_flip_screen(image);
        g_draw_frame(image);
        g_flip_screen(image);

        /* Phase C (0x285e): play the demo for INT_C_FRAMES frames (full render each frame). The
         * clr.l zeroes the frame-counter pair (A_int_frame_hi + A_int_frame); the loop ticks the
         * low word. */
        wr32(image + A_int_frame_hi, 0);
        for (;;) {
            g_game_update(image);
            g_render_road(image);
            g_blit_road_scroll(image);
            g_draw_game_objects(image);
            g_draw_hud(image);
            g_flip_screen(image);
            uint16_t f = (uint16_t)(rdw(image, A_int_frame) + 1);
            wrw(image, A_int_frame, f);
            if ((int16_t)(f - INT_C_FRAMES) >= 0) break;
            if (g_check_abort(image) != 0) return;
        }

        /* Phase D (0x2894): results carousel — cycle draw_leg_results across the legs. */
        wrw(image, A_leg_index, 0);
        g_init_leg_dash(image);
        g_draw_leg_results(image);
        g_xbios_setpalette(image, INT_PAL_D);
        g_flip_screen(image);
        for (;;) {
            if (g_int_stepD_counter(image) == INT_D_RESTART) break;   /* -> back to the prologue */
            g_draw_leg_results(image);
            g_flip_screen(image);
            if (g_check_abort(image) != 0) return;
        }
    }
}


