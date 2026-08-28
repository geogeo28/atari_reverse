| render.S — the four hot loops of the raycast frame, hand written. Compiled as .S so cpp pulls in
| spike.h: every geometry constant below is that file's, never a literal repeated here.
|
| CYCLE COUNTS. Each loop carries the per-iteration count computed from the MC68000 timing tables
| (8 MHz, no wait states, longword accesses to even addresses). The counts EXPECTED are in the
| comments; the counts MEASURED on the whole stage are in REPORT.md, which is canonical. The two are
| compared there rather than here, because a loop's measured cost also carries the caller's
| per-column overhead and Hatari's emulated bus.
|
| REGISTERS: m68k SysV — %d0/%d1/%a0/%a1 are scratch, %d2-%d7/%a2-%a6 are callee-saved, arguments
| start at 4(%sp) in 4-byte slots, result in %d0. Every routine here saves exactly what it uses.

#include "spike.h"

    .text

| ============================================================== the column drawer ===============
|
| void spike_draw_columns(const SpikeDrawJob *job)
|
| Draws EVERY logical column of the view into the chunky buffer: per column a solid ceiling run, a
| texture-mapped wall run and a solid floor run, each stepping down one chunky row (DRAW_STRIDE
| bytes) per logical pixel. The EVEN column of a pixel pair writes the chunky word and the ODD
| column ORs into it, which is what lets the c2p do one lookup per two pixels; the two differ only
| in their store, so they are one macro used twice.
|
| THE WHOLE LOOP IS HERE AND NOT IN C. With the ceiling and floor bands filled straight to the
| screen, a column is about a dozen pixels tall, and a per-column C call around this body measured
| 1680 cycles to draw 13 of them — the parameter block, the push and the prologue, ten times over
| the pixels. Walking the SpikeRay array in asm makes that per-column cost about 120 cycles.
|
| NO CLIPPING IS NEEDED and that is a property of the band, not an omission: DRAW_BAND_TOP is the
| minimum RAY_TOP over all columns and DRAW_BAND_BOTTOM the maximum RAY_TOP+RAY_ROWS, so every
| column's three runs are non-negative and sum to exactly the band's height. The unbanded pass
| passes 0 and VIEW_H, which bracket the same values.
|
| THE TEXTURE COORDINATE IS 16.16 WITH THE INTEGER PART A *TEXEL* INDEX, and the doubling to a byte
| offset is `add.w %d0,%d0` rather than a mask. That is not a saved instruction, it is the
| correctness argument: the accumulator's integer part is provably 0..TEX_SIZE-1 (main.c derives the
| step as distance * TEX_STEP_PER_DIST, truncating, so step * wall_height <= TEX_SIZE << 16), so
| doubling a value in that range always lands on an EVEN offset inside the column. Masking a byte
| offset instead would let an odd one through and `move.w (%a6,%d0.w)` would take an address error.
|
| REGISTERS: %d0/%d1 scratch, %d2 pair counter, %d3 floor rows, %d4 run counter, %d5 chunky stride,
| %d6 texture accumulator, %d7 texture step; %a0 chunky walker, %a1 SpikeRay walker, %a2 the job,
| %a3 the pair's first chunky word, %a4/%a5 the even/odd texture bases, %a6 the texture column.

    .macro  WALL_STORE_EVEN
    move.w  (%a6,%d0.w),(%a0)       | 18
    .endm

    .macro  WALL_STORE_ODD
    move.w  (%a6,%d0.w),%d1         | 14
    or.w    %d1,(%a0)               | 12
    .endm

    .macro  SOLID_STORE_EVEN
    move.w  %d1,(%a0)               |  8
    .endm

    .macro  SOLID_STORE_ODD
    or.w    %d1,(%a0)               | 12
    .endm

| \solid, \wall   the two store policies above
| \texbase        %a4 (even) or %a5 (odd)
| \ceil, \floor   the job's pre-scaled ceiling and floor values for this parity
    .macro  DRAW_COLUMN solid, wall, texbase, ceil, floor
    move.w  DRAW_BAND_BOTTOM(%a2),%d3
    sub.w   RAY_TOP(%a1),%d3
    sub.w   RAY_ROWS(%a1),%d3       | floor rows, kept for after the wall run clobbers %d4
    move.w  RAY_TOP(%a1),%d4
    sub.w   DRAW_BAND_TOP(%a2),%d4  | ceiling rows
    subq.w  #1,%d4
    bmi.w   1f
    move.w  \ceil(%a2),%d1
0:                                  | ceiling: 26 (even) / 30 (odd) cycles per pixel
    \solid
    adda.w  %d5,%a0                 |  8
    dbra    %d4,0b                  | 10
