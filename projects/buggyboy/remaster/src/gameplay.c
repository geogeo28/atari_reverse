/* gameplay.c — remaster of the draw_game_objects prefix (recreate's gobj_prefix @0x12ef6..0x12fc0).
 *
 * The deterministic per-frame state advance draw_game_objects runs before any drawing. It writes no
 * framebuffer pixels — it is off-frame game state: the marker-decay slot (records cleared/retired as
 * a roadside marker fades), the road-colour animation counters (which feed the animated colour the
 * palette uses), and the bonus-window flag animation. Transcribed 1:1 from recreate (16-bit wraps
 * mirrored); the flat-image reads/writes become native fields + named arenas (see game.h).
 */
#include <string.h>

#include "game.h"
#include "st.h"

#define GOBJ_MARKER_RECS      0xd    /* dbf #0xd -> 14 records cleared */
#define GOBJ_MARKER_STRIDE    0x20
#define OBJ_ANIM_IDX_MASK     0x1e   /* anim_counter & this indexes the anim tables */
#define GOBJ_DSP_ANIM_CAP     5      /* dsp_color_scroll cycles 0..4 while the bonus window is open */
#define GOBJ_BONUS_FLAG_FRAME 0x28   /* at this bonus_timer value, advance the flag sequence */
#define GOBJ_FLAG_SEQ_STEP    0x10
#define GOBJ_FLAG_SEQ_MASK    0x30
#define GOBJ_FLAG_SEQ_CAP     5
#define GOBJ_COLORIDX_SHIFT   3      /* anim colour-index << this = color_pairs byte offset */

void rm_gobj_prefix(GobjPrefixState *s, const GobjPrefixAssets *a) {
    /* marker-decay: clear this frame's 14-record slot, count down, retire the slot when exhausted. */
    if (s->marker_active != 0) {
        uint32_t rec = sx16((uint16_t)s->marker_off);
        for (int i = 0; i <= GOBJ_MARKER_RECS; i++, rec += GOBJ_MARKER_STRIDE)
            a->marker_recs[rec] = 0;
        int16_t countdown = (int16_t)(s->marker_countdown - GOBJ_MARKER_STRIDE);
        s->marker_countdown = countdown;
        if (countdown < 0) {
            s->marker_active = 0;                       /* clr.l -(a1): active + offset */
            s->marker_off = 0;
        } else {
            uint32_t decay = sx16((uint16_t)s->marker_off) + sx16((uint16_t)countdown);
            a->marker_recs[decay] = (uint8_t)(a->marker_recs[decay] - 1);
        }
    }

    /* road-colour animation: advance the counters, index the anim word + colour tables, mirror. */
    s->view_parity = (uint16_t)(s->view_parity + 2);
    s->anim_counter = (uint16_t)(s->anim_counter + 2);
    uint16_t idx = (uint16_t)(s->anim_counter & OBJ_ANIM_IDX_MASK);
    uint16_t anim_word = be16(a->anim_word_tbl + idx);
    s->anim_word = anim_word;
    wr16(a->anim_mirror1, anim_word);
    wr16(a->anim_mirror2, anim_word);
    uint16_t color_off = (uint16_t)(be16(a->anim_coloridx_tbl + idx) << GOBJ_COLORIDX_SHIFT);
    wr32(a->anim_color,     be32(a->color_pairs + color_off));
    wr32(a->anim_color + 4, be32(a->color_pairs + color_off + 4));

    /* bonus window: cycle the dsp colour scroll, count down, advance the flag sequence at 0x28. */
    if (s->bonus_timer != 0) {
        uint16_t scroll_next = (uint16_t)(s->dsp_color_scroll + 1);
        if ((int16_t)scroll_next >= GOBJ_DSP_ANIM_CAP) scroll_next = 0;
        s->dsp_color_scroll = scroll_next;
        uint16_t bonus_left = (uint16_t)(s->bonus_timer - 1);
        s->bonus_timer = bonus_left;
        if (bonus_left == 0) {
            s->dsp_color_scroll = 0;
        } else if (bonus_left == GOBJ_BONUS_FLAG_FRAME) {
            s->flag_seq_off = (uint16_t)((s->flag_seq_off + GOBJ_FLAG_SEQ_STEP) & GOBJ_FLAG_SEQ_MASK);
            if ((int16_t)s->flag_seq_count >= GOBJ_FLAG_SEQ_CAP)
                s->flag_seq_count = 0;
        }
    }
}

