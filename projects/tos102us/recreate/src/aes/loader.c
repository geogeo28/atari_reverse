/* loader.c — THE ACCESSORY LOADER (`aes/loader.h`): sndcli, ldaccs, free_accs and cre_aproc. Alcyon C in the ROM
 * ($fe42e8..$fe4569), ported over its own order: every callee is its C core, every GEMDOS call the glue's door
 * (`aes/gemdosif.h`) with the return site the ROM's own Line-F call parks (a code address stored as the data it is).
 */
#include <stdint.h>

#include "addrs.h"
#include "host_slot.h"
#include "machine.h"
#include "m68k_idioms.h"
#include "recreate.h"
#include "staged_call.h"
#include "aes/aes.h"
#include "aes/cart.h"
#include "aes/deskleaf.h"
#include "aes/gemdosif.h"
#include "aes/geminit.h"
#include "aes/loader.h"
#include "aes/pdpipe.h"
#include "aes/strings.h"
#include "gemdos/fs.h"

_Static_assert(ACC_UDA == PD_BYTES, "an allocated accessory's UDA lies behind its PD");
_Static_assert(ACC_CDA + CDA_BYTES == ACC_EVBS, "its event blocks lie behind its CDA");
_Static_assert(ACC_EVBS + ACC_EVB_COUNT * EVB_BYTES == ACC_BLOCK_BYTES, "the block ends with its last event block");
_Static_assert(HOST_SLOT_AES_SNDCLI_BASEPAGE_BYTES == sizeof(uint32_t), "sndcli's local: the basepage pgmld answers");

/* $fe44d4 — cre_aproc: an accessory's process descriptor allocated — one block, kept in AES_ACCESSORY_PDS at the
 * count getpd will read it back by (pstart's, later: the count is not stepped here). The PD is initialised with its
 * CDA; its UDA is the block's own, the stack pointer it saves the top of the empty stack; and each of its five event
 * blocks is pushed on the free list, the list's head read and stored back in memory each time. */
int16_t aes_cre_aproc(uint8_t *image)
{
    uint32_t block = aes_dos_alloc(image, ACC_BLOCK_BYTES);
    uint32_t uda, events;
    int16_t index;

    if (!block)
        return ACC_REFUSED;
    wr32(image + table_entry(AES_ACCESSORY_PDS, global_word(image, AES_ACCESSORY_COUNT), sizeof(uint32_t)), block);
    uda = block + ACC_UDA;
    events = block + ACC_EVBS;
    aes_pinit(image, block, block + ACC_CDA);
    set_bus_long(image, block + PD_UDA, uda);
    set_bus_long(image, uda + UDA_SUPER_SP, uda + ACC_STACK_TOP);
    for (index = 0; index < ACC_EVB_COUNT; index++) {
        uint32_t event = table_entry(events, index, EVB_BYTES);

        set_bus_long(image, event + EVB_NEXT, be32(image + AES_EUL));
        wr32(image + AES_EUL, event);
    }
    return ACC_MADE;
}

/* Where an accessory's process begins: gotopgm, which enters the program its PD was loaded as — the ROM's own off
 * target, a code address used as a value (`test/test_aes_rom_data.py`, CODE: $fe437c), the build's on target. */
#ifndef RECREATE_HOST_DIFFERENTIAL
void aes_rom_gotopgm(void);                                                                          /* $fe38b0 */
#endif

static inline uint32_t an_accessory_s_entry(void)
{
    return ALCYON_ROUTINE(AES_ROM_GOTOPGM, aes_rom_gotopgm);
}

/* $fe42e8 — sndcli: one accessory loaded and made a process (`aes/loader.h`). The file is opened by the shell's
 * buffer pointer — the line the name was just copied to — and its handle is all the open is for: pgmld loads by name.
 * THE ROM'S TWO LEAKS, as they are: a refused descriptor returns before the close, and a failed load leaves the
 * descriptor's block allocated and stored. `count` chooses the descriptor and where the basepage is kept: 0 is the
 * first accessory, which runs in the spare static PD. pgmld is handed the ADDRESS of sndcli's own local ($fe4332
 * `move.l a6,(sp); subq.l #6,(sp)`) and stores the basepage through it only where the load succeeds — the one arm
 * that reads it. */
int16_t aes_sndcli(uint8_t *image, uint32_t name, int16_t count)
{
    uint32_t basepage, basepage_at;
    int16_t handle, verdict;

    (void)aes_strcpy(image, name, AES_SHELL_LINE);
    handle = (int16_t)aes_dos_open(image, be32(image + AES_SHELL_BUFFER), SNDCLI_OPEN_MODE);
    if (aes_dos_failed(image))
        return SNDCLI_NOT_STARTED;
    if (count && !aes_cre_aproc(image))
        return SNDCLI_NOT_STARTED;
    basepage_at = host_slot_claim(AES_SNDCLI_BASEPAGE, &basepage);
    verdict = aes_pgmld(image, handle, AES_SHELL_LINE, basepage_at);
    host_slot_load_long(image, basepage_at, &basepage);
    host_slot_release(AES_SNDCLI_BASEPAGE);
    (void)aes_dos_close(image, AES_SNDCLI_CLOSE_RETURN, handle);
    if (verdict == PGMLD_FAILED)
        return SNDCLI_NOT_STARTED;
    if (!count)
        wr32(image + AES_FIRST_ACC_BASEPAGE, basepage);
    else
        wr32(image + table_entry(AES_ACC_BASEPAGES, global_word(image, AES_ACCESSORY_COUNT), sizeof(uint32_t)), basepage);
    (void)aes_pstart(image, an_accessory_s_entry(), name, basepage);
    return SNDCLI_STARTED;
}

