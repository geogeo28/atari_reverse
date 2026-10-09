/* deskmem.c — THE DESK'S MEMORY (`aes/deskmem.h`): size_theglo, desk_alloc and desk_free. Alcyon C in the ROM, ported
 * over its own order: every pointer is stored and read back through memory, as the ROM's absolute accesses do.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "recreate.h"
#include "aes/aes.h"
#include "aes/deskleaf.h"
#include "aes/deskmem.h"
#include "aes/gemdosif.h"
#include "aes/strings.h"

_Static_assert(DESK_GLOBALS_BYTES <= INT16_MAX, "the globals' clear hands bfill its count as a WORD ($fee824 move.w #19094)");

/* $fee800 — size_theglo: the count gem_entry's clear of THEGLO takes — its words less the one `dbmi` adds. */
uint16_t aes_size_theglo(void)
{
    return AES_THEGLO_WORDS - 1;
}

/* $fee80a — desk_alloc: no answer of dos_alloc is checked — a block Malloc refused is stored as the 0 it is.
 *
 * A REFUSED FIRST BLOCK IS NOT RECONSTRUCTED OFF TARGET, and halts by name: the ROM then clears 19,094 bytes from
 * address 0 — the exception vectors, `trap #1`'s with them — and its next Malloc traps through a vector of 0: its run
 * never returns (`test_aes_deskmem.py` pins that). The host's `image` has no vector that is taken, so the same C
 * would return with the page zeroed: an outcome the machine does not have. The target is the ROM's order as it is. */
void aes_desk_alloc(uint8_t *image)
{
    wr32(image + AES_DESK_GLOBALS, aes_dos_alloc(image, DESK_GLOBALS_BYTES));
#ifdef RECREATE_HOST_DIFFERENTIAL
    if (!be32(image + AES_DESK_GLOBALS))
        recreate_not_reconstructed("desk_alloc: Malloc refused the desk's globals — the ROM clears the vector page "
                                   "and never returns from its next trap");
#endif
    aes_bfill(image, DESK_GLOBALS_BYTES, 0, be32(image + AES_DESK_GLOBALS));
    wr32(image + AES_DESK_BLOCK_512, aes_dos_alloc(image, DESK_BLOCK_512_BYTES));
    wr32(image + AES_DESK_BLOCK_920, aes_dos_alloc(image, DESK_BLOCK_920_BYTES));
    wr32(image + AES_DESK_BLOCK_16000, aes_dos_alloc(image, DESK_BLOCK_16000_BYTES));
    wr32(image + AES_USERDEF_STACK, aes_dos_alloc(image, USERDEF_STACK_BYTES));
    wr32(image + AES_USERDEF_STACK, be32(image + AES_USERDEF_STACK) + USERDEF_STACK_BYTES);
}

/* $fee870 — desk_free: the desk's own two blocks (its globals read again for the second), its resource, the
 * userdef stack — its top taken back to the block's start, in memory — and the other four, the globals third. */
void aes_desk_free(uint8_t *image)
{
    (void)aes_dos_free(image, AES_DESK_FREE_FIRST_RETURN, bus_long(image, be32(image + AES_DESK_GLOBALS) + DESK_G_FIRST_FREED));
    (void)aes_dos_free(image, AES_DESK_FREE_SECOND_RETURN, bus_long(image, be32(image + AES_DESK_GLOBALS) + DESK_G_SECOND_FREED));
    (void)aes_desk_rsrc_free(image);
    wr32(image + AES_USERDEF_STACK, be32(image + AES_USERDEF_STACK) - USERDEF_STACK_BYTES);
    (void)aes_dos_free(image, AES_DESK_FREE_STACK_RETURN, be32(image + AES_USERDEF_STACK));
    (void)aes_dos_free(image, AES_DESK_FREE_C82E_RETURN, be32(image + AES_DESK_BLOCK_512));
    (void)aes_dos_free(image, AES_DESK_FREE_GLOBALS_RETURN, be32(image + AES_DESK_GLOBALS));
    (void)aes_dos_free(image, AES_DESK_FREE_C85E_RETURN, be32(image + AES_DESK_BLOCK_920));
    (void)aes_dos_free(image, AES_DESK_FREE_C67A_RETURN, be32(image + AES_DESK_BLOCK_16000));
}
