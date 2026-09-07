/* player.h — the player's plane: its input, its scripted take-off and fly-off, its bank, its death
 * sequence, the shots it fires and the two collision passes that kill it.
 *
 * THE 7-BYTE PLAYER RECORD lives at `A_player` (`include/hud.h`, which borrowed the address and the
 * control-mode byte before this subsystem existed) and its first three fields in `include/entity.h`
 * (`PLAYER_X`, `PLAYER_Y`, `PLAYER_FRAME`, borrowed for `sprite_hitbox_test`). BOTH LOANS HAVE BEEN
 * PAID OFF: the record is defined once, below, and those two headers read it from here — which is
 * what `test_constants.py::test_no_constant_is_defined_in_two_files` refuses the alternative to.
 * Nothing includes this header to reach it; `src/hud.c`, `src/entity.c` and `src/weapons.c` do.
 *
 * WHAT IS NOT HERE: the shot slots the fire patterns fill, the bomb record `bomb_drop` writes and
 * the enemy bullet array the collision pass walks are all the weapons subsystem's, and are read out
 * of `include/weapons.h` rather than restated. The one thing this file adds to that shot is the
 * muzzle offset every pattern opens with, which is the player's geometry and not the bullet's.
 */
#ifndef FS_PLAYER_H
#define FS_PLAYER_H

#include <stdint.h>

#include "display_list.h"   /* the 6-byte record the player and its shadow are published into */
#include "entity.h"         /* the 58-byte entity record and the group tables the passes walk */
#include "globals.h"
#include "hud.h"            /* A_player, PLAYER_MODE, A_lives, A_bombs, A_player_hit, the cheats */
#include "irq.h"            /* the four input bytes the ACIA handler writes and this one reads */
#include "sound.h"          /* the sfx wrappers the death and the landing bonus call */
#include "sprite.h"         /* the sprite record's hit box, and the scroll globals the restart sets */
#include "weapons.h"       /* the shot slots the patterns fill, the bomb record, the enemy bullets */

/* ================================================================================================
 * THE 7-BYTE PLAYER RECORD, whole: its address, its five fields and the six control modes its +6
 * byte holds. `include/hud.h` and `include/entity.h` each held part of this while this subsystem
 * was unported and now read it from here — which is why a HUD routine's `A_player` and an entity
 * routine's `PLAYER_X` are one definition rather than two.
 * ============================================================================================= */
#define A_player             0x190a4u /* `lea $190a4,a0` @ 0x123d8 */
#define PLAYER_X             0u    /* .w — `move.w (a1),d2` @ 0x116b6 */
#define PLAYER_Y             2u    /* .w — `move.w 2(a1),d2` @ 0x116dc */
#define PLAYER_FRAME         4u    /* .b — `move.b 4(a1),d0` @ 0x116a0, the sprite-bank index */
#define PLAYER_SHADOW_FRAME  5u    /* .b — `move.b 5(a0),5(a1)` @ 0x13cda, the sprite id of the
                                    * shadow the publisher offsets below the plane */
#define PLAYER_MODE          6u    /* `cmpi.b #$4,6(a0)` @ 0x123de */
#define PLAYER_RECORD_BYTES  7u    /* what `player_reset_to_start` copies, +0..+6 */

#define PLAYER_MODE_JOYSTICK 0u    /* `clr.b 6(a0)` @ 0x13b0c — the only mode input drives */
#define PLAYER_MODE_LANDING  1u    /* `move.b #$1,6(a0)` @ 0x13a80 — the end-of-level script */
#define PLAYER_MODE_FLYOFF   2u    /* `move.b #$2,6(a0)` @ 0x124fc — fly to the landing point */
#define PLAYER_MODE_DYING    3u    /* `move.b #$3,6(a1)` @ 0x1100e and @ 0x11010 */
#define PLAYER_MODE_GAMEOVER 4u    /* `cmpi.b #$4,6(a0)` @ 0x123de — the HUD's own test */
#define PLAYER_MODE_TAKEOFF  0xffu /* the template's own byte. No line of src/player.c names it: the
                                    * original tests it as `tst.b 6(a0) / bmi`, i.e. "the mode byte
                                    * is NEGATIVE", and the cores spell that test rather than an
                                    * equality the assembly does not make. It is here because
                                    * test_player.py drives the mode with it */

