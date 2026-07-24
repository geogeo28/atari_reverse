| road_band.S — hand-written m68k cores for ALL of render_road's per-scanline band writers: band D (slice
| 1), band B (slice 2), then bands C-near/C-far and band A (slice 3). With all seven ported, rm_render_road
| is pure C glue calling these + the group steps. PERF30 road-asm slices 1-3. Each core's byte-exact
| REFERENCE is its rr_band_?_c() in src/road.c (faithful ports of recreate's verified bands, pinned against
| the Musashi oracle); each is a drop-in with the SAME C signature. All are ALWAYS assembled (as objshift2.S
| is); road.c's RR_BAND_?_FN dispatch (keyed on RM_ASM_RR_BAND_? from the umbrella -DRM_ASM_ROAD — see
| include/road_const.h) chooses each core or its C reference, so undefining a per-core flag A/Bs that band on
| every build. Never diverge from the C by one byte — test/test_asm_road.py runs real staged road frames
| through both the C and each asm under Musashi and byte-compares the frame.
|
| The template is the ORIGINAL game's own render_road, transcribed register-for-register in
| recreate/src/machine/road.c (the byte-exact machine model): A @0x9172, B @0x93c2/@0x948c, C @0x9582/@0x96b8,
| D @0x987c/@0x9950. Shared register discipline, ported here:
|   * a2 = row-start dst, a0 = working dst, a1 = working src, a3 = tex (read-only within the band),
|     a4 = param cursor, a5 = width/ctrl cursor, a6 = edge cursor — all walked with (aN)+ post-increment.
|   * d5/d6 = the (lo,hi) fill plane pattern; d3 = the edge mask; d2 = the 160-byte scanline stride;
|     d7 = the column-align mask (band A: scratch); d4 = the row counter (16-bit dbra); d0/d1 = ctrl / scratch.
|   * the shoulder / full-row fills reset the cursor to the row start (a0 = a2) and walk forward; band C-far
|     and band A also fill the shoulder BACKWARD (fill_pair_rev, -(a0)); the per-row decode is RR_ROW_HEAD.
|
| ABI CONTRACT (shared; extend, don't restate per band). The original is one big register-resident
| render_road; these are the remaster's per-band C functions, so each reads its cursors from the rr_regs
| struct (native RoadInput pointers + an Offset dst rebased onto fb->px), advances them in registers, and
| writes the four that MOVE (param/width/edge/dst) back at return — the A4 localization contract
| (RR_BAND_PROLOGUE / RR_BAND_EPILOGUE below implement it once for all). Each reads its stack args (m68k
| SysV) behind a GCC-style movem save/restore. C signatures (src/road.c): B/D take (r, rows_m1, second);
| C-near/C-far take (r, rows_m1); band A takes (r) alone (row count hardcoded 96). rows_m1 draws
| (int16)rows_m1+1 times via the 16-bit dbra (callers pass RR_ROWS_?_NEAR / _FAR, always > 0), `second`
| selects the far tail.
|   * d7 invariant. Bands B/C/D run AFTER the first group step, so r->d7 == RR_D7_WORD_MASK (0xfff8); their
|     asm READS r->d7 into d7 and masks the column with it. Which C references also read r->d7 vs hardcode the
|     constant varies per band — all agree because the invariant holds: band B's C and band C-FAR's C read
|     r->d7 (agree unconditionally); band C-NEAR's C and band D's C hardcode RR_D7_WORD_MASK (agree only via
|     the invariant). Band A is DIFFERENT: it runs BEFORE the group step with r->d7 == 0 (scratch), masks the
|     column with the RR_D7_WORD_MASK *constant* (never r->d7), and REUSES d7 as the saved edge dst + d2 as a
|     saved col (restored to the stride before the row tail) — so band A's correctness does NOT depend on
|     r->d7's value. The shared prologue's d7/d2 loads happen to seed A's scratch correctly; A overrides d4 to 96.
|
| Algorithm (the SPEC is each rr_band_?_c in road.c; the op sequence mirrors the machine model). Per scanline
| all do RR_ROW_HEAD (ctrl = be32(width)+be16(param); fine_x column), then read the edge mask + edge_seed and
| a src-strip dispatch on the flag bits, then col = (half_width>>1)&mask and a per-band tail. They differ in
| the flag bits (D: MASK_A2/SPLIT_D/SKIP_D + MASK_OFF_LO + SRC_3500; B: MASK_A/SPLIT_B/SKIP_ABC + MASK_OFF_HI
| + SRC_4700; A/C: MASK read unconditionally; A: MASK_OFF_HI + SRC_5000, C: MASK_OFF_LO + SRC_3E00) and in
| the tails — see each core's banner below.

    .text

#include "road_const.h"

    .globl  rr_band_D_asm
    .globl  rr_band_B_asm
    .globl  rr_band_C_near_asm
    .globl  rr_band_C_far_asm
    .globl  rr_band_A_asm

| ---- stack argument offsets (after the movem.l saves .LSAVED bytes), shared by all cores ----
    .equ    .LSAVED,     44                | d2-d7/a2-a6 = 11 registers * 4 bytes
    .equ    .LA_R,        4+.LSAVED         | rr_regs *r
    .equ    .LA_ROWS,     8+.LSAVED         | uint32_t rows_m1 (B/C/D; garbage for band A, which overrides d4)
    .equ    .LA_SECOND,  12+.LSAVED         | int second (B/D only; near = 0 / far tail = 1)

| RR_BAND_PROLOGUE / RR_BAND_EPILOGUE — the shared A4 localization ABI (identical for all cores): load the
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

| RR_ROW_HEAD — the per-scanline header decode, byte-identical in all five cores (extracted at slice 3, when
| it reached five copies): reset the working cursors, read the control long + the perspective delta into the
| half_width, and offset the src by the fine-x column. Leaves d0 = ctrl (half_width in the low word) and a1 =
| tex + fine_x; d1 holds the fine-x scratch. Each core then reads the edge mask + edge_seed itself, since
| their order (band A reads the mask BEFORE edge_seed; B/C/D after) and conditionality differ.
    .macro  RR_ROW_HEAD
    movea.l %a3, %a1                        | a1 = working src = tex
    movea.l %a2, %a0                        | a0 = working dst = row start
    move.l  (%a5)+, %d0                     | d0 = ctrl = be32(width); width += 4
    add.w   (%a4)+, %d0                     | d0.w = half_width = ctrl.w + be16(param); param += 2
    move.w  %d0, %d1
    andi.w  #0xf, %d1
    lsl.w   #4, %d1                         | d1.w = (half_width & 0xf) << 4 (fine-x sub-column)
    adda.w  %d1, %a1                        | a1 = tex + fine_x
    .endm

| RR_SRCSEL(merge) — the plane-hi / SRC_CONST src-strip select, byte-identical in bands A (machine model
| L92da/L92e6), C-near (L966a/L9676) and C-far (L97ec/L97f8): PLANE_HI adds SRC_5800 and branches to `merge`;
| else a const control long >= 0 selects the 5BAA const strip; otherwise the src is left as-is. The non-
| plane-hi arms fall through to `merge` (each core places its tail label right after the invocation).
    .macro  RR_SRCSEL merge
    btst    #RR_FB_PLANE_HI, %d0
    beq     1f
    adda.w  #RR_SRC_5800, %a1
    bra     \merge
1:  btst    #RR_FB_SRC_CONST, %d0
    beq     \merge
    tst.l   %d0
    bmi     \merge
    movea.l .LA_R(%sp), %a1
    movea.l RR_OFF_EDGE_CONST(%a1), %a1
    adda.w  #RR_CONST_5BAA, %a1             | edge_const + 0x30
    .endm

| ============================================================================================
| Band D (@0x987c near / @0x9950 far): per scanline [left shoulder fill | edge cell | copied texture].
| ============================================================================================
rr_band_D_asm:
    RR_BAND_PROLOGUE

.Lrow:
    RR_ROW_HEAD
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
    RR_ROW_HEAD
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

| ============================================================================================
| Band C-near (@0x9582): edge mask read unconditionally; two tails — a fast edge-split tail
| ([edge cell | left-shoulder fill]) and a merge tail (narrow [texture | one-cell fill | texture]).
| d3 = the full-long edge mask (copy_long_masked ANDs the WHOLE long, not just the hi word as B/D do).
| ============================================================================================
rr_band_C_near_asm:
    RR_BAND_PROLOGUE

.LCn_row:
    RR_ROW_HEAD
    move.w  (%a4)+, %d1                     | d1 = edge_seed; param += 2
    move.l  RR_MASK_OFF_LO(%a1), %d3        | d3 = edge_mask (unconditional in band C)
    moveq   #-1, %d5                        | d5 = 0xffffffff (fill_lo)
    moveq   #0, %d6
    not.w   %d6                             | d6 = 0x0000ffff (fill_hi)
    btst    #RR_FB_PLANE_HI, %d0
    beq     .LCn_nohi_dflt
    swap    %d6                             | d6 = 0xffff0000
.LCn_nohi_dflt:
    btst    #RR_FB_SPLIT_C, %d0
    beq     .LCn_nosplit
    addq.l  #2, %a6                         | split strip: edge cursor advances
    btst    #RR_FB_WIDE, %d0
    bne     .LCn_wide
    btst    #RR_FB_SKIP_D, %d0
    beq     .LCn_srcsel                     | !SKIP_D -> hi/const src select then merge tail
    | ---- fast edge-split (0x95c0) ----
    moveq   #0, %d6                         | fill_hi = 0
    asr.w   #1, %d0
    and.w   %d7, %d0                        | col
    bpl     .LCn_fs_draw
    | col < 0: nothing drawn
    adda.w  %d2, %a2
    dbf     %d4, .LCn_row
    bra     .LCn_done
.LCn_fs_draw:                               | L95d2
    adda.w  %d1, %a1                        | a1 += edge_seed
    adda.w  %d0, %a0                        | a0 += col
    move.w  %d0, %d1                        | save col
    btst    #RR_FB_PLANE_HI, %d0
    beq     .LCn_fs_nohi
    | plane-hi: fill_lo = 0, +0xa800 (+0x0a00 if edge word nonzero)
    moveq   #0, %d5
    adda.l  #RR_SRC_A800, %a1
    tst.w   -2(%a6)
    beq     .LCn_fs_hi_nom
    adda.w  #RR_SRC_0A00, %a1
.LCn_fs_hi_nom:
    sub.w   %d2, %d0                        | col - stride
    bpl     .LCn_fullrow
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    bra     .LCn_fs_shoulder
.LCn_fs_nohi:
    move.w  -2(%a6), %d0                    | be16(edge-2) (clobbers col; saved in d1)
    adda.w  %d0, %a1                        | a1 += sx16(edge-2)
    move.w  %d1, %d0                        | restore col
    sub.w   %d2, %d0                        | col - stride
    bpl     .LCn_fullrow
    move.l  (%a1)+, (%a0)+                  | copy_long
    move.l  (%a1)+, (%a0)                   | copy_long_masked: write ...
    and.l   %d3, (%a0)+                     | ... then AND the whole long with the mask
.LCn_fs_shoulder:                           | L9608
    lsr.w   #3, %d1                         | col >> 3
    subq.w  #1, %d1
    bmi     .LCn_fs_next
    movea.l %a2, %a0                        | left shoulder from row start
.LCn_fs_fill:
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    dbf     %d1, .LCn_fs_fill
.LCn_fs_next:                               | L9618
    adda.w  %d2, %a2
    dbf     %d4, .LCn_row
    bra     .LCn_done
.LCn_fullrow:                               | L9622
    movea.l %a2, %a0
    moveq   #RR_ROW_FILL_DBF, %d1
.LCn_frow:
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    dbf     %d1, .LCn_frow
    adda.w  %d2, %a2
    dbf     %d4, .LCn_row
    bra     .LCn_done

.LCn_wide:                                  | L9638
    moveq   #0, %d6
    adda.w  #RR_SRC_3E00, %a1
    btst    #RR_FB_SRC_400, %d0
    beq     .LCn_wide_no400
    adda.w  #RR_SRC_0400, %a1
    btst    #RR_FB_SRC_100, %d0
    bne     .LCn_merge
    adda.w  #RR_SRC_0100, %a1
    moveq   #0, %d5                         | fill_lo = 0
    bra     .LCn_merge
.LCn_wide_no400:                            | L9656
    btst    #RR_FB_SRC_100, %d0
    bne     .LCn_merge
    adda.w  #RR_SRC_0100, %a1
    moveq   #0, %d5
    not.w   %d5                             | fill_lo = 0x0000ffff
    bra     .LCn_merge

.LCn_nosplit:                               | L9666
    adda.w  %d1, %a1                        | a1 += edge_seed
    move.w  (%a6)+, %d1                     | be16(edge); edge += 2
    adda.w  %d1, %a1
.LCn_srcsel:                                | L966a / L9676
    RR_SRCSEL .LCn_merge

.LCn_merge:                                 | L9686 merge tail
    asr.w   #1, %d0
    and.w   %d7, %d0                        | col
    subq.w  #8, %d0                         | left = col - 8
    bpl     .LCn_merge_left
    addq.w  #8, %d0                         | col
    bmi     .LCn_merge_next                 | col < 0: nothing
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    adda.w  %d2, %a2
    dbf     %d4, .LCn_row
    bra     .LCn_done
.LCn_merge_left:                            | L969e
    adda.w  %d0, %a0                        | a0 += left
    sub.w   %d2, %d0                        | left - stride = rem
    bpl     .LCn_merge_next
    move.l  %d5, (%a0)+                     | fill_pair
    move.l  %d6, (%a0)+
    addq.w  #8, %d0
    bpl     .LCn_merge_next
    move.l  (%a1)+, (%a0)+                  | two texture cells
    move.l  (%a1)+, (%a0)+
.LCn_merge_next:                            | L96b0
    adda.w  %d2, %a2
    dbf     %d4, .LCn_row
    | fall through to .LCn_done

.LCn_done:
    RR_BAND_EPILOGUE

| ============================================================================================
| Band C-far (@0x96b8). LOCKSTEP with C-near: the row front end through the SPLIT_C dispatch — RR_ROW_HEAD,
| the unconditional MASK_OFF_LO mask read, the d5/d6 defaults + PLANE_HI swap, and the SPLIT_C/WIDE/SKIP_D
| branch ladder — is instruction-identical to C-near's (only the branch TARGETS differ, .LCf_* vs .LCn_*).
| It is kept written-out per core, not macro'd, so each reads top-to-bottom against its machine-model
| L-labels; any edit to one MUST be mirrored in the other (the differential pins it). C-far then diverges:
| the fast edge-split path (0x96f6) selects the source strip FIRST and consumes one extra param word, and
| the merge tail (0x9808) is BIDIRECTIONAL — forward texture longs when the road grows rightward, a BACKWARD
| shoulder fill (fill_pair_rev, -(a0)) when it recedes, with d3 (the edge mask) reused as the reverse-fill
| width. The WIDE / no-split / src-select (RR_SRCSEL) tails also match C-near's (shared where clean).
| ============================================================================================
rr_band_C_far_asm:
    RR_BAND_PROLOGUE

.LCf_row:
    RR_ROW_HEAD
    move.w  (%a4)+, %d1                     | edge_seed
    move.l  RR_MASK_OFF_LO(%a1), %d3        | edge_mask
    moveq   #-1, %d5
    moveq   #0, %d6
    not.w   %d6
    btst    #RR_FB_PLANE_HI, %d0
    beq     .LCf_nohi_dflt
    swap    %d6
.LCf_nohi_dflt:
    btst    #RR_FB_SPLIT_C, %d0
    beq     .LCf_nosplit
    addq.l  #2, %a6
    btst    #RR_FB_WIDE, %d0
    bne     .LCf_wide
    btst    #RR_FB_SKIP_D, %d0
    beq     .LCf_srcsel
    | ---- fast edge-split (0x96f6): src select FIRST, extra param word ----
    adda.w  %d1, %a1                        | a1 += edge_seed
    addq.l  #2, %a4                         | far-only extra param word
    asr.w   #1, %d0                         | half_width >> 1 (col not yet masked)
    moveq   #0, %d6
    btst    #RR_FB_PLANE_HI, %d0
    beq     .LCf_fs_nohi
    | plane-hi (0x9704)
    moveq   #0, %d5
    adda.l  #RR_SRC_A800, %a1
    tst.w   -2(%a6)
    beq     .LCf_fs_hi_nom
    adda.w  #RR_SRC_0A00, %a1
.LCf_fs_hi_nom:
    and.w   %d7, %d0                        | col
    bpl     .LCf_fs_hi_draw
    addq.w  #8, %d0                         | col + 8
    bmi     .LCf_fs_hi_next
    addq.l  #8, %a1
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
.LCf_fs_hi_next:                            | L9724
    adda.w  %d2, %a2
    dbf     %d4, .LCf_row
    bra     .LCf_done
.LCf_fs_hi_draw:                            | L972e
    adda.w  %d0, %a0
    move.w  %d0, %d1                        | save col
    sub.w   %d2, %d0                        | col - stride
    bpl     .LCf_fullrow
    addq.w  #8, %d0
    bpl     .LCf_fs_hi_2long
    move.l  (%a1)+, (%a0)+                  | 4 longs (hi: no mask)
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    bra     .LCf_fs_shoulder
.LCf_fs_hi_2long:                           | L9748
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    bra     .LCf_fs_shoulder
.LCf_fs_nohi:                               | L9750
    move.w  -2(%a6), %d1                    | be16(edge-2) (edge_seed already added)
    adda.w  %d1, %a1
    and.w   %d7, %d0                        | col
    bpl     .LCf_fs_nohi_draw
    addq.w  #8, %d0
    bmi     .LCf_fs_nohi_next
    addq.l  #8, %a1
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
.LCf_fs_nohi_next:                          | L9762
    adda.w  %d2, %a2
    dbf     %d4, .LCf_row
    bra     .LCf_done
.LCf_fs_nohi_draw:                          | L976c
    adda.w  %d0, %a0
    move.w  %d0, %d1                        | save col
    sub.w   %d2, %d0                        | col - stride
    bpl     .LCf_fullrow
    addq.w  #8, %d0
    bpl     .LCf_fs_nohi_2long
    move.l  (%a1)+, (%a0)+                  | 4 longs, 2nd masked
    move.l  (%a1)+, (%a0)
    and.l   %d3, (%a0)+
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    bra     .LCf_fs_shoulder
.LCf_fs_nohi_2long:                         | L9784
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)                   | 2nd masked
    and.l   %d3, (%a0)+
