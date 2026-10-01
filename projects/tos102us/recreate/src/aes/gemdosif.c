/* gemdosif.c — the AES's GEMDOS glue (`aes/gemdosif.h`): hand 68000 in the ROM ($fe3a1c..$fe3c40, `__DOS` at
 * $fe3c3e), ported over its own order. The trap is one of `gemdos/gemdos.h`'s shapes, taken two ways by the two
 * builds.
 */
#include <stdint.h>

#include "machine.h"
#include "m68k_idioms.h"
#include "aes/aes.h"
#include "aes/gemdosif.h"
#include "gemdos/fs.h"
#include "gemdos/gemdos.h"
#include "gemdos/process.h"

#define ODD_BIT               1u         /* `btst #0,d0; beq; addq.l #1,d0`: rounded up to even ($fe3bbe, $fe3bde) */
#define DOS_FAILED            1          /* AES_DOS_ERR := 1 on a Malloc of nothing   ($fe3bd4 move.w #1)          */
#define DOS_SFIRST_FOUND      1          /* dos_sfirst's `moveq #1` ($fe3a08)                                        */
#define DOS_MISSED            0          /* ...and `moveq #0` ($fe3a04): dos_sfirst's miss, dos_open's failure     */

/* $fe3bba — dos_alloc: Malloc of `bytes` rounded up to even (a longword sum: $ffffffff asks for 0), its block rounded
 * up the same way; a 0 (no memory) sets AES_DOS_ERR and is answered as it is — and a success does NOT clear it. */
uint32_t aes_dos_alloc(uint8_t *image, uint32_t bytes)
{
    uint32_t block = gemdos_trap_word_long(image, GEMDOS_MALLOC_FN, bytes + (bytes & ODD_BIT));

    if (!block) {
        wr16(image + AES_DOS_ERR, DOS_FAILED);
        return block;
    }
    return block + (block & ODD_BIT);
}

/* ---- `__DOS` ($fe3c3e): the return address it was reached with parked, the trap, and the verdict ---------------- */

/* Its tail ($fe3c46): the answer's word in AES_DOS_AX, its LONG's sign in AES_DOS_ERR. The sign is also what it leaves
 * in D1, which dos_open tests (`tst.w d1`) — the answer here. */
static int16_t dos_verdict(uint8_t *image, uint32_t answer)
{
    int16_t failed = (int32_t)answer < 0;

    wr16(image + AES_DOS_AX, (uint16_t)answer);
    wr16(image + AES_DOS_ERR, (uint16_t)failed);
    return failed;
}

/* $fe3c28, the way dos_free, dos_sdta and dos_close reach `__DOS`: their caller's return address (a ROM code address,
 * stored as the data it is) parked in AES_DOS_RETURN, and `__DOS`'s own inside the glue in AES_TRAP1_RETURN — both
 * before the trap. */
static void park_both_returns(uint8_t *image, uint32_t return_site)
{
    wr32(image + AES_DOS_RETURN, return_site);
    wr32(image + AES_TRAP1_RETURN, AES_DOS_TRAP_RETURN);
}

/* $fe3c26 — dos_free: Mfree through $fe3c28. */
uint32_t aes_dos_free(uint8_t *image, uint32_t return_site, uint32_t block)
{
    uint32_t answer;

    park_both_returns(image, return_site);
    answer = gemdos_trap_word_long(image, GEMDOS_MFREE_FN, block);
    (void)dos_verdict(image, answer);
    return answer;
}

/* $fe3c06 — dos_sdta: Fsetdta through $fe3c28. */
uint32_t aes_dos_sdta(uint8_t *image, uint32_t return_site, uint32_t dta)
{
    uint32_t answer;

    park_both_returns(image, return_site);
    answer = gemdos_trap_word_long(image, GEMDOS_FSETDTA_FN, dta);
    (void)dos_verdict(image, answer);
    return answer;
}

/* $fe3c0a — dos_close: Fclose through $fe3c28, over the handle WORD its caller pushed. */
uint32_t aes_dos_close(uint8_t *image, uint32_t return_site, int16_t handle)
{
    uint32_t answer;

    park_both_returns(image, return_site);
    answer = gemdos_trap_word_word(image, GEMDOS_FCLOSE_FN, (uint16_t)handle);
    (void)dos_verdict(image, answer);
    return answer;
}

/* ---- the calls that reach `__DOS` by their own `bsr` ------------------------------------------------------------ */

/* $fe3a1c — dos_sfirst: Fsfirst(name, attributes) into the DTA; 1 when the answer's WORD is 0. Not found — EFILNF, or
 * ENMFIL, compared as words — is AES_DOS_AX 18 for the caller's retry; any other error leaves the answer's own word. */
int16_t aes_dos_sfirst(uint8_t *image, uint32_t name, int16_t attributes)
{
    uint32_t answer;

    wr32(image + AES_TRAP1_RETURN, AES_DOS_SFIRST_TRAP_RETURN);
    answer = gemdos_trap_word_long_word(image, GEMDOS_FSFIRST_FN, name, (uint16_t)attributes);
    (void)dos_verdict(image, answer);
    if (!(uint16_t)answer)
        return DOS_SFIRST_FOUND;
    if ((uint16_t)answer == (uint16_t)GEMDOS_ENMFIL || (uint16_t)answer == (uint16_t)GEMDOS_EFILNF)
        wr16(image + AES_DOS_AX, DOS_AX_NO_MORE_FILES);
    return DOS_MISSED;
}

/* $fe3a52 — dos_open: Fopen(name, mode); EFILNF (a word compare) is AES_DOS_AX 2. The answer is the trap's whole D0 —
 * the handle — unless AES_DOS_ERR, then 0. */
uint32_t aes_dos_open(uint8_t *image, uint32_t name, int16_t mode)
{
    uint32_t answer;
    int16_t failed;

    wr32(image + AES_TRAP1_RETURN, AES_DOS_OPEN_TRAP_RETURN);
    answer = gemdos_trap_word_long_word(image, GEMDOS_FOPEN_FN, name, (uint16_t)mode);
    failed = dos_verdict(image, answer);
    if ((uint16_t)answer == (uint16_t)GEMDOS_EFILNF)
        wr16(image + AES_DOS_AX, DOS_AX_FILE_NOT_FOUND);
    return failed ? DOS_MISSED : answer;
}

/* $fe3a78 — dos_read: Fread(handle, count, buffer), the count a WORD zero-extended to the call's longword
 * ($fe3a82 moveq #0; move.w). */
uint32_t aes_dos_read(uint8_t *image, int16_t handle, int16_t count, uint32_t buffer)
{
    uint32_t answer;

    wr32(image + AES_TRAP1_RETURN, AES_DOS_READ_TRAP_RETURN);
    answer = gemdos_trap_word_word_long_long(image, GEMDOS_FREAD_FN, (uint16_t)handle, (uint16_t)count, buffer);
    (void)dos_verdict(image, answer);
    return answer;
}

/* $fe3a9a — dos_lseek: Fseek(offset, handle, mode) — its caller pushes them handle, mode, offset, and the glue moves
 * the handle and the mode as ONE longword under the offset ($fe3a9a move.l 4(sp),-(sp)). */
uint32_t aes_dos_lseek(uint8_t *image, int16_t handle, int16_t mode, uint32_t offset)
{
    uint32_t answer;

    wr32(image + AES_TRAP1_RETURN, AES_DOS_LSEEK_TRAP_RETURN);
    answer = gemdos_trap_word_long_long(image, GEMDOS_FSEEK_FN, offset, words_long(handle, mode));
    (void)dos_verdict(image, answer);
    return answer;
}
