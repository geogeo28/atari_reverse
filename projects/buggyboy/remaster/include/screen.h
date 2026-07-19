/* screen.h — the Atari ST low-res framebuffer, the one surface remaster shares with recreate.
 *
 * 320x200, 4 bitplanes interleaved word-by-word: each row is 20 groups of 4 words (planes 0..3),
 * MSB = leftmost pixel, plane 0 = LSB of the palette index. 160 bytes/row, 32000 bytes total.
 * This mirrors recreate/render/render_screen.py's decoder exactly, because the equivalence harness
 * diffs these bytes against recreate's output. See README.md "The contract".
 */
#ifndef RM_SCREEN_H
#define RM_SCREEN_H

#include <stdint.h>

#define SCREEN_W        320
#define SCREEN_H        200
#define SCREEN_PLANES   4
#define SCREEN_ROW_BYTES 160                  /* (SCREEN_W / 8) * SCREEN_PLANES */
#define SCREEN_BYTES    (SCREEN_ROW_BYTES * SCREEN_H)   /* 32000 */

typedef struct {
    uint8_t px[SCREEN_BYTES];                 /* interleaved 4-plane framebuffer, ST byte order */
} Framebuffer;

#endif /* RM_SCREEN_H */
