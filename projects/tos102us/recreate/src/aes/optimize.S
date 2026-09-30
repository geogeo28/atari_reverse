/* optimize.S — the AES utility layer ("optimize", $fecb5a..$fed3bd) as the ROM spells it, and the Alcyon runtime's
 * lmul/ldiv: the TRANSCRIPTIONS a target build ships, where `strings.c` (the memory and string helpers) and `rect.c`
 * (the rectangle helpers) are what Tier 1's host differential proves.
 *
 * WHY THESE ARE ASSEMBLY. Each entry is hand-written 68000 in the ROM — a `move.b (a0)+,(a1)+; bne` copy, a `dbf` fill,
 * a byte counter in D0.b, a GRECT's pointers loaded by one `movem` — and each C port measures over Tier 3's 1.10 bar
 * against it (`bench/tier3.py`), so by the user's rule the target carries the ROM's own instructions
 * (`include/transcribed.h`). The Alcyon runtime's `ldiv` measures over the bar too on its callers' divisors (368640 /
 * 4608, 100000 / 30000); `lmul`, whose C is under it, is here for merge_str's sake: its two `jsr`s reach both, and a
 * byte-exact merge_str needs them byte-exact where it can relocate its calls to (they are compiled C with no Line-F
 * word, so they qualify).
 *
 * TWO PINNED REGIONS, each laid out in the ROM's order from its first entry (`test/test_aes_strings_asm.py` pins every
 * byte, `transcription.assert_transcribed`):
 *   * $fecb6e..$fed18d — the optimize layer from mul_div to wildcmp, ONE span because the SHARED RETURN TAILS at
 *     $fed066/$fed06a/$fed06e lie at its far end and every routine that leaves through them — rc_equal, streq,
 *     strlen, and inside and rc_intersect — must lie in the tails' own region (`../../README.md`, "An AES `.S`").
 *     Laid out as the ROM has them and entered by nothing here: the code between mul_div and set_contrl_ptr no ROM
 *     routine reaches (an unsigned mul_div and five pointer setters of the VDI parameter block); inside and
 *     rc_intersect, whose C is under the bar and ships; and the object-text helpers ($fecf84..$fed065, `objtext.c`),
 *     which Line-F-call other routines (their Line-F words are bytes, never executed by a row) and whose `bsr.w`s
 *     reach OB_ADDR at $fed18e, past the region, spelt as the ROM's words;
 *   * $fe3db4..$fe3ea5 — lmul and ldiv. merge_str's two `jsr`s are its only references out of a region, RELOCATED to
 *     where these are linked (the battery declares both).
 *
 * THE SPELLING POLICY (`m68k_encodings.h`): where GNU as would pick another encoding for the ROM's instruction —
 * `cmp.b/w/l #imm,Dn` and `add.w #imm,Dn` in the register form, `movea.l #imm,An` it would shorten to `.w` — the
 * ROM's words are spelt, the instruction in the comment.
 *
 * REGISTERS, as the ROM leaves them — the relation compares all of them. Against the GCC m68k ABI five entries leave a
 * callee-saved register changed, and `include/transcribed.h` lists each set: lmul's sign count is D2, merge_str forms
 * each digit in D2 (and calls lmul), rc_union's far edges are D2, and r_get and r_set leave A2 loaded from their frame.
 * ldiv saves D2-D7 round its work; every other entry uses D0/D1/A0/A1 alone, or saves what it uses (merge_str's and
 * r_get's `movem`).
 */
#include "addrs.h"
#include "m68k_encodings.h"
#include "aes/aes.h"
#include "aes/objects.h"
#include "aes/strings.h"

/* The object-text helpers' foreign words: their Line-F calls by the call table's byte offset, and their `bsr.w`s to
 * OB_ADDR, each displacement measured from its own extension word's ROM address, as the ROM's is — the routine's ROM
 * address (`routine`) plus how far past its first instruction (`start`, its label here) the word sits. */
#define LINEF_OFFSET_LSTCPY         0x138   /* -> $fecbe6 */
#define LINEF_OFFSET_OB_TEXT        0x174   /* -> $fecf84 */
#define LINEF_OFFSET_OB_SCAN        0x178   /* -> $fed010 */
#define BSR_W_TO_OB_ADDR(routine, start) .word M68K_BSR_W; .word AES_ROM_OB_ADDR - ((routine) + (. - (start)))

    .text

/* =============================================================================================================
 * Region $fecb6e..$fed18d: the optimize layer, one span — every routine that leaves through the shared tails lies in it
 * ============================================================================================================= */

/* ---- mul_div, $fecb6e: (m1 * m2) / d rounded, the words at 4/6/8(sp) --------------------------------------- */
    .globl  aes_rom_mul_div
aes_rom_mul_div:
    move.w  6(%sp),%d0
    add.w   %d0,%d0
    muls.w  4(%sp),%d0
    divs.w  8(%sp),%d0
    bmi.s   .Lmul_div_negative
    addq.w  #1,%d0
    asr.w   #1,%d0
    rts
.Lmul_div_negative:
    subq.w  #1,%d0
    asr.w   #1,%d0
    rts