/* ================================================================================================
 * The take-off and fly-in scripts.
 *
 * Each is a 10-byte copy of a template made by its `*_reset`, walked 4 bytes at a time: a WORD
 * countdown at +0 that the step DECREMENTS IN PLACE, and a frame id whose LOW BYTE is read from +3.
 * The last word is negative, which ends the script — so the third record's countdown word IS that
 * terminator and its frame byte is never reached.
 * ============================================================================================= */
#define A_player_start_template 0x1909cu /* `lea $1909c,a0` @ 0x13d24 — x, y, frame, shadow, mode */
#define A_takeoff_start_pos     0x190acu /* `lea $190ac,a0` @ 0x139e4 */
#define A_landing_start_pos     0x190b6u /* `lea $190b6,a0` @ 0x13a02 */
#define A_takeoff_script        0x17726u /* `lea $17726,a1` @ 0x139ea and @ 0x13ac4 */
#define A_takeoff_script_cursor 0x17724u /* `clr.w $17724` @ 0x139fa */
#define A_landing_script        0x17730u /* `lea $17730,a1` @ 0x13a08 and @ 0x13b2c */
#define A_landing_script_cursor 0x1773au /* `clr.w $1773a` @ 0x13a18 */
#define SCRIPT_TEMPLATE_WORDS   5u       /* `move.w #$4,d7` + `dbf` @ 0x139f0 — five words copied */
#define SCRIPT_STEP_BYTES       4u       /* `addi.w #$4,$17724` @ 0x13afc */
#define SCRIPT_STEP_FRAME       3u       /* `move.b 3(a1),4(a0)` @ 0x13ada — the LOW byte of word 1 */

/* ================================================================================================
 * The scripted-movement state: the input lock, the shadow, and the two script timers.
 * ============================================================================================= */
#define A_player_input_locked  0x1775eu /* `st $1775e` @ 0x13a42 — `read_player_input` returns at
                                         * once while it is set, so a script owns the plane */
#define A_player_turning       0x1775cu /* `st $1775c` @ 0x14412 — set by left/right, and what
                                         * `player_bank_recentre` waits for before drifting back */
#define A_player_script_timer  0x176c4u /* `addi.w #$1,$176c4` @ 0x13a4e — frames spent on the spot
                                         * at the landing point before the landing script starts */
#define A_player_script_fire_enable 0x1770cu /* `st $1770c` @ 0x13a5e — set only while the fly-off
                                             * has reached the landing x, cleared by either move */
#define A_shadow_offset        0x1773cu /* `add.w $1773c,d0` @ 0x13cf0 — how far below and right of
                                         * the plane its shadow is drawn; the take-off grows it and
                                         * the landing shrinks it */
#define A_takeoff_shadow_timer 0x1773eu /* `subi.w #$1,$1773e` @ 0x13ae0 — frames per shadow step */
#define A_landing_shadow_timer 0x17740u /* `subi.w #$1,$17740` @ 0x13b48 */
/* The counters the player owns and the HUD draws. `award_extra_life` @ 0x110d4 increments
 * `A_lives` and `hud_publish_bomb_and_life_icons` clamps it and writes the clamp BACK; the bomb
 * count is read by the icon row and spent by the smart bomb. */
#define A_lives      0x17712u /* `addi.w #$1,$17712` @ 0x11194 */
#define A_bombs      0x17710u /* `move.w $17710,d7` @ 0x1240e */
#define A_player_hit 0x17706u /* `move.w #$1,$17706` @ 0x10e38 — set by the invulnerability cheat
                               * and by the death path, read by everything that fires. `# ctx` in
                               * ../names.txt, i.e. the name was inferred from its call sites;
                               * CONFIRMED here from the bodies that write and read it —
                               * `player_death_sequence_step` @ 0x13bd6 raises it on the collision
                               * and `enemies_fire_abort_if_player_hit` @ 0x12856 is the guard */
