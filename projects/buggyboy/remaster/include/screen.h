/* screen.h — the Atari ST low-res framebuffer, the one surface remaster shares with recreate.
 *
 * 320x200, 4 bitplanes interleaved word-by-word: each row is 20 groups of 4 words (planes 0..3),
 * MSB = leftmost pixel, plane 0 = LSB of the palette index. 160 bytes/row, 32000 bytes total.
 * This mirrors recreate/render/render_screen.py's decoder exactly, because the equivalence harness
 * diffs these bytes against recreate's output. See README.md "The contract".
 */
#ifndef RM_SCREEN_H
#define RM_SCREEN_H

/* The dimension #defines are shared with the hand-written m68k blit core (src/asm/objshift2.S), which
 * #includes this header after cpp expands it — so the C-only parts (stdint, the Framebuffer typedef)
 * are hidden from the assembler behind __ASSEMBLER__ (gcc defines it when assembling a .S). */
#ifndef __ASSEMBLER__
#include <stdint.h>
#endif

#define SCREEN_W        320
#define SCREEN_H        200
#define SCREEN_PLANES   4
#define SCREEN_ROW_BYTES 160                  /* (SCREEN_W / 8) * SCREEN_PLANES */
#define SCREEN_BYTES    (SCREEN_ROW_BYTES * SCREEN_H)   /* 32000 */

#ifndef __ASSEMBLER__
typedef struct {
    uint8_t px[SCREEN_BYTES];                 /* interleaved 4-plane framebuffer, ST byte order */
} Framebuffer;
#endif

#endif /* RM_SCREEN_H */
