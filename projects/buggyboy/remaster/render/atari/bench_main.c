/* bench_main.c — per-function entry points for cycle-benchmarking the remaster render cores on a
 * 68000 (Musashi), against recreate's cross-compiled recon. Each bench_* symbol is a zero-work
 * wrapper that calls one core with structs staged from the baked demo fixture; tools/bench.py loads
 * this ELF, jumps to each wrapper via emu.run_bench, and counts instructions/cycles. Not a program
 * (no real main loop): main() exists only so os.s links.
 */
#include <stdint.h>
#include <string.h>          /* freestanding libc, defined in shim.c */

#include "assets.h"
#include "game.h"
#include "screen.h"
#include "demo_fixture.h"

void rm_build_road_geometry(RoadPose *pose, const RoadSource *src, const CourseRing *ring,
                            uint8_t *ctrl, uint8_t *scanline);
void rm_render_road(const RoadInput *in, Framebuffer *fb);
void rm_scroll_prebuild(const uint8_t *playfield, uint8_t *shifted);
void rm_blit_road_scroll(ScrollState *s, const uint8_t *shifted, Framebuffer *fb);
void rm_road_course_advance(RoadPose *pose, CourseState *cs, CourseRing *ring,
                            const uint8_t *stream);
void rm_draw_hud(const HudState *s, const HudAssets *a, Framebuffer *fb);

#define BENCH_SCROLL_SPEED 0x20     /* a representative racing speed (exercises the scroll edge/wrap tail) */

static Framebuffer fb __attribute__((aligned(2)));
static uint8_t ctrl[RM_CTRL_BYTES] __attribute__((aligned(2)));
static uint8_t scanline[RM_SCANLINE_BYTES] __attribute__((aligned(2)));
static uint8_t shifted[RM_SCROLL_SHIFTS * RM_SCROLL_WINDOW] __attribute__((aligned(2)));

static const HudState hud = {
    .flag_seq_count = HUD_FLAG_SEQ_COUNT, .flag_seq_off = HUD_FLAG_SEQ_OFF,
    .dsp_color_scroll = HUD_DSP_COLOR_SCROLL, .crash_lap = HUD_CRASH_LAP,
    .speed = HUD_SPEED, .time_left = HUD_TIME_LEFT, .game_over = HUD_GAME_OVER,
    .dsp_toggle = HUD_DSP_TOGGLE, .dsp_variant_idx = HUD_DSP_VARIANT_IDX,
    .gauge_blink = HUD_GAUGE_BLINK, .gauge_blink_on = HUD_GAUGE_BLINK_ON,
    .crash_active = HUD_CRASH_ACTIVE, .crash_frame = HUD_CRASH_FRAME,
    .crash_bars = HUD_CRASH_BARS, .hud_crash_timer = HUD_CRASH_TIMER,
};
/* The asset arena. There is no filesystem under Musashi, so bench.py writes the already-loaded and
 * unpacked arena bytes straight into `arena_block` and then calls bench_stage_assets, which is what
 * binds the arena-resident pointers below. Keeping that out of the wrappers is what lets them stay
 * zero-work — the staging cost must not land in the measured call. */
static uint8_t arena_block[RM_ARENA_BYTES] __attribute__((aligned(2)));

static HudAssets assets = {
    .color_pairs = fixture_color_pairs, .color_bar_mask = fixture_color_bar_mask,
    .color_bar_cidx = fixture_color_bar_cidx + CIDX_ZERO_OFF, .fuel_mask = fixture_fuel_mask,
    .font = fixture_font, .hud_text = fixture_hud_text, .dsp_table = fixture_dsp_table,
    .small_gauge_str = fixture_small_gauge_str,
    .num_glyph_tbl = fixture_num_glyph_tbl, .crash_color_tbl = fixture_crash_color_tbl,
    .score_delta_time = fixture_score_delta_time, .score_delta_roll = fixture_score_delta_roll,
};
static const RoadSource src = {
    .persp_seg = (const int8_t *)fixture_road_persp_seg,
    .width_count = fixture_road_width_count,
};
/* The per-band road widths the builder reads: live course state, advanced by bench_course_advance. */
static CourseRing ring = COURSE_RING_INIT;
static RoadInput road = {
    .width_tbl = ctrl + RM_CTRL_WIDTH_OFF, .param = fixture_road_param,
    .edge_tbl = fixture_road_edge + ROAD_EDGE_PAD, .edge_const = fixture_road_edge_const,
};
static const uint8_t *course_stream;
static RoadPose pose = {.curve = ROAD_CURVE_INIT, .view_flags = ROAD_VIEW_FLAGS_INIT,
                        .seg_data = ROAD_SEG_DATA_INIT};
static ScrollState scroll = {.scroll_speed = BENCH_SCROLL_SPEED, .hscroll_pos = HSCROLL_POS_INIT};
static CourseState course = {.row_ctr = COURSE_ROW_CTR_INIT, .read_pos = COURSE_READ_POS_INIT};

/* Bind everything that lives in the loaded asset arena. bench.py runs this before every measured
 * call, on memory it has already filled with the unpacked arena. */
static const uint8_t *scroll_playfield;
void bench_stage_assets(void) {
    RmArena arena;
    rm_arena_init(&arena, arena_block);
    assets.dashboard_src = arena.gfx + ARENA_DASH_SRC_OFF;
    assets.dsp_src = arena.gfx;              /* dsp_table's offsets are absolute within the arena */
    assets.num_sprites = arena.gfx + ARENA_NUM_SPRITES_OFF;
    road.tex = arena.scratch;
    scroll_playfield = arena.gfx + ARENA_SCROLL_PLAY_OFF;
    course_stream = arena.tables + ARENA_COURSE_STREAM_OFF;
}

/* One representative frame's worth of each core (as the demo's draw_frame chains them). */
void bench_build_geometry(void) { rm_build_road_geometry(&pose, &src, &ring, ctrl, scanline); }
void bench_render_road(void)    { road.width_tbl = ctrl + RM_CTRL_WIDTH_OFF; rm_render_road(&road, &fb); }
void bench_scroll_prebuild(void) { rm_scroll_prebuild(scroll_playfield, shifted); }
void bench_blit_scroll(void)    { rm_blit_road_scroll(&scroll, shifted, &fb); }
void bench_draw_hud(void)       { rm_draw_hud(&hud, &assets, &fb); }
void bench_course_advance(void) { rm_road_course_advance(&pose, &course, &ring, course_stream); }

int main(void) { return 0; }        /* unused; present so os.s's `jsr main` links */