/* ---- $fecb8a..$fecbc5: reached by no ROM code — an unsigned mul_div and the parameter block's pointer setters -- */
    move.w  6(%sp),%d0
    add.w   %d0,%d0
    mulu.w  4(%sp),%d0
    divu.w  8(%sp),%d0
    addq.w  #1,%d0
    asr.w   #1,%d0
    rts
    move.l  4(%sp),AES_GSX_PB + 8      /* ptsin */
    rts
    move.l  4(%sp),AES_GSX_PB + 4      /* intin */
    rts
    move.l  4(%sp),AES_GSX_PB + 16     /* ptsout */
    rts
    move.l  4(%sp),AES_GSX_PB + 12     /* intout */
    rts

/* ---- set_contrl_ptr, $fecbc6: contrl[7..8] := the longword at 4(sp) ---------------------------------------- */
    .globl  aes_rom_set_contrl_ptr
aes_rom_set_contrl_ptr:
    move.l  4(%sp),AES_GSX_CONTRL_PTR
    rts
    move.l  4(%sp),AES_GSX_CONTRL_PTR2     /* $fecbd0: contrl[9..10] := it, reached by no ROM code */
    rts

/* ---- get_contrl_ptr2, $fecbda: *(4(sp)) := contrl[9..10] ------------------------------------------------- */
    .globl  aes_rom_get_contrl_ptr2
aes_rom_get_contrl_ptr2:
    movea.l 4(%sp),%a0
    move.l  AES_GSX_CONTRL_PTR2,(%a0)
    rts

/* ---- lstcpy, $fecbe6: (dst, src) with the NUL, D0.w = the length counted in a BYTE ---------------------------- */
    .globl  aes_rom_lstcpy
aes_rom_lstcpy:
    movea.l 8(%sp),%a0
    movea.l 4(%sp),%a1
    clr.l   %d0
.Llstcpy_next:
    addq.b  #1,%d0
    move.b  (%a0)+,(%a1)+
    bne.s   .Llstcpy_next
    subq.w  #1,%d0
    rts

/* ---- xstrpix, $fecbfa: (dst, src) a string's bytes as words, no NUL, D0 = the count (a byte) ------------------- */
    .globl  aes_rom_xstrpix
aes_rom_xstrpix:
    movea.l 8(%sp),%a0
    movea.l 4(%sp),%a1
    clr.l   %d0
    clr.l   %d1
.Lxstrpix_next:
    move.b  (%a0)+,%d1
    beq.s   .Lxstrpix_done
    move.w  %d1,(%a1)+
    addq.b  #1,%d0
    bra.s   .Lxstrpix_next
.Lxstrpix_done:
    rts

/* ---- wset, $fecc12: (dst, count, value) count words, none for 0 ------------------------------------------- */
    .globl  aes_rom_wset
aes_rom_wset:
    movea.l 4(%sp),%a0
    move.w  10(%sp),%d1
    move.w  8(%sp),%d0
    beq.s   .Lwset_done
.Lwset_next:
    move.w  %d1,(%a0)+
    subq.w  #1,%d0
    bne.s   .Lwset_next
.Lwset_done:
    rts

/* ---- xstrpix_n, $fecc28: (dst, src, count) count bytes as words, 65536 for 0 ------------------------------- */
    .globl  aes_rom_xstrpix_n
aes_rom_xstrpix_n:
    movea.l 4(%sp),%a0
    movea.l 8(%sp),%a1
    move.w  12(%sp),%d0
    clr.w   %d1
.Lxstrpix_n_next:
    move.b  (%a1)+,%d1
    move.w  %d1,(%a0)+
    subq.w  #1,%d0
    bne.s   .Lxstrpix_n_next
    rts

/* ---- wcopy, $fecc40: (dst, src, count) count words, none for 0 -------------------------------------------- */
    .globl  aes_rom_wcopy
aes_rom_wcopy:
    movea.l 4(%sp),%a0
    movea.l 8(%sp),%a1
    move.w  12(%sp),%d0
    beq.s   .Lwcopy_done
.Lwcopy_next:
    move.w  (%a1)+,(%a0)+
    subq.w  #1,%d0
    bne.s   .Lwcopy_next
.Lwcopy_done:
    rts

/* ---- wfill, $fecc56: (dst, count, value) — the `beq` tests the VALUE, the last word loaded ------------------ */
    .globl  aes_rom_wfill
aes_rom_wfill:
    movea.l 4(%sp),%a0
    move.w  8(%sp),%d0
    move.w  10(%sp),%d1
    beq.s   .Lwfill_done
.Lwfill_next:
    move.w  %d1,(%a0)+
    subq.w  #1,%d0
    bne.s   .Lwfill_next
.Lwfill_done:
    rts

/* ---- lstrlen, $fecc6c: a string's length, a word, each byte counted before it is tested ------------------- */
    .globl  aes_rom_lstrlen
aes_rom_lstrlen:
    movea.l 4(%sp),%a0
    clr.w   %d0
.Llstrlen_next:
    addq.w  #1,%d0
    cmpi.b  #STRING_NUL,(%a0)+
    bne.s   .Llstrlen_next
    subq.w  #1,%d0
    rts

