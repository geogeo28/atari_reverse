| scroll_tile.S — the asm twin for the tile-column decoder, TRANSCRIBED from the original binary.
|
|   scroll_emit_tile_column_asm  <- the original @ 0x162c2, the C reference scroll_emit_tile_column
|
| WHAT A TWIN IS is written out in scroll_emit.S beside it, and holds here word for word: the C in
| ../scroll.c is byte-for-byte equivalent to the original (test/test_scroll.py's differential vs the
| Musashi oracle), the original's own instructions are in ../../out/prg_dis.txt, and everything
| between the prologue and the epilogues below is that instruction sequence in order. The only
| judgement exercised was how to translate the original's register and addressing conventions into
| the C ABI, and the three blocks below are the whole of it.
|
| THE C ABI. The twin carries the SAME signature as the core it replaces, because ../frame.c and
| ../init.c reach it through the ZY_SCROLL() seam in ../../include/scroll.h:
|
|   uint32_t scroll_emit_tile_column(uint8_t *image, uint32_t screen_edge, uint32_t page,
|                                    uint32_t map_column);
|
| ...and the RETURN VALUE is the map cursor as an image OFFSET again — `a6 - image` — because a6 is
| the original's one register output and both call sites (0x10d2c, 0x110bc) store it into `map_ptr`.
|
| REGISTERS. The original's, unchanged through the body:
|   a0 = the screen's right-edge column cursor    a5 = the page's own column cursor
|   a6 = the map cursor, IN and OUT               a3 = the workspace cursor
|   a1 = the near tile's pixel-row pointer        a2 = the far tile's
|   a4 = the tile-row counter, parked across the movem that clobbers d0
|   d0-d3 = the near tile's four plane words, then the packed `near : far` longwords
|   d4-d7 = the far tile's four plane words
|
| THE IMAGE BASE, and why the substitution it forces is free. The original IS the image, so it
| addresses the game's globals absolutely, and one of those `lea`s is INSIDE the outer loop:
|
|   tst.b  $19ac1.l   (once, at entry)      -> A_scroll_prefill_hide_screen
|   lea    $19fae.l,a3 (once, at entry)     -> A_scroll_col_workspace
|   lea    $4b3be.l,a1 (once per TILE ROW)  -> A_tile_set_base
|
| Every address register is already spoken for, so there is nowhere to park a base: `image +
| A_tile_set_base` is formed once in the prologue into a four-byte stack slot, and the in-loop `lea`
| becomes `movea.l FRAME_TILE_SET(%sp),%a1`. THE SLOT IS AT DISPLACEMENT ZERO ON PURPOSE — that
| assembles to `movea.l (%sp),%a1`, 12 cycles and three reads, which is exactly what
| `lea $4b3be.l,a1` costs. The hot substitution is therefore cycle-neutral, not merely cheap, and it
| was MEASURED so: moving the slot to displacement 4 costs the call 76 cycles more, 4 for each of the
| eighteen tile rows plus 4 on the prologue's own store. (The two once-per-call substitutions at
| entry are NOT cycle-neutral — an absolute address formed by `movea.l`+`adda.l #imm` costs 20 where
| a `lea abs.l` costs 12 — and at once per call they are noise.)
|
| %sp MUST NOT MOVE after the prologue or FRAME_TILE_SET and the ARG_* displacements go wrong — hence
| `lea` for the frame and no push or pop anywhere in the body.
|
| WHAT THE ASSEMBLED ARMS ARE. Byte-identical to the original's, compared instruction for
| instruction across all four, with three classes of difference and no others: the four substituted
| `lea`s above; the four `dbf` displacements, which necessarily differ; and gas spelling
| `and.w #$7fff,dN` as the ANDI encoding where the original's assembler used the AND-immediate one —
| four bytes and the same flags either way, and the M68000 manual gives both 8 cycles (Musashi's
| model charges the original's encoding 2 more, which is the instrument, not the code, and it leaves
| the twin marginally UNDER the original per masked arm rather than over).
|
| The whole call measures 1.011x the original on the twelve shipped levels — 350-360 cycles on
| 31,700-32,300, all of it the C-ABI prologue and epilogue the original has no counterpart for, and
| none of it per tile row. test_asm_scroll.py::test_the_tile_twin_costs_what_the_original_costs is
| that reading, taken every run.

    .text

