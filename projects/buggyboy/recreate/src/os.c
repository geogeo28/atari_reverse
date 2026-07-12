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
#include "os.h"

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

/* gem_aes @ 0x100dc — D1 = &aes_pblk, D0 = 0xC8, trap #2. The AES call's outputs land in the
 * param block's intout array; os_gem_trap models them (see os.h). */
void g_gem_aes(uint8_t *image) { os_gem_trap(image, GEM_AES, A_aes_pblk); }

/* gem_vdi @ 0x100ea — D1 = &vdi_pblk, D0 = 0x73, trap #2. */
void g_gem_vdi(uint8_t *image) { os_gem_trap(image, GEM_VDI, A_vdi_pblk); }

/* _start @ 0x10000 — program entry. Mshrink to release unused memory, then bring GEM up:
 * AES appl_init, AES graf_handle (its physical handle becomes the VDI handle), then
 * VDI v_opnvwk to open the screen workstation — before calling main.
 *
 * Reconstructed up to the `bsr main` at 0x100d4 (the checkpoint): main is the infinite game
 * loop and never returns, so _start is verified there, not at rts. Mshrink has no image effect
 * (os.h). The entry code also clears an AES global-array scratch (0x19a7c..0x19a88) that is
 * already zero at load — a no-op, so it is omitted here. Sets contrl exactly as the original
 * does per call, so the surviving fields (e.g. graf_handle's cell sizes in intout[2..4]) match. */
void g_start(uint8_t *image) {
    uint8_t *contrl = image + A_aesvdi_contrl;   /* contrl[i] at +2*i; contrl[6] at +12 */

    /* AES appl_init: contrl = {10, 0, 1, 0, 0} -> ap_id in intout[0]. */
    wr16(contrl + 0, AES_APPL_INIT);
    wr16(contrl + 2, 0); wr16(contrl + 4, 1); wr16(contrl + 6, 0); wr16(contrl + 8, 0);
    os_gem_trap(image, GEM_AES, A_aes_pblk);

    /* AES graf_handle: contrl = {77, 0, 5, 0, 0} -> handle + font cell sizes in intout[0..4]. */
    wr16(contrl + 0, AES_GRAF_HANDLE);
    wr16(contrl + 2, 0); wr16(contrl + 4, 5); wr16(contrl + 6, 0); wr16(contrl + 8, 0);
    os_gem_trap(image, GEM_AES, A_aes_pblk);

    /* Reuse the returned physical handle (intout[0]) as the VDI workstation handle. */
    uint16_t handle = be16(image + A_vdi_ws_handle);
    wr16(image + A_vdi_handle, handle);

    /* VDI v_opnvwk: contrl[0]=100, [1]=0, [3]=11 (intin count), [6]=handle; leaves contrl[2]=5
     * from graf_handle untouched, as the original does. work_in (intin) = ten 1s then a 2. */
    wr16(contrl + 0, VDI_V_OPNVWK);
    wr16(contrl + 2, 0); wr16(contrl + 6, 11); wr16(contrl + 12, handle);
    for (int i = 0; i < 10; i++) wr16(image + A_vdi_intin + 2 * i, 1);
    wr16(image + A_vdi_intin + 20, 2);
    os_gem_trap(image, GEM_VDI, A_vdi_pblk);
}