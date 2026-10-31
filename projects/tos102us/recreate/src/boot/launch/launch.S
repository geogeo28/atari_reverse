/* launch.S — THE BOOT'S LAST SLICE as the ROM spells it (the user's ruling R-B4-1, 2026-10-31: "Byte-transcribed .S",
 * the C-first rule's exception over the 1.10 bar): the launch [$fc047a, $fc0518) and the AUTO runner with the process
 * it launches [$fc0c4a, $fc0d50), BYTE FOR BYTE, laid as the ROM lays them — the bytes between the two FILLED, so both
 * `bsr`s to the runner are the ROM's own words. Its C twin is `launch.c` + `launch_entry.S` (`boot/launch.h`).
 *
 * WHAT DIFFERS FROM THE ROM'S WORDS (each held: `test_boot_launch.py`'s pin): every operand that leaves the two spans,
 * reaching the ROM's own bytes IN PLACE — the environment's template, "COMMAND.PRG", the empty string, the AUTO search's
 * path and its pattern (D11: TABLE obligations, `test_boot_rom_data.py`) — and ONE LONGWORD: the process's text the
 * runner stores in its basepage, this build's process entry (a linked address, mapped back by the comparison).
 *
 * THE ROM'S BUGS, KEPT BY BEING ITS BYTES: the environment's letter from `_bootdev`'s high byte; the launch's Pexec(5)
 * dropping 14 of its 16 bytes; Pexec(4) handed A3 as its name and environment; Pexec(5)'s answer unchecked. REGISTERS:
 * A5 = 0 for the runner's system variables; D7 the process's count for its own stack trick (`adda.w d7,sp` after two
 * traps); A4 Super's answer, never read; A5 the process's basepage — each kept by GEMDOS in a basepage frame. */
#include "addrs.h"
#include "m68k_encodings.h"
#include "boot/head.h"
#include "boot/sysvars.h"
#include "boot/launch.h"

/* A ROM address reached pc-relative where it lies: the .S is laid at LAUNCH_LAID_AT, so the address is `boot_launch_entry`
 * plus its distance from there — a difference inside this section, which the assembler resolves to the displacement. */
#define IN_PLACE(rom)        (boot_launch_entry + ((rom) - LAUNCH_LAID_AT))
#define SEARCH_FRAME_BYTES   8                               /* Fsfirst's: function, path, attributes (`moveq #8,d7`) */
#define FSNEXT_FRAME_BYTES   2                               /* Fsnext's: the function (`moveq #2,d7`) */
#define FSETDTA_FRAME_BYTES  6
#define MSHRINK_DROPPED      6                               /* the ROM drops 6 of Mshrink's 12: the rest is left */

    .text
/* ---- $fc047a: the launch — `_cmdload` tested before the AUTO programs run ---------------------------------------- */
    .globl  boot_launch_entry
    .type   boot_launch_entry,@function
boot_launch_entry:
    tst.w   (SYSVAR_CMDLOAD).l
    beq.s   boot_launch_calls_the_runner
    bsr.w   boot_auto_runner_entry
    move.l  #ROM_OS_HEADER,(SYSVAR_SYSBASE).l
    pea     (IN_PLACE(ROM_EMPTY_STRING),%pc)
    pea     (IN_PLACE(ROM_EMPTY_STRING),%pc)
    pea     (IN_PLACE(ROM_COMMAND_PRG),%pc)
    clr.w   -(%sp)                                          /* Pexec(0, "COMMAND.PRG", "", "") */
    bra.s   pexec_trap
/* ---- $fc04a0: the GEM arm ------------------------------------------------------------------------------------- */
    .globl  boot_launch_calls_the_runner
boot_launch_calls_the_runner:
    bsr.w   boot_auto_runner_entry
    .globl  boot_launch_auto_ran
boot_launch_auto_ran:
    move.l  #ROM_OS_HEADER,(SYSVAR_SYSBASE).l
    lea     (IN_PLACE(ROM_ENVIRONMENT_TEMPLATE),%pc),%a0
    .word   M68K_MOVEA_L_IMMEDIATE(M68K_A1)                 /* movea.l #$840,a1 (gas would shorten it) */
    .long   BOOT_ENVIRONMENT
environment_byte:
    cmpi.b  #ENVIRONMENT_DRIVE_MARK,(%a0)
    bne.s   environment_copied
    movea.l %a1,%a2
environment_copied:
    move.b  (%a0)+,(%a1)+
    bpl.s   environment_byte
    move.b  (SYSVAR_BOOTDEV).l,%d0
    .word   M68K_ADD_B_IMMEDIATE(M68K_D0), DRIVE_LETTER_A    /* add.b #'A',d0 (gas would make it addi.b) */
    move.b  %d0,(%a2)
    pea     (BOOT_ENVIRONMENT).l
    pea     (ROM_EMPTY_STRING).l
    pea     (IN_PLACE(ROM_EMPTY_STRING),%pc)
    move.w  #LAUNCH_PEXEC_CREATE_BASEPAGE,-(%sp)
    move.w  #GEMDOS_PEXEC_FN,-(%sp)
    trap    #1
    adda.w  #PEXEC_FRAME_BYTES - LAUNCH_STRAY_WORD,%sp
    movea.l %d0,%a0
    move.l  (SYSVAR_EXEC_OS).l,BASEPAGE_TBASE(%a0)
    pea     (BOOT_ENVIRONMENT).l
    move.l  %a0,-(%sp)
    pea     (IN_PLACE(ROM_EMPTY_STRING),%pc)
    move.w  #LAUNCH_PEXEC_JUST_GO,-(%sp)
