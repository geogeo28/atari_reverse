| frame.S — the asm twin for the frame loop's LAST STAGE, TRANSCRIBED from the original binary.
|
|   frame_resolve_hits_and_game_state_asm  <- the original @ [0x11d30, 0x1296e), the C reference
|                                             frame_resolve_hits_and_game_state in ../frame.c
|
| WHAT A TWIN IS is written out in scroll_emit.S and in README.md beside it, and holds here word for
| word: the C in ../frame.c is byte-for-byte equivalent to the original (test/test_frame.py's
| differential against the Musashi oracle), the original's own instructions are in
| ../../out/prg_dis.txt, and everything from `.Lbody` on is that instruction sequence in order.
|
| WHY THIS ONE. Waves A and B left every named hot routine within ~1.03x of the original, and the
| whole of the frame's remaining excess was HERE: 211,784 cycles a frame of this stage's own
| instructions against the original's ~71,600 for the same span — 2.96x, and 140,135 cycles a frame,
| which is the entire distance between our 417,257-cycle frame and the original's 277,122. It is the
| stage the profiler gives no row to, because the loop `bra`s into it rather than calling it.
|
| WHAT IS DIFFERENT ABOUT IT, and why it needed a new kit capability. Waves A and B twinned LEAF
| routines. This stage calls sixteen verified C cores, and the twin blob is linked ALONE — so a
| `jsr collision_chain_walk` did not link at all until `tools/recreate_kit`'s CALLBACK DOOR existed.
| Two more of its seams (the raster and vblank spins, and the MFP `bset`) are modelled HOST-SIDE by
| the kit and can never be m68k code at all. TRAP_MODEL.md carries the door; the trampolines at the
| foot of this file are its call sites.
|
| THE THREE TRANSLATIONS, and only these three.
|
| **1. The image base — and here it is TWO registers, not one.** The original IS the image, so it
| reads globals absolutely (`tst.b $19aad.l`). The reconstruction is position-independent and gets
| the image as a pointer, so every one of the sixty-six globals this stage names becomes
| base-relative. They span 0x1797e..0x19f44, which is 9,670 bytes — small enough for one signed
| 16-bit displacement window, so:
|
|     %a6 = image            the raw base: the trampolines' pointer->offset arithmetic, and the one
|                            store the original makes to ABSOLUTE ADDRESS 8 (0x122c2 and 0x123f4),
|                            which is below the window
|     %a5 = image + FGB      FGB = 0x18000, so `A_entity_table-FGB(%a5)` is -0x572 and
|                            `A_boss_hitpoints-FGB(%a5)` is +0x1f44 — both comfortably in range
|
| The original uses only %a0-%a4 and %a7, so neither reserved register displaces anything of its
| own. The body's address registers hold REAL POINTERS, exactly as the original's hold real
| addresses; only the trampolines convert back to offsets.
|
| **TWO SUBSTITUTIONS PULL OPPOSITE WAYS, AND THE MEASUREMENT SETTLED IT AGAINST THE PREDICTION.**
| Base-relative global access IS cheaper than the original's absolute-long forms — `tst.b d16(An)` is
| 12 where `tst.b abs.l` is 14, `move.b #imm,d16(An)` 16 against 20, `lea d16(An),An` 8 against 12 —
| and this header first predicted cost bars below 1.00x on that basis. IT WAS WRONG. The stage makes
| nine or ten door calls a frame, and a trampoline (a four-register `movem` pair, the `suba.l`
| pointer-to-offset conversions, the pushes and the `lea` unwind) costs far more than the single
| `bsr` the original has in its place. The trampolines win: measured, the twin is 240-360 cycles OVER
| the original on every band, and test/test_asm_frame.py's bars are **1.0223x-1.0369x** with about
| seven cycles of slack each. Its cost section carries the four-row table.
|
| **AND THE BYTE PIN IS GONE ENTIRELY — not narrowed, gone.** Wave A's twenty page blits are
| byte-identical to the original's machine code because they mention no address at all. Almost every
| instruction here mentions one, and the loops that look like exceptions are not: the starfield's
| three inner loops each reload `A_screen_back` and add the base, so none of them is the original's
| own bytes either. There is no `_body`/`_body_end` bracket in this file and no span one could cover.
|
| **WHAT STANDS IN ITS PLACE** is named in test/test_asm_frame.py: the differential per exit arm, the
| cost bars above, and a TRANSCRIPTION-ORDER pin — all 703 of the original's instruction addresses
| present exactly once, in ascending order, no gaps and no extras. That is weaker than bytes and this
| file does not pretend otherwise; it catches a band spliced out of order, an instruction dropped or
| a line duplicated, and it does not catch a wrong operand. README.md's "What wave C added" carries
| the scoping.
|
| **2. A pointer LOADED OUT OF THE IMAGE is an offset.** `movea.l $1797e.l,%a0` reads the back
| buffer, which the reconstruction stores as an OFFSET, so the base is added where the original had
| nothing to add — exactly as sprite.S does. A longword IMMEDIATE that names a sprite bank is
| ALREADY an offset and is left alone.
|
| **3. The exits.** The original does not `rts`: it `bra`s to one of five addresses in the frame
| loop. `frame_loop_once` stays C, so the twin answers with ../../include/frame.h's `frame_exit`
| for the address it would have branched to. The five are at the foot of the body.
|
| REGISTERS. The prologue saves %d2-%d7/%a2-%a6 — every callee-saved register the stage touches,
| plus the two it reserves. **The surface that catches a clobbered callee-saved register is NOT the
| differential** (it compares the image, and a corrupted %a2 leaves the image perfect and breaks the
| C CALLER instead): it is `bash atari/build.sh game && python3 atari/smoke.py game`. README.md's
| "Registers" says so at length, and it is why this twin is not done until the game smoke is green.

        .text

| WHICH BUILD IS THIS. The kit's Makefile defines RECREATE_HOST_DIFFERENTIAL for the off-target
| assembly (tools/recreate_kit/kit.mk's ASM_CFLAGS, the same marker its CFLAGS carry for the
| candidate .so); the target build defines nothing. Everything door-shaped in this file hangs off
| the one project-private name below, so the door reads as one story rather than as four
| appearances of a kit marker — and so atari/build.sh has nothing to pass.
#ifdef RECREATE_HOST_DIFFERENTIAL
# define ZY_ASM_FRAME_DOOR 1
#endif


| ---- the constants, named exactly as the headers in ../../include name them ------------------------------
| test/test_constants.py::test_asm_twin_equates_match_the_headers pins every one of these to its
| header, and requires every .S to contribute at least one — so a name that drifted from its header
| fails rather than going unchecked.
        .equ    ACTOR_SPEED,                           0x1e        | enemy.h
        .equ    ALIVE_BIT_EXPLODING,                   7           | frame.h
        .equ    A_active_bullets,                      0x19909     | init.h
        .equ    A_boss_hitpoints,                      0x19f44     | mothership.h
        .equ    A_boss_sequence_active,                0x19aad     | sprite.h
        .equ    A_current_player_index,                0x1991b     | hud.h
        .equ    A_death_event_flags,                   0x198c4     | weapon.h
        .equ    A_dying_player_section_index,          0x19896     | frame.h
        .equ    A_enemy_seeker_cooldown,               0x19abf     | enemy.h
        .equ    A_enemy_shot_slots,                    0x17b96     | enemy.h
        .equ    A_enemy_slots,                         0x17c1a     | enemy.h
        .equ    A_entity_boss_parts,                   0x18142     | mothership.h
        .equ    A_entity_collision_masks,              0x18252     | collision.h
        .equ    A_entity_gunsight,                     0x17dd2     | weapon.h
        .equ    A_entity_table,                        0x17a8e     | player.h
        .equ    A_explosion_group_active_bits,         0x19670     | enemy.h
        .equ    A_explosion_group_members,             0x19664     | enemy.h
        .equ    A_explosion_large_frame_ptrs,          0x1922c     | init.h
        .equ    A_explosion_large_sprite,              0x61b5e     | frame.h
        .equ    A_explosion_phase_even,                0x198ad     | frame.h
        .equ    A_explosion_phase_odd,                 0x198c5     | enemy.h
        .equ    A_explosion_small_frame_ptrs,          0x191fc     | enemy.h
        .equ    A_extra_life_threshold_bcd,            0x195d8     | score.h
        .equ    A_level_section,                       0x19895     | init.h
        .equ    A_lives,                               0x1991a     | hud.h
        .equ    A_map_column,                          0x198a6     | init.h
        .equ    A_map_page,                            0x198a5     | init.h
        .equ    A_map_ptr,                             0x18242     | init.h
        .equ    A_mothership_explosion_sprite,         0x5cf7e     | mothership.h
        .equ    A_mothership_index,                    0x1987c     | init.h
        .equ    A_mothership_offscreen,                0x19916     | mothership.h
        .equ    A_mothership_phase_timer,              0x19efe     | mothership.h
        .equ    A_mothership_ready,                    0x198b0     | mothership.h
        .equ    A_mothership_wave_clear_count,         0x19915     | init.h
        .equ    A_mothership_x,                        0x19dd0     | mothership.h
        .equ    A_mothership_y,                        0x19dd2     | mothership.h
        .equ    A_panel_redraw_mask,                   0x19904     | hud.h
        .equ    A_player_record,                       0x17d7a     | enemy.h
        .equ    A_player_records,                      0x19f02     | init.h
        .equ    A_player_score_bcd,                    0x195e0     | score.h
        .equ    A_power_gauge_display,                 0x198c3     | hud.h
        .equ    A_powerup_capsule_sprite,              0x5f3be     | frame.h
        .equ    A_powerup_cursor,                      0x19905     | hud.h
        .equ    A_raster_phase,                        0x198a8     | irq.h
        .equ    A_score_award_table_bcd,               0x195e4     | score.h
        .equ    A_screen_back,                         0x1797e     | video.h
        .equ    A_scroll_frozen,                       0x198b1     | enemy.h
        .equ    A_scroll_pos,                          0x195cc     | init.h
        .equ    A_section_end_delay_counter,           0x19ac0     | init.h
        .equ    A_seeker_lock_target_index,            0x19917     | weapon.h
        .equ    A_shield_decay_timer,                  0x19dca     | weapon.h
        .equ    A_shield_level,                        0x1990a     | weapon.h
        .equ    A_ship_invulnerable,                   0x19912     | weapon.h
        .equ    A_ship_record_shadow,                  0x17da6     | player.h
        .equ    A_ship_speed_level,                    0x19907     | player.h
        .equ    A_speed_decay_timer,                   0x19dc8     | weapon.h
        .equ    A_squadron_kill_counters,              0x198bb     | enemy.h
        .equ    A_starfield_layer2_phase,              0x198a9     | init.h
        .equ    A_starfield_layer3_countdown,          0x198aa     | init.h
        .equ    A_starfield_pixel_masks,               0x17a42     | frame.h
        .equ    A_starfield_table,                     0x179fa     | frame.h
        .equ    A_unused_section_end_flag,             0x19ce5     | frame.h
        .equ    A_vbl_wait_flag,                       0x198a7     | irq.h
        .equ    A_weapon_decay_timer,                  0x19dcc     | player.h
        .equ    A_weapon_power_level,                  0x19908     | player.h
        .equ    BOSS_DEATH_EXPLOSION_DX,               0x50        | frame.h
        .equ    BOSS_DEATH_EXPLOSION_DY,               6           | frame.h
        .equ    BOSS_HIT_SOUND,                        0x2c        | frame.h
        .equ    BULLET_TYPE,                           0x34        | frame.h
        .equ    BUS_ERROR_VECTOR,                      0x8         | frame.h
        .equ    COLLISION_ROW_BYTES,                   4           | collision.h
        .equ    DEATH_EVENT_BIT_SHIP,                  0           | weapon.h
        .equ    DEATH_EVENT_BOSS_BIT,                  1           | frame.h
        .equ    ENEMY_EXPLODING_ALIVE,                 0x80        | frame.h
        .equ    ENEMY_EXPLOSION_ROWS,                  0x10        | frame.h
        .equ    ENEMY_EXPLOSION_ROWS_LARGE,            8           | frame.h
        .equ    ENEMY_HIT_SOUND,                       0x2c        | frame.h
        .equ    ENEMY_SHOT_SLOT_COUNT,                 3           | frame.h
        .equ    ENEMY_SHOT_TOP_SLOT,                   8           | frame.h
        .equ    ENEMY_SLOT_COUNT,                      8           | enemy.h
        .equ    ENEMY_SHOT_SLOT_FIRST,                 6           | frame.h
        .equ    ENEMY_SLOT_FIRST,                      9           | frame.h
        .equ    ENEMY_TYPE_ARMOURED_A,                 0x10        | frame.h
        .equ    ENEMY_TYPE_ARMOURED_B,                 0x0f        | frame.h
        .equ    ENEMY_TYPE_BIG,                        0x0e        | frame.h
        .equ    ENEMY_TYPE_BOSS_SEGMENT,               0x02        | frame.h
        .equ    ENEMY_TYPE_INVULNERABLE,               0x01        | frame.h
        .equ    ENEMY_TYPE_SMALL_A,                    0x14        | frame.h
        .equ    ENEMY_TYPE_SMALL_B,                    0x16        | frame.h
        .equ    ENTITY_ALIVE,                          0x0e        | entity.h
        .equ    ENTITY_ANIM_FRAME,                     0x20        | entity.h
        .equ    ENTITY_HEIGHT,                         0x08        | entity.h
        .equ    ENTITY_HP,                             0x1a        | entity.h
        .equ    ENTITY_INDEX_SHIP,                     0x11        | weapon.h
        .equ    ENTITY_INDEX_TRAIL_DRONE,              0x13        | weapon.h
        .equ    ENTITY_PIXEL_HIT,                      0x0f        | entity.h
        .equ    ENTITY_SPRITE,                         0x0a        | entity.h
        .equ    ENTITY_SQUADRON,                       0x21        | entity.h
        .equ    ENTITY_STRIDE,                         0x2c        | entity.h
        .equ    ENTITY_TYPE,                           0x11        | entity.h
        .equ    ENTITY_X,                              0x00        | entity.h
        .equ    ENTITY_Y,                              0x04        | entity.h
        .equ    EXPLOSION_BIT_SECTION_END,             0           | frame.h
        .equ    EXPLOSION_BIT_SHIP_DEATH,              1           | frame.h
        .equ    EXPLOSION_CREDIT_TAG_OFFSET,           0x14        | frame.h
        .equ    EXPLOSION_DONE_FRAME,                  0x0d        | frame.h
        .equ    EXPLOSION_FRAME_MASK,                  0x7f        | frame.h
        .equ    EXPLOSION_GROUP_MEMBERS,               6           | frame.h
        .equ    EXPLOSION_LAST_FRAME,                  0x0d        | frame.h
        .equ    EXPLOSION_NO_CREDIT_TAG,               0xaa        | frame.h
        .equ    EXPLOSION_PART_FRAME,                  0x10        | enemy.h
        .equ    EXPLOSION_PART_TYPE,                   0x64        | enemy.h
        .equ    EXPLOSION_TYPE_LARGE,                  0x65        | frame.h
        .equ    EXPLOSION_X_ALIGN,                     0xfffc      | enemy.h
        .equ    FRAME_RASTER_PHASE_READY,              1           | frame.h
        .equ    FRAME_RASTER_WAIT_PC,                  0x126ee     | frame.h
        .equ    FRAME_VBL_WAIT_ARMED,                  1           | frame.h
        .equ    FRAME_VBL_WAIT_DONE,                   0           | frame.h
        .equ    FRAME_VBL_WAIT_PC,                     0x1270c     | frame.h
        .equ    GROUND_ABSORB_TYPE_AIMED,              0x0c        | frame.h
        .equ    GROUND_ABSORB_TYPE_SEEKER,             0x0b        | frame.h
        .equ    GUNSIGHT_ENEMY_MASK,                   0x1fe00     | frame.h
        .equ    HW_MFP_IERB,                           0xfffa09    | init.h
        .equ    IKBD_CMD_INTERROGATE_JOYSTICK,         0x16        | frame.h
        .equ    MAP_PAGES,                             8           | init.h
        .equ    MFP_ACIA_CHANNEL_BIT,                  6           | irq.h
        .equ    MOTHERSHIP_INDEX_SEGMENTED,            5           | frame.h
        .equ    MOTHERSHIP_LEAVE_FRAME,                0x640       | frame.h
        .equ    MOTHERSHIP_PAIR_BYTES,                 0x58        | mothership.h
        .equ    MOTHERSHIP_TAIL_PAIRS,                 4           | frame.h
        .equ    MOTHERSHIP_TAIL_SEGMENTS,              5           | mothership.h
        .equ    MOTHERSHIP_TURN_CLEAR_OFF,             0x27        | frame.h
        .equ    MOTHERSHIP_TURN_FLAG,                  1           | frame.h
        .equ    MOTHERSHIP_TURN_FLAG_OFF,              0x26        | frame.h
        .equ    MOTHERSHIP_TURN_FRAME,                 0x5dc       | frame.h
        .equ    MOTHERSHIP_TURN_HEADING,               0x7f        | frame.h
        .equ    MOTHERSHIP_TURN_HEADING_OFF,           0x28        | frame.h
        .equ    MOTHERSHIP_TURN_SPEED,                 0xc0        | frame.h
        .equ    MOTHERSHIP_TURN_SPEED_OFF,             0x22        | frame.h
        .equ    MOTHERSHIP_WAVE_CLEARS_TO_END,         2           | frame.h
        .equ    PANEL_REDRAW_GAUGE_BIT,                2           | hud.h
        .equ    PLAYER_RECORD_BYTES,                   0x0e        | init.h
        .equ    PLAYER_SHOT_SLOTS,                     6           | weapon.h
        .equ    PLAYER_SWAP_ATTEMPTS,                  3           | frame.h
        .equ    POWERUP_CAPSULE_LARGE_ANIM_FRAME,      0x55        | frame.h
        .equ    POWERUP_CAPSULE_LARGE_RISE,            3           | frame.h
        .equ    POWERUP_CAPSULE_ROWS,                  0x10        | frame.h
        .equ    POWERUP_CAPSULE_SOUND,                 0x1c        | frame.h
        .equ    POWERUP_CAPSULE_SPAWN_TAG,             1           | frame.h
        .equ    POWERUP_DECAY_TICKS,                   0x3e8       | player.h
        .equ    SCORE_AWARD_BOSS,                      3           | frame.h
        .equ    SCORE_BCD_BYTES,                       4           | score.h
        .equ    SCROLL_PHASES,                         20          | scroll.h
        .equ    SHIP_DEATH_EXPLOSION_GROUP,            1           | weapon.h
        .equ    SHIP_HIT_ENTITY_MASK,                  0xffffffc0  | frame.h
        .equ    SHIP_HIT_OWN_SHOT_MASK,                0x3f        | frame.h
        .equ    SHIP_RECORD_MASK,                      0x60000     | frame.h
        .equ    SHOT_TYPE_BOMB,                        0x33        | weapon.h
        .equ    SHOT_TYPE_MISSILE,                     0x32        | weapon.h
        .equ    SHOT_TYPE_PUFF,                        0x37        | weapon.h
        .equ    SHOT_TYPE_SEEKER,                      0x36        | weapon.h
        .equ    SQUADRON_ID_MASK,                      0xf         | frame.h
        .equ    STARFIELD_LAYER3_PERIOD,               3           | init.h
        .equ    STARFIELD_PLANE2_OFFSET,               4           | frame.h
        .equ    STARFIELD_RESPAWN_X,                   0x13f       | frame.h
        .equ    STARFIELD_STARS,                       6           | frame.h
        .equ    STARFIELD_X_CELL_MASK,                 0xfff0      | frame.h
        .equ    STARFIELD_X_PIXEL_MASK,                0xf         | frame.h
        .equ    TYPE_POWERUP_CAPSULE,                  0x11        | weapon.h
        .equ    WEAPON_POWER_LEVEL_MIN,                2           | player.h

