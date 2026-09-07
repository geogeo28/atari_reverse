/* entity.h — the 58-byte entity record, the tables that address it, and the entity subsystem's
 * cores in src/entity.c.
 *
 * THE RECORD BLOCK BELOW IS FROZEN. `A_entity_arena`'s 91 records are what several agents port
 * routines against at the same time — the player, the weapons and the spawn slices all reach into
 * them — so the whole layout is written out ONCE, in one block nobody adds to, rather than grown
 * field by field. "Append-only in offset order" is the rule that looks right and is not: inserting
 * at an offset is not appending (README.md, "Adding a function"; docs/agent-playbook.md §11). The
 * only permitted edit is upgrading a field's tag in the same change that ports the routine which
 * pins it.
 *
 * EVERY FIELD CARRIES ITS PROVENANCE, because "named" and "held by a test" are different claims.
 * `pinned by <test>` means a differential case would fail if the offset moved; `names.txt,
 * unpinned` means it is a read of ../names.txt's comment on 0x59984 plus the disassembly,
 * believed but not exercised by anything here — check it against ../out/prg_dis.txt before you
 * lean on it.
 *
 * The arena's PLACEMENT (`A_entity_arena`, `ENTITY_SLOTS`, `ENTITY_STRIDE`) is the memory model's
 * and lives in include/globals.h; this header includes it rather than restating it.
 */
#ifndef FS_ENTITY_H
#define FS_ENTITY_H

#include <stdint.h>

#include "display_list.h"   /* the 6-byte record every publisher writes */
#include "globals.h"
#include "hud.h"            /* score_add_award, which the bonus-item drop ends in */
#include "sprite.h"         /* the sprite record's hit box, read by sprite_hitbox_test */

/* ================================================================================================
 * THE RECORD — frozen. 58 bytes, 91 of them at A_entity_arena (include/globals.h).
 *
 * The initialiser is the definitive field census: `spawn_formation_common` @ 0x130aa and
 * `spawn_single_common` @ 0x131a4 write +0..+38, +50 and +54 from a formation record and an enemy
 * descriptor, and `spawn_stub_type14`'s body @ 0x134fe adds +44. The four fields no spawn writes
 * (+40, +44 on most kinds, +46, +48) are left as `init_new_game`'s zeroes and set by the routines
 * named against them.
 * ============================================================================================= */

#define ENTITY_X                 0u  /* .w — world x. `add.w d0,(a0)` @ 0x12eb6.
                                      * pinned by test_entity.py::test_move_script_mode_steps_x_and_y */
#define ENTITY_Y                 2u  /* .w — world y. `add.w d1,2(a0)` @ 0x12eb8.
                                      * pinned by test_entity.py::test_move_script_mode_steps_x_and_y */
#define ENTITY_FRAME_OFFSET      4u  /* .w — added to ENTITY_BASE_FRAME for the published sprite.
                                      * `move.w d0,4(a0)` @ 0x12ef0 (the death path writes it),
                                      * `add.w 4(a2),d1` @ 0x136ee.
                                      * pinned by test_entity.py::test_publish_plain_frame_is_base_plus_offset */
/* .w — the DRAW LAYER, and the field ../names.txt's comment on 0x59984 gets backwards. The spawn
 * writes a whole word (1 from `spawn_formation_common` @ 0x13122, 0xffff from `spawn_single_common`
 * @ 0x13222) and every publisher copies the LOW byte — `move.b 7(a2),5(a1)` — into the display
 * record's active byte, not the high one. So 1 draws the entity in render pass B (on top) and
 * 0xffff draws it in pass A (under the scenery overlay); the hit handlers set 2 and 0.
 * pinned by test_entity.py::test_publish_copies_the_low_byte_of_the_draw_layer */
