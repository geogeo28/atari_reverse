| frame_draw.S — the asm twin for the frame loop's FOURTH STAGE, TRANSCRIBED from the original.
|
|   frame_draw_objects_and_collide_asm  <- the original @ [0x11c00, 0x11d30), the C reference
|                                          frame_draw_objects_and_collide in ../frame.c
|
| WHAT A TWIN IS is written out in scroll_emit.S and in README.md beside it, and holds here word for
| word: the C in ../frame.c is byte-for-byte equivalent to the original (test/test_frame.py's
| differential against the Musashi oracle), the original's own instructions are in
| ../../out/prg_dis.txt, and everything from `.Lbody` on is that instruction sequence in order.
|
| WHY THIS ONE, AND WHY IT WAS NOT WAVE D'S. This is the ONE slice of the frame's five that no
| earlier wave twinned, and the reason it was passed over is the reason it turned out to matter.
| Every instrument the campaign used before it was an AVERAGE — a profiler window, a mean cycles/frame
| — and this stage's cost is a function of HOW MANY ENTITIES ARE ON SCREEN: it draws all twenty
| slots and then walks every ORDERED PAIR of them. On a quiet frame it is 22,970 cycles of the
| original's and 32,720 of ours; on a busy one (the entity table's eleven actor slots all live, which
| `atari/census.py` stages out of the oracle playing the real game) it is 91,038 against 132,094.
| An average over both hides the second reading inside the first, and the second is the frame a
| player feels. `atari/bench_tier.py` is the instrument that separates them, and README.md's
| PERFORMANCE section carries the table.
|
| WHERE THE 41,056 CYCLES WENT, measured part by part on that busy frame rather than inferred:
|
|     asteroids_draw                      +398    the C core, unchanged by this twin
|     draw_sprite_masked_collide x14    +4,212    the wave-B twin, already 1.06x — see below
|     object_pair_overlap_mark x51      +4,480    transcribed here, in this blob
|     the stage's own loops and glue   +31,966    5.05x, and the whole of what this file is for
|
| So this twin claims the last two rows. MEASURED after the fact, on target: the stage goes from
| 132,094 to **96,436** against the original's 91,038 — **35,658 cycles collected**, 11% of a release
| slot, against a frame that was missing its slot by under 2%. The first row is untouched C.
|
| (The cost bars in test_asm_frame_draw.py read 95,146 for the same frame, and the 1,290-cycle
| difference is the CALLBACK DOOR: off target `jsr asteroids_draw` costs the emulated machine
| nothing, on target it is a real call. The suite's figure is this twin's own instructions; the
| bench's is what the machine executes.) **THE SECOND
| ROW IS NOT CLAIMED AND IS NOT A DEFECT IN THE SPRITE TWIN**: its +301 a call is the C ABI at the
| seam — this file's trampoline turns two pointers into image offsets and `draw_sprite_masked_collide_asm`'s
| own prologue turns them straight back into pointers. Closing it needs a second, register-ABI entry
| point in sprite.S, which is a change to a shipped and pinned twin and is deliberately not made
| here; STATUS.md carries it as the named next step.
|
| ================================================================================================
| THE REGISTER MAP, and it is the whole of the judgement in this file.
|
| The original uses EVERY address register: %a0 (the mask-table cursor), %a1 (the right record),
| %a2 (the left record), %a3 and %a4 (their rows), %a5 and %a6 (their indices, held in address
| registers because `object_pair_overlap_mark` reads them with `move.l a5,d0`). Six of those seven
| are live at once inside the inner pair loop, and the reconstruction needs one more register than
| the original did — a base for the globals, because the original IS the image and reads them
| absolutely (`tst.b $198b0.l`) where we must read them base-relative.
|
| The seventh register is found rather than freed, and the observation that finds it is that %a0's
| ONE use — the mask-table clear at 0x11c5a..0x11c62 — is over before the pair loop starts and
| overlaps nothing. So:
|
|     %a0 = image + FGB     the globals' window, live from the prologue to the last instruction
|     %a1 = the original's %a1 ...AND its %a0, whose live range at 0x11c5a is disjoint from %a1's
|     %a2 %a3 %a4 %a5 %a6 = the original's own, UNPERMUTED
|
| **KEEPING %a3-%a6 UNPERMUTED IS WHAT BUYS THE BYTE PIN.** `object_pair_overlap_mark`'s tail
| [0x11cfe, 0x11d30) names no absolute address and carries no immediate-to-Dn operation, so it is
| byte-identical to the original's own machine code — 50 bytes of it, pinned by
| test_asm_frame_draw.py. Had the window taken %a5 or %a6 (frame.S's convention), `move.l a5,d0`
| would have assembled to different bytes and that pin would not exist. Wave D's frame_spawn.S
| permuted and said so; this file did the arithmetic the other way and got a check out of it.
|
| **%a0 IS CALL-CLOBBERED BY THE C ABI**, which is the price of that choice: every trampoline below
| saves and restores it, 24 cycles the round trip. Two of the three sites run once a frame, but the
| SPRITE one runs once per live record — sixteen executions on the busy frame, so about **384 cycles
| a frame**, 0.4% of the stage. That is the price of the byte pin over the routine that runs
| fifty-one times, and it is worth stating as a number rather than as "about 40", which is what this
| paragraph said until the review did the arithmetic.
|
| FGB = 0x18000. The globals this stage names span 0x17a8e..0x19efe, so every displacement off %a0
| lands in [-0x572, +0x1efe] — inside the signed 16-bit window with room to spare, and
| test_asm_frame_draw.py asserts exactly that over the whole list rather than trusting this sentence.
|
| ================================================================================================
| WHAT CALLS WHAT.
|
|   0x11c00  asteroids_draw            a C core -> the door (off target) / a real jsr (on target)
|   0x11c22  mothership_segments_update  ...the same
|   0x11c48  draw_sprite_masked_collide  the WAVE-B TWIN, and it is in THIS BLOB: every `.S` under
|            src/asm assembles together (kit.mk's $(ASM_ELF)), so this is a plain call in both builds and
|            needs no door slot. It does mean this file depends on sprite.S being assembled beside
|            it, which it always is — the glob is not conditional.
|   0x11c9e  object_pair_overlap_mark  IN-BLOB, and the point of the exercise: the original's own
|            `bsr` survives as a `bsr` into the transcribed body below (wave B's `draw_char`
|            precedent — 18 cycles, no marshalling, no door), where the C paid a seven-argument
|            call fifty-one times a busy frame.
|
| THE EXIT. The original does not `rts`: it `bra`s to 0x11d30, the next slice. `frame_loop_once`
| stays C and calls the slices in order, so the twin simply returns there.
|
| REGISTERS. The prologue saves %d2-%d7/%a2-%a6 — every callee-saved register the stage touches.
| **The surface that catches a clobbered callee-saved register is NOT the differential** (it compares
| the image, and a corrupted %a2 leaves the image perfect and breaks the C CALLER instead): it is
| `bash atari/build.sh game && python3 atari/smoke.py game`. README.md's "Registers" says so at
| length, and it is why this twin is not done until the game smoke is green.
|
| WHAT IS BYTE-PINNED AND WHAT IS NOT. The tail above is. The rest is not, and the reason is
| README.md's two known ones: almost every instruction outside it mentions a global, which is
| base-relative here and absolute there; and gas re-spells `cmp.w #imm,Dn` as CMPI and
| `and.w #imm,Dn` as ANDI (same length, same cycles, a different opcode word), which the stage's
| mothership gate and the pair test both use. What stands in its place is the differential over the
| staged worlds, the cost bars, and the transcription-order pin — all 86 of the original's
| instruction addresses present exactly once, in ascending order, no gaps and no extras.

        .text

| WHICH BUILD IS THIS — frame.S's comment applies verbatim; the kit defines
| RECREATE_HOST_DIFFERENTIAL for the off-target assembly and the target build defines nothing.
#ifdef RECREATE_HOST_DIFFERENTIAL
# define ZY_ASM_FRAME_DOOR 1
#endif

| ---- the constants, named exactly as the headers in ../../include name them --------------------
| test/test_constants.py::test_asm_twin_equates_match_the_headers pins every one of these to its
| header, and requires every .S to contribute at least one.
        .equ    A_entity_collision_masks,      0x18252     | collision.h
        .equ    A_entity_table,                0x17a8e     | player.h
        .equ    A_mothership_index,            0x1987c     | init.h
        .equ    A_mothership_phase_timer,      0x19efe     | mothership.h
        .equ    A_mothership_ready,            0x198b0     | mothership.h
        .equ    COLLISION_ROW_BYTES,           4           | collision.h
        .equ    ENTITY_ALIVE,                  0x0e        | entity.h
        .equ    ENTITY_HEIGHT,                 0x08        | entity.h
        .equ    ENTITY_HEIGHT_MASK,            0x7fff      | collision.h
        .equ    ENTITY_PIXEL_HIT,              0x0f        | entity.h
        .equ    ENTITY_SLOTS,                  0x14        | frame.h
        .equ    ENTITY_STRIDE,                 0x2c        | entity.h
        .equ    ENTITY_X,                      0x00        | entity.h
        .equ    ENTITY_Y,                      0x04        | entity.h
        .equ    MOTHERSHIP_INDEX_SEGMENTED,    5           | frame.h
| OBJECT_BOX_WIDTH is ../collision.c's own `#define`, not a header's, so test_constants.py's equate
| pin — which only covers `.equ` names a header ALSO defines — skips it in silence.
| test_asm_frame_draw.py::test_the_box_width_equate_is_collision_cs_own is what pins it instead, and
| it reads the `#define` out of ../collision.c rather than restating the number.
        .equ    OBJECT_BOX_WIDTH,              0x10        | collision.c

| COLLISION_MASK_LONGS is `ENTITY_SLOTS + 1` in frame.h — an expression, so test_constants.py
| recomputes it through ASM_DERIVED_PINS rather than reading a literal.
        .equ    COLLISION_MASK_LONGS,          ENTITY_SLOTS + 1

| The door slots this file adds to the frame family's namespace. test/asm_frame_common.py's
| DOOR_TABLE is the other half and test_asm_frame_doors.py pins the two equal; 0-59 are waves C
| and D's and are not renumbered.
        .equ    ZY_DOOR_asteroids_draw,             60
        .equ    ZY_DOOR_mothership_segments_update, 61

| The global window's origin — this file's own constant, not a header's. What makes it right is that
| every global the stage names lands within a signed 16-bit displacement of it, which
| test_asm_frame_draw.py asserts over the whole list.
        .equ    FGB, 0x18000

| What the prologue pushes, and every argument offset measured past it.
        .equ    SAVED, (11 * 4)                 | %d2-%d7/%a2-%a6
        .equ    ARG_IMAGE, 4 + SAVED

        .macro  DRAW_PROLOGUE
        movem.l %d2-%d7/%a2-%a6,-(%sp)
        movea.l ARG_IMAGE(%sp),%a0
        adda.l  #FGB,%a0                        | the globals' window; the raw base is %a0 - FGB
        .endm

        .macro  DRAW_EPILOGUE
        movem.l (%sp)+,%d2-%d7/%a2-%a6
        rts
        .endm

| ================================================================================================
| void frame_draw_objects_and_collide_asm(uint8_t *image)
| ================================================================================================
        .globl  frame_draw_objects_and_collide_asm
frame_draw_objects_and_collide_asm:
        DRAW_PROLOGUE

| ---- the asteroid columns, then the mothership's segments (0x11c00) ----------------------------
    jbsr    door_asteroids_draw                             | 011c00 bsr.w $159be
    tst.b   A_mothership_ready-FGB(%a0)                     | 011c04 tst.b $198b0.l
    jbeq    .L11c30                                         | 011c0a
    move.b  A_mothership_index-FGB(%a0),%d2                 | 011c0e move.b $1987c.l,d2
    ext.w   %d2                                             | 011c14
    cmp.w   #MOTHERSHIP_INDEX_SEGMENTED,%d2                 | 011c16 cmp.w #$5,d2
    jbge    .L11c22                                         | 011c1a
    jbra    .L11c30                                         | 011c1e
.L11c22:
    jbsr    door_mothership_segments_update                 | 011c22 bsr.w $151ba
    addi.l  #1,A_mothership_phase_timer-FGB(%a0)            | 011c26 addi.l #$1,$19efe.l

| ---- draw all twenty entity slots; the blitter publishes each record's pixel-hit byte (0x11c30) --
.L11c30:
    moveq   #ENTITY_SLOTS - 1,%d0                           | 011c30 moveq #$13,d0
    lea     A_entity_table-FGB(%a0),%a2                     | 011c32 lea $17a8e.l,a2
.L11c38:
    move.l  %d0,-(%sp)                                      | 011c38
    lea     ENTITY_PIXEL_HIT(%a2),%a5                       | 011c3a lea 15(a2),a5
    clr.b   (%a5)                                           | 011c3e
    tst.b   ENTITY_ALIVE(%a2)                               | 011c40 tst.b 14(a2)
    jbeq    .L11c4c                                         | 011c44
    jbsr    call_draw_sprite_masked_collide                 | 011c48 bsr.w $15b7c
.L11c4c:
    lea     ENTITY_STRIDE(%a2),%a2                          | 011c4c lea 44(a2),a2
    move.l  (%sp)+,%d0                                      | 011c50
    dbf     %d0,.L11c38                                     | 011c52

| ---- clear the overlap table, one longword per slot and one past it (0x11c56) -------------------
| %a1 stands in for the original's %a0 here — see the register map in the header.
    move.w  #COLLISION_MASK_LONGS - 1,%d0                   | 011c56 move.w #$14,d0
    lea     A_entity_collision_masks-FGB(%a0),%a1           | 011c5a lea $18252.l,a0
.L11c60:
    clr.l   (%a1)+                                          | 011c60 clr.l (a0)+
    dbf     %d0,.L11c60                                     | 011c62

| ---- the ordered-pair walk: entity `left` against every entity BELOW it (0x11c66) ---------------
| The outer walk starts at slot 1 because slot 0 is never a `left`; the inner one stops when its
| index reaches the outer's, so each pair is visited once and one call marks both rows.
    move.l  #1,%d0                                          | 011c66
    lea     A_entity_collision_masks+COLLISION_ROW_BYTES-FGB(%a0),%a3 | 011c6c lea $18256.l,a3
    lea     A_entity_table+ENTITY_STRIDE-FGB(%a0),%a2       | 011c72 lea $17aba.l,a2
.L11c78:
    tst.b   ENTITY_PIXEL_HIT(%a2)                           | 011c78 tst.b 15(a2)
    jbeq    .L11cb8                                         | 011c7c
    move.l  %d0,-(%sp)                                      | 011c80
    movea.l #0,%a6                                          | 011c82
    lea     A_entity_collision_masks-FGB(%a0),%a4           | 011c88 lea $18252.l,a4
    lea     A_entity_table-FGB(%a0),%a1                     | 011c8e lea $17a8e.l,a1
    movea.l %d0,%a5                                         | 011c94
.L11c96:
    tst.b   ENTITY_ALIVE(%a1)                               | 011c96 tst.b 14(a1)
    jbeq    .L11ca2                                         | 011c9a
    jbsr    .Lpair                                          | 011c9e bsr.w $11cce — IN-BLOB
.L11ca2:
    lea     1(%a6),%a6                                      | 011ca2
    lea     COLLISION_ROW_BYTES(%a4),%a4                     | 011ca6 lea 4(a4),a4
    lea     ENTITY_STRIDE(%a1),%a1                          | 011caa lea 44(a1),a1
    cmpa.l  %a6,%a5                                         | 011cae
    jbeq    .L11cb6                                         | 011cb0
    jbra    .L11c96                                         | 011cb4 bra.s $11c96
.L11cb6:
    move.l  (%sp)+,%d0                                      | 011cb6
.L11cb8:
    addq.l  #1,%d0                                          | 011cb8
    lea     ENTITY_STRIDE(%a2),%a2                          | 011cba
    lea     COLLISION_ROW_BYTES(%a3),%a3                     | 011cbe
    cmp.l   #ENTITY_SLOTS,%d0                               | 011cc2
    jbne    .L11c78                                         | 011cc8
    jbra    .Ldone                                          | 011cca bra.w $11d30 — the next slice

| ================================================================================================
| object_pair_overlap_mark @ 0x11cce — the all-pairs box test, reached by the `bsr` above.
|
| %a2 / %a1 are the two records, %a3 / %a4 their rows, %a5 / %a6 their indices — the original's own
| registers, unpermuted, which is what lets the tail below be byte-identical. It touches no global
| and makes no call, so nothing in it needed translating at all.
| ================================================================================================
.Lpair:
    move.w  ENTITY_X(%a2),%d0                               | 011cce move.w 0(a2),d0
    move.w  ENTITY_Y(%a2),%d1                               | 011cd2 move.w 4(a2),d1
    move.w  ENTITY_HEIGHT(%a2),%d2                          | 011cd6 move.w 8(a2),d2
    and.w   #ENTITY_HEIGHT_MASK,%d2                         | 011cda and.w #$7fff,d2
    move.w  ENTITY_X(%a1),%d4                               | 011cde move.w 0(a1),d4
    move.w  ENTITY_Y(%a1),%d5                               | 011ce2 move.w 4(a1),d5
    move.w  ENTITY_HEIGHT(%a1),%d6                          | 011ce6 move.w 8(a1),d6
    and.w   #ENTITY_HEIGHT_MASK,%d6                         | 011cea and.w #$7fff,d6
    add.w   %d1,%d2                                         | 011cee — the left box's bottom edge
    move.w  %d0,%d3                                         | 011cf0
    add.w   #OBJECT_BOX_WIDTH,%d3                           | 011cf2 — ...and its right edge
    add.w   %d5,%d6                                         | 011cf6 — the right box's bottom edge
    move.w  %d4,%d7                                         | 011cf8
    add.w   #OBJECT_BOX_WIDTH,%d7                           | 011cfa — ...and its right edge
        .globl  frame_draw_pair_tail_body
| The 50 byte-identical bytes: four signed `blt`/`rts` rejections and the reciprocal mark. No
| absolute address, no immediate-to-Dn operation, and no permuted register — so this span IS the
| original's machine code, and test_asm_frame_draw.py compares it byte for byte.
frame_draw_pair_tail_body:
    cmp.w   %d2,%d5                                         | 011cfe
    blt.w   .L11d06                                         | 011d00
    rts                                                     | 011d04
.L11d06:
    cmp.w   %d7,%d0                                         | 011d06
    blt.w   .L11d0e                                         | 011d08
    rts                                                     | 011d0c
.L11d0e:
    cmp.w   %d3,%d4                                         | 011d0e
    blt.w   .L11d16                                         | 011d10
    rts                                                     | 011d14
.L11d16:
    cmp.w   %d6,%d1                                         | 011d16
    blt.w   .L11d1e                                         | 011d18
    rts                                                     | 011d1c
.L11d1e:
    move.l  %a5,%d0                                         | 011d1e
    move.l  %a6,%d1                                         | 011d20
    move.l  (%a3),%d3                                       | 011d22 — BOTH rows are read before
    move.l  (%a4),%d4                                       | 011d24   either is stored
    bset    %d1,%d3                                         | 011d26
    bset    %d0,%d4                                         | 011d28
    move.l  %d3,(%a3)                                       | 011d2a
    move.l  %d4,(%a4)                                       | 011d2c
    rts                                                     | 011d2e
        .globl  frame_draw_pair_tail_body_end
frame_draw_pair_tail_body_end:

.Ldone:
        DRAW_EPILOGUE

| ================================================================================================
| THE TRAMPOLINES. frame.S's long note on what a trampoline is and why holds here; this file has
| three and they are the simplest shape it describes, because nothing in this stage reads an answer
| out of a callee — every one of the three C cores is `void` and the stage branches on nothing they
| leave. So there is no Z, no X and no D0 to marshal, and each block is: save the window register the
| C ABI does not preserve, form the image base, push, call, unwind, restore.
|
| WHY %a0 AND NOTHING ELSE IS SAVED — and the reason is DEAD AT THESE THREE SITES, not "unused".
| %a1 is very much used: it is the mask-table cursor at 0x11c5a-0x11c62 and the inner loop's
| right-record cursor at 0x11c8e-0x11caa, live across every one of the fifty-one `bsr .Lpair`
| visits. What is true is narrower and is what licenses this: at the three CALL SITES %d0 is on the
| stack (the original's own `move.l d0,-(a7)` at 0x11c38 brackets the sprite call), %d1 and %a1 hold
| nothing live, and the live pointers %a2 and %a5 are callee-saved by the ABI. Saving the whole file
| with frame.S's SCRATCH_SAVE would cost 84 cycles a call for nothing.
|
| **A DOOR CALL ADDED INSIDE THE PAIR LOOP WOULD BREAK THAT**, and STATUS.md's named next lever
| (a register-ABI entry point at the sprite seam) is the kind of change that might reach for one:
| a C callee clobbers %a1, which there is the right-record cursor, and the walk would run off into
| the image. Such a site needs the full SCRATCH_SAVE.
|
| `suba.l` AND NOT `sub.l`, exactly as frame.S's PUSH_OFFSET: SUBA touches no condition code, so the
| pointer-to-offset arithmetic is invisible where the original had none. Nothing in this stage reads
| a flag across a call today, so it is a property being preserved rather than one being relied on.
|
| **BUT THE WINDOW SAVE IS NOT CONDITION-CODE TRANSPARENT, AND THESE STUBS ARE THEREFORE NOT**, which
| the paragraph above used to imply and does not any more. `move.l %a0,-(%sp)` sets N/Z/V/C (X
| survives). frame.S's SCRATCH_SAVE is a `movem`, which touches no flag, and that is exactly why ITS
| stubs can carry a Z or an X across a call deliberately — a thing no stub here does.
|
| **MEASURED BOTH WAYS RATHER THAN ARGUED.** Spelling the save `movem.l %a0,-(%sp)` makes the
| transparency real and costs 11 cycles a round trip — 16 executions a busy frame, ~176 cycles —
| and the cost bars redden on both bands, which is the bars doing their job. Paying that for a
| property nothing in this stage reads would be buying a guarantee with cycles, so the `move` stays
| and the limitation is written down instead: **every one of the three call sites returns onto an
| instruction that sets the flags it needs** (`tst.b` at 0x11c04, `addi.l` at 0x11c26, and the
| `move.l (a7)+,d0` + `dbf` pair after the sprite call), so nothing reads a flag this clobbers.
| A FUTURE SITE THAT DID would need `movem` here, and its bar would move by 11 cycles a call.
| ================================================================================================
#ifdef ZY_ASM_FRAME_DOOR
# define ZY_CALL(slot, fn)      jsr     (RECREATE_DOOR_BASE + (slot) * RECREATE_DOOR_STRIDE)
#else
# define ZY_CALL(slot, fn)      jsr     fn
#endif

| The image base is `%a0 - FGB`, and %a0 is the one register the C ABI will not preserve for us. So
| a trampoline stacks the window, reuses %a0 for the base its callee wants, and puts the window back
| on the way out — the body either side of the call sees %a0 unchanged.
        .macro  SAVE_WINDOW_AND_FORM_BASE
        move.l  %a0,-(%sp)              | sets N/Z/V/C — see the header: no site here reads them
        suba.l  #FGB,%a0
        .endm
        .macro  RESTORE_WINDOW
        movea.l (%sp)+,%a0
        .endm

| ---- void asteroids_draw(uint8_t *image) ----
        .globl  door_asteroids_draw
door_asteroids_draw:
        SAVE_WINDOW_AND_FORM_BASE
        move.l  %a0,-(%sp)
        ZY_CALL(ZY_DOOR_asteroids_draw, asteroids_draw)
        addq.l  #4,%sp
        RESTORE_WINDOW
        rts

| ---- void mothership_segments_update(uint8_t *image) ----
        .globl  door_mothership_segments_update
door_mothership_segments_update:
        SAVE_WINDOW_AND_FORM_BASE
        move.l  %a0,-(%sp)
        ZY_CALL(ZY_DOOR_mothership_segments_update, mothership_segments_update)
        addq.l  #4,%sp
        RESTORE_WINDOW
        rts

| ---- void draw_sprite_masked_collide(uint8_t *image, uint32_t entity, uint32_t hit_flag) ----
|
| NOT A DOOR: the wave-B twin is in this same blob, so the call links in both builds. The hit flag
| is the record's own offset plus ENTITY_PIXEL_HIT, which is what the original's %a5 already is —
| so one `suba.l` serves both arguments and the second is a `pea` off the first.
        .globl  call_draw_sprite_masked_collide
call_draw_sprite_masked_collide:
        SAVE_WINDOW_AND_FORM_BASE
        movea.l %a2,%a1
        suba.l  %a0,%a1                         | %a1 = the record, as an image offset
        pea     ENTITY_PIXEL_HIT(%a1)           | ...its pixel-hit byte, the same way
        move.l  %a1,-(%sp)
        move.l  %a0,-(%sp)
        jbsr    draw_sprite_masked_collide_asm
        lea     12(%sp),%sp
        RESTORE_WINDOW
        rts
