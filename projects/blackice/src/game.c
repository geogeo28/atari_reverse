/*
 * game.c - the 25 Hz simulation tick: input, the player, the doors, the trace.
 *
 * Everything mutable lives in the caller's GameState, so a host replay can
 * snapshot and hash a run.  There is no AI here yet: DESIGN 8's state machines
 * are a separate deliverable, and the entity list currently only feeds the
 * sprite renderer.
 */
#include "game.h"
#include "render.h"

/* Rising-edge test against the previous tick's input word. */
#define PRESSED(now, before, bit) (((now) & (bit)) && !((before) & (bit)))

static void door_set_blocking(GameState *state, const Door *door)
{
    map_set_blocking(&state->blocking, door->cell, !DOOR_IS_PASSABLE(*door));
}

/* Does the player's body overlap this cell?  An open door will not close on
 * top of the player. */
static int body_occupies_cell(const GameState *state, uint16_t cell)
{
    const MapGrid grid = level_grid(state->level);
    /* uint16 / uint8 so the 68000 uses `divu.w` and not a libgcc call. */
    uint16_t cell_x = (uint16_t)(cell % (uint16_t)grid.width);
    uint16_t cell_y = (uint16_t)(cell / (uint16_t)grid.width);
    int32_t left = (int32_t)cell_x << CELL_SHIFT;
    int32_t top = (int32_t)cell_y << CELL_SHIFT;

    return state->player.x + PLAYER_RADIUS > left
        && state->player.x - PLAYER_RADIUS < left + CELL_UNITS
        && state->player.y + PLAYER_RADIUS > top
        && state->player.y - PLAYER_RADIUS < top + CELL_UNITS;
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
    if (door_variant_is_fixed(door->variant)) {
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
            if (body_occupies_cell(state, door->cell)) {
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
         * this game can never shut on the player. */
        if (body_occupies_cell(state, door->cell)) {
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

static void trace_tick(GameState *state)
{
    const ThrottleMode *mode = render_mode(state);
    int32_t rise = ((int32_t)state->level->trace_base_rate * mode->trace_scale) >> 8;

    state->trace_milli += rise;
    if (state->trace_milli > TRACE_MAX_MILLI) {
        state->trace_milli = TRACE_MAX_MILLI;
    }
}

void game_init(GameState *state, const Level *level, uint16_t seed)
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
    state->trace_milli = (int32_t)level->trace_start * TRACE_MILLI_PER_PERCENT;
    for (i = 0; i < LEVEL_MAX_ENTITIES; ++i) {
        state->entity_alive[i] = (uint8_t)(i < level->entity_count);
    }
}

void game_step(GameState *state, uint16_t input)
{
    const MapGrid grid = level_grid(state->level);
    int32_t bumped_cell;
    uint16_t i;

    if (state->throttle_lock) {
        --state->throttle_lock;
        input = 0;                                  /* DESIGN 5: the switch costs input */
    } else if (PRESSED(input, state->prev_input, INPUT_THROTTLE_NEXT)) {
        state->throttle = (uint8_t)((state->throttle + 1) % THROTTLE_MODE_COUNT);
        state->throttle_lock = THROTTLE_SWITCH_TICKS;
        input = 0;
    }

    player_step(&state->player, input, render_mode(state)->speed_scale,
                &grid, &state->blocking, &bumped_cell);

    /* DESIGN 6: walking into a door opens it; the explicit use key is kept as
     * a second trigger for the same mechanism. */
    game_touch_door(state, bumped_cell);
    if (PRESSED(input, state->prev_input, INPUT_USE)) {
        game_touch_door(state, player_use_target(&state->player, &grid));
    }

    for (i = 0; i < state->door_count; ++i) {
        door_tick(state, &state->doors[i]);
    }
    trace_tick(state);

    state->prev_input = input;
    ++state->tick;
}

/* ---- hashing ------------------------------------------------------------ */

#define FNV_OFFSET_BASIS 2166136261u
#define FNV_PRIME        16777619u

static uint32_t fnv_byte(uint32_t hash, uint8_t value)
{
    return (hash ^ value) * FNV_PRIME;
}

static uint32_t fnv_word(uint32_t hash, uint32_t value)
{
    hash = fnv_byte(hash, (uint8_t)(value >> 24));
    hash = fnv_byte(hash, (uint8_t)(value >> 16));
    hash = fnv_byte(hash, (uint8_t)(value >> 8));
    return fnv_byte(hash, (uint8_t)value);
}

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
    hash = fnv_byte(hash, state->throttle);
    hash = fnv_byte(hash, state->throttle_lock);
    hash = fnv_word(hash, state->door_count);
    for (i = 0; i < state->door_count; ++i) {
        hash = fnv_word(hash, state->doors[i].cell);
        hash = fnv_byte(hash, state->doors[i].state);
        hash = fnv_word(hash, state->doors[i].timer);
    }
    for (i = 0; i < LEVEL_MAX_ENTITIES; ++i) {
        hash = fnv_byte(hash, state->entity_alive[i]);
    }
    for (i = 0; i < MAP_BITMAP_BYTES; ++i) {
        hash = fnv_byte(hash, state->blocking.solid[i]);
    }
    return hash;
}
