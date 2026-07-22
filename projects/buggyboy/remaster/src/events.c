/* events.c — remaster of the BuggyBoy course-event engine: game_update's §12 tail (the fx block,
 * the horizon-event dispatch, the checkpoint/collision/score markers) plus the event jump-table
 * dispatcher every event resolves through (recreate's game_update.c gu_dispatch_event + its handler
 * bodies, events.c's flag-gate family, results.c's probe_collision / leg-dash, sprite.c's checkpoint
 * banner, and score.c's add_score).
 *
 * This is the system that DECIDES to crash you and ends a leg. It reads the near course bands (the
 * live CourseRing), the horizon the geometry builder produced, and the record's event byte; it arms
 * the crash script's PlayerState fields, bumps the checkpoint/score counters, and rebuilds the
 * dashboard on a checkpoint. It writes NO framebuffer pixels — every write is off-frame game state or
 * the graphics arena (the dashboard/banner bitmaps a later draw consumes).
 *
 * OFF-FRAME sound is SKIPPED throughout, the established remaster convention (see
 * buggyboy-sound-architecture): every play_event_tune / handle_marker / stop_music the original fires
 * is documented at its call site and omitted. The 68000 works in 16-bit registers, so intermediates
 * wrap mod 2^16 — mirrored with explicit uint16_t/int16_t exactly as in player.c / geometry.c.
 */
#include <string.h>

#include "game.h"
#include "st.h"
#include "text.h"

/* ---- add_score (recreate score.c @0x1580a) — the shared score helper (declared in game.h) ---- */

/* Add v to the n-byte big-endian integer at p (binary carry across bytes, as 68k add.l/.w). */
static void add_be(uint8_t *p, int n, uint32_t v) {
    uint32_t acc = 0;
    for (int i = 0; i < n; i++) acc = (acc << 8) | p[i];
    acc += v;
    for (int i = n - 1; i >= 0; i--) { p[i] = (uint8_t)acc; acc >>= 8; }
}

void rm_score_add(uint8_t *score, uint8_t *score_str, const uint8_t *delta, bool game_over) {
    if (game_over) return;
    add_be(score,     4, be32(delta));          /* 68k adds the top four digits as one long */
    add_be(score + 4, 2, be16(delta + 4));      /* ...and the low two as a word */
    for (int i = RM_SCORE_DIGITS - 1; i >= 1; i--)
        if ((int8_t)('9' - score[i]) < 0) { score[i] -= 10; score[i - 1] += 1; }
    for (int i = 0; i < RM_SCORE_DIGITS; i++) score_str[4 + i] = score[i];
    for (uint8_t *q = score_str + 4; *q == '0'; q++) *q -= 1;   /* blank leading zeros ('0' -> '/') */
}

/* ---- the event jump table (65 entries at image 0x11aa2, resolved to their handler family) ---- */

typedef enum {
    EV_NOOP, EV_FLAG_GATE, EV_FLAG_GATE_FORCED, EV_SCORE, EV_CKPT, EV_MARKER_DECAY, EV_SPIN_ARM,
    EV_RPM_COLLIDE, EV_CURVE_FREEZE, EV_RPM_PENALTY, EV_COMMON_COLLIDE, EV_DISP_FINISH, EV_DISP_BONUS
} EventKind;

/* One table entry. `gate` means different things per kind: for FLAG_GATE it is the object type
 * (1..5); for SCORE/CKPT it is gu_gate's kind (1 = a&&b, 0 = always, 2 = a&&!b); for
 * DISP_FINISH/DISP_BONUS it is the OR-gate variant (0 = a||b, 1 = !a||!b, which doubles as the
 * left/right side). `arg` carries the score-delta offset (SCORE), the finish record type
 * (DISP_FINISH), or the bonus id (DISP_BONUS). */
typedef struct { uint8_t kind, gate; uint16_t arg; } EventEntry;

#define FG(type)        { EV_FLAG_GATE, (type), 0 }
#define SCORE(g, delta) { EV_SCORE, (g), (delta) }
#define CKPT(g)         { EV_CKPT, (g), 0 }
#define SIMPLE(k)       { (k), 0, 0 }
#define FINISH(g, type) { EV_DISP_FINISH, (g), (type) }
#define BONUS(g, id)    { EV_DISP_BONUS, (g), (id) }

#define GU_DISP_FINISH_A 0x90
#define GU_DISP_FINISH_B 0x1a8
#define GU_BONUS_ID_L1   0x29    /* idx 41 */
#define GU_BONUS_ID_L2   0x3f    /* idx 63 */
#define GU_BONUS_ID_R1   0x2a    /* idx 42 */
#define GU_BONUS_ID_R2   0x40    /* idx 64 */