1:
    move.w  RAY_ROWS(%a1),%d4
    subq.w  #1,%d4
    bmi.w   2f
    moveq   #0,%d0
    move.w  RAY_TEX_OFFSET(%a1),%d0
    movea.l \texbase,%a6
    adda.l  %d0,%a6
    move.l  RAY_TEX_POS(%a1),%d6
    move.l  RAY_TEX_STEP(%a1),%d7
3:                                  | wall: 56 (even) / 64 (odd) cycles per pixel
    move.l  %d6,%d0                 |  4
    swap    %d0                     |  4   integer part == texel index, 0..TEX_SIZE-1
    add.w   %d0,%d0                 |  4   ...to an even byte offset inside the column
    add.l   %d7,%d6                 |  8
    \wall
    adda.w  %d5,%a0                 |  8
    dbra    %d4,3b                  | 10
2:
    move.w  %d3,%d4
    subq.w  #1,%d4
    bmi.w   4f
    move.w  \floor(%a2),%d1
5:
    \solid
    adda.w  %d5,%a0
    dbra    %d4,5b
4:
    lea     RAY_SIZEOF(%a1),%a1
    .endm

    DRAW_SAVED_BYTES = 44           | movem.l %d2-%d7/%a2-%a6 == 11 registers
    DRAW_ARG_JOB     = DRAW_SAVED_BYTES + 4

    .globl  spike_draw_columns
spike_draw_columns:
    movem.l %d2-%d7/%a2-%a6,-(%sp)
    move.l  DRAW_ARG_JOB(%sp),%a2
    move.l  DRAW_CHUNKY(%a2),%a3
    move.l  DRAW_RAYS(%a2),%a1
    move.l  DRAW_TEX_EVEN(%a2),%a4
    move.l  DRAW_TEX_ODD(%a2),%a5
    move.w  DRAW_STRIDE(%a2),%d5
    move.w  DRAW_PAIRS(%a2),%d2
    subq.w  #1,%d2
    bmi.w   9000f
9001:
    move.l  %a3,%a0
    DRAW_COLUMN SOLID_STORE_EVEN, WALL_STORE_EVEN, %a4, DRAW_CEIL_EVEN, DRAW_FLOOR_EVEN
    move.l  %a3,%a0                 | ...both columns of a pair write the same chunky words
    DRAW_COLUMN SOLID_STORE_ODD, WALL_STORE_ODD, %a5, DRAW_CEIL_ODD, DRAW_FLOOR_ODD
    addq.l  #2,%a3
    dbra    %d2,9001b
9000:
    movem.l (%sp)+,%d2-%d7/%a2-%a6
    rts

| ============================================================== chunky to planar ================
|
| void spike_c2p_high(const unsigned short *chunky, unsigned char *screen, int rows)
| void spike_c2p_low (const unsigned short *chunky, unsigned char *screen, int rows)
|
| One 16-screen-pixel group is four interleaved plane words == two longwords, and both are built by
| OR-ing table entries that are ALREADY in their final bit positions: one table per pair position
| (four of them at high detail, two at low), each entry C2P_ENTRY_BYTES wide holding planes 0/1 at
| +0 and planes 2/3 at +C2P_PLANE23_OFF. The chunky word IS the byte offset into that table, so the
| loop never shifts, masks or packs — it reads, ORs, and stores.
|
| Line doubling is the second store pair through %a3 == %a2 + one screen line. Writing the second
| line here costs 24 cycles per group; a separate MOVEM copy pass of the finished line measured
| ~2.2 cycles/byte == 33 cycles per group's worth, so the inline write is the cheaper of the two and
| needs no second pass over the image.
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

    .globl  spike_c2p_high
spike_c2p_high:
    movem.l %d2-%d7/%a2-%a6,-(%sp)
    move.l  C2P_ARG_CHUNKY(%sp),%a0
    move.l  C2P_ARG_SCREEN(%sp),%a2
    move.l  C2P_ARG_ROWS(%sp),%d7
    lea     SCREEN_BYTES_PER_LINE(%a2),%a3
    lea     spike_c2p_table_high,%a1
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
    lea     SCREEN_BYTES_PER_LINE(%a2),%a2      | ...past the line %a3 just wrote
    lea     SCREEN_BYTES_PER_LINE(%a3),%a3
    dbra    %d7,8001b
8000:
    movem.l (%sp)+,%d2-%d7/%a2-%a6
    rts

    .globl  spike_c2p_low
spike_c2p_low:
    movem.l %d2-%d7/%a2-%a6,-(%sp)
    move.l  C2P_ARG_CHUNKY(%sp),%a0
    move.l  C2P_ARG_SCREEN(%sp),%a2
    move.l  C2P_ARG_ROWS(%sp),%d7
    lea     SCREEN_BYTES_PER_LINE(%a2),%a3
    lea     spike_c2p_table_low,%a1
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
    lea     SCREEN_BYTES_PER_LINE(%a2),%a2
    lea     SCREEN_BYTES_PER_LINE(%a3),%a3
    dbra    %d7,7001b
