/*
 * game.c - the 25 Hz simulation tick: input, the player, the doors, the trace.
 *
 * Everything mutable lives in the caller's GameState, so a host replay can
 * snapshot and hash a run.  There is no AI here yet: DESIGN 8's state machines
 * are a separate deliverable, and the entity list currently only feeds the
 * sprite renderer.
 */
#include "game.h"
#include "hash.h"
#include "render.h"
#include "sim.h"

/* Rising-edge test against the previous tick's input word. */
#define PRESSED(now, before, bit) (((now) & (bit)) && !((before) & (bit)))

static void door_set_blocking(GameState *state, const Door *door)
{
    map_set_blocking(&state->blocking, door->cell, !DOOR_IS_PASSABLE(*door));
}

/* Does the player's body overlap this door's cell? */
static int player_occupies_cell(const GameState *state, const Door *door)
{
    int32_t left = (int32_t)door->cell_x << CELL_SHIFT;
    int32_t top = (int32_t)door->cell_y << CELL_SHIFT;

    return state->player.x + PLAYER_RADIUS > left
        && state->player.x - PLAYER_RADIUS < left + CELL_UNITS
        && state->player.y + PLAYER_RADIUS > top
        && state->player.y - PLAYER_RADIUS < top + CELL_UNITS;
}

/*
 * Is ANY body standing in this door's cell?  A door in this game never shuts on
 * a body, and until this asked about enemies too, "a body" meant the player: a
 * Watchdog walking a gate would be cut in half by the leaf, and worse, the door
 * would set the cell's blocking bit under a body that is already inside it -
 * which the collider and the flood both read as a wall with an enemy in it.
 *
 * An enemy counts if it CLAIMS the cell or is DRAWN in it, for the same reason
 * a shot has to hit both: a mover claims the cell ahead and then walks to its
 * centre, so a body halfway through a doorway is drawn in it while the claim
 * map already names the cell beyond.
 */
static int body_occupies_cell(const GameState *state, const Door *door)
{
    return player_occupies_cell(state, door)
        || entity_hittable_in_cell(state, door->cell) >= 0;
}

/*
 * The default permission rule, weak so the game layer can replace it without
 * the engine ever learning what a token is: a plain door opens for anyone, a
 * locked one for nobody.  DESIGN 10 gives locked doors 17/18/19 to the token
 * ledger, and that ledger lives above this file.
 */
BLACKICE_WEAK int door_may_open(const GameState *state, const Door *door)
{
    (void)state;
    return !door_variant_is_locked(door->variant);
}

int game_touch_door(GameState *state, int32_t cell)
{
    uint8_t index;
    Door *door;

    if (cell < 0) {
        return 0;
    }
    index = state->door_of_cell[cell];
    if (index == DOOR_NONE) {
        return 0;
    }
    door = &state->doors[index];
    if (door_variant_is_fixed(door->variant) || !door_may_open(state, door)) {
        return 0;
    }
    switch (door->state) {
    case DOOR_STATE_CLOSED:
    case DOOR_STATE_CLOSING:
        /* A door caught on its way shut re-opens from wherever it is; the
         * travel time is the same either way in the two-state renderer. */
        door->state = DOOR_STATE_OPENING;
        door->timer = DOOR_OPENING_TICKS;
        break;
    case DOOR_STATE_OPEN:
        door->timer = DOOR_OPEN_TICKS;      /* standing in it holds it open */
        break;
    default:
        break;                              /* already travelling open */
    }
    return 1;
}

static void door_tick(GameState *state, Door *door)
{
    switch (door->state) {
    case DOOR_STATE_OPENING:
        if (--door->timer == 0) {
            door->state = DOOR_STATE_OPEN;
            door->timer = DOOR_OPEN_TICKS;
            door_set_blocking(state, door);
        }
        break;

    case DOOR_STATE_OPEN:
        if (--door->timer == 0) {
            if (body_occupies_cell(state, door)) {
                door->timer = DOOR_OPEN_TICKS;      /* something is standing in it */
            } else {
                door->state = DOOR_STATE_CLOSING;
                door->timer = DOOR_CLOSING_TICKS;
                door_set_blocking(state, door);
            }
        }
        break;

    case DOOR_STATE_CLOSING:
        /* A body caught inside sends the leaf back the other way: a door in
         * this game can never shut on anything that is standing in it. */
        if (body_occupies_cell(state, door)) {
            door->state = DOOR_STATE_OPENING;
            door->timer = DOOR_OPENING_TICKS;
        } else if (--door->timer == 0) {
            door->state = DOOR_STATE_CLOSED;
        }
        break;

    default:
        break;                                      /* CLOSED waits for a bump */
    }
}

