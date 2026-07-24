/* flow.c — the between-legs FLOW state machine (slice B), host-side.
 *
 * The attract / leg-select flow that sequences the slice-A draw surfaces (intermission.c / results.c)
 * around the race pipeline. This file is the flow's LOGIC — the phase-step counter arithmetic, the
 * abort poll, the high-score insert, and the leg-select navigation — mapped onto FlowState (flow.h).
 * The COMPOSITION that drives them (the prologue + phase A..D loop, init_playfield's outer loop, the
 * demo pipeline, the Vsync/palette/flip/sound seams) lives in the host driver, exactly as the leg
 * drive's frame loop lives in the harness rather than a core (see PORTING.md). Every function here is
 * differential-pinned against recreate's g_* export at the counter/table level.
 *
 * The 68k word ops (subq/addq + signed branch) are mirrored via int16_t arithmetic. See flow.h for
 * FlowState and the off-image seams the host owns.
 */
#include "flow.h"
#include "game.h"      /* RM_IN_* joystick bits (shared with the gameplay input path) */
#include "sound.h"     /* the between-legs jingles / EGOFF / TURNOFF (slice 2) */
#include "st.h"

/* ---- between-legs sound trigger ids (recreate highscore.c / intermission.c) ------------------- */
#define RM_TUNE_GET_READY 0    /* leg-start "get ready" (ip_start_leg @0x2c96) */
#define RM_TUNE_GAME_OVER 2    /* the miss-the-table game-over jingle (g_hiscore_gameover) */
#define RM_TUNE_RANK1     4    /* name-entry jingle for a rank-1 score */
#define RM_TUNE_OTHER     3    /* ...for ranks 2..9 */

/* ---- check_abort (input.c g_check_abort @0x128ea) ---- */
#define ABORT_INPUT_MASK 0xff      /* the input_state LOW byte the abort compares (cmp.b) */

uint32_t rm_check_abort(uint16_t input_state, uint16_t input_prev) {
    uint8_t live = (uint8_t)(input_state & ABORT_INPUT_MASK);
    uint8_t baseline = (uint8_t)(input_prev & ABORT_INPUT_MASK);
    if (live != 0 && live != baseline)
        return RM_ABORT_CODE;
    return 0;                       /* Crawio(0xff): no key pending (off-image console seam) */
}

/* ---- intermission phase steps (intermission.c) ---- */
#define INT_TIMER_WRAP  0x5c       /* Phase-A timer reloads here when it underflows */
#define INT_LEGS        5          /* legs cycled by the attract loop */
#define INT_D_DWELL     0x1a       /* Phase-D per-leg dwell (frames before advancing) */

int rm_int_stepA(FlowState *fs) {
    int16_t timer = (int16_t)(fs->int_timer - 1);
    if (timer < 0) timer = INT_TIMER_WRAP;
    fs->int_timer = timer;
    if ((int16_t)(timer - INT_SCROLL_GATE) >= 0) {
        int16_t scroll = (int16_t)(fs->int_scroll - 1);
        fs->int_scroll = scroll;
        if (scroll < 0) {
            fs->int_scroll = 0;
            int16_t dwell = (int16_t)(fs->int_frame - 1);
            fs->int_frame = dwell;
            if (dwell < 0) return RM_INT_A_BREAK;
        }
    }
    /* the draw_intermission + flip pacing is the host composition's seam. */
    return rm_check_abort(fs->input_state, fs->input_prev) != 0 ? RM_INT_A_ABORT : RM_INT_A_CONTINUE;
}

void rm_int_phaseB_leg(FlowState *fs) {
    uint16_t sel = (uint16_t)(fs->leg_select + 1);
    if ((int16_t)(sel - INT_LEGS) >= 0) sel = 0;
    fs->leg_select = sel;
    fs->leg_index = sel;
}

int rm_int_stepD_counter(FlowState *fs) {
    uint16_t dwell = (uint16_t)(fs->int_frame_hi + 1);
    fs->int_frame_hi = (int16_t)dwell;
    if ((int16_t)(dwell - INT_D_DWELL) < 0) return RM_INT_D_DRAW;
    fs->int_frame_hi = 0;
    uint16_t leg = (uint16_t)(fs->leg_index + 1);
    fs->leg_index = leg;
    if ((int16_t)(leg - INT_LEGS) < 0) return RM_INT_D_ADVANCE;   /* host runs init_leg_dash */
    fs->leg_index = 0;
    return RM_INT_D_RESTART;
}

