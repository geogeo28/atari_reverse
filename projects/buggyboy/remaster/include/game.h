/* game.h — native BuggyBoy state, freed from recreate's flat image + Ghidra-offset model.
 *
 * This grows one struct at a time as each subsystem is ported (Phase A: the render inputs first;
 * Phase B: the full gameplay state). The rule is idiomatic C: named fields, native types, no
 * `image + offset` arithmetic. The test-only adapter (test/adapter.*) maps recreate's flat image
 * onto these structs so a captured snapshot can drive the remaster renderer — see README.md.
 */
#ifndef RM_GAME_H
#define RM_GAME_H

#include <stdbool.h>
#include <stdint.h>

#include "screen.h"

/* Player buggy pose — what the object/car draw reads. Fields added as the draw path is ported. */
typedef struct {
    int16_t lean;        /* left/right body lean (A_lean_state) */
    int16_t pitch;       /* suspension pitch   (A_buggy_pitch) */
    int16_t skid;        /* skid displacement  (A_buggy_skid)  */
    int16_t crash_disp;  /* crash bounce        (A_crash_disp)  */
} Buggy;

/* Top-level game state. A deliberately thin placeholder for now: Phase A fills in the render
 * inputs (road geometry, object list, HUD values, buggy pose); Phase B adds the gameplay state. */
typedef struct {
    Buggy buggy;
    uint8_t leg;         /* current leg 0..4 */
} GameState;

/* ---- HUD (draw_hud, phases 4/5/6a ported so far) ---- *//* Dynamic per-frame HUD inputs (recreate's scalar globals, named). See src/hud.c. */
typedef struct {
    int16_t flag_seq_count;    /* matched-in-a-row flags -> one lit bar each (phase 4) */
    int16_t flag_seq_off;      /* colour-index cursor offset (phase 5) */
    int16_t dsp_color_scroll;  /* scrolling colour-index cursor offset (phase 5) */
    int16_t crash_lap;         /* remaining bonus units -> one fuel column each (phase 6a) */
    uint16_t speed;            /* speedometer value (phase 1 formats its low byte into the string) */
    uint16_t time_left;        /* bonus time remaining (phase 2 formats into the string) */
    bool game_over;            /* blank the timer to 0 when set (phase 2) */
    bool dsp_toggle;           /* suppress the dashboard-variant sprite when set (phase 3) */
    uint16_t dsp_variant_idx;  /* byte offset into the dashboard-variant record table (phase 3) */
    uint16_t gauge_blink;      /* small-gauge blink phase; bit1 of (blink-1) gates the draw (phase 6b) */
    bool gauge_blink_on;       /* enable the extra bar under the blinking small gauge (phase 6b) */
    bool crash_active;         /* crash/bonus-tally gate (phase 8) */
    int16_t crash_frame;       /* crash-effect frame counter; +1 drives the colour cycle (phase 8) */
    uint16_t crash_bars;       /* number of gauge bars to draw, 0-5 (phase 8) */
    int16_t hud_crash_timer;   /* crash-arm timer: phase 8 draws only once this is negative */
} HudState;

/* Static ST-format asset tables the HUD reads (constant data baked into STATIC.BIN, plus the
 * unpacked dashboard graphic in buf_c). The pointers reference raw big-endian bytes, read via st.h.
 * color_bar_cidx points at the cursor's zero offset; the phase-5 code indexes it with the signed
 * flag_seq_off + dsp_color_scroll deltas. dsp_table's src offsets are rebased into dsp_src. */
typedef struct {
    const uint8_t *color_pairs;     /* 16 colours x 8-byte (4-plane) solid fill */
    const uint8_t *color_bar_mask;  /* phase-5 per-row {mask,ink} word stream */
    const uint8_t *color_bar_cidx;  /* phase-5 per-column colour-index byte cursor (zero offset) */
    const uint8_t *fuel_mask;       /* phase-6a two mask longs blended into the gauge mid rows */
    const uint8_t *font;            /* phase-7 1bpp glyph table (glyph N at font + N*16) */
    const uint8_t *hud_text;        /* the HUD-text working region [0x18172,0x18258): gauge string,
                                     * crash num/bar strings, rollover records, score — phases share
                                     * it (they overlap in the original), so it's one mutable copy */
    const uint8_t *dashboard_src;   /* phase-7 dashboard graphic (buf_c region), masked-blit source */
    const uint8_t *dsp_table;       /* phase-3 records {src_off:long, dst_off:word, rows-1:word} */
    const uint8_t *dsp_src;         /* phase-3 sprite pixels (buf_c window; dsp_table src_off is relative) */
    const uint8_t *small_gauge_str; /* phase-6b blinking small-gauge label/bar string */
    const uint8_t *num_sprites;     /* phase-8 pre-rendered digit sprites (buf_c region) */
    const uint8_t *num_glyph_tbl;   /* phase-8 per-digit word offset into num_sprites */
    const uint8_t *crash_color_tbl; /* phase-8 per-frame colour index, indexed (frame & 7) */
    const uint8_t *score_delta_time;/* phase-8 6-byte add_score delta while draining time */
    const uint8_t *score_delta_roll;/* phase-8 6-byte add_score delta per bonus unit / rollover */
} HudAssets;

