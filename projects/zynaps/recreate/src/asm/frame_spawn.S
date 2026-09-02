| frame_spawn.S — the asm twin for the frame loop's SPAWN AND MOVE stage, TRANSCRIBED from the
| original binary.
|
|   frame_spawn_and_move_stage_asm  <- the original @ [0x1167c, 0x11c00), the C reference
|                                      frame_spawn_and_move_stage in ../frame.c
|
| WHAT A TWIN IS is written out in README.md beside this file and in scroll_emit.S, and holds here
| word for word: the C in ../frame.c and ../enemy.c is byte-for-byte equivalent to the original
| (test/test_frame.py's and test/test_enemy.py's differentials against the Musashi oracle), the
| original's own instructions are in ../../out/prg_dis.txt, and everything from `.L1167c` on is that
| instruction sequence in order. Wave C's frame.S is the template; what follows says only what is
| DIFFERENT about this slice.
|
| WHAT THIS SLICE IS. The charged weapon's palette flash, the plain bullets' step, the explosion and
| scenery animations, the two map-driven spawn scripts, every enemy's animate and move pass, the
| player's own six shot slots, the enemy fire pass and the boss tail. 311 instructions and 44 calls,
| of which 40 go through the door and 4 are internal.
|
| FOUR WHOLE VERIFIED FUNCTIONS LIVE INSIDE THE SPAN and are transcribed here with it, because the
| transcription-order pin asks for every address in [0x1167c, 0x11c00) exactly once:
|
|   enemy_fire_and_update_shots  0x11906   ../enemy.c
|   spawn_enemy_shot             0x11a2c   ../enemy.c
|   enemy_shot_tick_type0b       0x11bbc   ../enemy.c
|   enemy_shot_tick_type0a       0x11bde   ../enemy.c
|
| Each ends in `rts`, so each is CALLED and not branched into (README.md, "What wave B added"): the
| original's own `bsr` to them survives as a plain `jbsr .L<addr>` inside this file, NOT as a door.
| The file is laid out in strict address order, so the four sit after the stage's own code exactly
| where the original puts them, and the stage's last instruction (0x11902) is an unconditional
| branch, so nothing falls into 0x11906 that should not.
|
| TWO REGISTER PARAMETERS STAY, and ../../include/frame.h says why. `chance_index_register` is D1 at
| the `bsr` to `enemy_fire_and_update_shots` (0x118cc): the routine loads the section with `move.b`
| into D1's low byte and indexes the chance table with `d1.w`, so the CALLER's high byte is part of
| the offset. `ground_spawn_y_register` is D7 at the `bsr` to `groundscript_spawn_type10`/`_type0f`
| (0x11818 / 0x11820), whose free-slot guard tests the whole longword. Neither is derivable inside
| the slice, so the prologue binds both from the C arguments.
|
| THE FOUR TRANSLATIONS, and only these four.
|
| **1. The image base — two registers, exactly as frame.S.**
|
|     %a6 = image            the raw base: the trampolines' pointer->offset arithmetic
|     %a5 = image + FGB      FGB = 0x18000, so every global this slice names is `NAME-FGB(%a5)`
|
| The twenty-seven globals span 0x17a8e..0x19efe, which is -0x572..+0x1efe from FGB — comfortably
| inside one signed 16-bit displacement window. test_asm_frame_spawn.py asserts that over the whole
| list rather than leaving it to gas, whose own refusal names the architecture and not the window.
|
| **2. A pointer LOADED OUT OF THE IMAGE is an offset, and one STORED BACK is one too.** The two
| script cursors are longwords in the image, and the reconstruction holds them as OFFSETS: 0x11728
| and 0x117f6 read one, so the base is added where the original had nothing to add; 0x117a8 and
| 0x117be write one back, so the base is taken off again — with `suba.l` through %a0, never `sub.l`,
| because `sub.l` sets the X flag the original never touches there. A longword IMMEDIATE naming a
| sprite bank is ALREADY an offset and is left alone (0x11788, 0x11796, 0x11ac2, 0x11b1e, 0x11b7e).
|
| **3. TWO OF THE ORIGINAL'S OWN REGISTERS ARE THE TWO THIS FILE RESERVES, so they are substituted.**
| This is the one translation frame.S did not need — its header records that the stage it transcribes
| "uses only %a0-%a4 and %a7". This one does not:
|
|     the original's A5   0x11788 / 0x11796   the alien sprite bank, consumed by the `bsr` at
|                                             0x1179c              -> %a3 here
|     the original's A6   0x1196a / 0x11984 / 0x11a64   the class bitmap, consumed by the `bsr` to
|                                             entity_type_in_mask  -> %a4 here
|
| Both substitutes are DEAD at every site: %a3 is not read between the bullet loop's `dbf` (0x1170c)
| and its reload at 0x1182c, and %a4 is not read anywhere in [0x11906, 0x11c00) — the ground script's
| use of it ends at 0x11824. Each substituted value's live range is the two or three instructions
| from its `lea` to the `bsr` that consumes it, so nothing else can observe the choice. The stubs
| below read the substitute, and each site's comment names the register it stands in for.
|
| **4. The exit.** The original does not `rts`: 0x118ec and 0x11902 both leave to 0x11c00, the next
| slice's entry. The C is `void`, so both become a branch to the epilogue and the twin has no answer
| to return — test_asm_frame_spawn.py's differential passes `expect_ret=None` for that reason.
|
| THE BYTE PIN IS UNAVAILABLE, for frame.S's reason (position-independence re-encodes every
| instruction that names a global) and for two of gas's:
|
|   * gas spells `and.w #imm,Dn` / `cmp.b #imm,Dn` / `add.l #imm,Dn` as ANDI/CMPI/ADDI — same length,
|     same cycles, a different opcode word. README.md's "What wave B added", point 3.
|   * gas FOLDS A ZERO DISPLACEMENT: the original's `move.w 0(a1),0(a2)` is the 6-byte d16 form, and
|     `ENTITY_X(%a1)` with ENTITY_X = 0 assembles to the 2-byte `(%a1)`. Same effect, FOUR TO EIGHT
|     CYCLES CHEAPER at each of the eleven sites that carry a zero offset. Named here rather than
|     hidden because it pulls the cost bars DOWN while the trampolines pull them up, and only the
|     measurement settles where they land — test_asm_frame_spawn.py's cost table is that measurement.
|
| WHAT STANDS IN THE BYTE PIN'S PLACE is what stands in it for frame.S: the differential over staged
| worlds per arm, the cost bars, and a TRANSCRIPTION-ORDER pin — all 311 of the original's
| instruction addresses present exactly once, in ascending order, no gaps and no extras.
|
| SEVEN INSTRUCTIONS OF THIS SPAN ARE DEAD, at 0x119ba..0x119d8. They sit past an unconditional
| `bra` and nothing branches to them; ../enemy.c leaves them out of the C entirely and STATUS.md
| records that. They are transcribed here anyway, because the pin asks for every address in the span
| and a gap would be indistinguishable from a dropped instruction. No case reaches them, and none
| can. (../enemy.c's header calls the block ELEVEN instructions; ../../out/prg_dis.txt has seven
| lines between those two addresses, which is what the pin counts. The SPAN both name is the same;
| only the count differs.)
|
| REGISTERS. The prologue saves %d2-%d3/%d6-%d7/%a2-%a6 — every callee-saved register the body
| touches (%d4 and %d5 appear nowhere in the span), plus the two it reserves. **The surface that
| catches a clobbered callee-saved register is NOT the differential**: it compares the image, and a
| corrupted %a2 leaves the image perfect and breaks the C CALLER instead. It is
| `bash atari/build.sh game && python3 atari/smoke.py game`, and README.md's "Registers" says so at
| length.

        .text

