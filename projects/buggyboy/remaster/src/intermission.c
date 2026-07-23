/* intermission.c — the between-legs intermission screen (recreate's intermission.c cores).
 *
 * Three surfaces, all onto remaster's native models:
 *   rm_intermission_poll  a 9-entry table-driven block copy (a pre-rendered layout graphic in buf_c
 *                         is stamped into the draw buffer as nine rectangles)
 *   rm_draw_intermission  the scrolling screen: a hi-score table (section 1), the leg-time numbers
 *                         (section 2) and a credits block (section 3) scroll together on int_scroll,
 *                         each row top-clipped as it leaves the visible band
 *   rm_fade_step          one backdrop frame: fill + poll + copyright header + draw_intermission
 *
 * The scroll math mirrors the 68k word ops exactly (the equivalence harness diffs these bytes against
 * recreate). Text rows go through rm_glyph_run, the leg-time numbers through rm_num_run; fills through
 * the rm_fill_* family. See flow.h for the asset model (esp. the persistent `highscore` buffer).
 */
#include "fill.h"
#include "flow.h"
#include "st.h"
#include "text.h"

#define ROW_STRIDE SCREEN_ROW_BYTES

/* ---- intermission_poll ---- */
#define POLL_ENTRIES   9
#define POLL_DST_BASE  0x990       /* dst base = draw buffer + this */
#define POLL_UNIT      8           /* bytes per inner unit (two longword moves) */
#define POLL_ENTRY     6           /* {src_off:w, dst_off:w, dims:w} */

void rm_intermission_poll(Framebuffer *fb, const uint8_t *src, const uint8_t *blits) {
    uint8_t *px = fb->px;
    const uint8_t *tbl = blits;
    for (int e = 0; e < POLL_ENTRIES; e++, tbl += POLL_ENTRY) {
        uint32_t src_off = be16(tbl);                                  /* unsigned src offset */
        Offset dst = (Offset)((int32_t)POLL_DST_BASE + sx16(be16(tbl + 2)));  /* signed dst offset */
        uint16_t dims = be16(tbl + 4);
        uint32_t width = (uint32_t)((dims & 0xf) + 1) * POLL_UNIT;   /* a multiple of 8 (long-aligned) */
        int rows = (dims >> 8) + 1;
        for (int r = 0; r < rows; r++) {
            Offset drow = dst + (uint32_t)r * ROW_STRIDE;
            uint32_t srow = src_off + (uint32_t)r * ROW_STRIDE;
            for (uint32_t b = 0; b < width; b += 4)                   /* the 68k longword copy */
                wr32(px + drow + b, be32(src + srow + b));
        }
    }
}

/* ---- draw_intermission ---- */
#define INT_FILL_DST      0x1f40   /* fill_span clears the scroll band */
#define INT_FILL_COLOR    6
#define INT_FILL_CELLS_M1 0x397
#define INT_BASE_ADJ      0x318    /* each entry's base shifts up by this before scrolling */
#define INT_MAX_VIS       0x13     /* visible rows from the top of the band (positive-position clip) */
#define INT_TBL_ENTRY     10       /* 5 words per layout entry */
#define INT_SEC1_ENTRIES  15
#define INT_SEC1_ROWS     5        /* stacked hi-score rows per section-1 entry */
#define INT_SEC1_STR_STEP 0x80     /* string advance between those rows */
#define INT_SEC2_ROWS     5
#define INT_SEC2_STR_STEP 0xc
#define INT_SEC2_DST_BASE 0x2620   /* section-2 dst = y-position + this */
#define INT_SEC2_COLOR    0xd
#define INT_SEC2_MAX_ROWS 8        /* off-top row budget for the numbers */
#define INT_SEC2_BASE0    0x10     /* section-2 un-scrolled base (before INT_BASE_ADJ) */
#define INT_SEC3_ENTRIES  3

/* Clip a scrolling row: `base` is its un-scrolled position. Returns the visible cell count (negative
 * => fully off screen, skip), writes the screen y-position to *ypos, and advances *si past the rows
 * clipped off the top (by str_step_clip bytes each). off_top_budget is the count used when the row
 * has scrolled above the band top. */
static int clip_scroll_row(int16_t int_scroll, int16_t base, Offset *si, int str_step_clip,
                           int16_t off_top_budget, int16_t *ypos) {
    int16_t pos = (int16_t)(((int32_t)int_scroll << 3) + base);   /* truncate only after +base (68k) */
    if (pos < 0) {                                    /* scrolled above the band: clip the top rows */
        int16_t clip = (int16_t)(-pos) >> 3;
        *si += (uint32_t)str_step_clip * (uint16_t)clip;
        *ypos = 0;
        return off_top_budget - clip;
    }
    *ypos = pos;                                      /* within the band: clip against its bottom */
    return INT_MAX_VIS - (pos >> 3);
}

/* Draw-buffer offset for a y-position + a per-entry add (68k `adda.w D0`: word, sign-extended). */
static Offset row_dst(int16_t ypos, int16_t add) {
    return (Offset)sx16((uint16_t)(int16_t)(ypos + add));
}

