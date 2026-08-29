/* weapon.c — the player's armament: what a spent shot becomes, how the live ones are animated, the
 * two type-class tests the targeting code asks, the power-up bar that chooses the weapon, and the
 * pass that resolves what the ship itself has just touched.
 *
 * Entity slots 0..5 hold the player's shots (include/entity.h). A shot leaves play by being
 * rewritten in place as the four-frame hit flash — `shot_to_puff` — which is why every "retire"
 * here is a conversion rather than a kill, and why the three kind-specific retires differ only in
 * which live-shot count they decrement and what they release first.
 *
 * The bar and the hit pass are one chain: `ship_resolve_entity_hits` is the only caller of
 * `powerup_capsule_collected`, which is the only caller of the five arms below it.
 */
#include "machine.h"
#include "entity.h"
#include "weapon.h"
#include "collision.h"
#include "player.h"
#include "enemy.h"
#include "hud.h"
#include "sound.h"
#include "util.h"

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
 * The power-up bar: the cursor, the commit, and the five arms the two jump tables reach.
 *
 * NONE OF THE FIVE ARMS HAS AN `fn` LINE IN ../names.txt — every one is a `jmp (a0)` target reached
 * only through a table, so the names below are THIS RECONSTRUCTION'S, proposed back in
 * ../out/names_wave3_misc.txt. `powerup_slot1_activate` above is the exception: the map names it,
 * and the commit's cursor-1 diversion is why nothing reaches it.
 * ============================================================================================= */

/* The addresses the two shipped tables hold. Entry addresses rather than globals, so they are spelt
 * `FN_` and not `A_` — src/enemy.c's animation dispatcher says why. */
#define FN_powerup_arm_none 0x148c8u   /* the bare `rts`; entry 0 of BOTH tables */
#define FN_powerup_select_missile 0x13e8au
#define FN_powerup_select_bomb 0x13eb4u
#define FN_powerup_slot1_activate 0x13edeu
#define FN_powerup_select_seeker 0x13ee8u
#define FN_powerup_upgrade_weapon_power 0x13f0eu
#define FN_powerup_upgrade_shield 0x13f3au

/* `lsl.w #2` on the slot before it indexes either table. Spelt here rather than shared with
 * src/enemy.c's `JUMP_TABLE_ENTRY_BYTES`, which is that translation unit's own file-scope name:
 * neither is in a header, and test_constants.py refuses one name defined in two files. */
#define POWERUP_TABLE_ENTRY_BYTES 4u

/* The three arms that SELECT a weapon kind share five stores — clear the shield level and the HUD
 * byte that mirrors it, ask for the gauge repaint, refill the shield timer, take the kind — and
 * differ only in the kind and in whether the shots already in flight are retired. */
static void powerup_select_weapon(uint8_t *image, uint8_t kind) {
    image[A_power_gauge_display] = 0;
    image[A_shield_level] = 0;
    panel_request_repaint(image, PANEL_REDRAW_GAUGE_BIT);
    wr16(image + A_shield_decay_timer, POWERUP_DECAY_TICKS);
    image[A_selected_weapon] = kind;
}

/* powerup_select_missile @ 0x13e8a — entry 4 of the activate table. */
static void powerup_select_missile(uint8_t *image) {
    powerup_select_weapon(image, WEAPON_KIND_MISSILE);
    player_shots_clear(image);
}

/* powerup_select_bomb @ 0x13eb4 — entry 2. */
static void powerup_select_bomb(uint8_t *image) {
    powerup_select_weapon(image, WEAPON_KIND_BOMB);
    player_shots_clear(image);
}

/* powerup_select_seeker @ 0x13ee8 — entry 3, and the one of the three that does NOT retire the
 * shots in flight: a seeker selection leaves the drone and the live seekers where they are. */
static void powerup_select_seeker(uint8_t *image) {
    powerup_select_weapon(image, WEAPON_KIND_SEEKER);
}

/* powerup_upgrade_weapon_power @ 0x13f0e — entry 1 of the UPGRADE table, and also where the commit
 * diverts a cursor of 1 before the activate table is read. It is the only arm that puts the cursor
 * back itself and the only one that asks for no repaint. */
static void powerup_upgrade_weapon_power(uint8_t *image) {
    wr16(image + A_weapon_decay_timer, POWERUP_DECAY_TICKS);
    image[A_weapon_power_level]++;
    if ((int8_t)image[A_weapon_power_level] > (int8_t)WEAPON_POWER_LEVEL_MAX)
        image[A_weapon_power_level] = WEAPON_POWER_LEVEL_MAX;
    image[A_powerup_cursor] = 0;
}

/* powerup_upgrade_shield @ 0x13f3a — entries 2, 3 and 4 of the upgrade table are all this one arm,
 * so re-committing any of the three weapon slots buys a shield level rather than a second copy of
 * the weapon. Unlike the select arms it MIRRORS the level to the HUD byte instead of clearing it. */
static void powerup_upgrade_shield(uint8_t *image) {
    wr16(image + A_shield_decay_timer, POWERUP_DECAY_TICKS);
    image[A_shield_level]++;
    if ((int8_t)image[A_shield_level] > (int8_t)SHIELD_LEVEL_MAX)
        image[A_shield_level] = SHIELD_LEVEL_MAX;
    image[A_power_gauge_display] = image[A_shield_level];
    panel_request_repaint(image, PANEL_REDRAW_GAUGE_BIT);
}