/* ---- render_road (the pseudo-3D road rasterizer @0x19144) ---- */

/* Per-frame inputs render_road consumes. In the full game these tables are rebuilt each frame by
 * build_road_geometry from the buggy pose + course curvature; Phase A feeds captured tables straight
 * through so the rasterizer is validated in isolation. All are ST-format byte buffers (see st.h):
 *   - width_tbl : per-scanline control long (flags in the high word, road half-width in the low);
 *                 the cursor resets to the base at each of the four band groups.
 *   - param     : one monotonic word stream read across every band (perspective offset, edge seed,
 *                 and per-row fill counts) — never reset.
 *   - edge_tbl  : per-scanline edge-run word table; the pointer already includes road_edge_sel.
 *   - tex       : the road texture (buf_b). src cursors and the per-row edge masks index this; it
 *                 points AT the buf_b origin, with padding below it for negative perspective seeds.
 *   - edge_const: three constant edge-texture strips (STATIC region) a few scanlines select. */
typedef struct {
    const uint8_t *width_tbl;
    const uint8_t *param;
    const uint8_t *edge_tbl;
    const uint8_t *tex;
    const uint8_t *edge_const;
} RoadInput;

void rm_render_road(const RoadInput *in, Framebuffer *fb);

/* ---- the course object/marker ring (the scrolling course window, produced by section 12) ----
 *
 * The course window the game scrolls toward you: RM_RING_ROWS distance bands, refilled at the far end
 * from the leg's packed course records (see rm_road_course_advance below). build_road_geometry reads
 * each band's marker word; draw_ground and the object-list dispatcher read the type-code slots (both
 * still through the flat image today — see PORTING.md). */
#define RM_RING_ROWS   14   /* distance bands: row 0 farthest (just refilled) .. row 13 nearest */
#define RM_RING_SLOTS  15   /* object/marker type-code slots per band */

/* Shoulder/edge flags. They are born in a band's marker word (below) and reach section 10 through the
 * control table, because build_road_geometry copies the marker word into each row's control long —
 * which is what makes the flags a per-band property of the course rather than a global. */
#define EDGE_OPEN    0x1000   /* the shoulder at this row can be driven onto */
#define EDGE_LEFT    0x2000
#define EDGE_RIGHT   0x4000

/* One distance band. `slot` holds the band's object type codes — a code sits in the LOW byte, which
 * is how the object-list dispatcher indexes its per-type records.
 *
 * `marker` is the band's CONTROL word, and the original's name for its column (road_width_src) is a
 * misnomer worth not inheriting: build_road_geometry copies it into the HIGH word of every control
 * long the band covers, and the high word is the flag half — render_road's blit-variant bits plus the
 * EDGE_* shoulder flags section 10 reads back. The road half-width is the control long's LOW word,
 * which integrate_perspective and spread_curvature produce; the marker never carries it. The column
 * is DYNAMIC course state, not a baked table — build_road_geometry reads it every frame. */
typedef struct {
    uint16_t slot[RM_RING_SLOTS];
    uint16_t marker;
} CourseRow;

typedef struct {
    CourseRow row[RM_RING_ROWS];
} CourseRing;

/* ---- build_road_geometry (the per-scanline table builder @0x11f4c) ---- */

/* Number of longs in the control table the builder produces (recreate's road_curve_tbl, 106 longs)
 * and the offset within it of render_road's width_tbl window (road_width_tbl overlaps road_curve_tbl
 * ten longs in). So a rendered frame is: rm_build_road_geometry -> ctrl, then rm_render_road with
 * `.width_tbl = ctrl + RM_CTRL_WIDTH_OFF`. */
#define RM_CTRL_LONGS       106
#define RM_CTRL_BYTES       (RM_CTRL_LONGS * 4)
#define RM_CTRL_WIDTH_OFF   0x28
#define RM_SCANLINE_BYTES   0x80        /* per-row cumulative-slope scratch (road_scanline_tbl) */