/* The player's own two display records, cleared together by `clear_player_display_slots`
 * @ 0x115c2 (src/hud.c) on the game-over arm. `dl_player` follows the shadow's six bytes. */
#define A_dl_player_shadow 0x17cfcu /* `lea $17cfc,a0` @ 0x115c6 */

#define A_landing_bomb_cash_timer 0x176c0u /* `subi.w #$1,$176c0` @ 0x13b62 — the landing script
                                         * cashes one spare bomb for 3000 points every time it
                                         * expires. ../names.txt's `weapon_decay_timer` is a
                                         * different routine's reading of the same word; see
                                         * ../out/names_player_port.txt, which proposes this name */
#define A_level_complete       0x1775au /* `st $1775a` @ 0x13ba2 when the landing script ends;
                                         * `level_progress_check` reads it as "advance the level" */

#define SHADOW_OFFSET_LANDED    0u      /* `move.w #$0,$1773c` @ 0x13b9a */
#define SHADOW_OFFSET_AIRBORNE  0x20u   /* `move.w #$20,$1773c` @ 0x13b1c */
#define TAKEOFF_SHADOW_PERIOD   3u      /* `move.w #$3,$1773e` @ 0x13af2 */
#define LANDING_SHADOW_PERIOD   2u      /* `move.w #$2,$17740` @ 0x13b5a */
#define BOMB_CASH_PERIOD        0xau    /* `move.w #$a,$176c0` @ 0x13b86 */
#define SHADOW_FRAME_AIRBORNE   0xffu   /* `move.b #$ff,5(a0)` @ 0x13abe — no shadow while climbing */
#define SHADOW_FRAME_ON_DECK    1u      /* `move.b #$1,5(a0)` @ 0x13b10 */
#define SHADOW_FRAME_OFFSET     7u      /* `addi.b #$7,d2` @ 0x13cfc — the shadow's sprite id is the
                                         * plane's plus seven, added as a BYTE */

/* The fly-off's target, and how long it hovers there before the landing script takes over. */
#define FLYOFF_TARGET_X      0x8fu /* `cmpi.w #$8f,(a0)` @ 0x13a56 */
#define FLYOFF_TARGET_Y      0x7eu /* `cmpi.w #$7e,2(a0)` @ 0x13a64 */
#define FLYOFF_HOVER_FRAMES  0x16u /* `cmpi.w #$16,$176c4` @ 0x13a76 */

/* ================================================================================================
 * The bank (tilt), and the frame table it indexes.
 * ============================================================================================= */
#define A_player_bank        0x17742u /* `adda.w $17742,a2` @ 0x13d18 — 1..11, centre 7 */
#define A_player_bank_frames 0x17744u /* `lea $17744,a2` @ 0x13d12 — one sprite id per bank step,
                                       * with a NEGATIVE byte at each end that the two turn
                                       * routines test before they step the index */
#define PLAYER_BANK_CENTRE   7u       /* `cmpi.w #$7,$17742` @ 0x13bb4 */

#define PLAYER_STEP_PIXELS   6u      /* `subi.w #$6,2(a0)` @ 0x13da8 and its three neighbours */
#define PLAYER_Y_MIN         0xcu    /* `cmpi.w #$c,2(a0) / blt` @ 0x13da0 — at or above this, up
                                      * moves; a y BELOW it is refused rather than clamped */
#define PLAYER_Y_MAX         0xbau   /* `cmpi.w #$ba,2(a0) / bgt` @ 0x13db0 */
#define PLAYER_X_MAX         0x120u  /* `cmpi.w #$120,(a0) / bgt` @ 0x13de8 */

/* ================================================================================================
 * The death sequence, the game-over display, and the bomb.
 * ============================================================================================= */
#define A_player_death_frames 0x19210u /* `lea $19210,a1` @ 0x13bd6 — WORDS whose low byte is the
                                        * frame, ended by a negative one */
