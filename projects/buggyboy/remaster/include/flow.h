/* flow.h — the between-legs flow's draw surfaces (recreate's intermission.c / results.c cores).
 *
 * Slice A of the between-legs flow: the four draw functions that paint the intermission and results
 * screens, ported onto remaster's native models. The FLOW that sequences them (the attract loop's
 * phases A-D) is slice B; these are the host-verified drawing cores it will call.
 *
 *   rm_intermission_poll  a 9-entry table-driven block copy from buf_c into the draw buffer
 *   rm_draw_intermission  the scrolling hi-score / leg-time / credits screen
 *   rm_draw_leg_results   the per-leg results screen (result panels, labels, digits, dashboard)
 *   rm_fade_step          one between-legs backdrop frame: fill + poll + header + intermission
 *
 * They reuse the shared primitives: rm_glyph_run / rm_num_run (text.h) for the paired-glyph text and
 * digit-sprite runs, cell_transp (plane.h) for the masked result blit, and the rm_fill_* family
 * (fill.h) for the background fills. Asset tables come from the arena (buf_c graphics, buf_a strings)
 * or program-data / persistent-state windows, following the established adapter split.
 */
#ifndef RM_FLOW_H
#define RM_FLOW_H

#include <stdbool.h>
#include <stdint.h>
#include "screen.h"

/* The intermission screen's assets (draw_intermission + fade_step + the poll leaf).
 *
 * `highscore` is the between-legs mutable game state — update_highscore writes it, so it is modelled
 * as a persistent buffer (like hud_text), seeded from init_scoretable's default table; the flow slice
 * owns its updates. Everything else is const: arena graphics (poll_src / num_sprites from buf_c),
 * buf_a strings (leg_names), and program-data layout tables / strings (sec1_tbl / sec3_tbl / credits /
 * header_str / poll_blits / num_glyph_tbl / font / color_pairs). */
typedef struct {
    const uint8_t *color_pairs;    /* 16 colours x 8-byte fill (text tint + fade backdrop) */
    const uint8_t *font;           /* 1bpp glyph table (16 bytes/char) */
    const uint8_t *num_sprites;    /* pre-rendered digit/letter sprites (buf_c + 0xbb80) */
    const uint8_t *num_glyph_tbl;  /* per-char word byte-offset into num_sprites */
    const uint8_t *poll_src;       /* block-copy source (buf_c + 0x32c80) */
    const uint8_t *poll_blits;     /* 9 x {src_off:w, dst_off:w, dims:w} control table (program data) */
    const uint8_t *header_str;     /* fade_step copyright header string (program data) */
    const uint8_t *sec1_tbl;       /* section-1 layout: 15 x {base,dst_add,max_rows,colour,str_off} */
    const uint8_t *sec3_tbl;       /* section-3 layout: 3 x the same 5-word entry */
    const uint8_t *credits;        /* section-3 credit strings (program data) */
    const uint8_t *leg_names;      /* section-2 scrolling leg-name sprites (buf_a + 0x884) */
    const uint8_t *highscore;      /* persistent hi-score table (section-1 strings) */
} RmIntermissionAssets;

/* The per-leg results screen's assets. `gfx` is the buf_c base (result panels + dashboard index it by
 * absolute offset); `leg_palette` points AT the per-row colour byte for leg 0 and is indexed [i - leg]
 * (recreate's `suba.w leg` cursor); the rest are buf_a strings and program-data. */
typedef struct {
    const uint8_t *color_pairs;
    const uint8_t *font;
    const uint8_t *num_sprites;
    const uint8_t *num_glyph_tbl;
    const uint8_t *gfx;            /* buf_c base; result/dashboard src offsets are absolute into it */
    const uint8_t *title;          /* row-1 concatenated label strings (program data) */
    const uint8_t *leg_palette;    /* per-row colour bytes, indexed [i - leg] (cursor at leg 0) */
    const uint8_t *row_names;      /* row-2 per-leg label strings (buf_a + 0x848) */
    const uint8_t *leg_digits;     /* leg time/score digit string (buf_a + 0x884) */
} RmResultsAssets;

/* 9-entry table-driven block copy from `src` (buf_c + 0x32c80) into fb at +0x990. */
void rm_intermission_poll(Framebuffer *fb, const uint8_t *src, const uint8_t *blits);

