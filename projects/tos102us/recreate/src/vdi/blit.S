/* blit.S — the bit-block transfer AS THE ROM WROTE IT: the TRANSCRIPTION of `src/vdi/blit.c`'s $a00e, $a007
 * and CPU engine the target build ships (`include/vdi/transcribed.h` is the table that says so, entry by
 * entry, with each one's registers).
 *
 * WHY THIS IS ASSEMBLY. The engine is THREADED CODE: after its setup a row is a chain of `jmp`s through
 * A4 (the row's first fragment), A3 (the next) and A2 (the logic op, whose entries `(a2)`, `8(a2)` and
 * `22(a2)` draw a middle, first and last word — one word lower when a pattern is ANDed in), picked out of
 * two tables of absolute addresses by four bits of geometry and the op. The C (`blit.c`) is the
 * reconstruction Tier 1 proves, and it cannot be that: every fragment boundary is a call or a branch it
 * has to make, and it measures well over Tier 3's 1.10 bar (STATUS.md has the rows). So the shipped
 * routine is the ROM's own sequence, proved two ways that need no C:
 *
 *   * BYTE FOR BYTE — `test_vdi_blit_transcription.py` compares the assembled words with the ROM's,
 *     region by region (`vdi.assert_transcribed`). Fifty-seven longwords differ, each RELOCATED there by
 *     name and pinned to the exact value it must hold: the engine's two dispatch tables (36 + 16
 *     fragment addresses) and its five `lea (fragment).l` — absolute references from the engine's region
 *     into the fragments', which name where THIS file puts them.
 *   * BY BEHAVIOUR — the batteries' cases, run through Tier 3's TRANSCRIPTION relation
 *     (`RomBench.measure_transcription`): the same image, the WHOLE register file and the same traffic.
 *
 * THE THREE REGIONS are the ROM's, in its order, each contiguous with its own tables so that every
 * PC-relative reference and every table offset assembles to the ROM's own word:
 *
 *   $fd0346..$fd063f  $a00e copy_raster and $a007 bitblt (an unreachable `rts` between them, kept)
 *   $fd1038..$fd141b  the engine: its setup, the two dispatch tables, the plane loop, the no-source rows,
 *                     the edge masks and their table, the two form-address helpers, the fast copy
 *   $fd1694..$fd19db  the fragments: the pattern row, the ten aligners, the eight middle loops, the row
 *                     ends, and the sixteen ops at their fixed entry offsets (the `.word 0` between them
 *                     is the ROM's padding, which keeps each op's entries where A2 + 8 and + 22 land)
 *
 * $fd141c..$fd1693 between the last two is the BIOS console's CPU screen set (`src/bios/`). Both front
 * ends reach the engine through drawing vector 4 exactly as the ROM does (`move.l LINEA_VECTOR_BITBLT,a5`
 * / `jsr` or `jmp (a5)`), so a shipped ROM that points the vector at `linea_rom_cpu_blit` runs this file
 * end to end. The one table read OUTSIDE these regions is VDI_MAP_COL, which $a00e addresses absolutely,
 * as `palette.S` does.
 *
 * Every line carries the ROM address it transcribes. `FRAME(field)` is a BITBLT block field as the engine
 * reaches it, off A6: `$a007` hands it the caller's block + 76, `$a00e` its own `link a6,#-76` frame.
 * `.word` lines spell the instructions GNU as would encode differently, as the ROM's words
 * (`m68k_encodings.h`), each with the instruction in its comment.
 */
#include "addrs.h"
#include "m68k_encodings.h"
#include "vdi/blit.h"
#include "vdi/linea.h"
#include "vdi/raster.h"
#include "vdi/vdi.h"

#define FRAME(field) ((field) - BITBLT_BYTES)
/* DEV_TAB's colour count, which a transparent copy's two colours are tested against */
#define DEVICE_COLOURS (LINEA_DEV_TAB + VDI_DEV_TAB_COLOURS_INDEX * VDI_WORD_BYTES)

    .text

/* ==== $fd0346..$fd063f ==============================================================================
 * $a00e copy_raster — every register saved, the block built in a `link` frame. intin[0]'s bit 4 the
 * pattern (P_* from PATPTR / MULTIFILL, or P_ADDR = 0); then each MFDB's form (a null base the screen:
 * v_bas_ad, PLANES, WIDTH), refused unless the destination is 1, 2 or 4 planes (`btst` on a register:
 * the count mod 32); then the ops — COPY_TRAN: a one-plane source (S_NXPL = 0), intin[1] / intin[2]
 * mapped through MAP_COL into FG / BG, OP_TAB by the mode; opaque: the same depths, op < 16. The
 * corners clipped only with CLIP on and a SCREEN destination; then vector 4 and contrl[2], [4] cleared. */
    .globl  linea_rom_copy_raster
linea_rom_copy_raster:
    movem.l %d0-%a5,-(%sp)                          /* $fd0346 */
    link.w  %fp,#-BITBLT_BYTES                      /* $fd034a */
    movea.l (LINEA_INTIN).l,%a2                     /* $fd034e */
    .word   M68K_MOVE_W_D16(2, 2), 0                /* $fd0354 move.w 0(%a2),%d2 */
    suba.l  %a3,%a3                                 /* $fd0358 */
    bclr    #BLIT_PATTERN_MODE_BIT,%d2              /* $fd035a */
    beq.s   .Lpattern_known                         /* $fd035e */
    movea.l (LINEA_PATPTR).l,%a3                    /* $fd0360 */
    moveq   #0,%d0                                  /* $fd0366 */
    tst.w   (LINEA_MULTIFILL).l                     /* $fd0368 */
    beq.s   .Lpattern_planes                        /* $fd036e */
    moveq   #RASTER_MULTIFILL_PLANE_BYTES,%d0       /* $fd0370 */
.Lpattern_planes:
    move.w  %d0,FRAME(BITBLT_P_NXPL)(%fp)           /* $fd0372 */
    move.w  #BLIT_PATTERN_ROW_BYTES,FRAME(BITBLT_P_NXLN)(%fp)/* $fd0376 */
    move.w  #BLIT_PATTERN_INDEX_MASK,FRAME(BITBLT_P_MASK)(%fp)/* $fd037c */
.Lpattern_known:
    move.l  %a3,FRAME(BITBLT_P_ADDR)(%fp)           /* $fd0382 */
    movea.l (LINEA_CONTRL).l,%a3                    /* $fd0386 */
    movea.l CONTRL_POINTER_A(%a3),%a5               /* $fd038c */
    movea.l CONTRL_POINTER_B(%a3),%a4               /* $fd0390 */
    .word   M68K_MOVE_L_D16(5, 6), 0                /* $fd0394 move.l 0(%a5),%d6 */
    bne.s   .Lsource_from_mfdb                      /* $fd0398 */
    move.l  (SYSVAR_V_BAS_AD).l,%d6                 /* $fd039a */
    move.w  (LINEA_PLANES).l,%d0                    /* $fd03a0 */
    move.w  (LINEA_WIDTH).l,%d4                     /* $fd03a6 */
    bra.s   .Ldestination_form                      /* $fd03ac */
.Lsource_from_mfdb:
    move.w  MFDB_NPLANES(%a5),%d0                   /* $fd03ae */
    move.w  MFDB_WDWIDTH(%a5),%d4                   /* $fd03b2 */
    add.w   %d4,%d4                                 /* $fd03b6 */
    mulu.w  %d0,%d4                                 /* $fd03b8 */
.Ldestination_form:
    .word   M68K_MOVE_L_D16(4, 7), 0                /* $fd03ba move.l 0(%a4),%d7 */
    bne.s   .Ldestination_from_mfdb                 /* $fd03be */
    move.l  (SYSVAR_V_BAS_AD).l,%d7                 /* $fd03c0 */
    move.w  (LINEA_PLANES).l,%d1                    /* $fd03c6 */
    move.w  (LINEA_WIDTH).l,%d5                     /* $fd03cc */
    bra.s   .Lforms_known                           /* $fd03d2 */
.Ldestination_from_mfdb:
    move.w  MFDB_NPLANES(%a4),%d1                   /* $fd03d4 */
    move.w  MFDB_WDWIDTH(%a4),%d5                   /* $fd03d8 */
    add.w   %d5,%d5                                 /* $fd03dc */
    mulu.w  %d1,%d5                                 /* $fd03de */
.Lforms_known:
    moveq   #BLIT_PLANE_COUNTS_SET,%d3              /* $fd03e0 */
    btst    %d1,%d3                                 /* $fd03e2 */
    beq.w   .Lcopy_raster_done                      /* $fd03e4 */
    move.w  %d1,FRAME(BITBLT_PLANE_CT)(%fp)         /* $fd03e8 */
    add.w   %d0,%d0                                 /* $fd03ec */
    move.w  %d0,FRAME(BITBLT_S_NXWD)(%fp)           /* $fd03ee */
    add.w   %d1,%d1                                 /* $fd03f2 */
    move.w  %d1,FRAME(BITBLT_D_NXWD)(%fp)           /* $fd03f4 */
    move.w  %d4,FRAME(BITBLT_S_NXLN)(%fp)           /* $fd03f8 */
    move.w  %d5,FRAME(BITBLT_D_NXLN)(%fp)           /* $fd03fc */
    move.l  %d6,FRAME(BITBLT_S_FORM)(%fp)           /* $fd0400 */
    move.l  %d7,FRAME(BITBLT_D_FORM)(%fp)           /* $fd0404 */
    moveq   #2,%d4                                  /* $fd0408 */
    moveq   #2,%d5                                  /* $fd040a */
    tst.w   (LINEA_COPY_TRAN).l                     /* $fd040c */
    beq.w   .Lopaque                                /* $fd0412 */
    .word   M68K_CMP_W_IMMEDIATE(0), VDI_WORD_BYTES /* $fd0416 cmp.w #2,%d0 */
    bne.w   .Lcopy_raster_done                      /* $fd041a */
    clr.w   %d4                                     /* $fd041e */
    lea     (VDI_MAP_COL).l,%a0                     /* $fd0420 */
    move.w  4(%a2),%d6                              /* $fd0426 */
    cmp.w   (DEVICE_COLOURS).l,%d6                  /* $fd042a */
    bmi.s   .Lbackground_known                      /* $fd0430 */
    moveq   #1,%d6                                  /* $fd0432 */