.LCf_fs_shoulder:                           | L978a
    lsr.w   #3, %d1
    subq.w  #1, %d1
    bmi     .LCf_fs_next
    movea.l %a2, %a0
.LCf_fs_fill:
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    dbf     %d1, .LCf_fs_fill
.LCf_fs_next:                               | L979a
    adda.w  %d2, %a2
    dbf     %d4, .LCf_row
    bra     .LCf_done
.LCf_fullrow:                               | L97a4
    movea.l %a2, %a0
    moveq   #RR_ROW_FILL_DBF, %d1
.LCf_frow:
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    dbf     %d1, .LCf_frow
    adda.w  %d2, %a2
    dbf     %d4, .LCf_row
    bra     .LCf_done

.LCf_wide:                                  | L97ba
    moveq   #0, %d6
    adda.w  #RR_SRC_3E00, %a1
    btst    #RR_FB_SRC_400, %d0
    beq     .LCf_wide_no400
    adda.w  #RR_SRC_0400, %a1
    btst    #RR_FB_SRC_100, %d0
    bne     .LCf_merge
    adda.w  #RR_SRC_0100, %a1
    moveq   #0, %d5
    bra     .LCf_merge
.LCf_wide_no400:                            | L97d8
    btst    #RR_FB_SRC_100, %d0
    bne     .LCf_merge
    adda.w  #RR_SRC_0100, %a1
    moveq   #0, %d5
    not.w   %d5
    bra     .LCf_merge

