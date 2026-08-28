/* weapon.h — the player's shots: their records, their tables, and the routines in src/weapon.c.
 * Subsystem: weapon.
 *
 * Names and addresses are ../../names.txt's; see README.md, "Adding a function".
 */
#ifndef ZYNAPS_WEAPON_H
#define ZYNAPS_WEAPON_H

#include <stdint.h>

/* ================================================================================================
 * The globals this subsystem owns (../out/globals.tsv).
 * ============================================================================================= */
/* Entity slot 19: the seeker's targeting reticle, type 0x35 — the "trail drone". */
#define A_entity_gunsight 0x17dd2u
/* Bit tables in the same family as collision.h's, read the same way (`type_class_bit_set`). */
#define A_type_mask_missile_target 0x1918eu
#define A_type_seeker_lockable_bits 0x191acu
/* One byte per heading, mapping a shot's SHOT_HEADING to the sprite variant that draws it. */
#define A_shot_variant_table 0x18f7cu
/* Sprite pointers indexed by that variant, one long each. */
#define A_shot_sprite_ptrs_a 0x192acu
/* The four hit-flash frames, one long each. */
#define A_puff_frame_ptrs 0x192fcu
/* Non-zero while the trail drone is out. */
#define A_trail_drone_active 0x19900u
/* Live-shot counts, one per kind; every retire path decrements the matching one. */
#define A_active_count_type32 0x1990bu
#define A_active_count_bombs 0x1990cu
#define A_active_count_seekers 0x1990du
/* The two homing-missile lock slots. A missile owns one of them, named by SHOT_LOCK_SLOT_B below,
 * and clears it when it retires. */
#define A_missile_lock_a 0x19918u
#define A_missile_lock_b 0x19919u
/* HALF-RATE GATE, and NOT this subsystem's by ../out/globals.tsv, which assigns 0x198c5 to
 * `sprite`. It is defined here because include/sprite.h does not carry it and shot_anim_puff needs
 * it; move it there — one address, one home — as soon as a sprite routine reads it too. */

/* ================================================================================================
 * Record fields and geometry.
 * ============================================================================================= */
/* Field 0x1d — the shot's HEADING, 0..0x3f, which `entity_steer_toward_target` @ 0x141d6 turns and
 * `shot_set_sprite_a` reads. include/entity.h's frozen block does not carry it (nor 0x1b/0x1c/0x1e/
 * 0x1f, the turn countdown, its reload, the speed and the maximum turn per tick), so it is named
 * here as a weapon-local offset. */
#define SHOT_HEADING 0x1du
/* Bit 15 of ENTITY_HEIGHT: which of the two lock slots above this missile owns. Set by
 * `fire_homing_missile` @ 0x1401a (`bset #7,8(a2)`, the field's high byte) and read back by
 * `shot_retire_kind32` as the word's sign. collision.h's ENTITY_HEIGHT_MASK is its complement. */
#define SHOT_LOCK_SLOT_B 0x8000u

/* The six entity slots at the bottom of the table that hold the player's shots. */
#define PLAYER_SHOT_SLOTS 6u

/* The kinds a shot record can carry in ENTITY_TYPE. */
#define SHOT_TYPE_MISSILE 0x32u
#define SHOT_TYPE_BOMB 0x33u
#define SHOT_TYPE_SEEKER 0x36u
#define SHOT_TYPE_PUFF 0x37u

/* The hit flash a spent shot becomes: `shot_to_puff` rewrites the record into these. */
#define A_puff_sprite 0x6791eu
#define PUFF_Y_LIFT 3u        /* `subi.w #$3,4(a2)` — the flash sits three rows above the shot */
#define PUFF_ROWS 0x10u
#define PUFF_FIRST_FRAME 1u
#define PUFF_DEATH_FRAME 5u   /* `cmpi.b #$5,32(a2)` — frames 1..4 draw, then the record dies */
#define PUFF_FRAME_INDEX_MASK 0xfu  /* `and.l #$f` on the frame before it indexes the pointers */
#define SPRITE_PTR_BYTES 4u   /* `lsl.w #2` / `lsl.l #2` — one long per sprite-table entry */

/* ================================================================================================
 * Prototypes.
 * ============================================================================================= */
int entity_type_is_lockable(const uint8_t *image, uint32_t entity);
int entity_type_is_missile_target(const uint8_t *image, uint32_t entity);
void entity_pos_from_ship(uint8_t *image, uint32_t entity);
void powerup_slot1_activate(uint8_t *image);
void powerup_downgrade_on_death(uint8_t *image);
void shot_to_puff(uint8_t *image, uint32_t shot);
void shot_retire_kind32(uint8_t *image, uint32_t shot);
void shot_retire_kind33(uint8_t *image, uint32_t shot);
void shot_retire_kind36(uint8_t *image, uint32_t shot);
void shot_set_sprite_a(uint8_t *image, uint32_t shot);
void shot_anim_puff(uint8_t *image, uint32_t shot);
void player_shot_update_all(uint8_t *image);
void player_shots_clear(uint8_t *image);

#endif /* ZYNAPS_WEAPON_H */
