/* weapons.h — every projectile in the game and everything that spawns one: the player's three
 * five-shot bullet slots, the smart bomb and its blast, the enemy bullets and turret barrels, the
 * two collision passes with their twenty-three hit handlers, and the level spawn script.
 *
 * THE FOUR RECORD BLOCKS BELOW ARE FROZEN, for the reason `include/entity.h`'s is: the player slice
 * ports `fire_pattern_level0..4` against the bullet slots, the entity slice already reaches the
 * item arena beside the bomb, and the sprite slice reads the display records these publish. Each is
 * written out ONCE, in one block nobody adds to — inserting at an offset is not appending
 * (../README.md, "FREEZE a shared record layout in one block"; docs/agent-playbook.md §11).
 *
 * EVERY FIELD CARRIES ITS PROVENANCE: `pinned by <test>` means a differential case would fail if
 * the offset moved; `names.txt, unpinned` is a read of ../names.txt plus ../out/prg_dis.txt,
 * believed but not exercised here. The only permitted edit is upgrading a tag in the same change
 * that ports the routine which pins it.
 */
#ifndef FS_WEAPONS_H
#define FS_WEAPONS_H

#include <stdint.h>

#include "display_list.h"  /* the 6-byte record every publisher below writes */
#include "entity.h"        /* the 58-byte entity record, the group tables, the enemy descriptors */

/* The weapon power-up level. Raised by `item_pickup_award` @ 0x11714 (src/entity.c), read by
 * `spawn_script_step` @ 0x12fc4 and by `player_fire` @ 0x13ebc — the level IS the weapon's state,
 * so it lives here and the other two subsystems include this header to reach it. */
#define A_weapon_level 0x17714u
#include "globals.h"
#include "hud.h"           /* score_add_award, A_player, A_bombs, A_alt_bullet_glyph_flag */
#include "sound.h"         /* the four sfx wrappers, and SND_SFX_ACTIVE for the one busy test */
#include "sprite.h"        /* the sprite record's hit box, which both collision passes read */

/* ================================================================================================
 * THE PLAYER'S BULLETS — frozen. 15 records of 8 bytes at A_player_bullet_arena, reached ONLY
 * through the three five-pointer slot tables (`player_shot_slot_0..2`), never by indexing.
 *
 * The three tables are one shot each: `player_fire` @ 0x13e12 picks a free slot, the level's fire
 * pattern activates a subset of its five bullets with different dx, and the slot's busy flag stays
 * set until `player_shot_slot_release_if_empty` @ 0x141e4 finds all five free again.
 * ============================================================================================= */
#define A_player_bullet_arena 0x5ae22u /* `var 0x5ae22 player_bullet_arena` — the 15 records the
                                        * three tables between them point at */
#define PLAYER_BULLET_BYTES      8u    /* 15 records over 0x5ae22..0x5ae9a */
#define PLAYER_BULLET_X          0u    /* .w — `add.w d0,(a1)` @ 0x140fc.
                                        * pinned by test_weapons.py::test_player_bullet_step */
#define PLAYER_BULLET_Y          2u    /* .w — `subi.w #$13,2(a1)` @ 0x140fe. Same pin. */
#define PLAYER_BULLET_DX         4u    /* .w, signed — the spread the fire pattern wrote.
                                        * pinned by test_weapons.py::test_player_bullet_step */
/* .w — 0 free, 1 in flight, 2 hit something this frame. The publisher draws state 2 as the impact
 * glyph and frees the slot in the same pass, so the impact shows for exactly one frame.
 * pinned by test_weapons.py::test_player_bullet_publish_states */
#define PLAYER_BULLET_STATE      6u
#define PLAYER_BULLET_FREE       0u
#define PLAYER_BULLET_IN_FLIGHT  1u
#define PLAYER_BULLET_HIT        2u

/* The three shot slots: five longword pointers into the arena each, their three busy flags, and the
 * five display records each publishes into. All three families are arithmetic progressions, which
 * is why a base and a stride replace the original's three unrolled `lea` pairs. */