static const EventEntry EVENT_TABLE[RM_EVENT_TABLE_ENTRIES] = {
    /* 0 */  SIMPLE(EV_NOOP),
    /* 1-5 */   FG(1), FG(2), FG(3), FG(4), FG(5),
    /* 6 */  SIMPLE(EV_FLAG_GATE_FORCED),
    /* 7-11 */  FG(1), FG(2), FG(3), FG(4), FG(5),
    /* 12 */ SIMPLE(EV_FLAG_GATE_FORCED),
    /* 13-15 */ SCORE(1, RM_EVT_SCORE_MSG), SCORE(0, RM_EVT_SCORE_MSG), SCORE(2, RM_EVT_SCORE_MSG),
    /* 16-18 */ SCORE(1, RM_EVT_SCORE_B),   SCORE(0, RM_EVT_SCORE_B),   SCORE(2, RM_EVT_SCORE_B),
    /* 19-21 */ SCORE(1, RM_EVT_SCORE_C),   SCORE(0, RM_EVT_SCORE_C),   SCORE(2, RM_EVT_SCORE_C),
    /* 22-24 */ CKPT(1), CKPT(0), CKPT(2),
    /* 25 */ SIMPLE(EV_COMMON_COLLIDE),
    /* 26 */ SIMPLE(EV_NOOP),
    /* 27 */ SIMPLE(EV_COMMON_COLLIDE),
    /* 28-29 */ SIMPLE(EV_NOOP), SIMPLE(EV_NOOP),
    /* 30 */ SIMPLE(EV_MARKER_DECAY),
    /* 31 */ SIMPLE(EV_NOOP),
    /* 32-33 */ SIMPLE(EV_SPIN_ARM), SIMPLE(EV_SPIN_ARM),
    /* 34 */ SIMPLE(EV_RPM_COLLIDE),
    /* 35-37 */ SIMPLE(EV_CURVE_FREEZE), SIMPLE(EV_CURVE_FREEZE), SIMPLE(EV_CURVE_FREEZE),
    /* 38-40 */ SIMPLE(EV_RPM_PENALTY), SIMPLE(EV_RPM_PENALTY), SIMPLE(EV_RPM_PENALTY),
    /* 41 */ BONUS(0, GU_BONUS_ID_L1),
    /* 42 */ BONUS(1, GU_BONUS_ID_R1),
    /* 43-59 */ SIMPLE(EV_COMMON_COLLIDE), SIMPLE(EV_COMMON_COLLIDE), SIMPLE(EV_COMMON_COLLIDE),
                SIMPLE(EV_COMMON_COLLIDE), SIMPLE(EV_COMMON_COLLIDE), SIMPLE(EV_COMMON_COLLIDE),
                SIMPLE(EV_COMMON_COLLIDE), SIMPLE(EV_COMMON_COLLIDE), SIMPLE(EV_COMMON_COLLIDE),
                SIMPLE(EV_COMMON_COLLIDE), SIMPLE(EV_COMMON_COLLIDE), SIMPLE(EV_COMMON_COLLIDE),
                SIMPLE(EV_COMMON_COLLIDE), SIMPLE(EV_COMMON_COLLIDE), SIMPLE(EV_COMMON_COLLIDE),
                SIMPLE(EV_COMMON_COLLIDE), SIMPLE(EV_COMMON_COLLIDE),
    /* 60 */ SIMPLE(EV_MARKER_DECAY),
    /* 61 */ FINISH(0, GU_DISP_FINISH_A),
    /* 62 */ FINISH(1, GU_DISP_FINISH_B),
    /* 63 */ BONUS(0, GU_BONUS_ID_L2),
    /* 64 */ BONUS(1, GU_BONUS_ID_R2),
};

uint32_t rm_event_classify(uint16_t idx) {
    if (idx >= RM_EVENT_TABLE_ENTRIES) return 0;
    const EventEntry *e = &EVENT_TABLE[idx];
    return ((uint32_t)e->kind << 24) | ((uint32_t)e->gate << 16) | e->arg;
}

/* ---- gate helpers ---- */

/* gu_gate: 0 = always, 1 = a && b, 2 = a && !b (the score / checkpoint groups). */
static bool gu_gate(uint8_t kind, uint16_t a, uint16_t b) {
    if (kind == 1) return b != 0 && a != 0;
    if (kind == 2) return b == 0 && a != 0;
    return true;
}

/* OR-gate: 0 = a || b, 1 = !a || !b (the finish / bonus display events). */
static bool or_gate(uint8_t kind, uint16_t a, uint16_t b) {
    return kind == 0 ? (a != 0 || b != 0) : (a == 0 || b == 0);
}

/* ---- score / checkpoint handlers ---- */

