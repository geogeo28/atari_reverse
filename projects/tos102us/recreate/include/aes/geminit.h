/* aes/geminit.h — GEMINIT (`src/aes/geminit.c`): gem_main, which brings GEM up, runs the shell and takes GEM down;
 * the reader of the desktop's saved screen line; and the three LEAVES gem_main and the accessory loader call before a
 * process runs.
 *
 *   $fd9ffc ini_dlongs()      the AES's five long pointers into its own BSS — the shell's command line and tail, the
 *                             working path, the AES's own global[], the screen's lock — each set to where THEGLO or
 *                             the BSS holds what it names
 *   $fda03e all_run()         every other process given a turn (one bare yield), then the screen's lock taken and
 *                             given back: whoever holds it has let go before the caller goes on
 *   $fda062 gem_main()        `jsr`ed by gem_entry alone (`src/aes/gemstart.S`), on the shell's own stack, THEGLO
 *                             cleared under it. The long pointers; every interrupt masked; `trap #2` taken; the event
 *                             blocks' free list, the scheduler's lists and the fork queue emptied; the three static
 *                             processes laid out — each PD its CDA and its UDA, UDA1 and UDA2 their stack tops — and
 *                             PD0 made the running one; the interrupts let in; the screen manager's process made; the
 *                             INF read; the AES's own resource and its two mouse forms; the accessories; the default
 *                             drive; the workstation opened; three icons made the device's; the critical-error
 *                             handler taken; the screen GEM's; the tick taken (the routine gem_entry stored); the
 *                             double-click rate; the resource fixed up once; the windows, the file selector, the
 *                             launch band sized to the screen; one dispatch, every process a turn — THE SHELL — and
 *                             then all of it given back in turn
 *   $fda3d6 pinit(pd, cda)    a PD made ready to be named and written to: its CDA, its pipe's address and index, its
 *                             name blank
 *   $fda408 gem_read_inf()    (a name of ours: the routine is unnamed in what was read) the shell's GEM buffer
 *                             REPLACED by `\DESKTOP.INF` — of the current drive, then of C: where the drive map has
 *                             one — or by the ROM's own default where no file is read; and, ONLY WHERE A FILE WAS
 *                             READ, its `#E` line acted on: a resolution change pending -> the line's second pair
 *                             rewritten with the device in use; none -> the pair's low two bits + 1 asked for as the
 *                             device (app_reschange), and the scan ends. D0 the word 0 where no file was read, or
 *                             the device asked is the one in use; else 1 — which gem_main does not read
 *
 * ALCYON C, each entered by a Line-F call over the frame its caller pushed — but gem_main, which gem_entry `jsr`s.
 *
 * BEHAVIOURS OF THE ROM REPRODUCED AS THEY ARE (`test/test_aes_geminit_inf.py` pins each of the reader's; the letters
 * are the wave's design's):
 *   (b) the reader ends the text with a NUL at the buffer + THE COUNT Fread ANSWERED, a SIGNED WORD: a file of 2,048
 *       bytes or more puts it ONE BYTE PAST THE BLOCK it allocated, and a read that fails (a negative count) puts it
 *       BELOW the block — the reader tests the open's verdict and never the read's, and then scans what the shell's
 *       buffer held;
 *   (c) where the file is not on the current drive and the map has a C:, the drive is SET to C: and put back only
 *       after a read: a C: without the file leaves C: the current drive;
 *   (f) gem_main's `clr.w d0 / ext.l d0` pairs and its `#$c808 - #$c804` are constants spelt as arithmetic: 0 and
 *       EVB_LINK;
 *   and three of the scan's own: the cursor is NOT moved past a `#E` line's pair (scan_2's answer is dropped), so
 *   with a change pending the scan goes on from the rewritten pair and EVERY later `#E` line is rewritten too; the
 *   five bytes skipped from a `#E` are skipped unread, so one at the text's end steps over the NUL into what the
 *   block held before; and a `#` is followed by a look at the next byte AS ITSELF (`##E` is a screen line).
 *   THE USABLE-DISK WORD the reader tests is not the 1 gem_entry stores: `aes/gemstart.h`, GEM_DISK_USABLE.
 */
#ifndef TOS102US_AES_GEMINIT_H
#define TOS102US_AES_GEMINIT_H

#include <stdint.h>

#include "aes/aes.h"

/* ---- what ini_dlongs points the AES's long pointers at: two places in THEGLO no other routine names by address ---- */
/* The shell's command line (`AES_SHELL_BUFFER` names it from then on): THEGLO + 8022. */
#define AES_SHELL_LINE        0xbbae     /* bytes[AES_SHELL_LINE_BYTES]         ($fda00a lea 8022(a5),a0)      */
/* The AES's own application global[] (`AES_RS_SYSTEM_GLOBAL` names it): THEGLO + 7992. */
#define AES_SYSTEM_GLOBAL     0xbb90     /* words[AES_GLOBAL_WORDS]             ($fda028 lea 7992(a5),a0)      */

/* ---- all_run -------------------------------------------------------------------------------------------------------- */
/* How many times all_run yields: the ROM's loop counts to one ($fda04e cmpi.w #1,-2(a6) / blt). */
#define ALL_RUN_YIELDS        1

