/* gameplay.c — remaster of the draw_game_objects prefix (recreate's gobj_prefix @0x12ef6..0x12fc0).
 *
 * The deterministic per-frame state advance draw_game_objects runs before any drawing. It writes no
 * framebuffer pixels — it is off-frame game state: the marker-decay slot (records cleared/retired as
 * a roadside marker fades), the road-colour animation counters (which feed the animated colour the
 * palette uses), and the bonus-window flag animation. Transcribed 1:1 from recreate (16-bit wraps
 * mirrored); the flat-image reads/writes become native fields + named arenas (see game.h).
 */
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
