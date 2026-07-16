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
#define GROUND_SOLID_ROWS_M1_TOP 0x13    /* nearest entry (d4==0): 2 scanlines */
#define GROUND_LIT_PLANES      0xffffffffu  /* lit ground row (d4>=9); moveq #$ff sign-extends */

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
static void ground_gradient(uint8_t *image, uint32_t buffer, uint32_t col, uint16_t view, int d4) {
    if (d4 >= 9) d4 = 6;
    else if (d4 >= 5) d4 = 5;                 /* else keep d4 */
    uint32_t rec = GROUND_BAND_RECORDS + (6 - d4) * GROUND_BAND_STRIDE;
    uint32_t dst = ground_dst(image, buffer, col, view);
    int bands = image[rec++];                 /* dbf count */
    dst -= 2 * image[rec++];                  /* suba.w d2 twice */
    for (int b = bands; b >= 0; b--) {
        uint32_t pattern = A_color_pairs + image[rec++];   /* colour byte -> color_pairs offset */
        dst = ground_row(image, dst, be32(image + pattern), be32(image + pattern + 4));
    }
}

/* 0x1c: a solid fill; lit (planes set) when the entry is distant, else black. */
static void ground_solid(uint8_t *image, uint32_t buffer, uint32_t col, uint16_t view, int d4) {
    uint32_t dst = ground_dst(image, buffer, col, view);
    uint32_t lo = (d4 >= 9) ? GROUND_LIT_PLANES : 0;
    int rows_m1 = (d4 == 0) ? GROUND_SOLID_ROWS_M1_TOP : GROUND_SOLID_ROWS_M1;
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
    for (int d4 = GROUND_SCAN_ENTRIES - 1; d4 >= 0; d4--, scan += GROUND_SCAN_STRIDE, col += GROUND_COL_STRIDE) {
        uint8_t marker = (uint8_t)be16(image + scan);
        if (marker == GROUND_MARK_GRADIENT) { ground_gradient(image, buffer, col, view, d4); return; }
        if (marker == GROUND_MARK_SOLID)    { ground_solid(image, buffer, col, view, d4); return; }
    }
}

/* ===========================================================================================
 * render_road @ 0x19144 — the pseudo-3D road rasterizer (PURE LEAF: no bsr/jsr; ends rts @0x9a3c).
 *
 * Draws the perspective road surface one scanline at a time, top to bottom, in seven successive
 * `dbf` bands. Each scanline pulls a 32-bit *control* longword from road_width_tbl (a5), adds a
 * per-row perspective offset word from a param stream (a4), and dispatches on the control's flag
 * bits to a 16-pixel-column, 4-plane blit variant: it copies road-texture columns from buf_b
 * (a3 = src_base, with a per-scanline sub-region chosen by the flags) into the on-screen road band
 * (a2 = dst), fills the road interior / shoulders with solid plane patterns (d5/d6), and masks the
 * road edge with d3. The bands share a preamble but differ in which flag gates the edge-split and
 * in the column layout; it is hand-written spaghetti (many shared blit tails), so this is a direct
 * 1:1 machine model — d0..d7 / a0..a6 are the 68000 registers and the branches are mirrored with
 * goto to labels named by their Ghidra address (Lxxxx), readable against prg_dis output.
 *
 * 16-bit-faithful throughout: the control's low word wraps mod 2^16 and a branch after a `.w` op
 * tests the *word* sign. The 4-byte thunk at 0x15af6 (`bra.w 0x19144`) is a plain alias.
 * =========================================================================================== */

/* ---- entry setup (0x19144-0x9170) ---- */
#define RR_DST_ROAD_OFF   0x4100     /* a2 = draw_buffer + this: top of the on-screen road band */
#define RR_PARAM_TBL      0x1623a    /* a4: per-scanline perspective-offset param stream */
#define RR_EDGE_TBL_BASE  0x15c3a    /* a6 base: per-scanline edge/run table */
/* A_road_edge_sel (0x18c5a) is shared with init_leg — defined in addrs.h. */
#define RR_WIDTH_TBL      0x18f24    /* a5 = road_width_tbl (reset at each band group) */

/* ---- inter-band group step (0x93ac / 0x956e / 0x9868) ---- */
#define RR_DST_BAND_STEP  0x3c00     /* a2 -= this between band groups (rewind up the screen) */
#define RR_SRC_BAND_STEP  0x0a00     /* a3 += this between band groups (next texture sub-block) */
#define RR_EDGE_BAND_STEP 0x00c0     /* a6 -= this between band groups */

/* ---- per-scanline edge-mask reads (d3 = *(a1 + off), a1 = buf_b + fine_x) ---- */
#define RR_MASK_OFF_HI    0x2808     /* bands A/B */
#define RR_MASK_OFF_LO    0x2800     /* bands C/D */

/* ---- control-longword flag bits (btst #n on long d0); each selects a blit variant / src region -- */
#define RR_F_MASK_A       (1u << 16) /* band B: read edge mask, clear left fill (d5=0) */
#define RR_F_SPLIT_B      (1u << 17) /* bands B: row has an edge split (else full-width fill) */
#define RR_F_SPLIT_A      (1u << 18) /* band A:  edge split present (else center-run) */
#define RR_F_SPLIT_C      (1u << 19) /* bands C: edge split present */
#define RR_F_SPLIT_D      (1u << 20) /* bands D: edge split present */
#define RR_F_SRC_400      (1u << 21) /* src sub-offset selector (+0x400) */
#define RR_F_SRC_100      (1u << 22) /* src sub-offset selector (+0x100) / fill-side selector */
#define RR_F_WIDE         (1u << 23) /* wide/solid centre branch (vs the edge-split blit) */
#define RR_F_MASK_A2      (1u << 24) /* bands D: read edge mask (near group) */
#define RR_F_PLANE_HI     (1u << 27) /* swap d6 (hi plane pattern) and select an alternate src region */
#define RR_F_SRC_CONST    (1u << 28) /* select the const edge texture at 0x5baa (when d0 >= 0) */
#define RR_F_SKIP_ABC     (1u << 29) /* bands A/B: gate for the edge-split fast path */
#define RR_F_SKIP_D       (1u << 30) /* bands C/D: gate for the edge-split fast path */