.LCf_nosplit:                               | L97e8
    adda.w  %d1, %a1
    move.w  (%a6)+, %d1
    adda.w  %d1, %a1
.LCf_srcsel:                                | L97ec / L97f8
    RR_SRCSEL .LCf_merge

.LCf_merge:                                 | L9808 far merge tail (bidirectional)
    move.w  (%a4)+, %d1                     | count = be16(param); param += 2 (far-only)
    asr.w   #1, %d0
    and.w   %d7, %d0                        | col
    bpl     .LCf_merge_pos
    | col < 0
    addq.w  #8, %d0
    bmi     .LCf_merge_next                 | col+8 < 0: nothing
    addq.l  #8, %a1
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
.LCf_merge_next:                            | L981a
    adda.w  %d2, %a2
    dbf     %d4, .LCf_row
    bra     .LCf_done
.LCf_merge_pos:                             | L9822
    adda.w  %d0, %a0                        | a0 += col
    move.w  %d0, %d3                        | d3 = col (width; edge mask no longer needed here)
    sub.w   %d2, %d0                        | col - stride
    bmi     .LCf_merge_lt                   | col-stride < 0
    subq.w  #8, %d0                         | col - stride - 8
    bmi     .LCf_merge_straight             | stride <= col < stride+8
    | road spans the whole row: advance row, reverse-fill (count - (rem-8)/8) pairs
    adda.w  %d2, %a2
    lsr.w   #3, %d0                         | (col-stride-8) >> 3
    sub.w   %d0, %d1                        | n = count - that
    bmi     .LCf_merge_span_end
    movea.l %a2, %a0                        | a0 = new row start