/* The accessories of an application cartridge ($fed554, which answers how many it started). NOT RECONSTRUCTED — no
 * machine here has a cartridge (ruling W3-R6: the oracle serves none), and the routine is the cartridge slice's —
 * so the arm halts by name on both builds rather than load from a disk as if the port were empty. */
static int16_t cartridge_accessories_started(void)
{
    recreate_not_reconstructed("ldaccs: an application cartridge answers — its accessories' loader ($fed554) is not "
                               "reconstructed");
    return 0;
}

/* $fe4394 — ldaccs: every accessory loaded (`aes/loader.h`). The drive map is asked twice (isdrive: once for "is
 * there a drive", its WORD; once for C:); the first search, of C:'s root, is only a look — found, the search stays on
 * C:; not found, the drive it began on is set again — and the second, of whichever drive that leaves, is the one
 * whose DTA names the files. The DTA is a block of its own, freed at the end; the names are read where a search
 * leaves them in it. */
void aes_ldaccs(uint8_t *image)
{
    uint32_t dta;
    int16_t started = 0, drive, found, pass;

    wr16(image + AES_ACCESSORY_COUNT, 0);
    if (aes_cart_init(image))
        started = (int16_t)(started + cartridge_accessories_started());
    if (!(uint16_t)aes_isdrive(image) || !be16(image + AES_DISK_USABLE))
        return;
    drive = (int16_t)aes_dos_gdrv(image, AES_LDACCS_GDRV_RETURN);
    dta = aes_dos_alloc(image, LDACCS_DTA_BYTES);
    (void)aes_dos_sdta(image, AES_LDACCS_SDTA_RETURN, dta);
    if (aes_isdrive(image) & DRIVE_C_BIT)
        (void)aes_dos_sdrv(image, AES_LDACCS_SDRV_C_RETURN, DRIVE_C);
    (void)aes_dos_chdir(image, AES_LDACCS_CHDIR_OF_C_RETURN, AES_ACC_ROOT_OF_C);
    if (!aes_dos_sfirst(image, AES_ACC_PATTERN_OF_C, LDACCS_SEARCH_ATTRIBUTES))
        (void)aes_dos_sdrv(image, AES_LDACCS_SDRV_BACK_RETURN, drive);
    (void)aes_dos_chdir(image, AES_LDACCS_CHDIR_RETURN, AES_ACC_ROOT);
    found = aes_dos_sfirst(image, AES_ACC_PATTERN, LDACCS_SEARCH_ATTRIBUTES);
    for (pass = 0; pass < ACC_SLOTS && started < ACC_SLOTS && found; pass++) {
        if (aes_sndcli(image, dta + DTA_NAME, started))
            started++;
        found = aes_dos_snext(image);
    }
    (void)aes_dos_free(image, AES_LDACCS_FREE_RETURN, dta);
}

/* $fe4476 — free_accs: the first accessory's environment and basepage, where there is one; then, for each allocated
 * accessory, its environment, its basepage and its descriptor's block. Nothing is cleared: neither the count (read
 * again every pass, a signed compare) nor a pointer. */
void aes_free_accs(uint8_t *image)
{
    int16_t index;

    if (be32(image + AES_FIRST_ACC_BASEPAGE)) {
        (void)aes_dos_free(image, AES_FREE_ACCS_FIRST_ENV_RETURN, bus_long(image, be32(image + AES_FIRST_ACC_BASEPAGE) + BASEPAGE_ENV));
        (void)aes_dos_free(image, AES_FREE_ACCS_FIRST_RETURN, be32(image + AES_FIRST_ACC_BASEPAGE));
    }
    for (index = 0; index < global_word(image, AES_ACCESSORY_COUNT); index++) {
        uint32_t basepage = be32(image + table_entry(AES_ACC_BASEPAGES, index, sizeof(uint32_t)));

        (void)aes_dos_free(image, AES_FREE_ACCS_ENV_RETURN, bus_long(image, basepage + BASEPAGE_ENV));
        (void)aes_dos_free(image, AES_FREE_ACCS_BASEPAGE_RETURN, basepage);
        (void)aes_dos_free(image, AES_FREE_ACCS_PD_RETURN, be32(image + table_entry(AES_ACCESSORY_PDS, index, sizeof(uint32_t))));
    }
}
