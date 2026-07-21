/* demo_main.c — interactive road + objects + HUD demo: remaster's own pipeline on a real 68000,
 * steered live.
 *
 * Each frame runs the full ported render pipeline in draw_frame order: rm_gobj_prefix (off-frame
 * state advance) -> rm_build_road_geometry -> rm_render_road -> rm_blit_road_scroll -> the
 * draw_game_objects tree (ground, foreground sprite, the two roadside object-list passes split around
 * the scaled draw_object, and the player buggy, ordered against the buggy by the view) -> rm_draw_hud,
 * then blits to the screen. The demo auto-runs (paced by the vertical blank) with non-blocking input:
 *   Up / Down    : throttle up / brake (speed scrolls the road and advances the leg's course)
 *   Left / Right : steer (road curvature; self-centres when released)
 *   Space        : cycle the view bank (0, 2, 4, 6)
 *   R            : reset the pose + course position;   Esc / Q : quit
 * The first frame (speed 0, before any input) is dumped to C:\SCREEN.BIN so a headless run can
 * byte-compare it to recreate's g_build_road_geometry + g_render_road + g_blit_road_scroll +
 * g_draw_game_objects + g_draw_hud (build/golden.bin).
 * All inputs are baked by gen_demo_fixture.py. See README.
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
void rm_gobj_prefix(GobjPrefixState *s, const GobjPrefixAssets *a);
void rm_draw_ground(const GroundState *s, const GroundAssets *a, Framebuffer *fb);
void rm_draw_fg_sprite(SpriteState *s, const SpriteAssets *a, Framebuffer *fb);
void rm_draw_buggy(SpriteState *s, const SpriteAssets *a, Framebuffer *fb);
void rm_draw_object(const ObjectInput *in, Framebuffer *fb);
void rm_draw_object_list(const ObjListCtx *c, const uint8_t *list, uint32_t list_off,
                         const uint8_t *flags, uint32_t flags_off,
                         uint16_t outer_rows_m1, uint16_t rec_off, uint16_t colour);

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

/* The prefix mutates its arenas (marker records, buf_a anim-word mirrors, the animated colour). The
 * anim-word mirrors land inside buf_a's record region (offsets 0xd70/0x1250), which the object
 * dispatcher then reads — so buf_a must be a MUTABLE copy of the fixture for the prefix write to be
 * seen by the draws, exactly as recreate's g_draw_game_objects does. The marker records + animated
 * colour are off-frame (this frame's marker slot is inactive), so they go to BSS scratch. */
static uint8_t ctrl[RM_CTRL_BYTES] __attribute__((aligned(2)));          /* BSS: per-frame control-long table */
static uint8_t scanline[RM_SCANLINE_BYTES] __attribute__((aligned(2)));  /* BSS: build_road_geometry scratch */
static uint8_t shifted[RM_SCROLL_SHIFTS * RM_SCROLL_WINDOW] __attribute__((aligned(2)));  /* pre-rotated scroll copies */
static uint8_t buf_a_ram[sizeof fixture_buf_a] __attribute__((aligned(2)));  /* mutable buf_a (prefix writes mirrors) */
static uint8_t gobj_scratch[0x400] __attribute__((aligned(2)));          /* BSS: marker recs (inactive) */
/* The prefix's animated colour aliases the HUD's phase-6a fuel-mask table in the original (both live
 * at 0x17f08): draw_game_objects' prefix writes the animated colour there, and draw_hud then reads it
 * as the fuel mask. Model that alias with one mutable buffer the prefix writes and the HUD reads. */
static uint8_t fuel_mask_ram[8] __attribute__((aligned(2)));

#define GOBJ_ANIM_BUF_OFF1 0xd70     /* buf_a + this = anim_word mirror 1 (read as a record by draws) */
#define GOBJ_ANIM_BUF_OFF2 0x1250    /* buf_a + this = anim_word mirror 2 */

/* Two screen buffers, 256-byte aligned at RUNTIME (the ST video base only uses the high/mid address
 * bytes, so a non-256-aligned base is rounded down → the image shifts). The link-time alignment isn't
 * enough because the GEMDOS load base needn't be 256-aligned, so over-allocate and round the pointer.
 * We render into the off-screen buffer and flip the video base to it at the vblank — a single-buffer
 * blit to the live screen tears badly at this render rate. SCREEN_BYTES is a multiple of 256, so the
 * second buffer stays aligned too.
 *
 * draw_game_objects legitimately writes off-screen sprite fragments well past the visible 32000 bytes
 * (partially/fully clipped roadside objects — measured up to ~102 KB past the screen). In the original
 * the draw buffer is followed by ample RAM, so those writes are harmless; here each buffer needs an
 * OVERDRAW tail so they don't corrupt the next buffer or BSS mid-frame. */
