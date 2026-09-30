/* fill.S — the polygon and contour-fill layer's HAND-WRITTEN 68000 as the ROM wrote it: the transcription of
 * `src/vdi/fill.c`'s three routines the target build ships because their C measures over Tier 3's 1.10 bar
 * (`include/vdi/transcribed.h` is the table; the user's rule: C first, Tier 1 proves it, then the ROM's own
 * instructions where the C is too slow).
 *
 *   $fca05e..$fca163  $a006 filled_poly: the crossings of Y1, `bsr` to sort_words, the pairs through $a004
 *   $fcfb54..$fcfc4f  fill_span (a `bra` into $a004's patterned entry) and end_pts, the seed colour's run
 *
 * Both are pinned BYTE FOR BYTE (`test_vdi_fill_transcription.py`). Five words differ from the ROM's, each
 * relocated there by name to the exact value it must hold: the displacements of the `bsr`/`bra` into
 * helpers.S's sort_words and raster.S's concat, $a004 and its patterned entry, which measure to where this
 * file's neighbours are linked rather than where the ROM has them. Two `.word` lines spell a `sub.w`/`add.w`
 * of `0(a0)` whose zero displacement gas would drop (`m68k_encodings.h`).
 *
 * The Line-A and VDI RAM they reach is at absolute addresses, as the ROM reaches it (`(<field>).l`).
 */
#include "addrs.h"
#include "m68k_encodings.h"
#include "vdi/linea.h"
#include "vdi/vdi.h"
#include "vdi/fill.h"

    .text

/* ==== $fca05e..$fca163 =============================================================================
 * $a006 — contrl[1] edges of the closed polygon at PTSIN: each crossing of row Y1 (the sign bits of
 * Y1 - y1 and Y1 - y2 differ) appended at $16da as x1 + (2dx(Y1 - y1) / dy, halved away from zero), counted
 * in FILL_INT; then sorted, and each pair through $a004 — x-clipped when CLIP, a pair wholly outside
 * skipped. D0/A1 are saved round each $a004 on the stack. */
    .globl  linea_rom_filled_poly
linea_rom_filled_poly:
    movea.l (LINEA_CONTRL).l,%a0                /* $fca05e */
    move.w  CONTRL_N_PTSIN(%a0),%d0             /* $fca064 */
    subq.w  #1,%d0                              /* $fca068 */
    movea.l (LINEA_PTSIN).l,%a0                 /* $fca06a */
    lea     (VDI_SCRATCH).l,%a1                 /* $fca070 */
    clr.w   (LINEA_GDP_FILL_INT).l              /* $fca076 */
.Lpoly_edge:
    move.w  6(%a0),%d1                          /* $fca07c */
    move.w  2(%a0),%d2                          /* $fca080 */
    sub.w   %d2,%d1                             /* $fca084 */
    beq.s   .Lpoly_next_edge                    /* $fca086 */
    move.w  (LINEA_Y1).l,%d3                    /* $fca088 */
    move.w  %d3,%d4                             /* $fca08e */
    sub.w   %d2,%d4                             /* $fca090 */
    sub.w   6(%a0),%d3                          /* $fca092 */
    move.w  %d4,%d2                             /* $fca096 */
    eor.w   %d3,%d2                             /* $fca098 */
    bpl.s   .Lpoly_next_edge                    /* $fca09a */
    move.w  4(%a0),%d2                          /* $fca09c */
    .word   M68K_SUB_W_D16(M68K_A0, M68K_D2), 0 /* $fca0a0 sub.w 0(%a0),%d2 */
    add.w   %d2,%d2                             /* $fca0a4 */
    muls.w  %d2,%d4                             /* $fca0a6 */
    divs.w  %d1,%d4                             /* $fca0a8 */
    bpl.s   .Lpoly_round_up                     /* $fca0aa */
    neg.w   %d4                                 /* $fca0ac */
    addq.w  #1,%d4                              /* $fca0ae */
    asr.w   #1,%d4                              /* $fca0b0 */
    neg.w   %d4                                 /* $fca0b2 */
    bra.s   .Lpoly_store                        /* $fca0b4 */
.Lpoly_round_up:
    addq.w  #1,%d4                              /* $fca0b6 */
    asr.w   #1,%d4                              /* $fca0b8 */
.Lpoly_store:
    .word   M68K_ADD_W_D16(M68K_A0, M68K_D4), 0 /* $fca0ba add.w 0(%a0),%d4 */
    move.w  %d4,(%a1)+                          /* $fca0be */
    addq.w  #1,(LINEA_GDP_FILL_INT).l           /* $fca0c0 */
.Lpoly_next_edge:
    lea     4(%a0),%a0                          /* $fca0c6 */
    dbf     %d0,.Lpoly_edge                     /* $fca0ca */
    move.w  (LINEA_GDP_FILL_INT).l,%d0          /* $fca0ce */
    bne.s   .Lpoly_sort                         /* $fca0d4 */
    rts                                         /* $fca0d6 */