/* ---- lbcopy, $fecc7e: (dst, src, count) memmove — backward when src < dst as SIGNED longs ------------------ */
    .globl  aes_rom_lbcopy
aes_rom_lbcopy:
    movem.l 4(%sp),%a0-%a1
    clr.l   %d0
    move.w  12(%sp),%d0
    beq.s   .Llbcopy_done
    cmpa.l  %a0,%a1
    blt.s   .Llbcopy_backward
.Llbcopy_forward:
    move.b  (%a1)+,(%a0)+
    subq.w  #1,%d0
    bne.s   .Llbcopy_forward
    rts
.Llbcopy_backward:
    adda.l  %d0,%a1
    adda.l  %d0,%a0
    subq.w  #1,%d0
.Llbcopy_back_next:
    move.b  -(%a1),-(%a0)
    subq.w  #1,%d0
    bpl.s   .Llbcopy_back_next
.Llbcopy_done:
    rts

/* ---- r_get, $fecca6: (rect, &x, &y, &w, &h) each word read and stored in turn --------------------------------------- */
    .globl  aes_rom_r_get
aes_rom_r_get:
    movem.l %a3-%a4,-(%sp)
    movem.l 12(%sp),%a0-%a4                     /* the frame, past the two saved registers */
    move.w  (%a0)+,(%a1)
    move.w  (%a0)+,(%a2)
    move.w  (%a0)+,(%a3)
    move.w  (%a0)+,(%a4)
    movem.l (%sp)+,%a3-%a4
    rts

/* ---- r_set, $feccbe: (rect, x, y, w, h) the four frame words as two longwords ------------------------------ */
    .globl  aes_rom_r_set
aes_rom_r_set:
    movem.l 4(%sp),%a0-%a2                      /* A1 = x:y, A2 = w:h */
    movem.l %a1-%a2,(%a0)
    rts

/* ---- rc_copy, $feccca: (from, to) two longwords, each read and stored in turn ---------------------------------- */
    .globl  aes_rom_rc_copy
aes_rom_rc_copy:
    movem.l 4(%sp),%a0-%a1
    move.l  (%a0)+,(%a1)+
    move.l  (%a0)+,(%a1)+
    rts

/* ---- inside, $feccd6: (x, y, rect) the point in it — C ships (under the bar); laid out for the region -------- */
    movem.w 4(%sp),%d0-%d1
    movea.l 8(%sp),%a0
    cmp.w   (%a0),%d0
    blt.w   .Lreturn_false
    cmp.w   2(%a0),%d1
    blt.w   .Lreturn_false
    move.w  (%a0),%d2
    add.w   4(%a0),%d2
    cmp.w   %d2,%d0
    bge.w   .Lreturn_false
    move.w  2(%a0),%d2
    add.w   6(%a0),%d2
    cmp.w   %d2,%d1
    bge.w   .Lreturn_false
    bra.w   .Lreturn_true

/* ---- rc_equal, $fecd0c: (one, other) two longword compares, the second only if the first matched --------- */
    .globl  aes_rom_rc_equal
aes_rom_rc_equal:
    movem.l 4(%sp),%a0-%a1
    cmpm.l  (%a0)+,(%a1)+
    bne.w   .Lreturn_false
    cmpm.l  (%a0)+,(%a1)+
    bne.w   .Lreturn_false
    bra.w   .Lreturn_true

/* ---- rc_intersect, $fecd22: (clip, rect) — C ships (under the bar); laid out for the region --------------- */
    movem.l 4(%sp),%a0-%a1
    move.w  (%a1),%d0
    cmp.w   (%a0),%d0
    bge.s   .Lintersect_x_origin
    move.w  (%a0),%d0
.Lintersect_x_origin:
    move.w  (%a0),%d1
    add.w   4(%a0),%d1
    move.w  (%a1),%d2
    add.w   4(%a1),%d2
    cmp.w   %d1,%d2
    ble.s   .Lintersect_x_far
    move.w  %d1,%d2
.Lintersect_x_far:
    move.w  %d0,(%a1)
    sub.w   %d0,%d2
    move.w  %sr,-(%sp)                          /* the x axis's flags, kept on the stack */
    move.w  %d2,4(%a1)
    move.w  2(%a1),%d0
    cmp.w   2(%a0),%d0
    bge.s   .Lintersect_y_origin
    move.w  2(%a0),%d0
.Lintersect_y_origin:
    move.w  2(%a0),%d1
    add.w   6(%a0),%d1
    move.w  2(%a1),%d2
    add.w   6(%a1),%d2
    cmp.w   %d1,%d2
    ble.s   .Lintersect_y_far
    move.w  %d1,%d2
.Lintersect_y_far:
    move.w  %d0,2(%a1)
    sub.w   %d0,%d2
    move.w  %sr,%d0
    move.w  %d2,6(%a1)
    move.w  (%sp)+,%ccr
    ble.w   .Lreturn_false
    move.w  %d0,%ccr
    ble.w   .Lreturn_false
    bra.w   .Lreturn_true

/* ---- rc_union, $fecd8c: (from, into) the smaller origin and the larger far edge, x stored before y is read - */
    .globl  aes_rom_rc_union
