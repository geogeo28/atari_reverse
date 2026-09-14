/* XBIOS Logbase (function 3) — $fc0aa6.
 *
 *      move.l  SYSVAR_V_BAS_AD,d0
 *      rts
 *
 * The LOGICAL screen base: where the VDI and the console draw, which is not necessarily where the
 * shifter reads (that is `Physbase`, $fc0a92, and it asks the chip rather than RAM — which is why it
 * is out of reach here and this one is not). `Setscreen` ($fc0ab8) is the writer.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"

uint32_t xbios_logbase(const uint8_t *image)
{
    return be32(image + SYSVAR_V_BAS_AD);
}