.Lbackground_known:
    add.w   %d6,%d6                                 /* $fd0434 */
    move.w  0(%a0,%d6.w),%d6                        /* $fd0436 */
    move.w  2(%a2),%d7                              /* $fd043a */
    cmp.w   (DEVICE_COLOURS).l,%d7                  /* $fd043e */
    bmi.s   .Lforeground_known                      /* $fd0444 */
    moveq   #1,%d7                                  /* $fd0446 */
.Lforeground_known:
    add.w   %d7,%d7                                 /* $fd0448 */
    move.w  0(%a0,%d7.w),%d7                        /* $fd044a */
    .word   M68K_CMP_W_IMMEDIATE(2), BLIT_MODE_REPLACE/* $fd044e cmp.w #1,%d2 */
    beq.s   .Lmode_replace                          /* $fd0452 */
    .word   M68K_CMP_W_IMMEDIATE(2), BLIT_MODE_TRANSPARENT/* $fd0454 cmp.w #2,%d2 */
    beq.s   .Lmode_transparent                      /* $fd0458 */
    .word   M68K_CMP_W_IMMEDIATE(2), BLIT_MODE_XOR  /* $fd045a cmp.w #3,%d2 */
    beq.s   .Lmode_xor                              /* $fd045e */
    .word   M68K_CMP_W_IMMEDIATE(2), BLIT_MODE_REVERSE/* $fd0460 cmp.w #4,%d2 */
    bne.w   .Lcopy_raster_done                      /* $fd0464 */
    move.b  #BLIT_OP_S_AND_D,FRAME(BITBLT_OP_TAB)(%fp)/* $fd0468 */
    move.b  #BLIT_OP_NOT_S_OR_D,FRAME(BITBLT_OP_TAB+1)(%fp)/* $fd046e */
    clr.w   FRAME(BITBLT_FG_COL)(%fp)               /* $fd0474 */
    move.w  %d6,FRAME(BITBLT_BG_COL)(%fp)           /* $fd0478 */
    bra.s   .Lops_known                             /* $fd047c */
.Lmode_transparent:
    move.b  #BLIT_OP_NOT_S_AND_D,FRAME(BITBLT_OP_TAB)(%fp)/* $fd047e */
    move.b  #BLIT_OP_S_OR_D,FRAME(BITBLT_OP_TAB+2)(%fp)/* $fd0484 */
    clr.w   FRAME(BITBLT_BG_COL)(%fp)               /* $fd048a */
    move.w  %d7,FRAME(BITBLT_FG_COL)(%fp)           /* $fd048e */
    bra.s   .Lops_known                             /* $fd0492 */
.Lmode_replace:
    move.w  %d6,FRAME(BITBLT_BG_COL)(%fp)           /* $fd0494 */
    move.w  %d7,FRAME(BITBLT_FG_COL)(%fp)           /* $fd0498 */
    move.b  #BLIT_OP_ZERO,FRAME(BITBLT_OP_TAB)(%fp) /* $fd049c */
    move.b  #BLIT_OP_NOT_S,FRAME(BITBLT_OP_TAB+1)(%fp)/* $fd04a2 */
    move.b  #BLIT_OP_S,FRAME(BITBLT_OP_TAB+2)(%fp)  /* $fd04a8 */
    move.b  #BLIT_OP_ONE,FRAME(BITBLT_OP_TAB+3)(%fp)/* $fd04ae */
    bra.s   .Lops_known                             /* $fd04b4 */
.Lmode_xor:
    clr.w   FRAME(BITBLT_BG_COL)(%fp)               /* $fd04b6 */
    clr.w   FRAME(BITBLT_FG_COL)(%fp)               /* $fd04ba */
    move.b  #BLIT_OP_S_XOR_D,FRAME(BITBLT_OP_TAB)(%fp)/* $fd04be */
    bra.s   .Lops_known                             /* $fd04c4 */
.Lopaque:
    .word   M68K_CMP_W_IMMEDIATE(2), BLIT_OP_COUNT  /* $fd04c6 cmp.w #16,%d2 */
    bcc.w   .Lcopy_raster_done                      /* $fd04ca */
    cmp.w   %d0,%d1                                 /* $fd04ce */
    bne.w   .Lcopy_raster_done                      /* $fd04d0 */
    clr.w   FRAME(BITBLT_BG_COL)(%fp)               /* $fd04d4 */
    clr.w   FRAME(BITBLT_FG_COL)(%fp)               /* $fd04d8 */
    move.b  %d2,FRAME(BITBLT_OP_TAB)(%fp)           /* $fd04dc */
.Lops_known:
    move.w  %d4,FRAME(BITBLT_S_NXPL)(%fp)           /* $fd04e0 */
    move.w  %d5,FRAME(BITBLT_D_NXPL)(%fp)           /* $fd04e4 */
    movea.l (LINEA_PTSIN).l,%a2                     /* $fd04e8 */
    tst.w   (LINEA_CLIP).l                          /* $fd04ee */
    beq.s   .Lcorners_given                         /* $fd04f4 */
    .word   M68K_TST_L_D16(4), 0                    /* $fd04f6 tst.l 0(%a4) */
    beq.s   .Lcorners_clipped                       /* $fd04fa */
.Lcorners_given:
    .word   M68K_MOVE_W_D16(2, 0), 0                /* $fd04fc move.w 0(%a2),%d0 */
    move.w  2(%a2),%d1                              /* $fd0500 */
    move.w  8(%a2),%d2                              /* $fd0504 */
    move.w  10(%a2),%d3                             /* $fd0508 */
    move.w  %d0,FRAME(BITBLT_S_XMIN)(%fp)           /* $fd050c */
    move.w  %d1,FRAME(BITBLT_S_YMIN)(%fp)           /* $fd0510 */
    move.w  %d2,FRAME(BITBLT_D_XMIN)(%fp)           /* $fd0514 */
    move.w  %d3,FRAME(BITBLT_D_YMIN)(%fp)           /* $fd0518 */
    move.w  4(%a2),%d4                              /* $fd051c */
    move.w  6(%a2),%d5                              /* $fd0520 */
    move.w  %d4,%d6                                 /* $fd0524 */
    sub.w   %d0,%d6                                 /* $fd0526 */
    addq.w  #1,%d6                                  /* $fd0528 */
    move.w  %d6,FRAME(BITBLT_B_WD)(%fp)             /* $fd052a */
    move.w  %d5,%d7                                 /* $fd052e */
    sub.w   %d1,%d7                                 /* $fd0530 */
    addq.w  #1,%d7                                  /* $fd0532 */
    move.w  %d7,FRAME(BITBLT_B_HT)(%fp)             /* $fd0534 */
    move.w  12(%a2),%d6                             /* $fd0538 */
    move.w  14(%a2),%d7                             /* $fd053c */
    bra.w   .Lfar_corners                           /* $fd0540 */
.Lcorners_clipped:
    .word   M68K_MOVE_W_D16(2, 0), 0                /* $fd0544 move.w 0(%a2),%d0 */
    move.w  8(%a2),%d2                              /* $fd0548 */
    move.w  (LINEA_XMINCL).l,%d4                    /* $fd054c */
    cmp.w   %d4,%d2                                 /* $fd0552 */
    bge.s   .Lclipped_left                          /* $fd0554 */
    exg     %d4,%d2                                 /* $fd0556 */
    sub.w   %d2,%d4                                 /* $fd0558 */
    sub.w   %d4,%d0                                 /* $fd055a */
.Lclipped_left:
    move.w  %d0,FRAME(BITBLT_S_XMIN)(%fp)           /* $fd055c */
    move.w  %d2,FRAME(BITBLT_D_XMIN)(%fp)           /* $fd0560 */
    move.w  4(%a2),%d6                              /* $fd0564 */
    sub.w   %d0,%d6                                 /* $fd0568 */
    add.w   %d2,%d6                                 /* $fd056a */
    move.w  (LINEA_XMAXCL).l,%d4                    /* $fd056c */
    cmp.w   %d4,%d6                                 /* $fd0572 */
    ble.s   .Lclipped_right                         /* $fd0574 */
    exg     %d4,%d6                                 /* $fd0576 */
.Lclipped_right:
    move.w  2(%a2),%d1                              /* $fd0578 */
    move.w  10(%a2),%d3                             /* $fd057c */
    move.w  (LINEA_YMINCL).l,%d4                    /* $fd0580 */
    cmp.w   %d4,%d3                                 /* $fd0586 */
    bge.s   .Lclipped_top                           /* $fd0588 */
    exg     %d4,%d3                                 /* $fd058a */
    sub.w   %d3,%d4                                 /* $fd058c */
    sub.w   %d4,%d1                                 /* $fd058e */
