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

/* Const source tables the builder reads (baked once; STATIC region, ST big-endian bytes). */
typedef struct {
    const int8_t  *persp_seg;    /* per-segment run lengths (0x31 signed bytes) */
    const uint8_t *width_src;    /* width source shorts, stride 0x20 (14 rows) */
    const uint8_t *width_count;  /* per-row width run counts, 4 view banks of 16 bytes */
} RoadSource;

/* Rebuild `ctrl` (RM_CTRL_BYTES, ST bytes) — the control-long table render_road consumes — and the
 * `scanline` scratch (RM_SCANLINE_BYTES), from the pose + const sources. Also writes the pose's
 * seg_head / horizon_row / horizon_frac outputs. */
void rm_build_road_geometry(RoadPose *pose, const RoadSource *src, uint8_t *ctrl, uint8_t *scanline);

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

/* ---- course advance (the road-geometry part of game_update's section 12 @0x11xxx) ---- */

/* Course-progress state: as the buggy drives forward, the road segment window (RoadPose.seg_data)
 * scrolls up one slot per step and, when row_ctr underflows, the next packed course record's slope
 * enters the window's tail — so the road's hills/curves follow the leg's authored track. This is the
 * render-affecting subset of section 12 (segments only); objects/events/collision are separate. */
typedef struct {
    uint16_t row_ctr;    /* course-record row countdown (-8 per step; < 0 pulls the next record) */
    uint16_t read_pos;   /* byte offset into the packed course stream ((+8) & 0x1ff8) */
} CourseState;

/* Advance the course one step. `stream` points at the leg's course-stream base; records lie at
 * NEGATIVE offsets (rec = stream - read_pos). Shifts pose->seg_data up one slot and refills the tail
 * (a pulled record's slope, or the previous slope), updating cs. Feed pose to rm_build_road_geometry. */
void rm_road_course_advance(RoadPose *pose, CourseState *cs, const uint8_t *stream);

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

#endif /* RM_GAME_H */
