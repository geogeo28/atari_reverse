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
#include "st.h"

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
#define INT_SCROLL_GATE 0x49       /* timer >= this advances the scroll one step */
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
#define HS_ROW           0xe       /* bytes per row */
#define HS_LEG_STRIDE    0x80      /* bytes per leg's table (leg_index << 7) */
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

void rm_update_highscore(FlowState *fs, uint8_t *highscore, uint8_t *score) {
    /* EGOFF (stop the envelope generator) is an off-image sound seam. */
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

/* ---- init_playfield leg-select (intermission.c g_init_playfield_nav / _fire) ---- */
#define IP_IDLE_INIT     0x15e     /* idle_countdown reload on an input change */
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
