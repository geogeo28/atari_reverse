/* text_raster.S — the TEXT RASTER as the ROM wrote it: $a008 TextBlt, v_gtext's byte-aligned fast path, and
 * the CPU bodies behind drawing vectors 9 and 5 — the TRANSCRIPTION of `src/vdi/text_raster.c` the target
 * build ships (the user's rule for the hand-written 68000: C first, and where the C measures over Tier 3's
 * 1.10 bar, the ROM's own instructions; `include/transcribed.h` records it, entry by entry).
 *
 * WHY THIS IS ASSEMBLY. The C is the reconstruction — Tier 1 proves it against the ROM over every arm — and
 * it runs several times the ROM's cycles (STATUS.md has the rows). TextBlt is the ROM's longest hand loop,
 * and its speed is in what C cannot name: a row loop that `jsr`s a FRAGMENT by an offset held in its frame,
 * effect fragments that jump on to the fragment they replaced, a skew step that branches from one multi-word
 * loop into the other, and registers carried across all of it. So the shipped routine is the ROM's own
 * sequence, proved two ways that need no C:
 *
 *   * BYTE FOR BYTE — `test_vdi_text_raster_transcription.py` reads the assembled words back out of the
 *     cross-compiled blob and compares them with the ROM's, region by region (`transcription.assert_transcribed`).
 *     Four references differ, each RELOCATED there by name and pinned to the exact value it must hold: the
 *     `bsr.w` to act_siz (`helpers.S`) and the `jsr` to concat (`raster.S`), the `lea` of the fringe masks —
 *     raster.S's copy of the ROM's table, reached through its region's entry — and the `movea.l #` of this
 *     file's own fragment base.
 *   * BY BEHAVIOUR — every registered case, through Tier 3's TRANSCRIPTION relation
 *     (`RomBench.measure_transcription`): the same image, the WHOLE register file and the same chip traffic
 *     as the ROM, entered through a staged caller that builds each body's entry stack.
 *
 * THE THREE REGIONS are the ROM's, in its order, each laid out whole so that every PC-relative reference,
 * every fragment offset and every table index assembles to the ROM's own word:
 *
 *   $fcee54..$fcee65  $a008, the front end of vector 9
 *   $fcf964..$fcf9bd  fast_text_try, its shared refusal BEFORE its entry, the front end of vector 5
 *   $fd1cc4..$fd2d31  the CPU bodies of vectors 5 and 9 with their tables, the op fragments and the ROM's
 *                     easter egg ("Dave StaUgas loves Bea Hablig", read as op indexes past write mode 19)
 *
 * $fcee66..$fcf963 between the first two is the BLITTER TextBlt, deferred with the rest of the blitter set
 * (STATUS.md, "Not reconstructed").
 *
 * WHAT A TRANSCRIPTION CANNOT CARRY: the op index is WRT_MODE * 4 + two colour bits, read PC-relative. For
 * a write mode up to 63 every table read lands inside the third region (the tables and the easter egg after
 * them); past that the ROM walks on into its own font data, and this file into whatever the build links
 * after it. Only a Line-A caller writing such a WRT_MODE reaches it, and the C (which reads the ROM's bytes)
 * is what `test_vdi_textblt.py` holds to it.
 *
 * FIVE `.word` LINES spell instructions GNU as would encode differently — `and.w`/`cmp.w #imm,Dn` in the
 * register form, and a `move.w 0(An),Dn` whose zero displacement gas would drop — as the ROM's own words
 * (`m68k_encodings.h`). Each carries the instruction in its comment.
 *
 * Every line carries the ROM address it transcribes. `LA(field)` is a Line-A field's displacement from the
 * base in A6; in the fast path A5 points INTO the block, and a field is spelt from where A5 then is. TextBlt's
 * frame (`link a5,#-84`) is `TB_*`, the fields of `struct textblt` in `text_raster.c`.
 */
#include "addrs.h"
#include "m68k_encodings.h"
#include "vdi/linea.h"
#include "vdi/vdi.h"
#include "vdi/helpers.h"
#include "vdi/raster.h"
#include "vdi/text_raster.h"

#define LA(field) ((field) - LINEA_BASE)
/* TextBlt's frame, `struct textblt` field by field. */
#define TB_SCRATCH_HALF         (-2)
#define TB_SOURCE               (-6)
#define TB_SOURCE_STEP          (-12)
#define TB_DEST_STEP            (-14)
#define TB_WIDTH                (-16)
#define TB_HEIGHT               (-18)
#define TB_SOURCE_BIT           (-20)
#define TB_DEST_BIT             (-22)
#define TB_MIDDLE_WORDS         (-24)
#define TB_THICKEN_LEFT         (-25)   /* byte */
#define TB_THICKEN_WORDS        (-26)   /* byte */
#define TB_THICKEN_EDGE         (-28)
#define TB_RIGHT_MASK           (-30)
#define TB_LEFT_MASK            (-32)
#define TB_CARRY_MASK           (-34)
#define TB_SHIFT                (-36)
#define TB_ROW_LOOP             (-38)
#define TB_OP_RIGHT             (-40)
#define TB_OP_FIRST             (-42)
#define TB_OP_EDGE              (-44)
#define TB_THICKEN_FIRST_NEXT   (-46)
#define TB_LIGHTEN_FIRST_NEXT   (-48)
#define TB_SKEW_FIRST_NEXT      (-50)
#define TB_THICKEN_EDGE_NEXT    (-52)
#define TB_LIGHTEN_EDGE_NEXT    (-54)
#define TB_OP_MIDDLE            (-56)
#define TB_THICKEN_MIDDLE_NEXT  (-58)
#define TB_LIGHTEN_MIDDLE_NEXT  (-60)
#define TB_WEIGHT               (-62)
#define TB_LIGHTEN_MASK         (-64)
#define TB_SKEW_MASK            (-66)
#define TB_THICKEN_SPILL        (-68)
#define TB_FG_BITS              (-70)
#define TB_BG_BITS              (-72)
#define TB_PLANES_LEFT          (-74)
#define TB_GROUP_BYTES          (-76)
#define TB_SCALED_WIDTH         (-78)
#define TB_SCALED_HEIGHT        (-80)
#define TB_SWAPPED_AXES         (-82)
#define TB_SCALED_ACCUMULATOR   (-84)
#define TB_FRAME_BYTES          84
/* LINEA_STYLE's bits as `btst` numbers them (vdi/vdi.h has them as masks), and T_SCLSTS's. */
#define STYLE_THICKEN_BIT       0
#define STYLE_LIGHTEN_BIT       1
#define STYLE_SKEW_BIT          2
#define STYLE_OUTLINE_BIT       4
#define SCALE_UP_BIT            0
#define WORD_BITS               16
#define LAST_BIT_IN_WORD        15
#define PIXEL_IN_GROUP_MASK     15
#define LEFTMOST_BIT            0x8000
#define WHOLE_WORD              0xffff
#define CCR_X                   0x10    /* `ori #CCR_X,ccr`: the 1 a `roxr` shifts in */

    .text

/* $a008 TextBlt: A5 and A6 pushed under the caller's return address — vector 9's body pops them on its
 * way out — A6 = the Line-A base, and on through the vector. */
    .globl  linea_rom_textblt
linea_rom_textblt:
    movem.l %a5-%a6,-(%sp)                      /* $fcee54 */
    lea     (LINEA_BASE).l,%a6                  /* $fcee58 */
    movea.l (LINEA_VECTOR_TEXTBLT).l,%a4        /* $fcee5e */
    jmp     (%a4)                               /* $fcee64 */

/* fast_text_try's SHARED REFUSAL, laid down BEFORE its entry: every refusing branch below lands here, pops
 * the A5 the entry pushed and answers 0. */
.Lfast_refused:
    movea.l (%sp)+,%a5                          /* $fcf964 */
    moveq   #0,%d0                              /* $fcf966 */
    rts                                         /* $fcf968 */

/* fast_text_try — v_gtext's `jsr` for an unscaled, unstyled eight-pixel font: x on a byte, and with CLIP
 * inside it by a test that refuses more than it must (a last row or column touching the far edge).
 * Accepted, D0-D3 = x, y, characters (contrl[3]), rows and A5 = &FBASE, through vector 5. */
    .globl  linea_rom_fast_text
linea_rom_fast_text:
    move.l  %a5,-(%sp)                          /* $fcf96a */
    lea     (LINEA_DESTX).l,%a5                 /* $fcf96c */
    move.w  (%a5)+,%d0                          /* $fcf972 */
    move.w  %d0,%d2                             /* $fcf974 */
    .word   M68K_AND_W_IMMEDIATE(2), TEXT_FAST_X_ALIGN_MASK /* $fcf976 and.w #7,%d2 */
    bne.s   .Lfast_refused                      /* $fcf97a */
    move.w  (%a5),%d1                           /* $fcf97c */
    move.w  (LINEA_DELY-LINEA_DESTY)(%a5),%d3   /* $fcf97e */
    movea.l (LINEA_CONTRL-LINEA_DESTY)(%a5),%a0 /* $fcf982 */
    move.w  CONTRL_N_INTIN(%a0),%d2             /* $fcf986 */
    lea     (LINEA_CLIP-LINEA_DESTY)(%a5),%a5   /* $fcf98a */
    tst.w   (%a5)+                              /* $fcf98e */
    beq.s   .Lfast_accepted                     /* $fcf990 */
    move.w  (%a5)+,%d5                          /* $fcf992 */
    move.w  (%a5)+,%d6                          /* $fcf994 */
    move.w  (%a5)+,%d7                          /* $fcf996 */
    cmp.w   %d6,%d1                             /* $fcf998 */
    blt.s   .Lfast_refused                      /* $fcf99a */
    move.w  %d1,%d4                             /* $fcf99c */
    add.w   %d3,%d4                             /* $fcf99e */
    cmp.w   (%a5),%d4                           /* $fcf9a0 */
    bge.s   .Lfast_refused                      /* $fcf9a2 */
    cmp.w   %d5,%d0                             /* $fcf9a4 */
    blt.s   .Lfast_refused                      /* $fcf9a6 */
    move.w  %d2,%d4                             /* $fcf9a8 */
    lsl.w   #TEXT_FAST_GLYPH_SHIFT,%d4          /* $fcf9aa */
    add.w   %d0,%d4                             /* $fcf9ac */
    cmp.w   %d7,%d4                             /* $fcf9ae */
    bge.s   .Lfast_refused                      /* $fcf9b0 */
.Lfast_accepted:
    lea     (LINEA_FBASE).l,%a5                 /* $fcf9b2 */
    movea.l (LINEA_VECTOR_FAST_TEXT-LINEA_FBASE)(%a5),%a4 /* $fcf9b8 */
    jmp     (%a4)                               /* $fcf9bc */

/* Vector 5's CPU body: A1 = the first glyph's screen byte (the odd byte when x & 8). The `dbf` on the row
 * count JUMPS INTO THE CHARACTER LOOP'S `dbf`; a count of 0 falls into the `rts` below, which returns
 * through the A6 this body pushed. Per character and plane: an arm by WRT_MODE * 2 and the plane's
 * colour bit, run down the glyph's rows a byte a row. */
    .globl  linea_rom_cpu_fast_text
linea_rom_cpu_fast_text:
    move.l  %a6,-(%sp)                          /* $fd1cc4 */
    muls.w  (LINEA_BYTES_LIN-LINEA_FBASE)(%a5),%d1 /* $fd1cc6 */
    asr.w   #4,%d0                              /* $fd1cca */
    subx.w  %d4,%d4                             /* $fd1ccc */
    muls.w  (LINEA_PLANES-LINEA_FBASE)(%a5),%d0 /* $fd1cce */
    add.w   %d4,%d4                             /* $fd1cd2 */
    addx.l  %d0,%d0                             /* $fd1cd4 */
    movea.l (SYSVAR_V_BAS_AD).l,%a1             /* $fd1cd6 */
    adda.l  %d0,%a1                             /* $fd1cdc */
    adda.l  %d1,%a1                             /* $fd1cde */
    movea.l (%a5)+,%a0                          /* $fd1ce0 */
    move.w  (%a5),%d0                           /* $fd1ce2 */
    movea.l (LINEA_INTIN-LINEA_FWIDTH)(%a5),%a2 /* $fd1ce4 */
    move.w  (LINEA_WIDTH-LINEA_FWIDTH)(%a5),%d1 /* $fd1ce8 */
    move.w  (LINEA_WRT_MODE-LINEA_FWIDTH)(%a5),%d4 /* $fd1cec */
    add.w   %d4,%d4                             /* $fd1cf0 */
    dbf     %d3,.Lfast_characters               /* $fd1cf2 */
    rts                                         /* $fd1cf6 */
.Lfast_character:
    move.l  %a1,-(%sp)                          /* $fd1cf8 */
    move.w  (%a2)+,%d5                          /* $fd1cfa */
    lea     0(%a0,%d5.w),%a3                    /* $fd1cfc */
    move.w  (LINEA_TEXT_FG-LINEA_FWIDTH)(%a5),%d6 /* $fd1d00 */
    move.w  (LINEA_PLANES-LINEA_FWIDTH)(%a5),%d5 /* $fd1d04 */
    bra.s   .Lfast_planes                       /* $fd1d08 */
.Lfast_plane:
    move.w  %d4,%d7                             /* $fd1d0a */
    ror.w   #1,%d6                              /* $fd1d0c */
    bcc.s   .Lfast_arm_chosen                   /* $fd1d0e */
    addq.w  #TEXT_FAST_ARM_COLOUR_SET,%d7       /* $fd1d10 */
.Lfast_arm_chosen:
    move.w  .Lfast_arms(%pc,%d7.w),%d7          /* $fd1d12 */
    jmp     .Lfast_arms(%pc,%d7.w)              /* $fd1d16 */
.Lfast_next_plane:
    addq.l  #2,%a1                              /* $fd1d1a */
.Lfast_planes:
    dbf     %d5,.Lfast_plane                    /* $fd1d1c */
    movea.l (%sp)+,%a1                          /* $fd1d20 */
    addq.l  #1,%a1                              /* $fd1d22 */
    move.l  %a1,%d7                             /* $fd1d24 */
    btst    #0,%d7                              /* $fd1d26 */
    bne.s   .Lfast_characters                   /* $fd1d2a */
    move.w  (LINEA_PLANES-LINEA_FWIDTH)(%a5),%d7 /* $fd1d2c */
    subq.w  #1,%d7                              /* $fd1d30 */
    add.w   %d7,%d7                             /* $fd1d32 */
    adda.w  %d7,%a1                             /* $fd1d34 */
.Lfast_characters:
    dbf     %d2,.Lfast_character                /* $fd1d36 */
    moveq   #1,%d0                              /* $fd1d3a */
    movea.l (%sp)+,%a6                          /* $fd1d3c */
    movea.l (%sp)+,%a5                          /* $fd1d3e */
    rts                                         /* $fd1d40 */

/* The eight byte arms, as offsets from here: modes 0..3 with the colour bit clear, then set. */
.Lfast_arms:
    .word   .Lfast_clear - .Lfast_arms          /* $fd1d42 */
    .word   .Lfast_and_not - .Lfast_arms        /* $fd1d44 */
    .word   .Lfast_xor - .Lfast_arms            /* $fd1d46 */
    .word   .Lfast_and - .Lfast_arms            /* $fd1d48 */
    .word   .Lfast_copy - .Lfast_arms           /* $fd1d4a */
    .word   .Lfast_or - .Lfast_arms             /* $fd1d4c */
    .word   .Lfast_xor - .Lfast_arms            /* $fd1d4e */
    .word   .Lfast_or_not - .Lfast_arms         /* $fd1d50 */