#define A_player_shot_slot_0  0x19422u /* `lea $19422,a0` @ 0x140cc — pinned by test_weapons.py */
#define PLAYER_SHOT_SLOTS        3u    /* the three tables 0x19422 / 0x19436 / 0x1944a */
#define PLAYER_SHOT_BULLETS      5u    /* `move.w #$4,d7` + `dbf` @ 0x140ea */
#define PLAYER_SHOT_TABLE_STRIDE 0x14u /* = PLAYER_SHOT_BULLETS * ENTITY_GROUP_PTR_BYTES */
#define A_shot_slot_busy_0    0x17716u /* `lea $17716,a4` @ 0x141ba; the three are consecutive */
#define SHOT_SLOT_BUSY_BYTES     2u    /* `clr.w (a4)` @ 0x141f4 — a WORD flag */
#define A_dl_player_bullets_0 0x17b6au /* `lea $17b6a,a1` @ 0x1411e — pinned by test_weapons.py */
#define DL_SHOT_STRIDE        0x1eu    /* = PLAYER_SHOT_BULLETS * DISPLAY_REC_BYTES */

#define PLAYER_BULLET_DY      0x13u    /* `subi.w #$13,2(a1)` @ 0x140fe — 19 pixels a frame, up */
#define PLAYER_BULLET_RETIRE_Y 0xfff8u /* `cmpi.w #$fff8,2(a1)` + `bgt` @ 0x14104: a bullet at or
                                        * above row -8 is freed */
#define PLAYER_BULLET_GLYPH   0x7fu    /* `move.b #$7f,4(a1)` @ 0x14164 */
#define PLAYER_BULLET_GLYPH_ALT 0xe4u  /* ...unless the "GCC" cheat flag is set @ 0x14172 */
#define PLAYER_BULLET_IMPACT_GLYPH 0xe5u /* `move.b #$e5,4(a1)` @ 0x1418e — state 2's one frame */

/* ================================================================================================
 * THE SMART BOMB AND ITS BLAST — frozen.
 *
 * One bomb at a time: `bomb_drop` arms A_player_bomb, `bomb_fall_step` walks it down the fall path
 * until the path's 999 ends it, and the impact hands the position to A_blast_state, which then
 * walks fifteen 8-byte steps of four signed (dx, dy) byte pairs — the four sprites of the blast.
 * ============================================================================================= */
#define A_player_bomb        0x5aed6u /* `lea $5aed6,a0` @ 0x10e8c — the seventh and last record of
                                       * the item arena `include/entity.h` names the first six of */
#define BOMB_X                   0u  /* .w — `move.w (a0),(a1)` @ 0x10efe.
                                      * pinned by test_weapons.py::test_bomb_publish_while_falling */
#define BOMB_START_Y             2u  /* .w — the row the drop began at; the fall path's dy is added
                                      * to THIS, not to the live y, so the path is absolute.
                                      * pinned by test_weapons.py::test_bomb_fall_walks_the_path */
#define BOMB_Y                   4u  /* .w — the live row. Same pin. */
#define BOMB_FRAME               6u  /* .w — the sprite id, published as a BYTE.
                                      * pinned by test_weapons.py::test_bomb_publish_while_falling */

#define A_bomb_fall_path     0x15ce6u /* `lea $15ce6,a1` @ 0x10e92 */
#define BOMB_PATH_DY             0u   /* .w — added to BOMB_START_Y; SCRIPT_TERMINATOR ends the path */
#define BOMB_PATH_FRAME          2u   /* .w -> BOMB_FRAME */
#define BOMB_PATH_STEP_BYTES     4u   /* `addi.l #$4,$176f2` @ 0x10eb4 */

#define A_blast_state        0x5aec2u /* `lea $5aec2,a1` @ 0x10cd4 */
#define BLAST_X                  0u  /* .w — the impact point, copied from BOMB_X.
                                      * pinned by test_weapons.py::test_bomb_impact_arms_the_blast */
#define BLAST_Y                  2u  /* .w — ...and from BOMB_Y. Same pin. */
#define BLAST_POINTS             4u  /* the four (x.w, y.w) sprite positions the step recomputes.
                                      * pinned by test_weapons.py::test_blast_step_walks_the_offsets */