| The five answers, which are an ENUM in ../../include/frame.h rather than a #define, so they are
| spelt here and PINNED against that enum by test_asm_frame.py rather than scraped.
        .equ    FRAME_EXIT_TITLE,              0
        .equ    FRAME_EXIT_RELOAD_SECTION,     1
        .equ    FRAME_EXIT_RESTART_SECTION,    2
        .equ    FRAME_EXIT_ADVANCE_SECTION,    3
        .equ    FRAME_EXIT_NEXT_FRAME,         4

        .equ    ZY_DOOR_collision_chain_walk,          0
        .equ    ZY_DOOR_score_add_bcd,                 1
        .equ    ZY_DOOR_enemy_morph_to_type6,          2
        .equ    ZY_DOOR_ship_resolve_entity_hits,      3
        .equ    ZY_DOOR_entity_type_is_lockable,       4
        .equ    ZY_DOOR_powerup_downgrade_on_death,    5
        .equ    ZY_DOOR_bomb_update,                   6
        .equ    ZY_DOOR_ikbd_send_cmd,                 7
        .equ    ZY_DOOR_mothership_segment_hit,        8
        .equ    ZY_DOOR_explosion_spawn,               9
        .equ    ZY_DOOR_shot_retire_kind32,            10
        .equ    ZY_DOOR_shot_retire_kind36,            11
        .equ    ZY_DOOR_shot_retire_kind33,            12
        .equ    ZY_DOOR_sound_start,                   13
        .equ    ZY_DOOR_screen_flip_buffers,           14
        .equ    ZY_DOOR_game_over_screen,              15
        .equ    ZY_DOOR_sched_wait8,                   16
        .equ    ZY_DOOR_hw_bset8,                      17


| The global window's origin. Not a header constant: it is this file's own, and the only thing that
| makes it right is that every global the stage names lands within a signed 16-bit displacement of
| it. test_asm_frame.py asserts exactly that over the whole list, so a global added later that falls
| outside the window fails loudly rather than assembling into a wild displacement.
        .equ    FGB, 0x18000

| What the prologue pushes, and every argument offset measured past it.
        .equ    SAVED, (11 * 4)                 | %d2-%d7/%a2-%a6
        .equ    ARG_IMAGE, 4 + SAVED
        .equ    ARG_SOUND_CHANNEL, 8 + SAVED

        .macro  FRAME_PROLOGUE
        movem.l %d2-%d7/%a2-%a6,-(%sp)
        movea.l ARG_IMAGE(%sp),%a6              | the raw image base
        movea.l %a6,%a5
        adda.l  #FGB,%a5                        | ...and the globals' window
        move.l  ARG_SOUND_CHANNEL(%sp),%d0      | D0 — the channel the stage is entered with
        .endm

        .macro  FRAME_EPILOGUE
        movem.l (%sp)+,%d2-%d7/%a2-%a6
        rts
        .endm

| ================================================================================================
| frame_exit frame_resolve_hits_and_game_state_asm(uint8_t *image, uint32_t sound_channel)
| ================================================================================================
        .globl  frame_resolve_hits_and_game_state_asm
frame_resolve_hits_and_game_state_asm:
        FRAME_PROLOGUE
        .globl  frame_resolve_hits_and_game_state_body
frame_resolve_hits_and_game_state_body:
| ==== band 1 — 0x11d30 .. 0x11fdc =================================================================
| frame_enemy_shots_absorb / frame_bombs_update / frame_seeker_lock / frame_ship_collision +
| frame_ship_hit / frame_player_shots_resolve.  159 instructions, transcribed in order.

| ---- enemy shots 8, 7, 6: absorb the ones only the landscape explains (0x11d30) ------------------
    tst.b   A_boss_sequence_active-FGB(%a5)                 | 011d30
    jbne    .L11d6a                                         | 011d36
    moveq   #ENEMY_SHOT_SLOT_COUNT - 1,%d7                  | 011d3a moveq #$2,d7
    moveq   #ENEMY_SHOT_TOP_SLOT,%d0                        | 011d3c moveq #$8,d0
.L11d3e:
    movem.l %d0/%d7,-(%sp)                                  | 011d3e movem.l #$8100,-(a7)
    jbsr    door_collision_chain_walk                       | 011d42 bsr.w $12d44
    movem.l (%sp)+,%d0/%d7                                  | 011d46 movem.l (a7)+,#$0081
    jbeq    .L11d60                                         | 011d4a
    move.l  %d0,%d1                                         | 011d4e
    mulu.w  #ENTITY_STRIDE,%d1                              | 011d50 mulu.w #$2c,d1
    lea     A_entity_table-FGB(%a5),%a2                     | 011d54
    adda.l  %d1,%a2                                         | 011d5a
    clr.b   ENTITY_ALIVE(%a2)                               | 011d5c clr.b 14(a2)
.L11d60:
    subi.l  #1,%d0                                          | 011d60 sub.l #$1,d0 (gas: SUBI, same size)
    dbf     %d7,.L11d3e                                     | 011d66

| ---- the six player-shot slots: step every bomb (0x11d6a) ----------------------------------------
.L11d6a:
    lea     A_entity_table-FGB(%a5),%a3                     | 011d6a
    move.w  #PLAYER_SHOT_SLOTS - 1,%d7                      | 011d70 move.w #$5,d7
.L11d74:
    cmpi.b  #SHOT_TYPE_BOMB,ENTITY_TYPE(%a3)                | 011d74 cmpi.b #$33,17(a3)
    jbne    .L11d8a                                         | 011d7a
    movem.l %d7/%a3,-(%sp)                                  | 011d7e movem.l #$0110,-(a7)
    jbsr    door_bomb_update                                | 011d82 bsr.w $14376
    movem.l (%sp)+,%d7/%a3                                  | 011d86 movem.l (a7)+,#$0880
.L11d8a:
    lea     ENTITY_STRIDE(%a3),%a3                          | 011d8a lea 44(a3),a3
    dbf     %d7,.L11d74                                     | 011d8e

| ---- what the gunsight is sitting on, published for the seeker (0x11d92) -------------------------
    lea     A_entity_gunsight-FGB(%a5),%a3                  | 011d92
    lea     A_entity_collision_masks + COLLISION_ROW_BYTES*ENTITY_INDEX_TRAIL_DRONE-FGB(%a5),%a4 | 011d98 lea $1829e.l,a4
    tst.b   ENTITY_ALIVE(%a3)                               | 011d9e tst.b 14(a3)
    jbeq    .L11e28                                         | 011da2
    tst.b   A_boss_sequence_active-FGB(%a5)                 | 011da6
    jbeq    .L11dce                                         | 011dac
    moveq   #ENTITY_INDEX_TRAIL_DRONE,%d0                   | 011db0 moveq #$13,d0
    movem.l %a3-%a4,-(%sp)                                  | 011db2 movem.l #$0018,-(a7)
    jbsr    door_collision_chain_walk                       | 011db6 bsr.w $12d44
    movem.l (%sp)+,%a3-%a4                                  | 011dba movem.l (a7)+,#$1800
    jbeq    .L11dce                                         | 011dbe
    move.b  #ENEMY_SLOT_FIRST,A_seeker_lock_target_index-FGB(%a5) | 011dc2 move.b #$9,$19917.l
    jbra    .L11e2e                                         | 011dca