.Lfast_copy:
    movea.l %a1,%a6                             /* $fd1d52 */
    movea.l %a3,%a4                             /* $fd1d54 */
    move.w  %d3,%d7                             /* $fd1d56 */
.Lfast_copy_row:
    move.b  (%a4),(%a6)                         /* $fd1d58 */
    adda.w  %d0,%a4                             /* $fd1d5a */
    adda.w  %d1,%a6                             /* $fd1d5c */
    dbf     %d7,.Lfast_copy_row                 /* $fd1d5e */
    bra.s   .Lfast_next_plane                   /* $fd1d62 */
.Lfast_clear:
    movea.l %a1,%a6                             /* $fd1d64 */
    move.w  %d3,%d7                             /* $fd1d66 */
.Lfast_clear_row:
    clr.b   (%a6)                               /* $fd1d68 */
    adda.w  %d1,%a6                             /* $fd1d6a */
    dbf     %d7,.Lfast_clear_row                /* $fd1d6c */
    bra.s   .Lfast_next_plane                   /* $fd1d70 */
.Lfast_and_not:
    swap    %d2                                 /* $fd1d72 */
    movea.l %a1,%a6                             /* $fd1d74 */
    movea.l %a3,%a4                             /* $fd1d76 */
    move.w  %d3,%d7                             /* $fd1d78 */
.Lfast_and_not_row:
    move.b  (%a4),%d2                           /* $fd1d7a */
    not.b   %d2                                 /* $fd1d7c */
    and.b   %d2,(%a6)                           /* $fd1d7e */
    adda.w  %d0,%a4                             /* $fd1d80 */
    adda.w  %d1,%a6                             /* $fd1d82 */
    dbf     %d7,.Lfast_and_not_row              /* $fd1d84 */
    swap    %d2                                 /* $fd1d88 */
    bra.s   .Lfast_next_plane                   /* $fd1d8a */
.Lfast_or:
    swap    %d2                                 /* $fd1d8c */
    movea.l %a1,%a6                             /* $fd1d8e */
    movea.l %a3,%a4                             /* $fd1d90 */
    move.w  %d3,%d7                             /* $fd1d92 */
.Lfast_or_row:
    move.b  (%a4),%d2                           /* $fd1d94 */
    or.b    %d2,(%a6)                           /* $fd1d96 */
    adda.w  %d0,%a4                             /* $fd1d98 */
    adda.w  %d1,%a6                             /* $fd1d9a */
    dbf     %d7,.Lfast_or_row                   /* $fd1d9c */
    swap    %d2                                 /* $fd1da0 */
    bra.w   .Lfast_next_plane                   /* $fd1da2 */
.Lfast_and:
    swap    %d2                                 /* $fd1da6 */
    movea.l %a1,%a6                             /* $fd1da8 */
    movea.l %a3,%a4                             /* $fd1daa */
    move.w  %d3,%d7                             /* $fd1dac */
.Lfast_and_row:
    move.b  (%a4),%d2                           /* $fd1dae */
    and.b   %d2,(%a6)                           /* $fd1db0 */
    adda.w  %d0,%a4                             /* $fd1db2 */
    adda.w  %d1,%a6                             /* $fd1db4 */
    dbf     %d7,.Lfast_and_row                  /* $fd1db6 */
    swap    %d2                                 /* $fd1dba */
    bra.w   .Lfast_next_plane                   /* $fd1dbc */
.Lfast_or_not:
    swap    %d2                                 /* $fd1dc0 */
    movea.l %a1,%a6                             /* $fd1dc2 */
    movea.l %a3,%a4                             /* $fd1dc4 */
    move.w  %d3,%d7                             /* $fd1dc6 */
.Lfast_or_not_row:
    move.b  (%a4),%d2                           /* $fd1dc8 */
    not.b   %d2                                 /* $fd1dca */
    or.b    %d2,(%a6)                           /* $fd1dcc */
    adda.w  %d0,%a4                             /* $fd1dce */
    adda.w  %d1,%a6                             /* $fd1dd0 */
    dbf     %d7,.Lfast_or_not_row               /* $fd1dd2 */
    swap    %d2                                 /* $fd1dd6 */
    bra.w   .Lfast_next_plane                   /* $fd1dd8 */
.Lfast_xor:
    swap    %d2                                 /* $fd1ddc */
    movea.l %a3,%a4                             /* $fd1dde */
    movea.l %a1,%a6                             /* $fd1de0 */
    move.w  %d3,%d7                             /* $fd1de2 */
.Lfast_xor_row:
    move.b  (%a4),%d2                           /* $fd1de4 */
    eor.b   %d2,(%a6)                           /* $fd1de6 */
    adda.w  %d0,%a4                             /* $fd1de8 */
    adda.w  %d1,%a6                             /* $fd1dea */
    dbf     %d7,.Lfast_xor_row                  /* $fd1dec */
    swap    %d2                                 /* $fd1df0 */
    bra.w   .Lfast_next_plane                   /* $fd1df2 */

/* Vector 9's CPU body: the frame, then the glyph's size on the screen — scaled (the height by act_siz,
 * the width by the DDA), thickened unless monospaced, italic, outlined, turned — STYLE, WRT_MODE,
 * SKEWMASK and DESTX/DELX/DESTY/DELY saved on the stack. */
    .globl  linea_rom_cpu_textblt
linea_rom_cpu_textblt:
    link.w  %a5,#-TB_FRAME_BYTES                /* $fd1df6 */
    clr.w   TB_SWAPPED_AXES(%a5)                /* $fd1dfa */
    move.w  LA(LINEA_STYLE)(%a6),-(%sp)         /* $fd1dfe */
    move.w  LA(LINEA_WRT_MODE)(%a6),-(%sp)      /* $fd1e02 */
    move.w  LA(LINEA_SKEWMASK)(%a6),-(%sp)      /* $fd1e06 */
    move.w  LA(LINEA_DESTX)(%a6),%d0            /* $fd1e0a */
    move.w  LA(LINEA_DESTY)(%a6),%d2            /* $fd1e0e */
    move.w  LA(LINEA_DELX)(%a6),%d1             /* $fd1e12 */
    move.w  LA(LINEA_DELY)(%a6),%d3             /* $fd1e16 */
    move.w  LA(LINEA_L_OFF)(%a6),%d6            /* $fd1e1a */
    add.w   LA(LINEA_R_OFF)(%a6),%d6            /* $fd1e1e */
    movem.w %d0-%d3,-(%sp)                      /* $fd1e22 */
    clr.w   TB_SCRATCH_HALF(%a5)                /* $fd1e26 */
    tst.w   LA(LINEA_SCALE)(%a6)                /* $fd1e2a */
    beq.s   .Lsized                             /* $fd1e2e */
    move.w  %d0,-(%sp)                          /* $fd1e30 */
    move.w  %d2,-(%sp)                          /* $fd1e32 */
    move.w  %d1,-(%sp)                          /* $fd1e34 */
    move.w  %d3,-(%sp)                          /* $fd1e36 */
    bsr.w   vdi_rom_act_siz                     /* $fd1e38 */
    move.w  (%sp)+,%d3                          /* $fd1e3c */
    move.w  %d0,%d3                             /* $fd1e3e */
    move.w  %d0,TB_SCALED_HEIGHT(%a5)           /* $fd1e40 */
    move.w  (%sp)+,%d2                          /* $fd1e44 */
    move.w  LA(LINEA_XACC_DDA)(%a6),%d1         /* $fd1e46 */
    move.w  LA(LINEA_DDA_INC)(%a6),%d0          /* $fd1e4a */
    move.w  %d3,-(%sp)                          /* $fd1e4e */
    moveq   #0,%d3                              /* $fd1e50 */
    bra.s   .Lwidth_columns                     /* $fd1e52 */
.Lwidth_dda:
    add.w   %d0,%d1                             /* $fd1e54 */
    bcc.s   .Lwidth_counted                     /* $fd1e56 */
    addq.w  #1,%d3                              /* $fd1e58 */
.Lwidth_counted:
    btst    #SCALE_UP_BIT,LA(LINEA_T_SCLSTS)+1(%a6) /* $fd1e5a */
    beq.s   .Lwidth_columns                     /* $fd1e60 */
    addq.w  #1,%d3                              /* $fd1e62 */
.Lwidth_columns:
    dbf     %d2,.Lwidth_dda                     /* $fd1e64 */
    move.w  %d1,TB_SCALED_ACCUMULATOR(%a5)      /* $fd1e68 */
    move.w  %d3,%d1                             /* $fd1e6c */
    move.w  %d3,TB_SCALED_WIDTH(%a5)            /* $fd1e6e */
    move.w  (%sp)+,%d3                          /* $fd1e72 */
    move.w  (%sp)+,%d2                          /* $fd1e74 */
    move.w  (%sp)+,%d0                          /* $fd1e76 */
.Lsized:
    clr.w   TB_WEIGHT(%a5)                      /* $fd1e78 */
    btst    #STYLE_THICKEN_BIT,LA(LINEA_STYLE)+1(%a6) /* $fd1e7c */
    beq.s   .Lskew_width                        /* $fd1e82 */
    move.w  LA(LINEA_WEIGHT)(%a6),%d4           /* $fd1e84 */
    bne.s   .Lthicken_mono                      /* $fd1e88 */
    andi.w  #~VDI_STYLE_THICKEN_MASK,LA(LINEA_STYLE)(%a6) /* $fd1e8a */
.Lthicken_mono:
    tst.w   LA(LINEA_MONO_STATUS)(%a6)          /* $fd1e90 */
    bne.s   .Lskew_width                        /* $fd1e94 */
    add.w   %d4,%d1                             /* $fd1e96 */
.Lskew_width:
    btst    #STYLE_SKEW_BIT,LA(LINEA_STYLE)+1(%a6) /* $fd1e98 */
    beq.s   .Loutline_size                      /* $fd1e9e */
    add.w   %d6,%d1                             /* $fd1ea0 */
.Loutline_size:
    btst    #STYLE_OUTLINE_BIT,LA(LINEA_STYLE)+1(%a6) /* $fd1ea2 */
    beq.s   .Lturned_size                       /* $fd1ea8 */
    addq.w  #TEXT_OUTLINE_GROWTH,%d1            /* $fd1eaa */
    addq.w  #TEXT_OUTLINE_GROWTH,%d3            /* $fd1eac */
.Lturned_size:
    move.w  LA(LINEA_CHUP)(%a6),%d4             /* $fd1eae */
    beq.s   .Ltrivial_clip                      /* $fd1eb2 */
    .word   M68K_CMP_W_IMMEDIATE(4), TEXT_ROTATION_90 /* $fd1eb4 cmp.w #900,%d4 */
    bne.s   .Lturn_not_90                       /* $fd1eb8 */
    sub.w   %d1,%d2                             /* $fd1eba */
    move.w  %d2,LA(LINEA_DESTY)(%a6)            /* $fd1ebc */
    exg     %d1,%d3                             /* $fd1ec0 */
    bra.s   .Ltrivial_clip                      /* $fd1ec2 */
.Lturn_not_90:
    .word   M68K_CMP_W_IMMEDIATE(4), TEXT_ROTATION_180 /* $fd1ec4 cmp.w #1800,%d4 */
    bne.s   .Lturn_swap                         /* $fd1ec8 */
    sub.w   %d1,%d0                             /* $fd1eca */
    move.w  %d0,LA(LINEA_DESTX)(%a6)            /* $fd1ecc */
    bra.s   .Ltrivial_clip                      /* $fd1ed0 */
.Lturn_swap:
    exg     %d1,%d3                             /* $fd1ed2 */

/* The trivial clip, before anything is drawn; D5 counts the ends it will cut. */
.Ltrivial_clip:
    moveq   #0,%d5                              /* $fd1ed4 */
    tst.w   LA(LINEA_CLIP)(%a6)                 /* $fd1ed6 */
    beq.s   .Lsource_form                       /* $fd1eda */
    cmp.w   LA(LINEA_YMINCL)(%a6),%d2           /* $fd1edc */
    bge.s   .Ly_from_inside                     /* $fd1ee0 */
    add.w   %d3,%d2                             /* $fd1ee2 */
    addq.w  #1,%d5                              /* $fd1ee4 */
    cmp.w   LA(LINEA_YMINCL)(%a6),%d2           /* $fd1ee6 */
    bgt.s   .Lx_trivial                         /* $fd1eea */
    bra.w   .Lrestore                           /* $fd1eec */
.Ly_from_inside:
    cmp.w   LA(LINEA_YMAXCL)(%a6),%d2           /* $fd1ef0 */
    bgt.w   .Lrestore                           /* $fd1ef4 */
    add.w   %d3,%d2                             /* $fd1ef8 */
    subq.w  #1,%d2                              /* $fd1efa */
    sub.w   LA(LINEA_YMAXCL)(%a6),%d2           /* $fd1efc */
    ble.s   .Lx_trivial                         /* $fd1f00 */
    addq.w  #1,%d5                              /* $fd1f02 */
.Lx_trivial:
    cmp.w   LA(LINEA_XMINCL)(%a6),%d0           /* $fd1f04 */
    bge.s   .Lx_from_inside                     /* $fd1f08 */
    add.w   %d1,%d0                             /* $fd1f0a */
    addq.w  #1,%d5                              /* $fd1f0c */
    cmp.w   LA(LINEA_XMINCL)(%a6),%d0           /* $fd1f0e */
    bgt.s   .Lsource_form                       /* $fd1f12 */
    bra.w   .Lrestore                           /* $fd1f14 */
.Lx_from_inside:
    cmp.w   LA(LINEA_XMAXCL)(%a6),%d0           /* $fd1f18 */
    bgt.w   .Lrestore                           /* $fd1f1c */
    add.w   %d1,%d0                             /* $fd1f20 */
    subq.w  #1,%d0                              /* $fd1f22 */
    cmp.w   LA(LINEA_XMAXCL)(%a6),%d0           /* $fd1f24 */
    ble.s   .Lsource_form                       /* $fd1f28 */
    addq.w  #1,%d5                              /* $fd1f2a */

/* The source is the font form — or, scaled, the scratch copy $fd2b54 makes. */
.Lsource_form:
    move.w  LA(LINEA_FWIDTH)(%a6),TB_SOURCE_STEP(%a5) /* $fd1f2c */
    move.l  LA(LINEA_FBASE)(%a6),TB_SOURCE(%a5) /* $fd1f32 */
    tst.w   LA(LINEA_SCALE)(%a6)                /* $fd1f38 */
    beq.s   .Lprepass_test                      /* $fd1f3c */
    movem.l %d0-%d7,-(%sp)                      /* $fd1f3e */
    bsr.w   .Lscale                             /* $fd1f42 */
    movem.l (%sp)+,%d0-%d7                      /* $fd1f46 */

/* The PRE-PASS, for a turned glyph with any effect, an outline, or an italic the clip cuts: the glyph
 * blitted in one plane, WRT_MODE 7 (op 3, source), thickened and skewed, into the scratch buffer —
 * cleared first for an outline or an italic, and outlined after — which becomes the source. */
.Lprepass_test:
    move.w  LA(LINEA_STYLE)(%a6),%d1            /* $fd1f4a */
    andi.w  #TEXT_PREPASS_EFFECTS,%d1           /* $fd1f4e */
    beq.w   .Lturn_test                         /* $fd1f52 */
    tst.w   LA(LINEA_CHUP)(%a6)                 /* $fd1f56 */
    bne.s   .Lprepass                           /* $fd1f5a */
    btst    #STYLE_SKEW_BIT,%d1                 /* $fd1f5c */
    beq.s   .Lprepass_outline_test              /* $fd1f60 */
    tst.w   %d5                                 /* $fd1f62 */
    bne.s   .Lprepass                           /* $fd1f64 */
