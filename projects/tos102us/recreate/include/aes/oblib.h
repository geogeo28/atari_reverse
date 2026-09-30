/* aes/oblib.h — the OBJECT-TREE walks (`src/aes/oblib.c`): an object's parent, its screen position, its fields
 * read out for drawing (ob_sst), and the depth-first walk that calls a routine per object (everyobj).
 *
 * All ALCYON C, entered by a Line-F call over the frame their caller pushed — the tree a LONGWORD, the object
 * a WORD (an Alcyon `int`) — and those that answer, answer a word in D0, which is all their callers read (`tst.w
 * d0`, `move.w d0,…`); everyobj answers nothing.
 * The layout they walk is `aes/objects.h`'s.
 */
#ifndef TOS102US_AES_OBLIB_H
#define TOS102US_AES_OBLIB_H

#include <stdint.h>

int16_t aes_get_par(uint8_t *image, uint32_t tree, int16_t object);                                   /* $fed382 */
int16_t aes_ob_offset(uint8_t *image, uint32_t tree, int16_t object, uint32_t x_out, uint32_t y_out); /* $fea584 */
int16_t aes_ob_sst(uint8_t *image, uint32_t tree, int16_t object, uint32_t spec_out, uint32_t state_out,
                   uint32_t type_out, uint32_t flags_out, uint32_t rect_out, uint32_t thickness_out);  /* $fed19e */
void aes_everyobj(uint8_t *image, uint32_t tree, int16_t first, int16_t last, uint32_t routine, int16_t start_x,
                  int16_t start_y, int16_t max_depth);                                                  /* $fed27c */

#endif /* TOS102US_AES_OBLIB_H */
