/* game_update.c — game_update @ 0x1110e: the per-frame in-race game-logic driver, root orchestrator
 * of the frame. No OS traps; returns each frame. Reconstructed from the Ghidra decompile + disasm.
 * The 68000 works in 16-bit registers; word/byte writes and compares are mirrored with
 * uint16_t/int16_t/uint8_t. Global/field roles are named in include/addrs.h.
 *
 * Sections (mirror the decomp): 1 marker gate + engine-sound; 2 input; 3 fire->dashboard variant;
 * 4 bonus-time countdown; 5 lean-anim + spin overrides; 6 crash/auto-steer script vs live steering;
 * 7 engine RPM/speed + EGFREQ; 8 scroll speed + view advance; 9 wheel position + lean; 10 road-curve
 * integration + edge clamp + off-road crash; 11 common path: build_road_geometry + return; 12 course
 * advance (collision probe, road-table shuffle, course-record unpack, marker/palette/scroll events),
 * fx-block rebuild, frame-event dispatch, and checkpoint/collision/score handling.
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

#define EGFLAG_ADDR        0x1b07c
#define GU_INPUT_MASK      0xff8f
#define GU_FIRE            0x80
#define GU_TIME_SUBDIV     0xb
#define GU_TIMEOUT_ARM     0x5b
#define GU_RPM_MIN         0xf
#define GU_SPEED_SPECIAL   0x44
#define GU_RPM_BAND        0x70
#define GU_VIEW_WRAP       8
#define GU_GROUND_OFF_MUL  0xdd
#define GU_EDGE_SEL_MUL    0x60
#define GU_STEER_HOLD_SPIN 10
#define GU_ROW_STRIDE      0xa0
#define GU_EVENT_CKPT      0x1a
#define GU_EVENT_COLLIDE   0x1d
#define GU_CRASH_PHASE_LEAN 3       /* crash_phase == this adds (wheel_pos - 2) to lean */
#define GU_ANIM_FRAME_HI   (A_anim_frame + 1)   /* the crash script writes anim_frame's high byte */

/* helpers mirroring the 68k word arithmetic */
static uint16_t rdw(uint8_t *im, uint32_t a) { return be16(im + a); }  /* read a BE word */
static void wrw(uint8_t *im, uint32_t a, uint16_t v) { wr16(im + a, v); }  /* write a BE word */

static void game_update_course_advance(uint8_t *image);   /* section 12 (view-wrap frames) */
static void game_update_fx_and_events(uint8_t *image);     /* sections G/H/I (course-advance tail) */

/* Resolve an A_event_jumptable entry to its handler target and invoke it with the frame context.
 * The table has 65 live entries (idx 0..64) reaching a family of course-event handlers, all in
 * 0x11ba4..0x11f4c. Grouped by resolved target address `t`:
 *   idx 1-5, 7-11  -> evt_flag_gate alt entries (0x11ba4..0x11bb4): each `moveq #k,d6` (obj_type
 *                     1..5) then the shared flag-sequence body; slot = d5.
 *   idx 13-21      -> score-message events (3 delta groups x {gate d6&&d7 / unconditional / d6&&!d7});
 *                     the fire is add_score(delta) then falls into play_event_tune(8).
 *   idx 22-24      -> checkpoint counter events (crash_lap++/crash_active++ + tune 9), gates d6&&d7 /
 *                     unconditional / d6&&!d7.
 *   idx 30/60      -> spawn a marker-decay object + score + tune 0xa (0x11d3a).
 *   idx 32-40      -> spin / rpm-penalty / collision-object spawns gated on collision_lock (0x11d64,
 *                     0x11d8e, 0x11dcc, 0x11de2).
 *   idx 25/27/43-59-> the common collision-object spawn (0x11e16).
 *   idx 61-62      -> finish-line display record + stop_music (0x11e6a body; OR gates).
 *   idx 41/42/63/64-> bonus-number display record + build_road_geometry + marker fx 8 (0x11ebe body).
 *   idx 26/28/29/31-> bare-rts no-ops (0x11d38 / 0x11d62).
 *   idx 0          -> a bare rts (unreachable; call sites guard != 0).
 *   idx 6, 12      -> an evt_flag_gate variant entered with d7=6 (@0x11c1a); it `bra`s into the body
 *                     past the type-match gate, so the flag sequence advances unconditionally
 *                     (g_evt_flag_gate_forced). */
#define GU_SCORE_A 0x17376    /* add_score delta pointers, one per score-event group (step +6) */
#define GU_SCORE_B 0x1737c
#define GU_SCORE_C 0x17382
#define GU_SCORE_TUNE 8
#define GU_CKPT_TUNE  9
#define GU_EVT_TUNE_A       0xa      /* object-spawn event tune (0x11d3a) */
/* checkpoint / collision / score-marker tunes (0x119c8..0x11a9c). play_event_tune has an image
 * effect only when unguarded, and these branches sit in the fuzz-unreached course-advance paths, so
 * a wrong id here is invisible to the differential harness — taken straight from the disassembly. */
#define GU_TUNE_CKPT_PASS   5        /* event_type==0x1a checkpoint reached (0x119c8) */
#define GU_TUNE_LEG_END     1        /* score digit hit '5' -> leg complete (0x11a82) */
#define GU_TUNE_COLL_MARK   6        /* collision-marker frame, bonus_timer armed (0x11a92) */
#define GU_MARKER_DECAY_ARM 0x1a0    /* marker_decay[4] countdown seed (0x11d3a) */
#define GU_SPIN_SPEED_MIN   0x1e     /* speed floor to arm a spin (0x11d64) */
#define GU_SPIN_LO          0xf      /* spin_reset value when d7==0 (0x11d64) */
#define GU_SPIN_HI          0x19     /* spin_word2 value when d7!=0 (0x11d64) */
#define GU_RPM_DROP         0x19     /* engine_rpm penalty (0x11de2) */
#define GU_SPEED_BIG        0x64     /* collision_lock 8 vs 0x18 threshold (0x11e16) */
#define GU_BONUS_HI_ID      0x32     /* event id >= this keeps the entry display params (0x11ebe) */
/* opaque display-record payloads: [collision_lock]=type, [crash_phase]=count, [curve_window]=data. */
#define GU_DISP_FINISH_A    0x90
#define GU_DISP_FINISH_B    0x1a8
#define GU_DISP_CW_FINISH   0x3ff6400aUL
#define GU_DISP_TYPE_L      0x3e8     /* type/entry-d0 for the left/curve<0 bonus variant */
#define GU_DISP_TYPE_R      0x460     /* type/entry-d0 for the right/curve>=0 bonus variant */
#define GU_DISP_CW_L        0x3f2e3f42UL
#define GU_DISP_CW_R        0x40be40d2UL
#define GU_CURVE_STEP_L     0x3c      /* road_curve delta, left variant */
#define GU_CURVE_STEP_R     0xffc4    /* road_curve delta, right variant (-0x3c) */

