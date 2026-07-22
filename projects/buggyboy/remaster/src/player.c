/* player.c — remaster of game_update's player-physics slice (recreate's g_game_update @0x1110e,
 * sections 3, 4, 5, 6, 7, 8, 9, 10).
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
 * §6 is the exception to "the player drives": while `collision_lock` is armed the crash / auto-steer
 * script has the controls and replays a canned crash out of `crash_anim_tbl`, one record per frame,
 * until a terminal record hands them back. Holding a steering lock long enough arms it too (§10).
 *
 * §6's event path is now wired in: when an event is pending it dispatches through the course-event
 * engine (rm_event_dispatch, via the RmEventCtx bundle), which is what arms the crashes the script
 * above replays. §1's marker gate (clearing the marker the crash script raised, closing the
 * raise/consume loop) and §2's input capture are modeled too; the rest of §1/§2 is off-frame sound
 * (handle_marker, the engine-sound enable block) this slice skips.
 * See game.h for the state model. The 68000 works in 16-bit registers, so intermediates wrap mod 2^16 —
 * mirrored with explicit uint16_t/int16_t, exactly as in geometry.c. Verified frame-by-frame against
 * recreate's g_game_update (test/test_player.py, test/test_leg_drive.py).
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

/* §6 — the crash / auto-steer script. One 8-byte crash_anim_tbl record is consumed per frame; the
 * cursor steps by CRASH_REC_BYTES minus the record's own step byte, so a record can hold the script
 * in place (step 8) or replay a run. A negative lean byte marks the terminal record. */
#define CRASH_REC_BYTES    8
#define CRASH_STEP         0       /* record fields, by byte offset */
#define CRASH_LEAN         1       /* body lean; < 0 = terminal, hand the controls back */
#define CRASH_PITCH        2       /* word: body pitch (the crash bounce) */
#define CRASH_RPM          4       /* rpm override; < 0 = leave the engine alone */
#define CRASH_ANIM         5       /* sprite animation frame */
#define CRASH_STEER        6       /* signed kick into the curve integrator */
#define CRASH_MARKER       7       /* marker effect id to raise */
#define CRASH_PHASE_LEAN   3       /* the one phase whose body still leans with the wheel */
#define CURVE_WINDOW_BIAS  0x4000  /* road_curve is compared to the window unsigned-biased by this */

/* §7 — engine. */
#define RPM_IDLE           0xf     /* rpm floor; speed_raw = (rpm - RPM_IDLE) * SPEED_PER_RPM */
#define RPM_BAND           0x70    /* the rpm bits that select a table band */
#define RPM_BRAKE_STEP     2
#define RPM_COAST_STEP     4       /* the script's coast-down (RM_IN_COAST), steeper than the brake */
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
#define STEER_ROW_SHIFT    3       /* (skid + steer_src) << this = steer-curve table row */
#define RPM_COL_SHIFT      4       /* rpm >> this = steer-curve table column */

/* §10 — spin-out. Holding a lock this long, against the spin override the event system left armed,
 * throws the buggy into the canned spin at SPIN_LOCK_START. */
#define STEER_HOLD_SPIN    10
#define SPIN_LOCK_START    0x18

/* §10 — road-edge clamp and off-road push. */
#define CLAMP_WIDE         0x144   /* road_curve limit with no shoulder in sight */
#define CLAMP_NARROW       0x46    /* ...where the row's shoulder flag is set but the road is closed */
#define CLAMP_SPEED_BASE   0x5a    /* ...open shoulder: (speed >> 1) + this — faster runs wider */
/* EDGE_OPEN / EDGE_LEFT / EDGE_RIGHT come from game.h: the course ring sets them per band and the
 * geometry builder carries them here through the control table. */
#define OFFROAD_LIMIT      0x6a    /* |road_curve| past this and the buggy is off the road */
#define OFFROAD_PUSH_SHIFT 3       /* push = excess - (excess >> 3) */
#define OFFROAD_LEAN_LEFT  0x14    /* lean = wheel_pos + this while ploughing the left shoulder */
#define OFFROAD_LEAN_RIGHT 0xa
#define SKID_PUSH          8       /* horizontal shove back toward the road */
#define ROW_OFFSET         0xa0    /* crash_disp counts rows: push rows * this */