typedef void (*powerup_arm)(uint8_t *image);

struct powerup_arm_entry {
    uint32_t address;
    powerup_arm run;        /* NULL where the original's entry is the bare `rts` */
};

static const struct powerup_arm_entry POWERUP_ARMS[] = {
    {FN_powerup_arm_none, 0},
    {FN_powerup_select_missile, powerup_select_missile},
    {FN_powerup_select_bomb, powerup_select_bomb},
    {FN_powerup_slot1_activate, powerup_slot1_activate},
    {FN_powerup_select_seeker, powerup_select_seeker},
    {FN_powerup_upgrade_weapon_power, powerup_upgrade_weapon_power},
    {FN_powerup_upgrade_shield, powerup_upgrade_shield},
};

#define POWERUP_ARM_COUNT (sizeof POWERUP_ARMS / sizeof POWERUP_ARMS[0])

/* `move.b $19906,d0 / ext.w d0 / lsl.w #2 / lea <table>,a0 / movea.l 0(a0,d0.w),a0 / jmp (a0)`.
 *
 * The index is SIGN-EXTENDED to a word and the scaled result is added to the base AS A WORD, so a
 * slot of 0x80 or more reads BELOW the table rather than 0x200 bytes above it. The game writes only
 * 0..4 there, but that is the instruction and this transcribes it.
 *
 * THE TARGET IS READ OUT OF THE IMAGE and mapped back to the C arm that IS it, the way
 * `enemies_animate_all` does; an address the map does not hold is left uncalled. */
static void run_powerup_arm(uint8_t *image, uint32_t table, uint8_t slot) {
    uint32_t offset = sign_ext16((uint16_t)(sign_ext8(slot) * POWERUP_TABLE_ENTRY_BYTES));
    uint32_t address = be32(image + addr_add(table, offset));

    for (unsigned arm = 0; arm < POWERUP_ARM_COUNT; arm++) {
        if (POWERUP_ARMS[arm].address != address)
            continue;
        if (POWERUP_ARMS[arm].run != 0)
            POWERUP_ARMS[arm].run(image);
        return;
    }
}

/* The uncharged arm @ 0x13e66: step the cursor round the five icons and ask for the repaint. */
static void powerup_cursor_advance(uint8_t *image) {
    image[A_powerup_cursor]++;
    if (image[A_powerup_cursor] == POWERUP_CURSOR_SLOTS)
        image[A_powerup_cursor] = 0;
    panel_request_repaint(image, PANEL_REDRAW_POWERUP_BIT);
}

/* Cursor 0's commit @ 0x13db4, taken before either table is consulted: one more speed level, an
 * EQUALITY test at the ceiling — so a level already past 2 walks on rather than being pulled back —
 * and then the same "cursor home, repaint the bar" tail the advance above has. */
static void powerup_speed_up(uint8_t *image) {
    image[A_ship_speed_level]++;
    if (image[A_ship_speed_level] == SHIP_SPEED_LEVEL_OVERFLOW)
        image[A_ship_speed_level] = SHIP_SPEED_LEVEL_MAX;
    wr16(image + A_speed_decay_timer, POWERUP_DECAY_TICKS);
    image[A_powerup_cursor] = 0;
    panel_request_repaint(image, PANEL_REDRAW_POWERUP_BIT);
}

/* The tail both table arms share @ 0x13e28 / 0x13e54: the cursor goes home and the bar is asked
 * for, and only THEN is the arm entered — so an arm that writes the cursor itself (the weapon-power
 * one does) wins over this clear. */
static void powerup_commit_through(uint8_t *image, uint32_t table, uint8_t slot) {
    image[A_powerup_cursor] = 0;
    panel_request_repaint(image, PANEL_REDRAW_POWERUP_BIT);
    run_powerup_arm(image, table, slot);
}

/* powerup_capsule_collected @ 0x13d9e — one call per frame while a capsule is in the ship's box.
 *
 * With the fire button not charged this only steps the bar's cursor. Charged, it COMMITS: cursor 0
 * is the speed slot and never reaches a table; a cursor equal to the slot already active goes
 * through the upgrade table; anything else records the new slot and goes through the activate
 * table — except cursor 1, which is diverted straight into the weapon-power arm AFTER the sound and
 * BEFORE the activate table is indexed, so entry 1 of that table can never run.
 *
 * BOTH `sound_start` CALLS TAKE THE CURSOR AS THEIR CHANNEL, because D0 still holds the byte the
 * commit loaded and `sound_start` reads D0 as its fallback voice. */