.Lprepass_outline_test:
    btst    #STYLE_OUTLINE_BIT,%d1              /* $fd1f66 */
    beq.w   .Lturn_test                         /* $fd1f6a */
.Lprepass:
    move.w  LA(LINEA_SOURCEX)(%a6),%d0          /* $fd1f6e */
    move.w  %d0,%d2                             /* $fd1f72 */
    andi.w  #PIXEL_IN_GROUP_MASK,%d2            /* $fd1f74 */
    move.w  %d2,TB_SOURCE_BIT(%a5)              /* $fd1f78 */
    lsr.w   #4,%d0                              /* $fd1f7c */
    add.w   %d0,%d0                             /* $fd1f7e */
    move.w  LA(LINEA_SOURCEY)(%a6),%d2          /* $fd1f80 */
    move.w  LA(LINEA_DELY)(%a6),TB_HEIGHT(%a5)  /* $fd1f84 */
    add.w   TB_HEIGHT(%a5),%d2                  /* $fd1f8a */
    subq.w  #1,%d2                              /* $fd1f8e */
    mulu.w  TB_SOURCE_STEP(%a5),%d2             /* $fd1f90 */
    neg.w   TB_SOURCE_STEP(%a5)                 /* $fd1f94 */
    movea.l TB_SOURCE(%a5),%a0                  /* $fd1f98 */
    adda.w  %d0,%a0                             /* $fd1f9c */
    adda.l  %d2,%a0                             /* $fd1f9e */
    move.w  LA(LINEA_DELX)(%a6),%d0             /* $fd1fa0 */
    move.w  LA(LINEA_WEIGHT)(%a6),%d1           /* $fd1fa4 */
    btst    #STYLE_THICKEN_BIT,LA(LINEA_STYLE)+1(%a6) /* $fd1fa8 */
    beq.s   .Lprepass_thickened                 /* $fd1fae */
    add.w   %d1,%d0                             /* $fd1fb0 */
    move.w  %d1,TB_WEIGHT(%a5)                  /* $fd1fb2 */
.Lprepass_thickened:
    clr.w   TB_DEST_BIT(%a5)                    /* $fd1fb6 */
    move.w  LA(LINEA_DELY)(%a6),%d1             /* $fd1fba */
    move.w  LA(LINEA_STYLE)(%a6),%d2            /* $fd1fbe */
    btst    #STYLE_OUTLINE_BIT,%d2              /* $fd1fc2 */
    beq.s   .Lprepass_outlined                  /* $fd1fc6 */
    addq.w  #TEXT_OUTLINE_BLIT_WIDTH,%d0        /* $fd1fc8 */
    addq.w  #1,TB_DEST_BIT(%a5)                 /* $fd1fca */
    addq.w  #TEXT_OUTLINE_GROWTH,LA(LINEA_DELY)(%a6) /* $fd1fce */
    addq.w  #TEXT_OUTLINE_BLIT_WIDTH,%d1        /* $fd1fd2 */
.Lprepass_outlined:
    move.w  %d0,TB_WIDTH(%a5)                   /* $fd1fd4 */
    add.w   %d6,%d0                             /* $fd1fd8 */
    move.w  %d0,LA(LINEA_DELX)(%a6)             /* $fd1fda */
    lsr.w   #4,%d0                              /* $fd1fde */
    add.w   %d0,%d0                             /* $fd1fe0 */
    addq.w  #2,%d0                              /* $fd1fe2 */
    neg.w   %d0                                 /* $fd1fe4 */
    move.w  %d0,TB_DEST_STEP(%a5)               /* $fd1fe6 */
    neg.w   %d0                                 /* $fd1fea */
    subq.w  #1,%d1                              /* $fd1fec */
    mulu.w  %d1,%d0                             /* $fd1fee */
    bsr.w   .Lselect_scratch                    /* $fd1ff0 */
    move.l  %a1,-(%sp)                          /* $fd1ff4 */
    btst    #STYLE_OUTLINE_BIT,%d2              /* $fd1ff6 */
    bne.s   .Lprepass_clear                     /* $fd1ffa */
    btst    #STYLE_SKEW_BIT,%d2                 /* $fd1ffc */
    beq.s   .Lprepass_placed                    /* $fd2000 */
.Lprepass_clear:
    move.l  %a1,-(%sp)                          /* $fd2002 */
    move.w  %d0,%d3                             /* $fd2004 */
    sub.w   TB_DEST_STEP(%a5),%d3               /* $fd2006 */
    lsr.w   #1,%d3                              /* $fd200a */
    moveq   #0,%d1                              /* $fd200c */
    bra.s   .Lprepass_clear_words               /* $fd200e */
.Lprepass_clear_word:
    move.w  %d1,(%a1)+                          /* $fd2010 */
.Lprepass_clear_words:
    dbf     %d3,.Lprepass_clear_word            /* $fd2012 */
    movea.l (%sp)+,%a1                          /* $fd2016 */
    btst    #STYLE_OUTLINE_BIT,%d2              /* $fd2018 */
    beq.s   .Lprepass_placed                    /* $fd201c */
    subq.w  #TEXT_OUTLINE_BLIT_WIDTH,TB_WIDTH(%a5) /* $fd201e */
    subq.w  #1,LA(LINEA_DELX)(%a6)              /* $fd2022 */
    add.w   TB_DEST_STEP(%a5),%d0               /* $fd2026 */
.Lprepass_placed:
    adda.w  %d0,%a1                             /* $fd202a */
    move.w  LA(LINEA_WRT_MODE)(%a6),-(%sp)      /* $fd202c */
    move.w  LA(LINEA_STYLE)(%a6),-(%sp)         /* $fd2030 */
    move.w  #TEXT_SCRATCH_WRITE_MODE,LA(LINEA_WRT_MODE)(%a6) /* $fd2034 */
    move.w  #1,TB_FG_BITS(%a5)                  /* $fd203a */
    clr.w   TB_BG_BITS(%a5)                     /* $fd2040 */
    move.w  #1,TB_PLANES_LEFT(%a5)              /* $fd2044 */
    move.w  #2,TB_GROUP_BYTES(%a5)              /* $fd204a */
    andi.w  #TEXT_PREPASS_APPLIED,LA(LINEA_STYLE)(%a6) /* $fd2050 */
    bsr.w   .Lblit                              /* $fd2056 */
    move.w  (%sp)+,LA(LINEA_STYLE)(%a6)         /* $fd205a */
    move.w  (%sp)+,LA(LINEA_WRT_MODE)(%a6)      /* $fd205e */
    movea.l (%sp)+,%a1                          /* $fd2062 */
    move.w  TB_DEST_STEP(%a5),%d7               /* $fd2064 */
    neg.w   %d7                                 /* $fd2068 */
    move.w  %d7,TB_SOURCE_STEP(%a5)             /* $fd206a */
    movea.l %a1,%a0                             /* $fd206e */
    move.l  %a0,TB_SOURCE(%a5)                  /* $fd2070 */
    btst    #STYLE_OUTLINE_BIT,LA(LINEA_STYLE)+1(%a6) /* $fd2074 */
    beq.s   .Lprepass_done                      /* $fd207a */
    ext.l   %d7                                 /* $fd207c */
    add.l   %d7,TB_SOURCE(%a5)                  /* $fd207e */
    bsr.w   .Loutline                           /* $fd2082 */
.Lprepass_done:
    clr.w   LA(LINEA_SOURCEX)(%a6)              /* $fd2086 */
    clr.w   LA(LINEA_SOURCEY)(%a6)              /* $fd208a */
    andi.w  #~TEXT_PREPASS_APPLIED,LA(LINEA_STYLE)(%a6) /* $fd208e */

/* Rotation of the source (a scratch copy), the thickening the pre-pass did not do, and the clip. */
.Lturn_test:
    tst.w   LA(LINEA_CHUP)(%a6)                 /* $fd2094 */
    beq.s   .Lthicken_final                     /* $fd2098 */
    bsr.w   .Lrotate                            /* $fd209a */
.Lthicken_final:
    btst    #STYLE_THICKEN_BIT,LA(LINEA_STYLE)+1(%a6) /* $fd209e */
    beq.s   .Lfinal_clip                        /* $fd20a4 */
    move.w  LA(LINEA_WEIGHT)(%a6),%d0           /* $fd20a6 */
    tst.w   LA(LINEA_MONO_STATUS)(%a6)          /* $fd20aa */
    bne.s   .Lweight_kept                       /* $fd20ae */
    add.w   %d0,LA(LINEA_DELX)(%a6)             /* $fd20b0 */
.Lweight_kept:
    move.w  %d0,TB_WEIGHT(%a5)                  /* $fd20b4 */
.Lfinal_clip:
    tst.w   LA(LINEA_CLIP)(%a6)                 /* $fd20b8 */
    beq.w   .Lblit_to_screen                    /* $fd20bc */
    move.w  LA(LINEA_DESTY)(%a6),%d0            /* $fd20c0 */
    cmp.w   LA(LINEA_YMINCL)(%a6),%d0           /* $fd20c4 */
    bge.s   .Ly_top_clipped                     /* $fd20c8 */
    add.w   LA(LINEA_DELY)(%a6),%d0             /* $fd20ca */
    cmp.w   LA(LINEA_YMINCL)(%a6),%d0           /* $fd20ce */
    ble.w   .Lrestore                           /* $fd20d2 */
    sub.w   LA(LINEA_YMINCL)(%a6),%d0           /* $fd20d6 */
    move.w  LA(LINEA_DELY)(%a6),%d1             /* $fd20da */
    move.w  %d0,LA(LINEA_DELY)(%a6)             /* $fd20de */
    sub.w   %d0,%d1                             /* $fd20e2 */
    add.w   %d1,LA(LINEA_SOURCEY)(%a6)          /* $fd20e4 */
    move.w  LA(LINEA_YMINCL)(%a6),%d0           /* $fd20e8 */
    move.w  %d0,LA(LINEA_DESTY)(%a6)            /* $fd20ec */
.Ly_top_clipped:
    cmp.w   LA(LINEA_YMAXCL)(%a6),%d0           /* $fd20f0 */
    bgt.w   .Lrestore                           /* $fd20f4 */
    add.w   LA(LINEA_DELY)(%a6),%d0             /* $fd20f8 */
    subq.w  #1,%d0                              /* $fd20fc */
    cmp.w   LA(LINEA_YMAXCL)(%a6),%d0           /* $fd20fe */
    ble.s   .Lx_clip                            /* $fd2102 */
    sub.w   LA(LINEA_YMAXCL)(%a6),%d0           /* $fd2104 */
    sub.w   %d0,LA(LINEA_DELY)(%a6)             /* $fd2108 */
.Lx_clip:
    move.w  LA(LINEA_DESTX)(%a6),%d0            /* $fd210c */
    cmp.w   LA(LINEA_XMINCL)(%a6),%d0           /* $fd2110 */
    bge.s   .Lx_left_clipped                    /* $fd2114 */
    add.w   LA(LINEA_DELX)(%a6),%d0             /* $fd2116 */
    cmp.w   LA(LINEA_XMINCL)(%a6),%d0           /* $fd211a */
    ble.w   .Lrestore                           /* $fd211e */
    sub.w   LA(LINEA_XMINCL)(%a6),%d0           /* $fd2122 */
    move.w  LA(LINEA_DELX)(%a6),%d1             /* $fd2126 */
    move.w  %d0,LA(LINEA_DELX)(%a6)             /* $fd212a */
    sub.w   %d0,%d1                             /* $fd212e */
    add.w   %d1,LA(LINEA_SOURCEX)(%a6)          /* $fd2130 */
    move.w  LA(LINEA_XMINCL)(%a6),%d0           /* $fd2134 */
    move.w  %d0,LA(LINEA_DESTX)(%a6)            /* $fd2138 */
.Lx_left_clipped:
    cmp.w   LA(LINEA_XMAXCL)(%a6),%d0           /* $fd213c */
    bgt.w   .Lrestore                           /* $fd2140 */
    add.w   LA(LINEA_DELX)(%a6),%d0             /* $fd2144 */
    subq.w  #1,%d0                              /* $fd2148 */
    cmp.w   LA(LINEA_XMAXCL)(%a6),%d0           /* $fd214a */
    ble.s   .Lclipped                           /* $fd214e */
    sub.w   LA(LINEA_XMAXCL)(%a6),%d0           /* $fd2150 */
    sub.w   %d0,LA(LINEA_DELX)(%a6)             /* $fd2154 */
.Lclipped:
    bra.s   .Lblit_to_screen                    /* $fd2158 */
.Lgroup_bytes_table:
    .byte   0x02, 0x04, 0x00, 0x08              /* $fd215a */

/* The final blit: the op per plane from TEXT_FG / TEXT_BG, a group's bytes from the table by PLANES
 * (TEXT_GROUP_BYTES_TABLE: entry 0 is the low byte of the `bra.s` above), the source and the screen
 * both from their bottom rows, the screen's placed by concat. */
.Lblit_to_screen:
    move.w  LA(LINEA_TEXT_FG)(%a6),TB_FG_BITS(%a5) /* $fd215e */
    move.w  LA(LINEA_TEXT_BG)(%a6),TB_BG_BITS(%a5) /* $fd2164 */
    .word   M68K_MOVE_W_D16(6, 0), LA(LINEA_PLANES) /* $fd216a move.w LA(LINEA_PLANES)(%a6),%d0 */
    move.w  %d0,TB_PLANES_LEFT(%a5)             /* $fd216e */
    move.b  .Lgroup_bytes_table-1(%pc,%d0.w),%d0 /* $fd2172 */
    move.w  %d0,TB_GROUP_BYTES(%a5)             /* $fd2176 */
    move.w  LA(LINEA_SOURCEX)(%a6),%d0          /* $fd217a */
    move.w  %d0,%d2                             /* $fd217e */
    andi.w  #PIXEL_IN_GROUP_MASK,%d2            /* $fd2180 */
    move.w  %d2,TB_SOURCE_BIT(%a5)              /* $fd2184 */
    lsr.w   #4,%d0                              /* $fd2188 */
    add.w   %d0,%d0                             /* $fd218a */
    move.w  LA(LINEA_DELY)(%a6),%d2             /* $fd218c */
    move.w  %d2,TB_HEIGHT(%a5)                  /* $fd2190 */
    add.w   LA(LINEA_SOURCEY)(%a6),%d2          /* $fd2194 */
    subq.w  #1,%d2                              /* $fd2198 */
    mulu.w  TB_SOURCE_STEP(%a5),%d2             /* $fd219a */
    neg.w   TB_SOURCE_STEP(%a5)                 /* $fd219e */
    movea.l TB_SOURCE(%a5),%a0                  /* $fd21a2 */
    adda.w  %d0,%a0                             /* $fd21a6 */
    adda.l  %d2,%a0                             /* $fd21a8 */
    move.w  LA(LINEA_DELX)(%a6),TB_WIDTH(%a5)   /* $fd21aa */
    move.w  LA(LINEA_DESTY)(%a6),%d1            /* $fd21b0 */
    add.w   LA(LINEA_DELY)(%a6),%d1             /* $fd21b4 */
    subq.w  #1,%d1                              /* $fd21b8 */
    move.w  LA(LINEA_DESTX)(%a6),%d0            /* $fd21ba */
    jsr     linea_rom_concat                    /* $fd21be */
    movea.l (SYSVAR_V_BAS_AD).l,%a1             /* $fd21c4 */
    adda.l  %d1,%a1                             /* $fd21ca */
    move.w  %d0,TB_DEST_BIT(%a5)                /* $fd21cc */
    move.w  LA(LINEA_WIDTH)(%a6),%d0            /* $fd21d0 */
    neg.w   %d0                                 /* $fd21d4 */
    move.w  %d0,TB_DEST_STEP(%a5)               /* $fd21d6 */
    bsr.w   .Lblit                              /* $fd21da */

