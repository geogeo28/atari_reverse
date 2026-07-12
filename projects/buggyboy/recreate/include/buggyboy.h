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
void g_add_score(uint8_t *image, uint32_t a1);

/* ---- screen fills (clear_screen @ 0x12e38, fill_span/fill_rect chain @ 0x12e56..) ---- */
#define SCREEN_BYTES   32000        /* 320x200x4bpp: 2000 * 16-byte writes */
#define FILL_CELL      8            /* one 16-pixel, 4-plane colour cell; also color_pairs stride */
#define SCREEN_CELLS   (SCREEN_BYTES / FILL_CELL)  /* 4000: whole draw buffer in fill cells */
#define ROW_STRIDE     160          /* bytes per scanline (0xa0) */
void screen_clear(uint8_t *buf);
void screen_fill_span(uint8_t *dst, const uint8_t *pattern, unsigned cells);
void screen_fill_rect(uint8_t *dst, const uint8_t *pattern, unsigned cells, unsigned rows);
void g_clear_screen(uint8_t *image);
void g_fill_screen(uint8_t *image, uint32_t d1);
void g_fill_words(uint8_t *image, uint32_t d1, uint32_t d2);
void g_fill_span(uint8_t *image, uint32_t d0, uint32_t d1, uint32_t d2);
void g_fill_rect(uint8_t *image, uint32_t d0, uint32_t d1, uint32_t d3, uint32_t d4);

/* ---- road perspective (build_road_geometry @ 0x11f4c) ---- */
void g_build_road_geometry(uint8_t *image);

/* ---- object sprite blitters (blit_obj_* @ 0x10bdc..) ---- */
#define OBJ_FULL_CELLS 10       /* full-width fill: 10 * 16-byte writes = one 160-byte scanline */
#define OBJ_ROW_UP     0xa0     /* 160 bytes: one scanline up (sprites drawn bottom to top) */
/* near: fixed x, column drawn up the screen.  far: x slants by one per row. */
uint32_t g_blit_obj_Ln(uint8_t *image, uint32_t a6, uint32_t d2, uint32_t d3,
                       uint32_t d4, uint32_t d5, uint32_t d6, uint32_t d7);
void     g_blit_obj_Rn(uint8_t *image, uint32_t a6, uint32_t d2, uint32_t d3,
                       uint32_t d4, uint32_t d5, uint32_t d6, uint32_t d7);
uint32_t g_blit_obj_Lf(uint8_t *image, uint32_t a6, uint32_t d2, uint32_t d3,
                       uint32_t d4, uint32_t d5, uint32_t d6, uint32_t d7);
void     g_blit_obj_Rf(uint8_t *image, uint32_t a6, uint32_t d2, uint32_t d3,
                       uint32_t d4, uint32_t d5, uint32_t d6, uint32_t d7);

#endif /* BB_BUGGYBOY_H */