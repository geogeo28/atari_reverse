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
#include "sound.h"   /* SoundDriver — the between-legs jingles / EGOFF / TURNOFF drive it (slice 2) */

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
    const uint8_t *panel5_str;     /* the 5-entry leg-name menu's concatenated labels (program data, 0x1803c) */
    const uint8_t *panel3_str;     /* F10 reload-prompt panel: 3 concatenated labels (program data, 0x18092) */
    const uint8_t *panel2_str;     /* F10 reload-confirmed panel: 2 concatenated labels (program data, 0x180d4) */
} RmResultsAssets;

/* The RACE-END / high-score name-entry results screen's assets (recreate's g_draw_results_screen
 * @0x1225a — distinct from draw_leg_results). `mode`/`pos`/`leg` are passed per call (they change
 * during name entry). Mutable regions: `highscore` (row 2 + where the initials are written), `hud_text`
 * (the third missed-block label at +0xc2), `score_line` (the 14-byte gap [0x18258,0x18266) holding the
 * score-line string and the "TIME nn" digits rm_hiscore_countdown writes). The palettes are cursors AT
 * their leg-0 byte, indexed [i - pos] (recreate's `suba.w pos`); the rest are const program data /
 * buf_a strings / buf_c graphics. */
typedef struct {
    const uint8_t *color_pairs;
    const uint8_t *font;
    const uint8_t *num_sprites;
    const uint8_t *num_glyph_tbl;
    const uint8_t *gfx;            /* buf_c base: the dashboard graphic */
    const uint8_t *title;          /* row-1 title + chained labels (program data, 0x184f8) */
    const uint8_t *palette_a;      /* row-1 per-row colour cursor, indexed [i - pos] (0x17ead) */
    const uint8_t *palette_b;      /* row-2 per-row colour cursor, indexed [i - pos] (0x17ebf) */
    const uint8_t *mode_str;       /* "missed the table" label block (program data, 0x18538) */
    const uint8_t *buf_a;          /* leg-time string (+0x80c) + the final label (+0x910) */
    const uint8_t *highscore;      /* persistent hi-score table: row 2 + the initials field */
    const uint8_t *hud_text;       /* the third missed-block label (hud_text + 0xc2) */
    const uint8_t *score_line;     /* the score-line string + "TIME nn" digits (image 0x18258) */
} RmResultsScreenAssets;

/* The race-end / name-entry results screen for (mode, pos, leg). */
void rm_draw_results_screen(Framebuffer *fb, const RmResultsScreenAssets *a,
                            uint16_t mode, uint16_t pos, uint16_t leg);

/* 9-entry table-driven block copy from `src` (buf_c + 0x32c80) into fb at +0x990. */
void rm_intermission_poll(Framebuffer *fb, const uint8_t *src, const uint8_t *blits);

/* The scrolling hi-score / leg-time / credits screen at vertical scroll `int_scroll`. */
void rm_draw_intermission(Framebuffer *fb, const RmIntermissionAssets *a, int16_t int_scroll);

/* One between-legs backdrop frame: fill(6) + poll + header + draw_intermission. */
void rm_fade_step(Framebuffer *fb, const RmIntermissionAssets *a, int16_t int_scroll);

/* The per-leg results screen for leg `leg` (0-4). */
void rm_draw_leg_results(Framebuffer *fb, const RmResultsAssets *a, uint16_t leg);

/* The leg-select divider: a colour-3 rectangle plus its two vertical bounding lines (recreate's
 * g_draw_divider @text.c). The building block of the leg-name menu panel below. */
void rm_draw_divider(Framebuffer *fb, const uint8_t *color_pairs);

/* The 5-entry leg-name menu drawn over the leg-select / get-ready screens (recreate's g_draw_panel5):
 * the divider then five colour-7 labels chained from one concatenated string (a->panel5_str). */
void rm_draw_panel5(Framebuffer *fb, const RmResultsAssets *a);