/* The frame restored, and DESTX (or DESTY) advanced past the glyph. */
.Lrestore:
    movem.w (%sp)+,%d0-%d3                      /* $fd21de */
    move.w  %d0,LA(LINEA_DESTX)(%a6)            /* $fd21e2 */
    move.w  %d1,LA(LINEA_DELX)(%a6)             /* $fd21e6 */
    move.w  %d2,LA(LINEA_DESTY)(%a6)            /* $fd21ea */
    move.w  %d3,LA(LINEA_DELY)(%a6)             /* $fd21ee */
    move.w  (%sp)+,LA(LINEA_SKEWMASK)(%a6)      /* $fd21f2 */
    move.w  (%sp)+,LA(LINEA_WRT_MODE)(%a6)      /* $fd21f6 */
    move.w  (%sp)+,LA(LINEA_STYLE)(%a6)         /* $fd21fa */
    tst.w   LA(LINEA_SCALE)(%a6)                /* $fd21fe */
    beq.s   .Ladvance_outline                   /* $fd2202 */
    move.w  TB_SCALED_ACCUMULATOR(%a5),LA(LINEA_XACC_DDA)(%a6) /* $fd2204 */
    move.w  TB_SCALED_WIDTH(%a5),%d1            /* $fd220a */
    move.w  TB_SCALED_HEIGHT(%a5),%d3           /* $fd220e */
    tst.w   TB_SWAPPED_AXES(%a5)                /* $fd2212 */
    beq.s   .Ladvance_outline                   /* $fd2216 */
    exg     %d1,%d3                             /* $fd2218 */
.Ladvance_outline:
    btst    #STYLE_OUTLINE_BIT,LA(LINEA_STYLE)+1(%a6) /* $fd221a */
    beq.s   .Ladvance_thicken                   /* $fd2220 */
    addq.w  #TEXT_OUTLINE_GROWTH,%d1            /* $fd2222 */
    addq.w  #TEXT_OUTLINE_GROWTH,%d3            /* $fd2224 */
.Ladvance_thicken:
    btst    #STYLE_THICKEN_BIT,LA(LINEA_STYLE)+1(%a6) /* $fd2226 */
    beq.s   .Ladvance                           /* $fd222c */
    tst.w   LA(LINEA_MONO_STATUS)(%a6)          /* $fd222e */
    bne.s   .Ladvance                           /* $fd2232 */
    add.w   LA(LINEA_WEIGHT)(%a6),%d1           /* $fd2234 */
.Ladvance:
    move.w  LA(LINEA_CHUP)(%a6),%d0             /* $fd2238 */
    bne.s   .Ladvance_not_0                     /* $fd223c */
    add.w   %d1,LA(LINEA_DESTX)(%a6)            /* $fd223e */
    bra.s   .Ldone                              /* $fd2242 */
.Ladvance_not_0:
    cmpi.w  #TEXT_ROTATION_90,%d0               /* $fd2244 */
    bne.s   .Ladvance_not_90                    /* $fd2248 */
    sub.w   %d1,LA(LINEA_DESTY)(%a6)            /* $fd224a */
    bra.s   .Ldone                              /* $fd224e */
.Ladvance_not_90:
    cmpi.w  #TEXT_ROTATION_180,%d0              /* $fd2250 */
    bne.s   .Ladvance_270                       /* $fd2254 */
    sub.w   %d1,LA(LINEA_DESTX)(%a6)            /* $fd2256 */
    bra.s   .Ldone                              /* $fd225a */
.Ladvance_270:
    add.w   %d1,LA(LINEA_DESTY)(%a6)            /* $fd225c */
.Ldone:
    unlk    %a5                                 /* $fd2260 */
    movem.l (%sp)+,%a5-%a6                      /* $fd2262 */
    rts                                         /* $fd2266 */

/* THE BLIT: the shift between the source's first pixel and the destination's (SIGN set: to the left),
 * the fringe masks, and the row loop the span needs. */
.Lblit:
    move.w  TB_DEST_BIT(%a5),%d1                /* $fd2268 */
    sub.w   TB_SOURCE_BIT(%a5),%d1              /* $fd226c */
    move.w  %d1,%d0                             /* $fd2270 */
    bpl.s   .Lshift_known                       /* $fd2272 */
    neg.w   %d1                                 /* $fd2274 */
    ori.w   #LEFTMOST_BIT,%d1                   /* $fd2276 */
    addi.w  #WORD_BITS,%d0                      /* $fd227a */
.Lshift_known:
    move.w  %d1,TB_SHIFT(%a5)                   /* $fd227e */
    lsl.w   #1,%d0                              /* $fd2282 */
    lea     linea_rom_line_plane_words+(RASTER_FRINGE_MASK_TABLE-LINEA_ROM_LINE_PLANE_WORDS),%a2 /* $fd2284 */
    move.w  0(%a2,%d0.w),%d0                    /* $fd228a */
    not.w   %d0                                 /* $fd228e */
    move.w  %d0,TB_CARRY_MASK(%a5)              /* $fd2290 */
    move.w  TB_DEST_BIT(%a5),%d0                /* $fd2294 */
    lsl.w   #1,%d0                              /* $fd2298 */
    move.w  0(%a2,%d0.w),TB_LEFT_MASK(%a5)      /* $fd229a */
    lsr.w   #1,%d0                              /* $fd22a0 */
    add.w   TB_WIDTH(%a5),%d0                   /* $fd22a2 */
    move.w  %d0,%d2                             /* $fd22a6 */
    sub.w   TB_WEIGHT(%a5),%d2                  /* $fd22a8 */
    andi.w  #PIXEL_IN_GROUP_MASK,%d2            /* $fd22ac */
    lsl.w   #1,%d2                              /* $fd22b0 */
    move.w  0(%a2,%d2.w),%d2                    /* $fd22b2 */
    not.w   %d2                                 /* $fd22b6 */
    move.w  %d2,TB_THICKEN_EDGE(%a5)            /* $fd22b8 */
    clr.w   %d4                                 /* $fd22bc */
    move.w  #LEFTMOST_BIT,TB_SKEW_MASK(%a5)     /* $fd22be */
    moveq   #-1,%d3                             /* $fd22c4 */
    cmpi.w  #TEXT_ONE_WORD_SPAN,%d0             /* $fd22c6 */
    bhi.s   .Lwide_row                          /* $fd22ca */
    lsl.w   #1,%d0                              /* $fd22cc */
    move.w  0(%a2,%d0.w),%d1                    /* $fd22ce */
    not.w   %d1                                 /* $fd22d2 */
    and.w   %d1,TB_LEFT_MASK(%a5)               /* $fd22d4 */
    move.w  #TEXT_ROWS_ONE_WORD,TB_ROW_LOOP(%a5) /* $fd22d8 */
    bra.s   .Lmasks_ready                       /* $fd22de */
.Lwide_row:
    move.w  #TEXT_ROWS_TWO_WORDS,TB_ROW_LOOP(%a5) /* $fd22e0 */
    move.w  %d0,%d1                             /* $fd22e6 */
    lsr.w   #4,%d1                              /* $fd22e8 */
    subq.w  #1,%d1                              /* $fd22ea */
    move.w  %d1,%d3                             /* $fd22ec */
    bne.s   .Lmulti_row                         /* $fd22ee */
    move.w  TB_SOURCE_BIT(%a5),%d1              /* $fd22f0 */
    add.w   TB_WIDTH(%a5),%d1                   /* $fd22f4 */
    cmpi.w  #TEXT_TWO_WORD_SOURCE_SPAN,%d1      /* $fd22f8 */
    bcs.s   .Lright_edge                        /* $fd22fc */
.Lmulti_row:
    move.w  #TEXT_ROWS_RIGHT,TB_ROW_LOOP(%a5)   /* $fd22fe */
    tst.w   TB_SHIFT(%a5)                       /* $fd2304 */
    bpl.s   .Lright_edge                        /* $fd2308 */
    move.w  #TEXT_ROWS_LEFT,TB_ROW_LOOP(%a5)    /* $fd230a */
.Lright_edge:
    andi.w  #PIXEL_IN_GROUP_MASK,%d0            /* $fd2310 */
    bne.s   .Lright_mask                        /* $fd2314 */
    subq.w  #1,%d3                              /* $fd2316 */
    move.w  #WORD_BITS,%d0                      /* $fd2318 */
.Lright_mask:
    lsl.w   #1,%d0                              /* $fd231c */
    move.w  0(%a2,%d0.w),%d4                    /* $fd231e */
    not.w   %d4                                 /* $fd2322 */
.Lmasks_ready:
    move.w  %d3,TB_MIDDLE_WORDS(%a5)            /* $fd2324 */
    move.w  %d4,TB_RIGHT_MASK(%a5)              /* $fd2328 */
    addq.w  #2,%d3                              /* $fd232c */
    cmp.w   %d2,%d4                             /* $fd232e */
    bcs.s   .Lthicken_count_ready               /* $fd2330 */
    addq.w  #1,%d3                              /* $fd2332 */
.Lthicken_count_ready:
    move.b  %d3,TB_THICKEN_WORDS(%a5)           /* $fd2334 */
    move.b  %d3,TB_THICKEN_LEFT(%a5)            /* $fd2338 */

/* Per plane: the op by WRT_MODE * 4 + colour bit * 2 + background bit, and its effect fragments. */
.Lplane:
    move.w  LA(LINEA_WRT_MODE)(%a6),%d0         /* $fd233c */
    lsr.w   TB_FG_BITS(%a5)                     /* $fd2340 */
    roxl.w  #1,%d0                              /* $fd2344 */
    lsr.w   TB_BG_BITS(%a5)                     /* $fd2346 */
    roxl.w  #1,%d0                              /* $fd234a */
    move.b  .Lop_index_table(%pc,%d0.w),%d0     /* $fd234c */
    movea.w .Lop_masked_table(%pc,%d0.w),%a2    /* $fd2350 */
    move.w  %a2,TB_OP_RIGHT(%a5)                /* $fd2354 */
    move.w  %a2,TB_OP_FIRST(%a5)                /* $fd2358 */
    move.w  %a2,TB_OP_EDGE(%a5)                 /* $fd235c */
    move.w  .Lop_whole_table(%pc,%d0.w),TB_OP_MIDDLE(%a5) /* $fd2360 */
    move.w  LA(LINEA_STYLE)(%a6),%d0            /* $fd2366 */
    bne.w   .Leffects                           /* $fd236a */
    bra.w   .Lrun_plane                         /* $fd236e */

/* The op tables: each op's fragment under a mask, and whole (offsets from .Lfragments); then the index
 * bytes by write mode (modes 4..19 are BitBlt's sixteen ops), and after them the ROM's easter egg —
 * which a write mode past 19 reads as indexes. */
.Lop_masked_table:
    .word   .Lmasked_op0 - .Lfragments          /* $fd2372 */
    .word   .Lmasked_op1 - .Lfragments          /* $fd2374 */
    .word   .Lmasked_op2 - .Lfragments          /* $fd2376 */
    .word   .Lmasked_op3 - .Lfragments          /* $fd2378 */
    .word   .Lmasked_op4 - .Lfragments          /* $fd237a */
    .word   .Lmasked_op5 - .Lfragments          /* $fd237c */
    .word   .Lmasked_op6 - .Lfragments          /* $fd237e */
    .word   .Lmasked_op7 - .Lfragments          /* $fd2380 */
    .word   .Lmasked_op8 - .Lfragments          /* $fd2382 */
    .word   .Lmasked_op9 - .Lfragments          /* $fd2384 */
    .word   .Lmasked_op10 - .Lfragments         /* $fd2386 */
    .word   .Lmasked_op11 - .Lfragments         /* $fd2388 */
    .word   .Lmasked_op12 - .Lfragments         /* $fd238a */
    .word   .Lmasked_op13 - .Lfragments         /* $fd238c */
    .word   .Lmasked_op14 - .Lfragments         /* $fd238e */
    .word   .Lmasked_op15 - .Lfragments         /* $fd2390 */
.Lop_whole_table:
    .word   .Lwhole_op0 - .Lfragments           /* $fd2392 */
    .word   .Lwhole_op1 - .Lfragments           /* $fd2394 */
    .word   .Lwhole_op2 - .Lfragments           /* $fd2396 */
    .word   .Lwhole_op3 - .Lfragments           /* $fd2398 */
    .word   .Lwhole_op4 - .Lfragments           /* $fd239a */
    .word   .Lwhole_op5 - .Lfragments           /* $fd239c */
    .word   .Lwhole_op6 - .Lfragments           /* $fd239e */
    .word   .Lwhole_op7 - .Lfragments           /* $fd23a0 */
    .word   .Lwhole_op8 - .Lfragments           /* $fd23a2 */
    .word   .Lwhole_op9 - .Lfragments           /* $fd23a4 */
    .word   .Lwhole_op10 - .Lfragments          /* $fd23a6 */
    .word   .Lwhole_op11 - .Lfragments          /* $fd23a8 */
    .word   .Lwhole_op12 - .Lfragments          /* $fd23aa */
    .word   .Lwhole_op13 - .Lfragments          /* $fd23ac */
    .word   .Lwhole_op14 - .Lfragments          /* $fd23ae */
    .word   .Lwhole_op15 - .Lfragments          /* $fd23b0 */
.Lop_index_table:
    .byte   0x00, 0x00, 0x06, 0x06, 0x08, 0x08, 0x0e, 0x0e, 0x0c, 0x0c, 0x0c, 0x0c, 0x02, 0x02, 0x1a, 0x1a /* $fd23b2 */
    .byte   0x00, 0x1e, 0x00, 0x1e, 0x00, 0x1c, 0x02, 0x1e, 0x00, 0x1a, 0x04, 0x1e, 0x00, 0x18, 0x06, 0x1e /* $fd23c2 */
    .byte   0x00, 0x16, 0x08, 0x1e, 0x00, 0x14, 0x0a, 0x1e, 0x00, 0x12, 0x0c, 0x1e, 0x00, 0x10, 0x0e, 0x1e /* $fd23d2 */
    .byte   0x00, 0x0e, 0x10, 0x1e, 0x00, 0x0c, 0x12, 0x1e, 0x00, 0x0a, 0x14, 0x1e, 0x00, 0x08, 0x16, 0x1e /* $fd23e2 */
    .byte   0x00, 0x06, 0x18, 0x1e, 0x00, 0x04, 0x1a, 0x1e, 0x00, 0x02, 0x1c, 0x1e, 0x00, 0x00, 0x1e, 0x1e /* $fd23f2 */
.Leaster_egg:
    .ascii  "  Dave StaUgas loves Bea Hablig "  /* $fd2402 */

/* An `rts` nothing reaches. */
.Lunreached_rts:
    rts                                         /* $fd2422 */