/* ---- const edge textures near buf_b (image-absolute), selected per the flags ---- */
#define RR_CONST_5B7A     0x15b7a
#define RR_CONST_5B9A     0x15b9a
#define RR_CONST_5BAA     0x15baa
/* ---- src sub-region deltas added to a1 (= buf_b + fine_x) per the flags ---- */
#define RR_SRC_A800       0xa800u
#define RR_SRC_5800       0x5800
#define RR_SRC_5000       0x5000
#define RR_SRC_4700       0x4700
#define RR_SRC_3E00       0x3e00
#define RR_SRC_3500       0x3500
#define RR_SRC_0A00       0x0a00
#define RR_SRC_0400       0x0400
#define RR_SRC_0100       0x0100

#define RR_D7_WORD_MASK   0xfff8     /* d7 (bands B/C/D): masks d0.w to a column-aligned offset */

/* 68000 register-op helpers (word ops touch only the low 16 bits). */
static inline uint32_t rr_wset(uint32_t r, uint16_t low) { return (r & 0xffff0000u) | low; } /* set low word */
static inline int16_t  rr_ws(uint32_t r)  { return (int16_t)(uint16_t)r; }                   /* low word, signed */
static inline uint32_t rr_moveq(int8_t b) { return (uint32_t)(int32_t)b; }                   /* moveq: sign-extend byte */
static inline uint32_t rr_notw(uint32_t r){ return rr_wset(r, (uint16_t)~(uint16_t)r); }     /* not.w */
static inline uint32_t rr_clrw(uint32_t r){ return r & 0xffff0000u; }                        /* clr.w */
static inline uint32_t rr_swap(uint32_t r){ return (r << 16) | (r >> 16); }                  /* swap */
/* dbf dN,label: decrement dN's low word; loop while the result != -1 (0xffff). Returns true to loop. */
static inline int rr_dbf(uint32_t *r) { uint16_t w = (uint16_t)(*r) - 1; *r = rr_wset(*r, w); return w != 0xffff; }

/* ---- blit primitives shared by every band (the 68k blit tails are hand-inlined copies of these).
 * a0 = dst cursor, a1 = src cursor; both are post-incremented like the 68k `(an)+` addressing. ---- */

/* move.l (a1)+,(a0)+ : copy one long (half a 4-plane, 16-pixel column) src->dst, advance both. */
static inline void rr_copy_long(uint8_t *img, uint32_t *a0, uint32_t *a1) {
    wr32(img + *a0, be32(img + *a1)); *a1 += 4; *a0 += 4;
}
/* move.l (a1)+,(a0); and.l d3,(a0)+ : copy one long masked by the full-long edge mask d3 (A/C/E). */
static inline void rr_copy_long_masked(uint8_t *img, uint32_t *a0, uint32_t *a1, uint32_t d3) {
    wr32(img + *a0, be32(img + *a1) & d3); *a1 += 4; *a0 += 4;
}
/* move.l d5,(a0)+; move.l d6,(a0)+ : write one forward shoulder-fill pair (interior/edge planes). */
static inline void rr_fill_pair(uint8_t *img, uint32_t *a0, uint32_t d5, uint32_t d6) {
    wr32(img + *a0, d5); *a0 += 4; wr32(img + *a0, d6); *a0 += 4;
}
/* move.l d6,-(a0); move.l d5,-(a0) : write one backward shoulder-fill pair (tail fill, predecrement). */
static inline void rr_fill_pair_rev(uint8_t *img, uint32_t *a0, uint32_t d5, uint32_t d6) {
    *a0 -= 4; wr32(img + *a0, d6); *a0 -= 4; wr32(img + *a0, d5);
}
/* Fill one full 160-byte road row forward through a2 (the 68k `moveq #9,d1; dbf` loop of ten
 * (d5,d6,d5,d6) writes). d1 is left dead by the original at every call site, so we don't model it. */
static inline void rr_fill_full_row(uint8_t *img, uint32_t *a2, uint32_t d5, uint32_t d6) {
    for (int i = 0; i < 10; i++) { rr_fill_pair(img, a2, d5, d6); rr_fill_pair(img, a2, d5, d6); }
}

#define RR_ROW_STRIDE_D2  0x00a0     /* d2 = ROW_STRIDE (160 bytes / scanline) at band entry */

/* Threaded 68000 registers that survive band-to-band (bands B/C/D share these across two loops each). */
typedef struct { uint8_t *img; uint32_t a2, a3, a4, a5, a6, d2, d7; } rr_regs;

static void rr_band_A(rr_regs *r);                                /* 0x9172 (96 rows, inline) */
static void rr_band_B(rr_regs *r, uint32_t rows_m1, int second);  /* 0x93c2 (near) / 0x948c (far) */
static void rr_band_C_near(rr_regs *r, uint32_t rows_m1);  /* 0x9582 */
static void rr_band_C_far(rr_regs *r, uint32_t rows_m1);   /* 0x96b8 (distinct fast-split + merge tail) */
static void rr_band_D(rr_regs *r, uint32_t rows_m1, int second);  /* 0x987c (near) / 0x9950 (far, ends in rts) */
static void rr_band_D_l2(rr_regs *r, uint32_t rows_m1, int second);  /* Layer-2 proper-C recreation of band D */

/* Band A (0x9172) — 96 rows, the widest branch set. Byte-exact machine model (trust anchor).
 * Inline in the original; extracted here so the band pipeline can select it like the other bands. */
