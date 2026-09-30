/* gemdosif.c — the AES's GEMDOS glue (`aes/gemdosif.h`): hand 68000 in the ROM ($fe3bba, and $fe3c26 through `__DOS`
 * $fe3c28 / $fe39b6 / $fe3c3e), ported over its own order. The trap is `gemdos/gemdos.h`'s one shape, taken two ways by
 * the two builds.
 */
#include <stdint.h>

#include "machine.h"
#include "aes/aes.h"
#include "aes/gemdosif.h"
#include "gemdos/gemdos.h"

#define ODD_BIT               1u         /* `btst #0,d0; beq; addq.l #1,d0`: rounded up to even ($fe3bbe, $fe3bde) */
#define DOS_FAILED            1          /* AES_DOS_ERR := 1 on a Malloc of nothing   ($fe3bd4 move.w #1)          */

/* $fe3bba — dos_alloc: Malloc of `bytes` rounded up to even (a longword sum: $ffffffff asks for 0), its block rounded
 * up the same way; a 0 (no memory) sets AES_DOS_ERR and is answered as it is — and a success does NOT clear it. */
uint32_t aes_dos_alloc(uint8_t *image, uint32_t bytes)
{
    uint32_t block = gemdos_trap_word_long(image, GEMDOS_MALLOC_FN, bytes + (bytes & ODD_BIT));

    if (!block) {
        wr16(image + AES_DOS_ERR, DOS_FAILED);
        return block;
    }
    return block + (block & ODD_BIT);
}

/* $fe3c26 — dos_free, through the glue's `__DOS`: both return addresses parked (its caller's, and `__DOS`'s own
 * inside the glue — ROM code addresses, stored as the data they are here), the call made, and its answer's word in
 * AES_DOS_AX and its LONG's sign in AES_DOS_ERR. */
uint32_t aes_dos_free(uint8_t *image, uint32_t return_site, uint32_t block)
{
    uint32_t answer;

    wr32(image + AES_DOS_RETURN, return_site);
    wr32(image + AES_TRAP1_RETURN, AES_DOS_TRAP_RETURN);
    answer = gemdos_trap_word_long(image, GEMDOS_MFREE_FN, block);
    wr16(image + AES_DOS_AX, (uint16_t)answer);
    wr16(image + AES_DOS_ERR, (int32_t)answer < 0);
    return answer;
}
