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
static int16_t  rd_i16(const uint8_t *image, uint32_t addr) { return (int16_t)be16(image + addr); }
static uint16_t rd_u16(const uint8_t *image, uint32_t addr) { return be16(image + addr); }
static void     wr_i16(uint8_t *image, uint32_t addr, uint16_t value) { wr16(image + addr, value); }
static int32_t  rd_i32(const uint8_t *image, uint32_t addr) { return (int32_t)be32(image + addr); }
static void     wr_i32(uint8_t *image, uint32_t addr, uint32_t value) { wr32(image + addr, value); }

#define NEAR_SEGMENTS   12      /* segment loop count (road_seg_data[1..12]) */
#define ROWS_PER_SEG     4      /* scanline rows emitted per segment */
#define PERSP_SEGMENTS  0x30    /* perspective integration outer count */
#define CURVE_ROWS      0x6a    /* road_curve_tbl length (106) and curve spread denominator */
#define WIDTH_ROWS      0x0e    /* road_width_tbl outer rows (14) */
#define WIDTH_SRC_STRIDE 0x20   /* bytes between width source values */
#define HORIZON_BIAS    0x210   /* added to horizon before dividing */
#define HORIZON_DIV     0x16    /* horizon divisor / clamp bound (22) */

/* Stages 1+2: cumulative slope down road_scanline_tbl. Returns the running accumulator. */
static uint16_t build_scanline_table(uint8_t *image) {
    int16_t seg0 = rd_i16(image, A_road_seg_data);
    uint16_t acc = 0;
    uint16_t near_rows = (uint16_t)(6 - rd_u16(image, A_view_flags)) >> 1;
    wr_i16(image, A_road_seg_head, (uint16_t)seg0);

    uint32_t scan_ptr = A_road_scanline_tbl;
    do {                                    /* near rows: constant first-segment slope */
        acc = (uint16_t)(seg0 + acc);
        wr_i16(image, scan_ptr, acc); scan_ptr += 2;
    } while (near_rows-- != 0);

    uint32_t seg_ptr = A_road_seg_data + 2;     /* road_seg_data[1..12] */
    for (int seg_i = 0; seg_i < NEAR_SEGMENTS; seg_i++, seg_ptr += 2, scan_ptr += 2 * ROWS_PER_SEG) {
        int16_t slope = rd_i16(image, seg_ptr);
        wr_i16(image, scan_ptr,     (uint16_t)(slope + acc));   /* row 0 uses pre-update accumulator */
        acc = (uint16_t)(slope + slope + acc);
        wr_i16(image, scan_ptr + 2, acc);
        acc = (uint16_t)(slope + acc);
        wr_i16(image, scan_ptr + 4, acc);
        acc = (uint16_t)(slope + acc);
        wr_i16(image, scan_ptr + 6, acc);
    }
    return acc;
}

/* Stage 2: integrate the slope table into road_curve_tbl, filled downward from its end.
 * A 4-bit fractional accumulator (frac) carries sub-unit slope between rows. */
static void integrate_perspective(uint8_t *image) {
    uint32_t curve_ptr = A_road_curve_tbl_end;  /* writes pre-decrement, so first write is -4 */
    uint16_t acc = 0, frac = 0;
    uint32_t slope_ptr = A_road_scanline_tbl;
    uint32_t run_ptr = A_persp_seg_tbl;

    for (int remaining = PERSP_SEGMENTS; remaining >= 0; remaining--, slope_ptr += 2, run_ptr += 1) {
        int8_t run = (int8_t)image[run_ptr];
        if (run < 0) continue;              /* negative run length: skip this row */

        int16_t slope = rd_i16(image, slope_ptr);
        if (slope < 0) {
            uint16_t magnitude = (uint16_t)-slope;
            for (int step_i = run; step_i >= 0; step_i--) {
                int16_t step = (int16_t)(magnitude + (frac & 0xfff0)) >> 4;
                acc = (uint16_t)((int16_t)acc - step);
                frac = (uint16_t)((magnitude & 0xf) + (frac & 0xf));
                curve_ptr -= 4; wr_i32(image, curve_ptr, acc);
            }
        } else {
            for (int step_i = run; step_i >= 0; step_i--) {
                int16_t step = (int16_t)((uint16_t)slope + (frac & 0xfff0)) >> 4;
                acc = (uint16_t)(step + (int16_t)acc);
                frac = (uint16_t)((slope & 0xf) + (frac & 0xf));
                curve_ptr -= 4; wr_i32(image, curve_ptr, acc);
            }
        }
    }
}

/* Stage 3: spread the road curvature across road_curve_tbl (106 rows), += onto each entry.
 * Distributes road_curve/106 per row with a remainder carry, sign preserved. */
static void spread_curvature(uint8_t *image) {
    int16_t curve = rd_i16(image, A_road_curve);
    uint16_t acc = 0, carry = CURVE_ROWS / 2;   /* 0x35 */
    uint32_t curve_ptr = A_road_curve_tbl;
    uint16_t magnitude = (uint16_t)(curve < 0 ? -curve : curve);
    uint16_t quotient = magnitude / CURVE_ROWS, remainder = magnitude % CURVE_ROWS;

    for (int row = CURVE_ROWS - 1; row >= 0; row--, curve_ptr += 4) {
        uint16_t value = curve < 0 ? (uint16_t)((int16_t)acc - quotient)
                                   : (uint16_t)((int16_t)acc + quotient);
        carry = (uint16_t)(remainder + carry);
        if (carry > CURVE_ROWS - 1) {           /* 0x69 */
            carry -= CURVE_ROWS;
            value = curve < 0 ? (uint16_t)(value - 1) : (uint16_t)(value + 1);
        }
        acc = value;
        wr_i32(image, curve_ptr, (uint32_t)acc + (uint32_t)rd_i32(image, curve_ptr));
    }
}

/* Stage 4a: fill road_width_tbl by repeating each source width for a run count. */
static void build_width_table(uint8_t *image) {
    uint32_t src_ptr = A_road_width_src;
    uint32_t dst_ptr = A_road_width_tbl;
    uint32_t count_ptr = A_width_count_tbl + (int16_t)((rd_u16(image, A_view_flags) & 6) << 3);

    for (int row = 0; row < WIDTH_ROWS; row++, src_ptr += WIDTH_SRC_STRIDE, count_ptr += 1) {
        int runs = image[count_ptr];
        uint16_t width = rd_u16(image, src_ptr);
        for (int run_i = runs; run_i >= 0; run_i--, dst_ptr += 4) wr_i16(image, dst_ptr, width);
    }
}

/* Stage 4b: clamp the horizon to a scanline row and record its parity. */
static void set_horizon(uint8_t *image) {
    int16_t quotient = (int16_t)((int16_t)(rd_i16(image, A_horizon) + HORIZON_BIAS) / HORIZON_DIV);
    uint16_t half = (uint16_t)quotient >> 1;
    if ((int16_t)half < 0) half = 0;
    else if ((int16_t)(half - HORIZON_DIV) >= 0) half = HORIZON_DIV;
    wr_i16(image, A_horizon_row, (uint16_t)((HORIZON_DIV - half) * 2));
    wr_i16(image, A_horizon_frac, (uint16_t)((uint16_t)quotient & 1));
}

void g_build_road_geometry(uint8_t *image) {
    build_scanline_table(image);
    integrate_perspective(image);
    spread_curvature(image);
    build_width_table(image);
    set_horizon(image);
}