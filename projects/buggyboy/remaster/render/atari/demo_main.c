/* demo_main.c — playable BuggyBoy on a real 68000, now the whole GAME SHELL (flow slice C).
 *
 * The demo is the game. main() composes the original's own outer loop (decomp.c main @0x10100) out of
 * remaster's ported pieces:
 *
 *   init_playfield (leg select) -> init_leg -> race-start frames -> the race loop -> on the leg end
 *   (abort_flag < 0): update_highscore -> game_over++ -> intermission (attract cycle) -> game_over = 0
 *   -> back to the leg select.
 *
 * The pieces:
 *   rm_player_update  (src/player.c)   — the driving model, dispatched through the course-event engine
 *   draw_frame        (below)          — the full ported render pipeline (geometry/road/scroll/objects/HUD)
 *   rm_init_leg       (src/gameplay.c) — a leg starts natively from the loaded assets
 *   rm_crash_fx_update(src/events.c)   — the end-of-race tally that ends a leg (abort_flag < 0)
 *   rm_update_highscore + the rm_int_* / rm_check_abort / rm_init_playfield_* flow (src/flow.c)
 *   rm_fade_step / rm_draw_intermission / rm_draw_leg_results (src/intermission.c, src/results.c)
 *
 * FlowState (include/flow.h) is the composition's owner — the attract/leg-select counters, the leg
 * selector, the idle countdown and the game-over flag — exactly as the host harness's _Candidate owns
 * the leg-drive structs. The off-image SEAMS the shell stands in for, each documented at its call site:
 *   - Sound: INITTUNE / INITFX / TURNOFF / the VBL vector / stop_music — never played.
 *   - Vsync pacing / the flip: the shell flips at the vblank; the original's exact frame cadence is off.
 *   - Palette fades: the flow's per-phase palettes are Setpalette'd (an off-image seam — the byte-compare
 *     is palette-agnostic); the 121-frame leg-start "get ready" palette FLASH is a plain frame wait.
 *   - The interactive high-score NAME-ENTRY tail: update_highscore ranks + inserts the score (the table
 *     fills in and the results screen shows it) but the IKBD initials screen is not run (recreate defers
 *     it too — it busy-polls the keyboard and the sound flag, never returning under the differential).
 *   - The attract DEMO's input-replay: the original plays a recorded ghost; here Phase C holds throttle
 *     (a documented stand-in) so the demo actually drives the course.
 *
 * BOOT / GOLDEN PARITY: run_demo.py byte-compares the FIRST painted frame (before any physics) to
 * recreate's pipeline on the leg-0 start (build/golden.bin). So the default boot takes a fast path: the
 * first outer-loop pass skips the leg select and starts leg DEMO_LEG_INDEX directly, drawing + dumping
 * that leg-start frame — byte-identical to today's demo. Only AFTER the first leg ends does the full
 * flow (highscore -> intermission -> leg select) run and close the loop. This is the "deterministic
 * first-race-frame" the task sanctions; it needs no build flag.
 *
 * Controls (held keys, read straight from the IKBD — see os.s):
 *   Up / Down    : throttle / brake      Left / Right : steer     Space : fire (dashboard variant)
 *   F1..F5       : select + start that leg (leg-select screen)     R : restart the leg
 *   Esc / Q      : quit
 * Assets come from the game's own COURSES.DAT + GRAPHICS.GRA, read off disk and unpacked by
 * src/assets.c. Only the original PROGRAM's own data-segment tables (fonts, colour pairs, layout
 * tables, the phase palettes, the object jump table) and two seeds (the intermission_poll control
 * table, the default hi-score table = init_scoretable's output) are baked by gen_demo_fixture.py.
 */
#include <stdint.h>
#include <string.h>          /* freestanding libc, defined in shim.c */

#include "assets.h"
#include "game.h"
#include "flow.h"
#include "screen.h"
#include "demo_fixture.h"
#include "demo_frame.h"

void rm_build_road_geometry(RoadPose *pose, const RoadSource *src, const CourseRing *ring,
                            uint8_t *ctrl, uint8_t *scanline);
void rm_render_road(const RoadInput *in, Framebuffer *fb);
void rm_scroll_prebuild(const uint8_t *playfield, uint8_t *shifted);
void rm_blit_road_scroll(ScrollState *s, const uint8_t *shifted, Framebuffer *fb);
void rm_road_course_advance(RoadPose *pose, CourseState *cs, CourseRing *ring,
                            const uint8_t *stream);
void rm_draw_hud(const HudState *s, const HudAssets *a, Framebuffer *fb);
void rm_gobj_prefix(GobjPrefixState *s, const GobjPrefixAssets *a);
void rm_player_update(PlayerState *p, const PlayerAssets *a, uint8_t *ctrl, RmEventCtx *ctx);
void rm_course_probe(RmEventCtx *c);
void rm_course_events(RmEventCtx *c);
void rm_crash_fx_update(RmEventCtx *c);
void rm_init_leg_dash(RmEventCtx *c);      /* rebuild the current leg's dashboard graphic + seed the marker (src/events.c) */
void rm_seed_leg_dash_marker(RmEventCtx *c); /* re-seed ONLY the dash marker (marker-only; src/events.c) */
void rm_init_leg(PlayerState *p, CourseState *cs, RoadPose *pose, ScrollState *scroll,
                 CourseRing *ring, EventState *ev, GobjPrefixState *gobj, SpriteState *sprite,
                 uint8_t *hud_text, int16_t *obj_shade, uint16_t *screen_offset,
                 const RmInitAssets *a, uint16_t leg);
void rm_draw_ground(const GroundState *s, const GroundAssets *a, Framebuffer *fb);
void rm_draw_fg_sprite(SpriteState *s, const SpriteAssets *a, Framebuffer *fb);
void rm_draw_buggy(SpriteState *s, const SpriteAssets *a, Framebuffer *fb);
void rm_draw_object(const ObjectInput *in, Framebuffer *fb);
void rm_draw_object_list(const ObjListCtx *c, const uint8_t *list, uint32_t list_off,
                         const uint8_t *flags, uint32_t flags_off,
                         uint16_t outer_rows_m1, uint16_t rec_off, uint16_t colour);

extern long Fcreate(const char *name, short attr);
extern long Fopen(const char *name, short mode);
extern long Fread(short handle, long count, void *buf);
extern long Fwrite(short handle, long count, void *buf);
extern long Fclose(short handle);
extern long Cconws(const char *s);
extern void Vsync(void);
extern long Setscreen(long logLoc, long physLoc, short rez);   /* flip the video base (latches at vblank) */
extern long Physbase(void);                                    /* current video base (to restore on exit) */
extern void Setpalette(const void *pal16);
extern long Setcolor(short idx, short color);                  /* color -1 reads a register without writing */
extern long Setexc(short number, long vector);
extern void Ikbdws(short count_m1, const void *buf);

/* Held-key state, maintained by the IKBD interrupt handler in os.s (indexed by scancode). */
extern volatile uint8_t key_down[128];
extern volatile uint8_t key_hit[128];
extern void kbd_isr(void);

/* Consume a latched key press. The driving keys are polled as HELD state, which is what steering and
 * throttle want, but a momentary key (quit, restart, an F-key) cannot be read that way: the loop polls
 * once per frame and a frame here is ~200 ms, so a quick tap's make AND break both land between two
 * polls and key_down is already back to 0 when it is read. key_hit is set by the interrupt on the make
 * and stays set until read here, so no press can be missed. */
static int take_key_hit(int scancode) {
    if (!key_hit[scancode]) return 0;
    key_hit[scancode] = 0;
    return 1;
}

/* ST keyboard scancodes. */
#define SCAN_ESC 0x01
#define SCAN_Q 0x10
#define SCAN_R 0x13
#define SCAN_SPACE 0x39
#define SCAN_UP 0x48
#define SCAN_DOWN 0x50
#define SCAN_LEFT 0x4b
#define SCAN_RIGHT 0x4d
#define SCAN_F1 0x3b              /* F1..F5 = 0x3b..0x3f: leg select (as init_playfield's function menu) */

/* Esc or Q, latched-edge: the shell's global quit. Polled once per frame in the race loop and every
 * menu/attract loop; each sets s->quit and unwinds so main's exit (screen + palette restore) still runs. */