/* The F10 reload-menu panels (recreate's g_draw_panel3 / g_draw_panel2 @text.c): the divider then 3 / 2
 * colour-7 labels. The leg-select function-key menu's F10 branch overlays them on the leg-select screen —
 * panel3 is the "reload? " prompt, panel2 the confirmation. */
void rm_draw_panel3(Framebuffer *fb, const RmResultsAssets *a);
void rm_draw_panel2(Framebuffer *fb, const RmResultsAssets *a);

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
#define INT_SCROLL_GATE 0x49       /* Phase-A: int_timer >= this advances the scroll one step (rm_int_stepA;
                                    * the host's GAME_FLOW_FAST prologue seeds the timer against it too) */

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
 * runs to completion under the differential oracle. `snd` drives the leading EGOFF (slice 2). */
void rm_update_highscore(FlowState *fs, uint8_t *highscore, uint8_t *score, SoundDriver *snd);

/* ---- the interactive high-score NAME-ENTRY tail (recreate's highscore.c @0x12412 onward) ---------
 *
 * update_highscore stops at the ranking checkpoint (above); when the score made the table (results_mode
 * == 0) the game runs an initials-entry screen — a vblank-paced loop rendering the results + a "TIME nn"
 * countdown while the player dials in three initials, ending on the third confirm or on timeout. The two
 * deterministic per-frame pieces are pure functions over FlowState (diffed against the oracle); the loop
 * that sequences them is a FlowOps driver (below), as the attract cycle is. NAME_FIELD_OFF is the offset
 * of the 3-char initials inside the inserted table row. */
/* High-score table geometry, shared by the flow (update_highscore ranks/inserts by it, src/flow.c)
 * and the results-screen draw (indexes the leg's rows by it, src/results.c). One definition, per
 * CLAUDE.md §5 — pinned against the adapter/oracle by test_course_ring's constants test. */
#define HS_ROW        0xe          /* bytes per table row */
#define HS_LEG_STRIDE 0x80         /* bytes per leg's table (leg * 0x80 == leg << 7) */

#define HS_NAME_FIELD_OFF 8        /* the initials sit at (winning row) + 8 */

/* One name-entry frame's countdown tick (highscore.c g_hiscore_countdown @0x2472): advance the sub-frame
 * counter, drop countdown_timer every HS_CD_SUB_PERIOD frames, and render it as the two "TIME nn" digits
 * into score_line (image 0x1825e/0x1825f == score_line + 6/7). Returns 1 when the timer underflows (name
 * entry times out), else 0. */
int rm_hiscore_countdown(FlowState *fs, uint8_t *score_line);

/* One name-entry frame's character selection (highscore.c g_hiscore_charstep @0x24ea): up/left steps the
 * current initial down (wrapping 'A' -> '`'), down/right steps it up (wrapping past 'z' -> 'A'), each
 * gated by its own auto-repeat delay (leg_dec_delay / leg_inc_delay). `name_ptr` points at the current
 * initial byte inside the highscore table row. */
void rm_hiscore_charstep(FlowState *fs, uint8_t *name_ptr);

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

#define IP_IDLE_INIT 0x15e         /* idle_countdown reload (leg-select outer loop + nav input-change) */

/* ---- the between-legs FLOW COMPOSITION driver (slice D) -----------------------------------------
 *
 * The driver that SEQUENCES the slice-A/B pieces — the attract cycle (prologue + phases A/B/C/D), the
 * leg-select loop, and the game-over enter/exit bracket around an intermission — hoisted out of the
 * on-target shell (render/atari/game_main.c) so `make test` can lockstep it against recreate's
 * g_intermission / g_init_playfield the same way the individual phase steps already are. It mirrors
 * g_intermission / g_init_playfield structure-for-structure (recreate intermission.c @0x127a0 /
 * @0x12af6). The counter arithmetic is the rm_int_* / rm_check_abort / rm_init_playfield_* functions
 * above; the driver composes them and orders the PLATFORM effects through a FlowOps callback table so
 * the shell keeps only the 68000 implementations (drawing, flipping, palettes, input, the demo-leg
 * pipeline) and the host test can substitute recording stubs. */