.Lclipped_top:
    move.w  %d1,FRAME(BITBLT_S_YMIN)(%fp)           /* $fd0590 */
    move.w  %d3,FRAME(BITBLT_D_YMIN)(%fp)           /* $fd0594 */
    move.w  6(%a2),%d7                              /* $fd0598 */
    sub.w   %d1,%d7                                 /* $fd059c */
    add.w   %d3,%d7                                 /* $fd059e */
    move.w  (LINEA_YMAXCL).l,%d4                    /* $fd05a0 */
    cmp.w   %d4,%d7                                 /* $fd05a6 */
    ble.s   .Lclipped_bottom                        /* $fd05a8 */
    exg     %d4,%d7                                 /* $fd05aa */
.Lclipped_bottom:
    move.w  %d6,%d4                                 /* $fd05ac */
    sub.w   %d2,%d4                                 /* $fd05ae */
    move.w  %d4,FRAME(BITBLT_B_WD)(%fp)             /* $fd05b0 */
    addq.w  #1,FRAME(BITBLT_B_WD)(%fp)              /* $fd05b4 */
    ble.s   .Lcopy_raster_done                      /* $fd05b8 */
    add.w   %d0,%d4                                 /* $fd05ba */
    move.w  %d7,%d5                                 /* $fd05bc */
    sub.w   %d3,%d5                                 /* $fd05be */
    move.w  %d5,FRAME(BITBLT_B_HT)(%fp)             /* $fd05c0 */
    addq.w  #1,FRAME(BITBLT_B_HT)(%fp)              /* $fd05c4 */
    ble.s   .Lcopy_raster_done                      /* $fd05c8 */
    add.w   %d1,%d5                                 /* $fd05ca */
.Lfar_corners:
    move.w  %d4,FRAME(BITBLT_S_XMAX)(%fp)           /* $fd05cc */
    move.w  %d5,FRAME(BITBLT_S_YMAX)(%fp)           /* $fd05d0 */
    move.w  %d6,FRAME(BITBLT_D_XMAX)(%fp)           /* $fd05d4 */
    move.w  %d7,FRAME(BITBLT_D_YMAX)(%fp)           /* $fd05d8 */
    movea.l (LINEA_VECTOR_BITBLT).l,%a5             /* $fd05dc */
    jsr     (%a5)                                   /* $fd05e2 */
.Lcopy_raster_done:
    movea.l (LINEA_CONTRL).l,%a0                    /* $fd05e4 */
    clr.w   CONTRL_N_PTSOUT(%a0)                    /* $fd05ea */
    clr.w   CONTRL_N_INTOUT(%a0)                    /* $fd05ee */
    unlk    %fp                                     /* $fd05f2 */
    movem.l (%sp)+,%d0-%a5                          /* $fd05f4 */
    rts                                             /* $fd05f8 */
    rts                                             /* $fd05fa */

/* $a007 bitblt — A6 = the caller's block, made its frame; the far corners = the near ones + B_WD / B_HT
 * - 1, stored into it; the engine entered with the x edges in D0/D2/D4/D6. It returns to $a007's caller. */
    .globl  linea_rom_bitblt
linea_rom_bitblt:
    adda.w  #BITBLT_BYTES,%fp                       /* $fd05fc */
    move.w  FRAME(BITBLT_S_XMIN)(%fp),%d0           /* $fd0600 */
    move.w  FRAME(BITBLT_S_YMIN)(%fp),%d5           /* $fd0604 */
    move.w  FRAME(BITBLT_D_XMIN)(%fp),%d2           /* $fd0608 */
    move.w  FRAME(BITBLT_D_YMIN)(%fp),%d7           /* $fd060c */
    move.w  %d0,%d4                                 /* $fd0610 */
    move.w  %d2,%d6                                 /* $fd0612 */
    move.w  FRAME(BITBLT_B_HT)(%fp),%d1             /* $fd0614 */
    subq.w  #1,%d1                                  /* $fd0618 */
    add.w   %d1,%d5                                 /* $fd061a */
    add.w   %d1,%d7                                 /* $fd061c */
    move.w  FRAME(BITBLT_B_WD)(%fp),%d1             /* $fd061e */
    subq.w  #1,%d1                                  /* $fd0622 */
    add.w   %d1,%d4                                 /* $fd0624 */
    add.w   %d1,%d6                                 /* $fd0626 */
    move.w  %d4,FRAME(BITBLT_S_XMAX)(%fp)           /* $fd0628 */
    move.w  %d5,FRAME(BITBLT_S_YMAX)(%fp)           /* $fd062c */
    move.w  %d6,FRAME(BITBLT_D_XMAX)(%fp)           /* $fd0630 */
    move.w  %d7,FRAME(BITBLT_D_YMAX)(%fp)           /* $fd0634 */
    movea.l (LINEA_VECTOR_BITBLT).l,%a5             /* $fd0638 */
    jmp     (%a5)                                   /* $fd063e */

/* ==== $fd1038..$fd141b ==============================================================================
 * The ENGINE, vector 4's CPU body. In: D0 source x min, D2 destination x min, D4 source x max, D6
 * destination x max, A6 the frame. D1 = the shift (source bit - destination bit), D4/D6 the two spans
 * in words (`lsr.w #4`), D5 their difference. A plain bit-aligned op-3 copy of four words or more takes
 * the FAST COPY ($fd1352); everything else builds the aligner index in D5 — bit 0 the shift is right,
 * bit 1 it is 8 or more (D4 = 16 - n), bit 2 BACKWARDS (the source's first word below the
 * destination's, or the same word shifting right), bit 3 the spans' difference odd — and runs the planes:
 * each plane's op out of OP_TAB by its FG / BG bit (both spent out of the block by `lsr.w`), A2 its entry
 * out of `.Lops`, and the rows through A4 = the aligner (or the pattern row first), A3 the middle loop. */
    .globl  linea_rom_cpu_blit
linea_rom_cpu_blit:
    moveq   #15,%d5                                 /* $fd1038 */
    move.w  %d0,%d1                                 /* $fd103a */
    and.w   %d5,%d1                                 /* $fd103c */
    move.w  %d2,%d3                                 /* $fd103e */
    and.w   %d5,%d3                                 /* $fd1040 */
    lsr.w   #4,%d0                                  /* $fd1042 */
    lsr.w   #4,%d2                                  /* $fd1044 */
    lsr.w   #4,%d4                                  /* $fd1046 */
    lsr.w   #4,%d6                                  /* $fd1048 */
    sub.w   %d0,%d4                                 /* $fd104a */
    sub.w   %d2,%d6                                 /* $fd104c */
    move.w  %d4,%d5                                 /* $fd104e */
    sub.w   %d6,%d5                                 /* $fd1050 */
    sub.w   %d3,%d1                                 /* $fd1052 */
    bne.s   .Laligned                               /* $fd1054 */
    tst.l   FRAME(BITBLT_FG_COL)(%fp)               /* $fd1056 */
    bne.s   .Laligned                               /* $fd105a */
    cmpi.b  #BLIT_OP_S,FRAME(BITBLT_OP_TAB)(%fp)    /* $fd105c */
    bne.s   .Laligned                               /* $fd1062 */
    move.w  %d4,%d7                                 /* $fd1064 */
    add.w   %d6,%d7                                 /* $fd1066 */
    .word   M68K_CMP_W_IMMEDIATE(7), BLIT_FAST_SPAN_WORDS/* $fd1068 cmp.w #4,%d7 */
    bcs.s   .Laligned                               /* $fd106c */
    tst.l   FRAME(BITBLT_P_ADDR)(%fp)               /* $fd106e */
    beq.w   .Lfast_copy                             /* $fd1072 */
.Laligned:
    move.w  %d6,%d0                                 /* $fd1076 */
    subq.w  #1,%d0                                  /* $fd1078 */
    move.w  %d0,FRAME(BITBLT_MIDDLE_COUNT)(%fp)     /* $fd107a */
    .word   M68K_AND_W_IMMEDIATE(5), 1              /* $fd107e and.w #1,%d5 */
    lsl.w   #3,%d5                                  /* $fd1082 */
    move.w  %d4,%d7                                 /* $fd1084 */
    move.w  %d1,%d4                                 /* $fd1086 */
    move.w  %d1,%d2                                 /* $fd1088 */
    tst.w   %d4                                     /* $fd108a */
    bgt.s   .Lshift_distance                        /* $fd108c */
    beq.s   .Lshift_known                           /* $fd108e */
    neg.w   %d4                                     /* $fd1090 */
    addq.w  #1,%d5                                  /* $fd1092 */
.Lshift_distance:
    .word   M68K_CMP_W_IMMEDIATE(4), 8              /* $fd1094 cmp.w #8,%d4 */
    blt.s   .Lshift_known                           /* $fd1098 */
    addq.w  #2,%d5                                  /* $fd109a */
    neg.w   %d4                                     /* $fd109c */
    .word   M68K_ADD_W_IMMEDIATE(4), 16             /* $fd109e add.w #16,%d4 */
