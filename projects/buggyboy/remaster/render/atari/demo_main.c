/* demo_main.c — playable BuggyBoy on a real 68000: remaster's own render pipeline driven by
 * remaster's own port of the original's player physics.
 *
 * Each frame is game_update-then-draw, as the original orders it:
 *   rm_player_update  — the ported driving model (src/player.c): throttle -> engine rpm -> speed,
 *                       speed -> the road-scroll rate and the view advance whose wrap advances the
 *                       course, steering -> wheel position -> body lean and road curvature, and the
 *                       road-edge clamp / off-road push. Its outputs are fanned out to the render
 *                       structs below, which is all the "wiring" the game loop is.
 *   draw_frame        — the full ported render pipeline: rm_gobj_prefix (off-frame state advance) ->
 *                       rm_build_road_geometry -> rm_render_road -> rm_blit_road_scroll -> the
 *                       draw_game_objects tree (ground, foreground sprite, the two roadside
 *                       object-list passes split around the scaled draw_object, and the player buggy,
 *                       ordered against the buggy by the view) -> rm_draw_hud, then flips.
 * Controls (held keys, read straight from the IKBD — see os.s):
 *   Up / Down    : throttle / brake      Left / Right : steer
 *   Space        : fire (cycles the dashboard variant, as in the original)
 *   R            : restart the leg       Esc / Q : quit
 * The first frame is dumped to C:\SCREEN.BIN *before* any physics runs, so a headless run can still
 * byte-compare it to recreate's g_build_road_geometry + g_render_road + g_blit_road_scroll +
 * g_draw_game_objects + g_draw_hud (build/golden.bin).
 *
 * Assets come from the game's own data files: COURSES.DAT and GRAPHICS.GRA are read off the disk at
 * boot and unpacked by src/assets.c, so the road texture, the scroll playfield, the course stream,
 * the object record arena and every sprite are the real thing. Only the original PROGRAM's own
 * data-segment tables (fonts, colour pairs, perspective/edge tables, the object jump table) are
 * still baked by gen_demo_fixture.py, because those are code constants, not file content. See README.
 */
#include <stdint.h>
#include <string.h>          /* freestanding libc, defined in shim.c */

#include "assets.h"
#include "game.h"
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
 * throttle want, but a momentary key (quit, restart) cannot be read that way: the loop polls once per
 * frame and a frame here is ~200 ms, so a quick tap's make AND break both land between two polls and
 * key_down is already back to 0 when it is read — the press is silently lost. key_hit is set by the
 * interrupt on the make and stays set until read here, so no press can be missed. */
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
 * a checkpoint/gate frame, and draw_hud reads it (via assets.hud_text) as the template it copies and
 * overlays the speed/time digits onto — the original aliases one region, so both must see the same
 * bytes. Seeded from fixture_hud_text at boot (frame 0 is thus byte-identical to the const fixture). */
static uint8_t hud_text_ram[sizeof fixture_hud_text] __attribute__((aligned(2)));

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

/* Re-derive every ring-owned view — the dispatcher's ST mirror, the ground markers, the sprite
 * gates — from the live ring. Must run wherever the ring changes: at seed, after every course
 * advance, and on a leg restart (missing the last one leaves mid-course scenery on a reset road). */
static void ring_views_refresh(const CourseRing *ring, GroundState *ground, SpriteState *sprite) {
    rm_ring_store_st(ring, ring_st);
    rm_ring_ground_markers(ring, ground->markers);
    sprite->buggy_gate = rm_ring_buggy_gate(ring);
    sprite->fg_gate = rm_ring_fg_gate(ring);
}

/* Start (or restart) the leg NATIVELY: reset every per-leg OWNER struct to its leg-start value through
 * rm_init_leg (recreate's init_leg), instead of the old baked *_INIT snapshot. It zeroes the owner
 * structs, reseeds the shared HUD-text region (rm_init_leg's phase 5 reads the score template out of
 * it, and phases 4/5/6 rewrite it), then fills them from the loaded arena. The render VIEWS (HudState,
 * GroundState, ObjListCtx, the sprite gates) follow from apply_player + ring_views_refresh, exactly as
 * every driving frame derives them. obj_shade / screen_offset are the two outputs with no owner field. */
