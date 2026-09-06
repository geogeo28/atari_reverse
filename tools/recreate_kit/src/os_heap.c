/* os_heap.c — the CANDIDATE side's copy of the modeled Malloc arena: where it starts, how far it may
 * grow, and the bump allocator itself. The mechanism that places it is in ../README.md, "The Malloc
 * arena is the one region a project places"; the keys that set it are `heap_base` / `heap_limit` in
 * a project's project.toml, and the ORACLE keeps its own copy in oracle/shim.c.
 *
 * ON-TARGET builds do not compile this file: there the heap is real TOS's, and a target build that
 * read OS_HEAP_BASE would fail at link rather than silently allocate from a stale default.
 */
#include <stdint.h>

#include "os.h"

/* The defaults are os.h's, so an unbound candidate — one nobody installed a base or a ceiling into —
 * behaves exactly as every candidate did before the keys existed. */
uint32_t g_os_heap_base = OS_HEAP_BASE_DEFAULT;
uint32_t g_os_heap_limit = OS_HEAP_LIMIT_DEFAULT;

/* ---- ...and the arena itself: the candidate's GEMDOS Malloc ---------------------------------
 * A bump pointer walking up from the base, mirroring what oracle/shim.c's trap handler does. WHY a
 * reconstruction calls this instead of carrying its own copy of the arithmetic is in os.h, beside
 * the declaration.
 *
 * `g_os_heap_reset` is called by harness.arm_candidate before EVERY candidate run, so a run starts
 * from the base the way the oracle's does; without it the second case in a process would allocate
 * where the first left off.
 */
/* Initialised to the default rather than to zero, so an unreset candidate allocates from the
 * arena rather than from address 0 — the same defensive default g_os_heap_base carries. */
static uint32_t g_os_heap = OS_HEAP_BASE_DEFAULT;

/* Installing a base REWINDS the pointer to it, rather than leaving it in whichever arena it was
 * last in. Without that a candidate whose project moved its heap allocated from
 * OS_HEAP_BASE_DEFAULT — the wrong arena entirely — for every os_malloc before the first reset. */
void os_set_heap_base(uint32_t base) { g_os_heap_base = base; g_os_heap = base; }
void os_set_heap_limit(uint32_t limit) { g_os_heap_limit = limit; }

void     g_os_heap_reset(void)   { g_os_heap = g_os_heap_base; }
uint32_t g_os_heap_pointer(void) { return g_os_heap; }

/* Round the request up to a word and hand back the pointer from BEFORE the bump.
 *
 * Two answers that are not that: Malloc(-1) is GEMDOS's "how big is the largest free block?" query
 * and reports the SIZE the window still holds without moving the pointer; and a request the window
 * cannot hold is REFUSED rather than served past the ceiling, because a block over the staged-file
 * table is a plain image write on both sides and the two corrupted runs would compare equal. Both
 * facts are the shim's too (os.h, beside the declaration). */
uint32_t os_malloc(uint32_t size) {
    uint32_t block = g_os_heap;
    /* Never a negative window: a ceiling installed below the pointer leaves nothing free rather
     * than wrapping to ~4 GB, which Malloc(-1) would report as an arena the model does not have. */
    uint32_t free_bytes = g_os_heap < g_os_heap_limit ? g_os_heap_limit - g_os_heap : 0;
    uint32_t want;

    if (size == OS_MALLOC_LARGEST_FREE) return free_bytes;
    want = (size + 1u) & ~1u;
    if (want > free_bytes) return (uint32_t)os_refused(0);
    g_os_heap += want;
    return block;
}