/* Fan the flag-sequence state into the HUD view (see game.h). draw_hud reads flag_seq_count (phase 4)
 * and the flag_seq_off / dsp_color_scroll colour cursors (phase 5) as globals in the original; here
 * they are GobjPrefixState fields the shell must copy into the per-frame HudState, like the EventState
 * crash scalars rm_apply_player copies. Called after rm_gobj_prefix, before rm_draw_hud. */
void rm_gobj_hud_view(const GobjPrefixState *g, HudState *hud) {
    hud->flag_seq_count   = g->flag_seq_count;
    hud->flag_seq_off     = (int16_t)g->flag_seq_off;
    hud->dsp_color_scroll = (int16_t)g->dsp_color_scroll;
}

/* ---- init_leg (recreate gameplay.c g_init_leg @0x104b8) — the leg-start state reset ----------------
 *
 * g_init_leg clears a contiguous 0x6d-word block of the flat image then seeds a few scalar defaults;
 * that block is nearly the whole per-leg game-state region, so in native terms almost every field of
 * the owner structs goes to zero and a handful get defaults. The clear does NOT reach a couple of
 * fields below/above its bounds — the game-over flag and the time-out gate (PlayerState), and the
 * anim-frame counter and flag-sequence cursor (GobjPrefixState) — which must survive a re-init, so
 * those are preserved across the reset. */

/* Phase-2 scalar defaults (recreate's INIT constants at those image addresses). */
#define IL_ENGINE_RPM   0xf     /* engine_rpm */
#define IL_RPM_CAP      0x44    /* leg_flags_c90 high word */
#define IL_RPM_ADD      0x2     /* leg_flags_c90 low word */
#define IL_VIEW_FLAGS   0x2     /* view_flags */
#define IL_GROUND_VIEW  0x1ba   /* ground_view_off / obj_scan_off */
#define IL_ROAD_EDGE    0xc0    /* road_edge_sel */
#define IL_WHEEL_POS    0x2     /* wheel_pos */
#define IL_LEAN         0x2     /* lean_state */
#define IL_TIME_LEFT    0x46    /* time_left */
#define IL_LEAN_FRAME   0x8     /* lean_frame (buggy lean-animation cursor) */
#define IL_VARIANT      0x8     /* buggy_variant scratch (draw_buggy overwrites it with lean*8) */

/* Phase 10 — the leg's 14 roadside-object marker records, unpacked into the ring's 14 bands. Each
 * source record uses the shared 8-byte RM_REC_* wire layout (game.h), the same course.c decodes. */
#define IL_MARKER_SRC_BASE   0x5ce0   /* buf_a + this + leg*IL_MARKER_LEG_STRIDE: the record block */
#define IL_MARKER_LEG_STRIDE 0x2000
#define IL_MARKER_MASK_BITS  0xe      /* the select mask walks bits 0xe..0 (slot = 0xe - bit) */
#define IL_MARKER_FLAG_MASK  0x60     /* marker fixup: if neither of these bits set, clear the sign */
#define IL_MARKER_SIGN_CLEAR 0x7f     /* ...i.e. AND off the sign bit (0x80), keeping the low 7 */

/* Phase 11 — the first object-display / palette record's selector, per leg. The record is shared with
 * the mode-4 palette event (rm_course_mode_event), so its resolver and stager live in game.h as
 * rm_objdisp_record / rm_stage_palette_record and are used by both. */
#define IL_OBJDISP_SEL_OFF   0x50     /* buf_a + this + leg*IL_OBJDISP_LEG_STRIDE: the selector byte */
#define IL_OBJDISP_LEG_STRIDE 0x20    /* per-leg stride of the selector table */
#define IL_OBJDISP_TBL_OFF   0xf2     /* buf_a + this + selector*IL_OBJDISP_REC_STRIDE: the record */
#define IL_OBJDISP_REC_STRIDE 0x10    /* per-selector stride of the record table */
#define IL_OBJDISP_SHADE_BIAS 2

/* Resolve the object-display / palette record for a given palette cursor (0 at a leg start): the
 * selector byte at buf_a[0x50 + cursor + leg*0x20] indexes the 16-byte record table at buf_a + 0xf2. */
const uint8_t *rm_objdisp_record(const uint8_t *buf_a, uint16_t leg, uint16_t cursor) {
    uint8_t sel = buf_a[(uint16_t)(IL_OBJDISP_SEL_OFF + cursor + leg * IL_OBJDISP_LEG_STRIDE)];
    return buf_a + IL_OBJDISP_TBL_OFF + (uint16_t)(sel * IL_OBJDISP_REC_STRIDE);
}

