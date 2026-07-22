/* bench_main.c — per-function entry points for cycle-benchmarking the remaster render cores on a
 * 68000 (Musashi), against recreate's cross-compiled recon. Each bench_* symbol is a zero-work
 * wrapper that calls one core with structs staged from the baked demo fixture; tools/bench.py loads
 * this ELF, jumps to each wrapper via emu.run_bench, and counts instructions/cycles. Not a program
 * (no real main loop): main() exists only so os.s links.
 *
 * The wrappers cover every stage of the demo's frame (demo_main.c draw_frame + the game-loop step),
 * so their sum is the demo's true frame cost on the staged leg-1 frame. Object costs vary with what
 * is in view; this is one representative frame, not a worst case.
 */
#include <stdint.h>
#include <string.h>          /* freestanding libc, defined in shim.c */

#include "assets.h"
#include "game.h"
#include "screen.h"
#include "demo_fixture.h"
#include "demo_frame.h"

void rm_draw_hud(const HudState *s, const HudAssets *a, Framebuffer *fb);

#define BENCH_SCROLL_SPEED 0x20     /* a representative racing speed (exercises the scroll edge/wrap tail) */

static Framebuffer fb __attribute__((aligned(2)));
static uint8_t ctrl[RM_CTRL_ALLOC_BYTES] __attribute__((aligned(2)));
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

static uint8_t fuel_mask_ram[8] __attribute__((aligned(2)));   /* prefix anim_color / HUD fuel-mask alias */

