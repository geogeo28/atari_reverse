/* raster.S — the Line-A pixel / scanline primitives and their CPU bodies AS THE ROM WROTE THEM: the
 * TRANSCRIPTION of `src/vdi/raster.c`'s routines the target build ships (the user's rule for the hand-
 * written 68000: C first, and where the C measures over Tier 3's 1.10 bar, the ROM's own instructions;
 * `include/vdi/transcribed.h` is the table that says so, entry by entry, with each one's registers).
 *
 * WHY THIS IS ASSEMBLY. The C is the reconstruction — Tier 1 proves it against the ROM over every arm —
 * and it is two to three times the ROM's cycles here (STATUS.md has the rows): these are hand-written
 * loops whose every trick is a register the compiler cannot name — a write-mode arm reached by
 * `jmp (a5)` through a PC-relative table, a Bresenham that runs CODE IT BUILT ON THE STACK
 * (`linea_rom_line_plane_words` writes one `and.w d0,(a5)+` / `or.w d1,(a5)+` per plane and a
 * `jmp (a3)`), a span count spent by `subq.w #1 / bcs` twice before a `dbf`. So the shipped routine is
 * the ROM's own sequence, and it is proved two ways that need no C:
 *
 *   * BYTE FOR BYTE — `test_vdi_raster_transcription.py` reads the assembled words back out of the
 *     cross-compiled blob and compares them with the ROM's, region by region (`vdi.assert_transcribed`).
 *     Six references differ, each RELOCATED there by name and pinned to the exact value it must hold:
 *     five displacements of a `bsr`/`bcc` from one region into another, which measure to where this file
 *     puts the other region rather than where the ROM does, and $a005's absolute `lea` of the fringe
 *     table, which names THIS file's copy of it ($fcfca4) so the transcription reads no ROM table.
 *   * BY BEHAVIOUR — every registered case, run through Tier 3's TRANSCRIPTION relation
 *     (`RomBench.measure_transcription`): the same image, the WHOLE register file and the same chip
 *     traffic as the ROM, entered through the same staged caller.
 *
 * THE FIVE REGIONS are the ROM's, in its order, each contiguous with its own tables so that every
 * PC-relative reference and every table offset assembles to the ROM's own word:
 *
 *   $fca1b8..$fca209  concat, its shift table, $a003's front end
 *   $fca2e0..$fca5c9  $a003's horizontal and diagonal arms, the octant table, line_plane_words, the eight
 *                     Bresenham loops, the blitter's (HOP, OP) table (data no CPU routine reads, kept so
 *                     the fringe table and $a004 sit where the ROM's do), the fringe table, $a004
 *   $fcface..$fcfb53  $a001 put_pixel, $a002 get_pixel
 *   $fcfc50..$fcfccb  $a005's clip-miss store and front end
 *   $fd19dc..$fd1cc3  the CPU bodies of vectors 7, 8 and 6, and the four span arms the last two share
 *
 * $fca20a..$fca2df between the first two is the BLITTER vertical line, deferred with the rest of the
 * blitter set (STATUS.md, "Not reconstructed"). The front ends reach their bodies through the drawing
 * vectors exactly as the ROM does (`move.l LINEA_VECTOR_*,a5 / jmp (a5)`), so a shipped ROM that points
 * those vectors at `linea_rom_cpu_*` runs this file end to end.
 *
 * FIFTEEN `.word` LINES spell instructions GNU as would encode differently — `and.w`/`cmp.w #imm,Dn` in
 * the register form, and a `move.w 0(An),Dn` whose zero displacement gas would drop — as the ROM's own
 * words (`m68k_encodings.h`, the one spelling policy every transcription follows). Each carries the
 * instruction in its comment.
 *
 * Every line carries the ROM address it transcribes. `LA(field)` is a Line-A field's displacement from
 * the base in A4 (A2 in the rectangle's routines) — the published layout's own spelling.
 */
#include "addrs.h"
#include "m68k_encodings.h"
#include "vdi/linea.h"
#include "vdi/raster.h"

#define LA(field) ((field) - LINEA_BASE)
/* The vertical body's table holds one longword per write mode, so WRT_MODE `lsl.w #2` ($fd1a34) is the
 * arm's offset — and $fd1a36 compares it with the XOR arm's to take the XOR-without-LSTLIN shortening. */
#define RASTER_VLINE_XOR_ARM (RASTER_MODE_XOR << 2)

    .text

/* ==== $fca1b8..$fca209 =============================================================================
 * concat — (x, y) in D0/D1 -> D1 = y * BYTES_LIN + (x & ~15) >> SHIFT[PLANES], D0.w = x & 15. D2/D3 are
 * saved as WORDS, so D2's high word comes back holding x's sign (`ext.l`). The shift table's index 0 is
 * the low byte of the `rts` itself: only 1, 2, 4 and 8 planes come out right. */
    .globl  linea_rom_concat
linea_rom_concat:
    move.w  %d2,-(%sp)                          /* $fca1b8 */
    move.w  %d3,-(%sp)                          /* $fca1ba */
    muls.w  (LINEA_BYTES_LIN).l,%d1             /* $fca1bc */
    move.w  (LINEA_PLANES).l,%d3                /* $fca1c2 */
    move.b  .Lconcat_shift_table-1(%pc,%d3.w),%d3/* $fca1c8 */
    move.w  %d0,%d2                             /* $fca1cc */
    ext.l   %d2                                 /* $fca1ce */
    .word   M68K_AND_W_IMMEDIATE(2), -16        /* $fca1d0 and.w #-16,%d2 */
    asr.w   %d3,%d2                             /* $fca1d4 */
    add.l   %d2,%d1                             /* $fca1d6 */
    .word   M68K_AND_W_IMMEDIATE(0), 15         /* $fca1d8 and.w #15,%d0 */
    move.w  (%sp)+,%d3                          /* $fca1dc */
    move.w  (%sp)+,%d2                          /* $fca1de */
    rts                                         /* $fca1e0 */
.Lconcat_shift_table:
/* $fca1e2 */
    .byte   3, 2, 0, 1, 0, 0, 0, 0

/* $a003 line — X1,Y1..X2,Y2 into D4-D7 with D0 = 2 (the XOR mode the arms compare WRT_MODE with):
 * Y1 = Y2 the horizontal arm, X1 = X2 vector 7's vertical body, anything else the diagonal arm. */
    .globl  linea_rom_line
linea_rom_line:
    lea     (LINEA_BASE).l,%a4                  /* $fca1ea */
    moveq   #2,%d0                              /* $fca1f0 */
    movem.w LA(LINEA_X1)(%a4),%d4-%d7           /* $fca1f2 */
    cmp.w   %d5,%d7                             /* $fca1f8 */
    beq.w   .Lline_horizontal                   /* $fca1fa */
    cmp.w   %d4,%d6                             /* $fca1fe */
    bne.w   .Lline_diagonal                     /* $fca200 */
    movea.l LA(LINEA_VECTOR_VLINE)(%a4),%a5     /* $fca204 */
    jmp     (%a5)                               /* $fca208 */

/* ==== $fca2e0..$fca5c9 =============================================================================
 * The HORIZONTAL arm: XOR without LSTLIN moves X2 one toward X1 and stores it; the span goes through
 * $a004's span entry with A0 = &LN_MASK and a stride of 0 — the style word itself, unaligned, is the
 * pattern — and LN_MASK is rotated by the pixel count afterwards. */
.Lline_horizontal:
    cmp.w   LA(LINEA_WRT_MODE)(%a4),%d0         /* $fca2e0 */
    bne.s   .Lhorizontal_ordered                            /* $fca2e4 */
    tst.w   LA(LINEA_LSTLIN)(%a4)               /* $fca2e6 */
    bne.s   .Lhorizontal_ordered                            /* $fca2ea */
    cmp.w   %d4,%d6                             /* $fca2ec */
    beq.s   .Lhorizontal_ordered                            /* $fca2ee */
    blt.s   .Lhorizontal_nearer                            /* $fca2f0 */
    subq.w  #2,%d6                              /* $fca2f2 */
