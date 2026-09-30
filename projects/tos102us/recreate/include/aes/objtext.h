/* aes/objtext.h — the object library's TEXT and STATE helpers (`src/aes/objtext.c`): an editable object's text in
 * and out of its TEDINFO, a state word set from a flag, and the first SELECTED object of a run — the file selector's
 * and the desk dialogs' plumbing.
 *
 * In the ROM's "optimize" layer, spelt in hand 68000 but called like Alcyon C — a Line-F call over a frame of the
 * tree (a LONGWORD), the object and the other values (WORDS), string and answer pointers (LONGWORDS) — and all
 * but inf_sset returning by `rts`. Each reaches its object's field through OB_ADDR ($fed18e), which is
 * `aes/objects.h`'s `object_address`. inf_gindex and inf_what answer a WORD in D0; the rest answer nothing a caller
 * reads.
 */
#ifndef TOS102US_AES_OBJTEXT_H
#define TOS102US_AES_OBJTEXT_H

#include <stdint.h>

/* inf_what's pair: the OK button and the one after it. */
#define INF_WHAT_BUTTONS      2          /* ($fed03a move.w #2,-(sp))                                          */

void aes_fs_sset(uint8_t *image, uint32_t tree, int16_t object, uint32_t text, uint32_t text_out,
                 uint32_t length_out);                                                                  /* $fecf84 */
void aes_inf_sset(uint8_t *image, uint32_t tree, int16_t object, uint32_t text);                        /* $fecfb2 */
void aes_fs_sget(uint8_t *image, uint32_t tree, int16_t object, uint32_t text);                         /* $fecfd6 */
void aes_inf_fldset(uint8_t *image, uint32_t tree, int16_t object, int16_t field, int16_t bits, int16_t when_set,
                    int16_t when_clear);                                                                 /* $fecfee */
int16_t aes_inf_gindex(uint8_t *image, uint32_t tree, int16_t first, int16_t count);                   /* $fed010 */
int16_t aes_inf_what(uint8_t *image, uint32_t tree, int16_t ok, int16_t cancel);                       /* $fed03a */

#endif /* TOS102US_AES_OBJTEXT_H */
