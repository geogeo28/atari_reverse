/* gsxif.S — gemgsxif's Line-F-free leaves as the ROM spells them: gsx_mret, ratinit, gsx_mxmy and gsx_button — the
 * TRANSCRIPTIONS a target build ships, where `gsxif.c` is what Tier 1's host differential proves.
 *
 * WHY THESE ARE ASSEMBLY. Each is a few instructions of hand 68000 over globals at absolute addresses (`move.w
 * $9c0c,(a1)`, `clr.w $c86a`) where the C pays the image pointer on every access (`bench/tier3.py`'s (A)), and each C
 * port measures over Tier 3's 1.10 bar (ratinit on its own cycles, mechanism (V)), so by the user's rule the target
 * carries the ROM's own instructions (`include/transcribed.h`). None executes a Line-F word, which an AES `.S` may
 * not (`../../README.md`, "An AES `.S`"): ratinit reaches the VDI by `bsr.w` to gsx_1code (`gsx.S`).
 *
 * THREE PINNED REGIONS, each laid out in the ROM's order (`test/test_aes_gsxif_transcription.py` pins every byte):
 *   * $fe87bc..$fe87d1 gsx_mret, the words before gsx_ncode's region (`gsx.S`);
 *   * $fe88e4..$fe88f7 ratinit, its `bsr.w gsx_1code` RELOCATED to where gsx_1code is linked;
 *   * $fe8a54..$fe8a71 gsx_mxmy, then gsx_button.
 *
 * REGISTERS, as the ROM leaves them: gsx_mret changes A0, gsx_mxmy A0/A1, gsx_button D0, and ratinit what gsx_1code
 * does (D0/D1/A0/A1) — none a callee-saved one.
 */
#include "addrs.h"
#include "aes/aes.h"
#include "aes/gsx.h"
#include "aes/gsxif.h"

    .text

/* =============================================================================================================
 * Region $fe87bc..$fe87d1: gsx_mret — (&address, &length): gl_tmp's buffer, then gl_mlen
 * ============================================================================================================= */
    .globl  aes_rom_gsx_mret
aes_rom_gsx_mret:
    movea.l 4(%sp),%a0
    move.l  AES_GL_TMP,(%a0)
    movea.l 8(%sp),%a0
    move.l  AES_GL_MLEN,(%a0)
    rts

/* =============================================================================================================
 * Region $fe88e4..$fe88f7: ratinit — v_show_c(0), the hide nest 0
 * ============================================================================================================= */
    .globl  aes_rom_ratinit
aes_rom_ratinit:
    clr.w   -(%sp)
    move.w  #VDI_ROM_V_SHOW_C_OPCODE,-(%sp)
    bsr.w   aes_rom_gsx_1code
    addq.l  #4,%sp
    clr.w   AES_GL_MOFF
    rts

/* =============================================================================================================
 * Region $fe8a54..$fe8a71: gsx_mxmy — (&x, &y): xrat, yrat; then gsx_button — D0 = the buttons' word
 * ============================================================================================================= */
    .globl  aes_rom_gsx_mxmy
aes_rom_gsx_mxmy:
    lea     4(%sp),%a0
    movea.l (%a0)+,%a1
    move.w  AES_XRAT,(%a1)
    movea.l (%a0)+,%a1
    move.w  AES_YRAT,(%a1)
    rts

    .globl  aes_rom_gsx_button
aes_rom_gsx_button:
    move.w  AES_BUTTON,%d0
    rts
/* SIZED, as the file's last entry (`gsx.S`'s reason): the m68k call graph reads an unsized function on to the next
 * label, which in the shipped blob may be a nameless weak C twin (`test/transcription.py`, `_function_ends`). */
    .size   aes_rom_gsx_button,.-aes_rom_gsx_button