/* §1 — the marker gate. The gate byte is the effect id the crash script raised last frame
 * (run_crash_script writes marker_pending from CRASH_MARKER); §1 hands it to handle_marker and CLEARS
 * it, closing the raise/consume loop across frames. Everything §1 does beyond the clear is off-frame
 * state this slice does not own: handle_marker and the engine-sound enable block (rev_reload / EGFLAG /
 * the VBL sound vector / EGOFF) are all sound — rev_reload aliases lean_frame (0x18d12), which no
 * compared surface reads, so it is skipped exactly as §6/§7 skip the same poke (see game.h). */
static void apply_marker_gate(PlayerState *p) {
    if (p->marker_pending != 0) {
        /* g_handle_marker(marker_pending): off-frame sound (stop music + INITFX), skipped */
        p->marker_pending = 0;
    }
}

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
 * frame the body is lifted", which is also the frame the lower body is drawn on. A spin override left
 * armed by the event system replaces the animated lean outright. Returns the resolved spin override —
 * §6's event path passes it to the dispatch as the event slot (recreate captures it here too). */
static uint16_t update_lean_anim(PlayerState *p, const PlayerAssets *a) {
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

    uint16_t spin = p->spin_reset != 0 ? p->spin_reset : p->spin_word2;
    if (spin != 0) p->lean = spin;
    return spin;
}

/* §6 (live-steering path) — the effective input when nothing has taken the controls away. Game over
 * pins the throttle on; an armed crash timer forces the brake instead. */
static uint16_t steer_centre_input(PlayerState *p) {
    p->steer_delta = 0;
    uint16_t in = (uint16_t)(p->input & IN_MASK);
    if (p->game_over) in = RM_IN_ACCEL;
    if (p->hud_crash_timer != 0) {
        in = (uint16_t)((in & (uint16_t)~RM_IN_ACCEL) | RM_IN_BRAKE);
        if (p->hud_crash_timer < 0) in = RM_IN_BRAKE;
    }
    return in;
}

/* §6 (script path) — replay one crash_anim_tbl record. The record poses the body, may override the
 * engine, and kicks the curve; the cursor then steps on. Steering is the only live input that still
 * gets through, OR'd onto whatever the script forces via turn_flags. Returns the effective input. */
static uint16_t run_crash_script(PlayerState *p, const PlayerAssets *a, uint16_t in) {
    const uint8_t *rec = a->crash_anim_tbl + p->collision_lock;

    in = (uint16_t)(p->turn_flags | (in & (RM_IN_LEFT | RM_IN_RIGHT)));
    p->collision_lock = (uint16_t)((uint8_t)(CRASH_REC_BYTES - rec[CRASH_STEP]) + p->collision_lock);

    if ((int8_t)rec[CRASH_LEAN] < 0) {          /* terminal record: the player drives again */
        p->crash_phase = 0;
        p->collision_lock = 0;
        return steer_centre_input(p);
    }

    p->lean = rec[CRASH_LEAN];
    p->buggy_pitch_off = (int16_t)be16(rec + CRASH_PITCH);
    if ((int8_t)rec[CRASH_RPM] >= 0) p->engine_rpm = rec[CRASH_RPM];
    p->anim_frame_sel = rec[CRASH_ANIM];
    p->steer_delta = (int8_t)rec[CRASH_STEER];
    p->marker_pending = rec[CRASH_MARKER];

    /* An armed window skips the script forward one record the moment the curve enters it — how being
     * shoved back onto the road cuts a crash short — and disarms itself so it fires once. */
    uint16_t curve_biased = (uint16_t)(p->road_curve + CURVE_WINDOW_BIAS);
    if (p->curve_window_lo != 0
        && (int16_t)(curve_biased - p->curve_window_lo) >= 0
        && (int16_t)(curve_biased - p->curve_window_hi) < 0) {
        p->curve_window_lo = 0;
        p->curve_window_hi = 0;
        p->collision_lock = (uint16_t)(p->collision_lock + CRASH_REC_BYTES);
    }
    return in;
}

