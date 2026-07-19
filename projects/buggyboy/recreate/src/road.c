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
#include "road_bands.h"

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
BB_WEAK void g_wait_vbl_set_offset(uint8_t *image) {
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

/* draw_ground @0x10ff2 — fill the ground/horizon band below the road. Scans up to
 * GROUND_SCAN_ENTRIES scanline descriptors (A_ground_scan_tbl, stride GROUND_SCAN_STRIDE) for a
 * marker byte at +3: 0x1a draws a horizon colour gradient (a band record picks 1-3 solid-colour
 * scanlines), 0x1c a solid ground fill (1 scanline, or 2 for the nearest entry); any other byte
 * advances. The band's screen offset comes from GROUND_COL_OFFSETS indexed by the entry and the
 * view column (ground_view_off). A6 = draw buffer. */
#define GROUND_SCAN_ENTRIES   13
#define GROUND_SCAN_STRIDE     0x20
#define GROUND_MARK_GRADIENT   0x1a
#define GROUND_MARK_SOLID      0x1c
#define GROUND_COL_OFFSETS     0x16a6e   /* per-entry buffer offset words, stride GROUND_COL_STRIDE, + view col */
#define GROUND_COL_STRIDE      0x22
#define GROUND_BAND_RECORDS    0x172ea   /* 0x1a records: [bands-1, backup, colours...], stride 8 */
#define GROUND_BAND_STRIDE     8
#define GROUND_ROW_LONGS       10        /* 10 * 16 bytes = one 160-byte scanline (dbf #9) */
#define GROUND_SOLID_ROWS_M1     9       /* solid fill: 1 scanline */
#define GROUND_SOLID_ROWS_M1_TOP 0x13    /* nearest entry (band==0): 2 scanlines */
#define GROUND_LIT_PLANES      0xffffffffu  /* lit ground row (band>=9); moveq #$ff sign-extends */

/* Base of the band in the draw buffer: buffer + the entry's offset word, indexed by the view col. */
static uint32_t ground_dst(const uint8_t *image, uint32_t buffer, uint32_t col, uint16_t view) {
    return buffer + sign_ext16(be16(image + col + sign_ext16(view)));
}

/* Write one 160-byte scanline as the longword pattern (lo, hi, lo, hi) x GROUND_ROW_LONGS. */
static uint32_t ground_row(uint8_t *image, uint32_t dst, uint32_t lo, uint32_t hi) {
    for (int j = 0; j < GROUND_ROW_LONGS; j++) {
        wr32(image + dst, lo);     wr32(image + dst + 4, hi);
        wr32(image + dst + 8, lo); wr32(image + dst + 12, hi);
        dst += 16;
    }
    return dst;
}

/* 0x1a: a colour gradient of (bands+1) scanlines, colours from the band record. */
static void ground_gradient(uint8_t *image, uint32_t buffer, uint32_t col, uint16_t view, int band) {
    if (band >= 9) band = 6;
    else if (band >= 5) band = 5;             /* else keep band */
    uint32_t rec = GROUND_BAND_RECORDS + (6 - band) * GROUND_BAND_STRIDE;
    uint32_t dst = ground_dst(image, buffer, col, view);
    int bands = image[rec++];                 /* dbf count */
    dst -= 2 * image[rec++];                  /* suba.w d2 twice */
    for (int b = bands; b >= 0; b--) {
        uint32_t pattern = A_color_pairs + image[rec++];   /* colour byte -> color_pairs offset */
        dst = ground_row(image, dst, be32(image + pattern), be32(image + pattern + 4));
    }
}

/* 0x1c: a solid fill; lit (planes set) when the entry is distant, else black. */
static void ground_solid(uint8_t *image, uint32_t buffer, uint32_t col, uint16_t view, int band) {
    uint32_t dst = ground_dst(image, buffer, col, view);
    uint32_t lo = (band >= 9) ? GROUND_LIT_PLANES : 0;
    int rows_m1 = (band == 0) ? GROUND_SOLID_ROWS_M1_TOP : GROUND_SOLID_ROWS_M1;
    for (int r = 0; r <= rows_m1; r++) {
        wr32(image + dst, lo);     wr32(image + dst + 4, 0);
        wr32(image + dst + 8, lo); wr32(image + dst + 12, 0);
        dst += 16;
    }
}

void g_draw_ground(uint8_t *image, uint32_t buffer) {
    uint32_t scan = A_ground_scan_tbl + 2;          /* a3: the descriptor's marker word */
    uint32_t col = GROUND_COL_OFFSETS;              /* a5 */
    uint16_t view = be16(image + A_ground_view_off);
    for (int band = GROUND_SCAN_ENTRIES - 1; band >= 0; band--, scan += GROUND_SCAN_STRIDE, col += GROUND_COL_STRIDE) {
        uint8_t marker = (uint8_t)be16(image + scan);
        if (marker == GROUND_MARK_GRADIENT) { ground_gradient(image, buffer, col, view, band); return; }
        if (marker == GROUND_MARK_SOLID)    { ground_solid(image, buffer, col, view, band); return; }
    }
}

/* ===========================================================================================
 * render_road @ 0x19144 — the pseudo-3D road rasterizer (PURE LEAF: no bsr/jsr; ends rts @0x9a3c).
 *
 * Draws the perspective road surface one scanline at a time, top to bottom, in seven successive
 * bands. Each scanline pulls a 32-bit *control* longword from road_width_tbl, adds a per-row
 * perspective offset word from a param stream, and dispatches on the control's flag bits to a
 * 16-pixel-column, 4-plane blit variant: it copies road-texture columns from buf_b (a flag-chosen
 * sub-region) into the on-screen road band, fills the road interior / shoulders with solid plane
 * patterns, and masks the road edge with a per-row mask.
 *
 * This file is the readable DEFAULT: each band is an idiomatic proper-C recreation (rr_band_*_l2),
 * driven by the shared pipeline in road_bands.h. Its byte-exact 1:1 machine-model twin — the trust
 * anchor, register/goto transcription — lives in machine/road.c (g_render_road_machine). Both are
 * verified byte-for-byte against the Musashi oracle by the same fuzz battery.
 *
 * 16-bit-faithful throughout: the control's low word wraps mod 2^16 and a branch after a `.w` op
 * tests the *word* sign. The 4-byte thunk at 0x15af6 (`bra.w 0x19144`) is a plain alias.
 * =========================================================================================== */

/* ---- render_road entry: the idiomatic bands are the default; the byte-exact machine model (the
 * trust anchor) lives in machine/road.c as g_render_road_machine. Shared pipeline, primitives and
 * constants are in road_bands.h. The idiomatic bands are defined below. ---- */
static void rr_band_A_l2(rr_regs *r);
static void rr_band_B_l2(rr_regs *r, uint32_t rows_m1, int second);
static void rr_band_C_near_l2(rr_regs *r, uint32_t rows_m1);
static void rr_band_C_far_l2(rr_regs *r, uint32_t rows_m1);
static void rr_band_D_l2(rr_regs *r, uint32_t rows_m1, int second);

static const rr_bands RR_BANDS = {
    rr_band_A_l2, rr_band_B_l2, rr_band_C_near_l2, rr_band_C_far_l2, rr_band_D_l2,
};
void g_render_road(uint8_t *image) {
    render_road_impl(image, &RR_BANDS);
}


/* =====================================================================================
 * Layer 2 — proper-C recreation of band B (byte-for-byte equivalent to rr_band_B).
 *
 * Band-B specifics vs C/D: the default fill is d5=0xffff0000 / d6=0x0000ffff, the edge mask
 * (loaded only when MASK_A is set) masks the HIGH WORD of the split long (and.w, via rr_andw),
 * and the two tails place the road differently:
 *   - near tail: draw at row_start + 8 + col, with a FORWARD shoulder fill to the right of the
 *     edge cell (the 68k adds 8 to both dst and src first);
 *   - far tail: a wider blit — a full-width fill when the road is off-screen, or up to four
 *     texture longs (third masked) followed by a forward shoulder fill.
 * A skip flag (SPLIT_B & SKIP_ABC & d0<0) blanks the row.
 * ===================================================================================== */
static void rr_band_B_l2(rr_regs *r, uint32_t rows_m1, int second) {
    uint8_t *img = r->img;
    const int16_t stride = (int16_t)r->d2;
    uint32_t remaining = rows_m1;

    for (;;) {
        uint32_t src = r->a3;
        uint32_t dst = r->a2;

        uint32_t ctrl = be32(img + r->a5); r->a5 += 4;
        uint16_t half_width = (uint16_t)(ctrl + be16(img + r->a4)); r->a4 += 2;
        ctrl = (ctrl & 0xffff0000u) | half_width;
        src += sign_ext16((uint16_t)((ctrl & 0xf) << 4));       /* fine-x sub-column */
        int16_t edge_seed = (int16_t)be16(img + r->a4); r->a4 += 2;

        uint32_t fill_lo = 0xffff0000u, fill_hi = 0x0000ffffu, edge_mask = 0xffffffffu;
        if (ctrl & RR_F_MASK_A) { fill_lo = 0; edge_mask = be32(img + src + RR_MASK_OFF_HI); }

        /* ---- source-strip dispatch ---- */
        if (!(ctrl & RR_F_SPLIT_B)) {                           /* no-split: a6-relative strip */
            src += sign_ext16((uint16_t)edge_seed) + sign_ext16(be16(img + r->a6)); r->a6 += 2;
            if (ctrl & RR_F_PLANE_HI) src += RR_SRC_5800;
        } else if ((ctrl & RR_F_SKIP_ABC) && (int32_t)ctrl < 0) {
            r->a6 += 2; r->a2 += stride;                        /* flagged blank scanline */
            if (!rr_dbf(&remaining)) break;
            continue;
        } else {
            r->a6 += 2;
            if (ctrl & RR_F_WIDE) {                             /* wide/solid-centre strip */
                fill_hi = 0; src += RR_SRC_4700;
                if (ctrl & RR_F_SRC_400) {
                    src += RR_SRC_0400;
                    if (!(ctrl & RR_F_SRC_100)) src = RR_CONST_5B7A;
                } else {
                    fill_lo = rr_notw(fill_lo);
                    if (!(ctrl & RR_F_SRC_100)) src = RR_CONST_5B9A;
                }
            } else if (ctrl & RR_F_PLANE_HI) {
                src += RR_SRC_5800;
            }
        }

        /* col = half the width, arithmetic-shifted then column-aligned (via d7 = 0xfff8). */
        int16_t col = (int16_t)((uint16_t)((int16_t)half_width >> 1) & (uint16_t)r->d7);

        if (!second) {
            /* ---- near tail: edge cell at row_start + 8 + col, forward shoulder fill ---- */
            dst += 8; src += 8;
            dst += sign_ext16((uint16_t)col);
            int16_t e = rr_wadd((uint16_t)col, 8);
            if (e < 0) {
                rr_fill_full_row(img, &r->a2, fill_lo, fill_hi);   /* road off-screen: fill row */
            } else {
                int16_t rem = rr_wsub((uint16_t)e, (uint16_t)stride);
                if (rem < 0) {
                    rr_copy_long(img, &dst, &src);
                    rr_andw(img, dst - 4, edge_mask);              /* mask high word of the long */
                    rr_copy_long(img, &dst, &src);
                    rem = rr_wadd((uint16_t)rem, 8);
                    while (rem < 0) {                             /* forward shoulder fill */
                        rr_fill_pair(img, &dst, fill_lo, fill_hi);
                        rem = rr_wadd((uint16_t)rem, 8);
                    }
                }
                r->a2 += stride;
            }
            if (!rr_dbf(&remaining)) break;
            continue;
        }

        /* ---- far tail: wider blit ---- */
        if (col < 0) {                                          /* road off-screen: counted fill */
            int16_t rem = rr_wadd((uint16_t)col, 8);
            uint32_t cells = (rem < 0) ? 0x13 : 0x12;
            if (rem >= 0) {                                     /* one masked edge cell first */
                src += 8;
                rr_copy_long(img, &dst, &src);
                rr_andw(img, dst - 4, edge_mask);
                rr_copy_long(img, &dst, &src);
            }
            do { rr_fill_pair(img, &dst, fill_lo, fill_hi); } while (rr_dbf(&cells));
            r->a2 += stride;
            if (!rr_dbf(&remaining)) break;
            continue;
        }

        dst += sign_ext16((uint16_t)col);
        int16_t rem = rr_wsub((uint16_t)col, (uint16_t)stride);
        if (rem < 0) {
            rem = rr_wadd((uint16_t)rem, 8);
            if (rem < 0) {                                      /* 4 longs, third masked */
                rr_copy_long(img, &dst, &src);
                rr_copy_long(img, &dst, &src);
                rr_copy_long(img, &dst, &src);
                rr_andw(img, dst - 4, edge_mask);
                rr_copy_long(img, &dst, &src);
            } else {                                            /* 2 longs */
                rr_copy_long(img, &dst, &src);
                rr_copy_long(img, &dst, &src);
            }
            rem = rr_wadd((uint16_t)rem, 8);
            while (rem < 0) {                                   /* forward shoulder fill */
                rr_fill_pair(img, &dst, fill_lo, fill_hi);
                rem = rr_wadd((uint16_t)rem, 8);
            }
        }
        r->a2 += stride;
        if (!rr_dbf(&remaining)) break;
    }
}


/* =====================================================================================
 * Layer 2 — proper-C recreation of band C-near (byte-for-byte equivalent to rr_band_C_near).
 *
 * Same per-scanline shape as band D, with band-C specifics: the edge mask is read
 * unconditionally and masks a FULL long on the split edge cell (and.l d3, vs band D's high-word
 * and.w), and two distinct blit tails feed the row:
 *   - fast edge-split tail (SPLIT_C set, SKIP_D set): [edge cell | left-shoulder fill], where the
 *     edge cell is either a plain 2-long copy (plane-hi strip) or copy + masked-copy;
 *   - merge tail (no-split / wide / plain split): a narrow [texture | one-cell fill | texture] blit
 *     around the column, with the road either off-screen, one cell wide, or two cells wide.
 * A skip flag blanks the row; a full-width road fills all 160 bytes with the plane pattern.
 * ===================================================================================== */
static void rr_band_C_near_l2(rr_regs *r, uint32_t rows_m1) {
    uint8_t *img = r->img;
    const int16_t stride = (int16_t)r->d2;
    uint32_t remaining = rows_m1;

    for (;;) {
        uint32_t src = r->a3;
        uint32_t dst = r->a2;

        uint32_t ctrl = be32(img + r->a5); r->a5 += 4;
        uint16_t half_width = (uint16_t)(ctrl + be16(img + r->a4)); r->a4 += 2;
        ctrl = (ctrl & 0xffff0000u) | half_width;
        src += sign_ext16((uint16_t)((ctrl & 0xf) << 4));       /* fine-x sub-column */
        int16_t edge_seed = (int16_t)be16(img + r->a4); r->a4 += 2;

        uint32_t edge_mask = be32(img + src + RR_MASK_OFF_LO);   /* unconditional (band C) */
        uint32_t fill_lo = 0xffffffffu, fill_hi = 0x0000ffffu;
        if (ctrl & RR_F_PLANE_HI) fill_hi = 0xffff0000u;         /* swap d6 */

        /* col = half the width, arithmetic-shifted then aligned to an 8-byte cell. */
        int16_t col = (int16_t)((uint16_t)((int16_t)half_width >> 1) & RR_D7_WORD_MASK);

        /* ---- source-strip dispatch: also decides which tail paints the row ---- */
        int fast_split = 0, do_src_select = 0;
        if (!(ctrl & RR_F_SPLIT_C)) {                            /* no-split: a6-relative strip */
            src += sign_ext16((uint16_t)edge_seed) + sign_ext16(be16(img + r->a6)); r->a6 += 2;
            do_src_select = 1;
        } else {
            r->a6 += 2;
            if (ctrl & RR_F_WIDE) {                              /* wide/solid-centre strip */
                fill_hi = 0; src += RR_SRC_3E00;
                if (ctrl & RR_F_SRC_400) {
                    src += RR_SRC_0400;
                    if (!(ctrl & RR_F_SRC_100)) { src += RR_SRC_0100; fill_lo = 0; }
                } else if (!(ctrl & RR_F_SRC_100)) {
                    src += RR_SRC_0100; fill_lo = 0x0000ffffu;
                }
            } else if (ctrl & RR_F_SKIP_D) {
                fast_split = 1;
            } else {
                do_src_select = 1;
            }
        }
        if (do_src_select) {                                     /* L966a: plane-hi / const strip */
            if (ctrl & RR_F_PLANE_HI) src += RR_SRC_5800;
            else if ((ctrl & RR_F_SRC_CONST) && (int32_t)ctrl >= 0) src = RR_CONST_5BAA;
        }

        if (fast_split) {
            fill_hi = 0;
            if (col >= 0) {
                src += sign_ext16((uint16_t)edge_seed);
                dst += sign_ext16((uint16_t)col);
                int full_row;
                if (ctrl & RR_F_PLANE_HI) {
                    fill_lo = 0; src += RR_SRC_A800;
                    if (be16(img + r->a6 - 2) != 0) src += RR_SRC_0A00;
                    full_row = rr_wsub((uint16_t)col, (uint16_t)stride) >= 0;
                    if (!full_row) { rr_copy_long(img, &dst, &src); rr_copy_long(img, &dst, &src); }
                } else {
                    src += sign_ext16(be16(img + r->a6 - 2));
                    full_row = rr_wsub((uint16_t)col, (uint16_t)stride) >= 0;
                    if (!full_row) { rr_copy_long(img, &dst, &src);
                                     rr_copy_long_masked(img, &dst, &src, edge_mask); }
                }
                if (full_row) {
                    rr_fill_full_row(img, &r->a2, fill_lo, fill_hi);
                    if (!rr_dbf(&remaining)) break;
                    continue;
                }
                /* left shoulder: (col/8) whole cells back from the row start */
                int16_t shoulder_cells = (int16_t)(((uint16_t)col >> 3) - 1);
                if (shoulder_cells >= 0) {
                    uint32_t sh = r->a2, cnt = (uint16_t)shoulder_cells;
                    do { rr_fill_pair(img, &sh, fill_lo, fill_hi); } while (rr_dbf(&cnt));
                }
            }
            /* col < 0 draws nothing (road off the left edge) */
            r->a2 += stride; if (!rr_dbf(&remaining)) break;
            continue;
        }

        /* ---- merge tail: narrow blit around the column ---- */
        int16_t left = rr_wsub((uint16_t)col, 8);               /* col - 8 */
        if (left < 0) {
            if (col >= 0) { rr_copy_long(img, &dst, &src); rr_copy_long(img, &dst, &src); }
        } else {
            dst += sign_ext16((uint16_t)left);
            int16_t rem = rr_wsub((uint16_t)left, (uint16_t)stride);
            if (rem < 0) {
                rr_fill_pair(img, &dst, fill_lo, fill_hi);
                if (rr_wadd((uint16_t)rem, 8) < 0) {            /* still room: two texture cells */
                    rr_copy_long(img, &dst, &src);
                    rr_copy_long(img, &dst, &src);
                }
            }
        }
        r->a2 += stride; if (!rr_dbf(&remaining)) break;
    }
}


/* =====================================================================================
 * Layer 2 — proper-C recreation of band C-far (byte-for-byte equivalent to rr_band_C_far).
 *
 * The far copy of band C. Preamble + src dispatch match band C-near, but two paths differ:
 *   - fast edge-split (SPLIT_C & SKIP_D): selects the source strip FIRST and consumes one extra
 *     param word (a4 += 2), then blits [edge cell | left-shoulder fill]. The plane-hi and masked
 *     variants each branch on off-screen / 2-long / 4-long width.
 *   - merge tail: reads yet another param word, then a bidirectional blit — forward 2..4 texture
 *     longs when the road grows rightward, or a BACKWARD shoulder fill (move.l -(a0)) when it
 *     recedes, using a separately-tracked width in d3.w.
 * ===================================================================================== */

static void rr_band_C_far_l2(rr_regs *r, uint32_t rows_m1) {
    uint8_t *img = r->img;
    const int16_t stride = (int16_t)r->d2;
    uint32_t remaining = rows_m1;

    for (;;) {
        uint32_t src = r->a3;
        uint32_t dst = r->a2;

        uint32_t ctrl = be32(img + r->a5); r->a5 += 4;
        uint16_t half_width = (uint16_t)(ctrl + be16(img + r->a4)); r->a4 += 2;
        ctrl = (ctrl & 0xffff0000u) | half_width;
        src += sign_ext16((uint16_t)((ctrl & 0xf) << 4));       /* fine-x sub-column */
        int16_t edge_seed = (int16_t)be16(img + r->a4); r->a4 += 2;

        uint32_t edge_mask = be32(img + src + RR_MASK_OFF_LO);   /* unconditional (band C) */
        uint32_t fill_lo = 0xffffffffu, fill_hi = 0x0000ffffu;
        if (ctrl & RR_F_PLANE_HI) fill_hi = 0xffff0000u;

        /* ---- fast edge-split path (its own tail; consumes an extra param word) ---- */
        if ((ctrl & RR_F_SPLIT_C) && !(ctrl & RR_F_WIDE) && (ctrl & RR_F_SKIP_D)) {
            r->a6 += 2;
            src += sign_ext16((uint16_t)edge_seed);
            r->a4 += 2;                                          /* far-only extra param word */
            int16_t col;
            fill_hi = 0;
            if (ctrl & RR_F_PLANE_HI) {
                fill_lo = 0; src += RR_SRC_A800;
                if (be16(img + r->a6 - 2) != 0) src += RR_SRC_0A00;
            } else {
                src += sign_ext16(be16(img + r->a6 - 2));
            }
            col = (int16_t)((uint16_t)((int16_t)half_width >> 1) & (uint16_t)r->d7);
            if (col < 0) {                                       /* road near/off the left edge */
                int16_t e = rr_wadd((uint16_t)col, 8);
                if (e >= 0) { src += 8; rr_copy_long(img, &dst, &src); rr_copy_long(img, &dst, &src); }
            } else {
                dst += sign_ext16((uint16_t)col);
                int16_t rem = rr_wsub((uint16_t)col, (uint16_t)stride);
                if (rem >= 0) {
                    rr_fill_full_row(img, &r->a2, fill_lo, fill_hi);
                    if (!rr_dbf(&remaining)) break;
                    continue;
                }
                int16_t e = rr_wadd((uint16_t)rem, 8);
                if (e < 0) {                                     /* 4 longs (masked 2nd on non-hi) */
                    rr_copy_long(img, &dst, &src);
                    if (!(ctrl & RR_F_PLANE_HI)) rr_copy_long_masked(img, &dst, &src, edge_mask);
                    else                         rr_copy_long(img, &dst, &src);
                    rr_copy_long(img, &dst, &src);
                    rr_copy_long(img, &dst, &src);
                } else {                                         /* 2 longs (masked 2nd on non-hi) */
                    rr_copy_long(img, &dst, &src);
                    if (!(ctrl & RR_F_PLANE_HI)) rr_copy_long_masked(img, &dst, &src, edge_mask);
                    else                         rr_copy_long(img, &dst, &src);
                }
                /* left shoulder: (col>>3 - 1) forward pairs from the row start */
                int16_t cells = (int16_t)(((uint16_t)col >> 3) - 1);
                if (cells >= 0) {
                    uint32_t sh = r->a2, cnt = (uint16_t)cells;
                    do { rr_fill_pair(img, &sh, fill_lo, fill_hi); } while (rr_dbf(&cnt));
                }
            }
            r->a2 += stride;
            if (!rr_dbf(&remaining)) break;
            continue;
        }

        /* ---- shared src dispatch (feeds the merge tail) ---- */
        if (!(ctrl & RR_F_SPLIT_C)) {                            /* no-split: a6-relative strip */
            src += sign_ext16((uint16_t)edge_seed) + sign_ext16(be16(img + r->a6)); r->a6 += 2;
            if (ctrl & RR_F_PLANE_HI) src += RR_SRC_5800;
            else if ((ctrl & RR_F_SRC_CONST) && (int32_t)ctrl >= 0) src = RR_CONST_5BAA;
        } else if (ctrl & RR_F_WIDE) {                           /* WIDE strip */
            r->a6 += 2;
            fill_hi = 0; src += RR_SRC_3E00;
            if (ctrl & RR_F_SRC_400) {
                src += RR_SRC_0400;
                if (!(ctrl & RR_F_SRC_100)) { src += RR_SRC_0100; fill_lo = 0; }
            } else if (!(ctrl & RR_F_SRC_100)) {
                src += RR_SRC_0100; fill_lo = 0x0000ffffu;
            }
        } else {                                                /* SPLIT_C, !WIDE, !SKIP_D: plane-hi/const */
            r->a6 += 2;
            if (ctrl & RR_F_PLANE_HI) src += RR_SRC_5800;
            else if ((ctrl & RR_F_SRC_CONST) && (int32_t)ctrl >= 0) src = RR_CONST_5BAA;
        }

        /* ---- merge tail (reads one more param word): a2-relative bidirectional blit ---- */
        int16_t count = (int16_t)be16(img + r->a4); r->a4 += 2;   /* d1: shoulder-fill count */
        int16_t col = (int16_t)((uint16_t)((int16_t)half_width >> 1) & (uint16_t)r->d7);
        if (col < 0) {                                            /* L980a: road off the left edge */
            if (rr_wadd((uint16_t)col, 8) >= 0) {
                src += 8; rr_copy_long(img, &dst, &src); rr_copy_long(img, &dst, &src);
            }
            r->a2 += stride;
            if (!rr_dbf(&remaining)) break;
            continue;
        }

        /* L9822: place at the column; d3.w (width) tracks the reverse-fill extent. */
        dst += sign_ext16((uint16_t)col);
        int16_t width = col;
        int16_t col_rem = rr_wsub((uint16_t)col, (uint16_t)stride);   /* col - stride */
        if (col_rem >= 0 && rr_wsub((uint16_t)col_rem, 8) >= 0) {
            /* road spans the whole row: advance a2, reverse-fill (count - (rem-8)/8) pairs. */
            col_rem = rr_wsub((uint16_t)col_rem, 8);
            r->a2 += stride;
            int16_t n = rr_wsub((uint16_t)count, (uint16_t)((uint16_t)col_rem >> 3));
            if (n >= 0) {
                uint32_t shoulder = r->a2, cnt = (uint16_t)n;
                do { rr_fill_pair_rev(img, &shoulder, fill_lo, fill_hi); } while (rr_dbf(&cnt));
            }
            if (!rr_dbf(&remaining)) break;
            continue;
        }

        /* Otherwise reach L984c with either: (a) col-stride < 0 -> L9846 clears d0 and copies 2
         * longs first; or (b) stride <= col < stride+8 -> straight in with d0 = col-stride-8. */
        if (col_rem < 0) {
            col_rem = 0;                                         /* L9846: moveq #0 */
            rr_copy_long(img, &dst, &src); rr_copy_long(img, &dst, &src);
        } else {
            col_rem = rr_wsub((uint16_t)col_rem, 8);
        }
        col_rem = rr_wadd((uint16_t)col_rem, 8);                 /* L984c */
        rr_copy_long(img, &dst, &src); rr_copy_long(img, &dst, &src);
        col_rem = rr_wadd((uint16_t)col_rem, 8);
        dst -= sign_ext16((uint16_t)col_rem);                    /* suba.w d0,a0 */

        /* L9856: reverse-fill while the width stays >= 0 and the count hasn't underflowed. */
        uint32_t cnt = (uint16_t)count;
        for (;;) {
            width = rr_wsub((uint16_t)width, 8);                 /* subq.w #8,d3 */
            if (width < 0) break;
            rr_fill_pair_rev(img, &dst, fill_lo, fill_hi);
            if (!rr_dbf(&cnt)) break;
        }
        r->a2 += stride;
        if (!rr_dbf(&remaining)) break;
    }
}


/* =====================================================================================
 * Layer 2 — proper-C recreation of band D (byte-for-byte equivalent to rr_band_D above).
 *
 * Same contract (the shared rr_regs cursors), but written as the algorithm reads rather than
 * as the 68000 stepped it. One perspective road band = `rows_m1`+1 scanlines. Each scanline
 * pulls a control word (road half-width in the low 16 bits, blit-variant flags in the high 16),
 * picks which texture strip the row samples (flag-driven src select), then paints the row as
 *     [ left-shoulder solid fill | antialiased edge cell | copied road texture ]
 * `second` selects the far (nearer-to-camera) copy, whose bottom rows draw a wider texture run
 * and additionally handle the road sliding off the left edge. Both layers run the same fuzz
 * battery against the Musashi oracle; rr_band_D stays the trust anchor.
 *
 * Word ops wrap mod 2^16 and branch on bit 15 — mirrored with (uint16_t)/(int16_t) casts.
 * ===================================================================================== */
#define RR_ROW_LONG_PAIRS 20         /* 160-byte scanline = 20 (fill_lo, fill_hi) long pairs */

/* Solid-fill one whole 160-byte scanline with the plane pattern (full-width road / off-screen). */
static void rr_fill_row(uint8_t *img, uint32_t dst, uint32_t fill_lo, uint32_t fill_hi) {
    for (int i = 0; i < RR_ROW_LONG_PAIRS; i++, dst += 8) {
        wr32(img + dst, fill_lo); wr32(img + dst + 4, fill_hi);
    }
}

/* Solid-fill the left shoulder [row_start, row_start + col): col is column-aligned, so it covers
 * whole 8-byte cells right up to the edge cell at row_start + col. */
static void rr_fill_shoulder(uint8_t *img, uint32_t row_start, int16_t col, uint32_t fill_lo, uint32_t fill_hi) {
    for (int cell = (int)((uint16_t)col >> 3); cell > 0; cell--, row_start += 8) {
        wr32(img + row_start, fill_lo); wr32(img + row_start + 4, fill_hi);
    }
}

/* Draw the antialiased edge cell (one 16-pixel 4-plane column) at dst: two longs, the first with
 * its high plane-word masked through edge_mask. Advances src/dst past the two longs. */
static void rr_draw_edge_cell(uint8_t *img, uint32_t *dst, uint32_t *src, uint32_t edge_mask) {
    uint32_t edge = *dst;
    rr_copy_long(img, dst, src);
    rr_andw(img, edge, edge_mask);
    rr_copy_long(img, dst, src);
}

/* =====================================================================================
 * Layer 2 — proper-C recreation of band A (byte-for-byte equivalent to rr_band_A).
 *
 * Band A is a two-pass renderer, unlike bands B/C/D. Each scanline has a road "edge" column at
 * dst + col (col = the aligned road half-width). From that edge it:
 *   - forward pass: copies road-texture longs rightward toward the row end, then gap-fills the
 *     remainder with the interior plane pattern;
 *   - backward pass: fills the left shoulder leftward from the edge with a (usually different)
 *     shoulder plane pattern, skipping any cells that fell past the row.
 * When the aligned width is negative (road off the left edge) it degenerates to a single forward
 * fill with no second pass. The flags choose the source texture strip and the two fill patterns;
 * SPLIT (edge-split) rows mask the joining edge cell, WIDE/centre rows do not.
 * ===================================================================================== */

/* Shoulder/interior plane pattern select (machine L928c/L9352 + L936a): the backward-fill colours. */
static void rr_band_A_shoulder_pattern(uint32_t ctrl, int center, uint32_t *lo, uint32_t *hi) {
    *lo = 0x0000ffffu;
    *hi = 0x0000ffffu;
    if (!center) {                                    /* split (L928c) */
        if ((int32_t)ctrl < 0 && (ctrl & RR_F_PLANE_HI)) { *lo = 0xffffffffu; *hi = 0; }
    } else {                                          /* centre (L9352) */
        if ((ctrl & RR_F_SRC_CONST) && (int32_t)ctrl >= 0 && !(ctrl & RR_F_PLANE_HI))
            *lo = 0xffffffffu;
    }
    if (ctrl & RR_F_WIDE) {                            /* L936a */
        *lo = 0xffffffffu; *hi = 0;
        if (ctrl & RR_F_SRC_100) {
            *lo = 0;
            if (!(ctrl & RR_F_SRC_400)) *lo = 0x0000ffffu;
        }
    }
}

/* Backward left-shoulder fill (machine L9384): from `edge` leftward, writing (lo,hi) cells. `width`
 * starts at the aligned road width and counts down a cell (8 bytes) at a time; a cell whose position
 * is still past the row end (>= stride) is skipped, and the walk stops when the position goes
 * negative or the `count` (edge-table run length) is exhausted. */
static void rr_band_A_shoulder_fill(uint8_t *img, uint32_t edge, int16_t width, uint32_t count,
                                    int16_t stride, uint32_t lo, uint32_t hi) {
    uint32_t shoulder = edge;
    for (;;) {
        width = rr_wsub((uint16_t)width, 8);
        if (width < 0) break;
        if (rr_wsub((uint16_t)width, (uint16_t)stride) >= 0) shoulder -= 8;   /* cell past the row: skip */
        else rr_fill_pair_rev(img, &shoulder, lo, hi);
        if (!rr_dbf(&count)) break;
    }
}

/* Forward interior for a SPLIT row (machine L91f8 / L925c). Copies 4 texture longs (the last edge-
 * masked when `masked_edge`) for a wide gap, or 2 longs for a narrow one, then gap-fills to the row
 * end with the interior pattern. Entered only when pos = col - stride < 0. */
static void rr_band_A_interior_split(uint8_t *img, uint32_t *dst, uint32_t *src, int16_t pos,
                                     int masked_edge, uint32_t edge_mask,
                                     uint32_t gap_lo, uint32_t gap_hi) {
    if (rr_wadd((uint16_t)pos, 8) >= 0) {             /* narrow gap: 2 longs */
        rr_copy_long(img, dst, src);
        rr_copy_long(img, dst, src);
    } else {                                          /* wide gap: 4 longs (last masked on the C variant) */
        rr_copy_long(img, dst, src);
        rr_copy_long(img, dst, src);
        rr_copy_long(img, dst, src);
        if (masked_edge) rr_copy_long_masked(img, dst, src, edge_mask);
        else             rr_copy_long(img, dst, src);
    }
    pos = rr_wadd((uint16_t)rr_wadd((uint16_t)pos, 8), 8);
    while (pos < 0) { rr_fill_pair(img, dst, gap_lo, gap_hi); pos = rr_wadd((uint16_t)pos, 8); }
}

/* Forward interior for a CENTRE/WIDE row (machine L9328). A narrow gap copies 2 longs and stops; a
 * wide gap copies 4 longs then gap-fills, bounded by both the row end and the run `count`. */
static void rr_band_A_interior_center(uint8_t *img, uint32_t *dst, uint32_t *src, int16_t pos,
                                      uint32_t count, uint32_t gap_lo, uint32_t gap_hi) {
    if (rr_wadd((uint16_t)pos, 8) >= 0) {             /* narrow gap: 2 longs, no fill */
        rr_copy_long(img, dst, src);
        rr_copy_long(img, dst, src);
        return;
    }
    rr_copy_long(img, dst, src);
    rr_copy_long(img, dst, src);
    rr_copy_long(img, dst, src);
    rr_copy_long(img, dst, src);
    pos = rr_wadd((uint16_t)pos, 8);
    for (;;) {
        pos = rr_wadd((uint16_t)pos, 8);
        if (pos >= 0) break;
        rr_fill_pair(img, dst, gap_lo, gap_hi);
        if (!rr_dbf(&count)) break;
    }
}

static void rr_band_A_l2(rr_regs *r) {
    uint8_t *img = r->img;
    const int16_t stride = (int16_t)r->d2;            /* 0xa0 */
    uint32_t rows = 0x5f;                             /* 96 scanlines */

    for (;;) {
        uint32_t src = r->a3;
        uint32_t row_dst = r->a2;

        uint32_t ctrl = be32(img + r->a5); r->a5 += 4;
        uint16_t half_width = (uint16_t)(ctrl + be16(img + r->a4)); r->a4 += 2;
        ctrl = (ctrl & 0xffff0000u) | half_width;
        src += sign_ext16((uint16_t)((ctrl & 0xf) << 4));           /* fine-x sub-column */
        uint32_t edge_mask = be32(img + src + RR_MASK_OFF_HI);      /* 0x2808, unconditional */
        int16_t edge_seed = (int16_t)be16(img + r->a4); r->a4 += 2;

        uint32_t fill_lo = 0xffffffffu, fill_hi = 0x0000ffffu;      /* interior/gap plane pattern */
        if (ctrl & RR_F_PLANE_HI) fill_hi = 0xffff0000u;

        int is_split = (ctrl & RR_F_SPLIT_A) && !(ctrl & RR_F_WIDE) && (ctrl & RR_F_SKIP_ABC);
        int plane_hi = (ctrl & RR_F_PLANE_HI) != 0;
        uint32_t count_long;

        /* ---- source-strip dispatch (sets src, fill pattern, count_long) ---- */
        if (is_split) {
            r->a6 += 2;
            src += sign_ext16((uint16_t)edge_seed);
            count_long = be32(img + r->a4); r->a4 += 4;             /* move.l (a4)+ */
            fill_hi = 0;
            if (plane_hi) {                                        /* L91c0 */
                fill_lo = 0; src += RR_SRC_A800;
                if (be16(img + r->a6 - 2) != 0) src += RR_SRC_0A00;
            } else {                                               /* L9230 */
                src += sign_ext16(be16(img + r->a6 - 2));
            }
        } else {
            if (!(ctrl & RR_F_SPLIT_A)) {                          /* L92d6 centre-run */
                src += sign_ext16((uint16_t)edge_seed) + sign_ext16(be16(img + r->a6)); r->a6 += 2;
                if (ctrl & RR_F_PLANE_HI) src += RR_SRC_5800;
                else if ((ctrl & RR_F_SRC_CONST) && (int32_t)ctrl >= 0) src = RR_CONST_5BAA;
            } else if (ctrl & RR_F_WIDE) {                         /* L92a8 wide src select */
                r->a6 += 2;
                fill_hi = 0; src += RR_SRC_5000;
                if (ctrl & RR_F_SRC_400) {
                    src += RR_SRC_0400;
                    if (!(ctrl & RR_F_SRC_100)) { src += RR_SRC_0100; fill_lo = 0; }
                } else if (!(ctrl & RR_F_SRC_100)) {
                    src += RR_SRC_0100; fill_lo = 0x0000ffffu;
                }
            } else {                                               /* L92da hi/const src select */
                r->a6 += 2;
                if (ctrl & RR_F_PLANE_HI) src += RR_SRC_5800;
                else if ((ctrl & RR_F_SRC_CONST) && (int32_t)ctrl >= 0) src = RR_CONST_5BAA;
            }
            count_long = be32(img + r->a4); r->a4 += 4;            /* L92f6: move.l (a4)+ */
        }

        int16_t col = (int16_t)((uint16_t)((int16_t)half_width >> 1) & RR_D7_WORD_MASK);

        if (col < 0) {
            /* ---- narrow: a single forward fill, no shoulder pass ---- */
            uint32_t dst = row_dst;
            if (is_split) {
                uint32_t count = 0x13;
                if (rr_wadd((uint16_t)col, 8) >= 0) {              /* copy an edge cell first */
                    count = 0x12; src += 8;
                    if (plane_hi) { rr_copy_long(img, &dst, &src); rr_copy_long(img, &dst, &src); }
                    else          { rr_copy_long(img, &dst, &src);
                                    rr_copy_long_masked(img, &dst, &src, edge_mask); }
                }
                do { rr_fill_pair(img, &dst, fill_lo, fill_hi); } while (rr_dbf(&count));
            } else {                                               /* L92f6 narrow centre */
                src += 8;
                int16_t col_cells = rr_wadd((uint16_t)col, 8);
                if (col_cells >= 0) { rr_copy_long(img, &dst, &src); rr_copy_long(img, &dst, &src); }
                else                { col_cells = rr_wadd((uint16_t)col_cells, 8); }
                col_cells = (int16_t)((int16_t)col_cells >> 3);
                uint32_t count = (uint16_t)((count_long & 0xffff) + (uint16_t)col_cells);
                if ((int16_t)count >= 0)
                    do { rr_fill_pair(img, &dst, fill_lo, fill_hi); } while (rr_dbf(&count));
            }
            r->a2 += stride;
            if (!rr_dbf(&rows)) break;
            continue;
        }

        /* ---- wide: forward texture blit from the edge, then a backward shoulder fill ---- */
        uint32_t edge = row_dst + sign_ext16((uint16_t)col);
        uint32_t dst = edge;
        int16_t pos = rr_wsub((uint16_t)col, (uint16_t)stride);
        if (pos < 0) {
            if (is_split) rr_band_A_interior_split(img, &dst, &src, pos, !plane_hi, edge_mask,
                                                   fill_lo, fill_hi);
            else          rr_band_A_interior_center(img, &dst, &src, pos, count_long & 0xffff,
                                                    fill_lo, fill_hi);
        }
        uint32_t sh_lo, sh_hi;
        rr_band_A_shoulder_pattern(ctrl, /*center=*/!is_split, &sh_lo, &sh_hi);
        rr_band_A_shoulder_fill(img, edge, col, count_long >> 16, stride, sh_lo, sh_hi);

        r->a2 += stride;
        if (!rr_dbf(&rows)) break;
    }
}

static void rr_band_D_l2(rr_regs *r, uint32_t rows_m1, int second) {
    uint8_t *img = r->img;
    const int16_t stride = (int16_t)r->d2;                 /* 0xa0 bytes per scanline */
    uint32_t remaining = rows_m1;

    for (;;) {
        uint32_t src = r->a3;                              /* texture base for this scanline */

        /* control long: high word = flags, low word = road half-width (+ perspective offset). */
        uint32_t ctrl = be32(img + r->a5); r->a5 += 4;
        uint16_t half_width = (uint16_t)(ctrl + be16(img + r->a4)); r->a4 += 2;
        ctrl = (ctrl & 0xffff0000u) | half_width;

        /* fine-x: the low nibble picks the sub-column within the 16-pixel texture cell. */
        src += sign_ext16((uint16_t)((ctrl & 0xf) << 4));
        int16_t edge_seed = (int16_t)be16(img + r->a4); r->a4 += 2;

        /* fill plane-patterns + edge-cell mask (defaults; MASK_A2 loads a real per-row mask). */
        uint32_t fill_lo = 0xffff0000u, fill_hi = 0x0000ffffu, edge_mask = 0xffffffffu;
        if (ctrl & RR_F_MASK_A2) { fill_lo = 0; edge_mask = be32(img + src + RR_MASK_OFF_LO); }

        int16_t edge_off = (int16_t)be16(img + r->a6);     /* used only by the no-split strip */
        r->a6 += 2;                                        /* a6 advances once per row, always */

        /* ---- source-strip dispatch: which region of the texture this scanline samples ---- */
        int skip_row = 0;
        if (!(ctrl & RR_F_SPLIT_D)) {                      /* straight strip (no edge split) */
            src += sign_ext16((uint16_t)edge_seed) + sign_ext16((uint16_t)edge_off);
            if (ctrl & RR_F_PLANE_HI) src += RR_SRC_5800;
        } else if ((ctrl & RR_F_SKIP_D) && (int32_t)ctrl < 0) {
            skip_row = 1;                                  /* flagged blank scanline */
        } else if (ctrl & RR_F_WIDE) {                     /* wide/solid-centre strip */
            fill_lo = 0; fill_hi = 0; src += RR_SRC_3500;
            if (ctrl & RR_F_SRC_400) {
                src += RR_SRC_0400;
                if (!(ctrl & RR_F_SRC_100)) src = RR_CONST_5B7A;
            } else {
                fill_lo = rr_notw(fill_lo);                /* 0 -> 0x0000ffff */
                if (!(ctrl & RR_F_SRC_100)) src = RR_CONST_5B9A;
            }
        } else if (ctrl & RR_F_PLANE_HI) {                 /* edge-split strip, high plane */
            src += RR_SRC_5800;
        }

        if (!skip_row) {
            /* column offset = half the width, arithmetic-shifted then aligned to an 8-byte cell. */
            int16_t col = (int16_t)((uint16_t)((int16_t)half_width >> 1) & RR_D7_WORD_MASK);
            uint32_t row_start = r->a2;
            uint32_t dst = row_start;

            if (col >= 0) {
                if (rr_wsub((uint16_t)col, (uint16_t)stride) >= 0) {
                    rr_fill_row(img, row_start, fill_lo, fill_hi);        /* road fills the row */
                } else {
                    dst += sign_ext16((uint16_t)col);
                    rr_draw_edge_cell(img, &dst, &src, edge_mask);
                    /* far copy widens the texture run by two more columns when there is room. */
                    if (second && rr_wadd((uint16_t)rr_wsub((uint16_t)col, (uint16_t)stride), 8) < 0) {
                        rr_copy_long(img, &dst, &src);
                        rr_copy_long(img, &dst, &src);
                    }
                    rr_fill_shoulder(img, row_start, col, fill_lo, fill_hi);
                }
            } else if (second && rr_wadd((uint16_t)col, 8) >= 0) {
                /* far copy, road one cell off the left edge: draw two texture longs at row start. */
                src += 8;
                rr_copy_long(img, &dst, &src);
                rr_copy_long(img, &dst, &src);
            }
            /* near copy with col < 0: nothing drawn (road entirely off the left edge). */
        }

        r->a2 += stride;
        if (!rr_dbf(&remaining)) break;
    }
}
