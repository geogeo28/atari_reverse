/* helpers.S — the hand-68000 PURE HELPERS as the ROM spells them: the TRANSCRIPTIONS a target build
 * ships, where `helpers.c` is what Tier 1's host differential proves.
 *
 * WHY THESE ARE ASSEMBLY. Each is hand-written 68000 in the ROM, and each C port measures over the
 * 1.10 bar against it (`bench/tier3.py`'s mechanism (T) says where the cycles go, and
 * `include/transcribed.h` is the table that makes these entries what ships): the register routines
 * pay for C's calling convention itself — their arguments and answers are REGISTERS, which a C core can
 * only take off the stack and hand back through memory — and the others a carry flag, a `-(An)` or a
 * `dbf` GCC does not emit. The user's rule for the hand-written routines is C first, and where the C
 * is over the bar, the ROM's own instructions.
 *
 * WHAT PINS THEM. `test/test_vdi_helpers_asm.py` reads every routine back out of the cross-compiled blob
 * and compares it with the ROM's bytes EXACTLY (`transcription.assert_transcribed`) — no word excused: where GNU
 * as would pick another encoding for an instruction (`cmp.w #imm` as `cmpi.w`, a zero displacement
 * dropped) the ROM's words are spelt with `.word` (`m68k_encodings.h`, the one spelling policy every
 * transcription follows) — and runs each through Tier 3's TRANSCRIPTION relation over its Tier 1 cases:
 * the same image and the WHOLE register file the ROM leaves.
 *
 * THE ENTRIES are the ROM routines' names with `_rom_` after the `vdi_` (`VDI_ROM_SORT_WORDS` is
 * `vdi_rom_sort_words`), which is how Tier 3 finds the ROM address a transcription row is about.
 *
 * REGISTERS, as the ROM leaves them — the relation compares all of them. Against the GCC m68k ABI,
 * whose callers keep D2-D7/A2-A6, four entries are hazards and `include/transcribed.h` lists each
 * one's set, measured: `sort_words` and `smul_div` destroy D2, `vr_trnfm`'s in-place transpose D7
 * outside its `movem` pair (harmless in the ROM only because its caller, the Alcyon dispatcher `$fca9f6`,
 * restores D7 from its own frame), and `gemdos_call` whatever its `trap #1` does not keep — D2/A2.
 * `act_siz` saves what it uses and `clc_dda` and `get_kbshift` touch only D0/D1. A C caller in a shipped
 * build reaches these through glue that names those sets as clobbers.
 *
 * `clamp_mouse` ($fcfedc) is a helper of this file's kind transcribed in `mouse.S` instead: the mouse ISR
 * reaches it by `bsr.s`, whose displacement only the ROM's own layout of the two reproduces.
 */
#include "addrs.h"
#include "m68k_encodings.h"
#include "vdi/linea.h"
#include "vdi/vdi.h"
#include "vdi/helpers.h"

    .text

/* ---- sort_words, $fca164: D0.w words at A0, bubble-sorted signed ascending ----------------------- */
    .globl  vdi_rom_sort_words
vdi_rom_sort_words:
    subq.w  #2,%d0
    bcs.s   .Lsort_done
    move.w  %d0,%d1
    movea.l %a0,%a1
.Lsort_pass:
    move.w  %d1,%d0
    movea.l %a1,%a0
.Lsort_pair:
    move.w  (%a0)+,%d2
    cmp.w   (%a0),%d2
    ble.s   .Lsort_next
    move.w  (%a0),-2(%a0)
    move.w  %d2,(%a0)
.Lsort_next:
    dbf     %d0,.Lsort_pair
    dbf     %d1,.Lsort_pass
.Lsort_done:
    rts

/* ---- smul_div, $fca186: (a * b) / c rounded, the words at 4/6/8(sp) ------------------------------ */
    .globl  vdi_rom_smul_div
vdi_rom_smul_div:
    moveq   #1,%d1
    move.w  6(%sp),%d0
    muls.w  4(%sp),%d0
    bge.s   .Lsmul_divide
    neg.w   %d1
.Lsmul_divide:
    move.w  8(%sp),%d2
    divs.w  %d2,%d0
    tst.w   %d2
    bge.s   .Lsmul_round
    neg.w   %d1
    neg.w   %d2
.Lsmul_round:
    move.l  %d3,-(%sp)
    move.l  %d0,%d3
    bge.s   .Lsmul_remainder
    neg.l   %d3
.Lsmul_remainder:
    swap    %d3
    add.w   %d3,%d3
    cmp.w   %d2,%d3
    blt.s   .Lsmul_done
    add.w   %d1,%d0
.Lsmul_done:
    move.l  (%sp)+,%d3
    rts

/* ---- get_kbshift, $fca648: the modifier keys in D0.w. Its `rts` IS vdi_nop ($fca652), the shared
 * entry of four opcodes, so the ROM's routine is these two instructions and that word. */
    .globl  vdi_rom_get_kbshift
vdi_rom_get_kbshift:
    move.b  (KBSHIFT).l,%d0
    andi.w  #0x000f,%d0
    rts

/* ---- gemdos_call, $fcfa9c: its own return address parked in LINEA_RETSAV around a `trap #1` over the
 * caller's words, and returned through ---------------------------------------------------------------- */
    .globl  vdi_rom_gemdos_call
vdi_rom_gemdos_call:
    move.l  (%sp)+,(LINEA_RETSAV).l
    trap    #1
    move.l  (LINEA_RETSAV).l,-(%sp)
    rts

/* ---- clc_dda, $fcedd0, and act_siz, $fcee02 — contiguous in the ROM, and here ------------------- */
    .globl  vdi_rom_clc_dda
