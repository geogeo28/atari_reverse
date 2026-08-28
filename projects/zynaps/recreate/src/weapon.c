/* weapon.c — the player's shots: what a spent one becomes, how the live ones are animated, and the
 * two type-class tests the targeting code asks.
 *
 * Entity slots 0..5 hold the player's shots (include/entity.h). A shot leaves play by being
 * rewritten in place as the four-frame hit flash — `shot_to_puff` — which is why every "retire"
 * here is a conversion rather than a kill, and why the three kind-specific retires differ only in
 * which live-shot count they decrement and what they release first.
 */
#include "machine.h"
#include "entity.h"
#include "weapon.h"
#include "collision.h"
#include "player.h"
#include "enemy.h"

/* ================================================================================================
 * The two type-class tests. Same probe as collision.c's pair — see the comment there for how the
 * bit tables are laid out and why the answer is the Z flag rather than a register.
 * ============================================================================================= */
/* entity_type_is_lockable @ 0x13d3e — a2 = the record. Can the drone lock this as a seeker target? */
int entity_type_is_lockable(const uint8_t *image, uint32_t entity) {
    return entity_type_in_class(image, entity, A_type_seeker_lockable_bits, TYPE_TARGETABLE_MAX);
}

/* entity_type_is_missile_target @ 0x140f6 — a1 = the record. Can a homing missile lock it? */
int entity_type_is_missile_target(const uint8_t *image, uint32_t entity) {
    return entity_type_in_class(image, entity, A_type_mask_missile_target, TYPE_TARGETABLE_MAX);
}

/* ================================================================================================
 * Spawning and the power-up levels.
 * ============================================================================================= */
/* entity_pos_from_ship @ 0x14092 — a2 = the entity. Every player weapon starts where the ship's
 * shadow record last drew, not where the live record now is. */
void entity_pos_from_ship(uint8_t *image, uint32_t entity) {
    wr16(image + entity + ENTITY_X, be16(image + A_ship_record_shadow + ENTITY_X));
    wr16(image + entity + ENTITY_Y, be16(image + A_ship_record_shadow + ENTITY_Y));
}

/* powerup_slot1_activate @ 0x13ede — one of the arms of the 0x19348 power-up jump table. It only
 * refills the weapon decay timer; ../out/subsystems.tsv reads it as unreachable, because
 * `powerup_capsule_collected` @ 0x13d9e diverts a cursor of 1 to 0x13f0e before the table is
 * consulted. Reconstructed because it is a named routine of this subsystem, not because a path
 * reaches it. */
void powerup_slot1_activate(uint8_t *image) {
    wr16(image + A_weapon_decay_timer, POWERUP_DECAY_TICKS);
}

/* powerup_downgrade_on_death @ 0x13f72 — losing a ship steps both levels back one, each with its
 * own floor. Both are `subq.b` read-modify-writes on the byte itself, so the decrement lands even
 * on the step that is about to be clamped away. */
void powerup_downgrade_on_death(uint8_t *image) {
    int8_t speed = (int8_t)(image[A_ship_speed_level] - 1);

    image[A_ship_speed_level] = (uint8_t)speed;
    if (speed < 0)                                  /* `bpl` past the `clr.b` */
        image[A_ship_speed_level] = 0;

    int8_t power = (int8_t)(image[A_weapon_power_level] - 1);

    image[A_weapon_power_level] = (uint8_t)power;
    if (power < WEAPON_POWER_LEVEL_MIN)
        image[A_weapon_power_level] = WEAPON_POWER_LEVEL_MIN;
}

/* ================================================================================================
 * Retiring a shot.
 * ============================================================================================= */
/* shot_to_puff @ 0x155e2 — a2 = the record. Rewrites a spent shot as the hit flash IN PLACE: the
 * slot stays alive and keeps animating, and `shot_anim_puff` is what finally clears it. */
