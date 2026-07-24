| objshift.S — hand-written m68k core for the colour-indexed fine-x masked sprite blitter (.S: cpp runs
| first, so it #includes the shared constant headers — see the Engine constants block below).
| PERF30 A3 phase 2. The byte-exact REFERENCE is rm_blit_objshift() in src/blit.c (fuzz-pinned); this is
| a drop-in replacement with the SAME C signature, shipped on the m68k builds behind -DRM_ASM_BLIT (see
| include/game.h RM_BLIT_OBJSHIFT, render/atari/README, test/test_asm_blit.py). Never diverge from the C
| by one byte — test/test_asm_blit.py runs every fuzz case through both the C and this asm under Musashi
| and byte-compares the whole destination.
|
| The template is the ORIGINAL game's own blit_objshift @0x14680 (its cycle-profiled disassembly runs
| this exact work in 110,572 cyc vs the C's 181,836). Its winning tricks, ported here:
|   * the four per-plane colour fill words loaded ONCE per call into d3/d5 as two 32-bit pairs and
|     swap-toggled per plane (2 registers hold 4 halves) — no per-plane color_pairs reload.
|   * moveq #-1 mask seed — the 0xFFFF high word (the SHOW mask ~(a|b|c)&d over four planes) comes for
|     free and rotates into the straddled column.
|   * all 4 planes fully unrolled, source walked with (a1)+, interleaved and.w/or.w memory RMW.
|   * per-family rewind baked as an immediate (dst) plus one register (src, since stride is runtime).
|
| Unlike objshift2 (plain OR, mask applied as a 32-bit block), objshift is COLOUR-INDEXED: each of the
| four planes gets the shifted source word gated by that plane's colour fill (fill.plane[N]), so the
| mask is applied per-plane word (4× and.w) and the pixels per-plane (4× or.w). Plane 3 folds in the
| transparency ~mask special case inline.
|
| C signature (include/game.h):
|   void rm_blit_objshift(uint8_t *dst, uint32_t dst_off, const uint8_t *src, uint32_t src_off,
|                         uint16_t x, uint16_t color, uint16_t rows_m1, int16_t stride,
|                         const uint8_t *color_pairs, int base_cells);
|
| Algorithm (the SPEC is the C in blit.c; transcribed here):
|   fine_x = x & 0xf;  shl = 16 - fine_x;  shr = fine_x;
|   col_off = (color & 0xf) << 3;  fill = color_pairs[col_off .. col_off+7]  (four 16-bit plane words)
|   A = ((int16)x >> 1) & 0xfff8;                   aligned 8-byte column (signed)
|   base_ceiling = 0x98 - 8*(base_cells-1);
|   col0 = dst + dst_off + sx16(A);  col1 = col0 + 8;  sp = src + src_off;
|   A < 0                     -> LEFT: k=(-A)/8; k>base_cells -> off-left return; straddle=base_cells-k,
|                                skips=k-1 (pre-advance col0/sp by 8*skips)
|   A - base_ceiling >= 0     -> RIGHT: s=(0x98-A)/8; s<0 -> off-right return; straddle=s
|   otherwise                 -> BASE, straddle = base_cells
|   per row: [left edge] then `straddle` straddle cells then [right edge]; then both columns step one
|   scanline up (-SCREEN_ROW_BYTES) and the source steps OBJSH_CELL_BYTES - sx16(stride) (SIGNED: stride
|   8 -> net 0 = re-read the same source row!; stride 0xa8 -> -160; stride -8 -> +16). rows = rows_m1 + 1.
|
| CONTRACT: base_cells ∈ {1, 2} — every object_list.c caller passes 1 or 2. The BASE path tests `== 1`
| and otherwise falls through to the 2-cell family, so base_cells >= 3 would draw 2 cells here where the
| C reference draws base_cells cells: a divergence OUTSIDE the contract, unreachable from the game's own
| callers (so neither the fuzz nor the differential exercises it — honestly unpinned, see PERF30 A3).
|
| Register roles (held across the row loop):
|   a0 = col0 cursor (dst)      a1 = sp cursor (src)      a2 = col1 cursor (dst + 8)
|   a3 = src per-row rewind = stride + 8*(total_cells - 1)  (holds the runtime stride term)
|   d0 = scratch / pixels       d1 = mask_col0 / scratch
|   d2 = mask_col1 / scratch    d3 = fill pair 0 (planes 0/1, swap-toggled)
|   d4 = row counter (dbra)     d5 = fill pair 1 (planes 2/3, swap-toggled)
|   d6 = shl (lsl.l / rol.l / lsl.w count)   d7 = shr (lsr.l / lsr.w count; RIGHT edge only)

    .text
    .globl  rm_blit_objshift_asm

| ---- stack argument offsets (after the movem.l saves .LSAVED bytes) ----
    .equ    .LSAVED,   32                  | d2-d7/a2-a3 = 8 registers * 4 bytes
    .equ    .LA_DST,     4+.LSAVED          | uint8_t *dst
    .equ    .LA_DSTOFF,  8+.LSAVED          | uint32_t dst_off
    .equ    .LA_SRC,    12+.LSAVED          | const uint8_t *src
    .equ    .LA_SRCOFF, 16+.LSAVED          | uint32_t src_off
    .equ    .LA_X_W,    22+.LSAVED          | uint16_t x        (value in the slot's low word)
    .equ    .LA_COLOR_W,26+.LSAVED          | uint16_t color    (low word)
    .equ    .LA_ROWS_W, 30+.LSAVED          | uint16_t rows_m1  (low word)
    .equ    .LA_STRIDE_W,34+.LSAVED         | int16_t  stride   (low word)
    .equ    .LA_PAIRS,  36+.LSAVED          | const uint8_t *color_pairs
    .equ    .LA_BCELLS_W,42+.LSAVED         | int base_cells    (low word; 1 or 2)

| Engine constants shared with the C reference — ONE source of truth (this is a .S, so cpp expands the
| #includes before the assembler runs). SCREEN_ROW_BYTES from screen.h (C-only parts guarded behind
| __ASSEMBLER__); OBJSH_* from blit_const.h (hoisted out of blit.c). See F11.
#include "screen.h"
#include "blit_const.h"

| ============================================================================================
| STRADDLE_CELL — one straddle group: for each of the 4 planes, mask the current word of both columns,
| then OR in the colour-gated shifted pixels (high half -> col0, low half -> col1). Byte-for-byte the
| original's cell (@0x146b2). Rebuilds the mask each cell (moveq #-1 seed) from the 4 source words read
| with (a1)+ then rewound (subq.l #8), then walks (a1)+ again for the pixels. Advances col0 (a0) and
| col1 (a2) by 8, sp (a1) by 8. Clobbers d0/d1/d2 (and toggles d3/d5 back to their loaded values).
| ============================================================================================
    .macro  OSH_MASK_BUILD
    moveq   #-1, %d2                     | mask seed 0xFFFFFFFF (high word 0xFFFF is load-bearing)
    move.w  (%a1)+, %d2                  | d2 = 0xFFFF:a
    or.w    (%a1)+, %d2                  | d2 = 0xFFFF:(a|b)
    or.w    (%a1)+, %d2                  | d2 = 0xFFFF:(a|b|c)
    move.w  (%a1)+, %d0
    not.w   %d0                          | d0 = ~d (low word)
    or.w    %d0, %d2                     | d2 = 0xFFFF:((a|b|c)|~d)
    not.w   %d2                          | d2 = 0xFFFF:(~(a|b|c)&d)   (not.w keeps the 0xFFFF high word)
    subq.l  #OBJSH_CELL_BYTES, %a1       | rewind sp by 8 (re-read the 4 words for the pixels)
    .endm

| OSH_PLANE — one plane of a straddle cell. `fillreg` holds this plane-pair's two fill halves; `swap`
| toggles it to this plane's half (invoked twice per pair, so it returns to its loaded value). Masks both
| columns' current word, then ORs the colour-gated pixels: low(pix)&fill -> col1, high(pix)&fill -> col0.
    .macro  OSH_PLANE  fillreg
    and.w   %d1, (%a0)                   | col0 word &= mask_col0
    and.w   %d2, (%a2)                   | col1 word &= mask_col1
    moveq   #0, %d0
    move.w  (%a1)+, %d0
    lsl.l   %d6, %d0                     | pix = word << shl (32-bit straddle)
    swap    \fillreg                     | fillreg low word = this plane's fill half
    and.w   \fillreg, %d0                | low(pix) &= fill
    or.w    %d0, (%a2)+                  | col1 |= low(pix)&fill ; col1 += 2
    swap    %d0
    and.w   \fillreg, %d0                | high(pix) &= fill
    or.w    %d0, (%a0)+                  | col0 |= high(pix)&fill ; col0 += 2
    .endm

| OSH_PLANE_LAST — plane 3: same as OSH_PLANE but folds the transparency ~mask (C's `if(is_last)
| pix &= ~mask`). Clobbers d1/d2 (notted), which the next cell rebuilds.
    .macro  OSH_PLANE_LAST  fillreg
    and.w   %d1, (%a0)
    and.w   %d2, (%a2)
    moveq   #0, %d0
    move.w  (%a1)+, %d0
    lsl.l   %d6, %d0
    swap    \fillreg
    and.w   \fillreg, %d0
    not.w   %d2                          | ~mask_col1
    and.w   %d2, %d0                     | low(pix) &= ~mask_col1
    or.w    %d0, (%a2)+
    swap    %d0
    and.w   \fillreg, %d0
    not.w   %d1                          | ~mask_col0
    and.w   %d1, %d0                     | high(pix) &= ~mask_col0
    or.w    %d0, (%a0)+
    .endm

    .macro  STRADDLE_CELL
    OSH_MASK_BUILD
    rol.l   %d6, %d2                     | rotl32(mask, shl) -> [mask_col0 : mask_col1]
    move.l  %d2, %d1
    swap    %d1                          | d1 low word = mask_col0 (high half); d2 low = mask_col1
    OSH_PLANE      %d3                    | plane 0 -> fill.plane[0]
    OSH_PLANE      %d3                    | plane 1 -> fill.plane[1]
    OSH_PLANE      %d5                    | plane 2 -> fill.plane[2]
    OSH_PLANE_LAST %d5                    | plane 3 -> fill.plane[3] + ~mask
    .endm

| LEFT_EDGE_CELL — the single on-screen column is col1; col0 only steps. Mask is the low word of
| rotl32(m32, shl) applied per plane; pixels shift left as 16-bit words (lsl.w). Transcribed from the
| original @0x14760. a1 += 8, col1 (a2) += 8, col0 (a0) += 8. Clobbers d0/d1/d2.
    .macro  OSH_LEFT_PLANE  fillreg
    and.w   %d2, (%a2)                   | col1 word &= mask
    move.w  (%a1)+, %d0
    lsl.w   %d6, %d0                     | word << shl (16-bit: only col1's half is used)
    swap    \fillreg
    and.w   \fillreg, %d0
    or.w    %d0, (%a2)+                  | col1 |= (word<<shl)&fill ; col1 += 2
    .endm

    .macro  LEFT_EDGE_CELL
    OSH_MASK_BUILD
    rol.l   %d6, %d2                     | rotl32(m32, shl); low word = mask (col1)
    and.w   %d2, (%a2)                   | col1 word &= mask (plane 0)
    move.w  (%a1)+, %d0
    lsl.w   %d6, %d0
    swap    %d3
    and.w   %d3, %d0
    or.w    %d0, (%a2)+                  | plane 0 -> fill.plane[0]
    OSH_LEFT_PLANE %d3                    | plane 1 -> fill.plane[1]
    OSH_LEFT_PLANE %d5                    | plane 2 -> fill.plane[2]
    and.w   %d2, (%a2)                   | col1 word &= mask (plane 3)
    move.w  (%a1)+, %d0
    lsl.w   %d6, %d0
    swap    %d5
    and.w   %d5, %d0                     | plane 3 -> fill.plane[3]
    not.w   %d2                          | ~mask
    and.w   %d2, %d0                     | pix &= ~mask (last plane)
    or.w    %d0, (%a2)+
    lea     OBJSH_CELL_BYTES(%a0), %a0   | col0 += 8 (step only)
    .endm

| RIGHT_EDGE_CELL — the single on-screen column is col0; col1 only steps. Mirror of LEFT_EDGE_CELL with
| the right shift: mask = low word of (m32 >> shr), pixels shift right (lsr.w by shr). a1 += 8, col0 (a0)
| += 8, col1 (a2) += 8. Clobbers d0/d1/d2.
    .macro  OSH_RIGHT_PLANE  fillreg
    and.w   %d2, (%a0)                   | col0 word &= mask
    move.w  (%a1)+, %d0
    lsr.w   %d7, %d0                     | word >> shr (16-bit)
    swap    \fillreg
    and.w   \fillreg, %d0
    or.w    %d0, (%a0)+                  | col0 |= (word>>shr)&fill ; col0 += 2
    .endm

    .macro  RIGHT_EDGE_CELL
    OSH_MASK_BUILD
    lsr.l   %d7, %d2                     | m32 >> shr; low word = mask (col0)
    and.w   %d2, (%a0)                   | col0 word &= mask (plane 0)
    move.w  (%a1)+, %d0
    lsr.w   %d7, %d0
    swap    %d3
    and.w   %d3, %d0
    or.w    %d0, (%a0)+                  | plane 0 -> fill.plane[0]
    OSH_RIGHT_PLANE %d3                   | plane 1 -> fill.plane[1]
    OSH_RIGHT_PLANE %d5                   | plane 2 -> fill.plane[2]
    and.w   %d2, (%a0)                   | col0 word &= mask (plane 3)
    move.w  (%a1)+, %d0
    lsr.w   %d7, %d0
    swap    %d5
    and.w   %d5, %d0                     | plane 3 -> fill.plane[3]
    not.w   %d2                          | ~mask
    and.w   %d2, %d0
    or.w    %d0, (%a0)+
    lea     OBJSH_CELL_BYTES(%a2), %a2   | col1 += 8 (step only)
    .endm

| The per-row dst rewind: 8*total_cells + one scanline. Both columns advanced 8*total during the row, so
| this net-steps them one scanline up (-SCREEN_ROW_BYTES).
    .equ    .LDST_RW1,  OBJSH_CELL_BYTES*1 + SCREEN_ROW_BYTES   | total_cells = 1
    .equ    .LDST_RW2,  OBJSH_CELL_BYTES*2 + SCREEN_ROW_BYTES   | total_cells = 2

| ============================================================================================
rm_blit_objshift_asm:
    movem.l %d2-%d7/%a2-%a3, -(%sp)      | GCC-style callee-save prologue

    | --- colour fill: load the two 32-bit pairs once (P1). col_off = (color & 0xf) << 3. ---
    movea.l .LA_PAIRS(%sp), %a2          | a2 = color_pairs (temp; a2 becomes col1 later)
    move.w  .LA_COLOR_W(%sp), %d1
    andi.w  #OBJSH_NIBBLE, %d1
    lsl.w   #3, %d1                      | d1 = col_off
    move.l  (%a2, %d1.w), %d3            | d3 = fill pair 0 = [fill.plane[0] : fill.plane[1]]
    move.l  4(%a2, %d1.w), %d5           | d5 = fill pair 1 = [fill.plane[2] : fill.plane[3]]

    | --- shifts ---
    move.w  .LA_X_W(%sp), %d0            | x
    moveq   #OBJSH_NIBBLE, %d7
    and.w   %d0, %d7                     | d7 = shr = fine_x = x & 0xf
    moveq   #OBJSH_SUBPX_BITS, %d6
    sub.w   %d7, %d6                     | d6 = shl = 16 - fine_x

    move.w  .LA_ROWS_W(%sp), %d4         | rows_m1 (dbra counts rows_m1 + 1 times)
    bmi     .Losh_done                   | rows_m1 bit15 set -> C draws (int16)rows_m1+1 <= 0 rows; skip

    | --- cursors ---
    movea.l .LA_DST(%sp), %a0
    adda.l  .LA_DSTOFF(%sp), %a0         | a0 = dst + dst_off
    movea.l .LA_SRC(%sp), %a1
    adda.l  .LA_SRCOFF(%sp), %a1         | a1 = sp = src + src_off

    | --- aligned column A = ((int16)x >> 1) & 0xfff8 ---
    asr.w   #1, %d0
    andi.w  #COL_ALIGN, %d0              | d0 = A (signed); N flag = (A < 0)
    adda.w  %d0, %a0                     | a0 = col0 = dst + dst_off + sx16(A)  (adda.w keeps CC)
    bmi     .Losh_left                   | A < 0 -> LEFT clip ladder

    | --- A >= 0: base vs right. base_ceiling = 0x98 - 8*(bcells-1) = (0x98+8) - 8*bcells. Uses only d0
    | (A, preserved for the RIGHT recompute) and d2 as scratch — d3/d5 hold the colour fill pairs. ---
    move.w  .LA_BCELLS_W(%sp), %d1       | d1 = base_cells (1 or 2)
    move.w  %d1, %d2
    lsl.w   #3, %d2                      | 8*base_cells
    add.w   %d0, %d2                     | A + 8*base_cells
    subi.w  #(OBJSH_RIGHT_BOUND+OBJSH_CELL_BYTES), %d2  | A - base_ceiling
    bpl     .Losh_right                  | (A - base_ceiling) >= 0 -> RIGHT clip ladder

    | --- BASE: straddle = base_cells. col1 = col0 + 8. ---
    movea.l %a0, %a2
    addq.l  #OBJSH_CELL_BYTES, %a2       | col1 = col0 + 8
    cmpi.w  #1, %d1
    beq     .Losh_base1
    | fall through: base_cells == 2 (straddle 2)
.Losh_base2:
    movea.w .LA_STRIDE_W(%sp), %a3
    adda.w  #OBJSH_CELL_BYTES, %a3       | a3 = src rewind = stride + 8*(total-1), total = 2
.Losh_base2_row:
    STRADDLE_CELL
    STRADDLE_CELL
    suba.w  #.LDST_RW2, %a0
    suba.w  #.LDST_RW2, %a2
    suba.l  %a3, %a1                     | a1 = row_start + 8 - stride (net source step)
    dbra    %d4, .Losh_base2_row
    bra     .Losh_done
.Losh_base1:
    movea.w .LA_STRIDE_W(%sp), %a3       | a3 = src rewind = stride (total = 1)
.Losh_base1_row:
    STRADDLE_CELL
    suba.w  #.LDST_RW1, %a0
    suba.w  #.LDST_RW1, %a2
    suba.l  %a3, %a1
    dbra    %d4, .Losh_base1_row
    bra     .Losh_done

| ---- LEFT clip (A < 0): k = (-A)/8; straddle = base_cells - k; skips = k - 1 ----
.Losh_left:
    move.w  .LA_BCELLS_W(%sp), %d1       | base_cells
    neg.w   %d0                          | d0 = -A (positive multiple of 8)
    lsr.w   #3, %d0                      | d0 = k
    cmp.w   %d1, %d0
    bgt     .Losh_done                   | k > base_cells -> off the left edge, draw nothing
    move.w  %d0, %d2
    subq.w  #1, %d2                      | d2 = skips = k - 1  (0 or 1)
    lsl.w   #3, %d2                      | 8*skips
    adda.w  %d2, %a0                     | col0 pre-advance
    adda.w  %d2, %a1                     | sp pre-advance
    sub.w   %d0, %d1                     | d1 = straddle = base_cells - k  (0 or 1)
    movea.l %a0, %a2
    addq.l  #OBJSH_CELL_BYTES, %a2       | col1 = col0 + 8
    movea.w .LA_STRIDE_W(%sp), %a3       | a3 = stride (total-1 term added below per straddle)
    tst.w   %d1
    beq     .Losh_left_s0
    | straddle == 1 -> total = 2
.Losh_left_s1:
    adda.w  #OBJSH_CELL_BYTES, %a3       | a3 = stride + 8
.Losh_left_s1_row:
    LEFT_EDGE_CELL
    STRADDLE_CELL
    suba.w  #.LDST_RW2, %a0
    suba.w  #.LDST_RW2, %a2
    suba.l  %a3, %a1
    dbra    %d4, .Losh_left_s1_row
    bra     .Losh_done
.Losh_left_s0:
    | straddle == 0 -> total = 1, a3 = stride (already loaded)
.Losh_left_s0_row:
    LEFT_EDGE_CELL
    suba.w  #.LDST_RW1, %a0
    suba.w  #.LDST_RW1, %a2
    suba.l  %a3, %a1
    dbra    %d4, .Losh_left_s0_row
    bra     .Losh_done

| ---- RIGHT clip (A - base_ceiling >= 0): s = (0x98 - A)/8; straddle = s ----
.Losh_right:
    move.w  #OBJSH_RIGHT_BOUND, %d1
    sub.w   %d0, %d1                     | d1 = 0x98 - A
    bmi     .Losh_done                   | s < 0 -> off the right edge, draw nothing
    lsr.w   #3, %d1                      | d1 = straddle = s  (0 or 1)
    movea.l %a0, %a2
    addq.l  #OBJSH_CELL_BYTES, %a2       | col1 = col0 + 8
    movea.w .LA_STRIDE_W(%sp), %a3
    tst.w   %d1
    beq     .Losh_right_s0
    | straddle == 1 -> total = 2
.Losh_right_s1:
    adda.w  #OBJSH_CELL_BYTES, %a3       | a3 = stride + 8
.Losh_right_s1_row:
    STRADDLE_CELL
    RIGHT_EDGE_CELL
    suba.w  #.LDST_RW2, %a0
    suba.w  #.LDST_RW2, %a2
    suba.l  %a3, %a1
    dbra    %d4, .Losh_right_s1_row
    bra     .Losh_done
.Losh_right_s0:
    | straddle == 0 -> total = 1, a3 = stride
.Losh_right_s0_row:
    RIGHT_EDGE_CELL
    suba.w  #.LDST_RW1, %a0
    suba.w  #.LDST_RW1, %a2
    suba.l  %a3, %a1
    dbra    %d4, .Losh_right_s0_row
    | fall through to done

.Losh_done:
    movem.l (%sp)+, %d2-%d7/%a2-%a3
    rts
