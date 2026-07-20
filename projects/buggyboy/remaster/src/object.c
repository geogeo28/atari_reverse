/* object.c — remaster of draw_object (recreate's g_draw_object @0x1087e) and its blit_obj_* /
 * objd_* solid-fill helpers (@0x10bdc..).
 *
 * draw_object scales + positions the one scaled roadside object (the near "billboard") from the road
 * control table, then paints it with solid scale-fills and antialiased edge cells. It scans the
 * control table (build_road_geometry's output — the same table render_road reads) for the object's
 * consecutive visible rows, tracks the running screen edges (max left / min right) and per-edge
 * scanline offsets, optionally clears + paints a centre band, and dispatches to the near/far
 * left/right blits (plus a second "scale2" pass). recreate stashes the derived geometry in an A_obj_*
 * scratch block; here those are plain locals.
 *
 * Byte-for-byte identical output to recreate's core (see test/test_object.py).
 */
#include "game.h"
#include "screen.h"
#include "st.h"

#define OBJ_FULL_CELLS     10       /* full-width fill: 10 * 16-byte writes = one 160-byte scanline */
#define OBJ_ROW_UP         0xa0     /* 160 bytes: one scanline up */
#define OBJ_ROAD_START_OFF 0x3480   /* draw-buffer offset where the road band begins */
#define OBJ_ROAD_ROWS      0x54     /* max scanline rows walked (84) */
#define COL_ALIGN          0xfff8   /* x/2 with the low 3 bits cleared (8-byte cell) */

/* Byte-aligned draw column from a screen x: x/2 with the low 3 bits cleared (8-byte cell). */
static uint16_t obj_aligned_col(uint16_t x) {
    return (uint16_t)((int16_t)x >> 1) & (uint16_t)COL_ALIGN;
}

/* Solid full-width row: 10 two-longword colour cells. */
static void full_row(Framebuffer *fb, Offset dst, Plane4 fill_lo, Plane4 fill_hi) {
    for (int cell = 0; cell < OBJ_FULL_CELLS; cell++, dst += 16) {
        wr32(fb->px + dst, fill_lo);     wr32(fb->px + dst + 4, fill_hi);
        wr32(fb->px + dst + 8, fill_lo); wr32(fb->px + dst + 12, fill_hi);
    }
}

/* One left-anchored row at row base `dst`, screen x. Returns the status word the caller chains on:
 * the column off-left, or (edge-width) when full, or 0xffff/mask when masked. */
static uint32_t row_left(const ObjectInput *in, Framebuffer *fb, Offset dst, uint16_t x,
                         int16_t width, Plane4 fill_lo, Plane4 fill_hi) {
    uint16_t half_x   = (uint16_t)((int16_t)x >> 1);
    uint16_t edge_col = half_x & (uint16_t)COL_ALIGN;

    if ((int16_t)edge_col < 0) return edge_col;            /* off the left edge: no draw */
    if ((int16_t)(edge_col - (uint16_t)width) >= 0) {      /* fully inside: solid fill */
        full_row(fb, dst, fill_lo, fill_hi);
        return (uint32_t)(uint16_t)(edge_col - (uint16_t)width);
    }
    /* straddling the edge: masked edge cell + solid interior to its left */
    Plane4 edge_mask = be32(in->blit_mask_l + ((x & 0xf) << 2));
    Offset edge_ptr = dst + sx16(edge_col);
    wr32(fb->px + edge_ptr,     (be32(fb->px + edge_ptr)     & edge_mask) | (fill_lo & ~edge_mask));
    wr32(fb->px + edge_ptr + 4, (be32(fb->px + edge_ptr + 4) & edge_mask) | (fill_hi & ~edge_mask));

    uint16_t interior_cells = half_x >> 3;
    if (interior_cells == 0) return edge_mask;
    Offset interior_ptr = dst;
    for (uint16_t cell = 0; cell < interior_cells; cell++, interior_ptr += 8) {
        wr32(fb->px + interior_ptr, fill_lo); wr32(fb->px + interior_ptr + 4, fill_hi);
    }
    return 0xffff;
}

/* One right-anchored row. Off-right fills the whole row; inside the width it draws a masked edge cell
 * plus a solid interior extending rightward. */
