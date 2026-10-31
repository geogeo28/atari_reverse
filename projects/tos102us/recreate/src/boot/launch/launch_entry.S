/* launch_entry.S — where boot B4's C is entered, and the moves of the stack and the traps the C cannot make
 * (`launch.c`'s header says which and why: every stack switch, and the two Pexec(4) whose register frame GEMDOS keeps
 * in the caller's basepage — made here at the ROM's own depth with the ROM's registers in place).
 *
 * `boot_launch_entry` is [$fc047a, gem_entry), entered as the ROM's boot reaches $fc047a: on the BIOS's stack at its
 * top, every `bsr` of the boot returned. `boot_auto_runner_entry` is $fc0c4a, `bsr`'d with that stack under its
 * return; `boot_auto_process_entry` is $fc0cae, the first instruction of the process the runner Pexec(4)s — user mode,
 * its basepage at 4(sp). The C keeps D2/A2 (GCC's ABI) and never touches D3-D7/A3-A6 (compiled with them fixed). */
#include "addrs.h"
#include "c_call_glue.h"
#include "boot/head.h"
#include "boot/sysvars.h"
#include "boot/launch.h"

    /* Pexec(mode, name, tail, environment) as the ROM's boot traps it: the five words pushed where the stack stands,
     * and dropped. Each operand is an effective address (an immediate, or a register the ROM held it in). */
    .macro  PEXEC_TRAP mode, name, tail, environment
    move.l  \environment,-(%sp)
    move.l  \tail,-(%sp)
    move.l  \name,-(%sp)
    move.w  #\mode,-(%sp)
    move.w  #GEMDOS_PEXEC_FN,-(%sp)
    trap    #1
    lea     PEXEC_FRAME_BYTES(%sp),%sp
    .endm

    .text
    .globl  boot_launch_entry
    .type   boot_launch_entry,@function
boot_launch_entry:
    tst.w   (SYSVAR_CMDLOAD).w          /* the arm is chosen BEFORE the AUTO programs run, as the ROM's is */
    beq.s   .Lthe_shell
    jbsr    boot_auto_runner_entry
    pea     (0).w
    jsr     boot_launch_sysbase
    addq.l  #IMAGE_ARGUMENT_BYTES,%sp
    PEXEC_TRAP LAUNCH_PEXEC_LOAD_AND_GO, #ROM_COMMAND_PRG, #ROM_EMPTY_STRING, #ROM_EMPTY_STRING
    bra.s   .Lreturned
.Lthe_shell:
    .globl  boot_launch_calls_the_runner
boot_launch_calls_the_runner:
    jbsr    boot_auto_runner_entry
    .globl  boot_launch_auto_ran
boot_launch_auto_ran:
    pea     (0).w
    jsr     boot_launch_gem             /* D0: the shell's basepage */
    addq.l  #IMAGE_ARGUMENT_BYTES,%sp
    subq.l  #LAUNCH_STRAY_WORD,%sp      /* the word the ROM's Pexec(5) leaves behind */
    PEXEC_TRAP LAUNCH_PEXEC_JUST_GO, #ROM_EMPTY_STRING, %d0, #BOOT_ENVIRONMENT
.Lreturned:
    jmp     (ROM_RESET_ENTRY).l
    .size   boot_launch_entry,.-boot_launch_entry

    /* The runner returns through AUTO_RETURN, and so does the process it launches — on the BIOS's stack, never
     * through Pexec(4). A5 = 0 as the ROM's (`suba.l a5,a5`): GEMDOS keeps it in the BIOS process's frame. Pexec(4)
     * is handed the caller's A3 as its name and environment, which mode 4 reads neither of (a ROM bug, kept). */
    .globl  boot_auto_runner_entry
    .type   boot_auto_runner_entry,@function
boot_auto_runner_entry:
    move.l  (%sp)+,(AUTO_RETURN).w
    suba.l  %a5,%a5
    pea     (0).w
    jsr     boot_auto_runner            /* D0: the process's basepage, or NO_AUTO_PROCESS */
    addq.l  #IMAGE_ARGUMENT_BYTES,%sp
    tst.l   %d0
    beq.s   .Lno_process
    PEXEC_TRAP LAUNCH_PEXEC_JUST_GO, %a3, %d0, %a3
.Lno_process:
    move.l  (AUTO_RETURN).w,-(%sp)
    rts
    .size   boot_auto_runner_entry,.-boot_auto_runner_entry

    /* Super(0) — supervisor, on the caller's own stack; A4 Super's answer and A5 the basepage, as the ROM's leaves them
     * for the launch (GEMDOS keeps both in this process's frame at the launch's traps) — then the basepage's top as
     * the stack, the C, and the return through AUTO_RETURN on the BIOS's stack at its top. */
    .globl  boot_auto_process_entry
    .type   boot_auto_process_entry,@function
boot_auto_process_entry:
    pea     (SUPER_ON_THE_CALLER_S_STACK).w
    move.w  #GEMDOS_SUPER_FN,-(%sp)
    trap    #1
    .globl  boot_auto_process_supervisor
boot_auto_process_supervisor:           /* Super's return, its frame left on the process's own stack */
    addq.l  #SUPER_FRAME_BYTES,%sp
    movea.l %d0,%a4
    movea.l BASEPAGE_ARGUMENT(%sp),%a5
    lea     AUTO_PROCESS_BYTES(%a5),%sp
    move.l  %a5,-(%sp)
    pea     (0).w
    jsr     boot_auto_process
    lea     (HEAD_BIOS_STACK_TOP).w,%sp
    move.l  (AUTO_RETURN).w,-(%sp)
    rts
    .size   boot_auto_process_entry,.-boot_auto_process_entry
