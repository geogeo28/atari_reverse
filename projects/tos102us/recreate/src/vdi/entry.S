/* entry.S — the Line-A exception, $a000 and the VDI's `trap #2` entry as the ROM spells them ($fc9f0c..$fc9ffb):
 * the TRANSCRIPTIONS a target build ships, where `entry.c` and `linea.c` are what Tier 1's host differential proves.
 *
 * WHY THIS IS ASSEMBLY. Two of the three are ENTRIES reached with a convention no C function has, which is
 * `vdi_rom_timer_tick`'s reason (`transcribed.h`): vector $28 enters `linea_rom_dispatch` with an exception
 * frame and leaves by `rte`, the PC stepped past the $Axxx word, D3-D7/A3-A5 kept and D0-D2/A0-A2 the primitive's
 * answer; `trap #2`'s VDI arm enters `vdi_rom_entry` expecting every register back but D0, the answer's word. And
 * `$a000` (`linea_rom_init`) lies between the first and the table it indexes PC-relative, so the region is one.
 *
 * THE LAYOUT IS THE ROM's: the handler, $a000, the opcode table the handler's `(pc,d2.w)` indexes, the font table,
 * the SEEDABORT default v_contourfill installs, and the entry. WHAT IS RELOCATED — each pinned to its exact value
 * by `test_vdi_entry_transcription.py` — are the absolute references into THIS region and into the other byte-pinned
 * transcriptions: $a000's two `lea`s of its own tables, and every opcode-table longword whose primitive ships as a
 * `.S` entry, which names that entry. Two primitives do not: $a009 (v_show_c's body) and $a00f (the contour fill)
 * ship as C, and their longwords stay the ROM's own, CODE values a rebuilt ROM owes an entry with the Line-A
 * convention (`test_vdi_rom_data.py`). So does the entry's `jsr` into the dispatcher, whose C ships. And the
 * font table's three longwords — $a000's answer in A1 — stay the ROM's own face headers, TABLE values a rebuilt
 * ROM owes at those addresses.
 *
 * NO WORD EXCUSED otherwise: the handler's `and.w #$fff,d2` and `cmp.w #15,d2` are the register forms GNU as would
 * turn into ANDI/CMPI, spelt as the ROM's words (`m68k_encodings.h`), and every absolute address a `.l`.
 */
#include "addrs.h"
#include "m68k_encodings.h"
#include "vdi/linea.h"
#include "vdi/vdi.h"
#include "vdi/font.h"

    .text

/* ---- $fc9f0c, the Line-A exception --------------------------------------------------------------------------- */
    .globl  linea_rom_dispatch
linea_rom_dispatch:
    movea.l EXCEPTION_FRAME_PC(%sp),%a1         /* the $Axxx word's address */
    move.w  (%a1),%d2
    .word   M68K_AND_W_IMMEDIATE(M68K_D2), LINEA_OPCODE_MASK       /* and.w #$fff,d2 */
    addq.l  #2,%a1
    move.l  %a1,EXCEPTION_FRAME_PC(%sp)         /* resume past it */
    .word   M68K_CMP_W_IMMEDIATE(M68K_D2), LINEA_OPCODE_LAST       /* cmp.w #15,d2 */
    bhi.s   .Llinea_done
    lsl.w   #2,%d2
    movea.l .Llinea_opcodes(%pc,%d2.w),%a1
    movem.l %d3-%d7/%a3-%a5,-(%sp)
    jsr     (%a1)
    movem.l (%sp)+,%d3-%d7/%a3-%a5
.Llinea_done:
    rte

/* ---- $fc9f34, $a000: the block's base in D0 and A0, the font table in A1, the opcode table in A2 ---------------- */
    .globl  linea_rom_init
linea_rom_init:
    lea     (LINEA_BASE).l,%a0
    move.l  %a0,%d0
    lea     (.Llinea_fonts).l,%a1
    lea     (.Llinea_opcodes).l,%a2
    rts

/* ---- $fc9f4a, the opcode table: $a000..$a00f ---------------------------------------------------------------- */
.Llinea_opcodes:
    .long   linea_rom_init, linea_rom_put_pixel, linea_rom_get_pixel, linea_rom_line
    .long   linea_rom_hline, linea_rom_filled_rect, linea_rom_filled_poly, linea_rom_bitblt
    .long   linea_rom_textblt, VDI_ROM_V_SHOW_C, linea_rom_hide_mouse, vdi_rom_vsc_form
    .long   linea_rom_undraw_sprite, linea_rom_draw_sprite, linea_rom_copy_raster, LINEA_ROM_CONTOUR_FILL

/* ---- $fc9f8a, the font table $a000 answers: the three ROM faces, then a zero -------------------------------------- */
.Llinea_fonts:
    .long   FONT_ROM_6X6, FONT_ROM_8X8, FONT_ROM_8X16, 0

/* ---- $fc9f9a, SEEDABORT's default: never abort (`fill.c` answers it without a call) -------------------------------- */
.Lseedabort_default:
    moveq   #0,%d0
    rts

/* ---- $fc9f9e, the VDI's `trap #2` entry, D1 = the parameter block --------------------------------------------------- */
    .globl  vdi_rom_entry
vdi_rom_entry:
    movem.l %d1-%a6,-(%sp)
    movea.l %d1,%a0
    lea     (LINEA_CONTRL).l,%a1
    lea     (VDI_PTSIN_COPY).l,%a3
    movea.l (%a0)+,%a2                          /* contrl, held */
    move.l  %a2,(%a1)+
    move.l  (%a0)+,(%a1)+                       /* intin */
    movea.l (%a0)+,%a4                          /* the caller's ptsin, held */
    move.l  %a3,(%a1)+                          /* ...and the copy in its place */
    move.l  (%a0)+,(%a1)+                       /* intout */
    move.l  (%a0)+,(%a1)+                       /* ptsout */
    move.w  CONTRL_N_PTSIN(%a2),%d0
    move.w  %d0,-(%sp)                          /* the caller's count, given back below */
    beq.s   .Lentry_dispatch
    add.w   %d0,%d0
    move.w  #VDI_PTSIN_COPY_BYTES/VDI_WORD_BYTES,%d1
    cmp.w   %d1,%d0
    bls.s   .Lentry_copy_next
    move.w  %d1,%d0
    move.w  #VDI_PTSIN_CAP_POINTS,CONTRL_N_PTSIN(%a2)
    bra.s   .Lentry_copy_next
.Lentry_copy:
    move.w  (%a4)+,(%a3)+
.Lentry_copy_next:
    dbf     %d0,.Lentry_copy
.Lentry_dispatch:
    jsr     (VDI_ROM_DISPATCH).l
    movea.l (LINEA_CONTRL).l,%a0
    move.w  (%sp)+,CONTRL_N_PTSIN(%a0)
    movem.l (%sp)+,%d1-%a6
    move.w  (VDI_RESULT).l,%d0
    rts