/* Phase-transition trace tags (the FlowOps `event` hook). game_main's GAME_FLOW_TRACE logs them and
 * the host driver test records them; fixed values so the on-target trace format stays stable. The
 * LEG_START/END/HISCORE tags are emitted by the shell's own leg loop, the rest by the driver. */
enum {
    RM_FLOW_EVT_LEG_START = 1, RM_FLOW_EVT_LEG_END, RM_FLOW_EVT_HISCORE,
    RM_FLOW_EVT_INT_PROLOGUE, RM_FLOW_EVT_INT_PHASEA_BREAK, RM_FLOW_EVT_INT_PHASEB,
    RM_FLOW_EVT_INT_PHASEC_DONE, RM_FLOW_EVT_INT_PHASED_ADVANCE, RM_FLOW_EVT_INT_PHASED_RESTART,
    RM_FLOW_EVT_INT_ABORT, RM_FLOW_EVT_SELECT_ENTER, RM_FLOW_EVT_SELECT_FIRE, RM_FLOW_EVT_SELECT_IDLE
};

/* Palette selector for the FlowOps `set_palette` hook — the only two palettes the driver itself
 * orders (the race/demo palette is set by the shell's start_leg, an off-image seam). */
#define RM_FLOW_PAL_INT_A      0   /* prologue: the attract-scroll palette */
#define RM_FLOW_PAL_LEG_SELECT 1   /* Phase D + leg select (Phase-D palette == the leg-select palette) */
#define RM_FLOW_PAL_RESULTS    2   /* the race-end / name-entry results screen (A_results_screen_pal) */

/* Driver return codes (the shell maps QUIT onto its quit-key (Q) unwind). */
typedef enum {
    RM_FLOW_CONTINUE = 0,   /* intermission_cycle: run another attract cycle */
    RM_FLOW_ABORT,          /* attract aborted by a fresh input -> return to the caller */
    RM_FLOW_QUIT,           /* the quit key (Q) -> unwind all the way to the shell's exit */
    RM_FLOW_START           /* leg_select: a leg was chosen -> start the race */
} RmFlowResult;

/* IP_LEG_COUNT — the leg-select function-key range (F1..F5 -> legs 0..IP_LEG_COUNT-1). The one source
 * of truth for the shell (game_main.c read_fkey), the flow (flow.c nav clamp + fkey menu) and the RM_FKEY_*
 * debug codes below, which are laid out ABOVE the leg range so a leg pick and a debug key never collide. */
#define IP_LEG_COUNT   5

/* fkey_leg / reload_confirm return codes — the leg-select function-key menu (ip_menu @0x2b24). The
 * original reads a raw IKBD scancode; these codes abstract it so the flow never compares scancodes.
 * 0..IP_LEG_COUNT-1 select+start that leg; F6 / F10 are the two debug keys; RM_FKEY_RETURN is
 * reload_confirm's "the F10 reload was confirmed" answer (RETURN); RM_FKEY_NONE = no key. The debug codes
 * are defined RELATIVE to IP_LEG_COUNT so the coupling is structural — a leg-count change moves them too. */
#define RM_FKEY_NONE   (-1)
#define RM_FKEY_F6     IP_LEG_COUNT        /* F6: results-screen preview (ip_menu @0x2b86) */
#define RM_FKEY_F10    (IP_LEG_COUNT + 1)  /* F10: graphics / score-table reload prompt (ip_menu @0x2b36) */
/* NB: RM_FKEY_RETURN squats in the F-key code space just above F10 — any future F7..F9 code MUST stay
 * below it (or it must move) so a real F-key never reads back as "reload confirmed". */
