/* screen.c — solid-colour screen fills into the current draw buffer.
 *
 * Reconstruction of the fall-through fill family:
 *   clear_screen @ 0x12e38   zero the whole draw buffer
 *   fill_screen  @ 0x12e56 ->  fill_words (D0=0) -> fill_span, whole screen in one colour
 *   fill_words   @ 0x12e5a ->  fill_span (D0=0)
 *   fill_span    @ 0x12e5c   fill a run of 8-byte colour cells
 *   fill_rect    @ 0x12e80   fill a rectangle of cells with a 160-byte scanline stride
 *
 * The draw buffer is *(physbase_tbl + flip_idx); a colour index selects an 8-byte,
 * 4-plane fill pattern from color_pairs. Writes are byte-identical to the 68k long
 * moves, so filling reduces to copying the pattern cell repeatedly.
 */
#include <string.h>
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"
#include "draw.h"

/* 8-byte fill pattern for a colour index (color_pairs entry = FILL_CELL bytes, word offset). */
static const uint8_t *color_pattern(const uint8_t *image, uint32_t color_index) {
    int16_t off = (int16_t)(uint16_t)((uint16_t)color_index * FILL_CELL);
    return image + A_color_pairs + off;
}

void screen_clear(uint8_t *buf) {
    memset(buf, 0, SCREEN_BYTES);
}

void screen_fill_span(uint8_t *dst, const uint8_t *pattern, unsigned cells) {
    for (unsigned i = 0; i < cells; i++) memcpy(dst + i * FILL_CELL, pattern, FILL_CELL);
}

void screen_fill_rect(uint8_t *dst, const uint8_t *pattern, unsigned cells, unsigned rows) {
    for (unsigned r = 0; r < rows; r++, dst += ROW_STRIDE)
        for (unsigned i = 0; i < cells; i++) memcpy(dst + i * FILL_CELL, pattern, FILL_CELL);
}

/* dbf loops (count_word + 1) times. */
static unsigned dbf_count(uint32_t reg) { return (reg & 0xFFFF) + 1; }

void g_clear_screen(uint8_t *image) {
    screen_clear(image + draw_buffer(image));
}

/* D0 dst_offset, D1 color_index, D2 cell_count-1. */
void g_fill_span(uint8_t *image, uint32_t dst_offset, uint32_t color_index, uint32_t cell_count_m1) {
    screen_fill_span(image + draw_dst(image, dst_offset), color_pattern(image, color_index),
                     dbf_count(cell_count_m1));
}

/* fill_words enters with D0 forced to 0. */
void g_fill_words(uint8_t *image, uint32_t color_index, uint32_t cell_count_m1) {
    g_fill_span(image, 0, color_index, cell_count_m1);
}

/* fill_screen enters with D0=0 and D2 = whole screen minus one cell (the dbf count). */
void g_fill_screen(uint8_t *image, uint32_t color_index) {
    g_fill_words(image, color_index, SCREEN_CELLS - 1);
}

/* D0 dst_offset, D1 color_index, D3 cells_per_row-1, D4 rows-1. */
void g_fill_rect(uint8_t *image, uint32_t dst_offset, uint32_t color_index,
                 uint32_t cells_m1, uint32_t rows_m1) {
    screen_fill_rect(image + draw_dst(image, dst_offset), color_pattern(image, color_index),
                     dbf_count(cells_m1), dbf_count(rows_m1));
}
/* flip_screen @ 0x121f8 — page-flip the double buffer. Point the ST video-base registers
 * ($ffff8200, interrupts masked around the write) at the current physbase_tbl[flip_idx], toggle
 * flip_idx between 0 and 4, and Vsync (XBIOS 0x25). The video-base write and Vsync are hardware
 * only; the sole observable image effect is the flip_idx toggle. */
BB_WEAK void g_flip_screen(uint8_t *image) {
    uint16_t flip_idx = be16(image + A_flip_idx);
    wr16(image + A_flip_idx, (uint16_t)((flip_idx + 4) & 4));
}