static void row_right(const ObjectInput *in, Framebuffer *fb, Offset dst, uint16_t x,
                      int16_t width, Plane4 fill_lo, Plane4 fill_hi) {
    uint16_t col = obj_aligned_col(x);

    if ((int16_t)col < 0) { full_row(fb, dst, fill_lo, fill_hi); return; }  /* off the right edge */
    if ((int16_t)(col - (uint16_t)width) >= 0) return;                      /* past the width */

    Plane4 edge_mask = be32(in->blit_mask_r + ((x & 0xf) << 2));
    Offset edge_ptr = dst + sx16(col);
    wr32(fb->px + edge_ptr,     (be32(fb->px + edge_ptr)     & edge_mask) | (fill_lo & ~edge_mask));
    wr32(fb->px + edge_ptr + 4, (be32(fb->px + edge_ptr + 4) & edge_mask) | (fill_hi & ~edge_mask));

    int16_t remaining = (int16_t)(col - (uint16_t)width) + 8;
    Offset interior_ptr = edge_ptr + 8;
    for (; remaining < 0; remaining += 8, interior_ptr += 8) {
        wr32(fb->px + interior_ptr, fill_lo); wr32(fb->px + interior_ptr + 4, fill_hi);
    }
}

/* ---- near variants: fixed x, straight vertical column. Ln returns the last row's status. ---- */

static uint32_t blit_obj_Ln(const ObjectInput *in, Framebuffer *fb, int16_t width, uint16_t row_off,
                            uint16_t x, Plane4 fill_lo, Plane4 fill_hi, uint16_t rows_m1) {
    Offset dst = sx16(row_off);
    int rows = (int16_t)rows_m1 + 1;
    uint16_t edge_col = obj_aligned_col(x);
    if ((int16_t)edge_col < 0) return edge_col;
    int full = (int16_t)(edge_col - (uint16_t)width) >= 0;
    int32_t stride = full ? -(int32_t)width : -(int32_t)OBJ_ROW_UP;

    uint32_t status = 0;
    for (int row = 0; row < rows; row++, dst = (Offset)((int32_t)dst + stride))
        status = row_left(in, fb, dst, x, width, fill_lo, fill_hi);
    return status;
}

static void blit_obj_Rn(const ObjectInput *in, Framebuffer *fb, int16_t width, uint16_t row_off,
                        uint16_t x, Plane4 fill_lo, Plane4 fill_hi, uint16_t rows_m1) {
    Offset dst = sx16(row_off);
    int rows = (int16_t)rows_m1 + 1;
    uint16_t col = obj_aligned_col(x);
    int32_t stride = ((int16_t)col < 0) ? -(int32_t)width : -(int32_t)OBJ_ROW_UP;
    for (int row = 0; row < rows; row++, dst = (Offset)((int32_t)dst + stride))
        row_right(in, fb, dst, x, width, fill_lo, fill_hi);
}

/* ---- far variants: x slants by one per row, stride = object width. ---- */

static uint32_t blit_obj_Lf(const ObjectInput *in, Framebuffer *fb, int16_t width, uint16_t row_off,
                            uint16_t x, Plane4 fill_lo, Plane4 fill_hi, uint16_t rows_m1) {
    Offset dst = sx16(row_off);
    uint16_t cur_x = x;
    int rows = (int16_t)rows_m1 + 1;
    uint32_t status = 0;
    for (int row = 0; row < rows; row++, dst = (Offset)((int32_t)dst - width), cur_x = (uint16_t)(cur_x - 1))
        status = row_left(in, fb, dst, cur_x, width, fill_lo, fill_hi);
    return status;
}

static void blit_obj_Rf(const ObjectInput *in, Framebuffer *fb, int16_t width, uint16_t row_off,
                        uint16_t x, Plane4 fill_lo, Plane4 fill_hi, uint16_t rows_m1) {
    Offset dst = sx16(row_off);
    uint16_t cur_x = x;
    int rows = (int16_t)rows_m1 + 1;
    for (int row = 0; row < rows; row++, dst = (Offset)((int32_t)dst - width), cur_x = (uint16_t)(cur_x + 1))
        row_right(in, fb, dst, cur_x, width, fill_lo, fill_hi);
}

/* ---- road-walk variants (the scale2 second pass): blit the object down the curving road, x per row
 * from the road control table's paired shorts [flag, x-offset] plus a per-variant linear ramp. ---- */