7000:
    movem.l (%sp)+,%d2-%d7/%a2-%a6
    rts

| ============================================================== the solid fill ==================
|
| void spike_fill(void *dst, long bytes, unsigned long plane01, unsigned long plane23)
|
| Fills whole screen lines with one pen, for the ceiling and floor bands the walls never reach. Ten
| registers per MOVEM is FILL_CHUNK_BYTES of screen, and the fill runs BACKWARD because the 68000's
| register-to-memory MOVEM takes predecrement and not postincrement. Predecrement stores A7..D0 in
| descending addresses, so ascending memory reads back d0,d1,...,d7,a3,a4 — which is why the pattern
| is loaded alternating plane01/plane23 in exactly that order.
|
| EXPECTED per chunk: movem.l 10 regs (8 + 8*10 = 88) + cmpa.l (6) + bne (10) = 104 / 40 bytes
|                     = 2.6 cycles per byte.

    FILL_SAVED_BYTES = 32           | movem.l %d2-%d7/%a3-%a4 == 8 registers
    FILL_ARG_DST     = FILL_SAVED_BYTES + 4
    FILL_ARG_BYTES   = FILL_SAVED_BYTES + 8
    FILL_ARG_PLANE01 = FILL_SAVED_BYTES + 12
    FILL_ARG_PLANE23 = FILL_SAVED_BYTES + 16

    .globl  spike_fill
spike_fill:
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
    bne.s   6001b                               | 10
6000:
    movem.l (%sp)+,%d2-%d7/%a3-%a4
    rts

| ============================================================== the clock ======================
|
| unsigned long spike_ticks(void)   — SUPERVISOR ONLY (it reads _hz_200 below $800).
|
| TOS's 200 Hz counter gives 5 ms, which is far too coarse to time a stage that costs 20; the MFP's
| timer C down-counter is the SAME clock's sub-tick part, one unit per TIMER_TICK_NS. Reading both
| is a race, so _hz_200 is read either side of the counter and the pair is retried if it moved:
| equal reads prove no tick landed in the window, which is what makes the counter belong to it.
| Interrupts stay ENABLED — masking them would stop the clock this routine is reading.
|
| The multiply by TIMER_C_RELOAD is two shifts and an add rather than `mulu`, because `mulu` is
| 16x16 and _hz_200 outgrows a word after 5.5 minutes of emulated time.

    .globl  spike_ticks
spike_ticks:
    movem.l %d2-%d3,-(%sp)
5001:
    move.l  (HZ_200_ADDR).w,%d0
    moveq   #0,%d1
    move.b  TIMER_C_DATA_ADDR,%d1
    move.l  (HZ_200_ADDR).w,%d2
    cmp.l   %d0,%d2
    bne.s   5001b
    move.l  %d0,%d3
    lsl.l   #7,%d0                              | * 128
    lsl.l   #6,%d3                              | *  64
    add.l   %d3,%d0                             | * 192 == TIMER_C_RELOAD
    move.l  #TIMER_C_RELOAD,%d2     | moveq only reaches 127
    sub.l   %d1,%d2                             | the counter counts DOWN
    add.l   %d2,%d0
    movem.l (%sp)+,%d2-%d3
    rts

| unsigned long spike_timer_c_read(void) — the raw down-counter, for the run's own check that
| TIMER_C_RELOAD is what this TOS actually programmed. SUPERVISOR ONLY.
    .globl  spike_timer_c_read
spike_timer_c_read:
    moveq   #0,%d0
    move.b  TIMER_C_DATA_ADDR,%d0
    rts

| ============================================================== 32/16 division ==================
|
| unsigned short spike_divu(unsigned long numerator, unsigned short denominator)
|
| The raycaster's ONE division: the wall's pixel height, (VIEW_H << 8) / distance_8_8. Written here
| because C would promote both operands and call libgcc's __udivsi3, a 32/32 routine costing several
| hundred cycles, where the 68000's own DIVU does 32/16 in about 140. The caller guarantees a
| non-zero denominator and a quotient inside a word (the numerator is VIEW_H << 8 and the
| denominator is at least 1), which is what DIVU needs to not overflow — on overflow it sets V and
| leaves the destination untouched, which would silently return the numerator's low word.

    .globl  spike_divu
spike_divu:
    move.l  4(%sp),%d0
    move.w  10(%sp),%d1             | short in a 4-byte slot: the value is the LOW word
    divu    %d1,%d0
    and.l   #0xffff,%d0             | ...the remainder rides in the high word
    rts
