/* blitter.c — the STE hardware-BLiTTER driver for the GAME_STE build target (PERF30 C4). Poke the
 * register block (include/blitter.h), start the chip, wait for done. The blitter emits the SAME
 * framebuffer bytes as the 68000 masked-blit engines, so every byte-compare pin still holds — this is
 * a perf swap, never a pixel change.
 *
 * SUPERVISOR ONLY. The 0xFFFF8Axx I/O page bus-errors from user mode; blitter_present() and blit_run()
 * are called from a Supexec excursion or the VBL (already supervisor). See game_main.c's STE boot check
 * and blitter_selftest().
 *
 * This file is compiled ONLY when build_game.sh is invoked with GAME_STE=1 — the stock ST binary never
 * links it, so the shipping .PRG is byte-for-byte unchanged (verified by hashing build/BUGGYBOY.PRG
 * with the flag off).
 */
#include "blitter.h"

/* ---- cookie jar (low memory, supervisor) ---- */
#define SYS_P_COOKIES   (*(volatile uint32_t *)0x5A0UL)   /* -> array of (tag,value) longs, 0-terminated */
#define COOKIE_BLT      0x5F424C54UL                       /* '_BLT' — set by TOS iff a blitter is present */
#define COOKIE_MCH      0x5F4D4348UL                       /* '_MCH' machine-type cookie (fallback probe) */
#define MCH_MACHINE_SHIFT 16                               /* _MCH value: machine id in the high word */
#define MCH_STE         1                                  /* STE/MegaSTE (high word 1) — has a blitter */
#define MCH_FALCON      3                                  /* Falcon030 — has a blitter (TT=2 does NOT) */

/* HOG-vs-shared: blit_run uses HOG (bit6) so the chip holds the bus and runs the whole pass to
 * completion in one go, then the CPU resumes with BUSY already clear. Justification: the masked object
 * blits this driver replaces are SMALL (a few dst words wide by <=43 rows) — tens of microseconds, far
 * under the 20 ms VBL period — so hogging the bus never starves the 50 Hz sound pump or the IKBD ISR
 * (they run in the gaps BETWEEN blits, one per object). Shared mode (HOG=0, 64-word bursts with a
 * CPU-side restart loop) only earns its keep on screen-sized blits where the CPU has overlapping work;
 * here there is none, so HOG is the simpler correct choice. The restart discipline for a future
 * screen-sized (road/scroll) blit is documented in BLIT_STE_SPEC.md.
 *
 * WAIT: after starting a HOG blit the 68000 is frozen until the chip releases the bus, so the very next
 * instruction already sees BUSY clear; a poll loop is kept anyway (belt-and-braces + it is the shape a
 * shared-mode restart would need). */
void blit_run(const BlitPass *p) {
    /* HOP=SRC never reads the halftone RAM, so this seed is not functionally required; we set halftone
     * lines 0-3 (the two longs written here) to 0xFFFF as belt-and-braces for a caller that later selects
     * a halftone HOP. The other 12 words are left as-is. */
    BLT_L(BLT_HALFTONE) = 0xFFFFFFFFUL;
    BLT_L(BLT_HALFTONE + 4) = 0xFFFFFFFFUL;

    BLT_W(BLT_SRC_X_INC) = (uint16_t)p->src_x_inc;
    BLT_W(BLT_SRC_Y_INC) = (uint16_t)p->src_y_inc;
    BLT_L(BLT_SRC_ADDR)  = p->src_addr;
    BLT_W(BLT_ENDMASK1)  = p->endmask1;
    BLT_W(BLT_ENDMASK2)  = p->endmask2;
    BLT_W(BLT_ENDMASK3)  = p->endmask3;
    BLT_W(BLT_DST_X_INC) = (uint16_t)p->dst_x_inc;
    BLT_W(BLT_DST_Y_INC) = (uint16_t)p->dst_y_inc;
    BLT_L(BLT_DST_ADDR)  = p->dst_addr;
    BLT_W(BLT_X_COUNT)   = p->x_count;
    BLT_W(BLT_Y_COUNT)   = p->y_count;
    BLT_B(BLT_HOP)       = p->hop;
    BLT_B(BLT_LOP)       = p->lop;
    BLT_B(BLT_SKEW)      = p->skew_ctl;

    /* Start: BUSY | HOG, halftone line 0. */
    BLT_B(BLT_CONTROL) = (uint8_t)(BLT_CTL_BUSY | BLT_CTL_HOG);
    while (BLT_B(BLT_CONTROL) & BLT_CTL_BUSY) { /* HOG completes before the next fetch; poll is a no-op */ }
}

/* True iff the machine has a BLiTTER. The _BLT cookie is authoritative — TOS creates it iff blitter
 * hardware is present — so it is checked first. On a pre-_BLT TOS we fall back to _MCH: the blitter-
 * equipped machines are STE/MegaSTE (high word 1) and Falcon030 (3); a plain ST (0) and — importantly —
 * the TT030 (2) have NONE, so the fallback must NOT accept "id >= 1". A pre-cookie TOS
 * (SYS_P_COOKIES == 0) is treated as no blitter. */
int blitter_present(void) {
    volatile uint32_t *jar = (volatile uint32_t *)SYS_P_COOKIES;
    if (!jar) return 0;
    int mch_has_blitter = 0;
    while (jar[0]) {
        if (jar[0] == COOKIE_BLT) return 1;              /* authoritative: a blitter exists */
        if (jar[0] == COOKIE_MCH) {
            uint32_t id = jar[1] >> MCH_MACHINE_SHIFT;
            mch_has_blitter = (id == MCH_STE || id == MCH_FALCON);
        }
        jar += 2;                            /* each entry is (tag, value) */
    }
    return mch_has_blitter;                   /* pre-_BLT fallback: STE/MegaSTE or Falcon only (not TT) */
}

/* User-mode-callable presence check: run blitter_present() in a supervisor excursion (the cookie jar
 * pointer at 0x5A0 is supervisor-only), like game_main's other supervisor touch-points. */
int blitter_available(void) {
    return (int)Supexec((long (*)(void))blitter_present);
}