#define ENTITY_DRAW_LAYER        6u
#define ENTITY_DRAW_LAYER_BYTE   7u  /* ...that low byte on its own, which is all a publisher reads */
#define ENTITY_DX                8u  /* .w — per-frame x step, from the movement script's +0.
                                      * pinned by test_entity.py::test_move_script_mode_steps_x_and_y */
#define ENTITY_DY               10u  /* .w — per-frame y step, from the script's +2. Same pin. */
#define ENTITY_STEP_COUNTDOWN   12u  /* .w — frames left on the current script record; `subi.w
                                      * #$1,12(a0)` @ 0x12ebc, and reaching ZERO steps the script.
                                      * pinned by test_entity.py::test_move_steps_the_script_at_zero */
#define ENTITY_ACTIVE           14u  /* .w — slot in use. Every walker's first `tst.w 14(a0)`.
                                      * pinned by test_entity.py::test_move_skips_an_inactive_slot */
/* .w — DYING, and it is also the mode selector `entity_move` branches on. A live entity (0) runs
 * the movement script; a dying one (non-zero) walks the death path table instead, and every
 * publisher offsets it by its descriptor's death offset and publishes ENTITY_FRAME_OFFSET rather
 * than ENTITY_FACING. Set by the hit handlers (`st 16(a3)`), cleared by the spawn.
 * pinned by test_entity.py::test_move_dying_walks_the_death_path */
#define ENTITY_DYING            16u
#define ENTITY_ITEM_KIND        18u  /* .w — descriptor +6, the item this formation drops when it is
                                      * wholly cleared (`move.w 6(a5),18(a3)` @ 0x13138).
                                      * names.txt, unpinned — the hit handlers that read it are wave 2 */
#define ENTITY_BASE_FRAME       20u  /* .w — descriptor +4; the published frame is this plus either
                                      * ENTITY_FRAME_OFFSET or ENTITY_FACING.
                                      * pinned by test_entity.py::test_publish_plain_frame_is_base_plus_offset */
/* .w — descriptor +24, and a genuine DUAL ROLE rather than a guess. To a destructible enemy it is
 * hit points (four per bullet); to the three `A_entity_group_pair` objects it is the animation
 * PERIOD `entity_publish_anim` reloads ENTITY_ANIM_TIMER from (`move.w 22(a2),42(a2)` @ 0x138c2) —
 * `spawn_single_common` writes descriptor +24 into BOTH +22 and +42 (@ 0x13264/0x1326a), which is
 * what makes the two readings one field. 999 in it marks the big object's first part as carrying
 * three extra sprites (`cmpi.w #$3e7,22(a1)` @ 0x102ec).
 * pinned by test_entity.py::test_anim_timer_reloads_from_the_period and
 * test_entity.py::test_bigobj_extra_parts_need_the_999_marker */
#define ENTITY_HIT_POINTS       22u
#define ENTITY_ANIM_PERIOD      ENTITY_HIT_POINTS  /* the second role, spelt where it is read */
#define ENTITY_AIM_CHANGED      24u  /* .b — `st 24(a3)` @ 0x13156. Read by the turret aiming at
                                      * 0x129b2 (wave 2). names.txt, unpinned.
                                      * SECOND ROLE, and this one IS pinned: for the big object's
                                      * four parts the WORDS at +24 and +26 are the death offset
                                      * `entity_publish_group_offset` @ 0x13902 adds, standing in
                                      * for the descriptor fields every other publisher uses. */
#define ENTITY_FACING           26u  /* .w — 0..11, the turret's rotation. The published frame is
                                      * ENTITY_BASE_FRAME + this while the entity is alive.
                                      * pinned by test_entity.py::test_publish_facing_frame_is_base_plus_facing */
/* .w — the depth flag `bigobj_depth_test` @ 0x11820 sets when the big object's y has passed this
 * entity's, which the wave-2 collision and turret code reads back (`tst.w 28(a2)` @ 0x1286e,
 * `cmpi.w #$1,28(a1)` @ 0x12b60). `spawn_single_common` clears it; a hit handler writes 1.
 * pinned by test_entity.py::test_depth_flag_follows_the_big_objects_y */
