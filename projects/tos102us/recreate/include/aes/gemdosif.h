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

#include <stdint.h>

#include "machine.h"
#include "aes/aes.h"

/* What the glue leaves in AES_DOS_AX for the errors its callers retry on: the MS-DOS numbers GEM was written against
 * ($fe3a3c move.w #18; $fe3a6a move.w #2), which sh_find tests with a third, 3, nothing here produces. */
#define DOS_AX_FILE_NOT_FOUND 2          /* dos_open's EFILNF                                                 */
#define DOS_AX_PATH_NOT_FOUND 3          /* ($feb02a cmpi.w #3): only a GEMDOS answer of that very word      */
#define DOS_AX_NO_MORE_FILES  18         /* dos_sfirst's EFILNF and ENMFIL                                     */

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

#endif /* TOS102US_AES_GEMDOSIF_H */
