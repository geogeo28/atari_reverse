/* game_main.c — the on-target BuggyBoy game shell: playable BuggyBoy on a real 68000. Ships as
 * BUGGYBOY.PRG, WITH sound: a 50 Hz VBL pump writes the ported REFRESH driver's YM2149 stream to the
 * chip and the trigger seam plays the baked Dosound lists through XBIOS (the sound-pump section below).
 *
 * main() composes the original's own outer loop (decomp.c main @0x10100) out of remaster's ported
 * pieces. The shipping build boots into the LEG SELECT first, exactly as the original game does:
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
 *   - Sound: WIRED and audible. The ported REFRESH driver's state is driven by the in-race / flow
 *     triggers (INITTUNE / INITFX / TURNOFF / stop_music), the 50 Hz VBL pump (vbl_sound, below) writes
 *     its YM2149 stream to the chip, and the Dosound trigger seam plays the baked command lists through
 *     XBIOS. Only the audio QUALITY (timbre / pitch / tempo) is still verified by ear rather than by the
 *     differential — the pump's register stream is proven right, the way it SOUNDS on real hardware is not.
 *   - Vsync pacing / the flip: the shell flips at the vblank; the original's exact frame cadence is off.
 *   - Palette fades: the flow's per-phase palettes are Setpalette'd (an off-image seam — the byte-compare
 *     is palette-agnostic); the 121-frame leg-start "get ready" palette FLASH is a plain frame wait.
 *   - The attract DEMO's input: NOT a seam — the original does not replay a recorded ghost. It runs the
 *     demo with game_over_flag != 0 (main @0x10100:314 / init_playfield @0x12af6:3946 both do
 *     `game_over_flag++; intermission(); game_over_flag = 0`), and game_update forces the player input to
 *     a constant throttle in that state (decomp game_update `uVar11 = input_state & 0xff8f; if
 *     (game_over_flag != 0) uVar11 = 1`). op_start_demo_leg RAISES the demo player's game_over to match,
 *     so the demo holds accel via the §6 forcing (`if (p->game_over) in = RM_IN_ACCEL`) AND runs SILENT
 *     with its scoring suppressed, exactly as the original's game-over-bracketed demo does — the road-edge
 *     clamp + the §6 auto-steer/crash script keep it on the course. (Sound is a seam only on TARGET, where
 *     the VBL pump is slice 3; the driver STATE is kept correct host-side.)
 *
 * BOOT / GOLDEN PARITY: the golden harness (run_golden.py) byte-compares the FIRST painted frame (before
 * any physics) to recreate's pipeline on the leg-0 start (build/golden.bin). The SHIPPING build has no
 * such frame — it boots into the leg select — so the golden harness builds a SEPARATE variant with the
 * fast path enabled by -DGOLDEN_BOOT_LEG=N: that variant skips the leg select on the boot pass and starts
 * leg N directly, drawing + dumping that leg-start frame (byte-identical to recreate's pipeline). The
 * shipping BUGGYBOY.PRG defines neither GOLDEN_BOOT_LEG nor GAME_AUTODRIVE, so it carries NO fast path.
 *
 * Controls — IDENTICAL to the original arcade port (held keys / a joystick in port 1, read straight from
 * the IKBD — see os.s; the joystick has priority, the keyboard is the fallback, exactly as read_input
 * @0x120b0 orders them). The one deliberate deviation is Q (below).
 *   Up / Down    : throttle / brake      Left / Right : steer     Space / joy-fire : fire (dashboard variant)
 *   ESC          : abort the race back to the intermission — breaks the race loop into update_highscore +
 *                  intermission, exactly as the original (main @0x10100:286 `cmpi.b #$1b,d0 / beq`).
 *   G            : toggle the dashboard-variant display (dsp_toggle; main @0x10100:296 `not.w dsp_toggle`).
 *   Help         : pause the race — silence the sound and freeze until any key (main @0x10100:293, scancode 0x62).
 *   F1..F5       : select + start that leg (leg-select screen, as init_playfield's function-key menu).
 *   F6           : preview the race-end results screen (leg select; ip_menu @0x2b86, holds until a fresh key).
 *   F10 + Return : reload GRAPHICS.GRA + the score table (leg select; ip_menu @0x2b36 — Return confirms).
 *   Q            : quit to the desktop. The SINGLE deviation from the original — a coin-op that never
 *                  terminates (main @0x10100 is an infinite loop); a GEMDOS .PRG needs a way back to the
 *                  desktop, so Q (a key the original never reads) is it. The original has NO quit and NO
 *                  restart key, so the shell's old R-restart is gone.
 *   High-score name entry: Up/Left / Down/Right dial each initial back / forward, Space confirms one
 *   (a 30-second TIME countdown ends entry if it runs out).
 * Assets come from the game's own COURSES.DAT + GRAPHICS.GRA, read off disk and unpacked by
 * src/assets.c. Only the original PROGRAM's own data-segment tables (fonts, colour pairs, layout
 * tables, the phase palettes, the object jump table) and two seeds (the intermission_poll control
 * table, the default hi-score table = init_scoretable's output) are baked by gen_game_fixture.py.
 */
#include <stdint.h>
#include <string.h>          /* freestanding libc, defined in shim.c */

#include "assets.h"
#include "game.h"
#include "flow.h"
#include "screen.h"
#include "st.h"              /* be16/wr16/be32/wr32 for the leg-start palette flash */
#include "game_fixture.h"
#include "game_frame.h"
#ifdef GAME_STE
#include "blitter.h"          /* STE hardware-blitter target (PERF30 C4): presence check + self-test */
#endif

void rm_build_road_geometry(RoadPose *pose, const RoadSource *src, const CourseRing *ring,
                            uint8_t *ctrl, uint8_t *scanline);
void rm_render_road(const RoadInput *in, Framebuffer *fb);
void rm_scroll_prebuild(const uint8_t *playfield, uint8_t *shifted);
void rm_blit_road_scroll(ScrollState *s, const uint8_t *shifted, Framebuffer *fb);
bool rm_road_course_advance(RoadPose *pose, CourseState *cs, CourseRing *ring,
                            const uint8_t *stream);
void rm_draw_hud(const HudState *s, const HudAssets *a, Framebuffer *fb);
void rm_gobj_prefix(GobjPrefixState *s, const GobjPrefixAssets *a);
void rm_gobj_hud_view(const GobjPrefixState *g, HudState *hud);
void rm_player_update(PlayerState *p, const PlayerAssets *a, uint8_t *ctrl, RmEventCtx *ctx);
void rm_course_probe(RmEventCtx *c);
void rm_course_events(RmEventCtx *c);
void rm_course_mode_event(RmEventCtx *c, int16_t *obj_shade, uint16_t *screen_offset,
                          uint8_t *race_pal, RmPaletteWrite *out);
