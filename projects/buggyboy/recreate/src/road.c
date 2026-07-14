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
#include "draw.h"

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
/* set_screen_offset @0x10300 — pick this frame's road-scroll offset into buf_c. The scroll frame
 * (0-15) indexes the leg's 16-byte scroll table at buf_a + leg_index*SCROLL_TABLE_STRIDE; the
 * selected byte times SCROLL_BAND_BYTES (one 40-scanline band) is the buf_c offset that
 * blit_road_scroll reads from screen_offset. */
#define SCROLL_TABLE_STRIDE  0x10     /* per-leg scroll table stride in buf_a (leg_index << 4) */
#define SCROLL_BAND_BYTES    0x1900   /* one scroll step = 40 scanlines; table byte * this */

void g_set_screen_offset(uint8_t *image) {
    uint32_t buf_a = be32(image + A_buf_a);
    uint16_t leg = be16(image + A_leg_index);
    uint16_t frame = be16(image + A_scroll_frame);
    uint32_t entry = buf_a + sign_ext16((uint16_t)(leg << 4)) + sign_ext16(frame);   /* adda.w x2 */
    uint8_t step = image[entry];
    wr16(image + A_screen_offset, (uint16_t)(step * SCROLL_BAND_BYTES));
}

/* wait_vbl_set_offset @0x102ee — wait 51 vblanks (XBIOS Vsync, hardware only) then fall into
 * set_screen_offset. The Vsync loop has no image effect. */
void g_wait_vbl_set_offset(uint8_t *image) {
    g_set_screen_offset(image);
}

/* blit_road_scroll @0x10326 — horizontal fine-scroll of the double-wide road playfield (in buf_c)
 * onto the visible screen's road band. Advance hscroll_pos by road_seg_head*scroll_speed, wrapped
 * into [0, SCROLL_WRAP); its low nibble is the fine bit shift and the rest a coarse byte offset into
 * the source row. Each of ROAD_ROWS scanlines blits ROAD_COLS 4-plane 16-pixel columns: every column
 * pairs its word with the next column's word (8 bytes ahead) and rotates left by the fine shift
 * (rol.l), so pixels slide smoothly. Once the scroll passes EDGE_THRESH the row's tail wraps back to
 * the start of the source row — a masked seam column then full wrap columns. Finally the area above
 * the band (screen[0..OBJ_ROAD_START_OFF)) is filled with the 0xffff0000 plane pattern. */
#define ROAD_PLANES     4          /* interleaved bitplanes per 16-pixel column */
#define ROAD_COL_BYTES  8          /* ROAD_PLANES words: one 16-pixel, 4-plane column */
#define ROAD_ROWS       0x14       /* scanlines blitted (d4 = 0x13) */
#define ROAD_COLS       0x14       /* columns per scanline (160-byte row) */
#define SCROLL_WRAP     0x280      /* hscroll_pos wraps modulo this (double screen width) */
#define SRC_ROW_STRIDE  0x140      /* source row pitch in buf_c (double-wide playfield) */
#define EDGE_THRESH     0x140      /* hscroll_pos >= this starts wrapping the row tail */
#define SEAM_MASK_BASE  0xffff     /* seam mask = this << shift (moveq #$ff sign-extends, then lsl.w) */
#define ROAD_TOP_FILL   0xffff0000u /* plane pattern filling the area above the road band */

/* Rotate a 32-bit value left by s (0..31); s==0 is identity (avoids the >>32 UB). */
static uint32_t rol32(uint32_t v, unsigned s) {
    return s ? ((v << s) | (v >> (32 - s))) : v;
}

/* Fine-shift one 4-plane, 16-pixel column: each plane word is paired with the next column's word
 * (ROAD_COL_BYTES ahead) and rotated left by shift; the low word is written to dst. */
static void scroll_column(uint8_t *image, uint32_t dst, uint32_t src, unsigned shift) {
    for (int p = 0; p < ROAD_PLANES; p++) {
        uint32_t pair = ((uint32_t)be16(image + src + ROAD_COL_BYTES + p * 2) << 16)
                        | be16(image + src + p * 2);
        wr16(image + dst + p * 2, (uint16_t)rol32(pair, shift));
    }
}

void g_blit_road_scroll(uint8_t *image) {
    uint32_t screen = draw_buffer(image);

    uint16_t delta = (uint16_t)((int16_t)be16(image + A_road_seg_head)
                                * (int16_t)be16(image + A_scroll_speed));   /* muls.w, low word */
    wr16(image + A_hscroll_step2, (uint16_t)(delta * 2));

    uint16_t h = (uint16_t)(be16(image + A_hscroll_pos) + delta);
    if ((int16_t)h < 0) h += SCROLL_WRAP;
    else if ((int16_t)(h - SCROLL_WRAP) >= 0) h -= SCROLL_WRAP;
    wr16(image + A_hscroll_pos, h);

    unsigned shift = h & 0xf;
    uint16_t coarse = (uint16_t)(((int16_t)h >> 1) & 0xfff8);               /* asr.w #1, andi.w */
    uint32_t wrap_base = be32(image + A_buf_c) + sign_ext16(be16(image + A_screen_offset));
    uint32_t src_base = wrap_base + sign_ext16(coarse);
    uint32_t dst_base = screen + OBJ_ROAD_START_OFF;

    /* When the scroll passes EDGE_THRESH, the last `edge` columns wrap to the source row start. */
    int edge = -1;
    unsigned main_cols = ROAD_COLS;
    if ((int16_t)(h - EDGE_THRESH) >= 0) {
        edge = (uint16_t)(h - EDGE_THRESH) >> 4;
        main_cols = ROAD_COLS - edge;
    }

    for (unsigned row = 0; row < ROAD_ROWS; row++) {
        uint32_t src = src_base + row * SRC_ROW_STRIDE;
        uint32_t wrap = wrap_base + row * SRC_ROW_STRIDE;
        uint32_t dst = dst_base + row * ROW_STRIDE;

        for (unsigned c = 0; c < main_cols; c++)
            scroll_column(image, dst + c * ROAD_COL_BYTES, src + c * ROAD_COL_BYTES, shift);

        if (edge >= 0) {
            /* Seam: mask the last main column, then OR in the wrap column's fractional pixels. */
            uint32_t seam = dst + (main_cols - 1) * ROAD_COL_BYTES;
            uint16_t mask = (uint16_t)(SEAM_MASK_BASE << shift);
            for (int p = 0; p < ROAD_PLANES; p++) {
                uint16_t frac = (uint16_t)rol32((uint32_t)be16(image + wrap + p * 2) << 16, shift);
                wr16(image + seam + p * 2, (uint16_t)((be16(image + seam + p * 2) & mask) | frac));
            }
            for (int c = 0; c < edge; c++)
                scroll_column(image, dst + (main_cols + c) * ROAD_COL_BYTES, wrap + c * ROAD_COL_BYTES, shift);
        }
    }

    for (uint32_t off = 0; off < OBJ_ROAD_START_OFF; off += 4)
        wr32(image + screen + off, ROAD_TOP_FILL);
}