#define BLAST_POINT_BYTES        4u
#define BLAST_POINTS_COUNT       4u  /* `move.w #$3,d7` @ 0x11b90, and the four unrolled pairs
                                      * @ 0x10cde..0x10d1c */

#define A_blast_offset_tbl   0x1606eu /* `lea $1606e,a0` @ 0x10cc2 */
#define BLAST_OFFSET_STEP_BYTES  8u   /* `lsl.w #3,d0` @ 0x10cd0 — four signed byte pairs */
#define BLAST_LAST_STEP       0x0eu   /* `cmpi.w #$e,d0` + `blt` @ 0x10ca2: step 14 is the one that
                                       * retires the blast, so the table has 14 live steps */
#define BLAST_GLYPH           0xd2u   /* `move.b #$d2,(a1)+` @ 0x10d3c and its three siblings */
#define BLAST_HIT_BOX         0x20u   /* `addi.w #$20,d2` @ 0x11c1a — each blast point tests as a
                                       * 32x32 box against the entity's own hit box */

#define A_blast_step         0x176ecu /* .w — which of the fifteen offset steps the blast is on */
#define A_bomb_falling       0x176eeu /* .w — `tst.w $176ee` @ 0x10e7c */
#define A_bomb_exploding     0x176f0u /* .w — `st $176f0` @ 0x10eda; set for the blast's whole life */
#define A_bomb_path_cursor   0x176f2u /* .l — a BYTE offset into A_bomb_fall_path */
#define A_dl_blast           0x17c8au /* `lea $17c8a,a1` @ 0x10d28 — BLAST_POINTS_COUNT records */
#define A_dl_bomb            0x17ca2u /* `lea $17ca2,a1` @ 0x10ef2 — one record */

/* ================================================================================================
 * THE ENEMY BULLETS — frozen. A 999-terminated array of 10-byte records at A_enemy_bullets, walked
 * forward until the sentinel rather than by a count.
 * ============================================================================================= */
#define A_enemy_bullets      0x1946eu /* `lea $1946e,a0` @ 0x125bc */
#define ENEMY_BULLET_BYTES      10u   /* `lea 10(a0),a0` @ 0x125ea */
#define ENEMY_BULLET_X           0u   /* .w — `move.w d4,(a6)` @ 0x128de.
                                       * pinned by test_weapons.py::test_enemy_bullet_spawn_aimed */
#define ENEMY_BULLET_Y           2u   /* .w. Same pin. */
#define ENEMY_BULLET_DX          4u   /* .w, signed — from A_enemy_bullet_velocity_tbl. Same pin. */
#define ENEMY_BULLET_DY          6u   /* .w, signed. Same pin. */
/* .w — 0 free, 1 in flight, and ENEMY_BULLET_END (999) in the record PAST the last: the array's own
 * sentinel, which every walk tests before it tests the slot.
 * pinned by test_weapons.py::test_enemy_bullets_publish_stops_at_the_sentinel */
#define ENEMY_BULLET_ACTIVE      8u
#define ENEMY_BULLET_END     0x3e7u   /* `cmpi.w #$3e7,8(a0)` @ 0x125c8 */
#define ENEMY_BULLET_LIVE        1u   /* `move.w #$1,8(a6)` @ 0x12918 */
#define A_dl_enemy_bullets   0x17bc4u /* `lea $17bc4,a1` @ 0x125c2 */
#define ENEMY_BULLET_GLYPH    0x80u   /* `move.b #$80,4(a1)` @ 0x125de */

/* The clip box `enemy_bullets_move` retires a bullet outside — asymmetric, and wider than the
 * screen on every side, because a bullet fired off-screen still has to reach the player. */
#define ENEMY_BULLET_CLIP_LEFT   0xffdau /* `cmpi.w #$ffda,(a0)` + `blt` @ 0x12986 */
#define ENEMY_BULLET_CLIP_RIGHT  0x166u  /* `cmpi.w #$166,(a0)` + `bgt` @ 0x1298c */
#define ENEMY_BULLET_CLIP_TOP    0xffdau /* `cmpi.w #$ffda,2(a0)` @ 0x12992 */
#define ENEMY_BULLET_CLIP_BOTTOM 0xecu   /* `cmpi.w #$ec,2(a0)` @ 0x1299a */

