/* head.S — THE BOOT'S HEAD as the ROM spells it, `[$fc0030, $fc02cc)` BYTE FOR BYTE (ruling D7, "Byte-transcribed
 * .S"): from the reset's first instruction to `lea $755a,sp`, the first point a C function can stand on. Hand 68000
 * with NO C SPELLING: it runs before any stack is real — every "call" is `lea <return>(pc),a6` (or a5) and a `bra`,
 * every return `jmp (a6)` — and the cold arm's stack at $8000 is cleared under it by both arms' `[$980, $10000)`.
 *
 * WHERE IT RUNS (`boot/head.h`, `HEAD_LAID_AT`; ruling "ROM-window overlay"): laid over a copy of the image's ROM at
 * $fc6000 — A LABELLED STAGING (`test/boot.py`, `Overlay`) — and linked there by its own rule (`build/boothead/`,
 * the Makefile), so no other blob holds it. Its own branches are the ROM's words; the TEN OPERANDS that leave it are
 * spelt `IN_PLACE(<ROM address>)` and reach the ROM's own bytes WHERE THEY LIE (each pinned to its exact value,
 * `transcription.Relocated(..., in_place=True)`): the memory-valid check and the bank test (code the ROM runs on both
 * shores, returning through the link in A6 / A5), the PAL arm's sync wait, and the four data reads — os_conf, the
 * palette, the OS header's os_magic and the header read as a MUPB (D11 open: obligations on a rebuilt ROM,
 * `test_boot_rom_data.py`).
 *
 * THE ARMS NO MACHINE OF THIS HARNESS TAKES are byte-pinned only: the diagnostic cartridge (D2), the reset-resident
 * hook (D12), the PAL header's sync wait (this ROM's header is US). `reset` is Musashi's no-op (D6): its byte and its
 * one instruction are held, its effect on the chips is on no surface.
 *
 * REGISTERS: A5 = 0 for every system variable's 16-bit displacement; A6 / A5 the return links; D6 memctrl and D5
 * phystop from the sizing (or reloaded) into the clears; D0-D4, D7, A0-A4 scratch of each loop (`$fc0160`: A4 holds
 * the bus-error vector the RAM probe borrows).
 */
#include "addrs.h"
#include "m68k_encodings.h"
#include "boot/head.h"

/* A ROM address reached pc-relative where it lies: the head is laid at HEAD_LAID_AT, so the address is `boot_head`
 * plus its distance from there — a difference inside this section, which the assembler resolves to the displacement. */
#define IN_PLACE(rom)        (boot_head + ((rom) - HEAD_LAID_AT))
#define LAST_INDEX(count)    ((count) - 1)                   /* a `dbf` count: one pass more than its register */

    .text
    .globl  boot_head
    .type   boot_head,@function
boot_head:
/* ---- $fc0030: the reset — mask everything, reset the chips, a diagnostic cartridge first (D2) ------------------ */
    move.w  #HEAD_SR_MASKED,%sr
    reset                                                   /* D6: Musashi's no-op */
    cmpi.l  #CARTRIDGE_DIAGNOSTIC_MAGIC,(CARTRIDGE_PORT).l
    bne.s   no_diagnostic_cartridge
    lea     (no_diagnostic_cartridge,%pc),%a6
    jmp     (CARTRIDGE_DIAGNOSTIC_ENTRY).l
/* ---- $fc004c: memory valid? then restore the memory controller as the sizing left it ---------------------------- */
no_diagnostic_cartridge:
    lea     (memvalid_answered,%pc),%a6
    bra.w   IN_PLACE(ROM_MEMVALID_CHECK)
memvalid_answered:
    bne.s   reset_resident_hook
    move.b  (SYSVAR_MEMCTRL).l,(ON_THE_BUS(MEMORY_CONTROLLER)).l
