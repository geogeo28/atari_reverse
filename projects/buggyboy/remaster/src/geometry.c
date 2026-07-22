/* geometry.c — remaster of build_road_geometry (recreate's g_build_road_geometry @0x11f4c).
 *
 * Rebuilds the per-scanline control-long table render_road consumes, from the current pose: the leg's
 * segment slopes, the view/leg selector, the road curvature (steering) and the horizon. Pure
 * fixed-point table math — no OS calls, no framebuffer — in four stages:
 *   1. cumulative slope down the near rows + 12 segments of 4 rows        -> scanline scratch
 *   2. perspective integration of that slope table (filled bottom-up)     -> ctrl (as longs)
 *   3. curvature spread by curve/106 with a fractional carry (+= onto it) -> ctrl (as longs)
 *   4. per-band control word stamped in from the course ring                -> ctrl (as shorts)
 * then a horizon clamp. Stages 3/4 write the SAME ctrl region recreate aliases as road_curve_tbl and
 * road_width_tbl (stage 4's shorts overwrite the high word of every long from RM_CTRL_WIDTH_OFF on —
 * the flag half, not the width; see build_width_table), so ctrl ends up exactly the control-long
 * stream render_road reads.
 *
 * Faithful port of recreate/src/road.c (build_scanline_table / integrate_perspective /
 * spread_curvature / build_width_table / set_horizon), verified byte-for-byte against the Musashi
 * oracle. recreate's flat image + absolute-address table access becomes native pose fields plus two
 * ST-byte buffers (ctrl, scanline) accessed through st.h. The 68000 works in 16-bit registers
 * throughout, so intermediate results wrap mod 2^16 — mirrored with explicit uint16_t/int16_t.
 */
#include "game.h"
#include "st.h"

#define NEAR_SEGMENTS    12      /* segment loop count (seg_data[1..12]) */
#define ROWS_PER_SEG      4      /* scanline rows emitted per segment */
#define PERSP_SEGMENTS   0x30    /* perspective integration outer count */
#define CURVE_ROWS       0x6a    /* ctrl length in longs (106) and curve-spread denominator */
#define HORIZON_BIAS    0x210    /* added to horizon before dividing */
#define HORIZON_DIV      RM_HORIZON_DIV   /* horizon divisor / clamp bound (0x16 == 22); game.h owns it */
#define HORIZON_OFF     0x162    /* recreate's A_horizon (0x1905e) lies INSIDE ctrl: the low word of
                                  * control long #88. So the horizon set_horizon clamps is not an
                                  * independent input — it's the value integrate/spread just wrote. */

/* Stage 1: cumulative slope down the scanline scratch (near rows at the first-segment slope, then 12
 * segments of 4 rows). Returns the running accumulator (unused by the caller, as in recreate). */
static uint16_t build_scanline_table(RoadPose *pose, uint8_t *scanline) {
    int16_t seg0 = pose->seg_data[0];
    uint16_t acc = 0;
    uint16_t near_rows = (uint16_t)(6 - pose->view_flags) >> 1;
    pose->seg_head = (int16_t)(uint16_t)seg0;

    uint32_t scan = 0;
    do {                                    /* near rows: constant first-segment slope */
        acc = (uint16_t)(seg0 + acc);
        wr16(scanline + scan, acc); scan += 2;
    } while (near_rows-- != 0);

    for (int seg_i = 0; seg_i < NEAR_SEGMENTS; seg_i++, scan += 2 * ROWS_PER_SEG) {
        int16_t slope = pose->seg_data[1 + seg_i];
        wr16(scanline + scan,     (uint16_t)(slope + acc));     /* row 0 uses the pre-update accumulator */
        acc = (uint16_t)(slope + slope + acc);
        wr16(scanline + scan + 2, acc);
        acc = (uint16_t)(slope + acc);
        wr16(scanline + scan + 4, acc);
        acc = (uint16_t)(slope + acc);
        wr16(scanline + scan + 6, acc);
    }
    return acc;
}

/* Stage 2: integrate the slope table into ctrl, filled downward from its end. A 4-bit fractional
 * accumulator (frac) carries sub-unit slope between rows. */