.Lshift_known:
    move.w  FRAME(BITBLT_S_XMIN)(%fp),%d0           /* $fd10a2 */
    move.w  FRAME(BITBLT_S_YMIN)(%fp),%d1           /* $fd10a6 */
    bsr.w   .Lsource_word                           /* $fd10aa */
    muls.w  FRAME(BITBLT_S_NXWD)(%fp),%d7           /* $fd10ae */
    sub.w   %d3,%d7                                 /* $fd10b2 */
    move.w  FRAME(BITBLT_D_XMIN)(%fp),%d0           /* $fd10b4 */
    move.w  FRAME(BITBLT_D_YMIN)(%fp),%d1           /* $fd10b8 */
    move.w  %d1,FRAME(BITBLT_P_INDEX)(%fp)          /* $fd10bc */
    bsr.w   .Ldestination_word                      /* $fd10c0 */
    muls.w  FRAME(BITBLT_D_NXWD)(%fp),%d6           /* $fd10c4 */
    sub.w   %d3,%d6                                 /* $fd10c8 */
    cmpa.l  %a1,%a0                                 /* $fd10ca */
    bhi.s   .Lforwards                              /* $fd10cc */
    bne.s   .Lbackwards                             /* $fd10ce */
    tst.w   %d2                                     /* $fd10d0 */
    bge.s   .Lforwards                              /* $fd10d2 */
.Lbackwards:
    addq.w  #4,%d5                                  /* $fd10d4 */
    move.w  FRAME(BITBLT_S_XMAX)(%fp),%d0           /* $fd10d6 */
    move.w  FRAME(BITBLT_S_YMAX)(%fp),%d1           /* $fd10da */
    bsr.w   .Lsource_word                           /* $fd10de */
    move.w  FRAME(BITBLT_D_XMAX)(%fp),%d0           /* $fd10e2 */
    move.w  FRAME(BITBLT_D_YMAX)(%fp),%d1           /* $fd10e6 */
    move.w  %d1,FRAME(BITBLT_P_INDEX)(%fp)          /* $fd10ea */
    bsr.w   .Ldestination_word                      /* $fd10ee */
    neg.w   FRAME(BITBLT_P_NXLN)(%fp)               /* $fd10f2 */
    bra.s   .Lwraps_known                           /* $fd10f6 */
.Lforwards:
    neg.w   %d7                                     /* $fd10f8 */
    neg.w   %d6                                     /* $fd10fa */
.Lwraps_known:
    move.w  %d7,FRAME(BITBLT_S_WRAP)(%fp)           /* $fd10fc */
    move.w  %d6,FRAME(BITBLT_D_WRAP)(%fp)           /* $fd1100 */
    bsr.w   .Ledge_masks                            /* $fd1104 */
    move.w  FRAME(BITBLT_S_NXWD)(%fp),%d2           /* $fd1108 */
    move.w  FRAME(BITBLT_D_NXWD)(%fp),%d3           /* $fd110c */
    btst    #2,%d5                                  /* $fd1110 */
    beq.s   .Lsteps_known                           /* $fd1114 */
    swap    %d6                                     /* $fd1116 */
    neg.w   %d2                                     /* $fd1118 */
    neg.w   %d3                                     /* $fd111a */
.Lsteps_known:
    move.l  %a0,FRAME(BITBLT_S_START)(%fp)          /* $fd111c */
    move.l  %a1,FRAME(BITBLT_D_START)(%fp)          /* $fd1120 */
    asl.w   #3,%d5                                  /* $fd1124 */
    movea.l .Laligners+4(%pc,%d5.w),%a3             /* $fd1126 */
    movea.l .Laligners(%pc,%d5.w),%a4               /* $fd112a */
    tst.w   FRAME(BITBLT_MIDDLE_COUNT)(%fp)         /* $fd112e */
    bge.w   .Lpattern_setup                         /* $fd1132 */
    move.l  %d6,%d0                                 /* $fd1136 */
    swap    %d0                                     /* $fd1138 */
    and.w   %d0,%d6                                 /* $fd113a */
    lea     (.Lnext_row).l,%a3                      /* $fd113c */
    btst    #6,%d5                                  /* $fd1142 */
    bne.w   .Lpattern_setup                         /* $fd1146 */
    lsr.w   #1,%d5                                  /* $fd114a */
    .word   M68K_AND_W_IMMEDIATE(5), 12             /* $fd114c and.w #12,%d5 */
    movea.l .Lword_rotates(%pc,%d5.w),%a4           /* $fd1150 */
    bra.w   .Lpattern_setup                         /* $fd1154 */
/* $fd1158: one destination word from one source word — a word rotate, by the shift bits alone */
.Lword_rotates:
    .long   .Lword_rotate_left                      /* $fd1158 */
    .long   .Lword_rotate_right                     /* $fd115c */
    .long   .Lword_rotate_right                     /* $fd1160 */
    .long   .Lword_rotate_left                      /* $fd1164 */
/* $fd1168: the ALIGNERS, sixteen (first fragment, middle loop) pairs by the index built above */
.Laligners:
    .long   .Lfirst_left_latch                      /* $fd1168 */
    .long   .Lmiddle_left_latch                     /* $fd116c */
    .long   .Lfirst_right_carry_one                 /* $fd1170 */
    .long   .Lmiddle_right_carry_read               /* $fd1174 */
    .long   .Lfirst_right_carry                     /* $fd1178 */
    .long   .Lmiddle_right_carry                    /* $fd117c */
    .long   .Lfirst_left_latch_one                  /* $fd1180 */
    .long   .Lmiddle_left_latch_read                /* $fd1184 */
    .long   .Lfirst_left_carry_one                  /* $fd1188 */
    .long   .Lmiddle_left_carry_read                /* $fd118c */
    .long   .Lfirst_right_latch                     /* $fd1190 */
    .long   .Lmiddle_right_latch                    /* $fd1194 */
    .long   .Lfirst_right_latch_one                 /* $fd1198 */
    .long   .Lmiddle_right_latch_read               /* $fd119c */
    .long   .Lfirst_left_carry                      /* $fd11a0 */
    .long   .Lmiddle_left_carry                     /* $fd11a4 */
    .long   .Lfirst_left_latch                      /* $fd11a8 */
    .long   .Lmiddle_left_latch_read                /* $fd11ac */
    .long   .Lfirst_right_carry_one                 /* $fd11b0 */
    .long   .Lmiddle_right_carry                    /* $fd11b4 */
    .long   .Lfirst_right_carry                     /* $fd11b8 */
    .long   .Lmiddle_right_carry_read               /* $fd11bc */
    .long   .Lfirst_left_latch_one                  /* $fd11c0 */
    .long   .Lmiddle_left_latch                     /* $fd11c4 */
    .long   .Lfirst_left_carry                      /* $fd11c8 */
    .long   .Lmiddle_left_carry_read                /* $fd11cc */
    .long   .Lfirst_right_latch_one                 /* $fd11d0 */
    .long   .Lmiddle_right_latch                    /* $fd11d4 */
    .long   .Lfirst_right_latch                     /* $fd11d8 */
    .long   .Lmiddle_right_latch_read               /* $fd11dc */
    .long   .Lfirst_left_carry_one                  /* $fd11e0 */
    .long   .Lmiddle_left_carry                     /* $fd11e4 */
.Lpattern_setup:
    tst.l   FRAME(BITBLT_P_ADDR)(%fp)               /* $fd11e8 */
    beq.s   .Lplane                                 /* $fd11ec */
    lea     (linea_rom_cpu_blit_ops).l,%a5          /* $fd11ee */
    exg     %a5,%a4                                 /* $fd11f4 */
    move.w  FRAME(BITBLT_P_NXLN)(%fp),%d0           /* $fd11f6 */
    bge.s   .Lpattern_step_unsigned                 /* $fd11fa */
    neg.w   %d0                                     /* $fd11fc */
.Lpattern_step_unsigned:
    muls.w  FRAME(BITBLT_P_INDEX)(%fp),%d0          /* $fd11fe */
    move.w  %d0,FRAME(BITBLT_P_INDEX)(%fp)          /* $fd1202 */
.Lplane:
    clr.w   %d0                                     /* $fd1206 */
    lsr.w   FRAME(BITBLT_FG_COL)(%fp)               /* $fd1208 */
    addx.w  %d0,%d0                                 /* $fd120c */
    lsr.w   FRAME(BITBLT_BG_COL)(%fp)               /* $fd120e */
    addx.w  %d0,%d0                                 /* $fd1212 */
    move.b  FRAME(BITBLT_OP_TAB)(%fp,%d0.w),%d0     /* $fd1214 */
    move.w  %d0,%d1                                 /* $fd1218 */
    lsl.w   #2,%d1                                  /* $fd121a */
    movea.l .Lops(%pc,%d1.w),%a2                    /* $fd121c */
    move.w  FRAME(BITBLT_B_HT)(%fp),%d5             /* $fd1220 */
    swap    %d5                                     /* $fd1224 */
    move.w  FRAME(BITBLT_MIDDLE_COUNT)(%fp),%d5     /* $fd1226 */
    move.w  #BLIT_NO_SOURCE_OPS_SET,%d1             /* $fd122a */
    btst    %d0,%d1                                 /* $fd122e */
    bne.w   .Lno_source                             /* $fd1230 */
    tst.l   FRAME(BITBLT_P_ADDR)(%fp)               /* $fd1234 */
    beq.s   .Lplane_rows                            /* $fd1238 */
    lea     -2(%a2),%a2                             /* $fd123a */
    move.w  FRAME(BITBLT_P_INDEX)(%fp),%d7          /* $fd123e */
    swap    %d7                                     /* $fd1242 */
.Lplane_rows:
    jsr     (%a4)                                   /* $fd1244 */