/* ---- gem_main ------------------------------------------------------------------------------------------------------- */
/* The AES resource's parts gem_main asks rs_gaddr for: the two mouse forms' data (the arrow, the hourglass), the three
 * icons it makes the device's, and the launch band's tree. */
#define GEM_ARROW_IMAGE       3          /* R_BIPDATA: AES_AD_ARMICE            ($fda206 move.l #$000e0003)      */
#define GEM_HOURGLASS_IMAGE   5          /* R_BIPDATA: AES_AD_HGMICE            ($fda228 move.l #$000e0005)      */
#define GEM_ICONS             3          /* R_BITBLK 0..2, each through gsx_trans ($fda2b4 cmp.w #3,d7)          */
#define GEM_BAND_TREE         2          /* R_TREE: AES_AD_STDESK               ($fda30a move.w #2,-(sp))        */
/* The band's three first objects are as wide as the screen; its root as high, the two under it a character's height
 * and a little. */
#define GEM_BAND_WIDE_OBJECTS 3          /* ($fda348 cmp.w #3,d7)                                               */
#define GEM_BAND_BAR          1          /* its height gl_hchar + 2             ($fda36c addq.w #2 -> tree + 46) */
#define GEM_BAND_BAR_EXTRA    2
#define GEM_BAND_TEXT         2          /* its height gl_hchar + 3             ($fda380 addq.w #3 -> tree + 70) */
#define GEM_BAND_TEXT_EXTRA   3
#define GEM_ROM_RAM_NO_SIZE   0          /* rom_ram's third argument, read for no part gem_main asks ($fda1f2)   */
#define GEM_DCLICK_RATE       3          /* ev_dclick(3, 1): the middle rate, set ($fda2dc..$fda2e4)             */
#define GEM_DCLICK_SET        1
#define AES_RSC_AES_FIXED     2          /* AES_RSC_AES_FRESH once rs_fixit ran ($fda2f8 move.w #2,$9c40)        */
#define GEM_ESCAPE_EXIT_ALPHA 2          /* gsx_escapes(2), the teardown's      ($fda3c8 move.w #2,(sp))         */

/* ---- the INF reader ------------------------------------------------------------------------------------------------- */
#define INF_BUFFER_BYTES      2048       /* the block, the shell's GEM buffer, the read ($fda410, $fda41e, $fda49a) */
/* The ROM's own strings, each twice — once for the current drive, once for C:. */
#define AES_INF_ROOT          0xfef348   /* bytes: "\\\0"                    ($fda442 move.l #$fef348,(sp))    */
#define AES_INF_NAME          0xfef34a   /* bytes: "DESKTOP.INF\0"           ($fda44c move.l #$fef34a,-(sp))   */
#define AES_INF_ROOT_OF_C     0xfef356   /* bytes: "\\\0"                    ($fda46e move.l #$fef356,(sp))    */
#define AES_INF_NAME_OF_C     0xfef358   /* bytes: "DESKTOP.INF\0"           ($fda478 move.l #$fef358,-(sp))   */
#define INF_OPEN_MODE         0          /* dos_open's: read                    ($fda44a, $fda476 clr.w (sp))   */
#define INF_ROM_RAM_NO_SIZE   0          /* rom_ram(3, buffer, 0)               ($fda4b4, $fda4c4 clr.w (sp))   */
#define INF_LINE_MARK         '#'        /* ($fda4e8 cmpi.b #35,(a5))                                           */
#define INF_SCREEN_LINE       'E'        /* ($fda4f4 cmpi.b #69,(a5))                                           */
#define INF_SECOND_PAIR       5          /* from the `E`: "E xx " skipped unread ($fda4fa addq.l #5,a5)          */
#define INF_PAIR_KEPT_BITS    0x00f0     /* what a rewritten pair keeps of itself ($fda512 andi.w #$f0,(sp))     */
#define INF_PAIR_DEVICE_BITS  0x0003     /* the device a pair asks, less one    ($fda528 andi.w #3,-2(a6))       */
#define INF_READ              1          /* ($fda564 moveq #1,d0)                                               */
#define INF_NOT_READ          0          /* ($fda56a clr.w d0)                                                  */

#ifndef __ASSEMBLER__
void aes_ini_dlongs(uint8_t *image);                                                                  /* $fd9ffc */
void aes_all_run(uint8_t *image);                                                                     /* $fda03e */
void aes_pinit(uint8_t *image, uint32_t pd, uint32_t cda);                                            /* $fda3d6 */
int16_t aes_gem_read_inf(uint8_t *image);                                                             /* $fda408 */
#ifdef RECREATE_HOST_DIFFERENTIAL
/* gem_main off target, where a core is handed the image. It returns only when the shell does — on no machine a
 * boot makes — so no case calls it whole (ruling W4-R5); ITS FIRST STRETCH, which calls nothing that waits or
 * traps but install_trap2, is a call of its own: from the entry to the instruction before `sti` ($fda062..$fda1ce). */
void aes_gem_main(uint8_t *image);                                                                    /* $fda062 */
void aes_gem_main_lays_the_processes(uint8_t *image);
#else
/* ...and on target: gem_entry's `jsr`, with no argument — the image base comes through a register
 * (`staged_call.h`'s `target_image`). */
void aes_rom_gem_main(void);                                                                          /* $fda062 */
#endif
#endif

#endif /* TOS102US_AES_GEMINIT_H */
