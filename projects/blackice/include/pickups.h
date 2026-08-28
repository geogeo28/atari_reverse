/*
 * pickups.h - walking over things, and walking into locked doors.
 *
 * Both are the same verb.  DESIGN 6 gives the game no use key and no switches:
 * you collect by standing on it and you open by walking into it, and a door
 * that wants a token you do not carry refuses with a HUD line and a tone.  So
 * the pickup sweep and the door predicate live together here.
 */
#ifndef BLACKICE_PICKUPS_H
#define BLACKICE_PICKUPS_H

#include <stdint.h>
#include "game_rules.h"

struct GameState;   /* game.h owns the definition; declared to break the cycle */

void pickups_init(struct GameState *state);

/* Collect every pickup the player's body is standing on this tick. */
void pickups_step(struct GameState *state);

/*
 * The token bit a locked door variant demands, or 0 if it demands none.
 * pickups.c also defines game.h's `door_may_open` hook in terms of it, which is
 * how the engine's door table asks about a token without knowing what one is;
 * the rest of the contact rules - the sector exit ending the level, the sealed
 * gate refusing, the locked-door latch and its +3% - are sim.c's, because they
 * have side effects and the hook is a pure predicate.
 */
uint8_t door_required_token(uint8_t variant);

#endif /* BLACKICE_PICKUPS_H */