| WHICH BUILD IS THIS — frame.S's paragraph, and the same one project-private name, so a reader who
| has read one file has read both. The kit's Makefile defines RECREATE_HOST_DIFFERENTIAL for the
| off-target assembly (tools/recreate_kit/kit.mk's ASM_CFLAGS); the target build defines nothing.
#ifdef RECREATE_HOST_DIFFERENTIAL
# define ZY_ASM_FRAME_DOOR 1
#endif


| ---- the constants, named exactly as the headers in ../../include name them --------------------
| test/test_constants.py::test_asm_twin_equates_match_the_headers pins every one of these whose name
| a header also defines, and requires every .S to contribute at least one — so a name that drifted
| from its header fails rather than going unchecked.
        .equ    A_active_bullets,                      0x19909     | init.h
        .equ    A_asteroid_section_flag,               0x198fd     | init.h
        .equ    A_boss_sequence_active,                0x19aad     | sprite.h
        .equ    A_charge_flash_dir,                    0x19903     | frame.h
        .equ    A_enemy_fire_chance_table,             0x19aaf     | enemy.h
        .equ    A_enemy_seeker_cooldown,               0x19abf     | enemy.h
        .equ    A_enemy_shot_slots,                    0x17b96     | enemy.h
        .equ    A_enemy_slots,                         0x17c1a     | enemy.h
        .equ    A_enemy_types_can_fire,                0x19172     | enemy.h
        .equ    A_enemy_types_fire_homing,             0x19164     | enemy.h
        .equ    A_enemy_types_fire_seeker,             0x19180     | enemy.h
        .equ    A_entity_table,                        0x17a8e     | player.h
        .equ    A_explosion_phase_odd,                 0x198c5     | enemy.h
        .equ    A_fire_charged,                        0x19902     | enemy.h
        .equ    A_ground_script_cursor,                0x1824a     | enemy.h
        .equ    A_level_section,                       0x19895     | init.h
        .equ    A_map_offset,                          0x1823e     | init.h
        .equ    A_map_page,                            0x198a5     | init.h
        .equ    A_mothership_pending,                  0x198af     | init.h
        .equ    A_mothership_phase_timer,              0x19efe     | mothership.h
        .equ    A_mothership_ready,                    0x198b0     | mothership.h
        .equ    A_palette_hw_shadow,                   0x18fc4     | irq.h
        .equ    A_player_record,                       0x17d7a     | enemy.h
        .equ    A_scroll_frozen,                       0x198b1     | enemy.h
        .equ    A_section_ground_target_flag,          0x19897     | init.h
        .equ    A_squadron_spawn_enabled,              0x19aae     | enemy.h
        .equ    A_wave_script_cursor,                  0x1824e     | enemy.h

| The sprite banks, which the body names as bare longwords rather than through the window: each is
| ALREADY an image offset, and all five are far outside a signed 16-bit displacement of FGB.
        .equ    A_shot_sprite_aimed,                   0x6115e     | enemy.h
        .equ    A_shot_sprite_homing,                  0x6e6ee     | enemy.h
        .equ    A_shot_sprite_seeker,                  0x65d9e     | enemy.h
        .equ    A_wave_alien_sprite_a,                 0x54ffe     | frame.h
        .equ    A_wave_alien_sprite_b,                 0x563fe     | frame.h

        .equ    ALIVE_BIT_EXPLODING,                   7           | frame.h
        .equ    BULLET_RETIRE_X,                       0x180       | frame.h
        .equ    BULLET_STEP_X,                         0x0c        | frame.h
        .equ    BULLET_TYPE,                           0x34        | frame.h
        .equ    CHARGE_FLASH_PEAK,                     0x444       | frame.h
        .equ    CHARGE_FLASH_STEP,                     0x111       | frame.h
        .equ    ENEMY_SHOT_SLOT_COUNT,                 3           | frame.h
        .equ    ENTITY_ALIVE,                          0x0e        | entity.h
        .equ    ENTITY_ANIM_FRAME,                     0x20        | entity.h
        .equ    ENTITY_HEIGHT,                         0x08        | entity.h
        .equ    ENTITY_HP,                             0x1a        | entity.h
        .equ    ENTITY_SPRITE,                         0x0a        | entity.h
        .equ    ENTITY_STRIDE,                         0x2c        | entity.h
        .equ    ENTITY_TYPE,                           0x11        | entity.h
        .equ    ENTITY_X,                              0x00        | entity.h
        .equ    ENTITY_Y,                              0x04        | entity.h
        .equ    ACTOR_FIRE_FLAGS,                      0x2a        | enemy.h
        .equ    ACTOR_SPAWN_TAG,                       0x10        | enemy.h
        .equ    PLAYER_SHOT_SLOTS,                     6           | weapon.h
        .equ    SCRIPT_TRIGGER_LOOKAHEAD,              0x24        | frame.h
        .equ    SHOT_HEADING,                          0x1d        | weapon.h
        .equ    SHOT_MAX_TURN,                         0x1f        | weapon.h
        .equ    SHOT_SPEED,                            0x1e        | weapon.h
        .equ    SHOT_TARGET_INDEX,                     0x1a        | weapon.h
        .equ    SHOT_TURN_COUNTDOWN,                   0x1b        | weapon.h
        .equ    SHOT_TURN_PERIOD,                      0x1c        | weapon.h
        .equ    SHOT_TYPE_MISSILE,                     0x32        | weapon.h
        .equ    SHOT_TYPE_SEEKER,                      0x36        | weapon.h
        .equ    SHOT_X_ALIGN_BIT,                      0           | frame.h
        .equ    SHOT_X_MAX,                            0x180       | frame.h
        .equ    SHOT_X_MIN,                            0x30        | frame.h
        .equ    SHOT_Y_MAX,                            0xb0        | frame.h
        .equ    SHOT_Y_MIN,                            0x15        | frame.h
        .equ    WAVE_ALIEN_SHIFT,                      4           | frame.h
        .equ    WAVE_ALIEN_TYPE_A,                     0x14        | frame.h
        .equ    WAVE_ALIEN_TYPE_B,                     0x16        | frame.h
        .equ    WAVE_OPCODE_SQUADRONS_OFF,             0x0d        | frame.h
        .equ    WAVE_OPCODE_SQUADRONS_ON,              0x0c        | frame.h
        .equ    WAVE_OPCODE_TRIO,                      0x0b        | frame.h
        .equ    WAVE_SCRIPT_ENTRY_BYTES,               4           | frame.h

| ---- the enemy-shot constants, which live in ../enemy.c and NOT in a header -------------------
| The four routines at 0x11906..0x11bfe are ../enemy.c's, and that file keeps their constants as
| file-static `#define`s rather than exporting them — so `test_constants.py` cannot pin these and
| does not try (it pins only names a header also defines). They are spelt EXACTLY as ../enemy.c
| spells them, which is what makes the two readable side by side; a name changed there and not here
| is the drift this note exists to make visible.
        .equ    ENEMY_AIM_LEAD,                        0x0e        | ../enemy.c
        .equ    ENEMY_FIRE_BIT_HALVED,                 2           | ../enemy.c
        .equ    ENEMY_FIRE_BIT_STEERED,                1           | ../enemy.c
        .equ    ENEMY_FIRE_CHANCE_MASK,                0x1f        | ../enemy.c
        .equ    ENEMY_FIRE_CHANCE_SHIFT,               4           | ../enemy.c
        .equ    ENEMY_FIRE_ROLL_MASK,                  3           | ../enemy.c
        .equ    ENEMY_HOMING_CHANCE,                   0x32        | ../enemy.c
        .equ    ENEMY_HOMING_TURN_PERIOD,              6           | ../enemy.c
        .equ    ENEMY_SEEKER_COOLDOWN,                 6           | ../enemy.c
        .equ    ENEMY_SEEKER_HEADING,                  0x30        | ../enemy.c
        .equ    ENEMY_SEEKER_ROWS,                     0x0b        | ../enemy.c
        .equ    ENEMY_SEEKER_SPEED,                    2           | ../enemy.c
        .equ    ENEMY_SEEKER_TURN_PERIOD,              2           | ../enemy.c
        .equ    ENEMY_SHOT_AIMED_FRAME,                1           | ../enemy.c
        .equ    ENEMY_SHOT_MIN_X,                      0x50        | ../enemy.c
        .equ    ENEMY_SHOT_ROWS,                       8           | ../enemy.c
        .equ    ENEMY_SHOT_SPEED,                      4           | ../enemy.c
        .equ    ENEMY_SHOT_STEERED_TTL,                0x64        | ../enemy.c
        .equ    ENEMY_SHOT_TYPE_AIMED,                 0x0c        | ../enemy.c
        .equ    ENEMY_SHOT_TYPE_HOMING,                0x0a        | ../enemy.c
        .equ    ENEMY_SHOT_TYPE_SEEKER,                0x0b        | ../enemy.c
        .equ    ENEMY_SLOT_PICK_MASK,                  7           | ../enemy.c
        .equ    ENEMY_STEERED_MAX_TURN,                1           | ../enemy.c
        .equ    PLAYER_ENTITY_INDEX,                   0x11        | ../enemy.c

| This file's own two, which no header and no `.c` names because nothing but an assembler needs
| them: what `and.l #$ffff` and `and.w #$ff` keep.
        .equ    WORD_MASK,                             0xffff
        .equ    BYTE_MASK,                             0xff
| ...and the mask in the dead block at 0x119d0, which ../enemy.c does not name because it does not
| transcribe the block at all.
        .equ    DEAD_SPAWN_HP_MASK,                    0x7ff

| The door slots. The table is the FAMILY's — test/asm_frame_common.py's DOOR_TABLE — and
| test_asm_frame_doors.py pins these `.equ`s against it, and pins that no sibling twin claims one of
| these numbers for a different core. Slots 2 and 10 are WAVE C'S, reused because a slot names a
| HOST FUNCTION: this file's sites for `enemy_morph_to_type6` and `shot_retire_kind32` have exactly
| frame.S's register contract, so they jump to frame.S's own stubs rather than to a second copy.
| The two `.equ`s below are therefore NOT referenced by any instruction in this file, and are here on
| purpose: they are how this twin DECLARES which host functions it reaches, which is what
| test_asm_frame_doors.py pins against the table and what
| test_asm_frame_spawn.py::test_the_cases_between_them_reach_every_door_this_twin_names reads to
| decide that every door of this twin's has a case behind it.
        .equ    ZY_DOOR_enemy_morph_to_type6,          2
        .equ    ZY_DOOR_shot_retire_kind32,            10
        .equ    ZY_DOOR_explosion_animate_all,         37
        .equ    ZY_DOOR_anim_ground_objects,           38
        .equ    ZY_DOOR_rand16,                        39
        .equ    ZY_DOOR_wavescript_spawn_wave,         40
        .equ    ZY_DOOR_wavescript_spawn_trio_type0e,  41
        .equ    ZY_DOOR_groundscript_spawn_type10,     42
        .equ    ZY_DOOR_groundscript_spawn_type0f,     43
        .equ    ZY_DOOR_enemies_animate_all,           44
        .equ    ZY_DOOR_enemies_move_all,              45
        .equ    ZY_DOOR_seeker_update,                 46
        .equ    ZY_DOOR_homing_missile_update,         47
        .equ    ZY_DOOR_player_shot_update_all,        48
        .equ    ZY_DOOR_squadron_spawn_tick,           49
        .equ    ZY_DOOR_asteroids_move,                50
        .equ    ZY_DOOR_asteroids_animate,             51
        .equ    ZY_DOOR_mothership_move_and_place,     52
        .equ    ZY_DOOR_mothership_draw,               53
        .equ    ZY_DOOR_entity_type_in_mask,           54
        .equ    ZY_DOOR_entity_apply_velocity,         55
        .equ    ZY_DOOR_entity_kill_if_offscreen,      56
        .equ    ZY_DOOR_angle_to_target,               57
        .equ    ZY_DOOR_entity_set_velocity_from_angle, 58
        .equ    ZY_DOOR_entity_steer_toward_target,    59

| The global window's origin, and frame.S's — the same number, because the two twins address the
| same globals and a reader moving between them should not have to re-derive it. It is not a header
| constant: the only thing that makes it right is that every global either file names lands within a
| signed 16-bit displacement of it, which each suite asserts over its own list.
        .equ    FGB, 0x18000

| What the prologue pushes, and every argument offset measured past it.
        .equ    SAVED, (9 * 4)                  | %d2-%d3/%d6-%d7/%a2-%a6
        .equ    ARG_IMAGE, 4 + SAVED
        .equ    ARG_CHANCE_INDEX, 8 + SAVED
        .equ    ARG_GROUND_SPAWN_Y, 12 + SAVED

        .macro  SPAWN_PROLOGUE
        movem.l %d2-%d3/%d6-%d7/%a2-%a6,-(%sp)
        movea.l ARG_IMAGE(%sp),%a6              | the raw image base
        movea.l %a6,%a5
        adda.l  #FGB,%a5                        | ...and the globals' window
        move.l  ARG_CHANCE_INDEX(%sp),%d1       | D1 — whose HIGH BYTE indexes the chance table
        move.l  ARG_GROUND_SPAWN_Y(%sp),%d7     | D7 — the y the ground script spawns at
        .endm

        .macro  SPAWN_EPILOGUE
        movem.l (%sp)+,%d2-%d3/%d6-%d7/%a2-%a6
        rts
        .endm

| ================================================================================================
| void frame_spawn_and_move_stage_asm(uint8_t *image, uint32_t chance_index_register,
|                                     uint32_t ground_spawn_y_register)
| ================================================================================================
        .globl  frame_spawn_and_move_stage_asm
frame_spawn_and_move_stage_asm:
        SPAWN_PROLOGUE

| ---- the charged weapon's palette flash, at half rate (0x1167c) --------------------------------
| It walks the palette shadow up to CHARGE_FLASH_PEAK and back down to 0, turning round with a
| `not.b` at each end.
.L1167c:
    tst.b   A_fire_charged-FGB(%a5)                         | 01167c
    jbeq    .L116d0                                         | 011682
    tst.b   A_explosion_phase_odd-FGB(%a5)                  | 011686
    jbne    .L116d0                                         | 01168c
    tst.b   A_charge_flash_dir-FGB(%a5)                     | 011690
    jbne    .L116b8                                         | 011696
    addi.w  #CHARGE_FLASH_STEP,A_palette_hw_shadow-FGB(%a5) | 01169a
    cmpi.w  #CHARGE_FLASH_PEAK,A_palette_hw_shadow-FGB(%a5) | 0116a2
    jbne    .L116d0                                         | 0116aa
    not.b   A_charge_flash_dir-FGB(%a5)                     | 0116ae
    jbra    .L116d0                                         | 0116b4
.L116b8:
    subi.w  #CHARGE_FLASH_STEP,A_palette_hw_shadow-FGB(%a5) | 0116b8
    tst.w   A_palette_hw_shadow-FGB(%a5)                    | 0116c0
    jbne    .L116d0                                         | 0116c6
    not.b   A_charge_flash_dir-FGB(%a5)                     | 0116ca

| ---- the six player-shot slots: step every plain bullet (0x116d0) ------------------------------
.L116d0:
    lea     A_entity_table-FGB(%a5),%a3                     | 0116d0
    move.w  #PLAYER_SHOT_SLOTS - 1,%d7                      | 0116d6 move.w #$5,d7
.L116da:
    tst.b   ENTITY_ALIVE(%a3)                               | 0116da tst.b 14(a3)
    jbeq    .L11708                                         | 0116de
    cmpi.b  #BULLET_TYPE,ENTITY_TYPE(%a3)                   | 0116e2 cmpi.b #$34,17(a3)
    jbne    .L11708                                         | 0116e8
    addi.w  #BULLET_STEP_X,ENTITY_X(%a3)                    | 0116ec addi.w #$c,0(a3)
    cmpi.w  #BULLET_RETIRE_X,ENTITY_X(%a3)                  | 0116f2 cmpi.w #$180,0(a3)
    jblt    .L11708                                         | 0116f8
    subi.b  #1,A_active_bullets-FGB(%a5)                    | 0116fc
    clr.b   ENTITY_ALIVE(%a3)                               | 011704 clr.b 14(a3)
.L11708:
    lea     ENTITY_STRIDE(%a3),%a3                          | 011708 lea 44(a3),a3
    dbf     %d7,.L116da                                     | 01170c

| ---- the two animation passes (0x11710) --------------------------------------------------------
    jbsr    door_explosion_animate_all                      | 011710 bsr.w $1544e
    jbsr    door_anim_ground_objects                        | 011714 bsr.w $14626

| ---- the ATTACK script (0x11718) ---------------------------------------------------------------
| A script fires when the map cursor's own column plus one column of look-ahead equals the cursor
| word the next record carries, rounded DOWN to a whole column. D7 comes out of this block as the
| ground script's y register on every path but the `mothership_pending` one.
    tst.b   A_mothership_pending-FGB(%a5)                   | 011718
    jbne    .L117d2                                         | 01171e
    move.l  A_map_offset-FGB(%a5),%d0                       | 011722
    movea.l A_wave_script_cursor-FGB(%a5),%a4               | 011728 movea.l $1824e.l,a4
    adda.l  %a6,%a4                                         | SUBSTITUTION: the image holds an OFFSET
    andi.l  #WORD_MASK,%d0                                  | 01172e and.l #$ffff,d0
    addi.l  #SCRIPT_TRIGGER_LOOKAHEAD,%d0                   | 011734 add.l #$24,d0
    move.w  (%a4),%d7                                       | 01173a
    andi.l  #WORD_MASK,%d7                                  | 01173c and.l #$ffff,d7
    divu.w  #SCRIPT_TRIGGER_LOOKAHEAD,%d7                   | 011742 divu.w #$24,d7
    andi.l  #WORD_MASK,%d7                                  | 011746 and.l #$ffff,d7
    mulu.w  #SCRIPT_TRIGGER_LOOKAHEAD,%d7                   | 01174c mulu.w #$24,d7
    cmp.w   %d7,%d0                                         | 011750
    jbne    .L117d2                                         | 011752
    move.w  2(%a4),%d7                                      | 011756
    move.b  %d7,%d6                                         | 01175a  a BYTE move: D6's high bytes stay the caller's
    lsr.w   #8,%d7                                          | 01175c
    cmpi.b  #WAVE_OPCODE_TRIO,%d7                           | 01175e cmp.b #$b,d7
    jbeq    .L117ce                                         | 011762
    cmpi.b  #WAVE_OPCODE_SQUADRONS_ON,%d7                   | 011766 cmp.b #$c,d7
    jbeq    .L117a4                                         | 01176a
    cmpi.b  #WAVE_OPCODE_SQUADRONS_OFF,%d7                  | 01176e cmp.b #$d,d7
    jbeq    .L117ba                                         | 011772
    jbsr    door_rand16                                     | 011776 bsr.w $13bf8
    lsr.w   #WAVE_ALIEN_SHIFT,%d0                           | 01177a lsr.w #4,d0
    btst    #0,%d0                                          | 01177c
    jbeq    .L11792                                         | 011780
    move.b  #WAVE_ALIEN_TYPE_A,%d1                          | 011784 move.b #$14,d1
    lea     A_wave_alien_sprite_a,%a3                       | 011788 lea $54ffe.l,a5 — SUBSTITUTED REGISTER, and the bank is already an OFFSET
    jbra    .L1179c                                         | 01178e
.L11792:
    move.b  #WAVE_ALIEN_TYPE_B,%d1                          | 011792 move.b #$16,d1
    lea     A_wave_alien_sprite_b,%a3                       | 011796 lea $563fe.l,a5 — SUBSTITUTED REGISTER
.L1179c:
    jbsr    door_wavescript_spawn_wave                      | 01179c bsr.w $13868
    jbra    .L117d2                                         | 0117a0
.L117a4:
    lea     WAVE_SCRIPT_ENTRY_BYTES(%a4),%a4                | 0117a4 lea 4(a4),a4
    movea.l %a4,%a0                                         | SUBSTITUTION: the image holds an OFFSET...
    suba.l  %a6,%a0                                         | ...and `suba.l` so the X flag is untouched
    move.l  %a0,A_wave_script_cursor-FGB(%a5)               | 0117a8 move.l a4,$1824e.l
    move.b  #1,A_squadron_spawn_enabled-FGB(%a5)            | 0117ae
    jbra    .L117d2                                         | 0117b6
.L117ba:
    lea     WAVE_SCRIPT_ENTRY_BYTES(%a4),%a4                | 0117ba lea 4(a4),a4
    movea.l %a4,%a0                                         | SUBSTITUTION: the image holds an OFFSET
    suba.l  %a6,%a0
    move.l  %a0,A_wave_script_cursor-FGB(%a5)               | 0117be move.l a4,$1824e.l
    clr.b   A_squadron_spawn_enabled-FGB(%a5)               | 0117c4
    jbra    .L117d2                                         | 0117ca
.L117ce:
    jbsr    door_wavescript_spawn_trio_type0e               | 0117ce bsr.w $13898

| ---- the GROUND script (0x117d2) ---------------------------------------------------------------
| Which of the two spawners runs is the section's own table byte, and both are handed D7 — the
| register the block above left, or this stage's own argument where it left none.
.L117d2:
    tst.b   A_asteroid_section_flag-FGB(%a5)                | 0117d2
    jbne    .L11824                                         | 0117d8
    tst.b   A_scroll_frozen-FGB(%a5)                        | 0117dc
    jbne    .L11824                                         | 0117e2
    tst.b   A_map_page-FGB(%a5)                             | 0117e6
    jbne    .L11824                                         | 0117ec
    move.l  A_map_offset-FGB(%a5),%d0                       | 0117f0
    movea.l A_ground_script_cursor-FGB(%a5),%a4             | 0117f6 movea.l $1824a.l,a4
    adda.l  %a6,%a4                                         | SUBSTITUTION: the image holds an OFFSET
    andi.l  #WORD_MASK,%d0                                  | 0117fc and.l #$ffff,d0
    addi.l  #SCRIPT_TRIGGER_LOOKAHEAD,%d0                   | 011802 add.l #$24,d0
    cmp.w   (%a4),%d0                                       | 011808
    jbne    .L11824                                         | 01180a
    tst.b   A_section_ground_target_flag-FGB(%a5)           | 01180e
    jbeq    .L11820                                         | 011814
    jbsr    door_groundscript_spawn_type10                  | 011818 bsr.w $13958
    jbra    .L11824                                         | 01181c
.L11820:
    jbsr    door_groundscript_spawn_type0f                  | 011820 bsr.w $13a12

| ---- every enemy animated and moved (0x11824) --------------------------------------------------
.L11824:
    jbsr    door_enemies_animate_all                        | 011824 bsr.w $147f2
    jbsr    door_enemies_move_all                           | 011828 bsr.w $1487c

| ---- the six player shot slots: steer the two steered kinds, align, retire (0x1182c) -----------
    lea     A_entity_table-FGB(%a5),%a3                     | 01182c
    move.w  #PLAYER_SHOT_SLOTS - 1,%d7                      | 011832 move.w #$5,d7
.L11836:
    tst.b   ENTITY_ALIVE(%a3)                               | 011836 tst.b 14(a3)
    jbeq    .L118c0                                         | 01183a
    cmpi.b  #SHOT_TYPE_SEEKER,ENTITY_TYPE(%a3)              | 01183e cmpi.b #$36,17(a3)
    jbne    .L11858                                         | 011844
    movem.l %d7/%a3,-(%sp)                                  | 011848 movem.l #$0110,-(a7)
    jbsr    door_seeker_update                              | 01184c bsr.w $140a6
    movem.l (%sp)+,%d7/%a3                                  | 011850 movem.l (a7)+,#$0880
    jbra    .L1186e                                         | 011854
.L11858:
    cmpi.b  #SHOT_TYPE_MISSILE,ENTITY_TYPE(%a3)             | 011858 cmpi.b #$32,17(a3)
    jbne    .L118c0                                         | 01185e
    movem.l %d7/%a3,-(%sp)                                  | 011862 movem.l #$0110,-(a7)
    jbsr    door_homing_missile_update                      | 011866 bsr.w $14126
    movem.l (%sp)+,%d7/%a3                                  | 01186a movem.l (a7)+,#$0880
| THE FOUR RETIRE SITES BELOW REUSE frame.S's `door_shot_retire_kind32`, AND ITS `X_IN` READS A
| FLAG THIS SLICE NEVER SETS — stated here because the reuse is what makes it non-obvious.
|
| That stub is X-CARRYING by design: it reads the 68000's X and hands it to the core as `extend_in`,
| because in frame.S's stage the previous award's `abcd` left it. HERE nothing does. Between the
| preceding door call and each of these sites there is no instruction that writes X (`movem` does
| not restore the CCR; `cmpi`, `bclr` and `movea` leave X alone on the 68000), so what `X_IN` picks
| up off target is whatever the DOOR left — and the door's X is now a per-callback schedule
| (TRAP_MODEL.md). The C shore passes EXTEND_UNREAD, a constant 0 (../frame.c).
|
| SO THE TWO SHORES KNOWINGLY DISAGREE ON THAT ARGUMENT, and nothing can see it: the core only
| echoes `extend_in` back out (../weapon.c), and every one of these four sites is followed by a
| `bra` before any instruction reads X again. It is recorded rather than fixed because fixing it
| means a second entry point into a wave-C stub for a value both shores discard — but a later
| change that makes this slice's X live must start by reading this paragraph.
.L1186e:
    bclr    #SHOT_X_ALIGN_BIT,ENTITY_X + 1(%a3)             | 01186e bclr #0,1(a3)
    cmpi.w  #SHOT_X_MIN,ENTITY_X(%a3)                       | 011874 cmpi.w #$30,0(a3)
    jbge    .L11888                                         | 01187a
    movea.l %a3,%a2                                         | 01187e
    jbsr    door_shot_retire_kind32                         | 011880 bsr.w $15582 — frame.S's stub
    jbra    .L118c0                                         | 011884
.L11888:
    cmpi.w  #SHOT_X_MAX,ENTITY_X(%a3)                       | 011888 cmpi.w #$180,0(a3)
    jble    .L1189c                                         | 01188e
    movea.l %a3,%a2                                         | 011892
    jbsr    door_shot_retire_kind32                         | 011894 bsr.w $15582
    jbra    .L118c0                                         | 011898
.L1189c:
    cmpi.w  #SHOT_Y_MIN,ENTITY_Y(%a3)                       | 01189c cmpi.w #$15,4(a3)
    jbge    .L118b0                                         | 0118a2
    movea.l %a3,%a2                                         | 0118a6
    jbsr    door_shot_retire_kind32                         | 0118a8 bsr.w $15582
    jbra    .L118c0                                         | 0118ac
.L118b0:
    cmpi.w  #SHOT_Y_MAX,ENTITY_Y(%a3)                       | 0118b0 cmpi.w #$b0,4(a3)
    jble    .L118c0                                         | 0118b6
    movea.l %a3,%a2                                         | 0118ba
    jbsr    door_shot_retire_kind32                         | 0118bc bsr.w $15582
.L118c0:
    lea     ENTITY_STRIDE(%a3),%a3                          | 0118c0 lea 44(a3),a3
    dbf     %d7,.L11836                                     | 0118c4

| ---- the enemy fire pass, the asteroid arm and the boss tail (0x118c8) -------------------------
    jbsr    door_player_shot_update_all                     | 0118c8 bsr.w $152a4
    jbsr    .L11906                                         | 0118cc bsr.w $11906 — INTERNAL: enemy_fire_and_update_shots
    tst.b   A_asteroid_section_flag-FGB(%a5)                | 0118d0
    jbeq    .L118e6                                         | 0118d6
    jbsr    door_squadron_spawn_tick                        | 0118da bsr.w $13af2
    jbsr    door_asteroids_move                             | 0118de bsr.w $159f2
    jbsr    door_asteroids_animate                          | 0118e2 bsr.w $15a6a
.L118e6:
    tst.b   A_boss_sequence_active-FGB(%a5)                 | 0118e6
    jbeq    .Lreturn                                        | 0118ec beq.w $11c00 — the stage's exit
    jbsr    door_mothership_move_and_place                  | 0118f0 bsr.w $14fc8
    addi.l  #1,A_mothership_phase_timer-FGB(%a5)            | 0118f4
    jbsr    door_mothership_draw                            | 0118fe bsr.w $158f4
    jbra    .Lreturn                                        | 011902 bra.w $11c00 — the stage's exit

| ================================================================================================
| enemy_fire_and_update_shots @ 0x11906 — ../enemy.c. One frame of enemy fire: pick one of the eight
| wave records at random, decide whether it fires, drop a shot into the first free slot if it does,
| and tick all three slots whatever happened. D1 in = the chance-table index register.
| ================================================================================================
.L11906:
    lea     A_enemy_shot_slots-FGB(%a5),%a2                 | 011906
    lea     A_player_record-FGB(%a5),%a0                    | 01190c
    lea     A_enemy_slots-FGB(%a5),%a1                      | 011912
    jbsr    door_rand16                                     | 011918 bsr.w $13bf8
    andi.w  #ENEMY_SLOT_PICK_MASK,%d0                       | 01191c and.w #$7,d0
    mulu.w  #ENTITY_STRIDE,%d0                              | 011920 mulu.w #$2c,d0
    adda.l  %d0,%a1                                         | 011924
    tst.b   A_mothership_ready-FGB(%a5)                     | 011926
    jbne    .L11966                                         | 01192c
    tst.b   ACTOR_FIRE_FLAGS(%a1)                           | 011930 tst.b 42(a1)
    jbeq    .L119e4                                         | 011934
    jbsr    door_rand16                                     | 011938 bsr.w $13bf8
    andi.w  #ENEMY_FIRE_ROLL_MASK,%d0                       | 01193c and.w #$3,d0
    jbne    .L119e4                                         | 011940
    jbsr    door_rand16                                     | 011944 bsr.w $13bf8
    lsr.l   #ENEMY_FIRE_CHANCE_SHIFT,%d0                    | 011948 lsr.l #4,d0
    move.b  A_level_section-FGB(%a5),%d1                    | 01194a  the LOW byte only: D1's high byte is the caller's
    lea     A_enemy_fire_chance_table-FGB(%a5),%a3          | 011950
    move.b  0(%a3,%d1.w),%d1                                | 011956
    ext.w   %d1                                             | 01195a
    andi.w  #ENEMY_FIRE_CHANCE_MASK,%d0                     | 01195c and.w #$1f,d0
    cmp.w   %d0,%d1                                         | 011960
    jblt    .L119e4                                         | 011962
.L11966:
    move.b  ENTITY_TYPE(%a1),%d0                            | 011966 move.b 17(a1),d0
    lea     A_enemy_types_fire_seeker-FGB(%a5),%a4          | 01196a lea $19180.l,a6 — SUBSTITUTED REGISTER
    jbsr    door_entity_type_in_mask                        | 011970 bsr.w $13bc2
    jbeq    .L11980                                         | 011974
    move.b  #1,%d3                                          | 011978
    jbra    .L11994                                         | 01197c
.L11980:
    move.b  ENTITY_TYPE(%a1),%d0                            | 011980 move.b 17(a1),d0
    lea     A_enemy_types_can_fire-FGB(%a5),%a4             | 011984 lea $19172.l,a6 — SUBSTITUTED REGISTER
    jbsr    door_entity_type_in_mask                        | 01198a bsr.w $13bc2
    jbeq    .L119e4                                         | 01198e
    clr.b   %d3                                             | 011992
.L11994:
    move.b  ENTITY_ALIVE(%a1),%d2                           | 011994 move.b 14(a1),d2
    jbeq    .L119e4                                         | 011998
    btst    #ALIVE_BIT_EXPLODING,%d2                        | 01199c btst #7,d2
    jbne    .L119e4                                         | 0119a0
    move.w  #ENEMY_SHOT_SLOT_COUNT - 1,%d7                  | 0119a4 move.w #$2,d7
.L119a8:
    tst.b   ENTITY_ALIVE(%a2)                               | 0119a8 tst.b 14(a2)
    jbne    .L119dc                                         | 0119ac
    clr.w   %d2                                             | 0119b0
    jbsr    .L11a2c                                         | 0119b2 bsr.w $11a2c — INTERNAL: spawn_enemy_shot
    jbra    .L119e4                                         | 0119b6

| DEAD, 0x119ba..0x119d8: past the unconditional `bra` above, and nothing branches here. It would
| have written a second shape of shot record. ../enemy.c leaves it out of the C entirely; it is
| transcribed because the order pin asks for every address in the span, and no case reaches it.
    move.w  %d2,ACTOR_SPAWN_TAG(%a2)                        | 0119ba move.w d2,16(a2)
    move.w  ENTITY_X(%a1),ENTITY_X(%a2)                     | 0119be
    move.w  ENTITY_Y(%a1),ENTITY_Y(%a2)                     | 0119c4
    move.b  #1,ENTITY_ALIVE(%a2)                            | 0119ca
    andi.w  #DEAD_SPAWN_HP_MASK,%d2                         | 0119d0 and.w #$7ff,d2
    move.w  %d2,ENTITY_HP(%a2)                              | 0119d4 move.w d2,26(a2)
    jbra    .L119e4                                         | 0119d8
.L119dc:
    lea     ENTITY_STRIDE(%a2),%a2                          | 0119dc lea 44(a2),a2
    dbf     %d7,.L119a8                                     | 0119e0

| ---- and the tick pass over all three slots, whatever the launch scan did (0x119e4) ------------
.L119e4:
    lea     A_enemy_shot_slots-FGB(%a5),%a2                 | 0119e4
    move.w  #ENEMY_SHOT_SLOT_COUNT - 1,%d7                  | 0119ea move.w #$2,d7
.L119ee:
    tst.b   ENTITY_ALIVE(%a2)                               | 0119ee tst.b 14(a2)
    jbeq    .L11a22                                         | 0119f2
    cmpi.b  #ENEMY_SHOT_TYPE_SEEKER,ENTITY_TYPE(%a2)        | 0119f6 cmpi.b #$b,17(a2)
    jbne    .L11a08                                         | 0119fc
    jbsr    .L11bbc                                         | 011a00 bsr.w $11bbc — INTERNAL: enemy_shot_tick_type0b
    jbra    .L11a22                                         | 011a04
.L11a08:
    cmpi.b  #ENEMY_SHOT_TYPE_HOMING,ENTITY_TYPE(%a2)        | 011a08 cmpi.b #$a,17(a2)
    jbne    .L11a1a                                         | 011a0e
    jbsr    .L11bde                                         | 011a12 bsr.w $11bde — INTERNAL: enemy_shot_tick_type0a
    jbra    .L11a22                                         | 011a16
.L11a1a:
    jbsr    door_entity_apply_velocity                      | 011a1a bsr.w $14306
    jbsr    door_entity_kill_if_offscreen                   | 011a1e bsr.w $13c9e
.L11a22:
    lea     ENTITY_STRIDE(%a2),%a2                          | 011a22 lea 44(a2),a2
    dbf     %d7,.L119ee                                     | 011a26
    rts                                                     | 011a2a

| ================================================================================================
| spawn_enemy_shot @ 0x11a2c — ../enemy.c. A0 = the player record, A1 = the firing enemy,
| A2 = the free shot slot, D3.b = the kind the caller's class tests chose (non-zero = a seeker).
| ================================================================================================
.L11a2c:
    tst.b   %d3                                             | 011a2c
    jbne    .L11b3a                                         | 011a2e
    cmpi.w  #ENEMY_SHOT_MIN_X,ENTITY_X(%a1)                 | 011a32 cmpi.w #$50,0(a1)
    jblt    .L11aca                                         | 011a38
    btst    #ENEMY_FIRE_BIT_STEERED,ACTOR_FIRE_FLAGS(%a1)   | 011a3c btst #1,42(a1)
    jbeq    .L11a7a                                         | 011a42
    btst    #ENEMY_FIRE_BIT_HALVED,ACTOR_FIRE_FLAGS(%a1)    | 011a46 btst #2,42(a1)
    jbeq    .L11a60                                         | 011a4c
    jbsr    door_rand16                                     | 011a50 bsr.w $13bf8
    andi.w  #BYTE_MASK,%d0                                  | 011a54 and.w #$ff,d0
    cmpi.w  #ENEMY_HOMING_CHANCE,%d0                        | 011a58 cmp.w #$32,d0
    jbge    .L11a7a                                         | 011a5c
.L11a60:
    move.b  ENTITY_TYPE(%a1),%d0                            | 011a60 move.b 17(a1),d0
    lea     A_enemy_types_fire_homing-FGB(%a5),%a4          | 011a64 lea $19164.l,a6 — SUBSTITUTED REGISTER
    movem.l %d0-%d7/%a0-%a6,-(%sp)                          | 011a6a movem.l #$fffe,-(a7)
    jbsr    door_entity_type_in_mask                        | 011a6e bsr.w $13bc2
    movem.l (%sp)+,%d0-%d7/%a0-%a6                          | 011a72 movem.l (a7)+,#$7fff
    jbne    .L11acc                                         | 011a76

| ---- the plain AIMED shot (0x11a7a): it flies its launch angle and is never steered again ------
.L11a7a:
    move.b  #ENEMY_SHOT_SPEED,SHOT_SPEED(%a2)               | 011a7a move.b #$4,30(a2)
    move.l  %a0,-(%sp)                                      | 011a80
    subi.w  #ENEMY_AIM_LEAD,ENTITY_Y(%a0)                   | 011a82 subi.w #$e,4(a0)
    move.w  ENTITY_X(%a1),ENTITY_X(%a2)                     | 011a88
    move.w  ENTITY_Y(%a1),ENTITY_Y(%a2)                     | 011a8e
    movea.l %a0,%a1                                         | 011a94
    jbsr    door_angle_to_target                            | 011a96 bsr.w $1424c
    movea.l (%sp)+,%a0                                      | 011a9a
    addi.w  #ENEMY_AIM_LEAD,ENTITY_Y(%a0)                   | 011a9c addi.w #$e,4(a0)
    move.b  SHOT_SPEED(%a2),%d1                             | 011aa2 move.b 30(a2),d1
    jbsr    door_entity_set_velocity_from_angle             | 011aa6 bsr.w $142d4
    move.b  #1,ENTITY_ALIVE(%a2)                            | 011aaa
    move.b  #ENEMY_SHOT_TYPE_AIMED,ENTITY_TYPE(%a2)         | 011ab0 move.b #$c,17(a2)
    move.w  #ENEMY_SHOT_ROWS,ENTITY_HEIGHT(%a2)             | 011ab6 move.w #$8,8(a2)
    move.b  #ENEMY_SHOT_AIMED_FRAME,ENTITY_ANIM_FRAME(%a2)  | 011abc move.b #$1,32(a2)
    move.l  #A_shot_sprite_aimed,ENTITY_SPRITE(%a2)         | 011ac2 move.l #$6115e,10(a2)
.L11aca:
    rts                                                     | 011aca

| ---- the HOMING missile (0x11acc): the aimed shot plus the steered block ----------------------
.L11acc:
    move.b  #PLAYER_ENTITY_INDEX,SHOT_TARGET_INDEX(%a2)     | 011acc move.b #$11,26(a2)
    move.b  #ENEMY_SHOT_SPEED,SHOT_SPEED(%a2)               | 011ad2 move.b #$4,30(a2)
    move.l  %a0,-(%sp)                                      | 011ad8
    subi.w  #ENEMY_AIM_LEAD,ENTITY_Y(%a0)                   | 011ada subi.w #$e,4(a0)
    move.w  ENTITY_X(%a1),ENTITY_X(%a2)                     | 011ae0
    move.w  ENTITY_Y(%a1),ENTITY_Y(%a2)                     | 011ae6
    movea.l %a0,%a1                                         | 011aec
    jbsr    door_angle_to_target                            | 011aee bsr.w $1424c
    move.b  %d0,SHOT_HEADING(%a2)                           | 011af2 move.b d0,29(a2)
    movea.l (%sp)+,%a0                                      | 011af6
    addi.w  #ENEMY_AIM_LEAD,ENTITY_Y(%a0)                   | 011af8 addi.w #$e,4(a0)
    move.b  SHOT_SPEED(%a2),%d1                             | 011afe move.b 30(a2),d1
    jbsr    door_entity_set_velocity_from_angle             | 011b02 bsr.w $142d4
    move.b  #1,ENTITY_ALIVE(%a2)                            | 011b06
    move.b  #ENEMY_SHOT_TYPE_HOMING,ENTITY_TYPE(%a2)        | 011b0c move.b #$a,17(a2)
    move.w  #ENEMY_SHOT_ROWS,ENTITY_HEIGHT(%a2)             | 011b12 move.w #$8,8(a2)
    move.b  #ENEMY_SHOT_STEERED_TTL,ENTITY_ANIM_FRAME(%a2)  | 011b18 move.b #$64,32(a2)
    move.l  #A_shot_sprite_homing,ENTITY_SPRITE(%a2)        | 011b1e move.l #$6e6ee,10(a2)
    move.b  #ENEMY_HOMING_TURN_PERIOD,SHOT_TURN_PERIOD(%a2) | 011b26 move.b #$6,28(a2)
    move.b  #ENEMY_STEERED_MAX_TURN,SHOT_MAX_TURN(%a2)      | 011b2c move.b #$1,31(a2)
    move.b  SHOT_TURN_PERIOD(%a2),SHOT_TURN_COUNTDOWN(%a2)  | 011b32 move.b 28(a2),27(a2)
    rts                                                     | 011b38

| ---- the SEEKER (0x11b3a): slow, on a global cooldown, and it takes no aim --------------------
| The heading is a literal and `entity_set_velocity_from_angle` is handed that same literal rather
| than a measured angle.
.L11b3a:
    tst.b   A_enemy_seeker_cooldown-FGB(%a5)                | 011b3a
    jbne    .L11b58                                         | 011b40
    move.b  #ENEMY_SEEKER_COOLDOWN,A_enemy_seeker_cooldown-FGB(%a5) | 011b44
    move.w  ENTITY_X(%a0),%d1                               | 011b4c
    cmp.w   ENTITY_X(%a1),%d1                               | 011b50
    jble    .L11b5a                                         | 011b54
.L11b58:
    rts                                                     | 011b58
.L11b5a:
    move.b  #PLAYER_ENTITY_INDEX,SHOT_TARGET_INDEX(%a2)     | 011b5a move.b #$11,26(a2)
    move.w  ENTITY_X(%a1),ENTITY_X(%a2)                     | 011b60
    move.w  ENTITY_Y(%a1),ENTITY_Y(%a2)                     | 011b66
    move.b  #1,ENTITY_ALIVE(%a2)                            | 011b6c
    move.b  #ENEMY_SHOT_TYPE_SEEKER,ENTITY_TYPE(%a2)        | 011b72 move.b #$b,17(a2)
    move.w  #ENEMY_SEEKER_ROWS,ENTITY_HEIGHT(%a2)           | 011b78 move.w #$b,8(a2)
    move.l  #A_shot_sprite_seeker,ENTITY_SPRITE(%a2)        | 011b7e move.l #$65d9e,10(a2)
    move.b  #ENEMY_SEEKER_TURN_PERIOD,SHOT_TURN_PERIOD(%a2) | 011b86 move.b #$2,28(a2)
    move.b  #ENEMY_SEEKER_SPEED,SHOT_SPEED(%a2)             | 011b8c move.b #$2,30(a2)
    move.b  #ENEMY_STEERED_MAX_TURN,SHOT_MAX_TURN(%a2)      | 011b92 move.b #$1,31(a2)
    move.b  SHOT_TURN_PERIOD(%a2),SHOT_TURN_COUNTDOWN(%a2)  | 011b98 move.b 28(a2),27(a2)
    move.b  #ENEMY_SEEKER_HEADING,SHOT_HEADING(%a2)         | 011b9e move.b #$30,29(a2)
    move.b  SHOT_SPEED(%a2),%d1                             | 011ba4 move.b 30(a2),d1
    move.l  #ENEMY_SEEKER_HEADING,%d0                       | 011ba8 move.l #$30,d0
    move.b  #ENEMY_SHOT_STEERED_TTL,ENTITY_ANIM_FRAME(%a2)  | 011bae move.b #$64,32(a2)
    movea.l %a0,%a1                                         | 011bb4  DEAD: the callee reads no A1 (../enemy.c says so)
    jbsr    door_entity_set_velocity_from_angle             | 011bb6 bsr.w $142d4
    rts                                                     | 011bba

| ================================================================================================
| enemy_shot_tick_type0b @ 0x11bbc — ../enemy.c. A2 = the shot record. The SEEKER's per-frame step:
| on expiry it becomes a ground-impact puff.
| ================================================================================================
.L11bbc:
    subi.b  #1,ENTITY_ANIM_FRAME(%a2)                       | 011bbc subi.b #$1,32(a2)
    jbne    .L11bcc                                         | 011bc2
    jbsr    door_enemy_morph_to_type6                       | 011bc6 bsr.w $13ad0 — frame.S's stub
    rts                                                     | 011bca
.L11bcc:
    movem.l %d7/%a0-%a2,-(%sp)                              | 011bcc movem.l #$01e0,-(a7)
    jbsr    door_entity_steer_toward_target                 | 011bd0 bsr.w $141d6
    movem.l (%sp)+,%d7/%a0-%a2                              | 011bd4 movem.l (a7)+,#$0780
    jbsr    door_entity_kill_if_offscreen                   | 011bd8 bsr.w $13c9e
    rts                                                     | 011bdc

| ================================================================================================
| enemy_shot_tick_type0a @ 0x11bde — ../enemy.c. A2 = the shot record. The HOMING shot's per-frame
| step, identical but that on expiry it simply stops being alive.
| ================================================================================================
.L11bde:
    subi.b  #1,ENTITY_ANIM_FRAME(%a2)                       | 011bde subi.b #$1,32(a2)
    jbne    .L11bee                                         | 011be4
    clr.b   ENTITY_ALIVE(%a2)                               | 011be8 clr.b 14(a2)
    rts                                                     | 011bec
.L11bee:
    movem.l %d7/%a0-%a2,-(%sp)                              | 011bee movem.l #$01e0,-(a7)
    jbsr    door_entity_steer_toward_target                 | 011bf2 bsr.w $141d6
    movem.l (%sp)+,%d7/%a0-%a2                              | 011bf6 movem.l (a7)+,#$0780
    jbsr    door_entity_kill_if_offscreen                   | 011bfa bsr.w $13c9e
    rts                                                     | 011bfe

| The stage's own exit. Both 0x118ec and 0x11902 leave to 0x11c00, the next slice's entry, and the C
| is `void` — so there is no answer to load into %d0 and nothing to compare it against.
.Lreturn:
        SPAWN_EPILOGUE

| ================================================================================================
| THE TRAMPOLINES — one thin block per callee, and the whole of the register translation.
|
| frame.S's block of the same name carries the long version of why these exist and what a door is;
| everything there holds here. What is worth saying about THIS file's twenty-three:
|
|   * TWO ARE NOT HERE AT ALL. `door_shot_retire_kind32` and `door_enemy_morph_to_type6` are
|     frame.S's, `.globl`, and this file jumps to them. A door slot names a HOST FUNCTION, and both
|     of this file's contracts are frame.S's exactly — A2 = the record, %a6 = the image — so a second
|     copy would be a second place for one contract to drift. `door_shot_retire_kind32` is
|     X-CARRYING (frame.S's `X_IN`/`X_OUT`), which is right here too: the original's four sites reach
|     it with whatever X the pass left, and the routine's early-return arms pass it straight back
|     out. Nothing in this slice READS the X afterwards — every one of the four is followed by a
|     `bra` — so the carry is faithful rather than load-bearing.
|
|   * EVERY OTHER STUB IS X-TRANSPARENT BY CONSTRUCTION. `PUSH_OFFSET` uses `suba.l`, which touches
|     no condition code; `tst.l`, `and.l`, `ext.w` and the `move`s below clear C and V and set N and
|     Z but leave X alone. A stub sits between two of the original's own instructions, and an X the
|     original never wrote is a carry into the next `abcd` that nothing here would report.
|
|   * THREE ANSWERS ARE MARSHALLED, each applied BEFORE the `movem` restores (neither `movem` nor
|     `rts` touches the condition codes on a 68000, so a flag set here survives to the twin's own
|     branch just as the original's callee's flag did):
|
|       Z    `entity_type_in_mask` — the original's callee answers with `btst`, which sets Z when the
|            bit is CLEAR, and the core RETURNS 1 when it is set. `tst.l %d0` is exactly that
|            inversion. Two sites branch on it (`beq` at 0x11974 and 0x1198e) and one on its
|            complement (`bne` at 0x11a76).
|       D0   `rand16` — the original's routine enters `moveq #0,d0`, so it leaves the word with its
|            high half ZERO, and 0x11948's `lsr.l #4,d0` reads the whole longword. The core is
|            declared `uint16_t`, whose high half neither ABI promises, so the stub masks it.
|       D0   `angle_to_target` — the original's callee ends `move.w d4,d0`, so the answer is D0's LOW
|            WORD over the caller's own high word. The stub reproduces that rather than delivering
|            the door's whole longword.
|
| Two gas macros stand in for what would otherwise be sixteen near-identical blocks. They are not an
| abstraction over anything subtle: a `void f(image)` stub and a `void f(image, pointer)` stub have
| no per-callee decisions left in them, and sixteen hand copies would be sixteen places for one
| `lea` to unwind by the wrong amount.
| ================================================================================================
| THE DOOR'S BAND IS THE KIT'S CONSTANT, USED DIRECTLY — tools/recreate_kit/asm_twin.py owns
| DOOR_BASE/DOOR_STRIDE because it is what WATCHES the band, and kit.mk passes both in as -D's.
#ifdef ZY_ASM_FRAME_DOOR
# define ZY_CALL(slot, fn)      jsr     (RECREATE_DOOR_BASE + (slot) * RECREATE_DOOR_STRIDE)
#else
# define ZY_CALL(slot, fn)      jsr     fn
#endif

        .macro  SCRATCH_SAVE
        movem.l %d0-%d1/%a0-%a1,-(%sp)
        .endm
        .macro  SCRATCH_RESTORE
        movem.l (%sp)+,%d0-%d1/%a0-%a1
        .endm

| Push one of the body's POINTERS as the image OFFSET the core wants. `suba.l` AND NOT `sub.l`, for
| the reason frame.S's copy of this macro gives at length: `sub.l` sets X, `suba.l` touches no
| condition code at all, and a stub sits between two of the original's own instructions.
        .macro  PUSH_OFFSET areg
        movea.l \areg,%a0
        suba.l  %a6,%a0
        move.l  %a0,-(%sp)
        .endm

| ---- void f(uint8_t *image) ---- the ten callees this slice reaches with no register argument
        .macro  DOOR_IMAGE_ONLY name, slot
        .globl  door_\name
door_\name:
        SCRATCH_SAVE
        move.l  %a6,-(%sp)
        ZY_CALL(\slot, \name)
        lea     4(%sp),%sp
        SCRATCH_RESTORE
        rts
        .endm

| ---- void f(uint8_t *image, uint32_t record) ---- ...and the six it reaches with one pointer
        .macro  DOOR_IMAGE_AND_POINTER name, slot, areg
        .globl  door_\name
door_\name:
        SCRATCH_SAVE
        PUSH_OFFSET \areg
        move.l  %a6,-(%sp)
        ZY_CALL(\slot, \name)
        lea     8(%sp),%sp
        SCRATCH_RESTORE
        rts
        .endm

        DOOR_IMAGE_ONLY explosion_animate_all, ZY_DOOR_explosion_animate_all
        DOOR_IMAGE_ONLY anim_ground_objects, ZY_DOOR_anim_ground_objects
        DOOR_IMAGE_ONLY enemies_animate_all, ZY_DOOR_enemies_animate_all
        DOOR_IMAGE_ONLY enemies_move_all, ZY_DOOR_enemies_move_all
        DOOR_IMAGE_ONLY player_shot_update_all, ZY_DOOR_player_shot_update_all
        DOOR_IMAGE_ONLY squadron_spawn_tick, ZY_DOOR_squadron_spawn_tick
        DOOR_IMAGE_ONLY asteroids_move, ZY_DOOR_asteroids_move
        DOOR_IMAGE_ONLY asteroids_animate, ZY_DOOR_asteroids_animate
        DOOR_IMAGE_ONLY mothership_move_and_place, ZY_DOOR_mothership_move_and_place
        DOOR_IMAGE_ONLY mothership_draw, ZY_DOOR_mothership_draw

| A3 = the shot slot, for both per-frame updates (../weapon.c's register map).
        DOOR_IMAGE_AND_POINTER seeker_update, ZY_DOOR_seeker_update, %a3
        DOOR_IMAGE_AND_POINTER homing_missile_update, ZY_DOOR_homing_missile_update, %a3
| A2 = the entity record, for all three (../util.c's and ../weapon.c's register maps).
        DOOR_IMAGE_AND_POINTER entity_apply_velocity, ZY_DOOR_entity_apply_velocity, %a2
        DOOR_IMAGE_AND_POINTER entity_kill_if_offscreen, ZY_DOOR_entity_kill_if_offscreen, %a2
        DOOR_IMAGE_AND_POINTER entity_steer_toward_target, ZY_DOOR_entity_steer_toward_target, %a2
| A4 = the script cursor (../enemy.c's register map).
        DOOR_IMAGE_AND_POINTER wavescript_spawn_trio_type0e, ZY_DOOR_wavescript_spawn_trio_type0e, %a4

| ---- uint16_t rand16(uint8_t *image) ---- no arguments; the word in D0, high half CLEAR
        .globl  door_rand16
door_rand16:
        movem.l %d1/%a0-%a1,-(%sp)              | %d0 is DELIVERED, so it is not saved
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_rand16, rand16)
        lea     4(%sp),%sp
        andi.l  #WORD_MASK,%d0                  | the original's routine enters `moveq #0,d0`
        movem.l (%sp)+,%d1/%a0-%a1
        rts

| ---- void wavescript_spawn_wave(uint8_t *image, uint32_t cursor, uint16_t opcode, uint16_t base_y,
| ----                            uint8_t actor_type, uint32_t sprite) ----
| A4 = cursor, D7.w = opcode, D6.w = base y, D1.b = actor type, and the SUBSTITUTED %a3 = the sprite
| bank the original loads into A5 — which is a longword IMMEDIATE naming a bank, so it is already an
| image offset and is pushed as it stands rather than through PUSH_OFFSET.
        .globl  door_wavescript_spawn_wave
door_wavescript_spawn_wave:
        SCRATCH_SAVE
        move.l  %a3,-(%sp)                      | the sprite bank: an OFFSET, not a pointer
        move.l  %d1,-(%sp)
        move.l  %d6,-(%sp)
        move.l  %d7,-(%sp)
        PUSH_OFFSET %a4
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_wavescript_spawn_wave, wavescript_spawn_wave)
        lea     24(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void groundscript_spawn_type10/_type0f(uint8_t *image, uint32_t cursor, uint32_t y_register)
| A4 = the ground-script cursor, D7 = the carried y register — the WHOLE longword, because the
| callee's free-slot guard tests its high word too (../enemy.c's register map).
        .macro  DOOR_GROUND_SPAWNER name, slot
        .globl  door_\name
door_\name:
        SCRATCH_SAVE
        move.l  %d7,-(%sp)
        PUSH_OFFSET %a4
        move.l  %a6,-(%sp)
        ZY_CALL(\slot, \name)
        lea     12(%sp),%sp
        SCRATCH_RESTORE
        rts
        .endm

        DOOR_GROUND_SPAWNER groundscript_spawn_type10, ZY_DOOR_groundscript_spawn_type10
        DOOR_GROUND_SPAWNER groundscript_spawn_type0f, ZY_DOOR_groundscript_spawn_type0f

| ---- unsigned entity_type_in_mask(const uint8_t *image, uint32_t bitmap, uint16_t type) ----
| The SUBSTITUTED %a4 = the class bitmap the original loads into A6, D0.b = the type. The answer is
| the ZERO flag, which the original's `btst` sets when the bit is CLEAR — the inverse of what the
| core returns, which is what `tst.l %d0` produces.
        .globl  door_entity_type_in_mask
door_entity_type_in_mask:
        SCRATCH_SAVE
        move.l  %d0,-(%sp)
        PUSH_OFFSET %a4
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_entity_type_in_mask, entity_type_in_mask)
        lea     12(%sp),%sp
        tst.l   %d0                             | the Z the original's callee answers in
        SCRATCH_RESTORE
        rts

| ---- uint16_t angle_to_target(const uint8_t *image, uint32_t self, uint32_t target) ----
| A2 = the entity asking, A1 = the entity aimed at. THE ANSWER IS D0'S LOW WORD OVER THE CALLER'S OWN
| HIGH WORD (../util.c's register map: the original ends `move.w d4,d0`), so the caller's D0 is
| parked across the call and the angle laid into its low half afterwards.
        .globl  door_angle_to_target
door_angle_to_target:
        movem.l %d1/%a0-%a1,-(%sp)              | %d0 is DELIVERED, so it is not saved
        move.l  %d0,-(%sp)                      | ...but its high word is part of the answer
        PUSH_OFFSET %a1
        PUSH_OFFSET %a2
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_angle_to_target, angle_to_target)
        lea     12(%sp),%sp
        move.l  %d0,%d1                         | the core's answer
        move.l  (%sp)+,%d0                      | the caller's own D0 back...
        move.w  %d1,%d0                         | ...with the angle over its low word
        movem.l (%sp)+,%d1/%a0-%a1
        rts

| ---- void entity_set_velocity_from_angle(uint8_t *image, uint32_t entity, uint32_t angle,
| ----                                     int16_t speed) ----
| A2 = the entity, D0 = the angle (the core masks it to a byte), D1.b = the SIGNED speed — which the
| original's callee reads through its own `ext.w d1`, and which the core takes as an `int16_t`. So
| the stub sign-extends the byte here rather than pushing D1's stale high half.
        .globl  door_entity_set_velocity_from_angle
door_entity_set_velocity_from_angle:
        SCRATCH_SAVE
        ext.w   %d1                             | D1.b is signed (../enemy.c's `shot_speed`)
        move.l  %d1,-(%sp)
        move.l  %d0,-(%sp)
        PUSH_OFFSET %a2
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_entity_set_velocity_from_angle, entity_set_velocity_from_angle)
        lea     16(%sp),%sp
        SCRATCH_RESTORE
        rts