/* The aim lookup: the direction byte is read out of a 21-column grid of 32-pixel cells around the
 * player, and the direction indexes a table of (dx, dy) word pairs. */
#define A_enemy_aim_dir_lut  0x15f3au /* `lea $15e88` + `adda.l #$b2` @ 0x128f2 — the ORIGIN cell of
                                       * the grid, which is why the index may be negative */
#define AIM_LUT_ROW_STRIDE   0x15u    /* `muls.w #$15,d5` @ 0x128ec */
#define AIM_CELL_SHIFT          5u    /* `asr.w #5,d4` @ 0x128e8 — 32-pixel cells, ARITHMETIC */
#define A_enemy_bullet_velocity_tbl 0x15feeu /* `lea $15fee,a4` @ 0x12906 */
#define AIM_VELOCITY_BYTES      4u    /* `lsl.w #2,d5` @ 0x12904 — (dx.w, dy.w) */

/* Where each firing group's shot leaves the muzzle, and the spread the four-way groups add. */
#define ENEMY_DESC_MUZZLE_DX  10u  /* .w — `add.w d4,(a6)` from `move.w 10(a5),d4` @ 0x1291e */
#define ENEMY_DESC_MUZZLE_DY  12u  /* .w — likewise @ 0x12922 */
#define ENEMY_FIRE_SPREAD  0x20u   /* `subi.w #$20,d0` @ 0x12756 and the ±0x20 pairs @ 0x12782 */
#define ENEMY_FIRE_RECOIL  0x19u   /* `subi.w #$19,(a6)` @ 0x128b4 — group D backs its own shot up */
/* The box a firing entity must be inside. Group B's top edge is -16 and every other group's is 0,
 * which is the whole difference between `enemies_fire_group_b` and its three siblings. */
#define ENEMY_FIRE_X_MAX   0x13fu  /* `cmp.w #$13f,d4` + `bgt` @ 0x12768 */
#define ENEMY_FIRE_Y_MAX    0xa8u  /* `cmp.w #$a8,d5` + `bgt` @ 0x12774 */
#define ENEMY_FIRE_Y_MIN_B 0xfff0u /* `cmp.w #$fff0,d5` + `blt` @ 0x1276e — group B's only */
/* Where `enemies_fire_all` aims: the player's record plus this on BOTH axes (`addi.w #$4,d0` and
 * `addi.w #$4,d1` @ 0x12618). Spelt apart from the turret's `TURRET_AIM_PLAYER_DX`, which is the
 * same number on the x axis only — two constants because they are two decisions. */
#define ENEMY_AIM_PLAYER_OFFSET 4u

/* ================================================================================================
 * THE TURRETS — eight groups of four, each with its own four display records for the BARREL.
 *
 * `include/entity.h` owns the turret slot tables (`A_entity_group_t0`, stride 0x20); the four
 * DISPLAY-RECORD pointers that follow each of them are the barrels', and are this subsystem's.
 * ============================================================================================= */
#define A_dl_turret_ptrs_t0  0x192c6u /* `lea $192c6,a3` @ 0x12a66 — four longword pointers to
                                       * display records, ENTITY_GROUP_T_STRIDE apart like the
                                       * slot tables they interleave with */
#define TURRET_FACINGS        12u   /* `cmpi.w #$b,26(a0)` @ 0x12c7a: facing wraps 0..11 */
#define TURRET_HALF_TURN       6u   /* `addi.b #$6,d1` @ 0x12c4a — the aim is compared half a turn
                                      * round, so "already there" is a difference of exactly 6 */
#define A_turret_facing_lut  0x15dc3u /* `lea $15d00` + `adda.l #$c3` @ 0x12c36 — the origin cell */
#define TURRET_LUT_ROW_STRIDE 0x17u  /* `muls.w #$17,d4` @ 0x12c30 — a 23-column grid */
#define TURRET_AIM_PLAYER_DX   4u    /* `addi.w #$4,d7` @ 0x12c1c — the turret aims at the player's
                                      * centre, not at the record's corner */