.Lpoly_sort:
    lea     (VDI_SCRATCH).l,%a0                 /* $fca0d8 */
    bsr.w   vdi_rom_sort_words                  /* $fca0de */
    move.w  (LINEA_GDP_FILL_INT).l,%d0          /* $fca0e2 */
    asr.w   #1,%d0                              /* $fca0e8 */
    subq.w  #1,%d0                              /* $fca0ea */
    tst.w   (LINEA_CLIP).l                      /* $fca0ec */
    bne.s   .Lpoly_clipped_pair                 /* $fca0f2 */
.Lpoly_pair:
    move.w  (%a1)+,(LINEA_X1).l                 /* $fca0f4 */
    move.w  (%a1)+,(LINEA_X2).l                 /* $fca0fa */
    move.w  %d0,-(%sp)                          /* $fca100 */
    move.l  %a1,-(%sp)                          /* $fca102 */
    bsr.w   linea_rom_hline                     /* $fca104 */
    movea.l (%sp)+,%a1                          /* $fca108 */
    move.w  (%sp)+,%d0                          /* $fca10a */
    dbf     %d0,.Lpoly_pair                     /* $fca10c */
    rts                                         /* $fca110 */
.Lpoly_clipped_pair:
    move.w  (%a1)+,(LINEA_X1).l                 /* $fca112 */
    move.w  (%a1)+,(LINEA_X2).l                 /* $fca118 */
    move.w  (LINEA_XMINCL).l,%d1                /* $fca11e */
    move.w  (LINEA_X1).l,%d2                    /* $fca124 */
    move.w  (LINEA_X2).l,%d3                    /* $fca12a */
    cmp.w   %d1,%d2                             /* $fca130 */
    bge.s   .Lpoly_right_end                    /* $fca132 */
    cmp.w   %d1,%d3                             /* $fca134 */
    blt.s   .Lpoly_next_pair                    /* $fca136 */
    move.w  %d1,(LINEA_X1).l                    /* $fca138 */
.Lpoly_right_end:
    move.w  (LINEA_XMAXCL).l,%d1                /* $fca13e */
    cmp.w   %d1,%d3                             /* $fca144 */
    ble.s   .Lpoly_fill_pair                    /* $fca146 */
    cmp.w   %d1,%d2                             /* $fca148 */
    bgt.s   .Lpoly_next_pair                    /* $fca14a */
    move.w  %d1,(LINEA_X2).l                    /* $fca14c */
.Lpoly_fill_pair:
    move.w  %d0,-(%sp)                          /* $fca152 */
    move.l  %a1,-(%sp)                          /* $fca154 */
    bsr.w   linea_rom_hline                     /* $fca156 */
    movea.l (%sp)+,%a1                          /* $fca15a */
    move.w  (%sp)+,%d0                          /* $fca15c */
.Lpoly_next_pair:
    dbf     %d0,.Lpoly_clipped_pair             /* $fca15e */
    rts                                         /* $fca162 */

/* ==== $fcfb54..$fcfc4f =============================================================================
 * fill_span — the Alcyon frame (x1, x2, y) into D4, D6, D5 and A4 = the Line-A base: $a004 from its
 * patterned entry. */
    .globl  linea_rom_fill_span
linea_rom_fill_span:
    movem.w 4(%sp),%d4-%d6                      /* $fcfb54 */
    exg     %d5,%d6                             /* $fcfb5a */
    lea     (LINEA_BASE).l,%a4                  /* $fcfb5c */
    bra.w   linea_rom_hline_patterned           /* $fcfb62 */

/* end_pts — (x, y, &xleft, &xright): the run of (x, y)'s colour, walked right while the colour holds and x
 * is not past XMAXCL, then left to XMINCL; the right end stored first. Each pixel's colour is read LAST
 * plane first into D1 by `sne` / `add.b` / `addx.w`, A3 = the group's bytes, A1 = PLANES - 1 kept for the
 * `dbf`, A2 = the seed's group, A0 = its bit. Answers SEED_TYPE, flipped when the seed's colour (D2) is
 * not SEARCH_COLOR — and 0 for a row outside YMINCL..YMAXCL, which stores nothing. */
    .globl  linea_rom_end_pts
linea_rom_end_pts:
    move.w  6(%sp),%d1                          /* $fcfb66 */
    cmp.w   (LINEA_YMINCL).l,%d1                /* $fcfb6a */
    bmi.w   .Lend_pts_outside                   /* $fcfb70 */
    cmp.w   (LINEA_YMAXCL).l,%d1                /* $fcfb74 */
    bgt.w   .Lend_pts_outside                   /* $fcfb7a */
    movea.l (SYSVAR_V_BAS_AD).l,%a5             /* $fcfb7e */
    move.w  (LINEA_PLANES).l,%d3                /* $fcfb84 */
    movea.w %d3,%a3                             /* $fcfb8a */
    adda.w  %a3,%a3                             /* $fcfb8c */
    subq.w  #1,%d3                              /* $fcfb8e */
    move.w  4(%sp),%d0                          /* $fcfb90 */
    bsr.w   linea_rom_concat                    /* $fcfb94 */
    adda.l  %d1,%a5                             /* $fcfb98 */
    eori.w  #15,%d0                             /* $fcfb9a */
    clr.w   %d1                                 /* $fcfb9e */
    bset    %d0,%d1                             /* $fcfba0 */
    move.w  %d1,%d0                             /* $fcfba2 */
    movea.w %d1,%a0                             /* $fcfba4 */
    movea.w %d3,%a1                             /* $fcfba6 */
    movea.l %a5,%a2                             /* $fcfba8 */
    adda.w  %a3,%a5                             /* $fcfbaa */
    moveq   #0,%d1                              /* $fcfbac */
