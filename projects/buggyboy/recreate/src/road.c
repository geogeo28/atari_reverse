/* road.c — build_road_geometry @ 0x11f4c.
 *
 * Rebuilds the per-scanline road perspective tables that render_road consumes, from the
 * current leg's segment slopes, the view/leg selector, the road curvature and the horizon.
 * Pure fixed-point table math (no OS calls, no framebuffer): four stages —
 *   1. cumulative slope down the near rows + 12 segments of 4 rows -> road_scanline_tbl
 *   2. perspective integration of the slope table -> road_curve_tbl (filled top-down)
 *   3. curvature spread by road_curve/106 with a fractional carry -> road_curve_tbl (+=)
 *   4. per-row road width from a source table -> road_width_tbl, then horizon clamp.
 *
 * The 68000 works in 16-bit registers throughout, so intermediate results wrap mod 2^16;
 * we mirror that with explicit uint16_t/int16_t rather than native int widths.
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

/* Big-endian typed table access at absolute image addresses. */
static int16_t  rd_i16(const uint8_t *m, uint32_t a) { return (int16_t)be16(m + a); }
static uint16_t rd_u16(const uint8_t *m, uint32_t a) { return be16(m + a); }
static void     wr_i16(uint8_t *m, uint32_t a, uint16_t v) { wr16(m + a, v); }
static int32_t  rd_i32(const uint8_t *m, uint32_t a) { return (int32_t)be32(m + a); }
static void     wr_i32(uint8_t *m, uint32_t a, uint32_t v) { wr32(m + a, v); }

#define NEAR_SEGMENTS   12      /* segment loop count (road_seg_data[1..12]) */
#define ROWS_PER_SEG     4      /* scanline rows emitted per segment */
#define PERSP_SEGMENTS  0x30    /* perspective integration outer count */
#define CURVE_ROWS      0x6a    /* road_curve_tbl length (106) and curve spread denominator */
#define WIDTH_ROWS      0x0e    /* road_width_tbl outer rows (14) */
#define WIDTH_SRC_STRIDE 0x20   /* bytes between width source values */
#define HORIZON_BIAS    0x210   /* added to horizon before dividing */
#define HORIZON_DIV     0x16    /* horizon divisor / clamp bound (22) */

/* Stages 1+2: cumulative slope down road_scanline_tbl. Returns the running accumulator. */
static uint16_t build_scanline_table(uint8_t *m) {
    int16_t seg0 = rd_i16(m, A_road_seg_data);
    uint16_t acc = 0;
    uint16_t n = (uint16_t)(6 - rd_u16(m, A_view_flags)) >> 1;
    wr_i16(m, A_road_seg_head, (uint16_t)seg0);

    uint32_t sl = A_road_scanline_tbl;
    do {                                    /* near rows: constant first-segment slope */
        acc = (uint16_t)(seg0 + acc);
        wr_i16(m, sl, acc); sl += 2;
    } while (n-- != 0);

    uint32_t seg = A_road_seg_data + 2;     /* road_seg_data[1..12] */
    for (int s = 0; s < NEAR_SEGMENTS; s++, seg += 2, sl += 2 * ROWS_PER_SEG) {
        int16_t v = rd_i16(m, seg);
        wr_i16(m, sl,     (uint16_t)(v + acc));   /* row 0 uses the pre-update accumulator */
        acc = (uint16_t)(v + v + acc);
        wr_i16(m, sl + 2, acc);
        acc = (uint16_t)(v + acc);
        wr_i16(m, sl + 4, acc);
        acc = (uint16_t)(v + acc);
        wr_i16(m, sl + 6, acc);
    }
    return acc;
}

/* Stage 2: integrate the slope table into road_curve_tbl, filled downward from its end.
 * A 4-bit fractional accumulator (frac) carries sub-unit slope between rows. */
