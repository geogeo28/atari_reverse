/* palette.S — vs_color and vq_color as the ROM spells them ($fd2dd2..$fd2f31): the TRANSCRIPTION a
 * target build ships, where `palette.c` is what Tier 1's host differential proves.
 *
 * WHY THIS IS ASSEMBLY. The ROM's pair is hand-written 68000 with no frame, no saved register but
 * vq_color's D4, two PC-relative tables and an I/O address held in an address register. The C port
 * measures 1.19x-2.55x against it (`bench/tier3.py`'s mechanism (T) says where the cycles go), over
 * the 1.10 bar — and the user's rule for the hand-written routines is: C first, and where the C is
 * over the bar, the ROM's own instructions, pinned byte for byte. `include/transcribed.h` is the
 * table that makes these two entries what ships.
 *
 * WHAT PINS IT. `test_vdi_color.py` reads the assembled block back out of the cross-compiled blob and
 * compares it with the ROM's $160 bytes EXACTLY (`transcription.assert_transcribed`), no word excused: the six
 * `<op>.w #imm,Dn` the ROM's assembler encoded in the register form, where GNU as would pick CMPI/ADDI/
 * ANDI, are spelt as the ROM's words (`m68k_encodings.h`, which says why that matters to the cycle
 * count too). And it runs the pair through Tier 3's TRANSCRIPTION relation
 * (`RomBench.measure_transcription`) over every arm: the same image, the WHOLE register file and the
 * same palette traffic as the ROM.
 *
 * THE LAYOUT IS THE ROM's, tables included, so every PC-relative displacement assembles to the ROM's
 * own: VDI_PEN_MASKS is the four bytes after vs_color's colour arm, indexed by LINEA_PLANES from the
 * `rts` in front of them, and VDI_VQ_COLOR_LEVELS follows vq_color. The two entries are the ROM's
 * routine names lower-cased — `VDI_ROM_VS_COLOR` is `vdi_rom_vs_color` — which is how Tier 3 finds the
 * ROM address a transcription row is measured against.
 *
 * REGISTERS, as the ROM leaves them — the transcription relation compares all of them. vs_color
 * clobbers D0-D4/A0/A1 (D3 and D4 are an Alcyon caller's register variables, which is harmless only
 * because `$fc9f9e`, the trap #2 entry, saves D1-A6 around the whole dispatch); vq_color saves D4 and
 * clobbers D0-D2/A0/A1. The callee-saved ones among those are each entry's row in
 * `include/transcribed.h`.
 */
#include "addrs.h"
#include "m68k_encodings.h"
#include "vdi/linea.h"
#include "vdi/palette.h"
#include "vdi/vdi.h"

    .text

/* ---- vs_color (14): A0 = intin, D0 = the index, D1 = planes, D4 = the index bound, A1 = its REQ_COL row */
    .globl  vdi_rom_vs_color
vdi_rom_vs_color:
    movea.l (LINEA_INTIN).l,%a0
    move.w  (%a0)+,%d0                          /* the index */
    move.w  (LINEA_PLANES).l,%d1
    move.b  (.Lpen_masks-1,%pc,%d1.w),%d4       /* the table is indexed by the plane count itself */
    cmp.b   %d4,%d0                             /* a BYTE compare: $8000 passes as colour 0 */
    bhi.w   .Lvs_done
    move.w  %d0,%d2
    mulu.w  #PALETTE_REQ_COL_ROW_BYTES,%d2
    lea     (LINEA_REQ_COL).l,%a1
    adda.w  %d2,%a1                             /* the row, the word product sign-extended */
    subq.w  #PALETTE_MONO_PLANES,%d1
    beq.s   .Lvs_mono
    moveq   #PALETTE_GUNS-1,%d3
    moveq   #0,%d1                              /* the shifter word, built a gun at a time */
.Lvs_gun:
    moveq   #0,%d2                              /* the high word is `divu`'s dividend too */
    move.w  (%a0)+,%d2
    move.w  %d2,(%a1)+                          /* the request, stored as given */
    bge.s   .Lvs_not_negative
    clr.w   %d2
.Lvs_not_negative:
    .word   M68K_CMP_W_IMMEDIATE(2), PALETTE_PER_MILLE_MAX   /* cmp.w #PALETTE_PER_MILLE_MAX,%d2 */
    ble.s   .Lvs_in_range
    move.w  #PALETTE_PER_MILLE_MAX,%d2
.Lvs_in_range:
    .word   M68K_ADD_W_IMMEDIATE(2), PALETTE_LEVEL_ROUNDING  /* add.w #PALETTE_LEVEL_ROUNDING,%d2 */
    divu.w  #PALETTE_PER_MILLE_PER_LEVEL,%d2
    asl.w   #PALETTE_GUN_BITS,%d1
    or.w    %d2,%d1
    dbf     %d3,.Lvs_gun
    lea     (VDI_MAP_COL).l,%a0
    add.w   %d0,%d0
    move.w  (0,%a0,%d0.w),%d0                   /* the pen... */
    and.b   %d4,%d0                             /* ...its LOW BYTE masked to the plane count */
    lea     (SHIFTER_PALETTE).l,%a0
    add.w   %d0,%d0
    move.w  %d1,(0,%a0,%d0.w)
    rts
