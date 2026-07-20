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

/* ---- HUD (draw_hud, phases 4/5/6a ported so far) ---- */

/* Dynamic per-frame HUD inputs (recreate's scalar globals, named). See src/hud.c. */
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

/* Fine-scroll the double-wide road playfield onto the screen's road band (rows 0..103): advance the
 * scroll position, blit ROAD_ROWS scanlines of rotated 4-plane columns from `playfield` (which points
 * at buf_c + screen_offset), then fill the area above the band. Updates the scroll state. */
void rm_blit_road_scroll(ScrollState *s, const uint8_t *playfield, Framebuffer *fb);

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

#endif /* RM_GAME_H */