aes_rom_rc_union:
    movem.l 4(%sp),%a0-%a1
    move.w  (%a1),%d0
    cmp.w   (%a0),%d0
    blt.s   1f
    move.w  (%a0),%d0
1:  move.w  (%a0),%d1
    add.w   4(%a0),%d1
    move.w  (%a1),%d2
    add.w   4(%a1),%d2
    cmp.w   %d1,%d2
    bgt.s   2f
    move.w  %d1,%d2
2:  sub.w   %d0,%d2
    move.w  %d0,(%a1)
    move.w  %d2,4(%a1)
    move.w  2(%a1),%d0
    cmp.w   2(%a0),%d0
    blt.s   3f
    move.w  2(%a0),%d0
3:  move.w  2(%a0),%d1
    add.w   6(%a0),%d1
    move.w  2(%a1),%d2
    add.w   6(%a1),%d2
    cmp.w   %d1,%d2
    bgt.s   4f
    move.w  %d1,%d2
4:  sub.w   %d0,%d2
    move.w  %d0,2(%a1)
    move.w  %d2,6(%a1)
    rts

/* ---- rc_constrain, $fecde4: (container, rect) the origin pulled up, then back so the far edge fits --------- */
    .globl  aes_rom_rc_constrain
aes_rom_rc_constrain:
    movem.l 4(%sp),%a0-%a1
    move.w  (%a0),%d0
    cmp.w   (%a1),%d0
    blt.s   1f
    move.w  %d0,(%a1)
1:  add.w   4(%a0),%d0
    move.w  (%a1),%d1
    add.w   4(%a1),%d1
    cmp.w   %d1,%d0
    bge.s   2f
    sub.w   4(%a1),%d0
    move.w  %d0,(%a1)
2:  move.w  2(%a0),%d0
    cmp.w   2(%a1),%d0
    blt.s   3f
    move.w  %d0,2(%a1)
3:  add.w   6(%a0),%d0
    move.w  2(%a1),%d1
    add.w   6(%a1),%d1
    cmp.w   %d1,%d0
    bge.s   4f
    sub.w   6(%a1),%d0
    move.w  %d0,2(%a1)
4:  rts

/* ---- movs, $fece2e: (count, src, dst) count bytes forward, `dbf` --------------------------------------------- */
    .globl  aes_rom_movs
aes_rom_movs:
    move.w  4(%sp),%d0
    movem.l 6(%sp),%a0-%a1
    bra.s   .Lmovs_count
.Lmovs_next:
    move.b  (%a0)+,(%a1)+
.Lmovs_count:
    dbf     %d0,.Lmovs_next
    rts

/* ---- min, $fece42, and max, $fece4e: the smaller / larger signed word — max's tail shared ------------------- */
    .globl  aes_rom_min
aes_rom_min:
    move.w  4(%sp),%d0
    cmp.w   6(%sp),%d0
    blt.s   .Lmin_max_done
    bra.s   .Lmin_max_second
    .globl  aes_rom_max
aes_rom_max:
    move.w  4(%sp),%d0
    cmp.w   6(%sp),%d0
    bgt.s   .Lmin_max_done
.Lmin_max_second:
    move.w  6(%sp),%d0
.Lmin_max_done:
    rts

/* ---- bfill, $fece5e: (count, byte, dst) count bytes, `dbf` ---------------------------------------------------- */
    .globl  aes_rom_bfill
aes_rom_bfill:
    move.w  4(%sp),%d0
    move.b  7(%sp),%d1
    movea.l 8(%sp),%a0
    bra.s   .Lbfill_count
.Lbfill_next:
    move.b  %d1,(%a0)+
.Lbfill_count:
    dbf     %d0,.Lbfill_next
    rts

/* ---- toupper, $fece74: the low byte, sign-extended, a-z less 32 ------------------------------------------------ */
    .globl  aes_rom_toupper
aes_rom_toupper:
    move.b  5(%sp),%d0
    ext.w   %d0
    .word   M68K_CMP_W_IMMEDIATE(0), TOUPPER_FIRST          /* cmp.w #TOUPPER_FIRST,%d0 */
    blt.s   .Ltoupper_done
    .word   M68K_CMP_W_IMMEDIATE(0), TOUPPER_LAST           /* cmp.w #TOUPPER_LAST,%d0 */
    bgt.s   .Ltoupper_done
    .word   M68K_ADD_W_IMMEDIATE(0), TOUPPER_DISTANCE & 0xffff /* add.w #TOUPPER_DISTANCE,%d0 */
.Ltoupper_done:
    rts

/* ---- strlen, $fece8c: a string's length, a word, each byte tested before it is counted --------------------- */
    .globl  aes_rom_strlen
aes_rom_strlen:
    movea.l 4(%sp),%a0
    clr.w   %d0
.Lstrlen_next:
    tst.b   (%a0)+
    beq.w   .Lreturn
    addq.w  #1,%d0
    bra.s   .Lstrlen_next

/* ---- streq, $fece9c: 1 when two strings are equal, through the shared tails -------------------------------- */
    .globl  aes_rom_streq
aes_rom_streq:
    movem.l 4(%sp),%a0-%a1