static int quit_requested(void) { return take_key_hit(SCAN_ESC) || take_key_hit(SCAN_Q); }

#define VEC_IKBD_ACIA 0x46           /* 68000 vector 0x46 (@0x118): MFP channel 6, the IKBD ACIA */
#define IKBD_MOUSE_OFF 0x12
#define IKBD_JOYSTICK_OFF 0x1a
#define IKBD_MOUSE_RELATIVE 0x08     /* the mode TOS leaves the mouse in; restored on exit */

/* The prefix mutates its arenas (marker records, buf_a anim-word mirrors, the animated colour). The
 * anim-word mirrors land inside buf_a's record region (offsets 0xd70/0x1250), which the object
 * dispatcher then reads — so buf_a must be a MUTABLE copy of the fixture for the prefix write to be
 * seen by the draws, exactly as recreate's g_draw_game_objects does. The marker records + animated
 * colour are off-frame (this frame's marker slot is inactive), so they go to BSS scratch. */
static uint8_t ctrl[RM_CTRL_ALLOC_BYTES] __attribute__((aligned(2)));    /* BSS: per-frame control-long table */
static uint8_t scanline[RM_SCANLINE_BYTES] __attribute__((aligned(2)));  /* BSS: build_road_geometry scratch */
static uint8_t shifted[RM_SCROLL_SHIFTS * RM_SCROLL_WINDOW] __attribute__((aligned(2)));  /* pre-rotated scroll copies */
static uint8_t buf_a_ram[ARENA_BUF_A_BYTES] __attribute__((aligned(2)));  /* mutable buf_a copy (prefix writes mirrors) */
static uint8_t arena_block[RM_ARENA_BYTES] __attribute__((aligned(2)));   /* COURSES.DAT + unpacked GRAPHICS.GRA */
static uint8_t gobj_scratch[GOBJ_MARKER_RECS_BYTES] __attribute__((aligned(2)));  /* BSS: marker recs (inactive) */
/* The live ring serialized back into the original's flat ST-byte row grid — the object-list
 * dispatcher's two flag streams walk this (rebuilt after every course advance). The other ring
 * consumers (sprite count, ground markers, sprite gates) read the native CourseRing directly. */
static uint8_t ring_st[RM_RING_ROWS * RM_RING_ROW_BYTES] __attribute__((aligned(2)));
/* The prefix's animated colour aliases the HUD's phase-6a fuel-mask table in the original (both live
 * at 0x17f08): draw_game_objects' prefix writes the animated colour there, and draw_hud then reads it
 * as the fuel mask. Model that alias with one mutable buffer the prefix writes and the HUD reads. */
static uint8_t fuel_mask_ram[8] __attribute__((aligned(2)));
/* The shared HUD-text region as MUTABLE RAM: the course-event engine writes the score digits here on
 * a checkpoint/gate frame, draw_hud reads it as the template it copies, and update_highscore ranks the
 * 12-byte score record that lives at its tail (offset RM_HUD_SCORE_BCD_OFF). The original aliases one
 * region, so all three must see the same bytes. Seeded from fixture_hud_text at boot. */
static uint8_t hud_text_ram[sizeof fixture_hud_text] __attribute__((aligned(2)));
/* The persistent hi-score table as MUTABLE RAM: rm_update_highscore inserts a winning score, the
 * intermission draws it. Seeded at boot from fixture_highscore (init_scoretable's default table — its
 * deterministic output baked as program data, like fixture_hud_text; init_scoretable itself is not run
 * on-target). The score record update_highscore ranks is hud_text_ram + RM_HUD_SCORE_BCD_OFF. */
static uint8_t highscore_ram[sizeof fixture_highscore] __attribute__((aligned(2)));

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

/* ---- the game shell's single handle: pointers to every per-race owner struct, its render views, the
 * const asset bundles, the course-event context, the flow state + its draw asset bundles, and the
 * per-leg mutable pointers (stream / collision mask) the leg select repoints. One struct so the frame
 * step, the leg start and the flow phases take one argument instead of twenty. ---- */
typedef struct {
    RmArena *arena;
    /* per-race owner structs */
    PlayerState *player; CourseState *course; RoadPose *pose; ScrollState *scroll;
    CourseRing *ring; EventState *ev; GobjPrefixState *pfx; SpriteState *sprite;
    /* render views + their scalar outputs */
    GroundState *ground; ObjListCtx *objlist; ObjectInput *object; HudState *hud; RoadInput *road;
    int16_t *obj_shade; uint16_t *screen_offset;
    /* const asset bundles */
    const RoadSource *src; const HudAssets *hud_assets; const GobjPrefixAssets *pfx_assets;
    const GroundAssets *ground_assets; const SpriteAssets *sprite_assets;
    const PlayerAssets *player_assets; const RmInitAssets *init_assets;
    const uint8_t *low;                 /* the obj-low program-data blob base */
    EventAssets *event_assets;          /* MUTABLE: coll_mask is repointed per leg */
    RmEventCtx *ctx;                    /* MUTABLE: leg + the pointers above; shared by §6 + the wrap tail */
    const uint8_t *stream;              /* MUTABLE: the current leg's packed course record stream */
    uint16_t leg;                       /* the leg currently loaded */
    uint16_t race_input_prev;           /* previous frame's input (the fire-edge baseline for §3) */
    /* between-legs flow */
    FlowState *flow;
    const RmIntermissionAssets *int_assets;
    const RmResultsAssets *res_assets;  /* .leg is passed per-call, so one bundle covers all 5 legs */
    int shown;                          /* index of the on-screen buffer; the back buffer is shown ^ 1 */
    int quit;                           /* set when Esc/Q is seen in any loop; the outer loop unwinds + restores */
} Shell;

/* Re-derive every ring-owned view — the dispatcher's ST mirror, the ground markers, the sprite
 * gates — from the live ring. Must run wherever the ring changes: at seed, after every course
 * advance, and on a leg start (missing the last one leaves mid-course scenery on a reset road). */
static void ring_views_refresh(const CourseRing *ring, GroundState *ground, SpriteState *sprite) {
    rm_ring_store_st(ring, ring_st);
    rm_ring_ground_markers(ring, ground->markers);
    sprite->buggy_gate = rm_ring_buggy_gate(ring);
    sprite->fg_gate = rm_ring_fg_gate(ring);
}

/* Run the full ported render pipeline into `fb`, in draw_game_objects order: prefix (off-frame state),
 * geometry + road + scroll band, then the object tree (ground, foreground sprite, the two sprite
 * object-list passes split around draw_object, and the buggy ordered against the fixed pass by the
 * view), then the HUD. The scroll advances every frame; the prefix advances view_parity/anim. */