.Lnext_plane:
    subq.w  #1,FRAME(BITBLT_PLANE_CT)(%fp)          /* $fd1246 */
    beq.s   .Lengine_done                           /* $fd124a */
    movea.l FRAME(BITBLT_S_START)(%fp),%a0          /* $fd124c */
    adda.w  FRAME(BITBLT_S_NXPL)(%fp),%a0           /* $fd1250 */
    move.l  %a0,FRAME(BITBLT_S_START)(%fp)          /* $fd1254 */
    movea.l FRAME(BITBLT_D_START)(%fp),%a1          /* $fd1258 */
    adda.w  FRAME(BITBLT_D_NXPL)(%fp),%a1           /* $fd125c */
    move.l  %a1,FRAME(BITBLT_D_START)(%fp)          /* $fd1260 */
    move.l  FRAME(BITBLT_P_ADDR)(%fp),%d0           /* $fd1264 */
    beq.s   .Lplane                                 /* $fd1268 */
    movea.l %d0,%a2                                 /* $fd126a */
    adda.w  FRAME(BITBLT_P_NXPL)(%fp),%a2           /* $fd126c */
    move.l  %a2,FRAME(BITBLT_P_ADDR)(%fp)           /* $fd1270 */
    bra.s   .Lplane                                 /* $fd1274 */
.Lengine_done:
    rts                                             /* $fd1276 */
/* $fd1278: the sixteen ops' entries — op 5's is op 6's pattern entry, and never run */
.Lops:
    .long   .Lop_zero                               /* $fd1278 */
    .long   .Lop_s_and_d                            /* $fd127c */
    .long   .Lop_s_and_not_d                        /* $fd1280 */
    .long   .Lop_s                                  /* $fd1284 */
    .long   .Lop_not_s_and_d                        /* $fd1288 */
    .long   .Lop_d                                  /* $fd128c */
    .long   .Lop_s_xor_d                            /* $fd1290 */
    .long   .Lop_s_or_d                             /* $fd1294 */
    .long   .Lop_nor                                /* $fd1298 */
    .long   .Lop_xnor                               /* $fd129c */
    .long   .Lop_not_d                              /* $fd12a0 */
    .long   .Lop_s_or_not_d                         /* $fd12a4 */
    .long   .Lop_not_s                              /* $fd12a8 */
    .long   .Lop_not_s_or_d                         /* $fd12ac */
    .long   .Lop_nand                               /* $fd12b0 */
    .long   .Lop_one                                /* $fd12b4 */

/* The ops that read no source — 0, 10, 15 (5 skips the plane): a row walks the destination alone. */
.Lno_source:
    .word   M68K_CMP_W_IMMEDIATE(0), BLIT_OP_D      /* $fd12b8 cmp.w #5,%d0 */
    beq.s   .Lnext_plane                            /* $fd12bc */
    movem.l %a3-%a4,-(%sp)                          /* $fd12be */
    lea     (.Lfirst_no_source).l,%a4               /* $fd12c2 */
    lea     (.Lmiddle_no_source).l,%a3              /* $fd12c8 */
    tst.w   %d5                                     /* $fd12ce */
    bge.s   .Lno_source_rows                        /* $fd12d0 */
    lea     (.Lnext_row_no_source).l,%a3            /* $fd12d2 */
.Lno_source_rows:
    jsr     (%a4)                                   /* $fd12d8 */
    movem.l (%sp)+,%a3-%a4                          /* $fd12da */
    bra.w   .Lnext_plane                            /* $fd12de */

/* $fd12e2 — D6 = the destination's edge masks: high word the right edge's, low word the left's. */
.Ledge_masks:
    move.w  FRAME(BITBLT_D_XMAX)(%fp),%d0           /* $fd12e2 */
    .word   M68K_AND_W_IMMEDIATE(0), 15             /* $fd12e6 and.w #15,%d0 */
    add.w   %d0,%d0                                 /* $fd12ea */
    move.w  .Ledge_mask_table+2(%pc,%d0.w),%d6      /* $fd12ec */
    swap    %d6                                     /* $fd12f0 */
    move.w  FRAME(BITBLT_D_XMIN)(%fp),%d0           /* $fd12f2 */
    .word   M68K_AND_W_IMMEDIATE(0), 15             /* $fd12f6 and.w #15,%d0 */
    add.w   %d0,%d0                                 /* $fd12fa */
    move.w  .Ledge_mask_table(%pc,%d0.w),%d6        /* $fd12fc */
    not.w   %d6                                     /* $fd1300 */
    rts                                             /* $fd1302 */
.Ledge_mask_table:
    .word   0x0000                                  /* $fd1304 */
    .word   0x8000                                  /* $fd1306 */
    .word   0xc000                                  /* $fd1308 */
    .word   0xe000                                  /* $fd130a */
    .word   0xf000                                  /* $fd130c */
    .word   0xf800                                  /* $fd130e */
    .word   0xfc00                                  /* $fd1310 */
    .word   0xfe00                                  /* $fd1312 */
    .word   0xff00                                  /* $fd1314 */
    .word   0xff80                                  /* $fd1316 */
    .word   0xffc0                                  /* $fd1318 */
    .word   0xffe0                                  /* $fd131a */
    .word   0xfff0                                  /* $fd131c */
    .word   0xfff8                                  /* $fd131e */
    .word   0xfffc                                  /* $fd1320 */
    .word   0xfffe                                  /* $fd1322 */
    .word   0xffff                                  /* $fd1324 */

/* $fd1326 / $fd133c — A0 (A1) = the source (destination) word of (D0, D1), plane 0; D3 = its NXLN. */
.Lsource_word:
    movea.l FRAME(BITBLT_S_FORM)(%fp),%a0           /* $fd1326 */
    move.w  FRAME(BITBLT_S_NXLN)(%fp),%d3           /* $fd132a */
    lsr.w   #4,%d0                                  /* $fd132e */
    muls.w  FRAME(BITBLT_S_NXWD)(%fp),%d0           /* $fd1330 */
    muls.w  %d3,%d1                                 /* $fd1334 */
    add.l   %d0,%d1                                 /* $fd1336 */
    adda.l  %d1,%a0                                 /* $fd1338 */
    rts                                             /* $fd133a */
.Ldestination_word:
    movea.l FRAME(BITBLT_D_FORM)(%fp),%a1           /* $fd133c */
    move.w  FRAME(BITBLT_D_NXLN)(%fp),%d3           /* $fd1340 */
    lsr.w   #4,%d0                                  /* $fd1344 */
    muls.w  FRAME(BITBLT_D_NXWD)(%fp),%d0           /* $fd1346 */
    muls.w  %d3,%d1                                 /* $fd134a */
    add.l   %d0,%d1                                 /* $fd134c */
    adda.l  %d1,%a1                                 /* $fd134e */
    rts                                             /* $fd1350 */

/* $fd1352 — the FAST COPY: masked first word, whole middle words, masked last word, the rows inside the
 * planes; backwards when the source is below the destination. S_START / D_START step after every plane. */
.Lfast_copy:
    move.w  %d4,%d0                                 /* $fd1352 */
    subq.w  #2,%d0                                  /* $fd1354 */
    move.w  %d0,FRAME(BITBLT_MIDDLE_COUNT)(%fp)     /* $fd1356 */
    move.w  FRAME(BITBLT_S_NXWD)(%fp),%d5           /* $fd135a */
    muls.w  %d5,%d4                                 /* $fd135e */
    move.w  FRAME(BITBLT_D_NXWD)(%fp),%d7           /* $fd1360 */
    muls.w  %d7,%d6                                 /* $fd1364 */
    move.w  FRAME(BITBLT_S_XMIN)(%fp),%d0           /* $fd1366 */
    move.w  FRAME(BITBLT_S_YMIN)(%fp),%d1           /* $fd136a */
    bsr.s   .Lsource_word                           /* $fd136e */
    sub.w   %d3,%d4                                 /* $fd1370 */
    move.w  FRAME(BITBLT_D_XMIN)(%fp),%d0           /* $fd1372 */
    move.w  FRAME(BITBLT_D_YMIN)(%fp),%d1           /* $fd1376 */
    bsr.s   .Ldestination_word                      /* $fd137a */
    sub.w   %d3,%d6                                 /* $fd137c */
    cmpa.l  %a1,%a0                                 /* $fd137e */
    bcc.s   .Lfast_forwards                         /* $fd1380 */
    move.w  FRAME(BITBLT_S_XMAX)(%fp),%d0           /* $fd1382 */
    move.w  FRAME(BITBLT_S_YMAX)(%fp),%d1           /* $fd1386 */
    bsr.s   .Lsource_word                           /* $fd138a */
    move.w  FRAME(BITBLT_D_XMAX)(%fp),%d0           /* $fd138c */
    move.w  FRAME(BITBLT_D_YMAX)(%fp),%d1           /* $fd1390 */
    bsr.s   .Ldestination_word                      /* $fd1394 */
    neg.w   %d5                                     /* $fd1396 */
    neg.w   %d7                                     /* $fd1398 */
    bra.s   .Lfast_steps_known                      /* $fd139a */
.Lfast_forwards:
    neg.w   %d4                                     /* $fd139c */
    neg.w   %d6                                     /* $fd139e */
.Lfast_steps_known:
    move.w  %d5,%d2                                 /* $fd13a0 */
    move.w  %d7,%d3                                 /* $fd13a2 */
    movea.w %d4,%a4                                 /* $fd13a4 */
    movea.w %d6,%a5                                 /* $fd13a6 */
    bsr.w   .Ledge_masks                            /* $fd13a8 */
    tst.w   %d2                                     /* $fd13ac */
    bpl.s   .Lfast_masks_known                      /* $fd13ae */
    swap    %d6                                     /* $fd13b0 */
