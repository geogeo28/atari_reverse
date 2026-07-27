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
#include <string.h>       /* memset — the placement zeroing below */

#include "blitter.h"

/* ---- cookie jar (low memory, supervisor) ---- */
#define SYS_P_COOKIES   (*(volatile uint32_t *)0x5A0UL)   /* -> array of (tag,value) longs, 0-terminated */
#define COOKIE_BLT      0x5F424C54UL                       /* '_BLT' — set by TOS iff a blitter is present */
#define COOKIE_MCH      0x5F4D4348UL                       /* '_MCH' machine-type cookie (fallback probe) */
#define MCH_MACHINE_SHIFT 16                               /* _MCH value: machine id in the high word */
#define MCH_STE         1                                  /* STE/MegaSTE (high word 1) — has a blitter */
#define MCH_FALCON      3                                  /* Falcon030 — has a blitter (TT=2 does NOT) */

/* Poke every register of one pass and STOP — the caller owns the bus policy. Split out of blit_run so
 * the road-scroll route can poke a pass and start it in SHARED-bus mode (blit_start_and_wait_shared);
 * blit_run below is this plus the HOG start.
 *
 * HOG-vs-shared, per route: blit_run's callers are the masked OBJECT blits, which are SMALL (a few dst
 * words wide by <=43 rows) — tens of microseconds, far under the 20 ms VBL period — so hogging the bus
 * never starves the 50 Hz sound pump or the IKBD ISR (they run in the gaps BETWEEN blits, one per
 * object), and HOG is the simpler correct choice. Shared mode (HOG=0, 64-word bursts with a CPU-side
 * restart loop) earns its keep on SCREEN-SIZED passes, where a single hold would freeze the 68000 for
 * milliseconds: that is the road-scroll route, and BLIT_STE_SPEC §16 carries its measured
 * HOG-vs-restart numbers. Both starts live in blitter.h so the two policies cannot drift apart. */
void blit_poke(const BlitPass *p) {
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
}

void blit_run(const BlitPass *p) {
    blit_poke(p);
    blit_start_and_wait();                   /* BUSY | HOG, halftone line 0 (blitter.h) */
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

/* ---- the fine-x object routes, enumerated once (see blitter.h) ---------------------------------- */

/* Lay both routes' lookup tables out in `window` (the free TPA above the program — see game_main.c's TPA
 * map) and hand each module its base. Returns 0 when the window is too small, which is the whole point of
 * the check: a 1 MB machine may not have 170 KB to spare above a ~700 KB program, and the caller then
 * binds the CPU engines exactly as it would on a machine with no blitter at all.
 *
 * The memory is UNINITIALISED (GEMDOS zeroes the BSS, not the TPA above it), and both tables mark a free
 * slot with a zero field — Objsh2Cache.valid, ObjshSkewEntry.rows_done — so the whole window is zeroed
 * here rather than each module re-deriving the BSS-zero assumption it was written under. */
static int blit_tables_place(uint8_t *window, uint32_t window_bytes) {
    uint32_t misalign = (uint32_t)(unsigned long)window & (BLIT_TABLE_ALIGN - 1);
    uint32_t pad = (BLIT_TABLE_ALIGN - misalign) & (BLIT_TABLE_ALIGN - 1);
    uint32_t cache_bytes = rm_blit_objshift2_cache_bytes();
    uint32_t table_bytes = rm_blit_objshift_skew_table_bytes();
    uint32_t need = pad + cache_bytes + table_bytes;      /* both sizes are multiples of BLIT_TABLE_ALIGN */
    if (window_bytes < need) return 0;

    uint8_t *p = window + pad;
    memset(p, 0, cache_bytes + table_bytes);
    rm_blit_objshift2_cache_place(p);
    rm_blit_objshift_skew_table_place(p + cache_bytes);
    rm_blit_objshift_skew_table_flush();                  /* clears the start-latched full flag */
    return 1;
}

/* Boot: place the OBJECT routes' tables, then point every seam at the hardware blitter when one is
 * present, else at the 68000 CPU engines. Called once from main() after blitter_available(); returns the
 * binding the TABLED routes actually made (0 when there was no blitter, or no room for their tables).
 *
 * The road-scroll route is bound FIRST and on the probe result alone, because it is the one route with
 * no lookup table: it blits out of the `shifted` buffer the CPU reference already reads, so a TPA too
 * small to place 170 KB of object tables (the 1 MB STE's thin margin — BLIT_STE_SPEC §15) has no bearing
 * on it. A machine that loses the object routes therefore still keeps the scroll on the chip. */
int rm_blit_bind_all(int have_blitter, void *window, uint32_t window_bytes) {
    rm_blit_road_scroll_bind(have_blitter);
    if (have_blitter && !blit_tables_place((uint8_t *)window, window_bytes)) have_blitter = 0;
    rm_blit_objshift2_bind(have_blitter);
    rm_blit_objshift_bind(have_blitter);
    return have_blitter;
}

/* Reload: both routes memoise bitmaps built from the arena.gfx bytes, which the F10 asset reload
 * rewrites IN PLACE at the same address — so every materialised bitmap must be dropped or the routes
 * would serve bitmaps built from the old contents. */
void rm_blit_flush_all(void) {
    rm_blit_objshift2_cache_flush();
    rm_blit_objshift_skew_table_flush();
}