static void integrate_perspective(uint8_t *m) {
    uint32_t out = A_road_curve_tbl_end;    /* writes pre-decrement, so first write is -4 */
    uint16_t acc = 0, frac = 0;
    uint32_t row = A_road_scanline_tbl;
    uint32_t seg = A_persp_seg_tbl;

    for (int outer = PERSP_SEGMENTS; outer >= 0; outer--, row += 2, seg += 1) {
        int8_t run = (int8_t)m[seg];
        if (run < 0) continue;              /* negative run length: skip this row */

        int16_t slope = rd_i16(m, row);
        if (slope < 0) {
            uint16_t mag = (uint16_t)-slope;
            for (int k = run; k >= 0; k--) {
                int16_t step = (int16_t)(mag + (frac & 0xfff0)) >> 4;
                acc = (uint16_t)((int16_t)acc - step);
                frac = (uint16_t)((mag & 0xf) + (frac & 0xf));
                out -= 4; wr_i32(m, out, acc);
            }
        } else {
            for (int k = run; k >= 0; k--) {
                int16_t step = (int16_t)((uint16_t)slope + (frac & 0xfff0)) >> 4;
                acc = (uint16_t)(step + (int16_t)acc);
                frac = (uint16_t)((slope & 0xf) + (frac & 0xf));
                out -= 4; wr_i32(m, out, acc);
            }
        }
    }
}

/* Stage 3: spread the road curvature across road_curve_tbl (106 rows), += onto each entry.
 * Distributes road_curve/106 per row with a remainder carry, sign preserved. */
static void spread_curvature(uint8_t *m) {
    int16_t curve = rd_i16(m, A_road_curve);
    uint16_t acc = 0, carry = CURVE_ROWS / 2;   /* 0x35 */
    uint32_t tbl = A_road_curve_tbl;
    uint16_t mag = (uint16_t)(curve < 0 ? -curve : curve);
    uint16_t quot = mag / CURVE_ROWS, rem = mag % CURVE_ROWS;

    for (int r = CURVE_ROWS - 1; r >= 0; r--, tbl += 4) {
        uint16_t v = curve < 0 ? (uint16_t)((int16_t)acc - quot)
                               : (uint16_t)((int16_t)acc + quot);
        carry = (uint16_t)(rem + carry);
        if (carry > CURVE_ROWS - 1) {           /* 0x69 */
            carry -= CURVE_ROWS;
            v = curve < 0 ? (uint16_t)(v - 1) : (uint16_t)(v + 1);
        }
        acc = v;
        wr_i32(m, tbl, (uint32_t)acc + (uint32_t)rd_i32(m, tbl));
    }
}

/* Stage 4a: fill road_width_tbl by repeating each source width for a run count. */
static void build_width_table(uint8_t *m) {
    uint32_t src = A_road_width_src;
    uint32_t dst = A_road_width_tbl;
    uint32_t cnt = A_width_count_tbl + (int16_t)((rd_u16(m, A_view_flags) & 6) << 3);

    for (int row = 0; row < WIDTH_ROWS; row++, src += WIDTH_SRC_STRIDE, cnt += 1) {
        int runs = m[cnt];
        uint16_t width = rd_u16(m, src);
        for (int k = runs; k >= 0; k--, dst += 4) wr_i16(m, dst, width);
    }
}

/* Stage 4b: clamp the horizon to a scanline row and record its parity. */
static void set_horizon(uint8_t *m) {
    int16_t q = (int16_t)((int16_t)(rd_i16(m, A_horizon) + HORIZON_BIAS) / HORIZON_DIV);
    uint16_t half = (uint16_t)q >> 1;
    if ((int16_t)half < 0) half = 0;
    else if ((int16_t)(half - HORIZON_DIV) >= 0) half = HORIZON_DIV;
    wr_i16(m, A_horizon_row, (uint16_t)((HORIZON_DIV - half) * 2));
    wr_i16(m, A_horizon_frac, (uint16_t)((uint16_t)q & 1));
}

void g_build_road_geometry(uint8_t *image) {
    build_scanline_table(image);
    integrate_perspective(image);
    spread_curvature(image);
    build_width_table(image);
    set_horizon(image);
}