.LCf_merge_span:                            | L9838
    move.l  %d6, -(%a0)                     | fill_pair_rev (hi then lo, backward)
    move.l  %d5, -(%a0)
    dbf     %d1, .LCf_merge_span
.LCf_merge_span_end:                        | L9840
    dbf     %d4, .LCf_row
    bra     .LCf_done
.LCf_merge_lt:                              | L9846 (col-stride < 0)
    moveq   #0, %d0                         | clear the running count
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
.LCf_merge_straight:                        | L984c
    addq.w  #8, %d0
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    addq.w  #8, %d0
    suba.w  %d0, %a0                        | a0 -= sx16(d0)
.LCf_merge_rfill:                           | L9856
    subq.w  #8, %d3                         | width -= 8
    bmi     .LCf_merge_rfill_end
    move.l  %d6, -(%a0)                     | fill_pair_rev
    move.l  %d5, -(%a0)
    dbf     %d1, .LCf_merge_rfill
.LCf_merge_rfill_end:                       | L9862
    adda.w  %d2, %a2
    dbf     %d4, .LCf_row
    | fall through to .LCf_done

.LCf_done:
    RR_BAND_EPILOGUE

| ============================================================================================
| Band A (@0x9172): 96 rows, the widest branch set — a two-pass renderer. Forward from the road edge it
| copies texture longs then gap-fills; backward it fills the left shoulder (fill_pair_rev, skipping off-row
| cells). See the CONTRACT's band-A d7 bullet for its d7-is-scratch / masks-with-the-constant / d2-holds-col
| ABI (and why the shared prologue/epilogue still fit).
| ============================================================================================
rr_band_A_asm:
    RR_BAND_PROLOGUE
    moveq   #RR_ROWS_A, %d4                 | 96 rows (band A takes no rows arg; overrides the prologue load)