#define ENTITY_DEPTH_SELECT     28u
#define ENTITY_FIRE_COUNTDOWN   30u  /* .w — frames to the next shot; seeded to 15 by both spawns.
                                      * names.txt, unpinned — enemy_fire (0x12602) is wave 2 */
#define ENTITY_FIRE_RELOAD      32u  /* .w — descriptor +8, rewritten per stage by
                                      * difficulty_apply_fire_rates. pinned by
                                      * test_entity.py::test_difficulty_writes_every_descriptor */
/* .w — which of `A_entity_path_tbl_ptrs`' three word tables the DEATH path walks. Seeded from the
 * descriptor's +16, the same word that indexes both hit-handler tables — so an enemy class's
 * handler and its death animation are one number.
 * pinned by test_entity.py::test_move_dying_walks_the_death_path (it drives all three selectors) */
#define ENTITY_PATH_SELECT      34u
#define ENTITY_PATH_CURSOR      36u  /* .w — index into that table, one word per frame.
                                      * pinned by the same test */
#define ENTITY_FIRING           38u  /* .w — set while the entity is shooting; `entity_publish_anim`
                                      * only runs its timer down while this is set.
                                      * pinned by test_entity.py::test_anim_timer_reloads_from_the_period */
/* .w — a ONE-SHOT alternate-frame latch: `entity_publish_anim` publishes ENTITY_FRAME_OFFSET + 1
 * and clears it (@ 0x138ae/0x138cc). Set by two bullet-hit handlers (`st 40(a3)` @ 0x11d16 and
 * 0x1209e), which is the flash an indestructible object shows when it is shot. Neither
 * ../names.txt's 0x59984 comment nor ../notes/gameplay.md §3.3 lists this field.
 * pinned by test_entity.py::test_anim_frame_bump_is_one_shot */
#define ENTITY_FRAME_BUMP       40u
#define ENTITY_ANIM_TIMER       42u  /* .w — counts down to the next animation step; reloaded from
                                      * ENTITY_ANIM_PERIOD. pinned by
                                      * test_entity.py::test_anim_timer_reloads_from_the_period */
#define ENTITY_KIND             44u  /* .w — descriptor +22 (`move.w 22(a5),44(a3)` @ 0x134fe).
                                      * ENTITY_KIND_BOMBER is the only value any ported routine tests.
                                      * pinned by test_entity.py::test_only_kind_4_drops_a_bomb */
#define ENTITY_HAS_DROPPED      46u  /* .w — this entity has already dropped its bomb; set by
                                      * enemy_bomb_drop and cleared when the death path ends.
                                      * pinned by test_entity.py::test_a_bomber_drops_exactly_once */
#define ENTITY_HIDDEN_UNDER_BIGOBJ 48u /* .w — set while the entity lies inside the big object's box,
                                      * which suppresses its display record entirely.
                                      * pinned by test_entity.py::test_hide_test_box_edges */
#define ENTITY_SCRIPT_BASE      50u  /* .l — the movement script's base pointer (formation +32).
                                      * pinned by test_entity.py::test_move_steps_the_script_at_zero */
#define ENTITY_SCRIPT_CURSOR    54u  /* .l — byte offset into it, advanced by MOVE_SCRIPT_BYTES.
                                      * pinned by the same test */

/* The big object's parts reuse the two words above as their death offset; spelt as aliases so the
 * publisher that reads them says what it means without a fourth number for offset 24. */
#define ENTITY_PART_DEATH_DX ENTITY_AIM_CHANGED
#define ENTITY_PART_DEATH_DY ENTITY_FACING

/* The one ENTITY_KIND value any routine in this file tests: `cmpi.w #$4,44(a0)` @ 0x12f00/0x12f0a.
 * A dying entity of this kind drops one enemy bomb on its way down. */