static void integrate_perspective(const uint8_t *scanline, const int8_t *persp_seg, uint8_t *ctrl) {
    uint32_t curve = RM_CTRL_BYTES;         /* writes pre-decrement, so the first write is -4 */
    uint16_t acc = 0, frac = 0;
    uint32_t slope_off = 0, run_off = 0;

    for (int remaining = PERSP_SEGMENTS; remaining >= 0; remaining--, slope_off += 2, run_off += 1) {
        int8_t run = persp_seg[run_off];
        if (run < 0) continue;              /* negative run length: skip this row */

        int16_t slope = (int16_t)be16(scanline + slope_off);
        if (slope < 0) {
            uint16_t magnitude = (uint16_t)-slope;
            for (int step_i = run; step_i >= 0; step_i--) {
                int16_t step = (int16_t)(magnitude + (frac & 0xfff0)) >> 4;
                acc = (uint16_t)((int16_t)acc - step);
                frac = (uint16_t)((magnitude & 0xf) + (frac & 0xf));
                curve -= 4; wr32(ctrl + curve, acc);
            }
        } else {
            for (int step_i = run; step_i >= 0; step_i--) {
                int16_t step = (int16_t)((uint16_t)slope + (frac & 0xfff0)) >> 4;
                acc = (uint16_t)(step + (int16_t)acc);
                frac = (uint16_t)((slope & 0xf) + (frac & 0xf));
                curve -= 4; wr32(ctrl + curve, acc);
            }
        }
    }
}

/* Stage 3: spread the road curvature across ctrl (106 longs), += onto each entry. Distributes
 * curve/106 per row with a remainder carry, sign preserved. */
static void spread_curvature(int16_t curve, uint8_t *ctrl) {
    uint16_t acc = 0, carry = CURVE_ROWS / 2;   /* 0x35 */
    uint32_t cp = 0;
    uint16_t magnitude = (uint16_t)(curve < 0 ? -curve : curve);
    uint16_t quotient = magnitude / CURVE_ROWS, remainder = magnitude % CURVE_ROWS;

    for (int row = CURVE_ROWS - 1; row >= 0; row--, cp += 4) {
        uint16_t value = curve < 0 ? (uint16_t)((int16_t)acc - quotient)
                                   : (uint16_t)((int16_t)acc + quotient);
        carry = (uint16_t)(remainder + carry);
        if (carry > CURVE_ROWS - 1) {           /* 0x69 */
            carry -= CURVE_ROWS;
            value = curve < 0 ? (uint16_t)(value - 1) : (uint16_t)(value + 1);
        }
        acc = value;
        wr32(ctrl + cp, (uint32_t)acc + be32(ctrl + cp));
    }
}

/* Stage 4a: stamp each ring band's control word across the scanlines it covers (a run count per
 * band). Writes at RM_CTRL_WIDTH_OFF, stride 4 — the HIGH word of each control long, i.e. the flag
 * half: render_road's blit-variant bits and the EDGE_* shoulder flags section 10 reads back out.
 * (The road half-width is the control long's LOW word, from stages 2/3 — despite the "width" in the
 * original's names for this table. See CourseRow in game.h.) One ring band per row, FARTHEST first:
 * band 0 is the one the course advance just refilled. */
static void build_width_table(uint16_t view_flags, const CourseRing *ring, const uint8_t *width_count, uint8_t *ctrl) {
    uint32_t dst = RM_CTRL_WIDTH_OFF;
    uint32_t count = (uint32_t)(int16_t)((view_flags & 6) << 3);

    for (int band = 0; band < RM_RING_ROWS; band++, count += 1) {
        int runs = width_count[count];
        uint16_t control = ring->row[band].marker;
        for (int run_i = runs; run_i >= 0; run_i--, dst += 4) wr16(ctrl + dst, control);
    }
}

/* Stage 4b: clamp the horizon to a scanline row and record its parity. The horizon it reads is the
 * value stages 2/3 wrote into ctrl (see HORIZON_OFF), not a separate input. */
static void set_horizon(const uint8_t *ctrl, RoadPose *pose) {
    int16_t horizon = (int16_t)be16(ctrl + HORIZON_OFF);
    int16_t quotient = (int16_t)((int16_t)(horizon + HORIZON_BIAS) / HORIZON_DIV);
    uint16_t half = (uint16_t)quotient >> 1;
    if ((int16_t)half < 0) half = 0;
    else if ((int16_t)(half - HORIZON_DIV) >= 0) half = HORIZON_DIV;
    pose->horizon_row = (int16_t)(uint16_t)((HORIZON_DIV - half) * 2);
    pose->horizon_frac = (int16_t)(uint16_t)((uint16_t)quotient & 1);
}

void rm_build_road_geometry(RoadPose *pose, const RoadSource *src, const CourseRing *ring,
                            uint8_t *ctrl, uint8_t *scanline) {
    build_scanline_table(pose, scanline);
    integrate_perspective(scanline, src->persp_seg, ctrl);
    spread_curvature(pose->curve, ctrl);
    build_width_table(pose->view_flags, ring, src->width_count, ctrl);
    set_horizon(ctrl, pose);
}