/* The scrolling hi-score / leg-time / credits screen at vertical scroll `int_scroll`. */
void rm_draw_intermission(Framebuffer *fb, const RmIntermissionAssets *a, int16_t int_scroll);

/* One between-legs backdrop frame: fill(6) + poll + header + draw_intermission. */
void rm_fade_step(Framebuffer *fb, const RmIntermissionAssets *a, int16_t int_scroll);

/* The per-leg results screen for leg `leg` (0-4). */
void rm_draw_leg_results(Framebuffer *fb, const RmResultsAssets *a, uint16_t leg);

/* ---- the between-legs FLOW state machine (slice B) ----------------------------------------------
 *
 * The host-side attract / leg-select flow that SEQUENCES the slice-A draw surfaces around the race
 * pipeline (recreate's intermission @0x127a0 + init_playfield @0x12af6 + check_abort @0x128ea +
 * update_highscore @0x1238e). The flow's own counters — the attract timers/scroll/dwell, the leg
 * selector, the idle countdown, the leg-select auto-repeat delays, and the game-over flag the main
 * loop bumps around an intermission — become native state in FlowState (the composition owns it, as
 * `_Candidate` owns the leg-drive structs). The slice-A draws, rm_init_leg, the race pipeline
 * (equiv's frame machinery) and the event engine are COMPOSED by the host driver — the phase-step and
 * leaf functions below are the pieces the driver calls, each differential against recreate's g_*.
 *
 * OFF-IMAGE SEAMS, per convention (documented at each call site in the host composition, not modeled
 * here): the Vsync/flip pacing, xbios_setpalette (no image effect — the byte-compare is palette-
 * agnostic), the IKBD joystick poll (its reply arrives by an interrupt the oracle does not run, so
 * input_state/input_prev are scripted state), and the play_event_tune/EGOFF sound. */
typedef struct {
    /* attract-loop counters (intermission phases A/C/D). */
    int16_t  int_timer;        /* free-running Phase-A timer; gates the scroll advance */
    int16_t  int_scroll;       /* vertical scroll draw_intermission consumes */
    int16_t  int_frame;        /* Phase-A scroll dwell / Phase-C demo-frame counter */
    int16_t  int_frame_hi;     /* Phase-D per-leg dwell counter */
    uint16_t leg_select;       /* attract leg selector (0-4); copied into leg_index each cycle */
    uint16_t leg_index;        /* current leg (0-4). Cross-cutting, but the flow OWNS its mutation
                                * during phases B/D and the leg-select nav (below) */
    /* leg-select (init_playfield). */
    uint16_t idle_countdown;   /* attract idle timer; reloaded on input change, expiry -> intermission */
    int16_t  leg_dec_delay;    /* auto-repeat delay: step to the previous leg (up/left) */
    int16_t  leg_inc_delay;    /* auto-repeat delay: step to the next leg (down/right) */
    uint16_t game_over_flag;   /* main bumps it around an intermission (++ before, reset after) */
    /* per-frame input the flow's abort / nav read (the host scripts them; the IKBD poll is a seam). */
    uint16_t input_state;      /* this frame's joystick/key bits */
    uint16_t input_prev;       /* the baseline snapshot the abort / fire edge compares against */
    /* update_highscore outputs (the results-screen layout + the deferred name-entry tail's seed). */
    uint16_t results_mode;     /* 0 = the score made the table (name entry), 2 = missed */
    uint16_t hiscore_pos;      /* 1-based rank the new score reached (0 = none) */
    uint16_t countdown_timer;  /* name-entry "TIME nn" countdown seed (deferred tail input) */
    uint16_t countdown_sub;    /* its per-frame sub-divider */
} FlowState;

/* check_abort return codes / phase-step return codes (mirror recreate's src/intermission.c). */
#define RM_ABORT_CODE   0x0d       /* rm_check_abort: a fresh input aborts the attract wait */
#define RM_INT_A_CONTINUE 0        /* Phase-A: drew this frame, keep scrolling */
#define RM_INT_A_ABORT    1        /* Phase-A: check_abort fired -> intermission returns */
#define RM_INT_A_BREAK    2        /* Phase-A: dwell exhausted -> advance to Phase B (before any draw) */
#define RM_INT_D_DRAW    0         /* Phase-D: dwell not elapsed, draw this leg's results frame */
#define RM_INT_D_ADVANCE 1         /* Phase-D: dwell elapsed, next leg (host runs init_leg_dash), draw */
#define RM_INT_D_RESTART 2         /* Phase-D: legs exhausted -> restart the whole cycle */

