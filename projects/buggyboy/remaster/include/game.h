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
#include "sound.h"   /* SoundDriver — the in-race sound trigger state the event/physics slices drive */

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
    int16_t crash_lap;         /* remaining bonus units -> one fuel column each (phase 6a). VIEW of
                                * EventState.crash_lap (narrowed to signed); the game loop copies it in */
    uint16_t speed;            /* speedometer value (phase 1 formats its low byte into the string) */
    uint16_t time_left;        /* bonus time remaining (phase 2 formats into the string) */
    bool game_over;            /* blank the timer to 0 when set (phase 2) */
    bool dsp_toggle;           /* suppress the dashboard-variant sprite when set (phase 3) */
    uint16_t dsp_variant_idx;  /* byte offset into the dashboard-variant record table (phase 3) */
    uint16_t gauge_blink;      /* small-gauge blink phase; bit1 of (blink-1) gates the draw (phase 6b).
                                * VIEW of EventState.gauge_blink; the game loop copies it in */
    bool gauge_blink_on;       /* enable the extra bar under the blinking small gauge (phase 6b). VIEW
                                * of EventState.gauge_blink_on (narrowed to bool) */
    bool crash_active;         /* crash/bonus-tally gate (phase 8). VIEW of EventState.crash_active
                                * (narrowed to bool) */
    int16_t crash_frame;       /* crash-effect frame counter; +1 drives the colour cycle (phase 8) */
    uint16_t crash_bars;       /* number of gauge bars to draw, 0-5 (phase 8). VIEW of
                                * EventState.crash_bars; the game loop copies it in */
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

/* Draw the whole HUD (all 8 phases) into `fb` from this frame's scalars + the static asset tables. */
void rm_draw_hud(const HudState *s, const HudAssets *a, Framebuffer *fb);

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
/* Stage 4's band stamp emits Σ(width_count[bank+band] + 1) words at stride 4, which runs 2 bytes
 * past RM_CTRL_BYTES on view bank 0 and 6 bytes on banks 2/4/6 — faithful to the original, whose
 * writes spill into the bytes after the table (nothing reads them). Allocating the spill is cheaper
 * than a bounds check in the 106-write stamp loop; the pad is the 6-byte worst case rounded up to a
 * whole long so derived buffers stay long-sized. test_geometry pins it to the measured write extent. */
#define RM_CTRL_STAMP_SPILL 8
#define RM_CTRL_ALLOC_BYTES (RM_CTRL_BYTES + RM_CTRL_STAMP_SPILL)
#define RM_CTRL_WIDTH_OFF   0x28
#define RM_SCANLINE_BYTES   0x80        /* per-row cumulative-slope scratch (road_scanline_tbl) */

/* set_horizon (geometry.c) clamps horizon_row to the even range [0, RM_HORIZON_DIV*2], so the deepest
 * row is RM_MAX_HORIZON_ROW. RM_HORIZON_DIV is the one source of truth for the clamp bound (geometry.c's
 * HORIZON_DIV is defined from it); events.c sizes its fx scratch against the max row. */
#define RM_HORIZON_DIV      0x16
#define RM_MAX_HORIZON_ROW  (RM_HORIZON_DIV * 2)   /* 0x2c: the highest horizon_row set_horizon emits */

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

/* Rebuild `ctrl` (allocate RM_CTRL_ALLOC_BYTES; the table proper is RM_CTRL_BYTES of ST bytes) — the
 * control-long table render_road consumes — and the `scanline` scratch (RM_SCANLINE_BYTES), from the
 * pose, the const sources and the ring's per-band road widths. Also writes the pose's seg_head /
 * horizon_row / horizon_frac outputs. */
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
 * record's palette/screen-offset event (rm_course_mode_event below), and the fx-block / horizon-event
 * dispatch. Returns TRUE when a new record was pulled this step (row_ctr underflowed) — the caller
 * fires rm_course_mode_event only then, exactly as the original runs the mode event inside the pull. */
bool rm_road_course_advance(RoadPose *pose, CourseState *cs, CourseRing *ring, const uint8_t *stream);

/* ---- the ring's other consumers ----
 *
 * The original holds the ring as a flat grid of RM_RING_ROW_BYTES rows in the image, and FOUR other
 * subsystems read that same grid through raw pointers: the object-list dispatcher's two flag streams,
 * draw_game_objects' sprite-slot count, draw_ground's per-band markers, and the buggy/foreground
 * sprite gates. Everything below is that aliasing made explicit, so a game loop holds ONE live
 * CourseRing and derives every consumer's view from it (seeding any of them once from a snapshot is
 * how the demo ended up with scenery frozen at fixture-generation values — see PORTING.md). */

#define RM_RING_ROW_BYTES ((RM_RING_SLOTS + 1) * 2)   /* one serialized band: 15 slot words + marker */

