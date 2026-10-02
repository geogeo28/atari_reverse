/* evdoor.c — the one definition of `aes/evdoor.h`'s host hook, the event door. WHY it exists is in that header.
 *
 * On TARGET this translation unit is empty: each door entry is the ROM's own call — its frame pushed, a `jsr` into the
 * ROM routine — and the hook is how the HOST build reaches a routine it cannot execute.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <stdint.h>

#include "aes/evdoor.h"

uint32_t (*recreate_call_event_door)(uint8_t *image, uint32_t routine, const uint8_t *frame, uint32_t frame_bytes,
                                     uint32_t *answer);
#endif
