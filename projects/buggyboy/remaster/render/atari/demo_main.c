/* demo_main.c — interactive road + HUD demo: remaster's own pipeline on a real 68000, steered live.
 *
 * Each frame runs rm_build_road_geometry (from the current pose) -> rm_render_road ->
 * rm_blit_road_scroll (the scrolling near-road band + sky) -> rm_draw_hud, then blits to the screen.
 * The demo auto-runs (paced by the vertical blank) with non-blocking input, so it drives itself:
 *   Up / Down    : throttle up / brake (speed scrolls the road and advances the leg's course)
 *   Left / Right : steer (road curvature; self-centres when released)
 *   Space        : cycle the view bank (0, 2, 4, 6)
 *   R            : reset the pose + course position;   Esc / Q : quit
 * The first frame (speed 0, before any input) is dumped to C:\SCREEN.BIN so a headless run can
 * byte-compare it to recreate's g_build_road_geometry + g_render_road + g_blit_road_scroll +
 * g_draw_hud (build/golden.bin).
 * All inputs are baked by gen_demo_fixture.py; only what remaster's C implements is drawn. See README.
 */
#include <stdint.h>

#include "game.h"
#include "screen.h"
#include "demo_fixture.h"

void rm_build_road_geometry(RoadPose *pose, const RoadSource *src, uint8_t *ctrl, uint8_t *scanline);
void rm_render_road(const RoadInput *in, Framebuffer *fb);
void rm_scroll_prebuild(const uint8_t *playfield, uint8_t *shifted);
void rm_blit_road_scroll(ScrollState *s, const uint8_t *shifted, Framebuffer *fb);
void rm_road_course_advance(RoadPose *pose, CourseState *cs, const uint8_t *stream);
void rm_draw_hud(const HudState *s, const HudAssets *a, Framebuffer *fb);

extern long Fcreate(const char *name, short attr);
extern long Fwrite(short handle, long count, void *buf);
extern long Fclose(short handle);
extern long Cconin(void);
extern long Cconis(void);        /* non-blocking: -1 if a key is waiting */
extern void Vsync(void);
extern long Setscreen(long logLoc, long physLoc, short rez);   /* flip the video base (latches at vblank) */
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
#define VIEW_BANK_WRAP 8             /* view_flags cycles 0,2,4,6 (mod 8) */

/* Driving feel. speed 0..SPEED_MAX; it both scrolls the road band (blit_road_scroll's scroll_speed)
 * and, via a distance accumulator, advances the course one segment per DIST_PER_SEG units. Steering
 * adds CURVE_STEP per press up to CURVE_MAX and self-centres by CURVE_DECAY each frame. */
#define SPEED_STEP     2
#define SPEED_MAX      0x20
#define DIST_PER_SEG   0x18          /* smaller = the course (road bends) advances faster per speed */
#define CURVE_STEP     0x60
#define CURVE_MAX      0x1800
#define CURVE_DECAY    0x30

static uint8_t ctrl[RM_CTRL_BYTES] __attribute__((aligned(2)));          /* BSS: per-frame control-long table */
static uint8_t scanline[RM_SCANLINE_BYTES] __attribute__((aligned(2)));  /* BSS: build_road_geometry scratch */
static uint8_t shifted[RM_SCROLL_SHIFTS * RM_SCROLL_WINDOW] __attribute__((aligned(2)));  /* pre-rotated scroll copies */

/* Two screen buffers, 256-byte aligned at RUNTIME (the ST video base only uses the high/mid address
 * bytes, so a non-256-aligned base is rounded down → the image shifts). The link-time alignment isn't
 * enough because the GEMDOS load base needn't be 256-aligned, so over-allocate and round the pointer.
 * We render into the off-screen buffer and flip the video base to it at the vblank — a single-buffer
 * blit to the live screen tears badly at this render rate. SCREEN_BYTES is a multiple of 256, so the
 * second buffer stays aligned too. */
#define SCREEN_ALIGN 256
static uint8_t screen_pool[2 * SCREEN_BYTES + SCREEN_ALIGN];

static Framebuffer *screen_buf(int i) {
    unsigned long base = ((unsigned long)screen_pool + (SCREEN_ALIGN - 1)) & ~(unsigned long)(SCREEN_ALIGN - 1);
    return (Framebuffer *)(base + (unsigned long)i * SCREEN_BYTES);
}

static const int16_t seg_data_init[13] = ROAD_SEG_DATA_INIT;

/* Build this frame's geometry from `pose`, then render road + scroll band + HUD into `fb`. The scroll
 * advances every frame (hscroll_pos persists in `scroll`) using the pre-rotated copies in `shifted`
 * (built once), so the road band slides each redraw. */
