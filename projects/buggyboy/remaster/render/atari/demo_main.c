/* demo_main.c — interactive road + HUD demo: remaster's own pipeline on a real 68000, steered live.
 *
 * Each frame runs rm_build_road_geometry (from the current pose) -> rm_render_road -> rm_draw_hud,
 * then blits to the screen. Arrow keys nudge the pose and redraw:
 *   Left / Right : road curvature (steer the road left/right)
 *   Up / Down    : near-slope (crest / dip the road ahead)
 *   Space        : cycle the view bank (0, 2, 4, 6)
 *   R            : reset the pose;   Esc / Q : quit
 * The first frame (before any key) is dumped to C:\SCREEN.BIN so a headless run can byte-compare it
 * to recreate's g_build_road_geometry + g_render_road + g_draw_hud on the same pose (build/golden.bin).
 * All inputs are baked by gen_demo_fixture.py; only what remaster's C implements is drawn. See README.
 */
#include <stdint.h>

#include "game.h"
#include "screen.h"
#include "demo_fixture.h"

void rm_build_road_geometry(RoadPose *pose, const RoadSource *src, uint8_t *ctrl, uint8_t *scanline);
void rm_render_road(const RoadInput *in, Framebuffer *fb);
void rm_draw_hud(const HudState *s, const HudAssets *a, Framebuffer *fb);

extern long Fcreate(const char *name, short attr);
extern long Fwrite(short handle, long count, void *buf);
extern long Fclose(short handle);
extern long Cconin(void);
extern long Physbase(void);
extern void Setpalette(const void *pal16);

/* freestanding libc the cores need (we link -nostdlib) */
void *memset(void *d, int c, unsigned long n) {
    uint8_t *dp = d;
    while (n--) *dp++ = (uint8_t)c;
    return d;
}
void *memcpy(void *d, const void *s, unsigned long n) {
    uint8_t *dp = d; const uint8_t *sp = s;
    while (n--) *dp++ = *sp++;
    return d;
}

/* Keyboard scancodes (Cconin returns the scancode in bits 16..23, the ASCII char in the low byte). */
#define SCAN_UP 0x48
#define SCAN_DOWN 0x50
#define SCAN_LEFT 0x4b
#define SCAN_RIGHT 0x4d
#define KEY_ESC 0x1b
#define CURVE_STEP 0x0200            /* road_curve nudge per Left/Right press */
#define SLOPE_STEP 2                 /* near-slope nudge per Up/Down press */
#define VIEW_BANK_WRAP 8             /* view_flags cycles 0,2,4,6 (mod 8) */

static Framebuffer fb __attribute__((aligned(2)));                       /* BSS: the 32000-byte draw buffer */
static uint8_t ctrl[RM_CTRL_BYTES] __attribute__((aligned(2)));          /* BSS: per-frame control-long table */
static uint8_t scanline[RM_SCANLINE_BYTES] __attribute__((aligned(2)));  /* BSS: build_road_geometry scratch */

static const int16_t seg_data_init[13] = ROAD_SEG_DATA_INIT;

/* Build this frame's geometry from `pose`, render road + HUD into fb, and blit to the screen. */
static void draw_frame(RoadPose *pose, const RoadSource *src, RoadInput *road,
                       const HudState *hud, const HudAssets *assets) {
    rm_build_road_geometry(pose, src, ctrl, scanline);
    road->width_tbl = ctrl + RM_CTRL_WIDTH_OFF;
    memset(fb.px, 0, SCREEN_BYTES);          /* blank frame, then draw only remaster's own pipeline */
    rm_render_road(road, &fb);
    rm_draw_hud(hud, assets, &fb);
    memcpy((void *)Physbase(), fb.px, SCREEN_BYTES);
}

