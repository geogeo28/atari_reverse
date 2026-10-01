/* gemgraf.S — the graphics library's Line-F-free leaves as the ROM spells them: gr_inside, gr_crack, gsx_gclip,
 * gsx_chkclip and gsx_bxpts — the TRANSCRIPTIONS a target build ships, where `gemgraf.c` is what Tier 1's host
 * differential proves.
 *
 * WHY THESE ARE ASSEMBLY. Each is hand 68000 over a caller's GRECT or answer words and the AES's clip words and ptsin
 * at absolute addresses, which the C reaches through the image pointer on every access (`bench/tier3.py`'s (A)), and
 * each C port measures over Tier 3's 1.10 bar (gsx_bxpts' at 2.07), so by the user's rule the target carries the
 * ROM's own instructions (`include/transcribed.h`). None calls anything, and none executes a Line-F word, which an
 * AES `.S` may not (`../../README.md`, "An AES `.S`").
 *
 * FOUR PINNED REGIONS, each laid out in the ROM's order (`test/test_aes_gemgraf_transcription.py` pins every byte):
 *   * $fda56e..$fda581 gr_inside;
 *   * $fda66a..$fda6c3 gr_crack;
 *   * $fda846..$fda8a7 gsx_gclip, then gsx_chkclip and its two returns;
 *   * $fda956..$fda97b gsx_bxpts.
 *
 * REGISTERS, as the ROM leaves them: gsx_chkclip leaves D2 (the clip's height, plus its y), gr_crack D2 (the interior
 * colour) — the table's rows say so; every other entry changes D0/D1/A0/A1 alone.
 */
#include "addrs.h"
#include "m68k_encodings.h"
#include "aes/aes.h"
#include "aes/gemgraf.h"
#include "aes/gsx.h"

    .text

/* =============================================================================================================
 * Region $fda56e..$fda581: gr_inside — (rect, thickness): x, y += t; w, h -= 2t
 * ============================================================================================================= */
    .globl  aes_rom_gr_inside
aes_rom_gr_inside:
    movea.l 4(%sp),%a0
    move.w  8(%sp),%d1
    add.w   %d1,(%a0)+
    add.w   %d1,(%a0)+
    asl.w   #1,%d1
    sub.w   %d1,(%a0)+
    sub.w   %d1,(%a0)+
    rts

/* =============================================================================================================
 * Region $fda66a..$fda6c3: gr_crack — (colour, &border, &text, &pattern, &interior, &mode)
 * ============================================================================================================= */
    .globl  aes_rom_gr_crack
aes_rom_gr_crack:
    move.w  4(%sp),%d0
    movea.l 6(%sp),%a0
    move.w  %d0,%d1
    lsr.w   #CRACK_TEXT_SHIFT,%d1
    move.w  %d1,%d2
    asr.w   #CRACK_BORDER_SHIFT - CRACK_TEXT_SHIFT,%d1
    .word   M68K_AND_W_IMMEDIATE(M68K_D1), CRACK_NIBBLE_MASK       /* and.w #15,d1 — gas would make it andi */
    move.w  %d1,(%a0)
    .word   M68K_AND_W_IMMEDIATE(M68K_D2), CRACK_NIBBLE_MASK
    movea.l 10(%sp),%a0
    move.w  %d2,(%a0)
    move.w  %d0,%d1
    .word   M68K_AND_W_IMMEDIATE(M68K_D1), CRACK_LOW_BYTE_MASK
    move.w  %d1,%d2
    asr.w   #CRACK_PATTERN_SHIFT,%d1
    .word   M68K_AND_W_IMMEDIATE(M68K_D1), CRACK_NIBBLE_MASK
    movea.l 14(%sp),%a0
    move.w  %d1,(%a0)
    movea.l 22(%sp),%a1
    btst    #CRACK_REPLACE_BIT,1(%a0)
    beq.s   .Lgr_crack_transparent
    andi.w  #CRACK_PATTERN_MASK,(%a0)
    move.w  #GSX_MODE_REPLACE,(%a1)
    bra.s   .Lgr_crack_interior
.Lgr_crack_transparent:
    move.w  #GSX_MODE_TRANSPARENT,(%a1)
.Lgr_crack_interior:
    .word   M68K_AND_W_IMMEDIATE(M68K_D2), CRACK_NIBBLE_MASK
    movea.l 18(%sp),%a1
    move.w  %d2,(%a1)
    rts

/* =============================================================================================================
 * Region $fda846..$fda8a7: gsx_gclip — (rect): the clip words out; gsx_chkclip — (rect): D0 = it touches the clip
 * ============================================================================================================= */
    .globl  aes_rom_gsx_gclip
aes_rom_gsx_gclip:
    movea.l 4(%sp),%a0
    move.w  AES_GL_XCLIP,(%a0)+
    move.w  AES_GL_YCLIP,(%a0)+
    move.w  AES_GL_WCLIP,(%a0)+
    move.w  AES_GL_HCLIP,(%a0)+
    rts

    .globl  aes_rom_gsx_chkclip
aes_rom_gsx_chkclip:
    move.w  AES_GL_WCLIP,%d1
    beq.s   .Lgsx_chkclip_in
    move.w  AES_GL_HCLIP,%d2
    beq.s   .Lgsx_chkclip_in
    movea.l 4(%sp),%a0
    lea     AES_GL_XCLIP,%a1
    lea     AES_GL_YCLIP,%a2
    move.w  (%a0)+,%d0
    add.w   (%a1),%d1
    cmp.w   %d1,%d0
    bge.s   .Lgsx_chkclip_out
    move.w  (%a0)+,%d1
    add.w   (%a2),%d2
    cmp.w   %d2,%d1
    bge.s   .Lgsx_chkclip_out
    add.w   (%a0)+,%d0
    cmp.w   (%a1),%d0
    blt.s   .Lgsx_chkclip_out
    add.w   (%a0)+,%d1
    cmp.w   (%a2),%d1
    blt.s   .Lgsx_chkclip_out
.Lgsx_chkclip_in:
    moveq   #1,%d0
    rts
.Lgsx_chkclip_out:
    moveq   #0,%d0
    rts

/* =============================================================================================================
 * Region $fda956..$fda97b: gsx_bxpts — (rect): its five corners, closed, into ptsin
 * ============================================================================================================= */
    .globl  aes_rom_gsx_bxpts
aes_rom_gsx_bxpts:
    movea.l 4(%sp),%a0
    move.l  (%a0)+,%d0
    move.w  (%a0)+,%d1
    subq.w  #1,%d1
    move.w  (%a0)+,%d2
    subq.w  #1,%d2
    lea     AES_GSX_PTSIN,%a1
    move.l  %d0,(%a1)+
    move.l  %d0,(%a1)
    add.w   %d1,(%a1)
    move.l  (%a1)+,(%a1)+
    move.l  %d0,(%a1)
    add.w   %d2,-(%a1)
    move.l  (%a1)+,(%a1)+
    move.w  %d0,(%a1)
    rts
/* SIZED, as the file's last entry: `gemgraf.c`'s weak C twins follow it in the shipped blob, nameless once their glue
 * displaces them, and the m68k call graph reads an unsized function on to the next label (`gsx.S` says the same). */
    .size   aes_rom_gsx_bxpts,.-aes_rom_gsx_bxpts