.Lhorizontal_nearer:
    addq.w  #1,%d6                              /* $fca2f4 */
    move.w  %d6,LA(LINEA_X2)(%a4)               /* $fca2f6 */
.Lhorizontal_ordered:
    cmp.w   %d4,%d6                             /* $fca2fa */
    bge.s   .Lhorizontal_from_left                            /* $fca2fc */
    exg     %d4,%d6                             /* $fca2fe */
.Lhorizontal_from_left:
    move.w  %d6,%d1                             /* $fca300 */
    sub.w   %d4,%d1                             /* $fca302 */
    addq.w  #1,%d1                              /* $fca304 */
    .word   M68K_AND_W_IMMEDIATE(1), 15         /* $fca306 and.w #15,%d1 */
    lea     LA(LINEA_LN_MASK)(%a4),%a0          /* $fca30a */
    clr.w   %d0                                 /* $fca30e */
    move.w  %d1,-(%sp)                          /* $fca310 */
    bsr.w   linea_rom_hline_span                /* $fca312 */
    move.w  (%sp)+,%d1                          /* $fca316 */
    move.w  (%a0),%d0                           /* $fca318 */
    rol.w   %d1,%d0                             /* $fca31a */
    move.w  %d0,(%a0)                           /* $fca31c */
    rts                                         /* $fca31e */

/* The DIAGONAL arm — a Bresenham from the left end. D3 = planes * 2, A0 = the pixel's group, D1/D0 =
 * its bit and the bit's complement, A1 = +-WIDTH (the y step); then D7 = the major axis, D4 = the error,
 * D5 / D6 = its straight and diagonal increments. A5 = (x-major ? 16 : 0) + WRT_MODE * 4 indexes the
 * octant table's PAIR: the loop to `jsr`, and A3 = where the per-plane code returns to — with A4 = A3 -
 * planes * 2, the entry into the unrolled `and.w d0,(a5)+` run that clears the pixel in every plane.
 * LN_MASK is stored rotated past the pixels BEFORE any is drawn; D2 holds the unrotated style. */
.Lline_diagonal:
    lea     -20(%sp),%sp                        /* $fca320 */
    .word   M68K_MOVE_W_D16(4, 3), LA(LINEA_PLANES) /* $fca324 move.w LA(LINEA_PLANES)(%a4),%d3 */
    .word   M68K_CMP_W_IMMEDIATE(3), RASTER_LINE_PLANES_MAX /* $fca328 cmp.w #8,%d3 */
    bhi.w   .Ldiagonal_done                     /* $fca32c */
    cmp.w   LA(LINEA_WRT_MODE)(%a4),%d0         /* $fca330 */
    beq.s   .Ldiagonal_built                            /* $fca334 */
    movea.l %sp,%a2                             /* $fca336 */
    bsr.w   linea_rom_line_plane_words          /* $fca338 */
.Ldiagonal_built:
    cmp.w   %d4,%d6                             /* $fca33c */
    bge.s   .Ldiagonal_from_left                            /* $fca33e */
    exg     %d4,%d6                             /* $fca340 */
    exg     %d5,%d7                             /* $fca342 */
.Ldiagonal_from_left:
    sub.w   %d4,%d6                             /* $fca344 */
    moveq   #0,%d1                              /* $fca346 */
    movea.l %d1,%a5                             /* $fca348 */
    move.w  %d4,%d0                             /* $fca34a */
    not.w   %d0                                 /* $fca34c */
    .word   M68K_AND_W_IMMEDIATE(0), 15         /* $fca34e and.w #15,%d0 */
    bset    %d0,%d1                             /* $fca352 */
    movea.l (SYSVAR_V_BAS_AD).l,%a0             /* $fca354 */
    .word   M68K_MOVE_W_D16(4, 3), LA(LINEA_PLANES) /* $fca35a move.w LA(LINEA_PLANES)(%a4),%d3 */
    add.w   %d3,%d3                             /* $fca35e */
    move.w  LA(LINEA_BYTES_LIN)(%a4),%d2        /* $fca360 */
    muls.w  %d5,%d2                             /* $fca364 */
    adda.l  %d2,%a0                             /* $fca366 */
    asr.w   #4,%d4                              /* $fca368 */
    muls.w  %d3,%d4                             /* $fca36a */
    adda.l  %d4,%a0                             /* $fca36c */
    move.w  LA(LINEA_WIDTH)(%a4),%d0            /* $fca36e */
    sub.w   %d5,%d7                             /* $fca372 */
    bge.s   .Ldiagonal_downward                            /* $fca374 */
    neg.w   %d7                                 /* $fca376 */
    neg.w   %d0                                 /* $fca378 */
.Ldiagonal_downward:
    movea.w %d0,%a1                             /* $fca37a */
    cmp.w   %d6,%d7                             /* $fca37c */
    bgt.s   .Ldiagonal_major_chosen                            /* $fca37e */
    exg     %d6,%d7                             /* $fca380 */
    lea     16(%a5),%a5                         /* $fca382 */
.Ldiagonal_major_chosen:
    move.w  %d6,%d4                             /* $fca386 */
    add.w   %d4,%d4                             /* $fca388 */
    move.w  %d4,%d5                             /* $fca38a */
    sub.w   %d7,%d4                             /* $fca38c */
    move.w  %d4,%d6                             /* $fca38e */
    sub.w   %d7,%d6                             /* $fca390 */
    move.w  LA(LINEA_WRT_MODE)(%a4),%d0         /* $fca392 */
    lsl.w   #2,%d0                              /* $fca396 */
    adda.w  %d0,%a5                             /* $fca398 */
    subq.w  #8,%d0                              /* $fca39a */
    bne.s   .Ldiagonal_count_ready                            /* $fca39c */
    tst.w   LA(LINEA_LSTLIN)(%a4)               /* $fca39e */
    bne.s   .Ldiagonal_count_ready                            /* $fca3a2 */
    subq.w  #1,%d7                              /* $fca3a4 */
.Ldiagonal_count_ready:
    lea     LA(LINEA_LN_MASK)(%a4),%a3          /* $fca3a6 */
    move.w  (%a3),%d0                           /* $fca3aa */
    move.w  %d7,%d2                             /* $fca3ac */
    addq.w  #1,%d2                              /* $fca3ae */
    .word   M68K_AND_W_IMMEDIATE(2), 15         /* $fca3b0 and.w #15,%d2 */
    rol.w   %d2,%d0                             /* $fca3b4 */
    move.w  (%a3),%d2                           /* $fca3b6 */
    move.w  %d0,(%a3)                           /* $fca3b8 */
    move.w  %d1,%d0                             /* $fca3ba */
    not.w   %d0                                 /* $fca3bc */
    lea     .Loctant_table(%pc,%a5.w),%a5       /* $fca3be */
    movea.l %a5,%a3                             /* $fca3c2 */
    adda.w  (%a5)+,%a3                          /* $fca3c4 */
    movea.l %a3,%a4                             /* $fca3c6 */
    suba.w  %d3,%a4                             /* $fca3c8 */
    adda.w  (%a5),%a5                           /* $fca3ca */
    jsr     (%a5)                               /* $fca3cc */
.Ldiagonal_done:
    lea     20(%sp),%sp                         /* $fca3ce */
    rts                                         /* $fca3d2 */

/* The octant table: a (loop, return-point) PAIR per write mode, y-major first and x-major 16 bytes on,
 * each word relative to itself. REVERSE is TRANSPARENT entered one instruction early, at its `not.w d2`. */
