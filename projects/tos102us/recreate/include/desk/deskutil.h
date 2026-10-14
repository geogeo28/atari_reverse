/* desk/deskutil.h — THE DESK'S UTILITIES, unit M (`src/desk/deskutil.c`): the range `$fed478..$fed887` — the cartridge
 * pair, the show / print engine. Band 5 owns the range's first two routines (cart_init `$fed478`, cart_find `$fed4be`:
 * `aes/cart.h`); band 6 wave 2 (group G2, ruling R-W2-1) takes the CARTRIDGE'S DIRECTORY SEARCH the directory read
 * pn_active `$fdfc3c` calls on drive 'c' — cart_sfirst `$fed522` and cart_snext `$fed534`, `aes/cart.h`'s own words
 * for them, each now read from its body. The rest of the unit is wave 4's.
 *
 * A SEARCH AS GEMDOS'S: the pair answers as dos_sfirst / dos_snext do — 1 an entry found (cart_find(1) has laid it into
 * the DTA cart_sfirst kept at AES_CART_DTA), 0 none, AES_DOS_AX then DOS_AX_NO_MORE_FILES. On the oracle's bus the
 * cartridge port reads 0 (`test/test_aes_cart.py`): cart_init always finds none there, so cart_sfirst's found arm
 * runs on no machine of ours.
 */
#ifndef TOS102US_DESK_DESKUTIL_H
#define TOS102US_DESK_DESKUTIL_H

/* ---- band 6 wave 2, group G2 (unit M) ---- */
#define CART_SNEXT_FILL       1          /* cart_find's `fill`: the entry laid into the DTA ($fed538 move.w #1,(sp)) */
#define CART_SNEXT_FOUND      1          /* ($fed542 moveq #1,d0)                                              */
#define CART_SNEXT_NONE       0          /* ($fed550 clr.w d0), AES_DOS_AX := DOS_AX_NO_MORE_FILES ($fed548)   */

#ifndef __ASSEMBLER__
#include <stdint.h>

int16_t aes_cart_sfirst(uint8_t *image, uint32_t dta, int16_t unread);                                /* $fed522 */
int16_t aes_cart_snext(uint8_t *image);                                                               /* $fed534 */
#endif
/* ---- end of group G2's wave-2 ---- */

#endif /* TOS102US_DESK_DESKUTIL_H */