/* ---- update_highscore (highscore.c g_update_highscore @0x1238e, verified to the prefix checkpoint) ---- */
#define HS_ROWS          9         /* rows per leg table */
/* HS_ROW (0xe, bytes/row) and HS_LEG_STRIDE (0x80, bytes/leg) live in flow.h — shared with results.c. */
#define HS_CMP_BYTES     6         /* digits compared per row (cmp.b loop) */
#define HS_RECORD_BYTES  12        /* score+name record inserted (3 longwords from score_bcd) */
#define HS_ROW_TAIL      (HS_ROW - HS_RECORD_BYTES)  /* the top 2 bytes of each row the shift skips */
#define HS_RECORD_LONGS  (HS_RECORD_BYTES / 4)       /* record moved as longwords: TAIL + LONGS*4 == ROW */
#define HS_SHIFT_SRC_OFF 0x70      /* shift walk starts one row below the last (table + 0x70/0x7e) */
#define HS_SHIFT_DST_OFF 0x7e
#define HS_COUNTDOWN_START 0x1e    /* name-entry countdown seed (30 -> "TIME 30") */
#define HS_MISS_MODE     2         /* results_mode when the score beats no row */
#define ASCII_ZERO       '0'       /* a blanked leading zero: '0' -> '/' */
#define ASCII_SLASH      '/'

/* Does the new score outrank the row at `row`? A byte-wise compare: the first byte where row < new
 * (signed cmp.b) means the new score belongs here; row > new (or all equal) means keep looking. */
static int outranks_row(const uint8_t *row, const uint8_t *score) {
    for (int i = 0; i < HS_CMP_BYTES; i++) {
        if ((int8_t)(uint8_t)(row[i] - score[i]) < 0) return 1;   /* row < new */
        if (row[i] != score[i]) return 0;                          /* row > new */
    }
    return 0;                                                      /* all equal */
}

/* Shift the rows from the insertion point down one slot (dropping the last), high address to low so
 * the overlapping copy is safe. Only the first HS_RECORD_BYTES of each 0xe-byte row move (the top 2
 * bytes stay put). `iters` = rows to move = (HS_ROWS - 1) - rank0. */
static void shift_rows_down(uint8_t *table, int iters) {
    uint32_t src = HS_SHIFT_SRC_OFF, dst = HS_SHIFT_DST_OFF;
    for (int n = 0; n < iters; n++) {
        src -= HS_ROW_TAIL; dst -= HS_ROW_TAIL;
        for (int k = 0; k < HS_RECORD_LONGS; k++) {    /* record longwords, pre-decrement both */
            src -= 4; dst -= 4;
            wr32(table + dst, be32(table + src));
        }
    }
}

void rm_update_highscore(FlowState *fs, uint8_t *highscore, uint8_t *score, SoundDriver *snd) {
    rm_egoff(&snd->state);                                 /* stop the envelope generator (recreate:56) */
    if (score[0] == ASCII_ZERO) score[0] = ASCII_SLASH;   /* blank a leading zero before ranking */

    uint8_t *table = highscore + (uint16_t)(fs->leg_index * HS_LEG_STRIDE);
    int rank0 = 0, made = 0;
    uint32_t row = 0;
    for (; rank0 < HS_ROWS; rank0++, row += HS_ROW) {
        if (outranks_row(table + row, score)) { made = 1; break; }
    }

    if (!made) {                                          /* checkpoint 0x123e6 */
        fs->results_mode = HS_MISS_MODE;
        fs->hiscore_pos = 0;
        return;
    }

    /* made the table at row `rank0` (1-based rank rank0 + 1) — checkpoint 0x12450. The interactive
     * name-entry tail that consumes hiscore_pos / countdown_* is DEFERRED (see flow.h). */
    fs->results_mode = 0;
    fs->hiscore_pos = (uint16_t)(rank0 + 1);
    fs->countdown_timer = HS_COUNTDOWN_START;
    fs->countdown_sub = 0;
    shift_rows_down(table, (HS_ROWS - 1) - rank0);        /* 0 iters when inserting at the last row */
    for (int b = 0; b < HS_RECORD_BYTES; b++) table[row + b] = score[b];
}