.Loctant_table:
/* $fca3d4 */
    .word   .Ly_major_replace_step - .
    .word   .Ly_major_replace - .
    .word   .Ly_major_transparent_step - .
    .word   .Ly_major_transparent - .
    .word   .Ly_major_xor_step - .
    .word   .Ly_major_xor - .
    .word   .Ly_major_transparent_step - .
    .word   .Ly_major_reverse - .
    .word   .Lx_major_replace_step - .
    .word   .Lx_major_replace - .
    .word   .Lx_major_transparent_step - .
    .word   .Lx_major_transparent - .
    .word   .Lx_major_xor_step - .
    .word   .Lx_major_xor - .
    .word   .Lx_major_transparent_step - .
    .word   .Lx_major_reverse - .

/* line_plane_words — D3 = planes, A2 = the buffer (the diagonal's and the vertical body's 20 bytes of
 * STACK): per plane, `or.w d1,(a5)+` where COLBIT is set and `and.w d0,(a5)+` where it is not, then
 * `jmp (a3)`. The two line bodies run this code, one pass per styled pixel. */
    .globl  linea_rom_line_plane_words
linea_rom_line_plane_words:
    subq.w  #1,%d3                              /* $fca3f4 */
    movem.w .Lplane_opcodes(%pc),%d0-%d2        /* $fca3f6 */
    movea.l %a2,%a0                             /* $fca3fc */
    lea     LA(LINEA_COLBIT0)(%a4),%a1          /* $fca3fe */
.Lplane_word:
    tst.w   (%a1)+                              /* $fca402 */
    bne.s   .Lplane_word_set                            /* $fca404 */
    move.w  %d0,(%a0)+                          /* $fca406 */
    dbf     %d3,.Lplane_word                        /* $fca408 */
    move.w  %d2,(%a0)+                          /* $fca40c */
    rts                                         /* $fca40e */
.Lplane_word_set:
    move.w  %d1,(%a0)+                          /* $fca410 */
    dbf     %d3,.Lplane_word                        /* $fca412 */
    move.w  %d2,(%a0)+                          /* $fca416 */
    rts                                         /* $fca418 */
.Lplane_opcodes:
/* $fca41a */
    and.w   %d0,(%a5)+
    or.w    %d1,(%a5)+
    jmp     (%a3)

/* The eight loops: y-major (A0 += A1 every pixel, x when the error is not negative) and x-major (the
 * reverse), each by write mode. A pixel whose style bit is set runs the stack code (`jmp (a2)`); REPLACE
 * clears one whose bit is not (`jmp (a4)`); XOR's set bit runs an unrolled `eor.w d1,(a5)+` instead. */
.Ly_major_replace:
    rol.w   #1,%d2                              /* $fca420 */
    bcc.s   .Ly_major_replace_clear                            /* $fca422 */
    movea.l %a0,%a5                             /* $fca424 */
    jmp     (%a2)                               /* $fca426 */
.Ly_major_replace_clear:
    movea.l %a0,%a5                             /* $fca428 */
    jmp     (%a4)                               /* $fca42a */
    and.w   %d0,(%a5)+                          /* $fca42c */
    and.w   %d0,(%a5)+                          /* $fca42e */
    and.w   %d0,(%a5)+                          /* $fca430 */
    and.w   %d0,(%a5)+                          /* $fca432 */
    and.w   %d0,(%a5)+                          /* $fca434 */
    and.w   %d0,(%a5)+                          /* $fca436 */
    and.w   %d0,(%a5)+                          /* $fca438 */
    and.w   %d0,(%a5)+                          /* $fca43a */
.Ly_major_replace_step:
    adda.w  %a1,%a0                             /* $fca43c */
    tst.w   %d4                                 /* $fca43e */
    bmi.s   .Ly_major_replace_straight                            /* $fca440 */
    ror.w   #1,%d0                              /* $fca442 */
    ror.w   #1,%d1                              /* $fca444 */
    bcc.s   .Ly_major_replace_error                            /* $fca446 */
    adda.w  %d3,%a0                             /* $fca448 */
.Ly_major_replace_error:
    add.w   %d6,%d4                             /* $fca44a */
    dbf     %d7,.Ly_major_replace                        /* $fca44c */
    rts                                         /* $fca450 */
.Ly_major_replace_straight:
    add.w   %d5,%d4                             /* $fca452 */
    dbf     %d7,.Ly_major_replace                        /* $fca454 */
    rts                                         /* $fca458 */
.Ly_major_reverse:
    not.w   %d2                                 /* $fca45a */
.Ly_major_transparent:
    rol.w   #1,%d2                              /* $fca45c */
    bcc.s   .Ly_major_transparent_step                            /* $fca45e */
    movea.l %a0,%a5                             /* $fca460 */
    jmp     (%a2)                               /* $fca462 */
.Ly_major_transparent_step:
    adda.w  %a1,%a0                             /* $fca464 */
    tst.w   %d4                                 /* $fca466 */
    bmi.s   .Ly_major_transparent_straight                            /* $fca468 */
    ror.w   #1,%d0                              /* $fca46a */
    ror.w   #1,%d1                              /* $fca46c */
    bcc.s   .Ly_major_transparent_error                            /* $fca46e */
    adda.w  %d3,%a0                             /* $fca470 */
.Ly_major_transparent_error:
    add.w   %d6,%d4                             /* $fca472 */
    dbf     %d7,.Ly_major_transparent                        /* $fca474 */
    rts                                         /* $fca478 */
.Ly_major_transparent_straight:
    add.w   %d5,%d4                             /* $fca47a */
    dbf     %d7,.Ly_major_transparent                        /* $fca47c */
    rts                                         /* $fca480 */
.Ly_major_xor:
    rol.w   #1,%d2                              /* $fca482 */
    bcc.s   .Ly_major_xor_step                            /* $fca484 */
    movea.l %a0,%a5                             /* $fca486 */
    jmp     (%a4)                               /* $fca488 */
    eor.w   %d1,(%a5)+                          /* $fca48a */
    eor.w   %d1,(%a5)+                          /* $fca48c */
    eor.w   %d1,(%a5)+                          /* $fca48e */
    eor.w   %d1,(%a5)+                          /* $fca490 */
    eor.w   %d1,(%a5)+                          /* $fca492 */
    eor.w   %d1,(%a5)+                          /* $fca494 */
    eor.w   %d1,(%a5)+                          /* $fca496 */
    eor.w   %d1,(%a5)+                          /* $fca498 */
.Ly_major_xor_step:
    adda.w  %a1,%a0                             /* $fca49a */
    tst.w   %d4                                 /* $fca49c */
    bmi.s   .Ly_major_xor_straight                            /* $fca49e */
    ror.w   #1,%d1                              /* $fca4a0 */
    bcc.s   .Ly_major_xor_error                            /* $fca4a2 */
    adda.w  %d3,%a0                             /* $fca4a4 */
.Ly_major_xor_error:
    add.w   %d6,%d4                             /* $fca4a6 */
    dbf     %d7,.Ly_major_xor                        /* $fca4a8 */
    rts                                         /* $fca4ac */
.Ly_major_xor_straight:
    add.w   %d5,%d4                             /* $fca4ae */
    dbf     %d7,.Ly_major_xor                        /* $fca4b0 */
    rts                                         /* $fca4b4 */
.Lx_major_replace:
    rol.w   #1,%d2                              /* $fca4b6 */
    bcc.s   .Lx_major_replace_clear                            /* $fca4b8 */
    movea.l %a0,%a5                             /* $fca4ba */
    jmp     (%a2)                               /* $fca4bc */
.Lx_major_replace_clear:
    movea.l %a0,%a5                             /* $fca4be */
    jmp     (%a4)                               /* $fca4c0 */
    and.w   %d0,(%a5)+                          /* $fca4c2 */
    and.w   %d0,(%a5)+                          /* $fca4c4 */
    and.w   %d0,(%a5)+                          /* $fca4c6 */
    and.w   %d0,(%a5)+                          /* $fca4c8 */
    and.w   %d0,(%a5)+                          /* $fca4ca */
    and.w   %d0,(%a5)+                          /* $fca4cc */
    and.w   %d0,(%a5)+                          /* $fca4ce */
    and.w   %d0,(%a5)+                          /* $fca4d0 */