/* ---- $fc0060: a reset-resident routine hooked (D12), entered with this as its return ----------------------------- */
reset_resident_hook:
    suba.l  %a5,%a5
    cmpi.l  #RESVALID_MAGIC,SYSVAR_RESVALID(%a5)
    bne.s   sound_chip_quiet
    move.l  SYSVAR_RESVECTOR(%a5),%d0
    tst.b   SYSVAR_RESVECTOR(%a5)                           /* a 24-bit address: its top byte zero */
    bne.s   sound_chip_quiet
    btst    #RESVECTOR_ODD_BIT,%d0
    bne.s   sound_chip_quiet
    movea.l %d0,%a0
    lea     (reset_resident_hook,%pc),%a6
    jmp     (%a0)
/* ---- $fc0084: the YM2149's ports outputs, every channel off; both drives deselected ----------------------------- */
sound_chip_quiet:
    lea     (ON_THE_BUS(PSG_PORT_SELECT)).l,%a0
    move.b  #PSG_MIXER_REGISTER,(%a0)
    move.b  #HEAD_PSG_MIXER_PORTS_OUT,HEAD_PSG_DATA_OFFSET(%a0)
    move.b  #PSG_PORT_A,(%a0)
    move.b  #HEAD_PSG_PORT_A_DESELECTED,HEAD_PSG_DATA_OFFSET(%a0)
    btst    #OS_CONF_PAL_BIT,(IN_PLACE(ROM_OS_CONF_LOW),%pc)
    beq.s   boot_palette
    lea     (pal_synced,%pc),%a6                            /* a PAL header's arm: no machine here takes it */
    bra.w   IN_PLACE(ROM_SYNC_WAIT)
pal_synced:
    move.b  #HEAD_SYNC_50HZ,(ON_THE_BUS(SHIFTER_SYNC_MODE)).l
/* ---- $fc00b6: the boot palette and the first screen base ------------------------------------------------------ */
boot_palette:
    lea     (ON_THE_BUS(SHIFTER_PALETTE)).l,%a1
    move.w  #LAST_INDEX(SHIFTER_PALETTE_ENTRIES),%d0
    lea     (IN_PLACE(ROM_BOOT_PALETTE),%pc),%a0
1:  move.w  (%a0)+,(%a1)+
    dbf     %d0,1b
    move.b  #(HEAD_SCREEN_BASE >> 16),(ON_THE_BUS(SHIFTER_BASE_HIGH)).l
    move.b  #((HEAD_SCREEN_BASE >> SHIFTER_BASE_SHIFT) & 0xff),(ON_THE_BUS(SHIFTER_BASE_MID)).l
/* ---- $fc00da: memory valid again — the warm arm skips the sizing (`beq.w`), the cold arm sizes ------------------ */
    .globl  boot_head_first_ends
boot_head_first_ends:
    suba.l  %a5,%a5
    move.b  SYSVAR_MEMCTRL(%a5),%d6
    move.l  SYSVAR_PHYSTOP(%a5),%d5
    lea     (memvalid_again,%pc),%a6
    bra.w   IN_PLACE(ROM_MEMVALID_CHECK)
memvalid_again:
    beq.w   boot_head_warm_arm
/* ---- $fc00f0: THE COLD ARM — a pattern at [$8, $200) and at the same offsets of the second bank ------------------ */
    .globl  boot_head_cold_arm
boot_head_cold_arm:
    clr.w   %d6
    move.b  #HEAD_MEMCTRL_SIZING,(ON_THE_BUS(MEMORY_CONTROLLER)).l
    movea.w #HEAD_PATTERN_LO,%a0
    lea     (HEAD_BANK_BYTES + HEAD_PATTERN_LO).l,%a1
    clr.w   %d0
1:  move.w  %d0,(%a0)+
    move.w  %d0,(%a1)+
    .word   M68K_ADD_W_IMMEDIATE(M68K_D0), HEAD_PATTERN_STEP    /* add.w #$fa54,d0 — gas would pick addi.w */
    cmpa.l  #HEAD_PATTERN_HI,%a0
    bne.s   1b
/* ---- $fc0116: each bank sized by where the bank test finds its pattern (D1: the oracle's memory is flat) --------- */
    move.l  #HEAD_BANK_BYTES,%d1
