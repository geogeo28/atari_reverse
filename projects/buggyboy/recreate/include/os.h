/* os.h — deterministic TOS trap model shared by the oracle (shim.c) and reconstructed
 * OS wrappers. The oracle can't call real TOS, so GEMDOS/BIOS/XBIOS traps are serviced
 * with fixed semantics; a reconstruction must model the SAME return value and image effect
 * for its differential test to hold.
 *
 * Modeled: calls that only touch hardware or files (Setpalette/Setcolor/Setscreen, sound,
 * console I/O, Ikbdws) have NO image effect and return 0. Physbase/Logbase return
 * OS_SCREEN_BASE; Getrez returns 0 (low-res); Malloc bump-allocates from OS_HEAP_BASE;
 * Mshrink/Mfree/Fclose return 0; Fopen returns OS_FILE_HANDLE. XBIOS Supexec runs the
 * passed routine in place (its rts returns to the caller, its D0 becomes the result).
 *
 * GEM trap #2 (AES/VDI) is modeled by os_gem_trap() below — the same code the oracle's
 * shim and the reconstructed gem_aes/gem_vdi wrappers both run, so their image writes agree
 * by construction. Only the three opcodes BuggyBoy actually uses are modeled.
 *
 * DEFERRED (serviced as return 0, effect NOT modeled): GEMDOS Fread (needs a file model)
 * and GEMDOS Super. A function that depends on these cannot be verified until the model is
 * extended — see recreate/README.md. OS_HEAP_BASE/OS_SCREEN_BASE are provisional low-memory
 * arenas that only fit small blocks; functions that Malloc large screen buffers need a
 * larger IMAGE_SIZE first.
 */
#ifndef BB_OS_H
#define BB_OS_H

#include "machine.h"

#define OS_SCREEN_BASE 0x8000u   /* Physbase/Logbase result (in-image screen region) */
#define OS_HEAP_BASE   0x1000u   /* Malloc bump arena start (small blocks only) */
#define OS_FILE_HANDLE 6u        /* Fopen result */

/* ---- GEM trap #2 (AES / VDI) --------------------------------------------------------
 * A trap #2 selects the subsystem by D0 and points D1 at a parameter block of array
 * pointers. AES: apb = {contrl, global, intin, intout, addrin, addrout}; VDI:
 * vpb = {contrl, intin, ptsin, intout, ptsout}. The opcode is contrl[0]; results go into
 * intout (and ptsout for VDI). BuggyBoy issues exactly three calls, all during _start:
 * appl_init, graf_handle, v_opnvwk — anything else is left unmodeled on purpose. */
#define GEM_AES 0xc8u            /* D0 for an AES call */
#define GEM_VDI 0x73u            /* D0 for a VDI call */

#define AES_APPL_INIT   10       /* -> ap_id in intout[0] */
#define AES_GRAF_HANDLE 77       /* -> phys handle + font cell sizes in intout[0..4] */
#define VDI_V_OPNVWK    100      /* -> device attributes in intout[0..] (work_out) */

/* Deterministic "realistic low-res ST" results (320x200, 16 colours). None are read back by
 * the game — _start only reuses graf_handle's handle as the VDI handle — so the exact values
 * matter for faithfulness/documentation, not for downstream behaviour. */
#define OS_AES_AP_ID    0        /* appl_init: single-application id */
#define OS_VDI_HANDLE   1        /* graf_handle: physical workstation handle */
#define OS_FONT_CELL_W  8        /* low-res system font cell / box width  (px) */
#define OS_FONT_CELL_H  8        /* low-res system font cell / box height (px) */
#define OS_SCREEN_MAX_X 319      /* v_opnvwk work_out[0]: max addressable x (xres-1) */
#define OS_SCREEN_MAX_Y 199      /* v_opnvwk work_out[1]: max addressable y (yres-1) */

/* Service a trap #2. Reads the parameter block at `pblk` in `mem`, writes the modeled
 * outputs, and returns 1 if the opcode is modeled, 0 otherwise (an unmodeled opcode must be
 * rejected, never diffed against a fabricated result). Shared verbatim by shim.c and the
 * gem_aes/gem_vdi reconstruction so both sides produce identical image writes. */
static inline int os_gem_trap(uint8_t *mem, uint32_t d0, uint32_t pblk) {
    uint32_t contrl = be32(mem + pblk);              /* apb[0] / vpb[0] */
    uint16_t opcode = be16(mem + contrl);            /* contrl[0] */

    if (d0 == GEM_AES) {
        uint32_t intout = be32(mem + pblk + 3 * 4);  /* apb[3] */
        if (opcode == AES_APPL_INIT) {
            wr16(mem + intout, OS_AES_AP_ID);
            return 1;
        }
        if (opcode == AES_GRAF_HANDLE) {
            wr16(mem + intout + 0, OS_VDI_HANDLE);
            wr16(mem + intout + 2, OS_FONT_CELL_W);  /* wchar */
            wr16(mem + intout + 4, OS_FONT_CELL_H);  /* hchar */
            wr16(mem + intout + 6, OS_FONT_CELL_W);  /* wbox  */
            wr16(mem + intout + 8, OS_FONT_CELL_H);  /* hbox  */
            return 1;
        }
        return 0;
    }
    if (d0 == GEM_VDI) {
        uint32_t intout = be32(mem + pblk + 3 * 4);  /* vpb[3] */
        if (opcode == VDI_V_OPNVWK) {
            /* work_out: only the two determinate low-res fields; the rest of the VDI
             * attribute table is left zero (no code reads it). */
            wr16(mem + intout + 0, OS_SCREEN_MAX_X);
            wr16(mem + intout + 2, OS_SCREEN_MAX_Y);
            return 1;
        }
        return 0;
    }
    return 0;
}

#endif /* BB_OS_H */