#define ENTITY_KIND_BOMBER       4u

/* ================================================================================================
 * THE MOVEMENT SCRIPT — 8-byte records, read by entity_move @ 0x12f88.
 * ============================================================================================= */
#define MOVE_SCRIPT_DX           0u  /* .w -> ENTITY_DX */
#define MOVE_SCRIPT_DY           2u  /* .w -> ENTITY_DY */
#define MOVE_SCRIPT_DURATION     4u  /* .w -> ENTITY_STEP_COUNTDOWN */
#define MOVE_SCRIPT_FRAME        6u  /* .w -> ENTITY_FRAME_OFFSET */
#define MOVE_SCRIPT_BYTES        8u  /* `addi.l #$8,54(a0)` @ 0x12f88 */
/* The word that ends a script (`cmpi.w #$3e7,(a1)` @ 0x12f9a) — 999, the same sentinel the item
 * flight path and the enemy-bullet array use. All three are pinned separately. */
#define SCRIPT_TERMINATOR    0x3e7u

/* ================================================================================================
 * THE SLOT-POINTER TABLES — 0x19246..0x1946e, and the ONLY way any pass reaches a slot.
 *
 * Every table is an array of longword pointers into the arena. The 91 slots are covered exactly
 * once between them (measured off the loaded image), which is why a pass that walks all of these
 * walks the whole arena. `A_entity_group_t0`'s stride is 0x20 rather than 0x10 because each turret
 * group is followed by four DISPLAY-RECORD pointers for its barrel sprites, which the wave-2 turret
 * code owns.
 * ============================================================================================= */
#define A_entity_group_a0    0x19246u  /* 7 slots (0..6) */
#define A_entity_group_a1    0x19262u  /* 7 slots (7..13) */
#define A_entity_group_a2    0x1927eu  /* 7 slots (21..27) */
#define A_entity_group_a3    0x1929au  /* 7 slots (14..20) */
#define ENTITY_GROUP_A_SLOTS     7u
#define A_entity_group_t0    0x192b6u  /* 8 turret groups of 4, stride ENTITY_GROUP_T_STRIDE */
#define ENTITY_GROUP_T_STRIDE 0x20u
#define ENTITY_GROUP_T_COUNT     8u
#define A_entity_group_bigobj 0x193b6u /* 4 slots (64..67) */
#define A_entity_group_x0    0x193c6u  /* 5 groups of 4, stride ENTITY_GROUP_X_STRIDE */
#define ENTITY_GROUP_X_STRIDE 0x10u
#define ENTITY_GROUP_X_COUNT     5u
/* Three SINGLE-slot entries, not an array of four: 0x19416, 0x1941a and 0x1941e each hold one
 * pointer and are always dereferenced with `movea.l (a6),a0` — no post-increment. The third points
 * at arena slot 70, which is the address `entities_move_bigobj` reaches DIRECTLY with
 * `lea $5a960,a0` @ 0x12e78 instead of through the table. */
#define A_entity_group_pair  0x19416u
#define ENTITY_GROUP_PAIR_STRIDE 4u
#define ENTITY_GROUP_PAIR_COUNT  3u
#define A_entity_pair_slot_2 0x5a960u  /* == the pointer at A_entity_group_pair + 8 */
#define A_entity_group_a4    0x1945eu  /* 4 slots (28..31) */
#define ENTITY_GROUP_SLOTS       4u    /* the count every group but the a-groups and the pair has */
#define ENTITY_GROUP_PTR_BYTES   4u

/* ================================================================================================
 * THE ENEMY DESCRIPTORS — 25 records, 0x19534..0x197f8, one per enemy class.
 *
 * Variable length (26..38 bytes), so they are addressed by their own table of entry addresses
 * rather than by a stride. FROZEN like the record above and for the same reason: the spawn, weapons
 * and turret slices all read these fields, so the ten the disassembly establishes are written out
 * whole rather than added one at a time. Six of them have no reader in src/entity.c yet, which is
 * what their `names.txt, unpinned` tag says.
 * ============================================================================================= */