.Lx_major_replace_step:
    ror.w   #1,%d0                              /* $fca4d2 */
    ror.w   #1,%d1                              /* $fca4d4 */
    bcc.s   .Lx_major_replace_error                            /* $fca4d6 */
    adda.w  %d3,%a0                             /* $fca4d8 */
.Lx_major_replace_error:
    tst.w   %d4                                 /* $fca4da */
    bmi.s   .Lx_major_replace_straight                            /* $fca4dc */
    add.w   %d6,%d4                             /* $fca4de */
    adda.w  %a1,%a0                             /* $fca4e0 */
    dbf     %d7,.Lx_major_replace                        /* $fca4e2 */
    rts                                         /* $fca4e6 */
.Lx_major_replace_straight:
    add.w   %d5,%d4                             /* $fca4e8 */
    dbf     %d7,.Lx_major_replace                        /* $fca4ea */
    rts                                         /* $fca4ee */
.Lx_major_reverse:
    not.w   %d2                                 /* $fca4f0 */
.Lx_major_transparent:
    rol.w   #1,%d2                              /* $fca4f2 */
    bcc.s   .Lx_major_transparent_step                            /* $fca4f4 */
    movea.l %a0,%a5                             /* $fca4f6 */
    jmp     (%a2)                               /* $fca4f8 */
.Lx_major_transparent_step:
    ror.w   #1,%d0                              /* $fca4fa */
    ror.w   #1,%d1                              /* $fca4fc */
    bcc.s   .Lx_major_transparent_error                            /* $fca4fe */
    adda.w  %d3,%a0                             /* $fca500 */
.Lx_major_transparent_error:
    tst.w   %d4                                 /* $fca502 */
    bmi.s   .Lx_major_transparent_straight                            /* $fca504 */
    add.w   %d6,%d4                             /* $fca506 */
    adda.w  %a1,%a0                             /* $fca508 */
    dbf     %d7,.Lx_major_transparent                        /* $fca50a */
    rts                                         /* $fca50e */
.Lx_major_transparent_straight:
    add.w   %d5,%d4                             /* $fca510 */
    dbf     %d7,.Lx_major_transparent                        /* $fca512 */
    rts                                         /* $fca516 */
.Lx_major_xor:
    rol.w   #1,%d2                              /* $fca518 */
    bcc.s   .Lx_major_xor_step                            /* $fca51a */
    movea.l %a0,%a5                             /* $fca51c */
    jmp     (%a4)                               /* $fca51e */
    eor.w   %d1,(%a5)+                          /* $fca520 */
    eor.w   %d1,(%a5)+                          /* $fca522 */
    eor.w   %d1,(%a5)+                          /* $fca524 */
    eor.w   %d1,(%a5)+                          /* $fca526 */
    eor.w   %d1,(%a5)+                          /* $fca528 */
    eor.w   %d1,(%a5)+                          /* $fca52a */
    eor.w   %d1,(%a5)+                          /* $fca52c */
    eor.w   %d1,(%a5)+                          /* $fca52e */
.Lx_major_xor_step:
    ror.w   #1,%d1                              /* $fca530 */
    bcc.s   .Lx_major_xor_error                            /* $fca532 */
    adda.w  %d3,%a0                             /* $fca534 */
.Lx_major_xor_error:
    tst.w   %d4                                 /* $fca536 */
    bmi.s   .Lx_major_xor_straight                            /* $fca538 */
    add.w   %d6,%d4                             /* $fca53a */
    adda.w  %a1,%a0                             /* $fca53c */
    dbf     %d7,.Lx_major_xor                        /* $fca53e */
    rts                                         /* $fca542 */
.Lx_major_xor_straight:
    add.w   %d5,%d4                             /* $fca544 */
    dbf     %d7,.Lx_major_xor                        /* $fca546 */
    rts                                         /* $fca54a */

/* The BLITTER's (HOP, OP) table, read only by the deferred blitter bodies ($fca288, $fca610, $fcfd14) —
 * transcribed as data so the fringe table and $a004 sit where the ROM's do. */
.Lblitter_op_table:
/* $fca54c */
    .word   0x0100, 0x0103, 0x0104, 0x0107
    .word   0x0106, 0x0106, 0x0101, 0x010d
/* The fringe masks, $ffff >> n for n = 0..16. */
.Lfringe_table:
/* $fca55c */
    .word   0xffff, 0x7fff, 0x3fff, 0x1fff
    .word   0x0fff, 0x07ff, 0x03ff, 0x01ff
    .word   0x00ff, 0x007f, 0x003f, 0x001f
    .word   0x000f, 0x0007, 0x0003, 0x0001
    .word   0x0000

/* $a004 hline, and the two entries other routines jump into partway: $fca58a with D4/D5/D6 = x1/y/x2
 * (the contour fill), and $fca5a2 with A0 = the pattern word and D0 = its plane stride as well ($a003's
 * horizontal arm). They leave D1 = the left group, D2 = the groups past it, D4/D6 = the fringe masks
 * (ANDed into D4 inside one group) and jump through vector 8. */
    .globl  linea_rom_hline
linea_rom_hline:
    lea     (LINEA_BASE).l,%a4                  /* $fca57e */
    movem.w LA(LINEA_X1)(%a4),%d4-%d6           /* $fca584 */
    .globl  linea_rom_hline_patterned
linea_rom_hline_patterned:
    move.w  %d5,%d0                             /* $fca58a */
    and.w   LA(LINEA_PATMSK)(%a4),%d0           /* $fca58c */
    add.w   %d0,%d0                             /* $fca590 */
    movea.l LA(LINEA_PATPTR)(%a4),%a0           /* $fca592 */
    adda.w  %d0,%a0                             /* $fca596 */
    tst.w   LA(LINEA_MULTIFILL)(%a4)            /* $fca598 */
    sne     %d0                                 /* $fca59c */
    .word   M68K_AND_W_IMMEDIATE(0), RASTER_MULTIFILL_PLANE_BYTES /* $fca59e and.w #32,%d0 */
    .globl  linea_rom_hline_span
linea_rom_hline_span:
    move.w  %d4,%d1                             /* $fca5a2 */
    asr.w   #4,%d1                              /* $fca5a4 */
    move.w  %d6,%d2                             /* $fca5a6 */
    asr.w   #4,%d2                              /* $fca5a8 */
    moveq   #15,%d3                             /* $fca5aa */
    and.w   %d3,%d4                             /* $fca5ac */
    add.w   %d4,%d4                             /* $fca5ae */
    move.w  .Lfringe_table(%pc,%d4.w),%d4       /* $fca5b0 */
    and.w   %d3,%d6                             /* $fca5b4 */
    add.w   %d6,%d6                             /* $fca5b6 */
    move.w  .Lfringe_table+2(%pc,%d6.w),%d6     /* $fca5b8 */
    not.w   %d6                                 /* $fca5bc */
    sub.w   %d1,%d2                             /* $fca5be */
    bne.s   .Lspan_masks_ready                            /* $fca5c0 */
    and.w   %d6,%d4                             /* $fca5c2 */
.Lspan_masks_ready:
    movea.l LA(LINEA_VECTOR_HLINE)(%a4),%a5     /* $fca5c4 */
    jmp     (%a5)                               /* $fca5c8 */

/* ==== $fcface..$fcfb53 =============================================================================
 * $a001 put_pixel — intin[0] into ptsin[0]'s pixel, one colour bit a plane (`ror.w`), unclipped. */
    .globl  linea_rom_put_pixel
