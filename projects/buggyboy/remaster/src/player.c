/* player.c — remaster of game_update's player-physics slice (recreate's g_game_update @0x1110e,
 * sections 3, 4, 5, 7, 8, 9, 10).
 *
 * The chain that turns the joystick into everything the renderer draws:
 *   throttle -> engine rpm -> speed        (§7)  -> the speedometer + the lean-animation rate
 *   rpm      -> road-scroll rate           (§8)  -> the scroll band, and the view advance whose wrap
 *                                                   is what times the course (one segment per wrap)
 *   steering -> wheel position -> body lean and road curvature       (§5, §9)
 *   curvature vs the road's shoulder flags -> clamp, or an off-road push  (§10)
 * Plus the two HUD counters that live in the same function: the fire-triggered dashboard animation
 * (§3) and the bonus-time countdown (§4).
 *
 * See game.h for the state model and the no-crash-in-progress PRECONDITION that lets sections 1, 2
 * and 6 (sound, input polling, the crash/auto-steer script) stay out. The 68000 works in 16-bit
 * registers, so intermediates wrap mod 2^16 — mirrored with explicit uint16_t/int16_t, exactly as in
 * geometry.c. Verified frame-by-frame against recreate's g_game_update (test/test_player.py).
 */
#include "game.h"
#include "st.h"

#define IN_MASK            0xff8f  /* the input_state bits game_update keeps */

/* §3 — fire press cycles the dashboard variant, then reloads the leg's engine limits. */
#define FIRE_HOLD_FRAMES   4
#define DSP_VARIANT_STEP   8
#define DSP_VARIANT_MASK   0x38
#define LEG_FLAGS_TOGGLE   4       /* (sel + 4) & 4: alternates the two legflag records */

/* §4 — bonus-time clock. */
#define TIME_SUBDIV        0xb     /* frames per bonus-time unit */
#define TIMEOUT_ARM        0x5b    /* hud_crash_timer seed when the clock hits zero */

/* §5 — body-lean animation (the buggy's idle bounce, faster at higher rpm). */
#define LEAN_PHASE_MASK    0xf

/* §7 — engine. */
#define RPM_IDLE           0xf     /* rpm floor; speed_raw = (rpm - RPM_IDLE) * SPEED_PER_RPM */
#define RPM_BAND           0x70    /* the rpm bits that select a table band */
#define RPM_BRAKE_STEP     2
#define RPM_OVERREV_STEP   2       /* bleed-off when above the cap without throttle */
#define RPM_CLAMP_STEP     4       /* extra drag while the curve clamp is pushing back */
#define RPM_CLAMP_MIN      0x2d    /* ...only above this rpm */
#define SPEED_PER_RPM      3
#define EGF_TURBO_CAP      0x44    /* rpm_cap value that selects the turbo engine-frequency curve */
#define EGF_TURBO_MUL      9       /* turbo: ((rpm - idle) * 9) >> 1, saturating */
#define EGF_MAX            0xff
#define JITTER_MIN_EGF     100     /* engine frequency at/above which the speedometer jitters */
#define JITTER_PH_MASK     0xe

/* §8 — road scroll + view bank. view_flags counts up by 2*scroll_speed and wraps past VIEW_MAX; each
 * wrap is one course step, so the course advances at the speed you are actually travelling. */
#define SCROLL_PHASE_STEP  2
#define SCROLL_PHASE_MASK  0xe
#define VIEW_MAX           7
#define VIEW_BANK_MASK     8
#define GROUND_OFF_MUL     0xdd    /* view_flags * this = the ground/object scan column */
#define EDGE_SEL_MUL       0x60    /* (view_flags + view_bank) * this = the road edge-table bank */

/* §9 — steering. */
#define WHEEL_CENTRE       2
#define WHEEL_MAX          4
#define STEER_ROW_SHIFT    3       /* (skid + wheel_pos) << this = steer-curve table row */
#define RPM_COL_SHIFT      4       /* rpm >> this = steer-curve table column */