/* Dynamic road-geometry inputs the builder integrates each frame (recreate's scalar globals). curve
 * (steering) and the segment slopes drive the road's bend/tilt; view_flags selects the width bank.
 * The horizon the builder clamps is not an input — it lands inside the control table (see
 * geometry.c). seg_head/horizon_row/horizon_frac are written back by the builder. */
typedef struct {
    int16_t  curve;         /* road_curve — signed road curvature (the steering input) */
    uint16_t view_flags;    /* view/leg selector (0, 2, 4, 6) */
    int16_t  seg_data[13];  /* road_seg_data: [0] near slope + [1..12] segment slopes */
    int16_t  seg_head;      /* out: cached seg_data[0] */
    int16_t  horizon_row;   /* out: clamped horizon scanline */
    int16_t  horizon_frac;  /* out: horizon sub-row parity */
} RoadPose;

/* Const source tables the builder reads (baked once; STATIC region, ST big-endian bytes). The
 * per-band control words are deliberately NOT here: they are the ring's live marker column, passed
 * separately so they cannot be mistaken for a table it is safe to snapshot once (they were exactly
 * that until the ring was ported, which silently froze the road's flags after the first frame). */
typedef struct {
    const int8_t  *persp_seg;    /* per-segment run lengths (0x31 signed bytes) */
    const uint8_t *width_count;  /* per-row width run counts, 4 view banks of 16 bytes */
} RoadSource;

/* Rebuild `ctrl` (RM_CTRL_BYTES, ST bytes) — the control-long table render_road consumes — and the
 * `scanline` scratch (RM_SCANLINE_BYTES), from the pose, the const sources and the ring's per-band
 * road widths. Also writes the pose's seg_head / horizon_row / horizon_frac outputs. */
void rm_build_road_geometry(RoadPose *pose, const RoadSource *src, const CourseRing *ring,
                            uint8_t *ctrl, uint8_t *scanline);

/* ---- blit_road_scroll (the horizontal road fine-scroll @0x10326) ---- */

/* Per-frame scroll state. seg_head (a build_road_geometry output) times scroll_speed advances the
 * fine-scroll position each frame; hscroll_pos persists across frames (wrapped into [0, 0x280)).
 * hscroll_step2 is written back (the doubled step other subsystems read). */
typedef struct {
    int16_t  seg_head;      /* road_seg_head (build_road_geometry output) */
    int16_t  scroll_speed;  /* signed horizontal scroll speed */
    uint16_t hscroll_pos;   /* in/out: fine-scroll position, wrapped into [0, 0x280) */
    uint16_t hscroll_step2; /* out: seg_head * scroll_speed * 2 */
} ScrollState;

/* Optimized fine-scroll (the perf win over recreate's per-word variable rotate): instead of rotating
 * every plane-word every frame, precompute — once, when the playfield changes — RM_SCROLL_SHIFTS copies
 * of the playfield window, copy s being every plane-word fine-scrolled by s with its next-column word.
 * Then the per-frame blit is a plain column copy from copy[shift]. Copy 0 is the raw playfield (a
 * rotate by 0 is identity), which the edge seam reads for its masked wrap blend. */
#define RM_SCROLL_SHIFTS   16          /* fine-shift is hscroll_pos & 0xf */
#define RM_SCROLL_WINDOW   0x1a00      /* bytes of playfield the blit reads (>= its max offset) per copy */

/* Build the RM_SCROLL_SHIFTS pre-rotated copies from `playfield` into `shifted`
 * (RM_SCROLL_SHIFTS * RM_SCROLL_WINDOW bytes). Call when the playfield / screen_offset changes. */
void rm_scroll_prebuild(const uint8_t *playfield, uint8_t *shifted);

/* Fine-scroll the double-wide road playfield onto the screen's road band (rows 0..103) from the
 * pre-rotated copies in `shifted` (see rm_scroll_prebuild), then fill the area above the band and
 * advance the scroll state. */
void rm_blit_road_scroll(ScrollState *s, const uint8_t *shifted, Framebuffer *fb);

/* ---- course advance (game_update's section 12 @0x11xxx) ----
 *
 * One step of "the course scrolls toward you". The original keeps the whole course window as a single
 * grid of 0x20-byte rows, one row per distance band, and each step moves every row one band nearer
 * and refills the far end from the next packed course record. RoadPose.seg_data is that grid's row
 * -1 — the road's slope column — and CourseRing below is rows 0..13, the scenery / marker bands.
 * (In the image the two are contiguous: seg_data[11]/[12] are the row -1 fields the original calls
 * marker_slope_src / marker_decay_base.) */

/* Course-progress state. row_ctr paces the record stream: a record's slopes and objects are held for
 * several bands before the next one is pulled. */