linea_rom_put_pixel:
    movea.l (LINEA_PTSIN).l,%a0                 /* $fcface */
    move.w  (%a0),%d0                           /* $fcfad4 */
    move.w  2(%a0),%d1                          /* $fcfad6 */
    bsr.w   linea_rom_concat                    /* $fcfada */
    movea.l (SYSVAR_V_BAS_AD).l,%a1             /* $fcfade */
    adda.l  %d1,%a1                             /* $fcfae4 */
    eori.w  #15,%d0                             /* $fcfae6 */
    clr.w   %d1                                 /* $fcfaea */
    bset    %d0,%d1                             /* $fcfaec */
    move.w  %d1,%d0                             /* $fcfaee */
    not.w   %d0                                 /* $fcfaf0 */
    move.w  (LINEA_PLANES).l,%d2                /* $fcfaf2 */
    subq.w  #1,%d2                              /* $fcfaf8 */
    movea.l (LINEA_INTIN).l,%a0                 /* $fcfafa */
    move.w  (%a0),%d3                           /* $fcfb00 */
.Lput_plane:
    ror.w   #1,%d3                              /* $fcfb02 */
    bcc.s   .Lput_plane_clear                            /* $fcfb04 */
    or.w    %d1,(%a1)+                          /* $fcfb06 */
    dbf     %d2,.Lput_plane                        /* $fcfb08 */
    rts                                         /* $fcfb0c */
.Lput_plane_clear:
    and.w   %d0,(%a1)+                          /* $fcfb0e */
    dbf     %d2,.Lput_plane                        /* $fcfb10 */
    rts                                         /* $fcfb14 */

/* $a002 get_pixel — ptsin[0]'s colour index in D0, from the LAST plane down (`sne` / `add.b` puts the
 * bit in X, `addx.w` shifts it in). */
    .globl  linea_rom_get_pixel
linea_rom_get_pixel:
    movea.l (LINEA_PTSIN).l,%a0                 /* $fcfb16 */
    move.w  (%a0)+,%d0                          /* $fcfb1c */
    move.w  (%a0),%d1                           /* $fcfb1e */
    bsr.w   linea_rom_concat                    /* $fcfb20 */
    movea.l (SYSVAR_V_BAS_AD).l,%a0             /* $fcfb24 */
    adda.l  %d1,%a0                             /* $fcfb2a */
    eori.w  #15,%d0                             /* $fcfb2c */
    clr.w   %d1                                 /* $fcfb30 */
    bset    %d0,%d1                             /* $fcfb32 */
    move.w  (LINEA_PLANES).l,%d2                /* $fcfb34 */
    move.w  %d2,%d0                             /* $fcfb3a */
    add.w   %d0,%d0                             /* $fcfb3c */
    subq.w  #1,%d2                              /* $fcfb3e */
    adda.w  %d0,%a0                             /* $fcfb40 */
    moveq   #0,%d0                              /* $fcfb42 */
.Lget_plane:
    move.w  -(%a0),%d3                          /* $fcfb44 */
    and.w   %d1,%d3                             /* $fcfb46 */
    sne     %d3                                 /* $fcfb48 */
    add.b   %d3,%d3                             /* $fcfb4a */
    addx.w  %d0,%d0                             /* $fcfb4c */
    dbf     %d2,.Lget_plane                        /* $fcfb4e */
    rts                                         /* $fcfb52 */

/* ==== $fcfc50..$fcfccb =============================================================================
 * $a005's clip miss: the corners, as far as the clip had got, stored back — then nothing drawn. */
.Lrect_store_corners:
    movem.w %d4-%d7,(%a0)                       /* $fcfc50 */
    rts                                         /* $fcfc54 */

/* $a005 filled rectangle — with CLIP on, each edge clipped against the clip rectangle and the corners
 * stored back; then D0/D1 = the two groups, D4/D6 = the fringe masks (from the fringe table by an
 * absolute `lea` — the ROM's names $fca55c, this one names the copy above, so the file is self-contained),
 * and a jump through vector 6. */
    .globl  linea_rom_filled_rect
linea_rom_filled_rect:
    lea     (LINEA_BASE).l,%a2                  /* $fcfc56 */
    lea     LA(LINEA_X1)(%a2),%a0               /* $fcfc5c */
    movem.w (%a0),%d4-%d7                       /* $fcfc60 */
    lea     LA(LINEA_CLIP)(%a2),%a1             /* $fcfc64 */
    tst.w   (%a1)+                              /* $fcfc68 */
    beq.s   .Lrect_masks                            /* $fcfc6a */
    movem.w (%a1),%d0-%d3                       /* $fcfc6c */
    cmp.w   %d0,%d4                             /* $fcfc70 */
    bge.s   .Lclip_right                            /* $fcfc72 */
    cmp.w   %d0,%d6                             /* $fcfc74 */
    blt.s   .Lrect_store_corners                /* $fcfc76 */
    move.w  %d0,%d4                             /* $fcfc78 */
.Lclip_right:
    cmp.w   %d2,%d6                             /* $fcfc7a */
    ble.s   .Lclip_top                            /* $fcfc7c */
    cmp.w   %d2,%d4                             /* $fcfc7e */
    bgt.s   .Lrect_store_corners                /* $fcfc80 */
    move.w  %d2,%d6                             /* $fcfc82 */
.Lclip_top:
    cmp.w   %d1,%d5                             /* $fcfc84 */
    bge.s   .Lclip_bottom                            /* $fcfc86 */
    cmp.w   %d1,%d7                             /* $fcfc88 */
    blt.s   .Lrect_store_corners                /* $fcfc8a */
    move.w  %d1,%d5                             /* $fcfc8c */
.Lclip_bottom:
    cmp.w   %d3,%d7                             /* $fcfc8e */
    ble.s   .Lclip_store                            /* $fcfc90 */
    cmp.w   %d3,%d5                             /* $fcfc92 */
    bgt.s   .Lrect_store_corners                /* $fcfc94 */
    move.w  %d3,%d7                             /* $fcfc96 */
.Lclip_store:
    movem.w %d4-%d7,(%a0)                       /* $fcfc98 */
.Lrect_masks:
    move.w  %d4,%d0                             /* $fcfc9c */
    asr.w   #4,%d0                              /* $fcfc9e */
    move.w  %d6,%d1                             /* $fcfca0 */
    asr.w   #4,%d1                              /* $fcfca2 */
    lea     (.Lfringe_table).l,%a1              /* $fcfca4 */
    moveq   #15,%d2                             /* $fcfcaa */
    and.w   %d2,%d4                             /* $fcfcac */
    add.w   %d4,%d4                             /* $fcfcae */
    move.w  0(%a1,%d4.w),%d4                    /* $fcfcb0 */
    and.w   %d2,%d6                             /* $fcfcb4 */
    add.w   %d6,%d6                             /* $fcfcb6 */
    move.w  2(%a1,%d6.w),%d6                    /* $fcfcb8 */
    not.w   %d6                                 /* $fcfcbc */
    sub.w   %d0,%d1                             /* $fcfcbe */
    bne.s   .Lrect_masks_ready                            /* $fcfcc0 */
    and.w   %d6,%d4                             /* $fcfcc2 */
.Lrect_masks_ready:
    movea.l (LINEA_VECTOR_RECT_FILL).l,%a5      /* $fcfcc4 */
    jmp     (%a5)                               /* $fcfcca */

/* ==== $fd19dc..$fd1cc3 =============================================================================
 * Vector 7's CPU body — the vertical line x1 = x2 (D4, D6), y1..y2 (D5, D7), entered with D0 = 2. The
 * diagonal arm's arrangement on one axis: A5 walks the column, A0 = the step, A1 = the step less the
 * planes the per-plane code has already walked past; the table below is a (loop, return-point) pair
 * per write mode, read as one longword and `swap`ped. */
    .globl  linea_rom_cpu_vline
