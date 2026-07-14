/* intermission.c — intermission-screen block blitter (intermission_poll @ 0x12914).
 *
 * Despite the "poll" name (inferred from call context, unconfirmed), this reads no input: it is a
 * table-driven plain block copy. A 9-entry control table (INTERMISSION_BLITS, inline right after
 * the function body) drives nine rectangular copies from a pre-rendered screen-layout graphic in
 * buf_c into the draw buffer (physbase_tbl[flip_idx] + 0x990). Each entry is three words:
 *   src_off (u16, unsigned)   dst_off (i16, signed)   dims (u16)
 * dims packs the row count-1 in the high byte and the inner 8-byte-unit count-1 in the low nibble,
 * so a row copies ((dims & 0xf) + 1) * 8 contiguous bytes and there are ((dims >> 8) + 1) rows.
 * Source and destination both step one scanline (ROW_STRIDE) per row — the source is stored at
 * screen pitch. No mask/transparency; src and dst bases are both recomputed fresh each entry.
 */
#include <string.h>
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

#define INTERMISSION_BLITS   0x1296a   /* inline control table: 9 x {src_off, dst_off, dims} words */
#define INTERMISSION_ENTRIES 9
#define INTERMISSION_SRC_OFF 0x32c80   /* source base = buf_c + this */
#define INTERMISSION_DST_OFF 0x990     /* dest base = physbase_tbl[flip_idx] + this */
#define BLIT_UNIT            8          /* bytes per inner unit (two longword moves) */

void g_intermission_poll(uint8_t *image) {
    int16_t flip_idx = (int16_t)be16(image + A_flip_idx);
    uint32_t dst_base = be32(image + A_physbase_tbl + flip_idx) + INTERMISSION_DST_OFF;
    uint32_t src_base = be32(image + A_buf_c) + INTERMISSION_SRC_OFF;

    uint32_t tbl = INTERMISSION_BLITS;
    for (int e = 0; e < INTERMISSION_ENTRIES; e++, tbl += 6) {
        uint32_t src = src_base + be16(image + tbl);                   /* unsigned src offset */
        uint32_t dst = dst_base + sign_ext16(be16(image + tbl + 2));   /* signed dst offset */
        uint16_t dims = be16(image + tbl + 4);
        uint32_t width = (uint32_t)((dims & 0xf) + 1) * BLIT_UNIT;
        int rows = (dims >> 8) + 1;
        for (int r = 0; r < rows; r++)
            memcpy(image + dst + r * ROW_STRIDE, image + src + r * ROW_STRIDE, width);
    }
}

/* --- draw_intermission @ 0x129ba --- The scrolling between-legs screen: a high-score table
 * (section 1), the leg-time numbers (section 2) and a two-line credit (section 3) all scroll
 * vertically together, driven by the signed scroll offset at INT_SCROLL. Each row's screen
 * y-position is (scroll << 3) + a per-row base; a positive position clips against the top of the
 * visible band (INT_MAX_VIS rows) and a negative one scrolls the row up off screen, advancing the
 * source string past the clipped rows. Rows entirely off screen (negative remaining count) are
 * skipped. Sections 1 and 3 draw text rows (draw_text_row); section 2 draws digit sprites
 * (draw_num). All three share the clip-and-draw logic below.
 *
 * Layout tables (const, inline in the program): section 1 = 15 entries, section 3 = 3 entries,
 * each 5 words {base, dst_add, max_rows, colour, str_off}. Section 1 draws 5 stacked rows per
 * entry (str = highscore_table + str_off + row*SEC1_STR_STEP). */
#define INT_SCROLL        0x18ca8   /* signed vertical scroll offset (animated by `intermission`) */
#define INT_TBL1          0x1858c   /* section 1 layout: 15 x 5 words */
#define INT_TBL3          0x18622   /* section 3 layout: 3 x 5 words */
#define INT_CREDITS_STR   0x180f4   /* section 3 string base (+ entry str_off) */
#define INT_TBL_ENTRY     10        /* 5 words per layout entry */
#define INT_FILL_DST      0x1f40    /* fill_span clears the scroll band: buffer + this */
#define INT_FILL_COLOR    6
#define INT_FILL_CELLS_M1 0x397
#define INT_BASE_ADJ      0x318     /* each entry's base is shifted up by this before scrolling */
#define INT_MAX_VIS       0x13      /* visible rows from the top of the band (positive-position clip) */
#define INT_SEC1_ROWS     5         /* stacked rows per section-1 entry */
#define INT_SEC1_STR_STEP 0x80      /* string advance between those rows */
#define INT_SEC2_ROWS     5
#define INT_SEC2_STR_OFF  0x884     /* section 2 numbers: buf_a + this + row*SEC2_STR_STEP */
#define INT_SEC2_STR_STEP 0xc
#define INT_SEC2_DST_BASE 0x2620    /* section 2 dst = y-position + this */
#define INT_SEC2_COLOR    0xd
#define INT_SEC2_MAX_ROWS 8         /* off-top row budget for the numbers (vs INT_MAX_VIS on-screen) */