/* §10 — road-edge clamp and off-road push. */
#define CLAMP_WIDE         0x144   /* road_curve limit with no shoulder in sight */
#define CLAMP_NARROW       0x46    /* ...where the row's shoulder flag is set but the road is closed */
#define CLAMP_SPEED_BASE   0x5a    /* ...open shoulder: (speed >> 1) + this — faster runs wider */
#define EDGE_OPEN          0x1000  /* the shoulder at this row can be driven onto */
#define EDGE_LEFT          0x2000
#define EDGE_RIGHT         0x4000
#define OFFROAD_LIMIT      0x6a    /* |road_curve| past this and the buggy is off the road */
#define OFFROAD_PUSH_SHIFT 3       /* push = excess - (excess >> 3) */
#define OFFROAD_LEAN_LEFT  0x14    /* lean = wheel_pos + this while ploughing the left shoulder */
#define OFFROAD_LEAN_RIGHT 0xa
#define SKID_PUSH          8       /* horizontal shove back toward the road */
#define ROW_OFFSET         0xa0    /* crash_disp counts rows: push rows * this */

/* §3 — a fire press starts a 4-frame dashboard-variant animation; when it ends, the leg's engine
 * limits (rev cap + throttle step) are reloaded from the other legflag record. */
static void update_dashboard_anim(PlayerState *p, const PlayerAssets *a, uint16_t in) {
    bool animating = p->fire_hold != 0;
    if (!animating && (in & RM_IN_FIRE) && (p->input_prev & RM_IN_FIRE) == 0) {
        p->fire_hold = FIRE_HOLD_FRAMES;
        animating = true;
    }
    if (!animating) return;

    p->dsp_variant_idx = (uint16_t)((p->dsp_variant_idx + DSP_VARIANT_STEP) & DSP_VARIANT_MASK);
    p->fire_hold = (uint16_t)(p->fire_hold - 1);
    if (p->fire_hold != 0) return;

    p->leg_flags_sel = (uint16_t)((p->leg_flags_sel + LEG_FLAGS_TOGGLE) & LEG_FLAGS_TOGGLE);
    p->rpm_cap = be16(a->legflag_tbl + p->leg_flags_sel);
    p->rpm_add = be16(a->legflag_tbl + p->leg_flags_sel + 2);
}

/* §4 — the bonus-time clock: one unit per TIME_SUBDIV frames, frozen while hud_crash_timer is armed.
 * Running out arms hud_crash_timer, which §6 below turns into forced braking. */
static void update_bonus_clock(PlayerState *p) {
    if (p->hud_crash_timer != 0) return;

    bool unit_elapsed = (int16_t)(p->time_subctr - TIME_SUBDIV) >= 0;
    p->time_subctr = (uint16_t)(p->time_subctr + 1);
    if (!unit_elapsed) return;

    p->time_subctr = 0;
    p->time_left = (int16_t)(p->time_left - 1);
    if (p->time_left >= 0) return;

    p->time_left = 0;
    if (!p->timeout_gate) p->hud_crash_timer = TIMEOUT_ARM;
}

/* §5 — advance the idle-bounce animation. The table byte is the lean; a negative entry means "this
 * frame the body is lifted", which is also the frame the lower body is drawn on. */
static void update_lean_anim(PlayerState *p, const PlayerAssets *a) {
    p->lean_phase = (uint16_t)((p->lean_phase + 1) & LEAN_PHASE_MASK);
    p->buggy_draw_flag = 0;

    uint16_t idx = (uint16_t)(p->lean_phase + (p->engine_rpm & RPM_BAND));
    int8_t entry = (int8_t)a->lean_anim_tbl[idx];
    if (entry < 0) {
        p->lean = 0;
        p->buggy_draw_flag = 0xffff;
    } else {
        p->lean = (uint8_t)entry;
    }
}

/* §6 (steer-centre path only) — the effective input for the rest of the frame. Game over pins the
 * throttle on; an armed crash timer forces the brake instead. */
static uint16_t effective_input(const PlayerState *p) {
    uint16_t in = (uint16_t)(p->input & IN_MASK);
    if (p->game_over) in = RM_IN_ACCEL;
    if (p->hud_crash_timer != 0) {
        in = (uint16_t)((in & (uint16_t)~RM_IN_ACCEL) | RM_IN_BRAKE);
        if (p->hud_crash_timer < 0) in = RM_IN_BRAKE;
    }
    return in;
}