.L11dce:
    move.l  (%a4),%d1                                       | 011dce
    and.l   #GUNSIGHT_ENEMY_MASK,%d1                        | 011dd0 and.l #$1fe00,d1
    jbne    .L11de4                                         | 011dd6
    clr.b   A_seeker_lock_target_index-FGB(%a5)             | 011dda
    jbra    .L11e2e                                         | 011de0
.L11de4:
    lea     A_enemy_slots-FGB(%a5),%a2                      | 011de4
    move.w  #ENEMY_SLOT_COUNT - 1,%d6                       | 011dea move.w #$7,d6
    move.w  #ENEMY_SLOT_FIRST,%d5                           | 011dee move.w #$9,d5
.L11df2:
    move.l  (%a4),%d1                                       | 011df2
    tst.b   ENTITY_ALIVE(%a2)                               | 011df4 tst.b 14(a2)
    jbeq    .L11e14                                         | 011df8
    btst    %d5,%d1                                         | 011dfc
    jbeq    .L11e14                                         | 011dfe
    jbsr    door_entity_type_is_lockable                    | 011e02 bsr.w $13d3e
    jbeq    .L11e14                                         | 011e06
    move.b  %d5,A_seeker_lock_target_index-FGB(%a5)         | 011e0a
    jbra    .L11e2e                                         | 011e10
.L11e14:
    addq.w  #1,%d5                                          | 011e14
    lea     ENTITY_STRIDE(%a2),%a2                          | 011e16 lea 44(a2),a2
    dbf     %d6,.L11df2                                     | 011e1a
    clr.b   A_seeker_lock_target_index-FGB(%a5)             | 011e1e
    jbra    .L11e2e                                         | 011e24
.L11e28:
    clr.b   A_seeker_lock_target_index-FGB(%a5)             | 011e28

| ---- the ship's two records against their own overlap rows (0x11e2e) -----------------------------
.L11e2e:
    btst    #EXPLOSION_BIT_SHIP_DEATH,A_explosion_group_active_bits-FGB(%a5) | 011e2e btst #1,$19670.l
    jbne    .L11ed4                                         | 011e36
    lea     A_player_record-FGB(%a5),%a2                     | 011e3a
    lea     A_entity_collision_masks + COLLISION_ROW_BYTES*ENTITY_INDEX_SHIP-FGB(%a5),%a3 | 011e40 lea $18296.l,a3
    tst.b   ENTITY_PIXEL_HIT(%a2)                           | 011e46 tst.b 15(a2)
    jbeq    .L11e8c                                         | 011e4a
    move.l  (%a3),%d0                                       | 011e4e
    and.l   #SHIP_HIT_ENTITY_MASK,%d0                       | 011e50 and.l #$ffffffc0,d0
    jbne    .L11e84                                         | 011e56
    move.l  (%a3),%d0                                       | 011e5a
    and.l   #SHIP_HIT_OWN_SHOT_MASK,%d0                     | 011e5c and.l #$3f,d0
    jbne    .L11e8c                                         | 011e62
    tst.b   A_ship_invulnerable-FGB(%a5)                    | 011e66
    jbne    .L11ed4                                         | 011e6c
    bset    #DEATH_EVENT_BIT_SHIP,A_death_event_flags-FGB(%a5) | 011e70 bset #0,$198c4.l
    move.w  #SHIP_DEATH_EXPLOSION_GROUP,%d2                 | 011e78 move.w #$1,d2
    jbsr    door_explosion_spawn                            | 011e7c bsr.w $15510
    jbra    .L11ed4                                         | 011e80
.L11e84:
    jbsr    door_ship_resolve_entity_hits                   | 011e84 bsr.w $13cd4
    jbra    .L11ed4                                         | 011e88
.L11e8c:
    lea     COLLISION_ROW_BYTES(%a3),%a3                    | 011e8c lea 4(a3),a3
    tst.b   A_ship_record_shadow+ENTITY_PIXEL_HIT-FGB(%a5)  | 011e90 tst.b $17db5.l
    jbeq    .L11ed4                                         | 011e96
    move.l  (%a3),%d0                                       | 011e9a
    and.l   #SHIP_HIT_ENTITY_MASK,%d0                       | 011e9c and.l #$ffffffc0,d0
    jbne    .L11ed0                                         | 011ea2
    move.l  (%a3),%d0                                       | 011ea6
    and.l   #SHIP_HIT_OWN_SHOT_MASK,%d0                     | 011ea8 and.l #$3f,d0
    jbne    .L11ed4                                         | 011eae
    tst.b   A_ship_invulnerable-FGB(%a5)                    | 011eb2
    jbne    .L11ed4                                         | 011eb8
    bset    #DEATH_EVENT_BIT_SHIP,A_death_event_flags-FGB(%a5) | 011ebc bset #0,$198c4.l
    move.w  #SHIP_DEATH_EXPLOSION_GROUP,%d2                 | 011ec4 move.w #$1,d2
    jbsr    door_explosion_spawn                            | 011ec8 bsr.w $15510
    jbra    .L11ed4                                         | 011ecc
.L11ed0:
    jbsr    door_ship_resolve_entity_hits                   | 011ed0 bsr.w $13cd4

| ---- slots 0..5: resolve every player projectile that touched something (0x11ed4) ----------------
.L11ed4:
    move.w  #PLAYER_SHOT_SLOTS - 1,%d7                      | 011ed4 move.w #$5,d7
    lea     A_entity_collision_masks-FGB(%a5),%a0           | 011ed8
    lea     A_entity_table-FGB(%a5),%a1                     | 011ede
    moveq   #0,%d0                                          | 011ee4
.L11ee6:
    tst.b   ENTITY_ALIVE(%a1)                               | 011ee6 tst.b 14(a1)
    jbeq    .L11fd2                                         | 011eea
    cmpi.b  #SHOT_TYPE_PUFF,ENTITY_TYPE(%a1)                | 011eee cmpi.b #$37,17(a1)
    jbeq    .L11fd2                                         | 011ef4
    movem.l %d0-%d7/%a0-%a6,-(%sp)                          | 011ef8 movem.l #$fffe,-(a7)
    jbsr    door_collision_chain_walk                       | 011efc bsr.w $12d44
    movem.l (%sp)+,%d0-%d7/%a0-%a6                          | 011f00 movem.l (a7)+,#$7fff
    jbeq    .L11fd2                                         | 011f04
    tst.b   A_boss_sequence_active-FGB(%a5)                 | 011f08
    jbeq    .L11f94                                         | 011f0e
    cmpi.b  #SHOT_TYPE_BOMB,ENTITY_TYPE(%a1)                | 011f12 cmpi.b #$33,17(a1)
    jbne    .L11f26                                         | 011f18
    move.l  %a2,-(%sp)                                      | 011f1c
    movea.l %a1,%a2                                         | 011f1e
    jbsr    door_shot_retire_kind33                         | 011f20 bsr.w $155c2
    movea.l (%sp)+,%a2                                      | 011f24
.L11f26:
    moveq   #BOSS_HIT_SOUND,%d1                             | 011f26 moveq #$2c,d1
    jbsr    door_sound_start                                | 011f28 bsr.w $16ac8
    subi.w  #1,A_boss_hitpoints-FGB(%a5)                    | 011f2c subi.w #$1,$19f44.l
    jbne    .L11f94                                         | 011f34

| the boss's own death — its award does not reach the sound channel (0x11f38 pushes D0, 0x11f92 pops)
    move.l  %d0,-(%sp)                                      | 011f38
    lea     A_enemy_slots-FGB(%a5),%a2                      | 011f3a
    move.w  A_mothership_x-FGB(%a5),%d0                     | 011f40
    move.w  A_mothership_y-FGB(%a5),%d1                     | 011f46
    addi.w  #BOSS_DEATH_EXPLOSION_DX,%d0                    | 011f4c add.w #$50,d0
    addi.w  #BOSS_DEATH_EXPLOSION_DY,%d1                    | 011f50 add.w #$6,d1 — its carry out is the award's X
    move.w  %d0,ENTITY_X(%a2)                               | 011f54 move.w d0,0(a2)
    move.w  %d1,ENTITY_Y(%a2)                               | 011f58 move.w d1,4(a2)
    movem.l %d7/%a0-%a1,-(%sp)                              | 011f5c movem.l #$01c0,-(a7)
    lea     A_score_award_table_bcd + SCORE_BCD_BYTES*(SCORE_AWARD_BOSS + 1)-FGB(%a5),%a1 | 011f60 lea $195f4.l,a1
    jbsr    door_score_add_bcd                              | 011f66 bsr.w $12df6
    bset    #DEATH_EVENT_BOSS_BIT,A_death_event_flags-FGB(%a5) | 011f6a bset #1,$198c4.l
    clr.w   %d2                                             | 011f72
    jbsr    door_explosion_spawn                            | 011f74 bsr.w $15510
    lea     A_entity_boss_parts-FGB(%a5),%a2                | 011f78
    move.w  #MOTHERSHIP_TAIL_SEGMENTS - 1,%d7               | 011f7e move.w #$4,d7
.L11f82:
    clr.b   ENTITY_ALIVE(%a2)                               | 011f82 clr.b 14(a2)
    lea     ENTITY_STRIDE(%a2),%a2                          | 011f86 lea 44(a2),a2
    dbf     %d7,.L11f82                                     | 011f8a
    movem.l (%sp)+,%d7/%a0-%a1                              | 011f8e movem.l (a7)+,#$0380
    move.l  (%sp)+,%d0                                      | 011f92

| the projectile's own retirement, by type (0x11f94)
.L11f94:
    cmpi.b  #SHOT_TYPE_MISSILE,ENTITY_TYPE(%a1)             | 011f94 cmpi.b #$32,17(a1)
    jbne    .L11fa8                                         | 011f9a
    movea.l %a1,%a2                                         | 011f9e
    jbsr    door_shot_retire_kind32                         | 011fa0 bsr.w $15582
    jbra    .L11fd2                                         | 011fa4
.L11fa8:
    cmpi.b  #SHOT_TYPE_SEEKER,ENTITY_TYPE(%a1)              | 011fa8 cmpi.b #$36,17(a1)
    jbne    .L11fbc                                         | 011fae
    movea.l %a1,%a2                                         | 011fb2
    jbsr    door_shot_retire_kind36                         | 011fb4 bsr.w $155b4
    jbra    .L11fd2                                         | 011fb8
.L11fbc:
    cmpi.b  #BULLET_TYPE,ENTITY_TYPE(%a1)                   | 011fbc cmpi.b #$34,17(a1)
    jbne    .L11fd2                                         | 011fc2
    clr.b   ENTITY_ALIVE(%a1)                               | 011fc6 clr.b 14(a1)
    subi.b  #1,A_active_bullets-FGB(%a5)                    | 011fca subi.b #$1,$19909.l
.L11fd2:
    lea     ENTITY_STRIDE(%a1),%a1                          | 011fd2 lea 44(a1),a1
    addq.l  #1,%d0                                          | 011fd6
    lea     COLLISION_ROW_BYTES(%a0),%a0                    | 011fd8 lea 4(a0),a0
    dbf     %d7,.L11ee6                                     | 011fdc

| ---- 0x11fe0 .. 0x120c6: the SMALL/capsule explosion pass ----------------------------------------
| Runs on the frame where `A_explosion_phase_even` toggles to zero; walks the eight wave slots and
| steps every EXPLOSION_PART_TYPE record's animation on one frame.
    not.b   A_explosion_phase_even-FGB(%a5)         | 011fe0
    jbne    .L120c8                                 | 011fe6
    lea     A_enemy_slots-FGB(%a5),%a2              | 011fea
    moveq   #ENEMY_SLOT_FIRST,%d6                   | 011ff0
    move.w  #ENEMY_SLOT_COUNT-1,%d7                 | 011ff2