typedef struct {
    uint16_t row_ctr;    /* course-record row countdown (-8 per step; < 0 pulls the next record) */
    uint16_t read_pos;   /* byte offset into the packed course stream ((+8) & 0x1ff8) */
} CourseState;

/* Advance the course one step: scroll the slope column and the ring one band nearer, then refill the
 * far end — from the next packed course record when row_ctr underflows, otherwise by carrying the
 * previous slope and ageing the far band's codes. `stream` points at the leg's course-stream base;
 * records lie at NEGATIVE offsets (rec = stream - read_pos). Feed pose AND ring on to
 * rm_build_road_geometry.
 *
 * NOT included from section 12 (they neither read nor write anything here): the collision probe, the
 * record's palette/screen-offset event, and the fx-block / horizon-event dispatch. */
void rm_road_course_advance(RoadPose *pose, CourseState *cs, CourseRing *ring, const uint8_t *stream);

/* ---- player physics (the driving slice of game_update @0x1110e) ----
 *
 * One frame of "what the player's inputs do to the buggy": throttle -> engine rpm -> speed, speed ->
 * road-scroll rate and the view advance that times the course, steering -> wheel position, body lean
 * and road curvature, and the road-edge clamp that pushes you back when you run wide. It is pure
 * scalar state — no framebuffer, no tables rebuilt — and it feeds every render input the demo already
 * has: RoadPose.curve/view_flags, ScrollState.scroll_speed, SpriteState.lean/wheel_pos/skid, and the
 * HUD's speed/time.
 *
 * This is game_update sections 3,4,5,6,7,8,9,10 — including the crash / auto-steer script that takes
 * the controls away while a crash plays out.
 *
 * PRECONDITION — no event pending (`event_pending` == 0). What is still NOT ported is the system that
 * *decides* to crash you: section 12's collision probe, the fx block rebuilt from `obj_flags`, and the
 * horizon-event dispatch that arms `collision_lock` / `crash_phase` / `turn_flags` / the spin pair (and
 * that also delivers the checkpoint and finish-line events which end a leg). Once armed by that
 * system, the script here plays the crash out and hands the controls back on its own.
 *
 * Two writes the original's section 6 makes are deliberately absent, both sound: the `rev_reload`
 * poke that accompanies an rpm override, and restoring the VBL sound vector on the terminal record.
 * Sound is off-frame state this slice does not own (see [[buggyboy-sound-architecture]]). */

/* Input bits, as the original's input_state packs them (joystick, or arrow keys mapped by read_input).
 * COAST is not a joystick bit — IN_MASK strips it from live input; only the crash script raises it
 * (via turn_flags), and section 7 reads it as "engine coasting down". */
#define RM_IN_ACCEL 0x01
#define RM_IN_BRAKE 0x02
#define RM_IN_LEFT  0x04
#define RM_IN_RIGHT 0x08
#define RM_IN_COAST 0x10
#define RM_IN_FIRE  0x80

/* Two rows of the road control table are read back as geometry *outputs* (the original aliases them
 * as the globals road_edge_flags / road_geom_hi, both of which land inside road_curve_tbl): the
 * shoulder/edge flags at the buggy's row, and the near-row sign that enables the narrow clamp. */
#define RM_CTRL_EDGE_FLAGS_OFF  0x160   /* control long #88, high word: edge/shoulder flag bits */
#define RM_CTRL_GEOM_HI_OFF     0x198   /* control long #102, high word: < 0 enables the edge clamp */