/* ---- name-entry per-frame pieces (highscore.c g_hiscore_countdown / g_hiscore_charstep) ---------- */
#define HS_CD_SUB_PERIOD 0x11      /* countdown_timer ticks down once every 0x11 sub-frames */
#define HS_CD_TENS_DIV   10        /* "TIME nn" = tens/units of countdown_timer */
#define HS_TIME_HI_OFF   6         /* score_line + 6 == image A_time_digit_hi (0x1825e) */
#define HS_TIME_LO_OFF   7         /* score_line + 7 == image A_time_digit_lo (0x1825f) */
#define HS_SEL_REPEAT    3         /* auto-repeat delay reload after a successful char step */
#define HS_INPUT_DEC     0x5       /* up (1) | left (4): step the char down */
#define HS_INPUT_INC     0xa       /* down (2) | right (8): step the char up */
#define HS_INPUT_FIRE    0x80
#define HS_CHAR_LO       0x41      /* 'A': stepped below this wraps to the delete sentinel */
#define HS_CHAR_WRAP     0x61      /* 'a': stepped up to here wraps back to 'A' */
#define HS_CHAR_DEL      0x60      /* '`': the delete sentinel (fire on it backs up a char) */
#define HS_CHAR_HOLD     0x5f      /* '_': placeholder left in the backed-out slot */
#define HS_INITIALS      3         /* initials entered per name (the loop counts them 3, 2, 1) */
#define HS_INPUT_ANY     0x8f      /* fire (0x80) | all four directions: the terminal release wait */

int rm_hiscore_countdown(FlowState *fs, uint8_t *score_line) {
    int16_t sub = (int16_t)fs->countdown_sub;
    fs->countdown_sub = (uint16_t)(sub + 1);
    if (sub - HS_CD_SUB_PERIOD >= 0) {                     /* sub was >= 0x11 */
        fs->countdown_sub = 0;
        int16_t timer = (int16_t)(fs->countdown_timer - 1);
        fs->countdown_timer = (uint16_t)timer;
        if (timer < 0) return 1;                           /* timed out */
    }
    int16_t timer = (int16_t)fs->countdown_timer;
    int tens = timer / HS_CD_TENS_DIV;
    score_line[HS_TIME_HI_OFF] = tens ? (uint8_t)(tens + ASCII_ZERO) : ASCII_SLASH;
    score_line[HS_TIME_LO_OFF] = (uint8_t)((timer - tens * HS_CD_TENS_DIV) + ASCII_ZERO);
    return 0;
}

void rm_hiscore_charstep(FlowState *fs, uint8_t *name_ptr) {
    uint16_t in = fs->input_state;

    int16_t dec = (int16_t)(fs->leg_dec_delay - 1);
    fs->leg_dec_delay = dec;
    if (dec < 0 && (in & HS_INPUT_DEC)) {
        uint8_t c = (uint8_t)(*name_ptr - 1);
        *name_ptr = c;
        if ((int8_t)(c - HS_CHAR_LO) < 0) *name_ptr = HS_CHAR_DEL;              /* below 'A' -> '`' */
        else { fs->leg_dec_delay = HS_SEL_REPEAT; fs->leg_inc_delay = 0; }
    }

    int16_t inc = (int16_t)(fs->leg_inc_delay - 1);
    fs->leg_inc_delay = inc;
    if (inc < 0 && (in & HS_INPUT_INC)) {
        uint8_t c = (uint8_t)(*name_ptr + 1);
        *name_ptr = c;
        if ((int8_t)(c - HS_CHAR_WRAP) < 0) { fs->leg_inc_delay = HS_SEL_REPEAT; fs->leg_dec_delay = 0; }
        else *name_ptr = HS_CHAR_LO;                                            /* reached 'a' -> 'A' */
    }
}

/* ---- init_playfield leg-select (intermission.c g_init_playfield_nav / _fire) ---- */
/* IP_IDLE_INIT (the idle_countdown reload) lives in flow.h — the tuning default shares it. */
#define IP_SEL_REPEAT    3         /* auto-repeat delay reloaded after a leg step */
#define IP_LEG_COUNT     5         /* legs 0..4 */
#define IP_DEC_BITS      (RM_IN_ACCEL | RM_IN_LEFT)   /* up | left  -> previous leg */
#define IP_INC_BITS      (RM_IN_BRAKE | RM_IN_RIGHT)  /* down | right -> next leg */