static void draw_frame(const Shell *s, Framebuffer *fb) {
    GobjPrefixState *pfx = s->pfx;
    ObjListCtx *objlist = s->objlist;
    RoadInput *road = s->road;
    const uint8_t *low = s->low;

    rm_gobj_prefix(pfx, s->pfx_assets);              /* off-frame: advance view_parity/anim/marker */
    objlist->view_parity = pfx->view_parity;         /* the dispatcher (handler_lo) reads the advanced parity */
    objlist->px = fb->px;                            /* the dispatcher's draw target: this frame's buffer */
    rm_build_road_geometry(s->pose, s->src, s->ring, ctrl, scanline);
    road->width_tbl = ctrl + RM_CTRL_WIDTH_OFF;
    /* The object dispatcher's per-row x-offset table aliases the freshly-built road control table in
     * the original (obj_xoff_tbl == road_width_tbl + 2), so rebind it to this frame's ctrl. */
    objlist->xoff_tbl = ctrl + RM_CTRL_WIDTH_OFF + 2;
    s->scroll->seg_head = s->pose->seg_head;         /* the scroll step follows the near slope */
    /* No per-frame clear: the pipeline below repaints every visible byte (blit_road_scroll's fill +
     * band, render_road, the ground/object tree, then the HUD), so drawing over this buffer's
     * two-frames-old content is byte-identical to drawing over zeros. The buffers are cleared once in
     * main() to establish that invariant. Verified byte-exact against a per-frame-clear build. */
    rm_render_road(road, fb);
    rm_blit_road_scroll(s->scroll, shifted, fb);

    /* --- draw_game_objects tree ---
     * DEMO_DUMP_STAGE (debug builds only) cuts the frame short after a chosen stage, so the normal
     * SCREEN.BIN dump yields a partial frame and a headless run can pinpoint the first stage whose
     * on-target output diverges from the host reference. Undefined in normal builds. */
#if defined(DEMO_DUMP_STAGE) && DEMO_DUMP_STAGE == 0
    return;
#endif
    rm_draw_ground(s->ground, s->ground_assets, fb);
#if defined(DEMO_DUMP_STAGE) && DEMO_DUMP_STAGE == 1
    return;
#endif
    rm_draw_fg_sprite(s->sprite, s->sprite_assets, fb);
#if defined(DEMO_DUMP_STAGE) && DEMO_DUMP_STAGE == 2
    return;
#endif

    /* The dispatcher's flag streams and the pass split all come from the LIVE ring: the sprite
     * passes walk the serialized grid from row 1, the fixed pass from row 12 — the same aliasing
     * the original gets from pointing into its flat row grid. */
    int count = rm_ring_sprite_count(s->ring);
    if (count - 1 >= 0)                               /* pass 1: the active sprite rows */
        rm_draw_object_list(objlist, low + OBJ_LOW_SPRITE_DISP, 0, ring_st + GOBJ_SPRITE_PASS_ROW * RM_RING_ROW_BYTES, 0,
                            (uint16_t)(count - 1), GOBJ_D6_INIT, (uint16_t)count);
#if defined(DEMO_DUMP_STAGE) && DEMO_DUMP_STAGE == 3
    return;
#endif
    rm_draw_object(s->object, fb);
    if (GOBJ_SPRITE_LAST - count >= 0)               /* pass 2: the remaining rows */
        rm_draw_object_list(objlist,
                            low + OBJ_LOW_SPRITE_DISP, (uint16_t)(count * GOBJ_ROW_A5_STRIDE),
                            ring_st + GOBJ_SPRITE_PASS_ROW * RM_RING_ROW_BYTES, (uint16_t)(count * GOBJ_ROW_A3_STRIDE),
                            (uint16_t)(GOBJ_SPRITE_LAST - count),
                            (uint16_t)(GOBJ_D6_INIT - count * GOBJ_D6_ROW_STEP), 0);
    if ((objlist->view_flags & GOBJ_VIEW_REAR) == 0) {   /* pass 3 (fixed) + buggy, view-ordered */
        rm_draw_object_list(objlist, low + OBJ_LOW_LIST_BASE, 0,
                            ring_st + GOBJ_FIXED_PASS_ROW * RM_RING_ROW_BYTES, 0, 0, 0, 0);
        rm_draw_buggy(s->sprite, s->sprite_assets, fb);
    } else {
        rm_draw_buggy(s->sprite, s->sprite_assets, fb);
        rm_draw_object_list(objlist, low + OBJ_LOW_LIST_BASE, 0,
                            ring_st + GOBJ_FIXED_PASS_ROW * RM_RING_ROW_BYTES, 0, 0, 0, 0);
    }

    rm_draw_hud(s->hud, s->hud_assets, fb);
}

/* Fan rm_player_update's outputs out to the render structs — the whole of the "game loop" beyond
 * running the physics and drawing. Each assignment is one of the original's shared globals: the
 * pose's curve/view come straight from the physics, the sprite reads the body pose (skid doubles as
 * the foreground-sprite suppressor, exactly as in the original), the ground column and the object
 * list's scan offset are the same global, and the HUD shows the speed and clock. */
static void apply_player(const Shell *s) {
    const PlayerState *p = s->player;
    RoadPose *pose = s->pose;
    SpriteState *sprite = s->sprite;
    HudState *hud = s->hud;
    ObjListCtx *objlist = s->objlist;
    const EventState *ev = s->ev;

    pose->curve = p->road_curve;
    pose->view_flags = p->view_flags;
    s->road->edge_tbl = fixture_road_edge + ROAD_EDGE_PAD + p->road_edge_sel;
    s->scroll->scroll_speed = p->scroll_speed;

    sprite->lean = p->lean;
    sprite->pitch = p->buggy_pitch_off;      /* the crash script's body bounce */
    sprite->wheel_pos = p->wheel_pos;
    sprite->skid = p->skid;
    sprite->sprite_suppress = (uint16_t)p->skid;
    sprite->crash_disp = p->crash_disp;
    sprite->buggy_draw_flag = p->buggy_draw_flag;
    sprite->speed_raw = p->speed_raw;
    sprite->road_curve = p->road_curve;

    s->ground->view = p->ground_view_off;
    objlist->view_flags = p->view_flags;
    objlist->obj_scan_off = p->ground_view_off;

    hud->speed = p->speed;
    hud->time_left = (uint16_t)p->time_left;
    hud->dsp_variant_idx = p->dsp_variant_idx;
    hud->hud_crash_timer = p->hud_crash_timer;

    /* The six HUD scalars EventState OWNS (see game.h ownership contract): the draw's per-frame VIEW,
     * refreshed from the event engine each frame exactly as speed/time are from the physics. */
    hud->crash_lap = (int16_t)ev->crash_lap;
    hud->gauge_blink = ev->gauge_blink;
    hud->gauge_blink_on = ev->gauge_blink_on != 0;
    hud->crash_active = ev->crash_active != 0;
    hud->crash_bars = ev->crash_bars;
    hud->crash_frame = (int16_t)ev->crash_frame;
}

/* Point the shell at leg `leg`'s per-leg data: the packed course stream (rm_road_course_advance reads
 * it), the collision-flag mask (the event engine), and the event context's leg (init_leg_dash / the
 * dispatch / the coll_mask window all key off it). buf_a is arena.tables; the offsets are the same
 * arithmetic recreate uses (leg * stride + a base). */
static void bind_leg(Shell *s, uint16_t leg) {
    uint32_t leg_off = (uint32_t)leg * COURSE_LEG_STRIDE;
    s->stream = s->arena->tables + leg_off + ARENA_COURSE_STREAM_BASE;
    s->event_assets->coll_mask = s->arena->tables + leg_off + ARENA_COURSE_MASK_BASE;
    s->ctx->leg = leg;
    s->leg = leg;
}

/* Start (or restart) leg `leg` NATIVELY: bind its per-leg data, reset every per-leg OWNER struct to its
 * leg-start value through rm_init_leg (recreate's init_leg — no baked *_INIT snapshot), pre-rotate the
 * scroll playfield for this leg's screen_offset, then derive every render VIEW exactly as a driving
 * frame does (the two scalars with no owner field, the object-list counters, apply_player,
 * ring_views_refresh). Used at boot, on R, on the leg-select fire, and by the attract Phase-B warm-up. */
static void start_leg(Shell *s, uint16_t leg) {
    bind_leg(s, leg);
    *s->player = (PlayerState){0};
    *s->course = (CourseState){0};
    *s->pose = (RoadPose){0};
    *s->scroll = (ScrollState){0};
    *s->ring = (CourseRing){0};
    *s->ev = (EventState){0};
    *s->pfx = (GobjPrefixState){0};
    *s->sprite = (SpriteState){0};
    for (unsigned i = 0; i < sizeof fixture_hud_text; i++) hud_text_ram[i] = fixture_hud_text[i];
    /* Re-seed the dash marker into the freshly-zeroed EventState (rm_init_leg preserves, never seeds it),
     * so no race entry — boot, the leg-select fire, R, the attract warm-up — drives with a (0,0)
     * collision-probe origin. Marker only, NOT the dashboard graphic: the marker feeds the event-path
     * collision probe on later wrap frames, never the pre-physics boot draw, so the frame-0 golden holds;
     * the graphic is already loaded for the current leg (boot's stock arena / the leg-select rebuild) and
     * is rebuilt where the leg changes (run_leg_select's gate, Phase B). */
    rm_seed_leg_dash_marker(s->ctx);
    rm_init_leg(s->player, s->course, s->pose, s->scroll, s->ring, s->ev, s->pfx, s->sprite,
                hud_text_ram, s->obj_shade, s->screen_offset, s->init_assets, leg);
#ifdef DEMO_TIME_LEFT
    /* Debug builds only: shorten the leg's bonus clock so a headless idle trace reaches the time-out
     * (and thus the leg end) in ~140 frames instead of ~800. A restart re-seeds the FULL clock from
     * rm_init_leg first, so a restart shows time_left jumping back up before this shortens it again. */
    s->player->time_left = DEMO_TIME_LEFT;
#endif
    rm_scroll_prebuild(s->arena->gfx + *s->screen_offset, shifted);   /* screen_offset is per-leg */
    s->object->shade = *s->obj_shade;
    s->objlist->bonus_timer = s->pfx->bonus_timer;                    /* the bonus clamp follows the prefix */
    s->objlist->p24_flag = hud_text_ram[RM_HUD_SCORE_STR_OFF + 1];    /* the live score_str[1] rm_init_leg wrote */
    apply_player(s);
    ring_views_refresh(s->ring, s->ground, s->sprite);
    s->race_input_prev = 0;
    /* The race palette, set in ONE place so every race entry (boot / leg-select fire / R / attract
     * Phase B) agrees. INT_PAL_B == the race palette == fixture_palette (0x17fa2); an off-image seam
     * (the byte-compare is palette-agnostic). */
    Setpalette(fixture_palette);
}

