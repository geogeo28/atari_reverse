/* cart.c — THE CARTRIDGE CHAIN (`aes/cart.h`): cart_init and cart_find. Alcyon C in the ROM, ported over its own
 * order: the cursor is stored and read back through memory each time, as the ROM's absolute accesses do.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/cart.h"
#include "aes/strings.h"

_Static_assert(CART_FIRST_HEADER == CART_BASE + sizeof(uint32_t), "the first header lies behind the magic longword");

/* $fed478 — cart_init: the cursor set to the cartridge's base, the longword there read THROUGH it, and the cursor
 * left at the first header or NULL. */
int16_t aes_cart_init(uint8_t *image)
{
    wr32(image + AES_CART_CURSOR, CART_BASE);
    if (bus_long(image, be32(image + AES_CART_CURSOR)) != CART_APPLICATION_MAGIC) {
        wr32(image + AES_CART_CURSOR, 0);
        return CART_ABSENT;
    }
    wr32(image + AES_CART_CURSOR, CART_FIRST_HEADER);
    return CART_PRESENT;
}

/* The header's directory entry laid into the DTA as a search's answer: the DTA cleared, read-only, then the entry. */
static inline void fill_the_dta(uint8_t *image)
{
    uint32_t dta = be32(image + AES_CART_DTA);

    aes_bfill(image, CART_DTA_CLEARED, 0, dta);
    set_bus_byte(image, dta + CART_DTA_ATTRIBUTE, CART_READ_ONLY);
    aes_lbcopy(image, dta + CART_DTA_ENTRY, be32(image + AES_CART_CURSOR) + CA_ENTRY, CA_ENTRY_BYTES);
}

/* $fed4be — cart_find: the header at the cursor, the cursor moved on to the one it names; NULL once the cursor is. */
uint32_t aes_cart_find(uint8_t *image, int16_t fill)
{
    uint32_t header;

    if (!be32(image + AES_CART_CURSOR))
        return CART_CHAIN_END;
    if (fill)
        fill_the_dta(image);
    header = be32(image + AES_CART_CURSOR);
    wr32(image + AES_CART_CURSOR, bus_long(image, be32(image + AES_CART_CURSOR) + CA_NEXT));
    return header;
}