#define RM_FKEY_RETURN (IP_LEG_COUNT + 2)  /* reload_confirm: RETURN confirmed the F10 reload (ip_menu @0x2b50) */

/* The platform effects the driver orders, as a callback table (+ a shell-owned `ctx`). Only the
 * effects the driver actually issues today — drawing into the back buffer, flipping, palettes, input,
 * and the demo-leg pipeline pieces (Phase B/C are game-pipeline work the shell owns). The host test
 * fills these with recording stubs; game_main fills them with the 68000 implementations. */
typedef struct {
    /* input (the IKBD poll is the shell's seam) */
    uint16_t (*poll_input)(void *ctx);      /* this frame's joystick/key bits */
    int      (*quit_requested)(void *ctx);  /* quit-key (Q) edge -> unwind everything */
    int      (*fkey_leg)(void *ctx);        /* leg select: an RM_FKEY_* code — F1..F5 -> 0..IP_LEG_COUNT-1,
                                             * RM_FKEY_F6 / RM_FKEY_F10 (debug keys), or RM_FKEY_NONE */
    /* draw + present (all draw into the back buffer; `show` flips it at the vblank) */
    void (*draw_fade)(void *ctx, int16_t scroll);          /* prologue backdrop (fade_step) */
    void (*draw_intermission)(void *ctx, int16_t scroll);  /* Phase-A scrolling hi-score screen */
    void (*draw_results)(void *ctx, uint16_t leg);         /* Phase-D + leg-select results screen */
    void (*draw_results_screen)(void *ctx, uint16_t mode, uint16_t pos, uint16_t leg); /* race-end / name-entry screen */
    void (*draw_panel5)(void *ctx);                        /* the 5-entry leg-name menu over the results screen */
    void (*set_palette)(void *ctx, int which);             /* RM_FLOW_PAL_* */
    void (*show)(void *ctx);                               /* flip the back buffer to the screen */
    /* demo-leg pipeline (Phase B/C — the shell's game structs; the render is a seam pinned by the leg drives) */
    void (*rebuild_dash)(void *ctx, uint16_t leg);         /* point the event ctx at `leg` + rebuild its dashboard */
    void (*draw_leg_labels)(void *ctx, uint16_t leg);      /* draw `leg`'s place-name labels onto the dashboard graphic */
    void (*start_demo_leg)(void *ctx, uint16_t leg);       /* Phase B: (re)init + settle + paint the demo leg */
    void (*run_demo_frame)(void *ctx);                     /* Phase C: one demo game-update + render + show */
    /* leg-start "get ready" flash (init_playfield's ip_start_leg @0x2c96): one frame of the 121-frame
     * leg_start_palette animation (a palette write + a vblank wait — an off-image seam; see game_main.c). */
    void (*flash_frame)(void *ctx);
    /* name-entry colour-3 flash (highscore.c g_hiscore_name_entry: one per initials-screen frame): read
     * A_name_anim_tbl[(anim_counter & 0xe)] into palette register 3 and load it. Off-image (Setcolor + a
     * shared anim_counter bump), like flash_frame; the driver owns the per-frame COUNT. */
    void (*name_flash)(void *ctx);
    /* name-entry terminal HOLD (highscore.c g_hiscore_name_entry @0x259c: one of the 121 Vsyncs that hold
     * the finished table on screen before returning). A plain vblank wait — NO draw, NO flip (the held
     * table already sits on the front buffer) — so it is an off-image seam like flash_frame; the driver
     * owns the COUNT (t->hold_frames). */
    void (*hold_frame)(void *ctx);
    /* name-entry / game-over terminal "wait for the jingle to end" (highscore.c @0x25bc / @0x2406): spin
     * until the tune finishes (SoundState mzflag clears), one vblank per poll. Called BEFORE the terminal
     * TURNOFF so mzflag is still readable — TURNOFF would clear it, making the wait unimplementable.
     * `skippable` carries the two call sites' semantic difference: the name-entry wait (@0x25bc) breaks
     * early on a fresh input (skippable = true); the game-over wait (@0x2406) never does (skippable =
     * false — the original never cuts the game-over jingle). The shell implements it as a Vsync +
     * rm_sound_music_on spin (game_main.c), the VBL pump advancing the tune; the host driver records it. */
    void (*wait_music_off)(void *ctx, bool skippable);
    /* leg-select function-key menu debug keys (ip_menu @0x2b24). The F6 preview and F10 reload are only
     * reachable from a real keyboard (fkey_leg is a no-key seam under the oracle), so these are shell
     * effects the driver merely orders — the host test records them. */
    void (*draw_panel3)(void *ctx);   /* F10 reload prompt overlay (draw_panel3 @0x2b3e) */
    void (*draw_panel2)(void *ctx);   /* F10 reload-confirmed overlay (draw_panel2 @0x2b58/0x2b62) */
    void (*preview_wait)(void *ctx);  /* F6: wait for F6-release then a fresh key (0x2bc4/0x2bd8) — the busy-wait
                                       * the flow delegates so it never blocks a scripted host test */
    int  (*reload_confirm)(void *ctx);/* F10: blocking read (Crawcin @0x2b48) -> RM_FKEY_RETURN, another
                                       * F-key code, or RM_FKEY_NONE */
    void (*reload_assets)(void *ctx); /* F10 reload (@0x2b64): re-read GRAPHICS.GRA + re-seed the score table + dash */
    /* phase-transition trace hook (RM_FLOW_EVT_*) */
    void (*event)(void *ctx, uint16_t tag, uint16_t leg, uint16_t aux);
} FlowOps;