linea_rom_cpu_vline:
    lea     -20(%sp),%sp                        /* $fd19dc */
    .word   M68K_MOVE_W_D16(4, 3), LA(LINEA_PLANES) /* $fd19e0 move.w LA(LINEA_PLANES)(%a4),%d3 */
    .word   M68K_CMP_W_IMMEDIATE(3), RASTER_LINE_PLANES_MAX /* $fd19e4 cmp.w #8,%d3 */
    bhi.w   .Lvline_done                        /* $fd19e8 */
    cmp.w   LA(LINEA_WRT_MODE)(%a4),%d0         /* $fd19ec */
    beq.s   .Lvline_built                            /* $fd19f0 */
    movea.l %sp,%a2                             /* $fd19f2 */
    bsr.w   linea_rom_line_plane_words          /* $fd19f4 */
.Lvline_built:
    .word   M68K_MOVE_W_D16(4, 0), LA(LINEA_PLANES) /* $fd19f8 move.w LA(LINEA_PLANES)(%a4),%d0 */
    add.w   %d0,%d0                             /* $fd19fc */
    movea.l (SYSVAR_V_BAS_AD).l,%a5             /* $fd19fe */
    asr.w   #4,%d6                              /* $fd1a04 */
    muls.w  %d0,%d6                             /* $fd1a06 */
    adda.l  %d6,%a5                             /* $fd1a08 */
    move.w  LA(LINEA_BYTES_LIN)(%a4),%d1        /* $fd1a0a */
    move.w  %d1,%d6                             /* $fd1a0e */
    muls.w  %d5,%d6                             /* $fd1a10 */
    adda.l  %d6,%a5                             /* $fd1a12 */
    move.w  LA(LINEA_WIDTH)(%a4),%d1            /* $fd1a14 */
    sub.w   %d5,%d7                             /* $fd1a18 */
    bge.s   .Lvline_downward                            /* $fd1a1a */
    neg.w   %d1                                 /* $fd1a1c */
    neg.w   %d7                                 /* $fd1a1e */
.Lvline_downward:
    movea.w %d1,%a0                             /* $fd1a20 */
    sub.w   %d0,%d1                             /* $fd1a22 */
    movea.w %d1,%a1                             /* $fd1a24 */
    moveq   #15,%d5                             /* $fd1a26 */
    not.w   %d4                                 /* $fd1a28 */
    and.w   %d5,%d4                             /* $fd1a2a */
    clr.w   %d1                                 /* $fd1a2c */
    bset    %d4,%d1                             /* $fd1a2e */
    move.w  LA(LINEA_WRT_MODE)(%a4),%d6         /* $fd1a30 */
    lsl.w   #2,%d6                              /* $fd1a34 */
    .word   M68K_CMP_W_IMMEDIATE(6), RASTER_VLINE_XOR_ARM /* $fd1a36 cmp.w #8,%d6 */
    bne.s   .Lvline_count_ready                            /* $fd1a3a */
    tst.w   LA(LINEA_LSTLIN)(%a4)               /* $fd1a3c */
    bne.s   .Lvline_count_ready                            /* $fd1a40 */
    subq.w  #1,%d7                              /* $fd1a42 */
.Lvline_count_ready:
    move.w  LA(LINEA_LN_MASK)(%a4),%d2          /* $fd1a44 */
    move.w  %d2,%d3                             /* $fd1a48 */
    move.w  %d7,%d4                             /* $fd1a4a */
    addq.w  #1,%d4                              /* $fd1a4c */
    and.w   %d5,%d4                             /* $fd1a4e */
    rol.w   %d4,%d3                             /* $fd1a50 */
    move.w  %d3,LA(LINEA_LN_MASK)(%a4)          /* $fd1a52 */
    move.l  .Lvline_table(%pc,%d6.w),%d6        /* $fd1a56 */
    lea     .Lvline_table(%pc,%d6.w),%a3        /* $fd1a5a */
    movea.l %a3,%a4                             /* $fd1a5e */
    suba.w  %d0,%a4                             /* $fd1a60 */
    move.w  %d1,%d0                             /* $fd1a62 */
    not.w   %d0                                 /* $fd1a64 */
    swap    %d6                                 /* $fd1a66 */
    jmp     .Lvline_table(%pc,%d6.w)            /* $fd1a68 */
.Lvline_done:
    lea     20(%sp),%sp                         /* $fd1a6c */
    rts                                         /* $fd1a70 */
.Lvline_table:
/* $fd1a72 */
    .word   .Lvline_replace - .Lvline_table
    .word   .Lvline_replace_step - .Lvline_table
    .word   .Lvline_transparent - .Lvline_table
    .word   .Lvline_transparent_step - .Lvline_table
    .word   .Lvline_xor - .Lvline_table
    .word   .Lvline_xor_step - .Lvline_table
    .word   .Lvline_reverse - .Lvline_table
    .word   .Lvline_transparent_step - .Lvline_table
.Lvline_replace:
    rol.w   #1,%d2                              /* $fd1a82 */
    bcc.s   .Lvline_replace_clear                            /* $fd1a84 */
    jmp     (%a2)                               /* $fd1a86 */
.Lvline_replace_clear:
    jmp     (%a4)                               /* $fd1a88 */
    and.w   %d0,(%a5)+                          /* $fd1a8a */
    and.w   %d0,(%a5)+                          /* $fd1a8c */
    and.w   %d0,(%a5)+                          /* $fd1a8e */
    and.w   %d0,(%a5)+                          /* $fd1a90 */
    and.w   %d0,(%a5)+                          /* $fd1a92 */
    and.w   %d0,(%a5)+                          /* $fd1a94 */
    and.w   %d0,(%a5)+                          /* $fd1a96 */
    and.w   %d0,(%a5)+                          /* $fd1a98 */
.Lvline_replace_step:
    adda.w  %a1,%a5                             /* $fd1a9a */
    dbf     %d7,.Lvline_replace                        /* $fd1a9c */
    bra.s   .Lvline_done                        /* $fd1aa0 */
.Lvline_reverse:
    not.w   %d2                                 /* $fd1aa2 */
.Lvline_transparent:
    rol.w   #1,%d2                              /* $fd1aa4 */
    bcc.s   .Lvline_transparent_skip                            /* $fd1aa6 */
    jmp     (%a2)                               /* $fd1aa8 */
.Lvline_transparent_step:
    adda.w  %a1,%a5                             /* $fd1aaa */
    dbf     %d7,.Lvline_transparent                        /* $fd1aac */
    bra.s   .Lvline_done                        /* $fd1ab0 */
.Lvline_transparent_skip:
    adda.w  %a0,%a5                             /* $fd1ab2 */
    dbf     %d7,.Lvline_transparent                        /* $fd1ab4 */
    bra.s   .Lvline_done                        /* $fd1ab8 */
.Lvline_xor:
    rol.w   #1,%d2                              /* $fd1aba */
    bcc.s   .Lvline_xor_skip                            /* $fd1abc */
    jmp     (%a4)                               /* $fd1abe */
    eor.w   %d1,(%a5)+                          /* $fd1ac0 */
    eor.w   %d1,(%a5)+                          /* $fd1ac2 */
    eor.w   %d1,(%a5)+                          /* $fd1ac4 */
    eor.w   %d1,(%a5)+                          /* $fd1ac6 */
    eor.w   %d1,(%a5)+                          /* $fd1ac8 */
    eor.w   %d1,(%a5)+                          /* $fd1aca */
    eor.w   %d1,(%a5)+                          /* $fd1acc */
    eor.w   %d1,(%a5)+                          /* $fd1ace */
.Lvline_xor_step:
    adda.w  %a1,%a5                             /* $fd1ad0 */
    dbf     %d7,.Lvline_xor                        /* $fd1ad2 */
    bra.s   .Lvline_done                        /* $fd1ad6 */
.Lvline_xor_skip:
    adda.w  %a0,%a5                             /* $fd1ad8 */
    dbf     %d7,.Lvline_xor                        /* $fd1ada */
    bra.s   .Lvline_done                        /* $fd1ade */

/* Vector 8's CPU body — one span row: A1 = the left group at y (D5), A2 = the pattern stride, D7 = the
 * plane count, A3 = COLBIT, D0 = planes * 2; then a jump into the write mode's arm below. */
    .globl  linea_rom_cpu_hline
