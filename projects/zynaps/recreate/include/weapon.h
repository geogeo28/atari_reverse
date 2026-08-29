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
 * it. They are named HERE because ../out/globals.tsv gives them no owner and the house rule for
 * that case is that whoever reads it names it — the same rule that puts `selected_weapon` (0x198b4)
 * below. `power_gauge_display` (0x198c3) is the neighbouring byte that is NOT here: globals.tsv
 * assigns it to `hud`, so this file includes include/hud.h to write it. */
#define A_missile_launch_counter 0x198b5u
#define A_bomb_launch_counter 0x198b6u
#define A_seeker_launch_counter 0x198b8u
/* Which of the four launchers the fire button runs, 1..4 (`cmpi.b #$4/#$2/#$1/#$3,$198b4` in the
 * fire dispatcher at 0x113d0..0x115f4). `../out/globals.tsv` gives it NO owner, so the house rule
 * that applies is the three counters' above: whoever reads it names it, and the three arms of the
 * activate table that write it are this file's. */
#define A_selected_weapon 0x198b4u
/* `bset #0,$198c4` when the ship is destroyed. `../out/globals.tsv` files it under `dead` — written
 * and never read — which is not a subsystem and owns no header, so it is named here beside its one
 * writer. The section-restart prologue (src/init.c) clears it and includes this header for it. */
#define A_death_event_flags 0x198c4u

/* ---- BORROWED: four player globals with no home yet -------------------------------------------
 *
 * ../out/globals.tsv puts all four in the **player** subsystem and `include/player.h` spells none
 * of them (its comment on `A_weapon_decay_timer` says so explicitly for the first of the three
 * timers). They are named here so `powerup_capsule_collected` and `ship_resolve_entity_hits` can
 * read them; STATUS.md's "## Borrowed globals" carries the debt, and deleting these four lines and
 * repointing the includes is the whole of the migration. */
#define A_shield_level 0x1990au        /* .b — the 0..3 gauge `A_power_gauge_display` mirrors */
#define A_speed_decay_timer 0x19dc8u   /* .w — the twin of player.h's A_weapon_decay_timer */
#define A_shield_decay_timer 0x19dcau  /* .w — ...and the third of the three */
#define A_ship_invulnerable 0x19912u   /* .b — non-zero suppresses every ship-death path */

/* ================================================================================================
 * The power-up bar.
 *
 * `powerup_capsule_collected` steps a cursor over five icons while the fire button is NOT charged,
 * and commits the icon under it when it is. The commit dispatches through one of two jump tables —
 * a NEW selection through the activate table, the SAME selection again through the upgrade table —
 * and both are read out of the image, so the reconstruction resolves the longword and maps it back
 * to the C arm (src/weapon.c, POWERUP_ARMS), exactly as `enemies_animate_all` does.
 * ============================================================================================= */
#define A_powerup_activate_jumptable 0x19348u  /* names.txt # ctx — the committed slot is NEW */
#define A_powerup_upgrade_jumptable 0x1935cu   /* names.txt # ctx — it is the one already active */
#define POWERUP_CURSOR_SLOTS 5u        /* `cmpi.b #$5,$19905` + wrap to 0 */
/* Cursor 0 never reaches a table at all: `tst.b d0` / `bne` takes it to the speed arm first. */
#define POWERUP_CURSOR_SPEED 0u
/* ...and cursor 1 is diverted to the WEAPON-POWER arm after the sound and before the activate
 * table is indexed (`cmp.b #$1,d0` / `beq`), which is what makes `powerup_slot1_activate` — the
 * table's own entry 1 — unreachable from the game. */
#define POWERUP_CURSOR_WEAPON_POWER 1u
#define SFX_POWERUP_COMMIT 0x0fu       /* `moveq #$f,d1` before both `sound_start` calls */

/* The ceilings the three level arms clamp at, each spelt as the instruction that tests it. The
 * speed one is an EQUALITY test on the incremented byte and the other two are signed `ble`s, so a
 * level already above its ceiling behaves differently in the three: speed walks on past 2, while
 * the other two are pulled back. */