static void rr_band_A(rr_regs *r) {
    uint8_t *img = r->img;
    uint32_t d0, d1, d3, d5, d6, d7, a0, a1;
    uint32_t a2 = r->a2, a3 = r->a3, a4 = r->a4, a5 = r->a5, a6 = r->a6, d2 = r->d2;
    uint32_t d4 = 0x5f;
    d7 = 0;                         /* band A never masks d0 with d7 (d7 = saved-a0 scratch there) */
L9172:
    a1 = a3; a0 = a2;
    d0 = be32(img + a5); a5 += 4;                                   /* move.l (a5)+,d0 */
    d0 = rr_wset(d0, (uint16_t)(d0 + be16(img + a4))); a4 += 2;     /* add.w (a4)+,d0 */
    d1 = 0xf & d0; d1 = rr_wset(d1, (uint16_t)(d1 << 4));           /* moveq #f; and.w d0,d1; lsl.w #4 */
    a1 += sign_ext16((uint16_t)d1);                                /* adda.w d1,a1 */
    d3 = be32(img + a1 + RR_MASK_OFF_HI);                          /* move.l 0x2808(a1),d3 */
    d1 = be16(img + a4); a4 += 2;                                  /* move.w (a4)+,d1 */
    d5 = rr_moveq((int8_t)0xff);                                   /* d5 = 0xffffffff */
    d6 = rr_notw(0);                                              /* d6 = 0x0000ffff */
    if (d0 & RR_F_PLANE_HI) d6 = rr_swap(d6);                     /* -> 0xffff0000 */
    if (!(d0 & RR_F_SPLIT_A)) goto L92d6;
    a6 += 2;
    if (d0 & RR_F_WIDE) goto L92a8;
    if (!(d0 & RR_F_SKIP_ABC)) goto L92da;
    /* 0x91b0 */
    d6 = 0;
    a1 += sign_ext16((uint16_t)d1);
    d1 = be32(img + a4); a4 += 4;                                 /* move.l (a4)+,d1 */
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));                 /* asr.w #1 */
    if (!(d0 & RR_F_PLANE_HI)) goto L9230;
    /* 0x91c0 */
    d5 = 0;
    a1 += RR_SRC_A800;
    if (be16(img + a6 - 2) != 0) a1 += RR_SRC_0A00;
    d0 = rr_wset(d0, (uint16_t)(d0 & RR_D7_WORD_MASK));
    if (rr_ws(d0) >= 0) goto L91f8;
    d1 = 0x13; d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) < 0) goto L91e6;
    d1 = 0x12; a1 += 8;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L91e6:
    do { wr32(img + a0, d6); a0 += 4; wr32(img + a0, d6); a0 += 4; }
    while (rr_dbf(&d1));                         /* dbf d1 */
    goto L91ee;
L91f8:
    a0 += sign_ext16((uint16_t)d0); d7 = a0;                      /* adda.w d0,a0; move.l a0,d7 */
    d2 = rr_wset(d2, (uint16_t)d0);                               /* move.w d0,d2 */
    d0 = rr_wset(d0, (uint16_t)(d0 - RR_ROW_STRIDE_D2));          /* subi.w #a0,d0 */
    if (rr_ws(d0) >= 0) goto L928c;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L921a;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L928c;
    goto L9224;
L921a:
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L928c;
L9224:
    do { wr32(img + a0, d6); a0 += 4; wr32(img + a0, d6); a0 += 4;
         d0 = rr_wset(d0, (uint16_t)(d0 + 8)); } while (rr_ws(d0) < 0);
    goto L928c;
L9230:
    a1 += sign_ext16(be16(img + a6 - 2));                         /* adda.w -2(a6),a1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & RR_D7_WORD_MASK));
    if (rr_ws(d0) >= 0) goto L925c;
    d1 = 0x13; d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) < 0) goto L924a;
    d1 = 0x12; a1 += 8;
    rr_copy_long(img, &a0, &a1);            /* move.l (a1)+,(a0)+ */
    rr_copy_long_masked(img, &a0, &a1, d3);       /* move.l (a1)+,(a0); and.l d3,(a0)+ */
L924a:
    do { rr_fill_pair(img, &a0, d5, d6); }
    while (rr_dbf(&d1));
    goto L91ee;
L925c:
    a0 += sign_ext16((uint16_t)d0); d7 = a0;
    d2 = rr_wset(d2, (uint16_t)d0);
    d0 = rr_wset(d0, (uint16_t)(d0 - RR_ROW_STRIDE_D2));
    if (rr_ws(d0) >= 0) goto L928c;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L927c;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long_masked(img, &a0, &a1, d3);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L928c;
    goto L9284;
L927c:
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L928c;
L9284:
    do { rr_fill_pair(img, &a0, d5, d6);
         d0 = rr_wset(d0, (uint16_t)(d0 + 8)); } while (rr_ws(d0) < 0);
L928c:
    d5 = rr_notw(0);                                              /* moveq #0,d5; not.w -> 0xffff */
    d6 = d5;                                                      /* move.l d5,d6 */
    if ((int32_t)d0 >= 0) goto L936a;                            /* tst.l d0; bpl */
    if (!(d0 & RR_F_PLANE_HI)) goto L936a;
    d5 = rr_moveq((int8_t)0xff); d6 = 0;                         /* 0x92a0 */
    goto L936a;
L92a8:
    d6 = 0;
    a1 += RR_SRC_5000;
    if (!(d0 & RR_F_SRC_400)) goto L92c6;
    a1 += RR_SRC_0400;
    if (d0 & RR_F_SRC_100) goto L92f6;
    a1 += RR_SRC_0100; d5 = 0;
    goto L92f6;
L92c6:
    if (d0 & RR_F_SRC_100) goto L92f6;
    a1 += RR_SRC_0100; d5 = rr_notw(0);                          /* moveq #0; not.w -> 0xffff */
    goto L92f6;
L92d6:
    a1 += sign_ext16((uint16_t)d1);
    a1 += sign_ext16(be16(img + a6)); a6 += 2;                   /* adda.w (a6)+,a1 */
L92da:
    if (!(d0 & RR_F_PLANE_HI)) goto L92e6;
    a1 += RR_SRC_5800;
    goto L92f6;
L92e6:
    if (!(d0 & RR_F_SRC_CONST)) goto L92f6;
    if ((int32_t)d0 < 0) goto L92f6;
    a1 = RR_CONST_5BAA;
L92f6:
    d1 = be32(img + a4); a4 += 4;                                /* move.l (a4)+,d1 */
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));                /* asr.w #1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & RR_D7_WORD_MASK));          /* andi.w #fff8 */
    if (rr_ws(d0) >= 0) goto L9328;
    a1 += 8; d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L930a;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    goto L930e;
L930a:
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L930e:
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 3));                /* asr.w #3 */
    d1 = rr_wset(d1, (uint16_t)(d1 + d0));                       /* add.w d0,d1 */
    if (rr_ws(d1) < 0) goto L931c;
    do { rr_fill_pair(img, &a0, d5, d6); }
    while (rr_dbf(&d1));                        /* dbf d1 */
L931c:
    a2 += RR_ROW_STRIDE_D2;                                      /* adda.w #a0,a2 */
    goto L9320;
L9328:
    a0 += sign_ext16((uint16_t)d0); d7 = a0;
    d2 = rr_wset(d2, (uint16_t)d0);
    d0 = rr_wset(d0, (uint16_t)(d0 - RR_ROW_STRIDE_D2));
    if (rr_ws(d0) >= 0) goto L9352;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L934e;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L9340:                                                          /* combined d0/d1 shoulder-fill loop */
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L9352;
    rr_fill_pair(img, &a0, d5, d6);
    if (rr_dbf(&d1)) goto L9340;                                /* dbf d1,$9340 */
    goto L9352;