#define ENEMY_DESC_GROUP         0u  /* .l — the slot-pointer table above this class spawns into.
                                      * names.txt, unpinned */
#define ENEMY_DESC_BASE_FRAME    4u  /* .w -> ENTITY_BASE_FRAME. names.txt, unpinned */
#define ENEMY_DESC_ITEM_KIND     6u  /* .w -> ENTITY_ITEM_KIND. names.txt, unpinned */
#define ENEMY_DESC_FIRE_RELOAD   8u  /* .w -> ENTITY_FIRE_RELOAD; rewritten by
                                      * difficulty_apply_fire_rates. pinned by
                                      * test_entity.py::test_difficulty_writes_every_descriptor */
#define ENEMY_DESC_COUNT_MINUS_1 14u /* .w — slots in the formation, minus one. names.txt, unpinned */
#define ENEMY_DESC_HANDLER      16u  /* .w -> ENTITY_PATH_SELECT, and the index into both hit-handler
                                      * tables. names.txt, unpinned */
#define ENEMY_DESC_DEATH_DX     18u  /* .w — added to the published x while the entity is dying.
                                      * pinned by test_entity.py::test_publish_facing_dying_takes_the_death_offset */
#define ENEMY_DESC_DEATH_DY     20u  /* .w — ...and to the published y. Same pin. */
#define ENEMY_DESC_KIND         22u  /* .w -> ENTITY_KIND. names.txt, unpinned */
#define ENEMY_DESC_HIT_POINTS   24u  /* .w -> ENTITY_HIT_POINTS and (single spawns) ENTITY_ANIM_PERIOD.
                                      * pinned by test_entity.py::test_difficulty_writes_every_descriptor */

/* The descriptors a ported routine names. The first four are the 7-slot groups' classes; the rest
 * are what difficulty_apply_fire_rates @ 0x12cc8 rewrites and what the publishers pair a group
 * with. Only these 22 of the 25 have a caller here. */
#define A_enemy_desc_00      0x19534u
#define A_enemy_desc_01      0x19550u
#define A_enemy_desc_02      0x1956cu
#define A_enemy_desc_03      0x19588u
#define A_enemy_desc_04      0x195a4u
#define A_enemy_desc_05      0x195beu
#define A_enemy_desc_06      0x195d8u
#define A_enemy_desc_07      0x195f2u
#define A_enemy_desc_08      0x1960cu
#define A_enemy_desc_09      0x19626u
#define A_enemy_desc_0a      0x19640u
#define A_enemy_desc_0b      0x1965au
#define A_enemy_desc_10      0x196deu  /* the three A_entity_group_pair classes */
#define A_enemy_desc_11      0x19702u
#define A_enemy_desc_12      0x19726u
#define A_enemy_desc_13      0x19742u
#define A_enemy_desc_14      0x1975eu
#define A_enemy_desc_15      0x1977eu
#define A_enemy_desc_16      0x1979au
#define A_enemy_desc_17      0x197b6u
#define A_enemy_desc_18      0x197d2u

/* ================================================================================================
 * THE DEATH PATH TABLES, the animation frame ids, and the item arena.
 * ============================================================================================= */
/* Three longword pointers @ 0x19128, indexed by ENTITY_PATH_SELECT: 0x19210 (which is also
 * `player_death_frames`), 0x191fe and 0x19220. Each is a word table of sprite frames, ended by a
 * NEGATIVE word — `tst.w (a1) / bmi` @ 0x12ee6, so the test is on the sign and not on a sentinel. */
#define A_entity_path_tbl_ptrs 0x19128u
#define ENTITY_PATH_TABLES       3u
#define ENTITY_PATH_PTR_BYTES    4u