.L11ff6:
    cmpi.b  #EXPLOSION_PART_TYPE,ENTITY_TYPE(%a2)   | 011ff6
    jbne    .L120be                                 | 011ffc
    clr.w   %d1                                     | 012000
    move.b  ENTITY_ALIVE(%a2),%d1                   | 012002
    btst    #ALIVE_BIT_EXPLODING,%d1                | 012006
    jbeq    .L120be                                 | 01200a
    and.l   #EXPLOSION_FRAME_MASK,%d1               | 01200e
    addi.b  #1,%d1                                  | 012014 add.b #$1,d1 — the I-form so gas
                                                    | keeps the 4-byte immediate, not `addq`
    cmp.b   #EXPLOSION_LAST_FRAME,%d1               | 012018
    jbne    .L1209c                                 | 01201c
    cmpi.b  #EXPLOSION_NO_CREDIT_TAG,EXPLOSION_CREDIT_TAG_OFFSET(%a2)   | 012020
    jbeq    .L12092                                 | 012026
    move.b  ENTITY_SQUADRON(%a2),%d1                | 01202a
    and.l   #SQUADRON_ID_MASK,%d1                   | 01202e
    lea     A_squadron_kill_counters-FGB(%a5),%a0   | 012034
    adda.l  %d1,%a0                                 | 01203a
    subi.b  #1,(%a0)                                | 01203c
    jbne    .L12092                                 | 012040
    move.b  #TYPE_POWERUP_CAPSULE,ENTITY_TYPE(%a2)  | 012044
    move.b  #POWERUP_CAPSULE_SPAWN_TAG,ENTITY_ANIM_FRAME(%a2)   | 01204a
    move.w  #POWERUP_CAPSULE_ROWS,ENTITY_HEIGHT(%a2)            | 012050
    move.b  #1,ENTITY_ALIVE(%a2)                    | 012056
    move.l  #A_powerup_capsule_sprite,ENTITY_SPRITE(%a2)        | 01205c
    movem.l %a0-%a1,-(%sp)                          | 012064
    lea     A_score_award_table_bcd+2*SCORE_BCD_BYTES-FGB(%a5),%a1  | 012068
    jbsr    door_score_add_bcd                      | 01206e
    movem.l (%sp)+,%a0-%a1                          | 012072
    movem.l %d0-%d7/%a0-%a6,-(%sp)                  | 012076
    move.l  %d6,%d0                                 | 01207a
    jbsr    door_collision_chain_walk               | 01207c
    movem.l (%sp)+,%d0-%d7/%a0-%a6                  | 012080
    jbne    .L12092                                 | 012084
    moveq   #POWERUP_CAPSULE_SOUND,%d1              | 012088
    jbsr    door_sound_start                        | 01208a
    jbra    .L120be                                 | 01208e
.L12092:
    move.b  #0,ENTITY_ALIVE(%a2)                    | 012092
    jbra    .L120be                                 | 012098
.L1209c:
    bset    #ALIVE_BIT_EXPLODING,%d1                | 01209c
    move.b  %d1,ENTITY_ALIVE(%a2)                   | 0120a0
    and.l   #EXPLOSION_FRAME_MASK,%d1               | 0120a4
    subi.b  #1,%d1                                  | 0120aa sub.b #$1,d1 — I-form, see 0x12014
    lsl.w   #2,%d1                                  | 0120ae
    lea     A_explosion_small_frame_ptrs-FGB(%a5),%a0           | 0120b0
    movea.l (%a0,%d1.w),%a0                         | 0120b6
    move.l  %a0,ENTITY_SPRITE(%a2)                  | 0120ba
.L120be:
    lea     ENTITY_STRIDE(%a2),%a2                  | 0120be
    addq.l  #1,%d6                                  | 0120c2
    dbf     %d7,.L11ff6                             | 0120c4

| ---- 0x120c8 .. 0x121b0: the LARGE explosion pass ------------------------------------------------
| The same walk over the same eight slots for EXPLOSION_TYPE_LARGE records, gated on
| `A_explosion_phase_odd` instead. Four things differ from the pass above and nothing else does:
| the gate, the matched type, the frame table, and the two extra stores at 0x12122 / 0x1213a that
| give the capsule its large-variant animation frame and lift it three pixels as it spawns.
.L120c8:
    tst.b   A_explosion_phase_odd-FGB(%a5)          | 0120c8
    jbne    .L121b2                                 | 0120ce
    lea     A_enemy_slots-FGB(%a5),%a2              | 0120d2
    moveq   #ENEMY_SLOT_FIRST,%d6                   | 0120d8
    move.w  #ENEMY_SLOT_COUNT-1,%d7                 | 0120da
.L120de:
    cmpi.b  #EXPLOSION_TYPE_LARGE,ENTITY_TYPE(%a2)  | 0120de
    jbne    .L121a8                                 | 0120e4
    clr.w   %d1                                     | 0120e8
    move.b  ENTITY_ALIVE(%a2),%d1                   | 0120ea
    btst    #ALIVE_BIT_EXPLODING,%d1                | 0120ee
    jbeq    .L121a8                                 | 0120f2
    and.l   #EXPLOSION_FRAME_MASK,%d1               | 0120f6
    addi.b  #1,%d1                                  | 0120fc add.b #$1,d1 — I-form, see 0x12014
    cmp.b   #EXPLOSION_LAST_FRAME,%d1               | 012100
    jbne    .L12186                                 | 012104
    move.b  ENTITY_SQUADRON(%a2),%d1                | 012108
    and.l   #SQUADRON_ID_MASK,%d1                   | 01210c
    lea     A_squadron_kill_counters-FGB(%a5),%a0   | 012112
    adda.l  %d1,%a0                                 | 012118
    subi.b  #1,(%a0)                                | 01211a
    jbne    .L1217c                                 | 01211e
    move.b  #POWERUP_CAPSULE_LARGE_ANIM_FRAME,ACTOR_SPEED(%a2)  | 012122
    move.b  #TYPE_POWERUP_CAPSULE,ENTITY_TYPE(%a2)  | 012128
    move.b  #POWERUP_CAPSULE_SPAWN_TAG,ENTITY_ANIM_FRAME(%a2)   | 01212e
    move.w  #POWERUP_CAPSULE_ROWS,ENTITY_HEIGHT(%a2)            | 012134
    subi.w  #POWERUP_CAPSULE_LARGE_RISE,ENTITY_Y(%a2)           | 01213a
    move.b  #1,ENTITY_ALIVE(%a2)                    | 012140
    move.l  #A_powerup_capsule_sprite,ENTITY_SPRITE(%a2)        | 012146
    movem.l %a0-%a1,-(%sp)                          | 01214e
    lea     A_score_award_table_bcd+2*SCORE_BCD_BYTES-FGB(%a5),%a1  | 012152
    jbsr    door_score_add_bcd                      | 012158
    movem.l (%sp)+,%a0-%a1                          | 01215c
    movem.l %d0-%d7/%a0-%a6,-(%sp)                  | 012160
    move.l  %d6,%d0                                 | 012164
    jbsr    door_collision_chain_walk               | 012166
    movem.l (%sp)+,%d0-%d7/%a0-%a6                  | 01216a
    jbne    .L1217c                                 | 01216e
    moveq   #POWERUP_CAPSULE_SOUND,%d1              | 012172
    jbsr    door_sound_start                        | 012174
    jbra    .L121a8                                 | 012178
.L1217c:
    move.b  #0,ENTITY_ALIVE(%a2)                    | 01217c
    jbra    .L121a8                                 | 012182
.L12186:
    bset    #ALIVE_BIT_EXPLODING,%d1                | 012186
    move.b  %d1,ENTITY_ALIVE(%a2)                   | 01218a
    and.l   #EXPLOSION_FRAME_MASK,%d1               | 01218e
    subi.b  #1,%d1                                  | 012194 sub.b #$1,d1 — I-form, see 0x12014
    lsl.w   #2,%d1                                  | 012198
    lea     A_explosion_large_frame_ptrs-FGB(%a5),%a0           | 01219a
    movea.l (%a0,%d1.w),%a0                         | 0121a0
    move.l  %a0,ENTITY_SPRITE(%a2)                  | 0121a4
.L121a8:
    lea     ENTITY_STRIDE(%a2),%a2                  | 0121a8
    addq.l  #1,%d6                                  | 0121ac
    dbf     %d7,.L120de                             | 0121ae

.L121b2:
    btst    #EXPLOSION_BIT_SHIP_DEATH,A_explosion_group_active_bits-FGB(%a5) | 0121b2  the ship's own death explosion suppresses the whole ram sweep
    jbne    .L122f4                                           | 0121ba
    lea     A_enemy_slots-FGB(%a5),%a1                        | 0121be
    lea     A_entity_collision_masks+COLLISION_ROW_BYTES*ENEMY_SLOT_FIRST-FGB(%a5),%a0         | 0121c4  the row of enemy slot 9
    move.w  #ENEMY_SLOT_COUNT - 1,%d7                         | 0121ca
.L121ce:
    tst.b   ENTITY_ALIVE(%a1)                                 | 0121ce
    jbeq    .L122e8                                           | 0121d2
    cmpi.b  #TYPE_POWERUP_CAPSULE,ENTITY_TYPE(%a1)            | 0121d6
    jbeq    .L122e8                                           | 0121dc
    cmpi.b  #EXPLOSION_PART_TYPE,ENTITY_TYPE(%a1)             | 0121e0
    jbeq    .L122e8                                           | 0121e6
    move.l  (%a0),%d1                                         | 0121ea
    and.l   #SHIP_RECORD_MASK,%d1                             | 0121ec  gas spells this ANDI: same length, same cycles (sprite.S records it)
    jbeq    .L122e8                                           | 0121f2
    cmpi.b  #ENEMY_TYPE_BOSS_SEGMENT,ENTITY_TYPE(%a1)         | 0121f6
    jbne    .L1220c                                           | 0121fc
    move.l  %d7,-(%sp)                                        | 012200  the slot counter, across the callee
    jbsr    door_mothership_segment_hit                       | 012202
    move.l  (%sp)+,%d7                                        | 012206
    jbra    .L122e8                                           | 012208
.L1220c:
    cmpi.b  #ENEMY_TYPE_INVULNERABLE,ENTITY_TYPE(%a1)         | 01220c
    jbne    .L1221a                                           | 012212
    jbra    .L122e8                                           | 012216
.L1221a:
    cmpi.b  #ENEMY_TYPE_ARMOURED_A,ENTITY_TYPE(%a1)           | 01221a
    jbeq    .L1222e                                           | 012220
    cmpi.b  #ENEMY_TYPE_ARMOURED_B,ENTITY_TYPE(%a1)           | 012224
    jbne    .L1223c                                           | 01222a
.L1222e:
    moveq   #ENEMY_HIT_SOUND,%d1                              | 01222e  the ram pass plays a tune here; the shoot pass at 0x1239c does not
    jbsr    door_sound_start                                  | 012230
    subq.b  #1,ENTITY_HP(%a1)                                 | 012234  BORROWS at 0 - the X the next abcd adds
    jbne    .L122e8                                           | 012238
.L1223c:
    cmpi.b  #ENEMY_TYPE_BIG,ENTITY_TYPE(%a1)                  | 01223c
    jbne    .L12284                                           | 012242
    move.b  #ENEMY_EXPLODING_ALIVE,%d2                        | 012246
    move.b  %d2,ENTITY_ALIVE(%a1)                             | 01224a
    move.b  #EXPLOSION_TYPE_LARGE,ENTITY_TYPE(%a1)            | 01224e
    move.l  #A_explosion_large_sprite,ENTITY_SPRITE(%a1)      | 012254  an image OFFSET, as the record stores it
    move.w  #ENEMY_EXPLOSION_ROWS_LARGE,ENTITY_HEIGHT(%a1)    | 01225c
    andi.w  #EXPLOSION_X_ALIGN,ENTITY_X(%a1)                  | 012262
    movem.l %a0-%a1,-(%sp)                                    | 012268  movem.l #$00c0,-(a7) - A0/A1 only
    lea     A_score_award_table_bcd+1*SCORE_BCD_BYTES-FGB(%a5),%a1 | 01226c
    jbsr    door_score_add_bcd                                | 012272
    movem.l (%sp)+,%a0-%a1                                    | 012276  movem.l (a7)+,#$0300
    moveq   #ENEMY_HIT_SOUND,%d1                              | 01227a
    jbsr    door_sound_start                                  | 01227c
    jbra    .L122e8                                           | 012280
.L12284:
    cmpi.b  #ENEMY_TYPE_SMALL_A,ENTITY_TYPE(%a1)              | 012284
    jbeq    .L122ac                                           | 01228a
    cmpi.b  #ENEMY_TYPE_SMALL_B,ENTITY_TYPE(%a1)              | 01228e
    jbeq    .L122ac                                           | 012294
    cmpi.b  #ENEMY_TYPE_ARMOURED_A,ENTITY_TYPE(%a1)           | 012298
    jbeq    .L122ac                                           | 01229e
    cmpi.b  #ENEMY_TYPE_ARMOURED_B,ENTITY_TYPE(%a1)           | 0122a2
    jbne    .L122e8                                           | 0122a8
.L122ac:
    move.b  #ENEMY_EXPLODING_ALIVE,%d2                        | 0122ac
    move.b  %d2,ENTITY_ALIVE(%a1)                             | 0122b0
    move.b  #EXPLOSION_PART_TYPE,ENTITY_TYPE(%a1)             | 0122b4
    move.l  #A_mothership_explosion_sprite,ENTITY_SPRITE(%a1) | 0122ba
    move.w  #ENEMY_EXPLOSION_ROWS,BUS_ERROR_VECTOR(%a6)       | 0122c2  THE ORIGINAL'S DEFECT, transcribed: move.w #$10,$8.l puts the row count
    andi.w  #EXPLOSION_X_ALIGN,ENTITY_X(%a1)                  | 0122ca  in the bus-error vector, not in the record.  %a6 = below the FGB window
    movem.l %a0-%a1,-(%sp)                                    | 0122d0
    lea     A_score_award_table_bcd+2*SCORE_BCD_BYTES-FGB(%a5),%a1 | 0122d4
    jbsr    door_score_add_bcd                                | 0122da
    movem.l (%sp)+,%a0-%a1                                    | 0122de
    moveq   #ENEMY_HIT_SOUND,%d1                              | 0122e2
    jbsr    door_sound_start                                  | 0122e4
