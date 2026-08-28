/*
 * game.h - GameState: every byte of mutable simulation state, in one struct.
 *
 * Nothing the simulation reads or writes lives in a global.  That is what lets
 * the host snapshot a run, hash it, and prove a replay is deterministic.  The
 * only globals in the engine are the const trig tables, the reciprocal tables
 * (const after tables_init) and the texture assets.
 */
#ifndef BLACKICE_GAME_H
#define BLACKICE_GAME_H

#include <stdint.h>
#include "ai.h"
#include "entities.h"
#include "events.h"
#include "game_consts.h"
#include "game_rules.h"
#include "level.h"
#include "map.h"
#include "player.h"
#include "rng.h"

typedef struct GameState {
    const Level *level;                     /* static data, not part of the hash */
    Player       player;
    Rng          rng;
    MapBlocking  blocking;
    Door         doors[DOOR_MAX_COUNT];
    uint8_t      door_of_cell[MAP_MAX_CELLS];   /* derived at init, DOOR_NONE elsewhere */
    uint16_t     door_count;
    uint32_t     tick;
    uint16_t     prev_input;                /* rising-edge detection */
    uint8_t      throttle;                  /* THROTTLE_* */
    uint8_t      throttle_lock;             /* ticks of locked input left */
    uint8_t      entity_alive[LEVEL_MAX_ENTITIES];
    int32_t      trace_milli;               /* 0 .. TRACE_MAX_MILLI */
    /* DESIGN 5 keeps the render width out of the clock throttle, so it is a
     * setting of its own.  Appended at the end of the engine half, where it
     * moves none of the offsets above it, with the padding spelled out so the
     * game layer below starts at a fixed place the test mirrors can name. */
    uint8_t      detail_level;              /* DETAIL_COLUMNS_* */
    uint8_t      pad_to_game_layer;

    /* ---- the game layer (src/entities.c, ai.c, weapons.c, pickups.c, trace.c) ----
     * Everything below is appended, never interleaved: the engine's fields
     * above keep their offsets, and the 68000 asm that knows them keeps
     * working.  See sim.h for how it is driven. */
    EntityRuntime   entities[LEVEL_MAX_ENTITIES];
    /* Maintained incrementally by claim_take/claim_release, never rebuilt: it
     * is derived from the entity table, so it is not hashed. */
    EntityOccupancy occupancy;
    NavField        nav;                    /* derived from the player cell, not hashed */
    /* Cell delta of neighbour n on THIS level's grid, filled at level load by
     * ai_neighbour_offsets.  Derived from the width, so it is not hashed. */
    int16_t         neighbour_offset[NEIGHBOUR_COUNT];
    EventQueue      events;                 /* drained by the platform layer */

    int16_t  integrity;                     /* 0 .. PLAYER_INTEGRITY_MAX */
    int16_t  cycles;                        /* 0 .. PLAYER_CYCLES_MAX */
    int16_t  trace_remainder;               /* sub-milli-percent carry; see trace.h */
    uint16_t route_ticks;                   /* ticks spent in this sector */
    uint16_t music_tempo_bpm;               /* DESIGN 9's tempo band, for the YM driver */
    uint8_t  tokens;                        /* TOKEN_*_BIT */
    uint8_t  phase;                         /* PHASE_* */
    uint8_t  next_sector_index;             /* valid once phase is PHASE_LEVEL_CLEAR */
    uint8_t  trace_band;                    /* 0 .. TRACE_BAND_COUNT - 1 */
    uint8_t  palette_variant;               /* the level's, escalated by the trace band */
    uint8_t  enemy_tier;                    /* DESIGN 9's tier, exposed but not yet acted on */
    uint8_t  weapon_cooldown;               /* ticks until the Buster may fire again */
    uint8_t  muzzle_flash;                  /* ticks of flash left, for the renderer */
    uint8_t  deaths_this_sector;            /* folded into DESIGN 9's start rule on retry */
    uint8_t  data_caches;                   /* DESIGN 10's route score */
    uint8_t  kills;
    uint8_t  enemy_has_los;                 /* any enemy saw the player this tick */
    int16_t  bumped_cell;                   /* cell the collider refused this tick, or -1 */
    int16_t  prev_bumped_cell;              /* so a lean on a locked gate refuses once */
} GameState;

/*
 * Is entity `index` in the world at all?
 *
 * Liveness has ONE authority and it is `entity_alive[]`.  EntityRuntime.state
 * is the authority on BEHAVIOUR and never on existence, and neither is ever
 * inferred from the other: a dissolving body is live and in ENT_STATE_DEAD -
 * still drawn, no longer shootable - and a collected pickup is not live at all
 * whatever its state says.  Every read of that fact goes through here, so the
 * two can never be asked in two different ways in two different files.
 */
static inline int entity_is_live(const GameState *state, uint16_t index)
{
    return state->entity_alive[index] != 0;
}

/* `seed` seeds the DESIGN 4.3 LCG.  The caller chooses it: the game passes
 * level->rng_seed, and a test or a tool may pass its own to fork a run. */
void game_init(GameState *state, const Level *level, uint32_t seed);
void game_step(GameState *state, uint16_t input);

/* Open the door in `cell` if there is one and it is openable.  Returns 1 if a
 * door started or continued opening. */
int game_touch_door(GameState *state, int32_t cell);

/*
 * A definition that another translation unit may replace with its own.  On the
 * 68000 this keeps a policy hook at the cost of a plain `jsr` - no function
 * pointer in GameState, no indirect call in the tick.
 */
#define BLACKICE_WEAK __attribute__((weak))

/*
 * May this door open for the body that just walked into it?  game.c supplies a
 * weak default (plain yes, locked no); the game layer overrides it with the
 * DESIGN 10 token rule by defining the same symbol strongly.
 */
int door_may_open(const GameState *state, const Door *door);

/* FNV-1a over the named fields, never over the raw struct: padding bytes are
 * not reproducible across compilers. */
uint32_t game_state_hash(const GameState *state);

#endif /* BLACKICE_GAME_H */