static HudAssets assets = {
    .color_pairs = fixture_color_pairs, .color_bar_mask = fixture_color_bar_mask,
    /* the HUD reads the same mutable buffer the prefix's animated colour writes, as in the demo */
    .color_bar_cidx = fixture_color_bar_cidx + CIDX_ZERO_OFF, .fuel_mask = fuel_mask_ram,
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

/* --- the draw_game_objects tree + player step, staged exactly as demo_main.c stages them --- */
static uint8_t buf_a_ram[ARENA_BUF_A_BYTES] __attribute__((aligned(2)));  /* mutable buf_a (prefix mirrors) */
static uint8_t gobj_scratch[GOBJ_MARKER_RECS_BYTES] __attribute__((aligned(2)));  /* marker recs (inactive) */
static uint8_t ring_st[RM_RING_ROWS * RM_RING_ROW_BYTES] __attribute__((aligned(2)));

static GobjPrefixState pfx = {
    .marker_active = PFX_MARKER_ACTIVE_INIT, .marker_off = PFX_MARKER_OFF_INIT,
    .marker_countdown = PFX_MARKER_CD_INIT, .view_parity = OBJ_VIEW_PARITY_INIT,
    .anim_counter = PFX_ANIM_COUNTER_INIT, .anim_word = PFX_ANIM_WORD_INIT,
    .bonus_timer = PFX_BONUS_TIMER_INIT, .dsp_color_scroll = PFX_DSP_SCROLL_INIT,
    .flag_seq_off = PFX_FLAG_SEQ_OFF_INIT, .flag_seq_count = PFX_FLAG_SEQ_CNT_INIT,
};
static const GobjPrefixAssets pfx_assets = {
    .anim_word_tbl = fixture_obj_low + OBJ_LOW_ANIM_WORD_TBL,
    .anim_coloridx_tbl = fixture_obj_low + OBJ_LOW_ANIM_COLORIDX,
    .color_pairs = fixture_obj_low + OBJ_LOW_COLOR_PAIRS,
    .marker_recs = gobj_scratch, .anim_color = fuel_mask_ram,
    .anim_mirror1 = buf_a_ram + GOBJ_ANIM_BUF_OFF1, .anim_mirror2 = buf_a_ram + GOBJ_ANIM_BUF_OFF2,
};
static GroundState ground = {.view = OBJ_GROUND_VIEW_INIT};   /* markers staged from the ring */
static const GroundAssets ground_assets = {
    .col_tbl = fixture_obj_low + OBJ_LOW_GROUND_COL,
    .band_records = fixture_obj_low + OBJ_LOW_GROUND_BAND,
    .color_pairs = fixture_obj_low + OBJ_LOW_COLOR_PAIRS,
};
static const ObjectInput object = {
    .width_tbl = ctrl + RM_CTRL_WIDTH_OFF, .blit_mask_l = fixture_obj_low + OBJ_LOW_BLIT_MASK_L,
    .blit_mask_r = fixture_obj_low + OBJ_LOW_BLIT_MASK_R, .shade = OBJ_SHADE_INIT,
};
static ObjListCtx objlist = {
    .px = 0, .draw_buf = 0, .buf_a = buf_a_ram, .buf_c = 0,   /* px/buf_c bound in bench_stage_assets */
    .color_pairs = fixture_obj_low + OBJ_LOW_COLOR_PAIRS,
    .view_xform = fixture_obj_low + OBJ_LOW_VIEW_XFORM,
    .objsh2p_tbl = fixture_obj_low + OBJ_LOW_OBJSH2P_TBL,
    .jumptable = fixture_obj_low + OBJ_LOW_JUMPTABLE,
    .xoff_tbl = ctrl + RM_CTRL_WIDTH_OFF + 2,                 /* aliases the freshly-built ctrl */
    /* Standalone objlist rows run at this staged parity; the composites advance it via the prefix
     * first, as the demo does. Both are real frames (parity alternates every frame) — the per-stage
     * rows and the composites just sample opposite phases of it. */
    .view_flags = ROAD_VIEW_FLAGS_INIT, .view_parity = OBJ_VIEW_PARITY_INIT,
    .bonus_timer = PFX_BONUS_TIMER_INIT, .obj_scan_off = OBJ_GROUND_VIEW_INIT,
    .p24_flag = OBJ_P24_FLAG_INIT,
};
static SpriteState sprite = {
    .lean = SP_LEAN_INIT, .pitch = SP_PITCH_INIT, .skid = SP_SKID_INIT,
    .crash_disp = SP_CRASH_DISP_INIT, .wheel_pos = SP_WHEEL_POS_INIT,
    .spin_state = SP_SPIN_STATE_INIT, .road_curve = ROAD_CURVE_INIT,
    .sprite_suppress = SP_SPRITE_SUPPRESS_INIT,
    .anim_frame = SP_ANIM_FRAME_INIT, .spin_reset = SP_SPIN_RESET_INIT,
    .buggy_draw_flag = SP_BUGGY_DRAW_FLAG_INIT,
    .collision_lock = SP_COLLISION_LOCK_INIT, .speed_raw = SP_SPEED_RAW_INIT,
    .lean_accum = SP_LEAN_ACCUM_INIT, .lean_frame = SP_LEAN_FRAME_INIT,
};
static SpriteAssets sprite_assets = {
    .gfx = 0,                                                 /* bound in bench_stage_assets */
    .fg_anim_tbl = fixture_obj_low + OBJ_LOW_FG_ANIM_TBL,
    .body_tbl = fixture_obj_low + OBJ_LOW_BODY_TBL, .hi_tbl = fixture_obj_low + OBJ_LOW_HI_TBL,
    .lo_piece_tbl = fixture_obj_low + OBJ_LOW_LO_PIECE_TBL,
    .lo_piece_idx = fixture_obj_low + OBJ_LOW_LO_PIECE_IDX,
};
static const PlayerAssets player_assets = {
    .lean_anim_tbl = fixture_obj_low + OBJ_LOW_LEAN_ANIM_TBL,
    .scroll_speed_tbl = fixture_obj_low + OBJ_LOW_SCROLL_SPEED_TBL,
    .speed_jitter_tbl = fixture_obj_low + OBJ_LOW_SPEED_JITTER_TBL,
    .steer_curve_tbl = fixture_obj_low + OBJ_LOW_STEER_CURVE_TBL,
    .legflag_tbl = fixture_obj_low + OBJ_LOW_LEGFLAG_TBL,
    .crash_anim_tbl = fixture_obj_low + OBJ_LOW_CRASH_ANIM_TBL,
};
static PlayerState player = {
    .input = RM_IN_ACCEL,       /* a driving frame, so the physics walks its live paths */
    .engine_rpm = PL_ENGINE_RPM_INIT, .rpm_cap = PL_RPM_CAP_INIT, .rpm_add = PL_RPM_ADD_INIT,
    .speed_raw = PL_SPEED_RAW_INIT, .speed = PL_SPEED_INIT,
    .speed_jitter_ph = PL_SPEED_JITTER_PH_INIT, .scroll_phase = PL_SCROLL_PHASE_INIT,
    .scroll_speed = SCROLL_SPEED_INIT, .view_flags = ROAD_VIEW_FLAGS_INIT,
    .view_bank = PL_VIEW_BANK_INIT, .ground_view_off = PL_GROUND_VIEW_OFF_INIT,
    .road_edge_sel = PL_ROAD_EDGE_SEL_INIT, .wheel_pos = PL_WHEEL_POS_INIT,
    .steer_hold = PL_STEER_HOLD_INIT, .lean_phase = PL_LEAN_PHASE_INIT, .lean = SP_LEAN_INIT,
    .road_curve = ROAD_CURVE_INIT, .skid = SP_SKID_INIT, .fire_hold = PL_FIRE_HOLD_INIT,
    .dsp_variant_idx = HUD_DSP_VARIANT_IDX, .leg_flags_sel = PL_LEG_FLAGS_SEL_INIT,
    .time_subctr = PL_TIME_SUBCTR_INIT, .time_left = HUD_TIME_LEFT,
    .hud_crash_timer = HUD_CRASH_TIMER, .timeout_gate = PL_TIMEOUT_GATE_INIT,
};

void bench_ring_views(void);

/* Bind everything that lives in the loaded asset arena, plus the mutable copies the demo stages at
 * boot (buf_a, the fuel-mask alias, the serialized ring views). bench.py runs this before every
 * measured call, on memory it has already filled with the unpacked arena. */
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

    memcpy(buf_a_ram, arena.tables, sizeof buf_a_ram);
    memcpy(fuel_mask_ram, fixture_fuel_mask, sizeof fuel_mask_ram);
    objlist.px = fb.px;
    objlist.buf_c = arena.gfx;
    sprite_assets.gfx = arena.gfx;
    bench_ring_views();
}