/* The EFFECT FRAGMENTS STYLE asks for, each put in front of the fragments it replaces. */
.Leffects:
    btst    #STYLE_LIGHTEN_BIT,%d0              /* $fd2424 */
    beq.s   .Lthicken_effect                    /* $fd2428 */
    move.w  LA(LINEA_LITEMASK)(%a6),TB_LIGHTEN_MASK(%a5) /* $fd242a */
    move.w  TB_OP_FIRST(%a5),TB_LIGHTEN_FIRST_NEXT(%a5) /* $fd2430 */
    move.w  #TEXT_FRAGMENT_LIGHTEN_FIRST,TB_OP_FIRST(%a5) /* $fd2436 */
    move.w  TB_OP_EDGE(%a5),TB_LIGHTEN_EDGE_NEXT(%a5) /* $fd243c */
    move.w  #TEXT_FRAGMENT_LIGHTEN_EDGE,TB_OP_EDGE(%a5) /* $fd2442 */
    move.w  TB_OP_MIDDLE(%a5),TB_LIGHTEN_MIDDLE_NEXT(%a5) /* $fd2448 */
    move.w  #TEXT_FRAGMENT_LIGHTEN_MIDDLE,TB_OP_MIDDLE(%a5) /* $fd244e */
.Lthicken_effect:
    btst    #STYLE_THICKEN_BIT,%d0              /* $fd2454 */
    beq.s   .Lskew_effect                       /* $fd2458 */
    clr.w   TB_THICKEN_SPILL(%a5)               /* $fd245a */
    move.w  TB_OP_FIRST(%a5),TB_THICKEN_FIRST_NEXT(%a5) /* $fd245e */
    move.w  #TEXT_FRAGMENT_THICKEN_FIRST,TB_OP_FIRST(%a5) /* $fd2464 */
    move.w  TB_OP_EDGE(%a5),TB_THICKEN_EDGE_NEXT(%a5) /* $fd246a */
    move.w  #TEXT_FRAGMENT_THICKEN_EDGE,TB_OP_EDGE(%a5) /* $fd2470 */
    move.w  TB_OP_MIDDLE(%a5),TB_THICKEN_MIDDLE_NEXT(%a5) /* $fd2476 */
    move.w  #TEXT_FRAGMENT_THICKEN_MIDDLE,TB_OP_MIDDLE(%a5) /* $fd247c */
.Lskew_effect:
    btst    #STYLE_SKEW_BIT,%d0                 /* $fd2482 */
    beq.s   .Lrun_plane                         /* $fd2486 */
    move.w  LA(LINEA_SKEWMASK)(%a6),TB_SKEW_MASK(%a5) /* $fd2488 */
    move.w  TB_OP_FIRST(%a5),TB_SKEW_FIRST_NEXT(%a5) /* $fd248e */
    move.w  #TEXT_FRAGMENT_SKEW,TB_OP_FIRST(%a5) /* $fd2494 */
    cmpi.w  #TEXT_ROWS_ONE_WORD,TB_ROW_LOOP(%a5) /* $fd249a */
    bne.s   .Lskew_two_words                    /* $fd24a0 */
    clr.w   TB_MIDDLE_WORDS(%a5)                /* $fd24a2 */
    move.w  #TEXT_ROWS_TWO_WORDS,TB_ROW_LOOP(%a5) /* $fd24a6 */
    bra.s   .Lrun_plane                         /* $fd24ac */
.Lskew_two_words:
    cmpi.w  #TEXT_ROWS_TWO_WORDS,TB_ROW_LOOP(%a5) /* $fd24ae */
    bne.s   .Lrun_plane                         /* $fd24b4 */
    cmpi.w  #TEXT_ONE_WORD_SPAN,TB_WIDTH(%a5)   /* $fd24b6 */
    bls.s   .Lrun_plane                         /* $fd24bc */
    move.w  #TEXT_ROWS_RIGHT,TB_ROW_LOOP(%a5)   /* $fd24be */
    tst.w   TB_SHIFT(%a5)                       /* $fd24c4 */
    bpl.s   .Lrun_plane                         /* $fd24c8 */
    move.w  #TEXT_ROWS_LEFT,TB_ROW_LOOP(%a5)    /* $fd24ca */

/* One plane: the row loop `jsr`ed at its offset from .Lfragments, then the next plane — the masks
 * recomputed first for italics. */
.Lrun_plane:
    move.w  TB_LEFT_MASK(%a5),%d2               /* $fd24d0 */
    move.w  TB_HEIGHT(%a5),%d3                  /* $fd24d4 */
    movea.l #.Lfragments,%a3                    /* $fd24d8 */
    movea.w TB_ROW_LOOP(%a5),%a4                /* $fd24de */
    movem.l %a0-%a1,-(%sp)                      /* $fd24e2 */
    jsr     0(%a3,%a4.w)                        /* $fd24e6 */
    movem.l (%sp)+,%a0-%a1                      /* $fd24ea */
    addq.l  #2,%a1                              /* $fd24ee */
    subq.w  #1,TB_PLANES_LEFT(%a5)              /* $fd24f0 */
    bne.s   .Lnext_plane                        /* $fd24f4 */
    rts                                         /* $fd24f6 */
.Lnext_plane:
    btst    #STYLE_SKEW_BIT,LA(LINEA_STYLE)+1(%a6) /* $fd24f8 */
    beq.w   .Lplane                             /* $fd24fe */
    bra.w   .Lblit                              /* $fd2502 */

/* THE ROW LOOPS, each `jsr`ed at TB_ROW_LOOP from here: one word a row and two (entered at their
 * `dbf`), and a run of words shifted left or right. The two multi-word loops are one loop in two
 * directions, and the skew step between rows (.Lskew_step) branches from either into either. */
.Lfragments:
    move.w  (%a1),%d4                           /* $fd2506 */
    move.l  (%a0),%d0                           /* $fd2508 */
    move.w  TB_SHIFT(%a5),%d1                   /* $fd250a */
    bmi.s   .Lone_word_left                     /* $fd250e */
    lsr.l   %d1,%d0                             /* $fd2510 */
    bra.s   .Lone_word_shifted                  /* $fd2512 */
.Lone_word_left:
    lsl.l   %d1,%d0                             /* $fd2514 */
.Lone_word_shifted:
    swap    %d0                                 /* $fd2516 */
    move.w  %d0,%d1                             /* $fd2518 */
    swap    %d0                                 /* $fd251a */
    movea.w TB_OP_FIRST(%a5),%a4                /* $fd251c */
    jsr     0(%a3,%a4.w)                        /* $fd2520 */
    move.w  %d1,(%a1)                           /* $fd2524 */
    adda.w  TB_SOURCE_STEP(%a5),%a0             /* $fd2526 */
    adda.w  TB_DEST_STEP(%a5),%a1               /* $fd252a */
.Lone_word_rows:
    dbf     %d3,.Lfragments                     /* $fd252e */
    rts                                         /* $fd2532 */
.Ltwo_word_row:
    move.w  (%a1),%d4                           /* $fd2534 */
    move.l  (%a0),%d0                           /* $fd2536 */
    move.w  TB_SHIFT(%a5),%d1                   /* $fd2538 */
    bmi.s   .Ltwo_word_left                     /* $fd253c */
    lsr.l   %d1,%d0                             /* $fd253e */
    bra.s   .Ltwo_word_shifted                  /* $fd2540 */
.Ltwo_word_left:
    lsl.l   %d1,%d0                             /* $fd2542 */
.Ltwo_word_shifted:
    swap    %d0                                 /* $fd2544 */
    move.w  %d0,%d1                             /* $fd2546 */
    swap    %d0                                 /* $fd2548 */
    move.w  TB_LEFT_MASK(%a5),%d2               /* $fd254a */
    movea.w TB_OP_FIRST(%a5),%a4                /* $fd254e */
    jsr     0(%a3,%a4.w)                        /* $fd2552 */
    move.w  %d1,(%a1)                           /* $fd2556 */
    move.w  %d0,%d1                             /* $fd2558 */
    move.w  TB_GROUP_BYTES(%a5),%d5             /* $fd255a */
    move.w  0(%a1,%d5.w),%d4                    /* $fd255e */
    move.w  TB_RIGHT_MASK(%a5),%d2              /* $fd2562 */
    movea.w TB_OP_RIGHT(%a5),%a4                /* $fd2566 */
    jsr     0(%a3,%a4.w)                        /* $fd256a */
    move.w  %d1,0(%a1,%d5.w)                    /* $fd256e */
    adda.w  TB_SOURCE_STEP(%a5),%a0             /* $fd2572 */
    adda.w  TB_DEST_STEP(%a5),%a1               /* $fd2576 */
.Ltwo_word_rows:
    dbf     %d3,.Ltwo_word_row                  /* $fd257a */
    rts                                         /* $fd257e */
.Lrows_left:
    movem.l %a0-%a1,-(%sp)                      /* $fd2580 */
    move.w  TB_MIDDLE_WORDS(%a5),%d7            /* $fd2584 */
    move.l  (%a0)+,%d0                          /* $fd2588 */
    move.w  (%a1),%d4                           /* $fd258a */
    move.w  TB_SHIFT(%a5),%d1                   /* $fd258c */
    lsl.l   %d1,%d0                             /* $fd2590 */
    swap    %d0                                 /* $fd2592 */
    move.w  %d0,%d1                             /* $fd2594 */
    swap    %d0                                 /* $fd2596 */
    move.w  TB_LEFT_MASK(%a5),%d2               /* $fd2598 */
    movea.w TB_OP_EDGE(%a5),%a4                 /* $fd259c */
    jsr     0(%a3,%a4.w)                        /* $fd25a0 */
    move.w  %d1,(%a1)                           /* $fd25a4 */
    adda.w  TB_GROUP_BYTES(%a5),%a1             /* $fd25a6 */
    move.w  TB_CARRY_MASK(%a5),%d2              /* $fd25aa */
.Lleft_word:
    move.w  %d0,%d4                             /* $fd25ae */
    and.w   %d2,%d4                             /* $fd25b0 */
    move.w  (%a0)+,%d0                          /* $fd25b2 */
    swap    %d0                                 /* $fd25b4 */
    move.w  %d1,%d0                             /* $fd25b6 */
    swap    %d0                                 /* $fd25b8 */
    move.w  TB_SHIFT(%a5),%d1                   /* $fd25ba */
    lsl.l   %d1,%d0                             /* $fd25be */
    swap    %d0                                 /* $fd25c0 */
    move.w  %d0,%d1                             /* $fd25c2 */
    swap    %d0                                 /* $fd25c4 */
    not.w   %d2                                 /* $fd25c6 */
    and.w   %d2,%d1                             /* $fd25c8 */
    not.w   %d2                                 /* $fd25ca */
    eor.w   %d4,%d1                             /* $fd25cc */
    move.w  (%a1),%d4                           /* $fd25ce */
    tst.w   %d7                                 /* $fd25d0 */
    beq.s   .Lleft_last                         /* $fd25d2 */
    movea.w TB_OP_MIDDLE(%a5),%a4               /* $fd25d4 */
    jsr     0(%a3,%a4.w)                        /* $fd25d8 */
    move.w  %d1,(%a1)                           /* $fd25dc */
    adda.w  TB_GROUP_BYTES(%a5),%a1             /* $fd25de */
    subq.w  #1,%d7                              /* $fd25e2 */
    bra.s   .Lleft_word                         /* $fd25e4 */
.Lleft_last:
    move.w  TB_RIGHT_MASK(%a5),%d2              /* $fd25e6 */
    movea.w TB_OP_EDGE(%a5),%a4                 /* $fd25ea */
    jsr     0(%a3,%a4.w)                        /* $fd25ee */
    move.w  %d1,(%a1)                           /* $fd25f2 */
    movem.l (%sp)+,%a0-%a1                      /* $fd25f4 */
    adda.w  TB_SOURCE_STEP(%a5),%a0             /* $fd25f8 */
    adda.w  TB_DEST_STEP(%a5),%a1               /* $fd25fc */
    clr.w   TB_THICKEN_SPILL(%a5)               /* $fd2600 */
    subq.w  #1,%d3                              /* $fd2604 */
    beq.s   .Lleft_done                         /* $fd2606 */
    rol.w   TB_LIGHTEN_MASK(%a5)                /* $fd2608 */
    btst    #STYLE_SKEW_BIT,LA(LINEA_STYLE)+1(%a6) /* $fd260c */
    bne.w   .Lskew_step                         /* $fd2612 */
    bra.w   .Lrows_left                         /* $fd2616 */
.Lleft_done:
    rts                                         /* $fd261a */
.Lrows_right:
    movem.l %a0-%a1,-(%sp)                      /* $fd261c */
    move.w  TB_MIDDLE_WORDS(%a5),%d7            /* $fd2620 */
    move.w  (%a0)+,%d0                          /* $fd2624 */
    swap    %d0                                 /* $fd2626 */
    move.w  (%a1),%d4                           /* $fd2628 */
    move.w  TB_SHIFT(%a5),%d1                   /* $fd262a */
    lsr.l   %d1,%d0                             /* $fd262e */
    swap    %d0                                 /* $fd2630 */
    move.w  %d0,%d1                             /* $fd2632 */
    swap    %d0                                 /* $fd2634 */
    move.w  TB_LEFT_MASK(%a5),%d2               /* $fd2636 */
    movea.w TB_OP_EDGE(%a5),%a4                 /* $fd263a */
    jsr     0(%a3,%a4.w)                        /* $fd263e */
    move.w  %d1,(%a1)                           /* $fd2642 */
    adda.w  TB_GROUP_BYTES(%a5),%a1             /* $fd2644 */
    move.w  TB_CARRY_MASK(%a5),%d2              /* $fd2648 */
.Lright_word:
    move.w  %d0,%d4                             /* $fd264c */
    and.w   %d2,%d4                             /* $fd264e */
    swap    %d0                                 /* $fd2650 */
    move.w  (%a0)+,%d0                          /* $fd2652 */
    swap    %d0                                 /* $fd2654 */
    move.w  TB_SHIFT(%a5),%d1                   /* $fd2656 */
    lsr.l   %d1,%d0                             /* $fd265a */
    swap    %d0                                 /* $fd265c */
    move.w  %d0,%d1                             /* $fd265e */
    swap    %d0                                 /* $fd2660 */
    not.w   %d2                                 /* $fd2662 */
    and.w   %d2,%d1                             /* $fd2664 */
    not.w   %d2                                 /* $fd2666 */
    eor.w   %d4,%d1                             /* $fd2668 */
    move.w  (%a1),%d4                           /* $fd266a */
    tst.w   %d7                                 /* $fd266c */
    beq.s   .Lright_last                        /* $fd266e */
    movea.w TB_OP_MIDDLE(%a5),%a4               /* $fd2670 */
    jsr     0(%a3,%a4.w)                        /* $fd2674 */
    move.w  %d1,(%a1)                           /* $fd2678 */
    adda.w  TB_GROUP_BYTES(%a5),%a1             /* $fd267a */
    subq.w  #1,%d7                              /* $fd267e */
    bra.s   .Lright_word                        /* $fd2680 */
.Lright_last:
    move.w  TB_RIGHT_MASK(%a5),%d2              /* $fd2682 */
    movea.w TB_OP_EDGE(%a5),%a4                 /* $fd2686 */
    jsr     0(%a3,%a4.w)                        /* $fd268a */
    move.w  %d1,(%a1)                           /* $fd268e */
    movem.l (%sp)+,%a0-%a1                      /* $fd2690 */
    adda.w  TB_SOURCE_STEP(%a5),%a0             /* $fd2694 */
    adda.w  TB_DEST_STEP(%a5),%a1               /* $fd2698 */
    clr.w   TB_THICKEN_SPILL(%a5)               /* $fd269c */
    subq.w  #1,%d3                              /* $fd26a0 */
    beq.s   .Lright_done                        /* $fd26a2 */
    rol.w   TB_LIGHTEN_MASK(%a5)                /* $fd26a4 */
    btst    #STYLE_SKEW_BIT,LA(LINEA_STYLE)+1(%a6) /* $fd26a8 */
    bne.w   .Lskew_step                         /* $fd26ae */
    bra.w   .Lrows_right                        /* $fd26b2 */