/* Tick both auto-repeat delays; when a delay expires (goes negative) and its direction is held, step
 * leg_index one slot (clamped to 0..IP_LEG_COUNT-1), reload that direction's delay and clear the
 * other. Both delays decrement every frame, so a step that clears the opposite delay lets the
 * opposite direction fire the same frame if held — mirroring the in-place 68k. */
static void ip_nav_step(FlowState *fs) {
    uint16_t input = fs->input_state;
    int16_t leg = (int16_t)fs->leg_index;

    int16_t dec_delay = (int16_t)(fs->leg_dec_delay - 1);
    fs->leg_dec_delay = dec_delay;
    if (dec_delay < 0 && (input & IP_DEC_BITS) && leg - 1 >= 0) {
        leg -= 1;
        fs->leg_dec_delay = IP_SEL_REPEAT;
        fs->leg_inc_delay = 0;
    }
    int16_t inc_delay = (int16_t)(fs->leg_inc_delay - 1);
    fs->leg_inc_delay = inc_delay;
    if (inc_delay < 0 && (input & IP_INC_BITS) && leg + 1 < IP_LEG_COUNT) {
        leg += 1;
        fs->leg_inc_delay = IP_SEL_REPEAT;
        fs->leg_dec_delay = 0;
    }
    fs->leg_index = (uint16_t)leg;
}

void rm_init_playfield_nav(FlowState *fs) {
    /* the IKBD joystick poll is a seam (input_state is scripted). */
    if (fs->input_state != fs->input_prev)
        fs->idle_countdown = IP_IDLE_INIT;
    ip_nav_step(fs);
}

bool rm_init_playfield_fire(const FlowState *fs) {
    return !(fs->input_prev & RM_IN_FIRE) && (fs->input_state & RM_IN_FIRE);
}

/* ---- game-over sequencing (main @0x10100:312-317) ---- */
/* main bumps game_over_flag before running the intermission and resets it after (update_highscore;
 * game_over_flag++; intermission; game_over_flag = 0). The flow owns the counter, so these tiny
 * functions own its two edits — the host driver calls them around the intermission it composes. */
void rm_flow_game_over_enter(FlowState *fs) { fs->game_over_flag++; }
void rm_flow_game_over_exit(FlowState *fs)  { fs->game_over_flag = 0; }

/* ---- the between-legs FLOW COMPOSITION driver (slice D) ------------------------------------------
 *
 * Hoisted from render/atari/game_main.c (intermission_cycle / run_intermission / run_leg_select /
 * main's game-over tail), it composes the rm_int_* / rm_check_abort / rm_init_playfield_* counters
 * above with the PLATFORM effects (draw / flip / palette / input / the demo-leg pipeline) it reaches
 * through the FlowOps table. Structure-for-structure with recreate's g_intermission @0x127a0 and
 * g_init_playfield @0x12af6 (intermission.c). Seams (each documented at the ops it calls): the Vsync/
 * flip pacing, the off-image palettes, the IKBD poll, and the demo-leg render (pinned by the leg
 * drives). */

/* Read this frame's input into the flow's scripted-input snapshots (flow_poll_input in the shell): the
 * baseline becomes last frame's live bits, the live bits become this frame's. rm_check_abort /
 * rm_init_playfield_fire compare the two. */
static void flow_poll(FlowState *fs, const FlowOps *ops, void *ctx) {
    fs->input_prev = fs->input_state;
    fs->input_state = ops->poll_input(ctx);
}

/* The shared abort/quit tail of Phases C and D — byte-identical but for the INT_ABORT `aux` code (1 in
 * Phase C, 2 in Phase D). Poll the quit edge, advance the scripted input, and abort on a fresh key.
 * Returns RM_FLOW_QUIT / RM_FLOW_ABORT to unwind, or RM_FLOW_CONTINUE to keep the phase loop running. */