.LA_row:                                    | L9172
    RR_ROW_HEAD
    move.l  RR_MASK_OFF_HI(%a1), %d3        | edge_mask (band A: MASK_OFF_HI)
    move.w  (%a4)+, %d1                     | edge_seed
    moveq   #-1, %d5                        | 0xffffffff
    moveq   #0, %d6
    not.w   %d6                             | 0x0000ffff
    btst    #RR_FB_PLANE_HI, %d0
    beq     .LA_nohi_dflt
    swap    %d6                             | 0xffff0000
.LA_nohi_dflt:
    btst    #RR_FB_SPLIT_A, %d0
    beq     .LA_nosplit                     | L92d6
    addq.l  #2, %a6
    btst    #RR_FB_WIDE, %d0
    bne     .LA_wide                        | L92a8
    btst    #RR_FB_SKIP_ABC, %d0
    beq     .LA_srcsel                      | L92da

    | ---- fast edge-split (0x91b0) ----
    moveq   #0, %d6
    adda.w  %d1, %a1                        | a1 += edge_seed
    move.l  (%a4)+, %d1                     | d1 = count_long = be32(param); param += 4
    asr.w   #1, %d0
    btst    #RR_FB_PLANE_HI, %d0
    beq     .LA_fs_nohi                     | L9230
    | ---- L91c0 (plane-hi) ----
    moveq   #0, %d5
    adda.l  #RR_SRC_A800, %a1
    tst.w   -2(%a6)
    beq     .LA_fs_hi_nom
    adda.w  #RR_SRC_0A00, %a1