/* add_score against the shared HUD-text score digits, with the delta at `delta_off` in score_deltas. */
static void evt_add_score(RmEventCtx *c, uint16_t delta_off) {
    rm_score_add(c->hud_text + RM_HUD_SCORE_BCD_OFF, c->hud_text + RM_HUD_SCORE_STR_OFF,
                 c->assets->score_deltas + delta_off, c->game_over);
}

static void ckpt_counter(RmEventCtx *c) {   /* recreate gu_ckpt_counter (0x11d1a body) */
    c->ev->crash_lap    = (uint16_t)(c->ev->crash_lap + 1);
    c->ev->crash_active = (uint16_t)(c->ev->crash_active + 1);
    /* play_event_tune(9): off-frame sound, skipped */
}

/* ---- flag-gate family (recreate events.c) ---- */

#define FLAG_SEQ_TARGET   5
#define FLAG_BONUS_FRAMES 0x3c

static void flag_gate_advance(RmEventCtx *c, uint16_t slot, bool match) {
    GobjPrefixState *g = c->gobj;
    uint16_t delta_off = RM_EVT_SCORE_GATE;
    if (match) {
        g->flag_seq_count = (int16_t)(g->flag_seq_count + 1);
        if (g->flag_seq_count == FLAG_SEQ_TARGET) {
            g->bonus_timer = FLAG_BONUS_FRAMES;
            delta_off = RM_EVT_SCORE_BONUS;
        } else if (g->flag_seq_count > FLAG_SEQ_TARGET) {
            g->flag_seq_count = 1;                          /* wrap past the window */
        }
    }
    evt_add_score(c, delta_off);
    rm_ring_poke_byte(c->ring, RM_RING_OBJ_ACTIVE_OFF + slot, 0);   /* clear the object's active flag */
    /* play_event_tune: off-frame sound, skipped */
}

static void flag_gate(RmEventCtx *c, uint16_t slot, uint16_t obj_type) {
    GobjPrefixState *g = c->gobj;
    const uint8_t *expected = c->assets->flag_seq_table + g->flag_seq_off;
    /* the original reads an unsigned word here (recreate events.c: image[expected + seq_count],
     * seq_count = be16); flag_seq_count is the shared signed field, so index unsigned to match. */
    bool match = g->bonus_timer != 0 || expected[(uint16_t)g->flag_seq_count] == (uint8_t)obj_type;
    flag_gate_advance(c, slot, match);
}

/* ---- object / spin / collision spawns (recreate gu_dispatch_event handler bodies) ---- */

#define MARKER_DECAY_ARM 0x1a0   /* marker_decay countdown seed (0x11d3a) */
#define SPIN_SPEED_MIN   0x1e    /* speed floor to arm a spin (0x11d64) */
#define SPIN_LO          0xf     /* spin_reset value when obj_flag_b == 0 */
#define SPIN_HI          0x19    /* spin_word2 value otherwise */
#define RPM_BAND         0x70
#define RPM_DROP         0x19    /* engine_rpm penalty (0x11de2) */
#define RPM_MIN          0xf
#define SPEED_PER_RPM    3
#define SPEED_BIG        0x64    /* collision_lock 0x18 vs 8 threshold (0x11e16) */

/* Clear the spin lean-override pair (the original's clr.l over spin_reset + spin_word2). */
static void clear_spin(PlayerState *p) {
    p->spin_reset = 0;
    p->spin_word2 = 0;
}

static void marker_decay_spawn(RmEventCtx *c, uint16_t slot) {   /* idx 30/60 (0x11d3a) */
    rm_ring_poke_byte(c->ring, RM_RING_OBJ_ACTIVE_OFF + slot, 0);
    c->gobj->marker_active   = (uint16_t)(c->gobj->marker_active + 1);
    c->gobj->marker_off      = (int16_t)slot;
    c->gobj->marker_countdown = MARKER_DECAY_ARM;
    evt_add_score(c, RM_EVT_SCORE_EVT);
    /* play_event_tune(0xa): off-frame sound, skipped */
}

static void spin_arm(RmEventCtx *c, uint16_t obj_flag_b) {   /* idx 32/33 (0x11d64) */
    PlayerState *p = c->player;
    if ((int16_t)p->speed >= SPIN_SPEED_MIN && p->collision_lock == 0) {
        if (obj_flag_b == 0) p->spin_reset = SPIN_LO;
        else                 p->spin_word2 = SPIN_HI;
    }
}

static void rpm_collide(RmEventCtx *c) {   /* idx 34 (0x11d8e): collision object by rpm band */
    PlayerState *p = c->player;
    if (p->collision_lock != 0) return;
    clear_spin(p);
    p->turn_flags = 0;
    uint16_t band = (uint16_t)((p->engine_rpm & RPM_BAND) >> 3);
    p->collision_lock = be16(c->assets->evt_obj_type_tbl + band);
    p->crash_phase = 3;
    /* handle_marker(band >= 6 ? 1 : 0): off-frame sound, skipped */
}