static int gu_gate(int kind, uint16_t d6, uint16_t d7) {   /* 0=always, 1=d6&&d7, 2=d6&&!d7 */
    if (kind == 1) return d7 != 0 && d6 != 0;
    if (kind == 2) return d7 == 0 && d6 != 0;
    return 1;
}

static void gu_score_fire(uint8_t *image, uint32_t delta) {
    g_add_score(image, delta);
    g_play_event_tune(image, GU_SCORE_TUNE);
}

static void gu_ckpt_counter(uint8_t *image) {              /* 0x11d1a body: bump lap/active + tune 9 */
    wrw(image, A_crash_lap,    (uint16_t)(rdw(image, A_crash_lap) + 1));
    wrw(image, A_crash_active, (uint16_t)(rdw(image, A_crash_active) + 1));
    g_play_event_tune(image, GU_CKPT_TUNE);
}

/* 0x11e6a body: finish-line display record then silence the music (unless game-over). */
static void gu_disp_finish(uint8_t *image, uint16_t type) {
    wr32(image + A_spin_reset, 0);                          /* clr.l -> spin_reset + spin_word2 */
    wrw(image, A_collision_lock, type);
    wrw(image, A_crash_phase, 1);
    wr32(image + A_curve_window, GU_DISP_CW_FINISH);
    g_stop_music(image, A_dosound_collide);
}

/* 0x11ebe body: bonus-number display record. `id` (d1) is the event id; (type,curve_step) are the
 * entry defaults for the id>=0x32 / spun-out cases. When collision_lock is already live it only
 * refreshes event_pending; otherwise it rebuilds the record, re-picking type/curve by road_curve
 * sign for low ids, then rebuilds the road and fires marker fx 8. (The fx_block[d2] read the 68k
 * does before build_road_geometry is dead — that function ignores d0 — so it is omitted.) */
static void gu_disp_bonus(uint8_t *image, uint16_t type, uint16_t id, uint16_t curve_step) {
    if (rdw(image, A_collision_lock) != 0) {
        if ((int16_t)rdw(image, A_crash_phase) < 0) id = 0;
        wrw(image, A_event_pending, id);
        return;
    }
    wr32(image + A_spin_reset, 0);
    uint32_t cw = GU_DISP_CW_FINISH;
    if ((int8_t)image[A_spin_state] != 0x20) {              /* not fully spun-out: pick by curve sign */
        if ((int16_t)rdw(image, A_road_curve) < 0) {
            cw = GU_DISP_CW_L;
            if ((int16_t)id < GU_BONUS_HI_ID) { type = GU_DISP_TYPE_L; curve_step = GU_CURVE_STEP_L; }
        } else {
            cw = GU_DISP_CW_R;
            if ((int16_t)id < GU_BONUS_HI_ID) { type = GU_DISP_TYPE_R; curve_step = GU_CURVE_STEP_R; }
        }
    }
    wrw(image, A_collision_lock, type);
    wrw(image, A_crash_phase, 0xffff);
    wr32(image + A_curve_window, cw);
    wrw(image, A_road_curve, (uint16_t)(rdw(image, A_road_curve) + curve_step));
    g_build_road_geometry(image);
    g_handle_marker(image, 8);
}