.LA_fs_hi_nom:
    andi.w  #RR_D7_WORD_MASK, %d0           | col
    bpl     .LA_fs_hi_sh                    | L91f8
    | col < 0: narrow fill of the whole row (both planes d6)
    moveq   #RR_ROW_FILL_PAIR_DBF, %d1
    addq.w  #8, %d0
    bmi     .LA_fs_hi_fill                  | L91e6
    moveq   #RR_ROW_FILL_EDGE_DBF, %d1
    addq.l  #8, %a1
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
.LA_fs_hi_fill:                             | L91e6
    move.l  %d6, (%a0)+
    move.l  %d6, (%a0)+
    dbf     %d1, .LA_fs_hi_fill
    bra     .LA_row_tail                    | L91ee
.LA_fs_hi_sh:                               | L91f8
    adda.w  %d0, %a0                        | a0 += col
    move.l  %a0, %d7                        | d7 = saved edge dst
    move.w  %d0, %d2                        | d2 = saved col
    subi.w  #RR_ROW_STRIDE_D2, %d0          | col - stride
    bpl     .LA_shpat                       | L928c
    addq.w  #8, %d0
    bpl     .LA_fs_hi_2long                 | L921a
    move.l  (%a1)+, (%a0)+                  | 4 longs (hi: no mask)
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    addq.w  #8, %d0
    bpl     .LA_shpat
    bra     .LA_fs_hi_gap                   | L9224