#define SCREEN_ALIGN 256
#define SCREEN_OVERDRAW 0x20000       /* scratch tail per buffer for off-screen object writes (>= max reach) */
#define SCREEN_STRIDE (SCREEN_BYTES + SCREEN_OVERDRAW)
static uint8_t screen_pool[2 * SCREEN_STRIDE + SCREEN_ALIGN];

static Framebuffer *screen_buf(int i) {
    unsigned long base = ((unsigned long)screen_pool + (SCREEN_ALIGN - 1)) & ~(unsigned long)(SCREEN_ALIGN - 1);
    return (Framebuffer *)(base + (unsigned long)i * SCREEN_STRIDE);
}

static const int16_t seg_data_init[13] = ROAD_SEG_DATA_INIT;

/* draw_game_objects' sprite-slot count: consecutive non-negative words (stride 0x20) after the base
 * of the sprite list, capped at 11. Selects how the two roadside object-list passes split. */
#define GOBJ_SPRITE_SLOTS   0xa
#define GOBJ_MARKER_STRIDE  0x20
#define GOBJ_SPRITE_LAST    10
#define GOBJ_ROW_A3_STRIDE  0x20
#define GOBJ_ROW_A5_STRIDE  0x22
#define GOBJ_D6_INIT        0xb0
#define GOBJ_D6_ROW_STEP    0x10
#define GOBJ_VIEW_REAR      4
#define GROUND_VIEW_COL_MUL 0xdd     /* view_flags * this = the ground/object-scan view column */

static int16_t be16s(const uint8_t *p) { return (int16_t)((p[0] << 8) | p[1]); }

static int sprite_count(const uint8_t *low) {
    const uint8_t *base = low + OBJ_LOW_SPRITE_LIST_BASE;
    if (be16s(base) < 0) return 0;
    int count = 0;
    for (int i = 0; i <= GOBJ_SPRITE_SLOTS; i++) {
        if (be16s(base + (i + 1) * GOBJ_MARKER_STRIDE) < 0) break;
        count++;
    }
    return count;
}

/* Run the full ported render pipeline into `fb`, in draw_game_objects order: prefix (off-frame state),
 * geometry + road + scroll band, then the object tree (ground, foreground sprite, the two sprite
 * object-list passes split around draw_object, and the buggy ordered against the fixed pass by the
 * view), then the HUD. The scroll advances every frame; the prefix advances view_parity/anim. */