linea_rom_cpu_hline:
    movea.l (SYSVAR_V_BAS_AD).l,%a1             /* $fd1ae0 */
    muls.w  LA(LINEA_BYTES_LIN)(%a4),%d5        /* $fd1ae6 */
    adda.l  %d5,%a1                             /* $fd1aea */
    movea.w %d0,%a2                             /* $fd1aec */
    .word   M68K_MOVE_W_D16(4, 7), LA(LINEA_PLANES) /* $fd1aee move.w LA(LINEA_PLANES)(%a4),%d7 */
    move.w  %d7,%d0                             /* $fd1af2 */
    add.w   %d0,%d0                             /* $fd1af4 */
    muls.w  %d0,%d1                             /* $fd1af6 */
    adda.l  %d1,%a1                             /* $fd1af8 */
    subq.w  #1,%d7                              /* $fd1afa */
    lea     LA(LINEA_COLBIT0)(%a4),%a3          /* $fd1afc */
    move.w  LA(LINEA_WRT_MODE)(%a4),%d1         /* $fd1b00 */
    add.w   %d1,%d1                             /* $fd1b04 */
    lea     .Lspan_arms(%pc,%d1.w),%a5          /* $fd1b06 */
    adda.w  (%a5),%a5                           /* $fd1b0a */
    jmp     (%a5)                               /* $fd1b0c */
.Lspan_arms:
/* $fd1b0e */
    .word   .Larm_replace - .
    .word   .Larm_transparent - .
    .word   .Larm_xor - .
    .word   .Larm_reverse - .

/* Vector 6's CPU body — the span rows y1..y2 (D5, D7): the row's constants kept in a LINK frame and
 * reloaded after every row, the arm `jsr`ed once a row, the pattern row stepped by one word and reset
 * only PAST PATMSK * 2, and A1 moved on by WIDTH less the planes the arm walked past. */
    .globl  linea_rom_cpu_rect_fill
linea_rom_cpu_rect_fill:
    link.w  %a6,#-20                            /* $fd1b16 */
    move.w  LA(LINEA_WRT_MODE)(%a2),%d2         /* $fd1b1a */
    add.w   %d2,%d2                             /* $fd1b1e */
    lea     .Lspan_arms(%pc,%d2.w),%a5          /* $fd1b20 */
    adda.w  (%a5),%a5                           /* $fd1b24 */
    sub.w   %d5,%d7                             /* $fd1b26 */
    movea.l (SYSVAR_V_BAS_AD).l,%a1             /* $fd1b28 */
    move.w  LA(LINEA_BYTES_LIN)(%a2),%d2        /* $fd1b2e */
    muls.w  %d5,%d2                             /* $fd1b32 */
    adda.l  %d2,%a1                             /* $fd1b34 */
    .word   M68K_MOVE_W_D16(2, 2), LA(LINEA_PLANES) /* $fd1b36 move.w LA(LINEA_PLANES)(%a2),%d2 */
    muls.w  %d2,%d0                             /* $fd1b3a */
    add.l   %d0,%d0                             /* $fd1b3c */
    adda.l  %d0,%a1                             /* $fd1b3e */
    move.w  %d2,%d0                             /* $fd1b40 */
    add.w   %d0,%d0                             /* $fd1b42 */
    subq.w  #1,%d2                              /* $fd1b44 */
    move.w  %d2,-(%a6)                          /* $fd1b46 */
    move.w  %d1,-(%a6)                          /* $fd1b48 */
    lea     LA(LINEA_COLBIT0)(%a2),%a3          /* $fd1b4a */
    move.l  %a3,-(%a6)                          /* $fd1b4e */
    move.w  LA(LINEA_WIDTH)(%a2),%d3            /* $fd1b50 */
    sub.w   %d0,%d3                             /* $fd1b54 */
    move.w  %d3,-(%a6)                          /* $fd1b56 */
    move.w  LA(LINEA_PATMSK)(%a2),%d3           /* $fd1b58 */
    and.w   %d3,%d5                             /* $fd1b5c */
    add.w   %d5,%d5                             /* $fd1b5e */
    move.w  %d5,-(%a6)                          /* $fd1b60 */
    add.w   %d3,%d3                             /* $fd1b62 */
    move.w  %d3,-(%a6)                          /* $fd1b64 */
    movea.l LA(LINEA_PATPTR)(%a2),%a0           /* $fd1b66 */
    move.l  %a0,-(%a6)                          /* $fd1b6a */
    adda.w  %d5,%a0                             /* $fd1b6c */
    move.w  %d7,-(%a6)                          /* $fd1b6e */
    move.w  %d2,%d7                             /* $fd1b70 */
    move.w  %d1,%d2                             /* $fd1b72 */
    moveq   #0,%d1                              /* $fd1b74 */
    tst.w   LA(LINEA_MULTIFILL)(%a2)            /* $fd1b76 */
    beq.s   .Lrect_stride_ready                            /* $fd1b7a */
    moveq   #32,%d1                             /* $fd1b7c */
.Lrect_stride_ready:
    movea.l %d1,%a2                             /* $fd1b7e */
.Lrect_row:
    jsr     (%a5)                               /* $fd1b80 */
    subq.w  #1,(%a6)+                           /* $fd1b82 */
    bcs.s   .Lrect_done                            /* $fd1b84 */
    movea.l (%a6)+,%a0                          /* $fd1b86 */
    move.w  (%a6)+,%d1                          /* $fd1b88 */
    move.w  (%a6),%d3                           /* $fd1b8a */
    addq.w  #2,%d3                              /* $fd1b8c */
    cmp.w   %d1,%d3                             /* $fd1b8e */
    ble.s   .Lrect_pattern_row_ready                            /* $fd1b90 */
    clr.w   %d3                                 /* $fd1b92 */
.Lrect_pattern_row_ready:
    move.w  %d3,(%a6)+                          /* $fd1b94 */
    adda.w  %d3,%a0                             /* $fd1b96 */
    adda.w  (%a6)+,%a1                          /* $fd1b98 */
    movea.l (%a6)+,%a3                          /* $fd1b9a */
    move.w  (%a6)+,%d2                          /* $fd1b9c */
    move.w  (%a6)+,%d7                          /* $fd1b9e */
    lea     -20(%a6),%a6                        /* $fd1ba0 */
    bra.s   .Lrect_row                            /* $fd1ba4 */
.Lrect_done:
    lea     18(%a6),%a6                         /* $fd1ba6 */
    unlk    %a6                                 /* $fd1baa */
    rts                                         /* $fd1bac */

/* The four SPAN ARMS both bodies share: per plane, the left word under D4, D2 - 1 whole middle words
 * and the right word under D6 (`subq.w #1,d5 / bcs` twice before the `dbf`), or the left word alone
 * when D2 is 0. XOR flips the pattern's bits and never reads COLBIT. */
.Larm_xor:
    movea.l %a1,%a4                             /* $fd1bae */
    move.w  %d2,%d5                             /* $fd1bb0 */
    move.w  (%a0),%d3                           /* $fd1bb2 */
    adda.w  %a2,%a0                             /* $fd1bb4 */
    move.w  %d4,%d1                             /* $fd1bb6 */
    and.w   %d3,%d1                             /* $fd1bb8 */
    eor.w   %d1,(%a1)+                          /* $fd1bba */
    subq.w  #1,%d5                              /* $fd1bbc */
    bcs.s   .Lxor_next_plane                            /* $fd1bbe */
    subq.w  #1,%d5                              /* $fd1bc0 */
    bcs.s   .Lxor_right                            /* $fd1bc2 */
.Lxor_middle:
    adda.w  %d0,%a4                             /* $fd1bc4 */
    eor.w   %d3,(%a4)                           /* $fd1bc6 */
    dbf     %d5,.Lxor_middle                        /* $fd1bc8 */
