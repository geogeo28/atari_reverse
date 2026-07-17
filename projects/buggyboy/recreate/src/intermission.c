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


/* --- init_playfield @ 0x12af6 --- The leg-select / playfield-init loop. It shows the leg-results
 * screen and lets the player pick a leg with the joystick (up/left = previous leg, down/right =
 * next, each gated by an auto-repeat delay) and start it with fire. Idling past the countdown at
 * A_idle_countdown runs one intermission (attract-demo) cycle and restarts. The loop returns only
 * when a leg is started: it announces the start tune, redraws, then runs a 121-frame palette-flash
 * "get ready" animation and falls through to the caller (which begins the race).
 *
 * Function-key debug menu (0x2b24..0x2bfc) — read-verified, UNREACHABLE under the harness: it polls
 * the GEMDOS console (Crawio, fn 6), which the deterministic OS model reports as no key pending
 * (OS_CRAWIO_RESULT = 0), so every frame the key is 0 and control always falls to the default
 * redraw (0x2b9e) and then the joystick tail. The menu the disassembly shows (never entered here):
 *   scancode 0x44 then RETURN (0xd) -> reload GRAPHICS.GRA + rebuild the score table
 *                                      (xbios_setscreen, load_graphics, init_leg_dash, init_scoretable);
 *   F1..F5 (scancodes 0x3b..0x3f)   -> select that leg (leg_index = key - 0x3b) and start it;
 *   F6 (scancode 0x40)              -> show the race-end results screen (draw_results_screen), then
 *                                      busy-wait for F6-release and a fresh keypress before redrawing.
 * See STATUS.md / HARNESS.md for why the console path is verified by reading, not execution. */
#define IP_IDLE_INIT      0x15e   /* A_idle_countdown reload on input change; expiry -> intermission */
#define IP_SEL_REPEAT     3       /* auto-repeat delay reloaded after a leg step */
#define IP_LEG_COUNT      5       /* legs 0..4 */
#define IP_INPUT_FIRE     0x80    /* input_state fire bit */
#define IP_DEC_BITS       (1 | 4) /* up | left  -> previous leg */
#define IP_INC_BITS       (2 | 8) /* down | right -> next leg */
/* Function-key menu (0x2b24..0x2bfc): IKBD scancodes read from the GEMDOS console. */
#define IP_KEY_F1         0x3b    /* F1..F5 = 0x3b..0x3f: select leg (scancode - F1); F6 = 0x40 */
#define IP_KEY_F6_INDEX   5       /* (scancode - F1) that means F6 (results-screen preview) */
#define IP_KEY_F6_SCAN    0x40    /* F6 raw scancode (IP_KEY_F1 + IP_KEY_F6_INDEX) */
#define IP_KEY_F10        0x44    /* F10: reload GRAPHICS.GRA + rebuild score table (after RETURN) */
#define IP_KEY_RETURN     0x0d    /* confirms the F10 reload */
#define IP_FLASH_FRAMES   0x78    /* dbf count: the flash runs IP_FLASH_FRAMES + 1 = 121 frames */
/* IP_FLASH_TBL_* index scales (mask, then >>1 for the word tables to keep the index word-aligned;
 * the long table indexes by the raw masked value). */
#define IP_FLASH_MASK_A   0x0c
#define IP_FLASH_MASK_BC  0x1c
#define IP_FLASH_MASK_D   0x06
/* Palette-entry byte offsets into A_leg_start_pal the flash animates each frame. */
#define IP_PAL_OFF_A      0x1c
#define IP_PAL_OFF_B0     0x08
#define IP_PAL_OFF_B1     0x1e
#define IP_PAL_OFF_C      0x0c
#define IP_PAL_OFF_D0     0x12
#define IP_PAL_OFF_D1     0x16

/* Leg-select navigation (0x2c1c..0x2c68): tick both auto-repeat delays; when a delay expires (goes
 * negative) and its direction is held, step leg_index one slot (clamped to 0..IP_LEG_COUNT-1),
 * reload that direction's delay and clear the other. Both delays are decremented every frame, so a
 * step that clears the opposite delay lets the opposite direction fire the same frame if held —
 * mirroring the in-place 68k (subq/addq on the leg word, subq on each delay). */