static void gu_dispatch_event(uint8_t *image, uint16_t idx, uint16_t d0, uint16_t d5,
                              uint16_t d6, uint16_t d7) {
    (void)d0;
    int16_t off = (int16_t)be16(image + A_event_jumptable + (uint16_t)(idx * 2));
    uint32_t t = (uint32_t)(A_event_jumptable + off);
    static const struct { uint32_t addr; int gate; uint32_t delta; } score[] = {
        {0x11c5a, 1, GU_SCORE_A}, {0x11c62, 0, GU_SCORE_A}, {0x11c6a, 2, GU_SCORE_A},
        {0x11cdc, 1, GU_SCORE_B}, {0x11ce4, 0, GU_SCORE_B}, {0x11cec, 2, GU_SCORE_B},
        {0x11cf6, 1, GU_SCORE_C}, {0x11cfe, 0, GU_SCORE_C}, {0x11d08, 2, GU_SCORE_C},
    };
    for (unsigned i = 0; i < sizeof score / sizeof score[0]; i++)
        if (t == score[i].addr) { if (gu_gate(score[i].gate, d6, d7)) gu_score_fire(image, score[i].delta); return; }

    /* checkpoint-counter group (shared 0x11d1a body, three gates). */
    if (t == 0x11d12) { if (d7 != 0 && d6 != 0) gu_ckpt_counter(image); return; }   /* idx 22 */
    if (t == 0x11d1a) { gu_ckpt_counter(image); return; }                           /* idx 23 */
    if (t == 0x11d2e) { if (d7 == 0 && d6 != 0) gu_ckpt_counter(image); return; }   /* idx 24 */

    if (t == 0x11d38 || t == 0x11d62) return;               /* bare-rts no-ops (idx 26/28/29/31) */

    if (t == 0x11d3a) {                                      /* idx 30/60: spawn marker-decay object */
        image[A_obj_active + 1 + (uint16_t)d5] = 0;
        wrw(image, A_marker_decay,     (uint16_t)(rdw(image, A_marker_decay) + 1));
        wrw(image, A_marker_decay + 2, d5);
        wrw(image, A_marker_decay + 4, GU_MARKER_DECAY_ARM);
        g_add_score(image, A_score_delta_evt);
        g_play_event_tune(image, GU_EVT_TUNE_A);
        return;
    }
    if (t == 0x11d64) {                                     /* idx 32/33: arm a spin if fast + unlocked */
        if ((int16_t)rdw(image, A_speed) >= GU_SPIN_SPEED_MIN && rdw(image, A_collision_lock) == 0) {
            if (d7 == 0) wrw(image, A_spin_reset, GU_SPIN_LO);
            else         wrw(image, A_spin_word2, GU_SPIN_HI);
        }
        return;
    }
    if (t == 0x11d8e) {                                     /* idx 34: spawn collision object by rpm band */
        if (rdw(image, A_collision_lock) == 0) {
            wr32(image + A_spin_reset, 0);
            wrw(image, A_turn_flags, 0);
            uint16_t band = (uint16_t)((rdw(image, A_engine_rpm) & GU_RPM_BAND) >> 3);
            wrw(image, A_collision_lock, be16(image + A_evt_obj_type_tbl + band));
            wrw(image, A_crash_phase, 3);
            g_handle_marker(image, band >= 6 ? 1 : 0);
        }
        return;
    }
    if (t == 0x11dcc) {                                     /* idx 35-37: freeze curve + marker fx 5 */
        if (rdw(image, A_collision_lock) == 0) {
            wrw(image, A_curve_freeze, 5);
            g_handle_marker(image, 5);
        }
        return;
    }
    if (t == 0x11de2) {                                     /* idx 38-40: rpm penalty -> speed, marker fx 6 */
        if (rdw(image, A_collision_lock) == 0) {
            int16_t rpm = (int16_t)(rdw(image, A_engine_rpm) - GU_RPM_DROP);
            if (rpm < GU_RPM_MIN) rpm = GU_RPM_MIN;
            wrw(image, A_engine_rpm, (uint16_t)rpm);
            uint16_t d1 = (uint16_t)(rpm - GU_RPM_MIN);
            wrw(image, A_speed, (uint16_t)(d1 * 3));         /* speed = d1 + 2*d1 */
            g_handle_marker(image, 6);
        }
        return;
    }
    if (t == 0x11e16) {                                     /* idx 25/27/43-59: common collision spawn */
        if (rdw(image, A_collision_lock) == 0) {
            wr32(image + A_spin_reset, 0);
            wrw(image, A_turn_flags, 0x10);
            wrw(image, A_collision_lock, (int16_t)rdw(image, A_speed) >= GU_SPEED_BIG ? 0x18 : 8);
            wrw(image, A_crash_phase, 2);
            g_handle_marker(image, 3);
        }
        return;
    }

    /* finish-line display (0x11e6a body); OR-style gates, two type variants. */
    if (t == 0x11e4e) { if (d6 != 0 || d7 != 0) gu_disp_finish(image, GU_DISP_FINISH_A); return; }  /* idx 61 */
    if (t == 0x11e5c) { if (d6 == 0 || d7 == 0) gu_disp_finish(image, GU_DISP_FINISH_B); return; }  /* idx 62 */

    /* bonus-number display (0x11ebe body); OR-style gates, entry (type,id,curve_step) defaults. */
    if (t == 0x11e8e) { if (d6 != 0 || d7 != 0) gu_disp_bonus(image, GU_DISP_TYPE_L, 0x29, GU_CURVE_STEP_L); return; }  /* idx 41 */
    if (t == 0x11e96) { if (d6 != 0 || d7 != 0) gu_disp_bonus(image, GU_DISP_TYPE_L, 0x3f, GU_CURVE_STEP_L); return; }  /* idx 63 */
    if (t == 0x11e92) { if (d6 == 0 || d7 == 0) gu_disp_bonus(image, GU_DISP_TYPE_R, 0x2a, GU_CURVE_STEP_R); return; }  /* idx 42 */
    if (t == 0x11eaa) { if (d6 == 0 || d7 == 0) gu_disp_bonus(image, GU_DISP_TYPE_R, 0x40, GU_CURVE_STEP_R); return; }  /* idx 64 */

    if (t >= 0x11ba4 && t <= 0x11bb4) g_evt_flag_gate(image, d5, (uint16_t)((t - 0x11ba4) / 4 + 1));
    else if (t == 0x11c1a)            g_evt_flag_gate_forced(image, d5);   /* d7=6 variant: gate skipped */
    /* t == 0x11c18 -> bare rts (no-op) */
}

/* Test glue: resolve+run one jump-table handler in isolation (entered at its own PC by the oracle). */
void g_gu_dispatch_event(uint8_t *image, uint32_t idx, uint32_t d5, uint32_t d6, uint32_t d7) {
    gu_dispatch_event(image, (uint16_t)idx, 0, (uint16_t)d5, (uint16_t)d6, (uint16_t)d7);
}