/* §6 — who has the controls this frame. Three regimes, in the original's order:
 *   collision_lock == 0 && event_pending == 0 -> the player drives (steer_centre).
 *   collision_lock == 0 && event_pending != 0 -> an event is pending: dispatch it through the
 *     course-event engine (which may ARM a crash), zero the live input, then fall into the script
 *     body with the freshly-armed lock. `spin` (the §5-resolved override) is the event slot.
 *   collision_lock != 0                       -> the crash script already has the controls.
 * The dispatch arms/reads `ctx` (whose player is `p`); a bonus-display record rebuilds ctx->ctrl in
 * place, which §10's edge clamp then reads back. */
static uint16_t update_controls(PlayerState *p, const PlayerAssets *a,
                                RmEventCtx *ctx, uint16_t frame_input, uint16_t spin) {
    p->buggy_pitch_off = 0;
    if (p->collision_lock == 0 && p->event_pending == 0) return steer_centre_input(p);
    if (p->collision_lock == 0) {
        uint16_t pending = p->event_pending;             /* captured before it is cleared (recreate §2) */
        p->event_pending = 0;
        rm_event_dispatch(ctx, pending, spin, 1, 0);     /* slot=spin, obj_flag_a=1, obj_flag_b=0 */
        frame_input = 0;
    }
    return run_crash_script(p, a, frame_input);
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
    } else if (in & RM_IN_COAST) {
        rpm = (uint16_t)(rpm - RPM_COAST_STEP);
    }
    if (p->curve_clamp && (int16_t)(rpm - RPM_CLAMP_MIN) >= 0) rpm = (uint16_t)(rpm - RPM_CLAMP_STEP);

    /* The rev limiter is the script's to break: it holds the engine wherever a crash record put it. */
    if ((int16_t)(rpm - RPM_IDLE) < 0) rpm = RPM_IDLE;
    else if (p->collision_lock == 0 && (int16_t)(p->rpm_cap - rpm) < 0)
        rpm = (uint16_t)(rpm - RPM_OVERREV_STEP);
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
 * into road_curve. While the script is driving, the wheel still moves but the curve is steered from
 * centre — the crash, not the player, decides where the buggy goes. Returns the steering source §10
 * leans off. */
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

    uint16_t steer_src;
    if (p->collision_lock == 0) {
        p->lean = (uint16_t)(wheel + p->lean);
        steer_src = wheel;
    } else {
        if (p->crash_phase == CRASH_PHASE_LEAN)
            p->lean = (uint16_t)((wheel - WHEEL_CENTRE) + p->lean);
        steer_src = WHEEL_CENTRE;
    }

    /* The steer-curve row is (last frame's off-road push + the steering source) — being shoved off the
     * road bends you differently from steering there. The index goes negative, hence the cursor-zero
     * table. The script's own kick is added on top, and an armed freeze holds the curve for a frame. */
    int32_t row = ((int32_t)p->skid + (int32_t)steer_src) << STEER_ROW_SHIFT;
    int16_t curve_delta = (int8_t)a->steer_curve_tbl[row + (p->engine_rpm >> RPM_COL_SHIFT)];
    if (p->skid == 0) curve_delta = (int16_t)(p->hscroll_step2 + curve_delta);
    if (p->curve_freeze == 0)
        p->road_curve = (int16_t)(p->steer_delta + curve_delta + p->road_curve);
    return steer_src;
}

/* §10 — spin-out. Braking always settles the buggy; otherwise, holding a steering lock past
 * STEER_HOLD_SPIN throws it into a spin, but only in the direction the armed override does not
 * already cover — locking the other way just settles it. Either outcome consumes the override. */
static void arm_spin(PlayerState *p, uint16_t in, uint16_t wheel) {
    bool override_armed = p->spin_reset != 0 || p->spin_word2 != 0;
    /* Which lock spins you is whichever way the armed override is NOT already leaning the body. */
    uint16_t spin_lock = p->spin_reset != 0 ? 0 : WHEEL_MAX;
    uint16_t settle_lock = p->spin_reset != 0 ? WHEEL_MAX : 0;
    bool consumed = false;

    if (in & RM_IN_BRAKE) {
        consumed = true;
    } else if (override_armed && (int16_t)(p->steer_hold - STEER_HOLD_SPIN) >= 0) {
        if (wheel == spin_lock) {
            p->turn_flags = RM_IN_COAST;
            p->collision_lock = SPIN_LOCK_START;
            consumed = true;
        } else if (wheel == settle_lock) {
            consumed = true;
        }
    }
    if (consumed) {
        p->spin_reset = 0;
        p->spin_word2 = 0;
    }
}