.LA_fs_hi_2long:                            | L921a
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    addq.w  #8, %d0
    bpl     .LA_shpat
.LA_fs_hi_gap:                              | L9224
    move.l  %d6, (%a0)+
    move.l  %d6, (%a0)+
    addq.w  #8, %d0
    bmi     .LA_fs_hi_gap
    bra     .LA_shpat
.LA_fs_nohi:                                | L9230
    move.w  -2(%a6), %d7                    | be16(edge-2) (d7 free here: not yet the saved-a0)
    adda.w  %d7, %a1
    andi.w  #RR_D7_WORD_MASK, %d0           | col
    bpl     .LA_fs_nohi_sh                  | L925c
    | col < 0: narrow fill, edge cell masked
    moveq   #RR_ROW_FILL_PAIR_DBF, %d1
    addq.w  #8, %d0
    bmi     .LA_fs_nohi_fill                | L924a
    moveq   #RR_ROW_FILL_EDGE_DBF, %d1
    addq.l  #8, %a1
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)
    and.l   %d3, (%a0)+                     | copy_long_masked
.LA_fs_nohi_fill:                           | L924a
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    dbf     %d1, .LA_fs_nohi_fill
    bra     .LA_row_tail                    | L91ee
.LA_fs_nohi_sh:                             | L925c
    adda.w  %d0, %a0
    move.l  %a0, %d7                        | d7 = saved edge dst
    move.w  %d0, %d2                        | d2 = saved col
    subi.w  #RR_ROW_STRIDE_D2, %d0          | col - stride
    bpl     .LA_shpat                       | L928c
    addq.w  #8, %d0
    bpl     .LA_fs_nohi_2long               | L927c
    move.l  (%a1)+, (%a0)+                  | 4 longs, last masked
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)
    and.l   %d3, (%a0)+
    addq.w  #8, %d0
    bpl     .LA_shpat
    bra     .LA_fs_nohi_gap                 | L9284
.LA_fs_nohi_2long:                          | L927c
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    addq.w  #8, %d0
    bpl     .LA_shpat
.LA_fs_nohi_gap:                            | L9284
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    addq.w  #8, %d0
    bmi     .LA_fs_nohi_gap

.LA_shpat:                                  | L928c: shoulder plane pattern
    moveq   #0, %d5
    not.w   %d5                             | d5 = 0x0000ffff
    move.l  %d5, %d6                        | d6 = 0x0000ffff
    tst.l   %d0                             | (int32)ctrl >= 0 ?
    bpl     .LA_widepat
    btst    #RR_FB_PLANE_HI, %d0
    beq     .LA_widepat
    moveq   #-1, %d5                        | 0x92a0: d5 = 0xffffffff, d6 = 0
    moveq   #0, %d6
    bra     .LA_widepat                     | L936a

.LA_wide:                                   | L92a8
    moveq   #0, %d6
    adda.w  #RR_SRC_5000, %a1
    btst    #RR_FB_SRC_400, %d0
    beq     .LA_wide_no400
    adda.w  #RR_SRC_0400, %a1
    btst    #RR_FB_SRC_100, %d0
    bne     .LA_center                      | L92f6
    adda.w  #RR_SRC_0100, %a1
    moveq   #0, %d5
    bra     .LA_center
.LA_wide_no400:                             | L92c6
    btst    #RR_FB_SRC_100, %d0
    bne     .LA_center
    adda.w  #RR_SRC_0100, %a1
    moveq   #0, %d5
    not.w   %d5                             | d5 = 0x0000ffff
    bra     .LA_center

.LA_nosplit:                                | L92d6
    adda.w  %d1, %a1                        | a1 += edge_seed
    move.w  (%a6)+, %d1                     | be16(edge); edge += 2
    adda.w  %d1, %a1