static RmFlowResult flow_poll_abort_tail(FlowState *fs, const FlowOps *ops, void *ctx, uint16_t abort_aux) {
    if (ops->quit_requested(ctx)) return RM_FLOW_QUIT;
    flow_poll(fs, ops, ctx);
    if (rm_check_abort(fs->input_state, fs->input_prev)) {
        ops->event(ctx, RM_FLOW_EVT_INT_ABORT, fs->leg_index, abort_aux);
        return RM_FLOW_ABORT;
    }
    return RM_FLOW_CONTINUE;
}

RmFlowResult rm_flow_intermission_cycle(FlowState *fs, const FlowOps *ops, void *ctx,
                                        const FlowTuning *t) {
    /* prologue (0x27a0): seed the Phase-A counters, paint two backdrop frames, load the A palette. */
    fs->int_scroll = t->prologue_scroll;
    fs->int_frame = t->prologue_frame;
    fs->int_timer = t->prologue_timer;
    ops->event(ctx, RM_FLOW_EVT_INT_PROLOGUE, fs->leg_index, (uint16_t)fs->int_scroll);
    ops->draw_fade(ctx, fs->int_scroll);
    ops->set_palette(ctx, RM_FLOW_PAL_INT_A);
    ops->show(ctx);
    ops->draw_fade(ctx, fs->int_scroll);
    ops->show(ctx);

    /* Phase A (0x27cc): scroll the hi-score/credits screen until the dwell counter runs out. The draw
     * happens for CONTINUE and ABORT (the abort frame still draws); BREAK returns before any draw. */
    for (;;) {
        if (ops->quit_requested(ctx)) return RM_FLOW_QUIT;
        flow_poll(fs, ops, ctx);
        int a = rm_int_stepA(fs);
        if (a == RM_INT_A_BREAK) break;
        ops->draw_intermission(ctx, fs->int_scroll);
        ops->show(ctx);
        if (a == RM_INT_A_ABORT) { ops->event(ctx, RM_FLOW_EVT_INT_ABORT, fs->leg_index, 0); return RM_FLOW_ABORT; }
    }
    ops->event(ctx, RM_FLOW_EVT_INT_PHASEA_BREAK, fs->leg_index, (uint16_t)fs->int_frame);

    /* Phase B (0x27fe): pick + start the next demo leg. start_demo_leg reseeds every owner struct via
     * init_leg, rebuilds the picked leg's dashboard, settles it with a burst of game-updates, and
     * paints the first frame (the demo palette is set inside it, as recreate's Phase B does). */
    rm_int_phaseB_leg(fs);
    ops->event(ctx, RM_FLOW_EVT_INT_PHASEB, fs->leg_index, 0);
    ops->start_demo_leg(ctx, fs->leg_index);

    /* Phase C (0x285e): play the demo for t->phase_c_frames frames (full render each frame). The
     * leg-end tally may fire during the demo — it is ignored here (the attract exits on the frame count
     * or check_abort, never abort_flag), exactly as recreate's Phase C ignores it. */
    fs->int_frame_hi = 0;
    fs->int_frame = 0;
    for (;;) {
        ops->run_demo_frame(ctx);
        uint16_t f = (uint16_t)(fs->int_frame + 1);
        fs->int_frame = (int16_t)f;
        if ((int16_t)(f - t->phase_c_frames) >= 0) break;
        RmFlowResult r = flow_poll_abort_tail(fs, ops, ctx, 1);   /* aux 1 = Phase C abort */
        if (r != RM_FLOW_CONTINUE) return r;
    }
    ops->event(ctx, RM_FLOW_EVT_INT_PHASEC_DONE, fs->leg_index, t->phase_c_frames);

    /* Phase D (0x2894): results carousel — cycle draw_leg_results across the legs, INT_D_DWELL each.
     * The Phase-D palette is the leg-select palette. */
    fs->leg_index = 0;
    ops->rebuild_dash(ctx, fs->leg_index);            /* rebuild leg 0's dashboard for the first frame */
    ops->draw_results(ctx, fs->leg_index);
    ops->set_palette(ctx, RM_FLOW_PAL_LEG_SELECT);
    ops->show(ctx);
    for (;;) {
        int d = rm_int_stepD_counter(fs);
        if (d == RM_INT_D_RESTART) {
            ops->event(ctx, RM_FLOW_EVT_INT_PHASED_RESTART, fs->leg_index, 0);
            break;
        }
        if (d == RM_INT_D_ADVANCE) {
            ops->rebuild_dash(ctx, fs->leg_index);    /* rebuild the advanced leg's dashboard */
            ops->event(ctx, RM_FLOW_EVT_INT_PHASED_ADVANCE, fs->leg_index, 0);
        }
        ops->draw_results(ctx, fs->leg_index);
        ops->show(ctx);
        RmFlowResult r = flow_poll_abort_tail(fs, ops, ctx, 2);   /* aux 2 = Phase D abort */
        if (r != RM_FLOW_CONTINUE) return r;
    }
    return RM_FLOW_CONTINUE;   /* cycle done -> the caller runs another prologue */
}

