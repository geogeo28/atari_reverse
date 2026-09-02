| frame_fire.S — the asm twin for the frame loop's DRONE-AND-FIRE STAGE, TRANSCRIBED from the
| original binary.
|
|   frame_drone_and_fire_stage_asm  <- the original @ [0x113c0, 0x1167c), the C reference
|                                      frame_drone_and_fire_stage in ../frame.c
|
| WHAT A TWIN IS is written out in README.md beside this file and in scroll_emit.S, and holds here
| word for word: the C in ../frame.c is byte-for-byte equivalent to the original
| (test/test_frame.py's differential against the Musashi oracle), the original's own instructions
| are in ../../out/prg_dis.txt, and everything from `frame_drone_and_fire_stage_body` on is that
| instruction sequence in order — 148 instructions, the smallest of wave D's three slices.
|
| WHAT THE SLICE DOES. Two halves, and ../frame.c cuts them into two statics. `frame_trail_drone`
| flies weapon 4's escort, which follows the ship's own position SHIP_POS_HISTORY_ENTRIES frames
| stale out of a ten-entry ring; launching it primes the whole ring with the ship's position so a
| fresh drone does not fly to the slot's previous occupant. `frame_fire_button` is the button's
| state machine: released it clears the charge state, held it counts up to a charged shot, and
| newly pressed it dispatches on the selected weapon — seeker, homing missile, bomb, the plain
| bullet, and an unknown weapon that fires nothing at all.
|
| WHAT IS EASY ABOUT IT, said plainly because the sibling twins are not: this slice calls nothing
| inside its own range, has no busy-wait and touches no hardware. Its whole door surface is the
| four `bsr`s at the foot, and the `#ifdef`-ed build split frame.S carries (its band 5) has no
| counterpart here. There is exactly one arm of it that no off-target surface reaches — none.
|
| THE TRANSLATIONS, and only these.
|
| **1. The image base — two registers, exactly as frame.S.** The original IS the image, so it reads
| globals absolutely (`tst.b $198b4.l`). The reconstruction is position-independent and gets the
| image as a pointer, so every one of the eighteen globals this slice ADDRESSES becomes
| base-relative (the two more it names are sprite banks, and those are immediates — see 3 below):
|
|     %a6 = image            the raw base, for the trampolines' pointer->offset arithmetic
|     %a5 = image + FGB      FGB = 0x18000, so `A_entity_table-FGB(%a5)` is -0x572 and
|                            `A_ship_pos_history-FGB(%a5)` is +0x1f86 — both inside the signed
|                            16-bit displacement a `d16(An)` carries
|
| The original uses only %a0, %a2-%a4 and %a7, so neither reserved register displaces one of its
| own. The body's address registers hold REAL POINTERS, exactly as the original's hold real
| addresses; only the trampolines convert back to offsets.
|
| **2. THE TWO ENTRY REGISTERS STAY PARAMETERS**, which is what ../../include/frame.h says and why:
| the range has its own entry point and a case drives it with values the globals do not hold. `ship`
| is %a2, which the head slice loaded with A_player_record at 0x111d0, and it arrives as an image
| OFFSET (the C signature's `uint32_t`) so the prologue adds the base to it once. `joystick` is %d0,
| which the head slice read out of A_joystick_state at 0x112a0, and it is a value rather than a
| pointer so it is taken as it comes. Both then behave exactly as the original's registers do —
| including %d0, which this slice pushes across the whole drone half (0x113c0/0x11474) and hands on
| to three of its four callees as their SOUND CHANNEL.
|
| A `uint8_t` argument still occupies a whole four-byte stack slot, which sprite.S establishes for
| this toolchain (`m68k-elf-gcc emits `pea` for one`), so ARG_JOYSTICK is read whole.
|
| **3. A pointer LOADED OUT OF THE IMAGE is an offset** — but this slice loads none: every address
| register it fills comes from a `lea` on a global or from stepping one on by ENTITY_STRIDE. The two
| longword IMMEDIATES it stores into a record's sprite field (A_gunsight_sprite,
| A_player_bullet_sprite) are ALREADY offsets in the reconstruction and are left alone, exactly as
| sprite.S leaves them.
|
| **THE BYTE PIN IS GONE, for frame.S's reason**: almost every instruction here names a global and
| position-independence re-encodes all of them. WHAT STANDS IN ITS PLACE is named in
| test/test_asm_frame_fire.py — the differential over staged worlds per fire arm, the cost bars, and
| the TRANSCRIPTION-ORDER pin (all 148 of the original's instruction addresses present exactly once,
| in ascending order, no gaps and no extras). That is weaker than bytes and this file does not
| pretend otherwise: it catches a band spliced out of order, an instruction dropped or a line
| duplicated, and it does not catch a wrong operand.
|
| REGISTERS. The body clobbers %d0, %d1, %d6, %d7, %a0, %a2, %a3 and %a4, of which %d6, %d7, %a2,
| %a3 and %a4 are callee-saved — so the prologue saves those five plus the two it reserves, and
| %d2-%d5 are neither touched nor saved. **The surface that catches a clobbered callee-saved
| register is NOT the differential** (it compares the image, and a corrupted %a3 leaves the image
| perfect and breaks the C CALLER instead): off target it is `AsmTwins.call`'s CALLEE_SAVED_SEEDS
| check, and on target `bash atari/build.sh game && python3 atari/smoke.py game`. README.md's
| "Registers" says so at length.

        .text

| WHICH BUILD IS THIS. The kit's Makefile defines RECREATE_HOST_DIFFERENTIAL for the off-target
| assembly (tools/recreate_kit/kit.mk's ASM_CFLAGS); the target build defines nothing. Spelt with
| this file's own private name for frame.S's reason — so the door reads as one story rather than as
| an appearance of a kit marker, and so atari/build.sh has nothing to pass.
#ifdef RECREATE_HOST_DIFFERENTIAL
# define ZY_ASM_FRAME_FIRE_DOOR 1
#endif


| ---- the constants, named exactly as the headers in ../../include name them --------------------
| test/test_constants.py::test_asm_twin_equates_match_the_headers pins every one of these to its
| header, and requires every .S to contribute at least one — so a name that drifted from its header
| fails rather than going unchecked.
        .equ    A_active_bullets,              0x19909     | init.h
        .equ    A_active_count_bombs,          0x1990c     | weapon.h
        .equ    A_active_count_seekers,        0x1990d     | weapon.h
        .equ    A_active_count_type32,         0x1990b     | weapon.h
        .equ    A_bullet_fire_toggle,          0x198c7     | frame.h
        .equ    A_charge_flash_dir,            0x19903     | frame.h
        .equ    A_entity_gunsight,             0x17dd2     | weapon.h
        .equ    A_entity_table,                0x17a8e     | player.h
        .equ    A_fire_button_held,            0x198b9     | frame.h
        .equ    A_fire_charge_counter,         0x19901     | frame.h
        .equ    A_fire_charged,                0x19902     | enemy.h
        .equ    A_gunsight_sprite,             0x6a61e     | highscore.h
        .equ    A_palette_hw_shadow,           0x18fc4     | irq.h
        .equ    A_player_bullet_sprite,        0x62a5e     | frame.h
        .equ    A_selected_weapon,             0x198b4     | weapon.h
        .equ    A_shield_level,                0x1990a     | weapon.h
        .equ    A_ship_pos_history,            0x19f86     | frame.h
        .equ    A_ship_pos_history_index,      0x198ff     | frame.h
        .equ    A_trail_drone_active,          0x19900     | weapon.h
        .equ    A_weapon_power_level,          0x19908     | player.h
        .equ    BULLET_ROWS,                   3           | frame.h
        .equ    BULLET_SOUND,                  0x0e        | frame.h
        .equ    BULLET_SPAWN_DX,               0x14        | frame.h
        .equ    BULLET_SPAWN_DY,               8           | frame.h
        .equ    BULLET_TYPE,                   0x34        | frame.h
        .equ    ENTITY_ALIVE,                  0x0e        | entity.h
        .equ    ENTITY_ANIM_FRAME,             0x20        | entity.h
        .equ    ENTITY_HEIGHT,                 0x08        | entity.h
        .equ    ENTITY_INDEX_TRAIL_DRONE,      0x13        | weapon.h
        .equ    ENTITY_SPRITE,                 0x0a        | entity.h
        .equ    ENTITY_STRIDE,                 0x2c        | entity.h
        .equ    ENTITY_TYPE,                   0x11        | entity.h
        .equ    ENTITY_X,                      0x00        | entity.h
        .equ    ENTITY_Y,                      0x04        | entity.h
        .equ    FIRE_CHARGE_FULL,              8           | frame.h
        .equ    PLAYER_SHOT_SLOTS,             6           | weapon.h
        .equ    SHIP_POS_HISTORY_ENTRIES,      0x0a        | frame.h
        .equ    TRAIL_DRONE_OFFSET_PACKED,     0x800005    | frame.h
        .equ    TRAIL_DRONE_ROWS,              9           | frame.h
        .equ    TYPE_TRAIL_DRONE,              0x35        | weapon.h
        .equ    WEAPON_BULLET,                 3           | frame.h
        .equ    WEAPON_KIND_BOMB,              1           | weapon.h
        .equ    WEAPON_KIND_MISSILE,           2           | weapon.h
        .equ    WEAPON_KIND_SEEKER,            4           | weapon.h
        .equ    WEAPON_SHOTS_WITHOUT_SHIELD,   1           | frame.h
        .equ    WEAPON_SHOTS_WITH_SHIELD,      2           | frame.h

| THE DOOR SLOTS ARE THE FAMILY'S. A slot names a HOST FUNCTION for the whole frame blob, so the
| numbers below are test/asm_frame_common.py's DOOR_TABLE and test_asm_frame_doors.py pins them
| against it. Slot 13 is WAVE C'S, reused rather than renumbered: `sound_start` is the same core
| reached with the same register contract, so this file also reuses frame.S's `door_sound_start`
| stub outright (it is `.globl` and the twins link as one blob) instead of writing a second one.
        .equ    ZY_DOOR_sound_start,           13
        .equ    ZY_DOOR_fire_seeker,           34
        .equ    ZY_DOOR_fire_homing_missile,   35
        .equ    ZY_DOOR_fire_bomb,             36


| The global window's origin, and frame.S's own value so the two files' `%a5` mean the same thing.
| Not a header constant: what makes it right is that every global this slice names lands within a
| signed 16-bit displacement of it, which test_asm_frame_fire.py asserts over the whole list — a
| global added later that fell outside is refused by gas ("displacement too large for this
| architecture"); this names the window and the offender instead of the architecture.
        .equ    FGB, 0x18000

| What the prologue pushes, and every argument offset measured past it.
        .equ    SAVED, (7 * 4)                  | %d6-%d7/%a2-%a6 — the body's callee-saved clobbers
        .equ    ARG_IMAGE,      4 + SAVED
        .equ    ARG_SHIP,       8 + SAVED
        .equ    ARG_JOYSTICK,  12 + SAVED

        .macro  FIRE_PROLOGUE
        movem.l %d6-%d7/%a2-%a6,-(%sp)
        movea.l ARG_IMAGE(%sp),%a6              | the raw image base
        movea.l %a6,%a5
        adda.l  #FGB,%a5                        | ...and the globals' window
        movea.l ARG_SHIP(%sp),%a2               | A2 — the ship record, which ARRIVES AS AN OFFSET
        adda.l  %a6,%a2
        move.l  ARG_JOYSTICK(%sp),%d0           | D0 — the joystick byte the head slice read
        .endm

        .macro  FIRE_EPILOGUE
        movem.l (%sp)+,%d6-%d7/%a2-%a6
        rts
        .endm

| ================================================================================================
| void frame_drone_and_fire_stage_asm(uint8_t *image, uint32_t ship, uint8_t joystick)
| ================================================================================================
        .globl  frame_drone_and_fire_stage_asm
frame_drone_and_fire_stage_asm:
        FIRE_PROLOGUE
        .globl  frame_drone_and_fire_stage_body
frame_drone_and_fire_stage_body:
| ==== the trail drone — 0x113c0 .. 0x11472 ======================================================
| ../frame.c's `frame_trail_drone`. The launch half (0x113dc..0x11426) runs only on the frame the
| gunsight record is dead AND weapon 4 is selected; the per-frame half below it runs always.
    move.l  %d0,-(%sp)                                      | 0113c0  the joystick, parked across the drone
    lea     A_entity_gunsight-FGB(%a5),%a3                  | 0113c2  lea $17dd2.l,a3
    tst.b   ENTITY_ALIVE(%a3)                               | 0113c8
    jbne    .L11428                                         | 0113cc
    cmpi.b  #WEAPON_KIND_SEEKER,A_selected_weapon-FGB(%a5)  | 0113d0  cmpi.b #$4,$198b4.l
    jbne    .L11474                                         | 0113d8
    movea.l %a3,%a4                                         | 0113dc
    move.b  #1,A_trail_drone_active-FGB(%a5)                | 0113de
    move.b  #1,ENTITY_ALIVE(%a3)                            | 0113e6
    move.b  #TYPE_TRAIL_DRONE,ENTITY_TYPE(%a3)              | 0113ec  move.b #$35,17(a3)
    move.l  #A_gunsight_sprite,ENTITY_SPRITE(%a3)           | 0113f2  an OFFSET already; not rebased
    move.w  #TRAIL_DRONE_ROWS,ENTITY_HEIGHT(%a3)            | 0113fa  move.w #$9,8(a3)
    move.w  ENTITY_X(%a2),%d0                               | 011400
    move.w  ENTITY_Y(%a2),%d1                               | 011404
    move.w  #SHIP_POS_HISTORY_ENTRIES-1,%d7                 | 011408  move.w #$9,d7
    lea     A_ship_pos_history-FGB(%a5),%a0                 | 01140c  lea $19f86.l,a0
.L11412:
    move.w  %d0,(%a0)+                                      | 011412
    move.w  %d1,(%a0)+                                      | 011414
    dbf     %d7,.L11412                                     | 011416
    clr.b   A_ship_pos_history_index-FGB(%a5)               | 01141a
    move.b  #0,A_active_count_seekers-FGB(%a5)              | 011420
.L11428:
    lea     A_ship_pos_history-FGB(%a5),%a0                 | 011428  lea $19f86.l,a0
    move.b  A_ship_pos_history_index-FGB(%a5),%d0           | 01142e
    ext.w   %d0                                             | 011434  SIGNED: the cursor is a signed byte
    lsl.w   #2,%d0                                          | 011436  ...times the entry's four bytes
    move.l  (%a0,%d0.w),%d1                                 | 011438  the oldest {x, y} pair
    add.l   #TRAIL_DRONE_OFFSET_PACKED,%d1                  | 01143c  ONE LONGWORD ADD: y carries into x
    move.w  %d1,ENTITY_Y(%a3)                               | 011442
    swap    %d1                                             | 011446
    move.w  %d1,ENTITY_X(%a3)                               | 011448
    move.w  ENTITY_X(%a2),%d1                               | 01144c
    swap    %d1                                             | 011450
    move.w  ENTITY_Y(%a2),%d1                               | 011452
    move.l  %d1,(%a0,%d0.w)                                 | 011456  the ship's position, into the ring
    addi.b  #1,A_ship_pos_history_index-FGB(%a5)            | 01145a
    cmpi.b  #SHIP_POS_HISTORY_ENTRIES,A_ship_pos_history_index-FGB(%a5) | 011462  cmpi.b #$a,$198ff.l
    jbne    .L11474                                         | 01146a  EQUALITY: an index already past ten stays
    clr.b   A_ship_pos_history_index-FGB(%a5)               | 01146e

| ==== the fire button — 0x11474 .. 0x115f2 ======================================================
| ../frame.c's `frame_fire_button`. Released clears the charge state, held counts to a charged
| shot, and a fresh press dispatches on A_selected_weapon.
.L11474:
    move.l  (%sp)+,%d0                                      | 011474  the joystick back
    tst.b   %d0                                             | 011476
    jbmi    .L1149e                                         | 011478  bit 7 = fire
    clr.b   A_fire_button_held-FGB(%a5)                     | 01147c
    clr.b   A_fire_charge_counter-FGB(%a5)                  | 011482
    clr.b   A_fire_charged-FGB(%a5)                         | 011488
    clr.w   A_palette_hw_shadow-FGB(%a5)                    | 01148e  the charged flash, back to black
    clr.b   A_charge_flash_dir-FGB(%a5)                     | 011494
    jbra    .Ldone                                          | 01149a
.L1149e:
    tst.b   A_fire_button_held-FGB(%a5)                     | 01149e
    jbeq    .L114d2                                         | 0114a4  clear -> this is a FRESH PRESS
    tst.b   A_fire_charged-FGB(%a5)                         | 0114a8
    jbne    .Ldone                                          | 0114ae
    addi.b  #1,A_fire_charge_counter-FGB(%a5)               | 0114b2
    cmpi.b  #FIRE_CHARGE_FULL,A_fire_charge_counter-FGB(%a5) | 0114ba  cmpi.b #$8,$19901.l
    jbne    .Ldone                                          | 0114c2  EQUALITY: 0xff wraps and keeps counting
    move.b  #1,A_fire_charged-FGB(%a5)                      | 0114c6
    jbra    .Ldone                                          | 0114ce

| ---- the fresh press, and the weapon dispatch under it ----
| The three counted arms have ONE shape: the shield's allowance in %d6, the weapon's own count in
| %d7, a signed compare that falls THROUGH to the plain bullet at 0x11600 when the count is at its
| limit, then a scan of entity slots 0..5 for a free record.
.L114d2:
    move.b  #1,A_fire_button_held-FGB(%a5)                  | 0114d2
    lea     A_entity_table-FGB(%a5),%a3                     | 0114da  lea $17a8e.l,a3 — shot slot 0
    cmpi.b  #WEAPON_KIND_SEEKER,A_selected_weapon-FGB(%a5)  | 0114e0
    jbne    .L1153e                                         | 0114e8
    move.b  A_shield_level-FGB(%a5),%d6                     | 0114ec
    tst.b   %d6                                             | 0114f2
    jbne    .L11500                                         | 0114f4
    move.b  #WEAPON_SHOTS_WITHOUT_SHIELD,%d6                | 0114f8
    jbra    .L11504                                         | 0114fc
.L11500:
    move.b  #WEAPON_SHOTS_WITH_SHIELD,%d6                   | 011500
.L11504:
    move.b  A_active_count_seekers-FGB(%a5),%d7             | 011504
    cmp.b   %d6,%d7                                         | 01150a
    jbge    .L11600                                         | 01150c  at the limit -> the plain bullet
    move.w  #PLAYER_SHOT_SLOTS-1,%d7                        | 011510  move.w #$5,d7
.L11514:
    tst.b   ENTITY_ALIVE(%a3)                               | 011514
    jbeq    .L11528                                         | 011518  the seeker's arm scans with `beq` OUT
    lea     ENTITY_STRIDE(%a3),%a3                          | 01151c  lea 44(a3),a3
    dbf     %d7,.L11514                                     | 011520
    jbra    .Ldone                                          | 011524  every slot busy: the press is spent
.L11528:
    lea     A_entity_gunsight-FGB(%a5),%a4                  | 011528  lea $17dd2.l,a4 — not read by the callee
    moveq   #ENTITY_INDEX_TRAIL_DRONE,%d6                   | 01152e  moveq #$13,d6 — the fallback target
    addq.b  #1,A_active_count_seekers-FGB(%a5)              | 011530
    jbsr    door_fire_seeker                                | 011536  bsr.w $13f9e
    jbra    .Ldone                                          | 01153a

.L1153e:
    cmpi.b  #WEAPON_KIND_MISSILE,A_selected_weapon-FGB(%a5) | 01153e  cmpi.b #$2,$198b4.l
    jbne    .L11596                                         | 011546
    move.b  A_shield_level-FGB(%a5),%d6                     | 01154a
    tst.b   %d6                                             | 011550
    jbne    .L1155e                                         | 011552
    move.b  #WEAPON_SHOTS_WITHOUT_SHIELD,%d6                | 011556
    jbra    .L11562                                         | 01155a
.L1155e:
    move.b  #WEAPON_SHOTS_WITH_SHIELD,%d6                   | 01155e
.L11562:
    move.b  A_active_count_type32-FGB(%a5),%d7              | 011562
    cmp.b   %d6,%d7                                         | 011568
    jbge    .L11600                                         | 01156a
    move.w  #PLAYER_SHOT_SLOTS-1,%d7                        | 01156e
.L11572:
    tst.b   ENTITY_ALIVE(%a3)                               | 011572
    jbne    .L1158a                                         | 011576  ...and the missile's with `bne` ROUND
    addi.b  #1,A_active_count_type32-FGB(%a5)               | 01157a
    jbsr    door_fire_homing_missile                        | 011582  bsr.w $1401a
    jbra    .Ldone                                          | 011586
.L1158a:
    lea     ENTITY_STRIDE(%a3),%a3                          | 01158a
    dbf     %d7,.L11572                                     | 01158e
    jbra    .Ldone                                          | 011592

.L11596:
    cmpi.b  #WEAPON_KIND_BOMB,A_selected_weapon-FGB(%a5)    | 011596  cmpi.b #$1,$198b4.l
    jbne    .L115f4                                         | 01159e
    move.b  A_shield_level-FGB(%a5),%d6                     | 0115a2
    tst.b   %d6                                             | 0115a8
    jbne    .L115b6                                         | 0115aa
    move.b  #WEAPON_SHOTS_WITHOUT_SHIELD,%d6                | 0115ae
    jbra    .L115ba                                         | 0115b2
.L115b6:
    move.b  #WEAPON_SHOTS_WITH_SHIELD,%d6                   | 0115b6
.L115ba:
    move.b  A_active_count_bombs-FGB(%a5),%d7               | 0115ba
    cmp.b   %d6,%d7                                         | 0115c0
    jbge    .L11600                                         | 0115c2
    lea     A_entity_table-FGB(%a5),%a3                     | 0115c6  RELOADS the base the loop already holds
    move.w  #PLAYER_SHOT_SLOTS-1,%d7                        | 0115cc
.L115d0:
    tst.b   ENTITY_ALIVE(%a3)                               | 0115d0
    jbne    .L115e8                                         | 0115d4
    addi.b  #1,A_active_count_bombs-FGB(%a5)                | 0115d8
    jbsr    door_fire_bomb                                  | 0115e0  bsr.w $14324
    jbra    .Ldone                                          | 0115e4
.L115e8:
    lea     ENTITY_STRIDE(%a3),%a3                          | 0115e8
    dbf     %d7,.L115d0                                     | 0115ec
    jbra    .Ldone                                          | 0115f0

.L115f4:
    cmpi.b  #WEAPON_BULLET,A_selected_weapon-FGB(%a5)       | 0115f4  cmpi.b #$3,$198b4.l
    jbne    .Ldone                                          | 0115fc  THE ONE ARM WITH NO FALL-THROUGH

| ==== the plain bullet — 0x11600 .. 0x1167a =====================================================
| ../frame.c's `frame_fire_bullet`, which weapon 3 reaches directly and the three counted arms
| reach through their `bge`.
.L11600:
    move.b  A_active_bullets-FGB(%a5),%d7                   | 011600
    cmp.b   A_weapon_power_level-FGB(%a5),%d7               | 011606  cmp.b $19908.l,d7
    jbge    .Ldone                                          | 01160c
    lea     A_entity_table-FGB(%a5),%a3                     | 011610
    move.w  #PLAYER_SHOT_SLOTS-1,%d7                        | 011616
.L1161a:
    tst.b   ENTITY_ALIVE(%a3)                               | 01161a
    jbne    .L11674                                         | 01161e
    move.w  ENTITY_X(%a2),%d1                               | 011622
    add.w   #BULLET_SPAWN_DX,%d1                            | 011626
    move.w  %d1,ENTITY_X(%a3)                               | 01162a
    move.w  ENTITY_Y(%a2),%d6                               | 01162e
    add.w   #BULLET_SPAWN_DY,%d6                            | 011632
    move.w  %d6,ENTITY_Y(%a3)                               | 011636
    move.b  #1,ENTITY_ALIVE(%a3)                            | 01163a
    move.l  #A_player_bullet_sprite,ENTITY_SPRITE(%a3)      | 011640  an OFFSET already; not rebased
    move.b  #0,ENTITY_ANIM_FRAME(%a3)                       | 011648
    move.w  #BULLET_ROWS,ENTITY_HEIGHT(%a3)                 | 01164e
    move.b  #BULLET_TYPE,ENTITY_TYPE(%a3)                   | 011654
    addi.b  #1,A_active_bullets-FGB(%a5)                    | 01165a
    eori.b  #1,A_bullet_fire_toggle-FGB(%a5)                | 011662  which barrel the next bullet leaves
    moveq   #BULLET_SOUND,%d1                               | 01166a  D1 = the tune, D0 = the channel
    jbsr    door_sound_start                                | 01166c  bsr.w $16ac8 — WAVE C'S STUB, reused
    jbra    .Ldone                                          | 011670
.L11674:
    lea     ENTITY_STRIDE(%a3),%a3                          | 011674
    dbf     %d7,.L1161a                                     | 011678

| The original has no `rts`: 0x1167c is the next slice's first instruction and every arm above
| `bra`s to it. The C is `void`, so the twin simply unwinds — and %d0 is left undefined on purpose,
| which the differential declares by passing `expect_ret=None`.
.Ldone:
        FIRE_EPILOGUE

| ================================================================================================
| THE TRAMPOLINES — one thin block per callee, and the whole of the register translation.
|
| frame.S's own trampoline preamble is the long version of this and holds word for word: the
| original passes its callees' arguments IN REGISTERS, the reconstruction's cores carry C
| signatures, and each site needs a block that binds one to the other. All three below have the
| same five parts — save the ABI's call-clobbered file, turn each POINTER argument into an image
| OFFSET, push right to left and call, apply the answer, restore and `rts`.
|
| THERE IS NO ANSWER TO APPLY AT ANY OF THESE THREE. All three cores are `void`, and no instruction
| after any of the four call sites reads a condition code: 0x1153a, 0x11586, 0x115e4 and 0x11670 are
| each an unconditional `bra` to the end of the slice. So all three are X-TRANSPARENT BY
| CONSTRUCTION, which is what PUSH_OFFSET's `suba.l` buys — a `sub.l` there would set X where the
| original set nothing, and although nothing in this slice reads it, a stub that quietly generates a
| carry is a stub the next transcription cannot reuse.
|
| AND THE FOURTH SITE REUSES WAVE C'S STUB. 0x1166c calls `sound_start` with D1 = the tune number
| and D0 = the channel, which is exactly frame.S's `door_sound_start` contract, so this file names
| that stub rather than writing a second one: a slot names a HOST FUNCTION, the twins link as one
| blob, and two spellings of one marshalling would be two places for it to drift. It is the one
| X-CARRYING stub of the four, deliberately — `sound_lookup_tune`'s `lsl.w #8,d1` shifts bit 7 of
| the tune number into X (../../include/sound.h's `sound_start_leaves_extend`) — and BULLET_SOUND
| has bit 7 clear, so what it reconstructs here is a cleared X.
| ================================================================================================
| THE DOOR'S BAND IS THE KIT'S CONSTANT, USED DIRECTLY, for frame.S's reason:
| tools/recreate_kit/asm_twin.py owns DOOR_BASE/DOOR_STRIDE because it is what WATCHES the band, and
| kit.mk passes both in as -D's. An `.equ` of our own would be a second spelling with nothing
| pinning it equal.
#ifdef ZY_ASM_FRAME_FIRE_DOOR
# define ZY_CALL(slot, fn)      jsr     (RECREATE_DOOR_BASE + (slot) * RECREATE_DOOR_STRIDE)
#else
# define ZY_CALL(slot, fn)      jsr     fn
#endif

| The macros are frame.S's, restated because `.macro` and `#define` are per-object and kit.mk
| assembles each twin's source separately (only the LABELS link across). Their contracts are
| frame.S's at length; the one-liners below are so a reader of this file need not go and get them.
        .macro  SCRATCH_SAVE
        movem.l %d0-%d1/%a0-%a1,-(%sp)          | the ABI's call-clobbered file; the cores keep the rest
        .endm
        .macro  SCRATCH_RESTORE
        movem.l (%sp)+,%d0-%d1/%a0-%a1
        .endm

| Push one of the body's POINTERS as the image OFFSET the core wants. `suba.l` AND NOT `sub.l`:
| `sub.l` sets X, `suba.l` touches no condition code at all, so this arithmetic is invisible where
| the original had none.
        .macro  PUSH_OFFSET areg
        movea.l \areg,%a0
        suba.l  %a6,%a0
        move.l  %a0,-(%sp)
        .endm

| ---- void fire_seeker(uint8_t *image, uint32_t shot, uint8_t fallback_target,
|                       uint8_t sound_channel) ---- A3 = shot, D6 = fallback target, D0 = channel
|
| THE CHANNEL IS THE JOYSTICK BYTE, which looks wrong and is not: this stage's D0 is the byte the
| head slice read out of A_joystick_state, and the original hands it to `fire_seeker` where the
| callee's own `bsr $16ac8` wants a channel (0x13fb4's `moveq #$1a,d1`). ../frame.c models it as
| exactly that — `fire_seeker(image, shot, ENTITY_INDEX_TRAIL_DRONE, joystick)`.
        .globl  door_fire_seeker
door_fire_seeker:
        SCRATCH_SAVE
        move.l  %d0,-(%sp)
        move.l  %d6,-(%sp)
        PUSH_OFFSET %a3
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_fire_seeker, fire_seeker)
        lea     16(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void fire_homing_missile(uint8_t *image, uint32_t shot) ---- A3 = shot; no channel at all
        .globl  door_fire_homing_missile
door_fire_homing_missile:
        SCRATCH_SAVE
        PUSH_OFFSET %a3
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_fire_homing_missile, fire_homing_missile)
        lea     8(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void fire_bomb(uint8_t *image, uint32_t shot, uint8_t sound_channel) ---- A3 = shot, D0 = ch
        .globl  door_fire_bomb
door_fire_bomb:
        SCRATCH_SAVE
        move.l  %d0,-(%sp)
        PUSH_OFFSET %a3
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_fire_bomb, fire_bomb)
        lea     12(%sp),%sp
        SCRATCH_RESTORE
        rts