| ---- constants: ../../include/scroll.h's and ../../include/video.h's, by their names there --------
| test_constants.py::test_asm_twin_equates_match_the_headers pins every one of these against the
| header that owns it, so a value that moved there cannot go on living here.
    .equ A_scroll_prefill_hide_screen, 0x19ac1  | non-zero: emit the column into the page, not the screen
    .equ A_scroll_col_workspace,       0x19fae  | the 32-pixel workspace the two emitters drain
    .equ A_tile_set_base,              0x4b3be  | 64 bytes a tile, indexed by the map word
    .equ MAP_ROWS,                     18       | words down one map column
    .equ SCROLL_MAP_PEEK_NEXT,         34       | 36 - the 2 the `(a6)+` beside it already stepped
    .equ SCROLL_TILE_BYTES,            64
    .equ SCROLL_TILE_PIXEL_ROWS,       8        | the eight unrolled row decodes inside each arm
    .equ SCROLL_TILE_ROW_BYTES,        8        | four plane words
    .equ SCROLL_TILE_LAST_ROW,         56       | where a vertically flipped tile starts reading
    .equ SCROLL_TILE_INDEX_MASK,       0x7fff   | the map word without its flip bit
    .equ SCROLL_COLUMN_ROW_LONGS,      4        | planes — a tile row's words and a workspace row's longs
    .equ SCREEN_ROW_BYTES,             160

| The tile index is scaled by `lsl.l #6`, so the shift and SCROLL_TILE_BYTES are one fact spelt two
| ways; assembling fails if they ever stop agreeing.
    .equ TILE_INDEX_SHIFT, 6
    .if (1 << TILE_INDEX_SHIFT) != SCROLL_TILE_BYTES
    .error "TILE_INDEX_SHIFT no longer scales a tile index by SCROLL_TILE_BYTES"
    .endif

| One workspace row is the four planes as `near word : far word` longs — `lea 16(a3),a3`. Spelt as
| the arithmetic so the stride and the register file cannot disagree about how wide a row is.
    .equ WORKSPACE_ROW_BYTES, (SCROLL_COLUMN_ROW_LONGS * 4)

| ---- the C stack frame ---------------------------------------------------------------------------
| SAVED is what the prologue's movem pushes: d2-d7 and a2-a6, the callee-saved registers this body
| clobbers (a5 and a6 among them — the original uses both as cursors). FRAME is the one slot the
| in-loop tile-set base lives in. Every argument offset is measured past BOTH, so none of the three
| can drift apart.
    .equ SAVED,          (11 * 4)
    .equ FRAME,          4
| ZERO, so the per-tile-row reload assembles to `movea.l (%sp),%a1` and stays cycle-neutral against
| the `lea $4b3be.l,a1` it replaces — see the header. A second frame slot would have to go ABOVE it.
    .equ FRAME_TILE_SET, 0                      | image + A_tile_set_base, formed once
    .equ ARG_IMAGE,       4 + SAVED + FRAME
    .equ ARG_SCREEN_EDGE, 8 + SAVED + FRAME
    .equ ARG_PAGE,       12 + SAVED + FRAME
    .equ ARG_MAP_COLUMN, 16 + SAVED + FRAME

| ---- the four arms, as two macros ----------------------------------------------------------------
| The original writes the eight-row body out four times over — near tile flipped or not, crossed with
| far tile flipped or not — so that each cursor is a straight `(aN)+` or a `lea 56` start with a
| `lea -8` step and the inner loop needs no test. These macros emit exactly those four arms, arm for
| arm; they are one text rather than four so the transcription cannot drift between them, NOT a
| collapse of the four into one runtime-tested body, which would change both the sequence and its
| cost.

| An arm's head: scale both map words to tile addresses, and start each flipped side at its last row.
| The masking is the original's — each arm masks only the side whose bit 15 it has just branched on,
| the other side's being known clear.
.macro TILE_ARM_HEAD near_flip, far_flip
    .if \near_flip
    and.w   #SCROLL_TILE_INDEX_MASK,%d0
    .endif
    .if \far_flip
    and.w   #SCROLL_TILE_INDEX_MASK,%d1
    .endif
    lsl.l   #TILE_INDEX_SHIFT,%d0
    lsl.l   #TILE_INDEX_SHIFT,%d1
    movea.l FRAME_TILE_SET(%sp),%a1           | the original's `lea $4b3be.l,a1` — see the header
    movea.l %a1,%a2
    adda.l  %d0,%a1
    adda.l  %d1,%a2
    .if \near_flip
    lea     SCROLL_TILE_LAST_ROW(%a1),%a1
    .endif
    .if \far_flip
    lea     SCROLL_TILE_LAST_ROW(%a2),%a2
    .endif
.endm

| One pixel row, written three times over: the near tile's four plane words go to the screen's edge
| column and to the page's column as one 16-pixel cell, then the far tile's row is read and the two
| are packed into the workspace as `near : far` longwords. THE ORDER IS THE ORIGINAL'S ORDER — the
| near row's two destinations are both written before the far row is read at all.
.macro TILE_ROW near_flip, far_flip
    .if \near_flip
    movem.w (%a1),%d0-%d3                     | flipped: read in place, then step back a row
    lea     -SCROLL_TILE_ROW_BYTES(%a1),%a1
    .else
    movem.w (%a1)+,%d0-%d3
    .endif
    movem.w %d0-%d3,(%a0)                     | the screen's right-edge column
    lea     SCREEN_ROW_BYTES(%a0),%a0
    movem.w %d0-%d3,(%a5)                     | the page's own column
    lea     SCREEN_ROW_BYTES(%a5),%a5
    .if \far_flip
    movem.w (%a2),%d4-%d7
    lea     -SCROLL_TILE_ROW_BYTES(%a2),%a2
    .else
    movem.w (%a2)+,%d4-%d7
    .endif
    swap    %d0                               | the near word up into the high half...
    swap    %d1
    swap    %d2
    swap    %d3
    move.w  %d4,%d0                           | ...and the far word into the low
    move.w  %d5,%d1
    move.w  %d6,%d2
    move.w  %d7,%d3
    movem.l %d0-%d3,(%a3)
    lea     WORKSPACE_ROW_BYTES(%a3),%a3