static void road_walk(const ObjectInput *in, Framebuffer *fb, int16_t width, Plane4 fill_lo,
                      Plane4 fill_hi, int is_left, int ramp_mul, int ramp_add) {
    Offset dst = OBJ_ROAD_START_OFF;
    uint32_t tbl = 0;
    int counter = OBJ_ROAD_ROWS;

    while ((int16_t)be16(in->width_tbl + tbl) >= 0) {      /* skip leading inactive rows */
        tbl += 4; dst = (Offset)((int32_t)dst - width);
        if (--counter < 0) return;
    }
    for (;;) {
        if ((int16_t)be16(in->width_tbl + tbl) >= 0) return;   /* end of the active band */
        int16_t x_off = (int16_t)be16(in->width_tbl + tbl + 2);
        uint16_t x = (uint16_t)(x_off + counter * ramp_mul + ramp_add);
        tbl += 4;
        if (is_left) row_left(in, fb, dst, x, width, fill_lo, fill_hi);
        else         row_right(in, fb, dst, x, width, fill_lo, fill_hi);
        dst = (Offset)((int32_t)dst - width);
        if (--counter < 0) return;
    }
}

/* ---- draw_object geometry helpers (@0x1087e) ---- */
#define OBJD_SCAN_ROWS   0x5f
#define OBJD_TOP_CLEAR   0x4100      /* pre-scan clear ends here (predecrement) */
#define OBJD_TOP_ROWS    0x4a        /* pre-scan clear dbf count */
#define OBJD_TOP_LONGS   8           /* longwords cleared per pre-scan row */
#define OBJD_BAND_LONGS  10          /* longwords per scale2 clear / centre-band row (40 bytes) */
#define OBJD_BASE_ROW    0x59        /* base_off = (this - i/2) * width */
#define OBJD_CENTER_SPAN 0x6b        /* centre-band row-count derivation */
#define OBJD_CENTER_BIAS (-0x2a)     /* centre-band row-count bias (moveq #$d6 sign-extended) */
#define OBJD_CLEAR_TAIL  0xa8        /* added to the clear count when the row past the object is visible */
#define OBJD_F_LEFT      0x40000000u
#define OBJD_F_RIGHT     0x20000000u
#define OBJD_F_FAR       0x10000000u
#define OBJD_F_SCALE2    0x08000000u
#define OBJD_WIDTH       0xa0        /* object width for every blit */
#define OBJD_LE_BIAS     0x36        /* left-edge screen bias */
#define OBJD_RE_BIAS     0x109       /* right-edge screen bias */
#define OBJD_ROW_MAX     0xc7        /* (this - row) * width = scanline offset */
#define OBJD_VPOS_CLAMP  0x54
#define OBJD_VPOS_BIAS   0x73

static uint16_t objd_row_off(uint16_t row) {
    return (uint16_t)((uint16_t)(OBJD_ROW_MAX - row) * OBJD_WIDTH);
}
static uint16_t objd_vpos(uint16_t row, int scale2) {
    if (scale2) {
        uint16_t r = (uint16_t)(OBJD_SCAN_ROWS - row);
        return (uint16_t)(0xf + r + (r >> 1));
    }
    int16_t t = (int16_t)(OBJD_SCAN_ROWS - row);
    if (t >= OBJD_VPOS_CLAMP) t = OBJD_VPOS_CLAMP;         /* cmpi #$54; bmi keeps */
    return (uint16_t)(t + OBJD_VPOS_BIAS - row);
}
/* Write `longs` predecrement longwords per row for (rows+1) rows, alternating hi/lo (hi first).
 * (Param names + the (j&1)?lo:hi selection are recreate's; the call sites pass them accordingly.) */
static Offset objd_fill_down(Framebuffer *fb, Offset dst_cur, int rows, int longs, Plane4 hi, Plane4 lo) {
    for (int r = 0; r <= rows; r++)
        for (int j = 0; j < longs; j++) { dst_cur -= 4; wr32(fb->px + dst_cur, (j & 1) ? lo : hi); }
    return dst_cur;
}

/* The centre/near fill is a two-longword (4-plane) pattern chosen by the shade sign: neutral when
 * shade == 0, else a one-plane pattern that leans left/right. Returns the pair (first, second). */
static void objd_shade_fill(int16_t shade, Plane4 *first, Plane4 *second) {
    *first = 0xffffffffu; *second = 0xffff0000u;           /* shade == 0 */
    if (shade > 0)      { *first = 0;           *second = 0x0000ffffu; }
    else if (shade < 0) { *first = 0x0000ffffu; *second = 0x0000ffffu; }
}