/* One race-frame UPDATE (no draw): run the driving model over the geometry the last frame built,
 * advance the course on a view-wrap (the same order as recreate's game_update.c §12), then the crash
 * / end-of-race tally. Returns 1 when the leg ENDS (abort_flag < 0), else 0. The caller draws + flips.
 * The wrap-frame block mirrors demo_main's original inline body one-for-one. */
static int game_update_step(Shell *s, uint16_t input) {
    PlayerState *player = s->player;

    /* hscroll_step2 is blit_road_scroll's output feeding back in — the scroll biases the curve.
     * input_prev is the previous frame's bits, which makes fire a true edge (one dashboard cycle per
     * press). */
    player->input_prev = s->race_input_prev;
    player->input = input;
    player->hscroll_step2 = (int16_t)s->scroll->hscroll_step2;
    s->race_input_prev = input;
    rm_player_update(player, s->player_assets, ctrl, s->ctx);

    /* Sync the pose/scroll the wrap-frame build reads BEFORE it runs (apply_player re-syncs after the
     * event tail, so a bonus-record curve kick reaches the render). */
    s->pose->curve = player->road_curve;
    s->pose->view_flags = player->view_flags;
    s->scroll->scroll_speed = player->scroll_speed;

    /* The view wrapping is what advances the course, so the road's bends arrive at the speed the buggy
     * is travelling (section 12). Order mirrors recreate game_update.c §12: clear event_pending (504),
     * the collision-probe head, the ring + segment scroll, the geometry rebuild (so horizon_row is
     * fresh for the event tail, 570/608), then the fx / horizon-event dispatch (611) — which arms
     * crashes + delivers checkpoint/finish/bonus records and pokes ring bands 11-13, so every
     * ring-derived view is refreshed after it (or the scenery freezes while the road animates). */
    if (player->view_wrapped) {
        player->event_pending = 0;
        rm_course_probe(s->ctx);
        rm_road_course_advance(s->pose, s->course, s->ring, s->stream);
        rm_build_road_geometry(s->pose, s->src, s->ring, ctrl, scanline);
        rm_course_events(s->ctx);
        ring_views_refresh(s->ring, s->ground, s->sprite);
    }

    /* HUD phase 8's STATE side (draw_crash_fx @0x15872): decay the crash-arm timer, or once it goes
     * negative run the leg-end tally — drain the bonus time / units / score-digit rollovers into the
     * score and arm abort_flag. Runs before apply_player so the drawn HUD reflects this frame's tally
     * through the six EventState -> HudState view fields. */
    rm_crash_fx_update(s->ctx);
    int ended = (int16_t)s->ev->abort_flag < 0;    /* abort_flag < 0 is the leg end (main @0x10100:286) */

    apply_player(s);
    return ended;
}

/* The back (off-screen) buffer a caller paints into before showing it. Pairs with show_surface, which
 * flips to this same buffer and advances s->shown. */
static Framebuffer *back_buffer(const Shell *s) { return screen_buf(s->shown ^ 1); }

/* Flip the video base to the back buffer at the vblank (no tearing) and make it the shown one. Callers
 * paint the back buffer (via back_buffer / draw_frame) first; this owns the flip + the shown toggle so
 * no caller repeats the derive-toggle bookkeeping. */
static void show_surface(Shell *s) {
    Framebuffer *fb = screen_buf(s->shown ^ 1);
    Setscreen(-1L, (long)fb->px, -1);
    Vsync();
    s->shown ^= 1;
}

/* Render the race pipeline into the back buffer and show it (draw_frame + show_surface). */
static void render_and_show(Shell *s) {
    draw_frame(s, back_buffer(s));
    show_surface(s);
}

/* ---- the between-legs flow palettes (all inside the obj-low program-data blob; an off-image seam —
 * the byte-compare is palette-agnostic, so these only affect the colours a human/screenshot sees). ---- */
static void set_palette(const Shell *s, uint32_t off) { Setpalette(s->low + off); }

/* Take the IKBD interrupt so held keys are visible (see os.s). Mouse and joystick reporting are
 * switched off first, which is what leaves the ACIA delivering keyboard scancodes only. */
static long kbd_install(void) {
    static const uint8_t quiet[] = {IKBD_MOUSE_OFF, IKBD_JOYSTICK_OFF};
    Ikbdws(sizeof quiet - 1, quiet);
    return Setexc(VEC_IKBD_ACIA, (long)kbd_isr);
}

static void kbd_remove(long old_vector) {
    static const uint8_t restore[] = {IKBD_MOUSE_RELATIVE};
    Setexc(VEC_IKBD_ACIA, old_vector);
    Ikbdws(sizeof restore - 1, restore);
}

static uint16_t read_input(void) {
    uint16_t in = 0;
    if (key_down[SCAN_UP]) in |= RM_IN_ACCEL;
    if (key_down[SCAN_DOWN]) in |= RM_IN_BRAKE;
    if (key_down[SCAN_LEFT]) in |= RM_IN_LEFT;
    if (key_down[SCAN_RIGHT]) in |= RM_IN_RIGHT;
    if (key_down[SCAN_SPACE]) in |= RM_IN_FIRE;
    return in;
}

__attribute__((unused)) static void dump_frame(Framebuffer *fb) {
    long h = Fcreate("SCREEN.BIN", 0);
    if (h >= 0) { Fwrite((short)h, SCREEN_BYTES, fb->px); Fclose((short)h); }
}

/* ---- headless drive + trace (debug builds only) --------------------------------------------------
 *
 * DEMO_AUTODRIVE=N drives a fixed script instead of the keyboard and dumps the frame after N frames;
 * DEMO_TRACE=N logs N frames of driving state to SCREEN.BIN instead. DEMO_FLOW_TRACE adds a compact
 * PHASE-transition log so a headless run can prove the between-legs flow (leg end -> highscore ->
 * intermission A->B->C->D -> leg select -> fire -> leg) runs on the 68000, and DEMO_FLOW_FAST shrinks
 * the attract phases so a whole cycle fits a bounded run (the phase counts are otherwise thousands of
 * frames). DEMO_FLOW_AUTO scripts the flow inputs (auto-fire the leg select, auto-abort the attract).
 */
#ifdef DEMO_AUTODRIVE
#ifndef AUTODRIVE_STEER_AFTER
#define AUTODRIVE_STEER_AFTER 60         /* throttle up first, then hold a steering lock */
#endif
/* The base bits held every frame. Default is throttle (drive the course). Set to 0 (with a large
 * AUTODRIVE_STEER_AFTER) to IDLE the buggy, which is what a leg-end time-out trace needs. */
#ifndef AUTODRIVE_BASE_INPUT
#define AUTODRIVE_BASE_INPUT RM_IN_ACCEL
#endif
static uint16_t autodrive_input(int frame) {
    return (uint16_t)(AUTODRIVE_BASE_INPUT | (frame < AUTODRIVE_STEER_AFTER ? 0 : RM_IN_LEFT));
}
#endif

#ifdef DEMO_TRACE
#define TRACE_WORDS 9
/* Round UP so the dump is >= SCREEN_BYTES whatever TRACE_WORDS is; never fewer slots than DEMO_TRACE. */
#define TRACE_MIN_SLOTS ((SCREEN_BYTES + TRACE_WORDS * 2 - 1) / (TRACE_WORDS * 2))
#define TRACE_SLOTS (DEMO_TRACE > TRACE_MIN_SLOTS ? DEMO_TRACE : TRACE_MIN_SLOTS)
static uint16_t trace_log[TRACE_SLOTS][TRACE_WORDS];