/* Attract-loop composition constants (intermission's prologue @0x27a0 + the Phase-C demo length). The
 * host driver seeds the Phase-A counters from these and counts Phase C's demo frames; the phase-step
 * functions below do not read them, but the driver and the differential mirror (test_flow_machine)
 * pin against them so the 0x96 boundary and the seeds live in exactly one place. */
#define INT_SCROLL_INIT 0x63       /* int_scroll seed */
#define INT_TIMER_INIT  0x3b       /* int_timer seed */
#define INT_FRAME_INIT  0x14       /* int_frame seed (Phase-A scroll dwell) */
#define INT_C_FRAMES    0x96       /* Phase-C demo runs this many frames before advancing to Phase D */

/* check_abort @0x128ea — abort (RM_ABORT_CODE) when the live input low byte is present AND differs
 * from the baseline; else 0 (the non-blocking console read is a no-key seam). Pure function of the
 * two input snapshots (the IKBD poll it fronts has no image effect). */
uint32_t rm_check_abort(uint16_t input_state, uint16_t input_prev);

/* Phase-A counter tick (intermission 0x27cc): advance the free-running timer, step the scroll while
 * it sits in the gate window, and tick the dwell down on a scroll underflow. Returns RM_INT_A_BREAK
 * (dwell exhausted, BEFORE any draw), else the check_abort verdict over fs->input_* (RM_INT_A_ABORT /
 * RM_INT_A_CONTINUE). The draw + flip are the host composition's seam, done when not BREAK. */
int rm_int_stepA(FlowState *fs);

/* Phase-B leg pick (0x27fe): advance leg_select (wrap at 5) and copy it into leg_index. */
void rm_int_phaseB_leg(FlowState *fs);

/* Phase-D counter slice (0x28b0): tick the per-leg dwell; when it elapses, advance to the next leg
 * (RM_INT_D_ADVANCE — the host rebuilds the dashboard via init_leg_dash) or restart the cycle
 * (RM_INT_D_RESTART) once every leg has shown; else RM_INT_D_DRAW. */
int rm_int_stepD_counter(FlowState *fs);

/* update_highscore @0x1238e (verified to recreate's CHECKPOINT — the deterministic prefix). Blank a
 * leading zero of the 12-byte score record, rank it byte-wise into leg `fs->leg_index`'s rows of
 * `highscore`, and on a hit shift the lower rows down and insert. Writes fs->results_mode /
 * hiscore_pos / countdown_timer / countdown_sub. `highscore` is the persistent 0x280 table (the flow
 * owns updates); `score` is the 12-byte record (the shared HUD-text region's score digits + name).
 *
 * DEFERRED, exactly as recreate defers it: the interactive IKBD-driven name-entry tail (the initials
 * screen) after this prefix — it busy-polls the keyboard and waits on the sound flag, so it never
 * runs to completion under the differential oracle. EGOFF (sound) is the usual off-image seam. */
void rm_update_highscore(FlowState *fs, uint8_t *highscore, uint8_t *score);

/* Leg-select navigation (init_playfield 0x2c00 tail): reload the idle countdown on an input change,
 * then step leg_index by the held direction, each gated by its auto-repeat delay. The IKBD poll it
 * fronts is a seam (input_state is scripted). */
void rm_init_playfield_nav(FlowState *fs);

/* Fire edge (0x2c6c): start the leg only on a FRESH fire press (clear last frame, set this frame). */
bool rm_init_playfield_fire(const FlowState *fs);

/* Game-over sequencing around an intermission (main @0x10100:312-317): bump game_over_flag before the
 * intermission (enter) and reset it after (exit). The flow owns the counter; the host driver calls
 * these where main did the ++ / = 0. */
void rm_flow_game_over_enter(FlowState *fs);
void rm_flow_game_over_exit(FlowState *fs);

#endif /* RM_FLOW_H */
