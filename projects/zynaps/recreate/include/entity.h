/* entity.h — the entity record, and the entity housekeeping in src/entity.c.
 *
 * ../../names.txt's `entity_table` (0x17a8e) is 20 of these records; `entity_boss_parts` (0x18142)
 * holds more. The layout below is a TRANSCRIPTION of names.txt's comment on 0x17a8e (plus the
 * velocity pair from its comment on 0x142d4) — the naming pass recovered the whole record from
 * full-body reads, so it is written out once here as a FROZEN block rather than grown field by
 * field. Freezing it is what lets several agents port entity routines at the same time: nobody has
 * to add a field, so nobody edits this block, and the field a routine needs is already named.
 *
 * EVERY FIELD CARRIES ITS PROVENANCE, because "named" and "held by a test" are different claims and
 * a reader porting the next routine needs to know which one they are getting. `pinned by <test>`
 * means a differential case would fail if the offset were wrong; `names.txt, unpinned` means it is
 * a read, believed but unexercised — confirm it against the disassembly before you lean on it, and
 * upgrade the tag in the change that ports a routine using it.
 *
 * Reading a global another subsystem owns is done by including ITS header; see README.md,
 * "Adding a function".
 */
#ifndef ZYNAPS_ENTITY_H
#define ZYNAPS_ENTITY_H

#include <stdint.h>

/* ================================================================================================
 * THE RECORD — frozen. names.txt 0x17a8e: "20 records x 0x2c".
 * ============================================================================================= */
/* pinned by test_enemy.py::test_alloc_finds_the_first_free_slot (the one free record at each of
 * eight positions, the returned pointer compared against the oracle's own A2 — a wrong stride
 * returns a wrong address, not merely a wrong count), test_weapon.py::test_player_shot_update_all_at_every_slot
 * (`lea 44(a2),a2`) and test_collision.py::test_unexplained_hit_at_every_index (`mulu.w #$2c,d0`). */
#define ENTITY_STRIDE      0x2cu

#define ENTITY_X           0x00u  /* .w signed — playfield x (entity_apply_velocity @ 0x14306 adds a LONGWORD
                                   * at +0, so the .w is the game's view, not the field's width).
                                   * pinned by test_entity.py, test_util.py */
#define ENTITY_Y           0x04u  /* .w signed — playfield y (same longword add at +4).
                                   * pinned by test_entity.py, test_util.py */
/* .w — sprite rows in bits 0..14; bit 15 is a FLAG the weapon code owns (include/weapon.h's
 * SHOT_LOCK_SLOT_B), which is why every reader of the count masks with collision.h's
 * ENTITY_HEIGHT_MASK — every reader except draw_sprite_masked (0x15ace), which feeds the raw word
 * to its dbf (an unreachable arm, see STATUS.md). Offset pinned by
 * test_mothership.py::test_place_tail_attribution and test_sprite.py (draw_sprite_masked); the mask
 * by test_collision.py::test_height_is_masked_and_wraps and test_weapon.py::test_shot_retire_kind32 */
#define ENTITY_HEIGHT      0x08u
#define ENTITY_SPRITE      0x0au  /* .l — pointer to the sprite bank. pinned by
                                   * test_enemy.py::test_anim_cycle_frames, test_weapon.py::test_shot_to_puff,
                                   * test_sprite.py (draw_sprite_masked) */
/* .b — alive / animation state, bit 7 = exploding. PINNED BY test_entity.py, and its NEIGHBOUR
 * matters: entity_kill_if_offscreen reads the two as one word (`tst.w 14(a2)`) and clears only this
 * byte (`clr.b 14(a2)`). See src/entity.c. */
#define ENTITY_ALIVE       0x0eu
/* .b — set by the blit at 0x15b7c when the sprite overlapped background pixels.
 * pinned by test_collision.py::test_unexplained_hit_at_every_index, which is the first case to read
 * it AS ITS OWN BYTE: collision_chain_walk branches on `tst.b 15(a0)`, that case is the one that
 * SETS the flag (every other byte of the record staying 0), and it drives all twenty indexes — so a
 * wrong offset reads a zero and answers "no hit". The offset no longer rides on ENTITY_ALIVE's word
 * read the way it did when this said "unpinned". Also pinned by
 * test_weapon.py::test_bomb_bounces_only_off_the_landscape, which drives the flag against the
 * bomb's own overlap row — the pair that decides whether a hit was the LANDSCAPE. */