#define A_death_anim_cursor   0x176f6u /* `addi.w #$2,$176f6` @ 0x13bec */
#define DEATH_FRAME_BYTES     2u       /* the cursor's step: the table is words */
#define DEATH_SINK_PIXELS     2u       /* `addi.w #$2,2(a0)` @ 0x13bfa */

#define A_dl_player      0x17d02u /* `lea $17d08,a1 / suba.l #$6,a1` @ 0x13cc0 — the LAST display
                                   * record; `A_dl_player_shadow` (include/hud.h) is the one below */
#define A_text_game_over 0x1613au /* `lea $1613a,a0` @ 0x13c6c — compiled into A_dl_bomb_icons */
#define A_game_over_flag 0x1769au /* `st $1769a` @ 0x13c7c — `level_progress_check` reads it */
#define A_game_over_delay 0x176aau /* `subi.w #$1,$176aa` @ 0x13c82 — frames the banner dwells */

#define LIVES_AFTER_GAME_OVER 1u /* `move.w $176ae,$17712` @ 0x13c4c */
#define BOMBS_AFTER_GAME_OVER 0u /* `move.w $176ac,$17710` @ 0x13c56 */

/* The bomb RECORD itself (`A_player_bomb`, `BOMB_X`, `BOMB_START_Y`) and its two in-flight flags
 * (`A_bomb_falling`, `A_bomb_exploding`) are `include/weapons.h`'s, read from there. What is here is
 * only where `bomb_drop` puts one and what it costs. */
#define BOMB_DROP_X_OFFSET 0xcu     /* `addi.w #$c,(a1)` @ 0x13d94 — the bomb leaves the nose */
#define BOMBS_MIN_TO_DROP  1u       /* `cmpi.w #$1,$17710 / blt` @ 0x13d74 */

/* ================================================================================================
 * Firing.
 * ============================================================================================= */
#define A_fire_held        0x17760u /* `st $17760` @ 0x13e46 — one shot per press, cleared when the
                                     * button is seen up */
#define A_shot_slots_full  0x17762u /* `st $17762` @ 0x13eb4 — all three shots already in flight */
#define A_weapon_fire_tbl  0x19232u /* `lea $19232,a0` @ 0x13ebc — five pattern addresses */
#define WEAPON_FIRE_PTR_BYTES 4u    /* `lsl.w #2,d1` @ 0x13ed8 */
#define WEAPON_LEVEL_MAX   4u       /* `move.w #$4,$17714` @ 0x13eca — what the cheat forces */
#define A_debug_overlay_flag 0x177cdu /* `tst.b $177cd` @ 0x13e12 — written NOWHERE in the image */
#define SFX_PLAYER_FIRE    0xbu     /* `move.w #$b,d0` @ 0x13e32, straight into the module */

/* ================================================================================================
 * The two collision passes.
 *
 * `player_vs_entities` runs the four a-groups through one box and the a4 group through a wider one;
 * both variants fall into the same loop with the five box registers already loaded.
 * ============================================================================================= */
#define PLAYER_HIT_BOX_W 0x1cu /* `addi.w #$1c,d2` @ 0x10fd2 — the player's own span, both variants */
#define PLAYER_HIT_BOX_H 0x18u /* `addi.w #$18,d2` @ 0x10ffa */

#define ENTITY_BOX_DX      0x11u /* `move.w #$11,d3` @ 0x10f8c — the standard group's box */
#define ENTITY_BOX_DY      0xcu  /* `move.w #$c,d4`  @ 0x10f90 */
#define ENTITY_BOX_H       0x17u /* `move.w #$17,d6` @ 0x10f94 */
#define ENTITY_BOX_W       0x1bu /* `move.w #$1b,d1` @ 0x10f98 */
#define ENTITY_A_GROUP_SLOTS 7u  /* `move.w #$6,d7` @ 0x10f88, a dbf count */