RmFlowResult rm_flow_intermission(FlowState *fs, const FlowOps *ops, void *ctx, const FlowTuning *t) {
    for (;;) {
        RmFlowResult r = rm_flow_intermission_cycle(fs, ops, ctx, t);
        if (r != RM_FLOW_CONTINUE) return r;   /* RM_FLOW_ABORT or RM_FLOW_QUIT */
    }
}

RmFlowResult rm_flow_game_over(FlowState *fs, const FlowOps *ops, void *ctx, const FlowTuning *t) {
    rm_flow_game_over_enter(fs);
    RmFlowResult r = rm_flow_intermission(fs, ops, ctx, t);
    rm_flow_game_over_exit(fs);
    return r;
}

/* Fire-start "get ready" (ip_start_leg @0x2c96): announce the fire, redraw the leg-results + the
 * leg-name menu twice, add the dashboard place-name labels (for the race dashboard that follows), then
 * flash the leg_start_palette for t->flash_frames frames (a per-frame palette write + vblank wait — an
 * off-image seam). The two Vsyncs/frame and the palette animation live in the shell's flash_frame op;
 * the driver owns the frame COUNT so a wrong length / a dropped frame diverges the driver test. Shared
 * by both start paths (the F-key direct pick and the joystick fire edge), each with its own trace aux. */
static RmFlowResult flow_start_leg(FlowState *fs, const FlowOps *ops, void *ctx,
                                   const FlowTuning *t, uint16_t fire_aux, SoundDriver *snd) {
    rm_play_event_tune(snd, RM_TUNE_GET_READY, fs->game_over_flag != 0);   /* ip_start_leg @0x2c96 */
    ops->event(ctx, RM_FLOW_EVT_SELECT_FIRE, fs->leg_index, fire_aux);
    ops->rebuild_dash(ctx, fs->leg_index);
    ops->draw_results(ctx, fs->leg_index);
    ops->draw_panel5(ctx);
    ops->show(ctx);
    ops->draw_results(ctx, fs->leg_index);
    ops->draw_panel5(ctx);
    ops->show(ctx);
    ops->draw_leg_labels(ctx, fs->leg_index);
    for (uint16_t n = 0; n < t->flash_frames; n++) ops->flash_frame(ctx);
    return RM_FLOW_START;
}

RmFlowResult rm_flow_leg_select(FlowState *fs, const FlowOps *ops, void *ctx, const FlowTuning *t,
                                SoundDriver *snd) {
    ops->event(ctx, RM_FLOW_EVT_SELECT_ENTER, fs->leg_index, 0);
    for (;;) {                                    /* outer loop: redraws + idle-timeout attract cycle */
        uint16_t drawn_leg = 0xffff;              /* != any leg (0..4): forces a dash rebuild on entry */
        fs->idle_countdown = t->idle_init;
        /* Load the leg-select palette at the OUTER-loop entry (g_init_playfield @0x2af6,
         * intermission.c:498), BEFORE the F-key branch below — so an F1..F5 direct pick reaches the
         * get-ready flash under the leg-select palette, not the stale boot/Phase-D palette. The
         * original sets it once here and NOT in the inner default redraw (0x2b9e), so we don't either.
         * Off-image seam (palette only; the byte-compare is palette-agnostic). */
        ops->set_palette(ctx, RM_FLOW_PAL_LEG_SELECT);

        for (;;) {                                /* per-frame loop (0x2b1a) */
            int fk = ops->fkey_leg(ctx);
            if (fk >= 0) {                        /* F1..F5 direct pick starts that leg */
                fs->leg_index = (uint16_t)fk;
                return flow_start_leg(fs, ops, ctx, t, 1, snd);
            }
            /* Rebuild the dashboard only when the selected leg changed (as Phase D rebuilds only on an
             * advance), not every idle frame — the graphic is identical between nav steps. */
            if (fs->leg_index != drawn_leg) {
                drawn_leg = fs->leg_index;
                ops->rebuild_dash(ctx, fs->leg_index);
            }
            ops->draw_results(ctx, fs->leg_index);   /* default redraw (0x2b9e) */
            ops->draw_panel5(ctx);                   /* the 5-entry leg-name menu (0x2b9e tail) */
            ops->show(ctx);

            flow_poll(fs, ops, ctx);                 /* joystick tail (0x2c00) */
            rm_init_playfield_nav(fs);
            if (rm_init_playfield_fire(fs))
                return flow_start_leg(fs, ops, ctx, t, 0, snd);
            if (ops->quit_requested(ctx)) return RM_FLOW_QUIT;

            int16_t next = (int16_t)(fs->idle_countdown - 1);   /* dbf (0x2c78) */
            if (next < 0) break;                     /* countdown expired -> attract cycle */
            fs->idle_countdown = (uint16_t)next;
        }
        ops->event(ctx, RM_FLOW_EVT_SELECT_IDLE, fs->leg_index, 0);
        if (rm_flow_game_over(fs, ops, ctx, t) == RM_FLOW_QUIT) return RM_FLOW_QUIT;
    }
}