/* Clip a scrolling row: base is the row's un-scrolled position. Returns the visible row count
 * (negative => fully off screen, skip) and writes the screen y-position to *ypos and advances
 * *str past clipped-off leading rows (by `str_step_clip` bytes each). off_top_budget is the row
 * count used when the row has scrolled above the band top. */
static int clip_scroll_row(uint8_t *image, int16_t base, uint32_t *str, int str_step_clip,
                           int16_t off_top_budget, int16_t *ypos) {
    int16_t pos = (int16_t)(((int16_t)be16(image + INT_SCROLL) << 3) + base);
    if (pos < 0) {                                    /* scrolled above the band: clip the top rows */
        int16_t clip = (int16_t)(-pos) >> 3;
        *str += (uint32_t)str_step_clip * (uint16_t)clip;
        *ypos = 0;
        return off_top_budget - clip;
    }
    *ypos = pos;                                      /* within the band: clip against its bottom */
    return INT_MAX_VIS - (pos >> 3);
}

void g_draw_intermission(uint8_t *image) {
    g_fill_span(image, INT_FILL_DST, INT_FILL_COLOR, INT_FILL_CELLS_M1);

    /* Section 1: 15 entries x 5 stacked high-score text rows. */
    uint32_t t1 = INT_TBL1;
    for (int e = 0; e < 15; e++, t1 += INT_TBL_ENTRY) {
        int16_t base = (int16_t)(be16(image + t1) - INT_BASE_ADJ);
        int16_t dst_add = (int16_t)be16(image + t1 + 2);
        int16_t max_rows = (int16_t)be16(image + t1 + 4);
        int16_t colour = (int16_t)be16(image + t1 + 6);
        int16_t str_off = (int16_t)be16(image + t1 + 8);
        int16_t row_str = 0;
        for (int i = 0; i < INT_SEC1_ROWS; i++) {
            uint32_t str = A_highscore_table + sign_ext16((uint16_t)str_off) + sign_ext16((uint16_t)row_str);
            int16_t ypos;
            int16_t rows = (int16_t)clip_scroll_row(image, base, &str, 2, max_rows, &ypos);
            if (rows >= 0)
                g_draw_text_row(image, (uint16_t)(int16_t)(ypos + dst_add), (uint16_t)colour,
                                (uint16_t)rows, str);
            base += ROW_STRIDE;
            row_str += INT_SEC1_STR_STEP;
        }
    }

    /* Section 2: 5 scrolling leg-time numbers from buf_a. */
    int16_t base = (int16_t)(0x10 - INT_BASE_ADJ);
    int16_t num_str = 0;
    for (int i = 0; i < INT_SEC2_ROWS; i++) {
        uint32_t str = be32(image + A_buf_a) + INT_SEC2_STR_OFF + sign_ext16((uint16_t)num_str);
        int16_t ypos;
        int16_t rows = (int16_t)clip_scroll_row(image, base, &str, 1, INT_SEC2_MAX_ROWS, &ypos);
        if (rows >= 0)
            g_draw_num(image, (uint16_t)(int16_t)(ypos + INT_SEC2_DST_BASE), INT_SEC2_COLOR,
                       (uint16_t)rows, str);
        base += ROW_STRIDE;
        num_str += INT_SEC2_STR_STEP;
    }

    /* Section 3: 3 scrolling credit lines. */
    uint32_t t3 = INT_TBL3;
    for (int e = 0; e < 3; e++, t3 += INT_TBL_ENTRY) {
        int16_t b3 = (int16_t)(be16(image + t3) - INT_BASE_ADJ);
        int16_t dst_add = (int16_t)be16(image + t3 + 2);
        int16_t max_rows = (int16_t)be16(image + t3 + 4);
        int16_t colour = (int16_t)be16(image + t3 + 6);
        int16_t str_off = (int16_t)be16(image + t3 + 8);
        uint32_t str = INT_CREDITS_STR + sign_ext16((uint16_t)str_off);
        int16_t ypos;
        int16_t rows = (int16_t)clip_scroll_row(image, b3, &str, 2, max_rows, &ypos);
        if (rows >= 0)
            g_draw_text_row(image, (uint16_t)(int16_t)(ypos + dst_add), (uint16_t)colour,
                            (uint16_t)rows, str);
    }
}