.Lright_done:
    rts                                         /* $fd26b6 */

/* THE OP FRAGMENTS: D1 = the source word, D4 = the screen word, D2 = the mask; the answer in D1. The
 * sixteen masked ops (the op inside D2, the screen outside it), then the sixteen whole-word ones. */
.Lmasked_op0:
    not.w   %d2                                 /* $fd26b8 */
    and.w   %d2,%d4                             /* $fd26ba */
    not.w   %d2                                 /* $fd26bc */
    move.w  %d4,%d1                             /* $fd26be */
    rts                                         /* $fd26c0 */
.Lmasked_op1:
    not.w   %d2                                 /* $fd26c2 */
    or.w    %d2,%d1                             /* $fd26c4 */
    not.w   %d2                                 /* $fd26c6 */
    and.w   %d4,%d1                             /* $fd26c8 */
    rts                                         /* $fd26ca */
.Lmasked_op2:
    not.w   %d1                                 /* $fd26cc */
    and.w   %d2,%d1                             /* $fd26ce */
    or.w    %d4,%d1                             /* $fd26d0 */
    eor.w   %d2,%d1                             /* $fd26d2 */
    rts                                         /* $fd26d4 */
.Lmasked_op3:
    eor.w   %d4,%d1                             /* $fd26d6 */
    and.w   %d2,%d1                             /* $fd26d8 */
    eor.w   %d4,%d1                             /* $fd26da */
    rts                                         /* $fd26dc */
.Lmasked_op4:
    and.w   %d2,%d1                             /* $fd26de */
    not.w   %d1                                 /* $fd26e0 */
    and.w   %d4,%d1                             /* $fd26e2 */
    rts                                         /* $fd26e4 */
.Lmasked_op5:
    move.w  %d4,%d1                             /* $fd26e6 */
    rts                                         /* $fd26e8 */
.Lmasked_op6:
    and.w   %d2,%d1                             /* $fd26ea */
    eor.w   %d4,%d1                             /* $fd26ec */
    rts                                         /* $fd26ee */
.Lmasked_op7:
    and.w   %d2,%d1                             /* $fd26f0 */
    or.w    %d4,%d1                             /* $fd26f2 */
    rts                                         /* $fd26f4 */
.Lmasked_op8:
    and.w   %d2,%d1                             /* $fd26f6 */
    or.w    %d4,%d1                             /* $fd26f8 */
    eor.w   %d2,%d1                             /* $fd26fa */
    rts                                         /* $fd26fc */
.Lmasked_op9:
    and.w   %d2,%d1                             /* $fd26fe */
    eor.w   %d4,%d1                             /* $fd2700 */
    eor.w   %d2,%d1                             /* $fd2702 */
    rts                                         /* $fd2704 */
.Lmasked_op10:
    move.w  %d4,%d1                             /* $fd2706 */
    eor.w   %d2,%d1                             /* $fd2708 */
    rts                                         /* $fd270a */
.Lmasked_op11:
    eor.w   %d2,%d4                             /* $fd270c */
    and.w   %d2,%d1                             /* $fd270e */
    or.w    %d4,%d1                             /* $fd2710 */
    rts                                         /* $fd2712 */
.Lmasked_op12:
    eor.w   %d4,%d1                             /* $fd2714 */
    and.w   %d2,%d1                             /* $fd2716 */
    eor.w   %d4,%d1                             /* $fd2718 */
    eor.w   %d2,%d1                             /* $fd271a */
    rts                                         /* $fd271c */
.Lmasked_op13:
    not.w   %d1                                 /* $fd271e */
    and.w   %d2,%d1                             /* $fd2720 */
    or.w    %d4,%d1                             /* $fd2722 */
    rts                                         /* $fd2724 */
.Lmasked_op14:
    not.w   %d1                                 /* $fd2726 */
    and.w   %d2,%d1                             /* $fd2728 */
    eor.w   %d2,%d4                             /* $fd272a */
    or.w    %d4,%d1                             /* $fd272c */
    rts                                         /* $fd272e */
.Lmasked_op15:
    or.w    %d2,%d4                             /* $fd2730 */
    move.w  %d4,%d1                             /* $fd2732 */
    rts                                         /* $fd2734 */
.Lwhole_op0:
    moveq   #0,%d1                              /* $fd2736 */
    rts                                         /* $fd2738 */
.Lwhole_op1:
    and.w   %d4,%d1                             /* $fd273a */
    rts                                         /* $fd273c */
.Lwhole_op2:
    not.w   %d4                                 /* $fd273e */
    and.w   %d4,%d1                             /* $fd2740 */
    rts                                         /* $fd2742 */
.Lwhole_op3:
    rts                                         /* $fd2744 */
.Lwhole_op4:
    not.w   %d1                                 /* $fd2746 */
    and.w   %d4,%d1                             /* $fd2748 */
    rts                                         /* $fd274a */
.Lwhole_op5:
    move.w  %d4,%d1                             /* $fd274c */
    rts                                         /* $fd274e */
.Lwhole_op6:
    eor.w   %d4,%d1                             /* $fd2750 */
    rts                                         /* $fd2752 */
.Lwhole_op7:
    or.w    %d4,%d1                             /* $fd2754 */
    rts                                         /* $fd2756 */
.Lwhole_op8:
    or.w    %d4,%d1                             /* $fd2758 */
    not.w   %d1                                 /* $fd275a */
    rts                                         /* $fd275c */
.Lwhole_op9:
    eor.w   %d4,%d1                             /* $fd275e */
    not.w   %d1                                 /* $fd2760 */
    rts                                         /* $fd2762 */
.Lwhole_op10:
    move.w  %d4,%d1                             /* $fd2764 */
    not.w   %d1                                 /* $fd2766 */
    rts                                         /* $fd2768 */
.Lwhole_op11:
    not.w   %d4                                 /* $fd276a */
    or.w    %d4,%d1                             /* $fd276c */
    rts                                         /* $fd276e */
.Lwhole_op12:
    not.w   %d1                                 /* $fd2770 */
    rts                                         /* $fd2772 */
.Lwhole_op13:
    not.w   %d1                                 /* $fd2774 */
    or.w    %d4,%d1                             /* $fd2776 */
    rts                                         /* $fd2778 */
.Lwhole_op14:
    and.w   %d4,%d1                             /* $fd277a */
    not.w   %d1                                 /* $fd277c */
    rts                                         /* $fd277e */
.Lwhole_op15:
    moveq   #-1,%d1                             /* $fd2780 */
    rts                                         /* $fd2782 */

/* THICKEN: the first word of a one- or two-word row, a middle word, an edge word — each smears the glyph
 * right by the weight and hands on what spilled. */
.Lthicken_first:
    and.w   %d2,%d1                             /* $fd2784 */
    move.w  TB_THICKEN_EDGE(%a5),%d6            /* $fd2786 */
    btst    #0,TB_SKEW_MASK+1(%a5)              /* $fd278a */
    beq.s   .Lthicken_first_cut                 /* $fd2790 */
    ori.b   #CCR_X,%ccr                         /* $fd2792 */
    roxr.w  #1,%d6                              /* $fd2796 */
    bcc.s   .Lthicken_edge_stepped              /* $fd2798 */
    move.w  #LEFTMOST_BIT,%d6                   /* $fd279a */
.Lthicken_edge_stepped:
    move.w  %d6,TB_THICKEN_EDGE(%a5)            /* $fd279e */
.Lthicken_first_cut:
    tst.w   TB_MIDDLE_WORDS(%a5)                /* $fd27a2 */
    bmi.s   .Lthicken_first_alone               /* $fd27a6 */
    cmp.w   TB_RIGHT_MASK(%a5),%d6              /* $fd27a8 */
    bcc.s   .Lthicken_first_alone               /* $fd27ac */
    and.w   %d6,%d0                             /* $fd27ae */
    bra.s   .Lthicken_first_room                /* $fd27b0 */
.Lthicken_first_alone:
    clr.w   %d0                                 /* $fd27b2 */
    and.w   %d6,%d1                             /* $fd27b4 */
.Lthicken_first_room:
    move.w  TB_WEIGHT(%a5),%d6                  /* $fd27b6 */
    move.w  %d2,%d5                             /* $fd27ba */
    swap    %d5                                 /* $fd27bc */
    move.w  TB_RIGHT_MASK(%a5),%d5              /* $fd27be */
    lsl.l   %d6,%d5                             /* $fd27c2 */
    swap    %d5                                 /* $fd27c4 */
    move.w  %d5,%d7                             /* $fd27c6 */
    swap    %d5                                 /* $fd27c8 */
    and.w   %d7,%d1                             /* $fd27ca */
    and.w   %d5,%d0                             /* $fd27cc */
    swap    %d1                                 /* $fd27ce */
    move.w  %d0,%d1                             /* $fd27d0 */
    bra.s   .Lthicken_first_smears              /* $fd27d2 */
.Lthicken_first_smear:
    move.l  %d1,%d0                             /* $fd27d4 */
    lsr.l   #1,%d0                              /* $fd27d6 */
    or.l    %d0,%d1                             /* $fd27d8 */
.Lthicken_first_smears:
    dbf     %d6,.Lthicken_first_smear           /* $fd27da */
    move.w  %d1,%d0                             /* $fd27de */
    swap    %d1                                 /* $fd27e0 */
    movea.w TB_THICKEN_FIRST_NEXT(%a5),%a4      /* $fd27e2 */
    jmp     0(%a3,%a4.w)                        /* $fd27e6 */
.Lthicken_middle:
    subq.b  #1,TB_THICKEN_LEFT(%a5)             /* $fd27ea */
    bne.s   .Lthicken_middle_cut                /* $fd27ee */
    and.w   TB_THICKEN_EDGE(%a5),%d1            /* $fd27f0 */
.Lthicken_middle_cut:
    move.w  TB_WEIGHT(%a5),%d6                  /* $fd27f4 */
    swap    %d1                                 /* $fd27f8 */
    clr.w   %d1                                 /* $fd27fa */
    move.l  %d1,%d5                             /* $fd27fc */
    bra.s   .Lthicken_middle_smears             /* $fd27fe */
.Lthicken_middle_smear:
    lsr.l   #1,%d5                              /* $fd2800 */
    or.l    %d5,%d1                             /* $fd2802 */
.Lthicken_middle_smears:
    dbf     %d6,.Lthicken_middle_smear          /* $fd2804 */
    move.w  %d1,%d5                             /* $fd2808 */
    swap    %d1                                 /* $fd280a */
    or.w    TB_THICKEN_SPILL(%a5),%d1           /* $fd280c */
    move.w  %d5,TB_THICKEN_SPILL(%a5)           /* $fd2810 */
    movea.w TB_THICKEN_MIDDLE_NEXT(%a5),%a4     /* $fd2814 */
    jmp     0(%a3,%a4.w)                        /* $fd2818 */
.Lthicken_edge:
    move.w  TB_THICKEN_EDGE(%a5),%d6            /* $fd281c */
    subq.b  #1,TB_THICKEN_LEFT(%a5)             /* $fd2820 */
    bmi.s   .Lthicken_edge_none                 /* $fd2824 */
    beq.s   .Lthicken_edge_last                 /* $fd2826 */
    subq.b  #1,TB_THICKEN_LEFT(%a5)             /* $fd2828 */
    bne.s   .Lthicken_edge_inside               /* $fd282c */
    and.w   %d6,%d1                             /* $fd282e */
.Lthicken_edge_inside:
    and.w   TB_LEFT_MASK(%a5),%d1               /* $fd2830 */
    bra.s   .Lthicken_edge_smear_start          /* $fd2834 */
.Lthicken_edge_none:
    clr.w   %d1                                 /* $fd2836 */
    bra.s   .Lthicken_recount                   /* $fd2838 */
.Lthicken_edge_last:
    and.w   %d6,%d1                             /* $fd283a */
.Lthicken_recount:
    tst.w   TB_SKEW_MASK(%a5)                   /* $fd283c */
    bmi.s   .Lthicken_reload                    /* $fd2840 */
    move.w  TB_MIDDLE_WORDS(%a5),%d5            /* $fd2842 */
    addq.w  #2,%d5                              /* $fd2846 */
    swap    %d7                                 /* $fd2848 */
    move.w  TB_RIGHT_MASK(%a5),%d7              /* $fd284a */
    ori.b   #CCR_X,%ccr                         /* $fd284e */
    roxr.w  #1,%d7                              /* $fd2852 */
    bcc.s   .Lrecount_right                     /* $fd2854 */
    move.w  #LEFTMOST_BIT,%d7                   /* $fd2856 */
    addq.w  #1,%d5                              /* $fd285a */
.Lrecount_right:
    cmpi.w  #1,TB_LEFT_MASK(%a5)                /* $fd285c */
    bne.s   .Lrecount_left                      /* $fd2862 */
    subq.w  #1,%d5                              /* $fd2864 */
.Lrecount_left:
    ori.b   #CCR_X,%ccr                         /* $fd2866 */
    roxr.w  #1,%d6                              /* $fd286a */
    bcc.s   .Lrecount_edge                      /* $fd286c */
    move.w  #LEFTMOST_BIT,%d6                   /* $fd286e */
.Lrecount_edge:
    cmp.w   %d6,%d7                             /* $fd2872 */
    bcs.s   .Lrecount_done                      /* $fd2874 */
    addq.w  #1,%d5                              /* $fd2876 */
.Lrecount_done:
    swap    %d7                                 /* $fd2878 */
    move.w  %d6,TB_THICKEN_EDGE(%a5)            /* $fd287a */
    move.b  %d5,TB_THICKEN_WORDS(%a5)           /* $fd287e */
.Lthicken_reload:
    move.b  TB_THICKEN_WORDS(%a5),TB_THICKEN_LEFT(%a5) /* $fd2882 */
.Lthicken_edge_smear_start:
    move.w  TB_WEIGHT(%a5),%d6                  /* $fd2888 */
    swap    %d1                                 /* $fd288c */
    clr.w   %d1                                 /* $fd288e */
    move.l  %d1,%d5                             /* $fd2890 */
    bra.s   .Lthicken_edge_smears               /* $fd2892 */
.Lthicken_edge_smear:
    lsr.l   #1,%d5                              /* $fd2894 */
    or.l    %d5,%d1                             /* $fd2896 */
.Lthicken_edge_smears:
    dbf     %d6,.Lthicken_edge_smear            /* $fd2898 */
    move.w  %d1,%d5                             /* $fd289c */
    swap    %d1                                 /* $fd289e */
    or.w    TB_THICKEN_SPILL(%a5),%d1           /* $fd28a0 */
    move.w  %d5,TB_THICKEN_SPILL(%a5)           /* $fd28a4 */
    and.w   %d2,%d1                             /* $fd28a8 */
    movea.w TB_THICKEN_EDGE_NEXT(%a5),%a4       /* $fd28aa */
    jmp     0(%a3,%a4.w)                        /* $fd28ae */

/* LIGHTEN: the glyph under the rotating LITEMASK. */
.Llighten_first:
    and.w   TB_LIGHTEN_MASK(%a5),%d1            /* $fd28b2 */
    and.w   TB_LIGHTEN_MASK(%a5),%d0            /* $fd28b6 */
    rol.w   TB_LIGHTEN_MASK(%a5)                /* $fd28ba */
    movea.w TB_LIGHTEN_FIRST_NEXT(%a5),%a4      /* $fd28be */
    jmp     0(%a3,%a4.w)                        /* $fd28c2 */