/* Packed course record — the 8-byte wire layout the ring is filled from, shared by BOTH decoders:
 * course.c's rm_road_course_advance (the per-frame course-stream refill) and gameplay.c's
 * init_ring_seed (the leg-start seed from the leg's 14 marker records). One canonical definition so
 * the two cannot drift (see CLAUDE.md §5). */
#define RM_REC_SELECT_OFF 0        /* word: bit (RM_RING_SLOTS-1 - s) selects slot s */
#define RM_REC_CTL_OFF    2        /* byte: row_ctr reload (& 0xf8) and new slope (& 7) */
#define RM_REC_CODES_OFF  3        /* the selected slots' type codes, one byte each, in slot order */
#define RM_REC_MARKER_OFF 6        /* word: the new band's marker word */
#define RM_REC_STRIDE     8        /* one record is 8 bytes */

/* Serialize the ring into the original's flat ST-byte row grid (RM_RING_ROWS x RM_RING_ROW_BYTES
 * big-endian words) for the object-list dispatcher, which walks its flag streams through the grid
 * exactly as the original walked the image: the sprite passes' stream starts at row 1's slots
 * (dst + RM_RING_ROW_BYTES), the fixed pass's at row 12's (dst + 12 * RM_RING_ROW_BYTES). Rebuild
 * after every rm_road_course_advance. */
void rm_ring_store_st(const CourseRing *ring, uint8_t *dst);

/* draw_game_objects' sprite-slot count — how the two roadside object-list passes split. The original
 * walks the grid's marker column: 0 if row 0's marker is negative, else the number of consecutive
 * non-negative markers over rows 1.., capped at RM_RING_SPRITE_ROWS. */
#define RM_RING_SPRITE_ROWS 11
uint16_t rm_ring_sprite_count(const CourseRing *ring);

/* draw_ground's per-band draw markers (GROUND_SCAN_ENTRIES bytes): band i's marker is the low byte
 * of ring row i's slot RING_GROUND_MARKER_SLOT — the byte the original reads at descriptor+3 from
 * 0x18d48 (= ring row base + 0xc + 3). Refresh before each draw. */
void rm_ring_ground_markers(const CourseRing *ring, uint8_t *markers);

/* The buggy/foreground sprite gates are ring row RM_RING_GATE_ROW's marker bytes in the original
 * (0x18eba/0x18ebb): the draws suppress the sprite on bit 7 of either — the MARKER_RAW_FLAG a
 * signed marker keeps only through marker_unpack's fall-through. Refresh SpriteState's gates from
 * here after every course advance. */
#define RM_RING_GATE_ROW 11
uint8_t rm_ring_buggy_gate(const CourseRing *ring);
int8_t rm_ring_fg_gate(const CourseRing *ring);

/* The obj_active clear the event engine fires: the original clears image[A_obj_active + slot + 1],
 * and A_obj_active (0x18eb4) sits inside the ring's row grid (base 0x18d3c), so the write lands at
 * flat grid offset RM_RING_OBJ_ACTIVE_OFF + slot. rm_ring_poke_byte inverts rm_ring_store_st's flat-
 * grid mapping — RM_RING_ROW_BYTES rows of 16 big-endian words — to poke one byte (band/word/parity)
 * of the live ring, so the handlers touch it directly instead of a serialized copy. */
#define RM_RING_OBJ_ACTIVE_OFF 0x179   /* 0x18eb5 - 0x18d3c: obj_active[slot+1] as a flat grid offset */
void rm_ring_poke_byte(CourseRing *ring, unsigned flat_off, uint8_t val);

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
 * Section 6's event path is now wired in: when `event_pending` is set (and the crash lock is clear),
 * this function dispatches the pending event through the course-event engine (`rm_event_dispatch`,
 * via the `ctx` bundle) — the system that *decides* to crash you (section 12's collision probe, the fx
 * block rebuilt from `obj_flags`, and the horizon-event dispatch) arms `collision_lock` / `crash_phase`
 * / `turn_flags` / the spin pair through that same bundle, and a bonus-display record rebuilds `ctrl`
 * in place. Once armed, the script here plays the crash out and hands the controls back on its own.
 * The probe and the fx / horizon dispatch themselves run on the caller's view-wrap frame (see the
 * frame loops in `game_main.c` / `equiv._Candidate`), not inside this function.
 *
 * Section 6's sound is now wired (slice 2, via the ctx's SoundDriver): the terminal record restores the
 * VBL sound vector, and §1's marker gate / engine-sound block fire through the trigger layer. The one
 * write still skipped is the `rev_reload` poke that accompanies an rpm override — it aliases lean_frame
 * (0x18d12), which no compared surface reads. */

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

/* rm_player_update's §6 event path dispatches through the course-event engine (defined at the end of
 * this header); forward-declared here so the physics prototype can name it. */
