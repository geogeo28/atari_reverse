/* fs_copy.c — THE SHARED byte copies ($fc55fa, $fc5622, $fc564a) and byte swaps ($fc4f10, $fc4f22).
 *
 * One loop and three entry points, each with the ROM's own argument order (`include/gemdos/fs_copy.h`
 * says which caller reaches which). The ROM keeps the loop three times; here it is `copy_forward`.
 */
#include <stdint.h>

#include "gemdos/fs_copy.h"
#include "m68k_idioms.h"
#include "machine.h"

/* `ror.w #8`: a word's two bytes exchanged. */
#define BYTE_ROTATION 8

/* `move.w n,d0 / subq.w #1,n / tst.w d0 / bne` around `move.b (a1),(a0)`: `count` bytes, lowest
 * address first, one at a time — so an overlapping copy smears exactly as the ROM's does. The
 * count is an unsigned word; 0 copies nothing. */
static void copy_forward(uint8_t *image, uint16_t count, uint32_t source, uint32_t destination)
{
    while (count-- != 0)
        image[destination++] = image[source++];
}

/* $fc55fa — (n, src, dst): the transfer engine's READ copy, cached sector -> caller's buffer. */
void gemdos_copy_out(uint8_t *image, uint16_t count, uint32_t source, uint32_t destination)
{
    copy_forward(image, count, source, destination);
}

/* $fc5622 — (n, dst, src): the WRITE copy, handed the engine's same (n, cache, user) and copying the
 * other way, user -> cache. */
void gemdos_copy_in(uint8_t *image, uint16_t count, uint32_t destination, uint32_t source)
{
    copy_forward(image, count, source, destination);
}

/* $fc564a — (n, src, dst), byte-identical to $fc55fa: the copy the rest of GEMDOS calls by name. */
void gemdos_bcopy(uint8_t *image, uint16_t count, uint32_t source, uint32_t destination)
{
    copy_forward(image, count, source, destination);
}

/* $fc4f10 — the word at `at`, its two bytes exchanged: `ror.w #8`. */
void os_swap_word(uint8_t *image, uint32_t at)
{
    wr16(image + at, rotate_right16(be16(image + at), BYTE_ROTATION));
}

/* $fc4f22 — the long at `at`, all four bytes reversed, as the ROM does it: `ror.w #8` on the low
 * half, `swap` the halves, `ror.w #8` on the new low half. */
void os_swap_long(uint8_t *image, uint32_t at)
{
    uint32_t value = be32(image + at);
    uint16_t low = rotate_right16((uint16_t)value, BYTE_ROTATION);
    uint16_t high = rotate_right16((uint16_t)(value >> M68K_WORD_BITS), BYTE_ROTATION);

    wr32(image + at, ((uint32_t)low << M68K_WORD_BITS) | high);
}