/* The barrel sprite's own two offset tables, one pair for groups t0..t3 and one for t4..t7. */
#define A_turret_barrel_tbl_lo 0x15b96u /* `lea $15b96,a4` @ 0x12a6c — signed (dx.b, dy.b) per
                                         * facing, TURRET_BARREL_STRIDE per body frame */
#define A_turret_barrel_tbl_hi 0x15c56u /* `lea $15c56,a4` @ 0x12adc */
#define TURRET_BARREL_STRIDE 0x18u   /* `muls.w #$18,d0` @ 0x12be0 — TURRET_FACINGS * 2 bytes */
#define TURRET_BARREL_ENTRY_BYTES 2u /* `add.w d4,d4` @ 0x12be8 — one signed byte pair per facing */
#define A_turret_hit_tbl_lo  0x15cb6u /* `lea $15cb6,a6` @ 0x12a72 — the offset a DESTROYED turret's
                                       * barrel takes, (dx.w, dy.w) per body frame */
#define A_turret_hit_tbl_hi  0x15cd6u /* `lea $15cd6,a6` @ 0x12ae2 */
#define TURRET_HIT_ENTRY_BYTES 4u    /* `lsl.w #2,d0` @ 0x12b90 */
#define A_turret_barrel_base_frame 0x197f8u /* `lea $197f8,a6` + `move.b 1(a6),d5` @ 0x12bc0: the
                                             * base sprite id the facing is added to, in the ODD
                                             * byte of the word — the even byte is never read */
#define TURRET_BARREL_BASE_FRAME_BYTE 1u
#define TURRET_STATE_AIMING      0u  /* ENTITY_DEPTH_SELECT, which the turrets reuse as a state:
                                      * 0 aims and draws the barrel from the facing table */
#define TURRET_STATE_HIT         1u  /* ...1 draws the wreck from A_turret_hit_tbl_*; anything else
                                      * publishes nothing at all (`cmpi.w #$1` + neither branch) */

/* ================================================================================================
 * THE MUZZLE FLASH — two display records per firing entity, published from the descriptor's own
 * four offsets. `# ctx` in ../names.txt; CONFIRMED from the bodies (../out/names_weapons_port.txt).
 * ============================================================================================= */
#define A_dl_muzzle_group    0x17b3au /* `lea $17b3a,a1` @ 0x12282 — ENTITY_GROUP_SLOTS pairs */
#define A_dl_muzzle_pair_0   0x179c6u /* `lea $179c6,a1` @ 0x12296 — one pair each, DL_FLASH_PAIR
                                       * apart, for the three single-slot pair objects */
#define DL_FLASH_PAIR       0x0cu     /* `adda.l #$c,a1` @ 0x1231a — two display records */
#define MUZZLE_FLASH_GLYPH_BUMP 3u    /* `addi.b #$3,d2` @ 0x122de — the alternate of A_anim_frame_a */
#define MUZZLE_FLASH_GROUP_DX 0x1au   /* `addi.w #$1a,d0` @ 0x12396 — the group form spaces its two
                                       * sprites a fixed distance apart instead of reading +32/+34 */
#define MUZZLE_FLASH_GROUP_DY    6u   /* `addi.w #$6,d3` @ 0x12376 — ...and drops them six rows when
                                       * the entity's frame offset is non-zero */
#define ENEMY_DESC_FLASH_DX  28u  /* .w — `add.w 28(a5),d0` @ 0x122f8 */
#define ENEMY_DESC_FLASH_DY  30u  /* .w — `add.w 30(a5),d0` @ 0x1230a */
#define ENEMY_DESC_FLASH2_DX 32u  /* .w — `add.w 32(a5),d0` @ 0x122fe, the pair form's second sprite */
#define ENEMY_DESC_FLASH2_DY 34u  /* .w — `add.w 34(a5),d0` @ 0x12312 */