typedef struct RmEventCtx RmEventCtx;

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
    uint16_t event_pending;    /* in: nonzero -> §6 dispatches this event idx through ctx, then clears
                                * it (recreate game_update §2). See the note above. */
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
 * (rm_build_road_geometry's output), read for the edge flags above and REBUILT IN PLACE when §6's
 * event path fires a bonus-display record. `ctx` bundles the course-event state §6 dispatches through;
 * its player MUST be `p` and its ctrl MUST be `ctrl` (the dispatch mutates them through the bundle). */
void rm_player_update(PlayerState *p, const PlayerAssets *a, uint8_t *ctrl, RmEventCtx *ctx);

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

/* PERF30 A3 phase 1 — hand-written m68k core for the fixed-pass engine (src/asm/objshift2.S). The C
 * above stays the byte-exact REFERENCE (fuzz-pinned); the asm is a drop-in with the same signature.
 *
 * Per-core selection flags (F10): RM_ASM_BLIT is the umbrella the m68k builds pass; it turns on each
 * individual core flag (unless already defined), and each engine's dispatch macro keys off its OWN
 * flag. So the objshift2 core is RM_ASM_OBJSHIFT2, and phase 2's rm_blit_objshift core is
 * RM_ASM_OBJSHIFT — each independently bisectable (define/undef one flag to A/B a single core), while
 * the umbrella keeps the build scripts a single -DRM_ASM_BLIT. The host test build defines neither, so
 * every RM_BLIT_* macro resolves to the C reference and the host suite keeps pinning C; the asm-vs-C
 * equivalence is pinned separately by test/test_asm_blit.py under Musashi. */
#ifdef RM_ASM_BLIT
#  ifndef RM_ASM_OBJSHIFT2
#    define RM_ASM_OBJSHIFT2
#  endif
#  ifndef RM_ASM_OBJSHIFT
#    define RM_ASM_OBJSHIFT
#  endif
#endif

#ifdef RM_ASM_OBJSHIFT2
void rm_blit_objshift2_asm(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                           uint16_t x, uint16_t rows_m1, int width_idx);
#define RM_BLIT_OBJSHIFT2 rm_blit_objshift2_asm
#else
#define RM_BLIT_OBJSHIFT2 rm_blit_objshift2
#endif

/* PERF30 A3 phase 2 — hand-written m68k core for the colour-indexed pass-1 engine (src/asm/objshift.S).
 * Same umbrella (RM_ASM_BLIT) and per-core flag shape as objshift2; the C rm_blit_objshift stays the
 * byte-exact REFERENCE, pinned vs the asm by test/test_asm_blit.py under Musashi. */
#ifdef RM_ASM_OBJSHIFT
void rm_blit_objshift_asm(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
                          uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
                          const uint8_t *color_pairs, int base_cells);
#define RM_BLIT_OBJSHIFT rm_blit_objshift_asm
#else
#define RM_BLIT_OBJSHIFT rm_blit_objshift
#endif

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

/* Fan the flag-sequence state GobjPrefixState OWNS into the HUD view the draw reads: the phase-4
 * bar count and the phase-5 colour-index cursors. The original's draw_hud reads these globals
 * directly (flag_seq_count/flag_seq_off/dsp_color_scroll); the remaster HudState is a per-frame VIEW,
 * so the shell must copy them in — exactly as it copies EventState's crash scalars (rm_apply_player).
 * Runs at HUD-draw time, AFTER rm_gobj_prefix (which advances these), mirroring the original's order
 * (g_draw_game_objects then g_draw_hud). Without it the flag-sequence bars never appear. */
void rm_gobj_hud_view(const GobjPrefixState *g, HudState *hud);

/* ---- whole-frame render composition (draw_frame @0x12e22 + draw_game_objects @0x12dcc) ------------
 *
 * The platform-independent per-frame render pipeline, in the exact order the game draws it: the
 * off-frame prefix advance, then the road (geometry -> raster -> fine-scroll band), then the object
 * tree (ground, foreground sprite, the two roadside-sprite passes split around the scaled object, and
 * the fixed pass ordered against the buggy by the view), then the HUD (with the flag-sequence fan-out
 * just before it). Hoisted out of the on-target shell (render/atari/game_main.c) and the bench
 * (the shell calls it; bench_main.c deliberately mirrors it with staged HUD scalars) — and, crucially, so `make test` runs the shell's real
 * frame end-to-end (the composed-frame differential in test/equiv.py) and catches any missing wiring
 * between the individually-verified stages. The shell keeps only buffer selection + Setscreen.
 *
 * How the two roadside object-list passes split (rm_ring_sprite_count over the ring's marker column). */
#define GOBJ_SPRITE_LAST    10       /* the fixed pass runs when sprite_count <= this */
#define GOBJ_ROW_A3_STRIDE  0x20     /* pass-2 flag-stream cursor step per skipped sprite row */
#define GOBJ_ROW_A5_STRIDE  0x22     /* pass-2 list cursor step per skipped sprite row */
#define GOBJ_D6_INIT        0xb0     /* pass-1 rec_off seed */
#define GOBJ_D6_ROW_STEP    0x10     /* pass-2 rec_off decrement per skipped sprite row */
#define GOBJ_VIEW_REAR      4        /* view_flags bit: rear view -> buggy draws before the fixed pass */
#define GOBJ_SPRITE_PASS_ROW 1       /* the sprite passes' flag stream starts at this ring row */
#define GOBJ_FIXED_PASS_ROW 12       /* the fixed-object pass's flag stream starts at this ring row */

/* Every per-race owner struct the render reads + its const asset bundle + the scratch buffers the
 * stages thread through, in one handle so rm_draw_frame takes one argument. The owner structs carry
 * THIS frame's state (populated by rm_apply_player / rm_gobj_hud_view / the leg-start derivations
 * before the call); rm_draw_frame only reads them + writes the few cursor fields the original writes
 * inside the draw (objlist view_parity/px/xoff_tbl, road width_tbl, scroll seg_head). */
typedef struct {
    /* per-race owner structs the draw reads (mutated by the caller's fan-out) */
    GobjPrefixState *pfx;
    RoadPose        *pose;
    CourseRing      *ring;
    ScrollState     *scroll;
    GroundState     *ground;
    SpriteState     *sprite;
    ObjListCtx      *objlist;
    ObjectInput     *object;
    HudState        *hud;
    RoadInput       *road;
    /* const asset bundles */
    const GobjPrefixAssets *pfx_assets;
    const RoadSource       *src;
    const GroundAssets     *ground_assets;
    const SpriteAssets     *sprite_assets;
    const HudAssets        *hud_assets;
    /* scratch buffers threaded through the stages */
    uint8_t       *ctrl;          /* per-frame control-long table (geometry out; road/objlist in) */
    uint8_t       *scanline;      /* build_road_geometry scratch */
    const uint8_t *shifted;       /* pre-rotated scroll copies (rm_scroll_prebuild output) */
    uint8_t       *ring_st;       /* the ring serialized to the flat ST row grid (dispatcher flag streams) */
    /* obj-low program-data list bases the two object-list pass families walk */
    const uint8_t *obj_sprite_disp;  /* low + OBJ_LOW_SPRITE_DISP: the roadside-sprite display list */
    const uint8_t *obj_fixed_list;   /* low + OBJ_LOW_LIST_BASE:  the fixed-object display list */
} RmScene;

/* Compose one whole frame into `fb`, in the game's exact draw order. See the notes above. */
void rm_draw_frame(const RmScene *sc, Framebuffer *fb);

/* ---- shared score helper (add_score @0x1580a) ----
 *
 * Six ASCII score digits (score_bcd, MS first) plus their on-screen copy (score_str[4..9]), both
 * inside the shared HUD-text region. Add a 6-byte BCD delta, carry decimal, refresh the display
 * digits and blank leading zeros. The HUD's crash tally and the event engine both call it — one
 * definition, no duplicate (CLAUDE.md §6). Offsets are within the 0x18172 HUD-text base. */
#define RM_HUD_SCORE_STR_OFF     0xbe   /* score_str  (image 0x18230); live digits at +4 */
#define RM_HUD_SCORE_BCD_OFF     0xda   /* score_bcd  (image 0x1824c); 6 ASCII digits */
#define RM_HUD_SCORE_OVERLAY_OFF 0xa3   /* score_overlay_dig (image 0x18215); bonus-overlay digit */
#define RM_SCORE_DIGITS          6
/* The value §I stamps into hud_crash_timer when a checkpoint rolls the score digit past its max: the
 * leg-complete sentinel the (unported) leg/game flow watches for to end the leg. */
#define RM_HUD_TIMER_LEG_END     0x65
void rm_score_add(uint8_t *score, uint8_t *score_str, const uint8_t *delta, bool game_over);

/* Step the first not-yet-drained score-digit rollover record over `crash_bars` (in `text`, the shared
 * HUD-text region): +RM_CRASH_ROLL_STEP into the ones digit, carrying one out of the tens — or reset
 * the ones when the tens reach RM_CRASH_ROLL_HI (see the RM_CRASH_* layout below). Returns whether a
 * record was stepped. The crash-fx UPDATE (events.c) and its DRAW (hud.c, on a throwaway HUD-text
 * copy) share this one definition — one walk, no duplicate (CLAUDE.md §6). */
bool rm_crash_rollover_step(uint8_t *text, uint16_t crash_bars);

/* ---- course-event engine (game_update §12's tail + the jump-table dispatch) ----
 *
 * The system that decides to crash you and ends a leg. It reads the near course bands (the ring), the
 * horizon the geometry builder produced, and the record's event byte; it arms the crash script's
 * PlayerState fields, bumps the checkpoint/score counters, and rebuilds the dashboard on a checkpoint.
 * It writes NO framebuffer pixels — everything it touches is off-frame game state or the graphics
 * arena (the dashboard/banner bitmaps a later HUD/draw pass consumes).
 *
 * IN-RACE sound is WIRED (slice 2): every play_event_tune / handle_marker / stop_music the original
 * fires drives the ctx's SoundDriver through the trigger layer (sound.h), guarded on ctx->game_over.
 * The driver state (SND_STATE + voices), the VBL enable and the Dosound ledger are compared against
 * recreate in the leg / dispatch / crash drives.
 */

/* Dynamic event-engine state (recreate's scalar globals, named). The crash-script fields the handlers
 * arm live in PlayerState (collision_lock, crash_phase, turn_flags, spin_reset/word2, curve_window_*,
 * curve_freeze, event_pending, road_curve, engine_rpm, speed, time_left, hud_crash_timer); the bonus
 * / flag-sequence counters live in GobjPrefixState (bonus_timer, flag_seq_off, flag_seq_count,
 * marker_active/off/countdown). What is left is here.
 *
 * OWNERSHIP — EventState is the sole OWNER of crash_bars, crash_active, crash_lap, gauge_blink,
 * gauge_blink_on AND the crash-fx tally's crash_frame / abort_flag: the event engine mutates them (see
 * course_markers + rm_crash_fx_update in events.c). HudState declares its own copies of the first five
 * plus crash_frame, but those are the draw's per-frame VIEW — the game loop refreshes them from here
 * before each rm_draw_hud, exactly as it already does for speed / time_left (see game_main.c
 * apply_player). The flow is one-directional (EventState -> HudState copy); the HudState types differ
 * deliberately (crash_active / gauge_blink_on are the draw's bool gate, crash_lap its signed count)
 * and the copy narrows into them. Slice 2 wires that copy. */
typedef struct {
    uint8_t  course_flag_bit;  /* collision-probe bit cursor (0x18c70) */
    uint8_t  dash_y;           /* dash_marker byte y      (0x18c3a) */
    uint8_t  dash_bit;         /* dash_marker bit index   (0x18c3b) */
    uint16_t dash_x;           /* dash_marker word x      (0x18c3c) */
    uint16_t crash_bars;       /* gauge bars / checkpoint counter (0x18d00) */
    uint16_t crash_active;     /* crash/bonus-tally gate  (0x18c7a) */
    uint16_t crash_lap;        /* remaining bonus units   (0x18c4a) */
    uint16_t gauge_blink;      /* checkpoint-banner timer (0x18d02) */
    uint16_t gauge_blink_on;   /* small-gauge extra bar   (0x18d04) */
    uint16_t ckpt_scroll;      /* checkpoint-banner scroll (0x18c72) */
    uint16_t spin_state;       /* the fx<<8 word §G writes (0x18caa); SpriteState.spin_state = its hi byte */
    uint16_t crash_frame;      /* crash-fx frame counter  (0x18c78); +1/frame drives the tally + colour */
    uint16_t abort_flag;       /* leg/game-over abort countdown (0x18c4e): 0xffff (game over) or 0x33
                                * (bonus exhausted), decays by 2/frame — the frame loop ends the leg
                                * when this goes negative */
    /* Record-driven mode-2/4/6 course-event state (course-advance tail; rm_course_mode_event). All
     * three are cleared to 0 by rm_init_leg (they sit in g_init_leg's phase-1 live-state clear). */
    uint16_t scroll_frame;     /* mode 2: road-scroll frame index 0..15 (0x18cb2), indexes the leg scroll table */
    uint16_t palette_cursor;   /* mode 4: palette-record cursor 0..0x1f (0x18cba), indexes buf_a + 0x50 */
    uint16_t palette_toggle;   /* mode 4/6: palette double-buffer toggle (0x18c5c) */
} EventState;

/* Const asset windows the event engine reads (STATIC region + a couple of arena tables), raw
 * big-endian bytes (st.h). score_deltas is one window of 7 contiguous 6-byte BCD records (0x1736a);
 * the byte offsets of each are RM_EVT_SCORE_* below. coll_mask points at the current leg's
 * collision-flag long table (buf_a + leg*0x2000 + 0x5d48), indexed by crash_bars<<2. buf_a / dash_raw
 * / font feed the leg-0 dashboard rebuild (rm_init_leg_dash / rm_draw_leg_labels). */
typedef struct {
    const uint8_t *fx_type_tbl;      /* 0x18640: spin/collision fx records, idx from the gate bits */
    const uint8_t *evt_obj_type_tbl; /* 0x18b68: word[8] collision-object type per rpm band */
    const uint8_t *score_deltas;     /* 0x1736a: 7 x 6-byte BCD add_score deltas */
    const uint8_t *score_label;      /* 0x18540: "SCORE/" header; checkpoint char = [7 + crash_bars] */
    const uint8_t *flag_seq_table;   /* 0x17e3a: expected roadside-object type sequence */
    const uint8_t *probe_deltas;     /* 0x17e7a: 8 x {delta_bit:w, delta_x:w} neighbour probes */
    const uint8_t *ckpt_anim_tbl;    /* 0x17324: checkpoint-banner scroll control records */
    const uint8_t *coll_mask;        /* leg collision-flag longs (buf_a + leg*0x2000 + 0x5d48) */
    const uint8_t *buf_a;            /* leg-dash label/clear/marker-seed tables */
    const uint8_t *dash_raw;         /* mem_base: raw per-leg dashboard block (init_leg_dash source) */
    const uint8_t *font;             /* 1bpp glyphs for the leg labels */
} EventAssets;

/* score_deltas byte offsets (7 contiguous 6-byte BCD records from 0x1736a). */
#define RM_EVT_SCORE_BYTES 6
#define RM_EVT_SCORE_CKPT  0x00   /* checkpoint / end-of-section-I add */
#define RM_EVT_SCORE_GATE  0x06   /* flag-gate normal */
#define RM_EVT_SCORE_MSG   0x0c   /* score-message group A (0x17376) */
#define RM_EVT_SCORE_B     0x12   /* group B (0x1737c) */
#define RM_EVT_SCORE_C     0x18   /* group C (0x17382) */
#define RM_EVT_SCORE_BONUS 0x1e   /* flag-sequence bonus (0x17388) */
#define RM_EVT_SCORE_EVT   0x24   /* marker-decay object spawn (0x1738e) */

/* One frame of the course-event engine, bundling every state view the handlers touch. Passed by
 * pointer so rm_player_update's §6 event path drives rm_event_dispatch through the same bundle the
 * caller's view-wrap tail (probe + fx/horizon) uses — one shared state view across both.
 * gfx is the mutable graphics arena (recreate's buf_c): the dashboard bitmap the probe reads
 * and the banner the checkpoint anim scrolls live in it. Tagged (forward-declared above) so the
 * physics prototype can take an RmEventCtx* before the full definition. */
struct RmEventCtx {
    PlayerState       *player;
    GobjPrefixState   *gobj;
    CourseRing        *ring;
    RoadPose          *pose;
    const RoadSource  *road_src;
    uint8_t           *ctrl;       /* road control table (RM_CTRL_ALLOC_BYTES) rm_build_road_geometry writes */
    uint8_t           *scanline;   /* the builder's per-row scratch (RM_SCANLINE_BYTES) */
    EventState        *ev;
    uint8_t           *hud_text;   /* mutable HUD-text region (base 0x18172): score digits live here */
    uint8_t           *gfx;        /* mutable graphics arena (buf_c): dashboard + banner bitmaps */
    const EventAssets *assets;
    uint16_t           leg;
    bool               game_over;
    SoundDriver       *snd;        /* slice 2: the sound trigger state the event handlers drive */
};

/* Resolve event `idx` (0..64) through the native jump table and run its handler with the frame's slot
 * and the two object-type gate flags. Slice 2 also calls this from the §6 event path. */
void rm_event_dispatch(RmEventCtx *c, uint16_t idx, uint16_t slot, uint16_t flag_a, uint16_t flag_b);

/* Sections G/H/I of the course-advance tail: rebuild the fx block from the near band, dispatch the two
 * horizon-keyed events, then handle the checkpoint / collision / score markers. */
void rm_course_events(RmEventCtx *c);

/* The collision-probe head (game_update §12 lines 509-515): walk the per-course flag bit and, when it
 * fires, step the dashboard progress marker. Runs before rm_road_course_advance on a wrap frame. */
void rm_course_probe(RmEventCtx *c);

/* ---- record-driven mode-2/4/6 palette / screen-offset event (game_update §12 lines 572-602) ----
 *
 * When a record is pulled, the low bits of the new near band's control word (ring row 0's marker high
 * byte & MODE_MASK) select one of three in-race effects:
 *   mode 2 — advance the road-scroll frame and re-pick screen_offset (a COMPARED render surface).
 *   mode 4 — advance the palette cursor, stage the next palette record (its obj_shade IS compared; the
 *            palette itself is an off-image Setpalette seam), reset the toggle.
 *   mode 6 — a per-register tunnel colour poke (off-image Setcolor seam), flipping the toggle.
 * The scalar state (scroll_frame / palette_cursor / palette_toggle) lives in EventState; obj_shade and
 * screen_offset are the shell's leg-start outputs; the palette bytes stage into `race_pal` (below). The
 * ACTUAL palette write is off-image (palette-agnostic byte-compare + golden) and is owned by the shell:
 * rm_course_mode_event reports which write to issue in *out, and the shell issues it (see game_main.c).
 *
 * The mode selector reads ring row 0's marker after the refill: (row0.marker >> 8) & MODE_MASK. */
#define RM_MODE_MASK          6    /* the two control-word bits that select the event */
#define RM_MODE_SCREEN_OFFSET 2    /* road-scroll offset event */
#define RM_MODE_PALETTE       4    /* palette-record stage + obj_shade */
#define RM_MODE_TUNNEL        6    /* per-register tunnel colour poke */
#define RM_PALETTE_CURSOR_MASK 0x1f
#define RM_SCROLL_FRAME_MASK   0xf

/* The mutable in-race palette buffer (RM_RACE_PAL_BYTES = one ST palette, base image 0x17fa2). mode 4
 * and rm_init_leg's phase 11 stage a record's colours into it at RM_PAL_STAGE_* (the original's
 * 0x17fac.. writes overlap the race palette's regs 5/7-11 — a partial in-race fade). The shell seeds it
 * from the const race palette; Setpalette loads it whole. The non-staged bytes never change. */
#define RM_RACE_PAL_BASE   0x17fa2
#define RM_RACE_PAL_BYTES  0x20
#define RM_PAL_STAGE_W2_OFF 0x0a   /* record[0xa..0xb] -> image 0x17fac */
#define RM_PAL_STAGE_W1_OFF 0x0e   /* record[0..1]     -> image 0x17fb0 */
#define RM_PAL_STAGE_L1_OFF 0x10   /* record[2..5]     -> image 0x17fb2 */
#define RM_PAL_STAGE_L2_OFF 0x14   /* record[6..9]     -> image 0x17fb6 */
#define RM_OBJDISP_SHADE_OFF 0x0c  /* obj_shade = be16(record + this) - 2 */

/* What off-image palette write the shell should issue after rm_course_mode_event (all palette-agnostic
 * seams; NONE on modes 0/2). */
typedef enum { RM_PAL_NONE = 0, RM_PAL_SETPALETTE, RM_PAL_POKE_REG } RmPaletteWriteKind;
typedef struct {
    RmPaletteWriteKind kind;
    int16_t  reg;      /* POKE_REG: the colour-register selector (0xffff824c + reg) */
    uint16_t color;    /* POKE_REG: the colour word to poke */
} RmPaletteWrite;

/* Resolve the object-display / palette record: buf_a + 0xf2 + sel*0x10, where sel is the per-leg
 * selector byte buf_a[0x50 + cursor + leg*0x20]. Shared by rm_init_leg (cursor 0) and mode 4. */
const uint8_t *rm_objdisp_record(const uint8_t *buf_a, uint16_t leg, uint16_t cursor);

/* Stage a 14-byte object-display / palette record into `race_pal` (4 pieces at RM_PAL_STAGE_*) and
 * derive obj_shade. Shared by rm_init_leg's phase 11 and mode 4. */
void rm_stage_palette_record(uint8_t *race_pal, int16_t *obj_shade, const uint8_t *disp);

/* This frame's road-scroll offset into buf_c: the leg's 16-byte scroll table (buf_a + leg*0x10) indexed
 * by scroll_frame, times one 40-scanline band. Shared by rm_init_leg's phase 7 (frame 0) and mode 2. */
uint16_t rm_screen_offset(const uint8_t *buf_a, uint16_t leg, uint16_t scroll_frame);

/* The mode-2/4/6 event: fire the effect the pulled record selects. Mutates the EventState scalars in
 * `c->ev` plus *obj_shade / *screen_offset / `race_pal` per the mode, and reports the shell's palette
 * write in *out. Runs after rm_build_road_geometry and before rm_course_events, only on a record pull. */
void rm_course_mode_event(RmEventCtx *c, int16_t *obj_shade, uint16_t *screen_offset,
                          uint8_t *race_pal, RmPaletteWrite *out);

/* ---- crash / end-of-race tally (HUD phase 8 timer + draw_crash_fx's STATE side @0x15872) ----
 *
 * The persistent counterpart to hud.c's hud_crash_fx DRAW. draw_hud phase 8 decays hud_crash_timer by
 * RM_HUD_CRASH_DECAY per frame; once it goes negative draw_crash_fx runs the leg-end tally: drain the
 * bonus time / units / score-digit rollovers into the score one unit per frame, then arm abort_flag —
 * 0xffff at once when there was no crash to tally (game over), else 0x33 when the bonus is exhausted.
 * hud.c's hud_crash_fx renders the same tally each frame off a throwaway HUD-text copy (const state);
 * THIS function owns the mutations (hud_crash_timer, EventState.crash_frame/crash_lap/abort_flag,
 * PlayerState.time_left, the rollover records + score in hud_text) so a self-running leg advances.
 * Runs after the course tail on the caller's frame, as draw_hud phase 8 runs after game_update.
 *
 * Slice 2 WIRES the crash-drain sound: each drained unit fires stop_music_chk(crash) through the ctx's
 * SoundDriver (recreate draw_crash_fx @0x15914), Dosound-ledgered like the rest. */
#define RM_HUD_CRASH_DECAY 2        /* hud_crash_timer step per frame while positive */
#define RM_ABORT_GAME_OVER 0xffff   /* abort_flag armed at once when crash_active == 0 */
#define RM_ABORT_BONUS_DONE 0x33    /* ...when the bonus tally is exhausted instead */

/* Shared crash-tally layout — the DRAW (hud.c hud_crash_fx) and this UPDATE both walk the same
 * one-unit-per-frame rollover (rm_crash_rollover_step) and index the same HUD lap digit, so the shared
 * layout is defined once here. All offsets are relative to the HUD-text base (0x18172). */
#define RM_CRASH_FRAME_MIN      0xa    /* the tally body runs once crash_frame reaches this */
#define RM_CRASH_ROLLOVER_OFF   0x1c   /* score-digit rollover records (0x1818e), stride below */
#define RM_CRASH_ROLL_STRIDE    0xe
#define RM_CRASH_ROLL_TARGET    0x60   /* a record is done when 0x60 - digit[-1] - digit == 0 */
#define RM_CRASH_ROLL_HI        0x35   /* the tens digit that resets instead of carrying */
#define RM_CRASH_ROLL_STEP      5      /* the ones digit steps by this per drained rollover unit */
#define RM_CRASH_HUD_LAP_OFF    0x68   /* HUD lap digit (0x181da) = '0' + crash_lap */
void rm_crash_fx_update(RmEventCtx *c);

/* Test seam: classify event `idx` as a packed (kind<<24 | gate<<16 | arg) word, so a test can pin the
 * native jump table against the image's own table at 0x11aa2 (see test_events). */
uint32_t rm_event_classify(uint16_t idx);
#define RM_EVENT_TABLE_ENTRIES 65

/* ---- init_leg (recreate gameplay.c g_init_leg @0x104b8) — the leg-start state reset ----
 *
 * A leg STARTS natively rather than from a baked snapshot: this resets every per-leg surface to its
 * leg-start value in one call — the physics/course/event/pose/scroll scalars (recreate's 0x6d-word
 * live-state clear plus a handful of scalar defaults), the course object/marker ring seeded from the
 * leg's packed marker records, the buggy-sprite pose, the HUD bonus-time / score strings, and the
 * scaled-object shade + the road-scroll offset. It owns the OWNER structs (Player/Course/Pose/Scroll/
 * Ring/Event/GobjPrefix/Sprite); the render VIEWS the demo derives per frame (Ground / ObjList / Hud)
 * follow from them via the normal apply_player / ring_views_refresh, so they are not taken here.
 *
 * Homed with the draw_game_objects prefix in gameplay.c because that is where recreate keeps
 * g_init_leg — both are gameplay-orchestrator code (per-leg init + per-frame object state), not a
 * render leaf. It reproduces g_init_leg's eleven phases with two documented exceptions, neither a
 * surface any consumer or the differential test reads:
 *   - Phase 3's checkpoint-banner draw (draw_checkpoint_anim) writes only the gfx banner bitmap, which
 *     rm_course_events regenerates on a checkpoint; the demo's golden renders from the freshly-loaded
 *     arena (no init-time banner scroll), so it is skipped here.
 *   - Phase 11 stages the object-display / palette record into `race_pal` (the same 0x17fac.. record
 *     mode 4 re-stages — an off-image Setpalette seam) AND derives obj_shade from it. Fully ported.
 *
 * The dash-marker scalars are NOT touched: verified against the oracle, g_init_leg leaves them
 * unchanged (0 at a leg start) — the per-leg arena reseed is the intermission's init_leg_dash (already
 * ported in events.c), which fires on a checkpoint, not here. */
typedef struct {
    const uint8_t *buf_a;    /* assets arena (COURSES.DAT): the leg's marker records (INIT_MARKER_SRC_BASE),
                              * the object-display selector/record (0x50 / 0xf2) and the per-leg scroll
                              * table (leg << 4) — all byte offsets into the loaded arena base */
    const uint8_t *legtime;  /* program-data bonus-time strings ("/2000/" ...) source (image 0x18136) */
} RmInitAssets;

/* Reset all per-leg state to its leg-start value (see above). `obj_shade` (draw_object's centre/near
 * fill selector), `screen_offset` (buf_c road-scroll offset, feeds the scroll prebuild) and `race_pal`
 * (the mutable in-race palette phase 11 stages into, RM_RACE_PAL_BYTES) are the three outputs with no
 * owning struct field. `hud_text` is the shared mutable HUD-text region (base 0x18172). */
void rm_init_leg(PlayerState *p, CourseState *cs, RoadPose *pose, ScrollState *scroll,
                 CourseRing *ring, EventState *ev, GobjPrefixState *gobj, SpriteState *sprite,
                 uint8_t *hud_text, int16_t *obj_shade, uint16_t *screen_offset, uint8_t *race_pal,
                 const RmInitAssets *a, uint16_t leg);

/* Fan the per-frame driving-model outputs (PlayerState + the event-owned EventState) out to the render
 * VIEW structs, deriving exactly what the draws read. `road_edge_base` = the edge table biased by
 * ROAD_EDGE_PAD (the shell's fixture pointer). Pure derivation; no I/O (see gameplay.c). */
void rm_apply_player(const PlayerState *p, const EventState *ev,
                     RoadPose *pose, ScrollState *scroll, SpriteState *sprite,
                     GroundState *ground, ObjListCtx *objlist, HudState *hud,
                     RoadInput *road, const uint8_t *road_edge_base);

#endif /* RM_GAME_H */
