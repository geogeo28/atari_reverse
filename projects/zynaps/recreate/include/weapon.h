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
 * and clears it when it retires. Each holds the ENTITY INDEX its missile is chasing (or
 * MISSILE_NO_TARGET), which is how `missile_acquire_target` refuses a target the other missile has
 * already taken. `A_missile_lock_a` is a `# ctx` NAME (../names.txt also reads 0x19918 as
 * `shot_slot_busy`); the body reads here confirm the lock-slot role for both bytes. */
#define A_missile_lock_a 0x19918u
#define A_missile_lock_b 0x19919u
/* The entity index the gunsight is sitting over, 0 = none. `fire_seeker` copies it into the new
 * seeker; with no lock the seeker keeps whatever index its caller handed over in D6. A `# ctx` NAME
 * in ../names.txt, which also reads 0x19917 as `drone_locked_target` — the address is confirmed,
 * the spelling is a proposal a later body read may overturn. */
#define A_seeker_lock_target_index 0x19917u
/* One counter per weapon kind, decremented on every launch. All three are `# ctx` NAMES in
 * ../names.txt (`missile_launch_counter` / `bomb_launch_counter` / `seeker_launch_counter`) and
 * none is in ../out/globals.tsv, so the role is read off the three launchers and nothing else pins
 * it. They are named HERE, unlike the panel bytes of the same block (`selected_weapon` 0x198b4 and
 * `power_gauge_display` 0x198c3, which STATUS.md defers): those two ../out/globals.tsv assigns to
 * `hud`, and a global goes in its OWNER's header. These three have no assigned owner, and the
 * house rule for that case is that whoever reads it names it. */
#define A_missile_launch_counter 0x198b5u
#define A_bomb_launch_counter 0x198b6u
#define A_seeker_launch_counter 0x198b8u

/* ================================================================================================
 * Record fields and geometry.
 * ============================================================================================= */
/* THE STEERED-SHOT BLOCK, record bytes +0x1a..+0x1f.
 *
 * include/entity.h's frozen block stops naming roles at +0x1a: it carries +0x1a as `ENTITY_HP` and
 * +0x1b as `ENTITY_BOUNCE` — the enemy's and the bomb's uses of those same bytes — and does not
 * carry +0x1c/+0x1d/+0x1e/+0x1f at all. Past +0x1a the record is a UNION (entity.h says so on
 * ENTITY_TYPE), so the seeker's and the missile's roles are named here as weapon-local offsets
 * rather than restated there. ../names.txt's comment on 0x17a8e is the provenance for all six.
 *
 * TWO NAMES FOR +0x1a IS THE UNION, NOT AN OVERSIGHT: a seeker and a missile hold an entity index
 * there, a bomb holds its remaining bounce count, and each reader says which it means. Only the
 * `A_*` address family is held to one name (test_constants.py) precisely because a record offset
 * carries no such claim. */
#define SHOT_TARGET_INDEX 0x1au    /* .b — seeker/missile: the entity index being chased
                                    * (entity.h calls this byte ENTITY_HP) */
#define SHOT_BOUNCES_LEFT 0x1au    /* .b — bomb: how many terrain bounces are left */
/* .b — frames until the heading may turn again. THE SAME BYTE has two other names in this tree, one
 * per role: entity.h's ENTITY_BOUNCE is the bomb's one-frame terrain latch — which is why
 * `bomb_update` in src/weapon.c reads +0x1b under THAT name and `entity_steer_toward_target` under
 * this one — and enemy.h's ACTOR_FIRE_COUNTDOWN is the script VM's. */
#define SHOT_TURN_COUNTDOWN 0x1bu
#define SHOT_TURN_PERIOD 0x1cu     /* .b — what the countdown reloads with */
#define SHOT_HEADING 0x1du         /* .b — 0..0x3f; `shot_set_sprite_a` picks the sprite from it */
#define SHOT_SPEED 0x1eu           /* .b — signed, multiplied into the velocity pair */
#define SHOT_MAX_TURN 0x1fu        /* .b — the most the heading may move in one turn */
/* The 6-bit compass mask the heading is wrapped with lives at function scope in src/weapon.c, with
 * `heading_step`, its only reader. */
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
 * Launching a shot: what `fire_seeker`, `fire_homing_missile` and `fire_bomb` write into the slot.
 * ============================================================================================= */
