/* os_heap.c — the CANDIDATE side's copy of the modeled Malloc arena's base. The mechanism is in
 * ../README.md, "The Malloc arena is the one region a project places"; the key that sets it is
 * `heap_base` in a project's project.toml, and the ORACLE keeps its own copy in oracle/shim.c.
 *
 * ON-TARGET builds do not compile this file: there the heap is real TOS's, and a target build that
 * read OS_HEAP_BASE would fail at link rather than silently allocate from a stale default.
 */
#include <stdint.h>

#include "os.h"

/* The default is os.h's, so an unbound candidate — one nobody installed a base into — behaves
 * exactly as every candidate did before the key existed. */
uint32_t g_os_heap_base = OS_HEAP_BASE_DEFAULT;

void os_set_heap_base(uint32_t base) { g_os_heap_base = base; }