.Lstreq_next:
    tst.b   (%a0)
    beq.s   .Lstreq_left_ended
    cmpm.b  (%a0)+,(%a1)+
    beq.s   .Lstreq_next
    bra.w   .Lreturn_false
.Lstreq_left_ended:
    tst.b   (%a1)
    bne.w   .Lreturn_false
    bra.w   .Lreturn_true

/* ---- strcpy, $feceb8: (src, dst) with the NUL, D0 = dst past it --------------------------------------------- */
    .globl  aes_rom_strcpy
aes_rom_strcpy:
    movem.l 4(%sp),%a0-%a1
.Lstrcpy_next:
    move.b  (%a0)+,(%a1)+
    bne.s   .Lstrcpy_next
    bra.s   .Lanswer_destination

/* ---- strscn, $fecec4: (src, dst, stop) up to the stop byte or the NUL, D0 = dst's end, nothing terminated ---- */
    .globl  aes_rom_strscn
aes_rom_strscn:
    movem.l 4(%sp),%a0-%a1
    move.b  13(%sp),%d0
.Lstrscn_next:
    cmp.b   (%a0),%d0
    beq.s   .Lanswer_destination
    tst.b   (%a0)
    beq.s   .Lanswer_destination
    move.b  (%a0)+,(%a1)+
    bra.s   .Lstrscn_next

/* ---- strcat, $feceda: (src, dst) src after dst's NUL, D0 = dst past the new NUL ------------------------------ */
    .globl  aes_rom_strcat
aes_rom_strcat:
    movem.l 4(%sp),%a0-%a1
.Lstrcat_find_end:
    tst.b   (%a1)+
    bne.s   .Lstrcat_find_end
    subq.l  #1,%a1
.Lstrcat_next:
    move.b  (%a0)+,(%a1)+
    bne.s   .Lstrcat_next
.Lanswer_destination:                   /* $feceea: strcpy's, strscn's, strcat's and scasb's answer */
    move.l  %a1,%d0
    rts

/* ---- scasb, $feceee: (string, byte) the byte's first place or the NUL's ------------------------------------ */
    .globl  aes_rom_scasb
aes_rom_scasb:
    movea.l 4(%sp),%a1
    move.b  9(%sp),%d0
.Lscasb_next:
    tst.b   (%a1)
    beq.s   .Lanswer_destination
    cmp.b   (%a1),%d0
    beq.s   .Lanswer_destination
    addq.l  #1,%a1
    bra.s   .Lscasb_next

/* ---- strchk, $fecf02: 0 when equal, else the signed byte difference where they first differ ---------------- */
    .globl  aes_rom_strchk
aes_rom_strchk:
    movem.l 4(%sp),%a0-%a1
    clr.w   %d0
.Lstrchk_next:
    move.b  (%a0),%d1
    cmp.b   (%a1)+,%d1
    bne.s   .Lstrchk_differ
    tst.b   (%a0)+
    beq.s   .Lstrchk_done
    bra.s   .Lstrchk_next
.Lstrchk_differ:
    move.b  (%a0),%d0
    ext.w   %d0
    move.b  -1(%a1),%d1
    ext.w   %d1
    sub.w   %d1,%d0
.Lstrchk_done:
    rts

/* ---- fmt_str, $fecf24: (src, dst) "NAME.EXT" -> "NAME    EXT" --------------------------------------------- */
    .globl  aes_rom_fmt_str
aes_rom_fmt_str:
    movem.l 4(%sp),%a0-%a1
    move.w  #FMT_NAME_BYTES - 1,%d0
.Lfmt_name:
    tst.b   (%a0)
    beq.s   .Lfmt_pad
    cmpi.b  #STRING_DOT,(%a0)
    beq.s   .Lfmt_pad
    move.b  (%a0)+,(%a1)+
    dbf     %d0,.Lfmt_name
    bra.s   .Lfmt_extension
.Lfmt_pad:
    tst.b   (%a0)
    beq.s   .Lformat_terminate
.Lfmt_space:
    move.b  #STRING_SPACE,(%a1)+
    dbf     %d0,.Lfmt_space
.Lfmt_extension:
    tst.b   (%a0)+
    beq.s   .Lformat_terminate
.Lfmt_extension_next:
    tst.b   (%a0)
    beq.s   .Lformat_terminate
    move.b  (%a0)+,(%a1)+
    bra.s   .Lfmt_extension_next

/* ---- unfmt_str, $fecf58: (src, dst) "NAME    EXT" -> "NAME.EXT" ------------------------------------------- */
    .globl  aes_rom_unfmt_str
aes_rom_unfmt_str:
    movem.l 4(%sp),%a0-%a1
    move.w  #FMT_NAME_BYTES - 1,%d0
.Lunfmt_name:
    move.b  (%a0)+,%d1
    tst.b   %d1
    beq.s   .Lformat_terminate
    .word   M68K_CMP_B_IMMEDIATE(1), STRING_SPACE           /* cmp.b #STRING_SPACE,%d1 */
    beq.s   .Lunfmt_skip
    move.b  %d1,(%a1)+
.Lunfmt_skip:
    dbf     %d0,.Lunfmt_name
    move.b  #STRING_DOT,(%a1)+
