/* dosglue.h — THE AES's GEMDOS GLUE's OWN STEPS, ONE HOME (band 6 slice F1, N13): `__DOS`'s verdict ($fe3c46), the two
 * returns its entries park, and the call through `$fe3c28` — spelt once for the two files whose entries are the glue's:
 * `src/aes/gemdosif.c` (band 5's: dos_free, dos_sdta, dos_close, the bell's Cconout, ...) and `src/desk/deskleaf.c`
 * (unit O's thirteen, the desk's). Each was a `static` of both until unit O flipped.
 */
#ifndef TOS102US_AES_DOSGLUE_H
#define TOS102US_AES_DOSGLUE_H

#include <stdint.h>

#include "addrs.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "gemdos/gemdos.h"

/* `__DOS`'s tail ($fe3c46): the answer's word in AES_DOS_AX, its LONG's sign in AES_DOS_ERR — which is also what it
 * leaves in D1, which dos_open tests (`tst.w d1`) and dos_mkdir answers from: the answer here. */
static inline int16_t dos_verdict(uint8_t *image, uint32_t answer)
{
    int16_t failed = (int32_t)answer < 0;

    wr16(image + AES_DOS_AX, (uint16_t)answer);
    wr16(image + AES_DOS_ERR, (uint16_t)failed);
    return failed;
}

/* ...and what every entry that answers the trap's whole D0 answers once the trap is back: the verdict taken, that D0. */
static inline uint32_t dos_answered(uint8_t *image, uint32_t answer)
{
    (void)dos_verdict(image, answer);
    return answer;
}

/* An entry that first pops ITS CALLER's return address into AES_DOS_RETURN — a ROM code address, stored as the data it
 * is ($fe3c28, $fe3ba0) — and parks `__DOS`'s own inside the glue, `glue_site`, in AES_TRAP1_RETURN: both before the trap. */
static inline void park_both_returns(uint8_t *image, uint32_t return_site, uint32_t glue_site)
{
    wr32(image + AES_DOS_RETURN, return_site);
    wr32(image + AES_TRAP1_RETURN, glue_site);
}

/* A call through $fe3c28 over the LONGWORD its caller pushed: both return addresses parked, the trap, the verdict — and
 * the trap's whole D0 the answer. */
static inline uint32_t dos_through_with_a_long(uint8_t *image, uint32_t return_site, uint16_t function, uint32_t argument)
{
    park_both_returns(image, return_site, AES_DOS_TRAP_RETURN);
    return dos_answered(image, gemdos_trap_word_long(image, function, argument));
}

#endif /* TOS102US_AES_DOSGLUE_H */
