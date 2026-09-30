/* aes/rect.h — the AES's RECTANGLE layer (`src/aes/rect.c`), over `aes/objects.h`'s GRECT.
 *
 * Hand 68000 in the ROM ("optimize", `$fecb5a..$fed3bd`), called like Alcyon C — by a Line-F call over a frame of
 * GRECT pointers (r_get's beside four answer pointers, r_set's beside four words, inside's after two) — and every
 * one returns by `rts`. The three that ANSWER (inside, rc_equal, rc_intersect) answer a WORD in D0 through the
 * shared tails `clr.w d0` / `move.w #1,d0`, which leave the caller's high word: every caller reads D0.w alone,
 * `tst.w d0`. The rest leave in D0 whatever their last `move` put there, which no caller reads.
 */
#ifndef TOS102US_AES_RECT_H
#define TOS102US_AES_RECT_H

#include <stdint.h>

void aes_r_get(uint8_t *image, uint32_t rect, uint32_t x_out, uint32_t y_out, uint32_t w_out,
               uint32_t h_out);                                                                        /* $fecca6 */
void aes_r_set(uint8_t *image, uint32_t rect, int16_t x, int16_t y, int16_t w, int16_t h);            /* $feccbe */
void aes_rc_copy(uint8_t *image, uint32_t from, uint32_t to);                                           /* $feccca */
int16_t aes_inside(uint8_t *image, int16_t x, int16_t y, uint32_t rect);                               /* $feccd6 */
int16_t aes_rc_equal(uint8_t *image, uint32_t first, uint32_t second);                                 /* $fecd0c */
int16_t aes_rc_intersect(uint8_t *image, uint32_t clip, uint32_t rect);                                /* $fecd22 */
void aes_rc_union(uint8_t *image, uint32_t from, uint32_t into);                                        /* $fecd8c */
void aes_rc_constrain(uint8_t *image, uint32_t container, uint32_t rect);                               /* $fecde4 */

#endif /* TOS102US_AES_RECT_H */