.LA_srcsel:                                 | L92da / L92e6
    RR_SRCSEL .LA_center

.LA_center:                                 | L92f6 center/merge tail
    move.l  (%a4)+, %d1                     | d1 = count_long = be32(param); param += 4
    asr.w   #1, %d0
    andi.w  #RR_D7_WORD_MASK, %d0           | col
    bpl     .LA_center_sh                   | L9328
    | col < 0: narrow centre
    addq.l  #8, %a1
    addq.w  #8, %d0
    bpl     .LA_center_2long                | L930a
    addq.w  #8, %d0
    bra     .LA_center_narrowcnt            | L930e
.LA_center_2long:                           | L930a
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
.LA_center_narrowcnt:                       | L930e
    asr.w   #3, %d0
    add.w   %d0, %d1                        | count = count_long.w + (col..)>>3
    bmi     .LA_center_narrowdone           | L931c
.LA_center_narrowfill:
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    dbf     %d1, .LA_center_narrowfill
.LA_center_narrowdone:                      | L931c
    adda.w  #RR_ROW_STRIDE_D2, %a2
    bra     .LA_next                        | L9320 (skip the a2 += d2 tail)
.LA_center_sh:                              | L9328
    adda.w  %d0, %a0
    move.l  %a0, %d7                        | d7 = saved edge dst
    move.w  %d0, %d2                        | d2 = saved col
    subi.w  #RR_ROW_STRIDE_D2, %d0          | col - stride
    bpl     .LA_center_shpat                | L9352
    addq.w  #8, %d0
    bpl     .LA_center_2long_sh             | L934e
    move.l  (%a1)+, (%a0)+                  | 4 longs (no mask)
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
.LA_center_gap:                             | L9340 combined gap fill
    addq.w  #8, %d0
    bpl     .LA_center_shpat
    move.l  %d5, (%a0)+
    move.l  %d6, (%a0)+
    dbf     %d1, .LA_center_gap
    bra     .LA_center_shpat
.LA_center_2long_sh:                        | L934e
    move.l  (%a1)+, (%a0)+
    move.l  (%a1)+, (%a0)+
.LA_center_shpat:                           | L9352
    moveq   #0, %d5
    not.w   %d5
    move.l  %d5, %d6                        | d5 = d6 = 0x0000ffff
    btst    #RR_FB_SRC_CONST, %d0
    beq     .LA_widepat
    tst.l   %d0
    bmi     .LA_widepat
    btst    #RR_FB_PLANE_HI, %d0
    bne     .LA_widepat
    moveq   #-1, %d5                        | d5 = 0xffffffff

.LA_widepat:                                | L936a: WIDE shoulder pattern override
    btst    #RR_FB_WIDE, %d0
    beq     .LA_rfill_setup
    moveq   #-1, %d5
    moveq   #0, %d6                         | d5 = 0xffffffff, d6 = 0
    btst    #RR_FB_SRC_100, %d0
    beq     .LA_rfill_setup
    moveq   #0, %d5
    btst    #RR_FB_SRC_400, %d0
    bne     .LA_rfill_setup
    not.w   %d5                             | d5 = 0x0000ffff

.LA_rfill_setup:                            | L9384
    movea.l %d7, %a0                        | a0 = saved edge dst
    move.w  %d2, %d0                        | d0 = saved col
    swap    %d1                             | d1 = count (count_long high word)
    move.w  #RR_ROW_STRIDE_D2, %d2          | restore d2 = stride
.LA_rfill:                                  | L938e backward shoulder fill (skip off-row cells)
    subq.w  #8, %d0                         | width -= 8
    bmi     .LA_row_tail                    | L93a6
    cmp.w   %d2, %d0                        | width - stride
    bpl     .LA_rfill_skip                  | width >= stride: off-row, skip
    move.l  %d6, -(%a0)                     | fill_pair_rev
    move.l  %d5, -(%a0)
    dbf     %d1, .LA_rfill
    bra     .LA_row_tail
.LA_rfill_skip:                             | L93a0
    subq.l  #8, %a0
    dbf     %d1, .LA_rfill

.LA_row_tail:                               | L91ee / L93a6
    adda.w  %d2, %a2                        | a2 += stride (d2 is the stride on every path reaching here)
.LA_next:                                   | L9320
    dbf     %d4, .LA_row
    RR_BAND_EPILOGUE