/* ---- the interactive high-score NAME-ENTRY tail (highscore.c @0x12412) --------------------------
 *
 * Run when a leg-end score MADE the table (results_mode == 0). The prefix (rm_update_highscore) set
 * hiscore_pos to the 1-based rank and seeded the countdown; this drives the initials screen, then the
 * shared terminal fade. Slice 2 WIRES the name-entry jingle (rank 1 -> tune 4, else 3) and the terminal
 * TURNOFF through the SoundDriver; only the tune-end / mzflag WAIT (the shell polls rm_sound_music_on)
 * and the Crawio key-drain stay slice-3 shell seams, so here they resolve to nothing and
 * control returns to the caller (which runs the intermission next). Each per-frame draw is
 * draw_results_screen; the colour-3 flash is the name_flash op (an off-image Setcolor, like the
 * get-ready flash — the driver owns its per-frame COUNT, the content is a documented seam). */
static void name_entry_prime(FlowState *fs, const FlowOps *ops, void *ctx) {
    /* draw + palette + show, then a second draw + show — priming both flip buffers (0x2450..0x2470). */
    ops->draw_results_screen(ctx, fs->results_mode, fs->hiscore_pos, fs->leg_index);
    ops->set_palette(ctx, RM_FLOW_PAL_RESULTS);
    ops->show(ctx);
    ops->draw_results_screen(ctx, fs->results_mode, fs->hiscore_pos, fs->leg_index);
    ops->show(ctx);
}

