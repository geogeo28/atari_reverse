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
#include "game_consts.h"
#include "level.h"
#include "map.h"
#include "player.h"
#include "rng.h"

typedef struct {
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
} GameState;

void game_init(GameState *state, const Level *level, uint16_t seed);
void game_step(GameState *state, uint16_t input);

/* Open the door in `cell` if there is one and it is openable.  Returns 1 if a
 * door started or continued opening. */
int game_touch_door(GameState *state, int32_t cell);

/* FNV-1a over the named fields, never over the raw struct: padding bytes are
 * not reproducible across compilers. */
uint32_t game_state_hash(const GameState *state);

#endif /* BLACKICE_GAME_H */