L934e:
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L9352:
    d5 = rr_notw(0); d6 = d5;                                    /* moveq #0; not.w; move.l d5,d6 */
    if (!(d0 & RR_F_SRC_CONST)) goto L936a;
    if ((int32_t)d0 < 0) goto L936a;
    if (d0 & RR_F_PLANE_HI) goto L936a;
    d5 = rr_moveq((int8_t)0xff);
L936a:
    if (!(d0 & RR_F_WIDE)) goto L9384;
    d5 = rr_moveq((int8_t)0xff); d6 = 0;
    if (!(d0 & RR_F_SRC_100)) goto L9384;
    d5 = 0;
    if (d0 & RR_F_SRC_400) goto L9384;
    d5 = rr_notw(d5);                                           /* not.w d5 (0 -> 0xffff) */
L9384:
    a0 = d7;                                                    /* movea.l d7,a0 */
    d0 = rr_wset(d0, (uint16_t)d2);                            /* move.w d2,d0 */
    d1 = rr_swap(d1);                                          /* swap d1 */
    d2 = RR_ROW_STRIDE_D2;                                     /* move.w #a0,d2 */
L938e:
    d0 = rr_wset(d0, (uint16_t)(d0 - 8));                      /* subq.w #8,d0 */
    if (rr_ws(d0) < 0) goto L93a6;                             /* bmi */
    if (rr_ws(d0) - (int16_t)d2 >= 0) goto L93a0;             /* cmp.w d2,d0; bpl */
    rr_fill_pair_rev(img, &a0, d5, d6);              /* move.l d6,-(a0); move.l d5,-(a0) */
    if (rr_dbf(&d1)) goto L938e;            /* dbf d1,$938e */
    goto L93a6;
L93a0:
    a0 -= 8;                                                  /* subq.l #8,a0 */
    if (rr_dbf(&d1)) goto L938e;
L93a6:                                                        /* row tail: advance dst, next scanline */
L91ee:                                                        /* fill-path exits land here (d2 == 0xa0) */
    a2 += d2;                                                 /* adda.w d2,a2 */
L9320:
    if (rr_dbf(&d4)) goto L9172;
    goto done;

done:
    (void)a0; (void)a1; (void)d3; (void)d5; (void)d6; (void)d7;
    r->a2 = a2; r->a3 = a3; r->a4 = a4; r->a5 = a5; r->a6 = a6; r->d2 = d2;
}

/* Inter-band-group step (0x93ac / 0x956e / 0x9868): rewind dst up the screen, advance the source to
 * the next texture sub-block and the edge table down, and reset the width-table cursor to its base. */
static void rr_group_step(rr_regs *r) {
    r->a2 -= RR_DST_BAND_STEP;
    r->a3 += RR_SRC_BAND_STEP;
    r->a6 -= RR_EDGE_BAND_STEP;
    r->a5 = RR_WIDTH_TBL;
}

/* One selectable set of band implementations. Layer 1 (rr_band_*) is the byte-exact machine model;
 * a Layer-2 table swaps in idiomatic recreations band by band as they are verified. */
typedef struct {
    void (*band_A)(rr_regs *r);
    void (*band_B)(rr_regs *r, uint32_t rows_m1, int second);
    void (*band_C_near)(rr_regs *r, uint32_t rows_m1);
    void (*band_C_far)(rr_regs *r, uint32_t rows_m1);
    void (*band_D)(rr_regs *r, uint32_t rows_m1, int second);
} rr_bands;

/* The seven-band pipeline (0x9172..0x9a3c). a4 streams monotonically across all bands; a5/a6/d7 are
 * reset at each group step. Band A runs alone; B/C/D each run a near then a far copy per group. */
static void render_road_impl(uint8_t *image, const rr_bands *b) {
    rr_regs r = {
        .img = image,
        .a2  = draw_buffer(image) + RR_DST_ROAD_OFF,
        .a3  = be32(image + A_buf_b),
        .a4  = RR_PARAM_TBL,
        .a5  = RR_WIDTH_TBL,
        .a6  = RR_EDGE_TBL_BASE + sign_ext16(be16(image + A_road_edge_sel)),
        .d2  = RR_ROW_STRIDE_D2,
        .d7  = 0,                 /* band A never masks d0 with d7 (scratch there) */
    };

    b->band_A(&r);
    rr_group_step(&r);
    r.d7 = rr_moveq((int8_t)0xf8);   /* 0xfffffff8; d7.w=0xfff8 from the first step onward */

    b->band_B(&r, 0x04, 0);   /* 0x93c2 (near copy) */
    b->band_B(&r, 0x5a, 1);   /* 0x948c (far copy: distinct wider blit tail) */
    rr_group_step(&r);        /* 0x956e */
    b->band_C_near(&r, 0x05); /* 0x9582 (near copy) */
    b->band_C_far(&r, 0x59);  /* 0x96b8 (far copy: distinct fast-split + merge tail) */
    rr_group_step(&r);        /* 0x9868 */
    b->band_D(&r, 0x05, 0);   /* 0x987c (near copy) */
    b->band_D(&r, 0x59, 1);   /* 0x9950 (far copy) -> rts */
}

/* Layer 1 (trust anchor): the byte-exact 1:1 machine model, all bands. */
static const rr_bands RR_BANDS_L1 = {
    rr_band_A, rr_band_B, rr_band_C_near, rr_band_C_far, rr_band_D,
};
void g_render_road(uint8_t *image) {
    render_road_impl(image, &RR_BANDS_L1);
}

/* Layer 2: the proper-C recreation. Shares the not-yet-recreated bands with Layer 1 and swaps in the
 * idiomatic reconstructions as they are verified. Proven against the same oracle by the same battery. */
static const rr_bands RR_BANDS_L2 = {
    rr_band_A, rr_band_B, rr_band_C_near, rr_band_C_far, rr_band_D_l2,
};
void g_render_road_l2(uint8_t *image) {
    render_road_impl(image, &RR_BANDS_L2);
}

/* Word memory RMW: word[addr] &= d3.w  (68k `and.w d3,-4(a0)` masks only the high word of a long). */
static inline void rr_andw(uint8_t *img, uint32_t addr, uint32_t d3) {
    wr16(img + addr, (uint16_t)(be16(img + addr) & (uint16_t)d3));
}