.Lfast_masks_known:
    move.l  %a0,FRAME(BITBLT_S_START)(%fp)          /* $fd13b2 */
    move.l  %a1,FRAME(BITBLT_D_START)(%fp)          /* $fd13b6 */
    move.w  FRAME(BITBLT_B_HT)(%fp),%d7             /* $fd13ba */
    move.w  FRAME(BITBLT_PLANE_CT)(%fp),%d4         /* $fd13be */
    bra.s   .Lfast_planes                           /* $fd13c2 */
.Lfast_row:
    move.w  (%a0),%d0                               /* $fd13c4 */
    move.w  (%a1),%d1                               /* $fd13c6 */
    eor.w   %d1,%d0                                 /* $fd13c8 */
    and.w   %d6,%d0                                 /* $fd13ca */
    eor.w   %d1,%d0                                 /* $fd13cc */
    move.w  %d0,(%a1)                               /* $fd13ce */
    adda.w  %d2,%a0                                 /* $fd13d0 */
    adda.w  %d3,%a1                                 /* $fd13d2 */
.Lfast_middle:
    move.w  (%a0),(%a1)                             /* $fd13d4 */
    adda.w  %d2,%a0                                 /* $fd13d6 */
    adda.w  %d3,%a1                                 /* $fd13d8 */
    dbf     %d5,.Lfast_middle                       /* $fd13da */
    swap    %d6                                     /* $fd13de */
    move.w  (%a0),%d0                               /* $fd13e0 */
    move.w  (%a1),%d1                               /* $fd13e2 */
    eor.w   %d1,%d0                                 /* $fd13e4 */
    and.w   %d6,%d0                                 /* $fd13e6 */
    eor.w   %d1,%d0                                 /* $fd13e8 */
    move.w  %d0,(%a1)                               /* $fd13ea */
    swap    %d6                                     /* $fd13ec */
    adda.w  %a4,%a0                                 /* $fd13ee */
    adda.w  %a5,%a1                                 /* $fd13f0 */
.Lfast_rows:
    move.w  FRAME(BITBLT_MIDDLE_COUNT)(%fp),%d5     /* $fd13f2 */
    dbf     %d7,.Lfast_row                          /* $fd13f6 */
    move.w  FRAME(BITBLT_B_HT)(%fp),%d7             /* $fd13fa */
    movea.l FRAME(BITBLT_S_START)(%fp),%a0          /* $fd13fe */
    movea.l FRAME(BITBLT_D_START)(%fp),%a1          /* $fd1402 */
    adda.w  FRAME(BITBLT_S_NXPL)(%fp),%a0           /* $fd1406 */
    adda.w  FRAME(BITBLT_D_NXPL)(%fp),%a1           /* $fd140a */
    move.l  %a0,FRAME(BITBLT_S_START)(%fp)          /* $fd140e */
    move.l  %a1,FRAME(BITBLT_D_START)(%fp)          /* $fd1412 */
.Lfast_planes:
    dbf     %d4,.Lfast_rows                         /* $fd1416 */
    rts                                             /* $fd141a */

/* ==== $fd1694..$fd19db ==============================================================================
 * The FRAGMENTS. Registers across them: A0 source, A1 destination, D2 / D3 their word steps, D4 the
 * rotate count, D0 the LATCH (the destination word forms in its low half), D1 the CARRY (the last two
 * source words, unrotated), D5 middle words (low) and rows (high), D6 the mask in use (low) and the
 * row's other end's (high), D7 this row's pattern word (low) and the next row's offset (high). */
/* $fd1694 — the pattern row: D7.w = the pattern word at P_ADDR + (offset & P_MASK), the offset
 * stepped by P_NXLN; then the aligner through A5. A6 is borrowed as the base, and put back. */
linea_rom_cpu_blit_ops:
    swap    %d7                                     /* $fd1694 */
    move.w  %d7,%d0                                 /* $fd1696 */
    add.w   FRAME(BITBLT_P_NXLN)(%fp),%d7           /* $fd1698 */
    swap    %d7                                     /* $fd169c */
    and.w   FRAME(BITBLT_P_MASK)(%fp),%d0           /* $fd169e */
    move.l  %fp,%d1                                 /* $fd16a2 */
    movea.l FRAME(BITBLT_P_ADDR)(%fp),%fp           /* $fd16a4 */
    move.w  0(%fp,%d0.w),%d7                        /* $fd16a8 */
    movea.l %d1,%fp                                 /* $fd16ac */
    jmp     (%a5)                                   /* $fd16ae */
/* $fd16b0 / $fd16b8 — one source word, rotated in its word. */
.Lword_rotate_left:
    move.w  (%a0),%d0                               /* $fd16b0 */
    rol.w   %d4,%d0                                 /* $fd16b2 */
    jmp     8(%a2)                                  /* $fd16b4 */
.Lword_rotate_right:
    move.w  (%a0),%d0                               /* $fd16b8 */
    ror.w   %d4,%d0                                 /* $fd16ba */
    jmp     8(%a2)                                  /* $fd16bc */
/* The FIRST fragments: the row's first destination word into D0.w, from two source words or (the
 * `_one` entries) one — paired with the stale latch half the mask then discards. */
.Lfirst_right_latch:
    move.w  (%a0),%d0                               /* $fd16c0 */
    adda.w  %d2,%a0                                 /* $fd16c2 */
    swap    %d0                                     /* $fd16c4 */
.Lfirst_right_latch_one:
    move.w  (%a0),%d0                               /* $fd16c6 */
    swap    %d0                                     /* $fd16c8 */
    move.l  %d0,%d1                                 /* $fd16ca */
    ror.l   %d4,%d0                                 /* $fd16cc */
    jmp     8(%a2)                                  /* $fd16ce */
.Lfirst_left_carry:
    move.w  (%a0),%d0                               /* $fd16d2 */
    adda.w  %d2,%a0                                 /* $fd16d4 */
    swap    %d0                                     /* $fd16d6 */
.Lfirst_left_carry_one:
    move.w  (%a0),%d0                               /* $fd16d8 */
    move.l  %d0,%d1                                 /* $fd16da */
    swap    %d1                                     /* $fd16dc */
    rol.l   %d4,%d0                                 /* $fd16de */
    jmp     8(%a2)                                  /* $fd16e0 */
.Lfirst_right_carry:
    move.w  (%a0),%d0                               /* $fd16e4 */
    adda.w  %d2,%a0                                 /* $fd16e6 */
    swap    %d0                                     /* $fd16e8 */
.Lfirst_right_carry_one:
    move.w  (%a0),%d0                               /* $fd16ea */
    move.l  %d0,%d1                                 /* $fd16ec */
    swap    %d1                                     /* $fd16ee */
    ror.l   %d4,%d0                                 /* $fd16f0 */
    jmp     8(%a2)                                  /* $fd16f2 */
.Lfirst_left_latch:
    move.w  (%a0),%d0                               /* $fd16f6 */
    adda.w  %d2,%a0                                 /* $fd16f8 */
    swap    %d0                                     /* $fd16fa */
.Lfirst_left_latch_one:
    move.w  (%a0),%d0                               /* $fd16fc */
    swap    %d0                                     /* $fd16fe */
    move.l  %d0,%d1                                 /* $fd1700 */
    rol.l   %d4,%d0                                 /* $fd1702 */
    jmp     8(%a2)                                  /* $fd1704 */
/* The NEXT fragments: the next word along, source and destination, paired with the carry. */
.Lnext_right_latch:
    adda.w  %d2,%a0                                 /* $fd1708 */
    adda.w  %d3,%a1                                 /* $fd170a */
    move.l  %d1,%d0                                 /* $fd170c */
    move.w  (%a0),%d0                               /* $fd170e */
    swap    %d0                                     /* $fd1710 */
    move.l  %d0,%d1                                 /* $fd1712 */
    ror.l   %d4,%d0                                 /* $fd1714 */
    jmp     (%a2)                                   /* $fd1716 */
.Lnext_left_carry:
    adda.w  %d2,%a0                                 /* $fd1718 */
    adda.w  %d3,%a1                                 /* $fd171a */
    move.l  %d1,%d0                                 /* $fd171c */
    move.w  (%a0),%d0                               /* $fd171e */
    move.l  %d0,%d1                                 /* $fd1720 */
    swap    %d1                                     /* $fd1722 */
    rol.l   %d4,%d0                                 /* $fd1724 */
    jmp     (%a2)                                   /* $fd1726 */
.Lnext_right_carry:
    adda.w  %d2,%a0                                 /* $fd1728 */
    adda.w  %d3,%a1                                 /* $fd172a */
    move.l  %d1,%d0                                 /* $fd172c */
    move.w  (%a0),%d0                               /* $fd172e */
    move.l  %d0,%d1                                 /* $fd1730 */
    swap    %d1                                     /* $fd1732 */
    ror.l   %d4,%d0                                 /* $fd1734 */
    jmp     (%a2)                                   /* $fd1736 */
.Lnext_left_latch:
    adda.w  %d2,%a0                                 /* $fd1738 */
    adda.w  %d3,%a1                                 /* $fd173a */
    move.l  %d1,%d0                                 /* $fd173c */
    move.w  (%a0),%d0                               /* $fd173e */
    swap    %d0                                     /* $fd1740 */
    move.l  %d0,%d1                                 /* $fd1742 */
    rol.l   %d4,%d0                                 /* $fd1744 */
    jmp     (%a2)                                   /* $fd1746 */
/* The MIDDLE loops (A3): `dbf` round the next fragment; out of it, the last word — one more source
 * word (`_read`) or the rotated latch's other half ($fd1796 `swap d0`) — under the other end's mask. */