/* Draw one layout entry's stacked scrolling glyph rows (shared by sections 1 and 3). Decode the
 * 5-word entry at `t`, tint by its colour, then draw `nrows` rows of `str`: each row starts
 * INT_SEC1_STR_STEP further into the string and one scanline lower, clipped against the scroll band
 * (str_step_clip = 2). Section 3 is the nrows == 1 case (a single credit line). */
static void draw_scroll_entry(Framebuffer *fb, const RmIntermissionAssets *a, int16_t int_scroll,
                              const uint8_t *t, const uint8_t *str, int nrows) {
    int16_t base = (int16_t)(be16(t) - INT_BASE_ADJ);
    int16_t dst_add = (int16_t)be16(t + 2);
    int16_t max_rows = (int16_t)be16(t + 4);
    int16_t colour = (int16_t)be16(t + 6);
    int16_t str_off = (int16_t)be16(t + 8);
    Plane4 fill_lo, fill_hi;
    rm_color_fill(a->color_pairs, (uint16_t)colour, COLOR_MASK_TEXT, &fill_lo, &fill_hi);
    int16_t row_str = 0;
    for (int i = 0; i < nrows; i++) {
        Offset si = (Offset)(sx16((uint16_t)str_off) + sx16((uint16_t)row_str));
        int16_t ypos;
        int16_t rows = (int16_t)clip_scroll_row(int_scroll, base, &si, 2, max_rows, &ypos);
        if (rows >= 0)
            rm_glyph_run(fb, row_dst(ypos, dst_add), fill_lo, fill_hi, a->font, str, si,
                         (uint16_t)rows, 0);
        base += ROW_STRIDE;
        row_str += INT_SEC1_STR_STEP;
    }
}

void rm_draw_intermission(Framebuffer *fb, const RmIntermissionAssets *a, int16_t int_scroll) {
    rm_fill_span(fb, a->color_pairs, INT_FILL_DST, INT_FILL_COLOR, INT_FILL_CELLS_M1);

    /* Section 1: 15 entries x 5 stacked high-score text rows. */
    const uint8_t *t1 = a->sec1_tbl;
    for (int e = 0; e < INT_SEC1_ENTRIES; e++, t1 += INT_TBL_ENTRY)
        draw_scroll_entry(fb, a, int_scroll, t1, a->highscore, INT_SEC1_ROWS);

    /* Section 2: 5 scrolling leg-time numbers from buf_a (leg_names already = buf_a + 0x884). */
    int16_t base = (int16_t)(INT_SEC2_BASE0 - INT_BASE_ADJ);
    int16_t num_str = 0;
    Plane4 n_lo, n_hi;
    rm_color_fill(a->color_pairs, INT_SEC2_COLOR, COLOR_MASK_NUM, &n_lo, &n_hi);
    for (int i = 0; i < INT_SEC2_ROWS; i++) {
        Offset si = (Offset)sx16((uint16_t)num_str);
        int16_t ypos;
        int16_t rows = (int16_t)clip_scroll_row(int_scroll, base, &si, 1, INT_SEC2_MAX_ROWS, &ypos);
        if (rows >= 0)
            rm_num_run(fb, row_dst(ypos, INT_SEC2_DST_BASE), n_lo, n_hi, a->num_sprites,
                       a->num_glyph_tbl, a->leg_names, si, (uint16_t)rows);
        base += ROW_STRIDE;
        num_str += INT_SEC2_STR_STEP;
    }

    /* Section 3: 3 scrolling credit lines (one row per entry). */
    const uint8_t *t3 = a->sec3_tbl;
    for (int e = 0; e < INT_SEC3_ENTRIES; e++, t3 += INT_TBL_ENTRY)
        draw_scroll_entry(fb, a, int_scroll, t3, a->credits, 1);
}

/* ---- fade_step ---- One between-legs backdrop frame: repaint the colour-6 backdrop, re-stamp the
 * static block layout (poll), draw the fixed copyright header, then draw the scrolling sections. */
#define FADE_FILL_COLOR   6
#define FADE_HEADER_DST   0x7448
#define FADE_HEADER_COLOR 0xf

void rm_fade_step(Framebuffer *fb, const RmIntermissionAssets *a, int16_t int_scroll) {
    rm_fill_screen(fb, a->color_pairs, FADE_FILL_COLOR);
    rm_intermission_poll(fb, a->poll_src, a->poll_blits);
    Plane4 fill_lo, fill_hi;
    rm_color_fill(a->color_pairs, FADE_HEADER_COLOR, COLOR_MASK_TEXT, &fill_lo, &fill_hi);
    rm_glyph_run(fb, (Offset)sx16(FADE_HEADER_DST), fill_lo, fill_hi, a->font,
                 a->header_str, 0, TEXT_MAX_CELLS_M1, 0);
    rm_draw_intermission(fb, a, int_scroll);
}