static void ip_nav_step(uint8_t *image) {
    uint16_t input = rdw(image, A_input_state);
    int16_t leg = (int16_t)rdw(image, A_leg_index);

    int16_t dec_delay = (int16_t)(rdw(image, A_leg_dec_delay) - 1);
    wrw(image, A_leg_dec_delay, (uint16_t)dec_delay);
    if (dec_delay < 0 && (input & IP_DEC_BITS) && leg - 1 >= 0) {
        leg -= 1;
        wrw(image, A_leg_dec_delay, IP_SEL_REPEAT);
        wrw(image, A_leg_inc_delay, 0);
    }
    int16_t inc_delay = (int16_t)(rdw(image, A_leg_inc_delay) - 1);
    wrw(image, A_leg_inc_delay, (uint16_t)inc_delay);
    if (inc_delay < 0 && (input & IP_INC_BITS) && leg + 1 < IP_LEG_COUNT) {
        leg += 1;
        wrw(image, A_leg_inc_delay, IP_SEL_REPEAT);
        wrw(image, A_leg_dec_delay, 0);
    }
    wrw(image, A_leg_index, (uint16_t)leg);
}

/* Fire edge (0x2c6c): start only on a fresh fire press — fire bit clear in the previous snapshot
 * (A_input_prev) but set in the current input_state. Exposed for the differential harness (the
 * decision is diffed by entering the oracle at 0x2c6c and checkpointing at the branch target). */
int g_init_playfield_fire(uint8_t *image) {
    return !(rdw(image, A_input_prev) & IP_INPUT_FIRE) && (rdw(image, A_input_state) & IP_INPUT_FIRE);
}

/* Leg-start "get ready" (0x2c96): announce the start tune, redraw the leg screen twice, draw the
 * dashboard labels, then flash six entries of A_leg_start_pal for IP_FLASH_FRAMES + 1 frames (two
 * XBIOS Vsyncs per frame -> hardware-only, no image effect). Falls through to the caller to race. */
static void ip_start_leg(uint8_t *image) {
    g_play_event_tune(image, 0);
    g_init_leg_dash(image);
    g_draw_leg_results(image);
    g_draw_panel5(image);
    g_flip_screen(image);
    g_draw_leg_results(image);
    g_draw_panel5(image);
    g_flip_screen(image);
    g_draw_leg_labels(image);

    for (int n = IP_FLASH_FRAMES; n >= 0; n--) {
        uint16_t counter = (uint16_t)(rdw(image, A_anim_counter) + 1);
        wrw(image, A_anim_counter, counter);

        uint16_t ia = (uint16_t)((counter & IP_FLASH_MASK_A) >> 1);
        uint16_t ibc = (uint16_t)((counter & IP_FLASH_MASK_BC) >> 1);
        uint16_t id = (uint16_t)(counter & IP_FLASH_MASK_D);
        wrw(image, A_leg_start_pal + IP_PAL_OFF_A,  rdw(image, A_leg_flash_tbl_a + ia));
        wrw(image, A_leg_start_pal + IP_PAL_OFF_B0, rdw(image, A_leg_flash_tbl_b + ibc));
        wrw(image, A_leg_start_pal + IP_PAL_OFF_B1, rdw(image, A_leg_flash_tbl_b + ibc));
        wrw(image, A_leg_start_pal + IP_PAL_OFF_C,  rdw(image, A_leg_flash_tbl_c + ibc));
        wr32(image + A_leg_start_pal + IP_PAL_OFF_D0, be32(image + A_leg_flash_tbl_d + id));
        wr32(image + A_leg_start_pal + IP_PAL_OFF_D1, be32(image + A_leg_flash_tbl_d + 4 + id));
        g_xbios_setpalette(image, A_leg_start_pal);
    }
}

/* Joystick-navigation slice (0x2c00 tail up to the idle-countdown dbf): poll the joystick, reload
 * the idle countdown on any input change, then run one nav step. Exposed for the differential
 * harness (the loop never returns except on a leg start, so navigation is diffed by entering the
 * oracle at 0x2c00 and checkpointing at the dbf). Shared with g_init_playfield below. */
void g_init_playfield_nav(uint8_t *image) {
    g_read_joystick(image);
    if (rdw(image, A_input_state) != rdw(image, A_input_prev))
        wrw(image, A_idle_countdown, IP_IDLE_INIT);
    ip_nav_step(image);
}

/* Function-key debug menu (0x2b24..0x2bfc): poll the GEMDOS console once and act on it. Under the
 * deterministic no-key OS model (g_console_scancode -> 0) this always falls straight through to the
 * default redraw, so the differential test is unaffected; on real hardware (the Atari PRG overrides
 * the console seam) it drives leg-select.
 *   F10 (0x44) then RETURN -> reload GRAPHICS.GRA + rebuild the score table
 *   F1..F5 (0x3b..0x3f)    -> select that leg (leg_index = scancode - F1) and start it
 *   F6 (0x40)              -> preview the results screen until a fresh key, then redraw leg-select */