next_bank:
    lsr.w   #HEAD_MEMCTRL_BANK_SHIFT,%d6
    movea.w #HEAD_ALIAS_128K,%a0
    lea     (bank_128k_answered,%pc),%a5
    bra.w   IN_PLACE(ROM_BANK_TEST)
bank_128k_answered:
    beq.s   bank_sized
    movea.w #HEAD_ALIAS_512K,%a0
    lea     (bank_512k_answered,%pc),%a5
    bra.w   IN_PLACE(ROM_BANK_TEST)
bank_512k_answered:
    beq.s   bank_512k
    movea.w #HEAD_ALIAS_2M,%a0
    lea     (bank_2m_answered,%pc),%a5
    bra.w   IN_PLACE(ROM_BANK_TEST)
bank_2m_answered:
    bne.s   bank_sized
    addq.w  #HEAD_MEMCTRL_SIZE_STEP,%d6
bank_512k:
    addq.w  #HEAD_MEMCTRL_SIZE_STEP,%d6
bank_sized:
    .word   M68K_SUB_L_IMMEDIATE(M68K_D1)                   /* sub.l #$200000,d1 — gas would pick subi.l */
    .long   HEAD_BANK_BYTES
    beq.s   next_bank
    move.b  %d6,(ON_THE_BUS(MEMORY_CONTROLLER)).l
/* ---- $fc015a: the RAM probe — a stack at $8000, the bus-error vector borrowed, 128 KB steps until a step fails ---- */
    lea     (HEAD_COLD_STACK).l,%sp
    movea.l (VECTOR_BUS_ERROR).l,%a4
    lea     (ram_probed,%pc),%a0
    move.l  %a0,(VECTOR_BUS_ERROR).l
    move.w  #HEAD_PROBE_PATTERN_STEP,%d3
    move.l  #HEAD_PROBE_STEP,%d7
    movea.l %d7,%a0
next_probe:
    movea.l %a0,%a1
    move.w  %d0,%d2
    moveq   #LAST_INDEX(HEAD_PROBE_WORDS),%d1
1:  move.w  %d2,-(%a1)
    add.w   %d3,%d2
    dbf     %d1,1b
    movea.l %a0,%a1
    moveq   #LAST_INDEX(HEAD_PROBE_WORDS),%d1
1:  cmp.w   -(%a1),%d0
    bne.s   ram_probed
    clr.w   (%a1)
    add.w   %d3,%d0
    dbf     %d1,1b
    adda.l  %d7,%a0
    bra.s   next_probe
/* ---- $fc019e: phystop is the last step that held (also the bus error's handler, on a machine) ---------------------- */
ram_probed:
    suba.l  %d7,%a0
    move.l  %a0,%d5
    move.l  %a4,(VECTOR_BUS_ERROR).l
    move.l  %d5,%d0
    .word   M68K_SUB_L_IMMEDIATE(M68K_D0)                   /* sub.l #$8000,d0 — gas would pick subi.l */
    .long   HEAD_SCREEN_BYTES
    lsr.w   #SHIFTER_BASE_SHIFT,%d0
    move.b  %d0,(ON_THE_BUS(SHIFTER_BASE_MID)).l
    swap    %d0
    move.b  %d0,(ON_THE_BUS(SHIFTER_BASE_HIGH)).l
/* ---- $fc01c0: RAM cleared from phystop down to $400 (the stack at $8000 with it) ------------------------------- */
    movea.l %d5,%a0
    move.l  #HEAD_RAM_CLEAR_FLOOR,%d4
    moveq   #0,%d0
    moveq   #0,%d1
    moveq   #0,%d2
    moveq   #0,%d3
1:  movem.l %d0-%d3,-(%a0)
    movem.l %d0-%d3,-(%a0)
    movem.l %d0-%d3,-(%a0)
    movem.l %d0-%d3,-(%a0)
    cmpa.l  %d4,%a0
    bne.s   1b