typedef struct {
    /* ---- per-frame input ---- */
    uint16_t input;            /* this frame's RM_IN_* bits */
    uint16_t input_prev;       /* previous frame's bits (the fire press is edge-triggered) */
    bool     game_over;        /* forces full throttle and blanks the clock */
    int16_t  hscroll_step2;    /* ScrollState.hscroll_step2 from the previous frame; biases the curve */

    /* ---- engine + speed (§7) ---- */
    uint16_t engine_rpm;
    uint16_t rpm_cap;          /* per-leg rev limiter, from the legflag record (§3 reloads it) */
    uint16_t rpm_add;          /* per-leg throttle step, likewise */
    uint16_t speed_raw;        /* out: (rpm - idle) * 3 — the lean-animation rate */
    uint16_t speed;            /* out: speed_raw plus high-speed jitter — the speedometer */
    uint16_t speed_jitter_ph;

    /* ---- view bank + road scroll (§8) ---- */
    uint16_t scroll_phase;
    int16_t  scroll_speed;     /* out: road-band scroll rate for this rpm */
    uint16_t view_flags;       /* out: view/leg selector, 0/2/4/6 */
    uint16_t view_bank;        /* out: toggles 0/8 on each wrap */
    bool     view_wrapped;     /* out: view_flags wrapped -> advance the course this frame */
    int16_t  ground_view_off;  /* out: ground/object scan column (view_flags * 0xdd) */
    int16_t  road_edge_sel;    /* out: byte offset into the road edge-run table bank */

    /* ---- steering + body pose (§5, §9, §10) ---- */
    uint16_t wheel_pos;        /* 0..4, centre 2 */
    uint16_t steer_hold;       /* frames the steering has been held off-centre */
    uint16_t lean_phase;       /* +1 & 0xf each frame; indexes the lean animation table */
    uint16_t lean;             /* out: buggy body lean */
    uint16_t buggy_draw_flag;  /* out: nonzero on the lean-table frames that show the lower body */
    int16_t  road_curve;       /* in/out: signed road curvature — the steering integrator */
    bool     curve_clamp;      /* out: the curve hit the edge limit (adds engine drag next frame) */
    int16_t  skid;             /* in: last frame's push (selects the steer-curve row); out: this frame's
                                * off-road push, 0 or +/-8. Also suppresses the foreground sprite. */
    int16_t  crash_disp;       /* out: vertical displacement while ploughing off-road (row offsets) */

    /* ---- crash / auto-steer script (§6) ---- */
    uint16_t collision_lock;   /* in/out: crash_anim_tbl cursor. Nonzero = the script has the controls;
                                * it steps the cursor per frame and clears this on the terminal record. */
    int16_t  crash_phase;      /* in/out: which crash the script is playing. < 0 suspends the edge
                                * clamp; == CRASH_PHASE_LEAN leans the body with the wheel. */
    uint16_t turn_flags;       /* in/out: the input bits the script forces (RM_IN_COAST) */
    uint16_t event_pending;    /* in: PRECONDITION 0 — see the note above */
    uint16_t spin_reset;       /* in/out: spin lean override; the pair is cleared together */
    uint16_t spin_word2;       /* in/out: the second override, used when spin_reset is 0 */
    uint16_t curve_window_lo;  /* in/out: a road_curve window that skips the script forward one record */
    uint16_t curve_window_hi;  /*         and disarms itself; zero lo = no window armed */
    int16_t  steer_delta;      /* out: the script's per-frame kick into the curve integrator */
    int16_t  buggy_pitch_off;  /* out: body pitch while the script plays (the crash bounce) */
    uint16_t curve_freeze;     /* in: nonzero freezes the curve integrator for this frame */
    uint8_t  anim_frame_sel;   /* out: the sprite animation frame the script selects */
    uint8_t  marker_pending;   /* out: the marker effect id the script raises */

    /* ---- HUD-facing counters (§3, §4) ---- */
    uint16_t fire_hold;        /* frames left in the fire-triggered dashboard animation */
    uint16_t dsp_variant_idx;  /* out: dashboard-variant record offset the HUD draws */
    uint16_t leg_flags_sel;    /* which legflag record supplies rpm_cap/rpm_add */
    uint16_t time_subctr;      /* frame subdivider under the bonus-time clock */
    int16_t  time_left;        /* out: bonus time remaining */
    int16_t  hud_crash_timer;  /* out: armed when the clock runs out; freezes the clock, forces braking */
    bool     timeout_gate;     /* nonzero suppresses arming hud_crash_timer at time-out */
} PlayerState;

/* Static ST-format tables the physics indexes (STATIC region, big-endian; see st.h). */
typedef struct {
    const uint8_t *lean_anim_tbl;    /* byte: lean per frame, at lean_phase + (rpm & 0x70) */
    const uint8_t *scroll_speed_tbl; /* word: scroll rate, at scroll_phase + (rpm & 0x70) */
    const uint8_t *speed_jitter_tbl; /* word: speedometer jitter, at speed_jitter_ph & 0xe */
    const uint8_t *steer_curve_tbl;  /* byte: curvature delta — CURSOR-ZERO, the row index is signed
                                      * ((skid + wheel_pos) << 3 reaches -0x40) */
    const uint8_t *legflag_tbl;      /* long records {rpm_cap:w, rpm_add:w}, at leg_flags_sel */
    const uint8_t *crash_anim_tbl;   /* 8-byte crash-script records, at collision_lock (see player.c) */
} PlayerAssets;

/* Advance one frame of player physics from p->input. `ctrl` is this frame's road control table
 * (rm_build_road_geometry's output), read for the edge flags above. */
void rm_player_update(PlayerState *p, const PlayerAssets *a, const uint8_t *ctrl);

/* ---- player buggy + foreground sprites (draw_fg_sprite .. draw_buggy @ 0x1518a..) ---- */

