/* hw.h — the ON-TARGET hardware-access header, shadowing the kit's for the PRG build only.
 *
 * It ADDS and replaces nothing: `#include_next` pulls in
 * `tools/recreate_kit/include/hw.h` whole, and the three prototypes below are the WRITE half that
 * file deliberately does not export yet. Its own words:
 *
 *   "WHAT IS NOT MODELED, and deliberately: a WRITE to one of these addresses. The oracle drops
 *    such a write exactly as it drops every other hardware write, so there is nothing for a
 *    reconstruction to mirror and no hw_write8() here."
 *
 * That is right for the differential and it is exactly what leaves the off-image class unpinned —
 * ../STATUS.md names a kit-level hardware-write ledger as the surface that would close it, in three
 * separate places. When that ledger lands it will export these three symbols from `hw.h` and route
 * `../src/irq_hw_offtarget.c`'s bodies through them; `zynaps_backend.c` already defines them under
 * those names and with those signatures, so the merge is deleting THIS FILE and nothing else.
 *
 * Until then the seam is the include path, as it is for os.h: build.sh puts this directory ahead of
 * the kit's. No CORE includes hw.h (measured — no Zynaps core calls `hw_read8` either), so this
 * shadow is visible only to the two shim translation units that ask for it.
 */
#ifndef ZYNAPS_TARGET_HW_H
#define ZYNAPS_TARGET_HW_H

#include <stdint.h>

#include_next "hw.h"

/* Store to a hardware register, in the 24-bit-bus address form the 68000 puts on the bus
 * ($ffff8240, not $ff8240). Defined in zynaps_backend.c, which is where the count they keep lives
 * too. A read-modify-write — the MFP's in-service acknowledge, the shifter's resolution byte — is
 * NOT one of these: those need the read half as well, and their call sites spell it. */
void hw_write8(uint32_t addr, uint8_t value);
void hw_write16(uint32_t addr, uint16_t value);
void hw_write32(uint32_t addr, uint32_t value);

#endif /* ZYNAPS_TARGET_HW_H */
