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

#endif /* BB_DRAW_H */
