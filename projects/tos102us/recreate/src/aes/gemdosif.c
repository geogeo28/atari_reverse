/* gemdosif.c — the AES's GEMDOS glue (`aes/gemdosif.h`): hand 68000 in the ROM ($fe3a1c..$fe3c40, `__DOS` at
 * $fe3c3e), ported over its own order. The trap is one of `gemdos/gemdos.h`'s shapes, taken two ways by the two
 * builds.
 */
#include <stdint.h>

#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "transcribed.h"
#include "aes/aes.h"
#include "aes/gemdosif.h"
#include "bios/bcon.h"
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

/* $fe3c28, the way dos_free, dos_sdta, dos_close and the bell's Cconout reach `__DOS`: their caller's return address (a
 * ROM code address, stored as the data it is) parked in AES_DOS_RETURN, and `__DOS`'s own inside the glue in AES_TRAP1_RETURN — both
 * before the trap. */
static void park_both_returns(uint8_t *image, uint32_t return_site)
{
    wr32(image + AES_DOS_RETURN, return_site);
    wr32(image + AES_TRAP1_RETURN, AES_DOS_TRAP_RETURN);
}

/* ...and what every such call answers once the trap is back: the verdict taken, the trap's whole D0. */
static inline uint32_t dos_answered(uint8_t *image, uint32_t answer)
{
    (void)dos_verdict(image, answer);
    return answer;
}

/* A call through $fe3c28 over the LONGWORD its caller pushed: both return addresses parked, the trap, the verdict — and
 * the trap's whole D0 the answer. */
static inline uint32_t dos_through_with_a_long(uint8_t *image, uint32_t return_site, uint16_t function, uint32_t argument)
{
    park_both_returns(image, return_site);
    return dos_answered(image, gemdos_trap_word_long(image, function, argument));
}

/* ...and over a WORD. */
static inline uint32_t dos_through_with_a_word(uint8_t *image, uint32_t return_site, uint16_t function, uint16_t argument)
{
    park_both_returns(image, return_site);
    return dos_answered(image, gemdos_trap_word_word(image, function, argument));
}

/* $fe3c26 — dos_free: Mfree through $fe3c28. */
uint32_t aes_dos_free(uint8_t *image, uint32_t return_site, uint32_t block)
{
    return dos_through_with_a_long(image, return_site, GEMDOS_MFREE_FN, block);
}

/* $fe3c06 — dos_sdta: Fsetdta through $fe3c28. */
uint32_t aes_dos_sdta(uint8_t *image, uint32_t return_site, uint32_t dta)
{
    return dos_through_with_a_long(image, return_site, GEMDOS_FSETDTA_FN, dta);
}

/* $fe3c0a — dos_close: Fclose through $fe3c28, over the handle WORD its caller pushed. */
uint32_t aes_dos_close(uint8_t *image, uint32_t return_site, int16_t handle)
{
    return dos_through_with_a_word(image, return_site, GEMDOS_FCLOSE_FN, (uint16_t)handle);
}

/* $fe3bf6 — Cconout through $fe3c28, over the character WORD its caller pushed: fs_active's bell. */
uint32_t aes_dos_cconout(uint8_t *image, uint32_t return_site, int16_t character)
{
    return dos_through_with_a_word(image, return_site, GEMDOS_CCONOUT_FN, (uint16_t)character);
}

/* ...and over NOTHING: the function word alone (Dgetdrv's). */
static inline uint32_t dos_through_with_nothing(uint8_t *image, uint32_t return_site, uint16_t function)
{
    park_both_returns(image, return_site);
    return dos_answered(image, gemdos_trap_word(image, function));
}

/* $fe3c02 — dos_gdrv: Dgetdrv through $fe3c28 — the current drive. */
uint32_t aes_dos_gdrv(uint8_t *image, uint32_t return_site)
{
    return dos_through_with_nothing(image, return_site, GEMDOS_DGETDRV_FN);
}

/* $fe3c0e — dos_chdir: Dsetpath through $fe3c28, over the path's address its caller pushed. */
uint32_t aes_dos_chdir(uint8_t *image, uint32_t return_site, uint32_t path)
{
    return dos_through_with_a_long(image, return_site, GEMDOS_DSETPATH_FN, path);
}

/* $fe3c12 — dos_sdrv: Dsetdrv through $fe3c28, over the drive WORD its caller pushed — the drive map. */
uint32_t aes_dos_sdrv(uint8_t *image, uint32_t return_site, int16_t drive)
{
    return dos_through_with_a_word(image, return_site, GEMDOS_DSETDRV_FN, (uint16_t)drive);
}

/* $fe39a6 — isdrive: the drive map — Dsetdrv of the drive Dgetdrv answers, its low WORD pushed ($fe39aa move.w d0).
 * Both calls are `bsr`s of the entries above from its own body, so the two sites parked in AES_DOS_RETURN are the
 * glue's own (the second is what the snapshot holds there). */
uint32_t aes_isdrive(uint8_t *image)
{
    uint32_t drive = aes_dos_gdrv(image, AES_ISDRIVE_GDRV_RETURN);

    return aes_dos_sdrv(image, AES_ISDRIVE_SDRV_RETURN, (int16_t)drive);
}