void g_game_update(uint8_t *image) {
    /* 1. pending marker gate + engine-sound enable. The gate byte itself is the effect id handed to
     * handle_marker (`move.b (marker_pending),d0; bsr handle_marker`), captured before it is cleared. */
    uint8_t marker_fx = image[A_marker_pending];
    if (marker_fx != 0) {
        image[A_marker_pending] = 0;
        g_handle_marker(image, marker_fx);
    }
    if (rdw(image, A_game_over_flag) == 0 && (int16_t)rdw(image, A_crash_phase) >= 0
        && rdw(image, A_crash_phase) != 1 && rdw(image, A_crash_frame) == 0) {
        if (rdw(image, A_speed) == 0) { wrw(image, A_rev_reload, 8); g_stop_music_chk(image, A_dosound_idle); }
        else { image[EGFLAG_ADDR] = 1; wr32(image + A_vbl_sound_vec, A_refresh); }
    } else {
        g_EGOFF(image);
    }

    /* 2. input. */
    uint16_t in = (rdw(image, A_game_over_flag) == 0)
                ? (uint16_t)(g_read_input(image), be16(image + A_input_state) & GU_INPUT_MASK) : 0;
    uint16_t event_pending = rdw(image, A_event_pending);

    /* 3. fire -> dashboard-variant animation. */
    int anim = rdw(image, A_fire_hold) != 0;
    if (!anim && (in & GU_FIRE) && (rdw(image, A_input_prev) & GU_FIRE) == 0) {
        wrw(image, A_fire_hold, 4); anim = 1;
    }
    if (anim) {
        wrw(image, A_dsp_variant_idx, (uint16_t)((rdw(image, A_dsp_variant_idx) + 8) & 0x38));
        wrw(image, A_fire_hold, (uint16_t)(rdw(image, A_fire_hold) - 1));
        if (rdw(image, A_fire_hold) == 0) {
            wrw(image, A_leg_flags_sel, (uint16_t)((rdw(image, A_leg_flags_sel) + 4) & 4));
            wr32(image + A_leg_flags_c90, be32(image + A_legflag_tbl + (int16_t)rdw(image, A_leg_flags_sel)));
        }
    }

    /* 4. bonus-time countdown. */
    if (rdw(image, A_hud_crash_timer) == 0) {
        int16_t sub = (int16_t)(rdw(image, A_time_subctr) - GU_TIME_SUBDIV);
        wrw(image, A_time_subctr, (uint16_t)(rdw(image, A_time_subctr) + 1));
        if (sub >= 0) {
            wrw(image, A_time_subctr, 0);
            int16_t t = (int16_t)(rdw(image, A_time_left) - 1);
            wrw(image, A_time_left, (uint16_t)t);
            if (t < 0) {
                wrw(image, A_time_left, 0);
                if (rdw(image, A_timeout_gate) == 0) wrw(image, A_hud_crash_timer, GU_TIMEOUT_ARM);
            }
        }
    }

    /* 5. lean-animation phase + spin overrides. */
    wrw(image, A_lean_phase, (uint16_t)((rdw(image, A_lean_phase) + 1) & 0xf));
    wrw(image, A_buggy_draw_flag, 0);
    uint16_t rpm = rdw(image, A_engine_rpm);
    uint16_t lean_idx = (uint16_t)(rdw(image, A_lean_phase) + (rpm & GU_RPM_BAND));
    int8_t lean_byte = (int8_t)image[A_lean_anim_tbl + (int16_t)lean_idx];
    uint16_t lean = (uint8_t)lean_byte;
    if (lean_byte < 0) { lean = 0; wrw(image, A_buggy_draw_flag, 0xffff); }
    wrw(image, A_lean_state, lean);
    uint16_t sp = rdw(image, A_spin_reset);
    if (sp != 0 || (sp = rdw(image, A_spin_word2)) != 0) wrw(image, A_lean_state, sp);

    /* 6. crash/auto-steer script (collision_lock) vs. live steering (steer_center). */
    wrw(image, A_buggy_pitch_off, 0);
    int steer_center = 0;
    if (rdw(image, A_collision_lock) != 0 || rdw(image, A_event_pending) != 0) {
        if (rdw(image, A_collision_lock) == 0) {               /* event path -> crash body */
            wrw(image, A_event_pending, 0);
            gu_dispatch_event(image, event_pending, 0, sp, 1, 0);   /* d5=slot=spin, d6=1, d7=0 */
            in = 0;
        }
        in = (uint16_t)(rdw(image, A_turn_flags) | (in & 0xc));
        uint16_t idx = rdw(image, A_collision_lock);
        uint32_t rec = A_crash_anim_tbl + idx;
        wrw(image, A_collision_lock, (uint16_t)((uint8_t)(8 - image[rec]) + idx));
        if ((int8_t)image[rec + 1] < 0) {                     /* terminal -> steer_center */
            wrw(image, A_crash_phase, 0); wrw(image, A_collision_lock, 0);
            wr32(image + A_vbl_sound_vec, A_refresh);
            steer_center = 1;
        } else {
            wrw(image, A_lean_state, image[rec + 1]);
            wrw(image, A_buggy_pitch_off, be16(image + rec + 2));
            if ((int8_t)image[rec + 4] >= 0) {
                wrw(image, A_engine_rpm, image[rec + 4]); wrw(image, A_rev_reload, 8);
            }
            image[GU_ANIM_FRAME_HI] = image[rec + 5];
            wrw(image, A_steer_delta, (uint16_t)(int16_t)(int8_t)image[rec + 6]);
            image[A_marker_pending] = image[rec + 7];
            uint16_t clo = be16(image + A_curve_window), chi = be16(image + A_curve_window + 2);
            uint16_t rc = (uint16_t)(rdw(image, A_road_curve) + 0x4000);
            if (clo != 0 && (int16_t)(rc - clo) >= 0 && (int16_t)(rc - chi) < 0) {
                wr32(image + A_curve_window, 0);
                wrw(image, A_collision_lock, (uint16_t)(rdw(image, A_collision_lock) + 8));
            }
        }
    } else {
        steer_center = 1;
    }
    if (steer_center) {
        wrw(image, A_steer_delta, 0);
        in = (uint16_t)(be16(image + A_input_state) & GU_INPUT_MASK);
        if (rdw(image, A_game_over_flag) != 0) in = 1;
        if (rdw(image, A_hud_crash_timer) != 0) {
            in = (uint16_t)((in & 0xfffe) | 2);
            if ((int16_t)rdw(image, A_hud_crash_timer) < 0) in = 2;
        }
    }

    /* 7. engine RPM / speed model + EGFREQ. */
    rpm = rdw(image, A_engine_rpm);
    uint16_t rpm_cap = be16(image + A_leg_flags_c90), rpm_add = be16(image + A_leg_flags_c90 + 2);
    if (in & 1) {
        rpm = (uint16_t)(rpm_add + rpm);
        if ((int16_t)(rpm_cap - rpm) < 0) rpm = (uint16_t)(rpm - rpm_add);
    } else if (in & 2) rpm = (uint16_t)(rpm - 2);
    else if (in & 0x10) rpm = (uint16_t)(rpm - 4);
    if (rdw(image, A_curve_clamp_flag) != 0 && (int16_t)(rpm - 0x2d) >= 0) rpm = (uint16_t)(rpm - 4);
    if ((int16_t)(rpm - GU_RPM_MIN) < 0) rpm = GU_RPM_MIN;
    else if (rdw(image, A_collision_lock) == 0 && (int16_t)(rpm_cap - rpm) < 0) rpm = (uint16_t)(rpm - 2);
    wrw(image, A_engine_rpm, rpm);
    uint16_t sraw = (uint16_t)((rpm - GU_RPM_MIN) * 3);
    wrw(image, A_speed_raw, sraw);
    uint16_t egf = sraw;
    if (rpm_cap == GU_SPEED_SPECIAL) {
        egf = (uint16_t)((uint16_t)((rpm - GU_RPM_MIN) * 9) >> 1);
        if ((int16_t)(egf - 0xff) >= 0) egf = 0xffff;
    }
    image[A_engfreq] = (uint8_t)egf;
    uint16_t speed = sraw;
    if ((int16_t)(egf - 100) >= 0) {
        wrw(image, A_speed_jitter_ph, (uint16_t)(rdw(image, A_speed_jitter_ph) + 1));
        speed = (uint16_t)((int16_t)be16(image + A_speed_jitter_tbl + (int16_t)(rdw(image, A_speed_jitter_ph) & 0xe)) + sraw);
    }
    wrw(image, A_speed, speed);

    /* 8. scroll speed + view-flags advance. */
    wrw(image, A_scroll_phase, (uint16_t)((rdw(image, A_scroll_phase) + 2) & 0xe));
    wrw(image, A_scroll_speed,
       be16(image + A_scroll_speed_tbl + (int16_t)rdw(image, A_scroll_phase) + (int16_t)(rpm & GU_RPM_BAND)));
    wrw(image, A_view_wrap_flag, 0);
    uint16_t vf = (uint16_t)((int16_t)be16(image + A_scroll_speed) * 2 + rdw(image, A_view_flags));
    if ((int16_t)vf > 7) {
        vf = 0;
        wrw(image, A_view_bank, (uint16_t)((rdw(image, A_view_bank) + 8) & 8));
        wrw(image, A_view_wrap_flag, 0xffff);
    }
    wrw(image, A_view_flags, vf);
    wrw(image, A_ground_view_off, (uint16_t)(vf * GU_GROUND_OFF_MUL));
    wrw(image, A_road_edge_sel, (uint16_t)((vf + (rdw(image, A_view_bank) & 8)) * GU_EDGE_SEL_MUL));

    /* 9. wheel position + lean from steering. */
    uint16_t wheel = rdw(image, A_wheel_pos);
    if ((in & 4) == 0) {
        if ((in & 8) == 0) {
            wrw(image, A_steer_hold, 0);
            if (wheel != 2) wheel = (uint16_t)((int16_t)(wheel - 2) < 0 ? wheel + 1 : wheel - 1);
        } else {
            wrw(image, A_steer_hold, (uint16_t)(rdw(image, A_steer_hold) + 1));
            wheel = (uint16_t)(wheel + 1); if ((int16_t)wheel > 3) wheel = 4;
        }
    } else {
        wrw(image, A_steer_hold, (uint16_t)(rdw(image, A_steer_hold) + 1));
        wheel = (uint16_t)(wheel - 1); if ((int16_t)wheel < 0) wheel = 0;
    }
    wrw(image, A_wheel_pos, wheel);
    uint16_t steer_src;
    if (rdw(image, A_collision_lock) == 0) {
        wrw(image, A_lean_state, (uint16_t)(wheel + rdw(image, A_lean_state)));
        steer_src = wheel;
    } else {
        if (rdw(image, A_crash_phase) == GU_CRASH_PHASE_LEAN)
            wrw(image, A_lean_state, (uint16_t)((wheel - 2) + rdw(image, A_lean_state)));
        steer_src = 2;
    }

    /* road-curve delta from the steer-curve table. */
    int16_t skid = (int16_t)rdw(image, A_sprite_suppress);          /* dual: prev-frame skid */
    int16_t curve_d = (int8_t)image[A_steer_curve_tbl + (int16_t)(rpm >> 4) + (int16_t)(skid << 3) + (int16_t)(steer_src << 3)];
    if (rdw(image, A_sprite_suppress) == 0) curve_d = (int16_t)(be16(image + A_hscroll_step2) + curve_d);
    if (rdw(image, A_curve_freeze) == 0)
        wrw(image, A_road_curve, (uint16_t)((int16_t)rdw(image, A_steer_delta) + curve_d + (int16_t)rdw(image, A_road_curve)));

    /* 10. edge clamp + off-road crash. */
    /* spin arming: brake or a held full-lock steer can trigger a spin; _DAT_00018cc8 = 0 clears the
     * spin LONG (spin_reset @0x18cc8 + spin_word2 @0x18cca). */
    int clear_spin = 0;
    if (in & 2) {
        clear_spin = 1;
    } else if ((int16_t)(rdw(image, A_steer_hold) - GU_STEER_HOLD_SPIN) >= 0) {
        if (rdw(image, A_spin_reset) == 0) {
            if (rdw(image, A_spin_word2) != 0) {
                if (wheel == 0) clear_spin = 1;
                else if (wheel == 4) { wrw(image, A_turn_flags, 0x10); wrw(image, A_collision_lock, 0x18); clear_spin = 1; }
            }
        } else if (wheel == 4) {
            clear_spin = 1;
        } else if (wheel == 0) {
            wrw(image, A_turn_flags, 0x10); wrw(image, A_collision_lock, 0x18); clear_spin = 1;
        }
    }
    if (clear_spin) wr32(image + A_spin_reset, 0);
    int16_t clamp_r = 0x144, clamp_l = 0x144;
    uint16_t edge = rdw(image, A_road_edge_flags);
    if ((int16_t)edge < 0 && (int16_t)be16(image + A_road_geom_hi) < 0) {
        if ((edge & 0x4000) && (clamp_r = 0x46, (edge & 0x1000))) clamp_r = (int16_t)((rdw(image, A_speed) >> 1) + 0x5a);
        if ((edge & 0x2000) && (clamp_l = 0x46, (edge & 0x1000))) clamp_l = (int16_t)((rdw(image, A_speed) >> 1) + 0x5a);
    }
    wrw(image, A_curve_clamp_flag, 0);
    if (rdw(image, A_event_pending) == 0 && (int16_t)rdw(image, A_crash_phase) >= 0) {
        int16_t rc = (int16_t)rdw(image, A_road_curve);
        if (rc < 0) {
            if ((int16_t)(-clamp_l - rc) >= 0) { wrw(image, A_road_curve, (uint16_t)-clamp_l); wrw(image, A_curve_clamp_flag, 1); }
        } else if ((int16_t)(rc - clamp_r) >= 0) { wrw(image, A_curve_clamp_flag, 1); wrw(image, A_road_curve, (uint16_t)clamp_r); }
    }
    wrw(image, A_buggy_skid_off, 0);
    wrw(image, A_crash_disp, 0);
    int off_road_crash = 0;
    if ((int16_t)edge < 0) {
        int16_t rc = (int16_t)rdw(image, A_road_curve);
        int16_t push = 0;
        if (rc < 0) {
            uint16_t u = (uint16_t)(0xff96 - rc);
            if ((edge & 0x1000) && (edge & 0x2000) && (int16_t)u >= 0) {
                push = (int16_t)(u - (u >> 3)); wrw(image, A_lean_state, (uint16_t)(steer_src + 0x14));
                wrw(image, A_buggy_skid_off, 8); off_road_crash = 1;
            }
        } else {
            uint16_t u = (uint16_t)(rc - 0x6a);
            if ((edge & 0x1000) && (edge & 0x4000) && (int16_t)u >= 0) {
                push = (int16_t)(u - (u >> 3)); wrw(image, A_lean_state, (uint16_t)(steer_src + 10));
                wrw(image, A_buggy_skid_off, (uint16_t)-8); off_road_crash = 1;
            }
        }
        if (off_road_crash) {
            wrw(image, A_crash_disp, (uint16_t)(push * GU_ROW_STRIDE));
            wrw(image, A_curve_clamp_flag, 0); wr32(image + A_spin_reset, 0); wrw(image, A_collision_lock, 0);
        }
    }
    wrw(image, A_sprite_suppress, rdw(image, A_buggy_skid_off));    /* skid_prev = buggy_skid_off */

    /* 11. common per-frame path: no view wrap -> just build the road geometry and return. */
    if (rdw(image, A_view_wrap_flag) == 0) { g_build_road_geometry(image); return; }

    /* 12. course advance (view wrapped this frame). */
    game_update_course_advance(image);
}

