/*
 * sim.c - the game layer's half of a tick, and the two hooks game.c calls.
 *
 * game.c owns input latching, the player body and the door state machines.
 * Everything above that hangs off sim_init and sim_step, so the engine has one
 * line for the game and not a second copy of the design document.
 *
 * The order inside a tick matters and is the order below:
 *   1. retire what finished dissolving, so a corpse cannot be shot or block
 *   2. the AI, which is what sets `enemy_has_los` for the trace meter
 *   3. the weapons, so a shot lands on the positions the player just saw
 *   4. the pickups, so walking onto one collects it the tick you arrive
 *   5. the door the collider bumped, which is where a locked gate is judged
 *   6. the trace meter, last, so this tick's LOS and this tick's bumps count
 *   7. the run's phase
 */
#include "game.h"
#include "hash.h"
#include "sim.h"

void sim_init(GameState *state)
{
    event_reset(&state->events);
    /* Before entities_init: the Sentry alcove test reads the offsets, and every
     * neighbour walk in the game layer reads them from here for the rest of the
     * level rather than multiplying by the width again. */
    ai_neighbour_offsets((int16_t)state->level->width, state->neighbour_offset);
    entities_init(state);
    weapons_init(state);
    pickups_init(state);
    /* trace_init is the single authority on the start value, including the
     * carry terms game_init cannot see.  A fresh start carries nothing. */
    trace_init(state, 0);

    state->nav.next_rebuild_tick = 0;   /* ai_step floods on the very first tick */
    state->nav.origin_cell = 0;
    state->phase = PHASE_PLAYING;
    state->next_sector_index = state->level->sector_index;
    state->route_ticks = 0;
    state->kills = 0;
    state->enemy_has_los = 0;
    state->bumped_cell = -1;
    state->prev_bumped_cell = -1;
}

void sim_damage_player(GameState *state, uint8_t damage)
{
    event_push(&state->events, EV_SFX_PLAYER_HIT);
    trace_apply(state, TRACE_BUMP_PLAYER_HIT);      /* DESIGN 9: taking a hit is +1% */
    state->integrity = (int16_t)(state->integrity - damage);
    if (state->integrity > 0) {
        return;
    }
    state->integrity = 0;
    state->phase = PHASE_DEAD;
    /*
     * DESIGN 15: retries are unlimited and restart the current sector, and each
     * death costs +10% starting trace.  The count is carried out in the
     * RunProgress the platform layer hands back to game_start_level.
     */
    ++state->deaths_this_sector;
    event_push(&state->events, EV_MSG_CONNECTION_TERMINATED);
}

/* ---- the door the collider bumped ---------------------------------------- */

static const uint8_t TOKEN_REFUSAL_MESSAGE[] = {
    [DOOR_LOCK_ALPHA - CELL_DOOR_BASE] = EV_MSG_ALPHA_REQUIRED,
    [DOOR_LOCK_BETA  - CELL_DOOR_BASE] = EV_MSG_BETA_REQUIRED,
    [DOOR_LOCK_GAMMA - CELL_DOOR_BASE] = EV_MSG_GAMMA_REQUIRED,
};

static void refuse(GameState *state, uint8_t message)
{
    event_push(&state->events, message);
    event_push(&state->events, EV_SFX_DOOR_REFUSAL);
}

/*
 * DESIGN 10: a locked door opened with its token PERMANENTLY becomes a plain
 * gate for the rest of the sector, and the +3% charge fires once per door per
 * sector.  The latch is what makes both true with no extra state: once the
 * variant is 16, door_required_token returns 0 and this branch is unreachable.
 */
static void latch_locked_door(GameState *state, Door *door)
{
    door->variant = DOOR_PLAIN;
    trace_apply(state, TRACE_BUMP_LOCKED_DOOR);
    event_push(&state->events, EV_SFX_GATE_OPEN);
}

/*
 * React to a door the player has just walked into.  Only a NEW bump is judged:
 * leaning on a gate you cannot open must not repeat its refusal line every
 * 40 ms.
 */