static void leg_reset(PlayerState *player, CourseState *course, RoadPose *pose, ScrollState *scroll,
                      CourseRing *ring, EventState *ev, GobjPrefixState *pfx, SpriteState *sprite,
                      const RmInitAssets *init_assets, int16_t *obj_shade, uint16_t *screen_offset) {
    *player = (PlayerState){0};
    *course = (CourseState){0};
    *pose = (RoadPose){0};
    *scroll = (ScrollState){0};
    *ring = (CourseRing){0};
    *ev = (EventState){0};
    *pfx = (GobjPrefixState){0};
    *sprite = (SpriteState){0};
    for (unsigned i = 0; i < sizeof fixture_hud_text; i++) hud_text_ram[i] = fixture_hud_text[i];
    rm_init_leg(player, course, pose, scroll, ring, ev, pfx, sprite,
                hud_text_ram, obj_shade, screen_offset, init_assets, DEMO_LEG_INDEX);
}

/* Run the full ported render pipeline into `fb`, in draw_game_objects order: prefix (off-frame state),
 * geometry + road + scroll band, then the object tree (ground, foreground sprite, the two sprite
 * object-list passes split around draw_object, and the buggy ordered against the fixed pass by the
 * view), then the HUD. The scroll advances every frame; the prefix advances view_parity/anim. */
static void draw_frame(Framebuffer *fb, RoadPose *pose, const RoadSource *src,
                       const CourseRing *ring, RoadInput *road,
                       ScrollState *scroll, const HudState *hud, const HudAssets *hud_assets,
                       GobjPrefixState *pfx, const GobjPrefixAssets *pfx_assets,
                       const GroundState *ground, const GroundAssets *ground_assets,
                       SpriteState *sprite, const SpriteAssets *sprite_assets,
                       const ObjectInput *object, ObjListCtx *objlist, const uint8_t *low) {
    rm_gobj_prefix(pfx, pfx_assets);                 /* off-frame: advance view_parity/anim/marker */
    objlist->view_parity = pfx->view_parity;         /* the dispatcher (handler_lo) reads the advanced parity */
    objlist->px = fb->px;                            /* the dispatcher's draw target: this frame's buffer */
    rm_build_road_geometry(pose, src, ring, ctrl, scanline);
    road->width_tbl = ctrl + RM_CTRL_WIDTH_OFF;
    /* The object dispatcher's per-row x-offset table aliases the freshly-built road control table in
     * the original (obj_xoff_tbl == road_width_tbl + 2), so rebind it to this frame's ctrl. */
    objlist->xoff_tbl = ctrl + RM_CTRL_WIDTH_OFF + 2;
    scroll->seg_head = pose->seg_head;               /* the scroll step follows the near slope */
    /* No per-frame clear: the pipeline below repaints every visible byte (blit_road_scroll's fill +
     * band, render_road, the ground/object tree, then the HUD), so drawing over this buffer's
     * two-frames-old content is byte-identical to drawing over zeros. The buffers are cleared once in
     * main() to establish that invariant. Verified byte-exact against a per-frame-clear build by the
     * autodrive frame-2/frame-61 dumps; the old memset here cost 96 ms/frame (a third of the frame —
     * the shim memset is a byte loop). */
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

    /* The dispatcher's flag streams and the pass split all come from the LIVE ring: the sprite
     * passes walk the serialized grid from row 1, the fixed pass from row 12 — the same aliasing
     * the original gets from pointing into its flat row grid. */
    int count = rm_ring_sprite_count(ring);
    if (count - 1 >= 0)                               /* pass 1: the active sprite rows */
        rm_draw_object_list(objlist, low + OBJ_LOW_SPRITE_DISP, 0, ring_st + GOBJ_SPRITE_PASS_ROW * RM_RING_ROW_BYTES, 0,
                            (uint16_t)(count - 1), GOBJ_D6_INIT, (uint16_t)count);
#if defined(DEMO_DUMP_STAGE) && DEMO_DUMP_STAGE == 3
    return;
#endif
    rm_draw_object(object, fb);
    if (GOBJ_SPRITE_LAST - count >= 0)               /* pass 2: the remaining rows */
        rm_draw_object_list(objlist,
                            low + OBJ_LOW_SPRITE_DISP, (uint16_t)(count * GOBJ_ROW_A5_STRIDE),
                            ring_st + GOBJ_SPRITE_PASS_ROW * RM_RING_ROW_BYTES, (uint16_t)(count * GOBJ_ROW_A3_STRIDE),
                            (uint16_t)(GOBJ_SPRITE_LAST - count),
                            (uint16_t)(GOBJ_D6_INIT - count * GOBJ_D6_ROW_STEP), 0);
    if ((objlist->view_flags & GOBJ_VIEW_REAR) == 0) {   /* pass 3 (fixed) + buggy, view-ordered */
        rm_draw_object_list(objlist, low + OBJ_LOW_LIST_BASE, 0,
                            ring_st + GOBJ_FIXED_PASS_ROW * RM_RING_ROW_BYTES, 0, 0, 0, 0);
        rm_draw_buggy(sprite, sprite_assets, fb);
    } else {
        rm_draw_buggy(sprite, sprite_assets, fb);
        rm_draw_object_list(objlist, low + OBJ_LOW_LIST_BASE, 0,
                            ring_st + GOBJ_FIXED_PASS_ROW * RM_RING_ROW_BYTES, 0, 0, 0, 0);
    }

    rm_draw_hud(hud, hud_assets, fb);
}