/* Section 12 — course advance (taken on the frame where view_flags wrapped). Probes collision,
 * scrolls the road-segment + road-curve tables up one row, pulls/unpacks the next packed course
 * record (or clears the row), rebuilds the road geometry, applies the record's marker/scroll/palette
 * event, rebuilds the 0x19114 fx block, dispatches the frame's events, and handles the checkpoint /
 * collision / score markers. Dense pointer code; addresses mirror the decomp exactly. */
#define GU_COURSE_MASK_BASE 0x5d48    /* buf_a + leg*0x2000 + this: per-course collision-flag longs */
#define GU_COURSE_STREAM    0x5ce0    /* buf_a + leg*0x2000 + this: packed course record stream base */
#define GU_LEG_STRIDE       0x2000
#define GU_ADD_SCORE_DELTA  0x1736a   /* A1 for add_score at the checkpoint path */
#define GU_SHUFFLE_P26      0x18d5c   /* puVar26 after the road_curve_tbl shuffle (13 iters) */
#define GU_SHUFFLE_P12      0x18d3c   /* puVar12 after the shuffle (= p26 - 0x20) */

static void game_update_course_advance(uint8_t *image) {
    wrw(image, A_event_pending, 0);
    uint32_t buf_a = be32(image + A_buf_a);
    uint16_t leg = rdw(image, A_leg_index);
    uint32_t leg_base = (uint32_t)((uint32_t)leg * GU_LEG_STRIDE + buf_a);

    /* collision probe: the per-course flag long, walked one bit per advance. */
    uint32_t mask_ptr = (uint32_t)((int16_t)(rdw(image, A_crash_bars) << 2) + leg_base + GU_COURSE_MASK_BASE);
    uint32_t coll_mask = be32(image + mask_ptr);
    image[A_course_flag_bit] = (uint8_t)(image[A_course_flag_bit] + 1);
    if ((int8_t)(image[mask_ptr] - image[A_course_flag_bit]) < 0) image[A_course_flag_bit] = 0;
    if (coll_mask & (1u << (image[A_course_flag_bit] & 0x1f)))
        g_probe_collision(image);   /* leaves D1 = updated mask; test stages the bit off (see notes) */

    /* road_seg_data: shift the 8-long window up by one word. */
    for (uint32_t p = A_road_seg_data, s = A_road_seg_data + 2, k = 0; k < 4; k++, p += 8, s += 8) {
        wr32(image + p, be32(image + s));
        wr32(image + p + 4, be32(image + s + 4));
    }

    /* road_curve_tbl: scroll the road-geometry window up by 0x20 bytes/frame, pulling from the ring
     * below it. Leaves p26 = GU_SHUFFLE_P26, p12 = GU_SHUFFLE_P12 for the unpack below. */
    uint32_t p22 = A_road_curve_tbl, p12 = A_course_src_ring, p26 = p12;
    for (int k = 0xc; k >= 0; k--) {
        p26 = p12;
        for (int n = 1; n <= 7; n++) wr32(image + p22 - 4 * n, be32(image + p26 - 4 * n));
        p12 = p26 - 0x20; p22 -= 0x20;
        wr32(image + p22, be32(image + p12));
    }

    wrw(image, A_course_row_ctr, (uint16_t)(rdw(image, A_course_row_ctr) - 8));
    if ((int16_t)rdw(image, A_course_row_ctr) < 0) {
        /* pull + unpack the next packed course record. */
        wrw(image, A_course_read_pos, (uint16_t)((rdw(image, A_course_read_pos) + 8) & 0x1ff8));
        uint32_t rec = (uint32_t)(leg_base + GU_COURSE_STREAM - (int16_t)rdw(image, A_course_read_pos));
        uint16_t marker_w = be16(image + rec + 6);
        uint16_t rec_w0 = be16(image + rec);
        uint8_t rec_ctl = image[rec + 2];
        /* clear the new row's 16 words at p12. */
        for (int k = 0; k < 16; k++) wr16(image + p12 + k * 2, 0);
        /* unpack 15 entries controlled by the (rec_w0 | coll_mask_hi) select mask, expanding the
         * animation control codes 0x0d/0x10/0x13/0x16 into their 2-word sub-runs. */
        uint32_t dst = p26 - 0x1f;
        uint32_t src = rec + 3;
        uint32_t sel = ((uint32_t)(uint16_t)(coll_mask >> 16) << 16) | rec_w0;
        for (int bit = 0xe; bit >= 0; bit--, dst += 2) {
            if (sel & (1u << (bit & 0x1f))) {
                int8_t c = (int8_t)image[src]; src += 1;
                image[dst] = (uint8_t)c;
                if (c == 0x0d) { image[dst+1]=0; image[dst+2]=0x0e; image[dst+3]=0; image[dst+4]=0x0f; }
                if (c == 0x10) { image[dst+1]=0; image[dst+2]=0x11; image[dst+3]=0; image[dst+4]=0x12; }
                if (c == 0x13) { image[dst+1]=0; image[dst+2]=0x14; image[dst+3]=0; image[dst+4]=0x15; }
                if (c == 0x16) { image[dst+1]=0; image[dst+2]=0x17; image[dst+3]=0; image[dst+4]=0x18; }
            }
        }
        uint32_t mw = p26 - 2;
        wr16(image + mw, marker_w);
        if ((int16_t)marker_w < 0) {
            if ((marker_w & 0xf01e) == 0xf012) image[mw] = (uint8_t)(image[mw] & 0x4f);
            else if ((marker_w & 0xf01e) == 0xf000) image[mw] = (uint8_t)(image[mw] & 0x6f);
            else if ((marker_w & 0x6000) == 0) image[mw] = (uint8_t)(image[mw] & 0x7f);
        } else {
            image[mw] = 0;
        }
        wrw(image, A_course_row_ctr, (uint16_t)(rec_ctl & 0xf8));
        wr16(image + A_marker_decay_base, (uint16_t)(int16_t)((rec_ctl & 7) - 3));
        if (be16(image + p26 - 0x1e) == 0x2e) wr16(image + p26 - 6, 0x2e);
        g_build_road_geometry(image);

        /* record's event: sprite-mode selector (dual-role road_width_src low byte & 6). */
        uint8_t mode = (uint8_t)(image[A_road_width_src] & 6);
        if (mode == 6) {
            /* tunnel palette swap: alternate one hardware colour register between record[0] and
             * record[reg_sel] each pass (palette_toggle picks the source), then poke the register
             * at 0xffff824c + reg_sel. That address is far above the image, so the write is
             * off-image — see g_poke_color_reg (no-op in the harness, real poke in the PRG). */
            uint32_t r = (uint32_t)(((uint16_t)image[(int16_t)rdw(image, A_palette_cursor) + (int16_t)(leg << 5) + buf_a + 0x50] << 4) + buf_a + 0xf0);
            int16_t reg_sel = (int16_t)be16(image + r + 0xe);
            uint16_t src_off;
            if (rdw(image, A_palette_toggle) == 0) { src_off = 0; wrw(image, A_palette_toggle, (uint16_t)reg_sel); }
            else { wrw(image, A_palette_toggle, 0); src_off = (uint16_t)reg_sel; }
            g_poke_color_reg(image, reg_sel, be16(image + r + sign_ext16(src_off)));
        } else if (mode == 2) {
            wrw(image, A_scroll_frame, (uint16_t)((rdw(image, A_scroll_frame) + 1) & 0xf));
            g_set_screen_offset(image);
        } else if (mode == 4) {
            wrw(image, A_palette_cursor, (uint16_t)((rdw(image, A_palette_cursor) + 1) & 0x1f));
            uint32_t pr = (uint32_t)(((uint16_t)image[(int16_t)rdw(image, A_palette_cursor) + (int16_t)(leg << 5) + buf_a + 0x50] << 4) + buf_a + 0xf2);
            wr16(image + A_palette_scratch, be16(image + pr));
            wr32(image + A_palette_scratch + 2, be32(image + pr + 2));
            wr32(image + A_palette_scratch + 6, be32(image + pr + 6));
            wr16(image + A_palette_scratch - 4, be16(image + pr + 0xa));
            wrw(image, A_obj_shade, (uint16_t)(be16(image + pr + 0xc) - 2));
            wrw(image, A_palette_toggle, 0);
            /* Setpalette loads the RACE palette (0x17fa2), not the scratch base: the original stages
             * into 0x17fb0.. then `suba #$18,a0` rewinds A0 to 0x17fa2 before the trap. The staging
             * writes overlap race_palette regs 5/7-11 (a partial in-race fade), so reg0 stays black —
             * loading 0x17fb0 (the +7 shifted view, reg0=tan) was the tunnel palette corruption. */
            g_xbios_setpalette(image, A_race_palette);   /* no image effect */
        }
    } else {
        /* no new record: clear the 15 marker words' low 6 bits, keep the previous slope. */
        uint32_t p = p12;
        for (int k = 0xe; k >= 0; k--, p += 2) wr16(image + p, (uint16_t)(be16(image + p) & 0xffc0));
        wr16(image + A_marker_decay_base, rdw(image, A_marker_slope_src));
        g_build_road_geometry(image);
    }

    game_update_fx_and_events(image);
}