static void curve_freeze_evt(RmEventCtx *c) {   /* idx 35-37 (0x11dcc) */
    PlayerState *p = c->player;
    if (p->collision_lock != 0) return;
    p->curve_freeze = 5;
    /* handle_marker(5): off-frame sound, skipped */
}

static void rpm_penalty(RmEventCtx *c) {   /* idx 38-40 (0x11de2): rpm penalty -> speed */
    PlayerState *p = c->player;
    if (p->collision_lock != 0) return;
    int16_t rpm = (int16_t)(p->engine_rpm - RPM_DROP);
    if (rpm < RPM_MIN) rpm = RPM_MIN;
    p->engine_rpm = (uint16_t)rpm;
    p->speed = (uint16_t)((uint16_t)(rpm - RPM_MIN) * SPEED_PER_RPM);
    /* handle_marker(6): off-frame sound, skipped */
}

static void common_collide(RmEventCtx *c) {   /* idx 25/27/43-59 (0x11e16) */
    PlayerState *p = c->player;
    if (p->collision_lock != 0) return;
    clear_spin(p);
    p->turn_flags = 0x10;
    p->collision_lock = (int16_t)p->speed >= SPEED_BIG ? 0x18 : 8;
    p->crash_phase = 2;
    /* handle_marker(3): off-frame sound, skipped */
}

/* ---- finish / bonus display records (recreate gu_disp_finish / gu_disp_bonus) ---- */

/* Opaque display-record payloads: the curve_window long is a {lo, hi} pair. */
#define GU_DISP_CW_FINISH 0x3ff6400aUL
#define GU_DISP_CW_L      0x3f2e3f42UL
#define GU_DISP_CW_R      0x40be40d2UL
#define GU_DISP_TYPE_L    0x3e8      /* type/entry default for the left / curve<0 bonus variant */
#define GU_DISP_TYPE_R    0x460      /* ...and the right / curve>=0 variant */
#define GU_CURVE_STEP_L   0x3c       /* road_curve delta, left */
#define GU_CURVE_STEP_R   0xffc4     /* road_curve delta, right (-0x3c) */
#define GU_BONUS_HI_ID    0x32       /* id >= this keeps the entry display params */
#define SPIN_FULLY_OUT    0x20       /* spin_state high byte == this: fully spun out */

static void set_curve_window(PlayerState *p, uint32_t cw) {
    p->curve_window_lo = (uint16_t)(cw >> 16);
    p->curve_window_hi = (uint16_t)cw;
}

static void disp_finish(RmEventCtx *c, uint16_t type) {   /* 0x11e6a body */
    PlayerState *p = c->player;
    clear_spin(p);
    p->collision_lock = type;
    p->crash_phase = 1;
    set_curve_window(p, GU_DISP_CW_FINISH);
    /* stop_music: off-frame sound, skipped */
}

static void disp_bonus(RmEventCtx *c, uint16_t type, uint16_t id, uint16_t curve_step) {  /* 0x11ebe */
    PlayerState *p = c->player;
    if (p->collision_lock != 0) {
        if (p->crash_phase < 0) id = 0;
        p->event_pending = id;
        return;
    }
    clear_spin(p);
    uint32_t cw = GU_DISP_CW_FINISH;
    if ((uint8_t)(c->ev->spin_state >> 8) != SPIN_FULLY_OUT) {   /* not fully spun-out: pick by curve sign */
        if (p->road_curve < 0) {
            cw = GU_DISP_CW_L;
            if ((int16_t)id < GU_BONUS_HI_ID) { type = GU_DISP_TYPE_L; curve_step = GU_CURVE_STEP_L; }
        } else {
            cw = GU_DISP_CW_R;
            if ((int16_t)id < GU_BONUS_HI_ID) { type = GU_DISP_TYPE_R; curve_step = GU_CURVE_STEP_R; }
        }
    }
    p->collision_lock = type;
    p->crash_phase = -1;
    set_curve_window(p, cw);
    p->road_curve = (int16_t)(p->road_curve + curve_step);
    c->pose->curve = p->road_curve;             /* the road rebuild reads the just-kicked curve */
    rm_build_road_geometry(c->pose, c->road_src, c->ring, c->ctrl, c->scanline);
    /* handle_marker(8): off-frame sound, skipped */
}

/* ---- dispatch ---- */

