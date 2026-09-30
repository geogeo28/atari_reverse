/* aes/rlist.h — the AES's RECTANGLE LISTS (`src/aes/rlist.c`): the ORECT pool's free list, and the cut that breaks a
 * window's visible rectangles round another's.
 *
 * All ALCYON C, entered by a Line-F call over the frame their caller pushed (or, mkrect, by everyobj's `jsr (a0)`);
 * an ORECT is answered as a LONGWORD pointer in D0 — all 32 bits, which the callers store and follow. The layout is
 * `aes/objects.h`'s ORECT, the pool and its free head `aes/aes.h`'s.
 */
#ifndef TOS102US_AES_RLIST_H
#define TOS102US_AES_RLIST_H

#include <stdint.h>

/* The pieces mkpiece makes, by the side of the cut they lie on — brkrct makes them in this order ($fe5b8e's switch). */
#define ORECT_PIECE_ABOVE     0          /* the rows above the cut, the whole width                            */
#define ORECT_PIECE_LEFT      1          /* left of the cut, the rows the two share                            */
#define ORECT_PIECE_RIGHT     2          /* ...and right of it                                                 */
#define ORECT_PIECE_BELOW     3          /* the rows below the cut, the whole width                            */
#define ORECT_PIECE_SIDES     4          /* brkrct's loop ($fe5c7e cmp.w #4)                                   */

void aes_or_start(uint8_t *image);                                                              /* $fe5a62 */
uint32_t aes_get_orect(uint8_t *image);                                                         /* $fe5aac */
uint32_t aes_mkpiece(uint8_t *image, int16_t side, uint32_t cut, uint32_t rect);                /* $fe5acc */
uint32_t aes_brkrct(uint8_t *image, uint32_t cut, uint32_t rect, uint32_t prior);               /* $fe5ba8 */
void aes_mkrect(uint8_t *image, uint32_t tree, int16_t window);                                 /* $fe5c9a */

#endif /* TOS102US_AES_RLIST_H */
