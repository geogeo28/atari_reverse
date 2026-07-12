/* os.c — OS-wrapper reconstructions (GEMDOS/BIOS/XBIOS glue @ various addresses).
 *
 * These thin wrappers push arguments and enter TOS via `trap`. Their effect lives in
 * hardware (video shifter, palette) or TOS state, not in our memory image, so the faithful
 * reconstruction touches nothing observable — the differential test confirms the oracle's
 * trap dispatch returns cleanly (reaches rts, no spurious image write). See os.h for the
 * modeled trap semantics both sides share.
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

/* xbios_setscreen @ 0x12226 — Setscreen(logbase = physbase = physbase_tbl[0], rez = -1).
 * Screen base + resolution are shifter/TOS state, not our image: no observable effect. */
void g_xbios_setscreen(uint8_t *image) { (void)image; }

/* xbios_setpalette @ 0x12eb0 — Setpalette(A0 = 16-word palette) -> hardware palette regs. */
void g_xbios_setpalette(uint8_t *image, uint32_t palette_ptr) { (void)image; (void)palette_ptr; }

/* set_rez @ 0x120f8 — store the low byte of D0 to a config global, then XBIOS 0x19 reads it
 * to set hardware (no image effect). Only the byte write is observable. */
void g_set_rez(uint8_t *image, uint32_t mode) {
    image[A_setrez_mode] = (uint8_t)mode;
}