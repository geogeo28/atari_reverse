/* gsx.S — the AES's VDI binding's Line-F-free atoms as the ROM spells them: gsx2, gsx_ncode and gsx_1code, gsx_mon
 * and gsx_fix — the TRANSCRIPTIONS a target build ships, where `gsx.c` is what Tier 1's host differential proves.
 *
 * WHY THESE ARE ASSEMBLY. Each is hand 68000 that reaches its globals at absolute addresses (`lea $c7e0,a1`,
 * `sub.w d0,$c86a`) where the C pays the image pointer on every access (`bench/tier3.py`'s (A)), and each C port
 * measures over Tier 3's 1.10 bar on its own cycles (mechanism (V)), so by the user's rule the target carries the
 * ROM's own instructions (`include/transcribed.h`). gsx_1code's C measures 1.40, so it is here on its own count —
 * and gsx_mon's `bsr.w` reaches it, which a byte-exact gsx_mon can relocate only into a region a battery pins. None of
 * them executes a Line-F word, which an AES `.S` may not (`../../README.md`, "An AES `.S`").
 *
 * FOUR PINNED REGIONS, each laid out in the ROM's order (`test/test_aes_gsx_transcription.py` pins every byte):
 *   * $fecb5a..$fecb6d gsx2, the word before the optimize layer's region (`optimize.S`);
 *   * $fe87d2..$fe8807 gsx_ncode and gsx_1code, whose `bsr.s` to gsx_ncode stays the ROM's word; gsx_ncode's
 *     `jmp gsx2` is RELOCATED to where gsx2 is linked;
 *   * $fe8a8e..$fe8aad gsx_mon, its `bsr.w gsx_1code` RELOCATED likewise;
 *   * $fda992..$fda9cd gsx_fix.
 *
 * THE TRAP. gsx2's `trap #2` is the machine's: on target, and under Tier 3, it enters the snapshot's own vector
 * and the ROM's VDI, as the ROM's gsx2 does. REGISTERS, as the ROM leaves them: gsx_fix leaves A2 at the MFDB's
 * last word (the table's row says so); every other entry changes D0/D1/A0/A1 alone — the VDI's entry restores D1-A6
 * round the trap, and gsx2 then hands D1 the block's address it loaded.
 */
#include "addrs.h"
#include "m68k_encodings.h"
#include "aes/aes.h"
#include "aes/gsx.h"

    .text

/* =============================================================================================================
 * Region $fecb5a..$fecb6d: gsx2 — the AES's one `trap #2`
 * ============================================================================================================= */
    .globl  aes_rom_gsx2
aes_rom_gsx2:
    lea     AES_GSX_PB,%a0
    move.l  #AES_GSX_CONTRL,(%a0)
    move.l  %a0,%d1
    moveq   #GEM_SELECTOR_VDI,%d0
    trap    #2
    rts

/* =============================================================================================================
 * Region $fe87d2..$fe8807: gsx_ncode, then gsx_1code
 * ============================================================================================================= */

/* ---- gsx_ncode, $fe87d2: (opcode, points, words) -> contrl[0,1] as one longword, contrl[3], the handle; gsx2 ---- */
    .globl  aes_rom_gsx_ncode
aes_rom_gsx_ncode:
    lea     4(%sp),%a0
    lea     AES_GSX_CONTRL,%a1
    move.l  (%a0)+,(%a1)+
    addq.l  #2,%a1
    move.w  (%a0)+,(%a1)
    addq.l  #6,%a1
    move.w  AES_GL_HANDLE,(%a1)
    .word   M68K_JMP_ABSOLUTE_LONG          /* jmp aes_rom_gsx2.l — gas would shorten it to (pc) */
    .long   aes_rom_gsx2

/* ---- gsx_1code, $fe87f0: (opcode, value) -> intin[0], then gsx_ncode(opcode, 0, 1) ---------------------------- */
    .globl  aes_rom_gsx_1code
aes_rom_gsx_1code:
    move.w  6(%sp),AES_GSX_INTIN
    move.l  #GSX_ONE_WORD,-(%sp)
    move.w  8(%sp),-(%sp)
    bsr.s   aes_rom_gsx_ncode
    addq.l  #6,%sp
    rts

/* =============================================================================================================
 * Region $fe8a8e..$fe8aad: gsx_mon — the nest counted down, the cursor shown at zero
 * ============================================================================================================= */
    .globl  aes_rom_gsx_mon
aes_rom_gsx_mon:
    moveq   #GSX_SHOW_AT_ONCE,%d0
    sub.w   %d0,AES_GL_MOFF
    bne.s   .Lgsx_mon_done
    move.w  %d0,-(%sp)
    move.w  #VDI_ROM_V_SHOW_C_OPCODE,-(%sp)
    bsr.w   aes_rom_gsx_1code
    addq.l  #4,%sp
    move.w  #GSX_MOUSE_SHOWN,AES_GL_MOUSE_SHOWN
.Lgsx_mon_done:
    rts

/* =============================================================================================================
 * Region $fda992..$fda9cd: gsx_fix — an MFDB for the screen (address 0) or a one-plane form
 * ============================================================================================================= */
    .globl  aes_rom_gsx_fix
aes_rom_gsx_fix:
    lea     4(%sp),%a0
    lea     AES_GL_WS,%a1
    movea.l (%a0)+,%a2
    move.l  (%a0)+,(%a2)+
    bne.s   .Lgsx_fix_form
    move.w  (%a1)+,%d0
    addq.w  #1,%d0
    move.w  %d0,(%a2)+
    move.w  (%a1)+,(%a2)
    addq.w  #1,(%a2)+
    lsr.w   #GSX_PIXELS_PER_WORD_SHIFT,%d0
    move.w  %d0,(%a2)+
    clr.w   (%a2)+
    move.w  AES_GL_NPLANES,(%a2)
    rts
.Lgsx_fix_form:
    move.w  (%a0)+,%d0
    lsl.w   #GSX_PIXELS_PER_BYTE_SHIFT,%d0
    move.w  %d0,(%a2)+
    move.w  (%a0)+,(%a2)+
    lsr.w   #GSX_PIXELS_PER_WORD_SHIFT,%d0
    move.w  %d0,(%a2)+
    clr.w   (%a2)+
    move.w  #GSX_FORM_PLANES,(%a2)
    rts