.endm

| An arm entire: its head, its eight unrolled rows, and the outer loop's own tail.
.macro TILE_ARM near_flip, far_flip
    TILE_ARM_HEAD \near_flip, \far_flip
    .rept SCROLL_TILE_PIXEL_ROWS
    TILE_ROW \near_flip, \far_flip
    .endr
    move.l  %a4,%d0                           | the tile-row count back out of a4
    dbf     %d0,.Ltile_row
    TILE_EPILOGUE
.endm

| ---- prologue / epilogue -------------------------------------------------------------------------
| Bind the C arguments to the original's register convention. Each offset argument is added to the
| image base once here, and the body from `.Lentry` on is then the original's own code working on
| absolute addresses exactly as it always did.
.macro TILE_PROLOGUE
    movem.l %d2-%d7/%a2-%a6,-(%sp)
    lea     -FRAME(%sp),%sp
    movea.l ARG_IMAGE(%sp),%a1                | the image base, for this prologue only
    movea.l ARG_SCREEN_EDGE(%sp),%a0
    adda.l  %a1,%a0
    movea.l ARG_PAGE(%sp),%a5
    adda.l  %a1,%a5
    movea.l ARG_MAP_COLUMN(%sp),%a6
    adda.l  %a1,%a6
    | None of the three global addresses fits a 16-bit displacement, so each is formed the long way.
    | a2 is scratch until the first arm head overwrites it; the tile-set base outlives the prologue
    | and so goes to the frame slot.
    movea.l %a1,%a2
    adda.l  #A_tile_set_base,%a2
    move.l  %a2,FRAME_TILE_SET(%sp)
    movea.l %a1,%a2
    adda.l  #A_scroll_prefill_hide_screen,%a2
.endm

| d0 is the return value and a6 the map cursor, so the offset is taken back BEFORE the frame and the
| saved file come off the stack — ARG_IMAGE is measured from the frame that is still standing.
.macro TILE_EPILOGUE
    move.l  %a6,%d0
    sub.l   ARG_IMAGE(%sp),%d0
    lea     FRAME(%sp),%sp
    movem.l (%sp)+,%d2-%d7/%a2-%a6
    rts
.endm

| ---- scroll_emit_tile_column_asm — the original @ 0x162c2 ----------------------------------------
    .globl  scroll_emit_tile_column_asm
scroll_emit_tile_column_asm:
    TILE_PROLOGUE
.Lentry:
    tst.b   (%a2)                             | 0x162c2 tst.b $19ac1.l
    beq.w   .Lworkspace                       | 0x162c8 beq.w $162ce
    movea.l %a5,%a0                           | 0x162cc: prefill — the column goes into the page twice
.Lworkspace:
    movea.l %a1,%a3                           | 0x162ce lea $19fae.l,a3
    adda.l  #A_scroll_col_workspace,%a3
    moveq   #MAP_ROWS - 1,%d0                 | 0x162d4 moveq #$11,d0
.Ltile_row:
    movea.l %d0,%a4                           | 0x162d6: park the count where the movem cannot reach it
    moveq   #0,%d0                            | 0x162d8: so the map word indexes as an UNSIGNED 16 bits
    moveq   #0,%d1                            | 0x162da
    move.w  (%a6)+,%d0                        | 0x162dc: this column's word, and on to the next row
    bmi.w   .Lnear_flipped                    | 0x162de bmi.w $16642
    move.w  SCROLL_MAP_PEEK_NEXT(%a6),%d1     | 0x162e2: the SAME row of the next map column
    bmi.w   .Lfar_flipped                     | 0x162e6 bmi.w $16482
    TILE_ARM 0, 0                             | 0x162ea .. 0x16480

.Lfar_flipped:
    TILE_ARM 0, 1                             | 0x16482 .. 0x16640

.Lnear_flipped:
    move.w  SCROLL_MAP_PEEK_NEXT(%a6),%d1     | 0x16642
    bmi.w   .Lboth_flipped                    | 0x16646 bmi.w $1680a
    TILE_ARM 1, 0                             | 0x1664a .. 0x16808

.Lboth_flipped:
    TILE_ARM 1, 1                             | 0x1680a .. 0x169f0
