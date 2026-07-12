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

/* Current draw buffer pointer: physbase_tbl indexed by the (word) flip_idx. */
static uint32_t cur_buf(const uint8_t *image) {
    int16_t fidx = (int16_t)be16(image + A_flip_idx);          /* adda.w sign-extends */
    return be32(image + A_physbase_tbl + fidx);
}

/* 8-byte fill pattern for a colour index (color_pairs entry = FILL_CELL bytes, word offset). */
static const uint8_t *color_pattern(const uint8_t *image, uint32_t d1) {
    int16_t off = (int16_t)(uint16_t)((uint16_t)d1 * FILL_CELL);
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
static unsigned dbf_count(uint32_t d) { return (d & 0xFFFF) + 1; }

/* Byte offset into the draw buffer from the D0 register (adda.w -> sign-extended word). */
static uint8_t *span_dst(uint8_t *image, uint32_t d0) {
    return image + cur_buf(image) + (int16_t)(uint16_t)d0;
}

void g_clear_screen(uint8_t *image) {
    screen_clear(image + cur_buf(image));
}

void g_fill_span(uint8_t *image, uint32_t d0, uint32_t d1, uint32_t d2) {
    screen_fill_span(span_dst(image, d0), color_pattern(image, d1), dbf_count(d2));
}

/* fill_words enters with D0 forced to 0. */
void g_fill_words(uint8_t *image, uint32_t d1, uint32_t d2) {
    g_fill_span(image, 0, d1, d2);
}

/* fill_screen enters with D0=0 and D2 = whole screen minus one cell (the dbf count). */
void g_fill_screen(uint8_t *image, uint32_t d1) {
    g_fill_words(image, d1, SCREEN_CELLS - 1);
}

void g_fill_rect(uint8_t *image, uint32_t d0, uint32_t d1, uint32_t d3, uint32_t d4) {
    screen_fill_rect(span_dst(image, d0), color_pattern(image, d1),
                     dbf_count(d3), dbf_count(d4));
}