void shot_to_puff(uint8_t *image, uint32_t shot) {
    wr16(image + shot + ENTITY_Y, (uint16_t)(be16(image + shot + ENTITY_Y) - PUFF_Y_LIFT));
    image[shot + ENTITY_TYPE] = SHOT_TYPE_PUFF;
    wr32(image + shot + ENTITY_SPRITE, A_puff_sprite);
    image[shot + ENTITY_ANIM_FRAME] = PUFF_FIRST_FRAME;
    wr16(image + shot + ENTITY_HEIGHT, PUFF_ROWS);
}

/* shot_retire_kind32 @ 0x15582 — a2 = the record. A homing missile also holds one of the two lock
 * slots; releasing it is what lets the next missile acquire that target. */
void shot_retire_kind32(uint8_t *image, uint32_t shot) {
    if (image[shot + ENTITY_ALIVE] == 0 || image[shot + ENTITY_TYPE] != SHOT_TYPE_MISSILE)
        return;

    uint32_t lock = (be16(image + shot + ENTITY_HEIGHT) & SHOT_LOCK_SLOT_B) ? A_missile_lock_b
                                                                           : A_missile_lock_a;

    image[lock] = 0;
    shot_to_puff(image, shot);
    image[A_active_count_type32] -= 1;
}

/* shot_retire_kind36 @ 0x155b4 — a2 = the record. NO kind check, unlike its two neighbours: every
 * caller has already established the slot holds a live seeker. */
void shot_retire_kind36(uint8_t *image, uint32_t shot) {
    shot_to_puff(image, shot);
    image[A_active_count_seekers] -= 1;
}

/* shot_retire_kind33 @ 0x155c2 — a2 = the record. */
void shot_retire_kind33(uint8_t *image, uint32_t shot) {
    if (image[shot + ENTITY_ALIVE] == 0 || image[shot + ENTITY_TYPE] != SHOT_TYPE_BOMB)
        return;

    shot_to_puff(image, shot);
    image[A_active_count_bombs] -= 1;
}

/* player_shots_clear @ 0x15604 — end of a life or a level: put the drone away and retire every
 * seeker. The seekers are RE-TYPED to 0x32 first, which is what lets the count-only
 * `shot_retire_kind36` be reused here without its own kind check ever mattering. */
void player_shots_clear(uint8_t *image) {
    image[A_entity_gunsight + ENTITY_ALIVE] = 0;
    image[A_trail_drone_active] = 0;

    for (unsigned slot = 0; slot < PLAYER_SHOT_SLOTS; slot++) {
        uint32_t shot = A_entity_table + slot * ENTITY_STRIDE;

        if (image[shot + ENTITY_ALIVE] == 0 || image[shot + ENTITY_TYPE] != SHOT_TYPE_SEEKER)
            continue;
        image[shot + ENTITY_TYPE] = SHOT_TYPE_MISSILE;
        shot_retire_kind36(image, shot);
    }
}

/* ================================================================================================
 * The per-frame shot pass.
 * ============================================================================================= */
/* shot_set_sprite_a @ 0x152ea — a2 = the record. Two lookups: heading -> variant -> sprite pointer.
 * Both indexes are SIGNED (`ext.w` then an indexed `move.b`/`movea.l` on a word index), which is
 * what lets a heading or a variant byte above 0x7f reach below its table's base. */
void shot_set_sprite_a(uint8_t *image, uint32_t shot) {
    /* `ext.w` on the heading BYTE, then `adda.w` — machine.h's sign_ext8 is that pair's net effect. */
    uint32_t variant_entry = addr_add(A_shot_variant_table,
                                      sign_ext8(image[shot + SHOT_HEADING]));
    /* ...then `ext.w` again on the variant byte, `lsl.w #2`, and a WORD-indexed `movea.l`. */
    int8_t variant = (int8_t)image[variant_entry];
    uint32_t entry = addr_add(A_shot_sprite_ptrs_a,
                              sign_ext16((uint16_t)(variant * (int)SPRITE_PTR_BYTES)));

    wr32(image + shot + ENTITY_SPRITE, be32(image + entry));
}