.Lunfmt_extension:
    tst.b   (%a0)
    beq.s   .Lformat_terminate
    move.b  (%a0)+,(%a1)+
    bra.s   .Lunfmt_extension
.Lformat_terminate:                     /* $fecf80: fmt_str's and unfmt_str's NUL */
    clr.b   (%a1)
    rts

/* ---- $fecf84..$fed065: the object-text helpers, as the ROM has them (entered by nothing here) ---------------
 * Their `bsr.w` to OB_ADDR ($fed18e, past this region) and their Line-F calls are the ROM's words. */
.Lfs_sset:
    movea.l 14(%sp),%a1                 /* $fecf84: an object's text and its length */
    .word   M68K_MOVEA_L_IMMEDIATE(0)   /* movea.l #12,%a0 */
    .long   12
    BSR_W_TO_OB_ADDR(AES_ROM_FS_SSET, .Lfs_sset)
    movea.l (%a0),%a0
    move.l  (%a0),(%a1)
    move.l  %a0,-(%sp)
    move.l  14(%sp),-(%sp)
    move.l  (%a0),-(%sp)
    .word   M68K_LINE_F_WORD + LINEF_OFFSET_LSTCPY
    addq.l  #8,%sp
    movea.l (%sp)+,%a0
    movea.l 18(%sp),%a1
    adda.l  #OB_BYTES,%a0
    move.w  (%a0),(%a1)
    rts
    link    %a6,#-8                     /* $fecfb2 */
    pea     -6(%a6)
    pea     -4(%a6)
    move.l  14(%a6),-(%sp)
    move.w  12(%a6),-(%sp)
    move.l  8(%a6),-(%sp)
    .word   M68K_LINE_F_WORD + LINEF_OFFSET_OB_TEXT
    adda.l  #18,%sp
    unlk    %a6
    rts
.Lfs_sget:
    .word   M68K_MOVEA_L_IMMEDIATE(0)   /* $fecfd6: movea.l #12,%a0 */
    .long   12
    BSR_W_TO_OB_ADDR(AES_ROM_FS_SGET, .Lfs_sget)
    movea.l (%a0),%a0
    move.l  (%a0),-(%sp)
    move.l  14(%sp),-(%sp)
    .word   M68K_LINE_F_WORD + LINEF_OFFSET_LSTCPY
    addq.l  #8,%sp
    rts
.Linf_fldset:
    .word   M68K_MOVEA_L_IMMEDIATE(0)   /* $fecfee: movea.l #10,%a0 */
    .long   10
    BSR_W_TO_OB_ADDR(AES_ROM_INF_FLDSET, .Linf_fldset)
    clr.w   %d0
    move.w  10(%sp),%d0
    and.w   12(%sp),%d0
    beq.s   .Lobject_state_clear
    move.w  14(%sp),(%a0)
    bra.s   .Lobject_state_done
.Lobject_state_clear:
    move.w  16(%sp),(%a0)
.Lobject_state_done:
    rts
.Linf_gindex:
    .word   M68K_MOVEA_L_IMMEDIATE(0)   /* $fed010: movea.l #11,%a0 */
    .long   11
    BSR_W_TO_OB_ADDR(AES_ROM_INF_GINDEX, .Linf_gindex)
    move.w  10(%sp),%d0
    subq.w  #1,%d0
    move.w  %d0,%d1
.Lobject_scan_next:
    btst    #0,(%a0)
    beq.s   .Lobject_scan_step
    sub.w   %d1,%d0
    bra.s   .Lobject_scan_done
.Lobject_scan_step:
    adda.l  #OB_BYTES,%a0
    dbf     %d1,.Lobject_scan_next
    move.w  %d1,%d0
.Lobject_scan_done:
    rts
.Linf_what:
    move.w  #2,-(%sp)                   /* $fed03a */
    move.w  10(%sp),-(%sp)
    move.l  8(%sp),-(%sp)
    .word   M68K_LINE_F_WORD + LINEF_OFFSET_OB_SCAN
    addq.l  #8,%sp
    .word   M68K_CMP_W_IMMEDIATE(0), -1                     /* cmp.w #-1,%d0: the scan's none */
    beq.s   .Lreturn
    move.w  %d0,%d1
    add.w   %d0,8(%sp)
    .word   M68K_MOVEA_L_IMMEDIATE(0)   /* movea.l #10,%a0 */
    .long   10
    BSR_W_TO_OB_ADDR(AES_ROM_INF_WHAT, .Linf_what)
    clr.w   (%a0)
    tst.w   %d1
    beq.s   .Lreturn_true

/* ---- the SHARED RETURN TAILS, $fed066 / $fed06a / $fed06e: word answers, D0's high word the caller's -------- */
.Lreturn_false:
    clr.w   %d0
    bra.s   .Lreturn
.Lreturn_true:
    move.w  #1,%d0
.Lreturn:
    rts

/* ---- merge_str, $fed070: (dst, template, parameters) %L %W %S %% into a NUL-ended string -------------------- */
    .globl  aes_rom_merge_str
aes_rom_merge_str:
    movem.l %d3-%d6/%a3-%a5,-(%sp)
    movem.l 32(%sp),%a3-%a5
    clr.w   %d3                         /* the slot offset */