/* §7 — engine rpm and the two speeds derived from it: speed_raw (the true rate, which drives the
 * lean animation and the steering tables) and speed (speed_raw plus a jitter that makes the
 * speedometer flicker at high revs). Returns the engine frequency, which gates that jitter. */
static void update_engine(PlayerState *p, const PlayerAssets *a, uint16_t in) {
    uint16_t rpm = p->engine_rpm;
    if (in & RM_IN_ACCEL) {
        rpm = (uint16_t)(rpm + p->rpm_add);
        if ((int16_t)(p->rpm_cap - rpm) < 0) rpm = (uint16_t)(rpm - p->rpm_add);   /* rev limiter */
    } else if (in & RM_IN_BRAKE) {
        rpm = (uint16_t)(rpm - RPM_BRAKE_STEP);
    }
    if (p->curve_clamp && (int16_t)(rpm - RPM_CLAMP_MIN) >= 0) rpm = (uint16_t)(rpm - RPM_CLAMP_STEP);

    if ((int16_t)(rpm - RPM_IDLE) < 0) rpm = RPM_IDLE;
    else if ((int16_t)(p->rpm_cap - rpm) < 0) rpm = (uint16_t)(rpm - RPM_OVERREV_STEP);
    p->engine_rpm = rpm;

    uint16_t raw = (uint16_t)((rpm - RPM_IDLE) * SPEED_PER_RPM);
    p->speed_raw = raw;

    uint16_t engine_freq = raw;
    if (p->rpm_cap == EGF_TURBO_CAP) {
        engine_freq = (uint16_t)((uint16_t)((rpm - RPM_IDLE) * EGF_TURBO_MUL) >> 1);
        if ((int16_t)(engine_freq - EGF_MAX) >= 0) engine_freq = 0xffff;
    }

    p->speed = raw;
    if ((int16_t)(engine_freq - JITTER_MIN_EGF) >= 0) {
        p->speed_jitter_ph = (uint16_t)(p->speed_jitter_ph + 1);
        uint16_t jitter = be16(a->speed_jitter_tbl + (p->speed_jitter_ph & JITTER_PH_MASK));
        p->speed = (uint16_t)(jitter + raw);
    }
}

/* §8 — the road-scroll rate for this rpm, and the view advance it drives. view_flags stepping past
 * VIEW_MAX wraps the bank and raises view_wrapped: that is the frame the course advances. */
static void update_view_and_scroll(PlayerState *p, const PlayerAssets *a) {
    p->scroll_phase = (uint16_t)((p->scroll_phase + SCROLL_PHASE_STEP) & SCROLL_PHASE_MASK);
    p->scroll_speed = (int16_t)be16(a->scroll_speed_tbl + p->scroll_phase + (p->engine_rpm & RPM_BAND));

    p->view_wrapped = false;
    uint16_t view = (uint16_t)(p->scroll_speed * 2 + p->view_flags);
    if ((int16_t)view > VIEW_MAX) {
        view = 0;
        p->view_bank = (uint16_t)((p->view_bank + VIEW_BANK_MASK) & VIEW_BANK_MASK);
        p->view_wrapped = true;
    }
    p->view_flags = view;
    p->ground_view_off = (int16_t)(view * GROUND_OFF_MUL);
    p->road_edge_sel = (int16_t)((view + (p->view_bank & VIEW_BANK_MASK)) * EDGE_SEL_MUL);
}

/* §9 — wheel position (0..4, centre 2): held steering walks it to the lock, releasing walks it back.
 * The wheel then adds to the body lean and picks the row of the steer-curve table that integrates
 * into road_curve. Returns the wheel position §10 leans off. */