#define SHIP_SPEED_LEVEL_OVERFLOW 2u   /* `cmpi.b #$2` + `bne` past the write-back */
#define SHIP_SPEED_LEVEL_MAX 1u        /* `move.b #$1,$19907` */
#define WEAPON_POWER_LEVEL_MAX 4u      /* `cmpi.b #$4` + `ble` */
#define SHIELD_LEVEL_MAX 3u            /* `cmpi.b #$3` + `ble` */

/* The four values `A_selected_weapon` can hold, as the fire dispatcher reads them. Kind 3 — the
 * plain bullet — is the per-life default and no power-up arm selects it. */
#define WEAPON_KIND_BOMB 1u
#define WEAPON_KIND_MISSILE 2u
#define WEAPON_KIND_SEEKER 4u

/* ================================================================================================
 * The ship's own collision pass.
 * ============================================================================================= */
/* Entity slots 6..17, the twelve `ship_resolve_entity_hits` scans: THREE enemy-shot slots (6..8,
 * `A_enemy_shot_slots` in include/enemy.h), the EIGHT wave enemies (9..16), and the ship's own LIVE
 * record (17, `A_player_record`). It stops one short of the SHADOW record at slot 18 and two short
 * of the gunsight at 19 — a scan of thirteen would resolve the ship against its own shadow every
 * frame. ../names.txt's comment on 0x11906 is the provenance for the 3 + 8 split. */
#define SHIP_HIT_SCAN_FIRST 6u
#define SHIP_HIT_SCAN_SLOTS 12u        /* `move.w #$b,d7` + `dbf` */
#define TYPE_POWERUP_CAPSULE 0x11u     /* `cmpi.b #$11,17(a4)` */
#define SFX_POWERUP_CAPSULE 0x16u      /* `moveq #$16,d1` once the capsule is taken */
#define SHIP_DEATH_EXPLOSION_GROUP 1u  /* `move.w #$1,d2` into `explosion_spawn` */
#define DEATH_EVENT_BIT_SHIP 0u        /* `bset #0,$198c4` */
/* A2 IS AN INPUT THE ROUTINE NEVER TOUCHES: it walks A4 and hands A2 straight to `explosion_spawn`
 * as the record to blow apart. Both call sites (0x11e84 and 0x11ed0) load `A_player_record` there,
 * so the ship explodes at its own position however far up the scan the lethal record sits — and
 * that is why the C takes it as a parameter rather than reading the global. */

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
void powerup_capsule_collected(uint8_t *image);
void ship_resolve_entity_hits(uint8_t *image, uint32_t ship, uint32_t hit_mask_row);
void shot_to_puff(uint8_t *image, uint32_t shot);
/* WHAT A CALL SITE PASSES WHEN NOTHING DOWNSTREAM READS THE FLAG BACK.
 *
 * `extend_in` below only ever decides the value the EARLY arm RETURNS — the arm that makes no
 * decrement and so leaves the caller's X where it was. A call site that discards the return value
 * therefore cannot observe the argument at all, and this name says so out loud rather than leaving
 * a bare 0 that reads like a claim about the machine. The sites are `src/weapon.c`'s two bomb
 * retires and `src/frame.c`'s three outside the two hit passes; the passes themselves thread a real
 * flag, because there the return IS read.
 */
#define EXTEND_UNREAD 0u

/* THE THREE RETIRE ROUTINES ANSWER IN THE 68000's X FLAG as well as in memory, and the frame loop's
 * scoring paths read it: each ends on `subi.b #$1` of its own live-shot counter, whose BORROW is the
 * carry-in of the next `abcd` in `score_add_bcd` (src/score.c states the whole argument). The two
 * with a guard take `extend_in` so that their EARLY arm — which makes no decrement and therefore
 * leaves the flag alone — can hand the caller's own X straight back; `_kind36` has no guard and so
 * needs none. */
unsigned shot_retire_kind32(uint8_t *image, uint32_t shot, unsigned extend_in);
unsigned shot_retire_kind33(uint8_t *image, uint32_t shot, unsigned extend_in);
unsigned shot_retire_kind36(uint8_t *image, uint32_t shot);
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
