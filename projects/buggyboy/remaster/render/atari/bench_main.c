/* bench_main.c — per-function entry points for cycle-benchmarking the remaster render cores on a
 * 68000 (Musashi), against recreate's cross-compiled recon. Each bench_* symbol is a zero-work
 * wrapper that calls one core with structs staged from the baked game fixture; tools/bench.py loads
 * this ELF, jumps to each wrapper via emu.run_bench, and counts instructions/cycles. Not a program
 * (no real main loop): main() exists only so os.s links.
 *
 * The wrappers cover every stage of the game's frame (game_main.c draw_frame + the game-loop step),
 * so their sum is the game's true frame cost on the staged leg-0 boot frame. Object costs vary with
 * what is in view; this is one representative frame, not a worst case.
 */
#include <stdint.h>
#include <string.h>          /* freestanding libc, defined in shim.c */

#include "assets.h"
#include "game.h"
#include "screen.h"
#include "game_fixture.h"
#include "game_frame.h"

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
/* rm_init_leg rewrites the HUD-text score / bonus-time region; the game does the same into a mutable
 * copy, so mirror it here (seeded from the baked leg-start text in bench_stage_assets). */
static uint8_t hud_text_ram[sizeof fixture_hud_text] __attribute__((aligned(2)));

static HudAssets assets = {
    .color_pairs = fixture_color_pairs, .color_bar_mask = fixture_color_bar_mask,
    /* the HUD reads the same mutable buffer the prefix's animated colour writes, as in the game */
    .color_bar_cidx = fixture_color_bar_cidx + CIDX_ZERO_OFF, .fuel_mask = fuel_mask_ram,
    .font = fixture_font, .hud_text = hud_text_ram, .dsp_table = fixture_dsp_table,
    .small_gauge_str = fixture_small_gauge_str,
    .num_glyph_tbl = fixture_num_glyph_tbl, .crash_color_tbl = fixture_crash_color_tbl,
    .score_delta_time = fixture_score_delta_time, .score_delta_roll = fixture_score_delta_roll,
};
static const RoadSource src = {
    .persp_seg = (const int8_t *)fixture_road_persp_seg,
    .width_count = fixture_road_width_count,
};
/* The per-band road widths the builder reads: live course state, seeded by rm_init_leg in
 * bench_stage_assets and advanced by bench_course_advance. */
static CourseRing ring;
static RoadInput road = {
    .width_tbl = ctrl + RM_CTRL_WIDTH_OFF, .param = fixture_road_param,
    .edge_tbl = fixture_road_edge + ROAD_EDGE_PAD, .edge_const = fixture_road_edge_const,
};
static const uint8_t *course_stream;
/* The per-leg owner structs rm_init_leg fills in bench_stage_assets (as game_main.c stages them), not
 * baked; scroll.scroll_speed is then forced to BENCH_SCROLL_SPEED there. */
static RoadPose pose;
static ScrollState scroll;
static CourseState course;
static EventState ev;              /* rm_init_leg owner struct (not otherwise read by the bench) */
static uint16_t screen_offset;     /* rm_init_leg output; the bench prebuilds a FIXED scroll offset */

/* --- the draw_game_objects tree + player step, staged exactly as game_main.c stages them --- */
static uint8_t buf_a_ram[ARENA_BUF_A_BYTES] __attribute__((aligned(2)));  /* mutable buf_a (prefix mirrors) */
static uint8_t gobj_scratch[GOBJ_MARKER_RECS_BYTES] __attribute__((aligned(2)));  /* marker recs (inactive) */
static uint8_t ring_st[RM_RING_ROWS * RM_RING_ROW_BYTES] __attribute__((aligned(2)));