.L122e8:
    lea     ENTITY_STRIDE(%a1),%a1                            | 0122e8
    lea     COLLISION_ROW_BYTES(%a0),%a0                      | 0122ec
    dbf     %d7,.L121ce                                       | 0122f0
.L122f4:
    lea     A_entity_table-FGB(%a5),%a2                       | 0122f4  the 6 x 8 shot x enemy sweep starts here
    move.l  #1,%d0                                            | 0122fa  D0 = the shot's bit, the sound channel, and what an award overwrites
    move.w  #PLAYER_SHOT_SLOTS - 1,%d6                        | 012300
.L12304:
    tst.b   ENTITY_ALIVE(%a2)                                 | 012304
    jbeq    .L12474                                           | 012308
    lea     A_enemy_slots-FGB(%a5),%a1                        | 01230c
    lea     A_entity_collision_masks+COLLISION_ROW_BYTES*ENEMY_SLOT_FIRST-FGB(%a5),%a0         | 012312
    move.w  #ENEMY_SLOT_COUNT - 1,%d7                         | 012318
.L1231c:
    tst.b   ENTITY_ALIVE(%a2)                                 | 01231c  re-tested: the arms below can retire the shot mid-walk
    jbeq    .L12474                                           | 012320
    cmpi.b  #EXPLOSION_PART_TYPE,ENTITY_TYPE(%a2)             | 012324
    jbeq    .L12474                                           | 01232a
    move.b  ENTITY_ALIVE(%a1),%d1                             | 01232e
    jbeq    .L1245e                                           | 012332
    btst    #ALIVE_BIT_EXPLODING,%d1                          | 012336
    jbne    .L1245e                                           | 01233a
    cmpi.b  #TYPE_POWERUP_CAPSULE,ENTITY_TYPE(%a1)            | 01233e
    jbeq    .L1245e                                           | 012344
    cmpi.b  #EXPLOSION_PART_TYPE,ENTITY_TYPE(%a1)             | 012348
    jbeq    .L1245e                                           | 01234e
    move.l  (%a0),%d1                                         | 012352
    and.l   %d0,%d1                                           | 012354
    jbeq    .L1245e                                           | 012356
    cmpi.b  #ENEMY_TYPE_BOSS_SEGMENT,ENTITY_TYPE(%a1)         | 01235a
    jbne    .L1237a                                           | 012360
    jbsr    door_mothership_segment_hit                       | 012364
    cmpi.b  #SHOT_TYPE_MISSILE,ENTITY_TYPE(%a2)               | 012368
    jbne    .L1241e                                           | 01236e  skips the missile test at 0x12414 - this arm has just made it
    jbsr    door_shot_retire_kind32                           | 012372
    jbra    .L1246e                                           | 012376
.L1237a:
    cmpi.b  #ENEMY_TYPE_INVULNERABLE,ENTITY_TYPE(%a1)         | 01237a
    jbne    .L12388                                           | 012380
    jbra    .L12414                                           | 012384
.L12388:
    cmpi.b  #ENEMY_TYPE_ARMOURED_A,ENTITY_TYPE(%a1)           | 012388
    jbeq    .L1239c                                           | 01238e
    cmpi.b  #ENEMY_TYPE_ARMOURED_B,ENTITY_TYPE(%a1)           | 012392
    jbne    .L123a4                                           | 012398
.L1239c:
    subq.b  #1,ENTITY_HP(%a1)                                 | 01239c  no tune on this side - the one difference from 0x1222e
    jbne    .L12414                                           | 0123a0
.L123a4:
    move.b  #ENEMY_EXPLODING_ALIVE,%d2                        | 0123a4
    move.b  %d2,ENTITY_ALIVE(%a1)                             | 0123a8
    cmpi.b  #ENEMY_TYPE_BIG,ENTITY_TYPE(%a1)                  | 0123ac
    jbne    .L123e6                                           | 0123b2
    move.b  #EXPLOSION_TYPE_LARGE,ENTITY_TYPE(%a1)            | 0123b6
    move.l  #A_explosion_large_sprite,ENTITY_SPRITE(%a1)      | 0123bc
    move.w  #ENEMY_EXPLOSION_ROWS_LARGE,ENTITY_HEIGHT(%a1)    | 0123c4
    andi.w  #EXPLOSION_X_ALIGN,ENTITY_X(%a1)                  | 0123ca
    movem.l %a0-%a1,-(%sp)                                    | 0123d0
    lea     A_score_award_table_bcd+1*SCORE_BCD_BYTES-FGB(%a5),%a1 | 0123d4
    jbsr    door_score_add_bcd                                | 0123da
    movem.l (%sp)+,%a0-%a1                                    | 0123de
    jbra    .L12414                                           | 0123e2
.L123e6:
    move.b  #EXPLOSION_PART_TYPE,ENTITY_TYPE(%a1)             | 0123e6
    move.l  #A_mothership_explosion_sprite,ENTITY_SPRITE(%a1) | 0123ec
    move.w  #ENEMY_EXPLOSION_ROWS,BUS_ERROR_VECTOR(%a6)       | 0123f4  the same defect again - see 0x122c2
    andi.w  #EXPLOSION_X_ALIGN,ENTITY_X(%a1)                  | 0123fc
    movem.l %a0-%a1,-(%sp)                                    | 012402
    lea     A_score_award_table_bcd+2*SCORE_BCD_BYTES-FGB(%a5),%a1 | 012406
    jbsr    door_score_add_bcd                                | 01240c
    movem.l (%sp)+,%a0-%a1                                    | 012410
.L12414:
    cmpi.b  #SHOT_TYPE_MISSILE,ENTITY_TYPE(%a2)               | 012414  a missile neither retires nor walks on
    jbeq    .L1246e                                           | 01241a
.L1241e:
    cmpi.b  #SHOT_TYPE_BOMB,ENTITY_TYPE(%a2)                  | 01241e
    jbne    .L12430                                           | 012424
    jbsr    door_shot_retire_kind33                           | 012428
    jbra    .L1246e                                           | 01242c
.L12430:
    cmpi.b  #SHOT_TYPE_SEEKER,ENTITY_TYPE(%a2)                | 012430
    jbne    .L12442                                           | 012436
    jbsr    door_shot_retire_kind36                           | 01243a
    jbra    .L1246e                                           | 01243e
.L12442:
    cmpi.b  #BULLET_TYPE,ENTITY_TYPE(%a2)                     | 012442
    jbne    .L1245e                                           | 012448
    subi.b  #1,A_active_bullets-FGB(%a5)                      | 01244c  sets X, but the tune two on overwrites it
    clr.b   ENTITY_ALIVE(%a2)                                 | 012454
    moveq   #ENEMY_HIT_SOUND,%d1                              | 012458
    jbsr    door_sound_start                                  | 01245a
.L1245e:
    lea     COLLISION_ROW_BYTES(%a0),%a0                      | 01245e
    lea     ENTITY_STRIDE(%a1),%a1                            | 012462
    dbf     %d7,.L1231c                                       | 012466
    jbra    .L12474                                           | 01246a
.L1246e:
    moveq   #ENEMY_HIT_SOUND,%d1                              | 01246e
    jbsr    door_sound_start                                  | 012470

| ---- 0x12474 .. 0x1247c: the collision matrix's outer loop closes -------------------------------
| The tail of the sweep whose body the previous band holds: the row mask walks one bit left, the
| cursor steps one entity record on, and the `dbf` goes back to the row head at 0x12304.
.L12474:
        lsl.l   #1,%d0                                  | 012474
        lea     ENTITY_STRIDE(%a2),%a2                  | 012476  lea 44(a2),a2
        dbf     %d6,.L12304                             | 01247a

| ---- 0x1247e .. 0x124d8: frame_enemy_shots_ground -----------------------------------------------
| The three enemy-shot slots are 6, 7 and 8, so the collision-matrix cursor starts on row 6 and
| steps one row (COLLISION_ROW_BYTES) per slot alongside the record cursor.
        lea     A_enemy_shot_slots-FGB(%a5),%a2         | 01247e  lea $17b96.l,a2
        lea     A_entity_collision_masks+COLLISION_ROW_BYTES*ENEMY_SHOT_SLOT_FIRST-FGB(%a5),%a0 | 012484  lea $1826a.l,a0 (row of slot 6)
        move.w  #ENEMY_SHOT_SLOT_COUNT-1,%d7            | 01248a  move.w #$2,d7
.L1248e:
        tst.b   ENTITY_ALIVE(%a2)                       | 01248e  tst.b 14(a2)
        jbeq    .L124ce                                 | 012492
        tst.b   ENTITY_PIXEL_HIT(%a2)                   | 012496  tst.b 15(a2)
        jbeq    .L124ce                                 | 01249a
        tst.l   (%a0)                                   | 01249e
        jbne    .L124ce                                 | 0124a0
        tst.b   A_boss_sequence_active-FGB(%a5)         | 0124a4  tst.b $19aad.l
        jbne    .L124ce                                 | 0124aa
        cmpi.b  #GROUND_ABSORB_TYPE_SEEKER,ENTITY_TYPE(%a2) | 0124ae  cmpi.b #$b,17(a2)
        jbne    .L124c0                                 | 0124b4
        jbsr    door_enemy_morph_to_type6               | 0124b8  bsr.w $13ad0
        jbra    .L124ce                                 | 0124bc
.L124c0:
        cmpi.b  #GROUND_ABSORB_TYPE_AIMED,ENTITY_TYPE(%a2) | 0124c0  cmpi.b #$c,17(a2)
        jbne    .L124ce                                 | 0124c6
        clr.b   ENTITY_ALIVE(%a2)                       | 0124ca  clr.b 14(a2)
.L124ce:
        lea     ENTITY_STRIDE(%a2),%a2                  | 0124ce  lea 44(a2),a2
        lea     COLLISION_ROW_BYTES(%a0),%a0            | 0124d2  lea 4(a0),a0
        dbf     %d7,.L1248e                             | 0124d6

| ---- 0x124da .. 0x12530: starfield layer 1 ------------------------------------------------------
| a1 is the ONE walking cursor the three layers share, so layer 2 picks it up where this leaves it.
| Layer 1 draws into plane 0 only and always moves its stars: it has neither the `or.w d3,4(a0)` of
| layers 2 and 3 nor their phase test, so its `bne` skip target is the `subi.w` itself.
        lea     A_starfield_table-FGB(%a5),%a1          | 0124da  lea $179fa.l,a1
        moveq   #STARFIELD_STARS-1,%d2                  | 0124e0  moveq #$5,d2
.L124e2:
        move.w  (%a1)+,%d0                              | 0124e2  the star's screen offset
        move.w  (%a1),%d1                               | 0124e4  ...and its x
        jbmi    .L1252a                                 | 0124e6  x < 0: respawn at the right edge
        and.w   #STARFIELD_X_PIXEL_MASK,%d1             | 0124ea  and.w #$f,d1
        add.w   %d1,%d1                                 | 0124ee
        lea     A_starfield_pixel_masks-FGB(%a5),%a2    | 0124f0  lea $17a42.l,a2
        adda.w  %d1,%a2                                 | 0124f6
        move.w  (%a2),%d3                               | 0124f8  the one-pixel mask
        move.w  (%a1),%d1                               | 0124fa
        and.w   #STARFIELD_X_CELL_MASK,%d1              | 0124fc  and.w #$fff0,d1
        lsr.w   #1,%d1                                  | 012500
        add.w   %d1,%d0                                 | 012502
        movea.l A_screen_back-FGB(%a5),%a0              | 012504  movea.l $1797e.l,a0
        adda.l  %a6,%a0                                 | SUBSTITUTION: the image holds an OFFSET
        adda.w  %d0,%a0                                 | 01250a
        movem.w (%a0),%d4-%d7                           | 01250c  movem.w (a0),#$00f0
        or.w    %d4,%d5                                 | 012510
        or.w    %d5,%d6                                 | 012512
        or.w    %d6,%d7                                 | 012514
        and.w   %d3,%d7                                 | 012516  drawn only where all four planes are clear
        jbne    .L1251e                                 | 012518
        or.w    %d3,(%a0)                               | 01251c  layer 1: plane 0 only
.L1251e:
        subi.w  #1,(%a1)+                               | 01251e  layer 1 moves every frame
        dbf     %d2,.L124e2                             | 012522
        jbra    .L12532                                 | 012526
.L1252a:
        move.w  #STARFIELD_RESPAWN_X,(%a1)+             | 01252a  move.w #$13f,(a1)+
        dbf     %d2,.L124e2                             | 01252e

| ---- 0x12532 .. 0x1259c: starfield layer 2 ------------------------------------------------------
| Layer 2 draws into BOTH plane 0 and plane 2, and moves only while A_starfield_layer2_phase is
| zero; on the other phase it steps the cursor past the x word with a `lea` instead of decrementing.
.L12532:
        moveq   #STARFIELD_STARS-1,%d2                  | 012532  moveq #$5,d2