static void draw_frame(Framebuffer *fb, RoadPose *pose, const RoadSource *src, RoadInput *road,
                       ScrollState *scroll, const HudState *hud, const HudAssets *hud_assets,
                       GobjPrefixState *pfx, const GobjPrefixAssets *pfx_assets,
                       const GroundState *ground, const GroundAssets *ground_assets,
                       SpriteState *sprite, const SpriteAssets *sprite_assets,
                       const ObjectInput *object, ObjListCtx *objlist, const uint8_t *low) {
    rm_gobj_prefix(pfx, pfx_assets);                 /* off-frame: advance view_parity/anim/marker */
    objlist->view_parity = pfx->view_parity;         /* the dispatcher (handler_lo) reads the advanced parity */
    objlist->px = fb->px;                            /* the dispatcher's draw target: this frame's buffer */
    rm_build_road_geometry(pose, src, ctrl, scanline);
    road->width_tbl = ctrl + RM_CTRL_WIDTH_OFF;
    /* The object dispatcher's per-row x-offset table aliases the freshly-built road control table in
     * the original (obj_xoff_tbl == road_width_tbl + 2), so rebind it to this frame's ctrl. */
    objlist->xoff_tbl = ctrl + RM_CTRL_WIDTH_OFF + 2;
    scroll->seg_head = pose->seg_head;               /* the scroll step follows the near slope */
    memset(fb->px, 0, SCREEN_BYTES);                 /* blank frame, then draw only remaster's pipeline */
    rm_render_road(road, fb);
    rm_blit_road_scroll(scroll, shifted, fb);

    /* --- draw_game_objects tree ---
     * DEMO_DUMP_STAGE (debug builds only) cuts the frame short after a chosen stage, so the normal
     * SCREEN.BIN dump yields a partial frame and a headless run can pinpoint the first stage whose
     * on-target output diverges from the host reference. Undefined in normal builds. */
#if defined(DEMO_DUMP_STAGE) && DEMO_DUMP_STAGE == 0
    return;
#endif
    rm_draw_ground(ground, ground_assets, fb);
#if defined(DEMO_DUMP_STAGE) && DEMO_DUMP_STAGE == 1
    return;
#endif
    rm_draw_fg_sprite(sprite, sprite_assets, fb);
#if defined(DEMO_DUMP_STAGE) && DEMO_DUMP_STAGE == 2
    return;
#endif

    int count = sprite_count(low);
    if (count - 1 >= 0)                               /* pass 1: the active sprite rows */
        rm_draw_object_list(objlist, low + OBJ_LOW_SPRITE_DISP, 0, low + OBJ_LOW_SPRITE_FLAGS, 0,
                            (uint16_t)(count - 1), GOBJ_D6_INIT, (uint16_t)count);
#if defined(DEMO_DUMP_STAGE) && DEMO_DUMP_STAGE == 3
    return;
#endif
    rm_draw_object(object, fb);
    if (GOBJ_SPRITE_LAST - count >= 0)               /* pass 2: the remaining rows */
        rm_draw_object_list(objlist,
                            low + OBJ_LOW_SPRITE_DISP, (uint16_t)(count * GOBJ_ROW_A5_STRIDE),
                            low + OBJ_LOW_SPRITE_FLAGS, (uint16_t)(count * GOBJ_ROW_A3_STRIDE),
                            (uint16_t)(GOBJ_SPRITE_LAST - count),
                            (uint16_t)(GOBJ_D6_INIT - count * GOBJ_D6_ROW_STEP), 0);
    if ((objlist->view_flags & GOBJ_VIEW_REAR) == 0) {   /* pass 3 (fixed) + buggy, view-ordered */
        rm_draw_object_list(objlist, low + OBJ_LOW_LIST_BASE, 0, low + OBJ_LOW_FLAGS, 0, 0, 0, 0);
        rm_draw_buggy(sprite, sprite_assets, fb);
    } else {
        rm_draw_buggy(sprite, sprite_assets, fb);
        rm_draw_object_list(objlist, low + OBJ_LOW_LIST_BASE, 0, low + OBJ_LOW_FLAGS, 0, 0, 0, 0);
    }

    rm_draw_hud(hud, hud_assets, fb);
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
        .color_bar_cidx = fixture_color_bar_cidx + CIDX_ZERO_OFF, .fuel_mask = fuel_mask_ram,
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

    /* --- draw_game_objects: a mutable buf_a copy (the prefix writes anim mirrors the draws read),
     * the object dispatcher context (arena pointers into the baked blobs; draw_buf 0 = fb->px base),
     * the ground + scaled-object inputs, the buggy sprite state, and the prefix state. --- */
    for (unsigned i = 0; i < sizeof buf_a_ram; i++) buf_a_ram[i] = fixture_buf_a[i];
    for (unsigned i = 0; i < sizeof fuel_mask_ram; i++) fuel_mask_ram[i] = fixture_fuel_mask[i];
    const uint8_t *low = fixture_obj_low;

    GobjPrefixState pfx = {
        .marker_active = PFX_MARKER_ACTIVE_INIT, .marker_off = PFX_MARKER_OFF_INIT,
        .marker_countdown = PFX_MARKER_CD_INIT, .view_parity = OBJ_VIEW_PARITY_INIT,
        .anim_counter = PFX_ANIM_COUNTER_INIT, .anim_word = PFX_ANIM_WORD_INIT,
        .bonus_timer = PFX_BONUS_TIMER_INIT, .dsp_color_scroll = PFX_DSP_SCROLL_INIT,
        .flag_seq_off = PFX_FLAG_SEQ_OFF_INIT, .flag_seq_count = PFX_FLAG_SEQ_CNT_INIT,
    };
    const GobjPrefixAssets pfx_assets = {
        .anim_word_tbl = low + OBJ_LOW_ANIM_WORD_TBL,
        .anim_coloridx_tbl = low + OBJ_LOW_ANIM_COLORIDX, .color_pairs = low + OBJ_LOW_COLOR_PAIRS,
        .marker_recs = gobj_scratch, .anim_color = fuel_mask_ram,   /* aliases the HUD's fuel mask */
        .anim_mirror1 = buf_a_ram + GOBJ_ANIM_BUF_OFF1, .anim_mirror2 = buf_a_ram + GOBJ_ANIM_BUF_OFF2,
    };
    const GroundState ground = {.view = OBJ_GROUND_VIEW_INIT};   /* markers copied below */
    const GroundAssets ground_assets = {
        .col_tbl = low + OBJ_LOW_GROUND_COL, .band_records = low + OBJ_LOW_GROUND_BAND,
        .color_pairs = low + OBJ_LOW_COLOR_PAIRS,
    };
    const ObjectInput object = {
        .width_tbl = ctrl + RM_CTRL_WIDTH_OFF, .blit_mask_l = low + OBJ_LOW_BLIT_MASK_L,
        .blit_mask_r = low + OBJ_LOW_BLIT_MASK_R, .shade = OBJ_SHADE_INIT,
    };
    ObjListCtx objlist = {
        /* px is rebound to the frame's buffer in draw_frame (we alternate two screen buffers). */
        .px = 0, .draw_buf = 0, .buf_a = buf_a_ram, .buf_c = fixture_buf_c,
        .color_pairs = low + OBJ_LOW_COLOR_PAIRS, .view_xform = low + OBJ_LOW_VIEW_XFORM,
        .objsh2p_tbl = low + OBJ_LOW_OBJSH2P_TBL, .jumptable = low + OBJ_LOW_JUMPTABLE,
        .xoff_tbl = low + OBJ_LOW_XOFF_TBL, .view_flags = ROAD_VIEW_FLAGS_INIT,
        .view_parity = OBJ_VIEW_PARITY_INIT, .bonus_timer = PFX_BONUS_TIMER_INIT,
        .obj_scan_off = 0, .p24_flag = OBJ_P24_FLAG_INIT,
    };
    SpriteState sprite = {
        .lean = SP_LEAN_INIT, .pitch = SP_PITCH_INIT, .skid = SP_SKID_INIT,
        .crash_disp = SP_CRASH_DISP_INIT, .wheel_pos = SP_WHEEL_POS_INIT,
        .spin_state = SP_SPIN_STATE_INIT, .road_curve = ROAD_CURVE_INIT,
        .sprite_suppress = SP_SPRITE_SUPPRESS_INIT, .fg_gate = SP_FG_GATE_INIT,
        .anim_frame = SP_ANIM_FRAME_INIT, .spin_reset = SP_SPIN_RESET_INIT,
        .buggy_draw_flag = SP_BUGGY_DRAW_FLAG_INIT, .buggy_gate = SP_BUGGY_GATE_INIT,
        .collision_lock = SP_COLLISION_LOCK_INIT, .speed_raw = SP_SPEED_RAW_INIT,
        .lean_accum = SP_LEAN_ACCUM_INIT, .lean_frame = SP_LEAN_FRAME_INIT,
    };
    const SpriteAssets sprite_assets = {
        .gfx = fixture_buf_c, .fg_anim_tbl = low + OBJ_LOW_FG_ANIM_TBL,
        .body_tbl = low + OBJ_LOW_BODY_TBL, .hi_tbl = low + OBJ_LOW_HI_TBL,
        .lo_piece_tbl = low + OBJ_LOW_LO_PIECE_TBL, .lo_piece_idx = low + OBJ_LOW_LO_PIECE_IDX,
    };
    GroundState ground_mut = ground;
    for (int i = 0; i < GROUND_SCAN_ENTRIES; i++)
        ground_mut.markers[i] = low[OBJ_LOW_GROUND_SCAN + i * GOBJ_MARKER_STRIDE + 3];

    Setpalette(fixture_palette);
    rm_scroll_prebuild(fixture_road_play, shifted);   /* pre-rotate the playfield once (screen_offset is fixed) */
    int shown = 0;
    draw_frame(screen_buf(shown), &pose, &src, &road, &scroll, &hud, &assets, &pfx, &pfx_assets,
               &ground_mut, &ground_assets, &sprite, &sprite_assets, &object, &objlist, low);
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

        /* keep the object draws in step with the live pose: the buggy reads the steering curve and the
         * object dispatcher / ground select on the view bank. The ground's view column and the object
         * list's scan offset are the SAME global in the original (0x18c58 = view_flags * 0xdd), so both
         * follow the view bank together. */
        sprite.road_curve = pose.curve;
        objlist.view_flags = pose.view_flags;
        int16_t view_col = (int16_t)(pose.view_flags * GROUND_VIEW_COL_MUL);
        ground_mut.view = view_col;
        objlist.obj_scan_off = view_col;

        /* render off-screen, then flip the video base to it at the vblank (no tearing). */
        int back = shown ^ 1;
        draw_frame(screen_buf(back), &pose, &src, &road, &scroll, &hud, &assets, &pfx, &pfx_assets,
                   &ground_mut, &ground_assets, &sprite, &sprite_assets, &object, &objlist, low);
        Setscreen(-1L, (long)screen_buf(back)->px, -1);
        Vsync();
        shown = back;
    }
}