/* ---- band B (0x93c2 near copy / 0x948c far copy): reg map a0=dst a1=src d0=ctrl d1=count
 * d3=mask d5/d6=fill. The two copies share the preamble + src dispatch but diverge at the blit
 * tail (near: 0x944a single masked column + shoulder fill; far: 0x9514, a wider 4-long blit with a
 * distinct full-fill path). `second` selects the far copy's tail. ---- */
static void rr_band_B(rr_regs *r, uint32_t rows_m1, int second) {
    uint8_t *img = r->img;
    uint32_t d0, d1, d3, d5, d6, a0, a1;
    uint32_t d4 = rows_m1;
L93c2:
    a1 = r->a3; a0 = r->a2;
    d0 = be32(img + r->a5); r->a5 += 4;
    d0 = rr_wset(d0, (uint16_t)(d0 + be16(img + r->a4))); r->a4 += 2;
    d1 = 0xf & d0; d1 = rr_wset(d1, (uint16_t)(d1 << 4));
    a1 += sign_ext16((uint16_t)d1);
    d1 = be16(img + r->a4); r->a4 += 2;                         /* move.w (a4)+,d1 */
    d5 = rr_clrw(rr_moveq((int8_t)0xff));                      /* moveq #ff; clr.w -> 0xffff0000 */
    d6 = rr_notw(0);                                          /* 0x0000ffff */
    d3 = rr_moveq((int8_t)0xff);                              /* moveq #ff,d3 -> 0xffffffff */
    if (d0 & RR_F_MASK_A) { d5 = 0; d3 = be32(img + a1 + RR_MASK_OFF_HI); }
    if (!(d0 & RR_F_SPLIT_B)) goto L943c;
    if (!(d0 & RR_F_SKIP_ABC)) goto L9406;
    if ((int32_t)d0 >= 0) goto L9406;                         /* tst.l d0; bpl */
    r->a6 += 2; r->a2 += r->d2; if (rr_dbf(&d4)) goto L93c2;  /* addq #2,a6; adda d2,a2; dbf */
    return;
L9406:
    r->a6 += 2;
    if (!(d0 & RR_F_WIDE)) goto L9440;
    d6 = 0; a1 += RR_SRC_4700;
    if (!(d0 & RR_F_SRC_400)) goto L942c;
    a1 += RR_SRC_0400;
    if (d0 & RR_F_SRC_100) goto Ltail;
    a1 = RR_CONST_5B7A; goto Ltail;
L942c:
    d5 = rr_notw(d5);                                         /* not.w d5 */
    if (d0 & RR_F_SRC_100) goto Ltail;
    a1 = RR_CONST_5B9A; goto Ltail;
L943c:
    a1 += sign_ext16((uint16_t)d1);
    a1 += sign_ext16(be16(img + r->a6)); r->a6 += 2;
L9440:
    if (!(d0 & RR_F_PLANE_HI)) goto Ltail;
    a1 += RR_SRC_5800;
Ltail:
    if (second) goto L9514;

    /* --- near copy tail (0x944a): +8 both, single masked column, shoulder fill --- */
    a0 += 8; a1 += 8;                                         /* addq.l #8 both */
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));            /* asr.w #1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));                /* and.w d7,d0 */
    a0 += sign_ext16((uint16_t)d0);                          /* adda.w d0,a0 */
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L946c;
    rr_fill_full_row(img, &r->a2, d5, d6);                /* moveq #9,d1; dbf: full-width fill of a2 */
    if (rr_dbf(&d4)) goto L93c2;
    return;
L946c:
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));               /* sub.w d2,d0 */
    if (rr_ws(d0) >= 0) goto L9484;
    rr_copy_long(img, &a0, &a1);       /* move.l (a1)+,(a0)+ */
    rr_andw(img, a0 - 4, d3);                               /* and.w d3,-4(a0) */
    rr_copy_long(img, &a0, &a1);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L9484;
    do {
        rr_fill_pair(img, &a0, d5, d6);
        d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    } while (rr_ws(d0) < 0);
L9484:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L93c2;
    (void)a0; (void)a1;
    return;

    /* --- far copy tail (0x9514): no +8, asr/mask then either a dbf-counted fill (d0<0) or a
     * wider 4-long masked blit + shoulder fill (d0>=0) --- */
L9514:
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));            /* asr.w #1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));                /* and.w d7,d0 */
    if (rr_ws(d0) >= 0) goto L953c;                          /* bpl */
    d1 = 0x13;                                               /* moveq #$13,d1 */
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) < 0) goto L952c;                           /* bmi */
    d1 = 0x12; a1 += 8;                                      /* moveq #$12,d1; addq.l #8,a1 */
    rr_copy_long(img, &a0, &a1);        /* move.l (a1)+,(a0)+ */
    rr_andw(img, a0 - 4, d3);                                /* and.w d3,-4(a0) */
    rr_copy_long(img, &a0, &a1);
L952c:
    do { rr_fill_pair(img, &a0, d5, d6); }
    while (rr_dbf(&d1));                                     /* dbf d1,$952c */
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L93c2;
    return;
L953c:
    a0 += sign_ext16((uint16_t)d0);                          /* adda.w d0,a0 */
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));                /* sub.w d2,d0 */
    if (rr_ws(d0) >= 0) goto L9568;                          /* bpl -> row done */
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) >= 0) goto L9558;                          /* bpl */
    rr_copy_long(img, &a0, &a1);        /* move.l (a1)+,(a0)+ x4, 3rd masked */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_andw(img, a0 - 4, d3);                                /* and.w d3,-4(a0) */
    rr_copy_long(img, &a0, &a1);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) >= 0) goto L9568;                          /* bpl */
    goto L9560;
L9558:
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) >= 0) goto L9568;                          /* bpl */
L9560:
    do {
        rr_fill_pair(img, &a0, d5, d6);
        d0 = rr_wset(d0, (uint16_t)(d0 + 8));               /* addq.w #8,d0 */
    } while (rr_ws(d0) < 0);                                /* bmi $9560 */
L9568:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L93c2;
    (void)a0; (void)a1;
}