/* ---- pgmld: a program loaded and its block cut to size ------------------------------------------------------------ */
#define PGMLD_FRAME_BYTES     16         /* Pexec's: the function, the mode, the name, the tail, the environment  */
_Static_assert(PGMLD_FRAME_BYTES == HOST_SLOT_AES_PGMLD_WORDS_BYTES, "pgmld's Pexec frame and its host slot");

/* The command tail pgmld hands Pexec: EMPTY — a zero word. In the ROM it lies in the text, two bytes before the
 * routine (`pea $fe39b4(pc)`); the host hands that address (the ROM's own zero word), a rebuilt ROM its own. */
#ifdef RECREATE_HOST_DIFFERENTIAL
static inline uint32_t empty_command_tail(void)
{
    return AES_PGMLD_EMPTY_TAIL;
}

/* Pexec(3, name, tail, 0) — the one frame of the glue wider than the GEMDOS words' slot, so it claims its own and
 * takes the host's trap over that (`gemdos_host_trap_over`). */
static uint32_t pexec_load(uint8_t *image, uint32_t name, uint32_t tail)
{
    uint8_t frame[PGMLD_FRAME_BYTES], words_local[PGMLD_FRAME_BYTES];
    uint32_t words = host_slot_claim(AES_PGMLD_WORDS, words_local);
    uint32_t answer;

    wr16(frame, GEMDOS_PEXEC_FN);
    wr16(frame + GEMDOS_ARGUMENT_WORD, PEXEC_LOAD);
    wr32(frame + 2 * GEMDOS_ARGUMENT_WORD, name);
    wr32(frame + 2 * GEMDOS_ARGUMENT_WORD + GEMDOS_FRAME_LONG, tail);
    wr32(frame + 2 * GEMDOS_ARGUMENT_WORD + 2 * GEMDOS_FRAME_LONG, PGMLD_NO_ENVIRONMENT);
    answer = gemdos_host_trap_over(image, words, frame, sizeof frame);
    host_slot_release(AES_PGMLD_WORDS);
    return answer;
}
#else
static const uint16_t pgmld_empty_tail = 0;

static inline uint32_t empty_command_tail(void)
{
    return (uint32_t)(uintptr_t)&pgmld_empty_tail;
}

/* The ROM's own four pushes ($fe39bc..$fe39c6: the function and the mode ONE longword), the trap, the frame dropped.
 * Each operand is PINNED to a register the trap restores (`gemdos/gemdos.h`'s shapes say why) — and never left to a
 * stack slot, whose displacement the pushes before it would have moved. */
static inline uint32_t pexec_load(uint8_t *image, uint32_t name, uint32_t tail)
{
    register uint32_t answer __asm__("d0") = (uint32_t)GEMDOS_PEXEC_FN << 16 | PEXEC_LOAD;
    register uint32_t program __asm__("a0") = name;
    register uint32_t command_tail __asm__("a1") = tail;

    (void)image;
    __asm__ volatile ("clr.l -(%%sp)\n\t"
                      "move.l %2,-(%%sp)\n\t"
                      "move.l %1,-(%%sp)\n\t"
                      "move.l %0,-(%%sp)\n\t"
                      "trap #1\n\t"
                      "lea 16(%%sp),%%sp"
                      : "+d"(answer)
                      : "a"(program), "a"(command_tail)
                      : "memory", "cc");
    return answer;
}
#endif

/* $fe39bc — pgmld: the program `name` loaded and not started (Pexec mode 3, an empty tail, the caller's environment);
 * its basepage stored through `basepage_out`; and its block shrunk to what it uses — the basepage and its text, data
 * and BSS (Mshrink). 1, or -1 where either call failed (the LONG's sign, by `__DOS`'s verdict). `handle` is not read:
 * the file its caller opened to see that it is there. Each call parks its own site inside the glue.
 *
 * THE TARGET SHIPS `gemdosif.S` — the ROM's own instructions; this C is what Tier 1 proves. MEASURED (Tier 3): 1.02
 * on the two arms that reach Mshrink, 1.11 — over the bar — on the arm where Pexec fails (796 cycles for the ROM's
 * 716: three registers saved round a trap for the half that arm never runs). Two re-spellings were measured and
 * neither helps: the second half out of line (1.11 / 1.13 / 1.13) and `__DOS`'s three words off one pointer (GCC
 * folds it back: the same code). The sites this twin parks are the ROM's, as every C glue's are (data: a C function
 * has no return site of that shape); the `.S` parks its own. */
TRANSCRIBED_CORE
int16_t aes_pgmld(uint8_t *image, int16_t handle, uint32_t name, uint32_t basepage_out)
{
    uint32_t basepage, kept;

    (void)handle;
    wr32(image + AES_TRAP1_RETURN, AES_PGMLD_PEXEC_RETURN);
    basepage = pexec_load(image, name, empty_command_tail());
    if (dos_verdict(image, basepage))
        return PGMLD_FAILED;
    set_bus_long(image, basepage_out, basepage);
    kept = PGMLD_BASEPAGE_BYTES + bus_long(image, basepage + BASEPAGE_TLEN) + bus_long(image, basepage + BASEPAGE_DLEN)
           + bus_long(image, basepage + BASEPAGE_BLEN);
    wr32(image + AES_TRAP1_RETURN, AES_PGMLD_MSHRINK_RETURN);
    return dos_verdict(image, gemdos_trap_word_word_long_long(image, GEMDOS_MSHRINK_FN, 0, basepage, kept))
               ? PGMLD_FAILED : PGMLD_LOADED;
}

