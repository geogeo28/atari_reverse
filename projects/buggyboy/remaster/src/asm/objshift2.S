| objshift2.S — hand-written m68k core for the fixed-pass fine-x masked sprite blitter (.S: cpp runs
| first, so it #includes the shared constant headers — see the Engine constants block below).
| PERF30 A3 phase 1. The byte-exact REFERENCE is rm_blit_objshift2() in src/blit.c (fuzz-pinned);
| this is a drop-in replacement with the SAME C signature, shipped on the m68k builds behind
| -DRM_ASM_BLIT (see include/game.h RM_BLIT_OBJSHIFT2, render/atari/README, test/test_asm_blit.py).
| Never diverge from the C by one byte — test/test_asm_blit.py runs every fuzz case through both the C
| and this asm under Musashi and byte-compares the whole destination.
|
| The template is the ORIGINAL game's own blit_objshift2 @0x13ed6 (its cycle-profiled disassembly runs
| this exact work in 262,940 cyc vs the C's 314,216). Its winning tricks, ported here:
|   * moveq #-1 mask seed  — the 0xFFFF high word comes for free (it rotates into col0's straddle half).
|   * mask split by move/swap shuffles (4-cyc ops) instead of andi.w immediates.
|   * both destination columns walked with (a0)+ / (a2)+ post-increment; source with (a1)+.
|   * base families fully unrolled (3 / 2 / 1 straddle cells), no per-cell loop control; the per-row
|     rewind is held in d3/d5 (F3) so the row bookkeeping is suba.w %dN,%aN (8 cyc) not #imm (12 cyc).
|
| Contract (the caller's low words; see rm_blit_objshift2 in blit.c): width_idx in {0,1,2} selects base
| straddle 3-width_idx and ceiling 0x88+8*width_idx; only the argument slot's low word is read. rows_m1
| is drawn (int16)rows_m1+1 times — a bit-15-set rows_m1 draws ZERO rows, guarded at entry by a `bmi`
| so the 16-bit dbra never runs away (the C's `rows <= 0` skip).
| The one structural difference from the original is the ABI: the original is register-in
| (x@D0 rows_m1@D4 dst@A0 src@A1); this implements the remaster C signature, so it reads its 7 args off
| the stack (m68k SysV, each arg a 4-byte slot) and mirrors what GCC emits — a movem save/restore of the
| callee-saved registers it uses (the "C-ABI entry overhead" over the original's zero-prologue core).
|
| C signature (include/game.h):
|   void rm_blit_objshift2(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
|                          uint16_t x, uint16_t rows_m1, int width_idx);
|
| Algorithm (the SPEC is the C in blit.c; transcribed here):
|   fine_x = x & 0xf;  shl = 16 - fine_x;  shr = fine_x;
|   col = ((int16)x >> 1) & 0xfff8;                 aligned 8-byte column (signed)
|   base_ceiling = 0x88 + 8*width_idx;
|   col0 = dst + dst_off + sx16(col);  col1 = col0 + 8;  sp = src + src_off;
|   col < 0                       -> LEFT clip ladder (pre-advance sp/col0 per rung), then left edge
|   col - base_ceiling >= 0       -> RIGHT clip ladder (straddle 2/1/0), then right edge
|   otherwise                     -> BASE, straddle = 3 - width_idx
|   per row: [left edge] then `straddle` straddle cells then [right edge]; then col0 -= 160 (one
|   scanline up), sp -= 80 (one sprite row back), col1 = col0 + 8.  rows = rows_m1 + 1.
|
| Register roles (held across the row loop):
|   a0 = col0 cursor (dst)      a1 = sp cursor (src)      a2 = col1 cursor (dst + 8)
|   a3 = straddle count (edge paths only)
|   d0 = scratch / pixels       d1 = mask_col0 / scratch
|   d2 = mask_col1              d3 = dst per-row rewind (base + edge paths) / scratch at setup
|   d4 = row counter (dbra)     d5 = src per-row rewind (base + edge paths)
|   d6 = shl (rol.l / lsl.l count)   d7 = shr (lsr.w count)

    .text
    .globl  rm_blit_objshift2_asm

| ---- stack argument offsets (after the movem.l saves .LSAVED bytes) ----
    .equ    .LSAVED,   32                  | d2-d7/a2-a3 = 8 registers * 4 bytes
    .equ    .LA_DST,    4+.LSAVED            | uint8_t *dst
    .equ    .LA_DSTOFF, 8+.LSAVED            | uint32_t dst_off
    .equ    .LA_SRC,   12+.LSAVED            | const uint8_t *src
    .equ    .LA_SRCOFF,16+.LSAVED            | uint32_t src_off
    .equ    .LA_X_W,   22+.LSAVED            | uint16_t x        (value in the slot's low word)
    .equ    .LA_ROWS_W,26+.LSAVED            | uint16_t rows_m1  (low word)
    .equ    .LA_WIDX_W,30+.LSAVED            | int width_idx     (low word)

| Engine constants shared with the C reference — ONE source of truth (this is a .S, so cpp expands the
| #includes before the assembler runs). SCREEN_ROW_BYTES from screen.h (C-only parts guarded behind
| __ASSEMBLER__); OBJSH_CELL_BYTES / OBJSH2_* from blit_const.h (hoisted out of blit.c). See F11.
#include "screen.h"
#include "blit_const.h"

| ============================================================================================
| STRADDLE_CELL — one straddle group: mask both columns, OR the shifted pixels in, then apply the
| transparency (~mask) fill. Byte-for-byte the original's cell (@0x13efc). Reads mask from (a1)/2(a1)
| without advancing, then two pixel words from (a1)+ (a1 += 4); writes col0/col1 via (a0)+/(a2)+
| (each += 8). Clobbers d0/d1/d2.
| ============================================================================================
    .macro  STRADDLE_CELL
    moveq   #-1, %d1                     | mask seed 0xFFFFFFFF (high word 0xFFFF is load-bearing)
    move.w  (%a1), %d1                   | d1 = 0xFFFF:w0
    or.w    2(%a1), %d1                  | d1 = 0xFFFF:(w0|w1)
    not.w   %d1                          | d1 = 0xFFFF:~(w0|w1)
    rol.l   %d6, %d1                     | rotl32(mask, shl)  -> [col0_hi : col1_lo]
    move.w  %d1, %d2
    swap    %d2
    move.w  %d1, %d2                     | d2 = dup16(col1 mask = low word)
    move.l  %d1, %d0
    swap    %d0
    move.w  %d0, %d1                     | d1 = dup16(col0 mask = high word)
    and.l   %d1, (%a0)                   | col0 &= mask_col0
    and.l   %d2, (%a2)                   | col1 &= mask_col1
    moveq   #0, %d0
    move.w  (%a1)+, %d0
    lsl.l   %d6, %d0                     | pix0 = w0 << shl (32-bit straddle)
    or.w    %d0, (%a2)+                  | col1 |= low(pix0)
    swap    %d0
    or.w    %d0, (%a0)+                  | col0 |= high(pix0)
    moveq   #0, %d0
    move.w  (%a1)+, %d0
    lsl.l   %d6, %d0                     | pix1 = w1 << shl
    or.w    %d0, (%a2)+
    swap    %d0
    or.w    %d0, (%a0)+
    move.l  %d1, %d0
    not.l   %d0
    and.l   %d1, (%a0)
    or.l    %d0, (%a0)+                  | col0 = (col0 & mask_col0) | ~mask_col0 ; col0 += 4
    move.l  %d2, %d0
    not.l   %d0
    and.l   %d2, (%a2)
    or.l    %d0, (%a2)+                  | col1 = (col1 & mask_col1) | ~mask_col1 ; col1 += 4
    .endm

| LEFT_EDGE_CELL — the single on-screen column is col1; col0 only steps. Cold on the gate frame, so
| transcribed straight from objsh2_left_edge_cell() for correctness (not micro-tuned). a1 += 4,
| col1 (a2) += 8, col0 (a0) += 8. Clobbers d0/d1/d2.
    .macro  LEFT_EDGE_CELL
    move.l  (%a1), %d1                   | both = w0:w1
    addq.l  #2, %a1                      | sp += 2
    move.l  %d1, %d0
    swap    %d0
    or.w    %d1, %d0                     | d0 low = w0 | w1 (lo)
    andi.l  #0xffff, %d0
    lsl.l   %d6, %d0                     | lo << shl
    not.w   %d0                          | mask = ~(lo << shl)   (low word)
    move.w  %d0, %d2
    swap    %d2
    move.w  %d0, %d2                     | d2 = dup16(mask) = mask_col1
    and.l   %d2, (%a2)                   | col1 &= mask_col1
    move.l  %d1, %d0
    swap    %d0
    andi.l  #0xffff, %d0                 | d0 = w0 (zero-extended)
    lsl.l   %d6, %d0                     | w0 << shl
    or.w    %d0, (%a2)+                  | col1 |= low(w0 << shl) ; col1 += 2
    moveq   #0, %d0
    move.w  (%a1)+, %d0                  | w1 ; sp += 2
    lsl.l   %d6, %d0                     | w1 << shl
    or.w    %d0, (%a2)+                  | col1 |= low(w1 << shl) ; col1 += 2
    move.l  %d2, %d0
    not.l   %d0
    and.l   %d2, (%a2)
    or.l    %d0, (%a2)+                  | col1 = (col1 & mask)|~mask ; col1 += 4
    lea     OBJSH_CELL_BYTES(%a0), %a0   | col0 += 8
    .endm

| RIGHT_EDGE_CELL — the single on-screen column is col0; col1 only steps. Mirror of LEFT_EDGE_CELL
| with the right shift (lsr by shr = fine_x). a1 += 4, col0 (a0) += 8, col1 (a2) += 8. Clobbers
| d0/d1/d2.
    .macro  RIGHT_EDGE_CELL
    move.l  (%a1), %d1                   | both = w0:w1
    addq.l  #2, %a1                      | sp += 2
    move.l  %d1, %d0
    swap    %d0
    or.w    %d1, %d0                     | d0 low = lo = w0 | w1
    lsr.w   %d7, %d0                     | lo >> shr
    not.w   %d0                          | mask (low word)
    move.w  %d0, %d2
    swap    %d2
    move.w  %d0, %d2                     | d2 = dup16(mask) = mask_col0
    and.l   %d2, (%a0)                   | col0 &= mask_col0
    move.l  %d1, %d0
    swap    %d0                          | d0 low = w0
    lsr.w   %d7, %d0                     | w0 >> shr
    or.w    %d0, (%a0)+                  | col0 |= (w0 >> shr) ; col0 += 2
    move.w  (%a1)+, %d0                  | w1 ; sp += 2
    lsr.w   %d7, %d0                     | w1 >> shr
    or.w    %d0, (%a0)+                  | col0 |= (w1 >> shr) ; col0 += 2
    move.l  %d2, %d0
    not.l   %d0
    and.l   %d2, (%a0)
    or.l    %d0, (%a0)+                  | col0 = (col0 & mask)|~mask ; col0 += 4
    lea     OBJSH_CELL_BYTES(%a2), %a2   | col1 += 8
    .endm

| COMPUTE_REWIND — in: d3 = total cells this row. out: d3 = dst rewind (8*cells + 160),
| d5 = src rewind (4*cells + 80). The advance/rewind terms cancel to a constant net step
| (-SCREEN_ROW_BYTES for both columns, -OBJSH2_SRC_ROW_BYTES for the source), same fold the C proves.
    .macro  COMPUTE_REWIND
    move.w  %d3, %d5
    lsl.w   #2, %d5
    addi.w  #OBJSH2_SRC_ROW_BYTES, %d5   | src rewind = 4*cells + 80
    lsl.w   #3, %d3
    addi.w  #SCREEN_ROW_BYTES, %d3       | dst rewind = 8*cells + 160
    .endm

| ============================================================================================
rm_blit_objshift2_asm:
    movem.l %d2-%d7/%a2-%a3, -(%sp)      | GCC-style callee-save prologue

    movea.l .LA_DST(%sp), %a0
    adda.l  .LA_DSTOFF(%sp), %a0           | a0 = dst + dst_off
    movea.l .LA_SRC(%sp), %a1
    adda.l  .LA_SRCOFF(%sp), %a1           | a1 = sp = src + src_off

    move.w  .LA_X_W(%sp), %d0              | x
    moveq   #0xf, %d7
    and.w   %d0, %d7                     | d7 = shr = fine_x = x & 0xf
    moveq   #0x10, %d6
    sub.w   %d7, %d6                     | d6 = shl = 16 - fine_x

    move.w  .LA_WIDX_W(%sp), %d1           | d1 = width_idx (left ladder start + base/right test)
    move.w  .LA_ROWS_W(%sp), %d4           | d4 = rows_m1 (dbra counts rows_m1 + 1 times)
    bmi     .Losh2_done                    | rows_m1 bit15 set -> C draws (int16)rows_m1+1 <= 0 rows;
                                           | skip (a 16-bit dbra would otherwise loop up to 65536 times)

    asr.w   #1, %d0
    andi.w  #0xfff8, %d0                 | d0 = col (signed); N flag = (col < 0)
    adda.w  %d0, %a0                     | a0 = col0 = dst + dst_off + sx16(col)  (adda.w keeps CC)
    bmi     .Losh2_left                   | col < 0 -> LEFT clip ladder

    | col >= 0: base vs right. base_ceiling = 0x88 + 8*width_idx.
    move.w  %d1, %d2
    lsl.w   #3, %d2
    addi.w  #OBJSH2_RIGHT_BOUND, %d2     | d2 = base_ceiling
    move.w  %d0, %d3
    sub.w   %d2, %d3                     | col - base_ceiling ; N flag
    bpl     .Losh2_right                  | (col - base_ceiling) >= 0 -> RIGHT clip ladder

    | BASE: straddle = 3 - width_idx (1..3). Dispatch to the matching unrolled loop.
    moveq   #3, %d0
    sub.w   %d1, %d0
    cmpi.w  #3, %d0
    beq     .Losh2_base3
    cmpi.w  #2, %d0
    beq     .Losh2_base2
    | fall through to base1 (width_idx == 2)

| ---- BASE, straddle 1 (width_idx 2): 1 straddle cell/row ----
.Losh2_base1:
    movea.l %a0, %a2
    addq.l  #OBJSH_CELL_BYTES, %a2       | col1 = col0 + 8
    | hold the per-row rewinds in d3/d5 (free inside STRADDLE_CELL, which clobbers only d0/d1/d2) so
    | the row bookkeeping is suba.w %dN,%aN (8 cyc) not suba.w #imm,%aN (12 cyc) — F3.
    move.w  #(OBJSH_CELL_BYTES*1+SCREEN_ROW_BYTES), %d3       | dst per-row rewind
    move.w  #(OBJSH_CELL_BYTES/2*1+OBJSH2_SRC_ROW_BYTES), %d5 | src per-row rewind
.Losh2_base1_row:
    STRADDLE_CELL
    suba.w  %d3, %a0
    suba.w  %d3, %a2
    suba.w  %d5, %a1
    dbra    %d4, .Losh2_base1_row
    bra     .Losh2_done

| ---- BASE, straddle 2 (width_idx 1): 2 straddle cells/row ----
.Losh2_base2:
    movea.l %a0, %a2
    addq.l  #OBJSH_CELL_BYTES, %a2
    move.w  #(OBJSH_CELL_BYTES*2+SCREEN_ROW_BYTES), %d3       | dst per-row rewind (F3)
    move.w  #(OBJSH_CELL_BYTES/2*2+OBJSH2_SRC_ROW_BYTES), %d5 | src per-row rewind
.Losh2_base2_row:
    STRADDLE_CELL
    STRADDLE_CELL
    suba.w  %d3, %a0
    suba.w  %d3, %a2
    suba.w  %d5, %a1
    dbra    %d4, .Losh2_base2_row
    bra     .Losh2_done

| ---- BASE, straddle 3 (width_idx 0): 3 straddle cells/row — THE hot path ----
.Losh2_base3:
    movea.l %a0, %a2
    addq.l  #OBJSH_CELL_BYTES, %a2
    move.w  #(OBJSH_CELL_BYTES*3+SCREEN_ROW_BYTES), %d3       | dst per-row rewind (F3)
    move.w  #(OBJSH_CELL_BYTES/2*3+OBJSH2_SRC_ROW_BYTES), %d5 | src per-row rewind
.Losh2_base3_row:
    STRADDLE_CELL
    STRADDLE_CELL
    STRADDLE_CELL
    suba.w  %d3, %a0
    suba.w  %d3, %a2
    suba.w  %d5, %a1
    dbra    %d4, .Losh2_base3_row
    bra     .Losh2_done

| ---- LEFT clip ladder (col < 0): walk rungs, pre-advancing sp/col0, until col+8*k >= 0 ----
.Losh2_left:
    | d0 = col (< 0), d1 = width_idx. rung starts at width_idx (kept in d3).
    move.w  %d1, %d3                     | rung = width_idx
.Losh2_left_ladder:
    addi.w  #OBJSH2_LADDER_STEP, %d0     | col += 8
    bpl.s   .Losh2_left_hit               | reached the screen: straddle = 2 - rung
    cmpi.w  #(OBJSH2_BASE_STRADDLE-1), %d3
    bge     .Losh2_done                   | rung == 2 and still off-screen -> draw nothing
    addq.l  #(OBJSH_CELL_BYTES/2), %a1   | sp += 4 (pre-advance)
    lea     OBJSH_CELL_BYTES(%a0), %a0   | col0 += 8
    addq.w  #1, %d3                       | rung++
    bra.s   .Losh2_left_ladder
.Losh2_left_hit:
    moveq   #(OBJSH2_BASE_STRADDLE-1), %d2
    sub.w   %d3, %d2                      | straddle = 2 - rung (0..2)
    movea.w %d2, %a3                      | a3 = straddle
    move.w  %d2, %d3
    addq.w  #1, %d3                       | total cells = straddle + 1 (left edge)
    COMPUTE_REWIND
    movea.l %a0, %a2
    addq.l  #OBJSH_CELL_BYTES, %a2        | col1 = col0 + 8
.Losh2_left_row:
    LEFT_EDGE_CELL
    move.w  %a3, %d0                      | straddle
    cmpi.w  #2, %d0
    beq.s   .Losh2_left_c2
    cmpi.w  #1, %d0
    beq.s   .Losh2_left_c1
    bra     .Losh2_left_c0
.Losh2_left_c2:
    STRADDLE_CELL
.Losh2_left_c1:
    STRADDLE_CELL
.Losh2_left_c0:
    suba.w  %d3, %a0
    suba.w  %d3, %a2
    suba.w  %d5, %a1
    dbra    %d4, .Losh2_left_row
    bra     .Losh2_done

| ---- RIGHT clip ladder (col - base_ceiling >= 0): straddle 2/1/0 off the fixed 0x88 bound ----
.Losh2_right:
    move.w  %d0, %d3                      | col
    subi.w  #OBJSH2_RIGHT_BOUND, %d3      | c = col - 0x88
    subi.w  #OBJSH2_LADDER_STEP, %d3
    bmi.s   .Losh2_right_s2               | c < 0 -> straddle 2
    subi.w  #OBJSH2_LADDER_STEP, %d3
    bmi.s   .Losh2_right_s1
    subi.w  #OBJSH2_LADDER_STEP, %d3
    bmi.s   .Losh2_right_s0
    bra     .Losh2_done                    | off the right edge -> draw nothing
.Losh2_right_s2:
    moveq   #2, %d0
    bra.s   .Losh2_right_setup
.Losh2_right_s1:
    moveq   #1, %d0
    bra.s   .Losh2_right_setup
.Losh2_right_s0:
    moveq   #0, %d0
.Losh2_right_setup:
    movea.w %d0, %a3                      | a3 = straddle
    move.w  %d0, %d3
    addq.w  #1, %d3                       | total cells = straddle + 1 (right edge)
    COMPUTE_REWIND
    movea.l %a0, %a2
    addq.l  #OBJSH_CELL_BYTES, %a2
.Losh2_right_row:
    move.w  %a3, %d0
    cmpi.w  #2, %d0
    beq.s   .Losh2_right_c2
    cmpi.w  #1, %d0
    beq.s   .Losh2_right_c1
    bra     .Losh2_right_c0
.Losh2_right_c2:
    STRADDLE_CELL
.Losh2_right_c1:
    STRADDLE_CELL
.Losh2_right_c0:
    RIGHT_EDGE_CELL
    suba.w  %d3, %a0
    suba.w  %d3, %a2
    suba.w  %d5, %a1
    dbra    %d4, .Losh2_right_row
    | fall through to done

.Losh2_done:
    movem.l (%sp)+, %d2-%d7/%a2-%a3
    rts
