| road_band.S — hand-written m68k core for render_road's band D (near + far copy), the pseudo-3D road
| rasterizer's last band group. PERF30 road-asm slice 1. The byte-exact REFERENCE is rr_band_D_c() in
| src/road.c (a faithful port of recreate's verified band, itself pinned against the Musashi oracle);
| this is a drop-in replacement with the SAME C signature. It is ALWAYS assembled (as objshift2.S is);
| road.c's RR_BAND_D_FN dispatch (keyed on RM_ASM_RR_BAND_D, from the umbrella -DRM_ASM_ROAD — see
| include/road_const.h) chooses this core or the C reference, so undefining the flag A/Bs the band on
| every build. Never diverge from the C by one byte — test/test_asm_road.py runs real staged road frames
| through both the C and this asm under Musashi and byte-compares the whole framebuffer.
|
| The template is the ORIGINAL game's own render_road band D @0x987c (near) / @0x9950 (far), transcribed
| register-for-register in recreate/src/machine/road.c (rr_band_D, the byte-exact machine model). Its
| register discipline, ported here:
|   * a2 = row-start dst, a0 = working dst, a1 = working src, a3 = tex (read-only within the band),
|     a4 = param cursor, a5 = width/ctrl cursor, a6 = edge cursor — all walked with (aN)+ post-increment.
|   * d5/d6 = the (lo,hi) fill plane pattern; d3 = the edge mask; d2 = the 160-byte scanline stride;
|     d7 = the column-align mask; d4 = the row counter (16-bit dbra); d0/d1 = ctrl / scratch.
|   * the shoulder / full-row fills reset the cursor to the row start (a0 = a2) and walk forward.
|
| The ONE structural change from the original is the ABI: the original is a stretch of one big register-
| resident render_road; this is the remaster's per-band C function, so it reads its cursors from the
| rr_regs struct (native RoadInput pointers + an Offset dst rebased onto fb->px), advances them in
| registers, and writes the four that move (param/width/edge/dst) back at return — the A4 localization
| contract. It reads its 3 args off the stack (m68k SysV) behind a GCC-style movem save/restore.
|
| C signature (src/road.c): void rr_band_D_c(rr_regs *r, uint32_t rows_m1, int second);
| rows_m1 draws (int16)rows_m1+1 times via the 16-bit dbra (callers pass RR_ROWS_D_NEAR / _FAR, so no
| bit-15 guard is needed — unlike the objshift cores, band D is never called with a zero-row count).
| `second` selects the far copy's wider blit tail.
|
| CONTRACT (caller invariant): band D always runs after the first group step, so r->d7 == RR_D7_WORD_MASK
| (0xfff8) at entry — never 0 (that is band A's scratch value). This asm READS r->d7 into d7 and masks the
| column with it; the frozen C reference hardcodes RR_D7_WORD_MASK at the same site (they agree because the
| invariant holds). If a future caller ran band D with d7 == 0 the two would diverge — pin it here.
|
| Algorithm (the SPEC is the C rr_band_D_c in road.c; the op sequence mirrors the machine model):
|   per scanline: ctrl = be32(width)+... ; fine_x column, edge mask, fill pattern; a src-strip dispatch
|   on the flag bits (no-split edge-relative / WIDE-const / plane-hi); then col = (half_width>>1)&d7 and
|   near vs far tail: [left shoulder fill | antialiased edge cell | copied texture]. col off the left
|   edge draws nothing (near) or two texture longs (far); col past the row fills the whole scanline.

    .text

#include "road_const.h"

    .globl  rr_band_D_asm

| ---- stack argument offsets (after the movem.l saves .LSAVED bytes) ----
    .equ    .LSAVED,     44                | d2-d7/a2-a6 = 11 registers * 4 bytes
    .equ    .LA_R,        4+.LSAVED         | rr_regs *r
    .equ    .LA_ROWS,     8+.LSAVED         | uint32_t rows_m1 (dbra counts rows_m1+1 times)
    .equ    .LA_SECOND,  12+.LSAVED         | int second (near = 0 / far tail = 1)

| ============================================================================================
rr_band_D_asm:
    movem.l %d2-%d7/%a2-%a6, -(%sp)         | GCC-style callee-save prologue

    movea.l .LA_R(%sp), %a0                 | a0 = r (temp)
    movea.l RR_OFF_TEX(%a0), %a3            | a3 = tex (read-only within the band)
    movea.l RR_OFF_PARAM(%a0), %a4          | a4 = param cursor
    movea.l RR_OFF_WIDTH(%a0), %a5          | a5 = width/ctrl cursor
    movea.l RR_OFF_EDGE(%a0), %a6           | a6 = edge cursor
    movea.l RR_OFF_FB(%a0), %a2             | a2 = fb->px base ...
    adda.l  RR_OFF_DST(%a0), %a2            | ... + dst offset = row-start dst pointer
    move.w  RR_OFF_STRIDE(%a0), %d2         | d2 = stride (160)
    move.w  RR_OFF_D7(%a0), %d7             | d7 = column-align mask
    move.l  .LA_ROWS(%sp), %d4              | d4 = rows_m1 (16-bit dbra)

.Lrow:
    movea.l %a3, %a1                        | a1 = working src = tex
    movea.l %a2, %a0                        | a0 = working dst = row start
    move.l  (%a5)+, %d0                     | d0 = ctrl = be32(width); width += 4
    add.w   (%a4)+, %d0                     | d0.w = half_width = ctrl.w + be16(param); param += 2
    move.w  %d0, %d1
    andi.w  #0xf, %d1
    lsl.w   #4, %d1                         | d1.w = (half_width & 0xf) << 4  (fine-x sub-column)
    adda.w  %d1, %a1                        | a1 = tex + fine_x
    move.w  (%a4)+, %d1                     | d1 = edge_seed = be16(param); param += 2

    moveq   #-1, %d3                        | d3 = 0xffffffff (default edge mask = keep all)
    move.l  %d3, %d5
    clr.w   %d5                             | d5 = 0xffff0000 (default fill_lo)
    moveq   #0, %d6
    not.w   %d6                             | d6 = 0x0000ffff (default fill_hi)
    btst    #RR_FB_MASK_A2, %d0            | control bit: read edge mask (near group)
    beq     .Lno_mask
    moveq   #0, %d5                         | mask row: clear the left fill ...
    move.l  RR_MASK_OFF_LO(%a1), %d3        | ... and load the per-row edge mask
.Lno_mask:
    btst    #RR_FB_SPLIT_D, %d0            | control bit: edge split present
    beq     .Lnosplit
    btst    #RR_FB_SKIP_D, %d0             | control bit: edge-split fast-path gate
    beq     .Lsplit
    tst.l   %d0                             | SKIP_D set: (int32)ctrl >= 0 -> still a split strip
    bpl     .Lsplit
    | flagged blank scanline: advance edge + row, no draw
    addq.l  #2, %a6
    adda.w  %d2, %a2
    dbf     %d4, .Lrow
    bra     .Ldone

.Lsplit:
    addq.l  #2, %a6                         | split strip: edge cursor advances (word unused)
    btst    #RR_FB_WIDE, %d0               | control bit: wide/solid-centre branch
    beq     .Lplane_hi
    | ---- WIDE / solid-centre strip ----
    moveq   #0, %d5
    moveq   #0, %d6                         | wide fill: both planes 0 (const/notw select below)
    adda.w  #RR_SRC_3500, %a1
    btst    #RR_FB_SRC_400, %d0            | control bit: +0x400 src selector
    beq     .Lwide_notw
    adda.w  #RR_SRC_0400, %a1
    btst    #RR_FB_SRC_100, %d0            | control bit: +0x100 src/fill selector
    bne     .Lcol                           | SRC_400 & SRC_100: texture strip as-is
    | SRC_400 & !SRC_100: const strip 5B7A
    movea.l .LA_R(%sp), %a1
    movea.l RR_OFF_EDGE_CONST(%a1), %a1     | a1 = edge_const + RR_CONST_5B7A (0)
    bra     .Lcol
.Lwide_notw:
    not.w   %d5                             | d5 = 0x0000ffff (fill_lo)
    btst    #RR_FB_SRC_100, %d0            | control bit: +0x100 src/fill selector
    bne     .Lcol
    | !SRC_400 & !SRC_100: const strip 5B9A
    movea.l .LA_R(%sp), %a1
    movea.l RR_OFF_EDGE_CONST(%a1), %a1
    adda.w  #RR_CONST_5B9A, %a1             | a1 = edge_const + 0x20
    bra     .Lcol

.Lnosplit:
    | ---- no-split: edge-relative strip ----
    adda.w  %d1, %a1                        | a1 += edge_seed (d1)
    move.w  (%a6)+, %d1                     | d1 = be16(edge); edge += 2
    adda.w  %d1, %a1                        | a1 += sx16(edge word)
.Lplane_hi:
    btst    #RR_FB_PLANE_HI, %d0           | control bit: hi-plane swap + alt src
    beq     .Lcol
    adda.w  #RR_SRC_5800, %a1

.Lcol:
    asr.w   #1, %d0                         | d0.w = half_width >> 1
    and.w   %d7, %d0                        | d0.w = col = (half_width>>1) & d7
    tst.l   .LA_SECOND(%sp)
    bne     .Lfar

| ---- near copy tail (0x990a): [edge cell | forward left-shoulder fill] ----
    tst.w   %d0
    bpl     .Lnear_draw
    | col < 0: road entirely off the left edge, nothing drawn
    adda.w  %d2, %a2
    dbf     %d4, .Lrow
    bra     .Ldone
.Lnear_draw:
    adda.w  %d0, %a0                        | a0 = row start + col (place at the edge)
    move.w  %d0, %d1                        | d1 = col (saved for the shoulder count)
    sub.w   %d2, %d0                        | d0.w = col - stride
    bpl     .Lnear_fullrow                  | col >= stride: road fills the whole scanline
    move.l  (%a1)+, (%a0)+                  | edge cell: copy long ...
    and.w   %d3, -4(%a0)                    | ... mask its high word ...
    move.l  (%a1)+, (%a0)+                  | ... copy long
    lsr.w   #3, %d1                         | d1.w = col >> 3 (shoulder cells)
    subq.w  #1, %d1
    bmi     .Lnear_next                     | no shoulder cells
    movea.l %a2, %a0                        | reset a0 to the row start
.Lnear_sh:
    move.l  %d5, (%a0)+                     | forward shoulder fill pair (lo, hi)
    move.l  %d6, (%a0)+
    dbf     %d1, .Lnear_sh
.Lnear_next:
    adda.w  %d2, %a2
    dbf     %d4, .Lrow
    bra     .Ldone
.Lnear_fullrow:
    movea.l %a2, %a0                        | full 160-byte scanline fill at the row start
    moveq   #RR_ROW_FILL_DBF, %d1        | full 160-byte row = RR_ROW_LONG_PAIRS pairs (4 longs/iter)
.Lnear_frow:
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    dbf     %d1, .Lnear_frow
    adda.w  %d2, %a2
    dbf     %d4, .Lrow
    bra     .Ldone

| ---- far copy tail (0x99dc): widens the texture run; also handles the road off the left edge ----
.Lfar:
    tst.w   %d0
    bpl     .Lfar_draw
    | col < 0: draw two texture longs at the row start if the road is one cell off the left edge
    addq.w  #8, %d0                         | col + 8
    bmi     .Lfar_next                      | still off-screen: nothing
    addq.l  #8, %a1                         | skip the off-screen edge cell in the source
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
.Lfar_next:
    adda.w  %d2, %a2
    dbf     %d4, .Lrow
    bra     .Ldone
.Lfar_draw:
    adda.w  %d0, %a0                        | a0 = row start + col
    move.w  %d0, %d1                        | d1 = col (shoulder count)
    sub.w   %d2, %d0                        | d0.w = col - stride
    bpl     .Lfar_fullrow                   | col >= stride: fills the whole scanline
    addq.w  #8, %d0                         | col - stride + 8
    bpl     .Lfar_narrow
    | wide: 4 texture longs, the first hi-word masked
    move.l  (%a1)+, (%a0)+
    and.w   %d3, -4(%a0)
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    bra     .Lfar_sh_test
.Lfar_narrow:
    | narrow: 2 texture longs, the first hi-word masked
    move.l  (%a1)+, (%a0)+
    and.w   %d3, -4(%a0)
    move.l  (%a1)+, (%a0)+
.Lfar_sh_test:
    lsr.w   #3, %d1                         | d1.w = col >> 3
    subq.w  #1, %d1
    bmi     .Lfar_next2
    movea.l %a2, %a0                        | reset a0 to the row start
.Lfar_sh:
    move.l  %d5, (%a0)+                     | forward shoulder fill pair
    move.l  %d6, (%a0)+
    dbf     %d1, .Lfar_sh
.Lfar_next2:
    adda.w  %d2, %a2
    dbf     %d4, .Lrow
    bra     .Ldone
.Lfar_fullrow:
    movea.l %a2, %a0
    moveq   #RR_ROW_FILL_DBF, %d1        | full 160-byte row = RR_ROW_LONG_PAIRS pairs (4 longs/iter)
.Lfar_frow:
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    dbf     %d1, .Lfar_frow
    adda.w  %d2, %a2
    dbf     %d4, .Lrow
    | fall through to .Ldone (the far copy's last dbf falls through, as in the original)

.Ldone:
    | write back the four cursors that advanced: param (a4), width (a5), edge (a6), dst (a2 rebased).
    movea.l .LA_R(%sp), %a0
    move.l  %a4, RR_OFF_PARAM(%a0)
    move.l  %a5, RR_OFF_WIDTH(%a0)
    move.l  %a6, RR_OFF_EDGE(%a0)
    move.l  %a2, %d0                        | d0 = final row-start pointer ...
    sub.l   RR_OFF_FB(%a0), %d0             | ... - fb->px base = dst offset
    move.l  %d0, RR_OFF_DST(%a0)
    movem.l (%sp)+, %d2-%d7/%a2-%a6
    rts
