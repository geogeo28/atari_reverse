/* evdoor.c — the one definition of the host hooks of `aes/evdoor.h` (the event door) and `aes/switch.h` (the
 * dispatcher's entry). WHY each exists is in its header.
 *
 * On TARGET this translation unit is empty: a door entry is the ROM's own call (its frame pushed, a `jsr` into the ROM
 * routine) or its C twin's, the dispatcher's entry is the switch's own, and a hook is how the HOST build reaches what
 * it cannot execute.
 */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <stdint.h>

#include "aes/evdoor.h"
#include "aes/switch.h"

uint32_t (*recreate_call_event_door)(uint8_t *image, uint32_t routine, const uint8_t *frame, uint32_t frame_bytes,
                                     uint32_t *answer);
void (*recreate_event_door_returned)(uint8_t *image, uint32_t routine, uint32_t answer);
uint32_t (*recreate_dispatch)(uint8_t *image);

/* dsptch as a case reaches it by name (`test/test_aes_event.py`, the dispatcher's hook): the header's inline, given a
 * symbol — no twin calls dsptch yet, and the hook's refusal is pinned before one does. */
void aes_dsptch_entered(uint8_t *image)
{
    aes_dsptch(image);
}
#endif