void rm_event_dispatch(RmEventCtx *c, uint16_t idx, uint16_t slot, uint16_t flag_a, uint16_t flag_b) {
    if (idx >= RM_EVENT_TABLE_ENTRIES) return;
    const EventEntry *e = &EVENT_TABLE[idx];
    switch (e->kind) {
    case EV_NOOP:              return;
    case EV_FLAG_GATE:         flag_gate(c, slot, e->gate); return;
    case EV_FLAG_GATE_FORCED:  flag_gate_advance(c, slot, true); return;   /* d7=6 variant: gate skipped */
    case EV_SCORE:             /* evt_add_score, then play_event_tune(8) — sound off-frame, skipped */
        if (gu_gate(e->gate, flag_a, flag_b)) evt_add_score(c, e->arg);
        return;
    case EV_CKPT:              if (gu_gate(e->gate, flag_a, flag_b)) ckpt_counter(c); return;
    case EV_MARKER_DECAY:      marker_decay_spawn(c, slot); return;
    case EV_SPIN_ARM:          spin_arm(c, flag_b); return;
    case EV_RPM_COLLIDE:       rpm_collide(c); return;
    case EV_CURVE_FREEZE:      curve_freeze_evt(c); return;
    case EV_RPM_PENALTY:       rpm_penalty(c); return;
    case EV_COMMON_COLLIDE:    common_collide(c); return;
    case EV_DISP_FINISH:       if (or_gate(e->gate, flag_a, flag_b)) disp_finish(c, e->arg); return;
    case EV_DISP_BONUS:
        if (or_gate(e->gate, flag_a, flag_b)) {
            if (e->gate == 0) disp_bonus(c, GU_DISP_TYPE_L, e->arg, GU_CURVE_STEP_L);
            else              disp_bonus(c, GU_DISP_TYPE_R, e->arg, GU_CURVE_STEP_R);
        }
        return;
    }
}

/* ---- collision probe (recreate results.c probe_collision @0x110a4) ---- */

#define ARENA_ROW_STRIDE   0xa0      /* one scanline in the graphics arena (== screen stride) */
#define CELL_WIDTH         8         /* bytes to the next 16-px 4-plane cell */
#define RM_DASH_SRC_OFF    0x11c20   /* dashboard graphic within the gfx arena (buf_c) */
#define RM_DASH_PROBE_ORIGIN (RM_DASH_SRC_OFF + 2)   /* dash_marker coordinates are relative to this */
#define PROBE_DIRS         8         /* neighbour cells probed */
#define PROBE_CELL_BITS    0x10      /* bits spanned per cell before y steps a row */
#define PROBE_Y_STEP       8

static void probe_collision(RmEventCtx *c) {
    uint8_t *base = c->gfx + RM_DASH_PROBE_ORIGIN;
    uint8_t  y0   = c->ev->dash_y;
    uint8_t  bit0 = c->ev->dash_bit & 0xf;
    uint16_t x0   = c->ev->dash_x;

    uint8_t *cur = base + y0 + sx16(x0);                       /* erase the marker's current dot */
    wr16(cur, (uint16_t)(be16(cur) & ~(1u << bit0)));

    const uint8_t *tbl = c->assets->probe_deltas;
    for (int dir = 0; dir < PROBE_DIRS; dir++, tbl += 4) {
        int16_t y   = (int16_t)(uint16_t)y0;
        int16_t bit = (int16_t)bit0 + (int16_t)be16(tbl);
        if (bit < 0)                     y += PROBE_Y_STEP;    /* underflowed the cell -> step down */
        else if (bit >= PROBE_CELL_BITS) y -= PROBE_Y_STEP;    /* overflowed the cell -> step up */
        bit &= 0xf;
        int16_t x = (int16_t)x0 + (int16_t)be16(tbl + 2);

        uint8_t *a = base + sx16((uint16_t)y) + sx16((uint16_t)x);
        uint16_t probe = (uint16_t)(be16(a) & be16(a + 4));
        if (probe & (1u << bit)) {                             /* neighbour on the track -> move here */
            c->ev->dash_x   = (uint16_t)x;
            c->ev->dash_bit = (uint8_t)bit;
            c->ev->dash_y   = (uint8_t)y;
            return;
        }
    }
}

#define GU_COURSE_MASK_STEP 4        /* crash_bars indexes the collision-flag long table by this */

void rm_course_probe(RmEventCtx *c) {
    const uint8_t *mask = c->assets->coll_mask + (int16_t)(c->ev->crash_bars << 2);
    uint32_t coll_mask = be32(mask);
    c->ev->course_flag_bit = (uint8_t)(c->ev->course_flag_bit + 1);
    if ((int8_t)(mask[0] - c->ev->course_flag_bit) < 0) c->ev->course_flag_bit = 0;
    if (coll_mask & (1u << (c->ev->course_flag_bit & 0x1f)))
        probe_collision(c);
}

/* ---- leg-0 dashboard rebuild (recreate results.c init_leg_dash / draw_leg_labels @0x12d38/0x12d88) */