static uint16_t update_steering(PlayerState *p, const PlayerAssets *a, uint16_t in) {
    uint16_t wheel = p->wheel_pos;
    if (in & RM_IN_LEFT) {
        p->steer_hold = (uint16_t)(p->steer_hold + 1);
        wheel = (uint16_t)(wheel - 1);
        if ((int16_t)wheel < 0) wheel = 0;
    } else if (in & RM_IN_RIGHT) {
        p->steer_hold = (uint16_t)(p->steer_hold + 1);
        wheel = (uint16_t)(wheel + 1);
        if ((int16_t)wheel > WHEEL_MAX) wheel = WHEEL_MAX;
    } else {
        p->steer_hold = 0;
        if (wheel != WHEEL_CENTRE)
            wheel = (uint16_t)((int16_t)(wheel - WHEEL_CENTRE) < 0 ? wheel + 1 : wheel - 1);
    }
    p->wheel_pos = wheel;
    p->lean = (uint16_t)(wheel + p->lean);

    /* The steer-curve row is (last frame's off-road push + the wheel) — being shoved off the road
     * bends you differently from steering there. The index goes negative, hence the cursor-zero table. */
    int32_t row = ((int32_t)p->skid + (int32_t)wheel) << STEER_ROW_SHIFT;
    int16_t curve_delta = (int8_t)a->steer_curve_tbl[row + (p->engine_rpm >> RPM_COL_SHIFT)];
    if (p->skid == 0) curve_delta = (int16_t)(p->hscroll_step2 + curve_delta);
    p->road_curve = (int16_t)(curve_delta + p->road_curve);
    return wheel;
}

/* §10 — how far off centre the road lets you get. The control row's flags say whether each shoulder
 * is there at all and whether it is open; road_curve is clamped to that, and past OFFROAD_LIMIT on an
 * open shoulder the buggy ploughs: a horizontal shove back (skid) and a vertical displacement. */
static void update_edge_clamp(PlayerState *p, const uint8_t *ctrl, uint16_t wheel) {
    uint16_t edge = be16(ctrl + RM_CTRL_EDGE_FLAGS_OFF);
    int16_t geom_hi = (int16_t)be16(ctrl + RM_CTRL_GEOM_HI_OFF);

    int16_t clamp_right = CLAMP_WIDE, clamp_left = CLAMP_WIDE;
    if ((int16_t)edge < 0 && geom_hi < 0) {
        int16_t shoulder = (edge & EDGE_OPEN) ? (int16_t)((p->speed >> 1) + CLAMP_SPEED_BASE)
                                              : CLAMP_NARROW;
        if (edge & EDGE_RIGHT) clamp_right = shoulder;
        if (edge & EDGE_LEFT)  clamp_left = shoulder;
    }

    p->curve_clamp = false;
    if (p->road_curve < 0) {
        if (p->road_curve <= -clamp_left) { p->road_curve = (int16_t)-clamp_left; p->curve_clamp = true; }
    } else if (p->road_curve >= clamp_right) {
        p->road_curve = clamp_right;
        p->curve_clamp = true;
    }

    p->skid = 0;
    p->crash_disp = 0;
    if ((int16_t)edge >= 0) return;

    int16_t excess;
    if (p->road_curve < 0) {
        excess = (int16_t)(-OFFROAD_LIMIT - p->road_curve);
        if (!((edge & EDGE_OPEN) && (edge & EDGE_LEFT) && excess >= 0)) return;
        p->lean = (uint16_t)(wheel + OFFROAD_LEAN_LEFT);
        p->skid = SKID_PUSH;
    } else {
        excess = (int16_t)(p->road_curve - OFFROAD_LIMIT);
        if (!((edge & EDGE_OPEN) && (edge & EDGE_RIGHT) && excess >= 0)) return;
        p->lean = (uint16_t)(wheel + OFFROAD_LEAN_RIGHT);
        p->skid = -SKID_PUSH;
    }
    int16_t push = (int16_t)(excess - (excess >> OFFROAD_PUSH_SHIFT));
    p->crash_disp = (int16_t)(push * ROW_OFFSET);
    p->curve_clamp = false;                   /* ploughing is not a clamp — no engine drag from it */
}

void rm_player_update(PlayerState *p, const PlayerAssets *a, const uint8_t *ctrl) {
    update_dashboard_anim(p, a, p->game_over ? 0 : (uint16_t)(p->input & IN_MASK));
    update_bonus_clock(p);
    update_lean_anim(p, a);

    uint16_t in = effective_input(p);
    update_engine(p, a, in);
    update_view_and_scroll(p, a);
    uint16_t wheel = update_steering(p, a, in);
    update_edge_clamp(p, ctrl, wheel);
}