/* Stage the record's four colour pieces into `race_pal` (the original's 0x17fac.. writes overlapping
 * the race palette) and derive obj_shade. The odd write order / offsets mirror g_init_leg exactly. */
void rm_stage_palette_record(uint8_t *race_pal, int16_t *obj_shade, const uint8_t *disp) {
    wr16(race_pal + RM_PAL_STAGE_W1_OFF, be16(disp));         /* disp[0..1]   -> 0x17fb0 */
    wr32(race_pal + RM_PAL_STAGE_L1_OFF, be32(disp + 2));     /* disp[2..5]   -> 0x17fb2 */
    wr32(race_pal + RM_PAL_STAGE_L2_OFF, be32(disp + 6));     /* disp[6..9]   -> 0x17fb6 */
    wr16(race_pal + RM_PAL_STAGE_W2_OFF, be16(disp + 0xa));   /* disp[0xa..b] -> 0x17fac */
    *obj_shade = (int16_t)(be16(disp + RM_OBJDISP_SHADE_OFF) - IL_OBJDISP_SHADE_BIAS);
}

/* Phase 7 — the road-scroll offset: the leg's scroll table (buf_a + leg*IL_SCROLL_TBL_STRIDE), indexed
 * by scroll_frame (0 at a leg start, since phase 1 clears it), times one 40-scanline band. Shared with
 * the mode-2 screen-offset event (rm_course_mode_event), which calls it at the advanced scroll_frame. */
#define IL_SCROLL_TBL_STRIDE 0x10
#define IL_SCROLL_BAND_BYTES 0x1900

uint16_t rm_screen_offset(const uint8_t *buf_a, uint16_t leg, uint16_t scroll_frame) {
    uint8_t step = buf_a[(uint16_t)(leg * IL_SCROLL_TBL_STRIDE + scroll_frame)];
    return (uint16_t)(step * IL_SCROLL_BAND_BYTES);
}

/* Phase 4 — the HUD bonus-time strings ("/2000/" ...), copied from program data into the HUD-text
 * region (leg 0 uses the base source; later legs start IL_LEGTIME_LEG_OFF further in). */
#define IL_LEGTIME_LEG_OFF   0x1e
#define IL_LEGTIME_DST_OFF   0x1a     /* hud_text + this (image 0x1818c) */
#define IL_LEGTIME_ROWS      5
#define IL_LEGTIME_COPY      6        /* bytes copied per row (a long + a word); 8 more are skipped */
#define IL_LEGTIME_DST_STRIDE 0xe

/* Phase 5/6 — the score string template + BCD reset, both inside the HUD-text region. */
#define IL_SCORE_TMPL_OFF    0x8a     /* hud_text + this (image 0x181fc): the "/1______0" template */
#define IL_SCORE_TMPL_BYTES  10
#define IL_SCORE_DIGITS_OFF  RM_HUD_SCORE_BCD_OFF   /* six ASCII score digits reset to '0' (0x1824c) */
#define IL_SCORE_DIGITS      6

/* Seed the far-to-near ring from the leg's 14 packed marker records (phases 9 + 10). Each 8-byte
 * record carries a 15-bit select mask; a set bit copies the next source byte into that slot's LOW byte
 * (the high byte stays clear, so a code sits where the object-list dispatcher indexes it). The type
 * word becomes the band's marker after a sign/priority fixup. */
static void init_ring_seed(CourseRing *ring, const uint8_t *buf_a, uint16_t leg) {
    const uint8_t *rec = buf_a + IL_MARKER_SRC_BASE + (uint32_t)leg * IL_MARKER_LEG_STRIDE;
    for (int band = 0; band < RM_RING_ROWS; band++, rec += RM_REC_STRIDE) {
        CourseRow *row = &ring->row[band];
        for (int slot = 0; slot < RM_RING_SLOTS; slot++) row->slot[slot] = 0;   /* phase 9 clear */

        int16_t  type = (int16_t)be16(rec + RM_REC_MARKER_OFF);
        uint16_t mask = be16(rec + RM_REC_SELECT_OFF);
        const uint8_t *code = rec + RM_REC_CODES_OFF;   /* mask word, a skipped ctl byte (+2), then codes */
        for (int bit = IL_MARKER_MASK_BITS; bit >= 0; bit--)
            if (mask & (1u << bit)) row->slot[IL_MARKER_MASK_BITS - bit] = *code++;

        uint8_t hi = (uint8_t)((uint16_t)type >> 8);
        if (type >= 0) hi = 0;                       /* a non-negative type keeps only its low byte */
        if ((hi & IL_MARKER_FLAG_MASK) == 0) hi &= IL_MARKER_SIGN_CLEAR;   /* no priority bits -> drop the sign too */
        row->marker = (uint16_t)((hi << 8) | ((uint16_t)type & 0xff));
    }
}