.Lmiddle_right_latch_read:
    dbf     %d5,.Lnext_right_latch                  /* $fd1748 */
    adda.w  %d2,%a0                                 /* $fd174c */
    move.l  %d1,%d0                                 /* $fd174e */
    move.w  (%a0),%d0                               /* $fd1750 */
    ror.l   %d4,%d0                                 /* $fd1752 */
    bra.s   .Llast_swapped                          /* $fd1754 */
.Lmiddle_left_carry_read:
    dbf     %d5,.Lnext_left_carry                   /* $fd1756 */
    adda.w  %d2,%a0                                 /* $fd175a */
    move.l  %d1,%d0                                 /* $fd175c */
    move.w  (%a0),%d0                               /* $fd175e */
    rol.l   %d4,%d0                                 /* $fd1760 */
    bra.s   .Llast_word                             /* $fd1762 */
.Lmiddle_right_carry_read:
    dbf     %d5,.Lnext_right_carry                  /* $fd1764 */
    adda.w  %d2,%a0                                 /* $fd1768 */
    move.l  %d1,%d0                                 /* $fd176a */
    move.w  (%a0),%d0                               /* $fd176c */
    ror.l   %d4,%d0                                 /* $fd176e */
    bra.s   .Llast_word                             /* $fd1770 */
.Lmiddle_left_latch_read:
    dbf     %d5,.Lnext_left_latch                   /* $fd1772 */
    adda.w  %d2,%a0                                 /* $fd1776 */
    move.l  %d1,%d0                                 /* $fd1778 */
    move.w  (%a0),%d0                               /* $fd177a */
    rol.l   %d4,%d0                                 /* $fd177c */
    bra.s   .Llast_swapped                          /* $fd177e */
.Lmiddle_right_latch:
    dbf     %d5,.Lnext_right_latch                  /* $fd1780 */
    bra.s   .Llast_swapped                          /* $fd1784 */
.Lmiddle_left_carry:
    dbf     %d5,.Lnext_left_carry                   /* $fd1786 */
    bra.s   .Llast_swapped                          /* $fd178a */
.Lmiddle_right_carry:
    dbf     %d5,.Lnext_right_carry                  /* $fd178c */
    bra.s   .Llast_swapped                          /* $fd1790 */
.Lmiddle_left_latch:
    dbf     %d5,.Lnext_left_latch                   /* $fd1792 */
.Llast_swapped:
    swap    %d0                                     /* $fd1796 */
.Llast_word:
    adda.w  %d3,%a1                                 /* $fd1798 */
    swap    %d6                                     /* $fd179a */
    jmp     22(%a2)                                 /* $fd179c */
/* The row's end: D5 reloaded, the rows counted, both addresses on to the next row (A4 again). */
.Lrow_end:
    swap    %d6                                     /* $fd17a0 */
    move.w  FRAME(BITBLT_MIDDLE_COUNT)(%fp),%d5     /* $fd17a2 */
.Lnext_row:
    swap    %d5                                     /* $fd17a6 */
    subq.w  #1,%d5                                  /* $fd17a8 */
    beq.s   .Lrows_done                             /* $fd17aa */
    swap    %d5                                     /* $fd17ac */
    adda.w  FRAME(BITBLT_S_WRAP)(%fp),%a0           /* $fd17ae */
    adda.w  FRAME(BITBLT_D_WRAP)(%fp),%a1           /* $fd17b2 */
    jmp     (%a4)                                   /* $fd17b6 */
.Lrows_done:
    rts                                             /* $fd17b8 */
/* ...and the no-source rows' fragments. */
.Lfirst_no_source:
    jmp     8(%a2)                                  /* $fd17ba */
.Lnext_no_source:
    adda.w  %d3,%a1                                 /* $fd17be */
    jmp     (%a2)                                   /* $fd17c0 */
.Lmiddle_no_source:
    dbf     %d5,.Lnext_no_source                    /* $fd17c2 */
    adda.w  %d3,%a1                                 /* $fd17c6 */
    swap    %d6                                     /* $fd17c8 */
    jmp     22(%a2)                                 /* $fd17ca */
.Lrow_end_no_source:
    swap    %d6                                     /* $fd17ce */
    move.w  FRAME(BITBLT_MIDDLE_COUNT)(%fp),%d5     /* $fd17d0 */
.Lnext_row_no_source:
    swap    %d5                                     /* $fd17d4 */
    subq.w  #1,%d5                                  /* $fd17d6 */
    beq.s   .Lrows_done                             /* $fd17d8 */
    swap    %d5                                     /* $fd17da */
    adda.w  FRAME(BITBLT_D_WRAP)(%fp),%a1           /* $fd17dc */
    jmp     (%a4)                                   /* $fd17e0 */
/* The SIXTEEN OPS. Each op's entries are at fixed offsets from A2: the middle word at +0, the first
 * word under D6 at +8, the last at +22 (then the row's end); the word before each, `and.w d7,d0`, is the
 * pattern's entry, taken with A2 two lower. */
    and.w   %d7,%d0                                 /* $fd17e2 */
.Lop_zero:
    move.w  #0,(%a1)                                /* $fd17e4 */
    jmp     (%a3)                                   /* $fd17e8 */
    and.w   %d7,%d0                                 /* $fd17ea */
    not.w   %d6                                     /* $fd17ec */
    and.w   %d6,(%a1)                               /* $fd17ee */
    not.w   %d6                                     /* $fd17f0 */
    jmp     (%a3)                                   /* $fd17f2 */
    .word   0x0000                                  /* $fd17f4 */
    .word   0x0000                                  /* $fd17f6 */
    and.w   %d7,%d0                                 /* $fd17f8 */
    not.w   %d6                                     /* $fd17fa */
    and.w   %d6,(%a1)                               /* $fd17fc */
    not.w   %d6                                     /* $fd17fe */
    bra.s   .Lrow_end_no_source                     /* $fd1800 */
    and.w   %d7,%d0                                 /* $fd1802 */
.Lop_s_and_d:
    and.w   %d0,(%a1)                               /* $fd1804 */
    jmp     (%a3)                                   /* $fd1806 */
    .word   0x0000, 0xc047                          /* orib #71,%d0 */     /* $fd1808 */
    not.w   %d6                                     /* $fd180c */
    or.w    %d6,%d0                                 /* $fd180e */
    not.w   %d6                                     /* $fd1810 */
    and.w   %d0,(%a1)                               /* $fd1812 */
    jmp     (%a3)                                   /* $fd1814 */
    .word   0x0000, 0xc047                          /* orib #71,%d0 */     /* $fd1816 */
    not.w   %d6                                     /* $fd181a */
    or.w    %d6,%d0                                 /* $fd181c */
    not.w   %d6                                     /* $fd181e */
    and.w   %d0,(%a1)                               /* $fd1820 */
    bra.w   .Lrow_end                               /* $fd1822 */
    and.w   %d7,%d0                                 /* $fd1826 */
.Lop_s_and_not_d:
    not.w   (%a1)                                   /* $fd1828 */
    and.w   %d0,(%a1)                               /* $fd182a */
    jmp     (%a3)                                   /* $fd182c */
    and.w   %d7,%d0                                 /* $fd182e */
    not.w   %d0                                     /* $fd1830 */
    and.w   %d6,%d0                                 /* $fd1832 */
    or.w    %d0,(%a1)                               /* $fd1834 */
    eor.w   %d6,(%a1)                               /* $fd1836 */
    jmp     (%a3)                                   /* $fd1838 */
    .word   0x0000, 0xc047                          /* orib #71,%d0 */     /* $fd183a */
    not.w   %d0                                     /* $fd183e */
    and.w   %d6,%d0                                 /* $fd1840 */
    or.w    %d0,(%a1)                               /* $fd1842 */
    eor.w   %d6,(%a1)                               /* $fd1844 */
    bra.w   .Lrow_end                               /* $fd1846 */
    and.w   %d7,%d0                                 /* $fd184a */
.Lop_s:
    move.w  %d0,(%a1)                               /* $fd184c */
    jmp     (%a3)                                   /* $fd184e */
    .word   0x0000, 0xc047                          /* orib #71,%d0 */     /* $fd1850 */
    move.w  (%a1),%d1                               /* $fd1854 */
    eor.w   %d1,%d0                                 /* $fd1856 */
    and.w   %d6,%d0                                 /* $fd1858 */
    eor.w   %d1,%d0                                 /* $fd185a */
    move.w  %d0,(%a1)                               /* $fd185c */
    jmp     (%a3)                                   /* $fd185e */
    and.w   %d7,%d0                                 /* $fd1860 */
    move.w  (%a1),%d1                               /* $fd1862 */
    eor.w   %d1,%d0                                 /* $fd1864 */
    and.w   %d6,%d0                                 /* $fd1866 */
    eor.w   %d1,%d0                                 /* $fd1868 */
    move.w  %d0,(%a1)                               /* $fd186a */
    bra.w   .Lrow_end                               /* $fd186c */
    and.w   %d7,%d0                                 /* $fd1870 */
.Lop_not_s_and_d:
    not.w   %d0                                     /* $fd1872 */
    and.w   %d0,(%a1)                               /* $fd1874 */
    jmp     (%a3)                                   /* $fd1876 */
    and.w   %d7,%d0                                 /* $fd1878 */
    and.w   %d6,%d0                                 /* $fd187a */
    not.w   %d0                                     /* $fd187c */
    and.w   %d0,(%a1)                               /* $fd187e */
    jmp     (%a3)                                   /* $fd1880 */
    .word   0x0000, 0x0000                          /* orib #0,%d0 */      /* $fd1882 */
    and.w   %d7,%d0                                 /* $fd1886 */
    and.w   %d6,%d0                                 /* $fd1888 */
    not.w   %d0                                     /* $fd188a */
    and.w   %d0,(%a1)                               /* $fd188c */
    bra.w   .Lrow_end                               /* $fd188e */