.L12534:
        move.w  (%a1)+,%d0                              | 012534
        move.w  (%a1),%d1                               | 012536
        jbmi    .L12596                                 | 012538
        and.w   #STARFIELD_X_PIXEL_MASK,%d1             | 01253c  and.w #$f,d1
        add.w   %d1,%d1                                 | 012540
        lea     A_starfield_pixel_masks-FGB(%a5),%a2    | 012542  lea $17a42.l,a2
        adda.w  %d1,%a2                                 | 012548
        move.w  (%a2),%d3                               | 01254a
        move.w  (%a1),%d1                               | 01254c
        and.w   #STARFIELD_X_CELL_MASK,%d1              | 01254e  and.w #$fff0,d1
        lsr.w   #1,%d1                                  | 012552
        add.w   %d1,%d0                                 | 012554
        movea.l A_screen_back-FGB(%a5),%a0              | 012556  movea.l $1797e.l,a0
        adda.l  %a6,%a0                                 | SUBSTITUTION: the image holds an OFFSET
        adda.w  %d0,%a0                                 | 01255c
        movem.w (%a0),%d4-%d7                           | 01255e  movem.w (a0),#$00f0
        or.w    %d4,%d5                                 | 012562
        or.w    %d5,%d6                                 | 012564
        or.w    %d6,%d7                                 | 012566
        and.w   %d3,%d7                                 | 012568
        jbne    .L12574                                 | 01256a
        or.w    %d3,(%a0)                               | 01256e  layer 2: plane 0...
        or.w    %d3,STARFIELD_PLANE2_OFFSET(%a0)        | 012570  ...and plane 2
.L12574:
        tst.b   A_starfield_layer2_phase-FGB(%a5)       | 012574  tst.b $198a9.l
        jbne    .L1258a                                 | 01257a
        subi.w  #1,(%a1)+                               | 01257e
        dbf     %d2,.L12534                             | 012582
        jbra    .L1259e                                 | 012586
.L1258a:
        lea     2(%a1),%a1                              | 01258a  standing still: just past the x word
        dbf     %d2,.L12534                             | 01258e
        jbra    .L1259e                                 | 012592
.L12596:
        move.w  #STARFIELD_RESPAWN_X,(%a1)+             | 012596  move.w #$13f,(a1)+
        dbf     %d2,.L12534                             | 01259a

| ---- 0x1259e .. 0x12606: starfield layer 3 ------------------------------------------------------
| Layer 3 draws into plane 2 ONLY — no `or.w d3,(a0)` — and gates its move on the layer-3 countdown
| rather than on the layer-2 phase byte.
.L1259e:
        moveq   #STARFIELD_STARS-1,%d2                  | 01259e  moveq #$5,d2
.L125a0:
        move.w  (%a1)+,%d0                              | 0125a0
        move.w  (%a1),%d1                               | 0125a2
        jbmi    .L12600                                 | 0125a4
        and.w   #STARFIELD_X_PIXEL_MASK,%d1             | 0125a8  and.w #$f,d1
        add.w   %d1,%d1                                 | 0125ac
        lea     A_starfield_pixel_masks-FGB(%a5),%a2    | 0125ae  lea $17a42.l,a2
        adda.w  %d1,%a2                                 | 0125b4
        move.w  (%a2),%d3                               | 0125b6
        move.w  (%a1),%d1                               | 0125b8
        and.w   #STARFIELD_X_CELL_MASK,%d1              | 0125ba  and.w #$fff0,d1
        lsr.w   #1,%d1                                  | 0125be
        add.w   %d1,%d0                                 | 0125c0
        movea.l A_screen_back-FGB(%a5),%a0              | 0125c2  movea.l $1797e.l,a0
        adda.l  %a6,%a0                                 | SUBSTITUTION: the image holds an OFFSET
        adda.w  %d0,%a0                                 | 0125c8
        movem.w (%a0),%d4-%d7                           | 0125ca  movem.w (a0),#$00f0
        or.w    %d4,%d5                                 | 0125ce
        or.w    %d5,%d6                                 | 0125d0
        or.w    %d6,%d7                                 | 0125d2
        and.w   %d3,%d7                                 | 0125d4
        jbne    .L125de                                 | 0125d6
        or.w    %d3,STARFIELD_PLANE2_OFFSET(%a0)        | 0125da  layer 3: plane 2 only
.L125de:
        tst.b   A_starfield_layer3_countdown-FGB(%a5)   | 0125de  tst.b $198aa.l
        jbne    .L125f4                                 | 0125e4
        subi.w  #1,(%a1)+                               | 0125e8
        dbf     %d2,.L125a0                             | 0125ec
        jbra    .L12608                                 | 0125f0
.L125f4:
        lea     2(%a1),%a1                              | 0125f4  standing still: just past the x word
        dbf     %d2,.L125a0                             | 0125f8
        jbra    .L12608                                 | 0125fc
.L12600:
        move.w  #STARFIELD_RESPAWN_X,(%a1)+             | 012600  move.w #$13f,(a1)+
        dbf     %d2,.L125a0                             | 012604

| ---- 0x12608 .. 0x1261e: the two starfield phase counters ---------------------------------------
.L12608:
        subq.b  #1,A_starfield_layer3_countdown-FGB(%a5) | 012608  subq.b #1,$198aa.l
        jbpl    .L1261a                                 | 01260e
        move.b  #STARFIELD_LAYER3_PERIOD,A_starfield_layer3_countdown-FGB(%a5) | 012612  move.b #$3,$198aa.l
.L1261a:
        not.b   A_starfield_layer2_phase-FGB(%a5)       | 01261a  not.b $198a9.l

| ---- 0x12620 .. 0x12654: the shield decays, and mirrors itself into the HUD gauge ---------------
        subi.w  #1,A_shield_decay_timer-FGB(%a5)        | 012620  subi.w #$1,$19dca.l
        jbne    .L12656                                 | 012628
        move.w  #POWERUP_DECAY_TICKS,A_shield_decay_timer-FGB(%a5) | 01262c  move.w #$3e8,$19dca.l
        move.b  A_shield_level-FGB(%a5),%d0             | 012634  move.b $1990a.l,d0
        jbeq    .L12656                                 | 01263a  floor 0: nothing left to give back
        sub.b   #1,%d0                                  | 01263e
        move.b  %d0,A_power_gauge_display-FGB(%a5)      | 012642  move.b d0,$198c3.l
        bset    #PANEL_REDRAW_GAUGE_BIT,A_panel_redraw_mask-FGB(%a5) | 012648  bset #2,$19904.l
        move.b  %d0,A_shield_level-FGB(%a5)             | 012650  move.b d0,$1990a.l

| ---- 0x12656 .. 0x12680: the weapon power decays, floored at WEAPON_POWER_LEVEL_MIN -------------
.L12656:
        subi.w  #1,A_weapon_decay_timer-FGB(%a5)        | 012656  subi.w #$1,$19dcc.l
        jbne    .L12682                                 | 01265e
        move.w  #POWERUP_DECAY_TICKS,A_weapon_decay_timer-FGB(%a5) | 012662  move.w #$3e8,$19dcc.l
        move.b  A_weapon_power_level-FGB(%a5),%d0       | 01266a  move.b $19908.l,d0
        cmp.b   #WEAPON_POWER_LEVEL_MIN,%d0             | 012670  cmp.b #$2,d0
        jbeq    .L12682                                 | 012674
        sub.b   #1,%d0                                  | 012678
        move.b  %d0,A_weapon_power_level-FGB(%a5)       | 01267c  move.b d0,$19908.l

| ---- 0x12682 .. 0x126a8: the ship speed decays, floored at 0 ------------------------------------
.L12682:
        subi.w  #1,A_speed_decay_timer-FGB(%a5)         | 012682  subi.w #$1,$19dc8.l
        jbne    .L126aa                                 | 01268a
        move.w  #POWERUP_DECAY_TICKS,A_speed_decay_timer-FGB(%a5) | 01268e  move.w #$3e8,$19dc8.l
        move.b  A_ship_speed_level-FGB(%a5),%d0         | 012696  move.b $19907.l,d0
        jbeq    .L126aa                                 | 01269c
        sub.b   #1,%d0                                  | 0126a0
        move.b  %d0,A_ship_speed_level-FGB(%a5)         | 0126a4  move.b d0,$19907.l

| ---- 0x126aa .. 0x126ec: frame_scroll_step ------------------------------------------------------
| One 2-pixel step of the scroller, then the page counter round its ring of MAP_PAGES and, on its
| wrap, the column phase round its ring of SCROLL_PHASES.
.L126aa:
        addi.l  #1,A_scroll_pos-FGB(%a5)                | 0126aa  addi.l #$1,$195cc.l
        tst.b   A_scroll_frozen-FGB(%a5)                | 0126b4  tst.b $198b1.l
        jbne    .L126ee                                 | 0126ba
        addq.b  #1,A_map_page-FGB(%a5)                  | 0126be  addq.b #1,$198a5.l
        cmpi.b  #MAP_PAGES,A_map_page-FGB(%a5)          | 0126c4  cmpi.b #$8,$198a5.l
        jbne    .L126ee                                 | 0126cc
        clr.b   A_map_page-FGB(%a5)                     | 0126d0  clr.b $198a5.l
        addq.b  #1,A_map_column-FGB(%a5)                | 0126d6  addq.b #1,$198a6.l
        cmpi.b  #SCROLL_PHASES,A_map_column-FGB(%a5)    | 0126dc  cmpi.b #$14,$198a6.l
        jbne    .L126ee                                 | 0126e4
        clr.b   A_map_column-FGB(%a5)                   | 0126e8  clr.b $198a6.l