/* Composition tuning — the debug GAME_FLOW_FAST knobs promoted to data, so the shell (fast build) and
 * the host driver test can both shorten the otherwise thousands-of-frames attract phases. The default
 * is the real attract timing (g_intermission's prologue seeds + Phase-C length + the leg-select idle). */
typedef struct {
    int16_t  prologue_scroll;   /* Phase-A int_scroll seed */
    int16_t  prologue_frame;    /* Phase-A int_frame (scroll-dwell) seed */
    int16_t  prologue_timer;    /* Phase-A int_timer seed */
    uint16_t phase_c_frames;    /* Phase-C demo length (frames before advancing to Phase D) */
    uint16_t idle_init;         /* leg-select idle-countdown reload (expiry -> one attract cycle) */
    uint16_t flash_frames;      /* leg-start "get ready" palette-flash length (ip_start_leg) */
    uint16_t hold_frames;       /* name-entry terminal hold length (the 121 Vsyncs at 0x259c) */
} FlowTuning;

/* The leg-start flash length. Remaster: IP_FLASH_FRAMES = 121 = the total frame COUNT, run half-open
 * (flow.c's `for (n = 0; n < flash_frames; n++)`). Recreate's same-named constant is 0x78 = 120 — a dbf
 * bound (`for (n = 0x78; n >= 0; n--)`) that iterates 0x78 + 1 = 121 times, the SAME 121 frames. So this
 * value already IS recreate's iteration count; do NOT add 1 to it. */
#define IP_FLASH_FRAMES 121

/* The name-entry terminal hold length. Recreate's TAIL_VSYNCS is 0x78 = 120, a dbf bound
 * (`for (i = 0x78; i >= 0; i--)`) that iterates 0x78 + 1 = 121 times; the remaster runs it half-open
 * (flow.c's `for (n = 0; n < hold_frames; n++)`), so this value already IS that 121-frame count — like
 * IP_FLASH_FRAMES, do NOT add 1. */
#define HS_HOLD_FRAMES 121

#define RM_FLOW_TUNING_DEFAULT { .prologue_scroll = INT_SCROLL_INIT, .prologue_frame = INT_FRAME_INIT, \
    .prologue_timer = INT_TIMER_INIT, .phase_c_frames = INT_C_FRAMES, .idle_init = IP_IDLE_INIT, \
    .flash_frames = IP_FLASH_FRAMES, .hold_frames = HS_HOLD_FRAMES }