/* ---- band C near copy (0x9582) ---- */
static void rr_band_C_near(rr_regs *r, uint32_t rows_m1) {
    uint8_t *img = r->img;
    uint32_t d0, d1, d3, d5, d6, a0, a1;
    uint32_t d4 = rows_m1;
L9582:
    a1 = r->a3; a0 = r->a2;
    d0 = be32(img + r->a5); r->a5 += 4;
    d0 = rr_wset(d0, (uint16_t)(d0 + be16(img + r->a4))); r->a4 += 2;
    d1 = 0xf & d0; d1 = rr_wset(d1, (uint16_t)(d1 << 4));
    a1 += sign_ext16((uint16_t)d1);
    d1 = be16(img + r->a4); r->a4 += 2;
    d3 = be32(img + a1 + RR_MASK_OFF_LO);                       /* move.l 0x2800(a1),d3 */
    d5 = rr_moveq((int8_t)0xff);                               /* 0xffffffff */
    d6 = rr_notw(0);                                          /* 0x0000ffff */
    if (d0 & RR_F_PLANE_HI) d6 = rr_swap(d6);
    if (!(d0 & RR_F_SPLIT_C)) goto L9666;
    r->a6 += 2;
    if (d0 & RR_F_WIDE) goto L9638;
    if (!(d0 & RR_F_SKIP_D)) goto L966a;
    /* 0x95c0 */
    d6 = 0;
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));            /* asr.w #1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));                /* and.w d7,d0 */
    if (rr_ws(d0) >= 0) goto L95d2;
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L9582;
    return;
L95d2:
    a1 += sign_ext16((uint16_t)d1);
    a0 += sign_ext16((uint16_t)d0);
    d1 = rr_wset(d1, (uint16_t)d0);                          /* move.w d0,d1 */
    if (!(d0 & RR_F_PLANE_HI)) goto L95fa;
    d5 = 0; a1 += RR_SRC_A800;
    if (be16(img + r->a6 - 2) != 0) a1 += RR_SRC_0A00;
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));                /* sub.w d2,d0 */
    if (rr_ws(d0) >= 0) goto L9622;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    goto L9608;
L95fa:
    a1 += sign_ext16(be16(img + r->a6 - 2));
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));
    if (rr_ws(d0) >= 0) goto L9622;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long_masked(img, &a0, &a1, d3);   /* move.l(a1)+,(a0); and.l d3,(a0)+ */
L9608:
    d1 = rr_wset(d1, (uint16_t)((uint16_t)d1 >> 3));         /* lsr.w #3,d1 */
    d1 = rr_wset(d1, (uint16_t)(d1 - 1));                    /* subq.w #1,d1 */
    if (rr_ws(d1) < 0) goto L9618;
    a0 = r->a2;
    do { rr_fill_pair(img, &a0, d5, d6); } while (rr_dbf(&d1));
L9618:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L9582;
    return;
L9622:
    rr_fill_full_row(img, &r->a2, d5, d6);                /* moveq #9,d1; dbf: full-width fill of a2 */
    if (rr_dbf(&d4)) goto L9582;
    return;
L9638:
    d6 = 0; a1 += RR_SRC_3E00;
    if (!(d0 & RR_F_SRC_400)) goto L9656;
    a1 += RR_SRC_0400;
    if (d0 & RR_F_SRC_100) goto L9686;
    a1 += RR_SRC_0100; d5 = 0; goto L9686;
L9656:
    if (d0 & RR_F_SRC_100) goto L9686;
    a1 += RR_SRC_0100; d5 = 0; d5 = rr_notw(d5); goto L9686;
L9666:
    a1 += sign_ext16((uint16_t)d1);
    a1 += sign_ext16(be16(img + r->a6)); r->a6 += 2;
L966a:
    if (!(d0 & RR_F_PLANE_HI)) goto L9676;
    a1 += RR_SRC_5800; goto L9686;
L9676:
    if (!(d0 & RR_F_SRC_CONST)) goto L9686;
    if ((int32_t)d0 < 0) goto L9686;
    a1 = RR_CONST_5BAA;
L9686:
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));           /* asr.w #1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));               /* and.w d7,d0 */
    d0 = rr_wset(d0, (uint16_t)(d0 - 8));                   /* subq.w #8,d0 */
    if (rr_ws(d0) >= 0) goto L969e;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) < 0) goto L96b0;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L9582;
    return;
L969e:
    a0 += sign_ext16((uint16_t)d0);
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));
    if (rr_ws(d0) >= 0) goto L96b0;
    rr_fill_pair(img, &a0, d5, d6);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L96b0;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L96b0:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L9582;
    (void)a0; (void)a1; (void)d3;
}

/* ---- band C far copy (0x96b8) ---- byte-identical preamble + WIDE/no-split/src-select to the
 * near copy, but a distinct fast-split path (0x96f6: does the src select first, consumes one extra
 * a4 param word) and a distinct merge tail (0x9808: reads an extra param word, then a wider
 * bidirectional blit). Falls through to the C->D group step (no rts). ---- */
static void rr_band_C_far(rr_regs *r, uint32_t rows_m1) {
    uint8_t *img = r->img;
    uint32_t d0, d1, d3, d5, d6, a0, a1;
    uint32_t d4 = rows_m1;
L96b8:
    a1 = r->a3; a0 = r->a2;
    d0 = be32(img + r->a5); r->a5 += 4;
    d0 = rr_wset(d0, (uint16_t)(d0 + be16(img + r->a4))); r->a4 += 2;
    d1 = 0xf & d0; d1 = rr_wset(d1, (uint16_t)(d1 << 4));
    a1 += sign_ext16((uint16_t)d1);
    d1 = be16(img + r->a4); r->a4 += 2;
    d3 = be32(img + a1 + RR_MASK_OFF_LO);                       /* move.l 0x2800(a1),d3 */
    d5 = rr_moveq((int8_t)0xff);                               /* 0xffffffff */
    d6 = rr_notw(0);                                          /* 0x0000ffff */
    if (d0 & RR_F_PLANE_HI) d6 = rr_swap(d6);
    if (!(d0 & RR_F_SPLIT_C)) goto L97e8;
    r->a6 += 2;
    if (d0 & RR_F_WIDE) goto L97ba;
    if (!(d0 & RR_F_SKIP_D)) goto L97ec;
    /* 0x96f6 fast edge-split: src select FIRST, extra a4 += 2 vs the near copy */
    a1 += sign_ext16((uint16_t)d1);                          /* adda.w d1,a1 */
    r->a4 += 2;                                              /* addq.l #2,a4 (far-only) */
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));            /* asr.w #1 */
    d6 = 0;
    if (!(d0 & RR_F_PLANE_HI)) goto L9750;
    /* 0x9704 (bit27 set) */
    d5 = 0; a1 += RR_SRC_A800;
    if (be16(img + r->a6 - 2) != 0) a1 += RR_SRC_0A00;
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));                /* and.w d7,d0 */
    if (rr_ws(d0) >= 0) goto L972e;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) < 0) goto L9724;
    a1 += 8;                                                 /* addq.l #8,a1 */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L9724:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L96b8;
    return;
