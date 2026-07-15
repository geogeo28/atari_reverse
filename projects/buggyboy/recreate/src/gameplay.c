/* gameplay.c — per-leg / gameplay orchestrators.
 *
 * init_leg @ 0x104b8 — resets all per-leg state at the start of a leg: clears the live-state block,
 * seeds the scalar defaults (lean/wheel/rpm/time/view), rebuilds the checkpoint banner
 * (draw_checkpoint_anim) and the road-scroll offset (set_screen_offset), lays out the HUD bonus-time
 * and score strings, clears the road-segment and object-marker tables, then unpacks this leg's
 * roadside-object marker records and the first object-display record from buf_a.
 *
 * A per-leg initializer: scalar writes + table copies/clears + two buf_a-driven unpack loops. The
 * 68000 works in 16-bit registers; word writes/compares are mirrored with uint16_t/int16_t. (The
 * disassembler misprints the `leg << 13` as `and.w #0x2000` — it is really `mulu.w #0x2000,d0`.)
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

/* ---- phase 1: clear the live per-leg state block ---- */
#define INIT_CLEAR_BASE   0x18c42   /* first word of the cleared block (== A_input_prev) */
#define INIT_CLEAR_WORDS  0x6d      /* dbf #0x6c -> 109 words */

/* ---- phase 2: scalar defaults ---- */
#define VIEW_FLAGS_INIT   0x000201ba  /* one long: view_flags=2 (0x18c56) + obj_scan_off=0x1ba (0x18c58) */
#define LEAN_STATE_INIT   2           /* 0x18cc2 */
#define LEAN_X10_INIT     0xa         /* 0x18cc4 */
#define BUGGY_VARIANT_INIT 8          /* 0x18cc6 */
#define WHEEL_POS_INIT    2           /* 0x18cc0 */
#define ROAD_EDGE_SEL_INIT 0xc0       /* 0x18c5a */
#define TIME_LEFT_INIT    0x46        /* 0x18cfc */
#define ENGINE_RPM_INIT   0xf         /* 0x18c8c */
#define LEAN_FRAME_INIT   8           /* 0x18d12 */
#define LEG_FLAGS_C90_INIT 0x00440002 /* 0x18c90 (long) */

/* ---- phase 4: HUD bonus-time strings ("/2000/" ...) copied from const image data ---- */
#define LEGTIME_SRC       0x18136   /* leg-0 source; leg != 0 starts LEGTIME_LEG_OFF further in */
#define LEGTIME_LEG_OFF   0x1e
#define LEGTIME_DST       0x1818c
#define LEGTIME_COUNT     5         /* dbf #4 */
#define LEGTIME_COPY      6         /* bytes copied per row (long + word) */
#define LEGTIME_DST_STRIDE 0xe      /* copied 6 + skipped 8 */

/* ---- phase 5/6: score string + BCD reset ---- */
#define SCORE_TMPL_SRC    0x181fc   /* "/1______0" HUD score template */
#define SCORE_TMPL_BYTES  10
#define SCORE_BCD_INIT    0x30303030  /* "0000" at A_score_bcd */
#define SCORE_CNT_INIT    0x3030      /* "00" at A_score_counter */

/* ---- phase 8/9: table clears ---- */
#define ROAD_SEG_CLR_LONGS 8        /* road_seg_data (0x18d1c): dbf #7 longs */
#define OBJ_MARKERS_CLR_LONGS 0x70  /* obj_markers (0x18d3c): dbf #0x37 x 2 longs */

/* ---- phase 10: roadside-object marker records unpacked from buf_a ---- */
#define MARKER_SRC_BASE   0x5ce0    /* buf_a + this + leg*MARKER_LEG_STRIDE */
#define MARKER_LEG_STRIDE 0x2000
#define MARKER_RECORDS    14        /* dbf #0xd */
#define MARKER_SRC_STRIDE 8         /* a2 += 8 per record */
#define MARKER_REC_STRIDE 0x20      /* a3 += 0x20 per record */
#define MARKER_MASK_BITS  0xe       /* dbf #0xe -> bits 0xe..0 of the select mask */
#define MARKER_FLAG_OFF   0x1e      /* type/flag byte within the record */
#define MARKER_FLAG_MASK  0x60      /* if neither bit set, clear bit7 */

/* ---- phase 11: first object-display record ---- */
#define OBJDISP_SEL_OFF   0x50      /* buf_a + this + leg*0x20 (leg << 5): selector byte */
#define OBJDISP_TBL_OFF   0xf2      /* buf_a + this + (selector << 4): the record source */
#define OBJDISP_DST       0x17fb0   /* record head; a trailing word lands at OBJDISP_DST - 4 */