void rm_draw_object(const ObjectInput *in, Framebuffer *fb) {
    uint32_t width_cur = 0;                                /* offset into in->width_tbl */
    int8_t byte0 = (int8_t)in->width_tbl[width_cur];
    if (byte0 < 0 && (byte0 & 8))                          /* pre-scan clear of the road band */
        objd_fill_down(fb, OBJD_TOP_CLEAR, OBJD_TOP_ROWS, OBJD_TOP_LONGS, 0, 0);

    int scan_row = OBJD_SCAN_ROWS;                         /* find the first visible (negative) row */
    for (;;) {
        int32_t entry = (int32_t)be32(in->width_tbl + width_cur); width_cur += 4;
        if (entry < 0) break;
        if (scan_row-- == 0) return;                       /* none in 96 rows */
    }

    uint32_t obj_desc = be32(in->width_tbl + width_cur - 4);
    int scale2 = (obj_desc & OBJD_F_SCALE2) != 0;
    uint16_t i = (uint16_t)(OBJD_SCAN_ROWS - scan_row);    /* entry index */
    uint16_t base_off = (uint16_t)((uint16_t)(OBJD_BASE_ROW - (i >> 1)) * OBJD_WIDTH);

    /* Walk the object's consecutive visible rows tracking the screen edges. */
    int16_t max_left = -1000, min_right = 1000;
    int cur_row = scan_row, left_row = OBJD_SCAN_ROWS, right_row = OBJD_SCAN_ROWS, extra_x2 = 0;
    uint32_t right_entry = width_cur, left_entry = width_cur;
    if (obj_desc & OBJD_F_FAR) {
        for (;;) {
            int16_t row_w = (int16_t)be16(in->width_tbl + width_cur - 2);
            int16_t left_edge = (int16_t)(OBJD_LE_BIAS + row_w + 2 * cur_row);
            if ((int16_t)(max_left - left_edge) < 0) { max_left = left_edge; left_row = cur_row; left_entry = width_cur; }
            int16_t right_edge = (int16_t)(OBJD_RE_BIAS + row_w - 2 * cur_row);
            if ((int16_t)(right_edge - min_right) < 0) { min_right = right_edge; right_row = cur_row; right_entry = width_cur; }
            if (cur_row-- == 0) break;
            int32_t entry = (int32_t)be32(in->width_tbl + width_cur); width_cur += 4;
            if (entry >= 0) break;
            extra_x2 += 2;
        }
        max_left = (int16_t)(OBJD_LE_BIAS + left_row + (int16_t)be16(in->width_tbl + left_entry - 2));
        min_right = (int16_t)(OBJD_RE_BIAS - right_row + (int16_t)be16(in->width_tbl + right_entry - 2));
    } else {
        for (;;) {
            int16_t row_w = (int16_t)be16(in->width_tbl + width_cur - 2);
            int16_t left_edge = (int16_t)(OBJD_LE_BIAS + cur_row + row_w);
            if ((int16_t)(max_left - left_edge) < 0) { max_left = left_edge; left_row = cur_row; }
            int16_t right_edge = (int16_t)(OBJD_RE_BIAS - cur_row + row_w);
            if ((int16_t)(right_edge - min_right) < 0) { min_right = right_edge; right_row = cur_row; }
            if (cur_row-- == 0) break;
            int32_t entry = (int32_t)be32(in->width_tbl + width_cur); width_cur += 4;
            if (entry >= 0) break;
            extra_x2 += 2;
        }
    }

    uint16_t row_after = (uint16_t)(cur_row + 1);
    extra_x2 = (int)((uint16_t)(((uint16_t)extra_x2 & 0xfffc) - 1));   /* clear-width count-1 */
    int16_t center_rows;                                   /* centre-band rows-1 (-1 = none) */
    uint16_t clear_w;
    int32_t next_entry = (int32_t)be32(in->width_tbl + width_cur); width_cur += 4;
    if (next_entry < 0) {
        clear_w = (uint16_t)(extra_x2 + OBJD_CLEAR_TAIL);
        center_rows = -1;
    } else {
        clear_w = (uint16_t)extra_x2;
        int16_t span = (int16_t)((uint16_t)(OBJD_CENTER_SPAN - row_after) >> 1);
        int16_t overshoot = (int16_t)(OBJD_CENTER_BIAS - (int16_t)((uint16_t)row_after >> 1) + span);
        if (overshoot >= 0) span = (int16_t)(span - overshoot);
        center_rows = (int16_t)(span * 4 - 1);
    }

    /* Near-pass edges (used when a centre band exists); derived from the row past the object. */
    uint16_t c_lx = 0, c_rx = 0, c_off = 0, c_rows = 0;
    if (center_rows >= 0) {
        int16_t w_after = (int16_t)be16(in->width_tbl + width_cur - 6);   /* width of the first row past the object */
        c_lx   = (uint16_t)(OBJD_LE_BIAS + row_after + w_after);
        c_rx   = (uint16_t)(OBJD_RE_BIAS - row_after + w_after);
        c_off  = objd_row_off(row_after);
        c_rows = objd_vpos(row_after, scale2);
    }
    uint16_t lx = (uint16_t)max_left, l_off = objd_row_off((uint16_t)left_row), l_rows = objd_vpos((uint16_t)left_row, scale2);
    uint16_t rx = (uint16_t)min_right, r_off = objd_row_off((uint16_t)right_row), r_rows = objd_vpos((uint16_t)right_row, scale2);

    if (scale2) {                                          /* clear the road band + paint centre */
        Offset fill_cur = base_off;
        if ((int16_t)clear_w >= 0) fill_cur = objd_fill_down(fb, fill_cur, (int16_t)clear_w, OBJD_BAND_LONGS, 0, 0);
        if (center_rows >= 0) {
            Plane4 hi, lo;
            objd_shade_fill(in->shade, &hi, &lo);
            objd_fill_down(fb, fill_cur, center_rows, OBJD_BAND_LONGS, lo, hi);   /* d1(lo) first, then d0(hi) */
        }
    }

    /* --- first pass: left and/or right, near or far --- */
    Plane4 fill_lo = (obj_desc & OBJD_F_SCALE2) ? 0 : 0xffffffffu, fill_hi = 0;
    if (obj_desc & OBJD_F_LEFT) {
        if (!(obj_desc & OBJD_F_FAR)) {
            blit_obj_Ln(in, fb, OBJD_WIDTH, l_off, lx, fill_lo, fill_hi, l_rows);
            if (!(obj_desc & OBJD_F_SCALE2))
                road_walk(in, fb, OBJD_WIDTH, fill_lo, fill_hi, /*is_left=*/1, /*ramp_mul=*/1, /*ramp_add=*/0x41);
        } else {
            blit_obj_Lf(in, fb, OBJD_WIDTH, l_off, lx, fill_lo, fill_hi, l_rows);
            road_walk(in, fb, OBJD_WIDTH, fill_lo, fill_hi, /*is_left=*/1, /*ramp_mul=*/3, /*ramp_add=*/-0x7b);
        }
    }
    if (obj_desc & OBJD_F_RIGHT) {
        if (!(obj_desc & OBJD_F_FAR)) {
            blit_obj_Rn(in, fb, OBJD_WIDTH, r_off, rx, fill_lo, fill_hi, r_rows);
            if (!(obj_desc & OBJD_F_SCALE2))
                road_walk(in, fb, OBJD_WIDTH, fill_lo, fill_hi, /*is_left=*/0, /*ramp_mul=*/-1, /*ramp_add=*/0xfe);
        } else {
            blit_obj_Rf(in, fb, OBJD_WIDTH, r_off, rx, fill_lo, fill_hi, r_rows);
            road_walk(in, fb, OBJD_WIDTH, fill_lo, fill_hi, /*is_left=*/0, /*ramp_mul=*/-3, /*ramp_add=*/0x1ba);
        }
    }
    if (center_rows < 0) return;

    /* --- second (near-object) pass --- shared offset/rows, shade-selected fill. */
    Plane4 f2_lo, f2_hi;
    objd_shade_fill(in->shade, &f2_lo, &f2_hi);
    if (obj_desc & OBJD_F_LEFT) {
        if (!(obj_desc & OBJD_F_FAR)) blit_obj_Ln(in, fb, OBJD_WIDTH, c_off, c_lx, f2_lo, f2_hi, c_rows);
        else                          blit_obj_Lf(in, fb, OBJD_WIDTH, c_off, c_lx, f2_lo, f2_hi, c_rows);
    }
    if (obj_desc & OBJD_F_RIGHT) {
        if (!(obj_desc & OBJD_F_FAR)) blit_obj_Rn(in, fb, OBJD_WIDTH, c_off, c_rx, f2_lo, f2_hi, c_rows);
        else                          blit_obj_Rf(in, fb, OBJD_WIDTH, c_off, c_rx, f2_lo, f2_hi, c_rows);
    }
}