vdi_rom_clc_dda:
    move.w  6(%sp),%d0
    move.w  4(%sp),%d1
    cmp.w   %d1,%d0
    ble.s   .Ldda_down
    move.w  #VDI_SCALE_UP,(LINEA_T_SCLSTS).l
    sub.w   %d1,%d0
    cmp.w   %d1,%d0
    blt.s   .Ldda_divide
    moveq   #-1,%d0
    rts
.Ldda_down:
    clr.w   (LINEA_T_SCLSTS).l
    tst.w   %d0
    bne.s   .Ldda_divide
    moveq   #1,%d0
.Ldda_divide:
    swap    %d0
    clr.w   %d0
    divu.w  %d1,%d0
    rts

    .globl  vdi_rom_act_siz
vdi_rom_act_siz:
    move.w  4(%sp),%d1
    movem.l %d2-%d3,-(%sp)
    move.w  #VDI_DDA_ACCUMULATOR_START,%d2
    move.w  (LINEA_DDA_INC).l,%d3
    .word   M68K_CMP_W_IMMEDIATE(3), VDI_DDA_DOUBLE     /* cmp.w #-1,%d3 */
    beq.s   .Lsiz_double
    moveq   #0,%d0
    subq.w  #1,%d1
    bmi.s   .Lsiz_up_done
    btst    #0,(LINEA_T_SCLSTS + 1).l
    beq.s   .Lsiz_down
.Lsiz_up:
    add.w   %d3,%d2
    bcc.s   .Lsiz_up_line
    addq.w  #1,%d0
.Lsiz_up_line:
    addq.w  #1,%d0
    dbf     %d1,.Lsiz_up
.Lsiz_up_done:
    bra.s   .Lsiz_done
.Lsiz_double:
    move.w  %d1,%d0
    add.w   %d0,%d0
    bra.s   .Lsiz_done
.Lsiz_down:
    add.w   %d3,%d2
    bcc.s   .Lsiz_down_next
    addq.w  #1,%d0
.Lsiz_down_next:
    dbf     %d1,.Lsiz_down
    tst.w   %d0
    bne.s   .Lsiz_done
    addq.w  #1,%d0
.Lsiz_done:
    movem.l (%sp)+,%d2-%d3
    rts

/* ---- vr_trnfm, $fd2d32 (opcode 110), and its two transposes, $fd2d80 and $fd2db4 ------------------
 * D0 = the inner count and D1 the outer (planes and words per plane, one way round or the other), A0
 * the source form and A1 the destination. */
    .globl  vdi_rom_vr_trnfm
vdi_rom_vr_trnfm:
    movem.l %d0-%d4/%a0-%a2,-(%sp)
    movea.l (LINEA_CONTRL).l,%a2
    movea.l CONTRL_POINTER_A(%a2),%a0
    movea.l CONTRL_POINTER_B(%a2),%a1
    move.w  MFDB_NPLANES(%a0),%d0
    move.w  MFDB_H(%a0),%d1
    move.w  MFDB_WDWIDTH(%a0),%d2
    tst.w   MFDB_STAND(%a0)
    bne.s   .Ltrnfm_to_device
    move.w  #MFDB_FORMAT_STANDARD,MFDB_STAND(%a1)
    mulu.w  %d2,%d1
    bra.s   .Ltrnfm_forms
.Ltrnfm_to_device:
    clr.w   MFDB_STAND(%a1)
    mulu.w  %d2,%d1
    exg     %d0,%d1
.Ltrnfm_forms:
    .word   M68K_MOVEA_L_D16(0, 0), MFDB_ADDR           /* movea.l MFDB_ADDR(%a0),%a0 */
    .word   M68K_MOVEA_L_D16(1, 1), MFDB_ADDR           /* movea.l MFDB_ADDR(%a1),%a1 */
    cmpa.l  %a0,%a1
    beq.s   .Ltrnfm_one_buffer
    bsr.s   .Ltrnfm_copy
    bra.s   .Ltrnfm_done
.Ltrnfm_one_buffer:
    bsr.s   .Ltrnfm_in_place
.Ltrnfm_done:
    movem.l (%sp)+,%d0-%d4/%a0-%a2
    rts

.Ltrnfm_in_place:
    dbf     %d1,.Ltrnfm_next_pass
    rts
.Ltrnfm_pass:
    clr.w   %d2
    move.w  %d1,%d4
    bra.s   .Ltrnfm_row_test
.Ltrnfm_row:
    adda.w  %d0,%a0
    lea     2(%a0,%d0.w),%a0
    move.w  (%a0),%d7
    movea.l %a0,%a1
    movea.l %a0,%a2
    add.w   %d0,%d2
    move.w  %d2,%d3
    bra.s   .Ltrnfm_shift_test
.Ltrnfm_shift:
    movea.l %a1,%a2
    move.w  -(%a1),(%a2)
.Ltrnfm_shift_test:
    dbf     %d3,.Ltrnfm_shift
    move.w  %d7,(%a1)
.Ltrnfm_row_test:
    dbf     %d4,.Ltrnfm_row
    movea.l %a2,%a0
.Ltrnfm_next_pass:
    dbf     %d0,.Ltrnfm_pass
    rts

.Ltrnfm_copy:
    move.w  %d1,%d4
    add.w   %d1,%d1
    bra.s   .Ltrnfm_copy_row_test
.Ltrnfm_copy_row:
    movea.l %a1,%a2
    move.w  %d0,%d3
    bra.s   .Ltrnfm_copy_word_test
.Ltrnfm_copy_word:
    move.w  (%a0)+,(%a2)
    adda.w  %d1,%a2
.Ltrnfm_copy_word_test:
    dbf     %d3,.Ltrnfm_copy_word
    lea     2(%a1),%a1
.Ltrnfm_copy_row_test:
    dbf     %d4,.Ltrnfm_copy_row
    rts