.Llighten_middle:
    and.w   TB_LIGHTEN_MASK(%a5),%d1            /* $fd28c6 */
    movea.w TB_LIGHTEN_MIDDLE_NEXT(%a5),%a4     /* $fd28ca */
    jmp     0(%a3,%a4.w)                        /* $fd28ce */
.Llighten_edge:
    and.w   TB_LIGHTEN_MASK(%a5),%d1            /* $fd28d2 */
    movea.w TB_LIGHTEN_EDGE_NEXT(%a5),%a4       /* $fd28d6 */
    jmp     0(%a3,%a4.w)                        /* $fd28da */

/* SKEW, a two-word row's first word: when SKEWMASK's top bit rotates out (C set), the glyph and both
 * masks a pixel right — into the next word when the left mask runs out. */
.Lskew_first:
    rol.w   TB_SKEW_MASK(%a5)                   /* $fd28de */
    bcc.s   .Lskew_first_next                   /* $fd28e2 */
    swap    %d1                                 /* $fd28e4 */
    move.w  %d0,%d1                             /* $fd28e6 */
    lsr.l   #1,%d1                              /* $fd28e8 */
    swap    %d2                                 /* $fd28ea */
    move.w  TB_RIGHT_MASK(%a5),%d2              /* $fd28ec */
    lsr.l   #1,%d2                              /* $fd28f0 */
    move.w  %d2,TB_RIGHT_MASK(%a5)              /* $fd28f2 */
    swap    %d2                                 /* $fd28f6 */
    move.w  %d2,TB_LEFT_MASK(%a5)               /* $fd28f8 */
    beq.s   .Lskew_next_word                    /* $fd28fc */
    move.w  TB_SHIFT(%a5),%d0                   /* $fd28fe */
    bmi.s   .Lskew_left_less                    /* $fd2902 */
.Lskew_right_more:
    addq.w  #1,%d0                              /* $fd2904 */
.Lskew_shift_stored:
    move.w  %d0,TB_SHIFT(%a5)                   /* $fd2906 */
    move.w  %d1,%d0                             /* $fd290a */
    swap    %d1                                 /* $fd290c */
.Lskew_first_next:
    movea.w TB_SKEW_FIRST_NEXT(%a5),%a4         /* $fd290e */
    jmp     0(%a3,%a4.w)                        /* $fd2912 */
.Lskew_left_less:
    tst.b   %d0                                 /* $fd2916 */
    beq.s   .Lskew_left_to_right                /* $fd2918 */
    subq.w  #1,%d0                              /* $fd291a */
    bra.s   .Lskew_shift_stored                 /* $fd291c */
.Lskew_left_to_right:
    clr.w   %d0                                 /* $fd291e */
    bra.s   .Lskew_right_more                   /* $fd2920 */
.Lskew_next_word:
    move.w  %d2,TB_RIGHT_MASK(%a5)              /* $fd2922 */
    swap    %d2                                 /* $fd2926 */
    move.w  %d2,TB_LEFT_MASK(%a5)               /* $fd2928 */
    adda.w  TB_GROUP_BYTES(%a5),%a1             /* $fd292c */
    move.w  (%a1),%d4                           /* $fd2930 */
    move.w  #LAST_BIT_IN_WORD,%d0               /* $fd2932 */
    sub.w   TB_SHIFT(%a5),%d0                   /* $fd2936 */
    ori.w   #LEFTMOST_BIT,%d0                   /* $fd293a */
    move.w  %d0,TB_SHIFT(%a5)                   /* $fd293e */
    bra.s   .Lskew_first_next                   /* $fd2942 */

/* The SKEW STEP between the rows of a multi-word loop: it steps when the bit SKEWMASK rotates out is
 * CLEAR — the opposite of the two-word fragment — and continues in the loop the new shift needs. */
.Lskew_step:
    rol.w   TB_SKEW_MASK(%a5)                   /* $fd2944 */
    bcc.s   .Lskew_stepped                      /* $fd2948 */
    tst.w   TB_SHIFT(%a5)                       /* $fd294a */
    bmi.w   .Lrows_left                         /* $fd294e */
    bra.w   .Lrows_right                        /* $fd2952 */
.Lskew_stepped:
    ori.b   #CCR_X,%ccr                         /* $fd2956 */
    roxr.w  TB_CARRY_MASK(%a5)                  /* $fd295a */
    move.w  TB_RIGHT_MASK(%a5),%d0              /* $fd295e */
    .word   M68K_CMP_W_IMMEDIATE(0), WHOLE_WORD /* $fd2962 cmp.w #-1,%d0 */
    beq.s   .Lskew_right_full                   /* $fd2966 */
    ori.b   #CCR_X,%ccr                         /* $fd2968 */
    roxr.w  #1,%d0                              /* $fd296c */
    move.w  %d0,TB_RIGHT_MASK(%a5)              /* $fd296e */
.Lskew_right_moved:
    move.w  TB_SHIFT(%a5),%d0                   /* $fd2972 */
    tst.b   %d0                                 /* $fd2976 */
    bne.s   .Lskew_left_mask                    /* $fd2978 */
    move.w  #LEFTMOST_BIT,TB_CARRY_MASK(%a5)    /* $fd297a */
.Lskew_left_mask:
    move.w  TB_LEFT_MASK(%a5),%d1               /* $fd2980 */
    lsr.w   #1,%d1                              /* $fd2984 */
    beq.s   .Lskew_rows_next_word               /* $fd2986 */
    move.w  %d1,TB_LEFT_MASK(%a5)               /* $fd2988 */
    tst.w   %d0                                 /* $fd298c */
    bmi.s   .Lskew_step_left                    /* $fd298e */
    addq.w  #1,TB_SHIFT(%a5)                    /* $fd2990 */
    bra.w   .Lrows_right                        /* $fd2994 */
.Lskew_step_left:
    tst.b   %d0                                 /* $fd2998 */
    beq.s   .Lskew_step_turns                   /* $fd299a */
    subq.w  #1,TB_SHIFT(%a5)                    /* $fd299c */
    bra.w   .Lrows_left                         /* $fd29a0 */
.Lskew_step_turns:
    move.w  #1,TB_SHIFT(%a5)                    /* $fd29a4 */
    bra.w   .Lrows_right                        /* $fd29aa */
.Lskew_right_full:
    addq.w  #1,TB_MIDDLE_WORDS(%a5)             /* $fd29ae */
    move.w  #LEFTMOST_BIT,TB_RIGHT_MASK(%a5)    /* $fd29b2 */
    bra.s   .Lskew_right_moved                  /* $fd29b8 */
.Lskew_rows_next_word:
    move.w  #WHOLE_WORD,TB_LEFT_MASK(%a5)       /* $fd29ba */
    subq.w  #1,TB_MIDDLE_WORDS(%a5)             /* $fd29c0 */
    adda.w  TB_GROUP_BYTES(%a5),%a1             /* $fd29c4 */
    move.w  #LAST_BIT_IN_WORD,%d2               /* $fd29c8 */
    sub.w   %d0,%d2                             /* $fd29cc */
    ori.w   #LEFTMOST_BIT,%d2                   /* $fd29ce */
    move.w  %d2,TB_SHIFT(%a5)                   /* $fd29d2 */
    bra.w   .Lrows_left                         /* $fd29d6 */

/* ROTATION into the scratch buffer: a quarter turn column by column, a half turn word-reversed from the
 * copy's end. */
.Lrotate:
    move.w  LA(LINEA_SOURCEX)(%a6),%d1          /* $fd29da */
    move.w  %d1,%d2                             /* $fd29de */
    andi.w  #PIXEL_IN_GROUP_MASK,%d2            /* $fd29e0 */
    move.w  %d2,TB_SOURCE_BIT(%a5)              /* $fd29e4 */
    lsr.w   #4,%d1                              /* $fd29e8 */
    lsl.w   #1,%d1                              /* $fd29ea */
    movea.l TB_SOURCE(%a5),%a0                  /* $fd29ec */
    adda.w  %d1,%a0                             /* $fd29f0 */
    move.w  LA(LINEA_DELX)(%a6),TB_WIDTH(%a5)   /* $fd29f2 */
    move.w  LA(LINEA_SOURCEY)(%a6),%d0          /* $fd29f8 */
    move.w  LA(LINEA_DELY)(%a6),%d1             /* $fd29fc */
    move.w  %d1,TB_HEIGHT(%a5)                  /* $fd2a00 */
    move.w  TB_SOURCE_STEP(%a5),%d2             /* $fd2a04 */
    bsr.w   .Lselect_scratch                    /* $fd2a08 */
    move.w  LA(LINEA_CHUP)(%a6),%d6             /* $fd2a0c */
    cmpi.w  #TEXT_ROTATION_180,%d6              /* $fd2a10 */
    beq.w   .Lhalf_turn                         /* $fd2a14 */
    cmpi.w  #TEXT_ROTATION_90,%d6               /* $fd2a18 */
    beq.s   .Lrotate_dest                       /* $fd2a1c */
    neg.w   TB_SOURCE_STEP(%a5)                 /* $fd2a1e */
    subq.w  #1,%d1                              /* $fd2a22 */
    add.w   %d1,%d0                             /* $fd2a24 */
    mulu.w  %d2,%d0                             /* $fd2a26 */
    adda.l  %d0,%a0                             /* $fd2a28 */
.Lrotate_dest:
    move.w  LA(LINEA_DELY)(%a6),%d0             /* $fd2a2a */
    lsr.w   #4,%d0                              /* $fd2a2e */
    add.w   %d0,%d0                             /* $fd2a30 */
    addq.w  #2,%d0                              /* $fd2a32 */
    move.w  %d0,TB_DEST_STEP(%a5)               /* $fd2a34 */
    move.l  %a1,-(%sp)                          /* $fd2a38 */
    cmpi.w  #TEXT_ROTATION_270,%d6              /* $fd2a3a */
    beq.s   .Lrotate_start                      /* $fd2a3e */
    neg.w   TB_DEST_STEP(%a5)                   /* $fd2a40 */
    move.w  LA(LINEA_DELX)(%a6),%d1             /* $fd2a44 */
    subq.w  #1,%d1                              /* $fd2a48 */
    mulu.w  %d1,%d0                             /* $fd2a4a */
    adda.l  %d0,%a1                             /* $fd2a4c */
.Lrotate_start:
    move.w  TB_SOURCE_BIT(%a5),%d2              /* $fd2a4e */
    move.w  #LEFTMOST_BIT,%d3                   /* $fd2a52 */
    move.w  %d3,%d4                             /* $fd2a56 */
    lsr.w   %d2,%d3                             /* $fd2a58 */
    moveq   #0,%d0                              /* $fd2a5a */
    move.w  TB_WIDTH(%a5),%d2                   /* $fd2a5c */
    move.w  TB_SOURCE_STEP(%a5),%d6             /* $fd2a60 */
    bra.s   .Lrotate_columns                    /* $fd2a64 */
.Lrotate_column:
    move.w  TB_HEIGHT(%a5),%d1                  /* $fd2a66 */
    movem.l %d4/%a0-%a1,-(%sp)                  /* $fd2a6a */
    bra.s   .Lrotate_rows                       /* $fd2a6e */
.Lrotate_pixel:
    move.w  (%a0),%d7                           /* $fd2a70 */
    and.w   %d3,%d7                             /* $fd2a72 */
    beq.s   .Lrotate_bit_placed                 /* $fd2a74 */
    or.w    %d4,%d0                             /* $fd2a76 */
.Lrotate_bit_placed:
    ror.w   #1,%d4                              /* $fd2a78 */
    bcc.s   .Lrotate_next_row                   /* $fd2a7a */
    move.w  %d0,(%a1)                           /* $fd2a7c */
    addq.l  #2,%a1                              /* $fd2a7e */
    moveq   #0,%d0                              /* $fd2a80 */
.Lrotate_next_row:
    adda.w  %d6,%a0                             /* $fd2a82 */
.Lrotate_rows:
    dbf     %d1,.Lrotate_pixel                  /* $fd2a84 */
    move.w  %d0,(%a1)                           /* $fd2a88 */
    moveq   #0,%d0                              /* $fd2a8a */
    movem.l (%sp)+,%d4/%a0-%a1                  /* $fd2a8c */
    adda.w  TB_DEST_STEP(%a5),%a1               /* $fd2a90 */
    ror.w   #1,%d3                              /* $fd2a94 */
    bcc.s   .Lrotate_columns                    /* $fd2a96 */
    addq.l  #2,%a0                              /* $fd2a98 */
.Lrotate_columns:
    dbf     %d2,.Lrotate_column                 /* $fd2a9a */
    movea.l (%sp)+,%a1                          /* $fd2a9e */
    move.w  LA(LINEA_DELX)(%a6),%d0             /* $fd2aa0 */
    move.w  LA(LINEA_DELY)(%a6),%d1             /* $fd2aa4 */
    move.w  %d1,TB_WIDTH(%a5)                   /* $fd2aa8 */
    move.w  %d1,LA(LINEA_DELX)(%a6)             /* $fd2aac */
    move.w  %d0,TB_HEIGHT(%a5)                  /* $fd2ab0 */
    move.w  %d0,LA(LINEA_DELY)(%a6)             /* $fd2ab4 */
    move.w  TB_SCALED_HEIGHT(%a5),%d0           /* $fd2ab8 */
    move.w  TB_SCALED_WIDTH(%a5),TB_SCALED_HEIGHT(%a5) /* $fd2abc */
    move.w  %d0,TB_SCALED_WIDTH(%a5)            /* $fd2ac2 */
    move.w  #1,TB_SWAPPED_AXES(%a5)             /* $fd2ac6 */
    move.w  TB_DEST_STEP(%a5),%d0               /* $fd2acc */
    cmpi.w  #TEXT_ROTATION_90,LA(LINEA_CHUP)(%a6) /* $fd2ad0 */
    bne.s   .Lrotate_step_ready                 /* $fd2ad6 */
    neg.w   %d0                                 /* $fd2ad8 */
.Lrotate_step_ready:
    move.w  %d0,TB_SOURCE_STEP(%a5)             /* $fd2ada */
.Lsource_is_copy:
    clr.w   LA(LINEA_SOURCEX)(%a6)              /* $fd2ade */
    clr.w   LA(LINEA_SOURCEY)(%a6)              /* $fd2ae2 */
    move.l  %a1,TB_SOURCE(%a5)                  /* $fd2ae6 */
    rts                                         /* $fd2aea */
.Lhalf_turn:
    move.w  LA(LINEA_DELX)(%a6),%d0             /* $fd2aec */
    add.w   TB_SOURCE_BIT(%a5),%d0              /* $fd2af0 */
    subq.w  #1,%d0                              /* $fd2af4 */
    lsr.w   #4,%d0                              /* $fd2af6 */
    add.w   %d0,%d0                             /* $fd2af8 */
    addq.w  #2,%d0                              /* $fd2afa */
    move.w  %d0,TB_DEST_STEP(%a5)               /* $fd2afc */
    move.w  %d0,%d2                             /* $fd2b00 */
    lsr.w   #1,%d2                              /* $fd2b02 */
    subq.w  #1,%d2                              /* $fd2b04 */
    mulu.w  %d1,%d0                             /* $fd2b06 */
    move.l  %a1,-(%sp)                          /* $fd2b08 */
    adda.l  %d0,%a1                             /* $fd2b0a */
    bra.s   .Lhalf_turn_rows                    /* $fd2b0c */
.Lhalf_turn_row:
    movea.l %a0,%a2                             /* $fd2b0e */
    move.w  %d2,%d3                             /* $fd2b10 */
.Lhalf_turn_word:
    move.w  (%a2)+,%d0                          /* $fd2b12 */
    moveq   #0,%d5                              /* $fd2b14 */
    move.w  #WORD_BITS-1,%d4                    /* $fd2b16 */