/* ---- $fc01e4: what the sizing found, and memory valid from now on ------------------------------------------------ */
    suba.l  %a5,%a5
    move.b  %d6,SYSVAR_MEMCTRL(%a5)
    move.l  %d5,SYSVAR_PHYSTOP(%a5)
    move.l  #MEMVALID_MAGIC,SYSVAR_MEMVALID(%a5)
    move.l  #MEMVAL2_MAGIC,SYSVAR_MEMVAL2(%a5)
    move.l  #MEMVAL3_MAGIC,SYSVAR_MEMVAL3(%a5)
/* ---- $fc0206: BOTH ARMS — [$980, $10000) cleared, the screen at phystop - 32 KB, cleared ------------------------- */
    .globl  boot_head_warm_arm
boot_head_warm_arm:
    suba.l  %a5,%a5
    movea.l #HEAD_CLEAR_LO,%a0
    movea.l #HEAD_CLEAR_HI,%a1
    moveq   #0,%d0
1:  move.w  %d0,(%a0)+
    cmpa.l  %a0,%a1
    bne.s   1b
    movea.l SYSVAR_PHYSTOP(%a5),%a0
    suba.l  #HEAD_SCREEN_BYTES,%a0
    move.l  %a0,SYSVAR_V_BAS_AD(%a5)
    move.b  (SYSVAR_V_BAS_AD + 1)(%a5),(ON_THE_BUS(SHIFTER_BASE_HIGH)).l
    move.b  (SYSVAR_V_BAS_AD + 2)(%a5),(ON_THE_BUS(SHIFTER_BASE_MID)).l
    move.w  #LAST_INDEX(HEAD_SCREEN_BYTES / HEAD_SCREEN_CLEAR_BYTES),%d1
1:  move.l  %d0,(%a0)+
    move.l  %d0,(%a0)+
    move.l  %d0,(%a0)+
    move.l  %d0,(%a0)+
    dbf     %d1,1b
/* ---- $fc024a: the OS's end and the shell to start — from GEM's MUPB if os_magic leads to one, else the header ---- */
    movea.l (IN_PLACE(ROM_OS_MAGIC),%pc),%a0
    cmpi.l  #MUPB_MAGIC,(%a0)
    beq.s   1f
    lea     (IN_PLACE(ROM_HEADER_AS_MUPB),%pc),%a0
1:  move.l  MUPB_END_OS(%a0),(SYSVAR_END_OS).l
    move.l  MUPB_EXEC_OS(%a0),(SYSVAR_EXEC_OS).l
/* ---- $fc026a: the disk, printer and screen-dump vectors (ROM code by value: CODE obligations on a rebuilt ROM) -- */
    move.l  #ROM_HDV_INIT,SYSVAR_HDV_INIT(%a5)
    move.l  #ROM_HDV_RW,HDV_RWABS(%a5)
    move.l  #ROM_HDV_BPB,HDV_BPB(%a5)
    move.l  #ROM_HDV_MEDIACH,HDV_MEDIACH(%a5)
    move.l  #ROM_HDV_BOOT,SYSVAR_HDV_BOOT(%a5)
    move.l  #XCOSTAT_PRT,SYSVAR_PRV_LSTO(%a5)
    move.l  #XCONOUT_PRT,SYSVAR_PRV_LST(%a5)
    move.l  #XCOSTAT_RS232,SYSVAR_PRV_AUXO(%a5)
    move.l  #XCONOUT_RS232,SYSVAR_PRV_AUX(%a5)
    move.l  #ROM_SCR_DUMP,SYSVAR_SCR_DUMP(%a5)
/* ---- $fc02ba: the TPA's bounds, and the BIOS's stack — where the head ends (D7) -------------------------------- */
    move.l  SYSVAR_V_BAS_AD(%a5),SYSVAR_MEMTOP(%a5)
    move.l  SYSVAR_END_OS(%a5),SYSVAR_MEMBOT(%a5)
    lea     (HEAD_BIOS_STACK_TOP).l,%sp
    .globl  boot_head_ends
boot_head_ends:
    .size   boot_head,.-boot_head