/* The six frame ids `anim_frame_ids_update` @ 0x119fc recomputes from A_frame_counter every frame.
 * Each is one byte, and the byte AFTER it opens the little table it is picked from — `lea $19519,a0
 * / adda.w d0,a0 / move.b (a0),$19518` is "read table[phase] into the id", with the table starting
 * one byte past the id itself. */
#define A_anim_frame_a       0x19518u  /* phase = frame_counter & 2 */
#define A_anim_frame_b       0x1951cu  /* phase = frame_counter & 2 */
#define A_anim_frame_item0   0x19520u  /* phase = frame_counter & 3 */
#define A_anim_frame_item1   0x19525u  /* phase = frame_counter & 3 */
#define A_anim_frame_item3   0x1952au  /* phase = frame_counter & 3 */
#define A_anim_frame_bomb    0x1952fu  /* phase = frame_counter & 2 */
#define ANIM_FRAME_TABLE_OFFSET 1u     /* the table starts one byte past the id it feeds */
#define ANIM_PHASE_MASK_2        2u    /* `andi.l #$2,d0` — 0 or 2, so a two-entry table read at
                                        * +0 and +2 with the odd byte between them unused */
#define ANIM_PHASE_MASK_3        3u    /* `andi.l #$3,d0` — a four-entry table */

/* The power-up items: 7 records of 10 bytes at 0x5ae9a..0x5aede. The last (A_player_bomb, the
 * player's own dropped bomb) belongs to the weapons slice and is not named here. */
#define A_item_weapon        0x5ae9au  /* raises weapon_level; walks the flight path */
#define A_item_life          0x5aea4u  /* raises lives; walks the flight path */
#define A_item_bomb          0x5aeaeu  /* raises bombs; falls straight down */
#define A_item_extra         0x5aeb8u  /* the 1000-point bonus; falls while its ITEM_CURSOR lasts */
#define ITEM_X                   0u  /* .w */
#define ITEM_Y                   2u  /* .w */
/* .l — a byte offset into A_item_flight_path for the two path items, and a FRAME COUNTDOWN for
 * A_item_extra (`subi.l #$1,4(a0)` @ 0x118c2, which retires the item when it goes negative). One
 * field, two readings, because the two item kinds never share a step routine. */
#define ITEM_CURSOR              4u
#define ITEM_ACTIVE              8u  /* .w */
#define ITEM_BYTES              10u

/* 4-byte (dx.w, dy.w) steps, ended by SCRIPT_TERMINATOR in the dx word; `item_path_step` rewinds to
 * the start rather than retiring the item, so the path loops for ever. */
#define A_item_flight_path   0x1b02au
#define ITEM_PATH_DX             0u
#define ITEM_PATH_DY             2u
#define ITEM_PATH_STEP_BYTES     4u

/* The three kinds `items_pickup_check` passes to the award arm in D6, and the caps it clamps to. */
#define ITEM_KIND_WEAPON         0u
#define ITEM_KIND_BOMB           1u
#define ITEM_KIND_LIFE           2u
/* THE THREE CAPS ARE NOT SPELT THE SAME WAY, and the difference is observable. Weapon level and
 * bombs are guarded by `beq` — the counter stops only when it is EXACTLY at its limit, so a value
 * above it (which the game never produces) would keep incrementing — while lives is guarded by a
 * signed `bgt`, so the settled value is one MORE than the number in the instruction. Each is named
 * for the comparison it is, not for the ceiling a reader would infer. */
#define WEAPON_LEVEL_FULL        4u  /* `cmpi.w #$4,$17714` + `beq` @ 0x11734 */
#define BOMBS_FULL               6u  /* `cmpi.w #$6,$17710` + `beq` @ 0x11748 */
#define LIVES_NO_AWARD_ABOVE     6u  /* `cmpi.w #$6,$17712` + `bgt` @ 0x1171e, so lives settle at 7 */

