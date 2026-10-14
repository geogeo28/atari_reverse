/* deskutil.c — THE DESK'S UTILITIES (`desk/deskutil.h`), unit M: band 6 wave 2 lays it for group G2's two routines of
 * the cartridge's directory search (`$fed522`, `$fed534`). Alcyon C in the ROM, ported over its own order.
 */
#include "desk/deskutil.h"

/* ---- band 6 wave 2, group G2 (unit M) ---- */
#include <stdint.h>

#include "machine.h"
#include "aes/aes.h"
#include "aes/cart.h"
#include "aes/gemdosif.h"

/* $fed534 — cart_snext: the chain's next header laid into the kept DTA as a search's answer; at the chain's end,
 * AES_DOS_AX "no more files" — as dos_snext answers. */
int16_t aes_cart_snext(uint8_t *image)
{
    if (aes_cart_find(image, CART_SNEXT_FILL))
        return CART_SNEXT_FOUND;
    wr16(image + AES_DOS_AX, DOS_AX_NO_MORE_FILES);
    return CART_SNEXT_NONE;
}

/* $fed522 — cart_sfirst: the DTA kept for cart_find, the chain begun (cart_init), its first header searched for. The
 * attribute word its caller hands, as to dos_sfirst, is read by nothing. */
int16_t aes_cart_sfirst(uint8_t *image, uint32_t dta, int16_t unread)
{
    (void)unread;
    wr32(image + AES_CART_DTA, dta);
    (void)aes_cart_init(image);
    return aes_cart_snext(image);
}
/* ---- end of group G2's wave-2 ---- */