void game_init(GameState *state, const Level *level, uint32_t seed)
{
    const MapGrid grid = level_grid(level);
    uint16_t i;

    state->level = level;
    state->player.x = cell_centre(level->start_cell_x);
    state->player.y = cell_centre(level->start_cell_y);
    state->player.angle = ANGLE_FROM_BRADS(level->start_facing_brads);
    rng_seed(&state->rng, seed);
    state->door_count = map_collect_doors(&grid, state->doors);
    map_build_door_index(&grid, state->doors, state->door_count, state->door_of_cell);
    map_build_blocking(&grid, state->doors, state->door_count, &state->blocking);
    state->tick = 0;
    state->prev_input = 0;
    state->throttle = THROTTLE_DEFAULT;
    state->throttle_lock = 0;
    state->detail_level = DETAIL_DEFAULT;
    state->trace_milli = (int32_t)level->trace_start * TRACE_MILLI_PER_PERCENT;
    for (i = 0; i < LEVEL_MAX_ENTITIES; ++i) {
        state->entity_alive[i] = (uint8_t)(i < level->entity_count);
    }
    sim_init(state);            /* the game layer: entities, weapons, trace, phase */
}

/* The next throttle mode, wrapping.  A `%` here is a __modsi3 call on the
 * 68000; three modes make a compare and a reset exactly equivalent. */
static uint8_t throttle_after(uint8_t throttle)
{
    uint8_t next = (uint8_t)(throttle + 1);

    /* DESIGN 18 item 6: the first playable's dial is a two-state UNDERCLOCK
     * <-> NOMINAL toggle.  OVERCLOCK is still in the mode table, and still
     * reachable by setting the field, but it arrives with 160-column mode. */
    return (uint8_t)(next < THROTTLE_TOGGLE_MODES ? next : 0);
}

void game_step(GameState *state, uint16_t input)
{
    const MapGrid grid = level_grid(state->level);
    /*
     * `input` is what the player is HOLDING and is what prev_input latches, so
     * a held throttle key stays held across the lock and cannot re-fire when
     * the lock expires.  `sim_input` is what this tick acts on, which the
     * switch zeroes - DESIGN 5: changing gear costs you the tick.
     */
    uint16_t sim_input = input;
    int32_t bumped_cell;
    uint16_t i;

    if (state->throttle_lock) {
        --state->throttle_lock;
        sim_input = 0;
    } else if (PRESSED(input, state->prev_input, INPUT_THROTTLE_NEXT)) {
        state->throttle = throttle_after(state->throttle);
        state->throttle_lock = THROTTLE_SWITCH_TICKS;
        sim_input = 0;
    }

    player_step(&state->player, sim_input, render_mode(state)->speed_scale,
                &grid, &state->blocking, &bumped_cell);

    /* DESIGN 6: walking into a door is the only thing that opens it. */
    game_touch_door(state, bumped_cell);
    /* Published for the game layer, which judges a locked gate and a sector
     * exit - both rules the collider must not know about. */
    state->bumped_cell = (int16_t)bumped_cell;

    for (i = 0; i < state->door_count; ++i) {
        door_tick(state, &state->doors[i]);
    }
    sim_step(state, sim_input);

    state->prev_input = input;
    ++state->tick;
}

/* ---- hashing ------------------------------------------------------------ */

uint32_t game_state_hash(const GameState *state)
{
    uint32_t hash = FNV_OFFSET_BASIS;
    uint16_t i;

    hash = fnv_word(hash, (uint32_t)(uint16_t)state->player.x);
    hash = fnv_word(hash, (uint32_t)(uint16_t)state->player.y);
    hash = fnv_word(hash, state->player.angle);
    hash = fnv_word(hash, state->rng.state);
    hash = fnv_word(hash, state->tick);
    hash = fnv_word(hash, (uint32_t)state->trace_milli);
    hash = fnv_word(hash, state->prev_input);   /* live edge-detection state */
    hash = fnv_byte(hash, state->throttle);
    hash = fnv_byte(hash, state->throttle_lock);
    hash = fnv_word(hash, state->door_count);
    for (i = 0; i < state->door_count; ++i) {
        hash = fnv_word(hash, state->doors[i].cell);
        hash = fnv_byte(hash, state->doors[i].state);
        hash = fnv_word(hash, state->doors[i].timer);
    }
    hash = fnv_bytes(hash, state->entity_alive, LEVEL_MAX_ENTITIES);
    hash = fnv_bytes(hash, state->blocking.solid, MAP_BITMAP_BYTES);
    return sim_hash(state, hash);
}