/* §10 — how far off centre the road lets you get. The control row's flags say whether each shoulder
 * is there at all and whether it is open; road_curve is clamped to that, and past OFFROAD_LIMIT on an
 * open shoulder the buggy ploughs: a horizontal shove back (skid) and a vertical displacement.
 * Ploughing outranks a crash in progress — it cancels the script and settles any pending spin. */
static void update_edge_clamp(PlayerState *p, const uint8_t *ctrl, uint16_t steer_src) {
    uint16_t edge = be16(ctrl + RM_CTRL_EDGE_FLAGS_OFF);
    int16_t geom_hi = (int16_t)be16(ctrl + RM_CTRL_GEOM_HI_OFF);

    int16_t clamp_right = CLAMP_WIDE, clamp_left = CLAMP_WIDE;
    if ((int16_t)edge < 0 && geom_hi < 0) {
        int16_t shoulder = (edge & EDGE_OPEN) ? (int16_t)((p->speed >> 1) + CLAMP_SPEED_BASE)
                                              : CLAMP_NARROW;
        if (edge & EDGE_RIGHT) clamp_right = shoulder;
        if (edge & EDGE_LEFT)  clamp_left = shoulder;
    }

    /* A crash in progress steers itself off the road on purpose, so the clamp stands down for it. */
    p->curve_clamp = false;
    if (p->event_pending == 0 && p->crash_phase >= 0) {
        if (p->road_curve < 0) {
            if (p->road_curve <= -clamp_left) {
                p->road_curve = (int16_t)-clamp_left;
                p->curve_clamp = true;
            }
        } else if (p->road_curve >= clamp_right) {
            p->road_curve = clamp_right;
            p->curve_clamp = true;
        }
    }

    p->skid = 0;
    p->crash_disp = 0;
    if ((int16_t)edge >= 0) return;

    int16_t excess;
    if (p->road_curve < 0) {
        excess = (int16_t)(-OFFROAD_LIMIT - p->road_curve);
        if (!((edge & EDGE_OPEN) && (edge & EDGE_LEFT) && excess >= 0)) return;
        p->lean = (uint16_t)(steer_src + OFFROAD_LEAN_LEFT);
        p->skid = SKID_PUSH;
    } else {
        excess = (int16_t)(p->road_curve - OFFROAD_LIMIT);
        if (!((edge & EDGE_OPEN) && (edge & EDGE_RIGHT) && excess >= 0)) return;
        p->lean = (uint16_t)(steer_src + OFFROAD_LEAN_RIGHT);
        p->skid = -SKID_PUSH;
    }
    int16_t push = (int16_t)(excess - (excess >> OFFROAD_PUSH_SHIFT));
    p->crash_disp = (int16_t)(push * ROW_OFFSET);
    p->curve_clamp = false;                   /* ploughing is not a clamp — no engine drag from it */
    p->spin_reset = 0;
    p->spin_word2 = 0;
    p->collision_lock = 0;
}

void rm_player_update(PlayerState *p, const PlayerAssets *a, uint8_t *ctrl, RmEventCtx *ctx) {
    apply_marker_gate(p);                                          /* §1 */
    uint16_t frame_input = p->game_over ? 0 : (uint16_t)(p->input & IN_MASK);   /* §2 input capture */

    update_dashboard_anim(p, a, frame_input);
    update_bonus_clock(p);
    uint16_t spin = update_lean_anim(p, a);

    uint16_t in = update_controls(p, a, ctx, frame_input, spin);
    update_engine(p, a, in);
    update_view_and_scroll(p, a);
    uint16_t steer_src = update_steering(p, a, in);
    arm_spin(p, in, p->wheel_pos);
    update_edge_clamp(p, ctrl, steer_src);
}