void powerup_capsule_collected(uint8_t *image) {
    uint8_t cursor;
    uint8_t active_slot;

    if (image[A_fire_charged] == 0) {
        powerup_cursor_advance(image);
        return;
    }
    cursor = image[A_powerup_cursor];
    if (cursor == POWERUP_CURSOR_SPEED) {
        powerup_speed_up(image);
        return;
    }
    /* `cmp.b $19906,d0` comes BEFORE the sound (0x13dee) and both arms then RE-READ the byte after
     * it (0x13e14 / 0x13e40). The two reads agree only because `sound_start` writes nothing at
     * 0x19906 — so the compare takes its operand from where the original takes it, and the arms
     * take the index from the image, rather than one local standing for both. */
    active_slot = image[A_powerup_active_slot];
    sound_start(image, SFX_POWERUP_COMMIT, cursor);
    if (cursor == active_slot) {
        powerup_commit_through(image, A_powerup_upgrade_jumptable, image[A_powerup_active_slot]);
        return;
    }
    if (cursor == POWERUP_CURSOR_WEAPON_POWER) {
        powerup_upgrade_weapon_power(image);
        return;
    }
    image[A_powerup_active_slot] = cursor;
    panel_request_repaint(image, PANEL_REDRAW_WEAPON_BIT);
    powerup_commit_through(image, A_powerup_activate_jumptable, image[A_powerup_active_slot]);
}

/* ================================================================================================
 * The ship's own collision pass.
 * ============================================================================================= */
/* ship_resolve_entity_hits @ 0x13cd4 — A3 = the ship's row of the all-pairs overlap mask built by
 * `object_pair_overlap_mark`. Bit j of that longword says entity j's box met the ship's this frame;
 * this walks the twelve entities the ship can meet and resolves each set bit.
 *
 * THE LETHAL ARM IS A `bra.w` TAIL CALL out of the MIDDLE of the loop, so the first lethal touch
 * ends the routine inside `explosion_spawn` and the entities after it are never examined. The
 * capsule arm returns to the loop instead, which is why two capsules in one frame both count.
 *
 * `ship` IS A2, AND THE ROUTINE NEVER WRITES IT — it is threaded straight through to
 * `explosion_spawn` as the record to blow apart (include/weapon.h says which record the two call
 * sites pass). The entity the ship touched is A4's, and it is NOT what explodes.
 *
 * The mask longword is RE-READ on every pass — `move.l (a3),d1` is the loop head and not a
 * preamble — so a capsule arm that rewrote the row would be seen by the passes after it.
 *
 * The sound's channel is the SCAN's own bit index (6..17), which D0 is holding; none of the twelve
 * is 1, 2 or 4, so `sound_start` resolves them all to voice 3 unless the stream names its own. */
void ship_resolve_entity_hits(uint8_t *image, uint32_t ship, uint32_t hit_mask_row) {
    for (unsigned slot = 0; slot < SHIP_HIT_SCAN_SLOTS; slot++) {
        uint32_t entity = addr_add(A_enemy_shot_slots, slot * ENTITY_STRIDE);
        unsigned bit = SHIP_HIT_SCAN_FIRST + slot;

        if ((be32(image + hit_mask_row) & (1u << bit)) == 0)
            continue;
        if (image[entity + ENTITY_TYPE] == TYPE_POWERUP_CAPSULE) {
            powerup_capsule_collected(image);
            image[entity + ENTITY_ALIVE] = 0;
            sound_start(image, SFX_POWERUP_CAPSULE, (uint8_t)bit);
            continue;
        }
        if (image[A_ship_invulnerable] != 0 || !entity_type_is_lethal(image, entity))
            continue;
        image[A_death_event_flags] |= (uint8_t)(1u << DEATH_EVENT_BIT_SHIP);
        explosion_spawn(image, ship, SHIP_DEATH_EXPLOSION_GROUP);
        return;
    }
}

/* ================================================================================================
 * Retiring a shot.
 * ============================================================================================= */
/* `subi.b #$1,<counter>` — decrement a live-shot counter and answer its BORROW, which is the
 * 68000's X. One helper because the three retire routines below end on the same instruction over
 * three different counters; the flag itself is machine.h's `byte_sub_extend`, which is the kit's one
 * model of what a byte subtract leaves in X. */
static unsigned count_down_reporting_borrow(uint8_t *image, uint32_t counter) {
    unsigned borrowed = byte_sub_extend(image[counter], 1);

    image[counter] -= 1;
    return borrowed;
}

/* shot_to_puff @ 0x155e2 — a2 = the record. Rewrites a spent shot as the hit flash IN PLACE: the
 * slot stays alive and keeps animating, and `shot_anim_puff` is what finally clears it. */
void shot_to_puff(uint8_t *image, uint32_t shot) {
    wr16(image + shot + ENTITY_Y, (uint16_t)(be16(image + shot + ENTITY_Y) - PUFF_Y_LIFT));
    image[shot + ENTITY_TYPE] = SHOT_TYPE_PUFF;
    wr32(image + shot + ENTITY_SPRITE, A_puff_sprite);
    image[shot + ENTITY_ANIM_FRAME] = PUFF_FIRST_FRAME;
    wr16(image + shot + ENTITY_HEIGHT, PUFF_ROWS);
}

/* THE THREE RETIRE ROUTINES REPORT THE 68000's X, and include/weapon.h says why a caller needs it:
 * each ends on a `subi.b #$1` of its own live-shot counter, whose BORROW is the flag the frame
 * loop's next `score_add_bcd` adds. An arm that returns EARLY makes no such decrement and leaves the
 * caller's own X, which is what `extend_in` is for — the value is passed straight back out. */

/* shot_retire_kind32 @ 0x15582 — a2 = the record. A homing missile also holds one of the two lock
 * slots; releasing it is what lets the next missile acquire that target. */
