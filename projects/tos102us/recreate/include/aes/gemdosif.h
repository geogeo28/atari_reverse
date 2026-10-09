/* aes/gemdosif.h — the AES's own GEMDOS glue (`src/aes/gemdosif.c`): the doors a score of Line-F callers take to
 * GEMDOS — dos_alloc and dos_free (`Malloc`, `Mfree`), and the file calls the shell and the resource load make.
 *
 * HAND 68000, entered by a Line-F call (or a `jsr`) over the frame its caller pushed, each answering D0 as its tail
 * leaves it. All but dos_alloc go through the glue's `__DOS` ($fe3c3e), which parks the return address it was
 * reached with in AES_TRAP1_RETURN, takes the trap, and leaves the answer's word in AES_DOS_AX and its LONG's sign in
 * AES_DOS_ERR — the verdict every caller tests. The file calls reach `__DOS` by their own `bsr`, so what is parked is
 * a site inside the glue (AES_DOS_*_TRAP_RETURN). dos_free, dos_sdta, dos_close and Cconout go through $fe3c28 instead, which
 * also PARKS ITS CALLER'S return address in AES_DOS_RETURN: that address is the machine's, carried by no frame, so the
 * host build is handed it (`return_site`, `vdi.declare_alcyon`'s host argument — the VDI door's `gemdos_call`
 * precedent).
 */
#ifndef TOS102US_AES_GEMDOSIF_H
#define TOS102US_AES_GEMDOSIF_H

#ifndef __ASSEMBLER__
#include <stdint.h>

#include "machine.h"
#endif
#include "aes/aes.h"

/* What the glue leaves in AES_DOS_AX for the errors its callers retry on: the MS-DOS numbers GEM was written against
 * ($fe3a3c move.w #18; $fe3a6a move.w #2), which sh_find tests with a third, 3, nothing here produces. */
#define DOS_AX_FILE_NOT_FOUND 2          /* dos_open's EFILNF                                                 */
#define DOS_AX_PATH_NOT_FOUND 3          /* ($feb02a cmpi.w #3): only a GEMDOS answer of that very word      */
#define DOS_AX_NO_MORE_FILES  18         /* dos_sfirst's EFILNF and ENMFIL                                     */

#ifndef __ASSEMBLER__
/* The verdict every caller of the glue tests: the last call failed (`tst.w $98ec`). */
static inline int aes_dos_failed(const uint8_t *image)
{
    return be16(image + AES_DOS_ERR) != 0;
}

uint32_t aes_dos_alloc(uint8_t *image, uint32_t bytes);                                             /* $fe3bba */
uint32_t aes_dos_free(uint8_t *image, uint32_t return_site, uint32_t block);                        /* $fe3c26 */
int16_t aes_dos_sfirst(uint8_t *image, uint32_t name, int16_t attributes);                          /* $fe3a1c */
uint32_t aes_dos_open(uint8_t *image, uint32_t name, int16_t mode);                                 /* $fe3a52 */
uint32_t aes_dos_read(uint8_t *image, int16_t handle, int16_t count, uint32_t buffer);              /* $fe3a78 */
uint32_t aes_dos_lseek(uint8_t *image, int16_t handle, int16_t mode, uint32_t offset);              /* $fe3a9a */
uint32_t aes_dos_sdta(uint8_t *image, uint32_t return_site, uint32_t dta);                          /* $fe3c06 */
uint32_t aes_dos_close(uint8_t *image, uint32_t return_site, int16_t handle);                       /* $fe3c0a */
int16_t aes_dos_snext(uint8_t *image);                                                              /* $fe3a46 */
uint32_t aes_dos_cconout(uint8_t *image, uint32_t return_site, int16_t character);                  /* $fe3bf6 */

/* ---- band 5's leftovers: the drive calls, and the two leaves built on `__DOS` --------------------------------------
 * dos_gdrv, dos_chdir and dos_sdrv go through $fe3c28 as dos_free does (the host argument); isdrive calls two of them
 * by `bsr` from its own body, so the sites it parks are the glue's own. */