pexec_trap:
    move.w  #GEMDOS_PEXEC_FN,-(%sp)
    trap    #1
    adda.w  #PEXEC_FRAME_BYTES - LAUNCH_STRAY_WORD,%sp
    jmp     (ROM_RESET_ENTRY).l
    .size   boot_launch_entry,.-boot_launch_entry

/* ---- [$fc0518, $fc0c4a): the ROM's strings and the rest of the BIOS between — not ours: FILLED --------------------- */
    .space  ROM_AUTO_RUNNER - ROM_LAUNCH_END

/* ---- $fc0c4a: THE AUTO RUNNER — its return kept, the search's path, the boot drive, a process Pexec'd ------------ */
    .globl  boot_auto_runner_entry
    .type   boot_auto_runner_entry,@function
boot_auto_runner_entry:
    lea     (IN_PLACE(ROM_AUTO_PATH),%pc),%a0
    lea     (IN_PLACE(ROM_AUTO_PATTERN),%pc),%a1
    move.l  (%sp)+,(AUTO_RETURN).l
    suba.l  %a5,%a5
    move.l  %a0,AUTO_PATH(%a5)
    move.l  %a1,AUTO_PATTERN(%a5)
    move.l  SYSVAR_DRVBITS(%a5),%d0
    move.w  (SYSVAR_BOOTDEV).l,%d1
    btst    %d1,%d0
    beq.s   auto_runner_returns
    lea     (IN_PLACE(ROM_EMPTY_STRING),%pc),%a0
    move.l  %a0,-(%sp)
    move.l  %a0,-(%sp)
    move.l  %a0,-(%sp)
    move.w  #LAUNCH_PEXEC_CREATE_BASEPAGE,-(%sp)
    move.w  #GEMDOS_PEXEC_FN,-(%sp)
    trap    #1
    adda.w  #PEXEC_FRAME_BYTES,%sp
    movea.l %d0,%a0
    move.l  #boot_auto_process_entry,BASEPAGE_TBASE(%a0)    /* THE ONE LONGWORD OURS: the ROM's $fc0cae */
    move.l  %a3,-(%sp)
    move.l  %d0,-(%sp)
    move.l  %a3,-(%sp)
    move.w  #LAUNCH_PEXEC_JUST_GO,-(%sp)
    move.w  #GEMDOS_PEXEC_FN,-(%sp)
    trap    #1
    adda.w  #PEXEC_FRAME_BYTES,%sp
auto_runner_returns:
    move.l  (AUTO_RETURN).l,-(%sp)
    rts
    .size   boot_auto_runner_entry,.-boot_auto_runner_entry

/* ---- $fc0cae: THE AUTO PROCESS — Super, its basepage's top its stack, Mshrink, every \AUTO\*.PRG Pexec(0)'d ------- */
    .globl  boot_auto_process_entry
    .type   boot_auto_process_entry,@function
boot_auto_process_entry:
    clr.l   -(%sp)
    move.w  #GEMDOS_SUPER_FN,-(%sp)
    trap    #1
    .globl  boot_auto_process_supervisor
boot_auto_process_supervisor:
    addq.w  #SUPER_FRAME_BYTES,%sp
    movea.l %d0,%a4
    movea.l BASEPAGE_ARGUMENT(%sp),%a5
    lea     AUTO_PROCESS_BYTES(%a5),%sp
    move.l  #AUTO_PROCESS_BYTES,-(%sp)
    move.l  %a5,-(%sp)
    clr.w   -(%sp)
    move.w  #GEMDOS_MSHRINK_FN,-(%sp)
    trap    #1
    addq.w  #MSHRINK_DROPPED,%sp
    tst.w   %d0
    bne.s   auto_process_ends
    move.w  #AUTO_SEARCH_ATTRIBUTES,-(%sp)
    move.l  (AUTO_PATH).l,-(%sp)
    move.w  #GEMDOS_FSFIRST_FN,-(%sp)
    moveq   #SEARCH_FRAME_BYTES,%d7
auto_dta_set:
    pea     (AUTO_DTA).l
    move.w  #GEMDOS_FSETDTA_FN,-(%sp)
    trap    #1
    addq.w  #FSETDTA_FRAME_BYTES,%sp
    trap    #1                                              /* Fsfirst, or Fsnext: its words pushed before Fsetdta's */
    adda.w  %d7,%sp
    tst.w   %d0
    bne.s   auto_process_ends
    movea.l (AUTO_PATH).l,%a0
    movea.l (AUTO_PATTERN).l,%a2
    lea     (AUTO_PROGRAM_NAME).l,%a1
auto_folder_copied:
    move.b  (%a0)+,(%a1)+
    cmpa.l  %a0,%a2
    bne.s   auto_folder_copied
    lea     (AUTO_DTA + AUTO_DTA_NAME).l,%a0
auto_name_copied:
    move.b  (%a0)+,(%a1)+
    bne.s   auto_name_copied
    pea     (IN_PLACE(ROM_EMPTY_STRING),%pc)
    pea     (IN_PLACE(ROM_EMPTY_STRING),%pc)
    pea     (AUTO_PROGRAM_NAME).l
    clr.w   -(%sp)
    move.w  #GEMDOS_PEXEC_FN,-(%sp)
    trap    #1
    adda.w  #PEXEC_FRAME_BYTES,%sp
    moveq   #FSNEXT_FRAME_BYTES,%d7
    move.w  #GEMDOS_FSNEXT_FN,-(%sp)
    bra.s   auto_dta_set
auto_process_ends:
    lea     (HEAD_BIOS_STACK_TOP).l,%sp
    move.l  (AUTO_RETURN).l,-(%sp)
    rts
    .size   boot_auto_process_entry,.-boot_auto_process_entry