unsigned shot_retire_kind32(uint8_t *image, uint32_t shot, unsigned extend_in) {
    if (image[shot + ENTITY_ALIVE] == 0 || image[shot + ENTITY_TYPE] != SHOT_TYPE_MISSILE)
        return extend_in;   /* `tst.b`/`cmpi.b` and the `rts` leave X where the caller had it */

    uint32_t lock = (be16(image + shot + ENTITY_HEIGHT) & SHOT_LOCK_SLOT_B) ? A_missile_lock_b
                                                                           : A_missile_lock_a;

    image[lock] = 0;
    shot_to_puff(image, shot);
    return count_down_reporting_borrow(image, A_active_count_type32);
}

/* shot_retire_kind36 @ 0x155b4 — a2 = the record. NO kind check, unlike its two neighbours: every
 * caller has already established the slot holds a live seeker. */
unsigned shot_retire_kind36(uint8_t *image, uint32_t shot) {
    shot_to_puff(image, shot);
    return count_down_reporting_borrow(image, A_active_count_seekers);
}

/* shot_retire_kind33 @ 0x155c2 — a2 = the record. */
unsigned shot_retire_kind33(uint8_t *image, uint32_t shot, unsigned extend_in) {
    if (image[shot + ENTITY_ALIVE] == 0 || image[shot + ENTITY_TYPE] != SHOT_TYPE_BOMB)
        return extend_in;

    shot_to_puff(image, shot);
    return count_down_reporting_borrow(image, A_active_count_bombs);
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
        (void)shot_retire_kind36(image, shot);
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
 * Launching one — the three `fire_*` routines.
 *
 * Every launch starts where the ship's shadow record last drew (`entity_pos_from_ship`) and steps
 * the matching launch counter down. The seeker and the missile then take the SAME twelve stores;
 * the bomb takes none of them, because it is aimed once and afterwards steered by gravity.
 * ============================================================================================= */

/* Arm `shot` as a steered projectile: alive, of `type`, drawn by the shared sprite, turning by
 * SHOT_ARM_MAX_TURN every SHOT_ARM_TURN_PERIOD frames, and launched along heading 0.
 *
 * The heading is cleared and the velocity pair derived from it before the shot has a target, so a
 * new seeker or missile always leaves the ship flying due east and turns towards its target on the
 * frames that follow.
 *
 * The two READ-BACKS below are the original's own, not a paraphrase: it reloads the countdown from
 * the period byte it has just stored (`move.b 28(a2),27(a2)`, a memory-to-memory move) and reloads
 * the speed byte for the velocity call (`move.b 30(a2),d1`). Nothing written in between shares
 * either offset, so both are equal to the arguments — they are kept because they are the
 * instructions, and because a later change to the record's union would make them stop being equal
 * silently if they were folded away. */
static void arm_steered_shot(uint8_t *image, uint32_t shot, uint8_t type, uint8_t speed,
                             uint8_t time_to_live) {
    image[shot + ENTITY_ALIVE] = 1;
    image[shot + ENTITY_TYPE] = type;
    wr16(image + shot + ENTITY_HEIGHT, SHOT_ARM_ROWS);
    wr32(image + shot + ENTITY_SPRITE, A_shot_sprite_steered);
    image[shot + SHOT_TURN_PERIOD] = SHOT_ARM_TURN_PERIOD;
    image[shot + SHOT_SPEED] = speed;
    image[shot + SHOT_MAX_TURN] = SHOT_ARM_MAX_TURN;
    image[shot + SHOT_TURN_COUNTDOWN] = image[shot + SHOT_TURN_PERIOD];
    image[shot + SHOT_HEADING] = 0;
    image[shot + ENTITY_ANIM_FRAME] = time_to_live;
    entity_set_velocity_from_angle(image, shot, 0, (int8_t)image[shot + SHOT_SPEED]);
}

/* fire_seeker @ 0x13f9e — a3 = the slot, d6.b = the target index to keep if the gunsight holds no
 * lock, d0.b = the channel `sound_start` would use for a stream that names none.
 *
 * D6 IS AN INPUT, not a local: the routine only overwrites it when `A_seeker_lock_target_index` is
 * non-zero, and it is the byte that ends up in the new seeker's SHOT_TARGET_INDEX either way. The
 * sound is likewise started only on the locked arm, which is what makes an unlocked launch silent.
 *
 * NO ALIVE GUARD, unlike its two neighbours — the caller has already picked a free slot. */
void fire_seeker(uint8_t *image, uint32_t shot, uint8_t fallback_target, uint8_t sound_channel) {
    uint8_t target = fallback_target;

    if (image[A_seeker_lock_target_index] != 0) {
        target = image[A_seeker_lock_target_index];
        sound_start(image, SFX_SEEKER_LAUNCH, sound_channel);
    }
    entity_pos_from_ship(image, shot);
    arm_steered_shot(image, shot, SHOT_TYPE_SEEKER, SEEKER_SPEED, SEEKER_TTL);
    image[A_seeker_launch_counter] -= 1;
    image[shot + SHOT_TARGET_INDEX] = target;
}

/* fire_homing_missile @ 0x1401a — a3 = the slot. Silent, and it acquires nothing here: the missile
 * leaves with MISSILE_NO_TARGET and `homing_missile_update` finds it something on the next frame.
 *
 * WHICH LOCK SLOT IT WILL OWN is decided at launch and recorded in ENTITY_HEIGHT's bit 15: a
 * non-zero `A_missile_lock_a` means the other missile is already using slot A, so this one takes
 * slot B. The flag is what `homing_missile_update` and `shot_retire_kind32` both read back. */
void fire_homing_missile(uint8_t *image, uint32_t shot) {
    if (image[shot + ENTITY_ALIVE] != 0)
        return;

    entity_pos_from_ship(image, shot);
    arm_steered_shot(image, shot, SHOT_TYPE_MISSILE, MISSILE_SPEED, MISSILE_TTL);
    image[A_missile_launch_counter] -= 1;
    if (image[A_missile_lock_a] != 0)
        wr16(image + shot + ENTITY_HEIGHT,
             (uint16_t)(be16(image + shot + ENTITY_HEIGHT) | SHOT_LOCK_SLOT_B));
    image[shot + SHOT_TARGET_INDEX] = MISSILE_NO_TARGET;
}

/* fire_bomb @ 0x14324 — a3 = the slot, d0.b = the sound channel (see `fire_seeker`). Thrown
 * forward at a fixed speed with gravity in ENTITY_AY and no heading block at all.
 *
 * IT DOES NOT CLEAR ENTITY_BOUNCE, and neither does the original, so a bomb inherits whatever the
 * slot's previous occupant left in +0x1b — a spent seeker's SHOT_TURN_COUNTDOWN, most likely. That
 * byte is `bomb_update`'s terrain latch, so a bomb launched into such a slot is retired on its FIRST
 * terrain contact instead of bouncing three times, until its first clean frame clears the latch.
 * Faithful, and named here because it is a cross-routine effect no single test reads as a bug. */
void fire_bomb(uint8_t *image, uint32_t shot, uint8_t sound_channel) {
    if (image[shot + ENTITY_ALIVE] != 0)
        return;

    wr16(image + shot + ENTITY_AX, 0);
    wr16(image + shot + ENTITY_AY, BOMB_GRAVITY_AY);
    wr16(image + shot + ENTITY_DX, BOMB_LAUNCH_DX);
    wr16(image + shot + ENTITY_DY, 0);
    image[shot + ENTITY_ALIVE] = 1;
    image[shot + ENTITY_TYPE] = SHOT_TYPE_BOMB;
    wr16(image + shot + ENTITY_HEIGHT, BOMB_ROWS);
    wr32(image + shot + ENTITY_SPRITE, A_bomb_sprite);
    image[A_bomb_launch_counter] -= 1;
    image[shot + SHOT_BOUNCES_LEFT] = BOMB_BOUNCES;
    sound_start(image, SFX_BOMB_LAUNCH, sound_channel);
    entity_pos_from_ship(image, shot);        /* the original's `bra.w $14092` tail call */
}

/* ================================================================================================
 * Steering — entity_steer_toward_target @ 0x141d6, and the two per-frame updates that drive it.
 * ============================================================================================= */

/* `entity_ptr_from_index` @ 0x141c0.
 *
 * That routine is `util`'s (../out/subsystems.tsv) and util has not ported it, so this names it and
 * transcribes the one instruction that is its own — `and.l #$ff,d6`, the mask, which is exact
 * because the index comes out of a record BYTE at both call sites here. The rest (`mulu.w #$2c` +
 * `adda.l` onto the table base) IS `collision_table_row`'s neighbour `entity_record`, so it is
 * called rather than copied. Both entries (0x141c0, 0x141c2) are now verified in src/enemy.c as
 * `entity_ptr_from_index`; this is the one site to swap (STATUS.md, enemy section, tables the debt). */
static uint32_t entity_from_index(uint8_t index) {
    return entity_record(index);
}

/* The heading is a 6-bit compass: 64 directions round the circle, which is also the length of
 * util.h's A_cos_table_64 and of A_shot_variant_table. HEADING_HALF_CIRCLE is the half-turn the
 * short-way test compares a distance against. Both are `heading_step`'s alone. */
#define HEADING_MASK 0x3fu
#define HEADING_HALF_CIRCLE 0x20u

/* Where the heading lands this frame.
 *
 * `difference` is a signed BYTE distance around the circle, so it can name the long way round;
 * `(-difference) & HEADING_MASK >= HEADING_HALF_CIRCLE` is the test that picks the short one. Every
 * step is a byte operation — the original never widens — which is why the whole helper works in
 * bytes. The two arms differ in more than direction: the turn-by-max arms mask the result back onto
 * the circle and the exact arm does not, because it stores `wanted` itself (`move.b d1,d0`), which
 * `angle_to_target` has already delivered as 0..0x3f. */
static uint8_t negate_byte(uint8_t value) {   /* `neg.b` — 0x80 negates to itself */
    return (uint8_t)(0u - value);
}

static uint8_t heading_step(uint8_t wanted, uint8_t heading, int8_t difference, int8_t max_turn) {
    /* `bpl` past the `neg.b`: a magnitude, and not an absolute value — 0x80 stays negative. */
    uint8_t magnitude = difference < 0 ? negate_byte((uint8_t)difference) : (uint8_t)difference;

    /* `cmp.b d2,d0` + `bge`: a target within one turn of here is taken exactly, not stepped at. */
    if ((int8_t)magnitude < max_turn)
        return wanted;

    /* The short-way test negates the difference AGAIN and unconditionally (`move.b d3,d0` reloads
     * the signed byte before `neg.b`), so it is not `magnitude`: a difference of +0x30 asks about
     * 0x10, not about 0x30. Each `& HEADING_MASK` is applied to a byte-wrapped value, as
     * `neg.b`/`add.b`/`sub.b` leave it — masking the promoted `int` would AND a negative number. */
    if ((negate_byte((uint8_t)difference) & HEADING_MASK) >= HEADING_HALF_CIRCLE)
        return (uint8_t)(heading + (uint8_t)max_turn) & HEADING_MASK;
    return (uint8_t)(heading - (uint8_t)max_turn) & HEADING_MASK;
}

/* entity_steer_toward_target @ 0x141d6 — a2 = the entity. Turn towards SHOT_TARGET_INDEX by at most
 * SHOT_MAX_TURN, re-derive the velocity pair from the new heading, and integrate the position.
 *
 * THE POSITION STEP IS UNCONDITIONAL and the turn is not: SHOT_TURN_COUNTDOWN gates the whole
 * steering block, so on the frames it does not reach zero the entity simply carries on along the
 * velocity the last turn left it with. The countdown is decremented on EVERY call and reloaded only
 * on the frame it expires (`subi.b #$1,27(a2)` + `bne`).
 *
 * IT ALSO RETURNS WITH THE CARRY CLEAR, and that is an ANSWER, not housekeeping — this `void`
 * reconstruction cannot express it and no differential case can see it, so it is written down here.
 * Both its exits run into `entity_apply_velocity` @ 0x14306, which ends `andi #$fe,ccr` + `rts`
 * (the bytes `023c 00fe 4e75`, which ../out/prg_dis.txt's linear sweep renders as one bogus
 * `andi.b #$fe,#$75`). The script VM's ext table at 0x19458 holds THIS routine at entry 8 and
 * 0x14306 at entry 7, and `actor_script_op_ext` @ 0x14cce is `jsr (a0)` + `rts` — so a handler's
 * carry IS the opcode's "run the next opcode this frame" flag (`ori.b #$1,ccr` is the SET idiom,
 * seen at 0x14cfa). Whoever wires ext entry 8 must answer CARRY CLEAR: this actor is done for the
 * frame. See src/enemy.c's CARRY_SET / CARRY_CLEAR and STATUS.md's residual note. */
void entity_steer_toward_target(uint8_t *image, uint32_t entity) {
    image[entity + SHOT_TURN_COUNTDOWN] -= 1;
    if (image[entity + SHOT_TURN_COUNTDOWN] == 0) {
        image[entity + SHOT_TURN_COUNTDOWN] = image[entity + SHOT_TURN_PERIOD];

        uint32_t target = entity_from_index(image[entity + SHOT_TARGET_INDEX]);
        uint8_t wanted = (uint8_t)angle_to_target(image, entity, target);
        uint8_t heading = image[entity + SHOT_HEADING];
        int8_t difference = (int8_t)(uint8_t)(wanted - heading);

        /* Already pointing at it: the original branches straight to the position step, leaving the
         * velocity pair as the last turn computed it rather than re-deriving the same answer. */
        if (difference != 0) {
            image[entity + SHOT_HEADING] =
                heading_step(wanted, heading, difference, (int8_t)image[entity + SHOT_MAX_TURN]);
            entity_set_velocity_from_angle(image, entity, image[entity + SHOT_HEADING],
                                           (int8_t)image[entity + SHOT_SPEED]);
        }
    }
    entity_apply_velocity(image, entity);
}

/* A DEAD TARGET SENDS THE SEEKER AT THE PLAYER: it prefers the trail drone, and falls back to the
 * ship's own record when the drone is not out — or when slot 19 is holding something that is not a
 * drone. Both arms write SHOT_TARGET_INDEX, so a seeker whose target has died never simply carries
 * on at the empty slot. */
static uint8_t seeker_fallback_target(const uint8_t *image) {
    if (image[A_entity_gunsight + ENTITY_ALIVE] != 0
        && image[A_entity_gunsight + ENTITY_TYPE] == TYPE_TRAIL_DRONE)
        return ENTITY_INDEX_TRAIL_DRONE;
    return ENTITY_INDEX_SHIP;
}

/* seeker_update @ 0x140a6 — a3 = the seeker. Retarget if what it was chasing has died, count the
 * time-to-live down, and steer. */
void seeker_update(uint8_t *image, uint32_t shot) {
    uint32_t target = entity_from_index(image[shot + SHOT_TARGET_INDEX]);

    if (image[target + ENTITY_ALIVE] == 0)
        image[shot + SHOT_TARGET_INDEX] = seeker_fallback_target(image);

    image[shot + ENTITY_ANIM_FRAME] -= 1;
    if (image[shot + ENTITY_ANIM_FRAME] == 0) {
        /* The original's `bra.w $155b4` tail call, so the retire's X is this routine's own
         * — and unread, because `seeker_update`'s callers are outside the two passes that
         * carry the flag. */
        (void)shot_retire_kind36(image, shot);
        return;
    }
    entity_steer_toward_target(image, shot);
}

/* Is `index`'s record something a homing missile may chase — alive, and of a listed type? */
static int missile_target_is_valid(const uint8_t *image, uint8_t index) {
    uint32_t record = entity_from_index(index);

    return image[record + ENTITY_ALIVE] != 0 && entity_type_is_missile_target(image, record);
}

/* The acquire scan: walk the wave-enemy slots for a live, lockable, unclaimed target.
 *
 * TWO THINGS MAKE THIS MORE THAN A SEARCH. It writes the missile's lock slot BEFORE it checks the
 * claim, so a candidate the other missile already holds still leaves its index in `lock` on the way
 * past — the store stands and the loop moves on. And the claim test compares the two lock BYTES
 * rather than this missile's against the other's target, so it is symmetric: whichever slot this
 * missile owns, an equal pair means the candidate is taken.
 *
 * The counter is a byte and the scan stops only at MISSILE_SCAN_END, so a missile resuming from an
 * index above the enemy slots walks all the way round through 0xff and gives up there rather than
 * spinning. Giving up parks MISSILE_NO_TARGET in both the record and the lock. */
static void missile_acquire_target(uint8_t *image, uint32_t missile, uint32_t lock) {
    uint8_t current = image[missile + SHOT_TARGET_INDEX];
    uint8_t candidate = (current == MISSILE_NO_TARGET) ? MISSILE_SCAN_FIRST : current;

    for (;;) {
        candidate = (uint8_t)(candidate + 1);
        if (candidate == MISSILE_SCAN_END) {
            image[missile + SHOT_TARGET_INDEX] = MISSILE_NO_TARGET;
            image[lock] = MISSILE_NO_TARGET;
            return;
        }
        if (!missile_target_is_valid(image, candidate))
            continue;
        image[lock] = candidate;
        if (image[A_missile_lock_b] == image[A_missile_lock_a])
            continue;
        image[missile + SHOT_TARGET_INDEX] = candidate;
        return;
    }
}

/* homing_missile_update @ 0x14126 — a3 = the missile. Acquire or re-acquire a target, count the
 * time-to-live down, and steer. */
void homing_missile_update(uint8_t *image, uint32_t missile) {
    /* `tst.w 8(a2)` + `bpl`: the lock-slot flag the launch set, read back as the word's sign. */
    uint32_t lock = (be16(image + missile + ENTITY_HEIGHT) & SHOT_LOCK_SLOT_B) ? A_missile_lock_b
                                                                              : A_missile_lock_a;
    uint8_t target = image[missile + SHOT_TARGET_INDEX];

    if (target == MISSILE_NO_TARGET || !missile_target_is_valid(image, target))
        missile_acquire_target(image, missile, lock);

    image[missile + ENTITY_ANIM_FRAME] -= 1;
    if (image[missile + ENTITY_ANIM_FRAME] == 0) {
        /* The original's `bra.w $15582` tail call, so the retire's X is this routine's own — and
         * unread, because `frame_player_shots_maintain` is outside the two passes that carry it. */
        (void)shot_retire_kind32(image, missile, EXTEND_UNREAD);
        return;
    }
    entity_steer_toward_target(image, missile);
}

/* ================================================================================================
 * bomb_update @ 0x14376 — a3 = the bomb. Bounce off the landscape, fall, and die at the floor.
 * ============================================================================================= */

/* The bomb's own row in the overlap table, derived from its record ADDRESS rather than from an
 * index it was handed: `sub.l #entity_table` / `divu.w #$2c`, then `collision_table_row`'s own
 * `lsl.w #2` / `adda.w`.
 *
 * `divu.w` is a 32-by-16 divide whose quotient is a WORD: for a record so far past the table that
 * the quotient overflows 0xffff, the 68000 sets V and leaves the DIVIDEND in the register, which is
 * a different answer from this truncation. The only caller walks slots 0..5, so neither that arm nor
 * `collision_table_row`'s sign extension is reachable — both are transcription, not behaviour the
 * suite pins. NOTE FOR THE ON-TARGET BUILD: this spells a full 32-bit divide, which m68k-elf-gcc
 * turns into a `__udivsi3` call where the original has one `divu.w`; see STATUS.md. */
static uint32_t bomb_collision_row(uint32_t bomb) {
    uint16_t index = (uint16_t)((bomb - A_entity_table) / ENTITY_STRIDE);

    return collision_table_row(A_entity_collision_masks, index);
}

/* Did the blitter's pixel hit come from the LANDSCAPE? The flag alone cannot say — it is set by any
 * non-background pixel — so the bomb also asks its overlap row: an empty row means no other entity
 * was under it, and what it hit was terrain. (`collision_chain_walk` answers the same question for
 * an entity that may be stacked with others; a bomb needs only this one-hop version.) */
static int bomb_hit_terrain(const uint8_t *image, uint32_t bomb) {
    return image[bomb + ENTITY_PIXEL_HIT] != 0 && be32(image + bomb_collision_row(bomb)) == 0;
}

/* `neg.w` then `asr.w #1` — the bounce keeps half the vertical speed and reverses it. The shift is
 * ARITHMETIC, so a bomb thrown back upwards halves towards zero rather than towards 0xffff. */
static uint16_t bounce_velocity(uint16_t vertical_speed) {
    return (uint16_t)((int16_t)(uint16_t)(0u - vertical_speed) >> 1);
}

void bomb_update(uint8_t *image, uint32_t bomb, uint8_t sound_channel) {
    if (image[bomb + ENTITY_ALIVE] == 0)
        return;

    if (bomb_hit_terrain(image, bomb)) {
        /* THE TWO ADJACENT BYTES READ ALIKE AND ARE NOT: +0x1a (SHOT_BOUNCES_LEFT) is the COUNT and
         * +0x1b (entity.h's ENTITY_BOUNCE) is a ONE-FRAME LATCH. A bomb that was also on the terrain
         * last frame is stuck in it rather than bouncing, and dies; the count is stepped either way,
         * which is why a retiring bomb still spends a bounce on its way out. The latch is read into
         * a named local so that swapping the two offsets cannot read as a plausible edit. */
        int was_on_terrain_last_frame = image[bomb + ENTITY_BOUNCE] != 0;

        sound_start(image, SFX_BOMB_BOUNCE, sound_channel);
        wr16(image + bomb + ENTITY_DY, bounce_velocity(be16(image + bomb + ENTITY_DY)));
        image[bomb + SHOT_BOUNCES_LEFT] -= 1;
        if (was_on_terrain_last_frame) {
            (void)shot_retire_kind33(image, bomb, EXTEND_UNREAD);
            return;
        }
        image[bomb + ENTITY_BOUNCE] = 1;
    } else {
        image[bomb + ENTITY_BOUNCE] = 0;
    }

    entity_apply_accel(image, bomb, 1u << ACCEL_BIT_Y_ADD);   /* `move.b #$20,d1` */
    if ((int16_t)be16(image + bomb + ENTITY_Y) >= BOMB_FLOOR_Y
        || image[bomb + SHOT_BOUNCES_LEFT] == 0)
        (void)shot_retire_kind33(image, bomb, EXTEND_UNREAD);
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

/* No register arguments: the cursor, the charge flag and the active slot are all globals. D0 holds
 * the cursor across the commit's `sound_start` and is not an input. */
void g_powerup_capsule_collected(uint8_t *image) {
    powerup_capsule_collected(image);
}

/* Register map: A2 = the record the death explosion blows apart (pass-through), A3 = the ship's row
 * of the collision mask. A4 walks the records and D0 doubles as the bit index and the sound
 * channel; neither is an output. */
void g_ship_resolve_entity_hits(uint8_t *image, uint32_t ship, uint32_t hit_mask_row) {
    ship_resolve_entity_hits(image, ship, hit_mask_row);
}

/* Register map: A2 = the record, for all six of these. */
void g_shot_to_puff(uint8_t *image, uint32_t shot) {
    shot_to_puff(image, shot);
}

/* The three retire routines answer in the 68000's X as well as in memory (include/weapon.h), so
 * their glue takes the flag in and hands it back: `test/abi.py`'s `extend_call_pokes` drives the
 * input and reads the oracle's output, and neither reaches the image diff. */
uint32_t g_shot_retire_kind32(uint8_t *image, uint32_t shot, uint32_t extend_in) {
    return shot_retire_kind32(image, shot, extend_in);
}

uint32_t g_shot_retire_kind33(uint8_t *image, uint32_t shot, uint32_t extend_in) {
    return shot_retire_kind33(image, shot, extend_in);
}

uint32_t g_shot_retire_kind36(uint8_t *image, uint32_t shot) {
    return shot_retire_kind36(image, shot);
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

/* Register map: A2 = the entity. Everything it does lands in the entity record. */
void g_entity_steer_toward_target(uint8_t *image, uint32_t entity) {
    entity_steer_toward_target(image, entity);
}

/* Register map: A3 = the slot, D6.b = the target index kept when the gunsight holds no lock, D0.b =
 * the channel `sound_start` falls back on. D0 CANNOT REACH THE VOICE for the shipped tune — sfx
 * 0x1a opens with the 0xfa header that names its own channel — and the battery asserts that off the
 * image rather than assuming it, which is why the argument is threaded rather than dropped. */
void g_fire_seeker(uint8_t *image, uint32_t shot, uint32_t target_reg, uint32_t channel_reg) {
    fire_seeker(image, shot, (uint8_t)target_reg, (uint8_t)channel_reg);
}

/* Register map: A3 = the slot. */
void g_fire_homing_missile(uint8_t *image, uint32_t shot) {
    fire_homing_missile(image, shot);
}

/* Register map: A3 = the slot, D0.b = the sound channel (see `g_fire_seeker`). */
void g_fire_bomb(uint8_t *image, uint32_t shot, uint32_t channel_reg) {
    fire_bomb(image, shot, (uint8_t)channel_reg);
}

/* Register map: A3 = the record, for all three per-frame updates. */
void g_seeker_update(uint8_t *image, uint32_t shot) {
    seeker_update(image, shot);
}

void g_homing_missile_update(uint8_t *image, uint32_t missile) {
    homing_missile_update(image, missile);
}

/* ...and D0.b = the sound channel, which the bounce's sfx 0x11 overrides the same way. */
void g_bomb_update(uint8_t *image, uint32_t bomb, uint32_t channel_reg) {
    bomb_update(image, bomb, (uint8_t)channel_reg);
}
