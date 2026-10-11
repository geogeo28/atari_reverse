/* aes/loader.h — THE ACCESSORY LOADER (`src/aes/loader.c`): what gem_main runs once GEM is up and before the shell —
 * every `\*.ACC` of the boot drive loaded and made a process — and what it runs when GEM comes down.
 *
 *   $fe42e8 sndcli(name, count)  ONE accessory: its name copied to the shell's line, the file opened (to see that it is
 *                                there), a process descriptor allocated for every accessory but the first (`count` is
 *                                how many are started: the first runs in the spare static PD), the program loaded and
 *                                not started (pgmld), the file closed, its basepage kept — AES_FIRST_ACC_BASEPAGE for the
 *                                first, AES_ACC_BASEPAGES[] for the others — and its process made, to begin at gotopgm
 *                                (pstart). D0 1, or the word 0 where the file, the descriptor or the load failed
 *   $fe4394 ldaccs()             the allocated count cleared; a cartridge's accessories; then, where there is a drive
 *                                to read, a DTA allocated, the root of C: (where the drive map has one) searched
 *                                for `\*.ACC` and, of whichever drive the search is left on, each file found handed
 *                                sndcli — at most six passes, and six started
 *   $fe4476 free_accs()          every accessory's environment and basepage given back to GEMDOS, and each allocated
 *                                descriptor's block
 *   $fe44d4 cre_aproc()          an accessory's process descriptor ALLOCATED, as gem_main lays the three static ones
 *                                out: one block — the PD, its UDA, its CDA and five event blocks — the PD initialised
 *                                (pinit), its UDA's stack empty, the event blocks pushed on the free list. D0 1, or
 *                                the word 0 where Malloc refuses
 *
 * ALCYON C, each entered by a Line-F call over the frame its caller pushed. `cre_aproc` is the plan's "allocator",
 * named as the published GEM sources name it (a name from memory of them: the body is what was read).
 *
 * BEHAVIOURS OF THE ROM REPRODUCED AS THEY ARE (`test/test_aes_loader.py` pins each; (a) and (b) are the wave's
 * design's letters, each on the ROM's own run over a disk whose accessory is broken):
 *   (a) sndcli with cre_aproc refusing returns WITHOUT closing the file: its handle is never given back;
 *   (b) sndcli with the load failing after a descriptor was allocated leaves that block in AES_ACCESSORY_PDS[count]
 *       — the count not stepped, nothing freed: the next accessory's block is stored over it;
 *   and free_accs clears neither the count nor the first basepage's word: called twice it frees twice.
 */
#ifndef TOS102US_AES_LOADER_H
#define TOS102US_AES_LOADER_H

#include <stdint.h>

#include "aes/aes.h"

/* ---- where the loader keeps what it loaded -------------------------------------------------------------------------- */
#define AES_FIRST_ACC_BASEPAGE 0x9724    /* long: the FIRST accessory's basepage ($fe4358 move.l -6(a6),$9724)  */
#define AES_ACC_BASEPAGES     0x9bc4     /* longs[ACC_SLOTS]: the others', by AES_ACCESSORY_COUNT ($fe436c)     */
#define ACC_SLOTS             6          /* ...as AES_ACCESSORY_PDS has: six passes, six started ($fe445a)      */
/* gem_entry's 1 ($fd9f64), which the desk clears where a call on the current drive fails ($fe2a62): ldaccs loads
 * nothing from a disk without it. (What else reads it is band 6's to say.) */
#define AES_DISK_USABLE       0x8992     /* word                                ($fe43ba tst.w $8992)           */

/* ---- sndcli --------------------------------------------------------------------------------------------------------- */
#define SNDCLI_OPEN_MODE      0          /* dos_open's: read                    ($fe4300 clr.w (sp))            */
#define SNDCLI_STARTED        1          /* ($fe4386 moveq #1,d0)                                              */
#define SNDCLI_NOT_STARTED    0          /* ($fe438a, $fe4390 clr.w d0)                                        */

/* ---- ldaccs --------------------------------------------------------------------------------------------------------- */
#define LDACCS_DTA_BYTES      50         /* the search's DTA                    ($fe43ca move.l #50,(sp))       */
#define LDACCS_SEARCH_ATTRIBUTES 0       /* ordinary files                      ($fe43f8, $fe441c clr.w (sp))   */
/* The ROM's own strings, each twice — once for the look at C:, once for the search that is kept. */
#define AES_ACC_ROOT_OF_C     0xfef7be   /* bytes: "\\\0"                        ($fe43f0 move.l #$fef7be,(sp))  */
#define AES_ACC_PATTERN_OF_C  0xfef7c0   /* bytes: "\\*.ACC\0"                   ($fe43fa move.l #$fef7c0,-(sp)) */
#define AES_ACC_ROOT          0xfef7c7   /* bytes: "\\\0"                        ($fe4414 move.l #$fef7c7,(sp))  */
#define AES_ACC_PATTERN       0xfef7c9   /* bytes: "\\*.ACC\0"                   ($fe441e move.l #$fef7c9,-(sp)) */

/* ---- cre_aproc: the block of an allocated accessory's process ------------------------------------------------------- */
#define ACC_BLOCK_BYTES       2226       /* ($fe44dc move.l #2226,(sp))                                        */
#define ACC_UDA               PD_BYTES   /* its UDA, behind the PD              ($fe4500 lea 184(a3),a0)        */
#define ACC_CDA               2050       /* its CDA                             ($fe4508 lea 2050(a3),a0)       */
#define ACC_EVBS              2086       /* its event blocks                    ($fe4510 lea 2086(a3),a4)       */
#define ACC_EVB_COUNT         5          /* ($fe455c cmp.w #5,d7)                                              */
#define ACC_STACK_TOP         1862       /* from the UDA: its empty stack's top ($fe4528 add.l #1862,d0)        */
#define ACC_MADE              1          /* ($fe4562 moveq #1,d0)                                              */
#define ACC_REFUSED           0          /* ($fe4566 clr.w d0)                                                 */

#ifndef __ASSEMBLER__
int16_t aes_sndcli(uint8_t *image, uint32_t name, int16_t count);                                     /* $fe42e8 */
void aes_ldaccs(uint8_t *image);                                                                      /* $fe4394 */
void aes_free_accs(uint8_t *image);                                                                   /* $fe4476 */
int16_t aes_cre_aproc(uint8_t *image);                                                                /* $fe44d4 */
#endif

#endif /* TOS102US_AES_LOADER_H */
