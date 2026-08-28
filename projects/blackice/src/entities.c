/*
 * entities.c - the runtime entity table: lifecycle, cell claims, damage.
 *
 * This file owns everything about a body that does not depend on which kind of
 * body it is.  The per-type state machines are in ai.c, and they reach in here
 * to claim cells and to deal damage, so there is exactly one place that writes
 * the occupancy map and exactly one place that decides a body has died.
 *
 * The occupancy map is maintained incrementally - claim_take and claim_release
 * are the only two functions that write it - rather than rebuilt each tick,
 * because a full 4,096-byte clear costs about 12,000 cycles on the 68000 and
 * this costs two byte writes.  test_ai.py rebuilds it independently from the
 * entity table and compares, which is what keeps the incremental form honest.
 */
#include "ai.h"
#include "entities.h"
#include "events.h"
#include "game.h"
#include "hash.h"
#include "trace.h"

/*
 * DESIGN 8's statistics table, indexed by EntityType.  A row of zeroes is a
 * body with no combat behaviour at all - a pickup, or a type this build defers.
 */
const EnemyStats g_enemy_stats[ENT_TYPE_COUNT] = {
    /* ENT_NONE            */ { 0, 0, 0, 0, 0 },
    /* ENT_WATCHDOG        */ { WATCHDOG_HP, WATCHDOG_SPEED, WATCHDOG_SIGHT_UNITS,
                                WATCHDOG_NOISE_UNITS, WATCHDOG_CONE_TAN_Q8 },
    /* ENT_SENTRY          */ { SENTRY_HP, 0, SENTRY_SIGHT_UNITS,
                                SENTRY_NOISE_UNITS, SENTRY_CONE_TAN_Q8 },
    /* ENT_TRACER          */ { TRACER_HP, TRACER_SPEED, TRACER_SIGHT_UNITS,
                                TRACER_NOISE_UNITS, TRACER_CONE_TAN_Q8 },
    /* ENT_BLACK_ICE       */ { 0, 0, 0, 0, 0 },     /* deferred (DESIGN 18) */
    /* ENT_ANCHOR          */ { ANCHOR_HP, 0, 0, 0, 0 },
    /* ENT_TOKEN_ALPHA     */ { 0, 0, 0, 0, 0 },
    /* ENT_TOKEN_BETA      */ { 0, 0, 0, 0, 0 },
    /* ENT_TOKEN_GAMMA     */ { 0, 0, 0, 0, 0 },
    /* ENT_CYCLES_SMALL    */ { 0, 0, 0, 0, 0 },
    /* ENT_CYCLES_LARGE    */ { 0, 0, 0, 0, 0 },
    /* ENT_INTEGRITY_SMALL */ { 0, 0, 0, 0, 0 },
    /* ENT_INTEGRITY_LARGE */ { 0, 0, 0, 0, 0 },
    /* ENT_SCRUBBER        */ { 0, 0, 0, 0, 0 },
    /* ENT_DATA_CACHE      */ { 0, 0, 0, 0, 0 },
};

/* ---- cell claims -------------------------------------------------------- */

void claim_release(GameState *state, uint16_t index)
{
    uint16_t cell = state->entities[index].claim_cell;

    if (state->occupancy.owner[cell] == (uint8_t)(index + 1)) {
        state->occupancy.owner[cell] = ENTITY_CLAIM_NONE;
    }
}

void claim_take(GameState *state, uint16_t index, uint16_t cell)
{
    EntityRuntime *body = &state->entities[index];
    const uint16_t width = state->level->width;

    claim_release(state, index);
    body->claim_cell = cell;
    /* The two divides in the whole mover, paid once per cell entered rather
     * than once per tick: uint16 / uint8 so the 68000 uses `divu.w`. */
    body->target_x = cell_centre((uint8_t)(cell % width));
    body->target_y = cell_centre((uint8_t)(cell / width));
    state->occupancy.owner[cell] = (uint8_t)(index + 1);
}

int32_t entity_at_cell(const GameState *state, uint16_t cell)
{
    return occupancy_owner(&state->occupancy, cell);
}

