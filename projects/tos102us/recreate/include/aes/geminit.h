/* aes/geminit.h — geminit's three LEAVES (`src/aes/geminit.c`): what gem_main (`$fda062`, band 5's last wave) and the
 * accessory loader call before a process runs.
 *
 *   $fd9ffc ini_dlongs()      the AES's five long pointers into its own BSS — the shell's command line and tail, the
 *                             working path, the AES's own global[], the screen's lock — each set to where THEGLO or
 *                             the BSS holds what it names
 *   $fda03e all_run()         every other process given a turn (one bare yield), then the screen's lock taken and
 *                             given back: whoever holds it has let go before the caller goes on
 *   $fda3d6 pinit(pd, cda)    a PD made ready to be named and written to: its CDA, its pipe's address and index, its
 *                             name blank
 *
 * ALCYON C, each entered by a Line-F call over the frame its caller pushed.
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

#ifndef __ASSEMBLER__
void aes_ini_dlongs(uint8_t *image);                                                                  /* $fd9ffc */
void aes_all_run(uint8_t *image);                                                                     /* $fda03e */
void aes_pinit(uint8_t *image, uint32_t pd, uint32_t cda);                                            /* $fda3d6 */
#endif

#endif /* TOS102US_AES_GEMINIT_H */
