/* screen.S — two of the screen plumbing's routines as the ROM spells them: the TRANSCRIPTIONS a target build
 * ships, where `screen.c`'s C twins are what Tier 1's host differential proves.
 *
 *   $fc4b7c..$fc4be7  the BIOS's span clear   (`vdi_rom_clear_span`)
 *   $fca78a..$fca7a1  the VDI's etv_timer tick (`vdi_rom_timer_tick`)
 *
 * WHY THE CLEAR IS ASSEMBLY. The ROM's loop stores 32 bytes an instruction — `movem.l` of eight zeroed
 * registers, eight to a 256-byte block — which no C spelling reaches: its C measures nearly four times the ROM
 * over v_clrwk's 32000 bytes (`bench/tier3.py`). By the user's rule for the hand-written routines — C first,
 * and where the C is over the 1.10 bar, the ROM's own instructions pinned byte for byte — the target carries
 * this, `include/transcribed.h` says so, and v_clrwk and GEMDOS's loader reach it by name.
 *
 * WHY THE TICK IS ASSEMBLY, though its C is under the bar: the etv_timer vector holds its ADDRESS, and what
 * timer C enters through it is a routine with the ROM's convention — the tick word under the return address,
 * every register the interrupted program's — which a C function of `(image, tick)` is not. The ROM's own entry
 * is the one that has it (the `src/bios/trap.S` / `isr.S` precedent for an entry the machine jumps to): the
 * `movem` bracket round USER_TIM, and the CHAIN into NEXT_TIM with the caller's registers and return address,
 * which C cannot spell (`screen.c` says what its twin does instead).
 *
 * WHAT PINS THEM. `test_vdi_screen.py` compares the assembled bytes with the ROM's EXACTLY
 * (`transcription.assert_transcribed`), no word excused, and runs both through Tier 3's TRANSCRIPTION relation — the
 * same image and the WHOLE register file. Two encodings GNU as would change are spelt out: the clear's
 * `and.l #-256,d0` as the ROM's register-form word (`m68k_encodings.h`), where as would pick ANDI; and the
 * tick's two absolute addresses as `(X).l`, which as would otherwise shorten to the word form.
 *
 * REGISTERS, as the ROM leaves them. The clear: D3-D7/A3 are saved round the loop and restored; D0-D2 and
 * A0-A2 are changed (A0 ends at `to`, A1 is `to`, A2 at the bottom of the blocks), and the callee-saved ones
 * among those, D2 and A2, are its row in `include/transcribed.h`. The tick: USER_TIM's registers are
 * restored by the bracket, but NEXT_TIM runs with the caller's and returns straight to it, so whatever the
 * chained handler changes reaches the caller — the row charges it the vector set, as every front end that
 * jumps through a vector is.
 */
#include "addrs.h"
#include "m68k_encodings.h"
#include "vdi/linea.h"
#include "vdi/screen.h"

#define CLEAR_BLOCK_SHIFT    8               /* ...counted by `lsr.l #8` */
#define FRAME_FROM           4               /* the Alcyon frame: from.l, to.l */
#define FRAME_TO             8

    .text

    .globl  vdi_rom_clear_span
vdi_rom_clear_span:
    movea.l FRAME_FROM(%sp),%a0
    movea.l FRAME_TO(%sp),%a1
    movem.l %d3-%d7/%a3,-(%sp)
    moveq   #0,%d1                              /* eight zeroed registers for the `movem` */
    moveq   #0,%d2
    moveq   #0,%d3
    moveq   #0,%d4
    moveq   #0,%d5
    moveq   #0,%d6
    moveq   #0,%d7
    movea.w %d7,%a3
    move.l  %a0,%d0
    btst    #0,%d0
    beq.s   .Leven
    move.b  %d1,(%a0)+                          /* the odd first byte */
.Leven:
    move.l  %a1,%d0
    sub.l   %a0,%d0
    .word   M68K_AND_L_IMMEDIATE(0)             /* and.l #VDI_CLEAR_BLOCK_MASK,%d0 */
    .long   VDI_CLEAR_BLOCK_MASK
    beq.s   .Ltail
    lea     (0,%a0,%d0.l),%a0                   /* past the blocks: the tail starts here */
    movea.l %a0,%a2                             /* ...and the blocks are stored DOWNWARDS from it */
    lsr.l   #CLEAR_BLOCK_SHIFT,%d0
.Lblock:
    movem.l %d1-%d7/%a3,-(%a2)
    movem.l %d1-%d7/%a3,-(%a2)
    movem.l %d1-%d7/%a3,-(%a2)
    movem.l %d1-%d7/%a3,-(%a2)
    movem.l %d1-%d7/%a3,-(%a2)
    movem.l %d1-%d7/%a3,-(%a2)
    movem.l %d1-%d7/%a3,-(%a2)
    movem.l %d1-%d7/%a3,-(%a2)
    subq.l  #1,%d0
    bne.s   .Lblock
.Ltail:
    cmpa.l  %a0,%a1                             /* EQUALITY: a `to` below `from` never stops it */
    beq.s   .Ldone
    move.b  %d1,(%a0)+
    bra.s   .Ltail
.Ldone:
    movem.l (%sp)+,%d3-%d7/%a3
    rts

/* ---- $fca78a, the etv_timer tick ------------------------------------------------------------------------ */
    .globl  vdi_rom_timer_tick
vdi_rom_timer_tick:
    movem.l %d0-%a6,-(%sp)
    movea.l (LINEA_USER_TIM).l,%a0
    jsr     (%a0)
    movem.l (%sp)+,%d0-%a6
    move.l  (LINEA_NEXT_TIM).l,-(%sp)           /* the CHAIN: NEXT_TIM entered as if timer C had called it */
    rts