void rm_crash_fx_update(RmEventCtx *c);
void rm_init_leg_dash(RmEventCtx *c);      /* rebuild the current leg's dashboard graphic + seed the marker (src/events.c) */
void rm_seed_leg_dash_marker(RmEventCtx *c); /* re-seed ONLY the dash marker (marker-only; src/events.c) */
void rm_draw_leg_labels(RmEventCtx *c);    /* draw the current leg's place-name labels onto the dashboard (src/events.c) */
void rm_init_leg(PlayerState *p, CourseState *cs, RoadPose *pose, ScrollState *scroll,
                 CourseRing *ring, EventState *ev, GobjPrefixState *gobj, SpriteState *sprite,
                 uint8_t *hud_text, int16_t *obj_shade, uint16_t *screen_offset, uint8_t *race_pal,
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
#ifdef GAME_STE
extern long Cconin(void);      /* GEMDOS 0x01: block for a keypress (STE-build bail message) */
#endif
extern void Vsync(void);
extern long Setscreen(long logLoc, long physLoc, short rez);   /* flip the video base (latches at vblank) */
extern long Physbase(void);                                    /* current video base (to restore on exit) */
extern void Setpalette(const void *pal16);
extern long Setcolor(short idx, short color);                  /* color -1 reads a register without writing */
extern long Setexc(short number, long vector);
extern void Ikbdws(short count_m1, const void *buf);
extern void Dosound(const void *list);        /* XBIOS 32: play a YM2149 command list (TOS steps it per VBL) */
extern long Supexec(long (*func)(void));       /* XBIOS 38: run func in supervisor mode, return to user */

/* Held-key + joystick state, maintained by the IKBD interrupt handler in os.s. key_down/key_hit are
 * indexed by scancode; joy_state is joystick 1 (the game port), updated from each joystick report. */
extern volatile uint8_t key_down[128];
extern volatile uint8_t key_hit[128];
extern volatile uint8_t joy_state;
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

#define SCANCODE_COUNT 128        /* key_down / key_hit are indexed by the full 7-bit scancode space */

/* Drain every latched keypress (the Crawio key-drain @0x25de), so a key pressed to skip the jingle does
 * not carry into the leg select that follows. */
static void drain_key_hits(void) {
    for (int i = 0; i < SCANCODE_COUNT; i++) key_hit[i] = 0;
}

/* Any latched keypress? Used by the wait-for-a-fresh-key busy-waits (Help pause, F6 preview), each of
 * which drains the latches FIRST so a set latch here is genuinely fresh (not a stale race latch — the
 * reason the general leg-select waits use read_input instead; see op_wait_music_off). */
static int any_key_hit(void) {
    for (int i = 0; i < SCANCODE_COUNT; i++) if (key_hit[i]) return 1;
    return 0;
}

/* ST keyboard scancodes. */
#define SCAN_ESC 0x01             /* ESC = abort the race back to the intermission (main @0x10100:286) */
#define SCAN_Q 0x10               /* Q = quit to the desktop (the one documented deviation; see the header) */
#define SCAN_G 0x22               /* G = toggle dsp_toggle (hide/show the dashboard variant; main @0x10100:296) */
#define SCAN_SPACE 0x39
#define SCAN_UP 0x48
#define SCAN_DOWN 0x50
#define SCAN_LEFT 0x4b
#define SCAN_RIGHT 0x4d
#define SCAN_F1 0x3b              /* F1..F5 = 0x3b..0x3f: leg select (as init_playfield's function menu) */
#define SCAN_F6 0x40              /* F6 = 0x40: results-screen preview (ip_menu @0x2b86) */
#define SCAN_F10 0x44             /* F10 = 0x44: graphics / score-table reload prompt (ip_menu @0x2b36) */
#define SCAN_RETURN 0x1c          /* Return: confirms the F10 reload (ip_menu @0x2b50 — ASCII 0x0d) */
#define SCAN_HELP 0x62            /* Help = pause the race, silence sound, resume on any key (main @0x10100:293) */
/* IP_LEG_COUNT (the leg-select F-key range) lives in flow.h, shared with the flow + the RM_FKEY_* codes. */

/* Q, latched-edge: quit to the desktop. This is the SINGLE deliberate deviation from the original, a
 * coin-op that never terminates (main @0x10100 is an infinite loop) — a GEMDOS .PRG needs some way back
 * to the desktop, so Q (a key the original never reads) is it. ESC does NOT quit; it aborts the race
 * back to the intermission, exactly as the original does. Polled once per frame in the race loop and
 * every menu/attract loop; sets s->quit and unwinds so main's exit (screen + palette restore) runs. */
static int quit_requested(void) { return take_key_hit(SCAN_Q); }

#define VEC_IKBD_ACIA 0x46           /* 68000 vector 0x46 (@0x118): MFP channel 6, the IKBD ACIA */
#define IKBD_MOUSE_OFF 0x12
#define IKBD_MOUSE_RELATIVE 0x08     /* the mode TOS leaves the mouse in; restored on exit */
/* The "any real input" bits read_input tests to give the joystick priority over the keyboard: up 1 /
 * down 2 / left 4 / right 8 / fire 0x80 (recreate input.c INPUT_ACTIVE_MASK). */
#define RM_IN_ACTIVE_MASK 0x8f
#define IKBD_INTERROGATE_JOYSTICK 0x16   /* read_joystick @0x12110 pokes the ACIA with this each frame */
/* Joystick INTERROGATION mode: the IKBD sends NO unsolicited joystick reports (event-mode 0xFD and the
 * single-stick 0xFE/0xFF) — the stick answers only a 0x16 interrogate (HD6301 protocol). Pins the report
 * stream instead of trusting the TOS boot default; installed alongside mouse-off in kbd_install. */
#define IKBD_JOY_INTERROGATE_MODE 0x15

/* The prefix mutates its arenas (marker records, buf_a anim-word mirrors, the animated colour). The
 * anim-word mirrors land inside buf_a's record region (offsets 0xd70/0x1250), which the object
 * dispatcher then reads — so buf_a must be a MUTABLE copy of the fixture for the prefix write to be
 * seen by the draws, exactly as recreate's g_draw_game_objects does. The marker records + animated
 * colour are off-frame (this frame's marker slot is inactive), so they go to BSS scratch. */
static uint8_t ctrl[RM_CTRL_ALLOC_BYTES] __attribute__((aligned(2)));    /* BSS: per-frame control-long table */
static uint8_t scanline[RM_SCANLINE_BYTES] __attribute__((aligned(2)));  /* BSS: build_road_geometry scratch */
static uint8_t shifted[RM_SCROLL_SHIFTS * RM_SCROLL_WINDOW] __attribute__((aligned(2)));  /* pre-rotated scroll copies */
/* The phase-7 dashboard is a fixed-per-leg opaque graphic; rm_hud_dashboard_prebuild renders it once into
 * this buffer and rm_draw_hud bulk-copies it per frame (PERF: skips the masked blit's source reads). It is
 * rebuilt only when the dashboard art changes — leg setup (op_rebuild_dash / op_draw_leg_labels) and the
 * per-wrap progress-marker move (probe_collision, in game_update_step's wrap block) — flagged by
 * dash_pristine_dirty so draw_frame refreshes it exactly then. Starts dirty so the first draw builds it. */
static uint8_t dash_pristine[RM_HUD_DASH_PRISTINE_BYTES] __attribute__((aligned(2)));
static int dash_pristine_dirty = 1;
static uint8_t buf_a_ram[ARENA_BUF_A_BYTES] __attribute__((aligned(2)));  /* mutable buf_a copy (prefix writes mirrors) */
static uint8_t arena_block[RM_ARENA_BYTES] __attribute__((aligned(2)));   /* COURSES.DAT + unpacked GRAPHICS.GRA */
/* The live ring serialized back into the original's flat ST-byte row grid — the object-list
 * dispatcher's two flag streams walk this (rebuilt after every course advance). The other ring
 * consumers (sprite count, ground markers, sprite gates) read the native CourseRing directly.
 *
 * This grid is ALSO the marker-decay arena rm_gobj_prefix mutates: in the original both are the one
 * block at A_obj_markers, and the decay base is 8 bytes below it (A_marker_decay_base), indexed by an
 * even horizon row 0..0x2e — so the walk reaches RING_ST_DECAY_BIAS bytes below row 0 and a few past
 * the last row. Hence the padded block and the biased base handed to the prefix: without that wire the
 * decay writes land nowhere and a kicked roadside object never animates away (it just vanishes).
 * The pad is inert here, which is faithful at the high end and NOT at the low end:
 *   - high pad: the original's is the head of road_curve_tbl, which rm_build_road_geometry rewrites
 *     later in the same frame, so absorbing those writes changes nothing.
 *   - low pad: the original's first word is RoadPose.seg_data[12] (game.h: seg_data[11]/[12] ARE
 *     marker_slope_src / marker_decay_base), which the port models natively. So a decay armed on a
 *     horizon_row == 0 frame zeroes that slope byte in the original and only the pad here. Left as a
 *     KNOWN residual rather than fixed blind: routing the low pad into the native seg_data needs its
 *     own differential, and this wire is already the difference between an animation and none. See
 *     STATUS.md's play-test table. */
#define RING_ST_DECAY_BIAS 8    /* A_obj_markers - A_marker_decay_base */
#define RING_ST_DECAY_SPILL 8   /* the decay walk's reach past the last row (max index 0x1ce) */
static uint8_t ring_st_block[RING_ST_DECAY_BIAS + RM_RING_ROWS * RM_RING_ROW_BYTES + RING_ST_DECAY_SPILL]
    __attribute__((aligned(2)));
static uint8_t *const ring_st = ring_st_block + RING_ST_DECAY_BIAS;
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
/* The name-entry score-line region (the score-line string + the "TIME nn" digits rm_hiscore_countdown
 * writes) as MUTABLE RAM. It sits in the gap between hud_text_ram and highscore_ram, so it is a separate
 * seed (fixture_score_line); rm_draw_results_screen reads it as the score-line string. */
static uint8_t score_line_ram[sizeof fixture_score_line] __attribute__((aligned(2)));

/* Seed the persistent hi-score table from its baked default (fixture_highscore == init_scoretable's
 * deterministic output). Shared by the boot seed and the F10 reload (op_reload_assets). */
static void seed_highscore_table(void) {
    memcpy(highscore_ram, fixture_highscore, sizeof fixture_highscore);
}

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
    const RmResultsScreenAssets *res_screen_assets;   /* the race-end / name-entry results screen */
    /* leg-start "get ready" palette flash (ip_start_leg): a mutable 16-word palette the flash animates
     * from the obj-low flash tables (s->low + OBJ_LOW_LEG_FLASH_*). Off-image — only the colours a
     * human/screenshot sees; the byte-compare and the golden are palette-agnostic. The flash's frame
     * counter is the SHARED GobjPrefixState.anim_counter (pfx above), not a private one, so it carries
     * the preceding race/demo's animation history exactly as the original does (see op_flash_frame). */
    uint8_t *leg_start_pal;             /* mutable 16-word (32-byte) palette buffer */
    /* The mutable in-race palette (RM_RACE_PAL_BYTES): seeded from fixture_palette at each leg start,
     * then mode 4 / rm_init_leg's phase 11 stage a record's colours into regs 5-11 (off-image seam).
     * start_leg loads it (the leg-start staged palette); mode 4 reloads it each tunnel-palette event. */
    uint8_t *race_pal;
    /* the flow driver's input sources (the shell owns the IKBD seam): the joystick/key poll and the
     * leg-select F-key pick. main repoints them per flow call (attract vs leg-select, auto vs keyboard),
     * exactly as the old composition passed an input_of / fkey_leg function pointer down. */
    uint16_t (*input_source)(void);
    int (*fkey_source)(void);
    int shown;                          /* index of the on-screen buffer; the back buffer is shown ^ 1 */
    int quit;                           /* set when Q is seen in any loop; the outer loop unwinds + restores */
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

/* Bundle the shell's per-race owner structs + const assets + scratch buffers into an RmScene — the
 * one handle rm_draw_frame (src/frame.c) takes. Built fresh each frame from the Shell; every pointer
 * is stable (the owner structs live for the whole run, the scratch buffers are module statics), so
 * this is pure pointer plumbing, no per-frame cost that matters. The obj-low list bases resolve the
 * two fixture offsets the composition walks. */
static RmScene shell_scene(const Shell *s) {
    RmScene sc = {
        .pfx = s->pfx, .pose = s->pose, .ring = s->ring, .scroll = s->scroll,
        .ground = s->ground, .sprite = s->sprite, .objlist = s->objlist, .object = s->object,
        .hud = s->hud, .road = s->road,
        .pfx_assets = s->pfx_assets, .src = s->src, .ground_assets = s->ground_assets,
        .sprite_assets = s->sprite_assets, .hud_assets = s->hud_assets,
        .ctrl = ctrl, .scanline = scanline, .shifted = shifted, .ring_st = ring_st,
        .hud_text = hud_text_ram,        /* live: the dispatcher's p24 gate re-reads score_str[1] */
        .obj_sprite_disp = s->low + OBJ_LOW_SPRITE_DISP, .obj_fixed_list = s->low + OBJ_LOW_LIST_BASE,
    };
    return sc;
}

/* Run the full ported render pipeline into `fb` via the hoisted composition (rm_draw_frame). The
 * shell keeps only the buffer selection (screen_buf / Setscreen, above) + the scene plumbing; the
 * draw order and the no-per-frame-clear invariant live in src/frame.c now (the buffers are cleared
 * once in main(); repainting over two-frames-old content is byte-identical to over zeros). */
static void draw_frame(const Shell *s, Framebuffer *fb) {
    if (dash_pristine_dirty) {          /* refresh the prebuilt dashboard after any art change (rare) */
        rm_hud_dashboard_prebuild(s->hud_assets, dash_pristine);
        dash_pristine_dirty = 0;
    }
    RmScene sc = shell_scene(s);
    rm_draw_frame(&sc, fb);
}

/* Fan rm_player_update's outputs out to the render structs — the whole of the "game loop" beyond
 * running the physics and drawing. The derivation itself is hoisted into rm_apply_player (src/
 * gameplay.c) so `make test` exercises it host-side; this wrapper only unpacks the Shell and supplies
 * the shell-owned edge table (fixture_road_edge + ROAD_EDGE_PAD). */
static void apply_player(const Shell *s) {
    rm_apply_player(s->player, s->ev, s->pose, s->scroll, s->sprite, s->ground, s->objlist,
                    s->hud, s->road, fixture_road_edge + ROAD_EDGE_PAD);
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
     * is rebuilt where the leg changes (the leg-select nav gate + Phase B, via op_rebuild_dash). */
    rm_seed_leg_dash_marker(s->ctx);
    /* Seed the in-race palette from fixture_palette; rm_init_leg's phase 11 then stages this leg's
     * object-display record over regs 5-11 (the same seam mode 4 re-stages). */
    memcpy(s->race_pal, fixture_palette, RM_RACE_PAL_BYTES);
    rm_init_leg(s->player, s->course, s->pose, s->scroll, s->ring, s->ev, s->pfx, s->sprite,
                hud_text_ram, s->obj_shade, s->screen_offset, s->race_pal, s->init_assets, leg);
#ifdef GAME_TIME_LEFT
    /* Debug builds only: shorten the leg's bonus clock so a headless idle trace reaches the time-out
     * (and thus the leg end) in ~140 frames instead of ~800. A restart re-seeds the FULL clock from
     * rm_init_leg first, so a restart shows time_left jumping back up before this shortens it again. */
    s->player->time_left = GAME_TIME_LEFT;
#endif
    rm_scroll_prebuild(s->arena->gfx + *s->screen_offset, shifted);   /* screen_offset is per-leg */
    s->object->shade = *s->obj_shade;
    /* objlist's bonus_timer / p24_flag are NOT derived here: they are live globals the dispatcher
     * reloads every frame, so rm_draw_frame refreshes them (src/frame.c). Deriving them once at a leg
     * start is what froze them — the bonus window never clamped and the p24 gate never re-read the
     * checkpoint-bumped score digit. */
    apply_player(s);
    ring_views_refresh(s->ring, s->ground, s->sprite);
    s->race_input_prev = 0;
    /* A real race runs with game_over CLEAR — reset the event ctx's mirror of it here (the single funnel
     * for every race entry), matching the zeroed player struct above. The attract demo re-raises both
     * mirrors after this (op_start_demo_leg), so a demo cycle can't leave game_over stuck for the next
     * real leg. game_over_flag (the flow's own counter) is a separate global the flow brackets. */
    s->ctx->game_over = 0;
    /* The race palette, set in ONE place so every race entry (boot / leg-select fire / R / attract
     * Phase B) agrees. It is race_pal — fixture_palette (0x17fa2) with phase 11's staging applied, as
     * the original loads 0x17fa2 after init_leg staged it; an off-image seam (byte-compare is
     * palette-agnostic, so the staged regs move no compared surface). */
    Setpalette(s->race_pal);
    dash_pristine_dirty = 1;   /* every race entry re-prebuilds the dashboard (the leg's art is now set) */
}

/* The mode-6 tunnel poke targets hardware colour register (ST_PAL_POKE_BASE + reg_sel), as recreate's
 * g_poke_color_reg does; Setcolor takes a register INDEX instead, so the byte address is folded back to
 * an index against the palette base. (reg_sel is 4 in the shipped data -> 0xffff8250 -> register 8.) */
#define ST_PAL_BASE      0xffff8240L   /* ST palette register 0 */
#define ST_PAL_POKE_BASE 0xffff824cL   /* g_poke_color_reg pokes this + reg_sel */
#define ST_PAL_REG_BYTES 2             /* ST palette registers are one word apart: byte offset / this = register index */

/* Fire the pulled record's mode-2/4/6 event (rm_course_mode_event). The compared state (obj_shade,
 * screen_offset, the EventState scalars) is owned by the core; the shell owns the three side effects it
 * cannot: propagating obj_shade to the draw (mode 4), re-prebuilding the scroll copies when
 * screen_offset moved (mode 2), and issuing the actual palette write (mode 4 Setpalette / mode 6
 * per-register Setcolor — off-image seams the byte-compare and golden do not see). */
static void course_mode_event(Shell *s) {
    RmPaletteWrite pw;
    uint16_t screen_off_before = *s->screen_offset;
    rm_course_mode_event(s->ctx, s->obj_shade, s->screen_offset, s->race_pal, &pw);
    s->object->shade = *s->obj_shade;                                     /* mode 4 changed obj_shade */
    if (*s->screen_offset != screen_off_before)                          /* mode 2 changed screen_offset */
        rm_scroll_prebuild(s->arena->gfx + *s->screen_offset, shifted);
    if (pw.kind == RM_PAL_SETPALETTE) {                                  /* mode 4 (seam) */
        Setpalette(s->race_pal);
    } else if (pw.kind == RM_PAL_POKE_REG) {                             /* mode 6 (seam) */
        /* Fold the poked byte address back to a Setcolor register index. reg_sel is taken UNSIGNED (no
         * sign-extend): valid tunnel data never yields a negative or odd selector — its high bit and
         * bit 0 are always clear — so widening it unsigned changes nothing (a reviewer verified this
         * against the shipped course data). */
        short reg_idx = (short)((ST_PAL_POKE_BASE + (unsigned short)pw.reg - ST_PAL_BASE) / ST_PAL_REG_BYTES);
        Setcolor(reg_idx, (short)pw.color);
    }
}

/* One race-frame UPDATE (no draw): run the driving model over the geometry the last frame built,
 * advance the course on a view-wrap (the same order as recreate's game_update.c §12), then the crash
 * / end-of-race tally. Returns 1 when the leg ENDS (abort_flag < 0), else 0. The caller draws + flips.
 * The wrap-frame block mirrors the shell's original inline body one-for-one. */
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
        rm_course_probe(s->ctx);            /* may move the dashboard progress marker (probe_collision) */
        /* The whole wrap block can rewrite the dashboard art: rm_course_probe's probe_collision moves the
         * marker, and rm_course_events (below) can rebuild it outright on a checkpoint (init_leg_dash +
         * draw_leg_labels) or re-probe on a collision. Flag it dirty unconditionally here, before those
         * run, so ANY of them is covered — do NOT narrow this to "only when the marker moved". */
        dash_pristine_dirty = 1;
        bool pulled = rm_road_course_advance(s->pose, s->course, s->ring, s->stream);
        rm_build_road_geometry(s->pose, s->src, s->ring, ctrl, scanline);
        if (pulled) course_mode_event(s);   /* mode 2/4/6: screen_offset / obj_shade / palette */
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

/* ==== C1: the vsync-locked 25 fps presentation cadence (PERF30 Tier-C C1) ==========================
 *
 * A free-running 50 Hz vblank clock (bumped by the VBL pump, vbl_sound below) lets the flip land on a
 * REGULAR cadence instead of free-running. Without the lock, each frame flips on whatever vblank the
 * render happens to finish near (a Setscreen + one Vsync), so the present-to-present gap jitters with the
 * render's phase against the 50 Hz grid — 5, 6, 7 vblanks frame to frame. The lock quantizes every flip
 * onto a fixed 2-vblank grid: consecutive frames present exactly 2 / 4 / 6 ... vblanks apart (the honest
 * ST vsync cadences: 25 / 12.5 / 8.3 fps). A frame lighter than one grid slot waits for it; a heavier
 * frame quantizes UP to the next even boundary. Fidelity trade: NONE in pixels — the frame drawn is the
 * same bytes, only WHEN it is shown moves. Game logic is frame-stepped (one game_update_step per drawn
 * frame; every clock is a per-frame counter — bonus time, TIME entry, crash timer), so the lock never
 * changes what is computed on which frame, only the presentation pacing. Still tearing-free: the flip is
 * a Setscreen (base poked mid-frame) that the shifter latches at the next vblank, which the flip's Vsync
 * lands on — exactly as before, just on a chosen boundary. GAME_PRESENT_FREERUN compiles the lock out
 * (the pre-C1 free-running behaviour), used to MEASURE the baseline cadence.
 *
 * WAIT DESIGN: the wait is the shell's existing Vsync() — its per-vblank primitive. Vsync services the
 * VBL sound pump (which runs in the very vblank Vsync waits for), so the pump's 50 Hz tempo and the IKBD
 * interrupt keep running untouched while we idle whole vblanks. On-target CPU idling buys nothing here
 * (no background work to overlap), so the plain Vsync spin is the simplest correct form — a busy-poll of
 * vbl_count or a stop #0x2300 halt would be strictly more code for no benefit. The pump coexists cleanly:
 * vbl_count is a single-writer (the VBL hook) / single-reader (this main line) 32-bit counter, and a
 * 68000 addq.l / move.l on it is one indivisible instruction, so no lock or torn read is possible (same
 * argument as snd_lock_depth's; the counter and the sound guard are independent). */
/* LIVENESS: the clock only ticks while the VBL pump is installed — show_surface's boundary wait would
 * spin forever otherwise. Safe today by ordering (install_sound precedes the first show_surface; the
 * exit path flips via raw Setscreen after uninstall_sound) — keep that ordering if either moves. */
static volatile uint32_t vbl_count;    /* free-running 50 Hz vblank clock, incremented in vbl_sound */

#ifndef GAME_PRESENT_FREERUN
#define PRESENT_QUANTUM_VBLS 2         /* present only every 2nd (even) vblank: the 25 fps vsync-lock cap */
static uint32_t present_target;        /* the vbl_count the next flip lands on; a fixed PRESENT_QUANTUM grid */

/* Idle whole vblanks until one short of the next cadence boundary, so the caller's own flip Vsync lands
 * ON present_target. present_target lives on a fixed 2-vblank grid (BSS-zero, only ever += the quantum,
 * so every value is a grid slot): each flip advances to the next slot, and a frame that overran its slot
 * steps the grid forward to the first slot strictly ahead of now (the "<= 0" keeps one vblank of headroom
 * to land on). Consecutive flips therefore land present_target apart — always a multiple of the quantum —
 * so the cadence is even-spaced, never free-running. */
static void present_wait_boundary(void) {
    present_target += PRESENT_QUANTUM_VBLS;
    while ((int32_t)(present_target - vbl_count) <= 0)          /* frame overran: skip to the next grid slot */
        present_target += PRESENT_QUANTUM_VBLS;
    while ((int32_t)(vbl_count - (present_target - 1)) < 0)     /* idle to one vblank before the boundary */
        Vsync();
}
#endif

#ifdef GAME_CADENCE_TRACE
/* SCRATCH cadence instrument (not shipped): record the vblank SPAN of each present — the delta of the
 * 50 Hz clock across a full flip — so a headless autodrive run yields the before/after cadence
 * distribution (build GAME_PRESENT_FREERUN for the baseline, plain for the locked cadence). Dumped to
 * SCREEN.BIN on autodrive exit, padded like flow_trace_dump so the standard runner picks it up. */
#define CADENCE_SLOTS GAME_CADENCE_TRACE
static uint16_t cadence_log[CADENCE_SLOTS];
static uint16_t cadence_pos;
static uint32_t cadence_last_vbl;
static void cadence_record(void) {
    uint32_t now = vbl_count;
    uint16_t span = (uint16_t)(now - cadence_last_vbl);
    cadence_last_vbl = now;
    if (cadence_pos < CADENCE_SLOTS) cadence_log[cadence_pos++] = span;
}
static void cadence_dump(void) {
    uint8_t *buf = screen_buf(0)->px;
    memset(buf, 0, SCREEN_BYTES);
    uint16_t *w = (uint16_t *)buf;
    w[0] = cadence_pos;
    for (int i = 0; i < cadence_pos && (i + 2) * 2 <= SCREEN_BYTES; i++) w[1 + i] = cadence_log[i];
    long h = Fcreate("SCREEN.BIN", 0);
    if (h >= 0) { Fwrite((short)h, SCREEN_BYTES, buf); Fclose((short)h); }
}
#endif

/* Flip the video base to the back buffer at the vblank (no tearing) and make it the shown one. Callers
 * paint the back buffer (via back_buffer / draw_frame) first; this owns the flip + the shown toggle so
 * no caller repeats the derive-toggle bookkeeping. The C1 boundary wait (above) idles to one vblank
 * before the next even cadence slot; the Setscreen + Vsync then latch the flip ON that slot. */
static void show_surface(Shell *s) {
    Framebuffer *fb = screen_buf(s->shown ^ 1);
#ifndef GAME_PRESENT_FREERUN
    present_wait_boundary();                 /* C1: quantize the flip onto the even-vblank cadence grid */
#endif
    Setscreen(-1L, (long)fb->px, -1);        /* poke the base; the shifter latches it at the next vblank */
    Vsync();                                 /* land on the boundary vblank: the new buffer is now visible */
    s->shown ^= 1;
#ifdef GAME_CADENCE_TRACE
    cadence_record();                        /* scratch: log this present's vblank span (before/after evidence) */
#endif
}

/* Render the race pipeline into the back buffer and show it (draw_frame + show_surface). */
static void render_and_show(Shell *s) {
    draw_frame(s, back_buffer(s));
    show_surface(s);
}

/* The leg-start "3-2-1-GO" countdown (original main @0x10226-0x10254; recreate game_main.c:402-405):
 * stop_music(BEEP) ×3 then stop_music(GO), each paced by a Vsync wait. Each stop_music parks the VBL
 * music pump (so the get-ready tune goes quiet) and hands the beep list to XBIOS Dosound, which TOS's
 * kept _vblqueue entries step over the wait — that is what makes the beeps audible. game_over is 0 here
 * (a real race entry). The original folds a road-scroll-offset write into each wait (wait_vbl_set_offset
 * @0x102ee); the remaster's screen_offset is already set by start_leg's prebuild and does not animate
 * pre-race, so this is a pure pacing wait. */
#define RACE_START_BEEPS       3    /* three "3-2-1" beeps, then the GO tone */
#ifdef GAME_FLOW_FAST
#define RACE_START_BEEP_VSYNCS 2    /* debug: keep a headless flow trace snappy (the beeps still fire) */
#else
#define RACE_START_BEEP_VSYNCS 51   /* wait_vbl_set_offset @0x102ee: 0x32+1 Vsyncs (~1 s/beep) */
#endif
static void race_start_countdown(Shell *s) {
    for (int beep = 0; beep < RACE_START_BEEPS + 1; beep++) {
        uint16_t list = beep < RACE_START_BEEPS ? SND_DOSOUND_BEEP : SND_DOSOUND_GO;
        rm_stop_music(s->ctx->snd, list, false);
        for (int v = 0; v < RACE_START_BEEP_VSYNCS; v++) Vsync();
    }
}

/* Wait for the trigger key `scancode` to be released (draining its IKBD auto-repeat) then for any fresh
 * key — the shared body of the Help pause (main @0x10100:2ac..2d0) and the F6 preview (ip_menu
 * @0x2bc4/0x2bd8). Vblank-paced. It deliberately does NOT drain the fresh key: each caller drains after,
 * and pause_race must first peek Q out of it (a Q-to-resume still quits) — so the final drain can't live
 * here. Shell-only (game_main.c is never compiled by `make test`; see STATUS). */
static void wait_key_release_then_fresh(int scancode) {
    while (key_down[scancode]) Vsync();            /* wait for release: drain the trigger key's auto-repeat */
    drain_key_hits();                              /* so the fresh-key wait sees only a genuinely new press */
    while (!any_key_hit()) Vsync();                /* wait for any fresh key */
}

/* Help-key pause (main @0x10100:293-309): freeze the race and silence the sound (rm_pause_silence: TURNOFF
 * + EGOFF + fxflag clear; the VBL pump stays RUNNING, so it plays silence rather than being parked), wait
 * for the Help auto-repeat to end then for any fresh key, then drain the resume key. The final drain
 * protects the race loop's edge-triggered keys (the ESC/G/Help/Q take_key_hit polls) from a stale latch —
 * steering reads key_down levels, not latches, so it is unaffected. A Q pressed to resume must still quit,
 * so capture it BEFORE the drain eats it. The engine sound resumes on its own via the per-frame
 * rm_sound_engine_update once the race continues. */
static void pause_race(Shell *s) {
    rm_pause_silence(s->ctx->snd);
    wait_key_release_then_fresh(SCAN_HELP);
    if (take_key_hit(SCAN_Q)) s->quit = 1;         /* a Q-to-resume still quits (peek it before the drain) */
    drain_key_hits();                              /* drain the resume key so it doesn't leak into the race loop's edge keys */
}

/* ---- the between-legs flow palettes (all inside the obj-low program-data blob; an off-image seam —
 * the byte-compare is palette-agnostic, so these only affect the colours a human/screenshot sees). ---- */
static void set_palette(const Shell *s, uint32_t off) { Setpalette(s->low + off); }

/* Take the IKBD interrupt so held keys AND the joystick are visible (see os.s). Two mode commands PIN
 * the ACIA's report stream rather than trusting the TOS boot default: 0x12 turns mouse reporting off,
 * and 0x15 puts the joystick in INTERROGATION mode — no unsolicited event reports (0xFD/0xFE/0xFF), the
 * stick answers only a 0x16 interrogate — so the ACIA delivers nothing but scancodes and our own
 * interrogate replies. kbd_isr's packet parser routes those replies to joy_state and keeps scancodes out
 * of key_down[]; read_input then kicks a 0x16 each frame and reads the reply from joy_state. */
static long kbd_install(void) {
    static const uint8_t modes[] = {IKBD_MOUSE_OFF, IKBD_JOY_INTERROGATE_MODE};
    Ikbdws(sizeof modes - 1, modes);
    return Setexc(VEC_IKBD_ACIA, (long)kbd_isr);
}

static void kbd_remove(long old_vector) {
    static const uint8_t restore[] = {IKBD_MOUSE_RELATIVE};
    Setexc(VEC_IKBD_ACIA, old_vector);
    Ikbdws(sizeof restore - 1, restore);
}

/* Kick this frame's joystick interrogate (IKBD command 0x16), the role of read_joystick @0x12110. The
 * original — running SUPERVISOR — pokes the ACIA data register directly; this shell is a user-mode
 * GEMDOS program, where the ACIA at 0xfffffc00 is supervisor-only (a raw poke bus-errors), so the
 * command goes through the BIOS instead (Ikbdws, XBIOS 25). The reply — a 0xFD joystick report — still
 * comes back through our own ACIA vector into kbd_isr, which parses it into joy_state. (kbd_isr's raw
 * ACIA reads are fine: interrupt handlers always run supervisor.) */
static void interrogate_joystick(void) {
    static const uint8_t cmd[] = {IKBD_INTERROGATE_JOYSTICK};
    Ikbdws(sizeof cmd - 1, cmd);
}

/* Poll the input, joystick-priority — read_input @0x120b0 / recreate input.c. Kick this frame's
 * interrogate first (its reply, parsed by kbd_isr into joy_state, is consumed on the NEXT frame,
 * exactly as the original's async joyvec delivery works). If the stick reports any active bit it wins
 * and the keyboard is ignored (input.c:32 `(input_state & 0x8f) != 0`); joy_state's bits are the RM_IN_*
 * bits (game.h), so it is returned as-is (its high byte, the mouse-port stick, is 0 — the game consumes
 * only joystick 1). Otherwise fall back to the arrow keys + Space, as the original does.
 * joy_state RETAINS the last interrogate reply, so if a reply is ever lost the previous stick state
 * stands — there is no timeout that falls back to the keyboard while the stick is held. This mirrors the
 * original's async joyvec delivery (the game reads whatever the last snapshot left); by design. */
static uint16_t read_input(void) {
    interrogate_joystick();
    uint16_t joy = joy_state;
    if ((joy & RM_IN_ACTIVE_MASK) != 0) return joy;
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

/* ==== sound (slice 3): make the wired triggers AUDIBLE on the 68000 ================================
 *
 * Slices 1+2 gave a fully-driven SoundDriver whose YM2149 (reg,val) stream rm_refresh returns but never
 * plays — the driver state is verified host-side, the chip stays silent. This section closes that seam:
 * a 50 Hz VBL pump writes rm_refresh's stream to the PSG, and the Dosound trigger seam plays the baked
 * command lists through the real XBIOS. It mirrors recreate/render/atari/game_main.c (which solved this
 * on-target) with one structural difference — the remaster shell runs USER mode (Setexc/Ikbdws/Setscreen
 * traps, GEMDOS SCREEN.BIN dumps), so the two supervisor touch-points are reached differently:
 *   - the VBL handler runs supervisor anyway (TOS calls the queue at interrupt), so its PSG pokes are fine;
 *   - the one-shot install (the TOS VBL queue + conterm, both supervisor-only low memory) runs in a brief
 *     Supexec excursion instead of flipping the whole program supervisor (which would run the golden /
 *     flow-trace GEMDOS dumps supervisor and risk the handle-0 GEMDOS-HD bug os.s's header warns about).
 *
 * VBL REENTRANCY — why a guard, and why a FLAG not an SR-mask. The pump calls rm_refresh on the SAME
 * SoundState the main loop mutates through the sound_trig leaves (rm_inittune / rm_stop_music / …). The
 * original 68k asm publishes a tune change safely by instruction ORDER (mzflag cleared first, records
 * rewritten, mzflag set last); -O3 C gives no such guarantee, so a VBL landing mid-mutation could
 * rm_refresh a half-written record. The mitigation is RM_SOUND_LOCK/UNLOCK (sound.h) bracketing each
 * leaf's mutation; here they are a nesting COUNTER (snd_lock_depth) the pump checks. Because a VBL is an
 * interrupt, it runs ATOMICALLY w.r.t. the main line (the CPU is single-threaded): a VBL either sees the
 * counter clear — and then the main line is provably NOT mid-mutation (a leaf only clears the counter
 * after finishing) — or sees it nonzero and SKIPS this frame's refresh. That is full mutual exclusion.
 * The counter is set only around the tiny per-leaf mutation (a few µs), NOT the whole ~150 ms game frame,
 * so a skip is rare and costs at most one 20 ms frame of held PSG state (inaudible) — masking the pump
 * for the whole frame would instead wreck REFRESH's 50 Hz tempo. An SR-mask (defer rather than skip)
 * would be marginally nicer but needs supervisor (`move #x,sr`), which this user-mode shell hasn't got;
 * the counter is correct in user mode and is exactly the "shell-side guard the handler checks" shape. */

/* YM2149 ports (reached only from the VBL handler, which runs supervisor). */
#define PSG_SELECT (*(volatile uint8_t *)0xffff8800UL)   /* register-select port */
#define PSG_WRITE  (*(volatile uint8_t *)0xffff8802UL)   /* data-write port */

/* TOS low memory the one-shot install touches (all supervisor-only — reached via Supexec). */
#define SYS_NVBLS    (*(volatile int16_t *)0x454UL)      /* VBL-queue length */
#define SYS_VBLQUEUE (*(volatile uint32_t *)0x456UL)     /* -> array of VBL routine pointers */
#define SYS_CONTERM  (*(volatile uint8_t *)0x484UL)      /* console flags: bit1 = the TOS key-click */

#define TOS_VBL_SLOTS   8      /* how many displaced TOS VBL entries we preserve after our own (recreate) */
#define PSG_WRITE_CAP   SND_PSG_WRITES_MAX   /* the pump's per-frame PSG buffer/cap (sound.h): 14 writes */

/* Our VBL queue: slot 0 is the sound pump, slots 1.. are the TOS VBL routines we displace at install
 * (see vbl_install_super). The initializer's function address becomes an R_68K_32 reloc mkprg fixes up
 * at load (exactly as the flow_ops table does), so slot 0 points at the real vbl_sound. */
static void vbl_sound(void);
static void (*vbl_queue[1 + TOS_VBL_SLOTS])(void) = { vbl_sound };

static SoundDriver *volatile snd_ptr;      /* the driver the pump refreshes (set by install_sound) */
static volatile uint16_t snd_lock_depth;   /* nonzero while a trigger mutates SoundState: the pump skips */
static uint32_t saved_vblqueue;            /* the TOS _vblqueue pointer install displaced (restored on exit) */
static int16_t  saved_nvbls;               /* the TOS _nvbls count install displaced (restored on exit) */

/* RM_SOUND_LOCK/UNLOCK (sound.h) on the m68k build: the shell-provided VBL-reentrancy counter. A COUNTER
 * (not a flag) so an accidentally-nested lock can't clear the guard early — the four self-bracketing sound
 * primitives (sound.c) may nest inside a trigger's own bracket (rm_stop_music), and the counter absorbs
 * that. `addq/subq` on a word in memory is a single instruction the VBL never interrupts mid-way, and the
 * pump only READS the counter, so no read-modify-write race exists between them. The `memory` barrier keeps
 * the compiler from floating the SoundState stores across the counter update — correctness then survives a
 * future build inlining these (e.g. -flto), not just their being out-of-line calls (sound.h CONTRACT). */
void rm_sound_lock(void)   { snd_lock_depth++; __asm__ volatile("" ::: "memory"); }
void rm_sound_unlock(void) { __asm__ volatile("" ::: "memory"); snd_lock_depth--; }

/* The 50 Hz VBL sound pump — TOS calls this every vertical blank (supervisor). When the driver is RUNNING
 * and no trigger mutation is in flight, refresh one frame and write its YM2149 stream to the chip. When
 * PARKED (stop_music parked it) it does nothing — silence, exactly as the original's parked VBL vector.
 * snd_ptr is set by install_sound BEFORE the queue is spliced and stays valid until uninstall detaches the
 * queue, so it is never NULL here (no guard needed). */
static void vbl_sound(void) {
    vbl_count++;    /* C1: the free-running 50 Hz cadence clock — bumped every vblank, before any early-out */
    if (snd_ptr->vbl_enable != RM_VBL_RUNNING) return;
    if (snd_lock_depth) return;    /* a trigger is publishing a change: skip this frame (see the note) */
    uint8_t regs[PSG_WRITE_CAP], vals[PSG_WRITE_CAP];
    uint32_t n = rm_refresh((SoundState *)&snd_ptr->state, regs, vals, PSG_WRITE_CAP);
    for (uint32_t i = 0; i < n; i++) { PSG_SELECT = regs[i]; PSG_WRITE = vals[i]; }
}

/* Splice our sound pump in as _vblqueue[0], PRESERVING the TOS VBL routines after it (mirrors recreate /
 * the original main @0x101b8) — keeping them is what lets TOS's own per-VBL Dosound stepper run, which is
 * what plays the countdown beeps / engine idle; dropping them silenced them once (recreate SOUND handoff).
 * Save the displaced _vblqueue pointer + count so the exit path can restore them (vbl_uninstall_super).
 * Then kill the TOS key-click (conterm = 0; original main @0x101dc), else TOS pokes the YM on every key.
 * Runs under Supexec (supervisor) — every address here is supervisor-only low memory. */
static long vbl_install_super(void) {
    uint32_t *old_q = (uint32_t *)(uintptr_t)SYS_VBLQUEUE;
    int16_t old_n = SYS_NVBLS;
    saved_vblqueue = SYS_VBLQUEUE;                      /* remember what to restore on exit */
    saved_nvbls = old_n;
    if (old_n > TOS_VBL_SLOTS) old_n = TOS_VBL_SLOTS;
    for (int i = 0; i < old_n; i++) vbl_queue[1 + i] = (void (*)(void))(uintptr_t)old_q[i];
    SYS_NVBLS = 0;                                      /* detach while we swap the queue pointer */
    SYS_VBLQUEUE = (uint32_t)(uintptr_t)vbl_queue;
    SYS_NVBLS = (int16_t)(1 + old_n);
    SYS_CONTERM = 0;
    return 0;
}

/* Detach the pump: restore the TOS _vblqueue pointer + count install displaced, so TOS stops calling
 * vbl_sound. The mirror of vbl_install_super; runs under Supexec (supervisor low memory). */
static long vbl_uninstall_super(void) {
    SYS_NVBLS = 0;                                      /* detach before swapping the pointer back */
    SYS_VBLQUEUE = saved_vblqueue;
    SYS_NVBLS = saved_nvbls;
    return 0;
}

/* Point the pump at `snd` and install the VBL queue + conterm clear (the supervisor part via Supexec).
 * Idempotent-safe to call once at boot; after it the pump is live but silent until a trigger sets the
 * driver RUNNING. */
static void install_sound(SoundDriver *snd) {
    snd_ptr = snd;
    Supexec(vbl_install_super);
}

/* Detach the pump on exit (mirror of install_sound, like kbd_remove mirrors kbd_install): park the driver
 * so a final in-flight VBL is a no-op, then restore the TOS VBL queue — BEFORE main() Pterms, so TOS never
 * calls vbl_sound in the freed TPA (a random-timed crash otherwise). snd_ptr stays valid: the park below
 * dereferences it, and the queue is still live until the Supexec detaches it. */
static void uninstall_sound(void) {
    snd_ptr->vbl_enable = RM_VBL_PARKED;
    Supexec(vbl_uninstall_super);
}

#include "sound_dosound.h"     /* SND_DOSOUND: the five baked Dosound command lists (target build only) */

/* The on-target Dosound seam — replaces src/sound_trig.c's host ledger (compiled out under
 * RM_SOUND_TARGET, which build_game.sh always passes; the include + this definition are unconditional so
 * a dropped -D fails loudly as a duplicate-symbol link against that ledger, not a silently mute PRG).
 * rm_stop_music / rm_stop_music_chk call this with a SND_DOSOUND_* offset; hand TOS a pointer to that list
 * in the baked blob (XBIOS Dosound; TOS's kept _vblqueue entries step it). Every caller runs after
 * install_sound, so the queue always exists — no install guard needed. */
void rm_dosound(uint16_t list_off) {
    Dosound(SND_DOSOUND + list_off);
}

/* The BOOT fast path (skip the leg select, boot straight into a leg, dump frame 0). Enabled ONLY for
 * the golden harness (GOLDEN_BOOT_LEG=N — run_golden.py builds this variant to pin the frame-0 golden
 * against recreate's pipeline) and the headless autodrive race trace (GAME_AUTODRIVE — it cannot drive
 * the leg-select menu with a dead keyboard, so it boots the fixture leg directly). The SHIPPING
 * BUGGYBOY.PRG defines neither, so it has NO fast path and boots into the leg select. */
#if defined(GOLDEN_BOOT_LEG)
#define BOOT_FAST_LEG GOLDEN_BOOT_LEG
#elif defined(GAME_AUTODRIVE)
#define BOOT_FAST_LEG GAME_LEG_INDEX
#endif

#if defined(GAME_AUTODRIVE) && defined(GAME_FLOW_AUTO)
#error "GAME_AUTODRIVE and GAME_FLOW_AUTO are mutually exclusive: autodrive takes the BOOT_FAST_LEG path and boots straight into a leg, skipping the leg select the GAME_FLOW_AUTO flow trace exists to prove."
#endif

/* ---- headless drive + trace (debug builds only) --------------------------------------------------
 *
 * GAME_AUTODRIVE=N drives a fixed script instead of the keyboard and dumps the frame after N frames;
 * GAME_TRACE=N logs N frames of driving state to SCREEN.BIN instead. GAME_FLOW_TRACE adds a compact
 * PHASE-transition log so a headless run can prove the between-legs flow (leg end -> highscore ->
 * intermission A->B->C->D -> leg select -> fire -> leg) runs on the 68000, and GAME_FLOW_FAST shrinks
 * the attract phases so a whole cycle fits a bounded run (the phase counts are otherwise thousands of
 * frames). GAME_FLOW_AUTO scripts the flow inputs (auto-fire the leg select, auto-abort the attract).
 */
#ifdef GAME_AUTODRIVE
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

#ifdef GAME_TRACE
#define TRACE_WORDS 9
/* Round UP so the dump is >= SCREEN_BYTES whatever TRACE_WORDS is; never fewer slots than GAME_TRACE. */
#define TRACE_MIN_SLOTS ((SCREEN_BYTES + TRACE_WORDS * 2 - 1) / (TRACE_WORDS * 2))
#define TRACE_SLOTS (GAME_TRACE > TRACE_MIN_SLOTS ? GAME_TRACE : TRACE_MIN_SLOTS)
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

#ifdef GAME_FLOW_TRACE
/* One phase-transition record per event: (tag, leg, aux) — the aux carries a phase-specific scalar
 * (Phase-A/C frame count, the leg select's leg, etc.). Written to SCREEN.BIN on quit. The tags are the
 * between-legs flow's boundaries (RM_FLOW_EVT_*, flow.h); a headless run reads them back to confirm
 * A->B->C->D->restart, the leg-select fire, and the leg-end -> intermission -> leg-select round trip.
 * NB: at the six intermission event sites the driver now passes the flow's own leg_index as the leg
 * column (the pre-slice-D shell passed its race leg there); they differ on 2nd+ attract cycles / a
 * Phase-D abort / the select-idle path. Diagnostic only — the drawn frames and counters are unchanged. */
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

/* Re-read + unpack GRAPHICS.GRA into the arena (the original's load_graphics). Shared by the boot load
 * and the F10 reload. Returns 0 after naming the file at fault (Cconws is invisible under headless
 * Hatari, so the only symptom there is a missing SCREEN.BIN). */
static int load_graphics(RmArena *arena) {
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

/* Load the game's own data files and unpack the graphics — everything the render pipeline draws from.
 * Both must sit next to the .PRG. Returns 0 after naming the file at fault. */
static int load_assets(RmArena *arena) {
    rm_arena_init(arena, arena_block);
    if (read_file("COURSES.DAT", arena->course, RM_COURSE_FILE_BYTES) != RM_COURSE_FILE_BYTES) {
        Cconws("COURSES.DAT missing or wrong size\r\n");
        return 0;
    }
    return load_graphics(arena);
}

/* ---- the between-legs FLOW COMPOSITION (slice D): the driver is hoisted into src/flow.c
 * (rm_flow_intermission / rm_flow_leg_select / rm_flow_game_over — the prologue + phase A/B/C/D loop,
 * the leg-select loop, and the game-over bracket, mirroring g_intermission / g_init_playfield). This
 * file keeps only the 68000 implementations of the platform effects the driver orders, wired through a
 * FlowOps table over the Shell (ctx), so `make test` can lockstep the sequence against the oracle. The
 * composition constants that stay here are the ones the demo-leg pipeline callbacks own (Phase B's
 * warm-up + rev override, the attract demo input); the counter-owned seeds live in flow.h + FlowTuning. ---- */

#define INT_B_WARMUP   0x33        /* Phase-B settle: game_update iterations before the first draw */
#define INT_B_RPM_CAP  0x5a        /* leg_flags_c90 high word (rev cap for the attract demo) */
#define INT_B_RPM_ADD  0x0001      /* leg_flags_c90 low word (throttle step) */
/* The attract demo's input is a CONSTANT throttle — this is what the ORIGINAL does, not a stand-in for a
 * (non-existent) recorded ghost. The intermission runs with game_over_flag != 0 (main:314 / init_playfield
 * :3946 bracket it, and init_leg preserves the flag — its clear starts at 0x18c42, game_over_flag is at
 * 0x18c34, below the range), and game_update forces the player input to 1 in that state (`if
 * (game_over_flag != 0) uVar11 = 1`). op_start_demo_leg now RAISES the demo player's game_over (above), so
 * rm_player_update reproduces that forcing itself (`if (p->game_over) in = RM_IN_ACCEL`, src/player.c) AND
 * the sound triggers + score suppression fire faithfully — the demo is silent and does not tally. We still
 * pass this constant to game_update_step below; with game_over set §2 zeroes the raw input and §6 forces
 * accel anyway, so it is belt-and-suspenders that documents "the demo drives on the throttle". */
#define ATTRACT_DEMO_INPUT RM_IN_ACCEL

/* The attract phase timing (FlowTuning). GAME_FLOW_FAST shrinks it so a whole cycle fits a bounded
 * headless trace (the real phases are thousands of frames); normal builds use the real attract timing.
 * The fast Phase-A seeds break the scroll in ~2 frames (timer inside the gate, scroll/dwell at the edge). */
#ifdef GAME_FLOW_FAST
#define FLOW_PHASE_C_FRAMES 6      /* debug: a handful of demo frames instead of INT_C_FRAMES (0x96) */
#define FLOW_IDLE_INIT      8      /* debug: short leg-select idle so the attract path is reachable */
#define FLOW_FLASH_FRAMES   4      /* debug: a short get-ready flash so a headless trace stays snappy */
#define FLOW_HOLD_FRAMES    4      /* debug: a short name-entry terminal hold so a headless trace stays snappy */
static const FlowTuning flow_tuning = {
    .prologue_scroll = 1, .prologue_frame = 0, .prologue_timer = INT_SCROLL_GATE + 2,
    .phase_c_frames = FLOW_PHASE_C_FRAMES, .idle_init = FLOW_IDLE_INIT, .flash_frames = FLOW_FLASH_FRAMES,
    .hold_frames = FLOW_HOLD_FRAMES,
};
#else
static const FlowTuning flow_tuning = RM_FLOW_TUNING_DEFAULT;
#endif

#ifdef GAME_FLOW_AUTO
static int auto_cycle_done;         /* set by Phase D's RESTART; the attract input aborts after it */
#endif

/* ---- FlowOps: the 68000 implementation of each platform effect the driver orders, over the Shell. ---- */
static uint16_t op_poll_input(void *ctx)     { return ((Shell *)ctx)->input_source(); }
/* Q edge OR a shell quit already latched (op_reload_assets sets s->quit on a failed reload) — so a flow
 * checking this unwinds on either, letting a catastrophic reload bail like the boot path. */
static int      op_quit_requested(void *ctx) { return quit_requested() || ((Shell *)ctx)->quit; }
static int      op_fkey_leg(void *ctx)       { return ((Shell *)ctx)->fkey_source(); }

static void op_draw_fade(void *ctx, int16_t scroll) {
    Shell *s = ctx; rm_fade_step(back_buffer(s), s->int_assets, scroll);
}
static void op_draw_intermission(void *ctx, int16_t scroll) {
    Shell *s = ctx; rm_draw_intermission(back_buffer(s), s->int_assets, scroll);
}
static void op_draw_results(void *ctx, uint16_t leg) {
    Shell *s = ctx; rm_draw_leg_results(back_buffer(s), s->res_assets, leg);
}
static void op_draw_results_screen(void *ctx, uint16_t mode, uint16_t pos, uint16_t leg) {
    Shell *s = ctx; rm_draw_results_screen(back_buffer(s), s->res_screen_assets, mode, pos, leg);
}
static void op_draw_panel5(void *ctx) {
    Shell *s = ctx; rm_draw_panel5(back_buffer(s), s->res_assets);
}

static int read_fkey(void);   /* the leg-select F-key reader (defined below), reused by op_reload_confirm */

/* The F10 reload-menu panels (ip_menu's draw_panel3 / draw_panel2), overlaid on the leg-select screen. */
static void op_draw_panel3(void *ctx) { Shell *s = ctx; rm_draw_panel3(back_buffer(s), s->res_assets); }
static void op_draw_panel2(void *ctx) { Shell *s = ctx; rm_draw_panel2(back_buffer(s), s->res_assets); }

/* F6 preview busy-wait (ip_menu @0x2bc4/0x2bd8): wait for F6 released then any fresh key (the shared body),
 * then drain the resume key so it does not leak into the nav. The flow delegates this so a scripted host
 * test never blocks (the op is a recorded no-op there). */
static void op_preview_wait(void *ctx) {
    (void)ctx;
    wait_key_release_then_fresh(SCAN_F6);
    drain_key_hits();                             /* drain the resume key so it doesn't leak into the nav */
}

/* Drain stale latches but PRESERVE the keys the confirm loop reads (RETURN + the leg-select F-key range),
 * so a RETURN or F-key typed AHEAD during the prompt draw still lands — the fast F10+RETURN chord the
 * original's Crawcin honors — while stale junk that would spuriously decline is still cleared. */
static void drain_confirm_stale(void) {
    for (int i = 0; i < SCANCODE_COUNT; i++) {
        int keep = i == SCAN_RETURN || (i >= SCAN_F1 && i < SCAN_F1 + IP_LEG_COUNT)   /* F1..F5 */
                   || i == SCAN_F6 || i == SCAN_F10;
        if (!keep) key_hit[i] = 0;
    }
}

/* F10 reload confirm (ip_menu @0x2b48 Crawcin, blocking): block until RETURN (confirm), an F-key (re-tested
 * by the caller), or any other key (declines -> RM_FKEY_NONE). The leading drain clears stale latches but
 * KEEPS a RETURN/F-key already typed ahead, so the F10+RETURN chord isn't lost to it. Vblank-paced. */
static int op_reload_confirm(void *ctx) {
    (void)ctx;
    drain_confirm_stale();
    for (;;) {
        if (take_key_hit(SCAN_RETURN)) return RM_FKEY_RETURN;
        int fk = read_fkey();                     /* F1..F5 / F6 / F10 as a code, else RM_FKEY_NONE */
        if (fk != RM_FKEY_NONE) return fk;
        if (any_key_hit()) { drain_key_hits(); return RM_FKEY_NONE; }   /* some other key -> declines */
        Vsync();
    }
}

/* F10 reload (ip_menu @0x2b64): re-read + unpack GRAPHICS.GRA (load_graphics), re-seed the hi-score table
 * from its baked default (fixture_highscore == the remaster's init_scoretable output), and rebuild the
 * current leg's dashboard (init_leg_dash). The original's xbios_setscreen is subsumed by the shell's own
 * double-buffer flip (it renders into the back buffer), so there is no separate screen re-establish — a
 * documented deviation. Shell-only debug path; not under `make test`. */
static void op_reload_assets(void *ctx) {
    Shell *s = ctx;
    if (!load_graphics(s->arena)) {   /* load_graphics @0x2b64 */
        /* A truncated read has already clobbered the live graphics arena; load_graphics can't tell a
         * missing file from a short one, so bail uniformly — rendering on a half-loaded arena is worse
         * than exiting. quit_requested honours s->quit, so the flow unwinds to main's restore + exit. */
        s->quit = 1;
        return;
    }
    seed_highscore_table();           /* init_scoretable: reseed the hi-score table from its baked default */
    rm_init_leg_dash(s->ctx);         /* init_leg_dash: rebuild the dashboard */
}
static void op_set_palette(void *ctx, int which) {
    uint32_t off = which == RM_FLOW_PAL_INT_A      ? OBJ_LOW_PAL_INT_A
                 : which == RM_FLOW_PAL_LEG_SELECT ? OBJ_LOW_PAL_LEG_SELECT
                 : OBJ_LOW_PAL_RESULTS;             /* RM_FLOW_PAL_RESULTS: the race-end / name-entry screen */
    set_palette(ctx, off);
}

/* One name-entry colour-3 flash frame (highscore.c g_hiscore_name_entry: read A_name_anim_tbl[(anim_
 * counter & 0xe)] into palette register 3 and load it). Off-image (Setcolor + the SHARED anim_counter
 * bump, exactly like op_flash_frame) — the driver owns the per-frame COUNT, this owns the seam. */
#define NAME_FLASH_MASK 0xe        /* (anim_counter & this) is the word byte-offset into name_anim_tbl */
#define NAME_FLASH_REG  3          /* the palette register the name-entry screen flashes */
static void op_name_flash(void *ctx) {
    Shell *s = ctx;
    uint16_t counter = (uint16_t)(s->pfx->anim_counter + 1);
    s->pfx->anim_counter = counter;
    Setcolor(NAME_FLASH_REG, (short)be16(s->low + OBJ_LOW_NAME_ANIM_TBL + (counter & NAME_FLASH_MASK)));
}
static void op_show(void *ctx) { show_surface(ctx); }

/* One name-entry terminal HOLD frame (highscore.c g_hiscore_name_entry @0x259c: one of the 121 Vsyncs
 * that hold the finished table before returning). A plain vblank wait — no draw, no flip (the held
 * table already sits on the front buffer) — so it never touches the framebuffer; the driver owns the
 * 121-frame COUNT (t->hold_frames). */
static void op_hold_frame(void *ctx) { (void)ctx; Vsync(); }

/* The name-entry / game-over terminal "wait for the jingle to end". Spins one Vsync per poll while the
 * tune plays (rm_sound_music_on: the VBL pump advances the stream each Vsync until its end command clears
 * mzflag), so the spin actually terminates. The two call sites differ in whether a fresh input skips it:
 *   - name-entry (highscore.c @0x25bc): SKIPPABLE. Each spin re-reads FRESH input (read_input — the same
 *     joystick-priority path the race loop uses; the original polls read_joystick + `input_state & 0x8f`),
 *     so any joystick move / key press breaks out. NOT the old any_key_hit() scan of stale key_hit latches,
 *     which the race left set and which a joystick could never satisfy.
 *   - game-over (highscore.c @0x2406 g_wait_music_off): NOT skippable — a bare do{}while(mzflag), the
 *     original never lets you cut the game-over jingle short. `skippable` carries that distinction from the
 *     two flow.c call sites.
 * Both paths then drain the key latches (@0x25de, the Crawio drain) so a skip key doesn't leak into the
 * leg select that follows. */
static void op_wait_music_off(void *ctx, bool skippable) {
    Shell *s = ctx;
    while (rm_sound_music_on(s->ctx->snd)) {
        if (skippable && (read_input() & RM_IN_ACTIVE_MASK)) break;   /* fresh input skips (name-entry only) */
        Vsync();
    }
    drain_key_hits();   /* @0x25de: the Crawio key-drain, so a skip key doesn't leak into the leg select */
}

static void op_rebuild_dash(void *ctx, uint16_t leg) {
    Shell *s = ctx; s->ctx->leg = leg; rm_init_leg_dash(s->ctx);
    dash_pristine_dirty = 1;              /* the dashboard graphic was rebuilt -> re-prebuild */
}

/* Draw leg `leg`'s place-name labels onto the dashboard graphic in the arena (+ the folded marker
 * probe), so the race / demo / get-ready dashboard shows them (recreate g_draw_leg_labels). The
 * dashboard graphic must already be built for `leg` (op_rebuild_dash) — this overlays the labels. */
static void op_draw_leg_labels(void *ctx, uint16_t leg) {
    Shell *s = ctx; s->ctx->leg = leg; rm_draw_leg_labels(s->ctx);
    dash_pristine_dirty = 1;              /* labels + the folded marker probe changed the art */
}

/* One leg-start "get ready" flash frame (ip_start_leg @0x2c96): animate six leg_start_palette entries
 * from the obj-low flash tables and load them, pacing two Vsyncs. Off-image (palette + vblank only), so
 * it never touches the framebuffer — the driver owns the 121-frame COUNT (a wrong length diverges the
 * driver test); this owns the per-frame palette animation the byte-compare cannot see. */
#define IP_FLASH_MASK_A   0x0c        /* (anim_counter & this) >> 1 -> flash_tbl_a word index */
#define IP_FLASH_MASK_BC  0x1c        /* ...tbl_b / tbl_c */
#define IP_FLASH_MASK_D   0x06        /* ...tbl_d long index (raw, not halved) */
#define IP_PAL_OFF_A      0x1c        /* leg_start_pal byte offsets the flash writes */
#define IP_PAL_OFF_B0     0x08
#define IP_PAL_OFF_B1     0x1e
#define IP_PAL_OFF_C      0x0c
#define IP_PAL_OFF_D0     0x12
#define IP_PAL_OFF_D1     0x16
#define LEG_START_PAL_BYTES 0x20      /* 16 ST palette words the flash animates + Setpalette loads */
static void op_flash_frame(void *ctx) {
    Shell *s = ctx;
    /* Read + increment the SHARED anim_counter (GobjPrefixState, bumped +2/frame by the race's object
     * animation), +1 per flash frame, exactly as ip_start_leg does (intermission.c:406 reads/writes
     * A_anim_counter). The flash runs during the leg select, BEFORE start_leg re-zeroes the prefix, so
     * the counter still holds the preceding race/demo's value — the get-ready flash carries the
     * animation history like the arcade, rather than always restarting from 0. Off-image seam. */
    uint16_t counter = (uint16_t)(s->pfx->anim_counter + 1);
    s->pfx->anim_counter = counter;
    uint16_t ia  = (uint16_t)((counter & IP_FLASH_MASK_A) >> 1);
    uint16_t ibc = (uint16_t)((counter & IP_FLASH_MASK_BC) >> 1);
    uint16_t id  = (uint16_t)(counter & IP_FLASH_MASK_D);
    uint8_t *pal = s->leg_start_pal;
    wr16(pal + IP_PAL_OFF_A,  be16(s->low + OBJ_LOW_LEG_FLASH_A + ia));
    wr16(pal + IP_PAL_OFF_B0, be16(s->low + OBJ_LOW_LEG_FLASH_B + ibc));
    wr16(pal + IP_PAL_OFF_B1, be16(s->low + OBJ_LOW_LEG_FLASH_B + ibc));
    wr16(pal + IP_PAL_OFF_C,  be16(s->low + OBJ_LOW_LEG_FLASH_C + ibc));
    wr32(pal + IP_PAL_OFF_D0, be32(s->low + OBJ_LOW_LEG_FLASH_D + id));
    wr32(pal + IP_PAL_OFF_D1, be32(s->low + OBJ_LOW_LEG_FLASH_D + 4 + id));
    Setpalette(pal);
    Vsync(); Vsync();
}

/* Phase B (0x27fe tail): (re)init the picked demo leg, rebuild its dashboard, override the engine
 * limits, settle it with a burst of game-updates (no draw), then paint the first two frames. start_leg
 * reseeds every owner struct via init_leg (+ the dash marker + the demo/race palette); rm_init_leg_dash
 * then rebuilds the DASHBOARD GRAPHIC for the newly-picked leg (a previous phase left another leg's). The
 * 0x5a0001 leg_flags override sets the demo's engine limits (the leg_flags_sel / dsp_toggle attract-feel
 * tweaks the original also does are off-image). */
static void op_start_demo_leg(void *ctx, uint16_t leg) {
    Shell *s = ctx;
    start_leg(s, leg);
    /* Run the demo leg with game_over SET, exactly as the original brackets the intermission with
     * game_over_flag != 0 (main @0x10100:314). This is what makes the attract demo SILENT: every sound
     * trigger bails on game_over and §1's engine-sound goes to EGOFF (no EG, no idle Dosound, no INITFX on
     * a demo crash — see rm_sound_engine_update / the trigger leaves). It also forces the demo's input to a
     * constant throttle via the already-modeled §6 path (`if (p->game_over) in = RM_IN_ACCEL`, player.c),
     * and suppresses the demo's own scoring (rm_score_add early-returns on game_over). Both mirrors of the
     * single game_over flag (the physics' p->game_over and the event ctx's game_over) are raised. */
    s->player->game_over = 1;
    s->ctx->game_over = 1;
    op_rebuild_dash(ctx, leg);   /* bind_leg already set ctx->leg; rebuild the picked leg's dashboard */
    /* Labels MUST draw AFTER the rebuild: rm_init_leg_dash rebuilds the dashboard GRAPHIC from scratch,
     * wiping anything overlaid on it, so labels drawn first would be erased. Same order as the fire-start
     * get-ready (flow_start_leg: rebuild_dash then draw_leg_labels) and intermission.c:268-271. */
    op_draw_leg_labels(ctx, leg); /* Phase B (intermission.c:268-271): the demo dashboard shows the labels */
    s->player->rpm_cap = INT_B_RPM_CAP;
    s->player->rpm_add = INT_B_RPM_ADD;
    for (int i = 0; i < INT_B_WARMUP; i++) game_update_step(s, ATTRACT_DEMO_INPUT);   /* settle, no draw */
    render_and_show(s);
    render_and_show(s);
}

/* Phase C (0x285e body): one demo frame — game-update through the event engine, then full render + flip. */
static void op_run_demo_frame(void *ctx) {
    Shell *s = ctx;
    game_update_step(s, ATTRACT_DEMO_INPUT);
    render_and_show(s);
}

/* Phase-transition trace hook: log it (GAME_FLOW_TRACE) and, under GAME_FLOW_AUTO, arm the attract abort
 * once a full cycle has traced its RESTART (so the next cycle's Phase A sees a fresh key and aborts). */
static void op_event(void *ctx, uint16_t tag, uint16_t leg, uint16_t aux) {
    (void)ctx;
    flow_event(tag, leg, aux);
#ifdef GAME_FLOW_AUTO
    if (tag == RM_FLOW_EVT_INT_PHASED_RESTART) auto_cycle_done = 1;
#endif
    (void)tag; (void)leg; (void)aux;   /* used above only under GAME_FLOW_TRACE / _AUTO */
}

static const FlowOps flow_ops = {
    .poll_input = op_poll_input, .quit_requested = op_quit_requested, .fkey_leg = op_fkey_leg,
    .draw_fade = op_draw_fade, .draw_intermission = op_draw_intermission, .draw_results = op_draw_results,
    .draw_results_screen = op_draw_results_screen,
    .draw_panel5 = op_draw_panel5, .set_palette = op_set_palette, .show = op_show,
    .rebuild_dash = op_rebuild_dash, .draw_leg_labels = op_draw_leg_labels,
    .start_demo_leg = op_start_demo_leg, .run_demo_frame = op_run_demo_frame,
    .flash_frame = op_flash_frame, .name_flash = op_name_flash, .hold_frame = op_hold_frame,
    .wait_music_off = op_wait_music_off,
    .draw_panel3 = op_draw_panel3, .draw_panel2 = op_draw_panel2, .preview_wait = op_preview_wait,
    .reload_confirm = op_reload_confirm, .reload_assets = op_reload_assets,
    .event = op_event,
};

/* Interactive leg-select input sources. read_fkey returns 0..4 for an F1..F5 tap (a direct leg pick,
 * as the original's function-key menu), or -1 for none; no_fkey is the headless placeholder. Each is
 * used by exactly one build config (interactive vs GAME_FLOW_AUTO), so both are marked maybe-unused. */
__attribute__((unused)) static int read_fkey(void) {
    for (int i = 0; i < IP_LEG_COUNT; i++) if (take_key_hit(SCAN_F1 + i)) return i;   /* F1..F5 -> 0..4 */
    if (take_key_hit(SCAN_F6)) return RM_FKEY_F6;      /* results-screen preview */
    if (take_key_hit(SCAN_F10)) return RM_FKEY_F10;    /* graphics / score-table reload */
    return RM_FKEY_NONE;
}
__attribute__((unused)) static int no_fkey(void) { return RM_FKEY_NONE; }

/* ---- headless flow scripting (GAME_FLOW_AUTO): drive the whole shell without a keyboard so a trace
 * run proves the loop closes. Booting into the leg select (the shipping order), the script fires the
 * select to start leg GAME_LEG_INDEX; the leg idles to its shortened time-out (GAME_TIME_LEFT), which
 * runs highscore + one attract cycle; then the leg select re-enters and fires again — proving the whole
 * loop (SELECT -> LEG -> LEG_END -> HISCORE -> INTERMISSION A->B->C->D -> SELECT) closed. ---- */
#ifdef GAME_FLOW_AUTO
static int auto_select_frame;          /* reset at each leg-select entry so the fire is a fresh 0->1 edge */
static int auto_intermission_done;     /* set after the first attract cycle returns; ends the trace run */
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
#ifdef GAME_STE
    /* STE build (PERF30 C4): the masked object blits run on the hardware blitter, which a plain ST lacks.
     * Bail with a clean message rather than bus-erroring on the first 0xFFFF8Axx poke. */
    if (!blitter_available()) {
        Cconws("BUGGYBOY STE build: this needs an STE (or later) with a blitter. Press a key.\r\n");
        Cconin();
        return;
    }
#ifdef GAME_STE_SELFTEST
    /* Slice-1 driver proof: reproduce rm_blit_objshift2 with the blitter and dump the XOR diff
     * (all-zero == byte-exact) to SCREEN.BIN for run_ste_selftest.py. No game boot needed. */
    {
        long mismatch;
        const uint8_t *diff = blitter_selftest(&mismatch);
        dump_frame((Framebuffer *)diff);
        return;
    }
#endif
#ifdef GAME_STE_SWEEP
    /* Slice-2 recipe proof: sweep rm_blit_objshift2_blitter vs the CPU engine over the objshift2 case
     * space, dump the per-case mismatch grid to SCREEN.BIN for run_ste_sweep.py. No game boot needed. */
    {
        long mismatch;
        const uint8_t *grid = blitter_sweep(&mismatch);
        dump_frame((Framebuffer *)grid);
        return;
    }
#endif
#endif
    RmArena arena;
    if (!load_assets(&arena)) return;

    /* Seed the two persistent RAM regions from their baked defaults (the score record + hi-score table
     * live here; the flow mutates them). */
    for (unsigned i = 0; i < sizeof fixture_hud_text; i++) hud_text_ram[i] = fixture_hud_text[i];
    seed_highscore_table();
    for (unsigned i = 0; i < sizeof fixture_score_line; i++) score_line_ram[i] = fixture_score_line[i];
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
        .dash_pristine = dash_pristine,   /* prebuilt per leg; see dash_pristine_dirty */
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

    /* Zero-initialised (unlike the other per-race owner structs, which start_leg zeroes before use):
     * the get-ready flash reads pfx.anim_counter during the FIRST leg select, before any start_leg, so
     * it must start at 0 to match the original's zero-at-boot A_anim_counter (see op_flash_frame). */
    GobjPrefixState pfx = {0};
    const GobjPrefixAssets pfx_assets = {
        .anim_word_tbl = low + OBJ_LOW_ANIM_WORD_TBL,
        .anim_coloridx_tbl = low + OBJ_LOW_ANIM_COLORIDX, .color_pairs = low + OBJ_LOW_COLOR_PAIRS,
        /* marker_recs IS the dispatcher's flag grid, at the original's decay base (see ring_st_block);
         * anim_color aliases the HUD's fuel mask. Both are aliases the original gets for free. */
        .marker_recs = ring_st_block, .anim_color = fuel_mask_ram,
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
    /* The in-race sound driver: the physics / event / flow triggers evolve its state (slice 2), and the
     * VBL pump + real Dosound seam above (slice 3) make it audible. It starts PARKED with no tune; a
     * trigger sets it RUNNING and the 50 Hz VBL (vbl_sound) writes rm_refresh's YM2149 stream to the chip.
     * install_sound(&snd) below points the pump at it and splices the VBL queue. The rm_inittune /
     * rm_stop_music / rm_turnoff mutations the triggers run at frame level are bracketed against the pump
     * by RM_SOUND_LOCK/UNLOCK (see the VBL-reentrancy write-up in the sound-pump section above). */
    SoundDriver snd;
    rm_sound_reset(&snd.state);
    snd.vbl_enable = RM_VBL_PARKED;
    snd.cur_tune_id = 0;

    RmEventCtx ctx = {
        .player = &player, .gobj = &pfx, .ring = &ring, .pose = &pose, .road_src = &src,
        .ctrl = ctrl, .scanline = scanline, .ev = &ev, .hud_text = hud_text_ram,
        .gfx = arena.gfx, .assets = &event_assets, .leg = GAME_LEG_INDEX, .game_over = 0,
        .snd = &snd,
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
        .panel5_str = low + OBJ_LOW_PANEL5_STR,
        .panel3_str = low + OBJ_LOW_PANEL3_STR, .panel2_str = low + OBJ_LOW_PANEL2_STR,
    };
    /* The race-end / name-entry results screen (slice F). Const program data + buf_c dashboard; the
     * mutable game-state windows point at the RAM the flow reads (the hi-score table, the HUD text, the
     * score-line region). The palettes are cursors AT their leg-0 byte, indexed [i - pos]. */
    const RmResultsScreenAssets res_screen_assets = {
        .color_pairs = fixture_color_pairs, .font = fixture_font,
        .num_sprites = arena.gfx + ARENA_NUM_SPRITES_OFF, .num_glyph_tbl = fixture_num_glyph_tbl,
        .gfx = arena.gfx, .title = low + OBJ_LOW_RS_TITLE,
        .palette_a = low + OBJ_LOW_RS_PAL_A, .palette_b = low + OBJ_LOW_RS_PAL_B,
        .mode_str = low + OBJ_LOW_RS_MODE_STR, .buf_a = buf_a_ram, .highscore = highscore_ram,
        .hud_text = hud_text_ram, .score_line = score_line_ram,
    };
    /* The leg-start flash's mutable palette, seeded from the baked leg_start_palette (obj-low blob); the
     * flash animates six of its entries per frame (op_flash_frame). Off-image (palette only). */
    uint8_t leg_start_pal_ram[LEG_START_PAL_BYTES];
    memcpy(leg_start_pal_ram, low + OBJ_LOW_LEG_START_PAL, sizeof leg_start_pal_ram);
    /* The in-race palette start_leg / mode 4 stage into (seeded from fixture_palette per leg start). */
    uint8_t race_pal_ram[RM_RACE_PAL_BYTES];

    Shell shell = {
        .arena = &arena, .player = &player, .course = &course, .pose = &pose, .scroll = &scroll,
        .ring = &ring, .ev = &ev, .pfx = &pfx, .sprite = &sprite, .ground = &ground_mut,
        .objlist = &objlist, .object = &object, .hud = &hud, .road = &road,
        .obj_shade = &obj_shade, .screen_offset = &screen_offset,
        .src = &src, .hud_assets = &hud_assets, .pfx_assets = &pfx_assets, .ground_assets = &ground_assets,
        .sprite_assets = &sprite_assets, .player_assets = &player_assets, .init_assets = &init_assets,
        .low = low, .event_assets = &event_assets, .ctx = &ctx, .stream = arena.tables, .leg = GAME_LEG_INDEX,
        .race_input_prev = 0, .flow = &flow,
        .int_assets = &int_assets, .res_assets = &res_assets, .res_screen_assets = &res_screen_assets,
        .leg_start_pal = leg_start_pal_ram, .race_pal = race_pal_ram,
        .input_source = read_input, .fkey_source = read_fkey,   /* repointed per flow call below */
    };
    Shell *s = &shell;

    /* Save the desktop's palette + video base so they can be restored on exit. The race palette is set
     * by start_leg (the single place every race entry funnels through — see fix note there). */
    uint16_t tos_palette[16];
    for (int reg = 0; reg < 16; reg++) tos_palette[reg] = (uint16_t)Setcolor((short)reg, -1);
    long tos_screen = Physbase();        /* the desktop base, captured before any flip to our buffers */
    /* Clear both screen buffers once, so "buffers start blank" holds before the first draw (draw_frame
     * never clears). The pool is BSS and already zero at GEMDOS load, so this is belt-and-braces. */
    memset(screen_buf(0)->px, 0, SCREEN_BYTES);
    memset(screen_buf(1)->px, 0, SCREEN_BYTES);

    /* Install the 50 Hz VBL sound pump (and clear the TOS key-click) before the game runs. It starts
     * silent — snd is PARKED — so it is harmless for the golden / autodrive fast-path frame below; a
     * trigger sets it RUNNING and from then on the VBL writes rm_refresh's stream to the YM2149. */
    install_sound(&snd);

    long old_kbd_vector;
#ifdef BOOT_FAST_LEG
    /* BOOT fast path — GOLDEN harness / autodrive builds ONLY (see BOOT_FAST_LEG above). Skip the leg
     * select and start leg BOOT_FAST_LEG directly, drawing (and, for the golden harness, dumping) its
     * first painted frame BEFORE any physics — byte-identical to recreate's pipeline (build/golden.bin).
     * The SHIPPING build compiles the #else branch: it has no fast path and boots into the leg select. */
    start_leg(s, BOOT_FAST_LEG);
    flow.leg_index = BOOT_FAST_LEG;
    flow.leg_select = BOOT_FAST_LEG;
    draw_frame(s, screen_buf(s->shown));
    Setscreen(-1L, (long)screen_buf(s->shown)->px, -1);
    Vsync();
#ifdef GOLDEN_BOOT_LEG
    dump_frame(screen_buf(s->shown));    /* the golden frame-0 dump (before the keyboard is taken) */
#endif
    old_kbd_vector = kbd_install();
    flow_event(RM_FLOW_EVT_LEG_START, BOOT_FAST_LEG, 0);
    int booted = 1;
#else
    /* SHIPPING boot: straight into the leg select (init_playfield), exactly as the original game boots
     * (decomp.c main @0x10100). The loop top runs rm_flow_leg_select; fire starts the chosen leg. */
    old_kbd_vector = kbd_install();
    int booted = 0;
#endif
    for (; !s->quit; booted = 0) {
        if (!booted) {
            /* Not the boot pass: run the leg select (init_playfield) to pick the next leg, then start
             * it (init_leg + the race palette, both inside start_leg). This is main's loop top. */
#ifdef GAME_FLOW_AUTO
            auto_select_frame = 0;   /* fresh 0->1 fire edge for this leg-select entry */
            s->input_source = auto_select_input; s->fkey_source = no_fkey;
#else
            s->input_source = read_input; s->fkey_source = read_fkey;
#endif
            if (rm_flow_leg_select(&flow, &flow_ops, s, &flow_tuning, &snd) == RM_FLOW_QUIT) {
                s->quit = 1;                            /* Q from the leg select -> restore + exit */
                break;
            }
            start_leg(s, flow.leg_index);
            flow_event(RM_FLOW_EVT_LEG_START, flow.leg_index, 1);
            render_and_show(s);                         /* race-start frame (start_leg set the palette) */
            race_start_countdown(s);                    /* the "3-2-1-GO" beeps (main @0x10226) */
        }

        /* ---- the race loop ---- */
        int ended = 0;
        /* Discard any ESC latched during the leg select. The original's menu consumes and ignores ESC
         * each frame (ip_menu's Crawio), so a menu ESC must not carry into the race and abort it on frame
         * 0. A firmly HELD ESC can still re-latch via IKBD auto-repeat before the first poll and abort
         * immediately — the original's Crawio reads that repeat char identically, so behaviour matches.
         * (Q is already consumed each menu frame by quit_requested, so it needs no such clear.) */
        take_key_hit(SCAN_ESC);
#if defined(GAME_FLOW_AUTO) && !defined(GAME_AUTODRIVE)
        /* The trace has already captured a full round trip (a leg, its time-out, the attract cycle) and
         * has now re-entered the leg select and started a leg again — the loop is closed. End the run
         * here rather than idling a second leg to its time-out. */
        if (auto_intermission_done) s->quit = 1;
#endif
        for (int frame = 0; !s->quit && !ended; frame++) {
            (void)frame;   /* only read by the debug trace / autodrive frame budget below */

            uint16_t input;
#ifdef GAME_AUTODRIVE
            input = autodrive_input(frame);
#else
            input = read_input();
#endif
            ended = game_update_step(s, input);

#ifdef GAME_TRACE
            trace_frame(frame, &player, &ev, &course);
#endif
            render_and_show(s);
            /* End-of-frame console poll, in the original's order (after the flip — main @0x10100:286..296):
             * ESC aborts the race into the leg-end path (update_highscore + intermission), like a natural
             * leg end but with no bonus tally — it does NOT quit; G toggles the dashboard-variant display
             * (dsp_toggle); Q quits (the one documented deviation). */
            if (take_key_hit(SCAN_ESC)) ended = 1;
            if (take_key_hit(SCAN_G)) s->hud->dsp_toggle = !s->hud->dsp_toggle;
            if (take_key_hit(SCAN_HELP)) pause_race(s);   /* Help = pause: silence + freeze until any key (main @0x10100:293) */
            s->quit |= quit_requested();                  /* OR: pause_race may already have latched a Q-to-resume quit */
#ifdef GAME_AUTODRIVE
            /* Headless frame budget: stop at the trace length (or the autodrive length when not tracing)
             * even if the leg has not ended. The dump itself happens on loop exit (below), so it fires on
             * a leg end too — a shortened-clock idle trace ends well before the budget. */
#ifdef GAME_TRACE
            if (frame + 1 >= GAME_TRACE) s->quit = 1;
#else
            if (frame + 1 >= GAME_AUTODRIVE) s->quit = 1;
#endif
#endif
        }
#if defined(GAME_AUTODRIVE) && !defined(GAME_FLOW_AUTO)
        /* Headless autodrive dumps on race-loop EXIT — whichever came first, the leg end (abort_flag < 0)
         * or the frame budget — then quits instead of entering the between-legs flow, which would poll a
         * dead keyboard under headless Hatari and hang (so an idle leg-end trace never reached the dump). */
#if defined(GAME_CADENCE_TRACE)
        cadence_dump();
#elif defined(GAME_TRACE)
        trace_dump();
#else
        dump_frame(screen_buf(s->shown));
#endif
        s->quit = 1;
#endif
        if (s->quit) break;

        /* ---- the leg ended (abort_flag < 0): update_highscore -> game_over++ -> intermission ->
         * game_over = 0, then the loop top runs the leg select again. This is main @0x10100:286-317. The
         * game-over enter/exit bracket around the intermission is rm_flow_game_over (flow.c). ---- */
        flow_event(RM_FLOW_EVT_LEG_END, s->leg, (uint16_t)ev.abort_flag);
        flow.leg_index = s->leg;
        rm_update_highscore(&flow, highscore_ram, hud_text_ram + RM_HUD_SCORE_BCD_OFF, &snd);
        flow_event(RM_FLOW_EVT_HISCORE, flow.leg_index, flow.hiscore_pos);
#ifdef GAME_FLOW_AUTO
        s->input_source = auto_intermission_input;
#else
        s->input_source = read_input;
#endif
        /* The interactive high-score tail (rm_flow_score_tail): a score that MADE the table
         * (results_mode == 0) runs the initials screen; one that MISSED (== 2) runs the short game-over
         * screen. Both consume the input source set above and return control here, then the intermission
         * runs. The dispatch lives in the flow (not this shell) so `make test` pins the branch. Sound is
         * fully wired and audible: the name-entry / game-over jingles + the terminal TURNOFF drive `snd`,
         * the VBL pump plays them (op_wait_music_off spins on the real rm_sound_music_on), and the terminal
         * jingle wait is skippable on the name-entry path only. */
        rm_flow_score_tail(&flow, &flow_ops, s, &flow_tuning, highscore_ram, score_line_ram, &snd);
        if (rm_flow_game_over(&flow, &flow_ops, s, &flow_tuning) == RM_FLOW_QUIT) s->quit = 1;
#ifdef GAME_FLOW_AUTO
        auto_intermission_done = 1;   /* the attract cycle returned; the next leg-select+start ends the trace */
#endif
    }

    uninstall_sound();   /* detach the VBL pump before Pterm, so TOS never calls it in the freed TPA */
    kbd_remove(old_kbd_vector);
    Setscreen(-1L, tos_screen, -1);
    Setpalette(tos_palette);
    Vsync();
#ifdef GAME_FLOW_TRACE
    flow_trace_dump();
#endif
}