.Lmerge_next:
    tst.b   (%a4)
    beq.w   .Lmerge_done
    cmpi.b  #STRING_PERCENT,(%a4)
    beq.s   .Lmerge_code
    move.b  (%a4)+,(%a3)+
    bra.s   .Lmerge_next
.Lmerge_code:
    tst.b   (%a4)+
    move.b  (%a4)+,%d0
    .word   M68K_CMP_B_IMMEDIATE(0), STRING_PERCENT         /* cmp.b #STRING_PERCENT,%d0 */
    bne.s   .Lmerge_not_percent
    move.b  %d0,(%a3)+
    bra.s   .Lmerge_next
.Lmerge_not_percent:
    .word   M68K_CMP_B_IMMEDIATE(0), MERGE_CODE_LONG        /* cmp.b #MERGE_CODE_LONG,%d0 */
    bne.s   .Lmerge_not_long
    movea.w %d3,%a0
    adda.l  %a5,%a0
    move.l  (%a0),%d4
    addq.w  #MERGE_SLOT_BYTES,%d3
    bra.s   .Lmerge_number
.Lmerge_not_long:
    .word   M68K_CMP_B_IMMEDIATE(0), MERGE_CODE_WORD        /* cmp.b #MERGE_CODE_WORD,%d0 */
    bne.s   .Lmerge_not_word
    clr.l   %d4
    movea.w %d3,%a0
    adda.l  %a5,%a0
    move.w  (%a0),%d4
    addq.w  #MERGE_SLOT_BYTES,%d3
    bra.s   .Lmerge_number
.Lmerge_not_word:
    .word   M68K_CMP_B_IMMEDIATE(0), MERGE_CODE_STRING      /* cmp.b #MERGE_CODE_STRING,%d0 */
    bne.s   .Lmerge_next
    movea.w %d3,%a0
    adda.l  %a5,%a0
    movea.l (%a0),%a0
    addq.w  #MERGE_SLOT_BYTES,%d3
.Lmerge_string_next:
    tst.b   (%a0)
    beq.s   .Lmerge_next
    move.b  (%a0)+,(%a3)+
    bra.s   .Lmerge_string_next
.Lmerge_number:                         /* D4 the value; its digits least significant first onto the stack */
    clr.l   %d5
    suba.l  #MERGE_DIGITS_BYTES,%sp
.Lmerge_digit:
    tst.l   %d4
    beq.s   .Lmerge_digits_done
    move.l  #DECIMAL_BASE,-(%sp)
    move.l  %d4,-(%sp)
    .word   M68K_JSR_ABSOLUTE_LONG      /* jsr aes_rom_ldiv.l */
    .long   aes_rom_ldiv
    move.l  %d0,%d6
    move.l  %d0,(%sp)
    .word   M68K_JSR_ABSOLUTE_LONG      /* jsr aes_rom_lmul.l */
    .long   aes_rom_lmul
    addq.l  #8,%sp
    move.l  %d4,%d2
    sub.l   %d0,%d2
    .word   M68K_ADD_W_IMMEDIATE(2), DIGIT_ZERO             /* add.w #DIGIT_ZERO,%d2 */
    move.b  %d2,0(%sp,%d5.w)
    addq.w  #1,%d5
    move.l  %d6,%d4
    bra.s   .Lmerge_digit
.Lmerge_digits_done:
    subq.w  #1,%d5
    bge.s   .Lmerge_digits_out
    move.b  #DIGIT_ZERO,(%a3)+
    bra.s   .Lmerge_digits_dropped
.Lmerge_digits_out:
    move.b  0(%sp,%d5.w),(%a3)+
    dbf     %d5,.Lmerge_digits_out
.Lmerge_digits_dropped:
    adda.l  #MERGE_DIGITS_BYTES,%sp
    bra.w   .Lmerge_next
.Lmerge_done:
    clr.b   (%a3)
    movem.l (%sp)+,%d3-%d6/%a3-%a5
    rts

/* ---- wildcmp, $fed12e: (pattern, name) 1 when the name matches `*` / `?` -------------------------------------- */
    .globl  aes_rom_wildcmp
aes_rom_wildcmp:
    movem.l 4(%sp),%a0-%a1
.Lwild_next:
    tst.b   (%a0)
    beq.s   .Lwild_rest
    tst.b   (%a1)
    beq.s   .Lwild_rest
    cmpi.b  #STRING_WILDCARD_ONE,(%a0)
    bne.s   .Lwild_not_one
    addq.l  #1,%a0
    cmpi.b  #STRING_DOT,(%a1)
    beq.s   .Lwild_next
.Lwild_name_step:
    addq.l  #1,%a1
    bra.s   .Lwild_next
.Lwild_not_one:
    cmpi.b  #STRING_WILDCARD_ANY,(%a0)
    bne.s   .Lwild_literal
    cmpi.b  #STRING_DOT,(%a1)
    bne.s   .Lwild_name_step
    addq.l  #1,%a0
    bra.s   .Lwild_next
.Lwild_literal:
    move.b  (%a0),%d0
    cmp.b   (%a1),%d0
    bne.s   .Lwild_false
    addq.l  #1,%a0
    bra.s   .Lwild_name_step