| ---- band 5: the frame end, the two-player swap and the section-end tests -------------------
|
| THREE SEAMS IN THIS BAND SPLIT BY BUILD, and they are the only three in the whole twin. The
| original busy-waits on two bytes an interrupt writes and pokes the MFP's interrupt-enable
| directly. ON TARGET all three are the original's own instructions, because on the real machine the
| interrupt really does write the byte and the register really is at $fffa09 — which is exactly what
| ../../../../tools/recreate_kit/include/sched.h says of itself ("ON TARGET this file IS EXCLUDED
| FROM THE BUILD ... a build for the real machine spins on the address itself"), and the target's own
| sched.h/hw.h supply `static inline` versions with no linkable symbol at all.
|
| OFF TARGET they go through the kit, because nothing in a differential can move those bytes: two
| `sched_wait8` calls, whose polls the harness counts against the oracle's arrivals, and one
| `hw_bset8`, whose write the hardware ledger compares. The twin must make the SAME calls in the
| SAME order as ../frame.c or both ledgers differ.
|
| AND OFF TARGET THE CAP IS A CONTROL-FLOW EDGE THE ORIGINAL DOES NOT HAVE. `sched_wait8` answers 0
| when its poll cap is exhausted and `frame_end_and_flip` RETURNS on that, skipping the flip, the
| IKBD command and the `bset`; so each wait is followed by a `tst.l`/`jbeq` to 0x1271c. On target
| there is no cap and no branch — which is why both are inside the `#ifdef` rather than left in as
| a pair of never-taken tests.

.L126ee:
#ifdef ZY_ASM_FRAME_DOOR
        jbsr    door_sched_wait_raster                  |         the kit's counted, capped wait
        tst.l   %d0
        jbeq    .L1271c                                 |         cap exhausted -> no flip
#else
        cmpi.b  #FRAME_RASTER_PHASE_READY,A_raster_phase-FGB(%a5)       | 0126ee
        jbne    .L126ee                                 | 0126f6
#endif
        jbsr    door_screen_flip_buffers                | 0126f8
        move.b  #IKBD_CMD_INTERROGATE_JOYSTICK,%d0      | 0126fc
        jbsr    door_ikbd_send_cmd                      | 012700
        move.b  #FRAME_VBL_WAIT_ARMED,A_vbl_wait_flag-FGB(%a5)  | 012704
.L1270c:
#ifdef ZY_ASM_FRAME_DOOR
        jbsr    door_sched_wait_vbl                     |         the kit's counted, capped wait
        tst.l   %d0
        jbeq    .L1271c                                 |         cap exhausted -> no bset
        jbsr    door_hw_bset_ierb                       |         ...and the ledgered `bset`
#else
        tst.b   A_vbl_wait_flag-FGB(%a5)                | 01270c
        jbne    .L1270c                                 | 012712
        bset    #MFP_ACIA_CHANNEL_BIT,(HW_MFP_IERB).l   | 012714
#endif
.L1271c:
        tst.b   A_explosion_group_active_bits-FGB(%a5)  | 01271c
        jbeq    .L1285e                                 | 012722
        clr.l   %d3                                     | 012726
        move.w  #1,%d1                                  | 012728
.L1272c:
        btst    %d1,A_explosion_group_active_bits-FGB(%a5)      | 01272c
        jbeq    .L1276a                                 | 012732
        move.w  %d1,%d0                                 | 012736
        ext.w   %d0                                     | 012738
        mulu.w  #EXPLOSION_GROUP_MEMBERS,%d0            | 01273a
        lea     A_explosion_group_members-FGB(%a5),%a4  | 01273e
        adda.l  %d0,%a4                                 | 012744
        move.w  #EXPLOSION_GROUP_MEMBERS-1,%d7          | 012746
.L1274a:
        lea     A_entity_table-FGB(%a5),%a2             | 01274a
        move.b  (%a4)+,%d2                              | 012750
        ext.w   %d2                                     | 012752
        mulu.w  #ENTITY_STRIDE,%d2                      | 012754
        adda.l  %d2,%a2                                 | 012758
        cmpi.b  #EXPLOSION_DONE_FRAME,EXPLOSION_PART_FRAME(%a2)  | 01275a
        jbne    .L1276a                                 | 012760
        dbf     %d7,.L1274a                             | 012764
        bset    %d1,%d3                                 | 012768
.L1276a:
        dbf     %d1,.L1272c                             | 01276a
        btst    #EXPLOSION_BIT_SHIP_DEATH,%d3           | 01276e
        jbeq    .L12846                                 | 012772
        jbsr    door_powerup_downgrade_on_death         | 012776
        subi.b  #1,A_lives-FGB(%a5)                     | 01277a
        jbne    .L1278a                                 | 012782
        jbsr    door_game_over_screen                   | 012786
.L1278a:
        move.b  A_level_section-FGB(%a5),A_dying_player_section_index-FGB(%a5)  | 01278a
        clr.b   %d7                                     | 012794
.L12796:
        lea     A_player_records-FGB(%a5),%a0           | 012796
        move.b  A_current_player_index-FGB(%a5),%d0     | 01279c
        ext.w   %d0                                     | 0127a2
        mulu.w  #PLAYER_RECORD_BYTES,%d0                | 0127a4
        adda.w  %d0,%a0                                 | 0127a8
        move.l  A_player_score_bcd-FGB(%a5),(%a0)+      | 0127aa
        move.b  A_lives-FGB(%a5),(%a0)+                 | 0127b0
        move.b  A_level_section-FGB(%a5),(%a0)+         | 0127b6
        move.l  A_map_ptr-FGB(%a5),(%a0)+               | 0127bc
        move.b  A_powerup_cursor-FGB(%a5),(%a0)+        | 0127c2
        move.b  A_weapon_power_level-FGB(%a5),(%a0)+    | 0127c8
        move.b  A_ship_speed_level-FGB(%a5),(%a0)+      | 0127ce
        clr.b   (%a0)+                                  | 0127d4
        eori.b  #1,A_current_player_index-FGB(%a5)      | 0127d6
        lea     A_player_records-FGB(%a5),%a0           | 0127de
        move.b  A_current_player_index-FGB(%a5),%d0     | 0127e4
        ext.w   %d0                                     | 0127ea
        mulu.w  #PLAYER_RECORD_BYTES,%d0                | 0127ec
        adda.w  %d0,%a0                                 | 0127f0
        move.l  (%a0)+,A_player_score_bcd-FGB(%a5)      | 0127f2
        move.b  (%a0)+,A_lives-FGB(%a5)                 | 0127f8
        move.b  (%a0)+,A_level_section-FGB(%a5)         | 0127fe
        move.l  (%a0)+,A_map_ptr-FGB(%a5)               | 012804
        move.b  (%a0)+,A_powerup_cursor-FGB(%a5)        | 01280a
        move.b  (%a0)+,A_weapon_power_level-FGB(%a5)    | 012810
        move.b  (%a0)+,A_ship_speed_level-FGB(%a5)      | 012816
        add.b   #1,%d7                                  | 01281c
        cmp.b   #PLAYER_SWAP_ATTEMPTS,%d7               | 012820
        jbeq    .Lexit_title                            | 012824  -> 0x10500
        tst.b   A_lives-FGB(%a5)                        | 012828
        jbeq    .L12796                                 | 01282e
        move.b  A_level_section-FGB(%a5),%d0            | 012832
        cmp.b   A_dying_player_section_index-FGB(%a5),%d0       | 012838
        jbne    .Lexit_reload_section                   | 01283e  -> 0x1083a
        jbra    .Lexit_restart_section                  | 012842  -> 0x10b6e
.L12846:
        btst    #EXPLOSION_BIT_SECTION_END,%d3          | 012846
        jbeq    .L1285e                                 | 01284a
        subi.b  #1,A_section_end_delay_counter-FGB(%a5) | 01284e
        jbeq    .Lexit_advance_section                  | 012856  -> 0x10814
        jbra    .L12958                                 | 01285a
.L1285e:
        tst.b   A_mothership_ready-FGB(%a5)             | 01285e
        jbeq    .L12934                                 | 012864
        cmpi.l  #MOTHERSHIP_TURN_FRAME,A_mothership_phase_timer-FGB(%a5)        | 012868
        jbne    .L128ea                                 | 012872
        cmpi.b  #MOTHERSHIP_INDEX_SEGMENTED,A_mothership_index-FGB(%a5)         | 012876
        jbge    .L128b8                                 | 01287e
        lea     A_enemy_slots-FGB(%a5),%a2              | 012882
        move.b  #MOTHERSHIP_TURN_HEADING,MOTHERSHIP_TURN_HEADING_OFF(%a2)       | 012888
        move.b  #MOTHERSHIP_TURN_HEADING,MOTHERSHIP_TURN_HEADING_OFF+ENTITY_STRIDE(%a2)  | 01288e
        move.w  #MOTHERSHIP_TURN_SPEED,%d0              | 012894
        move.w  %d0,MOTHERSHIP_TURN_SPEED_OFF(%a2)      | 012898
        move.w  %d0,MOTHERSHIP_TURN_SPEED_OFF+ENTITY_STRIDE(%a2)                | 01289c
        move.b  #MOTHERSHIP_TURN_FLAG,MOTHERSHIP_TURN_FLAG_OFF(%a2)             | 0128a0
        move.b  #MOTHERSHIP_TURN_FLAG,MOTHERSHIP_TURN_FLAG_OFF+ENTITY_STRIDE(%a2)        | 0128a6
        clr.b   MOTHERSHIP_TURN_CLEAR_OFF(%a2)          | 0128ac
        clr.b   MOTHERSHIP_TURN_CLEAR_OFF+ENTITY_STRIDE(%a2)                    | 0128b0
        jbra    .L128ea                                 | 0128b4
.L128b8:
        lea     A_enemy_slots-FGB(%a5),%a2              | 0128b8
        move.w  #MOTHERSHIP_TAIL_PAIRS-1,%d7            | 0128be
.L128c2:
        tst.b   ENTITY_ALIVE(%a2)                       | 0128c2
        jbeq    .L128e2                                 | 0128c6
        move.b  #MOTHERSHIP_TURN_HEADING,MOTHERSHIP_TURN_HEADING_OFF(%a2)       | 0128ca
        move.w  #MOTHERSHIP_TURN_SPEED,%d0              | 0128d0
        move.w  %d0,MOTHERSHIP_TURN_SPEED_OFF(%a2)      | 0128d4
        move.b  #MOTHERSHIP_TURN_FLAG,MOTHERSHIP_TURN_FLAG_OFF(%a2)             | 0128d8
        clr.b   MOTHERSHIP_TURN_CLEAR_OFF(%a2)          | 0128de
.L128e2:
        lea     MOTHERSHIP_PAIR_BYTES(%a2),%a2          | 0128e2
        dbf     %d7,.L128c2                             | 0128e6
.L128ea:
        btst    #EXPLOSION_BIT_SHIP_DEATH,A_explosion_group_active_bits-FGB(%a5)         | 0128ea
        jbne    .L12958                                 | 0128f2
        cmpi.b  #MOTHERSHIP_INDEX_SEGMENTED,A_mothership_index-FGB(%a5)         | 0128f6
        jblt    .L12934                                 | 0128fe
        lea     A_enemy_slots-FGB(%a5),%a2              | 012902
        move.w  #ENEMY_SLOT_COUNT-1,%d7                 | 012908
.L1290c:
        tst.b   ENTITY_ALIVE(%a2)                       | 01290c
        jbne    .L12934                                 | 012910
        lea     ENTITY_STRIDE(%a2),%a2                  | 012914
        dbf     %d7,.L1290c                             | 012918
        addi.b  #1,A_mothership_wave_clear_count-FGB(%a5)       | 01291c
        cmpi.b  #MOTHERSHIP_WAVE_CLEARS_TO_END,A_mothership_wave_clear_count-FGB(%a5)    | 012924
        jbne    .L12934                                 | 01292c
        jbra    .Lexit_advance_section                  | 012930  -> 0x10814
.L12934:
        st      A_unused_section_end_flag-FGB(%a5)      | 012934
        cmpi.l  #MOTHERSHIP_LEAVE_FRAME,A_mothership_phase_timer-FGB(%a5)       | 01293a
        jbeq    .Lexit_advance_section                  | 012944  -> 0x10814
        tst.b   A_mothership_offscreen-FGB(%a5)         | 012948
        jbne    .Lexit_advance_section                  | 01294e  -> 0x10814
        sf      A_unused_section_end_flag-FGB(%a5)      | 012952
.L12958:
        subi.b  #1,A_enemy_seeker_cooldown-FGB(%a5)     | 012958
        jbpl    .L1296a                                 | 012960
        clr.b   A_enemy_seeker_cooldown-FGB(%a5)        | 012964
.L1296a:
        jbra    .Lexit_next_frame                       | 01296a  -> 0x10f4e

| ================================================================================================
| THE EXITS — where the original leaves, and what this twin answers instead.
|
| The original's stage does not `rts`: it `bra`s to one of five addresses in the frame loop. The
| reconstruction's `frame_loop_once` stays C, so the twin ANSWERS WITH THE ADDRESS IT WOULD HAVE
| BRANCHED TO, as ../../include/frame.h's `frame_exit` enum, in %d0 — exactly what
| `frame_resolve_hits_and_game_state` returns.
| ================================================================================================
.Lexit_title:                                   | -> 0x10500
        moveq   #FRAME_EXIT_TITLE,%d0
        jbra    .Lreturn
.Lexit_reload_section:                          | -> 0x1083a
        moveq   #FRAME_EXIT_RELOAD_SECTION,%d0
        jbra    .Lreturn
.Lexit_restart_section:                         | -> 0x10b6e
        moveq   #FRAME_EXIT_RESTART_SECTION,%d0
        jbra    .Lreturn
.Lexit_advance_section:                         | -> 0x10814
        moveq   #FRAME_EXIT_ADVANCE_SECTION,%d0
        jbra    .Lreturn
.Lexit_next_frame:                              | -> 0x10f4e
        moveq   #FRAME_EXIT_NEXT_FRAME,%d0
.Lreturn:
        FRAME_EPILOGUE

| ================================================================================================
| THE TRAMPOLINES — one thin block per callee, and the whole of the register translation.
|
| The original passes its callees' arguments IN REGISTERS and reads their answers out of registers
| and the condition codes. The reconstruction's cores carry C signatures and the m68k SysV ABI, so
| each site needs a block that binds one to the other. There are NINETEEN blocks over eighteen C
| functions (the two spins share `sched_wait8`), and they all have the same five parts:
|
|   1. save the ABI's CALL-CLOBBERED file (%d0-%d1/%a0-%a1). The C cores preserve %d2-%d7/%a2-%a6
|      by the ABI, so with this `movem` a trampoline preserves EVERY register — which is what the
|      original's callees do, and what the twin's own instructions after the call assume. The two
|      that must DELIVER a value in %d0 (`score_add_bcd` and `mothership_segment_hit`) save
|      %d1/%a0-%a1 only, and say so where they do it.
|   2. turn each POINTER argument into an image OFFSET — with `suba.l`, for the reason PUSH_OFFSET
|      gives below. The body holds real pointers, exactly as the original holds real addresses; the
|      cores take offsets.
|   3. push the arguments right to left and call.
|   4. apply the answer the site reads — see the three kinds below.
|   5. restore and `rts`.
|
| THREE KINDS OF ANSWER, and each is applied BEFORE the `movem` restores, because `movem` and `rts`
| do not touch the condition codes on a 68000 — so a flag set here survives to the twin's own `beq`
| just as the original's callee's flag did:
|
|   Z   `tst.l %d0` — `collision_chain_walk` and `entity_type_is_lockable` are branched on.
|   X   SIX of them leave the 68000's X, and the next kill's `abcd` ADDS it. Four carry it as a C
|       `extend` value in and out (`shot_retire_kind32`/`_kind33`/`_kind36`, `score_add_bcd`,
|       `mothership_segment_hit`); `sound_start` leaves it as a pure function of the tune number
|       (include/sound.h's `sound_start_leaves_extend`) and never sees a C `extend` at all.
|       THE STUB MARSHALS X IN BOTH BUILDS, on purpose: the door below exists only off target, so
|       doing it there would be a thing the shipping machine never did.
|   D0  the extra-life threshold AS IT WAS BEFORE the award, which `score_add_bcd` leaks and this
|       stage uses as its sound channel (../frame.c, "WHAT A VERIFIED CALLEE LEAVES IN D0").
|
| EVERY OTHER STUB IS X-TRANSPARENT BY CONSTRUCTION, which is what PUSH_OFFSET's `suba.l` buys: a
| stub sits between two of the original's own instructions, and on the passes that carry X an extra
| `sub.l` would be a carry the original never generated.
|
| WHAT THE DOOR IS. Off target there is no C in the emulated address space at all, so `ZY_DOOR_*`
| names an address the harness watches for: the twin `jsr`s to it, tools/recreate_kit/asm_twin.py
| services the callback by calling the host C, and resumes the blob. ON TARGET the door does not
| exist and the same `jsr` names the real core. The bodies above are identical either way.
| ================================================================================================
| THE DOOR'S BAND IS THE KIT'S CONSTANT, USED DIRECTLY. tools/recreate_kit/asm_twin.py owns
| DOOR_BASE/DOOR_STRIDE because it is what WATCHES the band, and kit.mk passes both in as -D's. An
| `.equ` of our own here would be a second spelling with nothing pinning it equal: move the band
| there and every stub below would go on jumping at the old address, which is then ordinary zeroed
| memory — and each case would die as a sentinel timeout naming neither the door nor the callee.
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

| Push one of the body's POINTERS as the image OFFSET the core wants.
|
| `suba.l` AND NOT `sub.l`, WHICH IS THE WHOLE POINT: a stub sits between two of the original's own
| instructions, and on the two passes that carry the X flag (`frame_enemy_rams_ship` and
| `frame_player_shots_hit_enemies`) the next `abcd` ADDS whatever X is left behind. `sub.l` sets X;
| `suba.l` touches no condition code at all, so this arithmetic is invisible where the original had
| none. Every stub below is therefore X-TRANSPARENT except the five that set X deliberately.
        .macro  PUSH_OFFSET areg
        movea.l \areg,%a0
        suba.l  %a6,%a0
        move.l  %a0,-(%sp)
        .endm

| Read the 68000's X into \reg as the C's 0-or-1 `extend_in`.
|
| `roxl` AND NOT `move.w %sr`, and the reason is not style. MOVE FROM SR IS UNPRIVILEGED ONLY ON THE
| 68000: the 68010 made it a supervisor instruction and every later part kept it that way, so a
| `move.w %sr,\reg` here — which is the twin's OWN instruction, in the arm that ships, reached on the
| first scoring kill of the first frame — takes a privilege violation on a TT, a Falcon or any
| accelerated ST. Nothing in this workspace would see it: Musashi is configured as a 68000 and the
| smoke runs Hatari as an ST, so the whole differential and the whole on-target gate are blind to it.
| `roxl.l #1` rotates X into bit 0 of a cleared register and is unprivileged on every 68k. It is also
| cheaper — 12 cycles against the 22 the three-instruction form cost.
|
| It leaves X clear, which is harmless: every user of this pairs it with X_OUT.
        .macro  X_IN reg
        moveq   #0,\reg
        roxl.l  #1,\reg
        .endm

| Write bit 0 of \reg back into the 68000's X. Every other condition code is dead at each site this
| is used at, which is why the whole CCR may be written rather than only its bit 4 — and it is
| always the LAST flag-touching instruction in its stub.
        .macro  X_OUT reg
        lsl.w   #4,\reg
        move.w  \reg,%ccr
        .endm

| ---- int collision_chain_walk(const uint8_t *image, uint16_t index) ---- D0 = index, answer in Z
        .globl  door_collision_chain_walk
door_collision_chain_walk:
        SCRATCH_SAVE
        move.l  %d0,-(%sp)
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_collision_chain_walk, collision_chain_walk)
        lea     8(%sp),%sp
        tst.l   %d0                             | the Z the original's callee answers in
        SCRATCH_RESTORE
        rts

| ---- int entity_type_is_lockable(const uint8_t *image, uint32_t entity) ---- A2, answer in Z
        .globl  door_entity_type_is_lockable
door_entity_type_is_lockable:
        SCRATCH_SAVE
        PUSH_OFFSET %a2
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_entity_type_is_lockable, entity_type_is_lockable)
        lea     8(%sp),%sp
        tst.l   %d0
        SCRATCH_RESTORE
        rts