#define ENTITY_BOX_A4_DX   4u    /* `move.w #$4,d3`  @ 0x10f74 — the a4 group is wide and shallow */
#define ENTITY_BOX_A4_DY   3u    /* `move.w #$3,d4`  @ 0x10f78 */
#define ENTITY_BOX_A4_H    0x1bu /* `move.w #$1b,d6` @ 0x10f7c */
#define ENTITY_BOX_A4_W    0x39u /* `move.w #$39,d1` @ 0x10f80 */
#define ENTITY_A4_GROUP_SLOTS 4u /* `move.w #$3,d7` @ 0x10f70 */

/* `SCORE_AWARD_3000` — the index the landing script's bomb bonus passes to `score_add_award` — is
 * include/hud.h's, beside the run of award values it indexes. */
#define EXTEND_CLEAR 0u /* the 68000 X flag that award is entered with — see src/player.c */

#define ENEMY_BULLET_HIT_OFFSET 0x10u /* `addi.w #$10,d0` @ 0x1104c — the bullet is a POINT this far
                                       * down and right of its record's x, y */

/* ================================================================================================
 * Level flow: the end-of-level trigger, the level advance, and the checkpoint restart.
 * ============================================================================================= */
#define A_level_end_scroll_pos 0x1771cu /* `move.w $1771c,d0` @ 0x124d0 */
#define A_boss_scroll_pos      0x1770au /* `move.w $1770a,d0` @ 0x124de */
#define A_level_number         0x1642au /* `addq.w #1,$1642a` @ 0x12504 — 0..4 */
#define LEVELS                 5u       /* `cmpi.w #$5,$1642a` @ 0x1250a */
#define LEVEL_CLEAR_TUNE       0u       /* `clr.w d0` @ 0x124f6, then `music_play` */

/* The three one-shot flags that make the second, third and fourth times through the five levels
 * restart at level 1, 2 and 3 instead of at 0 — and are all cleared on the fifth. */
#define A_level_loop_flag_1 0x1769cu /* `st $1769c` @ 0x12528 */
#define A_level_loop_flag_2 0x1769eu /* `st $1769e` @ 0x12542 */
#define A_level_loop_flag_3 0x176a0u /* `st $176a0` @ 0x1255c */
#define LEVEL_LOOP_1_START  1u       /* `move.w $176ae,$1642a` @ 0x1252e — const_words[1] */
#define LEVEL_LOOP_2_START  2u       /* `move.w $176b0,$1642a` @ 0x12548 */
#define LEVEL_LOOP_3_START  3u       /* `move.w $176b2,$1642a` @ 0x12562 */

#define A_level_just_started 0x17696u /* `st $17696` @ 0x14aac — the frame loop clears it at its
                                       * bottom, and `read_player_input` skips pause and abort
                                       * while it is set */
/* `A_joy0_state` and `A_key_last_scancode` are `include/irq.h`'s — the ACIA handler writes them and
 * this subsystem only reads and clears them. THE RESTART CLEARS THE SCANCODE AND NOT `key_bits`,
 * which is why a held pause or abort key survives a stage reset and why `A_level_just_started` has
 * to gate both of them off for the frame after one. */
#define A_use_keyboard_flag  0x1770eu /* `tst.w $1770e` @ 0x14354 — read here, written nowhere */

#define A_checkpoint_tables      0x15ab0u /* `lea $15ab0,a0` @ 0x14aca — one longword per level */
/* `0x177cb` (`keep_player_hit_flag`) and the bomb count reloaded at 0x14b6e are past this slice's
 * end at 0x14b22 and are the init subsystem's to define when the rest of the restart lands. */
#define A_checkpoint_map_offset  0x176fcu /* `move.w (a1),$176fc` @ 0x14b00 */
#define A_checkpoint_scroll_pos  0x17704u /* `move.w 2(a1),$17704` @ 0x14b06 */
#define A_checkpoint_scroll_fine 0x17702u /* `move.w 4(a1),$17702` @ 0x14b0e */