/* One representative frame's worth of each core (as the demo's draw_frame chains them). */
void bench_build_geometry(void) { rm_build_road_geometry(&pose, &src, &ring, ctrl, scanline); }
void bench_render_road(void)    { road.width_tbl = ctrl + RM_CTRL_WIDTH_OFF; rm_render_road(&road, &fb); }
void bench_scroll_prebuild(void) { rm_scroll_prebuild(scroll_playfield, shifted); }
void bench_blit_scroll(void)    { rm_blit_road_scroll(&scroll, shifted, &fb); }
void bench_draw_hud(void)       { rm_draw_hud(&hud, &assets, &fb); }
void bench_course_advance(void) { rm_road_course_advance(&pose, &course, &ring, course_stream); }

/* The game-loop step + the draw_game_objects stages (demo_main.c draw_frame order). */
void bench_player_update(void)  { rm_player_update(&player, &player_assets, ctrl); }
void bench_gobj_prefix(void)    { rm_gobj_prefix(&pfx, &pfx_assets); }
void bench_frame_clear(void)    { memset(fb.px, 0, SCREEN_BYTES); }
void bench_draw_ground(void)    { rm_draw_ground(&ground, &ground_assets, &fb); }
void bench_draw_fg_sprite(void) { rm_draw_fg_sprite(&sprite, &sprite_assets, &fb); }
void bench_draw_object(void)    { rm_draw_object(&object, &fb); }
void bench_draw_buggy(void)     { rm_draw_buggy(&sprite, &sprite_assets, &fb); }
void bench_ring_views(void)     {
    rm_ring_store_st(&ring, ring_st);
    rm_ring_ground_markers(&ring, ground.markers);
    sprite.buggy_gate = rm_ring_buggy_gate(&ring);
    sprite.fg_gate = rm_ring_fg_gate(&ring);
}

/* The two roadside sprite passes split around draw_object, and the fixed pass (demo pass split). */
void bench_objlist_pass1(void) {
    int count = rm_ring_sprite_count(&ring);
    if (count - 1 >= 0)
        rm_draw_object_list(&objlist, fixture_obj_low + OBJ_LOW_SPRITE_DISP, 0,
                            ring_st + GOBJ_SPRITE_PASS_ROW * RM_RING_ROW_BYTES, 0,
                            (uint16_t)(count - 1), GOBJ_D6_INIT, (uint16_t)count);
}
void bench_objlist_pass2(void) {
    int count = rm_ring_sprite_count(&ring);
    if (GOBJ_SPRITE_LAST - count >= 0)
        rm_draw_object_list(&objlist,
                            fixture_obj_low + OBJ_LOW_SPRITE_DISP, (uint16_t)(count * GOBJ_ROW_A5_STRIDE),
                            ring_st + GOBJ_SPRITE_PASS_ROW * RM_RING_ROW_BYTES, (uint16_t)(count * GOBJ_ROW_A3_STRIDE),
                            (uint16_t)(GOBJ_SPRITE_LAST - count),
                            (uint16_t)(GOBJ_D6_INIT - count * GOBJ_D6_ROW_STEP), 0);
}
void bench_objlist_fixed(void) {
    rm_draw_object_list(&objlist, fixture_obj_low + OBJ_LOW_LIST_BASE, 0,
                        ring_st + GOBJ_FIXED_PASS_ROW * RM_RING_ROW_BYTES, 0, 0, 0, 0);
}

/* The object stages after the road — ground through the view-ordered fixed-pass/buggy tail. ONE
 * copy, called by both composites, so they cannot drift from each other (both must keep mirroring
 * demo_main.c's draw_frame). */
static void object_stages(void) {
    bench_draw_ground();
    bench_draw_fg_sprite();
    bench_objlist_pass1();
    bench_draw_object();
    bench_objlist_pass2();
    if ((objlist.view_flags & GOBJ_VIEW_REAR) == 0) {
        bench_objlist_fixed();
        bench_draw_buggy();
    } else {
        bench_draw_buggy();
        bench_objlist_fixed();
    }
}

/* The whole object tree in one call — recreate's g_draw_game_objects scope, for the rm/rec ratio. */
void bench_object_tree(void) {
    bench_gobj_prefix();
    objlist.view_parity = pfx.view_parity;
    object_stages();
}

/* The demo's whole draw_frame (demo_main.c), for the true per-frame render cost. */
void bench_draw_frame(void) {
    bench_gobj_prefix();
    objlist.view_parity = pfx.view_parity;
    bench_build_geometry();
    scroll.seg_head = pose.seg_head;
    bench_frame_clear();
    bench_render_road();
    bench_blit_scroll();
    object_stages();
    bench_draw_hud();
}

int main(void) { return 0; }        /* unused; present so os.s's `jsr main` links */