.Lwild_rest_step:
    addq.l  #1,%a0
.Lwild_rest:
    cmpi.b  #STRING_WILDCARD_ANY,(%a0)
    beq.s   .Lwild_rest_step
    cmpi.b  #STRING_WILDCARD_ONE,(%a0)
    beq.s   .Lwild_rest_step
    cmpi.b  #STRING_DOT,(%a0)
    beq.s   .Lwild_rest_step
    tst.b   (%a0)
    bne.s   .Lwild_false
    tst.b   (%a1)
    bne.s   .Lwild_false
    move.w  #1,%d0
    bra.s   .Lwild_done
.Lwild_false:
    clr.w   %d0
.Lwild_done:
    rts

/* =============================================================================================================
 * Region $fe3db4..$fe3ea5: the Alcyon runtime (compiled C)
 * ============================================================================================================= */

/* ---- lmul, $fe3db4: the signed longs at 8/12(a6) -> their product's low longword; D2 the sign count --------- */
    .globl  aes_rom_lmul
aes_rom_lmul:
    link    %a6,#-4
    clr.w   %d2
    tst.l   8(%a6)
    bge.s   .Llmul_first_positive
    neg.l   8(%a6)
    addq.w  #1,%d2
.Llmul_first_positive:
    tst.l   12(%a6)
    bge.s   .Llmul_second_positive
    neg.l   12(%a6)
    addq.w  #1,%d2
.Llmul_second_positive:
    move.w  10(%a6),%d0
    mulu.w  14(%a6),%d0
    move.l  %d0,-4(%a6)
    move.w  8(%a6),%d0
    mulu.w  14(%a6),%d0
    move.w  12(%a6),%d1
    mulu.w  10(%a6),%d1
    add.w   %d1,%d0
    add.w   -4(%a6),%d0
    move.w  %d0,-4(%a6)
    move.l  -4(%a6),%d0
    btst    #0,%d2
    beq.s   .Llmul_done
    neg.l   %d0
.Llmul_done:
    unlk    %a6
    rts

/* ---- ldiv, $fe3e08: the signed longs at 8/12(a6) -> the quotient; the remainder at AES_LDIV_REMAINDER --------- */
    .globl  aes_rom_ldiv
aes_rom_ldiv:
    link    %a6,#-2
    movem.l %d2-%d7,-(%sp)
    clr.w   %d3                         /* the negations */
    clr.l   %d5                         /* the quotient */
    move.l  8(%a6),%d7                  /* the dividend */
    move.l  12(%a6),%d6                 /* the divisor */
    bne.s   .Lldiv_divisor
    move.l  #LDIV_BY_ZERO_REMAINDER,AES_LDIV_REMAINDER
    move.l  #LDIV_BY_ZERO_REMAINDER,%d0
    divs.w  #0,%d0
    bra.w   .Lldiv_done
.Lldiv_divisor:
    bge.s   .Lldiv_divisor_positive
    neg.l   %d6
    addq.w  #1,%d3
.Lldiv_divisor_positive:
    tst.l   %d7
    bge.s   .Lldiv_dividend_positive
    neg.l   %d7
    addq.w  #1,%d3
.Lldiv_dividend_positive:
    cmp.l   %d7,%d6
    bgt.s   .Lldiv_signs
    bne.s   .Lldiv_divide
    moveq   #1,%d5
    clr.l   %d7
    bra.s   .Lldiv_signs
.Lldiv_divide:
    .word   M68K_CMP_L_IMMEDIATE(7)     /* cmp.l #LDIV_ONE_DIVIDE_BELOW,%d7 */
    .long   LDIV_ONE_DIVIDE_BELOW
    bge.s   .Lldiv_bit_by_bit
    divu.w  %d6,%d7
    move.w  %d7,%d5
    swap    %d7
    ext.l   %d7
    bra.s   .Lldiv_signs
.Lldiv_bit_by_bit:
    moveq   #1,%d4
.Lldiv_align:
    cmp.l   %d6,%d7
    bcs.s   .Lldiv_subtract
    asl.l   #1,%d6
    asl.l   #1,%d4
    bra.s   .Lldiv_align
.Lldiv_subtract:
    tst.l   %d4
    beq.s   .Lldiv_signs
    cmp.l   %d6,%d7
    bcs.s   .Lldiv_shift
    or.l    %d4,%d5
    sub.l   %d6,%d7
.Lldiv_shift:
    lsr.l   #1,%d4
    lsr.l   #1,%d6
    bra.s   .Lldiv_subtract
.Lldiv_signs:
    .word   M68K_CMP_W_IMMEDIATE(3), 1  /* cmp.w #1,%d3: exactly one negation */
    bne.s   .Lldiv_same_signs
    neg.l   %d7
    move.l  %d7,AES_LDIV_REMAINDER
    move.l  %d5,%d0
    neg.l   %d0
    bra.s   .Lldiv_done
.Lldiv_same_signs:
    move.l  %d7,AES_LDIV_REMAINDER
    move.l  %d5,%d0
.Lldiv_done:
    tst.l   (%sp)+
    movem.l (%sp)+,%d3-%d7
    unlk    %a6
    rts