.Lend_pts_seed_plane:
    move.w  -(%a5),%d4                          /* $fcfbae */
    and.w   %d0,%d4                             /* $fcfbb0 */
    sne     %d4                                 /* $fcfbb2 */
    add.b   %d4,%d4                             /* $fcfbb4 */
    addx.w  %d1,%d1                             /* $fcfbb6 */
    dbf     %d3,.Lend_pts_seed_plane            /* $fcfbb8 */
    move.w  %a1,%d3                             /* $fcfbbc */
    move.w  4(%sp),%d7                          /* $fcfbbe */
    move.w  (LINEA_XMAXCL).l,%d6                /* $fcfbc2 */
    move.w  %d1,%d2                             /* $fcfbc8 */
.Lend_pts_right:
    cmp.w   %d1,%d2                             /* $fcfbca */
    bne.s   .Lend_pts_right_end                 /* $fcfbcc */
    cmp.w   %d6,%d7                             /* $fcfbce */
    bgt.s   .Lend_pts_right_end                 /* $fcfbd0 */
    moveq   #0,%d1                              /* $fcfbd2 */
    addq.w  #1,%d7                              /* $fcfbd4 */
    ror.w   #1,%d0                              /* $fcfbd6 */
    bcc.s   .Lend_pts_right_same_group          /* $fcfbd8 */
    adda.w  %a3,%a5                             /* $fcfbda */
.Lend_pts_right_same_group:
    adda.w  %a3,%a5                             /* $fcfbdc */
.Lend_pts_right_plane:
    move.w  -(%a5),%d4                          /* $fcfbde */
    and.w   %d0,%d4                             /* $fcfbe0 */
    sne     %d4                                 /* $fcfbe2 */
    add.b   %d4,%d4                             /* $fcfbe4 */
    addx.w  %d1,%d1                             /* $fcfbe6 */
    dbf     %d3,.Lend_pts_right_plane           /* $fcfbe8 */
    move.w  %a1,%d3                             /* $fcfbec */
    bra.s   .Lend_pts_right                     /* $fcfbee */
.Lend_pts_right_end:
    movea.l %a2,%a5                             /* $fcfbf0 */
    movea.l 12(%sp),%a4                         /* $fcfbf2 */
    subq.w  #1,%d7                              /* $fcfbf6 */
    move.w  %d7,(%a4)                           /* $fcfbf8 */
    move.w  4(%sp),%d7                          /* $fcfbfa */
    move.w  (LINEA_XMINCL).l,%d6                /* $fcfbfe */
    move.w  %a0,%d0                             /* $fcfc04 */
    move.w  %d2,%d1                             /* $fcfc06 */
.Lend_pts_left:
    cmp.w   %d1,%d2                             /* $fcfc08 */
    bne.s   .Lend_pts_left_end                  /* $fcfc0a */
    cmp.w   %d6,%d7                             /* $fcfc0c */
    blt.s   .Lend_pts_left_end                  /* $fcfc0e */
    moveq   #0,%d1                              /* $fcfc10 */
    subq.w  #1,%d7                              /* $fcfc12 */
    rol.w   #1,%d0                              /* $fcfc14 */
    bcs.s   .Lend_pts_left_plane                /* $fcfc16 */
    adda.w  %a3,%a5                             /* $fcfc18 */
.Lend_pts_left_plane:
    move.w  -(%a5),%d4                          /* $fcfc1a */
    and.w   %d0,%d4                             /* $fcfc1c */
    sne     %d4                                 /* $fcfc1e */
    add.b   %d4,%d4                             /* $fcfc20 */
    addx.w  %d1,%d1                             /* $fcfc22 */
    dbf     %d3,.Lend_pts_left_plane            /* $fcfc24 */
    move.w  %a1,%d3                             /* $fcfc28 */
    bra.s   .Lend_pts_left                      /* $fcfc2a */
.Lend_pts_left_end:
    addq.w  #1,%d7                              /* $fcfc2c */
    movea.l 8(%sp),%a4                          /* $fcfc2e */
    move.w  %d7,(%a4)                           /* $fcfc32 */
    move.w  (VDI_FILL_SEED_TYPE).l,%d0          /* $fcfc34 */
    cmp.w   (VDI_FILL_SEARCH_COLOR).l,%d2       /* $fcfc3a */
    beq.s   .Lend_pts_answer                    /* $fcfc40 */
    eori.w  #1,%d0                              /* $fcfc42 */
.Lend_pts_answer:
    eori.w  #0,%d0                              /* $fcfc46 */
    rts                                         /* $fcfc4a */
.Lend_pts_outside:
    moveq   #0,%d0                              /* $fcfc4c */
    rts                                         /* $fcfc4e */