typedef enum {
    IP_MENU_REDRAW,     /* no menu action (or F10-reload/out-of-range) -> default redraw (0x2b9e) */
    IP_MENU_START,      /* F1..F5 -> caller starts the selected leg (0x2c96) */
    IP_MENU_NAV,        /* F6 preview did its own redraw -> skip straight to the nav tail (0x2c00) */
} ip_menu_result;

static ip_menu_result ip_menu(uint8_t *image) {
    int16_t key = (int16_t)g_console_scancode(image);      /* 0x2b24: Crawio(0xff) scancode, 0 if none */

    if (key == IP_KEY_F10) {                               /* 0x2b36: F10 -> graphics/score reload */
        g_draw_leg_results(image);
        g_draw_panel3(image);
        g_flip_screen(image);
        key = (int16_t)g_console_wait_char(image);         /* 0x2b48: Crawcin (fn 7), blocking */
        if (key == IP_KEY_RETURN) {                        /* 0x2b50: confirmed */
            g_draw_leg_results(image);
            g_draw_panel2(image);
            g_flip_screen(image);
            g_draw_leg_results(image);
            g_draw_panel2(image);
            g_xbios_setscreen(image);
            g_load_graphics(image);
            g_init_leg_dash(image);
            g_init_scoretable(image);
            return IP_MENU_REDRAW;                         /* 0x2b7a -> default redraw */
        }
        /* not RETURN: fall through to the F-key test with key = the char just read (0x2b7c) */
    }

    int16_t sel = (int16_t)(key - IP_KEY_F1);              /* 0x2b7c: scancode relative to F1 */
    if (sel < 0) return IP_MENU_REDRAW;                    /* 0x2b80: below F1 -> default redraw */
    if (sel == IP_KEY_F6_INDEX) {                          /* 0x2b86: F6 -> results-screen preview */
        wrw(image, A_results_mode, 0);                     /* 0x2bac */
        g_draw_results_screen(image);
        g_xbios_setpalette(image, A_results_screen_pal);
        g_flip_screen(image);
        while (g_console_scancode(image) == IP_KEY_F6_SCAN) { }   /* 0x2bc4: wait for F6 release */
        while (g_console_scancode(image) == 0) { }         /* 0x2bd8: wait for any fresh key */
        g_draw_leg_results(image);
        g_draw_panel5(image);
        g_xbios_setpalette(image, A_leg_select_pal);
        g_flip_screen(image);
        return IP_MENU_NAV;                                /* 0x2bfc -> nav tail (skips default redraw) */
    }
    if (sel > IP_KEY_F6_INDEX) return IP_MENU_REDRAW;      /* 0x2b88: above F6 -> default redraw */

    wrw(image, A_leg_index, (uint16_t)sel);               /* 0x2b8a: F1..F5 -> select leg 0..4 */
    wrw(image, A_timeout_gate, 0);                        /* 0x2b90 */
    return IP_MENU_START;                                 /* 0x2b9a -> start the leg */
}

void g_init_playfield(uint8_t *image) {
    for (;;) {                                              /* outer loop (0x2af6) */
        wrw(image, A_timeout_gate, 0);
        g_init_leg_dash(image);
        g_draw_leg_results(image);
        g_draw_panel5(image);
        g_xbios_setpalette(image, A_leg_select_pal);
        g_flip_screen(image);

        uint16_t idle = IP_IDLE_INIT;
        for (;;) {                                          /* per-frame loop (0x2b1a) */
            wrw(image, A_idle_countdown, idle);
            g_init_leg_dash(image);

            ip_menu_result menu = ip_menu(image);           /* function-key menu (0x2b24) */
            if (menu == IP_MENU_START) { ip_start_leg(image); return; }
            if (menu != IP_MENU_NAV) {                       /* F6 preview already redrew (0x2bfc) */
                g_draw_leg_results(image);                   /* default redraw (0x2b9e) */
                g_draw_panel5(image);
                g_flip_screen(image);
            }

            g_init_playfield_nav(image);                    /* joystick tail (0x2c00) */
            if (g_init_playfield_fire(image)) { ip_start_leg(image); return; }

            int16_t next = (int16_t)(rdw(image, A_idle_countdown) - 1);   /* dbf (0x2c78) */
            if (next == -1) break;                          /* countdown expired (dbf falls through) */
            idle = (uint16_t)next;
        }
        wrw(image, A_game_over_flag, (uint16_t)(rdw(image, A_game_over_flag) + 1));
        g_intermission(image);
        wrw(image, A_game_over_flag, 0);
    }
}