static void trace_frame(int frame, const PlayerState *p, const EventState *e, const CourseState *c) {
    if (frame >= TRACE_SLOTS) return;
    uint16_t *rec = trace_log[frame];
    rec[0] = (uint16_t)frame;
    rec[1] = c->read_pos;
    rec[2] = c->row_ctr;
    rec[3] = p->speed;
    rec[4] = p->engine_rpm;
    rec[5] = p->collision_lock;
    rec[6] = (uint16_t)p->hud_crash_timer;
    rec[7] = (uint16_t)(p->view_wrapped ? 1 : 0);
    rec[8] = e->abort_flag;      /* leg-end countdown: < 0 (0x8000..0xffff) ends the leg */
}

static void trace_dump(void) {
    long h = Fcreate("SCREEN.BIN", 0);
    if (h >= 0) { Fwrite((short)h, (long)sizeof trace_log, trace_log); Fclose((short)h); }
}
#endif

#ifdef DEMO_FLOW_TRACE
/* One phase-transition record per event: (tag, leg, aux) — the aux carries a phase-specific scalar
 * (Phase-A/C frame count, the leg select's leg, etc.). Written to SCREEN.BIN on quit. The tags below are
 * the between-legs flow's boundaries; a headless run reads them back to confirm A->B->C->D->restart,
 * the leg-select fire, and the leg-end -> intermission -> leg-select round trip. */
enum { FT_LEG_START = 1, FT_LEG_END, FT_HISCORE, FT_INT_PROLOGUE, FT_INT_PHASEA_BREAK, FT_INT_PHASEB,
       FT_INT_PHASEC_DONE, FT_INT_PHASED_ADVANCE, FT_INT_PHASED_RESTART, FT_INT_ABORT,
       FT_SELECT_ENTER, FT_SELECT_FIRE, FT_SELECT_IDLE };
#define FLOW_TRACE_SLOTS 256
static uint16_t flow_trace[FLOW_TRACE_SLOTS][3];
static uint16_t flow_trace_pos;

static void flow_event(uint16_t tag, uint16_t leg, uint16_t aux) {
    if (flow_trace_pos >= FLOW_TRACE_SLOTS) return;
    flow_trace[flow_trace_pos][0] = tag;
    flow_trace[flow_trace_pos][1] = leg;
    flow_trace[flow_trace_pos][2] = aux;
    flow_trace_pos++;
}

/* Dump the phase log to SCREEN.BIN (padded to a full framebuffer so the standard headless runner picks
 * it up unchanged — it waits for SCREEN_BYTES): word 0 = the record count, then the (tag, leg, aux)
 * triples. It is telemetry, not an image. */
static void flow_trace_dump(void) {
    uint8_t *buf = screen_buf(0)->px;
    memset(buf, 0, SCREEN_BYTES);
    uint16_t *w = (uint16_t *)buf;
    w[0] = flow_trace_pos;
    for (int i = 0; i < flow_trace_pos && (i * 3 + 4) * 2 <= SCREEN_BYTES; i++) {
        w[1 + i * 3 + 0] = flow_trace[i][0];
        w[1 + i * 3 + 1] = flow_trace[i][1];
        w[1 + i * 3 + 2] = flow_trace[i][2];
    }
    long h = Fcreate("SCREEN.BIN", 0);
    if (h >= 0) { Fwrite((short)h, SCREEN_BYTES, buf); Fclose((short)h); }
}
#else
#define flow_event(tag, leg, aux) ((void)0)
#endif

/* Read a file into `dst`, at most `max` bytes. Returns the byte count, or -1 if it won't open.
 * The handle test is `<= 0`, not `< 0`: handle 0 is a failure this project has hit (see os.s). */
#define FOPEN_READ_ONLY 0
static long read_file(const char *name, uint8_t *dst, long max) {
    long handle = Fopen(name, FOPEN_READ_ONLY);
    if (handle <= 0) return -1;
    long got = Fread((short)handle, max, dst);
    Fclose((short)handle);
    return got;
}

/* Load the game's own data files and unpack the graphics — everything the render pipeline draws from.
 * Both must sit next to the .PRG. Returns 0 after naming the file at fault (Cconws is invisible under
 * headless Hatari, so the only symptom there is a missing SCREEN.BIN). */
static int load_assets(RmArena *arena) {
    rm_arena_init(arena, arena_block);
    if (read_file("COURSES.DAT", arena->course, RM_COURSE_FILE_BYTES) != RM_COURSE_FILE_BYTES) {
        Cconws("COURSES.DAT missing or wrong size\r\n");
        return 0;
    }
    long gfx_bytes = read_file("GRAPHICS.GRA", arena->gfx + RM_GFX_LOAD_OFF, RM_GFX_READ_MAX);
    if (gfx_bytes < RM_GFX_FILE_MIN) {
        Cconws("GRAPHICS.GRA missing or too short\r\n");
        return 0;
    }
    if (!rm_assets_unpack(arena, (uint32_t)gfx_bytes)) {
        Cconws("GRAPHICS.GRA is corrupt (unpack failed)\r\n");
        return 0;
    }
    return 1;
}

/* ---- the between-legs flow (recreate intermission.c: intermission @0x127a0 / init_playfield @0x12af6).
 * The counter arithmetic lives in flow.c (rm_int_stepA / _phaseB_leg / _stepD_counter / check_abort /
 * init_playfield_nav / _fire); the COMPOSITION — the prologue, the phase loop, the draws, the palettes
 * and the seams — is here, mirroring g_intermission / g_init_playfield structure-for-structure. ---- */

/* Feed this frame's input into the flow's scripted-input snapshots (the IKBD poll is the seam): the
 * baseline becomes last frame's live bits, the live bits become this frame's. rm_check_abort /
 * rm_init_playfield_fire compare the two. */
static void flow_poll_input(Shell *s, uint16_t input) {
    s->flow->input_prev = s->flow->input_state;
    s->flow->input_state = input;
}

/* Phase-C demo length + Phase-B warm-up (intermission's own composition constants; flow.h pins the
 * counter-owned ones). {INT_B_RPM_CAP, INT_B_RPM_ADD} = the original's leg_flags_c90 = 0x5a0001,
 * seeding the demo leg's {rpm_cap, rpm_add}. */
#define INT_B_WARMUP   0x33        /* Phase-B settle: game_update iterations before the first draw */
#define INT_B_RPM_CAP  0x5a        /* leg_flags_c90 high word (rev cap for the attract demo) */
#define INT_B_RPM_ADD  0x0001      /* leg_flags_c90 low word (throttle step) */
#ifdef DEMO_FLOW_FAST
#define FLOW_PHASE_C_FRAMES 6      /* debug: a handful of demo frames instead of INT_C_FRAMES (0x96) */
#define IP_IDLE_INIT_SHELL  8      /* debug: short leg-select idle so the attract path is reachable */
#else
#define FLOW_PHASE_C_FRAMES INT_C_FRAMES
#define IP_IDLE_INIT_SHELL  0x15e  /* the original's IP_IDLE_INIT (350-frame attract delay) */
#endif
/* The attract demo's input: the original replays a recorded ghost drive (unported); here we hold
 * throttle so the demo actually covers the course. Documented stand-in (see the file header). */
#define ATTRACT_DEMO_INPUT RM_IN_ACCEL

#ifdef DEMO_FLOW_AUTO
static int auto_cycle_done;         /* set by Phase D's RESTART; the attract input aborts after it */
#endif

/* One attract cycle (g_intermission's for-body): prologue, Phase A (scrolling hi-score screen), Phase B
 * (warm up the next demo leg), Phase C (play the demo), Phase D (results carousel). Returns 1 on a
 * player ABORT (check_abort) — the caller stops the attract loop — else 0 to run another cycle.
 * `input_of` supplies each frame's input (scripted headless / the keyboard interactively). */
