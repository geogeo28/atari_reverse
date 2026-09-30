/* aes/objops.h — the OBJECT-TREE operations (`src/aes/objects.c`): finding the object under a point, linking one in,
 * unlinking it, moving it among its siblings, centring a tree, and the object library's small helpers they share.
 *
 * All ALCYON C, entered by a Line-F call over the frame their caller pushed — a tree a LONGWORD, an object a WORD (an
 * Alcyon `int`), a GRECT or word pointer a LONGWORD — over `aes/objects.h`'s layout. Those that answer, answer a WORD
 * in D0; ob_add, ob_delete, ob_order and ob_center answer nothing their callers read (the dispatcher's arms return
 * their own 1), nor do the three GRECT helpers.
 */
#ifndef TOS102US_AES_OBJOPS_H
#define TOS102US_AES_OBJOPS_H

#include <stdint.h>

int16_t aes_ob_find(uint8_t *image, uint32_t tree, int16_t object, int16_t depth, int16_t x, int16_t y);  /* $fea0a8 */
void aes_ob_add(uint8_t *image, uint32_t tree, int16_t parent, int16_t child);                              /* $fea1ba */
void aes_ob_delete(uint8_t *image, uint32_t tree, int16_t object);                                          /* $fea21e */
void aes_ob_order(uint8_t *image, uint32_t tree, int16_t object, int16_t position);                         /* $fea2be */
int16_t aes_ob_fs(uint8_t *image, uint32_t tree, int16_t object, uint32_t flags_out);                        /* $fea4b6 */
void aes_ob_actxywh(uint8_t *image, uint32_t tree, int16_t object, uint32_t rect);                          /* $fea4e8 */
void aes_ob_relxywh(uint8_t *image, uint32_t tree, int16_t object, uint32_t rect);                          /* $fea538 */
void aes_ob_setxywh(uint8_t *image, uint32_t tree, int16_t object, uint32_t rect);                          /* $fea55e */
int16_t aes_get_prev(uint8_t *image, uint32_t tree, int16_t parent, int16_t object);                        /* $fea5dc */
void aes_ob_center(uint8_t *image, uint32_t tree, uint32_t rect);                                           /* $fe92ae */

#endif /* TOS102US_AES_OBJOPS_H */
