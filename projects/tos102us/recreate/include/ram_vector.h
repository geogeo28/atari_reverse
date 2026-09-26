/* ram_vector.h — a core that reaches a ROM body through a RAM VECTOR, checked rather than assumed.
 *
 * TOS reaches its screen bodies through longwords of RAM — the console's four and the VDI's six
 * drawing vectors (`vdi/linea.h`) — which the boot fills with the CPU set and XBIOS Blitmode can
 * refill with the blitter set. A core reconstructs the CPU body and calls it BY NAME; this is the check
 * that the vector really holds that body, and the HALT on both builds when it does not, so a case that
 * repoints a vector is refused rather than served by the wrong code (`vdi/linea.h` has the policy).
 */
#ifndef TOS102US_RAM_VECTOR_H
#define TOS102US_RAM_VECTOR_H

#include <stdint.h>

#include "machine.h"
#include "recreate.h"

/* `move.l <vector>,a5 / jmp (a5)` — the vector, checked against the one routine the caller
 * reconstructs. `what` names the caller for a reader who hits the halt. */
static inline void require_cpu_routine(const uint8_t *image, uint32_t vector, uint32_t cpu_routine,
                                       const char *what)
{
    if (be32(image + vector) != cpu_routine)
        recreate_not_reconstructed(what);
}

#endif /* TOS102US_RAM_VECTOR_H */