/* Sections G/H/I — rebuild the 0x19114 fx block from obj_flags + the spin-effect table, dispatch the
 * two frame events keyed off horizon_row, then handle the checkpoint/collision/score markers. */
#define GU_SCORE_MAX_DIGIT '5'      /* score_str[1] == this ends the leg */
#define GU_BONUS_ARM       0x3c     /* bonus_timer armed on a collision-marker frame */
#define GU_CKPT_BANNER_T   0x28     /* gauge_blink (checkpoint banner timer) reload */

static void game_update_fx_and_events(uint8_t *image) {
    uint32_t obj = A_obj_flags;                          /* 0x18ebc */

    /* G. fx block rebuild. */
    wr32(image + A_fx_block, 0);   /* clr.l: zeros 0x19114..0x19117 (+2 word too) */
    wr32(image + A_fx_block_04, (uint32_t)be16(image + obj));          /* zext obj_flags[0] */
    wr32(image + A_fx_block_08, be32(image + A_fx_block_08) & 0xffff);
    uint32_t d = A_fx_block_0a, s = obj + 2;
    for (int k = 0xc; k >= 0; k--, d += 2, s += 2) wr16(image + d, be16(image + s));
    /* d/s now point one past the last copied word (d=0x19138, s=0x18ed8). */
    wr16(image + d, 0);
    wr16(image + d + 2, be16(image + s));
    wr32(image + d + 4, 0);
    wr32(image + d + 8, 0);
    wr16(image + A_spin_state, 0);
    /* Spin/fx select reads the two bytes at obj_flags-2 / obj_flags-1 (the original walks a1 to
     * obj_flags+0x1e after the fx-block copy, then `suba #$20` -> obj_flags-2). The earlier obj-0x1c
     * form dropped the +0x1e, reading the wrong bytes and mis-selecting the spin fx. */
    uint8_t flag_hi = (uint8_t)(image[obj - 2] & 0x60);
    if ((int8_t)image[obj - 2] >= 0 && ((image[obj - 1] & 0xe0) != 0 || flag_hi != 0)) {
        uint8_t sel = (uint8_t)((image[obj - 1] | (uint8_t)(flag_hi * 2)) >> 5);
        uint8_t fx = image[A_fx_type_tbl + sel];
        wrw(image, A_spin_state, (uint16_t)(fx << 8));
        if (fx != 0 && (int8_t)fx >= 0) {
            uint32_t ps = A_fx_block, pt = A_fx_type_tbl + fx;
            for (int k = 0x17; k >= 0; k--, ps += 2, pt += 1)
                if (be16(image + ps) == 0) image[ps + 1] = image[pt];
        }
    }
    if (be16(image + A_fx_block_06) == 0x3d) {
        wr32(image + A_fx_block, 0x3d003d); wr32(image + A_fx_block_04, 0x3d003d);
        wr32(image + A_fx_block_08, 0x3d003d); wr32(image + A_fx_block_0c, 0x3d003d);
        wr32(image + A_fx_block_10, 0x3d003d);
    }
    if (be16(image + A_fx_block_26) == 0x3d) {
        wr32(image + A_fx_block_1a, 0x3e003e); wr32(image + A_fx_block_1e, 0x3e003e);
        wr32(image + A_fx_block_22, 0x3e003e); wr32(image + A_fx_block_26, 0x3e003e);
        wr32(image + A_fx_block_2a, 0x3e003e); wr16(image + A_fx_block_2e, 0x3e);   /* move.w d0.w (=0x003e) */
    }
    wrw(image, A_curve_freeze, 0);

    /* H. two frame-event dispatches keyed off horizon_row. The dispatch passes D5 = the scanline
     * slot (horizon_row, then horizon_row+2) — handlers use it to index obj_active (`clear
     * obj_active[d5+1]`), which for the +2 slot aliases event_type (0x18eca). Passing 0 here left
     * event_type/obj_active flags uncleared, drifting the course/palette state over real play. */
    uint16_t hr = rdw(image, A_horizon_row);
    uint8_t ev = image[A_fx_block + hr + 1];
    if (ev != 0) gu_dispatch_event(image, ev, 0, hr, rdw(image, A_horizon_frac), 0);
    ev = image[A_fx_block + (uint16_t)(hr + 2) + 1];
    if (ev != 0) gu_dispatch_event(image, ev, 0, (uint16_t)(hr + 2), rdw(image, A_horizon_frac), 0xff);

    /* I. checkpoint / collision / score markers. The original loads the event_type WORD and tests
     * its low byte (`move.w (event_type),d1; cmpi.b #$1a,d1`), i.e. image[A_event_type+1] big-endian —
     * the marker code (0x1a/0x1d) lives in the low byte, high byte is 0. */
    uint8_t event_code = image[A_event_type + 1];
    if (event_code == GU_EVENT_CKPT) {
        g_play_event_tune(image, GU_TUNE_CKPT_PASS);
        uint16_t lap = rdw(image, A_crash_lap);
        wrw(image, A_hud_crash_timer, 0);
        wrw(image, A_crash_bars, (uint16_t)(rdw(image, A_crash_bars) + 1));
        wrw(image, A_crash_active, (uint16_t)(rdw(image, A_crash_active) + 1));
        if (image[A_score_str + 1] == GU_SCORE_MAX_DIGIT) { wrw(image, A_hud_crash_timer, 0x65); g_play_event_tune(image, GU_TUNE_LEG_END); return; }
        image[A_score_str + 1] = (uint8_t)(image[A_score_str + 1] + 1);
        int8_t c = (int8_t)(image[A_score_label + 0x7 + rdw(image, A_crash_bars)]);   /* "SCORE/"[crash_bars+7] */
        c = (int8_t)(c + (int8_t)rdw(image, A_time_left));
        wrw(image, A_gauge_blink_on, 0);
        if (lap != 0) {
            wrw(image, A_crash_lap, 0);
            int8_t c7 = (int8_t)(lap * 2);
            c = (int8_t)(c7 + c);
            image[A_score_overlay_dig] = (uint8_t)(c7 + '0');
            wrw(image, A_gauge_blink_on, (uint16_t)(((uint16_t)(lap * 2) >> 8 << 8) | image[A_score_overlay_dig]));
        }
        image[A_time_left + 1] = (uint8_t)c;   /* time_left low byte = checkpoint char (CONCAT) */
        wrw(image, A_gauge_blink, GU_CKPT_BANNER_T);
        if (rdw(image, A_leg_index) == 0) { g_init_leg_dash(image); g_draw_leg_labels(image); }
    } else if (event_code == GU_EVENT_COLLIDE) {
        g_probe_collision(image);
    }
    if (image[A_ground_scan_tbl + 1] != GU_EVENT_COLLIDE) {
        /* draw_checkpoint_anim gate reads the marker byte at +3 (`cmpi.b #$1a,(0x18d4b)`), the same
         * field draw_ground reads — not the +0 scanline byte. */
        if (image[A_ground_scan_tbl + 3] == GU_EVENT_CKPT && image[A_score_str + 1] != '1') {
            int16_t s = (int16_t)(rdw(image, A_ckpt_scroll) - 0x10);
            wrw(image, A_ckpt_scroll, (uint16_t)(rdw(image, A_ckpt_scroll) + 4));
            if (s >= 0) wrw(image, A_ckpt_scroll, 0);
            g_draw_checkpoint_anim(image);
        }
        g_add_score(image, GU_ADD_SCORE_DELTA);
        return;
    }
    wrw(image, A_bonus_timer, GU_BONUS_ARM);
    g_play_event_tune(image, GU_TUNE_COLL_MARK);
}

/* Test seam @0x118b6 — the sections-G/H/I tail (fx-block rebuild, horizon-event dispatch, and the
 * checkpoint/leg-end/collision-marker jingles). Entered directly so the directed coverage tests can
 * stage event_type/score_str/ground_scan and reach the play_event_tune sites (0x119ca/0x11a8c/
 * 0x11a9c) that the section-12 fuzz never hits — the full frame recomputes event_type upstream. */
void g_game_update_fx_and_events(uint8_t *image) { game_update_fx_and_events(image); }
