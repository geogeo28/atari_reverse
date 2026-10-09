/* aes/cart.h — THE CARTRIDGE CHAIN (`src/aes/cart.c`): the application cartridge at $fa0000 as the AES walks it.
 *
 *   $fed478 cart_init()      the cartridge's first longword against the application magic: there, the chain's
 *                            cursor is the header behind it and D0 1; not there, the cursor is NULL and D0.w 0
 *   $fed4be cart_find(fill)  the header at the cursor — D0, a pointer; NULL at the chain's end — and the cursor
 *                            moved to the next; with `fill`, the header's directory entry first laid into the DTA
 *                            cart_sfirst was handed, as a search's answer
 *
 * A CARTRIDGE'S APPLICATION HEADER (TOS's CA_HEADER), as these two read it: the next header's address (0 ends the
 * chain), eight bytes these routines do not read (its init and run addresses), then the directory entry — time,
 * date, size and name — exactly as a DTA holds one from its time on.
 *
 * ALCYON C, each entered by a Line-F call over the frame its caller pushed.
 */
#ifndef TOS102US_AES_CART_H
#define TOS102US_AES_CART_H

#include <stdint.h>

/* ---- the cartridge port ------------------------------------------------------------------------------------------- */
#define CART_BASE             0xfa0000u  /* the cartridge's first longword      ($fed47c move.l #$fa0000,$9ab8) */
#define CART_APPLICATION_MAGIC 0xabcdef42u /* an application cartridge          ($fed48e cmp.l #$abcdef42,d0)  */
#define CART_FIRST_HEADER     0xfa0004u  /* the chain's head, behind the magic  ($fed496 move.l #$fa0004,$9ab8) */

/* ---- a header, as cart_find reads it ------------------------------------------------------------------------------- */
#define CA_NEXT               0          /* long: the next header, 0 the end    ($fed514 move.l (a0),$9ab8)    */
#define CA_ENTRY              12         /* its directory entry                 ($fed4f6 addi.l #12,(sp))      */
#define CA_ENTRY_BYTES        21         /* time, date, size, 13 of the name's 14 ($fed4ec move.w #21,(sp))    */

/* ---- the DTA cart_find fills, a search's answer -------------------------------------------------------------------- */
#define CART_DTA_CLEARED      42         /* ...of its 44 bytes                  ($fed4de move.w #42,-(sp))     */
#define CART_DTA_ATTRIBUTE    21         /* byte: read-only                     ($fed4e6 move.b #1,21(a5))     */
#define CART_DTA_ENTRY        22         /* where the entry lands               ($fed4fe addi.l #22,(sp))      */
#define CART_READ_ONLY        1

/* ---- the AES's two words of it ------------------------------------------------------------------------------------- */
#define AES_CART_CURSOR       0x9ab8     /* long: the header cart_find answers next ($fed4c6 tst.l $9ab8)      */
#define AES_CART_DTA          0x96fa     /* long: the DTA cart_sfirst was handed ($fed526 move.l 8(a6),$96fa)  */

/* What cart_init answers. */
#define CART_PRESENT          1          /* ($fed4a0 moveq #1,d0)                                              */
#define CART_ABSENT           0          /* ($fed4ac clr.w d0)                                                 */
#define CART_CHAIN_END        0          /* cart_find's                         ($fed51e clr.l d0)             */

#ifndef __ASSEMBLER__
int16_t aes_cart_init(uint8_t *image);                                                                /* $fed478 */
uint32_t aes_cart_find(uint8_t *image, int16_t fill);                                                 /* $fed4be */
#endif

#endif /* TOS102US_AES_CART_H */