void rm_init_leg(PlayerState *p, CourseState *cs, RoadPose *pose, ScrollState *scroll,
                 CourseRing *ring, EventState *ev, GobjPrefixState *gobj, SpriteState *sprite,
                 uint8_t *hud_text, int16_t *obj_shade, uint16_t *screen_offset, uint8_t *race_pal,
                 const RmInitAssets *a, uint16_t leg) {
    /* Phase 1/2: the physics scalars — clear then default. game_over / timeout_gate live below the
     * cleared block, so a re-init preserves them. */
    bool game_over = p->game_over, timeout_gate = p->timeout_gate;
    memset(p, 0, sizeof *p);
    p->game_over = game_over;
    p->timeout_gate = timeout_gate;
    p->engine_rpm = IL_ENGINE_RPM;
    p->rpm_cap = IL_RPM_CAP;
    p->rpm_add = IL_RPM_ADD;
    p->view_flags = IL_VIEW_FLAGS;
    p->ground_view_off = IL_GROUND_VIEW;
    p->road_edge_sel = IL_ROAD_EDGE;
    p->wheel_pos = IL_WHEEL_POS;
    p->lean = IL_LEAN;
    p->time_left = IL_TIME_LEFT;

    memset(cs, 0, sizeof *cs);                       /* course_row_ctr / course_read_pos */

    memset(pose, 0, sizeof *pose);                   /* curve, seg_data (phase 8), horizon outputs */
    pose->view_flags = IL_VIEW_FLAGS;

    memset(scroll, 0, sizeof *scroll);               /* hscroll_pos / step2 / speed / seg_head */

    /* EventState: cleared, but the dashboard-marker scalars (dash_y/bit/x) sit below the cleared block
     * and g_init_leg does not touch them (verified: 0 at a leg start), so preserve them. */
    uint8_t dash_y = ev->dash_y, dash_bit = ev->dash_bit;
    uint16_t dash_x = ev->dash_x;
    memset(ev, 0, sizeof *ev);
    ev->dash_y = dash_y;
    ev->dash_bit = dash_bit;
    ev->dash_x = dash_x;

    /* GobjPrefixState: the anim-frame counter and flag-sequence cursor sit outside the cleared block. */
    uint16_t anim_counter = gobj->anim_counter, flag_seq_off = gobj->flag_seq_off;
    memset(gobj, 0, sizeof *gobj);
    gobj->anim_counter = anim_counter;
    gobj->flag_seq_off = flag_seq_off;

    /* Phase 8/9/10: clear + seed the ring, then refresh the sprite gates the near band feeds. */
    init_ring_seed(ring, a->buf_a, leg);

    /* Buggy-sprite pose: the persistent lean-animation cursor and the leg-start body pose. The fields
     * apply_player re-derives each frame (pitch/skid/speed_raw...) are set to 0 here for a consistent
     * boot snapshot; the sprite gates come from the ring just seeded. */
    memset(sprite, 0, sizeof *sprite);
    sprite->lean = IL_LEAN;
    sprite->wheel_pos = IL_WHEEL_POS;
    sprite->lean_frame = IL_LEAN_FRAME;
    sprite->variant = IL_VARIANT;
    sprite->buggy_gate = rm_ring_buggy_gate(ring);
    sprite->fg_gate = rm_ring_fg_gate(ring);

    /* Phase 4: HUD bonus-time strings (the shorter set from leg 1 on). */
    const uint8_t *src = a->legtime + (leg != 0 ? IL_LEGTIME_LEG_OFF : 0);
    uint8_t *dst = hud_text + IL_LEGTIME_DST_OFF;
    for (int row = 0; row < IL_LEGTIME_ROWS; row++, src += IL_LEGTIME_COPY, dst += IL_LEGTIME_DST_STRIDE)
        for (int b = 0; b < IL_LEGTIME_COPY; b++) dst[b] = src[b];

    /* Phase 5/6: score string template (copied within the HUD-text region) + the six-digit BCD reset. */
    for (int b = 0; b < IL_SCORE_TMPL_BYTES; b++)
        hud_text[RM_HUD_SCORE_STR_OFF + b] = hud_text[IL_SCORE_TMPL_OFF + b];
    for (int b = 0; b < IL_SCORE_DIGITS; b++) hud_text[IL_SCORE_DIGITS_OFF + b] = '0';

    /* Phase 7: this frame's road-scroll offset (scroll_frame is 0 at a leg start). */
    *screen_offset = rm_screen_offset(a->buf_a, leg, 0);

    /* Phase 11: the first object-display / palette record (palette cursor 0 at a leg start). Stage its
     * colours into race_pal (an off-image Setpalette seam mode 4 re-stages) and derive obj_shade. */
    rm_stage_palette_record(race_pal, obj_shade, rm_objdisp_record(a->buf_a, leg, 0));
}