static void draw_frame(Framebuffer *fb, RoadPose *pose, const RoadSource *src, RoadInput *road,
                       ScrollState *scroll, const HudState *hud, const HudAssets *assets) {
    rm_build_road_geometry(pose, src, ctrl, scanline);
    road->width_tbl = ctrl + RM_CTRL_WIDTH_OFF;
    scroll->seg_head = pose->seg_head;           /* the scroll step follows the near slope */
    memset(fb->px, 0, SCREEN_BYTES);             /* blank frame, then draw only remaster's own pipeline */
    rm_render_road(road, fb);
    rm_blit_road_scroll(scroll, shifted, fb);
    rm_draw_hud(hud, assets, fb);
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
    ScrollState scroll = {.scroll_speed = SCROLL_SPEED_INIT, .hscroll_pos = HSCROLL_POS_INIT};
    CourseState course = {.row_ctr = COURSE_ROW_CTR_INIT, .read_pos = COURSE_READ_POS_INIT};
    const uint8_t *stream = fixture_course_stream + COURSE_STREAM_PAD;   /* records lie below the base */

    Setpalette(fixture_palette);
    rm_scroll_prebuild(fixture_road_play, shifted);   /* pre-rotate the playfield once (screen_offset is fixed) */
    int shown = 0;
    draw_frame(screen_buf(shown), &pose, &src, &road, &scroll, &hud, &assets);
    Setscreen(-1L, (long)screen_buf(shown)->px, -1);   /* show the first frame */
    Vsync();

    /* Dump the first frame (speed 0) so a headless run can byte-compare it to golden.bin. */
    long h = Fcreate("SCREEN.BIN", 0);
    if (h >= 0) { Fwrite((short)h, SCREEN_BYTES, screen_buf(shown)->px); Fclose((short)h); }

    int speed = 0;                       /* current throttle */
    int steering = 0;                    /* -1 / 0 / +1 this frame, from the arrow keys */
    long dist = 0;                       /* distance accumulator: advances a segment each DIST_PER_SEG */
    for (;;) {
        steering = 0;
        while (Cconis()) {               /* drain all pending keys (non-blocking) */
            long k = Cconin();
            int scan = (int)((k >> 16) & 0xff), ascii = (int)(k & 0xff);
            if (ascii == KEY_ESC || ascii == 'q' || ascii == 'Q') return;
            switch (scan) {
                case SCAN_UP:    speed += SPEED_STEP; if (speed > SPEED_MAX) speed = SPEED_MAX; break;
                case SCAN_DOWN:  speed -= SPEED_STEP; if (speed < 0) speed = 0; break;
                case SCAN_LEFT:  steering = -1; break;
                case SCAN_RIGHT: steering = 1; break;
                default:
                    if (ascii == ' ')
                        pose.view_flags = (uint16_t)((pose.view_flags + 2) % VIEW_BANK_WRAP);
                    else if (ascii == 'r' || ascii == 'R') {
                        pose.curve = ROAD_CURVE_INIT; pose.view_flags = ROAD_VIEW_FLAGS_INIT;
                        course.row_ctr = COURSE_ROW_CTR_INIT; course.read_pos = COURSE_READ_POS_INIT;
                        for (int i = 0; i < 13; i++) pose.seg_data[i] = seg_data_init[i];
                        speed = 0; dist = 0;
                    }
                    break;
            }
        }

        /* steer: add toward the held direction (clamped), else decay back to centre. */
        int curve = (int16_t)pose.curve;
        if (steering < 0)      curve = (curve - CURVE_STEP < -CURVE_MAX) ? -CURVE_MAX : curve - CURVE_STEP;
        else if (steering > 0) curve = (curve + CURVE_STEP >  CURVE_MAX) ?  CURVE_MAX : curve + CURVE_STEP;
        else if (curve > 0)    curve = (curve < CURVE_DECAY) ? 0 : curve - CURVE_DECAY;
        else if (curve < 0)    curve = (curve > -CURVE_DECAY) ? 0 : curve + CURVE_DECAY;
        pose.curve = (int16_t)curve;

        /* throttle: scroll the road band at `speed` and advance the course by the distance covered. */
        scroll.scroll_speed = (int16_t)speed;
        dist += speed;
        while (dist >= DIST_PER_SEG) { rm_road_course_advance(&pose, &course, stream); dist -= DIST_PER_SEG; }

        /* render off-screen, then flip the video base to it at the vblank (no tearing). */
        int back = shown ^ 1;
        draw_frame(screen_buf(back), &pose, &src, &road, &scroll, &hud, &assets);
        Setscreen(-1L, (long)screen_buf(back)->px, -1);
        Vsync();
        shown = back;
    }
}