#define DASH_MARKER_TBL    0x7f8     /* per-leg marker-seed longs at buf_a + this */
#define DASH_LEG_STRIDE    0x500     /* raw per-leg dashboard block */
#define DASH_SRC_STRIDE    0x20      /* raw source bytes per row (8 units x 4 bytes) */
#define DASH_ROWS          40
#define DASH_GROUPS        8
#define LABEL_DESC_TBL     0x8c0     /* buf_a offset of the per-leg label descriptors */
#define LABEL_DESC_STRIDE  0x10
#define LABEL_CLEAR_TBL    0x7d0     /* buf_a offset of the per-leg clear records */
#define LABEL_CLEAR_STRIDE 8
#define LABEL_CLEAR_ROWS   4

static void init_leg_dash(RmEventCtx *c) {
    uint16_t leg = c->leg;
    const uint8_t *seed = c->assets->buf_a + DASH_MARKER_TBL + leg * 4;
    c->ev->dash_y   = seed[0];
    c->ev->dash_bit = seed[1];
    c->ev->dash_x   = be16(seed + 2);

    const uint8_t *src = c->assets->dash_raw + sx16((uint16_t)(leg * DASH_LEG_STRIDE));
    uint8_t *dst = c->gfx + RM_DASH_SRC_OFF;
    for (int row = 0; row < DASH_ROWS; row++, dst += ARENA_ROW_STRIDE, src += DASH_SRC_STRIDE) {
        uint8_t *d = dst;
        const uint8_t *s = src;
        for (int unit = 0; unit < DASH_GROUPS; unit++, d += 8, s += 4) {
            uint16_t w0 = be16(s), w1 = be16(s + 2);           /* double each unit horizontally */
            wr16(d, w0); wr16(d + 2, w1); wr16(d + 4, w1); wr16(d + 6, w1);
        }
    }
}

static void draw_leg_labels(RmEventCtx *c) {
    const uint8_t *buf_a = c->assets->buf_a;
    uint16_t leg = c->leg;

    const uint8_t *desc = buf_a + LABEL_DESC_TBL + leg * LABEL_DESC_STRIDE;
    uint8_t *cell = c->gfx + RM_DASH_SRC_OFF + sx16(be16(desc));
    desc += 2;
    for (;;) {
        uint8_t char1 = *desc++;
        if (char1 == 0) break;
        uint8_t char2 = *desc++;
        const uint8_t *glyph1 = c->assets->font + char1 * GLYPH_BYTES;
        const uint8_t *glyph2 = c->assets->font + char2 * GLYPH_BYTES;
        uint8_t *p = cell;
        for (int row = 0; row < TEXT_CELL_ROWS; row++, p += ARENA_ROW_STRIDE, glyph1 += 2, glyph2 += 2) {
            uint16_t mask, ink;
            rm_glyph_pair(be16(glyph1), be16(glyph2), &mask, &ink);
            wr16(p,     (uint16_t)(be16(p)     & mask));
            wr16(p + 4, (uint16_t)(be16(p + 4) | ink));
        }
        cell += CELL_WIDTH;
    }

    const uint8_t *rec = buf_a + LABEL_CLEAR_TBL + leg * LABEL_CLEAR_STRIDE;
    uint8_t *p = c->gfx + RM_DASH_PROBE_ORIGIN + sx16(be16(rec));
    uint16_t m1 = be16(rec + 2), m2 = be16(rec + 4);
    for (int row = 0; row < LABEL_CLEAR_ROWS; row++, p += ARENA_ROW_STRIDE) {
        wr16(p,     (uint16_t)(be16(p)     & m1));
        wr16(p + 8, (uint16_t)(be16(p + 8) & m2));
    }
    probe_collision(c);
}

/* ---- checkpoint banner scroll (recreate sprite.c draw_checkpoint_anim @0x1442c) ---- */

#define CKPT_BASE_OFF   0x9c40   /* checkpoint banner region within the gfx arena */
#define CKPT_STRIDE     0x50     /* per-row src/dst step (copied longs + skip) */
#define CKPT_B1_GROUPS  7
#define CKPT_B2_GROUPS  4
#define CKPT_B3_ROWS_M1 0x1c

/* One banner-scroll block: `groups` columns, each a record {rows-1:w, src_off:w, dst_off:w}, copying
 * `longs` longwords per row over (rows+1) rows at CKPT_STRIDE. Returns the advanced control cursor. */
static const uint8_t *ckpt_anim_block(uint8_t *src_base, uint8_t *dst_base,
                                      const uint8_t *tbl, int groups, int longs) {
    for (int g = 0; g < groups; g++, tbl += 6) {
        int rows = (int16_t)be16(tbl);
        uint8_t *src = src_base + sx16(be16(tbl + 2));
        uint8_t *dst = dst_base + sx16(be16(tbl + 4));
        for (int r = 0; r <= rows; r++, src += CKPT_STRIDE, dst += CKPT_STRIDE)
            for (int l = 0; l < longs; l++) wr32(dst + l * 4, be32(src + l * 4));
    }
    return tbl;
}