int32_t entity_hittable_in_cell(const GameState *state, uint16_t cell)
{
    const uint8_t width = state->level->width;
    int32_t owner = occupancy_owner(&state->occupancy, cell);
    int n;

    if (owner >= 0 && entity_is_shootable(state, (uint16_t)owner)) {
        return owner;                   /* it claims this cell */
    }
    /*
     * Nobody shootable claims it.  A body's drawn cell is either the cell it
     * claims or the one it came from, and those are neighbours - claim_take
     * only ever moves it to a cell neighbour_is_open offered - so a body drawn
     * in THIS cell claims one of the eight around it.  Eight byte loads, and no
     * scan of the entity table.
     */
    for (n = 0; n < NEIGHBOUR_COUNT; ++n) {
        uint16_t around = (uint16_t)(cell + state->neighbour_offset[n]);
        int32_t candidate;

        /*
         * The one neighbour walk in the game layer that is NOT started from a
         * walkable cell: the Buster's hitscan asks about every cell it crosses,
         * and the cell it stops on is the border wall.  A negative offset from
         * cell 0 wraps to 65,504, which is a read a long way past the occupancy
         * map - so this walk, alone, carries the bounds test the sealed-border
         * invariant buys everywhere else.
         */
        if (around >= MAP_MAX_CELLS) {
            continue;
        }
        candidate = occupancy_owner(&state->occupancy, around);
        if (candidate < 0 || !entity_is_shootable(state, (uint16_t)candidate)) {
            continue;
        }
        if (cell_of_point(width, state->entities[candidate].x,
                          state->entities[candidate].y) == cell) {
            return candidate;
        }
    }
    return -1;
}

/* ---- lifecycle ---------------------------------------------------------- */

fix88_t entity_world_x(const GameState *state, uint16_t index)
{
    return state->entities[index].x;
}

fix88_t entity_world_y(const GameState *state, uint16_t index)
{
    return state->entities[index].y;
}

int entity_is_shootable(const GameState *state, uint16_t index)
{
    const EntityRuntime *body = &state->entities[index];

    if (!entity_is_live(state, index)) {
        return 0;
    }
    if (body->state == ENT_STATE_DEAD || body->state == ENT_STATE_DESTROYED) {
        return 0;
    }
    return entity_type_is_enemy(body->type) || body->type == ENT_ANCHOR;
}

/*
 * DESIGN 8: the Sentry is invulnerable while its iris is closed.  Nothing else
 * in the first playable's roster has a vulnerability window.
 */
static int entity_is_invulnerable(const EntityRuntime *body)
{
    return body->type == ENT_SENTRY && body->state != ENT_STATE_ATTACK;
}

static void entity_die(GameState *state, uint16_t index)
{
    EntityRuntime *body = &state->entities[index];

    claim_release(state, index);
    body->claim_cell = 0;
    ++state->kills;
    event_push(&state->events, EV_SFX_ENEMY_DISSOLVE);

    /* DESIGN 9's falls: a Sentry destroyed is -5%, and a Tracer killed BEFORE
     * it flees is -8%.  One that is already fleeing has stopped being a threat
     * to the meter and pays nothing. */
    if (body->type == ENT_SENTRY) {
        trace_apply(state, -TRACE_DROP_SENTRY_KILL);
        /* The destroyed frame stays as scenery: still drawn, never removed. */
        body->state = ENT_STATE_DESTROYED;
        return;
    }
    if (body->type == ENT_TRACER && body->state != ENT_STATE_FLEE) {
        trace_apply(state, -TRACE_DROP_TRACER_KILL);
    }
    body->state = ENT_STATE_DEAD;
    body->state_timer = ENEMY_DISSOLVE_TICKS;
}

int entity_damage(GameState *state, uint16_t index, uint8_t damage)
{
    EntityRuntime *body = &state->entities[index];

    if (!entity_is_shootable(state, index) || entity_is_invulnerable(body)) {
        return 0;
    }
    if (body->hp > damage) {
        body->hp = (uint8_t)(body->hp - damage);
        return 1;
    }
    body->hp = 0;
    entity_die(state, index);
    return 1;
}

/*
 * DESIGN 8 puts a Sentry in a 1-cell alcove with three wall neighbours and one
 * open side, and DESIGN 11 rule 5 makes the compiler enforce that shape.  So
 * the alcove itself says which way the turret looks, and no level file has to
 * author a facing that could disagree with the geometry around it.
 */
static angle_t sentry_facing_from_alcove(const GameState *state, uint16_t cell)
{
    int n;

    for (n = 0; n < NEIGHBOUR_ORTHO_COUNT; ++n) {
        uint16_t neighbour = (uint16_t)(cell + state->neighbour_offset[n]);

        if (!map_cell_blocks(&state->blocking, neighbour)) {
            return ai_ortho_facing(n);
        }
    }
    return 0;                       /* a sealed alcove: it can never see anything */
}