/* ================================================================================================
 * THE TWO COLLISION PASSES AND THEIR HANDLER TABLES.
 *
 * Both walk the SAME 22 group descriptors in the same order and dispatch through a table indexed by
 * the descriptor's +22 — which the old `cmt 0x19534` had as +16, and which the merged one now calls
 * "THE HIT-HANDLER INDEX". The mutation table in STATUS.md is how the +16 was found wrong.
 * ============================================================================================= */
#define A_bullet_hit_handler_tbl 0x19134u /* `lea $19134,a0` @ 0x11fb4 */
#define A_blast_hit_handler_tbl  0x19180u /* `lea $19180,a0` @ 0x11c62 */
#define HIT_HANDLER_PTR_BYTES     4u      /* `lsl.w #2,d0` @ 0x11fb2 and @ 0x11c60 */
#define HIT_GROUPS               22u      /* the 22 unrolled `lea <desc>,a5` pairs @ 0x11a8a and
                                           * @ 0x11e06 — the same descriptors in the same order */
#define PLAYER_BULLET_HIT_DX      5u      /* `addi.w #$5,d0` @ 0x11f3e — the bullet tests as a POINT
                                           * five pixels inside its own record */
#define ENEMY_DESC_FIRING_HP     26u      /* .w — `move.w 26(a5),d0` @ 0x11d20: the hit-point level
                                           * at or below which a damaged enemy starts firing back */
#define ENEMY_HIT_DROP_OFFSET  0x11u      /* `addi.w #$11,d0` @ 0x11c8e — where a cleared formation
                                           * leaves its item, relative to the last kill */

/* What the damage handlers subtract, spelt per handler because the four are NOT the same number and
 * ../names.txt's comment on 0x11f0c ("subtract 4") is right for only two of them. */
#define BLAST_DAMAGE_4            4u  /* `subi.w #$4,22(a3)` @ 0x11d08 and @ 0x11d40 */
#define BLAST_DAMAGE_5            5u  /* `subi.w #$5,22(a3)` @ 0x11d7c */
#define BLAST_DAMAGE_6            6u  /* `subi.w #$6,22(a3)` @ 0x11dc8 */
#define BULLET_DAMAGE             1u  /* `subi.w #$1,22(a3)` — every bullet damage handler */
#define BULLET_KILL_AT_HIT_POINTS 1u  /* `cmpi.w #$1,22(a3)` + `beq` @ 0x12092: `bullet_hit_damage_a`
                                       * kills at ONE hit point left, not at zero. Its three
                                       * siblings use `beq` on the subtract itself, i.e. at zero */
#define ENEMY_INDESTRUCTIBLE  0x3e7u  /* `cmpi.w #$3e7,22(a3)` @ 0x11dba and @ 0x1214a: 999 hit
                                       * points means the two `_d` handlers refuse the hit outright */
#define ENEMY_FRAME_HURT_BUMP  0x0cu  /* `addi.w #$c,20(a3)` @ 0x11d62 and @ 0x120ec — the damaged
                                       * enemy's base frame moves twelve records on */

/* ================================================================================================
 * THE LEVEL SPAWN SCRIPT — frozen. 10-byte records walked by `spawn_script_step` @ 0x12fc4, one
 * record per frame while the scroll has reached its trigger.
 * ============================================================================================= */
#define A_spawn_script_ptr    0x17770u /* .l — the level's script, installed by `start_level` */
#define A_spawn_script_cursor 0x17754u /* .l — a BYTE offset into it */
#define A_item_bomb_spawned   0x176a6u /* .w — set the first time the script offers a bomb item, so
                                        * the second offer becomes the plain enemy instead */
#define SPAWN_REC_TRIGGER        0u  /* .w — the scroll position that fires the record; SPAWN_SCRIPT_END
                                      * ends the script. pinned by test_weapons.py::test_spawn_script_step */
#define SPAWN_REC_TYPE           2u  /* .w — the index into A_spawn_handler_tbl. Same pin. */
#define SPAWN_REC_X              4u  /* .w — the formation's origin. Same pin. */
#define SPAWN_REC_Y              6u  /* .w. Same pin. */
#define SPAWN_REC_FORMATION      8u  /* .w — which record of the handler's formation table. Same pin. */
#define SPAWN_REC_BYTES         10u  /* `addi.l #$a,$17754` @ 0x13038 */
#define SPAWN_SCRIPT_END    0xa3a1u  /* `cmpi.w #$a3a1,(a0)` @ 0x12fd0 */

