| cast.S — src/raycast.c's render_cast, per ray, in 68000. Compiled as .S so cpp pulls in plat.h.
|
| WHAT THIS IS AND WHAT IT MUST EQUAL. src/raycast.c is the definition: this file produces the SAME
| RenderColumn[] and wall_dist[] for the same GameState, byte for byte. The bench build proves it on
| every frame of every pass by running both and comparing (main.c's cast_selfcheck), and the ledger
| publishes the mismatch count. The C stays the oracle; nothing here is an improvement on it, only a
| faster way to the same answer, and a "harmless" rounding difference would be a bug.
|
| WHY IT IS WORTH THE ASM. Measured before this file existed: 65.4 ms a frame at 160 columns —
| 523,000 cycles, 3,270 a ray, 30% of the whole frame and the second largest stage after the wall
| drawer. ../include/render.h's cost model budgets 730-1,150 cycles a ray and DESIGN 17.3's item 3
| says to put the raycast in asm. The C could not get near the model because the DDA's state does
| not fit the 68000's register file through a compiler: GCC spills a side distance every iteration.
|
| REGISTERS, across the whole column loop:
|   %a0 RenderColumn walker   %a1 wall_dist walker   %a2 the job
|   %a3 angle-table walker    %a4 cosine-table walker
| and inside the DDA:
|   %d0 side_x   %d1 side_y   %d2 delta_step_x   %d3 delta_step_y
|   %d4 index    %d5 hit_len  %d6 scratch/side   %d7 max_trace
|   %a5 the blocking bitmap   %a6 step_x (+1 or -1), added with `add.w %a6,%d4`
| The y step is a stack local rather than a ninth register: 8 cycles on half the steps, against a
| spill of something live on all of them. The column counter is on the stack for the same reason.
|
| THE CELL COORDINATES ARE NOT TRACKED. src/raycast.c carries map_x and map_y alongside the grid
| index and the door test compares against them; keeping them here would be two more adds on every
| step for a value only the door path reads. One DIVU recovers both from the index instead
| (quotient = map_y, remainder = map_x), on the door path only, where 140 cycles is free.

#include "plat.h"

    | Per-ray locals. The DDA owns every register, so what it needs only at the ends lives here.
    L_SINE          = 0     | i16
    L_COSINE        = 2     | i16
    L_DELTA_X       = 4     | u16, UNCLAMPED: the door plane's half-step needs the real length
    L_DELTA_Y       = 6     | u16
    L_ISTEP_Y       = 8     | i16, step_y * grid_width
    L_HIT_U         = 10    | u16, map units along the face within the cell
    L_CELL          = 12    | u16, the grid value that was hit
    L_SIDE          = 14    | u16, PLAT_SIDE_NS or PLAT_SIDE_EW
    L_PERP          = 16    | u16, the fisheye-corrected distance
    L_SAVE_D        = 18    | 4 words: the DDA's live state while the door path runs
    L_SAVE_A        = 28    | 2 longs: the two output walkers, likewise
    L_LOCAL_BYTES   = 36

    CAST_SAVED_BYTES = 44   | movem.l %d2-%d7/%a2-%a6 == 11 registers
    CAST_ARG_JOB     = L_LOCAL_BYTES + CAST_SAVED_BYTES + 4

    | Once the column counter is pushed, every local is two bytes further down. The two names for
    | each offset are what keeps that from being a silent off-by-two.
    C_SINE      = L_SINE + 2
    C_COSINE    = L_COSINE + 2
    C_DELTA_X   = L_DELTA_X + 2
    C_DELTA_Y   = L_DELTA_Y + 2
    C_ISTEP_Y   = L_ISTEP_Y + 2
    C_HIT_U     = L_HIT_U + 2
    C_CELL      = L_CELL + 2
    C_SIDE      = L_SIDE + 2
    C_PERP      = L_PERP + 2
    C_SAVE_D    = L_SAVE_D + 2
    C_SAVE_A    = L_SAVE_A + 2

    .text
    .globl  bi_render_cast
bi_render_cast:
    movem.l %d2-%d7/%a2-%a6,-(%sp)
    suba.w  #L_LOCAL_BYTES,%sp
    move.l  CAST_ARG_JOB(%sp),%a2
    move.l  CJOB_COLUMNS(%a2),%a0
    move.l  CJOB_WALL_DIST(%a2),%a1
    move.l  CJOB_ANGLE_TABLE(%a2),%a3
    move.l  CJOB_COS_TABLE(%a2),%a4
    move.w  CJOB_COUNT(%a2),%d6
    subq.w  #1,%d6
    bmi.w   9000f
    move.w  %d6,-(%sp)

| ================================================================ per ray =======================
1000:
    | ---- the ray angle, and the four table entries it selects ----
    move.w  CJOB_PLAYER_ANGLE(%a2),%d0
    add.w   (%a3)+,%d0              | angle_t wraps by definition, so the add IS the wrap
    lsr.w   #PLAT_TRIG_INDEX_SHIFT,%d0
    add.w   %d0,%d0                 | a byte offset, 0..2046: a 16-bit value shifted down 6 needs
    move.l  CJOB_SIN_TABLE(%a2),%a5 | no mask, which is why TRIG_INDEX_MASK does not appear here
    move.l  CJOB_INV_COS_TABLE(%a2),%a6
    move.w  (%a5,%d0.w),%d6
    move.w  %d6,C_SINE(%sp)
    move.w  (%a6,%d0.w),%d6
    move.w  %d6,C_DELTA_X(%sp)
    move.w  %d0,%d1
    add.w   #PLAT_TRIG_QUARTER_BYTES,%d1
    and.w   #PLAT_TRIG_WRAP_BYTES,%d1
    move.w  (%a5,%d1.w),%d6         | cosine: the sine table read a quarter turn along
    move.w  %d6,C_COSINE(%sp)
    move.w  %d0,%d1
    sub.w   #PLAT_TRIG_QUARTER_BYTES,%d1
    and.w   #PLAT_TRIG_WRAP_BYTES,%d1
    move.w  (%a6,%d1.w),%d6
    move.w  %d6,C_DELTA_Y(%sp)

    move.w  CJOB_MAX_TRACE(%a2),%d7
    moveq   #0,%d4
    move.w  %d7,%d4                 | max_trace zero-extended, for the two 32-bit crossing tests

    | ---- x: the cell step, the distance to the next grid line, and the first crossing ----
    tst.w   C_COSINE(%sp)
    bmi.s   1010f
    moveq   #1,%d6
    move.w  CJOB_TO_NEXT_X_POS(%a2),%d0
    bra.s   1011f
1010:
    moveq   #-1,%d6
    move.w  CJOB_TO_NEXT_X_NEG(%a2),%d0
1011:
    movea.w %d6,%a6                 | step_x, for the whole DDA
    move.w  C_DELTA_X(%sp),%d2
    cmp.w   #PLAT_DELTA_DIST_NEVER,%d2
    beq.s   1012f
    mulu.w  %d2,%d0                 | to_next * delta, a genuine unsigned 16x16
    lsr.l   #PLAT_CELL_SHIFT,%d0
    cmp.l   %d4,%d0
    bls.s   1013f
1012:
    move.w  #PLAT_DDA_BEYOND_TRACE,%d0
1013:

    | ---- y: the same, and the grid-index step that goes with it ----
    tst.w   C_SINE(%sp)
    bmi.s   1020f
    move.w  CJOB_GRID_WIDTH(%a2),%d6
    move.w  CJOB_TO_NEXT_Y_POS(%a2),%d1
    bra.s   1021f
1020:
    move.w  CJOB_GRID_WIDTH(%a2),%d6
    neg.w   %d6
    move.w  CJOB_TO_NEXT_Y_NEG(%a2),%d1
1021:
    move.w  %d6,C_ISTEP_Y(%sp)
    move.w  C_DELTA_Y(%sp),%d3
    cmp.w   #PLAT_DELTA_DIST_NEVER,%d3
    beq.s   1022f
    mulu.w  %d3,%d1
    lsr.l   #PLAT_CELL_SHIFT,%d1
    cmp.l   %d4,%d1
    bls.s   1023f
1022:
    move.w  #PLAT_DDA_BEYOND_TRACE,%d1
1023:

    | ---- the accumulator steps, clamped so the side distances stay inside a word ----
    cmp.w   #PLAT_DDA_BEYOND_TRACE,%d2  | UNSIGNED: a delta can exceed INT16_MAX
    bls.s   1030f
    move.w  #PLAT_DDA_BEYOND_TRACE,%d2
1030:
    cmp.w   #PLAT_DDA_BEYOND_TRACE,%d3
    bls.s   1031f
    move.w  #PLAT_DDA_BEYOND_TRACE,%d3
1031:
    move.w  CJOB_START_INDEX(%a2),%d4
    move.l  CJOB_BLOCKING(%a2),%a5

| ---------------------------------------------------------------- the DDA ----------------------
| The blocking test is written out in BOTH branches rather than after them, which costs 20 bytes and
| buys the register `side` would have needed: the branch that took the step is the branch that knows
| which side was crossed, so it says so with a `moveq` on the way out and nothing carries it.
|
| COUNTED, x branch, no hit: 4 + 8 + 4+4+4 + 4 + 8 + 4 + 14 + 14 + 10 = 78 cycles
|          y branch, no hit: 4 + 10 + 4+4+12 + 4 + 8 + 4 + 14 + 14 + 10 = 88
| `btst Dn,<ea>` takes its bit number modulo 8, so the index doubles as the bit selector and only
| the byte offset has to be derived — which is the whole reason the blocking map is a bitmap.
|
| THERE IS NO STEP COUNTER, and src/raycast.c's DDA_MAX_STEPS is not reproduced because it cannot
| fire: both side distances only ever grow, by at least CELL_UNITS a step (a delta is
| CELL_UNITS / |cos| and so never smaller), so one of them exceeds max_trace within
| 2 * RENDER_RADIUS_MAX = 40 steps, well inside the 64 the C allows.
1100:
    cmp.w   %d1,%d0
    bge.w   1200f
    move.w  %d0,%d5                 | hit_len = side_x
    add.w   %d2,%d0
    add.w   %a6,%d4                 | index += step_x
    cmp.w   %d7,%d5
    bgt.w   1900f                   | past the trace: no hit, the far fill
    move.w  %d4,%d6
    lsr.w   #3,%d6
    btst    %d4,(%a5,%d6.w)
    beq.w   1100b
    moveq   #PLAT_SIDE_EW,%d6
    bra.w   1300f
1200:
    move.w  %d1,%d5                 | hit_len = side_y
    add.w   %d3,%d1
    add.w   C_ISTEP_Y(%sp),%d4
    cmp.w   %d7,%d5
    bgt.w   1900f
    move.w  %d4,%d6
    lsr.w   #3,%d6
    btst    %d4,(%a5,%d6.w)
    beq.w   1100b
    moveq   #PLAT_SIDE_NS,%d6

| ---------------------------------------------------------------- something blocks -------------
1300:
    move.w  %d6,C_SIDE(%sp)
    move.l  CJOB_GRID_CELLS(%a2),%a5    | %a5 stops being the bitmap here; the door path puts it back
    moveq   #0,%d6
    move.b  (%a5,%d4.w),%d6
    move.w  %d6,C_CELL(%sp)
    cmp.w   #PLAT_CELL_DOOR_BASE,%d6
    blo.w   1500f
    cmp.w   #PLAT_CELL_DOOR_MAX,%d6
    bhi.w   1500f

| ---------------------------------------------------------------- a door -----------------------
| Doors are rare, so this path spends freely: it saves the DDA's live state to locals, works with
| every register, and either returns to the loop, falls out to the far fill, or joins the wall path.
    movem.w %d0-%d3,C_SAVE_D(%sp)
    movem.l %a0-%a1,C_SAVE_A(%sp)
    move.l  CJOB_DOOR_OF_CELL(%a2),%a5
    moveq   #0,%d0
    move.b  (%a5,%d4.w),%d0
    cmp.w   #PLAT_DOOR_NONE,%d0
    beq.s   1400f                       | no door record: it can only be shut
    move.l  CJOB_DOORS(%a2),%a5
    mulu.w  #PLAT_DOOR_SIZEOF,%d0
    adda.l  %d0,%a5
    cmp.b   #PLAT_DOOR_STATE_OPEN,PLAT_DOOR_STATE_OFF(%a5)
    beq.w   1450f                       | an open door is simply not there
1400:
    | plane_len = hit_len + (unclamped delta >> 1), and 32 bits because it can exceed INT16_MAX
    move.w  C_DELTA_X(%sp),%d1
    cmp.w   #PLAT_SIDE_EW,C_SIDE(%sp)
    beq.s   1401f
    move.w  C_DELTA_Y(%sp),%d1
1401:
    moveq   #0,%d2
    move.w  %d1,%d2
    lsr.l   #1,%d2
    moveq   #0,%d3
    move.w  %d5,%d3
    add.l   %d2,%d3                     | plane_len
    moveq   #0,%d2
    move.w  %d7,%d2
    cmp.l   %d2,%d3
    bgt.w   1460f                       | past the trace: the C breaks with no hit at all
    | across = pos + (mul16(sine or cosine, plane_len) >> TRIG_SHIFT)
    move.w  C_SINE(%sp),%d0
    move.w  CJOB_POS_Y(%a2),%d1
    cmp.w   #PLAT_SIDE_EW,C_SIDE(%sp)
    beq.s   1402f
    move.w  C_COSINE(%sp),%d0
    move.w  CJOB_POS_X(%a2),%d1
1402:
    muls.w  %d3,%d0                     | plane_len is inside a word: it passed the test above
    add.l   %d0,%d0
    add.l   %d0,%d0
    swap    %d0                         | (x << 2) >> 16 == x >> TRIG_SHIFT, and 20 cycles not 36
    add.w   %d1,%d0                     | across
    move.w  %d0,%d1
    asr.w   #PLAT_CELL_SHIFT,%d1        | the cell it landed in; across can be negative
    | the cell the ray is IN, recovered from the grid index
    moveq   #0,%d2
    move.w  %d4,%d2
    divu.w  CJOB_GRID_WIDTH(%a2),%d2    | quotient = map_y, remainder in the high word = map_x
    cmp.w   #PLAT_SIDE_EW,C_SIDE(%sp)
    beq.s   1403f
    swap    %d2                         | side NS: compare against map_x
1403:
    cmp.w   %d2,%d1
    bne.w   1450f                       | the ray left the cell sideways before the leaf
    move.w  %d3,%d5                     | hit_len = plane_len
    and.w   #PLAT_CELL_FRAC_MASK,%d0
    move.w  %d0,C_HIT_U(%sp)
    movem.l C_SAVE_A(%sp),%a0-%a1
    bra.w   1600f
1450:                                   | not a hit: carry on stepping
    movem.w C_SAVE_D(%sp),%d0-%d3
    movem.l C_SAVE_A(%sp),%a0-%a1
    move.l  CJOB_BLOCKING(%a2),%a5
    bra.w   1100b
1460:
    movem.l C_SAVE_A(%sp),%a0-%a1
    bra.w   1900f

| ---------------------------------------------------------------- a wall -----------------------
1500:
    move.w  C_SINE(%sp),%d0
    move.w  CJOB_POS_Y(%a2),%d1
    cmp.w   #PLAT_SIDE_EW,C_SIDE(%sp)
    beq.s   1501f
    move.w  C_COSINE(%sp),%d0
    move.w  CJOB_POS_X(%a2),%d1
1501:
    muls.w  %d5,%d0
    add.l   %d0,%d0
    add.l   %d0,%d0
    swap    %d0
    add.w   %d1,%d0
    and.w   #PLAT_CELL_FRAC_MASK,%d0
    move.w  %d0,C_HIT_U(%sp)

| ---------------------------------------------------------------- emit a wall column -----------
1600:
    move.w  (%a4),%d0                   | this column's fisheye cosine, 1.14
    muls.w  %d5,%d0
    add.l   %d0,%d0
    add.l   %d0,%d0
    swap    %d0
    move.w  %d0,C_PERP(%sp)
    move.w  C_HIT_U(%sp),%d3
    lsr.w   #PLAT_TEXEL_SHIFT,%d3       | tex_col
    | The two faces whose winding runs the other way get the texture mirrored, or adjacent walls
    | meet with it flipped. WHICH TWO was inverted until 2026-08-28 and the whole world was
    | left-right flipped with no seam to show for it; src/raycast.c's comment has the measurement,
    | and this is the same rule with the same senses: mirror when EW and cosine <= 0, or NS and
    | sine >= 0.
    cmp.w   #PLAT_SIDE_EW,C_SIDE(%sp)
    bne.s   1601f
    tst.w   C_COSINE(%sp)
    ble.s   1602f
    bra.s   1603f
1601:
    tst.w   C_SINE(%sp)
    blt.s   1603f
1602:
    move.w  #PLAT_TEX_INDEX_MASK,%d6
    sub.w   %d3,%d6
    move.w  %d6,%d3
1603:
    move.w  C_PERP(%sp),%d0
    bsr.w   8000f                       | project_slice
    move.l  CJOB_CELL_TEXTURE(%a2),%a5
    move.w  C_CELL(%sp),%d0
    move.b  (%a5,%d0.w),COL_TEX_ID(%a0)
    move.b  %d3,COL_TEX_COL(%a0)
    move.w  C_PERP(%sp),%d0
    bsr.w   8100f                       | band_of
    move.b  %d0,COL_BAND(%a0)
    move.w  C_SIDE(%sp),%d0
    move.b  %d0,COL_SIDE(%a0)
    move.w  C_PERP(%sp),(%a1)
    bra.w   1950f

| ---------------------------------------------------------------- emit a far column ------------
1900:
    move.w  (%a4),%d0
    muls.w  %d7,%d0                     | max_trace, fisheye corrected exactly as a hit would be
    add.l   %d0,%d0
    add.l   %d0,%d0
    swap    %d0
    bsr.w   8000f                       | project_slice
    clr.b   COL_TEX_ID(%a0)             | COLUMN_TEX_FAR
    clr.b   COL_TEX_COL(%a0)
    move.b  CJOB_BAND_LAST(%a2),COL_BAND(%a0)
    move.b  #PLAT_SIDE_NS,COL_SIDE(%a0)
    | A flat far-fill slab never occludes a sprite: everything the sim draws is nearer by construction.
    move.w  #PLAT_WALL_DIST_NONE,(%a1)

1950:
    lea     COL_SIZEOF(%a0),%a0
    addq.l  #2,%a1
    addq.l  #2,%a4
    move.w  (%sp),%d0
    subq.w  #1,%d0
    move.w  %d0,(%sp)
    bpl.w   1000b
    addq.l  #2,%sp
9000:
    adda.w  #L_LOCAL_BYTES,%sp
    movem.l (%sp)+,%d2-%d7/%a2-%a6
    rts

| ---------------------------------------------------------------- project_slice ----------------
| d0 = perpendicular distance, %a0 = the column. Writes tex_step, tex_v, top and rows; clobbers
| d0/d1/d2/d6 and %a5. Uses no locals, so the `bsr` return address on the stack cannot shift them.
8000:
    cmp.w   #PLAT_DIST_TABLE_MAX,%d0    | the head of the table repeats DIST_MIN_UNITS, so only the
    bls.s   8001f                       | top end needs clamping
    move.w  #PLAT_DIST_TABLE_MAX,%d0
8001:
    add.w   %d0,%d0
    move.l  CJOB_SLICE_HEIGHT(%a2),%a5
    move.w  (%a5,%d0.w),%d1             | height
    move.l  CJOB_TEX_STEP(%a2),%a5
    move.w  (%a5,%d0.w),%d2             | step
    move.w  %d2,COL_TEX_STEP(%a0)
    move.w  #PLAT_RENDER_H,%d6
    sub.w   %d1,%d6
    asr.w   #1,%d6                      | top, floored so the slice stays symmetric
    bpl.s   8010f
    neg.w   %d6                          | taller than the window: start the texel past the overhang
    muls.w  %d2,%d6
    move.w  %d6,COL_TEX_V(%a0)
    clr.w   COL_TOP(%a0)
    move.w  #PLAT_RENDER_H,COL_ROWS(%a0)
    rts
8010:
    clr.w   COL_TEX_V(%a0)
    move.w  %d6,COL_TOP(%a0)
    move.w  %d6,%d0
    add.w   %d1,%d0
    cmp.w   #PLAT_RENDER_H,%d0
    bls.s   8011f
    move.w  #PLAT_RENDER_H,%d1
    sub.w   %d6,%d1
8011:
    move.w  %d1,COL_ROWS(%a0)
    rts

| ---------------------------------------------------------------- band_of ----------------------
| d0 = perpendicular distance in, the depth band out. src/raycast.c writes the chain out for exactly
| BAND_COUNT - 1 edges and so does this; unused edges are 0xffff, which is why a three-band mode
| needs no special case. Clobbers %a5.
8100:
    lea     CJOB_BAND_LIMIT(%a2),%a5
    cmp.w   (%a5),%d0
    blo.s   8110f
    cmp.w   2(%a5),%d0
    blo.s   8111f
    cmp.w   4(%a5),%d0
    blo.s   8112f
    cmp.w   6(%a5),%d0
    blo.s   8113f
    moveq   #0,%d0
    move.b  CJOB_BAND_LAST(%a2),%d0
    rts
8110:
    moveq   #0,%d0
    rts
8111:
    moveq   #1,%d0
    rts
8112:
    moveq   #2,%d0
    rts
8113:
    moveq   #3,%d0
    rts