static int intermission_cycle(Shell *s, uint16_t (*input_of)(void)) {
    FlowState *fs = s->flow;

    /* prologue (0x27a0): seed the animation counters, paint two backdrop frames, load the A palette. */
#ifdef DEMO_FLOW_FAST
    /* Break Phase A in ~2 frames: seed the timer already inside the scroll gate window and the
     * scroll/dwell at the edge, so the underflow fires at once (the real seeds are thousands of frames). */
    fs->int_scroll = 1; fs->int_frame = 0; fs->int_timer = INT_SCROLL_GATE + 2;
#else
    fs->int_scroll = INT_SCROLL_INIT; fs->int_frame = INT_FRAME_INIT; fs->int_timer = INT_TIMER_INIT;
#endif
    flow_event(FT_INT_PROLOGUE, s->leg, (uint16_t)fs->int_scroll);
    rm_fade_step(back_buffer(s), s->int_assets, fs->int_scroll);
    set_palette(s, OBJ_LOW_PAL_INT_A);
    show_surface(s);
    rm_fade_step(back_buffer(s), s->int_assets, fs->int_scroll);
    show_surface(s);

    /* Phase A (0x27cc): scroll the hi-score/credits screen until the dwell counter runs out. The draw
     * happens for CONTINUE and ABORT (the abort frame still draws); BREAK returns before any draw. */
    for (;;) {
        if (quit_requested()) { s->quit = 1; return 1; }
        flow_poll_input(s, input_of());
        int a = rm_int_stepA(fs);
        if (a == RM_INT_A_BREAK) break;
        rm_draw_intermission(back_buffer(s), s->int_assets, fs->int_scroll);
        show_surface(s);
        if (a == RM_INT_A_ABORT) { flow_event(FT_INT_ABORT, s->leg, 0); return 1; }
    }
    flow_event(FT_INT_PHASEA_BREAK, s->leg, (uint16_t)fs->int_frame);

    /* Phase B (0x27fe): pick + (re)init the next demo leg, settle it, paint the first frame. start_leg
     * reseeds every owner struct via init_leg (+ the dash marker + the race palette); rm_init_leg_dash
     * then rebuilds the DASHBOARD GRAPHIC for the newly-picked demo leg, which start_leg's marker-only
     * seed does not (the previous phase left a different leg's dashboard loaded). The 0x5a0001 leg_flags
     * override sets the demo's engine limits; the leg_flags_sel / dsp_toggle tweaks the original also
     * does are attract-feel only (off-image). */
    rm_int_phaseB_leg(fs);
    flow_event(FT_INT_PHASEB, fs->leg_index, 0);
    start_leg(s, fs->leg_index);
    rm_init_leg_dash(s->ctx);
    s->player->rpm_cap = INT_B_RPM_CAP;
    s->player->rpm_add = INT_B_RPM_ADD;
    for (int i = 0; i < INT_B_WARMUP; i++) game_update_step(s, ATTRACT_DEMO_INPUT);   /* settle, no draw */
    render_and_show(s);
    render_and_show(s);

    /* Phase C (0x285e): play the demo for FLOW_PHASE_C_FRAMES frames (full render each frame). The
     * leg-end tally may fire during the demo — it is ignored here (the attract exits on the frame count
     * or check_abort, never abort_flag), exactly as recreate's Phase C ignores it. */
    fs->int_frame_hi = 0; fs->int_frame = 0;
    for (;;) {
        game_update_step(s, ATTRACT_DEMO_INPUT);
        render_and_show(s);
        uint16_t f = (uint16_t)(fs->int_frame + 1);
        fs->int_frame = (int16_t)f;
        if ((int16_t)(f - FLOW_PHASE_C_FRAMES) >= 0) break;
        if (quit_requested()) { s->quit = 1; return 1; }
        flow_poll_input(s, input_of());
        if (rm_check_abort(fs->input_state, fs->input_prev)) { flow_event(FT_INT_ABORT, s->leg, 1); return 1; }
    }
    flow_event(FT_INT_PHASEC_DONE, s->leg, FLOW_PHASE_C_FRAMES);

    /* Phase D (0x2894): results carousel — cycle draw_leg_results across the legs, INT_D_DWELL each. */
    fs->leg_index = 0;
    s->ctx->leg = 0;
    rm_init_leg_dash(s->ctx);   /* rebuild leg 0's dashboard for the carousel's first frame */
    rm_draw_leg_results(back_buffer(s), s->res_assets, fs->leg_index);
    set_palette(s, OBJ_LOW_PAL_LEG_SELECT);   /* Phase-D palette == INT_PAL_D == the leg-select palette */
    show_surface(s);
    for (;;) {
        int d = rm_int_stepD_counter(fs);
        if (d == RM_INT_D_RESTART) {
            flow_event(FT_INT_PHASED_RESTART, fs->leg_index, 0);
#ifdef DEMO_FLOW_AUTO
            auto_cycle_done = 1;        /* the next cycle's Phase A will now see a fresh key and abort */
#endif
            break;
        }
        if (d == RM_INT_D_ADVANCE) {
            s->ctx->leg = fs->leg_index;
            rm_init_leg_dash(s->ctx);           /* host runs init_leg_dash on the leg advance */
            flow_event(FT_INT_PHASED_ADVANCE, fs->leg_index, 0);
        }
        rm_draw_leg_results(back_buffer(s), s->res_assets, fs->leg_index);
        show_surface(s);
        if (quit_requested()) { s->quit = 1; return 1; }
        flow_poll_input(s, input_of());
        if (rm_check_abort(fs->input_state, fs->input_prev)) { flow_event(FT_INT_ABORT, s->leg, 2); return 1; }
    }
    return 0;   /* cycle done -> the caller runs another prologue */
}

/* g_intermission: run attract cycles until the player aborts (or, headless, the caller's input scripts
 * an abort; or Esc/Q sets s->quit). */
static void run_intermission(Shell *s, uint16_t (*input_of)(void)) {
    while (!s->quit && !intermission_cycle(s, input_of)) { }
}

/* g_init_playfield's leg-select loop (0x2af6): show the leg-results screen, let the player pick a leg
 * (nav) and start it (fire, or an F1..F5 direct pick), and on the idle-countdown expiry run one attract
 * cycle and restart. Returns with fs->leg_index = the chosen leg once a leg is started (or on Esc/Q with
 * s->quit set). `input_of` supplies the joystick bits; `fkey_leg` returns 0..4 for a direct F-key pick
 * this frame, or -1. The draw_panel5 selector overlay is an unported sub-draw (an off-image seam); the
 * results screen still shows the selected leg. */
static void run_leg_select(Shell *s, uint16_t (*input_of)(void), int (*fkey_leg)(void)) {
    FlowState *fs = s->flow;
    flow_event(FT_SELECT_ENTER, fs->leg_index, 0);
    for (;;) {                                      /* outer loop: redraws + idle-timeout intermission */
        uint16_t drawn_leg = 0xffff;                /* != any leg (0..4): forces a dash rebuild on entry */
        fs->idle_countdown = IP_IDLE_INIT_SHELL;

        for (;;) {                                  /* per-frame loop (0x2b1a) */
            int fk = fkey_leg();
            if (fk >= 0) { fs->leg_index = (uint16_t)fk; flow_event(FT_SELECT_FIRE, fs->leg_index, 1); return; }

            /* Rebuild the dashboard only when the selected leg changed (as Phase D rebuilds only on an
             * INT_D_ADVANCE), not every idle frame — the graphic is identical between nav steps. */
            if (fs->leg_index != drawn_leg) {
                drawn_leg = fs->leg_index;
                s->ctx->leg = fs->leg_index;
                rm_init_leg_dash(s->ctx);
            }
            rm_draw_leg_results(back_buffer(s), s->res_assets, fs->leg_index);   /* default redraw (0x2b9e) */
            set_palette(s, OBJ_LOW_PAL_LEG_SELECT);
            show_surface(s);

            flow_poll_input(s, input_of());         /* joystick tail (0x2c00) */
            rm_init_playfield_nav(fs);
            if (rm_init_playfield_fire(fs)) { flow_event(FT_SELECT_FIRE, fs->leg_index, 0); return; }
            if (quit_requested()) { s->quit = 1; return; }

            int16_t next = (int16_t)(fs->idle_countdown - 1);   /* dbf (0x2c78) */
            if (next < 0) break;                    /* countdown expired -> attract cycle */
            fs->idle_countdown = (uint16_t)next;
        }
        flow_event(FT_SELECT_IDLE, fs->leg_index, 0);
        rm_flow_game_over_enter(fs);
        run_intermission(s, input_of);
        rm_flow_game_over_exit(fs);
        if (s->quit) return;
    }
}