.Lhalf_turn_bit:
    lsr.w   #1,%d0                              /* $fd2b1a */
    roxl.w  #1,%d5                              /* $fd2b1c */
    dbf     %d4,.Lhalf_turn_bit                 /* $fd2b1e */
    move.w  %d5,-(%a1)                          /* $fd2b22 */
    dbf     %d3,.Lhalf_turn_word                /* $fd2b24 */
    adda.w  TB_SOURCE_STEP(%a5),%a0             /* $fd2b28 */
.Lhalf_turn_rows:
    dbf     %d1,.Lhalf_turn_row                 /* $fd2b2c */
    move.w  TB_DEST_STEP(%a5),TB_SOURCE_STEP(%a5) /* $fd2b30 */
    movea.l (%sp)+,%a1                          /* $fd2b36 */
    move.l  %a1,TB_SOURCE(%a5)                  /* $fd2b38 */
    move.w  LA(LINEA_SOURCEX)(%a6),%d0          /* $fd2b3c */
    add.w   LA(LINEA_DELX)(%a6),%d0             /* $fd2b40 */
    neg.w   %d0                                 /* $fd2b44 */
    andi.w  #PIXEL_IN_GROUP_MASK,%d0            /* $fd2b46 */
    move.w  %d0,LA(LINEA_SOURCEX)(%a6)          /* $fd2b4a */
    clr.w   LA(LINEA_SOURCEY)(%a6)              /* $fd2b4e */
    rts                                         /* $fd2b52 */

/* SCALING into the scratch buffer, before anything else: rows by the DDA (twice each enlarging), each
 * row across by the DDA from XACC_DDA. */
.Lscale:
    move.w  LA(LINEA_SOURCEX)(%a6),%d0          /* $fd2b54 */
    move.w  %d0,%d4                             /* $fd2b58 */
    andi.w  #PIXEL_IN_GROUP_MASK,%d0            /* $fd2b5a */
    move.w  %d0,TB_SOURCE_BIT(%a5)              /* $fd2b5e */
    lsr.w   #4,%d4                              /* $fd2b62 */
    add.w   %d4,%d4                             /* $fd2b64 */
    move.w  LA(LINEA_SOURCEY)(%a6),%d0          /* $fd2b66 */
    mulu.w  TB_SOURCE_STEP(%a5),%d0             /* $fd2b6a */
    movea.l TB_SOURCE(%a5),%a0                  /* $fd2b6e */
    adda.w  %d4,%a0                             /* $fd2b72 */
    adda.l  %d0,%a0                             /* $fd2b74 */
    move.w  TB_SOURCE_BIT(%a5),%d2              /* $fd2b76 */
    move.w  #LEFTMOST_BIT,%d3                   /* $fd2b7a */
    move.w  %d3,%d4                             /* $fd2b7e */
    lsr.w   %d2,%d3                             /* $fd2b80 */
    move.w  LA(LINEA_DELY)(%a6),%d2             /* $fd2b82 */
    move.w  LA(LINEA_DELX)(%a6),%d1             /* $fd2b86 */
    move.w  %d2,TB_HEIGHT(%a5)                  /* $fd2b8a */
    move.w  %d1,TB_WIDTH(%a5)                   /* $fd2b8e */
    bsr.w   .Lselect_scratch                    /* $fd2b92 */
    lsr.w   #3,%d1                              /* $fd2b96 */
    add.w   %d1,%d1                             /* $fd2b98 */
    addq.w  #2,%d1                              /* $fd2b9a */
    move.w  %d1,TB_DEST_STEP(%a5)               /* $fd2b9c */
    movea.l %a1,%a3                             /* $fd2ba0 */
    move.w  LA(LINEA_T_SCLSTS)(%a6),%d7         /* $fd2ba2 */
    roxr.l  #1,%d7                              /* $fd2ba6 */
    moveq   #0,%d7                              /* $fd2ba8 */
    roxr.l  #1,%d7                              /* $fd2baa */
    move.w  TB_SOURCE_STEP(%a5),%d7             /* $fd2bac */
    move.w  LA(LINEA_DDA_INC)(%a6),%d2          /* $fd2bb0 */
    move.w  TB_HEIGHT(%a5),%d5                  /* $fd2bb4 */
    subq.w  #1,%d5                              /* $fd2bb8 */
    move.w  #VDI_DDA_ACCUMULATOR_START,%d6      /* $fd2bba */
    tst.l   %d7                                 /* $fd2bbe */
    bmi.s   .Lscale_up_row                      /* $fd2bc0 */
.Lscale_down_row:
    add.w   %d2,%d6                             /* $fd2bc2 */
    bcc.s   .Lscale_down_next                   /* $fd2bc4 */
    bsr.s   .Lscale_row                         /* $fd2bc6 */
.Lscale_down_next:
    adda.w  %d7,%a0                             /* $fd2bc8 */
    dbf     %d5,.Lscale_down_row                /* $fd2bca */
    bra.s   .Lscale_width                       /* $fd2bce */
.Lscale_up_row:
    add.w   %d2,%d6                             /* $fd2bd0 */
    bcc.s   .Lscale_up_again                    /* $fd2bd2 */
    bsr.s   .Lscale_row                         /* $fd2bd4 */
.Lscale_up_again:
    bsr.s   .Lscale_row                         /* $fd2bd6 */
    adda.w  %d7,%a0                             /* $fd2bd8 */
    dbf     %d5,.Lscale_up_row                  /* $fd2bda */
.Lscale_width:
    move.w  LA(LINEA_DELX)(%a6),%d2             /* $fd2bde */
    move.w  LA(LINEA_XACC_DDA)(%a6),%d1         /* $fd2be2 */
    move.w  LA(LINEA_DDA_INC)(%a6),%d0          /* $fd2be6 */
    moveq   #0,%d3                              /* $fd2bea */
    bra.s   .Lscale_columns                     /* $fd2bec */
.Lscale_column:
    add.w   %d0,%d1                             /* $fd2bee */
    bcc.s   .Lscale_column_counted              /* $fd2bf0 */
    addq.w  #1,%d3                              /* $fd2bf2 */
.Lscale_column_counted:
    tst.l   %d7                                 /* $fd2bf4 */
    bpl.s   .Lscale_columns                     /* $fd2bf6 */
    addq.w  #1,%d3                              /* $fd2bf8 */
.Lscale_columns:
    dbf     %d2,.Lscale_column                  /* $fd2bfa */
    move.w  %d1,LA(LINEA_XACC_DDA)(%a6)         /* $fd2bfe */
    move.w  %d3,LA(LINEA_DELX)(%a6)             /* $fd2c02 */
    move.w  TB_SCALED_HEIGHT(%a5),LA(LINEA_DELY)(%a6) /* $fd2c06 */
    move.w  TB_DEST_STEP(%a5),%d1               /* $fd2c0c */
    move.w  %d1,TB_SOURCE_STEP(%a5)             /* $fd2c10 */
    movea.l LA(LINEA_SCRTCHP)(%a6),%a1          /* $fd2c14 */
    bra.w   .Lsource_is_copy                    /* $fd2c18 */
.Lscale_row:
    movem.l %d3-%a1,-(%sp)                      /* $fd2c1c */
    moveq   #0,%d0                              /* $fd2c20 */
    move.w  TB_WIDTH(%a5),%d5                   /* $fd2c22 */
    subq.w  #1,%d5                              /* $fd2c26 */
    move.w  LA(LINEA_XACC_DDA)(%a6),%d7         /* $fd2c28 */
    bra.s   .Lscale_load_word                   /* $fd2c2c */
.Lscale_next_pixel:
    ror.w   #1,%d3                              /* $fd2c2e */
    bcc.s   .Lscale_pixel                       /* $fd2c30 */
.Lscale_load_word:
    movea.w (%a0)+,%a2                          /* $fd2c32 */
.Lscale_pixel:
    move.w  %a2,%d6                             /* $fd2c34 */
    and.w   %d3,%d6                             /* $fd2c36 */
    bne.s   .Lscale_set                         /* $fd2c38 */
    tst.l   %d7                                 /* $fd2c3a */
    bmi.s   .Lscale_up_clear                    /* $fd2c3c */
    add.w   %d2,%d7                             /* $fd2c3e */
    bcc.s   .Lscale_pixels                      /* $fd2c40 */
    bra.s   .Lscale_advance                     /* $fd2c42 */
.Lscale_up_clear:
    add.w   %d2,%d7                             /* $fd2c44 */
    bcc.s   .Lscale_advance                     /* $fd2c46 */
    ror.w   #1,%d4                              /* $fd2c48 */
    bcc.s   .Lscale_advance                     /* $fd2c4a */
    move.w  %d0,(%a1)+                          /* $fd2c4c */
    moveq   #0,%d0                              /* $fd2c4e */
    bra.s   .Lscale_advance                     /* $fd2c50 */
.Lscale_set:
    add.w   %d2,%d7                             /* $fd2c52 */
    bcc.s   .Lscale_set_again                   /* $fd2c54 */
    or.w    %d4,%d0                             /* $fd2c56 */
    ror.w   #1,%d4                              /* $fd2c58 */
    bcc.s   .Lscale_set_again                   /* $fd2c5a */
    move.w  %d0,(%a1)+                          /* $fd2c5c */
    moveq   #0,%d0                              /* $fd2c5e */
.Lscale_set_again:
    tst.l   %d7                                 /* $fd2c60 */
    bpl.s   .Lscale_pixels                      /* $fd2c62 */
    or.w    %d4,%d0                             /* $fd2c64 */
.Lscale_advance:
    ror.w   #1,%d4                              /* $fd2c66 */
    bcc.s   .Lscale_pixels                      /* $fd2c68 */
    move.w  %d0,(%a1)+                          /* $fd2c6a */
    moveq   #0,%d0                              /* $fd2c6c */
.Lscale_pixels:
    dbf     %d5,.Lscale_next_pixel              /* $fd2c6e */
    move.w  %d0,(%a1)                           /* $fd2c72 */
    movem.l (%sp)+,%d3-%a1                      /* $fd2c74 */
    adda.w  %d1,%a1                             /* $fd2c78 */
    rts                                         /* $fd2c7a */

/* The scratch half the next copy goes in: the first, then SCRPT2 on, in turn. */
.Lselect_scratch:
    move.w  %d7,-(%sp)                          /* $fd2c7c */
    movea.l LA(LINEA_SCRTCHP)(%a6),%a1          /* $fd2c7e */
    move.w  TB_SCRATCH_HALF(%a5),%d7            /* $fd2c82 */
    beq.s   .Lscratch_first_half                /* $fd2c86 */
    adda.w  %d7,%a1                             /* $fd2c88 */
    clr.w   TB_SCRATCH_HALF(%a5)                /* $fd2c8a */
    bra.s   .Lscratch_selected                  /* $fd2c8e */
.Lscratch_first_half:
    move.w  LA(LINEA_SCRPT2)(%a6),TB_SCRATCH_HALF(%a5) /* $fd2c90 */
.Lscratch_selected:
    move.w  (%sp)+,%d7                          /* $fd2c96 */
    rts                                         /* $fd2c98 */

/* OUTLINING the scratch copy in place: each pixel whose 3x3 neighbourhood is not one colour, less the
 * glyph itself. The buffer's first row holds the ORIGINAL of the row last outlined. */
.Loutline:
    lea     0(%a0,%d7.w),%a1                    /* $fd2c9a */
    lea     0(%a1,%d7.w),%a2                    /* $fd2c9e */
    lsr.w   #1,%d7                              /* $fd2ca2 */
    subq.w  #1,%d7                              /* $fd2ca4 */
    move.w  LA(LINEA_DELY)(%a6),%d6             /* $fd2ca6 */
    bra.w   .Loutline_rows                      /* $fd2caa */
.Loutline_row:
    movem.l %d6-%a2,-(%sp)                      /* $fd2cae */
    moveq   #0,%d5                              /* $fd2cb2 */
    moveq   #0,%d6                              /* $fd2cb4 */
    move.l  (%a2),%d1                           /* $fd2cb6 */
    lsr.l   #1,%d1                              /* $fd2cb8 */
.Loutline_word:
    move.l  (%a0),%d0                           /* $fd2cba */
    move.b  %d5,%d0                             /* $fd2cbc */
    ror.l   #1,%d0                              /* $fd2cbe */
    move.l  (%a1),%d2                           /* $fd2cc0 */
    move.b  %d6,%d2                             /* $fd2cc2 */
    move.l  %d2,%d3                             /* $fd2cc4 */
    ror.l   #1,%d3                              /* $fd2cc6 */
    move.l  %d3,%d4                             /* $fd2cc8 */
    ror.l   #1,%d4                              /* $fd2cca */
    move.l  %d0,%d5                             /* $fd2ccc */
    move.l  %d0,%d6                             /* $fd2cce */
    eor.l   %d2,%d0                             /* $fd2cd0 */
    eor.l   %d3,%d5                             /* $fd2cd2 */
    eor.l   %d4,%d6                             /* $fd2cd4 */
    rol.l   #1,%d5                              /* $fd2cd6 */
    rol.l   #2,%d6                              /* $fd2cd8 */
    or.l    %d5,%d0                             /* $fd2cda */
    or.l    %d6,%d0                             /* $fd2cdc */
    move.l  %d1,%d5                             /* $fd2cde */
    move.l  %d1,%d6                             /* $fd2ce0 */
    eor.l   %d2,%d1                             /* $fd2ce2 */
    eor.l   %d3,%d5                             /* $fd2ce4 */
    eor.l   %d4,%d6                             /* $fd2ce6 */
    rol.l   #1,%d5                              /* $fd2ce8 */
    rol.l   #2,%d6                              /* $fd2cea */
    or.l    %d1,%d0                             /* $fd2cec */
    or.l    %d5,%d0                             /* $fd2cee */
    or.l    %d6,%d0                             /* $fd2cf0 */
    eor.l   %d3,%d2                             /* $fd2cf2 */
    eor.l   %d3,%d4                             /* $fd2cf4 */
    rol.l   #2,%d4                              /* $fd2cf6 */
    or.l    %d2,%d0                             /* $fd2cf8 */
    or.l    %d4,%d0                             /* $fd2cfa */
    swap    %d0                                 /* $fd2cfc */
    move.w  (%a1),%d6                           /* $fd2cfe */
    move.w  %d6,%d5                             /* $fd2d00 */
    eor.w   %d0,%d5                             /* $fd2d02 */
    and.w   %d0,%d5                             /* $fd2d04 */
    addq.l  #2,%a2                              /* $fd2d06 */
    move.l  (%a2),%d1                           /* $fd2d08 */
    move.b  -1(%a2),%d1                         /* $fd2d0a */
    ror.l   #1,%d1                              /* $fd2d0e */
    move.w  %d5,(%a1)+                          /* $fd2d10 */
    move.w  (%a0),%d5                           /* $fd2d12 */
    move.w  %d6,(%a0)+                          /* $fd2d14 */
    dbf     %d7,.Loutline_word                  /* $fd2d16 */
    movem.l (%sp)+,%d6-%a2                      /* $fd2d1a */
    movea.l %a2,%a1                             /* $fd2d1e */
    adda.w  TB_SOURCE_STEP(%a5),%a2             /* $fd2d20 */
    cmpi.w  #1,%d6                              /* $fd2d24 */
    bne.s   .Loutline_rows                      /* $fd2d28 */
    movea.l %a1,%a2                             /* $fd2d2a */
.Loutline_rows:
    dbf     %d6,.Loutline_row                   /* $fd2d2c */
    rts                                         /* $fd2d30 */