/* ================================================================================================
 * THE DISPLAY-LIST SUB-RANGES THE PUBLISHERS OWN.
 *
 * Each publisher writes a fixed run of consecutive 6-byte display records — one per slot of the
 * group it walks — and the runs are laid out as arithmetic progressions, which is why a base and a
 * stride replace the original's unrolled `lea`s. The two turret runs are NOT contiguous: the four
 * barrel-sprite records of groups t0..t3 sit between them (0x17894..0x178f4), which is where the
 * wave-2 turret code publishes.
 * ============================================================================================= */
#define A_dl_entity_t0       0x17834u  /* turret bodies t0..t3, ENTITY_GROUP_SLOTS records each */
#define A_dl_entity_t4       0x178f4u  /* ...and t4..t7 */
#define DL_GROUP4_STRIDE      0x18u    /* ENTITY_GROUP_SLOTS * DISPLAY_REC_BYTES */
#define DL_TURRET_RUN_GROUPS     4u    /* how many turret groups the first run holds */
#define A_dl_entity_pair     0x179b4u  /* the three single-slot pair objects, one record each */
#define A_dl_entity_bigobj   0x179eau  /* the big object's four parts */
#define A_dl_entity_x0       0x17a02u  /* the five facing groups, DL_GROUP4_STRIDE apart */
#define A_dl_entity_a0       0x17a7au  /* the four 7-slot groups, DL_GROUP7_STRIDE apart */
#define DL_GROUP7_STRIDE      0x2au    /* ENTITY_GROUP_A_SLOTS * DISPLAY_REC_BYTES */
#define A_dl_entity_a4       0x17b22u  /* A_entity_group_a4's four slots */
#define A_dl_item_0          0x17c24u  /* A_item_weapon */
#define A_dl_item_1          0x17c2au  /* A_item_life */
#define A_dl_item_2          0x17c30u  /* A_item_extra */
#define A_dl_item_3          0x1782eu  /* A_item_bomb — the one item record outside the run */

/* The three extra sprites `bigobj_extra_parts_publish` @ 0x102de stamps over the FRAME bytes of
 * A_dl_entity_bigobj's records 1..3 when the big object's first part carries the 999 marker. It
 * writes only those bytes: the positions are whatever entities_publish_bigobj_group left. */
#define BIGOBJ_EXTRA_PART_FRAME_0 0x4fu
#define BIGOBJ_EXTRA_PART_FRAME_1 0x4au
#define BIGOBJ_EXTRA_PART_FRAME_2 0x4bu
#define BIGOBJ_EXTRA_PARTS         3u
#define BIGOBJ_EXTRA_MARKER    0x3e7u  /* ENTITY_HIT_POINTS == 999 on part 0 arms the three */

/* The two boxes the big object is tested against, both 0x40 wide and offset by 0x0e. */
#define BIGOBJ_BOX_SIZE       0x40u   /* `addi.w #$40,d2` / `addi.w #$40,d3` @ 0x117c8/0x117d0 */
#define BIGOBJ_PROBE_OFFSET   0x0eu   /* `addi.w #$e,d0` — the probe point inside the entity */

/* ================================================================================================
 * ENTITY-OWNED GLOBALS.
 * ============================================================================================= */
#define A_frame_counter      0x17764u  /* .l — `addq.l #1,$17764` @ 0x11654, read only by
                                        * anim_frame_ids_update. Both ends are in this subsystem. */
#define A_item_pickup_pending 0x176c2u /* .w — set when a weapon power-up is on screen, so the level
                                        * script stops offering another. Written by
                                        * item_drop_if_formation_cleared and by the pickup award. */
#define A_enemy_bomb_slot_scan 0x1776cu /* .w — enemy_bomb_drop's scan cursor over the first
                                        * ENEMY_BOMB_SLOTS display records; 0x12f2e is its only
                                        * reader or writer. */