/* Interactive leg-select input sources. read_fkey returns 0..4 for an F1..F5 tap (a direct leg pick,
 * as the original's function-key menu), or -1 for none; no_fkey is the headless placeholder. Each is
 * used by exactly one build config (interactive vs DEMO_FLOW_AUTO), so both are marked maybe-unused. */
__attribute__((unused)) static int read_fkey(void) {
    for (int i = 0; i < 5; i++) if (take_key_hit(SCAN_F1 + i)) return i;
    return -1;
}
__attribute__((unused)) static int no_fkey(void) { return -1; }

/* ---- headless flow scripting (DEMO_FLOW_AUTO): drive the whole shell without a keyboard so a trace
 * run proves the loop closes. The leg select auto-fires after a few frames; the intermission runs one
 * cycle then aborts (a fresh input the second time check_abort sees it). ---- */
#ifdef DEMO_FLOW_AUTO
#define FLOW_AUTO_RACE_CAP 4          /* the post-leg-select race runs this many frames, then the run quits */
static int auto_select_frame;
static uint16_t auto_select_input(void) {
    /* Idle a few frames (so the fire edge is a true 0->1 transition), then hold fire — a fresh fire
     * press starts the currently-selected leg (rm_init_playfield_fire). */
    return (uint16_t)(auto_select_frame++ >= 3 ? RM_IN_FIRE : 0);
}
static uint16_t auto_intermission_input(void) {
    /* Idle so Phase A/B/C/D run to completion; once a full cycle has traced its RESTART, present a
     * fresh key so check_abort fires in the next cycle's Phase A and the attract returns to the leg
     * select — capturing one whole A->B->C->D->restart set before the abort. */
    return (uint16_t)(auto_cycle_done ? RM_IN_FIRE : 0);
}
#endif