| ---- void bomb_update(uint8_t *image, uint32_t bomb, uint8_t channel) ---- A3 = bomb, D0 = channel
        .globl  door_bomb_update
door_bomb_update:
        SCRATCH_SAVE
        move.l  %d0,-(%sp)
        PUSH_OFFSET %a3
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_bomb_update, bomb_update)
        lea     12(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void explosion_spawn(uint8_t *image, uint32_t source, uint16_t group) ---- A2, D2
        .globl  door_explosion_spawn
door_explosion_spawn:
        SCRATCH_SAVE
        move.l  %d2,-(%sp)
        PUSH_OFFSET %a2
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_explosion_spawn, explosion_spawn)
        lea     12(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void ship_resolve_entity_hits(uint8_t *image, uint32_t ship, uint32_t row) ---- A2, A3
        .globl  door_ship_resolve_entity_hits
door_ship_resolve_entity_hits:
        SCRATCH_SAVE
        PUSH_OFFSET %a3
        PUSH_OFFSET %a2
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_ship_resolve_entity_hits, ship_resolve_entity_hits)
        lea     12(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void enemy_morph_to_type6(uint8_t *image, uint32_t entity) ---- A2
        .globl  door_enemy_morph_to_type6
door_enemy_morph_to_type6:
        SCRATCH_SAVE
        PUSH_OFFSET %a2
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_enemy_morph_to_type6, enemy_morph_to_type6)
        lea     8(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void sound_start(uint8_t *image, uint16_t number, uint8_t channel) ---- D1 = number, D0 = ch
|
| IT LEAVES X, AND THE STAGE READS IT. `sound_lookup_tune`'s `lsl.w #8,d1` at 0x16b42 shifts bit 7
| of the tune number out into the 68000's X, and the next kill's `score_add_bcd` ADDS it
| (include/sound.h's `sound_start_leaves_extend`, which is that predicate; src/frame.c's
| `play_enemy_hit_tune` is the site that threads it). The routine preserves every register, so the
| stage's D0 — the channel — survives, and the whole of its effect on this stub is that one flag.
        .globl  door_sound_start
door_sound_start:
        SCRATCH_SAVE
        move.l  %d0,-(%sp)
        move.l  %d1,-(%sp)
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_sound_start, sound_start)
        lea     12(%sp),%sp
        move.l  4(%sp),%d0                      | the tune number as it was passed (the saved %d1)
        lsr.w   #3,%d0                          | its bit 7 -> the CCR's bit 4
        and.w   #(1 << 4),%d0
        move.w  %d0,%ccr
        SCRATCH_RESTORE
        rts

| ---- unsigned shot_retire_kind32(uint8_t *image, uint32_t shot, unsigned extend_in) ---- A2, X
        .globl  door_shot_retire_kind32
door_shot_retire_kind32:
        SCRATCH_SAVE
        X_IN    %d1
        move.l  %d1,-(%sp)
        PUSH_OFFSET %a2
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_shot_retire_kind32, shot_retire_kind32)
        lea     12(%sp),%sp
        X_OUT   %d0
        SCRATCH_RESTORE
        rts

| ---- unsigned shot_retire_kind33(uint8_t *image, uint32_t shot, unsigned extend_in) ---- A2, X
        .globl  door_shot_retire_kind33
door_shot_retire_kind33:
        SCRATCH_SAVE
        X_IN    %d1
        move.l  %d1,-(%sp)
        PUSH_OFFSET %a2
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_shot_retire_kind33, shot_retire_kind33)
        lea     12(%sp),%sp
        X_OUT   %d0
        SCRATCH_RESTORE
        rts

| ---- unsigned shot_retire_kind36(uint8_t *image, uint32_t shot) ---- A2; NO extend in, X out
        .globl  door_shot_retire_kind36
door_shot_retire_kind36:
        SCRATCH_SAVE
        PUSH_OFFSET %a2
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_shot_retire_kind36, shot_retire_kind36)
        lea     8(%sp),%sp
        X_OUT   %d0
        SCRATCH_RESTORE
        rts

| ---- unsigned score_add_bcd(uint8_t *image, uint32_t award_end, unsigned extend_in) ---- A1, X
|
| THE ONE THAT DELIVERS %d0. The original ends `move.l $195d8,d0` — the extra-life threshold AS IT
| STOOD BEFORE the award, because 0x12e04 loads it before 0x12e26 rewrites it — and this stage arms
| its next tune on whatever the last callee left in D0. So the threshold is read HERE, before the
| call, parked, and delivered afterwards; %d0 is NOT restored.
        .globl  door_score_add_bcd
door_score_add_bcd:
        movem.l %d1/%a0-%a1,-(%sp)
        move.l  A_extra_life_threshold_bcd-FGB(%a5),-(%sp)      | before the award
        X_IN    %d1
        move.l  %d1,-(%sp)
        PUSH_OFFSET %a1
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_score_add_bcd, score_add_bcd)
        lea     12(%sp),%sp
        X_OUT   %d0
        move.l  (%sp)+,%d0                      | the leaked threshold (`move` does not touch X)
        movem.l (%sp)+,%d1/%a0-%a1
        rts

| ---- unsigned mothership_segment_hit(uint8_t *image, uint32_t segment) ---- A1, X out
|
| THE SECOND THAT DELIVERS %d0, AND ONLY ON ONE ARM. The routine calls `score_add_bcd` where a
| segment PAIR dies, under a `movem` that saves only A0 and A1, so it leaks the same threshold —
| and only there. src/frame.c's `frame_segment_hit` is that model: the pair's death is observable
| from outside as this record's own type becoming EXPLOSION_PART_TYPE, so the stub re-reads it and
| leaves the incoming channel in %d0 when the pair lived.
|
| THE ORDER HERE IS LOAD-BEARING: the type test must happen BEFORE X is written, because `cmpi`
| leaves X alone but the pointer arithmetic before it would not have. X is set last, on both arms.
        .globl  door_mothership_segment_hit
door_mothership_segment_hit:
        SCRATCH_SAVE                                            | %d0 = the incoming sound channel
        move.l  A_extra_life_threshold_bcd-FGB(%a5),-(%sp)      | before the award
        move.l  %a1,-(%sp)                                      | park the POINTER for the re-read
        PUSH_OFFSET %a1                                         | ...and the OFFSET as the argument
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_mothership_segment_hit, mothership_segment_hit)
        lea     8(%sp),%sp                                      | drop arg0 and arg1
        move.l  %d0,%d1                                         | %d1 = the returned extend
        movea.l (%sp)+,%a0                                      | the parked pointer, as it stood
        move.l  (%sp)+,%d0                                      | the threshold before the award
        cmpi.b  #EXPLOSION_PART_TYPE,ENTITY_TYPE(%a0)
        jbeq    .Lseg_pair_died                                 | it died -> leak the threshold
        move.l  (%sp),%d0                                       | it lived -> the incoming channel
.Lseg_pair_died:
        X_OUT   %d1
        lea     4(%sp),%sp                                      | skip the saved %d0: we deliver ours
        movem.l (%sp)+,%d1/%a0-%a1
        rts

| ---- void screen_flip_buffers(uint8_t *image) ----
        .globl  door_screen_flip_buffers
door_screen_flip_buffers:
        SCRATCH_SAVE
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_screen_flip_buffers, screen_flip_buffers)
        lea     4(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void powerup_downgrade_on_death(uint8_t *image) ----
        .globl  door_powerup_downgrade_on_death
door_powerup_downgrade_on_death:
        SCRATCH_SAVE
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_powerup_downgrade_on_death, powerup_downgrade_on_death)
        lea     4(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void game_over_screen(uint8_t *image) ----
        .globl  door_game_over_screen
door_game_over_screen:
        SCRATCH_SAVE
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_game_over_screen, game_over_screen)
        lea     4(%sp),%sp
        SCRATCH_RESTORE
        rts

| ---- void ikbd_send_cmd(uint8_t command) ---- D0 = command; TAKES NO IMAGE POINTER
        .globl  door_ikbd_send_cmd
door_ikbd_send_cmd:
        SCRATCH_SAVE
        move.l  %d0,-(%sp)
        ZY_CALL(ZY_DOOR_ikbd_send_cmd, ikbd_send_cmd)
        lea     4(%sp),%sp
        SCRATCH_RESTORE
        rts

#ifdef ZY_ASM_FRAME_DOOR
| THE LAST THREE ARE OFF-TARGET ONLY. On target the body spins and pokes the MFP with the
| original's own instructions (band 5 says why), and the target's own sched.h/hw.h supply only
| `static inline` versions with no linkable symbol — so these stubs would not even link there.
| ---- int sched_wait8(uint8_t *image, uint32_t addr, uint8_t until, uint32_t site_pc) ----
|
| THE TWO SPINS, and with the `bset` below they are the only three places this twin is not the
| original's own instructions. tools/recreate_kit/include/sched.h says why a busy-wait on a byte an
| interrupt writes has to be read through the kit off target. THE ANSWER IS DELIVERED IN %d0 (0 = the
| poll cap was exhausted), which band 5 branches on, so neither stub restores %d0.
        .globl  door_sched_wait_raster
door_sched_wait_raster:
        movem.l %d1/%a0-%a1,-(%sp)
        pea     FRAME_RASTER_WAIT_PC
        pea     FRAME_RASTER_PHASE_READY
        pea     A_raster_phase
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_sched_wait8, sched_wait8)
        lea     16(%sp),%sp
        movem.l (%sp)+,%d1/%a0-%a1
        rts

        .globl  door_sched_wait_vbl
door_sched_wait_vbl:
        movem.l %d1/%a0-%a1,-(%sp)
        pea     FRAME_VBL_WAIT_PC
        pea     FRAME_VBL_WAIT_DONE
        pea     A_vbl_wait_flag
        move.l  %a6,-(%sp)
        ZY_CALL(ZY_DOOR_sched_wait8, sched_wait8)
        lea     16(%sp),%sp
        movem.l (%sp)+,%d1/%a0-%a1
        rts

| ---- void hw_bset8(uint32_t addr, uint32_t bit) ---- `bset #6,$fffa09`; TAKES NO IMAGE POINTER
        .globl  door_hw_bset_ierb
door_hw_bset_ierb:
        SCRATCH_SAVE
        pea     MFP_ACIA_CHANNEL_BIT
        pea     HW_MFP_IERB
        ZY_CALL(ZY_DOOR_hw_bset8, hw_bset8)
        lea     8(%sp),%sp
        SCRATCH_RESTORE
        rts
#endif