.Lop_d:
    and.w   %d7,%d0                                 /* $fd1892 */
.Lop_s_xor_d:
    eor.w   %d0,(%a1)                               /* $fd1894 */
    jmp     (%a3)                                   /* $fd1896 */
    .word   0x0000, 0xc047                          /* orib #71,%d0 */     /* $fd1898 */
    and.w   %d6,%d0                                 /* $fd189c */
    eor.w   %d0,(%a1)                               /* $fd189e */
    jmp     (%a3)                                   /* $fd18a0 */
    .word   0x0000, 0x0000                          /* orib #0,%d0 */      /* $fd18a2 */
    .word   0x0000, 0xc047                          /* orib #71,%d0 */     /* $fd18a6 */
    and.w   %d6,%d0                                 /* $fd18aa */
    eor.w   %d0,(%a1)                               /* $fd18ac */
    bra.w   .Lrow_end                               /* $fd18ae */
    and.w   %d7,%d0                                 /* $fd18b2 */
.Lop_s_or_d:
    or.w    %d0,(%a1)                               /* $fd18b4 */
    jmp     (%a3)                                   /* $fd18b6 */
    .word   0x0000, 0xc047                          /* orib #71,%d0 */     /* $fd18b8 */
    and.w   %d6,%d0                                 /* $fd18bc */
    or.w    %d0,(%a1)                               /* $fd18be */
    jmp     (%a3)                                   /* $fd18c0 */
    .word   0x0000, 0x0000                          /* orib #0,%d0 */      /* $fd18c2 */
    .word   0x0000, 0xc047                          /* orib #71,%d0 */     /* $fd18c6 */
    and.w   %d6,%d0                                 /* $fd18ca */
    or.w    %d0,(%a1)                               /* $fd18cc */
    bra.w   .Lrow_end                               /* $fd18ce */
    and.w   %d7,%d0                                 /* $fd18d2 */
.Lop_nor:
    or.w    %d0,(%a1)                               /* $fd18d4 */
    not.w   (%a1)                                   /* $fd18d6 */
    jmp     (%a3)                                   /* $fd18d8 */
    and.w   %d7,%d0                                 /* $fd18da */
    and.w   %d6,%d0                                 /* $fd18dc */
    or.w    %d0,(%a1)                               /* $fd18de */
    eor.w   %d6,(%a1)                               /* $fd18e0 */
    jmp     (%a3)                                   /* $fd18e2 */
    .word   0x0000, 0x0000                          /* orib #0,%d0 */      /* $fd18e4 */
    and.w   %d7,%d0                                 /* $fd18e8 */
    and.w   %d6,%d0                                 /* $fd18ea */
    or.w    %d0,(%a1)                               /* $fd18ec */
    eor.w   %d6,(%a1)                               /* $fd18ee */
    bra.w   .Lrow_end                               /* $fd18f0 */
    and.w   %d7,%d0                                 /* $fd18f4 */
.Lop_xnor:
    not.w   %d0                                     /* $fd18f6 */
    eor.w   %d0,(%a1)                               /* $fd18f8 */
    jmp     (%a3)                                   /* $fd18fa */
    and.w   %d7,%d0                                 /* $fd18fc */
    and.w   %d6,%d0                                 /* $fd18fe */
    eor.w   %d0,(%a1)                               /* $fd1900 */
    eor.w   %d6,(%a1)                               /* $fd1902 */
    jmp     (%a3)                                   /* $fd1904 */
    .word   0x0000, 0x0000                          /* orib #0,%d0 */      /* $fd1906 */
    and.w   %d7,%d0                                 /* $fd190a */
    and.w   %d6,%d0                                 /* $fd190c */
    eor.w   %d0,(%a1)                               /* $fd190e */
    eor.w   %d6,(%a1)                               /* $fd1910 */
    bra.w   .Lrow_end                               /* $fd1912 */
    and.w   %d7,%d0                                 /* $fd1916 */
.Lop_not_d:
    not.w   (%a1)                                   /* $fd1918 */
    jmp     (%a3)                                   /* $fd191a */
    .word   0x0000, 0xc047                          /* orib #71,%d0 */     /* $fd191c */
    eor.w   %d6,(%a1)                               /* $fd1920 */
    jmp     (%a3)                                   /* $fd1922 */
    .word   0x0000, 0x0000                          /* orib #0,%d0 */      /* $fd1924 */
    .word   0x0000, 0x0000                          /* orib #0,%d0 */      /* $fd1928 */
    and.w   %d7,%d0                                 /* $fd192c */
    eor.w   %d6,(%a1)                               /* $fd192e */
    bra.w   .Lrow_end_no_source                     /* $fd1930 */
    and.w   %d7,%d0                                 /* $fd1934 */
.Lop_s_or_not_d:
    not.w   (%a1)                                   /* $fd1936 */
    or.w    %d0,(%a1)                               /* $fd1938 */
    jmp     (%a3)                                   /* $fd193a */
    and.w   %d7,%d0                                 /* $fd193c */
    eor.w   %d6,(%a1)                               /* $fd193e */
    and.w   %d6,%d0                                 /* $fd1940 */
    or.w    %d0,(%a1)                               /* $fd1942 */
    jmp     (%a3)                                   /* $fd1944 */
    .word   0x0000, 0x0000                          /* orib #0,%d0 */      /* $fd1946 */
    and.w   %d7,%d0                                 /* $fd194a */
    eor.w   %d6,(%a1)                               /* $fd194c */
    and.w   %d6,%d0                                 /* $fd194e */
    or.w    %d0,(%a1)                               /* $fd1950 */
    bra.w   .Lrow_end                               /* $fd1952 */
    and.w   %d7,%d0                                 /* $fd1956 */
.Lop_not_s:
    not.w   %d0                                     /* $fd1958 */
    move.w  %d0,(%a1)                               /* $fd195a */
    jmp     (%a3)                                   /* $fd195c */
    and.w   %d7,%d0                                 /* $fd195e */
    or.w    %d6,(%a1)                               /* $fd1960 */
    and.w   %d6,%d0                                 /* $fd1962 */
    eor.w   %d0,(%a1)                               /* $fd1964 */
    jmp     (%a3)                                   /* $fd1966 */
    .word   0x0000, 0x0000                          /* orib #0,%d0 */      /* $fd1968 */
    and.w   %d7,%d0                                 /* $fd196c */
    or.w    %d6,(%a1)                               /* $fd196e */
    and.w   %d6,%d0                                 /* $fd1970 */
    eor.w   %d0,(%a1)                               /* $fd1972 */
    bra.w   .Lrow_end                               /* $fd1974 */
    and.w   %d7,%d0                                 /* $fd1978 */
.Lop_not_s_or_d:
    not.w   %d0                                     /* $fd197a */
    or.w    %d0,(%a1)                               /* $fd197c */
    jmp     (%a3)                                   /* $fd197e */
    and.w   %d7,%d0                                 /* $fd1980 */
    not.w   %d0                                     /* $fd1982 */
    and.w   %d6,%d0                                 /* $fd1984 */
    or.w    %d0,(%a1)                               /* $fd1986 */
    jmp     (%a3)                                   /* $fd1988 */
    .word   0x0000, 0x0000                          /* orib #0,%d0 */      /* $fd198a */
    and.w   %d7,%d0                                 /* $fd198e */
    not.w   %d0                                     /* $fd1990 */
    and.w   %d6,%d0                                 /* $fd1992 */
    or.w    %d0,(%a1)                               /* $fd1994 */
    bra.w   .Lrow_end                               /* $fd1996 */
    and.w   %d7,%d0                                 /* $fd199a */
.Lop_nand:
    and.w   %d0,(%a1)                               /* $fd199c */
    not.w   (%a1)                                   /* $fd199e */
    jmp     (%a3)                                   /* $fd19a0 */
    and.w   %d7,%d0                                 /* $fd19a2 */
    not.w   %d0                                     /* $fd19a4 */
    eor.w   %d6,(%a1)                               /* $fd19a6 */
    and.w   %d6,%d0                                 /* $fd19a8 */
    or.w    %d0,(%a1)                               /* $fd19aa */
    jmp     (%a3)                                   /* $fd19ac */
    .word   0x0000, 0xc047                          /* orib #71,%d0 */     /* $fd19ae */
    not.w   %d0                                     /* $fd19b2 */
    eor.w   %d6,(%a1)                               /* $fd19b4 */
    and.w   %d6,%d0                                 /* $fd19b6 */
    or.w    %d0,(%a1)                               /* $fd19b8 */
    bra.w   .Lrow_end                               /* $fd19ba */
    and.w   %d7,%d0                                 /* $fd19be */
.Lop_one:
    move.w  #-1,(%a1)                               /* $fd19c0 */
    jmp     (%a3)                                   /* $fd19c4 */
    and.w   %d7,%d0                                 /* $fd19c6 */
    or.w    %d6,(%a1)                               /* $fd19c8 */
    jmp     (%a3)                                   /* $fd19ca */
    .word   0x0000, 0x0000                          /* orib #0,%d0 */      /* $fd19cc */
    .word   0x0000, 0x0000                          /* orib #0,%d0 */      /* $fd19d0 */
    and.w   %d7,%d0                                 /* $fd19d4 */
    or.w    %d6,(%a1)                               /* $fd19d6 */
    bra.w   .Lrow_end_no_source                     /* $fd19d8 */
