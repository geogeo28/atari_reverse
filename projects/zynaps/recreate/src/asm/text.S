| text.S — asm twins for the score panel and the character blitter it ends in, TRANSCRIBED from the
| original binary.
|
|   draw_score_panel_asm  <- the original @ 0x136c8, the C reference draw_score_panel (../hud.c)
|   draw_bcd_number_asm   <- the original @ 0x136f6, the C reference draw_bcd_number (../text.c)
|   draw_char_asm         <- the original @ 0x13710, the C reference draw_char (../text.c)
|
| WHAT A TWIN IS is written out in scroll_emit.S and in README.md beside it, and holds here word for
| word. Everything from `.Lpanel` on is the original's instruction sequence in order; the only
| judgement exercised was how to translate its register and addressing conventions into the C ABI.
|
| THE THREE ARE ONE PIECE OF CODE, and that is why they share a file rather than sit in three.
| 0x136c8 has NO `rts`: it sets up 0x136f6's arguments and RUNS OFF ITS OWN END into it, and 0x136f6
| reaches the character blitter by a `bsr` twelve bytes further on. The twin keeps all of that — the
| fall-through is a fall-through and the `bsr` is a `bsr`, at the same displacement — so the eight
| digits of a score cost eight PLAIN subroutine calls here, not eight C calls with a `movem` pair
| each. That is most of what this twin is worth: the C had to spend a whole C-ABI call per digit
| where the original spends 18 cycles.
|
| THE C ABI. Each entry point carries the SAME signature as the core it replaces, because ../frame.c,
| ../hud.c and ../highscore.c reach it through the ZY_TEXT() seam in ../../include/text.h and
| ../../include/hud.h:
|
|   void draw_score_panel(uint8_t *image, uint32_t buffer);
|   void draw_bcd_number(uint8_t *image, uint32_t row_base, uint16_t rightmost_column,
|                        uint32_t digits);
|   void draw_char(uint8_t *image, uint32_t row_base, uint16_t column, uint16_t character);
|
| A `uint16_t` argument still occupies a whole four-byte stack slot, so those are read as the LOW
| WORD of their slot — the same truncation the C cores perform.
|
| THE `bsr` BRACKET is sprite.S's, for the same reason: `draw_char` returns from two places
| (0x1379c and 0x137c8) and `draw_score_panel` from neither of its own. Each wrapper CALLS the body,
| so the original's own `rts` instructions are what return, and no rejection path had to be rewritten
| into a branch.
|
| THE IMAGE BASE lives in %a5 throughout, because that is the one register none of the three bodies
| touches — 0x136d6's `movem.l` alone claims d1-d7 and a0-a2. Four absolute references need it:
|
|   lea    $6c72e.l,a4   (panel, entry)          -> A_score_panel_strip, hoisted to the prologue
|   move.l $195e0.l,d6   (panel, once)           -> A_player_score_bcd's stored longword
|   lea    $198d6.l,a1   (char, once, non-letter)-> A_char_to_glyph_table
|   lea    $6be6e.l,a1   (char, once)            -> A_font_glyphs
|
| Each costs 8 cycles more than the `lea abs.l` it replaces (`movea.l An,An` plus `adda.l #imm,An` is
| 20 where a `lea abs.l,An` is 12); the score's longword costs 12 more, needing an address register
| formed for it.
|
| TWO OF THEM ARE INSIDE THE DIGIT LOOP, which is worth stating plainly because it is where most of
| the panel's excess is. `.Lchar` is reached once per digit through `.Lbcd`'s `dbf`, and a BCD digit
| (0x30-0x3f, below CHAR_FIRST_LETTER) takes the TABLE arm and then falls into the GLYPH arm — so it
| pays both, 16 cycles a digit, 128 of the panel's 336-cycle excess. Measured: a letter costs the twin
| +198 and a digit +206.
|
| THEY ARE LEFT WHERE THE ORIGINAL FORMS THEM ANYWAY. Hoisting the font base into one of the registers
| that is dead here would save ~108 cycles a panel — 0.03% of a 417,000-cycle frame — at the price
| of a third entry convention for `.Lchar`, a register the standalone entry would have to save, and a
| reload CHEAPER than the `lea` it stands for. src/asm/README.md's rule is that a substitution goes
| where its original stands; the gain here does not come close to buying an exception.
|
| WHAT IS BYTE-PINNED, AND WHAT IS NOT. As in sprite.S: the original's assembler encoded
| `and.w #imm,Dn` / `cmp.b #imm,Dn` / `add.w #imm,Dn` as the immediate-EA forms and gas spells them
| ANDI/CMPI/ADDI — same length, same cycles, a different opcode word. So the three DISPATCH
| prologues cannot be byte-equal; the three ROW LOOPS can, and are (test_asm_text.py compares each
| against the .PRG). Those loops are where a panel's cycles are: eight `movem` rows for the strip,
| and eight four-plane rows for each of the eight digits.
|
| REGISTERS. The original's, unchanged through the bodies:
|   draw_score_panel   a6 = the destination buffer (in)   a3 = its strip cursor
|                      a4 = the strip source              d0 = the row counter
|                      d1-d7/a0-a2 = one 40-byte strip row, in flight between two `movem`s
|   draw_bcd_number    a0 = the row's base   d1 = the column, stepping left   d6 = the BCD longword
|                      d7 = the digit counter
|   draw_char          a0 = the cell, saved and restored across the call   a1 = the glyph cursor
|                      d0 = the character then the glyph number   d1/d4 = the column
|                      d3 = one plane byte   d5 = the row's mask   d7 = the fill arms' row counter
|   %a5 = the image base (the twin's; the original had every address inline)

    .text

| ---- constants: ../../include/{hud,text,score,video}.h's, by their names there --------------------
| test_constants.py::test_asm_twin_equates_match_the_headers pins every one of these against the
| header that owns it, so a value that moved there cannot go on living here.
    .equ A_score_panel_strip,     0x6c72e  | 8 rows x 40 bytes, carved from the stamped panel image
    .equ A_player_score_bcd,      0x195e0  | .l — the packed-BCD score
    .equ A_font_glyphs,           0x6be6e  | 8 rows of {mask, plane0..3} a glyph
    .equ A_char_to_glyph_table,   0x198d6  | one glyph index per character from CHAR_MAP_FIRST up

    .equ PANEL_STRIP_ROWS,             8
    .equ SCORE_STRIP_OFFSET,      0x5ed8   | row 151, byte 120 — where the SCORE strip lands
    .equ SCORE_DIGITS_OFFSET,     0x5e60   | row 151, byte 0 — the digits take the ROW's base
    .equ SCORE_RIGHTMOST_COLUMN,  0x26

    .equ BCD_DIGITS,                   8
    .equ BCD_DIGIT_MASK,             0xf
    .equ CHAR_DIGIT_ZERO,           0x30

    .equ CHAR_SPACE,                0x20   | a no-op, not a cleared cell
    .equ CHAR_CLEAR_CELL,              1
    .equ CHAR_FILL_CELL,               2
    .equ CELL_CLEAR_BYTE,           0x00
    .equ CELL_FILL_BYTE,            0xff
    .equ CHAR_FIRST_LETTER,         0x41
    .equ LETTER_GLYPH_BIAS,         0x37
    .equ CHAR_MAP_FIRST,            0x20
    .equ COLUMN_PAIR_MASK,        0xfffe
    .equ COLUMN_PAIR_SHIFT,            2
    .equ COLUMN_ODD_BIT,               1
    .equ GLYPH_BYTES,             0x28
    .equ GLYPH_ROWS,                   8
    .equ PLANE_STRIDE,                 2   | (a0) / 2(a0) / 4(a0) / 6(a0)

    .equ SCREEN_ROW_BYTES,           160

| ---- the three C entry points ---------------------------------------------------------------
| ALL THREE WRAPPERS COME FIRST and the three bodies follow CONTIGUOUSLY, because the panel body
| ends by falling off its own end into the digit body exactly as the original does. A wrapper laid
| between them would be what the fall-through landed in.

| draw_score_panel @ 0x136c8. The strip loop's `movem.l` claims d1-d7 and a0-a2, so this entry saves
| the whole callee-saved file; every argument offset is measured past it.
    .equ PANEL_SAVED,      (11 * 4)
    .equ PANEL_ARG_IMAGE,     4 + PANEL_SAVED
    .equ PANEL_ARG_BUFFER,    8 + PANEL_SAVED

    .globl  draw_score_panel_asm
draw_score_panel_asm:
    movem.l %d2-%d7/%a2-%a6,-(%sp)
    movea.l PANEL_ARG_IMAGE(%sp),%a5          | the image base, live through the digits and the font
    movea.l PANEL_ARG_BUFFER(%sp),%a6         | the destination buffer, as an offset...
    adda.l  %a5,%a6                           | ...made absolute
    movea.l %a5,%a4                           | 0x136c8 lea $6c72e.l,a4
    adda.l  #A_score_panel_strip,%a4
    bsr.w   .Lpanel                           | the fall-through's own `rts` returns HERE
    movem.l (%sp)+,%d2-%d7/%a2-%a6
    rts

| draw_bcd_number @ 0x136f6.
    .equ BCD_SAVED,          (6 * 4)
    .equ BCD_ARG_IMAGE,     4 + BCD_SAVED
    .equ BCD_ARG_ROW_BASE,  8 + BCD_SAVED
    .equ BCD_ARG_COLUMN,   12 + BCD_SAVED
    .equ BCD_ARG_DIGITS,   16 + BCD_SAVED

    .globl  draw_bcd_number_asm
draw_bcd_number_asm:
    movem.l %d3-%d7/%a5,-(%sp)
    movea.l BCD_ARG_IMAGE(%sp),%a5
    movea.l BCD_ARG_ROW_BASE(%sp),%a0
    adda.l  %a5,%a0
    move.w  BCD_ARG_COLUMN + 2(%sp),%d1       | the LOW word of the slot
    move.l  BCD_ARG_DIGITS(%sp),%d6
    bsr.w   .Lbcd
    movem.l (%sp)+,%d3-%d7/%a5
    rts

| draw_char @ 0x13710.
    .equ CHAR_SAVED,           (5 * 4)
    .equ CHAR_ARG_IMAGE,      4 + CHAR_SAVED
    .equ CHAR_ARG_ROW_BASE,   8 + CHAR_SAVED
    .equ CHAR_ARG_COLUMN,    12 + CHAR_SAVED
    .equ CHAR_ARG_CHARACTER, 16 + CHAR_SAVED

    .globl  draw_char_asm
draw_char_asm:
    movem.l %d3-%d5/%d7/%a5,-(%sp)
    movea.l CHAR_ARG_IMAGE(%sp),%a5
    movea.l CHAR_ARG_ROW_BASE(%sp),%a0
    adda.l  %a5,%a0
    move.w  CHAR_ARG_COLUMN + 2(%sp),%d1
    move.w  CHAR_ARG_CHARACTER + 2(%sp),%d0
    bsr.w   .Lchar
    movem.l (%sp)+,%d3-%d5/%d7/%a5
    rts

| ============================================================== draw_score_panel @ 0x136c8 ========
.Lpanel:
    movea.l %a6,%a3                           | 0x136ce
    lea     SCORE_STRIP_OFFSET(%a3),%a3       | 0x136d0
    moveq   #PANEL_STRIP_ROWS - 1,%d0         | 0x136d4

    .globl  draw_score_panel_strip_body
draw_score_panel_strip_body:                  | from here on, the original's own bytes — see the pin
.Lpanel_row:
    movem.l (%a4)+,%d1-%d7/%a0-%a2            | 0x136d6: one 40-byte strip row, in ten registers
    movem.l %d1-%d7/%a0-%a2,(%a3)             | 0x136da
    lea     SCREEN_ROW_BYTES(%a3),%a3         | 0x136de
    dbf     %d0,.Lpanel_row                   | 0x136e2
    .globl  draw_score_panel_strip_body_end
draw_score_panel_strip_body_end:

    movea.l %a6,%a0                           | 0x136e6
    lea     SCORE_DIGITS_OFFSET(%a0),%a0      | 0x136e8
    move.w  #SCORE_RIGHTMOST_COLUMN,%d1       | 0x136ec
    movea.l %a5,%a1                           | 0x136f0 move.l $195e0.l,d6 — a1 is dead here, the
    adda.l  #A_player_score_bcd,%a1           |         strip row it held having been stored already
    move.l  (%a1),%d6
                                              | ...and runs off its own end into draw_bcd_number,
                                              |    exactly as the original does at 0x136f6

| =============================================================== draw_bcd_number @ 0x136f6 ========
.Lbcd:
    moveq   #BCD_DIGITS - 1,%d7               | 0x136f6: a fixed eight, so a score of 0 draws eight
.Lbcd_digit:                                  |          zeroes rather than one
    move.b  %d6,%d0                           | 0x136f8
    and.w   #BCD_DIGIT_MASK,%d0               | 0x136fa
    add.w   #CHAR_DIGIT_ZERO,%d0              | 0x136fe
    bsr.w   .Lchar                            | 0x13702: the original's own `bsr`, at its own
    lsr.l   #4,%d6                            | 0x13706  displacement — see the file header
    subq.w  #1,%d1                            | 0x13708: the column steps LEFT
    dbf     %d7,.Lbcd_digit                   | 0x1370a
    rts                                       | 0x1370e

| ==================================================================== draw_char @ 0x13710 =========
.Lchar:
    move.l  %a0,-(%sp)                        | 0x13710: the row base comes back untouched, which is
    cmp.b   #CHAR_SPACE,%d0                   | 0x13712  what lets draw_bcd_number step the column
    beq.w   .Lchar_done                       | 0x13716: a SPACE leaves whatever was under it
    move.w  %d1,%d4                           | 0x1371a
    and.w   #COLUMN_PAIR_MASK,%d1             | 0x1371c
    lsl.w   #COLUMN_PAIR_SHIFT,%d1            | 0x13720
    adda.w  %d1,%a0                           | 0x13722
    move.w  %d4,%d1                           | 0x13724
    and.w   #COLUMN_ODD_BIT,%d1               | 0x13726: +1 byte for the right-hand cell of a pair
    adda.w  %d1,%a0                           | 0x1372a
    move.w  %d4,%d1                           | 0x1372c
    cmp.b   #CHAR_CLEAR_CELL,%d0              | 0x1372e
    beq.w   .Lchar_clear                      | 0x13732
    cmp.b   #CHAR_FILL_CELL,%d0               | 0x13736
    beq.w   .Lchar_fill                       | 0x1373a
    cmp.w   #CHAR_FIRST_LETTER,%d0            | 0x1373e: a SIGNED word compare
    blt.w   .Lchar_from_table                 | 0x13742
    sub.w   #LETTER_GLYPH_BIAS,%d0            | 0x13746
    bra.w   .Lchar_glyph                      | 0x1374a
.Lchar_from_table:
    movea.l %a5,%a1                           | 0x1374e lea $198d6.l,a1
    adda.l  #A_char_to_glyph_table,%a1
    sub.w   #CHAR_MAP_FIRST,%d0               | 0x13754
    move.b  (%a1,%d0.w),%d0                   | 0x13758
    ext.w   %d0                               | 0x1375c
.Lchar_glyph:
    movea.l %a5,%a1                           | 0x1375e lea $6be6e.l,a1
    adda.l  #A_font_glyphs,%a1
    mulu.w  #GLYPH_BYTES,%d0                  | 0x13764
    adda.w  %d0,%a1                           | 0x13768
    moveq   #GLYPH_ROWS - 1,%d4               | 0x1376a

    .globl  draw_char_glyph_body
draw_char_glyph_body:                         | from here on, the original's own bytes — see the pin
.Lchar_row:
    move.b  (%a1)+,%d5                        | 0x1376c: the row's mask
    and.b   %d5,(%a0)                         | 0x1376e
    move.b  (%a1)+,%d3                        | 0x13770
    or.b    %d3,(%a0)                         | 0x13772: the AND and the OR are two separate stores
    and.b   %d5,PLANE_STRIDE(%a0)             | 0x13774
    move.b  (%a1)+,%d3                        | 0x13778
    or.b    %d3,PLANE_STRIDE(%a0)             | 0x1377a
    and.b   %d5,2 * PLANE_STRIDE(%a0)         | 0x1377e
    move.b  (%a1)+,%d3                        | 0x13782
    or.b    %d3,2 * PLANE_STRIDE(%a0)         | 0x13784
    and.b   %d5,3 * PLANE_STRIDE(%a0)         | 0x13788
    move.b  (%a1)+,%d3                        | 0x1378c
    or.b    %d3,3 * PLANE_STRIDE(%a0)         | 0x1378e
    lea     SCREEN_ROW_BYTES(%a0),%a0         | 0x13792
    dbf     %d4,.Lchar_row                    | 0x13796
.Lchar_done:
    movea.l (%sp)+,%a0                        | 0x1379a
    rts                                       | 0x1379c
    .globl  draw_char_glyph_body_end
draw_char_glyph_body_end:

.Lchar_fill:
    move.b  #CELL_FILL_BYTE,%d0               | 0x1379e: character 2 — the name-entry block cursor
    move.w  #GLYPH_ROWS - 1,%d7               | 0x137a2: NOT `moveq`, and it clobbers draw_bcd_number's
    bra.w   .Lchar_fill_rows                  | 0x137a6  own counter — unreachable from a BCD digit
.Lchar_clear:
    clr.b   %d0                               | 0x137aa: character 1 — the cleared cell
    move.w  #GLYPH_ROWS - 1,%d7               | 0x137ac

    .globl  draw_char_fill_body
draw_char_fill_body:                          | from here on, the original's own bytes — see the pin
.Lchar_fill_rows:
    move.b  %d0,(%a0)                         | 0x137b0
    move.b  %d0,PLANE_STRIDE(%a0)             | 0x137b2
    move.b  %d0,2 * PLANE_STRIDE(%a0)         | 0x137b6
    move.b  %d0,3 * PLANE_STRIDE(%a0)         | 0x137ba
    lea     SCREEN_ROW_BYTES(%a0),%a0         | 0x137be
    dbf     %d7,.Lchar_fill_rows              | 0x137c2
    movea.l (%sp)+,%a0                        | 0x137c6
    rts                                       | 0x137c8
    .globl  draw_char_fill_body_end
draw_char_fill_body_end:

| CELL_CLEAR_BYTE is what `clr.b %d0` at 0x137aa writes; it is `.equ`-ed rather than left in a comment
| so that test_constants.py pins it against include/text.h's own definition of the same name.