static GobjPrefixState pfx;        /* filled by rm_init_leg in bench_stage_assets */
static const GobjPrefixAssets pfx_assets = {
    .anim_word_tbl = fixture_obj_low + OBJ_LOW_ANIM_WORD_TBL,
    .anim_coloridx_tbl = fixture_obj_low + OBJ_LOW_ANIM_COLORIDX,
    .color_pairs = fixture_obj_low + OBJ_LOW_COLOR_PAIRS,
    .marker_recs = gobj_scratch, .anim_color = fuel_mask_ram,
    .anim_mirror1 = buf_a_ram + GOBJ_ANIM_BUF_OFF1, .anim_mirror2 = buf_a_ram + GOBJ_ANIM_BUF_OFF2,
};
static GroundState ground;         /* view + markers derived from the reset state / ring (bench_stage_assets) */
static const GroundAssets ground_assets = {
    .col_tbl = fixture_obj_low + OBJ_LOW_GROUND_COL,
    .band_records = fixture_obj_low + OBJ_LOW_GROUND_BAND,
    .color_pairs = fixture_obj_low + OBJ_LOW_COLOR_PAIRS,
};
/* object.shade is rm_init_leg's obj_shade output, set in bench_stage_assets. */
static ObjectInput object = {
    .width_tbl = ctrl + RM_CTRL_WIDTH_OFF, .blit_mask_l = fixture_obj_low + OBJ_LOW_BLIT_MASK_L,
    .blit_mask_r = fixture_obj_low + OBJ_LOW_BLIT_MASK_R,
};
static ObjListCtx objlist = {
    .px = 0, .draw_buf = 0, .buf_a = buf_a_ram, .buf_c = 0,   /* px/buf_c bound in bench_stage_assets */
    .color_pairs = fixture_obj_low + OBJ_LOW_COLOR_PAIRS,
    .view_xform = fixture_obj_low + OBJ_LOW_VIEW_XFORM,
    .objsh2p_tbl = fixture_obj_low + OBJ_LOW_OBJSH2P_TBL,
    .jumptable = fixture_obj_low + OBJ_LOW_JUMPTABLE,
    .xoff_tbl = ctrl + RM_CTRL_WIDTH_OFF + 2,                 /* aliases the freshly-built ctrl */
    /* view_flags / view_parity / bonus_timer / obj_scan_off / p24_flag are derived from the reset
     * owner structs in bench_stage_assets (as game_main.c's start_leg derives them). Standalone
     * objlist rows run at that staged parity; the composites advance it via the prefix first, as the
     * game does — both are real frames (parity alternates every frame). */
};
static SpriteState sprite;         /* the buggy pose — filled by rm_init_leg in bench_stage_assets */
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
/* Filled by rm_init_leg in bench_stage_assets; input is forced to a driving frame there so the physics
 * walks its live paths. */
static PlayerState player;
/* rm_player_update takes an RmEventCtx*, but the bench frame drives with collision_lock and
 * event_pending clear, so §6's event path (the only code that dereferences ctx) is never taken and
 * the dispatch never runs — so just the physics-side pointers are enough; the event-only fields
 * (ev / assets / hud_text / gfx the dispatch would read) are left unset, which the measured call never
 * touches. */
static RmEventCtx ctx = {
    .player = &player, .gobj = &pfx, .ring = &ring, .pose = &pose, .road_src = &src,
    .ctrl = ctrl, .scanline = scanline, .leg = GAME_LEG_INDEX, .game_over = 0,
};

void bench_ring_views(void);

/* Bind everything that lives in the loaded asset arena, plus the mutable copies the game stages at
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

    /* Stage the leg-start owner state NATIVELY (rm_init_leg, as game_main.c does) rather than baking a
     * *_INIT snapshot: the physics / course / pose / scroll scalars, the ring seeded from the leg's
     * marker records, the buggy pose, the HUD-text region and object.shade. Then the bench's two
     * deliberate overrides (a driving input; a representative racing scroll speed) and the render
     * VIEWS derived from the owners exactly as game_main.c's start_leg derives them. Re-run before
     * every measured call, so each stage starts from a fresh leg-start state. */
    for (unsigned i = 0; i < sizeof fixture_hud_text; i++) hud_text_ram[i] = fixture_hud_text[i];
    RmInitAssets init_assets = {.buf_a = arena.tables, .legtime = fixture_legtime};
    static uint8_t race_pal[RM_RACE_PAL_BYTES];   /* phase-11 staging sink (obj_shade is the read output) */
    rm_init_leg(&player, &course, &pose, &scroll, &ring, &ev, &pfx, &sprite,
                hud_text_ram, &object.shade, &screen_offset, race_pal, &init_assets, GAME_LEG_INDEX);
    player.input = RM_IN_ACCEL;                 /* a driving frame, so the physics walks its live paths */
    scroll.scroll_speed = BENCH_SCROLL_SPEED;   /* a representative racing speed (scroll edge/wrap tail) */
    ground.view = player.ground_view_off;
    objlist.view_flags = pose.view_flags;
    objlist.view_parity = pfx.view_parity;
    objlist.bonus_timer = pfx.bonus_timer;
    objlist.obj_scan_off = player.ground_view_off;
    objlist.p24_flag = hud_text_ram[RM_HUD_SCORE_STR_OFF + 1];

    bench_ring_views();
}

/* One representative frame's worth of each core (as the game's draw_frame chains them). */
void bench_build_geometry(void) { rm_build_road_geometry(&pose, &src, &ring, ctrl, scanline); }
void bench_render_road(void)    { road.width_tbl = ctrl + RM_CTRL_WIDTH_OFF; rm_render_road(&road, &fb); }
void bench_scroll_prebuild(void) { rm_scroll_prebuild(scroll_playfield, shifted); }
void bench_blit_scroll(void)    { rm_blit_road_scroll(&scroll, shifted, &fb); }
void bench_draw_hud(void)       { rm_draw_hud(&hud, &assets, &fb); }
void bench_course_advance(void) { rm_road_course_advance(&pose, &course, &ring, course_stream); }

