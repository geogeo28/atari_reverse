/* bench_main.c — per-function entry points for cycle-benchmarking the remaster render cores on a
 * 68000 (Musashi), against recreate's cross-compiled recon. Each bench_* symbol is a zero-work
 * wrapper that calls one core with structs staged from the baked demo fixture; tools/bench.py loads
 * this ELF, jumps to each wrapper via emu.run_bench, and counts instructions/cycles. Not a program
 * (no real main loop): main() exists only so os.s links.
 */
#include <stdint.h>

#include "game.h"
#include "screen.h"
#include "demo_fixture.h"

void rm_build_road_geometry(RoadPose *pose, const RoadSource *src, uint8_t *ctrl, uint8_t *scanline);
void rm_render_road(const RoadInput *in, Framebuffer *fb);
void rm_blit_road_scroll(ScrollState *s, const uint8_t *playfield, Framebuffer *fb);
void rm_road_course_advance(RoadPose *pose, CourseState *cs, const uint8_t *stream);
void rm_draw_hud(const HudState *s, const HudAssets *a, Framebuffer *fb);

#define BENCH_SCROLL_SPEED 0x20     /* a representative racing speed (exercises the scroll edge/wrap tail) */

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

static Framebuffer fb __attribute__((aligned(2)));
static uint8_t ctrl[RM_CTRL_BYTES] __attribute__((aligned(2)));
static uint8_t scanline[RM_SCANLINE_BYTES] __attribute__((aligned(2)));

static const HudState hud = {
    .flag_seq_count = HUD_FLAG_SEQ_COUNT, .flag_seq_off = HUD_FLAG_SEQ_OFF,
    .dsp_color_scroll = HUD_DSP_COLOR_SCROLL, .crash_lap = HUD_CRASH_LAP,
    .speed = HUD_SPEED, .time_left = HUD_TIME_LEFT, .game_over = HUD_GAME_OVER,
    .dsp_toggle = HUD_DSP_TOGGLE, .dsp_variant_idx = HUD_DSP_VARIANT_IDX,
    .gauge_blink = HUD_GAUGE_BLINK, .gauge_blink_on = HUD_GAUGE_BLINK_ON,
    .crash_active = HUD_CRASH_ACTIVE, .crash_frame = HUD_CRASH_FRAME,
    .crash_bars = HUD_CRASH_BARS, .hud_crash_timer = HUD_CRASH_TIMER,
};
static const HudAssets assets = {
    .color_pairs = fixture_color_pairs, .color_bar_mask = fixture_color_bar_mask,
    .color_bar_cidx = fixture_color_bar_cidx + CIDX_ZERO_OFF, .fuel_mask = fixture_fuel_mask,
    .font = fixture_font, .hud_text = fixture_hud_text, .dashboard_src = fixture_dashboard_src,
    .dsp_table = fixture_dsp_table, .dsp_src = fixture_dsp_src,
    .small_gauge_str = fixture_small_gauge_str, .num_sprites = fixture_num_sprites,
    .num_glyph_tbl = fixture_num_glyph_tbl, .crash_color_tbl = fixture_crash_color_tbl,
    .score_delta_time = fixture_score_delta_time, .score_delta_roll = fixture_score_delta_roll,
};
static const RoadSource src = {
    .persp_seg = (const int8_t *)fixture_road_persp_seg,
    .width_src = fixture_road_width_src, .width_count = fixture_road_width_count,
};
static RoadInput road = {
    .width_tbl = ctrl + RM_CTRL_WIDTH_OFF, .param = fixture_road_param,
    .edge_tbl = fixture_road_edge + ROAD_EDGE_PAD, .tex = fixture_road_tex + ROAD_TEX_PAD_LO,
    .edge_const = fixture_road_edge_const,
};
static RoadPose pose = {.curve = ROAD_CURVE_INIT, .view_flags = ROAD_VIEW_FLAGS_INIT,
                        .seg_data = ROAD_SEG_DATA_INIT};
static ScrollState scroll = {.scroll_speed = BENCH_SCROLL_SPEED, .hscroll_pos = HSCROLL_POS_INIT};
static CourseState course = {.row_ctr = COURSE_ROW_CTR_INIT, .read_pos = COURSE_READ_POS_INIT};

/* One representative frame's worth of each core (as the demo's draw_frame chains them). */
void bench_build_geometry(void) { rm_build_road_geometry(&pose, &src, ctrl, scanline); }
void bench_render_road(void)    { road.width_tbl = ctrl + RM_CTRL_WIDTH_OFF; rm_render_road(&road, &fb); }
void bench_blit_scroll(void)    { rm_blit_road_scroll(&scroll, fixture_road_play, &fb); }
void bench_draw_hud(void)       { rm_draw_hud(&hud, &assets, &fb); }
void bench_course_advance(void) { rm_road_course_advance(&pose, &course, fixture_course_stream + COURSE_STREAM_PAD); }

int main(void) { return 0; }        /* unused; present so os.s's `jsr main` links */
