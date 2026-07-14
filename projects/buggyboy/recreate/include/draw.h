/* draw.h — the current draw buffer address, shared by every drawing primitive.
 *
 * The draw buffer is *(physbase_tbl + flip_idx) (adda.w sign-extends the word flip_idx); most
 * primitives then add a signed word D0 offset to it. Consolidated here so the screen-fill,
 * text/glyph, and results families share one definition instead of copies.
 */
#ifndef BB_DRAW_H
#define BB_DRAW_H

#include "machine.h"
#include "addrs.h"

/* Base of the current draw buffer: physbase_tbl indexed by the (word) flip_idx. */
static inline uint32_t draw_buffer(const uint8_t *image) {
    int16_t flip_idx = (int16_t)be16(image + A_flip_idx);      /* adda.w sign-extends */
    return be32(image + A_physbase_tbl + flip_idx);
}

/* Draw buffer plus a sign-extended word offset (the 68k `adda.w D0,A0` dst setup). */
static inline uint32_t draw_dst(const uint8_t *image, uint32_t off) {
    return draw_buffer(image) + sign_ext16(off);
}

/* Duplicate a 16-bit pattern into both halves of a longword (68k swap + move.w idiom). */
static inline uint32_t dup16(uint16_t word) { return ((uint32_t)word << 16) | word; }

/* One 8-byte (16-pixel, 4-plane) transparency-blit cell from four source words A,B,C,D at src:
 * mask = ~(A|B|C) & D shows the background through where the sprite is transparent; planes 0-2
 * take A/B/C, plane 3 takes D's leftover (non-A/B/C) bits. The shared masked-sprite primitive
 * (results row blitter, buggy/foreground sprites). */
static inline void blit_transp_cell(uint8_t *image, uint32_t dst, uint32_t src) {
    uint16_t a = be16(image + src);
    uint16_t b = be16(image + src + 2);
    uint16_t c = be16(image + src + 4);
    uint16_t d = be16(image + src + 6);
    uint16_t mask = (uint16_t)(~(a | b | c) & d);
    wr16(image + dst,     (uint16_t)((be16(image + dst)     & mask) | a));
    wr16(image + dst + 2, (uint16_t)((be16(image + dst + 2) & mask) | b));
    wr16(image + dst + 4, (uint16_t)((be16(image + dst + 4) & mask) | c));
    wr16(image + dst + 6, (uint16_t)((be16(image + dst + 6) & mask) | (uint16_t)(d & ~mask)));
}

#endif /* BB_DRAW_H */
