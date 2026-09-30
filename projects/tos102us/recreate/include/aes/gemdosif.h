/* aes/gemdosif.h — the AES's own GEMDOS glue (`src/aes/gemdosif.c`): dos_alloc and dos_free, the two doors a score of
 * Line-F callers take to `Malloc` and `Mfree`.
 *
 * HAND 68000, entered by a Line-F call (or a `jsr`) over one stacked LONGWORD, each answering D0 as the trap left it.
 * dos_free goes through the glue's `__DOS` ($fe3c28), which PARKS its caller's return address in AES_DOS_RETURN and
 * returns through it: that address is the machine's, carried by no frame, so the host build is handed it
 * (`return_site`, `vdi.declare_alcyon`'s host argument — the VDI door's `gemdos_call` precedent).
 */
#ifndef TOS102US_AES_GEMDOSIF_H
#define TOS102US_AES_GEMDOSIF_H

#include <stdint.h>

uint32_t aes_dos_alloc(uint8_t *image, uint32_t bytes);                                             /* $fe3bba */
uint32_t aes_dos_free(uint8_t *image, uint32_t return_site, uint32_t block);                        /* $fe3c26 */

#endif /* TOS102US_AES_GEMDOSIF_H */