/* Dynamic per-frame state the buggy/foreground sprite draws read (recreate's scalar globals, named).
 * All the sprites blit bottom row first, walking one scanline up per row, into the draw buffer.
 * lean_accum / lean_frame are in/out: draw_buggy_hi advances the lean animation and writes them back.
 * variant is a draw_buggy scratch (lean * 8) read back by draw_buggy_hi. spin_counter is written by
 * draw_fg_sprite (0, or a spin duration when a hard curve aborts the draw). */
typedef struct {
    /* buggy body position + selection */
    uint16_t lean;            /* body lean; indexes buggy_body_tbl, gates the hi overlay (>= LEAN_MAX
                               * skips it), and (* 8) is the hi piece-list variant */
    int16_t  pitch;           /* vertical buggy position offset (road pitch) */
    int16_t  skid;            /* horizontal buggy skid offset (+/-8) */
    int16_t  crash_disp;      /* vertical crash displacement (shifts the buggy up) */
    uint16_t wheel_pos;       /* wheel/steer position; selects the lower-body piece list */
    uint16_t variant;         /* out/scratch: lean * 8 (draw_buggy_hi reads it back) */
    /* foreground sprite (draw_fg_sprite) */
    int8_t   spin_state;      /* <0 while spinning after a crash */
    int16_t  road_curve;      /* signed road curvature; a hard curve aborts a spin's draw */
    uint16_t sprite_suppress; /* nonzero suppresses the foreground sprite */
    int8_t   fg_gate;         /* bit7 set suppresses the foreground sprite */
    uint16_t anim_frame;      /* word byte-offset into fg_anim_tbl for the current frame */
    uint16_t spin_counter;    /* out: frames the buggy spins (also indexes the lower-body list) */
    uint32_t spin_reset;      /* longword; nonzero suppresses the lower body */
    /* lower body (draw_buggy_lo) gates */
    uint16_t buggy_draw_flag; /* nonzero enables the lower-body draw */
    uint8_t  buggy_gate;      /* OR'd with fg_gate; bit7 suppresses the lower body */
    uint16_t collision_lock;  /* nonzero suppresses the lower body */
    /* lean overlay (draw_buggy_hi) animation */
    uint16_t speed_raw;       /* raw speed; drives the lean-animation rate */
    uint16_t lean_accum;      /* in/out: lean-anim rate accumulator */
    uint16_t lean_frame;      /* in/out: lean-anim frame offset into the hi piece table */
} SpriteState;

/* Static ST-format asset tables the buggy/foreground sprites read. `gfx` is the unpacked-graphics
 * arena (recreate's buf_c): every sprite's pixels live at `gfx + <table src offset>` (the hi/lo
 * blits add their own sub-arena bias, HI_SRC_OFF / LO_SRC_OFF, on top). The four const piece tables
 * live in the STATIC region; their `src_off` fields index into `gfx`. All are raw big-endian bytes
 * (read via st.h). */
typedef struct {
    const uint8_t *gfx;           /* unpacked-graphics arena (buf_c); sprite pixels at gfx + src_off */
    const uint8_t *fg_anim_tbl;   /* foreground frames: {rows-1:w, dst_off:w, src_off:l} x8 */
    const uint8_t *body_tbl;      /* per-lean body sprite: {src_off:l, flag:b, rows-1:b, pos_off:w} */
    const uint8_t *hi_tbl;        /* rate bytes at [speed_raw>>5], then lean-overlay piece lists */
    const uint8_t *lo_piece_tbl;  /* lower-body piece lists: {rows0:b, rows1:b, (src:w, dst:w) x2} */
    const uint8_t *lo_piece_idx;  /* per-wheel_pos word offset into lo_piece_tbl */
} SpriteAssets;

/* Draw the foreground buggy sprite (spin/curve/suppress gated). Writes s->spin_counter. */
void rm_draw_fg_sprite(SpriteState *s, const SpriteAssets *a, Framebuffer *fb);

/* Draw the player car: body (upright or leaning frames), the lean overlay, and the lower body.
 * Advances s->lean_accum / s->lean_frame and writes s->variant. */
void rm_draw_buggy(SpriteState *s, const SpriteAssets *a, Framebuffer *fb);

/* ---- ground / horizon band (draw_ground @0x10ff2) ---- */

#define GROUND_SCAN_ENTRIES 13    /* scanline descriptors scanned for the first draw marker */

/* Per-frame ground/horizon inputs. draw_ground scans `markers` (recreate reads the marker byte at
 * +3 of each 0x20-stride descriptor) for the first 0x1a (colour gradient) or 0x1c (solid fill) and
 * draws that one band; `view` is the column index into the per-entry offset table. Entry i selects
 * band (GROUND_SCAN_ENTRIES-1 - i), so markers[0] is the farthest band. */
