| scroll_emit.S — asm twins for the two column emitters, TRANSCRIBED from the original binary.
|
|   scroll_emit_column_shift2_asm  <- the original @ 0x169f2, the C reference scroll_emit_column_shift2
|   scroll_emit_column_shift0_asm  <- the original @ 0x16a56, the C reference scroll_emit_column_shift0
|
| WHAT A TWIN IS, and why it is 1.00x by construction: the C in ../scroll.c is byte-for-byte
| equivalent to the original (test/test_scroll.py's differential vs the Musashi oracle), and the
| original's own instructions are in ../../out/prg_dis.txt. So the fast version of this routine is
| not something to invent — it is something to COPY. Everything between the prologue and the
| epilogue below is the original's instruction sequence in order, and the only judgement exercised
| was how to translate its two register conventions (see the next two blocks). See src/asm/README.md.
|
| THE C ABI. The twin carries the SAME signature as the core it replaces, because ../frame.c and
| ../init.c call it through the ZY_SCROLL() seam in ../../include/scroll.h and must not care which
| they got:
|
|   void scroll_emit_column_shift2(uint8_t *image, uint32_t workspace, uint32_t page, uint32_t edge);
|
| THE IMAGE BASE. The original IS the image, so it addresses the game's globals absolutely
| (`tst.b $19ac1.l`) and receives its three cursors as absolute addresses in a0/a1/a2. The
| reconstruction addresses everything as an OFFSET from `image`, which on the target build is a real
| pointer to the staged program. The prologue is the whole of that translation: each offset argument
| is added to the image base once, and the body from `.Lentry` on is then the original's own code
| working on absolute addresses exactly as it always did.
|
| THE PASS LOOP IS THE ORIGINAL'S OWN BYTES, and that is a test rather than a claim. Only the two
| entry instructions needed translating (`tst.b $19ac1.l` -> `tst.b (%a3)`), so from the pass counter
| at 0x169fe / 0x16a62 through the `dbf` the twin assembles byte-for-byte to what the original holds
| there — the `dbf` displacement included, the loop shape being identical. The `_body` / `_body_end`
| labels bracket that span and test_asm_scroll.py::test_the_twins_transcribe_the_original compares it
| against the .PRG. Only the prologue, the two translated instructions and the epilogue sit outside.
|
| REGISTERS. The original's, unchanged through the body:
|   a0 = the workspace cursor (32 bytes a pass)   a1 = the page cursor       a2 = the edge cursor
|   a3 = &image[A_scroll_prefill_hide_screen] (the twin's; the original had the address inline)
|   a4 = the pass counter parked across the movem that clobbers d0
|   d0-d7 = one workspace cell: two screen rows of four planes, 32 pixels wide
|
| WHAT `swap` + `movem.w` IS DOING, because it reads as a no-op pair otherwise: each longword holds
| `this column : the next column along`, and only the HIGH half is on screen. `movem.w` stores the
| LOW word of each register, so the `swap` before it is what selects the visible half.

    .text

| ---- constants: ../../include/scroll.h's and ../../include/video.h's, by their names there --------
| test_constants.py::test_asm_twin_equates_match_the_headers pins every one of these against the
| header that owns it, so a value that moved there cannot go on living here.
    .equ A_scroll_prefill_hide_screen, 0x19ac1  | non-zero: emit the edge column into the page instead
    .equ SCROLL_COLUMN_PASSES,         72       | two screen rows a pass, 144 rows in all
    .equ SCROLL_COLUMN_SHIFT_BITS,     2        | the 2-pixel step one frame of scroll advances by
    .equ SCREEN_ROW_BYTES,             160

| One workspace cell = SCROLL_COLUMN_CELL_LONGS longs, which is what d0-d7 hold and what a pass
| steps over. Spelt as the arithmetic rather than as 32 so the `lea` and the register file cannot
| disagree about how wide a cell is.
    .equ SCROLL_COLUMN_CELL_LONGS,     8
    .equ CELL_BYTES, (SCROLL_COLUMN_CELL_LONGS * 4)

| ---- the C stack frame ---------------------------------------------------------------------------
| SAVED is what the prologue's movem pushes: d2-d7 and a2-a4, the callee-saved registers this body
| clobbers. Every argument offset is measured past it, so the two can never drift apart.
    .equ SAVED,       (9 * 4)
    .equ ARG_IMAGE,     4 + SAVED
    .equ ARG_WORKSPACE, 8 + SAVED
    .equ ARG_PAGE,     12 + SAVED
    .equ ARG_EDGE,     16 + SAVED

| Bind the C arguments to the original's register convention. Shared by both emitters, which is all
| that is shared: the two bodies below are written out separately because the original writes them
| out separately, at two entry points, and a transcription follows the thing it transcribes. They
| differ by more than a shift count anyway — `_shift2` has the eight `lsl.l`, the `movem.l` write-back
| AND its own `lea` placement — so a `.if`-parameterised body would be a rewrite, not a copy.
| (`scroll_tile.S` DOES parameterise, because there the original's four arms really are one body with
| two flags; the test is what the original does, not what would be tidier here.)
.macro EMIT_PROLOGUE
    movem.l %d2-%d7/%a2-%a4,-(%sp)
    movea.l ARG_IMAGE(%sp),%a4                | the image base, for this prologue only
    movea.l ARG_WORKSPACE(%sp),%a0
    adda.l  %a4,%a0
    movea.l ARG_PAGE(%sp),%a1
    adda.l  %a4,%a1
    movea.l ARG_EDGE(%sp),%a2
    adda.l  %a4,%a2
    | The flag's address does not fit a 16-bit displacement, so it is formed once here rather than
    | recomputed inside the loop the original tests it outside of.
    movea.l %a4,%a3
    adda.l  #A_scroll_prefill_hide_screen,%a3
.endm

.macro EMIT_EPILOGUE
    movem.l (%sp)+,%d2-%d7/%a2-%a4
    rts
.endm

| ---- scroll_emit_column_shift2_asm — the original @ 0x169f2 ---------------------------------------
    .globl  scroll_emit_column_shift2_asm
scroll_emit_column_shift2_asm:
    EMIT_PROLOGUE
    tst.b   (%a3)                            | 0x169f2 tst.b $19ac1.l
    beq.w   .L2_pass                        | 0x169f8 beq.w $169fe
    movea.l %a1,%a2                           | 0x169fc: prefill — the edge column goes into the page
    .globl  scroll_emit_column_shift2_body
.L2_pass:
scroll_emit_column_shift2_body:              | from here on, the original's own bytes — see the pin
    moveq   #SCROLL_COLUMN_PASSES - 1,%d0    | 0x169fe moveq #$47,d0
.L2_loop:
    movea.l %d0,%a4                           | 0x16a00: park the count where the movem cannot reach it
    movem.l (%a0),%d0-%d7                      | 0x16a02: one cell — two rows of four planes
    lsl.l   #SCROLL_COLUMN_SHIFT_BITS,%d0    | 0x16a06 .. 0x16a14: walk the far column two pixels in
    lsl.l   #SCROLL_COLUMN_SHIFT_BITS,%d1
    lsl.l   #SCROLL_COLUMN_SHIFT_BITS,%d2
    lsl.l   #SCROLL_COLUMN_SHIFT_BITS,%d3
    lsl.l   #SCROLL_COLUMN_SHIFT_BITS,%d4
    lsl.l   #SCROLL_COLUMN_SHIFT_BITS,%d5
    lsl.l   #SCROLL_COLUMN_SHIFT_BITS,%d6
    lsl.l   #SCROLL_COLUMN_SHIFT_BITS,%d7
    movem.l %d0-%d7,(%a0)                      | 0x16a16: the shifted cell goes back for the next frame
    lea     CELL_BYTES(%a0),%a0               | 0x16a1a lea 32(a0),a0
    swap    %d0                              | 0x16a1e .. 0x16a2c: bring the visible half down
    swap    %d1
    swap    %d2
    swap    %d3
    swap    %d4
    swap    %d5
    swap    %d6
    swap    %d7
    movem.w %d0-%d3,(%a1)                      | 0x16a2e: row 2n — four planes into the page
    movem.w %d0-%d3,(%a2)                      | 0x16a32: ...and into the screen's right-edge column
    lea     SCREEN_ROW_BYTES(%a1),%a1         | 0x16a36
    lea     SCREEN_ROW_BYTES(%a2),%a2         | 0x16a3a
    movem.w %d4-%d7,(%a1)                      | 0x16a3e: row 2n + 1
    movem.w %d4-%d7,(%a2)                      | 0x16a42
    lea     SCREEN_ROW_BYTES(%a1),%a1         | 0x16a46
    lea     SCREEN_ROW_BYTES(%a2),%a2         | 0x16a4a
    move.l  %a4,%d0                           | 0x16a4e: the count back out of a4
    dbf     %d0,.L2_loop                     | 0x16a50 dbf d0,$16a00
    .globl  scroll_emit_column_shift2_body_end
scroll_emit_column_shift2_body_end:
    EMIT_EPILOGUE                           | 0x16a54 rts

| ---- scroll_emit_column_shift0_asm — the original @ 0x16a56 ---------------------------------------
| The same body with the shift-and-write-back step absent: the scroller uses it while the scroll is
| frozen, so the workspace is emitted as it stands and left alone.
    .globl  scroll_emit_column_shift0_asm
scroll_emit_column_shift0_asm:
    EMIT_PROLOGUE
    tst.b   (%a3)                            | 0x16a56 tst.b $19ac1.l
    beq.w   .L0_pass                        | 0x16a5c beq.w $16a62
    movea.l %a1,%a2                           | 0x16a60
    .globl  scroll_emit_column_shift0_body
.L0_pass:
scroll_emit_column_shift0_body:              | from here on, the original's own bytes — see the pin
    moveq   #SCROLL_COLUMN_PASSES - 1,%d0    | 0x16a62 moveq #$47,d0
.L0_loop:
    movea.l %d0,%a4                           | 0x16a64
    movem.l (%a0),%d0-%d7                      | 0x16a66
    lea     CELL_BYTES(%a0),%a0               | 0x16a6a
    swap    %d0                              | 0x16a6e .. 0x16a7c
    swap    %d1
    swap    %d2
    swap    %d3
    swap    %d4
    swap    %d5
    swap    %d6
    swap    %d7
    movem.w %d0-%d3,(%a1)                      | 0x16a7e
    movem.w %d0-%d3,(%a2)                      | 0x16a82
    lea     SCREEN_ROW_BYTES(%a1),%a1         | 0x16a86
    lea     SCREEN_ROW_BYTES(%a2),%a2         | 0x16a8a
    movem.w %d4-%d7,(%a1)                      | 0x16a8e
    movem.w %d4-%d7,(%a2)                      | 0x16a92
    lea     SCREEN_ROW_BYTES(%a1),%a1         | 0x16a96
    lea     SCREEN_ROW_BYTES(%a2),%a2         | 0x16a9a
    move.l  %a4,%d0                           | 0x16a9e
    dbf     %d0,.L0_loop                     | 0x16aa0 dbf d0,$16a64
    .globl  scroll_emit_column_shift0_body_end
scroll_emit_column_shift0_body_end:
    EMIT_EPILOGUE                           | 0x16aa4 rts