L972e:
    a0 += sign_ext16((uint16_t)d0);
    d1 = rr_wset(d1, (uint16_t)d0);                          /* move.w d0,d1 */
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));                /* sub.w d2,d0 */
    if (rr_ws(d0) >= 0) goto L97a4;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) >= 0) goto L9748;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    goto L978a;
L9748:
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    goto L978a;
L9750:                                                       /* 0x9750 (bit27 clear) */
    a1 += sign_ext16(be16(img + r->a6 - 2));                 /* adda.w -2(a6),a1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));                /* and.w d7,d0 */
    if (rr_ws(d0) >= 0) goto L976c;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) < 0) goto L9762;
    a1 += 8;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L9762:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L96b8;
    return;
L976c:
    a0 += sign_ext16((uint16_t)d0);
    d1 = rr_wset(d1, (uint16_t)d0);                          /* move.w d0,d1 */
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));                /* sub.w d2,d0 */
    if (rr_ws(d0) >= 0) goto L97a4;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));
    if (rr_ws(d0) >= 0) goto L9784;
    rr_copy_long(img, &a0, &a1);
    rr_copy_long_masked(img, &a0, &a1, d3);   /* move.l(a1)+,(a0); and.l d3,(a0)+ */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    goto L978a;
L9784:
    rr_copy_long(img, &a0, &a1);
    rr_copy_long_masked(img, &a0, &a1, d3);
L978a:
    d1 = rr_wset(d1, (uint16_t)((uint16_t)d1 >> 3));         /* lsr.w #3,d1 */
    d1 = rr_wset(d1, (uint16_t)(d1 - 1));                    /* subq.w #1,d1 */
    if (rr_ws(d1) < 0) goto L979a;
    a0 = r->a2;
    do { rr_fill_pair(img, &a0, d5, d6); } while (rr_dbf(&d1));
L979a:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L96b8;
    return;
L97a4:                                                       /* full-width fill */
    rr_fill_full_row(img, &r->a2, d5, d6);                /* moveq #9,d1; dbf: full-width fill of a2 */
    if (rr_dbf(&d4)) goto L96b8;
    return;
L97ba:                                                       /* WIDE src select (identical to near) */
    d6 = 0; a1 += RR_SRC_3E00;
    if (!(d0 & RR_F_SRC_400)) goto L97d8;
    a1 += RR_SRC_0400;
    if (d0 & RR_F_SRC_100) goto L9808;
    a1 += RR_SRC_0100; d5 = 0; goto L9808;
L97d8:
    if (d0 & RR_F_SRC_100) goto L9808;
    a1 += RR_SRC_0100; d5 = 0; d5 = rr_notw(d5); goto L9808;
L97e8:                                                       /* no-split (a6-add) */
    a1 += sign_ext16((uint16_t)d1);
    a1 += sign_ext16(be16(img + r->a6)); r->a6 += 2;
L97ec:                                                       /* hi/const src select */
    if (!(d0 & RR_F_PLANE_HI)) goto L97f8;
    a1 += RR_SRC_5800; goto L9808;
L97f8:
    if (!(d0 & RR_F_SRC_CONST)) goto L9808;
    if ((int32_t)d0 < 0) goto L9808;
    a1 = RR_CONST_5BAA;
L9808:                                                       /* far merge/blit tail (distinct) */
    d1 = be16(img + r->a4); r->a4 += 2;                      /* move.w (a4)+,d1 (far-only) */
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));            /* asr.w #1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));                /* and.w d7,d0 */
    if (rr_ws(d0) >= 0) goto L9822;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) < 0) goto L981a;
    a1 += 8;                                                 /* addq.l #8,a1 */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L981a:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L96b8;
    return;
L9822:
    a0 += sign_ext16((uint16_t)d0);                          /* adda.w d0,a0 */
    d3 = rr_wset(d3, (uint16_t)d0);                          /* move.w d0,d3 (near uses d1) */
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));                /* sub.w d2,d0 */
    if (rr_ws(d0) < 0) goto L9846;                           /* bmi */
    d0 = rr_wset(d0, (uint16_t)(d0 - 8));                    /* subq.w #8,d0 */
    if (rr_ws(d0) < 0) goto L984c;                           /* bmi */
    r->a2 += r->d2;                                          /* adda.w d2,a2 */
    d0 = rr_wset(d0, (uint16_t)((uint16_t)d0 >> 3));         /* lsr.w #3,d0 */
    d1 = rr_wset(d1, (uint16_t)(d1 - d0));                   /* sub.w d0,d1 */
    if (rr_ws(d1) < 0) goto L9840;                           /* bmi */
    a0 = r->a2;
L9838:
    rr_fill_pair_rev(img, &a0, d5, d6);              /* move.l d6,-(a0); move.l d5,-(a0) */
    if (rr_dbf(&d1)) goto L9838;                             /* dbf d1,$9838 */
L9840:
    if (rr_dbf(&d4)) goto L96b8;
    return;
L9846:
    d0 = 0;                                                  /* moveq #0,d0 (clears the full register) */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L984c:
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    a0 -= sign_ext16((uint16_t)d0);                          /* suba.w d0,a0 */
L9856:
    d3 = rr_wset(d3, (uint16_t)(d3 - 8));                    /* subq.w #8,d3 */
    if (rr_ws(d3) < 0) goto L9862;                           /* bmi */
    rr_fill_pair_rev(img, &a0, d5, d6);              /* move.l d6,-(a0); move.l d5,-(a0) */
    if (rr_dbf(&d1)) goto L9856;                             /* dbf d1,$9856 (re-runs subq/suba) */
L9862:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto L96b8;
    (void)a0; (void)a1;
}

/* ---- band D (0x987c near copy / 0x9950 far copy; the far copy's last dbf falls through to rts).
 * The two copies share the preamble + src dispatch but diverge at the blit tail (0x9914 vs 0x99f0);
 * `second` selects the far copy's wider blit tail. ---- */