/* One attract cycle (g_intermission's for-body): prologue -> Phase A (scroll) -> Phase B (warm the demo
 * leg) -> Phase C (play it) -> Phase D (results carousel). Returns RM_FLOW_CONTINUE (run another cycle),
 * RM_FLOW_ABORT (a fresh input aborted the attract), or RM_FLOW_QUIT (the quit key, Q). */
RmFlowResult rm_flow_intermission_cycle(FlowState *fs, const FlowOps *ops, void *ctx, const FlowTuning *t);

/* g_intermission @0x127a0: run attract cycles until an abort (or a quit). Returns RM_FLOW_ABORT / QUIT. */
RmFlowResult rm_flow_intermission(FlowState *fs, const FlowOps *ops, void *ctx, const FlowTuning *t);

/* Game-over bracket around an intermission (main @0x10100:312-317 + init_playfield's idle path): bump
 * game_over_flag, run the intermission, reset it. Returns the intermission's result (ABORT / QUIT). */
RmFlowResult rm_flow_game_over(FlowState *fs, const FlowOps *ops, void *ctx, const FlowTuning *t);

/* g_init_playfield's leg-select loop @0x12af6: show the results screen, let the player pick (nav) and
 * start (fire / F-key) a leg, and on the idle-countdown expiry run one game-over-bracketed attract cycle
 * and restart. Returns RM_FLOW_START (fs->leg_index is the chosen leg) or RM_FLOW_QUIT (the quit key, Q). */
RmFlowResult rm_flow_leg_select(FlowState *fs, const FlowOps *ops, void *ctx, const FlowTuning *t,
                                SoundDriver *snd);

/* The interactive name-entry loop, run when a leg-end score MADE the table (results_mode == 0). Draws
 * the results + a "TIME nn" countdown each frame while the player dials three initials into the winning
 * row (highscore + leg*0x80 + (pos-1)*0xe + HS_NAME_FIELD_OFF), ending on the third confirm or on
 * timeout, then clears the rank, redraws, holds the finished table t->hold_frames Vsyncs and waits for
 * the input to be released (recreate g_hiscore_name_entry @0x12412). Slice 2 wires the name-entry jingle
 * (`snd`) and the terminal TURNOFF; only the tune-end / mzflag WAIT + the key-drain stay slice-3 shell
 * seams. Returns RM_FLOW_CONTINUE (control returns to the caller, which runs the intermission next). */
RmFlowResult rm_flow_name_entry(FlowState *fs, const FlowOps *ops, void *ctx, const FlowTuning *t,
                                uint8_t *highscore, uint8_t *score_line, SoundDriver *snd);

/* The "missed the table" tail, run when the score beat no row (results_mode == 2): redraw the results
 * screen twice under the results palette (recreate g_hiscore_gameover @0x123e6 -> 0x240e), then play the
 * game-over jingle (tune 2, slice-2-wired via `snd`). The mzflag WAIT + key-drain stay shell seams.
 * Returns RM_FLOW_CONTINUE. */
RmFlowResult rm_flow_game_over_tail(FlowState *fs, const FlowOps *ops, void *ctx, SoundDriver *snd);

/* The high-score tail DISPATCH (main @0x10100: update_highscore's two exits): after ranking, a score
 * that MADE the table (results_mode == 0) runs the interactive name entry, one that MISSED (== 2) runs
 * the game-over redraw. Kept in the flow (not the shell) so `make test` compiles + pins the branch.
 * Returns whatever the chosen tail returns (RM_FLOW_CONTINUE). */
RmFlowResult rm_flow_score_tail(FlowState *fs, const FlowOps *ops, void *ctx, const FlowTuning *t,
                                uint8_t *highscore, uint8_t *score_line, SoundDriver *snd);

#endif /* RM_FLOW_H */