static void handle_door_bump(GameState *state)
{
    int16_t cell = state->bumped_cell;
    uint8_t index;
    Door *door;

    if (cell < 0 || cell == state->prev_bumped_cell) {
        return;
    }
    index = state->door_of_cell[cell];
    if (index == DOOR_NONE) {
        return;
    }
    door = &state->doors[index];

    switch (door->variant) {
    case DOOR_SECTOR_EXIT:
        /* Terminal: touching the arch ends the sector.  It never opens, which
         * is what keeps the map border sealed for the DDA and the BFS. */
        state->phase = PHASE_LEVEL_CLEAR;
        state->next_sector_index = (uint8_t)(state->level->sector_index + 1);
        event_push(&state->events, EV_MSG_SECTOR_CLEAR);
        event_push(&state->events, EV_SFX_GATE_OPEN);
        break;

    case DOOR_SEALED:
        refuse(state, EV_MSG_GATE_SEALED);
        break;

    case DOOR_CORRUPTED:
        /* Jammed forever, and DESIGN 10 gives it no line of its own. */
        event_push(&state->events, EV_SFX_DOOR_REFUSAL);
        break;

    case DOOR_LOCK_ALPHA:
    case DOOR_LOCK_BETA:
    case DOOR_LOCK_GAMMA:
        if (door_may_open(state, door)) {
            latch_locked_door(state, door);
        } else {
            refuse(state, TOKEN_REFUSAL_MESSAGE[door->variant - CELL_DOOR_BASE]);
        }
        break;

    case DOOR_PLAIN:
        event_push(&state->events, EV_SFX_GATE_OPEN);
        break;

    default:
        break;
    }
}

/* ---- the tick ------------------------------------------------------------ */

void sim_step(GameState *state, uint16_t input)
{
    if (state->phase != PHASE_PLAYING) {
        return;                             /* dead or cleared: the sim is frozen */
    }
    ++state->route_ticks;

    /* DESIGN 5's dial moved this tick: the switch has just armed its lock. */
    if (state->throttle_lock == THROTTLE_SWITCH_TICKS) {
        event_push(&state->events, EV_SFX_THROTTLE_CHANGE);
    }

    entities_step(state);
    ai_step(state);
    weapons_step(state, input);
    pickups_step(state);
    handle_door_bump(state);
    state->prev_bumped_cell = state->bumped_cell;
    trace_step(state, input);

    /*
     * DESIGN 18 item 5: the Hunter and the 100% exfil are deferred, so in the
     * first playable reaching HARDENED swaps the palette (trace.c has already
     * published it) and immediately runs the death path.
     */
    if (state->trace_band == TRACE_BAND_HARDENED && state->phase == PHASE_PLAYING) {
        event_push(&state->events, EV_SFX_EXFIL_SIREN);
        sim_damage_player(state, (uint8_t)state->integrity);
    }
}

/* ---- hashing ------------------------------------------------------------- */

/*
 * The occupancy map, the navigation field and the neighbour offsets are
 * DERIVED - from the entity table, from the player's cell and the blocking
 * bitmap, and from the level's width - so they are deliberately not hashed.
 * Hashing them would cost 8 KB of FNV a tick and could only ever report a
 * divergence the entity table already reports.
 *
 * The event ring IS hashed, and it is the one thing here that is not state at
 * all: it is the sim's entire OUTPUT surface.  A change that plays the wrong
 * cue, plays one twice, or drops a HUD line moves no other field in this
 * struct, so without the ring a whole class of regression is invisible to the
 * replay - which is the differential's only claim.  The contents are hashed in
 * ring order, plus the dropped count, so a policy change shows up as a
 * divergence and not as silence.
 */
static uint32_t events_hash(const EventQueue *queue, uint32_t hash)
{
    uint8_t slot = queue->tail;

    while (slot != queue->head) {
        hash = fnv_byte(hash, queue->ids[slot]);
        slot = (uint8_t)((slot + 1) & EVENT_QUEUE_MASK);
    }
    return fnv_byte(hash, queue->dropped);
}

uint32_t sim_hash(const GameState *state, uint32_t hash)
{
    hash = entities_hash(state, hash);
    hash = events_hash(&state->events, hash);
    hash = fnv_word(hash, (uint16_t)state->integrity);
    hash = fnv_word(hash, (uint16_t)state->cycles);
    hash = fnv_word(hash, (uint16_t)state->trace_remainder);
    hash = fnv_word(hash, state->route_ticks);
    hash = fnv_word(hash, state->music_tempo_bpm);
    hash = fnv_word(hash, (uint16_t)state->bumped_cell);
    hash = fnv_word(hash, (uint16_t)state->prev_bumped_cell);
    hash = fnv_byte(hash, state->tokens);
    hash = fnv_byte(hash, state->phase);
    hash = fnv_byte(hash, state->next_sector_index);
    hash = fnv_byte(hash, state->trace_band);
    hash = fnv_byte(hash, state->palette_variant);
    hash = fnv_byte(hash, state->enemy_tier);
    hash = fnv_byte(hash, state->weapon_cooldown);
    hash = fnv_byte(hash, state->muzzle_flash);
    hash = fnv_byte(hash, state->deaths_this_sector);
    hash = fnv_byte(hash, state->data_caches);
    hash = fnv_byte(hash, state->kills);
    hash = fnv_byte(hash, state->enemy_has_los);
    return hash;
}