.Lpen_masks:                                    /* VDI_PEN_MASKS + 1: planes 1, 2, 3, 4 */
    .byte   1, 3, 0, 15

/* The monochrome arm: each gun black, kept or white; register 0 gets the INDEX for all-black and its
 * complement for all-white, and nothing for a grey. */
.Lvs_mono:
    move.w  (%a0)+,%d1
    move.w  %d1,(%a1)+
    bsr.s   .Lmono_level
    move.w  %d1,%d2
    move.w  (%a0)+,%d1
    move.w  %d1,(%a1)+
    bsr.s   .Lmono_level
    add.w   %d1,%d2
    move.w  (%a0)+,%d1
    move.w  %d1,(%a1)+
    bsr.s   .Lmono_level
    add.w   %d1,%d2
    beq.s   .Lvs_mono_store                     /* all black: the index itself */
    .word   M68K_CMP_W_IMMEDIATE(2), PALETTE_WHITE_SUM       /* cmp.w #PALETTE_WHITE_SUM,%d2 */
    bne.s   .Lvs_done                           /* a grey: nothing */
    not.w   %d0
.Lvs_mono_store:
    move.w  %d0,(SHIFTER_PALETTE).l
.Lvs_done:
    rts

/* $fd2e6e — D1 per mille -> 0, as given, or white. */
.Lmono_level:
    .word   M68K_CMP_W_IMMEDIATE(1), PALETTE_MONO_BLACK_BELOW /* cmp.w #PALETTE_MONO_BLACK_BELOW,%d1 */
    blt.s   .Lmono_black
    .word   M68K_CMP_W_IMMEDIATE(1), PALETTE_MONO_WHITE_FROM /* cmp.w #PALETTE_MONO_WHITE_FROM,%d1 */
    blt.s   .Lmono_kept
    move.w  #PALETTE_PER_MILLE_MAX,%d1
.Lmono_kept:
    rts
.Lmono_black:
    moveq   #0,%d1
    rts

/* ---- vq_color (26): D0 = the index, D2 = the realized flag, A0 = intout, D4 = the index bound ---- */
    .globl  vdi_rom_vq_color
vdi_rom_vq_color:
    move.l  %d4,-(%sp)
    movea.l (LINEA_CONTRL).l,%a0
    move.w  #PALETTE_VQ_COLOR_INTOUT_WORDS,(CONTRL_N_INTOUT,%a0)   /* first, whatever follows */
    movea.l (LINEA_INTIN).l,%a0
    move.w  (%a0)+,%d0
    move.w  (%a0),%d2
    movea.l (LINEA_INTOUT).l,%a0
    move.w  (LINEA_PLANES).l,%d1
    move.b  (.Lpen_masks-1,%pc,%d1.w),%d4
    cmp.b   %d4,%d0
    bls.s   .Lvq_valid
    move.w  #PALETTE_INVALID,(%a0)
    bra.s   .Lvq_done
.Lvq_valid:
    move.w  %d0,(%a0)+                          /* the index, the whole word */
    tst.w   %d2
    bne.s   .Lvq_realized
    lea     (LINEA_REQ_COL).l,%a1
    mulu.w  #PALETTE_REQ_COL_ROW_BYTES,%d0
    adda.w  %d0,%a1
    move.w  (%a1)+,(%a0)+
    move.w  (%a1)+,(%a0)+
    move.w  (%a1),(%a0)
.Lvq_done:
    move.l  (%sp)+,%d4
    rts
.Lvq_realized:
    subq.w  #PALETTE_MONO_PLANES,%d1
    beq.s   .Lvq_mono
    lea     (VDI_MAP_COL).l,%a1
    add.w   %d0,%d0
    move.w  (0,%a1,%d0.w),%d0
    and.b   %d4,%d0
    lea     (SHIFTER_PALETTE).l,%a1
    add.w   %d0,%d0
    move.w  (0,%a1,%d0.w),%d0                   /* the register, 0RGB */
    rol.w   #PALETTE_FIRST_GUN_ROTATE,%d0
    moveq   #PALETTE_GUNS-1,%d1
.Lvq_gun:
    rol.w   #PALETTE_GUN_BITS,%d0               /* the next gun's level, as a word index */
    move.w  %d0,%d2
    .word   M68K_AND_W_IMMEDIATE(2), PALETTE_LEVEL_INDEX_MASK /* and.w #PALETTE_LEVEL_INDEX_MASK,%d2 */
    move.w  (.Llevels,%pc,%d2.w),(%a0)+
    dbf     %d1,.Lvq_gun
    bra.s   .Lvq_done
.Lvq_mono:
    move.w  (SHIFTER_PALETTE).l,%d1
    eor.w   %d1,%d0
    moveq   #0,%d1
    btst    #PALETTE_MONO_INVERT_BIT,%d0
    beq.s   .Lvq_mono_level
    move.w  #PALETTE_PER_MILLE_MAX,%d1
.Lvq_mono_level:
    move.w  %d1,(%a0)+
    move.w  %d1,(%a0)+
    move.w  %d1,(%a0)
    bra.s   .Lvq_done
.Llevels:                                       /* VDI_VQ_COLOR_LEVELS: level -> per mille */
    .word   0, 142, 285, 428, 571, 714, 857, 1000