typedef struct {
    uint8_t  markers[GROUND_SCAN_ENTRIES];  /* per-entry draw marker (0x1a gradient / 0x1c solid) */
    int16_t  view;                          /* signed column index into the per-entry offset table */
} GroundState;

/* Static ground asset tables (STATIC region + colour palette, ST big-endian bytes). col_tbl holds
 * one signed word draw-buffer offset per entry (stride GROUND_COL_STRIDE), indexed by `view`;
 * band_records are the 0x1a gradient descriptors [bands-1, backup, colours...]; color_pairs is the
 * 4-plane solid fill per colour index. */
typedef struct {
    const uint8_t *col_tbl;       /* per-entry buffer offset words (stride GROUND_COL_STRIDE) + view */
    const uint8_t *band_records;  /* gradient records: {bands-1:b, backup:b, colour bytes...} stride 8 */
    const uint8_t *color_pairs;   /* 4-plane (8-byte) solid fill per colour index */
} GroundAssets;

/* Fill the first ground/horizon band whose descriptor carries a draw marker (a colour gradient or a
 * solid fill), into the draw buffer. No-op when no entry carries one. */
void rm_draw_ground(const GroundState *s, const GroundAssets *a, Framebuffer *fb);

/* ---- scaled roadside object (draw_object @0x1087e) ---- */

/* The one scaled roadside object drawn per frame (the near "billboard"): draw_object scans the road
 * control table for the object's visible rows, derives its screen edges + a centre band, and paints
 * solid scale-fills with antialiased edge cells. Inputs: `width_tbl` is the per-scanline road control
 * long table (build_road_geometry's output — same table render_road reads); `shade` sign-selects the
 * centre/near fill pattern. */
typedef struct {
    const uint8_t *width_tbl;     /* per-scanline road control longs (flags high word, half-width low) */
    const uint8_t *blit_mask_l;   /* left-edge antialias masks, indexed (x & 0xf) << 2 (cursor-zero) */
    const uint8_t *blit_mask_r;   /* right-edge antialias masks, indexed (x & 0xf) << 2 (cursor-zero) */
    int16_t        shade;         /* sign selects the centre-band / near fill pattern */
} ObjectInput;

void rm_draw_object(const ObjectInput *in, Framebuffer *fb);

/* ---- fine-x (sub-pixel) masked sprite blit engines (the leaf writers under draw_object_list) ----
 *
 * Both shift a 16-pixel source column to an arbitrary pixel x so a sprite straddles two dest columns,
 * walking one scanline up per row. `dst`/`dst_off` name the framebuffer target; `src`/`src_off` the
 * sprite arena — separate buffers (remaster) where recreate threaded one flat image. */

/* Colour-indexed engine (recreate's blit_objshift @0x14680): SHOW mask ~(A|B|C)&D over four planes,
 * pixels gated by color_pairs[color]. `stride` is the per-row src-stride word; base_cells 1 / 2
 * select the width family (0x98 / 0x90). */
void rm_blit_objshift(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                      uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                      const uint8_t *color_pairs, int base_cells);

/* Plain engine (recreate's blit_objshift2 @0x13ed6): SHOW mask ~(w0|w1), pixels copied plain-shifted
 * and OR'd (no colour). width_idx 0/1/2 = base ceiling 0x88/0x90/0x98. */
void rm_blit_objshift2(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                       uint16_t x, uint16_t rows_m1, int width_idx);

/* objsprite engine (recreate's @0x131f6): the third fine-x blitter — four-word SHOW mask, no colour.
 * width_idx 0/1/2/3 selects WIDTH 0x80/0x88/0x90/0x98 (the t4/w88/t2/t1 glue). */
void rm_objsprite(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                  uint16_t x, uint16_t rows_m1, int width_idx);

/* Alt entry (recreate's @0x13204, t53): aligned_col / shl / shr precomputed by the caller. */
void rm_objsprite_alt(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                      uint16_t aligned_col, unsigned shl, unsigned shr, uint16_t rows_m1);

/* ---- roadside-object display-list dispatcher (draw_object_list @0x1306e) ----
 *
 * Two nested loops walk the per-frame object list, dispatching each object through obj_type_jumptable
 * to one of the fine-x blit engines / handler families above. Everything it reads lives in a distinct
 * arena (below); the only thing it WRITES is the draw target `px` at `draw_buf`-relative offsets — so
 * the whole dispatcher takes const arena pointers + one mutable draw target, no flat image. */
