/*
 * weapons.h - the Buster, and the hitscan every weapon in this game is.
 *
 * DESIGN 7 makes both weapons hitscan on purpose: a projectile is a sprite,
 * sprites are the scarcest per-frame resource, and a weapon that eats the
 * budget you need for enemies makes the game worse exactly when it matters.
 * So a shot is a grid walk (ai.h) that stops at the first body or wall.
 *
 * Only the Buster ships in the first playable; Spike is deferred (DESIGN 18).
 */
#ifndef BLACKICE_WEAPONS_H
#define BLACKICE_WEAPONS_H

#include <stdint.h>
#include "fixed.h"
#include "game_rules.h"

struct GameState;   /* game.h owns the definition; declared to break the cycle */

void weapons_init(struct GameState *state);

/*
 * DESIGN 6: fire is edge-triggered on press and auto-repeats at the weapon's
 * rate while held.  Both fall out of one rule - fire when the button is down
 * and the cooldown has expired - because the cooldown starts at zero.
 */
void weapons_step(struct GameState *state, uint16_t input);

/*
 * Walk the Buster's hitscan from the player along the current facing and
 * return the entity it hit, or -1 for a wall, a closed door or empty range.
 * Exposed so a test can assert what the shot found without firing it.
 */
int32_t weapon_hitscan_target(const struct GameState *state, int32_t *out_distance_units);

#endif /* BLACKICE_WEAPONS_H */
