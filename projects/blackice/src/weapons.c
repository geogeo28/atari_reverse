/*
 * weapons.c - the Buster.
 *
 * DESIGN 7's whole weapon is a grid walk down the player's facing that stops
 * at the first thing it meets.  A body claims a cell (entities.h), so "the
 * first thing" is a byte lookup per cell and never a scan of the entity table,
 * and the wall behind a body can never be hit before the body is - which is the
 * property test_weapons.py pins.
 */
#include "ai.h"
#include "entities.h"
#include "events.h"
#include "game.h"
#include "sim.h"
#include "trace.h"
#include "weapons.h"

void weapons_init(GameState *state)
{
    state->weapon_cooldown = 0;
    state->muzzle_flash = 0;
}

/* The far end of the Buster's reach, as a point the grid walk can aim at. */
static void hitscan_endpoint(const GameState *state, fix88_t *out_x, fix88_t *out_y)
{
    int16_t cosine = angle_cos(state->player.angle);
    int16_t sine = angle_sin(state->player.angle);

    *out_x = (fix88_t)(state->player.x
                       + (mul16(cosine, (int16_t)BUSTER_RANGE_UNITS) >> TRIG_SHIFT));
    *out_y = (fix88_t)(state->player.y
                       + (mul16(sine, (int16_t)BUSTER_RANGE_UNITS) >> TRIG_SHIFT));
}

int32_t weapon_hitscan_target(const GameState *state, int32_t *out_distance_units)
{
    const MapGrid grid = level_grid(state->level);
    GridWalk walk;
    fix88_t end_x;
    fix88_t end_y;
    uint16_t reach;
    uint16_t step;

    hitscan_endpoint(state, &end_x, &end_y);
    grid_walk_init(&walk, &grid, state->player.x, state->player.y, end_x, end_y);
    /* The walk knows exactly how many cells lie between the muzzle and the end
     * of the Buster's reach, so the range test is the loop bound and not a
     * comparison against the far cell's coordinates. */
    reach = walk.steps_left;
    if (reach > GRID_WALK_MAX_STEPS) {
        reach = GRID_WALK_MAX_STEPS;
    }

    /*
     * The player's OWN cell counts, which is why the body test comes before the
     * wall test and the step counter starts at zero.  A Watchdog closes to a
     * 0.6-cell melee reach, which puts it inside the cell you are standing in,
     * and a walk that only looked at the cells it stepped into would make the
     * one enemy that is actually eating you the one enemy you cannot shoot.
     */
    for (step = 0; ; ++step) {
        int32_t hit = entity_hittable_in_cell(state, walk.cell);

        if (hit >= 0) {
            if (out_distance_units) {
                *out_distance_units = ai_distance_squared(state->player.x, state->player.y,
                                                          state->entities[hit].x,
                                                          state->entities[hit].y);
            }
            return hit;
        }
        if (step > 0 && map_cell_blocks(&state->blocking, walk.cell)) {
            return -1;                          /* a wall, or a door that is not OPEN */
        }
        if (step == reach) {
            return -1;                          /* the shot ran out of range */
        }
        grid_walk_step(&walk);
    }
}

/*
 * DESIGN 7's damage falls off past BUSTER_FALLOFF_UNITS, and the brownout
 * floor at zero cycles replaces both the damage and the rate.  `distance` is
 * the SQUARED distance the hitscan reported, so the comparison is against the
 * squared threshold and no square root is taken.
 *
 * `brownout` is passed in and not re-derived: the caller has already SPENT the
 * cycle by the time the damage is worked out, so a shot fired with exactly
 * BUSTER_COST_CYCLES left would read as a brownout here and do 3 damage on the
 * one shot that was properly paid for.
 */
static uint8_t buster_damage(int brownout, int32_t distance_squared)
{
    const int32_t falloff_squared = mul16((int16_t)BUSTER_FALLOFF_UNITS,
                                          (int16_t)BUSTER_FALLOFF_UNITS);

    if (brownout) {
        return BUSTER_BROWNOUT_DAMAGE;
    }
    return distance_squared > falloff_squared ? BUSTER_DAMAGE_FAR : BUSTER_DAMAGE_NEAR;
}

static void buster_fire(GameState *state)
{
    int32_t distance_squared = 0;
    int32_t target = weapon_hitscan_target(state, &distance_squared);
    const int brownout = state->cycles < BUSTER_COST_CYCLES;

    if (!brownout) {
        state->cycles -= BUSTER_COST_CYCLES;
    }
    state->weapon_cooldown = brownout ? BUSTER_BROWNOUT_RATE_TICKS : BUSTER_RATE_TICKS;
    state->muzzle_flash = MUZZLE_FLASH_TICKS;
    event_push(&state->events, EV_SFX_BUSTER_SHOT);

    /*
     * DESIGN 8: the shot is heard whether or not it connects, and DESIGN 9
     * charges +2% for firing inside the noise radius of an enemy that had not
     * noticed you yet.  entities_alert_by_noise counts exactly those.
     */
    if (entities_alert_by_noise(state) > 0) {
        trace_apply(state, TRACE_BUMP_NOISE_SHOT);
    }
    if (target >= 0) {
        entity_damage(state, (uint16_t)target, buster_damage(brownout, distance_squared));
    }
}

void weapons_step(GameState *state, uint16_t input)
{
    if (state->muzzle_flash > 0) {
        --state->muzzle_flash;
    }
    if (state->weapon_cooldown > 0) {
        --state->weapon_cooldown;
        return;
    }
    /*
     * DESIGN 6: "edge-triggered on press; holding fire auto-repeats at the
     * current weapon's rate of fire".  Both are this one rule - fire while the
     * button is down and the cooldown has expired - because the cooldown starts
     * at zero, so the first press fires on the tick it arrives and every repeat
     * waits out the rate.
     */
    if (input & INPUT_FIRE) {
        buster_fire(state);
    }
}
