/* host_slot.c — `include/host_slot.h`'s held flags: one per slot, host build only.
 *
 * Its own file at the top of src/, because the table is shared by every component and belongs beside
 * none of their cores. On target a slot IS the frame local, nothing is held, and this is empty.
 */
#include "host_slot.h"

#ifdef RECREATE_HOST_DIFFERENTIAL
unsigned char host_slots_held[HOST_SLOT_ID_COUNT];
#endif