#define CHECKPOINT_TABLE_PTR_BYTES 4u     /* `lsl.w #2,d0` @ 0x14ad8 */
#define CHECKPOINT_REC_BYTES       6u     /* `suba.w #$6,a1` @ 0x14af6 */
#define CHECKPOINT_REC_MAP_OFFSET  0u     /* the word `a1 -= 2` lands back on */
#define CHECKPOINT_REC_SCROLL_POS  2u     /* the word the backwards scan COMPARES */
#define CHECKPOINT_REC_SCROLL_FINE 4u
#define CHECKPOINT_SCAN_FROM   0x26u      /* `adda.l #$26,a1` @ 0x14ade — the SCROLL_POS word of the
                                           * table's seventh record, not its start */
#define CHECKPOINT_SCROLL_BACK 0xd8u      /* `subi.w #$d8,$17758` @ 0x14ae4, added back at 0x14b16 */

/* The muzzle every fire pattern starts from. The rest of the shot's shape — the bullet record, the
 * three slot tables and the busy flags — is `include/weapons.h`'s, read from there. */
#define BULLET_MUZZLE_DY 0xau /* `addi.w #$a,d1` @ 0x13eec, before any pattern touches x */
#define ENEMY_BULLET_SLOTS 16u /* `move.w #$f,d7` @ 0x11036, a dbf count — how many of the array's
                                * records `player_vs_enemy_bullets` tests, whatever the terminator
                                * `include/weapons.h`'s ENEMY_BULLET_END marks says */

/* ================================================================================================
 * THE CORES (src/player.c). Every `g_*` glue takes the original's registers; the one-line comment
 * above each maps register -> role.
 * ============================================================================================= */
void takeoff_script_reset(uint8_t *image);
void landing_script_reset(uint8_t *image);
void player_script_step(uint8_t *image);
void player_bank_recentre(uint8_t *image);
void player_frame_from_bank(uint8_t *image, uint32_t player);
void player_reset_to_start(uint8_t *image);

void player_move_up(uint8_t *image, uint32_t player);
void player_move_down(uint8_t *image, uint32_t player);
void player_move_left(uint8_t *image, uint32_t player);
void player_move_right(uint8_t *image, uint32_t player);
void bomb_drop(uint8_t *image, uint32_t player);

/* Both of these reach the game-over banner, which compiles a text script through the hud's
 * `build_text_display_list` — and that routine takes its cursor x and y in D1 and D2, keeping the
 * HIGH byte of each word the caller left. So the caller's two registers are real inputs here, and
 * the cases drive them with junk high halves rather than assuming zero. */
void player_death_sequence_step(uint8_t *image, uint32_t player, uint32_t text_x, uint32_t text_y);
void player_publish(uint8_t *image, uint32_t text_x, uint32_t text_y);

void fire_pattern_level0(uint8_t *image, uint32_t slot);
void fire_pattern_level1(uint8_t *image, uint32_t slot);
void fire_pattern_level2(uint8_t *image, uint32_t slot);
void fire_pattern_level3(uint8_t *image, uint32_t slot);
void fire_pattern_level4(uint8_t *image, uint32_t slot);
void player_fire_by_weapon_level(uint8_t *image, uint32_t slot);
void player_shot_slot_alloc(uint8_t *image);
void player_fire(uint8_t *image);

void read_player_input(uint8_t *image);

/* The three collision entries below are SLICES on their HIT arm: the original's `bra.w
 * score_add_200` @ 0x11018 enters the score subsystem's `abcd` chain with an X flag the sound
 * module's `sfx_start` left, which is not this routine's to know. test_player.py checkpoints there. */
void player_vs_entity_group_test(uint8_t *image, uint32_t group, uint32_t slots, uint32_t box_dx,
                                 uint32_t box_dy, uint32_t box_h, uint32_t box_w);
void player_vs_entities_group(uint8_t *image, uint32_t group);
void player_vs_entities_group_a4(uint8_t *image, uint32_t group);
void player_vs_entities(uint8_t *image);
void player_vs_enemy_bullets(uint8_t *image);

void level_progress_check(uint8_t *image);
void restart_level_at_checkpoint_setup(uint8_t *image);

#endif /* FS_PLAYER_H */