static void draw_checkpoint_anim(RmEventCtx *c) {
    uint8_t *dst_base = c->gfx + CKPT_BASE_OFF;
    int16_t scroll = (int16_t)c->ev->ckpt_scroll;
    uint8_t *src_base = dst_base;
    const uint8_t *tbl = c->assets->ckpt_anim_tbl;

    src_base += scroll;                                        /* block 1: 1-longword columns */
    tbl = ckpt_anim_block(src_base, dst_base, tbl, CKPT_B1_GROUPS, 1);
    src_base += scroll;                                        /* block 2: 2-longword columns */
    tbl = ckpt_anim_block(src_base, dst_base, tbl, CKPT_B2_GROUPS, 2);
    src_base += scroll;                                        /* block 3: one 3-longword group (record
                                                                * shape differs: src at tbl+0, dst at tbl+2) */
    uint8_t *src = src_base + sx16(be16(tbl));
    uint8_t *dst = dst_base + sx16(be16(tbl + 2));
    for (int r = 0; r <= CKPT_B3_ROWS_M1; r++, src += CKPT_STRIDE, dst += CKPT_STRIDE) {
        wr32(dst, be32(src));
        wr32(dst + 4, be32(src + 4));
        wr32(dst + 8, be32(src + 8));
    }
}

/* ---- sections G / H / I (recreate game_update_fx_and_events @0x118b6) ---- */

#define FX_BLOCK_BYTES 0x30
#define FX_BLOCK_WORDS (FX_BLOCK_BYTES / 2)   /* words the spin-fx overlay scans (0x18) */
/* §H's second dispatch reads fx[horizon_row+3]; set_horizon clamps horizon_row <= RM_MAX_HORIZON_ROW
 * (geometry.c), so the deepest read is RM_MAX_HORIZON_ROW+3 == 0x2f, which must stay inside the block. */
_Static_assert(RM_MAX_HORIZON_ROW + 3 < FX_BLOCK_BYTES, "fx scratch too small for the clamped horizon");
#define EVT_CKPT       0x1a      /* event_type low byte: checkpoint reached */
#define EVT_COLLIDE    0x1d      /* ...collision marker */
#define SCORE_MAX_DIGIT '5'      /* score_str[1] == this ends the leg */
#define BONUS_ARM      0x3c      /* bonus_timer armed on a collision-marker frame */
#define CKPT_BANNER_T  0x28      /* gauge_blink (checkpoint banner timer) reload */
#define FX_RUN_3D      0x3d      /* fx[+6] / fx[+0x26] == this triggers the run fills */
#define FX_RUN_3E      0x3e

/* Rebuild the fx block from the near band (ring row 12) into `fx`, then overlay the spin fx. The
 * band's slot words map to fx words: +6 <- slot 0, +0xa..+0x22 <- slots 1..13, +0x26 <- slot 14; all
 * other words start zero. The block is read by NOTHING outside this function, so it is local scratch;
 * horizon_row is even in [0, 0x2c] (geometry.c set_horizon), so fx[horizon_row+3] <= 0x2f is in range. */
static void build_fx_block(RmEventCtx *c, uint8_t fx[FX_BLOCK_BYTES]) {
    memset(fx, 0, FX_BLOCK_BYTES);
    const CourseRow *band = &c->ring->row[12];                 /* obj_flags = ring row 12 slot words */
    wr16(fx + 6, band->slot[0]);
    for (int k = 0; k < 13; k++) wr16(fx + 0xa + k * 2, band->slot[1 + k]);
    wr16(fx + 0x26, band->slot[14]);

    c->ev->spin_state = 0;
    uint8_t buggy_gate = rm_ring_buggy_gate(c->ring);            /* obj_flags-2 (ring row 11 marker hi) */
    uint8_t fg_gate    = (uint8_t)rm_ring_fg_gate(c->ring);      /* obj_flags-1 (ring row 11 marker lo) */
    uint8_t flag_hi = (uint8_t)(buggy_gate & 0x60);
    if ((int8_t)buggy_gate >= 0 && ((fg_gate & 0xe0) != 0 || flag_hi != 0)) {
        uint8_t sel = (uint8_t)((fg_gate | (uint8_t)(flag_hi * 2)) >> 5);
        uint8_t fx_code = c->assets->fx_type_tbl[sel];
        c->ev->spin_state = (uint16_t)(fx_code << 8);
        if (fx_code != 0 && (int8_t)fx_code >= 0)
            for (int k = 0; k < FX_BLOCK_WORDS; k++)
                if (be16(fx + k * 2) == 0) fx[k * 2 + 1] = c->assets->fx_type_tbl[fx_code + k];
    }
    if (be16(fx + 6) == FX_RUN_3D)
        for (int off = 0; off <= 0x12; off += 2) wr16(fx + off, FX_RUN_3D);       /* fills +0..+0x13 */
    if (be16(fx + 0x26) == FX_RUN_3D)
        for (int off = 0x1a; off <= 0x2e; off += 2) wr16(fx + off, FX_RUN_3E);    /* fills +0x1a..+0x2f */
}

