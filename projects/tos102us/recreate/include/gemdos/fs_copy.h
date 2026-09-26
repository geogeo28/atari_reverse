/* gemdos/fs_copy.h — THE SHARED byte copies and byte swaps of the GEMDOS file system.
 *
 * `$fc55fa`, `$fc5622` and `$fc564a` are the same forty bytes of Alcyon output three times: a
 * `link`, then `move.b (a1),(a0)` with both pointers bumped IN THE FRAME, until a word count that
 * is post-decremented reaches zero. What differs is only which stack slot is the destination:
 *
 *   $fc55fa  copy_out(n, src, dst)   the transfer engine `$fc6218`'s copy function for a READ — it is
 *                                    handed `(n, cache, user)` and copies cache -> user ($fc5ec4)
 *   $fc5622  copy_in(n, dst, src)    ...and for a WRITE: the same three arguments, copied user ->
 *                                    cache ($fc5f20). The engine never knows which it was given.
 *   $fc564a  bcopy(n, src, dst)      byte-identical to $fc55fa; the one the rest of GEMDOS calls by
 *                                    name (the DND name, the DTA fields, `Pexec`'s basepage)
 *
 * ALL THREE ARE FORWARD BYTE COPIES, which is observable: an overlapping destination above the
 * source smears the first bytes forward, and nothing here is memmove.
 *
 * NO RESULT. The loop leaves D0's low word 0 (the last count it tested) over the caller's high half,
 * and no caller reads it — `$fc62fe`/`$fc6582` drop the arguments and go on, and every `bsr` site
 * re-loads D0 before its next test — so the cores are `void`.
 */
#ifndef TOS102US_GEMDOS_FS_COPY_H
#define TOS102US_GEMDOS_FS_COPY_H

#include <stdint.h>

/* A copy routine as the transfer engine CALLS it, in the order `$fc6218` pushes its arguments: the
 * count, the address inside the cached sector, then the caller's buffer. `gemdos_copy_out` and
 * `gemdos_copy_in` both have this shape; what they do with the two addresses is their difference.
 *
 * NOT what the engine is HANDED. `gemdos_ofd_xfer`'s `copy` parameter is the ROM ADDRESS its caller
 * pushes (`$fc55fa` or `$fc5622`, `include/gemdos/fs_io.h`), because that is the ROM's own argument
 * and what a case stages in the frame; the engine maps it to one of these once, at its entry
 * (`src/gemdos/fs_io.c`, `copy_routine_at`), and calls through the pointer from there on. */
typedef void (*gemdos_copy_fn)(uint8_t *image, uint16_t count, uint32_t cache, uint32_t user);

void gemdos_copy_out(uint8_t *image, uint16_t count, uint32_t source, uint32_t destination);
void gemdos_copy_in(uint8_t *image, uint16_t count, uint32_t destination, uint32_t source);
void gemdos_bcopy(uint8_t *image, uint16_t count, uint32_t source, uint32_t destination);

/* ---- the two byte swaps: a little-endian on-disk field turned round IN PLACE ----------------------
 * `$fc4f10` (`ror.w #8` on the word at its argument) and `$fc4f22` (`ror.w #8 / swap / ror.w #8` on
 * the long). How GEMDOS reads a DOS directory entry's cluster and length and a FAT12 pair. Both
 * leave the swapped value in D0 and no caller reads it, so neither returns anything. */
void os_swap_word(uint8_t *image, uint32_t at);
void os_swap_long(uint8_t *image, uint32_t at);

#endif /* TOS102US_GEMDOS_FS_COPY_H */
