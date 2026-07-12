/* buggyboy.h — reconstruction cores + their image glue.
 *
 * Each function has two parts:
 *   - a *core* that works on idiomatic C types (the readable reconstruction);
 *   - a *glue* g_<name>(image, regs...) that unpacks the core's inputs from the flat
 *     image at their real addresses, calls the core, and lets it write back. The glue
 *     is the function's I/O contract; the differential harness diffs the whole image.
 */
#ifndef BB_BUGGYBOY_H
#define BB_BUGGYBOY_H

#include <stdint.h>

/* ---- score (add_score @ 0x1580a) ---- */
#define SCORE_DIGITS 6
void score_add(uint8_t *score, char *score_str, const uint8_t *delta, int game_over);
void g_add_score(uint8_t *image, uint32_t delta_ptr);            /* A1 -> 6-byte delta */

/* ---- screen fills (clear_screen @ 0x12e38, fill_span/fill_rect chain @ 0x12e56..) ---- */
#define SCREEN_BYTES   32000        /* 320x200x4bpp: 2000 * 16-byte writes */
#define FILL_CELL      8            /* one 16-pixel, 4-plane colour cell; also color_pairs stride */
#define SCREEN_CELLS   (SCREEN_BYTES / FILL_CELL)  /* 4000: whole draw buffer in fill cells */
#define ROW_STRIDE     160          /* bytes per scanline (0xa0) */
void screen_clear(uint8_t *buf);
void screen_fill_span(uint8_t *dst, const uint8_t *pattern, unsigned cells);
void screen_fill_rect(uint8_t *dst, const uint8_t *pattern, unsigned cells, unsigned rows);
void g_clear_screen(uint8_t *image);
void g_fill_screen(uint8_t *image, uint32_t color_index);       /* D1 colour */
void g_fill_words(uint8_t *image, uint32_t color_index, uint32_t cell_count_m1);   /* D1, D2 */
void g_fill_span(uint8_t *image, uint32_t dst_offset, uint32_t color_index, uint32_t cell_count_m1);
void g_fill_rect(uint8_t *image, uint32_t dst_offset, uint32_t color_index,
                 uint32_t cells_m1, uint32_t rows_m1);           /* D0, D1, D3, D4 */

/* ---- road perspective (build_road_geometry @ 0x11f4c) ---- */
void g_build_road_geometry(uint8_t *image);

/* ---- object sprite blitters (blit_obj_* @ 0x10bdc..) ---- */
#define OBJ_FULL_CELLS 10       /* full-width fill: 10 * 16-byte writes = one 160-byte scanline */
#define OBJ_ROW_UP     0xa0     /* 160 bytes: one scanline up (sprites drawn bottom to top) */
/* Glue register map: A6 buf_base, D2 width, D3 row_offset, D4 x, D5/D6 fill, D7 rows-1.
 * near: fixed x, column drawn up the screen.  far: x slants by one per row. */
uint32_t g_blit_obj_Ln(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t row_offset,
                       uint32_t x, uint32_t fill_lo, uint32_t fill_hi, uint32_t rows_minus1);
void     g_blit_obj_Rn(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t row_offset,
                       uint32_t x, uint32_t fill_lo, uint32_t fill_hi, uint32_t rows_minus1);
uint32_t g_blit_obj_Lf(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t row_offset,
                       uint32_t x, uint32_t fill_lo, uint32_t fill_hi, uint32_t rows_minus1);
void     g_blit_obj_Rf(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t row_offset,
                       uint32_t x, uint32_t fill_lo, uint32_t fill_hi, uint32_t rows_minus1);
/* road-walk variants: A6 buf_base, D2 width, D5/D6 fill; x per row from road_width_tbl + ramp */
#define OBJ_ROAD_START_OFF 0x3480   /* draw buffer offset where the road band begins */
#define OBJ_ROAD_ROWS      0x54     /* max scanline rows walked (84) */
void g_blit_obj_Ln2(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t fill_lo, uint32_t fill_hi);
void g_blit_obj_Rn2(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t fill_lo, uint32_t fill_hi);
void g_blit_obj_Lf2(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t fill_lo, uint32_t fill_hi);
void g_blit_obj_Rf2(uint8_t *image, uint32_t buf_base, uint32_t width, uint32_t fill_lo, uint32_t fill_hi);

/* ---- OS wrappers (GEMDOS/BIOS/XBIOS glue); see os.h for the shared trap model ---- */
void g_xbios_setscreen(uint8_t *image);
void g_xbios_setpalette(uint8_t *image, uint32_t palette_ptr);   /* A0 -> 16-word palette */

#endif /* BB_BUGGYBOY_H */