/* aes/oblib.h — the OBJECT-TREE walks (`src/aes/oblib.c`): an object's parent, and its screen position.
 *
 * Both are ALCYON C, entered by a Line-F call over the frame their caller pushed — the tree a LONGWORD, the object
 * a WORD (an Alcyon `int`) — and answer a word in D0, which is all their callers read (`tst.w d0`, `move.w d0,…`).
 * The layout they walk is `aes/objects.h`'s.
 */
#ifndef TOS102US_AES_OBLIB_H
#define TOS102US_AES_OBLIB_H

#include <stdint.h>

int16_t aes_get_par(uint8_t *image, uint32_t tree, int16_t object);                                   /* $fed382 */
int16_t aes_ob_offset(uint8_t *image, uint32_t tree, int16_t object, uint32_t x_out, uint32_t y_out); /* $fea584 */

#endif /* TOS102US_AES_OBLIB_H */