/* ---- the calls that reach `__DOS` by their own `bsr` ------------------------------------------------------------ */

/* The tail dos_sfirst and dos_snext share ($fe3a2c): 1 when the search's answer's WORD is 0. Not found — EFILNF, or
 * ENMFIL, compared as words — is AES_DOS_AX 18 for the caller's retry; any other error leaves the answer's own word. */
static inline int16_t search_found(uint8_t *image, uint32_t answer)
{
    (void)dos_verdict(image, answer);
    if (!(uint16_t)answer)
        return DOS_SFIRST_FOUND;
    if ((uint16_t)answer == (uint16_t)GEMDOS_ENMFIL || (uint16_t)answer == (uint16_t)GEMDOS_EFILNF)
        wr16(image + AES_DOS_AX, DOS_AX_NO_MORE_FILES);
    return DOS_MISSED;
}

/* $fe3a1c — dos_sfirst: Fsfirst(name, attributes) into the DTA, and whether it found one. */
int16_t aes_dos_sfirst(uint8_t *image, uint32_t name, int16_t attributes)
{
    wr32(image + AES_TRAP1_RETURN, AES_DOS_SFIRST_TRAP_RETURN);
    return search_found(image, gemdos_trap_word_long_word(image, GEMDOS_FSFIRST_FN, name, (uint16_t)attributes));
}

/* $fe3a46 — dos_snext: Fsnext over the DTA the search left, and whether it found another. */
int16_t aes_dos_snext(uint8_t *image)
{
    wr32(image + AES_TRAP1_RETURN, AES_DOS_SNEXT_TRAP_RETURN);
    return search_found(image, gemdos_trap_word(image, GEMDOS_FSNEXT_FN));
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

/* ---- THE VECTORS GEM TAKES ($fe3c62..$fe3cbd) ------------------------------------------------------------------------
 * THE TARGET SHIPS `gemdosif.S` — the ROM's own instructions: each twin below measures over Tier 3's bar (the image
 * pointer's floor on a routine of two to six instructions). The C is what Tier 1 proves. */

/* The two handlers GEM installs, as a vector holds them: off target the ROM's own addresses (Tier 1 stays exact); on
 * target a rebuilt ROM owes its own — the trap door and crit_err are band 5's wave 3, so until they land the target
 * stores the ROM's too (`test_aes_rom_data.py`: rows $fe3c78, $fe3c84, $fe3c8e, $fe3cb6). */
static inline uint32_t gem_trap2_handler(void)
{
    return GEM_TRAP2;
}

static inline uint32_t critical_error_handler(void)
{
    return AES_ROM_CRIT_ERR;
}

/* The tail the three share ($fe3c94): Setexc($101, handler) through the BIOS — the handler displaced. */
static inline uint32_t setexc_critic(uint8_t *image, uint32_t handler)
{
    return bios_setexc_by_trap(image, SETEXC_ETV_CRITIC, handler);
}

/* $fe3c62 — restore_trap2: vector $88 given back what install_trap2 found there. */
TRANSCRIBED_CORE
void aes_restore_trap2(uint8_t *image)
{
    wr32(image + VECTOR_TRAP_GEM, be32(image + SYSVAR_VDI_ENTRY));
}

/* $fe3c6e — install_trap2: the vector's holder saved FIRST — it is where the handler's VDI arm jumps — then the
 * handler stored. */
TRANSCRIBED_CORE
void aes_install_trap2(uint8_t *image)
{
    wr32(image + SYSVAR_VDI_ENTRY, be32(image + VECTOR_TRAP_GEM));
    wr32(image + VECTOR_TRAP_GEM, gem_trap2_handler());
}

/* $fe3c84 — retake: both of GEM's again, the trap #2 vector first; nothing is saved (what a program left in either
 * is lost). */
TRANSCRIBED_CORE
uint32_t aes_retake(uint8_t *image)
{
    wr32(image + VECTOR_TRAP_GEM, gem_trap2_handler());
    return setexc_critic(image, critical_error_handler());
}

/* $fe3ca4 — giveerr: the critical-error handler takeerr saved, installed again. */
TRANSCRIBED_CORE
uint32_t aes_giveerr(uint8_t *image)
{
    return setexc_critic(image, be32(image + AES_OLD_CRITIC));
}

/* $fe3cac — takeerr: the handler in place asked for and saved, then crit_err installed. */
TRANSCRIBED_CORE
uint32_t aes_takeerr(uint8_t *image)
{
    wr32(image + AES_OLD_CRITIC, setexc_critic(image, SETEXC_INQUIRE));
    return setexc_critic(image, critical_error_handler());
}
