/* The one definition of `include/staged_call.h`'s host hook. WHY it exists is in that header.
 *
 * It is a file of its own rather than a line at the top of `vbl.c` because three handlers reach it
 * and none of them owns it. On TARGET this translation unit is empty: the hook is how the HOST
 * build transfers control to a routine it cannot execute, and the machine has a `jsr`.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <stdint.h>

#include "staged_call.h"

void (*recreate_call_vector)(uint8_t *image, uint32_t routine, uint32_t argument);
#endif
