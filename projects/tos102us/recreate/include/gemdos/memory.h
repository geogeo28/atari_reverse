/* gemdos/memory.h — GEMDOS's memory manager: the MPB, the memory descriptors, and the pool the
 * descriptors themselves come out of.
 *
 * THREE STRUCTURES, ONE OF WHICH IS NOT THE ONE A PROGRAMMER EXPECTS.
 *
 *   * the MPB at `GEMDOS_MPB` — the three list heads `Getmpb` describes (`MPB_*` in addrs.h),
 *     except that GEMDOS keeps its OWN at $7e8e and hands it to `Getmpb` out of its init
 *     ($fc9356). Every routine here reaches it by that absolute address rather than through a
 *     parameter, which is why `Malloc` and `Mfree` have no MPB argument and `md_alloc` does.
 *   * the MEMORY DESCRIPTOR — link/start/length/owner (`MD_*` in addrs.h), sixteen bytes. A
 *     descriptor is on exactly one of the MPB's two lists. The FREE list is kept sorted by
 *     `m_start` ascending (`gemdos_md_free_insert` is the only thing that adds to it and it
 *     inserts in order); the ALLOCATED list is in no order at all — `gemdos_md_alloc` pushes onto
 *     its head.
 *   * the RECORD POOL, which is the surprising one: a descriptor is not a fixed array slot. It is
 *     a record of SIZE CLASS 1 out of a general-purpose pool that also serves basepages (class 16)
 *     and the file system's records, laid down by a bump allocator over 16,000 bytes of GEMDOS BSS
 *     and recycled through one free chain per class at `GEMDOS_P_ROOT`. That is the whole of TOS
 *     1.02's famous "out of memory descriptors": the bump arena runs out, `gemdos_pool_get`
 *     answers 0, and `Malloc` reports failure over RAM that is plainly free.
 *
 * WHERE THE POOL IS, exactly, and how this bootstrap knows: GEMDOS's init writes
 * `move.w #8000,$8780` ($fc936e) and `gemdos_pool_arena_alloc` bumps from `$2a6e`, so the arena is
 * $2a6e..$68ed and the word that counts the words handed out sits at $68f0, two bytes above its
 * top. COMPONENTS.md records the GEMDOS BSS extent as unestablished; this is the part of it the
 * memory group pins.
 *
 * THE OWNER IS `p_run`'s BASEPAGE AT THE MOMENT OF THE CALL, read through `GEMDOS_P_RUN` — which
 * is what makes a block releasable by process rather than by pointer, and what `Pterm` walks the
 * allocated list for. `gemdos_md_free_insert` and `gemdos_pool_free` are exported for that caller:
 * releasing a process's memory is "unlink from the allocated list, insert into the free list", the
 * same two calls `gemdos_mfree` makes.
 */
#ifndef TOS102US_GEMDOS_MEMORY_H
#define TOS102US_GEMDOS_MEMORY_H

#include <stdint.h>

#include "machine.h"
/* `MPB_FREE_LIST`/`MPB_ALLOCATED_LIST`/`MPB_ROVER` and `MD_LINK`/`MD_START`/`MD_LENGTH`/`MD_OWNER`
 * are already there — the layouts BIOS `Getmpb` established. Not re-spelt here. */
#include "addrs.h"

/* ---- the GEMDOS globals these routines reach by absolute address ------------------------------ */
/* `GEMDOS_P_RUN` is not here: `addrs.h` has it, the whole wave reads it through `gemdos/gemdos.h`'s
 * `gemdos_basepage`, and the same address in two headers is two places to keep one fact right. */
#define GEMDOS_MPB          0x7e8e  /* GEMDOS's own memory parameter block — mfl, mal, rover */
#define GEMDOS_P_ROOT       0x7e9c  /* the pool's free chain per size class; OS header +$20 */

/* ---- the record pool ($fc7ed0/$fc7f1a/$fc7f9c) ------------------------------------------------- */
#define GEMDOS_POOL_ARENA       0x2a6e /* the bump arena's base */
#define GEMDOS_POOL_USED_WORDS  0x68f0 /* word: WORDS handed out so far — the bump cursor */
#define GEMDOS_POOL_FREE_WORDS  0x8780 /* word: words still to hand out; init writes 8000 there */
#define GEMDOS_POOL_ARENA_WORDS 8000   /* ...that 8000, so the arena's extent is derivable */
/* A size class is a count of EIGHT-WORD units: `asl.w #3` turns the class into the record's size in
 * words, so class 1 is a 16-byte memory descriptor and class 16 the 256-byte basepage GEMDOS's init
 * allocates for the root process. */
#define POOL_CLASS_WORDS_SHIFT  3
#define POOL_CHAIN_ENTRY_BYTES  4      /* one free-chain head per class, indexed off GEMDOS_P_ROOT */
#define POOL_CLASS_HEADER_BYTES 2      /* the class word the pool writes BELOW every record */
#define MD_SIZE_CLASS           1      /* ...and the class a memory descriptor is */
#define MD_BYTES               16

/* ---- what the three trap routines answer ------------------------------------------------------- */
/* `Malloc(-1)` reports the largest free block instead of allocating one, and the test is made
 * against the WHOLE longword before the odd-size rounding below — which is the whole of why the
 * rounding cannot simply be applied first. */
#define MALLOC_LARGEST_FREE_BLOCK 0xffffffffu
/* The two error codes these three arms leave, as the whole D0 a `moveq` sign-extends into. */
#define GEMDOS_EIMBA        0xffffffd8u /* -40: no allocated block starts at that address */
#define GEMDOS_EGSBF        0xffffffbdu /* -67: Mshrink asked to GROW a block */

/* ---- the cores -------------------------------------------------------------------------------- */
/* The pool, innermost first. `gemdos_pool_arena_alloc` takes a WORD count of words and is the only
 * thing that can fail; `gemdos_pool_get` takes a size class and answers a ZEROED record; and
 * `gemdos_pool_free` reads the class back out of the record's own header word. */
uint32_t gemdos_pool_arena_alloc(uint8_t *image, uint16_t words);
uint32_t gemdos_pool_get(uint8_t *image, uint16_t size_class);
void gemdos_pool_free(uint8_t *image, uint32_t record);

/* The two list routines every trap routine here is built out of. `gemdos_md_alloc` answers the
 * DESCRIPTOR (or the largest free length, for `MALLOC_LARGEST_FREE_BLOCK`, or 0); its caller is the
 * one that turns that into an address. `gemdos_md_free_insert` puts a descriptor back on the sorted
 * free list and coalesces it with its neighbours. */
uint32_t gemdos_md_alloc(uint8_t *image, uint32_t amount, uint32_t mpb);
void gemdos_md_free_insert(uint8_t *image, uint32_t md, uint32_t mpb);

/* GEMDOS $48/$49/$4a. `gemdos_mshrink` does not take the reserved zero WORD its caller pushes below
 * the block address: the ROM never reads it (see the core). */
uint32_t gemdos_malloc(uint8_t *image, uint32_t amount);
uint32_t gemdos_mfree(uint8_t *image, uint32_t address);
uint32_t gemdos_mshrink(uint8_t *image, uint32_t block, uint32_t new_length);

#endif /* TOS102US_GEMDOS_MEMORY_H */