#define ENTITY_PIXEL_HIT   0x0fu
#define ENTITY_TYPE        0x11u  /* .b — class id; entity_type_in_mask (0x13bc2) indexes it into the
                                   * 14-byte class bitmaps at 0x19164 / 0x19172 / 0x19180 (src/enemy.c) —
                                   * no caller bounds the type. Past +0x1a the record is a UNION:
                                   * +0x1b is also the script VM's fire countdown and +0x21 an
                                   * asteroid speed flag (second roles named in enemy.h / src/enemy.c).
                                   * pinned by test_enemy.py::test_ground_skips_dead_and_wrong_type and
                                   * test_collision.py::test_class_range_bounds */
#define ENTITY_DX          0x12u  /* .w — cos64[angle]*speed (0x142d4). pinned by
                                   * test_enemy.py::test_op_halt_zeroes_both_velocity_words */
#define ENTITY_DY          0x14u  /* .w — sin64[angle]*speed (0x142d4). pinned by the same test */
#define ENTITY_AX          0x16u  /* .w — acceleration, added to / subtracted from ENTITY_DX by
                                   * entity_apply_accel (0x143f8). pinned by test_util.py and by
                                   * test_weapon.py::test_fire_bomb, which is the launch that
                                   * CLEARS it while setting ENTITY_AY to the bomb's gravity */
#define ENTITY_AY          0x18u  /* .w — the same for ENTITY_DY. pinned by test_util.py and
                                   * test_weapon.py::test_fire_bomb */
/* .b — hit points to an enemy; to a seeker or a homing missile the ENTITY INDEX it is chasing, and
 * to a bomb its remaining bounce count (both named in include/weapon.h, which is where this union's
 * weapon-side roles live).
 *
 * THE OFFSET is pinned, the "hit points" READING is not. No C reads this name yet — the routines
 * that use the byte read it under weapon.h's SHOT_TARGET_INDEX / SHOT_BOUNCES_LEFT — so what holds
 * it is test_weapon.py's `MIRRORS`, which pins THIS constant equal to those, plus
 * test_steer_resolves_the_target_index_as_a_byte, which drives ten indices from 0 to 0xff through
 * the record arithmetic and so lands on a different record for each. A wrong offset here now fails
 * the suite by name; the hit-points role remains names.txt's and unexercised. The enemy side pins
 * the offset too: the type-14 sine patroller uses this byte's WORD as its centre line (enemy.h's
 * ACTOR_SINE_BASE_Y) and test_enemy.py::test_sine_height_is_added_to_the_base fails if it moves. */
#define ENTITY_HP          0x1au
/* .b — a bomb's one-frame "was on the terrain last frame" latch (read under THIS name by
 * `bomb_update`), the steered shot's turn countdown (weapon.h's SHOT_TURN_COUNTDOWN, same byte),
 * and the script VM's fire countdown (enemy.h's ACTOR_FIRE_COUNTDOWN). See ENTITY_TYPE's union note.
 *
 * The OFFSET and the LATCH role are pinned by test_weapon.py::test_bomb_latch_and_bounce_count,
 * whose 4x6 grid separates the latch from the bounce COUNT in the byte beside it, and by that
 * battery's `MIRRORS` pin against SHOT_TURN_COUNTDOWN. The fire-countdown role is names.txt's and
 * unexercised — script class 2 (0x14d00) is not ported. */
#define ENTITY_BOUNCE      0x1bu
/* .b — the animation frame (enemies), the hit flash's frame counter, and ALSO the seeker's and the
 * missile's time-to-live (0x4b and 0x64, counted down by 0x140a6 / 0x14126). The roles never share
 * a record: a shot only becomes a flash once it is spent.
 * pinned by test_enemy.py::test_anim_cycle_frames, test_weapon.py::test_every_puff_frame, and — for
 * the time-to-live role — test_weapon.py::test_seeker_time_to_live and
 * test_weapon.py::test_missile_time_to_live_releases_its_own_lock */
#define ENTITY_ANIM_FRAME  0x20u
#define ENTITY_SQUADRON    0x21u  /* .b — squadron id. pinned by
                                   * test_enemy.py::test_despawn_credits_the_squadron */

/* ================================================================================================
 * Prototypes.
 * ============================================================================================= */
void entity_kill_if_offscreen(uint8_t *image, uint32_t entity);

#endif /* ZYNAPS_ENTITY_H */