/* ---- apply_player — fan the driving model's per-frame outputs out to the render structs -------------
 *
 * The whole of the "game loop" beyond running the physics/events and drawing: each assignment is one
 * of the original's shared globals, so the draws read this frame's state through their own structs.
 * Pure struct-to-struct derivation, hoisted out of the on-target shell (game_main.c) so `make test`
 * compiles and exercises it host-side (test_leg_drive pins the sprite fan-out against recreate's image
 * bytes). `road_edge_base` is the edge-run table already biased by ROAD_EDGE_PAD (a fixture pointer
 * the shell owns); the per-frame edge_tbl aliases it at road_edge_sel, exactly as the original does.
 *
 * The pose's curve/view come straight from the physics; the ground column and the object list's scan
 * offset are the same global; the HUD shows the speed and clock plus the six scalars EventState OWNS
 * (game.h ownership contract), refreshed from the event engine each frame like speed/time. The sprite
 * reads the body pose AND the crash/spin script state: skid doubles as the foreground-sprite
 * suppressor; the crash script's anim_frame_sel picks the foreground frame; the fx<<8 spin word's hi
 * byte gates the spin abort; and collision_lock plus the spin longword suppress the lower body. */
void rm_apply_player(const PlayerState *p, const EventState *ev,
                     RoadPose *pose, ScrollState *scroll, SpriteState *sprite,
                     GroundState *ground, ObjListCtx *objlist, HudState *hud,
                     RoadInput *road, const uint8_t *road_edge_base) {
    pose->curve = p->road_curve;
    pose->view_flags = p->view_flags;
    road->edge_tbl = road_edge_base + p->road_edge_sel;
    scroll->scroll_speed = p->scroll_speed;

    sprite->lean = p->lean;
    sprite->pitch = p->buggy_pitch_off;      /* the crash script's body bounce */
    sprite->wheel_pos = p->wheel_pos;
    sprite->skid = p->skid;
    sprite->sprite_suppress = (uint16_t)p->skid;
    sprite->crash_disp = p->crash_disp;
    sprite->buggy_draw_flag = p->buggy_draw_flag;
    sprite->speed_raw = p->speed_raw;
    sprite->road_curve = p->road_curve;
    /* Crash/spin script view: the four fields the fg/lower-body draws read but that no owner field
     * used to reach (game_update.c writes each into the flat image; here they alias the same way). */
    sprite->anim_frame = p->anim_frame_sel;                                /* fg frame; byte->word forces hi byte 0x18d0c to 0 (script writes only 0x18d0d) */
    sprite->spin_state = (int8_t)(ev->spin_state >> 8);                    /* the fx<<8 word's hi byte (0x18caa) */
    sprite->spin_reset = ((uint32_t)p->spin_reset << 16) | p->spin_word2;  /* the 0x18cc8 spin longword */
    sprite->collision_lock = p->collision_lock;                           /* lower-body crash suppressor (0x18c84) */

    ground->view = p->ground_view_off;
    objlist->view_flags = p->view_flags;
    objlist->obj_scan_off = p->ground_view_off;

    hud->speed = p->speed;
    hud->time_left = (uint16_t)p->time_left;
    hud->dsp_variant_idx = p->dsp_variant_idx;
    hud->hud_crash_timer = p->hud_crash_timer;

    /* The six HUD scalars EventState OWNS (see game.h ownership contract): the draw's per-frame VIEW,
     * refreshed from the event engine each frame exactly as speed/time are from the physics. */
    hud->crash_lap = (int16_t)ev->crash_lap;
    hud->gauge_blink = ev->gauge_blink;
    hud->gauge_blink_on = ev->gauge_blink_on != 0;
    hud->crash_active = ev->crash_active != 0;
    hud->crash_bars = ev->crash_bars;
    hud->crash_frame = (int16_t)ev->crash_frame;
}