.Lxor_right:
    move.w  %d6,%d1                             /* $fd1bcc */
    and.w   %d3,%d1                             /* $fd1bce */
    adda.w  %d0,%a4                             /* $fd1bd0 */
    eor.w   %d1,(%a4)                           /* $fd1bd2 */
.Lxor_next_plane:
    dbf     %d7,.Larm_xor                       /* $fd1bd4 */
    rts                                         /* $fd1bd8 */

/* REPLACE: a plane whose COLBIT is clear is cleared under the masks (the masks are complemented for the
 * pass and back after it); one whose COLBIT is set takes the pattern there. */
.Larm_replace:
    not.w   %d4                                 /* $fd1bda */
    not.w   %d6                                 /* $fd1bdc */
.Lreplace_plane:
    movea.l %a1,%a4                             /* $fd1bde */
    move.w  %d2,%d5                             /* $fd1be0 */
    move.w  (%a0),%d3                           /* $fd1be2 */
    adda.w  %a2,%a0                             /* $fd1be4 */
    tst.w   (%a3)+                              /* $fd1be6 */
    bne.s   .Lreplace_colour                            /* $fd1be8 */
    move.w  %d4,%d1                             /* $fd1bea */
    and.w   %d1,(%a1)+                          /* $fd1bec */
    subq.w  #1,%d5                              /* $fd1bee */
    bcs.s   .Lreplace_next_plane                            /* $fd1bf0 */
    subq.w  #1,%d5                              /* $fd1bf2 */
    bcs.s   .Lreplace_clear_right                            /* $fd1bf4 */
    clr.w   %d1                                 /* $fd1bf6 */
.Lreplace_clear_middle:
    adda.w  %d0,%a4                             /* $fd1bf8 */
    move.w  %d1,(%a4)                           /* $fd1bfa */
    dbf     %d5,.Lreplace_clear_middle                        /* $fd1bfc */
.Lreplace_clear_right:
    move.w  %d6,%d1                             /* $fd1c00 */
    adda.w  %d0,%a4                             /* $fd1c02 */
    and.w   %d1,(%a4)                           /* $fd1c04 */
.Lreplace_next_plane:
    dbf     %d7,.Lreplace_plane                        /* $fd1c06 */
    not.w   %d4                                 /* $fd1c0a */
    not.w   %d6                                 /* $fd1c0c */
    rts                                         /* $fd1c0e */
.Lreplace_colour:
    move.w  (%a4),%d1                           /* $fd1c10 */
    eor.w   %d3,%d1                             /* $fd1c12 */
    and.w   %d4,%d1                             /* $fd1c14 */
    eor.w   %d3,%d1                             /* $fd1c16 */
    move.w  %d1,(%a1)+                          /* $fd1c18 */
    subq.w  #1,%d5                              /* $fd1c1a */
    bcs.s   .Lreplace_colour_next_plane                            /* $fd1c1c */
    subq.w  #1,%d5                              /* $fd1c1e */
    bcs.s   .Lreplace_colour_right                            /* $fd1c20 */
.Lreplace_colour_middle:
    adda.w  %d0,%a4                             /* $fd1c22 */
    move.w  %d3,(%a4)                           /* $fd1c24 */
    dbf     %d5,.Lreplace_colour_middle                        /* $fd1c26 */
.Lreplace_colour_right:
    adda.w  %d0,%a4                             /* $fd1c2a */
    move.w  (%a4),%d1                           /* $fd1c2c */
    eor.w   %d3,%d1                             /* $fd1c2e */
    and.w   %d6,%d1                             /* $fd1c30 */
    eor.w   %d3,%d1                             /* $fd1c32 */
    move.w  %d1,(%a4)                           /* $fd1c34 */
.Lreplace_colour_next_plane:
    dbf     %d7,.Lreplace_plane                        /* $fd1c36 */
    not.w   %d4                                 /* $fd1c3a */
    not.w   %d6                                 /* $fd1c3c */
    rts                                         /* $fd1c3e */

/* TRANSPARENT sets the pattern's bits where COLBIT is set and clears them where it is not; REVERSE is
 * the same over the complemented pattern. Both reach the two span helpers below. */
.Larm_transparent:
    movea.l %a1,%a4                             /* $fd1c40 */
    move.w  %d2,%d5                             /* $fd1c42 */
    move.w  (%a0),%d3                           /* $fd1c44 */
    adda.w  %a2,%a0                             /* $fd1c46 */
    tst.w   (%a3)+                              /* $fd1c48 */
    bne.s   .Ltransparent_set                            /* $fd1c4a */
    not.w   %d3                                 /* $fd1c4c */
    bsr.s   .Lspan_reset                        /* $fd1c4e */
    dbf     %d7,.Larm_transparent               /* $fd1c50 */
    rts                                         /* $fd1c54 */
.Ltransparent_set:
    bsr.s   .Lspan_set                          /* $fd1c56 */
    dbf     %d7,.Larm_transparent               /* $fd1c58 */
    rts                                         /* $fd1c5c */
.Larm_reverse:
    movea.l %a1,%a4                             /* $fd1c5e */
    move.w  %d2,%d5                             /* $fd1c60 */
    move.w  (%a0),%d3                           /* $fd1c62 */
    adda.w  %a2,%a0                             /* $fd1c64 */
    tst.w   (%a3)+                              /* $fd1c66 */
    bne.s   .Lreverse_set                            /* $fd1c68 */
    bsr.s   .Lspan_reset                        /* $fd1c6a */
    dbf     %d7,.Larm_reverse                   /* $fd1c6c */
    rts                                         /* $fd1c70 */
.Lreverse_set:
    not.w   %d3                                 /* $fd1c72 */
    bsr.s   .Lspan_set                          /* $fd1c74 */
    dbf     %d7,.Larm_reverse                   /* $fd1c76 */
    rts                                         /* $fd1c7a */
.Lspan_reset:
    move.w  %d4,%d1                             /* $fd1c7c */
    not.w   %d1                                 /* $fd1c7e */
    or.w    %d3,%d1                             /* $fd1c80 */
    and.w   %d1,(%a1)+                          /* $fd1c82 */
    dbf     %d5,.Lreset_middles                        /* $fd1c84 */
    rts                                         /* $fd1c88 */
.Lreset_middles:
    subq.w  #1,%d5                              /* $fd1c8a */
    bcs.s   .Lreset_right                            /* $fd1c8c */
.Lreset_middle:
    adda.w  %d0,%a4                             /* $fd1c8e */
    and.w   %d3,(%a4)                           /* $fd1c90 */
    dbf     %d5,.Lreset_middle                        /* $fd1c92 */
.Lreset_right:
    move.w  %d6,%d1                             /* $fd1c96 */
    not.w   %d1                                 /* $fd1c98 */
    or.w    %d3,%d1                             /* $fd1c9a */
    adda.w  %d0,%a4                             /* $fd1c9c */
    and.w   %d1,(%a4)                           /* $fd1c9e */
    rts                                         /* $fd1ca0 */
.Lspan_set:
    move.w  %d4,%d1                             /* $fd1ca2 */
    and.w   %d3,%d1                             /* $fd1ca4 */
    or.w    %d1,(%a1)+                          /* $fd1ca6 */
    dbf     %d5,.Lset_middles                        /* $fd1ca8 */
    rts                                         /* $fd1cac */
.Lset_middles:
    subq.w  #1,%d5                              /* $fd1cae */
    bcs.s   .Lset_right                            /* $fd1cb0 */
.Lset_middle:
    adda.w  %d0,%a4                             /* $fd1cb2 */
    or.w    %d3,(%a4)                           /* $fd1cb4 */
    dbf     %d5,.Lset_middle                        /* $fd1cb6 */
.Lset_right:
    move.w  %d6,%d1                             /* $fd1cba */
    and.w   %d3,%d1                             /* $fd1cbc */
    adda.w  %d0,%a4                             /* $fd1cbe */
    or.w    %d1,(%a4)                           /* $fd1cc0 */
    rts                                         /* $fd1cc2 */
