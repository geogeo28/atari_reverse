| road_band.S — hand-written m68k cores for render_road's bands D (slice 1) and B (slice 2), two of the
| pseudo-3D road rasterizer's seven per-scanline band writers. PERF30 road-asm slices 1-2. Each core's
| byte-exact REFERENCE is its rr_band_?_c() in src/road.c (faithful ports of recreate's verified bands,
| pinned against the Musashi oracle); each is a drop-in with the SAME C signature. Both are ALWAYS
| assembled (as objshift2.S is); road.c's RR_BAND_?_FN dispatch (keyed on RM_ASM_RR_BAND_? from the
| umbrella -DRM_ASM_ROAD — see include/road_const.h) chooses each core or its C reference, so undefining a
| per-core flag A/Bs that band on every build. Never diverge from the C by one byte — test/test_asm_road.py
| runs real staged road frames through both the C and each asm under Musashi and byte-compares the frame.
|
| The template is the ORIGINAL game's own render_road, transcribed register-for-register in
| recreate/src/machine/road.c (the byte-exact machine model): band D @0x987c/@0x9950, band B @0x93c2/@0x948c.
| Shared register discipline, ported here:
|   * a2 = row-start dst, a0 = working dst, a1 = working src, a3 = tex (read-only within the band),
|     a4 = param cursor, a5 = width/ctrl cursor, a6 = edge cursor — all walked with (aN)+ post-increment.
|   * d5/d6 = the (lo,hi) fill plane pattern; d3 = the edge mask; d2 = the 160-byte scanline stride;
|     d7 = the column-align mask; d4 = the row counter (16-bit dbra); d0/d1 = ctrl / scratch.
|   * the shoulder / full-row fills reset the cursor to the row start (a0 = a2) and walk forward.
|
| ABI CONTRACT (shared by both cores; extend, don't restate per band). The original is one big register-
| resident render_road; these are the remaster's per-band C functions, so each reads its cursors from the
| rr_regs struct (native RoadInput pointers + an Offset dst rebased onto fb->px), advances them in
| registers, and writes the four that MOVE (param/width/edge/dst) back at return — the A4 localization
| contract (RR_BAND_PROLOGUE / RR_BAND_EPILOGUE below implement it once for both). Each reads its 3 stack
| args (m68k SysV) behind a GCC-style movem save/restore. C signatures (src/road.c):
|     void rr_band_D_c(rr_regs *r, uint32_t rows_m1, int second);
|     void rr_band_B_c(rr_regs *r, uint32_t rows_m1, int second);
| rows_m1 draws (int16)rows_m1+1 times via the 16-bit dbra (callers pass RR_ROWS_?_NEAR / _FAR, always > 0,
| so no bit-15 guard is needed). `second` selects the far copy's wider blit tail.
|   * d7 invariant: both cores READ r->d7 into d7 and mask the column with it. Bands B/C/D always run after
|     the first group step, so r->d7 == RR_D7_WORD_MASK (0xfff8) — never 0 (band A's scratch value). Band
|     B's C reference ALSO reads r->d7 (its col_mask local), so C and asm read the same field and agree
|     unconditionally; band D's C HARDCODES RR_D7_WORD_MASK, so there they agree only because the invariant
|     holds. Either way, running a band with d7 == 0 would diverge from its C — pinned by the invariant.
|
| Algorithm (the SPEC is each rr_band_?_c in road.c; the op sequence mirrors the machine model). Per
| scanline both do: ctrl = be32(width)+be16(param); fine_x column; edge mask; fill pattern; a src-strip
| dispatch on the flag bits; then col = (half_width>>1)&d7 and a near vs far tail. They differ in the flag
| bits (D: MASK_A2/SPLIT_D/SKIP_D + MASK_OFF_LO + SRC_3500; B: MASK_A/SPLIT_B/SKIP_ABC + MASK_OFF_HI +
| SRC_4700) and in the tails (B's near +8s both cursors before the shift; B's far has a dbf-counted fill on
| the col<0 side and a 4/2-long blit on the col>=0 side; D paints [shoulder | edge cell | texture]).

    .text

#include "road_const.h"

    .globl  rr_band_D_asm
    .globl  rr_band_B_asm

| ---- stack argument offsets (after the movem.l saves .LSAVED bytes), shared by both cores ----
    .equ    .LSAVED,     44                | d2-d7/a2-a6 = 11 registers * 4 bytes
    .equ    .LA_R,        4+.LSAVED         | rr_regs *r
    .equ    .LA_ROWS,     8+.LSAVED         | uint32_t rows_m1 (dbra counts rows_m1+1 times)
    .equ    .LA_SECOND,  12+.LSAVED         | int second (near = 0 / far tail = 1)

| RR_BAND_PROLOGUE / RR_BAND_EPILOGUE — the shared A4 localization ABI (identical for both bands): load the
| cursors from rr_regs into registers, and write the four that advance back at return.
    .macro  RR_BAND_PROLOGUE
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
    .endm

    .macro  RR_BAND_EPILOGUE
    movea.l .LA_R(%sp), %a0
    move.l  %a4, RR_OFF_PARAM(%a0)
    move.l  %a5, RR_OFF_WIDTH(%a0)
    move.l  %a6, RR_OFF_EDGE(%a0)
    move.l  %a2, %d0                        | d0 = final row-start pointer ...
    sub.l   RR_OFF_FB(%a0), %d0             | ... - fb->px base = dst offset
    move.l  %d0, RR_OFF_DST(%a0)
    movem.l (%sp)+, %d2-%d7/%a2-%a6
    rts
    .endm

| ============================================================================================
| Band D (@0x987c near / @0x9950 far): per scanline [left shoulder fill | edge cell | copied texture].
| ============================================================================================
rr_band_D_asm:
    RR_BAND_PROLOGUE

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
    RR_BAND_EPILOGUE

| ============================================================================================
| Band B (@0x93c2 near / @0x948c far): near copy (SPLIT_B blit) then far copy (a distinct, wider tail).
| Default fill lo=0xffff0000 / hi=0x0000ffff; the edge mask (loaded only on MASK_A) masks the split long's
| HIGH WORD. Near tail +8s both cursors before the shift; far tail has a dbf-counted fill (col<0) or a
| 4/2-long masked blit + shoulder fill (col>=0), plus a full-fill path.
| ============================================================================================
rr_band_B_asm:
    RR_BAND_PROLOGUE

.LBrow:
    movea.l %a3, %a1                        | a1 = working src = tex
    movea.l %a2, %a0                        | a0 = working dst = row start
    move.l  (%a5)+, %d0                     | d0 = ctrl = be32(width); width += 4
    add.w   (%a4)+, %d0                     | d0.w = half_width; param += 2
    move.w  %d0, %d1
    andi.w  #0xf, %d1
    lsl.w   #4, %d1                         | d1.w = (half_width & 0xf) << 4 (fine-x)
    adda.w  %d1, %a1                        | a1 = tex + fine_x
    move.w  (%a4)+, %d1                     | d1 = edge_seed = be16(param); param += 2

    moveq   #-1, %d3                        | d3 = 0xffffffff (default edge mask)
    move.l  %d3, %d5
    clr.w   %d5                             | d5 = 0xffff0000 (default fill_lo)
    moveq   #0, %d6
    not.w   %d6                             | d6 = 0x0000ffff (default fill_hi)
    btst    #RR_FB_MASK_A, %d0             | control bit: read edge mask, clear left fill
    beq     .LBno_mask
    moveq   #0, %d5                         | mask row: fill_lo = 0 ...
    move.l  RR_MASK_OFF_HI(%a1), %d3        | ... edge_mask = be32(src + 0x2808)
.LBno_mask:
    btst    #RR_FB_SPLIT_B, %d0            | control bit: edge split present
    beq     .LBnosplit
    btst    #RR_FB_SKIP_ABC, %d0          | control bit: edge-split fast-path gate
    beq     .LBsplit
    tst.l   %d0                             | SKIP_ABC set: (int32)ctrl >= 0 -> still a split strip
    bpl     .LBsplit
    | flagged blank scanline: advance edge + row, no draw
    addq.l  #2, %a6
    adda.w  %d2, %a2
    dbf     %d4, .LBrow
    bra     .LBdone

.LBsplit:
    addq.l  #2, %a6                         | split strip: edge cursor advances (word unused)
    btst    #RR_FB_WIDE, %d0               | control bit: wide/solid-centre branch
    beq     .LBplane_hi
    | ---- WIDE / solid-centre strip (band B: only fill_hi cleared; SRC base 0x4700) ----
    moveq   #0, %d6                         | fill_hi = 0 (fill_lo keeps 0xffff0000 unless notw'd below)
    adda.w  #RR_SRC_4700, %a1
    btst    #RR_FB_SRC_400, %d0            | control bit: +0x400 src selector
    beq     .LBwide_notw
    adda.w  #RR_SRC_0400, %a1
    btst    #RR_FB_SRC_100, %d0            | control bit: +0x100 src/fill selector
    bne     .LBtail                         | SRC_400 & SRC_100: texture strip as-is
    | SRC_400 & !SRC_100: const strip 5B7A
    movea.l .LA_R(%sp), %a1
    movea.l RR_OFF_EDGE_CONST(%a1), %a1     | a1 = edge_const + RR_CONST_5B7A (0)
    bra     .LBtail
.LBwide_notw:
    not.w   %d5                             | fill_lo = notw(d5): 0xffff0000 -> 0xffffffff, or (if MASK_A
    |                                       |   already cleared d5) 0 -> 0x0000ffff
    btst    #RR_FB_SRC_100, %d0
    bne     .LBtail
    | !SRC_400 & !SRC_100: const strip 5B9A
    movea.l .LA_R(%sp), %a1
    movea.l RR_OFF_EDGE_CONST(%a1), %a1
    adda.w  #RR_CONST_5B9A, %a1             | a1 = edge_const + 0x20
    bra     .LBtail

.LBnosplit:
    | ---- no-split: edge-relative strip ----
    adda.w  %d1, %a1                        | a1 += edge_seed (d1)
    move.w  (%a6)+, %d1                     | d1 = be16(edge); edge += 2
    adda.w  %d1, %a1                        | a1 += sx16(edge word)
.LBplane_hi:
    btst    #RR_FB_PLANE_HI, %d0           | control bit: hi-plane alt src
    beq     .LBtail
    adda.w  #RR_SRC_5800, %a1

.LBtail:
    tst.l   .LA_SECOND(%sp)
    bne     .LBfar

| ---- near copy tail (0x944a): +8 both cursors, single masked column, forward shoulder fill ----
    addq.l  #8, %a0                         | a0 += 8 (near copy places one cell in from the row start)
    addq.l  #8, %a1                         | a1 += 8
    asr.w   #1, %d0                         | d0.w = half_width >> 1
    and.w   %d7, %d0                        | d0.w = col = (half_width>>1) & d7
    adda.w  %d0, %a0                        | a0 += col
    addq.w  #8, %d0                         | d0.w = e = col + 8
    bpl     .LBnear_e                       | e >= 0
    | e < 0: road off-screen -> fill the whole scanline
    movea.l %a2, %a0
    moveq   #RR_ROW_FILL_DBF, %d1
.LBnear_frow:
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    dbf     %d1, .LBnear_frow
    adda.w  %d2, %a2
    dbf     %d4, .LBrow
    bra     .LBdone
.LBnear_e:
    sub.w   %d2, %d0                        | d0.w = e - stride = rem
    bpl     .LBnear_next                    | rem >= 0: nothing more to draw
    move.l  (%a1)+, (%a0)+                  | edge cell: copy long ...
    and.w   %d3, -4(%a0)                    | ... mask its high word ...
    move.l  (%a1)+, (%a0)+                  | ... copy long
    addq.w  #8, %d0
    bpl     .LBnear_next
.LBnear_fill:
    move.l  %d5, (%a0)+                     | forward shoulder fill pair
    move.l  %d6, (%a0)+
    addq.w  #8, %d0
    bmi     .LBnear_fill
.LBnear_next:
    adda.w  %d2, %a2
    dbf     %d4, .LBrow
    bra     .LBdone

| ---- far copy tail (0x9514): col<0 -> dbf-counted fill; col>=0 -> 4/2-long masked blit + shoulder ----
.LBfar:
    asr.w   #1, %d0
    and.w   %d7, %d0                        | d0.w = col = (half_width>>1) & d7
    bpl     .LBfar_pos                      | col >= 0
    | col < 0: road off-screen, a pair-store fill of the whole 160-byte row, preceded by an edge cell if col+8>=0
    moveq   #RR_ROW_FILL_PAIR_DBF, %d1      | fill the full row (RR_ROW_LONG_PAIRS pairs), no edge cell
    addq.w  #8, %d0                         | col + 8
    bmi     .LBfar_cfill                    | col+8 < 0: no edge cell
    moveq   #RR_ROW_FILL_EDGE_DBF, %d1      | one edge cell then RR_ROW_LONG_PAIRS-1 fill pairs
    addq.l  #8, %a1                         | src += 8 (skip the off-screen edge cell in the source)
    move.l  (%a1)+, (%a0)+
    and.w   %d3, -4(%a0)
    move.l  (%a1)+, (%a0)+
.LBfar_cfill:
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    dbf     %d1, .LBfar_cfill
    adda.w  %d2, %a2
    dbf     %d4, .LBrow
    bra     .LBdone
.LBfar_pos:
    adda.w  %d0, %a0                        | a0 += col
    sub.w   %d2, %d0                        | d0.w = col - stride = rem
    bpl     .LBfar_next                     | rem >= 0: road spans the row, nothing to blit
    addq.w  #8, %d0                         | col - stride + 8
    bpl     .LBfar_2long                    | >= 0: narrow (2 longs)
    | wide: 4 texture longs, the THIRD hi-word masked
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    and.w   %d3, -4(%a0)
    move.l  (%a1)+, (%a0)+
    addq.w  #8, %d0
    bpl     .LBfar_next
    bra     .LBfar_fill
.LBfar_2long:
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    addq.w  #8, %d0
    bpl     .LBfar_next
.LBfar_fill:
    move.l  %d5, (%a0)+                     | forward shoulder fill pair
    move.l  %d6, (%a0)+
    addq.w  #8, %d0
    bmi     .LBfar_fill
.LBfar_next:
    adda.w  %d2, %a2
    dbf     %d4, .LBrow
    | fall through to .LBdone

.LBdone:
    RR_BAND_EPILOGUE