/* shot_anim_puff @ 0x15370 — a2 = the record. Runs at half rate, off the same phase byte the
 * explosion animation uses, so the flash takes eight frames to play its four. */
void shot_anim_puff(uint8_t *image, uint32_t shot) {
    if (image[A_explosion_phase_odd] != 0)
        return;

    uint8_t frame = (uint8_t)(image[shot + ENTITY_ANIM_FRAME] + 1);

    image[shot + ENTITY_ANIM_FRAME] = frame;
    if (frame == PUFF_DEATH_FRAME) {
        image[shot + ENTITY_ALIVE] = 0;
        return;
    }

    uint32_t entry = addr_add(A_puff_frame_ptrs,
                              ((frame - 1u) & PUFF_FRAME_INDEX_MASK) * SPRITE_PTR_BYTES);

    wr32(image + shot + ENTITY_SPRITE, be32(image + entry));
}

/* player_shot_update_all @ 0x152a4 — the frame's pass over the six shot slots.
 *
 * The original tests the type byte three times in a row rather than branching away after a match;
 * the single read here is equivalent because neither callee writes ENTITY_TYPE, and the three kinds
 * are distinct. */
void player_shot_update_all(uint8_t *image) {
    for (unsigned slot = 0; slot < PLAYER_SHOT_SLOTS; slot++) {
        uint32_t shot = A_entity_table + slot * ENTITY_STRIDE;

        if (image[shot + ENTITY_ALIVE] == 0)
            continue;

        uint8_t type = image[shot + ENTITY_TYPE];

        if (type == SHOT_TYPE_MISSILE || type == SHOT_TYPE_SEEKER)
            shot_set_sprite_a(image, shot);
        else if (type == SHOT_TYPE_PUFF)
            shot_anim_puff(image, shot);
    }
}

/* ================================================================================================
 * Glue. The two class tests answer in the Z flag and write no memory, so their answer reaches the
 * diff through `store_z_flag_answer` — collision.c's mirror of the `seq` in test/abi.py's stub.
 * Everything else writes the image directly.
 * ============================================================================================= */
/* Register map: A2 = the record; answer in Z (set = not lockable). */
void g_entity_type_is_lockable(uint8_t *image, uint32_t result, uint32_t entity) {
    store_z_flag_answer(image, result, entity_type_is_lockable(image, entity));
}

/* Register map: A1 = the record; answer in Z (set = not a missile target). */
void g_entity_type_is_missile_target(uint8_t *image, uint32_t result, uint32_t entity) {
    store_z_flag_answer(image, result, entity_type_is_missile_target(image, entity));
}

/* Register map: A2 = the entity. */
void g_entity_pos_from_ship(uint8_t *image, uint32_t entity) {
    entity_pos_from_ship(image, entity);
}

/* No register arguments. */
void g_powerup_slot1_activate(uint8_t *image) {
    powerup_slot1_activate(image);
}

/* No register arguments. */
void g_powerup_downgrade_on_death(uint8_t *image) {
    powerup_downgrade_on_death(image);
}

/* Register map: A2 = the record, for all six of these. */
void g_shot_to_puff(uint8_t *image, uint32_t shot) {
    shot_to_puff(image, shot);
}

void g_shot_retire_kind32(uint8_t *image, uint32_t shot) {
    shot_retire_kind32(image, shot);
}

void g_shot_retire_kind33(uint8_t *image, uint32_t shot) {
    shot_retire_kind33(image, shot);
}

void g_shot_retire_kind36(uint8_t *image, uint32_t shot) {
    shot_retire_kind36(image, shot);
}

void g_shot_set_sprite_a(uint8_t *image, uint32_t shot) {
    shot_set_sprite_a(image, shot);
}

void g_shot_anim_puff(uint8_t *image, uint32_t shot) {
    shot_anim_puff(image, shot);
}

/* No register arguments — both walk the fixed entity table. */
void g_player_shot_update_all(uint8_t *image) {
    player_shot_update_all(image);
}

void g_player_shots_clear(uint8_t *image) {
    player_shots_clear(image);
}