typedef struct {
    uint8_t       *px;           /* draw target base (framebuffer bytes) */
    uint32_t       draw_buf;     /* draw-buffer offset within px (0 for the real framebuffer) */
    const uint8_t *buf_a;        /* record arena: per-type + special object records */
    const uint8_t *buf_c;        /* sprite-pixel arena (record src longs index into it) */
    const uint8_t *color_pairs;  /* 4-plane fill per colour index (the objshift engine reads it) */
    const uint8_t *view_xform;   /* per-view sprite transform records (obj_view_xform @0x1722a) */
    const uint8_t *objsh2p_tbl;  /* per-scanline dst-offset table for the objshift2 P-prefix family */
    const uint8_t *jumptable;    /* obj_type_jumptable: word offset per jumpidx -> handler */
    const uint8_t *xoff_tbl;     /* per-row shared x-offset word table (a4) */
    uint16_t view_flags;         /* leg/view selector (0,2,4,6) */
    uint16_t view_parity;        /* per-view parity word (handler_lo reads &2) */
    uint16_t bonus_timer;        /* nonzero clamps low object types up to the bonus minimum */
    int16_t  obj_scan_off;       /* signed word added to the list cursor + used by the scan wrapper */
    uint8_t  p24_flag;           /* global byte gating the P24 handler's three-stage path */
} ObjListCtx;

/* Walk one object list. `list`/`flags` are the two input streams (the per-frame passes feed different
 * bases); list_off/flags_off are cursors within them. outer_rows_m1 / rec_off / colour thread the
 * loop state (the real caller passes outer_rows_m1 = 0). */
void rm_draw_object_list(const ObjListCtx *c, const uint8_t *list, uint32_t list_off,
                         const uint8_t *flags, uint32_t flags_off,
                         uint16_t outer_rows_m1, uint16_t rec_off, uint16_t colour);

/* ---- draw_game_objects prefix (gobj_prefix @0x12ef6..0x12fc0) ----
 *
 * The deterministic per-frame state advance draw_game_objects runs before any drawing: the
 * marker-decay slot, the road-colour animation counters, and the bonus-window flag animation. It
 * writes NO framebuffer pixels — it is off-frame game state (counters, the marker scan-table records,
 * the animated colour that feeds the palette). Modeled natively so the render loop can advance it; the
 * fields mirror recreate's scalar globals + the two arenas it mutates. */
typedef struct {
    /* marker-decay: a 14-record slot cleared per frame, counted down, retired when exhausted. */
    uint16_t marker_active;      /* nonzero -> the decay runs this frame */
    int16_t  marker_off;         /* signed record byte-offset into the marker arena */
    int16_t  marker_countdown;   /* -0x20/frame; < 0 retires the slot */
    /* road-colour animation counters. */
    uint16_t view_parity;        /* += 2/frame (per-view parity the object dispatcher reads) */
    uint16_t anim_counter;       /* += 2/frame; & 0x1e indexes the anim tables */
    uint16_t anim_word;          /* out: current anim word (mirrored into buf_a) */
    /* bonus window. */
    uint16_t bonus_timer;        /* frames left; 0 = closed */
    uint16_t dsp_color_scroll;   /* cycles 0..4 while the window is open */
    uint16_t flag_seq_off;       /* advanced at bonus_timer == 0x28 */
    int16_t  flag_seq_count;     /* reset to 0 at the cap */
} GobjPrefixState;

/* Static/arena data gobj_prefix reads + the buffers it mutates. anim_word_tbl / anim_coloridx_tbl are
 * STATIC word tables; color_pairs is the palette source; marker_recs is the 14-record decay arena;
 * anim_color (8 bytes) + the two buf_a anim-word mirrors receive the animated colour. */
typedef struct {
    const uint8_t *anim_word_tbl;      /* word table -> anim_word, indexed (anim_counter & 0x1e) */
    const uint8_t *anim_coloridx_tbl;  /* word table -> color_pairs offset (<<3) */
    const uint8_t *color_pairs;        /* palette source (8 bytes copied to anim_color) */
    uint8_t       *marker_recs;        /* marker-decay record arena (base; marker_off indexes it) */
    uint8_t       *anim_color;         /* out: 8-byte animated colour pair */
    uint8_t       *anim_mirror1;       /* out: buf_a + 0xd70 anim-word mirror */
    uint8_t       *anim_mirror2;       /* out: buf_a + 0x1250 anim-word mirror */
} GobjPrefixAssets;

/* Advance the per-frame object state (marker decay, colour animation, bonus flag). No framebuffer
 * writes. */
void rm_gobj_prefix(GobjPrefixState *s, const GobjPrefixAssets *a);

#endif /* RM_GAME_H */
