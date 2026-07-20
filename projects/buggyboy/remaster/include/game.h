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

#endif /* RM_GAME_H */