void main(void) {
    RmArena arena;
    if (!load_assets(&arena)) return;

    /* Seed the two persistent RAM regions from their baked defaults (the score record + hi-score table
     * live here; the flow mutates them). */
    for (unsigned i = 0; i < sizeof fixture_hud_text; i++) hud_text_ram[i] = fixture_hud_text[i];
    for (unsigned i = 0; i < sizeof fixture_highscore; i++) highscore_ram[i] = fixture_highscore[i];
    for (unsigned i = 0; i < sizeof buf_a_ram; i++) buf_a_ram[i] = arena.tables[i];
    for (unsigned i = 0; i < sizeof fuel_mask_ram; i++) fuel_mask_ram[i] = fixture_fuel_mask[i];

    HudState hud = {0};
    const HudAssets hud_assets = {
        .color_pairs = fixture_color_pairs, .color_bar_mask = fixture_color_bar_mask,
        .color_bar_cidx = fixture_color_bar_cidx + CIDX_ZERO_OFF, .fuel_mask = fuel_mask_ram,
        .font = fixture_font, .hud_text = hud_text_ram,   /* mutable: course_events writes the score here */
        .dashboard_src = arena.gfx + ARENA_DASH_SRC_OFF,
        .dsp_table = fixture_dsp_table, .dsp_src = arena.gfx,
        .small_gauge_str = fixture_small_gauge_str,
        .num_sprites = arena.gfx + ARENA_NUM_SPRITES_OFF,
        .num_glyph_tbl = fixture_num_glyph_tbl, .crash_color_tbl = fixture_crash_color_tbl,
        .score_delta_time = fixture_score_delta_time, .score_delta_roll = fixture_score_delta_roll,
    };
    const RoadSource src = {
        .persp_seg = (const int8_t *)fixture_road_persp_seg,
        .width_count = fixture_road_width_count,
    };
    RoadInput road = {
        .width_tbl = ctrl + RM_CTRL_WIDTH_OFF,   /* rebound per frame after the build */
        .param = fixture_road_param,
        .edge_tbl = fixture_road_edge + ROAD_EDGE_PAD,   /* rebound by apply_player (road_edge_sel) */
        .tex = arena.scratch, .edge_const = fixture_road_edge_const,
    };
    RoadPose pose;
    ScrollState scroll;
    CourseState course;
    CourseRing ring;
    int16_t obj_shade;
    uint16_t screen_offset;
    const RmInitAssets init_assets = {.buf_a = arena.tables, .legtime = fixture_legtime};

    const uint8_t *low = fixture_obj_low;

    GobjPrefixState pfx;
    const GobjPrefixAssets pfx_assets = {
        .anim_word_tbl = low + OBJ_LOW_ANIM_WORD_TBL,
        .anim_coloridx_tbl = low + OBJ_LOW_ANIM_COLORIDX, .color_pairs = low + OBJ_LOW_COLOR_PAIRS,
        .marker_recs = gobj_scratch, .anim_color = fuel_mask_ram,   /* aliases the HUD's fuel mask */
        .anim_mirror1 = buf_a_ram + GOBJ_ANIM_BUF_OFF1, .anim_mirror2 = buf_a_ram + GOBJ_ANIM_BUF_OFF2,
    };
    const GroundAssets ground_assets = {
        .col_tbl = low + OBJ_LOW_GROUND_COL, .band_records = low + OBJ_LOW_GROUND_BAND,
        .color_pairs = low + OBJ_LOW_COLOR_PAIRS,
    };
    ObjectInput object = {
        .width_tbl = ctrl + RM_CTRL_WIDTH_OFF, .blit_mask_l = low + OBJ_LOW_BLIT_MASK_L,
        .blit_mask_r = low + OBJ_LOW_BLIT_MASK_R,
    };
    ObjListCtx objlist = {
        .px = 0, .draw_buf = 0, .buf_a = buf_a_ram, .buf_c = arena.gfx,
        .color_pairs = low + OBJ_LOW_COLOR_PAIRS, .view_xform = low + OBJ_LOW_VIEW_XFORM,
        .objsh2p_tbl = low + OBJ_LOW_OBJSH2P_TBL, .jumptable = low + OBJ_LOW_JUMPTABLE,
        .xoff_tbl = low + OBJ_LOW_XOFF_TBL,
    };
    SpriteState sprite;
    const SpriteAssets sprite_assets = {
        .gfx = arena.gfx, .fg_anim_tbl = low + OBJ_LOW_FG_ANIM_TBL,
        .body_tbl = low + OBJ_LOW_BODY_TBL, .hi_tbl = low + OBJ_LOW_HI_TBL,
        .lo_piece_tbl = low + OBJ_LOW_LO_PIECE_TBL, .lo_piece_idx = low + OBJ_LOW_LO_PIECE_IDX,
    };
    GroundState ground_mut = {0};

    const PlayerAssets player_assets = {
        .lean_anim_tbl = low + OBJ_LOW_LEAN_ANIM_TBL,
        .scroll_speed_tbl = low + OBJ_LOW_SCROLL_SPEED_TBL,
        .speed_jitter_tbl = low + OBJ_LOW_SPEED_JITTER_TBL,
        .steer_curve_tbl = low + OBJ_LOW_STEER_CURVE_TBL,   /* cursor-zero: the row index goes negative */
        .legflag_tbl = low + OBJ_LOW_LEGFLAG_TBL,
        .crash_anim_tbl = low + OBJ_LOW_CRASH_ANIM_TBL,
    };
    PlayerState player;

    EventState ev;
    EventAssets event_assets = {         /* MUTABLE: coll_mask is repointed per leg by bind_leg */
        .fx_type_tbl = low + OBJ_LOW_FX_TYPE_TBL, .evt_obj_type_tbl = low + OBJ_LOW_EVT_OBJ_TYPE,
        .score_deltas = low + OBJ_LOW_SCORE_DELTAS, .score_label = low + OBJ_LOW_SCORE_LABEL,
        .flag_seq_table = low + OBJ_LOW_FLAG_SEQ_TBL, .probe_deltas = low + OBJ_LOW_PROBE_DELTAS,
        .ckpt_anim_tbl = low + OBJ_LOW_CKPT_ANIM_TBL,
        .coll_mask = arena.tables + ARENA_COURSE_MASK_BASE,   /* rebound per leg */
        .buf_a = arena.tables, .dash_raw = arena.course, .font = fixture_font,
    };
    RmEventCtx ctx = {
        .player = &player, .gobj = &pfx, .ring = &ring, .pose = &pose, .road_src = &src,
        .ctrl = ctrl, .scanline = scanline, .ev = &ev, .hud_text = hud_text_ram,
        .gfx = arena.gfx, .assets = &event_assets, .leg = DEMO_LEG_INDEX, .game_over = 0,
    };

    /* The between-legs flow's draw-asset bundles. Const graphics from the arena / obj-low blob; the
     * hi-score table points at the mutable highscore_ram (update_highscore writes it, the draw reads
     * it). leg_palette points AT leg 0's per-row colour byte (indexed [i - leg]). */
    FlowState flow = {0};
    const RmIntermissionAssets int_assets = {
        .color_pairs = fixture_color_pairs, .font = fixture_font,
        .num_sprites = arena.gfx + ARENA_NUM_SPRITES_OFF, .num_glyph_tbl = fixture_num_glyph_tbl,
        .poll_src = arena.gfx + ARENA_POLL_SRC_OFF, .poll_blits = fixture_poll_blits,
        .header_str = low + OBJ_LOW_INT_HEADER, .sec1_tbl = low + OBJ_LOW_INT_SEC1,
        .sec3_tbl = low + OBJ_LOW_INT_SEC3, .credits = low + OBJ_LOW_INT_CREDITS,
        .leg_names = arena.tables + ARENA_LEG_NAMES_OFF, .highscore = highscore_ram,
    };
    const RmResultsAssets res_assets = {
        .color_pairs = fixture_color_pairs, .font = fixture_font,
        .num_sprites = arena.gfx + ARENA_NUM_SPRITES_OFF, .num_glyph_tbl = fixture_num_glyph_tbl,
        .gfx = arena.gfx, .title = low + OBJ_LOW_LEG_TITLE, .leg_palette = low + OBJ_LOW_LEG_ROW_PAL,
        .row_names = arena.tables + ARENA_ROW_NAMES_OFF, .leg_digits = arena.tables + ARENA_LEG_NAMES_OFF,
    };

    Shell shell = {
        .arena = &arena, .player = &player, .course = &course, .pose = &pose, .scroll = &scroll,
        .ring = &ring, .ev = &ev, .pfx = &pfx, .sprite = &sprite, .ground = &ground_mut,
        .objlist = &objlist, .object = &object, .hud = &hud, .road = &road,
        .obj_shade = &obj_shade, .screen_offset = &screen_offset,
        .src = &src, .hud_assets = &hud_assets, .pfx_assets = &pfx_assets, .ground_assets = &ground_assets,
        .sprite_assets = &sprite_assets, .player_assets = &player_assets, .init_assets = &init_assets,
        .low = low, .event_assets = &event_assets, .ctx = &ctx, .stream = arena.tables, .leg = DEMO_LEG_INDEX,
        .race_input_prev = 0, .flow = &flow,
        .int_assets = &int_assets, .res_assets = &res_assets,
    };
    Shell *s = &shell;

    /* Save the desktop's palette + video base so they can be restored on exit. The race palette is set
     * by start_leg (the single place every race entry funnels through — see fix note there). */
    uint16_t tos_palette[16];
    for (int reg = 0; reg < 16; reg++) tos_palette[reg] = (uint16_t)Setcolor((short)reg, -1);
    /* Clear both screen buffers once, so "buffers start blank" holds before the first draw (draw_frame
     * never clears). The pool is BSS and already zero at GEMDOS load, so this is belt-and-braces. */
    memset(screen_buf(0)->px, 0, SCREEN_BYTES);
    memset(screen_buf(1)->px, 0, SCREEN_BYTES);

    /* BOOT fast path (golden parity): start leg DEMO_LEG_INDEX directly and dump its first painted
     * frame BEFORE any physics — byte-identical to recreate's pipeline (build/golden.bin). Only after
     * the first leg ends does the full flow (highscore -> intermission -> leg select) close the loop. */
    start_leg(s, DEMO_LEG_INDEX);
    flow.leg_index = DEMO_LEG_INDEX;
    flow.leg_select = DEMO_LEG_INDEX;
    draw_frame(s, screen_buf(s->shown));
    long tos_screen = Physbase();
    Setscreen(-1L, (long)screen_buf(s->shown)->px, -1);
    Vsync();
#if !defined(DEMO_AUTODRIVE) && !defined(DEMO_FLOW_AUTO)
    dump_frame(screen_buf(s->shown));    /* the golden frame-0 dump (before the keyboard is taken) */
#endif

    long old_kbd_vector = kbd_install();
    flow_event(FT_LEG_START, DEMO_LEG_INDEX, 0);
    int booted = 1;
    for (; !s->quit; booted = 0) {
        if (!booted) {
            /* Not the boot pass: run the leg select (init_playfield) to pick the next leg, then start
             * it (init_leg + the race palette, both inside start_leg). This is main's loop top. */
#ifdef DEMO_FLOW_AUTO
            run_leg_select(s, auto_select_input, no_fkey);
#else
            run_leg_select(s, read_input, read_fkey);
#endif
            if (s->quit) break;                         /* Esc/Q from the leg select -> restore + exit */
            start_leg(s, flow.leg_index);
            flow_event(FT_LEG_START, flow.leg_index, 1);
            render_and_show(s);                         /* race-start frame (start_leg set the palette) */
        }

        /* ---- the race loop ---- */
        int ended = 0;
        for (int frame = 0; !s->quit && !ended; frame++) {
            (void)frame;   /* only read by the debug trace / autodrive / flow-auto caps below */
            if (take_key_hit(SCAN_R)) start_leg(s, s->leg);   /* R restarts the current leg */

            uint16_t input;
#ifdef DEMO_AUTODRIVE
            input = autodrive_input(frame);
#else
            input = read_input();
#endif
            ended = game_update_step(s, input);

#ifdef DEMO_TRACE
            trace_frame(frame, &player, &ev, &course);
#endif
            render_and_show(s);
            s->quit = quit_requested();
#ifdef DEMO_AUTODRIVE
            /* Headless frame budget: stop at the trace length (or the autodrive length when not tracing)
             * even if the leg has not ended. The dump itself happens on loop exit (below), so it fires on
             * a leg end too — a shortened-clock idle trace ends well before the budget. */
#ifdef DEMO_TRACE
            if (frame + 1 >= DEMO_TRACE) s->quit = 1;
#else
            if (frame + 1 >= DEMO_AUTODRIVE) s->quit = 1;
#endif
#endif
#if defined(DEMO_FLOW_AUTO) && !defined(DEMO_AUTODRIVE)
            /* A race reached via the leg select (booted == 0) proves the whole loop closed; run a few
             * frames as evidence the started leg drives, then end the trace run. */
            if (!booted && frame + 1 >= FLOW_AUTO_RACE_CAP) s->quit = 1;
#endif
        }
#if defined(DEMO_AUTODRIVE) && !defined(DEMO_FLOW_AUTO)
        /* Headless autodrive dumps on race-loop EXIT — whichever came first, the leg end (abort_flag < 0)
         * or the frame budget — then quits instead of entering the between-legs flow, which would poll a
         * dead keyboard under headless Hatari and hang (so an idle leg-end trace never reached the dump). */
#ifdef DEMO_TRACE
        trace_dump();
#else
        dump_frame(screen_buf(s->shown));
#endif
        s->quit = 1;
#endif
        if (s->quit) break;

        /* ---- the leg ended (abort_flag < 0): update_highscore -> game_over++ -> intermission ->
         * game_over = 0, then the loop top runs the leg select again. This is main @0x10100:286-317. */
        flow_event(FT_LEG_END, s->leg, (uint16_t)ev.abort_flag);
        flow.leg_index = s->leg;
        rm_update_highscore(&flow, highscore_ram, hud_text_ram + RM_HUD_SCORE_BCD_OFF);
        flow_event(FT_HISCORE, flow.leg_index, flow.hiscore_pos);
        rm_flow_game_over_enter(&flow);
#ifdef DEMO_FLOW_AUTO
        run_intermission(s, auto_intermission_input);
#else
        run_intermission(s, read_input);
#endif
        rm_flow_game_over_exit(&flow);
    }

    kbd_remove(old_kbd_vector);
    Setscreen(-1L, tos_screen, -1);
    Setpalette(tos_palette);
    Vsync();
#ifdef DEMO_FLOW_TRACE
    flow_trace_dump();
#endif
}