static void rr_band_D(rr_regs *r, uint32_t rows_m1, int second) {
    uint8_t *img = r->img;
    uint32_t d0, d1, d3, d5, d6, a0, a1;
    uint32_t d4 = rows_m1;
Ltop:
    a1 = r->a3; a0 = r->a2;
    d0 = be32(img + r->a5); r->a5 += 4;
    d0 = rr_wset(d0, (uint16_t)(d0 + be16(img + r->a4))); r->a4 += 2;
    d1 = 0xf & d0; d1 = rr_wset(d1, (uint16_t)(d1 << 4));
    a1 += sign_ext16((uint16_t)d1);
    d1 = be16(img + r->a4); r->a4 += 2;
    d5 = rr_clrw(rr_moveq((int8_t)0xff));                       /* 0xffff0000 */
    d6 = rr_notw(0);                                          /* 0x0000ffff */
    d3 = rr_moveq((int8_t)0xff);                              /* 0xffffffff */
    if (d0 & RR_F_MASK_A2) { d5 = 0; d3 = be32(img + a1 + RR_MASK_OFF_LO); }
    if (!(d0 & RR_F_SPLIT_D)) goto L98f8;
    if (!(d0 & RR_F_SKIP_D)) goto L98c0;
    if ((int32_t)d0 >= 0) goto L98c0;
    r->a6 += 2; r->a2 += r->d2; if (rr_dbf(&d4)) goto Ltop;
    return;
L98c0:
    r->a6 += 2;
    if (!(d0 & RR_F_WIDE)) goto L98fc;
    d5 = 0; d6 = 0; a1 += RR_SRC_3500;
    if (!(d0 & RR_F_SRC_400)) goto L98e8;
    a1 += RR_SRC_0400;
    if (d0 & RR_F_SRC_100) goto L9906;
    a1 = RR_CONST_5B7A; goto L9906;
L98e8:
    d5 = rr_notw(d5);
    if (d0 & RR_F_SRC_100) goto L9906;
    a1 = RR_CONST_5B9A; goto L9906;
L98f8:
    a1 += sign_ext16((uint16_t)d1);
    a1 += sign_ext16(be16(img + r->a6)); r->a6 += 2;
L98fc:
    if (!(d0 & RR_F_PLANE_HI)) goto L9906;
    a1 += RR_SRC_5800;
L9906:
    d0 = rr_wset(d0, (uint16_t)(rr_ws(d0) >> 1));            /* asr.w #1 */
    d0 = rr_wset(d0, (uint16_t)(d0 & r->d7));                /* and.w d7,d0 */
    if (second) goto D2_tail;

    /* --- near copy tail (0x990a) --- */
    if (rr_ws(d0) >= 0) goto L9914;
    r->a2 += r->d2; if (rr_dbf(&d4)) goto Ltop;
    return;
L9914:                                                       /* single masked 2-long blit + fill */
    a0 += sign_ext16((uint16_t)d0);
    d1 = rr_wset(d1, (uint16_t)d0);                          /* move.w d0,d1 */
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));                /* sub.w d2,d0 */
    if (rr_ws(d0) >= 0) goto L993c;
    rr_copy_long(img, &a0, &a1);
    rr_andw(img, a0 - 4, d3);                                /* and.w d3,-4(a0) */
    rr_copy_long(img, &a0, &a1);
    d1 = rr_wset(d1, (uint16_t)((uint16_t)d1 >> 3));         /* lsr.w #3,d1 */
    d1 = rr_wset(d1, (uint16_t)(d1 - 1));                    /* subq.w #1 */
    if (rr_ws(d1) < 0) goto L9934;
    a0 = r->a2;
    do { rr_fill_pair(img, &a0, d5, d6); } while (rr_dbf(&d1));
L9934:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto Ltop;
    return;
L993c:
    rr_fill_full_row(img, &r->a2, d5, d6);                /* moveq #9,d1; dbf: full-width fill of a2 */
    if (rr_dbf(&d4)) goto Ltop;
    return;

    /* --- far copy tail (0x99dc) --- */
D2_tail:
    if (rr_ws(d0) >= 0) goto L99f0;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) < 0) goto L99e8;
    a1 += 8;                                                 /* addq.l #8,a1 */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
L99e8:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto Ltop;
    return;
L99f0:
    a0 += sign_ext16((uint16_t)d0);                          /* adda.w d0,a0 */
    d1 = rr_wset(d1, (uint16_t)d0);                          /* move.w d0,d1 */
    d0 = rr_wset(d0, (uint16_t)(d0 - r->d2));                /* sub.w d2,d0 */
    if (rr_ws(d0) >= 0) goto L9a2a;
    d0 = rr_wset(d0, (uint16_t)(d0 + 8));                    /* addq.w #8,d0 */
    if (rr_ws(d0) >= 0) goto L9a0a;
    rr_copy_long(img, &a0, &a1);        /* move.l(a1)+,(a0)+ */
    rr_andw(img, a0 - 4, d3);                                /* and.w d3,-4(a0) */
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    rr_copy_long(img, &a0, &a1);
    goto L9a12;
L9a0a:
    rr_copy_long(img, &a0, &a1);
    rr_andw(img, a0 - 4, d3);
    rr_copy_long(img, &a0, &a1);
L9a12:
    d1 = rr_wset(d1, (uint16_t)((uint16_t)d1 >> 3));         /* lsr.w #3,d1 */
    d1 = rr_wset(d1, (uint16_t)(d1 - 1));                    /* subq.w #1 */
    if (rr_ws(d1) < 0) goto L9a22;
    a0 = r->a2;
    do { rr_fill_pair(img, &a0, d5, d6); } while (rr_dbf(&d1));
L9a22:
    r->a2 += r->d2; if (rr_dbf(&d4)) goto Ltop;
    return;
L9a2a:
    rr_fill_full_row(img, &r->a2, d5, d6);                /* moveq #9,d1; dbf: full-width fill of a2 */
    if (rr_dbf(&d4)) goto Ltop;
    return;
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

/* signed low-word result of a 68k word op (sub.w / add.w) — wraps mod 2^16, then bit-15 sign. */
static inline int16_t rr_wsub(uint16_t a, uint16_t b) { return (int16_t)(uint16_t)(a - b); }
static inline int16_t rr_wadd(uint16_t a, uint16_t b) { return (int16_t)(uint16_t)(a + b); }

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