uint32_t aes_dos_gdrv(uint8_t *image, uint32_t return_site);                                        /* $fe3c02 */
uint32_t aes_dos_chdir(uint8_t *image, uint32_t return_site, uint32_t path);                        /* $fe3c0e */
uint32_t aes_dos_sdrv(uint8_t *image, uint32_t return_site, int16_t drive);                         /* $fe3c12 */
uint32_t aes_isdrive(uint8_t *image);                                                               /* $fe39a6 */
int16_t aes_pgmld(uint8_t *image, int16_t handle, uint32_t name, uint32_t basepage_out);            /* $fe39bc */
#endif

/* pgmld's two answers ($fe3a08 `moveq #1,d0` — dos_sfirst's own tail, branched into — and $fe3a00 `moveq #-1,d0`), and
 * what it adds to a program's three lengths for the block it keeps: the basepage. */
#define PGMLD_LOADED          1
#define PGMLD_FAILED          (-1)
#define PGMLD_BASEPAGE_BYTES  256        /* ($fe39dc move.l #256,d0)                                           */
#define PGMLD_NO_ENVIRONMENT  0          /* Pexec's environment: the caller's own ($fe39bc clr.l -(sp))        */
/* ...and its frame as the hand 68000 reads and builds it (`gemdosif.S`): its two pointer arguments over the handle's
 * word and the return address — the name read once two longwords are pushed — and the two calls' first longwords,
 * the function and the word under it. */
#define PGMLD_BASEPAGE_OUT    10         /* ($fe39d4 movea.l 10(sp),a0)                                        */
#define PGMLD_NAME_ONCE_TWO_ARE_PUSHED 14 /* ($fe39c2 move.l 14(sp),-(sp): 6(sp) at entry)                      */
#define PGMLD_PEXEC_LOAD_WORDS 0x004b0003 /* Pexec, mode 3 — load, do not start ($fe39c6 move.l #$004b0003,-(sp)) */
#define PGMLD_PEXEC_FRAME_BYTES 16       /* ($fe39ce adda.w #16,sp)                                            */
#define PGMLD_MSHRINK_WORDS   0x004a0000 /* Mshrink, its reserved word 0        ($fe39f2 move.l #$004a0000,-(sp)) */
#define PGMLD_MSHRINK_FRAME_BYTES 12     /* ($fe39fa adda.w #12,sp)                                            */

/* ---- THE VECTORS GEM TAKES (hand 68000, `$fe3c62..$fe3cbd`; `src/aes/gemdosif.S` ships on target) -------------------
 * `trap #2` ($88): install_trap2 saves what it held — the BIOS's VDI door — in SYSVAR_VDI_ENTRY and stores the AES's
 * handler; restore_trap2 puts the saved one back. THE CRITICAL-ERROR HANDLER (etv_critic, Setexc's $101): takeerr
 * saves the one it finds in AES_OLD_CRITIC and installs crit_err; giveerr installs the saved one; retake stores BOTH
 * of GEM's again (the trap #2 vector written, not saved) — what sh_tographic does when a program hands the screen
 * back. Each is called with the interrupts masked (spl7_save / spl_restore round the Line-F call).
 * The three that reach Setexc answer its D0 — the handler displaced — which no caller reads. */
#define SETEXC_ETV_CRITIC     0x101      /* Setexc's number for the critical-error handler ($fe3c96 move.w #257) */

#ifndef __ASSEMBLER__
void aes_restore_trap2(uint8_t *image);                                                             /* $fe3c62 */
void aes_install_trap2(uint8_t *image);                                                             /* $fe3c6e */
uint32_t aes_retake(uint8_t *image);                                                                /* $fe3c84 */
uint32_t aes_giveerr(uint8_t *image);                                                               /* $fe3ca4 */
uint32_t aes_takeerr(uint8_t *image);                                                               /* $fe3cac */
#endif

#endif /* TOS102US_AES_GEMDOSIF_H */
