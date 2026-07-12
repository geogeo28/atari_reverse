/* os.h — deterministic TOS trap model shared by the oracle (shim.c) and reconstructed
 * OS wrappers. The oracle can't call real TOS, so GEMDOS/BIOS/XBIOS traps are serviced
 * with fixed semantics; a reconstruction must model the SAME return value and image effect
 * for its differential test to hold.
 *
 * Modeled: calls that only touch hardware or files (Setpalette/Setcolor/Setscreen, sound,
 * console I/O, Ikbdws) have NO image effect and return 0. Physbase/Logbase return
 * OS_SCREEN_BASE; Getrez returns 0 (low-res); Malloc bump-allocates from OS_HEAP_BASE;
 * Mshrink/Mfree return 0. GEMDOS Fopen/Fread/Fclose are modeled by os_fopen/os_fread/os_fclose
 * over a staged-file table (below). XBIOS Supexec runs the passed routine in place (its rts
 * returns to the caller, its D0 becomes the result).
 *
 * GEM trap #2 (AES/VDI) is modeled by os_gem_trap() below — the same code the oracle's
 * shim and the reconstructed gem_aes/gem_vdi wrappers both run, so their image writes agree
 * by construction. Only the three opcodes BuggyBoy actually uses are modeled.
 *
 * DEFERRED (serviced as return 0, effect NOT modeled): GEMDOS Super. A function that depends
 * on it cannot be verified until the model is extended — see recreate/README.md.
 * OS_HEAP_BASE/OS_SCREEN_BASE are provisional low-memory arenas that only fit small blocks;
 * functions that Malloc large screen buffers need Malloc pointed at a real in-image block.
 */
#ifndef BB_OS_H
#define BB_OS_H

#include <string.h>
#include "machine.h"

#define OS_SCREEN_BASE 0x8000u   /* Physbase/Logbase result (in-image screen region) */
#define OS_HEAP_BASE   0x1000u   /* Malloc bump arena start (small blocks only) */

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

/* ---- GEMDOS file I/O (Fopen 0x3d / Fread 0x3f / Fclose 0x3e) -------------------------
 * The oracle can't touch a real filesystem, so files are *staged* into the image: the harness
 * writes each file's raw bytes into the staging area and one table entry per file. os_fopen
 * resolves a filename to a handle, os_fread copies bytes out of staging, os_fclose releases the
 * slot — all pure image operations shared by the shim and the reconstructed loaders. An
 * unstaged filename / bad handle returns -1, which the caller treats as unmodeled (rejected),
 * so a loader reading a file we didn't stage can never be falsely "verified".
 *
 * Table entry (OS_FS_ENTRY bytes): name[16] (nul-terminated) | staging addr u32 | size u32 |
 * cursor u32 | open flag u32. The harness lays out the same layout (see harness.stage_files);
 * the open/read round-trip test pins the two in agreement. */
#define OS_FS_TABLE        0xbf000u  /* staged-file table: OS_FS_SLOTS entries of OS_FS_ENTRY bytes */
#define OS_FS_STAGING      0xc0000u  /* raw file bytes, laid out below the stack by the harness */
#define OS_FS_SLOTS        8
#define OS_FS_ENTRY        32
#define OS_FS_NAME         16        /* name field width; filenames must be < 16 chars */
#define OS_FS_FIRST_HANDLE 6         /* GEMDOS handles 0..5 are reserved; files start here */

static inline int os_fs_name_eq(const uint8_t *a, const uint8_t *b) {
    for (int i = 0; i < OS_FS_NAME; i++) {
        if (a[i] != b[i]) return 0;
        if (a[i] == 0) return 1;
    }
    return 1;                                        /* matched the whole (unterminated) field */
}

/* Fopen(name): match the staged-file table, reset the cursor, return a handle (>= 6), or -1. */
static inline int32_t os_fopen(uint8_t *mem, uint32_t name_ptr) {
    for (int slot = 0; slot < OS_FS_SLOTS; slot++) {
        uint8_t *e = mem + OS_FS_TABLE + slot * OS_FS_ENTRY;
        if (e[0] == 0) continue;                     /* empty slot */
        if (os_fs_name_eq(mem + name_ptr, e)) {
            wr32(e + 24, 0);                         /* cursor = 0 */
            wr32(e + 28, 1);                         /* open */
            return OS_FS_FIRST_HANDLE + slot;
        }
    }
    return -1;
}

/* Fread(handle, count, buf): copy min(count, remaining) bytes from the cursor into buf, advance
 * the cursor, return the byte count. -1 if the handle isn't an open staged file. */
static inline int32_t os_fread(uint8_t *mem, uint16_t handle, uint32_t count, uint32_t buf) {
    int slot = (int)handle - OS_FS_FIRST_HANDLE;
    if (slot < 0 || slot >= OS_FS_SLOTS) return -1;
    uint8_t *e = mem + OS_FS_TABLE + slot * OS_FS_ENTRY;
    if (e[0] == 0 || be32(e + 28) == 0) return -1;   /* not staged / not open */
    uint32_t staging = be32(e + 16), size = be32(e + 20), cursor = be32(e + 24);
    uint32_t n = size - cursor;                      /* remaining; cursor never exceeds size */
    if (count < n) n = count;
    memcpy(mem + buf, mem + staging + cursor, n);
    wr32(e + 24, cursor + n);
    return (int32_t)n;
}

/* Fclose(handle): mark the slot closed. -1 on a bad handle. */
static inline int32_t os_fclose(uint8_t *mem, uint16_t handle) {
    int slot = (int)handle - OS_FS_FIRST_HANDLE;
    if (slot < 0 || slot >= OS_FS_SLOTS) return -1;
    uint8_t *e = mem + OS_FS_TABLE + slot * OS_FS_ENTRY;
    if (e[0] == 0) return -1;
    wr32(e + 28, 0);
    return 0;
}

#endif /* BB_OS_H */