/* Section I — checkpoint / collision / score markers. Returns nothing; writes the checkpoint counters,
 * the score, the dashboard rebuild (leg 0), and the banner scroll. */
static void course_markers(RmEventCtx *c) {
    PlayerState *p = c->player;
    uint8_t *score_str = c->hud_text + RM_HUD_SCORE_STR_OFF;
    uint8_t event_code = (uint8_t)(c->ring->row[12].slot[7] & 0xff);   /* event_type low byte */

    if (event_code == EVT_CKPT) {
        /* play_event_tune(5): off-frame sound, skipped */
        uint16_t lap = c->ev->crash_lap;
        p->hud_crash_timer = 0;
        c->ev->crash_bars   = (uint16_t)(c->ev->crash_bars + 1);
        c->ev->crash_active = (uint16_t)(c->ev->crash_active + 1);
        if (score_str[1] == SCORE_MAX_DIGIT) {
            p->hud_crash_timer = 0x65;
            /* play_event_tune(1): leg complete, off-frame sound, skipped */
            return;
        }
        score_str[1] = (uint8_t)(score_str[1] + 1);
        int8_t ch = (int8_t)c->assets->score_label[7 + c->ev->crash_bars];   /* "SCORE/"[crash_bars+7] */
        ch = (int8_t)(ch + (int8_t)p->time_left);
        c->ev->gauge_blink_on = 0;
        if (lap != 0) {
            c->ev->crash_lap = 0;
            int8_t lap_doubled = (int8_t)(lap * 2);            /* doubled bonus-unit count folded into the char */
            ch = (int8_t)(lap_doubled + ch);
            c->hud_text[RM_HUD_SCORE_OVERLAY_OFF] = (uint8_t)(lap_doubled + '0');
            c->ev->gauge_blink_on = (uint16_t)((((uint16_t)(lap * 2) >> 8) << 8)
                                               | c->hud_text[RM_HUD_SCORE_OVERLAY_OFF]);
        }
        p->time_left = (int16_t)((p->time_left & 0xff00) | (uint8_t)ch);   /* time_left low byte = ckpt char */
        c->ev->gauge_blink = CKPT_BANNER_T;
        if (c->leg == 0) { init_leg_dash(c); draw_leg_labels(c); }
    } else if (event_code == EVT_COLLIDE) {
        probe_collision(c);
    }

    /* ground_scan_tbl reads: row 0 slot 6 low byte (+1) and slot 7 low byte (+3). */
    uint8_t gs1 = (uint8_t)(c->ring->row[0].slot[6] & 0xff);
    uint8_t gs3 = (uint8_t)(c->ring->row[0].slot[7] & 0xff);
    if (gs1 != EVT_COLLIDE) {
        if (gs3 == EVT_CKPT && score_str[1] != '1') {
            int16_t s = (int16_t)(c->ev->ckpt_scroll - 0x10);
            c->ev->ckpt_scroll = (uint16_t)(c->ev->ckpt_scroll + 4);
            if (s >= 0) c->ev->ckpt_scroll = 0;
            draw_checkpoint_anim(c);
        }
        evt_add_score(c, RM_EVT_SCORE_CKPT);
        return;
    }
    c->gobj->bonus_timer = BONUS_ARM;
    /* play_event_tune(6): off-frame sound, skipped */
}

void rm_course_events(RmEventCtx *c) {
    uint8_t fx[FX_BLOCK_BYTES];
    build_fx_block(c, fx);                                     /* G */
    c->player->curve_freeze = 0;

    uint16_t horizon_row = (uint16_t)c->pose->horizon_row;     /* H: two horizon-keyed dispatches */
    uint16_t horizon_frac = (uint16_t)c->pose->horizon_frac;
    uint8_t event = fx[horizon_row + 1];
    if (event != 0) rm_event_dispatch(c, event, horizon_row, horizon_frac, 0);
    event = fx[(uint16_t)(horizon_row + 2) + 1];
    if (event != 0) rm_event_dispatch(c, event, (uint16_t)(horizon_row + 2), horizon_frac, 0xff);

    course_markers(c);                                         /* I */
}