/* The game-loop step + the draw_game_objects stages (game_main.c draw_frame order). */
void bench_player_update(void)  { rm_player_update(&player, &player_assets, ctrl, &ctx); }
void bench_gobj_prefix(void)    { rm_gobj_prefix(&pfx, &pfx_assets); }
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

/* The two roadside sprite passes split around draw_object, and the fixed pass (game pass split). */
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

/* ---- PERF30 A3: objshift2 hand-asm core, C vs asm, plus the asm-vs-C differential param block ----
 * The composed rows above (bench_objlist_fixed / bench_object_tree / bench_draw_frame) already run the
 * ASM path — this build defines RM_ASM_BLIT, so object_list.c's RM_BLIT_OBJSHIFT2 dispatches to the
 * asm, exactly like the game. These extra entries measure the two engines head to head on one
 * self-contained representative blit, and expose a param-block harness for test/test_asm_blit.py. */
#define OBJSH2_BUF_BYTES  0x4000
#define OBJSH2_BUF_MID    0x2000            /* start the cursors mid-buffer: room to walk up 0x2a rows */
uint8_t objsh2_dst[OBJSH2_BUF_BYTES] __attribute__((aligned(2)));
uint8_t objsh2_src[OBJSH2_BUF_BYTES] __attribute__((aligned(2)));

/* Representative gate-frame-class workload: a full base straddle (width_idx 0 -> 3 straddle cells),
 * fine_x 7, 0x2a rows — the dominant fixed-pass shape. bench.py measures _c vs _asm on it. */
#define OBJSH2_BENCH_X       ((0x40 << 1) | 7)   /* aligned col 0x40, fine_x 7 -> BASE straddle 3 */
#define OBJSH2_BENCH_ROWS_M1 0x2a
/* ONE 7-arg marshalling site (F9), shared by the microbench pair (static args) and the param-block
 * pair below: `engine` and the arg source are the only things that vary. Expands to the same direct
 * call as before, so the C-vs-asm cycle counts (and their ratio) are unchanged. */
#define OBJSH2_INVOKE(engine, D, DOFF, S, SOFF, X, ROWS, WI) \
    engine((uint8_t *)(D), (DOFF), (const uint8_t *)(S), (SOFF), (X), (ROWS), (WI))
void bench_objshift2_c(void) {
    OBJSH2_INVOKE(rm_blit_objshift2, objsh2_dst, OBJSH2_BUF_MID, objsh2_src, OBJSH2_BUF_MID,
                  OBJSH2_BENCH_X, OBJSH2_BENCH_ROWS_M1, 0);
}
void bench_objshift2_asm(void) {
    OBJSH2_INVOKE(rm_blit_objshift2_asm, objsh2_dst, OBJSH2_BUF_MID, objsh2_src, OBJSH2_BUF_MID,
                  OBJSH2_BENCH_X, OBJSH2_BENCH_ROWS_M1, 0);
}

/* Param block the differential test pokes: dst/src are absolute addresses of any staged buffer in the
 * flat Musashi image (objsh2_dst/objsh2_src, or the test's own region); the run wrappers unpack it and
 * invoke one engine, so the test can drive every fuzz case through both and byte-compare. */
typedef struct {
    uint32_t dst, dst_off, src, src_off;
    uint16_t x, rows_m1;
    int32_t  width_idx;
} Objsh2Args;
Objsh2Args objsh2_args;
void bench_objsh2_run_c(void) {
    OBJSH2_INVOKE(rm_blit_objshift2, objsh2_args.dst, objsh2_args.dst_off,
                  objsh2_args.src, objsh2_args.src_off,
                  objsh2_args.x, objsh2_args.rows_m1, objsh2_args.width_idx);
}
void bench_objsh2_run_asm(void) {
    OBJSH2_INVOKE(rm_blit_objshift2_asm, objsh2_args.dst, objsh2_args.dst_off,
                  objsh2_args.src, objsh2_args.src_off,
                  objsh2_args.x, objsh2_args.rows_m1, objsh2_args.width_idx);
}

/* ---- PERF30 A3 phase 2: objshift (colour-indexed pass-1) hand-asm core, C vs asm + differential ----
 * Same shape as the objshift2 block above (buffers started mid-buffer, ONE marshalling macro, a static
 * microbench pair for bench.py, and a param-block pair for test/test_asm_blit.py). The extra buffer here
 * is objsh_pairs: the 16-entry x 8-byte color_pairs table the engine indexes by the colour nibble — the
 * differential test stages a distinct-byte table into it and fuzzes the nibble so the colour gate bits
 * actually vary; the static microbench reads the real baked fixture_color_pairs. */
