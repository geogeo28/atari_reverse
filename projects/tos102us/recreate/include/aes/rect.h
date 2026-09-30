/* aes/rect.h — the AES's RECTANGLE layer (`src/aes/rect.c`), over `aes/objects.h`'s GRECT.
 *
 * Hand 68000 in the ROM ("optimize", `$fecb5a..$fed3bd`), called like Alcyon C — by a Line-F call over a frame
 * of two GRECT pointers — and answering a WORD in D0 (the shared tails `clr.w d0` / `move.w #1,d0`, which leave
 * the caller's high word: every caller reads D0.w alone, `tst.w d0`).
 */
#ifndef TOS102US_AES_RECT_H
#define TOS102US_AES_RECT_H

#include <stdint.h>

int16_t aes_rc_intersect(uint8_t *image, uint32_t clip, uint32_t rect);                                /* $fecd22 */

#endif /* TOS102US_AES_RECT_H */