void g_init_leg(uint8_t *image) {
    /* Phase 1: clear the live per-leg state block. */
    for (int i = 0; i < INIT_CLEAR_WORDS; i++)
        wr16(image + INIT_CLEAR_BASE + i * 2, 0);

    /* Phase 2: scalar defaults. */
    wr32(image + A_view_flags, VIEW_FLAGS_INIT);
    wr16(image + A_lean_state, LEAN_STATE_INIT);
    wr16(image + A_buggy_lean_x10, LEAN_X10_INIT);
    wr16(image + A_buggy_variant, BUGGY_VARIANT_INIT);
    wr16(image + A_wheel_pos, WHEEL_POS_INIT);
    wr16(image + A_road_edge_sel, ROAD_EDGE_SEL_INIT);
    wr16(image + A_time_left, TIME_LEFT_INIT);
    wr16(image + A_engine_rpm, ENGINE_RPM_INIT);
    wr16(image + A_lean_frame, LEAN_FRAME_INIT);
    wr32(image + A_leg_flags_c90, LEG_FLAGS_C90_INIT);

    /* Phase 3: rebuild the checkpoint banner. */
    g_draw_checkpoint_anim(image);

    /* Phase 4: HUD bonus-time strings (shorter set from leg 1 on). */
    uint32_t src = LEGTIME_SRC + (be16(image + A_leg_index) != 0 ? LEGTIME_LEG_OFF : 0);
    uint32_t dst = LEGTIME_DST;
    for (int i = 0; i < LEGTIME_COUNT; i++, src += LEGTIME_COPY, dst += LEGTIME_DST_STRIDE)
        for (int b = 0; b < LEGTIME_COPY; b++)
            image[dst + b] = image[src + b];

    /* Phase 5/6: score string template + BCD reset. */
    for (int b = 0; b < SCORE_TMPL_BYTES; b++)
        image[A_score_str + b] = image[SCORE_TMPL_SRC + b];
    wr32(image + A_score_bcd, SCORE_BCD_INIT);
    wr16(image + A_score_counter, SCORE_CNT_INIT);

    /* Phase 7: this frame's road-scroll offset. */
    g_set_screen_offset(image);

    /* Phase 8/9: clear the road-segment and object-marker tables. */
    for (int i = 0; i < ROAD_SEG_CLR_LONGS; i++)
        wr32(image + A_road_seg_data + i * 4, 0);
    for (int i = 0; i < OBJ_MARKERS_CLR_LONGS; i++)
        wr32(image + A_obj_markers + i * 4, 0);

    uint32_t buf_a = be32(image + A_buf_a);
    uint16_t leg = be16(image + A_leg_index);

    /* Phase 10: unpack this leg's 14 roadside-object marker records. Each source record has a
     * 15-bit select mask; a set bit copies the next source byte into the record at a 2-byte stride.
     * The type word seeds the record's flag byte with sign/priority cleanup. */
    uint32_t rec_src = buf_a + MARKER_SRC_BASE + (uint32_t)leg * MARKER_LEG_STRIDE;
    uint32_t rec = A_obj_markers;
    for (int r = 0; r < MARKER_RECORDS; r++, rec_src += MARKER_SRC_STRIDE, rec += MARKER_REC_STRIDE) {
        int16_t type = (int16_t)be16(image + rec_src + 6);
        uint16_t mask = be16(image + rec_src);
        uint32_t s = rec_src + 3;                 /* mask word (+0,+1) then a skipped byte (+2) */
        uint32_t d = rec + 1;
        for (int bit = MARKER_MASK_BITS; bit >= 0; bit--, d += 2) {
            if (mask & (1u << bit)) image[d] = image[s++];
        }
        uint32_t flag = rec + MARKER_FLAG_OFF;
        wr16(image + flag, (uint16_t)type);
        if (type >= 0) image[flag] = 0;
        if ((image[flag] & MARKER_FLAG_MASK) == 0) image[flag] &= 0x7f;
    }

    /* Phase 11: first object-display record, selected from buf_a by a per-leg index. */
    uint8_t sel = image[buf_a + OBJDISP_SEL_OFF + (uint16_t)(leg << 5)];
    uint32_t d11 = buf_a + OBJDISP_TBL_OFF + ((uint16_t)sel << 4);
    wr16(image + OBJDISP_DST,     be16(image + d11));     d11 += 2;
    wr32(image + OBJDISP_DST + 2, be32(image + d11));     d11 += 4;
    wr32(image + OBJDISP_DST + 6, be32(image + d11));     d11 += 4;
    wr16(image + OBJDISP_DST - 4, be16(image + d11));     d11 += 2;   /* move.w (a3)+,0xa(a0), a0 rewound 0x18 */
    wr16(image + A_obj_shade, (uint16_t)(be16(image + d11) - 2));
}
