/*
 * pickups.c - collecting things, and the token ledger locked doors consult.
 *
 * DESIGN 6 gives the game no use key: you collect by standing on it and you
 * open by walking into it.  So this file is two halves of one verb - a sweep
 * over the pickups the player's body overlaps, and the strong definition of
 * game.h's weak `door_may_open` hook, which is how the engine's door table asks
 * about a token without ever learning what one is.
 */
#include "entities.h"
#include "events.h"
#include "game.h"
#include "pickups.h"
#include "trace.h"

/*
 * What each pickup type does, in one table so DESIGN 10's list and the code
 * that applies it cannot drift.  `token` is a TOKEN_*_BIT, `cycles` and
 * `integrity` are added and capped, `trace_milli` is applied as a one-shot,
 * and `message` is the HUD line.
 */
typedef struct {
    uint8_t  token;
    uint8_t  message;
    int16_t  cycles;
    int16_t  integrity;
    int32_t  trace_milli;
    uint8_t  data_cache;
} PickupEffect;

static const PickupEffect PICKUP_EFFECTS[ENT_TYPE_COUNT] = {
    [ENT_TOKEN_ALPHA]     = { TOKEN_ALPHA_BIT, EV_MSG_TOKEN_ALPHA, 0, 0, 0, 0 },
    [ENT_TOKEN_BETA]      = { TOKEN_BETA_BIT,  EV_MSG_TOKEN_BETA,  0, 0, 0, 0 },
    [ENT_TOKEN_GAMMA]     = { TOKEN_GAMMA_BIT, EV_MSG_TOKEN_GAMMA, 0, 0, 0, 0 },
    [ENT_CYCLES_SMALL]    = { 0, EV_MSG_CYCLES, PICKUP_CYCLES_SMALL, 0, 0, 0 },
    [ENT_CYCLES_LARGE]    = { 0, EV_MSG_CYCLES, PICKUP_CYCLES_LARGE, 0, 0, 0 },
    [ENT_INTEGRITY_SMALL] = { 0, EV_MSG_INTEGRITY, 0, PICKUP_INTEGRITY_SMALL, 0, 0 },
    [ENT_INTEGRITY_LARGE] = { 0, EV_MSG_INTEGRITY, 0, PICKUP_INTEGRITY_LARGE, 0, 0 },
    [ENT_SCRUBBER]        = { 0, EV_MSG_SCRUBBER, 0, 0, -TRACE_DROP_SCRUBBER, 0 },
    [ENT_DATA_CACHE]      = { 0, EV_MSG_DATA_CACHE, 0, 0, 0, 1 },
};

/* A type with no effect row is not a pickup: an enemy, an anchor, or nothing. */
static int type_is_pickup(uint8_t type)
{
    const PickupEffect *effect = &PICKUP_EFFECTS[type];

    return effect->token != 0 || effect->cycles != 0 || effect->integrity != 0
        || effect->trace_milli != 0 || effect->data_cache != 0;
}

uint8_t door_required_token(uint8_t variant)
{
    switch (variant) {
    case DOOR_LOCK_ALPHA:
        return TOKEN_ALPHA_BIT;
    case DOOR_LOCK_BETA:
        return TOKEN_BETA_BIT;
    case DOOR_LOCK_GAMMA:
        return TOKEN_GAMMA_BIT;
    default:
        return 0;
    }
}

/*
 * The strong definition of game.h's weak hook.  Linking this file replaces the
 * engine's "locked means never" with DESIGN 10's "locked means show me the
 * token", and nothing in game.c had to learn what a token is.
 */
int door_may_open(const GameState *state, const Door *door)
{
    uint8_t needed = door_required_token(door->variant);

    return needed == 0 || (state->tokens & needed) != 0;
}

void pickups_init(GameState *state)
{
    state->tokens = 0;
    state->data_caches = 0;
    state->integrity = PLAYER_INTEGRITY_START;
    state->cycles = PLAYER_CYCLES_START;
}

static int16_t add_capped(int16_t value, int16_t gain, int16_t cap)
{
    int32_t sum = (int32_t)value + gain;

    return (int16_t)(sum > cap ? cap : sum);
}

static void collect(GameState *state, uint16_t index)
{
    const EntityRuntime *body = &state->entities[index];
    const PickupEffect *effect = &PICKUP_EFFECTS[body->type];

    state->entity_alive[index] = 0;
    state->tokens |= effect->token;
    state->data_caches = (uint8_t)(state->data_caches + effect->data_cache);
    state->cycles = add_capped(state->cycles, effect->cycles, PLAYER_CYCLES_MAX);
    state->integrity = add_capped(state->integrity, effect->integrity,
                                  PLAYER_INTEGRITY_MAX);
    if (effect->trace_milli != 0) {
        trace_apply(state, effect->trace_milli);
    }
    event_push(&state->events, effect->message);
    event_push(&state->events, EV_SFX_TOKEN_GRAB);
}

/*
 * A pickup is collected anywhere inside its cell (DESIGN 10 and DESIGN 17.1:
 * it is a floor object in the lower half of the cell, not a target).  The test
 * is therefore a box and not a circle, which costs two compares and no
 * multiply.
 */
static int player_is_on(const GameState *state, const EntityRuntime *body)
{
    int16_t dx = (int16_t)(state->player.x - body->x);
    int16_t dy = (int16_t)(state->player.y - body->y);

    if (dx < 0) {
        dx = (int16_t)-dx;
    }
    if (dy < 0) {
        dy = (int16_t)-dy;
    }
    return dx < PICKUP_REACH_UNITS && dy < PICKUP_REACH_UNITS;
}

void pickups_step(GameState *state)
{
    uint16_t i;

    for (i = 0; i < state->level->entity_count; ++i) {
        const EntityRuntime *body = &state->entities[i];

        if (!entity_is_live(state, i) || !type_is_pickup(body->type)) {
            continue;
        }
        if (player_is_on(state, body)) {
            collect(state, i);
        }
    }
}