#define A_spawn_handler_tbl  0x190c0u /* `lea $190c0,a1` @ 0x12fe2 — longword stubs by record type */
#define SPAWN_HANDLER_PTR_BYTES  4u   /* `muls.w #$4,d1` @ 0x1302e */
#define SPAWN_TYPE_WEAPON_ITEM   1u   /* the record type that offers a weapon power-up... */
#define SPAWN_TYPE_BOMB_ITEM     3u   /* ...and the one that offers a bomb, each of which falls back
                                       * to SPAWN_TYPE_FALLBACK when the player may not have it */
#define SPAWN_TYPE_FALLBACK      2u   /* `move.w #$2,d1` @ 0x13008 and @ 0x13022 */

/* A formation record, and the arithmetic that lays one out. `slots` differs per spawn body (1, 4 or
 * 7) and the three field groups are packed back to back, so every offset is derived from it rather
 * than written down four times: `move.l 16(a1),54(a3)` @ 0x130e6 is slots=4's script-offset array
 * and `move.l 28(a1),54(a3)` @ 0x13586 is slots=7's. */
#define FORMATION_POS_DX         0u  /* .w — added to SPAWN_REC_X */
#define FORMATION_POS_DY         2u  /* .w */
#define FORMATION_POS_BYTES      4u
#define FORMATION_SLOT_UNUSED 0x63u  /* `cmp.w #$63,d2` @ 0x130cc — 99 in EITHER word retires the
                                      * slot, and the retired slot is marked with -1 in its cursor */
#define FORMATION_SCRIPT_PTR_BYTES 4u
#define FORMATION_TBL_ENTRY_BYTES  4u /* `lsl.w #2,d1` @ 0x130ae — the table is longword pointers */
#define SPAWN_FACING_START       6u  /* `move.w #$6,26(a3)` @ 0x134de — the turret spawn's only */
/* ENTITY_DRAW_LAYER's two values, spelt where the spawn writes them: the low byte becomes the
 * display record's active byte, so 1 draws in render pass B and 0xffff in pass A. */
#define SPAWN_DRAW_LAYER_TOP     1u      /* `move.w #$1,6(a3)` @ 0x13122 */
#define SPAWN_DRAW_LAYER_UNDER   0xffffu /* `move.w #$ffff,6(a3)` @ 0x13222 */
#define SPAWN_FIRE_COUNTDOWN_15 15u  /* `move.w #$f,30(a3)` @ 0x1314a */
#define SPAWN_FIRE_COUNTDOWN_10 10u  /* `move.w #$a,30(a3)` @ 0x13376 */

/* The five spawn bodies' formation tables, one per `bra` target the 26 stubs join. */
#define A_formation_tbl_a    0x1ae0cu /* `lea $1ae0c,a1` @ 0x13060 — spawn_formation_common */
#define A_formation_tbl_b    0x1af80u /* `lea $1af80,a1` @ 0x13080 */
#define A_formation_tbl_single 0x19a54u /* `lea $19a54,a1` @ 0x131a4 — spawn_single_common's own */
#define A_formation_tbl_parts  0x197fau /* `lea $197fa,a1` @ 0x13292 — spawn_bigobj_parts_common */
#define A_formation_tbl_parts_b 0x198a4u /* `lea $198a4,a1` @ 0x132c2 */
#define A_formation_tbl_parts_c 0x198f6u /* `lea $198f6,a1` @ 0x132d2 */
#define A_formation_tbl_turret_a 0x1ac80u /* `lea $1ac80,a1` @ 0x133c4 — spawn_turret_common */
#define A_formation_tbl_turret_b 0x1a58cu /* `lea $1a58c,a1` @ 0x13404 */
#define A_formation_tbl_squadron 0x19b54u /* `lea $19b54,a1` @ 0x13544 — spawn_squadron_common */