/* Fan rm_player_update's outputs out to the render structs — the whole of the "game loop" beyond
 * running the physics and drawing. Each assignment is one of the original's shared globals: the
 * pose's curve/view come straight from the physics, the sprite reads the body pose (skid doubles as
 * the foreground-sprite suppressor, exactly as in the original), the ground column and the object
 * list's scan offset are the same global, and the HUD shows the speed and clock. */
static void apply_player(const PlayerState *p, RoadPose *pose, RoadInput *road, ScrollState *scroll,
                         SpriteState *sprite, HudState *hud, GroundState *ground, ObjListCtx *objlist,
                         const EventState *ev) {
    pose->curve = p->road_curve;
    pose->view_flags = p->view_flags;
    road->edge_tbl = fixture_road_edge + ROAD_EDGE_PAD + p->road_edge_sel;
    scroll->scroll_speed = p->scroll_speed;

    sprite->lean = p->lean;
    sprite->pitch = p->buggy_pitch_off;      /* the crash script's body bounce */
    sprite->wheel_pos = p->wheel_pos;
    sprite->skid = p->skid;
    sprite->sprite_suppress = (uint16_t)p->skid;
    sprite->crash_disp = p->crash_disp;
    sprite->buggy_draw_flag = p->buggy_draw_flag;
    sprite->speed_raw = p->speed_raw;
    sprite->road_curve = p->road_curve;

    ground->view = p->ground_view_off;
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

/* Start (or restart) the leg: reset the owner structs natively (leg_reset -> rm_init_leg), then derive
 * every render VIEW from them exactly as a driving frame does — the two scalars with no owner field
 * (object.shade, the scroll's screen_offset), the object-list's live counters, then apply_player and
 * ring_views_refresh. Used at boot AND on the R / leg-end restart, so the two paths cannot drift. */
static void start_leg(PlayerState *player, CourseState *course, RoadPose *pose, ScrollState *scroll,
                      CourseRing *ring, EventState *ev, GobjPrefixState *pfx, SpriteState *sprite,
                      GroundState *ground, ObjListCtx *objlist, ObjectInput *object, HudState *hud,
                      RoadInput *road, const RmInitAssets *init_assets,
                      int16_t *obj_shade, uint16_t *screen_offset) {
    leg_reset(player, course, pose, scroll, ring, ev, pfx, sprite, init_assets, obj_shade, screen_offset);
#ifdef DEMO_TIME_LEFT
    /* Debug builds only: shorten the leg's bonus clock so a headless idle trace reaches the time-out
     * (and thus the leg end) in ~140 frames instead of ~800. A restart re-seeds the FULL clock from
     * rm_init_leg first, so a restart shows time_left jumping back up before this shortens it again. */
    player->time_left = DEMO_TIME_LEFT;
#endif
    object->shade = *obj_shade;
    objlist->bonus_timer = pfx->bonus_timer;              /* the bonus clamp follows the prefix */
    objlist->p24_flag = hud_text_ram[RM_HUD_SCORE_STR_OFF + 1];   /* the live score_str[1] rm_init_leg wrote */
    apply_player(player, pose, road, scroll, sprite, hud, ground, objlist, ev);
    ring_views_refresh(ring, ground, sprite);
}

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

/* DEMO_AUTODRIVE=N (debug builds only): drive a fixed script instead of the keyboard and dump the
 * frame after N frames, so a headless run can prove the whole loop — physics, course advance, render
 * — runs on the 68000 and the buggy actually moves. Undefined in normal builds. */
#ifdef DEMO_AUTODRIVE
#ifndef AUTODRIVE_STEER_AFTER
#define AUTODRIVE_STEER_AFTER 60         /* throttle up first, then hold a steering lock */
#endif
/* The base bits held every frame. Default is throttle (drive the course). Set to 0 (with a large
 * AUTODRIVE_STEER_AFTER) to IDLE the buggy, which is what a leg-end time-out trace needs: nothing
 * moves, so nothing crashes, and §4's bonus clock is the only thing that fires. */
#ifndef AUTODRIVE_BASE_INPUT
#define AUTODRIVE_BASE_INPUT RM_IN_ACCEL
#endif
static uint16_t autodrive_input(int frame) {
    return (uint16_t)(AUTODRIVE_BASE_INPUT | (frame < AUTODRIVE_STEER_AFTER ? 0 : RM_IN_LEFT));
}
#endif

/* DEMO_TRACE=N (debug builds only, with DEMO_AUTODRIVE): log N frames of driving state instead of a
 * framebuffer, so a headless run can see whether the course actually advances on-target. The log goes
 * to SCREEN.BIN, padded to a full framebuffer, purely so the existing headless runner picks it up
 * unchanged — it is telemetry, not an image. Words are big-endian by virtue of being 68000 stores. */
#ifdef DEMO_TRACE
#define TRACE_WORDS 9
/* Round UP so the dump is >= SCREEN_BYTES whatever TRACE_WORDS is — the headless runner waits for a
 * full framebuffer's worth of bytes (9 words divides 32000 unevenly, unlike the old 8). And never
 * fewer slots than DEMO_TRACE asks for: the runner minimum alone caps at 1778 slots with 9 words,
 * which would silently truncate the documented DEMO_TRACE=2000 keylog run. */
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

/* DEMO_KEYLOG (debug builds only, needs -Wa,--defsym,KBD_RAWLOG=1): play normally, then on quit dump
 * every byte the IKBD ACIA delivered, in order, plus how many times the R-restart fired. Written to
 * KEYLOG.BIN on the demo's own drive, so an interactive session can be inspected afterwards. This is
 * how we find out whether non-keyboard packets are reaching key_down[] — see README. */
#ifdef DEMO_KEYLOG
extern volatile uint8_t kbd_raw_log[];
extern volatile uint16_t kbd_raw_pos;

#define KEYLOG_HEADER_WORDS 4
static uint16_t keylog_restarts;

static void keylog_dump(int frames) {
    static uint16_t header[KEYLOG_HEADER_WORDS];
    header[0] = kbd_raw_pos;          /* bytes captured */
    header[1] = keylog_restarts;      /* times the R-restart path ran */
    header[2] = (uint16_t)frames;
    header[3] = 0;
    long h = Fcreate("KEYLOG.BIN", 0);
    if (h < 0) return;
    Fwrite((short)h, (long)sizeof header, header);
    Fwrite((short)h, (long)kbd_raw_pos, (void *)kbd_raw_log);
#ifdef DEMO_TRACE
    /* ...followed by the per-frame driving state, so one interactive session shows both what was
     * pressed and what the course position did in response. */
    Fwrite((short)h, (long)sizeof trace_log, trace_log);
#endif
    Fclose((short)h);
}
#endif

static uint16_t read_input(void) {
    uint16_t in = 0;
    if (key_down[SCAN_UP]) in |= RM_IN_ACCEL;
    if (key_down[SCAN_DOWN]) in |= RM_IN_BRAKE;
    if (key_down[SCAN_LEFT]) in |= RM_IN_LEFT;
    if (key_down[SCAN_RIGHT]) in |= RM_IN_RIGHT;
    if (key_down[SCAN_SPACE]) in |= RM_IN_FIRE;
    return in;
}

static void dump_frame(Framebuffer *fb) {
    long h = Fcreate("SCREEN.BIN", 0);
    if (h >= 0) { Fwrite((short)h, SCREEN_BYTES, fb->px); Fclose((short)h); }
}

/* Read a file into `dst`, at most `max` bytes. Returns the byte count, or -1 if it won't open.
 *
 * The handle test is `<= 0`, not `< 0`: GEMDOS reserves 0/1/2 for con/aux/prn and never returns
 * them from a successful Fopen, and handle 0 is a failure this project has actually hit — see the
 * ordering note at the top of os.s. Treating it as valid means Fread reads the KEYBOARD. */
#define FOPEN_READ_ONLY 0
static long read_file(const char *name, uint8_t *dst, long max) {
    long handle = Fopen(name, FOPEN_READ_ONLY);
    if (handle <= 0) return -1;
    long got = Fread((short)handle, max, dst);
    Fclose((short)handle);
    return got;
}

/* Load the game's own data files and unpack the graphics — everything the render pipeline draws
 * from. Both must sit next to the .PRG.
 *
 * COURSES.DAT is read with a count equal to its exact size, so anything else is definitively the
 * wrong file. GRAPHICS.GRA has no such pin, so it is read with a count the arena can actually hold
 * (RM_GFX_READ_MAX — a larger count would let the READ itself overrun before any check runs) and
 * only floored here; the real protection against a truncated or foreign file is that the unpack
 * is bounded and reports failure, which no size heuristic could do on its own.
 *
 * Returns 0 after naming the file at fault. NOTE: Cconws writes to the ST console, so under
 * headless Hatari the message is invisible and the only symptom is a missing SCREEN.BIN. */
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

void main(void) {
    RmArena arena;
    if (!load_assets(&arena)) return;

    /* The HUD is a per-frame VIEW: apply_player refreshes every field the demo reads from the physics /
     * event state (the leg-start values below are all it needs before the first apply_player, which
     * runs before the frame-0 draw). It is not baked. */
    HudState hud = {0};
    const HudAssets assets = {
        .color_pairs = fixture_color_pairs, .color_bar_mask = fixture_color_bar_mask,
        .color_bar_cidx = fixture_color_bar_cidx + CIDX_ZERO_OFF, .fuel_mask = fuel_mask_ram,
        .font = fixture_font, .hud_text = hud_text_ram,   /* mutable: course_events writes the score here */
        .dashboard_src = arena.gfx + ARENA_DASH_SRC_OFF,
        /* dsp_table's record offsets are absolute within the graphics arena, so dsp_src is its base */
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
        /* the road texture is the sprite-shift table region; the perspective seeds index below it */
        .tex = arena.scratch, .edge_const = fixture_road_edge_const,
    };
    /* Every per-leg owner struct below is filled by leg_reset (rm_init_leg), not a baked snapshot: the
     * physics/course/event/pose/scroll scalars, the ring seeded from the leg's packed marker records,
     * and the buggy pose. obj_shade / screen_offset are rm_init_leg's two output scalars. */
    RoadPose pose;
    ScrollState scroll;
    CourseState course;
    CourseRing ring;                 /* the live course window the advance scrolls (marker column = the
                                      * road's per-band widths / shoulder flags), reseeded on restart */
    int16_t obj_shade;
    uint16_t screen_offset;
    const RmInitAssets init_assets = {.buf_a = arena.tables, .legtime = fixture_legtime};
    /* the leg's course records, read backward from this anchor in the loaded COURSES.DAT */
    const uint8_t *stream = arena.tables + ARENA_COURSE_STREAM_OFF;

    /* --- draw_game_objects: a mutable buf_a copy (the prefix writes anim mirrors the draws read),
     * the object dispatcher context (arena pointers into the baked blobs; draw_buf 0 = fb->px base),
     * the ground + scaled-object inputs, the buggy sprite state, and the prefix state. --- */
    for (unsigned i = 0; i < sizeof buf_a_ram; i++) buf_a_ram[i] = arena.tables[i];
    for (unsigned i = 0; i < sizeof fuel_mask_ram; i++) fuel_mask_ram[i] = fixture_fuel_mask[i];
    for (unsigned i = 0; i < sizeof hud_text_ram; i++) hud_text_ram[i] = fixture_hud_text[i];
    const uint8_t *low = fixture_obj_low;

    /* The event engine mutates the prefix state too (flag_seq_count/off, bonus_timer, the marker
     * decay counters), so it is per-leg state leg_reset rewinds. */
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
    /* object.shade is rm_init_leg's obj_shade output; set after leg_reset. */
    ObjectInput object = {
        .width_tbl = ctrl + RM_CTRL_WIDTH_OFF, .blit_mask_l = low + OBJ_LOW_BLIT_MASK_L,
        .blit_mask_r = low + OBJ_LOW_BLIT_MASK_R,
    };
    ObjListCtx objlist = {
        /* px is rebound to the frame's buffer in draw_frame (we alternate two screen buffers). */
        .px = 0, .draw_buf = 0, .buf_a = buf_a_ram, .buf_c = arena.gfx,
        .color_pairs = low + OBJ_LOW_COLOR_PAIRS, .view_xform = low + OBJ_LOW_VIEW_XFORM,
        .objsh2p_tbl = low + OBJ_LOW_OBJSH2P_TBL, .jumptable = low + OBJ_LOW_JUMPTABLE,
        .xoff_tbl = low + OBJ_LOW_XOFF_TBL,
        /* view_flags / view_parity / obj_scan_off are refreshed each frame (apply_player + draw_frame);
         * bonus_timer follows the prefix; p24_flag is the live score_str[1] rm_init_leg wrote. All are
         * set from the reset state below, so no leg-start value is baked. */
    };
    SpriteState sprite;                /* the buggy pose — filled by leg_reset (rm_init_leg) */
    const SpriteAssets sprite_assets = {
        .gfx = arena.gfx, .fg_anim_tbl = low + OBJ_LOW_FG_ANIM_TBL,
        .body_tbl = low + OBJ_LOW_BODY_TBL, .hi_tbl = low + OBJ_LOW_HI_TBL,
        .lo_piece_tbl = low + OBJ_LOW_LO_PIECE_TBL, .lo_piece_idx = low + OBJ_LOW_LO_PIECE_IDX,
    };
    GroundState ground_mut = {0};   /* view + markers seeded from the reset state / ring below */

    /* --- the driving model (src/player.c). Its const tables all live inside the obj-low blob. --- */
    const PlayerAssets player_assets = {
        .lean_anim_tbl = low + OBJ_LOW_LEAN_ANIM_TBL,
        .scroll_speed_tbl = low + OBJ_LOW_SCROLL_SPEED_TBL,
        .speed_jitter_tbl = low + OBJ_LOW_SPEED_JITTER_TBL,
        .steer_curve_tbl = low + OBJ_LOW_STEER_CURVE_TBL,   /* cursor-zero: the row index goes negative */
        .legflag_tbl = low + OBJ_LOW_LEGFLAG_TBL,
        /* The crash script's records. Nothing on-target arms it yet — that is section 12's collision
         * probe and event dispatch (see game.h) — but the pointer has to be real, not NULL. */
        .crash_anim_tbl = low + OBJ_LOW_CRASH_ANIM_TBL,
    };
    PlayerState player;   /* filled by leg_reset (rm_init_leg) at boot + on restart */

    /* --- the course-event engine (src/events.c): the system that decides to crash you and delivers
     * the checkpoint / finish / bonus events. rm_player_update dispatches through it on the §6 event
     * path; the wrap-frame block below runs its probe + fx/horizon tail. EventState is the leg-start
     * scalar globals (reset on R); the const tables are program data (obj-low), the coll-mask / dash
     * label & clear tables / raw dashboard block are arena-resident (per PORTING.md, from the loaded
     * arena, not baked); the score digits land in the shared hud_text_ram the HUD reads. --- */
    EventState ev;   /* filled by leg_reset (rm_init_leg); the dash marker stays 0 at a leg start */
    const EventAssets event_assets = {
        .fx_type_tbl = low + OBJ_LOW_FX_TYPE_TBL, .evt_obj_type_tbl = low + OBJ_LOW_EVT_OBJ_TYPE,
        .score_deltas = low + OBJ_LOW_SCORE_DELTAS, .score_label = low + OBJ_LOW_SCORE_LABEL,
        .flag_seq_table = low + OBJ_LOW_FLAG_SEQ_TBL, .probe_deltas = low + OBJ_LOW_PROBE_DELTAS,
        .ckpt_anim_tbl = low + OBJ_LOW_CKPT_ANIM_TBL,
        .coll_mask = arena.tables + ARENA_COURSE_MASK_OFF,   /* per-leg collision-flag longs (buf_a data) */
        .buf_a = arena.tables, .dash_raw = arena.course, .font = fixture_font,
    };
    /* The bundle the §6 dispatch and the wrap-frame tail share: it points at the SAME player / pose /
     * ring / ctrl the loop drives, so an armed crash or a rebuilt control table is seen by everything. */
    RmEventCtx ctx = {
        .player = &player, .gobj = &pfx, .ring = &ring, .pose = &pose, .road_src = &src,
        .ctrl = ctrl, .scanline = scanline, .ev = &ev, .hud_text = hud_text_ram,
        .gfx = arena.gfx, .assets = &event_assets, .leg = DEMO_LEG_INDEX, .game_over = 0,
    };

    /* Start leg 0 NATIVELY (rm_init_leg via start_leg): reset every owner struct + derive the views. */
    start_leg(&player, &course, &pose, &scroll, &ring, &ev, &pfx, &sprite, &ground_mut, &objlist,
              &object, &hud, &road, &init_assets, &obj_shade, &screen_offset);

    uint16_t tos_palette[16];    /* the desktop's colours — restored on exit alongside its video base */
    for (int reg = 0; reg < 16; reg++) tos_palette[reg] = (uint16_t)Setcolor((short)reg, -1);
    Setpalette(fixture_palette);
    rm_scroll_prebuild(arena.gfx + screen_offset, shifted);   /* pre-rotate the playfield once (screen_offset is fixed per leg) */
    /* Clear both screen buffers once, so "buffers start blank" holds before the first draw. The pool
     * is BSS and already zero at GEMDOS load, so this is redundant today — but draw_frame relies on
     * the invariant (it never clears), and the explicit clear keeps it if the pool ever stops being
     * BSS. Boot-time cost is invisible (twice, never again). */
    memset(screen_buf(0)->px, 0, SCREEN_BYTES);
    memset(screen_buf(1)->px, 0, SCREEN_BYTES);
    int shown = 0;
    draw_frame(screen_buf(shown), &pose, &src, &ring, &road, &scroll, &hud, &assets, &pfx, &pfx_assets,
               &ground_mut, &ground_assets, &sprite, &sprite_assets, &object, &objlist, low);
    long tos_screen = Physbase();   /* the desktop's video base — restored on exit or the shifter
                                     * keeps showing our last frame while GEM redraws into TOS's buffer */
    Setscreen(-1L, (long)screen_buf(shown)->px, -1);   /* show the first frame */
    Vsync();

    /* Dump the first frame — drawn before any physics runs — so a headless run can byte-compare it
     * to golden.bin. Only after that do we take the keyboard away from GEMDOS. */
#ifndef DEMO_AUTODRIVE
    dump_frame(screen_buf(shown));
#endif

    long old_kbd_vector = kbd_install();
    uint16_t input_prev = 0;
    int frame_count = 0;
    int quit = 0;
    int restart_pending = 0;   /* set at the leg end (abort_flag < 0) to restart on the next frame */
    for (int frame = 0; !quit; frame++, frame_count++) {
        int r_pressed = take_key_hit(SCAN_R);         /* R restarts the leg natively (rm_init_leg) */
        if (r_pressed || restart_pending) {
            restart_pending = 0;
#ifdef DEMO_KEYLOG
            if (r_pressed) keylog_restarts++;         /* count key presses only, not leg-end restarts */
#endif
            /* Re-run the NATIVE leg start — the same path boot uses. It rewinds every per-leg owner
             * struct (player / event / prefix / course / pose / ring / sprite) and the shared HUD-text
             * score region, so a restart renders the reset road under leg-start scenery, not the
             * mid-course ring the drive advanced into. Stands in for the unported intermission handoff. */
            start_leg(&player, &course, &pose, &scroll, &ring, &ev, &pfx, &sprite, &ground_mut,
                      &objlist, &object, &hud, &road, &init_assets, &obj_shade, &screen_offset);
        }

        /* One frame of the original's driving model, over the road geometry the last frame built.
         * hscroll_step2 is blit_road_scroll's output feeding back in — the scroll biases the curve.
         * input_prev is fed the previous frame's bits, which makes fire a true edge (one dashboard
         * cycle per press). The original leaves that global as a stale baseline instead, so holding
         * fire there re-triggers the animation every time it ends — a demo choice, not the core's. */
        player.input_prev = input_prev;
#ifdef DEMO_AUTODRIVE
        player.input = autodrive_input(frame);
#else
        player.input = read_input();
#endif
        player.hscroll_step2 = (int16_t)scroll.hscroll_step2;
        input_prev = player.input;
        rm_player_update(&player, &player_assets, ctrl, &ctx);

        /* Sync the pose/scroll the wrap-frame build reads BEFORE it runs (apply_player re-syncs after
         * the event tail, so a bonus-record curve kick reaches the render). */
        pose.curve = player.road_curve;
        pose.view_flags = player.view_flags;
        scroll.scroll_speed = player.scroll_speed;

        /* The view wrapping is what advances the course, so the road's bends arrive at the speed the
         * buggy is actually travelling (section 12 of the original). The order mirrors recreate's
         * game_update.c §12: clear event_pending (line 504), the collision-probe head, the ring +
         * segment scroll, the geometry rebuild (so horizon_row is fresh for the event tail, line
         * 570/608), then the fx / horizon-event dispatch (line 611) — which arms crashes and delivers
         * the checkpoint / finish / bonus records, and pokes ring bands 11-13, so every ring-derived
         * view is refreshed after it (or the scenery freezes while the road animates). */
        if (player.view_wrapped) {
            player.event_pending = 0;
            rm_course_probe(&ctx);
            rm_road_course_advance(&pose, &course, &ring, stream);
            /* This build feeds horizon_row to the event tail below; draw_frame builds AGAIN after,
             * off the ring bands the tail pokes — BOTH are faithful (the original's own g_draw_frame,
             * recreate gameplay.c:268, likewise rebuilds after the event pokes). Dropping either shows
             * stale horizon_row / pre-poke geometry; see STATUS.md's perf note before "optimizing" it. */
            rm_build_road_geometry(&pose, &src, &ring, ctrl, scanline);
            rm_course_events(&ctx);
            ring_views_refresh(&ring, &ground_mut, &sprite);
        }

        /* HUD phase 8's STATE side (draw_crash_fx @0x15872, split out from hud.c's DRAW): decay the
         * crash-arm timer, or once it goes negative run the leg-end tally — drain the bonus time /
         * units / score-digit rollovers into the score and arm abort_flag. It runs every frame at the
         * per-frame tail, where the original runs it inside draw_hud. The load-bearing invariant is
         * BEFORE apply_player, so the drawn HUD reflects this frame's tally through the six
         * EventState -> HudState view fields apply_player copies (equiv._Candidate.step keeps the same
         * invariant but sequences the tally after its blit — immaterial, no shared state). make test
         * never runs this loop: the demo's ordering is pinned only by on-target runs. */
        rm_crash_fx_update(&ctx);
        /* abort_flag < 0 is the leg end — the original's main @0x10100 breaks its frame loop here and
         * hands off to update_highscore -> game_over_flag++ -> the intermission -> init_leg. That whole
         * handoff is UNPORTED (see STATUS/PORTING "slice 2"), so we stand in by restarting the current
         * leg from its boot state on the next frame — the same reset R uses, which re-seeds every field
         * slice 1 made persistent (abort_flag, crash_frame, hud_crash_timer, time_left, crash_lap, the
         * HUD-text score/rollover region, marker_pending). Deferring to next frame keeps the reset on a
         * single code path. */
        if ((int16_t)ev.abort_flag < 0) restart_pending = 1;

        apply_player(&player, &pose, &road, &scroll, &sprite, &hud, &ground_mut, &objlist, &ev);
#ifdef DEMO_TRACE
        trace_frame(frame, &player, &ev, &course);
#endif

        /* render off-screen, then flip the video base to it at the vblank (no tearing). */
        int back = shown ^ 1;
        draw_frame(screen_buf(back), &pose, &src, &ring, &road, &scroll, &hud, &assets, &pfx, &pfx_assets,
                   &ground_mut, &ground_assets, &sprite, &sprite_assets, &object, &objlist, low);
        Setscreen(-1L, (long)screen_buf(back)->px, -1);
        Vsync();
        shown = back;
        quit = take_key_hit(SCAN_ESC) || take_key_hit(SCAN_Q);
#if defined(DEMO_TRACE) && defined(DEMO_AUTODRIVE)
        if (frame + 1 >= DEMO_TRACE) { trace_dump(); break; }
#elif defined(DEMO_AUTODRIVE)
        if (frame + 1 >= DEMO_AUTODRIVE) { dump_frame(screen_buf(shown)); break; }
#endif
    }
    kbd_remove(old_kbd_vector);
    Setscreen(-1L, tos_screen, -1);
    Setpalette(tos_palette);
    Vsync();
#ifdef DEMO_KEYLOG
    keylog_dump(frame_count);
#endif
}