void main(void) {
    static const HudState hud = {
        .flag_seq_count = HUD_FLAG_SEQ_COUNT, .flag_seq_off = HUD_FLAG_SEQ_OFF,
        .dsp_color_scroll = HUD_DSP_COLOR_SCROLL, .crash_lap = HUD_CRASH_LAP,
        .speed = HUD_SPEED, .time_left = HUD_TIME_LEFT, .game_over = HUD_GAME_OVER,
        .dsp_toggle = HUD_DSP_TOGGLE, .dsp_variant_idx = HUD_DSP_VARIANT_IDX,
        .gauge_blink = HUD_GAUGE_BLINK, .gauge_blink_on = HUD_GAUGE_BLINK_ON,
        .crash_active = HUD_CRASH_ACTIVE, .crash_frame = HUD_CRASH_FRAME,
        .crash_bars = HUD_CRASH_BARS, .hud_crash_timer = HUD_CRASH_TIMER,
    };
    const HudAssets assets = {
        .color_pairs = fixture_color_pairs, .color_bar_mask = fixture_color_bar_mask,
        .color_bar_cidx = fixture_color_bar_cidx + CIDX_ZERO_OFF, .fuel_mask = fixture_fuel_mask,
        .font = fixture_font, .hud_text = fixture_hud_text, .dashboard_src = fixture_dashboard_src,
        .dsp_table = fixture_dsp_table, .dsp_src = fixture_dsp_src,
        .small_gauge_str = fixture_small_gauge_str, .num_sprites = fixture_num_sprites,
        .num_glyph_tbl = fixture_num_glyph_tbl, .crash_color_tbl = fixture_crash_color_tbl,
        .score_delta_time = fixture_score_delta_time, .score_delta_roll = fixture_score_delta_roll,
    };
    const RoadSource src = {
        .persp_seg = (const int8_t *)fixture_road_persp_seg,
        .width_src = fixture_road_width_src, .width_count = fixture_road_width_count,
    };
    RoadInput road = {
        .width_tbl = ctrl + RM_CTRL_WIDTH_OFF,   /* rebound per frame after the build */
        .param = fixture_road_param, .edge_tbl = fixture_road_edge + ROAD_EDGE_PAD,
        .tex = fixture_road_tex + ROAD_TEX_PAD_LO, .edge_const = fixture_road_edge_const,
    };
    RoadPose pose = {.curve = ROAD_CURVE_INIT, .view_flags = ROAD_VIEW_FLAGS_INIT};
    for (int i = 0; i < 13; i++) pose.seg_data[i] = seg_data_init[i];

    Setpalette(fixture_palette);
    draw_frame(&pose, &src, &road, &hud, &assets);

    /* Dump the first frame so a headless run can byte-compare it to golden.bin. */
    long h = Fcreate("SCREEN.BIN", 0);
    if (h >= 0) { Fwrite((short)h, SCREEN_BYTES, fb.px); Fclose((short)h); }

    for (;;) {
        long k = Cconin();
        int scan = (int)((k >> 16) & 0xff), ascii = (int)(k & 0xff);
        if (ascii == KEY_ESC || ascii == 'q' || ascii == 'Q') break;
        switch (scan) {
            case SCAN_LEFT:  pose.curve = (int16_t)(pose.curve - CURVE_STEP); break;
            case SCAN_RIGHT: pose.curve = (int16_t)(pose.curve + CURVE_STEP); break;
            case SCAN_UP:    pose.seg_data[0] = (int16_t)(pose.seg_data[0] + SLOPE_STEP); break;
            case SCAN_DOWN:  pose.seg_data[0] = (int16_t)(pose.seg_data[0] - SLOPE_STEP); break;
            default:
                if (ascii == ' ') pose.view_flags = (uint16_t)((pose.view_flags + 2) % VIEW_BANK_WRAP);
                else if (ascii == 'r' || ascii == 'R') {
                    pose.curve = ROAD_CURVE_INIT; pose.view_flags = ROAD_VIEW_FLAGS_INIT;
                    for (int i = 0; i < 13; i++) pose.seg_data[i] = seg_data_init[i];
                }
                break;
        }
        draw_frame(&pose, &src, &road, &hud, &assets);
    }
}