/* The seeker and the missile are armed by the SAME twelve stores (`arm_steered_shot` in
 * src/weapon.c) and draw the SAME sprite; only the type, the speed and the time-to-live differ. */
#define A_shot_sprite_steered 0x6421eu
#define SHOT_ARM_ROWS 0x0bu          /* `move.w #$b,8(a2)` — ENTITY_HEIGHT for both */
#define SHOT_ARM_TURN_PERIOD 1u      /* both turn every frame */
#define SHOT_ARM_MAX_TURN 2u         /* ...by at most two of the 64 headings */
#define SEEKER_SPEED 4u
#define SEEKER_TTL 0x4bu             /* `move.b #$4b,32(a2)` — ENTITY_ANIM_FRAME's other role */
#define MISSILE_SPEED 5u
#define MISSILE_TTL 0x64u

/* The bomb is armed in line instead: it steers by gravity rather than by heading, so it writes the
 * acceleration pair and no turn block at all. */
#define A_bomb_sprite 0x6a11eu
#define BOMB_ROWS 8u
#define BOMB_LAUNCH_DX 0x200u        /* `move.w #$200,18(a2)` — thrown forward, never turned */
#define BOMB_GRAVITY_AY 0x40u        /* `move.w #$40,24(a2)` — ENTITY_AY, added every frame */
#define BOMB_BOUNCES 3u
/* `cmpi.w #$ac,4(a2)` + `bge` — at or below it, the bomb dies. NO `u` SUFFIX, UNLIKE ITS SIBLINGS,
 * and that is load-bearing rather than an oversight: `bge` is signed, and its reader compares
 * `(int16_t)…y >= BOMB_FLOOR_Y`. Made unsigned, the promotion would flip the comparison and a bomb
 * driven above the top of the playfield (y's high word past 0x8000) would be retired on the spot.
 * `test_bomb_floor_is_a_signed_word_compare` drives both sides of that edge. */
#define BOMB_FLOOR_Y 0xac
/* D1 into `entity_apply_accel` is `1u << ACCEL_BIT_Y_ADD` — util.h owns that bit NUMBER, so the
 * mask is built from it at the call site rather than spelt here as a literal 0x20 that nothing
 * could pin equal. Gravity is added to ENTITY_DY and ENTITY_DX is left where the launch put it. */

/* The sound each launch (and the bomb's bounce) starts, as D1 into `sound_start`. */
#define SFX_BOMB_BOUNCE 0x11u
#define SFX_BOMB_LAUNCH 0x18u
#define SFX_SEEKER_LAUNCH 0x1au

/* ================================================================================================
 * Entity indices and types the targeting code names.
 * ============================================================================================= */
#define ENTITY_INDEX_SHIP 0x11u          /* slot 17 — the LIVE ship record, not the shadow */
#define ENTITY_INDEX_TRAIL_DRONE 0x13u   /* slot 19 = A_entity_gunsight */
#define TYPE_TRAIL_DRONE 0x35u           /* what the gunsight record must hold to be steered at */
/* Entity index 20 — one PAST the 20-record table, so it names no record: the missile's "no target
 * yet". It is what `fire_homing_missile` writes and what the acquire scan gives up with. */
#define MISSILE_NO_TARGET 0x14u
/* The scan runs the eight wave-enemy slots, 9..16: it resumes at `MISSILE_SCAN_FIRST` + 1 and stops
 * the moment the counter reaches the ship's own slot. Numerically that end IS ENTITY_INDEX_SHIP;
 * it is spelt separately because the instruction is a scan bound, not a reference to the ship. */
#define MISSILE_SCAN_FIRST 0x08u
#define MISSILE_SCAN_END 0x11u

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
void entity_steer_toward_target(uint8_t *image, uint32_t entity);
void fire_seeker(uint8_t *image, uint32_t shot, uint8_t fallback_target, uint8_t sound_channel);
void fire_homing_missile(uint8_t *image, uint32_t shot);
void fire_bomb(uint8_t *image, uint32_t shot, uint8_t sound_channel);
void seeker_update(uint8_t *image, uint32_t shot);
void homing_missile_update(uint8_t *image, uint32_t shot);
void bomb_update(uint8_t *image, uint32_t bomb, uint8_t sound_channel);

#endif /* ZYNAPS_WEAPON_H */