#define ENEMY_BOMB_SLOTS        16u    /* `cmpi.w #$10,$1776c` — the first 16 display records */
#define ENEMY_BOMB_DY            2u    /* `addi.w #$2,2(a0)` @ 0x11858 */
#define ENTITY_RETIRE_Y      0xc8u     /* `cmpi.w #$c8,2(a0)`: at or past row 200 an enemy bomb or a
                                        * falling item leaves the screen and is retired */

/* ================================================================================================
 * NOTHING IS ON LOAN HERE ANY MORE.
 *
 * This header carried four globals it did not own while their subsystems were unported:
 * `PLAYER_X`, `PLAYER_Y` and `PLAYER_FRAME` went home to `include/player.h` and `A_weapon_level` to
 * `include/weapons.h` when those landed, and STATUS.md's "Borrowed globals" lost their rows in the
 * same change. `src/entity.c` includes both headers and reads the names out of them, which is what
 * `test_constants.py::test_no_constant_is_defined_in_two_files` leaves as the only option.
 *
 * The display list, the sprite record's hit box and the player record are likewise NOT here — they
 * live in `include/display_list.h`, `include/sprite.h` and `include/player.h`.
 * ============================================================================================= */

/* ================================================================================================
 * THE CORES (src/entity.c). Every `g_*` glue takes the original's registers; the one-line comment
 * above each maps register -> role.
 * ============================================================================================= */
void count_game_frame(uint8_t *image);
void anim_frame_ids_update(uint8_t *image);

void entity_move(uint8_t *image, uint32_t entity);
void entities_move_group4(uint8_t *image, uint32_t group);
void entities_move_one_group(uint8_t *image, uint32_t group);
void entities_move_groups_extra(uint8_t *image);
void entities_move_bigobj(uint8_t *image);
void entities_move_bigobj_parts(uint8_t *image);
void entities_move_all(uint8_t *image);
void enemy_bomb_drop(uint8_t *image, uint32_t entity, uint16_t x, uint16_t y);
void enemy_bombs_move(uint8_t *image);

void entity_publish_group_facing(uint8_t *image, uint32_t group, uint32_t records, uint32_t desc);
void entity_publish_group_a4(uint8_t *image);
void entity_publish_group_plain(uint8_t *image, uint32_t group, uint32_t records);
void entity_publish_anim(uint8_t *image, uint32_t group, uint32_t records, uint32_t desc);
void entity_publish_group_offset(uint8_t *image, uint32_t group, uint32_t records);
void entity_publish_group_last(uint8_t *image, uint32_t group, uint32_t records, uint32_t desc);
void entities_publish_facing_groups(uint8_t *image);
void entities_publish_bigobj_group(uint8_t *image);
void entities_publish_plain_groups(uint8_t *image);
void entities_publish_anim_groups(uint8_t *image);
void entities_publish_last_groups(uint8_t *image);
void entities_publish_all(uint8_t *image);
void bigobj_extra_parts_publish(uint8_t *image);

void entity_hide_test(uint8_t *image, uint32_t entity);
void entity_hide_under_bigobj_group(uint8_t *image, uint32_t group);
void entity_hide_under_bigobj(uint8_t *image);
void bigobj_depth_test(uint8_t *image, uint32_t entity, uint32_t group);
void bigobj_overlap_depth_update(uint8_t *image);

void item_fall_step(uint8_t *image, uint32_t item);
void item_drop_step(uint8_t *image, uint32_t item);
void item_path_step(uint8_t *image, uint32_t item);
void items_move_all(uint8_t *image);
void items_publish(uint8_t *image);
void sprite_hitbox_test(uint8_t *image, uint32_t item, uint16_t kind);
void items_pickup_check(uint8_t *image);
void item_pickup_award(uint8_t *image, uint16_t kind);
unsigned item_drop_if_formation_cleared(uint8_t *image, uint32_t group, uint16_t x, uint16_t y,
                                        uint16_t kind, unsigned extend_in);
void difficulty_apply_fire_rates(uint8_t *image);

#endif /* FS_ENTITY_H */
