| sprite.S — asm twins for the two masked sprite blitters, TRANSCRIBED from the original binary.
|
|   draw_sprite_masked_asm          <- the original @ 0x15ace, the C reference draw_sprite_masked
|   draw_sprite_masked_collide_asm  <- the original @ 0x15b7c, the C reference draw_sprite_masked_collide
|
| WHAT A TWIN IS is written out in scroll_emit.S and in README.md beside it, and holds here word for
| word: the C in ../sprite.c is byte-for-byte equivalent to the original (test/test_sprite.py's
| differential against the Musashi oracle), the original's own instructions are in
| ../../out/prg_dis.txt, and everything from `.Lmasked` / `.Lcollide` on is that instruction sequence
| in order. The only judgement exercised was how to translate the original's register and addressing
| conventions into the C ABI, and the four blocks below are the whole of it.
|
| THE C ABI. Each twin carries the SAME signature as the core it replaces, because ../frame.c,
| ../enemy.c, ../mothership.c and ../highscore.c reach it through the ZY_SPRITE() seam in
| ../../include/sprite.h and must not care which they got:
|
|   void draw_sprite_masked(uint8_t *image, uint32_t entity, uint16_t preshift_bytes_per_pixel);
|   void draw_sprite_masked_collide(uint8_t *image, uint32_t entity, uint32_t hit_flag);
|
| A `uint16_t` argument still occupies a whole four-byte stack slot (m68k-elf-gcc emits `pea` for
| one), so the twin reads its LOW WORD at MASKED_ARG_PRESHIFT + 2 — which is also the truncation the
| C core performs on the same value.
|
| THE `bsr` BRACKET, and why it is worth eighteen cycles. Both routines RETURN FROM SEVERAL PLACES
| (0x15ae0, 0x15aea, 0x15b08, 0x15b14, 0x15b7a for the first; 0x15bb6, 0x15bc2, 0x15c26, 0x15c34 and
| the three band tails for the second) — every clip rejection is its own `rts`. Replacing each with a
| branch to a shared epilogue would change the body's byte layout at nine places and put every branch
| displacement after them out of step with the original's. So the wrapper CALLS the body instead:
| each of the original's own `rts` instructions returns to the wrapper, which then unwinds the C
| frame. One `bsr.w` (18 cycles) buys byte-identical rejection paths and byte-identical row loops.
|
| THE IMAGE BASE, and the three substitutions it forces. The original IS the image, so it reads the
| framebuffer pointer and the keep-mask table absolutely and treats a record's sprite field as an
| absolute address. The reconstruction passes an image base and stores OFFSETS, so:
|
|   movea.l $1797e.l,a0   (entry, both)     -> A_screen_back's stored offset, plus the base
|   movea.l 10(a2),a1     (once per call)   -> ENTITY_SPRITE's stored offset, plus the base
|   lea     $1821e.l,a3   (collide, once)   -> A_shift_mask_table, formed in the prologue
|
| None of the three is inside a loop, so none of them costs a row anything. The first is hoisted into
| the prologue whole (four instructions where the original had one: +20 cycles a call). The other two
| are formed WHERE THE ORIGINAL FORMS THEM, each gaining 8 cycles in place (`movea.l An,An` plus
| `adda.l #imm,An` is 20 where a `lea abs.l,An` is 12).
|
| THE KEEP-MASK ONE WAS IN THE PROLOGUE FIRST, AND THAT WAS A DEFECT. 0x15c08 sits AFTER the two
| y-clip `rts`s at 0x15bb6 and 0x15bc2, so a sprite clipped off the top or bottom of the playfield
| never reaches it — and `frame_draw_objects_and_collide` calls this routine for every alive object
| every frame, so that path is not rare. Hoisting it made every such call pay 20 cycles the original
| does not (measured: a y-reject went 298 -> 622 where it should go 298 -> 602). Put a substitution
| where its original stands unless there is a reason it cannot go there; test_asm_sprite.py now clocks
| a REJECTION as well as a draw, which is the surface that would have caught this when it was written.
|
| WHAT THE COST BARS ARE, and why they are looser than the scroll wave's. A page blit is 110,000
| cycles a call, so its C-ABI prologue is 0.24% of it. These blitters are 1,000-8,000 cycles a call
| and the collide twin saves eleven callee-saved registers, so the same fixed cost is a few percent.
| The bars in test_asm_sprite.py are therefore set per case from the measurement, tight enough that
| ONE more register in either `movem` (16 cycles) reddens them, and no looser.
|
| WHAT IS BYTE-PINNED, AND WHAT IS NOT. The original's assembler encoded `and.w #imm,Dn`,
| `cmp.w #imm,Dn` and `sub.w #imm,Dn` as the AND/CMP/SUB-with-immediate-EA forms (0xc07c, 0xb07c,
| 0x907c); gas spells all three as ANDI/CMPI/SUBI. Same length, same cycle count, different opcode —
| so the CLIP PROLOGUES, which are nothing but immediate compares, cannot be byte-equal however
| faithfully they are transcribed. The FOUR ROW LOOPS can, and are: they contain no immediate-to-Dn
| operation at all, they are where every cycle of a real call goes, and test_asm_sprite.py compares
| each of them against the .PRG byte for byte. scroll_tile.S records the same gas encoding
| difference for the same reason.
|
| REGISTERS. The original's, unchanged through both bodies:
|   draw_sprite_masked          a0 = screen cursor  a1 = sprite cursor  a2 = the entity record
|                               a3 = the image base (the twin's; the original had it inline)
|                               d0 = x then scratch  d1 = y  d2 = rows, then the row count
|                               d3/d4/d7 = one screen cell's plane pairs  d5 = the hidden-row count
|   draw_sprite_masked_collide  a0 = screen cursor  a1 = sprite cursor  a2 = the entity record
|                               a3 = the keep-mask table, then a rotated-word scratch
|                               a4 = the image base until 0x15c58, then a rotated-word scratch
|                               a5 = the pixel-hit flag's address  a6 = the row count across the movem
|                               d0/d1 = the rotated sprite word and the plane pair it splits into
|                               d2-d5 = one screen row's two cells   d6/d7 = the keep mask and its
|                               complement, live across the whole call

    .text

| ---- constants: ../../include/{sprite,entity,collision,video}.h's, by their names there -----------
| test_constants.py::test_asm_twin_equates_match_the_headers pins every one of these against the
| header that owns it, so a value that moved there cannot go on living here.
    .equ A_screen_back,        0x1797e  | .l — the buffer being drawn into, as an image offset
    .equ A_shift_mask_table,   0x1821e  | the keep-mask that re-splits a rotated sprite word

    .equ ENTITY_X,                0x00  | .w signed
    .equ ENTITY_Y,                0x04  | .w signed
    .equ ENTITY_HEIGHT,           0x08  | .w — rows; bit 15 is a flag the collide arm masks off
    .equ ENTITY_SPRITE,           0x0a  | .l — an image offset to the preshift bank
    .equ ENTITY_HEIGHT_MASK,    0x7fff

    .equ SPRITE_X_EVEN_MASK,    0xfffe
    .equ SPRITE_X_PHASE_MASK,      0xf  | the pixel within the 16-pixel cell
    .equ SPRITE_X_CELL_MASK,    0xfff0  | ...and then `lsr.w #1` = the cell's byte offset
    .equ SPRITE_MASKED_ROW_BYTES,   10  | mask word + four plane words
    .equ SPRITE_CELL_BYTES,          8  | one 16-pixel four-plane screen cell
    .equ SPRITE_CELL_LONGS,          2  | ...read as planes 0+1, then planes 2+3
    .equ SPRITE_SHIFT_MASK_STRIDE,   2  | a WORD step into a table of longwords
    .equ SPRITE_COLLIDE_ROW_HALF_WORDS, 5   | half a one-cell masked row, per row of height
    .equ SPRITE_COLLIDE_ORIGIN_X, 0x40  | world x of screen column 0
    .equ SPRITE_COLLIDE_LEFT_EDGE, 0x30
    .equ SPRITE_COLLIDE_RIGHT_EDGE, 0x170
    .equ SPRITE_COLLIDE_RIGHT_OFF, 0x180

    .equ SCREEN_ROW_BYTES,         160
    .equ SCREEN_PIXELS_WIDE,       320
    .equ PLAYFIELD_TOP_Y,           32
    .equ PLAYFIELD_ROWS,           144
    .equ PLAYFIELD_BOTTOM_Y, (PLAYFIELD_TOP_Y + PLAYFIELD_ROWS)

| One plane PAIR — half a cell, which is the unit both blitters read and write with `move.l`.
    .equ SPRITE_CELL_HALF, (SPRITE_CELL_BYTES / SPRITE_CELL_LONGS)
| `lea 156(a0),a0` closes a row that a `move.l dN,(a0)+` has already stepped half a cell into.
    .equ SPRITE_ROW_TAIL, (SCREEN_ROW_BYTES - SPRITE_CELL_HALF)
| `lea 152(a0),a0` — the collide blitter's right-edge band draws in the row's LAST cell.
    .equ SPRITE_COLLIDE_LAST_CELL, (SCREEN_ROW_BYTES - SPRITE_CELL_BYTES)

| The keep-mask index is `lsl.w #1` on the sub-cell phase, so the shift and the stride are one fact
| spelt two ways; assembling fails if they ever stop agreeing.
    .equ SHIFT_MASK_INDEX_SHIFT, 1
    .if (1 << SHIFT_MASK_INDEX_SHIFT) != SPRITE_SHIFT_MASK_STRIDE
    .error "SHIFT_MASK_INDEX_SHIFT no longer scales a phase by SPRITE_SHIFT_MASK_STRIDE"
    .endif

| ================================================================ draw_sprite_masked @ 0x15ace ====
| The callee-saved registers this body clobbers, and every argument offset measured past them, so the
| two can never drift apart.
    .equ MASKED_SAVED,      (7 * 4)
    .equ MASKED_ARG_IMAGE,     4 + MASKED_SAVED
    .equ MASKED_ARG_ENTITY,    8 + MASKED_SAVED
    .equ MASKED_ARG_PRESHIFT, 12 + MASKED_SAVED

    .globl  draw_sprite_masked_asm
draw_sprite_masked_asm:
    movem.l %d2-%d5/%d7/%a2-%a3,-(%sp)
    movea.l MASKED_ARG_IMAGE(%sp),%a3         | the image base, live across the whole body
    movea.l MASKED_ARG_ENTITY(%sp),%a2        | the record, as an offset...
    adda.l  %a3,%a2                           | ...made absolute
    move.w  MASKED_ARG_PRESHIFT + 2(%sp),%d2  | half a preshift frame — the LOW word of the slot
    movea.l %a3,%a0                           | 0x15ace movea.l $1797e.l,a0: the stored offset...
    adda.l  #A_screen_back,%a0
    movea.l (%a0),%a0
    adda.l  %a3,%a0                           | ...plus the base
    bsr.w   .Lmasked                          | every `rts` in the body returns HERE
    movem.l (%sp)+,%d2-%d5/%d7/%a2-%a3
    rts

.Lmasked:
    move.w  ENTITY_X(%a2),%d0                 | 0x15ad4
    and.w   #SPRITE_X_EVEN_MASK,%d0           | 0x15ad8
    bpl.w   .Lm_x_not_negative                | 0x15adc
    rts                                       | 0x15ae0
.Lm_x_not_negative:
    cmp.w   #SCREEN_PIXELS_WIDE,%d0           | 0x15ae2
    blt.w   .Lm_x_on_screen                   | 0x15ae6
    rts                                       | 0x15aea
.Lm_x_on_screen:
    and.w   #SPRITE_X_PHASE_MASK,%d0          | 0x15aec
    mulu.w  %d2,%d0                           | 0x15af0: the phase's slot within the bank
    movea.l ENTITY_SPRITE(%a2),%a1            | 0x15af2 movea.l 10(a2),a1 — an image offset here
    adda.l  %a3,%a1                           |         ...made absolute
    adda.l  %d0,%a1                           | 0x15af6
    move.w  ENTITY_HEIGHT(%a2),%d2            | 0x15af8: NOT masked — see ../sprite.c
    move.w  ENTITY_Y(%a2),%d0                 | 0x15afc
    move.w  %d0,%d1                           | 0x15b00
    cmp.w   #PLAYFIELD_BOTTOM_Y,%d0           | 0x15b02
    blt.s   .Lm_y_above_bottom                | 0x15b06
    rts                                       | 0x15b08
.Lm_y_above_bottom:
    add.w   %d2,%d0                           | 0x15b0a: y + rows
    move.w  %d0,%d3                           | 0x15b0c
    cmp.w   #PLAYFIELD_TOP_Y,%d0              | 0x15b0e
    bgt.s   .Lm_bottom_below_top              | 0x15b12
    rts                                       | 0x15b14
.Lm_bottom_below_top:
    cmp.w   #PLAYFIELD_TOP_Y,%d1              | 0x15b16
    bge.s   .Lm_clip_bottom                   | 0x15b1a: the two clips are EXCLUSIVE arms
    move.w  #PLAYFIELD_TOP_Y,%d5              | 0x15b1c: y above the top — clip the SOURCE forward
    sub.w   %d1,%d5                           | 0x15b20
    move.w  %d5,%d4                           | 0x15b22
    mulu.w  #SPRITE_MASKED_ROW_BYTES,%d5      | 0x15b24
    adda.l  %d5,%a1                           | 0x15b28
    sub.w   %d4,%d2                           | 0x15b2a
    bra.w   .Lm_rows                          | 0x15b2c
.Lm_clip_bottom:
    cmp.w   #PLAYFIELD_BOTTOM_Y,%d3           | 0x15b30
    ble.s   .Lm_rows_fit                      | 0x15b34
    move.w  #PLAYFIELD_BOTTOM_Y,%d2           | 0x15b36
    sub.w   %d1,%d2                           | 0x15b3a
.Lm_rows_fit:
    sub.w   #PLAYFIELD_TOP_Y,%d1              | 0x15b3c
    mulu.w  #SCREEN_ROW_BYTES,%d1             | 0x15b40
    adda.l  %d1,%a0                           | 0x15b44
.Lm_rows:
    subi.w  #1,%d2                            | 0x15b46 sub.w #$1,d2 — NOT the `subq` its sibling has
    move.w  ENTITY_X(%a2),%d0                 | 0x15b4a: x again, unmasked — the cell mask drops the
    and.w   #SPRITE_X_CELL_MASK,%d0           | 0x15b4e  bit the even mask did
    lsr.w   #1,%d0                            | 0x15b52: the cell index times its eight bytes
    adda.w  %d0,%a0                           | 0x15b54

    .globl  draw_sprite_masked_rows_body
draw_sprite_masked_rows_body:                 | from here on, the original's own bytes — see the pin
.Lm_row:
    move.w  (%a1),%d0                         | 0x15b56: the mask word, doubled into a longword
    swap    %d0                               | 0x15b58
    move.w  (%a1)+,%d0                        | 0x15b5a
    move.l  (%a1)+,%d1                        | 0x15b5c: planes 0 and 1
    move.l  (%a1)+,%d7                        | 0x15b5e: planes 2 and 3
    move.l  (%a0),%d3                         | 0x15b60
    move.l  SPRITE_CELL_HALF(%a0),%d4         | 0x15b62
    and.l   %d0,%d3                           | 0x15b66: a mask BIT of 1 keeps the background
    and.l   %d0,%d4                           | 0x15b68
    or.l    %d1,%d3                           | 0x15b6a
    or.l    %d7,%d4                           | 0x15b6c
    move.l  %d3,(%a0)+                        | 0x15b6e
    move.l  %d4,(%a0)                         | 0x15b70
    lea     SPRITE_ROW_TAIL(%a0),%a0          | 0x15b72
    dbf     %d2,.Lm_row                       | 0x15b76
    rts                                       | 0x15b7a
    .globl  draw_sprite_masked_rows_body_end
draw_sprite_masked_rows_body_end:

| ======================================================== draw_sprite_masked_collide @ 0x15b7c ====
    .equ COLLIDE_SAVED,     (11 * 4)
    .equ COLLIDE_ARG_IMAGE,    4 + COLLIDE_SAVED
    .equ COLLIDE_ARG_ENTITY,   8 + COLLIDE_SAVED
    .equ COLLIDE_ARG_HIT,     12 + COLLIDE_SAVED

    .globl  draw_sprite_masked_collide_asm
draw_sprite_masked_collide_asm:
    movem.l %d2-%d7/%a2-%a6,-(%sp)
    movea.l COLLIDE_ARG_IMAGE(%sp),%a4        | the image base — dead by 0x15c58, which reclaims a4
    movea.l COLLIDE_ARG_ENTITY(%sp),%a2
    adda.l  %a4,%a2
    movea.l COLLIDE_ARG_HIT(%sp),%a5          | where a pixel hit stores its 0xff
    adda.l  %a4,%a5
    movea.l %a4,%a0                           | 0x15b7c movea.l $1797e.l,a0: the stored offset...
    adda.l  #A_screen_back,%a0
    movea.l (%a0),%a0
    adda.l  %a4,%a0                           | ...plus the base
    bsr.w   .Lcollide                         | every `rts` in the body returns HERE
    movem.l (%sp)+,%d2-%d7/%a2-%a6
    rts

.Lcollide:
    move.w  ENTITY_X(%a2),%d0                 | 0x15b82
    bclr    #0,%d0                            | 0x15b86: forced even, as its sibling's `and.w` does
    and.w   #SPRITE_X_PHASE_MASK,%d0          | 0x15b8a
    move.w  ENTITY_HEIGHT(%a2),%d2            | 0x15b8e
    and.w   #ENTITY_HEIGHT_MASK,%d2           | 0x15b92
    mulu.w  #SPRITE_COLLIDE_ROW_HALF_WORDS,%d2 | 0x15b96: half a frame, from the height itself
    mulu.w  %d2,%d0                           | 0x15b9a: ...and only its LOW word reaches here
    movea.l ENTITY_SPRITE(%a2),%a1            | 0x15b9c movea.l 10(a2),a1 — an image offset here
    adda.l  %a4,%a1                           |         ...made absolute
    adda.l  %d0,%a1                           | 0x15ba0
    move.w  ENTITY_HEIGHT(%a2),%d2            | 0x15ba2
    and.w   #ENTITY_HEIGHT_MASK,%d2           | 0x15ba6
    move.w  ENTITY_Y(%a2),%d0                 | 0x15baa
    move.w  %d0,%d1                           | 0x15bae
    cmp.w   #PLAYFIELD_BOTTOM_Y,%d0           | 0x15bb0
    blt.s   .Lc_y_above_bottom                | 0x15bb4
    rts                                       | 0x15bb6
.Lc_y_above_bottom:
    add.w   %d2,%d0                           | 0x15bb8
    move.w  %d0,%d3                           | 0x15bba
    cmp.w   #PLAYFIELD_TOP_Y,%d0              | 0x15bbc
    bgt.s   .Lc_bottom_below_top              | 0x15bc0
    rts                                       | 0x15bc2
.Lc_bottom_below_top:
    cmp.w   #PLAYFIELD_TOP_Y,%d1              | 0x15bc4
    bge.s   .Lc_clip_bottom                   | 0x15bc8: the two clips are EXCLUSIVE arms
    move.w  #PLAYFIELD_TOP_Y,%d5              | 0x15bca
    sub.w   %d1,%d5                           | 0x15bce
    move.w  %d5,%d4                           | 0x15bd0
    mulu.w  #SPRITE_MASKED_ROW_BYTES,%d5      | 0x15bd2
    adda.l  %d5,%a1                           | 0x15bd6
    sub.w   %d4,%d2                           | 0x15bd8
    bra.w   .Lc_bands                         | 0x15bda
.Lc_clip_bottom:
    cmp.w   #PLAYFIELD_BOTTOM_Y,%d3           | 0x15bde
    ble.s   .Lc_rows_fit                      | 0x15be2
    move.w  #PLAYFIELD_BOTTOM_Y,%d2           | 0x15be4
    sub.w   %d1,%d2                           | 0x15be8
.Lc_rows_fit:
    sub.w   #PLAYFIELD_TOP_Y,%d1              | 0x15bea
    mulu.w  #SCREEN_ROW_BYTES,%d1             | 0x15bee
    adda.l  %d1,%a0                           | 0x15bf2
.Lc_bands:
    subq.w  #1,%d2                            | 0x15bf4
    move.w  ENTITY_X(%a2),%d0                 | 0x15bf6: x again, forced even a second time
    bclr    #0,%d0                            | 0x15bfa
    move.w  %d0,%d1                           | 0x15bfe
    and.l   #SPRITE_X_PHASE_MASK,%d0          | 0x15c00
    lsl.w   #SHIFT_MASK_INDEX_SHIFT,%d0       | 0x15c06
    movea.l %a4,%a3                           | 0x15c08 lea $1821e.l,a3 — %a4 still holds the
    adda.l  #A_shift_mask_table,%a3           |         image base here, nothing having reused it
    move.l  (%a3,%d0.w),%d7                   | 0x15c0e: the near cell's keep mask...
    move.l  %d7,%d6                           | 0x15c12
    not.l   %d6                               | 0x15c14: ...and the far cell's
    move.w  %d1,%d0                           | 0x15c16
    cmp.w   #SPRITE_COLLIDE_ORIGIN_X,%d0      | 0x15c18
    bge.s   .Lc_not_left_of_screen            | 0x15c1c
    cmp.w   #SPRITE_COLLIDE_LEFT_EDGE,%d0     | 0x15c1e
    bgt.w   .Lc_left_band                     | 0x15c22
    rts                                       | 0x15c26
.Lc_not_left_of_screen:
    cmp.w   #SPRITE_COLLIDE_RIGHT_EDGE,%d0    | 0x15c28
    ble.s   .Lc_middle                        | 0x15c2c
    cmp.w   #SPRITE_COLLIDE_RIGHT_OFF,%d0     | 0x15c2e
    blt.s   .Lc_right_edge                    | 0x15c32
    rts                                       | 0x15c34
.Lc_right_edge:
    lea     SPRITE_COLLIDE_LAST_CELL(%a0),%a0 | 0x15c36
    bra.w   .Lc_right_band                    | 0x15c3a
.Lc_middle:
    sub.w   #SPRITE_COLLIDE_ORIGIN_X,%d0      | 0x15c3e
    and.w   #SPRITE_X_CELL_MASK,%d0           | 0x15c42
    lsr.w   #1,%d0                            | 0x15c46
    adda.w  %d0,%a0                           | 0x15c48

    .globl  draw_sprite_masked_collide_span2_body
draw_sprite_masked_collide_span2_body:        | from here on, the original's own bytes — see the pin
.Lc_span2:                                    | the middle band: the rotated word spans TWO cells
    movea.l %d2,%a6                           | 0x15c4a: the row count, parked past the movem
    movem.l (%a0),%d2-%d5                     | 0x15c4c: both cells, planes 0+1 then 2+3
    move.w  (%a1)+,%d0                        | 0x15c50
    move.w  %d0,%d1                           | 0x15c52
    swap    %d0                               | 0x15c54
    move.w  %d1,%d0                           | 0x15c56: the mask word doubled into a longword
    movea.l %d0,%a4                           | 0x15c58
    not.l   %d0                               | 0x15c5a: the sprite's OPAQUE pixels
    movea.l %d0,%a3                           | 0x15c5c
    and.l   %d7,%d0                           | 0x15c5e
    and.l   %d0,%d3                           | 0x15c60: planes 2+3 of the near cell — the terrain
    beq.s   .Lc_span2_far_test                | 0x15c62
    st      (%a5)                             | 0x15c64
    bra.s   .Lc_span2_compose                 | 0x15c66: a near hit skips the far test
.Lc_span2_far_test:
    move.l  %a3,%d0                           | 0x15c68
    and.l   %d6,%d0                           | 0x15c6a
    and.l   %d0,%d5                           | 0x15c6c
    beq.s   .Lc_span2_compose                 | 0x15c6e
    st      (%a5)                             | 0x15c70
.Lc_span2_compose:
    movem.l (%a0),%d2-%d5                     | 0x15c72: the row again — see ../sprite.c
    move.l  %a4,%d0                           | 0x15c76
    and.l   %d7,%d0                           | 0x15c78
    or.l    %d6,%d0                           | 0x15c7a
    and.l   %d0,%d2                           | 0x15c7c
    and.l   %d0,%d3                           | 0x15c7e
    move.l  %a4,%d0                           | 0x15c80
    and.l   %d6,%d0                           | 0x15c82
    or.l    %d7,%d0                           | 0x15c84
    and.l   %d0,%d4                           | 0x15c86
    and.l   %d0,%d5                           | 0x15c88
    movem.l (%a1)+,%d0-%d1                    | 0x15c8a: the four plane words
    movea.l %d0,%a3                           | 0x15c8e
    movea.l %d1,%a4                           | 0x15c90
    and.l   %d7,%d0                           | 0x15c92
    or.l    %d0,%d2                           | 0x15c94
    and.l   %d7,%d1                           | 0x15c96
    or.l    %d1,%d3                           | 0x15c98
    move.l  %a3,%d0                           | 0x15c9a
    move.l  %a4,%d1                           | 0x15c9c
    and.l   %d6,%d0                           | 0x15c9e
    or.l    %d0,%d4                           | 0x15ca0
    and.l   %d6,%d1                           | 0x15ca2
    or.l    %d1,%d5                           | 0x15ca4
    movem.l %d2-%d5,(%a0)                     | 0x15ca6
    lea     SCREEN_ROW_BYTES(%a0),%a0         | 0x15caa
    move.l  %a6,%d2                           | 0x15cae
    dbf     %d2,.Lc_span2                     | 0x15cb0
    rts                                       | 0x15cb4
    .globl  draw_sprite_masked_collide_span2_body_end
draw_sprite_masked_collide_span2_body_end:

    .globl  draw_sprite_masked_collide_right_body
draw_sprite_masked_collide_right_body:
.Lc_right_band:                               | straddling the right edge: only the sprite's own half
    movea.l %d2,%a6                           | 0x15cb6
    movem.l (%a0),%d2-%d3                     | 0x15cb8
    move.l  %d2,%d4                           | 0x15cbc
    move.l  %d3,%d5                           | 0x15cbe
    move.w  (%a1)+,%d0                        | 0x15cc0
    move.w  %d0,%d1                           | 0x15cc2
    swap    %d0                               | 0x15cc4
    move.w  %d1,%d0                           | 0x15cc6
    movea.l %d0,%a4                           | 0x15cc8
    not.l   %d0                               | 0x15cca
    and.l   %d7,%d0                           | 0x15ccc
    and.l   %d0,%d3                           | 0x15cce
    beq.s   .Lc_right_compose                 | 0x15cd0
    st      (%a5)                             | 0x15cd2
.Lc_right_compose:
    move.l  %a4,%d0                           | 0x15cd4
    and.l   %d7,%d0                           | 0x15cd6
    or.l    %d6,%d0                           | 0x15cd8
    and.l   %d0,%d4                           | 0x15cda
    and.l   %d0,%d5                           | 0x15cdc
    movem.l (%a1)+,%d0-%d1                    | 0x15cde
    and.l   %d7,%d0                           | 0x15ce2
    or.l    %d0,%d4                           | 0x15ce4
    and.l   %d7,%d1                           | 0x15ce6
    or.l    %d1,%d5                           | 0x15ce8
    movem.l %d4-%d5,(%a0)                     | 0x15cea
    lea     SCREEN_ROW_BYTES(%a0),%a0         | 0x15cee
    move.l  %a6,%d2                           | 0x15cf2
    dbf     %d2,.Lc_right_band                | 0x15cf4
    rts                                       | 0x15cf8
    .globl  draw_sprite_masked_collide_right_body_end
draw_sprite_masked_collide_right_body_end:

    .globl  draw_sprite_masked_collide_left_body
draw_sprite_masked_collide_left_body:
.Lc_left_band:                                | straddling the left edge: only the half that rotated
    movea.l %d2,%a6                           | 0x15cfa  OUT of the sprite's own cell is on screen,
    movem.l (%a0),%d2-%d3                     | 0x15cfc  so the two keep masks change places
    move.l  %d2,%d4                           | 0x15d00
    move.l  %d3,%d5                           | 0x15d02
    move.w  (%a1)+,%d0                        | 0x15d04
    move.w  %d0,%d1                           | 0x15d06
    swap    %d0                               | 0x15d08
    move.w  %d1,%d0                           | 0x15d0a
    movea.l %d0,%a4                           | 0x15d0c
    not.l   %d0                               | 0x15d0e
    and.l   %d6,%d0                           | 0x15d10
    and.l   %d0,%d3                           | 0x15d12
    beq.s   .Lc_left_compose                  | 0x15d14
    st      (%a5)                             | 0x15d16
.Lc_left_compose:
    move.l  %a4,%d0                           | 0x15d18
    and.l   %d6,%d0                           | 0x15d1a
    or.l    %d7,%d0                           | 0x15d1c
    and.l   %d0,%d4                           | 0x15d1e
    and.l   %d0,%d5                           | 0x15d20
    movem.l (%a1)+,%d0-%d1                    | 0x15d22
    and.l   %d6,%d0                           | 0x15d26
    or.l    %d0,%d4                           | 0x15d28
    and.l   %d6,%d1                           | 0x15d2a
    or.l    %d1,%d5                           | 0x15d2c
    movem.l %d4-%d5,(%a0)                     | 0x15d2e
    lea     SCREEN_ROW_BYTES(%a0),%a0         | 0x15d32
    move.l  %a6,%d2                           | 0x15d36
    dbf     %d2,.Lc_left_band                 | 0x15d38
    rts                                       | 0x15d3c
| A BRACKET ENDS AT THE TRUE END OF THE TRANSCRIBED SPAN, `rts` included. An `_body_end` label sits
| at the first byte AFTER the span, which for a body that ends a routine is the NEXT routine's entry
| point — and `atari/profile.py` resolves a profiled call by ADDRESS while reporting it by NAME, so
| such a label used to take that entry point's row (measured: the collide twin's 1,146 calls came back
| as `draw_sprite_masked_rows_body_end`, and `draw_score_panel_asm` had no row at all). That is fixed
| where it belongs — `profile.py`'s `elf_symbols` drops `_body`/`_body_end` markers, which are span
| brackets and never call targets — so a bracket here can cover every byte it claims to.
    .globl  draw_sprite_masked_collide_left_body_end
draw_sprite_masked_collide_left_body_end:
