| render.S — the five hot loops of a BLACK ICE frame, hand written. Compiled as .S so cpp pulls in
| plat.h: every geometry constant below is that file's, never a literal repeated here.
|
| CYCLE COUNTS. Each loop carries the per-iteration count computed from the MC68000 timing tables
| (8 MHz, no wait states, longword accesses to even addresses). The counts EXPECTED are in the
| comments; the counts MEASURED per stage are in README.md, which is canonical, and the spike's
| equivalents are in ../spike/REPORT.md. The two are compared there rather than here, because a
| loop's measured cost also carries the caller's per-column overhead and Hatari's emulated bus.
|
| REGISTERS: m68k SysV — %d0/%d1/%a0/%a1 are scratch, %d2-%d7/%a2-%a6 are callee-saved, arguments
| start at 4(%sp) in 4-byte slots, result in %d0. Every routine here saves exactly what it uses.
|
| WHAT THE ENGINE HANDS OVER. include/render.h's RenderColumn list and include/sprite.h's
| RenderSprite list, both fully clipped and divide-free; what goes back is the planar picture. The
| chunky layout in between is the PLATFORM's business, and it is the pair-word buffer plat.h
| documents, not the engine's column-major byte reference (src/draw.c, src/sprite.c) — those stay
| the host-side oracle that atari/verify.py compares this file's pixels against.

#include "plat.h"

    | Shift counts spelled as their log2 so a change to the layout in plat.h cannot leave a stale
    | literal behind here. `.if` refuses rather than mis-assembling.
    TEX_ID_SCALE_SHIFT      = 2       | a texture slot is a 4-byte pointer
    TEX_WORD_COL_SHIFT      = 7       | TEX_WORD_COL_BYTES == 128
    SHADE_LEVEL_SHIFT       = 6       | SHADE_LEVEL_BYTES  == 64
    .if (1 << TEX_WORD_COL_SHIFT) - TEX_WORD_COL_BYTES
    .error "TEX_WORD_COL_SHIFT does not match TEX_WORD_COL_BYTES"
    .endif
    .if (1 << SHADE_LEVEL_SHIFT) - SHADE_LEVEL_BYTES
    .error "SHADE_LEVEL_SHIFT does not match SHADE_LEVEL_BYTES"
    .endif

    .text

| ============================================================== the column drawer ===============
|
| void bi_draw_columns(const BiDrawJob *job)
|
| Draws EVERY logical column of the view into the chunky buffer: per column a solid ceiling run, a
| wall run (textured, or the flat far fill when tex_id is COLUMN_TEX_FAR) and a solid floor run,
| each stepping down one chunky row (JOB_STRIDE bytes) per logical pixel. The EVEN column of a
| pixel pair writes the chunky word and the ODD column ORs into it, which is what lets the c2p do
| one lookup per two pixels; the two differ only in their store and in which 16-word shade table
| they use, so they are one macro instantiated twice.
|
| NO CLIPPING IS NEEDED and that is a property of the band, not an omission: JOB_BAND_TOP is the
| minimum RenderColumn.top over all columns and JOB_BAND_BOTTOM the maximum top+rows (widened in
| main.c to cover the sprites), so every column's three runs are non-negative and sum to exactly
| the band's height. Outside the band the view is COLOUR_VOID, written straight to the screen by
| bi_fill at 2.7 cycles a byte instead of the drawer's 26 plus the c2p's 31 — ../spike/REPORT.md
| measured that band fill as a 40-42% saving on the whole frame, the single largest lever it found.
|
| THE TEXTURE COORDINATE IS 16.16 WITH THE INTEGER PART A *TEXEL* INDEX. The engine's tex_v and
| tex_step are 8.8 words; shifting both up by 8 once per column puts the texel index in the high
| word, where `swap` reaches it for 4 cycles instead of `lsr.w #8`'s 24. The doubling to a word
| offset is `add.w %d0,%d0` rather than a mask, and that is the correctness argument, not a saved
| instruction: src/raycast.c's project_slice derives the step by truncating (TEX_DIM << 8) / height
| and never writes more than `height` rows, so the accumulator's integer part is provably
| 0..TEX_DIM-1 and doubling a value in that range always lands on an EVEN offset inside the column.
| A masked byte offset could let an odd one through and `move.w (%a6,%d0.w)` would take an address
| error. Out of range it could only read a neighbouring texture column — every texture word this
| file reads is a palette index doubled, which the shade table is 16 entries wide for, so no read
| here can leave the tables.
|
| REGISTERS: %d0/%d1 scratch, %d2 pair counter, %d3 floor rows, %d4 run counter, %d5 chunky stride,
| %d6 texture accumulator, %d7 texture step; %a0 chunky walker, %a1 RenderColumn walker, %a2 the
| job, %a3 the pair's first chunky word, %a4 the BiTables, %a5 the column's shade table, %a6 the
| texture column.

| ---- unrolling ---------------------------------------------------------------------------------
| Every run below is drawn EIGHT PIXELS AT A TIME with the row pitch folded into each store's
| displacement, then the remaining 0..7 one at a time by the same code the loop used to be. The
| pitch can be a literal because plat.h fixes CHUNKY_ROW_BYTES at both detail levels; the eight
| stores replace eight `adda.w` and seven eighths of a `dbra`.
|
| COUNTED, per pixel, against what the one-at-a-time version cost:
|   wall  even  4 + 8 + 4 + 4 + 14 + 22            = 56, plus (8 + 10) / 8    -> 58   was 70
|   wall  odd   4 + 8 + 4 + 4 + 14 + 14 + 20       = 68, plus 18 / 8          -> 70   was 78
|   solid even  12                                                            -> 14   was 26
|   solid odd   20                                                            -> 22   was 30
| The tail runs at the old rate, so a run of n pixels pays the old price for n mod 8 of them. The
| measured stage figures are in README.md; a run shorter than eight is common at the top of the
| band, which is why the tail is a loop and not an error.

    .macro  WALL_PIXEL store, disp
    move.l  %d6,%d0                 |  4
    add.l   %d7,%d6                 |  8
    swap    %d0                     |  4   integer part == texel index, 0..TEX_DIM-1
    add.w   %d0,%d0                 |  4   ...to an even word offset inside the column
    move.w  (%a6,%d0.w),%d1         | 14   the texel, already palette index * 2
    \store  \disp
    .endm

    .macro  WALL_STORE_EVEN disp
    move.w  (%a5,%d1.w),\disp(%a0)  | 22
    .endm

    .macro  WALL_STORE_ODD disp
    move.w  (%a5,%d1.w),%d0         | 14
    or.w    %d0,\disp(%a0)          | 20
    .endm

    .macro  SOLID_STORE_EVEN disp
    move.w  %d1,\disp(%a0)          | 12
    .endm

    .macro  SOLID_STORE_ODD disp
    or.w    %d1,\disp(%a0)          | 20
    .endm

    ROW  = CHUNKY_ROW_BYTES
    UNROLL_SHIFT = 3                | eight pixels a block
    UNROLL       = (1 << UNROLL_SHIFT)

| THE RUN GUARDS ARE SIGNED AND TEST FOR "AT MOST ZERO", which is not fussiness. A run count reaches
| here as `band_bottom - top - rows`, and main.c clamps the band's edges to the window as a
| belt-and-braces against a slice that overran — so a clamp that fires makes a floor run NEGATIVE.
| `lsr.w #3` of a negative word is a large positive, the block loop then runs thousands of times,
| and the chunky pointer walks off into the machine: measured here as a bus error at $400060 inside
| the odd column's solid store, on the first bench run after the unroll landed.
|
| THE RUN MACROS USE LABELS 5-8 AND DRAW_COLUMN USES 1-4, and that separation is load-bearing: these
| are expanded INSIDE it, and a numeric local resolves to the nearest definition in the right
| direction — so when both used 1-4, DRAW_COLUMN's "skip the wall run" branch landed in the middle of
| a solid run's unrolled body. It ran, and it walked the chunky pointer off into the machine: a bus
| error at $400060 in the odd column's solid store, on the first bench after the unroll.
|
| A run of \d4 pixels of one solid pen (\d1), eight at a time then the remainder.
    .macro  SOLID_RUN store
    move.w  %d4,%d3
    lsr.w   #UNROLL_SHIFT,%d3
    beq.w   6f
    subq.w  #1,%d3
5:
    \store  0*ROW
    \store  1*ROW
    \store  2*ROW
    \store  3*ROW
    \store  4*ROW
    \store  5*ROW
    \store  6*ROW
    \store  7*ROW
    lea     (UNROLL*ROW)(%a0),%a0   |  8
    dbra    %d3,5b                  | 10
6:
    and.w   #(UNROLL-1),%d4
    subq.w  #1,%d4
    bmi.w   8f
7:
    \store  0
    lea     ROW(%a0),%a0
    dbra    %d4,7b
8:
    .endm

| The same shape for the textured run: \d6/\d7 are the 16.16 texel accumulator and its step.
    .macro  WALL_RUN store
    move.w  %d4,%d3
    lsr.w   #UNROLL_SHIFT,%d3
    beq.w   6f
    subq.w  #1,%d3
5:
    WALL_PIXEL \store, 0*ROW
    WALL_PIXEL \store, 1*ROW
    WALL_PIXEL \store, 2*ROW
    WALL_PIXEL \store, 3*ROW
    WALL_PIXEL \store, 4*ROW
    WALL_PIXEL \store, 5*ROW
    WALL_PIXEL \store, 6*ROW
    WALL_PIXEL \store, 7*ROW
    lea     (UNROLL*ROW)(%a0),%a0
    dbra    %d3,5b
6:
    and.w   #(UNROLL-1),%d4
    subq.w  #1,%d4
    bmi.w   8f
7:
    WALL_PIXEL \store, 0
    lea     ROW(%a0),%a0
    dbra    %d4,7b
8:
    .endm

| \solid, \wall   the two store policies above
| \shade_off      0 for the even column's shade tables, SHADE_TABLE_BYTES for the odd column's
| \void_off       JOB_VOID_EVEN or JOB_VOID_ODD — the ceiling and floor pen, already pair-scaled
| \far_off        JOB_FAR_EVEN or JOB_FAR_ODD
    .macro  DRAW_COLUMN solid, wall, shade_off, void_off, far_off
    move.w  JOB_BAND_BOTTOM(%a2),%d5
    sub.w   COL_TOP(%a1),%d5
    sub.w   COL_ROWS(%a1),%d5       | floor rows, kept for after the wall run clobbers %d4
    move.w  COL_TOP(%a1),%d4
    sub.w   JOB_BAND_TOP(%a2),%d4   | ceiling rows
    ble.w   1f                      | SIGNED, and not `beq`: see the note on the run guards below
    move.w  \void_off(%a2),%d1
    SOLID_RUN \solid
1:
    move.w  COL_ROWS(%a1),%d4
    ble.w   2f
    moveq   #0,%d0
    move.b  COL_TEX_ID(%a1),%d0
    bne.w   3f
    move.w  \far_off(%a2),%d1       | COLUMN_TEX_FAR: a flat column of COLOUR_FAR_FILL
    SOLID_RUN \solid
    bra.w   2f
3:
    lsl.w   #TEX_ID_SCALE_SHIFT,%d0
    move.l  TBL_TEX(%a4,%d0.w),%a6
    moveq   #0,%d0
    move.b  COL_TEX_COL(%a1),%d0
    lsl.w   #TEX_WORD_COL_SHIFT,%d0 | at most 63 * 128 == 8064, so the sign-extended adda is safe
    adda.w  %d0,%a6
    moveq   #0,%d0
    move.b  COL_BAND(%a1),%d0
    moveq   #0,%d1
    move.b  COL_SIDE(%a1),%d1
    add.w   %d1,%d0                 | the shade level IS band + side (include/render.h)
    lsl.w   #SHADE_LEVEL_SHIFT,%d0
    lea     (TBL_SHADE + \shade_off)(%a4,%d0.w),%a5
    moveq   #0,%d6
    move.w  COL_TEX_V(%a1),%d6
    lsl.l   #8,%d6                  | 8.8 -> 16.16 with the texel index in the high word
    moveq   #0,%d7
    move.w  COL_TEX_STEP(%a1),%d7
    lsl.l   #8,%d7
    WALL_RUN \wall
2:
    move.w  %d5,%d4
    ble.w   4f
    move.w  \void_off(%a2),%d1
    SOLID_RUN \solid
4:
    lea     COL_SIZEOF(%a1),%a1
    .endm

    DRAW_SAVED_BYTES = 44           | movem.l %d2-%d7/%a2-%a6 == 11 registers
    DRAW_ARG_JOB     = DRAW_SAVED_BYTES + 4

    .globl  bi_draw_columns
bi_draw_columns:
    movem.l %d2-%d7/%a2-%a6,-(%sp)
    move.l  DRAW_ARG_JOB(%sp),%a2
    move.l  JOB_CHUNKY(%a2),%a3
    move.l  JOB_COLUMNS(%a2),%a1
    move.l  JOB_TABLES(%a2),%a4
    move.w  JOB_PAIRS(%a2),%d2
    subq.w  #1,%d2
    bmi.w   9000f
9001:
    move.l  %a3,%a0
    DRAW_COLUMN SOLID_STORE_EVEN, WALL_STORE_EVEN, 0, JOB_VOID_EVEN, JOB_FAR_EVEN
    move.l  %a3,%a0                 | ...both columns of a pair write the same chunky words
    DRAW_COLUMN SOLID_STORE_ODD, WALL_STORE_ODD, SHADE_TABLE_BYTES, JOB_VOID_ODD, JOB_FAR_ODD
    addq.l  #2,%a3
    dbra    %d2,9001b
9000:
    movem.l (%sp)+,%d2-%d7/%a2-%a6
    rts

| ============================================================== the sprite drawer ===============
|
| void bi_draw_sprites(const BiSpriteJob *job)
|
| Walks the RenderSprite list far-to-near (src/sprite.c sorted it) and, for each, walks its screen
| columns: one texel-u step per column, the engine's per-column depth test against wall_dist, the
| sprite's own opaque span for that column, and then a row loop that steps tex_step_v down the
| texel column.
|
| ONE ROW LOOP SERVES BOTH PARITIES. A sprite pixel REPLACES what the wall drawer put there, so it
| cannot use the wall's move/or pair: it is a read-modify-write that keeps the other pixel of the
| pair (%d5 holds that pen's mask) and drops the new one in. That shape is identical for the even
| and odd columns — only the mask and which 16-word shade table %a3 points at change — so unlike
| the wall drawer there is no second copy of the loop.
|
| The span table is what makes the per-pixel transparency test affordable: it hoists the leading
| and trailing transparent runs of a column out of the loop entirely (include/sprite.h), so the
| `cmp/beq` only pays for holes INSIDE the silhouette.
|
| REGISTERS, row loop: %a0 chunky walker, %a3 the column's shade table, %a5 the chunky stride,
| %a6 the texel column; %d0 scratch, %d1 the texel, %d2 the shaded pen, %d3 the transparency key
| doubled, %d4 the row counter, %d5 the other parity's keep-mask, %d6/%d7 the 16.16 texel-v pair.
| Outer: %a1 the RenderSprite, %a2 the job, %a4 the BiTables, and four words of locals on the stack
| for the state the row loop's register pressure leaves no room for.

    SPR_SAVED_BYTES  = 44           | movem.l %d2-%d7/%a2-%a6 == 11 registers
    | Five words of locals, rounded to a longword so %sp stays even: the row loop uses every data
    | and address register, so the sprite's own cursors have nowhere else to live.
    SPR_LOCAL_BYTES  = 12
    L_TEX_U          = 0            | u16 8.8, this sprite's running texel u
    L_TEX_STEP_U     = 2            | u16 8.8
    L_SCREEN_X       = 4            | i16 the column being drawn
    L_SPRITES_LEFT   = 6            | i16
    L_COLS_LEFT      = 8            | i16
    SPR_ARG_JOB      = SPR_LOCAL_BYTES + SPR_SAVED_BYTES + 4

    .globl  bi_draw_sprites
bi_draw_sprites:
    movem.l %d2-%d7/%a2-%a6,-(%sp)
    suba.w  #SPR_LOCAL_BYTES,%sp
    move.l  SPR_ARG_JOB(%sp),%a2
    move.w  SJOB_COUNT(%a2),%d0
    subq.w  #1,%d0
    bmi.w   8900f
    move.w  %d0,L_SPRITES_LEFT(%sp)
    move.l  SJOB_SPRITES(%a2),%a1
    move.l  SJOB_TABLES(%a2),%a4
    lea     bi_chunky_row_offset,%a5
8800:                               | ---------------------------------------------- per sprite --
    move.w  SPR_TEX_U(%a1),L_TEX_U(%sp)
    move.w  SPR_TEX_STEP_U(%a1),L_TEX_STEP_U(%sp)
    move.w  SPR_LEFT(%a1),L_SCREEN_X(%sp)
    move.w  SPR_COLS(%a1),%d0
    subq.w  #1,%d0
    move.w  %d0,L_COLS_LEFT(%sp)
    bmi.w   8890f
8700:                               | ---------------------------------------------- per column --
    moveq   #0,%d0
    move.b  L_TEX_U(%sp),%d0        | the 8.8 accumulator's HIGH byte IS its integer part
    move.w  L_TEX_U(%sp),%d1
    add.w   L_TEX_STEP_U(%sp),%d1
    move.w  %d1,L_TEX_U(%sp)
    cmpi.w  #PLAT_TEX_DIM,%d0
    bcc.w   8790f                   | past the last texel column: src/sprite.c skips it too

    move.l  SPR_TEXELS(%a1),%a6
    move.w  %d0,%d1
    lsl.w   #TEX_WORD_COL_SHIFT,%d1 | at most 63 * 128 == 8064, so the sign-extended adda is safe
    adda.w  %d1,%a6                 | the texel column, in the word form plat.h describes

    move.l  SPR_SPANS(%a1),%a0
    add.w   %d0,%d0                 | a SpriteSpan is two bytes
    moveq   #0,%d3
    move.b  (%a0,%d0.w),%d3         | first opaque texel row
    moveq   #0,%d4
    move.b  1(%a0,%d0.w),%d4        | last opaque texel row
    cmp.w   %d3,%d4
    bcs.w   8790f                   | last < first: SPRITE_SPAN_IS_EMPTY

    move.w  L_SCREEN_X(%sp),%d1
    cmp.w   SJOB_COLUMNS(%a2),%d1
    bcc.w   8790f                   | unsigned, so a negative column is caught by the same test
    add.w   %d1,%d1
    move.l  SJOB_WALL_DIST(%a2),%a0
    move.w  (%a0,%d1.w),%d2
    cmp.w   SPR_DIST(%a1),%d2
    bls.w   8790f                   | wall_dist <= sprite dist: the wall in this column is nearer

    | first_row = top + (first * rows >> SPRITE_ROW_SHIFT), and one past the last the same way.
    | `first` is under TEX_DIM and `rows` at most SLICE_HEIGHT_MAX (341), so both products are well
    | inside a word and `muls.w` is the right instruction rather than a libgcc call.
    move.w  SPR_ROWS(%a1),%d5
    muls.w  %d5,%d3
    asr.l   #SPRITE_ROW_SHIFT,%d3
    add.w   SPR_TOP(%a1),%d3        | first_row
    addq.w  #1,%d4
    muls.w  %d5,%d4
    asr.l   #SPRITE_ROW_SHIFT,%d4
    add.w   SPR_TOP(%a1),%d4
    subq.w  #1,%d4                  | last_row
    | Clip to the band, which main.c widened to cover every sprite: outside it the chunky buffer is
    | never converted, so a pixel written there would simply be lost.
    move.w  SJOB_BAND_TOP(%a2),%d0
    cmp.w   %d0,%d3
    bge.s   8710f
    move.w  %d0,%d3
8710:
    move.w  SJOB_BAND_BOTTOM(%a2),%d0
    subq.w  #1,%d0
    cmp.w   %d0,%d4
    ble.s   8720f
    move.w  %d0,%d4
8720:
    cmp.w   %d4,%d3
    bgt.w   8790f

    | texel v at first_row, truncated to 16 bits exactly as src/sprite.c's cast does, then shifted
    | up 8 so the texel index lands in the high word where `swap` reaches it.
    move.w  %d3,%d0
    sub.w   SPR_TOP(%a1),%d0
    muls.w  SPR_TEX_STEP_V(%a1),%d0
    moveq   #0,%d6
    move.w  %d0,%d6
    lsl.l   #8,%d6
    moveq   #0,%d7
    move.w  SPR_TEX_STEP_V(%a1),%d7
    lsl.l   #8,%d7
    sub.w   %d3,%d4                 | rows - 1, the dbra counter

    | dst = chunky + row_offset[first_row] + (screen_x & ~1): the chunky word this pair lives in.
    | THE ROW OFFSET IS A TABLE AND NOT A MULTIPLY. It used to be `muls.w SJOB_STRIDE`, 70 cycles on
    | every column of every sprite; the pitch is a constant now (plat.h's CHUNKY_ROW_BYTES) so the
    | 80 products can be a table main.c fills at boot, and the read is 14.
    move.w  %d3,%d0
    add.w   %d0,%d0
    move.w  (%a5,%d0.w),%d0
    move.l  SJOB_CHUNKY(%a2),%a0
    adda.w  %d0,%a0
    move.w  L_SCREEN_X(%sp),%d1
    move.w  %d1,%d0
    bclr    #0,%d0
    adda.w  %d0,%a0

    | The shade table and the keep-mask are the only things the two parities differ in: a sprite
    | pixel REPLACES the wall's, so the store is a read-modify-write either way.
    moveq   #0,%d2
    move.b  SPR_BAND(%a1),%d2
    lsl.w   #SHADE_LEVEL_SHIFT,%d2
    btst    #0,%d1
    beq.s   8730f
    addi.w  #SHADE_TABLE_BYTES,%d2
    move.w  #PAIR_EVEN_MASK,%d5     | the odd column: keep the even pixel of the pair
    bra.s   8740f
8730:
    move.w  #PAIR_ODD_MASK,%d5      | the even column: keep the odd pixel
8740:
    lea     TBL_SHADE(%a4,%d2.w),%a3
    move.w  #(PLAT_SPRITE_TRANSPARENT * 2),%d3

8750:                               | opaque 102 cycles / pixel, transparent 66
    move.l  %d6,%d0                 |  4
    add.l   %d7,%d6                 |  8
    swap    %d0                     |  4   integer part == texel index, 0..TEX_DIM-1
    add.w   %d0,%d0                 |  4
    move.w  (%a6,%d0.w),%d1         | 14   the texel, already palette index * 2
    cmp.w   %d3,%d1                 |  4
    beq.s   8760f                   | 10 taken / 8 not
    move.w  (%a3,%d1.w),%d2         | 14   shaded and pair-scaled
    move.w  (%a0),%d0               |  8
    and.w   %d5,%d0                 |  4   keep the other pixel of the pair
    or.w    %d2,%d0                 |  4
    move.w  %d0,(%a0)               |  8
8760:
    lea     CHUNKY_ROW_BYTES(%a0),%a0   |  8   the pitch is a constant, so this needs no register
    dbra    %d4,8750b               | 10

8790:                               | ------------------------------------------- next column ----
    addq.w  #1,L_SCREEN_X(%sp)
    subq.w  #1,L_COLS_LEFT(%sp)
    bge.w   8700b
8890:                               | ------------------------------------------- next sprite ----
    lea     SPR_SIZEOF(%a1),%a1
    subq.w  #1,L_SPRITES_LEFT(%sp)
    bge.w   8800b
8900:
    adda.w  #SPR_LOCAL_BYTES,%sp
    movem.l (%sp)+,%d2-%d7/%a2-%a6
    rts

| ============================================================== chunky to planar ================
|
| void bi_c2p_high(const unsigned short *chunky, unsigned char *screen, int rows)
| void bi_c2p_low (const unsigned short *chunky, unsigned char *screen, int rows)
|
| One 16-screen-pixel group is four interleaved plane words == two longwords, and both are built by
| OR-ing table entries that are ALREADY in their final bit positions: one table per pair position
| (four of them at high detail, two at low), each entry C2P_ENTRY_BYTES wide holding planes 0/1 at
| +0 and planes 2/3 at +C2P_PLANE23_OFF. The chunky word IS the byte offset into that table, so the
| loop never shifts, masks or packs — it reads, ORs, and stores.
|
| Line doubling is the second store pair through %a3 == %a2 + one screen line. Writing the second
| line here costs 24 cycles per group; ../spike/REPORT.md measured a separate MOVEM copy pass of
| the finished line at 2.71 cycles/byte == 33 cycles for the same eight bytes plus a second walk
| over the image, so the inline write is the cheaper of the two.
|
| EXPECTED, high detail, per group of 8 logical pixels (16 screen px on two lines):
|   4x move.w (%a0)+,Dn                                    4 * 8  =  32
|   1x move.l (An,Dn.w),D4 + 1x move.l 4(An,Dn.w),D5       2 * 18 =  36
|   3x or.l   (An,Dn.w),D4 + 3x or.l   4(An,Dn.w),D5       6 * 20 = 120
|   4x move.l Dn,(An)+                                     4 * 12 =  48
|   dbra                                                            10
|                                                          total = 246  -> 30.8 cyc / logical px
| EXPECTED, low detail, per group of 4 logical pixels: 16 + 36 + 40 + 48 + 10 = 150 -> 37.5 cyc/px.

    C2P_SAVED_BYTES = 44            | movem.l %d2-%d7/%a2-%a6 == 11 registers
    C2P_ARG_CHUNKY  = C2P_SAVED_BYTES + 4
    C2P_ARG_SCREEN  = C2P_SAVED_BYTES + 8
    C2P_ARG_ROWS    = C2P_SAVED_BYTES + 12

    .globl  bi_c2p_high
bi_c2p_high:
    movem.l %d2-%d7/%a2-%a6,-(%sp)
    move.l  C2P_ARG_CHUNKY(%sp),%a0
    move.l  C2P_ARG_SCREEN(%sp),%a2
    move.l  C2P_ARG_ROWS(%sp),%d7
    lea     PLAT_SCREEN_BYTES_PER_LINE(%a2),%a3
    lea     bi_c2p_table_high,%a1
    lea     C2P_TABLE_BYTES(%a1),%a4
    lea     (2*C2P_TABLE_BYTES)(%a1),%a5
    lea     (3*C2P_TABLE_BYTES)(%a1),%a6
    subq.l  #1,%d7
    bmi.s   8000f
8001:
    moveq   #GROUPS_PER_LINE-1,%d6
8002:
    move.w  (%a0)+,%d0
    move.w  (%a0)+,%d1
    move.w  (%a0)+,%d2
    move.w  (%a0)+,%d3
    move.l  (%a1,%d0.w),%d4
    move.l  C2P_PLANE23_OFF(%a1,%d0.w),%d5
    or.l    (%a4,%d1.w),%d4
    or.l    C2P_PLANE23_OFF(%a4,%d1.w),%d5
    or.l    (%a5,%d2.w),%d4
    or.l    C2P_PLANE23_OFF(%a5,%d2.w),%d5
    or.l    (%a6,%d3.w),%d4
    or.l    C2P_PLANE23_OFF(%a6,%d3.w),%d5
    move.l  %d4,(%a2)+
    move.l  %d5,(%a2)+
    move.l  %d4,(%a3)+
    move.l  %d5,(%a3)+
    dbra    %d6,8002b
    lea     PLAT_SCREEN_BYTES_PER_LINE(%a2),%a2     | ...past the line %a3 just wrote
    lea     PLAT_SCREEN_BYTES_PER_LINE(%a3),%a3
    dbra    %d7,8001b
8000:
    movem.l (%sp)+,%d2-%d7/%a2-%a6
    rts

    .globl  bi_c2p_low
bi_c2p_low:
    movem.l %d2-%d7/%a2-%a6,-(%sp)
    move.l  C2P_ARG_CHUNKY(%sp),%a0
    move.l  C2P_ARG_SCREEN(%sp),%a2
    move.l  C2P_ARG_ROWS(%sp),%d7
    lea     PLAT_SCREEN_BYTES_PER_LINE(%a2),%a3
    lea     bi_c2p_table_low,%a1
    lea     C2P_TABLE_BYTES(%a1),%a4
    subq.l  #1,%d7
    bmi.s   7000f
7001:
    moveq   #GROUPS_PER_LINE-1,%d6
7002:
    move.w  (%a0)+,%d0
    move.w  (%a0)+,%d1
    move.l  (%a1,%d0.w),%d4
    move.l  C2P_PLANE23_OFF(%a1,%d0.w),%d5
    or.l    (%a4,%d1.w),%d4
    or.l    C2P_PLANE23_OFF(%a4,%d1.w),%d5
    move.l  %d4,(%a2)+
    move.l  %d5,(%a2)+
    move.l  %d4,(%a3)+
    move.l  %d5,(%a3)+
    dbra    %d6,7002b
    lea     C2P_LOW_ROW_SKIP(%a0),%a0   | the unread half of this chunky row (plat.h)
    lea     PLAT_SCREEN_BYTES_PER_LINE(%a2),%a2
    lea     PLAT_SCREEN_BYTES_PER_LINE(%a3),%a3
    dbra    %d7,7001b
7000:
    movem.l (%sp)+,%d2-%d7/%a2-%a6
    rts

| ============================================================== the solid fill ==================
|
| void bi_fill(void *dst, long bytes, unsigned long plane01, unsigned long plane23)
|
| Fills whole screen lines with one pen: the ceiling and floor bands the walls never reach, and the
| HUD strip before its backdrop lands. Ten registers per MOVEM is FILL_CHUNK_BYTES of screen, and
| the fill runs BACKWARD because the 68000's register-to-memory MOVEM takes predecrement and not
| postincrement. Predecrement stores A7..D0 in descending addresses, so ascending memory reads back
| d0,d1,...,d7,a3,a4 — which is why the pattern is loaded alternating plane01/plane23 in that order.
|
| THE TERMINATION IS `bhi` AND NOT `bne`, AND THAT IS FAIL-SAFE RATHER THAN STYLE. The walker only
| lands exactly on the low limit when the byte count is a whole number of FILL_CHUNK_BYTES; on a
| count that is not, `bne` would step straight past it and keep writing backwards through every byte
| below the screen until it wrapped the address space. `bhi` stops at the first chunk at or below the
| limit — a short fill rather than a destroyed machine. main.c pins the multiple with a
| _Static_assert as well, so the fail-safe is a second line of defence and not the argument.
|
| EXPECTED per chunk: movem.l 10 regs (8 + 8*10 = 88) + cmpa.l (6) + bhi (10) = 104 / 40 bytes
|                     = 2.6 cycles per byte. ../spike/REPORT.md measured 2.71.

    FILL_SAVED_BYTES = 32           | movem.l %d2-%d7/%a3-%a4 == 8 registers
    FILL_ARG_DST     = FILL_SAVED_BYTES + 4
    FILL_ARG_BYTES   = FILL_SAVED_BYTES + 8
    FILL_ARG_PLANE01 = FILL_SAVED_BYTES + 12
    FILL_ARG_PLANE23 = FILL_SAVED_BYTES + 16

    .globl  bi_fill
bi_fill:
    movem.l %d2-%d7/%a3-%a4,-(%sp)
    move.l  FILL_ARG_BYTES(%sp),%d0
    ble.s   6000f
    move.l  FILL_ARG_DST(%sp),%a1               | the low limit
    move.l  %a1,%a0
    adda.l  %d0,%a0                             | ...and the walker starts one chunk past the top
    move.l  FILL_ARG_PLANE01(%sp),%d0
    move.l  FILL_ARG_PLANE23(%sp),%d1
    move.l  %d0,%d2
    move.l  %d1,%d3
    move.l  %d0,%d4
    move.l  %d1,%d5
    move.l  %d0,%d6
    move.l  %d1,%d7
    move.l  %d0,%a3
    move.l  %d1,%a4
6001:
    movem.l %d0-%d7/%a3-%a4,-(%a0)              | 88
    cmpa.l  %a1,%a0                             |  6
    bhi.s   6001b                               | 10
6000:
    movem.l (%sp)+,%d2-%d7/%a3-%a4
    rts