#define OBJSH_PAIRS_BYTES  (16 * 8)         /* 16 colour entries x one 4-plane fill pair (8 bytes) */
uint8_t objsh_dst[OBJSH2_BUF_BYTES] __attribute__((aligned(2)));
uint8_t objsh_src[OBJSH2_BUF_BYTES] __attribute__((aligned(2)));
uint8_t objsh_pairs[OBJSH_PAIRS_BYTES] __attribute__((aligned(2)));

/* Representative gate-frame shape: base_cells 1 -> BASE straddle 1, fine_x 7, colour 7, stride 8 (the
 * pass-1 hi/tail callers' mode word), 0x2a rows — the dominant pass-1 blit. bench.py measures _c vs _asm. */
#define OBJSH_BENCH_X       ((0x40 << 1) | 7)   /* aligned col 0x40, fine_x 7 -> BASE */
#define OBJSH_BENCH_COLOR    7
#define OBJSH_BENCH_ROWS_M1  0x2a
#define OBJSH_BENCH_STRIDE   8
#define OBJSH_BENCH_BCELLS   1
/* ONE 10-arg marshalling site, shared by the microbench pair (static args) and the param-block pair. */
#define OBJSH_INVOKE(engine, D, DOFF, S, SOFF, X, COL, ROWS, STR, CP, BC) \
    engine((uint8_t *)(D), (DOFF), (const uint8_t *)(S), (SOFF), (X), (COL), (ROWS), (STR), \
           (const uint8_t *)(CP), (BC))
void bench_objshift_c(void) {
    OBJSH_INVOKE(rm_blit_objshift, objsh_dst, OBJSH2_BUF_MID, objsh_src, OBJSH2_BUF_MID,
                 OBJSH_BENCH_X, OBJSH_BENCH_COLOR, OBJSH_BENCH_ROWS_M1, OBJSH_BENCH_STRIDE,
                 fixture_color_pairs, OBJSH_BENCH_BCELLS);
}
void bench_objshift_asm(void) {
    OBJSH_INVOKE(rm_blit_objshift_asm, objsh_dst, OBJSH2_BUF_MID, objsh_src, OBJSH2_BUF_MID,
                 OBJSH_BENCH_X, OBJSH_BENCH_COLOR, OBJSH_BENCH_ROWS_M1, OBJSH_BENCH_STRIDE,
                 fixture_color_pairs, OBJSH_BENCH_BCELLS);
}

/* Param block the differential test pokes (all 10 args; dst/src/color_pairs are absolute addresses of
 * staged buffers in the flat Musashi image). Field order + sizes mirror the test's struct.pack layout. */
typedef struct {
    uint32_t dst, dst_off, src, src_off;
    uint16_t x, color, rows_m1;
    int16_t  stride;
    uint32_t color_pairs;
    int32_t  base_cells;
} ObjshArgs;
ObjshArgs objsh_args;
void bench_objsh_run_c(void) {
    OBJSH_INVOKE(rm_blit_objshift, objsh_args.dst, objsh_args.dst_off, objsh_args.src, objsh_args.src_off,
                 objsh_args.x, objsh_args.color, objsh_args.rows_m1, objsh_args.stride,
                 objsh_args.color_pairs, objsh_args.base_cells);
}
void bench_objsh_run_asm(void) {
    OBJSH_INVOKE(rm_blit_objshift_asm, objsh_args.dst, objsh_args.dst_off, objsh_args.src, objsh_args.src_off,
                 objsh_args.x, objsh_args.color, objsh_args.rows_m1, objsh_args.stride,
                 objsh_args.color_pairs, objsh_args.base_cells);
}

/* The object stages after the road — ground through the view-ordered fixed-pass/buggy tail. ONE
 * copy, called by both composites, so they cannot drift from each other (both must keep mirroring
 * game_main.c's draw_frame). */
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

/* The game's whole draw_frame, for the true per-frame render cost. The canonical composition + order
 * is rm_draw_frame (src/frame.c), which the shell calls; this rig mirrors that order but stages the
 * HUD scalars deliberately (const `hud` above) so the measured frame exercises a representative HUD,
 * rather than letting the hud-view fan overwrite them with the leg-start prefix's zeros. */
void bench_draw_frame(void) {
    bench_gobj_prefix();
    objlist.view_parity = pfx.view_parity;
    bench_build_geometry();
    scroll.seg_head = pose.seg_head;
    bench_render_road();
    bench_blit_scroll();
    object_stages();
    bench_draw_hud();
}

int main(void) { return 0; }        /* unused; present so os.s's `jsr main` links */