/* The four enemy descriptors `include/entity.h` does not name, all reached only by a spawn stub or
 * by the big-object publishers. Named here rather than there because these are their only readers. */
#define A_enemy_desc_0c      0x19674u
#define A_enemy_desc_0d      0x1968eu
#define A_enemy_desc_0e      0x196a8u
#define A_enemy_desc_0f      0x196c2u

/* ================================================================================================
 * THE CORES (src/weapons.c). Every `g_*` glue takes the original's registers; the one-line comment
 * above each maps register -> role.
 *
 * A HIT HANDLER TAKES ITS 68000 X FLAG AS AN ARGUMENT, because the score chain it tail-calls does:
 * `score_add_bcd` opens with `abcd`, which adds X (include/hud.h). The dispatcher's `lsl.w #2` on
 * the handler index is what sets it, and inside a handler an `addi.w`/`subi.w` resets it, so the
 * value is derived rather than guessed — `hit_dispatch_extend` is the one place that says how.
 * ============================================================================================= */
typedef void (*hit_handler)(uint8_t *image, uint32_t entity, uint32_t desc, uint32_t projectile,
                            unsigned extend_in);

void bomb_fall_step(uint8_t *image);
void bomb_publish(uint8_t *image);
void bomb_blast_step(uint8_t *image, uint32_t scratch);
void bomb_blast_publish(uint8_t *image);

void player_bullets_move_group(uint8_t *image, uint32_t slots);
void player_bullets_move_all(uint8_t *image);
void player_bullets_publish_group(uint8_t *image, uint32_t slots, uint32_t records);
void player_bullets_publish_all(uint8_t *image);
void player_shot_slot_release_if_empty(uint8_t *image, uint32_t slots, uint32_t busy);
void player_shot_slots_release(uint8_t *image);

void bomb_blast_vs_entity_groups(uint8_t *image, uint32_t point, uint32_t desc);
void bomb_blast_vs_entities_if_active(uint8_t *image, uint32_t blast, uint32_t desc);
void bomb_blast_vs_entities(uint8_t *image);
void player_bullet_vs_entity_groups(uint8_t *image, uint32_t slots, uint32_t desc);
void player_bullets_vs_entities_group(uint8_t *image, uint32_t slots);
void player_bullets_vs_entities(uint8_t *image);

void muzzle_flash_publish_pair(uint8_t *image, uint32_t desc, uint32_t records);
void muzzle_flash_publish_group(uint8_t *image, uint32_t desc, uint32_t records, uint32_t count);
void muzzle_flash_publish_all(uint8_t *image);

void enemy_bullet_spawn_aimed(uint8_t *image, uint32_t desc, uint32_t *cursor,
                              uint16_t aim_x, uint16_t aim_y, uint16_t x, uint16_t y);
void enemy_bullets_move(uint8_t *image);
void enemy_bullets_publish(uint8_t *image);
void enemies_fire_all(uint8_t *image);

void turret_aim_step(uint8_t *image, uint32_t entity);
void turrets_aim_group(uint8_t *image, uint32_t group);
void turrets_aim_group_active(uint8_t *image, uint32_t group);
void turrets_aim_all(uint8_t *image);
void turret_publish_group(uint8_t *image, uint32_t group, uint32_t records,
                          uint32_t barrel_tbl, uint32_t hit_tbl);
void turrets_publish_all(uint8_t *image);

void spawn_item_bomb(uint8_t *image, uint32_t record);
void spawn_formation_common(uint8_t *image, uint32_t record, uint32_t desc, uint32_t table);
void spawn_single_common(uint8_t *image, uint32_t record, uint32_t desc);
void spawn_bigobj_parts_common(uint8_t *image, uint32_t record, uint32_t desc, uint32_t table);
void spawn_turret_common(uint8_t *image, uint32_t record, uint32_t desc, uint32_t table);
void spawn_squadron_common(uint8_t *image, uint32_t record, uint32_t desc);
void spawn_script_step(uint8_t *image);

void clear_object_list(uint8_t *image);

#endif /* FS_WEAPONS_H */
