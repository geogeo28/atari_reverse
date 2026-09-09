/* bubble_backend.c — the GEM door's three counters and its cache flag, and the three libc
 * functions a freestanding build owes GCC.
 *
 * THE DOOR ITSELF IS `bubble_os.s`'s, and its header comment is where the argument lives: every
 * pointer the cores put in a GEM parameter block is an IMAGE OFFSET, so a `trap #2` here has to
 * restate the block, and a raster copy has to patch two MFDBs the block only reaches by
 * dereference. It was C until wave 5a (`../STATUS.md`, "Performance") and cost 8,493 cycles a
 * frame: GCC cannot keep a value in a register across a `jsr` to a routine that traps, so every
 * live value went through the stack frame. What is left here is the STORAGE the door counts into
 * — which stays in C so that the widths the assembly hard-codes are pinned by the compiler.
 */
#include <stdint.h>

#include "bubble_target.h"

/* THE DOOR BUMPS THESE WITH `addq.l`, so their width is not free — a `uint16_t` here would have the
 * assembly add 1 to the longword straddling two of them. The same rule and the same spelling as the
 * four widths `bubble_main.c` pins for `bg_timer_c_entry` (wave 4). */
volatile uint32_t bg_vdi_calls;
volatile uint32_t bg_aes_calls;
volatile uint32_t bg_vdi_raster_copies;

_Static_assert(sizeof bg_vdi_calls == 4, "bg_gem_dispatch bumps this with `addq.l`");
_Static_assert(sizeof bg_aes_calls == 4, "bg_gem_dispatch bumps this with `addq.l`");
_Static_assert(sizeof bg_vdi_raster_copies == 4, "bg_gem_dispatch bumps this with `addq.l`");

/* WHETHER THE DOOR'S VDI PARAMETER-BLOCK CACHE HAS BEEN TAKEN — `bg_gem_cache_vdi_pblock` sets it,
 * and every VDI call tests it to choose between restating one slot and restating five (see
 * `shim_include/os.h`). Here rather than in the assembly's .bss for the counters' reason: the
 * assembly `move.b`s and `tst.b`s it, so a C type that grew would leave the door setting one byte
 * of the object and testing another — which is a SLOW door on a machine, not a broken one, and so
 * has no other surface at all. */
volatile uint8_t bg_vdi_pblock_cached;

_Static_assert(sizeof bg_vdi_pblock_cached == 1, "bg_gem_dispatch tests this one byte with `tst.b`");

/* ================================================================================================
 * The three libc functions, hand-written
 *
 * `-fno-tree-loop-distribute-patterns` is what stops GCC noticing that each of these is a memcpy or
 * a memset and replacing its body with a call to itself; `build.sh` passes it and there is no other
 * defence, so a build that lost the flag would recurse until the stack ran out.
 * ============================================================================================= */

void *memcpy(void *dst, const void *src, unsigned long n) {
    uint8_t *to = dst;
    const uint8_t *from = src;

    while (n--)
        *to++ = *from++;
    return dst;
}

void *memmove(void *dst, const void *src, unsigned long n) {
    uint8_t *to = dst;
    const uint8_t *from = src;

    if (to > from) {                       /* descending, so an overlap is read before it is written */
        to += n;
        from += n;
        while (n--)
            *--to = *--from;
        return dst;
    }
    while (n--)
        *to++ = *from++;
    return dst;
}

void *memset(void *dst, int c, unsigned long n) {
    uint8_t *to = dst;

    while (n--)
        *to++ = (uint8_t)c;
    return dst;
}
