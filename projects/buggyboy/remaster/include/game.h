/* game.h — native BuggyBoy state, freed from recreate's flat image + Ghidra-offset model.
 *
 * This grows one struct at a time as each subsystem is ported (Phase A: the render inputs first;
 * Phase B: the full gameplay state). The rule is idiomatic C: named fields, native types, no
 * `image + offset` arithmetic. The test-only adapter (test/adapter.*) maps recreate's flat image
 * onto these structs so a captured snapshot can drive the remaster renderer — see README.md.
 */
#ifndef RM_GAME_H
#define RM_GAME_H

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
    int16_t game_over;         /* nonzero blanks the timer to 0 (phase 2) */
} HudState;

/* Static ST-format asset tables the HUD reads (constant data baked into STATIC.BIN, plus the
 * unpacked dashboard graphic in buf_c). The pointers reference raw big-endian bytes, read via st.h.
 * color_bar_cidx points at the cursor's zero offset; the phase-5 code indexes it with the signed
 * flag_seq_off + dsp_color_scroll deltas. */
typedef struct {
    const uint8_t *color_pairs;     /* 16 colours x 8-byte (4-plane) solid fill */
    const uint8_t *color_bar_mask;  /* phase-5 per-row {mask,ink} word stream */
    const uint8_t *color_bar_cidx;  /* phase-5 per-column colour-index byte cursor (zero offset) */
    const uint8_t *fuel_mask;       /* phase-6a two mask longs blended into the gauge mid rows */
    const uint8_t *font;            /* phase-7 1bpp glyph table (glyph N at font + N*16) */
    const uint8_t *gauge_str;       /* phase-7 concatenated gauge-cluster label/bar string */
    const uint8_t *dashboard_src;   /* phase-7 dashboard graphic (buf_c region), masked-blit source */
} HudAssets;

#endif /* RM_GAME_H */
