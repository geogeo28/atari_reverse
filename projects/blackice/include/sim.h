/*
 * sim.h - the game layer's two entry points into the engine's tick.
 *
 * src/game.c owns the engine's half of a tick: input latching, the player
 * body, the door state machines.  Everything above that - enemies, weapons,
 * pickups, the trace meter, the run's phase - is the game layer, and it hangs
 * off exactly these two calls so that game.c has one line for it and not a
 * second copy of the design document.
 */
#ifndef BLACKICE_SIM_H
#define BLACKICE_SIM_H

#include <stdint.h>
#include "ai.h"
#include "entities.h"
#include "events.h"
#include "pickups.h"
#include "trace.h"
#include "weapons.h"

struct GameState;

/* Reset every game-layer field.  Called at the end of game_init. */
void sim_init(struct GameState *state);

/*
 * The game layer's half of a tick, run after the player has moved and the
 * doors have ticked.  `input` is the word game.c actually applied, which is
 * zero while the throttle switch holds input locked (DESIGN 5).
 */
void sim_step(struct GameState *state, uint16_t input);

/* Fold the game layer's state into game_state_hash's running FNV-1a. */
uint32_t sim_hash(const struct GameState *state, uint32_t hash);

/*
 * Hurt the player: DESIGN 4's integrity, DESIGN 9's +1% for taking a hit, and
 * DESIGN 15's death path at zero.  Every enemy weapon lands here.
 */
void sim_damage_player(struct GameState *state, uint8_t damage);

#endif /* BLACKICE_SIM_H */