void entities_init(GameState *state)
{
    const Level *level = state->level;
    const uint8_t width = level->width;
    uint16_t i;

    for (i = 0; i < MAP_MAX_CELLS; ++i) {
        state->occupancy.owner[i] = ENTITY_CLAIM_NONE;
    }
    for (i = 0; i < LEVEL_MAX_ENTITIES; ++i) {
        EntityRuntime *body = &state->entities[i];
        const Entity *authored = &level->entities[i];

        if (i >= level->entity_count) {
            body->type = ENT_NONE;
            body->state = ENT_STATE_IDLE;
            body->flags = 0;
            body->hp = 0;
            body->x = 0;
            body->y = 0;
            body->facing = 0;
            body->state_timer = 0;
            body->attack_timer = 0;
            body->claim_cell = 0;
            body->spawn_cell = 0;
            body->target_x = 0;
            body->target_y = 0;
            continue;
        }
        body->type = authored->type;
        body->state = ENT_STATE_IDLE;
        body->flags = 0;
        body->hp = entity_stats(authored->type)->hp;
        body->x = cell_centre(authored->cell_x);
        body->y = cell_centre(authored->cell_y);
        /* The file stores a facing as brads >> 2 (DESIGN 11's entity record). */
        body->facing = ANGLE_FROM_BRADS((uint16_t)authored->facing << 2);
        body->state_timer = 0;
        body->attack_timer = 0;
        body->claim_cell = 0;
        body->spawn_cell = (uint16_t)(authored->cell_y * width + authored->cell_x);
        body->target_x = body->x;
        body->target_y = body->y;
        if (entity_type_is_enemy(authored->type) || authored->type == ENT_ANCHOR) {
            claim_take(state, i, body->spawn_cell);
            if (authored->type == ENT_SENTRY) {
                body->facing = sentry_facing_from_alcove(state, body->spawn_cell);
            }
        }
    }
}

/*
 * The type-independent half of a tick: retire what has finished dissolving.
 * The state machines themselves are ai.c's.
 */
void entities_step(GameState *state)
{
    uint16_t i;

    for (i = 0; i < state->level->entity_count; ++i) {
        EntityRuntime *body = &state->entities[i];

        if (!entity_is_live(state, i) || body->state != ENT_STATE_DEAD) {
            continue;
        }
        if (--body->state_timer == 0) {
            state->entity_alive[i] = 0;     /* the sprite pass stops drawing it here */
        }
    }
}

uint16_t entities_alert_by_noise(GameState *state)
{
    uint16_t woken = 0;
    uint16_t i;

    for (i = 0; i < state->level->entity_count; ++i) {
        EntityRuntime *body = &state->entities[i];
        const EnemyStats *stats = entity_stats(body->type);
        int32_t noise_squared;

        if (!entity_is_live(state, i) || body->state != ENT_STATE_IDLE
            || !entity_type_is_enemy(body->type)) {
            continue;
        }
        noise_squared = mul16((int16_t)stats->noise_units, (int16_t)stats->noise_units);
        if (ai_distance_squared(body->x, body->y, state->player.x, state->player.y)
            > noise_squared) {
            continue;
        }
        woken = (uint16_t)(woken + entity_alert(state, i));
    }
    return woken;
}

/* ---- hashing ------------------------------------------------------------ */

uint32_t entities_hash(const GameState *state, uint32_t hash)
{
    uint16_t i;

    for (i = 0; i < LEVEL_MAX_ENTITIES; ++i) {
        const EntityRuntime *body = &state->entities[i];

        hash = fnv_byte(hash, body->state);
        hash = fnv_byte(hash, body->flags);
        hash = fnv_byte(hash, body->hp);
        hash = fnv_word(hash, (uint16_t)body->x);
        hash = fnv_word(hash, (uint16_t)body->y);
        hash = fnv_word(hash, body->facing);
        hash = fnv_word(hash, body->state_timer);
        hash = fnv_word(hash, body->attack_timer);
        hash = fnv_word(hash, body->claim_cell);
        hash = fnv_word(hash, (uint16_t)body->target_x);
        hash = fnv_word(hash, (uint16_t)body->target_y);
    }
    return hash;
}