RmFlowResult rm_flow_name_entry(FlowState *fs, const FlowOps *ops, void *ctx, const FlowTuning *t,
                                uint8_t *highscore, uint8_t *score_line, SoundDriver *snd) {
    uint16_t leg = fs->leg_index;
    /* the current initial's byte inside the winning row (row + HS_NAME_FIELD_OFF). */
    uint8_t *p = highscore + (uint16_t)(leg * HS_LEG_STRIDE)
               + (uint16_t)((fs->hiscore_pos - 1) * HS_ROW) + HS_NAME_FIELD_OFF;

    /* the name-entry jingle (recreate @0x2450: tune 4 for a rank-1 score, else 3). */
    rm_play_event_tune(snd, fs->hiscore_pos == 1 ? RM_TUNE_RANK1 : RM_TUNE_OTHER,
                       fs->game_over_flag != 0);
    name_entry_prime(fs, ops, ctx);

    int chars_left = HS_INITIALS - 1;                      /* counts the HS_INITIALS down: 2 -> 1 -> 0 -> -1 */
    int timed_out = 0;
    for (;;) {                                              /* outer loop (0x2472) */
        for (;;) {                                          /* per-frame loop until a fresh fire press */
            if (rm_hiscore_countdown(fs, score_line)) { timed_out = 1; break; }
            ops->draw_results_screen(ctx, fs->results_mode, fs->hiscore_pos, leg);
            ops->name_flash(ctx);                           /* the colour-3 flash (off-image seam) */
            ops->show(ctx);
            flow_poll(fs, ops, ctx);                        /* read_joystick: advance the input snapshots */
            uint16_t in = fs->input_state, prev = fs->input_prev;
            rm_hiscore_charstep(fs, p);
            if (!(prev & HS_INPUT_FIRE) && (in & HS_INPUT_FIRE)) break;   /* fresh fire (0x2542) */
        }
        if (timed_out) break;

        if (*p == HS_CHAR_DEL) {                            /* fire on '`' -> back up a char */
            if (chars_left != HS_INITIALS - 1) {           /* not the first initial: a char can be undone */
                *(p - 1) = *p;                              /* shift '`' back */
                *p = HS_CHAR_HOLD;                          /* leave '_' */
                chars_left += 1;
                p -= 1;
            }
            continue;                                       /* re-enter the frame loop */
        }
        *(p + 1) = *p;                                      /* seed the next initial */
        chars_left -= 1;
        p += 1;
        if (chars_left == -1) { *p = 0; break; }            /* counted past the last initial (HS_INITIALS entered), 0x257a */
    }

    /* shared terminal tail (0x257c): clear the rank, redraw + fade the results screen (the double-draw IS
     * the "fade" — draw + palette + flip + draw + flip), hold it t->hold_frames Vsyncs (0x259c), then wait
     * for the input to be released (0x25ae). Only the tune-end / mzflag wait (0x25bc), TURNOFF (0x25d2)
     * and the key-drain (0x25de) are the off-image SOUND seams the game ships without. */
    fs->hiscore_pos = 0;
    name_entry_prime(fs, ops, ctx);
    for (uint16_t n = 0; n < t->hold_frames; n++) ops->hold_frame(ctx);   /* 0x259c: hold the finished table */
    do { flow_poll(fs, ops, ctx); } while (fs->input_state & HS_INPUT_ANY);  /* 0x25ae: wait for release */
    /* Wait out the tune BEFORE TURNOFF (0x25bc): spin until mzflag clears or a fresh key arrives. TURNOFF
     * (0x25d2) must follow the wait — doing it first (as an earlier port did) clears SND_MUSIC_ON, the
     * byte the wait reads, so the jingle would always be cut. The wait itself + the Crawio key-drain
     * (0x25de) are the shell's slice-3 seams (it polls rm_sound_music_on); fxflag clear (0x25d8) is wired. */
    ops->wait_music_off(ctx, true);   /* name-entry (0x25bc): a fresh input skips the jingle */
    rm_turnoff(&snd->state);
    snd->state.header[SND_FX_FLAG] = 0;
    return RM_FLOW_CONTINUE;
}

/* The "missed the table" tail (highscore.c g_hiscore_gameover @0x123e6 -> 0x240e): redraw the results
 * screen twice under the results palette, then play the game-over jingle (tune 2, slice-2-wired). The
 * mzflag WAIT + key-drain stay slice-3 shell seams. Run when results_mode == 2 (the score beat no row). */
RmFlowResult rm_flow_game_over_tail(FlowState *fs, const FlowOps *ops, void *ctx, SoundDriver *snd) {
    name_entry_prime(fs, ops, ctx);   /* same double-draw under the results palette (0x23e6..0x240e) */
    rm_play_event_tune(snd, RM_TUNE_GAME_OVER, fs->game_over_flag != 0);   /* the game-over jingle (0x2400) */
    ops->wait_music_off(ctx, false);  /* 0x2406: spin until the jingle ends — NOT skippable (game-over) */
    /* the Crawio key-drain (0x25de) stays a slice-3 shell seam; there is no TURNOFF on this path. */
    return RM_FLOW_CONTINUE;
}

/* The high-score tail dispatch (see flow.h): route the ranked score to name entry (made) or the
 * game-over redraw (missed). Hoisted from the shell so `make test` compiles + pins the branch. */
RmFlowResult rm_flow_score_tail(FlowState *fs, const FlowOps *ops, void *ctx, const FlowTuning *t,
                                uint8_t *highscore, uint8_t *score_line, SoundDriver *snd) {
    if (fs->results_mode == 0)
        return rm_flow_name_entry(fs, ops, ctx, t, highscore, score_line, snd);
    return rm_flow_game_over_tail(fs, ops, ctx, snd);
}
